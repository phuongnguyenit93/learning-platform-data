# Kiểm thử null case trong switch với Java Pattern Matching

## 1. Vì sao phải kiểm thử `null` riêng?

Từ Java 21, `switch` hỗ trợ chính thức **pattern matching**, **record patterns** và nhãn **`case null`** (JEP 441, JEP 440). Khi xử lý dữ liệu tham chiếu có thể vắng mặt, `null` là một trường hợp cần có **hợp đồng hành vi** và **bài kiểm thử riêng**, không thể suy ra chỉ từ việc `switch` đã biên dịch hoặc đã có `default`.

Ví dụ:

```java
static String show(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

Với mã này, ít nhất ba đường chạy đáng kiểm thử:

| Giá trị selector | Case được chọn | Kết quả |
| --- | --- | --- |
| `null` | `case null` | `"missing"` |
| `"hello"` | `case String text` | `"text:hello"` |
| `Integer.valueOf(5)` | `default` | `"other"` |

**Trọng tâm của việc kiểm thử** không chỉ là “chạy với `null` xem có crash không”, mà là khẳng định một cách cụ thể rằng:

1. `null` được xử lý **đúng nhánh được thiết kế**, hoặc ném đúng ngoại lệ nếu đó là hợp đồng.
2. Nhánh xử lý `null` không làm thay đổi hành vi các giá trị khác `null`.
3. `default` và mẫu tổng quát không bị nhầm là “đã xử lý `null`”.
4. Với `enum`, `sealed`, `when` và record patterns lồng nhau, có phân biệt **selector bằng `null`** với **thành phần dữ liệu bên trong bằng `null`**.
5. Cả `switch expression` lẫn `switch statement` có thể được kiểm thử qua đầu ra, trạng thái hoặc side effects quan sát được.

Bài sử dụng **Java 21+** để các cú pháp `case null`, `case String s when ...`, record patterns và các bài test đều chạy không cần preview.

## 2. Quy tắc Java cần biết trước khi viết test

### 2.1. `case null` xử lý `null` của selector

Với `switch (value)` mà `value` là một tham chiếu, nếu `value == null` và khối switch có nhãn `case null` phù hợp thì nhãn đó được chọn:

```java
String label = switch (value) {
    case null -> "no value";
    case String text -> "text";
    default -> "other";
};
```

Đây là đoạn minh họa, giả định `value` có kiểu `Object`. `case null` **không** chỉ là cách viết ngắn của `default`. Nó nêu rõ một giá trị tham chiếu đặc biệt phải được xử lý theo chính sách riêng.

### 2.2. Không có `case null` thì `switch` trên tham chiếu `null` thường ném NPE

```java
static String withoutNull(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

Dù có `default`, lời gọi `withoutNull(null)` ném **`NullPointerException`**. Một kiểm thử tốt phải **assert rằng NPE được ném**, không giả định trả `"other"`. `default` là nhánh dự phòng cho các giá trị **khác `null`** không khớp case đã liệt kê, không phải một `catch` hoặc một trường hợp bắt `null`.

### 2.3. Mẫu tổng quát không có nghĩa khớp `null`

```java
static String totalPattern(Object value) {
    return switch (value) {
        case Object anything -> "object";
    };
}
```

Mẫu `Object anything` có thể bao phủ các đối tượng khác `null` của kiểu selector `Object`. Điều đó cho phép switch được coi là **exhaustive** về tập giá trị được xét, nhưng **không** có nghĩa `null` sẽ khớp mẫu `Object`. `totalPattern(null)` vẫn ném `NullPointerException`.

Cũng vì thế, **exhaustive** không đồng nghĩa với **null-safe**. Bộ test cần kiểm tra cả tính đầy đủ nhánh và chính sách xử lý `null`.

### 2.4. Có thể gộp `case null, default` khi cùng một kết quả

```java
static String fallback(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        case null, default -> "fallback";
    };
}
```

Khi `null` và mọi giá trị khác chưa khớp đều thật sự có cùng hành vi, `case null, default` là cú pháp hợp lệ của Java 21. Nếu nghiệp vụ cần tách “không có dữ liệu” và “dữ liệu không được hỗ trợ”, hãy dùng hai nhánh riêng:

```java
case null -> "missing";
default -> "unsupported";
```

Hai dòng trên là các nhãn minh họa trong một switch đầy đủ, không phải một chương trình độc lập.

### 2.5. `case null` là kiểm tra selector, không phải mọi nơi có thể chứa null

Với `record Order(String id, Notice notice)`, hai giá trị sau rất khác nhau:

- `switch ((Object) null)`: **selector** bằng `null`, nên chạy `case null` nếu có.
- `switch (new Order("O2", null))`: selector là một instance `Order` hợp lệ, nhưng **thành phần `notice` của record bằng `null`**. Nhãn `case null` của switch không được chọn. Mẫu record khác quyết định kết quả.

Không nên viết test chỉ có một trong hai trường hợp rồi kết luận đã kiểm tra toàn bộ rủi ro `null` của mô hình.

## 3. Thiết kế ma trận kiểm thử theo hợp đồng

Khi bắt đầu viết test, liệt kê **đầu vào**, **hành vi mong muốn**, **nhánh phải được chọn** và **bằng chứng kiểm thử**. Với `switch` sử dụng pattern, một ma trận cơ sở gồm:

| Nhóm trường hợp | Ví dụ | Điều cần assert |
| --- | --- | --- |
| Selector `null`, có `case null` | `classify(null)` | Giá trị do nhánh null trả về |
| Selector `null`, chỉ có `default` | `withoutNull(null)` | `NullPointerException` được ném |
| Selector `null`, có mẫu `Object` tổng quát | `totalPattern(null)` | Vẫn ném `NullPointerException` |
| Selector `null`, có `case null, default` | `fallback(null)` | Giá trị chung theo hợp đồng |
| Kiểu khớp pattern | `"Java"` | Nhánh `String` trả đúng dữ liệu |
| Kiểu khớp nhưng guard không đúng | `" "` hoặc `Created(null)` | Nhánh dành cho điều kiện còn lại được chọn |
| Giá trị khác kiểu | `Integer`, `Boolean` | Nhánh dự phòng đúng |
| Enum selector `null` | `stage(null)` | Nhánh `case null`; hoặc NPE nếu cố ý không có |
| Sealed selector `null` | `noticeStatus(null)` | Không bị lẫn với các kiểu con |
| Record con `null` | `new Order("O2", null)` | Record ngoài vẫn khớp, mẫu con có thể không khớp |
| `switch statement` gặp `null` | `statement(null)` | Side effect/giá trị quan sát đúng |
| Exception trong selector expression | `switch (value.toString())` khi value `null` | NPE xảy ra **trước** khi switch nhận selector |

**Không được chỉ đo “coverage xanh”** rồi mặc định hợp đồng `null` đã được bảo vệ: branch coverage có thể ghi nhận một `default` nhưng không chỉ rõ nó không xử lý null. Các assertion có giá trị hơn một bài test chỉ gọi phương thức và không kiểm chứng gì.

## 4. Kịch bản đầy đủ, chạy độc lập: 26 kiểm thử có assertion

Chương trình dưới đây cố ý không phụ thuộc JUnit. Nó dùng hai hàm kiểm tra nhỏ: `equal` so kết quả kỳ vọng và `npe` xác minh một lời gọi **phải ném `NullPointerException`**. Nếu hành vi sai, chương trình ném `AssertionError` và không thể in tổng số ca đạt theo đúng kế hoạch.

Lưu nguyên văn vào tệp **`NullSwitchTests.java`**.

```java
import java.util.Objects;
import java.util.function.Supplier;

public class NullSwitchTests {
    enum Stage { NEW, DONE }

    sealed interface Notice permits Created, Cancelled {}
    record Created(String code) implements Notice {}
    record Cancelled(String reason) implements Notice {}
    record Order(String id, Notice notice) {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "selector:null";
            case String text when text.isBlank() -> "text:blank";
            case String text -> "text:" + text;
            case Number number -> "number:" + number.intValue();
            default -> "other";
        };
    }

    static String defaultDoesNotCatchNull(Object value) {
        return switch (value) {
            case String s -> "text:" + s;
            default -> "default";
        };
    }

    static String totalPatternDoesNotCatchNull(Object value) {
        return switch (value) {
            case Object any -> "object";
        };
    }

    static String combinedFallback(Object value) {
        return switch (value) {
            case String s -> "text:" + s;
            case null, default -> "fallback";
        };
    }

    static String stage(Stage stage) {
        return switch (stage) {
            case null -> "stage:null";
            case NEW -> "stage:new";
            case DONE -> "stage:done";
        };
    }

    static String stageWithoutNull(Stage stage) {
        return switch (stage) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    static String noticeStatus(Notice notice) {
        return switch (notice) {
            case null -> "notice:null";
            case Created(var code) when code != null && !code.isBlank() ->
                    "created:" + code;
            case Created(var code) -> "created:missing";
            case Cancelled(var reason) -> "cancelled:" + reason;
        };
    }

    static String nested(Object candidate) {
        return switch (candidate) {
            case null -> "order:null";
            case Order(var orderId, Created(var code)) ->
                    "order-created:" + orderId + ":" + code;
            case Order(var orderId, var notice) ->
                    "order-other:" + orderId + ":" +
                    (notice == null ? "null" : notice.getClass().getSimpleName());
            default -> "not-order";
        };
    }

    static String statement(Object value) {
        StringBuilder result = new StringBuilder();
        switch (value) {
            case null -> result.append("statement:null");
            case String s -> result.append("statement:text:").append(s);
            default -> result.append("statement:other");
        }
        return result.toString();
    }

    static int passed = 0;

    static void equal(String name, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + " expected=" + expected
                    + " actual=" + actual);
        }
        passed++;
        System.out.println("PASS " + name + "=" + actual);
    }

    static void npe(String name, Supplier<String> call) {
        try {
            call.get();
            throw new AssertionError(name
                    + " should throw NullPointerException");
        } catch (NullPointerException expected) {
            passed++;
            System.out.println("PASS " + name + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        equal("selector-null", "selector:null", classify(null));
        equal("text-blank", "text:blank", classify(" "));
        equal("text-normal", "text:Java", classify("Java"));
        equal("number", "number:3", classify(3.9));
        equal("other", "other", classify(true));

        npe("default-null", () -> defaultDoesNotCatchNull(null));
        equal("default-object", "default", defaultDoesNotCatchNull(42));
        npe("total-pattern-null", () -> totalPatternDoesNotCatchNull(null));

        equal("combined-null", "fallback", combinedFallback(null));
        equal("combined-object", "fallback", combinedFallback(42));
        equal("combined-string", "text:hello", combinedFallback("hello"));

        equal("enum-null", "stage:null", stage(null));
        equal("enum-done", "stage:done", stage(Stage.DONE));
        npe("enum-without-null", () -> stageWithoutNull(null));

        equal("sealed-null", "notice:null", noticeStatus(null));
        equal("sealed-created", "created:AB", noticeStatus(new Created("AB")));
        equal("sealed-blank", "created:missing", noticeStatus(new Created("")));
        equal("sealed-code-null", "created:missing", noticeStatus(new Created(null)));
        equal("sealed-cancelled", "cancelled:duplicate",
                noticeStatus(new Cancelled("duplicate")));

        equal("nested-selector-null", "order:null", nested(null));
        equal("nested-member-null", "order-other:O2:null",
                nested(new Order("O2", null)));
        equal("nested-created", "order-created:O1:AB",
                nested(new Order("O1", new Created("AB"))));
        equal("nested-cancelled", "order-other:O3:Cancelled",
                nested(new Order("O3", new Cancelled("x"))));

        equal("statement-null", "statement:null", statement(null));
        equal("statement-string", "statement:text:hi", statement("hi"));
        equal("statement-other", "statement:other", statement(7));

        System.out.println("TOTAL=" + passed);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 NullSwitchTests.java
java NullSwitchTests
```

**Kết quả chính xác khi cả 26 ca đạt:**

```text
PASS selector-null=selector:null
PASS text-blank=text:blank
PASS text-normal=text:Java
PASS number=number:3
PASS other=other
PASS default-null=NullPointerException
PASS default-object=default
PASS total-pattern-null=NullPointerException
PASS combined-null=fallback
PASS combined-object=fallback
PASS combined-string=text:hello
PASS enum-null=stage:null
PASS enum-done=stage:done
PASS enum-without-null=NullPointerException
PASS sealed-null=notice:null
PASS sealed-created=created:AB
PASS sealed-blank=created:missing
PASS sealed-code-null=created:missing
PASS sealed-cancelled=cancelled:duplicate
PASS nested-selector-null=order:null
PASS nested-member-null=order-other:O2:null
PASS nested-created=order-created:O1:AB
PASS nested-cancelled=order-other:O3:Cancelled
PASS statement-null=statement:null
PASS statement-string=statement:text:hi
PASS statement-other=statement:other
TOTAL=26
```

Ví dụ dùng các chuỗi đầu ra ASCII để tránh khác biệt encoding của terminal. Đoạn mã không cần thư viện ngoài JDK. Các `record` và `sealed interface` nằm trong cùng lớp để có thể biên dịch bằng một tệp duy nhất.

**Quan trọng với test runner:** tổng `TOTAL=26` chỉ được in khi tất cả `equal` và `npe` đã hoàn tất bình thường. Nếu một ca không trả giá trị hoặc không ném ngoại lệ như mong đợi, `AssertionError` khiến chương trình thất bại tại ca đó; không được diễn giải một phần stdout là kết quả PASS toàn bộ.

## 5. Phân tích ca selector null và ca guard

### 5.1. Không nhầm `null` với chuỗi rỗng

`classify` có nhánh:

```java
case null -> "selector:null";
case String text when text.isBlank() -> "text:blank";
case String text -> "text:" + text;
```

Với `null`, **`case null` chạy**; không có biến `text` được ràng buộc và không có lời gọi `text.isBlank()`. Vì thế, đây là ca kiểm thử cho **null selector**, không phải ca kiểm thử cho `String.isBlank()`.

Với `" "`, selector là một `String` khác null; guard `text.isBlank()` trả `true` và kết quả là `"text:blank"`. Với `"Java"`, guard trả `false`, Java xét tiếp mẫu `String` không có guard và trả `"text:Java"`.

Nếu test chỉ dùng `null` và `"Java"`, có thể bỏ sót lỗi logic ở nhánh chuỗi trắng. Ngược lại, chỉ dùng chuỗi trắng không chứng minh `case null` chạy đúng.

### 5.2. Tại sao còn phải kiểm tra Number và Boolean?

Trong `classify(3.9)`, `Double` là `Number`. Mã trả về `"number:3"` vì `Number.intValue()` của 3.9 trả 3. Kiểm thử giúp phát hiện vô tình thay thứ tự case hoặc thay biểu thức chuyển đổi.

`classify(true)` trả `"other"` nhờ `default` vì `Boolean` không khớp `String` hay `Number`. Đây là đối chứng với `null`: **một giá trị không được nhận diện** mới đi `default`, còn **không có giá trị** đi `case null`.

### 5.3. Vì sao phải test guard sai?

Với `noticeStatus(new Created(null))`, selector **không null**: nó là một record `Created`, nhưng component `code` bằng `null`. Record pattern `Created(var code)` có thể ràng buộc `code == null`. Guard:

```java
when code != null && !code.isBlank()
```

trả `false` khi `code` bằng `null`; nhờ short-circuit `&&`, `code.isBlank()` không được gọi nên không ném NPE. Nhánh `case Created(var code)` không guard phía sau xử lý bằng `"created:missing"`.

Bộ test xác minh cả `new Created("")` lẫn `new Created(null)` để chứng minh logic guard nhận diện đúng hai dạng thiếu mã. Test cho `noticeStatus(null)` lại là **một tình huống hoàn toàn khác**, phải trả `"notice:null"`.

## 6. `default` không bắt null: hãy kiểm thử ngoại lệ chủ động

Đây là một trong những phép thử có giá trị nhất khi bảo trì switch:

```java
static String defaultDoesNotCatchNull(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        default -> "default";
    };
}
```

**Kiểm thử đúng hợp đồng nếu hiện tại muốn null phải bị từ chối:**

```java
npe("default-null", () -> defaultDoesNotCatchNull(null));
```

Và cần đối chứng giá trị không phải String, không phải null:

```java
equal("default-object", "default", defaultDoesNotCatchNull(42));
```

Nếu chỉ kiểm tra ca thứ hai, test chưa hề chứng minh rằng `default` không bắt `null`.

### Không nuốt ngoại lệ trong test

Một anti-pattern:

```java
// SAI: chỉ gọi hàm rồi catch chung không assert gì cả.
try {
    defaultDoesNotCatchNull(null);
} catch (Exception ignored) {
    // Không biết loại exception, vẫn coi như test xong.
}
```

Trong `npe(...)` của chương trình, nếu không có NPE, code **ném AssertionError**. Nếu hàm ném ngoại lệ khác, ngoại lệ đó không bị bắt thành PASS. Chỉ khi đúng `NullPointerException` mới tăng biến đếm `passed`.

Khi dùng JUnit 5, biểu đạt tương đương bằng `assertThrows(NullPointerException.class, () -> method(null))`; cách viết JUnit sẽ được minh họa ở phần sau.

## 7. Enum: exhaustive không tự xử lý null

Giả sử:

```java
enum Stage { NEW, DONE }
```

Một switch expression **đã liệt kê đủ enum constants** có thể biên dịch dù không có `case null`:

```java
static String stageWithoutNull(Stage stage) {
    return switch (stage) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

Nhưng gọi `stageWithoutNull(null)` vẫn ném `NullPointerException`. Điều này được xác nhận bởi ca `enum-without-null` trong ví dụ.

Nếu hợp đồng cho phép `null`:

```java
static String stage(Stage stage) {
    return switch (stage) {
        case null -> "stage:null";
        case NEW -> "stage:new";
        case DONE -> "stage:done";
    };
}
```

Cần kiểm thử **hai tính chất độc lập**: `stage(null)` trả `"stage:null"` và `stage(Stage.DONE)` vẫn trả `"stage:done"`.

Không nên thêm `default` chỉ để “tránh NPE”: nó không xử lý `null` theo cách nghĩ thông thường và có thể che mất cảnh báo khi enum được mở rộng bằng hằng mới. Nếu chính sách là cấm `null`, giữ NPE (hoặc dùng kiểm tra đầu vào rõ ràng); nếu chính sách cho phép, viết `case null`.

## 8. Sealed hierarchy: null selector khác null component

Một sealed interface với hai record:

```java
sealed interface Notice permits Created, Cancelled {}
record Created(String code) implements Notice {}
record Cancelled(String reason) implements Notice {}
```

Có thể viết switch expression exhaustive với hai kiểu con:

```java
static String noticeStatus(Notice notice) {
    return switch (notice) {
        case null -> "notice:null";
        case Created(var code) when code != null && !code.isBlank() ->
                "created:" + code;
        case Created(var code) -> "created:missing";
        case Cancelled(var reason) -> "cancelled:" + reason;
    };
}
```

Các ca cần có:
- `noticeStatus(null)` trả `"notice:null"`: selector null.
- `noticeStatus(new Created("AB"))` trả `"created:AB"`: guard thành công.
- `noticeStatus(new Created(""))` trả `"created:missing"`: guard thất bại vì rỗng.
- `noticeStatus(new Created(null))` trả `"created:missing"`: component null nhưng record tồn tại.
- `noticeStatus(new Cancelled("duplicate"))` trả `"cancelled:duplicate"`: kiểu con khác vẫn hoạt động.

Với hierarchy `sealed`, việc liệt kê các kiểu con đảm bảo bao phủ các instance hợp lệ theo cấu trúc kiểu. `case null` bổ sung chính sách cho giá trị vắng mặt, **không thay thế bất kỳ case kiểu con nào**.

## 9. Record patterns lồng nhau: hai tầng null cần hai bài test

Cấu trúc:

```java
record Order(String id, Notice notice) {}
```

và switch:

```java
static String nested(Object candidate) {
    return switch (candidate) {
        case null -> "order:null";
        case Order(var orderId, Created(var code)) ->
                "order-created:" + orderId + ":" + code;
        case Order(var orderId, var notice) ->
                "order-other:" + orderId + ":" +
                (notice == null ? "null" : notice.getClass().getSimpleName());
        default -> "not-order";
    };
}
```

Khác biệt quan trọng:

| Đầu vào | Kết quả | Lý do |
| --- | --- | --- |
| `null` | `"order:null"` | Selector null, chọn `case null` |
| `new Order("O2", null)` | `"order-other:O2:null"` | Selector là `Order`; mẫu `Created(...)` không khớp component null; mẫu `var notice` nhận null |
| `new Order("O1", new Created("AB"))` | `"order-created:O1:AB"` | Cả `Order` lẫn record con `Created` khớp |
| `new Order("O3", new Cancelled("x"))` | `"order-other:O3:Cancelled"` | Record con không phải `Created`, dùng case tổng quát của `Order` |

**Một nguyên tắc kiểm thử:** với record pattern lồng nhau, hãy phân biệt null ở **chính selector** với null ở **mỗi component quan trọng**. Không nên cho rằng đã có `case null` thì mọi accessor/chặng dữ liệu phía trong đều được xử lý.

Trong Java 21, `var` ở một component tham chiếu có thể ràng buộc giá trị `null`, còn một mẫu record lồng `Created(...)` không khớp với component null. Nếu accessor của record được viết riêng và tự ném ngoại lệ khi truy xuất, đó là một tình huống lỗi khác, không đơn thuần là null case. Khi accessor ném lỗi trong lúc matching, có thể xuất hiện `MatchException` với cause; phải test riêng theo hợp đồng accessor.

## 10. Switch statement: kiểm thử hành động, không chỉ giá trị

Không phải mọi switch đều trả về một giá trị. Với `switch statement`, có thể cần xác minh log, event, cập nhật trạng thái hoặc lời gọi service ở nhánh null.

Ví dụ chạy được trong `NullSwitchTests.java` dùng `StringBuilder` làm trạng thái có thể quan sát:

```java
static String statement(Object value) {
    StringBuilder result = new StringBuilder();
    switch (value) {
        case null -> result.append("statement:null");
        case String s -> result.append("statement:text:").append(s);
        default -> result.append("statement:other");
    }
    return result.toString();
}
```

Ba ca:
- `statement(null)`: `"statement:null"`.
- `statement("hi")`: `"statement:text:hi"`.
- `statement(7)`: `"statement:other"`.

Dù phương thức mẫu trả một chuỗi giúp test thuận tiện, bản thân cấu trúc bên trong vẫn là **switch statement**. Trong ứng dụng thật, thay `StringBuilder` bằng event sink, mock service hoặc state được quan sát sau thực thi.

Một test tốt cho side effect phải đảm bảo:
1. Khi selector `null`, đúng hành động của case null được thực hiện.
2. Không có hành động thuộc nhánh khác chạy ngoài dự kiến.
3. Khi giá trị không null, hành động cũ được giữ nguyên.
4. Nếu nhánh null phải dừng sớm, không có bước tiếp theo được thực hiện.

**Enhanced switch statement** dùng pattern trong Java 21 có quy tắc exhaustiveness; không nên nhầm với statement truyền thống trên `int` hoặc `String` dùng case hằng có thể không bao phủ hết.

## 11. Kiểm thử `case null, default`: tiện nhưng cần đúng ý nghĩa

Bộ test dùng:

```java
static String combinedFallback(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null, default -> "fallback";
    };
}
```

Ba assertion bảo vệ ý nghĩa:

```java
equal("combined-null", "fallback", combinedFallback(null));
equal("combined-object", "fallback", combinedFallback(42));
equal("combined-string", "text:hello", combinedFallback("hello"));
```

Nếu thay `case null, default` bằng `default`, test **combined-null** thất bại (NPE). Nếu thay bằng `case null` mà không giữ nhánh bao phủ giá trị khác kiểu, switch expression thiếu tính exhaustive với `Object`. Nếu vô tình đổi kết quả `String`, test **combined-string** phát hiện.

Chỉ dùng nhãn kết hợp khi null và giá trị không thuộc các case được liệt kê **thật sự tương đương trong nghiệp vụ**. Nếu null cần thông báo khác, đừng gộp chỉ để rút ngắn code. Tính đúng của chính sách quan trọng hơn ít dòng.

## 12. Phân biệt NPE trước switch và NPE do selector null

Có những trường hợp nhìn giống “lỗi null trong switch” nhưng `case null` không giúp được. Ví dụ:

```java
Object value = null;

String result = switch (value.toString()) {
    case null -> "null string";
    default -> "other";
};
```

Đây là **ví dụ cố ý ném `NullPointerException`**, không phải chương trình nên chạy trong luồng thông thường. Trình tự thực tế:

1. Java cần **đánh giá biểu thức selector `value.toString()`**.
2. Vì `value == null`, lời gọi `toString()` ném `NullPointerException` ngay.
3. Switch **chưa hề nhận được kết quả selector**, nên `case null` không có cơ hội được chọn.

Một chính sách đúng phải xử lý trước khi dereference:

```java
String result = switch (value) {
    case null -> "null object";
    default -> value.toString();
};
```

Đoạn thứ hai nhận `value` trực tiếp làm selector và xử lý `null` trước khi gọi phương thức. Đây là minh họa về **thời điểm lỗi**, không phải quy tắc tự động thay mọi lời gọi bằng switch.

Tương tự, khi code tự unbox một `Integer` đang bằng `null` để tạo một `int` trước switch, NPE có thể xảy ra trong bước unboxing. Với selector kiểu `Integer` trong Java 21, có thể kiểm tra `case null` trực tiếp mà không cần chủ động unbox trước đó.

## 13. Dùng JUnit 5 để bảo vệ hành vi trong dự án

Trong dự án có JUnit 5, không cần tự viết `equal` và `npe` như chương trình độc lập. Có thể viết test với `assertEquals`, `assertThrows` hoặc `assertAll`.

Ví dụ này **là đoạn lớp test minh họa, không phải file chạy độc lập không phụ thuộc gì**. Cần thêm JUnit 5 vào test classpath và truy cập được các phương thức/kiểu dưới lớp `NullSwitchTests`:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class NullSwitchJUnitTest {
    @Test
    void nullSelectorMustTakeNullCase() {
        assertEquals("selector:null", NullSwitchTests.classify(null));
    }

    @Test
    void defaultDoesNotConsumeNull() {
        assertThrows(NullPointerException.class,
                () -> NullSwitchTests.defaultDoesNotCatchNull(null));
    }

    @Test
    void nullComponentIsNotNullSelector() {
        assertEquals("order-other:O2:null",
                NullSwitchTests.nested(new NullSwitchTests.Order("O2", null)));
    }

    @Test
    void guardDistinguishesMissingCode() {
        assertAll(
                () -> assertEquals("notice:null",
                        NullSwitchTests.noticeStatus(null)),
                () -> assertEquals("created:missing",
                        NullSwitchTests.noticeStatus(new NullSwitchTests.Created(null))),
                () -> assertEquals("created:AB",
                        NullSwitchTests.noticeStatus(new NullSwitchTests.Created("AB")))
        );
    }
}
```

Với cấu trúc `NullSwitchTests.java` ở trên, các kiểu thành viên và phương thức có quyền truy cập package-private; lớp test cùng package (ở đây là default package) có thể gọi chúng. Trong dự án thực, đặt các lớp vào package hợp lệ hoặc điều chỉnh phạm vi hiển thị cho phù hợp, không tự đưa logic production sang public chỉ vì test.

### Tránh false positive khi test exception

Một anti-pattern:

```java
@Test
void weakTest() {
    try {
        NullSwitchTests.defaultDoesNotCatchNull(null);
    } catch (Exception ignored) {
        // Không kiểm chứng là NPE hay exception khác.
    }
}
```

Đoạn test như vậy có thể “xanh” dù không xảy ra lỗi, hoặc dù lỗi sai loại. `assertThrows(NullPointerException.class, ...)` yêu cầu rõ loại ngoại lệ; nếu phương thức trả bình thường hoặc ném exception khác, test thất bại.

Nếu hợp đồng đã đổi từ “ném NPE” sang “trả một giá trị null-specific”, cần **cập nhật test và lý do nghiệp vụ** thay vì chỉ xóa assertion khiến CI xanh mà không còn bảo vệ hành vi.

## 14. Cách đo mức bao phủ kiểm thử đúng hơn

Bộ 26 ca của chương trình minh họa là một tập trường hợp, **không phải bảo đảm mọi switch trong hệ thống đều được kiểm thử đủ**. Trong code production, nên áp dụng thêm:

1. **Branch coverage:** xác nhận từng nhánh cần thiết, gồm `case null`, guard true/false, `default` và các kiểu con, đều có bài test kích hoạt.
2. **Exception assertions:** nếu API cố ý từ chối null, khẳng định đúng NPE (hoặc exception đã định nghĩa), không chỉ nhìn thấy test có chạy.
3. **Mutation-oriented reasoning:** giả sử xóa `case null`; test nào bắt được thay đổi? Nếu không có test thất bại thì độ bảo vệ chưa đủ.
4. **Boundary and domain coverage:** `""`, `" "`, mã thành phần null, record con null, enum hằng mới, trường hợp sai kiểu.
5. **Side-effect verification:** với statement, khẳng định số lần gọi và dữ liệu gửi đến service, không chỉ nhìn return value.
6. **Parameterized tests:** gom các đầu vào tương đồng vào bảng khi có nhiều kiểu/giá trị, nhưng giữ ca null rõ ràng thay vì giấu ở một tập dữ liệu rất lớn.
7. **Regression after refactor:** khi đổi chuỗi `if` sang `switch` hoặc đổi `default`, chạy toàn bộ ca null và non-null để xác nhận hành vi trước/sau.
8. **Runtime/compiler compatibility:** chạy test bằng cùng mức ngôn ngữ ứng dụng deploy; cú pháp pattern switch và record patterns của ví dụ yêu cầu Java 21.

Đừng đo chất lượng chỉ bằng số test. Hai test có assertion chính xác cho `null`/non-null có giá trị hơn hàng chục test không quan sát được nhánh.

## 15. Những lỗi phổ biến khi kiểm thử null case

### 15.1. Cho rằng có `default` là đủ

Sai về semantics Java 21: `default` không tự xử lý selector null. Phải dùng `case null` hoặc chủ động mong đợi NPE.

### 15.2. Chỉ thử giá trị null, bỏ quên trường hợp khác

Thêm `case null` có thể vô tình đổi `case String` hoặc `default`. Luôn có đối chứng non-null để giữ đúng hành vi cũ.

### 15.3. Chỉ test null component rồi tuyên bố null selector đã an toàn

`new Order("O2", null)` là một **Order không null**. Nó không kiểm tra `case null` ở cùng switch.

### 15.4. Bắt chung `Exception` rồi cho test pass

Điều này che giấu lỗi sai loại và lỗi do các thao tác khác. Hãy assert đúng exception theo hợp đồng.

### 15.5. Nhầm guard với null case

Với `case String s when s.isBlank()`, selector null không vào guard đó. Test chuỗi rỗng và null phải tách biệt.

### 15.6. Dựa vào exhaustiveness mà không test null

Enum/sealed switch có thể exhaustive đối với các instance thuộc kiểu nhưng vẫn ném NPE với `null` nếu không có case tương ứng. Compiler không thay thế bài test hợp đồng null.

### 15.7. Không xét side effect của switch statement

Một test chỉ gọi `void process(null)` mà không assert log, event hoặc trạng thái có thể xanh kể cả khi nhánh sai chạy. Dùng mock/spy hoặc một sink có thể quan sát.

### 15.8. Đánh đồng exception ở selector với exception trong matching

`switch (obj.toString())` khi `obj == null` ném lỗi trước khi khối switch chọn case. `case null` không có cơ hội xử lý; muốn test và sửa đúng thì phải phân tích vị trí dereference.

### 15.9. Bỏ qua null của trường hợp sealed/record con

`new Created(null)` vẫn là `Created`. Nếu guard dùng `code.isBlank()` mà không kiểm tra `code != null`, có thể ném NPE. Test `Created(null)` và `notice == null` là hai ca khác nhau.

### 15.10. Sử dụng `List.of(null)` để tạo fixture mà không chú ý lỗi trước switch

`List.of(...)` không chấp nhận phần tử null, nên `List.of((Object) null)` ném NPE khi tạo list, trước khi phương thức đang kiểm thử được gọi. Muốn kiểm thử selector null, hãy truyền trực tiếp `null` vào phương thức hoặc dùng fixture cho phép null và có mục đích rõ.

### 15.11. Chỉ nhìn stdout mà không có assertion

In ra `"OK"` không chứng minh case được chọn đúng nếu test không so với expected value. Chương trình minh họa sử dụng `AssertionError`; trong dự án thật nên dùng framework test.

## 16. Bài tập tự luyện và đáp án

**Bài 1 — Default và null.** Có:

```java
String result = switch (value) {
    case String s -> "text";
    default -> "other";
};
```

Với `Object value = null`, trả `"other"` hay ném lỗi?

**Đáp án:** ném `NullPointerException`. `default` không tự bắt selector null.

**Bài 2 — Exhaustive enum.** `enum Stage { NEW, DONE }` đã có `case NEW` và `case DONE`. Nếu không có `case null` thì `stageWithoutNull(null)` thế nào?

**Đáp án:** switch expression vẫn có thể biên dịch vì đủ các giá trị enum; gọi với null vẫn ném NPE.

**Bài 3 — Hai tầng null.** `nested(null)` và `nested(new Order("O2", null))` có cùng kết quả không?

**Đáp án:** không. Trường hợp đầu trả `order:null`; trường hợp sau trả `order-other:O2:null` theo ví dụ. Selector và record component là hai vị trí khác nhau.

**Bài 4 — Guard của Created.** `noticeStatus(new Created(null))` có vào `case null` không?

**Đáp án:** không. Selector là một đối tượng `Created`. Guard của case có điều kiện trả false, nhánh `Created` không guard xử lý bằng `created:missing`.

**Bài 5 — Gộp nhánh.** Khi nào `case null, default -> "fallback"` phù hợp?

**Đáp án:** chỉ khi hợp đồng nghiệp vụ thật sự xem null và các giá trị còn lại không khớp như cùng một loại fallback. Nếu muốn trả `missing` cho null và `unsupported` cho kiểu khác, tách nhánh.

**Bài 6 — Assert NPE.** Tại sao phải dùng `assertThrows` thay cho `try/catch (Exception ignored)` trong unit test?

**Đáp án:** `assertThrows` kiểm tra rằng exception **phải xảy ra và đúng loại**. Catch bỏ qua khiến test có thể xanh ngay cả khi hàm không ném lỗi hoặc ném loại lỗi ngoài mong đợi.

**Bài 7 — Null trước switch.** `switch (value.toString())` với `value == null`, thêm `case null` có khắc phục không?

**Đáp án:** không. `value.toString()` ném NPE trước khi switch nhận selector. Cần kiểm tra null trước khi dereference hoặc dùng trực tiếp `switch (value)` với `case null`.

**Bài 8 — Kiểm thử regression.** Khi thêm `case null` vào switch statement có side effect, nên test gì ngoài output cho null?

**Đáp án:** hành động của nhánh null, xác nhận không chạy nhánh khác, side effects và thứ tự quan trọng, cùng ít nhất các giá trị non-null vốn được hỗ trợ.

**Bài 9 — Mẫu Object.** Với `switch(Object value) { case Object any -> "object"; }`, tại sao vẫn phải test `value == null`?

**Đáp án:** mẫu `Object` có thể là mẫu bao phủ mọi instance không null nhưng không khớp null. Trường hợp null vẫn ném NPE.

**Bài 10 — Đo hiệu quả test.** Nếu xóa `case null` khỏi `classify`, test nào trong `NullSwitchTests` thất bại?

**Đáp án:** test `selector-null`: thay vì trả `"selector:null"`, lời gọi sẽ ném NPE. Đây là một kiểm tra dễ hiểu về độ nhạy của bộ test với lỗi null.

## 17. Ghi nhớ và checklist ngắn

- Trước khi viết test, quyết định rõ **hợp đồng của selector null**: có nhánh riêng, gộp fallback hay từ chối bằng exception.
- **`case null`** là cách xử lý null của selector trong switch trên kiểu tham chiếu; **`default`** không mặc nhiên thay thế.
- **Exhaustiveness không tự đồng nghĩa null safety**; enum, sealed hierarchy hoặc mẫu `Object` vẫn cần xét selector null.
- **`case null, default`** hợp lệ nhưng chỉ nên dùng khi hai tình huống thật sự có cùng ý nghĩa.
- **Record component null khác selector null**; với nested record pattern, cần thêm ca kiểm thử cho từng tầng dữ liệu quan trọng.
- **Guard `when`** không phải nhánh null. Test guard đúng, guard sai và null tách biệt.
- Với **switch expression**, assert giá trị hoặc exception; với **switch statement**, assert hành vi/side effects.
- **NPE trước khi chọn case** (dereference hoặc unboxing ở selector) không được `case null` bắt.
- Một bộ kiểm thử tốt có cả **positive, negative, boundary và regression cases**, không chỉ chạy một lần rồi nhìn output.
- Chạy kiểm thử với Java 21+ để đúng semantics của pattern matching for switch và record patterns trong bài.

**Tài liệu chính thức:**
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [Java Language Specification 21 — The switch Statement (`14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — Switch Expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
