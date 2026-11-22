# Thành phần supplier, accumulator, combiner và finisher của Collector

> **Chương:** Cơ chế collect và Collector  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Hiểu vai trò, kiểu dữ liệu và hợp đồng của bốn thành phần trong `Collector<T, A, R>`; tự xây một collector chính xác cho pipeline tuần tự và song song; biết khi nào nên dùng collector có sẵn.

Trong **JAVA_STREAM_API**, ta dùng các pipeline lazy với `filter`, `map` và các phép trung gian để mô tả cách biến đổi phần tử. Khi cần đưa những phần tử đã xử lý vào danh sách, bản đồ, báo cáo thống kê hoặc cấu trúc riêng, một phép kết thúc thường gặp là **`collect(...)`**.

Một `Collector` mô tả cách **tích lũy nhiều phần tử thành kết quả**. Nó làm được điều đó bằng bốn thành phần: **`supplier`** tạo nơi tích lũy; **`accumulator`** đưa phần tử vào; **`combiner`** gộp các nơi tích lũy; **`finisher`** chuyển trạng thái tích lũy thành kết quả cuối. Các thành phần này đặc biệt quan trọng khi Stream được thực thi song song và Java có thể phân chia dữ liệu thành nhiều phần.

Bài học tập trung vào **hợp đồng giữa bốn thành phần**. Sau khi nắm mô hình này, việc dùng `Collectors.groupingBy`, `mapping`, `reducing`, collector tùy chỉnh, `Spliterator` và Stream Gatherers sẽ dễ lý giải hơn. Đồng thời, người học có cơ sở nhận diện lỗi liên quan đến trạng thái mutable, thứ tự, tài nguyên và hiệu năng.

Các ví dụ chạy được trên **Java 17+**; bản thân `Collector` và `Collector.of` đã xuất hiện từ Java 8. Một số ví dụ dùng `record` (Java 16+) và `Stream.toList()` (Java 16+).

## 1. Collector đứng ở đâu trong pipeline?

Xét một nguồn bán hàng:

```java
record Sale(String category, long amount) {}

List<Sale> sales = List.of(
    new Sale("Sách", 120_000),
    new Sale("Thiết bị", 200_000),
    new Sale("Sách", 80_000)
);
```

Muốn tính tổng tiền các giao dịch hợp lệ theo nhóm:

```java
Map<String, Long> revenue = sales.stream()
    .filter(sale -> sale.amount() > 0)
    .collect(Collectors.groupingBy(
        Sale::category,
        Collectors.summingLong(Sale::amount)
    ));
```

`filter` là phép **trung gian**: nó mô tả điều kiện. `collect` là phép **kết thúc**: nó yêu cầu đánh giá pipeline và trả `Map<String, Long>`. Trong ví dụ, `groupingBy` và `summingLong` là các factory method tạo Collector; chúng che giấu chi tiết tích lũy để ta chỉ cần nêu ý định nghiệp vụ.

Khi tự thiết kế Collector, ta phải làm rõ quá trình bên trong:

```text
                  Stream<Sale>
                       │
                       ▼
                collect(collector)
                       │
                  supplier()
                       ▼
               A: vùng tích lũy
                       │
           accumulator(A, Sale)
                  nhiều lần
                       ▼
               A: đã tích lũy
                       │
              [nếu có chia việc]
                       │
            combiner(A1, A2)
                       ▼
                A: tổng hợp
                       │
                  finisher(A)
                       ▼
                  R: kết quả
```

Ở đây **`A` không nhất thiết giống `R`**. Chẳng hạn, `A` có thể là một đối tượng mutable giữ bộ đếm và tổng, còn `R` là một record chỉ đọc chứa thống kê cuối.

Sơ đồ là mô hình logic, **không phải cam kết về số lần hoặc thứ tự gọi các hàm**. Java có thể dùng một vùng tích lũy hoặc nhiều vùng tùy nguồn, collector và chế độ thực thi. Một collector có đặc tính đặc biệt cũng có thể được tích lũy đồng thời vào cùng một vùng.

## 2. Kiểu tổng quát Collector<T, A, R>

Giao diện `java.util.stream.Collector` có ba tham số kiểu:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu của **mỗi phần tử đầu vào** từ Stream | `Sale` |
| `A` | Kiểu **trạng thái tích lũy trung gian** (*accumulation type*) | `SalesAccumulator` |
| `R` | Kiểu **kết quả trả về** sau collect | `SalesSummary` |

Các phương thức quan trọng của giao diện có chữ ký rút gọn:

```java
Supplier<A> supplier();

BiConsumer<A, T> accumulator();

BinaryOperator<A> combiner();

Function<A, R> finisher();

Set<Collector.Characteristics> characteristics();
```

Bốn thành phần đầu đóng góp trực tiếp vào quá trình gom dữ liệu. Phương thức thứ năm công bố các **đặc tính** mà framework được phép dựa vào, như `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT`.

Ví dụ, cách khai báo tường minh:

```java
Collector<String, StringJoiner, String> joining = Collector.of(
    () -> new StringJoiner(", "),
    StringJoiner::add,
    StringJoiner::merge,
    StringJoiner::toString
);
```

- `T = String`: các phần tử đầu vào.
- `A = StringJoiner`: nơi tích lũy các chuỗi.
- `R = String`: kết quả sau khi gọi `toString()`.

Đoạn mã cần import `java.util.StringJoiner` và `java.util.stream.Collector`. Trong nhiều tình huống, ta chỉ cần lưu biến ở kiểu `Collector<T, ?, R>` vì không cần tiết lộ kiểu trạng thái trung gian `A` cho nơi sử dụng.

## 3. Supplier: tạo vùng tích lũy mới

**Supplier** là hàm không nhận tham số, trả về một đối tượng kiểu `A`:

```java
Supplier<A> supplier();
```

Nhiệm vụ của nó là cấp **trạng thái khởi đầu phù hợp** cho mỗi vùng tích lũy mà quá trình `collect` cần tạo.

Ví dụ dễ hiểu:

```java
Supplier<ArrayList<String>> supplier = ArrayList::new;

ArrayList<String> first = supplier.get();
ArrayList<String> second = supplier.get();

System.out.println(first == second); // false
```

Mỗi lần gọi tạo danh sách mới. Với Collector, supplier không nên trả cùng một danh sách mutable đã lưu ở biến toàn cục cho mọi lượt sử dụng.

### 3.1. Tại sao supplier phải tạo trạng thái độc lập?

Khi chạy song song, framework có thể chia một nguồn thành nhiều phần. Mỗi phần có thể dùng một accumulator riêng, sau đó gộp lại:

```text
Phần nguồn 1                    Phần nguồn 2
    │                               │
supplier()                      supplier()
    │                               │
    ▼                               ▼
  A1 rỗng                         A2 rỗng
    │                               │
accumulate                       accumulate
    │                               │
    ▼                               ▼
 A1 có dữ liệu                   A2 có dữ liệu
    └────────── combiner ───────────┘
                    │
                    ▼
                  A tổng
```

Nếu supplier liên tục trả **cùng một đối tượng mutable**, dữ liệu có thể bị ghi trùng, dùng sai miền sở hữu hoặc gây race condition. Đây là lỗi về hợp đồng, kể cả khi một thử nghiệm tuần tự nhỏ chưa bộc lộ vấn đề.

**Sai:**

```java
List<String> shared = new ArrayList<>();

Collector<String, List<String>, List<String>> broken = Collector.of(
    () -> shared, // Tất cả vùng tích lũy dùng chung một list.
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

**Đúng:**

```java
Collector<String, List<String>, List<String>> collector = Collector.of(
    ArrayList::new, // Mỗi lần gọi tạo list mới.
    List::add,
    (left, right) -> {
        left.addAll(right);
        return left;
    }
);
```

Ví dụ dùng `java.util.List`, `java.util.ArrayList` và `java.util.stream.Collector`. Khi thiết kế một collector thông thường, hãy coi vùng tích lũy là tài nguyên **thuộc về một lần thực thi `collect`**, không giữ nó ở biến chia sẻ bên ngoài.

### 3.2. Trạng thái rỗng phải đóng vai trò phần tử đồng nhất

Giá trị do supplier tạo phải phù hợp với combiner. Nếu `a` là trạng thái đã tích lũy, thì việc gộp thêm một trạng thái rỗng phải tương đương với `a`:

```text
combine(a, supplier())  ≈  a
```

Ví dụ:

- Tổng số tiền: trạng thái mới có `sum = 0`.
- Đếm phần tử: trạng thái mới có `count = 0`.
- Danh sách: trạng thái mới là danh sách rỗng.
- Chuỗi nối: trạng thái mới là `StringJoiner` rỗng.

Dấu `≈` nghĩa là **tương đương theo kết quả Collector**, không nhất thiết là cùng một tham chiếu đối tượng.

## 4. Accumulator: đưa từng phần tử vào trạng thái

**Accumulator** là một `BiConsumer<A, T>`:

```java
BiConsumer<A, T> accumulator();
```

Nó nhận hai tham số: một vùng tích lũy `A` và một phần tử đầu vào `T`, rồi cập nhật vùng tích lũy đó.

Ví dụ tính tổng và đếm:

```java
static final class MutableStats {
    long count;
    long total;
}

BiConsumer<MutableStats, Long> addAmount = (stats, amount) -> {
    stats.count++;
    stats.total += amount;
};
```

Khi được áp dụng:

```java
MutableStats stats = new MutableStats();
addAmount.accept(stats, 100L);
addAmount.accept(stats, 200L);

// stats.count = 2
// stats.total = 300
```

Đoạn này giả định các khai báo nằm trong một lớp Java; `MutableStats` và `addAmount` minh họa vai trò của `A` và `T`.

### 4.1. Accumulator thường cập nhật A, không trả về A

Khác với `reduce` dùng hàm kết hợp trả giá trị, `Collector.accumulator()` trả `BiConsumer`, tức phương thức `accept` có kiểu trả về `void`. Vì vậy các collector mutable thường **thay đổi nội dung đối tượng `A`**.

```java
BiConsumer<List<String>, String> append =
    (list, item) -> list.add(item);
```

Lambda trên hợp lệ dù `List.add` trả `boolean`, bởi đây là một statement expression và kết quả bị bỏ qua trong ngữ cảnh `void`.

Không nên làm:

```java
List<String> outside = new ArrayList<>();

BiConsumer<List<String>, String> wrong =
    (current, item) -> outside.add(item);
```

Hàm này bỏ qua tham số `current` và ghi vào trạng thái ngoài. Khi framework tạo nhiều accumulator, dữ liệu sẽ không nằm ở những vùng cần thiết để `combiner` gộp.

### 4.2. Một phần tử phải được tính đúng một lần trong logic tích lũy

Với bộ đếm và tổng, mỗi phần tử hợp lệ thường đóng góp:

```java
void add(Sale sale) {
    count++;
    total += sale.amount();
}
```

Ví dụ giả định đây là phương thức của một lớp accumulator có trường `count` và `total`, dùng kiểu `Sale` đã nêu ở mục 1.

Nếu đầu vào cần loại dữ liệu không hợp lệ, có thể lọc trước `collect`:

```java
SalesSummary summary = sales.stream()
    .filter(sale -> sale.amount() > 0)
    .collect(summaryCollector);
```

`summaryCollector` sẽ được khai báo trong ví dụ hoàn chỉnh. Điều kiện lọc rõ ràng ở pipeline giúp accumulator chỉ tập trung vào nhiệm vụ tích lũy. Trong một collector tùy chỉnh, việc bỏ qua phần tử cũng có thể là quy tắc hợp lệ, nhưng cần được ghi rõ và nhất quán với phép gộp.

### 4.3. Giữ vùng tích lũy ở trạng thái hợp lệ

Hãy xác định các bất biến (*invariants*) cho `A`. Ví dụ: `count >= 0`; `total` là tổng tiền của những phần tử đã đi qua; không có phần tử được giữ hai lần trừ khi nghiệp vụ yêu cầu.

Đối với số nguyên, `long` có thể tràn. Dùng `Math.addExact` hoặc kiểu số lớn hơn nếu nghiệp vụ không cho phép tràn; nhưng cần hiểu rằng việc tính toán song song có thể gộp các phần theo thứ tự khác nhau. Khi cần bảo đảm kết quả đúng cho mọi dữ liệu kể cả tổng vượt giới hạn trung gian, hãy dùng biểu diễn đủ rộng, ví dụ `BigInteger`.

## 5. Combiner: gộp hai trạng thái tích lũy

**Combiner** là một `BinaryOperator<A>`:

```java
BinaryOperator<A> combiner();
```

Nó nhận hai trạng thái `A` đã chứa dữ liệu và trả lại **một trạng thái tích lũy tương đương với việc xử lý tất cả phần tử của cả hai phần**.

Ví dụ với danh sách:

```java
BinaryOperator<List<String>> mergeLists = (left, right) -> {
    left.addAll(right);
    return left;
};
```

Lưu ý: combiner của `Collector` **phải trả `A`**, khác với combiner dạng `BiConsumer<R, R>` của overload `Stream.collect` ba đối số.

### 5.1. Vì sao cần combiner ngay cả khi thường chạy tuần tự?

Framework có thể không cần gọi combiner trong một lượt collect tuần tự. Nhưng để một Collector hoạt động đúng khi bị phân chia, combiner phải có sẵn và hợp lệ.

Giả sử một nguồn bốn số được chia:

```text
Nhánh trái             Nhánh phải
[10, 20]               [30, 40]
   │                       │
   ▼                       ▼
A1: sum=30             A2: sum=70
   └──────── combine ───────┘
              │
              ▼
        A: sum=100
              │
              ▼
        finisher → 100
```

Combiner dùng cho thống kê:

```java
static final class MutableStats {
    long count;
    long total;

    MutableStats merge(MutableStats other) {
        this.count += other.count;
        this.total += other.total;
        return this;
    }
}
```

Nếu bỏ qua `other.total` hoặc `other.count`, kết quả song song sẽ thiếu dữ liệu dù ví dụ tuần tự có thể vẫn đúng.

### 5.2. Gộp đúng nghĩa, không chỉ trả một nhánh

**Sai:**

```java
(left, right) -> left // Làm mất dữ liệu trong right.
```

**Đúng:**

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

Dạng đúng dành cho accumulator kiểu `List<T>`. Với thống kê nhiều trường, phải gộp **tất cả các trường đóng góp vào kết quả**.

Sau khi một vùng đã được truyền cho combiner hoặc finisher, các quy tắc Collector hạn chế việc tiếp tục dùng lại vùng đó. Đừng lưu tham chiếu accumulator ở bên ngoài rồi sửa nó sau khi collect hoàn tất.

### 5.3. Tính kết hợp và thứ tự

Hợp đồng Collector yêu cầu phép gộp thỏa **tính kết hợp về kết quả**:

```text
combine(combine(A, B), C)
              ≈
combine(A, combine(B, C))
```

Hai vế phải cho kết quả tương đương khi đã áp dụng `finisher`, vì framework có thể chọn cây gộp khác nhau.

Với tổng số nguyên nằm trong phạm vi biểu diễn, phép cộng thỏa điều kiện. Với danh sách giữ thứ tự, phép nối danh sách cũng có tính kết hợp **nếu giữ đúng thứ tự nhánh trái rồi nhánh phải**.

Không phải cứ dùng phép toán bất kỳ là hợp lệ. Ví dụ lấy **trung bình của hai trung bình** không có trọng số sẽ sai khi hai phần có số phần tử khác nhau:

```text
Nhánh A: [10, 20]  → average = 15, count = 2
Nhánh B: [90]      → average = 90, count = 1

Sai: (15 + 90) / 2 = 52.5
Đúng: (10 + 20 + 90) / 3 = 40
```

Với bài toán trung bình, accumulator nên giữ **`sum` và `count`**; combiner cộng hai tổng và hai bộ đếm; finisher mới chia. Đây là ví dụ cho thấy thiết kế kiểu `A` quyết định độ đúng.

**Chú ý:** phép cộng `double` có sai số làm tròn và không hoàn toàn kết hợp về mặt bit. Vì vậy kết quả số thực có thể khác đôi chút khi thứ tự cộng thay đổi, đặc biệt khi chạy song song. Đừng dùng phép bằng tuyệt đối giữa hai kết quả `double` như một tiêu chuẩn tổng quát.

## 6. Finisher: biến A thành R

**Finisher** là `Function<A, R>`:

```java
Function<A, R> finisher();
```

Nó nhận trạng thái tích lũy đã hoàn thành và tạo **kết quả mà người gọi cần**.

Ví dụ trạng thái giữ hai trường, kết quả là record:

```java
record Summary(long count, long total) {}

static final class MutableStats {
    long count;
    long total;
}

Function<MutableStats, Summary> finish =
    stats -> new Summary(stats.count, stats.total);
```

Ở đây `A = MutableStats` là kiểu mutable, còn `R = Summary` là record với các trường final. Người gọi nhận một bản kết quả đơn giản thay vì vùng tích lũy có thể bị chỉnh sửa.

### 6.1. Finisher có thể giữ nguyên A

Đôi khi kết quả cuối chính là vùng tích lũy:

```java
Collector<String, ArrayList<String>, ArrayList<String>> toArrayList =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Overload ba thành phần của `Collector.of` tạo collector với **identity finisher**: `A` và `R` là cùng kiểu, kết quả cuối là chính vùng tích lũy.

Điều này khác với việc trả danh sách không thể sửa:

```java
Collector<String, ArrayList<String>, List<String>> toImmutableList =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        List::copyOf
    );
```

Trong ví dụ thứ hai, `A = ArrayList<String>`, `R = List<String>` và finisher tạo một danh sách không thể sửa bằng `List.copyOf`. Phương thức này không chấp nhận phần tử `null`, vì vậy nguồn chứa `null` sẽ cần chính sách xử lý riêng.

### 6.2. Không dùng finisher làm nơi có tác động phụ bắt buộc

Khi Collector có `IDENTITY_FINISH`, framework được phép bỏ qua việc gọi hàm hoàn tất. Số lần hoặc thời điểm đánh giá các bước nội bộ cũng không nên được dùng để kích hoạt tác vụ nghiệp vụ ngoài việc tạo kết quả.

Tránh dựa vào finisher để gửi thông báo, ghi nhật ký thanh toán hoặc tự ý thay đổi một dịch vụ bên ngoài. Nếu nghiệp vụ phải có hành động sau khi thu thập, hãy thực hiện **sau lời gọi `collect`** dựa trên kết quả đã nhận.

### 6.3. Finisher cho báo cáo tổng hợp

Ví dụ accumulator chứa `sum` và `count`, còn kết quả cần thêm trung bình:

```java
record AverageReport(long count, long total, double average) {}

Function<MutableStats, AverageReport> finish = stats ->
    new AverageReport(
        stats.count,
        stats.total,
        stats.count == 0 ? 0.0 : (double) stats.total / stats.count
    );
```

Giá trị `0.0` khi `count == 0` là **quy tắc mặc định của ví dụ**, không phải trung bình toán học của tập rỗng. Nếu ứng dụng cần phân biệt tập rỗng, có thể trả `OptionalDouble` hoặc một kiểu báo cáo diễn đạt rõ trạng thái không có dữ liệu.

## 7. Viết Collector bằng Collector.of

`Collector.of` cung cấp factory method cho cả hai tình huống:

```java
// A cũng là R, finisher đồng nhất:
Collector.of(supplier, accumulator, combiner, characteristics...);

// A và R có thể khác nhau:
Collector.of(supplier, accumulator, combiner,
             finisher, characteristics...);
```

Ví dụ ghép chuỗi bằng `StringJoiner`:

```java
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

class JoiningCollectorExample {
    public static void main(String[] args) {
        Collector<String, StringJoiner, String> joining = Collector.of(
            () -> new StringJoiner(", "),
            StringJoiner::add,
            StringJoiner::merge,
            StringJoiner::toString
        );

        String text = Stream.of("An", "Bình", "Chi")
            .collect(joining);

        System.out.println(text); // An, Bình, Chi
    }
}
```

Phân tích:

| Thành phần | Biểu thức | Ý nghĩa |
| --- | --- | --- |
| Supplier | `() -> new StringJoiner(", ")` | Tạo vùng tích lũy có dấu phân cách. |
| Accumulator | `StringJoiner::add` | Thêm một chuỗi vào vùng hiện tại. |
| Combiner | `StringJoiner::merge` | Nối nội dung của hai vùng tích lũy. |
| Finisher | `StringJoiner::toString` | Tạo kết quả `String`. |

Trong dự án thực tế, `Collectors.joining(", ")` có sẵn và thường là lựa chọn tốt hơn. Tự viết collector ở đây để hiểu hợp đồng bên trong.

### 7.1. Khi nào nên dùng Collector.of?

`Collector.of` hữu ích khi:

- Cần một kết quả riêng gồm nhiều thống kê.
- Cần gộp dữ liệu theo quy tắc nghiệp vụ không thể diễn đạt thuận tiện bằng collector chuẩn.
- Cần kiểm soát rõ trạng thái tích lũy, cách gộp, kết quả cuối hoặc chính sách bất biến.
- Cần tái sử dụng cách tích lũy ở nhiều pipeline hoặc làm downstream collector của `groupingBy`.

Nếu `Collectors.toList`, `toCollection`, `joining`, `groupingBy`, `summingLong` hay `summarizingInt` đã đáp ứng đúng yêu cầu, ưu tiên chúng để giảm mã phải bảo trì.

## 8. Ví dụ đầy đủ: Collector báo cáo doanh thu

Bài toán: mỗi giao dịch có nhóm hàng và số tiền. Cần tổng số giao dịch và tổng doanh thu; sau đó tái sử dụng cùng Collector để thống kê theo từng nhóm hàng.

Ta thiết kế:

- `T = Sale`: dữ liệu đầu vào.
- `A = Metrics`: vùng mutable có `count` và `total`.
- `R = SalesReport`: record bất biến về mặt trường, chỉ chứa kết quả.

Lưu ví dụ dưới đây vào tệp `CollectorContractDemo.java` và chạy trên Java 17+:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CollectorContractDemo {
    record Sale(String category, long amount) {}
    record SalesReport(long count, long total) {}

    static final class Metrics {
        private long count;
        private long total;

        // ACCUMULATOR: tích lũy một phần tử Sale.
        void add(Sale sale) {
            count = Math.addExact(count, 1L);
            total = Math.addExact(total, sale.amount());
        }

        // COMBINER: gộp dữ liệu từ một vùng tích lũy khác.
        Metrics merge(Metrics other) {
            count = Math.addExact(count, other.count);
            total = Math.addExact(total, other.total);
            return this;
        }

        // FINISHER: chuyển trạng thái trung gian thành kết quả.
        SalesReport finish() {
            return new SalesReport(count, total);
        }
    }

    static Collector<Sale, Metrics, SalesReport> reportCollector() {
        return Collector.of(
            Metrics::new,     // SUPPLIER
            Metrics::add,     // ACCUMULATOR
            Metrics::merge,   // COMBINER
            Metrics::finish   // FINISHER
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("Sách", 120_000),
            new Sale("Thiết bị", 200_000),
            new Sale("Sách", 80_000),
            new Sale("Thiết bị", 150_000)
        );

        Collector<Sale, Metrics, SalesReport> collector =
            reportCollector();

        SalesReport total = sales.stream()
            .collect(collector);

        SalesReport totalParallel = sales.parallelStream()
            .collect(collector);

        Map<String, SalesReport> byCategory = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                collector
            ));

        System.out.println(total);
        // SalesReport[count=4, total=550000]

        System.out.println(totalParallel);
        // SalesReport[count=4, total=550000]

        System.out.println(byCategory);
        // {Sách=SalesReport[count=2, total=200000],
        //  Thiết bị=SalesReport[count=2, total=350000]}
    }
}
```

**Vì sao cấu trúc này đúng về mặt cơ chế?**

1. `Metrics::new` tạo một trạng thái độc lập, `count=0` và `total=0`.
2. `Metrics::add` ghi một `Sale` vào đúng trạng thái được truyền cho nó.
3. `Metrics::merge` gộp hai trạng thái theo phép cộng của `count` và `total`, rồi trả trạng thái đã gộp.
4. `Metrics::finish` tạo `SalesReport`, giúp người gọi không phải làm việc với vùng tích lũy mutable.
5. Cùng một đối tượng **Collector** có thể tái sử dụng giữa các lời gọi `collect` vì mỗi lượt lấy vùng tích lũy mới từ supplier; không tái sử dụng **Stream** sau terminal operation.

Trong ví dụ, dữ liệu có số tiền không âm và kết quả nằm trong phạm vi `long`. `Math.addExact` giúp phát hiện tràn số ở từng bước cộng. Với dữ liệu có số âm và số dương rất lớn, các thứ tự gộp có thể khác nhau về việc phát hiện tràn trung gian; nếu cần tính tổng toán học độc lập thứ tự cho mọi số `long`, dùng accumulator kiểu `BigInteger` hoặc một biểu diễn đủ rộng.

### 8.1. Diễn giải hai nhánh của ví dụ

Nếu framework chia bốn giao dịch thành hai phần:

```text
Phần 1:
  Sách 120000
  Thiết bị 200000
  → Metrics(count=2, total=320000)

Phần 2:
  Sách 80000
  Thiết bị 150000
  → Metrics(count=2, total=230000)

combiner:
  count = 2 + 2 = 4
  total = 320000 + 230000 = 550000

finisher:
  SalesReport(count=4, total=550000)
```

Đây là **một cách phân chia có thể xảy ra**, không phải quy định rằng Stream phải tạo đúng hai nhánh hoặc gọi combiner đúng một lần.

### 8.2. Dùng collector làm downstream của groupingBy

`Collectors.groupingBy(Sale::category, TreeMap::new, collector)` dùng classifier `Sale::category` để chọn nhóm, rồi áp dụng collector đã viết cho mỗi nhóm.

Lợi ích là tách hai mối quan tâm:

- **Nhóm nào?** Do `groupingBy` quyết định.
- **Mỗi nhóm tích lũy ra sao?** Do `collector` của chúng ta quyết định.

Vì vậy một collector tự viết tốt thường dễ kết hợp với collector chuẩn, thay vì phải tự xây lại toàn bộ logic nhóm, map và bộ đếm.

## 9. Hợp đồng correctness: đồng nhất, kết hợp và tương đương

Một Collector không được xem là đúng chỉ vì trả kết quả đúng cho một Stream tuần tự nhỏ. Java cho phép **chia nguồn**, tích lũy từng phần và **gộp theo các cây khác nhau**. Vì vậy các thành phần phải tuân thủ hợp đồng.

### 9.1. Identity constraint

Một vùng tích lũy rỗng do `supplier` tạo không được làm thay đổi kết quả khi gộp:

```text
a = một trạng thái hợp lệ sau khi tích lũy
empty = supplier.get()

finisher(combiner(a, empty)) ≈ finisher(a)
```

Nếu collector nối danh sách theo thứ tự, `combiner(a, empty)` phải giữ nguyên trình tự phần tử có trong `a`.

Ví dụ sai:

```java
// Sai: supplier khởi tạo count=1 nên có thể tăng thừa khi chia việc.
Supplier<MutableStats> wrongSupplier = () -> {
    MutableStats stats = new MutableStats();
    stats.count = 1;
    return stats;
};
```

### 9.2. Associativity constraint

Kết quả phải tương đương dù nhóm phần dữ liệu theo cách nào, miễn là vẫn tôn trọng các bảo đảm thứ tự mà collector yêu cầu:

```text
finisher(combine(combine(A, B), C))
                  ≈
finisher(combine(A, combine(B, C)))
```

Trên dữ liệu đếm và tổng, gộp từng phần bằng cộng hợp lệ trong miền biểu diễn phù hợp. Trên chuỗi có thứ tự, combiner phải nối dữ liệu theo đúng chiều; đổi chiều `right + left` trong một nhánh sẽ tạo kết quả sai dù vẫn “đã nối đủ các phần tử”.

### 9.3. Kết quả tuần tự và song song phải tương đương

Với cùng đầu vào, kết quả từ:

```java
R sequential = data.stream().collect(collector);
R parallel = data.parallelStream().collect(collector);
```

phải tương đương theo hợp đồng Collector, với giả định dữ liệu, hàm tích lũy và phép toán đáp ứng các yêu cầu cần thiết. Đoạn mã này là **ký hiệu tổng quát**, trong chương trình thực tế phải khai báo `data`, `collector` và kiểu `R`.

Nếu collector có `UNORDERED`, tính tương đương cho phép thứ tự gặp phần tử không quan trọng. Nếu collector yêu cầu giữ thứ tự, combiner và kết quả phải tôn trọng thứ tự đó.

### 9.4. Đừng để logic phụ thuộc số lần gọi

Framework không cam kết rằng:

- `supplier` chỉ được gọi một lần.
- `accumulator` chỉ chạy trên một thread.
- `combiner` luôn được gọi hoặc được gọi đúng số lần dự đoán.
- Một phần tử sẽ được xử lý theo thứ tự thời gian trùng với thứ tự đầu vào khi pipeline chạy song song.

Thiết kế Collector dựa trên **ngữ nghĩa của kết quả**, không dựa trên việc in log hay đếm số lần gọi các hàm nội bộ.

## 10. Ba Characteristics và ý nghĩa chính xác

`Collector.Characteristics` là enum mô tả những bảo đảm mà framework có thể tận dụng:

| Đặc tính | Ý nghĩa | Điểm cần tránh |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher là phép đồng nhất: kiểu `A` có thể được dùng trực tiếp làm `R`. | Không khai báo nếu finisher tạo bản sao, biến đổi hoặc trả kiểu khác. |
| `UNORDERED` | Kết quả Collector không phụ thuộc việc giữ *encounter order* của nguồn. | Không khai báo cho danh sách mà thứ tự phần tử quan trọng. |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên cùng một vùng tích lũy mà vẫn đúng. | Không khai báo cho `ArrayList` hoặc bộ đếm `long` mutable thiếu đồng bộ. |

Các đặc tính này **là hợp đồng**, không phải công tắc “tăng tốc”.

### 10.1. IDENTITY_FINISH

Với overload `Collector.of(supplier, accumulator, combiner)`, finisher đồng nhất được cung cấp ngầm định. Còn trong ví dụ `Metrics → SalesReport`, finisher chuyển từ một lớp mutable sang record, nên **không** khai báo `IDENTITY_FINISH`.

Ngay cả khi `A` và `R` trùng kiểu khai báo, không được khai báo `IDENTITY_FINISH` nếu finisher có hành động thực sự, chẳng hạn tạo bản sao không thể sửa.

### 10.2. UNORDERED không có nghĩa phần tử được trộn ngẫu nhiên

Nếu kết quả chỉ là tổng hoặc bộ đếm và không phụ thuộc thứ tự, một collector **có thể** công bố `UNORDERED` nếu các thành phần thực sự đáp ứng hợp đồng.

Ví dụ với kết quả là `List<String>` cần hiển thị theo thứ tự đầu vào, không nên khai báo `UNORDERED`: một danh sách có đủ phần tử nhưng đảo vị trí chưa chắc tương đương về nghiệp vụ.

`UNORDERED` cũng khác phương thức `Stream.unordered()`: một bên công bố đặc tính **của collector**, bên kia bỏ yêu cầu về thứ tự gặp phần tử **của stream**.

### 10.3. CONCURRENT cần accumulator an toàn đồng thời

`CONCURRENT` cho phép nhiều luồng gọi accumulator với **cùng một kết quả container**. Khi collector đồng thời không có `UNORDERED`, việc tích lũy đồng thời vào cùng container chỉ được áp dụng theo hợp đồng nếu Stream cũng không có thứ tự.

Một ví dụ collector chuẩn là `Collectors.groupingByConcurrent(...)`, có đặc tính đồng thời và không có thứ tự. Khi làm việc với map, việc dùng `ConcurrentHashMap` không tự động khiến logic cập nhật những giá trị mutable bên trong trở nên an toàn. Cần xem toàn bộ đường cập nhật của accumulator.

**Quan trọng:** không đặt `CONCURRENT` **không có nghĩa** Collector của bạn không thể được sử dụng trong `parallelStream()`. Framework vẫn có thể tạo nhiều container độc lập và gộp bằng combiner. Collector `Metrics` trong mục 8 áp dụng đúng cơ chế đó.

## 11. Collector.of khác Stream.collect ba đối số

Java có hai cách biểu diễn trực tiếp logic tích lũy, nhưng chữ ký **khác nhau**.

### 11.1. Stream.collect nhận ba hàm

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
);
```

Ví dụ:

```java
List<String> result = Stream.of("An", "Bình", "Chi")
    .collect(
        ArrayList::new,
        List::add,
        List::addAll
    );
```

Ở đây combiner là **`BiConsumer<R,R>` trả `void`**, dùng để thay đổi container kết quả.

### 11.2. Collector.of nhận combiner trả A

```java
Collector<String, ArrayList<String>, ArrayList<String>> toList =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );

ArrayList<String> result = Stream.of("An", "Bình", "Chi")
    .collect(toList);
```

Ở đây combiner là **`BinaryOperator<A>`**, phải trả container đã gộp. `Collector.of` còn có thể nhận **finisher** và **characteristics**, vì vậy phù hợp để đóng gói thành thành phần tái sử dụng và kết hợp downstream.

### 11.3. Primitive stream cũng có collect riêng

`IntStream.collect` có dạng:

```java
<R> R collect(
    Supplier<R> supplier,
    ObjIntConsumer<R> accumulator,
    BiConsumer<R, R> combiner
);
```

`LongStream` và `DoubleStream` có các biến thể với `ObjLongConsumer` và `ObjDoubleConsumer`. Những API này xử lý số nguyên thủy mà không cần wrapper. Nếu cần dùng một `Collector<T,A,R>` chuẩn với `IntStream`, có thể chuyển sang `Stream<Integer>` bằng `boxed()`, nhưng điều đó phát sinh boxing tại ranh giới API.

## 12. Collector chuẩn đã chứa những thành phần này ra sao?

Khi dùng collector có sẵn, ta vẫn đang sử dụng mô hình bốn thành phần.

| Collector | Trạng thái tích lũy theo ý tưởng | Kết quả | Gợi ý |
| --- | --- | --- | --- |
| `Collectors.toCollection(ArrayList::new)` | Danh sách có thể thay đổi | Một `ArrayList` | Khi cần rõ loại collection. |
| `Collectors.toList()` | Một dạng tích lũy danh sách | `List<T>` | Không cam kết cụ thể về loại hoặc tính sửa đổi được. |
| `Collectors.joining(", ")` | Bộ tích lũy chuỗi | `String` | Tránh tự viết combiner cho ghép chuỗi. |
| `Collectors.summingLong(...)` | Trạng thái tổng số | `Long` | Tổng kiểu `long`. |
| `Collectors.summarizingLong(...)` | Thống kê count/sum/min/max | `LongSummaryStatistics` | Nhiều đại lượng cùng lúc. |
| `Collectors.groupingBy(...)` | Cấu trúc nhóm và accumulator cho từng nhóm | `Map<K,D>` | Có thể ghép với downstream collector. |
| `Collectors.toMap(...)` | Map các khóa và giá trị | `Map<K,V>` | Cần chính sách khóa trùng khi có thể va chạm. |
| `Collectors.collectingAndThen(downstream, finisher)` | Trạng thái của downstream | Đầu ra của finisher mới | Biến đổi kết quả collector đã có. |

Bảng trình bày **ý tưởng tích lũy**, không khẳng định kiểu `A` nội bộ cụ thể của từng collector chuẩn; triển khai có thể thay đổi theo JDK.

### 12.1. collectingAndThen: bổ sung finisher

Ví dụ muốn tạo danh sách không thể sửa:

```java
List<String> immutable = Stream.of("An", "Bình")
    .collect(Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    ));
```

`Collectors.toList()` tích lũy phần tử, còn `List::copyOf` biến kết quả thành danh sách không thể sửa. Trong thực tế, nếu chỉ cần một danh sách không thể sửa, `Stream.toList()` (Java 16+) hoặc `Collectors.toUnmodifiableList()` (Java 10+) cũng có thể đáp ứng, với lưu ý khác nhau về xử lý `null`.

Vì finisher thêm này có công việc thực sự, không được giả định kết quả collector mới có `IDENTITY_FINISH`.

### 12.2. teeing: tổng hợp hai kết quả rồi hoàn tất

Từ Java 12, `Collectors.teeing` có thể dùng hai collector rồi hợp nhất kết quả:

```java
record Summary(long count, long amount) {}

Summary result = sales.stream()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::amount),
        Summary::new
    ));
```

Ví dụ dùng `Sale` đã khai báo ở đầu bài. `teeing` giữ kết quả của hai nhánh thống kê và áp dụng hàm hợp nhất sau cùng. Đây là cách dùng công cụ sẵn có để khỏi viết accumulator và combiner thủ công khi nhu cầu vừa khớp.

## 13. Collector và reduce: điểm giống và khác

`reduce` và `collect` đều là phép kết thúc giúp tổng hợp Stream, nhưng mô hình khác nhau:

- `reduce` biểu diễn phép gộp các giá trị theo toán tử kết hợp, thường hướng đến một giá trị bất biến hoặc một phép tính.
- `collect` thường sử dụng **container tích lũy mutable**, với supplier và accumulator riêng; phù hợp tạo collection, map hoặc cấu trúc thống kê phức tạp.

Tính tổng:

```java
long total = sales.stream()
    .mapToLong(Sale::amount)
    .sum();
```

Thống kê nhiều trường:

```java
SalesReport report = sales.stream()
    .collect(reportCollector);
```

Không dùng một danh sách mutable chia sẻ làm **identity** cho `reduce` rồi thêm phần tử vào chính identity đó. Khi Stream bị chia, nhiều nhánh có thể cùng tham chiếu đối tượng này và phá hỏng logic. Nếu mục tiêu là tích lũy mutable, hãy dùng `collect` với supplier tạo container mới.

Ví dụ rủi ro:

```java
// Tránh mẫu reduce này với identity mutable:
// List<String> sharedIdentity = new ArrayList<>();
// List<String> result = words.parallelStream().reduce(
//     sharedIdentity,
//     (list, word) -> { list.add(word); return list; },
//     (left, right) -> { left.addAll(right); return left; }
// );
```

`words` trong ví dụ là nguồn `Stream<String>` được giả định; đoạn mã được chú thích để minh họa điều không nên làm.

## 14. Đúng trước, tối ưu sau: hiệu năng và tài nguyên

Một Collector đúng có thể vẫn tốn bộ nhớ hoặc CPU. Độ phức tạp phụ thuộc trạng thái `A`, phương pháp tích lũy, cách gộp và số lượng kết quả.

### 14.1. Bộ nhớ của accumulator

- Danh sách giữ tất cả phần tử cần bộ nhớ tỷ lệ với số phần tử.
- Bộ đếm và tổng thường chỉ cần một lượng trạng thái cố định.
- `groupingBy` có thể cần map với nhiều khóa và accumulator cho từng nhóm.
- Collector tạo bản sao trong finisher có thể tạm thời giữ cả container trung gian và kết quả cuối.

Chọn `A` vừa đủ để phục vụ `R`. Nếu chỉ cần tổng tiền, không cần lưu mọi giao dịch trong danh sách rồi mới cộng ở finisher.

### 14.2. Chi phí combiner trong parallel stream

Với nguồn lớn có thể chia tốt nhờ `Spliterator` và tác vụ tích lũy phù hợp, song song có thể giúp tăng tốc. Nhưng nếu combiner phải nối những danh sách rất lớn hoặc sao chép toàn bộ map liên tục, việc gộp có thể làm tăng chi phí đáng kể.

Không tự bật `CONCURRENT` để tránh combiner khi accumulator chưa an toàn đồng thời. Cũng không nên giả định `parallelStream` luôn nhanh hơn. Việc quyết định cần dựa vào đo đạc theo khối lượng dữ liệu, kích thước nhóm và dạng collector thực tế.

### 14.3. Tài nguyên I/O không được collect tự đóng

Nếu nguồn là `Files.lines(path)`, phải đóng Stream:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class CollectLinesExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (Stream<String> lines = Files.lines(path)) {
            List<String> nonBlank = lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .collect(Collectors.toList());

            System.out.println(nonBlank.size());
        }
    }
}
```

Ví dụ giả định `data.txt` tồn tại. Phép kết thúc `collect` không tự động đóng nguồn I/O; `try-with-resources` mới quản lý vòng đời tài nguyên đó.

## 15. Lỗi thiết kế Collector thường gặp

| Sai lầm | Tại sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| Supplier trả về một list dùng chung | Các lượt tích lũy không độc lập, dễ trùng dữ liệu hoặc race. | Tạo container mới trong mỗi lần gọi supplier. |
| Accumulator ghi vào biến bên ngoài thay vì tham số `A` | Combiner không nhìn thấy dữ liệu đúng của mỗi nhánh. | Chỉ cập nhật vùng tích lũy được truyền vào. |
| Combiner luôn trả `left` mà không gộp `right` | Mất dữ liệu của các phần bị chia. | Gộp mọi trường rồi trả trạng thái hợp lệ. |
| Combiner lấy trung bình hai trung bình không có trọng số | Kết quả phụ thuộc cách chia. | Giữ `sum` và `count`, chỉ tính trung bình trong finisher. |
| Supplier khởi tạo count bằng 1 | Không có trạng thái rỗng đúng. | Bắt đầu từ count=0 và identity phù hợp. |
| Combiner đảo thứ tự trong collector có yêu cầu ordered | Kết quả song song có thể khác tuần tự. | Bảo toàn thứ tự khi nối kết quả từng phần. |
| Khai báo `IDENTITY_FINISH` khi finisher chuyển kiểu | Framework có thể bỏ qua finisher và trả sai kiểu. | Chỉ khai báo khi thực sự là phép đồng nhất. |
| Khai báo `CONCURRENT` cho `ArrayList` hoặc bộ đếm không đồng bộ | Nhiều luồng ghi cùng container không an toàn. | Dùng collector không concurrent hoặc triển khai trạng thái đồng thời đúng. |
| Khai báo `UNORDERED` dù thứ tự danh sách quan trọng | Có thể mất bảo đảm về thứ tự. | Không khai báo đặc tính không được dữ liệu đáp ứng. |
| Dựa vào `println` trong accumulator/combiner để quyết định nghiệp vụ | Lời gọi có thể diễn ra ở thứ tự và số lần khác nhau. | Thực hiện hành động nghiệp vụ sau collect. |
| Thu mọi phần tử vào danh sách để cuối cùng chỉ tính tổng | Tốn bộ nhớ không cần thiết. | Giữ accumulator `sum`, hoặc dùng `summingLong` / `mapToLong(...).sum()`. |
| Xử lý nguồn I/O nhưng không đóng Stream | Rò rỉ tài nguyên. | `try-with-resources`. |

## 16. Tự kiểm tra

1. Trong `Collector<Sale, Metrics, SalesReport>`, kiểu `T`, `A` và `R` lần lượt biểu diễn điều gì?
2. `supplier` cần tạo trạng thái như thế nào để một collector dùng đúng cho nhiều vùng tích lũy?
3. Vì sao `accumulator` dùng `BiConsumer<A,T>`, còn `combiner` dùng `BinaryOperator<A>`?
4. Nếu `combiner(a,b)` trả về `a` mà không gộp `b`, lỗi thường bộc lộ rõ khi nào?
5. Vì sao không nên tính trung bình của các trung bình không có trọng số khi gom dữ liệu từ nhiều nhánh?
6. Khi nào `finisher` có thể là phép đồng nhất? Đặc tính nào mô tả điều đó?
7. Một collector không có `CONCURRENT` có được dùng với `parallelStream()` không? Vì sao?
8. `Collector.of` ba thành phần và `Stream.collect` ba đối số khác nhau ở kiểu của combiner ra sao?
9. Tại sao `Collectors.collectingAndThen` thường không có `IDENTITY_FINISH`?
10. Collector có thể làm nguồn `Files.lines` tự đóng sau `collect` không?

**Đối chiếu nhanh:** (1) phần tử, trạng thái tích lũy, kết quả; (2) trạng thái mới độc lập và đóng vai trò identity; (3) accumulator cập nhật container, combiner trả container sau khi gộp; (4) khi dữ liệu bị chia, thường là xử lý song song; (5) các nhánh có số phần tử khác nhau; (6) khi `A=R` và không cần biến đổi, `IDENTITY_FINISH`; (7) có, framework dùng container riêng rồi gộp; (8) `BinaryOperator<A>` trả `A` so với `BiConsumer<R,R>` trả `void`; (9) có finisher bổ sung thật sự; (10) không, phải quản lý vòng đời tệp.

## 17. Bài tập thực hành

**Bài 1 — Đếm và tổng.** Viết `Collector<Integer, ?, Summary>` với `Summary(long count, long sum)`. Dùng lớp accumulator giữ count và sum, triển khai bốn thành phần bằng `Collector.of`; kiểm tra với danh sách `[1, 2, 3, 4]`.

**Bài 2 — Ghép chuỗi.** Dùng `StringJoiner` tạo collector ghép các từ bằng ký tự `" | "`. Chạy trên Stream tuần tự và song song, so sánh kết quả khi nguồn là một `List` có thứ tự.

**Bài 3 — Sai combiner.** Thay combiner của collector đếm bằng `(left, right) -> left`. Giải thích vì sao trường hợp tuần tự có thể cho kết quả đúng nhưng song song có thể thiếu phần tử.

**Bài 4 — Tính trung bình.** Xây accumulator lưu `long count` và `long sum`, finisher tạo một record chứa `OptionalDouble` hoặc một kiểu thể hiện nguồn rỗng. Vì sao cần lưu hai thông số đến cuối?

**Bài 5 — Danh sách bất biến.** Viết collector dùng `ArrayList` làm `A` và `List.copyOf` làm finisher. Thử thêm phần tử vào `R` sau collect và giải thích đặc tính `IDENTITY_FINISH` có thích hợp không.

**Bài 6 — Grouping downstream.** Tái sử dụng collector của Bài 1 làm downstream của `Collectors.groupingBy` để tính count và sum theo nhãn chẵn/lẻ.

**Bài 7 — Review đặc tính.** Với accumulator là `HashMap<String, Long>` và combiner gộp từng khóa, phân tích xem có được khai báo `CONCURRENT` không. Cần điều kiện gì để cùng một map được cập nhật an toàn bởi nhiều luồng?

Gợi ý triển khai Bài 1:

```java
record Summary(long count, long sum) {}

static final class Acc {
    long count;
    long sum;

    void add(int n) {
        count++;
        sum += n;
    }

    Acc merge(Acc right) {
        count += right.count;
        sum += right.sum;
        return this;
    }

    Summary finish() {
        return new Summary(count, sum);
    }
}

Collector<Integer, Acc, Summary> collector = Collector.of(
    Acc::new,
    Acc::add,
    Acc::merge,
    Acc::finish
);
```

Đoạn mã trên cần đặt các khai báo `record` và `class` trong một lớp Java phù hợp; biến `collector` có thể nằm trong một phương thức. Với dữ liệu lớn, hãy cân nhắc tràn `long` và quy tắc xử lý lỗi.

## 18. Ghi nhớ cốt lõi

- **`Collector<T,A,R>`** mô tả cách biến nhiều phần tử kiểu `T` thành kết quả `R` qua trạng thái trung gian `A`.
- **`supplier`** tạo vùng tích lũy mới với trạng thái ban đầu đóng vai trò identity; **`accumulator`** thêm từng phần tử vào vùng đó.
- **`combiner`** gộp hai vùng tích lũy và phải giữ nguyên toàn bộ đóng góp từ các nhánh; việc gộp phải **có tính kết hợp về kết quả**.
- **`finisher`** chuyển trạng thái `A` thành kết quả `R`; khi `A` chính là `R` và không cần chuyển đổi, collector có thể có `IDENTITY_FINISH`.
- **`UNORDERED` và `CONCURRENT`** là bảo đảm thực sự về ngữ nghĩa và an toàn đồng thời, không phải mẹo tăng tốc.
- **`Collector.of` và overload ba tham số của `Stream.collect`** dùng combiner với chữ ký khác nhau; không hoán đổi trực tiếp mà bỏ qua khác biệt kiểu trả về.
- **Collector đúng phải hoạt động tương đương khi chia và gộp dữ liệu**. Không dựa vào số lần gọi các hàm nội bộ, không dùng biến mutable ngoài pipeline làm accumulator chia sẻ, không tự đánh dấu đặc tính thiếu căn cứ.
- Ưu tiên **`Collectors` có sẵn** khi chúng đáp ứng yêu cầu; tự viết collector khi cần trạng thái hoặc kết quả riêng. Việc tối ưu bộ nhớ, thực thi song song và quản lý tài nguyên phải dựa trên hợp đồng nguồn, `Spliterator` và phép thu thập thực tế trong **JAVA_STREAM_API**.
