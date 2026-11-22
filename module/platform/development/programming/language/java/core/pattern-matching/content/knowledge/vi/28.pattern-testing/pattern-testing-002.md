# Kiểm thử flow branch với dữ liệu biên trong Java Pattern Matching

**Flow branch testing** là kỹ thuật thiết kế ca kiểm thử dựa trên **những đường đi khác nhau của chương trình**: điều kiện đúng/sai, nhánh `if/else`, `switch case`, guard `when`, fallback và trường hợp xử lý `null`. **Boundary-value testing** bổ sung những giá trị ở ngay trước, đúng tại và ngay sau ranh giới của một điều kiện, vì đây là nơi dễ xuất hiện lỗi `<`/`<=`, `>`/`>=` hoặc sai thứ tự nhánh.

Khi Java dùng **pattern matching**, một ca kiểm thử phải quan tâm cả hai câu hỏi:

1. **Pattern có khớp không?** Ví dụ selector có phải `Score`, `Message`, `Batch`; record con có phải `Score` khác `null` không?
2. **Sau khi pattern khớp, điều kiện bổ sung có đúng không?** Ví dụ `n < 0`, `n == 100`, `text.isBlank()` hay guard `when a == b`.

Hai bước này quyết định nhánh nào thực sự được thực thi. Kiểm thử chỉ một vài trường hợp “đẹp” thường bỏ sót những đường đi quan trọng.

**Phiên bản:** Chương trình chính sử dụng `record`, `sealed interface`, record patterns và pattern matching cho `switch` trên **Java 21+**. `record` ổn định từ Java 16, `sealed` từ Java 17; record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) ổn định từ Java 21. Chương trình đã được biên dịch bằng `javac --release 21`, không cần bật preview.

## 1. Phân biệt kiểm thử nhánh và kiểm thử giá trị biên

Giả sử logic nghiệp vụ phân loại một điểm số:

```java
if (n < 0) {
    return "NEGATIVE";
}
if (n == 0) {
    return "ZERO";
}
if (n == 100) {
    return "MAX";
}
if (n > 100) {
    return "OVER_LIMIT";
}
return "IN_RANGE";
```

Phân loại gồm năm **kết quả nhánh**: số âm, số 0, đúng 100, vượt 100 và 1–99. Chỉ kiểm tra `n = 50` chứng minh được một nhánh; nó không phát hiện được lỗi ở bốn nhánh còn lại.

Để kiểm tra các điều kiện có nguy cơ sai dấu, ta thường chọn các bộ ba biên:

| Ranh giới | Trước biên | Tại biên | Sau biên | Vì sao cần? |
| --- | ---: | ---: | ---: | --- |
| `0` | `-1` | `0` | `1` | Phân biệt âm, bằng 0 và dương |
| `100` | `99` | `100` | `101` | Phân biệt còn trong khoảng, đúng tối đa và vượt mức |

Bên cạnh đó, `Integer.MIN_VALUE` và `Integer.MAX_VALUE` giúp xác nhận hai cực của miền `int`. Các giá trị cực trị không thay thế bộ ba `-1/0/1` hoặc `99/100/101`; mỗi nhóm có mục tiêu khác nhau.

**Branch outcome coverage** là việc quan sát các kết quả phân loại đã định nghĩa. **Branch coverage** do công cụ như JaCoCo đo đạc là khái niệm khác: nó theo các cạnh điều khiển hoặc quyết định đã được instrument. Không nên tuyên bố “100% branch coverage” chỉ vì nhìn thấy tất cả chuỗi kết quả. Trong chương trình mục 7, ta kiểm tra được **13 nhãn kết quả** và 20 hàng dữ liệu, nhưng không giả định đó là số liệu coverage của JaCoCo.

## 2. Domain model để thử nhiều pattern và flow branch

Ta dùng một mô hình đóng gồm ba dạng đầu vào:

```java
sealed interface Input permits Message, Score, Batch {}

record Message(String text) implements Input {}
record Score(int points) implements Input {}
record Batch(Score first, Score second) implements Input {}
```

Ý nghĩa:

- `Message` có thành phần `String text`, cho phép kiểm tra `null`, chuỗi rỗng, chuỗi toàn khoảng trắng hoặc chuỗi có nội dung.
- `Score` chứa số nguyên `points`, phù hợp để kiểm tra các ranh giới số.
- `Batch` chứa hai `Score`, dùng để kiểm tra **nested record patterns** và nhánh dự phòng khi một record con bằng `null`.
- `Input` là `sealed` và các record đều là `final` mặc định. Trình biên dịch biết tập kiểu được phép nên `switch expression` có thể exhaustive mà không cần một `default` che những subtype mới.

Trong bài, `Batch` **cố ý không cấm thành phần `null`** để kiểm thử đường đi khi thiếu record con. Nếu domain thực tế yêu cầu hai thành phần luôn khác `null`, nên tạo bất biến trong constructor; khi đó các ca kiểm thử đầu vào `Batch(null, ...)` cần chuyển thành **kiểm thử constructor ném exception** thay vì kiểm thử nhánh phân loại.

## 3. Một switch có nhiều nhánh và guard

Dùng Java 21:

```java
static String classify(Input input) {
    return switch (input) {
        case null -> "NULL_SELECTOR";

        case Message(var text) when text == null -> "MISSING_TEXT";
        case Message(var text) when text.isBlank() -> "BLANK_TEXT";
        case Message(var text) when text.length() == 1 -> "ONE_CHAR";
        case Message(var text) -> "TEXT";

        case Score(int n) when n < 0 -> "NEGATIVE";
        case Score(int n) when n == 0 -> "ZERO";
        case Score(int n) when n == 100 -> "MAX";
        case Score(int n) when n > 100 -> "OVER_LIMIT";
        case Score(var n) -> "IN_RANGE";

        case Batch(Score(int a), Score(int b)) when a == b ->
                "EQUAL_BATCH";
        case Batch(Score(var a), Score(var b)) -> "DIFFERENT_BATCH";
        case Batch(var first, var second) -> "INCOMPLETE_BATCH";
    };
}
```

**Đoạn này là phương thức minh họa:** phải đặt nó trong lớp có các record đã khai báo. Chương trình độc lập ở mục 7 chứa đầy đủ mọi khai báo.

### Thứ tự case là một phần của yêu cầu kiểm thử

Một pattern **rộng** đặt trước case **hẹp** không chỉ làm chọn sai nhánh, mà trong nhiều trường hợp Java sẽ **không biên dịch** do lỗi dominance. Ở phương thức trên:

1. `Message(var text) when text == null` đi trước mọi phép gọi `text.isBlank()` để tránh truy cập tham chiếu `null`.
2. `Message(var text)` không guard đứng **sau** các nhánh có guard; nó bắt `Message` còn lại.
3. `Score(var n)` đứng cuối nhóm `Score` vì khớp mọi `Score` khác `null`, kể cả những điểm số ở ranh giới.
4. `Batch(Score(...), Score(...))` cần cả hai record con tồn tại. Nhánh cuối `Batch(var first, var second)` bao phủ `Batch` có một hoặc hai thành phần con bằng `null`.
5. `case null` xử lý **selector `input`** bằng `null`; `case Message(var text) when text == null` xử lý **đối tượng Message tồn tại** nhưng có thành phần `text` bằng `null`. Hai trường hợp hoàn toàn khác nhau.

Java kiểm tra dominance và exhaustiveness lúc biên dịch. Bộ kiểm thử runtime không thay thế các quy tắc của compiler, nhưng giúp xác nhận **thứ tự ưu tiên nghiệp vụ** và các guard ở sát ranh giới.

## 4. Kiểm thử guard đúng/sai và flow scoping

Flow analysis xác định khi nào pattern variable được dùng hợp lệ. Ví dụ:

```java
static String scoreWithIf(Object value) {
    if (!(value instanceof Score score)) {
        return "NOT_SCORE";
    }

    int n = score.points();
    if (n < 0) return "NEGATIVE";
    if (n == 0) return "ZERO";
    if (n == 100) return "MAX";
    if (n > 100) return "OVER_LIMIT";
    return "IN_RANGE";
}
```

Trong `if (!(value instanceof Score score))`:

- Nếu giá trị là `null` hoặc không phải `Score`, phép khớp thất bại và phương thức trả `NOT_SCORE`.
- Nếu không trả về, compiler biết `Score score` chắc chắn đã được ràng buộc; `score.points()` hợp lệ ở các lệnh sau nhờ **definite matching/flow scoping**.
- Các điều kiện `n < 0`, `n == 0`, `n == 100` và `n > 100` tạo đường đi khác nhau.

Phương thức này cố ý trả **cùng kết quả** với nhóm `case Score(...)` trong `classify`. Nhờ đó ta có thể viết **kiểm thử đối chiếu** hai cách triển khai trên cùng bảng dữ liệu. Đây là một bổ sung hữu ích, nhưng không thể thay thế việc xác định kết quả kỳ vọng độc lập từ đặc tả: nếu cả hai thuật toán cùng mắc lỗi, chúng vẫn có thể cho kết quả bằng nhau.

### Kiểm tra điều kiện kết hợp

```java
if (value instanceof Score score && score.points() > 100) {
    System.out.println("Over limit");
}
```

Vế phải của `&&` chỉ được đánh giá khi type pattern ở vế trái đã khớp. Khi kiểm thử, cần bao gồm: `value == null`, sai kiểu, `Score(100)` và `Score(101)`. Chúng lần lượt đi qua các đường **không khớp**, **không khớp**, **khớp nhưng guard sai**, **khớp và guard đúng**.

Đối với điều kiện phủ định và `||`, việc đánh giá ngắn mạch cũng ảnh hưởng đến đường đi: `!(value instanceof Score score) || score.points() > 100` hợp lệ vì chỉ khi vế trái phủ định sai, biến `score` mới được dùng ở vế phải. Khi xây dựng test, hãy kiểm tra cả hai đường short-circuit.

## 5. Bảng test case cho các giá trị biên

Bảng sau được viết **trước khi chạy chương trình** và đóng vai trò *expected oracle*: mỗi đầu vào được ánh xạ thủ công tới một kết quả được đặc tả.

### Selector null và chuỗi

| Ca kiểm thử | Đầu vào | Kỳ vọng | Ranh giới/nhánh |
| --- | --- | --- | --- |
| selector-null | `null` | `NULL_SELECTOR` | Giá trị selector null |
| text-null | `new Message(null)` | `MISSING_TEXT` | Thành phần record null |
| text-empty | `new Message("")` | `BLANK_TEXT` | Chuỗi rỗng |
| text-spaces | `new Message(" \\t")` | `BLANK_TEXT` | Chỉ có whitespace |
| text-one | `new Message("X")` | `ONE_CHAR` | Chiều dài bằng 1 |
| text-two | `new Message("AB")` | `TEXT` | Chiều dài bằng 2 |
| text-unicode | `new Message("á")` | `ONE_CHAR` | Một đơn vị UTF-16 |

Lưu ý `String.isBlank()` trả `true` với chuỗi rỗng và chuỗi chỉ chứa code points được Java xem là whitespace. Trong khi đó, `String.length()` đếm **UTF-16 code units**, không phải số grapheme mà người dùng nhìn thấy. Chẳng hạn một ký tự emoji có thể chiếm hai code units và được xử lý khác `"á"` trong bộ test. Nếu hợp đồng sản phẩm cần đếm ký tự theo code point hoặc grapheme, phải đổi cách tính và cập nhật test oracle, không chỉ đổi input.

### Giá trị số sát ranh giới

| Ca kiểm thử | Đầu vào | Kỳ vọng | Vai trò |
| --- | --- | --- | --- |
| score-min | `new Score(Integer.MIN_VALUE)` | `NEGATIVE` | Cực tiểu `int` |
| score-minus-one | `new Score(-1)` | `NEGATIVE` | Ngay trước 0 |
| score-zero | `new Score(0)` | `ZERO` | Đúng 0 |
| score-one | `new Score(1)` | `IN_RANGE` | Ngay sau 0 |
| score-99 | `new Score(99)` | `IN_RANGE` | Ngay trước 100 |
| score-100 | `new Score(100)` | `MAX` | Đúng 100 |
| score-101 | `new Score(101)` | `OVER_LIMIT` | Ngay sau 100 |
| score-max | `new Score(Integer.MAX_VALUE)` | `OVER_LIMIT` | Cực đại `int` |

Tại mốc `100`, phép thử `99/100/101` giúp phân biệt cách viết `n == 100` và `n > 100`. Không nên chỉ dùng `n = 200` rồi kết luận đã kiểm tra đúng ranh giới.

### Record con và nested patterns

| Ca kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| batch-equal | `new Batch(new Score(1), new Score(1))` | `EQUAL_BATCH` |
| batch-different | `new Batch(new Score(1), new Score(2))` | `DIFFERENT_BATCH` |
| batch-left-null | `new Batch(null, new Score(2))` | `INCOMPLETE_BATCH` |
| batch-right-null | `new Batch(new Score(2), null)` | `INCOMPLETE_BATCH` |
| batch-both-null | `new Batch(null, null)` | `INCOMPLETE_BATCH` |

Hai dòng đầu cùng khớp cấu trúc `Batch(Score(...), Score(...))` nhưng khác nhau ở guard `a == b`. Ba dòng cuối kiểm tra việc record pattern lồng **không khớp đối tượng con null**, trong khi `Batch(var first, var second)` vẫn khớp record ngoài và cho phép thành phần tham chiếu null.

Tổng cộng: **7 ca selector/chuỗi + 8 ca số + 5 ca batch = 20 ca**. Bộ test này có cả các ca lặp một nhãn kết quả: đó là chủ ý, vì hai input có cùng kết quả vẫn có thể phát hiện các lỗi khác nhau.

## 6. Nguyên tắc viết assert và đo bao phủ

Một ca kiểm thử không nên chỉ in kết quả. Nó cần **so sánh kết quả thực tế với giá trị mong đợi** rồi báo lỗi nếu khác:

```java
static void check(String label, String expected, String actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                label + ": expected=" + expected + ", actual=" + actual);
    }
}
```

Khi dùng bảng dữ liệu (*table-driven testing*), mỗi hàng có ba thông tin: tên ca, đầu vào, đầu ra kỳ vọng. Vòng lặp chạy từng hàng và gọi `check(...)`. Nếu một assert thất bại, chương trình kết thúc với `AssertionError` và thông báo nêu rõ test nào sai.

### Nhãn kết quả khác với % coverage

Ở ví dụ này, ta có thể thu thập `Set<String> outcomes` từ kết quả chạy và so sánh với tập **13 nhãn kết quả cần có**. Việc đó xác nhận từng **loại kết quả do đặc tả định nghĩa** đã được quan sát.

Tuy nhiên:

- Một nhãn kết quả có thể được sinh ra qua nhiều điều kiện hoặc đường đi khác nhau.
- Một đường có `when` thất bại rồi sang case tiếp theo vẫn là đường đi riêng mà việc đếm nhãn không nhất thiết thể hiện đầy đủ.
- Công cụ Java như JaCoCo đo **instruction, line và branch coverage** theo bytecode được instrument. Với pattern switch, cách Java compiler sinh bytecode có thể khác với cách ta đếm nhãn.
- **Coverage cao không bảo đảm các assert đúng.** Nếu test chỉ gọi phương thức rồi không so sánh với oracle độc lập, một nhánh chạy qua vẫn có thể sai ngữ nghĩa.

Nên kết hợp: **test oracle rõ ràng + trường hợp biên + theo dõi loại kết quả + đo coverage bằng công cụ**. Khi có điều kiện, thêm mutation testing để kiểm tra sức mạnh của bộ test.

## 7. Chương trình Java 21 hoàn chỉnh và có kiểm chứng

Lưu nguyên tệp sau thành **`FlowBranchBoundaryDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class FlowBranchBoundaryDemo {
    sealed interface Input permits Message, Score, Batch {}
    record Message(String text) implements Input {}
    record Score(int points) implements Input {}
    record Batch(Score first, Score second) implements Input {}
    record TestCase(String label, Input input, String expected) {}

    static String classify(Input input) {
        return switch (input) {
            case null -> "NULL_SELECTOR";
            case Message(var text) when text == null -> "MISSING_TEXT";
            case Message(var text) when text.isBlank() -> "BLANK_TEXT";
            case Message(var text) when text.length() == 1 -> "ONE_CHAR";
            case Message(var text) -> "TEXT";
            case Score(int n) when n < 0 -> "NEGATIVE";
            case Score(int n) when n == 0 -> "ZERO";
            case Score(int n) when n == 100 -> "MAX";
            case Score(int n) when n > 100 -> "OVER_LIMIT";
            case Score(var n) -> "IN_RANGE";
            case Batch(Score(int a), Score(int b)) when a == b -> "EQUAL_BATCH";
            case Batch(Score(var a), Score(var b)) -> "DIFFERENT_BATCH";
            case Batch(var first, var second) -> "INCOMPLETE_BATCH";
        };
    }

    static String scoreWithIf(Object value) {
        if (!(value instanceof Score score)) {
            return "NOT_SCORE";
        }
        int n = score.points();
        if (n < 0) return "NEGATIVE";
        if (n == 0) return "ZERO";
        if (n == 100) return "MAX";
        if (n > 100) return "OVER_LIMIT";
        return "IN_RANGE";
    }

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        TestCase[] matrix = {
            new TestCase("selector-null", null, "NULL_SELECTOR"),
            new TestCase("text-null", new Message(null), "MISSING_TEXT"),
            new TestCase("text-empty", new Message(""), "BLANK_TEXT"),
            new TestCase("text-spaces", new Message(" \t"), "BLANK_TEXT"),
            new TestCase("text-one", new Message("X"), "ONE_CHAR"),
            new TestCase("text-two", new Message("AB"), "TEXT"),
            new TestCase("text-unicode", new Message("á"), "ONE_CHAR"),
            new TestCase("score-min", new Score(Integer.MIN_VALUE), "NEGATIVE"),
            new TestCase("score-minus-one", new Score(-1), "NEGATIVE"),
            new TestCase("score-zero", new Score(0), "ZERO"),
            new TestCase("score-one", new Score(1), "IN_RANGE"),
            new TestCase("score-99", new Score(99), "IN_RANGE"),
            new TestCase("score-100", new Score(100), "MAX"),
            new TestCase("score-101", new Score(101), "OVER_LIMIT"),
            new TestCase("score-max", new Score(Integer.MAX_VALUE), "OVER_LIMIT"),
            new TestCase("batch-equal", new Batch(new Score(1), new Score(1)), "EQUAL_BATCH"),
            new TestCase("batch-different", new Batch(new Score(1), new Score(2)), "DIFFERENT_BATCH"),
            new TestCase("batch-left-null", new Batch(null, new Score(2)), "INCOMPLETE_BATCH"),
            new TestCase("batch-right-null", new Batch(new Score(2), null), "INCOMPLETE_BATCH"),
            new TestCase("batch-both-null", new Batch(null, null), "INCOMPLETE_BATCH")
        };

        Set<String> outcomes = new HashSet<>();
        int scoreChecks = 0;
        for (TestCase test : matrix) {
            String actual = classify(test.input());
            check(test.label(), test.expected(), actual);
            outcomes.add(actual);
            if (test.input() instanceof Score) {
                check("if-" + test.label(), test.expected(), scoreWithIf(test.input()));
                scoreChecks++;
            }
        }
        Set<String> required = Set.of(
            "NULL_SELECTOR", "MISSING_TEXT", "BLANK_TEXT", "ONE_CHAR", "TEXT",
            "NEGATIVE", "ZERO", "MAX", "OVER_LIMIT", "IN_RANGE",
            "EQUAL_BATCH", "DIFFERENT_BATCH", "INCOMPLETE_BATCH");
        if (!outcomes.equals(required)) {
            throw new AssertionError("branch outcomes mismatch: " + outcomes);
        }
        check("if-null", "NOT_SCORE", scoreWithIf(null));
        check("if-other-type", "NOT_SCORE", scoreWithIf(new Message("abc")));

        System.out.println("PASS matrix=" + matrix.length);
        System.out.println("PASS branch-outcomes=" + outcomes.size());
        System.out.println("PASS if-vs-switch=" + scoreChecks);
        System.out.println("PASS non-score-guards=2");
        System.out.println("example null=" + classify(null));
        System.out.println("example boundary=" + classify(new Score(100)));
        System.out.println("example nested-null=" + classify(new Batch(null, new Score(1))));
    }
}
```

Biên dịch và chạy bằng **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 -encoding UTF-8 FlowBranchBoundaryDemo.java
java FlowBranchBoundaryDemo
```

**Stdout chính xác:**

```text
PASS matrix=20
PASS branch-outcomes=13
PASS if-vs-switch=8
PASS non-score-guards=2
example null=NULL_SELECTOR
example boundary=MAX
example nested-null=INCOMPLETE_BATCH
```

Các dòng `PASS` được in **sau khi các phép kiểm tra thực sự hoàn thành**. Chúng không phải thông báo trang trí:

1. `matrix=20`: tất cả 20 ca đều so sánh `expected` với `actual` bằng `check(...)`, không có `AssertionError`.
2. `branch-outcomes=13`: tập kết quả quan sát khớp chính xác tập 13 nhãn kỳ vọng.
3. `if-vs-switch=8`: tám input dạng `Score` đi qua cả `classify` và `scoreWithIf`; cả hai đều phải cho kết quả bằng oracle của ca đó.
4. `non-score-guards=2`: kiểm tra hai trường hợp của `scoreWithIf` khi đầu vào là `null` và `Message`, cả hai đều trả `NOT_SCORE`.
5. Ba dòng cuối cho thấy ví dụ cụ thể của nhánh null selector, biên `100` và record con `null`.

Chương trình chạy được với `javac --release 21` và đã cho đúng bảy dòng stdout phía trên. Nó không phụ thuộc JUnit, Maven hoặc thư viện bên ngoài; đây là một test harness tối giản để học cách thiết kế bảng ca kiểm thử.

## 8. Cách chuyển sang JUnit và báo cáo coverage

Trong dự án thực tế, nên đặt các ca thành unit test có tên rõ ràng. Với **JUnit Jupiter (JUnit 5)**, có thể chuyển bộ test `Score` thành phương thức parameterized test:

```java
// Đoạn minh họa dành cho lớp test có JUnit Jupiter trên classpath.
// Cần đặt vào test class, thêm imports của JUnit và class chứa Score/classify.
@org.junit.jupiter.params.ParameterizedTest
@org.junit.jupiter.params.provider.CsvSource({
    "-1,NEGATIVE",
    "0,ZERO",
    "1,IN_RANGE",
    "99,IN_RANGE",
    "100,MAX",
    "101,OVER_LIMIT"
})
void scoreBoundaryCases(int points, String expected) {
    org.junit.jupiter.api.Assertions.assertEquals(
        expected,
        FlowBranchBoundaryDemo.classify(
            new FlowBranchBoundaryDemo.Score(points)));
}
```

Đoạn này **không phải tệp Java độc lập** và chỉ dùng được khi test code được đặt trong cùng package phù hợp với lớp `FlowBranchBoundaryDemo`, đã cấu hình JUnit Jupiter `api` và `params`. Không đưa đoạn JUnit trên vào cùng tệp chạy ở mục 7 nếu chưa có dependency. Giá trị cốt lõi ở đây là cách đặt **expected outcome độc lập** và tái sử dụng một hàm test cho nhiều điểm biên.

Nếu dùng JaCoCo, hãy xem tỷ lệ branch coverage như **chỉ báo phụ**. Ưu tiên đọc vùng chưa được thực thi, thêm ca cho guard sai/đúng và kiểu/null chưa có; đồng thời giữ nguyên các assert để bảo đảm test thật sự phát hiện lỗi. Với switch pattern matching, bytecode compiler tạo ra có thể có các nhánh kỹ thuật ngoài những nhánh nghiệp vụ trong source.

### Dùng mutation testing để kiểm tra test có “sức bắt lỗi”

Ví dụ, nếu một thay đổi vô tình biến `n < 0` thành `n <= 0`, test `score-zero` sẽ mong `ZERO` nhưng nhận `NEGATIVE`. Nếu đổi `n > 100` thành `n > 101`, test `score-101` sẽ mong `OVER_LIMIT` nhưng có thể rơi vào `IN_RANGE`.

Những ca biên `0` và `101` có khả năng phát hiện hai thay đổi đó. Đây là ví dụ về việc test hữu ích hơn chỉ “chạy qua” đoạn mã.

Một mutation khác là thay đổi **thứ tự guard** hoặc bỏ `case Message(var text) when text == null`. Khi đó `Message(null)` có thể gây `NullPointerException` tại `text.isBlank()` hoặc cho kết quả không đúng; test `text-null` sẽ phát hiện.

## 9. Cần kiểm tra thêm điều gì khi domain tiến hóa?

- **Thêm subtype vào `sealed interface`:** nếu thêm `record Flag(boolean enabled) implements Input`, compiler có thể yêu cầu thêm case để `switch expression` tiếp tục exhaustive. Khi bổ sung case, phải thêm dữ liệu test cho cả hai giá trị `true/false` nếu có logic phân nhánh.
- **Thay quy tắc ranh giới:** nếu mức tối đa đổi từ `100` sang `120`, cập nhật **oracle nghiệp vụ trước**, rồi cập nhật bộ ba `119/120/121` và mã thực hiện. Tránh sửa test để chỉ bắt chước lỗi trong implementation.
- **Đặt bất biến trong constructor:** nếu `Batch` về sau cấm thành phần `null`, các test `batch-left-null`, `batch-right-null`, `batch-both-null` phải kiểm tra lỗi constructor hoặc dùng input mà domain hợp lệ.
- **Thay kiểu từ `int` sang `long`:** xem lại giá trị cực trị và rủi ro tràn số. `Integer.MIN_VALUE` không còn là cực tiểu của `long`.
- **Đếm độ dài văn bản theo mục đích UI:** `String.length()` đếm UTF-16 code units; nếu yêu cầu khác, cập nhật thuật toán và các ca Unicode tương ứng.
- **Khi xử lý exception:** một test mong đợi exception cần assert **đúng loại lỗi và chính sách liên quan**, không chỉ xác nhận rằng “có lỗi”. JUnit có `assertThrows` cho trường hợp này.
- **Thay thứ tự case:** compiler thường chặn case bị dominated, nhưng không chặn mọi sai sót logic trong các guard khác nhau. Duy trì test sát ranh giới và từng đường đi.

## 10. Những lỗi thường gặp khi kiểm thử flow branch

1. **Chỉ dùng happy path.** Một input `Score(50)` không thử được các nhánh âm, 0, cực đại, vượt mức.
2. **Không thử giá trị sát biên.** Có ca `Score(200)` nhưng thiếu `99/100/101` rất dễ bỏ lọt sai dấu so sánh.
3. **Gộp mọi trường hợp null.** `classify(null)` và `classify(new Message(null))` đi hai nhánh hoàn toàn khác; `Batch(null, new Score(1))` là tình huống thứ ba.
4. **Cho rằng record pattern luôn loại mọi null.** Record ngoài `Batch` phải khác null để khớp, nhưng `var first` có thể nhận thành phần null; nested record pattern `Score(...)` thì không khớp record con null.
5. **Cho rằng biến pattern luôn khác null ở mọi cấp.** Sau `Message(var text)`, `text` vẫn có thể bằng null; phải bảo vệ việc gọi `text.isBlank()` hoặc tạo invariant ở constructor.
6. **Kiểm thử nhánh có guard mà không thử guard false.** `a == b` cần cặp bằng nhau và cặp khác nhau, không chỉ một cặp bằng nhau.
7. **Nhầm kết quả mong đợi với kết quả thực thi.** Viết `assertEquals(actual, actual)` hoặc tự sinh `expected` bằng chính hàm đang kiểm thử sẽ làm test vô giá trị.
8. **In log thay vì assert.** Một dòng `System.out.println(classify(input))` chỉ hiển thị kết quả, không làm test thất bại nếu sai.
9. **Đếm nhãn rồi kết luận đủ branch coverage.** Nhãn là kết quả nghiệp vụ; dùng coverage tool để đánh giá các nhánh thực tế và kết hợp với oracle.
10. **Không kiểm thử type pattern phủ định và early return.** Mẫu `if (!(value instanceof Score score)) return ...` cần thử cả `null`, sai kiểu và đúng kiểu.
11. **Dùng cùng một tập ca chỉ chứa dữ liệu hợp lệ.** Nếu ứng dụng cho phép nullable components, hãy thử thiếu bên trái, thiếu bên phải và thiếu cả hai.
12. **Tắt kiểm tra exhaustiveness bằng `default` rộng vô điều kiện.** Với `sealed`, thường nên để compiler phát hiện subtype mới chưa có case và thêm test tương ứng.
13. **Tạo case sai thứ tự rồi kỳ vọng unit test phát hiện runtime.** Java có thể từ chối ngay lúc biên dịch vì dominance; trước tiên phải có source code biên dịch được.
14. **Chạy ví dụ Java 21 dưới cấu hình Java 17.** Record patterns và pattern switch của chương trình này yêu cầu `--release 21` trở lên; không phải ví dụ chạy với `--release 17`.

## 11. Bài tập tự kiểm tra

**Câu 1.** Với nhóm case số hiện tại, nếu đổi `n < 0` thành `n <= 0`, ca nào trong bảng phát hiện lỗi trước tiên? Vì sao?

*Đáp án:* `score-zero`. Đầu vào `0` sẽ đi vào `NEGATIVE` thay vì `ZERO`. Đây là ví dụ lỗi tại biên `0`.

**Câu 2.** Có thể thay `case Message(var text) when text == null` bằng `case null` để xử lý `Message(null)` không?

*Đáp án:* Không. `case null` xử lý giá trị selector `input` bằng null; `Message(null)` vẫn là một đối tượng record khác null. Chỉ một guard hoặc chính sách dữ liệu phù hợp mới xử lý được thành phần `text` null.

**Câu 3.** `new Batch(null, new Score(2))` sẽ đi vào case nào, nếu không có kiểm tra constructor cấm null?

*Đáp án:* Case cuối `Batch(var first, var second)`, trả `INCOMPLETE_BATCH`, vì các case lồng `Batch(Score(...), Score(...))` không khớp khi `first == null`.

**Câu 4.** Vì sao `Score(99)`, `Score(100)`, `Score(101)` có ý nghĩa hơn chỉ `Score(150)`?

*Đáp án:* Chúng nằm ngay trước/tại/sau ranh giới `100`, dễ phát hiện lỗi `>` thành `>=` hoặc điều kiện ranh giới bị bỏ qua; `150` chỉ chứng minh một giá trị rất xa phía trên.

**Câu 5.** Nếu chương trình in `PASS branch-outcomes=13`, ta có thể khẳng định JaCoCo báo branch coverage 100% không?

*Đáp án:* Không. Bài chỉ xác nhận 13 nhãn kết quả nghiệp vụ đã được quan sát. Số branch theo bytecode và các đường đi guard có thể khác, nên phải chạy coverage tool mới biết tỷ lệ đo được.

**Câu 6.** Tại sao cần kiểm tra `scoreWithIf(null)` và `scoreWithIf(new Message("abc"))`, mặc dù `scoreWithIf` đã dùng `!(value instanceof Score score)`?

*Đáp án:* Hai ca xác nhận cùng kết quả `NOT_SCORE` từ hai nguyên nhân khác nhau: selector `null` và đối tượng sai kiểu. Chúng giúp phát hiện nếu khi refactor ta vô tình truy cập đối tượng trước khi kiểm tra kiểu hoặc xử lý null không đúng.

**Tham khảo chính thức:** [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [JLS Java 21 `14.11 – switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11), [JLS Java 21 `14.30 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
