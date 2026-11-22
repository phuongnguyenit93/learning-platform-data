# Khoảng trắng không ngắt dòng không luôn được `String.strip()` loại bỏ

## 1. Mục tiêu và hiện tượng cần nhớ

Trong Java 11+ (bao gồm Java 17), `String.strip()` xóa các ký tự được `Character.isWhitespace(...)` phân loại là khoảng trắng **ở đầu và cuối chuỗi**. Tên phương thức dễ làm ta hiểu nhầm rằng nó xóa **mọi** loại ký tự trông như dấu cách. Thực tế, một số **dấu cách không ngắt dòng** (*non-breaking spaces*) vẫn được giữ nguyên.

Ví dụ:

```java
String text = "\u00A0Java\u00A0"; // NBSP + Java + NBSP
System.out.println(text.strip().equals(text)); // true
System.out.println(text.isBlank());             // false
```

Hai dấu cách hai bên có mã Unicode **U+00A0 NO-BREAK SPACE**, không phải dấu cách ASCII U+0020. `strip()` giữ nguyên chúng, còn `isBlank()` không coi một chuỗi chỉ chứa NBSP là “blank”.

Bài học này giúp bạn:
- Phân biệt **dấu cách nhìn thấy được**, **Unicode space character** và các ký tự mà Java xem là `whitespace`.
- Hiểu sự khác nhau giữa `strip()`, `trim()`, `isBlank()` và `Character.isSpaceChar()`.
- Xử lý đúng NBSP, FIGURE SPACE, NARROW NO-BREAK SPACE khi làm sạch văn bản.
- Chọn chính sách loại bỏ khoảng trắng phù hợp để không làm thay đổi ý nghĩa của dữ liệu.

## 2. Dấu cách không ngắt dòng là gì?

Trong văn bản được dàn trang, một số khoảng trắng có mục đích **giữ hai phần văn bản trên cùng một dòng**. Ví dụ, khoảng giữa số và đơn vị trong `"10 kg"` đôi khi được viết bằng NBSP để tránh xuống dòng giữa `10` và `kg`.

Ba code point thường gặp:

| Code point | Tên Unicode | Đặc điểm |
| --- | --- | --- |
| `U+00A0` | NO-BREAK SPACE (NBSP) | Khoảng trắng không ngắt dòng thông dụng; HTML có thực thể `&nbsp;`. |
| `U+2007` | FIGURE SPACE | Khoảng trắng có bề rộng liên quan chữ số, không ngắt dòng. |
| `U+202F` | NARROW NO-BREAK SPACE | Khoảng trắng không ngắt dòng có bề rộng hẹp hơn; xuất hiện trong một số quy ước dàn trang. |

Chúng thường khó phân biệt với dấu cách thường bằng mắt. Khi sao chép từ HTML, tài liệu PDF, trình soạn thảo hoặc nội dung đã được dàn trang, chuỗi có thể chứa các code point này dù người dùng nghĩ chỉ có “space”.

**Lưu ý:** Các ký tự này là dữ liệu văn bản có ý nghĩa. Tùy nghiệp vụ, việc tự ý xóa hoặc đổi toàn bộ NBSP thành dấu cách thường có thể phá vỡ ý định trình bày hoặc quy tắc định dạng.

## 3. Vì sao `strip()` không loại bỏ mọi dấu cách?

Theo hợp đồng của Java, `String.strip()` xác định ký tự cần loại bỏ bằng **`Character.isWhitespace(int)`**. Trong Java 17, `Character.isWhitespace` trả về `false` đối với ba ký tự không ngắt dòng `U+00A0`, `U+2007` và `U+202F`.

Điều này khác với `Character.isSpaceChar(int)`, vốn trả về `true` cho các ký tự thuộc nhóm Unicode space separators, bao gồm ba trường hợp trên.

Bảng kết quả đáng chú ý trên Java 17:

| Ký tự | `Character.isWhitespace(cp)` | `Character.isSpaceChar(cp)` | `strip()` có thể loại bỏ ở đầu/cuối? |
| --- | --- | --- | --- |
| `U+0020` SPACE | `true` | `true` | Có |
| `U+0009` TAB | `true` | `false` | Có |
| `U+00A0` NO-BREAK SPACE | `false` | `true` | **Không** |
| `U+2007` FIGURE SPACE | `false` | `true` | **Không** |
| `U+202F` NARROW NO-BREAK SPACE | `false` | `true` | **Không** |
| `U+2003` EM SPACE | `true` | `true` | Có |
| `U+3000` IDEOGRAPHIC SPACE | `true` | `true` | Có |

Sự khác biệt thể hiện rõ qua ba đoạn mã:

```java
System.out.println("\u2003Java\u2003".strip().equals("Java")); // true
System.out.println("\u00A0Java\u00A0".strip().equals("Java")); // false
System.out.println("\u00A0Java\u00A0".strip()
        .equals("\u00A0Java\u00A0"));                       // true
```

Không thể suy ra rằng `strip()` sẽ loại bỏ một ký tự chỉ vì tên Unicode của nó có từ “SPACE” hoặc vì nó hiển thị giống một khoảng trắng.

### Một trường hợp dễ bất ngờ: hỗn hợp SPACE và NBSP

```java
String mixed = " \u00A0Java\u00A0 ";
String result = mixed.strip();

System.out.println(result.equals("\u00A0Java\u00A0")); // true
```

`strip()` bỏ dấu cách ASCII `U+0020` ngoài cùng. Sau đó, khi gặp NBSP `U+00A0` ở đầu và cuối vùng còn lại, nó **dừng lại** vì NBSP không thỏa `Character.isWhitespace`. Bởi vậy, một chuỗi đã gọi `strip()` vẫn có thể bắt đầu hoặc kết thúc bằng dấu cách không ngắt dòng.

## 4. Phân biệt các phép kiểm tra khi gặp NBSP

`strip()` chỉ cắt các code point được `Character.isWhitespace` công nhận ở hai mép; `stripLeading()` và `stripTrailing()` chỉ cắt một phía. `isBlank()` kiểm tra toàn chuỗi nhưng cùng tiêu chí Java whitespace, vì vậy cả `strip()` lẫn `isBlank()` **không coi NBSP là khoảng trắng có thể bỏ qua**. `trim()` lại cắt các đơn vị mã `char <= U+0020`, nên cũng giữ NBSP.

~~~java
String nbsp = "\u00A0";
String em = "\u2003";
System.out.println(nbsp.strip().isEmpty()); // false
System.out.println(nbsp.isBlank());         // false
System.out.println(em.strip().isEmpty());   // true
System.out.println(em.trim().isEmpty());    // false
~~~

Hai cặp kết quả giúp phân biệt **khoảng trắng không ngắt dòng** với EM SPACE và giới hạn riêng của `trim()`. Nếu chỉ cần phát hiện dữ liệu rỗng hoặc chỉ có *Java whitespace*, dùng `isBlank()`; nếu yêu cầu chấp nhận hoặc cắt thêm NBSP ở biên, áp dụng predicate theo hợp đồng nghiệp vụ như ở mục 7.

## 5. Ví dụ Java 17+ chạy độc lập, hiện rõ code point

Vì NBSP khó nhìn thấy, ví dụ dưới đây **in mã Unicode** thay vì chỉ in khoảng trắng để có kết quả kiểm chứng được.

Lưu thành file `NonBreakingSpaceDemo.java`:

```java
import java.util.stream.Collectors;

public class NonBreakingSpaceDemo {
    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String ascii = "\t Java \n";
        String nbsp = "\u00A0Java\u00A0";
        String emSpace = "\u2003Java\u2003";
        String mixed = " \u00A0Java\u00A0 ";

        System.out.println("ASCII strip = "
                + codePoints(ascii.strip()));
        System.out.println("NBSP strip = "
                + codePoints(nbsp.strip()));
        System.out.println("EM SPACE strip = "
                + codePoints(emSpace.strip()));
        System.out.println("mixed strip = "
                + codePoints(mixed.strip()));

        System.out.println("NBSP only isBlank = "
                + "\u00A0".isBlank());
        System.out.println("EM SPACE only isBlank = "
                + "\u2003".isBlank());
        System.out.println("NBSP trim unchanged = "
                + nbsp.trim().equals(nbsp));

        int[] samples = {
            0x0020, 0x0009, 0x00A0,
            0x2007, 0x202F, 0x2003
        };
        for (int cp : samples) {
            System.out.printf(
                    "U+%04X whitespace=%s spaceChar=%s%n",
                    cp,
                    Character.isWhitespace(cp),
                    Character.isSpaceChar(cp));
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 NonBreakingSpaceDemo.java
java NonBreakingSpaceDemo
```

Đầu ra:

```text
ASCII strip = U+004A U+0061 U+0076 U+0061
NBSP strip = U+00A0 U+004A U+0061 U+0076 U+0061 U+00A0
EM SPACE strip = U+004A U+0061 U+0076 U+0061
mixed strip = U+00A0 U+004A U+0061 U+0076 U+0061 U+00A0
NBSP only isBlank = false
EM SPACE only isBlank = true
NBSP trim unchanged = true
U+0020 whitespace=true spaceChar=true
U+0009 whitespace=true spaceChar=false
U+00A0 whitespace=false spaceChar=true
U+2007 whitespace=false spaceChar=true
U+202F whitespace=false spaceChar=true
U+2003 whitespace=true spaceChar=true
```

**Giải thích:**
1. Chuỗi có TAB `U+0009`, SPACE `U+0020` và LINE FEED `U+000A` được `strip()` cắt phần trắng ở hai đầu, chỉ còn `Java`.
2. Chuỗi có NBSP ở hai đầu vẫn chứa hai `U+00A0` sau `strip()`.
3. EM SPACE `U+2003` được `Character.isWhitespace` nhận diện nên bị cắt.
4. Với `mixed`, `strip()` bỏ SPACE bên ngoài rồi giữ NBSP ngay sát chữ.
5. `"\u00A0".isBlank()` là `false` mặc dù trên giao diện chuỗi có thể trông như một khoảng trắng.

## 6. Khi nào nên giữ nguyên NBSP?

NBSP không phải lúc nào cũng là dữ liệu “bẩn”. Nó có thể được dùng để:
- Giữ số và đơn vị cùng dòng, chẳng hạn `"10 km"` hoặc `"25 °C"`.
- Giữ tiền tệ và giá trị cùng dòng theo quy ước trình bày.
- Giữ các phần của một tên riêng hoặc cụm từ được dàn trang có chủ đích.
- Biểu diễn khoảng trắng không ngắt dòng từ HTML qua thực thể `&nbsp;`.

Hãy phân biệt hai nhiệm vụ:

**Làm sạch input để tìm giá trị nghiệp vụ:** Nếu biểu mẫu cho phép người dùng dán dữ liệu chứa NBSP ở **đầu/cuối**, có thể chủ đích xem NBSP là khoảng trắng biên và loại bỏ nó.

**Bảo toàn nội dung văn bản:** Nếu ứng dụng xử lý nội dung trình bày, tài liệu hoặc bản ghi cần tính toàn vẹn, nên giữ các dấu cách đặc biệt, trừ khi yêu cầu nói rõ được phép chuẩn hóa chúng.

Không có phương thức duy nhất “đúng” cho cả hai mục đích. Trước khi chuẩn hóa cần trả lời: **Ta muốn bỏ khoảng trắng ở biên, hay thay đổi mọi khoảng trắng bên trong?** Việc thay thế bên trong chuỗi có thể thay đổi ý nghĩa dàn trang.

## 7. Cách bỏ cả NBSP ở ranh giới nếu nghiệp vụ yêu cầu

Nếu chính sách là “bỏ tất cả ký tự mà Java xem là whitespace **hoặc** Unicode space character ở hai đầu”, có thể kết hợp `Character.isWhitespace` và `Character.isSpaceChar`.

Ví dụ phương thức hỗ trợ Java 17:

```java
static boolean boundarySpace(int codePoint) {
    return Character.isWhitespace(codePoint)
            || Character.isSpaceChar(codePoint);
}

static String stripBoundarySpaces(String text) {
    java.util.Objects.requireNonNull(text, "text");

    int begin = 0;
    int end = text.length();

    while (begin < end) {
        int cp = text.codePointAt(begin);
        if (!boundarySpace(cp)) {
            break;
        }
        begin += Character.charCount(cp);
    }

    while (begin < end) {
        int cp = text.codePointBefore(end);
        if (!boundarySpace(cp)) {
            break;
        }
        end -= Character.charCount(cp);
    }

    return text.substring(begin, end);
}
```

Đây là **các phương thức cần đặt trong một lớp Java**, không phải chương trình độc lập có `main`. Ví dụ gọi bên trong `main`:

```java
String input = "\u00A0\u202FJava\u2007\u00A0";

System.out.println(input.strip().equals(input)); // true
System.out.println(stripBoundarySpaces(input)
        .equals("Java"));                         // true

String meaningful = "10\u00A0kg";
System.out.println(stripBoundarySpaces(meaningful)
        .equals(meaningful));                     // true
```

**Tại sao dùng `codePointAt` và `codePointBefore`?** Hai phương thức cho phép duyệt hai đầu chuỗi theo code point và dùng `Character.charCount(cp)` để tiến/lùi đúng số `char` UTF-16. Trong các ví dụ NBSP, code point nằm trong BMP, nhưng cách triển khai này thể hiện rõ đơn vị thao tác và có thể dùng cho mọi đầu vào Unicode trong phạm vi chính sách.

**Giới hạn cần hiểu:**
- `isWhitespace || isSpaceChar` là **một chính sách rõ ràng do ứng dụng chọn**; nó không phải định nghĩa duy nhất của “khoảng trắng” trong mọi tiêu chuẩn và mọi ngôn ngữ.
- Phương thức chỉ bỏ ký tự ở **hai đầu**, không xóa hay thay NBSP **ở giữa** như `"10\u00A0kg"`.
- Với văn bản chứa các surrogate đơn lẻ (chuỗi UTF-16 không hoàn chỉnh), phương thức không tự sửa các dữ liệu đó.
- Khi yêu cầu nghiêm ngặt theo một phiên bản Unicode hay tiêu chuẩn bên ngoài, nên xác định trực tiếp tập code point được cho phép và viết kiểm thử cho tập đó.

### Nếu chỉ muốn bỏ riêng NBSP thông thường ở hai đầu

Bạn có thể chọn một chính sách hẹp hơn `boundarySpace`, ví dụ chỉ coi `U+00A0` bổ sung vào những gì `strip()` vốn đã loại bỏ. Đó là lựa chọn thích hợp nếu ứng dụng cần giữ `U+2007` và `U+202F` vì mục đích dàn trang.

Không nên vô thức thay toàn bộ dấu cách đặc biệt bằng một dấu cách ASCII chỉ vì người dùng nhìn thấy chúng giống nhau.

## 8. Dùng Unicode regex khi hợp đồng muốn bao gồm NBSP

Nếu chính sách ghi rõ “bỏ các ký tự thuộc Unicode White_Space ở đầu/cuối”, Java regex với cờ `(?U)` là một lựa chọn. Mặc định `\s` không bao phủ NBSP, còn `(?U)\s` nhận diện thêm NBSP và một số ký tự Unicode khác.

~~~java
String nbsp = "\u00A0Hello\u00A0";
String cleaned = nbsp.replaceAll("(?U)\\A\\s+|\\s+\\z", "");
System.out.println(cleaned.equals("Hello")); // true
~~~

Hai neo `\A` và `\z` đảm bảo chỉ bỏ ở **hai đầu toàn bộ chuỗi**; không thay NBSP có ý nghĩa nằm giữa các từ. Unicode White_Space cũng khác với phép hợp `Character.isWhitespace || Character.isSpaceChar` ở mục 7: chẳng hạn U+0085 thuộc Unicode White_Space nhưng không được hai API `Character` này nhận diện. Hãy kiểm thử theo chính tập ký tự nghiệp vụ yêu cầu và giữ nguyên dữ liệu gốc khi cần phục hồi.

## 9. Có nên dùng Unicode normalization để “xóa khoảng trắng”?

`java.text.Normalizer` dùng để chuẩn hóa dạng Unicode, không phải API chuyên xóa khoảng trắng ở đầu/cuối.

Ví dụ, chuẩn hóa tương thích `NFKC` có thể biến NBSP `U+00A0` thành SPACE `U+0020`:

```java
String nbsp = "\u00A0";
String nfkc = java.text.Normalizer.normalize(
        nbsp, java.text.Normalizer.Form.NFKC);
System.out.println(nfkc.equals(" ")); // true
```

Nhưng **không nên tự động chạy NFKC cho mọi input chỉ để giải quyết NBSP**. Chuẩn hóa tương thích có thể thay đổi nhiều loại ký tự khác và làm mất sự khác biệt kiểu chữ/định dạng mà ứng dụng cần giữ.

Nếu chỉ cần xử lý khoảng trắng biên, cách thích hợp hơn là định nghĩa tập ký tự biên và loại bỏ **đúng vùng cần loại bỏ**. Nếu yêu cầu nghiệp vụ là chuẩn hóa toàn bộ văn bản theo NFKC, hãy áp dụng như một chính sách riêng và kiểm tra đầy đủ các hệ quả của nó.

## 10. Các sai lầm phổ biến

| Nhầm lẫn | Vấn đề thực tế | Hướng xử lý |
| --- | --- | --- |
| “`strip()` xóa tất cả dấu cách.” | `U+00A0`, `U+2007`, `U+202F` vẫn có thể tồn tại ở biên. | Kiểm tra `Character.isWhitespace` và chính sách ứng dụng. |
| “`trim()` chắc chắn xóa nhiều hơn `strip()`.” | `trim()` chủ yếu dựa trên code unit `<= U+0020`, không xử lý NBSP. | Dùng API theo hợp đồng, không theo tên gọi. |
| “Có NBSP nên `isBlank()` phải trả `true`.” | `isBlank()` cũng dựa trên `Character.isWhitespace`. | Nếu muốn định nghĩa blank rộng hơn, tự kiểm tra theo predicate được chọn. |
| “Thấy trống thì chuỗi rỗng.” | NBSP có độ dài thật, ví dụ `"\u00A0".length() == 1`. | In code point khi gỡ lỗi. |
| “Thay hết NBSP thành SPACE luôn an toàn.” | Có thể mất hành vi không ngắt dòng, ảnh hưởng dàn trang. | Chỉ chuẩn hóa theo chính sách rõ ràng. |
| “`\s` mặc định trong regex luôn bắt được NBSP.” | Tập ký tự phụ thuộc cờ Unicode của `Pattern`. | Dùng `(?U)` khi cần Unicode regex và đã kiểm thử. |
| “`NFKC` chỉ thay NBSP.” | Đây là phép chuẩn hóa tương thích ảnh hưởng nhiều ký tự. | Không dùng NFKC như mẹo làm sạch khoảng trắng nếu không cần. |

### Cách chẩn đoán một chuỗi trông như có dấu cách

Đừng chỉ in trực tiếp `System.out.println(text)`. Khi cần xác định ký tự đặc biệt, hãy in mã của các code point:

```java
String input = "\u00A0Hi\u202F";
input.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Đầu ra:

```text
U+00A0
U+0048
U+0069
U+202F
```

Cách kiểm tra này cho biết chính xác tại sao một chuỗi **có vẻ đã được trim/strip nhưng vẫn chứa khoảng trắng ở hai đầu**.

## 11. Tự kiểm tra kiến thức

### Câu 1

```java
String s = "\u00A0";
System.out.println(s.isBlank());
System.out.println(s.strip().isEmpty());
```

**Đáp án:** `false` và `false`. `U+00A0` không thỏa `Character.isWhitespace`, nên `strip()` không xóa nó, và `isBlank()` không xem chuỗi này là blank.

### Câu 2

```java
String s = "\u2003Java\u2003";
System.out.println(s.trim().equals(s));
System.out.println(s.strip().equals("Java"));
```

**Đáp án:** `true` và `true`. `trim()` không bỏ EM SPACE `U+2003`, nhưng `strip()` có bỏ vì `Character.isWhitespace(0x2003)` là `true`.

### Câu 3

```java
String s = " \u00A0A\u00A0 ";
System.out.println(s.strip()
        .equals("\u00A0A\u00A0"));
```

**Đáp án:** `true`. `strip()` bỏ SPACE ASCII ở ngoài nhưng dừng khi gặp NBSP.

### Câu 4

Một sản phẩm cần loại bỏ NBSP ở đầu/cuối trường tên được dán từ HTML, nhưng phải giữ khoảng trắng không ngắt dòng giữa số và đơn vị trong `"10\u00A0kg"`. Nên làm gì?

**Đáp án:** Áp dụng quy tắc **chỉ bỏ ở ranh giới** (chẳng hạn hàm `stripBoundarySpaces` ở trên), không dùng `replace("\u00A0", " ")` trên toàn bộ văn bản. Kiểm thử cả trường hợp NBSP ở biên và NBSP có ý nghĩa ở giữa.

### Câu 5

Trong Java 17, `Character.isSpaceChar(0x00A0)` và `Character.isWhitespace(0x00A0)` có cùng kết quả không?

**Đáp án:** Không. `isSpaceChar(0x00A0) == true` còn `isWhitespace(0x00A0) == false`. Đây chính là nguyên nhân NBSP không bị `strip()` loại bỏ.

## 12. Tổng kết

- `String.strip()` (Java 11+) loại bỏ **`Character.isWhitespace` ở hai đầu**, không phải mọi Unicode space character.
- Ba dấu cách không ngắt dòng quan trọng là **NBSP `U+00A0`**, **FIGURE SPACE `U+2007`**, **NARROW NO-BREAK SPACE `U+202F`**; trong Java 17 chúng được `isSpaceChar` nhận diện nhưng `isWhitespace` không nhận diện.
- `trim()` cũng không loại bỏ NBSP; `isBlank()` có thể trả `false` cho chuỗi chỉ chứa NBSP.
- Nếu yêu cầu nghiệp vụ muốn bỏ thêm các khoảng trắng không ngắt dòng ở **đầu/cuối**, hãy định nghĩa rõ predicate biên hoặc dùng Unicode-aware regex với kiểm thử phù hợp.
- Không xóa NBSP bên trong chuỗi hoặc áp dụng chuẩn hóa tương thích một cách tùy tiện; dấu cách không ngắt dòng có thể mang ý nghĩa dàn trang.

## Tài liệu tham khảo

- [Java SE 17 — `String.strip()`, `stripLeading()`, `stripTrailing()` và `isBlank()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character.isWhitespace` và `Character.isSpaceChar`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Java SE 17 — `Pattern` và `UNICODE_CHARACTER_CLASS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Standard — Unicode Character Database](https://www.unicode.org/ucd/)
