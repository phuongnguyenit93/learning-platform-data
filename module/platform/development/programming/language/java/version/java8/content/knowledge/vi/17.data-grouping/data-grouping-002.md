# Downstream collector và tổng hợp trong từng nhóm (Java 8)

Trong **Phân nhóm dữ liệu**, `Collectors.groupingBy(...)` không chỉ gom phần tử thành `Map<K, List<T>>`. Khi truyền **downstream collector**, bạn còn xác định **mỗi nhóm được tích lũy thành kết quả gì**: số lượng, tổng, trung bình, tập giá trị không trùng, chuỗi tên, thống kê nhiều chỉ số hoặc một bản đồ nhóm cấp hai. Đây là cách thực hiện phép tổng hợp ngay trong một lần duyệt của pipeline, tránh thu cả danh sách mỗi nhóm rồi tự viết vòng lặp xử lý tiếp.

Các API trong bài thuộc `java.util.stream.Collectors` của **Java 8**, vẫn áp dụng trong Java hiện đại. Ví dụ biên dịch được ở mức Java 8; nếu dùng JDK mới hơn, chúng vẫn chạy bình thường.

## 1. Downstream collector là gì?

Mẫu đơn giản:

```java
// Minh họa cú pháp, các biến và hàm được cung cấp bởi ứng dụng.
Map<K, List<T>> groups =
    stream.collect(Collectors.groupingBy(classifier));
```

Mặc định, mỗi phần tử `T` được phân vào nhóm có khóa `K` do `classifier` tạo ra; kết quả của từng khóa là một `List<T>`.

Mẫu có downstream:

```java
// Minh họa chữ ký ở mức ý tưởng, không phải chương trình độc lập.
Map<K, D> result =
    stream.collect(Collectors.groupingBy(classifier, downstream));
```

Lúc này, phần tử vẫn được phân nhóm bằng `classifier`, nhưng **giá trị của mỗi khóa** trở thành kết quả `D` mà `downstream` tạo ra. Ví dụ:

- `counting()`: `Map<K, Long>`, mỗi khóa là số phần tử.
- `summingInt(mapper)`: `Map<K, Integer>`, mỗi khóa là tổng giá trị số do mapper trích xuất.
- `mapping(mapper, toSet())`: `Map<K, Set<U>>`, mỗi khóa chứa các giá trị `U` không trùng.
- `joining(", ")` hoặc `mapping(..., joining(", "))`: `Map<K, String>`, mỗi khóa chứa chuỗi đã ghép.
- `summarizingInt(mapper)`: `Map<K, IntSummaryStatistics>`, mỗi khóa có count, sum, min, max, average.
- `groupingBy(secondClassifier, counting())`: `Map<K, Map<K2, Long>>`, phân nhóm hai cấp rồi đếm.

Sơ đồ xử lý:

```text
Stream<T>
    │
    ├─ classifier(element) ──> khóa K
    │
    └─ groupingBy
         ├─ nhóm A → downstream nhận các phần tử thuộc A → D_A
         ├─ nhóm B → downstream nhận các phần tử thuộc B → D_B
         └─ nhóm C → downstream nhận các phần tử thuộc C → D_C

Kết quả: Map<K, D>
```

**Điểm cốt lõi:** downstream không chạy như một terminal operation độc lập trên một `Stream` mới của từng nhóm. Nó là một phần của **collector tổng thể** mà `collect(...)` thực hiện. Framework phối hợp tạo, cập nhật và kết hợp trạng thái tích lũy của từng nhóm.

## 2. Ba overload groupingBy cần phân biệt

| Cú pháp | Giá trị mỗi khóa | Khi sử dụng |
| --- | --- | --- |
| `groupingBy(classifier)` | `List<T>` | Muốn giữ toàn bộ phần tử từng nhóm |
| `groupingBy(classifier, downstream)` | Kết quả `D` của downstream | Muốn đếm/tính tổng/ánh xạ/tổng hợp theo nhóm |
| `groupingBy(classifier, mapFactory, downstream)` | Vẫn là `D`, nhưng chọn kiểu `Map` bên ngoài | Cần `TreeMap` theo khóa, `LinkedHashMap` theo thứ tự chèn hoặc một loại Map cụ thể |

`classifier` tạo khóa nhóm. `mapFactory` như `TreeMap::new` chỉ quyết định cấu trúc của **Map bên ngoài**, không thay đổi thuật toán tính kết quả của downstream.

Trong Java 8, các hàm này có chữ ký khái quát:

```java
// Trích chữ ký rút gọn để đọc API, không phải mã đặt trong main:
<T, K> Collector<T, ?, Map<K, List<T>>>
    groupingBy(Function<? super T, ? extends K> classifier)

<T, K, A, D> Collector<T, ?, Map<K, D>>
    groupingBy(Function<? super T, ? extends K> classifier,
               Collector<? super T, A, D> downstream)

<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M>
    groupingBy(Function<? super T, ? extends K> classifier,
               Supplier<M> mapFactory,
               Collector<? super T, A, D> downstream)
```

Với downstream, kiểu **`D` khác kiểu phần tử đầu vào `T`**. Ví dụ khi đếm đơn hàng, `T` là `Sale` nhưng `D` là `Long`. Đây là lợi ích lớn: không cần tạo `List<Sale>` chỉ để lấy `size()` sau đó.

## 3. Ví dụ hoàn chỉnh: đếm, cộng và thống kê trong từng vùng

Ta có các giao dịch chứa vùng, tên mặt hàng và số lượng. Yêu cầu:

1. Đếm số giao dịch theo vùng.
2. Tính tổng số lượng theo vùng.
3. Lấy danh sách **mặt hàng không trùng** trong mỗi vùng.
4. Lấy bộ thống kê count, sum, min, max, average trên số lượng giao dịch.

Tệp **`GroupSummaryDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class GroupSummaryDemo {
    static final class Sale {
        private final String region;
        private final String item;
        private final int units;

        Sale(String region, String item, int units) {
            this.region = region;
            this.item = item;
            this.units = units;
        }

        String getRegion() { return region; }
        String getItem() { return item; }
        int getUnits() { return units; }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
            new Sale("North", "Book", 2),
            new Sale("South", "Pen", 5),
            new Sale("North", "Pen", 3),
            new Sale("North", "Book", 4),
            new Sale("South", "Book", 1)
        );

        Map<String, Long> counts = sales.stream().collect(
            Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.counting()));

        Map<String, Integer> unitsByRegion = sales.stream().collect(
            Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.summingInt(Sale::getUnits)));

        Map<String, Set<String>> items = sales.stream().collect(
            Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.mapping(
                    Sale::getItem,
                    Collectors.toCollection(LinkedHashSet::new))));

        Map<String, IntSummaryStatistics> stats = sales.stream().collect(
            Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.summarizingInt(Sale::getUnits)));

        System.out.println("counts=" + counts);
        System.out.println("units=" + unitsByRegion);
        System.out.println("items=" + items);

        stats.forEach((region, s) -> System.out.printf(Locale.ROOT,
            "%s count=%d sum=%d min=%d max=%d avg=%.2f%n",
            region, s.getCount(), s.getSum(),
            s.getMin(), s.getMax(), s.getAverage()));
    }
}
```

Biên dịch/chạy với JDK đã cài:

```bash
javac -encoding UTF-8 GroupSummaryDemo.java
java GroupSummaryDemo
```

Kết quả chính xác:

```text
counts={North=3, South=2}
units={North=9, South=6}
items={North=[Book, Pen], South=[Pen, Book]}
North count=3 sum=9 min=2 max=4 avg=3.00
South count=2 sum=6 min=1 max=5 avg=3.00
```

**Giải thích từng downstream:**

- `counting()` nhận mỗi phần tử nhóm làm một lần đếm; giá trị là `Long`. `North` có ba dòng, `South` có hai dòng.
- `summingInt(Sale::getUnits)` trích `units` từ từng `Sale` rồi cộng, nên `North = 2 + 3 + 4 = 9`, `South = 5 + 1 = 6`. Đây là **tổng số lượng**, không phải số giao dịch.
- `mapping(Sale::getItem, toCollection(LinkedHashSet::new))` đổi từng `Sale` thành tên hàng **chỉ trong phần thu của mỗi nhóm**, rồi gom tên thành `LinkedHashSet` để bỏ trùng và giữ thứ tự chèn.
- `summarizingInt(Sale::getUnits)` gói nhiều thống kê liên quan vào **một đối tượng** `IntSummaryStatistics` cho mỗi vùng. `getCount()` và `getSum()` trả về `long`; `getAverage()` trả về `double`. Trong ví dụ này, trung bình 3.00 là số lượng trung bình **trên mỗi giao dịch**, không phải tổng theo vùng.
- Dùng `TreeMap::new` giúp khóa vùng được in theo thứ tự xác định; nếu bỏ `mapFactory`, không được dựa vào một thứ tự khóa hoặc kiểu map cụ thể.

Mỗi phép `sales.stream()` ở trên tạo **một Stream mới**. Không thể gọi `collect` lần thứ hai trên cùng một đối tượng Stream đã tiêu thụ. Nếu cần nhiều phép tổng hợp, cân nhắc `summarizingInt` để tránh nhiều lượt duyệt khi các chỉ số phục vụ cùng một mục đích.

### Đọc bảng kết quả cho đúng

| Vùng | Giao dịch | Tổng số lượng | Min | Max | Trung bình số lượng/giao dịch |
| --- | ---: | ---: | ---: | ---: | ---: |
| North | 3 | 9 | 2 | 4 | 3.00 |
| South | 2 | 6 | 1 | 5 | 3.00 |

Đừng nhầm `counting()` với `summingInt(s -> s.getUnits())`: một phép đếm **bản ghi**, một phép cộng **một trường số**. Khi áp dụng vào doanh thu, cần chọn kiểu số và chính sách làm tròn phù hợp (ví dụ `BigDecimal` cho tiền tệ), không mặc định dùng số thực dấu phẩy động để quyết toán.

## 4. mapping: biến đổi giá trị bên trong nhóm

Một trường hợp rất hay gặp: dữ liệu nguồn là `Employee`, nhưng giá trị mong muốn trong map chỉ là **tên nhân viên**. Mẫu:

```java
// Trong ngữ cảnh đã có List<Employee> employees,
// Employee::getTeam và Employee::getName.
Map<String, List<String>> namesByTeam = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::getTeam,
        Collectors.mapping(Employee::getName,
                           Collectors.toList())));
```

Đây là **đoạn minh họa phụ thuộc lớp Employee và biến employees**, không phải tệp độc lập. Pipeline nhóm theo `getTeam` rồi downstream `mapping` biến mỗi Employee trong nhóm thành `String` và gom vào List.

Sự khác nhau về ý nghĩa:

```text
groupingBy(Employee::getTeam)
    → Map<String, List<Employee>>

groupingBy(Employee::getTeam,
           mapping(Employee::getName, toList()))
    → Map<String, List<String>>

groupingBy(Employee::getTeam,
           mapping(Employee::getName, joining(" | ")))
    → Map<String, String>
```

Không phải tạo `Map<String, List<Employee>>` rồi lặp từng danh sách để trích `name`. Downstream `mapping` biểu đạt rõ **phần tử tích lũy của nhóm là dữ liệu đã được chiếu (project)**. Nếu mục tiêu là biến đổi mọi phần tử cùng một cách trước khi nhóm, `stream.map(...)` cũng có thể phù hợp, miễn là phần tử sau `map` còn đủ thông tin để tính khóa nhóm. Dùng downstream `mapping` khi muốn tính khóa từ đối tượng gốc nhưng thu giá trị biến đổi.

## 5. Ví dụ hoàn chỉnh: ghép tên, nhóm lồng nhau, chốt kết quả mỗi nhóm

Ta có nhân viên thuộc các đội và vai trò. Mục tiêu:

- Nối tên theo đội.
- Đếm nhân viên theo **đội → vai trò**.
- Thu một danh sách tên **không được sửa qua List API** cho từng đội.

Tệp **`GroupProjectionDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class GroupProjectionDemo {
    static final class Employee {
        final String team;
        final String role;
        final String name;

        Employee(String team, String role, String name) {
            this.team = team;
            this.role = role;
            this.name = name;
        }

        String getTeam() { return team; }
        String getRole() { return role; }
        String getName() { return name; }
    }

    public static void main(String[] args) {
        List<Employee> people = Arrays.asList(
            new Employee("Backend", "Developer", "An"),
            new Employee("Backend", "Developer", "Binh"),
            new Employee("Backend", "QA", "Chi"),
            new Employee("Platform", "SRE", "Dung"),
            new Employee("Platform", "SRE", "Em"),
            new Employee("Platform", "Developer", "Giang")
        );

        Map<String, String> names = people.stream().collect(
            Collectors.groupingBy(
                Employee::getTeam,
                TreeMap::new,
                Collectors.mapping(
                    Employee::getName, Collectors.joining(" | "))));

        Map<String, Map<String, Long>> roleCounts =
            people.stream().collect(
                Collectors.groupingBy(
                    Employee::getTeam,
                    TreeMap::new,
                    Collectors.groupingBy(
                        Employee::getRole,
                        TreeMap::new,
                        Collectors.counting())));

        Map<String, List<String>> readOnlyNames =
            people.stream().collect(
                Collectors.groupingBy(
                    Employee::getTeam,
                    TreeMap::new,
                    Collectors.collectingAndThen(
                        Collectors.mapping(
                            Employee::getName, Collectors.toList()),
                        Collections::unmodifiableList)));

        System.out.println("names=" + names);
        System.out.println("roleCounts=" + roleCounts);
        System.out.println("readOnlyNames=" + readOnlyNames);
    }
}
```

```bash
javac -encoding UTF-8 GroupProjectionDemo.java
java GroupProjectionDemo
```

```text
names={Backend=An | Binh | Chi, Platform=Dung | Em | Giang}
roleCounts={Backend={Developer=2, QA=1}, Platform={Developer=1, SRE=2}}
readOnlyNames={Backend=[An, Binh, Chi], Platform=[Dung, Em, Giang]}
```

Các điểm đáng chú ý:

1. `mapping(Employee::getName, joining(" | "))` biến đối tượng thành tên rồi nối với dấu phân cách. Mỗi đội nhận một `String`.
2. `groupingBy(Employee::getRole, TreeMap::new, counting())` là **downstream của groupingBy theo đội**. Vì thế mỗi đội có một map vai trò; mỗi vai trò có một số đếm.
3. `collectingAndThen(downstream, finisher)` thực hiện bước kết thúc của **từng kết quả downstream**. Ở đây, downstream tạo danh sách tên, còn finisher bọc bằng `Collections.unmodifiableList`.
4. `Collections.unmodifiableList` ngăn sửa thông qua danh sách trả về. Nó là **read-only view**, không tự tạo bản sao sâu hoặc khiến đối tượng bên trong bất biến. Để tạo snapshot độc lập cần nêu rõ yêu cầu sao chép và thiết kế phù hợp.
5. `TreeMap` ở cả hai cấp nhóm làm thứ tự khóa rõ ràng. Chỉ `TreeMap` bên ngoài không tự quyết định thứ tự của map bên trong, vì vậy ví dụ chỉ định factory cho cả hai cấp.

Ở đây **grouping lồng nhau** phù hợp vì bài toán thật sự có hai trục nhóm. Không nên lồng nhiều cấp chỉ để viết code “ngầu”: nếu kết quả khó đọc, hãy đặt tên kiểu dữ liệu, chia thành các phương thức nhỏ hoặc tạo đối tượng báo cáo rõ nghĩa.

## 6. Các downstream hay dùng và cách chọn

| Downstream Java 8 | Kiểu kết quả **từng nhóm** | Câu hỏi được trả lời |
| --- | --- | --- |
| `counting()` | `Long` | Có bao nhiêu bản ghi? |
| `summingInt(ToIntFunction<T>)` | `Integer` | Tổng trường `int` là bao nhiêu? |
| `summingLong(ToLongFunction<T>)` | `Long` | Tổng trường `long` hoặc biến đổi sang `long`? |
| `averagingInt(ToIntFunction<T>)` | `Double` | Trung bình trường `int`? |
| `summarizingInt(ToIntFunction<T>)` | `IntSummaryStatistics` | Count, sum, min, max, average trong một kết quả? |
| `minBy(comparator)` / `maxBy(comparator)` | `Optional<T>` | Phần tử nhỏ nhất/lớn nhất theo tiêu chí? |
| `mapping(fn, toList())` | `List<U>` | Muốn trích thông tin nào từ đối tượng? |
| `mapping(fn, toSet())` | `Set<U>` | Muốn danh sách giá trị không trùng? |
| `mapping(fn, joining(", "))` | `String` | Muốn nối thông tin thành chuỗi? |
| `groupingBy(secondFn, counting())` | `Map<K2, Long>` | Muốn nhóm cấp hai và đếm? |
| `collectingAndThen(downstream, finisher)` | Kiểu của `finisher` | Muốn xử lý kết quả cuối của từng nhóm? |
| `reducing(...)` | Tùy overload | Muốn phép giảm tùy chỉnh theo từng nhóm? |

**Thống kê số:** bên cạnh `summarizingInt`, Java 8 còn có `summarizingLong` và `summarizingDouble`. `averagingDouble` có những vấn đề độ chính xác số thực tương tự phép toán `double` thông thường. Với giá trị tiền, kết quả tài chính cần chính xác số thập phân, nên chọn biểu diễn và quy tắc làm tròn thích hợp (thường là `BigDecimal`) thay vì dùng `double` một cách ngầm định.

**Chọn min/max:** `Collectors.maxBy(Comparator.comparingInt(Employee::getAge))` trả `Optional<Employee>` cho từng nhóm; cần xử lý `Optional` đúng hợp đồng khi đưa vào DTO hoặc báo cáo. Dù `groupingBy` thường chỉ tạo nhóm khi có phần tử, vẫn nên thiết kế xử lý sự vắng mặt rõ ràng thay vì dùng `get()` vô điều kiện trong những API tổng quát.

**Chọn reducing:** `reducing` hữu ích khi đã có phép kết hợp kết quả tuân theo hợp đồng kết hợp (*associativity*) và giá trị identity đúng. Với phép đếm/tổng/min/max/thống kê thông dụng, collector chuyên dụng thường dễ đọc hơn và giảm nguy cơ sai quy tắc kết hợp.

## 7. Lọc trước khi nhóm khác với tính điều kiện bên trong nhóm

Đây là điểm dễ dẫn tới **báo cáo thiếu nhóm**.

Giả sử có ba danh mục A, B, C. Trong đó **B có bản ghi nhưng không bản ghi nào được chấp nhận**. Có hai yêu cầu khác nhau:

- Chỉ quan tâm các nhóm **có bản ghi được chấp nhận** → lọc trước `groupingBy`.
- Cần báo cáo **mọi nhóm xuất hiện trong nguồn**, kể cả nhóm có 0 bản ghi được chấp nhận → vẫn nhóm toàn bộ, downstream cộng số lần điều kiện đúng.

Tệp **`GroupFilteringScopeDemo.java`** (Java 8):

```java
import java.util.*;
import java.util.stream.*;

public class GroupFilteringScopeDemo {
    static final class Entry {
        final String category;
        final boolean accepted;

        Entry(String category, boolean accepted) {
            this.category = category;
            this.accepted = accepted;
        }
    }

    public static void main(String[] args) {
        List<Entry> entries = Arrays.asList(
            new Entry("A", true),
            new Entry("A", false),
            new Entry("B", false),
            new Entry("C", true)
        );

        // Chỉ nhóm các phần tử đạt điều kiện.
        Map<String, Long> afterFilter = entries.stream()
            .filter(e -> e.accepted)
            .collect(Collectors.groupingBy(
                e -> e.category,
                TreeMap::new,
                Collectors.counting()));

        // Vẫn tạo nhóm cho mọi category có trong nguồn.
        Map<String, Long> perGroup = entries.stream()
            .collect(Collectors.groupingBy(
                e -> e.category,
                TreeMap::new,
                Collectors.summingLong(
                    e -> e.accepted ? 1L : 0L)));

        // Nếu chỉ phân thành hai nhóm true/false.
        Map<Boolean, Long> partition = entries.stream()
            .collect(Collectors.partitioningBy(
                e -> e.accepted,
                Collectors.counting()));

        System.out.println("afterFilter=" + afterFilter);
        System.out.println("perGroup=" + perGroup);
        System.out.println("accepted=" + partition.get(true)
            + ", rejected=" + partition.get(false));
    }
}
```

```bash
javac -encoding UTF-8 GroupFilteringScopeDemo.java
java GroupFilteringScopeDemo
```

```text
afterFilter={A=1, C=1}
perGroup={A=1, B=0, C=1}
accepted=2, rejected=2
```

**Vì sao khác nhau?**

- `filter(e -> e.accepted)` chạy **trước** khi collector thấy phần tử. Nhóm `B` không còn phần tử để khởi tạo, vì vậy **không có khóa B** trong `afterFilter`.
- `summingLong(e -> e.accepted ? 1L : 0L)` vẫn gửi **mọi bản ghi** vào nhóm theo `category`. Nhóm B được tạo, nhưng tất cả lần cộng đều bằng 0.
- `partitioningBy(predicate, downstream)` chuyên dùng khi có **hai phía của điều kiện Boolean**. Với `counting()`, trả về số lượng true và false, không tạo map theo category.

Nếu yêu cầu là “báo cáo toàn bộ danh mục được định nghĩa trong hệ thống, kể cả danh mục **chưa xuất hiện trong nguồn**”, ngay cả `perGroup` ở trên cũng chưa đủ: `groupingBy` không tự sinh khóa cho danh mục hoàn toàn vắng mặt. Cần đối chiếu kết quả với danh mục chuẩn và bổ sung giá trị mặc định **sau khi tổng hợp** hoặc thiết kế đầu vào khác đáp ứng hợp đồng.

**Chú ý phiên bản:** bài này chỉ dùng các API có từ Java 8. Nếu đọc ví dụ trên JDK mới hơn, không giả định một phương thức downstream xuất hiện sau Java 8 có thể biên dịch trực tiếp khi đặt `--release 8`.

## 8. groupingBy với downstream và partitioningBy khác nhau ở đâu?

`groupingBy(classifier, downstream)` phù hợp khi classifier trả về **nhiều giá trị khóa**: team, khu vực, trạng thái, loại giao dịch... `partitioningBy(predicate, downstream)` phù hợp khi chỉ muốn **true/false** theo một điều kiện.

| Thuộc tính | `groupingBy` | `partitioningBy` |
| --- | --- | --- |
| Khóa | Kiểu `K` do classifier tạo | `Boolean` |
| Nhóm có thể có | Một nhóm cho mỗi khóa gặp trong nguồn | Hai phân hoạch true/false |
| Khi nhóm không có phần tử | Khóa không xuất hiện trong Map kết quả | Cả hai khóa Boolean được cung cấp; downstream nhận phân hoạch rỗng nếu cần |
| Downstream | Có | Có |
| Ví dụ | `groupingBy(Sale::getRegion, counting())` | `partitioningBy(x -> x.accepted, counting())` |

Không dùng `partitioningBy` chỉ vì số nhóm lúc thử nghiệm bằng hai: hai khóa nghiệp vụ như `"North"`/`"South"` vẫn là khóa nhóm, có thể mở rộng thành nhiều giá trị. `partitioningBy` biểu đạt trực tiếp câu hỏi “đạt/không đạt điều kiện?”.

## 9. Map bên ngoài, thứ tự, nhóm rỗng và null

### 9.1. Không mặc định thứ tự kết quả

`Collectors.groupingBy(classifier, downstream)` không bảo đảm kiểu hay thứ tự duyệt của Map. Nếu cần khóa theo thứ tự từ điển, có thể dùng:

```java
// Trong ngữ cảnh Sale và sales của ví dụ 3.
Map<String, Long> result = sales.stream().collect(
    Collectors.groupingBy(Sale::getRegion,
        TreeMap::new, Collectors.counting()));
```

Nếu muốn giữ thứ tự **khóa xuất hiện lần đầu**, có thể dùng `LinkedHashMap::new` và một nguồn có thứ tự gặp (như List) khi chạy tuần tự. Đừng suy luận thứ tự từ biểu diễn `HashMap.toString()`. Nếu cần kết quả ổn định để xuất báo cáo, xác định thứ tự ở hợp đồng đầu ra thay vì phụ thuộc vào chi tiết implementation.

### 9.2. Khóa null không phải một nhóm được ngầm chấp nhận

Không để classifier trả `null` mà không có chính sách. Các collector `groupingBy` trong Java có thể từ chối khóa null và ném `NullPointerException`. Với dữ liệu ngoài, hãy **lọc bản ghi thiếu khóa** hoặc thay bằng một giá trị khóa hợp lệ, rõ ràng như `"UNKNOWN"` nếu nghiệp vụ cho phép:

```java
// Minh họa trong ngữ cảnh nguồn sales.
Map<String, Long> counts = sales.stream()
    .filter(s -> s.getRegion() != null)
    .collect(Collectors.groupingBy(
        Sale::getRegion, Collectors.counting()));
```

Lọc bỏ dữ liệu là quyết định nghiệp vụ: nếu cần thống kê lỗi hoặc báo người dùng, phải giữ lại thông tin đó thay vì âm thầm bỏ. Không đánh đồng một vùng thực sự có tên `"UNKNOWN"` với vùng thiếu khóa nếu hợp đồng không cho phép.

### 9.3. Nhóm không có bản ghi và nhóm có kết quả 0 là khác nhau

Với `Map<String, Long>`, `!map.containsKey("B")` và `map.get("B") == 0L` biểu thị hai sự kiện khác nhau: B chưa tạo nhóm trong kết quả hoặc B đã có nhóm với tổng bằng 0. Nếu API downstream cần phân biệt hai trạng thái, đừng dùng `getOrDefault("B", 0L)` rồi đánh mất thông tin về việc B có trong nguồn hay không.

### 9.4. Mỗi nhóm có collector tích lũy riêng

Một cách hiểu sai là downstream “tự chạy lại toàn bộ Stream cho mỗi nhóm”. Thực tế, một terminal `collect` phối hợp đưa từng phần tử vào bộ tích lũy của **khóa tương ứng**; khi cần chạy song song, framework còn có thể kết hợp trạng thái phần. Vì thế một lần `groupingBy(classifier, downstream)` có thể biểu đạt việc thu gọn mà không tạo các `List<T>` trung gian.

Không xem `Map<K, D>` do `collect` tạo ra là tự động bất biến, đồng bộ hoặc thread-safe. Chọn factory hoặc áp chính sách công khai kết quả phù hợp sau khi thu xong.

## 10. Độ chính xác thống kê, phân phối và hiệu năng

- **Kiểu số:** `counting()` cho `Long`; `summingInt()` cho `Integer` và có thể tràn nếu tổng vượt giới hạn số nguyên `int`. Nếu tổng có thể lớn, trích ra `long` và dùng `summingLong()`; với tiền tệ dùng kiểu số thập phân chính xác và quy tắc làm tròn đã định.
- **Trung bình:** `averagingInt()`/`summarizingInt()` cho kết quả trung bình dạng `double`; kiểm tra xem bài toán chấp nhận sai số làm tròn hay không. Đừng dùng trung bình của các trung bình nhóm để suy ra trung bình chung nếu kích thước các nhóm khác nhau.
- **Min/max:** `minBy`/`maxBy` dùng Comparator xác định rõ thứ tự; nếu có nhiều phần tử bằng nhau, đừng trông đợi tự động chọn bản ghi theo một quy tắc phụ chưa được định nghĩa.
- **Kích thước kết quả:** `groupingBy(..., counting())` chỉ giữ số đếm theo khóa, thường tiết kiệm bộ nhớ hơn `groupingBy(...)` giữ toàn bộ phần tử từng nhóm. Nhưng nếu số khóa phân biệt cực lớn, chính `Map` vẫn có thể lớn.
- **Parallel Stream:** `groupingBy` thông thường không phải một concurrent collector. Cơ chế kết hợp từng map có thể tốn chi phí khi chạy song song; `groupingByConcurrent` tồn tại trong Java 8 nhưng là collector đồng thời **không bảo đảm encounter order**. Chỉ cân nhắc khi yêu cầu thứ tự cho phép và đo đạc chứng minh hiệu năng.
- **Side effect:** classifier và mapper nên độc lập, không sửa danh sách/map ngoài, không phụ thuộc vào thứ tự gọi. Đặc biệt không ghi vào `ArrayList` chia sẻ trong `parallelStream().forEach(...)` để thay thế cho collector.
- **Nguồn dữ liệu:** phải xác định null, bản ghi thiếu khóa, bản ghi trùng, dữ liệu sai và tập khóa hợp lệ trước khi thực hiện thống kê. Collector không tự hiểu nghiệp vụ.

Nếu cần cập nhật liên tục một báo cáo thời gian thực, `collect` thường trả snapshot sau một lượt duyệt đầu vào. Nó **không** tự làm thành hệ thống stream processing giữ trạng thái cho dữ liệu vô hạn; hãy chọn công cụ/lifecycle lưu trạng thái phù hợp với yêu cầu nếu dữ liệu liên tục và không có điểm kết thúc.

## 11. Lỗi phổ biến trong downstream collector

| Lỗi | Vì sao dẫn đến kết quả sai | Hướng xử lý |
| --- | --- | --- |
| Dùng `groupingBy(key)` rồi lấy `list.size()` chỉ để đếm | Giữ tất cả phần tử trong bộ nhớ khi chỉ cần số đếm | `groupingBy(key, counting())` |
| Dùng `counting()` để tính tổng số lượng | Đếm bản ghi, không cộng số lượng | `summingInt/Long(quantityMapper)` |
| Dùng `mapping(..., toSet())` rồi mong giữ bản ghi trùng | Set loại trùng | Dùng `toList()` nếu phải giữ trùng |
| Dùng `toSet()` khi cần thứ tự hiển thị | Set trả về không có thứ tự được cam kết | `toCollection(LinkedHashSet::new)` nếu thứ tự chèn quan trọng |
| Lọc trước khi nhóm nhưng cần giữ nhóm có 0 bản ghi đạt | Nhóm không còn phần tử sẽ biến mất | Nhóm tất cả và cộng điều kiện hoặc bổ sung khóa sau |
| Mong `groupingBy` tạo khóa không có trong nguồn | Collector chỉ nhìn thấy các khóa classifier phát ra | Dùng danh mục chuẩn để bổ sung |
| Chỉ định `TreeMap` bên ngoài nhưng mong map cấp hai tự sắp | Map factory ngoài không điều khiển Map trong | Chỉ định mapFactory cho cả downstream grouping |
| Dùng `toMap(key, value)` với khóa có thể trùng | Có thể ném ngoại lệ do khóa trùng | Dùng `groupingBy` hoặc `toMap` với merge rõ ràng |
| Lấy `Optional.get()` từ `maxBy/minBy` không kiểm tra | Có thể gây `NoSuchElementException` khi Optional rỗng | Xử lý vắng mặt qua Optional API hoặc hợp đồng rõ |
| Giả định group key nhận null | Có thể ném `NullPointerException` | Làm sạch/đặt chính sách cho null trước khi nhóm |
| Gom doanh thu dạng `double` rồi yêu cầu chính xác đến đơn vị nhỏ | Sai số floating-point | Dùng biểu diễn số chính xác và làm tròn rõ |
| Đưa thao tác có side effect vào classifier/downstream mapper | Có thể phụ thuộc thứ tự và luồng thực thi | Dùng hàm thuần, thu kết quả rồi điều phối side effect |

## 12. Bài tập ứng dụng và tự kiểm tra

**Bài tập 1 — thống kê trạng thái đơn hàng.** Có `Order(status, amountInCents)`. Hãy tạo `Map<String, Long>` đếm đơn theo trạng thái; sau đó tạo `Map<String, Long>` tổng tiền (đơn vị cent) theo trạng thái. **Gợi ý:** cùng classifier `Order::getStatus`, thay downstream từ `counting()` sang `summingLong(Order::getAmountInCents)`. Lưu ý kiểm tra overflow theo giới hạn dữ liệu.

**Bài tập 2 — danh sách email theo đội.** Từ `Employee(team, email)`, thu `Map<String, Set<String>>` để tránh email trùng mà vẫn giữ thứ tự chèn trong mỗi đội. **Gợi ý:** `groupingBy(Employee::getTeam, mapping(Employee::getEmail, toCollection(LinkedHashSet::new)))`. Xác định xử lý email null và chuẩn hóa định dạng trước khi thu.

**Bài tập 3 — giữ nhóm có 0 bản ghi được duyệt.** Với các bản ghi `Entry(category, approved)`, cần xuất số bản ghi được duyệt cho mọi category xuất hiện. **Gợi ý:** `groupingBy(category, summingLong(e -> e.approved ? 1L : 0L))`; không lọc `approved` trước khi nhóm.

**Câu hỏi 1.** Trong `groupingBy(Employee::getTeam, counting())`, giá trị mỗi nhóm có kiểu gì?  
**Trả lời:** `Long`, không phải `List<Employee>`.

**Câu hỏi 2.** Khác biệt giữa `mapping(fn, toList())` và `mapping(fn, joining(", "))`?  
**Trả lời:** Cả hai biến đổi phần tử bằng `fn`; downstream sau đó tạo lần lượt `List<U>` hoặc `String`. `joining` yêu cầu dữ liệu là kiểu chuỗi phù hợp.

**Câu hỏi 3.** Trong ví dụ `afterFilter` và `perGroup`, vì sao khóa B chỉ xuất hiện ở `perGroup`?  
**Trả lời:** Lọc trước nhóm loại mọi bản ghi B; còn phép cộng điều kiện vẫn nhóm B nhưng nhận tổng 0.

**Câu hỏi 4.** Vì sao `groupingBy(team, TreeMap::new, groupingBy(role, counting()))` chưa bảo đảm khóa vai trò bên trong được sắp xếp?  
**Trả lời:** `TreeMap::new` chỉ được dùng cho Map theo team; downstream `groupingBy(role, counting())` dùng mapFactory mặc định, không cam kết thứ tự. Cần chỉ định `TreeMap::new` cho cả downstream nếu cần.

**Câu hỏi 5.** Vì sao `summarizingInt` có ích khi một nhóm cần count, sum, min, max và average?  
**Trả lời:** Một downstream collector tạo ra `IntSummaryStatistics` cho mỗi nhóm, tránh nhiều pipeline riêng biệt chỉ để tính các chỉ số liên quan.

## Tài liệu Java chính thức

- [Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): `groupingBy` với downstream/mapFactory; `mapping`, `counting`, `summingInt`, `summarizingInt`, `collectingAndThen`, `partitioningBy`.
- [Java SE 8 — Collector](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.html): supplier, accumulator, combiner, finisher và đặc tính collector.
- [Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): terminal `collect` và các thao tác trung gian.
- [Java SE 8 — IntSummaryStatistics](https://docs.oracle.com/javase/8/docs/api/java/util/IntSummaryStatistics.html): đọc count, sum, min, max, average.

**Ghi nhớ:** `groupingBy` quyết định **phần tử thuộc nhóm nào**; downstream collector quyết định **mỗi nhóm có kết quả gì**. Thay `toList()` bằng `counting()`, `summingLong()`, `mapping()`, `summarizingInt()` hoặc một `groupingBy` khác là cách diễn đạt trực tiếp báo cáo cần tạo, giảm code xử lý trung gian và làm rõ hợp đồng dữ liệu.