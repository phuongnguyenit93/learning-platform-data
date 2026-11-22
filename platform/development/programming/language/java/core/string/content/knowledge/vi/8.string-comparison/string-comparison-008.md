# regionMatches() để so sánh một vùng chuỗi trong Java

## 1. Mục tiêu và tình huống sử dụng

Khi so sánh hai chuỗi, đôi khi bạn **không cần so sánh toàn bộ nội dung**. Ví dụ: kiểm tra bốn ký tự ở giữa hai mã định danh có trùng nhau không; so sánh một đoạn bắt đầu ở vị trí xác định trong văn bản; hoặc kiểm tra một vùng mà **không phân biệt chữ hoa/chữ thường**.

`String.regionMatches()` làm đúng việc này: so sánh **hai vùng liên tiếp có cùng độ dài** được chỉ định bằng offset và số đơn vị ký tự. Phương thức trả `boolean`, **không sửa chuỗi nguồn** và không trả một chuỗi con mới.

Sau bài này, bạn có thể:

1. Dùng đúng cả **hai overload** của `regionMatches()`.
2. Xác định đúng `toffset`, `ooffset` và `len`; phân biệt **vị trí bắt đầu**, **độ dài** và **chỉ số kết thúc**.
3. Dự đoán `true`/`false` khi vùng trùng, khác ký tự, vượt biên hoặc độ dài bằng `0`.
4. Hiểu rõ `ignoreCase`, giới hạn Unicode/locale và đơn vị chỉ số UTF-16.
5. So sánh với `equals()`, `equalsIgnoreCase()`, `startsWith()`, `substring()` và `matches()`.
6. Viết hàm bao ngoài để kiểm soát `null`, tham số âm và phạm vi trước khi dùng trong nghiệp vụ.

Kiến thức cần có: `String`, chỉ số từ `0`, `length()`, `charAt()`, `boolean` và lời gọi phương thức. Ví dụ độc lập dùng **Java 17+**.

## 2. Hai overload và ý nghĩa từng tham số

Java cung cấp hai dạng:

~~~java
public boolean regionMatches(int toffset,
                             String other,
                             int ooffset,
                             int len);

public boolean regionMatches(boolean ignoreCase,
                             int toffset,
                             String other,
                             int ooffset,
                             int len);
~~~

Cú pháp tổng quát:

~~~java
left.regionMatches(leftOffset, right, rightOffset, length);
left.regionMatches(ignoreCase, leftOffset, right, rightOffset, length);
~~~

Trong đó:

| Tham số | Kiểu | Vai trò |
| --- | --- | --- |
| `left` (đối tượng nhận lời gọi) | `String` | Chuỗi thứ nhất (`this`) |
| `toffset` / `leftOffset` | `int` | Chỉ số bắt đầu của vùng trong `left` |
| `other` / `right` | `String` | Chuỗi thứ hai |
| `ooffset` / `rightOffset` | `int` | Chỉ số bắt đầu của vùng trong `right` |
| `len` / `length` | `int` | **Số đơn vị UTF-16** cần so ở mỗi vùng, không phải chỉ số kết thúc |
| `ignoreCase` | `boolean` | `true`: bỏ qua khác biệt chữ hoa/chữ thường theo quy tắc của `Character`; `false`: so chính xác |

Bản bốn tham số so sánh chính xác (phân biệt case). Bản năm tham số cho phép chọn hành vi case bằng `ignoreCase`.

**Điểm cần nhớ:** `len` là cùng một độ dài áp dụng cho hai vùng; phương thức không cho một bên dài hơn bên còn lại rồi tự cắt cho vừa.

## 3. Đọc offset bằng hình ảnh

Xét hai chuỗi:

~~~text
left  = "prefix-Java-END"
         012345678901234
                ^^^^
                vị trí 7..10 = Java

right = "Start-Java-OK"
         0123456789012
               ^^^^
               vị trí 6..9 = Java
~~~

Ta so **bốn đơn vị UTF-16** bắt đầu ở vị trí `7` của `left` và vị trí `6` của `right`:

~~~java
String left = "prefix-Java-END";
String right = "Start-Java-OK";

boolean same = left.regionMatches(7, right, 6, 4);
System.out.println(same); // true
~~~

Hai vùng đều là `"Java"` nên kết quả `true`, mặc dù hai chuỗi **toàn phần không giống nhau**.

Nếu tăng `len` lên `6`, vùng so sánh trở thành `"Java-E"` và `"Java-O"`, kết quả `false`:

~~~java
System.out.println(left.regionMatches(7, right, 6, 6)); // false
~~~

**Không nhầm với `substring(begin, end)`:** phương thức `substring(7, 11)` có tham số thứ hai là **chỉ số kết thúc loại trừ**, còn `regionMatches(7, right, 6, 4)` có tham số cuối là **độ dài 4**. Nhầm hai kiểu ký hiệu là lỗi rất thường gặp.

## 4. So khớp chính xác: bốn tham số

Cú pháp:

~~~java
boolean result = first.regionMatches(
        firstOffset, second, secondOffset, count);
~~~

Các vị trí được so theo thứ tự từ trái sang phải. Với phiên bản bốn tham số, hai vùng cần có cùng chuỗi **UTF-16 code units**.

~~~java
String a = "--JAVA--";
String b = "xxJAVAyy";
String c = "xxJavaYY";

System.out.println(a.regionMatches(2, b, 2, 4)); // true
System.out.println(a.regionMatches(2, c, 2, 4)); // false
~~~

Chữ hoa `"JAVA"` và `"Java"` khác nhau ở các ký tự tương ứng nên không khớp trong chế độ chính xác.

Nếu chỉ muốn biết toàn bộ chuỗi có cùng nội dung, hãy dùng `equals()`:

~~~java
boolean allEqual = a.equals(b);              // false
boolean areaEqual = a.regionMatches(2, b, 2, 4); // true
~~~

Đừng dùng `regionMatches()` thay `equals()` khi yêu cầu là so **toàn bộ** nội dung. Một phép so vùng có thể cho `true` trong khi phần đầu, phần cuối hoặc độ dài tổng thể khác nhau.

## 5. Bỏ qua chữ hoa/chữ thường: năm tham số

Phiên bản năm tham số bổ sung cờ `ignoreCase` ở đầu:

~~~java
String left = "prefix-Java-END";
String right = "Start-jAvA-OK";

System.out.println(left.regionMatches(7, right, 6, 4));
// false

System.out.println(left.regionMatches(false, 7, right, 6, 4));
// false

System.out.println(left.regionMatches(true, 7, right, 6, 4));
// true
~~~

Ý nghĩa:

- `ignoreCase = false`: kiểm tra các vùng khớp **chính xác**.
- `ignoreCase = true`: kiểm tra tương ứng **không phân biệt case** theo cơ chế của `Character`; `'J'` và `'j'` có thể được coi là tương đương.

Không cần tạo hai chuỗi viết thường bằng `toLowerCase()` trước khi gọi khi nhu cầu chỉ là so một vùng với quy tắc của `regionMatches(true, ...)`.

### Không đồng nghĩa so sánh văn bản theo ngôn ngữ tự nhiên

`regionMatches(true, ...)` **không sử dụng `Locale`** và không thay thế thuật toán *collation* cho mọi ngôn ngữ. Theo Javadoc Java 17, dạng này so sánh các chuỗi **Unicode code points** ở trong vùng; khi bỏ qua case, cơ chế dựa trên phép đổi case bằng `Character.toUpperCase(int)` rồi `Character.toLowerCase(int)`.

Do đó, `ignoreCase`:

- Không phải thuật toán tìm kiếm và so sánh có quy tắc ngôn ngữ cụ thể.
- Không tự bỏ dấu thanh tiếng Việt hoặc tự chuẩn hóa Unicode.
- Không bảo đảm xử lý tất cả quy tắc *full case folding* có thể khiến một chữ biến thành nhiều code points.
- Không cho phép hai vùng có độ dài UTF-16 khác nhau.

Nếu nghiệp vụ yêu cầu thứ tự hay sự tương đương theo locale, cân nhắc `java.text.Collator` hoặc một thư viện xử lý văn bản phù hợp; các yêu cầu an ninh/mã định danh có thể cần **so sánh chính xác** thay vì bỏ qua case.

## 6. Điều kiện biên: offset, độ dài và vùng rỗng

Với `len >= 0`, cách nghĩ an toàn nhất là hai khoảng chỉ số nửa mở phải hợp lệ:

~~~text
Vùng trái: [toffset, toffset + len)
Vùng phải: [ooffset, ooffset + len)
~~~

Khoảng `[a, b)` lấy vị trí `a` nhưng **không lấy** vị trí `b`.

Các điều kiện hợp lệ theo cách kiểm tra chủ động:

~~~text
toffset >= 0
ooffset >= 0
len >= 0
toffset <= left.length()
ooffset <= right.length()
len <= left.length() - toffset
len <= right.length() - ooffset
~~~

Khi một offset âm hoặc vùng vượt khỏi độ dài chuỗi, phương thức trả `false` (với `other` hợp lệ); khác `substring()` vốn thường ném ngoại lệ khi chỉ số sai.

Ví dụ:

~~~java
String a = "Java";
String b = "JAVA";

System.out.println(a.regionMatches(0, b, 0, 1));  // true
System.out.println(a.regionMatches(1, b, 1, 3));  // false
System.out.println(a.regionMatches(-1, b, 0, 2)); // false
System.out.println(a.regionMatches(0, b, 0, 5));  // false
System.out.println(a.regionMatches(4, b, 4, 0));  // true
~~~

Dòng cuối so hai **vùng rỗng** tại vị trí cuối chuỗi; với hai offset hợp lệ và `len = 0`, không có ký tự nào để khác nhau, nên trả `true`.

**Quan trọng:** dùng `len >= 0` như một tiền điều kiện của chương trình. Không dựa vào hành vi với độ dài âm vì đó không phải một yêu cầu so vùng có ý nghĩa và kết quả có thể bất ngờ. Khi nhận offset từ người dùng hoặc dữ liệu không tin cậy, xác minh tham số trước khi gọi.

### Vì sao nên kiểm tra bằng phép trừ?

Trong hàm tự viết, điều kiện:

~~~java
len <= text.length() - offset
~~~

thường dễ bảo vệ hơn `offset + len <= text.length()` nếu offset/len đến từ các số nguyên bất kỳ, vì phép cộng số nguyên có thể **tràn số**. Trước khi trừ, cần chắc chắn `offset` nằm trong `[0, text.length()]`.

### null không được coi là false thông thường

~~~java
String source = "Java";
String other = null;

// source.regionMatches(0, other, 0, 2); // NullPointerException
~~~

Đối số `other == null` gây `NullPointerException`; receiver `source == null` cũng không thể gọi phương thức. Hãy quyết định hợp đồng cho `null`: từ chối bằng ngoại lệ rõ ràng, hoặc trả `false` qua một hàm bao ngoài tự viết.

## 7. Unicode: offset/len đếm UTF-16, không đếm ký tự nhìn thấy

Cả `toffset`, `ooffset` và `len` được tính theo **UTF-16 code units** (đơn vị `char` 16 bit). Một Unicode code point ngoài BMP, chẳng hạn emoji `😀`, được biểu diễn bằng **surrogate pair** gồm hai đơn vị UTF-16.

~~~java
String text = "A😀Z";

System.out.println(text.length()); // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

Sơ đồ:

~~~text
Hiển thị:          A      😀       Z
UTF-16:           [A] [high][low] [Z]
Chỉ số:            0    1    2    3
Độ dài UTF-16:                   4
Code points:                     3
~~~

Để so **toàn bộ emoji**, `len` là `2`, không phải `1`:

~~~java
String a = "A😀Z";
String b = "X😀Y";
System.out.println(a.regionMatches(1, b, 1, 2)); // true
~~~

Nếu `len = 1` thì chỉ một nửa surrogate pair được đưa vào vùng so. Điều này có thể tạo kết quả trông đúng nhưng **không phản ánh so sánh trọn một emoji**:

~~~java
String a = "A😀Z";
String b = "X😁Y";

// Hai emoji khác nhau nhưng high surrogate giống nhau.
System.out.println(a.regionMatches(1, b, 1, 1)); // true
System.out.println(a.regionMatches(1, b, 1, 2)); // false
~~~

**Bài học:** cần đặt ranh giới vùng tại **đầu/cuối một code point**, tránh cắt giữa surrogate pair. Khi cần tính chỉ số theo code points, dùng `offsetByCodePoints()` để đổi thành offset UTF-16 phù hợp trước khi gọi:

~~~java
String text = "A😀Z";
int start = text.offsetByCodePoints(0, 1); // 1
int end = text.offsetByCodePoints(start, 1); // 3
int len = end - start; // 2 UTF-16 code units

System.out.println(text.regionMatches(start, "😀", 0, len)); // true
~~~

**Lưu ý khác:** code point vẫn không nhất thiết là một *grapheme cluster* (ký tự người dùng nhìn thấy). Ví dụ `"é"` có thể biểu diễn bằng một code point hoặc `"e\u0301"` (e + dấu sắc kết hợp). Hai chuỗi đó không có cùng dãy UTF-16 code units; `regionMatches()` không tự chuẩn hóa chúng. Nếu nghiệp vụ cần sự tương đương chuẩn hóa, xem `java.text.Normalizer` và quy tắc so sánh đã thỏa thuận.

## 8. Khi nào dùng regionMatches thay vì các API khác?

| Mục đích | API phù hợp | Lý do |
| --- | --- | --- |
| So **hai chuỗi toàn phần** chính xác | `a.equals(b)` | Rõ nghĩa, không cần tính offset |
| So hai chuỗi toàn phần không phân biệt case | `a.equalsIgnoreCase(b)` | Diễn đạt trực tiếp |
| So **hai vùng bất kỳ** trong hai chuỗi | `a.regionMatches(offsetA, b, offsetB, len)` | Có offset cho cả hai bên |
| So hai vùng, bỏ qua case | `a.regionMatches(true, offsetA, b, offsetB, len)` | Có cờ `ignoreCase` |
| Kiểm tra tiền tố tại một vị trí trong một chuỗi | `a.startsWith(prefix, offset)` | Diễn đạt rõ hơn nếu vùng ở chuỗi so sánh luôn bắt đầu tại 0 |
| Kiểm tra hậu tố | `a.endsWith(suffix)` | Không cần tự tính vị trí bắt đầu |
| Trích vùng để dùng như một giá trị `String` | `a.substring(begin, end)` | Trả chuỗi con thay vì boolean |
| Tìm vị trí của đoạn không biết nằm ở đâu | `a.indexOf(fragment)` | Trả vị trí hoặc `-1` |
| Khớp biểu thức chính quy | `Pattern`/`Matcher` hay `matches()` | Dùng khi mẫu là regex, không phải so hai vùng ở vị trí biết trước |

Ví dụ so tiền tố bắt đầu tại vị trí thứ ba:

~~~java
String log = "--ERROR: disk full";
String prefix = "ERROR";

System.out.println(log.regionMatches(2, prefix, 0, prefix.length())); // true
System.out.println(log.startsWith(prefix, 2)); // true
~~~

Cả hai phù hợp; trong trường hợp chỉ kiểm tra một `prefix`, `startsWith(prefix, 2)` thường dễ đọc hơn.

So với:

~~~java
String a = "prefix-Java-END";
String b = "Start-Java-OK";

boolean same = a.substring(7, 11).equals(b.substring(6, 10));
~~~

Kết quả cũng `true` nếu chỉ số hợp lệ. Nhưng cách này tạo **giá trị chuỗi con** để so; `regionMatches()` diễn đạt trực tiếp thao tác so vùng và không yêu cầu tạo chuỗi con tại phía người gọi. Đừng mặc định nó luôn nhanh hơn trong mọi môi trường; đo thực tế nếu đoạn code là điểm nghẽn.

## 9. Ví dụ chạy độc lập Java 17+

Tạo file **`RegionMatchesDemo.java`**:

~~~java
public class RegionMatchesDemo {
    public static void main(String[] args) {
        String left = "prefix-Java-END";
        String right = "Start-Java-OK";
        String mixed = "Start-jAvA-OK";

        System.out.println(left.regionMatches(7, right, 6, 4));
        System.out.println(left.regionMatches(7, right, 6, 6));
        System.out.println(left.regionMatches(7, mixed, 6, 4));
        System.out.println(left.regionMatches(true, 7, mixed, 6, 4));
        System.out.println(left.regionMatches(false, 7, mixed, 6, 4));

        System.out.println(left.regionMatches(-1, right, 6, 4));
        System.out.println(left.regionMatches(7, right, 6, 99));
        System.out.println(left.regionMatches(
                left.length(), right, right.length(), 0));

        String smile = "A😀Z";
        String grin = "X😁Y";
        System.out.println(smile.regionMatches(1, grin, 1, 1));
        System.out.println(smile.regionMatches(1, grin, 1, 2));

        System.out.println(left.startsWith("Java", 7));
        System.out.println(left.equals(right));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RegionMatchesDemo.java
java RegionMatchesDemo
~~~

Stdout **chính xác**:

~~~text
true
false
false
true
false
false
false
true
true
false
true
false
~~~

Giải thích theo từng nhóm:

1. `"Java"` tại offset `7` của `left` trùng `"Java"` tại offset `6` của `right`: `true`.
2. So sáu đơn vị gồm `"Java-E"` và `"Java-O"` khác nhau: `false`.
3. Chuỗi `mixed` có `"jAvA"` nên chế độ phân biệt case: `false`; `ignoreCase = true`: `true`; `false`: `false`.
4. Offset âm hoặc `len` quá lớn: `false`; vùng rỗng tại cuối hai chuỗi: `true`.
5. Hai emoji `😀` và `😁` có **high surrogate giống nhau**, nên so `len = 1` (chỉ high surrogate) ra `true`; so đủ `len = 2` ra `false`.
6. `startsWith("Java", 7)` trả `true`, nhưng `equals(right)` trả `false` vì toàn bộ chuỗi khác nhau.

Chương trình là một file độc lập, dùng đúng tên lớp và tên file, không cần thư viện ngoài JDK.

## 10. Viết hàm so vùng có kiểm tra đầu vào

Trong API nhận offset/len từ bên ngoài, bạn có thể công bố một hợp đồng rõ ràng: **trả `false` nếu chuỗi nào `null`, nếu `len` âm hoặc vùng vượt biên**.

~~~java
public final class RegionUtils {
    private RegionUtils() {}

    public static boolean sameRegion(
            String left, int leftOffset,
            String right, int rightOffset,
            int len, boolean ignoreCase) {

        if (left == null || right == null || len < 0
                || leftOffset < 0 || rightOffset < 0) {
            return false;
        }
        if (leftOffset > left.length()
                || rightOffset > right.length()) {
            return false;
        }
        if (len > left.length() - leftOffset
                || len > right.length() - rightOffset) {
            return false;
        }
        return left.regionMatches(
                ignoreCase, leftOffset, right, rightOffset, len);
    }
}
~~~

Đây là **đoạn lớp tiện ích** độc lập về mặt mã nguồn Java; nếu bạn muốn lưu nó riêng, tạo file `RegionUtils.java`. Mỗi điều kiện có mục đích:

- Kiểm tra `null` để không ném `NullPointerException` ngoài ý muốn.
- Yêu cầu `len >= 0` vì độ dài âm không có ý nghĩa trong hợp đồng đã chọn.
- Kiểm tra offset theo độ dài từng chuỗi.
- So sánh với `length() - offset` để tránh phép cộng có thể tràn `int`.
- Cuối cùng mới ủy quyền cho `regionMatches()`.

Kiểm thử hàm:

~~~java
System.out.println(RegionUtils.sameRegion(
        "prefix-Java", 7, "JAVA", 0, 4, true)); // true
System.out.println(RegionUtils.sameRegion(
        null, 0, "JAVA", 0, 4, true));          // false
System.out.println(RegionUtils.sameRegion(
        "Java", 0, "Java", 0, -1, false));      // false
~~~

**Không có chính sách null duy nhất đúng cho mọi chương trình.** Một API khác có thể chọn ném `IllegalArgumentException` hoặc `NullPointerException` để chỉ ra lỗi người gọi. Quan trọng là hợp đồng rõ và kiểm thử nhất quán.

## 11. Độ phức tạp và cách sử dụng hiệu quả

Ở góc nhìn thuật toán, so hai vùng `len` đơn vị UTF-16 cần tối đa công việc tăng theo độ dài vùng, thường mô tả là **O(len)**; nếu gặp khác biệt sớm, phép so có thể dừng sớm. Bộ nhớ bổ sung ở cách sử dụng thông thường là **O(1)** vì không cần tạo hai chuỗi con riêng.

Tuy nhiên, không nên suy luận rằng mọi phiên bản JDK có cùng vi tối ưu hoặc cùng thời gian chạy cho một trường hợp cụ thể; Unicode case folding có chi phí xử lý riêng.

Thực hành hiệu quả:

- Dùng `regionMatches()` khi **đã biết vị trí bắt đầu** ở cả hai chuỗi.
- Nếu phải tìm vị trí chưa biết, dùng `indexOf()` hoặc thuật toán tìm kiếm phù hợp trước.
- Nếu cần **so toàn bộ** thì `equals()`/`equalsIgnoreCase()` sáng nghĩa hơn.
- Nếu cần so văn bản theo locale hoặc tương đương Unicode chuẩn hóa, định nghĩa yêu cầu nghiệp vụ trước khi chọn API.
- Khi so dữ liệu bí mật và cần kháng timing attacks, không giả định `regionMatches()` là phép so thời gian cố định; nó không được thiết kế để bảo đảm thuộc tính đó.

## 12. Bài tập theo mức độ

### Bài 1 — Đọc vị trí

Cho `left = "abc-JAVA-xyz"` và `right = "12-JAVA-45"`. Hãy tính offset cho hai vùng `"JAVA"` và dùng `regionMatches()` so đúng bốn đơn vị. Dự đoán kết quả trước khi chạy.

### Bài 2 — Phân biệt case

So vùng `"Java"` với `"jAvA"` lần lượt bằng dạng bốn và năm tham số. Giải thích vì sao `ignoreCase = true` thay đổi kết quả.

### Bài 3 — Tham số hợp lệ

Với hai chuỗi `"abc"` và `"ABC"`, thử `toffset = -1`, `ooffset = -1`, `len = 4`, rồi `toffset = 3`/`ooffset = 3`/`len = 0`. Ghi lý do trả `false` hoặc `true`; không nhầm vùng rỗng với vùng vượt biên.

### Bài 4 — So bằng substring và regionMatches

Viết hai cách so vùng tương ứng trong `"prefix-Java-END"` và `"Start-Java-OK"`. Đặt tên biến phù hợp để người đọc không nhầm `len` với chỉ số kết thúc của `substring()`. Chỉ ra vì sao `regionMatches()` không cần tạo chuỗi con ở mã gọi.

### Bài 5 — Một ký tự emoji khác nhau

Cho `"A😀B"` và `"X😁Y"`. Thử `len = 1` và `len = 2` tại offset `1`. Giải thích bằng UTF-16 surrogate pair. Tính lại chỉ số khi nối thêm một emoji vào đầu chuỗi.

### Bài 6 — Tạo helper an toàn

Tự cài hàm `sameRegion(...)` nhận đầu vào có thể `null`. Viết ít nhất sáu trường hợp kiểm thử: hai vùng giống, vùng khác, ignoreCase, null, offset âm, vượt biên, vùng rỗng. Giải thích vì sao kiểm tra `len > length - offset` hữu ích hơn kiểm tra cộng trong code nhận số nguyên từ ngoài.

### Bài 7 — Chọn API đúng

Với ba yêu cầu: "hai tên đầy đủ giống nhau", "chuỗi bắt đầu bằng `ERROR` tại vị trí `3`", và "vùng giữa hai đường dẫn giống nhau", hãy chọn lần lượt `equals()`, `startsWith(prefix, offset)`, hoặc `regionMatches()` và giải thích sự khác biệt.

### Bài 8 — Unicode normalization

So `"é"` với `"e\u0301"` theo `regionMatches()`. Sau đó dùng `java.text.Normalizer.normalize(..., Normalizer.Form.NFC)` cho cả hai và so lại. Giải thích vì sao hình thức hiển thị tương tự không đồng nghĩa cùng dãy đơn vị UTF-16.

## 13. Những lỗi phổ biến và checklist

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Nhầm `len` với chỉ số kết thúc | So sai vùng hoặc vượt biên | Nhớ vùng là `[offset, offset + len)` |
| Dùng offset bắt đầu từ `1` như số thứ tự | Lệch một ký tự | Chỉ số Java bắt đầu từ `0` |
| Mong `regionMatches()` so toàn bộ hai chuỗi | Có thể trả `true` khi phần khác nhau nằm ngoài vùng | Dùng `equals()` cho so toàn bộ |
| Dùng bản bốn tham số và mong bỏ qua case | `"Java"` khác `"java"` | Dùng dạng năm tham số với `ignoreCase = true` |
| Giả định `ignoreCase` là so sánh theo locale | Sai trong một số ngôn ngữ và quy tắc nghiệp vụ | Xác định locale, dùng API collation khi phù hợp |
| Cho rằng `len = 1` là một emoji | Surrogate pair có thể cần hai `char` | Đặt cận theo UTF-16 của code point |
| Truyền `other = null` | Có thể ném NPE | Kiểm tra null trước theo contract |
| Dùng `len < 0` và mong một kết quả có ý nghĩa | Yêu cầu so vùng không hợp lệ | Từ chối độ dài âm trong helper |
| Dùng `substring()` với cận sai khi chỉ muốn so | Có thể ném ngoại lệ hoặc tạo giá trị trung gian | Dùng `regionMatches()` khi vị trí biết trước |
| Tin rằng phương thức chuẩn hóa Unicode | Hai cách mã hóa cùng hình thức có thể khác | Chuẩn hóa trước nếu nghiệp vụ yêu cầu |
| Dùng nó làm phép so dữ liệu mật constant-time | Không có bảo đảm thời gian cố định | Dùng API phù hợp với bài toán bảo mật |

**Checklist trước khi gọi:**

1. Có đúng **hai chuỗi** và xác định được **hai offset**?
2. `len` là số **UTF-16 code units**, không phải chỉ số kết thúc?
3. Hai đoạn đủ độ dài? Có xử lý `null` và tham số âm?
4. Có cần bỏ qua case? Nếu có, quy tắc không phụ thuộc locale của `regionMatches(true, ...)` có đáp ứng nghiệp vụ không?
5. Nếu có emoji hoặc ký tự kết hợp, vùng có đặt cận trên đơn vị Unicode thích hợp không?
6. Kết quả `boolean` đã được kiểm tra/thực sự sử dụng chưa?

**Quy tắc nhớ:** `regionMatches()` so sánh **một vùng trong chuỗi hiện tại** với **một vùng cùng độ dài trong chuỗi khác**, trả `true/false`, không sửa dữ liệu. Chỉ số và độ dài tính theo **UTF-16**; cờ `ignoreCase` điều khiển cách so chữ hoa/chữ thường, **không thay thế so sánh ngôn ngữ tự nhiên**.

## 14. Tài liệu tra cứu chuẩn

- [Java SE 17 — String.regionMatches(int, String, int, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#regionMatches(int,java.lang.String,int,int)): overload chính xác, ý nghĩa offset/len.
- [Java SE 17 — String.regionMatches(boolean, int, String, int, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#regionMatches(boolean,int,java.lang.String,int,int)): overload có ignoreCase, quy tắc Unicode/locale.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length()`, `offsetByCodePoints()`, `equals()`, `startsWith()` và `substring()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): Unicode code points, surrogate pairs và chuyển chữ hoa/chữ thường.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html), [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): so sánh phụ thuộc locale và chuẩn hóa khi nghiệp vụ cần.
