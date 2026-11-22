# Mốc phiên bản của pattern switch trong Java: từ preview đến Java 21 và các mở rộng sau đó

## 1. Kết luận cần nhớ trước tiên

**Pattern matching for `switch` chính thức (*final/permanent*) từ Java 21 — JEP 441.** Tính năng này được giới thiệu dưới dạng **preview** ở Java 17 và trải qua bốn vòng preview trong Java 17, 18, 19, 20 trước khi ổn định.

Mốc chính:

**Java 17 (JEP 406, preview) → Java 18 (JEP 420, second preview) → Java 19 (JEP 427, third preview) → Java 20 (JEP 433, fourth preview) → Java 21 (JEP 441, final).**

Cần phân biệt ba tính năng liên quan nhưng **không phải cùng một mốc**:

1. **Switch expressions** với `case ... ->` và `yield` chính thức từ **Java 14** (JEP 361). Đây **chưa phải** pattern matching for `switch`.
2. **Pattern matching for `instanceof`** chính thức từ **Java 16** (JEP 394). Điều kiện `obj instanceof String s` không đồng nghĩa Java 16 đã có `case String s`.
3. **Record patterns** như `case Point(int x, int y)` chính thức từ **Java 21** (JEP 440), sau các vòng preview ở Java 19–20. Có thể kết hợp record patterns với pattern switch final của Java 21.

**Chọn mốc thực tế:** Nếu một dự án dùng `case String s`, `case Point(int x, int y)`, `when` và `case null` theo cú pháp hiện hành mà **không muốn bật preview**, chọn **Java 21 trở lên** làm source level. Trên JDK 21, biên dịch mã Java 21 ổn định không cần `--enable-preview`.

Nội dung này sử dụng **Java 21 làm chuẩn tương thích chính**. Phần cuối ghi riêng các preview mở rộng primitive patterns trong Java 23–27, cập nhật theo tài liệu Java 27 (tháng 9/2026); chúng **không thay đổi** việc pattern switch trên reference types đã final từ Java 21.

## 2. Timeline chính thức của pattern matching for switch

| Bản Java | JEP | Trạng thái | Điểm quan trọng |
| --- | --- | --- | --- |
| **Java 17** | **406** | Preview lần 1 | Đưa type patterns vào `switch`, hỗ trợ kiểm tra kiểu, pattern variables, null label và guarded patterns. Cú pháp guard ban đầu nằm **bên trong pattern**, dạng `case String s && condition`. |
| **Java 18** | **420** | Preview lần 2 | Điều chỉnh dominance của nhãn hằng/guard/type pattern; cải thiện kiểm tra exhaustiveness, gồm các generic sealed hierarchies. |
| **Java 19** | **427** | Preview lần 3 | Guard chuyển sang **`when`**; điều chỉnh xử lý selector null; tình huống exhaustive lúc compile nhưng không khớp lúc chạy dẫn tới `MatchException`. Có thể kết hợp với **record patterns preview** (JEP 405). |
| **Java 20** | **433** | Preview lần 4 | Đơn giản hóa cú pháp nhãn `case`, làm rõ `MatchException` khi exhaustive enum switch mất nhánh ở runtime và phối hợp với record pattern generic type inference (JEP 432). |
| **Java 21** | **441** | **Final** | Pattern matching for `switch` trở thành tính năng chuẩn; không cần preview flag. Loại bỏ parenthesized patterns, cho phép qualified enum constants trong case constants. Record patterns cũng final (JEP 440). |

**Nguồn:** Oracle Java 21 Language Changes by Release và các JEP tương ứng.

Bảng trên mô tả **mốc tính năng**, không phải đảm bảo một file source preview viết bằng Java 17 có thể biên dịch không sửa trên Java 21. Chính các vòng preview đã thay đổi cú pháp và một số quy tắc. Vì vậy một tài liệu hướng dẫn viết cho Java 17/18 có thể chứa `case String s && ...`, trong khi tài liệu cho Java 21 sử dụng `case String s when ...`.

### 2.1. Java 17 — JEP 406 (Preview)

Java 17 cho phép dùng type patterns trong `switch` ở dạng preview. Ví dụ **minh họa cú pháp của bản preview Java 17**:

```java
// Java 17 preview: không phải cú pháp guard Java 21.
static String oldPreview(Object value) {
    return switch (value) {
        case String s && s.length() > 3 -> "long text";
        case String s -> "text";
        case null -> "null";
        default -> "other";
    };
}
```

Dạng `String s && condition` là **guarded pattern syntax** của preview ban đầu. Không nhầm với biểu thức `instanceof String s && condition` (vốn vẫn hợp lệ trong Java 21). Trong Java 21, guard của nhãn `case` cần viết **`when`**.

Java 17 đồng thời hoàn tất **sealed classes** (JEP 409), tạo nền tảng để compiler phân tích tập subtype trong exhaustive switch. Nhưng sealed classes final **không làm** pattern switch cũng final trong Java 17.

Để sử dụng tính năng preview ở **đúng JDK 17**:

```bash
javac --enable-preview --release 17 PreviewSwitchDemo.java
java --enable-preview PreviewSwitchDemo
```

`PreviewSwitchDemo.java` trong cặp lệnh này là **tên file minh họa** cho một chương trình Java 17 preview hoàn chỉnh do người học tạo. Đoạn `oldPreview` bên trên chỉ là một phương thức, **không phải chương trình độc lập**. Không thực thi cặp lệnh trên một bản JDK mới hơn để cố bật lại preview của JDK 17.

### 2.2. Java 18 — JEP 420 (Second Preview)

Java 18 tiếp tục preview. Mốc đáng chú ý về hành vi compiler:

- Kiểm tra **dominance** của constant labels, guarded patterns và non-guarded type patterns được tinh chỉnh.
- Phân tích **exhaustiveness** của `switch` được mở rộng, nhất là với generic sealed classes và một số tập kiểu phức tạp.
- Không được hiểu “preview lần 2” là Java 18 đã cho phép dùng pattern switch mà không có preview flag.

Khi đánh giá mã legacy viết cho Java 18, cần kiểm tra cả **thứ tự nhãn** và **các trường hợp compiler đánh giá đã bao phủ toàn bộ**. Một đoạn mã có vẻ tương đương về logic có thể gặp chẩn đoán compiler khác giữa các preview.

### 2.3. Java 19 — JEP 427 (Third Preview)

Đây là mốc đặc biệt dễ nhầm:

- Guard trở thành **một phần của case label** với từ khóa **`when`**, thay cho dạng guarded pattern `p && e` trong Java 17/18.
- Quy tắc selector null rõ hơn: nếu selector là `null` và không có nhãn `case null` thích hợp, ném `NullPointerException`, ngay cả khi có type pattern bao phủ kiểu selector.
- Nếu `switch` được coi là exhaustive lúc biên dịch nhưng không tìm được nhãn ở runtime, `MatchException` có thể được ném.
- **Record patterns** xuất hiện dưới dạng preview lần đầu ở Java 19, thông qua **JEP 405**; từ đây có thể dùng nested record patterns trong các ngữ cảnh pattern tương ứng.

Ví dụ **minh họa cú pháp Java 19 preview**:

```java
// Java 19 preview hoặc Java 21 final:
static String lengthClass(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long text";
        case String s -> "text";
        case null -> "null";
        default -> "other";
    };
}
```

Đây là cú pháp `when` phù hợp với Java 21. Tuy nhiên **cú pháp giống nhau chưa bảo đảm mọi quy tắc và phiên bản API preview hoàn toàn giống nhau**. Khi nâng cấp, nên đọc release notes/JEP và chạy lại test.

### 2.4. Java 20 — JEP 433 (Fourth Preview)

Java 20 tiếp tục preview nhưng hướng đến sự hoàn thiện:

- Đơn giản hóa grammar của `switch` case labels.
- Tinh chỉnh ngoại lệ khi một exhaustive enum switch không có nhãn khớp lúc runtime: `MatchException` thay cho `IncompatibleClassChangeError` trong tình huống được JEP nêu.
- **Record patterns second preview** (JEP 432) bổ sung khả năng suy luận type arguments của **generic record patterns**, giúp các mẫu không phải luôn viết tham số generic tường minh.
- Cú pháp và khả năng xuất hiện record patterns trong enhanced `for` của các bản preview có thay đổi; **không áp dụng máy móc code preview Java 20 cho Java 21**.

**Java 20 vẫn chưa là bản final** của pattern switch; với mã dùng tính năng preview trên JDK 20, phải bật preview flag cho compile/run và kiểm thử khi chuyển bản Java.

### 2.5. Java 21 — JEP 441 (Final)

Java 21 chuẩn hóa pattern matching for `switch`:

```java
Object value = "Java";

String label = switch (value) {
    case String text when text.length() > 3 ->
            "long:" + text;
    case String text -> "text:" + text;
    case null -> "null";
    default -> "other";
};
```

Đoạn trên là **mã minh họa nằm trong một method/initializer**, sử dụng cú pháp final Java 21 và trả `long:Java`.

Những điểm chuẩn Java 21 đáng lưu ý:

- Selector có thể là **reference type bất kỳ**, cùng các kiểu nguyên thủy đã hỗ trợ từ trước (`byte`, `short`, `char`, `int`); không suy ra primitive `long`/`double` cũng được phép trong Java 21.
- `when` là cú pháp guard của case label. `when` chỉ chạy khi pattern tương ứng khớp.
- `case null` cho phép xử lý selector null tường minh; `default` không đương nhiên nhận selector null trong pattern switch.
- Compiler kiểm tra **domination** (nhánh bị bao phủ) và **exhaustiveness**. Với sealed hierarchy, có thể không cần `default` nếu đủ nhánh; việc thêm subtype đòi cập nhật các nơi phân loại phù hợp.
- **Parenthesized patterns** từng tồn tại trong preview đã bị loại bỏ ở Java 21, và qualified enum constants được phép trong case constants.
- Switch expression có thể chứa block `-> { ... yield result; }`. `yield` là cơ chế của switch expression, không phải một tính năng lần đầu xuất hiện trong Java 21.
- Runtime có thể ném `MatchException` khi một switch exhaustive tại compile time trở nên không match tại runtime; không nhầm với `NullPointerException` từ selector null.

**Kết luận về cờ:** Trên Java 21, viết mã sử dụng JEP 441 và JEP 440 **không cần** `--enable-preview`. Cờ preview chỉ cần khi đang dùng một preview feature khác của chính bản JDK đó.

## 3. Mốc nền tảng trước Java 17: vì sao dễ nhầm?

| Bản Java | Tính năng liên quan | Preview/final |
| --- | --- | --- |
| **12** | Switch expressions, JEP 325 | Preview lần 1 |
| **13** | Switch expressions, JEP 354 | Preview lần 2; chuyển sang dùng `yield` để trả giá trị từ switch expression block |
| **14** | Switch expressions, JEP 361 | **Final**; `case ... ->` và `yield` dùng ổn định, nhưng chưa có pattern switch final |
| **14** | Pattern matching for `instanceof`, JEP 305 | Preview lần 1 |
| **15** | Pattern matching for `instanceof`, JEP 375 | Preview lần 2 |
| **16** | Pattern matching for `instanceof`, JEP 394 | **Final** |
| **14 → 16** | Record classes, JEP 359 → 384 → 395 | Preview trong 14–15, **final ở 16** |
| **15 → 17** | Sealed classes, JEP 360 → 397 → 409 | Preview trong 15–16, **final ở 17** |
| **19 → 21** | Record patterns, JEP 405 → 432 → 440 | Preview ở 19–20, **final ở 21** |

### 3.1. Có `case ... ->` không có nghĩa có pattern switch

Java 14 trở lên đã có:

```java
int day = 2;
String kind = switch (day) {
    case 1, 7 -> "WEEKEND";
    default -> {
        yield "WEEKDAY";
    }
};
```

Đây là **switch expression**: các nhãn vẫn là **hằng số**, không phải type/record patterns. Nó hợp lệ trong Java 14+ mà không cần Java 21.

Ngược lại:

```java
// Không thể coi đây là cú pháp Java 14/16 final:
Object value = "hello";
String kind = switch (value) {
    case String s -> "text:" + s;
    default -> "other";
};
```

Bản `switch` có `case String s` thuộc pattern matching for switch, được preview từ Java 17 và chỉ final ở Java 21. Khác biệt không nằm ở dấu `->`, mà nằm ở việc **nhãn `case` là pattern** và selector có thể là một reference type như `Object`.

### 3.2. `instanceof` pattern từ Java 16 khác `switch` pattern

Hợp lệ từ Java 16:

```java
Object value = "hello";
if (value instanceof String s && !s.isBlank()) {
    System.out.println(s.toUpperCase());
}
```

Dùng `&&` ngay sau `instanceof` là **biểu thức Boolean** với flow scoping. Nó **không** phải cú pháp `case String s && condition` của preview Java 17/18.

Nếu mục đích chỉ là kiểm tra một kiểu, `instanceof` pattern thường đủ rõ; không cần chuyển sang `switch` pattern rồi nâng baseline runtime lên Java 21 chỉ vì phong cách.

### 3.3. Record class không đồng nghĩa record pattern

Có thể khai báo và sử dụng record ổn định từ Java 16:

```java
record Point(int x, int y) {}

Point p = new Point(2, 3);
int x = p.x();  // Gọi accessor truyền thống.
```

Nhưng cú pháp **deconstruction**:

```java
// Java 21 final; đã preview ở Java 19/20.
case Point(int x, int y) -> x + y;
```

là **record pattern**, không phải chỉ “cú pháp record”. Khi review code cần xác định **cả hai** tính năng: model là record và code đang **match record pattern**.

## 4. Ví dụ Java 21 hoàn chỉnh kết hợp các mốc

Ví dụ này gom ba thế hệ tính năng vào một chương trình:

- `dayKind` dùng **switch expression** đã final từ Java 14.
- `inspect` dùng **`instanceof` type pattern** đã final từ Java 16.
- `classify` dùng **pattern switch**, **`when`**, **record patterns lồng nhau**, `sealed`, `case null` đã có cú pháp final đầy đủ trong Java 21.

Lưu file **`PatternSwitchTimelineDemo.java`**:

```java
public class PatternSwitchTimelineDemo {
    sealed interface Message permits Text, Count, Position {}

    record Text(String value) implements Message {}
    record Count(int value) implements Message {}
    record Point(int x, int y) {}
    record Position(Point point) implements Message {}

    // Java 14: switch expression (không có pattern).
    static String dayKind(int day) {
        return switch (day) {
            case 1, 7 -> "WEEKEND";
            default -> {
                yield "WEEKDAY";
            }
        };
    }

    // Java 16: instanceof type pattern.
    static String inspect(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "NONBLANK:" + s;
        }
        return "NOT_TEXT";
    }

    // Java 21: pattern switch + when + nested record patterns.
    static String classify(Object value) {
        return switch (value) {
            case Text(String text)
                    when text != null && !text.isBlank() ->
                    "TEXT:" + text.strip();

            case Text(var text) -> "TEXT_EMPTY";

            case Count(int number) when number > 0 ->
                    "COUNT_POS:" + number;

            case Count(int number) ->
                    "COUNT_NONPOS:" + number;

            case Position(Point(int x, int y))
                    when x == 0 && y == 0 ->
                    "ORIGIN";

            case Position(Point(int x, int y)) ->
                    "POINT:" + x + "," + y;

            case Position(var point) -> "NO_POINT";
            case String text -> "RAW:" + text;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("day-1=" + dayKind(1));
        System.out.println("day-2=" + dayKind(2));
        System.out.println("instanceof=" + inspect("Java"));
        System.out.println("instanceof-blank=" + inspect(" "));

        System.out.println(classify(new Text(" hello ")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Count(3)));
        System.out.println(classify(new Count(0)));
        System.out.println(classify(
                new Position(new Point(0, 0))));
        System.out.println(classify(
                new Position(new Point(2, 5))));
        System.out.println(classify(new Position(null)));
        System.out.println(classify("legacy"));
        System.out.println(classify(null));
        System.out.println(classify(3.14));
    }
}
```

Biên dịch/chạy bằng JDK 21 hoặc mới hơn, nhắm chính xác cú pháp Java 21:

```bash
javac --release 21 PatternSwitchTimelineDemo.java
java PatternSwitchTimelineDemo
```

**Stdout:**

```text
day-1=WEEKEND
day-2=WEEKDAY
instanceof=NONBLANK:Java
instanceof-blank=NOT_TEXT
TEXT:hello
TEXT_EMPTY
COUNT_POS:3
COUNT_NONPOS:0
ORIGIN
POINT:2,5
NO_POINT
RAW:legacy
NULL
OTHER
```

**Giải thích:**

1. Hai dòng `day-...` dùng nhãn hằng và `yield`, minh họa tính năng **switch expression** chứ chưa phải pattern switch.
2. `inspect("Java")` binding `String s` sau `instanceof` và dùng `&&` short-circuit. Với chuỗi blank, kết quả là `NOT_TEXT`.
3. Hai nhánh `Text` đặt nhánh có `when` trước nhánh tổng quát. `new Text(null)` đi vào `TEXT_EMPTY` do guard `text != null` trả false.
4. Hai nhánh `Count` phân biệt số dương với không dương.
5. Hai nhánh record lồng `Position(Point(...))` phân biệt gốc tọa độ và điểm khác. `Position(null)` không khớp `Point(...)` nhưng vẫn được nhánh `Position(var point)` tiếp nhận.
6. `case String text` xử lý `String` thô không thuộc sealed `Message`; `case null` xử lý selector null, còn `default` nhận kiểu khác như `Double`.
7. Kết quả chứng minh các cú pháp ổn định khác thời điểm có thể **cùng tồn tại trong một chương trình Java 21**.

Đây là một chương trình độc lập, đã được chạy trên JDK 24 với cú pháp Java 21 và 14 dòng stdout tương ứng. Nếu một module cần triển khai trên Java 17, **không thể chỉ sao chép toàn bộ `classify`** rồi dùng flag `--release 17`: record patterns và `when` của dạng này không thuộc Java 17 final.

## 5. Chuyển mã qua các phiên bản: những thay đổi nguy hiểm

### 5.1. Guard `&&` của Java 17/18 preview so với `when` từ Java 19

**Dạng Java 17/18 preview (lịch sử):**

```java
// Preview Java 17/18, không phải cú pháp guard Java 21.
case String s && s.length() > 3 -> "long";
```

**Dạng Java 19/20 preview và Java 21 final:**

```java
// Cú pháp ổn định từ Java 21.
case String s when s.length() > 3 -> "long";
```

Hai đoạn trên chỉ là **case fragments**, không phải chương trình độc lập. Chúng cũng **không cùng ý nghĩa với `instanceof String s && ...`** đặt trong một điều kiện Boolean.

Nếu đang nâng từ JDK 17 preview lên 21, phải đổi **cú pháp** và xem lại **quy tắc dominance, exhaustiveness, null** — không chỉ đổi một chuỗi token.

### 5.2. Null trong preview và final

Java 21:

```java
Object input = null;

String result = switch (input) {
    case String text -> "text";
    case null -> "missing";
    default -> "other";
};
```

Trả `missing`. Nếu bỏ `case null` và selector null, có thể ném `NullPointerException`, **dù có `default`**.

Quy tắc null trong quá trình preview đã được điều chỉnh ở Java 19. Khi đọc một ví dụ Java 17/18 về **total pattern** và `null`, hãy kiểm tra JEP/release thực tế; không mặc nhiên suy ra behavior Java 21. Ngoài ra, record pattern lồng không tự khớp một record component null chỉ vì selector ngoài khác null.

### 5.3. Exhaustiveness và lỗi runtime

Một pattern `switch` expression cần bao phủ các kiểu có thể gặp. Với sealed hierarchy, compiler có thể xác minh tính exhaustive:

```java
sealed interface Result permits Ok, Error {}
record Ok(String value) implements Result {}
record Error(int code) implements Result {}

// Đoạn minh họa trong một method nhận Result result:
return switch (result) {
    case Ok ok -> ok.value();
    case Error error -> "E:" + error.code();
};
```

Đoạn này **không có `default`** vì bộ subtype được phép đã được bao phủ.

Nếu sau này thêm subtype và code switch **được biên dịch lại**, compiler có thể yêu cầu bổ sung case. Nếu chạy bytecode cũ với hierarchy đã thay đổi ở runtime, có thể gặp `MatchException`. Việc JEP 433 (Java 20 preview) tinh chỉnh lỗi runtime trên enum và Java 21 final có `MatchException` là ví dụ rõ rằng **semantics qua preview có thể thay đổi**.

**Không chữa mọi lỗi exhaustive bằng `default -> "OTHER"`** nếu domain muốn compiler nhắc xử lý subtype mới; việc thêm fallback có thể che một thay đổi cần review.

### 5.4. Record pattern và khả năng suy luận generic

Với:

```java
record Box<T>(T value) {}
Box<String> box = new Box<>("A");

// Ví dụ trong switch expression trên box (Java 21):
case Box(String text) -> text;
```

Generic record pattern inference được cải thiện trong vòng preview Java 20 (JEP 432), rồi final trong Java 21 với record patterns (JEP 440). Khi đọc ví dụ Java 19 preview có các type arguments tường minh hoặc named record pattern, không mặc định đoạn code ấy sẽ giữ nguyên cú pháp ở Java 21.

**Không nhầm “record được khai báo từ Java 16” với “record pattern có từ Java 16”.**

## 6. Bật preview đúng cách: điều nên và không nên làm

Một preview language feature **phụ thuộc phiên bản JDK phát hành nó**; việc bật `--enable-preview` không biến mọi preview cũ thành API ổn định trong bản JDK mới.

| Mục tiêu | Lệnh/thiết lập | Ghi chú |
| --- | --- | --- |
| **Java 21 final** | `javac --release 21 App.java` | Dùng syntax/API Java 21; **không cần preview** cho pattern switch hoặc record patterns final. |
| **Java 17 preview** | `javac --enable-preview --release 17 App.java` | Phải dùng **JDK 17**, và khi chạy dùng `java --enable-preview App` trên JDK 17. |
| **Java 19 preview** | `javac --enable-preview --release 19 App.java` | Phải dùng **JDK 19**, dùng cú pháp preview tương ứng và bật preview lúc chạy. |
| **Java 20 preview** | `javac --enable-preview --release 20 App.java` | Phải dùng **JDK 20**, không phải JDK 21. |
| **Java 27 preview mở rộng primitives** | `javac --enable-preview --release 27 App.java` | Phải dùng **JDK 27**, chạy với `java --enable-preview App`. Đây là **preview primitive patterns**, không phải pattern switch reference đã final từ 21. |

`App.java` chỉ là **tên chương trình minh họa**. Thay bằng file source thực tế phù hợp phiên bản được chọn.

Để kiểm tra môi trường, dùng:

```bash
java -version
javac -version
```

Trong Maven/Gradle, cấu hình Java toolchain và release/source target nhất quán với JDK sử dụng. Việc IDE hiển thị cú pháp màu đẹp hoặc hỗ trợ highlight **không bảo đảm build CI có cùng JDK**.

### 6.1. Tại sao không dùng JDK 24 để bật lại preview Java 17?

Preview được gắn với release cụ thể. Một JDK mới có thể **không hỗ trợ** biên dịch lại một preview feature của bản cũ dưới cờ `--release 17 --enable-preview`. Bạn cần JDK 17 để biên dịch preview Java 17, hoặc **nâng cú pháp** lên tính năng final tương đương ở Java 21.

Điều quan trọng trong migration là **chuyển source sang ngữ nghĩa chuẩn mới**, chứ không dựa vào flag để khôi phục một phiên bản preview đã bị thay đổi.

### 6.2. `--release` và khả năng chạy trên runtime cũ

`javac --release 21` đặt mức source language, class-file target và Java SE APIs theo Java 21. Class đã biên dịch cho Java 21 **không thể giả định** chạy trên JVM 17.

Ví dụ nếu một ứng dụng vẫn triển khai trên JVM 17:

- Dùng cú pháp `instanceof String s` final từ Java 16 và `switch` hằng số theo Java 14.
- Hoặc lên kế hoạch nâng **runtime target lên Java 21+** trước khi sử dụng pattern switch/record patterns final.
- Không chỉ thay source flag trong IDE rồi hy vọng máy chủ Java 17 hiểu class file Java 21.

Nếu thư viện muốn hỗ trợ nhiều mức Java, cần một chiến lược có chủ đích (ví dụ source set/module riêng hoặc multi-release JAR khi phù hợp), thay vì nhét tính năng Java 21 vào source Java 17.

## 7. Sau Java 21: pattern switch đã final, nhưng primitive patterns vẫn có preview

Đến **Java 27 (tháng 9/2026)**, một hướng mở rộng riêng là **Primitive Types in Patterns, `instanceof`, and `switch`**. Nó **không làm pattern switch reference types trở về preview**; chỉ mở thêm các ngữ cảnh pattern/selector dùng kiểu nguyên thủy, vốn bị giới hạn ở Java 21.

| Release | JEP | Trạng thái của mở rộng primitive patterns |
| --- | --- | --- |
| Java **23** | **455** | Preview lần 1 |
| Java **24** | **488** | Preview lần 2 |
| Java **25** | **507** | Preview lần 3 |
| Java **26** | **530** | Preview lần 4 |
| Java **27** | **532** | Preview lần 5; vẫn **chưa final** |

Ví dụ selector primitive `long`:

```java
// Chỉ minh họa mở rộng primitive switch ở bản JDK
// có preview tương ứng; KHÔNG hợp lệ trong --release 21.
long value = 5L;

String label = switch (value) {
    case long n when n > 0L -> "positive";
    case long n -> "non-positive";
};
```

Khi chạy ví dụ primitive mới trên JDK 27, cần dùng `--enable-preview` cho bản Java 27. Không bê ví dụ này vào Java 21 chỉ vì `case String s` đã final ở 21.

Đối với Java 21, selector primitive được hỗ trợ của `switch` gồm `byte`, `short`, `char`, `int`; các kiểu primitive `long`, `float`, `double`, `boolean` **chưa được phép làm selector**. Java 27 preview mở rộng phạm vi nhưng bản chất preview vẫn cần xem lại trước khi đưa vào baseline ổn định.

**Ngoài phạm vi:** Unnamed patterns/variables và những thay đổi cú pháp ngôn ngữ khác cũng có timeline riêng. Không nên gộp chúng vào timeline JEP 406→441 như thể tất cả là cùng một tính năng.

## 8. Bảng lựa chọn phiên bản theo nhu cầu

| Muốn viết | Mốc final tối thiểu | Ghi chú |
| --- | --- | --- |
| `switch (int)` trả giá trị với `case 1 ->` | **Java 14** | Switch expression final; không cần type pattern. |
| `if (obj instanceof String s)` | **Java 16** | `instanceof` pattern final. |
| `sealed interface` với `permits` | **Java 17** | Sealed types final; độc lập với pattern switch final. |
| `switch (Object) { case String s -> ... }` | **Java 21** | Pattern switch final; Java 17–20 có preview nhưng không phải final. |
| `case String s when s.length() > 3` | **Java 21** | Cú pháp `when` xuất hiện trong preview Java 19; final từ 21. |
| `case Point(int x, int y)` | **Java 21** | Record patterns final; record *declaration* đã final từ 16. |
| Pattern switch trên sealed types, không cần `default` nếu exhaustive | **Java 21** | Pattern switch final; sealed types final từ 17. |
| `switch(long)` với primitive type patterns | **Chưa có mốc final tính đến Java 27** | Preview JEP 455/488/507/530/532; dùng đúng JDK và flag. |

**Nhận định triển khai:** Nếu cần code pattern switch chạy ổn định cho mọi người trong nhóm mà không phụ thuộc preview, Java 21 là baseline dễ xác định. Nếu vẫn phải hỗ trợ Java 17, hãy dùng type patterns với `instanceof`, switch expressions không pattern, hoặc để logic Java 21 trong một thành phần có runtime tương thích.

## 9. Lỗi thường gặp khi đọc ví dụ từ các release khác nhau

1. **Nhầm `case ... ->` với pattern switch.** Arrow switch expressions đã final ở Java 14; pattern case chỉ final ở 21.
2. **Nhầm `instanceof` pattern đã final Java 16 với switch pattern.** Java 16 không có `case String s` final.
3. **Nhầm record class với record pattern.** Record class final 16, record patterns final 21.
4. **Đem `case String s && guard` từ Java 17/18 preview vào Java 21.** Phải dùng `case String s when guard`.
5. **Cho rằng Java 19 đã final vì có `when`.** Java 19 vẫn là preview lần 3.
6. **Cho rằng Java 20 final vì gần Java 21.** Java 20 vẫn là preview lần 4.
7. **Cho rằng `--enable-preview` trên JDK mới bật lại mọi preview cũ.** Preview gắn với bản JDK phát hành; mã cũ có thể cần sửa.
8. **Sử dụng `--release 21` nhưng triển khai runtime Java 17.** Class file/API/source target không tương thích với JVM cũ.
9. **Tin rằng `case null` và `default` là tương đương.** Selector null có quy tắc riêng của pattern switch.
10. **Đặt pattern kiểu cha trước kiểu con.** Compiler có thể phát hiện dominated case; guard/case ordering cũng ảnh hưởng logic.
11. **Tin rằng mọi exhaustive switch không thể lỗi runtime.** Thay đổi enum/sealed hierarchy theo kiểu separate compilation có thể tạo `MatchException`.
12. **Nhầm primitive patterns preview Java 27 với pattern switch final Java 21.** Đây là hai mức ổn định khác nhau.
13. **Đọc tài liệu JEP cũ như cú pháp khuyến nghị hiện tại.** Một JEP preview là ảnh chụp thiết kế ở thời điểm đó; code mới nên tham chiếu JLS/JDK target.
14. **Giữ preview flag trong build mà không kiểm tra cần dùng hay không.** Chỉ bật nếu thật sự có preview feature của JDK đang sử dụng; tránh làm build phụ thuộc preview vô ích.

## 10. Checklist khi nâng Java 17/19/20 lên 21

- [ ] Xác định runtime thấp nhất thực sự dùng trong production và source/toolchain của CI.
- [ ] Tìm `case` type/record patterns cùng mọi chỗ dùng `--enable-preview`.
- [ ] Nếu code Java 17/18 dùng `case T t && condition`, chuyển sang `case T t when condition`.
- [ ] Đối chiếu precedence của constant labels, guarded patterns và unguarded patterns.
- [ ] Kiểm tra null selector, nullable record components, `case null` và hành vi ngoại lệ.
- [ ] Với sealed hierarchy, xác minh exhaustive switch và tác động của việc thêm subtype.
- [ ] Với record patterns, xem lại syntax preview cũ, generic inference và nested record null.
- [ ] Biên dịch lại toàn bộ source theo target Java 21; không giả định preview cũ tái sử dụng bytecode.
- [ ] Chạy unit, integration, regression tests và kiểm tra artifact/dependency ở runtime.
- [ ] Xóa preview flag khi code chỉ dùng các tính năng đã final trong Java 21.
- [ ] Nếu có primitive patterns của Java 23–27, tách chúng thành phần preview riêng và ghi rõ JDK/flag được yêu cầu.

**Ghi nhớ:** “`switch` có dấu `->`” là câu chuyện **Java 14**; “`switch` có `case Type variable`” bắt đầu **preview Java 17** và **final Java 21**; “`case Record(component patterns)`” final **Java 21**; còn “`switch` trên mọi primitive type” vẫn là **preview ở Java 27**. Khi chọn source level, hãy dựa trên **cú pháp thực tế của case labels** và **tình trạng final/preview của tính năng đang dùng**, không chỉ nhìn tên phương thức `switch`.

### Tài liệu tham khảo

- Oracle Java 21 — Language Changes by Release: https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 17 — Pattern Matching (preview syntax): https://docs.oracle.com/en/java/javase/17/language/pattern-matching.html
- Oracle Java 27 — Language Changes Summary: https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html
- Oracle Java 27 — Primitive Types in Patterns, instanceof, and switch (preview): https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html
- Oracle — Preview Language and VM Features: https://docs.oracle.com/en/java/javase/23/language/preview-language-and-vm-features.html
- OpenJDK JEP 406, 420, 427, 433, 441 (pattern switch): https://openjdk.org/jeps/441
- OpenJDK JEP 405, 432, 440 (record patterns): https://openjdk.org/jeps/440
- OpenJDK JEP 532 (primitive patterns fifth preview): https://openjdk.org/jeps/532
