# Dùng pattern variable ngoài flow scope

## 1. Lỗi này xuất hiện khi nào?

Trong Java, **pattern variable** là biến được khai báo bởi một pattern. Ví dụ, ở biểu thức `value instanceof String text`, tên `text` chỉ có nghĩa khi phép kiểm tra kiểu `String` thành công. Java dùng phân tích luồng điều khiển (*flow scoping*) để xác định **những điểm trong chương trình mà compiler có thể bảo đảm biến pattern đã được ràng buộc**.

Một lỗi thường gặp khi refactor mã cũ là đưa `String text` vào `instanceof`, sau đó cố sử dụng `text` ở mọi vị trí trong phương thức:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}

// KHÔNG BIÊN DỊCH: value có thể không phải String,
// nên text không được ràng buộc trên mọi đường đi.
// System.out.println(text.length());
```

Lời gọi `text.length()` đã được chú thích vì **đây là ví dụ sai có chủ đích**. Kể cả khi dữ liệu mẫu thật sự là `"Java"`, compiler vẫn kiểm tra theo các đường đi có thể có dựa trên kiểu tĩnh `Object`, chứ không cho phép lập trình viên tự suy diễn rằng `value` luôn khớp.

Đừng nhầm **flow scope** với phạm vi của mọi biến cục bộ thông thường: biến pattern không chỉ phụ thuộc dấu ngoặc `{}`; nó còn phụ thuộc việc pattern đã chắc chắn khớp **ở thời điểm sử dụng** hay chưa. Mục tiêu của bài này là nhận diện các vị trí không hợp lệ, hiểu tại sao và sửa mà không đổi hành vi ngoài ý muốn.

## 2. Quy tắc cốt lõi: biến chỉ tồn tại ở nơi mẫu chắc chắn khớp

Xét biểu thức:

```java
value instanceof String text
```

Nó thực hiện hai nhiệm vụ:

1. Kiểm tra giá trị của `value` có khớp type pattern `String` hay không.
2. **Nếu thành công**, ràng buộc biến `text` có kiểu tĩnh `String` với chính giá trị đã kiểm tra.

Khi `value == null` hoặc là một đối tượng không phải `String`, mẫu không khớp và không có biến `text` hợp lệ để sử dụng trên nhánh đó. Việc trình biên dịch từ chối tên biến ngoài phạm vi giúp ngăn những lỗi “dùng dữ liệu chưa được kiểm tra kiểu”.

Với một `if` đơn giản:

```java
if (value instanceof String text) {
    // Hợp lệ: đang ở nhánh pattern đã khớp.
    System.out.println(text.length());
} else {
    // KHÔNG HỢP LỆ nếu bỏ chú thích:
    // System.out.println(text.length());
}
```

Nhánh `else` được thực thi khi điều kiện `instanceof` sai, nên biến `text` không được ràng buộc tại đây.

**Điều cần nhớ:** “Biến được viết trong biểu thức `if`” không có nghĩa nó là biến dùng được cho cả hai nhánh hoặc bên dưới toàn bộ `if`. Flow scoping mô tả điều compiler chứng minh được, không phải một giả định của lập trình viên về dữ liệu sẽ chạy.

## 3. Với &&: dùng biến ở vế phải khi mẫu bên trái khớp

Java đánh giá toán tử `&&` theo cách **ngắn mạch** (*short-circuit*). Vế phải chỉ được xét nếu vế trái là `true`. Vì vậy, đây là cách viết hợp lệ:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

Luồng xử lý:

- Nếu `value` không phải `String` hoặc bằng `null`, `instanceof` là `false` và `text.isBlank()` không chạy.
- Nếu `value` là `String`, `text` được ràng buộc trước khi Java xét vế phải của `&&`.
- Nếu `text` không rỗng theo quy tắc `isBlank()`, phần thân `if` chạy và có thể dùng biến `text`.

Có thể nối thêm điều kiện phụ thuộc:

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 4) {
    System.out.println("Hợp lệ: " + text);
}
```

Điều kiện được đọc theo thứ tự: **khớp kiểu → kiểm tra nội dung → kiểm tra độ dài → xử lý**.

**Không tùy tiện đổi `&&` thành `&`.** Với toán hạng boolean, `&` đánh giá cả hai bên, không có tính ngắn mạch như `&&`. Nếu các toán hạng sau chỉ hợp lệ khi mẫu trước khớp, `&&` mới biểu diễn đúng sự phụ thuộc này.

## 4. Với ||: vì sao biến pattern thường không thể dùng ở vế phải?

Toán tử `||` cũng đánh giá ngắn mạch, nhưng vế phải được xét khi **vế trái sai**. Vì vậy, ví dụ sau không hợp lệ:

```java
// KHÔNG BIÊN DỊCH: text có thể chưa được ràng buộc.
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

Nếu vế trái `value instanceof String text` sai, `text` không tồn tại trên đường đi cần đánh giá `text.isBlank()`. Compiler không cho phép sử dụng đó.

Một biến thể khác cũng dễ mắc:

```java
boolean fallback = true;

// KHÔNG BIÊN DỊCH nếu dùng text trong thân:
// if (value instanceof String text || fallback) {
//     System.out.println(text.toUpperCase());
// }
```

Điều kiện toàn bộ `if` có thể đúng **chỉ vì `fallback` đúng**, dù `value` không phải `String`. Do vậy, trong thân `if` cũng không có bảo đảm rằng `text` đã được ràng buộc.

Cách sửa phụ thuộc ý định:

- Nếu phần xử lý **bắt buộc** có `String`, dùng `&&` để kiểm tra các điều kiện phụ thuộc sau pattern.
- Nếu cho phép một điều kiện thay thế độc lập, hãy tách thành hai nhánh có mục đích rõ ràng; chỉ dùng `text` ở nhánh đã khớp.
- Nếu kết quả chỉ là boolean và không cần biến pattern trong một nhánh khác, có thể dùng `instanceof String` không ràng buộc biến.

Ví dụ sửa không đánh đồng hai trường hợp:

```java
if (value instanceof String text) {
    System.out.println("Chuỗi: " + text);
} else if (fallback) {
    System.out.println("Đường dự phòng");
}
```

Ở đây mỗi đường đi có trách nhiệm riêng, không cố dùng `text` khi `value` không khớp.

## 5. Phủ định pattern và guard clause: hợp lệ khi nhánh thất bại thoát sớm

Một cách viết đặc biệt hữu ích trong code thực tế là **kiểm tra không khớp rồi thoát khỏi phương thức**, ví dụ:

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

Tại dòng cuối, `text` hợp lệ dù nó không nằm trong dấu ngoặc của `if`. Lý do:

1. `!(value instanceof String text)` đúng khi pattern **không khớp**.
2. Trường hợp không khớp kết thúc ngay bằng `return 0`.
3. Mọi đường đi có thể đến `return text.length()` đều đã vượt qua phép thử `instanceof String text` thành công.

Đây là hiệu ứng của phân tích luồng, thường được gọi là **guard clause** (nhánh bảo vệ). Có thể dùng `throw` thay vì `return` khi đầu vào sai kiểu là lỗi hợp đồng:

```java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần String");
    }
    return text;
}
```

Tuy nhiên, **phủ định `instanceof` không tự động kéo dài scope**. Ví dụ sau vẫn sai:

```java
// KHÔNG BIÊN DỊCH nếu dùng text sau if:
// if (!(value instanceof String text)) {
//     System.out.println("Sai kiểu");
// }
// System.out.println(text.length());
```

Nhánh không khớp chỉ in thông báo rồi **vẫn đi tiếp**, nên ở câu lệnh sau compiler không thể bảo đảm `text` tồn tại. Muốn dùng biến sau `if`, cần để nhánh thất bại thực sự kết thúc đường đi liên quan, hoặc đưa phần dùng biến vào nhánh đã khớp.

### Lưu ý về toán tử phủ định kết hợp

Biểu thức:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text);
```

là hợp lệ về flow scope nếu đặt trong một phương thức `void` thích hợp. Nhưng **không nên suy diễn** rằng mọi cách kết hợp `!`, `&&` và `||` đều cho scope như nhau: hãy phân tích điều kiện nào khiến Java đi đến từng toán hạng hoặc nhánh, rồi kiểm tra rằng tất cả đường đi tới chỗ dùng biến đều bảo đảm pattern đã khớp.

## 6. Dùng pattern trong toán tử ?: và phép gán boolean

### Toán tử điều kiện (ternary)

Mẫu có thể ràng buộc biến để dùng ở nhánh được chọn khi điều kiện đúng:

```java
String label = value instanceof String text
        ? "Độ dài: " + text.length()
        : "Không phải chuỗi";
```

Nếu `value` là `String`, biểu thức ở nhánh sau `?` dùng `text` hợp lệ. Nếu không khớp, nhánh sau dấu `:` được chọn và không được giả định có `text`.

Ví dụ sai:

```java
// KHÔNG BIÊN DỊCH:
// String label = value instanceof String text
//         ? "Là String"
//         : "Không phải String: " + text.length();
```

Nhánh `false` không có bảo đảm về biến pattern.

### Chỉ lưu kết quả boolean không mang theo biến

```java
boolean isString = value instanceof String text;

// KHÔNG BIÊN DỊCH: biến text không tự trở thành
// biến cục bộ dùng được sau phép gán boolean.
// System.out.println(text.length());
```

`isString` là một biến boolean thông thường. Dù nó nhận kết quả của `instanceof`, việc đọc `isString` về sau không tự thiết lập flow scope cho `text`. Nếu thật sự cần đối tượng đã kiểm tra, nên thực hiện kiểm tra và xử lý trong cấu trúc điều khiển phù hợp hoặc dùng một guard clause như phần trên.

## 7. Trong switch: biến chỉ dành cho case đã khớp

Từ **Java 21**, pattern matching for `switch` cùng record patterns cho phép chọn nhánh và lấy dữ liệu bên trong một biểu thức:

```java
return switch (value) {
    case String text when !text.isBlank() ->
            "Chuỗi: " + text.toUpperCase();
    case String text ->
            "Chuỗi trống";
    case Integer number ->
            "Số: " + number;
    case null ->
            "Thiếu dữ liệu";
    default ->
            "Loại khác";
};
```

Đây là đoạn minh họa bên trong một phương thức trả về `String`, với `value` đã khai báo. Quy tắc quan trọng:

- Biến `text` trong `case String text when ...` hợp lệ trong **guard `when`** và phần xử lý của đúng case đó.
- Nhánh `case String text` tiếp theo có một biến pattern **riêng**, dù trùng tên.
- Biến `number` chỉ tồn tại ở case `Integer`.
- Không thể dùng `text` từ case `String` trong case `Integer` hoặc sau toàn bộ `switch`.
- Nhánh `case String text` không guard phải đặt **sau** nhánh có guard đặc thù; đặt trước có thể khiến case sau bị *dominated* và báo lỗi biên dịch.
- `case null` giải quyết selector `null`, còn `default` xử lý các kiểu khác.

Nếu một case cần nhiều thao tác trước khi tạo kết quả của `switch expression`, có thể dùng block và `yield`; biến pattern vẫn chỉ thuộc phạm vi hợp lệ của case:

```java
return switch (value) {
    case String text -> {
        String result = text.strip().toUpperCase();
        yield "Chuỗi: " + result;
    }
    case null -> "Thiếu dữ liệu";
    default -> "Loại khác";
};
```

Vì scope phụ thuộc vào cấu trúc case, với code mới nên ưu tiên **switch rule dùng `->`** để ranh giới biến dễ đọc, thay vì trộn nhiều nhánh có *fall-through*.

## 8. Record pattern lồng nhau: scope của biến con

Xét hai record:

```java
record Note(String message) {}
record Envelope(String id, Note note) {}
```

Có thể khớp và phân rã lồng nhau:

```java
if (value instanceof Envelope(
        String id, Note(String message))
        && !message.isBlank()) {
    System.out.println(id + ": " + message);
}
```

Với **JDK 21**, compiler đối chiếu component của `Envelope` và `Note`, sau đó cho phép dùng `id` và `message` trong những vị trí mà mẫu đã khớp. Cả hai biến đều tuân theo quy tắc flow scoping; không phải cứ lấy từ record thì biến tồn tại mọi nơi.

Một trường hợp cần để ý là component lồng bằng `null`. Nếu `note` của `Envelope` bằng `null`, mẫu `Note(String message)` không khớp; do đó **cả mẫu lồng** thất bại, và điều kiện `!message.isBlank()` không được đánh giá.

Tương tự, nếu `note` tồn tại nhưng `message` bằng `null` thì mẫu `String message` không khớp. Trường hợp này cũng không gọi `message.isBlank()`. Tuy nhiên, nếu thay bằng `var message` và kiểu component có thể nhận `null`, cần tự xem xét khả năng null trước khi gọi phương thức của component; không nên giả định mọi cách phân rã record đều loại trừ null.

Khi phân loại nhiều trường hợp:

```java
return switch (value) {
    case Envelope(String id, Note(String message))
            when !message.isBlank() -> id + ": " + message;
    case Envelope envelope -> "Thiếu thông tin";
    case null -> "Không có phong bì";
    default -> "Không phải phong bì";
};
```

Nhánh `Envelope envelope` tổng quát đứng sau xử lý những đối tượng có cấu trúc bên trong không khớp hoặc guard không đạt. Đây là ví dụ minh họa trong phương thức trả về `String`.

## 9. Chương trình Java 21 hoàn chỉnh

Tạo tệp **`PatternFlowScopeDemo.java`**. Chương trình chỉ sử dụng cú pháp hợp lệ; những mẫu không biên dịch ở các phần trước đã được chú thích riêng.

```java
import java.util.Locale;

public class PatternFlowScopeDemo {
    record Note(String message) {}
    record Envelope(String id, Note note) {}

    static String inspect(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Chuỗi: " + text.strip().toUpperCase(Locale.ROOT);
        }
        return "Không có chuỗi hợp lệ";
    }

    static String required(Object value) {
        if (!(value instanceof String text)) {
            return "Sai kiểu";
        }
        return "Dài: " + text.length();
    }

    static String classify(Object value) {
        return switch (value) {
            case String text when !text.isBlank() ->
                    "Có chữ: " + text.toUpperCase(Locale.ROOT);
            case String ignored ->
                    "Chuỗi trống";
            case Integer number when number > 0 ->
                    "Số dương: " + number;
            case Integer number ->
                    "Số không dương: " + number;
            case null ->
                    "Thiếu dữ liệu";
            default ->
                    "Kiểu khác";
        };
    }

    static String inspectEnvelope(Object value) {
        return switch (value) {
            case Envelope(String id, Note(String message))
                    when !message.isBlank() ->
                    id + ": " + message;
            case Envelope envelope ->
                    "Phong bì thiếu thông tin";
            case null ->
                    "Không có phong bì";
            default ->
                    "Không phải phong bì";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(" Java "));
        System.out.println(inspect(12));
        System.out.println(required("abc"));
        System.out.println(required(null));

        System.out.println(classify("hello"));
        System.out.println(classify(" "));
        System.out.println(classify(3));
        System.out.println(classify(-2));
        System.out.println(classify(null));
        System.out.println(classify(3.5));

        System.out.println(inspectEnvelope(
                new Envelope("E1", new Note("OK"))));
        System.out.println(inspectEnvelope(
                new Envelope("E2", null)));
        System.out.println(inspectEnvelope(
                new Envelope("E3", new Note(null))));
        System.out.println(inspectEnvelope(null));
        System.out.println(inspectEnvelope("khác"));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**; không cần bật preview:

```bash
javac -encoding UTF-8 PatternFlowScopeDemo.java
java PatternFlowScopeDemo
```

Kết quả trên standard output:

```text
Chuỗi: JAVA
Không có chuỗi hợp lệ
Dài: 3
Sai kiểu
Có chữ: HELLO
Chuỗi trống
Số dương: 3
Số không dương: -2
Thiếu dữ liệu
Kiểu khác
E1: OK
Phong bì thiếu thông tin
Phong bì thiếu thông tin
Không có phong bì
Không phải phong bì
```

Giải thích:

1. `inspect(" Java ")` khớp `String text`, không blank; `strip()` loại khoảng trắng đầu/cuối và `toUpperCase(Locale.ROOT)` tạo `JAVA`.
2. `inspect(12)` không khớp `String` nên vế phải của `&&` và thân `if` không chạy; trả `Không có chuỗi hợp lệ`.
3. `required("abc")` vượt qua guard phủ định và dùng `text.length()` hợp lệ sau `if`. `required(null)` thoát sớm bằng `Sai kiểu`.
4. `classify("hello")` khớp case `String` có guard `!text.isBlank()`; `classify(" ")` trượt guard và chọn case `String` không guard.
5. Hai số nguyên `3` và `-2` đi vào các case `Integer` riêng, được phân biệt bằng `number > 0`; `null` vào `case null`; số thực `3.5` thuộc kiểu khác và vào `default`.
6. `Envelope("E1", Note("OK"))` khớp pattern lồng, guard đúng nên trả `E1: OK`.
7. `Envelope("E2", null)` không khớp `Note(...)`. `Envelope("E3", Note(null))` không khớp `String message`. Cả hai đều được xử lý bằng case `Envelope envelope` tổng quát.
8. `inspectEnvelope(null)` trả `Không có phong bì` và chuỗi `"khác"` vào `default`.

Trong toàn bộ chương trình, không có chỗ nào sử dụng biến pattern ở nhánh mà compiler chưa thể chứng minh mẫu đã khớp. Đó là lý do những cách viết ngắn gọn vẫn an toàn về phạm vi.

## 10. Bảng so sánh đúng – sai

| Tình huống | Ví dụ ý tưởng | Hợp lệ? | Lý do |
| --- | --- | --- | --- |
| Biến trong nhánh `if` khớp | `if (o instanceof String s) { use(s); }` | Có | Nhánh chạy khi mẫu đúng. |
| Biến trong `else` của phép thử dương | `if (o instanceof String s) ... else use(s);` | Không | Nhánh `else` chạy khi mẫu sai. |
| Biến ở vế phải `&&` | `o instanceof String s && !s.isBlank()` | Có | `&&` chỉ đánh giá vế sau khi mẫu đúng. |
| Biến ở vế phải `||` | `o instanceof String s || s.isBlank()` | Không | Vế phải chỉ được xét khi mẫu sai. |
| Biến sau phép thử phủ định có `return` | `if (!(o instanceof String s)) return; use(s);` | Có, trong phương thức phù hợp | Nhánh không khớp đã kết thúc. |
| Biến sau phép thử phủ định không thoát | `if (!(o instanceof String s)) log(); use(s);` | Không | Đường đi không khớp vẫn đến `use(s)`. |
| Biến trong nhánh đúng của `?:` | `o instanceof String s ? s.length() : 0` | Có | Vế sau `?` chạy khi mẫu đúng. |
| Biến trong nhánh sai của `?:` | `o instanceof String s ? 1 : s.length()` | Không | Vế sau dấu `:` không bảo đảm mẫu khớp. |
| Biến trong `when` | `case String s when s.length() > 0 -> ...` | Có | Guard chỉ xét khi case pattern đã khớp. |
| Biến pattern sang case khác | `case String s -> ...; case Integer i -> use(s);` | Không | Mỗi case có phạm vi riêng. |

Trong bảng, `use(...)` và `log()` là **tên hàm minh họa** để nói về scope, không phải Java API có sẵn. Các biểu thức gắn “Không” được dùng để giải thích lỗi, không phải mã runnable.

## 11. Các lỗi đi kèm khi refactor

### 11.1. Dời lệnh ra ngoài nhánh để “giảm lồng nhau”

Trước:

```java
if (value instanceof String text) {
    System.out.println(text);
}
```

Sau khi dời lệnh:

```java
// SAI: không thể dời xử lý ra ngoài if theo cách này.
// if (value instanceof String text) {
//     // ...
// }
// System.out.println(text);
```

**Sửa:** Giữ phần xử lý trong nhánh khớp hoặc dùng guard phủ định trả về sớm. Khi đổi sang guard clause, cần giữ đúng hành vi ở nhánh không khớp.

### 11.2. Tưởng một cờ boolean giữ được biến đã được ràng buộc

```java
boolean accepted = value instanceof String text;

// SAI: accepted không có tác dụng mở flow scope cho text.
// if (accepted) {
//     System.out.println(text);
// }
```

**Sửa:** Dùng trực tiếp điều kiện pattern ở cấu trúc cần sử dụng biến; nếu không muốn lặp kiểm tra, có thể tổ chức logic thành một phương thức nhận `String` sau khi pattern đã khớp.

### 11.3. Nhầm flow scope với giá trị nullable của component

`value instanceof Envelope envelope` chứng minh `envelope` không null và đúng kiểu `Envelope`, nhưng không chứng minh `envelope.note()` khác null. Nếu truy cập component tham chiếu, hãy xem xét kiểm tra null hoặc nested pattern phù hợp. Không để một phép thử type pattern tạo cảm giác rằng mọi dữ liệu bên trong đã được xác thực.

### 11.4. Đặt biến cùng tên gây xung đột

Nếu đã có một biến cục bộ `text` trong phạm vi trùng với nơi khai báo pattern, việc thêm `instanceof String text` có thể tạo lỗi trùng tên biến hoặc lỗi scope. Chọn tên khác cho biến pattern, hoặc refactor phạm vi biến cũ có chủ đích. Không nên chữa bằng cách bỏ kiểm tra kiểu.

### 11.5. Nhầm lỗi compile-time với lỗi runtime

Sử dụng biến pattern ở nơi không được ràng buộc là lỗi **được trình biên dịch phát hiện**; chương trình không đến được bước chạy để gây `NullPointerException` từ chính cách dùng sai đó. Nhưng một component `null` được ràng buộc bằng `var` rồi bị gọi phương thức mà không kiểm tra có thể gây `NullPointerException` ở runtime; đó là vấn đề khác.

## 12. Checklist sửa lỗi nhanh

Khi thấy báo lỗi liên quan biến pattern không tồn tại hoặc chưa ở phạm vi hợp lệ, hãy kiểm tra:

1. Biến được khai báo ở **pattern nào** và pattern có khả năng không khớp không?
2. Vị trí sử dụng thuộc nhánh `if` đúng, `else` hay nằm sau toàn bộ `if`?
3. Nếu có `&&` hoặc `||`, vế nào được đánh giá khi pattern đúng hoặc sai?
4. Với `!`, nhánh thất bại có `return`, `throw` hoặc cách kết thúc đường đi thích hợp không?
5. Trong `switch`, biến có đang được dùng trong chính `case`/`when` đã ràng buộc nó không?
6. Nếu cần dùng giá trị ở nhiều nơi, nên đưa logic vào nhánh, đặt guard clause, hay đổi thiết kế phương thức?
7. Có đang nhầm phạm vi biến pattern với việc một component được xác nhận không null không?
8. Sau khi sửa, đã biên dịch với đúng phiên bản Java và kiểm tra cả đầu vào khớp, không khớp, `null` chưa?

## 13. Tự kiểm tra

Cho:

```java
Object input = "hello";
```

**Câu A:** Vì sao ví dụ sau sai?

```java
// KHÔNG BIÊN DỊCH:
// if (input instanceof String s) {
//     System.out.println(s.length());
// }
// System.out.println(s.toUpperCase());
```

**Đáp án:** Dòng ngoài `if` có thể chạy khi `input` không phải `String`. Compiler không bảo đảm `s` đã được ràng buộc. Chuyển dòng xử lý vào nhánh đúng hoặc dùng guard trả về sớm.

**Câu B:** Cách viết sau có hợp lệ không?

```java
if (input instanceof String s && s.length() >= 3) {
    System.out.println(s.toUpperCase());
}
```

**Đáp án:** Hợp lệ. `&&` bảo đảm `s.length()` chỉ được gọi sau khi mẫu `String s` khớp. Với dữ liệu ví dụ, chương trình in `HELLO`.

**Câu C:** Khi xử lý `case Envelope(String id, Note(String message)) when !message.isBlank()`, biến `message` hợp lệ ở đâu?

**Đáp án:** Trong guard `when` và phần xử lý của đúng case ấy. Nếu một case khác xử lý `Envelope` thiếu component, case đó cần biến pattern riêng (ví dụ `case Envelope envelope`), không được lấy `message` của case trước.

**Ghi nhớ:** Một pattern variable chỉ được sử dụng ở nơi **compiler chứng minh pattern chắc chắn đã khớp**. Đừng chỉ nhìn vị trí khai báo: hãy đọc luồng điều kiện và các đường thoát. Dùng `&&` đúng chỗ, tránh giả định sai với `||`, tận dụng guard clause có `return`/`throw` và giữ biến trong đúng case của `switch`. Hiểu flow scoping sẽ giúp tránh lỗi biên dịch khi refactor từ `instanceof` và cast thủ công sang pattern matching.
