# Thay chuỗi ép kiểu trong xử lý dữ liệu bằng pattern với `instanceof` (Java 17)

> **Chủ đề:** Java 17  
> **Chương:** Pattern `instanceof`  
> **Mục tiêu:** Chuyển những đoạn mã kiểm tra kiểu rồi ép kiểu thủ công sang **pattern matching for `instanceof`**, dùng biến pattern đúng phạm vi trong các nhánh xử lý dữ liệu, và tránh các cú pháp chưa ổn định ở Java 17.

## 1. Tình huống: Vì sao chuỗi ép kiểu trở nên khó đọc?

Trong Java, một hàm nhận `Object`, một interface hoặc một kiểu cha có thể nhận nhiều đối tượng thực tế khác nhau. Ví dụ, hệ thống xử lý thông điệp có thể nhận sự kiện tạo đơn, lỗi xử lý hoặc một ghi chú văn bản. Trước khi sử dụng thuộc tính riêng của từng loại, mã Java truyền thống thường phải làm hai việc:

1. Kiểm tra đối tượng có thuộc loại mong muốn bằng `instanceof`.
2. Ép kiểu tường minh bằng `(Type) object` rồi mới đọc dữ liệu.

Ví dụ trước khi áp dụng pattern:

```java
static String describe(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "Văn bản: " + text.strip();
    } else if (value instanceof Integer) {
        Integer number = (Integer) value;
        return "Số nguyên: " + number.intValue();
    } else {
        return "Không hỗ trợ";
    }
}
```

Các dòng `String text = (String) value` và `Integer number = (Integer) value` lặp lại thông tin kiểu ngay sau khi vừa kiểm tra. Khi có nhiều kiểu, nhiều cấp `if` và nhiều vị trí ép kiểu, mã dài hơn, dễ đọc nhầm biến hoặc ép kiểu nhầm nếu sửa điều kiện mà quên sửa phần thân.

**Pattern matching for `instanceof`** giải quyết trực tiếp trường hợp này bằng cú pháp:

```java
if (expression instanceof Type variableName) {
    // variableName đã có kiểu Type ở đây.
}
```

Từ Java 16 (JEP 394), đây là tính năng chính thức và **sử dụng ổn định trong Java 17**. Không cần bật `--enable-preview` để dùng type pattern với `instanceof`.

## 2. Chuyển đổi cơ bản: Kiểm tra kiểu và nhận biến chỉ trong một biểu thức

### 2.1. Trước và sau

**Trước — kiểm tra và ép kiểu tách rời:**

```java
Object input = "  Java 17  ";

if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip());
}
```

**Sau — type pattern:**

```java
Object input = "  Java 17  ";

if (input instanceof String text) {
    System.out.println(text.strip());
}
```

Biểu thức `input instanceof String text` có hai tác dụng:

- Kiểm tra giá trị runtime của `input` có tương thích với `String` không.
- Khi khớp, tạo và gán **pattern variable** `text` có kiểu `String`, dùng được tại những vị trí mà trình biên dịch bảo đảm phép kiểm tra đã thành công.

Trong ví dụ này, `text` được sử dụng trực tiếp để gọi `strip()`. Không cần và không nên viết thêm `(String) input` trong phần thân `if`.

### 2.2. `instanceof` trước và sau vẫn có ý nghĩa kiểm tra kiểu

| Đặc điểm | `instanceof String` truyền thống | `instanceof String text` có pattern |
|---|---|---|
| Kiểm tra kiểu runtime | Có | Có |
| Trả kết quả boolean | Có | Có |
| Tự tạo biến tham chiếu đã được thu hẹp kiểu | Không | Có, khi pattern khớp |
| Cần ép kiểu thủ công để gọi API của subtype | Thường có | Không trong phạm vi `text` |
| Giá trị `null` có khớp không? | Không | Không |
| Có thể dùng trong Java 17 không bật preview? | Có | Có |

**Lưu ý:** Đây là **type pattern**. Cú pháp kiểm tra và bóc tách các component của record, ví dụ `instanceof Point(int x, int y)`, **không thuộc Java 17 ổn định**; record patterns được hoàn thiện trong Java 21.

### 2.3. Lợi ích khi biểu thức nguồn phức tạp

Với `instanceof` pattern, bạn không cần lặp biểu thức nguồn trong phép ép kiểu:

```java
static void process(Object[] items, int index) {
    if (items[index] instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

Việc này có ích đặc biệt khi giá trị đến từ một lời gọi phương thức, phần tử mảng hoặc một tầng dữ liệu trung gian. Tuy vậy, khi đọc từ nguồn có side effect, vẫn nên lấy dữ liệu ra một biến trước để chương trình dễ theo dõi:

```java
Object item = queue.poll();
if (item instanceof String text) {
    System.out.println(text);
}
```

## 3. Chuyển cả chuỗi `if / else if` dùng ép kiểu

Giả sử một bộ xử lý nhận các đối tượng `OrderCreated` và `ProcessingError`:

```java
record OrderCreated(String orderId, int quantity) { }
record ProcessingError(String code, String message) { }
```

**Mã cũ:**

```java
static String describe(Object event) {
    if (event instanceof OrderCreated) {
        OrderCreated created = (OrderCreated) event;
        return "Đơn " + created.orderId()
                + " có " + created.quantity() + " sản phẩm";
    } else if (event instanceof ProcessingError) {
        ProcessingError error = (ProcessingError) event;
        return "Lỗi " + error.code() + ": " + error.message();
    } else if (event instanceof String) {
        String note = (String) event;
        return "Ghi chú: " + note.strip();
    }
    return "Không nhận diện được dữ liệu";
}
```

**Mã sau khi thay bằng pattern:**

```java
static String describe(Object event) {
    if (event instanceof OrderCreated created) {
        return "Đơn " + created.orderId()
                + " có " + created.quantity() + " sản phẩm";
    } else if (event instanceof ProcessingError error) {
        return "Lỗi " + error.code() + ": " + error.message();
    } else if (event instanceof String note) {
        return "Ghi chú: " + note.strip();
    }
    return "Không nhận diện được dữ liệu";
}
```

Mỗi nhánh đã gom **kiểm tra kiểu + khai báo biến đúng kiểu** vào một dòng. Vì vậy, phần xử lý dữ liệu tập trung vào quy tắc nghiệp vụ hơn là câu lệnh ép kiểu.

Không cần đổi cấu trúc `if / else if` khi refactor. Điều quan trọng là mỗi pattern variable có tên gợi nghĩa và chỉ được dùng trong vùng mà phép kiểm tra kiểu thành công.

## 4. Ví dụ đầy đủ có thể chạy với Java 17

Tạo một file có tên `DataProcessingDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class DataProcessingDemo {

    record OrderCreated(String orderId, int quantity) {
        OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
            if (orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Dữ liệu đơn hàng không hợp lệ");
            }
        }
    }

    record ProcessingError(String code, String message) {
        ProcessingError {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
        }
    }

    static String describe(Object value) {
        if (value == null) {
            return "Dữ liệu null";
        }

        if (value instanceof OrderCreated created) {
            return "Tạo đơn " + created.orderId()
                    + " x " + created.quantity();
        }

        if (value instanceof ProcessingError error) {
            return "Lỗi " + error.code() + ": " + error.message();
        }

        // Phối hợp type pattern với kiểm tra nghiệp vụ.
        if (value instanceof String note && !note.isBlank()) {
            return "Ghi chú: " + note.strip();
        }

        // Có thể nhận diện kiểu danh sách mà không ép kiểu thủ công.
        if (value instanceof List<?> items) {
            return "Danh sách: " + items.size() + " phần tử";
        }

        return "Không hỗ trợ: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Object[] inputs = {
                new OrderCreated("ORD-100", 3),
                new ProcessingError("OUT_OF_STOCK", "Hết hàng"),
                "  ưu tiên  ",
                List.of("A", "B"),
                42,
                null
        };

        for (Object input : inputs) {
            System.out.println(describe(input));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 DataProcessingDemo.java
java DataProcessingDemo
```

Kết quả dự kiến:

```text
Tạo đơn ORD-100 x 3
Lỗi OUT_OF_STOCK: Hết hàng
Ghi chú: ưu tiên
Danh sách: 2 phần tử
Không hỗ trợ: Integer
Dữ liệu null
```

Các điểm chính trong ví dụ:

1. `value` có kiểu khai báo `Object` nhưng có thể chứa các giá trị runtime khác nhau.
2. Mỗi nhánh pattern khớp sẽ có biến đúng kiểu: `created`, `error`, `note` hoặc `items`.
3. `created.orderId()` và `error.message()` là accessor của `record`, không phải một cú pháp record pattern mới.
4. `value instanceof String note && !note.isBlank()` chỉ gọi `note.isBlank()` khi dữ liệu thực sự là `String`.
5. `value instanceof List<?> items` giữ việc kiểm tra generic an toàn mà không dùng ép kiểu `(List<String>)` thiếu kiểm chứng.
6. Kiểm tra `value == null` giúp phân biệt dữ liệu thiếu với loại dữ liệu khác. `instanceof` tự trả `false` khi giá trị là `null`.

## 5. Quy tắc quan trọng nhất: Phạm vi biến phụ thuộc luồng điều khiển

Java 17 xác định phạm vi của **pattern variable** theo những vị trí mà compiler biết chắc mẫu đã khớp. Cách này thường được gọi là **flow scoping**.

### 5.1. Biến tồn tại trong nhánh `if` khớp

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Hợp lệ
    } else {
        System.out.println("Không phải chuỗi");
        // System.out.println(text); // SAI: text không có trong phạm vi này.
    }

    // System.out.println(text); // SAI: nhánh if có thể không khớp.
}
```

Nếu phép kiểm tra `instanceof` trả `false`, không có gì bảo đảm `text` đã được gán nên không thể sử dụng ở nhánh `else` hoặc tùy ý sau `if`.

### 5.2. Dùng `&&` để kiểm tra thêm dữ liệu đã được thu hẹp kiểu

```java
static boolean isValidCode(Object input) {
    return input instanceof String code
            && !code.isBlank()
            && code.startsWith("ORD-");
}
```

Toán tử `&&` được đánh giá từ trái sang phải và dừng khi gặp `false`. Vì vậy, Java bảo đảm `code` đã được gán khi kiểm tra `!code.isBlank()` và `code.startsWith(...)`.

Đây là một trong những cách **giảm lồng nhiều tầng `if`** mà vẫn giữ điều kiện rõ ràng.

**Trước:**

```java
if (input instanceof String) {
    String code = (String) input;
    if (!code.isBlank()) {
        if (code.startsWith("ORD-")) {
            System.out.println("Mã đơn hợp lệ");
        }
    }
}
```

**Sau:**

```java
if (input instanceof String code
        && !code.isBlank()
        && code.startsWith("ORD-")) {
    System.out.println("Mã đơn hợp lệ");
}
```

### 5.3. Không dùng pattern variable ở phía phải `||` theo cách tùy ý

Ví dụ **không hợp lệ**:

```java
// SAI: nếu vế trái false, text chưa có giá trị.
// if (input instanceof String text || text.isBlank()) {
//     System.out.println("...");
// }
```

Với `||`, vế phải được tính khi vế trái **false**. Tại thời điểm ấy, `input instanceof String text` không khớp, nên `text` không sẵn sàng.

Khi cần một điều kiện loại trừ, hãy dùng các nhánh có nghĩa rõ ràng:

```java
static String readNonBlankString(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Cần một chuỗi");
    }
    if (text.isBlank()) {
        throw new IllegalArgumentException("Chuỗi không được rỗng");
    }
    return text.strip();
}
```

Hoặc viết điều kiện kết hợp với phép phủ định và `||`:

```java
static String readName(Object input) {
    if (!(input instanceof String name) || name.isBlank()) {
        throw new IllegalArgumentException("Tên phải là chuỗi không rỗng");
    }
    return name.strip();
}
```

Trong ví dụ thứ hai, `name.isBlank()` chỉ được đánh giá khi `!(input instanceof String name)` là `false`, tức là pattern **đã** khớp. Đây là quy tắc về **flow**, không phải quy tắc đơn giản “không bao giờ dùng `||` với pattern”.

### 5.4. Guard clause và phạm vi biến sau nhánh thoát sớm

Một cách refactor dữ liệu đầu vào rất hữu ích là **kiểm tra kiểu và thoát sớm**:

```java
static int parseLength(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Yêu cầu String");
    }

    // Tới đây, Java biết chắc text là String.
    return text.strip().length();
}
```

Vì nhánh xử lý sai kiểu luôn kết thúc bằng `throw`, nếu chương trình tiếp tục chạy sau `if` thì phép kiểm tra đã phải thành công. Java cho phép dùng `text` ở đoạn tiếp theo.

Tương tự, có thể dùng `return` hoặc `continue` trong trường hợp thích hợp:

```java
static void printUppercaseStrings(List<?> values) {
    for (Object value : values) {
        if (!(value instanceof String text)) {
            continue;
        }
        System.out.println(text.toUpperCase());
    }
}
```

Điều này thường tạo mã dễ đọc hơn so với việc bao toàn bộ thân xử lý trong nhiều `if` lồng nhau.

### 5.5. Pattern variable có thể xuất hiện trong biểu thức điều kiện

```java
static String summary(Object input) {
    return input instanceof String text
            ? "Độ dài: " + text.length()
            : "Không phải chuỗi";
}
```

Biến `text` có trong phạm vi của nhánh kết quả khi biểu thức `instanceof` là `true`. Bạn không thể dùng `text` tùy ý trong nhánh `false`.

## 6. Dùng pattern để làm sạch dữ liệu `Object` và `Map<?, ?>`

Một nguồn gây ép kiểu lặp lại phổ biến là dữ liệu linh hoạt: cấu hình đọc từ thư viện, sự kiện nội bộ, map chứa giá trị khác kiểu hoặc dữ liệu ở ranh giới tích hợp. Khi đó ta có thể dùng pattern để kiểm tra **từng giá trị** trước khi dùng.

### 6.1. Ví dụ trước khi thay ép kiểu

```java
static int readQuantity(Object raw) {
    if (!(raw instanceof java.util.Map)) {
        throw new IllegalArgumentException("Phải là Map");
    }
    java.util.Map<?, ?> fields = (java.util.Map<?, ?>) raw;

    Object quantity = fields.get("quantity");
    if (!(quantity instanceof Integer)) {
        throw new IllegalArgumentException("quantity phải là Integer");
    }

    Integer number = (Integer) quantity;
    return number.intValue();
}
```

Mã cần hai vị trí ép kiểu, trong khi mỗi vị trí đều đã được bảo vệ bằng một phép kiểm tra `instanceof`.

### 6.2. Refactor bằng pattern và guard clause

```java
import java.util.Map;

public class MapDataDemo {

    static int readQuantity(Object raw) {
        if (!(raw instanceof Map<?, ?> fields)) {
            throw new IllegalArgumentException("Phải là Map");
        }

        Object rawQuantity = fields.get("quantity");
        if (!(rawQuantity instanceof Integer quantity)) {
            throw new IllegalArgumentException("quantity phải là Integer");
        }

        if (quantity < 0) {
            throw new IllegalArgumentException("quantity không được âm");
        }

        return quantity;
    }

    public static void main(String[] args) {
        Object valid = Map.of("quantity", 5, "unit", "items");
        System.out.println(readQuantity(valid)); // 5
    }
}
```

Biên dịch:

```bash
javac --release 17 MapDataDemo.java
java MapDataDemo
```

**Những điều cần hiểu:**

- `Map<?, ?> fields` kiểm tra dữ liệu là một `Map`, nhưng chưa khẳng định kiểu của từng key hoặc value bên trong. Việc dùng wildcard `?` là thành phần quan trọng để tránh một phép cast generic không được kiểm chứng.
- `fields.get("quantity")` trả về `Object`. Pattern thứ hai bảo đảm nó thật sự là `Integer` trước khi sử dụng.
- Khi giá trị không khớp, phương thức báo lỗi có chủ đích thay vì cố ép kiểu rồi nhận `ClassCastException` khó hiểu.
- Ví dụ này chủ động yêu cầu `Integer`. Một nguồn dữ liệu JSON có thể trả số dưới dạng `Long`, `Double` hoặc `BigDecimal` tùy thư viện và cấu hình; phải xác định schema đầu vào trước khi chọn pattern. Không giả định mọi giá trị số đều là `Integer`.

Pattern matching **không phải công cụ tự động kiểm tra toàn bộ dữ liệu của Map**, và không thay thế validation nghiệp vụ. Với dữ liệu có cấu trúc ổn định, nên sớm chuyển sang một DTO/record có kiểu rõ ràng rồi xử lý trên kiểu đó.

## 7. Generic: Vì sao dùng `List<?>` thay vì `List<String>` trong pattern?

Java dùng **type erasure** cho nhiều thông tin generic khi chạy. Vì vậy, không thể kiểm tra trực tiếp kiểu tham số hóa không reifiable như cách dưới đây:

```java
Object raw = List.of("A", "B");

// SAI: không được kiểm tra kiểu List<String> bằng instanceof.
// if (raw instanceof List<String> names) {
//     ...
// }
```

Cách hợp lệ trong Java 17 là kiểm tra kiểu collection với wildcard, sau đó kiểm tra từng phần tử:

```java
import java.util.ArrayList;
import java.util.List;

public class NameListDemo {
    static List<String> extractNonBlankNames(Object raw) {
        List<String> result = new ArrayList<>();

        if (!(raw instanceof List<?> items)) {
            return result;
        }

        for (Object item : items) {
            if (item instanceof String name && !name.isBlank()) {
                result.add(name.strip());
            }
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object values = List.of("An", 17, "  Bình  ", "");
        System.out.println(extractNonBlankNames(values)); // [An, Bình]
    }
}
```

Ở ví dụ này, danh sách nguồn có thể chứa nhiều loại dữ liệu. Không có phép ép kiểu `(List<String>) raw`; từng phần tử chỉ đi vào danh sách kết quả khi thật sự là `String`.

Nếu yêu cầu nghiệp vụ là **mọi** phần tử phải là chuỗi, không nên âm thầm bỏ qua phần tử sai kiểu. Thay bằng báo lỗi rõ ràng:

```java
static List<String> requireStrings(Object raw) {
    if (!(raw instanceof List<?> values)) {
        throw new IllegalArgumentException("Cần một List");
    }

    List<String> names = new java.util.ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String name)) {
            throw new IllegalArgumentException("Danh sách có phần tử không phải String");
        }
        names.add(name);
    }
    return List.copyOf(names);
}
```

Sự lựa chọn **lọc** hay **từ chối** dữ liệu sai kiểu là quyết định nghiệp vụ; pattern chỉ giúp thực hiện kiểm tra rõ ràng và an toàn hơn.

## 8. Kết hợp `instanceof` pattern với record và sealed interface

Java 17 có `record` và `sealed interface` ổn định. Bạn có thể dùng các record làm biến thể dữ liệu của một giao diện sealed rồi xử lý bằng `instanceof` pattern.

```java
public class ResultDemo {
    sealed interface Result permits Success, Failure { }

    record Success(String value) implements Result { }
    record Failure(String code, String message) implements Result { }

    static String toMessage(Result result) {
        if (result instanceof Success success) {
            return "Thành công: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Lỗi " + failure.code() + ": " + failure.message();
        }
        throw new IllegalStateException("Loại Result chưa được xử lý");
    }

    public static void main(String[] args) {
        System.out.println(toMessage(new Success("OK")));
        System.out.println(toMessage(new Failure("E-1", "Từ chối")));
    }
}
```

Trong ví dụ:

- `sealed interface Result` giới hạn các kiểu triển khai trực tiếp vào `Success` và `Failure`.
- `record Success`, `record Failure` mô tả dữ liệu cho từng biến thể.
- `instanceof Success success` kiểm tra kiểu và cho phép gọi `success.value()`.
- Không có việc “bóc tách record” trực tiếp trong mẫu. Java 17 yêu cầu truy cập các component bằng accessor như `value()`, `code()`, `message()`.

**Quan trọng:** Với chuỗi `if` ở Java 17, trình biên dịch **không tự kiểm tra đã xử lý đầy đủ mọi biến thể** của sealed interface. Nếu sau này thêm `Pending` vào `permits` nhưng quên sửa `toMessage`, hàm có thể đi tới nhánh ném ngoại lệ tại runtime. Khi thay đổi tập kiểu, cần xem xét lại toàn bộ những điểm phân nhánh và kiểm thử phù hợp. Nếu hành vi thuộc trách nhiệm của mỗi biến thể, có thể đưa một phương thức chung lên interface và dùng đa hình để buộc các record cung cấp triển khai.

### 8.1. Không nhầm với pattern matching cho `switch`

Cú pháp sau trông rất gọn:

```java
// Không phải cú pháp ổn định để dùng với --release 17:
//
// return switch (result) {
//     case Success success -> success.value();
//     case Failure failure -> failure.message();
// };
```

Trong **Java 17**, pattern matching cho `switch` là tính năng **preview** (JEP 406). Nó chỉ được hoàn thiện thành tính năng chính thức trong Java 21 (JEP 441). Với bài học Java 17, sử dụng `instanceof` pattern trong `if`, `else if` và guard clauses; không đưa preview syntax vào ví dụ cần biên dịch thông thường.

### 8.2. Không nhầm với record patterns

```java
record Point(int x, int y) { }

static int sum(Object value) {
    if (value instanceof Point point) {
        return point.x() + point.y(); // Hợp lệ trên Java 17
    }
    return 0;
}
```

Cú pháp kiểu `value instanceof Point(int x, int y)` **không phải** cách viết thay thế trên Java 17. Record patterns được hoàn thiện trong Java 21 (JEP 440).

## 9. Những bẫy khi refactor chuỗi kiểm tra kiểu

### 9.1. `null` không khớp type pattern

```java
Object value = null;

System.out.println(value instanceof String);       // false
System.out.println(value instanceof String text);  // false
```

Không cần viết `value != null && value instanceof String text` chỉ để tránh `NullPointerException` trong chính phép kiểm tra `instanceof`. Tuy nhiên, nếu `null` có ý nghĩa riêng (dữ liệu thiếu, trường không tồn tại), hãy xử lý tường minh khi cần.

### 9.2. Kiểm tra từ subtype cụ thể trước supertype rộng hơn

```java
static String classify(Object input) {
    if (input instanceof Integer number) {
        return "Integer: " + number;
    }
    if (input instanceof Number number) {
        return "Number: " + number;
    }
    return "Khác";
}
```

Một `Integer` cũng là `Number`. Nếu đưa nhánh `Number` lên trước, nhánh `Integer` phía sau sẽ không xử lý các đối tượng `Integer`. Đây là vấn đề **thứ tự quy tắc** đã tồn tại ở `if / else if` truyền thống; pattern không tự quyết định mức ưu tiên các kiểu.

### 9.3. Không dùng pattern khi kiểu đã được biết chắc tại biên dịch

Ví dụ:

```java
String name = "Lan";

// SAI ở Java 17: kiểm tra String với mẫu String là vô nghĩa.
// if (name instanceof String text) {
//     System.out.println(text.length());
// }

System.out.println(name.length()); // Đúng và đơn giản hơn
```

Khi kiểu biểu thức đầu vào đã là subtype của kiểu pattern, việc kiểm tra không đem lại thông tin mới và trình biên dịch Java 17 từ chối mẫu như vậy. Pattern matching hữu ích khi **kiểu tĩnh rộng hơn** kiểu cần dùng, ví dụ `Object`, `Number` hoặc interface cha.

### 9.4. Không kiểm tra được generic type argument theo cách không reifiable

```java
Object input = List.of(1, 2, 3);

// SAI: instanceof List<Integer> numbers
if (input instanceof List<?> numbers) {
    System.out.println("Có " + numbers.size() + " phần tử");
}
```

Kiểm tra tiếp từng phần tử nếu cần bảo đảm đúng kiểu. Ép kiểu thủ công `(List<Integer>) input` có thể tạo cảnh báo unchecked và không chứng minh các phần tử thực sự là `Integer`.

### 9.5. Không giả định pattern variable sử dụng được ngoài mọi nhánh

```java
static int textLength(Object input) {
    if (input instanceof String text) {
        return text.length();
    }

    // Không thể dùng text ở đây: pattern có thể thất bại.
    return 0;
}
```

Ngược lại, nếu nhánh phủ định **kết thúc việc thực thi** bằng `return` hoặc `throw` thì biến có thể được sử dụng sau `if` như mục 5.4.

### 9.6. Pattern variable không tự động là `final`

Ở Java 17, pattern variable không mặc nhiên là `final`:

```java
static void printTrimmed(Object input) {
    if (input instanceof String text) {
        text = text.strip(); // Hợp lệ trong Java 17
        System.out.println(text);
    }
}
```

Trong nhiều trường hợp, vẫn nên **giữ biến pattern để biểu diễn đối tượng đã khớp** và tạo biến cục bộ khác khi một phép biến đổi có ý nghĩa riêng:

```java
if (input instanceof String text) {
    String normalized = text.strip();
    System.out.println(normalized);
}
```

Cách đó giúp phân biệt dữ liệu gốc với dữ liệu được chuẩn hóa, đặc biệt trong code xử lý dữ liệu nhiều bước.

### 9.7. Tránh tên biến mâu thuẫn với biến đang nằm trong phạm vi

Biến pattern vẫn tuân theo quy tắc phạm vi và xung đột tên của biến cục bộ:

```java
static void show(Object value) {
    String text = "fallback";

    // SAI: không thể khai báo pattern variable trùng tên local text
    // khi hai phạm vi bị chồng lên nhau.
    // if (value instanceof String text) {
    //     System.out.println(text);
    // }

    if (value instanceof String actualText) {
        System.out.println(actualText);
    } else {
        System.out.println(text);
    }
}
```

### 9.8. Pattern matching không thay thế xác thực giá trị nghiệp vụ

```java
if (raw instanceof String email) {
    // Chỉ biết raw là String, chưa biết có phải email hợp lệ.
}
```

Tương tự, `raw instanceof Integer count` không bảo đảm `count >= 0`. Hãy phân biệt:

- **Kiểm tra kiểu:** giá trị có đúng loại dữ liệu không?
- **Kiểm tra giá trị:** chuỗi có hợp lệ, số có nằm trong miền cho phép, dữ liệu có thỏa quan hệ nghiệp vụ không?

Với dữ liệu đầu vào từ người dùng hoặc hệ thống khác, cần cả hai tầng kiểm tra.

## 10. Quy trình refactor một hàm xử lý dữ liệu có nhiều kiểu

Khi gặp một phương thức dài gồm nhiều `instanceof`, cast và khối `if` lồng nhau, có thể chỉnh từng bước:

1. **Xác định kiểu tĩnh của đầu vào:** thường là `Object`, interface hoặc class cha. Ghi rõ các kiểu runtime mà hàm có thể gặp.
2. **Tìm cặp thao tác lặp:** `value instanceof X` ngay trước `X x = (X) value`. Đổi thành `value instanceof X x`.
3. **Giữ nguyên ý nghĩa nhánh:** đổi cú pháp từng nhánh trước; chưa cần sắp xếp lại thứ tự kiểu hoặc thay đổi fallback.
4. **Đưa các điều kiện phụ an toàn vào `&&`:** ví dụ `value instanceof String text && !text.isBlank()`.
5. **Dùng guard clause nếu giúp giảm lồng nhau:** `if (!(value instanceof X x)) return/throw;` rồi tiếp tục xử lý với `x`.
6. **Loại bỏ cast thừa và làm rõ tên pattern variable:** dùng `order`, `error`, `name`; tránh dùng hàng loạt tên `x`/`a` khó đọc.
7. **Xem xét giới hạn thiết kế:** nếu cùng một phép phân nhánh bị sao chép nhiều nơi hoặc tập kiểu liên tục thay đổi, cân nhắc mô hình polymorphism/visitor hay cấu trúc dữ liệu rõ hơn.

### Ví dụ thay ba tầng `if` bằng guard clause

**Trước:**

```java
static String parseTitle(Object raw) {
    if (raw instanceof String) {
        String title = (String) raw;
        if (!title.isBlank()) {
            String normalized = title.strip();
            if (normalized.length() <= 40) {
                return normalized;
            }
        }
    }
    throw new IllegalArgumentException("Tiêu đề không hợp lệ");
}
```

**Sau:**

```java
static String parseTitle(Object raw) {
    if (!(raw instanceof String title)) {
        throw new IllegalArgumentException("Tiêu đề phải là chuỗi");
    }

    String normalized = title.strip();
    if (normalized.isEmpty() || normalized.length() > 40) {
        throw new IllegalArgumentException("Tiêu đề không hợp lệ");
    }
    return normalized;
}
```

Phiên bản mới giữ phép kiểm tra kiểu rõ ràng, không cần ép kiểu và tách bước chuẩn hóa khỏi bước xác thực. Khi áp dụng vào dự án thật, phải cân nhắc liệu thay đổi thông điệp ngoại lệ hoặc hành vi xử lý khoảng trắng có ảnh hưởng đến API/caller hiện tại hay không.

## 11. Khi nào dùng pattern, khi nào dùng đa hình?

Pattern matching phù hợp ở **ranh giới dữ liệu** hoặc khi cần lựa chọn hành vi theo loại giá trị runtime:

- Đọc dữ liệu dị loại từ `Map<?, ?>` hoặc `List<?>`.
- Xử lý nhiều loại message/event với một API đầu vào chung.
- Ánh xạ các biến thể của sealed hierarchy sang định dạng hiển thị, DTO hoặc báo cáo.
- Kiểm tra một đối tượng ở ranh giới giữa hai lớp đã biết kiểu.

Tuy nhiên, nếu mã phải liên tục hỏi “đây là loại gì?” để thực hiện cùng một hành vi, thường nên cân nhắc đa hình:

**Liên tục phân nhánh ở phía người dùng:**

```java
interface Shape { }
record Rectangle(double width, double height) implements Shape { }
record Circle(double radius) implements Shape { }

static double area(Shape shape) {
    if (shape instanceof Rectangle rect) {
        return rect.width() * rect.height();
    }
    if (shape instanceof Circle circle) {
        return Math.PI * circle.radius() * circle.radius();
    }
    throw new IllegalArgumentException("Shape không hỗ trợ");
}
```

**Hoặc đặt hành vi chung vào kiểu cha:**

```java
interface Shape {
    double area();
}

record Rectangle(double width, double height) implements Shape {
    public double area() {
        return width * height;
    }
}

record Circle(double radius) implements Shape {
    public double area() {
        return Math.PI * radius * radius;
    }
}

static double area(Shape shape) {
    return shape.area();
}
```

Hai đoạn trên là **hai cách thiết kế độc lập**, không đặt các định nghĩa cùng tên vào chung một file. Cách thứ hai thường phù hợp hơn khi tính diện tích là hành vi cốt lõi của từng hình và bạn muốn mỗi lớp tự định nghĩa nó. Trong khi đó, một bộ chuyển đổi bên ngoài phục vụ nhiều định dạng khác nhau có thể hợp lý hơn nếu sử dụng pattern ở một vị trí tập trung.

## 12. Bài tập thực hành

### Bài 1 — Loại bỏ phép ép kiểu lặp

Refactor đoạn mã Java 17 sau bằng `instanceof` pattern:

```java
static String inspect(Object value) {
    if (value instanceof Long) {
        Long number = (Long) value;
        return "Long=" + number;
    } else if (value instanceof String) {
        String text = (String) value;
        return "String=" + text.strip();
    }
    return "Unsupported";
}
```

**Lời giải tham khảo:**

```java
static String inspect(Object value) {
    if (value instanceof Long number) {
        return "Long=" + number;
    }
    if (value instanceof String text) {
        return "String=" + text.strip();
    }
    return "Unsupported";
}
```

### Bài 2 — Lọc dữ liệu theo kiểu và điều kiện

Viết phương thức `static List<String> normalizeCodes(List<?> rawCodes)`:

- Chỉ giữ phần tử kiểu `String`.
- Bỏ chuỗi trống hoặc chỉ chứa khoảng trắng.
- Xóa khoảng trắng hai đầu và chuyển sang chữ hoa bằng `Locale.ROOT`.
- Không dùng bất kỳ phép ép kiểu thủ công nào.

**Lời giải tham khảo:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

static List<String> normalizeCodes(List<?> rawCodes) {
    List<String> result = new ArrayList<>();
    for (Object value : rawCodes) {
        if (value instanceof String code && !code.isBlank()) {
            result.add(code.strip().toUpperCase(Locale.ROOT));
        }
    }
    return List.copyOf(result);
}
```

Ví dụ `normalizeCodes(List.of(" abc ", 123, "", " xYz "))` trả về danh sách `[ABC, XYZ]`.

### Bài 3 — Guard clause và `Map` dữ liệu động

Cho đầu vào `Object raw`, yêu cầu:

1. Phải là `Map<?, ?>`.
2. Khóa `"name"` phải chứa `String` không rỗng.
3. Trả về tên sau khi `strip()`.
4. Nếu một điều kiện sai, ném `IllegalArgumentException`.

**Lời giải:**

```java
import java.util.Map;

static String readName(Object raw) {
    if (!(raw instanceof Map<?, ?> values)) {
        throw new IllegalArgumentException("Dữ liệu phải là Map");
    }

    Object nameValue = values.get("name");
    if (!(nameValue instanceof String name) || name.isBlank()) {
        throw new IllegalArgumentException("name phải là chuỗi không rỗng");
    }

    return name.strip();
}
```

### Bài 4 — Phát hiện lỗi phạm vi biến

Xem hai đoạn sau:

```java
// A
// if (value instanceof String text || text.isBlank()) { ... }

// B
// if (!(value instanceof String text)) return;
// System.out.println(text.length());
```

**Câu hỏi:** Đoạn nào hợp lệ về phạm vi biến pattern trong Java 17, và vì sao?

**Đáp án:** A không hợp lệ vì `||` có thể đánh giá vế phải sau khi phép kiểm tra kiểu thất bại, khiến `text` chưa được gán. B hợp lệ nếu nằm trong phương thức có kiểu trả về phù hợp `return;` (ví dụ phương thức `void`): khi vượt qua `if`, điều kiện phủ định phải sai, nên `text` chắc chắn khớp `String`.

### Bài 5 — Mở rộng xử lý biến thể

Giả sử `sealed interface Result permits Success, Failure` đã có hai record. Thêm `Pending(String ticketId)` và chỉnh `toMessage`.

**Câu hỏi:** Java 17 có tự báo lỗi biên dịch ở chuỗi `if` cũ vì thiếu nhánh `Pending` không?

**Đáp án:** Không. Sau khi thêm `Pending` vào `permits`, mã `if/else if` cũ vẫn có thể biên dịch, nhưng sẽ rơi vào fallback khi nhận `Pending`. Cần chủ động cập nhật hàm xử lý và bài kiểm thử liên quan.

## 13. Những điểm cần ghi nhớ

| Tình huống | Cách dùng Java 17 |
|---|---|
| Kiểm tra kiểu rồi cast ngay | `if (raw instanceof String text)` |
| Thêm điều kiện dựa trên subtype | `if (raw instanceof String text && !text.isBlank())` |
| Muốn xử lý tiếp sau khi loại bỏ sai kiểu | `if (!(raw instanceof String text)) throw ...;` |
| Dữ liệu generic không biết component type | `raw instanceof List<?> list`, kiểm tra phần tử riêng |
| Dữ liệu dạng record | `raw instanceof RecordType record`, dùng `record.component()` |
| Dữ liệu `null` | `instanceof` trả `false`; xử lý `null` riêng nếu cần |
| Cần phân nhánh nhiều loại | Chuỗi `if/else if` có pattern, nhánh đặc thù trước nhánh rộng |
| Muốn dùng `case Type variable ->` | Đây là pattern switch preview ở Java 17; không dùng trong mã Java 17 ổn định |
| Muốn bóc tách `RecordType(var a, var b)` | Record patterns thuộc Java 21; Java 17 dùng accessor |
| Nghiệp vụ có kiểm tra giá trị | Pattern chỉ kiểm tra kiểu, vẫn cần validation |

## 14. Tài liệu chính thức

- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): đề xuất đã được hoàn thiện trong Java 16, dùng ổn định với Java 17.
- [Oracle Java 17 — Pattern Matching](https://docs.oracle.com/en/java/javase/17/language/pattern-matching.html): hướng dẫn chính thức, ví dụ áp dụng type pattern trong xử lý đối tượng.
- [Java Language Specification 17 — `15.20.2 The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): quy tắc kiểm tra kiểu và kiểm tra mẫu.
- [Java Language Specification 17 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi biến pattern phụ thuộc luồng điều khiển.
- [Java Language Specification 17 — `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): định nghĩa type pattern trong Java 17.
- [JEP 406 — Pattern Matching for `switch` (Preview in Java 17)](https://openjdk.org/jeps/406) và [JEP 441 — Pattern Matching for `switch` (Java 21)](https://openjdk.org/jeps/441): phân biệt cú pháp preview của Java 17 với cú pháp ổn định của các bản Java sau.
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440): tham khảo để không nhầm việc truy cập component của record trong Java 17 với destructuring của phiên bản mới.

**Kết luận:** Khi xử lý dữ liệu có nhiều kiểu runtime, thay chuỗi `instanceof` + `(Type) value` bằng **`instanceof Type variable`** sẽ giảm mã ép kiểu và biểu diễn ràng buộc kiểu ngay tại điều kiện. Kết hợp flow scoping, `&&`, guard clauses và kiểm tra schema/giá trị để xử lý dữ liệu rõ ràng, an toàn hơn trên Java 17 mà không phụ thuộc vào tính năng preview.
