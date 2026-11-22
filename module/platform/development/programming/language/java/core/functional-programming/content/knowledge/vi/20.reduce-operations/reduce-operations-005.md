# `reduce()` ba tham số: `identity`, `accumulator` và `combiner` trong Java

## 1. Vì sao có `reduce` ba tham số?

Trong lập trình hàm, **rút gọn** (*reduction*) là quá trình kết hợp nhiều phần tử của một luồng dữ liệu thành một giá trị kết quả. Ví dụ: tính tổng, tính tổng độ dài các chuỗi hoặc gộp thông tin đơn hàng thành một bản thống kê.

Với `Stream<T>` trong Java, `reduce` có nhiều dạng. Dạng ba tham số đặc biệt quan trọng khi:

- **Kiểu phần tử nguồn `T` khác kiểu kết quả tích lũy `U`.** Chẳng hạn mỗi phần tử là `String` nhưng kết quả là `Integer`, hoặc mỗi phần tử là `OrderLine` nhưng kết quả là `Summary`.
- **Cần mô tả cách gộp hai kết quả tích lũy riêng rẽ**, nhất là khi Stream có thể chạy song song.
- **Muốn một kết quả cụ thể ngay cả khi Stream rỗng**, nhờ giá trị khởi đầu `identity`.

Chữ ký API của `java.util.stream.Stream<T>`:

```java
<U> U reduce(
        U identity,
        java.util.function.BiFunction<U, ? super T, U> accumulator,
        java.util.function.BinaryOperator<U> combiner);
```

Đọc chữ ký theo lời: từ `Stream<T>`, kết quả là một `U`; `identity` là giá trị trung hòa kiểu `U`; `accumulator` nhận kết quả đang có (`U`) và một phần tử nguồn (`T`) rồi tạo kết quả `U` mới; `combiner` nhận **hai kết quả `U`** rồi kết hợp chúng thành một `U`.

Ví dụ ngắn:

```java
int lengthSum = java.util.stream.Stream.of("aa", "bbb", "c")
        .reduce(
                0,                                // identity: Integer
                (sum, text) -> sum + text.length(), // U + T → U
                Integer::sum                      // U + U → U
        );

System.out.println(lengthSum); // 6
```

Ở đây `T = String`, `U = Integer`, nên dạng `reduce(identity, accumulator)` với hai tham số (đòi `T` và kết quả cùng kiểu trong `Stream<T>`) không thay thế trực tiếp được ví dụ này. Dạng ba tham số cho phép tích lũy một kiểu **khác** kiểu phần tử nguồn.

## 2. Ba thành phần đóng vai trò gì?

### `identity` — giá trị trung hòa

`identity` là trạng thái tích lũy ban đầu và phải là **phần tử trung hòa** của phép kết hợp `combiner`: kết hợp với nó không được làm đổi kết quả.

Với phép cộng số nguyên, identity là `0`:

```text
0 + x = x
x + 0 = x
```

Với phép nhân, identity là `1`:

```text
1 × x = x
x × 1 = x
```

Với một bản thống kê gồm số bản ghi, số lượng và doanh thu, identity có thể là `Summary(0, 0, 0)`: chưa xử lý phần tử nào thì cả ba chỉ số bằng 0.

`identity` còn là **kết quả trả về cho Stream rỗng**:

```java
int value = java.util.stream.Stream.<String>empty()
        .reduce(0, (sum, s) -> sum + s.length(), Integer::sum);

// value = 0
```

Trong xử lý song song, đừng hiểu identity là một giá trị chỉ được thêm một lần ở đầu toàn bộ Stream. Các nhánh con có thể bắt đầu từ identity của riêng chúng, rồi kết quả các nhánh mới được combiner gộp lại. Vì vậy, chọn identity không trung hòa có thể tạo sai lệch nghiêm trọng.

### `accumulator` — đưa một phần tử vào trạng thái đã có

Dạng tổng quát:

```text
accumulator: (U state, T element) -> U nextState
```

Ví dụ:

```java
(sum, text) -> sum + text.length()
```

Đối số thứ nhất là tổng độ dài đã tích lũy (`Integer`); đối số thứ hai là chuỗi tiếp theo (`String`). Kết quả trả về là một tổng mới (`Integer`).

Trong phần tổng hợp đơn hàng, `accumulator` có thể tăng số dòng, tăng số lượng và cộng thêm doanh thu của **một** dòng vào summary hiện có.

Không nên hiểu accumulator là “chỉ chạy ở chế độ tuần tự”. Nó cũng được dùng để rút gọn các phần tử bên trong những nhánh của phép xử lý song song. Khi có hai phần kết quả cần nhập lại, trách nhiệm thuộc về combiner.

### `combiner` — gộp hai trạng thái tích lũy

Dạng tổng quát:

```text
combiner: (U partialLeft, U partialRight) -> U merged
```

Ví dụ `Integer::sum` cộng hai tổng độ dài đã tính riêng. Với `Summary`, combiner cộng từng trường thống kê.

Sơ đồ khái niệm cho một Stream có bốn phần tử:

```text
                   Stream<T>
               t1  t2  t3  t4
                    │
           ┌────────┴────────┐
           │                 │
       nhánh trái        nhánh phải
     identity + t1       identity + t3
                + t2                + t4
           │                 │
          U1                U2
           └────────┬────────┘
                    ▼
              combiner(U1,U2)
                    │
                    ▼
                 kết quả U
```

Đây là **mô hình để hiểu**, không phải cam kết rằng Java luôn chia Stream thành đúng hai nhánh hoặc gọi combiner một lần. Kiểu phân vùng, số lần và thứ tự gọi combiner là chi tiết phụ thuộc nguồn, pipeline và cách thực thi. Với Stream tuần tự, combiner thường không được gọi; do đó thử chỉ chế độ tuần tự **không đủ** để phát hiện combiner viết sai.

## 3. `reduce` ba tham số khác các overload còn lại ra sao?

| Overload | Kết quả | Khi dùng |
| --- | --- | --- |
| `Optional<T> reduce(BinaryOperator<T> op)` | `Optional<T>` | Không cung cấp identity; Stream có thể rỗng |
| `T reduce(T identity, BinaryOperator<T> op)` | `T` | Phần tử và kết quả tích lũy có cùng kiểu `T` |
| `<U> U reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` | `U` | Kết quả `U` có thể khác kiểu nguồn `T`; cần mô tả cách gộp kết quả từng nhánh |

So sánh:

```java
// Cùng kiểu Integer: overload hai tham số.
int sum = java.util.stream.Stream.of(1, 2, 3)
        .reduce(0, Integer::sum);

// Khác kiểu: String -> Integer, overload ba tham số.
int totalChars = java.util.stream.Stream.of("a", "bb", "ccc")
        .reduce(0, (n, s) -> n + s.length(), Integer::sum);

// Không có identity: có thể trả Optional.empty().
java.util.Optional<Integer> max =
        java.util.stream.Stream.<Integer>empty()
                .reduce(Integer::max);
```

Các đoạn này minh họa độc lập và cần import đúng kiểu nếu không viết tên đầy đủ. Về mặt ý định, ví dụ tổng độ dài còn có cách biểu diễn tuyến tính rất rõ là `mapToInt(String::length).sum()`. Không cần dùng overload phức tạp nếu thao tác có sẵn diễn đạt đúng nghiệp vụ và dễ bảo trì hơn.

## 4. Ba quy tắc để rút gọn đúng — đặc biệt với `parallelStream()`

Một reduction có thể được thực hiện theo nhiều cách phân nhóm khác nhau. Để kết quả **đúng và ổn định**, phải đáp ứng những ràng buộc sau.

### 4.1. `identity` trung hòa với `combiner`

Với mọi kết quả tích lũy `u` hợp lệ:

```text
combiner(identity, u) = u
combiner(u, identity) = u
```

Khi gộp các tổng số học bằng phép cộng, `0` là trung hòa; `10` không phải trung hòa.

**Sai:**

```java
int wrong = java.util.stream.Stream.of(1, 2, 3)
        .reduce(10, Integer::sum, Integer::sum);
```

Nếu xử lý tuần tự, có thể thu được `16` vì bắt đầu từ `10` và cộng `1 + 2 + 3`. Nhưng `10` **không trung hòa** với phép cộng, nên các nhánh song song có thể tự đưa giá trị `10` vào tổng một lần mỗi nhánh, làm kết quả khác. Không có một kết quả song song cố định nào được bảo đảm để dự đoán ở đây. Sửa bằng identity `0`.

### 4.2. `combiner` kết hợp được (associative)

Với `u1`, `u2`, `u3`:

```text
combiner(combiner(u1, u2), u3)
    = combiner(u1, combiner(u2, u3))
```

Phép cộng số nguyên (trong ngữ nghĩa số nguyên Java) có tính kết hợp; phép trừ nói chung **không**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Nếu combiner không kết hợp được, việc đổi cách phân nhóm có thể làm thay đổi kết quả. Với số thực `double`/`float`, cần cẩn thận: phép cộng dấu phẩy động không kết hợp chính xác về mặt bit do làm tròn, nên thứ tự gộp khác có thể cho sai khác nhỏ. Khi tính tiền, cân nhắc dùng đơn vị nguyên nhỏ nhất hoặc `BigDecimal` và xác định chính sách làm tròn.

### 4.3. `accumulator` tương thích với `combiner`

Đây là quy tắc rất quan trọng của dạng ba tham số. Với kết quả tích lũy `u` và một phần tử nguồn `t`, cần có:

```text
combiner(u, accumulator(identity, t))
    = accumulator(u, t)
```

Diễn giải: nếu xử lý riêng `t` trên trạng thái trung hòa rồi gộp vào `u`, kết quả phải giống việc đưa `t` trực tiếp vào `u`. Nhờ đó Stream có thể chia phần tử thành các nhánh rồi gộp mà không làm đổi ý nghĩa bài toán.

Ví dụ tổng độ dài:

```text
identity = 0
accumulator(u, text) = u + text.length()
combiner(a, b) = a + b

combiner(u, accumulator(0, "abc"))
= u + (0 + 3)
= u + 3
= accumulator(u, "abc")
```

Với summary nhiều trường, combiner phải gộp **đúng các trường mà accumulator cập nhật**; nếu accumulator tăng số dòng nhưng combiner quên cộng số dòng của nhánh phải, xử lý tuần tự có thể vẫn đúng trong khi xử lý song song sai.

Hai hàm còn phải **không can thiệp vào nguồn** (*non-interfering*) và phù hợp tính **stateless** theo hợp đồng Stream: đừng để kết quả phụ thuộc vào biến đếm mutable dùng chung, dữ liệu bị sửa ngoài ý muốn hoặc tác dụng phụ bắt buộc phải xảy ra theo thứ tự cụ thể.

## 5. Ví dụ Java 17: tổng hợp đơn hàng thành một record bất biến

Giả sử mỗi phần tử nguồn là một dòng đơn hàng:

```text
Line(sku, quantity, unitPrice)
```

Ta muốn một kết quả `Summary` gồm:

- `lines`: số dòng đã xử lý.
- `units`: tổng số lượng hàng.
- `revenue`: doanh thu = tổng `quantity × unitPrice` (đơn vị tiền nguyên đã quy ước).

Trong trường hợp này:

```text
T = Line
U = Summary
identity = Summary(0, 0, 0)

accumulator(Summary, Line) -> Summary mới
combiner(Summary, Summary) -> Summary mới
```

Chọn **record bất biến** giúp mỗi nhánh làm việc trên giá trị tổng hợp riêng mà không phải chỉnh sửa một accumulator chia sẻ. Việc tạo Summary mới cho từng phần tử có chi phí allocation, nhưng rõ nghĩa, an toàn về mặt trạng thái, dễ kiểm thử. Nếu đầu vào rất lớn và hiệu năng là trọng tâm, có thể cân nhắc `collect` với container mutable đúng hợp đồng hoặc phép tổng hợp chuyên biệt, thay vì thay đổi tùy tiện reduce thành mutate state chung.

### Chương trình đầy đủ

Tạo file `ThreeArgumentReduceDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

public class ThreeArgumentReduceDemo {
    record Line(String sku, int quantity, long unitPrice) {}

    record Summary(long lines, long units, long revenue) {}

    private static final Summary ZERO = new Summary(0, 0, 0);

    private static final BiFunction<Summary, Line, Summary> ACCUMULATE =
            (summary, line) -> new Summary(
                    summary.lines() + 1,
                    summary.units() + line.quantity(),
                    summary.revenue() + (long) line.quantity()
                            * line.unitPrice());

    private static final BinaryOperator<Summary> COMBINE =
            (left, right) -> new Summary(
                    left.lines() + right.lines(),
                    left.units() + right.units(),
                    left.revenue() + right.revenue());

    static Summary summarize(Stream<Line> lines) {
        return lines.reduce(ZERO, ACCUMULATE, COMBINE);
    }

    static void expect(Object expected, Object actual, String name) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static List<Line> sample() {
        return List.of(
                new Line("A", 2, 100),
                new Line("B", 3, 70),
                new Line("C", 1, 200),
                new Line("D", 4, 25));
    }

    static void runTests() {
        List<Line> lines = sample();
        Summary expected = new Summary(4, 10, 710);

        expect(expected, summarize(lines.stream()),
                "sequential summary");
        expect(expected, summarize(lines.parallelStream()),
                "parallel summary");
        expect(ZERO, summarize(Stream.<Line>empty()),
                "empty stream");
        expect(new Summary(1, 2, 200),
                summarize(lines.stream().limit(1)),
                "single row");

        // identity phải trung hòa với combiner.
        expect(expected, COMBINE.apply(ZERO, expected),
                "left identity");
        expect(expected, COMBINE.apply(expected, ZERO),
                "right identity");

        // Tương thích giữa accumulator và combiner.
        Line one = lines.get(0);
        Summary partial = new Summary(5, 9, 500);
        expect(ACCUMULATE.apply(partial, one),
                COMBINE.apply(partial,
                        ACCUMULATE.apply(ZERO, one)),
                "accumulator/combiner compatibility");

        int totalLength = Stream.of("aa", "bbb", "c")
                .reduce(0,
                        (sum, word) -> sum + word.length(),
                        Integer::sum);
        expect(6, totalLength, "different source/result types");

        int squareSum = Stream.of(1, 2, 3, 4)
                .reduce(0, (sum, n) -> sum + n * n, Integer::sum);
        expect(30, squareSum, "squares");
    }

    public static void main(String[] args) {
        runTests();

        List<Line> lines = sample();
        Summary sequential = summarize(lines.stream());
        Summary parallel = summarize(lines.parallelStream());
        Summary empty = summarize(Stream.<Line>empty());

        int totalLength = Stream.of("aa", "bbb", "c")
                .reduce(0,
                        (sum, word) -> sum + word.length(),
                        Integer::sum);
        int squareSum = Stream.of(1, 2, 3, 4)
                .reduce(0, (sum, n) -> sum + n * n, Integer::sum);

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
        System.out.println("lengths=" + totalLength);
        System.out.println("squares=" + squareSum);
        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac ThreeArgumentReduceDemo.java
java ThreeArgumentReduceDemo
```

Stdout kỳ vọng:

```text
sequential=Summary[lines=4, units=10, revenue=710]
parallel=Summary[lines=4, units=10, revenue=710]
empty=Summary[lines=0, units=0, revenue=0]
lengths=6
squares=30
tests=PASS
```

### Đối chiếu phép tính

Các dòng mẫu:

| SKU | Quantity | Unit price | Revenue |
| --- | ---: | ---: | ---: |
| A | 2 | 100 | 200 |
| B | 3 | 70 | 210 |
| C | 1 | 200 | 200 |
| D | 4 | 25 | 100 |
| **Tổng** | **10** | | **710** |

Do có bốn dòng nên `lines=4`. Cả `ACCUMULATE` lẫn `COMBINE` đều trả **record mới**, không ghi đè vào đối tượng `Summary` được truyền vào. Thống kê tổng được tạo với phép cộng trường-với-trường, nên thích hợp để các nhánh độc lập tạo kết quả rồi gộp lại.

Dòng `ZERO = new Summary(0, 0, 0)` là trạng thái khởi đầu có thể dùng lại vì immutable. Ngược lại, dùng cùng một `ArrayList` hay `StringBuilder` mutable làm identity sẽ rất dễ làm hỏng dữ liệu, đặc biệt khi các nhánh chạy song song.

Phương thức `runTests()` so sánh cả giá trị tuần tự, song song, Stream rỗng, một dòng, hai phía identity, khả năng tương thích accumulator/combiner và ví dụ khác kiểu nguồn. Test chủ động ném `AssertionError` nên **không cần** tham số JVM `-ea`.

## 6. Vì sao chạy song song vẫn ra cùng kết quả?

Theo mô hình toán học, xét bốn dòng mẫu chia thành hai nhóm:

```text
Nhóm 1: A, B
  Summary(lines=2, units=5, revenue=410)

Nhóm 2: C, D
  Summary(lines=2, units=5, revenue=300)

Combiner:
  Summary(2+2, 5+5, 410+300)
= Summary(4, 10, 710)
```

Nếu Java chia theo nhóm khác, `COMBINE` vẫn hợp lệ vì nó cộng các tổng độc lập và `ZERO` trung hòa. Thứ tự nhóm không ảnh hưởng kết quả cộng các số nguyên này (trong phạm vi không xảy ra overflow).

**Lưu ý:** đây là mô hình suy luận, không phải dự đoán cách triển khai cụ thể sẽ chia và gộp. Không nên in log trong combiner để suy ra chắc chắn cách `parallelStream` hoạt động ở mọi JVM và kích thước dữ liệu.

Một nguồn Stream có encounter order không buộc phép tổng hợp ba tham số phải duyệt đúng một thread hay duy trì thứ tự gọi `accumulator` theo cách dễ quan sát. Logic `ACCUMULATE`/`COMBINE` phải được thiết kế sao cho kết quả thống nhất với hợp đồng; các phép cộng thống kê ở đây không cần dựa vào thứ tự.

## 7. Những cách viết sai cần tránh

### Sai 1 — identity không trung hòa

```java
int wrong = Stream.of(1, 2, 3)
        .reduce(100, Integer::sum, Integer::sum);
```

`100` bị tính thành một phần của kết quả, và phép xử lý song song có thể đưa identity vào các nhánh riêng. Nếu yêu cầu là tổng các phần tử, phải chọn `0` chứ không chọn `100`. Nếu thực sự cần cộng thêm phí cố định 100 chỉ **một lần**, hãy tính tổng với identity `0` rồi cộng 100 **sau khi reduce**.

### Sai 2 — accumulator và combiner không cùng ý nghĩa

```java
// Sai ngữ nghĩa khi combiner quên cộng trạng thái bên phải.
int count = Stream.of("a", "bb", "ccc")
        .reduce(0,
                (n, s) -> n + 1,
                (left, right) -> left);
```

Chạy tuần tự có thể cho `3`; khi các phần tử được rút gọn thành nhiều nhánh, combiner có thể loại mất kết quả một nhánh. Điều kiện tương thích ở phần 4 không được thỏa mãn. Sửa bằng `Integer::sum`.

### Sai 3 — dùng phép không kết hợp được

```java
int value = Stream.of(1, 2, 3)
        .reduce(0,
                (left, right) -> left - right,
                (left, right) -> left - right);
```

Phép trừ không kết hợp được; kết quả phụ thuộc cách nhóm và thứ tự gộp. Hơn nữa `0` không là identity hai phía của phép trừ (`0 - x` khác `x`). Ví dụ này **không tuân thủ hợp đồng reduction**, dù chương trình có thể biên dịch.

### Sai 4 — làm biến đổi object mutable bên trong accumulator

```java
// Phản ví dụ: KHÔNG nên dùng reduce kiểu này.
java.util.List<String> wrong = Stream.of("a", "b", "c")
        .reduce(
                new java.util.ArrayList<String>(),
                (list, item) -> {
                    list.add(item); // Mutation trên trạng thái tích lũy.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

Đây là kiểu mã có vấn đề: cùng một đối tượng identity mutable có thể bị nhiều nhánh truy cập; trạng thái chia sẻ, tương tác giữa accumulator và combiner và yêu cầu hành vi kết hợp sẽ trở nên nguy hiểm. Không dùng `reduce` ba tham số như phép nối dữ liệu bằng side effect vào cùng một danh sách.

**Giải pháp đúng cho mutable accumulation:**

```java
java.util.List<String> values = Stream.of("a", "b", "c")
        .collect(
                java.util.ArrayList::new,
                java.util.ArrayList::add,
                java.util.ArrayList::addAll);
```

`collect(supplier, accumulator, combiner)` được thiết kế cho **mutable reduction**: supplier tạo container độc lập khi cần; accumulator cập nhật container; combiner gộp các container. Với `List` đầu ra đơn giản, có thể dùng `stream.toList()` nếu chấp nhận danh sách không thể chỉnh sửa từ Java 16. Hai cách trên không nên bị nhầm lẫn với `reduce(identity, ...)`.

### Sai 5 — dựa vào tác dụng phụ để kiểm chứng số lần gọi

```java
// Không nên viết logic dựa vào bộ đếm chung trong accumulator.
java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

int result = Stream.of(1, 2, 3)
        .reduce(0,
                (sum, value) -> {
                    calls.incrementAndGet();
                    return sum + value;
                },
                Integer::sum);
```

Trong một thử nghiệm nhỏ, bộ đếm có thể ghi lại số lần accumulator được gọi, nhưng dùng kết quả này làm hợp đồng nghiệp vụ là sai định hướng. Stream có thể chia công việc, kết hợp theo nhiều cách, hoặc tối ưu các bước khác trong pipeline. Nên kiểm thử **giá trị tổng hợp cuối cùng**, không phụ thuộc log, thread hay thứ tự gọi nội bộ.

### Sai 6 — bỏ qua tràn số và độ chính xác

```java
int total = Stream.of(Integer.MAX_VALUE, 1)
        .reduce(0, Integer::sum, Integer::sum);
```

Kết quả kiểu `int` sẽ tràn theo ngữ nghĩa số nguyên Java. Đây không phải lỗi của API `reduce`, mà là rủi ro khi chọn kiểu tích lũy và phép toán. Với các tổng lớn, cân nhắc tích lũy bằng `long`, `BigInteger` hoặc `BigDecimal` theo yêu cầu miền nghiệp vụ. Chọn kiểu đủ rộng **trước** khi cộng; sau khi `int` đã tràn thì cast sang `long` không khôi phục giá trị đúng.

Ví dụ:

```java
long safeTotal = Stream.of(Integer.MAX_VALUE, 1)
        .reduce(0L,
                (sum, n) -> sum + n.longValue(),
                Long::sum);

// 2147483648
```

`0L` bảo đảm `U = Long`; không áp dụng phép cộng `int` trước khi chuyển lên `long`. Dù vậy, `long` cũng có giới hạn; cần kiểm tra overflow khi dữ liệu có thể vượt khoảng của nó.

## 8. `reduce` hay `collect`?

Cả `reduce` và `collect` đều là thao tác kết thúc, nhưng chúng phù hợp với những kiểu rút gọn khác nhau.

| Tiêu chí | `reduce(identity, accumulator, combiner)` | `collect(supplier, accumulator, combiner)` |
| --- | --- | --- |
| Trạng thái kết quả | Thích hợp với giá trị bất biến | Thích hợp với container có thể thay đổi |
| Bước xử lý một phần tử | `BiFunction<U,T,U>` **trả về** `U` mới | `BiConsumer<R,T>` **cập nhật** container `R` |
| Gộp hai phần kết quả | `BinaryOperator<U>` **trả về** `U` | `BiConsumer<R,R>` **gộp mutable containers** |
| Khởi tạo | Một `identity` giá trị `U` | `Supplier<R>` tạo container |
| Ví dụ | Summary bất biến, tổng độ dài chuỗi | `ArrayList`, `HashMap`, nhóm bản ghi |
| Khi chạy song song | Cần identity trung hòa, các phép kết hợp đúng | Cần supplier/accumulator/combiner tuân thủ hợp đồng collector và an toàn trước việc sử dụng đồng thời |

Với bài toán tổng hợp số lượng/tiền, `reduce` ba tham số là công cụ tốt để **giải thích phép biến đổi từ `Line` sang `Summary`**. Nhưng với một số thống kê thông thường, JDK có sẵn giải pháp ngắn hơn:

```java
long units = lines.stream()
        .mapToLong(Line::quantity)
        .sum();
```

Trong đoạn trên `lines` là `List<Line>` và `Line` là record minh họa trong chương trình đầy đủ. Nếu chỉ cần tổng số lượng, `mapToLong(...).sum()` rõ hơn việc tạo một `Summary` nhiều trường.

Với grouping theo khóa, `Collectors.groupingBy(...)` hoặc một collector thích hợp thường dễ dùng hơn so với một `reduce` có cấu trúc `Map` mutable, miễn là tuân thủ nhu cầu thread safety và đặc tính thứ tự thực tế.

## 9. Kiểm thử hợp đồng tổng hợp

Một bộ kiểm thử cho `reduce` ba tham số nên kiểm tra cả **giá trị** lẫn **quy tắc toán học**:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Stream rỗng | Kết quả bằng identity, không phải `null` bất ngờ |
| Một phần tử | `accumulator(identity, t)` cho kết quả đúng |
| Nhiều phần tử | Tổng hợp đúng các trường và không bỏ dữ liệu |
| Identity hai phía | `combiner(identity,u)` và `combiner(u,identity)` đều bằng `u` |
| Combiner kết hợp | Gộp các trạng thái theo nhiều cách phân nhóm đều có cùng kết quả |
| Tương thích accumulator/combiner | Gộp một phần tử riêng lẻ vào `u` bằng xử lý trực tiếp phần tử |
| Tuần tự vs song song | Kết quả bằng nhau khi phép tính đáp ứng các quy luật và giới hạn kiểu số |
| Tràn số, null, dữ liệu sai | Chính sách xử lý tường minh theo miền nghiệp vụ |
| Trạng thái mutable | Không có sự chia sẻ trạng thái không an toàn hoặc side effect không mong muốn |

Với `Summary`, có thể kiểm tra thêm tính kết hợp của combiner:

```java
// Đoạn minh họa bên trong class ThreeArgumentReduceDemo.
Summary a = new Summary(1, 2, 200);
Summary b = new Summary(1, 3, 210);
Summary c = new Summary(2, 5, 300);

Summary leftGrouped = COMBINE.apply(COMBINE.apply(a, b), c);
Summary rightGrouped = COMBINE.apply(a, COMBINE.apply(b, c));

expect(leftGrouped, rightGrouped, "associativity");
```

Việc kiểm thử này giúp khoanh vùng lỗi trong combiner trước khi thử `parallelStream()`. Với dữ liệu lớn, test không nên chỉ so `count()` hoặc một trường; phải kiểm tra **tất cả trường** mà accumulator tạo ra.

## 10. Những lưu ý tinh tế về kiểu, thứ tự và hiệu năng

**Kiểu `U` khác `T` không tự chuyển đổi dữ liệu.** Nếu `T = OrderLine`, `U = Summary`, chính `accumulator` phải chuyển thông tin dòng vào Summary. Generic chỉ diễn tả hợp đồng kiểu; nó không tự biết cách tính doanh thu, số lượng hay trạng thái của ứng dụng.

**Không lẫn combiner với một bước map.** Combiner nhận **hai `U`**, không phải `U` và `T`. Nếu combiner chỉ biết xử lý một phần tử `T`, chương trình không có cách đúng để gộp hai kết quả đã tích lũy riêng.

**Không giả định combiner chỉ dùng ở parallel Stream.** Về mô hình lập trình, combiner là một phần bắt buộc của reduction ba tham số. Dù một pipeline tuần tự cụ thể có thể không gọi nó, phương thức phải đúng để đáp ứng hợp đồng và khi cách thực thi thay đổi.

**Không tự cho phép thay đổi nguồn khi reduction chạy.** Các lambda nên non-interfering: đừng thêm/xóa phần tử của nguồn đang duyệt, nhất là `ArrayList`, trong `accumulator`. Điều đó có thể làm sai kết quả hoặc tạo lỗi `ConcurrentModificationException` và không phải cấu trúc an toàn cho Stream song song.

**Giá trị bất biến rõ ràng nhưng có chi phí.** Bản ghi `Summary` mới được tạo mỗi lần tích lũy và gộp. Với dữ liệu lớn, chi phí cấp phát có thể đáng kể; cần đo bằng benchmark phù hợp và lựa chọn `collect` hoặc phép tổng hợp chuyên dụng nếu hiệu năng thực sự là yêu cầu. Không lấy việc `parallel()` làm lý do bỏ qua ràng buộc tính kết hợp hay thread safety.

**Nếu thứ tự là một phần của kết quả**, ví dụ nối chuỗi không được đảo thứ tự, hãy dùng phép kết hợp và nguồn có encounter order phù hợp, hoặc một collector đảm bảo cách xử lý đúng. Đừng phụ thuộc vào thứ tự gọi lambda quan sát qua `System.out.println` để quyết định nội dung kết quả.

**Tính chính xác của số thực** khác tính chính xác số nguyên. Khi tổng hợp `double`, thay đổi thứ tự nhóm có thể làm sai khác làm tròn. Với tiền tệ, chính sách làm tròn, đơn vị đo và kiểu số phải được xác định rõ; việc chọn overload `reduce` không tự giải quyết vấn đề.

## 11. Bài tập tự luyện

1. Cho `Stream.of("Java", "Stream", "API")`. Dùng `reduce(0, accumulator, combiner)` để tính tổng độ dài; dự đoán kết quả `13`. Viết test so sánh `stream()` và `parallelStream()`.
2. Viết record `Stats(long items, long chars)` và phương thức dùng `reduce` ba tham số để đếm số chuỗi và tổng độ dài trong một lần duyệt. Xây `identity`, `accumulator`, `combiner`; chứng minh tính trung hòa và tính kết hợp.
3. Trong chương trình `ThreeArgumentReduceDemo`, thêm một dòng `new Line("E", 5, 10)`. Cập nhật expected summary, kiểm tra cả tuần tự và song song. Doanh thu tăng thêm `50`, số lượng tăng thêm `5`, số dòng tăng thêm `1`.
4. Cố tình sửa combiner thành `new Summary(left.lines(), left.units() + right.units(), left.revenue() + right.revenue())`. Giải thích vì sao kết quả tuần tự có thể vẫn đúng nhưng parallel sai, và viết test cho lỗi.
5. Thử identity `new Summary(1,0,0)` rồi giải thích vì sao kết quả có thể sai khi Stream bị phân chia; sửa lại identity trung hòa.
6. So sánh `reduce` trả một `Summary` bất biến với `collect` vào một `ArrayList`; phân biệt `BiFunction` trả trạng thái mới và `BiConsumer` thay đổi container.
7. Tính tổng các số rất lớn bằng `Stream<Integer>.reduce(0L, (sum, n) -> sum + n.longValue(), Long::sum)` và kiểm tra kết quả với `Integer.MAX_VALUE` và `1`.

## 12. Tổng kết

`Stream.reduce(identity, accumulator, combiner)` là **rút gọn ba tham số** với khả năng biến `Stream<T>` thành một kết quả `U` khác kiểu phần tử nguồn:

- `identity` là giá trị trung hòa của trạng thái tích lũy và kết quả của Stream rỗng.
- `accumulator` nhận trạng thái `U` cùng một phần tử `T`, trả lại trạng thái `U`.
- `combiner` gộp **hai trạng thái `U`** — đặc biệt quan trọng khi Stream có thể phân chia để xử lý song song.

Một reduction đúng cần **identity trung hòa, combiner kết hợp được, accumulator tương thích với combiner**, cùng các hàm không gây tác dụng phụ can thiệp vào nguồn. Ưu tiên trạng thái bất biến cho `reduce`; dùng `collect` khi mục đích là tích lũy vào container mutable. Hiểu những hợp đồng này quan trọng hơn việc chỉ thuộc cú pháp, bởi chúng quyết định kết quả có còn đúng khi nguồn rỗng, khi phân nhóm khác nhau hoặc khi chuyển từ tuần tự sang song song.
