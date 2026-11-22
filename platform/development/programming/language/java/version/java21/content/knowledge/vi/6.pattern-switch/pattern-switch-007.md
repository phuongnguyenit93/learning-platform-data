# Thứ tự đánh giá pattern và guard

Trong Java 21, pattern matching for `switch` cho phép một nhánh kiểm tra kiểu, cấu trúc record và điều kiện bổ sung. Khi nhiều nhánh có thể phù hợp với cùng một giá trị, thứ tự khai báo và kết quả của guard quyết định nhánh nào được chọn.

Hiểu đúng thứ tự đánh giá giúp tránh nhánh tổng quát che mất nhánh cụ thể, biết khi nào guard được chạy và dự đoán chính xác hành vi khi một pattern hoặc guard không khớp. Nội dung dưới đây dùng cú pháp đã hoàn thiện trong Java 21 (JEP 441), không yêu cầu bật Preview.

## 1. Trình tự tổng quát của một switch pattern

Với switch expression hoặc switch statement dùng arrow rules (`case ... ->`), có thể hình dung trình tự như sau:

1. Java đánh giá biểu thức selector đúng một lần để lấy giá trị cần phân loại.
2. Nếu giá trị là `null`, Java xử lý nhãn `case null` theo quy tắc riêng. Nếu không có nhãn này, switch ném `NullPointerException`, kể cả khi có `default`.
3. Với giá trị không null, các nhãn `case` được xét theo thứ tự xuất hiện trong switch block.
4. Với nhãn có pattern, Java kiểm tra giá trị có khớp pattern hay không. Nếu không khớp, chuyển sang nhãn tiếp theo.
5. Nếu pattern khớp và nhãn có guard `when`, Java đánh giá guard. Guard trả về `true` thì chọn nhánh; trả về `false` thì tiếp tục xét nhãn tiếp theo.
6. Khi tìm được nhãn phù hợp, Java thực hiện nhánh đó. Với arrow rules, switch không tự rơi tiếp xuống nhánh kế tiếp.

Đây là thứ tự xét ở runtime. Compiler còn kiểm tra các quy tắc như dominance để phát hiện một số nhãn chắc chắn không thể được chọn.

## 2. Selector được đánh giá một lần

Biểu thức đặt trong `switch (...)` được đánh giá một lần trước khi xét các nhãn. Việc chuyển từ nhãn này sang nhãn khác không gọi lại biểu thức selector.

```java
static Object readNextValue() {
    System.out.println("read selector");
    return "Java 21";
}

static String describeNextValue() {
    return switch (readNextValue()) {
        case String text -> "text: " + text;
        case Integer number -> "number: " + number;
        default -> "other";
    };
}
```

Khi gọi `describeNextValue()`, dòng `read selector` chỉ được in một lần. Vì vậy, nên tránh đặt trong selector một biểu thức có tác dụng phụ khó dự đoán; nếu cần, hãy tính giá trị trước rồi truyền biến vào `switch`.

## 3. Các nhãn được xét theo thứ tự từ trên xuống

Khi một giá trị khớp một nhãn, các nhãn phía sau không được xét nữa. Vì vậy, hãy đặt nhánh cụ thể trước nhánh tổng quát.

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "text";
        case Integer number -> "integer";
        default -> "other";
    };
}
```

Ví dụ, nếu đặt `case Object object` trước `case String text`, nhánh `Object` sẽ bao phủ mọi giá trị không null và nhãn `String` phía sau bị compiler báo lỗi vì đã bị nhãn trước chi phối (dominated).

```java
// Không hợp lệ: case Object bao phủ mọi String không null.
static String invalidOrder(Object value) {
    return switch (value) {
        case null -> "null";
        case Object object -> "object";
        // case String text -> "text"; // bị dominated
    };
}
```

Thứ tự cũng quan trọng giữa các kiểu trong cùng một hierarchy. Với `Number` và `Integer`, đặt `Integer` trước `Number` để giá trị nguyên được xử lý bởi nhánh chuyên biệt.

```java
static String describeNumber(Number value) {
    return switch (value) {
        case null -> "null";
        case Integer number -> "integer: " + number;
        case Number number -> "number: " + number;
    };
}
```

Ví dụ trên đã xử lý `null` bằng `case null`. Nhánh `Number` là nhánh tổng quát cho các giá trị `Number` còn lại sau khi `Integer` đã được xét.

## 4. Guard `when` chỉ được đánh giá sau khi pattern khớp

Guard là biểu thức boolean đặt sau pattern bằng từ khóa `when`. Java chỉ đánh giá guard khi giá trị đã khớp pattern của nhãn đó. Nếu guard trả về `false`, switch tiếp tục xét nhãn kế tiếp.

```java
static String classifyText(String text) {
    return switch (text) {
        case null -> "null";
        case String value when value.isBlank() -> "blank";
        case String value when value.length() < 8 -> "short";
        case String value -> "long";
    };
}
```

Với chuỗi rỗng hoặc chỉ có khoảng trắng, nhánh `blank` được chọn. Với chuỗi không trống có ít hơn 8 ký tự, guard đầu tiên sai, guard thứ hai đúng và nhánh `short` được chọn. Các chuỗi còn lại đi đến nhánh `long`.

Thứ tự hai nhánh có guard làm thay đổi kết quả. Nếu đặt nhánh `length() < 8` lên trước nhánh `isBlank()`, chuỗi trắng ngắn cũng được phân loại là `short`; nhánh `blank` phía sau sẽ không bao giờ được chọn cho giá trị đó.

Guard có thể dùng biến pattern đã được tạo bởi pattern. Ví dụ `value` trong `case String value when value.length() < 8` có kiểu `String` và chỉ có phạm vi sử dụng trong nhãn/nhánh tương ứng.

## 5. Guard sai thì switch tiếp tục, guard ném lỗi thì lỗi được truyền ra

Guard trả về `false` không kết thúc switch. Java tiếp tục xét các nhãn sau theo thứ tự nguồn. Ngược lại, nếu việc đánh giá guard ném exception, exception được truyền ra ngoài; switch không coi exception như kết quả `false` để thử nhánh tiếp theo.

```java
static boolean isApproved(String value) {
    return value.startsWith("approved:");
}

static String route(Object input) {
    return switch (input) {
        case String value when isApproved(value) -> "approved";
        case String value -> "unapproved text";
        default -> "not text";
    };
}
```

Với chuỗi bắt đầu bằng `approved:`, guard trả về `true` và nhánh đầu được chọn. Với chuỗi khác, guard trả về `false`, sau đó nhánh `String` thứ hai xử lý giá trị. Giá trị không phải chuỗi đi đến `default`.

Có thể dùng toán tử boolean thông thường trong guard. Ví dụ `when value != null && value.length() > 5` đánh giá vế trái trước; nếu vế trái sai thì vế phải không được đánh giá theo quy tắc short-circuit của `&&`. Tuy nhiên, với pattern `String value`, bản thân pattern đã không khớp `null`, nên kiểm tra `value != null` thường là dư thừa.

## 6. Quy tắc dominance được kiểm tra lúc biên dịch

Dominance là quy tắc compiler dùng để phát hiện nhãn phía sau không thể được chọn vì nhãn trước đã bao phủ toàn bộ giá trị mà nhãn sau có thể khớp. Đây là lỗi cấu trúc được phát hiện khi biên dịch, khác với việc một guard tình cờ trả về `true` trong một lần chạy.

- Pattern không có guard có thể chi phối pattern tương thích hẹp hơn xuất hiện phía sau. Ví dụ `case String s` chi phối một `case String s when ...` phía sau.
- Pattern cụ thể cần đặt trước pattern tổng quát. Ví dụ `case Integer i` trước `case Number n`.
- Guard không phải biểu thức hằng `true` có thể trả về `false`, nên một guarded pattern thường không chi phối pattern rộng hơn phía sau.
- Guard là biểu thức hằng có giá trị `true` có thể khiến pattern đó chi phối các pattern tương thích phía sau.

Ví dụ hợp lệ: nhánh có guard thử điều kiện trước, nhánh không guard xử lý phần còn lại:

```java
static String check(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> "non-blank text";
        default -> "other";
    };
}
```

Ví dụ không hợp lệ: nhánh không guard đã nhận mọi `String`, do đó nhánh guarded phía sau không thể được chọn:

```java
// Không hợp lệ vì nhãn String đầu tiên chi phối nhãn thứ hai.
static String invalidGuardOrder(Object value) {
    return switch (value) {
        case String text -> "text";
        // case String text when text.isBlank() -> "blank";
        default -> "other";
    };
}
```

Compiler cũng kiểm tra tính bao phủ (exhaustiveness) của switch expression. Với sealed hierarchy hoặc enum, các nhánh có thể bao phủ hết kiểu đầu vào mà không cần `default`. Không nên thêm `default` một cách máy móc nếu muốn compiler giúp phát hiện kiểu con mới được bổ sung sau này.

## 7. Record pattern kiểm tra component theo thứ tự

Khi một record pattern có nhiều component pattern, Java kiểm tra các component theo thứ tự từ trái sang phải. Nếu một component không khớp, record pattern đó thất bại và các component phía sau không cần được kiểm tra. Guard của nhãn chỉ được đánh giá sau khi toàn bộ record pattern khớp.

```java
record Pair(Object first, Object second) {}

static String describePair(Object input) {
    return switch (input) {
        case Pair(String first, String second)
                when !first.isBlank() && !second.isBlank() -> "two non-blank strings";
        case Pair(String first, String second) -> "two strings";
        case Pair pair -> "other pair";
        default -> "not a pair";
    };
}
```

Java trước tiên xác định giá trị có phải `Pair` hay không, rồi kiểm tra component `first` và `second` theo thứ tự. Nếu cả hai component đều là `String`, guard mới được chạy. Nếu guard sai, nhãn `Pair(String first, String second)` kế tiếp có thể nhận cùng giá trị và trả về `two strings`.

Không nên dựa vào tác dụng phụ của accessor record hoặc guard để điều khiển nghiệp vụ. Record accessor nên trả về component một cách ổn định; guard nên là điều kiện kiểm tra dễ hiểu và ít tác dụng phụ. Điều này làm cho thứ tự đánh giá rõ ràng và tránh hành vi khó dự đoán khi pattern được thử.

## 8. Xử lý null là quy tắc riêng của switch

Pattern kiểu tham chiếu như `String text` không khớp với `null`. Trong Java 21, selector `null` làm switch ném `NullPointerException` nếu switch block không có nhãn `case null`. `default` đơn lẻ không nhận giá trị null.

```java
static String safeDescribe(Object value) {
    return switch (value) {
        case null -> "null value";
        case String text -> "text";
        default -> "other";
    };
}
```

Có thể viết `case null, default -> ...` khi cùng một nhánh cần xử lý cả null và mọi giá trị không được các nhánh khác nhận. Nếu cần phân biệt null với giá trị còn lại, hãy dùng hai nhánh riêng như ví dụ trên.

## 9. Cách thiết kế thứ tự pattern và guard

Khi xây dựng một pattern switch, có thể áp dụng trình tự thiết kế sau:

1. Xử lý `null` rõ ràng nếu selector có thể null.
2. Đặt các giá trị hoặc kiểu đặc biệt trước kiểu tổng quát, chẳng hạn constant label trước pattern `String`, `Integer` trước `Number`.
3. Với cùng một kiểu, đặt guarded pattern cụ thể trước guarded pattern rộng hơn.
4. Đặt pattern không guard làm nhánh dự phòng sau các guard cần thiết.
5. Kiểm tra compiler diagnostics về dominance và exhaustiveness; không cố lách bằng cách đổi thứ tự một cách tùy tiện.
6. Giữ guard ngắn, dễ đọc và tránh side effect. Nếu điều kiện phức tạp, tách thành phương thức có tên mô tả rõ ý nghĩa.

| Mục tiêu | Thứ tự gợi ý |
|---|---|
| Phân loại chuỗi rỗng trước mọi chuỗi | `String` với guard `isBlank()` → `String` không guard |
| Phân loại số nguyên riêng trước mọi số | `Integer` → `Number` |
| Phân loại kiểu con của sealed hierarchy | Các kiểu con cụ thể → nhánh tổng quát nếu cần |
| Xử lý null | `case null` → các pattern khác → `default` |

## 10. Biên dịch với Java 21

Pattern Matching for `switch` được hoàn thiện trong Java 21 qua JEP 441. Guard dùng từ khóa `when`; không cần bật Preview để biên dịch các ví dụ trong bài.

```bash
javac --release 21 -d out src/PatternSwitchOrderDemo.java
java -cp out PatternSwitchOrderDemo
```

Đảm bảo compiler và runtime tương ứng Java 21. Với Maven hoặc Gradle, đặt compiler release/toolchain là 21 và không thêm `--enable-preview` cho các tính năng đã final này.

## 11. Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification, Java SE 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification, Java SE 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification, Java SE 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
