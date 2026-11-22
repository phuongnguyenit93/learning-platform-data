# Điều kiện dùng biến sau `if` và lỗi với `||` trong pattern matching for `instanceof` (Java 17)

Khi viết `if (value instanceof String text)`, Java không chỉ kiểm tra kiểu dữ liệu: nếu phép kiểm tra thành công, Java còn tạo biến `text` có kiểu `String` để sử dụng mà không cần ép kiểu thủ công. Tuy nhiên, **biến pattern không tồn tại ở mọi vị trí sau câu lệnh `if`**. Java chỉ cho phép dùng nó tại những vị trí mà luồng điều khiển bảo đảm phép kiểm tra đã khớp (*definitely matched*).

Đây là quy tắc **flow scoping**. Hiểu quy tắc này đặc biệt quan trọng khi sử dụng `&&`, `||`, phủ định `!` và các nhánh thoát sớm bằng `return` hoặc `throw`.

> **Phạm vi phiên bản:** Pattern matching for `instanceof` đã chính thức từ Java 16 (JEP 394) và dùng ổn định trong Java 17; các ví dụ dưới đây không cần `--enable-preview`. Chỉ sử dụng cú pháp áp dụng cho Java 17 trở lên, không dựa vào các bản preview trước đây.

## 1. Từ `instanceof` truyền thống đến biến pattern

Trước khi dùng pattern matching, mã kiểm tra rồi ép kiểu thường được viết như sau:

~~~java
static void printLength(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
~~~

Trong Java 17, có thể viết gọn:

~~~java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
~~~

Biểu thức:

~~~java
value instanceof String text
~~~

gồm ba phần:

| Thành phần | Ý nghĩa |
|---|---|
| `value` | Biểu thức cần kiểm tra, có kiểu tĩnh `Object` trong ví dụ |
| `String` | Kiểu mà đối tượng cần khớp |
| `text` | Biến pattern kiểu `String`, chỉ khả dụng ở những vị trí Java xác định đã khớp |

Nếu `value` tham chiếu đến một đối tượng `String`, phép kiểm tra trả về `true` và biến `text` liên kết với tham chiếu đó. Nếu `value` là đối tượng kiểu khác hoặc `null`, kết quả là `false`; không có giá trị `String` hợp lệ nào để dùng thông qua `text`.

Điểm khác biệt với cách cũ là bạn **không phải tự khai báo rồi ép kiểu**. Đổi lại, cần hiểu rõ phạm vi của biến do phép kiểm tra tạo ra.

## 2. Quy tắc cốt lõi: biến chỉ tồn tại nơi đã chắc chắn khớp

Hãy xem:

~~~java
static void demo(Object value) {
    if (value instanceof String text) {
        // Nhánh true: phép instanceof đã thành công.
        System.out.println(text.toUpperCase());
    } else {
        // Nhánh false: không có bảo đảm value là String.
        // System.out.println(text); // LỖI biên dịch.
    }

    // Sau cả câu if-else, hai nhánh có thể cùng đi tới đây.
    // System.out.println(text); // LỖI biên dịch.
}
~~~

Trong nhánh `true`, Java chắc chắn biết `value` là `String`, do đó `text` dùng được. Trong nhánh `false`, phép kiểm tra không khớp, nên `text` không có trong phạm vi hợp lệ.

**Bên ngoài một `if` thông thường cũng không tự động dùng được `text`**, bởi việc chương trình đi đến vị trí đó không chứng minh được điều kiện đã đúng:

~~~java
static void printIfString(Object value) {
    if (value instanceof String text) {
        System.out.println("Đã nhận chuỗi: " + text);
    }

    // Sai: nếu value không phải String thì luồng chạy vẫn tới đây.
    // System.out.println(text.length());
}
~~~

Có thể hình dung:

~~~text
                    value instanceof String text
                             /       \
                         true         false
                          |             |
                     text hợp lệ    text không có
                          \             /
                           \           /
                        Sau if thông thường
                     không chắc text đã khớp
~~~

Java dựa trên **luồng điều khiển thực tế**, không dựa vào việc biến được viết “trước” hay “sau” theo thứ tự dòng.

### 2.1. Bảng định hướng nhanh

| Vị trí sử dụng `text` | Có hợp lệ? | Lý do |
|---|---|---|
| Trong nhánh `if (value instanceof String text)` | **Có** | Điều kiện đúng nghĩa là pattern đã khớp |
| Trong `else` của cùng phép kiểm tra | **Không** | `else` chỉ chạy khi pattern không khớp |
| Sau một `if` thông thường, không có nhánh thoát | **Không** | Có đường đi qua điều kiện sai |
| Vế phải của `value instanceof String text && ...` | **Có** | `&&` chỉ đánh giá vế phải nếu vế trái đúng |
| Vế phải của `value instanceof String text || ...` | **Không** | `||` chỉ đánh giá vế phải nếu vế trái sai |
| Sau `if (!(value instanceof String text)) return;` | **Có** | Tới được dòng sau nghĩa là nhánh không khớp đã thoát |
| Trong nhánh `if (!(value instanceof String text))` | **Không** | Nhánh này chạy khi pattern không khớp |

## 3. Tại sao `&&` dùng được biến pattern?

Toán tử logic `&&` (*conditional AND*) đánh giá từ trái sang phải và **ngừng ngay khi gặp `false`** (*short-circuit evaluation*).

Ví dụ:

~~~java
static boolean isLongText(Object value) {
    return value instanceof String text && text.length() >= 10;
}
~~~

Đây là mã hợp lệ trong Java 17:

1. Java đánh giá `value instanceof String text`.
2. Nếu kết quả là `false`, toàn bộ biểu thức `&&` là `false`; `text.length()` **không được thực hiện**.
3. Nếu kết quả là `true`, `text` đã được liên kết với một `String`; Java mới đánh giá `text.length() >= 10`.

Sơ đồ:

~~~text
value instanceof String text
      |
      +--- false ------> kết quả false
      |
      +--- true
             |
             v
      text.length() >= 10  (text dùng được)
             |
             v
         true / false
~~~

Ta có thể kết hợp nhiều điều kiện:

~~~java
static boolean isUsefulText(Object value) {
    return value instanceof String text
            && !text.isBlank()
            && text.length() <= 100;
}
~~~

Với điều kiện trên:

- `value = "Java 17"`: hợp lệ, kết quả `true`.
- `value = "   "`: là `String` nhưng rỗng theo `isBlank()`, kết quả `false`.
- `value = 17`: không phải `String`, dừng ngay ở phép `instanceof`, kết quả `false`.
- `value = null`: `instanceof` trả về `false`, không thực hiện `text.isBlank()` hay `text.length()`.

Với kiểm tra kiểu như trên, thêm `value != null` trước `instanceof` thường không cần thiết, bởi `null instanceof String` vốn trả về `false`.

### 3.1. Vị trí của phép kiểm tra rất quan trọng

Cách viết đúng:

~~~java
if (value instanceof String text && text.startsWith("J")) {
    System.out.println(text);
}
~~~

Cách viết sau gây lỗi:

~~~java
// SAI: text bị dùng trước khi pattern khai báo và khớp.
// if (text.startsWith("J") && value instanceof String text) {
//     System.out.println(text);
// }
~~~

`&&` không hoán đổi thứ tự hai vế; việc vế trái được đánh giá trước là điều kiện giúp vế phải có thể dùng biến.

### 3.2. Có thể kết hợp `&&` với `||` ở bên trong phần đã an toàn

Không phải mọi lần xuất hiện `||` đều làm mã sai. Quan trọng là **biến đã được chứng minh khớp trước khi đánh giá biểu thức có `||` hay chưa**.

Ví dụ hợp lệ:

~~~java
static boolean needsReview(Object value) {
    return value instanceof String text
            && (text.isBlank() || text.length() > 20);
}
~~~

Khi Java đi tới biểu thức trong ngoặc, `value instanceof String text` chắc chắn đã trả về `true`. Vì thế **cả hai vế** của `(text.isBlank() || text.length() > 20)` đều được phép dùng `text`.

Ranh giới an toàn nằm ở phép `&&` phía ngoài.

## 4. Tại sao `||` thường gây lỗi với biến pattern?

`||` (*conditional OR*) cũng đánh giá từ trái sang phải, nhưng **chỉ chạy vế phải khi vế trái là `false`**.

Xét mã không hợp lệ:

~~~java
static boolean wrong(Object value) {
    // LỖI BIÊN DỊCH:
    // return value instanceof String text || text.isEmpty();
    return false;
}
~~~

Nếu `value instanceof String text` trả về `true`, toán tử `||` đã có kết quả `true` và **bỏ qua vế phải**. Nếu Java cần đánh giá `text.isEmpty()` thì nghĩa là phép `instanceof` vừa **trả về `false`**. Chính lúc này `text` lại không tồn tại hợp lệ!

Sơ đồ:

~~~text
value instanceof String text
      |
      +--- true -------> kết quả true
      |
      +--- false
             |
             v
       text.isEmpty()        <-- LỖI: text chưa khớp
~~~

Vì vậy, `||` **không thể được dùng để lấy một biến pattern từ vế trái khẳng định và dùng ngay ở vế phải**.

### 4.1. Ngay cả khi vế phải không dùng biến, bên trong `if` cũng có thể sai

Xét:

~~~java
static void wrongInside(Object value, boolean allowFallback) {
    // Ví dụ SAI nếu bỏ comment phần dùng text:
    if (value instanceof String text || allowFallback) {
        // System.out.println(text.length()); // LỖI.
        System.out.println("Một điều kiện đã đúng");
    }
}
~~~

Vì sao `text` không dùng được trong thân `if`?

- Trường hợp A: `value` là `String`. Vế trái đúng, `text` có giá trị.
- Trường hợp B: `value` không phải `String` nhưng `allowFallback` đúng. Cả biểu thức `||` vẫn đúng, **mặc dù `text` chưa hề khớp**.

Do có trường hợp B, Java không cho phép dùng `text` trong nhánh `if` đó.

**Phân biệt hai lỗi**:

| Mẫu mã | Vị trí lỗi | Nguyên nhân |
|---|---|---|
| `value instanceof String text || text.isBlank()` | Vế phải `||` | Vế phải chạy khi pattern đã thất bại |
| `if (value instanceof String text || flag) { use(text); }` | Thân `if` | Điều kiện đúng chưa đủ chứng minh pattern đã khớp |

### 4.2. Cách sửa phổ biến: dùng `&&` nếu cả hai điều kiện phải đúng

Nếu mục tiêu là “đối tượng phải là `String` và nội dung không rỗng”, hãy viết:

~~~java
static boolean hasContent(Object value) {
    return value instanceof String text && !text.isBlank();
}
~~~

Đây là trường hợp cần **đồng thời** thỏa hai điều kiện, nên dùng `&&`.

### 4.3. Cách sửa khi thật sự cần phép OR

Giả sử quy tắc là “chấp nhận giá trị nếu nó là chuỗi **hoặc** được phép dự phòng”:

~~~java
static boolean shouldProcess(Object value, boolean allowFallback) {
    return value instanceof String || allowFallback;
}
~~~

Ta chỉ cần biết giá trị logic, nên không cần khai báo biến pattern.

Nếu còn phải xử lý `String` riêng khi nó thật sự xuất hiện, hãy tách hai nhánh:

~~~java
static void process(Object value, boolean allowFallback) {
    if (value instanceof String text) {
        System.out.println("Chuỗi: " + text.strip());
    } else if (allowFallback) {
        System.out.println("Xử lý dự phòng");
    } else {
        System.out.println("Bỏ qua");
    }
}
~~~

Cách này thể hiện đúng hai tình huống: chỉ nhánh `String` có biến `text`.

## 5. Ngoại lệ quan trọng: dùng `||` hợp lệ sau phủ định `!`

`||` không phải lúc nào cũng xung đột với pattern variable. Một mẫu thường dùng là:

~~~java
static boolean isValidUsername(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return false;
    }

    return text.length() >= 3;
}
~~~

Mã này **hợp lệ**. Hãy phân tích:

- `value instanceof String text` đúng ⇒ phủ định `!(...)` là `false` ⇒ `||` cần đánh giá vế phải. Lúc này `text` chắc chắn đã khớp.
- `value instanceof String text` sai ⇒ phủ định là `true` ⇒ `||` dừng ngay, **không gọi `text.isBlank()`**.
- Nếu toàn bộ `if` đúng, hàm trả về `false`.
- Nếu chương trình tới `return text.length() >= 3;`, toàn bộ điều kiện `if` vừa sai. Điều đó chỉ có thể xảy ra khi `text` đã khớp và không rỗng.

Đây là cơ chế **guard clause** (điều kiện loại bỏ sớm): loại bỏ các đầu vào không hợp lệ rồi tiếp tục làm việc với biến đã được xác thực.

Diễn tiến:

~~~text
!(value instanceof String text)
            |
      +-----+-----+
      |           |
     true        false
      |           |
      v           v
 OR dừng      text.isBlank()
 (trả false       |
  từ hàm)     +---+---+
              |       |
             true    false
              |       |
              v       v
         trả false   đi tiếp
                         |
                         v
                   dùng text an toàn
~~~

**Đừng đảo sai phép phủ định.** Đoạn sau không hợp lệ:

~~~java
// SAI: vế phải chỉ chạy khi !(instanceof) là true,
// tức là khi pattern chưa khớp.
//
// if (!(value instanceof String text) && text.isBlank()) {
//     ...
// }
~~~

Quy tắc đơn giản là xét **điều kiện để vế phải được chạy**, chứ không chỉ nhìn xem biểu thức chứa `&&` hay `||`.

## 6. Khi nào dùng được biến sau câu lệnh `if`?

Đây là phần quan trọng nhất khi áp dụng flow scoping trong chương trình thực tế.

### 6.1. Sau một `if` thông thường: không thể mặc định dùng

~~~java
static int lengthOrZero(Object value) {
    if (value instanceof String text) {
        System.out.println("Đây là chuỗi");
    }

    // Sai: value có thể là Integer hoặc null.
    // return text.length();

    return 0;
}
~~~

Tại dòng sau `if`, Java không biết nhánh `true` có được thực hiện hay không.

### 6.2. Sau `if` phủ định có `return`: dùng được

~~~java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }

    // Nếu chạy đến đây, nhánh không khớp đã thoát khỏi hàm.
    return text.length();
}
~~~

Cơ chế:

1. Không phải `String` ⇒ điều kiện `if` đúng ⇒ thực hiện `return 0`.
2. Là `String` ⇒ điều kiện `if` sai ⇒ bỏ qua `return 0`.
3. Mọi đường chạy **có thể đến dòng cuối** đều bảo đảm `text` đã khớp.

Do đó, biến pattern có thể xuất hiện **sau dấu ngoặc đóng của `if`**, dù nó được khai báo trong điều kiện.

### 6.3. Sau `if` phủ định có `throw`: dùng được

~~~java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException(
                "Giá trị phải có kiểu String");
    }

    return text.strip();
}
~~~

`throw` cũng khiến nhánh không khớp không thể tiếp tục đến câu lệnh sau. Vì vậy, `text` được bảo đảm đã khớp trên đường đi tiếp.

Mẫu này phù hợp cho việc kiểm tra đối số ở đầu phương thức:

~~~java
static void saveIdentifier(Object input) {
    if (!(input instanceof String identifier)) {
        throw new IllegalArgumentException("Identifier phải là String");
    }

    if (identifier.isBlank()) {
        throw new IllegalArgumentException("Identifier không được rỗng");
    }

    System.out.println("Lưu: " + identifier.strip());
}
~~~

### 6.4. Sau `if` phủ định không thoát: không dùng được

So sánh:

~~~java
static void broken(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Không phải chuỗi");
    }

    // LỖI nếu bỏ comment:
    // System.out.println(text.length());
}
~~~

Vì nhánh không khớp chỉ in thông báo rồi vẫn đi tiếp, chương trình có thể đến dòng cuối mà `text` chưa khớp. Chỉ thêm dấu `!` **không đủ** để mở rộng phạm vi biến; phải xét cả đường chạy của chương trình.

### 6.5. Khi hàm còn cần nhánh `else`

Nếu muốn xử lý song song hai trường hợp, cách đơn giản và rõ ràng là đặt việc sử dụng biến trong nhánh đã khớp:

~~~java
static String display(Object value) {
    if (value instanceof String text) {
        return text.toUpperCase();
    } else {
        return "(không phải chuỗi)";
    }
}
~~~

Nếu muốn loại đầu vào không phù hợp rồi viết logic theo chiều thẳng, dùng guard clause phủ định như phần 6.2 hoặc 6.3.

## 7. Ví dụ tổng hợp chạy trên Java 17

Tạo file **`PatternFlowDemo.java`**:

~~~java
import java.util.Locale;

public class PatternFlowDemo {

    // Mẫu 1: && bảo đảm vế phải đã có biến pattern.
    static boolean hasShortContent(Object value) {
        return value instanceof String text
                && !text.isBlank()
                && text.length() <= 12;
    }

    // Mẫu 2: ! + return để dùng biến sau if.
    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "(không phải String)";
        }

        return text.strip().toUpperCase(Locale.ROOT);
    }

    // Mẫu 3: || hợp lệ vì điều kiện instanceof bị phủ định.
    static boolean validCode(Object value) {
        if (!(value instanceof String code) || code.isBlank()) {
            return false;
        }

        return code.length() >= 3;
    }

    // Mẫu 4: OR giữa hai tình huống, xử lý String ở nhánh riêng.
    static String describe(Object value, boolean fallback) {
        if (value instanceof String text) {
            return "String: " + text;
        } else if (fallback) {
            return "Giá trị dự phòng";
        } else {
            return "Không hỗ trợ";
        }
    }

    public static void main(String[] args) {
        System.out.println(hasShortContent("Java 17"));
        System.out.println(hasShortContent(17));
        System.out.println(normalize("  Java 17  "));
        System.out.println(normalize(null));
        System.out.println(validCode("ABC"));
        System.out.println(validCode("  "));
        System.out.println(describe("hello", false));
        System.out.println(describe(42, true));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17**:

~~~bash
javac --release 17 PatternFlowDemo.java
java PatternFlowDemo
~~~

Kết quả:

~~~text
true
false
JAVA 17
(không phải String)
true
false
String: hello
Giá trị dự phòng
~~~

Ba hàm đầu minh họa những vị trí Java có đủ căn cứ rằng pattern đã khớp. Hàm cuối minh họa việc dùng `||` ở cấp yêu cầu nghiệp vụ và tách riêng nhánh xử lý cần biến pattern.

## 8. Thêm các tình huống dễ nhầm

### 8.1. `else` của một điều kiện phủ định

Nếu điều kiện `if` được phủ định, nhánh `else` lại là nơi pattern chắc chắn khớp:

~~~java
static void print(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Không phải String");
    } else {
        System.out.println(text.length()); // Hợp lệ.
    }
}
~~~

Khi vào `else`, `!(instanceof)` là `false`, nên `instanceof` gốc phải là `true`.

### 8.2. Toán tử ba ngôi `? :`

Flow scoping cũng áp dụng cho biểu thức điều kiện:

~~~java
static String label(Object value) {
    return value instanceof String text
            ? text.toUpperCase()
            : "(khác)";
}
~~~

`text` hợp lệ trong nhánh `?` khi điều kiện đúng; nhánh `:` không được giả định `text` tồn tại.

### 8.3. Biến chỉ nằm trong phần biểu thức có đủ căn cứ

~~~java
static boolean longEnough(Object value) {
    boolean result = value instanceof String text
            && text.length() >= 5;

    // Không hợp lệ:
    // System.out.println(text);
    return result;
}
~~~

Biến `text` dùng được ở phần đánh giá của `&&`; việc biến logic `result` là `true` hoặc `false` không khiến biến pattern trở thành biến cục bộ dùng được ở mọi dòng sau đó.

### 8.4. Dùng nhiều điều kiện độc lập không tự tạo ra quan hệ an toàn

~~~java
static void check(Object value, boolean approved) {
    if (value instanceof String text || approved) {
        // Không thể dùng text ở đây.
        System.out.println("Được phép tiếp tục");
    }
}
~~~

Đừng suy luận “đã vào `if` nghĩa là pattern khớp”. Với `||`, **một vế khác** cũng có thể khiến điều kiện đúng.

### 8.5. `null`, `instanceof` và gọi phương thức

Với `value == null`, phép `value instanceof String text` trả về `false`; nó **không ném `NullPointerException`**. Vì vậy:

~~~java
static boolean nonBlankString(Object value) {
    return value instanceof String text && !text.isBlank();
}
~~~

là mẫu null-safe đối với `value`: vế phải chỉ chạy khi `value` thực sự là `String`.

### 8.6. Không nhầm biến pattern với field hay khai báo thường

~~~java
if (value instanceof String text) {
    System.out.println(text);
}
~~~

`text` không phải field tự động được tạo cho class, cũng không phải biến được khai báo độc lập tại đầu phương thức. Phạm vi của nó do **điều kiện khớp và cấu trúc điều khiển** xác định.

Nếu bạn cần giữ một giá trị sử dụng trên nhiều nhánh độc lập, hãy thiết kế luồng rõ ràng: trả về sớm cho trường hợp không phù hợp, hoặc gán vào một biến địa phương khác sau khi xác thực kiểu.

## 9. Cách tìm và sửa lỗi biên dịch liên quan `||`

Khi compiler không nhận ra biến pattern hoặc báo biến không nằm trong scope, hãy đọc biểu thức logic theo thứ tự đánh giá:

1. Tìm vị trí `instanceof Type variable`.
2. Xác định biến đang được sử dụng ở vế nào hoặc nhánh nào.
3. Hỏi: **Có đường chạy nào đi đến vị trí này khi `instanceof` đã trả về `false` không?**
4. Nếu **có**, vị trí đó không được bảo đảm có biến pattern.
5. Chọn cách sửa phù hợp với ý nghĩa nghiệp vụ: `&&`, nhánh `if/else` riêng, hoặc guard clause dùng `!` cùng `return`/`throw`.

Ví dụ chuyển từng bước.

**Mã sai:**

~~~java
// Sai: text được dùng ở vế phải ||.
// if (value instanceof String text || text.isBlank()) {
//     ...
// }
~~~

Nếu ý định là “chỉ xử lý chuỗi không rỗng”, dùng `&&`:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println("Chuỗi hợp lệ: " + text);
}
~~~

Nếu ý định là “từ chối khi không phải chuỗi **hoặc** là chuỗi rỗng”, dùng phủ định:

~~~java
static void validate(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Chuỗi không hợp lệ");
    }

    System.out.println("Chuỗi hợp lệ: " + text);
}
~~~

Nếu ý định là “chấp nhận chuỗi, hoặc cho phép dự phòng”, tách nhánh:

~~~java
static void handle(Object value, boolean fallback) {
    if (value instanceof String text) {
        System.out.println("Xử lý chuỗi: " + text);
    } else if (fallback) {
        System.out.println("Xử lý dự phòng");
    }
}
~~~

Ba cách sửa tương ứng với **ba yêu cầu logic khác nhau**; đừng thay `||` thành `&&` một cách máy móc nếu làm thay đổi ý nghĩa điều kiện.

## 10. Bảng tình huống: đúng hay sai?

Các dòng có nhãn “Sai” là đoạn minh họa lỗi biên dịch, không dùng chung vào một file để chạy.

| Đoạn điều kiện / cách dùng | Hợp lệ trong Java 17? | Giải thích |
|---|---|---|
| `if (o instanceof String s) { use(s); }` | Có | Nhánh `true` bảo đảm đã khớp |
| `if (o instanceof String s) {} else { use(s); }` | **Sai** | Nhánh `false` không có `s` |
| `if (o instanceof String s) {} use(s);` | **Sai** | Sau `if` có thể đi theo đường không khớp |
| `if (o instanceof String s && s.length() > 3) { use(s); }` | Có | Vế phải `&&` chỉ chạy sau khi khớp |
| `if (o instanceof String s || s.length() > 3) {}` | **Sai** | Vế phải `||` chạy khi chưa khớp |
| `if (o instanceof String s || flag) { use(s); }` | **Sai** | `flag` có thể làm điều kiện đúng khi chưa khớp |
| `if (!(o instanceof String s)) return; use(s);` | Có | Nhánh không khớp đã thoát |
| `if (!(o instanceof String s)) { use(s); }` | **Sai** | Thân `if` chạy khi chưa khớp |
| `if (!(o instanceof String s) || s.isBlank()) return; use(s);` | Có | `s` có trong vế phải `||` và ở đường đi tiếp |
| `if (o instanceof String s && (s.isBlank() || s.length() > 3)) {}` | Có | Phần `||` bên trong được bảo vệ bởi `&&` |

Trong bảng, `use(s)` là ký hiệu minh họa cho thao tác sử dụng biến như `System.out.println(s)`; bản thân `use` không phải API Java có sẵn.

## 11. Bài tập thực hành

### Bài 1: Biến có dùng được sau `if` không?

Cho đoạn:

~~~java
static void show(Object value) {
    if (value instanceof String text) {
        System.out.println("Chuỗi hợp lệ");
    }

    // System.out.println(text.length());
}
~~~

**Câu hỏi:** Nếu bỏ comment dòng cuối, có biên dịch được không? Vì sao?

**Đáp án:** Không. Dòng cuối vẫn chạy khi `value` là `Integer`, `null` hoặc kiểu khác; Java không chứng minh được `text` đã khớp.

### Bài 2: Sửa biểu thức `||` bị lỗi

~~~java
// Sai:
// if (value instanceof String text || text.length() > 5) {
//     System.out.println(text);
// }
~~~

**Yêu cầu:** Chỉ in những chuỗi dài hơn 5 ký tự.

**Đáp án:**

~~~java
if (value instanceof String text && text.length() > 5) {
    System.out.println(text);
}
~~~

Điều kiện nghiệp vụ đòi hỏi đồng thời “là `String`” và “dài hơn 5 ký tự”, nên `&&` là lựa chọn đúng.

### Bài 3: Dùng biến sau `if` mà không ép kiểu

Cho:

~~~java
static int getLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    // TODO: trả về độ dài text.
}
~~~

**Đáp án:**

~~~java
static int getLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    return text.length();
}
~~~

Vì đường không khớp đã `return`, dòng cuối chỉ có thể chạy khi `text` đã khớp.

### Bài 4: Đánh giá biểu thức khó hơn

~~~java
static boolean isAcceptable(Object value) {
    return value instanceof String text
            && (text.startsWith("A") || text.endsWith("Z"));
}
~~~

**Câu hỏi:** Có lỗi với `||` không?

**Đáp án:** Không. Toàn bộ biểu thức trong ngoặc chỉ được đánh giá khi `instanceof` ở vế trái của `&&` đã khớp, nên `text` hợp lệ trong cả hai điều kiện `startsWith` và `endsWith`.

### Bài 5: Sửa guard clause theo đúng mục đích

Yêu cầu: Từ chối nếu `value` không phải `String` **hoặc** là chuỗi chỉ có khoảng trắng; sau đó in chữ hoa của chuỗi.

**Đáp án tham khảo:**

~~~java
import java.util.Locale;

class Example {
    static void printNormalized(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Cần một chuỗi không rỗng");
        }

        System.out.println(text.strip().toUpperCase(Locale.ROOT));
    }
}
~~~

Đây là một trường hợp `||` hoàn toàn hợp lệ: biến `text` chỉ được dùng khi vế trái đã chứng minh phép `instanceof` thành công.

## 12. Ghi nhớ cách suy luận về flow scoping

Không nên học thuộc một quy tắc đơn giản như “`&&` luôn đúng, `||` luôn sai”. Quy tắc chính xác hơn là:

> **Một biến pattern chỉ khả dụng trên những đường điều khiển mà Java có thể chứng minh phép khớp mẫu đã thành công.**

Ba tình huống thường dùng nhất trong Java 17:

~~~java
// (1) Trong nhánh if khớp:
if (value instanceof String text) {
    System.out.println(text.length());
}

// (2) Trong vế phải của &&:
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}

// (3) Sau guard clause phủ định:
if (!(value instanceof String text)) {
    throw new IllegalArgumentException();
}
System.out.println(text.length());
~~~

Mẫu `||` đáng ghi nhớ:

~~~java
// SAI: vế phải chạy khi instanceof sai.
// value instanceof String text || text.isBlank()

// ĐÚNG: vế phải chạy khi instanceof đúng.
// !(value instanceof String text) || text.isBlank()
~~~

Khi đọc một điều kiện, hãy tự hỏi: **“Để chương trình đến được nơi sử dụng biến, liệu phép `instanceof` có bắt buộc phải trả về `true` không?”** Nếu câu trả lời là có, Java thường cho phép biến pattern xuất hiện tại vị trí đó.

## 13. Tài liệu tham khảo

- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): tính năng chính thức và mô hình *flow scoping*.
- [Oracle Java SE 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): cách viết và phạm vi biến pattern.
- [Java Language Specification 17 — `6.3 Scope of a Declaration`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): quy tắc scope và việc biểu thức giới thiệu biến pattern.
- [Java Language Specification 17 — `15.20.2 Type Comparison Operator instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): ngữ nghĩa của phép kiểm tra và pattern.

