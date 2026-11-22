# Tích lũy và phát trạng thái bằng `Gatherers.scan`

> **Chương:** Stream Gatherer  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện các giới hạn về trạng thái, tài nguyên và hiệu năng.

Khi tính tổng một danh sách số, `sum()` và `reduce()` thường chỉ trả về **kết quả cuối**. Nhưng một số yêu cầu nghiệp vụ cần biết **trạng thái sau từng sự kiện**: số dư tài khoản sau mỗi giao dịch, tồn kho sau từng lần nhập/xuất, tổng doanh thu lũy kế sau từng đơn hàng hay số lần lỗi đã gặp khi xử lý log.

`Gatherers.scan` giải quyết kiểu bài toán này bằng cách giữ một trạng thái tích lũy, cập nhật trạng thái theo từng phần tử đầu vào rồi **phát trạng thái mới sau mỗi phần tử** vào pipeline. Nó là một gatherer dựng sẵn, giúp biểu diễn phép *prefix scan* mà không phải tự viết `Gatherer` từ đầu.

**Yêu cầu JDK:** `java.util.stream.Gatherers` và `Stream.gather(...)` trở thành API chính thức ở **Java 24**. Các ví dụ dưới đây dùng **JDK 24 trở lên**; chúng không biên dịch trên Java 17. Trên Java 22/23, Gatherers từng là tính năng preview, với cách bật và chữ ký cần tham khảo đúng phiên bản JDK tương ứng.

Sau bài này, bạn có thể:

1. Giải thích hai tham số `initial` và `scanner` của `Gatherers.scan`.
2. Phân biệt **trạng thái ban đầu** với **các trạng thái được phát ra**, nhất là với nguồn rỗng.
3. Tạo chuỗi tổng lũy kế, số dư giao dịch và các thống kê trung gian có nhiều trường.
4. Kết hợp `scan` với `filter`, `map`, `limit` và terminal operation; hiểu tính lười, dừng sớm và encounter order.
5. Chọn đúng giữa `scan`, `reduce`, `collect` và gatherer tùy biến; tránh lỗi trạng thái dùng chung hoặc giả định sai khi chạy song song.

## 1. Bản chất: mỗi phần tử đầu vào tạo một trạng thái tiếp theo

Với một nguồn có thứ tự `x1, x2, x3, ...` và một trạng thái khởi tạo `s0`, phép `scan` tạo:

```text
s0 = initial.get()
s1 = scanner(s0, x1)     → phát s1
s2 = scanner(s1, x2)     → phát s2
s3 = scanner(s2, x3)     → phát s3
...
```

Điều cần nhớ là **`s0` không tự được phát ra**. Nếu đầu vào có ba phần tử và mỗi bước hoàn tất bình thường, `scan` phát ba trạng thái: `s1`, `s2`, `s3`.

Ví dụ tổng lũy kế:

```text
Đầu vào:             2       3       5
                     │       │       │
Ban đầu s0 = 0       │       │       │
                     ▼       ▼       ▼
scan bằng phép cộng: 2  ───►  5  ───► 10
Đầu ra:              2       5      10
```

Nếu chỉ gọi `reduce(0, Integer::sum)`, kết quả sẽ là **một số `10`**, không phải ba số `2, 5, 10`.

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> runningTotals = List.of(2, 3, 5).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(runningTotals); // [2, 5, 10]
```

Ở đây, `List.of(...).stream()` tạo `Stream<Integer>`, `gather(...)` là phép toán trung gian tạo `Stream<Integer>` khác, và `toList()` là terminal operation kích hoạt tính toán.

## 2. Chữ ký API và vai trò của `initial`, `scanner`

Ý tưởng chữ ký của phương thức là:

```java
public static <T, R> Gatherer<T, ?, R> scan(
        Supplier<R> initial,
        BiFunction<? super R, ? super T, ? extends R> scanner
)
```

Đây là chữ ký diễn giải kiểu generic; trong code, `Supplier` và `BiFunction` thuộc `java.util.function`, còn `Gatherer` và `Gatherers` thuộc `java.util.stream`.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu phần tử đầu vào | `Integer`, `Order`, `Transaction` |
| `R` | Kiểu trạng thái tích lũy và cũng là kiểu đầu ra | `Long`, `BigDecimal`, record `RunningState` |
| `Supplier<R> initial` | Tạo trạng thái ban đầu cho **một lần thu thập** | `() -> 0`, `() -> BigDecimal.ZERO` |
| `BiFunction<R,T,R> scanner` | Nhận trạng thái trước và phần tử mới, trả trạng thái tiếp theo | `Integer::sum`, `(sum, x) -> sum.add(x)` |

Ví dụ sau cho thấy kết quả không bắt buộc cùng kiểu với nguồn:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> counts = List.of("Java", "Stream", "API").stream()
        .gather(Gatherers.<String, Long>scan(
                () -> 0L,
                (count, ignoredWord) -> Math.addExact(count, 1L)
        ))
        .toList();

System.out.println(counts); // [1, 2, 3]
```

Đầu vào là `String`, trạng thái và đầu ra là `Long`. Cặp kiểu tường minh `<String, Long>` giúp nhìn rõ `T` và `R`, dù trong nhiều biểu thức trình biên dịch có thể suy luận được chúng.

### Vì sao nên dùng một `Supplier`?

Thay vì truyền một đối tượng trạng thái dùng chung, `scan` nhận hàm **tạo trạng thái ban đầu**. Điều này quan trọng khi một Gatherer được dùng trong nhiều pipeline khác nhau: mỗi lần thực thi phải có trạng thái phù hợp, không bị kết quả của lần trước rò rỉ sang.

Với trạng thái là record bất biến hoặc `BigDecimal`, việc khởi tạo và tạo giá trị mới rất dễ kiểm soát. Với trạng thái mutable, phải đặc biệt tránh trả lại một danh sách hoặc bản đồ được chia sẻ bởi nhiều lượt chạy.

## 3. So sánh `scan`, `reduce`, `collect` và `map`

Giả sử đầu vào là `[2, 3, 5]`:

| Phương pháp | Kết quả điển hình | Khi nào chọn |
| --- | --- | --- |
| `map(n -> n * 2)` | `[4, 6, 10]` | Mỗi đầu vào chuyển thành một đầu ra, **không cần nhớ quá khứ**. |
| `reduce(0, Integer::sum)` | `10` | Chỉ cần **một tổng cuối**. |
| `collect(Collectors.summingInt(...))` | `10` | Thu thập thành kết quả cuối bằng collector. |
| `gather(Gatherers.scan(() -> 0, Integer::sum))` | `[2, 5, 10]` | Cần **mọi tổng tiền tố** trong quá trình duyệt. |

Đây là bốn mục tiêu khác nhau. `map` có thể chạy độc lập trên từng phần tử; `scan` cần kết quả tích lũy của phần tử trước để tính phần tử sau. `reduce` và `collect` chủ yếu xây dựng **kết quả cuối**, còn `scan` phát ra một **Stream các trạng thái trung gian** để các bước sau tiếp tục xử lý.

Nếu chỉ cần tổng cuối và không quan tâm những tổng trung gian, `sum()` hoặc `reduce()` thường đơn giản, dễ tối ưu hơn. Không nên dùng `scan(...).reduce((a, b) -> b)` chỉ để lấy tổng cuối nếu một phép `sum()` thông thường đã giải quyết được.

## 4. Trạng thái đầu tiên và nguồn rỗng

Trạng thái khởi tạo được dùng **trước phần tử đầu tiên**, nhưng nó không phải một đầu ra bổ sung:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> one = Stream.of(7)
        .gather(Gatherers.scan(() -> 100, Integer::sum))
        .toList();

List<Integer> empty = Stream.<Integer>empty()
        .gather(Gatherers.scan(() -> 100, Integer::sum))
        .toList();

System.out.println(one);   // [107]
System.out.println(empty); // []
```

| Đầu vào | Giá trị ban đầu | Phép cập nhật | Đầu ra `scan` |
| --- | ---: | --- | --- |
| `[]` | 100 | Cộng | `[]` |
| `[7]` | 100 | Cộng | `[107]` |
| `[7, 3]` | 100 | Cộng | `[107, 110]` |
| `[7, 3, -4]` | 100 | Cộng | `[107, 110, 106]` |

Nếu nghiệp vụ cần hiển thị số dư **trước khi giao dịch đầu tiên xảy ra**, hãy bổ sung nó một cách tường minh tại tầng trình bày hoặc tạo một Stream ghép có kiểm soát. Đừng nhầm rằng `scan` tự thêm giá trị khởi tạo vào đầu ra.

### Không tự thay `scan` bằng `Stream.iterate`

`Stream.iterate` tạo các phần tử mới dựa trên phần tử trước đó, nhưng không tự lấy các **giao dịch từ một nguồn khác** rồi ghép vào từng bước của trạng thái. `scan` được thiết kế để tiêu thụ **một nguồn đầu vào hiện hữu** và cập nhật trạng thái theo chính nguồn đó.

## 5. Ví dụ hoàn chỉnh: số dư tài khoản sau từng giao dịch

Một khách hàng có số dư đầu kỳ là **100,00** đơn vị tiền. Trong kỳ phát sinh ba sự kiện:

| Giao dịch | Biến động | Số dư sau giao dịch |
| --- | ---: | ---: |
| TX-01 | +25,50 | 125,50 |
| TX-02 | -10,00 | 115,50 |
| TX-03 | +5,25 | 120,75 |

Ta cần một `List<BalanceRow>` theo **đúng thứ tự giao dịch**, mỗi dòng gồm số thứ tự xử lý, mã giao dịch và số dư **sau khi đã áp dụng** giao dịch đó.

Lưu mã dưới đây thành tệp `GatherersScanDemo.java` trên **JDK 24+**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GatherersScanDemo {

    record Transaction(String id, BigDecimal change) {
        Transaction {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(change, "change");
            if (id.isBlank()) {
                throw new IllegalArgumentException("ID không được rỗng");
            }
        }
    }

    // Trạng thái trung gian sau một số giao dịch đã xử lý.
    record RunningState(
            long processed,
            String lastTransactionId,
            BigDecimal balance
    ) {}

    // Bản ghi công bố cho người đọc báo cáo.
    record BalanceRow(
            long ordinal,
            String transactionId,
            BigDecimal balance
    ) {}

    static List<Transaction> sample() {
        return List.of(
                new Transaction("TX-01", new BigDecimal("25.50")),
                new Transaction("TX-02", new BigDecimal("-10.00")),
                new Transaction("TX-03", new BigDecimal("5.25"))
        );
    }

    static List<BalanceRow> timeline(
            List<Transaction> transactions,
            BigDecimal openingBalance
    ) {
        Objects.requireNonNull(transactions, "transactions");
        Objects.requireNonNull(openingBalance, "openingBalance");

        return transactions.stream()
                .gather(Gatherers.<Transaction, RunningState>scan(
                        // S0 chưa phải đầu ra: trạng thái trước giao dịch.
                        () -> new RunningState(0L, "", openingBalance),

                        // Mỗi giao dịch sinh một trạng thái mới.
                        (state, tx) -> new RunningState(
                                Math.addExact(state.processed(), 1L),
                                tx.id(),
                                state.balance().add(tx.change()))
                ))
                .map(state -> new BalanceRow(
                        state.processed(),
                        state.lastTransactionId(),
                        state.balance()))
                .toList();
    }

    static void check(boolean actual, String reason) {
        if (!actual) {
            throw new AssertionError(reason);
        }
    }

    static void checkMoney(
            String label, BigDecimal actual, String expected
    ) {
        check(actual.compareTo(new BigDecimal(expected)) == 0,
                label + ": expected " + expected + ", actual " + actual);
    }

    static void selfTest() {
        BigDecimal opening = new BigDecimal("100.00");
        List<Transaction> transactions = sample();
        List<BalanceRow> rows = timeline(transactions, opening);

        // Một đầu vào tạo một trạng thái đầu ra.
        check(rows.size() == 3, "Phải có đúng 3 trạng thái");
        check(rows.get(0).ordinal() == 1, "Số thứ tự đầu");
        check(rows.get(0).transactionId().equals("TX-01"),
                "Mã giao dịch đầu");
        checkMoney("Sau TX-01", rows.get(0).balance(), "125.50");
        checkMoney("Sau TX-02", rows.get(1).balance(), "115.50");
        checkMoney("Sau TX-03", rows.get(2).balance(), "120.75");

        // Nguồn rỗng: không phát số dư ban đầu.
        check(timeline(List.of(), opening).isEmpty(), "Nguồn rỗng");

        // Một đầu vào cho một trạng thái.
        check(timeline(List.of(transactions.get(0)), opening).size() == 1,
                "Một giao dịch");

        // Lần chạy khác phải có trạng thái khởi tạo của riêng nó.
        List<BalanceRow> other =
                timeline(transactions, new BigDecimal("200.00"));
        checkMoney("Kỳ khác", other.get(0).balance(), "225.50");
        checkMoney("Lần chạy gốc", rows.get(0).balance(), "125.50");

        // Tổng tiền cuối bằng opening + tổng biến động của nguồn.
        BigDecimal finalByReduce = transactions.stream()
                .map(Transaction::change)
                .reduce(opening, BigDecimal::add);
        checkMoney("Tổng cuối reduce", finalByReduce, "120.75");
        check(rows.get(rows.size() - 1).balance()
                .compareTo(finalByReduce) == 0, "Sai trạng thái cuối");

        // Đảo encounter order làm thay đổi trạng thái trung gian,
        // dù tổng cuối của phép cộng không đổi.
        List<Transaction> reversed = new ArrayList<>(transactions);
        Collections.reverse(reversed);
        List<BalanceRow> otherOrder = timeline(reversed, opening);
        checkMoney("Đảo nguồn - trạng thái đầu",
                otherOrder.get(0).balance(), "105.25");
        checkMoney("Đảo nguồn - tổng cuối",
                otherOrder.get(2).balance(), "120.75");
        check(!rows.get(0).equals(otherOrder.get(0)),
                "Trạng thái trung gian không được giữ nguyên khi đảo nguồn");

        // Kiểm tra lazy: không chạy scanner khi chỉ tạo pipeline.
        AtomicInteger calls = new AtomicInteger();
        Stream<Integer> pipeline = Stream.of(2, 3, 5)
                .gather(Gatherers.scan(
                        () -> 0,
                        (sum, value) -> {
                            calls.incrementAndGet();
                            return sum + value;
                        }
                ));
        check(calls.get() == 0, "Scanner chạy trước terminal");
        check(pipeline.toList().equals(List.of(2, 5, 10)),
                "Tổng tiền tố sai");
        check(calls.get() == 3, "Scanner không chạy đủ ba bước");

        // Nguồn vô hạn có thể dừng khi downstream lấy đủ đầu ra.
        List<Long> firstFour = Stream.iterate(1L, n -> n + 1L)
                .gather(Gatherers.scan(
                        () -> 0L,
                        Math::addExact
                ))
                .limit(4)
                .toList();
        check(firstFour.equals(List.of(1L, 3L, 6L, 10L)),
                "Scan kết hợp limit");

        // Kết quả trên nguồn có thứ tự vẫn có thứ tự được định nghĩa
        // dù pipeline trước scan được đặt ở chế độ parallel.
        List<Integer> orderedParallel = List.of(2, 3, 5)
                .parallelStream()
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();
        check(orderedParallel.equals(List.of(2, 5, 10)),
                "Parallel làm đổi prefix có thứ tự");
    }

    public static void main(String[] args) {
        List<BalanceRow> rows =
                timeline(sample(), new BigDecimal("100.00"));

        rows.forEach(row ->
                System.out.println(row.ordinal() + " | "
                        + row.transactionId() + " | "
                        + row.balance()));

        // Bộ kiểm tra này chạy mà không cần cờ -ea.
        selfTest();
        System.out.println("SCAN TESTS PASS");
    }
}
```

Biên dịch và chạy khi thực hành:

```text
javac GatherersScanDemo.java
java GatherersScanDemo
```

Đầu ra kỳ vọng:

```text
1 | TX-01 | 125.50
2 | TX-02 | 115.50
3 | TX-03 | 120.75
SCAN TESTS PASS
```

Ví dụ dùng `BigDecimal` để cộng tiền đúng theo giá trị thập phân. `new BigDecimal("25.50")` an toàn hơn `new BigDecimal(25.50)` khi đầu vào được biểu diễn dưới dạng số thập phân của nghiệp vụ. Phần `Math.addExact` giúp phát hiện tràn số đếm nếu một chuỗi có quá nhiều giao dịch, thay vì âm thầm quay vòng giá trị `long`.

Chương trình và bộ kiểm tra được cung cấp để người học tự chạy; việc viết tài liệu ở bước này **không có nghĩa** mã đã được biên dịch hoặc chạy tự động.

## 6. Dùng record bất biến để tích lũy nhiều đại lượng

Trạng thái `RunningState` trong ví dụ có ba trường:

- `processed`: số giao dịch đã đi qua.
- `lastTransactionId`: mã giao dịch vừa xử lý.
- `balance`: số dư sau giao dịch gần nhất.

`scanner` tạo **record mới** từ record trước và phần tử đầu vào:

```java
(state, tx) -> new RunningState(
        Math.addExact(state.processed(), 1L),
        tx.id(),
        state.balance().add(tx.change())
)
```

Thiết kế trạng thái bất biến có các lợi ích:

1. Các `BalanceRow` đã được phát không bị thay đổi khi scanner xử lý phần tử tiếp theo.
2. Không cần dùng biến `long count` hoặc `BigDecimal sum` đặt **bên ngoài** pipeline.
3. Mỗi lần chạy có trạng thái riêng từ `Supplier`.
4. Việc kiểm tra từng giá trị trung gian rõ ràng, dễ đối chiếu với kết quả chạy bằng vòng lặp.

Nếu thay bằng một đối tượng mutable và luôn phát **cùng tham chiếu state**, tất cả kết quả trong danh sách có thể cùng trỏ đến trạng thái sau cùng. `scan` không biến một đối tượng mutable dùng chung thành các bản chụp bất biến một cách tự động.

### Ví dụ lũy kế trung bình

Để tính trung bình sau từng phần tử, ta cần **tổng và số lượng**, không chỉ một biến trung bình có thể mất thông tin:

```java
record RunningAverage(long count, long total) {
    double average() {
        return (double) total / count;
    }
}

List<Double> averages = List.of(2, 4, 6).stream()
        .gather(Gatherers.<Integer, RunningAverage>scan(
                () -> new RunningAverage(0L, 0L),
                (state, n) -> new RunningAverage(
                        Math.addExact(state.count(), 1L),
                        Math.addExact(state.total(), n))
        ))
        .map(RunningAverage::average)
        .toList();

System.out.println(averages); // [2.0, 3.0, 4.0]
```

Trạng thái ban đầu có `count == 0` nhưng không được phát. `average()` chỉ được gọi **sau khi scanner đã xử lý ít nhất một phần tử**, vì vậy không có phép chia cho 0 trong pipeline này. Nếu cần trung bình tài chính hay tỷ lệ với quy tắc làm tròn cụ thể, dùng `BigDecimal` và chỉ làm tròn ở giai đoạn được quy định.

## 7. Tính lười: `scan` chỉ chạy khi có terminal operation

`gather(Gatherers.scan(...))` là **intermediate operation**. Khi mới tạo pipeline, những phép cập nhật trạng thái chưa cần chạy:

```java
AtomicInteger invoked = new AtomicInteger();

Stream<Integer> pipeline = Stream.of(4, 6, 8)
        .gather(Gatherers.scan(
                () -> 0,
                (sum, n) -> {
                    invoked.incrementAndGet();
                    return sum + n;
                }
        ));

System.out.println(invoked.get());   // 0, chưa có terminal operation
System.out.println(pipeline.toList()); // [4, 10, 18]
System.out.println(invoked.get());   // 3, đã tiêu thụ nguồn tuần tự
```

**Phạm vi của kiểm thử:** Đếm lời gọi scanner ở đây là phép quan sát cho một pipeline tuần tự, hữu hạn, được tiêu thụ đầy đủ. Không được mặc định trong **mọi** pipeline số lần gọi lambda sẽ cố định: short-circuit, nguồn vô hạn, việc bỏ encounter order hoặc cách chia công việc có thể làm số phần tử thực tế được xử lý khác mong đợi.

Ngoài ra, một đối tượng `Stream` chỉ sử dụng được cho **một terminal operation**. Sau `pipeline.toList()`, không gọi tiếp `pipeline.count()`. Khi cần một kết quả khác, tạo pipeline mới từ nguồn có thể duyệt lại.

## 8. Dừng sớm, `limit` và nguồn vô hạn

Vì `scan` phát một trạng thái mới ngay sau mỗi phần tử đầu vào, downstream có thể lấy **một phần chuỗi trạng thái**:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Long> triangular = Stream.iterate(1L, n -> n + 1L)
        .gather(Gatherers.scan(() -> 0L, Math::addExact))
        .limit(5)
        .toList();

System.out.println(triangular); // [1, 3, 6, 10, 15]
```

Nguồn `Stream.iterate(1L, ...)` có thể vô hạn; `limit(5)` yêu cầu chỉ **năm kết quả đầu** nên pipeline có thể hoàn tất. `Gatherers.scan` không tự đặt giới hạn số phần tử: không có `limit` hoặc một điều kiện dừng phù hợp, việc `toList()` trên nguồn vô hạn sẽ không kết thúc.

Không nhầm:

```java
// Lấy 5 trạng thái đầu, không có nghĩa lấy tổng cuối của toàn nguồn.
stream.gather(Gatherers.scan(initial, scanner)).limit(5)
```

Với nguồn có thứ tự, `limit(5)` lấy năm trạng thái đầu tiên theo encounter order. Nếu đổi vị trí `limit` và `scan`, cần xem lại ngữ nghĩa: `limit` trước `scan` hạn chế **đầu vào**, còn `limit` sau `scan` hạn chế **đầu ra**. Hai cách giống về giá trị đối với `scan` phát chính xác một kết quả cho mỗi đầu vào, nhưng có thể khác nhau với gatherer khác phát nhiều hoặc không phát kết quả cho một đầu vào.

### `scan` có thể thay `takeWhile` không?

`scan` có thể giúp **tính điều kiện trên số dư lũy kế**, rồi dùng `takeWhile` để chỉ giữ các trạng thái còn nằm trong hạn mức:

```java
List<Integer> withinBudget = List.of(4, 5, 3, 7).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .takeWhile(total -> total <= 10)
        .toList();

System.out.println(withinBudget); // [4, 9]
```

Kết quả `[4, 9, 12, 19]` do scan sinh ra được cắt ở trạng thái đầu tiên vượt `10`. Nếu cần cả **phần tử gây vượt ngưỡng**, hoặc quy tắc phát đầu ra phức tạp hơn, cần điều chỉnh pipeline hay viết Gatherer tùy biến.

## 9. Thứ tự đầu vào quyết định chuỗi trạng thái

Khác với tổng cuối của phép cộng, **tổng tiền tố phụ thuộc thứ tự**:

```java
List<Integer> forward = List.of(2, 3, 5).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [2, 5, 10]

List<Integer> reversed = List.of(5, 3, 2).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [5, 8, 10]
```

Hai danh sách có **tổng cuối như nhau** nhưng các trạng thái trung gian khác nhau. Đối với báo cáo số dư, thứ tự cần xuất phát từ quy tắc nghiệp vụ rõ ràng, ví dụ `occurredAt` tăng dần và `transactionId` làm tiêu chí phá hòa khi nhiều sự kiện cùng thời điểm.

### `sorted()` phải đặt trước `scan` nếu muốn tính theo thứ tự được sắp

```java
List<Integer> running = List.of(5, 2, 3).stream()
        .sorted()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(running); // [2, 5, 10]
```

Nếu viết `gather(scan(...)).sorted()`, bạn sẽ **sắp xếp các tổng đã tính**, chứ không thay đổi thứ tự các phần tử được dùng để tính tiền tố. Sắp xếp **sau** scan không khôi phục được đúng chuỗi trạng thái của nguồn đã sắp.

### Cần phân biệt nguồn có thứ tự và nguồn unordered

`List` có encounter order; `HashSet` không bảo đảm một thứ tự nghiệp vụ ổn định. Nếu dùng `unordered()` hoặc nguồn không có encounter order, các trạng thái trung gian có thể phụ thuộc thứ tự phần tử được đưa tới Gatherer, và không nên kỳ vọng một chuỗi prefix cố định.

Khi thứ tự là phần của hợp đồng, hãy **chọn nguồn có thứ tự hoặc sắp xếp tường minh trước scan**. Không dùng các hiệu ứng phụ như ghi log trong scanner để quyết định “thứ tự nào đã đúng” chỉ dựa trên thời điểm các callback được gọi.

## 10. `scan` và xử lý song song

`Gatherers.scan` là một gatherer có trạng thái và có ngữ nghĩa **quét tiền tố theo thứ tự**. Nó không phải phép biến đổi độc lập như `map`; việc tính trạng thái sau phụ thuộc trạng thái trước. Gatherer `scan` dựng sẵn vận hành theo hợp đồng tuần tự của riêng giai đoạn quét.

```java
List<Integer> prefixes = List.of(2, 3, 5).parallelStream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(prefixes); // [2, 5, 10]
```

Việc nguồn được cấu hình `parallelStream()` **không biến** phép tính prefix thành các phép cộng độc lập có thể ghép tùy ý. Với nguồn có encounter order và pipeline giữ thứ tự, kết quả prefix phải đúng như chuỗi theo thứ tự đó.

Tuy nhiên, không nên suy từ điều này rằng:

- Mọi giai đoạn của pipeline bắt buộc chạy trên cùng một thread.
- `parallelStream()` sẽ giúp `scan` chạy nhanh hơn.
- `scan` tự động chọn một `Executor` riêng hoặc cung cấp giới hạn I/O chặn.
- Có thể chia state tích lũy tùy ý rồi nối hai danh sách trạng thái mà không điều chỉnh tiền tố của nhánh sau.

Để tạo một phép prefix scan song song chuyên biệt, cần thuật toán phân đoạn và **hiệu chỉnh trạng thái của những đoạn sau** dựa trên kết quả đoạn trước. Đó là bài toán khác và không thể được bảo đảm chỉ bằng một `combiner` cộng hai state mà bỏ qua thứ tự.

## 11. Tích lũy theo từng nhóm: không nhầm với một scan toàn nguồn

`scan` áp dụng cho **Stream đang được đưa vào**, giữ **một chuỗi trạng thái** cho lượt thực thi đó. Khi dữ liệu gồm nhiều khách hàng và yêu cầu mỗi khách có số dư độc lập, không được lấy một `scan` cộng toàn nguồn rồi cho rằng nó sẽ tự reset trạng thái theo khóa.

Có hai cách thường gặp:

1. **Nhóm trước, scan từng nhóm:** phân loại theo `customerId`, sắp xếp các giao dịch trong từng nhóm theo `occurredAt` cùng tiêu chí phụ, rồi gọi `scan` riêng cho mỗi nhóm.
2. **Giữ một Map trạng thái trong gatherer tùy biến:** phù hợp khi dữ liệu cần xử lý liên tục nhiều khóa và không muốn materialize tất cả nhóm. Khi đó phải tự xác định ranh giới reset, trạng thái và tính đúng đắn khi dữ liệu song song.

Ví dụ minh họa cách thứ nhất:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Gatherers;

record Payment(String customerId, int amount) {}

List<Payment> payments = List.of(
        new Payment("A", 5),
        new Payment("B", 7),
        new Payment("A", 3),
        new Payment("B", 2)
);

Map<String, List<Integer>> runningByCustomer = payments.stream()
        .collect(Collectors.groupingBy(
                Payment::customerId,
                LinkedHashMap::new,
                Collectors.toList()))
        .entrySet().stream()
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                entry -> entry.getValue().stream()
                        .map(Payment::amount)
                        .gather(Gatherers.scan(() -> 0, Integer::sum))
                        .toList(),
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));

System.out.println(runningByCustomer);
// {A=[5, 8], B=[7, 9]}
```

Ở đây, `Collectors.groupingBy` tạo danh sách giao dịch cho từng khách, sau đó **mỗi danh sách mở một pipeline scan với trạng thái ban đầu bằng 0**. Bài toán này có chi phí lưu các nhóm; trên nguồn rất lớn hoặc dữ liệu theo dòng thời gian, cần đánh giá bộ nhớ và yêu cầu thứ tự riêng.

Nếu một khách có nhiều giao dịch cùng thời điểm, đừng chỉ dựa vào thứ tự vô tình của dữ liệu nhập: hãy đặt tiêu chí sắp xếp phụ như mã giao dịch nếu nghiệp vụ yêu cầu kết quả có thể tái lập.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tưởng `scan` trả một tổng cuối | Mất nhu cầu lấy trạng thái trung gian hoặc dùng API thừa | Dùng `scan` để phát chuỗi trạng thái; dùng `reduce`/`sum` cho tổng cuối. |
| Tưởng giá trị `initial` là phần tử đầu tiên được phát | Số lượng kết quả sai một đơn vị | Nhớ rằng đầu ra bắt đầu sau khi scanner xử lý phần tử đầu. |
| Quên quy tắc cho nguồn rỗng | Mong có một trạng thái mặc định từ `scan` | Nguồn rỗng tạo Stream kết quả rỗng; bổ sung đầu ra riêng nếu cần. |
| Dùng biến cộng dồn bên ngoài lambda | State rò rỉ giữa các lần chạy, khó kiểm soát song song | Chỉ giữ trạng thái qua `initial` và `scanner`. |
| Phát lại đối tượng mutable rồi sửa tiếp | Những kết quả cũ có thể đổi khi tiếp tục duyệt | Trả record/snapshot bất biến hoặc sao chép state trước khi phát. |
| Gọi `sorted()` sau `scan` để “sắp thứ tự tính” | Chỉ sắp kết quả đã tính, không sửa thứ tự cộng đầu vào | Sắp xếp nguồn **trước** Gatherer. |
| Chạy trên nguồn unordered rồi kỳ vọng chuỗi prefix cố định | Kết quả trung gian có thể thay đổi | Sắp xếp hoặc giữ encounter order rõ ràng. |
| Dùng `scan` trên nguồn vô hạn rồi `toList()` | Pipeline không kết thúc | Dùng `limit`, `takeWhile` hoặc điều kiện dừng phù hợp. |
| Nghĩ cấu hình parallel sẽ làm `scan` tự chia/gộp prefix tối ưu | Sai kỳ vọng hiệu năng, thậm chí sai thuật toán tùy biến | Hiểu tính phụ thuộc thứ tự; đo trên dữ liệu thực tế. |
| Cộng các số nguyên rất lớn bằng `sum`/`Integer::sum` không kiểm tra | Có thể tràn kiểu số | Dùng `long`, `BigInteger` hoặc `Math.addExact` theo nghiệp vụ. |
| Muốn số dư riêng từng khách nhưng scan chung mọi khách | Trạng thái khách này lẫn vào khách khác | Group theo khóa rồi scan riêng hoặc dùng Gatherer có state theo khóa. |
| Dùng lại một đối tượng Stream sau terminal operation | `IllegalStateException` | Tạo Stream mới từ nguồn có thể duyệt lại. |

## 13. Câu hỏi và bài tập

**Bài 1 — Tổng tiền tố.** Cho `[4, -2, 6]` và `initial = 10`, dự đoán kết quả sau `scan` bằng phép cộng.

**Đáp án:** `[14, 12, 18]`. Giá trị `10` không tự đứng ở vị trí đầu của kết quả.

**Bài 2 — Rỗng.** `Stream.<Integer>empty().gather(Gatherers.scan(() -> 100, Integer::sum)).toList()` tạo gì?

**Đáp án:** Danh sách rỗng `[]`. Khác với một collector được thiết kế trả về một tổng cuối mặc định, `scan` không tự phát initial.

**Bài 3 — Kiểm thử thứ tự.** Cho `[3, 1, 4]` và `initial = 0`. Hãy tìm kết quả khi scan trực tiếp và khi sắp tăng dần trước scan.

```java
List<Integer> direct = List.of(3, 1, 4).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [3, 4, 8]

List<Integer> sorted = List.of(3, 1, 4).stream()
        .sorted()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [1, 4, 8]
```

**Bài 4 — Trung bình lũy kế.** Với `[10, 20, 30, 40]`, dùng trạng thái `(count, sum)` để phát chuỗi trung bình `[10, 15, 20, 25]`. Vì sao không chỉ lưu một biến `average`?

**Đáp án gợi ý:** Cần số lượng và tổng để tính chính xác trung bình khi có phần tử mới. Nếu chỉ lưu trung bình mà không có số lượng, không biết trọng số của kết quả trước khi cập nhật.

**Bài 5 — Giới hạn.** Trên `Stream.iterate(1, n -> n + 1)`, gọi `scan(() -> 0, Integer::sum).limit(3).toList()`. Kết quả?

**Đáp án:** `[1, 3, 6]`. Downstream `limit` cho phép dừng sau ba trạng thái được yêu cầu.

**Bài 6 — Đa khách hàng.** Giao dịch theo thứ tự: `A +5`, `B +10`, `A +2`, `B -3`. Nếu số dư đầu kỳ của cả hai khách đều là 0, hãy cho kết quả lũy kế từng khách.

**Đáp án:** `A=[5,7]`, `B=[10,7]`. Không dùng một scan duy nhất của cả danh sách nếu muốn trạng thái độc lập cho từng khách.

**Bài 7 — So sánh `reduce`.** Với số đầu vào `[2,3,5]`, hãy kiểm tra phần tử cuối của `scan` có bằng kết quả `reduce(0,Integer::sum)` không. Sau đó đảo nguồn và xác minh giá trị cuối giữ nguyên còn các prefix thay đổi.

**Gợi ý:** Trong miền số học không tràn, phép cộng có tính kết hợp nên tổng cuối không phụ thuộc thứ tự. Nhưng danh sách các **tổng trung gian** thì phụ thuộc.

## 14. Ghi nhớ

- `Gatherers.scan(initial, scanner)` biến mỗi phần tử đầu vào thành **một trạng thái tích lũy mới** và phát trạng thái đó xuống pipeline.
- `initial.get()` khởi tạo trạng thái **trước phần tử đầu tiên**, không tự trở thành phần tử đầu ra. Nguồn rỗng tạo **không đầu ra**.
- `scan` là intermediate operation và vẫn lazy; `toList`, `collect`, `reduce` hoặc các terminal operation khác mới kích hoạt pipeline.
- Dùng record hay snapshot bất biến cho trạng thái nhiều trường để tránh kết quả cũ bị thay đổi; cần số dư chính xác thì ưu tiên `BigDecimal`.
- Các trạng thái tiền tố **phụ thuộc encounter order**. Nếu yêu cầu kết quả lặp lại được, phải định nghĩa thứ tự trước khi scan; `parallelStream()` không tự biến quét tiền tố thành phép cộng độc lập.
- Chỉ cần **một kết quả cuối** thì cân nhắc `sum`/`reduce`/`collect`; cần trạng thái riêng theo từng khóa thì nhóm trước hoặc thiết kế Gatherer có state theo khóa.
