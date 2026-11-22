# Làm cho `switch` exhaustive trong Java 21+: bài thực hành tổng hợp

## 1. Mục tiêu của bài

Khi Java chọn nhánh xử lý bằng `switch`, câu hỏi quan trọng là: **đã có đường đi hợp lệ cho mọi giá trị mà kiểu selector cho phép chưa?** Nếu chưa, chương trình có thể bỏ sót một subtype, một enum constant hoặc trường hợp guard không khớp.

Tính chất **exhaustive** (bao quát đầy đủ) là việc các nhãn `case` đủ để xử lý tất cả những trường hợp mà quy tắc **kiểm tra tại compile time** của Java yêu cầu. Với `switch expression`, điều kiện này đặc biệt quan trọng vì biểu thức bắt buộc phải tạo kết quả khi hoàn thành bình thường.

Java 21 hỗ trợ chính thức:

- **Type patterns:** `case String s -> ...`.
- **Record patterns:** `case Create(var id) -> ...`; có thể tách nhiều component trong cùng pattern.
- **Guarded patterns:** `case Create(var id) when id.isBlank() -> ...`.
- **Sealed hierarchy:** compiler biết tập các subtype trực tiếp được phép.
- **`case null`:** xử lý selector là null khi hợp đồng cho phép.

**Kết quả mong muốn:** sau bài học, bạn có thể sửa một `switch` chưa exhaustive, tránh dùng `default` để che thiếu case trên sealed hierarchy, xử lý guard true/false, kết hợp nested record patterns, và phân biệt **exhaustive ở compile time** với **an toàn runtime** khi gặp null hoặc dữ liệu không khớp.

> Phạm vi: Java 21 trở lên. `Pattern Matching for switch` (JEP 441) và `Record Patterns` (JEP 440) đã là tính năng chuẩn trong Java 21; không cần `--enable-preview`.

## 2. Tại sao compiler yêu cầu exhaustive?

Ví dụ một `switch expression` không đầy đủ:

~~~java
static String label(Object value) {
    return switch (value) {
        case String s -> "String: " + s;
    };
}
~~~

Đoạn trên **không biên dịch** vì `value` có kiểu tĩnh `Object`: bên cạnh `String`, giá trị có thể là `Integer`, `Long`, bất kỳ object khác hoặc null. Compiler không thể chứng minh switch sẽ luôn cho kết quả hợp lệ.

Một diagnostic thường gặp:

~~~text
error: the switch expression does not cover all possible input values
~~~

Sửa bằng một case dự phòng cho các giá trị non-null khác, đồng thời quyết định chính sách null:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "String: " + s;
        default -> "Kiểu khác";
    };
}
~~~

Bây giờ mọi giá trị đều có nhánh:

- `null` → `"NULL"`.
- String không null → `case String s`.
- Các object khác → `default`.

**Phân biệt quan trọng:** `default` giúp bao quát các trường hợp còn lại phục vụ tính exhaustive, nhưng **không tự bắt selector null**. Thiếu `case null`, một `switch` trên reference selector vẫn có thể ném `NullPointerException` ở runtime, dù compile thành công và có `default`.

## 3. Chọn chiến lược theo kiểu tĩnh của selector

Cách làm cho switch exhaustive phụ thuộc **kiểu của biểu thức selector**, không chỉ loại object xuất hiện trong một lần chạy.

| Kiểu selector | Cách thường dùng để đạt exhaustiveness | Điều cần lưu ý |
| --- | --- | --- |
| `Object` hoặc interface mở | `default` hoặc type pattern bao quát phần non-null còn lại | `null` có chính sách riêng |
| `enum` | Liệt kê đầy đủ các enum constants hoặc dùng `default` | Liệt kê đầy đủ giúp compiler phát hiện enum constant mới |
| `sealed interface` | Bao quát từng permitted subtype, tránh `default` khi thích hợp | Khi thêm subtype, switch có thể lỗi compile để nhắc cập nhật |
| Record type | Có record pattern bao quát, hoặc type pattern tổng quát cho record đó | Nested patterns có thể không khớp vì component null |
| Kiểu `String` | Bao quát mọi giá trị String bằng case thích hợp hoặc `default` | Các `case "A"`, `case "B"` không bao phủ mọi String |
| Kiểu nguyên thủy `int` | Các hằng số cụ thể cùng `default` khi không thể bao phủ mọi số bằng cách liệt kê | `int` không null; boxed `Integer` có thể null |

Không nên dùng `default` theo thói quen cho mọi kiểu. Trên **sealed hierarchy**, lợi thế lớn của việc liệt kê tất cả subtype là compiler báo khi domain model thay đổi; một `default` quá rộng có thể làm mất tín hiệu này.

## 4. Bước 1 — Bắt đầu với sealed hierarchy

Dùng hệ thống giả định có ba loại hành động:

~~~java
sealed interface Action permits Create, Adjust, Relocate {}

record Create(String id) implements Action {}
record Adjust(int delta) implements Action {}

record Point(int x, int y) {}
record Relocate(Point destination) implements Action {}
~~~

Ba record `Create`, `Adjust` và `Relocate` là các subtype trực tiếp duy nhất được phép của `Action`. Record vốn là `final` nên không thể có subtype phát sinh từ chúng.

Một switch **chưa exhaustive**:

~~~java
static String describe(Action action) {
    return switch (action) {
        case Create(var id) -> "CREATE:" + id;
        case Adjust(var delta) -> "ADJUST:" + delta;
    };
}
~~~

Compiler có thể báo:

~~~text
the switch expression does not cover all possible input values
~~~

Bởi vì `Relocate` là một subtype hợp lệ chưa có nhánh. Compiler không quan tâm rằng chương trình demo chưa từng tạo `Relocate`. Nó xem **kiểu tĩnh `Action` và tập subtype có thể xuất hiện**.

**Sửa đúng hướng:**

~~~java
static String describe(Action action) {
    return switch (action) {
        case Create(var id) -> "CREATE:" + id;
        case Adjust(var delta) -> "ADJUST:" + delta;
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

Switch này đã xử lý ba subtype của `Action`. Không cần thêm `default` chỉ để compiler im lặng. Tuy nhiên **selector null** vẫn cần chính sách riêng nếu method cho phép nhận null; xét tiếp ở bước 3.

## 5. Bước 2 — Guard `when` không thay thế nhánh bao quát

Muốn phân loại riêng các lệnh `Create` có ID rỗng:

~~~java
// CỐ Ý KHÔNG EXHAUSTIVE:
static String describe(Action action) {
    return switch (action) {
        case Create(var id) when id != null && !id.isBlank() ->
            "CREATE:" + id;
        case Adjust(var delta) -> "ADJUST:" + delta;
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

Dù có một `case Create(...)`, nó **chỉ chọn khi guard đúng**. Ví dụ `new Create(null)` hoặc `new Create("   ")` vẫn là instance `Create` nhưng guard sai, không khớp case đó. Vì vậy một **guard phụ thuộc dữ liệu** không bao phủ toàn bộ subtype.

**Sửa bằng nhánh Create không guard:**

~~~java
static String describe(Action action) {
    return switch (action) {
        case Create(var id) when id == null || id.isBlank() ->
            "CREATE_INVALID";
        case Create(var id) ->
            "CREATE:" + id;
        case Adjust(var delta) ->
            "ADJUST:" + delta;
        case Relocate(var destination) ->
            "RELOCATE";
    };
}
~~~

Bây giờ có hai đường cho `Create`:

1. Guard đúng → `CREATE_INVALID`.
2. Guard sai → case `Create` tổng quát → `CREATE:<id>`.

**Thứ tự quan trọng:** nhánh có guard cụ thể đứng trước nhánh không guard. Nếu đặt `case Create(var id)` tổng quát trước, nhánh `Create ... when ...` phía sau có thể bị compiler báo **dominated case label**.

Tương tự với `Adjust`:

~~~java
case Adjust(var delta) when delta == 0 -> "NO_CHANGE";
case Adjust(var delta) -> "ADJUST:" + delta;
~~~

Guard đúng chỉ xử lý delta bằng 0; nhánh không guard vẫn cần để bao quát delta khác 0.

**Lưu ý:** nếu constructor của record chủ động cấm ID null/rỗng, một số nhánh invalid có thể không xuất hiện trong runtime với object hợp lệ. Nhưng không nên tin invariant ngoài type system như một cách thay thế tùy tiện cho exhaustiveness của compiler; hãy viết switch theo hợp đồng dữ liệu và tránh case thừa khi thật sự không cần.

## 6. Bước 3 — Xử lý null selector có chủ đích

Trên reference selector:

~~~java
static String typeOf(Action action) {
    return switch (action) {
        case Create(var id) -> "CREATE";
        case Adjust(var delta) -> "ADJUST";
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

Switch trên có thể **biên dịch thành công** vì đã bao quát subtype của `Action`. Nhưng:

~~~java
typeOf(null); // Runtime: NullPointerException
~~~

Không nên kết luận “exhaustive nghĩa là không còn runtime exception”. Tính exhaustive compile time và null policy là **hai vấn đề khác nhau**.

### Chính sách A — null là một trạng thái được cho phép

~~~java
static String typeOf(Action action) {
    return switch (action) {
        case null -> "NULL_ACTION";
        case Create(var id) -> "CREATE";
        case Adjust(var delta) -> "ADJUST";
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

### Chính sách B — null là lỗi hợp đồng API

~~~java
static String typeOf(Action action) {
    java.util.Objects.requireNonNull(action, "action");
    return switch (action) {
        case Create(var id) -> "CREATE";
        case Adjust(var delta) -> "ADJUST";
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

`requireNonNull` ném NPE với thông điệp có chủ đích ngay tại tiền điều kiện. Có thể chọn exception domain/application khác nếu null là input lỗi cần phản hồi nghiệp vụ.

**Tránh hiểu lầm:** `default` không thay `case null`. Ngay cả `case Object obj` là một type pattern rất rộng cũng không xử lý selector null khi không có nhãn `case null`.

Khi cần gom null và các loại còn lại trong một switch trên `Object`, Java 21 cho phép:

~~~java
static String onlyText(Object value) {
    return switch (value) {
        case String s -> s;
        case null, default -> "Không phải text hoặc null";
    };
}
~~~

Chỉ gộp như vậy nếu null và kiểu khác **thật sự** có cùng ý nghĩa. Dùng hai nhánh riêng khi domain cần phân biệt.

## 7. Bước 4 — Nested record pattern và sự khác nhau giữa exhaustive compile time và runtime

Xét `Relocate` có component `Point destination`:

~~~java
record Point(int x, int y) {}
record Relocate(Point destination) implements Action {}
~~~

Muốn lấy tọa độ trực tiếp:

~~~java
case Relocate(Point(var x, var y)) ->
    "MOVE:" + x + "," + y;
~~~

Nhưng một instance `new Relocate(null)` vẫn hợp lệ về cú pháp nếu constructor không từ chối null. Khi đó:

- Selector ngoài là `Relocate` **không null**.
- Component `destination` là null.
- Nested record pattern `Point(var x, var y)` **không khớp null**.
- Nếu không còn case phù hợp, switch có thể gặp tình huống không match ở runtime.

### Một bẫy ít được biết: `MatchException`

Java 21 có thể **coi một nested record pattern là exhaustive về mặt type checking**, nhưng ở runtime một component null vẫn khiến mọi pattern đó không khớp:

~~~java
record Point(int x) {}
sealed interface Target permits Move {}
record Move(Point point) implements Target {}

static String risky(Target value) {
    return switch (value) {
        case Move(Point(var x)) -> "X:" + x;
    };
}
~~~

Đoạn trên được compiler chấp nhận như switch exhaustive trong Java 21, nhưng:

~~~java
risky(new Move(null)); // Runtime: java.lang.MatchException
~~~

Lý do: `Move(Point(var x))` không khớp khi component `point` bằng null, mặc dù pattern được xét đủ trong phân tích exhaustiveness theo cấu trúc. Đây là ví dụ cho giới hạn giữa **syntactic/type exhaustiveness** và **runtime totality**. Tài liệu API `java.lang.MatchException` Java 21 nêu cụ thể trường hợp nested record patterns và null.

**Sửa theo dữ liệu thực tế:**

~~~java
static String safe(Target value) {
    return switch (value) {
        case null -> "NO_TARGET_ACTION";
        case Move(Point(var x)) -> "X:" + x;
        case Move(var point) -> "MISSING_POINT";
    };
}
~~~

`case Move(var point)` là **record pattern tổng quát** đứng sau nhánh nested, có thể nhận reference component null, nên xử lý được `new Move(null)`. `case null` xử lý selector null riêng.

**Phương án khác:** nếu domain cấm null Point, kiểm tra ngay trong compact constructor của `Move` bằng `Objects.requireNonNull(point, "point")`. Khi đó mọi `Move` được tạo hợp lệ sẽ có Point; nhưng dữ liệu không tin cậy, serializer, reflection hoặc sự thay đổi binary schema vẫn cần được xem xét theo bối cảnh.

**Điểm review:** không chỉ hỏi “compiler có báo exhaustive không?”, mà còn hỏi “các nullable nested components có được xử lý bằng case tổng quát hoặc invariant đáng tin không?”. Không được đánh đồng null selector với null component.

## 8. Bước 5 — Enum exhaustive mà không có `default`

Giả sử:

~~~java
enum Traffic { RED, YELLOW, GREEN }
~~~

Một switch expression đầy đủ:

~~~java
static String traffic(Traffic signal) {
    return switch (signal) {
        case RED -> "STOP";
        case YELLOW -> "CAUTION";
        case GREEN -> "GO";
    };
}
~~~

Đây là một cách dùng **không có `default`** vì compiler biết các enum constants hiện được khai báo. Nếu sau này thêm `BLUE` vào `Traffic` rồi biên dịch lại nguồn, switch có thể được compiler báo thiếu case để bạn chủ động quyết định hành vi mới.

Nếu chỉ có `RED` và `GREEN`, bỏ `YELLOW`:

~~~java
// CỐ Ý KHÔNG EXHAUSTIVE:
return switch (signal) {
    case RED -> "STOP";
    case GREEN -> "GO";
};
~~~

Lỗi compile time vì switch expression chưa bao quát các constants hiện có.

**Null vẫn riêng:** `traffic(null)` ném `NullPointerException` nếu không có `case null`, dù enum switch đã liệt kê đủ constants. Có thể thêm nhãn null nếu business cho phép hoặc chặn đầu vào bằng tiền điều kiện.

**Tương thích khi thay đổi enum:** cùng với sealed hierarchy, khi các lớp được compile riêng hoặc enum bị thay đổi giữa thời điểm compile/runtime, một switch được coi exhaustive có thể gặp giá trị ngoài các case đã biết và ném `MatchException`. Đó là trường hợp tương thích nhị phân cần lưu ý, không phải lý do thêm `default` vô điều kiện vào mọi switch.

## 9. Bước 6 — Kiểu `Object` hoặc interface mở: `default` có vai trò hợp lý

Với selector kiểu `Object`, compiler không có danh sách subtype đóng như `sealed Action`. Có thể viết:

~~~java
static String classifyObject(Object value) {
    return switch (value) {
        case null -> "ANY_NULL";
        case Action action -> classify(action);
        case String text -> "TEXT:" + text;
        default -> "OTHER";
    };
}
~~~

Trong ví dụ:

- `Action action` là type pattern; với object thuộc subtype của `Action`, ta gọi một switch chuyên biệt `classify`.
- `String text` bắt các chuỗi.
- `default` bắt các object không null còn lại.

**Một lựa chọn không cần default** là type pattern tổng quát cuối cùng:

~~~java
static String classifyAny(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "TEXT:" + text;
        case Object other -> "OBJECT:" + other.getClass().getSimpleName();
    };
}
~~~

`case Object other` bao quát các reference object không null còn lại; `case null` xử lý null. Nếu đặt `case Object other` lên đầu, các type patterns cụ thể sau có thể bị báo **dominated**.

Lựa chọn giữa `default` và type pattern tổng quát phụ thuộc vào việc bạn có cần **biến ràng buộc** kiểu cha trong nhánh hay không. Không phải một lựa chọn có hiệu năng luôn tốt hơn.

## 10. `switch expression`, `switch statement` và trường hợp “enhanced”

Hai dạng `switch` thường gặp:

### `switch expression` — trả ra một giá trị

~~~java
String text = switch (action) {
    case Create(var id) -> "CREATE";
    case Adjust(var delta) -> "ADJUST";
    case Relocate(var point) -> "RELOCATE";
};
~~~

Switch expression luôn cần exhaustive theo quy tắc ngôn ngữ; nhánh block muốn trả giá trị dùng `yield`:

~~~java
String text = switch (action) {
    case Create(var id) -> {
        String normalized = id == null ? "?" : id.strip();
        yield "CREATE:" + normalized;
    }
    case Adjust(var delta) -> "ADJUST:" + delta;
    case Relocate(var point) -> "RELOCATE";
};
~~~

### `switch statement` — thực hiện hành động

Từ Java 21, **enhanced switch statement** (ví dụ có nhãn pattern hoặc null) cũng **phải exhaustive**:

~~~java
static void printAction(Object action) {
    switch (action) {
        case null -> System.out.println("NULL");
        case String text -> System.out.println(text);
        default -> System.out.println("OTHER");
    }
}
~~~

Bỏ `default` ở ví dụ switch statement trên sẽ khiến một enhanced switch statement với selector `Object` và chỉ case String/null không exhaustive.

**Phân biệt với legacy switch statement:** một switch statement truyền thống trên enum/int/String, không có pattern hay `case null` và không thuộc dạng enhanced, vẫn có thể không exhaustive vì lý do tương thích với Java cũ:

~~~java
enum Traffic { RED, YELLOW, GREEN }

static void printLegacy(Traffic signal) {
    switch (signal) {
        case RED -> System.out.println("STOP");
        case GREEN -> System.out.println("GO");
        // Không có YELLOW: dạng switch statement truyền thống
        // vẫn có thể được compiler chấp nhận.
    }
}
~~~

Không suy từ tính được phép của **legacy statement** rằng mọi **switch expression** hay **enhanced statement** cũng được bỏ case. Xem JLS Java 21 `14.11 để xác định trường hợp nào yêu cầu exhaustiveness.

## 11. Chương trình thực hành đầy đủ Java 21+

Mã sau gộp các kỹ thuật: sealed hierarchy, record patterns, `when` và fallback không guard, nested record pattern, `case null`, enum exhaustive, và selector kiểu Object có `default`.

Lưu vào **`ExhaustiveSwitchPracticeDemo.java`**:

~~~java
public class ExhaustiveSwitchPracticeDemo {
    sealed interface Action permits Create, Adjust, Relocate {}

    record Create(String id) implements Action {}
    record Adjust(int delta) implements Action {}
    record Point(int x, int y) {}
    record Relocate(Point destination) implements Action {}

    enum Traffic { RED, YELLOW, GREEN }

    static String classify(Action action) {
        return switch (action) {
            case null -> "NULL_ACTION";

            case Create(var id) when id == null || id.isBlank() ->
                "CREATE_INVALID";

            case Create(var id) ->
                "CREATE:" + id;

            case Adjust(var delta) when delta == 0 ->
                "NO_CHANGE";

            case Adjust(var delta) ->
                "ADJUST:" + delta;

            case Relocate(Point(var x, var y)) when x == y ->
                "MOVE_DIAGONAL:" + x;

            case Relocate(Point(var x, var y)) ->
                "MOVE:" + x + "," + y;

            case Relocate(var destination) ->
                "MOVE_MISSING";
        };
    }

    static String traffic(Traffic signal) {
        return switch (signal) {
            case RED -> "STOP";
            case YELLOW -> "CAUTION";
            case GREEN -> "GO";
        };
    }

    static String classifyObject(Object value) {
        return switch (value) {
            case null -> "ANY_NULL";
            case Action action -> classify(action);
            case String text -> "TEXT:" + text;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify(new Create(null)));
        System.out.println(classify(new Create("   ")));
        System.out.println(classify(new Create("REQ-1")));
        System.out.println(classify(new Adjust(0)));
        System.out.println(classify(new Adjust(-2)));
        System.out.println(classify(
                new Relocate(new Point(3, 3))));
        System.out.println(classify(
                new Relocate(new Point(1, 4))));
        System.out.println(classify(new Relocate(null)));

        System.out.println(traffic(Traffic.RED));
        System.out.println(traffic(Traffic.YELLOW));
        System.out.println(traffic(Traffic.GREEN));

        System.out.println(classifyObject(
                new Create("REQ-2")));
        System.out.println(classifyObject("hello"));
        System.out.println(classifyObject(5));
        System.out.println(classifyObject(null));

        try {
            traffic(null);
        } catch (NullPointerException e) {
            System.out.println("TRAFFIC_NULL_NPE");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 -encoding UTF-8 ExhaustiveSwitchPracticeDemo.java
java ExhaustiveSwitchPracticeDemo
~~~

**Stdout chính xác:**

~~~text
NULL_ACTION
CREATE_INVALID
CREATE_INVALID
CREATE:REQ-1
NO_CHANGE
ADJUST:-2
MOVE_DIAGONAL:3
MOVE:1,4
MOVE_MISSING
STOP
CAUTION
GO
CREATE:REQ-2
TEXT:hello
OTHER
ANY_NULL
TRAFFIC_NULL_NPE
~~~

### 11.1. Tại sao chương trình này exhaustive?

- `Action` có ba subtype được phép: `Create`, `Adjust` và `Relocate`.
- Các pattern `Create(var id)`, `Adjust(var delta)` và `Relocate(var destination)` **không guard** bảo đảm luôn có nhánh cho từng subtype non-null.
- Các case có `when` **đứng trước** fallback cùng subtype; guard true/false đều dẫn tới nhánh có kết quả.
- Với `Relocate`, nested `Point(...)` khớp điểm đến hợp lệ; fallback `Relocate(var destination)` xử lý component null.
- `case null` xử lý `Action` selector null theo hợp đồng của demo.
- `Traffic` đã liệt kê đủ ba constants; dù vậy selector enum null vẫn NPE vì `traffic` không có `case null`.
- `classifyObject` có `default` hợp lý vì selector là `Object` và không giới hạn vào hierarchy đóng.

### 11.2. Vì sao không thêm `default` vào `classify`?

Vì hierarchy `Action` đóng và mọi subtype đã được liệt kê. Nếu sau này thêm `record Cancel(...) implements Action`, việc compiler yêu cầu cập nhật `classify` là một **tín hiệu hữu ích**, tránh tình huống một loại hành động mới âm thầm nhận kết quả chung như `"OTHER"`.

### 11.3. Vì sao demo cho phép ID hoặc Point null?

Để minh họa khả năng xử lý guard và nested fallback. Một domain model thật có thể dùng compact constructor:

~~~java
record Create(String id) implements Action {
    public Create {
        if (id == null || id.isBlank())
            throw new IllegalArgumentException("id rỗng");
        id = id.strip();
    }
}

record Relocate(Point destination) implements Action {
    public Relocate {
        java.util.Objects.requireNonNull(destination, "destination");
    }
}
~~~

Đây là các khai báo **thay thế** cho những record tương ứng trong ví dụ, không được dán cùng file với các khai báo `Create`/`Relocate` đã có vì sẽ bị trùng tên.

Khi constructor bảo vệ invariant, nhiều input null bị từ chối sớm. Tuy nhiên vẫn nên hiểu cả quy tắc exhaustive của compiler và quy tắc match runtime để thiết kế code review và tests đúng.

## 12. Quy trình sửa một switch chưa exhaustive

Khi nhận lỗi:

~~~text
the switch expression does not cover all possible input values
~~~

Đừng lập tức chèn `default -> null`. Hãy xử lý theo thứ tự:

1. **Xác định kiểu selector**: là enum, sealed interface, Object hay interface mở?
2. **Liệt kê các trường hợp được phép**: enum constants hoặc permitted subtypes; với Object cần xác định nhánh tổng quát.
3. **Nhìn từng case có `when`**: guard true không đủ; có case không guard hoặc chuỗi case bao quát hoàn toàn trường hợp guard false không?
4. **Kiểm tra record patterns lồng**: có component null hoặc kiểu nested khác làm pattern không match không?
5. **Quyết định chính sách null selector**: case null hay chặn null từ boundary?
6. **Đặt case chuyên biệt trước case tổng quát** để tránh dominance.
7. **Biên dịch lại** với language level đúng, ví dụ `javac --release 21`.
8. **Viết test cho từng đường thực thi**: không chỉ quan sát compiler hết báo lỗi.

Ví dụ sửa theo từng bước:

~~~text
Bản lỗi A: thiếu Relocate
  -> thêm case Relocate(...)

Bản lỗi B: có Create when ..., không có Create thường
  -> thêm case Create(...) không guard

Bản lỗi C: chỉ có Relocate(Point(...))
  -> thêm Relocate(var destination) nếu component có thể null

Bản lỗi D: default đã đủ compile nhưng selector null gây NPE
  -> thêm case null hoặc từ chối null sớm

Bản lỗi E: case tổng quát đứng trước case guard
  -> đưa case chuyên biệt lên trước
~~~

**Đọc đúng chẩn đoán:** lỗi arity/kiểu record pattern, lỗi dominance và lỗi không exhaustive đều là **compile-time errors khác nhau**. Không có một cách chữa “thêm default” áp dụng đúng cho tất cả.

## 13. Tại sao `default -> null` hay `default -> ""` có thể gây hại?

Một câu lệnh kiểu:

~~~java
return switch (action) {
    case Create(var id) -> "CREATE";
    case Adjust(var delta) -> "ADJUST";
    default -> "";
};
~~~

trông dễ compile, nhưng nếu `action` là `Relocate`, người gọi nhận chuỗi rỗng mà không biết có loại hành động **chưa được xử lý**. Nếu hệ thống cần báo lỗi cho các trường hợp không hỗ trợ, câu trả về rỗng còn có thể làm sai log, thống kê hoặc API.

Các lựa chọn có chủ đích hơn:

- **Sealed hierarchy đóng:** liệt kê từng subtype và tận dụng compiler exhaustiveness; không dùng default nếu không cần.
- **Kiểu mở:** nếu không xử lý được loại khác, dùng `default -> throw new IllegalArgumentException("Unsupported action")` hoặc kiểu lỗi miền phù hợp; tránh phản hồi thành công giả.
- **Đầu vào có type discriminator từ JSON:** mapping/validation tại boundary trước khi tạo subtype, không làm mất thông tin về loại payload không biết.
- **Thực sự muốn fallback:** định nghĩa hành vi fallback trong contract và test cho một object thuộc kiểu chưa xử lý.

Nhớ rằng `default` trên switch reference **không bắt null**; nếu muốn một chính sách chung cho null và phần còn lại, dùng `case null, default -> ...` khi Java 21 cho phép và hợp đồng thực sự coi chúng tương đương.

## 14. Test matrix: compiler bảo đảm gì, còn runtime cần test gì?

| ID | Input | Đường mong đợi | Ý nghĩa |
| --- | --- | --- | --- |
| T1 | `null` gửi vào `classify` | `NULL_ACTION` | Case null selector |
| T2 | `Create(null)` | `CREATE_INVALID` | Guard true do vế trái `id == null` |
| T3 | `Create("   ")` | `CREATE_INVALID` | Guard true do `id.isBlank()` |
| T4 | `Create("REQ-1")` | `CREATE:REQ-1` | Guard false, Create fallback |
| T5 | `Adjust(0)` | `NO_CHANGE` | Guard Adjust true |
| T6 | `Adjust(-2)` | `ADJUST:-2` | Guard Adjust false |
| T7 | `Relocate(Point(3,3))` | `MOVE_DIAGONAL:3` | Nested record + guard true |
| T8 | `Relocate(Point(1,4))` | `MOVE:1,4` | Nested record + guard false |
| T9 | `Relocate(null)` | `MOVE_MISSING` | Nested pattern không match, fallback nhận null component |
| T10 | `Traffic.RED/YELLOW/GREEN` | STOP/CAUTION/GO | Enum constants được bao quát |
| T11 | `Traffic` selector null | NPE theo demo | Exhaustive không có nghĩa null-safe |
| T12 | `Object` nhận `Create("REQ-2")` | `CREATE:REQ-2` | Type pattern Action |
| T13 | `Object` nhận String | `TEXT:hello` | Type pattern String |
| T14 | `Object` nhận Integer | `OTHER` | Default |
| T15 | `Object` selector null | `ANY_NULL` | Null case trong switch Object |

Ma trận này là **kiểm thử hành vi**, không phải tỉ lệ JaCoCo branch coverage. Đối với guarded patterns, cần test cả điều kiện đúng và sai, đặc biệt khi guard gồm `&&` hoặc `||`. Không được chỉ đếm một lần vào mỗi nhãn `case` rồi kết luận mọi đường đi đều được kiểm tra.

## 15. JUnit 5: kiểm tra tính đúng của giải pháp

Có thể chuyển ví dụ thành unit tests. File sau giả định class demo nằm trong cùng package và project đã có JUnit 5 dependency; đây **không phải chương trình Java độc lập chỉ chạy bằng javac không có classpath JUnit**.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExhaustiveSwitchPracticeDemoTest {
    @Test
    void handlesNullAndCreateGuard() {
        assertEquals("NULL_ACTION",
                ExhaustiveSwitchPracticeDemo.classify(null));
        assertEquals("CREATE_INVALID",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Create(" ")));
        assertEquals("CREATE:REQ-1",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Create("REQ-1")));
    }

    @Test
    void handlesRelocateWithNullComponent() {
        assertEquals("MOVE_DIAGONAL:3",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Relocate(
                                new ExhaustiveSwitchPracticeDemo.Point(3, 3))));
        assertEquals("MOVE_MISSING",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Relocate(null)));
    }

    @Test
    void checksAllEnumConstantsAndNullPolicy() {
        for (var traffic : ExhaustiveSwitchPracticeDemo.Traffic.values()) {
            assertNotNull(ExhaustiveSwitchPracticeDemo.traffic(traffic));
        }
        assertThrows(NullPointerException.class,
                () -> ExhaustiveSwitchPracticeDemo.traffic(null));
    }
}
~~~

Một test dùng `Traffic.values()` để chạy qua các constants hiện có, nhưng với domain quan trọng vẫn nên assert **chính xác** mỗi giá trị (STOP/CAUTION/GO), không chỉ `assertNotNull`. Nếu contract thay đổi, test cần phản ánh quy tắc nghiệp vụ, không chỉ bảo đảm code có trả chuỗi.

Kiểm thử trên JDK baseline của dự án. Khi code dùng Java 21 patterns, compile/tests phải chạy với compiler hỗ trợ `--release 21`; không thêm `--enable-preview` cho record/switch patterns chuẩn của Java 21.

## 16. Các lỗi hay gặp khi làm exhaustive `switch`

| Lỗi/hiểu nhầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Chỉ có case cho một số subtype sealed | Compiler thấy subtype còn thiếu | Thêm case cho subtype đó |
| Có `when` nhưng thiếu fallback không guard | Guard false làm thiếu đường bao phủ | Thêm case tổng quát cùng subtype |
| Đặt case tổng quát trước case có guard | Nhánh sau bị dominated | Sắp xếp case cụ thể trước |
| Chỉ dùng nested record pattern | Nullable component có thể không match dù compiler cho exhaustive | Xem invariant hoặc thêm record fallback |
| Thấy compile thành công và tin không có exception | Null selector hay `MatchException` vẫn có thể xuất hiện | Test runtime, null/nested coverage |
| Cho rằng `default` nhận null | Java xử lý selector null riêng | `case null` hoặc chặn null sớm |
| Luôn thêm `default` vào sealed switch | Che việc thêm subtype mới | Ưu tiên liệt kê subtype đầy đủ |
| Dùng `case Object o` rồi đặt type pattern nhỏ sau | Type patterns cụ thể bị dominated | Đưa pattern rộng cuối cùng |
| Dùng switch expression thiếu enum constant | Không exhaustive compile-time | Liệt kê đủ constants |
| Cho rằng mọi switch statement đều bắt buộc exhaustive | Legacy statement khác enhanced statement | Phân biệt theo JLS Java 21 |
| Thêm case để compile nhưng trả `null` cho subtype chưa hỗ trợ | Che bug nghiệp vụ | Trả lỗi rõ hoặc triển khai hành vi |
| Đếm số nhãn case bằng tỷ lệ branch coverage | C1 dựa trên bytecode, guard nhiều đường | Dùng test matrix và coverage report |
| Không recompilation sau khi thêm subtype/enum constant | Binary cũ có thể gặp giá trị mới | Rebuild/redeploy đồng bộ, integration tests |

## 17. Bài tập thực hành theo cấp độ

### Bài 1 — Tìm subtype còn thiếu

~~~java
sealed interface Request permits CreateUser, DeleteUser, UpdateUser {}
record CreateUser(String id) implements Request {}
record DeleteUser(String id) implements Request {}
record UpdateUser(String id) implements Request {}

static String route(Request request) {
    return switch (request) {
        case CreateUser(var id) -> "CREATE";
        case DeleteUser(var id) -> "DELETE";
    };
}
~~~

Hãy sửa để switch exhaustive **không dùng `default`**. Nếu thêm `record LockUser(...) implements Request`, những thay đổi nào cần thực hiện ở `permits` và switch?

### Bài 2 — Guard true/false

~~~java
case CreateUser(var id) when id != null && !id.isBlank() ->
    "CREATE:" + id;
~~~

Vì sao chỉ có nhánh này không đủ bao quát mọi `CreateUser`? Bổ sung nhánh xử lý ID null hoặc blank và test ít nhất hai đường.

### Bài 3 — Nested record null

~~~java
record Point(int x) {}
sealed interface Task permits Move {}
record Move(Point point) implements Task {}

return switch (task) {
    case Move(Point(var x)) -> "X:" + x;
};
~~~

Có thể compiler chấp nhận đoạn trên như exhaustive không? Khi `new Move(null)` thì điều gì có thể xảy ra? Viết một phiên bản tránh `MatchException` bằng fallback.

### Bài 4 — Enum và null

~~~java
enum Stage { NEW, ACTIVE, CLOSED }
~~~

Viết switch expression không `default` trả nhãn cho ba constants. Thử truyền null: compiler có tự bảo vệ không? Hãy bổ sung cách xử lý null theo hai chính sách khác nhau (cho phép null và cấm null).

### Bài 5 — Enhanced statement

Với selector kiểu `Object`, viết switch **statement** chỉ có `case String s -> ...`. Vì sao Java 21 có thể từ chối compile? Sửa để thành enhanced switch statement exhaustive nhưng vẫn không nhầm `default` với null.

### Bài 6 — Review một default nguy hiểm

Một PR chứa:

~~~java
return switch (request) {
    case CreateUser(var id) -> "OK";
    default -> "OK";
};
~~~

Giải thích vì sao code có thể compile nhưng không bảo đảm đã xử lý đúng `DeleteUser`/`UpdateUser`. Đề xuất cách xử lý khiến compiler nhắc khi hierarchy được mở rộng.

### Gợi ý đáp án

~~~java
// Bài 1: thêm nhánh còn thiếu:
case UpdateUser(var id) -> "UPDATE";

// Bài 2: nhánh cụ thể rồi nhánh bao quát:
case CreateUser(var id) when id == null || id.isBlank() ->
    "INVALID_CREATE";
case CreateUser(var id) -> "CREATE:" + id;

// Bài 3: nested trước, fallback sau:
case Move(Point(var x)) -> "X:" + x;
case Move(var point) -> "NO_POINT";

// Bài 4:
return switch (stage) {
    case null -> "UNKNOWN";
    case NEW -> "Mới";
    case ACTIVE -> "Hoạt động";
    case CLOSED -> "Đã đóng";
};
~~~

Các code fragments trong phần đáp án là **nhãn switch hoặc đoạn thân switch**, không phải các top-level chương trình độc lập; đặt vào ngữ cảnh method/class phù hợp để thử bằng compiler.

**Bài 5:** enhanced switch statement có pattern/null yêu cầu exhaustive; dùng thêm `default` hoặc type pattern bao quát, và `case null` nếu muốn nhận null hợp lệ. **Bài 6:** bỏ `default -> "OK"`, xử lý từng permitted subtype bằng case riêng và dùng test cho từng hành vi.

## 18. Checklist trước khi merge

- [ ] Đã xác định **kiểu tĩnh selector** và các subtype/enum constants có thể xảy ra.
- [ ] `switch expression` và enhanced statement thỏa exhaustive theo compiler.
- [ ] Các subtype của sealed hierarchy có case rõ; không dùng `default` để che subtype mới nếu không cần.
- [ ] Pattern có `when` đã có đường xử lý giá trị guard **false**.
- [ ] Case chuyên biệt đứng trước case tổng quát; không có dominance.
- [ ] Nested record components có thể null đã được validate hoặc có fallback phù hợp.
- [ ] `case null` hoặc tiền điều kiện non-null thể hiện chính sách selector.
- [ ] `default` dùng đúng khi selector mở/rộng hoặc fallback thực sự có ý nghĩa.
- [ ] Có test case cho mỗi nhánh nghiệp vụ, guard true/false, null selector, null component và kiểu khác.
- [ ] Không dùng compile-time exhaustive như một cam kết không thể phát sinh `MatchException`/NPE ở runtime.
- [ ] Code được biên dịch và thử trên JDK/source release đã chốt; stdout, exception, invariant được kiểm chứng.
- [ ] Việc thêm enum constant/subtype mới được kèm test và cập nhật handler tương ứng.

## 19. Tổng kết

**“Làm cho switch exhaustive”** không chỉ là thêm `default` để qua compiler:

1. Với **enum** hoặc **sealed hierarchy**, ưu tiên bao quát **từng constant/subtype** để giữ lợi ích kiểm tra khi model tiến hóa.
2. Với **guard `when`**, nhớ guard phụ thuộc dữ liệu có thể false, nên cần nhánh không guard hoặc tổ hợp case thực sự bao quát.
3. Với **nested record patterns**, xem xét null component và `MatchException` ngay cả khi compiler đã chấp nhận tính exhaustive.
4. Với **reference selector null**, chọn rõ `case null` hoặc tiền điều kiện từ chối; `default` không tự bắt null.
5. Với **selector mở** như `Object`, `default` hoặc một type pattern rộng có vị trí hợp lý.
6. Kiểm chứng bằng **`javac` + test matrix + runtime assertions**, không chỉ đếm case.

### Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): exhaustive switch, patterns, guarded patterns, dominance và null (Java 21).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): nested deconstruction và matching.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): permitted subtypes và mô hình đóng.
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JLS Java SE 21 `14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): enhanced statements và exhaustiveness.
- [JLS Java SE 21 `15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc switch expressions.
- [Java SE 21 API — `MatchException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): các tình huống runtime không match dù cấu trúc được coi exhaustive, gồm nullable nested record patterns.
