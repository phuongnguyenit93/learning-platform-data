# Checklist sắp xếp `case` trong Java Pattern Matching

## 1. Mục tiêu của checklist

Khi viết pattern matching cho `switch`, **thứ tự các `case` là một phần của hành vi chương trình**, không chỉ là cách trình bày đẹp. Cùng một selector có thể phù hợp với nhiều pattern hoặc guard; Java sẽ chọn nhánh đáp ứng quy tắc matching theo thứ tự trong `switch`. Một số thứ tự sai bị compiler chặn bằng lỗi **dominance**, nhưng có những thứ tự vẫn biên dịch mà cho kết quả nghiệp vụ sai.

Bài này là checklist thực hành để **sắp xếp, review và kiểm thử các nhánh `case`** trong Java 21, với các tình huống về:

- Hằng số cụ thể, type pattern, kiểu cha–con và interface.
- Guard `when` đúng/sai, nhánh dự phòng không guard.
- Record patterns lồng nhau, dữ liệu component null.
- `case null`, `default`, và các giá trị không thuộc tập pattern hiện có.
- `sealed` hierarchy, enum, generic collections.
- Nguy cơ đổi hành vi khi refactor thứ tự, và phân biệt với `switch` cổ điển có fall-through.

**Phiên bản:** type patterns trong `switch` và record patterns đều là tính năng chính thức từ **Java 21** (JEP 441, JEP 440), không cần `--enable-preview`. Các ví dụ hoàn chỉnh dùng `javac --release 21`.

## 2. Nguyên tắc chính: case phù hợp đầu tiên thắng

Xét một object chuỗi `"hello"`. Nó vừa là `String`, vừa là `CharSequence`, vừa là `Object`. Vì vậy một `switch(Object)` với nhiều type patterns có thể có các nhãn **chồng vùng nhận dữ liệu**.

Java xét các switch labels theo thứ tự xuất hiện để chọn nhánh thích hợp; compiler còn kiểm tra **dominance** và từ chối nhiều trường hợp một label ở dưới không thể khớp vì label đứng trước đã phủ toàn bộ giá trị tương ứng.

Điều cần phân biệt:

1. **Lỗi dominance tĩnh:** compiler chứng minh một nhãn sau bị nhãn trước che hoàn toàn. Source **không biên dịch**.
2. **Lỗi ưu tiên nghiệp vụ:** compiler không thể hoặc không buộc chứng minh điều kiện guard chồng nhau; source có thể biên dịch nhưng nhánh dự kiến không được chọn.
3. **Lỗi không exhaustive:** sau khi sắp xếp, một `switch` expression hoặc enhanced switch statement có thể thiếu đường đi cho một subtype/giá trị hợp lệ.
4. **Lỗi runtime logic:** các nhánh có thể đầy đủ về kiểu nhưng trả kết quả sai, xử lý `null` sai hoặc ném lỗi không mong đợi.

Một `switch` không phải “rule engine tự chọn case cụ thể nhất”. **Hãy thiết kế thứ tự rõ ràng.**

## 3. Checklist nhanh trước khi review từng nhánh

Khi cần một thứ tự dễ hiểu cho pattern `switch`, cách ưu tiên thường hữu ích là:

1. **Hằng số/enum constants đặc biệt trước** pattern nhận nhiều giá trị cùng kiểu, nếu selector và loại nhãn cho phép.
2. **Pattern cụ thể có guard** trước pattern cùng kiểu không guard.
3. **Subtype cụ thể** trước supertype/interface tổng quát.
4. **Record pattern lồng và các điều kiện cấu trúc riêng** trước pattern cùng record loại rộng hơn.
5. **Pattern tổng quát không guard** để xử lý phần còn lại của kiểu, khi đó là hợp đồng mong muốn.
6. **`case null`** ở một vị trí dễ thấy (thường đầu hoặc gần cuối); nó có ngữ nghĩa riêng.
7. **`default` cuối cùng** khi thật sự cần fallback cho các giá trị còn lại.

Đây là **gợi ý thiết kế, không phải ngữ pháp bắt buộc đúng cho mọi `switch`**. Ví dụ `case null` có thể hợp lệ sau `case Object o`, vì type pattern `Object o` ở selector ngoài không match `null`. Tuy nhiên `default` không thể tùy ý đặt trước các pattern mới, và `case null, default` nên nằm cuối.

**Ưu tiên số một là giữ ngữ nghĩa nghiệp vụ** và làm compiler chấp nhận, chứ không phải sắp xếp máy móc theo một bảng tần suất.

## 4. Dominance: đặt kiểu chuyên biệt trước kiểu tổng quát

### Đoạn sai — cố tình không biên dịch

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence sequence -> "sequence";
        case String text -> "string";
        default -> "other";
    };
}
```

`String implements CharSequence`, nên bất cứ chuỗi non-null nào khớp `String` cũng đã khớp `CharSequence` trước đó. Compiler Java 21 báo **case `String` bị dominated**.

### Sửa đúng thứ tự

```java
static String correct(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence sequence -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
```

Các phương thức trên là **đoạn minh họa bên trong một class**, không phải chương trình độc lập. Với bản đúng:

- `"hi"` → `"string"`.
- `new StringBuilder("hi")` → `"sequence"`.
- `null` → `"null"`.
- `42` → `"other"`.

**Review:** hãy duyệt tất cả quan hệ `extends`/`implements`, không chỉ quan hệ lớp trực tiếp. Ví dụ `ArrayList<?>` cũng là `List<?>`, và nhiều interface khác nhau vẫn có thể được cùng một class implements.

## 5. Hằng số trước type pattern rộng: compiler có thể chặn nhãn bị che

Một type pattern không guard có thể nhận **mọi giá trị tương ứng với type**; nó có thể che luôn hằng số cùng kiểu.

Đoạn dưới đây **cố tình không biên dịch**:

```java
static String wrong(String command) {
    return switch (command) {
        case String value -> "any-string";
        case "START" -> "start";
        case null -> "null";
    };
}
```

Case `"START"` bị pattern `String value` đứng trước nhận mất. Compiler báo dominance; không thể “cứ để vậy vì `START` hiếm gặp”.

Cách viết đúng với trường hợp đặc biệt:

```java
static String correct(String command) {
    return switch (command) {
        case "START", "BEGIN" -> "start";
        case String value when value.isBlank() -> "blank";
        case String value -> "text:" + value;
        case null -> "null";
    };
}
```

Ở đây các hằng `"START"`, `"BEGIN"` đi trước guard và pattern chuỗi tổng quát; từ khóa `when` chỉ thêm điều kiện cho type pattern tương ứng. Không có `default` vì `String value` xử lý toàn bộ chuỗi non-null và `case null` xử lý null.

## 6. Ví dụ chạy được: hằng số, guard, type pattern và null

Lưu `ConstantCaseDemo.java`:

```java
public class ConstantCaseDemo {
    static String label(String value) {
        return switch (value) {
            case "START", "BEGIN" ->
                    "start";

            case String text when text.isBlank() ->
                    "blank";

            case String text ->
                    "text:" + text;

            case null ->
                    "null";
        };
    }

    public static void main(String[] args) {
        String[] inputs = {
            "START", "BEGIN", " ", "hello", null
        };

        for (String input : inputs) {
            System.out.println(label(input));
        }
    }
}
```

```bash
javac --release 21 ConstantCaseDemo.java
java ConstantCaseDemo
```

Stdout chính xác:

```text
start
start
blank
text:hello
null
```

Từ ví dụ, có thể rút ra quy tắc thực hành: **giá trị đặc biệt → guard đặc biệt → pattern tổng quát → null policy**. Quy tắc này cần được biến thành test, đặc biệt khi có thay đổi danh sách constants hoặc nhiều guard cùng kiểu.

## 7. Guard `when`: compiler không luôn giúp bắt sai ưu tiên

Các nhãn có `when` không nhất thiết bị compiler xem là phủ hoàn toàn một hằng ở phía sau, ngay cả khi guard thực tế đúng với hằng đó. Vì vậy code sau **có thể biên dịch** nhưng cho kết quả không mong đợi nếu nghiệp vụ muốn ưu tiên số `1`:

```java
static String surprising(Integer value) {
    return switch (value) {
        case Integer number when number > 0 -> "positive";
        case 1 -> "one";
        case Integer number -> "other";
        case null -> "null";
    };
}
```

Khi `value = 1`, nhánh guard đứng trước khớp và trả `"positive"`, nên nhánh `case 1` không được chọn. Đây là **lỗi ưu tiên nghiệp vụ**, không phải lỗi dominance tĩnh trong tình huống này.

### Mẫu sắp xếp rõ ý định hơn

```java
static String classify(Integer value) {
    return switch (value) {
        case 1 -> "one";
        case Integer number when number > 0 -> "positive";
        case Integer number -> "other";
        case null -> "null";
    };
}
```

- `classify(1)` → `"one"`.
- `classify(2)` → `"positive"`.
- `classify(-1)` → `"other"`.
- `classify(null)` → `"null"`.

**Checklist:** khi case có guard và case hằng chồng điều kiện, đặt **constant quan trọng trước**, trừ khi nghiệp vụ cố ý cho guard ưu tiên. Đừng chỉ dựa vào việc code biên dịch mà kết luận thứ tự đúng.

## 8. Ví dụ đầy đủ: phân loại `Object` với guard và hierarchy

Lưu `CaseOrderingDemo.java`:

```java
public class CaseOrderingDemo {
    static String describe(Object input) {
        return switch (input) {
            case String text when text.isBlank() ->
                    "blank";

            case String text ->
                    "text:" + text;

            case CharSequence sequence ->
                    "sequence:" + sequence.length();

            case Number number
                    when number.doubleValue() >= 0 ->
                    "nonnegative:" + number;

            case Number number ->
                    "negative:" + number;

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            "",
            "java",
            new StringBuilder("xy"),
            2,
            -3,
            null,
            new Object()
        };

        for (Object value : inputs) {
            System.out.println(describe(value));
        }
    }
}
```

```bash
javac --release 21 CaseOrderingDemo.java
java CaseOrderingDemo
```

Stdout:

```text
blank
text:java
sequence:2
nonnegative:2
negative:-3
null
other
```

**Phân tích thứ tự:**

- `case String ... when ...` đứng trước `case String ...` để xử lý chuỗi blank.
- Cả hai `String` case đứng trước `CharSequence`, vì `String` là subtype của `CharSequence`.
- Với `Number`, guard cho số không âm đứng trước nhánh `Number` không guard.
- `case null` xử lý selector null; `default` xử lý mọi kiểu non-null còn lại không thuộc các nhóm trên.

Trong ví dụ, `number.doubleValue()` dùng để phân chia nhóm số đơn giản. Với số cực lớn, `NaN`, `BigDecimal` hoặc yêu cầu chính xác tiền tệ, cần quy tắc so sánh khác phù hợp domain. Bài này kiểm thử **thứ tự case**, không khẳng định cách so sánh số đó là chuẩn cho mọi nghiệp vụ.

## 9. Record pattern: cấu trúc cụ thể trước fallback tổng quát

Record patterns cho phép matching theo component của một record. Nếu một nhánh có nested record pattern và một nhánh chỉ nhận record ở mức ngoài, hãy ưu tiên nhánh phân loại cụ thể trước.

Ví dụ mô hình:

```java
record Payload(int code) {}
record Packet(String id, Payload payload) {}
```

Một thứ tự hợp lý:

```java
static String describe(Object value) {
    return switch (value) {
        case Packet(var id, Payload(var code))
                when code >= 400 ->
                "error:" + id + ":" + code;

        case Packet(var id, Payload(var code)) ->
                "ok:" + id + ":" + code;

        case Packet(var id, var payload) ->
                "missing-payload:" + id;

        case null -> "null";
        default -> "other";
    };
}
```

Đây là **đoạn minh họa đặt cùng phạm vi với hai record**, không phải file độc lập. Nhánh có guard kiểm tra code lỗi đứng trước record pattern lồng không guard; nhánh rộng `Packet(var id, var payload)` nhận những `Packet` chưa được xử lý, bao gồm trường hợp `payload == null`.

Record pattern lồng `Payload(...)` **không khớp** nếu chính reference `Payload` là null. Nhưng một type pattern ở vị trí component có thể có quy tắc null-matching riêng khi unconditional với kiểu component; vì vậy không nên suy luận “mọi pattern con đều loại null”. Khi xử lý payload bắt buộc, nên validate ở constructor/factory và có test tương ứng.

## 10. Ví dụ chạy được: thứ tự nested record patterns

Lưu `RecordCaseOrderDemo.java`:

```java
public class RecordCaseOrderDemo {
    record Payload(int code) {}
    record Packet(String id, Payload payload) {}

    static String label(Object value) {
        return switch (value) {
            case Packet(var id, Payload(var code))
                    when code >= 400 ->
                    "error:" + id + ":" + code;

            case Packet(var id, Payload(var code)) ->
                    "ok:" + id + ":" + code;

            case Packet(var id, var payload) ->
                    "missing-payload:" + id;

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            new Packet("A", new Payload(503)),
            new Packet("B", new Payload(200)),
            new Packet("C", null),
            null,
            "plain"
        };

        for (Object input : inputs) {
            System.out.println(label(input));
        }
    }
}
```

```bash
javac --release 21 RecordCaseOrderDemo.java
java RecordCaseOrderDemo
```

Stdout:

```text
error:A:503
ok:B:200
missing-payload:C
null
other
```

Các test của record `Packet` xác nhận **guard true/false, nested record có/thiếu, selector null và giá trị không phải Packet**. Nếu đảo thứ tự để `case Packet(var id, var payload)` đứng đầu, các pattern cụ thể phía sau sẽ bị che hoặc compiler từ chối do dominance.

## 11. `sealed` hierarchy: khi thêm subtype, không dùng `default` để né trách nhiệm

Với sealed root, một `switch` expression có thể exhaustive khi xử lý hết các permitted subtype phù hợp, không cần `default`.

Ví dụ:

```java
sealed interface Event permits Created, Confirmed, Cancelled {}
record Created(String id) implements Event {}
record Confirmed(String id, int units) implements Event {}
record Cancelled(String id) implements Event {}
```

Khi `Confirmed` có guard, **phải còn đường đi cho `Confirmed` không thỏa guard** nếu cần exhaustive:

```java
return switch (event) {
    case Confirmed(var id, var units)
            when units >= 10 -> "bulk:" + id;

    case Confirmed(var id, var units) ->
            "confirmed:" + id + ":" + units;

    case Created(var id) -> "created:" + id;
    case Cancelled(var id) -> "cancelled:" + id;
    case null -> "null";
};
```

Nhánh rộng `Confirmed` đứng ngay sau nhánh có guard. Thứ tự giữa các subtype record **không có quan hệ kế thừa trực tiếp** có thể thay đổi mà không làm đổi type coverage, nhưng nên nhóm theo domain và bảo toàn test.

Nếu thêm subtype `Refunded` mà compiler báo thiếu exhaustive case, hãy **bổ sung logic xử lý rõ ràng** thay vì vội thêm `default -> "unknown"`. `default` có thể che việc domain đã xuất hiện biến thể mới cần được xem xét.

## 12. Chương trình hoàn chỉnh: kiểm thử thứ tự trên sealed hierarchy

Lưu `SealedCaseOrderDemo.java`:

```java
public class SealedCaseOrderDemo {
    sealed interface Event
            permits Created, Confirmed, Cancelled {}

    record Created(String id) implements Event {}
    record Confirmed(String id, int units) implements Event {}
    record Cancelled(String id) implements Event {}

    static String label(Event event) {
        return switch (event) {
            case Confirmed(var id, var units)
                    when units >= 10 ->
                    "bulk:" + id;

            case Confirmed(var id, var units) ->
                    "confirmed:" + id + ":" + units;

            case Created(var id) ->
                    "created:" + id;

            case Cancelled(var id) ->
                    "cancelled:" + id;

            case null ->
                    "null";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Created("C"),
            new Confirmed("A", 20),
            new Confirmed("B", 3),
            new Cancelled("X"),
            null
        };

        for (Event event : events) {
            System.out.println(label(event));
        }
    }
}
```

```bash
javac --release 21 SealedCaseOrderDemo.java
java SealedCaseOrderDemo
```

Stdout:

```text
created:C
bulk:A
confirmed:B:3
cancelled:X
null
```

Case `Confirmed` với guard và case `Confirmed` không guard là một cặp bắt buộc cho định tuyến đầy đủ của subtype này. Nếu xóa nhánh không guard trong `switch` expression, compiler có thể báo không exhaustive. Đó là một kiểm tra **tại compile time**, bổ sung cho runtime tests.

## 13. `case null` nên đặt đâu?

`case null` là một nhãn riêng; đừng coi nó tương đương `default`. Với reference selector, nếu không có `case null` thích hợp, `switch(null)` thường ném `NullPointerException`.

Ví dụ:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

Đây là **phương thức minh họa**. Có thể đặt `case null` ở cuối trước `default` nếu phù hợp cách đọc. Về mặt luật Java 21, ví dụ sau **vẫn hợp lệ**:

```java
static String classify(Object value) {
    return switch (value) {
        case Object any -> "non-null";
        case null -> "missing";
    };
}
```

`case Object any` nhận mọi object **khác null** còn `case null` nhận null. Bởi vậy, checklist “`case null` bắt buộc ở đầu” là **sai**; quy tắc tốt là **đặt ở chỗ dễ thấy và có test xác nhận**.

Cũng có thể dùng:

```java
case null, default -> "missing-or-other";
```

khi **cố ý gom null và mọi giá trị còn lại** vào một nhánh; đây là dạng label được phép ở Java 21 và nên đặt **cuối**. Tuy nhiên, cách gộp này không phù hợp nếu nghiệp vụ cần phân biệt null với giá trị không hỗ trợ.

## 14. `default` đặt sau các pattern; đừng để nó che case khác

Khi có `default`, cách viết nhất quán là đặt nó **cuối switch block**. Điều này làm phạm vi fallback rõ ràng và tránh các vấn đề dominance.

Tránh các trường hợp:

- Đặt pattern tổng quát trước pattern chuyên biệt.
- Đặt `default` trước các pattern/nhãn `null`.
- Dùng `case null, default` rồi thêm case mới phía sau.
- Dùng `default` để bỏ qua subtype mới của sealed hierarchy.
- Nhầm `default` với một policy null.

Có một số kiểu `switch` truyền thống cho phép sắp đặt nhãn khác thường vì lý do tương thích lịch sử, nhưng đó **không phải phong cách tốt** cho code pattern `switch` mới.

Nếu đã có một pattern unconditional bao phủ toàn bộ selector type, thêm `default` có thể bị compiler coi là không hợp lệ hoặc thừa theo quy tắc dominance. Chỉ dùng fallback khi nó có ý nghĩa thực tế.

## 15. Generic collections: subtype trước interface và wildcard cho type argument

Giả sử selector là `Object`, muốn phân biệt `ArrayList` với các `List` khác. Mẫu hợp lý:

```java
static String kind(Object value) {
    return switch (value) {
        case java.util.ArrayList<?> list ->
                "arraylist:" + list.size();

        case java.util.List<?> list ->
                "list:" + list.size();

        case null -> "null";
        default -> "other";
    };
}
```

Đặt `List<?>` lên trước `ArrayList<?>` sẽ làm nhánh `ArrayList` bị che bởi nhánh tổng quát. Mã dùng wildcard `<?>` thay vì raw `List`; Java runtime **không bảo đảm generic element type** chỉ từ type pattern cho collection.

`kind(new ArrayList<>(List.of(1, 2)))` trả `"arraylist:2"`, còn `kind(List.of(1))` trả `"list:1"` theo những implementation cụ thể của `List.of` và `ArrayList`.

Nếu nghiệp vụ cần `List<String>`, hãy kiểm tra từng phần tử hoặc dùng API generic có contract tĩnh. Không dùng raw type hoặc unchecked cast để qua compiler khi sắp xếp pattern.

## 16. Enum constants: case cụ thể trước pattern enum bao phủ cả kiểu

Một enum có thể dùng hằng số `case` và một type pattern tổng quát trong pattern `switch`, ví dụ:

```java
enum State { NEW, RUNNING, DONE }

static String describe(State state) {
    return switch (state) {
        case DONE -> "done";
        case NEW -> "new";
        case State any -> "other-state";
        case null -> "null";
    };
}
```

Đây là **đoạn minh họa trong class có enum State**, không phải file độc lập. Nếu `case State any` đứng trước `case DONE`, hằng `DONE` ở dưới bị dominated và compiler có thể báo lỗi.

Nếu enum có số lượng giá trị cố định và từng hằng có logic riêng, có thể liệt kê **mọi enum constant mà không cần default** để compiler phát hiện khi một constant mới được thêm (đối với `switch` expression và quy tắc exhaustive phù hợp).

**Không dùng pattern `State any` chỉ để tránh viết các case khác** nếu yêu cầu nghiệp vụ là xử lý riêng từng enum constant.

## 17. `switch` statement với `:` có rủi ro fall-through khác thứ tự matching

Trong code mới, `case ... ->` không tự fall-through sang thân nhánh tiếp theo. Trong legacy `switch` statement dùng dấu `:`, thiếu `break` có thể làm chạy tiếp các lệnh của case sau:

```java
int n = 1;
switch (n) {
    case 1:
        System.out.println("one");
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
```

Đoạn trên **là các lệnh trong method**, không phải file độc lập. Stdout:

```text
one
two
```

Đây là **fall-through**, không phải case `2` tự khớp với selector `1`. Khi refactor statement truyền thống sang `switch` rules với `->`, kiểm tra xem chương trình cũ có dựa vào fall-through hay không; đổi sang `->` có thể làm đổi hành vi.

Với các pattern variables trong switch statement kiểu colon, còn có quy tắc scope/definite assignment hạn chế luồng điều khiển. Ưu tiên `->` cho mã pattern `switch` mới để tránh những rủi ro không cần thiết.

## 18. Các lỗi compile-negative nên giữ làm ví dụ học tập

Để compiler kiểm tra ranh giới, dùng những fixture **cố tình không biên dịch** sau ở một source set riêng.

**A. Supertype trước subtype:**

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence s -> "sequence";
        case String s -> "string";
        default -> "other";
    };
}
```

**B. Case không guard trước cùng type có guard:**

```java
static String wrong(Object value) {
    return switch (value) {
        case String s -> "all-strings";
        case String s when s.length() > 3 -> "long";
        default -> "other";
    };
}
```

**C. Guard trên sealed subtype nhưng thiếu fallback:**

```java
sealed interface Action permits Go, Stop {}
record Go(int level) implements Action {}
record Stop() implements Action {}

static int wrong(Action action) {
    return switch (action) {
        case Go(var level) when level > 0 -> 1;
        case Stop stop -> 0;
    };
}
```

Đoạn A/B bị compiler từ chối vì dominance; đoạn C bị từ chối vì **không exhaustive** khi `Go.level <= 0`. Đây là **đoạn minh họa được đặt trong class** (các khai báo type ở cùng scope phù hợp), không phải ba chương trình runnable độc lập.

Kiểm thử âm tính nên xác nhận `javac` trả exit code khác 0 và đúng nhóm nguyên nhân; không cần match tuyệt đối văn bản lỗi, vì diagnostic có thể khác giữa các bản JDK.

## 19. Checklist test sau khi đổi thứ tự

Ngay cả khi code biên dịch, bộ test nên chứng minh các nhánh ưu tiên đúng.

| Case cần kiểm thử | Input mẫu | Output tham chiếu |
| --- | --- | --- |
| Hằng số ưu tiên | `"START"` | `start` trong ConstantCaseDemo |
| Hằng alias | `"BEGIN"` | `start` |
| Guard chuỗi đúng | `" "` | `blank` |
| Guard chuỗi sai | `"hello"` | `text:hello` |
| `String` vs `CharSequence` | `"java"` | `text:java` trong CaseOrderingDemo |
| Cha–con interface | `new StringBuilder("xy")` | `sequence:2` |
| Guard số đúng | `2` | `nonnegative:2` |
| Guard số sai | `-3` | `negative:-3` |
| Nested record guard đúng | `Packet("A", Payload(503))` | `error:A:503` |
| Nested record guard sai | `Packet("B", Payload(200))` | `ok:B:200` |
| Nested payload null | `Packet("C", null)` | `missing-payload:C` |
| Sealed subtype mới | Thêm permitted subtype | Build phải được rà soát/cập nhật |
| `null` selector | `null` | Nhánh `case null` đúng hợp đồng |
| Không khớp pattern | `new Object()` | Nhánh `default` nếu có |

Hãy thử cả ranh giới guard, ví dụ `code = 399` và `400`, hoặc `units = 9` và `10`; input ở xa ngưỡng có thể bỏ sót lỗi `>` so với `>=`.

**Một test quan trọng đặc biệt:** khi `case Integer i when i > 0` đứng trước `case 1`, hãy assert rằng input `1` được xử lý theo mục tiêu nghiệp vụ. Compiler cho phép đoạn này nhưng không tự đoán được bạn muốn `"one"` hay `"positive"`.

## 20. Cách review từng bước

Khi nhận một `switch` mới hoặc một diff sắp xếp lại `case`, thực hiện theo thứ tự:

1. **Ghi kiểu tĩnh của selector:** enum, sealed root, `Object`, generic interface hay record?
2. **Vẽ quan hệ subtype:** những nhãn `case` nào có thể khớp cùng một object?
3. **Đánh dấu hằng đặc biệt:** constants/enum values có cần ưu tiên trước type pattern tổng quát không?
4. **Đánh dấu tất cả guards:** guard nào có vùng nhận dữ liệu chồng lên hằng hoặc guard khác?
5. **Đặt cấu trúc record cụ thể trước cấu trúc bao quát:** nested pattern và guard trước outer record fallback.
6. **Kiểm tra exhaustive:** với sealed/enum, có case không guard bao phủ các giá trị guard bị false không?
7. **Chốt chính sách `null`:** trả kết quả, ném lỗi hay xử lý ở tầng boundary?
8. **Đưa `default` xuống cuối nếu dùng:** nó có thật sự cần hay chỉ che thiếu nhánh?
9. **Phân biệt `->` với `:`:** có rủi ro fall-through khi refactor code legacy không?
10. **Biên dịch với đúng target Java:** ví dụ `javac --release 21`, không thêm preview flag.
11. **Chạy test mỗi nhánh và ranh giới guard:** xác nhận ưu tiên, kết quả và side effects.
12. **Review theo domain:** compiler chứng minh type coverage, không chứng minh business logic chính xác.

Bước 2 và 4 đặc biệt quan trọng: **một thay đổi thứ tự có thể làm lỗi ngay ở compile time hoặc âm thầm thay đổi kết quả runtime**, tùy cấu trúc pattern.

## 21. Một số hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Java luôn chọn pattern cụ thể nhất dù nằm cuối” | Nhãn được xét theo thứ tự; nhãn bị dominated có thể bị từ chối |
| “Chỉ cần build thành công thì thứ tự đúng” | Guard có thể che hằng mà compiler không báo |
| “Guard `when` luôn dominate hằng bên dưới” | Guard không thường được dùng để suy luận dominance với mọi hằng |
| “Case hằng cứ đặt đâu cũng được” | Hằng có thể bị pattern cùng kiểu không guard che |
| “Cứ có `case T t` là không cần case khác” | Có thể che nhánh đặc biệt và làm mất xử lý theo nghiệp vụ |
| “Record pattern lồng luôn an toàn với null” | Nested record reference null khiến nested pattern không khớp |
| “`case null` bắt buộc là case đầu” | Không bắt buộc; nên đặt rõ ràng và test |
| “`default` nhận cả `null`” | `default` riêng không phải chính sách xử lý null |
| “Thêm `default` là cách sửa sealed exhaustive tốt nhất” | Có thể che subtype mới cần xử lý |
| “`List<String>` kiểm tra được bằng runtime pattern” | Type erasure vẫn tồn tại; dùng wildcard và kiểm tra component |
| “Case với `->` tự chạy tiếp nhánh kế tiếp” | Switch rule `->` không fall-through như colon statement cũ |
| “Đưa nhánh hay gặp lên đầu luôn tăng tốc” | Phải giữ ngữ nghĩa; cần benchmark mới có kết luận hiệu năng |

## 22. Checklist cuối cùng có thể dùng ngay

**Trước khi merge một `switch` có pattern:**

- [ ] Kiểu selector và tập runtime types đã rõ ràng.
- [ ] Constants/enum cases đặc biệt nằm trước pattern bao phủ chúng.
- [ ] Các subtype cụ thể đứng trước supertype/interface rộng hơn.
- [ ] Với cùng một kiểu, các case `when` ưu tiên nằm trước case không guard.
- [ ] Các guards chồng điều kiện đã được test về **ưu tiên**, kể cả khi compiler không báo.
- [ ] Nested record patterns có fallback đúng cho component null hoặc giá trị thiếu.
- [ ] Sealed/enum switch vẫn exhaustive; không thêm `default` chỉ để hết lỗi.
- [ ] `case null` có chính sách đúng; `default` đứng cuối nếu có.
- [ ] Không có nhãn bị dominated hoặc trùng hằng số.
- [ ] Không đổi behavior khi chuyển `:` sang `->`.
- [ ] Có test hằng đặc biệt, subtype, guard true/false, boundary, null và fallback.
- [ ] Build dùng Java 21 final và không phụ thuộc cú pháp preview cũ.

**Kết luận:** Checklist sắp xếp `case` phải kiểm tra **loại và phạm vi giá trị mỗi nhánh nhận**, không chỉ xem các dòng được xếp đẹp. Mẫu thường hữu ích là **hằng/ngoại lệ cụ thể → guarded patterns → unguarded patterns → fallback**, kết hợp thứ tự **subtype trước supertype** và chính sách `null` rõ ràng. Quan trọng nhất, hãy test cả những lỗi **compiler không thể nhận ra vì guard mang ý nghĩa nghiệp vụ**.

## Tài liệu chính thức

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java SE 21 — Pattern Matching for switch (dominance, when, null)](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 Language Specification §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
