# Chuỗi rỗng, chuỗi trắng, `null` và chuỗi `"null"` trong Java

Trong Java, một biến kiểu `String` có thể không tham chiếu đến đối tượng nào (`null`), tham chiếu đến chuỗi không có ký tự (`""`), đến chuỗi chỉ chứa khoảng trắng (`"   "`), hoặc đến một chuỗi có bốn chữ cái `"null"`. Đây là bốn trường hợp khác nhau về **dữ liệu và cách xử lý**. Phân biệt đúng giúp kiểm tra đầu vào, thiết kế API, xử lý cấu hình và ghi log chính xác.

## 1. Hiểu từng trường hợp

### 1.1. Tham chiếu `null`: không có đối tượng `String`

`null` là literal đặc biệt biểu thị việc biến tham chiếu chưa trỏ tới đối tượng. Nó **không phải là một chuỗi**.

```java
String name = null;
System.out.println(name == null); // true
// name.length(); // NullPointerException nếu chạy
```

Biểu thức `name == null` kiểm tra trạng thái tham chiếu. Không thể gọi trực tiếp `length()`, `isEmpty()`, `isBlank()` hay `strip()` trên tham chiếu `null`.

### 1.2. Chuỗi rỗng `""`: có đối tượng, độ dài bằng 0

```java
String empty = "";
System.out.println(empty.length());  // 0
System.out.println(empty.isEmpty()); // true
System.out.println(empty.isBlank()); // true
```

`""` là giá trị chuỗi hợp lệ không chứa ký tự nào. Nó khác `null`. Một chuỗi rỗng cũng được `isBlank()` coi là blank vì không có ký tự nào khác whitespace.

### 1.3. Chuỗi trắng (blank): chỉ gồm các ký tự whitespace

Ví dụ `" "`, `"   "`, `"\t"`, `"\n"` hay `" \t\n "`. Chúng chứa ký tự thật, nên thường **không rỗng**, nhưng `isBlank()` trả về `true` nếu mọi ký tự đều được Java nhận diện là whitespace.

```java
String spaces = " \t";
System.out.println(spaces.length());  // 2
System.out.println(spaces.isEmpty()); // false
System.out.println(spaces.isBlank()); // true
```

Lưu ý: “Nhìn có vẻ là khoảng trắng” không đồng nghĩa với `Character.isWhitespace`. Chẳng hạn NO-BREAK SPACE (`\u00A0`) không được `String.isBlank()` coi là whitespace, trong khi EM SPACE (`\u2003`) được coi là whitespace. Vì vậy, kiểm tra blank không phải phép kiểm tra tổng quát mọi ký tự vô hình hay mọi dấu cách Unicode.

### 1.4. Chuỗi chứa chữ `"null"`: bốn ký tự thông thường

```java
String word = "null";
System.out.println(word == null);       // false
System.out.println(word.length());      // 4
System.out.println(word.isBlank());     // false
System.out.println("null".equals(word)); // true
```

Đây là văn bản gồm `'n'`, `'u'`, `'l'`, `'l'`. Java không tự biến chuỗi `"null"` thành tham chiếu `null`. Ví dụ `"NULL"` hoặc `" Null "` cũng là các chuỗi khác `"null"` khi so sánh bằng `equals`.

## 2. Bảng so sánh nhanh

Các hàng dưới đây là trạng thái độc lập của biến `s`; cột “bằng chữ null” dùng `"null".equals(s)`.

| Giá trị của `s` | `s == null` | `s != null && s.isEmpty()` | `s != null && s.isBlank()` | `"null".equals(s)` |
| --- | --- | --- | --- | --- |
| `null` | `true` | `false` | `false` | `false` |
| `""` | `false` | `true` | `true` | `false` |
| `" \t"` | `false` | `false` | `true` | `false` |
| `"null"` | `false` | `false` | `false` | `true` |
| `"Java"` | `false` | `false` | `false` | `false` |

**Điểm mấu chốt:** `isEmpty()` chỉ kiểm tra độ dài 0; `isBlank()` chấp nhận cả độ dài 0 lẫn chuỗi chỉ gồm whitespace. Cả hai đều cần bảo vệ khỏi `null`.

## 3. Những API cần biết

| Công cụ | Câu hỏi trả lời | Đặc điểm |
| --- | --- | --- |
| `s == null` | Có thiếu đối tượng chuỗi không? | An toàn cả khi `s` bằng `null` |
| `s.isEmpty()` | Có đúng 0 ký tự không? | `NullPointerException` khi `s == null` |
| `s.isBlank()` | Có rỗng hoặc chỉ gồm whitespace không? | Có từ Java 11; `NullPointerException` khi `s == null` |
| `s.trim()` | Bỏ các ký tự ở hai đầu có mã ≤ U+0020? | Quy tắc lịch sử, không tương đương mọi whitespace Unicode |
| `s.strip()` | Bỏ whitespace ở hai đầu theo `Character.isWhitespace`? | Có từ Java 11; thường phù hợp hơn `trim()` khi cần Unicode |
| `"null".equals(s)` | Giá trị có đúng chữ `"null"` không? | An toàn khi `s == null`; phân biệt hoa/thường |
| `Objects.equals(s, "null")` | Hai giá trị có bằng nhau, kể cả `null`? | So sánh `null` an toàn, cần `java.util.Objects` |

Dùng toán tử `||` theo cơ chế *short-circuit* để tránh gọi phương thức trên `null`:

```java
boolean missingOrBlank = s == null || s.isBlank();
boolean hasText = s != null && !s.isBlank();
```

Hai dòng này là **đoạn mã minh họa** khi đã có biến `String s`. Dòng đầu kiểm tra “không có văn bản hữu ích” theo định nghĩa `isBlank`; dòng thứ hai kiểm tra có ít nhất một ký tự không phải whitespace. Nếu nghiệp vụ cần phân biệt “không gửi trường” và “gửi trường rỗng”, đừng gom các trạng thái ấy vào một điều kiện.

## 4. Ví dụ Java 17 có thể biên dịch và chạy

Lưu nội dung sau vào tệp `StringStates.java`:

```java
public class StringStates {
    private static void show(String label, String s) {
        System.out.printf(
                "%s -> null=%b, empty=%b, blank=%b, textNull=%b%n",
                label,
                s == null,
                s != null && s.isEmpty(),
                s != null && s.isBlank(),
                "null".equals(s)
        );
    }

    public static void main(String[] args) {
        show("missing", null);
        show("empty", "");
        show("blank", " \t");
        show("literal", "null");
        show("normal", "Java");

        String emSpace = "\u2003";
        String nbsp = "\u00A0";
        System.out.printf(
                "EM SPACE -> blank=%b, trimLength=%d, stripLength=%d%n",
                emSpace.isBlank(),
                emSpace.trim().length(),
                emSpace.strip().length()
        );
        System.out.printf(
                "NBSP -> blank=%b, stripLength=%d%n",
                nbsp.isBlank(),
                nbsp.strip().length()
        );
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac StringStates.java
java StringStates
```

Kết quả chuẩn:

```text
missing -> null=true, empty=false, blank=false, textNull=false
empty -> null=false, empty=true, blank=true, textNull=false
blank -> null=false, empty=false, blank=true, textNull=false
literal -> null=false, empty=false, blank=false, textNull=true
normal -> null=false, empty=false, blank=false, textNull=false
EM SPACE -> blank=true, trimLength=1, stripLength=0
NBSP -> blank=false, stripLength=1
```

Ở đây các điều kiện có `s != null && ...` bảo vệ lời gọi phương thức. `EM SPACE` cho thấy `strip()` xử lý whitespace Unicode khác `trim()`. `NBSP` cho thấy `isBlank()` không tự nhận diện mọi ký tự trông giống khoảng trắng.

## 5. Ứng dụng: phân loại dữ liệu đầu vào mà không đánh mất ý nghĩa

Giả sử một trường văn bản được nhận từ API hoặc biểu mẫu:

- `null`: có thể có nghĩa “không được cung cấp”, tùy hợp đồng API.
- `""`: đã có một giá trị chuỗi nhưng độ dài bằng 0; có thể thể hiện ý định xóa dữ liệu.
- `"   "`: đã gửi ký tự nhưng không có nội dung chữ hữu ích.
- `"null"`: có thể là văn bản người dùng thực sự muốn nhập, **không tự coi là không có dữ liệu**.
- `"  Minh  "`: có chữ với khoảng trắng ở đầu/cuối; có thể cần chuẩn hóa trước khi lưu.

Có thể dùng phương thức phân loại sau **bên trong một lớp Java**:

```java
enum TextKind { MISSING, EMPTY, BLANK, LITERAL_NULL, TEXT }

static TextKind classify(String s) {
    if (s == null) {
        return TextKind.MISSING;
    }
    if (s.isEmpty()) {
        return TextKind.EMPTY;
    }
    if (s.isBlank()) {
        return TextKind.BLANK;
    }
    if ("null".equals(s)) {
        return TextKind.LITERAL_NULL;
    }
    return TextKind.TEXT;
}
```

**Thứ tự kiểm tra có ý nghĩa:** một chuỗi rỗng cũng là blank theo `isBlank()`, nên phải kiểm tra `isEmpty()` trước nếu muốn tách hai nhóm. Bước kiểm tra chữ `"null"` chỉ hữu ích khi bài toán cần nhận biết chính xác văn bản này; đừng biến nó thành quy tắc xóa dữ liệu một cách mặc định.

Nếu nghiệp vụ **chủ động quyết định** mọi chuỗi thiếu/rỗng/trắng đều được biểu diễn bằng `null`, có thể dùng đoạn phương thức sau (đặt trong một lớp):

```java
static String normalizeOptionalText(String s) {
    if (s == null) {
        return null;
    }
    String stripped = s.strip();
    return stripped.isEmpty() ? null : stripped;
}
```

Ví dụ: `normalizeOptionalText(null)`, `normalizeOptionalText("")` và `normalizeOptionalText("  \t ")` đều trả về `null`; `normalizeOptionalText("  Java  ")` trả về `"Java"`; `normalizeOptionalText("null")` vẫn trả về `"null"`. Đây là **lựa chọn theo yêu cầu nghiệp vụ**: không dùng nó khi phải giữ khác biệt giữa trường vắng mặt, trường rỗng và trường chỉ có khoảng trắng. Phương thức cũng tuân theo quy tắc Unicode của `strip()`, nên NBSP không tự bị loại bỏ.

## 6. Vì sao log hoặc chuyển kiểu có thể gây nhầm lẫn?

Java có thể tạo ra **chuỗi** `"null"` từ tham chiếu `null` trong phép nối chuỗi hoặc chuyển sang văn bản:

```java
String absent = null;
String literal = "null";

System.out.println("value=" + absent);                 // value=null
System.out.println("value=" + literal);                // value=null
System.out.println(String.valueOf((Object) absent));   // null
System.out.println(java.util.Objects.toString(absent, "<missing>")); // <missing>
```

Hai dòng đầu có đầu ra giống hệt nhau, dù đầu vào khác nhau. `String.valueOf((Object) absent)` trả về chuỗi `"null"` (không phải tham chiếu `null`). Ép kiểu `(Object)` trong ví dụ làm rõ overload muốn gọi; tránh nhầm với các overload như `valueOf(char[])`. Muốn log phân biệt, ghi trạng thái riêng (`absent == null`) hoặc dùng một dấu thay thế nhất quán như `"<missing>"`. Nếu cần truyền dữ liệu qua JSON, hãy giữ rõ sự khác nhau giữa giá trị `null`, chuỗi `"null"`, chuỗi `""` và thuộc tính vắng mặt theo hợp đồng dữ liệu.

## 7. Các lỗi thường gặp

1. **Gọi phương thức trực tiếp trên `null`:** `s.isEmpty()`, `s.isBlank()`, `s.trim()` gây `NullPointerException` nếu `s == null`. Kiểm tra tham chiếu trước khi gọi.
2. **Dùng `isEmpty()` để chặn chuỗi trắng:** `"   ".isEmpty()` trả về `false`. Nếu muốn chặn đầu vào chỉ chứa whitespace, dùng `isBlank()` trên giá trị khác `null`.
3. **Dùng `s.equals("null")` khi `s` có thể `null`:** đổi thành `"null".equals(s)` hoặc `Objects.equals(s, "null")`.
4. **So sánh chuỗi bằng `==`:** `==` so sánh tham chiếu đối tượng (ngoại trừ cách dùng với `null`), không phải nội dung chữ; dùng `equals` cho nội dung. Không dựa vào string pool để kiểm tra.
5. **Dùng `trim().isEmpty()` mà cho rằng giống `isBlank()`:** chúng có quy tắc whitespace khác nhau; Unicode có những trường hợp cho kết quả khác.
6. **Tự coi chữ `"null"` là dữ liệu thiếu:** chỉ được chuyển đổi khi có quy ước rõ ràng; nếu không sẽ làm mất văn bản hợp lệ của người dùng.
7. **Chuẩn hóa quá sớm:** gộp mọi trạng thái vào `null` hoặc `""` có thể làm mất thông tin phân biệt “không gửi”, “xóa trống” và “chỉ gửi khoảng trắng”.

## 8. Cách chọn điều kiện cho đúng yêu cầu

| Yêu cầu | Điều kiện hoặc cách làm |
| --- | --- |
| Chỉ phát hiện không có tham chiếu | `s == null` |
| Chỉ phát hiện chuỗi có đúng 0 ký tự | `s != null && s.isEmpty()` |
| Phát hiện chuỗi trắng, kể cả rỗng (không tính `null`) | `s != null && s.isBlank()` |
| Phát hiện `null` hoặc chuỗi rỗng | `s == null || s.isEmpty()` |
| Phát hiện `null` hoặc chuỗi blank | `s == null || s.isBlank()` |
| Phát hiện chính xác văn bản `"null"` | `"null".equals(s)` |
| Cần giữ được cả bốn trạng thái riêng biệt | Kiểm tra theo thứ tự: `null` → `isEmpty()` → `isBlank()` → `"null".equals(s)` |
| Muốn cắt whitespace đầu/cuối theo Java 11+ | `s == null ? null : s.strip()`; cân nhắc quy tắc Unicode |

**Tự kiểm tra:** Dự đoán `isEmpty()` và `isBlank()` cho `""`, `"  "`, `"abc"`; sau đó thử `null`, `"null"` và ký tự `\u00A0`. Nếu kết quả gây ngạc nhiên, hãy kiểm tra trước xem bạn đang nói về **tham chiếu**, **độ dài**, **whitespace theo Java** hay **nội dung văn bản**.
