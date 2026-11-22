# Kết hợp hai phép thu thập bằng teeing

Một báo cáo thường cần **nhiều chỉ số trên cùng tập dữ liệu**: số đơn hàng và tổng doanh thu, điểm thấp nhất và cao nhất, hoặc danh sách mã giao dịch cùng số lượng giao dịch. Có thể viết hai pipeline Stream độc lập rồi kết hợp kết quả, nhưng điều đó khiến nguồn phải được duyệt hai lần nếu có thể tạo lại, và không phù hợp khi dữ liệu chỉ được đọc một lần.

Từ **Java 12**, `Collectors.teeing(...)` cho phép **kết hợp hai collector** trong một phép `collect`. Mỗi phần tử đi vào **cả hai collector nhánh**, sau đó một hàm `merger` nhận **hai kết quả đã hoàn tất** để tạo kết quả cuối cùng. Cơ chế này đặc biệt hữu ích với các báo cáo nhiều chỉ số và các phép tổng hợp lồng nhau.

Bài thuộc chương **Collector nhiều tầng và tổng hợp** của module **JAVA_STREAM_API**. Ta sẽ tìm hiểu hợp đồng `teeing`, cách dùng `counting`, `summingLong`, `minBy`, `maxBy`, `groupingBy` và `filtering` làm downstream; đồng thời nhận diện giới hạn về thứ tự, trạng thái, nguồn Stream, bộ nhớ, tính kết hợp và hiệu năng khi chạy song song. Những nguyên tắc này cũng liên hệ với collector tùy chỉnh, `Spliterator` và Stream Gatherers.

## 1. Vì sao cần kết hợp hai collector?

Giả sử có danh sách thanh toán và ta cần hai chỉ số của **các khoản đã thanh toán**:

1. **Số giao dịch thành công**.
2. **Tổng tiền của các giao dịch thành công**.

Một cách viết thông thường là tạo hai Stream:

~~~java
long count = payments.stream()
    .filter(Payment::paid)
    .count();

long total = payments.stream()
    .filter(Payment::paid)
    .mapToLong(Payment::amountVnd)
    .sum();
~~~

Hai đoạn code hợp lệ nếu `payments` là một collection có thể duyệt lại, nhưng phải duyệt danh sách **hai lần**, thực hiện `filter` hai lần và quản lý hai kết quả độc lập. Với nguồn đọc một lần (ví dụ Stream từ file), không thể dùng lại **cùng một đối tượng Stream** sau terminal operation đầu tiên.

`teeing` mô tả việc thu cả hai kết quả trong **một terminal operation**:

~~~java
Stats result = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));
~~~

Đoạn này giả định đã khai báo `record Payment(...)` và `record Stats(long count, long totalVnd)` như ví dụ đầy đủ bên dưới.

Điểm quan trọng: **`teeing` không phải phép nhân bản Stream**. Nó xây **một collector tổng hợp** có hai collector nhánh. Mỗi phần tử được đưa tới hai accumulator của chúng trong một lần thu thập.

## 2. Ví dụ hoàn chỉnh: số lượng và tổng tiền trong một lần collect

Đoạn sau có thể đặt trong file `TeeingOverviewDemo.java` và chạy với **JDK 17+**. `Collectors.teeing` có từ Java 12; ví dụ sử dụng thêm `record` và `List.of` để mã dễ đọc.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TeeingOverviewDemo {
    record Payment(
        String id,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    record Stats(long count, long totalVnd) {}

    public static void main(String[] args) {
        List<Payment> payments = List.of(
            new Payment("P01", "Văn phòng", 120_000L, true),
            new Payment("P02", "Sách",       70_000L, false),
            new Payment("P03", "Văn phòng",  80_000L, true),
            new Payment("P04", "Sách",      200_000L, true),
            new Payment("P05", "Văn phòng",  50_000L, false),
            new Payment("P06", "Thể thao",   60_000L, false)
        );

        Stats paidStats = payments.stream()
            .filter(Payment::paid)
            .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Payment::amountVnd),
                Stats::new
            ));

        System.out.println(paidStats);
        // Stats[count=3, totalVnd=400000]

        Map<String, Stats> paidStatsByCategory = payments.stream()
            .filter(Payment::paid)
            .collect(Collectors.groupingBy(
                Payment::category,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingLong(Payment::amountVnd),
                    Stats::new
                )
            ));

        System.out.println(paidStatsByCategory.get("Văn phòng"));
        // Stats[count=2, totalVnd=200000]

        System.out.println(paidStatsByCategory.get("Sách"));
        // Stats[count=1, totalVnd=200000]

        System.out.println(paidStatsByCategory.containsKey("Thể thao"));
        // false: không có giao dịch đã thanh toán trong nhóm này
    }
}
~~~

Giải thích:

- `counting()` tạo kết quả đầu tiên kiểu `Long`, là số giao dịch đạt điều kiện.
- `summingLong(Payment::amountVnd)` tạo kết quả thứ hai kiểu `Long`, là tổng tiền.
- `Stats::new` là hàm ghép hai kết quả thành một `Stats`.
- `groupingBy(Payment::category, teeing(...))` thực hiện cùng phép tính **riêng trong từng nhóm danh mục**.
- Vì có `filter(Payment::paid)` trước `groupingBy`, danh mục chỉ có giao dịch chưa thanh toán (`Thể thao`) không được tạo trong kết quả.

Trong ví dụ này, thứ tự các khóa của `Map` không được bảo đảm. Ta truy xuất bằng khóa cụ thể thay vì giả định kết quả của `Map.toString()` có thứ tự cố định.

## 3. Chữ ký và ba vai trò của teeing

Chữ ký API có thể đọc theo dạng:

~~~java
public static <T, R1, R2, R>
Collector<T, ?, R> teeing(
    Collector<? super T, ?, R1> downstream1,
    Collector<? super T, ?, R2> downstream2,
    BiFunction<? super R1, ? super R2, R> merger
)
~~~

| Thành phần | Nhận gì? | Tạo gì? | Trách nhiệm |
|---|---|---|---|
| `downstream1` | Các phần tử `T` | Kết quả `R1` | Thu thập chỉ số/thông tin thứ nhất |
| `downstream2` | **Cùng các phần tử `T`** | Kết quả `R2` | Thu thập chỉ số/thông tin thứ hai |
| `merger` | Kết quả `R1` và `R2` | Kết quả cuối `R` | Kết hợp hai kết quả, không duyệt lại nguồn |

Những kiểu `R1`, `R2` và `R` **không cần giống nhau**. Ví dụ một nhánh tạo `List<String>`, nhánh kia tạo `Long`, còn kết quả cuối là record tùy chỉnh.

### 3.1. teeing diễn ra khi nào?

~~~mermaid
flowchart TD
    S["Stream<Payment>"] --> C["collect(teeing(...))"]
    C --> A["Collector 1: counting"]
    C --> B["Collector 2: summingLong"]
    A --> R1["R1: Long count"]
    B --> R2["R2: Long total"]
    R1 --> M["merger(count, total)"]
    R2 --> M
    M --> R["Stats(count, total)"]
~~~

Khi `collect` chạy, framework tổ chức việc thu thập vào hai nhánh. Chỉ **sau khi hai nhánh tạo kết quả của mình**, hàm `merger` mới kết hợp chúng. Nó **không phải** hàm được gọi một lần cho từng phần tử.

Trong pipeline song song, mỗi collector nhánh còn có thể có các bộ chứa cục bộ và bộ kết hợp (*combiner*) riêng trước giai đoạn tạo kết quả cuối. Số lần tạo bộ chứa và thứ tự thực thi là chi tiết của framework, không nên dùng làm logic nghiệp vụ.

### 3.2. Phân biệt merger với accumulator và combiner

Ba khái niệm dễ nhầm:

- **Accumulator của mỗi downstream collector:** cập nhật trạng thái tích lũy khi nhận **mỗi phần tử `T`**.
- **Combiner của mỗi downstream collector:** hợp nhất **hai trạng thái tích lũy cùng loại**, đặc biệt khi chạy song song.
- **`merger` của `teeing`:** nhận **hai kết quả cuối** `R1` và `R2` rồi tạo `R`.

Ví dụ `Stats::new` chỉ chạy ở bước tạo kết quả cuối; nó **không chịu trách nhiệm** cộng trực tiếp từng số tiền của các phần tử đầu vào.

## 4. Suy luận kiểu khi hai nhánh có kết quả khác nhau

Hãy viết các kiểu một cách tường minh để thấy cơ chế:

~~~java
Collector<Payment, ?, Long> counter =
    Collectors.counting();

Collector<Payment, ?, Long> moneySum =
    Collectors.summingLong(Payment::amountVnd);

Collector<Payment, ?, Stats> both =
    Collectors.teeing(
        counter,
        moneySum,
        Stats::new
    );

Stats result = payments.stream()
    .filter(Payment::paid)
    .collect(both);
~~~

Ở đây `Payment`, `Stats` và `payments` được khai báo trong ví dụ hoàn chỉnh mục 2. Để biên dịch đoạn riêng này cần import `java.util.stream.Collector` và `java.util.stream.Collectors`.

Bảng kiểu:

| Vị trí | Kiểu |
|---|---|
| Phần tử nguồn | `Payment` |
| Kết quả nhánh 1 | `Long` |
| Kết quả nhánh 2 | `Long` |
| BiFunction của `merger` | `(Long, Long) -> Stats` |
| Kết quả chung | `Stats` |

Với record `Stats(long count, long totalVnd)`, Java có thể thực hiện unboxing từ `Long` sang `long` khi gọi constructor. Khi compiler không suy luận được kiểu generic trong một biểu thức lồng nhiều cấp, ta có thể tách downstream và merger thành biến có kiểu rõ ràng thay vì thêm các ép kiểu không an toàn.

## 5. Ví dụ hai kiểu đầu ra khác nhau: danh sách và tổng tiền

Giả sử báo cáo cần **danh sách mã giao dịch** và **tổng tiền** của cùng nhóm. Một nhánh trả `List<String>`, một nhánh trả `Long`:

~~~java
record DetailReport(List<String> ids, long totalVnd) {}

DetailReport details = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.mapping(
            Payment::id,
            Collectors.toList()
        ),
        Collectors.summingLong(Payment::amountVnd),
        (ids, total) ->
            new DetailReport(List.copyOf(ids), total)
    ));

System.out.println(details.ids());
// [P01, P03, P04]

System.out.println(details.totalVnd());
// 400000
~~~

Ví dụ dùng `payments` và `Payment` từ mục 2, cùng `List`/`Collectors` đã import.

Lưu ý quan trọng:

1. `mapping(Payment::id, toList())` là **collector lồng**: nó lấy mã từ `Payment` trong nhánh thứ nhất, không làm mất dữ liệu cần dùng trong nhánh thứ hai.
2. `summingLong` lấy số tiền từ **cùng các phần tử Payment**.
3. `List.copyOf(ids)` (Java 10+) tạo danh sách kết quả không cho sửa, giúp bảo vệ kết quả báo cáo khỏi thay đổi danh sách trung gian; nó **không chấp nhận phần tử null**.
4. Một record chứa `List` không tự làm nội dung List trở nên bất biến. Nếu bỏ `List.copyOf`, một danh sách có thể thay đổi vẫn được đặt vào record.

Nếu đầu ra cần đầy đủ thứ tự theo `List` nguồn, `Collectors.toList()` là downstream có thể thu theo encounter order của nguồn có thứ tự. Với các Stream không có thứ tự hoặc collector `UNORDERED`, không được áp đặt kỳ vọng về thứ tự mã.

### 5.1. Chỉ cần tập mã không trùng

Thay `mapping(Payment::id, toList())` bằng:

~~~java
Collectors.mapping(Payment::id, Collectors.toSet())
~~~

thì kiểu kết quả nhánh thứ nhất trở thành `Set<String>`. Tuy nhiên, `toSet()` **không bảo đảm thứ tự duyệt**; nếu báo cáo cần tập sắp xếp, có thể dùng `toCollection(TreeSet::new)` khi phần tử so sánh được.

## 6. Tìm giá trị nhỏ nhất và lớn nhất trong cùng một collect

Một cách dùng rất tự nhiên của `teeing` là kết hợp `minBy` với `maxBy`. Mỗi collector trả về một `Optional<T>` vì tập nguồn có thể rỗng.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class TeeingExtremesDemo {
    record Score(String student, int point) {}
    record Extremes(
        Optional<Score> lowest,
        Optional<Score> highest
    ) {}

    public static void main(String[] args) {
        List<Score> scores = List.of(
            new Score("An", 8),
            new Score("Bình", 5),
            new Score("Chi", 9),
            new Score("Dũng", 7)
        );

        Comparator<Score> byPoint =
            Comparator.comparingInt(Score::point);

        Extremes result = scores.stream().collect(
            Collectors.teeing(
                Collectors.minBy(byPoint),
                Collectors.maxBy(byPoint),
                Extremes::new
            )
        );

        System.out.println(
            result.lowest().map(Score::student).orElse("Không có")
        ); // Bình

        System.out.println(
            result.highest().map(Score::student).orElse("Không có")
        ); // Chi
    }
}
~~~

Nếu danh sách điểm rỗng:

~~~java
Extremes empty = List.<Score>of().stream()
    .collect(Collectors.teeing(
        Collectors.minBy(byPoint),
        Collectors.maxBy(byPoint),
        Extremes::new
    ));

System.out.println(empty.lowest().isPresent());  // false
System.out.println(empty.highest().isPresent()); // false
~~~

Đoạn thứ hai dùng `Score`, `byPoint` và `Extremes` từ phạm vi chương trình trước. Hai collector `minBy` và `maxBy` đều trả Optional rỗng, **nhưng bản thân phép `collect(teeing)` vẫn hoàn thành và trả một đối tượng `Extremes`** có hai trường Optional rỗng.

Với các phần tử bằng nhau theo comparator, không dựa vào một bản ghi đồng hạng cụ thể trừ khi có quy tắc phá hòa. Nếu cần kết quả xác định, xây comparator gồm các tiêu chí phụ (chẳng hạn `thenComparing(Score::student)`).

### 6.1. Khi đầu ra phải là một Optional chung

Nếu nghiệp vụ không muốn đối tượng `Extremes` chứa hai Optional rỗng, `merger` có thể kiểm tra trạng thái và trả một `Optional<Extremes>`:

~~~java
Optional<Extremes> result = scores.stream()
    .collect(Collectors.teeing(
        Collectors.minBy(byPoint),
        Collectors.maxBy(byPoint),
        (min, max) ->
            min.isPresent() && max.isPresent()
                ? Optional.of(new Extremes(min, max))
                : Optional.empty()
    ));
~~~

Đoạn code dùng các khai báo ở ví dụ đầy đủ. Đây là một **chính sách biểu diễn kết quả**, không phải hành vi mặc định của `teeing`. Tùy bài toán, giữ hai Optional riêng cũng có thể rõ nghĩa hơn.

## 7. Kết quả rỗng: mỗi downstream có quy tắc riêng

`teeing` **không tự tạo ra `Optional.empty()`** khi Stream rỗng. Nó chạy hợp đồng của hai downstream và đưa kết quả vào `merger`.

| Downstream | Kết quả khi không có phần tử |
|---|---|
| `counting()` | `0L` |
| `summingLong(...)` | `0L` |
| `averagingLong(...)` | `0.0` |
| `toList()` | Danh sách rỗng |
| `toSet()` | Tập rỗng |
| `minBy(...)` | `Optional.empty()` |
| `maxBy(...)` | `Optional.empty()` |
| `reducing(BinaryOperator)` | `Optional.empty()` |

Ví dụ:

~~~java
Stats noPayments = java.util.stream.Stream.<Payment>empty()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));

System.out.println(noPayments);
// Stats[count=0, totalVnd=0]
~~~

Ở đây dùng `Payment` và `Stats` của mục 2. **`Stats(0, 0)` có thể được hiểu là một kết quả thống kê hợp lệ**, nhưng không tự phân biệt “không có giao dịch” với “có giao dịch nhưng tổng bằng 0”. Nếu báo cáo cần phân biệt, dùng `count` để xác định dữ liệu có mặt.

### 7.1. Trung bình cần xử lý mẫu số bằng 0

Nếu muốn tính trung bình từ `count` và `total`, đừng chia mà không kiểm tra `count == 0`:

~~~java
import java.util.OptionalDouble;

OptionalDouble average = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.summingLong(Payment::amountVnd),
        Collectors.counting(),
        (total, count) -> count == 0L
            ? OptionalDouble.empty()
            : OptionalDouble.of((double) total / count)
    ));

System.out.println(average.orElse(Double.NaN));
// 133333.33333333334 với ba giao dịch thành công
~~~

Ở đây `OptionalDouble.empty()` là lựa chọn nghiệp vụ khi không có phần tử. Nếu chỉ cần **giá trị trung bình đơn lẻ**, `mapToLong(Payment::amountVnd).average()` đã trả `OptionalDouble` và có thể ngắn hơn. Dùng `teeing` khi thực sự cần **hai phép thu thập khác nhau** hoặc một báo cáo ghép.

Với tiền tệ, dùng `double` có thể gây sai số làm tròn. Hãy lựa chọn đơn vị nguyên và chính sách làm tròn hoặc dùng `BigDecimal` khi yêu cầu tính toán chính xác.

## 8. Kết hợp teeing bên trong groupingBy

Một lợi thế của `teeing` là có thể dùng làm **downstream** của `groupingBy`. Khi đó, mỗi nhóm có riêng hai nhánh thống kê:

~~~java
Map<String, Stats> byCategory = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.groupingBy(
        Payment::category,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Payment::amountVnd),
            Stats::new
        )
    ));
~~~

Bảng tương ứng với ví dụ mục 2:

| Danh mục | Số giao dịch đã thanh toán | Tổng tiền |
|---|---:|---:|
| Văn phòng | 2 | 200.000 |
| Sách | 1 | 200.000 |
| Thể thao | *Không có khóa* | *Không có khóa* |

Nhánh thống kê của từng nhóm chỉ nhận các phần tử **trong nhóm đó**. `teeing` không làm phẳng những nhóm hoặc sử dụng chung một `Stats` cho tất cả danh mục.

### 8.1. Giữ nhóm có kết quả bằng 0 bằng filtering downstream

Giả sử cần hiển thị cả danh mục có giao dịch nhưng **không có giao dịch được thanh toán** (ở ví dụ này là Thể thao). Nếu lọc `paid` trước `groupingBy`, nhóm đó biến mất.

Dùng **`Collectors.filtering`** (Java 9+) **bên trong** nhóm và **bên ngoài** `teeing`:

~~~java
Map<String, Stats> includingZero = payments.stream()
    .collect(Collectors.groupingBy(
        Payment::category,
        Collectors.filtering(
            Payment::paid,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Payment::amountVnd),
                Stats::new
            )
        )
    ));

System.out.println(includingZero.get("Thể thao"));
// Stats[count=0, totalVnd=0]
~~~

Ở đây:

1. `groupingBy(Payment::category)` nhìn thấy **mọi giao dịch**, nên tạo nhóm Thể thao.
2. `filtering(Payment::paid, ...)` chỉ chuyển **giao dịch đã thanh toán** của mỗi nhóm tới downstream.
3. `teeing` tổng hợp số đếm và tổng tiền trên dữ liệu đã qua lọc.
4. Nhóm không có giao dịch thỏa điều kiện vẫn tạo `Stats(0, 0)`.

**Lưu ý:** Nếu một danh mục **không có bất kỳ giao dịch nào trong nguồn**, `groupingBy` không tự tạo khóa cho danh mục đó. Muốn đầy đủ mọi danh mục hợp lệ kể cả danh mục chưa xuất hiện, ứng dụng cần có danh sách danh mục chuẩn và bước bổ sung nhóm vắng mặt.

### 8.2. Khi nào phải đặt filtering riêng cho hai nhánh?

Hai chỉ số đôi khi dùng **hai điều kiện khác nhau**, ví dụ số lượng giao dịch thành công và tổng tiền giao dịch thất bại. Khi đó, mỗi nhánh phải tự lọc theo quy tắc của mình:

~~~java
record TwoStates(long paidCount, long unpaidTotalVnd) {}

TwoStates result = payments.stream().collect(Collectors.teeing(
    Collectors.filtering(
        Payment::paid,
        Collectors.counting()
    ),
    Collectors.filtering(
        p -> !p.paid(),
        Collectors.summingLong(Payment::amountVnd)
    ),
    TwoStates::new
));

System.out.println(result);
// TwoStates[paidCount=3, unpaidTotalVnd=180000]
~~~

Ở đây `TwoStates` được khai báo như một record Java 16+. Giao dịch chưa thanh toán gồm `P02` (70.000), `P05` (50.000), `P06` (60.000), nên tổng là **180.000**.

Điểm quan trọng: hai downstream của `teeing` **cùng nhận tập đầu vào tổng**, nhưng mỗi downstream `filtering` có điều kiện riêng. Không thể đặt một phép `stream.filter(Payment::paid)` trước `teeing` nếu nhánh thứ hai cần nhìn thấy các giao dịch chưa thanh toán.

## 9. Kết hợp ba phép tổng hợp bằng teeing lồng nhau

`teeing` nhận **đúng hai downstream**. Khi cần ba hoặc nhiều chỉ số, có thể lồng một `teeing` bên trong nhánh khác, rồi ghép kết quả:

~~~java
record Tail(long totalVnd, long highestVnd) {}
record FullStats(long count, long totalVnd, long highestVnd) {}

FullStats result = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.teeing(
            Collectors.summingLong(Payment::amountVnd),
            Collectors.collectingAndThen(
                Collectors.maxBy(
                    java.util.Comparator.comparingLong(Payment::amountVnd)
                ),
                max -> max.map(Payment::amountVnd).orElse(0L)
            ),
            Tail::new
        ),
        (count, tail) ->
            new FullStats(count, tail.totalVnd(), tail.highestVnd())
    ));

System.out.println(result);
// FullStats[count=3, totalVnd=400000, highestVnd=200000]
~~~

Ví dụ sử dụng `Payment` và `payments` ở mục 2. `Tail` chỉ là đối tượng trung gian để đóng gói kết quả của hai collector nhánh bên trong.

Đoạn code hợp lệ, nhưng **không nhất thiết là cách tốt nhất** để lấy số lượng, tổng và giá trị lớn nhất. Khi tất cả chỉ số cùng thuộc một thuộc tính số, `Collectors.summarizingLong` thường đơn giản hơn:

~~~java
java.util.LongSummaryStatistics stats = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.summarizingLong(Payment::amountVnd));

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 400000
System.out.println(stats.getMax());   // 200000
~~~

Hãy chọn `teeing` khi muốn ghép **hai kết quả hoặc hai loại phân tích khác nhau** thành một kiểu kết quả có nghĩa. Không lồng `teeing` chỉ vì có thể làm vậy.

## 10. teeing khác gì với reduce và collector tùy chỉnh?

| Tình huống | Công cụ phù hợp | Vì sao |
|---|---|---|
| Chỉ tính tổng số nguyên | `mapToLong(...).sum()` | Ngắn, trực tiếp, tránh boxing trung gian |
| Chỉ cần count/sum/min/max/average của một trường số | `summarizingLong(...)` | Có sẵn bộ thống kê nhiều chỉ số |
| Kết hợp hai báo cáo sẵn có, như `counting` và `toList` | `teeing(...)` | Tái sử dụng hai collector, gộp kết quả có kiểm soát |
| Nhóm dữ liệu, mỗi nhóm trả hai chỉ số | `groupingBy(..., teeing(...))` | Mỗi nhóm có báo cáo kết hợp riêng |
| Muốn trạng thái tích lũy đặc biệt hoặc hơn hai chỉ số liên quan | Collector tùy chỉnh | Kiểm soát bộ chứa, accumulator, combiner và finisher |
| Gộp các giá trị bất biến bằng phép toán associative | `reduce(...)` | Hợp đồng non-mutating reduction rõ ràng |

### 10.1. teeing không thay thế mọi collector tùy chỉnh

`teeing` sử dụng **hai cơ chế tích lũy riêng**. Nếu hai chỉ số chia sẻ nhiều dữ liệu trung gian hoặc cần nhiều thành phần thống kê kết hợp chặt chẽ, một collector tùy chỉnh với **một bộ chứa** có thể giảm cấp phát hoặc giảm thao tác; song bạn phải tự bảo đảm hợp đồng supplier/accumulator/combiner/finisher.

Ngược lại, khi đã có hai collector chuẩn đúng mục tiêu, `teeing` giúp code dễ đọc và tránh viết lại logic tích lũy, nhất là với các downstream phức tạp.

### 10.2. teeing không giống reduce với một cặp mutable

Không nên cố tự dựng một `Pair` mutable và đưa vào `reduce(identity, accumulator, combiner)` bằng cách sửa cùng đối tượng tích lũy. Một `reduce` như vậy dễ vi phạm hợp đồng identity/associativity và gây sai khi chạy song song.

`teeing` nằm trong mô hình **mutable reduction qua Collector**: mỗi collector nhánh kiểm soát bộ chứa trung gian đúng hợp đồng, còn `merger` chỉ làm việc với kết quả đã được hoàn tất.

## 11. Đặc tính Collector và xử lý song song

Một collector có các **characteristics** như `UNORDERED`, `CONCURRENT` và `IDENTITY_FINISH`. Với `teeing`, các đặc tính có thể được kế thừa theo sự tương thích của **cả hai downstream**.

Về nguyên tắc:

- Chỉ khi **cả hai** downstream phù hợp với `CONCURRENT`, collector kết hợp mới có thể công bố đặc tính đồng thời đó.
- Chỉ khi **cả hai** downstream là `UNORDERED`, collector kết hợp mới có thể công bố tính không có thứ tự.
- `teeing` **không mang `IDENTITY_FINISH`**, vì kết quả cần đi qua hàm `merger`.

Đặc tính thực tế do API của các downstream xác định; **không nên tự suy đoán** rằng `teeing(toList(), counting(), ...)` có thể dùng một container kết quả duy nhất cho nhiều thread.

### 11.1. Chạy parallel không có nghĩa dùng một container chia sẻ

~~~java
Stats parallelStats = payments.parallelStream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));

System.out.println(parallelStats);
// Stats[count=3, totalVnd=400000]
~~~

Với bộ dữ liệu mẫu, kết quả bằng kết quả tuần tự. Framework quản lý việc tích lũy cục bộ và kết hợp các kết quả theo hợp đồng collector; không nên sử dụng một `ArrayList` hoặc `HashMap` mutable ngoài pipeline làm biến chia sẻ cho hai nhánh.

Chẳng hạn, **không nên** viết:

~~~java
java.util.ArrayList<String> sharedIds =
    new java.util.ArrayList<>();

// Không thu thập theo kiểu có tác dụng phụ ngoài:
// payments.parallelStream().forEach(p -> sharedIds.add(p.id()));
~~~

`ArrayList` không thread-safe. Ngay cả khi dùng một cấu trúc có đồng bộ, thứ tự và hiệu năng vẫn phải xét theo mục tiêu nghiệp vụ. Nếu muốn danh sách trong một nhánh của `teeing`, dùng `mapping(..., toList())` hoặc collector phù hợp.

### 11.2. Không sử dụng merger để sửa nguồn hoặc kích hoạt nghiệp vụ ngoài

`merger` nên thuần theo nghĩa: nhận hai kết quả và xây một kết quả rõ ràng. Tránh dùng nó để gửi thông báo, ghi database hoặc thay đổi trạng thái dùng chung. Với parallel Stream, các callback trung gian và combiner có thể chạy ở những thread/thứ tự khác nhau; dù merger tạo kết quả cuối, tác dụng phụ ở đây vẫn khiến code khó kiểm thử và khó tái sử dụng.

Khi cần I/O sau khi đã có báo cáo, hãy tách thành bước **sau `collect`**. Ví dụ:

~~~java
Stats stats = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));

System.out.println("Đã tính báo cáo: " + stats);
~~~

## 12. Thứ tự, null và tính ổn định của dữ liệu

### 12.1. Encounter order vẫn quan trọng nếu một nhánh thu List

Một `List` làm nguồn có thứ tự; `Collectors.toList()` có thể giữ thứ tự phần tử theo encounter order. Nhưng nếu pipeline gọi `unordered()` hoặc nguồn không có encounter order, đừng kỳ vọng nhánh kết quả danh sách phản ánh một thứ tự cụ thể.

Các downstream như `counting` và `summingLong` về ý nghĩa không phụ thuộc thứ tự phần tử khi số học chính xác và không tràn; các collector chọn đại diện khi hòa nhau (như `minBy` trên comparator không có tie-breaker) có thể có yêu cầu mạnh hơn về thứ tự hoặc quy tắc ưu tiên.

### 12.2. Null cần được xử lý theo hợp đồng từng nhánh

`teeing` không tự loại `null`. Nếu phần tử nguồn có thể là null, một nhánh như `mapping(Payment::id, ...)` hoặc `summingLong(Payment::amountVnd)` có thể ném `NullPointerException`.

~~~java
import java.util.Arrays;
import java.util.Objects;

List<Payment> safePayments = Arrays.asList(
    new Payment("P01", "Sách", 100L, true),
    null
);

Stats safeStats = safePayments.stream()
    .filter(Objects::nonNull)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));
~~~

Ngoài null đầu vào, từng downstream còn có chính sách riêng: `toUnmodifiableList()` không chấp nhận phần tử null, `groupingBy` không cho classifier trả khóa null theo hợp đồng triển khai Java chuẩn, và một `minBy` trên comparator không xử lý được null cũng có thể lỗi.

Không nên coi hai nhánh sẽ luôn xử lý null giống nhau. Hãy chuẩn hóa hoặc xác thực dữ liệu **trước** giai đoạn thu thập khi có thể.

### 12.3. Không sửa nguồn khi đang thu thập

Các lambda như `Payment::amountVnd` hoặc `Payment::paid` nên không can thiệp nguồn và không phụ thuộc trạng thái ngoài thay đổi giữa lúc duyệt. Nếu đối tượng nguồn bị sửa trong lúc chạy song song, các nhánh có thể quan sát dữ liệu khác nhau và báo cáo sẽ không còn nhất quán.

Nếu báo cáo cần một **snapshot** của dữ liệu biến đổi liên tục, cần chiến lược chụp dữ liệu hoặc giao dịch ở tầng nguồn. `teeing` giúp hợp nhất hai phép thu thập trong một pipeline nhưng **không bảo đảm snapshot nguyên tử** trước các thay đổi đồng thời từ bên ngoài.

## 13. Tài nguyên và hiệu năng: một lần duyệt không có nghĩa chi phí bằng một collector

### 13.1. Ưu điểm

- Một pipeline `collect` có thể xây **hai chỉ số** mà không cần chạy hai Stream riêng.
- Tái sử dụng collector có sẵn, giảm lượng code accumulator/combiner tự viết.
- Phù hợp với nguồn chỉ đọc một lần hoặc nguồn mà việc duyệt lại đắt đỏ.
- Dễ ghép với `groupingBy` hoặc downstream như `filtering` và `mapping`.

### 13.2. Giới hạn

- Mỗi phần tử được xử lý bởi **cả hai nhánh**; đó không phải một phép tính miễn phí.
- Hai collector có thể giữ **hai trạng thái tích lũy** khác nhau. Nếu một nhánh là `toList` và một nhánh là `toSet`, bộ nhớ có thể tăng theo kích thước các kết quả.
- Nếu cả hai nhánh đều duyệt và xây cấu trúc phức tạp, một collector tùy chỉnh chia sẻ trạng thái có thể tiết kiệm hơn — nhưng cần đo kiểm thay vì phỏng đoán.
- `teeing` là terminal collection: với nguồn vô hạn không có điểm dừng, collector thường **không thể hoàn thành**.
- `summingLong` có thể tràn `long`; thống kê dấu phẩy động có sai số và có thể phụ thuộc thứ tự phép tính.

### 13.3. So sánh với hai lần collect

~~~java
long count = payments.stream().filter(Payment::paid).count();

long total = payments.stream()
    .filter(Payment::paid)
    .mapToLong(Payment::amountVnd)
    .sum();
~~~

Hai pipeline riêng giúp dễ đọc trong một số tình huống nhỏ, nhưng duyệt lại nguồn. `teeing` giúp gộp trong một pipeline; tuy nhiên, nó cũng tạo/ghép hai accumulator và chạy merger cuối. Trên dữ liệu ít phần tử, **đừng khẳng định** nó luôn nhanh hơn. Với vấn đề hiệu năng quan trọng, hãy kiểm tra bằng benchmark thực tế trên JDK và kiểu nguồn của ứng dụng.

### 13.4. Đừng dùng teeing để giải quyết vấn đề kết thúc của Stream

Ví dụ sau **không nên chạy**:

~~~java
// Nguồn vô hạn và không có điều kiện dừng.
// java.util.stream.Stream.iterate(1, n -> n + 1)
//     .collect(Collectors.teeing(
//         Collectors.counting(),
//         Collectors.summingInt(Integer::intValue),
//         (count, sum) -> count + ":" + sum
//     ));
~~~

`counting` và `summingInt` phải xử lý đủ nguồn để trả kết quả. Khi nguồn không bao giờ hết, phép thu thập không thể tạo kết quả cuối. Nếu nhu cầu là lấy một cửa sổ hữu hạn:

~~~java
String firstFive = java.util.stream.IntStream
    .iterate(1, n -> n + 1)
    .limit(5)
    .boxed()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingInt(Integer::intValue),
        (count, sum) -> count + " phần tử, tổng = " + sum
    ));

System.out.println(firstFive);
// 5 phần tử, tổng = 15
~~~

Giới hạn `limit(5)` bảo đảm pipeline này có số phần tử hữu hạn.

## 14. Các lỗi thường gặp khi dùng teeing

| Cách hiểu/cách làm sai | Rủi ro | Cách sửa |
|---|---|---|
| Nghĩ `teeing` nhân đôi Stream thành hai Stream độc lập | Hiểu sai vòng đời và cách duyệt | Xem nó là **một Collector có hai nhánh** |
| Nghĩ `merger` chạy cho từng phần tử | Đặt nhầm logic tích lũy | Đưa việc tích lũy vào downstream, chỉ ghép kết quả ở merger |
| Dùng `counting` và `summingLong` rồi chia luôn cho count | Chia cho 0 với nguồn rỗng | Kiểm tra `count == 0` và định nghĩa chính sách |
| Dùng `minBy/maxBy` rồi gọi `Optional.get()` trực tiếp | Ném lỗi nếu nguồn rỗng | Xử lý Optional bằng `map`/`orElse`/`orElseThrow` |
| Dùng `groupingBy` sau khi `filter` nhưng muốn nhóm count 0 | Nhóm có toàn phần tử không đạt bị xóa | Dùng downstream `filtering` trong nhóm |
| Muốn hai điều kiện khác nhau nhưng lọc chung trước teeing | Nhánh thứ hai mất dữ liệu cần thiết | Đặt `filtering` riêng cho từng nhánh |
| Dùng `toList` rồi tưởng kết quả trong record bất biến | List có thể thay đổi | Sao chép `List.copyOf` nếu cần, và xử lý null |
| Tự cập nhật List/Map chung trong `parallelStream` | Race condition | Dùng collector đúng hợp đồng |
| Nghĩ merger quyết định đặc tính `CONCURRENT` | Kế thừa characteristics của hai downstream bị hiểu sai | Xem hợp đồng của cả hai collector; đừng tự khai báo tùy tiện |
| Dùng teeing để lấy các chỉ số số học đã có `summarizingLong` | Code lồng khó đọc không cần thiết | Ưu tiên collector chuyên dụng khi phù hợp |
| Thu thập trên nguồn vô hạn | Không thể hoàn thành phép tổng hợp | Cắt nguồn hoặc dùng cửa sổ hữu hạn |
| Cho rằng teeing tạo snapshot nguyên tử | Hai nhánh vẫn đọc nguồn có thể thay đổi | Ổn định dữ liệu trước pipeline |
| Tin rằng chạy song song luôn nhanh hơn | Chi phí chia việc và hợp nhất có thể lớn | Benchmark và kiểm tra điều kiện thread-safe |

## 15. Bài tập: báo cáo kết quả xử lý tác vụ theo nhóm

Một hệ thống có các tác vụ gồm `id`, `team`, `effort` và `done`. Hãy xây báo cáo bằng `teeing`, sau đó kết hợp với `groupingBy`.

**Yêu cầu:**

1. Đếm tác vụ **đã hoàn tất** và tính tổng `effort` của những tác vụ đó, trong **một phép `collect`**.
2. Tạo `Map<String, Metrics>` theo nhóm `team`, giữ cả nhóm chưa có tác vụ hoàn tất với `count = 0` và `total = 0`.
3. Từ `count` và `total`, tính trung bình của tác vụ hoàn tất; nếu không có dữ liệu, biểu diễn rõ trạng thái thiếu.
4. Không dùng danh sách mutable ngoài pipeline để đếm hoặc thu thập.
5. Giải thích vì sao `stream.filter(Task::done)` trước `groupingBy` sẽ không giữ nhóm chỉ có tác vụ chưa hoàn tất.

### Lời giải tham khảo (Java 17+)

~~~java
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

public class TeeingPractice {
    record Task(String id, String team, long effort, boolean done) {}
    record Metrics(long count, long total, OptionalDouble average) {}

    static Metrics toMetrics(long count, long total) {
        OptionalDouble average = count == 0L
            ? OptionalDouble.empty()
            : OptionalDouble.of((double) total / count);
        return new Metrics(count, total, average);
    }

    public static void main(String[] args) {
        List<Task> tasks = List.of(
            new Task("T01", "Backend", 5L, true),
            new Task("T02", "Frontend", 8L, false),
            new Task("T03", "Backend", 3L, true),
            new Task("T04", "QA", 4L, false),
            new Task("T05", "Frontend", 2L, true)
        );

        Metrics allDone = tasks.stream()
            .filter(Task::done)
            .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Task::effort),
                TeeingPractice::toMetrics
            ));

        Map<String, Metrics> byTeam = tasks.stream()
            .collect(Collectors.groupingBy(
                Task::team,
                Collectors.filtering(
                    Task::done,
                    Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Task::effort),
                        TeeingPractice::toMetrics
                    )
                )
            ));

        System.out.println(allDone.count()); // 3
        System.out.println(allDone.total()); // 10
        System.out.println(allDone.average().orElse(Double.NaN));
        // 3.3333333333333335

        System.out.println(byTeam.get("Backend").total()); // 8
        System.out.println(byTeam.get("Frontend").total()); // 2
        System.out.println(byTeam.get("QA").count());       // 0
        System.out.println(byTeam.get("QA").average().isPresent());
        // false
    }
}
~~~

Trong lời giải:

- Các tác vụ hoàn tất là `T01`, `T03` và `T05`, tổng effort bằng `5 + 3 + 2 = 10`.
- `toMetrics` là **merger** dùng lại cho cả phép tổng hợp toàn bộ lẫn từng nhóm.
- `groupingBy(Task::team)` tạo nhóm Backend, Frontend và QA từ **toàn bộ nguồn**.
- `filtering(Task::done, teeing(...))` chỉ chuyển tác vụ hoàn tất vào collector hai nhánh. QA không có tác vụ hoàn tất, nhưng vẫn có nhóm và được ghép thành `Metrics(count=0, total=0, average=empty)`.
- `OptionalDouble.empty()` cho trường hợp không có dữ liệu giúp phân biệt “không có mức trung bình” với “mức trung bình thực sự bằng 0”.

### Câu hỏi tự kiểm tra

1. `Collectors.teeing` được giới thiệu từ phiên bản Java nào? — **Java 12**.
2. `teeing` nhận mấy downstream và một hàm gì? — **Hai downstream collector** và một **BiFunction merger**.
3. `merger` nhận từng `Payment` hay kết quả cuối của mỗi collector? — **Hai kết quả đã thu thập**.
4. Có thể dùng `teeing(counting(), mapping(..., toList()), merger)` không? — **Có**, hai nhánh có thể có kiểu kết quả khác nhau.
5. `teeing(minBy(...), maxBy(...), ...)` trên nguồn rỗng có tự trả null không? — **Không mặc định**; hai downstream trả `Optional.empty()` rồi merger quyết định kết quả.
6. Khi nào dùng `summarizingLong` thay vì lồng nhiều `teeing`? — Khi chỉ cần các chỉ số chuẩn như count, sum, min, max, average của **cùng một trường số**.
7. `teeing` có đặc tính `IDENTITY_FINISH` không? — **Không**, vì cần thực hiện merger.
8. Làm sao giữ nhóm `QA` chỉ có tác vụ chưa hoàn tất? — Nhóm trước bằng `groupingBy`, đặt `filtering` bên trong downstream.
9. Nguồn Stream dùng với `teeing` có thể được tiêu thụ lại sau `collect` không? — **Không**, phải tạo Stream mới từ nguồn có thể sử dụng lại.
10. `teeing` có bảo đảm chạy nhanh hơn hai pipeline riêng không? — **Không**, cần xét số lượng phần tử, chi phí hai nhánh, bộ nhớ và cách thực thi.

## 16. Ghi nhớ và hướng vận dụng

**`Collectors.teeing(downstream1, downstream2, merger)`** kết hợp **hai phép thu thập trên cùng các phần tử** trong một terminal `collect`. Hai downstream có thể trả những kiểu khác nhau; `merger` biến hai kết quả thành một giá trị có ý nghĩa đối với nghiệp vụ. Hãy nhớ đây là **composition của collector**, không phải phép ghép hoặc nhân bản Stream.

Khi kết hợp với `groupingBy`, mỗi nhóm có thể trả một báo cáo gồm nhiều chỉ số. Đặt `filtering` **ở ngoài teeing nhưng bên trong groupingBy** nếu cần giữ nhóm có count 0; đặt `filtering` **riêng cho từng nhánh teeing** nếu hai chỉ số dùng hai điều kiện độc lập.

Luôn kiểm tra **nguồn rỗng**, **Optional**, **kiểu số và tràn số**, **thứ tự**, **null**, **trạng thái mutable của collector** và **chi phí tích lũy song song**. Khi chỉ cần các thống kê số học tiêu chuẩn, ưu tiên `summarizingLong` hoặc Stream nguyên thủy; khi hai downstream đã mô tả chính xác bài toán, `teeing` giúp xây một kết quả rõ ràng mà không phải tự viết collector phức tạp.
