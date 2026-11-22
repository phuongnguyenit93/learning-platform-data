# Xây dựng và kiểm tra quy trình biến đổi có thể tái sử dụng trong Java

## 1. Bài toán: từ nhiều bước rời rạc đến một quy trình

Trong lập trình hàm, **quy trình biến đổi** (*transformation pipeline*) là một chuỗi các hàm nhỏ, mỗi hàm nhận đầu vào và trả về một kết quả. Đầu ra của bước trước được đưa vào bước sau. Thay vì lặp lại các thao tác chuẩn hóa, kiểm tra và biểu diễn ở nhiều nơi, ta kết hợp chúng thành một đơn vị có thể gọi lại và kiểm thử độc lập.

Giả sử ứng dụng nhận tên hoặc nhãn từ người dùng. Yêu cầu nghiệp vụ:

1. Bỏ khoảng trắng ở hai đầu.
2. Gộp các cụm khoảng trắng nội bộ thành một dấu cách.
3. Chuyển thành chữ thường theo quy tắc không phụ thuộc locale của máy.
4. Chỉ chấp nhận văn bản không rỗng và gồm các chữ cái ASCII `a-z` cùng dấu cách.
5. Khi hợp lệ, tạo nhãn dạng `{nội dung}`; dữ liệu `null`, rỗng hoặc sai quy tắc phải được từ chối.
6. Cùng quy trình được dùng để xử lý một giá trị đơn hoặc danh sách, với các bài kiểm thử chứng minh hành vi.

Luồng khái niệm:

```text
Giá trị đầu vào
      │
      ▼
Bỏ khoảng trắng hai đầu (strip)
      │
      ▼
Gộp khoảng trắng (collapse)
      │
      ▼
Chữ thường (lowercase)
      │
      ▼
Kiểm tra (nonBlank AND allowedCharacters)
      ├── Không hợp lệ ──> Không có kết quả
      │
      └── Hợp lệ ────────> Định dạng "{...}" ──> Kết quả
```

Mỗi bước biến đổi chỉ làm một việc; điều kiện hợp lệ tách riêng khỏi thao tác thay đổi dữ liệu. Ví dụ áp dụng trong bài này là một **quy tắc minh họa**; với tên người dùng thực, danh sách ký tự được chấp nhận cần phản ánh yêu cầu quốc tế hóa, dấu tiếng Việt và Unicode.

## 2. Các thành phần cần nắm

### `Function<T, R>` và tính kết hợp

`java.util.function.Function<T, R>` có phương thức trừu tượng `R apply(T value)`. Một `Function<String, String>` phù hợp với thao tác nhận một chuỗi và tạo chuỗi mới, chẳng hạn `String::strip`.

Hai phương thức mặc định tạo hàm mới từ các hàm đã có:

```java
Function<A, B> first = ...;
Function<B, C> second = ...;

Function<A, C> pipeline = first.andThen(second);
```

Diễn giải: `pipeline.apply(a)` tương đương `second.apply(first.apply(a))`. `andThen` đọc từ trái sang phải theo thứ tự thực hiện.

Với `compose`, thứ tự ngược lại:

```java
Function<B, C> second = ...;
Function<A, B> first = ...;

Function<A, C> pipeline = second.compose(first);
```

`second.compose(first).apply(a)` cũng bằng `second.apply(first.apply(a))`: hàm truyền vào `compose` chạy **trước** hàm đứng bên trái.

Ví dụ dễ phát hiện sai thứ tự:

```java
Function<Integer, Integer> addTwo = n -> n + 2;
Function<Integer, Integer> timesThree = n -> n * 3;

int leftToRight = addTwo.andThen(timesThree).apply(4); // (4 + 2) * 3 = 18
int rightToLeft = addTwo.compose(timesThree).apply(4); // (4 * 3) + 2 = 14
```

Hai pipeline không tương đương. Hoán đổi các bước chỉ an toàn khi có lý do nghiệp vụ hoặc chứng minh phù hợp; nhiều phép biến đổi không giao hoán.

### `UnaryOperator<T>` và `Function.identity()`

Khi kiểu đầu vào và đầu ra bằng nhau, `UnaryOperator<T>` là dạng chuyên biệt của `Function<T, T>`. Có thể khai báo các bước cùng kiểu như:

```java
UnaryOperator<String> trim = String::strip;
UnaryOperator<String> lowercase =
        s -> s.toLowerCase(java.util.Locale.ROOT);
```

Dù vậy, kết quả của `andThen` được khai báo theo `Function`, nên đừng mặc định rằng mọi phép ghép hai `UnaryOperator<String>` trả về biến có kiểu `UnaryOperator<String>`.

`Function.identity()` tạo hàm giữ nguyên đầu vào và có ích làm giá trị mặc định cho chuỗi biến đổi:

```java
Function<String, String> unchanged = Function.identity();
System.out.println(unchanged.apply("Java")); // Java
```

### `Predicate<T>` để ghép điều kiện

`Predicate<T>` có `boolean test(T value)` và các phép kết hợp:

- `p.and(q)` kiểm tra `p` trước; nếu `p` trả về `false`, không gọi `q`.
- `p.or(q)` kiểm tra `p` trước; nếu `p` trả về `true`, không gọi `q`.
- `p.negate()` đảo kết quả của `p`.
- `Predicate.not(p)` tạo predicate phủ định, thường dễ đọc với method reference.

```java
Predicate<String> nonBlank = Predicate.not(String::isBlank);
Predicate<String> onlyAsciiLettersAndSpaces =
        s -> s.matches("[a-z ]+");

Predicate<String> accepted = nonBlank.and(onlyAsciiLettersAndSpaces);
```

Điều kiện `accepted` nên được gọi **sau** chuẩn hóa vì bước chuẩn hóa chuyển chữ hoa thành chữ thường và cắt khoảng trắng. Nếu kiểm tra trước, cùng một dữ liệu có thể cho kết quả khác. `Predicate.and`/`or` dừng sớm giống các toán tử logic tương ứng; các predicate có tác dụng phụ có thể làm hành vi trở nên khó hiểu.

### `Optional<T>` để biểu diễn có/không có kết quả

`Optional.ofNullable(input)` tạo `Optional.empty()` nếu `input == null`, từ đó tránh gọi các method của `String` trên `null`.

Có thể nối:

```java
Optional.ofNullable(raw)
        .map(normalize)
        .filter(accepted)
        .map(format);
```

- `map(normalize)` biến đổi nếu còn giá trị.
- `filter(accepted)` giữ giá trị khi hợp lệ; khi sai, trả về empty.
- `map(format)` chỉ định dạng khi đã qua kiểm tra.

`Optional` là cách biểu diễn thao tác có thể không cho kết quả trong trường hợp này. Nếu nghiệp vụ cần báo **lý do** thất bại cụ thể (ví dụ rỗng, ký tự cấm, quá dài), cần kiểu kết quả có thông tin lỗi hoặc validation riêng; `Optional.empty()` không lưu nguyên nhân.

## 3. Thiết kế pipeline có thể dùng lại

Để pipeline rõ ràng, nên xác định **hợp đồng** của từng bước:

| Thành phần | Kiểu | Trách nhiệm | Ví dụ |
| --- | --- | --- | --- |
| `STRIP` | `Function<String, String>` | Bỏ khoảng trắng hai đầu | `" Java "` → `"Java"` |
| `COLLAPSE_SPACES` | `Function<String, String>` | Gộp khoảng trắng phù hợp regex | `"Java   API"` → `"Java API"` |
| `LOWER` | `Function<String, String>` | Chuyển sang chữ thường bằng `Locale.ROOT` | `"Java"` → `"java"` |
| `NORMALIZE` | `Function<String, String>` | Kết hợp ba bước theo thứ tự | `" JAVA   API "` → `"java api"` |
| `VALID` | `Predicate<String>` | Quyết định văn bản đã chuẩn hóa có hợp lệ hay không | `"java api"` → `true` |
| `PROCESS` | `Function<String, Optional<String>>` | Kiểm tra `null`, chuẩn hóa, lọc, định dạng | `" JAVA "` → `Optional[{java}]` |

Một số nguyên tắc thiết kế:

- **Một bước một trách nhiệm:** thay quy tắc gộp dấu cách không buộc viết lại bước kiểm tra.
- **Đầu vào/đầu ra rõ kiểu:** các bước biến đổi ghép bằng `Function.andThen` khi kiểu kết quả bước trước tương thích kiểu đầu vào bước sau.
- **Không chia sẻ trạng thái có thể thay đổi:** mỗi hàm tính kết quả từ đối số; tránh bộ đếm hay `StringBuilder` dùng chung nằm trong lambda.
- **Không thay đổi đầu vào:** `String` bất biến, nên ví dụ trả về giá trị mới. Với đối tượng mutable, cần nêu rõ chính sách sao chép hoặc thay đổi tại chỗ.
- **Quy tắc lỗi tường minh:** đầu vào `null` và dữ liệu không hợp lệ trả `Optional.empty()`; lỗi lập trình hoặc lỗi hệ thống không nên bị bắt chung rồi lặng lẽ biến thành empty.
- **Tái sử dụng ở nhiều ngữ cảnh:** một `PROCESS` chung giúp xử lý đơn và batch nhất quán; test trực tiếp từng hàm vẫn cần thiết để khoanh vùng lỗi.

## 4. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `ReusablePipelineDemo.java` với nội dung sau. Đây là chương trình độc lập, chỉ sử dụng Java Standard Library; phần `verify()` đóng vai trò bộ kiểm thử tự động tối giản, chạy mà không cần JUnit hoặc bật tùy chọn `-ea`.

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import java.util.function.Predicate;

public final class ReusablePipelineDemo {
    private static final Function<String, String> STRIP = String::strip;

    private static final Function<String, String> COLLAPSE_SPACES =
            s -> s.replaceAll("\\s+", " ");

    private static final Function<String, String> LOWER =
            s -> s.toLowerCase(Locale.ROOT);

    private static final Function<String, String> NORMALIZE =
            STRIP.andThen(COLLAPSE_SPACES).andThen(LOWER);

    private static final Predicate<String> VALID =
            Predicate.not(String::isBlank)
                    .and(s -> s.matches("[a-z ]+"));

    private static final Function<String, Optional<String>> PROCESS =
            raw -> Optional.ofNullable(raw)
                    .map(NORMALIZE)
                    .filter(VALID)
                    .map(s -> "{" + s + "}");

    private static final Function<Integer, Integer> ADD_TWO =
            n -> n + 2;

    private static final Function<Integer, Integer> TIMES_THREE =
            n -> n * 3;

    private ReusablePipelineDemo() {
    }

    private static List<String> processBatch(List<String> values) {
        return values.stream()
                .map(PROCESS)
                .flatMap(Optional::stream)
                .toList();
    }

    private static void expect(
            Object expected, Object actual, String caseName) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    caseName + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static void verify() {
        expect("java lambda", NORMALIZE.apply("  JAVA   LAMBDA "),
                "normalize whitespace and case");
        expect("api", NORMALIZE.apply("\tAPI  "),
                "normalize tab and surrounding spaces");

        Function<String, String> sameSequence =
                LOWER.compose(COLLAPSE_SPACES).compose(STRIP);
        expect(NORMALIZE.apply(" JAVA   API "),
                sameSequence.apply(" JAVA   API "), "compose equivalence");

        expect(Optional.of("{java lambda}"),
                PROCESS.apply(" JAVA  Lambda "), "valid input");
        expect(Optional.empty(), PROCESS.apply(" \t "), "blank input");
        expect(Optional.empty(), PROCESS.apply(" Java17 "), "invalid characters");
        expect(Optional.empty(), PROCESS.apply(null), "null input");

        expect(List.of("{java lambda}", "{new api}"),
                processBatch(List.of(
                        "  JAVA   LAMBDA ", "  ", " New   API ", "Java17")),
                "batch reuse");

        expect(18, ADD_TWO.andThen(TIMES_THREE).apply(4),
                "andThen order");
        expect(14, ADD_TWO.compose(TIMES_THREE).apply(4),
                "compose order");

        System.out.println("tests=PASS");
    }

    public static void main(String[] args) {
        verify();

        System.out.println(
                "andThen=" + ADD_TWO.andThen(TIMES_THREE).apply(4));
        System.out.println(
                "compose=" + ADD_TWO.compose(TIMES_THREE).apply(4));
        System.out.println(
                "one=" + PROCESS.apply("  JAVA   LAMBDA ").orElse("<invalid>"));
        System.out.println(
                "blank=" + PROCESS.apply(" \t ").orElse("<invalid>"));
        System.out.println(
                "batch=" + processBatch(List.of(
                        "  JAVA   LAMBDA ", "  ", " New   API ", "Java17")));
    }
}
```

Biên dịch và chạy (JDK 17 hoặc mới hơn):

```bash
javac ReusablePipelineDemo.java
java ReusablePipelineDemo
```

Kết quả stdout chính xác khi các kiểm tra thành công:

```text
tests=PASS
andThen=18
compose=14
one={java lambda}
blank=<invalid>
batch=[{java lambda}, {new api}]
```

Nếu kiểm thử thất bại, `expect` ném `AssertionError` với tên ca kiểm thử và hai giá trị để đối chiếu; chương trình dừng trước khi in `tests=PASS`. Dùng phương thức kiểm tra chủ động như vậy đáng tin cậy hơn lệnh `assert` của Java khi không chắc người chạy đã bật `-ea`.

### Vì sao ví dụ xử lý được `null`?

`PROCESS` bắt đầu bằng `Optional.ofNullable(raw)`. Khi `raw` là `null`, kết quả empty và các bước `NORMALIZE`, `VALID`, định dạng đều không chạy. Tuy nhiên, gọi thẳng `NORMALIZE.apply(null)` vẫn ném `NullPointerException`; hợp đồng xử lý `null` thuộc **pipeline tổng** chứ không phải mọi hàm thành phần.

### Vì sao xử lý hàng loạt không phải viết lại logic?

`processBatch` sử dụng lại `PROCESS` cho từng phần tử. `Optional::stream` cho 0 phần tử nếu empty và 1 phần tử nếu có dữ liệu, nên `flatMap(Optional::stream)` loại các giá trị bị từ chối. `Stream.toList()` trả về danh sách không cho phép chỉnh sửa cấu trúc; trong Java 17 kết quả này phù hợp nếu mục đích chỉ đọc.

`List.of(...)` không chấp nhận phần tử `null`. Nếu danh sách đầu vào thực tế có thể chứa `null`, chọn một nguồn dữ liệu cho phép `null` (chẳng hạn `Arrays.asList(...)`) rồi vẫn cho từng phần tử đi qua `PROCESS`. `PROCESS` sẽ loại giá trị `null` như đã kiểm tra trong test riêng.

## 5. Kiểm thử pipeline theo từng lớp

Một bài test tốt phải kiểm tra **hành vi quan sát được** và **hợp đồng biên**, không đơn thuần gọi hàm rồi in ra. Có ba cấp độ quan trọng.

### Kiểm thử từng biến đổi

Kiểm tra đầu vào bình thường và biến thể khó:

| Ca | Đầu vào | Kỳ vọng sau `NORMALIZE` |
| --- | --- | --- |
| Khoảng trắng và chữ hoa | `"  JAVA   LAMBDA "` | `"java lambda"` |
| Tab trước/sau | `"\tAPI  "` | `"api"` |
| Chuỗi rỗng | `""` | `""` |
| Chỉ toàn khoảng trắng | `"   "` | `""` |
| Đã chuẩn hóa | `"java api"` | `"java api"` |

Cần kiểm tra **thứ tự** bước. `STRIP.andThen(COLLAPSE_SPACES).andThen(LOWER)` và `LOWER.compose(COLLAPSE_SPACES).compose(STRIP)` phải cho cùng kết quả trên cùng dữ liệu. Khi hai cách dùng khác nhau mà cho kết quả khác, có thể xảy ra lỗi thứ tự hoặc lỗi trong một bước.

### Kiểm thử điều kiện hợp lệ và đầu ra tổng

| Đầu vào `PROCESS` | Kết quả |
| --- | --- |
| `" JAVA  Lambda "` | `Optional.of("{java lambda}")` |
| `" \t "` | `Optional.empty()` |
| `" Java17 "` | `Optional.empty()` |
| `null` | `Optional.empty()` |
| `"a b"` | `Optional.of("{a b}")` |
| `"..."` | `Optional.empty()` |

Test cả trường hợp bị từ chối sau khi chuẩn hóa. Ví dụ `Java17` trở thành `java17`, nhưng regex `"[a-z ]+"` không chấp nhận chữ số nên phải trả empty.

Đối với pipeline nhiều bước, các ca biên có ý nghĩa hơn hàng chục ca cùng loại: dữ liệu rỗng, null, ký tự không hợp lệ, khoảng trắng nhiều loại, dữ liệu đã chuẩn hóa, độ dài lớn (nếu có giới hạn nghiệp vụ), và trường hợp Unicode khi sản phẩm có hỗ trợ quốc tế hóa.

### Kiểm thử khả năng tái sử dụng

Một pipeline tái sử dụng phải cho kết quả nhất quán khi:

- Gọi nhiều lần với cùng đầu vào.
- Dùng trực tiếp trên một giá trị và dùng gián tiếp trong `Stream`.
- Dùng cho các phần tử khác nhau mà không “rò” trạng thái từ lần gọi trước sang lần gọi sau.
- Thực hiện các bước ở thứ tự đã công bố.

Trong ví dụ, `PROCESS` là một hàm không lưu trạng thái. `Function` và `Predicate` là giao diện, không tự bảo đảm tính thuần; tính nhất quán đến từ cách chúng ta triển khai các lambda.

## 6. Đặc tính đáng kiểm tra của quy trình

Ngoài so sánh một số đầu ra cụ thể, có thể xác định các **bất biến** (invariants) theo yêu cầu nghiệp vụ.

**Tính idempotent của chuẩn hóa:**

```java
String once = NORMALIZE.apply("  JAVA   API ");
String twice = NORMALIZE.apply(once);
expect(once, twice, "normalization is idempotent");
```

Với ba phép biến đổi được chọn trong bài, chuẩn hóa lại một giá trị đã chuẩn hóa không làm nó thay đổi. Phải kiểm chứng lại khi bổ sung bước mới, ví dụ thay thế ký tự hoặc thêm tiền tố, vì không phải mọi pipeline đều idempotent.

**Kết quả hợp lệ thỏa điều kiện:**

```java
String normalized = NORMALIZE.apply(" JAVA   API ");
if (!VALID.test(normalized)) {
    throw new AssertionError("normalized sample should be valid");
}
```

Khi `PROCESS` trả về giá trị, nghĩa là `VALID` đã cho `true` trên chuỗi chuẩn hóa trước khi thêm `{...}`. Đừng áp dụng `VALID` lên nhãn **sau định dạng**, vì dấu `{}` không được regex chấp nhận.

**Đầu vào ban đầu không bị biến đổi:**

```java
String raw = " JAVA ";
String transformed = NORMALIZE.apply(raw);
expect(" JAVA ", raw, "input remains unchanged");
expect("java", transformed, "new value");
```

Đây là đặc tính tự nhiên của `String` bất biến. Nếu pipeline xử lý DTO mutable hoặc collection có thể chỉnh sửa, phải test rõ bước nào sao chép và bước nào có thể thay đổi trạng thái.

## 7. Những sai lầm dễ gặp

### Sai thứ tự `compose` và `andThen`

`f.andThen(g)` nghĩa là `g(f(x))`; còn `f.compose(g)` nghĩa là `f(g(x))`. Khi các bước không giao hoán, nhầm lẫn sẽ làm thay đổi kết quả. Cách tự kiểm tra là viết biểu thức lồng nhau hoặc kiểm thử bằng các phép toán có kết quả khác rõ như cộng 2 và nhân 3.

### Ghép sai kiểu

Một bước `Function<String, Integer>` không thể nối trực tiếp vào bước `Function<String, String>` bằng `andThen`, vì bước sau đòi đầu vào `String`, trong khi bước trước tạo `Integer`. Hãy thiết kế đầu ra/đầu vào tương thích hoặc thêm bước chuyển kiểu có ý nghĩa.

### Kiểm tra dữ liệu tại sai thời điểm

Nếu regex `[a-z ]+` được kiểm tra trước khi chuyển sang chữ thường, `"JAVA"` bị loại. Trật tự chuẩn hóa → kiểm tra phải thể hiện ở cấu trúc pipeline và có test chứng minh.

### Không xác định chính sách `null` và lỗi

`String::strip`, `String::isBlank`, `String::length` đều cần receiver không `null`. `Optional.ofNullable` bảo vệ đường đi hiện tại; các bước gọi trực tiếp có thể vẫn ném lỗi. Không nên `catch (Exception)` rồi coi mọi sự cố là “dữ liệu không hợp lệ” vì sẽ che khuất lỗi lập trình hoặc lỗi hạ tầng.

### Dùng lambda có tác dụng phụ

Ví dụ sau không thích hợp làm bước biến đổi tái sử dụng ở nhiều luồng:

```java
// Minh họa mã có vấn đề: dùng trạng thái bên ngoài.
int[] counter = {0};
Function<String, String> withCounter = s -> {
    counter[0]++;
    return counter[0] + ":" + s;
};
```

Cùng một chuỗi nhưng các lần gọi cho kết quả khác nhau, lại có nguy cơ tranh chấp khi chạy song song. Tốt hơn là tách số thứ tự ra khỏi quy tắc chuẩn hóa, truyền ngữ cảnh rõ ràng, hoặc để bước xử lý trạng thái nằm ở lớp điều phối.

### Dùng quy tắc văn bản không phù hợp dữ liệu thật

`strip()` dùng tiêu chí khoảng trắng của `Character.isWhitespace`; `replaceAll("\\s+", " ")` dùng lớp `\s` của Java regex với hành vi mặc định; hai tiêu chí không đồng nhất cho toàn bộ Unicode. Regex `[a-z ]+` cũng chỉ chấp nhận chữ cái ASCII thường và dấu cách. Ví dụ chủ ý giới hạn như vậy để dễ kiểm thử, **không phải bộ chuẩn hóa tên người đa ngôn ngữ**.

Nếu sản phẩm cần hỗ trợ dấu tiếng Việt, Unicode và các quy tắc nghiệp vụ khác, phải thiết kế lại điều kiện chấp nhận, cách xử lý khoảng trắng và tập ca kiểm thử; không nên chỉ đổi regex mà giữ nguyên kỳ vọng cũ.

### Tối ưu hóa quá sớm và dùng Stream không phù hợp

`String.matches` biên dịch biểu thức chính quy cho từng lời gọi; nếu số lượng bản ghi lớn, có thể cân nhắc `Pattern.compile(...)` một lần rồi dùng `pattern.matcher(s).matches()`, sau khi đo đạc. Với các bước nghiệp vụ có I/O hoặc ngoại lệ checked, `Function` thuần đơn giản có thể không đủ: cần chính sách lỗi và giao diện hàm thích hợp. Chỉ dùng Stream khi nó làm luồng rõ hơn; vòng lặp thông thường vẫn là lựa chọn đúng trong các tình huống cần điều khiển hoặc báo lỗi chi tiết.

## 8. Mở rộng theo hướng cấu hình và test dễ bảo trì

Khi pipeline phát triển, có thể đóng gói các bước bằng một lớp service hoặc factory nhận các `Function` và `Predicate` qua constructor. Nhờ vậy, test có thể thay thế riêng quy tắc chuẩn hóa, kiểm tra hoặc định dạng mà không sao chép toàn bộ pipeline.

Ví dụ hàm ghép độc lập:

```java
static <T, U> Function<T, Optional<U>> validatedTransform(
        Function<T, U> transform,
        Predicate<? super U> valid) {
    return input -> Optional.ofNullable(input)
            .map(transform)
            .filter(valid);
}
```

Đoạn mã này là **phương thức minh họa**, đặt trong một class Java có import `Function`, `Predicate`, `Optional`; nó không phải tệp nguồn độc lập. `Function<T, U>` cho phép kiểu đầu ra khác đầu vào; predicate được kiểm tra trên giá trị `U`. Chính sách `null` vẫn dựa vào `Optional` và `Optional.map`: nếu đầu vào null hoặc transform trả null, kết quả empty. Nếu cần phân biệt hai trường hợp này, thay `Optional` bằng cấu trúc trả về có lý do.

Test ghép hàm nên tập trung vào hợp đồng và các trường hợp lỗi, thay vì kiểm tra chi tiết bên trong mọi lambda. Ví dụ, với một factory có thể cấu hình, test chứng minh: transform gọi đúng một lần trên dữ liệu hợp lệ, predicate nhận đầu ra đã transform, đầu vào null không kích hoạt transform, và giá trị bị từ chối không đi tới bước định dạng.

## 9. Bài tập tự luyện

1. Thêm giới hạn độ dài đã chuẩn hóa bằng `Predicate<String> withinLimit = s -> s.length() <= 20;`, sau đó kết hợp `VALID.and(withinLimit)`. Viết test độ dài đúng 20 và 21 ký tự.
2. Thay phần `{...}` thành mã định danh `"id:" + normalized`, rồi bảo đảm cả hàm xử lý đơn và `processBatch` sử dụng định dạng mới mà không trùng logic.
3. Viết test lặp gọi `PROCESS` với cùng đầu vào 100 lần và khẳng định kết quả luôn giống nhau.
4. Thử dữ liệu tiếng Việt có dấu, chẳng hạn `"  Tiếng Việt  "`; dự đoán vì sao quy tắc hiện tại loại bỏ nó. Sau đó thiết kế quy tắc ký tự hợp lệ thực tế và thêm các ca Unicode tương ứng.
5. Giải thích bằng biểu thức lồng nhau vì sao `ADD_TWO.andThen(TIMES_THREE)` cho 18, trong khi `ADD_TWO.compose(TIMES_THREE)` cho 14 với đầu vào 4.

Khi làm bài, hãy ghi rõ mỗi bước nhận gì, trả gì, có xử lý `null` hay không, chạy trước/sau bước nào và kiểm thử được điều kiện nào. Một pipeline đáng tái sử dụng là pipeline có **hợp đồng rõ, thứ tự chính xác, chính sách lỗi nhất quán và bộ test phát hiện thay đổi hành vi**.
