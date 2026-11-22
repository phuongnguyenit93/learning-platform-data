# Checklist kiểm tra flow scope trong Java Pattern Matching

**Flow scoping** là cơ chế Java xác định **biến được khai báo bởi pattern có thể được tham chiếu ở vị trí nào**, dựa trên những đường đi mà compiler chứng minh pattern đã khớp. Với `instanceof`, record patterns và pattern matching cho `switch`, việc nhìn thấy tên biến trong cùng một phương thức **không đủ** để kết luận có thể dùng biến ở mọi nhánh.

Mục tiêu của checklist này là giúp người học hoặc người review Java trả lời chính xác:

- Biến pattern đã **được ràng buộc chắc chắn** trước khi truy cập chưa?
- Đường điều khiển nào đưa chương trình tới chỗ sử dụng biến: điều kiện đúng, điều kiện sai, guard return, toán tử `&&`/`||`, toán tử `?:`, vòng lặp hay `case` của switch?
- Biến nằm trong **phạm vi hợp lệ** nhưng giá trị có thể vẫn là `null` không?
- Compiler có thể phát hiện sai scope tại lúc build, hay vấn đề nằm ở hành vi runtime cần test?
- Refactor `if` sang `switch` có giữ nguyên thứ tự xét guard, xử lý null và ý nghĩa nghiệp vụ không?

**Phiên bản:** Type pattern `instanceof String s` đã final từ **Java 16** (JEP 394), `record` final từ Java 16 và `sealed` final từ Java 17. Các ví dụ có **record patterns** và **pattern switch/when** được biên dịch ở **Java 21+** (JEP 440, 441). Chương trình đầy đủ dùng `javac --release 21`, không cần `--enable-preview`.

## 1. Các thuật ngữ cần kiểm tra

| Thuật ngữ | Ý nghĩa trong bài | Điều phải xác nhận |
| --- | --- | --- |
| **Pattern** | Mẫu kiểm tra kiểu hoặc cấu trúc, ví dụ `String text` hoặc `TextEvent(var text)` | Mẫu có thể khớp đầu vào nào? |
| **Pattern variable** | Biến được khai báo qua pattern: `text`, `number`, `left` | Có nằm trong flow scope tại chỗ dùng không? |
| **Matching succeeds** | Mẫu khớp và các biến của pattern được ràng buộc | Điều kiện nào đảm bảo đã khớp? |
| **Definitely matched** | Compiler có thể kết luận pattern đã khớp trên mọi đường đi tới vị trí sử dụng | Có một đường đi không khớp mà vẫn tới chỗ dùng biến không? |
| **Flow scoping** | Phạm vi hiệu lực của pattern variable phụ thuộc luồng điều khiển và cấu trúc biểu thức | Không suy luận chỉ theo dấu ngoặc hoặc tên biến |
| **Short-circuit** | `&&` bỏ qua vế phải khi vế trái false; `||` bỏ qua vế phải khi vế trái true | Biến có chắc chắn được gán khi vế phải chạy? |
| **Guard `when`** | Điều kiện kiểm tra thêm sau khi case pattern khớp | Biến trong guard có được ràng buộc? Guard có xử lý null đúng thứ tự không? |
| **Dominance** | Một case tổng quát đứng trước bao phủ case cụ thể phía sau | Thứ tự case có bị compiler từ chối không? |
| **Exhaustiveness** | Switch expression bao phủ đủ giá trị selector theo quy tắc ngôn ngữ | Có thiếu biến thể sealed hoặc thiếu nhánh cần thiết không? |

Điểm phân biệt quan trọng: **flow scope không đồng nghĩa null safety**. Khi một type pattern `value instanceof String text` thành công, `text` tham chiếu đến một `String` khác null. Nhưng với **component pattern** `TextEvent(var text)`, biến `text` có thể nhận `null` vì thành phần record khai báo kiểu `String` có thể null. Compiler có thể cho phép truy cập biến, trong khi lời gọi `text.isBlank()` vẫn gây `NullPointerException`.

## 2. Checklist nhanh trước khi đọc hoặc sửa code

Dùng bảng sau như một **checklist review**. Mỗi câu trả lời “không rõ” là dấu hiệu nên kiểm tra đường đi, biên dịch thử hoặc thêm test.

| # | Câu hỏi kiểm tra | Tiêu chí PASS |
| --- | --- | --- |
| 1 | Pattern variable được khai báo **ở đâu**? | Xác định chính xác `instanceof`, record pattern hoặc case label |
| 2 | Ở vị trí sử dụng, pattern đã khớp trên **mọi** đường đi chưa? | Không có đường đi chưa khớp nhưng vẫn dùng biến |
| 3 | Nếu ở nhánh `if`, đang ở nhánh **true** hay **false**? | Biến `s` từ `instanceof String s` được dùng ở nhánh true, trừ các quy tắc flow đặc biệt |
| 4 | Nếu dùng phủ định `!`, điều kiện đã được đảo đúng chưa? | Khi `!(value instanceof String s)` false thì pattern gốc đã khớp |
| 5 | Nếu dùng `&&`, vế trái có đảm bảo biến đã ràng buộc cho vế phải không? | Với `value instanceof String s && s.length() > 0`, câu trả lời là có |
| 6 | Nếu dùng `||`, vế trái true hay false mới khiến vế phải chạy? | Với `!(value instanceof String s) || s.isBlank()`, vế phải chỉ chạy khi pattern khớp |
| 7 | Nếu dùng `?:`, biến pattern chỉ xuất hiện ở nhánh có đảm bảo khớp? | Với `value instanceof String s ? s.length() : 0`, biến được dùng ở nhánh true |
| 8 | Nếu dùng early return, nhánh chưa khớp có thực sự thoát phương thức? | `if (!(value instanceof String s)) return ...;` cho phép dùng `s` ở phần còn lại |
| 9 | Nếu ở vòng `while`/`for`, điều kiện có đảm bảo pattern khớp trước thân/update? | Điều kiện khớp cho phép dùng biến trong những phần được JLS quy định |
| 10 | Nếu ở `switch`, biến thuộc đúng case pattern chưa? | Biến trong guard/body của case đó, không chảy sang case khác |
| 11 | Với record pattern, component nào có thể null? | Guard null ở lá trước khi dereference |
| 12 | Thứ tự case có bị dominance hoặc guard gây NPE không? | Case chuyên biệt trước case rộng; guard null trước guard gọi phương thức |
| 13 | Build có dùng đúng mức Java? | Mã dùng record patterns và `when` có `--release 21` hoặc phiên bản hỗ trợ |
| 14 | Có test cả đường không khớp, khớp, null và giá trị biên không? | Có oracle và assert, không chỉ log ra console |

**Quy tắc tư duy:** Đừng hỏi “biến `s` có được khai báo trong phương thức này không?”. Hãy hỏi: “**Nếu chương trình thực sự tới dòng đang dùng `s`, compiler có biết chắc `instanceof String s` trước đó đã thành công không?**”

## 3. if/else: phân biệt nhánh pattern khớp và không khớp

Ví dụ Java 16+:

```java
static String positiveIf(Object value) {
    if (value instanceof String text) {
        return "IF=" + text.length();
    }
    return "NO_STRING";
}
```

**Flow analysis:**

1. Java đánh giá `value instanceof String text`.
2. Nếu trả `true`, `text` được ràng buộc là `String` khác null; trong thân `if` dùng được `text.length()`.
3. Nếu trả `false`, biến `text` không được ràng buộc trên đường đó. Nhánh bên ngoài trả `NO_STRING` mà không tham chiếu `text`.

Các giá trị thử:

| Input | Kết quả |
| --- | --- |
| `"Java"` | `IF=4` |
| `Integer.valueOf(4)` | `NO_STRING` |
| `null` | `NO_STRING` |

**Sai thường gặp:**

```java
// CỐ Ý SAI: ở ngoài if chưa chắc pattern đã khớp.
static int wrongPostIf(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
    return text.length(); // error: cannot find symbol
}
```

Một đường đi có thể là `value == null`; chương trình vẫn đi tới `return text.length()` dù pattern không khớp. Compiler từ chối, không phải đợi NPE lúc chạy.

**Nếu muốn sử dụng biến sau if**, dùng nhánh phủ định thoát sớm như phần 4, hoặc đặt đoạn xử lý trong nhánh `if` đã khớp.

### else có tự thấy biến của nhánh if không?

Không. Trong cấu trúc:

```java
// CỐ Ý SAI:
if (value instanceof String text) {
    System.out.println(text);
} else {
    System.out.println(text.length()); // Chưa khớp, biến không ở scope này.
}
```

`else` chính là nhánh khi `instanceof` sai. Do đó `text` không có nghĩa ở nhánh này. Mã tương đương với một biến local khai báo trong thân `if` không được dùng tùy ý ngoài thân đó.

## 4. Phủ định và early return: biến sống sau guard

Một kỹ thuật Java phổ biến là **guard clause**:

```java
static String negativeGuard(Object value) {
    if (!(value instanceof String text)) {
        return "NO_STRING";
    }
    return "GUARD=" + text.toUpperCase(java.util.Locale.ROOT);
}
```

Có thể phân tích bằng bảng chân trị:

| `value instanceof String text` | `!(...)` | Điều gì xảy ra? | Có được dùng `text` sau `if`? |
| --- | --- | --- | --- |
| `false` | `true` | Trả `NO_STRING` ngay | Không tới phần sau |
| `true` | `false` | Bỏ qua nhánh `if` | **Có**, pattern chắc chắn đã khớp |

Vì nhánh chưa khớp luôn kết thúc bằng `return`, mọi đường đi tới `return "GUARD=" + text...` đều đã khớp pattern.

Kết quả: `negativeGuard("java")` trả `GUARD=JAVA`, `negativeGuard(null)` trả `NO_STRING`.

### Checklist riêng cho early return

- [ ] Có dấu phủ định `!` đúng vị trí không?
- [ ] Nhánh không khớp có thật sự **thoát** bằng `return` hoặc `throw` không?
- [ ] Có một nhánh nào rơi xuống dòng dùng biến dù chưa khớp không?
- [ ] Sau guard, đã phân biệt “biến chắc chắn được ràng buộc” với “thành phần lồng trong biến có thể null” chưa?

**Ví dụ sai ngược lại:**

```java
// CỐ Ý SAI:
static int wrongNegationBranch(Object value) {
    if (!(value instanceof String text)) {
        return text.length(); // Lúc này pattern gốc KHÔNG khớp.
    }
    return 0;
}
```

Compiler báo `cannot find symbol` tại chỗ dùng `text` trong nhánh phủ định true.

## 5. Toán tử &&: vế phải chỉ chạy khi pattern đã khớp

Mẫu chuẩn:

```java
static String andGate(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "AND=" + text.strip();
    }
    return "AND_SKIP";
}
```

Đây là cách viết **an toàn theo flow scope**:

- Vế trái `value instanceof String text` được đánh giá trước.
- Nếu false, Java không đánh giá `!text.isBlank()`; compiler không cần truy cập `text` trên đường này.
- Nếu true, `text` đã được ràng buộc và là `String` khác null; vế phải được phép gọi `isBlank()`.
- Nếu cả hai vế đúng, thân `if` dùng được `text.strip()`.

Bảng test:

| Input | Pattern | Guard | Kết quả |
| --- | --- | --- | --- |
| `" Hi "` | true | true | `AND=Hi` |
| `"  "` | true | false | `AND_SKIP` |
| `12` | false | không đánh giá | `AND_SKIP` |
| `null` | false | không đánh giá | `AND_SKIP` |

### Ghép nhiều pattern trong một điều kiện

```java
static String twoPatterns(Object first, Object second) {
    return first instanceof String left
            && second instanceof String right
            && left.length() == right.length()
            ? "EQUAL_LEN=" + left + ":" + right
            : "DIFFERENT";
}
```

Ở vế thứ ba, **cả `left` lẫn `right` đã được ràng buộc** vì Java chỉ đến đó nếu cả hai phép `instanceof` trước đều true.

Điều này giúp kiểm tra hai đối tượng mà không cần cast tay:

```text
twoPatterns("ab", "xy")   -> EQUAL_LEN=ab:xy
twoPatterns(null, "xy")   -> DIFFERENT
twoPatterns("a", "xy")    -> DIFFERENT
```

**Lưu ý:** Luồng điều khiển quan trọng hơn vị trí khai báo. Đổi thứ tự các vế có thể khiến biến bị dùng trước khi compiler chứng minh đã khớp.

## 6. Toán tử ||: phủ định cần được hiểu đúng

`||` chỉ đánh giá vế phải khi vế trái **false**, nên dùng pattern variable đòi hỏi cách suy luận ngược với `&&`.

### Mẫu sai: dùng biến sau một instanceof dương nối ||

```java
// CỐ Ý SAI:
static boolean wrongOr(Object value) {
    return value instanceof String text || text.length() > 0;
}
```

Khi `value instanceof String text` trả false, Java phải xét `text.length() > 0` nhưng **text chưa được ràng buộc**. Compiler báo `cannot find symbol`. Không thể “sửa” bằng cách giả định biến được khai báo khi parser đọc qua pattern.

### Mẫu đúng: phủ định phép match

```java
static String orGate(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "OR_SKIP";
    }
    return "OR=" + text;
}
```

Thứ tự:

1. Nếu không phải String hoặc là `null`, `!(...)` true; `||` không đánh giá vế phải. Trả `OR_SKIP`.
2. Nếu là String, `!(...)` false; lúc này `text` đã được ràng buộc và vế phải được phép gọi `text.isBlank()`.
3. Nếu String blank, trả `OR_SKIP`.
4. Nếu String không blank, cả điều kiện `if` false; đường đi sau `if` cho phép dùng `text` và trả `OR=...`.

Kết quả: `orGate("Hi")` → `OR=Hi`; `orGate("  ")` → `OR_SKIP`; `orGate(null)` → `OR_SKIP`.

**Checklist cho `||`:** Để vế phải dùng một pattern variable từ vế trái, hãy chứng minh **việc vế trái false** đồng nghĩa pattern đã khớp. Với mẫu phủ định như trên thì đúng; với mẫu dương `value instanceof String text || ...` thì sai.

## 7. Toán tử ba ngôi ?: và đường nhánh hợp lệ

Toán tử điều kiện `?:` cũng có hai đường:

```java
static String ternary(Object value) {
    return value instanceof Integer number
            ? "TERNARY=" + (number + 1)
            : "NO_INTEGER";
}
```

- Nhánh sau `?` chỉ chạy khi `instanceof Integer number` true, nên `number` dùng hợp lệ.
- Nhánh sau `:` chạy khi pattern false. Nó không được tùy ý sử dụng `number`.

Ví dụ cố ý sai:

```java
// CỐ Ý SAI:
static boolean wrongTernary(Object value) {
    return value instanceof String text ? true : text.isBlank();
}
```

Compiler từ chối vì nhánh false không bảo đảm pattern biến `text` được ràng buộc.

**Lưu ý thêm:** Chọn nhánh bằng `?:` hữu ích cho biểu thức ngắn. Với logic nhiều guard hoặc cần thông báo lỗi khác nhau, `if/else` hoặc `switch` thường dễ review hơn.

## 8. while và for: pattern variable ở thân và update

Flow scoping còn xuất hiện trong vòng lặp. Trình biên dịch có thể suy luận biến đã được ràng buộc trên đường đi vào thân vòng lặp khi điều kiện `instanceof` đúng.

### while với điều kiện pattern

```java
static String whileLoop(Object input) {
    int sum = 0;
    while (input instanceof String text && !text.isEmpty()) {
        sum += text.length();
        input = text.substring(1);
    }
    return "WHILE=" + sum;
}
```

Giải thích với `input="abc"`:

| Lượt kiểm tra | `text` | `text.length()` cộng thêm | `input` sau lượt |
| --- | --- | ---: | --- |
| 1 | `"abc"` | 3 | `"bc"` |
| 2 | `"bc"` | 2 | `"c"` |
| 3 | `"c"` | 1 | `""` |
| 4 | `""` | Điều kiện `!text.isEmpty()` false | Thoát |

Tổng là `3 + 2 + 1 = 6`. Với `input == null`, vòng lặp không vào thân và trả `WHILE=0`.

### for kiểu truyền thống

```java
static String forLoop(Object input) {
    int sum = 0;
    for (; input instanceof String text && !text.isEmpty();
            input = text.substring(1)) {
        sum += text.length();
    }
    return "FOR=" + sum;
}
```

Trong cấu trúc `for (init; condition; update)` này, biến pattern `text` được phép dùng trong **thân** và phần **update** vì điều kiện đã khớp trước khi chạy các phần đó. Ví dụ đã biên dịch thực tế bằng Java 21 và cho `FOR=6` với `"abc"`, `FOR=0` với `null`.

**Checklist vòng lặp:**

- [ ] Biến pattern được khai báo trong phần điều kiện có đảm bảo khớp trước khi vào thân không?
- [ ] Nếu dùng biến trong update của `for`, có thực sự được khai báo từ điều kiện với đường true không?
- [ ] Biến có bị dùng sau khi vòng lặp đã kết thúc, trong khi điều kiện cuối cùng có thể false không?
- [ ] Nếu input thay đổi trong vòng, có rủi ro không kết thúc hoặc đánh giá lặp nhiều lần accessor có side effect không?

**Không suy luận tùy tiện cho `do/while`:** phần thân `do` chạy **trước** khi điều kiện được đánh giá, nên pattern variable khai báo ở điều kiện cuối không thể dùng trong thân trước khi được ràng buộc. Nếu cần sử dụng biến qua nhiều lần lặp, hãy tách điều kiện hoặc chuyển cấu trúc có kiểm chứng.

## 9. Switch pattern: scope nằm trong case và guard của nó

Java 21 cho phép phân loại một hierarchy đóng:

```java
sealed interface Event permits TextEvent, CountEvent, PairEvent {}
record TextEvent(String text) implements Event {}
record CountEvent(int count) implements Event {}
record PairEvent(TextEvent left, TextEvent right) implements Event {}
```

Khi `switch` chọn case:

```java
static String switchEvent(Event event) {
    return switch (event) {
        case null -> "MISSING_EVENT";
        case TextEvent(var text) when text == null -> "MISSING_TEXT";
        case TextEvent(var text) when text.isBlank() -> "BLANK";
        case TextEvent(var text) -> "TEXT=" + text.strip();
        case CountEvent(int count) when count < 0 -> "NEG_COUNT=" + count;
        case CountEvent(int count) -> "COUNT=" + count;
        case PairEvent(TextEvent(var left), TextEvent(var right))
                when left != null && right != null && left.equals(right) ->
                "SAME_PAIR=" + left;
        case PairEvent(TextEvent(var left), TextEvent(var right)) ->
                "PAIR=" + left + "|" + right;
        case PairEvent(var left, var right) -> "MISSING_PAIR_ITEM";
    };
}
```

Các khai báo `record` và phương thức trên được đặt trong cùng lớp ở chương trình hoàn chỉnh mục 11. Các case có record patterns cần mức Java 21+.

### Scope qua case label

Với `case CountEvent(int count) when count < 0 -> ...`:

- Java chỉ đánh giá guard `count < 0` sau khi `CountEvent(int count)` khớp.
- Biến `count` hợp lệ trong guard và thân của **case đó**.
- Biến `count` của case này **không tự chảy** sang case `PairEvent` hay `TextEvent`.
- Case `CountEvent(int count)` khác có thể dùng lại tên `count` trong một scope case riêng, theo quy tắc của switch pattern labels.

Mỗi nhánh dạng `->` tạo luồng xử lý độc lập; không nên tìm cách dùng pattern variable của case này trong nhánh case khác.

### Scope và null là hai vấn đề khác nhau

`case TextEvent(var text) when text == null -> ...` vẫn cần thiết vì component `TextEvent.text` có thể null, dù record pattern đã khớp. Sau khi nhánh này bắt null component, guard `text.isBlank()` phía sau mới an toàn trên các giá trị còn lại trong thiết kế này.

`case null` chỉ xử lý **selector event bằng null**; nó không giải quyết `new TextEvent(null)`. Một nested record pattern cũng không khớp **record con null**:

```java
new PairEvent(null, new TextEvent("B"))
```

Giá trị trên không khớp `PairEvent(TextEvent(...), TextEvent(...))` vì `left == null`, nhưng khớp `PairEvent(var left, var right)` và được xử lý bởi `MISSING_PAIR_ITEM` trong ví dụ.

Ngược lại:

```java
new PairEvent(new TextEvent(null), new TextEvent("B"))
```

Hai record con tồn tại, nên case `PairEvent(TextEvent(var left), TextEvent(var right))` khớp; `left` được ràng buộc nhưng **giá trị của nó có thể null**. Guard `left != null && right != null && left.equals(right)` không dereference null; case không guard phía sau trả `PAIR=null|B`.

### Dominance cũng phải được review

Nhánh không guard `case TextEvent(var text)` nếu đặt **trước** các nhánh cùng type có `when` sẽ bao phủ tất cả `TextEvent`, khiến case chuyên biệt phía sau bị dominated. Compiler có thể báo:

```text
error: this case label is dominated by a preceding case label
```

Sắp các nhánh theo thứ tự **special case / when → type case tổng quát**, và giữ nhánh xử lý null component trước khi guard gọi phương thức trên component.

### Exhaustiveness có giống flow scoping?

Không. Switch expression trên `sealed Event` được xem xét tính exhaustive dựa vào tập subtype được phép. Scope kiểm soát **biến trong từng case**. Một switch có thể exhaustive mà case body vẫn tham chiếu sai biến (compile error), hoặc vẫn gặp NPE runtime vì component null.

## 10. Flow scope sai trong switch: biến không đi sang case khác

Ví dụ **cố ý không biên dịch được**:

```java
static String wrongSwitchBranch(Object value) {
    return switch (value) {
        case String text -> text;
        case Integer number -> text; // Không phải biến của case Integer.
        default -> "other";
    };
}
```

`text` chỉ thuộc case `String text`. Khi selector là `Integer`, chưa có ràng buộc `text`, và compiler báo `cannot find symbol`.

**Cách sửa:** mỗi case chỉ sử dụng các pattern variables đã được ràng buộc trong chính nhánh đó. Nếu cần kết quả chung ở nhiều case, hãy tính toán từ biến có mặt ở scope chung hoặc tách handler.

Một số lỗi khác không phải flow scope nhưng thường bị nhầm:

- **Dominated case:** compiler từ chối nhánh cụ thể đứng sau nhánh tổng quát đã bao phủ nó.
- **Non-exhaustive switch expression:** compiler từ chối switch thiếu trường hợp bắt buộc.
- **Null selector:** pattern switch thiếu `case null` có thể ném NPE runtime.
- **Nullable record component:** biến nằm trong scope nhưng gọi method trên giá trị null có thể ném NPE.

Vì vậy, không nên cứ thấy lỗi liên quan pattern là sửa bằng `default` hoặc thêm `instanceof` bừa bãi.

## 11. Chương trình Java 21 hoàn chỉnh đã biên dịch và chạy

Lưu nguyên nội dung thành tệp **`FlowScopeChecklistDemo.java`**:

```java
import java.util.Locale;

public class FlowScopeChecklistDemo {
    sealed interface Event permits TextEvent, CountEvent, PairEvent {}
    record TextEvent(String text) implements Event {}
    record CountEvent(int count) implements Event {}
    record PairEvent(TextEvent left, TextEvent right) implements Event {}

    private static int checks;

    static String positiveIf(Object value) {
        if (value instanceof String text) {
            return "IF=" + text.length();
        }
        return "NO_STRING";
    }

    static String negativeGuard(Object value) {
        if (!(value instanceof String text)) {
            return "NO_STRING";
        }
        return "GUARD=" + text.toUpperCase(Locale.ROOT);
    }

    static String andGate(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "AND=" + text.strip();
        }
        return "AND_SKIP";
    }

    static String orGate(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "OR_SKIP";
        }
        return "OR=" + text;
    }

    static String numericIf(Object value) {
        if (value instanceof Integer number && number >= 0) {
            return "NONNEG=" + number;
        } else {
            return "NEG_OR_OTHER";
        }
    }

    static String ternary(Object value) {
        return value instanceof Integer number
                ? "TERNARY=" + (number + 1)
                : "NO_INTEGER";
    }

    static String twoPatterns(Object first, Object second) {
        return first instanceof String left
                && second instanceof String right
                && left.length() == right.length()
                ? "EQUAL_LEN=" + left + ":" + right
                : "DIFFERENT";
    }

    static String switchEvent(Event event) {
        return switch (event) {
            case null -> "MISSING_EVENT";
            case TextEvent(var text) when text == null -> "MISSING_TEXT";
            case TextEvent(var text) when text.isBlank() -> "BLANK";
            case TextEvent(var text) -> "TEXT=" + text.strip();
            case CountEvent(int count) when count < 0 -> "NEG_COUNT=" + count;
            case CountEvent(int count) -> "COUNT=" + count;
            case PairEvent(TextEvent(var left), TextEvent(var right))
                    when left != null && right != null && left.equals(right) ->
                    "SAME_PAIR=" + left;
            case PairEvent(TextEvent(var left), TextEvent(var right)) ->
                    "PAIR=" + left + "|" + right;
            case PairEvent(var left, var right) -> "MISSING_PAIR_ITEM";
        };
    }

    static String whileLoop(Object input) {
        int sum = 0;
        while (input instanceof String text && !text.isEmpty()) {
            sum += text.length();
            input = text.substring(1);
        }
        return "WHILE=" + sum;
    }

    static String forLoop(Object input) {
        int sum = 0;
        for (; input instanceof String text && !text.isEmpty();
                input = text.substring(1)) {
            sum += text.length();
        }
        return "FOR=" + sum;
    }

    private static void expect(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + ": expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        expect("positive", "IF=4", positiveIf("Java"));
        expect("positive-int", "NO_STRING", positiveIf(4));
        expect("positive-null", "NO_STRING", positiveIf(null));
        expect("negative-guard", "GUARD=JAVA", negativeGuard("java"));
        expect("negative-guard-null", "NO_STRING", negativeGuard(null));
        expect("and-trim", "AND=Hi", andGate(" Hi "));
        expect("and-blank", "AND_SKIP", andGate("  "));
        expect("and-other", "AND_SKIP", andGate(12));
        expect("or-text", "OR=Hi", orGate("Hi"));
        expect("or-blank", "OR_SKIP", orGate("   "));
        expect("or-null", "OR_SKIP", orGate(null));
        expect("numeric", "NONNEG=2", numericIf(2));
        expect("numeric-negative", "NEG_OR_OTHER", numericIf(-1));
        expect("ternary", "TERNARY=6", ternary(5));
        expect("ternary-other", "NO_INTEGER", ternary("5"));
        expect("two-patterns", "EQUAL_LEN=ab:xy", twoPatterns("ab", "xy"));
        expect("two-patterns-null", "DIFFERENT", twoPatterns(null, "xy"));
        expect("switch-null", "MISSING_EVENT", switchEvent(null));
        expect("switch-empty", "BLANK", switchEvent(new TextEvent("  ")));
        expect("switch-null-text", "MISSING_TEXT", switchEvent(new TextEvent(null)));
        expect("switch-text", "TEXT=Hi", switchEvent(new TextEvent(" Hi ")));
        expect("switch-negative", "NEG_COUNT=-1", switchEvent(new CountEvent(-1)));
        expect("switch-zero", "COUNT=0", switchEvent(new CountEvent(0)));
        expect("switch-pair-same", "SAME_PAIR=A",
                switchEvent(new PairEvent(new TextEvent("A"), new TextEvent("A"))));
        expect("switch-pair-other", "PAIR=A|B",
                switchEvent(new PairEvent(new TextEvent("A"), new TextEvent("B"))));
        expect("switch-pair-null-component", "PAIR=null|B",
                switchEvent(new PairEvent(new TextEvent(null), new TextEvent("B"))));
        expect("switch-pair-null-record", "MISSING_PAIR_ITEM",
                switchEvent(new PairEvent(null, new TextEvent("B"))));
        expect("while-loop", "WHILE=6", whileLoop("abc"));
        expect("while-loop-null", "WHILE=0", whileLoop(null));
        expect("for-loop", "FOR=6", forLoop("abc"));
        expect("for-loop-null", "FOR=0", forLoop(null));

        System.out.println("PASS assertions=" + checks);
        System.out.println("PASS if=" + positiveIf("Java"));
        System.out.println("PASS guard=" + negativeGuard("java"));
        System.out.println("PASS and=" + andGate(" Hi "));
        System.out.println("PASS or=" + orGate("Hi"));
        System.out.println("PASS switch=" + switchEvent(new PairEvent(new TextEvent("A"), new TextEvent("A"))));
        System.out.println("PASS loops=" + whileLoop("abc") + "," + forLoop("abc"));
    }
}
```

**Cách chạy bằng JDK 21+:**

```bash
javac --release 21 -Xlint:all -Werror -encoding UTF-8 FlowScopeChecklistDemo.java
java FlowScopeChecklistDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
PASS assertions=31
PASS if=IF=4
PASS guard=GUARD=JAVA
PASS and=AND=Hi
PASS or=OR=Hi
PASS switch=SAME_PAIR=A
PASS loops=WHILE=6,FOR=6
```

Chương trình dùng một hàm `expect` so sánh **giá trị thực tế với oracle độc lập**; nếu có một sai lệch, nó ném `AssertionError` và không thể in `PASS assertions=31` như trên. Kiểm chứng thực tế đã biên dịch sạch với `javac --release 21 -Xlint:all -Werror` và chạy đúng **7 dòng stdout**. Không sử dụng thư viện bên ngoài.

### Cách hiểu 31 phép kiểm tra

Những ca kiểm thử phân bổ qua:

- `if` với String, số nguyên và selector null;
- guard phủ định với String và null;
- `&&` với chuỗi có nội dung, blank và đối tượng khác;
- `||` phủ định với chuỗi có nội dung, blank và null;
- `if/else` numeric, `?:` với Integer/sai kiểu;
- hai pattern trong một biểu thức `&&`;
- switch với selector null, record component null, guard blank, số âm/0, nested record bằng nhau/khác nhau, record con null;
- hai kiểu vòng lặp với String và null.

Điều này không tự đồng nghĩa **100% branch coverage theo JaCoCo**. Bộ test được thiết kế để xác nhận flow scope và ngữ nghĩa quan sát được của các nhánh đã chọn; công cụ coverage còn dùng những tiêu chí bytecode riêng.

## 12. Chương trình cố ý sai: năm lỗi phạm vi ở compile time

Lưu riêng thành **`FlowScopeCompileErrors.java`** để quan sát các lỗi. **Không dùng tệp này cùng lệnh biên dịch với chương trình chạy được ở mục 11**, vì nó được viết để thất bại.

```java
public class FlowScopeCompileErrors {
    static boolean wrongOr(Object value) {
        return value instanceof String text || text.length() > 0;
    }

    static int wrongNegationBranch(Object value) {
        if (!(value instanceof String text)) {
            return text.length();
        }
        return 0;
    }

    static int wrongPostIf(Object value) {
        if (value instanceof String text) {
            System.out.println(text);
        }
        return text.length();
    }

    static boolean wrongTernary(Object value) {
        return value instanceof String text ? true : text.isBlank();
    }

    static String wrongSwitchBranch(Object value) {
        return switch (value) {
            case String text -> text;
            case Integer number -> text;
            default -> "other";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 -encoding UTF-8 FlowScopeCompileErrors.java
```

Kết quả đã kiểm chứng bằng `javac` có **5 lỗi**, đều thuộc nhóm:

```text
error: cannot find symbol
  symbol:   variable text
5 errors
```

| Vị trí lỗi | Vì sao compiler từ chối? | Cách sửa |
| --- | --- | --- |
| `wrongOr` | Vế phải `||` chạy khi `instanceof` false | Dùng `!(value instanceof String text) || ...` khi ngữ nghĩa phù hợp, hoặc thiết kế logic khác |
| `wrongNegationBranch` | Nhánh `if` true vì **không** khớp pattern | Dùng `text` sau early-return guard, không dùng trong nhánh không khớp |
| `wrongPostIf` | Sau `if` vẫn có đường đi không khớp | Đưa xử lý vào nhánh true hoặc bảo đảm nhánh false thoát |
| `wrongTernary` | Nhánh false của `?:` không có ràng buộc `text` | Dùng `text` ở nhánh true, hoặc chọn giá trị khác cho nhánh false |
| `wrongSwitchBranch` | Biến `text` thuộc case String, không thuộc case Integer | Sử dụng `number` hoặc một biến ở scope chung |

**Diagnostic là lỗi biên dịch, không phải NPE runtime.** Bật/tắt `-Xlint` không làm những biểu thức bị sai scope trở nên hợp lệ. Ngược lại, một biểu thức đã đúng scope vẫn có thể gặp lỗi runtime do nullable component hoặc side effect; vì vậy phải kết hợp compile-time review với test.

## 13. Checklist null-safety khi dùng record pattern

Một lỗi logic thường thấy trong code đã biên dịch thành công là **đánh đồng biến được ràng buộc với biến khác null**.

Giả sử:

```java
record TextEvent(String text) {}
Object input = new TextEvent(null);
```

Với component pattern:

```java
// Pattern có thể khớp và text có thể null:
if (input instanceof TextEvent(var text)) {
    // text.isBlank(); // KHÔNG an toàn nếu text == null.
    System.out.println(text == null ? "missing" : text);
}
```

**Vì sao?** Record `TextEvent` tồn tại nên record pattern khớp; `var text` ràng buộc thành phần tham chiếu vốn được phép null. Type pattern cấp ngoài và component pattern bên trong không có cùng bảo đảm null cho mọi giá trị.

Cách xử lý:

```java
if (input instanceof TextEvent(var text)
        && text != null
        && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Kiểm tra theo thứ tự: pattern record khớp → component khác null → điều kiện nội dung. Đừng gọi `text.strip()` hoặc `text.isBlank()` trước khi xác định nullability của thành phần.

**Checklist bổ sung:**

- [ ] Selector ngoài có thể null không? `instanceof` với selector null chỉ false; `switch` cần chính sách `case null` hoặc guard riêng.
- [ ] Record con lồng có thể null không? Nested record pattern yêu cầu record con tồn tại để khớp.
- [ ] Thành phần `var`/type pattern không điều kiện có thể nhận null không? Không mặc định non-null cho biến thành phần.
- [ ] Guard nào gọi method trên component? Có guard null chạy **trước** nó chưa?
- [ ] Có cần từ chối null ở record constructor thay vì lặp guard nhiều nơi không? Chỉ áp dụng khi hợp đồng nghiệp vụ thực sự cấm null.
- [ ] Đã thử input null/blank và record con null bằng unit test chưa?

## 14. Checklist cho review một pull request refactor pattern

Trước khi approve một thay đổi dùng pattern matching, có thể dùng quy trình sau:

### A. Kiểm tra luồng và scope

- [ ] Tìm tất cả các vị trí khai báo biến pattern (`instanceof`, record pattern, `case`).
- [ ] Đánh dấu đường **pattern true** và **pattern false**.
- [ ] Với `&&`: chỉ dùng biến ở vế phải khi đường tới đó bảo đảm khớp.
- [ ] Với `||`: kiểm tra đặc biệt trường hợp phủ định; vế phải chạy khi vế trái false.
- [ ] Với `?:`: xác định đúng nhánh có biến pattern.
- [ ] Với early-return guard: nhánh không khớp phải kết thúc điều khiển trước khi biến được dùng.
- [ ] Với vòng lặp: chỉ dùng biến khi điều kiện lặp đã bảo đảm pattern khớp.
- [ ] Với switch: guard/body của case dùng biến của chính case; không dùng tên từ case khác.

### B. Kiểm tra kiểu, null và thứ tự

- [ ] Phân biệt `null` ở selector với `null` ở component record.
- [ ] Case có `when` được đặt trước case tổng quát cùng type để tránh dominance.
- [ ] Guard xử lý null component đứng trước guard dereference component.
- [ ] Switch expression trên sealed hierarchy xử lý đủ biến thể; không tự thêm `default` để che case thiếu.
- [ ] Pattern variables có thể được khai báo trùng tên trong các scope độc lập, nhưng không vi phạm các quy tắc khai báo/che khuất tên ở phạm vi đang hoạt động.
- [ ] Nếu cần dùng biến ở nhiều nơi, hãy tách phương thức hoặc khai báo biến chung hợp pháp, không “kéo” pattern variable ra khỏi flow scope.

### C. Kiểm tra khả năng chạy và test

- [ ] Mức `javac --release` phù hợp cú pháp: Java 16+ cho `instanceof` type patterns, Java 21+ cho record patterns/pattern switch final.
- [ ] Build không có compiler error `cannot find symbol` liên quan pattern variable.
- [ ] Có test cho đầu vào pattern true và false, sai kiểu, null selector, nullable components.
- [ ] Có test guard true/false, trường hợp blank, giá trị biên số học và nested record con null nếu domain cho phép.
- [ ] Kết quả kỳ vọng được định nghĩa **độc lập với kết quả thực tế**; test không chỉ in ra console.
- [ ] Sau khi refactor, hành vi nghiệp vụ giữ nguyên theo contract, kể cả thứ tự ưu tiên lỗi và branch đặc biệt.

## 15. Các sai lầm thường gặp

1. **Dùng pattern variable sau một `if` có thể rơi qua nhánh false.** Compiler không thấy biến definitely matched.
2. **Dùng biến ở nhánh phủ định true.** `!(value instanceof String s)` đúng đồng nghĩa `s` chưa được ràng buộc.
3. **Viết `value instanceof String s || s.isEmpty()`.** Vế phải chạy khi pattern false; compiler từ chối.
4. **Nhầm `&&` với `||`.** Hai toán tử có đường short-circuit khác nhau; không thể thay thế tùy tiện.
5. **Dùng biến pattern ở nhánh false của `?:`.** Với pattern dương ở điều kiện, nhánh false không đảm bảo ràng buộc.
6. **Dùng biến pattern của case này ở case khác.** Switch không có một biến tự động chia sẻ giữa các case.
7. **Cho rằng biến pattern hoạt động trong toàn bộ lexical block.** Flow scoping phụ thuộc các đường điều khiển, không chỉ dấu ngoặc.
8. **Nhầm scope với null safety của record component.** `var text` có thể ràng buộc component null trong một record đã khớp.
9. **Quên case null của switch pattern.** Dù các subtype sealed được xử lý đầy đủ, selector null có thể vẫn gây NPE nếu không có chính sách riêng.
10. **Đặt case tổng quát trước case guarded.** Compiler có thể báo dominated case; sắp case cụ thể trước.
11. **Coi mọi thiếu nhánh trong switch là flow scope error.** Missing subtype là lỗi exhaustiveness; nguyên nhân và cách sửa khác.
12. **Tin rằng compiler chứng minh được mọi điều kiện nghiệp vụ.** Compiler kiểm tra luật scope tĩnh, không đảm bảo một guard có side effect hoặc truy cập nullable component luôn an toàn.
13. **Dùng tên biến pattern trùng với biến đang trong scope.** Có thể gây lỗi khai báo trùng/shadowing hoặc gây khó đọc dù cấu trúc gần nhau.
14. **Cho rằng Java 17 đã hỗ trợ record patterns final.** `record` đã có, nhưng deconstruction bằng record pattern và `when` cần Java 21 để là feature final.
15. **Chỉ kiểm tra nhánh thành công.** Test phải bao gồm false path, null, guard false, đường thoát sớm và vòng lặp không vào thân.
16. **Dựa vào cú pháp mới để refactor nhưng không giữ nguyên behavior.** Sắp lại điều kiện có thể đổi short-circuit, thứ tự gọi accessor, exception và nhánh được chọn.

## 16. Bài tập tự kiểm tra kèm đáp án

**Bài 1.** Biến `s` có hợp lệ ở cuối phương thức dưới đây không?

```java
static int length(Object value) {
    if (!(value instanceof String s)) {
        throw new IllegalArgumentException("not a String");
    }
    return s.length();
}
```

*Đáp án:* **Có.** Nhánh pattern không khớp ném exception, không có đường đi tiếp tục đến `return s.length()`. Mọi đường còn lại đã khớp `String s`.

**Bài 2.** Đoạn sau có hợp lệ không?

```java
return value instanceof String s && s.length() > 1;
```

*Đáp án:* **Có**, nếu đặt trong ngữ cảnh Java hợp lệ, vì vế phải `&&` chỉ chạy khi `instanceof` ở vế trái true.

**Bài 3.** Vì sao đoạn sau lỗi?

```java
return value instanceof String s || s.length() > 1;
```

*Đáp án:* Vế phải `||` chỉ chạy nếu `instanceof` false; lúc đó `s` chưa được ràng buộc. Compiler không cho dùng `s` ở đó.

**Bài 4.** `if (!(value instanceof String s) || s.isBlank()) return;` có thể dùng `s` ở vế phải không?

*Đáp án:* **Có**, vì vế phải chỉ chạy khi phủ định false, tức pattern gốc đã khớp. Sau `if` có `return` ở nhánh true, những đường còn lại cũng đã khớp `String` và không blank.

**Bài 5.** `case TextEvent(var text) when text.isBlank()` có đảm bảo không có NPE không?

*Đáp án:* **Không.** Pattern variable ở đúng scope, nhưng component `TextEvent.text` có thể null. Cần xử lý `text == null` trước hoặc bảo đảm non-null bằng invariant trong constructor.

**Bài 6.** Trong switch, có thể dùng `text` của `case String text` ở `case Integer number` không?

*Đáp án:* **Không.** Mỗi case pattern ràng buộc biến trên đường match riêng; case Integer không ràng buộc text.

**Bài 7.** Tại sao `for (; input instanceof String s && !s.isEmpty(); input=s.substring(1))` có thể sử dụng `s` trong update?

*Đáp án:* Phần update chỉ chạy sau khi điều kiện vòng lặp đã true và phần thân đã thực hiện; pattern đã được ràng buộc trên đường đó. Ví dụ Java 21 ở mục 11 được compiler chấp nhận.

**Bài 8.** Sau vòng `while (value instanceof String s)`, có thể dùng `s` ngay trong câu lệnh tiếp theo chỉ vì nó đã được khai báo trong điều kiện không?

*Đáp án:* **Không mặc định.** Vòng lặp có thể không chạy lần nào hoặc kết thúc khi điều kiện không còn khớp; phải kiểm tra lại ràng buộc theo đường đi cụ thể thay vì dựa vào tên biến xuất hiện trong điều kiện.

**Bài 9.** Có thể thay một nested record pattern bằng type pattern để dễ debug không?

*Đáp án:* **Có.** Có thể kiểm tra object con qua accessor và `instanceof`, rồi tách từng bước. Nếu logic nhiều cấp và cần phân biệt null từng cấp, snapshot variables có thể dễ đọc hơn deconstruction quá sâu. Phải giữ nguyên behavior và test.

**Bài 10.** Trong review, làm cách nào biết một lỗi là scope, dominance hay null safety?

*Đáp án:* Bắt đầu từ diagnostic: `cannot find symbol` tại tên pattern variable thường là scope; `dominated by a preceding case label` là thứ tự case; `NullPointerException` khi gọi method trên component là runtime null safety. Với switch expression thiếu variant, compiler báo không bao phủ hết đầu vào. Không dùng một cách sửa cho tất cả.

## 17. Tài liệu chính thức

- [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394): type pattern và flow scoping, final từ Java 16.
- [JEP 440 – Record Patterns](https://openjdk.org/jeps/440): deconstruction nested record, final từ Java 21.
- [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441): case patterns, guard, dominance và exhaustive switch.
- [JLS Java 21 `6.3 – Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi pattern variables.
- [JLS Java 21 `14.30 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): các quy tắc ngữ nghĩa pattern, including record patterns.
- [JLS Java 21 `14.11 – switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): quy tắc switch và nhánh case.
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
