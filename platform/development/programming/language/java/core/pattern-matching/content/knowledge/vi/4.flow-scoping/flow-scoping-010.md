# Lỗi dùng pattern variable ngoài flow scope trong Java 21

## 1. Vấn đề: biến đã xuất hiện trong pattern nhưng chưa chắc được phép dùng

Xét đoạn mã sau:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // Hợp lệ: text đã khớp
}

System.out.println(text); // LỖI BIÊN DỊCH
```

`String text` là **type pattern**. Biến `text` chỉ được sử dụng ở các điểm mà trình biên dịch có thể chứng minh pattern đã **khớp thành công**. Sau `if` không có `else`, điều kiện có thể đã sai, nên không thể mặc nhiên dùng `text`.

Quy tắc này gọi là **flow scoping**: phạm vi của *pattern variable* phụ thuộc vào **luồng điều khiển và kết quả điều kiện**, thay vì chỉ nhìn dấu ngoặc nhọn. Lỗi thường biểu hiện ở biên dịch, chẳng hạn `cannot find symbol` đối với biến pattern không ở trong scope; chẩn đoán chi tiết có thể thay đổi theo JDK và vị trí mã.

Bài tập trung vào cách xác định phạm vi, phát hiện lỗi, sửa lỗi và tránh làm mất tính đúng đắn khi refactor. Áp dụng cho Java 21 với **type pattern**, **record pattern** và **pattern matching for switch** chính thức; các ví dụ chạy được không cần bật preview.

## 2. Cơ sở để xác định flow scope

Theo [Java Language Specification 21, §6.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3), một pattern variable có thể được **introduced when true**, **introduced when false** hoặc được đưa vào phạm vi bởi một statement, tùy theo điều kiện và dạng câu lệnh.

Hãy đọc một biểu thức điều kiện như sau:

```java
obj instanceof String s
```

- Khi biểu thức là `true`, `obj` đã khớp `String` và biến `s` có giá trị để sử dụng.
- Khi biểu thức là `false`, không có cơ sở nói `s` đã khớp; `s` không được dùng trên nhánh đó.
- `null instanceof String s` trả về `false`, vì vậy pattern không giới thiệu biến `s` ở nhánh `false`.

Nếu phủ định:

```java
!(obj instanceof String s)
```

thì ý nghĩa đảo chiều:

- Biểu thức phủ định **đúng** khi pattern **không khớp**: không thể dùng `s` trong nhánh `true`.
- Biểu thức phủ định **sai** khi pattern **đã khớp**: có thể dùng `s` trong nhánh `false`.

Cần phân biệt ba thứ: **đã khai báo biến trong cú pháp**, **biến có giá trị khi match thành công**, và **vị trí Java cho phép tham chiếu tới biến**. Việc thấy chữ `s` trong cùng một phương thức hoặc cùng một khối ngoặc không đủ để kết luận nó đang ở scope.

### Bảng định hướng nhanh

| Ngữ cảnh | Có thể dùng `s`? | Lý do |
| --- | --- | --- |
| Vế phải `&&` trong `obj instanceof String s && s.length() > 2` | **Có** | Vế phải chỉ chạy nếu vế trái đúng |
| Nhánh `then` của `if (obj instanceof String s)` | **Có** | Nhánh chạy khi pattern khớp |
| Nhánh `else` của `if (obj instanceof String s)` | **Không** | Đây là đường đi không khớp |
| Vế phải `||` trong `obj instanceof String s || s.isEmpty()` | **Không** | Vế phải chỉ chạy khi vế trái sai |
| Vế phải `||` trong `!(obj instanceof String s) || s.isBlank()` | **Có** | Vế trái sai đồng nghĩa pattern đã khớp |
| Nhánh `else` của `if (!(obj instanceof String s))` | **Có** | Phủ định sai tức pattern khớp |
| Nhánh `then` của `if (!(obj instanceof String s))` | **Không** | Phủ định đúng tức pattern không khớp |
| Sau `if (obj instanceof String s)` thông thường | **Không** | Một đường đi đến sau `if` có thể không khớp |
| Sau guard `if (!(obj instanceof String s)) return;` | **Có** | Đường đi không khớp đã kết thúc |
| Trong `case String s when s.isBlank() ->` | **Có** | Guard và thân nhánh thuộc phạm vi `s` |

Bảng áp dụng cho cách viết minh họa, với mỗi biến `s` chỉ được khai báo trong biểu thức tương ứng. Những trường hợp có `return`, `throw`, `break`, hoặc điều kiện ghép khác cần phân tích đường đi cụ thể.

## 3. Lỗi 1 — Dùng biến trong nhánh `else` khi pattern ở điều kiện `if`

Mã sai:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (obj instanceof String s) {
    System.out.println("Length: " + s.length());
} else {
    System.out.println("Failed match: " + s); // LỖI
}
```

Nhánh `else` chạy khi `obj` không phải `String` (hoặc là `null`), vì vậy không tồn tại giá trị `s` được match. Không thể “tận dụng” tên `s` để đại diện cho `obj` ở nhánh thất bại.

Sửa:

```java
if (obj instanceof String s) {
    System.out.println("Length: " + s.length());
} else {
    System.out.println("Not a String: " + obj);
}
```

Nếu muốn sử dụng `s` trong nhánh thứ hai, phải **đảo điều kiện**:

```java
if (!(obj instanceof String s)) {
    System.out.println("Not a String");
} else {
    System.out.println("Length: " + s.length());
}
```

Trong đoạn đảo điều kiện, `s` ở `else` hợp lệ vì chỉ nhánh này bảo đảm pattern đã khớp.

## 4. Lỗi 2 — Dùng `s` sau `if` nhưng không loại bỏ đường đi thất bại

Mã sai:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (obj instanceof String s) {
    System.out.println("Found a string");
}
System.out.println(s.length()); // LỖI: obj có thể không là String
```

Vì nhánh thất bại vẫn đi tới dòng cuối, compiler không cho phép sử dụng `s`.

### Cách sửa A: Giữ xử lý bên trong nhánh hợp lệ

```java
if (obj instanceof String s) {
    System.out.println("Found a string");
    System.out.println(s.length());
}
```

### Cách sửa B: Guard clause bằng `return`

```java
static int lengthOrMinusOne(Object obj) {
    if (!(obj instanceof String s)) {
        return -1;
    }
    return s.length(); // Hợp lệ
}
```

Ở dòng `return s.length()`, nhánh pattern **không khớp** đã thoát khỏi phương thức. Java có thể chứng minh mọi đường đi còn lại đều có `s`.

### Cách sửa C: Guard clause bằng `throw`

```java
static int requireLength(Object obj) {
    if (!(obj instanceof String s)) {
        throw new IllegalArgumentException("Expected String");
    }
    return s.length();
}
```

`throw` cũng chặn luồng thất bại. Trái lại, một nhánh chỉ `System.out.println(...)` vẫn hoàn tất bình thường nên không đưa `s` vào scope của các câu lệnh phía sau.

### Cần hiểu cả trường hợp `if/else` có đường đi kết thúc

```java
static int requireTextLength(Object obj) {
    if (obj instanceof String s) {
        System.out.println("String found");
    } else {
        throw new IllegalArgumentException("Not a String");
    }
    return s.length(); // Hợp lệ: nhánh else không thể hoàn tất bình thường
}
```

Đây không phải ngoại lệ tùy ý của compiler: theo JLS, một `if/else` có thể đưa pattern variable ra các statement phía sau khi nhánh còn lại **không thể hoàn tất bình thường**. Hãy dựa vào đường đi có thể tới câu lệnh kế tiếp, không chỉ vị trí ngoặc nhọn.

## 5. Lỗi 3 — Đọc pattern variable ở vế phải `||` khi vế trái có thể thất bại

Mã sai:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (obj instanceof String s || s.isBlank()) {
    System.out.println("Matched");
}
```

Toán tử `||` có **short-circuit**: vế phải chỉ được đánh giá khi vế trái **false**. Nhưng `obj instanceof String s` là false khi `obj` không khớp `String`; chính lúc đó `s` không được liên kết. Đây là trường hợp dùng biến ngoài flow scope.

Sửa nếu cần kiểm tra “là chuỗi và không trống”:

```java
if (obj instanceof String s && !s.isBlank()) {
    System.out.println(s);
}
```

Sửa nếu cần phân loại chuỗi và đối tượng khác nhau:

```java
if (obj instanceof String s) {
    if (s.isBlank()) {
        System.out.println("Blank string");
    } else {
        System.out.println("Text: " + s);
    }
} else {
    System.out.println("Not a String");
}
```

### `||` không phải lúc nào cũng sai

Một trường hợp **hợp lệ** thường bị hiểu nhầm:

```java
static String nonBlankOrDefault(Object obj) {
    if (!(obj instanceof String s) || s.isBlank()) {
        return "missing";
    }
    return s.trim();
}
```

Ở biểu thức `!(obj instanceof String s) || s.isBlank()`, vế phải chỉ chạy khi phủ định là **false**, tức `obj instanceof String s` đã **true**. Vì vậy `s.isBlank()` là hợp lệ.

Sau `if`, chỉ đường đi làm **cả hai vế** false mới tiếp tục, nên `s` vẫn ở scope và chắc chắn là một `String` không blank. Cách phân tích này chính xác hơn quy tắc mẹo “`&&` luôn được, `||` luôn sai”.

## 6. Lỗi 4 — Đảo thứ tự các vế `&&` hoặc dùng `&` thay `&&`

Mã sai vì dùng biến **trước** khi chứng minh match:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (s.length() > 2 && obj instanceof String s) {
    System.out.println("OK");
}
```

Dù một phần điều kiện sau đó có `String s`, ở vị trí `s.length()` đầu tiên thì chưa có gì khai báo/liên kết `s` phù hợp.

Sửa: kiểm tra pattern trước, dùng biến sau.

```java
if (obj instanceof String s && s.length() > 2) {
    System.out.println("Long String: " + s);
}
```

Một lỗi khác là đổi nhầm `&&` thành `&`:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (obj instanceof String s & s.length() > 2) {
    System.out.println(s);
}
```

`&` với boolean đánh giá cả hai vế; nó không mang quy tắc **flow scope ở vế phải** như toán tử conditional-and `&&` trong ví dụ hợp lệ. Dù kết quả logic có vẻ giống nhau trong một số trường hợp, không thể thay `&&` bằng `&` để sử dụng pattern variable như trên.

**Quy tắc code review:** biểu thức nào sử dụng biến phải nằm ở đường đi mà phép match đã thành công, và toán tử phải thực sự bảo đảm đường đi đó.

## 7. Lỗi 5 — Hiểu sai dấu `!` và nhánh phù hợp

Lỗi:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (!(obj instanceof String s)) {
    System.out.println(s.length()); // LỖI: nhánh này nghĩa là KHÔNG khớp
}
```

Đừng hiểu cú pháp `String s` có trong dấu ngoặc là `s` tự động tồn tại ở mọi nhánh.

Cách sửa thứ nhất:

```java
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

Cách sửa thứ hai: dùng phủ định để xử lý lỗi, rồi tiếp tục trong đường đi thành công.

```java
static String normalized(Object obj) {
    if (!(obj instanceof String s)) {
        return "not a String";
    }
    return s.trim().toLowerCase();
}
```

Mấu chốt là **giá trị boolean của toàn bộ điều kiện**. Với `!(obj instanceof String s)`, `s` chắc chắn đã match khi điều kiện phủ định **false**.

## 8. Lỗi 6 — Dùng `s` sai nhánh trong toán tử `? :`

Toán tử ba ngôi cũng có quy tắc flow scope:

```java
static int length(Object obj) {
    return obj instanceof String s ? s.length() : 0;
}
```

Trong `? then : else`, khi điều kiện pattern là true thì nhánh sau `?` có `s`; nhánh sau `:` không có.

Mã sai:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
int result = obj instanceof String s
        ? 1
        : s.length();  // LỖI
```

Với phủ định thì có thể đưa biến vào **nhánh còn lại**:

```java
static int lengthWithNegation(Object obj) {
    return !(obj instanceof String s) ? -1 : s.length();
}
```

Đừng dùng biến sau toàn bộ toán tử chỉ vì đã xuất hiện ở một vế:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
int n = obj instanceof String s ? s.length() : 0;
System.out.println(s); // LỖI: sau toán tử không chắc đã match
```

Theo JLS, phép `? :` không tự đưa một pattern variable vào phạm vi toàn bộ biểu thức khi kết quả có thể đi theo hai nhánh.

## 9. Lỗi 7 — Mang biến từ nhánh `switch` sang nhánh khác hoặc ra ngoài `switch`

Java 21 hỗ trợ pattern matching for `switch`:

```java
static String describe(Object obj) {
    return switch (obj) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s -> "text: " + s;
        case Integer n -> "number: " + n;
        default -> "other";
    };
}
```

Trong nhánh `case String s when s.isBlank()`, `s` ở scope của **guard** `when` và nhánh tương ứng. Trong nhánh `case String s ->`, `s` thuộc nhánh ấy. Việc hai nhánh cùng dùng tên `s` không khiến chúng trở thành một biến chung; mỗi pattern là một khai báo riêng trong phạm vi phù hợp.

Mã sai:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
switch (obj) {
    case String s -> System.out.println(s);
    case Integer n -> System.out.println(s); // LỖI: s của nhánh khác
    default -> {}
}
System.out.println(s); // LỖI: s không thoát khỏi switch
```

Sửa bằng cách xử lý ở **đúng nhánh** hoặc trả về một **giá trị chung**:

```java
String result = switch (obj) {
    case null -> "null";
    case String s -> "string:" + s;
    case Integer n -> "integer:" + n;
    default -> "unknown";
};
System.out.println(result);
```

`result` là biến cục bộ được khai báo **bên ngoài** `switch`, nên có thể dùng sau đó. Pattern variable `s`, `n` chỉ có scope trong các nhánh thích hợp.

Đừng nhầm lỗi **dominance** (một nhánh `case` bị nhánh kiểu rộng đứng trước che khuất) với lỗi **flow scoping**. Cả hai đều có thể khiến code không biên dịch, nhưng lý do khác nhau.

## 10. Lỗi 8 — Dùng biến component của record pattern ngoài nhánh match

Với record patterns trong Java 21:

```java
record Point(int x, int y) {}
```

Đoạn sau giới thiệu hai pattern variable `x` và `y` **chỉ khi toàn bộ record pattern khớp**:

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y); // Hợp lệ
}
```

Không được dùng chúng ở đường đi có thể thất bại:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (obj instanceof Point(int x, int y)) {
    System.out.println("matched");
}
System.out.println(x + y); // LỖI: x, y ngoài flow scope
```

Nested record pattern cũng tuân theo nguyên tắc đó:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

static int sumX(Object obj) {
    if (!(obj instanceof Segment(
            Point(var x1, var y1),
            Point(var x2, var y2)))) {
        return -1;
    }
    return x1 + x2; // Hợp lệ sau guard clause
}
```

Với đoạn này, Java chỉ cho phép sử dụng các biến component khi **toàn bộ** `Segment(...)` lồng `Point(...)` match. Nếu component `start` hoặc `end` là `null`, nested record pattern `Point(...)` không khớp; nhánh `return -1` được chọn.

**Lưu ý về `record`:** các tên `x`, `y` trong `record Point(int x, int y)` là tên component. Khi viết `Point(int x, int y)` ở vị trí pattern, ta khai báo **biến pattern mới**. Dù trùng tên, phạm vi không giống field, accessor `p.x()`, hoặc biến cục bộ thường.

## 11. Lỗi 9 — Trùng tên biến cục bộ hoặc nhầm reuse với shadowing

Trong một block, tên pattern variable không được tùy ý **shadow** tên biến cục bộ đã ở scope. Ví dụ lỗi:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
String s = "existing";
if (obj instanceof String s) {  // LỖI: trùng tên biến đã ở scope
    System.out.println(s);
}
```

Sửa bằng tên rõ nghĩa:

```java
String existing = "existing";
if (obj instanceof String matched) {
    System.out.println(matched);
}
```

Tuy vậy, cũng không nên khái quát “tên pattern variable đã dùng là không bao giờ dùng lại được trong phương thức”. Khi một nhánh kết thúc và biến **không còn ở scope**, một khai báo mới tại vị trí hợp lệ có thể dùng lại cùng tên. Điều cần kiểm tra là **scope hiện hành** và quy tắc khai báo của Java, không chỉ tìm kiếm chuỗi trùng tên trong file.

## 12. Lỗi 10 — Tưởng `while` / `for` làm biến tồn tại sau vòng lặp

Một biến pattern được khớp bởi điều kiện vòng lặp có thể sử dụng **trong thân vòng lặp**, khi điều kiện đã được chứng minh true:

```java
while (value instanceof String s) {
    System.out.println(s.length());
    break;
}
```

Nhưng không thể tự động dùng `s` sau vòng lặp, vì nó có thể kết thúc mà không có match, hoặc do đường đi `break`.

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
while (value instanceof String s) {
    break;
}
System.out.println(s); // LỖI
```

Với `for` cơ bản, pattern variable do biểu thức điều kiện giới thiệu khi true có thể dùng trong **thân** và phần **cập nhật** của vòng lặp, miễn điều kiện vẫn chứng minh match. Ví dụ đọc mã:

```java
for (; value instanceof String s; ) {
    System.out.println(s.length()); // Hợp lệ
    break;
}
```

Trong các vòng lặp có phủ định, quy tắc về biến sau vòng lặp phụ thuộc cả vào điều kiện và khả năng **break**. JLS §6.3.2 có các quy tắc riêng; tránh kết luận dựa duy nhất vào việc có/không có `while`.

## 13. Chương trình Java 21 hoàn chỉnh để kiểm chứng

Lưu mã dưới đây vào tệp **`FlowScopeDemo.java`**. Tất cả kỹ thuật dùng tính năng **chính thức** của Java 21.

```java
public class FlowScopeDemo {
    record Point(int x, int y) {}

    static String classify(Object obj) {
        if (obj instanceof String s && !s.isBlank()) {
            return "text:" + s.length();
        }
        return "other";
    }

    static String label(Object obj) {
        if (!(obj instanceof String text)) {
            return "not-string";
        }
        return text.toUpperCase();
    }

    static String nonBlank(Object obj) {
        if (!(obj instanceof String s) || s.isBlank()) {
            return "missing";
        }
        return s.trim();
    }

    static int sum(Object obj) {
        if (obj instanceof Point(int x, int y)) {
            return x + y;
        }
        return -1;
    }

    static String viaSwitch(Object obj) {
        return switch (obj) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s -> "str:" + s.length();
            case Integer n -> "int:" + n;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("   "));
        System.out.println(label("flow"));
        System.out.println(label(42));
        System.out.println(nonBlank(" hi "));
        System.out.println(nonBlank("  "));
        System.out.println(sum(new Point(2, 5)));
        System.out.println(sum("x"));
        System.out.println(viaSwitch(null));
        System.out.println(viaSwitch("   "));
        System.out.println(viaSwitch(12));
    }
}
```

Biên dịch và chạy bằng JDK 21:

```bash
javac --release 21 FlowScopeDemo.java
java FlowScopeDemo
```

Kết quả stdout:

```text
text:4
other
FLOW
not-string
hi
missing
7
-1
null
blank
int:12
```

**Đối chiếu từng phương thức:**

- `classify`: `s` hợp lệ sau `instanceof` ở vế trái `&&`, trong nhánh `then`.
- `label`: `text` hợp lệ **sau** `if` phủ định có `return` loại đường đi không match.
- `nonBlank`: `s` hợp lệ bên phải `||` vì vế trái phủ định **false** nghĩa là đã match; `s` cũng hợp lệ sau guard clause.
- `sum`: `x`, `y` thuộc record pattern `Point(...)` và chỉ được dùng trong nhánh match.
- `viaSwitch`: `s` và `n` ở scope của guard/thân case tương ứng, không phải biến của toàn `switch`.

## 14. Chiến lược sửa lỗi trong mã thực tế

Khi IDE hoặc `javac` báo không tìm được tên pattern variable, hãy làm theo trình tự:

1. **Xác định điểm khai báo pattern:** ví dụ `obj instanceof String s` hay `case String s`.
2. **Xác định kết quả nào bảo đảm match:** `true` với `instanceof` trực tiếp; `false` với `!(instanceof ...)`.
3. **Lần theo đúng đường điều khiển:** kiểm tra nhánh `if/else`, thứ tự `&&`/`||`, nhánh `? :`, đường `return`/`throw`/`break`, và scope của từng `case`.
4. **Chọn cách sửa vừa đủ:** đưa lệnh vào nhánh match; đổi `||` sang `&&` khi đúng mục tiêu logic; đặt guard clause; hoặc trả về một giá trị từ `switch`.
5. **Đừng dùng cast để che lỗi logic:** ép kiểu `(String) obj` bên ngoài đường đi match có thể ném `ClassCastException`. Flow scoping giúp compiler chặn lỗi trước khi chạy.
6. **Đừng tự khai báo biến cùng tên để “vá scope”:** biến ngoài pattern có thể gây xung đột hoặc khiến mã dùng nhầm biến; ưu tiên đặt tên rõ nghĩa và giữ dữ liệu ở phạm vi chính xác.

### Trước và sau khi refactor một chuỗi kiểm tra

Trước, mã bị lỗi vì dùng biến ngoài flow scope:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (request instanceof String payload && !payload.isBlank()) {
    System.out.println("accepted");
}
send(payload); // LỖI: không chắc pattern đã khớp
```

Sau, giữ lời gọi trong đường đi match:

```java
if (request instanceof String payload && !payload.isBlank()) {
    System.out.println("accepted");
    send(payload);
}
```

Trong ví dụ này `send` và `request` là tên minh họa do ứng dụng cung cấp; đây là **đoạn trích**, không phải chương trình độc lập.

Hoặc dùng guard clause trong phương thức:

```java
static String acceptedText(Object request) {
    if (!(request instanceof String payload) || payload.isBlank()) {
        return "rejected";
    }
    return "accepted:" + payload;
}
```

Cách này thích hợp khi các bước xử lý phía sau đều cần một `payload` đã được chứng minh là `String` không blank.

## 15. Bài tập phát hiện lỗi và đáp án

### Bài 1: Biến được dùng ở những vị trí nào?

```java
if (obj instanceof String s && s.length() >= 3) {
    System.out.println(s);
} else {
    System.out.println(s); // ?
}
```

**Đáp án:** `s` hợp lệ ở vế phải `&&` và trong nhánh `then`. `s` **không hợp lệ ở `else`**, bởi có thể rơi vào nhánh này khi `obj` không phải `String` hoặc độ dài chưa đủ.

### Bài 2: Đảo điều kiện có làm mất `s` không?

```java
static String f(Object obj) {
    if (!(obj instanceof String s)) {
        return "bad";
    }
    return s.toLowerCase();
}
```

**Đáp án:** Không. `return s.toLowerCase()` hợp lệ; khi tới được đây thì nhánh phủ định không match đã kết thúc.

### Bài 3: Hai phép `||` khác nhau ở đâu?

```java
// A: Sai
if (obj instanceof String s || s.isBlank()) { }

// B: Đúng
if (!(obj instanceof String s) || s.isBlank()) { }
```

**Đáp án:** Ở A, vế phải chạy khi match thất bại, nên không có `s`. Ở B, vế phải chạy khi điều kiện phủ định false, tức pattern đã match, nên có `s`. **B hợp lệ về scope**, còn việc xử lý đối tượng không phải `String` là quyết định nghiệp vụ riêng.

### Bài 4: `switch` có cho dùng `s` sau khi kết thúc không?

```java
String result = switch (obj) {
    case String s -> s.toUpperCase();
    default -> "n/a";
};
System.out.println(result);
```

**Đáp án:** Có thể dùng `result`; không thể dùng trực tiếp `s` sau `switch`. Đây là hai khai báo khác nhau: `s` thuộc nhánh pattern, `result` thuộc block bên ngoài.

### Bài 5: Record pattern có thay đổi quy tắc không?

```java
record Point(int x, int y) {}

if (!(obj instanceof Point(int x, int y))) {
    return;
}
System.out.println(x + y);
```

**Đáp án:** Trong một phương thức trả về `void`, phần sau guard clause hợp lệ: `x` và `y` của record pattern đều đã được liên kết trên mọi đường đi còn tiếp tục.

## 16. Những điều cần ghi nhớ

- **Flow scope phụ thuộc đường đi đã chứng minh match.** Pattern variable không giống biến cục bộ được khai báo trực tiếp trong block.
- **`&&` và `||` phải đọc cùng chiều điều kiện.** Với `instanceof` trực tiếp, `&&` thường thuận tiện; với phủ định `!(instanceof ...)`, `||` có thể an toàn.
- **`return` và `throw` là công cụ sửa scope hữu ích** khi muốn tiếp tục làm việc với biến đã match ở phần còn lại của phương thức.
- **`case` và record pattern cũng chịu flow scoping:** mỗi pattern variable chỉ được dùng nơi match đã được bảo đảm.
- **Các đoạn cố ý lỗi biên dịch trong bài là ví dụ chẩn đoán**, không được ghép vào tệp `FlowScopeDemo.java`.

## 17. Tài liệu đối chiếu

- [Java Language Specification 21, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): quy tắc chính thức của flow scope, `&&`, `||`, `!`, `? :`, `if`, vòng lặp và `switch`.
- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): cách pattern khai báo biến và record pattern lồng nhau.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): giải thích pattern variable và kiểm tra kiểu với `instanceof`.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns chính thức trong Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): phạm vi biến trong pattern `case`, guard và quy tắc `switch`.
