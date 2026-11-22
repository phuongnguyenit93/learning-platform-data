# Xây lại String bằng bộ đệm với appendCodePoint trong Java

## 1. Mục tiêu

Khi xử lý văn bản từ `String.codePoints()` hoặc một `IntStream` các mã Unicode, ta thường cần tạo lại một `String`. Cách làm trực tiếp là dùng **`StringBuilder` làm bộ đệm**, thêm lần lượt mỗi mã Unicode với **`appendCodePoint(int)`**, rồi gọi `toString()`.

Mẫu cơ bản:

~~~java
String source = "A\uD83D\uDE80B"; // "A🚀B"
StringBuilder builder = new StringBuilder(source.length());
source.codePoints().forEach(builder::appendCodePoint);
String rebuilt = builder.toString();
~~~

Đây là **đoạn minh họa đặt trong một phương thức**, không phải một tệp Java độc lập. `rebuilt.equals(source)` là `true`.

Cách này đặc biệt hữu ích khi luồng xử lý cần **lọc, ánh xạ hoặc biến đổi từng Unicode code point** trước khi lắp thành chuỗi mới. Với việc sao chép nguyên xi một chuỗi mà không xử lý gì, không cần tạo bộ đệm; ta đã có chuỗi gốc.

## 2. Phân biệt `char`, code point và ký tự hiển thị

Java `String` lưu văn bản theo **UTF-16**. Ba đơn vị đo sau khác nhau:

| Khái niệm | Ví dụ/đặc điểm |
| --- | --- |
| **UTF-16 code unit** | Một giá trị `char`, 16 bit. `String.length()` trả số code unit, không luôn bằng số ký tự người dùng nhìn thấy. |
| **Unicode code point** | Giá trị số của một vị trí mã Unicode. Có thể cần **một** hoặc **hai** UTF-16 code unit để biểu diễn. `String.codePoints()` trả về `IntStream` của các giá trị kiểu `int`. |
| **Grapheme cluster** (ký tự hiển thị) | Một đơn vị người dùng nhìn như một ký tự, có thể gồm **nhiều code point**, ví dụ chữ `e` kết hợp dấu sắc `\u0301` hay emoji nối bằng ZWJ. |

Ví dụ:

- `"A"`: một code point U+0041, một UTF-16 code unit.
- `"★"`: U+2605, một code point, một code unit.
- `"🚀"`: U+1F680, một code point nhưng **hai** code unit (surrogate pair).
- `"e\u0301"`: thường hiển thị thành một chữ có dấu, nhưng chứa **hai code point** (`e` và U+0301), cũng là hai code unit.

Do đó:

~~~java
String text = "A\uD83D\uDE80B"; // A🚀B
System.out.println(text.length());                       // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

`String.chars()` trả một `IntStream` nhưng mỗi phần tử chỉ là **một UTF-16 code unit mở rộng sang int**, nên surrogate pair tạo **hai phần tử**. Ngược lại, `String.codePoints()` ghép cặp surrogate hợp lệ thành **một phần tử kiểu int**. Vì vậy, khi thao tác theo code point, hãy chọn `codePoints()`.

Một `char` đơn lẻ không chứa trọn emoji như U+1F680. Nếu dùng `(char) cp` để ép kiểu một code point bổ sung, sẽ mất phần thông tin vượt quá 16 bit.

## 3. `StringBuilder.appendCodePoint(int)` làm gì?

`StringBuilder.appendCodePoint(int codePoint)` thêm biểu diễn UTF-16 của code point vào cuối builder:

1. Với giá trị trong **Basic Multilingual Plane (BMP)** như U+0041 hoặc U+2605, phương thức thêm **một** UTF-16 code unit.
2. Với code point bổ sung như U+1F680, phương thức tạo **một surrogate pair**, tức **hai** code unit.
3. Với giá trị ngoài phạm vi mã code point (ví dụ `-1` hoặc `0x110000`), phương thức ném `IllegalArgumentException`.

Phương thức trả về chính `StringBuilder` nên có thể nối chuỗi lệnh:

~~~java
StringBuilder b = new StringBuilder();
b.appendCodePoint(0x41)
 .appendCodePoint(0x1F680)
 .appendCodePoint(0x42);
String result = b.toString(); // A🚀B
~~~

Với `StringBuilder`, `length()` đo **số UTF-16 code unit đã thêm**. Khi thêm emoji U+1F680, độ dài tăng **2**, không phải 1.

**Lưu ý tinh tế:** `Character.isValidCodePoint` và `appendCodePoint` kiểm tra phạm vi code point từ U+0000 đến U+10FFFF, bao gồm cả dải giá trị surrogate U+D800–U+DFFF. Giá trị thuộc dải này khi thêm đơn lẻ tạo **unpaired surrogate** trong chuỗi UTF-16, không phải Unicode scalar value hợp lệ để trao đổi qua mọi bộ mã hóa. Với dữ liệu văn bản ngoài hệ thống, nên kiểm soát cả các surrogate lẻ, tùy hợp đồng xử lý.

## 4. Ví dụ Java 17+ hoàn chỉnh và kiểm thử

Lưu chương trình sau vào tệp **AppendCodePointDemo.java**. Bài kiểm thử chạy không cần thư viện ngoài; mỗi trường hợp sai sẽ ném `AssertionError`.

~~~java
public class AppendCodePointDemo {
    private static final int ROCKET = 0x1F680; // U+1F680 🚀

    static String rebuild(String input) {
        StringBuilder result = new StringBuilder(input.length());
        input.codePoints().forEach(result::appendCodePoint);
        return result.toString();
    }

    static String removeRocket(String input) {
        StringBuilder result = new StringBuilder(input.length());
        input.codePoints()
                .filter(cp -> cp != ROCKET)
                .forEach(result::appendCodePoint);
        return result.toString();
    }

    static String rocketToStar(String input) {
        StringBuilder result = new StringBuilder(input.length());
        input.codePoints()
                .map(cp -> cp == ROCKET ? 0x2605 : cp) // U+2605 ★
                .forEach(result::appendCodePoint);
        return result.toString();
    }

    static String rebuildByIndex(String input) {
        StringBuilder result = new StringBuilder(input.length());
        for (int i = 0; i < input.length();) {
            int cp = input.codePointAt(i);
            result.appendCodePoint(cp);
            i += Character.charCount(cp);
        }
        return result.toString();
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("Failed: " + name);
        }
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE80B"; // A🚀B: 4 UTF-16 units, 3 code points

        check("UTF-16 length", text.length() == 4);
        check("code point count",
                text.codePointCount(0, text.length()) == 3);
        check("round trip stream", text.equals(rebuild(text)));
        check("round trip indexes", text.equals(rebuildByIndex(text)));
        check("remove rocket", "AB".equals(removeRocket(text)));
        check("replace rocket", "A\u2605B".equals(rocketToStar(text)));
        check("empty input", "".equals(rebuild("")));
        check("combining mark", "e\u0301".equals(rebuild("e\u0301")));
        String isolatedHighSurrogate = String.valueOf((char) 0xD83D);
        check("isolated surrogate retained",
                isolatedHighSurrogate.equals(rebuild(isolatedHighSurrogate)));

        StringBuilder supplementary = new StringBuilder();
        supplementary.appendCodePoint(ROCKET);
        check("supplementary uses two UTF-16 units",
                supplementary.length() == 2);

        boolean invalidRejected = false;
        try {
            new StringBuilder().appendCodePoint(0x110000);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check("invalid code point rejected", invalidRejected);

        System.out.println("utf16Length=" + text.length());
        System.out.println("codePointCount="
                + text.codePointCount(0, text.length()));
        System.out.println("roundTrip=" + text.equals(rebuild(text)));
        System.out.println("removedRocket=" + removeRocket(text));
        System.out.println("replacedRocket=" + rocketToStar(text));
        System.out.println("emojiUtf16Length=" + supplementary.length());
        System.out.println("invalidRejected=" + invalidRejected);
        System.out.println("PASS: 11 checks");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AppendCodePointDemo.java
java AppendCodePointDemo
~~~

Đầu ra dự kiến khi toàn bộ 11 kiểm tra thành công:

~~~text
utf16Length=4
codePointCount=3
roundTrip=true
removedRocket=AB
replacedRocket=A★B
emojiUtf16Length=2
invalidRejected=true
PASS: 11 checks
~~~

Trong ví dụ:

- `rebuild` duyệt `codePoints()` và nối từng code point theo đúng thứ tự, nên khôi phục nguyên văn chuỗi đầu vào.
- `removeRocket` loại U+1F680 bằng `filter`; cả hai UTF-16 code unit tạo ra emoji bị loại **cùng nhau**, thay vì lọc từng nửa surrogate pair.
- `rocketToStar` dùng `map` biến một code point bổ sung thành code point BMP U+2605, nên độ dài UTF-16 của kết quả thay đổi dù số code point vẫn bằng nhau.
- `rebuildByIndex` cho cách tương đương khi cần nắm **vị trí trong chuỗi gốc**: `codePointAt(i)` đọc code point, `Character.charCount(cp)` giúp bước nhảy đúng 1 hoặc 2 code unit.
- Bài kiểm thử còn gồm chuỗi rỗng, dấu kết hợp, surrogate đứng lẻ, và mã nằm ngoài U+10FFFF. Các giá trị surrogate đơn lẻ được `codePoints()` trả như giá trị code unit, rồi `appendCodePoint` có thể ghi lại, nhờ vậy việc sao chép không vô tình làm đổi chuỗi gốc.

Dùng phép kiểm tra `equals` xác nhận kết quả thực tế giúp phát hiện các khác biệt không dễ thấy bằng mắt, đặc biệt khi dữ liệu chứa emoji hoặc dấu kết hợp. Không dựa chỉ vào lệnh Java `assert`, vì `assert` có thể bị tắt nếu JVM không bật `-ea`.

## 5. Cơ chế phối hợp với `IntStream`

`String.codePoints()` cung cấp luồng `IntStream` tuần tự. Mỗi giá trị `int` biểu diễn một code point (hoặc một surrogate lẻ). `forEach(result::appendCodePoint)` là cách viết ngắn gọn của:

~~~java
StringBuilder result = new StringBuilder();
text.codePoints().forEach(cp -> result.appendCodePoint(cp));
String output = result.toString();
~~~

Nếu cần điều kiện hoặc ánh xạ, đặt trước phép append:

~~~java
StringBuilder result = new StringBuilder();
text.codePoints()
    .filter(cp -> cp != 0x1F680)          // Bỏ 🚀
    .map(cp -> cp == 'a' ? 'A' : cp)        // Đổi a thành A
    .forEach(result::appendCodePoint);
String output = result.toString();
~~~

Hai đoạn là **mảnh code minh họa trong phương thức**, với `text` là một biến `String` đã có. Trong `map`, mỗi đầu ra cần là giá trị code point hợp lệ cho `appendCodePoint`. Nếu một đầu vào phải đổi thành **nhiều code point**, hãy dùng vòng lặp/`forEach` với nhiều lệnh `appendCodePoint` hoặc dùng cấu trúc xử lý phù hợp; `IntStream.map` thông thường là phép biến đổi **một sang một**.

Lưu ý quan trọng về thứ tự: mẫu `forEach` với một `StringBuilder` dùng **luồng tuần tự**. Nếu gọi `parallel()` rồi ghi cùng một builder trong `forEach`, các thao tác có thể đua nhau, mất thứ tự, hỏng kết quả do `StringBuilder` không thread-safe. Khi cần xử lý song song, phải thiết kế phương án gom kết quả an toàn và đúng thứ tự; đừng đơn thuần thêm `parallel()` vào ví dụ.

## 6. Độ phức tạp, bộ nhớ và cách chọn vòng lặp

Với đầu vào gồm `n` UTF-16 code unit và xử lý tuyến tính theo từng code point, duyệt rồi append có thời gian tổng thể **O(n)**. `StringBuilder` giảm chi phí tạo các chuỗi trung gian so với nối `String` lặp lại bằng `result += ...` trong vòng lặp lớn.

`new StringBuilder(input.length())` cấp phát dung lượng ban đầu theo **số UTF-16 code unit**, không theo số code point. Nếu chỉ sao chép hoặc lọc bỏ code point, dung lượng đó thường đủ cho kết quả. Nếu một code point có thể được thay bằng nhiều ký tự hoặc chuỗi dài hơn, builder vẫn tự mở rộng, nhưng có thể có thêm chi phí cấp phát.

`StringBuilder` là mutable và thích hợp khi dựng kết quả **trong một luồng xử lý**. Sau `toString()`, kết quả là một đối tượng `String` bất biến độc lập với các thao tác thay đổi builder về sau.

Khi cần vừa xử lý vừa biết chỉ số UTF-16 trong đầu vào, vòng lặp sau có thể thuận tiện hơn stream:

~~~java
StringBuilder out = new StringBuilder(input.length());
for (int index = 0; index < input.length();) {
    int cp = input.codePointAt(index);
    out.appendCodePoint(cp);
    index += Character.charCount(cp);
}
String rebuilt = out.toString();
~~~

Đây là mảnh code bên trong phương thức có biến `input`. **Không tăng `index++` vô điều kiện** nếu đang xử lý theo code point: với một supplementary code point, phải tiến **hai code unit**. Phương thức `Character.charCount(cp)` trả về 2 với code point bổ sung, trả về 1 với BMP hoặc surrogate đứng lẻ.

## 7. Những điểm dễ sai trong thực tế

1. **Dùng `chars()` khi muốn xử lý trọn code point:** `chars()` nhìn từng code unit, có thể làm tách đôi surrogate pair trong các phép lọc và biến đổi. Hãy dùng `codePoints()` nếu yêu cầu ở mức code point.
2. **Ép kiểu `(char) cp` rồi append:** làm mất thông tin với các giá trị trên U+FFFF. Dùng `appendCodePoint(cp)`.
3. **Nhầm code point với “một chữ người dùng thấy”:** emoji nối bằng ZWJ hoặc ký tự kết hợp dấu có thể gồm nhiều code point. `codePoints()` không tự nhóm grapheme cluster; khi cần xử lý theo cụm ký tự, cân nhắc `BreakIterator` hoặc thư viện phân đoạn Unicode phù hợp.
4. **Duyệt song song và ghi chung builder:** `StringBuilder` không an toàn khi bị nhiều luồng ghi đồng thời. Sử dụng pipeline tuần tự hoặc kiến trúc thu gom được bảo đảm thứ tự.
5. **Quên `toString()`:** builder là bộ đệm mutable; API yêu cầu `String` cần kết quả cuối `builder.toString()`.
6. **Tự giả định mọi code point chỉ thêm một `char`:** supplementary code point cần surrogate pair. Kích thước builder và chỉ số trong `String` đều tính theo UTF-16.
7. **Không kiểm tra code point sinh từ phép biến đổi:** mã âm hoặc vượt `0x10FFFF` làm `appendCodePoint` ném `IllegalArgumentException`. Nếu cần xuất bản văn bản Unicode chuẩn, chú ý cả surrogate lẻ trong vùng U+D800–U+DFFF.
8. **Dùng builder để tái tạo nguyên xi chuỗi gốc mà không có biến đổi:** không cần thiết nếu ứng dụng đã có `String` và có thể trả trực tiếp. Builder hữu ích khi cần thực sự dựng một kết quả mới.

## 8. Bài tập tự kiểm tra

**Bài 1.** Với `"x🚀y"`, `length()` và `codePoints().count()` bằng bao nhiêu?

Đáp án: `length() == 4` vì `x` và `y` mỗi ký tự một code unit, rocket hai code unit; `codePoints().count() == 3` vì có ba code point.

**Bài 2.** Vì sao `input.codePoints().filter(cp -> cp != 0x1F680).forEach(builder::appendCodePoint)` xóa emoji 🚀 một cách trọn vẹn?

Đáp án: luồng chứa **một phần tử int U+1F680** cho cả surrogate pair. `filter` loại chính phần tử này; không có nửa surrogate nào được append.

**Bài 3.** Nếu thay U+1F680 bằng U+2605 thông qua `map`, số code point thay đổi không? Số UTF-16 code unit có thể thay đổi không?

Đáp án: một mã đổi thành một mã nên số code point không đổi, nhưng U+1F680 dùng hai code unit còn U+2605 dùng một, nên `String.length()` giảm một.

**Bài 4.** Làm sao giữ nguyên thứ tự và tránh lỗi khi dựng chuỗi bằng builder từ stream?

Đáp án: dùng `codePoints()` **tuần tự** và append tuần tự; không ghi song song vào cùng `StringBuilder`.

## 9. Khi nào nên dùng mẫu này?

Dùng `codePoints() → filter/map → StringBuilder.appendCodePoint() → toString()` khi cần **chủ động dựng lại String theo code point**, ví dụ bỏ emoji cụ thể, chuẩn hóa một số ký tự, thay ký hiệu Unicode, hoặc lọc những mã không cho phép. Nếu cần xử lý theo UTF-16 code unit, grapheme cluster hoặc quy tắc ngôn ngữ tự nhiên, cần chọn mức trừu tượng tương ứng.

**Quy tắc nhớ:** `String.length()` đếm UTF-16 code unit, `String.codePoints()` duyệt code point, còn `StringBuilder.appendCodePoint()` biến mỗi giá trị `int` trở lại biểu diễn UTF-16 đúng độ rộng. Giữ thứ tự, kiểm tra mã đầu vào và xây dựng kết quả tuần tự để tái tạo `String` an toàn.
