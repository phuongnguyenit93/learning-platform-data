# Phủ định điều kiện và thoát sớm với pattern `instanceof` trong Java 17

Khi kiểm tra kiểu dữ liệu của một đối tượng, Java 17 cho phép viết **pattern matching cho `instanceof`** để vừa xác nhận kiểu, vừa khai báo một biến đã được chuyển sang kiểu đó. Tính năng này là tính năng chính thức của ngôn ngữ từ Java 16 và được sử dụng ổn định trong Java 17.

Một tình huống rất hay gặp trong code thực tế là: **nếu đối tượng không đúng kiểu, thoát khỏi phương thức hoặc bỏ qua phần tử; nếu đúng kiểu, tiếp tục xử lý**. Cách diễn đạt này kết hợp ba kiến thức quan trọng:

- Phủ định kết quả `instanceof` bằng toán tử `!`.
- Viết **guard clause** — nhánh kiểm tra điều kiện lỗi và thoát sớm.
- Hiểu **flow scoping** — phạm vi của pattern variable phụ thuộc vào việc trình biên dịch có chứng minh được điều kiện kiểm tra kiểu đã thành công hay không.

Bài này trình bày các quy tắc đó qua những đoạn mã Java 17 có thể dùng trong ứng dụng hiện nay.

## 1. Từ `instanceof` truyền thống đến pattern variable

Trước khi dùng pattern matching, một đoạn mã xử lý chuỗi từ biến kiểu `Object` thường viết như sau:

```java
public static void printLength(Object value) {
    if (!(value instanceof String)) {
        return;
    }

    String text = (String) value;
    System.out.println(text.length());
}
```

Mã trên hoạt động, nhưng phải vừa kiểm tra bằng `instanceof` vừa ép kiểu tường minh bằng `(String) value`.

Với Java 17, có thể rút gọn:

```java
public static void printLength(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    System.out.println(text.length());
}
```

Trong biểu thức `value instanceof String text`:

| Thành phần | Vai trò |
| --- | --- |
| `value` | Biểu thức chứa đối tượng cần kiểm tra. |
| `String` | Kiểu muốn kiểm tra. |
| `text` | **Pattern variable** nhận giá trị đã được nhìn nhận là `String` nếu phép kiểm tra thành công. |
| `!` | Phủ định kết quả `instanceof`. |
| `return` | Thoát phương thức nếu đối tượng không phải `String`. |

Điểm đáng chú ý: dù `text` được viết **bên trong điều kiện `if`**, nó vẫn được sử dụng **sau câu lệnh `if`**. Đây là kết quả của quy tắc *flow scoping*; biến không chỉ đơn thuần sống trong phạm vi cặp ngoặc nhọn gần nhất.

## 2. Vì sao biến `text` hợp lệ sau điều kiện phủ định?

Xét lại đoạn mã:

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }

    return text.length();
}
```

Khi thực thi, có hai khả năng:

1. `input` **không phải** `String`: biểu thức `input instanceof String text` là `false`; sau khi phủ định thì điều kiện `if` thành `true` và `return 0` lập tức kết thúc phương thức.
2. `input` **là** `String`: biểu thức `instanceof` là `true`; phép phủ định cho ra `false`; chương trình bỏ qua nhánh `if` và tiếp tục tới `text.length()`. Lúc này `text` chắc chắn đã được gán.

Đường đi của chương trình:

```text
                         Object input
                              |
                              v
                 input instanceof String text
                      /                 \
                   false                true
                    |                    |
                    v                    v
                  Phủ định (!)          Phủ định (!)
                    |                    |
                   true                 false
                    |                    |
                    v                    v
                if branch           Bỏ qua if branch
                return 0                |
                                         v
                                 text đã được gán
                                         |
                                         v
                                return text.length()
```

Trình biên dịch có thể chứng minh rằng **mọi đường chạy tới câu lệnh cuối** đều đã vượt qua phép kiểm tra kiểu thành công. Vì vậy, `text` hợp lệ ở vị trí đó.

Quy tắc này không có nghĩa mọi pattern variable đều dùng được sau mọi `if`. Nó chỉ tồn tại ở những vị trí mà luồng điều khiển bảo đảm pattern đã khớp.

## 3. Đối chiếu: chỉ phủ định thôi chưa đủ

**Sai — nhánh kiểm tra thất bại vẫn có thể đi tiếp:**

```java
static void show(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Không phải chuỗi");
    }

    System.out.println(text.length()); // LỖI BIÊN DỊCH
}
```

Nếu `input` là `Integer`, sau khi in thông báo, chương trình vẫn tiếp tục tới `text.length()` mặc dù không có biến `text` đã được khớp. Do đó trình biên dịch không cho phép sử dụng `text` ở đây.

**Đúng — thêm thoát sớm:**

```java
static void show(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Không phải chuỗi");
        return;
    }

    System.out.println(text.length());
}
```

**Đúng — xử lý nhánh thành công ngay bên trong `else`:**

```java
static void show(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Không phải chuỗi");
    } else {
        System.out.println(text.length());
    }
}
```

Trong `else`, điều kiện phủ định đã thất bại, tương đương với việc phép `instanceof` thành công. Vì thế `text` có thể dùng trong `else`.

Nếu chọn phiên bản guard clause có `return`, phần xử lý chính được giữ ở cấp thụt lề ngắn hơn và không cần `else`.

## 4. Cú pháp chuẩn cho guard clause kết hợp pattern `instanceof`

Một mẫu thường dùng là:

```java
static Result process(Object input) {
    if (!(input instanceof ExpectedType value)) {
        // Xử lý đầu vào không đúng kiểu.
        return fallbackResult();
    }

    // value có kiểu ExpectedType ở đây.
    return use(value);
}
```

Các tên `Result`, `ExpectedType`, `fallbackResult` và `use` ở trên là ký hiệu minh họa. Ví dụ Java 17 hoàn chỉnh:

```java
public class PatternGuardDemo {
    static String normalizeName(Object input) {
        if (!(input instanceof String name)) {
            return "UNKNOWN";
        }

        String normalized = name.strip();

        if (normalized.isBlank()) {
            return "UNKNOWN";
        }

        return normalized;
    }

    public static void main(String[] args) {
        System.out.println(normalizeName("  Minh  "));
        System.out.println(normalizeName(123));
        System.out.println(normalizeName("   "));
    }
}
```

Đầu ra:

```text
Minh
UNKNOWN
UNKNOWN
```

Biên dịch bằng Java 17:

```bash
javac --release 17 -encoding UTF-8 PatternGuardDemo.java
java PatternGuardDemo
```

Ở đây có hai điều kiện được xử lý độc lập:

- `!(input instanceof String name)`: từ chối dữ liệu không phải `String`.
- `normalized.isBlank()`: từ chối chuỗi hợp kiểu nhưng không có nội dung sau khi loại bỏ khoảng trắng hai đầu.

Pattern matching giải quyết **kiểm tra kiểu**, còn validation của dữ liệu bên trong kiểu vẫn do ứng dụng quyết định.

## 5. Kết hợp phủ định với `throw` để báo đầu vào sai

Không phải mọi tình huống đều nên trả giá trị mặc định. Đối với API yêu cầu đầu vào đúng kiểu, cách phù hợp có thể là **ném ngoại lệ**:

```java
public class StrictNumberDemo {
    static int doubleInteger(Object input) {
        if (!(input instanceof Integer number)) {
            throw new IllegalArgumentException(
                    "input phải là một Integer"
            );
        }

        return Math.multiplyExact(number, 2);
    }

    public static void main(String[] args) {
        System.out.println(doubleInteger(12)); // 24
        System.out.println(doubleInteger("12")); // IllegalArgumentException
    }
}
```

Với đầu vào không phải `Integer`, `throw` kết thúc đường thực thi bình thường của phương thức. Do đó, khi chương trình đi đến `Math.multiplyExact(number, 2)`, pattern `Integer number` chắc chắn đã khớp.

Sử dụng `Math.multiplyExact` ở ví dụ giúp phép nhân báo `ArithmeticException` nếu kết quả vượt miền `int`; đó là một quy tắc riêng đối với tính toán số học, không phải yêu cầu của pattern matching.

Các kiểu thoát sớm phổ biến có ý nghĩa:

| Thao tác | Kết quả luồng điều khiển | Tình huống phù hợp |
| --- | --- | --- |
| `return;` | Kết thúc phương thức `void`. | Bỏ qua xử lý khi đầu vào không phù hợp. |
| `return value;` | Kết thúc phương thức và trả kết quả. | Có giá trị dự phòng hợp lệ. |
| `throw new ...` | Ném ngoại lệ; không tiếp tục bình thường. | Đầu vào vi phạm hợp đồng của phương thức. |
| `continue;` | Bỏ phần còn lại của lượt lặp hiện tại. | Lọc phần tử sai kiểu trong vòng lặp. |
| `break;` | Thoát khỏi vòng lặp hoặc cấu trúc được phép `break`. | Ngừng duyệt khi gặp phần tử không phù hợp. |

Điểm chung là **luồng chạy không thể tiếp tục tới đoạn dùng pattern variable trên một đường mà pattern chưa khớp**.

## 6. Dùng `continue` để bỏ qua phần tử sai kiểu trong vòng lặp

Khi duyệt một danh sách `Object` chứa nhiều kiểu dữ liệu, một guard clause với `continue` thường rõ ràng hơn việc lồng nhiều nhánh `if`.

```java
import java.util.List;

public class FilterNames {
    public static void main(String[] args) {
        List<Object> values = List.of(
                "  An  ",
                100,
                "  Bình  ",
                false,
                "  Chi  "
        );

        for (Object item : values) {
            if (!(item instanceof String name)) {
                continue;
            }

            System.out.println(name.strip());
        }
    }
}
```

Đầu ra:

```text
An
Bình
Chi
```

Mỗi lượt lặp:

- Nếu `item` không phải chuỗi, `continue` chuyển ngay sang phần tử tiếp theo.
- Nếu `item` là chuỗi, điều kiện phủ định là `false`, nên `name` được sử dụng an toàn trong phần còn lại của lượt lặp.

**Đối chiếu — thiếu `continue` thì không hợp lệ:**

```java
for (Object item : values) {
    if (!(item instanceof String name)) {
        System.out.println("Bỏ qua");
    }

    System.out.println(name.strip()); // LỖI BIÊN DỊCH
}
```

Không có lời gọi thoát sớm, trình biên dịch không thể bảo đảm `name` luôn tồn tại ở câu lệnh `println`.

## 7. Dùng `break` khi gặp phần tử không phù hợp

Tương tự `continue`, `break` có thể loại bỏ đường đi mà pattern không khớp khỏi phần code còn lại bên trong vòng lặp.

```java
import java.util.List;

public class ReadPrefix {
    public static void main(String[] args) {
        List<Object> values = List.of(
                "first",
                "second",
                42,
                "fourth"
        );

        for (Object item : values) {
            if (!(item instanceof String text)) {
                break;
            }

            System.out.println(text.toUpperCase());
        }
    }
}
```

Đầu ra:

```text
FIRST
SECOND
```

Khi gặp `42`, `break` thoát khỏi vòng lặp nên `text.toUpperCase()` sẽ không được thực hiện ở lượt đó.

Phân biệt:

- `continue`: bỏ qua **một lượt** và tiếp tục duyệt các phần tử sau.
- `break`: dừng **toàn bộ vòng lặp** gần nhất (trừ khi dùng nhãn để chỉ vòng lặp khác).

Vì vậy, chọn `continue` hay `break` là quyết định về **ý nghĩa nghiệp vụ**, không chỉ là cách làm cho pattern variable có phạm vi hợp lệ.

## 8. Phủ định và toán tử `&&`: điều kiện nào được kiểm tra trước?

Java sử dụng **short-circuit evaluation** đối với `&&` và `||`:

- Với `A && B`: chỉ tính `B` nếu `A` là `true`.
- Với `A || B`: chỉ tính `B` nếu `A` là `false`.

Thứ tự này quyết định khi nào pattern variable đã chắc chắn được gán.

### 8.1. Dùng `&&` sau phép `instanceof` khẳng định

**Đúng:**

```java
static boolean isLongName(Object input) {
    return input instanceof String name && name.length() >= 5;
}
```

`name.length()` chỉ chạy khi `input instanceof String name` là `true`. Đến lúc đó `name` đã có giá trị `String`.

### 8.2. Không dùng `&&` ngay sau phép `instanceof` bị phủ định để đọc biến

**Sai:**

```java
static boolean invalid(Object input) {
    return !(input instanceof String name) && name.isBlank();
    //                                     ^  LỖI: name chưa chắc tồn tại
}
```

Phép `&&` chỉ tính vế phải khi vế trái là `true`. Nhưng vế trái `!(input instanceof String name)` bằng `true` chính khi pattern **không khớp**. Vì thế `name` không thể dùng ở vế phải.

Một cách diễn đạt hợp lệ cho ý định “không phải chuỗi hoặc là chuỗi rỗng” nằm ở phần kế tiếp.

## 9. Phủ định và toán tử `||`: kiểm tra kiểu hoặc dữ liệu không hợp lệ

Khi muốn **từ chối đối tượng không phải `String` hoặc chuỗi trống**, có thể kết hợp phủ định với `||`:

```java
static String requireNonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                "Cần một String không trống"
        );
    }

    return text;
}
```

Tại sao hợp lệ?

1. Nếu `input` không phải `String`, vế `!(input instanceof String text)` bằng `true`. Vì là `||`, Java **không đánh giá** `text.isBlank()`. Điều kiện toàn bộ là `true` và ném ngoại lệ.
2. Nếu `input` là `String`, vế phủ định bằng `false`. Java mới đánh giá `text.isBlank()`, lúc này `text` đã được gán.
3. Nếu toàn bộ điều kiện bằng `false`, `input` chắc chắn là chuỗi không trống, nên `return text` hợp lệ sau `if`.

Có thể mở rộng ví dụ để chuẩn hóa:

```java
static String requireNonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("input không hợp lệ");
    }

    return text.strip();
}
```

Với yêu cầu **chỉ chấp nhận chuỗi có nội dung sau khi cắt khoảng trắng đầu/cuối**, `text.isBlank()` đủ để từ chối chuỗi chỉ chứa whitespace.

### Bảng đối chiếu bốn mẫu logic

| Biểu thức | Có được dùng pattern variable ở vế phải? | Giải thích |
| --- | --- | --- |
| `input instanceof String text && text.length() > 3` | **Có** | Vế phải chạy khi `instanceof` đã khớp. |
| `!(input instanceof String text) || text.isBlank()` | **Có** | Vế phải chạy khi phủ định là `false`, tức pattern đã khớp. |
| `input instanceof String text || text.isBlank()` | **Không** | Vế phải chạy khi `instanceof` thất bại. |
| `!(input instanceof String text) && text.isBlank()` | **Không** | Vế phải chạy khi phủ định là `true`, tức pattern thất bại. |

Quy tắc thực hành: **đừng ghi nhớ máy móc “`&&` đúng, `||` sai”**. Hãy xét **trường hợp nào khiến vế phải được đánh giá** và trong trường hợp ấy pattern đã khớp hay chưa.

## 10. Điều kiện phủ định với nhiều nhánh lỗi

Khi kiểm tra nhiều thuộc tính, nên giữ **điều kiện sai** và **thông báo lỗi** rõ ràng.

Ví dụ một API chỉ chấp nhận số nguyên dương:

```java
public class QuantityChecker {
    static int requirePositiveInteger(Object input) {
        if (!(input instanceof Integer quantity)) {
            throw new IllegalArgumentException(
                    "quantity phải có kiểu Integer"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity phải lớn hơn 0"
            );
        }

        return quantity;
    }

    public static void main(String[] args) {
        System.out.println(requirePositiveInteger(8));
    }
}
```

Mẫu tách hai guard clause trên phù hợp khi người gọi cần thông báo lỗi phân biệt **sai kiểu** và **sai giá trị**.

Có thể rút thành một điều kiện:

```java
static int requirePositiveInteger(Object input) {
    if (!(input instanceof Integer quantity) || quantity <= 0) {
        throw new IllegalArgumentException(
                "Cần một Integer lớn hơn 0"
        );
    }

    return quantity;
}
```

Hai cách đều hợp lệ với Java 17. Chọn cách tách hoặc gộp tùy mức độ cần giải thích từng lỗi cho người dùng API.

## 11. `null` được xử lý thế nào?

Biểu thức pattern `instanceof` không khớp khi đối tượng là `null`:

```java
Object input = null;

if (!(input instanceof String text)) {
    System.out.println("Không phải String");
    return;
}

// Với trường hợp null, chương trình không tới đây.
```

Ở đây `input instanceof String text` là `false`, nên phủ định là `true` và thực hiện thoát sớm. Không có `NullPointerException` chỉ vì kiểm tra `instanceof` với `null`.

Ví dụ có `||` cũng không truy cập biến chưa có giá trị:

```java
static boolean valid(Object input) {
    return input instanceof String text && !text.isBlank();
}

static boolean invalid(Object input) {
    return !(input instanceof String text) || text.isBlank();
}
```

Với `input == null`:

- `valid(input)` trả `false`.
- `invalid(input)` trả `true`.
- Không bên nào gọi `text.isBlank()` vì quy tắc short-circuit.

Điều này không có nghĩa mọi điều kiện lồng nhau đều chống lỗi `null`. Nếu bạn gọi `input.toString()` **trước** khi kiểm tra kiểu, thao tác đó vẫn có thể ném `NullPointerException`.

## 12. Không có thoát sớm: phạm vi biến thường bị giới hạn

So sánh ba phiên bản có mục tiêu tương tự.

### Phiên bản A — nhánh thành công nằm trong `if`

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip());
    }

    // Không dùng text ở đây: nhánh instanceof có thể không khớp.
}
```

Cách này phù hợp khi chỉ xử lý một trường hợp có kiểu đúng, không cần thoát phương thức.

### Phiên bản B — nhánh lỗi thoát sớm bằng `return`

```java
static void print(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    System.out.println(text.strip());
}
```

Cách này phù hợp khi toàn bộ phần còn lại của phương thức đòi hỏi `value` phải là `String`.

### Phiên bản C — có `else` nhưng không cần thoát cả phương thức

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println("String: " + text.strip());
    } else {
        System.out.println("Kiểu khác");
    }
}
```

Cách này phù hợp khi mỗi nhánh có cách xử lý độc lập. Không phải cứ dùng pattern variable là cần guard clause; guard clause chỉ có lợi khi điều kiện sai nên dừng sớm.

## 13. Flow scoping với phủ định có ý nghĩa gì trong thiết kế API?

Cách viết guard clause giúp đặt tiền điều kiện ở đầu phương thức và giữ logic chính ở một luồng rõ ràng.

Ví dụ xử lý yêu cầu chỉ chấp nhận đối tượng đã được phân loại thành `String`:

```java
public class UserService {
    static String toLoginId(Object rawId) {
        if (!(rawId instanceof String id)) {
            throw new IllegalArgumentException(
                    "rawId phải là String"
            );
        }

        String cleaned = id.strip();

        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException(
                    "rawId không được trống"
            );
        }

        if (cleaned.length() > 30) {
            throw new IllegalArgumentException(
                    "rawId không được vượt quá 30 ký tự"
            );
        }

        return cleaned;
    }
}
```

Chuỗi điều kiện ở đầu phương thức lần lượt từ chối:

1. Đối tượng không phải `String` (bao gồm `null`).
2. Chuỗi rỗng sau chuẩn hóa.
3. Chuỗi vượt quá giới hạn độ dài do ví dụ đặt ra.

Khi thực thi đến `return cleaned`, phần xử lý chính đã được bảo đảm về **kiểu** và **các điều kiện dữ liệu** mà phương thức yêu cầu.

Nếu tham số của API vốn đã khai báo là `String` và không cần chấp nhận kiểu khác, có thể kiểm tra `null`/nội dung trực tiếp; không cần ép mọi API phải nhận `Object` chỉ để sử dụng pattern matching. Pattern `instanceof` đặc biệt hữu ích ở ranh giới nơi dữ liệu thực sự có nhiều kiểu khả dĩ.

## 14. Những lỗi thường gặp

### Lỗi 1 — quên cặp ngoặc quanh biểu thức trước `!`

**Sai:**

```java
if (!input instanceof String text) {
    return;
}
```

Toán tử `!` áp dụng lên toán hạng của nó trước khi biểu thức `instanceof` được phân tích theo ý định người viết; viết như vậy không hợp lệ cho một đối tượng kiểu `Object`.

**Đúng:**

```java
if (!(input instanceof String text)) {
    return;
}
```

Mẫu cần nhớ: `!(expression instanceof Type variable)`.

### Lỗi 2 — sử dụng biến sau một nhánh kiểm tra có thể kết thúc bình thường

**Sai:**

```java
static void inspect(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Sai kiểu");
    }

    System.out.println(text.length()); // LỖI
}
```

**Đúng:** nhánh sai kiểu phải thoát sớm, hoặc chuyển phần dùng `text` vào nhánh đảm bảo phép kiểm tra đã khớp.

### Lỗi 3 — dùng nhầm toán tử `&&` và `||`

**Sai:**

```java
static boolean bad(Object input) {
    return input instanceof String text || text.isEmpty();
}
```

**Đúng nếu muốn nhận chuỗi không rỗng:**

```java
static boolean good(Object input) {
    return input instanceof String text && !text.isEmpty();
}
```

**Đúng nếu muốn nhận diện giá trị sai:**

```java
static boolean isBad(Object input) {
    return !(input instanceof String text) || text.isEmpty();
}
```

Cần xác định mục tiêu của biểu thức là kiểm tra **hợp lệ** hay **không hợp lệ**, rồi chọn phép logic tương ứng.

### Lỗi 4 — tưởng rằng pattern variable tồn tại ở mọi vị trí trong phương thức

**Sai:**

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text);
    }

    System.out.println(text); // LỖI
}
```

Bên ngoài `if`, không có bảo đảm rằng `input` đã khớp `String`. Pattern variable khác với biến cục bộ khai báo ở đầu phương thức: phạm vi của nó gắn với **đường đi chắc chắn đã khớp**.

### Lỗi 5 — nhầm pattern `instanceof` với cú pháp pattern mới hơn Java 17

Java 17 hỗ trợ chính thức **type pattern** trong `instanceof`, như `input instanceof String text`.

Không nên viết bài tập Java 17 mặc định bằng các dạng cú pháp xuất hiện chính thức ở những bản Java mới hơn, chẳng hạn **record deconstruction pattern**:

```java
// Không phải cú pháp instanceof dùng được ở mức Java 17:
if (input instanceof Point(int x, int y)) {
    // ...
}
```

Nếu `Point` là record trong Java 17, vẫn có thể kiểm tra **kiểu** bằng:

```java
record Point(int x, int y) {}

static void showPoint(Object input) {
    if (!(input instanceof Point point)) {
        return;
    }

    System.out.println(point.x() + ", " + point.y());
}
```

Tương tự, pattern matching trong `switch` chưa phải tính năng chính thức của Java 17; đây là cú pháp khác, không cần thiết cho các ví dụ trong bài này.

### Lỗi 6 — cho rằng việc khớp kiểu đã kiểm tra cả giá trị

`input instanceof String text` chỉ xác nhận giá trị không `null` và có kiểu phù hợp. Nó **không** đảm bảo chuỗi có độ dài tối thiểu, đúng định dạng hay đáp ứng bất kỳ quy tắc nghiệp vụ nào.

```java
static String requireEmailLike(Object input) {
    if (!(input instanceof String email)) {
        throw new IllegalArgumentException("Cần String");
    }

    email = email.strip();

    if (email.isBlank() || !email.contains("@")) {
        throw new IllegalArgumentException("Giá trị không hợp lệ");
    }

    return email;
}
```

Kiểm tra `contains("@")` trong ví dụ chỉ là minh họa điều kiện nghiệp vụ đơn giản; **không phải bộ kiểm tra địa chỉ email đầy đủ**.

### Lỗi 7 — tạo xung đột tên với biến cục bộ đã tồn tại

Pattern variable có tên riêng và tuân theo quy tắc phạm vi/khai báo biến của Java.

**Sai — khai báo trùng tên ngay trong phạm vi đang có biến:**

```java
static void show(Object input) {
    String text = "fallback";

    if (input instanceof String text) { // LỖI: text đã được khai báo
        System.out.println(text);
    }
}
```

**Đúng — chọn tên pattern variable khác:**

```java
static void show(Object input) {
    String fallback = "fallback";

    if (input instanceof String text) {
        System.out.println(text);
    } else {
        System.out.println(fallback);
    }
}
```

## 15. Bài thực hành tổng hợp với ba kiểu thoát sớm

Bài sau dùng `return`, `continue` và `throw` để thể hiện mỗi kiểu thoát sớm có ngữ nghĩa riêng.

Tạo tệp `EarlyExitDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class EarlyExitDemo {

    static String render(Object input) {
        if (!(input instanceof String text)) {
            return "[unsupported]";
        }

        return text.strip().toUpperCase();
    }

    static List<String> onlyNonBlankStrings(List<Object> items) {
        List<String> result = new ArrayList<>();

        for (Object item : items) {
            if (!(item instanceof String text)) {
                continue;
            }

            String cleaned = text.strip();

            if (cleaned.isBlank()) {
                continue;
            }

            result.add(cleaned);
        }

        return List.copyOf(result);
    }

    static int requireInteger(Object input) {
        if (!(input instanceof Integer number)) {
            throw new IllegalArgumentException(
                    "Cần Integer, nhận giá trị khác kiểu"
            );
        }

        return number;
    }

    public static void main(String[] args) {
        System.out.println(render("  java  "));
        System.out.println(render(17));

        var source = new ArrayList<Object>();
        source.add("  Lan  ");
        source.add(123);
        source.add("   ");
        source.add("  Nam  ");
        source.add(null);

        System.out.println(onlyNonBlankStrings(source));
        System.out.println(requireInteger(42));
    }
}
```

Chạy với Java 17:

```bash
javac --release 17 -encoding UTF-8 EarlyExitDemo.java
java EarlyExitDemo
```

Đầu ra dự kiến:

```text
JAVA
[unsupported]
[Lan, Nam]
42
```

Phân tích:

- `render` dùng `return` để xử lý đối tượng không phải chuỗi ngay lập tức.
- `onlyNonBlankStrings` dùng `continue` để bỏ qua từng phần tử không đúng kiểu hoặc chuỗi không có nội dung, rồi thu kết quả thành một danh sách không cho sửa.
- `requireInteger` dùng `throw` khi vi phạm yêu cầu về kiểu đầu vào.

Cả ba sử dụng pattern variable mà không cần ép kiểu tường minh.

## 16. Bài tập tự luyện

### Bài 1 — hoàn thiện guard clause

Cho mã sau:

```java
static String normalize(Object raw) {
    if (!(raw instanceof String text)) {
        // Điền lệnh thoát phù hợp.
    }

    return text.strip();
}
```

Hãy chỉnh để phương thức trả `"N/A"` khi `raw` không phải `String`; trường hợp khớp `String` thì trả chuỗi đã gọi `strip()`.

### Bài 2 — chọn toán tử logic

Viết hàm:

```java
static boolean isValidUsername(Object raw) {
    // Chỉ đúng khi raw là String và không blank.
}
```

Hãy sử dụng `instanceof String username` và `&&` để viết một biểu thức `return` duy nhất. Sau đó viết phiên bản dùng phủ định và `||` để nhận diện trường hợp **không hợp lệ**.

### Bài 3 — sửa lỗi phạm vi biến

Cho đoạn mã lỗi:

```java
static void describe(Object value) {
    if (!(value instanceof Number number)) {
        System.out.println("Unsupported");
    }

    System.out.println(number.doubleValue());
}
```

Hãy sửa theo hai cách: (1) thêm lệnh `return` trong nhánh sai kiểu; (2) đặt phần sử dụng `number` trong nhánh `else`.

### Bài 4 — phân biệt `continue` với `break`

Cho danh sách:

```java
List<Object> values = List.of("A", 10, "B", "C");
```

Viết hai vòng lặp có cùng phép kiểm tra:

```java
if (!(value instanceof String text)) {
    // continue hoặc break
}
```

Một phiên bản dùng `continue`, phiên bản khác dùng `break`. Dự đoán các giá trị sẽ được in ra và giải thích vì sao hai kết quả khác nhau.

### Bài 5 — kiểm tra `null`

Viết phương thức trả `false` nếu đầu vào là `null`, không phải `String` hoặc là chuỗi blank; ngược lại trả `true`. Hãy dùng một biểu thức `return` duy nhất có `instanceof String text` mà không tạo `NullPointerException`.

## 17. Ghi nhớ nhanh

| Mục tiêu | Mẫu Java 17 |
| --- | --- |
| Xử lý khi đúng kiểu | `if (obj instanceof Type value) { use(value); }` |
| Trả về sớm khi sai kiểu | `if (!(obj instanceof Type value)) return fallback;` |
| Ném ngoại lệ khi sai kiểu | `if (!(obj instanceof Type value)) throw new IllegalArgumentException(...);` |
| Bỏ lượt lặp khi sai kiểu | `if (!(obj instanceof Type value)) continue;` |
| Dừng vòng lặp khi sai kiểu | `if (!(obj instanceof Type value)) break;` |
| Kiểm tra đúng kiểu **và** điều kiện phụ | `obj instanceof Type value && valid(value)` |
| Từ chối sai kiểu **hoặc** dữ liệu không hợp lệ | `!(obj instanceof Type value) || invalid(value)` |
| Dùng pattern variable phía sau `if` | Bảo đảm mọi nhánh không khớp đã thoát khỏi luồng thực thi đi tới chỗ sử dụng. |

**Nguyên tắc cốt lõi:** Trong Java 17, phạm vi của pattern variable phụ thuộc vào **luồng điều khiển**. Khi điều kiện phủ định `!(obj instanceof Type value)` dẫn đến `return`, `throw`, `continue` hoặc `break` theo đúng ngữ cảnh, phần code tiếp tục xử lý có thể sử dụng `value` vì đường đi không khớp đã bị loại bỏ. Hiểu quy tắc này giúp viết guard clause ngắn gọn, an toàn về kiểu và dễ theo dõi hơn.
