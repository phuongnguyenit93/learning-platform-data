# Return sớm sau khi match trong Java Pattern Matching

**Return sớm sau khi match** (early return after matching) là cách thoát khỏi phương thức ngay khi một **pattern** đã xác nhận giá trị đầu vào thuộc trường hợp cần xử lý, hoặc khi một pattern **không khớp** và phương thức không thể tiếp tục. Kỹ thuật này đặc biệt hữu ích khi xử lý `Object` có nhiều kiểu runtime, validate dữ liệu đầu vào, phân rã `record`, hoặc muốn tránh các nhánh `else` lồng nhau.

Trong chủ đề **Java Core Pattern Matching → Pattern trong statement**, cần phân biệt hai hình thức:

1. **Match thành công rồi return ngay**: `if (value instanceof String text) { return ...; }`.
2. **Match thất bại thì return sớm (guard clause)**: `if (!(value instanceof String text)) { return ...; }`, sau đó tiếp tục dùng `text` ở phần còn lại của phương thức.

Từ **Java 16**, pattern matching với `instanceof` là tính năng chính thức (JEP 394). **Record patterns** và **pattern matching for switch** trở thành tính năng chính thức trong **Java 21** (JEP 440, JEP 441). Các ví dụ đầy đủ dưới đây dùng **Java 21 trở lên**, không yêu cầu bật preview.

## 1. Return ngay khi `instanceof` pattern khớp

Một type pattern có cú pháp `value instanceof Type variable`. Nếu `value` là đối tượng thuộc kiểu `Type` phù hợp, Java ràng buộc giá trị vào `variable` trong nhánh đã khớp.

```java
// Trích đoạn minh họa: 'value' đã được khai báo là Object.
if (value instanceof String text) {
    return "Text: " + text.trim();
}
if (value instanceof Integer number) {
    return "Number: " + number;
}
return "Unsupported";
```

Thứ tự thực thi:

- Java kiểm tra `value instanceof String text`. Nếu đúng, `text` có kiểu `String`; phương thức trả về kết quả thứ nhất **ngay lập tức**. Các kiểm tra bên dưới không chạy.
- Nếu không khớp `String`, Java thử `Integer number`. Nếu đúng, trả về kết quả thứ hai.
- Nếu cả hai không khớp, chạy câu lệnh `return "Unsupported";` cuối cùng.

So với `if/else if/else`, các nhánh early return làm rõ rằng mỗi trường hợp đã xử lý xong sẽ **kết thúc phương thức**, nên không cần bọc phần còn lại trong `else`. Cách này chỉ nên áp dụng khi việc kết thúc sớm đúng với logic nghiệp vụ.

**Lưu ý:** `instanceof` trả về `false` khi giá trị đầu vào là `null`. Bởi vậy, với `value == null`, hai pattern trên không khớp và đi tới nhánh cuối.

## 2. Guard clause: return khi không match, dùng biến phía sau

Một mẫu rất hữu ích là **phủ định `instanceof`**, trả về trong nhánh lỗi, sau đó viết luồng chính ở cùng mức thụt lề:

```java
// Trích đoạn bên trong phương thức trả về String.
// 'value' có kiểu Object.
if (!(value instanceof String text)) {
    return "Not a string";
}

// Hợp lệ: để đến đây, pattern String text chắc chắn đã khớp.
return "Length: " + text.length();
```

Vì sao `text` còn sử dụng được **sau** câu `if`?

- Nếu pattern **không khớp**, điều kiện `!(...)` đúng và nhánh `if` chạy `return`, kết thúc phương thức.
- Nếu luồng thực thi **đi tiếp xuống dưới** câu `if`, điều đó chứng minh `value instanceof String text` đã khớp.
- Compiler áp dụng **flow scoping**: pattern variable `text` được xem là có trong phạm vi ở những vị trí mà chương trình chứng minh nó đã được ràng buộc.

Đây không phải là “biến có thể truy cập ở mọi nơi sau `instanceof`”. Phạm vi phụ thuộc **luồng điều khiển**.

### Vì sao `return` trong nhánh không match quan trọng?

Đoạn sau **không biên dịch**:

```java
// SAI: minh họa lỗi phạm vi; 'value' là Object.
if (!(value instanceof String text)) {
    System.out.println("Not a string");
}
return text.length(); // Có đường chạy tới đây dù pattern không khớp.
```

Nhánh `if` có thể kết thúc bình thường, nên `text` không chắc đã được gán. Thay bằng `return` hoặc `throw` trong nhánh không match sẽ loại bỏ đường chạy không hợp lệ:

```java
// Trích đoạn hợp lệ trong phương thức trả về int.
if (!(value instanceof String text)) {
    throw new IllegalArgumentException("String required");
}
return text.length();
```

Dùng `return` nếu không khớp là một kết quả nghiệp vụ thông thường; dùng `throw` khi không khớp vi phạm hợp đồng đầu vào và người gọi cần nhận ngoại lệ. Chọn theo API của phương thức, không theo thói quen.

## 3. Match kết hợp điều kiện bằng `&&`

Pattern variable có thể được sử dụng ngay trong điều kiện phía sau của toán tử **short-circuit AND**:

```java
// Trích đoạn: 'input' có kiểu Object.
if (input instanceof String text && !text.isBlank()) {
    return "Valid text: " + text.trim();
}
return "Empty or not text";
```

Java chỉ đánh giá `!text.isBlank()` khi `input instanceof String text` đã đúng. Trong phần bên phải của `&&`, `text` chắc chắn tồn tại và có kiểu `String`.

Đối với `||`, không thể tham chiếu biến như sau:

```java
// SAI: Java không bảo đảm text được tạo khi vế phải được đánh giá.
if (input instanceof String text || text.isBlank()) {
    return "Invalid";
}
```

Khi vế trái của `||` sai, vế phải mới được đánh giá, nhưng đó lại là trường hợp pattern **không khớp**. Compiler báo lỗi vì `text` không có trong phạm vi ở vế phải.

Để từ chối chuỗi trắng và giữ biến phía sau, có thể viết:

```java
// Trích đoạn trong phương thức trả về String.
if (!(input instanceof String text) || text.isBlank()) {
    return "Invalid text";
}
return "Valid: " + text;
```

Trong biểu thức điều kiện này, nhánh trái là `!(input instanceof String text)`. Khi vế phải `text.isBlank()` được đánh giá, phủ định đã sai, nghĩa là pattern gốc **đã khớp**; vì vậy `text` được phép tham chiếu. Nếu toàn bộ điều kiện sai thì phương thức tiếp tục với một `String` không trắng. Tình huống phủ định này minh họa rằng **phạm vi phụ thuộc logic của điều kiện**, không phụ thuộc máy móc vào ký hiệu `&&` hay `||`.

### Không kiểm tra `null` hai lần một cách không cần thiết

`if (input instanceof String text)` đã loại trừ `input == null` cho nhánh thành công. Do đó trong nhánh này, không cần `if (input != null)` chỉ để xác nhận giá trị ngoài cùng. Tuy nhiên, nếu phân rã một `record` có component tham chiếu, component đó **vẫn có thể là `null`** và cần xử lý riêng.

## 4. Return sớm sau khi match một record pattern

Record pattern giúp kiểm tra cấu trúc đối tượng và lấy component thành biến. Với Java 21+:

```java
record Item(String sku, int quantity) {}
record Order(String id, Object detail) {}
```

Một kiểu xử lý là chỉ nhận đối tượng `Order` có `detail` thực sự là `Item`:

```java
// Trích đoạn: 'raw' là Object, ở trong phương thức trả về String.
if (!(raw instanceof Order(var id, Item(var sku, var quantity)))) {
    return "Invalid order shape";
}

if (id == null || id.isBlank()) {
    return "Missing order id";
}
if (sku == null || sku.isBlank()) {
    return "Missing SKU for " + id;
}
if (quantity <= 0) {
    return "Invalid quantity for " + id;
}
return "Accepted " + id + " / " + sku + " x" + quantity;
```

**Giải thích cơ chế match:**

- `Order(var id, ...)` yêu cầu `raw` là `Order` khác `null`. `var id` lấy component `id` vào biến kiểu `String`.
- `Item(var sku, var quantity)` phân rã tiếp component `detail`. Vì `detail` được khai báo `Object`, record pattern lồng nhau còn kiểm tra runtime rằng nó là một `Item`.
- Nếu `raw == null`, không phải `Order`, hoặc `detail == null`/không phải `Item`, **toàn bộ pattern không khớp**, và nhánh guard trả về `"Invalid order shape"`.
- Khi chạy tới các câu `if` phía dưới, compiler biết các biến `id`, `sku`, `quantity` đã được ràng buộc. `quantity` có kiểu `int`, còn `id` và `sku` có kiểu `String` nhưng có thể chứa `null`.
- Mỗi guard clause kiểm tra một yêu cầu riêng và `return` ngay khi gặp lỗi. Nếu qua hết các guard, dữ liệu đã đáp ứng các điều kiện được kiểm tra.

Khi một component chỉ được trích bằng `var`, việc match **không tự bảo đảm component khác `null`**. Đó là lý do phải kiểm tra `id == null` và `sku == null` trước khi gọi `isBlank()`. Nhờ toán tử `||` có tính short-circuit, `isBlank()` chỉ chạy khi biến không `null`.

Đoạn này khác với `if (raw instanceof Order(var id, Item(var sku, var quantity))) { return ...; }`: cách viết positive match phù hợp khi chỉ cần xử lý trường hợp khớp và trả về ngay; cách viết phủ định phù hợp khi muốn các bước validate **tiếp diễn sau guard** mà không lồng nhiều cấp `if`.

## 5. Return bên trong `switch statement` có pattern

Từ Java 21, `switch` có thể dùng type pattern và guard `when`. Trong một **switch statement**, nhánh được chọn có thể thực thi `return` để kết thúc **phương thức chứa switch**:

```java
// Trích đoạn bên trong phương thức trả về String.
switch (value) {
    case String text when text.isBlank() -> {
        return "Blank text";
    }
    case String text -> {
        return "Text length " + text.length();
    }
    case Integer n when n >= 0 -> {
        return "Nonnegative " + n;
    }
    case Integer n -> {
        return "Negative " + n;
    }
    case null -> {
        return "Null";
    }
    default -> {
        return "Other";
    }
}
```

Trong mỗi nhánh:

- Type pattern kiểm tra kiểu của `value` và khai báo pattern variable trong phạm vi nhánh.
- Guard `when` chỉ được kiểm tra khi pattern tương ứng đã khớp.
- `return` kết thúc **phương thức**, không đơn thuần thoát khỏi `switch`. Không có bước chạy tiếp các case sau khi phương thức đã trả về.
- Thứ tự quan trọng: `case String text when text.isBlank()` đứng trước `case String text` để tránh bị nhánh tổng quát che khuất (**dominated case**); tương tự đối với `Integer`.
- `case null` xử lý selector `null`. `default` xử lý các kiểu khác.

Đây là **switch statement**, nên không nhất thiết phải có `default` chỉ để switch statement đầy đủ. Tuy nhiên, nếu một phương thức có kiểu trả về không phải `void` và chỉ dựa vào `return` trong switch, phải bảo đảm mọi đường chạy kết thúc bằng giá trị hợp lệ hoặc có một `return` sau switch cho các trường hợp không được xử lý.

### Khác nhau giữa `return` và `yield`

`switch expression` tạo ra **một giá trị**. Một nhánh block của switch expression dùng `yield` để cung cấp giá trị cho biểu thức:

```java
// Trích đoạn: 'value' có kiểu Object.
return switch (value) {
    case String text -> text.trim();
    case Integer n -> n.toString();
    case null -> "No data";
    default -> "Other";
};
```

Ở đây, `return` **bao quanh toàn bộ switch expression**, trả về kết quả cuối cùng của nó từ phương thức. Nếu một nhánh của switch expression cần nhiều lệnh, dùng block `-> { ... yield expression; }` để cung cấp kết quả. Đừng nhầm `yield` (tạo giá trị cho switch expression) với `return` (thoát khỏi phương thức).

Ví dụ:

```java
// Trích đoạn: 'value' có kiểu Object.
return switch (value) {
    case String text -> {
        String normalized = text.trim();
        yield normalized.isEmpty() ? "(blank)" : normalized;
    }
    case null -> "(null)";
    default -> "(other)";
};
```

Để tránh nhầm về control flow, hãy dùng **return trực tiếp trong switch statement** khi mỗi case muốn kết thúc phương thức, hoặc dùng **return switch expression** khi tất cả case cùng tạo một kết quả.

## 6. Ví dụ hoàn chỉnh Java 21+: match, guard clause, switch

Tạo tệp **`EarlyReturnAfterMatchDemo.java`**:

```java
public class EarlyReturnAfterMatchDemo {
    record Item(String sku, int quantity) {}
    record Order(String id, Object detail) {}

    static String describe(Object value) {
        if (value instanceof String text) {
            return "Text: " + text.trim();
        }
        if (value instanceof Integer number) {
            return "Number: " + number;
        }
        if (value == null) {
            return "No input";
        }
        return "Unsupported: " + value.getClass().getSimpleName();
    }

    static String validate(Object raw) {
        if (!(raw instanceof Order(var id, Item(var sku, var quantity)))) {
            return "Invalid order shape";
        }
        if (id == null || id.isBlank()) {
            return "Missing order id";
        }
        if (sku == null || sku.isBlank()) {
            return "Missing SKU for " + id;
        }
        if (quantity <= 0) {
            return "Invalid quantity for " + id;
        }
        return "Accepted " + id + " / " + sku + " x" + quantity;
    }

    static String classify(Object value) {
        switch (value) {
            case String text when text.isBlank() -> {
                return "Blank text";
            }
            case String text -> {
                return "Text length " + text.length();
            }
            case Integer n when n >= 0 -> {
                return "Nonnegative " + n;
            }
            case Integer n -> {
                return "Negative " + n;
            }
            case null -> {
                return "Null";
            }
            default -> {
                return "Other";
            }
        }
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java  "));
        System.out.println(describe(12));
        System.out.println(describe(null));
        System.out.println(describe(2.5));
        System.out.println(validate(new Order("O-1", new Item("SKU-7", 3))));
        System.out.println(validate(new Order("O-2", new Item("SKU-8", 0))));
        System.out.println(validate(new Order("O-3", null)));
        System.out.println(validate(new Order("  ", new Item("SKU-9", 1))));
        System.out.println(validate(new Order("O-4", new Item(null, 1))));
        System.out.println(validate("x"));
        System.out.println(classify("  "));
        System.out.println(classify("abc"));
        System.out.println(classify(0));
        System.out.println(classify(-2));
        System.out.println(classify(null));
        System.out.println(classify(1.5));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**:

```bash
javac -encoding UTF-8 EarlyReturnAfterMatchDemo.java
java EarlyReturnAfterMatchDemo
```

Đầu ra chính xác:

```text
Text: Java
Number: 12
No input
Unsupported: Double
Accepted O-1 / SKU-7 x3
Invalid quantity for O-2
Invalid order shape
Missing order id
Missing SKU for O-4
Invalid order shape
Blank text
Text length 3
Nonnegative 0
Negative -2
Null
Other
```

**Phân tích các trường hợp tiêu biểu:**

1. `describe("  Java  ")` khớp `String text` và trả `"Text: Java"` sau `trim()`. Nhánh `Integer` và những câu lệnh phía sau không chạy.
2. `describe(12)` không khớp `String`, nhưng khớp `Integer number`, rồi trả ngay. Khi truyền `12` cho tham số `Object`, Java dùng autoboxing thành `Integer`.
3. `describe(null)` không khớp type pattern nào, được xử lý bởi `if (value == null)`. `describe(2.5)` nhận đối tượng `Double`, rơi vào nhánh fallback; ở đó `value` chắc chắn khác `null` nhờ guard trước.
4. `validate(new Order("O-1", new Item("SKU-7", 3)))` khớp record pattern lồng nhau, vượt qua tất cả guard và trả kết quả `Accepted`.
5. `Order("O-2", Item("SKU-8", 0))` khớp cấu trúc nhưng bị guard `quantity <= 0` từ chối. `Order("O-3", null)` không khớp record pattern lồng nhau nên trả `Invalid order shape`.
6. Với `id` là chuỗi toàn khoảng trắng hoặc `sku` bằng `null`, guard clause thích hợp trả về thông báo trước khi dùng các giá trị này.
7. `classify` dùng `switch statement` với type pattern, `when`, `case null` và return trực tiếp. Các cặp guard/nhánh tổng quát bao phủ đúng những trường hợp cùng kiểu.

## 7. Phạm vi biến và ngữ nghĩa control flow cần nhớ

### `return` thoát khỏi phương thức

`return expression;` trả về một giá trị và kết thúc **lần gọi phương thức đang chạy**. Nó không chỉ “thoát nhánh if” để chạy tiếp câu lệnh sau nhánh. Với phương thức `void`, dạng trả về sớm hợp lệ là `return;` không có biểu thức:

```java
// Trích đoạn bên trong phương thức void log(Object input).
if (!(input instanceof String text)) {
    return; // Không có gì để log.
}
System.out.println(text);
```

Trong lambda, `return` (nếu được phép trong block lambda) kết thúc **lambda đó**, không tự động thoát khỏi phương thức bao ngoài đang gọi lambda. Vì vậy không nên dùng các lệnh `return` của callback/lambda để thay thế guard clause ở cấp phương thức khi cần dừng toàn bộ xử lý.

### Pattern variable chỉ tồn tại khi được chứng minh đã match

| Ngữ cảnh | Có thể dùng biến? | Lý do |
| --- | --- | --- |
| Bên trong `if (x instanceof String s) { ... }` | Có | Nhánh chỉ chạy khi pattern khớp |
| Vế phải `&&` trong `x instanceof String s && s.length() > 0` | Có | Short-circuit bảo đảm vế trái đã đúng |
| Phía sau `if (!(x instanceof String s)) return ...;` | Có | Nếu đi tiếp, pattern gốc chắc chắn khớp |
| Sau `if (!(x instanceof String s)) println(...);` | Không chắc; thường lỗi biên dịch nếu tham chiếu `s` | Nhánh không match vẫn có thể đi tiếp |
| Trong guard `when` và body của `case String s` | Có | Pattern đã khớp trước guard và body |
| Trong nhánh case khác hoặc bên ngoài switch | Không | Biến không có phạm vi ở những nơi đó |

### Pattern match không thay thế validation nghiệp vụ

`input instanceof Order(var id, Item(var sku, var quantity))` bảo đảm cấu trúc kiểu và trích component, nhưng **không tự bảo đảm** `id` hợp lệ, `sku` không `null`, `quantity` dương hoặc các quy tắc kinh doanh khác. Những điều kiện này phải được kiểm tra riêng.

Nếu một phương thức trả về sớm, phần cleanup quan trọng đã được cấu trúc đúng cần vẫn được thực hiện. Ví dụ, khi dùng try-with-resources, các resource được đóng khi thoát scope, kể cả khi return; tránh viết logic nghiệp vụ phụ thuộc vào một câu lệnh phía sau có thể bị bỏ qua bởi early return.

## 8. So sánh cách viết và tiêu chí lựa chọn

| Cách viết | Dùng khi nào | Điểm chú ý |
| --- | --- | --- |
| `if (x instanceof T v) return result;` | Chỉ xử lý riêng trường hợp match rồi kết thúc | Có thể xếp nhiều nhánh pattern nối tiếp |
| `if (!(x instanceof T v)) return fallback;` | Input bắt buộc phải match, trường hợp còn lại là luồng chính | Biến `v` có thể nằm trong phạm vi bên dưới nhờ flow scoping |
| `if (x instanceof T v && guard(v)) return result;` | Chỉ return cho subtype và điều kiện hợp lệ | Guard chỉ chạy khi đã match |
| `switch (x) { case T v -> { return ...; } ... }` | Nhiều kiểu cần xử lý riêng trong cùng phương thức | Guard cụ thể trước case tổng quát; cân nhắc null/default |
| `return switch (x) { case T v -> ...; ... };` | Các nhánh cùng sinh ra một giá trị | Switch expression phải exhaustive; block dùng `yield` |

Guard clause giúp code dễ đọc khi điều kiện tiên quyết có thể được kiểm tra nhanh trước phần xử lý chính. Tuy nhiên, **không nên có quá nhiều return rải rác** nếu phương thức phải thực hiện một bước cuối bắt buộc cho mọi trường hợp (ví dụ cập nhật transaction state, audit hoặc thống kê). Khi đó, cân nhắc tách các bước thành phương thức nhỏ hoặc gom luồng thực thi ở một chỗ thích hợp.

## 9. Các lỗi thường gặp

| Lỗi | Vì sao | Cách sửa |
| --- | --- | --- |
| Truy cập `text` sau `if (x instanceof String text) { ... }` khi có đường đi không match | Biến có thể chưa được ràng buộc | Dùng trong nhánh match, hoặc phủ định pattern và return khi không khớp |
| Nhánh `if (!(x instanceof String text))` chỉ in log, rồi dùng `text` phía dưới | Log không bảo đảm thoát phương thức | Dùng `return`/`throw` hoặc tổ chức lại control flow |
| Đọc `text` ở vế phải `x instanceof String text || ...` | `text` không có trong phạm vi khi vế trái sai | Dùng logic điều kiện có short-circuit bảo đảm match, ví dụ `&&` |
| Cho rằng `instanceof` khớp `null` | Type pattern không khớp `null` | Thêm nhánh xử lý `null` khi cần |
| Cho rằng `var sku` từ record pattern luôn khác `null` | Component tham chiếu có thể null | Kiểm tra `sku == null` trước khi gọi phương thức |
| Bỏ qua bước validate sau khi record pattern khớp | Match chỉ chứng minh cấu trúc/kiểu, không chứng minh nghiệp vụ hợp lệ | Thêm guard clauses tương ứng |
| Đặt `case String s` trước `case String s when s.isBlank()` | Case rộng che case có guard, Java báo dominance error | Đặt guard cụ thể trước |
| Nhầm `return` với `break` hay `yield` | Ba lệnh có vai trò control flow khác nhau | `return` thoát phương thức; `yield` tạo kết quả switch expression; `break` thoát switch statement/loop tương ứng |
| Viết nhiều nhánh return nhưng bỏ quên cleanup nghiệp vụ | Câu lệnh sau return không chạy | Thiết kế đường kết thúc rõ ràng, dùng scope/try-with-resources hoặc tách phương thức phù hợp |
| Dùng record pattern trên Java 17 không bật preview | Record patterns chưa chính thức trên Java 17 | Dùng Java 21+ hoặc chỉ sử dụng type pattern của `instanceof` |

## 10. Bài tập tự luyện

Cho hai record:

```java
record Customer(String id, String email) {}
record Envelope(Object payload) {}
```

**Bài 1.** Viết phương thức trả về `"Not a customer"` nếu `input` không phải `Customer`. Nếu khớp, sử dụng `id` và `email` phía sau guard để trả về `id + ": " + email`.

**Đáp án:**

```java
// Trích đoạn trong một lớp chứa các record đã khai báo.
static String customerLabel(Object input) {
    if (!(input instanceof Customer(var id, var email))) {
        return "Not a customer";
    }
    return id + ": " + email;
}
```

Điều kiện match ở đây không kiểm tra `email` khác `null`; nếu nghiệp vụ yêu cầu email hợp lệ, phải validate riêng.

**Bài 2.** Cho `Object raw`, chỉ nhận `Envelope` có payload là `String` không trắng. Trả về `"Invalid"` nếu không hợp lệ, nếu hợp lệ trả về bản trim.

**Đáp án:**

```java
static String normalized(Object raw) {
    if (!(raw instanceof Envelope(String text)) || text.isBlank()) {
        return "Invalid";
    }
    return text.trim();
}
```

Nếu `raw` không phải `Envelope` hoặc payload không phải `String` khác `null`, vế trái của `||` đúng và vế phải không chạy. Nếu pattern khớp, compiler cho phép dùng `text` trong `text.isBlank()` và sau câu guard.

**Bài 3.** Viết `switch statement` trong phương thức `static String category(Object value)`: chuỗi trắng trả `"Blank"`, chuỗi khác trả `"Text"`, số `Integer` trả `"Integer"`, `null` trả `"Null"`, các trường hợp còn lại trả `"Other"`.

**Đáp án:**

```java
static String category(Object value) {
    switch (value) {
        case String s when s.isBlank() -> { return "Blank"; }
        case String s -> { return "Text"; }
        case Integer n -> { return "Integer"; }
        case null -> { return "Null"; }
        default -> { return "Other"; }
    }
}
```

Nhánh có guard phải ở trước nhánh `String` rộng hơn. Mỗi nhánh `return` trực tiếp, nên không cần thêm `return` sau switch.

**Bài 4.** Vì sao đoạn này không thể sử dụng `text` sau `if`?

```java
if (!(input instanceof String text)) {
    System.out.println("Invalid");
}
System.out.println(text);
```

**Đáp án:** Đường chạy không match vẫn đi tiếp sau khi in log, nên `text` có thể chưa được khai báo trong phạm vi hợp lệ. Thêm `return;` (trong phương thức `void`) hoặc `throw` trong nhánh lỗi, hay chuyển thao tác in `text` vào nhánh match.

## 11. Tóm tắt kiến thức và nguồn tham khảo

- **Positive match + return**: khi pattern khớp, dùng ngay các biến đã ràng buộc và kết thúc phương thức.
- **Negative guard + return**: khi pattern không khớp, dừng sớm; code phía sau có thể sử dụng pattern variable nhờ quy tắc flow scoping.
- Với `&&`, guard phía sau có thể dùng biến của pattern đã khớp; với phủ định pattern kết hợp `||`, chỉ dùng được biến khi logic điều kiện chứng minh pattern gốc đã khớp.
- Record pattern lồng nhau cho phép trích nhiều component, nhưng chỉ chứng minh điều kiện cấu trúc/kiểu; kiểm tra `null` và nghiệp vụ riêng.
- Trong `switch statement`, `return` trong nhánh kết thúc phương thức. Trong `switch expression`, các nhánh tạo giá trị bằng biểu thức hoặc `yield`; `return switch (...)` trả kết quả cả biểu thức.
- Chọn early return để giảm lồng nhau và làm rõ các điểm kết thúc, đồng thời đảm bảo những bước cuối cần thiết vẫn được thiết kế an toàn.

Tài liệu chính thức: [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
