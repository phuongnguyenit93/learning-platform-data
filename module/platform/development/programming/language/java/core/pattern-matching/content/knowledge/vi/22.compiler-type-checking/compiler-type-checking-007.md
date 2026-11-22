# Cast dư thừa sau pattern match trong Java: nhận biết và loại bỏ đúng cách

## 1. Vấn đề: đã kiểm tra kiểu, tại sao vẫn ép kiểu?

Trước khi Java hỗ trợ **pattern matching cho `instanceof`**, cách quen thuộc để truy cập thành viên của một subtype là **kiểm tra kiểu rồi ép kiểu tường minh**:

```java
static String oldStyle(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.strip().toUpperCase(java.util.Locale.ROOT);
    }
    return "Không phải chuỗi";
}
```

Kể từ Java 16, **type pattern** giúp kết hợp kiểm tra kiểu và khai báo biến đúng kiểu trong một bước:

```java
static String modernStyle(Object value) {
    if (value instanceof String text) {
        return text.strip().toUpperCase(java.util.Locale.ROOT);
    }
    return "Không phải chuỗi";
}
```

**`text` đã có kiểu tĩnh `String`.** Vì vậy không cần viết `(String) text`, cũng không cần khai báo `String text = (String) value` trong nhánh thành công nữa. Compiler biết pattern đã khớp và cho phép dùng ngay các phương thức của `String` thông qua biến `text`.

Tuy nhiên, cần phân biệt hai trường hợp:

- **Cast dư thừa thật sự:** ép từ một biểu thức đã có kiểu mong muốn, chẳng hạn `(String) text` khi `text` là `String`.
- **Cast có thể thay bằng pattern variable:** `(String) value` trong nhánh `value instanceof String text`. Ở đây `value` **vẫn có kiểu tĩnh `Object`**. Cast trên `value` có thể cần cho chính biểu thức đó, nhưng tốt hơn là dùng `text` đã được kiểm tra và ràng buộc.

Không phải mọi cast xuất hiện “sau một pattern match” đều sai. Một số cast vẫn **thay đổi kiểu tĩnh cần thiết**, **làm rõ một subtype sâu hơn**, **chuyển kiểu số**, hoặc **chọn overload khác**. Nội dung bài học là nhận ra những khác biệt ấy để loại bỏ cast đúng mà không thay đổi hành vi.

### Phiên bản Java

- **Pattern matching cho `instanceof`** (JEP 394): chính thức từ **Java 16**.
- **Record patterns** (JEP 440) và **pattern matching cho `switch`** (JEP 441): chính thức từ **Java 21**.
- Các ví dụ chương trình hoàn chỉnh dùng **JDK 21+**, không cần `--enable-preview`. Java 17 có thể chạy ví dụ chỉ dùng `instanceof String text`, nhưng không dùng được record pattern / pattern `switch` ổn định như bài này.

## 2. Hiểu compiler: kiểu tĩnh của biểu thức và sự thành công của pattern

Xét:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());
    // System.out.println(value.length()); // KHÔNG biên dịch.
}
```

Trong nhánh thành công:

- `value` vẫn được **khai báo** là `Object`. Đối tượng thực tế mà nó tham chiếu là `String`, nhưng điều đó không tự làm kiểu tĩnh của biến `value` đổi thành `String`.
- `text` là **pattern variable** có kiểu tĩnh `String`; compiler biết `value` khớp `String` trước khi cho phép dùng `text`.
- `text.length()` hợp lệ vì `String` có phương thức `length()`.
- `value.length()` không hợp lệ vì kiểu tĩnh `Object` không khai báo `length()`.

Từ đó, so sánh ba dòng:

```java
if (value instanceof String text) {
    int a = text.length();           // NÊN: dùng pattern variable.
    int b = ((String) value).length(); // Chạy được, nhưng lặp ý kiểm tra.
    int c = ((String) text).length();  // Cast String -> String dư thừa.
}
```

Dòng `b` vẫn cần cú pháp cast **nếu cố gọi `length()` trên `value`**, nhưng kết quả tương đương đơn giản có thể đạt bằng `text.length()`. Dòng `c` không thay đổi kiểu hữu ích, vì `text` vốn đã là `String`.

**Quy tắc thực hành:** Sau khi pattern ràng buộc biến, hãy **dùng biến của pattern thay vì tiếp tục ép kiểu đối tượng đầu vào**. Không nên xóa dấu cast một cách máy móc mà không đổi tham chiếu sang biến đúng kiểu.

### Pattern matching không đồng nghĩa với cast ở runtime

Pattern kiểm tra điều kiện kiểu và ràng buộc một biến theo phạm vi hợp lệ. Bạn không phải tự viết phép ép kiểu; compiler thực hiện các kiểm tra và ràng buộc thích hợp theo ngữ nghĩa Java. Điều đó không có nghĩa một giá trị Java bất kỳ có thể trở thành subtype mong muốn: nếu đối tượng không tương thích, pattern **không khớp**, chứ không tự chuyển đổi dữ liệu.

Ví dụ, `"42"` không khớp `Integer i`. Muốn đổi chuỗi sang số nguyên phải dùng parsing như `Integer.parseInt`, không phải xóa hoặc thêm cast.

## 3. Pattern variable có phạm vi do luồng điều khiển quyết định

Cast có thể được loại bỏ khi biến pattern **đang nằm trong scope** và đã có kiểu phù hợp. Trong Java, scope của pattern variable phụ thuộc **luồng điều khiển** (flow scoping), không chỉ dấu ngoặc nhọn.

### 3.1. Trong nhánh `if` khớp kiểu

```java
static int lengthOrMinusOne(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return -1;
}
```

Nếu `value` không phải `String` hoặc là `null`, `instanceof` false; thân `if` không chạy. Biến `text` không dùng được trong đường đi thất bại.

Dạng cũ:

```java
if (value instanceof String) {
    return ((String) value).length();
}
```

Dạng mới:

```java
if (value instanceof String text) {
    return text.length();
}
```

Cả hai đều trả kết quả mong muốn cho đối tượng `String` nhưng dạng mới bỏ lặp cast và giúp ý định rõ hơn.

### 3.2. Điều kiện nối bằng `&&`

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 3) {
    System.out.println(text.strip());
}
```

Phép `&&` có **short-circuit**: vế bên phải chỉ được xét khi vế bên trái true. Vì vậy `text` đã được ràng buộc khi compiler cần kiểm tra `text.isBlank()` hoặc `text.length()`.

Đừng viết:

```java
// KHÔNG biên dịch: bên phải || có thể chạy khi pattern false.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
```

Một phép `||` không tự đảm bảo pattern đúng. Ngược lại, `||` nằm trong một nhóm sau phép `&&` có thể hợp lệ:

```java
if (value instanceof String text
        && (text.startsWith("J") || text.startsWith("K"))) {
    System.out.println(text);
}
```

Ở ví dụ này, cả hai điều kiện trong ngoặc chỉ được đánh giá sau khi `value` khớp `String`.

### 3.3. Early return sau phủ định

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải chuỗi";
    }
    return text.strip(); // text còn trong scope ở đường thành công.
}
```

Nếu execution tới câu lệnh `return text.strip()` thì nhánh không khớp đã kết thúc bằng `return`, nên compiler biết `text` tồn tại. Không cần cast bổ sung sau `if`.

Ví dụ **không tương đương**:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải chuỗi");
}
// KHÔNG dùng được text ở đây: đường thất bại vẫn có thể đi tiếp.
```

**Điều kiện cần để loại cast là biết rõ biến pattern có thể dùng ở vị trí đó.** Nếu biến chưa nằm trong scope, đổi cấu trúc code bằng nhánh hoặc early return; không đưa pattern variable sang nơi compiler không đảm bảo matching.

## 4. `switch` pattern matching: mỗi `case` đã mang kiểu phù hợp

Kể từ Java 21, bạn có thể xử lý nhiều kiểu bằng `switch`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case String text when !text.isBlank() ->
            "Chuỗi: " + text.strip();
        case String text ->
            "Chuỗi trắng hoặc rỗng";
        case Integer number ->
            "Số nguyên: " + (number + 1);
        default -> "Kiểu khác";
    };
}
```

Ở nhánh `case String text`, `text` **đã có kiểu `String`**. Không cần viết:

```java
// VÍ DỤ CAST DƯ THỪA bên trong nhánh pattern:
case String text -> "Chuỗi: " + ((String) text).strip();
```

Và cũng không cần quay lại selector:

```java
// Nếu selector tên là value, cách này lặp lại cast:
case String text -> "Chuỗi: " + ((String) value).strip();
```

Nên dùng `text.strip()`. Với `case Integer number`, gọi `number.intValue()` hoặc dùng `number + 1`; không phải `((Integer) number).intValue()`.

**Guard `when` cũng có scope của biến pattern:**

```java
case String text when text.length() > 10 ->
    "Chuỗi dài: " + text;
```

Điều kiện `when` chỉ được đánh giá sau khi `case String text` khớp, nên cast không cần thiết trong guard.

**Thứ tự case và dominance:** nhánh có điều kiện/cụ thể đặt trước nhánh tổng quát. Ví dụ `case String text -> ...` đặt **trước** `case String text when text.length() > 10 -> ...` sẽ làm nhánh có guard không thể tới. Đừng nhầm lỗi dominance với lỗi cast hoặc scope.

## 5. Record pattern và deconstruction: không cast từng component

Với Java 21, record pattern tách component có kiểu theo khai báo record:

```java
record Point(int x, int y) {}
record Parcel(String code, Point destination) {}
```

Ví dụ:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

`x` và `y` được suy luận là `int` từ component của `Point`, nên không cần ép sang `Integer`, cũng không cần gọi `((Point) value).x()`, `((Point) value).y()`.

Với record lồng:

```java
if (value instanceof Parcel(var code, Point(var x, var y))) {
    System.out.println(code + " -> (" + x + ", " + y + ")");
}
```

- `Parcel(...)` kiểm tra đối tượng ngoài cùng là `Parcel` không-null.
- `var code` nhận component `String code`.
- `Point(var x, var y)` kiểm tra `destination` là `Point` không-null rồi tách `int x` và `int y`.
- Biến `code`, `x`, `y` đã có đúng kiểu trong nhánh; không cần `(String) code` hay `(Integer) x`.
- Nếu `destination == null`, nested `Point(...)` không khớp, nên toàn bộ `Parcel(...)` không khớp. Không có chuyện biến `x`, `y` giữ lại giá trị “một phần” để dùng.

### Dừng deconstruction ở tầng thực sự cần

Nếu chỉ cần mã và điểm đến mà không cần tọa độ:

```java
if (value instanceof Parcel(var code, var destination)) {
    // destination có kiểu Point, nhưng có thể là null.
    if (destination != null) {
        System.out.println(code + ": x=" + destination.x());
    }
}
```

`var destination` suy luận kiểu `Point` theo component, nên `((Point) destination).x()` dư thừa. Nhưng kiểm tra null vẫn cần nếu component có thể null: **đúng kiểu tĩnh không đồng nghĩa với không-null**.

Với record có component khai báo là kiểu rộng hơn, phải phân biệt:

```java
record Envelope(Object payload) {}

if (value instanceof Envelope(var payload)) {
    // payload có kiểu tĩnh Object, không phải String.
    if (payload instanceof String text) {
        System.out.println(text.length()); // Không cần cast.
    }
}
```

Do `Envelope.payload` khai báo là `Object`, `var payload` có kiểu `Object`. Muốn gọi `String.length()`, phải **kiểm tra subtype**. Không được suy luận “đã deconstruct thì mọi component tự động thành kiểu chi tiết” rồi bỏ cast mà thiếu kiểm tra.

## 6. Chương trình Java 21 đầy đủ: bỏ cast nhưng giữ hành vi

Tạo tệp **`RedundantCastPatternDemo.java`**:

```java
public class RedundantCastPatternDemo {
    record Point(int x, int y) {}
    record Parcel(String code, Point destination) {}
    record Envelope(Object payload) {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Văn bản: " + text.strip()
                    .toUpperCase(java.util.Locale.ROOT);
        }

        if (value instanceof Parcel(
                var code, Point(var x, var y))) {
            return "Kiện " + code + " -> (" + x + ", " + y + ")";
        }

        if (value instanceof Number number) {
            return "Số: " + number.doubleValue();
        }

        return "Không phù hợp";
    }

    static String route(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case String text when !text.isBlank() ->
                "Chuỗi: " + text.strip();

            case String text ->
                "Chuỗi trắng hoặc rỗng";

            case Point(var x, var y) when x == 0 && y == 0 ->
                "Gốc tọa độ";

            case Point(var x, var y) ->
                "Điểm: " + (x + y);

            case Integer number ->
                "Số nguyên: " + (number + 1);

            case Number number ->
                "Số khác: " + number.doubleValue();

            default -> "Kiểu khác";
        };
    }

    static int payloadLength(Object value) {
        if (value instanceof Envelope(var payload)
                && payload instanceof String text) {
            return text.length();
        }
        return -1;
    }

    public static void main(String[] args) {
        System.out.println(describe(" Java "));
        System.out.println(describe(
            new Parcel("PK-7", new Point(4, 6))));
        System.out.println(describe(new Parcel("PK-8", null)));
        System.out.println(describe(12));
        System.out.println(describe(null));

        System.out.println(route(null));
        System.out.println(route(" Hi "));
        System.out.println(route("  "));
        System.out.println(route(new Point(0, 0)));
        System.out.println(route(new Point(2, 3)));
        System.out.println(route(7));
        System.out.println(route(2.5));
        System.out.println(route(new Object()));

        System.out.println("Payload length: "
            + payloadLength(new Envelope("abcd")));
        System.out.println("Payload length: "
            + payloadLength(new Envelope(123)));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 RedundantCastPatternDemo.java
java RedundantCastPatternDemo
```

Kết quả dự kiến:

```text
Văn bản: JAVA
Kiện PK-7 -> (4, 6)
Không phù hợp
Số: 12.0
Không phù hợp
Không có dữ liệu
Chuỗi: Hi
Chuỗi trắng hoặc rỗng
Gốc tọa độ
Điểm: 5
Số nguyên: 8
Số khác: 2.5
Kiểu khác
Payload length: 4
Payload length: -1
```

### Phân tích điểm cần chú ý

1. `describe(" Java ")`: `String text` đã ràng buộc kiểu. Không có `(String) value`; chuỗi được `strip()` rồi đổi sang chữ hoa.
2. `describe(Parcel(...))`: nested record pattern tách trực tiếp `code`, `x`, `y`. Không gọi `((Parcel)value).destination()` rồi ép tiếp sang `Point`.
3. `describe(new Parcel("PK-8", null))`: `Point(...)` không khớp vì `destination` là null. Các nhánh còn lại cũng không khớp; trả `Không phù hợp`.
4. `describe(12)`: `Integer` là một `Number`, nên `Number number` khớp và dùng trực tiếp `doubleValue()`.
5. `route`: biến ở từng `case` đã có kiểu tương ứng; `when` dùng biến ấy, không cần ép kiểu. Nhánh `Integer` đặt trước nhánh `Number` tổng quát.
6. `payloadLength`: `Envelope(var payload)` chỉ tách được `Object`, nên cần kiểm tra tiếp `payload instanceof String text`. Sau khi match `String`, dùng `text.length()` mà không cast.

Bài minh họa đồng thời hai hành động khác nhau: **bỏ cast thừa** nơi đã có pattern variable đúng kiểu, và **giữ lại kiểm tra kiểu cần thiết** khi component vẫn chỉ có kiểu rộng hơn.

## 7. Khi nào cast sau pattern match KHÔNG dư thừa?

### 7.1. Pattern kiểm tra kiểu cha, còn xử lý cần kiểu con

```java
if (value instanceof Number number) {
    System.out.println(number.doubleValue()); // An toàn cho Number.
}
```

`number` có kiểu tĩnh `Number`, không phải mọi trường hợp đều là `Integer`:

```java
// Không phải cast dư thừa: narrowing từ Number sang Integer.
// Nhưng có thể ném ClassCastException nếu value là Double.
if (value instanceof Number number) {
    Integer whole = (Integer) number;
}
```

Nếu nghiệp vụ yêu cầu chắc chắn là `Integer`, kiểm tra subtype chính xác ngay từ đầu:

```java
if (value instanceof Integer whole) {
    System.out.println(whole.intValue());
}
```

**Không tự bỏ `(Integer) number`** nếu code đang phụ thuộc vào hành vi riêng của `Integer`. Thay bằng một pattern sâu hơn chỉ khi logic thực sự muốn nhận `Integer` và thay đổi đó được xác nhận phù hợp.

### 7.2. Kiểu interface không khẳng định một implementation cụ thể

```java
if (value instanceof CharSequence sequence) {
    System.out.println(sequence.length());
}
```

`sequence` có thể là `String`, `StringBuilder` hoặc kiểu khác thực thi `CharSequence`. Cast sang `String` không phải dư thừa:

```java
// Vẫn là downcast, có thể thất bại.
String text = (String) sequence;
```

Nếu cần `String`, nên dùng một pattern `value instanceof String text` (hoặc matching bổ sung sau đó), thay vì mặc định interface đồng nghĩa với implementation.

### 7.3. Kiểu số: cast có thể là phép chuyển đổi có mất thông tin

```java
if (value instanceof Number number) {
    int truncated = (int) number.doubleValue();
    System.out.println(truncated);
}
```

`(int)` chuyển giá trị `double` về `int` theo quy tắc Java, có thể mất phần thập phân hoặc thay đổi giá trị khi ngoài miền `int`. Đây là **numeric conversion** có ngữ nghĩa riêng, không phải cast đối tượng dư thừa cần xóa chỉ vì đã match `Number`.

Ví dụ `Double.valueOf(2.9)` cho `truncated == 2`; nếu bỏ `(int)`, phép gán `double` vào `int` không hợp lệ. Tên biến `truncated` phản ánh phép cắt phần thập phân, không nhầm là phép làm tròn.

### 7.4. Generic type và type erasure

Không thể thay mọi cast generic bằng `instanceof List<String> items`:

```java
// KHÔNG biên dịch với biến obj kiểu Object: kiểu generic
// List<String> không phải dạng reifiable cho instanceof.
if (obj instanceof java.util.List<String> items) {
    // ...
}
```

Có thể kiểm tra kiểu thô ở runtime với wildcard:

```java
if (obj instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase(
                java.util.Locale.ROOT));
        }
    }
}
```

`List<?>` chứng minh đây là một `List`, **không chứng minh mọi phần tử là `String`**. Pattern `String text` trên từng phần tử là một cách tránh unchecked cast. Cast `(List<String>) obj`, nếu được dùng, thuộc vấn đề khác: có thể sinh unchecked warning và không tự kiểm tra được tham số generic ở runtime. Bỏ nó phải đi kèm thiết kế lại hợp đồng kiểu, không thể dựa duy nhất vào `instanceof List<?>`.

### 7.5. Cast có thể ảnh hưởng lựa chọn overload

Overloading được quyết định theo **kiểu tĩnh của biểu thức**:

```java
static String format(Object value) { return "Object"; }
static String format(String value) { return "String"; }

// Đoạn minh họa trong một phương thức khác.
Object value = "hello";
if (value instanceof String text) {
    System.out.println(format(value));        // Object
    System.out.println(format((String) value)); // String
    System.out.println(format(text));         // String
}
```

Nếu chỉ **xóa cast** trong `format((String) value)` thành `format(value)`, phương thức overload được chọn **thay đổi**. Nếu mục tiêu là tránh cast mà **giữ hành vi**, thay toàn bộ biểu thức đối số bằng `text`.

Đây là ví dụ quan trọng cho review: không gọi một cast là “có thể xóa vô hại” khi chính nó ảnh hưởng đến overload resolution. Hãy cân nhắc thay bằng pattern variable đúng kiểu thay vì xóa riêng cặp ngoặc cast.

## 8. Những trường hợp dễ hiểu sai về `null`

### `instanceof` với null

```java
Object value = null;
if (value instanceof String text) {
    // Không chạy.
}
```

Null không khớp type pattern ở cấp này. Không cần viết thêm `value != null` trước `instanceof` chỉ để phòng lỗi trong ví dụ trên.

### Component của record vẫn có thể null

```java
record Note(String text) {}

if (value instanceof Note(var text)) {
    // text có kiểu String nhưng có thể là null.
    if (text != null) {
        System.out.println(text.length());
    }
}
```

Record pattern `Note(var text)` vẫn có thể khớp khi `Note.text() == null`: `var text` là pattern vô điều kiện cho kiểu component, cho phép giữ null. Cast `(String) text` **không** biến null thành chuỗi hợp lệ, và cũng không thay thế kiểm tra `text != null`.

### Nested record cần record con không-null

```java
record Wrapper(Note note) {}

if (value instanceof Wrapper(Note(var text))) {
    // Wrapper.note() bắt buộc là một Note không-null.
    // Nhưng text nằm trong Note vẫn có thể null.
}
```

**Phân biệt:** kiểu tĩnh phù hợp, giá trị có thể null, và pattern có khớp hay không là ba câu hỏi khác nhau. Bỏ cast thừa không tự động giải quyết vấn đề null-safety.

## 9. So sánh trước/sau khi refactor

### Trường hợp A: thay cast bằng type pattern variable

**Trước:**

```java
if (value instanceof String) {
    String text = (String) value;
    consume(text);
}
```

**Sau:**

```java
if (value instanceof String text) {
    consume(text);
}
```

Đây là refactor đơn giản. Nếu compiler đang kiểm tra được cấu trúc và cách dùng biến, nó loại bỏ nhu cầu viết ép kiểu và giảm code.

### Trường hợp B: tránh cast lặp khi gọi nhiều phương thức

**Trước:**

```java
if (value instanceof String) {
    System.out.println(((String) value).length());
    System.out.println(((String) value).strip());
}
```

**Sau:**

```java
if (value instanceof String text) {
    System.out.println(text.length());
    System.out.println(text.strip());
}
```

Bản sau biểu thị rõ một lần kiểm tra kiểu và dùng một biến cùng kiểu. Không cần re-cast ở từng dòng.

### Trường hợp C: đổi vị trí kiểm tra kiểu, không chỉ xóa cast

**Dễ gây lỗi:**

```java
if (value instanceof Number number) {
    Integer count = (Integer) number; // Không bảo đảm nếu Number là Double.
    System.out.println(count + 1);
}
```

**Nếu chỉ nhận số nguyên:**

```java
if (value instanceof Integer count) {
    System.out.println(count + 1);
}
```

Đây **không** là refactor tương đương tuyệt đối cho mọi input: bản đầu có thể ném `ClassCastException` khi input là `Double`, còn bản sau chỉ bỏ qua nhánh. Cần xác định hành vi mong muốn với input khác `Integer` trước khi chọn cách xử lý.

### Trường hợp D: không mất thông tin khi xử lý record

**Trước:**

```java
if (value instanceof Parcel) {
    Parcel parcel = (Parcel) value;
    Point destination = parcel.destination();
    if (destination != null) {
        System.out.println(destination.x());
    }
}
```

**Sau:**

```java
if (value instanceof Parcel(var code, var destination)
        && destination != null) {
    System.out.println(destination.x());
}
```

Trong hai đoạn, `value` phải là `Parcel` và destination phải không-null để in ra tọa độ. Bản sau bỏ cast và khai báo `Point` thủ công nhưng vẫn có guard null. Lưu ý biến `code` chỉ được tách thêm do record có hai component; nếu không cần deconstruction, `value instanceof Parcel parcel` và `parcel.destination()` cũng là lựa chọn rõ ràng.

## 10. Compiler có thể giúp phát hiện cast thừa như thế nào?

Khi phân tích cast, hãy xem hai thứ: **mã có biên dịch không** và **việc bỏ cast có giữ hành vi không**.

- `javac` kiểm tra kiểu tĩnh, khả năng truy cập biến pattern theo flow scoping, điều kiện matching trong `switch` và các quy tắc chuyển kiểu.
- Tùy phiên bản/cấu hình compiler, có thể bật cảnh báo về cast dư thừa bằng `-Xlint:cast`; IDE cũng có thể gợi ý “redundant cast”.
- Cảnh báo không chứng minh rằng thay đổi cơ học luôn giữ hành vi trong mọi biểu thức. Với overload, generics và cast narrowing, cần kiểm tra kiểu tĩnh và ý nghĩa runtime.
- Đừng xóa unchecked cast generic mà không sửa hợp đồng kiểu. Một cast generic trông “không cần” trên đường đi hiện tại vẫn có thể là dấu hiệu API đang thiếu type safety.

Ví dụ lệnh chạy chương trình trong mục 6 và bật cảnh báo:

```bash
javac --release 21 -encoding UTF-8 -Xlint:cast RedundantCastPatternDemo.java
java RedundantCastPatternDemo
```

Mục tiêu của `-Xlint:cast` là hỗ trợ phát hiện trường hợp có thể đơn giản hóa. **Không phải mọi biểu thức cần cải thiện đều tạo cảnh báo**, đặc biệt với trường hợp lặp `(String) value` trong khi biến `text` đã tồn tại nhưng `value` vẫn được khai báo `Object`. Review ngữ nghĩa vẫn quan trọng.

Nếu một cast được IDE đề xuất xóa, hãy đọc biểu thức xung quanh: lời gọi overload nào được chọn, biến nào có kiểu gì, và có đang chuyển số hay thu hẹp subtype hay không.

## 11. Checklist review cho cast sau pattern match

| Câu hỏi | Cách kiểm tra | Quyết định |
| --- | --- | --- |
| Pattern đã khai báo biến đúng subtype chưa? | Xem `instanceof T t`, `case T t` hoặc `Record(var component)` | Dùng biến `t`/component thay cast khi phù hợp |
| Tên biến pattern còn trong scope? | Xem `if`/`else`, `&&`, early return, từng nhánh `case` | Chỉ dùng biến ở nhánh chắc chắn matching thành công |
| Cast đang áp dụng lên biến pattern hay biến gốc? | So kiểu tĩnh `t` và `value` | `(T) t` thường dư; `(T) value` có thể thay bằng `t` |
| Cast thu hẹp subtype hơn pattern? | Ví dụ `Number` thành `Integer` | Kiểm tra kiểu con hoặc giữ cast có chủ đích, dự liệu lỗi |
| Cast chuyển kiểu số? | `(int) doubleValue()` | Xem có phép narrowing và mất dữ liệu không |
| Cast generic có unchecked warning? | `List<?>` so với `List<String>` | Điều chỉnh API/kiểm tra phần tử thay vì xóa bừa |
| Overload có đổi không? | So kiểu tĩnh của đối số trước/sau | Dùng pattern variable đúng kiểu để giữ overload nếu cần |
| Component có thể null? | Kiểm tra contract của record/constructor | Cast không thay được null guard |
| Nhánh `switch` có bị che? | Xem thứ tự type patterns và guard | Đặt nhánh cụ thể trước nhánh tổng quát |
| Đã kiểm thử các case khác kiểu? | String, Integer, Double, null, record con null | Xác nhận kết quả và exception theo nghiệp vụ |

Một quyết định tốt phải tách **tính an toàn kiểu** và **chất lượng mã**. Cast có thể hợp lệ về cú pháp nhưng diễn đạt kém vì quên tận dụng pattern variable; ngược lại cast có thể cần thiết khi mẫu được chọn chưa đủ chính xác.

## 12. Lỗi phổ biến

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `value instanceof String text` rồi viết `String s = (String) text` | `text` đã là `String` | Dùng thẳng `text`; bỏ khai báo trùng |
| Xóa `(String) value` nhưng vẫn gọi `value.length()` | `value` có kiểu tĩnh `Object` | Đổi sang `text.length()` |
| Sau `instanceof Number n` tự cho rằng `n` là `Integer` | Match chỉ chứng minh `Number` | Dùng `instanceof Integer i` nếu cần `Integer` |
| Dùng `var payload` trong record `Object payload` rồi gọi `payload.length()` | `var` suy luận `Object`, không đoán subtype runtime | Dùng `payload instanceof String text` |
| Tưởng cast và null check là tương đương | Cast tham chiếu null vẫn trả null; gọi method trên null gây NPE | Kiểm tra null riêng |
| Dùng pattern variable ngoài flow scoping | Pattern có thể chưa khớp trên một đường đi | Tổ chức lại `if`/`else`/early return |
| Dùng `||` sau `instanceof` rồi đọc pattern variable | Vế phải có thể chạy lúc pattern false | Dùng `&&` khi điều kiện phụ thuộc matching thành công |
| Bỏ narrowing cast số vì “đã instanceof Number” | `Number` không biến `double` thành `int` | Giữ conversion và làm rõ mất phần thập phân |
| Dùng `instanceof List<String>` thay cast generic | Type erasure, kiểu tham số không reifiable | Dùng `List<?>` + kiểm tra phần tử hoặc thiết kế API generic |
| Bỏ cast trên argument làm đổi overload | Overload dựa vào kiểu tĩnh | Thay cả argument bằng biến pattern đúng subtype |
| Nhánh `case Number n` trước `case Integer i` | Case sau bị dominance | Đưa `Integer` trước `Number` |
| Bỏ cast nhưng không chạy kiểm thử | Refactor có thể đổi output/exception | Biên dịch và test các trường hợp biên |

## 13. Bài tập thực hành

**Bài 1 — Nhận diện cast dư thừa.** Với `Object value`, xét:

```java
if (value instanceof String text) {
    int a = ((String) text).length();
    int b = ((String) value).length();
    int c = text.length();
}
```

Đâu là cách viết tốt nhất? **Gợi ý:** `c`. Dòng `a` ép một biến vốn là String; dòng `b` chỉ còn cần cast vì gọi phương thức trên biến `Object`, có thể thay bằng `text`.

**Bài 2 — Overload.** Với `format(Object)` và `format(String)`, giải thích tại sao `format(value)` và `format(text)` chọn overload khác nhau dù `value` và `text` có thể tham chiếu cùng một chuỗi. Câu trả lời: **kiểu tĩnh** quyết định overload khi biên dịch.

**Bài 3 — Kiểu cha/kiểu con.** Tại sao `Number n` không tự chứng minh đối tượng là `Integer`? Hãy viết code xử lý `Integer` và `Double` trong hai nhánh `switch` riêng mà không cast.

**Bài 4 — Record component kiểu rộng.** Với `record Envelope(Object payload)`, hãy viết `if` trả về độ dài nếu `payload` là `String`. Gợi ý: dùng nested matching `value instanceof Envelope(var payload) && payload instanceof String text`.

**Bài 5 — Null.** Với `record Note(String text)`, viết xử lý không ném NPE nếu component `text` là null. Gợi ý: sau `Note(var text)`, kiểm tra `text != null` trước khi gọi `text.length()`.

**Bài 6 — Biên dịch và phân loại.** Chạy `RedundantCastPatternDemo.java`, sau đó thử thay `case Integer number` và `case Number number` cho nhau. Compiler phản ứng thế nào? Giải thích bằng **dominance**.

**Bài 7 — Refactor có kiểm chứng.** Chuyển một đoạn kiểm tra kiểu + cast thủ công trong code của bạn sang pattern variable; test dữ liệu đúng subtype, sai subtype và null. Nếu có overload hoặc narrowing conversion, ghi rõ vì sao giữ hoặc thay cast.

## 14. Tổng kết

**Bỏ cast dư thừa sau pattern match là kết quả của việc dùng đúng biến đã được compiler kiểm tra kiểu**, không phải thao tác xóa mọi `(Type)` trong vùng code vừa có `instanceof` hay `case`.

- `instanceof T t` và `case T t` cho biến `t` có kiểu tĩnh `T` trong phạm vi matching hợp lệ.
- `Record(var x, ...)` suy luận kiểu `x` từ component khai báo; nested record pattern có thể tách tới kiểu lá.
- Dùng biến pattern trực tiếp thường loại bỏ chuỗi kiểm tra kiểu → cast → khai báo biến phụ.
- Biến gốc vẫn mang kiểu tĩnh đã khai báo; nếu còn dùng nó, có thể cần cast trong chính biểu thức ấy. Thay bằng pattern variable thường rõ hơn.
- Cast thu hẹp subtype, chuyển đổi số, generic casts và cast ảnh hưởng overload có thể mang ý nghĩa thực sự; không xóa khi chưa hiểu.
- Flow scoping, null và thứ tự `switch case` là các yếu tố độc lập cần kiểm tra khi refactor.

### Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
