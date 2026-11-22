# Thiết kế Gatherer có combiner cho xử lý song song

Trong **Java Stream API**, các phép toán `map`, `filter`, `flatMap`, `reduce` và `collect` giải quyết nhiều bài toán xử lý dữ liệu khai báo. Tuy nhiên, có những phép biến đổi cần **trạng thái riêng**, có thể phát ra không phần tử, một phần tử hoặc nhiều phần tử, và có thể phát ra kết quả khi nguồn kết thúc. **Stream Gatherers** cung cấp điểm mở rộng `Stream.gather(...)` để mô tả những phép toán trung gian như vậy.

Khi muốn Gatherer tự định nghĩa hoạt động hiệu quả trên **parallel stream**, phần khó nhất thường là thiết kế **`combiner`**. Hàm này không chỉ “ghép hai đối tượng”: nó phải tạo ra trạng thái tương đương với trạng thái thu được nếu toàn bộ phần tử được xử lý theo đúng ngữ nghĩa, bất kể framework chia nguồn thành bao nhiêu phần.

Bài học thuộc chương **Xây dựng Gatherer tùy biến** của mô-đun `JAVA_STREAM_API`. Chúng ta sẽ xây một Gatherer có bốn thành phần `initializer`, `integrator`, `combiner`, `finisher`; phân tích các luật kết hợp, kiểm thử tuần tự/song song và nhận diện những thuật toán **không thể song song hóa chỉ bằng một combiner đơn giản**.

## 1. Phiên bản Java và phạm vi của API

`Gatherer<T, A, R>`, `Gatherers` và `Stream.gather(...)` là API chính thức từ **Java 24**. Chúng từng xuất hiện dưới dạng **preview** ở Java 22 và Java 23; mã trong bài sử dụng API chuẩn của **Java 24 trở lên**, không cần bật preview khi biên dịch với JDK 24.

```java
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;
```

Ở những dự án chỉ chạy Java 17 hoặc 21, không thể sao chép trực tiếp ví dụ `gather` mà mong biên dịch. Khi đó hãy dùng `map`, `flatMap`, `collect`, một collector tùy chỉnh hoặc nâng mức JDK theo kế hoạch của dự án.

Một Gatherer là **intermediate operation**: `stream.gather(gatherer)` trả một stream mới, và việc xử lý thực tế vẫn được kích hoạt bởi terminal operation như `toList()`, `count()`, `findFirst()` hoặc `collect()`.

## 2. Bốn thành phần phối hợp thế nào?

Các kiểu generic của `Gatherer<T, A, R>` có ý nghĩa:

| Ký hiệu | Vai trò | Ví dụ của bài |
| --- | --- | --- |
| `T` | Kiểu phần tử đi vào Gatherer. | `Integer` |
| `A` | Kiểu trạng thái tích lũy riêng, có thể mutable. | `State` chứa count, sum, min, max |
| `R` | Kiểu phần tử Gatherer phát ra cho downstream. | `Summary` bất biến |

Một Gatherer đầy đủ sử dụng bốn hàm:

| Thành phần | Chữ ký/ý nghĩa khái quát | Trách nhiệm |
| --- | --- | --- |
| `initializer` | `Supplier<A>` | Tạo **trạng thái mới** cho mỗi phần tích lũy cần thiết. |
| `integrator` | `(A, T, Downstream<R>) -> boolean` | Xử lý một đầu vào, cập nhật trạng thái và có thể `push` đầu ra. |
| `combiner` | `BinaryOperator<A>` | Gộp hai trạng thái bộ phận thành một trạng thái tương đương. |
| `finisher` | `(A, Downstream<R>) -> void` | Thực hiện bước cuối khi đã xử lý xong nguồn, có thể phát ra kết quả. |

Trên Java 24, factory phù hợp là:

```java
Gatherer.of(initializer, integrator, combiner, finisher);
```

Sơ đồ ý tưởng với nguồn được chia:

```text
                      Stream<T> có thể chia
                               |
                    +----------+----------+
                    |                     |
                  Phần 1                Phần 2
                    |                     |
              initializer()           initializer()
                    |                     |
              State A1                State A2
                    |                     |
           integrator() nhiều lần  integrator() nhiều lần
                    |                     |
                    +--------+------------+
                             |
                    combiner(A1, A2)
                             |
                       State kết hợp
                             |
                       finisher()
                             |
                   Downstream.push(R)
```

Số phần, vị trí cắt, thứ tự thực thi và số lần gọi `combiner` là quyết định của framework. **Không** được viết logic phụ thuộc vào việc nguồn chắc chắn được chia làm hai phần hay `combiner` chắc chắn được gọi.

## 3. Có combiner khác gì với `ofSequential`?

Một Gatherer **có trạng thái** nhưng không có combiner phù hợp nên dùng `Gatherer.ofSequential(...)`. Nếu `combiner()` của Gatherer là `Gatherer.defaultCombiner()`, Gatherer ấy **chỉ được thực thi tuần tự**, kể cả khi upstream được đánh dấu `parallel()`.

```java
// Khái niệm, với State và integrator đã được định nghĩa:
Gatherer.ofSequential(State::new, integrator, finisher);

// Cho phép phân chia và gộp trạng thái khi combiner hợp lệ:
Gatherer.of(State::new, integrator, combiner, finisher);
```

Từ **cho phép** rất quan trọng: cung cấp combiner không bảo đảm runtime **sẽ** thực thi song song, và cũng không bảo đảm nó **nhanh hơn**. Framework có thể chọn kế hoạch thực thi khác tùy nguồn, terminal operation và tính chất Gatherer.

Ngược lại, với Gatherer **không có trạng thái**, Java có `Gatherer.of(integrator)` tạo Gatherer parallelizable mà không cần cung cấp trạng thái hoặc combiner thủ công:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> doubled =
    Gatherer.<Integer, Integer>of(
        (ignored, value, downstream) ->
            downstream.push(value * 2)
    );

List<Integer> result = Stream.of(1, 2, 3, 4)
    .parallel()
    .gather(doubled)
    .toList();

System.out.println(result); // [2, 4, 6, 8]
```

Đây chỉ là cách **minh họa API**; phép biến đổi một-một đơn giản nên dùng `map(value -> value * 2)` thay vì tự viết Gatherer.

## 4. Luật quan trọng nhất: trạng thái phải gộp được

Giả sử nguồn được chia thành ba đoạn `P`, `Q`, `R`. Gọi `S(P)` là trạng thái thu được bằng cách tích lũy đoạn `P`, và `C(a, b)` là combiner.

Điều kiện mong muốn là:

\[
C(S(P), S(Q)) \equiv S(P \mathbin{+\!+} Q)
\]

Ký hiệu `++` ở đây là phép nối hai đoạn nguồn theo đúng thứ tự nếu đầu vào có encounter order. Với ba đoạn, combiner phải có tính **kết hợp** (*associativity*) theo ngữ nghĩa:

\[
C(C(a,b),c) \equiv C(a,C(b,c))
\]

Nếu `e` là trạng thái rỗng do initializer tạo, cần phần tử đơn vị:

\[
C(e,a) \equiv a, \quad C(a,e) \equiv a
\]

Dấu `≡` nói về **kết quả quan sát được**, không đòi các object có cùng tham chiếu. Ví dụ một combiner có thể sửa `left` rồi trả `left`, miễn là nó chỉ sửa trạng thái riêng phù hợp và bảo toàn ngữ nghĩa.

**Tính kết hợp không đồng nghĩa tính giao hoán.** Phép nối chuỗi `"A" + "B"` có tính kết hợp nhưng `"AB"` khác `"BA"`. Khi kết quả cần giữ thứ tự nguồn, combiner phải bảo toàn thứ tự ghép các đoạn; không tự ý đảo `left` và `right`. Với nguồn unordered, cần xác định rõ kết quả có được phép khác thứ tự hay không.

## 5. Dự án mẫu: Gatherer thống kê song song, phát một báo cáo

Bài toán: đầu vào là một stream `Integer`; đầu ra là **một `Summary`** chứa số lượng, tổng, giá trị nhỏ nhất/lớn nhất. Chúng ta không phát kết quả sau mỗi phần tử. Mỗi phần dữ liệu được tích lũy vào `State` riêng; các trạng thái được gộp; cuối cùng `finisher` mới phát báo cáo.

Đây là ví dụ sư phạm để minh họa **combiner của Gatherer**. Nếu chỉ muốn thống kê số nguyên trong ứng dụng thực tế, `IntStream.summaryStatistics()` hoặc `Collectors.summarizingInt(...)` thường đơn giản hơn.

### Chương trình hoàn chỉnh (Java 24+)

```java
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.stream.Gatherer;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public final class ParallelSummaryGatherer {
    private ParallelSummaryGatherer() {}

    // Đầu ra chỉ chứa các giá trị không thể thay đổi.
    public record Summary(
        long count,
        long sum,
        OptionalInt minimum,
        OptionalInt maximum
    ) {}

    // Trạng thái tích lũy nội bộ cho từng phần dữ liệu.
    private static final class State {
        private long count = 0L;
        private long sum = 0L;
        private int minimum = Integer.MAX_VALUE;
        private int maximum = Integer.MIN_VALUE;

        void add(Integer boxedValue) {
            int value = Objects.requireNonNull(
                boxedValue, "Gatherer không nhận null"
            );

            count = Math.addExact(count, 1L);
            sum = Math.addExact(sum, (long) value);
            minimum = Math.min(minimum, value);
            maximum = Math.max(maximum, value);
        }

        State combine(State right) {
            // State rỗng phải là phần tử đơn vị.
            if (right.count == 0L) {
                return this;
            }
            if (this.count == 0L) {
                this.count = right.count;
                this.sum = right.sum;
                this.minimum = right.minimum;
                this.maximum = right.maximum;
                return this;
            }

            this.count = Math.addExact(this.count, right.count);
            this.sum = Math.addExact(this.sum, right.sum);
            this.minimum = Math.min(this.minimum, right.minimum);
            this.maximum = Math.max(this.maximum, right.maximum);
            return this;
        }

        Summary snapshot() {
            return new Summary(
                count,
                sum,
                count == 0L
                    ? OptionalInt.empty()
                    : OptionalInt.of(minimum),
                count == 0L
                    ? OptionalInt.empty()
                    : OptionalInt.of(maximum)
            );
        }
    }

    public static Gatherer<Integer, ?, Summary> summaryGatherer() {
        return Gatherer.<Integer, State, Summary>of(
            State::new,

            // Integrator: chỉ tích lũy; chưa phát kết quả.
            Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    state.add(element);
                    return true;
                }
            ),

            // Combiner: gộp hai State độc lập.
            (left, right) -> left.combine(right),

            // Finisher: phát đúng một báo cáo cuối cùng.
            (state, downstream) ->
                downstream.push(state.snapshot())
        );
    }

    public static void main(String[] args) {
        List<Summary> sequential = IntStream
            .rangeClosed(1, 1_000)
            .boxed()
            .gather(summaryGatherer())
            .toList();

        List<Summary> parallel = IntStream
            .rangeClosed(1, 1_000)
            .boxed()
            .parallel()
            .gather(summaryGatherer())
            .toList();

        if (!sequential.equals(parallel)) {
            throw new AssertionError("Kết quả không tương đương");
        }
        if (parallel.size() != 1) {
            throw new AssertionError("Phải có một báo cáo");
        }

        Summary report = parallel.get(0);
        System.out.println(report.count());                 // 1000
        System.out.println(report.sum());                   // 500500
        System.out.println(report.minimum().orElseThrow()); // 1
        System.out.println(report.maximum().orElseThrow()); // 1000

        List<Summary> empty = Stream.<Integer>empty()
            .gather(summaryGatherer())
            .toList();

        System.out.println(empty.get(0).count());           // 0
        System.out.println(empty.get(0).minimum().isEmpty()); // true
    }
}
```

Lưu thành `ParallelSummaryGatherer.java`, biên dịch và chạy bằng **JDK 24 hoặc mới hơn**:

```text
javac ParallelSummaryGatherer.java
java ParallelSummaryGatherer
```

Đây là mã thực hành được cung cấp để người học chạy; bài viết **không đưa ra số liệu benchmark** và không coi một lần chạy đúng là kiểm thử đầy đủ các cách phân hoạch.

## 6. Phân tích từng thành phần của chương trình

### `initializer`: mỗi phần có trạng thái mới

```java
State::new
```

Khi framework chia nguồn, nó có thể gọi initializer nhiều lần để tạo các `State` độc lập. **Không** tạo một biến `State shared = new State()` ở bên ngoài rồi cung cấp `() -> shared`: làm vậy khiến nhiều phần tích lũy dùng chung count/sum/min/max, phá vỡ khả năng phân chia an toàn.

Trong ví dụ, `State` cố ý mutable, nhưng không bị lộ ra ngoài. **Không cần đồng bộ mọi `State.add`** nếu framework dùng chúng theo hợp đồng Gatherer: mỗi phần được tích lũy riêng, việc kết hợp bắt đầu sau khi tích lũy các phần liên quan kết thúc.

### `integrator`: cập nhật phần dữ liệu hiện tại

```java
Gatherer.Integrator.ofGreedy(
    (state, value, downstream) -> {
        state.add(value);
        return true;
    }
)
```

`Integrator.ofGreedy` báo rằng integrator không tự ngắn mạch việc tiêu thụ đầu vào. Nó vẫn phải tôn trọng downstream nếu phát phần tử và downstream không muốn nhận thêm. Trong ví dụ, integrator **chưa `push` gì**, nên luôn trả `true`, dành việc phát kết quả cho `finisher`.

`Downstream.push(r)` trả `boolean` để cho biết downstream còn muốn nhận phần tử hay không. Khi viết một Gatherer phát nhiều phần tử trong integrator, phải xem xét kết quả trả về và không cố phát mãi sau khi downstream từ chối.

### `combiner`: ghép hai kết quả bộ phận

```java
(left, right) -> left.combine(right)
```

`left` và `right` là hai trạng thái được trả về bởi initializer hoặc combiner, không phải hai phần tử `Integer` đầu vào. `combine` ở ví dụ:

- Cộng `count` và `sum`.
- Lấy min của hai min và max của hai max.
- Xử lý trạng thái rỗng làm identity.
- Trả trạng thái đã gộp.

Với các giá trị nằm trong phạm vi số học cho phép, kết quả không phụ thuộc cách ngoặc hóa phép gộp. `Math.addExact` chủ động ném `ArithmeticException` khi tổng vượt `long`, tránh tràn âm thầm; ở dữ liệu cực lớn có thể cần `BigInteger` hoặc chính sách số học khác.

Một điều ít người chú ý: sau khi trạng thái đã được đưa vào **combiner hoặc finisher**, framework sẽ không chuyển trạng thái ấy lại cho integrator. Điều này cho phép combiner gộp và chuyển quyền sở hữu trạng thái, nhưng **không** cho phép giữ tham chiếu trạng thái để tự sửa ở thread khác.

### `finisher`: một báo cáo, không phải một báo cáo cho mỗi phần

```java
(state, downstream) -> downstream.push(state.snapshot())
```

Vì `integrator` chỉ tích lũy và `combiner` kết hợp trạng thái, finisher phát **một Summary cuối cùng**. Record `Summary` chỉ giữ primitive và `OptionalInt`, nên không chứa tham chiếu tới `State` mutable.

Đừng nghĩ finisher sẽ chạy một lần cho **mỗi partition** rồi tự động gộp các báo cáo đã phát. Với Gatherer có combiner, việc gộp **trạng thái** là bước cần thiết trước khi phát kết quả cuối.

## 7. Tự kiểm tra luật của combiner

Không chỉ chạy `parallel()` một lần rồi thấy kết quả đúng. Hãy kiểm tra chính phép kết hợp trạng thái bằng những trường hợp có thể tự tính tay.

Ví dụ nguồn `[2, 4, 6, 8]`:

| Phân hoạch | Trạng thái riêng | Gộp cuối |
| --- | --- | --- |
| `[2, 4]`, `[6, 8]` | `(2,6,2,4)`, `(2,14,6,8)` | `(4,20,2,8)` |
| `[2]`, `[4,6,8]` | `(1,2,2,2)`, `(3,18,4,8)` | `(4,20,2,8)` |
| `[]`, `[2,4,6,8]` | State rỗng và `(4,20,2,8)` | `(4,20,2,8)` |

Các tuple lần lượt có nghĩa `(count, sum, min, max)`. Với dữ liệu không tràn số:

```text
combine(combine(A, B), C)
          ==
combine(A, combine(B, C))
```

**Lưu ý về mutation trong test:** `State.combine` ở ví dụ sửa đối tượng bên trái. Không được lấy **cùng một State** rồi thử cả hai cách ngoặc hóa trên nó; phép thử thứ hai sẽ nhìn thấy trạng thái đã bị thay đổi bởi phép thử thứ nhất. Cần tạo các bản trạng thái độc lập cho từng đường tính và so sánh `Summary` cuối.

Một test mạnh hơn nên thử:

- Không phần tử.
- Một phần tử.
- Nhiều phần tử chẵn/lẻ, số âm và số dương.
- Giá trị `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.
- Nhiều cách chia đoạn, kể cả các đoạn rỗng.
- Kết quả tuần tự so với song song ở nhiều kích thước nguồn.
- Nguồn có dữ liệu lặp lại, bảo đảm không mất hoặc cộng trùng phần tử.

Nếu phép toán sử dụng `double`, tính kết hợp **không còn chính xác tuyệt đối theo bit** do quy tắc làm tròn. Khi đó test cần tiêu chí sai số và yêu cầu nghiệp vụ rõ ràng; không giả định tổng `double` tuần tự/song song luôn giống từng bit.

## 8. Vì sao phát kết quả sớm làm combiner khó hơn nhiều?

Gatherer có thể phát kết quả trong **integrator**, chứ không cần chờ finisher. Nhưng khi đầu ra của phần sau **phụ thuộc trạng thái của phần trước**, việc kết hợp trạng thái cuối cùng thường **không sửa được những kết quả đã phát**.

Ví dụ một phép **prefix sum** của `[1, 2, 3, 4]` phải phát:

```text
Input:      1   2   3   4
Prefix:     1   3   6  10
```

Giả sử framework chia thành `[1,2]` và `[3,4]`. Nếu mỗi phần bắt đầu từ tổng `0` và phát ngay:

```text
Phần 1 phát: [1, 3]
Phần 2 phát: [3, 7]    <-- sai: cần [6, 10]
```

Dù sau đó combiner có cộng hai tổng phần (`3 + 7 = 10`), nó **không tự sửa các phần tử `3,7` đã được phát** từ nhánh thứ hai. Muốn song song hóa prefix scan cần thuật toán nhiều pha: tính tổng từng phần, tính offset cho phần sau, rồi điều chỉnh các giá trị đầu ra **trước khi phát chúng**. Đó là bài toán khác với chỉ cung cấp `(left, right) -> left.sum += right.sum`.

Java đã có `Gatherers.scan(...)` cho phép quét tiền tố theo thứ tự, và `Gatherers.fold(...)` cho bài toán rút gọn có tính phụ thuộc thứ tự. Hai Gatherer này diễn đạt những tác vụ thường **cần xử lý tuần tự** theo hợp đồng, thay vì lắp một combiner giả để ép chạy song song.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> prefixes = Stream.of(1, 2, 3, 4)
    .gather(Gatherers.scan(() -> 0, Integer::sum))
    .toList();

System.out.println(prefixes); // [1, 3, 6, 10]
```

**Bài học cốt lõi:** khi phép biến đổi phát ra nhiều phần tử phụ thuộc vào lịch sử, phải chứng minh **đầu ra** của từng phần vẫn tương đương với chạy tuần tự, chứ không chỉ chứng minh trạng thái cuối gộp được.

## 9. Tính kết hợp nhưng không giao hoán: thứ tự cũng là hợp đồng

Một combiner gộp trạng thái là danh sách hoặc chuỗi có thể dùng phép nối:

```text
combine("AB", "CD") = "ABCD"
```

Phép nối có tính kết hợp:

```text
("AB" + "CD") + "EF" = "AB" + ("CD" + "EF")
```

nhưng không có tính giao hoán:

```text
"AB" + "CD" != "CD" + "AB"
```

Nếu Gatherer dùng thứ tự nguồn để tạo chuỗi hoặc danh sách, combiner phải giữ đúng **thứ tự các đoạn**. Không được dùng một `HashSet` rồi kỳ vọng thứ tự encounter order sẽ được giữ nguyên. Nếu đầu vào đến từ nguồn không có encounter order hoặc đã gọi `unordered()`, phải xác định rõ kết quả nào được coi là hợp lệ.

Với phép `windowFixed(3)`, ranh giới chia nguồn còn tạo vấn đề khác: một cửa sổ có thể bắt đầu ở phần trái và kết thúc ở phần phải. Combiner đúng phải **giữ hoặc tái tạo được các phần tử ở ranh giới**, không thể chỉ nối hai danh sách cửa sổ đã phát mà bỏ qua phần dư. Khi không có một thiết kế gộp ranh giới đúng, nên sử dụng `Gatherers.windowFixed(3)` thay vì tự viết Gatherer song song.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows); // [[1, 2, 3], [4, 5, 6], [7]]
```

## 10. Những combiner sai thường gặp

| Thiết kế sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| `(left, right) -> left` | Bỏ toàn bộ trạng thái của nhánh phải. | Gộp đủ thông tin từ hai nhánh. |
| `(left, right) -> right` | Bỏ toàn bộ nhánh trái. | Thiết kế phép kết hợp theo nghiệp vụ. |
| `(left, right) -> new State()` | Mất dữ liệu đã tích lũy. | Trả trạng thái thực sự tổng hợp hai nhánh. |
| Lấy **trung bình của hai trung bình** | Sai khi số mẫu hai nhánh khác nhau. | Gộp `sum` và `count`, rồi mới chia. |
| Gộp min/max nhưng không xử lý trạng thái rỗng | Có thể phát sentinel `MAX_VALUE`/`MIN_VALUE` như dữ liệu thật. | Thiết kế identity rỗng và `Optional` khi chốt. |
| Dùng chung một `State` từ initializer | Race, đếm trùng hoặc gộp chính đối tượng đó vào nó. | `State::new` tạo riêng cho từng phần. |
| Combiner có side effect ngoài, ví dụ ghi vào `List` toàn cục | Tính đúng phụ thuộc lịch gọi, khó kiểm thử. | Chỉ gộp hai state của Gatherer. |
| `left + right` trên phép toán không kết hợp, như phép trừ | Kết quả có thể phụ thuộc ranh giới phân hoạch. | Chọn biểu diễn trạng thái có phép kết hợp hợp lệ hoặc dùng sequential. |
| Gộp trạng thái sau khi integrator đã phát prefix phụ thuộc phần trước | Đầu ra từng phần đã sai, không tự sửa được. | Thiết kế thuật toán hiệu chỉnh ranh giới/offset hoặc dùng `scan` tuần tự. |
| Giữ tham chiếu `Downstream` để `push` sau khi callback trả về | Vi phạm vòng đời do API quy định. | Chỉ dùng downstream trong lời gọi integrator/finisher hợp lệ. |

### Ví dụ lỗi trung bình của các trung bình

```text
Nhóm A: [10]         -> mean = 10, count = 1
Nhóm B: [20,30,40]   -> mean = 30, count = 3

(10 + 30) / 2 = 20         // SAI
(10 + 20 + 30 + 40) / 4 = 25 // ĐÚNG
```

Một `State` đúng cho average nên lưu `sum` và `count`, combiner cộng từng trường, rồi finisher tính `sum / count`. Nếu yêu cầu độ chính xác thập phân đặc biệt, chọn kiểu số và chính sách làm tròn phù hợp trước khi triển khai.

## 11. State mutable không đồng nghĩa phải thread-safe

Trong một Gatherer có combiner hợp lệ, framework có thể tạo nhiều state bằng initializer, xử lý **các phân vùng độc lập**, sau đó kết hợp. Vì vậy một `State` với các trường `long`/ `int` đơn giản hoặc một `ArrayList` nội bộ có thể được dùng an toàn **trong phạm vi trạng thái riêng** mà không nhất thiết phải dùng `AtomicLong` hay khóa.

Tuy nhiên, có những điều **không được làm**:

- Giữ một `State` dùng chung trong biến static để mọi integrator cùng cập nhật.
- Trả lại state mutable trực tiếp trong kết quả mà mã khác có thể sửa khi stream chưa hoàn tất.
- Capture tham chiếu `State` hoặc `Downstream` rồi giữ lại để dùng ở thread khác sau khi callback kết thúc.
- Tạo task bất đồng bộ trong integrator và để task đó tiếp tục sửa state sau khi integrator trả về.
- Đánh đồng `parallel()` với “mỗi phần tử có thread riêng”, hoặc dự đoán số lần framework gọi initializer/combiner.

**Không dùng một state đồng thời hóa toàn cục để né thiết kế combiner.** Cách đó có thể triệt tiêu lợi ích của song song, thay đổi ngữ nghĩa và làm mất tính độc lập của các phần tích lũy.

## 12. Kỹ thuật kiểm thử không phụ thuộc lịch chia của runtime

Không có cơ sở để viết test rằng input có 1.000 phần tử thì runtime luôn gọi `combiner` đúng 3 lần hoặc luôn dùng 4 worker. Một phép kiểm thử tốt cần tập trung vào **bất biến kết quả**:

1. Chạy tuần tự trên cùng dữ liệu, lấy `Summary` mong đợi.
2. Chạy song song nhiều lần và so sánh **giá trị**, không so sánh lịch callback hoặc thread.
3. Thử trên nguồn mảng/`ArrayList` có thứ tự và nguồn không có encounter order nếu ngữ nghĩa hỗ trợ.
4. Kiểm tra trạng thái rỗng, một phần tử, số âm, các giá trị biên và dữ liệu trùng.
5. Thử trực tiếp luật identity/associativity trên những state **mới**, không tái sử dụng state đã bị combiner sửa.
6. Thử downstream ngắn mạch như `limit` hoặc `findFirst` theo **hợp đồng đầu ra** thực sự của Gatherer; không suy ra mọi phần tử bắt buộc đã đi qua integrator.
7. Nếu combiner có phép gộp không giao hoán, kiểm tra chính xác yêu cầu **giữ thứ tự**.

Đối với bài thống kê của chúng ta, `Math.addExact` cố ý báo lỗi nếu vượt `long`. Điều đó tốt hơn trả một tổng sai không có cảnh báo, nhưng cũng có nghĩa những input mà tổng **trung gian** vượt phạm vi có thể không được xử lý thành công. Nếu muốn hỗ trợ mọi dữ liệu số nguyên trong một miền rộng hơn, thay `sum` bằng kiểu không tràn như `BigInteger` và thiết kế combiner tương ứng.

**Tách test đúng đắn khỏi benchmark:** việc kết quả tuần tự/song song bằng nhau chỉ chứng minh một số trường hợp đầu vào đã thử, không chứng minh phiên bản song song nhanh hơn.

## 13. Có combiner rồi, vì sao vẫn có thể chậm?

Khả năng mở rộng phụ thuộc nhiều yếu tố:

| Yếu tố | Hệ quả có thể xảy ra |
| --- | --- |
| Nguồn nhỏ, integrator rẻ | Chi phí chia/gộp và tạo state lớn hơn lợi ích. |
| Spliterator khó chia hoặc `trySplit()` không hữu ích | Không tận dụng được nhiều worker. |
| Combiner phải nối/copy container lớn | Chi phí gộp tăng theo lượng dữ liệu, có thể làm song song chậm hơn. |
| Finisher tạo output lớn | Chi phí sau bước gộp có thể là nút thắt tuần tự. |
| Integrator giữ nhiều trạng thái | Áp lực bộ nhớ và cache tăng theo số partition. |
| Nguồn có encounter order và thuật toán phụ thuộc thứ tự | Cần duy trì thứ tự ranh giới, chi phí phối hợp tăng. |
| Mapper hoặc tích lũy có blocking I/O | Worker có thể bị giữ khi chờ I/O; parallel stream không phải bộ điều phối kết nối. |
| Nhiều request song song dùng chung tài nguyên | Tranh chấp CPU, bộ nhớ và pool làm latency biến động. |

Chẳng hạn, Gatherer thống kê count/sum/min/max chỉ gộp vài trường nên **chi phí combiner nhỏ**. Nhưng nếu bài toán thật là ghi file, nối một triệu chuỗi hoặc duy trì mọi phần tử để xử lý hậu kỳ, chi phí gộp có thể hoàn toàn khác.

Khi đo, nên so sánh **stream tuần tự**, **stream song song với Gatherer**, và một phương án **collector/reduction chuẩn** cho cùng yêu cầu. Dùng JMH với warm-up, nhiều lần đo/fork, input đã chuẩn bị ngoài đoạn đo; quan sát throughput, time/op và cấp phát. Không đưa ra speedup giả định khi chưa có số liệu thật.

## 14. Gatherer có combiner hay Collector thông thường?

Không phải bài toán tổng hợp nào cũng nên viết Gatherer mới:

| Nhu cầu | API thường phù hợp | Vì sao |
| --- | --- | --- |
| Tính tổng, count, min, max cho stream số | `IntStream.summaryStatistics()` | Có sẵn, dễ đọc, không tự quản lý state/combiner. |
| Tổng hợp thành một giá trị từ `Stream<T>` | `reduce` hoặc `collect` | Terminal reduction thể hiện đúng mục tiêu đầu ra. |
| Thu phần tử vào `Map<K,V>` hoặc nhóm | `toMap`, `groupingBy`, `groupingByConcurrent` | Collector chuẩn đã xử lý tích lũy và kết hợp. |
| Phép biến đổi một-một không có trạng thái | `map` | Đơn giản hơn `Gatherer.of`. |
| Biến đổi một-nhiều đơn giản | `flatMap` hoặc `mapMulti` | Không cần quản lý combiner cho một thuật toán stateful. |
| Prefix scan theo thứ tự | `Gatherers.scan` | Phụ thuộc lịch sử, không thể gộp bằng sum state cuối thông thường. |
| Chia cửa sổ cố định | `Gatherers.windowFixed` | Xử lý ranh giới cửa sổ theo hợp đồng. |
| Phép biến đổi mới có trạng thái và có luật gộp | **Gatherer tự định nghĩa với combiner** | Điều khiển đầu ra và khả năng xử lý song song. |

Ở ví dụ thống kê, Gatherer là một lựa chọn **để học cơ chế mở rộng Stream**; phương án production thông thường có thể chỉ cần:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics summary =
    IntStream.rangeClosed(1, 1_000).parallel().summaryStatistics();

System.out.println(summary.getSum()); // 500500
```

Sử dụng một Gatherer custom khi các phép toán có sẵn không biểu đạt được ngữ nghĩa, hoặc khi thiết kế ấy có lợi ích rõ ràng về khả năng kết hợp với các bước `gather` khác trong pipeline.

## 15. Bài tập thực hành

**Bài 1 — Tự chứng minh combiner.** Viết một `State` có `count` và `sum`, thử gộp trạng thái từ `[1,2]`, `[3]`, `[4,5]` theo hai cách ngoặc hóa. Chứng minh hai cách cho `(count=5,sum=15)` và state rỗng không làm thay đổi kết quả.

**Bài 2 — Kiểm tra dữ liệu biên.** Chạy `summaryGatherer()` với stream rỗng, một phần tử, `Integer.MIN_VALUE` và `Integer.MAX_VALUE`. Vì sao phải dùng `OptionalInt` cho min/max của nhóm rỗng thay vì công bố `Integer.MAX_VALUE` như một dữ liệu đo thật?

**Bài 3 — Chỉ số trung bình.** Mở rộng `Summary` thêm average. Chỉ tính `sum/count` trong finisher sau khi combiner đã gộp sum và count. Giải thích tại sao trung bình của hai trung bình không đúng nếu hai partition có số mẫu khác nhau.

**Bài 4 — Phân tích thiết kế sai.** Một Gatherer dùng `() -> sharedState` cho initializer và `(left,right) -> left` cho combiner. Chỉ ra ít nhất hai lỗi độc lập, giải thích vì sao đổi `sharedState` thành một đối tượng dùng `AtomicLong` không tự sửa đúng mọi lỗi.

**Bài 5 — Prefix scan.** Với `[1,2,3,4]`, chia làm hai phần và tính prefix cục bộ. Trình bày offset mà phần thứ hai cần cộng thêm để cho ra `[1,3,6,10]`. Vì sao một combiner gộp tổng cuối mà không đụng tới các giá trị đã phát không đủ?

**Bài 6 — Thứ tự.** Tưởng tượng một Gatherer ghép các tên bằng dấu phẩy trong thứ tự nguồn. Combiner nào có tính kết hợp, và tại sao `combine(right,left)` có thể làm sai kết quả? Điều gì thay đổi khi nguồn không có encounter order?

**Bài 7 — Thiết kế benchmark.** Trên JDK 24+, so sánh `summaryGatherer()`, `IntStream.summaryStatistics()` và vòng lặp `for` cho nhiều kích thước dữ liệu, bảo đảm đầu ra tương đương. Ghi số liệu đo thực tế và giải thích overhead của state, combiner, box/unbox, chia nguồn trước khi đưa ra kết luận.

## 16. Checklist trước khi chọn Gatherer song song

- [ ] Đã xác nhận JDK hỗ trợ `Stream.gather` và `Gatherer.of` (Java 24+ cho API chuẩn).
- [ ] Bài toán cần phép biến đổi Gatherer thay vì chỉ `map`, `collect` hoặc `reduce`.
- [ ] Initializer tạo **state mới** cho từng phần tích lũy.
- [ ] Integrator cập nhật đúng state được truyền vào, không sửa nguồn hoặc trạng thái toàn cục.
- [ ] Combiner giữ **đầy đủ thông tin** từ hai state, có identity và tính kết hợp theo ngữ nghĩa.
- [ ] Đã xét thứ tự encounter order nếu đầu ra không giao hoán.
- [ ] Không phát kết quả bộ phận quá sớm khi còn cần hiệu chỉnh bởi các phần trước.
- [ ] Finisher tạo đúng output, không để lộ state mutable.
- [ ] Không giữ state hoặc `Downstream` để sử dụng ngoài vòng đời lời gọi callback.
- [ ] Kiểm tra kết quả trên dữ liệu rỗng, dữ liệu biên và nhiều cách chia.
- [ ] So sánh tuần tự/song song về **giá trị**, không phụ thuộc số thread hoặc số lần combiner chạy.
- [ ] Đã đánh giá giới hạn số học, bộ nhớ, Spliterator, hiệu năng và điều kiện dừng.

**Ghi nhớ:** Một Gatherer có combiner **không** đơn giản là Gatherer tuần tự được thêm một lambda ghép state. Muốn song song hóa đúng, initializer phải cung cấp trạng thái độc lập, integrator không làm lộ hoặc dùng chung trạng thái, combiner phải bảo toàn **ngữ nghĩa của mọi cách chia/gộp**, và finisher chỉ phát đầu ra khi dữ liệu cần thiết đã hoàn chỉnh. Nếu đầu ra phụ thuộc lịch sử hoặc ranh giới phân vùng mà chưa có thuật toán hiệu chỉnh đúng, hãy chọn Gatherer tuần tự hoặc thiết kế lại phép biến đổi thay vì cố ép `parallel()`.

**Tài liệu API chính thức:** [Gatherer (Java 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html), [Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html), [Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) và [Stream.gather](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)).
