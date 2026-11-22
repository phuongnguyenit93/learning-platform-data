# String.isBlank() và khoảng trắng theo Unicode trong Java 11

## Mục tiêu

Sau bài học, bạn có thể giải thích chính xác khi nào `String.isBlank()` trả về `true`, nhận ra những ký tự nhìn giống dấu cách nhưng Java không xem là khoảng trắng, phân biệt `isBlank()` với `isEmpty()`, `trim()` và `strip()`, đồng thời chọn chính sách kiểm tra dữ liệu phù hợp khi làm việc với chuỗi Unicode.

Bài tập trung vào những API **vẫn được hỗ trợ trong Java hiện hành** và sử dụng cú pháp chạy được trên Java 11 trở lên. Cách phân loại khoảng trắng dưới đây được đối chiếu với Javadoc Java 11 và tài liệu `Character` của các bản JDK hiện hành.

## 1. `String.isBlank()` kiểm tra điều gì?

Phương thức:

~~~java
public boolean isBlank()
~~~

được thêm từ **Java 11** (`Since: 11`) vào `java.lang.String`. Theo Javadoc, kết quả là:

- `true` nếu chuỗi **rỗng** (`""`), hoặc **mọi Unicode code point** trong chuỗi đều được Java xem là khoảng trắng.
- `false` nếu có **ít nhất một code point** không được Java xem là khoảng trắng.

Khái niệm *khoảng trắng theo Java* ở đây được định nghĩa bởi `Character.isWhitespace(int)`, **không phải** cứ ký tự trông trống trên màn hình thì `isBlank()` phải trả `true`.

Một số ví dụ nhanh:

~~~java
"".isBlank();          // true: chuỗi rỗng
" ".isBlank();         // true: U+0020 SPACE
"\t\n".isBlank();      // true: tab và xuống dòng
"\u2003".isBlank();    // true: U+2003 EM SPACE
"\u3000".isBlank();    // true: U+3000 IDEOGRAPHIC SPACE
"A".isBlank();         // false: có chữ A
" A \t".isBlank();     // false: chứa A
"\u00A0".isBlank();    // false: U+00A0 NO-BREAK SPACE
"\u200B".isBlank();    // false: U+200B ZERO WIDTH SPACE
~~~

**Đọc đúng:** `isBlank()` kiểm tra **toàn bộ** chuỗi, không phải kiểm tra liệu chuỗi *có chứa* khoảng trắng. `"A B"` chứa dấu cách nhưng `"A B".isBlank()` là `false`.

Đây là phương thức instance trả về `boolean`, **không thay đổi chuỗi**, không tự cắt khoảng trắng và không xử lý `null`:

~~~java
String text = null;
// text.isBlank(); // Ném NullPointerException nếu bỏ dấu chú thích.
boolean missing = text == null || text.isBlank(); // true
~~~

Việc xem `null` là «thiếu dữ liệu» hay là lỗi lập trình phải do hợp đồng đầu vào quyết định; `isBlank()` tự nó không đưa ra quyết định đó.

## 2. Unicode code point và định nghĩa khoảng trắng của Java

Unicode gán cho mỗi ký tự một **code point**, thường viết dạng `U+XXXX`. `String` lưu văn bản theo đơn vị mã UTF-16; một ký tự ngoài vùng BMP có thể chiếm hai `char`. `isBlank()` được đặc tả theo **code point**, nên khi tự viết quy tắc phân loại, nên dùng `Character.isWhitespace(int)` và `String.codePoints()` thay vì giả định mỗi `char` luôn là một ký tự đầy đủ.

Có thể hình dung điều kiện của `isBlank()` bằng biểu thức tương đương về mặt ý nghĩa đối với một `String` khác `null`:

~~~java
text.codePoints().allMatch(Character::isWhitespace)
~~~

Trong đó `allMatch` trả `true` cho stream rỗng, phù hợp với việc `"".isBlank()` là `true`. Đây là **mô hình để hiểu cơ chế**, không cần tự viết lại khi `isBlank()` đã tồn tại.

### `Character.isWhitespace(int)` bao gồm và loại trừ gì?

Theo Javadoc Java SE, `Character.isWhitespace(codePoint)` trả `true` cho:

- Các ký tự thuộc nhóm Unicode **SPACE_SEPARATOR**, **LINE_SEPARATOR** và **PARAGRAPH_SEPARATOR**, **ngoại trừ ba non-breaking space** `U+00A0`, `U+2007`, `U+202F`.
- Các ký tự điều khiển được Java liệt kê rõ: `U+0009` TAB, `U+000A` LINE FEED, `U+000B` VERTICAL TAB, `U+000C` FORM FEED, `U+000D` CARRIAGE RETURN, và `U+001C` đến `U+001F`.

Vì vậy không thể dùng quy tắc đơn giản như «mọi ký tự có tên SPACE đều là whitespace Java». Các ký tự **non-breaking space** được thiết kế để tránh ngắt dòng ở vị trí nhất định, nhưng `Character.isWhitespace` chủ động **loại trừ** chúng.

`Character.isSpaceChar(int)` là phép kiểm tra **khác**: nó xét các nhóm Unicode `SPACE_SEPARATOR`, `LINE_SEPARATOR`, `PARAGRAPH_SEPARATOR`; do đó nhận diện ba non-breaking space kể trên nhưng **không** xem TAB là space character. Hai phương thức có tập kết quả giao nhau nhưng không đồng nhất.

### Bảng các code point quan trọng

| Code point | Tên / cách nhập trong Java | `isWhitespace` | `isSpaceChar` | `String` chứa duy nhất ký tự đó có `isBlank()`? |
| --- | --- | --- | --- | --- |
| `U+0020` | SPACE: `" "` | `true` | `true` | `true` |
| `U+0009` | TAB: `"\t"` | `true` | `false` | `true` |
| `U+000A` | LINE FEED: `"\n"` | `true` | `false` | `true` |
| `U+2003` | EM SPACE: `"\u2003"` | `true` | `true` | `true` |
| `U+3000` | IDEOGRAPHIC SPACE: `"\u3000"` | `true` | `true` | `true` |
| `U+00A0` | NO-BREAK SPACE: `"\u00A0"` | `false` | `true` | **`false`** |
| `U+2007` | FIGURE SPACE: `"\u2007"` | `false` | `true` | **`false`** |
| `U+202F` | NARROW NO-BREAK SPACE: `"\u202F"` | `false` | `true` | **`false`** |
| `U+200B` | ZERO WIDTH SPACE: `"\u200B"` | `false` | `false` | **`false`** |
| `U+0085` | NEXT LINE (NEL): `"\u0085"` | `false` | `false` | **`false`** |

**Lưu ý:** thuộc tính **Unicode White_Space** của tiêu chuẩn Unicode, cách xác định **Java whitespace** và khái niệm **Java space character** là các cách phân loại khác nhau. Chẳng hạn `U+0085` được Unicode liệt kê trong thuộc tính `White_Space` nhưng không thỏa các tiêu chí của `Character.isWhitespace`. Nếu hệ thống yêu cầu đúng thuộc tính Unicode theo một phiên bản cụ thể, phải chọn bộ dữ liệu/thư viện và kiểm thử theo đúng đặc tả đó; **không mặc định** `isBlank()` bao phủ mọi ký tự thuộc Unicode `White_Space`.

Javadoc `Character` có thể sử dụng dữ liệu phiên bản Unicode khác nhau giữa các đời JDK. Với các ký tự và quy tắc quan trọng đối với nghiệp vụ, hãy kiểm thử trên **phiên bản JDK thực tế đang chạy**.

## 3. Thực hành Java 11: thấy sự khác nhau bằng kết quả thật

Tạo tệp **BlankUnicodeDemo.java** với chương trình độc lập:

~~~java
public class BlankUnicodeDemo {
    private static void inspect(String label, String text) {
        System.out.printf(
                "%s: empty=%s, blank=%s, trimEmpty=%s, stripEmpty=%s%n",
                label,
                text.isEmpty(),
                text.isBlank(),
                text.trim().isEmpty(),
                text.strip().isEmpty());
    }

    public static void main(String[] args) {
        inspect("empty", "");
        inspect("space", " ");
        inspect("tab+lf", "\t\n");
        inspect("em-space", "\u2003");
        inspect("ideographic", "\u3000");
        inspect("nbsp", "\u00A0");
        inspect("figure-space", "\u2007");
        inspect("narrow-nbsp", "\u202F");
        inspect("zero-width", "\u200B");
        inspect("text", " A ");

        int nbsp = 0x00A0;
        System.out.println(
                "NBSP predicates: whitespace=" + Character.isWhitespace(nbsp)
                + ", spaceChar=" + Character.isSpaceChar(nbsp));
    }
}
~~~

Biên dịch và chạy bằng JDK 11 hoặc JDK mới hơn hỗ trợ target 11:

~~~bash
javac --release 11 BlankUnicodeDemo.java
java BlankUnicodeDemo
~~~

**Đầu ra chính xác:**

~~~text
empty: empty=true, blank=true, trimEmpty=true, stripEmpty=true
space: empty=false, blank=true, trimEmpty=true, stripEmpty=true
tab+lf: empty=false, blank=true, trimEmpty=true, stripEmpty=true
em-space: empty=false, blank=true, trimEmpty=false, stripEmpty=true
ideographic: empty=false, blank=true, trimEmpty=false, stripEmpty=true
nbsp: empty=false, blank=false, trimEmpty=false, stripEmpty=false
figure-space: empty=false, blank=false, trimEmpty=false, stripEmpty=false
narrow-nbsp: empty=false, blank=false, trimEmpty=false, stripEmpty=false
zero-width: empty=false, blank=false, trimEmpty=false, stripEmpty=false
text: empty=false, blank=false, trimEmpty=false, stripEmpty=false
NBSP predicates: whitespace=false, spaceChar=true
~~~

Giải thích các hàng dễ nhầm:

- **`empty`:** `isEmpty()` và `isBlank()` đều trả `true` vì chuỗi không chứa code point nào.
- **`em-space`, `ideographic`:** đó là các khoảng trắng được `Character.isWhitespace` nhận diện; `strip()` loại bỏ được nhưng `trim()` không loại bỏ vì nằm ngoài ngưỡng `U+0020`.
- **`nbsp`, `figure-space`, `narrow-nbsp`:** nhìn giống khoảng trắng nhưng **không được `isBlank()` hoặc `strip()` chấp nhận theo định nghĩa của Java**.
- **`zero-width`:** độ rộng hiển thị bằng 0 không đủ để biến một ký tự thành Java whitespace; chuỗi có `U+200B` vẫn không `isBlank()`.
- **`text`:** có ký tự `A` nên không thể là blank dù hai đầu có dấu cách.

Chuỗi Java như `"\u00A0"` trong chương trình biểu diễn ký tự Unicode tương ứng, khác với một chuỗi chứa các ký tự hiển thị `\`, `u`, `0`, `0`, `A`, `0`. Khi kiểm thử, nên đặt nhãn/ký hiệu code point rõ ràng vì bản thân các khoảng trắng rất khó phân biệt bằng mắt.

## 4. `isBlank()`, `isEmpty()`, `trim()`, `strip()` khác nhau thế nào?

| Cách gọi | Vai trò / định nghĩa | Ví dụ phân biệt |
| --- | --- | --- |
| `s.isEmpty()` | Chỉ kiểm tra `s.length() == 0`. | `" ".isEmpty()` là `false`. |
| `s.isBlank()` | Trả `true` khi chuỗi rỗng hoặc mọi code point là `Character.isWhitespace`. | `"\u2003".isBlank()` là `true`; `"\u00A0".isBlank()` là `false`. |
| `s.trim()` | Trả chuỗi mới/chuỗi hiện có sau khi bỏ các ký tự đầu và cuối có giá trị mã `<= U+0020`. | `"\u2003".trim()` vẫn còn EM SPACE. |
| `s.strip()` | Trả chuỗi sau khi bỏ code point `Character.isWhitespace` ở **hai đầu**. | `"\u2003".strip()` là `""`; `"\u00A0".strip()` vẫn chứa NBSP. |
| `s.stripLeading()` / `s.stripTrailing()` | Chỉ loại bỏ Java whitespace ở đầu / cuối chuỗi. | Không tự xóa khoảng trắng ở giữa chuỗi. |

`trim()` vẫn là API tồn tại và có những ngữ nghĩa riêng; tuy nhiên **`trim().isEmpty()` không phải phép thay thế chính xác cho `isBlank()`**. Ví dụ `"\u2003".isBlank()` là `true`, còn `"\u2003".trim().isEmpty()` là `false`. Ở chiều ngược lại, `trim()` có thể loại bỏ những ký tự điều khiển `<= U+0020` mà `Character.isWhitespace` không công nhận: một chuỗi chỉ chứa `U+0000` có `trim().isEmpty() == true` nhưng `isBlank() == false`.

Với `s != null`, biểu thức `s.strip().isEmpty()` có kết quả boolean phù hợp với `s.isBlank()` vì chúng sử dụng cùng tiêu chí `Character.isWhitespace`. Dù vậy, khi **chỉ cần kiểm tra blank**, gọi thẳng `s.isBlank()` sẽ rõ mục đích và tránh phải tạo/duyệt chuỗi trung gian để kiểm tra kết quả.

**Quan trọng:** `isBlank()`, `strip()` và `trim()` không phải công cụ **Unicode normalization** (NFC/NFKC), không xóa ký tự zero-width nói chung, không chuẩn hóa mọi ký tự mà người dùng cảm nhận là trống, cũng không tự dọn mọi định dạng Unicode.

## 5. Khi nào nên dùng `isBlank()` trong ứng dụng?

### 5.1. Kiểm tra trường nhập liệu bắt buộc

Nếu chính sách yêu cầu tên không được rỗng và không chỉ gồm Java whitespace:

~~~java
public static boolean hasVisibleRequiredText(String value) {
    return value != null && !value.isBlank();
}
~~~

Đây là **đoạn phương thức minh họa** để đặt trong một lớp Java; nó trả `false` đối với `null`, `""` và chuỗi chỉ gồm Java whitespace. Tên `hasVisibleRequiredText` ở đây mô tả ý định nghiệp vụ; **đừng hiểu là phép kiểm tra chính xác mọi ký tự có khả năng hiển thị**. Chẳng hạn `"\u200B"` khiến hàm trả `true` mặc dù không hiển thị nội dung rõ ràng.

Ở tầng xử lý yêu cầu, có thể chủ động phản hồi lỗi xác thực nếu giá trị thiếu; không nên âm thầm đồng nhất `null` và `""` khi API contract yêu cầu phân biệt chúng.

### 5.2. Dữ liệu có non-breaking spaces từ web, PDF, tài liệu văn phòng

Copy/paste từ HTML, tài liệu hoặc các nguồn có định dạng có thể chứa `U+00A0`. Khi đó:

~~~java
String copied = "\u00A0";
System.out.println(copied.isBlank()); // false
~~~

Đây **không phải lỗi** của `isBlank()`: nó đang tuân đúng hợp đồng. Nếu nghiệp vụ coi cả non-breaking spaces là «không có nội dung», cần **định nghĩa quy tắc khác** thay vì giả định `isBlank()` sẽ làm việc đó.

Một ví dụ chính sách bổ sung, sử dụng API vẫn có mặt trong Java 11:

~~~java
public class BlankPolicyDemo {
    public static boolean onlyJavaWhitespaceOrUnicodeSeparators(String value) {
        return value.codePoints().allMatch(cp ->
                Character.isWhitespace(cp) || Character.isSpaceChar(cp));
    }

    public static void main(String[] args) {
        System.out.println(onlyJavaWhitespaceOrUnicodeSeparators("\u00A0\u2007\u202F"));
        System.out.println(onlyJavaWhitespaceOrUnicodeSeparators("\t\u2003"));
        System.out.println(onlyJavaWhitespaceOrUnicodeSeparators("\u200B"));
    }
}
~~~

Lưu trong tệp **BlankPolicyDemo.java**, chạy:

~~~bash
javac --release 11 BlankPolicyDemo.java
java BlankPolicyDemo
~~~

Đầu ra:

~~~text
true
true
false
~~~

Hàm này coi khoảng trắng Java **hoặc** các nhóm Unicode `SPACE_SEPARATOR`/`LINE_SEPARATOR`/`PARAGRAPH_SEPARATOR` là blank, vì vậy nhận thêm ba non-breaking spaces mà `isBlank()` loại trừ. Nó **không phải** là phép triển khai chính xác thuộc tính Unicode `White_Space` của tiêu chuẩn Unicode; ví dụ `U+0085` vẫn không thuộc hai phép kiểm tra trên.

Hàm cũng giả định `value != null` (giống phương thức instance `isBlank()`). Chỉ nên dùng khi có **yêu cầu nghiệp vụ** rõ ràng. Đối với dữ liệu tên riêng, mã nhận dạng, văn bản đa ngôn ngữ hoặc ký tự zero-width có vai trò ngôn ngữ, đừng tự xóa hoặc gộp mã ký tự nếu chưa xác định chính sách và hậu quả.

### 5.3. Khi cần kiểm tra chính xác Unicode `White_Space`

Nếu một giao thức, định dạng dữ liệu hoặc chuẩn trao đổi yêu cầu đúng thuộc tính **Unicode White_Space** (thay vì «khoảng trắng theo Java»), hãy nêu rõ **phiên bản Unicode** và bộ thuộc tính áp dụng. `Character.isWhitespace`, `Character.isSpaceChar` và biểu thức chính sách ở mục 5.2 không tự động thay thế được bảng thuộc tính chuẩn đó.

Tương tự, biểu thức chính quy `\s` và lựa chọn cờ Unicode trong regex Java có thể sử dụng những quy tắc khác tùy cấu hình; không nên suy ra `split`, `matches`, `strip` và `isBlank` có cùng một tập ký tự chỉ vì đều nhắc đến *whitespace*. Hãy kiểm thử cụ thể các code point đầu vào quan trọng.

## 6. Các lỗi thường gặp và cách phòng tránh

1. **Dùng `isEmpty()` để chặn nhập toàn dấu cách:** `"   ".isEmpty()` là `false`. Nếu muốn chặn chuỗi chỉ gồm Java whitespace, dùng `isBlank()` sau khi quyết định chính sách `null`.
2. **Cho rằng mọi dấu cách Unicode đều làm `isBlank()` thành `true`:** `U+00A0`, `U+2007` và `U+202F` là ngoại lệ được Javadoc nêu rõ.
3. **Dựa vào cảm giác nhìn thấy trên giao diện:** `U+200B` và một số ký tự định dạng có thể vô hình nhưng vẫn khiến `isBlank()` là `false`. Phân tích dữ liệu bằng code point khi cần gỡ lỗi.
4. **Dùng `trim().isEmpty()` như bản thay thế `isBlank()`:** định nghĩa loại bỏ ký tự khác nhau; thử `U+2003` và `U+0000` sẽ thấy sự khác biệt.
5. **Bỏ sót `null`:** gọi `null.isBlank()` không hợp lệ và sẽ ném `NullPointerException` qua biến tham chiếu `null`. Chọn chính sách phân biệt dữ liệu thiếu, chuỗi rỗng và chuỗi chỉ gồm khoảng trắng.
6. **Viết vòng lặp theo `char` rồi gán là «kiểm tra mọi Unicode code point»:** `String` lưu UTF-16, nên cần hiểu surrogate pair. Ưu tiên `String.isBlank()` cho quy tắc chuẩn của Java hoặc `codePoints()` khi thật sự cần chính sách riêng.
7. **Tự động xóa mọi ký tự trông không hiển thị:** việc xóa `ZERO WIDTH`, dấu kết hợp hoặc ký tự định dạng có thể làm thay đổi văn bản hợp lệ. Hãy xác định yêu cầu của trường dữ liệu trước khi chuẩn hóa.

## 7. Câu hỏi tự đánh giá

**Câu 1.** `" \t\u2003".isBlank()` trả về gì?

**Đáp án:** `true`, vì SPACE, TAB và EM SPACE đều là `Character.isWhitespace`.

**Câu 2.** Vì sao `"\u00A0".isBlank()` là `false` nhưng `Character.isSpaceChar(0x00A0)` là `true`?

**Đáp án:** NO-BREAK SPACE là ký tự phân cách thuộc nhóm `SPACE_SEPARATOR`, nên `isSpaceChar` nhận diện. `isWhitespace` cố ý loại trừ ba non-breaking spaces, trong đó có `U+00A0`, và `String.isBlank()` dựa vào `isWhitespace`.

**Câu 3.** `"\u2003".trim().isEmpty()` và `"\u2003".strip().isEmpty()` khác nhau thế nào?

**Đáp án:** `false` và `true`. `trim` chỉ bỏ mã ký tự `<= U+0020` ở hai đầu, còn `strip` sử dụng `Character.isWhitespace` nên bỏ được `U+2003`.

**Câu 4.** Trường «họ tên» yêu cầu chặn cả một chuỗi chỉ chứa `U+00A0`. Chỉ gọi `isBlank()` có đủ không?

**Đáp án:** Không. Phải đưa điều kiện bổ sung vào quy tắc nhập liệu, ví dụ xét cả `Character.isSpaceChar` nếu phù hợp. Kiểm thử bằng code point thật và làm rõ tác động lên những văn bản hợp lệ.

**Câu 5.** Chuỗi `""` có cần một ký tự whitespace để `isBlank()` trả `true` không?

**Đáp án:** Không. Javadoc nêu rõ chuỗi rỗng cũng là blank.

## Tóm tắt kiến thức phải nhớ

- `String.isBlank()` xuất hiện từ **Java 11**, vẫn là API được hỗ trợ trong JDK hiện hành, trả `true` khi chuỗi rỗng hoặc toàn bộ Unicode code point là **Java whitespace**.
- Định nghĩa chuẩn để tra cứu: **`Character.isWhitespace(int)`**. Nó khác **`Character.isSpaceChar(int)`** và cũng không hoàn toàn đồng nhất với thuộc tính **Unicode White_Space**.
- `U+00A0`, `U+2007`, `U+202F` không được `isBlank()` coi là blank; `U+200B` cũng không phải Java whitespace.
- `isEmpty()` kiểm tra độ dài bằng 0; `trim()` và `strip()` trả chuỗi sau khi loại bỏ ký tự theo **hai quy tắc khác nhau**. `isBlank()` chỉ trả boolean.
- Với đầu vào thực tế, phải xác định rõ chính sách `null` và các ký tự khoảng trắng đặc biệt; dùng bảng code point, ví dụ chạy được và Javadoc của phiên bản Java cần hỗ trợ để xác nhận.

## Tài liệu tham khảo chính thức

1. [Java SE 11 — `String.isBlank()`, `isEmpty()`, `strip()`, `trim()`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html)
2. [Java SE 11 — `Character.isWhitespace(int)` và `Character.isSpaceChar(int)`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html)
3. [Java SE 27 — `Character` (đối chiếu hành vi còn áp dụng trên JDK hiện hành)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html)
4. [Unicode Character Database — Unicode Standard](https://www.unicode.org/ucd/)
