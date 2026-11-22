# Phân biệt chuỗi rỗng (empty), chuỗi blank và `null` trong Java 11+

## 1. Vì sao cần phân biệt ba trạng thái?

Khi nhận một giá trị `String` từ biểu mẫu, API, tệp cấu hình hoặc cơ sở dữ liệu, ba tình huống nhìn có vẻ “không có nội dung” thực ra mang ý nghĩa khác nhau:

- **`null`:** biến tham chiếu **không trỏ tới đối tượng `String` nào**. Không thể gọi phương thức của `String` trên giá trị này.
- **Chuỗi rỗng (empty):** có đối tượng `String` hợp lệ nhưng **không chứa ký tự nào**: `""`.
- **Chuỗi blank:** có đối tượng `String` và **chỉ chứa các ký tự được Java xem là khoảng trắng (whitespace)**, **hoặc** chuỗi hoàn toàn rỗng. Khái niệm này được thể hiện bằng `String.isBlank()` từ **Java 11**.

Điểm dễ nhầm nhất: **chuỗi rỗng cũng là chuỗi blank**, nhưng `null` **không phải chuỗi** nên không thể kết luận bằng `null.isBlank()`. Một chuỗi có khoảng trắng như `"   "` là blank nhưng **không** empty.

Trong Java, `String.isBlank()` vẫn là API hiện hành; cú pháp Java 11 này tiếp tục dùng được trên các JDK hiện đại. Trong bài học này, “blank” luôn có nghĩa **theo chuẩn Java `Character.isWhitespace(int)`**, không có nghĩa “mọi ký tự trông giống khoảng trắng”.

## 2. Ba phép kiểm tra cốt lõi

### 2.1. Kiểm tra `null`

```java
String value = null;
boolean absent = (value == null); // true
```

`null` là giá trị tham chiếu đặc biệt; nó **không phải** đối tượng `String`, không có độ dài và không có phương thức. Do đó:

```java
String value = null;
// value.isEmpty(); // Lỗi khi chạy: NullPointerException
// value.isBlank(); // Lỗi khi chạy: NullPointerException
```

Vì vậy phải kiểm tra `value == null` hoặc bảo đảm giá trị không `null` trước khi gọi các phương thức chuỗi. Ngược lại, chuỗi chứa bốn ký tự `"null"` là **chuỗi văn bản bình thường**, không đồng nghĩa với tham chiếu `null`.

### 2.2. Kiểm tra chuỗi rỗng bằng `isEmpty()`

`String.isEmpty()` trả về `true` khi và chỉ khi độ dài chuỗi bằng 0:

```java
"".isEmpty();       // true
" ".isEmpty();      // false: có một dấu cách
"\t\n".isEmpty();   // false: có ký tự tab và xuống dòng
"Java".isEmpty();   // false
```

`isEmpty()` không loại bỏ whitespace trước khi kiểm tra. Điều này phù hợp với yêu cầu phân biệt “không gửi ký tự nào” và “đã gửi một số ký tự khoảng trắng”.

### 2.3. Kiểm tra chuỗi blank bằng `isBlank()`

Từ **Java 11**, `String.isBlank()` trả về `true` nếu chuỗi **rỗng hoặc tất cả Unicode code point của chuỗi đều thỏa `Character.isWhitespace(int)`**:

```java
"".isBlank();          // true
"   ".isBlank();       // true
"\t\n".isBlank();      // true
"\u2003".isBlank();    // true: EM SPACE (U+2003)
" Java ".isBlank();    // false: chứa các chữ cái
```

`isBlank()` không tự xóa whitespace và không sửa nội dung chuỗi; nó chỉ trả về `boolean`. Nếu cần làm sạch khoảng trắng đầu/cuối, xem mục 5.

**Quan hệ logic:**

```text
empty => blank
blank không nhất thiết => empty
null khác cả empty lẫn blank vì null không phải String
```

Muốn nhận diện một chuỗi **blank nhưng không rỗng**, có thể dùng `!value.isEmpty() && value.isBlank()` **sau khi đã bảo đảm `value != null`**.

## 3. Bảng so sánh những giá trị thường gặp

Bảng dưới đây giả sử có biến `String s` chứa giá trị tương ứng. Dấu `N/A` nghĩa là **không thể gọi phương thức trên `null`**.

| Giá trị của `s` | `s == null` | `s.isEmpty()` | `s.isBlank()` | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `null` | `true` | N/A | N/A | Không có đối tượng `String` |
| `""` | `false` | `true` | `true` | Rỗng và cũng là blank |
| `" "` | `false` | `false` | `true` | Một dấu cách thường U+0020 |
| `" \t "` | `false` | `false` | `true` | Chỉ có khoảng trắng/tab |
| `"\u2003"` | `false` | `false` | `true` | EM SPACE U+2003 là whitespace theo Java |
| `"\u00A0"` | `false` | `false` | `false` | NO-BREAK SPACE U+00A0 không được `isBlank()` coi là whitespace |
| `"\u200B"` | `false` | `false` | `false` | ZERO WIDTH SPACE U+200B không được `isBlank()` coi là whitespace |
| `" Java "` | `false` | `false` | `false` | Có chữ cái khác whitespace |
| `"null"` | `false` | `false` | `false` | Chuỗi gồm các chữ n-u-l-l |

Dấu `\uXXXX` trong các giá trị minh họa là ký hiệu Unicode escape của Java, cho phép biểu diễn những ký tự khó nhìn trên màn hình.

**Cảnh báo quan trọng với Unicode:** `isBlank() == false` chỉ có nghĩa “có ít nhất một code point không được `Character.isWhitespace` nhận diện”; nó **không bảo đảm chuỗi có văn bản nhìn thấy được**. Ví dụ NO-BREAK SPACE (NBSP), FIGURE SPACE (U+2007), NARROW NO-BREAK SPACE (U+202F) và ZERO WIDTH SPACE (U+200B) có thể làm người đọc tưởng chuỗi trống nhưng vẫn cho `isBlank() == false`.

## 4. Ví dụ Java 11 chạy được và kết quả chính xác

Tạo tệp **`StringStateDemo.java`**:

```java
public class StringStateDemo {
    static String classify(String value) {
        if (value == null) {
            return "NULL";
        }
        if (value.isEmpty()) {
            return "EMPTY";
        }
        if (value.isBlank()) {
            return "BLANK";
        }
        return "NOT_BLANK";
    }

    static void show(String label, String value) {
        String empty = value == null ? "N/A" : Boolean.toString(value.isEmpty());
        String blank = value == null ? "N/A" : Boolean.toString(value.isBlank());
        System.out.println(label + ": " + classify(value)
                + " | isEmpty=" + empty + " | isBlank=" + blank);
    }

    public static void main(String[] args) {
        show("null-reference", null);
        show("empty", "");
        show("space-and-tab", " \t ");
        show("em-space", "\u2003");
        show("non-breaking-space", "\u00A0");
        show("zero-width-space", "\u200B");
        show("text", " Java ");
        show("literal-null", "null");

        String padded = "\u2003Java\u2003";
        System.out.println("trim removes EM SPACE: " + padded.trim().equals("Java"));
        System.out.println("strip removes EM SPACE: " + padded.strip().equals("Java"));
        System.out.println("NBSP isWhitespace: " + Character.isWhitespace(0x00A0));
        System.out.println("NBSP isSpaceChar: " + Character.isSpaceChar(0x00A0));
    }
}
```

Biên dịch với JDK 11 hoặc mới hơn; tùy chọn `--release 11` giúp xác thực mã không dùng API/cú pháp vượt Java 11 khi sử dụng JDK mới:

```bash
javac --release 11 -encoding UTF-8 StringStateDemo.java
java StringStateDemo
```

**Đầu ra chính xác:**

```text
null-reference: NULL | isEmpty=N/A | isBlank=N/A
empty: EMPTY | isEmpty=true | isBlank=true
space-and-tab: BLANK | isEmpty=false | isBlank=true
em-space: BLANK | isEmpty=false | isBlank=true
non-breaking-space: NOT_BLANK | isEmpty=false | isBlank=false
zero-width-space: NOT_BLANK | isEmpty=false | isBlank=false
text: NOT_BLANK | isEmpty=false | isBlank=false
literal-null: NOT_BLANK | isEmpty=false | isBlank=false
trim removes EM SPACE: false
strip removes EM SPACE: true
NBSP isWhitespace: false
NBSP isSpaceChar: true
```

**Cách đọc kết quả:**

1. Hàm `classify` kiểm tra `null` **trước** để tránh `NullPointerException`.
2. Kiểm tra `isEmpty` **trước** `isBlank` để nhãn `EMPTY` không bị gộp thành `BLANK`, vì chuỗi rỗng đồng thời thỏa `isBlank()`.
3. `" \t "` và `"\u2003"` không rỗng nhưng là blank. Ngược lại, `"\u00A0"` và `"\u200B"` đều không thỏa `isBlank()`.
4. `trim()` và `strip()` có định nghĩa whitespace khác nhau; với EM SPACE ở hai đầu, `strip()` loại được nhưng `trim()` không loại được.
5. `Character.isSpaceChar(0x00A0)` trả về `true` trong khi `Character.isWhitespace(0x00A0)` trả về `false`, vì hai phương thức kiểm tra theo **hai tiêu chí khác nhau**.

## 5. `strip()`, `trim()` và giới hạn của khái niệm whitespace

Trong ngữ cảnh Java 11+, ba phép xử lý liên quan có mục đích khác nhau:

| Phương thức | Mục đích | Quy tắc |
| --- | --- | --- |
| `isEmpty()` | Kiểm tra độ dài bằng 0 | Không loại bỏ ký tự |
| `isBlank()` | Kiểm tra chỉ chứa whitespace theo Java hoặc rỗng | Dựa `Character.isWhitespace` |
| `strip()` | Loại whitespace **ở đầu và cuối** | Dựa `Character.isWhitespace`, có từ Java 11 |
| `stripLeading()` / `stripTrailing()` | Chỉ loại ở đầu / cuối | Có từ Java 11 |
| `trim()` | Loại ký tự ở đầu/cuối có mã không vượt U+0020 theo quy tắc của `trim` | Khác tiêu chí Unicode của `strip` |

Ví dụ:

```java
String name = "\u2003Java\u2003";
boolean a = name.trim().equals("Java");  // false
boolean b = name.strip().equals("Java"); // true
```

`trim()` **không bị deprecated** và vẫn có trường hợp dùng hợp lý khi chủ đích xử lý bộ ký tự theo quy tắc của nó. Nhưng để nhận diện chuỗi chỉ chứa khoảng trắng theo cách mà `isBlank()` định nghĩa, hãy dùng `isBlank()` trực tiếp, thay vì mặc định cho rằng `trim().isEmpty()` luôn tương đương.

Lưu ý riêng **NO-BREAK SPACE U+00A0**: cả `isBlank()` lẫn `strip()` đều dựa trên `Character.isWhitespace`, vốn loại trừ một số non-breaking spaces. Do đó:

```java
String nbsp = "\u00A0";
boolean blank = nbsp.isBlank();           // false
boolean emptyAfterStrip = nbsp.strip().isEmpty(); // false
```

Nếu dữ liệu cần coi NBSP, U+2007, U+202F hoặc U+200B như ký tự không mang nội dung, phải **định nghĩa quy tắc kiểm tra/chuẩn hóa riêng** cho nguồn dữ liệu đó. Không được suy từ việc ký tự “khó nhìn thấy” rằng `isBlank()` bắt buộc sẽ là `true`.

### Unicode code point và `String.length()`

Java `String` sử dụng biểu diễn **UTF-16**. `length()` đếm **UTF-16 code unit**, không phải số ký tự hiển thị hay số grapheme cluster. Điều này không đổi nguyên tắc: `isEmpty()` chỉ đúng khi chuỗi có **0 code unit**; `isBlank()` quan tâm tới các code point thỏa quy tắc whitespace của Java.

Với dữ liệu đa ngôn ngữ, không dùng `length() > 0` làm bằng chứng rằng người dùng đã nhập nội dung có thể nhìn thấy; chuỗi có thể chứa khoảng trắng, ký tự không in hoặc ký tự định dạng.

## 6. Viết điều kiện kiểm tra null-safe

### 6.1. Xem `null` và blank là “chưa nhập dữ liệu”

Nếu quy tắc nghiệp vụ coi `null`, `""` và chuỗi chỉ có whitespace là cùng nhóm thiếu đầu vào:

```java
static boolean isMissing(String value) {
    return value == null || value.isBlank();
}

static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

Toán tử `||` và `&&` trong Java **short-circuit**: khi `value == null` đúng, vế `value.isBlank()` không được thực hiện; khi `value != null` sai, vế `!value.isBlank()` không được thực hiện. Vì vậy hai phương thức không ném `NullPointerException` đối với `null`.

**Sai thứ tự:**

```java
// Sai nếu value có thể null:
// return value.isBlank() || value == null;
```

Kết hợp null-safe này có thể dùng cho nhãn hiển thị bắt buộc có văn bản, với điều kiện domain chấp nhận định nghĩa whitespace của Java.

### 6.2. Phân biệt thật sự cả ba trạng thái

Khi hợp đồng API quy định `null` = không gửi trường, `""` = chủ động xóa, và `"   "` = dữ liệu không hợp lệ, **không gộp cả ba thành một giá trị**:

```java
static String decide(String input) {
    if (input == null) {
        return "NOT_PROVIDED";
    }
    if (input.isEmpty()) {
        return "EXPLICITLY_EMPTY";
    }
    if (input.isBlank()) {
        return "WHITESPACE_ONLY";
    }
    return "HAS_NON_WHITESPACE";
}
```

Đây là ví dụ về **lựa chọn quy tắc nghiệp vụ**, không phải semantics mặc định của JSON/HTTP/cơ sở dữ liệu. Khi xây API thực tế phải dựa vào contract của từng trường để quyết định có được gộp `null`, empty và blank hay không.

### 6.3. Chuẩn hóa trước khi lưu hoặc hiển thị

Nếu yêu cầu của trường dữ liệu cho phép loại khoảng trắng ở hai đầu:

```java
static String normalizeLabel(String input) {
    if (input == null) {
        return null;
    }
    return input.strip();
}
```

Với input `"  Java  "`, kết quả là `"Java"`. Với input `"   "`, kết quả là `""`. Tuy nhiên với input `"\u00A0"`, kết quả vẫn không rỗng vì `strip` không loại bỏ NBSP. Tùy contract, có thể đổi `null` thành lỗi dữ liệu, giữ nguyên hoặc trả về một giá trị mặc định — không có cách đúng cho mọi ứng dụng.

Không tự động áp dụng `strip()` cho mọi loại thông tin (chẳng hạn mật khẩu hoặc dữ liệu có ý nghĩa về whitespace), vì việc xóa ký tự có thể thay đổi giá trị gốc.

## 7. Những nhầm lẫn cần tránh

| Nhầm lẫn | Điều đúng trong Java |
| --- | --- |
| “`null` cũng là chuỗi rỗng” | `null` không phải đối tượng `String`; `""` là một chuỗi hợp lệ |
| “`"".isBlank()` là false” | Kết quả **true**: tập ký tự rỗng thỏa điều kiện “chỉ có whitespace” của API |
| “`isEmpty()` kiểm tra khoảng trắng” | `isEmpty()` chỉ kiểm tra `length() == 0` |
| “`isBlank()` sẽ không gặp `NullPointerException`” | Vẫn ném lỗi khi gọi trên tham chiếu `null` |
| “`"null"` là `null`” | Đó là chuỗi chứa bốn chữ cái |
| “Mọi dấu cách Unicode đều được `isBlank()` nhận là blank” | Một số code point như U+00A0, U+2007, U+202F không thỏa `Character.isWhitespace` |
| “`strip()` xóa mọi ký tự vô hình” | `strip()` chỉ bỏ whitespace theo Java ở đầu/cuối; không xóa NBSP, zero-width space |
| “`trim().isEmpty()` luôn giống `isBlank()`” | Khác nhau vì tiêu chí whitespace khác nhau |
| “`isBlank() == false` đồng nghĩa dữ liệu có chữ nhìn thấy” | Có thể chỉ chứa NBSP hoặc ký tự zero-width |

## 8. Checklist áp dụng nhanh

1. **Có thể `null`?** Kiểm tra `value == null` trước khi gọi phương thức của `String`.
2. **Cần biết đúng 0 ký tự?** Dùng `value.isEmpty()` sau khi kiểm tra null.
3. **Cần biết chuỗi rỗng hoặc toàn whitespace theo Java?** Dùng `value.isBlank()` (Java 11+).
4. **Cần phân biệt cả ba?** Kiểm tra lần lượt: `null` → `isEmpty()` → `isBlank()` → trường hợp còn lại.
5. **Cần loại khoảng trắng đầu/cuối?** Cân nhắc `strip()`, đồng thời xác định rõ xử lý NBSP và các ký tự định dạng tùy dữ liệu.
6. **Kết quả kiểm tra ảnh hưởng tới lưu trữ/validation?** Ghi rõ trong contract việc `null`, empty và blank có tương đương nhau hay không.

## 9. Tự kiểm tra

**Câu hỏi 1:** `"".isBlank()` và `"".isEmpty()` trả về gì?  
**Đáp án:** Cả hai đều `true`.

**Câu hỏi 2:** `" \t ".isEmpty()` và `" \t ".isBlank()` trả về gì?  
**Đáp án:** Lần lượt là `false` và `true`.

**Câu hỏi 3:** Với `String input = null;`, biểu thức `input == null || input.isBlank()` có an toàn không?  
**Đáp án:** Có; Java short-circuit nên không gọi `isBlank` khi `input` là `null`.

**Câu hỏi 4:** `"\u00A0".isBlank()` trả về gì?  
**Đáp án:** `false`; NO-BREAK SPACE U+00A0 không được `Character.isWhitespace` xem là whitespace.

## 10. Ghi nhớ

- `null`: **không có đối tượng chuỗi**.
- `isEmpty()`: **đúng 0 ký tự**, không tự bỏ khoảng trắng.
- `isBlank()`: **rỗng hoặc chỉ chứa whitespace theo Java**, hỗ trợ từ Java 11 và vẫn áp dụng hiện nay.
- `isEmpty() == true` kéo theo `isBlank() == true` đối với `String` khác `null`, nhưng chiều ngược lại không đúng.
- Không nhầm khái niệm whitespace của Java với mọi ký tự Unicode có vẻ trống; các giá trị như NBSP hoặc zero-width space cần được xử lý theo chính sách dữ liệu cụ thể.

**Tài liệu chính thức:** [Java String API — isEmpty, isBlank, strip](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html); [Java Character API — isWhitespace, isSpaceChar](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html).