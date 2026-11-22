# `String.indexOf(String)` và `indexOf(String, fromIndex)` — tìm chuỗi con từ vị trí chỉ định

## 1. Mục tiêu và tình huống sử dụng

`String.indexOf` tìm vị trí xuất hiện của một **chuỗi con nguyên văn** trong một `String`. Đặc biệt, overload nhận `fromIndex` cho phép chọn **vị trí bắt đầu tìm**. Bạn có thể dùng nó để xác định dấu phân cách, trích xuất một trường dữ liệu, tìm lần xuất hiện tiếp theo và liệt kê mọi lần khớp, kể cả những lần khớp **chồng lấp**.

Sau bài này, bạn cần nắm:

- `indexOf(String str)` và `indexOf(String str, int fromIndex)` khác nhau thế nào.
- `fromIndex` là **chỉ số bắt đầu tìm kiếm, bao gồm vị trí đó**; nó không phải số lượng ký tự cần bỏ qua hay chỉ số bắt đầu của chuỗi con `str`.
- Kết quả là chỉ số bắt đầu của lần khớp đầu tiên, tính theo **đơn vị mã UTF-16**; không tìm thấy thì trả về `-1`.
- Cách xử lý `fromIndex` âm, bằng/vượt `length()`, chuỗi con rỗng, chuỗi đích rỗng và `null`.
- Cách dùng `indexOf` trong vòng lặp tiến vị trí, xử lý trường hợp chồng lấp và kết hợp an toàn với `substring`.
- Những giới hạn của phép tìm kiếm nguyên văn khi nội dung có chữ hoa/chữ thường, Unicode hoặc yêu cầu khớp theo từ.

## 2. Hai overload thường dùng

Trong `java.lang.String`, Java cung cấp:

~~~java
int indexOf(String str)
int indexOf(String str, int fromIndex)
~~~

Cách đọc:

~~~java
String text = "Java JavaScript Java";

int first = text.indexOf("Java");     // 0
int second = text.indexOf("Java", 1); // 5
int third = text.indexOf("Java", 6);  // 16
~~~

`indexOf("Java")` tìm từ đầu chuỗi; có thể xem như `indexOf("Java", 0)` về **kết quả**. `indexOf("Java", 1)` loại vị trí bắt đầu `0` ra khỏi các ứng viên nên nhận vị trí `5`. `indexOf("Java", 6)` bỏ qua cả lần bắt đầu ở `5`, nên nhận vị trí `16`. Lần khớp tại index `5` có thể kéo dài qua vị trí `6`; điều kiện vẫn là **điểm bắt đầu lần khớp** phải lớn hơn hoặc bằng `fromIndex`.

Hình dung vị trí:

~~~text
Văn bản:  J a v a   J a v a S c r i p t   J a v a
Chỉ số:  0 1 2 3 4 5 6 7 8 9 ...      15 16 17 18 19

"Java" bắt đầu tại: 0, 5, 16
fromIndex = 0  -> trả 0
fromIndex = 1  -> trả 5
fromIndex = 5  -> trả 5 (bao gồm)
fromIndex = 6  -> trả 16
~~~

Trong cả hai overload, kết quả là một `int`:

- Nếu tìm thấy: `0 <= result < text.length()` với chuỗi con **không rỗng**.
- Nếu không tìm thấy: `result == -1`.
- Với **chuỗi con rỗng**, kết quả còn có thể bằng `text.length()`, vì một chuỗi rỗng khớp tại ranh giới cuối. Đây là ngoại lệ quan trọng với bất đẳng thức dành cho kết quả không rỗng.

## 3. Quy tắc chính xác của `fromIndex`

Giả sử `text` có chiều dài `n` tính bằng UTF-16 code unit, `needle` là chuỗi con cần tìm.

Với `needle` **không rỗng**, `indexOf(needle, fromIndex)` tìm lần xuất hiện sớm nhất có **vị trí bắt đầu lớn hơn hoặc bằng `max(fromIndex, 0)`**. Nếu không tồn tại thì trả `-1`.

| Tình huống | Ví dụ | Kết quả |
| --- | --- | --- |
| Tìm lần xuất hiện đầu | `"banana".indexOf("ana")` | `1` |
| Bắt đầu ngay vị trí một lần khớp | `"banana".indexOf("ana", 1)` | `1` |
| Bỏ qua vị trí khớp ban đầu | `"banana".indexOf("ana", 2)` | `3` |
| `fromIndex` âm | `"banana".indexOf("ana", -100)` | `1`, tương đương tìm từ `0` |
| `fromIndex` bằng `length()`, needle không rỗng | `"banana".indexOf("ana", 6)` | `-1` |
| `fromIndex` lớn hơn `length()`, needle không rỗng | `"banana".indexOf("ana", 999)` | `-1` |
| Chuỗi con dài hơn phần còn lại | `"banana".indexOf("ana", 4)` | `-1` |
| Không có chuỗi cần tìm | `"banana".indexOf("xyz", 0)` | `-1` |

Chú ý `fromIndex` **không phải cận cuối tìm kiếm**. Hàm vẫn có thể so khớp các ký tự sau `fromIndex`; nó chỉ giới hạn vị trí **bắt đầu** của ứng viên. Ví dụ `"banana".indexOf("ana", 2)` trả `3` vì chuỗi `"ana"` bắt đầu tại `3`.

### Chuỗi con rỗng: một quy tắc riêng

Với `needle.equals("")`, kết quả là:

~~~text
indexOf("", fromIndex) = min(max(fromIndex, 0), text.length())
~~~

Áp dụng cho `"Java"` (`length() == 4`):

| Lệnh | Kết quả |
| --- | ---: |
| `"Java".indexOf("")` | `0` |
| `"Java".indexOf("", -10)` | `0` |
| `"Java".indexOf("", 2)` | `2` |
| `"Java".indexOf("", 4)` | `4` |
| `"Java".indexOf("", 100)` | `4` |

**Vì sao không phải `-1` khi `fromIndex` quá lớn?** Một chuỗi con rỗng khớp tại mọi ranh giới hợp lệ, kể cả cuối chuỗi, và Java chặn kết quả về khoảng `[0, length()]`. Quy tắc này đặc biệt quan trọng trong vòng lặp tìm nhiều lần xuất hiện.

### Chuỗi nguồn rỗng

~~~java
String empty = "";

System.out.println(empty.indexOf("x"));    // -1
System.out.println(empty.indexOf(""));     // 0
System.out.println(empty.indexOf("", 50)); // 0
~~~

Chuỗi rỗng không chứa chuỗi con **không rỗng**, nhưng bản thân chuỗi rỗng khớp tại ranh giới duy nhất `0`.

## 4. `indexOf` làm những việc gì, và không làm những việc gì?

`indexOf(String)` tìm một **dãy ký tự liền nhau chính xác**, không phải biểu thức chính quy (regex), không tự hiểu khái niệm “từ hoàn chỉnh”, không tự chuẩn hóa Unicode và không tự bỏ qua khác biệt chữ hoa/chữ thường.

Ví dụ:

~~~java
String text = "Java JavaScript";
System.out.println(text.indexOf("Java"));   // 0
System.out.println(text.indexOf("Java", 1)); // 5
System.out.println(text.indexOf("java"));   // -1
~~~

Lần khớp ở `5` nằm **bên trong `JavaScript`**. Nếu mục tiêu là tìm từ `Java` đứng độc lập, cần kiểm tra ranh giới từ hoặc dùng một bộ phân tích có quy tắc rõ ràng. Nếu mục tiêu là tìm regex như `Ja.a`, cần `Pattern`/`Matcher`; `indexOf("Ja.a")` chỉ tìm đúng dấu chấm `.` trong văn bản.

**Phân biệt overload:** `text.indexOf('a', fromIndex)` dùng overload tìm `char/int`; `text.indexOf("a", fromIndex)` dùng overload **`String`**. Hai trường hợp đơn giản có thể cho cùng vị trí, nhưng overload tìm `int ch` còn có quy định về Unicode code point supplementary. Bài này tập trung vào tìm **chuỗi con `String`**.

## 5. Ví dụ Java 17+ đầy đủ, đã kiểm tra bằng biên dịch và chạy

Tạo tệp **`IndexOfSubstringDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class IndexOfSubstringDemo {
    public static void main(String[] args) {
        String text = "Java JavaScript Java";
        System.out.println("length=" + text.length());
        System.out.println("first=" + text.indexOf("Java"));
        System.out.println("from1=" + text.indexOf("Java", 1));
        System.out.println("from6=" + text.indexOf("Java", 6));
        System.out.println("missing=" + text.indexOf("Python", 0));
        System.out.println("negativeFrom=" + text.indexOf("Java", -100));
        System.out.println("tooLargeFrom=" + text.indexOf("Java", 999));
        System.out.println("emptyNegative=" + text.indexOf("", -3));
        System.out.println("emptyAt3=" + text.indexOf("", 3));
        System.out.println("emptyTooLarge=" + text.indexOf("", 999));
        System.out.println("nonemptyAtEnd=" + text.indexOf("Java", text.length()));
        System.out.println("emptyAtEnd=" + text.indexOf("", text.length()));

        String overlap = "bananana";
        String term = "ana";
        List<Integer> positions = new ArrayList<>();
        for (int from = 0, found;
             (found = overlap.indexOf(term, from)) != -1;
             from = found + 1) {
            positions.add(found);
        }
        System.out.println("overlapping=" + positions);

        positions.clear();
        for (int from = 0, found;
             (found = overlap.indexOf(term, from)) != -1;
             from = found + term.length()) {
            positions.add(found);
        }
        System.out.println("nonOverlapping=" + positions);

        String email = "user@example.com";
        int separator = email.indexOf("@");
        String domain = separator >= 0 ? email.substring(separator + 1) : "";
        System.out.println("domain=" + domain);

        String emoji = Character.toString(0x1F600);
        String mixed = "A" + emoji + "B" + emoji;
        System.out.println("mixedLength=" + mixed.length());
        System.out.println("emojiFirst=" + mixed.indexOf(emoji));
        System.out.println("emojiNext=" + mixed.indexOf(emoji, 2));
        System.out.println("lowSurrogate=" + mixed.indexOf(String.valueOf(mixed.charAt(2))));
        System.out.println("caseSensitive=" + "Java".indexOf("java"));
    }
}
~~~

Biên dịch/chạy (đã kiểm tra ở chế độ tương thích Java 17):

~~~bash
javac --release 17 -encoding UTF-8 IndexOfSubstringDemo.java
java IndexOfSubstringDemo
~~~

`stdout` chính xác:

~~~text
length=20
first=0
from1=5
from6=16
missing=-1
negativeFrom=0
tooLargeFrom=-1
emptyNegative=0
emptyAt3=3
emptyTooLarge=20
nonemptyAtEnd=-1
emptyAtEnd=20
overlapping=[1, 3, 5]
nonOverlapping=[1, 5]
domain=example.com
mixedLength=6
emojiFirst=1
emojiNext=4
lowSurrogate=2
caseSensitive=-1
~~~

**Giải thích kết quả:**

1. `"Java JavaScript Java"` có `length() == 20`. `"Java"` xuất hiện tại UTF-16 index `0`, `5`, `16`; các giá trị `fromIndex` lần lượt chọn vị trí tương ứng.
2. Với `fromIndex = -100`, tìm như từ `0`. Với `999`, chuỗi con `"Java"` không thể có vị trí bắt đầu hợp lệ nên trả `-1`.
3. Chuỗi con rỗng khớp ở biên `0`, `3` hoặc `20` sau khi chặn `fromIndex` theo `length()`; needle không rỗng tại `fromIndex = 20` trả `-1`.
4. Trong `"bananana"`, `"ana"` bắt đầu tại `1`, `3`, `5`. Tăng `from = found + 1` cho phép khớp chồng lấp; tăng `found + term.length()` bỏ qua các ký tự đã khớp.
5. Vị trí `'@'` trong email được kiểm tra trước khi gọi `substring(separator + 1)`, tránh xử lý dữ liệu theo kết quả `-1` như thể là một vị trí tìm thấy.
6. `mixed` có sáu code unit UTF-16 vì mỗi emoji `U+1F600` dùng hai code unit. Hai emoji bắt đầu tại index `1` và `4`; vẫn có thể tìm riêng low surrogate tại index `2` nếu cố ý tạo một chuỗi con chỉ gồm code unit đó.
7. `"Java".indexOf("java")` trả `-1`: phép tìm này phân biệt hoa/thường.

## 6. Tìm lần xuất hiện tiếp theo bằng `fromIndex`

Bài toán thường gặp: “Tôi đã tìm thấy một kết quả; làm sao tiếp tục?”

Với chuỗi con `needle` **không rỗng**, ta chọn:

- **Cho phép chồng lấp:** `nextFrom = found + 1` (tăng một **UTF-16 code unit**).
- **Không cho phép chồng lấp:** `nextFrom = found + needle.length()` (đi qua toàn bộ dãy vừa khớp).

Ví dụ `"bananana"` và `"ana"`:

~~~text
Chuỗi:   b a n a n a n a
Index:   0 1 2 3 4 5 6 7
"ana":     1..3
"ana":         3..5
"ana":             5..7
Cho chồng lấp:        [1, 3, 5]
Không chồng lấp:      [1, 5]
~~~

Mẫu tổng quát khi muốn tìm **mọi vị trí bắt đầu, kể cả chồng lấp**:

~~~java
static List<Integer> allPositions(String text, String needle) {
    if (needle.isEmpty()) {
        throw new IllegalArgumentException("needle phải không rỗng");
    }

    List<Integer> positions = new ArrayList<>();
    for (int from = 0, found;
         (found = text.indexOf(needle, from)) != -1;
         from = found + 1) {
        positions.add(found);
    }
    return positions;
}
~~~

Đoạn trên là **phương thức minh họa**, cần import `java.util.List` và `java.util.ArrayList` khi đặt vào một class Java hoàn chỉnh (như ví dụ `IndexOfSubstringDemo`).

Điều kiện `needle.isEmpty()` không thể bỏ qua tùy tiện. Nếu tìm `""` trong vòng lặp chỉ kết thúc khi thấy `-1`, sẽ có nguy cơ **lặp vô hạn**: khi `from` vượt `length()`, `indexOf("", from)` vẫn trả `length()`, không bao giờ thành `-1`. Nếu nghiệp vụ cần vị trí của tất cả các khoảng rỗng, định nghĩa riêng `0, 1, ..., text.length()`, tức `length() + 1` ranh giới UTF-16, thay vì dùng mẫu tìm needle không rỗng.

Đối với khớp không chồng lấp, thay đúng một dòng `from = found + 1` bằng `from = found + needle.length()`; vẫn phải giữ điều kiện needle không rỗng.

### Cẩn thận với giá trị `-1`

Không bao giờ coi `-1` là một vị trí hợp lệ của `substring` hay `charAt`:

~~~java
String record = "name=value";
int equalsAt = record.indexOf("=");

if (equalsAt >= 0) {
    String name = record.substring(0, equalsAt);
    String value = record.substring(equalsAt + 1);
    System.out.println(name + " => " + value);
}
~~~

Nếu không thấy dấu phân cách và vẫn thực hiện `substring(0, equalsAt)`, bạn sẽ truyền `-1` làm chỉ số và nhận lỗi vượt biên. Trong một số trường hợp như `substring(indexOf("@") + 1)`, kết quả `-1 + 1 == 0` **không ném lỗi** nhưng lại âm thầm lấy toàn bộ chuỗi; đây cũng là lỗi logic cần tránh.

## 7. Ý nghĩa của kết quả index khi có Unicode

Java `String` dùng UTF-16. Các API `length()`, `substring(...)` và `indexOf(String, fromIndex)` làm việc theo **chỉ số code unit UTF-16**.

Ví dụ:

~~~text
Giá trị hiển thị:     A       😀       B       😀
Code point:         U+0041  U+1F600  U+0042  U+1F600

Chỉ số UTF-16:         0    1    2      3    4    5
Code unit:            0041 D83D DE00   0042 D83D DE00
                             \__/                \__/
                           một CP              một CP
String.length() == 6
~~~

Vì vậy:

~~~java
String emoji = Character.toString(0x1F600);
String s = "A" + emoji + "B" + emoji;

System.out.println(s.indexOf(emoji));     // 1
System.out.println(s.indexOf(emoji, 2));  // 4
~~~

Kết quả `1` và `4` là **vị trí UTF-16**, không phải số thứ tự code point. `fromIndex = 2` nằm giữa surrogate pair đầu tiên, vì thế nó không tìm lại emoji bắt đầu tại `1`; lần emoji kế tiếp bắt đầu tại `4`.

Quan trọng hơn, `indexOf(String)` so khớp các **đơn vị UTF-16 liền nhau** nên một needle cố ý chứa **một surrogate code unit đơn lẻ** vẫn có thể được tìm thấy bên trong cặp surrogate:

~~~java
String lowHalf = String.valueOf(s.charAt(2));
System.out.println(s.indexOf(lowHalf)); // 2
~~~

Nếu muốn thao tác với Unicode code point hoàn chỉnh, tự bảo đảm needle/ranh giới không cắt giữa cặp surrogate. Nếu cần **vị trí tính bằng code point**, có thể chuyển chỉ số UTF-16 `matchIndex` sang số code point trước vị trí khớp:

~~~java
int matchIndex = s.indexOf(emoji);
if (matchIndex >= 0) {
    int codePointsBefore = s.codePointCount(0, matchIndex);
    System.out.println(codePointsBefore); // 1
}
~~~

Điều này giả định `matchIndex` là ranh giới code point hợp lệ. Đối với khớp surrogate lẻ, không thể coi kết quả là một ranh giới ký tự Unicode hoàn chỉnh.

Ngoài ra, chuỗi Unicode có thể có nhiều cách mã hóa nhìn giống nhau (ví dụ ký tự `é` đơn nhất và `e` cộng dấu kết hợp). `indexOf` **không chuẩn hóa NFC/NFD** trước khi tìm. Nếu nghiệp vụ cần so khớp tương đương chuẩn hóa, có thể dùng `java.text.Normalizer` để chuẩn hóa dữ liệu **và needle** theo chính sách thống nhất trước khi so sánh; khi chuyển về chuỗi đã chuẩn hóa, nhớ rằng index trả về thuộc **chuỗi sau chuẩn hóa**, có thể không ánh xạ trực tiếp sang chuỗi ban đầu.

## 8. Phân biệt với `contains`, `startsWith` và `lastIndexOf`

| Mục đích | API phù hợp | Kết quả |
| --- | --- | --- |
| Chỉ cần biết có chứa chuỗi con không | `text.contains(needle)` | `boolean` |
| Cần vị trí lần đầu | `text.indexOf(needle)` | `int`, hoặc `-1` |
| Cần tìm lần đầu từ một vị trí | `text.indexOf(needle, fromIndex)` | `int`, hoặc `-1` |
| Cần kiểm tra tiền tố tại vị trí cụ thể | `text.startsWith(prefix, offset)` | `boolean` |
| Cần tìm từ phải sang trái | `text.lastIndexOf(needle)` hoặc `lastIndexOf(needle, fromIndex)` | `int`, hoặc `-1` |
| Cần biểu thức chính quy hoặc nhóm capture | `java.util.regex.Pattern` và `Matcher` | Match có quy tắc regex |

`contains` thuận tiện khi không dùng index, nhưng không trả vị trí. `startsWith(prefix, offset)` kiểm tra **chính xác tại offset**, còn `indexOf(prefix, offset)` có thể tìm thấy ở **bất kỳ vị trí nào từ offset trở về sau**. `lastIndexOf` có chiều tìm và quy tắc `fromIndex` riêng, không thể lấy nguyên các ví dụ của `indexOf` để suy ra tất cả hành vi của nó.

## 9. Tìm kiếm phân biệt hoa/thường và theo “từ”

`indexOf` có phân biệt chữ hoa và chữ thường:

~~~java
String headline = "Java Core";
System.out.println(headline.indexOf("java")); // -1
~~~

Nếu nghiệp vụ cần không phân biệt hoa/thường, không nên mặc định rằng gọi `toLowerCase()` là giải pháp chính xác cho mọi ngôn ngữ và mọi tình huống. Chuyển đổi hoa/thường có thể phụ thuộc locale, làm thay đổi độ dài UTF-16 và thay đổi ý nghĩa chỉ số; Unicode case folding và grapheme matching có quy tắc riêng.

Với văn bản giới hạn trong ASCII và mục tiêu chỉ là kiểm tra có chứa hay không, có thể chuẩn hóa đầu vào theo chính sách cố định (chẳng hạn `Locale.ROOT`). Nếu bạn cần **chỉ số trong chuỗi gốc**, kiểm tra cách ánh xạ index sau biến đổi; không mặc định chỉ số của chuỗi đã lowercase trùng tuyệt đối với vị trí trong chuỗi gốc. Với tìm kiếm ngôn ngữ tự nhiên, cân nhắc `Collator` hoặc công cụ tìm kiếm phù hợp.

`indexOf("Java")` cũng có thể tìm thấy `"Java"` trong `"JavaScript"`. Nếu yêu cầu “nguyên từ”, cần quy tắc ranh giới (khoảng trắng, dấu câu, ký tự Unicode, v.v.) hoặc regex cụ thể, không chỉ một lời gọi `indexOf`.

## 10. Hiệu năng và sử dụng đúng

- `indexOf` thích hợp cho **tìm kiếm chuỗi con nguyên văn**, nhất là khi đầu vào và quy tắc tìm đơn giản.
- Kết quả được đo bằng **UTF-16 offset**. Nếu dùng tiếp trong `substring`, bạn có thể dùng trực tiếp index khi ranh giới đúng và đã kiểm tra `-1`.
- Không thể suy ra một **độ phức tạp thực thi cố định** từ chữ ký API; cách tìm và tối ưu của JDK có thể thay đổi. Với chuỗi rất lớn hoặc tìm nhiều mẫu phức tạp, hãy đo trên dữ liệu thật.
- Nếu quét cùng một nội dung nhiều lần, tránh vô ý tạo ra nhiều bản sao chuỗi lớn và cân nhắc dữ liệu/thuật toán có cấu trúc phù hợp với bài toán.
- `fromIndex` không tự sửa nội dung chuỗi. `String` immutable; mỗi lời gọi chỉ trả vị trí tìm thấy theo chuỗi hiện tại.
- Không giả định kết quả sẽ là chỉ số theo ký tự người dùng hiển thị (grapheme cluster). Muốn cắt theo code point hay grapheme, cần chuyển đổi ranh giới phù hợp.

## 11. Những lỗi phổ biến

1. **Nhầm `fromIndex` là vị trí bắt đầu trong needle.** Thực tế nó là vị trí tìm kiếm trên **chuỗi nguồn**.
2. **Bỏ qua tính bao gồm của `fromIndex`.** `indexOf("ana", 1)` trên `"banana"` trả ngay `1`; để tìm lần kế tiếp, dùng `found + 1` hoặc `found + needle.length()` tùy chính sách chồng lấp.
3. **Không xử lý `-1`.** Có thể dẫn đến exception trong `substring` hoặc lỗi âm thầm nếu cộng `1` vào `-1`.
4. **Dùng vòng lặp cho phép needle rỗng.** Vì `indexOf("", hugeIndex) == length()`, vòng lặp chờ `-1` có thể không bao giờ kết thúc.
5. **Cho rằng `fromIndex` quá lớn luôn trả `-1`.** Ngoại lệ là tìm **chuỗi con rỗng**: trả `length()`.
6. **Tăng fromIndex thêm `needle.length()` khi cần bắt các kết quả chồng lấp.** Sẽ bỏ sót `3` trong ví dụ `"bananana"`.
7. **Cho rằng `indexOf` là regex hoặc không phân biệt hoa/thường.** Hàm tìm **nguyên văn, phân biệt hoa/thường** và không xét ranh giới từ.
8. **Quên rằng kết quả là UTF-16 index.** Có thể cắt đôi surrogate pair nếu dùng index tùy tiện cho văn bản Unicode.
9. **Không phân biệt `null` và `""`.** `text.indexOf((String) null)` ném `NullPointerException`; còn `text.indexOf("")` hợp lệ và trả `0`.
10. **Dùng index sau chuẩn hóa Unicode/hoa-thường trên chuỗi gốc mà không kiểm tra.** Các phép biến đổi có thể làm thay đổi số code unit; chỉ số phải thuộc đúng chuỗi được tìm.

## 12. Bài tập tự kiểm tra

**Câu 1.** `"ababab".indexOf("ab", 2)` trả bao nhiêu?

**Đáp án:** `2`, vì `fromIndex` bao gồm vị trí `2`.

**Câu 2.** `"banana".indexOf("ana", 2)` trả bao nhiêu? Vì sao?

**Đáp án:** `3`. Lần khớp ở `1` bắt đầu trước `fromIndex`, còn lần khớp tại `3` được phép.

**Câu 3.** `"Java".indexOf("", 999)` và `"Java".indexOf("a", 999)` khác nhau thế nào?

**Đáp án:** trả lần lượt `4` và `-1`; needle rỗng được chặn về ranh giới cuối chuỗi.

**Câu 4.** Với `"bananana"` và needle `"ana"`, cách tăng từ lần khớp `found` nào bắt đủ `[1, 3, 5]`?

**Đáp án:** `from = found + 1`. Nếu tăng `found + needle.length()` sẽ thu được `[1, 5]`.

**Câu 5.** Nếu `indexOf("@")` trả `-1`, có nên gọi `substring(index + 1)` ngay không?

**Đáp án:** không. `-1 + 1` trở thành `0` và có thể trả toàn chuỗi như một kết quả sai nghiệp vụ. Cần kiểm tra `index >= 0` trước.

**Câu 6.** Vì sao vị trí emoji thứ hai trong `"A😀B😀"` là UTF-16 index `4`?

**Đáp án:** chữ `A` dùng một code unit; emoji đầu dùng hai code unit ở index `1` và `2`; chữ `B` ở index `3`, nên emoji thứ hai bắt đầu tại index `4`.

**Câu 7.** `text.indexOf(needle, fromIndex)` có thể trả index **nhỏ hơn** `fromIndex` khi `fromIndex` không âm không?

**Đáp án:** không đối với needle không rỗng; nó chỉ chấp nhận các lần khớp có vị trí bắt đầu `>= fromIndex`. Riêng needle rỗng và `fromIndex > length()`, kết quả bị chặn về `length()`, nhỏ hơn `fromIndex`.

## 13. Tài liệu tham khảo

- [Oracle Java SE 17 — `String.indexOf(String)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#indexOf(java.lang.String)): tìm lần đầu của chuỗi con nguyên văn.
- [Oracle Java SE 17 — `String.indexOf(String, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#indexOf(java.lang.String,int)): ngữ nghĩa `fromIndex`, kết quả `-1` và needle rỗng.
- [Oracle Java SE 17 — `String.substring`, `codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): các API dùng/đổi UTF-16 index.
- [Oracle Java SE 17 — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): code point, surrogate pair, UTF-16.

**Ghi nhớ:** `indexOf(needle, fromIndex)` trả **UTF-16 index bắt đầu** của lần xuất hiện đầu tiên có vị trí `>= fromIndex` hoặc `-1`. `fromIndex` âm được hiểu là bắt đầu từ `0`; chuỗi con rỗng có quy tắc riêng theo `length()`. Khi tìm nhiều lần, tăng điểm bắt đầu theo chính sách **có/không chồng lấp**, và luôn kiểm tra `-1` trước khi dùng index để trích xuất.