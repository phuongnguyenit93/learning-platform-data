# Bổ sung `case null` đúng chủ đích: thực hành tổng hợp Java Pattern Matching (Java 21+)

## 1. Bài toán: bổ sung null case không chỉ là sửa một lỗi NPE

Khi chuyển code từ chuỗi `if/else` và ép kiểu sang **pattern matching trong `switch`**, một thay đổi tưởng nhỏ có thể làm sai hợp đồng xử lý `null`:

~~~java
static String label(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Với `label("abc")`, phương thức trả `"text:abc"`. Với `label(42)`, nó trả `"other"`. **Với `label(null)`, pattern switch Java 21 ném `NullPointerException`**, chứ không tự đi vào `default`.

Có thể sửa bằng:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Nhưng câu hỏi quan trọng hơn là: **`"missing"` có thật sự là kết quả nghiệp vụ đúng không?** Nếu `null` biểu thị một giá trị bị thiếu mà API cho phép, `case null` là lựa chọn hợp lý. Nếu `null` là lỗi lập trình vì contract yêu cầu một command bắt buộc, **không nên biến nó thành kết quả hợp lệ một cách âm thầm**.

Bài thực hành tổng hợp này giúp bạn quyết định:

- Khi nào nên dùng `case null` để biểu diễn một nhánh nghiệp vụ.
- Khi nào nên chủ động từ chối đầu vào bằng `Objects.requireNonNull`.
- Khi nào cần validation trả lỗi dữ liệu có cấu trúc thay vì ném exception tình cờ.
- Vì sao `default`, `when` và record pattern không tự đảm nhiệm việc xử lý `null` ở mọi vị trí.
- Cách xử lý `null` ở **selector bên ngoài**, **record lồng nhau** và **component bên trong record**.
- Cách giữ tính **exhaustive** khi `switch` xử lý một `sealed interface`.
- Cách chứng minh thay đổi là có chủ đích bằng **kiểm thử tình huống dương và âm**, không chỉ bằng một dòng code.

Ví dụ chính dùng **JDK 21+** vì record pattern và pattern `switch` là tính năng ổn định từ Java 21. Không cần `--enable-preview`.

## 2. Ba ý nghĩa nghiệp vụ khác nhau của null

Một giá trị `null` là trạng thái ở mức Java, nhưng **ý nghĩa của nó phải do hợp đồng ứng dụng quyết định**. Cùng `null` ở hai API khác nhau có thể cần hành vi khác nhau.

| Ngữ cảnh | Ý nghĩa `null` | Chính sách phù hợp | Ví dụ |
| --- | --- | --- | --- |
| Bộ phân loại đầu vào từ hệ thống ngoài | Chưa có request hoặc payload vắng mặt | Trả kết quả `INVALID` hoặc nhãn “thiếu” | `case null -> invalid("missing-command")` |
| API nội bộ yêu cầu command bắt buộc | Người gọi vi phạm contract | Từ chối sớm, nêu rõ tên tham số | `Objects.requireNonNull(command, "command")` |
| Dữ liệu có thể vắng mặt theo nghiệp vụ | “Chưa xác định”, “chưa nhập”, “chưa có” là trạng thái hợp lệ | `case null` với kết quả domain rõ nghĩa | `case null -> "not-selected"` |
| Field trong record có thể null | Payload thiếu component, không nhất thiết selector thiếu | Constructor/factory validation hoặc guard trong case | `name != null && !name.isBlank()` |
| Record lồng nhau bằng null | Thiếu đối tượng con | Nhánh fallback cho object bao ngoài hoặc lỗi dữ liệu | `case Envelope(var customer, var memo)` |

**Quy tắc quyết định:** trước khi thêm một nhánh null, hãy hỏi **ai chịu trách nhiệm sửa giá trị null** và **null có được hợp đồng cho phép hay không**.

- Nếu người gọi được phép không cung cấp một giá trị, ánh xạ null sang một kết quả domain có thể đúng.
- Nếu người gọi bắt buộc cung cấp một object, việc từ chối sớm giúp phát hiện bug nhanh hơn.
- Nếu dữ liệu đến từ JSON, message queue hay DTO chưa xác thực, cần phân biệt **thiếu field**, **field là null** và **field có nội dung không hợp lệ** theo contract API. `case null` trên object đã parse không tự phân biệt được các trường hợp ấy.

Đừng thêm `case null -> defaultValue` chỉ để làm cho test hết ném exception, nếu default ấy che một lỗi dữ liệu quan trọng.

## 3. Ngữ nghĩa Java 21 cần nắm vững

### 3.1. `instanceof` với selector null

~~~java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not a string");
}
~~~

Kết quả:

~~~text
not a string
~~~

`instanceof` trực tiếp trả `false` khi selector bằng null. Thân `if` không chạy, nên biến pattern `text` không bị dereference.

Điều này **không có nghĩa** mọi `String` được khai báo bằng pattern đều non-null ở mọi vị trí: record component pattern có quy tắc riêng (mục 7).

### 3.2. Pattern `switch` không tự chuyển null sang `default`

~~~java
static String defaultIsNotNull(Object value) {
    return switch (value) {
        case String text -> "string:" + text;
        default -> "other";
    };
}
~~~

Với `defaultIsNotNull(null)`, chương trình ném `NullPointerException` trên Java 21. `default` xử lý các **giá trị không null** không khớp những pattern đã khai báo; nó không thay cho quyết định xử lý null.

Nếu null là trường hợp hợp lệ, viết `case null`. Nếu null là lỗi gọi API, từ chối tường minh trước switch; nếu null là payload sai, có thể biến nó thành kết quả validation.

### 3.3. `when` không thay cho `case null`

~~~java
return switch (value) {
    case String text when text.length() > 3 -> "long text";
    case String text -> "short text";
    case null -> "missing";
    default -> "other";
};
~~~

Đây là **một đoạn biểu thức minh họa** cần đặt trong phương thức trả về `String` có biến `value` thích hợp. Type pattern trực tiếp `case String text` chỉ khớp khi selector có giá trị `String` khác null. Guard `when` được đánh giá **sau khi pattern khớp**.

Viết `case String text when text == null` không phải cách “bắt null selector”: pattern `String` bên ngoài không khớp null, nên guard đó không được gọi cho selector null. Một nhánh `case null` riêng mới diễn đạt đúng ý định.

### 3.4. Exhaustive về subtype không đồng nghĩa quyết định được null policy

Một `sealed interface` giúp compiler kiểm tra đã bao phủ đủ subtype được phép trong `switch expression`. Nhưng **null không phải một subtype**. Tùy hợp đồng, vẫn cần:

- `case null` khi muốn trả kết quả cho selector null; hoặc
- từ chối null tường minh, ví dụ `Objects.requireNonNull`.

Đừng bổ sung `default` chỉ để “cho đủ case” nếu tập subtype đã đóng và bạn muốn compiler cảnh báo khi thêm subtype mới.

## 4. Tình huống thực hành: xử lý command đơn hàng

Ta định nghĩa ba command thuộc tập đóng:

~~~java
sealed interface Command permits Create, Ship, Cancel {}

record Create(String id, int units) implements Command {}
record Ship(String id, String tracking) implements Command {}
record Cancel(String id, String reason) implements Command {}
~~~

Với mỗi command, hệ thống cần đưa ra kết quả có kiểu:

~~~java
enum Code { OK, INVALID }
record Result(Code code, String detail) {}
~~~

Các quy tắc dữ liệu của ví dụ:

- `Create` yêu cầu `id` không null/không trắng và `units > 0`.
- `Ship` yêu cầu `id` và `tracking` không null/không trắng.
- `Cancel` yêu cầu `id` và `reason` không null/không trắng.
- `Command` selector null trong **đường tiếp nhận có thể vắng mặt** được xem là payload thiếu, trả `INVALID:missing-command`.
- `Command` selector null trong **API nội bộ bắt buộc** được xem là lỗi gọi API, ném `NullPointerException` có chủ đích.

**Chú ý:** ba record ở đây **cố ý không có constructor validation** để mô phỏng dữ liệu lệnh chưa được xác thực. Vì vậy `new Create(null, -1)` vẫn có thể được tạo theo Java, nhưng handler sẽ trả lỗi validation. Một hệ thống thật có thể validate ngay tại constructor/factory hoặc ở boundary; điều quan trọng là xác định rõ điểm kiểm tra.

Để không nhân bản nghiệp vụ, cả hai chính sách null sẽ dùng **cùng ba handler**:

~~~java
static boolean blank(String value) {
    return value == null || value.isBlank();
}

static Result onCreate(Create c) {
    if (blank(c.id())) return invalid("create-id");
    if (c.units() <= 0) return invalid("units");
    return ok("created:" + c.id() + ":" + c.units());
}

static Result onShip(Ship s) {
    if (blank(s.id())) return invalid("ship-id");
    if (blank(s.tracking())) return invalid("tracking");
    return ok("shipped:" + s.id() + ":" + s.tracking());
}

static Result onCancel(Cancel c) {
    if (blank(c.id())) return invalid("cancel-id");
    if (blank(c.reason())) return invalid("reason");
    return ok("cancelled:" + c.id());
}
~~~

Đây là **các phương thức minh họa**. `ok` và `invalid` trả về record `Result` trong chương trình hoàn chỉnh ở mục 9. `blank` dùng toán tử `||` ngắn mạch nên không gọi `isBlank()` khi `value == null`.

Các handler này không tự xử lý selector command null: chúng được gọi **sau khi dispatcher đã xác định loại command**. Chính sách null thuộc về **ranh giới điều phối**, không nên nằm rải rác trong từng handler không cần thiết.

## 5. Chính sách A: null là một kết quả dữ liệu cần xử lý

Đối với hàm nhận command từ một nguồn cho phép payload vắng mặt:

~~~java
static Result handleNullable(Command command) {
    return switch (command) {
        case null -> invalid("missing-command");
        case Create c -> onCreate(c);
        case Ship s -> onShip(s);
        case Cancel c -> onCancel(c);
    };
}
~~~

Cách đọc:

1. `case null` diễn đạt rõ quyết định nghiệp vụ: command không được cung cấp sẽ được **phân loại là dữ liệu thiếu**.
2. Ba type pattern tiếp theo phân tuyến đến handler của từng record.
3. Không cần `default` vì `Command` là sealed với ba subtype record final; compiler có thể xác minh nhánh cho các subtype không null là đầy đủ.
4. Cùng một `Create`, `Ship` hoặc `Cancel` sẽ có kết quả validation như khi đi qua API strict ở phần tiếp theo, vì cùng gọi ba handler.

Ưu điểm: hàm có kết quả **typed** `Result`, không dùng NPE ngoài ý muốn làm phương thức trả lỗi dữ liệu. Người gọi có thể chuyển `INVALID` thành HTTP response, CLI message hoặc một trạng thái nghiệp vụ mà không phải bắt exception để phân loại.

Hạn chế: null đã được hiểu là một **input nghiệp vụ được dự kiến**, nên caller có thể không phát hiện bug nếu nó đáng ra bắt buộc truyền command. Vì thế tên phương thức `handleNullable` và tài liệu API phải nêu rõ hợp đồng, không suy đoán rằng mọi nơi đều nên dùng chính sách này.

Một comment tốt gần nhánh null:

~~~java
// Boundary nhận request thiếu: trả lỗi validation có cấu trúc.
// Không áp dụng chính sách này cho API nội bộ yêu cầu command bắt buộc.
case null -> invalid("missing-command");
~~~

Comment tập trung vào **lý do** chọn nhánh thay vì chỉ lặp lại cú pháp “xử lý null”.

## 6. Chính sách B: null là lỗi vi phạm hợp đồng API

Đối với hàm nội bộ chỉ cho phép command có kiểu `Command` khác null:

~~~java
static Result handleRequired(Command command) {
    java.util.Objects.requireNonNull(command, "command");

    return switch (command) {
        case Create c -> onCreate(c);
        case Ship s -> onShip(s);
        case Cancel c -> onCancel(c);
    };
}
~~~

`Objects.requireNonNull(command, "command")` ném `NullPointerException` sớm với tên tham số dễ chẩn đoán nếu có người gọi sai. Đây không phải “quên xử lý null”; đó là **quyết định từ chối null tường minh**.

So sánh hai lời gọi:

~~~java
handleNullable(null); // Result(INVALID, "missing-command")
handleRequired(null); // NullPointerException: command
~~~

Đây là các lời gọi minh họa. Nếu `null` thực sự là request thiếu hợp lệ theo protocol, dùng `handleNullable`. Nếu `null` vi phạm tiền điều kiện của hàm nội bộ, dùng `handleRequired`.

**Không nên dùng một cơ chế `null -> ok("empty")` chung cho cả hai.** Nó biến bug ở caller thành trạng thái thành công giả và có thể khiến downstream tưởng đã xử lý command.

### Có nên ném `IllegalArgumentException` thay vì NPE?

Có thể nếu API đã có quy ước từ chối các tham số không hợp lệ bằng `IllegalArgumentException`. Java không bắt buộc mọi phương thức phải chọn `Objects.requireNonNull`; điều cốt lõi là **document một contract nhất quán** và có test cho trường hợp null.

`Objects.requireNonNull` phù hợp với tham chiếu bắt buộc, còn validation của payload như `units <= 0` thường là lỗi domain khác. Việc phân biệt hai tầng giúp log và xử lý lỗi chính xác hơn.

## 7. Null bên trong record khác null selector ngoài cùng

Một sai lầm dễ gặp là bổ sung `case null` ở đầu `switch` rồi tin rằng mọi null lồng trong object đã được xử lý.

Ví dụ dữ liệu đầu vào:

~~~java
record Customer(String name) {}
record Envelope(Customer customer, String memo) {}
~~~

Các trường hợp:

~~~java
Object a = null;
Object b = new Envelope(null, "note");
Object c = new Envelope(new Customer(null), "note");
Object d = new Envelope(new Customer("Lan"), null);
~~~

Bốn trường hợp này **không giống nhau**:

- `a`: selector ngoài cùng là null.
- `b`: selector tồn tại và là một `Envelope`, nhưng component `customer` bằng null.
- `c`: `customer` tồn tại, nhưng `Customer.name` bằng null.
- `d`: `customer.name` hợp lệ, nhưng component `memo` của `Envelope` bằng null.

Một `case null` trên selector chỉ áp dụng cho `a`. Nó không thay validation bên trong record.

### Dùng record pattern có nhánh dự phòng theo từng tầng

~~~java
static String inspect(Object raw) {
    return switch (raw) {
        case null -> "missing-selector";

        case Envelope(Customer(var name), var memo)
                when name != null && !name.isBlank()
                  && memo != null && !memo.isBlank() ->
                "ready:" + name + ":" + memo;

        case Envelope(Customer(var name), var memo) ->
                "invalid-fields";

        case Envelope(var customer, var memo) ->
                "missing-customer";

        case String text when !text.isBlank() ->
                "text:" + text;

        case String text -> "blank-text";
        default -> "other-type";
    };
}
~~~

Đây là một phương thức Java 21 hoàn chỉnh **trong phạm vi khai báo có `Customer` và `Envelope`**. Bản runnable chứa mọi type ở mục 9.

Xét đường thực thi:

| Input | Nhánh được chọn | Lý do |
| --- | --- | --- |
| `null` | `case null` | Selector ngoài cùng vắng mặt |
| `Envelope(Customer("Lan"), "note")` | Guarded record case | Cả tên và memo có nội dung |
| `Envelope(null, "note")` | `Envelope(var customer, var memo)` | Mẫu lồng `Customer(...)` không khớp null |
| `Envelope(Customer(null), "note")` | `invalid-fields` | Customer tồn tại; tên null làm guard sai |
| `Envelope(Customer("Lan"), null)` | `invalid-fields` | Memo null làm guard sai |
| `"hello"` | `case String text when ...` | Type pattern trực tiếp khớp String |
| `"  "` | `case String text` không guard | Guard kiểm tra không trắng trả false |
| `42` | `default` | Kiểu không được xử lý riêng, nhưng không null |

**Cần nhớ thứ tự case:** guarded case thường đứng trước case cùng kiểu rộng hơn. Nếu `Envelope(var customer, var memo)` được đặt lên trước các case `Envelope(...)` cụ thể, chúng có thể bị compiler báo *dominated* hoặc không còn được lựa chọn theo cách mong muốn.

### Vì sao `when` cần null guard?

Trong `Envelope(Customer(var name), var memo)`, `var name` và `var memo` chỉ suy ra kiểu tĩnh của component; chúng **có thể giữ giá trị null**. Do đó:

~~~java
name != null && !name.isBlank()
    && memo != null && !memo.isBlank()
~~~

được đánh giá từ trái sang phải. Khi `name` hoặc `memo` null, lời gọi `isBlank()` tương ứng không được thực hiện, tránh NPE.

Nếu đặt `name.isBlank()` trước `name != null` thì guard có thể ném NPE ngay trong quá trình chọn case.

## 8. Trường hợp tinh tế: type pattern trên component có thể khớp null

Không nên đơn giản hóa rằng “cứ thấy `String x` trong pattern thì chắc chắn khác null”. Hãy phân biệt hai record:

~~~java
record TypedMessage(String body) {}
record BroadMessage(Object body) {}
~~~

Trong Java 21:

~~~java
Object typed = new TypedMessage(null);

boolean matchesTyped =
        typed instanceof TypedMessage(String body)
        && body == null;

System.out.println(matchesTyped); // true
~~~

Ở đây component của `TypedMessage` đã được khai báo kiểu tĩnh `String`, nên mẫu con `String body` là một **unconditional pattern** đối với kiểu component ấy. Nó có thể khớp cả component null.

Trong khi đó:

~~~java
Object broad = new BroadMessage(null);

boolean matchesBroad =
        broad instanceof BroadMessage(String body);

System.out.println(matchesBroad); // false
~~~

Component của `BroadMessage` được khai báo kiểu `Object`. Mẫu con `String body` là **conditional type pattern**, chỉ khớp khi component mang một chuỗi thực tế khác null.

**So sánh chính xác:**

| Phép khớp | Input null | Kết quả |
| --- | --- | --- |
| `Object x = null; x instanceof String s` | Selector ngoài cùng null | `false` |
| `TypedMessage(String body)` | Component có kiểu tĩnh `String` nhưng giá trị null | Có thể khớp, `body == null` |
| `TypedMessage(var body)` | Component `String` null | Có thể khớp, `body == null` |
| `BroadMessage(String body)` | Component có kiểu tĩnh `Object` và giá trị null | `false` |
| `Envelope(Customer(var name), ...)` | Component `customer` là null | Mẫu record lồng `Customer(...)` không khớp |

**Hệ quả thực tế:** nếu bạn gọi `body.length()` trong một nhánh record pattern, hãy kiểm tra có **invariant domain** được constructor/factory bảo vệ hay chưa. Đừng kết luận component non-null chỉ vì pattern viết `String body` hoặc `var body`.

## 9. Chương trình Java 21 hoàn chỉnh — 31 ca kiểm thử

Tạo tệp **`IntentionalNullCasesDemo.java`** với toàn bộ nội dung dưới đây. Chương trình mô phỏng hai policy null cho command, null ở ba tầng record, null trong type pattern và phản ví dụ `default` không bắt null.

~~~java
public class IntentionalNullCasesDemo {
    sealed interface Command permits Create, Ship, Cancel {}
    record Create(String id, int units) implements Command {}
    record Ship(String id, String tracking) implements Command {}
    record Cancel(String id, String reason) implements Command {}

    enum Code { OK, INVALID }
    record Result(Code code, String detail) {}
    record Customer(String name) {}
    record Envelope(Customer customer, String memo) {}
    record TypedMessage(String body) {}
    record BroadMessage(Object body) {}

    static Result ok(String text) {
        return new Result(Code.OK, text);
    }

    static Result invalid(String field) {
        return new Result(Code.INVALID, field);
    }

    static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    static Result onCreate(Create c) {
        if (blank(c.id())) return invalid("create-id");
        if (c.units() <= 0) return invalid("units");
        return ok("created:" + c.id() + ":" + c.units());
    }

    static Result onShip(Ship s) {
        if (blank(s.id())) return invalid("ship-id");
        if (blank(s.tracking())) return invalid("tracking");
        return ok("shipped:" + s.id() + ":" + s.tracking());
    }

    static Result onCancel(Cancel c) {
        if (blank(c.id())) return invalid("cancel-id");
        if (blank(c.reason())) return invalid("reason");
        return ok("cancelled:" + c.id());
    }

    static Result handleNullable(Command command) {
        return switch (command) {
            case null -> invalid("missing-command");
            case Create c -> onCreate(c);
            case Ship s -> onShip(s);
            case Cancel c -> onCancel(c);
        };
    }

    static Result handleRequired(Command command) {
        java.util.Objects.requireNonNull(command, "command");
        return switch (command) {
            case Create c -> onCreate(c);
            case Ship s -> onShip(s);
            case Cancel c -> onCancel(c);
        };
    }

    static String inspect(Object raw) {
        return switch (raw) {
            case null -> "missing-selector";

            case Envelope(Customer(var name), var memo)
                    when name != null && !name.isBlank()
                      && memo != null && !memo.isBlank() ->
                    "ready:" + name + ":" + memo;

            case Envelope(Customer(var name), var memo) ->
                    "invalid-fields";

            case Envelope(var customer, var memo) ->
                    "missing-customer";

            case String text when !text.isBlank() ->
                    "text:" + text;

            case String text -> "blank-text";
            default -> "other-type";
        };
    }

    static String defaultIsNotNull(Object value) {
        return switch (value) {
            case String text -> "string:" + text;
            default -> "other";
        };
    }

    private static int passed = 0;

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        ++passed;
        System.out.println("PASS " + label);
    }

    static void verify(String label, Command command, Result expected) {
        Result nullable = handleNullable(command);
        boolean ok = nullable.equals(expected);
        if (command != null) {
            ok &= handleRequired(command).equals(expected);
        }
        check(label, ok);
    }

    static void checkInspect(
            String label, Object input, String expected) {
        check(label, inspect(input).equals(expected));
    }

    static void expectNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NPE: " + label);
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        verify("create-ok",
                new Create("O1", 3), ok("created:O1:3"));
        verify("create-null-id",
                new Create(null, 3), invalid("create-id"));
        verify("create-blank-id",
                new Create("  ", 3), invalid("create-id"));
        verify("create-zero",
                new Create("O1", 0), invalid("units"));
        verify("create-negative",
                new Create("O1", -1), invalid("units"));

        verify("ship-ok",
                new Ship("O1", "TR-7"),
                ok("shipped:O1:TR-7"));
        verify("ship-null-id",
                new Ship(null, "TR-7"), invalid("ship-id"));
        verify("ship-blank-id",
                new Ship(" ", "TR-7"), invalid("ship-id"));
        verify("ship-null-tracking",
                new Ship("O1", null), invalid("tracking"));
        verify("ship-blank-tracking",
                new Ship("O1", " "), invalid("tracking"));

        verify("cancel-ok",
                new Cancel("O1", "changed"),
                ok("cancelled:O1"));
        verify("cancel-null-id",
                new Cancel(null, "changed"), invalid("cancel-id"));
        verify("cancel-blank-reason",
                new Cancel("O1", " "), invalid("reason"));
        verify("cancel-null-reason",
                new Cancel("O1", null), invalid("reason"));
        verify("null-command",
                null, invalid("missing-command"));

        checkInspect("envelope-ready",
                new Envelope(new Customer("Lan"), "note"),
                "ready:Lan:note");
        checkInspect("envelope-null-customer",
                new Envelope(null, "note"),
                "missing-customer");
        checkInspect("envelope-null-name",
                new Envelope(new Customer(null), "note"),
                "invalid-fields");
        checkInspect("envelope-blank-name",
                new Envelope(new Customer("  "), "note"),
                "invalid-fields");
        checkInspect("envelope-null-memo",
                new Envelope(new Customer("Lan"), null),
                "invalid-fields");
        checkInspect("envelope-blank-memo",
                new Envelope(new Customer("Lan"), ""),
                "invalid-fields");
        checkInspect("envelope-valid-other",
                new Envelope(new Customer("Minh"), "ok"),
                "ready:Minh:ok");
        checkInspect("top-level-null",
                null, "missing-selector");
        checkInspect("string-normal",
                "hello", "text:hello");
        checkInspect("string-blank",
                "  ", "blank-text");
        checkInspect("other-type",
                42, "other-type");

        Object missing = null;
        check("instanceof-null-false",
                !(missing instanceof String s));

        Object typed = new TypedMessage(null);
        check("record-component-unconditional-null",
                typed instanceof TypedMessage(String body)
                        && body == null);

        Object broad = new BroadMessage(null);
        check("record-component-conditional-null",
                !(broad instanceof BroadMessage(String body)));

        expectNpe("required-rejects-null",
                () -> handleRequired(null));
        expectNpe("default-not-null",
                () -> defaultIsNotNull(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Biên dịch và chạy

Dùng **JDK 21 trở lên**:

~~~bash
javac --release 21 IntentionalNullCasesDemo.java
java IntentionalNullCasesDemo
~~~

**Output chính xác khi tất cả assertion đạt:**

~~~text
PASS create-ok
PASS create-null-id
PASS create-blank-id
PASS create-zero
PASS create-negative
PASS ship-ok
PASS ship-null-id
PASS ship-blank-id
PASS ship-null-tracking
PASS ship-blank-tracking
PASS cancel-ok
PASS cancel-null-id
PASS cancel-blank-reason
PASS cancel-null-reason
PASS null-command
PASS envelope-ready
PASS envelope-null-customer
PASS envelope-null-name
PASS envelope-blank-name
PASS envelope-null-memo
PASS envelope-blank-memo
PASS envelope-valid-other
PASS top-level-null
PASS string-normal
PASS string-blank
PASS other-type
PASS instanceof-null-false
PASS record-component-unconditional-null
PASS record-component-conditional-null
PASS required-rejects-null
PASS default-not-null
ALL PASSED: 31
~~~

### Hiểu đúng kết quả kiểm thử

**Nhóm command:**

- `create-ok`, `ship-ok`, `cancel-ok`: các command hợp lệ có kết quả `OK` như nhau ở cả hai API.
- Các ca `*-null-id`, `*-blank-*`, `create-zero` và `create-negative`: validation nội dung payload trả `INVALID` theo trường cụ thể. Với command khác null, test so sánh **`handleNullable` và `handleRequired`** để bảo đảm không vô tình sửa logic nghiệp vụ khi đổi chính sách null.
- `null-command`: chỉ gọi `handleNullable(null)` vì API này được thiết kế chấp nhận request vắng mặt và trả `INVALID:missing-command`.

**Nhóm record lồng:**

- `envelope-null-customer`: record `Envelope` vẫn tồn tại nhưng component `customer` null; nhánh record lồng không khớp, fallback `missing-customer` được chọn.
- `envelope-null-name` và `envelope-null-memo`: record lồng có thể khớp nhưng guard thất bại; nhánh `invalid-fields` xử lý.
- `top-level-null`: chỉ trường hợp selector ngoài cùng null mới đi vào `case null` của `inspect`.
- `string-normal`, `string-blank` và `other-type`: xác minh guard + fallback theo kiểu không che lẫn nhau.

**Nhóm kiểm chứng ngữ nghĩa Java:**

- `instanceof-null-false`: `instanceof` bên ngoài trả false với null.
- `record-component-unconditional-null`: `TypedMessage(String body)` có thể khớp component null.
- `record-component-conditional-null`: `BroadMessage(String body)` không khớp component null khi component tĩnh là `Object`.
- `required-rejects-null`: `Objects.requireNonNull` chủ động từ chối null ở API strict.
- `default-not-null`: pattern `switch` có `default` nhưng không có `case null` vẫn ném `NullPointerException`.

Hàm `check` ném `AssertionError` nếu điều kiện không đúng. Vì vậy `ALL PASSED: 31` chỉ xuất hiện sau khi toàn bộ đường xử lý đều cho kết quả dự kiến.

**Lưu ý phạm vi:** đây là bộ demo xử lý kết quả, **không thực thi thanh toán hay thay đổi đơn hàng thật**. Khi tích hợp hệ thống, cần tách validation, kiểm tra trạng thái và tác động I/O phù hợp.

## 10. Bài tập trước–sau: sửa một switch thiếu null mà không đổi contract

Giả sử code cũ:

~~~java
static String classify(Object input) {
    return switch (input) {
        case String text -> "text:" + text;
        case Integer count -> "number:" + count;
        default -> "unsupported";
    };
}
~~~

Đây là **một phương thức độc lập về cú pháp**, nhưng ví dụ chỉ minh họa logic nhỏ; không dùng trong chương trình chính ở mục 9.

Yêu cầu mới của API: khi request không có dữ liệu, trả `"missing"`. Một bản sửa hợp lý:

~~~java
static String classify(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text:" + text;
        case Integer count -> "number:" + count;
        default -> "unsupported";
    };
}
~~~

Những thay đổi cần được kiểm tra:

1. `classify(null)` bây giờ trả `"missing"` như hợp đồng mới.
2. `classify("hi")` vẫn trả `"text:hi"`.
3. `classify(3)` vẫn trả `"number:3"`.
4. `classify(3.5)` vẫn trả `"unsupported"`.
5. `default` vẫn chỉ làm nhiệm vụ xử lý các kiểu không hỗ trợ; **không bị dùng sai để biểu diễn request vắng mặt**.

Nếu contract lại quy định “`input` bắt buộc phải được cung cấp”, thì không nên sửa thành `"missing"`. Có thể giữ switch như cũ nhưng đặt `Objects.requireNonNull(input, "input")` ở đầu phương thức và test rằng null bị từ chối.

Đây là điểm khác nhau giữa **sửa hành vi theo yêu cầu** và **che ngoại lệ bằng giá trị mặc định**.

## 11. Một null case có thể ảnh hưởng thứ tự chọn nhánh và lỗi nghiệp vụ

Khi thêm `case null`, phải bảo đảm các nhánh đang có vẫn hoạt động như trước. Đặc biệt với `when`:

~~~java
// Phần switch expression minh họa:
case null -> "missing";
case String text when !text.isBlank() -> "text:" + text;
case String text -> "blank-text";
default -> "other";
~~~

- `case null` nhận selector null.
- Type pattern `String text` chỉ nhận chuỗi không null.
- Guard chỉ áp dụng khi pattern đã khớp.
- Nhánh `String text` không guard đứng sau nhận chuỗi trắng.
- `default` nhận kiểu không hỗ trợ.

Nếu đặt `case String text -> ...` tổng quát lên **trước** nhánh `String text when ...`, compiler có thể báo nhánh guarded phía sau bị *dominated*. Đây là vấn đề về phạm vi bao phủ của pattern, không liên quan đến việc `case null` có đứng đầu hay không.

Tương tự, khi thiết kế lỗi dữ liệu:

~~~java
case null -> invalid("missing-command");
case Create c -> onCreate(c);
~~~

đừng tự động đổi `invalid("missing-command")` thành `ok("ignored")` chỉ vì null “không cần xử lý”. Việc biến đầu vào thiếu thành thành công có thể khiến hệ thống không phát hiện mất command.

## 12. Xử lý null ở ranh giới hệ thống: DTO, domain và ngoại lệ

Một quy trình ứng dụng thường có ba tầng:

~~~text
Input ngoài (JSON / queue / API / CLI)
              |
              v
Parse và validation theo hợp đồng nguồn
              |
              v
Domain object hợp lệ hoặc lỗi dữ liệu
              |
              v
Điều phối bằng pattern switch / handler
              |
              v
Kết quả nghiệp vụ / lỗi trạng thái / lỗi hệ thống
~~~

**Đừng nhầm từng tầng:**

- Một JSON thiếu khóa `command` không nhất thiết tương đương JSON có `"command": null`. Nếu giao thức phân biệt chúng, parser/DTO phải giữ được thông tin đó; sau khi đều quy thành một giá trị Java null thì `case null` **không thể khôi phục sự khác biệt**.
- Trường `units == 0` không phải selector null. Nó là validation số học thuộc `Create`.
- `Ship(null, "TR-7")` là object command có tồn tại nhưng payload thiếu field. `case null` trên `Command` không bắt trường hợp này; `onShip` phải kiểm tra.
- Trạng thái domain không cho phép thao tác (ví dụ đơn đã giao không thể hủy) nên là một loại kết quả **khác lỗi dữ liệu** nếu kiến trúc yêu cầu phân biệt.
- `NullPointerException` do bug không nên bị bắt rộng rồi trả “thiếu input” nếu chưa chứng minh null thực sự đến từ ranh giới dữ liệu.

Một comment contract rõ ràng có thể ghi:

~~~java
/**
 * Nhận command đã parse từ nguồn có thể thiếu request.
 * Null được coi là INVALID:missing-command, không ném exception.
 * Field null bên trong command được validate tại handler tương ứng.
 */
static Result handleNullable(Command command) { /* ... */ }
~~~

Đây là **minh họa Javadoc**, không phải phương thức độc lập chạy được vì phần thân được rút gọn. Quan trọng là document:

1. Phương thức có cho phép selector null không?
2. Null được ánh xạ sang giá trị nào?
3. Component null được xử lý ở đâu?
4. Ai chịu trách nhiệm sửa dữ liệu và phản ứng với kết quả?

## 13. Những lỗi thường gặp khi “sửa null”

**Lỗi 1 — tin rằng `default` bắt null.** Pattern `switch` Java 21 không tự đi vào `default` khi selector null. Bổ sung `case null` nếu null là input được chấp nhận hoặc từ chối sớm theo contract.

**Lỗi 2 — thêm `case null -> success` chỉ để tránh NPE.** Nếu null là payload lỗi, trả success che mất vấn đề. Hãy chọn kết quả có ý nghĩa như `INVALID` hoặc từ chối tường minh.

**Lỗi 3 — cho rằng `case null` ở ngoài xử lý tất cả null bên trong.** Selector null và component null thuộc các tầng khác nhau. Record lồng cần fallback/guard hoặc constructor validation.

**Lỗi 4 — viết `case String s when s == null` để bắt selector null.** Type pattern `String` ở selector không khớp null; guard không chạy. Dùng `case null`.

**Lỗi 5 — nghĩ `var` đảm bảo non-null.** `var` suy ra kiểu tĩnh; component pattern `var name` có thể nhận null. Phải có guard hoặc invariant đáng tin.

**Lỗi 6 — nghĩ component pattern `String body` luôn loại null.** Với record component đã khai báo kiểu `String`, pattern con unconditional có thể khớp null trong Java 21. Không dereference nếu không có bảo đảm dữ liệu.

**Lỗi 7 — đảo thứ tự bảo vệ null.** `name.isBlank() && name != null` có thể ném NPE; `name != null && !name.isBlank()` an toàn nhờ short-circuit.

**Lỗi 8 — dùng `default` che việc thêm subtype trong sealed interface.** Nếu tập command đóng, bỏ `default` và xử lý đủ subtype để compiler giúp phát hiện khi schema mở rộng.

**Lỗi 9 — lẫn “không có command” với “command có payload không hợp lệ”.** `null` selector thuộc điểm điều phối; `new Create(null, -1)` là object tồn tại, cần validation ở handler/factory.

**Lỗi 10 — bắt mọi `RuntimeException` rồi trả lỗi dữ liệu.** Điều này có thể che cả bug và lỗi hạ tầng. Catch chỉ những lỗi tầng hiện tại thực sự biết cách xử lý.

**Lỗi 11 — thay policy mà không sửa test.** Khi đổi từ từ chối null sang trả `Result(INVALID, ...)`, cập nhật tài liệu và các ca kiểm thử; không để caller cũ trông chờ NPE mà bất ngờ nhận kết quả nghiệp vụ.

**Lỗi 12 — sử dụng `Optional` thay cho mọi null.** `Optional` có ích để biểu diễn một số kết quả có thể thiếu, nhưng không tự giải quyết validation của record lồng hay hợp đồng input; cũng không có nghĩa mọi parameter/field đều nên chuyển thành `Optional`.

**Lỗi 13 — coi ghi log là xử lý null.** Log “request missing” nhưng vẫn tiếp tục dereference command sẽ vẫn có NPE. Nhánh null phải có hành vi kết thúc hoặc fallback được thiết kế đúng.

## 14. Checklist review trước khi chốt null case

| Câu hỏi | Cách xác minh |
| --- | --- |
| Selector có thể null theo contract không? | Đọc tài liệu API và nguồn dữ liệu |
| Nếu null, đó là trạng thái hợp lệ hay lỗi? | Chọn rõ return/exception |
| Có dùng `case null` hay `requireNonNull` đúng chính sách? | Test đường null |
| `default` có bị hiểu nhầm là null handling? | Test `switch(null)` |
| Type pattern và record pattern có đúng thứ tự? | Kiểm tra dominated case |
| Nested record có thể null không? | Test thiếu record con |
| Component của record có thể null không? | Test null tên/field |
| Guard có kiểm tra null trước dereference? | Test null + chuỗi trắng |
| `sealed switch` đã bao phủ mọi subtype? | Biên dịch không cần `default` |
| Payload sai có khác selector thiếu không? | Test riêng hai tình huống |
| Handler có bị nhân bản logic sau refactor? | So sánh kết quả trên cùng input |
| Ngoại lệ ngoài dự kiến có bị che? | Review catch rộng |
| Có ghi rõ contract null trong Javadoc? | Review call site và API |
| Có kiểm thử ít nhất một kiểu ngoài tập pattern? | Test fallback |
| Có kiểm thử hành vi sau khi thêm subtype? | Build/compile và regression |

### Bài tập thực hành

1. **Thay đổi policy:** sửa `handleNullable` để từ chối null bằng `Objects.requireNonNull`. Điều chỉnh `null-command` thành một ca kiểm tra exception và giải thích vì sao đây là thay đổi hợp đồng.
2. **Từ chối dữ liệu tại constructor:** thêm compact constructor vào `Create`, `Ship` và `Cancel`. Những ca kiểm thử null component hiện nay sẽ phải đổi từ kiểm tra `Result(INVALID)` sang kiểm tra ngoại lệ ngay khi tạo object. So sánh hai chiến lược validation.
3. **Bổ sung command:** thêm subtype `Refund(String id, long cents)` vào `Command.permits`. Biên dịch lại và xác định cả hai `switch` cần thêm nhánh nào để giữ exhaustive. Định nghĩa riêng policy null.
4. **Thêm record lồng:** mở rộng `Envelope` thêm `Customer.email`. Viết guard null-safe cho email và test trường hợp thiếu customer, customer thiếu tên, email null, email trắng.
5. **Phân biệt null đầu vào:** tạo lớp `MissingRequest` hoặc một result type riêng để phân biệt “không có request” với “request có payload null”, thay vì biến cả hai thành selector null.
6. **Tự xây bảng kiểm thử:** với một `switch` bất kỳ, lập ma trận selector null, subtype hợp lệ, subtype có component null, kiểu không hỗ trợ và guard false. Chỉ gọi refactor hoàn thành khi mọi dòng có hành vi mong đợi.

**Ghi nhớ:** **Bổ sung `case null` đúng chủ đích** là quyết định về **hợp đồng API và ngữ nghĩa domain**, không chỉ là thêm một nhánh để tránh `NullPointerException`. Selector null của pattern switch khác null ở record component; `default` khác `case null`; một API nullable khác API bắt buộc đầu vào. Hãy chọn chính sách rõ ràng, giữ exhaustive trên tập sealed, bảo vệ các component bằng guard/invariant và dùng kiểm thử để chứng minh hành vi đã thay đổi đúng yêu cầu.