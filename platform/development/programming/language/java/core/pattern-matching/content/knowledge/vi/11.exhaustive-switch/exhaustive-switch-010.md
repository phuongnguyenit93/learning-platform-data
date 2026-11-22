# Thiết kế nhánh không thể xảy ra trong exhaustive switch Java

**Chủ đề:** Java Core Pattern Matching → *Exhaustive switch*. Tài liệu sử dụng **Java SE 21** (pattern matching for `switch` chính thức theo JEP 441), với các ví dụ có thể biên dịch bằng JDK 21 trở lên, không cần preview. Mục tiêu là thiết kế đúng các nhánh **“không thể xảy ra”**: khi nào *không nên viết nhánh dự phòng*, khi nào nên **ném lỗi có chủ đích**, và khi nào nhánh không được khớp ở runtime nhưng thực tế vẫn có rủi ro do thay đổi mã hoặc phiên bản thư viện.

## 1. “Không thể xảy ra” có ba nghĩa khác nhau

Khi viết `switch`, câu “trường hợp này không thể xảy ra” thường đang nói về **ba mức bảo đảm khác nhau**:

1. **Không thể xảy ra theo luật ngôn ngữ tại compile time.** Một nhãn bị nhãn trước *dominate* hoặc một câu lệnh hoàn toàn unreachable sẽ gây lỗi biên dịch. Không có chuyện “cứ để nhánh đó, compiler sẽ bỏ qua”.
2. **Không thể xảy ra theo mô hình kiểu tĩnh hiện tại.** Ví dụ một `enum` chỉ có ba constant, hoặc một `sealed interface` chỉ cho phép hai kiểu con. Một `switch` đã bao phủ đầy đủ có thể **không cần `default`**. Đây thường là lựa chọn tốt khi ta muốn trình biên dịch nhắc cập nhật code nếu mô hình phát triển.
3. **Không thể xảy ra theo giả định nghiệp vụ hoặc ở phiên bản mã hiện tại.** Ví dụ “mã đơn hàng không bao giờ rỗng”, “phần tử từ adapter này luôn là String”. Compiler **không tự chứng minh** các bất biến nghiệp vụ tùy ý. Với dữ liệu đến từ bên ngoài, nên có xử lý ngoại lệ rõ ràng. Hơn nữa, phần mềm chạy với các class không cùng phiên bản biên dịch có thể phá vỡ tính bao phủ mà compiler từng chấp nhận.

**Nguyên tắc tổng quát:** dựa vào compiler để loại bỏ những trạng thái *không thể có theo kiểu tĩnh*; dùng kiểm tra và lỗi rõ ràng cho trạng thái *có thể biểu diễn về mặt kiểu nhưng vi phạm hợp đồng*; không dùng `default` chỉ để che lỗi.

## 2. Exhaustiveness thực sự bảo đảm điều gì?

JLS `14.11.1.1 gọi một `switch` block là **exhaustive** khi nó bao phủ được kiểu của selector theo những quy tắc tĩnh cụ thể. Có thể đạt được bằng:

- Một nhãn `default`.
- Một nhãn tổng hợp `case null, default`.
- Một tập nhãn constant/pattern phù hợp, ví dụ liệt kê **mọi constant của enum**, các type pattern bao phủ những kiểu con được phép của `sealed`, hoặc một type pattern *unconditional* cho kiểu selector.

Một **`switch` expression** phải exhaustive. Từ Java 21, **enhanced `switch` statement** (chẳng hạn statement chứa pattern hoặc `case null`) cũng phải exhaustive. Nhưng một `switch` statement truyền thống chỉ dùng các hằng số `int`, `String` hoặc `enum` vẫn có thể không exhaustive vì lý do tương thích ngược.

**Exhaustive không có nghĩa không bao giờ ném ngoại lệ.** Nó cũng không khẳng định mọi dữ liệu nghiệp vụ đều hợp lệ. Nó là một bảo đảm **của hệ thống kiểu và tập nhãn tại thời điểm biên dịch**.

### Enum: tính bao phủ trên tập tên hữu hạn

```java
enum Phase { NEW, APPROVED, DECLINED }

static String phaseLabel(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

Đoạn trên hợp lệ: `switch` expression bao phủ toàn bộ enum `Phase` hiện có. Không cần thêm:

```java
// Không cần thiết khi cả ba enum constant đều đã được xử lý:
// default -> "unknown";
```

Nếu sửa enum thành `{ NEW, APPROVED, DECLINED, CANCELLED }` và **biên dịch lại cùng mã `phaseLabel`**, compiler phát hiện `switch` expression không còn exhaustive và yêu cầu xử lý `CANCELLED`.

**Lợi ích của việc bỏ `default` ở mô hình đóng:** một trạng thái mới buộc người viết quyết định cách xử lý thay vì âm thầm rơi vào nhánh chung.

### Sealed: dùng kiểu con để biểu diễn các trạng thái hợp lệ

```java
sealed interface Payment permits Cash, Card {}

record Cash(int amount) implements Payment {}

record Card(String token) implements Payment {}

static String describe(Payment payment) {
    return switch (payment) {
        case Cash c -> "cash:" + c.amount();
        case Card c -> "card:" + c.token();
    };
}
```

`Payment` chỉ cho phép hai kiểu con trực tiếp `Cash`, `Card` trong ví dụ. Hai type pattern bao phủ tất cả các hiện thực hợp lệ hiện tại; `switch` expression exhaustive mà không cần `default`. Nếu sau này mô hình được mở rộng thêm kiểu `BankTransfer` và code liên quan được biên dịch lại với hierarchy mới, compiler sẽ yêu cầu xét lại `describe`.

**Cẩn trọng:** không được suy luận “sealed” nghĩa là mọi lớp đều `final` trong mọi mô hình. Một permitted class có thể là `final`, `sealed` hoặc `non-sealed` theo quy tắc JLS; cách bao phủ phụ thuộc cấu trúc phân cấp thực tế. Ví dụ trên dùng hai record (mặc nhiên `final`), vì vậy tập trạng thái rất rõ ràng.

## 3. Không dùng default để che những trường hợp mới cần được xử lý

Một cách viết dễ qua compiler nhưng có nguy cơ che thay đổi:

```java
static String phaseWithCatchAll(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        default -> "other";
    };
}
```

Mã này biên dịch khi enum `Phase` có ba giá trị; `DECLINED` sẽ trả về `other`. Nếu `CANCELLED` được thêm sau, nó **cũng** trả về `other` mà compiler không yêu cầu cập nhật logic.

Điều đó hoàn toàn hợp lý **nếu yêu cầu nghiệp vụ cố ý nhóm các trạng thái còn lại là `other`**. Nhưng nó là thiết kế kém khi mọi trạng thái phải có cách xử lý riêng (chẳng hạn thanh toán, chuyển trạng thái nghiệp vụ, quyết định quyền truy cập).

So sánh:

| Mục tiêu thiết kế | Cách phù hợp | Lý do |
| --- | --- | --- |
| Tập trạng thái đóng, mọi trạng thái phải có xử lý riêng | Liệt kê đầy đủ case, **không dùng default** | Thêm enum constant/kiểu con mới → được kiểm tra lại khi recompile |
| Các trạng thái không liệt kê có cùng ý nghĩa thật sự | `default -> fallback` | Đây là một phần hợp đồng chứ không phải lối thoát tạm |
| Input kiểu `Object` từ hệ thống ngoài có thể bất kỳ | `default -> throw new IllegalArgumentException(...)` hoặc kết quả từ chối rõ ràng | Không có mô hình kiểu đóng để compiler bao phủ |
| Có bất biến nội bộ nhưng trạng thái lỗi vẫn biểu diễn được | Kiểm tra và `throw` trong nhánh phù hợp | Không âm thầm trả giá trị “có vẻ hợp lệ” |
| Muốn biểu thị lỗi lập trình thực sự không được phép xuất hiện | `throw new AssertionError(...)` tại điểm có chứng cứ | Đánh dấu vi phạm bất biến, không dùng làm nhánh nghiệp vụ thường xuyên |

Chú ý rằng **không phải lúc nào có thể thêm `default` vào mọi vị trí**. Trong `switch` có unguarded pattern *unconditional* đối với selector, một `default` đứng sau có thể bị *dominate* và gây lỗi biên dịch.

## 4. Nhánh thật sự bất thường nên fail fast thay vì nuốt lỗi

Giả sử adapter nhận `Object` từ một plug-in bên ngoài và ứng dụng chỉ chấp nhận chuỗi không blank hoặc số nguyên.

```java
static String fromBoundary(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when !text.isBlank() -> "text:" + text;
        case String text ->
                throw new IllegalArgumentException("blank-string");
        case Integer number -> "integer:" + number;
        default -> throw new IllegalArgumentException("unsupported");
    };
}
```

Đây là thiết kế có ý nghĩa rõ:

- `null` là đầu vào hợp lệ trong hợp đồng ví dụ, có kết quả riêng.
- Chuỗi không blank được nhận qua pattern có `when`.
- Chuỗi blank vẫn là `String` về mặt kiểu nhưng **không đạt điều kiện nghiệp vụ**, nên ném lỗi có giải thích.
- `Integer` được chấp nhận.
- Các kiểu khác (`Double`, `Boolean`, đối tượng bất kỳ) là dữ liệu ngoài hợp đồng; `default` **cần thiết** để bao phủ selector kiểu `Object`, và ném lỗi thay vì trả về một kết quả gây hiểu lầm.

Ở đây `default` **không phải** “nhánh không thể xảy ra” theo kiểu tĩnh: có vô số đối tượng không phải String hoặc Integer. Nó chỉ là trường hợp **không mong muốn** theo hợp đồng API — vì thế cần được xử lý có chủ đích.

### Chọn ngoại lệ phù hợp

- **`IllegalArgumentException`**: người gọi đưa vào đối số sai theo hợp đồng của phương thức, ví dụ kiểu dữ liệu/định dạng không được chấp nhận.
- **`IllegalStateException`**: đối tượng hoặc hệ thống đang ở trạng thái không hợp lệ cho thao tác hiện tại, dù kiểu Java của nó hợp lệ.
- **`AssertionError`**: khẳng định một trạng thái là không thể xảy ra theo bất biến nội bộ. Đây là một `Error` cho lỗi lập trình/bất biến rất nghiêm trọng; không nên dùng để phản hồi dữ liệu sai thông thường từ người dùng.
- **`MatchException`**: Java có thể tự ném khi một `switch` exhaustive ở compile time nhưng tại runtime không nhãn nào áp dụng. Thông thường **không** cần tự ném ngoại lệ này để thay cho thông báo nghiệp vụ.

Không có luật bắt buộc mọi “unexpected value” phải ném cùng một ngoại lệ; chọn theo bản chất lỗi và hợp đồng của API.

## 5. `default -> throw new AssertionError(...)`: khi nào hữu ích và khi nào phản tác dụng?

Trong mã legacy hoặc API có giới hạn kiểu chưa đủ chặt, đôi khi dùng một nhánh phòng thủ:

```java
static String defensive(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
        default -> throw new AssertionError("Unexpected phase: " + phase);
    };
}
```

Đoạn này hợp lệ, và với ba trạng thái enum hiện tại nhánh `default` không được chọn cho giá trị khác null. Nhưng có một **đánh đổi quan trọng**:

- Nếu thêm enum constant `CANCELLED`, nhánh `default` **đã có sẵn** nên recompile **không buộc** sửa phương thức.
- Giá trị mới sẽ rơi vào `default` và ném `AssertionError` khi chạy. Tức là lỗi đáng lẽ có thể được phát hiện **sớm tại compile time** giờ mới xuất hiện **tại runtime**.
- Vì vậy với enum/sealed hierarchy do ứng dụng kiểm soát, nếu mục đích là buộc xem xét mọi subtype mới, **ưu tiên không có `default`** và để compiler phát hiện thay đổi.

Một nhánh `default` ném lỗi vẫn có thể hữu ích ở **ranh giới mở** hoặc khi contract yêu cầu từ chối các giá trị chưa hỗ trợ, nhưng hãy cân nhắc dùng `IllegalArgumentException`/`IllegalStateException` thay vì `AssertionError` cho dữ liệu đến từ bên ngoài.

**Không dùng `assert false` làm xử lý bắt buộc cho nhánh bất thường:**

```java
// Không dùng như cơ chế fail-fast bắt buộc:
// default -> {
//     assert false : "unreachable";
//     yield "fallback";
// }
```

Java assertions có thể **bị tắt theo mặc định** nếu không bật `-ea`. Khi tắt, mã trên sẽ trả `fallback` và âm thầm bỏ qua lỗi. Nếu đã quyết định tình huống phải kết thúc bằng lỗi, dùng `throw` rõ ràng.

## 6. Null là một đường đi riêng: exhaustive không đồng nghĩa null-safe

Một `switch` expression trên `enum` hoặc `sealed interface` có thể exhaustive **mà vẫn ném `NullPointerException`** khi selector là `null`:

```java
static String state(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

`state(null)` ném `NullPointerException` vì không có nhãn `case null`. `default` đơn lẻ cũng không tự bắt selector null trong Java 21.

Nếu null là **lỗi hợp đồng**, có thể nói rõ tại đầu phương thức:

```java
static String requireState(Phase phase) {
    java.util.Objects.requireNonNull(phase, "phase");
    return switch (phase) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

Hoặc đặt lỗi ngay trong `switch`:

```java
static String requireState2(Phase phase) {
    return switch (phase) {
        case null -> throw new IllegalArgumentException("phase-required");
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

Hai cách thể hiện **hai quyết định về loại ngoại lệ** khác nhau. Dùng `Objects.requireNonNull` thông thường cho `NullPointerException`; dùng `case null -> throw ...` nếu chủ động chọn kiểu ngoại lệ khác hoặc cần xử lý null trong cấu trúc switch. Nếu null là trạng thái hợp lệ, có thể `case null -> "unknown"`.

### Vì sao `case Object x` cũng không tự bắt null?

```java
static String category(Object value) {
    return switch (value) {
        case Object x -> "non-null object";
    };
}
```

Type pattern `Object x` là unconditional cho những giá trị `Object` khác null, nên expression này exhaustive về kiểu tĩnh. Nhưng `category(null)` vẫn ném NPE. Muốn xử lý null, cần thêm `case null`. Tính exhaustive và chính sách null là hai câu hỏi riêng.

## 7. Nhánh bị dominate không phải nhánh “để phòng hờ”

Một nhãn `case` có thể bị coi là **dominated** nếu trình biên dịch xác định mọi giá trị mà nó có thể nhận đã được một nhãn đứng trước bao phủ. Java 21 báo lỗi thay vì âm thầm để mã đó chờ chạy.

```java
// KHÔNG BIÊN DỊCH:
static String dominated(Object input) {
    return switch (input) {
        case Object any -> "object";
        case String text -> "string"; // Bị Object any dominate.
    };
}
```

`Object any` đã khớp mọi tham chiếu khác null kiểu `Object`. Nhãn `String` sau đó không thể được chọn. Thứ tự đúng nếu muốn phân biệt chuỗi:

```java
static String ordered(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "string:" + text;
        case Object any -> "object";
    };
}
```

Nhãn `Object any` bây giờ ở cuối, đóng vai trò bao phủ các giá trị khác null còn lại và làm `switch` expression exhaustive.

### Guard không phải nhánh vô điều kiện

```java
static String classifyNumber(Object input) {
    return switch (input) {
        case Integer n when n < 0 -> "negative";
        case Integer n -> "other integer";
        case null -> "null";
        default -> "other";
    };
}
```

Nhánh có guard đứng trước hợp lệ, vì guard `n < 0` có thể sai. Đảo thứ tự và để `case Integer n` không guard lên trước sẽ khiến nhánh guard phía sau bị dominate.

**Không giả định compiler chứng minh mọi biểu thức nghiệp vụ.** Hai guard `n < 0` và `n >= 0` về mặt toán học phân chia toàn bộ số nguyên, nhưng compiler không dùng các chứng minh tùy ý như vậy để coi tập pattern đã exhaustive. Thêm một nhánh không guard thích hợp khi cần tính exhaustive. Guard `when true` là trường hợp đặc biệt mà JLS xem như không guard; guard hằng `when false` không hợp lệ.

### Reachability khác với dominance

Hai đoạn lỗi có bản chất khác nhau:

```java
// KHÔNG BIÊN DỊCH: unreachable statement.
static void afterReturn() {
    return;
    // System.out.println("never"); // Nếu bỏ comment: unreachable statement.
}
```

```java
// KHÔNG BIÊN DỊCH: dominated switch label.
static String wrongOrder(Object input) {
    return switch (input) {
        case Object any -> "any";
        case String s -> "string";
    };
}
```

**Reachability** của statement được xét theo JLS `14.22; **dominance** của switch label được xét trong JLS `14.11.1. Cả hai đều có thể gây lỗi biên dịch, nhưng không phải cùng một quy tắc và không được giải quyết bằng cách thêm `default` hoặc đặt một nhánh “impossible” mới.

## 8. Runtime: trạng thái “không thể xảy ra” vẫn có thể xuất hiện do biên dịch riêng

Đây là lý do không được coi exhaustiveness là bảo đảm tuyệt đối bất biến qua mọi phiên bản triển khai.

Giả sử ứng dụng được biên dịch khi mô hình chỉ có:

```java
sealed interface Payment permits Cash, Card {}
record Cash(int amount) implements Payment {}
record Card(String token) implements Payment {}
```

Một hàm phân nhánh trên hai subtype `Cash`/`Card` không cần `default`. Sau này thư viện được cập nhật để `Payment` cho phép thêm `Transfer`, nhưng module chứa `switch` **không được biên dịch lại**. Khi runtime đưa `Transfer` vào mã cũ, không có nhãn nào phù hợp với đối tượng khác null.

Trong Java 21, một `switch` expression (hoặc enhanced `switch` statement) được xem exhaustive lúc biên dịch nhưng không tìm thấy nhãn phù hợp lúc chạy có thể ném **`java.lang.MatchException`**. Điều này cũng có thể xảy ra khi enum có constant mới hoặc phân cấp kiểu thay đổi giữa các module được biên dịch riêng.

**Phân biệt ba trường hợp lỗi:**

| Tình huống | Hành vi tiêu biểu trong Java 21 |
| --- | --- |
| Selector null, không có `case null` | `NullPointerException` |
| Selector khác null nhưng exhaustive switch không còn nhãn phù hợp do runtime hierarchy khác khi compile | `MatchException` |
| Nhãn `default -> throw new IllegalArgumentException(...)` được chọn | Ngoại lệ do chính ứng dụng chủ động ném |
| Nhánh bị dominate hoặc switch expression không exhaustive tại compile time | Lỗi biên dịch, không chạy |

Hướng xử lý đúng khi gặp `MatchException` do thay đổi mô hình là **đồng bộ phiên bản, biên dịch lại mã phụ thuộc và cập nhật nhánh xử lý**. Không nên biến nó thành một lỗi “không có gì” hoặc luôn trả fallback để che thay đổi hợp đồng.

Đây cũng là lý do cần có các bài kiểm thử tương thích giữa module hoặc giữa bản phát hành khi sealed hierarchy/enum được thay đổi.

## 9. Switch expression và switch statement: đừng nhầm yêu cầu exhaustive

### Switch expression: không được thiếu trường hợp cần bao phủ

```java
// KHÔNG BIÊN DỊCH: selector Object có nhiều giá trị khác String.
static String incomplete(Object value) {
    return switch (value) {
        case String text -> text;
    };
}
```

Compiler yêu cầu bao phủ phần còn lại. Khi selector là `Object` mở, có thể thêm `default -> throw ...` nếu ứng dụng không hỗ trợ các kiểu khác.

### Enhanced switch statement: cũng phải exhaustive

```java
// KHÔNG BIÊN DỊCH trong Java 21:
static void incompleteStatement(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
    }
}
```

Đây là enhanced `switch` statement chứa pattern; phải thêm nhãn đủ bao phủ, chẳng hạn:

```java
static void completeStatement(Object value) {
    switch (value) {
        case null -> throw new IllegalArgumentException("missing");
        case String text -> System.out.println(text);
        default -> throw new IllegalArgumentException("unsupported");
    }
}
```

### Legacy switch statement: có thể không exhaustive

```java
static void legacyEnumStatement(Phase phase) {
    switch (phase) {
        case NEW -> System.out.println("created");
        // APPROVED và DECLINED không có nhánh.
    }
}
```

Đây là kiểu statement với selector enum và case constant truyền thống, **không phải enhanced statement**. Java vẫn cho phép nó không exhaustive vì tương thích ngược. Với `APPROVED` hoặc `DECLINED`, không nhãn nào áp dụng và statement kết thúc bình thường mà không in gì. Khi thiết kế luồng nghiệp vụ quan trọng, nếu cần bắt buộc xử lý đầy đủ, dùng `switch` expression hoặc mô hình dữ liệu/tính toán khiến lỗi thiếu nhánh bị compiler phát hiện.

**Không nhầm `switch` statement và `switch` expression.** Expression phải tạo giá trị (hoặc ném ngoại lệ) và luôn chịu kiểm tra exhaustive; statement có thể có hành vi thực thi lệnh mà không tạo giá trị.

## 10. Chương trình Java 21 hoàn chỉnh

Tạo tệp **`ImpossibleBranchDemo.java`** với toàn bộ nội dung sau:

```java
public class ImpossibleBranchDemo {
    // Tập kiểu con hợp lệ hiện tại là đóng.
    sealed interface Payment permits Cash, Card {}

    record Cash(int amount) implements Payment {}
    record Card(String token) implements Payment {}

    enum Phase { NEW, APPROVED, DECLINED }

    // Bao phủ enum theo tên, không cần default.
    static String phaseLabel(Phase phase) {
        return switch (phase) {
            case null -> throw new IllegalArgumentException("phase-required");
            case NEW -> "new";
            case APPROVED -> "approved";
            case DECLINED -> "declined";
        };
    }

    // Bao phủ sealed hierarchy theo type pattern, không cần default.
    static String describe(Payment payment) {
        return switch (payment) {
            case null -> throw new IllegalArgumentException("payment-required");
            case Cash c -> "cash:" + c.amount();
            case Card c -> "card:" + c.token();
        };
    }

    // Biên dữ liệu mở: dùng default để từ chối kiểu ngoài hợp đồng.
    static String fromBoundary(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text when !text.isBlank() -> "text:" + text;
            case String text -> throw new IllegalArgumentException("blank-string");
            case Integer number -> "integer:" + number;
            default -> throw new IllegalArgumentException("unsupported");
        };
    }

    // Ví dụ phòng thủ: default vẫn hợp lệ, nhưng có đánh đổi.
    static String defensive(Phase phase) {
        return switch (phase) {
            case null -> "null";
            case NEW -> "new";
            case APPROVED -> "approved";
            case DECLINED -> "declined";
            default -> throw new AssertionError("Unexpected phase " + phase);
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Cash(120)));
        System.out.println(describe(new Card("T9")));
        System.out.println(phaseLabel(Phase.NEW));
        System.out.println(fromBoundary(null));
        System.out.println(fromBoundary("Java"));
        System.out.println(fromBoundary(7));

        try {
            fromBoundary(" ");
        } catch (IllegalArgumentException e) {
            System.out.println("bad:" + e.getMessage());
        }

        try {
            fromBoundary(3.14);
        } catch (IllegalArgumentException e) {
            System.out.println("bad:" + e.getMessage());
        }

        try {
            describe(null);
        } catch (IllegalArgumentException e) {
            System.out.println("bad:" + e.getMessage());
        }

        System.out.println(defensive(Phase.DECLINED));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 ImpossibleBranchDemo.java
java ImpossibleBranchDemo
```

**Kết quả chuẩn:**

```text
cash:120
card:T9
new
missing
text:Java
integer:7
bad:blank-string
bad:unsupported
bad:payment-required
declined
```

**Giải thích:**

1. `Cash` và `Card` được phân biệt bởi type pattern trên sealed hierarchy. Không có `default` để che việc bổ sung subtype mới.
2. `Phase.NEW` có nhãn enum, trả `new`.
3. `fromBoundary(null)` vào nhãn null riêng; `"Java"` khớp guard không blank; `7` khớp type pattern Integer.
4. `" "` là String nhưng blank nên đi vào nhãn String không guard và ném `IllegalArgumentException("blank-string")`; không được xem là “không thể là String”.
5. `3.14` là Double và không khớp các pattern hỗ trợ, nên `default` ném `IllegalArgumentException("unsupported")`.
6. `describe(null)` chủ động ném lỗi hợp đồng thanh toán thiếu; khác với NPE ngầm khi thiếu null label.
7. `defensive(Phase.DECLINED)` vẫn trả `declined`. Nhánh `default -> throw AssertionError` hôm nay không chạy với ba enum constant, nhưng nếu enum đổi trong tương lai, nó có thể ngăn compiler nhắc cập nhật nhánh.

Chương trình này không minh họa `MatchException` bằng cách tự tạo hierarchy lỗi. Vì `MatchException` liên quan đến **mã compile riêng ở các phiên bản không đồng bộ**, phải tổ chức một thử nghiệm biên dịch nhiều phiên bản thật sự mới tái hiện chính xác; không nên ngụy tạo ngoại lệ bằng cách `throw new MatchException(...)` rồi coi đó là hành vi tự nhiên của `switch`.

## 11. Thiết kế kiểm thử cho nhánh bất thường

Một bộ kiểm thử tốt phải kiểm tra cả đường đúng và đường vi phạm:

- **Mọi trạng thái hợp lệ của enum:** mỗi `Phase` đều trả đúng nhãn.
- **Mọi subtype hợp lệ của sealed:** `Cash` và `Card` được nhận, pattern variable có dữ liệu đúng.
- **Null:** thử trực tiếp `phaseLabel(null)` và `describe(null)`; xác minh loại ngoại lệ và thông điệp mong đợi.
- **Biên dữ liệu mở:** thử String có nội dung, String blank, Integer, một kiểu chưa hỗ trợ (ví dụ Double), và null.
- **Quy tắc lỗi:** dữ liệu bất thường phải gây lỗi rõ ràng, không bị chuyển thành giá trị nghiệp vụ hợp lệ.
- **Thay đổi mô hình:** trong CI, recompile module chứa `switch` khi thêm enum constant hoặc sealed subtype; ưu tiên bắt lỗi compile thay vì chỉ kiểm thử runtime.
- **Thư viện đa phiên bản:** nếu hệ thống tải module đã biên dịch riêng, kiểm thử tích hợp giữa các phiên bản để phát hiện `MatchException` hoặc thay đổi hợp đồng không tương thích.

Không nên viết test chỉ để “đi vào nhánh bất khả thi” bằng reflection/bytecode bất thường nếu đó không phải rủi ro thực tế của ứng dụng. Test cần chứng minh **hợp đồng** và **quy trình quản lý thay đổi** hơn là tạo ra trạng thái giả tạo.

### Kiểm tra bằng compiler là một bài test thiết kế

Nếu thêm `CANCELLED` vào enum `Phase` rồi biên dịch lại phương thức `phaseLabel` **không có default**, việc compiler yêu cầu cập nhật là dấu hiệu tốt. Nếu phương thức dùng `default`, compiler có thể không báo và chỉ khi chạy mới thấy lỗi hoặc fallback.

Tương tự, nếu đổi `Payment` thành `permits Cash, Card, Transfer` và biên dịch lại mã `describe` không có default, compiler giúp chỉ ra nơi cần bổ sung xử lý subtype `Transfer`.

## 12. Những lỗi thường gặp

**Lỗi 1 — luôn thêm `default` cho chắc.** Với một enum/sealed model đóng có yêu cầu xử lý riêng từng trường hợp, `default` có thể che việc bổ sung trạng thái mới và làm mất kiểm tra exhaustive hữu ích.

**Lỗi 2 — dùng `default -> null`, `default -> false` hoặc `default -> ""` để “không crash”.** Điều này biến dữ liệu bất thường thành kết quả có vẻ hợp lệ, khó theo dõi lỗi và có thể tạo hành vi nghiệp vụ sai. Chỉ dùng fallback khi hợp đồng thật sự cho phép.

**Lỗi 3 — dùng `assert false` để báo lỗi bắt buộc.** Java assertions có thể bị tắt; dùng `throw` rõ ràng cho trường hợp phải thất bại.

**Lỗi 4 — cho rằng exhaustive xử lý luôn null.** `null` không khớp các type pattern ở selector ngoài. Không có `case null` thì một `switch` exhaustive vẫn có thể ném NPE.

**Lỗi 5 — nhầm guard với exhaustiveness.** Các nhánh `when` chỉ khớp khi guard đúng. Không dựa vào các điều kiện động “bù nhau” để compiler suy ra exhaustive; dùng nhãn không guard thích hợp.

**Lỗi 6 — giữ nhãn đã bị dominate như một “nhánh dự phòng”.** Java 21 báo lỗi biên dịch với dominated switch label. Hãy sắp nhánh cụ thể trước, tổng quát sau.

**Lỗi 7 — đồng nhất lỗi nguồn với lỗi runtime.** Nhánh không exhaustive có thể bị compiler chặn; một `MatchException` do class hierarchy thay đổi giữa compile time/runtime lại xảy ra khi chương trình đang chạy.

**Lỗi 8 — dùng `AssertionError` cho mọi đầu vào sai.** Input từ người gọi hay hệ thống ngoài nên được mô tả bằng hợp đồng và lỗi tương ứng; `Error` dành cho vi phạm bất biến lập trình nghiêm trọng, không phải lựa chọn mặc định cho validation.

**Lỗi 9 — không recompile các module phụ thuộc khi enum/sealed hierarchy thay đổi.** Kiểu được xem exhaustive trong mã cũ không tự cập nhật nhánh trong bytecode đã biên dịch. Cần quản lý binary compatibility và test tích hợp.

**Lỗi 10 — đánh đồng switch expression với legacy switch statement.** Enhanced statement và expression yêu cầu exhaustive trong Java 21, nhưng statement truyền thống với enum constants vẫn có thể kết thúc bình thường khi không nhãn nào khớp.

## 13. Bài tập và đáp án

### Bài tập A — nên có default không?

Với:

```java
enum Direction { NORTH, SOUTH }

static int sign(Direction direction) {
    return switch (direction) {
        case NORTH -> 1;
        case SOUTH -> -1;
    };
}
```

Nếu thêm `EAST`, điều gì xảy ra khi biên dịch lại? Nếu thêm `default -> 0` trước khi thay enum thì sao?

**Đáp án:** Khi recompile mà không có default, biểu thức không còn exhaustive và compiler yêu cầu xử lý `EAST`. Nếu đã có default, compiler không buộc bổ sung nhánh, `EAST` sẽ trả `0`. Cách nào tốt phụ thuộc `0` có thực sự là kết quả đúng cho hướng mới hay không; nếu không, tránh default.

### Bài tập B — phát hiện bất biến bị phá vỡ

Một adapter nhận `Object x` nhưng chỉ chấp nhận `String` không blank. Chọn cách viết thích hợp.

```java
static String requireText(Object x) {
    return switch (x) {
        case String s when !s.isBlank() -> s;
        case String s -> throw new IllegalArgumentException("blank");
        case null -> throw new IllegalArgumentException("missing");
        default -> throw new IllegalArgumentException("not-string");
    };
}
```

**Đáp án:** Phương thức exhaustive cho kiểu `Object` nhờ `default`, nhưng không nuốt lỗi. Null, blank và sai kiểu được phân loại rõ ràng. `when` không thay thế nhánh String không guard vì chuỗi blank còn tồn tại.

### Bài tập C — lỗi nào thuộc compiler?

```java
// KHÔNG BIÊN DỊCH:
static String wrong(Object x) {
    return switch (x) {
        case Object any -> "object";
        case String text -> "text";
    };
}
```

**Đáp án:** `case String text` bị nhãn `Object any` đứng trước dominate. Đây là **compile-time error**, không phải case “runtime không bao giờ chạy”. Đổi thứ tự hai pattern để sửa.

### Bài tập D — null trong exhaustive switch

```java
static String name(Phase p) {
    return switch (p) {
        case NEW -> "new";
        case APPROVED -> "approved";
        case DECLINED -> "declined";
    };
}
```

**Đáp án:** `name(null)` ném NPE. Tính exhaustive của các enum constant không bao gồm một chính sách xử lý null. Dùng `case null` hoặc `Objects.requireNonNull` nếu muốn nói rõ hành vi mong đợi.

### Bài tập E — MatchException

Một class chứa `switch` exhaustive trên `sealed interface` được biên dịch ở phiên bản A. Sang phiên bản B, hierarchy cho phép thêm một subtype nhưng module chứa `switch` không được recompile. Mã cũ nhận đối tượng subtype mới sẽ gặp tình huống nào?

**Đáp án:** Nếu không nhãn nào áp dụng cho selector khác null, `switch` có thể ném `MatchException` theo Java 21, dù khi biên dịch ở phiên bản A compiler đã chấp nhận là exhaustive. Cần đồng bộ/recompile và xử lý subtype mới, không mặc nhiên coi lỗi này là dữ liệu sai mà nên bỏ qua.

### Bài tập F — chọn kiểu exception

Phân loại ba tình huống: (1) client gửi kiểu đầu vào không được API chấp nhận; (2) đơn hàng đã `CANCELLED` nhưng hệ thống cố gửi hàng; (3) logic nội bộ bảo đảm một nhánh `default` không thể được chọn nhưng nó vẫn được chọn.

**Đáp án tham khảo:** (1) `IllegalArgumentException`; (2) `IllegalStateException`; (3) `AssertionError` nếu đó thực sự là vi phạm bất biến lập trình nghiêm trọng. Đây là lựa chọn thiết kế, không phải yêu cầu cú pháp bắt buộc của Java.

## 14. Checklist thực hành

Trước khi thêm một nhánh “không thể xảy ra”, hãy tự trả lời:

1. **Tập trạng thái đóng hay mở?** Enum/sealed do mình kiểm soát hay `Object` nhận dữ liệu từ bên ngoài?
2. **Có thể liệt kê đủ trạng thái hợp lệ mà không dùng default không?** Nếu có, recompile giúp phát hiện thay đổi kiểu.
3. **Compiler sẽ báo lỗi gì?** Nhãn dominated/unreachable? Switch expression chưa exhaustive? Đây là các lỗi thiết kế cần sửa ở mã nguồn, không phải “nhánh dự phòng”.
4. **Null có được phép không?** Định nghĩa chính sách `case null`, kiểm tra trước switch hoặc để NPE theo hợp đồng.
5. **Các guard có thể sai không?** Bố trí unguarded pattern hoặc fallback để thật sự exhaustive.
6. **Trường hợp bất thường là vi phạm hợp đồng hay bug nội bộ?** Chọn `IllegalArgumentException`, `IllegalStateException` hoặc `AssertionError` một cách có lý do.
7. **Có nên fail fast không?** Nếu giá trị không được phép, thường tốt hơn ném lỗi rõ ràng thay vì trả một giá trị trông có vẻ đúng.
8. **Có thay đổi runtime độc lập với compile time không?** Nếu có, kiểm tra tương thích module và rủi ro `MatchException`.
9. **Đã test đường đúng và đường lỗi chưa?** Test giá trị enum, subtype sealed, null, kiểu ngoài hợp đồng, guard sai và tích hợp giữa phiên bản.
10. **Nếu mai có trạng thái mới, ai bị buộc cập nhật logic?** Đây là câu hỏi quyết định có nên viết `default` hay không.

**Tóm lại:** với dữ liệu đóng, hãy tận dụng **exhaustive switch không cần default** để compiler bảo vệ thiết kế. Với biên dữ liệu mở, dùng nhánh dự phòng nhưng **xử lý bất thường rõ ràng, thường bằng ngoại lệ**. Đừng xem `default` là “bảo hiểm miễn phí”, cũng đừng tin rằng exhaustiveness đã chứng minh mọi trạng thái runtime và nghiệp vụ đều không thể sai.

## Tài liệu chính thức

- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): quy tắc bao phủ type, enum và sealed hierarchy.
- [JLS Java SE 21 `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): dominance, case label và guard.
- [JLS Java SE 21 `14.11.3 — Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): null, enhanced statement và lỗi runtime khi không nhãn nào áp dụng.
- [JLS Java SE 21 `15.28.2 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2): `NullPointerException` và `MatchException`.
- [JLS Java SE 21 `14.22 — Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.22): phân biệt reachability với dominance của nhãn.
- [Java SE 21 API — java.lang.MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): nguyên nhân một exhaustive match có thể thất bại tại runtime.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng ổn định trong Java 21.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mô hình tập subtype đóng.
