# Character.isWhitespace và giới hạn với khoảng trắng Unicode trong Java

Các chuỗi `" "`, `"\t"`, `"\u2003"` và `"\u00A0"` có thể đều trông giống khoảng trắng, nhưng Java **không coi chúng giống nhau trong mọi API**. Khi cần kiểm tra chuỗi rỗng về mặt nội dung, xóa khoảng trắng đầu/cuối hay chuẩn hóa văn bản đa ngôn ngữ, cần hiểu chính xác `Character.isWhitespace()`, phân biệt nó với `Character.isSpaceChar()` và tập **Unicode White_Space**.

Điểm quan trọng nhất của bài:

> **`Character.isWhitespace()` không nhận diện mọi ký tự thuộc Unicode White_Space.** Đặc biệt, các khoảng trắng không ngắt dòng như NO-BREAK SPACE (`U+00A0`), FIGURE SPACE (`U+2007`) và NARROW NO-BREAK SPACE (`U+202F`) được `Character.isSpaceChar()` nhận diện nhưng **không** được `Character.isWhitespace()` nhận diện. Vì `String.isBlank()` và `String.strip()` dựa trên định nghĩa whitespace của Java, chúng cũng có giới hạn tương ứng.

## 1. Ba khái niệm không thể dùng thay nhau

| Khái niệm/API | Kiểm tra điều gì? | Điểm cần lưu ý |
| --- | --- | --- |
| `Character.isWhitespace(int codePoint)` | Theo quy tắc “Java whitespace” trong API `Character` | Có các dấu phân cách Unicode nhất định và ký tự điều khiển như tab/newline, nhưng **loại trừ ba khoảng trắng không ngắt dòng** nêu trên |
| `Character.isSpaceChar(int codePoint)` | Unicode category `SPACE_SEPARATOR` (`Zs`), `LINE_SEPARATOR` (`Zl`), `PARAGRAPH_SEPARATOR` (`Zp`) | Có thể nhận diện khoảng trắng không ngắt dòng nhưng **không** nhận diện tab hay newline là “space character” |
| Unicode binary property `White_Space` | Thuộc tính Unicode dùng trong nhiều thuật toán phân loại và regex Unicode | Bao gồm những ký tự như NBSP và NEXT LINE (`U+0085`); cũng khác với `isWhitespace`/`isSpaceChar` riêng lẻ |

`Character.isWhitespace()` có hai overload chính:

~~~java
Character.isWhitespace(char ch);
Character.isWhitespace(int codePoint);
~~~

Đây là **chữ ký phương thức minh họa**, không phải chương trình Java độc lập. Khi dữ liệu là Unicode code point kiểu `int`, ưu tiên overload nhận `int`. Overload nhận `char` chỉ xét một **UTF-16 code unit**; nếu nhận một phần của surrogate pair, nó không phải toàn bộ code point. Với các ký tự whitespace thường gặp, chúng nằm trong BMP, nhưng thói quen duyệt code point giúp tránh lỗi khi mở rộng xử lý Unicode.

### Quy tắc Character.isWhitespace(int)

Một code point được coi là “Java whitespace” khi nó thuộc các nhóm:

1. Unicode `SPACE_SEPARATOR`, `LINE_SEPARATOR` hoặc `PARAGRAPH_SEPARATOR`, **trừ** ba ký tự `U+00A0`, `U+2007`, `U+202F`.
2. Ký tự điều khiển `U+0009` (tab), `U+000A` (line feed), `U+000B` (vertical tab), `U+000C` (form feed), `U+000D` (carriage return).
3. Ký tự điều khiển `U+001C`, `U+001D`, `U+001E`, `U+001F`.

Đây là **định nghĩa cụ thể của Java**, không phải một lời hứa rằng mọi thứ trông trống trên màn hình, mọi ký tự “invisible”, hay mọi thành viên của Unicode White_Space sẽ trả về `true`. Phân loại Unicode có thể thay đổi khi cập nhật dữ liệu Unicode của JDK; mã nguồn nên căn cứ vào hợp đồng API và phiên bản nền tảng đang chạy.

## 2. Bảng so sánh các code point quan trọng

| Code point | Tên hoặc ý nghĩa | `isWhitespace` | `isSpaceChar` | Lý do/ghi chú |
| --- | --- | :---: | :---: | --- |
| `U+0009` | CHARACTER TABULATION (tab) | **true** | false | Ký tự điều khiển được Java coi là whitespace |
| `U+000A` | LINE FEED | **true** | false | Ký tự xuống dòng |
| `U+001C` | FILE SEPARATOR | **true** | false | Java đặc biệt đưa vào nhóm whitespace |
| `U+0020` | SPACE thông thường | **true** | **true** | Khoảng trắng ASCII |
| `U+00A0` | NO-BREAK SPACE (NBSP) | **false** | **true** | Khoảng trắng không ngắt dòng; phản ví dụ quan trọng |
| `U+1680` | OGHAM SPACE MARK | **true** | **true** | Dấu cách Unicode |
| `U+2003` | EM SPACE | **true** | **true** | Khoảng trắng rộng trong typography |
| `U+2007` | FIGURE SPACE | **false** | **true** | Khoảng trắng không ngắt dòng |
| `U+2028` | LINE SEPARATOR | **true** | **true** | Loại `Zl` |
| `U+2029` | PARAGRAPH SEPARATOR | **true** | **true** | Loại `Zp` |
| `U+202F` | NARROW NO-BREAK SPACE | **false** | **true** | Khoảng trắng hẹp không ngắt dòng |
| `U+205F` | MEDIUM MATHEMATICAL SPACE | **true** | **true** | Khoảng trắng Unicode |
| `U+3000` | IDEOGRAPHIC SPACE | **true** | **true** | Dùng trong một số ngữ cảnh chữ Đông Á |
| `U+0085` | NEXT LINE (NEL) | **false** | false | Thuộc Unicode White_Space, nhưng **không** được hai API này nhận diện |
| `U+200B` | ZERO WIDTH SPACE | **false** | false | Tên có chữ “SPACE” nhưng **không** thuộc Unicode White_Space |
| `U+FEFF` | ZERO WIDTH NO-BREAK SPACE / BOM | **false** | false | Thường gặp trong xử lý BOM; không phải whitespace theo hai API |

Bảng trên được mô tả cho Java hiện đại (ví dụ JDK 17+). Điểm phân biệt đáng nhớ:

- **NBSP**, **FIGURE SPACE** và **NARROW NO-BREAK SPACE**: `isSpaceChar == true` nhưng `isWhitespace == false`.
- **Tab** và **line feed**: `isWhitespace == true` nhưng `isSpaceChar == false`.
- **NEXT LINE U+0085**: Unicode White_Space nhận diện, nhưng cả `isWhitespace` và `isSpaceChar` đều `false`.
- **ZERO WIDTH SPACE U+200B**: vô hình trong nhiều môi trường, nhưng **không** thuộc Unicode White_Space; đừng tự động coi mọi ký tự vô hình là dấu cách.

Điều này giải thích vì sao phép kiểm tra `Character.isWhitespace(cp) || Character.isSpaceChar(cp)` có thể bao phủ nhiều dấu cách hơn từng API riêng, nhưng **vẫn không tương đương với toàn bộ thuộc tính Unicode White_Space** (vì thiếu `U+0085`).

## 3. Ảnh hưởng tới String.isBlank(), strip() và trim()

Java có nhiều phương thức tên gần giống nhưng tiêu chí khác nhau:

| Phương thức | Quy tắc | Tác động với NBSP `U+00A0` |
| --- | --- | --- |
| `String.isEmpty()` | Chỉ `length() == 0` | `"\u00A0".isEmpty()` là `false` |
| `String.isBlank()` (Java 11+) | Rỗng hoặc chỉ có code point được Java coi là whitespace | `"\u00A0".isBlank()` là `false` |
| `String.strip()` (Java 11+) | Bỏ whitespace theo định nghĩa `Character.isWhitespace` ở **đầu và cuối** chuỗi | Không bỏ NBSP ở đầu/cuối |
| `String.stripLeading()` | Chỉ bỏ Java whitespace ở đầu chuỗi | Không bỏ NBSP đầu |
| `String.stripTrailing()` | Chỉ bỏ Java whitespace ở cuối chuỗi | Không bỏ NBSP cuối |
| `String.trim()` | Bỏ các `char` ở hai đầu có giá trị **không vượt `U+0020`** | Không bỏ NBSP; đồng thời không bỏ EM SPACE `U+2003` |

Một số hệ quả:

1. `"".isEmpty()` và `"".isBlank()` đều `true`; nhưng `" \t".isEmpty()` là `false` trong khi `" \t".isBlank()` là `true`.
2. `"\u2003".isBlank()` là `true` vì EM SPACE được `Character.isWhitespace` nhận diện.
3. `"\u00A0".isBlank()` là `false` dù NBSP thường hiển thị giống một chỗ trống.
4. `"\u200B".isBlank()` là `false`: ZERO WIDTH SPACE không tự động là Java whitespace.
5. `trim()` là phép cắt theo ngưỡng code unit lịch sử, khác với `strip()`. Vì vậy `trim()` cũng không phải bộ lọc “toàn bộ whitespace Unicode”.

**Không dùng `strip().isEmpty()` với kỳ vọng xóa mọi loại khoảng trắng Unicode.** Với chuỗi chỉ chứa NBSP, kết quả `strip()` vẫn chứa NBSP và `isEmpty()` là `false`; điều này phù hợp với `isBlank()` của Java.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu đoạn mã sau trong tệp **JavaWhitespaceDemo.java**:

~~~java
public class JavaWhitespaceDemo {
    private static void inspect(int codePoint) {
        String text = new String(Character.toChars(codePoint));
        System.out.printf(
                "U+%04X whitespace=%s spaceChar=%s blank=%s%n",
                codePoint,
                Character.isWhitespace(codePoint),
                Character.isSpaceChar(codePoint),
                text.isBlank());
    }

    public static void main(String[] args) {
        inspect(0x0020); // SPACE
        inspect(0x0009); // TAB
        inspect(0x00A0); // NO-BREAK SPACE
        inspect(0x2003); // EM SPACE
        inspect(0x2007); // FIGURE SPACE
        inspect(0x202F); // NARROW NO-BREAK SPACE
        inspect(0x0085); // NEXT LINE
        inspect(0x200B); // ZERO WIDTH SPACE
        inspect(0x3000); // IDEOGRAPHIC SPACE

        String nbsp = "\u00A0X\u00A0";
        String emSpace = "\u2003X\u2003";

        System.out.println("NBSP trim length = " + nbsp.trim().length());
        System.out.println("NBSP strip length = " + nbsp.strip().length());
        System.out.println("EM SPACE trim length = "
                + emSpace.trim().length());
        System.out.println("EM SPACE strip length = "
                + emSpace.strip().length());
        System.out.println("Only tab isBlank = " + "\t".isBlank());
        System.out.println("Only NBSP isBlank = " + "\u00A0".isBlank());

        System.out.println("NBSP Unicode-regex whitespace = "
                + "\u00A0".matches("(?U)\\s"));
        System.out.println("NEL Unicode-regex whitespace = "
                + "\u0085".matches("(?U)\\s"));
        System.out.println("ZWSP Unicode-regex whitespace = "
                + "\u200B".matches("(?U)\\s"));

        String unicodeStripped =
                nbsp.replaceAll("(?U)\\A\\s+|\\s+\\z", "");
        System.out.println("Unicode regex strip result = ["
                + unicodeStripped + "]");
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac -encoding UTF-8 JavaWhitespaceDemo.java
java JavaWhitespaceDemo
~~~

**Stdout:**

~~~text
U+0020 whitespace=true spaceChar=true blank=true
U+0009 whitespace=true spaceChar=false blank=true
U+00A0 whitespace=false spaceChar=true blank=false
U+2003 whitespace=true spaceChar=true blank=true
U+2007 whitespace=false spaceChar=true blank=false
U+202F whitespace=false spaceChar=true blank=false
U+0085 whitespace=false spaceChar=false blank=false
U+200B whitespace=false spaceChar=false blank=false
U+3000 whitespace=true spaceChar=true blank=true
NBSP trim length = 3
NBSP strip length = 3
EM SPACE trim length = 3
EM SPACE strip length = 1
Only tab isBlank = true
Only NBSP isBlank = false
NBSP Unicode-regex whitespace = true
NEL Unicode-regex whitespace = true
ZWSP Unicode-regex whitespace = false
Unicode regex strip result = [X]
~~~

**Giải thích:**

- NBSP không được coi là Java whitespace nên cả `trim()` lẫn `strip()` đều giữ nguyên hai ký tự NBSP hai bên `X`; chiều dài vẫn bằng 3.
- EM SPACE vượt ngưỡng `U+0020` của `trim()` nên `trim()` không loại bỏ; `strip()` nhận diện theo `isWhitespace()` nên trả về `"X"` có độ dài 1.
- Regex `(?U)\\s` bật chế độ `UNICODE_CHARACTER_CLASS`, khi đó `\s` dùng định nghĩa whitespace theo Unicode và khớp cả NBSP lẫn NEXT LINE. Nó không khớp ZERO WIDTH SPACE vì ký tự đó không thuộc Unicode White_Space.
- Trong biểu thức `"(?U)\\A\\s+|\\s+\\z"`, `\A` và `\z` neo tại đầu và cuối toàn bộ chuỗi; hai nhánh thay thế loại các khoảng Unicode White_Space liên tiếp ở **đầu hoặc cuối**, giữ nội dung bên trong. Đây là chính sách khác với `String.strip()`.

Các ký tự `\u00A0` và `\u2003` trong Java source được viết bằng escape Unicode để bài học dễ nhìn. Khi xuất ra terminal, không cần in trực tiếp khoảng trắng vô hình để quan sát vì các giá trị Boolean và chiều dài đã cho thấy sự khác biệt.

## 5. Regex \s cũng có hai chế độ đáng chú ý

Trong Java regex, `\s` không nên được hiểu máy móc là “toàn bộ dấu cách Unicode” trong mọi cấu hình.

**Chế độ mặc định** (không bật `UNICODE_CHARACTER_CLASS`): `\s` có tập ký tự whitespace truyền thống như SPACE, TAB, LINE FEED, VERTICAL TAB, FORM FEED và CARRIAGE RETURN. Điều đó không bao gồm mọi khoảng trắng Unicode.

**Chế độ Unicode**, dùng cờ `Pattern.UNICODE_CHARACTER_CLASS` hoặc cờ nội tuyến `(?U)`: `\s` sử dụng cách phân loại Unicode cho whitespace và nhận ra thêm NBSP, NARROW NO-BREAK SPACE, FIGURE SPACE, NEXT LINE cùng các khoảng trắng Unicode khác.

Ví dụ đoạn mã sau **đặt bên trong một phương thức**:

~~~java
String nbsp = "\u00A0";
System.out.println(nbsp.matches("\\s"));     // false
System.out.println(nbsp.matches("(?U)\\s")); // true
~~~

Nếu muốn regex có cờ tường minh ở mức đối tượng:

~~~java
java.util.regex.Pattern unicodeSpaces =
        java.util.regex.Pattern.compile(
                "\\s+",
                java.util.regex.Pattern.UNICODE_CHARACTER_CLASS);
System.out.println(unicodeSpaces.matcher("\u00A0").matches()); // true
~~~

Hai đoạn trên là **mã minh họa**, không phải chương trình độc lập. Với tác vụ phức tạp hoặc xử lý nhiều chuỗi, có thể biên dịch `Pattern` một lần và dùng lại. Chọn regex Unicode khi nghiệp vụ yêu cầu Unicode White_Space, thay vì ngầm đổi quy tắc toàn ứng dụng.

**Cảnh báo về mục tiêu:** Thuộc tính White_Space của Unicode vẫn **không** phải “mọi ký tự vô hình”. Chẳng hạn ZERO WIDTH SPACE (`U+200B`), ZERO WIDTH JOINER (`U+200D`), BOM/`U+FEFF` không được phép tùy tiện loại bỏ như khoảng trắng thông thường. Một số ký tự này có tác dụng định dạng văn bản, kết hợp emoji hoặc thông tin tệp.

## 6. Làm thế nào nếu muốn loại bỏ cả NBSP?

Trước khi viết hàm loại khoảng trắng, hãy xác định **định nghĩa đầu vào** của ứng dụng:

- Với một trường dữ liệu chỉ cần theo quy tắc whitespace của Java, `String.isBlank()` và `strip()` thường đủ rõ ràng.
- Với dữ liệu web, tài liệu văn bản hoặc CSV có thể chứa NBSP/NNBSP, hãy quy định rõ có coi chúng là khoảng trắng cần loại không. Nếu muốn **Unicode White_Space** theo regex Java, có thể dùng `(?U)\\s`.
- Nếu mục tiêu là bảo toàn khoảng trắng không ngắt dòng trong văn bản hiển thị (ví dụ đơn vị số, tên riêng có định dạng), **không** nên xóa NBSP chỉ vì nó trông như space. NBSP có ý nghĩa cấm ngắt dòng ở vị trí đó.
- Nếu ứng dụng cần xử lý Unicode theo một phiên bản chuẩn xác tuyệt đối giữa nhiều môi trường, hãy quản lý phiên bản Unicode/JDK hoặc thư viện phân loại phù hợp; không mặc định mọi JDK luôn có cùng bảng thuộc tính cho mã mới.

### Ví dụ hàm cắt Unicode White_Space ở hai đầu

~~~java
static String stripUnicodeWhiteSpace(String input) {
    java.util.Objects.requireNonNull(input, "input");
    return input.replaceAll("(?U)\\A\\s+|\\s+\\z", "");
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một lớp Java. Hàm cắt theo chính sách Unicode regex, có thể bỏ NBSP và NEXT LINE hai bên, nhưng không có ý định xóa mọi ký tự format/zero-width. Nó không thay thế `strip()` một cách mặc định cho mọi ứng dụng: hai hàm có **hợp đồng khác nhau**.

Nếu muốn phát hiện “toàn bộ chuỗi chỉ là Unicode White_Space” theo chính sách này, có thể dùng:

~~~java
static boolean isUnicodeWhiteSpaceOnly(String input) {
    java.util.Objects.requireNonNull(input, "input");
    return input.isEmpty() || input.matches("(?U)\\s+");
}
~~~

Đây là phương thức minh họa; với chuỗi rỗng trả về `true` tương tự `String.isBlank()`. Mẫu `(?U)\\s+` yêu cầu **một hoặc nhiều** code point thuộc Unicode White_Space, còn điều kiện `isEmpty()` xử lý riêng chuỗi rỗng. Nếu yêu cầu tối ưu cho nhiều lần gọi, dùng `Pattern` đã biên dịch thay vì tạo regex cho mỗi lời gọi.

### Trường hợp đặc biệt: xử lý dữ liệu “trông trống”

Một ô dữ liệu từ web chứa NBSP có thể **không rỗng theo `isBlank()`**; đây là điều dễ gây lỗi khi kiểm tra đầu vào. Nhưng một mã zero-width như `U+200B` còn có thể vô hình mà **không thuộc cả Java whitespace lẫn Unicode White_Space**. Do đó, câu “ô nhập trông trống” có thể cần **một chính sách riêng** về ký tự format, dấu điều khiển, chuẩn hóa và an toàn dữ liệu. Đừng âm thầm áp dụng `replaceAll("\\s+", "")` rồi cho rằng đã làm sạch mọi thứ.

Ví dụ, biến đổi `replaceAll("(?U)\\s+", " ")` gom các nhóm Unicode White_Space thành một dấu cách ASCII và có thể **thay đổi ý nghĩa trình bày** (mất NBSP ngăn ngắt dòng, mất các dấu xuống dòng). Nếu ứng dụng cần giữ cấu trúc đoạn văn hay layout, quy tắc ấy quá mạnh. Nên xác định rõ ngữ cảnh dữ liệu trước khi chọn bước chuẩn hóa.

## 7. UTF-16 và overload char/int: khi duyệt Unicode

Vì `String` đánh chỉ số theo UTF-16, một code point ngoài BMP có thể cần hai giá trị `char`. Khi kiểm tra từng Unicode code point nói chung, dùng:

~~~java
String text = "A😀\u00A0B";
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    System.out.printf("U+%04X whitespace=%s%n",
            cp, Character.isWhitespace(cp));
    i += Character.charCount(cp);
}
~~~

Đây là **đoạn mã đặt trong một phương thức Java**, không phải lớp độc lập. Kết quả:

~~~text
U+0041 whitespace=false
U+1F600 whitespace=false
U+00A0 whitespace=false
U+0042 whitespace=false
~~~

Phép duyệt `codePointAt(i)` và tăng `Character.charCount(cp)` tránh lặp qua từng nửa surrogate của emoji. Với mỗi code point, hàm nhận `int` áp dụng tiêu chí Java whitespace. Vì vậy, dù xử lý Unicode bằng code point chính xác, NBSP **vẫn** bị `isWhitespace()` xem là `false`: đây là quyết định phân loại của API, không phải lỗi vì duyệt bằng UTF-16.

Để xử lý code point bằng Stream, có thể dùng `text.codePoints().allMatch(Character::isWhitespace)`, nhưng biểu thức này cũng dùng **đúng tiêu chí Java whitespace**, không tự mở rộng sang Unicode White_Space. Với chuỗi rỗng, `allMatch` cho `true` theo quy tắc của stream rỗng.

## 8. Những nhầm lẫn phổ biến

| Nhận định hoặc cách làm | Vấn đề | Điều nên làm |
| --- | --- | --- |
| “Unicode space thì `Character.isWhitespace` luôn `true`” | NBSP, FIGURE SPACE, NNBSP là phản ví dụ | Kiểm tra chính sách: Java whitespace, `isSpaceChar` hay Unicode White_Space |
| “`isWhitespace` và `isSpaceChar` là hai tên của một hàm” | Tab chỉ thuộc `isWhitespace`; NBSP chỉ thuộc `isSpaceChar` | Hiểu hai hợp đồng trước khi dùng |
| “`strip()` xóa mọi khoảng trắng mà mắt nhìn thấy” | `strip()` không xóa NBSP/NNBSP | Dùng quy tắc rõ ràng cho Unicode whitespace nếu cần |
| “`trim()` tương đương `strip()`” | `trim()` dựa trên ngưỡng `U+0020`, còn `strip()` dựa trên `isWhitespace` | Chọn theo phạm vi ký tự cần xử lý |
| “Chuỗi chứa NBSP luôn là `isBlank() == true`” | NBSP không phải Java whitespace | Kiểm tra riêng hoặc dùng Unicode regex khi nghiệp vụ yêu cầu |
| “Regex `\\s` luôn khớp mọi Unicode whitespace” | Chế độ mặc định khác chế độ Unicode | Chọn `(?U)\\s` hoặc `UNICODE_CHARACTER_CLASS` |
| “Ký tự zero-width nào cũng nên xóa” | Nhiều ký tự có vai trò format, emoji, BOM | Xác định chính sách xử lý ký tự vô hình |
| “Kết hợp `isWhitespace || isSpaceChar` đúng bằng Unicode White_Space” | Unicode White_Space còn có NEXT LINE `U+0085` | Dùng property/regex Unicode khi cần tập Unicode tương ứng |
| “`charAt()` luôn trả về một code point hoàn chỉnh” | Code point ngoài BMP có cặp surrogate | Dùng `codePointAt()` và bước nhảy theo `Character.charCount()` |
| “Một đoạn `String` toàn space sẽ luôn có `length() == 0` sau `strip()`” | Không đúng với NBSP, NNBSP, FIGURE SPACE | Kiểm thử dữ liệu thực tế, theo tiêu chí cụ thể |

## 9. Checklist thiết kế thao tác kiểm tra chuỗi trắng

1. **Xác định ý nghĩa của “trắng”:** hoàn toàn không có ký tự (`isEmpty`), chỉ Java whitespace (`isBlank`), Unicode White_Space, hay “không có ký tự hiển thị” theo tiêu chí của giao diện?
2. **Nhận diện nguồn dữ liệu:** bàn phím, HTML, bản sao từ tài liệu, tệp UTF-8/UTF-16, dữ liệu nhập từ đối tác; nguồn web và tài liệu thường có NBSP.
3. **Chọn đúng API:** `Character.isWhitespace` cho tiêu chí Java; `Character.isSpaceChar` cho các Unicode separator; regex Unicode White_Space khi cần bao gồm NBSP/NEL.
4. **Xác định phạm vi chuẩn hóa:** chỉ cắt đầu/cuối hay thay toàn bộ khoảng trắng bên trong? Giữ dòng mới và NBSP khi chúng có ý nghĩa.
5. **Kiểm tra chuỗi rỗng và `null`:** `"".isBlank()` trả `true`, còn gọi phương thức lên tham chiếu `null` sẽ ném `NullPointerException`.
6. **Viết test theo code point**, không dựa vào độ rộng hiển thị: `U+0020`, `U+0009`, `U+00A0`, `U+2003`, `U+2007`, `U+202F`, `U+0085`, `U+200B` và `U+FEFF`.
7. **Ghi rõ chính sách của ứng dụng** để người duy trì hiểu vì sao `strip()` hoặc Unicode regex được chọn, tránh tự ý thay đổi sau này.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Character.isWhitespace('\u00A0')` trả về `false`, dù NBSP trông giống dấu cách?

**Đáp án:** NBSP là khoảng trắng **không ngắt dòng**, thuộc nhóm separator nhưng được **loại trừ** khỏi tiêu chí Java whitespace. `Character.isSpaceChar('\u00A0')` vẫn trả về `true`.

**Câu 2.** `"\u2003".isBlank()` và `"\u00A0".isBlank()` trả về gì?

**Đáp án:** lần lượt là `true` và `false`: EM SPACE được `isWhitespace` nhận diện, còn NBSP bị loại trừ.

**Câu 3.** `"\u2003X\u2003".strip()` và `"\u2003X\u2003".trim()` khác nhau thế nào?

**Đáp án:** `strip()` trả `"X"`; `trim()` giữ nguyên hai EM SPACE vì code unit `U+2003` vượt ngưỡng `U+0020`.

**Câu 4.** Bật `(?U)` trong Java regex `\\s` có mục đích gì?

**Đáp án:** bật `UNICODE_CHARACTER_CLASS` để `\\s` dùng tập Unicode White_Space rộng hơn, bao gồm NBSP và NEXT LINE.

**Câu 5.** ZERO WIDTH SPACE `U+200B` có được xem là whitespace theo hai API Java trên hoặc theo Unicode White_Space không?

**Đáp án:** không. Ký tự có thể vô hình nhưng tên gọi/hình thức hiển thị không đủ để kết luận thuộc một tập whitespace.

**Câu 6.** Nếu ứng dụng cần bỏ khoảng Unicode White_Space đầu/cuối, dùng `String.strip()` có đáp ứng hoàn toàn không?

**Đáp án:** không. `strip()` dùng Java whitespace, nên giữ NBSP/NNBSP/FIGURE SPACE. Có thể dùng regex Unicode với `(?U)\\s` và neo đầu/cuối khi đó đúng yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): hợp đồng chính thức của `isWhitespace(char/int)` và `isSpaceChar(char/int)`.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `isBlank()`, `strip()`, `stripLeading()`, `stripTrailing()`, `trim()`, `codePoints()`.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\\s`, `UNICODE_CHARACTER_CLASS`, `(?U)` và Unicode properties.
- [Unicode Character Database — PropList.txt](https://www.unicode.org/Public/UCD/latest/ucd/PropList.txt): danh sách Unicode binary property `White_Space`; dữ liệu có thể khác theo phiên bản Unicode.
