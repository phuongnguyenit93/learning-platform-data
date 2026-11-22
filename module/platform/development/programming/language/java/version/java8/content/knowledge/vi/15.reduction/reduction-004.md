# Accumulator, combiner và `reduce` ba tham số trong Java Stream

> **Phạm vi:** Bài này giải thích `Stream.reduce(identity, accumulator, combiner)` thuộc Java Stream API từ Java 8 và **vẫn là API hiện hành** trên JDK hiện đại. Các ví dụ sử dụng cú pháp và thư viện có từ Java 8, có thể biên dịch với `javac --release 8` trên JDK 17+. Không dùng cơ chế đã lỗi thời hay phụ thuộc vào chi tiết triển khai của một JDK.

## Mục tiêu

Sau bài này, bạn có thể:

- Nêu đúng vai trò của **identity**, **accumulator**, **combiner** và kiểu đầu vào `T` khác kiểu kết quả `U`.
- Tính từng kết quả trung gian trong luồng tuần tự và hiểu vì sao luồng song song cần `combiner`.
- Kiểm tra ba tính chất thiết yếu: identity trung hòa, combiner kết hợp (associative), accumulator tương thích với combiner.
- Viết reduction ba tham số tạo ra tổng hoặc đối tượng tổng hợp **bất biến**, chạy đúng trên cả `stream()` và `parallelStream()`.
- Nhận biết lúc nào nên dùng `mapToLong(...).sum()` hoặc `collect(...)` thay vì ép `reduce` vào bài toán không phù hợp.

## 1. Reduction ba tham số là gì?

**Reduction** (phép gộp) biến một luồng phần tử thành một giá trị tổng hợp duy nhất. Java cung cấp overload tổng quát:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
);
```

Trong đó `Stream<T>` chứa phần tử kiểu `T`, còn kết quả trả về thuộc kiểu `U`. Hai kiểu này **không bắt buộc giống nhau**.

| Thành phần | Kiểu hàm/giá trị | Vai trò |
| --- | --- | --- |
| `identity` | `U` | Giá trị trung hòa; đồng thời là kết quả cho stream rỗng |
| `accumulator` | `(U, T) -> U` | Nhận kết quả một phần và **một phần tử nguồn**, tạo kết quả một phần mới |
| `combiner` | `(U, U) -> U` | Gộp **hai kết quả một phần**, quan trọng khi giảm song song |
| Kết quả `reduce` | `U` | Một giá trị cuối cùng; không bọc trong `Optional` ở overload này |

Chẳng hạn với `Stream<String>` và yêu cầu tính tổng độ dài, `T` là `String` còn `U` là `Long`:

```java
List<String> words = Arrays.asList("Java", "Stream", "API");

long total = words.stream().reduce(
        0L,                                  // identity: Long
        (sum, word) -> sum + word.length(), // accumulator: Long + String -> Long
        Long::sum                            // combiner: Long + Long -> Long
);
// total == 13
```

Ở đây `"Java"` dài 4, `"Stream"` dài 6, `"API"` dài 3; tổng là **13**. `String.length()` đếm đơn vị mã UTF-16, vì vậy nếu bài toán thực tế yêu cầu đếm Unicode code point hoặc cụm ký tự hiển thị thì cần xác định cách đếm phù hợp; trong ví dụ ASCII này, cách hiểu rất rõ ràng.

### Vai trò của từng tham số

**`identity = 0L`:** bắt đầu từ không có độ dài. Nếu stream rỗng, giá trị kết quả là `0L`. Giá trị trung hòa phải phù hợp với phép gộp: `0 + x = x`.

**`accumulator = (sum, word) -> sum + word.length()`:** đọc một `String`, lấy độ dài và cộng vào một phần kết quả `Long`. Nó kết hợp **hai kiểu khác nhau** (`Long` và `String`).

**`combiner = Long::sum`:** cộng hai kết quả `Long` đã được tích lũy riêng. Không được nhầm `combiner` với một hàm nhận `String` mới; cả hai tham số của `combiner` đều có kiểu `U`.

`reduce` là một **terminal operation**. Với nguồn hữu hạn, nó thực hiện reduction để cho ra kết quả; không phải phép dừng sớm tùy ý như `findFirst()`. Stream đã được dùng cho terminal không thể được tiêu thụ lần thứ hai; hãy tạo stream mới nếu muốn chạy lại.

## 2. Cơ chế tuần tự và song song

### 2.1. Với stream tuần tự

Đối với ví dụ tổng độ dài, có thể suy nghĩ về phép gộp theo thứ tự sau:

| Bước | Phần tử mới `T` | Kết quả `U` trước | `accumulator` tạo |
| --- | --- | --- | --- |
| Khởi tạo | — | — | `identity = 0` |
| 1 | `"Java"` | 0 | 4 |
| 2 | `"Stream"` | 4 | 10 |
| 3 | `"API"` | 10 | 13 |

Một cách mô tả tương đương về **giá trị** là:

```java
long result = 0L;
for (String word : words) {
    result = result + word.length();
}
// result == 13
```

Đây là cách **hiểu kết quả**, không phải cam kết rằng implementation Stream bắt buộc phải thực thi đúng vòng lặp này. Với stream tuần tự đơn giản, `combiner` thường không cần được gọi, vì chỉ có một chuỗi kết quả một phần. **Không viết logic phụ thuộc vào số lần `combiner` thực sự được gọi.**

### 2.2. Với stream song song

Trong `words.parallelStream()`, thư viện có thể chia nguồn thành nhiều phần và reduction trên từng phần:

```text
Nguồn ["Java", "Stream", "API"]
                 |
        (Minh họa cách chia)
          /             \
 ["Java", "Stream"]      ["API"]
          |                |
 identity = 0         identity = 0
 acc("Java") = 4      acc("API") = 3
 acc("Stream") = 10         |
          \                /
           combiner(10, 3)
                  |
                 13
```

Đây là **một cách phân vùng minh họa**; Java không cam kết số lượng nhánh, kích thước nhánh, thứ tự gọi hay số lần gọi `combiner`. Đáp án cần ổn định **bất kể cách phân vùng hợp lệ nào**.

Vì vậy, phép gộp phải đúng khi thực hiện:

- Tích lũy toàn bộ dữ liệu một mạch; hoặc
- Tích lũy từng đoạn độc lập với `identity` rồi hợp nhất chúng bằng `combiner`.

Đó là lý do kiểm thử `parallelStream()` là một phần quan trọng, nhưng **một lần chạy đúng không tự chứng minh các quy luật đại số đã đúng**.

## 3. Những quy luật bắt buộc để reduction đúng

Ký hiệu `e` là `identity`, `a(u,t)` là `accumulator` và `c(u,v)` là `combiner`. JavaDoc yêu cầu `combiner` có tính kết hợp, có identity phù hợp và tương thích với accumulator.

### 3.1. Identity phải trung hòa cho combiner

Với mọi giá trị kết quả một phần `u`:

```text
c(e, u) = u
c(u, e) = u
```

Với `e = 0` và `c = cộng`, cả `0 + u` và `u + 0` đều bằng `u`.

**Sai:** khởi tạo bằng `10L` nhưng vẫn dùng phép cộng và mong kết quả bằng tổng độ dài thuần túy. Trong stream tuần tự, ví dụ trên cho ra `23` thay vì `13`; khi song song, `10` có thể bị đưa vào nhiều nhánh và khiến sai lệch phụ thuộc cách phân vùng.

### 3.2. Combiner phải có tính kết hợp (associativity)

Với mọi `a`, `b`, `c` (đang dùng như các kết quả `U`):

```text
combine(combine(a, b), c)
    = combine(a, combine(b, c))
```

Phép cộng số nguyên đáp ứng cách gộp này. Phép trừ không có tính kết hợp; ví dụ `(10 - 4) - 2 = 4` nhưng `10 - (4 - 2) = 8`. Vì Java có thể thay đổi cách nhóm phần tử, dùng phép trừ làm combiner thường gây kết quả không nhất quán.

**Tính kết hợp không giống tính giao hoán.** Ghép chuỗi theo đúng thứ tự có thể kết hợp theo nhóm nhưng không thể đảo thứ tự tùy ý: `"a" + "b"` khác `"b" + "a"`. Với dữ liệu có thứ tự (ordered stream), muốn bảo toàn thứ tự phải thiết kế phép gộp phù hợp với encounter order; đừng thay thế điều đó bằng phép hoán vị tự do. Nếu chỉ muốn nối chuỗi có dấu phân cách, `Collectors.joining(...)` thường dễ đọc và hiệu quả hơn.

### 3.3. Accumulator và combiner phải tương thích

Với mọi `u` kiểu `U` và `t` kiểu `T`:

```text
combine(u, accumulate(identity, t))
    = accumulate(u, t)
```

Áp dụng vào ví dụ: `u=7`, `t="Java"`. Vế trái bằng `7 + (0 + 4) = 11`; vế phải bằng `7 + 4 = 11`.

Một **lỗi tinh vi** là giữ accumulator cộng độ dài nhưng thay combiner bằng `Math::max`:

```java
// Không hợp lệ: accumulator cộng, combiner lấy max.
long broken = words.parallelStream().reduce(
        0L,
        (sum, word) -> sum + word.length(),
        Math::max);
```

`Math.max` có tính kết hợp và `0` trung hòa với các kết quả không âm, nhưng **không tương thích với accumulator**: `max(7, 4) = 7` khác `7 + 4 = 11`. Dù có vẻ đúng trên một số lần chạy tuần tự, reduction này không đáp ứng hợp đồng cho song song.

### 3.4. Hàm phải stateless và không can thiệp nguồn

`accumulator` và `combiner` phải **stateless**, **non-interfering**, không thay đổi collection nguồn đang được duyệt và không dựa vào mutable state chia sẻ giữa các worker. Cách an toàn là trả giá trị mới hoặc sử dụng giá trị bất biến, giống `Long` và lớp `Summary` ở phần sau.

Không dùng `AtomicInteger` đếm số lần combiner để suy ra một kết quả nghiệp vụ. Atomic counter chỉ giúp ghi nhận có đồng bộ; nó không biến thứ tự/tần suất gọi hàm thành một phần của hợp đồng Stream.

## 4. Ví dụ hoàn chỉnh, chạy được: tổng độ dài và đối tượng `Summary` bất biến

Ví dụ sau thể hiện **hai kiểu `U`**: `Long` để tính một tổng, và `Summary` để tổng hợp đồng thời *số từ* với *tổng độ dài*. Cả hai trường hợp đều có phép gộp tương thích, hoạt động trên luồng tuần tự lẫn song song.

Tạo tệp **`ThreeArgumentReductionDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class ThreeArgumentReductionDemo {

    // Bất biến: không sửa fields sau khi tạo, mỗi phép gộp trả object mới.
    static final class Summary {
        final long words;
        final long characters;

        Summary(long words, long characters) {
            this.words = words;
            this.characters = characters;
        }

        // Accumulator: Summary (U) + String (T) -> Summary (U).
        Summary add(String word) {
            return new Summary(words + 1, characters + word.length());
        }

        // Combiner: Summary (U) + Summary (U) -> Summary (U).
        Summary merge(Summary other) {
            return new Summary(
                    words + other.words,
                    characters + other.characters);
        }

        @Override
        public String toString() {
            return "Summary(words=" + words + ", chars=" + characters + ")";
        }
    }

    static Summary summarize(Stream<String> source) {
        return source.reduce(
                new Summary(0, 0),                   // identity
                (partial, word) -> partial.add(word), // accumulator
                (left, right) -> left.merge(right)   // combiner
        );
    }

    public static void main(String[] args) {
        List<String> words = Arrays.asList("Java", "Stream", "API");

        long sequentialLength = words.stream().reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum);

        long parallelLength = words.parallelStream().reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum);

        Summary sequential = summarize(words.stream());
        Summary parallel = summarize(words.parallelStream());
        Summary empty = summarize(Stream.<String>empty());

        System.out.println("Length sequential: " + sequentialLength);
        System.out.println("Length parallel: " + parallelLength);
        System.out.println("Summary sequential: " + sequential);
        System.out.println("Summary parallel: " + parallel);
        System.out.println("Summary empty: " + empty);

        if (sequentialLength != 13 || parallelLength != 13
                || sequential.words != 3 || sequential.characters != 13
                || parallel.words != 3 || parallel.characters != 13
                || empty.words != 0 || empty.characters != 0) {
            throw new AssertionError("Invalid reduction result");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 17+ nhưng **kiểm tra tương thích API/ngôn ngữ Java 8**:

```bash
javac --release 8 ThreeArgumentReductionDemo.java
java ThreeArgumentReductionDemo
```

Hoặc dùng `javac ThreeArgumentReductionDemo.java` / `java ThreeArgumentReductionDemo` nếu không cần bật ràng buộc `--release 8`. **Stdout đã kiểm chứng trên OpenJDK 24:**

```text
Length sequential: 13
Length parallel: 13
Summary sequential: Summary(words=3, chars=13)
Summary parallel: Summary(words=3, chars=13)
Summary empty: Summary(words=0, chars=0)
Checks passed.
```

**Giải thích:**

- Với `Long`, `identity=0L` và phép cộng làm cả accumulator/combiner thỏa ba quy luật.
- Với `Summary`, identity là `Summary(0,0)`. Mỗi từ tăng `words` một và tăng `characters` bằng độ dài từ; `merge` cộng riêng hai thành phần. Hai phép cộng này có tính kết hợp và identity trung hòa.
- Lớp `Summary` bất biến, nên không tồn tại trường hợp nhiều nhánh song song cùng thêm dữ liệu vào một đối tượng duy nhất.
- Đối với stream rỗng, không có từ để tích lũy; `reduce` trả đúng identity mới truyền vào (`Summary(0,0)`).
- Điều kiện ở cuối `main` xác nhận đầu ra của các bài thử. Những kiểm tra này không phụ thuộc số lần `combiner` được gọi hoặc cách Java chia tác vụ song song.

## 5. Cách tự kiểm tra quy luật của một accumulator/combiner

Trước khi đưa vào chương trình, hãy viết phép toán thành công thức và thử bộ dữ liệu đại diện:

1. **Rỗng:** `reduce(e, a, c)` phải trả `e` theo ý nghĩa nghiệp vụ.
2. **Một phần tử:** `a(e, t)` phải là kết quả của một phần tử `t`.
3. **Hai phần dữ liệu:** `c(reduce(A), reduce(B))` phải bằng reduction của `A` ghép với `B` trong đúng thứ tự hợp lệ.
4. **Identity:** `c(e, u)` và `c(u, e)` phải bằng `u`.
5. **Associativity:** `c(c(u,v),w)` và `c(u,c(v,w))` phải bằng nhau.
6. **Compatibility:** `c(u, a(e,t))` và `a(u,t)` phải bằng nhau.
7. **Chạy song song:** so sánh kết quả **theo giá trị**, không so sánh số lần/thứ tự callback.

Ví dụ kiểm tra tương thích với tổng độ dài có thể tính tay:

```text
e = 0, u = 10, t = "API" (length = 3)

combine(10, accumulate(0, "API"))
= combine(10, 3)
= 13

accumulate(10, "API")
= 10 + 3
= 13
```

Trong unit test thực tế, hãy so sánh `stream()`, `parallelStream()` với một oracle đơn giản (vòng lặp hoặc một phép tổng xác định) trên **stream rỗng, một phần tử, nhiều phần tử, dữ liệu lặp, nhiều kích thước nguồn**. Với kiểu tổng hợp đối tượng, kiểm tra từng field hoặc cung cấp `equals`/`hashCode` có ý nghĩa. Không kết luận tính đúng đắn đại số chỉ từ một kết quả song song trùng hợp.

### Ví dụ JUnit Jupiter ngắn (dự án cần JUnit 5)

Đoạn test này minh họa oracle độc lập với ba tham số của `reduce`. Nó là **mã trong một lớp test thuộc dự án có JUnit**, không phải chương trình chạy riêng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class ThreeArgumentReductionTest {

    @Test
    void parallelReductionMatchesExpectedLength() {
        List<List<String>> datasets = Arrays.asList(
                Collections.<String>emptyList(),
                Arrays.asList("Java"),
                Arrays.asList("a", "bb", "ccc", "d"),
                Collections.nCopies(1000, "abc"));

        for (List<String> data : datasets) {
            long expected = data.stream()
                    .mapToLong(String::length).sum();

            long sequential = data.stream().reduce(
                    0L, (sum, s) -> sum + s.length(), Long::sum);
            long parallel = data.parallelStream().reduce(
                    0L, (sum, s) -> sum + s.length(), Long::sum);

            assertEquals(expected, sequential);
            assertEquals(expected, parallel);
        }
    }
}
```

Những assert này kiểm tra **giá trị cuối cùng**. Nếu phép toán tự thân không associative/compatible, cần sửa định nghĩa phép toán trước; việc chỉ tăng số lần chạy test song song không thay thế chứng minh quy luật.

## 6. Vì sao không nên dùng `reduce` để tích lũy đối tượng có thể thay đổi?

Cách sau sai về hợp đồng reduction, dù đôi khi có vẻ chạy đúng khi dùng stream tuần tự:

```java
// PHẢN VÍ DỤ: không dùng trong code ứng dụng.
List<String> unsafe = words.parallelStream().reduce(
        new java.util.ArrayList<String>(),
        (list, word) -> {
            list.add(word);     // Thay đổi chính identity/partial list.
            return list;
        },
        (left, right) -> {
            left.addAll(right); // Có thể gộp với chính đối tượng dùng chung.
            return left;
        });
```

Vấn đề:

- `reduce` nhận một **giá trị identity**, không phải `Supplier` tạo container độc lập cho mỗi nhánh. Một `ArrayList` có thể bị các nhánh dùng chung; mutate nó vi phạm yêu cầu stateless/non-interfering và dễ tạo data race, kết quả lặp hoặc sai.
- `add`/`addAll` làm thay đổi đối tượng hiện có, khiến tính chất identity/compatibility theo giá trị không giữ như một reduction bất biến.
- Số lần phân vùng song song không được cố định. “Chạy thử vài lần đều đúng” không biến cách này thành an toàn.

Với **mutable reduction**, dùng `collect`:

```java
List<String> safe = words.parallelStream()
        .collect(java.util.stream.Collectors.toList());

String csv = words.parallelStream()
        .collect(java.util.stream.Collectors.joining(", "));
// csv == "Java, Stream, API" với nguồn có encounter order
```

`collect` ba đối số là API khác:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
);
```

`supplier` tạo container kết quả; `accumulator`/`combiner` của `collect` **có thể cập nhật container** theo hợp đồng mutable reduction. Dù trùng tên hai hàm, chữ ký và cách dùng **khác** với `Stream.reduce(U, BiFunction, BinaryOperator)`. Khi cần danh sách, map, grouping hay chuỗi, ưu tiên các collector có sẵn thay vì tự viết combiner thủ công.

## 7. So sánh ba overload của `reduce` và lựa chọn API

| API | Kết quả | Khi phù hợp |
| --- | --- | --- |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Không có identity tự nhiên; stream rỗng trả `Optional.empty()` |
| `reduce(T identity, BinaryOperator<T>)` | `T` | Đầu vào và kết quả cùng kiểu, có phép kết hợp associative và identity |
| `reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)` | `U` | Muốn gộp phần tử `T` thành kết quả khác kiểu `U` hoặc đồng thời map và gộp |

Trong bảng, `BiFunction<U,T,U>` là cách viết rút gọn để đọc; chữ ký thực dùng wildcard `? super T` như phần 1.

Ví dụ:

```java
// Không có identity: trả Optional<String>.
java.util.Optional<String> longest = words.stream().reduce(
        (a, b) -> a.length() >= b.length() ? a : b);

// Có identity và T = U = Integer.
int sum = Arrays.asList(2, 4, 6).stream()
        .reduce(0, Integer::sum);

// T = String, U = Long.
long lengths = words.stream().reduce(
        0L, (total, w) -> total + w.length(), Long::sum);
```

**Không nhất thiết dùng ba tham số khi API chuyên dụng rõ hơn.** Bài toán chỉ cộng độ dài thường gọn hơn và tránh boxing `Long` lặp lại bằng:

```java
long lengths = words.stream().mapToLong(String::length).sum();
```

Với thống kê số lượng, min/max/tổng/trung bình, cân nhắc `Collectors.summarizingInt`, `Collectors.summarizingLong`; với gộp nhiều field, thiết kế một kiểu kết quả bất biến và cân nhắc chi phí tạo object của mỗi bước `reduce`.

## 8. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Identity có giá trị mặc định nghiệp vụ nhưng không trung hòa | Lặp giá trị khi chia nhánh song song | Chọn identity đúng cho combiner, áp dụng giá trị mặc định sau reduction nếu cần |
| Combiner dùng phép trừ hoặc phép gộp không associative | Kết quả thay đổi theo cách nhóm | Dùng phép associative hoặc thiết kế mô hình tổng hợp khác |
| Combiner đúng riêng lẻ nhưng không tương thích accumulator | Sai khi chia thành partial results | Kiểm chứng `combine(u, accumulate(e,t)) = accumulate(u,t)` |
| Mutate `ArrayList`/`StringBuilder` trong `reduce` | Vi phạm hợp đồng; có thể race hay trùng dữ liệu | Dùng `collect`/`Collectors` cho mutable containers |
| Ghi log/count trong `combiner` rồi khẳng định số lần gọi | Phụ thuộc chiến lược triển khai | Assert giá trị cuối; đừng dựa tần suất callback |
| Dùng `parallelStream()` vì nghĩ chắc nhanh hơn | Tăng overhead, chia task và merge không rẻ | Đo benchmark trên tải và nguồn thực tế |
| Dùng `Integer` cho tổng có thể vượt khoảng 32-bit | Tràn số nguyên | Chọn `long`/`BigInteger` theo dữ liệu; kiểm tra giới hạn |
| Xem `String.length()` là số ký tự hiển thị | Sai với emoji/Unicode phức tạp | Xác định rõ đang đếm UTF-16, code point hay grapheme |
| Thực hiện terminal rồi gọi tiếp trên cùng stream | `IllegalStateException` ở nhiều tình huống | Tạo stream mới cho mỗi reduction |

**Thực tế hiệu năng:** Một reduction ba tham số hợp lệ có thể song song hóa, nhưng không đảm bảo chạy nhanh hơn. Với nguồn nhỏ, chi phí chia/gộp thường lớn hơn lợi ích; với object bất biến lớn, chi phí cấp phát có thể đáng kể. Quyết định tuần tự/song song dựa trên profiling/benchmark có cùng workload, không dựa trên số lõi CPU một cách đơn giản.

## 9. Bài tập tự kiểm tra

1. `Stream<String>` gộp thành tổng độ dài `Long`: xác định `T`, `U`, identity, kiểu accumulator, kiểu combiner.
2. Vì sao `reduce(10L, (n,s) -> n+s.length(), Long::sum)` không tính đúng *tổng độ dài* khi chia nhiều nhánh?
3. Cho `identity=0`, accumulator cộng 1 mỗi phần tử, combiner lấy `max`. Combiner đã associative, vậy còn thiếu quy luật nào?
4. Nêu hai lý do không nên truyền `new ArrayList<>()` vào `reduce` rồi gọi `add` trên cùng list.
5. Với `Summary(words,characters)`, viết kết quả của stream rỗng, stream chỉ chứa `"API"` và stream ba từ ở ví dụ.
6. Trường hợp nào nên dùng `collect(Collectors.toList())` thay vì `reduce`?

**Đáp án:**

1. `T=String`; `U=Long`; identity `0L`; accumulator `(Long,String)->Long`; combiner `(Long,Long)->Long`.
2. `10` không là phần tử trung hòa của phép cộng; nó có thể bị thêm lại trong từng nhánh.
3. Thiếu **compatibility**: `max(u, 1)` không luôn bằng `u + 1`.
4. Identity mutable có thể được chia sẻ; side effect gây sai quy luật và data race. `collect` tạo được container đúng hợp đồng.
5. `(0,0)`, `(1,3)` và `(3,13)`.
6. Khi cần container mutable làm đầu ra, đặc biệt với stream song song.

## Tài liệu chính thống (API vẫn đang áp dụng)

- [Oracle Java SE 26 — `Stream.reduce`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): overload ba tham số, quy luật identity/associativity/compatibility và các terminal operations.
- [Oracle Java SE 26 — `java.util.stream` package](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html): reduction, parallel reduction, non-interference và mutable reduction.
- [Java SE 8 — `Stream` API gốc](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): đối chiếu rằng API ba tham số đã tồn tại từ Java 8.

**Điểm cần nhớ:** `accumulator` thêm từng phần tử kiểu `T` vào một kết quả kiểu `U`; `combiner` gộp các kết quả kiểu `U`. Tính đúng đắn đến từ **các quy luật về identity, associativity và compatibility**, chứ không phụ thuộc vào việc chỉ chạy đúng trên một cách phân chia dữ liệu cụ thể.
