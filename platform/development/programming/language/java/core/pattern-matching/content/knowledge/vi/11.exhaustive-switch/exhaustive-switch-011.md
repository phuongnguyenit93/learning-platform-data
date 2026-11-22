# Kiểm thử đầy đủ các pattern `case` trong Java

## 1. Mục tiêu: “exhaustive” không có nghĩa đã kiểm thử đủ

Từ **Java 21**, pattern matching cho `switch` (JEP 441) là tính năng chính thức. Một `switch` có thể dùng type pattern (`case String s`), record pattern (`case Point(int x, int y)`), guard (`when ...`), nhãn `null`, nhãn hằng số và `default`.

**Exhaustiveness (tính bao phủ của `switch`)** và **test coverage (độ bao phủ của kiểm thử)** là hai khái niệm khác nhau:

- **Compile-time exhaustiveness:** trình biên dịch xác định switch đã có đủ nhãn để xử lý các giá trị không `null` có thể xuất hiện theo kiểu tĩnh của selector hay chưa. `switch expression` và **enhanced switch statement** phải exhaustive.
- **Runtime test coverage:** bộ kiểm thử chủ động chạy những đầu vào đại diện để kiểm tra **nhánh thực sự được chọn**, điều kiện guard, thứ tự nhãn, các ranh giới và đầu ra/ngoại lệ.
- **Business correctness:** dù một switch hợp lệ và có các test đi qua từng case, logic trong guard hoặc thứ tự giữa các case vẫn có thể sai yêu cầu nghiệp vụ.

Ví dụ, compiler có thể chấp nhận:

```java
return switch (value) {
    case String s when s.length() < 5 -> "short";
    case String s when s.isBlank() -> "blank";
    case String s -> "text";
    case null -> "null";
    default -> "other";
};
```

Nhưng với `" "`, cả hai guard đầu có thể đúng và Java chọn **case đầu tiên**. Nếu nghiệp vụ yêu cầu `" "` là chuỗi trắng, test phải phát hiện rằng thứ tự cần đổi. Compiler không giải toàn bộ quan hệ logic giữa các biểu thức `when`.

**Mục tiêu của bài:** xây dựng ma trận kiểm thử bao phủ từng pattern, từng tập giá trị của guard, ranh giới, giá trị `null`, các kiểu không khớp và các tình huống lỗi biên dịch; hiểu giới hạn của việc tuyên bố “test đầy đủ” khi miền đầu vào có thể vô hạn.

## 2. Java kiểm tra exhaustiveness bằng cách nào?

### 2.1. Switch expression và enhanced switch statement

Theo **Java Language Specification (JLS) 21, §14.11**, một **switch expression** phải exhaustive. Một **enhanced switch statement** (ví dụ có nhãn pattern hoặc `case null`, hay selector dùng kiểu không thuộc các kiểu switch truyền thống) cũng phải exhaustive.

Ví dụ **không biên dịch** (đoạn phương thức minh họa cần đặt trong lớp):

```java
static String incomplete(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer n -> "integer";
        // LỖI: thiếu các kiểu Object còn lại.
    };
}
```

Sửa bằng một nhánh còn thiếu:

```java
static String complete(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "string";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

Ở đây `default` bao phủ các giá trị không `null` không khớp `String` hoặc `Integer`. `case null` là chính sách xử lý `null` **riêng**: trong Java 21, nếu không có nhãn xử lý `null` thì selector `null` thông thường gây `NullPointerException`, kể cả khi có `default`.

**Cần lưu ý:** một switch statement kiểu cũ, chỉ có hằng số và không thuộc diện enhanced, có thể không bắt buộc exhaustive vì lý do tương thích ngược. Không nên khái quát “mọi switch statement đều phải có `default`”.

### 2.2. Exhaustive qua sealed hierarchy

Một kiểu `sealed` giới hạn tập lớp/kiểu con trực tiếp được phép triển khai. Nếu switch có case bao phủ mọi subtype được phép, compiler có thể coi switch là exhaustive **không cần `default`**.

Ví dụ:

```java
sealed interface Event permits Started, Finished {}

record Started(String id) implements Event {}
record Finished(String id) implements Event {}

static String eventKind(Event event) {
    return switch (event) {
        case Started s -> "started";
        case Finished f -> "finished";
    };
}
```

Đây là **mảnh mã minh họa**: đặt các khai báo ở phạm vi hợp lệ trong một tệp Java 21. Nó bao phủ mọi đối tượng `Event` khác `null` trong tập subtype đã khai báo. Muốn có phản hồi cụ thể cho `null`, bổ sung `case null`.

Nếu bổ sung subtype mới, ví dụ `record Cancelled(...) implements Event`, rồi biên dịch lại mã nguồn switch hiện tại, compiler có thể yêu cầu một case mới. Nhưng trong hệ thống có **biên dịch/phân phối riêng các thành phần**, một switch đã được biên dịch trước đó có thể gặp subtype mới ở runtime và ném **`MatchException`**. Vì vậy kiểm thử và quy trình build cần xem xét cả sự thay đổi của sealed hierarchy, không chỉ tập test hiện hành.

### 2.3. Guard không tự chứng minh bao phủ toàn miền

Ví dụ **không exhaustive** nếu selector là `Integer` và chỉ có các guard tùy ý:

```java
static String sign(Integer value) {
    return switch (value) {
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n when n > 0 -> "positive";
        // LỖI: compiler không chứng minh các guard tùy ý bao phủ mọi Integer.
    };
}
```

Về toán học, ba miền `< 0`, `== 0`, `> 0` bao phủ mọi số nguyên. Nhưng kiểm tra exhaustiveness của Java không phải bộ giải logic tổng quát cho các biểu thức guard.

Cách viết rõ ràng hơn:

```java
static String sign(Integer value) {
    return switch (value) {
        case null -> "null";
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n -> "positive";
    };
}
```

Rule `case Integer n` **không guard** bao phủ các giá trị `Integer` còn lại, nên switch exhaustive với selector kiểu `Integer` (đồng thời xử lý `null` rõ ràng).

## 3. “Kiểm thử đầy đủ” cần những lớp kiểm tra nào?

Có thể chia thành bốn nhóm:

| Nhóm | Cần xác minh | Dấu hiệu lỗi |
| --- | --- | --- |
| **Compile-time** | Switch expression/enhanced statement exhaustive; không có case bị dominated; cú pháp hợp lệ | `javac` báo lỗi |
| **Type partition** | Mọi subtype của sealed hierarchy, mỗi type pattern, kiểu lạ vào `default` | Một lớp không tới case mong đợi |
| **Guard partition** | Mỗi nhánh `when` đúng/sai, trường hợp chồng lấn, ranh giới số/chuỗi | Hai guard cùng đúng nhưng case ưu tiên sai |
| **Exceptional/null** | `null`, guard ném ngoại lệ, `MatchException` do binary evolution, dữ liệu bất thường | Null đi vào NPE ngoài ý muốn; lỗi lọt qua không được dự kiến |

**Không thể tự suy rằng một bộ test đã kiểm hết vô hạn giá trị `String`, `int` hay mọi dữ liệu bên ngoài.** “Đầy đủ” trong thực hành thường nghĩa là bộ test đã phủ được **các nhánh cú pháp, các lớp tương đương, ranh giới và bất biến nghiệp vụ được xác định rõ**, cùng với kiểm tra build bắt lỗi thiếu case.

### 3.1. Ma trận type patterns

Với `Object` có thể chứa nhiều kiểu runtime, tối thiểu nên có một đầu vào cho mỗi type pattern và một đầu vào không khớp bất cứ type pattern chuyên biệt nào.

Ví dụ:

```java
return switch (value) {
    case null -> "NULL";
    case String s -> "TEXT";
    case Integer n -> "INT";
    case Number n -> "OTHER_NUMBER";
    default -> "OTHER";
};
```

Ma trận mẫu:

| Giá trị | Runtime type | Nhãn mong đợi |
| --- | --- | --- |
| `null` | không có đối tượng | `case null` |
| `"Hi"` | `String` | `case String s` |
| `Integer.valueOf(7)` | `Integer` | `case Integer n` |
| `Double.valueOf(2.5)` | `Double` (là `Number`) | `case Number n` |
| `Boolean.TRUE` | `Boolean` | `default` |

**Thứ tự case quan trọng:** `Integer` phải đứng trước `Number` để không bị case lớp cha che. Nếu đổi `case Number n` lên đầu, `case Integer n` đứng sau có thể gây lỗi **dominance** khi biên dịch.

### 3.2. Ma trận guard theo điểm biên

Với tiến độ phần trăm `int percent`, giả sử:

1. Nếu `percent < 0 || percent > 100` → `INVALID`.
2. Nếu `percent == 100` → `DONE`.
3. Nếu `percent >= 80` → `HIGH`.
4. Còn lại → `NORMAL`.

Chọn các giá trị quanh điểm chuyển:

| Input `percent` | Expected | Lý do |
| ---: | --- | --- |
| `-1` | `INVALID` | Ngay dưới cận dưới |
| `0` | `NORMAL` | Tại cận dưới |
| `79` | `NORMAL` | Ngay trước ngưỡng cao |
| `80` | `HIGH` | Tại ngưỡng cao |
| `99` | `HIGH` | Ngay trước hoàn tất |
| `100` | `DONE` | Tại điểm đặc biệt cần ưu tiên hơn `>= 80` |
| `101` | `INVALID` | Ngay trên cận trên |

Đặc biệt, `100` **đồng thời thỏa** `percent == 100` và `percent >= 80`; guard `== 100` phải đứng **trước** guard `>= 80` nếu muốn nhãn `DONE`. Một test chỉ dùng `80` sẽ **không phát hiện lỗi ưu tiên tại 100**.

### 3.3. Negative tests ở mức biên dịch

Ngoài kiểm thử runtime, hãy cố tình viết những mẫu lỗi trong **file thử riêng** và xác nhận `javac` từ chối chúng:

- Thiếu case cho một subtype trong sealed hierarchy;
- Chỉ có guarded patterns mà không có case tổng quát chứng minh được exhaustiveness;
- Pattern lớp cha không guard đứng trước pattern lớp con (dominance);
- Nhãn trùng hằng số;
- Truy cập pattern variable ở ngoài phạm vi nhánh chứa khai báo.

Một file được **kỳ vọng biên dịch thất bại** không nên trộn vào chương trình demo chính, bởi như vậy chương trình test bình thường cũng không chạy được. Khi tự động hóa, chỉ kiểm tra exit code khác 0 và chẩn đoán phù hợp, không giả định chính xác văn bản lỗi giữa các bản `javac`.

## 4. Chương trình Java 21+ có assertion và bao phủ từng pattern case

Ví dụ sau dùng **hai switch**:

1. `classifyEvent(Event)` là switch expression trên **sealed hierarchy**, bao phủ mọi subtype qua pattern; không có `default`.
2. `classifyAny(Object)` kiểm tra `null`, `String`, `Integer`, `Event`, **record patterns** và `default`; có guard trống/độ dài, số âm và điểm nằm trên đường chéo.

Hàm `check` tự ném `AssertionError` khi kết quả không như mong đợi: việc chương trình in `PASS` vì thế có giá trị hơn ví dụ chỉ in kết quả mà không đối chiếu.

### 4.1. Mã nguồn hoàn chỉnh

Lưu file **`ExhaustiveCaseTestDemo.java`**:

```java
public class ExhaustiveCaseTestDemo {
    sealed interface Event permits Started, Progress, Completed, Failed {}

    record Started(String id) implements Event {}
    record Progress(int percent) implements Event {}
    record Completed(String result) implements Event {}
    record Failed(String reason) implements Event {}
    record Point(int x, int y) {}

    static String classifyEvent(Event event) {
        return switch (event) {
            case null -> "EVENT_NULL";
            case Started started -> "STARTED:" + started.id();

            case Progress p when p.percent() < 0 || p.percent() > 100 ->
                    "INVALID_PROGRESS:" + p.percent();
            case Progress p when p.percent() == 100 ->
                    "PROGRESS_DONE";
            case Progress p when p.percent() >= 80 ->
                    "HIGH_PROGRESS:" + p.percent();
            case Progress p -> "PROGRESS:" + p.percent();

            case Completed c -> "COMPLETED:" + c.result();
            case Failed f -> "FAILED:" + f.reason();
        };
    }

    static String classifyAny(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG_TEXT:" + s;
            case String s -> "SHORT_TEXT:" + s;

            case Integer n when n < 0 -> "NEGATIVE:" + n;
            case Integer n -> "INTEGER:" + n;

            case Event e -> "EVENT/" + classifyEvent(e);

            case Point(int x, int y) when x == y -> "DIAGONAL:" + x;
            case Point(int x, int y) -> "POINT:" + x + "," + y;

            default -> "OTHER";
        };
    }

    static int passed = 0;

    static void check(String testName, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError(testName + ": expected [" + expected
                    + "] but got [" + actual + "]");
        }
        passed++;
        System.out.println("PASS " + testName + " -> " + actual);
    }

    public static void main(String[] args) {
        check("event-null", classifyEvent(null), "EVENT_NULL");
        check("started", classifyEvent(new Started("A")), "STARTED:A");

        check("progress-under", classifyEvent(new Progress(-1)),
                "INVALID_PROGRESS:-1");
        check("progress-zero", classifyEvent(new Progress(0)), "PROGRESS:0");
        check("progress-79", classifyEvent(new Progress(79)), "PROGRESS:79");
        check("progress-80", classifyEvent(new Progress(80)), "HIGH_PROGRESS:80");
        check("progress-99", classifyEvent(new Progress(99)), "HIGH_PROGRESS:99");
        check("progress-100", classifyEvent(new Progress(100)), "PROGRESS_DONE");
        check("progress-over", classifyEvent(new Progress(101)),
                "INVALID_PROGRESS:101");

        check("completed", classifyEvent(new Completed("ok")), "COMPLETED:ok");
        check("failed", classifyEvent(new Failed("timeout")), "FAILED:timeout");

        check("any-null", classifyAny(null), "NULL");
        check("any-blank", classifyAny("  "), "BLANK");
        check("any-short", classifyAny("Hi"), "SHORT_TEXT:Hi");
        check("any-long", classifyAny("Java21"), "LONG_TEXT:Java21");
        check("any-negative", classifyAny(-3), "NEGATIVE:-3");
        check("any-zero", classifyAny(0), "INTEGER:0");
        check("any-event", classifyAny(new Progress(100)),
                "EVENT/PROGRESS_DONE");
        check("any-diagonal", classifyAny(new Point(2, 2)), "DIAGONAL:2");
        check("any-point", classifyAny(new Point(2, 3)), "POINT:2,3");
        check("any-other", classifyAny(2.5), "OTHER");

        System.out.println("ALL PASSED: " + passed);
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**:

```bash
javac ExhaustiveCaseTestDemo.java
java ExhaustiveCaseTestDemo
```

**Standard output mong đợi (khi 21 assertion đều thành công):**

```text
PASS event-null -> EVENT_NULL
PASS started -> STARTED:A
PASS progress-under -> INVALID_PROGRESS:-1
PASS progress-zero -> PROGRESS:0
PASS progress-79 -> PROGRESS:79
PASS progress-80 -> HIGH_PROGRESS:80
PASS progress-99 -> HIGH_PROGRESS:99
PASS progress-100 -> PROGRESS_DONE
PASS progress-over -> INVALID_PROGRESS:101
PASS completed -> COMPLETED:ok
PASS failed -> FAILED:timeout
PASS any-null -> NULL
PASS any-blank -> BLANK
PASS any-short -> SHORT_TEXT:Hi
PASS any-long -> LONG_TEXT:Java21
PASS any-negative -> NEGATIVE:-3
PASS any-zero -> INTEGER:0
PASS any-event -> EVENT/PROGRESS_DONE
PASS any-diagonal -> DIAGONAL:2
PASS any-point -> POINT:2,3
PASS any-other -> OTHER
ALL PASSED: 21
```

### 4.2. Vì sao đây là kiểm thử có ý nghĩa?

- **Sealed type:** có test cho tất cả bốn subtype `Started`, `Progress`, `Completed`, `Failed`. Riêng `Progress` được chia thành các guard và một pattern không guard.
- **Guard boundary:** `-1`, `0`, `79`, `80`, `99`, `100`, `101` kiểm thử những ranh giới làm nhánh chuyển từ bình thường sang ưu tiên và ngoại lệ. Nếu đặt `>=80` lên trước `==100`, test tại `100` thất bại.
- **Null:** hai phương thức đều có `case null` riêng, do đó test xác minh chính sách null thay vì dựa vào `default`.
- **Object pattern:** chuỗi trắng, chuỗi ngắn, chuỗi dài, số âm, số không âm, subtype `Event`, `Point` và kiểu lạ `Double` đi vào các rule khác nhau.
- **Record pattern:** `Point(2,2)` thử guard `x == y`, còn `Point(2,3)` thử nhánh record không guard. Vì thành phần là `int`, không có vấn đề khớp pattern thành phần tham chiếu `null` tại đây.
- **Assertion:** chương trình dừng với lỗi ngay khi kết quả sai. Các dòng `PASS` và tổng số bài kiểm tra chỉ in khi từng check đã nhận đúng kết quả.

### 4.3. Giới hạn của demo này

Tuy có 21 assertion, demo không tự chứng minh mọi giá trị `int` hay mọi chuỗi trong thế giới thực đều xử lý đúng. Ví dụ, một guard nhầm `>= 80` thành `> 80` có thể được phát hiện bởi test tại 80, nhưng một lỗi chỉ xảy ra với `Integer.MIN_VALUE` vẫn cần test bổ sung nếu có quy tắc nghiệp vụ liên quan.

Khi miền đầu vào lớn, bổ sung **property-based testing**, fuzzing có kiểm soát hoặc kiểm thử sinh dữ liệu quanh các biên. Điều quan trọng là phải xác định *oracle* (kết quả đúng kỳ vọng) độc lập với mã `switch`: nếu viết test bằng cách sao chép nguyên logic production, cả hai có thể cùng chứa một sai lầm.

## 5. Tự kiểm thử những switch không exhaustive

### 5.1. Thiếu một subtype của `sealed`

Đoạn phương thức sau dùng các kiểu lồng trong `ExhaustiveCaseTestDemo` ở trên. Nó được dùng để **thử lỗi biên dịch**, không được thêm vào chương trình chạy chính nếu đang muốn chạy các test thành công.

```java
static String missingSubtype(Event event) {
    return switch (event) {
        case Started s -> "started";
        case Progress p -> "progress";
        case Completed c -> "completed";
        // Thiếu Failed: lỗi non-exhaustive switch.
    };
}
```

**Kỳ vọng:** `javac` trả exit code khác 0 vì tập nhãn không bao phủ subtype `Failed`. Thêm `case Failed f -> "failed";` để sửa. Nếu có `default`, switch có thể biên dịch dù đã quên `Failed`, nhưng bạn sẽ **mất khả năng nhờ compiler nhắc cập nhật** khi sealed hierarchy phát triển.

### 5.2. Guard không đủ để chứng minh bao phủ

```java
static String incompleteProgress(Event event) {
    return switch (event) {
        case Started s -> "started";
        case Progress p when p.percent() < 0 -> "invalid";
        case Completed c -> "completed";
        case Failed f -> "failed";
        // Không có case Progress không guard.
    };
}
```

**Kỳ vọng:** lỗi non-exhaustive. Một `Progress` với giá trị 50 không thỏa guard duy nhất. Để sửa, thêm `case Progress p -> "progress";` **sau** nhánh có guard.

### 5.3. Dominated pattern và thứ tự nhánh

```java
static String invalidOrder(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer n -> "integer"; // LỖI: bị case Number che.
        default -> "other";
    };
}
```

**Kỳ vọng:** lỗi dominated case label. Java phát hiện vì mọi `Integer` đều là `Number`. Sửa bằng cách đưa `Integer` lên trước `Number`.

**Khác với lỗi dominance:** hai guard tùy ý như `p.percent() == 100` và `p.percent() >= 80` có thể **cùng đúng**, nhưng compiler không giải toàn bộ quan hệ toán học giữa chúng. Đổi thứ tự thường vẫn biên dịch; test tại 100 mới phát hiện trường hợp ưu tiên sai.

### 5.4. Kiểm thử compile-negative một cách an toàn

Có thể lưu từng biến thể lỗi vào **file Java riêng** khi tự học và chạy:

```bash
javac MissingSubtype.java
```

Kỳ vọng compile fail. Với tự động hóa CI, tổ chức **negative compilation tests** riêng với source set chính, để file cố tình sai không làm hỏng build sản phẩm. Tùy compiler và phiên bản JDK, thông báo chữ có thể khác; tiêu chí chung là lệnh biên dịch thất bại vì lý do dự kiến.

## 6. `null`, `default`, `MatchException` và các trường hợp ngoại lệ

### 6.1. Không đánh đồng `default` với `case null`

Với selector tham chiếu:

```java
static String label(Object value) {
    return switch (value) {
        case String s -> "string";
        default -> "other";
    };
}
```

Chương trình xử lý các đối tượng không `null`; nhưng gọi `label(null)` gây **`NullPointerException`** vì `default` không tự khớp `null`. Nếu muốn kiểm thử chính sách null có giá trị trả về, thêm `case null -> "null"` hoặc dùng nhãn đặc biệt `case null, default -> ...` khi thật sự muốn chung xử lý.

Cách viết kiểm thử ngoại lệ dùng Java thuần:

```java
boolean thrown = false;
try {
    label(null);
} catch (NullPointerException expected) {
    thrown = true;
}
if (!thrown) {
    throw new AssertionError("Expected NullPointerException");
}
```

Đây là **mảnh mã đặt trong phương thức phù hợp**; nó xác nhận chính sách “không hỗ trợ null” một cách tường minh. Đừng dùng dạng test này nếu API mong muốn **xử lý `null` bình thường**: khi đó nên viết `case null` và assert kết quả như chương trình hoàn chỉnh ở mục 4.

### 6.2. Vì sao một switch exhaustive vẫn có thể gặp `MatchException`?

Oracle Java 21 nêu trường hợp **binary evolution**: một switch đã được biên dịch để bao phủ mọi nhánh trong một sealed hierarchy, nhưng thư viện khai báo hierarchy được sửa, biên dịch lại và có thêm subtype, trong khi mã switch cũ không được biên dịch lại.

Khi đó switch có thể gặp một đối tượng không còn phù hợp với các case mà bản nhị phân của switch cũ đã biết, và **`java.lang.MatchException`** có thể xuất hiện tại runtime.

Điều này **không** có nghĩa rằng mọi switch exhaustive đều cần một `default`. Với sealed hierarchy, không có `default` thường hữu ích vì compiler buộc người viết xử lý subtype mới khi build lại toàn bộ mã. Cần:

- Biên dịch lại các module phụ thuộc khi thay đổi sealed hierarchy;
- Có integration tests chạy với đúng tập artifact được phân phối;
- Không để các thành phần runtime thuộc phiên bản không tương thích nhau;
- Theo dõi `MatchException` như tín hiệu lỗi tương thích/phủ nhánh, không coi là một trường hợp nghiệp vụ thông thường.

### 6.3. Guard có thể ném ngoại lệ

Nếu guard gọi một phương thức ném ngoại lệ, switch không đơn giản chuyển sang case tiếp theo như lúc guard trả `false`. Ví dụ, guard trên dữ liệu chứa giá trị có thể `null` cần kiểm tra an toàn trước:

```java
case String s when s.length() > 3 -> ...
```

Type pattern `String s` đã chứng minh `s` không null, nên `s.length()` an toàn về mặt null. Nhưng các thành phần record kiểu tham chiếu hoặc phương thức nghiệp vụ khác có thể vẫn là `null`/ném ngoại lệ. Kiểm thử cả đường thất bại phù hợp với hợp đồng API.

## 7. Kiểm thử `switch statement` và `switch expression`

### Switch expression

- **Luôn phải exhaustive** về mặt kiểu/cấu trúc theo JLS.
- Mỗi nhánh bình thường cho ra một giá trị; trong RHS dạng block, dùng `yield` để tạo giá trị.
- Test nên assert **giá trị trả về** của từng nhánh hoặc loại ngoại lệ.

### Enhanced switch statement

- Khi có pattern hoặc `case null`, thường thuộc nhóm **enhanced** và cũng phải exhaustive.
- Thực thi lệnh, không tự tạo giá trị của biểu thức `switch`.
- Test nên kiểm tra **tác dụng quan sát được**: gọi callback, ghi một đối tượng vào danh sách, thay đổi trạng thái, hoặc gọi phương thức được giả lập. Nếu chỉ in `System.out`, có thể kiểm tra output bằng cách bắt luồng in, nhưng mã sản xuất thường dễ test hơn khi trả về giá trị/đưa hành động vào dependency.

Ví dụ minh họa `switch statement` với type pattern:

```java
static void printEvent(Event event) {
    switch (event) {
        case Started s -> System.out.println("started " + s.id());
        case Progress p -> System.out.println("progress " + p.percent());
        case Completed c -> System.out.println("completed " + c.result());
        case Failed f -> System.out.println("failed " + f.reason());
    }
}
```

Phương thức minh họa thuộc cùng lớp định nghĩa `Event`; nó bao phủ toàn bộ subtype **không `null`** của sealed hierarchy. Gọi với `null` sẽ ném NPE; thêm `case null` nếu cần xử lý. Khi dùng **arrow rules `->`**, không có fall-through; nếu dùng các nhóm lệnh `case ...:`, phải kiểm soát `break` và các quy tắc không được fall through vào pattern variable chưa được khởi tạo.

## 8. Test strategy nâng cao cho dự án thực tế

### 8.1. Lập ma trận coverage trước khi viết code

Với mỗi nhãn `case`, ghi rõ:

| Cột cần có | Nội dung mẫu |
| --- | --- |
| Nhãn | `case Progress p when p.percent() >= 80` |
| Kiểu đầu vào | `Progress` |
| Điều kiện để chọn | `80 <= percent < 100`, sau nhánh kiểm tra 100 |
| Một giá trị dương tính | `Progress(80)` |
| Một giá trị âm tính gần biên | `Progress(79)` |
| Giá trị gây chồng lấn | `Progress(100)` |
| Kỳ vọng | `"HIGH_PROGRESS:80"`, hoặc nhánh hoàn tất nếu 100 |
| Kết quả thực tế | So sánh qua assertion |

Mỗi test nên chứng minh điều gì đó **phân biệt được** giữa các nhánh. Chỉ viết một test bất kỳ cho mỗi type là chưa đủ nếu cùng type có nhiều guard.

### 8.2. Tập kiểm thử tối thiểu có cấu trúc

Một bộ kiểm thử tốt thường gồm:

1. **Mỗi subtype** được phép của sealed hierarchy (mỗi subtype một test dương tính).
2. **Mỗi guard** có ít nhất một test đúng và một test sai.
3. **Mỗi ranh giới**: ngay trước, đúng tại, ngay sau ngưỡng (`79`, `80`, `81` nếu ngưỡng 80).
4. **Mỗi xung đột ưu tiên**: giá trị thỏa nhiều guard, ví dụ `100` thỏa `==100` và `>=80`.
5. **`null`**: trả kết quả hoặc ném NPE theo hợp đồng.
6. **Nhánh cuối** không guard cùng kiểu, và `default` nếu có.
7. **Mẫu lồng nhau**: record pattern khớp/không khớp thành phần và guard.
8. **Compile-negative**: thiếu subtype, guard-only, nhãn bị dominated.
9. **Thay đổi API**: thêm enum constant hoặc permitted subtype để kiểm tra build/test phát hiện.
10. **Đầu vào bất thường**: giá trị cực tiểu/cực đại, chuỗi rỗng, chuỗi trắng, các trạng thái sai nhưng vẫn có thể tạo được.

Không cần mỗi bài toán đều có tất cả mười nhóm, nhưng **không bỏ một nhóm ảnh hưởng trực tiếp đến yêu cầu nghiệp vụ**.

### 8.3. Mutation test: tự làm mã sai có chủ đích

Một cách kiểm nghiệm chất lượng test là thử một thay đổi nhỏ khiến hành vi sai:

- Đổi `p.percent() == 100` thành `>= 100`;
- Đổi `p.percent() >= 80` thành `> 80`;
- Đảo thứ tự guard `== 100` và `>= 80`;
- Đổi `s.isBlank()` thành `s.isEmpty()` (chuỗi toàn dấu cách khác chuỗi rỗng);
- Bỏ nhánh xử lý một subtype.

Nếu test suite vẫn qua dù logic đã sai, cần bổ sung test phân biệt. Ví dụ đổi `>= 80` sang `> 80` cần bị test ở `Progress(80)` phát hiện. Đảo guard `==100` và `>=80` cần bị `Progress(100)` phát hiện.

### 8.4. Không dùng “đã có default” thay cho kiểm thử đầy đủ

Một `default` cho `Object` có ích để nhận những kiểu ngoài dự kiến, nhưng đôi khi che mất việc một subtype nghiệp vụ mới không có nhánh riêng. Với sealed hierarchy do chính dự án kiểm soát, cân nhắc **không dùng `default`** khi compiler có thể xác nhận đủ subtype: mỗi lần thêm subtype mới sẽ buộc xem lại nhánh xử lý lúc build.

Ngược lại, với đầu vào mở kiểu `Object` có thể là bất kỳ kiểu tham chiếu nào, `default` thường là giải pháp thích hợp để bao phủ tập kiểu còn lại; cần test một giá trị thực sự đi vào nhánh đó.

## 9. Lỗi thường gặp khi kiểm thử pattern case

1. **Đánh đồng compiler exhaustiveness với test branch coverage.** Compiler kiểm tra bao phủ kiểu theo quy tắc ngôn ngữ, không bảo đảm logic trong mọi nhánh đúng.
2. **Chỉ chạy test “happy path”.** Với các guard điều kiện, thiếu ranh giới và giá trị âm/trắng/rỗng thường bỏ lọt lỗi.
3. **Không test `null`.** `default` không tự xử lý null, nên cần quyết định rõ trả giá trị hay ném ngoại lệ.
4. **Quên test guard chồng lấn.** Java chọn nhãn phù hợp đầu tiên, không tự ưu tiên nhãn “cụ thể nhất”.
5. **Viết test assertion bằng chính switch production.** Expected value nên được xác định độc lập từ quy tắc nghiệp vụ.
6. **Cho rằng chỉ có guarded patterns là exhaustive.** Guard bất kỳ không chứng minh được mọi giá trị đều khớp; cần pattern không guard hoặc phần bao phủ khác.
7. **Đưa `default` vào mọi sealed switch mà không cân nhắc.** Nó có thể làm mất tín hiệu compile-time khi subtype được thêm.
8. **Không kiểm thử `record` khi có thành phần null hoặc giá trị biên.** Type/record pattern có quy tắc khớp riêng cho thành phần; không nên giả định mọi cấu trúc đều khớp.
9. **Chỉ kiểm tra kết quả in mà không assert.** Chạy được không đồng nghĩa đúng; bài test cần fail khi khác expected.
10. **Không kiểm tra bản phân phối sau thay đổi sealed hierarchy.** Separate compilation có thể dẫn tới `MatchException` dù build cũ từng exhaustive.
11. **Đặt case kiểu cha trước kiểu con.** Đây là dominance có thể bị compiler từ chối; cần test compile-negative hoặc dựa vào build.
12. **Dùng JDK không đúng phiên bản.** Pattern matching cho `switch` là tính năng chính thức từ Java 21; chạy các ví dụ ở đây bằng JDK 21+.

## 10. Bài tập thực hành

1. **Thêm subtype:** thêm `record Cancelled(String reason) implements Event` vào permits list của chương trình ở mục 4. Dự đoán lỗi của switch `classifyEvent`, rồi thêm nhánh `case Cancelled c`; tạo test `"CANCELLED:..."`.
2. **Thử thay đổi thứ tự guard:** đưa `case Progress p when p.percent() >= 80` lên trước `case Progress p when p.percent() == 100`. Chạy lại 21 test và chỉ ra assertion nào fail, tại sao.
3. **Thử thay đổi toán tử:** đổi `>= 80` thành `> 80`; giải thích vì sao test ở 80 phát hiện lỗi.
4. **Thử guard chồng lấn với chuỗi:** đặt `case String s when s.length() <= 4` trước `case String s when s.isBlank()` rồi phân loại `" "`; viết assertion để bắt lỗi ưu tiên.
5. **Null policy:** bỏ `case null` trong `classifyAny`, gọi với `null` và viết test kỳ vọng `NullPointerException` thay cho `NULL`.
6. **Type partitions:** bổ sung `case Number n` trong `classifyAny` **sau** các case `Integer`; viết test với `Double`, `Long`, `Integer` và phân biệt các đầu ra.
7. **Record pattern:** thêm `Point(0,0)` và `Point(0,1)` vào test; giải thích những nhánh nào phải chạy. Bổ sung guard ưu tiên cho điểm gốc trước guard chéo nếu nghiệp vụ yêu cầu `"ORIGIN"`.
8. **Negative compile:** tạo file thử riêng cố tình bỏ `Failed`, file có pattern `Number` trước `Integer`, file chỉ có guarded patterns; xác nhận từng lỗi thông qua kết quả biên dịch.
9. **Property test:** sinh ngẫu nhiên 1.000 giá trị tiến độ trong khoảng -100 đến 200, so kết quả `classifyEvent(new Progress(p))` với một hàm tham chiếu được viết dựa trên bảng luật; ghi lại seed nếu thất bại.
10. **CI:** đề xuất luồng kiểm tra gồm compilation với JDK21, unit tests, negative compilation tests, kiểm tra thay đổi sealed hierarchy và kiểm thử tích hợp với bộ artifact sẽ triển khai.

**Ghi nhớ:** *Exhaustive switch* là một cam kết về khả năng **bao phủ kiểu** của cấu trúc `switch`; *kiểm thử đầy đủ các pattern case* là công việc xác minh **từng đường đi có ý nghĩa** và **đầu ra mong đợi**. Với Java 21, kết hợp kiểm tra của compiler, ma trận type/guard/boundary/null, assertion thật, các test cố tình thất bại và kiểm thử khi thay đổi hierarchy sẽ tạo ra sự bảo đảm tốt hơn nhiều so với chỉ có `default` hoặc chỉ một test cho mỗi type.

## Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §14.11 — switch Statements (exhaustiveness, dominance, labels)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification 21, §6.3.3 — Pattern variable scope in case labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
