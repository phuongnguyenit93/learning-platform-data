# `length()`, `charAt()` và `substring()` trong Java 17+

Ba phương thức thường dùng nhất để đọc và cắt `String` trong Java là:

- `length()`: trả về **số đơn vị mã UTF-16** trong chuỗi.
- `charAt(index)`: lấy một giá trị `char` tại **chỉ số UTF-16** được yêu cầu.
- `substring(beginIndex)` và `substring(beginIndex, endIndex)`: lấy phần nội dung từ một vị trí, hoặc từ vị trí bắt đầu **bao gồm** đến vị trí kết thúc **không bao gồm**.

Mọi chỉ số đều **bắt đầu từ 0**. Đây là ba thao tác để **đọc hoặc tạo kết quả chuỗi**, không thay đổi nội dung `String` gốc.

## 1. Bảng tra nhanh cú pháp và giới hạn

Giả sử:

~~~java
String text = "Java Core";
~~~

Chuỗi trên có 9 đơn vị mã UTF-16, đánh chỉ số như sau:

~~~text
Ký tự : J a v a   C o r e
Chỉ số: 0 1 2 3 4 5 6 7 8
Biên  : 0 1 2 3 4 5 6 7 8 9
~~~

| Biểu thức | Kết quả | Quy tắc |
| --- | --- | --- |
| `text.length()` | `9` | Tổng số **UTF-16 code unit** |
| `text.charAt(0)` | `'J'` | Phần tử đầu; kiểu trả về là `char` |
| `text.charAt(5)` | `'C'` | Vị trí thứ 6 |
| `text.substring(0, 4)` | `"Java"` | Lấy các chỉ số 0, 1, 2, 3 |
| `text.substring(5)` | `"Core"` | Lấy từ 5 tới hết |
| `text.substring(5, 9)` | `"Core"` | `endIndex = length()` được phép |
| `text.substring(4, 4)` | `""` | Hai đầu bằng nhau tạo chuỗi rỗng |
| `text.substring(0, text.length())` | `"Java Core"` | Chọn toàn bộ chuỗi |

Điểm khác nhau quan trọng: **`charAt(length())` sai**, còn **`substring(length())` hợp lệ và trả về `""`**. Vì `charAt` phải đọc phần tử có thật, còn `substring` được phép bắt đầu tại **biên cuối**.

## 2. Ví dụ Java 17+ chạy được

Lưu tệp UTF-8 tên **`StringIndexDemo.java`**:

~~~java
public class StringIndexDemo {
    public static void main(String[] args) {
        String text = "Java Core";

        System.out.println("text=" + text);
        System.out.println("length=" + text.length());
        System.out.println("first=" + text.charAt(0));
        System.out.println("sixth=" + text.charAt(5));
        System.out.println("prefix=" + text.substring(0, 4));
        System.out.println("suffix=" + text.substring(5));
        System.out.println("middle=" + text.substring(5, 9));
        System.out.println("emptyLength=" + text.substring(4, 4).length());
        System.out.println("wholeSameContent="
                + text.substring(0, text.length()).equals(text));

        String unicode = "A🚀B";
        String rocket = unicode.substring(1, 3);

        System.out.println("codeUnits=" + unicode.length());
        System.out.println("codePoints="
                + unicode.codePointCount(0, unicode.length()));
        System.out.println("emojiSliceUnits=" + rocket.length());
        System.out.println("emojiSliceCodePoints="
                + rocket.codePointCount(0, rocket.length()));
        System.out.println("highSurrogate="
                + Character.isHighSurrogate(unicode.charAt(1)));
        System.out.println("lowSurrogate="
                + Character.isLowSurrogate(unicode.charAt(2)));
        System.out.printf("rocketPoint=U+%X%n", unicode.codePointAt(1));

        try {
            text.charAt(text.length());
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("invalidCharAt=StringIndexOutOfBoundsException");
        }

        try {
            text.substring(6, 5);
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println(
                    "invalidSubstring=StringIndexOutOfBoundsException");
        }
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) ở thư mục chứa tệp và chạy với JDK 17+:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StringIndexDemo.java
java StringIndexDemo
~~~

**Expected output:**

~~~text
text=Java Core
length=9
first=J
sixth=C
prefix=Java
suffix=Core
middle=Core
emptyLength=0
wholeSameContent=true
codeUnits=4
codePoints=3
emojiSliceUnits=2
emojiSliceCodePoints=1
highSurrogate=true
lowSurrogate=true
rocketPoint=U+1F680
invalidCharAt=StringIndexOutOfBoundsException
invalidSubstring=StringIndexOutOfBoundsException
~~~

Giải thích nhanh: `"Java Core"` có 9 code unit và vị trí 5 là chữ `C`. `substring(5, 9)` không lấy phần tử có chỉ số 9 mà lấy các vị trí `5, 6, 7, 8`. `"A🚀B"` có **4 UTF-16 code unit** dù chỉ gồm **3 Unicode code point**, vì emoji 🚀 (U+1F680) cần hai đơn vị mã.

Hai lỗi được bắt bằng `try/catch` để chương trình tiếp tục chạy. Khi lập trình thực tế, ưu tiên kiểm tra cận trước khi gọi thay vì dựa vào exception cho luồng xử lý bình thường.

## 3. Hiểu chính xác phạm vi chỉ số

Gọi `n = text.length()`.

| Phương thức | Điều kiện hợp lệ | Không hợp lệ |
| --- | --- | --- |
| `text.charAt(i)` | `0 <= i && i < n` | `i < 0` hoặc `i >= n` |
| `text.substring(begin)` | `0 <= begin && begin <= n` | `begin < 0` hoặc `begin > n` |
| `text.substring(begin, end)` | `0 <= begin && begin <= end && end <= n` | Bất kỳ vi phạm nào |

Java ném **`StringIndexOutOfBoundsException`** khi dùng chỉ số không hợp lệ với các phương thức trên.

Những lỗi thường gặp:

~~~java
String s = "Hi"; // length() = 2.

// s.charAt(2);       // Sai: chi so hop le chi co 0, 1.
// s.charAt(-1);      // Sai: khong co chi so am.
// s.substring(-1);   // Sai: begin am.
// s.substring(1, 3); // Sai: end vuot length().
// s.substring(2, 1); // Sai: begin lon hon end.

String empty = s.substring(2); // Hop le: chuoi rong.
~~~

**Lấy ký tự cuối cùng** khi chắc chắn chuỗi không rỗng:

~~~java
char last = s.charAt(s.length() - 1);
~~~

Nếu `s.isEmpty()`, biểu thức `length() - 1` bằng `-1` và sẽ gây exception. Cần kiểm tra:

~~~java
if (!s.isEmpty()) {
    char last = s.charAt(s.length() - 1);
    System.out.println(last);
}
~~~

Nếu `s == null`, cả ba phương thức đều không thể được gọi và sẽ ném `NullPointerException`. Điều này **khác** với chuỗi rỗng `""`: chuỗi rỗng là một đối tượng tồn tại, có `length() == 0` và `substring(0)` hợp lệ.

## 4. Tại sao `substring` dùng cận cuối loại trừ?

Thiết kế khoảng **`[begin, end)`** có ba lợi ích:

1. Độ dài đoạn cắt bằng **`end - begin`** tính theo UTF-16 code unit.
2. Hai khoảng liên tiếp ghép đúng biên: `substring(0, k)` và `substring(k, n)` không trùng, không thiếu đơn vị mã.
3. Khi lấy từ đầu đến hết, dùng ngay `text.substring(0, text.length())`.

Ví dụ tách phần trước/sau dấu `':'`:

~~~java
String record = "id:42";
int colon = record.indexOf(':');

if (colon >= 0) {
    String key = record.substring(0, colon);     // "id"
    String value = record.substring(colon + 1); // "42"
}
~~~

`indexOf` trả `-1` khi không tìm thấy ký tự. Nếu quên kiểm tra kết quả, phép tính cận cho `substring` có thể sai ý định dù đôi lúc vẫn hợp lệ về mặt chỉ số.

Cũng cần phân biệt **phần của một chuỗi** với **một chuỗi mới có đối tượng độc lập**: `substring` cho kết quả `String` bất biến, nhưng không nên dựa vào giả định JVM luôn tạo ra một đối tượng khác cho mọi khoảng cắt. Hãy kiểm tra **nội dung** bằng `equals`, không dùng `==`.

## 5. Cạm bẫy Unicode: chỉ số trong Java là chỉ số UTF-16

`length()` đếm **code unit**, không mặc định đếm Unicode code point hoặc số ký tự hiển thị.

Với `"A🚀B"`:

~~~text
Giá trị nhìn thấy:    A       🚀          B
Chỉ số code unit:     0       1, 2        3
Đầu cuối chuỗi:                              4
~~~

- `charAt(0)` chứa `'A'`.
- `charAt(1)` trả **high surrogate**, còn `charAt(2)` trả **low surrogate**. Mỗi giá trị là một `char`, **không phải toàn bộ emoji**.
- `substring(1, 3)` lấy **đúng cả cặp surrogate** nên là đoạn chứa emoji.
- `substring(1, 2)` chỉ lấy **nửa cặp surrogate**, có thể tạo chuỗi chứa surrogate đơn lẻ không mong muốn. Đừng cắt giữa hai code unit của một code point ngoài BMP.

Nếu cần làm việc với Unicode code point, dùng `codePointAt`, `codePointCount`, `offsetByCodePoints` và `codePoints()`. Ví dụ lấy code point đầu tiên:

~~~java
String word = "🚀Launch";
int cp = word.codePointAt(0);              // 0x1F680.
int end = word.offsetByCodePoints(0, 1);    // 2 code unit.
String firstCodePoint = word.substring(0, end); // "🚀".
~~~

Lưu ý: **code point không nhất thiết bằng một ký tự người dùng cảm nhận** (*grapheme cluster*), chẳng hạn chữ có dấu kết hợp có thể gồm nhiều code point. Các phương thức `length`/`charAt`/`substring` không phải bộ tách grapheme đầy đủ.

## 6. Chọn phương thức cho đúng mục đích

| Yêu cầu | Cách làm | Ghi chú |
| --- | --- | --- |
| Đo độ dài theo UTF-16 | `text.length()` | Không phải số code point trong mọi trường hợp |
| Lấy code unit tại chỉ số `i` | `text.charAt(i)` | Kiểm tra `0 <= i < length()` |
| Lấy từ `begin` đến hết | `text.substring(begin)` | `begin == length()` trả `""` |
| Lấy khoảng `[begin, end)` | `text.substring(begin, end)` | Cận cuối loại trừ |
| Đọc một code point | `text.codePointAt(i)` | `i` vẫn là chỉ số UTF-16 |
| Đếm code point | `text.codePointCount(0, text.length())` | Không phải đếm grapheme |
| Tránh `NullPointerException` | Kiểm tra `text != null` | Chuỗi rỗng khác null |

## 7. Bài tập tự kiểm tra

**Bài 1.** `String s = "abcdef";`. Giá trị của `s.length()`, `s.charAt(2)` và `s.substring(2, 5)` là gì?

*Đáp án:* `6`, `'c'` và `"cde"`.

**Bài 2.** Với `String s = "Java";`, `s.substring(4)` và `s.charAt(4)` khác nhau thế nào?

*Đáp án:* `substring(4)` trả chuỗi rỗng; `charAt(4)` ném `StringIndexOutOfBoundsException`.

**Bài 3.** Tại sao `s.substring(1, 3)` có độ dài 2, không phải 3?

*Đáp án:* Chỉ lấy chỉ số 1 và 2; cận cuối 3 **không bao gồm**.

**Bài 4.** `"A🚀B".length()` bằng 4 hay 3? `substring(1, 3)` cắt được gì?

*Đáp án:* `length()` bằng 4 code unit; `substring(1, 3)` chứa cả emoji 🚀.

**Bài 5.** Làm thế nào lấy ký tự cuối chuỗi mà không phát sinh lỗi khi chuỗi rỗng?

*Đáp án:* Kiểm tra `!s.isEmpty()` rồi mới gọi `s.charAt(s.length() - 1)`. Nếu `s` có thể null, kiểm tra `s != null` trước.

## Checklist ghi nhớ

- [ ] `length()` đếm UTF-16 code unit, không mặc định đếm code point.
- [ ] `charAt(i)` chỉ nhận `0 <= i < length()`.
- [ ] `substring(begin, end)` lấy khoảng **`[begin, end)`**, nên độ dài bằng `end - begin`.
- [ ] `substring(length())` hợp lệ nhưng `charAt(length())` không hợp lệ.
- [ ] Không lấy `charAt(length() - 1)` trước khi kiểm tra chuỗi rỗng.
- [ ] Không cắt `substring` giữa hai surrogate của một emoji ngoài BMP.
- [ ] Phương thức không sửa `String` gốc; nên kiểm tra kết quả theo **nội dung**.

**Kết luận:** Hãy nhìn `length()` như **giới hạn trên loại trừ** của chỉ số UTF-16, dùng `charAt` để đọc một code unit và dùng `substring` để lấy khoảng `[begin, end)`. Khi thao tác với Unicode ngoài BMP, nhớ rằng một ký tự hiển thị có thể chiếm nhiều vị trí chỉ số.
