# Tính giá trị từ pattern switch trong Java 21

## 1. Mục tiêu: dùng pattern matching để tạo ra một giá trị

Khi biểu thức đầu vào có thể thuộc nhiều kiểu dữ liệu, ta thường muốn **tính ra một giá trị duy nhất** dựa trên kiểu và nội dung của đầu vào: chuỗi mô tả kết quả, số điểm, phí xử lý, trạng thái hiển thị hoặc dữ liệu đầu ra cho API. Từ Java 21, **pattern matching for `switch`** là tính năng chính thức (JEP 441), cho phép đặt **type pattern**, **record pattern** và điều kiện `when` trong từng nhánh `case`. Khi viết dưới dạng **`switch expression`**, toàn bộ `switch` được đánh giá thành một giá trị.

Ví dụ ngắn với `Object input`:

```java
String message = switch (input) {
    case String text -> "Text: " + text;
    case Integer number -> "Number: " + number;
    case null -> "Missing";
    default -> "Unsupported";
};
```

Đọc ví dụ: nếu `input` là chuỗi, biến `text` được ràng buộc với chuỗi đó và nhánh trả về `"Text: " + text`; nếu là `Integer`, nhánh thứ hai tạo chuỗi khác. `switch` expression có giá trị kiểu `String` nên có thể gán vào `message`.

Mục tiêu của bài:

- Phân biệt `switch expression` (tính giá trị) và `switch statement` (thực thi câu lệnh).
- Dùng `case Type variable`, `case Record(...)` và `when` để chọn cách tính giá trị.
- Hiểu `->`, block có `yield`, kiểu kết quả, yêu cầu tính đầy đủ (**exhaustiveness**) và cách xử lý `null`.
- Tránh các lỗi compiler thường gặp: nhánh không sinh giá trị, thiếu nhánh, nhánh bị che khuất (domination), đặt `return`/`break` sai.
- Xây dựng hàm Java 21+ độc lập, chạy được và dự đoán đúng đầu ra.

Các ví dụ chính dùng **JDK 21+**, vì record patterns cũng được chuẩn hóa ở Java 21 (JEP 440). Không cần bật `--enable-preview`.

## 2. Cú pháp tính giá trị: `case ... -> value`

Mẫu thông dụng:

```java
ResultType result = switch (selector) {
    case PatternA -> expressionA;
    case PatternB when condition -> expressionB;
    case null -> expressionForNull;
    default -> fallbackExpression;
};
```

Trong đó:

1. `selector` là biểu thức đầu vào, ví dụ một biến kiểu `Object` hoặc một interface.
2. `PatternA` và `PatternB` thử khớp kiểu/cấu trúc đầu vào và có thể khai báo biến pattern.
3. `when condition` là điều kiện bổ sung được kiểm tra **sau khi pattern khớp**; điều kiện có thể dùng các biến vừa được ràng buộc.
4. Phần sau `->` tính giá trị của nhánh. Với nhánh một biểu thức, Java lấy luôn giá trị đó làm kết quả của `switch expression`.
5. `;` sau dấu `}` kết thúc câu lệnh gán hoặc `return` chứa biểu thức `switch`.

Ví dụ tính giá trị số nguyên:

```java
// Đặt trong phương thức có biến Object value.
int score = switch (value) {
    case Integer n when n > 10 -> n * 2;
    case Integer n -> n;
    case String s -> s.trim().length();
    case null -> 0;
    default -> -1;
};
```

Tại một thời điểm chỉ có **một nhánh được chọn**. Nếu `value == 12`, nhánh có `when n > 10` trả về `24`; nếu `value == 8`, nhánh `Integer` tiếp theo trả về `8`; nếu là `"  Java  "`, nhánh `String` trả về `4`. Các nhánh dạng `->` không rơi xuyên (fall-through) sang nhánh sau.

Khác với câu lệnh `switch` dùng để thực thi hành động, `switch expression` **phải có kết quả cho mọi đường chạy bình thường**. Nhánh `throw` kết thúc bằng ngoại lệ cũng hợp lệ vì không có luồng chạy bình thường đi qua nhánh đó.

## 3. Trả kết quả bằng `return switch (...)`

Có thể trả trực tiếp giá trị của `switch expression` từ phương thức:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> "text(" + s.length() + ")";
        case Integer n -> "integer(" + n + ")";
        default -> "other";
    };
}
```

`return` ở đây thuộc về **phương thức `describe`**. Bên phải `return` là **một biểu thức `switch`**, và giá trị của biểu thức đó chính là giá trị trả về của phương thức.

Không nhầm với đoạn sau:

```java
// Minh họa switch STATEMENT, không phải switch expression.
static String describeStatement(Object value) {
    switch (value) {
        case String s -> {
            return "text(" + s.length() + ")";
        }
        default -> {
            return "other";
        }
    }
}
```

Ở ví dụ thứ hai, `switch` là **statement** vì nó được dùng như câu lệnh độc lập; các lệnh `return` bên trong từng nhánh trực tiếp thoát khỏi phương thức. Hai cách đều có thể dùng, nhưng `return switch (...) { ... };` thường thể hiện rõ ý đồ ánh xạ đầu vào thành một giá trị duy nhất và giúp tránh lặp `return`.

## 4. Một nhánh có nhiều câu lệnh: dùng `yield`

Khi phần tính giá trị cần nhiều thao tác (kiểm tra, tính tạm, định dạng), đặt các câu lệnh trong block `{ ... }` rồi dùng **`yield`**:

```java
// Đoạn minh họa trong phương thức trả về int.
return switch (value) {
    case String text -> {
        String normalized = text.trim();
        int length = normalized.length();
        yield length;
    }
    case Integer number -> number;
    default -> 0;
};
```

`yield length;` nói với Java rằng **giá trị của nhánh `switch expression` là `length`**. Nó kết thúc việc đánh giá nhánh và chuyển giá trị ra ngoài `switch`. `yield` khác `return`: `yield` trả giá trị cho biểu thức `switch`, còn `return` trả giá trị cho phương thức chứa nó.

Đối với `switch expression`:

- `case ... -> expression;` phù hợp khi tính toán đơn giản.
- `case ... -> { ...; yield expression; }` phù hợp khi cần một block gồm nhiều lệnh.
- `case ... -> throw new IllegalArgumentException(...);` hợp lệ khi tình huống đó phải thất bại.
- Không dùng `break 10;` để trả giá trị; cú pháp trả giá trị là `yield 10;`.
- Một block nhánh không thể kết thúc bình thường mà không sinh giá trị. Nếu cần nhiều hướng xử lý, mỗi hướng kết thúc phải `yield` hoặc `throw` tương ứng.

Với cú pháp dấu hai chấm cũ, `switch expression` cũng sử dụng `yield` để sinh giá trị:

```java
int length = switch (value) {
    case String s:
        yield s.length();
    default:
        yield 0;
};
```

Tuy nhiên, cú pháp `->` thường dễ đọc hơn khi xử lý pattern và tránh nhầm với fall-through của `switch statement` kiểu cũ.

## 5. Type pattern và `when`: tính giá trị theo kiểu cùng điều kiện

Pattern `case Integer n` vừa kiểm tra xem selector có khớp với `Integer` hay không, vừa khai báo biến `n` cho phần tính toán. Guard `when` bổ sung điều kiện:

```java
static int adjust(Object input) {
    return switch (input) {
        case Integer n when n >= 100 -> n + 10;
        case Integer n when n >= 0 -> n;
        case Integer n -> 0;
        case null -> 0;
        default -> -1;
    };
}
```

Thứ tự nhánh mang ý nghĩa:

1. `Integer` từ 100 trở lên: cộng thêm 10.
2. `Integer` không âm nhỏ hơn 100: giữ nguyên.
3. `Integer` âm: trả 0.
4. Selector `null`: trả 0.
5. Kiểu không được hỗ trợ: trả -1.

Các `when` được xét sau khi pattern tương ứng khớp. Nếu `n >= 100` là false, Java có thể thử nhánh tiếp theo. Biến `n` trong từng nhánh chỉ dùng trong guard và phần xử lý của nhánh đó, không phải một biến chung cho toàn bộ phương thức.

**Phải đặt nhánh hẹp trước nhánh rộng.** Nếu viết `case Integer n -> n;` lên đầu, rồi mới đặt `case Integer n when n >= 100 -> ...;` thì nhánh có `when` bị nhánh rộng che khuất; compiler có thể báo lỗi **dominated case label**.

Không nên dùng điều kiện `when` để làm nhiều side effect phức tạp. Mục đích chính của guard là nói rõ tình huống nào thuộc nhánh đang tính giá trị.

## 6. Record pattern: lấy component rồi tạo giá trị

Java 21 cho phép pattern `case RecordType(componentPatterns...)`. Nó kiểm tra record và phân rã các component ngay tại nhánh `case`:

```java
record Item(String sku, int quantity) {}

// Đặt trong phương thức nhận Object value, trả về String.
return switch (value) {
    case Item(String sku, int quantity) when quantity > 0
            -> sku + " x " + quantity;
    case Item(var sku, var quantity) -> "empty item " + sku;
    case null -> "missing item";
    default -> "unsupported";
};
```

Nếu selector là `new Item("BK-1", 3)`, kết quả là `"BK-1 x 3"`. Record pattern giúp ta tính chuỗi từ `sku` và `quantity` mà không cần gọi `item.sku()`/`item.quantity()` sau khi đã khớp.

Record pattern cần **đủ số component và đúng thứ tự** trong khai báo record. Với `record Item(String sku, int quantity)`, `Item(var sku)` không hợp lệ vì thiếu component. Có thể dùng `var` để suy luận kiểu trong pattern, hoặc ghi rõ `String sku`/`int quantity`. Một record pattern chỉ khớp khi giá trị record ở vị trí đó khác `null` và cấu trúc con được yêu cầu khớp; việc lấy component bằng `var` không bảo đảm mọi component đều khác `null`.

Ví dụ có record lồng:

```java
record Address(String city) {}
record User(String id, Address address) {}

static String destination(Object input) {
    return switch (input) {
        case User(var id, Address(var city)) when city != null -> id + "@" + city;
        case User(var id, var address) -> "No city for " + id;
        case null -> "Missing user";
        default -> "Unsupported";
    };
}
```

Ở nhánh đầu, `Address(...)` là một record pattern lồng trong `User(...)`, nên cả user lẫn address đều phải khớp. Guard `city != null` kiểm tra component chuỗi. Nhánh `User(...)` thứ hai vẫn bắt được user có `address == null` hoặc thành phố trống/null tùy nội dung, rồi trả về thông báo khác.

## 7. Tính đầy đủ (exhaustiveness) của switch expression

Vì `switch expression` phải có giá trị trên mọi đường chạy bình thường, compiler yêu cầu các nhánh xử lý **đầy đủ tất cả các trường hợp có thể có** theo kiểu tĩnh của selector.

### Selector là `Object`: thường cần `default`

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "S:" + s;
        case Integer n -> "I:" + n;
        case null -> "null";
        default -> "other";
    };
}
```

`Object` còn có thể chứa vô số kiểu khác `String` và `Integer`, nên nhánh `default` là cần thiết. Nếu bỏ `default`, compiler không thể chứng minh rằng mọi giá trị đều có nhánh trả kết quả.

### Selector là sealed hierarchy: có thể không cần default

Với `sealed interface` mà compiler biết đầy đủ các subtype trực tiếp, có thể dùng pattern `case` bao phủ hết các subtype:

```java
sealed interface Payment permits Approved, Declined {}
record Approved(String id, int cents) implements Payment {}
record Declined(int code, String reason) implements Payment {}

static String summarize(Payment payment) {
    return switch (payment) {
        case null -> "Missing payment";
        case Approved(var id, var cents) when cents >= 10000
                -> "large " + id;
        case Approved(var id, var cents) -> "regular " + id;
        case Declined(var code, var reason) -> "declined " + code;
    };
}
```

Các trường hợp `Approved` được bao phủ bằng hai nhánh (guard và nhánh còn lại), `Declined` có một nhánh, còn `null` có nhánh riêng. Do đó `switch expression` đầy đủ dù không có `default`. Nhờ vậy, nếu hierarchy được thay đổi trong mã nguồn và thêm subtype được phép, compiler có thể yêu cầu cập nhật xử lý để duy trì tính đầy đủ.

**Chú ý:** `when` làm một nhánh trở thành nhánh có điều kiện. Chỉ có `case Approved(var id, var cents) when cents >= 10000` thì chưa bao phủ mọi `Approved`. Cần thêm nhánh `Approved` không guard (hoặc nhánh bao quát thích hợp).

### `null` và tính đầy đủ là hai vấn đề khác nhau

Một `case null` bắt selector bằng `null`. Đừng nghĩ `default` sẽ luôn xử lý `null`: khi selector `switch` dựa trên tham chiếu bằng `null` mà không có nhánh phù hợp cho `null`, Java thường ném `NullPointerException`. Nếu `null` là đầu vào hợp lệ của ứng dụng, hãy viết `case null -> ...` rõ ràng hoặc kiểm tra trước khi switch.

Nếu không muốn trả giá trị khi input null, một nhánh `case null -> throw new IllegalArgumentException("Missing input");` cũng hợp lệ.

## 8. Ví dụ Java 21 hoàn chỉnh: trả chuỗi và số từ pattern switch

Tạo tệp **`PatternSwitchValueDemo.java`** như sau:

```java
public class PatternSwitchValueDemo {
    sealed interface Payment permits Approved, Declined {}
    record Approved(String id, int cents) implements Payment {}
    record Declined(int code, String reason) implements Payment {}

    static String summarize(Payment payment) {
        return switch (payment) {
            case null -> "Missing payment";
            case Approved(String id, int cents) when cents >= 10000 -> {
                String tier = "large";
                yield id + ":" + tier + ":" + cents;
            }
            case Approved(String id, int cents) -> id + ":regular:" + cents;
            case Declined(int code, String reason) -> "declined:" + code + ":" + reason;
        };
    }

    static int score(Object value) {
        return switch (value) {
            case null -> 0;
            case Integer n when n > 10 -> n * 2;
            case Integer n -> n;
            case String s -> {
                int trimmedLength = s.trim().length();
                yield trimmedLength;
            }
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(summarize(new Approved("A1", 12000)));
        System.out.println(summarize(new Approved("A2", 5000)));
        System.out.println(summarize(new Declined(403, "blocked")));
        System.out.println(summarize(null));
        System.out.println(score(12));
        System.out.println(score(8));
        System.out.println(score("  Java  "));
        System.out.println(score(new Object()));
        System.out.println(score(null));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**:

```bash
javac --release 21 PatternSwitchValueDemo.java
java PatternSwitchValueDemo
```

Kết quả chính xác:

```text
A1:large:12000
A2:regular:5000
declined:403:blocked
Missing payment
24
8
4
-1
0
```

**Vì sao kết quả như vậy?**

- `Approved("A1", 12000)` khớp record `Approved` và vượt ngưỡng `10000`, nên vào nhánh `when`. Block khai báo `tier` rồi `yield` chuỗi `A1:large:12000`.
- `Approved("A2", 5000)` vẫn khớp record `Approved` nhưng không qua guard, nên vào nhánh `Approved` thứ hai, trả `A2:regular:5000`.
- `Declined(403, "blocked")` khớp record `Declined`, trả `declined:403:blocked`.
- `null` ở phương thức `summarize` được xử lý bằng `case null` và trả `Missing payment`.
- `score(12)`: pattern `Integer n` khớp, guard `n > 10` đúng, trả `24`. Với `score(8)`, guard sai và nhánh `Integer` không guard trả `8`.
- `score("  Java  ")`: nhánh `String` tạo biến `trimmedLength` rồi `yield 4`.
- `new Object()`: không khớp `Integer` hoặc `String`, nên `default` trả `-1`.
- `score(null)`: `case null` trả `0`.

Mã ví dụ sử dụng **hai biểu thức `switch` thực sự trả giá trị**: `summarize` trả `String` và `score` trả `int`. Cả hai đều đặt trực tiếp sau `return`, và mỗi nhánh hoàn thành bằng một biểu thức, `yield`, hoặc (trong các biến thể khác) có thể ném ngoại lệ.

## 9. Kiểu kết quả của switch expression

Khi gán kết quả cho biến hoặc trả kết quả từ phương thức, các nhánh phải tạo ra giá trị **tương thích với ngữ cảnh kiểu**:

```java
// Đoạn minh họa, giả sử có biến Object value.
String label = switch (value) {
    case Integer n -> "count=" + n;
    case String s -> s;
    default -> "unknown";
};
```

Tất cả nhánh sinh `String`, nên `label` có kiểu `String`. Một ví dụ khác, các nhánh sinh `int`:

```java
int total = switch (value) {
    case Integer n -> n;
    case String s -> s.length();
    default -> 0;
};
```

Nếu muốn trả `double`, có thể dùng các giá trị số có thể chuyển đổi phù hợp với target type. Nếu trộn các giá trị hoàn toàn không tương thích với kiểu yêu cầu, compiler báo lỗi. Ví dụ không thể gán một nhánh trả `String` và nhánh khác trả `int` vào biến kiểu nguyên thủy `int`.

**Target type** có thể được xác định từ phép gán, kiểu trả về của phương thức hoặc tham số lời gọi phương thức. Khi dùng `var result = switch (...) { ... };`, compiler phải suy luận kiểu kết quả từ các nhánh; nếu nhiều nhánh có kiểu khác nhau, kiểu chung được xác định theo quy tắc của ngôn ngữ. Để API dễ đọc, thường nên dùng kiểu trả về rõ ràng như `String`, `int` hoặc một interface/record kết quả có chủ đích, thay vì dựa vào kiểu chung quá rộng.

Thực tế, nên thiết kế một switch expression để trả về **một loại ý nghĩa**: cùng là trạng thái, cùng là điểm số, hoặc cùng là đối tượng DTO kết quả. Nếu mỗi nhánh vừa ghi log, vừa thay đổi dữ liệu và trả kiểu khác nhau, tách trách nhiệm thành các phương thức nhỏ sẽ dễ hiểu hơn.

## 10. Lỗi hay gặp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng `case String s -> { s.length(); }` trong switch expression | Block có câu lệnh nhưng **không trả giá trị** cho biểu thức switch. | Dùng `yield s.length();` hoặc viết `case String s -> s.length();`. |
| Viết `break n;` để tính giá trị | `break` không phải cơ chế trả kết quả của switch expression. | Dùng `yield n;` trong block. |
| Bỏ `default` trong `switch (Object value)` khi chỉ xử lý `String` và `Integer` | Chưa đầy đủ cho các kiểu khác. | Thêm `default -> ...` hoặc xử lý kiểu đầu vào bằng một sealed hierarchy đủ trường hợp. |
| Nghĩ `default` luôn bắt `null` | Selector null cần xử lý riêng trong pattern switch; nếu không có case phù hợp sẽ có ngoại lệ. | Thêm `case null -> ...` khi muốn xử lý null như dữ liệu hợp lệ. |
| Đặt `case Integer n -> ...` trước `case Integer n when n > 10 -> ...` | Nhánh không guard bao phủ cả trường hợp có guard, làm nhánh sau bị dominated. | Đặt nhánh có guard trước. |
| `case A(...) when condition` là nhánh duy nhất xử lý subtype `A` | Guard có thể false, nên nhánh không bao phủ toàn bộ `A`. | Thêm nhánh `case A(...) -> ...` còn lại hoặc nhánh phù hợp khác. |
| Gọi biến `s` của `case String s` ở nhánh `Integer` | Biến pattern chỉ có hiệu lực ở guard và phần xử lý nhánh của nó. | Tính kết quả ngay trong nhánh tương ứng; truyền sang phương thức khác qua đối số. |
| Dùng `return` trong block `case ... -> { ... }` của switch expression với ý định trả giá trị về switch | `return` thoát phương thức, không diễn đạt giá trị của nhánh switch expression; tùy vị trí còn bị compiler từ chối. | Dùng `yield` để cho switch expression một giá trị. |
| Dùng cú pháp Java 21 trên Java 17 như cú pháp chuẩn | Pattern matching cho switch và record patterns chưa được chuẩn hóa trong Java 17. | Dùng JDK 21+ cho ví dụ trong bài. |
| Chuyển nguyên switch statement có fall-through sang switch expression mà không kiểm tra | Expression yêu cầu sinh giá trị và khớp đầy đủ. | Thiết kế lại nhánh dùng `->`/`yield` và xác nhận mọi trường hợp đều được bao phủ. |

## 11. Bài tập: định giá theo loại giao dịch

Cho hai record dùng làm dữ liệu đầu vào:

```java
record DigitalPurchase(String sku, int price) {}
record PhysicalPurchase(String sku, int price, int shippingFee) {}
```

Viết phương thức `static int total(Object purchase)` tính kết quả theo quy tắc:

- `DigitalPurchase`: trả `price` nếu không âm.
- `PhysicalPurchase`: trả `price + shippingFee` nếu cả hai số không âm.
- `null`: trả 0.
- Các trường hợp khác (bao gồm dữ liệu không hợp lệ): ném `IllegalArgumentException`.

**Lời giải Java 21** (đặt trong cùng lớp với hai record trên):

```java
static int total(Object purchase) {
    return switch (purchase) {
        case null -> 0;
        case DigitalPurchase(var sku, var price) when price >= 0 -> price;
        case PhysicalPurchase(var sku, var price, var shippingFee)
                when price >= 0 && shippingFee >= 0 -> price + shippingFee;
        default -> throw new IllegalArgumentException("Unsupported purchase");
    };
}
```

Đây là `switch expression` kiểu `int`. Hai nhánh record pattern chỉ trả số khi guard xác nhận các khoản không âm. Nhánh `default` **ném ngoại lệ** chứ không sinh số; điều đó vẫn hợp lệ vì đường chạy ấy kết thúc bất thường. Chẳng hạn `total(new DigitalPurchase("EBOOK", 150))` trả 150; `total(new PhysicalPurchase("BOOK", 200, 30))` trả 230; `total(null)` trả 0; `total(new DigitalPurchase("BAD", -1))` ném `IllegalArgumentException`.

Điểm cần tự đánh giá: nếu một `PhysicalPurchase` có phí vận chuyển âm, nhánh có `when` không khớp; nó sẽ rơi đến `default` và ném ngoại lệ. Nếu yêu cầu nghiệp vụ cần thông báo lỗi khác nhau cho từng record, có thể thêm các nhánh không guard phía sau để phân biệt thay vì gom mọi lỗi vào một `default`.

## 12. Các nguyên tắc chọn cách viết

- Nếu mục tiêu là **ánh xạ một đầu vào thành một giá trị**, ưu tiên `switch expression` và viết `return switch (...) { ... };` hoặc gán kết quả vào biến.
- Với phép tính một dòng, dùng `case Pattern -> expression;`. Với nhiều bước, dùng `case Pattern -> { ...; yield result; }`.
- Dùng pattern để vừa kiểm tra kiểu/cấu trúc vừa lấy biến; dùng `when` cho điều kiện phụ dựa trên các biến ấy. Đặt nhánh cụ thể trước nhánh bao quát.
- Luôn bảo đảm tính đầy đủ: `default` cho kiểu mở như `Object` khi cần; liệt kê mọi subtype trong sealed hierarchy nếu muốn compiler giúp kiểm tra độ bao phủ.
- Xử lý `null` theo hợp đồng hàm bằng `case null` hoặc kiểm tra trước, thay vì ngầm mặc định `default` bắt nó.
- Giữ nhất quán kiểu và ý nghĩa của kết quả; ngoại lệ chỉ dành cho trạng thái lỗi thật sự, không thay thế việc thiết kế nhánh hợp lệ.

**Tài liệu tham khảo:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Java SE 21 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
