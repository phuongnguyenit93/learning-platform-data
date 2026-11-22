# Exhaustive switch expression và lỗi thiếu case trong Java Pattern Matching

## 1. Mô hình tư duy: một biểu thức phải cho ra kết quả với mọi khả năng

Trong Java, `switch` có thể dùng như **biểu thức** (switch expression): cả cấu trúc `switch (...) { ... }` tính ra một giá trị để gán cho biến hoặc trả về từ phương thức.

```java
enum Stage { NEW, ACTIVE, DONE }

static String label(Stage stage) {
    return switch (stage) {
        case NEW -> "new";
        case ACTIVE -> "active";
        case DONE -> "done";
    };
}
```

Ở đây, trình biên dịch nhận thấy mọi giá trị `Stage` đều có nhánh: `NEW`, `ACTIVE` hoặc `DONE`. Vì vậy, `switch` **exhaustive** (bao phủ đầy đủ các khả năng thuộc kiểu đầu vào được xét). Mỗi lần biểu thức `switch` chạy bình thường với một giá trị hợp lệ của `Stage`, nó có nhánh để tính ra kết quả.

Nếu bỏ `case DONE`, chương trình **không biên dịch**: với `Stage.DONE`, biểu thức sẽ không biết trả về gì. Đây là ý nghĩa của lỗi “thiếu case”.

```text
Stage
 ├── NEW       ──> "new"
 ├── ACTIVE    ──> "active"
 └── DONE      ──> "done"
                    ↓
           Đủ nhánh cho kiểu Stage
```

Từ Java 21, **pattern matching for switch** (JEP 441) cho phép dùng `case` dạng mẫu kiểu và mẫu record, nên khả năng bao phủ không chỉ đến từ liệt kê hằng `enum`. Trình biên dịch còn có thể chứng minh mọi kiểu con được cho phép của một `sealed` hierarchy đã có nhánh xử lý.

**Điểm quan trọng:** exhaustive là thuộc tính được kiểm tra **dựa trên kiểu tĩnh và cấu trúc của các case ở thời điểm biên dịch**, không phải việc chạy vài bộ dữ liệu thử mà không lỗi. Nó cũng không tự động đồng nghĩa với “an toàn với `null`” hay “đã kiểm tra hết các điều kiện nghiệp vụ”.

## 2. Vì sao switch expression cần exhaustive?

Xem phép gán:

```java
String message = switch (stage) {
    case NEW -> "Received";
    case ACTIVE -> "Processing";
    case DONE -> "Completed";
};
```

`switch` ở bên phải dấu `=` là một biểu thức. Java cần xác định biểu thức ấy có thể hoàn tất với một giá trị hoặc ném ngoại lệ, và không được rơi vào trạng thái “không có case nào thực thi” khi nhận một giá trị thuộc tập mà trình biên dịch phải bao phủ.

Khác với biểu thức:

```java
int score = switch (stage) {
    case NEW -> 0;
    case ACTIVE -> 50;
    case DONE -> 100;
};
```

`switch statement` kiểu cũ chỉ thực hiện lệnh:

```java
switch (stage) {
    case NEW -> System.out.println("Received");
    case ACTIVE -> System.out.println("Processing");
    // Bỏ DONE ở statement kiểu truyền thống vẫn có thể biên dịch.
}
```

Nếu thiếu một nhánh, loại statement truyền thống có thể chỉ không làm gì với giá trị đó. Tuy nhiên, **Java 21 yêu cầu enhanced switch statement phải exhaustive**: một switch statement dùng `case` pattern hoặc `case null`, hay chọn các kiểu mở rộng ngoài nhóm truyền thống, cũng phải bao phủ đầy đủ. Không nên áp dụng nhận xét “statement không cần exhaustive” cho mọi switch statement hiện đại.

| Dạng | Có phải exhaustive? | Ý nghĩa |
| --- | --- | --- |
| `switch` expression | **Bắt buộc** | Biểu thức phải cho kết quả hoặc hoàn tất bất thường; không được thiếu nhánh |
| Switch statement truyền thống trên `int`, `String`, `enum`, không có pattern/null case | **Không bắt buộc** | Có thể có đầu vào không thực thi nhánh nào |
| Enhanced switch statement (Java 21, có pattern/null case hoặc selector thuộc kiểu mở rộng) | **Bắt buộc** | Không được âm thầm bỏ qua trường hợp hợp lệ |
| `if / else if` | Không có cơ chế exhaustiveness tổng quát tương tự | Người viết phải thiết kế nhánh cuối phù hợp |

`switch expression` có thể dùng quy tắc mũi tên `->` hoặc nhóm nhãn dạng dấu hai chấm và `yield`. `yield` chuyển một giá trị ra khỏi switch expression:

```java
int score = switch (stage) {
    case NEW -> 0;
    case ACTIVE -> {
        int progress = 50;
        yield progress;
    }
    case DONE -> 100;
};
```

Đây là đoạn mã minh họa, giả định `Stage` và biến `stage` đã khai báo. Dùng `yield` trong block khi nhánh phải thực hiện nhiều câu lệnh trước khi tạo kết quả. Với cú pháp `->`, không xảy ra việc chạy xuyên xuống nhánh tiếp theo (fall-through) như các nhóm nhãn `case:` truyền thống.

## 3. Java quyết định “đủ case” như thế nào?

Theo Java Language Specification 21, một khối switch được xem là exhaustive nếu có một cách bao phủ toàn bộ **kiểu selector**. Những cách thường gặp:

1. Có nhánh `default` (hoặc trường hợp nhãn `case null, default`).
2. Với `enum`, liệt kê tất cả các hằng enum thuộc kiểu selector, không nhất thiết phải có `default`.
3. Với kiểu `sealed`, các mẫu không bị guard giới hạn có thể bao phủ tất cả các kiểu con được phép, xét theo cây kế thừa đã biết.
4. Có mẫu kiểu phù hợp **vô điều kiện với kiểu selector**, chẳng hạn `case Object obj` cho selector có kiểu `Object` (đối với các giá trị khác `null`).
5. Với các mẫu record, trình biên dịch xét các khả năng thành phần và sự bao phủ của tập mẫu; không thể tự coi một mẫu record sâu, chỉ khớp vài hình dạng con, là đủ cho mọi đầu vào.

`default` là lối thoát tổng quát dễ dùng, nhưng không phải lúc nào cũng là lựa chọn tốt nhất. Với `enum` và `sealed`, bỏ `default` có chủ đích sẽ giúp trình biên dịch nhắc bạn khi thêm giá trị hoặc kiểu con mới cần được xử lý.

Cần phân biệt **hai câu hỏi**:

- **Bao phủ kiểu:** với mọi giá trị **không phải `null`** thuộc selector, có nhánh nào phù hợp không?
- **Xử lý `null`:** nếu biểu thức selector là `null`, có `case null` phù hợp không? Nếu không, `switch` thường ném `NullPointerException`, ngay cả khi switch được chứng minh exhaustive về mặt kiểu.

Ví dụ mẫu tổng quát:

```java
Object value = 17;

String result = switch (value) {
    case Object anything -> "Value: " + anything;
};
```

Mã này được chấp nhận vì mẫu `Object anything` bao phủ các đối tượng khác `null` ở kiểu `Object`. Tuy nhiên, truyền `null` vào selector vẫn gây `NullPointerException` nếu không có `case null`.

## 4. Lỗi thiếu một giá trị enum

Cho:

```java
enum Status { NEW, RUNNING, DONE }
```

Đoạn sau là **ví dụ cố ý không biên dịch**:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        // Thiếu case DONE.
    };
}
```

Lỗi thường gặp từ `javac`:

```text
the switch expression does not cover all possible input values
```

Trình biên dịch không hỏi “với dữ liệu thử hiện tại có gặp DONE không?”. Nó nhìn thấy `Status` đã khai báo ba hằng và biểu thức chỉ bao phủ hai hằng. Dù ứng dụng hôm nay chỉ tạo `NEW` hoặc `RUNNING`, mã vẫn phải biên dịch hợp lệ với kiểu `Status`.

**Cách sửa 1 — Liệt kê đủ enum**, giúp bộ biên dịch nhắc khi enum được mở rộng:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        case DONE -> "Done";
    };
}
```

**Cách sửa 2 — Dùng `default`** khi nghiệp vụ thật sự muốn gom các giá trị còn lại:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        default -> "Other";
    };
}
```

Cách 2 hợp lệ, nhưng nếu sau này thêm `CANCELLED` vào enum, `default` có thể âm thầm trả `"Other"` thay vì buộc người bảo trì quyết định cách trình bày trạng thái mới. Với mô hình miền nghiệp vụ có tập giá trị đóng, thường nên liệt kê đủ để nhận cảnh báo khi mở rộng.

Không cần có một nhánh cho mọi **kết quả khác nhau**: nhiều enum constants có thể cùng dùng một nhãn `case` hoặc cùng tạo một kết quả. Điều bắt buộc là các khả năng thuộc kiểu selector được bao phủ.

## 5. Lỗi thiếu một kiểu trong sealed hierarchy

Trong Java, `sealed` giới hạn những lớp/record/interface nào có thể trực tiếp triển khai hoặc kế thừa một kiểu. Đây là cơ sở để trình biên dịch chứng minh `switch` trên hierarchy ấy có đủ nhánh kiểu.

```java
sealed interface Event permits Created, Cancelled, Paid {}

record Created(String orderId) implements Event {}
record Cancelled(String orderId, String reason) implements Event {}
record Paid(String orderId, int amount) implements Event {}
```

Một biểu thức **thiếu case**:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created " + id;
        case Cancelled(var id, var reason) -> "Cancelled " + id;
        // Thiếu Paid.
    };
}
```

Biên dịch thất bại vì `Paid` cũng là một kiểu được phép của `Event`. Sửa bằng cách thêm:

```java
case Paid(var id, var amount) -> "Paid " + id + " = " + amount;
```

Đoạn `case` bổ sung này là phần của switch trước đó, không phải lệnh Java độc lập. Khi đủ `Created`, `Cancelled`, `Paid`, trình biên dịch chứng minh switch exhaustive dù không có `default`.

**Khi nào không thể liệt kê hết?** Nếu hierarchy chứa một nhánh `non-sealed` hoặc kiểu selector là interface mở có thể nhận thêm các implementation, tập giá trị không còn được đóng hoàn toàn ở nhánh đó. Khi ấy cần một mẫu tổng quát hoặc `default` phù hợp. Với `sealed`, nên đọc đúng toàn bộ hierarchy, không chỉ các lớp bạn thường thấy trong dữ liệu thử.

### Rủi ro khi hierarchy thay đổi

Khi bổ sung một kiểu con được cho phép, việc **biên dịch lại** switch không có `default` có thể phát hiện nhánh còn thiếu, giúp cập nhật nghiệp vụ cùng lúc với mô hình. Nếu các thành phần được biên dịch ở các thời điểm khác nhau và hierarchy thay đổi sau khi mã switch đã biên dịch, một trường hợp bất ngờ tại runtime có thể dẫn đến `MatchException`. Vì thế exhaustiveness tại thời điểm biên dịch là bảo đảm dựa trên **phiên bản kiểu mà trình biên dịch đã thấy**, không thay thế việc quản lý tương thích nhị phân, đóng gói và triển khai đồng bộ.

## 6. Vì sao guarded pattern không tự bao phủ cả một kiểu?

Java 21 cho phép thêm `when` để ràng buộc điều kiện:

```java
case Paid(var id, var amount) when amount > 0 -> "Positive payment";
```

Đây **không phải** nhánh bao phủ toàn bộ kiểu `Paid`, vì `amount` có thể bằng 0 hoặc nhỏ hơn 0. Ví dụ sau **cố ý không biên dịch**:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) when amount > 0 -> "Positive payment";
        // Paid(0) và Paid(-1) không có nhánh.
    };
}
```

Bổ sung một mẫu `Paid` không có guard để xử lý phần còn lại:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) when amount > 0 -> "Positive payment";
        case Paid(var id, var amount) -> "Non-positive payment";
    };
}
```

Trình tự rất quan trọng: nhánh hẹp có `when` đứng trước nhánh rộng không có guard. Nếu đặt mẫu rộng trước, nó có thể che phủ nhánh hẹp (*dominated case*) và dẫn đến lỗi biên dịch hoặc nhánh không thể đạt được.

Về **exhaustiveness**, các nhánh có guard phụ thuộc dữ liệu thường không được tính là nhánh bao phủ đầy đủ. Java 21 có một ngoại lệ kỹ thuật là guard hằng `true` có thể được coi tương đương không guard; điều này không thay đổi lời khuyên thực hành: khi điều kiện nghiệp vụ có thể sai, hãy có nhánh xử lý còn lại.

## 7. Mẫu record lồng nhau có thể bỏ sót dữ liệu hợp lệ

Một mẫu record không chỉ kiểm tra kiểu record ngoài mà còn yêu cầu các mẫu thành phần bên trong khớp. Ví dụ:

```java
record Wrapper(Event event) {}
```

Đoạn sau **không exhaustive**:

```java
static String classify(Wrapper wrapper) {
    return switch (wrapper) {
        case Wrapper(Created(var id)) -> "Wrapped created " + id;
    };
}
```

`Wrapper` có thể chứa `Cancelled`, `Paid` hoặc thậm chí `event == null`. Mẫu `Wrapper(Created(...))` chỉ nhận một phần giá trị của `Wrapper`. Một `Wrapper` không bị `null` nhưng thành phần `event` lại bằng `null` sẽ **không khớp** mẫu record con `Created(...)`.

Sửa bằng cách đặt mẫu cụ thể trước và thêm mẫu nhận tất cả các thành phần còn lại:

```java
static String classify(Wrapper wrapper) {
    return switch (wrapper) {
        case Wrapper(Created(var id)) -> "Wrapped created " + id;
        case Wrapper(var other) -> "Another wrapper: " + other;
    };
}
```

Mẫu `Wrapper(var other)` xử lý các instance `Wrapper` khác, bao gồm trường hợp thành phần `event` bằng `null`. Nó **không** tự xử lý selector `wrapper == null`; muốn chấp nhận điều đó, thêm `case null` riêng.

Khi phân rã nhiều tầng, hãy kiểm tra từng nút có thể bị `null` hoặc thay đổi hình dạng. Nếu nghiệp vụ cần biết rõ lý do thiếu dữ liệu, có thể thay một mẫu sâu bằng nhiều case cụ thể hoặc giữ record trung gian để kiểm tra.

## 8. Selector kiểu mở: cần nhánh tổng quát

Nếu selector là `Object`, Java không thể suy ra chỉ có một vài lớp ứng dụng. Ví dụ dưới đây cố ý không biên dịch:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "Text: " + s;
        case Integer i -> "Number: " + i;
        // Vẫn có thể là Boolean, Long, List, hoặc nhiều kiểu khác.
    };
}
```

Một cách sửa:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "No value";
        case String s -> "Text: " + s;
        case Integer i -> "Number: " + i;
        default -> "Other object";
    };
}
```

`default` giải quyết mọi giá trị khác `null` chưa khớp các mẫu trước; `case null` đưa ra hành vi riêng cho đầu vào `null`. Nếu không cần tách `null`, chỉ có `default` vẫn đủ để switch **exhaustive về kiểu**, nhưng selector bằng `null` thông thường sẽ ném `NullPointerException`.

Một phương án khác dùng mẫu kiểu tổng quát:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "Text: " + s;
        case Integer i -> "Number: " + i;
        case Object any -> "Other object: " + any;
    };
}
```

Mẫu `Object any` bao phủ mọi đối tượng khác `null`. Không đặt mẫu đó trước các mẫu `String` hoặc `Integer`: mẫu tổng quát ở trước sẽ che phủ các mẫu cụ thể.

## 9. Exhaustive không đồng nghĩa với null-safe

Một trường hợp dễ nhầm:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) -> "Paid";
    };
}
```

Switch này exhaustive với các instance `Event` khác `null`, nhưng `describe(null)` sẽ ném `NullPointerException`. `null` là **giá trị tham chiếu vắng mặt**, không phải một implementation `Event` khác mà trình biên dịch buộc bạn liệt kê trong phép chứng minh exhaustive.

Nếu API cho phép đầu vào `null`, viết rõ:

```java
static String describe(Event event) {
    return switch (event) {
        case null -> "No event";
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) -> "Paid";
    };
}
```

Cả hai phiên bản đều exhaustive về kiểu; chỉ phiên bản thứ hai có nhánh xử lý `null`. Nếu hợp đồng API cấm `null`, cũng có thể kiểm tra ở đầu phương thức bằng `Objects.requireNonNull(event)` để lỗi rõ ràng, hoặc để switch ném NPE. Hãy chọn một hợp đồng nhất quán cho ứng dụng.

## 10. Ví dụ hoàn chỉnh, chạy được với Java 21+

Chương trình dưới đây kết hợp enum, sealed interface, record pattern, guard, `case null`, selector kiểu mở và record pattern lồng nhau. Lưu vào tệp **`ExhaustiveSwitchDemo.java`**.

```java
public class ExhaustiveSwitchDemo {
    enum Stage { NEW, ACTIVE, DONE }

    sealed interface Event permits Created, Cancelled, Paid {}
    record Created(String orderId) implements Event {}
    record Cancelled(String orderId, String reason) implements Event {}
    record Paid(String orderId, int amount) implements Event {}
    record Wrapper(Event event) {}

    // Exhausive vì đã liệt kê đủ ba enum constants.
    static String stageName(Stage stage) {
        return switch (stage) {
            case NEW -> "new";
            case ACTIVE -> "active";
            case DONE -> "done";
        };
    }

    // Exhaustive nhờ toàn bộ các kiểu con được phép của Event.
    static String describe(Event event) {
        return switch (event) {
            case Created(var id) -> "created:" + id;
            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
            case Paid(var id, var amount) ->
                    "paid:" + id + ":" + amount;
        };
    }

    // Việc cho phép null là quyết định riêng của API.
    static String withNull(Event event) {
        return switch (event) {
            case null -> "missing event";
            case Created(var id) -> "created:" + id;
            case Cancelled(var id, var reason) -> "cancelled:" + id;
            case Paid(var id, var amount) -> "paid:" + amount;
        };
    }

    // Guard chỉ phủ trường hợp amount > 0; cần case Paid còn lại.
    static String guarded(Event event) {
        return switch (event) {
            case Paid(var id, var amount) when amount > 0 ->
                    "positive:" + amount;
            case Paid(var id, var amount) ->
                    "non-positive:" + amount;
            case Created(var id) -> "created:" + id;
            case Cancelled(var id, var reason) -> "cancelled:" + id;
        };
    }

    // Object là kiểu mở; default xử lý các kiểu chưa liệt kê.
    static String inspect(Object value) {
        return switch (value) {
            case String s -> "text:" + s;
            case Integer number -> "int:" + number;
            case null -> "null";
            default -> "other";
        };
    }

    // Mẫu cụ thể đi trước, mẫu record rộng hơn đi sau.
    static String nested(Wrapper value) {
        return switch (value) {
            case Wrapper(Created(var id)) -> "wrapped-created:" + id;
            case Wrapper(var other) -> "wrapped-other:" + other;
        };
    }

    public static void main(String[] args) {
        System.out.println(stageName(Stage.ACTIVE));
        System.out.println(describe(new Created("A1")));
        System.out.println(describe(new Paid("B2", 500)));
        System.out.println(guarded(new Paid("B2", 500)));
        System.out.println(guarded(new Paid("B2", 0)));
        System.out.println(withNull(null));
        System.out.println(inspect(42));
        System.out.println(nested(new Wrapper(new Created("C3"))));
        System.out.println(nested(new Wrapper(null)));

        try {
            describe(null);
        } catch (NullPointerException e) {
            System.out.println("NPE on null selector");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac --release 21 -encoding UTF-8 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
```

Đầu ra chính xác:

```text
active
created:A1
paid:B2:500
positive:500
non-positive:0
missing event
int:42
wrapped-created:C3
wrapped-other:null
NPE on null selector
```

**Đọc kết quả:** `stageName` chứng minh bao phủ enum; `describe` chứng minh bao phủ toàn bộ các record được cho phép bởi sealed interface; `guarded` có nhánh cho cả số tiền dương và không dương; `withNull` phân biệt giá trị `null` với các loại `Event`; `inspect` có `default` cho kiểu mở; `nested` chứng minh một mẫu sâu cần mẫu rộng hơn để bao phủ những hình dạng `Wrapper` còn lại. Dòng cuối cùng được in bởi `catch` sau khi switch exhaustive gặp selector `null` mà không có `case null`.

## 11. Quy trình gỡ lỗi “does not cover all possible input values”

Khi trình biên dịch đánh dấu một switch expression là thiếu case, kiểm tra lần lượt:

1. **Xác định kiểu tĩnh của selector** (kiểu của biểu thức bên trong `switch(...)`): `enum`, `sealed`, `Object`, `String`, kiểu generic, hay interface mở? Không suy luận từ vài dữ liệu runtime.
2. **Nếu là enum:** liệt kê tất cả hằng. Kiểm tra hằng mới được thêm hoặc thay tên; không quên trường hợp chưa từng chạy trong test.
3. **Nếu là sealed:** xem toàn bộ hierarchy được phép ở cấu trúc khai báo. Với các nhánh không còn đóng, cần case tổng quát.
4. **Nếu có `when`:** hỏi điều kiện có thể sai không. Nếu có, thêm case không guard cho phần còn lại. Không xem một pattern có điều kiện là tương đương với tất cả giá trị của kiểu đó.
5. **Nếu dùng nested record patterns:** hỏi record con có thể là `null` hoặc thuộc hình dạng khác không; thêm mẫu record tổng quát hoặc phân nhánh theo từng tầng.
6. **Nếu selector là kiểu mở:** thêm `default` hoặc mẫu kiểu bao phủ phần còn lại; tránh đặt case tổng quát trước các case cụ thể.
7. **Xử lý `null` theo hợp đồng phương thức:** thêm `case null` nếu chấp nhận `null`; nhận biết việc này khác với sửa lỗi exhaustive về kiểu.
8. **Kiểm tra loại switch:** switch expression và enhanced switch statement phải exhaustive; switch statement truyền thống có quy tắc tương thích ngược.
9. **Đọc lỗi khác ngoài exhaustive:** nhánh có thể bị che phủ (*dominated case*), biến pattern không nằm trong phạm vi, guard sai kiểu, hoặc kiểu trả về các nhánh không tương thích. Thêm `default` sẽ không sửa những lỗi độc lập này.

Với cùng lỗi biên dịch, phương án sửa phù hợp có thể là thêm một case cụ thể, thêm nhánh xử lý guard thất bại, hoặc dùng nhánh tổng quát. **Không tự động thêm `default` cho mọi switch** nếu mục tiêu của mô hình là buộc nhà phát triển xử lý mọi trạng thái khi kiểu miền nghiệp vụ được mở rộng.

## 12. Bài tập tự kiểm tra

**Bài 1 — Enum thêm trạng thái.** `enum Stage { NEW, ACTIVE, DONE }` và switch expression liệt kê đúng ba hằng. Nếu thêm `PAUSED` rồi biên dịch lại mà không cập nhật switch, điều gì xảy ra? **Đáp án:** switch không còn exhaustive và trình biên dịch báo thiếu case nếu không có nhánh bao phủ `PAUSED`.

**Bài 2 — Guard chưa đủ.** Với `Paid(int amount)`, tại sao `case Paid(var amount) when amount > 0` chưa bao phủ `Paid`? **Đáp án:** vẫn còn `amount == 0` và `amount < 0`. Thêm `case Paid(var amount)` không guard hoặc một tập nhánh được chứng minh bao phủ toàn bộ.

**Bài 3 — Null và exhaustive.** Switch trên sealed `Event` có đủ ba case nhưng nhận `null`. Có phải lỗi thiếu case ở thời điểm biên dịch không? **Đáp án:** không; compiler chứng minh exhaustive cho các instance thuộc `Event`, còn `null` không có `case null` sẽ dẫn đến `NullPointerException`.

**Bài 4 — Bẫy record con.** `Wrapper(Created(...))` có xử lý tất cả `Wrapper` không? **Đáp án:** không. Thành phần `event` có thể là `Cancelled`, `Paid` hoặc `null`. Có thể thêm `Wrapper(var other)` ở sau để bao phủ phần còn lại.

**Bài 5 — Khi nào dùng default?** Với switch trên `Event` sealed có tập record đóng, nên ưu tiên gì khi muốn compiler nhắc lúc thêm loại event mới? **Đáp án:** liệt kê các kiểu con, tránh `default` chỉ để cho qua lỗi. Với selector là `Object` và mục đích xử lý mọi đối tượng bất kỳ, `default` hoặc mẫu tổng quát là lựa chọn phù hợp.

**Bài 6 — Statement hay expression?** Tại sao statement truyền thống `switch(stage) { case NEW -> ...; }` có thể biên dịch trong khi `return switch(stage) { case NEW -> ...; };` không? **Đáp án:** statement truyền thống được giữ khả năng không exhaustive vì tương thích ngược; biểu thức bắt buộc phải bao phủ mọi giá trị enum.

## 13. Ghi nhớ

- **Exhaustive** nghĩa là compiler chứng minh switch có nhánh áp dụng cho mọi khả năng thuộc kiểu selector (với cách xử lý `null` là một vấn đề riêng).
- **Enum:** liệt kê đủ hằng hoặc dùng nhánh tổng quát.
- **Sealed:** bao phủ toàn bộ các kiểu con liên quan; thêm kiểu mới có thể khiến code cũ thiếu case khi biên dịch lại.
- **`when`:** một guard có thể sai không tạo ra độ bao phủ toàn kiểu.
- **Record pattern:** mẫu lồng sâu có thể không khớp khi record con bằng `null` hay sai hình dạng; cần xử lý những trường hợp đó nếu có thể xảy ra.
- **Kiểu mở:** `default` hoặc một mẫu tổng quát giúp bao phủ phần còn lại.
- **`case null`:** đưa ra hành vi rõ khi selector bằng `null`, độc lập với tính exhaustive về kiểu.

**Tài liệu chính thức:** [Java Language Specification 21 — Exhaustive Switch Blocks (`14.11.1.1)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1), [JLS 21 — switch expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
