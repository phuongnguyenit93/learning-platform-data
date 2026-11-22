# Chọn đơn vị chỉ số phù hợp trước khi duyệt hoặc cắt chuỗi trong Java

Khi duyệt hay cắt `String`, câu hỏi đầu tiên không phải “dùng `charAt()` hay `substring()`?” mà là **một vị trí trong yêu cầu nghiệp vụ đại diện cho đơn vị nào?** Java cung cấp chỉ số theo **UTF-16 code unit** (đơn vị mã), API xử lý **Unicode code point** (điểm mã), và công cụ phân đoạn văn bản theo **ký tự người dùng nhìn thấy** (grapheme cluster). Ba đơn vị này đôi khi có cùng độ dài với chữ ASCII, nhưng khác nhau với emoji, dấu kết hợp và nhiều hệ chữ viết.

Chọn sai đơn vị có thể khiến chương trình cắt đôi emoji, làm rơi dấu tiếng Việt, đếm sai độ dài hoặc đặt con trỏ ở một vị trí không phù hợp. Bài này tập trung vào cách xác định đúng đơn vị **trước khi duyệt hoặc cắt chuỗi**, sau đó chọn API tương ứng.

## 1. Ba đơn vị cần phân biệt

| Đơn vị | Ý nghĩa | API hoặc công cụ trong Java | Khi nào nên dùng |
| --- | --- | --- | --- |
| **UTF-16 code unit** | Một đơn vị mã 16 bit, tương ứng giá trị `char` | `length()`, `charAt()`, `substring()`, `toCharArray()`, `chars()` | Làm việc với các API chấp nhận chỉ số `String` của Java, ký tự ASCII hoặc dữ liệu đã định nghĩa theo `char` |
| **Unicode code point** | Một giá trị Unicode; có thể cần một hoặc hai code unit UTF-16 | `codePointAt()`, `codePointCount()`, `offsetByCodePoints()`, `codePoints()`, `Character.charCount()` | Duyệt các Unicode code point, nhận diện emoji/code point ngoài BMP, tính khoảng cắt theo số code point |
| **Grapheme cluster** | Cụm ký tự thường được người dùng cảm nhận như một ký tự hiển thị | Công cụ phân đoạn văn bản như `BreakIterator`; với yêu cầu đầy đủ UAX #29, cân nhắc ICU4J hoặc thư viện đã kiểm thử | Đặt con trỏ, xóa “một ký tự” trong giao diện, giới hạn số ký tự người dùng nhìn thấy, cắt nhãn hiển thị |

**Không có đơn vị chỉ số đúng cho mọi tình huống.** Nếu một API Java yêu cầu `beginIndex` của `substring()`, nó cần **UTF-16 offset**. Nếu yêu cầu là “lấy ba Unicode code point đầu”, phải chuyển vị trí theo code point thành UTF-16 offset rồi mới gọi `substring()`. Nếu là “xóa đúng một ký tự mà người dùng thấy”, code point cũng có thể quá nhỏ vì một cụm hiển thị có thể gồm nhiều code point.

Lưu ý thêm: **byte của UTF-8 không phải chỉ số `String`**. Vị trí byte trong tệp/luồng là đơn vị thứ tư, được tính sau khi mã hóa; không thể dùng trực tiếp làm `substring()` index.

## 2. Ví dụ nền tảng: cùng một chuỗi, ba cách đếm

Dùng chuỗi Java sau:

~~~java
String text = "A😀e\u0301B";
~~~

Trong đoạn mã, `e\u0301` là chữ `e` theo sau bởi dấu sắc kết hợp `U+0301`. Khi hiển thị, chúng thường trông như một chữ “é”, nhưng **đang là hai code point**. Chuỗi có cấu trúc:

| UTF-16 index | Phần tử `char` | Vai trò |
| ---: | --- | --- |
| 0 | `A` | Một code unit, một code point |
| 1 | `\uD83D` | High surrogate của 😀 |
| 2 | `\uDE00` | Low surrogate của 😀 |
| 3 | `e` | Code point chữ e |
| 4 | `\u0301` | Code point dấu sắc kết hợp |
| 5 | `B` | Một code unit, một code point |

Vì vậy:

- **6 UTF-16 code unit:** `text.length() == 6`.
- **5 Unicode code point:** A, 😀, e, dấu sắc kết hợp, B.
- **Thường 4 grapheme cluster:** A, 😀, e + dấu sắc, B (cách hiển thị và ranh giới cụm phải được xác định theo chuẩn phân đoạn tương ứng).

Emoji 😀 là code point `U+1F600`, nằm ngoài Basic Multilingual Plane (BMP), nên cần **hai code unit** UTF-16 (một surrogate pair). Trái lại, chữ `e` và dấu `U+0301` mỗi thứ chỉ cần một code unit nhưng kết hợp thành một cụm người đọc cảm nhận là một ký tự.

Trường hợp chữ ghép sẵn `"é"` (`U+00E9`) khác về dãy code point so với `"e\u0301"`. Hai chuỗi có thể trông giống nhau, nhưng độ dài Java và nội dung code point khác nhau. Unicode normalization, ví dụ NFC, có thể giúp xử lý một số dạng biểu diễn tương đương; normalization **không thay thế** việc xác định ranh giới grapheme cluster.

## 3. Nếu mục tiêu là chỉ số UTF-16: dùng charAt và substring

Các API thông dụng làm việc trực tiếp trên chỉ số **UTF-16 code unit**:

- `text.length()`: số đơn vị UTF-16, không mặc nhiên là số ký tự người dùng thấy.
- `text.charAt(index)`: trả về đúng **một `char`** tại vị trí `index`. Chỉ số hợp lệ từ `0` đến `length() - 1`.
- `text.substring(beginIndex, endIndex)`: lấy đoạn **[beginIndex, endIndex)**, gồm vị trí bắt đầu, không gồm vị trí kết thúc. `beginIndex == endIndex` hợp lệ nếu trong phạm vi và trả về chuỗi rỗng.
- `text.subSequence(begin, end)` cũng dùng đơn vị chỉ số UTF-16.
- `text.chars()` trả về `IntStream` chứa các giá trị UTF-16 `char` được mở rộng thành `int`; **khác** `codePoints()`.

Với ví dụ trên:

~~~java
String text = "A😀e\u0301B";
System.out.println(text.length());                  // 6
System.out.println(text.substring(1, 3).equals("😀")); // true
System.out.println(text.substring(1, 2).length());  // 1
System.out.println(
        Character.isHighSurrogate(text.substring(1, 2).charAt(0))); // true
~~~

Đây là **đoạn code minh họa đặt trong một phương thức**, không phải lớp Java độc lập. Kết quả lần lượt là `6`, `true`, `1`, `true`.

Vùng `[1, 3)` lấy cả high và low surrogate, nên giữ trọn emoji 😀. Vùng `[1, 2)` chỉ lấy **một nửa** của cặp surrogate. Java vẫn có thể tạo `String` chứa một surrogate lẻ, nhưng đó không còn là emoji hoàn chỉnh; khi mã hóa hoặc hiển thị có thể gặp ký tự thay thế. Tương tự, vùng `[3, 4)` lấy chữ e mà không lấy dấu sắc ở `[4, 5)`.

**Quy tắc:** chỉ số UTF-16 phù hợp khi hợp đồng API hoặc dữ liệu đã được quy định theo `char`. Khi cắt văn bản tự nhiên, hãy xác minh điểm bắt đầu/kết thúc **không chia đôi cặp surrogate** và, nếu quan trọng với giao diện, **không chia cụm ký tự hiển thị**.

## 4. Nếu mục tiêu là Unicode code point: duyệt theo codePointAt

Một Unicode code point ngoài BMP chiếm **hai** `char` UTF-16. Vì vậy, vòng lặp `for (int i = 0; i < text.length(); i++)` kết hợp `charAt(i)` là vòng lặp theo **code unit**, không phải theo code point.

Để duyệt các code point liên tiếp, dùng `codePointAt(offset)` và tăng offset bằng `Character.charCount(cp)`:

~~~java
String text = "A😀e\u0301B";

// Code bên trong phương thức Java:
for (int offset = 0; offset < text.length(); ) {
    int cp = text.codePointAt(offset);
    System.out.printf("U+%04X%n", cp);
    offset += Character.charCount(cp);
}
~~~

Kết quả:

~~~text
U+0041
U+1F600
U+0065
U+0301
U+0042
~~~

Tại vị trí của 😀, `codePointAt(1)` hợp nhất high và low surrogate thành `U+1F600`; `Character.charCount(0x1F600)` bằng `2` nên chỉ số nhảy từ 1 lên 3. Với A, e, dấu sắc, B, `charCount(cp)` bằng `1`.

**Quan trọng:** `codePointAt(index)` nhận **chỉ số UTF-16** chứ không phải “code point index”. Hàm trả về **code point bắt đầu tại offset đó** (nếu là high surrogate có low surrogate ngay sau); gọi với một chỉ số trỏ vào low surrogate có thể nhận riêng giá trị low surrogate. Vì vậy hãy luôn chuyển đổi offset đúng cách trước khi truy cập.

### Hai lựa chọn khác: codePoints và codePointCount

- `text.codePoints()` tạo `IntStream` duyệt code point. Dùng khi muốn `map`, `filter` hoặc xử lý stream mà không tự cập nhật UTF-16 offset.
- `text.codePointCount(beginIndex, endIndex)` đếm code point trong vùng có ranh giới vẫn là **UTF-16 offset**. Với chuỗi nguyên vẹn, `text.codePointCount(0, text.length())` cho số code point.
- `text.chars()` tạo stream các code unit, nên khi có emoji ngoài BMP, nó cho **hai phần tử** thay vì một.

Một `String` có thể chứa surrogate lẻ; các API code point của Java xử lý surrogate không ghép cặp như một giá trị riêng khi đếm/duyệt. Đừng giả định mọi chuỗi Java đang chứa dãy Unicode scalar value hợp lệ nếu dữ liệu đầu vào có thể lỗi.

## 5. Nếu muốn cắt theo số code point: chuyển sang UTF-16 offset

`substring()` **không có overload nhận chỉ số code point**. Phải chuyển từ vị trí theo code point sang UTF-16 offset bằng `offsetByCodePoints()`:

~~~java
String text = "A😀e\u0301B";
int begin = text.offsetByCodePoints(0, 1); // 1 code point sau đầu chuỗi
int end = text.offsetByCodePoints(begin, 1); // sau emoji, UTF-16 offset = 3
String emoji = text.substring(begin, end);
System.out.println(emoji.equals("😀")); // true
~~~

Giải thích: `offsetByCodePoints(index, codePointOffset)` nhận **UTF-16 index** và khoảng dịch chuyển tính bằng **code point**, trả về **UTF-16 index** mới. Cách tính này xử lý surrogate pair hợp lệ; nếu yêu cầu đi ra ngoài đoạn hợp lệ, phương thức ném `IndexOutOfBoundsException`.

Công thức chuyển hai ranh giới thường gặp:

~~~java
int utf16Start = text.offsetByCodePoints(0, startPointIndex);
int utf16End = text.offsetByCodePoints(utf16Start, pointCount);
String part = text.substring(utf16Start, utf16End);
~~~

Đây là **đoạn code minh họa**: `startPointIndex` và `pointCount` phải được kiểm tra hợp lệ trước. Giá trị `pointCount` là **số code point cần lấy**, khác với “chỉ số kết thúc”.

### Hàm tiện ích có kiểm tra phạm vi

~~~java
static String sliceByCodePoints(String text, int startPoint, int count) {
    java.util.Objects.requireNonNull(text, "text");
    int total = text.codePointCount(0, text.length());

    if (startPoint < 0 || count < 0 || startPoint > total - count) {
        throw new IndexOutOfBoundsException("Invalid code point range");
    }

    int begin = text.offsetByCodePoints(0, startPoint);
    int end = text.offsetByCodePoints(begin, count);
    return text.substring(begin, end);
}
~~~

Đây là **phương thức minh họa**, đặt trong một lớp Java. Kiểm tra `startPoint > total - count` giúp tránh dùng phép cộng `startPoint + count` có khả năng tràn `int`. Vùng trống ở điểm kết thúc `startPoint == total, count == 0` là hợp lệ. Nếu `count` âm hoặc chọn vượt số code point, hàm chủ động báo lỗi.

**Giới hạn của giải pháp:** nó giữ nguyên **code point**, nhưng có thể cắt giữa chữ e và dấu kết hợp nếu yêu cầu một code point. Khi cần bảo toàn một ký tự hiển thị, nên phân đoạn theo grapheme cluster.

## 6. Chương trình Java 17+ chạy độc lập

Tạo tệp **StringIndexUnitsDemo.java**:

~~~java
import java.util.Objects;

public class StringIndexUnitsDemo {
    static String sliceByCodePoints(String text, int startPoint, int count) {
        Objects.requireNonNull(text, "text");
        int total = text.codePointCount(0, text.length());
        if (startPoint < 0 || count < 0 || startPoint > total - count) {
            throw new IndexOutOfBoundsException("Invalid code point range");
        }
        int begin = text.offsetByCodePoints(0, startPoint);
        int end = text.offsetByCodePoints(begin, count);
        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        String text = "A😀e\u0301B";

        System.out.println("UTF-16 units = " + text.length());
        System.out.println("Code points = "
                + text.codePointCount(0, text.length()));
        System.out.println("index 1 is high surrogate = "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("substring(1, 2) keeps whole emoji = "
                + text.substring(1, 2).equals("😀"));
        System.out.println("substring(1, 3) keeps whole emoji = "
                + text.substring(1, 3).equals("😀"));

        String firstTwo = sliceByCodePoints(text, 0, 2);
        String emoji = sliceByCodePoints(text, 1, 1);
        String accentPair = sliceByCodePoints(text, 2, 2);

        System.out.println("firstTwo code points = "
                + firstTwo.codePointCount(0, firstTwo.length()));
        System.out.println("emoji UTF-16 units = " + emoji.length());
        System.out.println("accentPair code points = "
                + accentPair.codePointCount(0, accentPair.length()));
        System.out.println("accentPair UTF-16 units = " + accentPair.length());

        String onePoint = sliceByCodePoints(text, 2, 1);
        System.out.println("onePoint includes combining accent = "
                + onePoint.equals("e\u0301"));

        StringBuilder codePoints = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (codePoints.length() > 0) {
                codePoints.append(' ');
            }
            codePoints.append(String.format("U+%04X", cp));
        });
        System.out.println("Values = " + codePoints);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 StringIndexUnitsDemo.java
java StringIndexUnitsDemo
~~~

Kết quả:

~~~text
UTF-16 units = 6
Code points = 5
index 1 is high surrogate = true
substring(1, 2) keeps whole emoji = false
substring(1, 3) keeps whole emoji = true
firstTwo code points = 2
emoji UTF-16 units = 2
accentPair code points = 2
accentPair UTF-16 units = 2
onePoint includes combining accent = false
Values = U+0041 U+1F600 U+0065 U+0301 U+0042
~~~

**Diễn giải:** `substring(1, 2)` cắt mất low surrogate nên không giữ nguyên emoji; `substring(1, 3)` lấy trọn cặp. Hàm `sliceByCodePoints()` giúp chọn đủ emoji theo một code point nhưng, nếu chọn riêng code point e, **không tự kéo theo dấu sắc kết hợp** ở code point kế tiếp. Đây là bằng chứng rằng *cắt an toàn theo code point chưa đủ để cắt an toàn theo ký tự hiển thị*.

## 7. Nếu cần một ký tự mà người dùng nhìn thấy: grapheme cluster

Grapheme cluster là đơn vị phù hợp hơn khi ứng dụng cần:

- Xóa ký tự tại con trỏ trong ô nhập văn bản theo cách người dùng kỳ vọng.
- Giới hạn độ dài tên hiển thị theo số ký tự cảm nhận, thay vì `char` hoặc code point.
- Cắt nhãn hay lời nhắn mà không tách dấu kết hợp và các chuỗi emoji phức tạp.
- Di chuyển con trỏ qua các cụm ký tự trong văn bản đa ngôn ngữ.

Ví dụ những thứ có thể gồm **nhiều code point** nhưng tạo một cụm hiển thị: `e\u0301` (chữ và dấu), cờ tạo từ các *regional indicator*, emoji có bộ biến đổi tông da, hoặc chuỗi emoji có *zero-width joiner* (ZWJ). Chỉ số code point sẽ thấy từng thành phần; ranh giới của một ký tự hiển thị cần thêm quy tắc phân đoạn Unicode.

Java có `java.text.BreakIterator.getCharacterInstance(Locale)` để tìm ranh giới ký tự theo locale và phiên bản JDK. API trả về các **UTF-16 offset**, vì vậy dùng được trực tiếp với `substring()`. Tuy nhiên, hành vi phân đoạn với emoji ZWJ, cờ và các tình huống Unicode mới có thể phụ thuộc JDK/dữ liệu Unicode/locale. Khi yêu cầu **đầy đủ Extended Grapheme Cluster theo Unicode UAX #29** hoặc tương thích giao diện trên nhiều nền tảng, hãy kiểm thử các trường hợp thực tế và cân nhắc thư viện phân đoạn cập nhật như ICU4J.

### Cách sử dụng BreakIterator theo từng ranh giới

~~~java
import java.text.BreakIterator;
import java.util.Locale;

// Đoạn code bên trong phương thức Java:
String text = "Cafe\u0301!";
BreakIterator boundaries = BreakIterator.getCharacterInstance(Locale.ROOT);
boundaries.setText(text);

int start = boundaries.first();
for (int end = boundaries.next();
     end != BreakIterator.DONE;
     start = end, end = boundaries.next()) {
    String cluster = text.substring(start, end);
    System.out.println(cluster);
}
~~~

Đây là **đoạn mã minh họa**, không phải một chương trình độc lập. `BreakIterator` trả về các khoảng `[start, end)` theo **UTF-16 index** và `substring()` lấy đoạn tương ứng. Kết quả phân đoạn chi tiết được quyết định bởi phiên bản/cấu hình bộ phân đoạn; ứng dụng cần thử trên văn bản thực tế trước khi dùng để giới hạn hoặc biên tập nội dung.

**Không dùng “một `char` = một ký tự người dùng”.** Tương tự, không mặc định “một Unicode code point = một ký tự người dùng”. Với các cụm hiển thị phức tạp, đơn vị grapheme mới gần với kỳ vọng giao diện.

### Ba phép cắt minh họa cho cùng yêu cầu

Với `String text = "A😀e\u0301B";`:

| Yêu cầu thực sự | Đơn vị nên chọn | Cách tiếp cận |
| --- | --- | --- |
| Lấy `char` tại UTF-16 offset 1 | UTF-16 code unit | `text.charAt(1)` → high surrogate, **không phải emoji trọn vẹn** |
| Lấy Unicode code point thứ hai | Code point | Chuyển điểm thứ hai thành UTF-16 offset, `codePointAt(offset)` → `U+1F600` |
| Lấy cụm thứ ba theo cách hiển thị | Grapheme cluster | Phân đoạn thành các cụm A, 😀, e+dấu, B bằng thuật toán grapheme phù hợp, sau đó cắt theo ranh giới trả về |
| Lấy nội dung trong vùng UTF-16 `[3, 5)` | UTF-16 code unit | `text.substring(3, 5)` → e cộng dấu kết hợp, vẫn là hai code point |
| Lấy hai code point từ vị trí code point 2 | Code point | `sliceByCodePoints(text, 2, 2)` → e cộng dấu; đúng vì yêu cầu cụ thể là hai code point |

Trong bảng, “thứ hai”, “thứ ba” là cách đếm **từ 1** trong câu tự nhiên; API Java vẫn đếm offset **từ 0**. Phải thống nhất quy ước đầu vào trước khi viết code.

## 8. Cách chọn đơn vị theo mục tiêu thực tế

| Tình huống | Quyết định khuyến nghị | Lý do |
| --- | --- | --- |
| Đang nhận chỉ số từ `String.indexOf()` hoặc truyền vào `substring()` | Giữ **UTF-16 offset** | Các API trả/nhận vị trí theo cùng đơn vị; tránh trộn chỉ số |
| Duyệt từng `char` để xử lý dữ liệu ASCII hoặc định dạng giới hạn ASCII | **Code unit**, với giả định ASCII được kiểm tra | Mỗi ký tự ASCII chiếm một đơn vị UTF-16 |
| Đếm/duyệt các Unicode code point của văn bản | **Code point** | Một code point ngoài BMP có thể cần hai `char` |
| Lấy *n* code point đầu của chuỗi | **Code point** + `offsetByCodePoints()` | Chuyển sang UTF-16 offset an toàn rồi gọi `substring()` |
| Cắt theo “n ký tự người dùng nhìn thấy” | **Grapheme cluster** | Tránh chia dấu kết hợp, emoji ghép và nhiều cụm đa code point |
| Tính kích thước tệp hoặc giới hạn số byte trên giao thức | **Byte theo charset xác định** | `length()` không tính số byte UTF-8 |
| Cắt chuỗi theo độ rộng hiển thị trong terminal | Cần thêm **độ rộng glyph/cell** | Số grapheme cũng không nhất thiết bằng số ô hiển thị |
| Tìm ranh giới từ/câu | Phân đoạn **từ/câu**, không chỉ grapheme | Ranh giới từ/câu có quy tắc riêng |

**Ví dụ quan trọng với `indexOf()`:** nếu `int p = text.indexOf("B");`, giá trị `p` là UTF-16 offset; có thể gọi ngay `text.substring(0, p)`. Không coi `p` là số code point rồi đưa vào `offsetByCodePoints(0, p)`, vì khi có emoji, việc “chuyển lần nữa” dẫn đến vị trí sai hoặc ngoại lệ.

## 9. Những lỗi phổ biến

1. **Duyệt `charAt(i)` rồi coi mỗi lần là một Unicode ký tự.** Với emoji ngoài BMP, mã nguồn xử lý hai surrogate riêng lẻ. Nếu cần code point, dùng `codePointAt()` và tăng `i` theo `Character.charCount(cp)`, hoặc dùng `codePoints()`.
2. **Dùng `substring(0, n)` để lấy n code point.** `n` trong lời gọi là UTF-16 offset. Hãy đổi qua `offsetByCodePoints()`.
3. **Đếm bằng `length()` rồi áp dụng quy định “tối đa 10 ký tự hiển thị”.** Quy định UI thường đòi hỏi grapheme cluster và đôi lúc chính sách sản phẩm cụ thể; `length()` chỉ đếm đơn vị mã.
4. **Nhận code point offset rồi truyền thẳng vào `charAt()`.** `charAt()` luôn cần UTF-16 index.
5. **Giả sử code point luôn tương ứng một glyph.** Dấu kết hợp, ZWJ sequence, variation selector, cờ và emoji bổ sung có thể tạo nhiều code point trên một cụm hiển thị.
6. **Dùng `codePoints()` để cắt văn bản hiển thị mà không kiểm tra cụm.** Không phá surrogate pair nhưng vẫn có thể tách dấu hoặc thành phần emoji.
7. **Giả sử `BreakIterator` ở mọi JDK đều cho cùng ranh giới với emoji phức tạp.** Cần kiểm thử phiên bản, locale và bộ dữ liệu Unicode cho yêu cầu cụ thể.
8. **Trộn vị trí byte của UTF-8 với chỉ số `String`.** Byte offset phải giải mã/chuyển theo charset; không thể làm `substring()` trực tiếp.
9. **Quên kiểm tra ranh giới và số âm.** Với `charAt()`, chỉ số âm hoặc bằng `length()` gây `StringIndexOutOfBoundsException`; `substring()` cũng báo lỗi cho vùng ngoài phạm vi hoặc `begin > end`. Với hàm cắt theo code point, cần kiểm tra số code point thực.
10. **Quên rằng `String` có thể chứa surrogate lẻ.** Các API Java vẫn có thể quan sát giá trị này, nên khi nhận văn bản từ nguồn không tin cậy phải kiểm tra hợp lệ nếu yêu cầu dữ liệu Unicode chuẩn.

## 10. Checklist trước khi viết vòng lặp hoặc substring

Hãy tự trả lời lần lượt:

1. **Yêu cầu là gì?** Ký tự Java `char`, Unicode code point, ký tự giao diện hay byte của tệp?
2. **Nguồn chỉ số là API nào?** Nếu đến từ `indexOf()`, `Matcher.start()`, `BreakIterator` hoặc `substring()`, kiểm tra hợp đồng chỉ số UTF-16; nếu là con số trong yêu cầu nghiệp vụ, xác định đơn vị được đếm.
3. **Có Unicode ngoài BMP không?** Hãy thử một emoji như 😀 để phát hiện vòng lặp đang cắt surrogate pair.
4. **Có dấu kết hợp hoặc emoji ZWJ không?** Thử `e\u0301` và các emoji ghép để kiểm tra xem code point có đủ hay cần grapheme cluster.
5. **Ranh giới có hợp lệ?** Với UTF-16: `0 <= begin <= end <= length()`. Với code point: `0 <= startPoint`, `0 <= count`, `startPoint + count <= totalCodePoints` (kiểm tra an toàn bằng phép trừ nếu cần).
6. **Mỗi lần chuyển đổi phải rõ ràng.** Biến như `utf16Offset`, `codePointIndex`, `graphemeBoundary` giúp tránh sử dụng nhầm đơn vị.
7. **Kiểm tra với đầu vào mẫu đa dạng.** Chuỗi rỗng, ASCII, tiếng Việt, emoji ngoài BMP, chữ + dấu kết hợp, emoji ghép, và dữ liệu chứa surrogate lẻ nếu có thể gặp.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Với `String s = "😀X";`, vì sao `s.charAt(1)` không trả về X?

**Đáp án:** emoji chiếm UTF-16 offset 0 và 1; `s.charAt(1)` là low surrogate, còn X ở offset 2.

**Câu 2.** `s.substring(0, 1)` có phải “lấy một Unicode code point đầu” không?

**Đáp án:** không. Nó lấy một UTF-16 code unit, có thể chỉ là high surrogate. Để lấy một code point, dùng `s.substring(0, s.offsetByCodePoints(0, 1))`.

**Câu 3.** Tại sao chuỗi `"e\u0301"` có `length() == 2` và `codePointCount(0, 2) == 2` nhưng thường chỉ hiển thị một chữ?

**Đáp án:** chữ e và dấu sắc kết hợp là hai code point BMP, mỗi điểm mã chiếm một UTF-16 code unit; chúng thường tạo một grapheme cluster hiển thị.

**Câu 4.** Nếu `indexOf("B")` trả về offset 5 trong `"A😀e\u0301B"`, có cần đổi số 5 sang code point index trước khi gọi `substring(0, 5)` không?

**Đáp án:** không. `indexOf()` và `substring()` đều dùng UTF-16 offset, nên giá trị 5 được dùng trực tiếp.

**Câu 5.** Giao diện yêu cầu giới hạn “không quá 20 ký tự hiển thị”. Dùng `codePointCount()` đã bảo đảm đúng chưa?

**Đáp án:** chưa. Một ký tự hiển thị có thể gồm nhiều code point. Cần chọn bộ phân đoạn grapheme cluster phù hợp và kiểm thử trường hợp emoji ghép, dấu kết hợp và các ngôn ngữ mục tiêu.

## Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length()`, `charAt()`, `substring()`, `codePointAt()`, `codePointCount()`, `offsetByCodePoints()`, `chars()` và `codePoints()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pair, `charCount()`, code point và UTF-16.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): tìm ranh giới ký tự, từ và câu dựa trên locale.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://unicode.org/reports/tr29/): quy tắc phân đoạn grapheme cluster, từ và câu.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): những dạng biểu diễn Unicode tương đương và chuẩn hóa.
