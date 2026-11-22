# Scope của pattern variable trong when (Java 21)

## 1. Vấn đề cần hiểu: biến nào thực sự tồn tại trong guard?

Trong Java 21, `switch` có thể dùng *type pattern* hoặc *record pattern* trong nhãn `case`, kèm điều kiện bổ sung `when` (*guard*). Ví dụ:

```java
static String classify(Object input) {
    return switch (input) {
        case String text when text.isBlank() -> "blank";
        case String text -> "text: " + text;
        case null -> "missing";
        default -> "other";
    };
}
```

Đây là một phương thức Java 21 đặt trong lớp. `String text` khai báo **pattern variable `text`**; nếu selector khớp `String`, Java mới đánh giá `text.isBlank()`. Vì vậy, **`text` dùng được trong biểu thức `when`** và trong biểu thức bên phải `->` của nhánh tương ứng. Guard sai thì nhánh đó không được chọn, trình chạy tiếp tục xét nhãn phù hợp khác.

Điều quan trọng hơn: một guard có thể chứa chính phép `instanceof` khai báo *pattern variable mới*, rồi biến mới đó cũng có thể dùng trong thân case khi guard **chắc chắn đúng**. Phạm vi này dựa trên quy tắc **definitely matched** (*mẫu chắc chắn đã khớp*), không chỉ phụ thuộc vị trí dấu ngoặc nhọn.

Mục tiêu của bài:

- Phân biệt biến khai báo **ở pattern của case** với biến khai báo **bên trong guard**.
- Biết biến nào có phạm vi trong `when`, thân `case ->`, khối lệnh `yield` và `switch statement`.
- Hiểu cách `&&`, `||`, phủ định và đường đi đúng/sai ảnh hưởng tới biến được đưa vào phạm vi.
- Tránh lỗi trùng tên, sử dụng biến sang case khác, gán lại biến đang được guard tham chiếu và dereference giá trị nullable.
- Viết ví dụ chạy được với Java 21 chính thức, không dựa vào preview.

**Phiên bản:** `instanceof` type pattern chính thức từ Java 16; pattern matching cho `switch` và guard `when` chính thức từ **Java 21** (JEP 441). Record pattern cũng chính thức từ Java 21 (JEP 440). Các chương trình của bài biên dịch bằng `javac --release 21`.

## 2. Ba bước của một case có when

Hãy đọc câu lệnh sau theo đúng thứ tự:

```java
case String text when text.length() >= 4 -> "long: " + text;
```

Đây là **nhãn/thân nhánh minh họa**, cần đặt trong một `switch` có selector tương thích. Diễn tiến:

1. Java kiểm tra selector có **khớp pattern `String text`** không. Nếu không, case bị bỏ qua; `text` không được ràng buộc cho nhánh này.
2. Nếu khớp, Java có `text` kiểu `String`, rồi **đánh giá `when text.length() >= 4`**. Guard chỉ chạy sau khi biến đã được ràng buộc.
3. Nếu guard là `true`, Java chọn nhánh và thực hiện thân `"long: " + text`; `text` vẫn nằm trong phạm vi tại đó. Nếu guard là `false`, nhánh không được chọn; Java xét tiếp các nhãn khác.

Mô hình khái quát:

```text
Selector
   |
   v
Khớp pattern trong case?
   |-- Không --> thử case tiếp
   |
  Có --> các biến do pattern khai báo được gán
   |
   v
Đánh giá when (guard)
   |-- false --> thử case tiếp
   |
  true --> chạy thân case (có các biến definitely matched)
```

Đây là sơ đồ luồng, không phải cú pháp Java. Sơ đồ không mô tả ngoại lệ: nếu pattern/guard ném ngoại lệ thì `switch` hoàn thành bất thường, **không tự chuyển sang case kế**.

### Quy tắc ngôn ngữ nền tảng

Java Language Specification (JLS 21) `6.3.3 quy định:

- Pattern variable được khai báo trong **case pattern** được *definitely matched* tại **guard** của chính case đó.
- Một **guard** có thể giới thiệu thêm pattern variable nếu biểu thức guard giới thiệu biến khi **kết quả là true**.
- Những biến do nhãn case giới thiệu được *definitely matched* trong **thân switch rule** tương ứng, gồm biểu thức sau `->`, khối lệnh hoặc câu lệnh `throw` (JLS `6.3.1.6 và `6.3.2.6).

Đó là lý do Java cho dùng `text` ở cả `when` và thân nhánh; đồng thời không cho tùy tiện dùng nó trong case khác.

## 3. Biến khai báo ở case pattern: dùng được trong when và thân nhánh

### Type pattern

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text when text.length() > 6 -> "long: " + text;
        case String text -> "short: " + text;
        case Integer number -> "number: " + number;
        case null -> "missing";
        default -> "other";
    };
}
```

Các điểm đáng chú ý:

- Từng `case String text` **khai báo một biến riêng**. Dùng lại cùng tên `text` ở các switch rule độc lập là hợp lệ; không phải một biến được truyền qua nhiều case.
- `text` trong guard được bảo đảm là một đối tượng `String`, nên có thể dùng `isBlank()` và `length()` mà không cần ép kiểu.
- Guard của case thứ hai chỉ được xét nếu case đầu không được chọn và pattern của case thứ hai khớp. Một `String` dài nhưng toàn khoảng trắng sẽ vào case `blank`.
- `Integer number` chỉ cung cấp biến `number` cho case số nguyên; không thể gọi `text` ở đó.
- `case null` và `default` **không giới thiệu** pattern variable `text`.

Khi một case có guard sai, không có chuyện biến của nó “được giữ lại” để dùng tại case tiếp theo. Mỗi case là một lần đối sánh với khai báo riêng.

### Record pattern và nhiều biến thành phần

Giả sử có:

```java
record Point(int x, int y) {}
```

Trong `switch (value)` với kiểu selector phù hợp:

```java
case Point(int x, int y) when x == y -> "diagonal: " + x;
case Point(int x, int y) -> "point: " + x + "," + y;
```

`x` và `y` được khai báo từ **component type patterns** nằm trong record pattern. Chúng đã được ràng buộc khi guard `x == y` chạy và vẫn dùng được trong thân case được chọn. Trường hợp `Point(2, 5)` không khớp guard đầu nên đi vào case `Point` tổng quát kế tiếp.

Nếu record pattern lồng nhau, các biến từ những component pattern hợp lệ cũng được dùng trong guard và thân nhánh, miễn quy tắc tên và kiểu được đáp ứng. Không phải mọi dấu ngoặc `(...)` đều tạo một phạm vi biến Java; việc biến có hiệu lực đến đâu vẫn theo quy tắc pattern scope.

## 4. Biến khai báo ngay trong when bằng instanceof

Đây là điểm dễ bị bỏ sót nhất: **`when` không chỉ đọc biến từ pattern bên trái; nó có thể khai báo thêm biến pattern bằng `instanceof`**.

Ví dụ giả sử có:

```java
record Payload(Object data) {}
```

Một nhánh hợp lệ:

```java
case Payload payload
        when payload.data() instanceof String text
             && !text.isBlank()
        -> "payload-text:" + text.strip();
```

Trong nhãn này có **hai nguồn khai báo**:

| Tên | Được khai báo ở đâu? | Có mặt ở đâu? |
| --- | --- | --- |
| `payload` | Pattern ngoài `Payload payload` | Trong guard và thân case được chọn |
| `text` | `payload.data() instanceof String text` bên trong guard | Trong vế phải `&&` và thân case khi guard true |

Diễn tiến với `new Payload(" Java ")`:

1. Selector khớp `Payload payload`.
2. Guard kiểm tra `payload.data() instanceof String text`; thành công thì `text` là `" Java "`.
3. Do toán tử `&&` chỉ đánh giá vế phải khi vế trái đúng, `text` đã được ràng buộc khi `!text.isBlank()` chạy.
4. Guard true: Java chạy thân nhánh, nên `text.strip()` hợp lệ và trả `"Java"`.

Với `new Payload(42)`, phép `instanceof String` sai; vế phải `&&` không chạy và nhánh này không được chọn. Với `new Payload(null)` cũng vậy. Không có biến `text` nào được dùng trên đường đi không khớp.

**Điểm quy tắc:** Một guard dạng `a instanceof Type t && conditionUsingT` giới thiệu `t` **khi toàn guard đúng**. Bởi JLS `6.3.3, `t` nằm trong phạm vi của thân case. Đây là một ứng dụng cụ thể của *flow scoping*, không phải Java “tự đưa mọi biến của guard ra ngoài”.

### Có thể khai báo theo nhiều kiểu trong nhiều guard riêng

```java
case Payload p when p.data() instanceof String text ->
        "string:" + text;
case Payload p when p.data() instanceof Integer n ->
        "integer:" + n;
case Payload p ->
        "other-payload";
```

Mỗi guard tự đối sánh trường `data` và giới thiệu biến riêng (`text` hoặc `n`). Case `Payload p` không guard ở cuối là nhánh dự phòng cho các payload còn lại. Tên `p` ở các nhãn là các biến độc lập.

## 5. Tại sao && hợp lệ còn || thường không?

Xét câu sau:

```java
case Payload p when p.data() instanceof String text
                    && text.length() >= 3
        -> "ok:" + text;
```

Đây là **case minh họa hợp lệ**: `&&` có tính *short-circuit*. Khi tới `text.length()`, biểu thức bên trái phải đúng nên `text` đã có giá trị. Khi toàn guard true, `text` cũng chắc chắn đã khớp để dùng ở thân.

Ngược lại:

```java
// CỐ Ý SAI: text không chắc đã được ràng buộc ở vế phải ||.
case Payload p when p.data() instanceof String text
                    || text.isEmpty()
        -> "invalid";
```

Vế phải của `||` chạy khi vế trái **sai**. Khi đó `text` không hề được giới thiệu theo nhánh đúng của `instanceof`, nên phép gọi `text.isEmpty()` không hợp lệ về phạm vi biến.

Ngay cả khi vế phải không dùng `text`, guard có thể đúng khi pattern đầu sai:

```java
// CỐ Ý SAI nếu thân cần text: allowAny có thể true khi instanceof sai.
case Payload p when p.data() instanceof String text || allowAny
        -> "text:" + text;
```

Giả sử `allowAny` là biến boolean đã khai báo. Nếu `allowAny` đúng, toàn guard đúng mà `text` chưa chắc có giá trị. Do đó `text` không được xem là definitely matched trong thân case.

**Cách sửa:** Tách riêng các trường hợp, hoặc viết điều kiện `&&` chỉ sử dụng biến sau khi pattern đã khớp.

### Phủ định làm đảo chiều điều kiện khớp

```java
// CỐ Ý SAI: khi !(...) là true thì mẫu String không khớp.
case Payload p when !(p.data() instanceof String text)
        -> "not text:" + text;
```

Trong nhánh này, `text` không thể được bảo đảm có giá trị khi guard true. Muốn mô tả kiểu không phải `String`, không cần khai báo biến trong điều kiện phủ định:

```java
case Payload p when !(p.data() instanceof String)
        -> "not a string";
```

Nếu cần dùng `text`, hãy đặt xử lý ở nhánh `instanceof String text` thành công thay vì nhánh phủ định.

## 6. Phạm vi trong switch expression, block yield và switch statement

### 6.1. Nhánh -> trả biểu thức

```java
static String label(Object value) {
    return switch (value) {
        case String s when s.startsWith("A") -> "A:" + s;
        case String s -> "text:" + s;
        case null -> "missing";
        default -> "other";
    };
}
```

Trong mỗi nhánh, `s` chỉ sống trong vùng được pattern scope cho phép: guard và thân rule tương ứng. Không có khai báo `s` dùng chung sau dấu `};`.

### 6.2. Nhánh -> dùng block và yield

```java
static String normalize(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> {
            String cleaned = s.strip();
            yield "clean:" + cleaned;
        }
        case String s -> "blank";
        case null -> "missing";
        default -> "other";
    };
}
```

Biến `s` dùng được trong khối `{ ... }` của rule đã chọn; `cleaned` là **biến cục bộ mới** chỉ thuộc block đó. `yield` trả giá trị của `switch expression`. Dùng `return` để thay `yield` trong khối này là không đúng vai trò.

### 6.3. Switch statement

Java 21 cũng hỗ trợ pattern matching ở `switch statement`:

```java
static void print(Object input) {
    switch (input) {
        case String s when s.isBlank() ->
                System.out.println("blank");
        case String s ->
                System.out.println("text:" + s);
        case null ->
                System.out.println("missing");
        default ->
                System.out.println("other");
    }
}
```

Với mỗi switch rule, pattern variable có mặt ở **câu lệnh hoặc block** thuộc rule đó. Khi chọn nhánh đầu, `s` dùng được trong guard lẫn lời gọi `println`, nhưng không dùng được trong statement của case khác hay sau toàn bộ `switch`.

**Lưu ý về nhãn dấu hai chấm (`case ...:`):** JLS cũng quy định phạm vi cho *switch labeled statement group*. Nhưng nhiều nhãn chung, luồng rơi xuyên (*fall-through*) và biến chỉ được gán khi pattern khớp tạo ràng buộc khó đọc; nên ưu tiên `->` cho ví dụ học tập và xử lý độc lập theo kiểu.

## 7. Ranh giới không thể vượt: case khác, default, null, sau switch

Một biến khai báo từ case **không phải** biến phương thức được khai báo cho mọi nhánh.

Ví dụ cố ý sai:

```java
static String wrong(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case Integer n -> text;  // SAI: text không thuộc case Integer.
        default -> "other";
    };
}
```

Khi selector là số nguyên, `text` chưa bao giờ được ràng buộc cho case này. Cách sửa: dùng `n` ở case `Integer` hoặc một giá trị kết quả không cần `text`.

Một ví dụ sai khác:

```java
static String wrongAfter(Object value) {
    String answer = switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> text;
        default -> "other";
    };
    return text; // SAI: không có text được giới thiệu sau switch.
}
```

Biến địa phương `answer` (được gán từ kết quả `switch`) mới là biến hợp lệ sau đó. Pattern variable `text` chỉ dành cho các nhánh liên quan.

Với `case null` và `default`, không có một biến từ `case String text` tự động xuất hiện. Trong Java 21, `case null` nhận đầu vào null; `default` của switch pattern thông thường không tự đảm nhận null. Khi không có nhánh xử lý null thích hợp, selector null có thể dẫn đến `NullPointerException` trước khi một thân case thường được chọn.

## 8. Điều kiện final/effectively final của biến được guard tham chiếu

Đây là một **giới hạn quan trọng trong Java 21**: theo JLS `14.11.1, **biến cục bộ, tham số phương thức hoặc tham số ngoại lệ dùng trong guard nhưng không được chính guard khai báo** phải là `final` hoặc *effectively final*.

Điều này áp dụng cả với **pattern variable do case pattern khai báo** khi biến ấy được guard tham chiếu.

### Ví dụ hợp lệ: chỉ đọc biến của case trong guard

```java
static String safe(Object value) {
    int minLength = 3; // Không bị gán lại: effectively final.
    return switch (value) {
        case String text when text.length() >= minLength -> {
            String result = text.strip();
            yield "accepted:" + result;
        }
        case String text -> "too-short:" + text;
        case null -> "missing";
        default -> "other";
    };
}
```

Ở đây cả `text` được dùng trong guard và `minLength` từ bên ngoài đều không bị gán lại. Biến `result` là biến cục bộ khác, dùng để tính giá trị sau khi nhánh được chọn.

### Ví dụ không hợp lệ: gán lại pattern variable đang dùng bởi guard

```java
// CỐ Ý SAI: pattern variable s được guard tham chiếu,
// nhưng lại bị gán lại trong cùng rule.
static String notEffectivelyFinal(Object value) {
    return switch (value) {
        case String s when s.length() > 2 -> {
            s = s.strip(); // SAI với quy tắc effectively final của guard.
            yield s;
        }
        case String s -> s;
        default -> "other";
    };
}
```

Mặc dù pattern variable nói chung **không mặc định `final`** từ Java 16, khi đã được một guard tham chiếu, quy định riêng đối với guard có thể cấm gán lại như trên. Đừng kết luận “pattern variable luôn final”; sự khác biệt nằm ở **việc biến được guard sử dụng**.

Sửa bằng cách tạo biến mới:

```java
case String s when s.length() > 2 -> {
    String normalized = s.strip();
    yield normalized;
}
```

Đây là mảnh case minh họa cho một `switch expression`. Mẫu tương tự áp dụng với biến bên ngoài:

```java
int limit = 3;
// Nếu limit được dùng trong guard và bị gán lại ở phương thức,
// nó không còn effectively final.
```

Nếu sau đó lập trình viên viết `limit++` trong cùng phương thức, một guard tham chiếu `limit` có thể không biên dịch. Dùng hằng hoặc giá trị cục bộ cuối cùng đã xác định trước khi bước vào `switch`.

## 9. Các ràng buộc khác của when ảnh hưởng tới việc dùng biến

### Guard phải là boolean hoặc Boolean

```java
// HỢP LỆ:
case String text when text.length() > 0 -> "nonempty";

// CỐ Ý SAI: length() trả int, không phải boolean.
case String text when text.length() -> "invalid";
```

Nếu guard trả `Boolean`, Java thực hiện unboxing. Giá trị `Boolean` null có thể ném `NullPointerException` khi được unbox; điều đó **không** có nghĩa guard false và nhảy sang case khác.

Ví dụ tránh unboxing null:

```java
// boolean an toàn nếu check(t) có thể trả Boolean null:
case String text when Boolean.TRUE.equals(check(text)) -> "accepted";
```

`check(text)` là **lời gọi tượng trưng** cần được định nghĩa trong lớp. Nếu guard phụ thuộc vào dữ liệu nullable hoặc phương thức có tác dụng phụ, hãy cân nhắc kiểm tra/sắp xếp lại logic thay vì để ngoại lệ bất ngờ trong lúc chọn case.

### Guard phải theo sau case pattern

```java
// CỐ Ý SAI: when không gắn với case pattern.
case 1 when enabled -> "one";
```

Với Java 21, dùng `when` để bổ sung điều kiện cho một **pattern**, không phải hằng số case. `when` là từ khóa ngữ cảnh trong nhãn case; không dùng cú pháp preview cũ `&&` sau pattern:

```java
// CỐ Ý SAI với cú pháp Java 21 ổn định:
case String s && s.isBlank() -> "blank";
```

Viết đúng:

```java
case String s when s.isBlank() -> "blank";
```

Guard là hằng biểu thức `false` bị từ chối ở thời điểm biên dịch; guard hằng `true` có thể được xem như một case không guard trong kiểm tra dominance, không phải biện pháp xử lý phạm vi biến đặc biệt.

### Phạm vi tên vẫn bị kiểm tra xung đột

```java
static String naming(Object input) {
    String text = "outer";
    return switch (input) {
        case String text when text.isBlank() -> "blank"; // SAI: trùng tên.
        default -> "other";
    };
}
```

Đây là ví dụ cố ý không biên dịch: pattern variable không được shadow một biến cục bộ đang có hiệu lực trong phạm vi xung đột. Hãy đặt tên khác:

```java
case String candidate when candidate.isBlank() -> "blank";
```

Ngược lại, hai nhánh `case String text` riêng biệt có thể khai báo lại cùng một tên vì các switch rule có phạm vi tách biệt. Tránh nhầm **tái sử dụng tên ở các case riêng** với **khai báo trùng tên trong cùng một phạm vi**.

## 10. Thứ tự case, dominance và đường đi guard false

Xét:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s;
    default -> "other";
};
```

Với `"Java"`, pattern `String` ở nhánh đầu khớp nhưng guard `isBlank()` **false**; Java tiếp tục xét nhánh `String` thứ hai. Nhánh thứ hai **khai báo biến `s` khác** rồi tạo kết quả.

Nếu đặt case `String` không guard lên trước:

```java
// CỐ Ý SAI do dominance:
return switch (value) {
    case String s -> "any";
    case String s when s.isBlank() -> "blank";
    default -> "other";
};
```

Case đầu đã bao mọi `String` khác null, khiến nhánh có guard phía sau bị che khuất; Java bác bỏ khi biên dịch. Quy tắc thực hành: **guard cụ thể trước, case bao quát cùng kiểu sau**.

Một case có guard chỉ nhận tập con của giá trị khớp pattern. Nếu `switch expression` phải exhaustive, chỉ ghi:

```java
// CỐ Ý SAI nếu thiếu xử lý những String không đáp ứng guard
// và các kiểu khác có thể đến.
return switch (value) {
    case String s when s.length() >= 3 -> "long";
};
```

thì không đủ; cần nhánh bao quát thích hợp. Với selector kiểu `Object`, thông thường cần `default`, và `case null` khi muốn xử lý null rõ nghĩa. Với hierarchy `sealed`, có thể liệt kê đủ kiểu con bằng các case không guard để compiler kiểm tra tính đầy đủ.

## 11. Ví dụ hoàn chỉnh 1: scope trong type pattern, record pattern và guard

Tạo file **`WhenScopeDemo21.java`** với nội dung:

```java
public class WhenScopeDemo21 {

    record Payload(Object data) {}
    record Point(int x, int y) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";

            case Payload p
                    when p.data() instanceof String text
                         && !text.isBlank() ->
                    "payload-text:" + text.strip();

            case Payload p
                    when p.data() instanceof Integer n
                         && n >= 0 ->
                    "payload-int:" + n;

            case Payload p -> "payload-other";

            case Point(int x, int y) when x == y ->
                    "diagonal:" + x;

            case Point(int x, int y) ->
                    "point:" + x + "," + y;

            case String s when s.isBlank() -> "blank";

            case String s -> "string:" + s.strip();

            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe(new Payload(" Java ")));
        System.out.println(describe(new Payload(7)));
        System.out.println(describe(new Payload(null)));
        System.out.println(describe(new Point(2, 2)));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe("  "));
        System.out.println(describe(" hi "));
        System.out.println(describe(1.5));
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 WhenScopeDemo21.java
java WhenScopeDemo21
```

Kết quả chính xác:

```text
null
payload-text:Java
payload-int:7
payload-other
diagonal:2
point:2,5
blank
string:hi
unsupported
```

**Đối chiếu từng loại phạm vi:**

- `Payload p` khai báo biến trong pattern ngoài; `p` có mặt trong guard và trong thân rule được chọn.
- `instanceof String text` ở guard khai báo thêm `text`. Nhờ `&&`, `text` có mặt khi kiểm tra `!text.isBlank()`, và khi guard true, cả thân rule cũng dùng được `text.strip()`.
- Tương tự, `Integer n` nằm trong guard khác, và `n` dùng được khi tính kết quả `payload-int:7`.
- `new Payload(null)` không khớp `instanceof String` hay `instanceof Integer`; nó vào nhánh `Payload p` không guard, không truy cập nhầm một biến chưa ràng buộc.
- `Point(int x, int y)` khai báo `x`, `y` từ record pattern; cả hai biến đã có mặt tại guard `x == y`. Ở case `Point` kế tiếp, hai tên ấy là các khai báo mới.
- `String s` ở hai case chuỗi là hai pattern variables độc lập, dùng được trong guard và thân case tương ứng.
- `default` không có quyền truy cập `text`, `n`, `x`, `y` hay `s` của case khác.

## 12. Ví dụ hoàn chỉnh 2: block, yield và switch statement

Tạo file **`GuardScopeBlock21.java`**:

```java
public class GuardScopeBlock21 {

    record Box(Object content) {}

    static String show(Object value, int minLength) {
        return switch (value) {
            case Box box
                    when box.content() instanceof String text
                         && text.length() >= minLength -> {
                String normalized = text.strip();
                yield "accepted:" + normalized;
            }

            case Box box -> "rejected";
            case null -> "missing";
            default -> "unsupported";
        };
    }

    static void log(Object value) {
        switch (value) {
            case String name when name.isBlank() ->
                    System.out.println("blank");
            case String name ->
                    System.out.println("name:" + name);
            case null ->
                    System.out.println("missing");
            default ->
                    System.out.println("other");
        }
    }

    public static void main(String[] args) {
        System.out.println(show(new Box(" Java "), 4));
        System.out.println(show(new Box("go"), 4));
        System.out.println(show(new Box(null), 4));
        System.out.println(show(null, 4));
        System.out.println(show(42, 4));

        log("   ");
        log("Mai");
        log(null);
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 --release 21 GuardScopeBlock21.java
java GuardScopeBlock21
```

Kết quả:

```text
accepted:Java
rejected
rejected
missing
unsupported
blank
name:Mai
missing
```

Giải thích:

- `box` được khai báo trong case pattern; `text` được khai báo **bên trong `when`** và được guard giới thiệu khi true.
- `text` hợp lệ trong khối bên phải `->`; `normalized` chỉ được khai báo trong chính block đó. `yield` trả giá trị cho `switch expression`, không khai báo biến bên ngoài.
- `minLength` là tham số phương thức được guard tham chiếu và **không bị gán lại**. Do đó nó đáp ứng yêu cầu effectively final.
- Nếu `Box` chứa `null`, `instanceof String text` trả false, thân nhánh có `text` không chạy; nhánh `case Box box` kế tiếp có kết quả `rejected`.
- Ở `log`, `name` chỉ thuộc guard và statement rule tương ứng. Hai nhánh `String name` vẫn là hai khai báo tách biệt. `case null` không có `name`.

## 13. Những lỗi điển hình cần phân biệt

| Tình huống | Lý do | Cách sửa |
| --- | --- | --- |
| `case String s when s.isBlank()` | **Hợp lệ**: `s` từ case pattern dùng được trong guard | Giữ nguyên nếu đúng nghiệp vụ |
| `case Box b when b.content() instanceof String s && !s.isBlank() -> s` | **Hợp lệ**: `s` khai báo trong guard khi true và dùng được trong thân | Giữ nguyên nếu selector và Box phù hợp |
| `... instanceof String s || s.isBlank()` | `s` chưa khớp khi vế phải của `||` chạy | Dùng `&&` hoặc tách nhánh |
| `... instanceof String s || allowAny -> s` | Guard có thể true nhờ `allowAny` mà `s` chưa khớp | Đừng dùng `s` ở thân; tách nhánh |
| `when !(x instanceof String s) -> s` | Guard true khi pattern không khớp | Bỏ tham chiếu `s` hoặc xử lý case đối diện |
| Dùng `s` ở một case `Integer` | `s` của case `String` không nằm trong phạm vi case khác | Khai báo/dùng biến thuộc chính nhánh đang xét |
| Dùng `s` sau toàn bộ `switch` | Pattern variable không được đưa ra khỏi case rule | Gán kết quả của `switch` vào biến địa phương |
| Gán lại `s` ở thân nhánh có `when s...` | `s` được guard tham chiếu, phải final/effectively final | Tạo biến `normalized`, không gán lại `s` |
| Thay đổi biến địa phương ngoài mà guard tham chiếu | Vi phạm yêu cầu effectively final | Giữ biến ổn định hoặc tính giá trị trước switch |
| `case String s when s.length()` | Guard trả `int`, không phải boolean/Boolean | So sánh, ví dụ `s.length() > 0` |
| Guard trả `Boolean null` | Có thể lỗi khi unbox | Dùng điều kiện boolean chắc chắn hoặc `Boolean.TRUE.equals(...)` |
| `case 1 when ...` | `when` chỉ đi cùng case pattern | Dùng type pattern + guard hoặc xử lý hằng riêng |
| Pattern tổng quát trước case có guard | Case sau có thể bị dominance | Đặt guard đặc biệt trước case tổng quát |
| Guard dereference trường nullable | Pattern ngoài không chứng minh component khác null | Dùng `instanceof` / kiểm tra null trước |

Đây là hai loại lỗi **khác nhau**: trình biên dịch phát hiện sai scope/cú pháp/dominance; còn guard truy cập dữ liệu nullable hoặc thực hiện tác dụng phụ có thể gây lỗi **khi chạy**.

## 14. Checklist thiết kế guard dễ bảo trì

Trước khi đưa một case có `when` vào dự án, tự kiểm tra:

1. **Biến nào do case pattern khai báo?** Gạch chân tên đó; nó sẽ sẵn sàng cho guard khi pattern khớp.
2. **Guard có khai báo thêm pattern variable qua `instanceof` không?** Nếu có, chứng minh biến được giới thiệu khi **toàn guard true** rồi mới dùng trong thân.
3. **Toán tử boolean có bảo đảm đường đi không?** Với `&&`, vế phải nhận được biến nếu vế trái đã khớp; với `||` hoặc phủ định, không được suy luận điều tương tự.
4. **Biến được guard tham chiếu có final/effectively final không?** Xem cả việc gán lại trong thân rule hoặc ở vị trí khác trong phạm vi khai báo.
5. **Tên có trùng một biến địa phương đã có không?** Tái sử dụng tên ở các rule tách biệt có thể hợp lệ, nhưng shadow một biến đang có hiệu lực thì không.
6. **Guard có dereference đối tượng nullable không?** Trước khi gọi `.length()` hoặc `.isBlank()` lên giá trị từ accessor, xác nhận null an toàn.
7. **Guard false sẽ đi đâu?** Phải có một nhánh đáp ứng các trường hợp còn lại của kiểu; `switch expression` phải exhaustive.
8. **Nhãn case có sắp từ đặc biệt tới tổng quát chưa?** Không đặt case không guard bao quát trước case có guard cùng kiểu.
9. **Biến được dùng trong đúng rule không?** Không gọi tên pattern variable của nhánh khác hoặc sau toàn bộ `switch`.
10. **Các thử nghiệm có phủ null, guard true, guard false, kiểu khác và record component không?** So sánh đầu ra đúng hợp đồng.

Ưu tiên guard ngắn, thuần (*không tạo side effect*) và dễ đọc. Với điều kiện quá phức tạp, dùng phương thức kiểm tra có tên rõ nghĩa hoặc tách logic nghiệp vụ khỏi biểu thức lựa chọn.

## 15. Bài tập củng cố scope của pattern variable

**Bài 1 — Vùng hợp lệ.** Xét:

```java
case String value when value.length() > 3 -> value.toUpperCase();
```

Cho biết `value` được khai báo ở đâu, vì sao có mặt trong guard, và vì sao được dùng sau `->`. Nếu thêm một case khác, có thể dùng lại chính biến của case này không?

**Bài 2 — Khai báo trong when.** Với `record Message(Object body) {}`, viết case dùng `when m.body() instanceof String content && !content.isBlank()` để trả `content.strip()`. Thêm nhánh xử lý `Message` chứa `Integer` và `null`; giải thích phạm vi của `content`.

**Bài 3 — && và ||.** Thử thay `&&` trong bài 2 bằng `||` rồi tham chiếu `content` ở vế phải và thân case. Dự đoán lỗi compile và giải thích những đường đi nào có thể true khi pattern chưa khớp.

**Bài 4 — Phủ định.** Viết case riêng cho `Message` không chứa chuỗi. Dùng `!(m.body() instanceof String)` mà không cố đọc pattern variable chưa được ràng buộc. Viết thêm case cho thông điệp chứa chuỗi.

**Bài 5 — Effectively final.** Viết `case String s when s.length() > 2 -> { s = s.strip(); yield s; }` và thử biên dịch. Sửa bằng `String cleaned = s.strip(); yield cleaned;`; giải thích vì sao không thể dùng phép gán lại `s` như ban đầu.

**Bài 6 — Record pattern.** Tạo `record Range(int low, int high)`. Viết `case Range(int low, int high) when low <= high -> ...` và một case `Range` dự phòng. Chứng minh `low`, `high` dùng được ở guard và trong thân rule nào.

**Bài 7 — Scope sau switch.** Viết phương thức nhận `Object`, dùng `switch expression` để tạo `String description`. Sau `switch` chỉ dùng `description`, không tham chiếu các pattern variable riêng của case. Thử gõ tên pattern variable ngoài switch để quan sát lỗi biên dịch.

**Bài 8 — Kiểm thử.** Chạy cả hai chương trình hoàn chỉnh. Với `WhenScopeDemo21`, thêm `new Payload("")` và `new Payload(-1)`, dự đoán nhánh được chọn. Với `GuardScopeBlock21`, thử `show(new Box("abc"), 3)` và `show(new Box("abc"), 4)`, phân biệt kết quả khi guard true và false.

### Câu hỏi tự đánh giá

- Tại thời điểm chạy `when`, Java đã chắc chắn điều gì về pattern variable khai báo bởi case?
- Biến được giới thiệu bên trong guard có thể được dùng trong thân case trong điều kiện nào?
- Vì sao `&&` hỗ trợ scope của `instanceof` pattern còn `||` không bảo đảm điều đó?
- `when` sai có làm biến từ case cũ xuất hiện ở case tiếp theo không?
- Hai nhãn `case String s` độc lập là hai khai báo hay một biến dùng chung?
- Một biến không mặc định `final` có thể vẫn bị cấm gán lại vì guard đã tham chiếu nó không?
- Record component variables có thể dùng ở guard và rule như thế nào?
- `switch statement` dạng `->` và `switch expression` có phạm vi pattern variable tương tự ở phần thân rule không?

Nếu giải thích được những câu này và xác định đúng dòng nào biên dịch được trong các mảnh “cố ý sai”, bạn đã nắm trọng tâm **scope của pattern variable trong `when`**.

## 16. Tài liệu chính thức

- [JLS Java SE 21 — `6.3.3 Scope for Pattern Variables in case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3): biến từ pattern có mặt ở guard; biến do guard giới thiệu khi true được đưa vào phạm vi của nhánh.
- [JLS Java SE 21 — `6.3.1.6 switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1.6): phạm vi biến mẫu trong thân switch rule của expression.
- [JLS Java SE 21 — `6.3.2.6 switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.6): phạm vi biến mẫu trong switch statement.
- [JLS Java SE 21 — `6.3.1.1 và `6.3.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1.1): flow scoping trong `&&` và `||`.
- [JLS Java SE 21 — `14.11.1 Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): cú pháp guard, kiểu boolean/Boolean, final/effectively final và kiểm tra dominance.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế ngôn ngữ và trạng thái chính thức của `when` trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): khai báo và đối sánh biến thành phần của record.

Trong môi trường học tập, hãy dùng `java -version` và `javac -version` để kiểm tra JDK, rồi biên dịch ví dụ với `javac --release 21`. Khi gặp lỗi phạm vi, nên phân tích **những đường đi nào bảo đảm mẫu đã khớp**, thay vì chỉ di chuyển dấu ngoặc hoặc khai báo lại biến tùy ý.
