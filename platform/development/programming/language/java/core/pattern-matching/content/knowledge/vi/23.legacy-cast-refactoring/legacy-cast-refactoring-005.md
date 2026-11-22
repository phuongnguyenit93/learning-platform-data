# Refactor null check cùng type check trong Java Pattern Matching

Khi bảo trì Java cũ, một mẫu mã thường gặp là **kiểm tra `null`, kiểm tra kiểu bằng `instanceof`, rồi ép kiểu (cast) để dùng đối tượng**. Từ Java 16, *pattern matching for `instanceof`* giúp gộp kiểm tra kiểu và khai báo biến có kiểu, từ đó đơn giản hóa nhiều phép kiểm tra `null` dư thừa. Khi refactor, mục tiêu là **giữ nguyên hành vi với mọi đầu vào**, đặc biệt phân biệt giữa `null`, kiểu không phù hợp và đối tượng đúng kiểu nhưng nội dung không hợp lệ.

Bài học tập trung vào mã legacy có `if`, `instanceof` và cast. Ví dụ chính dùng **Java 17** (cũng chạy trên Java 21+); `instanceof` type pattern là tính năng chuẩn từ Java 16 (JEP 394), không cần bật preview.

## 1. Từ ba thao tác thành một phép kiểm tra

Mã legacy:

```java
Object input = "  Java  ";

if (input != null && input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip()); // Java
}
```

Mã refactor:

```java
if (input instanceof String text) {
    System.out.println(text.strip()); // Java
}
```

Cách hiểu `input instanceof String text`:

1. Kiểm tra giá trị `input` có phải một đối tượng `String` hay không.
2. Nếu thành công, tạo biến pattern `text` có kiểu tĩnh `String` và trỏ tới cùng đối tượng.
3. Biến `text` dùng được trong nhánh `if` khi trình biên dịch chứng minh pattern chắc chắn đã khớp.
4. Nếu không khớp, nhánh `if` không chạy; không cần thực hiện cast.

**Vì sao bỏ được `input != null`?** Theo ngữ nghĩa của `instanceof` trong Java, giá trị `null` **không khớp** type pattern. Biểu thức `null instanceof String text` cho kết quả `false`. Vì vậy:

```java
input != null && input instanceof String
```

và:

```java
input instanceof String text
```

cùng quyết định **có được vào nhánh hay không** khi mục tiêu đơn thuần là kiểm tra `String`. Phiên bản sau còn cung cấp biến `text` được kiểm tra kiểu sẵn.

**Giới hạn quan trọng:** tính tương đương này áp dụng khi kiểm tra `null` chỉ để bảo vệ kiểm tra kiểu/cast. Nếu mã cũ phân biệt riêng `null` để ghi log, trả lỗi khác hoặc ném exception khác, phải giữ nhánh đó khi refactor.

## 2. Bảng hành vi của instanceof với null

Xét `Object input` và điều kiện `input instanceof String text`:

| Giá trị của `input` | Kết quả `instanceof` | Nhánh đúng có chạy? |
| --- | --- | --- |
| `null` | `false` | Không |
| `"Java"` | `true` | Có, `text = "Java"` |
| `""` (chuỗi rỗng) | `true` | Có, `text = ""` |
| `"   "` (chỉ khoảng trắng) | `true` | Có, `text` chứa khoảng trắng |
| `Integer.valueOf(7)` | `false` | Không |

Kết quả **`instanceof` không đồng nghĩa với kiểm tra dữ liệu hợp lệ**. Một chuỗi rỗng vẫn là `String`; chỉ khi cần loại chuỗi rỗng hoặc blank mới bổ sung điều kiện riêng.

Những điều kiện thường gặp:

```java
input != null && input instanceof String  // Có thể thay bằng type pattern.
input instanceof String                    // false nếu input == null.
input instanceof String text              // false nếu input == null; có biến text khi khớp.
```

Không được nhầm với phép gọi `input.getClass()`, `input.toString()` hoặc cast rồi truy cập thuộc tính: các phép gọi phương thức trên `null` có thể ném `NullPointerException`, còn phép `instanceof` đơn lẻ thì không.

## 3. Refactor kiểu kiểm tra null + type + điều kiện nghiệp vụ

Một ví dụ legacy kiểm tra chuỗi có nội dung:

```java
static String legacyLabel(Object input) {
    if (input != null && input instanceof String) {
        String text = (String) input;
        if (!text.isBlank()) {
            return "text=" + text.strip();
        }
    }
    return "unavailable";
}
```

Phiên bản dùng pattern matching:

```java
static String modernLabel(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return "text=" + text.strip();
    }
    return "unavailable";
}
```

Ở phiên bản mới:

- `input instanceof String text` vừa kiểm tra kiểu vừa ràng buộc `text`.
- Toán tử `&&` **đánh giá ngắn mạch** (*short-circuit*): `!text.isBlank()` chỉ được gọi khi vế trái đúng, vì vậy `text` khác `null`.
- Điều kiện nghiệp vụ “không blank” giữ nguyên; mã mới không vô tình chấp nhận chuỗi `"   "`.
- `String.isBlank()` và `String.strip()` được hỗ trợ từ Java 11; ví dụ này chạy trên Java 17.
- `strip()` có thể trả chuỗi mới nhưng không sửa giá trị `String` ban đầu.

Đối chiếu các trường hợp: với `null`, số nguyên hoặc chuỗi chỉ chứa khoảng trắng, cả hai phương thức trả `"unavailable"`. Với `"  Java  "`, cả hai trả `"text=Java"`.

Nếu cần một ràng buộc độ dài, viết cùng cách:

```java
if (input instanceof String text
        && !text.isBlank()
        && text.length() <= 20) {
    System.out.println(text.strip());
}
```

Vế thứ hai và thứ ba được thực hiện chỉ khi biến `text` đã được ràng buộc, nên không cần lặp thêm `text != null`. Tuy nhiên, có thể vẫn cần kiểm tra các **thành phần tham chiếu bên trong** đối tượng nếu chúng có thể `null`.

## 4. Refactor guard clause: kiểm tra sai rồi return

Mã cũ thường loại bỏ đầu vào không đúng kiểu trước khi ép kiểu:

```java
static int legacyLength(Object input) {
    if (input == null || !(input instanceof String)) {
        return -1;
    }
    String text = (String) input;
    return text.length();
}
```

Có thể viết lại:

```java
static int modernLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Tại sao `text` dùng được **sau** `if`?

1. `input instanceof String text` là `true` duy nhất khi đầu vào khớp `String`.
2. Phủ định `!(...)` đúng khi không khớp, và khi đó phương thức `return -1` ngay.
3. Mọi đường chạy tới `return text.length()` đều có biểu thức `instanceof` đã khớp.
4. Trình biên dịch cho phép dùng `text` tại đây nhờ **flow scoping/definite matching**.

`modernLength(null)` và `modernLength(42)` đều trả `-1`; `modernLength("abc")` trả `3`. Không cần `String text = (String) input;` nữa.

Mẫu tương tự với `throw`:

```java
static String requireString(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text;
}
```

Ví dụ trên cố ý gộp `null` và kiểu không hợp lệ vào **cùng một** lỗi, giống điều kiện phủ định. Nếu mã cũ ném exception khác cho `null`, cần bảo toàn sự phân biệt đó.

## 5. Kết hợp phủ định với || để loại dữ liệu rỗng

Với điều kiện kiểm tra thất bại, Java vẫn cho phép sử dụng biến pattern ở vế phải của `||` nếu vế trái phủ định **chỉ sai khi phép khớp thành công**:

```java
static String validate(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "invalid";
    }
    return "valid=" + text.strip();
}
```

Cơ chế:

- Khi `input` là `null` hoặc không phải `String`, `!(input instanceof String text)` đúng; `||` không đọc `text.isBlank()` và trả `"invalid"`.
- Khi đầu vào là `String`, phép phủ định sai nên `text` chắc chắn đã được ràng buộc; lúc đó mới gọi `text.isBlank()`.
- Nếu `text` không blank, toàn điều kiện sai và chương trình đi tiếp tới `return "valid=" + text.strip()`.

Kết quả: `validate("  ")` trả `invalid`; `validate(" ABC ")` trả `valid=ABC`; `validate(null)` trả `invalid`.

**Tránh lỗi phổ biến với `||`:**

```java
// SAI — biểu thức không biên dịch vì vế phải có thể chạy khi s chưa khớp.
// if (input instanceof String s || s.isEmpty()) {
//     System.out.println(s.length());
// }
```

Với `a || b`, `b` chỉ được đánh giá nếu `a` sai. Vì vậy pattern `String s` **không** được bảo đảm tại `s.isEmpty()` trong đoạn sai. Ngược lại, `!(input instanceof String s) || s.isEmpty()` hợp lệ vì vế trái phủ định sai đồng nghĩa pattern bên trong thành công.

## 6. Khi null phải có hành vi riêng: đừng xóa nhánh

Không phải mọi null check đều thừa. Giả sử hệ thống yêu cầu phân biệt ba trường hợp:

- `null` nghĩa là dữ liệu **bị thiếu**.
- Một `String` là dữ liệu hợp lệ về kiểu.
- Giá trị thuộc kiểu khác báo dữ liệu **sai kiểu**.

Mẫu refactor đúng:

```java
static String distinguishNull(Object input) {
    if (input == null) {
        return "missing";
    }
    if (input instanceof String text) {
        return "string=" + text;
    }
    return "other type";
}
```

Nếu bỏ `if (input == null)` và chỉ dùng `input instanceof String text`, giá trị `null` sẽ rơi vào nhánh `"other type"`, làm **thay đổi contract**.

Đặc biệt cần giữ nhánh tách biệt khi mã cũ:

- Ném `NullPointerException` hoặc `IllegalArgumentException` với thông điệp cụ thể cho `null`.
- Ghi log/metric khác nhau giữa “không có dữ liệu” và “dữ liệu sai kiểu”.
- Trả mã lỗi/API response riêng cho trường hợp thiếu giá trị.
- Sử dụng giá trị mặc định hoặc xử lý nghiệp vụ riêng khi `null`.

Chỉ loại bỏ null check nếu **hành vi quan sát được** sau refactor vẫn giống trước.

## 7. Phối hợp nhiều type checks trong if / else if

Từ mã cũ:

```java
static String oldClassify(Object input) {
    if (input != null && input instanceof String) {
        String text = (String) input;
        if (!text.isEmpty()) {
            return "string length=" + text.length();
        }
    } else if (input != null && input instanceof Integer) {
        Integer n = (Integer) input;
        if (n > 0) {
            return "positive integer=" + n;
        }
    }
    return "other";
}
```

Có thể chuyển thành:

```java
static String classify(Object input) {
    if (input instanceof String text && !text.isEmpty()) {
        return "string length=" + text.length();
    } else if (input instanceof Integer n && n > 0) {
        return "positive integer=" + n;
    }
    return "other";
}
```

Hai nhánh có các biến pattern riêng: `text` thuộc `String`, `n` thuộc `Integer`. Bỏ được cast và null check thừa trong cả hai nhánh.

**Chú ý khi refactor:** nếu mã cũ có điều kiện phức tạp, nhánh `else if` có thể chỉ được xét trong một vài trường hợp. Ví dụ `if (obj instanceof String) { ... } else if (...)` và `if (obj instanceof String && extraCondition) { ... } else if (...)` **khác nhau** khi `obj` là `String` nhưng `extraCondition` sai. Đừng gộp điều kiện hoặc di chuyển `else` theo trực giác mà chưa đối chiếu.

## 8. Type pattern không thay thế mọi loại type check

Khi tự động hóa refactor, cần kiểm tra **ý nghĩa phép kiểm tra kiểu ban đầu**.

### instanceof và getClass() không luôn tương đương

`instanceof` chấp nhận đối tượng thuộc lớp con hoặc triển khai interface tương ứng. Ngược lại, `obj.getClass() == Base.class` yêu cầu **đúng lớp runtime** `Base`. Thay `getClass() == Base.class` bằng `instanceof Base b` có thể làm thay đổi cách xử lý subclass, và gọi `getClass()` trên `null` còn có thể ném `NullPointerException`. Nếu yêu cầu chính xác lớp runtime, phải giữ logic tương ứng.

### Một số generic type không dùng trực tiếp với instanceof

Không thể viết `input instanceof java.util.List<String> xs` vì `List<String>` là kiểu có tham số không reifiable trong ngữ cảnh này. Khi cần, có thể dùng `input instanceof java.util.List<?> xs` rồi kiểm tra phần tử theo yêu cầu nghiệp vụ; không được tự suy ra rằng mọi phần tử đều là `String`.

### Toán tử và biểu thức có tác dụng phụ

Nếu mã cũ gọi phương thức nhiều lần, chẳng hạn `getValue() != null && getValue() instanceof String`, mỗi lời gọi có thể có kết quả khác nhau hoặc tác dụng phụ. Refactor an toàn thường bắt đầu bằng cách lưu giá trị một lần vào biến cục bộ:

```java
Object value = getValue(); // Giả sử getValue() đã có trong lớp đang xét.
if (value instanceof String text) {
    System.out.println(text);
}
```

Đoạn trên minh họa cách làm và **không phải chương trình Java độc lập**, vì chưa định nghĩa `getValue()`. Trước khi đổi, phải quyết định số lần gọi `getValue()` có phải một phần hành vi quan trọng hay không; thay đổi số lần gọi một phương thức có side effect không nhất thiết tương đương.

## 9. Null ở record component là trường hợp khác (Java 21+)

Khi dùng **record pattern** từ Java 21, phải phân biệt null ở **đối tượng ngoài** với null nằm trong **thành phần record**:

```java
record Box(String label) {}

Object a = null;
Object b = new Box(null);

if (a instanceof Box(var label)) {
    // Không chạy: đối tượng a là null.
}
if (b instanceof Box(var label)) {
    System.out.println(label == null); // true
}
```

`Box(var label)` không khớp đối tượng `Box` bằng `null`. Tuy nhiên, vì `var label` là **component pattern** không điều kiện với kiểu khai báo `String`, nó có thể nhận thành phần `label == null`. Sau khi pattern khớp, `label.length()` vẫn sẽ ném `NullPointerException` nếu không kiểm tra `label` trước.

Khi refactor mã dùng record patterns, đừng suy luận rằng “pattern khớp” đồng nghĩa **mọi thành phần tham chiếu khác null**. Mục này là mở rộng cho Java 21; chương trình chính ở phần 11 chỉ cần Java 17.

## 10. Quy trình refactor bảo toàn hành vi

Thực hiện theo trình tự để hạn chế lỗi:

1. **Xác định giá trị được kiểm tra kiểu.** Nó là một biến cục bộ hay là kết quả gọi phương thức có thể thay đổi? Nếu là lời gọi có side effect, xác định yêu cầu về số lần gọi.
2. **Tìm các null check.** Đánh dấu check chỉ bảo vệ `instanceof`/cast và check có nhánh xử lý nghiệp vụ riêng.
3. **Chuyển `instanceof Type` + cast thành `instanceof Type variable`.** Chọn tên mới rõ nghĩa và không đụng phạm vi biến đã có.
4. **Bỏ null check dư thừa** khi nó không mang hành vi riêng. `instanceof` tự trả `false` với null.
5. **Giữ các điều kiện nghiệp vụ.** Ví dụ độ dài, `isBlank()`, số dương, quyền truy cập hoặc thông điệp lỗi, và bảo đảm thứ tự đánh giá.
6. **Kiểm tra flow scoping.** Dùng biến pattern trong nhánh khớp, vế phải `&&` phù hợp, hoặc sau guard phủ định có `return`/`throw`. Với `||`, xem kỹ hướng điều kiện.
7. **Đối chiếu đầu vào biên.** Ít nhất thử `null`, đối tượng sai kiểu, đúng kiểu nhưng giá trị rỗng, và đúng kiểu có dữ liệu. Thêm thử subclass/generic và ngoại lệ nếu code cũ liên quan.
8. **Biên dịch và chạy test hành vi.** So sánh output và exception giữa trước/sau trước khi xóa cast hoặc logic cũ.

## 11. Chương trình Java 17 hoàn chỉnh

Lưu toàn bộ đoạn mã sau vào tệp **`NullTypeRefactorDemo.java`**. Nó minh họa cả mã legacy và mã refactor để kiểm chứng kết quả:

```java
public class NullTypeRefactorDemo {
    static String legacyLabel(Object input) {
        if (input != null && input instanceof String) {
            String text = (String) input;
            if (!text.isBlank()) {
                return "text=" + text.strip();
            }
        }
        return "unavailable";
    }

    static String modernLabel(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "text=" + text.strip();
        }
        return "unavailable";
    }

    static int legacyLength(Object input) {
        if (input == null || !(input instanceof String)) {
            return -1;
        }
        String text = (String) input;
        return text.length();
    }

    static int modernLength(Object input) {
        if (!(input instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    static String validate(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "invalid";
        }
        return "valid=" + text.strip();
    }

    static String distinguishNull(Object input) {
        if (input == null) {
            return "missing";
        }
        if (input instanceof String text) {
            return "string=" + text;
        }
        return "other type";
    }

    static String classify(Object input) {
        if (input instanceof String text && !text.isEmpty()) {
            return "string length=" + text.length();
        } else if (input instanceof Integer n && n > 0) {
            return "positive integer=" + n;
        }
        return "other";
    }

    public static void main(String[] args) {
        Object[] inputs = {null, "  Java  ", "   ", "ok", 42};
        for (Object input : inputs) {
            String before = legacyLabel(input);
            String after = modernLabel(input);
            System.out.println("same=" + before.equals(after) + ", " + after);
        }

        System.out.println("length(null)=" + modernLength(null));
        System.out.println("length(abc)=" + modernLength("abc"));
        System.out.println("length(42)=" + modernLength(42));
        System.out.println("legacy and modern length agree="
                + (legacyLength("abc") == modernLength("abc")));

        System.out.println("validate(blank)=" + validate("  "));
        System.out.println("validate(text)=" + validate(" ABC "));
        System.out.println("validate(null)=" + validate(null));

        System.out.println("null branch=" + distinguishNull(null));
        System.out.println("non-string branch=" + distinguishNull(42));
        System.out.println("classify(number)=" + classify(5));
        System.out.println("classify(text)=" + classify("Go"));
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac --release 17 -encoding UTF-8 NullTypeRefactorDemo.java
java NullTypeRefactorDemo
```

**Kết quả stdout đã kiểm chứng:**

```text
same=true, unavailable
same=true, text=Java
same=true, unavailable
same=true, text=ok
same=true, unavailable
length(null)=-1
length(abc)=3
length(42)=-1
legacy and modern length agree=true
validate(blank)=invalid
validate(text)=valid=ABC
validate(null)=invalid
null branch=missing
non-string branch=other type
classify(number)=positive integer=5
classify(text)=string length=2
```

Năm dòng đầu đối chiếu `legacyLabel` và `modernLabel` trên `null`, chuỗi có khoảng trắng ở hai đầu, chuỗi blank, chuỗi ngắn và kiểu khác. Tất cả đều in `same=true`. Phần tiếp theo xác nhận guard phủ định, phép `||` và nhánh `null` riêng hoạt động đúng. Kiểm tra kết quả trên những mẫu này là bước xác minh hữu ích; trong dự án thực tế vẫn nên chạy bộ test theo các tình huống nghiệp vụ của hệ thống.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai hoặc rủi ro | Cách sửa |
| --- | --- | --- |
| Giữ `obj != null` trước `obj instanceof String s` dù không có hành vi riêng | Check dư, làm điều kiện khó đọc | Dùng `obj instanceof String s` |
| Giữ cast `(String) obj` trong nhánh đã có `String s` | Lặp kiểm tra/ép kiểu, bỏ lỡ lợi ích của pattern | Dùng trực tiếp `s` |
| Xóa nhánh `if (obj == null)` có kết quả riêng | Thay đổi hành vi `null`, lỗi hoặc thông điệp | Giữ nhánh `null` trước type pattern |
| Dùng `s` ở vế phải `obj instanceof String s || ...` | Vế phải có thể chạy khi pattern chưa khớp | Dùng `&&` hoặc phủ định phù hợp với `||` |
| Dùng `s` ngoài `if` không có guard thoát sớm | Compiler không đảm bảo definite matching | Giữ logic trong nhánh đúng hoặc dùng early return |
| Cho rằng `obj instanceof String s` loại cả chuỗi rỗng | `instanceof` chỉ kiểm tra kiểu, không kiểm tra nội dung | Thêm `!s.isBlank()` hay quy tắc dữ liệu tương ứng |
| Đổi `getClass() == T.class` sang `instanceof T t` | Hai phép kiểm tra có thể khác nhau với subclass | Giữ kiểm tra exact class nếu đó là contract |
| Truy cập thành phần nullable sau record pattern | Biến thành phần đã ràng buộc vẫn có thể chứa null | Kiểm tra biến trước khi gọi phương thức |
| Refactor gọi phương thức có side effect nhiều lần | Có thể đổi thứ tự hoặc số lần thực thi | Phân tích behavior, cân nhắc snapshot giá trị |
| Đặt biến pattern trùng tên biến trong phạm vi xung đột | Compiler có thể báo khai báo trùng | Đổi tên biến pattern rõ nghĩa |

## 13. Bài tập áp dụng

**Bài 1.** Refactor đoạn sau mà giữ kết quả `false` cho `null`:

```java
boolean isPositive(Object value) {
    if (value != null && value instanceof Integer) {
        Integer n = (Integer) value;
        return n > 0;
    }
    return false;
}
```

*Gợi ý đáp án:*

```java
boolean isPositive(Object value) {
    return value instanceof Integer n && n > 0;
}
```

`null` không khớp `Integer n` nên toàn biểu thức vẫn trả `false`.

**Bài 2.** Cần trả `"missing"` nếu `value == null`, trả `"ok"` nếu là `String`, ngược lại trả `"bad type"`. Có thể xóa null check chỉ vì `instanceof` tự trả false không?

*Đáp án:* Không. Xóa null check sẽ làm `null` rơi vào `"bad type"`, thay đổi yêu cầu nghiệp vụ. Giữ ba nhánh riêng.

**Bài 3.** Đoạn `if (value instanceof String s && !s.isBlank())` có thể gây `NullPointerException` tại `s.isBlank()` vì `value == null` không?

*Đáp án:* Không. Khi `value == null`, `instanceof` là `false`, và vế phải của `&&` không được đánh giá.

**Bài 4.** Vì sao `if (!(value instanceof String s)) return;` cho phép dùng `s` ngay sau câu lệnh này (nếu đặt trong phương thức `void`)?

*Đáp án:* Đường đi không khớp đã kết thúc bằng `return`. Mọi đường có thể đi tiếp đều chắc chắn đã khớp `String s`.

**Bài 5.** Vì sao không nên tự động đổi `value.getClass() == Base.class` thành `value instanceof Base b`?

*Đáp án:* `getClass() == Base.class` kiểm tra đúng lớp runtime, còn `instanceof Base` nhận cả các lớp con; giá trị `null` cũng khác về cách xử lý nếu trước đó chưa có null guard.

**Tài liệu tham khảo chính thức:** [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Oracle Java – Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html), [JLS 17 – `15.20.2 Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2), [JLS 17 – `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440).
