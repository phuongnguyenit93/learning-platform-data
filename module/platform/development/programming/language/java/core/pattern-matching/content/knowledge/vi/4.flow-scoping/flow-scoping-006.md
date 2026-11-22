# Phạm vi biến trong else — Flow scoping của pattern variable

## 1. Câu hỏi cốt lõi: vì sao có lúc else dùng được biến mẫu, có lúc không?

Từ Java 16 (và ổn định trong Java 17+), có thể viết **type pattern** ngay trong `instanceof`:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`text` là **pattern variable**: nó chỉ có giá trị sau khi biểu thức `value instanceof String text` khớp. Khác với một biến cục bộ thông thường có phạm vi chủ yếu dựa trên dấu ngoặc khối, phạm vi biến mẫu còn phụ thuộc vào **đường đi của chương trình** (*flow scoping*).

Câu hỏi quan trọng đối với `else` không phải `biến được khai báo trong cùng câu lệnh if hay không?`, mà là:

> **Khi chương trình đi vào nhánh else, trình biên dịch có chứng minh chắc chắn mẫu đã khớp và biến mẫu đã được khởi tạo không?**

- Nếu **có**, biến mẫu nằm trong phạm vi (*in scope*) ở `else`.
- Nếu **không**, nhắc đến tên biến mẫu ở `else` sẽ bị lỗi biên dịch.

Chỉ cần đảo điều kiện bằng dấu `!` là phạm vi của biến mẫu có thể chuyển từ nhánh `if` sang nhánh `else`. Đây là trọng tâm của bài học.

## 2. Điều kiện dương: instanceof trực tiếp không đưa biến mẫu vào else

Xét ví dụ minh họa sau (đặt trong một phương thức Java 17+):

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());  // Hợp lệ: text là String
} else {
    System.out.println("Không phải String");
}
```

Luồng thực thi:

1. Nếu `value` thực sự là `String`, biểu thức `instanceof String text` trả về `true`, gán tham chiếu phù hợp cho `text` và chạy nhánh `if`.
2. Nếu `value` là một đối tượng khác hoặc `null`, biểu thức trả về `false`, **không có String nào được gán cho `text`**, và chạy nhánh `else`.

Vì nhánh `else` chỉ xảy ra khi phép khớp **thất bại**, mã sau là **cố ý sai**:

```java
static void invalid(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println(text.length()); // COMPILE ERROR: text không in scope
    }
}
```

Trình biên dịch phải ngăn việc đọc một biến mà nhánh đang chạy không bảo đảm đã được khởi tạo. Không có chuyện `text` tự nhận giá trị `null` trong `else`. Đây là **lỗi phạm vi biến tại compile time**, không phải `NullPointerException` tại runtime.

Chú ý thêm: nếu chính bạn khai báo một **biến khác** bên trong `else` thì đó là biến mới và tuân theo quy tắc phạm vi thông thường của biến cục bộ; nó không làm biến mẫu `text` từ nhánh `if` trở nên khả dụng.

## 3. Phủ định điều kiện: else mới là nơi mẫu chắc chắn khớp

Bây giờ đảo điều kiện:

```java
static String upper(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải String";
    } else {
        return text.toUpperCase();
    }
}
```

Trong biểu thức `!(value instanceof String text)`:

- Khi điều kiện **true**, phép `instanceof` ở trong dấu `!` là **false**, nên `text` **không** ở trong phạm vi của nhánh `if`.
- Khi điều kiện **false**, phép `instanceof` gốc chắc chắn **true**, nên `text` **đã khớp** và ở trong phạm vi của nhánh `else`.

Sơ đồ:

```text
value instanceof String text?
├── true  → text đã được gán
│           → !(...) = false
│           → đi vào else  → có thể dùng text
└── false → text chưa được gán
            → !(...) = true
            → đi vào if    → không thể dùng text
```

Điểm dễ nhầm: `else` **không cần** nhánh `if` có `return` hoặc `throw` để dùng được `text`. Chỉ riêng sự thật rằng **điều kiện phủ định là false** đã đủ chứng minh pattern match thành công. `return` trong ví dụ giúp phương thức trả kết quả, nhưng không tạo ra phạm vi bên trong `else`.

Ngược lại, đoạn sau cố ý không hợp lệ:

```java
static void invalidNegated(Object value) {
    if (!(value instanceof String text)) {
        System.out.println(text); // COMPILE ERROR: text không in scope ở nhánh if
    } else {
        System.out.println(text); // Hợp lệ
    }
}
```

## 4. Chương trình hoàn chỉnh: kiểm tra cả hai hướng

Tệp **`ElseFlowDemo.java`**, dùng Java 17 trở lên:

```java
public class ElseFlowDemo {

    static String direct(Object value) {
        if (value instanceof String text) {
            return "String length=" + text.length();
        } else {
            return "Not a String";
        }
    }

    static String inverted(Object value) {
        if (!(value instanceof String text)) {
            return "Not a String";
        } else {
            return "Upper=" + text.toUpperCase();
        }
    }

    static String guarded(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "Rejected";
        } else {
            return "Trim=" + text.trim();
        }
    }

    static String chained(Object value) {
        if (!(value instanceof String text)) {
            return "Other";
        } else if (text.isEmpty()) {
            return "Empty";
        } else {
            return "Text=" + text;
        }
    }

    static int lengthOrThrow(Object value) {
        if (value instanceof String text) {
            // Có thể tiếp tục thực thi nhánh này.
        } else {
            throw new IllegalArgumentException("Need String");
        }

        // Mọi đường đi đến đây đều đã khớp String text.
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println(direct("Java"));
        System.out.println(direct(42));
        System.out.println(inverted("java"));
        System.out.println(inverted(null));
        System.out.println(guarded("  Java  "));
        System.out.println(guarded("  "));
        System.out.println(guarded(42));
        System.out.println(chained(""));
        System.out.println(chained("Hi"));
        System.out.println(chained(42));
        System.out.println(lengthOrThrow("Java"));
    }
}
```

Biên dịch và chạy:

```bash
javac ElseFlowDemo.java
java ElseFlowDemo
```

Kết quả:

```text
String length=4
Not a String
Upper=JAVA
Not a String
Trim=Java
Rejected
Rejected
Empty
Text=Hi
Other
4
```

Hai phương thức `direct` và `inverted` chứng minh sự đổi chỗ phạm vi giữa `if` và `else`. `guarded` thể hiện kết hợp `!` với `||`, `chained` thể hiện `else if` lồng nhau, còn `lengthOrThrow` là trường hợp biến mẫu tồn tại **sau cả câu lệnh if-else** do nhánh không khớp luôn kết thúc bằng `throw`.

Các phần dưới giải thích vì sao những trường hợp này hợp lệ.

## 5. Quy tắc chuẩn của Java cho nhánh if/else

Java Language Specification (JLS) mô tả trạng thái **definitely matched**: tại một vị trí trong mã, trình biên dịch chứng minh biến mẫu chắc chắn đã được khởi tạo vì pattern đã khớp.

Với biểu thức điều kiện `e` trong `if (e) S else T`:

- Biến mẫu được `e` giới thiệu **khi true** nằm trong phạm vi ở nhánh `S` (`if`).
- Biến mẫu được `e` giới thiệu **khi false** nằm trong phạm vi ở nhánh `T` (`else`).

Cụm từ `được giới thiệu khi false` không mâu thuẫn với pattern matching. Thông thường `value instanceof String s` chỉ giới thiệu `s` **khi true**. Nhưng `!(value instanceof String s)` đảo kết quả boolean, nên nó giới thiệu `s` **khi false**.

| Điều kiện của if | Biến `s` trong nhánh if | Biến `s` trong nhánh else | Giải thích |
| --- | --- | --- | --- |
| `value instanceof String s` | Có | Không | if true ⇒ mẫu khớp |
| `!(value instanceof String s)` | Không | Có | if false ⇒ mẫu gốc khớp |
| `value instanceof String s && !s.isBlank()` | Có | Không | if false có thể do không phải String |
| `!(value instanceof String s) || s.isBlank()` | Không | Có | if false ⇒ là String và không blank |
| `value instanceof String s || otherCondition` | Không bảo đảm | Không | if true có thể do vế phải; if false thì mẫu không khớp |

Bảng nói về **phạm vi trong hai nhánh của if-else**. Muốn dùng `s` sau toàn bộ câu lệnh, còn phải xét đường đi nào có thể hoàn tất bình thường; xem mục 8.

## 6. Vai trò của &&: điều kiện đúng bảo đảm mẫu khớp, điều kiện sai thì chưa chắc

Phần này giúp tránh suy luận sai về `else`. Với phép AND ngắn mạch:

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("Đủ dài: " + text);
} else {
    System.out.println("Không đủ điều kiện");
}
```

Biểu thức `text.length() >= 4` chỉ được đánh giá nếu phép `instanceof` đã khớp. Bởi vậy, `text` hợp lệ ở **vế phải của `&&`** và trong nhánh `if`.

Nhưng vì sao **else không được dùng `text`**? Điều kiện AND bằng false trong **ít nhất hai trường hợp**:

1. `value` **không phải String**, nên phép `instanceof` false và `text` không được gán.
2. `value` là String nhưng độ dài nhỏ hơn 4, nên `text` đã được gán nhưng toàn biểu thức AND vẫn false.

Trình biên dịch không thể khẳng định trường hợp nào đã xảy ra tại lối vào `else`. Do đó:

```java
static void invalidAnd(Object value) {
    if (value instanceof String text && text.length() >= 4) {
        System.out.println(text);
    } else {
        System.out.println(text); // COMPILE ERROR
    }
}
```

**Quy tắc thực hành:** `instanceof T t && kiểmTraThêm(t)` cho phép dùng `t` ở nhánh **if**, nhưng không tự cho phép dùng `t` ở `else`.

## 7. Vai trò của || kết hợp phủ định: else được bảo đảm khớp

So sánh đoạn hợp lệ:

```java
static String normalize(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "Rejected";
    } else {
        return text.strip();
    }
}
```

Đọc điều kiện theo nghĩa: **không phải String HOẶC là String nhưng chỉ chứa khoảng trắng**. Trong biểu thức OR ngắn mạch:

1. Nếu `value` không phải String, vế trái `!(... instanceof String text)` là true; vế phải không chạy, và `if` được chọn.
2. Nếu `value` là String, vế trái là false; **`text` đã khớp**, nên vế phải `text.isBlank()` được phép truy cập.
3. Chỉ khi **cả hai vế false** mới vào `else`. Điều đó chứng minh `value` là String và `!text.isBlank()` đúng. Vì vậy `text` hợp lệ trong `else`.

Sơ đồ logic:

```text
!(value instanceof String text) || text.isBlank()
       A                      ||       B
- A = true  → không khớp String → vào if
- A = false → đã khớp String    → mới xét B
   - B = true  → chuỗi trắng    → vào if
   - B = false → chuỗi có chữ   → vào else (text chắc chắn có giá trị)
```

Ngược lại, viết `value instanceof String text || fallback` **không đưa `text` vào nhánh if**, vì toàn biểu thức có thể true **chỉ do `fallback` true** khi `value` không phải String.

Một bẫy tương tự là dùng `&&` sau điều kiện phủ định:

```java
static void invalidNegatedAnd(Object value, boolean flag) {
    if (!(value instanceof String text) && flag) {
        System.out.println("Nhánh if");
    } else {
        System.out.println(text); // COMPILE ERROR
    }
}
```

Điều kiện AND có thể false vì `flag` false **dù `value` không phải String**. Vậy việc đi vào else không chứng minh `text` đã khớp.

## 8. else if là một if nằm trong else: phạm vi truyền vào như thế nào?

Trong Java, cú pháp `else if (...)` về mặt cấu trúc là một **câu lệnh if khác nằm trong nhánh else** của câu lệnh ngoài. Vì thế cần xét điều kiện của `if` bên ngoài trước.

### 8.1. Chuỗi điều kiện dương: biến của nhánh trước không đi sang nhánh sau

```java
static String classify(Object value) {
    if (value instanceof String text) {
        return "String: " + text;
    } else if (value instanceof Integer number) {
        return "Integer: " + number;
    } else {
        return "Other";
    }
}
```

Đây là **phương thức minh họa**: đặt trong một class Java 17+ để gọi. `text` chỉ dùng được ở nhánh String; `number` chỉ dùng được ở nhánh Integer. Nhánh `else` cuối không có bảo đảm về một trong hai kiểu nên **không có cả hai biến mẫu**.

Không thể đặt `text.length()` trong điều kiện `else if` ở đây: đi vào đó nghĩa là `value instanceof String text` đã **false**.

### 8.2. Chuỗi điều kiện phủ định: biến vẫn hợp lệ trong else if và else phía trong

```java
static String inspect(Object value) {
    if (!(value instanceof String text)) {
        return "Other";
    } else if (text.isEmpty()) {
        return "Empty";
    } else if (text.length() < 4) {
        return "Short: " + text;
    } else {
        return "Long: " + text;
    }
}
```

Đường đi vào toàn bộ nhánh `else` của câu lệnh ngoài đã bảo đảm `text` là String. Vì vậy `text` có thể dùng trong:

- Điều kiện của `else if` đầu tiên.
- Điều kiện của `else if` thứ hai.
- Thân các nhánh `else if` tương ứng.
- Nhánh `else` cuối của chuỗi lồng bên trong.

Đây **không phải** quyền truy cập biến mẫu `mọi nơi trong method`. Chỉ những vị trí thuộc đường đi mà trình biên dịch chứng minh mẫu khớp mới được phép truy cập.

## 9. Sau if-else: khi nào phạm vi của biến tiếp tục?

**Bên trong else** và **sau toàn bộ if-else** là hai vấn đề khác nhau. Với một điều kiện đơn thuần:

```java
static void invalidAfter(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println("Other");
    }
    System.out.println(text); // COMPILE ERROR
}
```

Cả hai nhánh có thể kết thúc bình thường; đi đến câu lệnh cuối không chứng minh nhánh nào vừa chạy. Vì vậy `text` không được dùng sau `if-else`.

Tuy nhiên, Java còn phân tích **nhánh nào không thể hoàn tất bình thường** (*cannot complete normally*), chẳng hạn do `return` hoặc `throw`:

```java
static int lengthOrThrow(Object value) {
    if (value instanceof String text) {
        // Đường đi khớp có thể tiếp tục.
    } else {
        throw new IllegalArgumentException("Need String");
    }
    return text.length(); // HỢP LỆ: đường đi không khớp đã throw
}
```

Ở đây biến `text` được giới thiệu khi điều kiện **true**; nhánh `if` có thể tiếp tục bình thường, nhánh `else` **không thể**. Nếu chương trình tới `return text.length()`, trường hợp duy nhất còn lại là mẫu đã khớp.

Cách viết guard clause cũng hợp lệ:

```java
static int safeLength(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // HỢP LỆ: mọi đường đi tiếp tục đều là String
}
```

Cần tránh suy luận máy móc `cứ có return ở đâu đó thì biến ra ngoài scope`. Trình biên dịch xét **đường đi đến điểm sử dụng**, bao gồm biểu thức true/false và khả năng hoàn tất bình thường của từng nhánh. Một nhánh có lối đi tiếp tục mà chưa khớp là đủ để biến mẫu không khả dụng sau câu lệnh.

### Bảng quyết định nhanh

| Mẫu mã | Trong else | Sau toàn bộ if-else |
| --- | --- | --- |
| `if (o instanceof String s) { ... } else { ... }`; cả hai nhánh kết thúc bình thường | `s` không ở scope | Không ở scope |
| `if (!(o instanceof String s)) { ... } else { ... }`; cả hai nhánh kết thúc bình thường | `s` ở scope | Không ở scope |
| `if (o instanceof String s) { ... } else { throw ...; }` | `s` không ở scope | `s` ở scope nếu nhánh khớp có thể tiếp tục |
| `if (!(o instanceof String s)) { return; } else { ... }` | `s` ở scope | `s` có thể ở scope khi nhánh else tiếp tục bình thường |

Ở dòng cuối, phương thức phải có kiểu trả về phù hợp với câu lệnh `return` và nhánh else. Nếu một nhánh cũng không thể hoàn tất bình thường thì các quy tắc cụ thể theo JLS tiếp tục áp dụng.

## 10. null có làm biến mẫu trong else thành null không?

Không. Với type pattern `String text` trong `instanceof`, **null không khớp**.

```java
static String render(Object value) {
    if (!(value instanceof String text)) {
        return "Not a String";
    } else {
        return "Value=" + text;
    }
}
```

- `render(null)` trả về `"Not a String"`: dấu `!` đảo kết quả `false` của `instanceof` thành `true`, nên vào nhánh if.
- `render("Hi")` trả về `"Value=Hi"`: điều kiện phủ định false, vào else và `text` chứa tham chiếu String thực tế.

Do đó trong **else của phép phủ định type pattern**, khi biến mẫu đang in scope, giá trị tham chiếu đã được so khớp theo điều kiện pattern; không cần cast thủ công. Tuy nhiên, không nên lấy kết luận này áp dụng chung cho **mọi loại pattern lồng trong record**: các quy tắc null-matching của deconstruction và component patterns có chi tiết riêng.

## 11. Java 21: cùng nguyên tắc với record pattern

Flow scoping không chỉ áp dụng với type pattern đơn. Từ **Java 21**, record pattern có thể trích xuất component và các biến mẫu cũng chịu phân tích luồng điều khiển.

Tệp **`ElseRecordDemo.java`**:

```java
public class ElseRecordDemo {
    record Point(int x, int y) {}

    static String describe(Object value) {
        if (!(value instanceof Point(int x, int y))) {
            return "Other";
        } else {
            return "Point=" + x + "," + y;
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(null));
    }
}
```

Chạy bằng JDK 21+:

```bash
javac ElseRecordDemo.java
java ElseRecordDemo
```

Kết quả:

```text
Point=2,3
Other
```

Biến `x` và `y` được trích xuất **chỉ khi record pattern `Point(int x, int y)` khớp**. Nếu điều kiện phủ định false thì mẫu gốc true; do đó cả hai biến nằm trong phạm vi của `else`. Khi `value` là null, mẫu ngoài `Point(...)` không khớp nên vào nhánh if.

**Giới hạn phiên bản:** `instanceof String s` đã là tính năng chính thức từ Java 16, dùng bình thường trên Java 17. Record patterns là tính năng chính thức từ Java 21. Mã `ElseRecordDemo` không biên dịch bằng Java 17 như một tính năng chính thức.

## 12. Lỗi hay gặp và cách sửa

| Lỗi hoặc ngộ nhận | Nguyên nhân | Cách làm đúng |
| --- | --- | --- |
| Dùng `s` trong else của `if (o instanceof String s)` | Else ứng với phép khớp thất bại | Dùng đối tượng gốc hoặc phân nhánh khác; chỉ dùng `s` khi chắc chắn khớp |
| Tưởng `!(o instanceof String s)` cho dùng `s` trong nhánh if | Đảo true/false nhưng không làm mẫu khớp | Dùng `s` ở else hoặc sau guard clause có return/throw |
| Dùng `s` trong else của `o instanceof String s && kiểmTra(s)` | false có thể do `instanceof` thất bại | Tách thành các nhánh riêng hoặc dùng biểu thức phủ định kết hợp `||` phù hợp |
| Dùng `s` trong nhánh then của `o instanceof String s || fallback` | true có thể chỉ do fallback | Tách điều kiện; đừng giả định mọi đường đi đã gán `s` |
| Dùng `s` sau if-else dù cả hai nhánh đều tiếp tục | Không thể biết đường đi vừa qua có khớp | Cho nhánh không khớp kết thúc hẳn, hoặc chỉ dùng `s` trong nhánh được bảo đảm |
| Cho rằng `else if` luôn nhìn thấy mọi biến từ điều kiện trước | Mỗi `else if` là if lồng trong else, phụ thuộc luồng vào | Xét điều kiện của if bên ngoài; với `!(... instanceof T t)`, biến có thể dùng trong else-if |
| Tưởng null làm biến mẫu có giá trị null trong else | Với `instanceof` type pattern, null không khớp | Xử lý null qua nhánh không khớp; không dereference biến mẫu khi chưa khớp |

Trong code review, một cách đơn giản để tự kiểm tra là **liệt kê mọi cách khiến điều kiện if có thể là false**. Nếu có dù chỉ một cách mà mẫu chưa khớp, thì không được sử dụng biến mẫu trong else.

## 13. Tự kiểm tra

**Câu 1.** Đoạn nào biên dịch được?

```java
// (A)
if (obj instanceof String s) {
    use(s);
} else {
    use(s); // ?
}

// (B)
if (!(obj instanceof String s)) {
    fallback();
} else {
    use(s); // ?
}
```

Giả sử `obj` là `Object`, và `use`/`fallback` là phương thức đã khai báo phù hợp. **Đáp án:** (A) lỗi biên dịch vì else chỉ chạy sau khi mẫu không khớp; (B) hợp lệ vì else chỉ chạy khi mẫu gốc đã khớp. Các đoạn là **mã minh họa, không phải chương trình độc lập**.

**Câu 2.** Vì sao đoạn này lỗi ở else?

```java
if (obj instanceof String s && s.length() > 5) {
    System.out.println("long");
} else {
    System.out.println(s); // ?
}
```

**Đáp án:** Đường đi vào else có thể là `obj` không phải String (mẫu không khớp) hoặc String có độ dài ≤ 5 (mẫu đã khớp). Vì không chắc chắn khớp trên **mọi** đường đi, `s` không ở phạm vi trong else.

**Câu 3.** Vì sao đoạn sau có thể dùng `s` trong else?

```java
if (!(obj instanceof String s) || s.isEmpty()) {
    System.out.println("missing or empty");
} else {
    System.out.println(s.toUpperCase());
}
```

**Đáp án:** Để điều kiện OR là false, **cả hai vế phải false**: `obj` chắc chắn là String và `s.isEmpty()` false. Vì thế `s` đã được gán khi vào else.

## 14. Tài liệu chuẩn

Đối với Java 17/21, những quy tắc trên được quy định trong JLS:

- [JLS 21 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): khái niệm `definitely matched`, phạm vi biến mẫu.
- [JLS 21 §6.3.1.1–6.3.1.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1): cách `&&`, `||` và `!` giới thiệu biến khi true/false.
- [JLS 21 §6.3.2.2 — if Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.2): quy tắc biến mẫu trong nhánh if, else và sau if-else.
- [JLS 21 §15.20.2 — instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): điều kiện so khớp của `instanceof`.

**Kết luận:** Biến mẫu nằm trong `else` khi **điều kiện if là false đồng nghĩa pattern đã khớp**. Với `instanceof` trực tiếp thì thường không; với `!(... instanceof T t)` thì có. Khi kết hợp `&&`, `||`, `else if` hoặc tiếp tục sau if-else, hãy suy luận theo tất cả đường đi của chương trình và quy tắc *definitely matched*, không chỉ theo dấu ngoặc nhọn.
