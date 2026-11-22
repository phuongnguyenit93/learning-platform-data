# `lastIndexOf` và hướng tìm ngược trong Java

`String.lastIndexOf(...)` dùng để tìm **lần xuất hiện cuối cùng** của một ký tự hoặc chuỗi con, tính theo chỉ số trong `String`. Nó hữu ích khi cần dấu phân cách cuối cùng, phần mở rộng tệp, vị trí dấu gạch chéo cuối trong đường dẫn, hoặc khi muốn tìm ngược từ một vị trí xác định.

Khác biệt quan trọng với `indexOf` là **hướng tìm và vị trí khớp được chọn**. Cả hai trả về một chỉ số bắt đầu tính từ **0 ở đầu chuỗi**, không phải khoảng cách đếm từ cuối. Nếu không tìm thấy thì trả về `-1`.

> Quy tắc trọng tâm: `lastIndexOf` chọn vị trí bắt đầu của **lần khớp nằm xa về phía bên phải nhất** trong phạm vi tìm kiếm; `fromIndex`, nếu có, giới hạn phạm vi tìm từ phải sang trái.

## 1. Bốn overload của `String.lastIndexOf`

`String` trong Java cung cấp bốn overload chính:

| Phương thức | Tìm gì? | Bắt đầu ở đâu? |
| --- | --- | --- |
| `lastIndexOf(int ch)` | Một Unicode code point được biểu diễn bằng `int` | Từ cuối chuỗi về đầu |
| `lastIndexOf(int ch, int fromIndex)` | Code point `ch` | Từ vị trí `fromIndex` (bao gồm vị trí đó) trở về đầu |
| `lastIndexOf(String str)` | Toàn bộ chuỗi con `str` | Lần xuất hiện cuối trong chuỗi nguồn |
| `lastIndexOf(String str, int fromIndex)` | Toàn bộ chuỗi con `str` | Lần khớp có **chỉ số bắt đầu** không vượt quá `fromIndex` |

Mỗi overload trả về `int`: **chỉ số đầu tiên của đoạn khớp** trên thang vị trí UTF-16 của chuỗi nguồn, hoặc `-1` khi không khớp.

Các overload `int` nhận Unicode code point. Với ký tự thông thường trong Basic Multilingual Plane (BMP), bạn có thể truyền một literal kiểu `char` vì Java tự nâng `char` thành `int`. Với code point ngoài BMP (ví dụ một số emoji), `int` cho phép tìm cả cặp surrogate như một code point; điều này được giải thích ở phần Unicode.

Các overload nhận `String str` đòi hỏi đối số `str` không phải `null`. Đối số `null` không phải «không tìm thấy»: nó gây `NullPointerException`. Nếu bạn cần xử lý trường hợp thiếu chuỗi tìm kiếm, hãy kiểm tra và quyết định chính sách ở phía gọi.

## 2. Tìm lần xuất hiện cuối cùng nhưng trả chỉ số tính từ đầu

Xét `"abracadabra"`:

```text
Giá trị: a b r a c a d a b r a
Chỉ số: 0 1 2 3 4 5 6 7 8 9 10
```

Ký tự `'a'` xuất hiện ở các vị trí `0`, `3`, `5`, `7` và `10`. Do đó:

- `indexOf('a')` trả về `0`: lần xuất hiện đầu tiên.
- `lastIndexOf('a')` trả về `10`: lần xuất hiện cuối cùng.
- `lastIndexOf("bra")` trả về `8`: đoạn `"bra"` cuối cùng bắt đầu tại chỉ số 8.
- `lastIndexOf("missing")` trả về `-1`: không có đoạn khớp.

Tên `lastIndexOf` mô tả cách **chọn kết quả**; chỉ số vẫn là chỉ số của Java tính từ đầu. Không được lấy `length() - result` để xem đó là vị trí trả về của phương thức. Nếu bài toán thật sự cần khoảng cách đến cuối, bạn mới tự tính từ chỉ số đã tìm được theo đúng ý nghĩa bài toán.

### Ví dụ 1: phân biệt `indexOf` và `lastIndexOf`

Tạo tệp `LastIndexOfBasicsDemo.java`:

```java
public class LastIndexOfBasicsDemo {
    public static void main(String[] args) {
        String text = "abracadabra";

        System.out.println(text.indexOf('a'));
        System.out.println(text.lastIndexOf('a'));
        System.out.println(text.indexOf("bra"));
        System.out.println(text.lastIndexOf("bra"));
        System.out.println(text.lastIndexOf("BRA"));
        System.out.println(text.lastIndexOf('z'));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LastIndexOfBasicsDemo.java
java LastIndexOfBasicsDemo
```

Kết quả:

```text
0
10
1
8
-1
-1
```

`"BRA"` không khớp với `"bra"` vì các phép tìm này **phân biệt chữ hoa và chữ thường**. `lastIndexOf` không tự bỏ dấu, chuẩn hóa Unicode, tách từ hay áp dụng quy tắc ngôn ngữ tự nhiên.

## 3. `fromIndex`: tìm ngược từ vị trí được chỉ định

Hai overload có `fromIndex` cho phép giới hạn phần nguồn được xét:

```java
lastIndexOf(int ch, int fromIndex)
lastIndexOf(String str, int fromIndex)
```

Tìm theo hướng **giảm chỉ số**, từ khu vực gần `fromIndex` sang bên trái. Với một ký tự thuộc BMP, vị trí `fromIndex` được kiểm tra **bao gồm cả chính nó** nếu hợp lệ.

Ví dụ:

```text
String text = "abracadabra";

Index:   0 1 2 3 4 5 6 7 8 9 10
Text:    a b r a c a d a b r a
                 ^
           fromIndex = 6
```

Lệnh `text.lastIndexOf('a', 6)` không xét `'a'` ở 7 hay 10; nó đi ngược từ chỉ số 6 và gặp `'a'` ở 5, nên trả `5`. Tương tự, `text.lastIndexOf('a', 3)` trả `3` vì vị trí bắt đầu **được tính vào phạm vi tìm kiếm**.

Một điểm quan trọng hơn với *chuỗi con*: `fromIndex` giới hạn **vị trí bắt đầu của lần khớp**, không nhất thiết giới hạn tất cả ký tự của lần khớp ở bên trái `fromIndex`.

Ví dụ `"abcd".lastIndexOf("bcd", 1)` trả về `1` dù phần khớp có các ký tự ở chỉ số `2` và `3`. Đoạn khớp bắt đầu ở chỉ số 1 nên vẫn thỏa điều kiện.

### Ví dụ 2: vị trí bắt đầu được tính vào kết quả

Tạo `LastIndexOfFromIndexDemo.java`:

```java
public class LastIndexOfFromIndexDemo {
    public static void main(String[] args) {
        String text = "abracadabra";

        System.out.println(text.lastIndexOf('a', 6));
        System.out.println(text.lastIndexOf('a', 3));
        System.out.println(text.lastIndexOf('a', -1));
        System.out.println(text.lastIndexOf('a', 99));

        System.out.println(text.lastIndexOf("bra", 8));
        System.out.println(text.lastIndexOf("bra", 7));

        System.out.println("abcd".lastIndexOf("bcd", 1));
        System.out.println("abcd".lastIndexOf("bcd", 0));
    }
}
```

```bash
javac LastIndexOfFromIndexDemo.java
java LastIndexOfFromIndexDemo
```

Kết quả:

```text
5
3
-1
10
8
1
1
-1
```

Giải thích:

1. Khi `fromIndex` là 6, vị trí `'a'` gần nhất tính về bên trái là 5.
2. Khi `fromIndex` là 3, ký tự `'a'` ngay tại chỉ số 3 được tính.
3. Khi `fromIndex < 0`, không có vị trí bắt đầu hợp lệ nên kết quả là `-1`.
4. Khi `fromIndex` vượt quá chỉ số cuối, tìm ký tự bắt đầu hiệu quả từ vị trí cuối hợp lệ; kết quả là 10.
5. Với `"bra"`, vị trí bắt đầu 8 được tính trong `lastIndexOf("bra", 8)`; khi giới hạn `fromIndex = 7` thì tìm lần khớp trước đó ở 1.
6. `"bcd"` bắt đầu tại 1 nên `lastIndexOf("bcd", 1)` hợp lệ, dù đoạn khớp kéo dài qua chỉ số 3.

Nếu bạn định nghĩa «chỉ tìm trong **tiền tố** kết thúc tại một chỉ số», cần kiểm soát ranh giới đoạn khớp thay vì giả định `fromIndex` tự cắt dữ liệu đầu vào.

## 4. Một chuỗi con có thể khớp nhiều lần, kể cả chồng lấp

`lastIndexOf(String)` tìm toàn bộ dãy ký tự liên tiếp. Các lần xuất hiện chồng lấp vẫn là ứng viên hợp lệ.

Ví dụ `"bananana"` có đoạn `"ana"` bắt đầu ở các chỉ số `1`, `3` và `5`:

```text
b a n a n a n a
0 1 2 3 4 5 6 7
  └─ana─┘
      └─ana─┘
          └─ana─┘
```

Do đó:

- `lastIndexOf("ana")` → `5`.
- `lastIndexOf("ana", 4)` → `3`.
- `lastIndexOf("ana", 2)` → `1`.
- `lastIndexOf("ana", 0)` → `-1`.

### Ví dụ 3: tìm ngược nhiều lần

Tạo `ReverseSearchDemo.java`:

```java
public class ReverseSearchDemo {
    public static void main(String[] args) {
        String text = "bananana";

        System.out.println(text.indexOf("ana"));
        System.out.println(text.lastIndexOf("ana"));
        System.out.println(text.lastIndexOf("ana", 4));
        System.out.println(text.lastIndexOf("ana", 2));
        System.out.println(text.lastIndexOf("ana", 0));

        int at = text.lastIndexOf("ana");
        while (at >= 0) {
            System.out.println("match = " + at);
            at = text.lastIndexOf("ana", at - 1);
        }
    }
}
```

```bash
javac ReverseSearchDemo.java
java ReverseSearchDemo
```

Kết quả:

```text
1
5
3
1
-1
match = 5
match = 3
match = 1
```

Trong vòng lặp, `at - 1` bảo đảm lần tìm tiếp theo xét các **vị trí bắt đầu nhỏ hơn** vị trí vừa tìm thấy. Nếu gọi lại với đúng `at`, kết quả có thể là chính vị trí hiện tại và tạo vòng lặp vô hạn. Mẫu trên liệt kê được cả những lần khớp **chồng lấp**. Nếu muốn bỏ khớp chồng lấp, chính sách cập nhật chỉ số cần được thiết kế theo mục tiêu riêng.

## 5. Biên đặc biệt: chuỗi trống, vị trí âm và vị trí vượt độ dài

Các cạnh biên dễ bị bỏ qua nhất nằm ở overload tìm **chuỗi con rỗng**.

Với một chuỗi `s` có độ dài `n`:

- `s.lastIndexOf("")` trả về `n`, vì chuỗi rỗng có thể khớp ở ranh giới ngay sau ký tự cuối.
- `s.lastIndexOf("", fromIndex)` trả về `min(fromIndex, n)` nếu `fromIndex >= 0`; nếu `fromIndex < 0`, trả về `-1`.
- Với chuỗi tìm kiếm **không rỗng**, `fromIndex < 0` trả về `-1`; `fromIndex` quá lớn sẽ được giới hạn vào các vị trí bắt đầu có thể khớp.
- `s.lastIndexOf("longer-than-source")` trả về `-1` nếu toàn bộ chuỗi con không thể nằm trong `s`.
- `s.lastIndexOf((String) null)` gây `NullPointerException`, khác với kết quả `-1` khi không tìm thấy.

### Ví dụ 4: kiểm thử ranh giới một cách có chủ đích

Tạo `LastIndexOfEdgeCasesDemo.java`:

```java
public class LastIndexOfEdgeCasesDemo {
    public static void main(String[] args) {
        String text = "abc";

        System.out.println(text.lastIndexOf(""));
        System.out.println(text.lastIndexOf("", 1));
        System.out.println(text.lastIndexOf("", 100));
        System.out.println(text.lastIndexOf("", -1));

        System.out.println(text.lastIndexOf("abcd"));
        System.out.println(text.lastIndexOf('b', 100));
        System.out.println(text.lastIndexOf('b', -1));

        String empty = "";
        System.out.println(empty.lastIndexOf(""));
        System.out.println(empty.lastIndexOf('a'));
    }
}
```

```bash
javac LastIndexOfEdgeCasesDemo.java
java LastIndexOfEdgeCasesDemo
```

Kết quả:

```text
3
1
3
-1
-1
1
-1
0
-1
```

**Không đồng nhất chuỗi rỗng với «không tìm thấy».** Nếu một tham số tìm kiếm rỗng là không hợp lệ trong nghiệp vụ, hãy kiểm tra `needle.isEmpty()` trước khi gọi, thay vì dựa vào `lastIndexOf` để trả `-1`.

## 6. Chỉ số của `lastIndexOf` theo UTF-16, không phải vị trí ký tự hiển thị

`String` lưu các ký tự với ngữ nghĩa chỉ số **UTF-16 code unit**. Một ký tự Unicode ngoài BMP (ví dụ U+1F600) được biểu diễn bằng **hai `char`** — một cặp surrogate. Vì thế chỉ số trả về của `lastIndexOf` cũng là **vị trí code unit**, không phải vị trí đếm theo code point hoặc grapheme cluster.

Có hai cách tìm đáng phân biệt:

- `lastIndexOf(int ch)` có thể nhận một Unicode code point hợp lệ ngoài BMP, ví dụ `0x1F600`, và tìm cặp surrogate tương ứng. Kết quả là chỉ số UTF-16 của **high surrogate**, tức vị trí bắt đầu của cặp.
- `lastIndexOf(String str)` tìm chính xác dãy code unit có trong chuỗi con `str`. Có thể dùng một chuỗi chứa đủ cặp surrogate.
- `lastIndexOf(char)` không phải overload độc lập; truyền một `char` gọi overload `int` sau khi nâng kiểu. Một `char` đơn lẻ không thể biểu diễn toàn bộ code point ngoài BMP.

### Ví dụ 5: tìm emoji bằng Unicode code point

Tạo `LastIndexOfUnicodeDemo.java`:

```java
public class LastIndexOfUnicodeDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B\uD83D\uDE00";
        int emoji = 0x1F600;

        System.out.println(text.length());
        System.out.println(text.lastIndexOf(emoji));
        System.out.println(text.lastIndexOf(emoji, 3));
        System.out.println(text.lastIndexOf("\uD83D\uDE00"));
        System.out.println(text.lastIndexOf('\uDE00'));
        System.out.println(text.codePointCount(0, text.length()));
    }
}
```

```bash
javac LastIndexOfUnicodeDemo.java
java LastIndexOfUnicodeDemo
```

Kết quả:

```text
6
4
1
4
5
4
```

Chuỗi hiển thị là `A😀B😀`: bốn code point nhưng sáu UTF-16 code unit. Emoji đầu có high surrogate ở vị trí 1; emoji cuối ở vị trí 4. `lastIndexOf(emoji, 3)` tìm lùi từ khu vực chỉ số 3 và gặp emoji đầu ở 1. Tìm riêng low surrogate `'\uDE00'` cho kết quả 5, nhưng đó chỉ là **nửa sau của cặp surrogate cuối**, không đại diện cho cả emoji.

Lưu ý bổ sung: ngay cả khi đếm theo code point, một ký tự mà người dùng nhìn thấy có thể gồm nhiều code point (ví dụ ký tự kết hợp dấu hoặc emoji ghép). Nếu cần tìm kiếm theo **grapheme cluster** hay quy tắc ngôn ngữ tự nhiên, `lastIndexOf` không tự cung cấp chức năng đó.

## 7. Tình huống thực tế: lấy phần sau dấu phân cách cuối

Khi biết dữ liệu có cấu trúc đơn giản với dấu phân cách cố định, `lastIndexOf` kết hợp `substring` là giải pháp trực tiếp.

Giả sử tên tệp là `report.final.csv` và cần lấy phần mở rộng cuối:

```java
String filename = "report.final.csv";
int dot = filename.lastIndexOf('.');
String extension = dot >= 0 ? filename.substring(dot + 1) : "";
```

Kết quả `extension` là `"csv"`. `dot + 1` đúng vì `substring(beginIndex)` bắt đầu **sau** dấu chấm. Nếu dấu chấm không xuất hiện, `lastIndexOf` trả `-1`. Trong ví dụ trên, ta chủ động chọn giá trị rỗng cho trường hợp không có dấu chấm.

### Ví dụ 6: xử lý nhiều tên tệp

Tạo `FileExtensionDemo.java`:

```java
public class FileExtensionDemo {
    static String extension(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot < 0 ? "" : filename.substring(dot + 1);
    }

    public static void main(String[] args) {
        System.out.println(extension("report.final.csv"));
        System.out.println(extension("README"));
        System.out.println("[" + extension("notes.") + "]");
        System.out.println(extension(".env"));
    }
}
```

```bash
javac FileExtensionDemo.java
java FileExtensionDemo
```

Kết quả:

```text
csv

[]
env
```

Trong đầu ra có **một dòng trống** sau `csv` vì `README` không có dấu chấm. `"notes."` có dấu chấm cuối nên `substring(dot + 1)` là chuỗi rỗng được in dưới dạng `[]`. Với `".env"`, hàm đơn giản coi `"env"` là phần mở rộng; nhiều quy ước về tệp ẩn lại coi `.env` là **tên tệp không có phần mở rộng**.

**Giới hạn của ví dụ:** đây là quy tắc xử lý *chuỗi tên tệp*, không phải parser đường dẫn đầy đủ. Một dấu chấm trong tên thư mục, đường dẫn URL, file ẩn hoặc quy ước nhiều phần mở rộng có thể cần chính sách khác. Trong ứng dụng cần xử lý đường dẫn đa nền tảng, cân nhắc `java.nio.file.Path` để tách tên tệp khỏi đường dẫn trước khi áp dụng logic phần mở rộng.

## 8. Tình huống thực tế: lấy đoạn sau dấu phân cách nhiều ký tự

Khi dấu phân cách có nhiều ký tự, cần cộng **độ dài của toàn bộ dấu phân cách**, không chỉ cộng 1.

```java
String message = "region::team::member";
String separator = "::";
int at = message.lastIndexOf(separator);
String last = at < 0 ? message : message.substring(at + separator.length());
```

Kết quả `last` là `"member"`. Nếu bạn cộng `at + 1`, kết quả sẽ chứa dư một dấu `':'` ở đầu.

### Ví dụ 7: tìm phần cuối và kiểm soát lỗi

Tạo `LastSegmentDemo.java`:

```java
public class LastSegmentDemo {
    static String lastSegment(String text, String separator) {
        if (separator.isEmpty()) {
            throw new IllegalArgumentException("separator must not be empty");
        }

        int at = text.lastIndexOf(separator);
        return at < 0 ? text : text.substring(at + separator.length());
    }

    public static void main(String[] args) {
        System.out.println(lastSegment("a::b::c", "::"));
        System.out.println(lastSegment("single", "::"));
        System.out.println("[" + lastSegment("a::", "::") + "]");
    }
}
```

```bash
javac LastSegmentDemo.java
java LastSegmentDemo
```

Kết quả:

```text
c
single
[]
```

Hàm lựa chọn trả toàn bộ đầu vào khi không có dấu phân cách, và trả chuỗi rỗng nếu dấu phân cách nằm cuối. Đây là **chính sách nghiệp vụ** được viết rõ trong code, không phải tính năng tự động của `lastIndexOf`. Hàm cũng chặn dấu phân cách rỗng vì `lastIndexOf("")` có ngữ nghĩa riêng, thường không phù hợp để tách phân đoạn.

## 9. So sánh `indexOf` và `lastIndexOf` khi lựa chọn cách tìm

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Tìm vị trí **đầu tiên** của ký tự hoặc chuỗi con | `indexOf(...)` |
| Tìm vị trí **cuối cùng** của ký tự hoặc chuỗi con | `lastIndexOf(...)` |
| Tìm lần xuất hiện đầu ở vị trí ≥ `fromIndex` | `indexOf(..., fromIndex)` |
| Tìm lần xuất hiện cuối có vị trí bắt đầu ≤ `fromIndex` | `lastIndexOf(..., fromIndex)` |
| Kiểm tra có chứa một chuỗi con cụ thể hay không | `contains(...)` hoặc `indexOf(...) >= 0` |
| Kiểm tra tiền tố/hậu tố cụ thể | `startsWith(...)` / `endsWith(...)` |
| Tìm theo biểu thức chính quy, nhóm bắt, tập ký tự | `Pattern`/`Matcher` và regex thích hợp |

`lastIndexOf` tìm **literal** ký tự hoặc chuỗi con. Ví dụ `lastIndexOf(".")` tìm dấu chấm thực, không diễn giải `"."` là «mọi ký tự» như trong regex. Khi chỉ cần dấu phân cách cuối, không cần regex.

`lastIndexOf` có thể được JVM tối ưu ở mức implementation, nhưng API không cam kết một độ phức tạp hay kiểu bộ nhớ duy nhất cho mọi JVM. Không nên đưa ra kết luận hiệu năng tuyệt đối nếu chưa đo trên dữ liệu và runtime thực tế.

## 10. Những lỗi dễ mắc

**Lỗi 1 — tưởng kết quả đếm từ cuối.** `lastIndexOf` trả **chỉ số từ đầu chuỗi**. Với `"abcabc"`, `lastIndexOf("abc") == 3`, không phải 0.

**Lỗi 2 — dùng `fromIndex` như chỉ số loại trừ.** Khác với `endIndex` trong `substring`, `fromIndex` trong `lastIndexOf` được tính **bao gồm**. Muốn bỏ vị trí khớp hiện tại, thường cần gọi lại với `at - 1`.

**Lỗi 3 — nghĩ chuỗi con phải nằm hoàn toàn bên trái `fromIndex`.** `fromIndex` hạn chế **vị trí bắt đầu**, không nhất thiết hạn chế vị trí kết thúc đoạn khớp. `"abcd".lastIndexOf("bcd", 1)` trả 1.

**Lỗi 4 — không kiểm tra `-1`.** `substring(text.lastIndexOf("::") + 2)` có thể xử lý sai khi dấu phân cách vắng mặt vì `-1 + 2 == 1`. Hãy kiểm tra vị trí khớp trước khi cắt chuỗi.

**Lỗi 5 — cộng 1 cho dấu phân cách nhiều ký tự.** Với `"::"`, phải cộng `separator.length()` khi lấy phần sau đoạn khớp.

**Lỗi 6 — bỏ qua chuỗi rỗng.** `lastIndexOf("")` trả độ dài chuỗi, không trả `-1`. Hãy tự định nghĩa có cho phép tìm chuỗi rỗng hay không.

**Lỗi 7 — giả định tìm kiếm không phân biệt hoa thường.** `"Java".lastIndexOf("java") == -1`. Nếu muốn xử lý không phân biệt hoa thường, cần quy tắc so sánh riêng, đặc biệt khi có Unicode và locale.

**Lỗi 8 — coi `char` là mọi ký tự Unicode.** Một code point ngoài BMP chiếm hai UTF-16 code unit. Dùng overload `int` với code point đúng, hoặc dùng chuỗi con hoàn chỉnh, và hiểu chỉ số trả về.

**Lỗi 9 — dùng `lastIndexOf` như parser ngữ nghĩa.** Tìm dấu `'.'` cuối chỉ là thao tác trên chuỗi; nó không tự biết phần mở rộng tệp, định dạng URL, escape sequence hay quy tắc đường dẫn.

**Lỗi 10 — quên rằng chuỗi nguồn bất biến.** `lastIndexOf` chỉ đọc `String` và trả vị trí, không sửa nội dung hay dịch con trỏ tìm kiếm bên trong chuỗi.

## 11. Tự kiểm tra

### Câu 1: tìm ngược có chỉ số bắt đầu

Cho:

```java
String text = "one-two-two";
System.out.println(text.lastIndexOf("two"));
System.out.println(text.lastIndexOf("two", 5));
System.out.println(text.lastIndexOf('-', 6));
```

Đáp án:

```text
8
4
3
```

`"two"` xuất hiện tại 4 và 8; tìm từ vị trí 5 chỉ có thể chọn khớp bắt đầu ở 4. Dấu `'-'` ở chỉ số 3 và 7; tìm ngược từ 6 gặp chỉ số 3.

### Câu 2: chuỗi tìm kiếm rỗng

Cho:

```java
String text = "xyz";
System.out.println(text.lastIndexOf(""));
System.out.println(text.lastIndexOf("", 1));
System.out.println(text.lastIndexOf("", -1));
```

Đáp án:

```text
3
1
-1
```

Vị trí ranh giới ngay sau ký tự cuối cũng là một vị trí khớp hợp lệ của chuỗi rỗng.

### Câu 3: lấy hậu tố sau dấu hai chấm cuối

Với `String text = "a:b:c";`, viết phép cắt để lấy `"c"`.

Lời giải:

```java
int separator = text.lastIndexOf(':');
String tail = separator < 0 ? text : text.substring(separator + 1);
```

Biến `tail` có giá trị `"c"`. Đây là một đoạn mã minh họa đặt trong phương thức có biến `text` đã khai báo.

### Câu 4: các lần khớp chồng lấp

Với `"aaaa"`, đoạn `"aa"` bắt đầu ở các chỉ số `0`, `1`, `2`. Vì vậy `lastIndexOf("aa")` trả `2`, còn `lastIndexOf("aa", 1)` trả `1`. Tính chồng lấp không khiến một vị trí khớp hợp lệ bị loại bỏ.

## Ghi nhớ

**`lastIndexOf` tìm từ phải sang trái nhưng trả về chỉ số bắt đầu tính từ trái sang phải.** Overload với `fromIndex` tìm các lần khớp có vị trí bắt đầu không lớn hơn ranh giới đó; ranh giới được tính **bao gồm**. Kết quả `-1` nghĩa là không tìm thấy, còn tìm chuỗi rỗng là một trường hợp đặc biệt có kết quả hợp lệ. Khi dùng chỉ số để cắt đoạn văn bản, hãy kiểm tra `-1`, cộng đúng độ dài dấu phân cách, và nhớ rằng các chỉ số của `String` dùng UTF-16 code unit.