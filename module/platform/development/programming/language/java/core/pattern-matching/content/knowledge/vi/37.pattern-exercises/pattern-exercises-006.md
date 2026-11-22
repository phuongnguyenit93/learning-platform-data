# Sửa lỗi dominated case trong Java Pattern Matching (Java 21+)

## 1. Mục tiêu của bài thực hành

Khi áp dụng type patterns, record patterns và guard `when` vào `switch`, **thứ tự các `case` có ý nghĩa**. Nếu một nhánh trước đã bao phủ mọi giá trị mà một nhánh sau có thể nhận, nhánh sau được gọi là **dominated case**. Java không cho biên dịch nhiều trường hợp như vậy vì nhánh bị che **không thể được chọn** theo quy tắc matching.

Thông báo điển hình:

```text
this case label is dominated by a preceding case label
```

Ví dụ **cố tình không biên dịch**:

```java
static String label(Object value) {
    return switch (value) {
        case CharSequence sequence -> "SEQUENCE";
        case String text -> "STRING"; // DOMINATED
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

`String` implements `CharSequence`, nên mọi giá trị `String` đã khớp nhánh `CharSequence`. Compiler không bao giờ có thể chọn nhánh `String`.

**Sửa theo ý định cần String riêng:**

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "STRING";
        case CharSequence sequence -> "SEQUENCE";
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Nguyên tắc khởi đầu:

- Với quan hệ kiểu cha/con: **kiểu cụ thể trước, kiểu tổng quát sau**.
- Với cùng pattern: **guard có ý nghĩa nghiệp vụ trước, nhánh không guard sau**.
- Với nhãn hằng và pattern bao phủ hằng đó: đặt **hằng trước nhánh tổng quát** nếu loại selector cho phép hằng.
- Với record pattern lồng: xem **cả cấu trúc và kiểu từng component**, không chỉ tên record ngoài.
- Với `sealed` hierarchy: giữ exhaustive coverage và bổ sung test khi thêm subtype.
- Quan trọng nhất: **không chỉ sửa để hết lỗi compiler, mà phải giữ đúng hành vi nghiệp vụ**.

**Phiên bản:** Pattern matching for `switch` (JEP 441) và record patterns (JEP 440) trở thành tính năng chuẩn từ **Java 21**. Bài dùng JDK 21+, không cần `--enable-preview`. Pattern matching for `instanceof` đã chuẩn từ Java 16 (JEP 394).

## 2. Mô hình tập giá trị: hiểu vì sao case bị che

Hãy nghĩ mỗi nhãn `case` là một tập giá trị có thể áp dụng:

| Case label | Tập giá trị theo trực giác |
| --- | --- |
| `case String s` | Các String khác null |
| `case CharSequence cs` | Các CharSequence, bao gồm String/StringBuilder |
| `case Integer n` | Các Integer khác null |
| `case Integer n when n > 0` | Các Integer dương |
| `case 0` | Giá trị hằng 0, nếu selector phù hợp kiểu |
| `case Parcel(var id, int grams)` | Những record Parcel có cấu trúc tương ứng |
| `case Parcel(var id, int grams) when grams > 100` | Tập con của Parcel có grams lớn hơn 100 |
| `case null` | Chính selector null; **không** phải mọi record component null |

Nếu nhánh A đứng trước và compiler chứng minh mọi giá trị của nhánh B đều được A tiếp nhận, B bị dominated.

**Phân biệt quan trọng:** Compiler sử dụng các quy tắc dominance tĩnh của ngôn ngữ; nó **không giải được mọi biểu thức logic của `when`**. Có những trường hợp compiler cho biên dịch nhưng người review vẫn nhận ra nhánh sau không được chọn vì guard phía trước che mất.

Ví dụ:

```java
case Integer n when n >= 0 -> "NON_NEGATIVE";
case Integer n when n > 0 -> "POSITIVE";
case Integer n -> "NEGATIVE";
```

Với mọi n dương, nhánh đầu đúng trước, nên nhánh `POSITIVE` không được chọn. Java 21 **không nhất thiết báo dominated** do không chứng minh quan hệ giữa hai guard động. Đây là **semantic shadowing** — vấn đề đúng/sai nghiệp vụ, khác với compile-time domination.

Từ đó có hai lớp review: **compiler có chấp nhận switch không?** và **đầu vào thực tế có vào đúng nhánh mong muốn không?**

## 3. Bảng chẩn đoán nhanh

| Trường hợp | Compiler Java 21 | Hướng xử lý |
| --- | --- | --- |
| `case CharSequence cs` trước `case String s` | Dominated | Đưa String lên trước |
| `case Number n` trước `case Integer i` | Dominated | Đưa Integer lên trước |
| `case String s` trước `case String s when s.isBlank()` | Dominated | Đưa guard lên trước |
| `case String s when true` trước `case String s` | Dominated | Bỏ guard true hoặc thiết kế lại nhánh |
| `case Integer i` trước `case 0`, selector `Integer` | Dominated | Xử lý 0 trước |
| `case Parcel(var id, int grams)` trước `case Parcel(String id, int grams) when grams > 100` | Dominated | Record pattern cụ thể/guard trước |
| `case Integer n when n >= 0` trước `case Integer n when n > 0` | Có thể hợp lệ | Sửa ưu tiên và test overlap |
| `case 0` trong `switch(Object)` | **Không tương thích kiểu nhãn** | Dùng selector Integer hoặc pattern Integer |
| Một `switch` expression trên `Object` chỉ có case `Integer` | **Non-exhaustive** | Xác định fallback hoặc các kiểu còn thiếu |
| Hai `case 1` trùng nhau | **Duplicate case** | Xóa/tránh nhãn hằng trùng |

Điểm quan trọng trong bảng: **không phải lỗi liên quan `case` nào cũng là dominated**. Đọc đúng vị trí và thông báo compiler trước khi thay code.

## 4. Bài tập 1 — Type pattern cha che subtype

### Mã lỗi

Lưu `BadType.java`:

```java
class BadType {
    static String classify(Object value) {
        return switch (value) {
            case CharSequence seq -> "sequence";
            case String s -> "string"; // Dominated
            case null -> "null";
            default -> "other";
        };
    }
}
```

Thử biên dịch trên JDK 21:

```bash
javac --release 21 BadType.java
```

`String` là một `CharSequence`, nhưng ngược lại một `StringBuilder` không phải `String`. Do đó nhánh rộng đứng trước che nhánh hẹp.

### Bản sửa đúng

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "string";
        case CharSequence seq -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
```

Ma trận kiểm thử:

- `"abc"` → `string`.
- `new StringBuilder("abc")` → `sequence`.
- `42` → `other`.
- `null` → `null`.

**Không sửa bằng cách xóa nhánh String** nếu nghiệp vụ muốn xử lý String đặc biệt. Ngược lại, nếu hai nhánh thực sự có cùng hành vi, gộp chúng cũng có thể là một refactor tốt.

Trường hợp tổng quát: `Number` có thể che `Integer`, `Long`, `Double`; một interface cha che subtype implements interface đó. Không cần class inheritance trực tiếp mới có quan hệ dominance.

## 5. Bài tập 2 — Nhánh không guard che nhánh có guard

### Mã lỗi

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "TEXT";
        case String s when s.isBlank() -> "BLANK"; // Dominated
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Nhánh `String` đầu tiên nhận tất cả chuỗi, trong đó có chuỗi rỗng và blank. Điều kiện `when` ở nhánh sau không có cơ hội đánh giá.

### Sửa

```java
static String classify(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Test `""` và `"  "` → BLANK; `"abc"` → TEXT.

**Lưu ý:** guard chỉ được xét khi phần pattern đã khớp, và một guard trả `false` cho phép switch thử nhãn sau. Guard ném exception thì exception được truyền ra, **không coi như false**.

### Trường hợp đặc biệt: `when true`

```java
// Không biên dịch:
case String s when true -> "ANY_STRING";
case String s -> "OTHER_STRING"; // Dominated
```

JLS Java 21 xem `when true` là **unguarded** cho mục đích domination. Đừng thêm `when true` để “né” compiler, cũng đừng coi nó là cách dự phòng cho một guard sẽ viết về sau.

Nếu guard là lời gọi method, compiler không tự chứng minh method luôn trả true. Vì vậy “chưa bị compiler báo” không có nghĩa nhánh sau có thể được chọn.

## 6. Bài tập 3 — Constant label bị pattern bao phủ

Ví dụ cố tình không biên dịch:

```java
class BadConstant {
    static String classify(Integer value) {
        return switch (value) {
            case Integer n -> "INTEGER";
            case 0 -> "ZERO"; // Dominated
        };
    }
}
```

Nhánh type pattern `case Integer n` đã nhận Integer bằng 0, nên nhãn `case 0` bị che.

### Sửa

```java
static String classify(Integer value) {
    return switch (value) {
        case 0 -> "ZERO";
        case Integer n when n < 0 -> "NEGATIVE:" + n;
        case Integer n -> "POSITIVE:" + n;
        case null -> "NO_NUMBER";
    };
}
```

Giá trị 0 được chọn trước, sau đó số âm, còn lại là số dương. `case null` trả riêng cho selector null.

**Cẩn thận với kiểu selector:** `case 0` **không hợp lệ** trong `switch(Object)` của Java 21. Ở đó compiler báo loại constant label không tương thích, chứ không phải dominated:

```java
// Không biên dịch trong Java 21:
Object value = Integer.valueOf(0);
String result = switch (value) {
    case 0 -> "ZERO"; // Nhãn hằng không tương thích Object
    default -> "OTHER";
};
```

Muốn phân loại 0 từ một `Object`, có thể viết:

```java
static String classify(Object value) {
    return switch (value) {
        case Integer n when n == 0 -> "ZERO";
        case Integer n -> "INTEGER:" + n;
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Đừng chỉ đổi selector type để compiler hết lỗi nếu nghiệp vụ còn nhận String/Number/record types khác.

### Guarded pattern trước constant: hợp lệ mà có thể sai ưu tiên

```java
// Mảnh case trong switch trên Integer:
case Integer n when n > 0 -> "POSITIVE";
case 1 -> "ONE";
case Integer n -> "OTHER";
```

Compiler có thể chấp nhận vì guarded pattern `n > 0` không được phân tích như unguarded pattern để dominate constant. Nhưng với `value=1`, nhánh đầu đã trả POSITIVE, nhánh ONE không chạy.

Nếu ONE cần ưu tiên:

```java
case 1 -> "ONE";
case Integer n when n > 0 -> "POSITIVE";
case Integer n -> "OTHER";
```

**Kết luận:** Compile-time domination và runtime rule priority là hai phép kiểm tra khác nhau. Phải test đúng những giá trị có thể khớp nhiều nhánh.

## 7. Bài tập 4 — Record pattern tổng quát che record pattern hẹp

Giả sử:

```java
record Parcel(String id, int grams) {}
```

Đoạn **sai**:

```java
static String group(Object value) {
    return switch (value) {
        case Parcel(var id, int grams) -> "PARCEL";
        case Parcel(String id, int grams)
                when grams > 100 -> "HEAVY"; // Dominated
        case null -> "MISSING";
        default -> "OTHER";
    };
}
```

`case Parcel(var id, int grams)` đã nhận các Parcel có grams 101, 1000, ...; nhánh còn lại không được chọn. Compiler chẩn đoán domination tương tự type pattern.

Sửa:

```java
static String group(Object value) {
    return switch (value) {
        case Parcel(var id, int grams) when grams > 100 ->
                "HEAVY";
        case Parcel(var id, int grams) -> "PARCEL";
        case null -> "MISSING";
        default -> "OTHER";
    };
}
```

Test: `Parcel("A",100)` → PARCEL; `Parcel("A",101)` → HEAVY. `Parcel("A",-1)` vẫn là PARCEL theo mã trên; **đây chưa phải validation** về khối lượng. Nếu business cấm số âm, thêm điều kiện từ chối chứ không coi pattern matching tự bảo vệ mọi invariant.

**Khi có nested record patterns:** trình tự so khớp của các component ảnh hưởng khả năng một mẫu bao phủ mẫu khác. Pattern `Delivery(Address(...))` không tự khớp nếu chính component `Address` là null; reviewer cần xét nullable component và test chứ không chỉ đếm số mức nested. Đặc tả domination của record patterns dựa trên kiểu/cấu trúc của pattern, không phải việc tên biến giống nhau.

## 8. Bài tập 5 — Case tổng quát trong sealed hierarchy

`sealed` giới hạn các subtype, cho phép compiler kiểm tra exhaustive switch.

```java
sealed interface Event permits TextEvent, CountEvent {}
record TextEvent(String text) implements Event {}
record CountEvent(int value) implements Event {}
```

Sai:

```java
// Không biên dịch:
return switch (event) {
    case Event e -> "EVENT";
    case TextEvent t -> "TEXT";  // Dominated
    case CountEvent c -> "COUNT"; // Dominated
    case null -> "NULL";
};
```

Mọi `TextEvent` và `CountEvent` đều là `Event`. Nhánh Event đứng trước nhận hết.

Sửa:

```java
return switch (event) {
    case TextEvent t -> "TEXT";
    case CountEvent c -> "COUNT";
    case null -> "NULL";
};
```

Không cần tự thêm `default` khi compiler có thể xác minh các permitted subtypes đã được xử lý. Nếu thêm subtype, những switch không có nhánh mới sẽ cần cập nhật lúc biên dịch lại.

**Đừng nhầm hai khái niệm:**

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Dominance** | Nhánh phía sau có bị nhánh trước bao phủ hoàn toàn không? |
| **Exhaustiveness** | Có cách xử lý cho mọi giá trị selector trong miền hợp lệ không? |
| **Runtime matching** | Với một input cụ thể, nhánh nào được chọn? |
| **Business completeness** | Các quy tắc nghiệp vụ đã đúng và đủ chưa? |

Một switch exhaustive vẫn có thể đặt guard sai ưu tiên; một switch không có dominated case vẫn có thể sai nghiệp vụ. Nếu class hierarchy hoặc enum thay đổi qua separate compilation, runtime còn có thể gặp `MatchException` trong những trường hợp exhaustive switch cũ không có nhãn khớp. Lỗi đó khác với compile-time dominated case.

## 9. Chương trình Java 21 hoàn chỉnh: sửa và kiểm thử

Bài lab này gom bốn bài thực hành thành một chương trình độc lập:

- `classifyEvent` dùng sealed records và record patterns, đặt guard trước fallback.
- `classifyObject` đặt String trước CharSequence, Integer trước Number.
- `classifyInteger` đặt constant 0 trước Integer pattern.
- `referenceEvent`, `referenceObject` được viết bằng `if/instanceof` để đối chiếu.
- `overlapping` cố ý chứa semantic shadowing (biên dịch được), minh họa giới hạn compiler.
- Kiểm tra **25 trường hợp cụ thể**, cùng **48 đối chiếu hồi quy** không ném lỗi.

Lưu file **`DominatedCaseRepairLab.java`**:

```java
public class DominatedCaseRepairLab {
    sealed interface Event permits Text, Metric, Heartbeat {}

    record Text(String value) implements Event {}
    record Metric(int value) implements Event {}
    record Heartbeat() implements Event {}

    static String classifyEvent(Event event) {
        return switch (event) {
            case Text(String text)
                    when text != null && text.isBlank() ->
                    "TEXT_BLANK";

            case Text(String text)
                    when text != null && text.length() >= 5 ->
                    "TEXT_LONG:" + text.length();

            case Text(var text) ->
                    "TEXT:" + text;

            case Metric(int n) when n == 0 ->
                    "METRIC_ZERO";

            case Metric(int n) when n < 0 ->
                    "METRIC_NEGATIVE";

            case Metric(int n) ->
                    "METRIC:" + n;

            case Heartbeat() ->
                    "HEARTBEAT";

            case null ->
                    "MISSING_EVENT";
        };
    }

    static String referenceEvent(Event event) {
        if (event == null) return "MISSING_EVENT";

        if (event instanceof Text t) {
            String text = t.value();

            if (text != null && text.isBlank())
                return "TEXT_BLANK";

            if (text != null && text.length() >= 5)
                return "TEXT_LONG:" + text.length();

            return "TEXT:" + text;
        }

        if (event instanceof Metric m) {
            int n = m.value();

            if (n == 0) return "METRIC_ZERO";
            if (n < 0) return "METRIC_NEGATIVE";

            return "METRIC:" + n;
        }

        if (event instanceof Heartbeat)
            return "HEARTBEAT";

        throw new AssertionError("unknown event");
    }

    static String classifyObject(Object value) {
        return switch (value) {
            case String text when text.isBlank() ->
                    "RAW_BLANK";

            case String text ->
                    "RAW:" + text;

            case CharSequence other ->
                    "SEQUENCE:" + other.length();

            case Integer n when n == 0 ->
                    "INT_ZERO";

            case Integer n ->
                    "INT:" + n;

            case Number n ->
                    "NUMBER:" + n;

            case null ->
                    "NULL";

            default ->
                    "OTHER";
        };
    }

    static String referenceObject(Object value) {
        if (value == null)
            return "NULL";

        if (value instanceof String text)
            return text.isBlank() ? "RAW_BLANK" : "RAW:" + text;

        if (value instanceof CharSequence other)
            return "SEQUENCE:" + other.length();

        if (value instanceof Integer n)
            return n == 0 ? "INT_ZERO" : "INT:" + n;

        if (value instanceof Number n)
            return "NUMBER:" + n;

        return "OTHER";
    }

    static String classifyInteger(Integer value) {
        return switch (value) {
            case 0 -> "ZERO";

            case Integer n when n < 0 ->
                    "NEGATIVE:" + n;

            case Integer n ->
                    "POSITIVE:" + n;

            case null ->
                    "NO_NUMBER";
        };
    }

    // Biên dịch được, nhưng nhánh n>0 bị n>=0 che
    // về mặt logic với mọi số dương.
    static String overlapping(Integer value) {
        return switch (value) {
            case Integer n when n >= 0 ->
                    "NON_NEGATIVE";

            case Integer n when n > 0 ->
                    "POSITIVE";

            case Integer n ->
                    "NEGATIVE";

            case null ->
                    "NULL";
        };
    }

    static void assertEqual(
            String expected, String actual, String context) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(
                    context + " expected=" + expected
                            + " actual=" + actual);
        }
    }

    static void checkEvent(
            String label, Event event, String expected) {
        String actual = classifyEvent(event);

        assertEqual(expected, actual, label);
        assertEqual(
                referenceEvent(event), actual,
                label + " oracle");

        System.out.println(label + " => " + actual);
    }

    static void checkObject(
            String label, Object value, String expected) {
        String actual = classifyObject(value);

        assertEqual(expected, actual, label);
        assertEqual(
                referenceObject(value), actual,
                label + " oracle");

        System.out.println(label + " => " + actual);
    }

    static void checkInteger(
            String label, Integer value, String expected) {
        String actual = classifyInteger(value);

        assertEqual(expected, actual, label);
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        checkEvent(
                "event-empty", new Text(""), "TEXT_BLANK");
        checkEvent(
                "event-blank", new Text("  "), "TEXT_BLANK");
        checkEvent(
                "event-short", new Text("hey"), "TEXT:hey");
        checkEvent(
                "event-boundary",
                new Text("abcde"), "TEXT_LONG:5");
        checkEvent(
                "event-long",
                new Text("abcdef"), "TEXT_LONG:6");
        checkEvent(
                "event-null-component",
                new Text(null), "TEXT:null");
        checkEvent(
                "event-zero", new Metric(0), "METRIC_ZERO");
        checkEvent(
                "event-negative",
                new Metric(-2), "METRIC_NEGATIVE");
        checkEvent(
                "event-positive",
                new Metric(7), "METRIC:7");
        checkEvent(
                "event-heartbeat",
                new Heartbeat(), "HEARTBEAT");
        checkEvent(
                "event-null-selector",
                null, "MISSING_EVENT");

        checkObject(
                "raw-blank", "  ", "RAW_BLANK");
        checkObject(
                "raw-string", "hello", "RAW:hello");
        checkObject(
                "raw-builder",
                new StringBuilder("xy"), "SEQUENCE:2");
        checkObject(
                "raw-int-zero", 0, "INT_ZERO");
        checkObject(
                "raw-int-negative", -3, "INT:-3");
        checkObject(
                "raw-int", 42, "INT:42");
        checkObject(
                "raw-long", 42L, "NUMBER:42");
        checkObject(
                "raw-double", 2.5, "NUMBER:2.5");
        checkObject(
                "raw-null", null, "NULL");
        checkObject(
                "raw-other", true, "OTHER");

        checkInteger(
                "int-zero", 0, "ZERO");
        checkInteger(
                "int-negative", -5, "NEGATIVE:-5");
        checkInteger(
                "int-positive", 8, "POSITIVE:8");
        checkInteger(
                "int-null", null, "NO_NUMBER");

        int checks = 0;
        for (int n = -20; n <= 20; n++) {
            Event event = new Metric(n);

            assertEqual(
                    referenceEvent(event),
                    classifyEvent(event),
                    "metric sweep " + n);

            checks++;
        }

        for (String s : new String[] {
                null, "", " ", "a", "abcd", "abcde", "abcdef"
        }) {
            Event event = new Text(s);

            assertEqual(
                    referenceEvent(event),
                    classifyEvent(event),
                    "text sweep " + s);

            checks++;
        }

        System.out.println(
                "regression=" + checks + " PASS");
        System.out.println(
                "overlap-positive=" + overlapping(3));
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 DominatedCaseRepairLab.java
java DominatedCaseRepairLab
```

**Stdout chính xác:**

```text
event-empty => TEXT_BLANK
event-blank => TEXT_BLANK
event-short => TEXT:hey
event-boundary => TEXT_LONG:5
event-long => TEXT_LONG:6
event-null-component => TEXT:null
event-zero => METRIC_ZERO
event-negative => METRIC_NEGATIVE
event-positive => METRIC:7
event-heartbeat => HEARTBEAT
event-null-selector => MISSING_EVENT
raw-blank => RAW_BLANK
raw-string => RAW:hello
raw-builder => SEQUENCE:2
raw-int-zero => INT_ZERO
raw-int-negative => INT:-3
raw-int => INT:42
raw-long => NUMBER:42
raw-double => NUMBER:2.5
raw-null => NULL
raw-other => OTHER
int-zero => ZERO
int-negative => NEGATIVE:-5
int-positive => POSITIVE:8
int-null => NO_NUMBER
regression=48 PASS
overlap-positive=NON_NEGATIVE
```

Chương trình đã được thực thi bằng **JDK 24 JShell**, sử dụng cú pháp Java 21, cho **26 dòng stdout** như trên. Các phương thức `assertEqual` so sánh đầu ra với giá trị cố định và baseline độc lập; nếu sai sẽ ném `AssertionError`. Vòng hồi quy kiểm tra 41 giá trị int từ -20 tới 20 và 7 chuỗi, tổng **48 lần đối chiếu**. Lệnh `javac --release 21` dùng để biên dịch mã khi lưu file trong project tương thích.

**Có chủ đích:** phương thức `overlapping` là một **ví dụ lỗi logic chưa sửa** và dòng `overlap-positive=NON_NEGATIVE` minh họa nhánh `when n >= 0` nhận input 3 trước `when n > 0`. Không nên sử dụng hàm này làm classifier thực tế nếu muốn trả POSITIVE.

## 10. Phân tích ba nhóm pattern trong lab

### 10.1. Text: các guard ưu tiên đứng trước fallback

```java
case Text(String text)
        when text != null && text.isBlank() -> "TEXT_BLANK";

case Text(String text)
        when text != null && text.length() >= 5 ->
        "TEXT_LONG:" + text.length();

case Text(var text) -> "TEXT:" + text;
```

- Chuỗi blank và empty → nhánh đầu.
- Chuỗi không blank, độ dài từ 5 → nhánh thứ hai.
- Chuỗi ngắn hơn hoặc component `text == null` → nhánh fallback.

Ở đây `String.length()` đếm UTF-16 code units, không phải tất cả ký tự mà người dùng nhìn thấy. Nếu nghiệp vụ cần độ dài theo grapheme cluster, phải thay hợp đồng và implementation chứ không phải chỉ sửa dominated case.

`text != null && ...` tránh NPE qua short-circuit. Với `new Text(null)`, selector là record `Text` **khác null**; `case null` không xử lý record component null.

### 10.2. Metric: giá trị biên trước mẫu tổng quát

```java
case Metric(int n) when n == 0 -> "METRIC_ZERO";
case Metric(int n) when n < 0 -> "METRIC_NEGATIVE";
case Metric(int n) -> "METRIC:" + n;
```

Zero, negative và positive được tách rõ. Nhánh không guard cuối có tác dụng fallback cho Metric. Nếu đặt nhánh đó lên đầu, các nhánh đặc biệt phía sau bị dominated.

### 10.3. Object: hai cây kiểu chồng lấn độc lập

```java
case String text when text.isBlank() -> "RAW_BLANK";
case String text -> "RAW:" + text;
case CharSequence other -> "SEQUENCE:" + other.length();

case Integer n when n == 0 -> "INT_ZERO";
case Integer n -> "INT:" + n;
case Number n -> "NUMBER:" + n;
```

Trong nhóm thứ nhất, String phải ở trước CharSequence. Trong nhóm thứ hai, Integer phải ở trước Number. `StringBuilder` và `Long` trong test chứng minh các nhánh tổng quát **vẫn có input riêng** và không bị biến thành nhánh chết.

Với String, guard blank đứng trước unguarded String. Với Integer, guard zero đứng trước unguarded Integer. Dấu `->` đảm bảo không fall-through sang nhánh sau khi một rule được chọn.

## 11. Guard chồng lấn không nhất thiết bị javac phát hiện

Xét:

```java
case Integer n when n >= 10 -> "AT_LEAST_TEN";
case Integer n when n > 100 -> "VERY_LARGE";
case Integer n -> "SMALL";
```

Nếu n=101, hai guard đầu đều đúng; case thứ nhất trả AT_LEAST_TEN. Compiler có thể cho biên dịch vì không chứng minh tổng quát mối quan hệ giữa điều kiện của các guard.

Nếu muốn VERY_LARGE ưu tiên:

```java
case Integer n when n > 100 -> "VERY_LARGE";
case Integer n when n >= 10 -> "AT_LEAST_TEN";
case Integer n -> "SMALL";
```

Test cần có **9, 10, 100, 101**. Đây là phân tích **chồng lấn nghiệp vụ**, không chỉ là compiler fix. Guard có thể gọi method tùy ý; với method có side effect, việc đổi thứ tự còn có thể đổi số lần gọi và trạng thái, nên cần test tương ứng.

### Một trường hợp cần tránh: side effect trong guard

```java
// Anti-pattern minh họa; không phải chương trình độc lập:
// case Transfer t when chargeCard(t) -> "PAID";
// case Transfer t -> "REJECTED";
```

Nếu `chargeCard(t)` thực hiện trừ tiền trước khi trả false, switch có thể xét nhánh sau nhưng side effect đã xảy ra. Nên dùng guard thuần túy để kiểm tra điều kiện, rồi thực hiện hành động trong handler đã chọn và được bảo vệ bởi transaction/idempotency phù hợp. Một switch không bị dominated **không đồng nghĩa** nó an toàn về side effect.

## 12. Null, default và exhaustive không thay thế nhau

- **`case null`** kiểm tra chính selector null.
- **`default`** là nhánh dự phòng cho các giá trị không có case khác áp dụng theo ngữ nghĩa switch; trong pattern switch Java 21, nó **không mặc nhiên thay thế xử lý null selector**.
- **Nested record pattern** có thể không match khi một record component lồng là null, dù record ngoài khác null.
- **Exhaustiveness** là yêu cầu switch expression/enhanced switch có đường xử lý cho mọi selector theo mô hình compile-time.
- **Dominance** là lỗi một case bị case trước che. Đây là hai khái niệm khác nhau.

Nếu xóa một nhánh tổng quát để sửa domination, chương trình có thể báo thêm **switch not exhaustive** vì giờ thiếu đường xử lý một kiểu khác. Đó không phải lý do để thêm `default -> null` tùy tiện; hãy xác định cách xử lý phần còn thiếu theo business contract.

Với sealed hierarchy, việc không có default đôi khi là lợi thế: thêm subtype mới khiến compiler buộc cập nhật switch khi biên dịch lại. Tuy nhiên separate compilation có thể tạo mismatch runtime; khi có `MatchException` phải điều tra version class/hierarchy hoặc component null ở đúng tầng.

## 13. Quy trình sửa trong code review

**Bước 1 — Xác định selector type.** `switch(Object)`, `switch(Integer)` hay `switch(SealedInterface)` có những nhãn hợp lệ và yêu cầu exhaustiveness khác nhau.

**Bước 2 — Tìm nhánh bao phủ.** Đi lên từ case lỗi, kiểm tra type cha/con, record shape, unguarded pattern, constant và `when true`. Đừng chỉ nhìn hai dòng ngay bên cạnh; nhánh che có thể nằm ở đầu switch.

**Bước 3 — Xác nhận business priority.** Ví dụ “Integer cần xử lý đặc biệt” khác với “Integer có thể dùng chung Number”. Chỉ đổi thứ tự nếu đó thực sự là hành vi mong muốn.

**Bước 4 — Chọn phương án sửa.** Có thể chuyển case cụ thể lên trước, thu hẹp guard, gộp những nhánh cùng hành vi, hoặc tách logic dài thành helper rõ nghĩa. Không thay một bug compiler bằng cast thủ công dễ gây `ClassCastException` runtime.

**Bước 5 — Biên dịch lại.** Sử dụng JDK 21+ và source level phù hợp; nếu công cụ báo lỗi preview do source level 17–20, đó là vấn đề cấu hình JDK khác với domination.

**Bước 6 — Test vùng giao.** Tập trung vào giá trị có thể khớp nhiều nhánh: subtype String và CharSequence, Integer và Number, 0, giá trị biên của guard, null selector, null component và record nested.

**Bước 7 — Kiểm tra exception/side effect.** Khi di chuyển case có handler tác động hệ thống, so sánh không chỉ output mà cả database changes, event phát ra, exception type và số lần gọi.

**Bước 8 — Review exhaustive coverage.** Nếu thêm subtype vào sealed model hoặc bỏ một nhánh tổng quát, cập nhật case phù hợp thay vì che lỗi bằng default vô điều kiện.

## 14. Những lỗi sửa nhanh cần tránh

1. Xóa nhánh bị gạch lỗi mà không hiểu hợp đồng nghiệp vụ.
2. Thêm một `default` để “chữa” dominated pattern; có thể làm phát sinh lỗi khác hoặc che sự thiếu hụt domain.
3. Dùng `when true` để lách compiler, trong khi nó được xem như nhánh không guard cho domination.
4. Đưa một supertype lên đầu switch rồi hy vọng subtype case phía sau vẫn chạy.
5. Dùng guard gọi method không thuần túy chỉ để tránh domination.
6. Tin mọi cặp guard chồng lấn sẽ bị compiler phát hiện.
7. Không test đúng giá trị overlap/biên vì chỉ chạy happy path.
8. Nhầm lỗi incompatible constant với dominated case.
9. Nhầm duplicate constant labels với dominated case.
10. Nhầm thiếu exhaustiveness với dominated case.
11. Quên rằng selector null và nested record component null khác nhau.
12. Không xem thứ tự/kiểu record components trong nested record patterns.
13. Chuyển code về chuỗi cast/`instanceof` thủ công nhưng không giữ đúng exception/side effect.
14. Sửa thứ tự nhánh và làm đổi business priority không có regression tests.
15. Đặt một pattern quá rộng (`case Object o`, `case Event e`) lên đầu rồi giữ hàng loạt case cụ thể ở sau.
16. Cho rằng một switch compile xanh là đã kiểm thử đầy đủ mọi kiểu và mọi guard.
17. Không chú ý version Java: pattern switch/record patterns cần Java 21 final.
18. Dùng `String.length()` và giả định số UTF-16 code units bằng số ký tự nhìn thấy của Unicode trong mọi domain.

## 15. Bài tập luyện tập (có gợi ý sửa)

### Bài 1 — Number và Integer

```java
// Sai:
case Number n -> "NUMBER";
case Integer i -> "INTEGER";

// Sửa:
case Integer i -> "INTEGER";
case Number n -> "NUMBER";
```

Chạy test với `Integer.valueOf(5)` và `Double.valueOf(2.5)`. Nhớ rằng các đoạn trên là **mảnh switch label**; đặt vào một switch có selector thích hợp để chạy.

### Bài 2 — Guard trên record

```java
// Sai:
case Parcel(var id, int grams) -> "NORMAL";
case Parcel(var id, int grams) when grams > 100 -> "HEAVY";

// Sửa:
case Parcel(var id, int grams) when grams > 100 -> "HEAVY";
case Parcel(var id, int grams) -> "NORMAL";
```

Test grams 100 và 101; nếu domain cấm số âm, thêm nhánh validation.

### Bài 3 — Guard logic nhưng không có compile error

```java
// Sai ý định phân loại số:
case Integer n when n >= 10 -> "TEN_PLUS";
case Integer n when n > 100 -> "VERY_LARGE";
case Integer n -> "SMALL";
```

Đưa `n > 100` lên trước `n >= 10`; viết test 9/10/100/101. Tập trung vào **mức độ ưu tiên**, không chỉ khả năng compiler chấp nhận.

### Bài 4 — Thêm subtype sealed

Có `sealed interface Message permits TextMessage, ImageMessage`, đã có switch exhaustive; bổ sung `VideoMessage` và recompile. Hãy thêm nhánh xử lý và test, không dùng default để né việc thiết kế behavior mới.

### Bài 5 — So sánh trước–sau

Tự viết một `if/instanceof` oracle cho một switch đang refactor. Tạo bảng quyết định cho String/CharSequence, Integer/Number và null. Kiểm tra kết quả trước/sau trên các input tương ứng, kể cả các giá trị chồng lấn.

## 16. Checklist trước khi approve

- [ ] Selector type và JDK source level có đúng Java 21+?
- [ ] Đã tìm đúng case đứng trước bao phủ case bị lỗi?
- [ ] Subtype đứng trước supertype nếu có chính sách riêng?
- [ ] Guarded case đứng trước cùng pattern không guard?
- [ ] Nhãn hằng đặc biệt đứng trước type pattern bao phủ nó nếu selector phù hợp?
- [ ] Không dùng `when true` hoặc guard nhân tạo chỉ để qua compiler?
- [ ] Với record pattern, đã kiểm tra thứ tự kiểu component và nullability?
- [ ] Với sealed switch, đã giữ kiểm tra exhaustiveness và test subtype mới?
- [ ] Test cả overlap và boundary của guard, không chỉ test một input ngẫu nhiên?
- [ ] Đã phân biệt dominated, duplicate, non-exhaustive và incompatible constant?
- [ ] Refactor có giữ output, exception, side effect và business priority?
- [ ] Các helper/fallback có tên dễ hiểu và không che dữ liệu không hợp lệ?
- [ ] Guard đủ thuần túy để an toàn khi được kiểm tra nhưng nhánh không được chọn?

**Kết luận:** Sửa lỗi dominated case không đơn thuần là đảo hai dòng. Phải tìm **nhánh nào bao phủ nhánh nào**, xác định **chính sách nào cần ưu tiên**, chỉnh lại thứ tự từ cụ thể/guarded tới tổng quát, rồi kiểm thử những đầu vào có thể khớp nhiều nhãn. Compiler Java 21 giúp phát hiện nhiều pattern bị domination, nhưng **guard chồng lấn về logic vẫn có thể lọt qua**, nên bài test và code review giữ vai trò quyết định.

### Tài liệu tham khảo

- Oracle Java 21 — Pattern Matching for switch, mục Pattern Label Dominance: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.11.1 Switch Blocks` và `14.30.3 Pattern Dominance`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
