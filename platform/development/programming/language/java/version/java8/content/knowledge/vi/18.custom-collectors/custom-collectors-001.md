# Collector<T, A, R>: ba kiểu đầu vào, tích lũy và kết quả trong Java Stream

## 1. Collector là gì? Vì sao có ba tham số kiểu?

`java.util.stream.Collector<T, A, R>` mô tả **một chiến lược mutable reduction**: nhận các phần tử của một Stream, tích lũy chúng vào một hoặc nhiều vùng chứa trung gian, kết hợp các vùng chứa khi cần, rồi tạo kết quả cuối. Interface này có từ Java 8 và vẫn là phần hiện hành của Stream API.

Ba tham số generic **không nhất thiết cùng kiểu**:

| Tham số | Tên | Ý nghĩa | Ví dụ bài tổng hợp đơn hàng |
| --- | --- | --- | --- |
| `T` | **Input element type** | Kiểu **mỗi phần tử** mà Stream đưa vào collector | `Sale` |
| `A` | **Mutable accumulation type** | Kiểu **vùng chứa trung gian** dùng để gom/trộn dữ liệu | `StatsAccumulator` |
| `R` | **Final result type** | Kiểu **kết quả trả về** từ `stream.collect(collector)` | `Summary` |

Ví dụ cụ thể:

```java
Collector<Sale, StatsAccumulator, Summary> collector = summaryCollector();
Summary result = sales.stream().collect(collector);
```

Đây là đoạn trích trong ví dụ hoàn chỉnh phía dưới, nơi `Sale`, `StatsAccumulator`, `Summary`, `summaryCollector()` và `sales` đã được định nghĩa.

**Phân biệt đúng:** `T` là một bản ghi bán hàng, `A` là bộ đếm/tổng tiền **có thể thay đổi trong quá trình xử lý**, còn `R` là bản tổng kết **đã hoàn thiện**. Không được coi `A` là “kiểu phần tử thứ hai” hay mặc định `A == R`.

Hình dung pipeline:

```text
Stream<Sale>                         T = Sale
    │ từng Sale
    ▼
supplier(): StatsAccumulator         A = StatsAccumulator (mới, rỗng)
    │
accumulator(A, T)                    cập nhật count và totalCents
    │
    ├── khi song song có thể có nhiều A độc lập
    │      A1 + A2 -> combiner(A1, A2) -> A
    ▼
finisher(A): Summary                 R = Summary (đầu ra cuối)
    │
    ▼
stream.collect(collector) -> Summary
```

Đối với nguồn rỗng, collector vẫn tạo kết quả từ trạng thái tích lũy rỗng theo hợp đồng của nó; ví dụ `Summary[count=0, totalCents=0]`. Khi chạy song song, số lần gọi supplier/combiner phụ thuộc cách Stream chia việc; không viết logic dựa vào số lời gọi cụ thể.

## 2. Năm phương thức của `Collector<T, A, R>`

Collector có **bốn hàm xử lý dữ liệu** và một tập đặc tính:

| Phương thức | Kiểu trả về | Vai trò |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Tạo một vùng chứa tích lũy mới, thường rỗng |
| `accumulator()` | `BiConsumer<A, T>` | Thêm một phần tử kiểu `T` vào vùng chứa `A` |
| `combiner()` | `BinaryOperator<A>` | Gộp hai vùng chứa `A`, trả lại một `A` |
| `finisher()` | `Function<A, R>` | Đổi trạng thái tích lũy `A` thành kết quả `R` |
| `characteristics()` | `Set<Collector.Characteristics>` | Công bố những bảo đảm về thứ tự, đồng thời và finisher |

Dưới đây là **khai báo giao diện rút gọn để đọc chữ ký**, không phải tệp Java độc lập cần tự định nghĩa lại:

```java
interface Collector<T, A, R> {
    Supplier<A> supplier();
    BiConsumer<A, T> accumulator();
    BinaryOperator<A> combiner();
    Function<A, R> finisher();
    Set<Collector.Characteristics> characteristics();
}
```

Ví dụ cụ thể cho `Collector<Sale, StatsAccumulator, Summary>`:

- `supplier()`: `StatsAccumulator::new` — mỗi lần được gọi phải tạo **một instance mới**. Tránh trả cùng một object được giữ trong biến `static`.
- `accumulator()`: `StatsAccumulator::add` — nhận (`StatsAccumulator`, `Sale`), cập nhật số lượng và tổng tiền.
- `combiner()`: `StatsAccumulator::merge` — nhận (`StatsAccumulator`, `StatsAccumulator`) và trả `StatsAccumulator` đã gộp.
- `finisher()`: `StatsAccumulator::finish` — nhận `StatsAccumulator`, tạo một `Summary` mới.
- `characteristics()`: trong ví dụ sẽ không công bố `CONCURRENT`, `UNORDERED` hay `IDENTITY_FINISH`; đặc biệt `A` và `R` khác kiểu nên finisher không phải identity.

### Điểm khác nhau giữa accumulator và combiner

`accumulator()` có kiểu **`BiConsumer<A,T>`**, nên thường là thao tác `void`: thêm **một phần tử đầu vào T** vào trạng thái đang có. `combiner()` có kiểu **`BinaryOperator<A>`**, nên trả về trạng thái `A`: gộp **hai kết quả trung gian cùng kiểu A**.

Không viết `combiner` chỉ lặp lại accumulator nếu hai toán hạng không phải cùng bản chất. Với ví dụ `Sale`, combiner không nhận `Sale` mà nhận hai bộ tổng hợp `StatsAccumulator`.

Một reducer tùy biến có thể dùng cùng `A` và `R`, nhưng khi cần đầu ra DTO bất biến, báo cáo hoặc cấu trúc bảo vệ khỏi sửa đổi, dùng `A != R` là cách thiết kế rõ ràng.

## 3. Cách tạo Collector tùy biến hiện hành bằng `Collector.of`

Thường không cần viết lớp `implements Collector<T,A,R>` đầy đủ. Factory `Collector.of(...)` (từ Java 8) giúp lắp ghép các thành phần.

Khi **A khác R**, dùng overload có finisher:

```java
Collector<Sale, StatsAccumulator, Summary> collector = Collector.of(
        StatsAccumulator::new,      // Supplier<A>
        StatsAccumulator::add,      // BiConsumer<A, T>
        StatsAccumulator::merge,    // BinaryOperator<A>
        StatsAccumulator::finish    // Function<A, R>
);
```

Đây là đoạn trích từ chương trình ở mục 5. Các method reference hoạt động vì chữ ký khớp vai trò:

```java
StatsAccumulator()                      // tạo A mới
void add(Sale sale)                     // cập nhật A với T
StatsAccumulator merge(StatsAccumulator other) // kết hợp A với A
Summary finish()                        // chuyển A thành R
```

Đoạn trên là **mô tả chữ ký phương thức** thuộc lớp `StatsAccumulator`, không phải khai báo Java hoàn chỉnh có thể tự biên dịch riêng.

Overload ngắn hơn dành cho **A = R** và không có bước chuyển kiểu cuối:

```java
Collector<String, List<String>, List<String>> mutableListCollector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.IDENTITY_FINISH
        );
```

Đoạn minh họa này cần import `java.util.*` và `java.util.stream.*`; nó tạo collector trả về chính danh sách mutable tích lũy, nên có thể có `IDENTITY_FINISH`. Không gắn `IDENTITY_FINISH` cho collector cần chuyển `A` thành một `R` thực sự khác kiểu.

**Khi nào không cần custom collector?** Nếu chỉ đếm, tính tổng, gom danh sách, phân nhóm đơn giản, nối chuỗi hoặc tính thống kê thông thường, ưu tiên các collector tiêu chuẩn như `counting()`, `summingLong()`, `toList()`, `groupingBy()`, `joining()` và `summarizingLong()`. Chỉ tự viết khi cần hành vi tổng hợp/phân phối/kết quả cụ thể mà cách có sẵn không đáp ứng rõ ràng.

## 4. Thiết kế ví dụ: Sale → StatsAccumulator → Summary

Ta cần tổng hợp doanh số:

- Mỗi `Sale(region, cents)` là **T**. `cents` có kiểu `long` để lưu số tiền theo đơn vị nhỏ nhất, tránh đưa sai số `double` vào ví dụ tài chính.
- `StatsAccumulator` là **A**: giữ `count` và `totalCents`; có thể sửa vì chỉ dùng nội bộ quá trình `collect`.
- `Summary(count, totalCents)` là **R**: một Java `record` chỉ chứa hai trường `long`, tạo snapshot kết quả không có setter.
- `supplier` tạo `StatsAccumulator` mới với hai trường `0`; `accumulator` tăng đếm/cộng tiền; `combiner` cộng hai trạng thái; `finisher` tạo record bất biến.

Trong chương trình dưới đây, `Math.addExact` được dùng để **phát hiện tràn số** bằng `ArithmeticException` thay vì âm thầm lấy kết quả sai khi tổng vượt phạm vi `long`. Với dữ liệu không gây tràn, phép cộng số nguyên có tính kết hợp và có phần tử đơn vị `0`, phù hợp khi chạy song song. Trong hệ thống thực tế, hãy quy định rõ cách xử lý overflow, dữ liệu âm/hoàn tiền, và đơn vị tiền tệ.

Việc dùng `record` và `Stream.toList()` yêu cầu Java 16+, do đó chương trình đầy đủ được đặt mục tiêu **Java 17 trở lên**. Bản thân `Collector.of`, `Stream.collect` và `Collector<T,A,R>` đã có từ Java 8 và vẫn được sử dụng.

## 5. Chương trình Java 17+ hoàn chỉnh, kiểm tra tuần tự, song song và rỗng

Tạo tệp tên **`CustomCollectorDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class CustomCollectorDemo {
    record Sale(String region, long cents) {}
    record Summary(long count, long totalCents) {}

    static final class StatsAccumulator {
        private long count;
        private long totalCents;

        void add(Sale sale) {
            count = Math.addExact(count, 1);
            totalCents = Math.addExact(totalCents, sale.cents());
        }

        StatsAccumulator merge(StatsAccumulator other) {
            count = Math.addExact(count, other.count);
            totalCents = Math.addExact(totalCents, other.totalCents);
            return this;
        }

        Summary finish() {
            return new Summary(count, totalCents);
        }
    }

    static Collector<Sale, StatsAccumulator, Summary> summaryCollector() {
        return Collector.of(
                StatsAccumulator::new,
                StatsAccumulator::add,
                StatsAccumulator::merge,
                StatsAccumulator::finish);
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Collector<Sale, StatsAccumulator, Summary> collector =
                summaryCollector();

        List<Sale> sales = List.of(
                new Sale("A", 1200),
                new Sale("B", 2500),
                new Sale("A", 800));

        Summary expected = new Summary(3, 4500);
        Summary sequential = sales.stream().collect(collector);
        Summary parallel = sales.parallelStream().collect(collector);
        Summary empty = Stream.<Sale>empty().collect(collector);

        require(expected.equals(sequential), "Sequential result");
        require(expected.equals(parallel), "Parallel result");
        require(new Summary(0, 0).equals(empty), "Empty result");

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);

        Map<String, Summary> grouped = sales.stream().collect(
                Collectors.groupingBy(Sale::region, TreeMap::new, collector));
        require(grouped.get("A").equals(new Summary(2, 2000)), "Group A");
        require(grouped.get("B").equals(new Summary(1, 2500)), "Group B");
        System.out.println("grouped=" + grouped);

        // Nguồn lớn để kiểm tra thêm quá trình kết hợp các partial results.
        List<Sale> large = IntStream.range(0, 10_000)
                .mapToObj(i -> new Sale("A", (i % 5) + 1))
                .toList();
        Summary largeExpected = new Summary(10_000, 30_000);

        require(largeExpected.equals(large.stream().collect(collector)),
                "Large sequential");
        for (int i = 0; i < 10; i++) {
            require(largeExpected.equals(large.parallelStream().collect(collector)),
                    "Large parallel " + i);
        }
        System.out.println("largeSequentialAndParallel=PASS");

        System.out.println("identityFinish=" + collector.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("ALL TESTS PASSED");
    }
}
```

Biên dịch và chạy:

```bash
javac CustomCollectorDemo.java
java CustomCollectorDemo
```

Kết quả chuẩn:

```text
sequential=Summary[count=3, totalCents=4500]
parallel=Summary[count=3, totalCents=4500]
empty=Summary[count=0, totalCents=0]
grouped={A=Summary[count=2, totalCents=2000], B=Summary[count=1, totalCents=2500]}
largeSequentialAndParallel=PASS
identityFinish=false
ALL TESTS PASSED
```

Giải thích các điểm cần quan sát:

1. `T = Sale`: mỗi bản ghi được chuyển cho `StatsAccumulator.add(Sale)`.
2. `A = StatsAccumulator`: giữ dữ liệu trung gian mutable. Pipeline tuần tự và song song có thể tạo **nhiều instance** qua `supplier`, nhưng dùng chúng độc lập và gộp bằng `merge`.
3. `R = Summary`: sau khi kết thúc, `finish` tạo record cuối. `record` cung cấp `equals`, `hashCode` và `toString` dựa trên thành phần, thuận tiện cho test; ví dụ không công bố đối tượng `A`.
4. `sequential` và `parallel` đều bằng `Summary(3, 4500)` vì tổng tiền 1200 + 2500 + 800 = 4500 và có 3 phần tử.
5. `empty` cho count và total bằng 0; nó **không** trả `null` hay `Optional.empty()` vì finisher của collector này tự xác định kiểu kết quả `Summary`.
6. `grouped` chứng minh một custom collector có thể làm downstream của `Collectors.groupingBy`. `TreeMap::new` bảo đảm thứ tự khóa theo so sánh tự nhiên; A có hai bản ghi tổng 2000, B có một bản ghi tổng 2500.
7. `largeSequentialAndParallel=PASS`: 10.000 phần tử có đơn giá lặp `1,2,3,4,5`, tổng bằng `30.000`. Test lặp 10 lượt song song để tăng khả năng phát hiện lỗi, nhưng **không chứng minh** mọi lỗi cạnh tranh đã bị loại bỏ.
8. `identityFinish=false` vì `StatsAccumulator` và `Summary` khác nhau và có bước biến đổi cuối.

**Bộ test đúng tiêu chí:** So cả tuần tự và song song với `expected` được tính độc lập, không chỉ so chúng với nhau vì cả hai có thể cùng sai. Một lần chạy đúng không khẳng định hiệu năng hoặc số lượng luồng được sử dụng.

## 6. Quan hệ giữa T, A, R và suy luận kiểu generic

### 6.1. Chữ ký của `Stream.collect(Collector)`

Trong `Stream<T>`, phương thức terminal operation có dạng:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

Vì vậy với `Stream<Sale>` và `Collector<Sale, StatsAccumulator, Summary>`, trình biên dịch suy ra kết quả là `Summary`. `? super T` trong tham số cho phép collector xử lý kiểu `T` hoặc một supertype phù hợp; đó là yêu cầu tương thích đầu vào, không làm thay đổi ý nghĩa ba tham số của collector.

Nếu một phương thức chỉ cần **nhận collector và trả kết quả**, không thao tác trực tiếp với accumulator, thường có thể **ẩn A bằng wildcard**:

```java
Collector<Sale, ?, Summary> collector = summaryCollector();
Summary result = sales.stream().collect(collector);
```

Đây là đoạn trích (cần các khai báo `Sale`, `Summary`, `sales` và `summaryCollector`). Dấu `?` nói rằng caller không cần biết kiểu tích lũy thực tế. Nó **không đồng nghĩa** `Object` và không có nghĩa accumulator là null.

### 6.2. Khi nào A = R và khi nào A khác R?

| T | A | R | Tình huống |
| --- | --- | --- | --- |
| `String` | `List<String>` | `List<String>` | Gom danh sách, trả chính container (có thể mutable) |
| `Sale` | `StatsAccumulator` | `Summary` | Gom count/tổng, tạo kết quả bất biến |
| `String` | `StringJoiner` | `String` | Gom chuỗi trong bộ tích lũy rồi xuất String |
| `Person` | `Map<String, List<Person>>` | `Report` | Phân nhóm nội bộ rồi tạo báo cáo riêng |

Khi `A == R`, finisher có thể là identity nếu thực sự trả chính container tương ứng; không phải lúc nào **cùng kiểu** cũng đồng nghĩa được phép công bố `IDENTITY_FINISH`. Nếu finisher tạo **bản sao cùng kiểu** để chặn chỉnh sửa, đó vẫn là phép biến đổi thực sự và **không** được công bố identity finish.

Khi `A != R`, cần finisher chuyển kiểu. Không cast ép `StatsAccumulator` thành `Summary` để né bước chuyển đổi: đó là sai kiểu và có thể gây `ClassCastException`.

### 6.3. Tránh raw type và đặt nhầm thứ tự generic

**Sai:**

```java
Collector raw = summaryCollector(); // raw type: mất kiểm tra kiểu generic
```

Trong một chương trình có thể biên dịch, khai báo `Collector` thô tạo cảnh báo unchecked khi sử dụng và che đi lỗi không tương thích. Giữ `Collector<Sale, StatsAccumulator, Summary>` nếu xây dựng collector hoặc `Collector<Sale, ?, Summary>` khi chỉ cần sử dụng.

**Sai về ý nghĩa:** `Collector<Summary, Sale, StatsAccumulator>` không thể thay cho `Collector<Sale, StatsAccumulator, Summary>`. Generic được đọc theo thứ tự **T → A → R**, không phải “input → output → accumulator”.

## 7. Hợp đồng quan trọng khi sử dụng Collector song song

`parallelStream()` được quyền chia đầu vào thành nhiều phần, gọi supplier cho nhiều vùng chứa, thu thập vào từng vùng, rồi dùng combiner gộp. Để kết quả vẫn tương đương với tuần tự, thiết kế Collector phải tuân thủ các luật:

### 7.1. Supplier tạo trạng thái mới, có đơn vị rỗng

`StatsAccumulator::new` trả về instance **mới** với count=0 và total=0. Trạng thái rỗng phải trung lập khi kết hợp:

```text
combine(partial, freshEmpty) ≡ partial
combine(freshEmpty, partial) ≡ partial    // trong ví dụ cộng số liệu
```

Ký hiệu `≡` là **tương đương về kết quả** (qua finisher), không nhất thiết phải là cùng một object theo `==`. Nếu supplier luôn trả cùng một container `static`, nhiều tác vụ có thể chia sẻ trạng thái và gây sai kết quả; điều đó vi phạm thiết kế collector không đồng thời của ví dụ.

### 7.2. Combiner phải bảo toàn kết quả khi đổi cách nhóm

Với ba partials A, B, C:

```text
combine(combine(A, B), C) ≡ combine(A, combine(B, C))
```

Đây là **associativity (tính kết hợp)**, cho phép giảm theo các cây gộp khác nhau mà kết quả vẫn tương đương. Trong ví dụ, combiner cộng count và totalCents theo từng trường, nên thỏa luật với dữ liệu nằm trong miền không tràn số.

Combiner **không nhất thiết phải giao hoán** (commutative): một collector nối chuỗi có thứ tự có thể cần giữ encounter order, ví dụ `"A" + "B"` khác `"B" + "A"`. Nếu thứ tự quan trọng, combiner phải bảo toàn cách nối theo thứ tự logic của dữ liệu và không gắn đặc tính `UNORDERED`.

### 7.3. Accumulator phải tương thích với cách gộp

Khi một phần tử được thêm trực tiếp vào partial accumulator, kết quả cuối phải tương đương với việc thêm phần tử đó vào một accumulator rỗng rồi kết hợp hai partials. Nếu combiner chỉ cộng count mà **quên totalCents**, collector có thể có vẻ đúng tuần tự (ít phải gọi combiner) nhưng sai song song.

Trong ví dụ:

```java
StatsAccumulator merge(StatsAccumulator other) {
    count = Math.addExact(count, other.count);
    totalCents = Math.addExact(totalCents, other.totalCents);
    return this;
}
```

Đây là một phương thức trong lớp `StatsAccumulator`, không phải tệp Java riêng. Nó trả `this` sau khi gộp đầy đủ hai trường; Stream không được tiếp tục sử dụng các accumulator cũ đã bị gộp theo cách làm thay đổi kết quả.

### 7.4. Non-concurrent vẫn có thể chạy parallel đúng

**Một Collector không có `CONCURRENT` vẫn có thể dùng với `parallelStream()`**. Stream framework quản lý các container trung gian sao cho mỗi container được xử lý riêng trong giai đoạn tích lũy, sau đó gộp lại. Vì vậy `StatsAccumulator` có thể dùng các trường `long` mutable mà không cần `AtomicLong`/lock **khi không chia sẻ cùng instance giữa các luồng**.

Đừng nhầm **collection song song** với **concurrent accumulation trên cùng một container**. Không gắn `CONCURRENT` chỉ vì muốn nhanh; đặc tính này yêu cầu cùng một container có thể nhận nhiều lời gọi accumulator đồng thời một cách an toàn.

### 7.5. Không dùng side effect vào dữ liệu nguồn

Collector tùy biến phải tôn trọng yêu cầu **non-interfering**: không sửa collection nguồn đang được Stream duyệt. Tránh phụ thuộc biến mutable toàn cục, logging như một phần điều kiện đúng, hoặc giả định accumulator luôn được gọi một số lần cố định. Thực hiện side effect nghiệp vụ sau khi đã có kết quả cuối nếu cần.

## 8. Ba đặc tính `Collector.Characteristics`

| Đặc tính | Ý nghĩa | Khi nào hợp lệ |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher là identity và có thể bị bỏ qua; cast từ `A` sang `R` phải hợp lệ | Chỉ khi chính accumulator là kết quả, không cần transform thực sự |
| `UNORDERED` | Collector không cam kết bảo toàn encounter order | Khi thứ tự đầu vào không ảnh hưởng ngữ nghĩa kết quả |
| `CONCURRENT` | Có thể gọi accumulator đồng thời trên **cùng container** | Chỉ khi container và accumulator thật sự hỗ trợ cập nhật đồng thời |

Collector trong `CustomCollectorDemo` không yêu cầu đặc tính nào. Vì A khác R, nó **không** có `IDENTITY_FINISH`. Vì chưa thiết kế container cho cập nhật đồng thời cùng instance, nó **không** có `CONCURRENT`. Không cần khai báo `UNORDERED` để có thể xử lý song song.

Đặc tính là **hợp đồng kỹ thuật**, không phải nhãn tối ưu tùy ý. Khai báo sai có thể dẫn đến lỗi chỉ xuất hiện trong parallel execution, hoặc làm finisher bị bỏ qua khi đáng ra phải chạy.

## 9. Phân biệt các API dễ nhầm lẫn

### `Collector.of(...)` và `Stream.collect(...)`

`Collector.of(...)` tạo **đối tượng mô tả chiến lược thu thập** dùng lại được. `stream.collect(collector)` là **terminal operation** áp dụng chiến lược ấy lên một Stream cụ thể.

Ngoài ra, `Stream.collect` có overload không nhận Collector:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner)
```

Đây là chữ ký rút gọn trong ngữ cảnh `Stream<T>`. Overload này **không có finisher riêng** và đối số combiner của nó là `BiConsumer<R,R>` (thao tác cập nhật, trả `void`), khác với `Collector.combiner()` trả `BinaryOperator<A>`. Đừng tráo hai loại combiner giữa các API.

Ví dụ từ JDK, thu vào container mutable có thể dùng:

```java
List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

Ví dụ này độc lập khi có import `java.util.*` và `java.util.stream.*`, nhưng chỉ cần kết quả List thì `toList()`/`Collectors.toList()` thường dễ đọc hơn.

### `collect` và `reduce`

`reduce` phù hợp phép toán kết hợp trên các **giá trị**, thường tránh làm biến đổi accumulator mutable. `collect` được thiết kế cho **mutable reduction**, trong đó vùng chứa `A` được cập nhật trong pipeline và có thể hoàn thiện thành `R`.

Không viết `reduce(new ArrayList<>(), (list, item) -> { list.add(item); return list; }, ...)` để thay collector khi chạy song song: identity mutable có thể bị chia sẻ và phá luật reduction. Dùng `collect` với supplier tạo container **mới**.

### `Collector.of(...)` và `Collectors.collectingAndThen(...)`

`Collector.of` dựng toàn bộ bốn bước từ đầu. `Collectors.collectingAndThen(existingCollector, finisher)` **bọc một collector có sẵn** rồi thêm bước hoàn thiện cuối. Ví dụ chỉ muốn danh sách không sửa được:

```java
List<String> names = Stream.of("An", "Binh").collect(
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf));
```

Ở đây đã có downstream cần thiết, không cần tự định nghĩa `StatsAccumulator`. Trên Java 17+, `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` cũng là những lựa chọn rõ ràng cho việc lấy danh sách không sửa được, tùy chính sách xử lý `null` và dữ liệu đầu vào.

## 10. Kiểm thử đúng theo ba kiểu T/A/R và theo trường hợp biên

Để kiểm tra custom collector, hãy xây bộ test dựa trên **giá trị mong đợi độc lập**:

| Test | Điều xác minh | Lỗi dễ phát hiện |
| --- | --- | --- |
| Nguồn rỗng | `Stream.<Sale>empty().collect(collector) == Summary(0,0)` | Supplier hoặc finisher xử lý empty sai |
| Một `Sale` | Count=1, tổng đúng bằng giá tiền | Accumulator bỏ sót một phần tử |
| Ba `Sale` nhỏ | Count=3, total=4500 | Accumulator cộng sai |
| Nhiều `Sale`, `parallelStream()` | Kết quả bằng oracle 10.000 phần tử/tổng 30.000 | Combiner thiếu trường, supplier dùng chung state |
| Grouping theo region | A=(2,2000), B=(1,2500) | T/A/R không tương thích khi dùng downstream |
| R kiểu `record` | Không lộ accumulator mutable, kết quả so bằng `equals` | Finisher trả nhầm A hoặc object ngoài |
| Overflow có chủ đích | Phải có chính sách xử lý rõ; ví dụ `Math.addExact` ném lỗi | Sai kết quả tiền do tràn âm thầm |
| Chạy lại nhiều lần | Có kết quả đúng và không phụ thuộc lần chạy trước | Collector giữ state giữa các lần thu thập |

Unit test tối thiểu có thể dùng chính `require(...)` trong chương trình: không phụ thuộc framework ngoài JDK. Với dự án có JUnit Jupiter, viết `assertEquals(new Summary(...), stream.collect(collector))` và dùng `assertThrows` cho trường hợp overflow, nhưng hãy giữ một **oracle độc lập** để tránh hai cách chạy cùng cho kết quả sai vẫn khiến test “pass”.

**Không test:** số luồng chính xác, thứ tự gọi accumulator/combiner, thời lượng thực thi cố định, số lần gọi supplier bằng 1, hoặc danh tính object theo `==`. Đây không phải những thuộc tính mà hợp đồng Collector bảo đảm cho mọi thực thi.

## 11. Những lỗi thường gặp với `Collector<T,A,R>`

**1. Supplier luôn trả về cùng một instance.** Ví dụ `() -> sharedAccumulator` là sai cho thiết kế này, vì mọi lượt thu thập hoặc nhánh song song có thể chia sẻ trạng thái. Dùng constructor/factory tạo mới như `StatsAccumulator::new`.

**2. Nhầm T với A.** `accumulator` phải nhận (`A`, `T`); `combiner` phải nhận (`A`, `A`). Với kiểu khác nhau, compiler có thể bắt được lỗi; đừng dùng raw type để che cảnh báo.

**3. Combiner chỉ lấy một nhánh hoặc quên một trường.** Một chương trình chỉ test `stream()` có thể không kích hoạt combiner theo cách bạn mong đợi. Luôn test `parallelStream()` với nguồn đủ lớn và nhiều cách phân chia, rồi so với kết quả độc lập.

**4. Finisher trả về container mutable nội bộ.** Nếu caller có thể sửa accumulator sau khi hoàn tất, có thể phá tính ổn định của kết quả. Thiết kế `R` thành DTO/record bất biến hoặc defensive copy khi cần; record chỉ bảo vệ nông nếu bản thân các thành phần của nó là object mutable.

**5. Gắn `IDENTITY_FINISH` khi A khác R.** Framework có quyền bỏ qua finisher, dẫn tới kết quả sai hoặc lỗi kiểu. Chỉ công bố đặc tính này khi thực sự đáp ứng hợp đồng.

**6. Gắn `CONCURRENT` vào collector mutable thông thường.** `ArrayList`, `HashMap`, hay object giữ các trường `long` không tự trở nên thread-safe. Không cần gắn `CONCURRENT` để dùng collector trong `parallelStream()`.

**7. Phụ thuộc vào thứ tự mà không bảo đảm.** Nếu kết quả là danh sách có thứ tự, combiner phải gộp đúng encounter order; không khai báo `UNORDERED`. Nếu chỉ đếm/tính tổng thì thứ tự ít quan trọng hơn, nhưng vẫn cần đúng tính kết hợp.

**8. Không định nghĩa nguồn rỗng.** Hỏi “`A` khởi đầu ra sao?” và “`finisher` trả `R` nào khi chưa có phần tử?”. Với `Summary` của bài, kết quả rỗng là `Summary(0,0)`. Nếu nghiệp vụ yêu cầu “không có kết quả” thì đổi thiết kế `R` hoặc thêm thông tin trạng thái một cách rõ ràng.

**9. Hiểu nhầm generic variance.** `Collector<Sale,StatsAccumulator,Summary>` không tự động biến thành `Collector<Sale,Object,Summary>` vì generic Java không hiệp biến kiểu tích lũy. Dùng `Collector<Sale,?,Summary>` khi mục tiêu là ẩn A.

**10. Dùng số thực để tính tiền mà không định nghĩa sai số.** `double` có sai số làm tròn và có thể chịu ảnh hưởng thứ tự kết hợp; ví dụ chọn `long` cents. Sản phẩm thực cần thêm thông tin loại tiền, giới hạn, hoàn tiền và quy tắc nghiệp vụ.

## 12. Bài tự luyện và đáp án

1. Với `Collector<String, StringJoiner, String>`, hãy chỉ ra T, A, R. **Đáp án:** T là `String` đầu vào, A là `StringJoiner` tích lũy, R là `String` kết quả.
2. Trong `Collector<Sale, StatsAccumulator, Summary>`, phương thức nào nhận `Sale`? **`accumulator()`**; phương thức nào nhận hai `StatsAccumulator`? **`combiner()`**; phương thức nào tạo `Summary`? **`finisher()`**.
3. Nếu Stream rỗng, `finisher` nhận gì? **Một trạng thái tích lũy rỗng phù hợp supplier/combiner**, và ví dụ trả `Summary(0,0)`. Không được suy diễn rằng supplier chỉ được gọi đúng một lần trong mọi cách chạy.
4. Có thể dùng `parallelStream().collect(collector)` nếu collector không có `CONCURRENT` không? **Có**, khi các luật collector đúng; framework quản lý vùng tích lũy riêng biệt rồi kết hợp.
5. Khi nào dùng `Collector<Sale, ?, Summary>`? **Khi caller chỉ cần collector và kết quả Summary**, không cần biết chính xác loại state A.
6. Có được công bố `IDENTITY_FINISH` khi `A=StatsAccumulator` và `R=Summary`? **Không**; finisher đang chuyển kiểu và tạo kết quả mới.
7. Nếu thêm `Sale("A", 700)` vào nguồn ở ví dụ, kết quả tổng cần là gì? **`Summary[count=4, totalCents=5200]`**; riêng nhóm A thành `Summary[count=3, totalCents=2700]`.

## 13. Checklist thiết kế custom collector

- [ ] Đã xác định rõ **T (phần tử)**, **A (container trung gian)**, **R (đầu ra)**.
- [ ] `supplier` tạo mỗi vùng chứa mới; trạng thái rỗng là đơn vị đúng của phép gộp.
- [ ] `accumulator(A,T)` đưa đủ dữ liệu T vào A, không sửa nguồn, không có shared mutable state.
- [ ] `combiner(A,A)` gộp đầy đủ mọi trường và thỏa identity/associativity theo ngữ nghĩa kết quả.
- [ ] `finisher(A)` trả R đúng kiểu, rõ chính sách mutable/immutable, empty và lỗi.
- [ ] `IDENTITY_FINISH`, `CONCURRENT`, `UNORDERED` chỉ được khai báo khi thật sự đúng.
- [ ] Đã có test empty, một phần tử, nhiều phần tử, nhóm, song song và kết quả oracle độc lập.
- [ ] Đã kiểm tra overflow, null và dữ liệu bất thường theo hợp đồng nghiệp vụ.
- [ ] Đã xác minh không có collector tiêu chuẩn nào giải quyết bài toán đơn giản hơn.

## Tài liệu tham khảo chính thức (API hiện hành)

- [Oracle Java SE 26 — Collector<T,A,R>, các hàm supplier/accumulator/combiner/finisher và Collector.of](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html)
- [Oracle Java SE 25 — Collector.Characteristics](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.Characteristics.html)
- [Oracle Java SE 26 — package java.util.stream: Reduction, Parallelism, Associativity và Extensibility](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 25 — Stream.collect và các overload khác nhau](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
