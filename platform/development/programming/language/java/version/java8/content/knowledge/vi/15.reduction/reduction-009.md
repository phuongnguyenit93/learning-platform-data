# Kiểm thử reduction tuần tự, song song và nguồn rỗng trong Java Stream

## 1. Mục tiêu và phạm vi

**Reduction** là phép gộp các phần tử của `Stream` thành một giá trị kết quả, chẳng hạn tổng, giá trị lớn nhất hoặc một bản tóm tắt. Bài này tập trung vào **kiểm thử tính đúng đắn** của phép `reduce` trong ba tình huống: nguồn dữ liệu có phần tử và chạy tuần tự; cùng nguồn đó nhưng chạy song song; nguồn rỗng. Đây là kiến thức của Java 8 Stream API vẫn được sử dụng trong các phiên bản Java hiện đại.

Sau bài học, bạn cần:

1. Phân biệt kết quả của ba overload `reduce` khi nguồn không rỗng và khi nguồn rỗng.
2. Viết test có **kết quả mong đợi độc lập** thay vì chỉ so sánh hai cách tính có thể cùng sai.
3. Kiểm tra các luật `identity`, `associativity` và `accumulator–combiner compatibility` trước khi kỳ vọng phép giảm chạy song song cho kết quả đúng.
4. Biết vì sao không nên xác nhận số luồng, thứ tự gọi accumulator, tốc độ, hay một lịch thực thi cụ thể trong unit test.
5. Nhận diện các phép giảm không an toàn như trừ liên tiếp hoặc dùng đối tượng tích lũy mutable chung.

Ví dụ hoàn chỉnh dùng **Java 17+** để dễ biên dịch và kiểm thử. Các overload `Stream.reduce` đã có từ Java 8; cú pháp `List.of`, `Stream.toList` và `Optional.isEmpty` xuất hiện ở các phiên bản sau Java 8, nhưng vẫn là API hiện hành.

## 2. Ba overload `reduce` và kết quả cần kiểm thử

Với `Stream<T>`:

| Overload | Ý nghĩa | Nguồn rỗng | Ví dụ |
| --- | --- | --- | --- |
| `T reduce(T identity, BinaryOperator<T> accumulator)` | Gộp các phần tử, bắt đầu từ phần tử đơn vị | Trả đúng `identity` | `numbers.stream().reduce(0, Integer::sum)` |
| `Optional<T> reduce(BinaryOperator<T> accumulator)` | Gộp khi không cung cấp phần tử đơn vị | Trả `Optional.empty()` | `numbers.stream().reduce(Integer::max)` |
| `<U> U reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` | Cho phép kiểu phần tử `T` khác kiểu kết quả `U` và gộp kết quả trung gian | Trả đúng `identity` | `words.stream().reduce(0, (n,s) -> n+s.length(), Integer::sum)` |

`identity` phải là **phần tử đơn vị** phù hợp, không chỉ là một “giá trị mặc định” bất kỳ. Với tổng, `0` là đơn vị: `0 + x = x`. Với phép nhân, `1` là đơn vị: `1 * x = x`. Với phép nối chuỗi, `""` là đơn vị: `"" + s = s`.

Đối với **primitive streams**, `IntStream.reduce(int, IntBinaryOperator)` trả về `int` và `IntStream.reduce(IntBinaryOperator)` trả về `OptionalInt`; tương tự đối với `LongStream`/`DoubleStream`. Vì vậy test nên so đúng kiểu, không ép mọi overload thành `Optional<T>`.

Bảng kiểm thử tối thiểu với phép **cộng số nguyên**:

| Dữ liệu | `reduce(0, Integer::sum)` | `reduce(Integer::sum)` | Kỳ vọng |
| --- | --- | --- | --- |
| `[]` | `0` | `Optional.empty()` | Không có phần tử, không có tổng tùy chọn |
| `[42]` | `42` | `Optional[42]` | Một phần tử |
| `[2, 3, 5]` | `10` | `Optional[10]` | Nhiều phần tử |
| `[1, …, 10_000]` | `50_005_000` | `Optional[50_005_000]` | Nguồn lớn, có khả năng chia thành các phần |

Đối với nguồn có thứ tự và phép toán hợp lệ, giá trị kết quả cộng phải như nhau khi dùng `stream()` và `parallelStream()`. Điều đó không có nghĩa hai cách chạy sử dụng cùng số lời gọi accumulator/combiner, hoặc đạt cùng tốc độ.

## 3. Vì sao phép giảm đúng khi chạy song song?

Với xử lý tuần tự, có thể hình dung cộng `[2, 3, 5]` dưới dạng `((0 + 2) + 3) + 5 = 10`. Khi song song, Stream có thể phân vùng nguồn, giảm trong từng vùng rồi kết hợp kết quả, ví dụ `(2 + 3) + 5 = 10`. Chỉ một số phép gộp mới bảo toàn kết quả khi cách nhóm thay đổi.

**Các luật cần kiểm tra:**

1. **Identity:** `combine(identity, u) == u` (và với phép toán cộng thường cũng có `combine(u, identity) == u`). Overload hai đối số yêu cầu identity là phần tử đơn vị của accumulator.
2. **Associativity (tính kết hợp):** `combine(combine(a, b), c) == combine(a, combine(b, c))`. Đây là khả năng đổi cách nhóm mà không đổi kết quả, **không** phải tính giao hoán (đổi thứ tự phần tử).
3. **Compatibility của overload ba đối số:** `combine(u, accumulate(identity, t)) == accumulate(u, t)` cho mọi giá trị tích lũy hợp lệ `u` và phần tử `t`.
4. **Stateless, non-interfering:** accumulator và combiner phải không phụ thuộc trạng thái mutable có thể bị tác vụ khác thay đổi; không sửa collection nguồn khi pipeline đang chạy. Cách gộp nên trả giá trị mới hoặc kết quả bất biến thay vì thay đổi một container chung.

Với phép tổng độ dài chuỗi:

```java
java.util.function.BiFunction<Integer, String, Integer> accumulate =
        (total, word) -> total + word.length();
java.util.function.BinaryOperator<Integer> combine = Integer::sum;
int identity = 0;
```

Đây là **đoạn mã minh họa** trong ngữ cảnh có các biến trên, không phải một chương trình độc lập. Với `u = 7` và `t = "Java"`, hai vế compatibility đều bằng `11`: `7 + (0 + 4) == 7 + 4`.

Không dùng phép trừ để viết reduction tổng quát có thể chạy song song:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Phép trừ **không kết hợp**. Đặc biệt, `Stream.of(10, 3, 2).reduce((a, b) -> a - b)` có thể tạo kết quả khác nhau tùy cách nhóm, nên không được yêu cầu kết quả tuần tự và song song luôn trùng nhau. Nếu viết `reduce(0, (a, b) -> a - b)`, `0` còn sai vai trò identity vì `0 - b != b`. Không dựa vào một giá trị sai tình cờ quan sát được của `parallelStream()` làm kết quả test cố định.

## 4. Chương trình tự kiểm thử hoàn chỉnh (Java 17+)

Tạo tệp **`ReductionChecks.java`** với mã dưới đây. Chương trình dùng các phương thức `checkEquals`/`checkTrue` để thất bại ngay bằng `AssertionError` nếu kết quả không đúng, **không phụ thuộc cờ `-ea`** (khác với từ khóa `assert` của Java).

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class ReductionChecks {
    private static void checkEquals(Object expected, Object actual, String name) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + ": expected " + expected
                    + ", got " + actual);
        }
    }

    private static void checkTrue(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        // Kiểm tra cả kết quả tuần tự và song song với expected độc lập.
        List<Integer> numbers = IntStream.rangeClosed(1, 10_000).boxed().toList();
        long expected = 50_005_000L;

        checkEquals(expected,
                numbers.stream().mapToLong(Integer::longValue).reduce(0L, Long::sum),
                "sequential sum");
        for (int round = 0; round < 10; round++) {
            checkEquals(expected,
                    numbers.parallelStream()
                            .mapToLong(Integer::longValue).reduce(0L, Long::sum),
                    "parallel sum at round " + round);
        }
        System.out.println("PASS sequential and parallel sums");

        // Nguồn rỗng: overload có identity khác overload trả Optional.
        List<Integer> empty = List.of();
        checkEquals(0, empty.stream().reduce(0, Integer::sum),
                "empty two-arg sequential");
        checkEquals(0, empty.parallelStream().reduce(0, Integer::sum),
                "empty two-arg parallel");
        checkTrue(empty.stream().reduce(Integer::sum).isEmpty(),
                "empty one-arg sequential");
        checkTrue(empty.parallelStream().reduce(Integer::sum).isEmpty(),
                "empty one-arg parallel");

        // Một phần tử: kết quả Optional phải có mặt.
        checkEquals(Optional.of(42), List.of(42).stream().reduce(Integer::sum),
                "single-element sequential");
        checkEquals(Optional.of(42), List.of(42).parallelStream().reduce(Integer::sum),
                "single-element parallel");
        System.out.println("PASS empty and single-element sources");

        // reduce ba đối số: phần tử là String, kết quả là Integer.
        List<String> words = List.of("Java", "Stream", "API");
        BiFunction<Integer, String, Integer> accumulator =
                (total, word) -> total + word.length();
        BinaryOperator<Integer> combiner = Integer::sum;

        checkEquals(13, words.stream().reduce(0, accumulator, combiner),
                "three-arg sequential");
        checkEquals(13, words.parallelStream().reduce(0, accumulator, combiner),
                "three-arg parallel");
        checkEquals(0, List.<String>of().stream().reduce(0, accumulator, combiner),
                "three-arg empty sequential");
        checkEquals(0, List.<String>of().parallelStream().reduce(0, accumulator, combiner),
                "three-arg empty parallel");
        System.out.println("PASS three-argument reduce");

        // Kiểm tra mẫu cho ba luật đại số.
        checkEquals(7, combiner.apply(0, 7), "left identity");
        checkEquals(7, combiner.apply(7, 0), "right identity");
        checkEquals(combiner.apply(combiner.apply(1, 2), 3),
                combiner.apply(1, combiner.apply(2, 3)), "associativity");
        checkEquals(accumulator.apply(7, "Java"),
                combiner.apply(7, accumulator.apply(0, "Java")),
                "accumulator/combiner compatibility");
        System.out.println("PASS identity, associativity, compatibility");

        // Khi cần nối chuỗi bằng container mutable, collect là lựa chọn đúng.
        checkEquals("Java,Stream,API",
                words.stream().collect(Collectors.joining(",")),
                "sequential joining");
        checkEquals("Java,Stream,API",
                words.parallelStream().collect(Collectors.joining(",")),
                "parallel joining");
        System.out.println("PASS ordered joining with collect");

        System.out.println("ALL REDUCTION CHECKS PASSED");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac ReductionChecks.java
java ReductionChecks
```

Kết quả chuẩn khi tất cả test đạt:

```text
PASS sequential and parallel sums
PASS empty and single-element sources
PASS three-argument reduce
PASS identity, associativity, compatibility
PASS ordered joining with collect
ALL REDUCTION CHECKS PASSED
```

**Đọc kết quả test đúng cách:**

- `expected = 50_005_000L` là tổng toán học của các số từ `1` đến `10_000`. Test so cả hai implementation với expected này, giúp bắt lỗi ngay cả khi tuần tự và song song cùng trả một số sai. Sử dụng `long` để tránh nhầm lẫn do giới hạn `int` nếu sau này tăng miền dữ liệu.
- Chạy 10 lượt song song là phép kiểm tra lặp có ích để phát hiện một số lỗi ngẫu nhiên. Nó **không chứng minh** code chắc chắn không có race condition hoặc môi trường chắc chắn dùng nhiều thread.
- Mỗi lệnh tạo Stream **mới** từ `numbers`, `empty` hoặc `words`. Một Stream đã qua terminal operation như `reduce` không thể tái sử dụng.
- Hai overload trả giá trị trực tiếp cần so `0` cho nguồn rỗng; overload không identity cần so `Optional.empty()`. Đừng gọi `get()` trên Optional rỗng.
- Phần kiểm tra ba luật chỉ dùng vài bộ giá trị mẫu nên là test minh họa; với hàm tùy biến cần mở rộng dữ liệu kiểm thử để tăng độ tin cậy.
- `Collectors.joining(",")` được chọn để gộp chuỗi giữ thứ tự gặp phần tử của nguồn `List`; không sử dụng một `StringBuilder` mutable làm identity trong `reduce`.

## 5. Viết unit test bằng JUnit Jupiter

Nếu dự án đã cấu hình **JUnit Jupiter** (JUnit 6 là thế hệ hiện hành trên Java 17+), thay kiểm tra bằng `main` bằng các phương thức `@Test`. Ví dụ sau là **tệp test dành cho dự án có dependency JUnit**, không thể chạy chỉ bằng lệnh `javac` với classpath JDK thuần.

Tệp **`ReductionJUnitTest.java`** trong nguồn test của dự án:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ReductionJUnitTest {
    @Test
    void sequentialAndParallelHaveTheSameKnownSum() {
        List<Integer> numbers = IntStream.rangeClosed(1, 1_000).boxed().toList();

        long sequential = numbers.stream()
                .mapToLong(Integer::longValue).reduce(0L, Long::sum);
        long parallel = numbers.parallelStream()
                .mapToLong(Integer::longValue).reduce(0L, Long::sum);

        assertEquals(500_500L, sequential);
        assertEquals(500_500L, parallel);
    }

    @Test
    void emptySourcesFollowTheOverloadContract() {
        List<Integer> empty = List.of();

        assertEquals(0, empty.stream().reduce(0, Integer::sum));
        assertEquals(0, empty.parallelStream().reduce(0, Integer::sum));
        assertTrue(empty.stream().reduce(Integer::sum).isEmpty());
        assertTrue(empty.parallelStream().reduce(Integer::sum).isEmpty());

        assertEquals(0, List.<String>of().stream()
                .reduce(0, (sum, s) -> sum + s.length(), Integer::sum));
        assertEquals(0, List.<String>of().parallelStream()
                .reduce(0, (sum, s) -> sum + s.length(), Integer::sum));
    }

    @Test
    void oneElementReturnsPresentOptional() {
        assertEquals(42, List.of(42).stream()
                .reduce(Integer::sum).orElseThrow());
        assertEquals(42, List.of(42).parallelStream()
                .reduce(Integer::sum).orElseThrow());
    }
}
```

Chạy bằng tác vụ test của dự án, chẳng hạn `mvn test` hoặc `gradle test` khi dự án đã cấu hình JUnit/JUnit Platform phù hợp. Không cần ép test chạy trong một số thread cụ thể. `assertEquals` xác minh **giá trị**, `assertTrue` xác minh hợp đồng Optional rỗng.

## 6. Thiết kế bộ test có giá trị

Không chỉ kiểm tra một nguồn nhiều phần tử. Ma trận sau bao quát các ranh giới quan trọng:

| Trường hợp | Điều cần xác nhận | Sai sót giúp phát hiện |
| --- | --- | --- |
| Nguồn rỗng `[]` | Identity được trả nguyên vẹn; no-identity trả Optional rỗng | Nhầm `0` với `Optional.empty()` hoặc truy cập `get()` |
| Một phần tử `[42]` | Kết quả đúng và Optional có mặt | Sai seed hoặc logic điều kiện dừng |
| Nhiều phần tử nhỏ `[2,3,5]` | Kết quả bằng `10` ở cả hai chế độ | Sai accumulator/combiner |
| Nguồn nhiều phần tử `1..10_000` | Cùng bằng `50_005_000` | Lỗi khi phân vùng hoặc kết hợp |
| Kiểu đầu vào khác kiểu đầu ra | `reduce(identity, accumulator, combiner)` đúng ở cả hai chế độ | Combiner không tương thích accumulator |
| Giá trị âm, số 0 hoặc chuỗi rỗng (nếu hợp lệ) | Hành vi đúng theo nghiệp vụ | Sai identity, bỏ sót trường hợp biên |
| Nguồn có thứ tự và phép nối chuỗi | Kết quả nối có thứ tự khi API bảo đảm | Nhầm xử lý đồng thời với thứ tự gặp phần tử |

**Oracle độc lập:** Với phép cộng, một vòng lặp `for` hoặc công thức tổng độc lập là phép đối chiếu tốt. Nếu chỉ viết `assertEquals(sequentialResult, parallelResult)`, hai kết quả có thể cùng sai. Với tính tổng tiền, chọn kiểu dữ liệu và quy tắc làm tròn phù hợp miền nghiệp vụ, không suy ra rằng cộng `double` luôn có thể so chính xác bit giữa hai cách nhóm.

**Luật đại số dưới nhiều dữ liệu:** Thử các bộ `a,b,c` khác nhau cho associativity, thử `identity` ở hai phía của combiner và thử các cặp `u,t` cho compatibility. Property-based testing có thể sinh nhiều bộ đầu vào để tăng khả năng phát hiện phản ví dụ, nhưng không thay thế việc thiết kế đúng luật.

**Lặp lại có kiểm soát:** Test với nguồn nhiều phần tử, chạy song song nhiều lần và so với oracle. Mỗi lần phải dựng pipeline mới. Tránh test phụ thuộc vào log, thứ tự thực thi, số lời gọi combiner, tên thread hoặc thời gian hoàn thành; những thứ này có thể thay đổi theo JDK và môi trường.

## 7. Các lỗi thường gặp khi kiểm thử reduction

### 7.1. Phép toán không kết hợp

`reduce` không thể tự sửa một phép toán vi phạm associativity. Với `(a - b) - c != a - (b - c)`, thay cách nhóm có thể thay kết quả. Một test chỉ chạy tuần tự và pass không đủ để chứng minh phép trừ có thể giảm song song an toàn. Chọn phép gộp có các luật phù hợp hoặc chuyển bài toán sang thuật toán tuần tự rõ ràng nếu bắt buộc giữ cách đánh giá theo thứ tự.

### 7.2. Identity không trung lập

```java
int wrong = java.util.stream.Stream.of(2, 3, 5)
        .reduce(10, Integer::sum); // 20, vì 10 không là identity của phép cộng
```

Đây là **đoạn minh họa**. Nếu yêu cầu là tính tổng các phần tử, expected là `10` và identity đúng phải là `0`. Trong reduction song song, identity có thể được dùng cho nhiều kết quả trung gian nên lỗi chọn seed càng nguy hiểm.

### 7.3. Combiner sai hoặc không tương thích

```java
List<String> words = List.of("Java", "API");
int wrongDesign = words.parallelStream().reduce(
        0,
        (total, s) -> total + s.length(),
        (left, right) -> left - right
);
```

`Integer::sum` mới là combiner đúng với accumulator cộng độ dài; combiner trừ phá vỡ associativity và compatibility. Không cố định một giá trị “sai dự kiến” trong test: tùy cách chia, biểu thức có thể cho những kết quả khác nhau. Đoạn trên là minh họa anti-pattern, không phải code nên dùng trong sản phẩm.

### 7.4. Dùng mutable identity trong `reduce`

Đừng viết `reduce(new StringBuilder(), (builder, s) -> builder.append(s), (a, b) -> a.append(b))` để giảm song song. Các hàm `append` sửa đối tượng đầu vào; các tác vụ có thể chia sẻ cùng identity mutable và vi phạm giả định của reduction, dẫn đến kết quả sai hoặc lặp dữ liệu. Dùng `collect(Collectors.joining(","))` cho nối chuỗi hoặc một Collector đúng hợp đồng khi cần tạo container mutable.

### 7.5. Phép cộng số thực không kết hợp tuyệt đối

Với `double`, thứ tự cộng có thể ảnh hưởng đến sai số IEEE 754. Ví dụ, về mặt dấu phẩy động, `(1e16 + -1e16) + 1` có thể cho `1`, còn `1e16 + (-1e16 + 1)` có thể cho `0`. Do đó không thiết kế kiểm thử bắt buộc tổng song song và tuần tự bằng nhau theo từng bit cho mọi dãy `double`. Tùy ứng dụng có thể dùng sai số dung sai phù hợp, thuật toán cộng chính xác hơn, hoặc `BigDecimal` với quy tắc làm tròn được định nghĩa rõ.

### 7.6. Tràn số nguyên

Cộng `int`/`long` có giới hạn biểu diễn. Nếu mong đợi tổng toán học vượt miền của kiểu, test nên xác định rõ chính sách: dùng kiểu rộng hơn, `BigInteger`, hoặc phát hiện tràn bằng `Math.addExact` khi phù hợp. Không coi kết quả tràn là tổng toán học chính xác.

### 7.7. Test không đáng tin do side effect hoặc phụ thuộc lịch chạy

Đếm số lần gọi accumulator bằng biến `int` dùng chung, sửa một `ArrayList` trong lambda hay ghi log rồi assert thứ tự lời gọi đều là các mẫu test dễ sai, đặc biệt khi song song. Dùng giá trị trả về và bất biến đại số làm tiêu chí chính. Test lặp có thể phát hiện một số race nhưng không chứng minh an toàn luồng; hãy loại bỏ chia sẻ trạng thái trong thiết kế.

### 7.8. Tái sử dụng Stream

```java
java.util.stream.Stream<Integer> s = java.util.stream.Stream.of(1, 2, 3);
int total = s.reduce(0, Integer::sum);
// s.reduce(0, Integer::sum); // Không hợp lệ: Stream đã kết thúc.
```

Một đối tượng Stream thường chỉ có thể được tiêu thụ một lần. Tạo `list.stream()`/`list.parallelStream()` mới cho mỗi assertion, hoặc dùng `Supplier<Stream<T>>` trả về Stream mới.

## 8. Quy trình áp dụng vào dự án

1. **Định nghĩa chính xác kết quả:** chọn oracle độc lập, kiểu dữ liệu và quy tắc làm tròn/overflow phù hợp.
2. **Chọn overload `reduce`:** có identity thì test identity trên nguồn rỗng; không có identity thì test Optional rỗng; khác kiểu đầu vào/đầu ra thì test cả accumulator và combiner.
3. **Kiểm tra luật trước khi song song:** identity, associativity, compatibility, stateless và không can thiệp nguồn.
4. **Chạy cùng một tập dữ liệu ở hai chế độ:** tạo các Stream mới, so cả hai với expected và với nhau khi các luật hợp lệ.
5. **Kiểm thử biên:** `[]`, một phần tử, nhiều phần tử, số 0/âm/chuỗi rỗng tùy miền dữ liệu.
6. **Xử lý lỗi đúng mục đích:** dùng `collect` cho mutable reduction; không đưa side effect vào `reduce`; không test số thread/tốc độ như hợp đồng chức năng.
7. **Đọc kết quả từ CI:** một trường hợp sai phải cho tên test và expected/actual rõ ràng, đủ để sửa luật gộp hoặc điều kiện biên.

## Tài liệu tham khảo hiện hành

- [Oracle Java SE 25 — Stream.reduce và các hợp đồng identity/accumulator/combiner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — Stream API: Reduction, Parallelism, Associativity, Non-interference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 25 — IntStream và reduce cho kiểu primitive](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html)
- [JUnit — tài liệu chính thức và JUnit Jupiter hiện hành](https://junit.org/)
