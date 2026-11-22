# Supplier, accumulator, combiner và finisher trong custom Collector

## 1. Vì sao cần hiểu bốn thành phần này?

Khi làm việc với Java Stream, một phép **mutable reduction** nhận nhiều phần tử đầu vào, tích lũy chúng vào một hoặc nhiều vùng chứa trung gian và trả về kết quả cuối. Ví dụ: tạo danh sách, gộp chuỗi, thống kê đơn hàng, tổng hợp một báo cáo hoặc tạo cấu trúc dữ liệu riêng cho nghiệp vụ.

`Collector<T, A, R>` trong `java.util.stream` đóng gói quy trình này bằng bốn chức năng chính:

1. **Supplier** — tạo vùng chứa tích lũy mới.
2. **Accumulator** — thêm một phần tử đầu vào vào vùng chứa.
3. **Combiner** — kết hợp hai vùng chứa kết quả trung gian.
4. **Finisher** — chuyển vùng chứa đã tích lũy thành kết quả cuối.

Một collector tùy biến dùng lại được có thể tạo bằng `Collector.of(...)`. Đây là API chuẩn có từ Java 8 và vẫn được hỗ trợ trong Java hiện đại. Điều quan trọng nhất là hiểu **từng chức năng, vòng đời, kiểu dữ liệu và hợp đồng kết hợp**; chỉ biết cách truyền bốn lambda là chưa đủ để viết collector đúng khi stream chạy song song.

Ví dụ nghiệp vụ: một danh sách `List<Integer>` có `[1, 2, 3, 4]`. Ta muốn trả về một `Report` có `count=4`, `sum=10` và `average=2.5`. Thay vì tạo một `Report` rồi cho mọi luồng cùng sửa, ta sẽ để supplier tạo các vùng chứa, accumulator thêm dữ liệu, combiner gộp kết quả từng phần, cuối cùng finisher tạo báo cáo.

## 2. Collector<T, A, R> và kiểu của từng thành phần

Chữ ký tổng quát:

```java
Collector<T, A, R>
```

Ba tham số kiểu có vai trò khác nhau:

| Ký hiệu | Ý nghĩa | Ví dụ collector thống kê |
| --- | --- | --- |
| `T` | Kiểu **mỗi phần tử đầu vào** của Stream | `Integer` |
| `A` | Kiểu **vùng chứa tích lũy trung gian** | `StatsBox` có `count` và `sum` |
| `R` | Kiểu **kết quả cuối** của `collect` | `Report` bất biến |

Bốn hàm tương ứng:

| Thành phần | Kiểu hàm | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| Supplier | `Supplier<A>` | Không có tham số | Tạo **A mới** |
| Accumulator | `BiConsumer<A, T>` | Container `A` và phần tử `T` | Thường sửa `A` tại chỗ; trả `void` |
| Combiner | `BinaryOperator<A>` | Hai container trung gian `A` | Trả về một `A` đã gộp |
| Finisher | `Function<A, R>` | Container `A` đã gộp | Trả kết quả cuối `R` |

**Phân biệt quan trọng:** accumulator của **Collector** là `BiConsumer<A,T>`, nên thường đổi trạng thái vùng chứa và trả `void`. Accumulator của một số overload `Stream.reduce(...)` là một hàm **trả giá trị rút gọn mới**. Không nên nhầm hai kiểu hợp đồng khi tự viết code.

Hai factory method của `Collector.of`:

```java
// Dạng 1: A và R cùng kiểu; finisher là identity.
static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
);

// Dạng 2: A và R có thể khác kiểu; tự chỉ định finisher.
static <T, A, R> Collector<T, A, R> of(
    Supplier<A> supplier,
    BiConsumer<A, T> accumulator,
    BinaryOperator<A> combiner,
    Function<A, R> finisher,
    Collector.Characteristics... characteristics
);
```

Đây là **chữ ký API minh họa**, không phải hai method độc lập để dán vào một file Java và chạy ngay. Tham số cuối là varargs, nên ở các ví dụ tiếp theo ta có thể gọi `Collector.of` mà không truyền thêm characteristics.

## 3. Vòng đời: các bước chạy theo cách nào?

### 3.1. Với stream tuần tự

Có thể hình dung phép thu thập tuần tự như sau:

```text
Supplier.get()
    |
    v
container A ban đầu
    |
    +-- Accumulator.accept(A, T1)
    +-- Accumulator.accept(A, T2)
    +-- Accumulator.accept(A, T3)
    |
    v
Finisher.apply(A) --> kết quả R
```

Khi nguồn là stream tuần tự đơn giản, runtime thường chỉ cần một vùng chứa và gọi accumulator cho từng phần tử. **Không nên viết code dựa vào giả định Java bắt buộc gọi supplier hay combiner một số lần cố định**. API mô tả kết quả và các ràng buộc cần giữ, còn runtime có thể tối ưu.

### 3.2. Với stream song song

Runtime có thể chia dữ liệu thành nhiều phần:

```text
               Stream<T>
                  |
          +-------+-------+
          |               |
     partition 1     partition 2
          |               |
  Supplier -> A1   Supplier -> A2
          |               |
  accumulator()    accumulator()
          |               |
          +-------+-------+
                  |
        combiner(A1, A2) -> A
                  |
           finisher(A) -> R
```

Sơ đồ mô tả **một khả năng phân chia**, không khẳng định chỉ có hai nhánh hoặc mỗi thread tương ứng một container. Trong thực tế có thể có nhiều container, nhiều cấp combiner; khi không cần gộp (chẳng hạn trong một lượt xử lý tuần tự), combiner có thể không được gọi.

**Collector đúng phải cho kết quả tương đương dù dữ liệu được chia và kết hợp khác nhau.** Đó là lý do supplier, accumulator và combiner phải tuân thủ các ràng buộc về identity và associativity; không được gắn nghiệp vụ với số lần runtime gọi từng hàm.

## 4. Supplier — tạo vùng chứa tích lũy độc lập

`supplier()` là một `Supplier<A>`, thường viết dưới dạng constructor reference:

```java
ArrayList::new
StringBuilder::new
HashMap::new
```

Hoặc lambda tạo kiểu vùng chứa riêng:

```java
() -> new long[2]  // long[0] = count, long[1] = sum
```

Supplier có thể được gọi nhiều lần khi collect chạy song song. **Mỗi lần gọi phải cấp một vùng chứa mới phù hợp với phép thu thập**, nhất là khi accumulator thay đổi vùng chứa tại chỗ. Một supplier trả về cùng một collection từ biến bên ngoài sẽ khiến các nhánh có thể dùng chung trạng thái và phá ý nghĩa của phép thu thập.

Ví dụ **không đúng**:

```java
// Đoạn minh họa sai; không dùng làm collector thật.
List<String> shared = new ArrayList<>();
Supplier<List<String>> badSupplier = () -> shared;
```

Ví dụ **đúng**:

```java
// Đoạn minh họa; mỗi lời gọi trả danh sách mới.
Supplier<List<String>> goodSupplier = ArrayList::new;
```

Các đoạn minh họa này cần các import `java.util.*` và `java.util.function.*` nếu đặt trong chương trình độc lập. Supplier không nhất thiết tạo `List`: nó có thể tạo `StringBuilder`, `Map`, một lớp thống kê nội bộ hoặc kiểu container khác, miễn cấu trúc đó phục vụ quy trình tích lũy và gộp.

## 5. Accumulator — thêm một phần tử vào vùng chứa

Kiểu của accumulator:

```java
BiConsumer<A, T>
```

Nó nhận `A` và `T`, thay đổi dữ liệu trung gian rồi kết thúc mà không trả kết quả. Ví dụ:

```java
// Mã minh họa, T = String và A = List<String>
(list, value) -> list.add(value)

// Mã minh họa, T = String và A = StringBuilder
(builder, value) -> builder.append(value)
```

Để thống kê:

```java
// Mã minh họa, StatsBox có hai trường long count và sum.
(box, number) -> {
    box.count++;
    box.sum += number;
}
```

Các mẫu này **được phép thay đổi container nội bộ** của collector: mutable reduction được thiết kế để hoạt động như vậy. Nhưng accumulator không nên sửa nguồn Stream, biến kết quả chia sẻ bên ngoài, hoặc dựa vào state thay đổi ngẫu nhiên của những lần gọi khác.

Với collector thông thường không được khai báo `CONCURRENT`, runtime quản lý việc tích lũy sao cho mỗi container thích hợp không bị nhiều luồng cập nhật đồng thời; không vì thế mà `ArrayList` hay `StringBuilder` tự biến thành kiểu thread-safe. Không được tự mang container đó ra bên ngoài và cho nhiều thread sửa khi chưa có đồng bộ phù hợp.

## 6. Combiner — ghép hai kết quả trung gian

Kiểu:

```java
BinaryOperator<A>
```

Combiner nhận hai container cùng kiểu `A`, trả về một `A` đại diện cho kết quả đã gộp. Nó **có thể** sửa một container rồi trả về container đó, hoặc tạo container mới. Ví dụ gộp danh sách:

```java
// Mã minh họa; A = List<String>.
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Ví dụ gộp thống kê:

```java
// Mã minh họa; A = StatsBox.
(left, right) -> {
    left.count += right.count;
    left.sum += right.sum;
    return left;
}
```

Nếu `left` có `count=2, sum=30` và `right` có `count=3, sum=70`, kết quả gộp phải biểu diễn `count=5, sum=100`. Dù runtime kết hợp theo nhiều cấp khác nhau, tổng hợp vẫn đúng.

**Combiner không phải hàm chỉ dùng để cho đủ tham số.** Nó quyết định collector có hoạt động đúng với parallel stream không. Viết combiner như `(left, right) -> left` sẽ âm thầm **vứt bỏ** dữ liệu của nhánh `right`. Mã có thể vẫn trông đúng khi chạy tuần tự nếu combiner chưa từng được gọi, nhưng sai trong môi trường song song.

Ngoài ra, combiner của `Collector.of(...)` là `BinaryOperator<A>`, **phải trả về `A`**. Trong overload ba tham số của `Stream.collect(supplier, accumulator, combiner)`, tham số combiner lại là `BiConsumer<R,R>` và **trả `void`**. Hai API cùng khái niệm gộp kết quả nhưng khác kiểu hàm.

## 7. Finisher — tạo kết quả cuối, có thể khác kiểu A

`finisher()` có kiểu `Function<A,R>`. Nó được dùng sau khi có kết quả tích lũy để chuyển `A` sang `R`. Ví dụ:

- `StringBuilder -> String` bằng `StringBuilder::toString`.
- `StatsBox -> Report` bằng một hàm tạo báo cáo.
- `ArrayList<String> -> List<String>` không thể chỉnh sửa bằng một phép sao chép và bao gói phù hợp.

Lý do tách `A` và `R`: kiểu mutable thường tiện cho việc tích lũy, trong khi kiểu immutable/read-only lại an toàn, rõ ý nghĩa hơn cho kết quả nghiệp vụ.

Khi không cần bước biến đổi và muốn trả chính container tích lũy, dùng overload `Collector.of(supplier, accumulator, combiner)`: `A` và `R` là cùng kiểu; collector được tạo có đặc tính `IDENTITY_FINISH`.

Khi thật sự chuyển kiểu (`StatsBox` thành `Report`, `StringBuilder` thành `String`), dùng overload có finisher. **Không đánh dấu `IDENTITY_FINISH` cho collector có finisher chuyển kiểu**, bởi đặc tính đó cho phép runtime bỏ qua bước finisher và giả định có thể cast `A` thành `R`.

### Finisher và số lần gọi

Trong thu thập thông thường, finisher tạo kết quả sau bước tích lũy/gộp. Khi collector được sử dụng **lồng bên trong** `groupingBy`, phép biến đổi cuối có thể được áp dụng cho từng nhóm. Khi collector có `IDENTITY_FINISH`, runtime có thể bỏ qua việc gọi finisher. Vì vậy không nên xem finisher là nơi duy nhất có thể gây side effect toàn cục với giả định “chắc chắn chạy đúng một lần”.

## 8. Ví dụ 1 — Collector.of với ba thành phần và IDENTITY_FINISH

Ví dụ này tạo một `List<String>` theo thứ tự dữ liệu đầu vào, kể cả khi stream chạy song song. Tạo file **IdentityCollectorDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collector;

public class IdentityCollectorDemo {
    public static void main(String[] args) {
        Collector<String, List<String>, List<String>> collector =
            Collector.of(
                ArrayList::new,                 // supplier
                List::add,                      // accumulator
                (left, right) -> {              // combiner
                    left.addAll(right);
                    return left;
                }
            );

        List<String> steps = Arrays.asList("read", "check", "write")
            .parallelStream()
            .collect(collector);

        System.out.println("steps=" + steps);
        System.out.println("identityFinish=" +
            collector.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH));
    }
}
```

Chạy bằng JDK 17 trở lên; các API trong ví dụ đã có từ Java 8:

```bash
javac IdentityCollectorDemo.java
java IdentityCollectorDemo
```

Đầu ra:

```text
steps=[read, check, write]
identityFinish=true
```

**Tại sao đúng?**

1. `ArrayList::new` tạo mỗi container mới khi supplier được gọi.
2. `List::add` đưa từng phần tử vào container mà runtime cung cấp.
3. Combiner `addAll` ghép hai danh sách, rồi trả `left`. Đối với stream có encounter order, collector không khai báo `UNORDERED` nên nó phải duy trì kết quả có thứ tự tương đương với việc duyệt nguồn.
4. Không truyền finisher; kết quả cuối chính là vùng chứa `List<String>`. `IDENTITY_FINISH` được thiết lập tự động theo overload ba thành phần.

Ví dụ này có giá trị học tập, nhưng **trong mã sản xuất** nên cân nhắc dùng `collect(Collectors.toCollection(ArrayList::new))`: ý định rõ ràng hơn và tránh tự viết lại collector chuẩn. Muốn trả một `List` không chỉnh sửa được trong Java hiện đại, có thể dùng `stream.toList()` (Java 16+) nếu hành vi và yêu cầu tương thích cho phép.

## 9. Ví dụ 2 — bốn thành phần: từ StatsBox sang Report

Giả sử cần tổng hợp số lượng phần tử và tổng giá trị, rồi trả một báo cáo **không thể chỉnh sửa** với ba trường `count`, `sum`, `average`. Ta dùng `StatsBox` mutable làm `A` và `Report` làm `R`.

Tạo file **ReportCollectorDemo.java**:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.stream.Collector;

public class ReportCollectorDemo {
    // Container trung gian: chỉ dùng trong quá trình collect.
    static class StatsBox {
        long count;
        long sum;
    }

    // Kết quả cuối: các trường đều final.
    static final class Report {
        private final long count;
        private final long sum;
        private final double average;

        Report(long count, long sum) {
            this.count = count;
            this.sum = sum;
            this.average = count == 0 ? 0.0 : (double) sum / count;
        }

        @Override
        public String toString() {
            return "Report{count=" + count +
                   ", sum=" + sum +
                   ", average=" + average + "}";
        }
    }

    public static void main(String[] args) {
        Collector<Integer, StatsBox, Report> summary =
            Collector.of(
                StatsBox::new,                    // supplier
                (box, n) -> {                    // accumulator
                    box.count++;
                    box.sum += n;
                },
                (left, right) -> {               // combiner
                    left.count += right.count;
                    left.sum += right.sum;
                    return left;
                },
                box -> new Report(box.count, box.sum)  // finisher
            );

        Report report = Arrays.asList(1, 2, 3, 4)
            .parallelStream()
            .collect(summary);

        Report emptyReport = Collections.<Integer>emptyList()
            .stream()
            .collect(summary);

        System.out.println("summary=" + report);
        System.out.println("empty=" + emptyReport);
        System.out.println("identityFinish=" +
            summary.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH));
    }
}
```

```bash
javac ReportCollectorDemo.java
java ReportCollectorDemo
```

Đầu ra xác định:

```text
summary=Report{count=4, sum=10, average=2.5}
empty=Report{count=0, sum=0, average=0.0}
identityFinish=false
```

**Phân tích đúng theo bốn thành phần:**

- **Supplier:** mỗi lời gọi `StatsBox::new` cung cấp một hộp có `count=0`, `sum=0`.
- **Accumulator:** mỗi số nguyên được đếm một lần và cộng vào `sum`.
- **Combiner:** hai hộp được gộp bằng phép cộng `count` và `sum`. Phép cộng số nguyên `long` có tính kết hợp theo ngữ nghĩa modulo của Java; với đầu vào của ví dụ không có tràn.
- **Finisher:** chuyển container sang `Report`, lấy trung bình `sum/count` và xử lý trường hợp rỗng để tránh chia cho 0.

Vì `StatsBox` và `Report` là **hai kiểu khác nhau**, collector này **không** mang `IDENTITY_FINISH`. Người dùng của collector chỉ nhận `Report` và không cần biết về lớp tích lũy mutable `StatsBox`.

Trường hợp rỗng cho `Report{count=0, sum=0, average=0.0}` là **quy ước được ví dụ lựa chọn**, không phải quy tắc chung cho mọi báo cáo. Trong nghiệp vụ thật, có thể định nghĩa trung bình chưa có dữ liệu bằng `OptionalDouble` hoặc kiểu biểu diễn khác.

## 10. Ví dụ 3 — StringBuilder là A, String là R

Với phép nối chuỗi, `StringBuilder` thích hợp làm container mutable vì thêm chuỗi không phải liên tục tạo các `String` trung gian. `String` lại thích hợp làm kết quả cuối.

Tạo file **JoinCollectorDemo.java**:

```java
import java.util.Arrays;
import java.util.stream.Collector;

public class JoinCollectorDemo {
    public static void main(String[] args) {
        Collector<String, StringBuilder, String> join =
            Collector.of(
                StringBuilder::new,
                (builder, text) -> builder.append(text),
                (left, right) -> left.append(right),
                StringBuilder::toString
            );

        String result = Arrays.asList("Java ", "Stream ", "Collector")
            .parallelStream()
            .collect(join);

        System.out.println("joined=" + result);
    }
}
```

```bash
javac JoinCollectorDemo.java
java JoinCollectorDemo
```

Đầu ra:

```text
joined=Java Stream Collector
```

`StringBuilder` **không thread-safe**, nhưng ở đây supplier tạo các vùng chứa riêng và collector không khai báo `CONCURRENT`. Runtime tổ chức việc gộp kết quả trung gian theo hợp đồng Collector. Chỉ cần **một String cuối** chứ không cần trả StringBuilder có thể thay đổi được.

Ví dụ này cho thấy rõ công việc của finisher, nhưng khi chỉ muốn nối chuỗi, collector chuẩn `Collectors.joining()` hoặc `Collectors.joining(delimiter)` thường là lựa chọn dễ bảo trì hơn. Chỉ tự viết `Collector.of` nếu có logic nghiệp vụ đặc thù mà các collector dựng sẵn hoặc cách kết hợp chúng không diễn đạt rõ.

## 11. Ví dụ 4 — dùng custom collector làm downstream của groupingBy

Một custom collector có thể dùng lại cho toàn Stream hoặc dùng làm **downstream collector** để tính kết quả trong từng nhóm. Ví dụ: mỗi nhóm nhân viên cần trả chuỗi `count=..., points=...`.

Ở ví dụ này, `A` là `long[2]`, với `[0]` chứa count và `[1]` chứa tổng điểm. `R` là `String`. Tạo file **GroupingCollectorDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class GroupingCollectorDemo {
    static final class Employee {
        private final String team;
        private final int points;

        Employee(String team, int points) {
            this.team = team;
            this.points = points;
        }

        String getTeam() {
            return team;
        }

        int getPoints() {
            return points;
        }
    }

    public static void main(String[] args) {
        List<Employee> employees = Arrays.asList(
            new Employee("API", 20),
            new Employee("UI", 30),
            new Employee("API", 30)
        );

        Collector<Employee, long[], String> perTeam =
            Collector.of(
                () -> new long[2],              // supplier
                (box, employee) -> {           // accumulator
                    box[0]++;
                    box[1] += employee.getPoints();
                },
                (left, right) -> {              // combiner
                    left[0] += right[0];
                    left[1] += right[1];
                    return left;
                },
                box -> "count=" + box[0] +     // finisher
                       ", points=" + box[1]
            );

        Map<String, String> result = employees.parallelStream()
            .collect(Collectors.groupingBy(
                Employee::getTeam,
                TreeMap::new,
                perTeam
            ));

        System.out.println(result);
    }
}
```

```bash
javac GroupingCollectorDemo.java
java GroupingCollectorDemo
```

Đầu ra:

```text
{API=count=2, points=50, UI=count=1, points=30}
```

**Tại sao ví dụ này quan trọng?** `groupingBy` quản lý nhiều container của downstream collector, tách biệt theo từng nhóm. Kết quả cuối là `Map<String,String>`; mỗi giá trị `String` đã qua finisher của collector được định nghĩa. `TreeMap::new` được dùng để đầu ra theo thứ tự khóa ổn định, không dựa vào thứ tự không được bảo đảm của một `HashMap`.

Với bài toán thực, cũng có thể dùng các collector chuẩn để đếm và cộng, hoặc thiết kế một lớp báo cáo có kiểu dữ liệu rõ ràng thay vì chuỗi. Mục đích ở đây là chứng minh **cùng bốn thành phần vẫn hoạt động khi collector được lồng**.

## 12. Hợp đồng bắt buộc: identity, associativity và equivalence

Custom collector đúng cần hoạt động **tương đương** khi Stream chia dữ liệu thành nhiều nhánh và gộp với nhiều cách nhóm khác nhau. Javadoc của `Collector` xác định các yêu cầu quan trọng.

### 12.1. Identity: gộp với container rỗng không làm đổi ý nghĩa

Nếu `a` là một container đã tích lũy và `empty = supplier.get()` là container mới rỗng, thì:

```text
combiner(a, empty) phải tương đương a
```

Trong ví dụ thống kê, container rỗng có `count=0`, `sum=0`. Gộp với nó giữ nguyên dữ liệu của `a`, nên identity hợp lệ.

Nếu supplier tạo container mặc định `count=1` hoặc `sum=100` mà không có lý do đại số, việc gộp có thể thêm dữ liệu giả. Không được xem supplier như “khởi tạo một bản ghi mẫu” mang dữ liệu nghiệp vụ rồi chờ combiner tự sửa.

### 12.2. Associativity: chia/gộp theo nhiều cách vẫn tương đương

Ví dụ đầu vào `[1, 2, 3]`:

```text
Cách A:
  accumulator(1), accumulator(2), accumulator(3)
  -> count=3, sum=6

Cách B:
  A1 nhận [1]          -> count=1, sum=1
  A2 nhận [2, 3]       -> count=2, sum=5
  combiner(A1, A2)     -> count=3, sum=6
```

Hai cách phải cho **kết quả cuối tương đương** sau finisher. Một phép combiner lấy `max` cho `sum` hoặc xóa một container sẽ phá kết quả, dù ví dụ tuần tự có vẻ đúng.

Đối với collector có giữ thứ tự (không khai báo `UNORDERED`), kết quả phải tôn trọng encounter order của nguồn khi thứ tự đó là một phần ý nghĩa. Chẳng hạn collector nối chuỗi có thể cần phân biệt `"AB"` và `"BA"`; tuy phép cộng chuỗi có tính kết hợp, nó **không giao hoán**, nên combiner phải nối đúng hai đoạn được gộp theo thứ tự được yêu cầu.

### 12.3. Equivalence không nhất thiết nghĩa là cùng tham chiếu

Collector có thể tạo những container `A` khác nhau, miễn kết quả sau finisher là **tương đương** theo hợp đồng. Đối với collector có thứ tự, Javadoc dùng sự bằng nhau giữa các kết quả đã qua finisher như tiêu chuẩn tương đương. Với collector khai báo `UNORDERED`, so sánh có thể bỏ qua khác biệt thứ tự nếu đúng ngữ nghĩa của kết quả đó.

Không nên kiểm tra collector bằng cách yêu cầu reference equality (`a == b`) giữa hai cách chạy. Kiểm tra **giá trị và cấu trúc kết quả cuối**.

## 13. Characteristics: metadata để runtime chọn cách thực hiện

Ngoài bốn hàm, `Collector` còn cung cấp `characteristics()`. Có ba thuộc tính chuẩn:

| Characteristic | Nghĩa chính | Khi nào được khai báo |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher là identity; runtime có thể bỏ qua và xem `A` là `R`. | Khi kết quả cuối đúng là container và việc cast từ `A` sang `R` hợp lệ; overload `Collector.of` ba hàm tự thêm. |
| `UNORDERED` | Collector không cam kết giữ encounter order ở kết quả. | Khi đổi thứ tự đầu vào không ảnh hưởng ý nghĩa kết quả, ví dụ một số bài toán tập hợp hoặc phép tổng độc lập thứ tự. |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên **cùng một** container kết quả. | Chỉ khi container và accumulator thực sự hỗ trợ cập nhật đồng thời đúng đắn. |

**Không tự thêm characteristic để “tăng tốc” nếu không thỏa hợp đồng.**

- Nếu `A = StringBuilder` và `R = String`, **không** khai báo `IDENTITY_FINISH`: cast từ `StringBuilder` thành `String` là không hợp lệ, finisher cần chạy.
- Nếu collector dùng `ArrayList::add` mà không bảo vệ cập nhật đồng thời, **không** khai báo `CONCURRENT`.
- Nếu collector nối chuỗi theo thứ tự với kết quả `"Java Stream Collector"`, **không** khai báo `UNORDERED`; thứ tự là một phần ý nghĩa.
- `CONCURRENT` không có nghĩa cứ dùng `parallelStream()` là chắc chắn có nhiều thread cập nhật cùng container. Một collector concurrent nhưng vẫn đòi hỏi encounter order chỉ được đánh giá theo cách concurrent khi nguồn không có thứ tự theo điều kiện của Stream. Runtime còn có quyền chọn chiến lược thích hợp.

**Không khai báo `CONCURRENT` vẫn có thể hỗ trợ parallel stream.** Nó chỉ có nghĩa runtime dùng các container trung gian theo hợp đồng collector, rồi gộp bằng combiner, thay vì cho nhiều thread mặc nhiên sửa chung một container.

## 14. Phân biệt hai cách viết collect và các lựa chọn dựng sẵn

### 14.1. Collector.of và Stream.collect ba tham số

Hai API có thể nhìn gần giống nhau:

```java
// Mã minh họa dùng trong hàm có biến Stream<String> stream.
stream.collect(
    ArrayList::new,
    ArrayList::add,
    ArrayList::addAll
);
```

Đây là overload **`Stream.collect(Supplier<R>, BiConsumer<R,T>, BiConsumer<R,R>)`**. Combiner là `BiConsumer`, nên `ArrayList::addAll` có thể dùng ở đây mà không cần trả container.

Ngược lại:

```java
// Mã minh họa về Collector.of.
Collector<String, List<String>, List<String>> collector =
    Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Ở `Collector.of`, combiner là `BinaryOperator<A>`, nên phải **return left** hoặc trả một container gộp khác. Sự khác biệt về kiểu tham số này thường gây lỗi biên dịch khi chuyển mã từ API này sang API kia.

Ngoài ra, một `Collector` là một đối tượng mô tả chiến lược thu thập nên có thể **tái sử dụng** trên nhiều stream mới hoặc truyền làm downstream collector. Bản thân các container trung gian do supplier tạo vẫn phải mới và được quản lý theo từng lần thu thập.

### 14.2. Ưu tiên ghép collector có sẵn khi đủ ý nghĩa

Rất nhiều nhu cầu không cần viết custom collector:

- Tạo danh sách: `Collectors.toList()` hoặc `Collectors.toCollection(ArrayList::new)` nếu cần chính xác `ArrayList`.
- Nối chuỗi: `Collectors.joining(", ")`.
- Thống kê: `Collectors.summarizingInt(...)`, `summarizingLong(...)`, `summarizingDouble(...)`.
- Nhóm: `Collectors.groupingBy(...)`.
- Biến đổi kết quả cuối của một collector có sẵn: `Collectors.collectingAndThen(downstream, finisher)`.

Ví dụ về biến đổi kết quả cuối có thể viết:

```java
// Đoạn minh họa Java 17+: nhận List không thể chỉnh sửa.
List<String> result = values.stream().collect(
    Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    )
);
```

`values` là `List<String>` đã được khai báo trong chương trình. `List.copyOf` trả danh sách không chỉnh sửa được và **không chấp nhận phần tử null**. Nếu dùng Java 8 và muốn tạo một kết quả chỉ đọc, có thể bọc một bản sao bằng `Collections.unmodifiableList(new ArrayList<>(list))`. Khi đã có `collectingAndThen` hoặc collector chuẩn diễn đạt được ý định, không cần tự triển khai bốn hàm.

## 15. Những lỗi thường gặp khi tự viết collector

### Lỗi 1 — supplier trả cùng một object

`() -> sharedList` trả một container dùng chung. Khi parallel, các nhánh có thể sửa cùng một object. Đổi thành `ArrayList::new` hoặc supplier cấp container độc lập.

### Lỗi 2 — combiner bỏ dữ liệu của nhánh phải

`(left, right) -> left` khiến kết quả từ `right` bị mất. Với danh sách, cần thực sự gộp: `left.addAll(right); return left;`. Với tổng/count, phải cộng các trường của hai kết quả trung gian.

### Lỗi 3 — coi combiner là optional vì chạy sequential không gọi

Ngay cả khi các lần kiểm thử tuần tự đều thành công, collector vẫn phải định nghĩa combiner đúng để không hỏng khi được dùng với `parallelStream()` hoặc một cách chia việc khác. Không dựa vào log chỉ để đếm số lần combiner chạy.

### Lỗi 4 — dùng finisher chuyển kiểu nhưng khai báo IDENTITY_FINISH

Nếu `A` là `StringBuilder` và `R` là `String`, finisher `toString` không phải identity. Gắn sai characteristic có thể khiến runtime bỏ qua finisher và thực hiện cast không hợp lệ, dẫn tới kết quả sai hoặc lỗi runtime.

### Lỗi 5 — thêm CONCURRENT cho container không thread-safe

`ArrayList`, `StringBuilder` hoặc mảng thường không an toàn khi nhiều thread sửa cùng lúc. Không thêm `CONCURRENT` nếu accumulator không đáp ứng cập nhật đồng thời trên **cùng một vùng chứa**.

### Lỗi 6 — đánh dấu UNORDERED khi kết quả cần encounter order

Collector tạo chuỗi, danh sách theo thứ tự hoặc dữ liệu có thứ tự nghiệp vụ cần bảo toàn encounter order của nguồn. `UNORDERED` không làm kết quả “ngẫu nhiên” theo định nghĩa, nhưng bỏ yêu cầu bảo toàn thứ tự.

### Lỗi 7 — accumulator hoặc finisher dùng side effect bên ngoài

Không phụ thuộc vào biến đếm toàn cục, trạng thái mutable chia sẻ, ghi log để suy ra lịch thực thi hoặc giả định finisher luôn chỉ chạy một lần. Các hàm phải tuân thủ hợp đồng **stateless** và **non-interfering**; accumulator thay đổi đúng container do runtime cấp là hợp lệ.

### Lỗi 8 — dùng container có dữ liệu khởi tạo không trung hòa

Supplier tạo `count=1` hoặc chứa sẵn một bản ghi không thuộc input có thể làm gộp nhiều nhánh cho ra số liệu bị cộng lặp. Supplier phải tạo container đóng vai trò phần tử trung hòa của phép kết hợp.

### Lỗi 9 — giả định số lần supplier/combiner hay thread là cố định

`parallelStream()` không cam kết bao nhiêu partition, mỗi thread có đúng một container hay combiner chạy bao nhiêu lần. Những chi tiết này không phải một phần của contract nghiệp vụ.

### Lỗi 10 — kiểm tra chỉ bằng một lần chạy tuần tự

Collector có thể đúng ở input nhỏ tuần tự nhưng sai ở input lớn hoặc parallel. Hãy so sánh kết quả theo **giá trị** giữa `stream()` và `parallelStream()` với nhiều trường hợp, đặc biệt dữ liệu rỗng, một phần tử, nhiều phần tử và nhiều cách chia nhóm.

### Lỗi 11 — bỏ qua giới hạn số và tính chất phép gộp

Ví dụ cộng `long` có thể tràn; phép tính `double` có thể sai khác nhỏ theo cách kết hợp do tính gần đúng của số chấm động. Nếu nghiệp vụ yêu cầu chính xác tuyệt đối, hãy định nghĩa kiểu số, độ chính xác và phép kết hợp thích hợp trước khi viết collector.

## 16. Cách tự kiểm thử một custom collector

Một checklist có thể dùng khi review code:

1. **Tạo container:** supplier có tạo vùng chứa mới, rỗng và đúng kiểu `A` mỗi lần gọi không?
2. **Thêm phần tử:** accumulator có đưa từng `T` vào đúng container mà không sửa nguồn/biến chia sẻ không?
3. **Gộp:** combiner có bảo toàn toàn bộ dữ liệu của hai nhánh và trả một `A` hợp lệ không?
4. **Kết thúc:** finisher có chuyển từ `A` sang `R` đúng kiểu, xử lý input rỗng và tránh rò container mutable ngoài ý muốn không?
5. **Đại số:** gộp với container rỗng có tương đương không đổi? Chia input thành các nhóm khác nhau có cho kết quả tương đương không?
6. **Đặc tính:** `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT` có phản ánh đúng hành vi thực tế không?
7. **Biên:** thử input rỗng, một phần tử, nhiều phần tử, dữ liệu trùng, dữ liệu lớn, giá trị biên và `null` nếu mô hình cho phép.
8. **Parallel:** so sánh kết quả tuần tự/song song; với collector nhạy thứ tự, xác nhận encounter order được bảo toàn khi nguồn có thứ tự.

Ví dụ kiểm tra đối với collector `summary` ở phần trên:

```java
// Đoạn minh họa trong ngữ cảnh đã có summary và input.
Report sequential = input.stream().collect(summary);
Report parallel = input.parallelStream().collect(summary);
// So sánh giá trị các trường count, sum, average của hai report.
```

Đây là đoạn kiểm tra ý tưởng, **không phải chương trình độc lập**. Để kiểm tra tự động, nên viết test cho số liệu thực tế và các bất biến thay vì so sánh hai object khác tham chiếu bằng toán tử `==`.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Với `Collector<String, StringBuilder, String>`, đâu là `T`, `A` và `R`?

**Trả lời:** `T=String` là phần tử đầu vào; `A=StringBuilder` là vùng chứa mutable; `R=String` là kết quả cuối. Finisher thường là `StringBuilder::toString`.

**Câu 2.** Tại sao supplier `() -> sharedArrayList` có thể sai dù accumulator `List::add` tự nó đơn giản?

**Trả lời:** Supplier trả cùng tham chiếu, khiến các nhánh hoặc lần thu thập dùng chung state mutable. Điều này có thể gây race, trùng hoặc mất dữ liệu. Supplier phải tạo container mới khi cần.

**Câu 3.** Vì sao collector muốn hỗ trợ parallel stream phải viết combiner đúng?

**Trả lời:** Runtime có thể tạo nhiều kết quả trung gian rồi gộp. Nếu combiner bỏ dữ liệu hoặc không thỏa tính kết hợp, kết quả phụ thuộc cách phân chia input.

**Câu 4.** Collector có finisher chuyển `StatsBox -> Report` có được gắn `IDENTITY_FINISH` không?

**Trả lời:** Không. Hai kiểu khác nhau và bước chuyển đổi phải chạy; `IDENTITY_FINISH` cho phép runtime bỏ finisher.

**Câu 5.** Tại sao `Collector.of(...)` dùng combiner trả `A`, còn `Stream.collect(supplier, accumulator, combiner)` lại dùng combiner trả `void`?

**Trả lời:** Đó là hai overload API với kiểu hàm khác nhau: `Collector.of` dùng `BinaryOperator<A>`, còn `Stream.collect` ba tham số dùng `BiConsumer<R,R>`. Khi chuyển mã phải viết đúng chữ ký.

**Câu 6.** Có phải collector muốn dùng với parallel stream bắt buộc có `CONCURRENT`?

**Trả lời:** Không. Collector thông thường vẫn có thể thực thi song song thông qua các container trung gian và combiner. `CONCURRENT` chỉ dành cho collector cho phép nhiều thread tích lũy an toàn vào **cùng** một container theo điều kiện của Stream.

**Câu 7.** Vì sao `finisher` không nên dùng để tăng một bộ đếm toàn cục và kỳ vọng nó được gọi đúng một lần?

**Trả lời:** Collector có thể được dùng trong downstream collector nhiều nhóm; collector có `IDENTITY_FINISH` có thể được tối ưu bỏ finisher. Side effect như vậy không thuộc kết quả nghiệp vụ ổn định của collector.

## 18. Tài liệu API đang được hỗ trợ

- [Oracle Java SE 26 — `Collector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html): chữ ký các hàm, identity, associativity, cách hoạt động song song và characteristics.
- [Oracle Java SE 26 — `Stream.collect`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): các overload của `collect` và hợp đồng mutable reduction.
- [Oracle Java SE 26 — `Collectors`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): collector chuẩn, `collectingAndThen`, `groupingBy` và các lựa chọn trước khi tự viết collector.
- [dev.java — Creating Your Own Collector](https://dev.java/learn/api/collections-and-streams/streams/custom-collectors/): hướng dẫn chính thức về các thành phần collector.
- [dev.java — Implementing the Collector Interface](https://dev.java/learn/api/collections-and-streams/streams/collector-interface/): phân biệt kiểu vùng chứa, kết quả và characteristics.

**Điểm cần nhớ:** `supplier` tạo trạng thái trung gian độc lập; `accumulator` nhận từng phần tử và cập nhật trạng thái; `combiner` gộp các trạng thái để phép thu thập đúng khi chia nhánh; `finisher` biến trạng thái đã gộp thành kết quả cuối. **Bốn chức năng phải cùng thỏa hợp đồng identity, associativity, thứ tự và an toàn trạng thái**, để cùng một custom collector cho kết quả đúng với cả stream tuần tự lẫn song song.