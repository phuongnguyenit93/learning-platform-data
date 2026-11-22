# Unicode escape trong mã nguồn Java và thứ tự xử lý của trình biên dịch

## 1. Mục tiêu

Sau bài này, bạn có thể giải thích vì sao `\u0041` trong mã nguồn Java có thể trở thành chữ `A` **trước khi** trình biên dịch nhận diện chuỗi, ký tự, từ khóa hay chú thích; phân biệt Unicode escape ở mức **mã nguồn** với escape của `String`/`char`; dự đoán các trường hợp có dấu gạch chéo ngược, xuống dòng, dấu nháy; và viết mã an toàn, dễ đọc khi cần xử lý Unicode.

Trọng tâm là **thứ tự xử lý văn bản nguồn của `javac`**. Đây không phải một API xử lý chuỗi khi chương trình đang chạy.

## 2. Unicode escape là gì?

Trong **tệp nguồn `.java`**, Unicode escape có dạng:

~~~text
\uXXXX
~~~

- `\` và `u` là ký tự ASCII; `XXXX` là **đúng bốn chữ số hệ 16** (`0–9`, `a–f`, `A–F`).
- Có thể có nhiều chữ `u` liên tiếp, ví dụ `\uuuu0041` cũng tạo ra `A`.
- Mỗi escape đại diện cho **một đơn vị mã UTF-16** (UTF-16 code unit) từ `U+0000` đến `U+FFFF`. Vì vậy `\u0041` → `A`, `\u03A9` → `Ω`; một code point bổ sung như `U+1F600` cần **hai** đơn vị surrogate (`\uD83D\uDE00`).
- Dạng `\u{1F600}`, `\U0001F600` hay chỉ ba/chín chữ số hex **không phải** cú pháp Unicode escape của Java.
- Escape được xử lý ở **khắp văn bản nguồn**, kể cả vùng sau `//`, giữa `/* ... */`, bên trong literal chuỗi, literal ký tự và text block. Nó không phụ thuộc vào phạm vi cú pháp mà mắt người nhìn thấy.

Ví dụ ở mức văn bản nguồn: `cl\u0061ss` tạo thành từ khóa `class`; `\u002f\u002f` tạo thành hai dấu `//`; `\u000a` tạo thành ký tự LF xuống dòng. **Đó là phép dịch ký tự trước khi Java phân tích cú pháp**, không phải các phép thay thế diễn ra lúc chạy chương trình.

## 3. Trình biên dịch xử lý theo thứ tự nào?

Theo *Java Language Specification* (JLS) `3.2–3.5, tiến trình từ tệp mã nguồn đến token có ba giai đoạn dịch từ vựng:

~~~text
Byte trong tệp .java
    |
    v
Giải mã byte thành ký tự nguồn (chẳng hạn UTF-8)
    |
    v
(1) Dịch Unicode escape hợp lệ: \uXXXX -> một UTF-16 code unit
    |
    v
(2) Nhận diện kết thúc dòng: CR, LF, CRLF
    |
    v
(3) Phân tách input elements: khoảng trắng, comment, token
    |
    v
Phân tích cú pháp, kiểm tra kiểu, tạo bytecode, ...
~~~

Điều quan trọng là **bước (1) xảy ra trước bước (2) và (3)**. Vì thế:

- Nếu `\u000a` xuất hiện trong nội dung một dòng `//`, nó trở thành LF **trước lúc** nhận diện ranh giới chú thích. Phần phía sau LF có thể là mã Java hoạt động.
- Nếu `\u0022` tạo ra dấu `"`, dấu đó tham gia xác định **ranh giới chuỗi**. Nó không được tự động hiểu là một dấu nháy thuộc *giá trị* chuỗi.
- Nếu `\u005c` tạo ra `\`, ký tự đó có thể ảnh hưởng đến cú pháp literal được phân tích **sau đó**; việc dịch Unicode escape không tự chạy lại đệ quy.
- Một Unicode escape tạo ra chữ thường cũng có thể nằm trong tên biến, từ khóa hoặc toán tử: thứ tự này không giới hạn trong `String`.

Lưu ý: mã hóa tệp (`UTF-8`, v.v.) là việc giải mã **byte**; Unicode escape là chuỗi ký tự **ASCII viết trong mã nguồn**. Có thể dùng ký tự `Ω` trực tiếp trong tệp UTF-8 hoặc viết `\u03A9`; hai cách tạo cùng đơn vị mã trong ví dụ này. Khi môi trường mã hóa nguồn không được bảo đảm, chỉ rõ `-encoding UTF-8` lúc biên dịch.

## 4. Ví dụ chạy được với Java 17+

Tạo tệp **`UnicodeEscapeDemo.java`** với nội dung sau (giữ nguyên các dấu `\` trong source):

~~~java
public class UnicodeEscapeDemo {
    public static void main(String[] args) {
        String literalA = "A";
        String sourceEscapeA = "\u0041";
        String visibleEscapeText = "\\u0041";
        char omega = '\u03A9';
        String emoji = "\uD83D\uDE00";

        System.out.println(literalA.equals(sourceEscapeA));
        System.out.println(sourceEscapeA);
        System.out.println(visibleEscapeText);
        System.out.println((int) omega);
        System.out.println(emoji.length());
        System.out.println(emoji.codePointCount(0, emoji.length()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UnicodeEscapeDemo.java
java UnicodeEscapeDemo
~~~

Kết quả chuẩn:

~~~text
true
A
\u0041
937
2
1
~~~

Giải thích từng kết quả:

1. `"\u0041"` được dịch thành `"A"` **trước** khi quét token nên so sánh với `"A"` trả về `true`.
2. `sourceEscapeA` chứa đúng ký tự `A`.
3. `"\\u0041"` là một chuỗi gồm **hai** gạch chéo ngược ở mã nguồn, theo sau bởi `u0041`. Quy tắc chọn dấu `\` hợp lệ ngăn dấu thứ hai mở đầu Unicode escape; đến khi phân tích literal, `\\` mới cho ra **một** gạch chéo ngược trong chuỗi kết quả, nên in nguyên văn `\u0041`.
4. `\u03A9` là `Ω`, đơn vị UTF-16 có giá trị thập phân `937`.
5. `\uD83D\uDE00` biểu diễn một code point bổ sung bằng **hai** `char` UTF-16: `length()` bằng `2`, nhưng `codePointCount(...)` bằng `1`. Không lấy độ dài `String` làm số ký tự Unicode theo nghĩa code point.

Lưu ý rằng kết quả trên không cần thư viện Unicode đặc biệt; đó là đặc tả về cách trình biên dịch hiểu **ký tự viết trong nguồn**.

## 5. Các bẫy do dịch Unicode escape quá sớm

### 5.1. `\u000a` có thể kết thúc chú thích `//`

Tệp **`CommentEscapeDemo.java`**:

~~~java
public class CommentEscapeDemo {
    public static void main(String[] args) {
        System.out.println("Truoc");
        // \u000a System.out.println("Sau");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CommentEscapeDemo.java
java CommentEscapeDemo
~~~

Output:

~~~text
Truoc
Sau
~~~

Tại sao? Bước (1) biến `\u000a` thành LF. Bước (2) xác định đó là xuống dòng thật. Bước (3) chỉ coi nội dung **trước** LF là phần của comment `//`; lệnh `System.out.println("Sau");` giờ nằm sau ranh giới comment và được thực thi. Một cách tương tự, ký tự CR `\u000d` cũng có thể kết thúc dòng.

**Quy tắc khi review code:** đừng cho rằng các ký tự `\uXXXX` trong comment chắc chắn là văn bản vô hại. Khi phân tích code lạ, cần xét phép dịch trước khi kết luận đoạn nào là chú thích.

### 5.2. Không dùng Unicode escape để viết CR/LF bên trong literal

Hai ví dụ sau **cố ý không biên dịch được**:

~~~java
String badLine = "Dong 1\u000aDong 2";
char badLf = '\u000a';
~~~

`\u000a` trở thành LF **trước lúc** trình biên dịch xử lý chuỗi/`char`, nên một line terminator xuất hiện giữa dấu nháy; hai literal này không hợp lệ. Để đặt ký tự xuống dòng vào **giá trị** chuỗi hoặc ký tự, viết:

~~~java
String goodLine = "Dong 1\nDong 2";
char goodLf = '\n';
String windowsBreak = "\r\n";
~~~

Escape `\n`/`\r` được diễn giải **khi phân tích nội dung literal**, sau giai đoạn Unicode escape. Vì vậy chúng không làm vỡ cú pháp mã nguồn.

### 5.3. Unicode escape thành dấu nháy hoặc gạch chéo ngược

Đây cũng là ví dụ **cố ý sai cú pháp**:

~~~java
String badQuote = "\u0022";
char badApostrophe = '\u0027';
String badSlash = "\u005c";
~~~

- `\u0022` đổi thành dấu nháy kép `"`, khiến dấu nháy mở/đóng literal bị thay đổi (dòng thứ nhất không phải một chuỗi chứa dấu nháy).
- `\u0027` đổi thành `'`, không tạo `char` chứa dấu nháy đơn như ý định.
- `\u005c` đổi thành `\`. Trong dòng thứ ba, dấu `\` ngay trước dấu nháy đóng có thể escape dấu nháy đó và làm literal không kết thúc hợp lệ.

Viết escape **của literal**, không dùng Unicode escape sớm, để biểu diễn các ký tự đặc biệt:

~~~java
String quote = "\"";
char apostrophe = '\'';
String slash = "\\";
~~~

Các câu lệnh cuối đều hợp lệ: `quote` chứa `"`, `apostrophe` chứa `'`, `slash` chứa một ký tự `\`.

### 5.4. Không dịch Unicode escape nhiều lần

Ví dụ raw source `\u005cu005a`: escape `\u005c` sinh ra `\`, sau đó các ký tự `u005a` vẫn giữ nguyên. **Trình biên dịch không xem lại** ký tự `\` vừa được sinh ra để dịch tiếp thành `Z`. Kết quả giai đoạn Unicode là chuỗi ký tự nguồn `\u005a`, **không phải** chữ `Z`. Nếu đặt chuỗi ký tự đó bên trong literal Java, `\u` có thể trở thành escape sequence **không hợp lệ** ở giai đoạn literal; không nên coi ví dụ này là một literal chạy được.

Cần diễn đạt rõ hai ý khác nhau: ký tự tạo ra từ Unicode escape không tự khởi động một lượt dịch mới; nhưng một dấu `\` viết **trực tiếp** trong raw source xuất hiện sau một Unicode escape có thể được xét theo quy tắc chọn dấu gạch chéo tiếp theo.

## 6. Dấu `\` nào được phép mở đầu Unicode escape?

Khi duyệt đầu vào thô, **không phải mọi** `\u` đều được chuyển thành ký tự. JLS `3.3 có quy tắc về *eligible backslash* (dấu gạch chéo ngược đủ điều kiện):

- Với `\` ASCII đang xét, nếu ký tự raw gần nhất **được sinh ra bởi một Unicode escape trước đó**, `\` hiện tại đủ điều kiện mở đầu escape mới.
- Trường hợp còn lại, đếm số dấu `\` liên tiếp ngay trước nó trong kết quả dịch cho tới ký tự không phải `\` (hoặc đầu dữ liệu): nếu số đó **chẵn**, `\` hiện tại đủ điều kiện; nếu **lẻ**, không đủ điều kiện.
- Nếu dấu đủ điều kiện được theo sau bởi một hoặc nhiều `u` nhưng không có đúng bốn ký tự hex hợp lệ theo sau, đó là **lỗi biên dịch** (không được âm thầm coi là văn bản bình thường).
- Ký tự đã được sinh ra bởi Unicode escape **không tự trở thành một escape mới**.

Trong thực hành với `String`, các trường hợp cần nhớ:

| Văn bản viết trong `.java` | Ý nghĩa khi xử lý | Kết quả mong đợi |
| --- | --- | --- |
| `"\u0041"` | Unicode escape được dịch sớm | Chuỗi chứa `A` |
| `"\\u0041"` | Hai dấu `\` thô đứng cạnh; dấu thứ hai không đủ điều kiện Unicode escape | Chuỗi chứa đúng sáu ký tự `\u0041` |
| `"\uu0041"` | Có nhiều `u`, vẫn hợp lệ | Chuỗi chứa `A` |
| `"\n"` | Escape của literal, không phải Unicode escape | Chuỗi có một LF |
| `"\u000a"` | LF thật được tạo trước lúc nhận diện chuỗi | **Không biên dịch** |
| `'\u03A9'` | Escape nguồn thành một đơn vị UTF-16 | `char` có giá trị `Ω` |
| `"\uD83D\uDE00"` | Hai surrogate UTF-16 | `String.length() == 2` |

Ví dụ nâng cao: raw literal `"\\\u006e"` có ba dấu `\` liên quan (hai dấu đầu thô, dấu thứ ba mở đầu `\u006e`). Dịch Unicode cho phần nội dung `\\n`; giai đoạn escape của literal đọc thành ký tự LF. Đây là minh họa vì sao **quy tắc chẵn/lẻ** và **thứ tự hai giai đoạn** phải được áp dụng riêng rẽ. Trong code thường ngày, hãy viết `"\n"` vì rõ ý định hơn.

## 7. Phân biệt ba lớp thường bị nhầm

| Lớp xử lý | Diễn ra khi nào? | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| Giải mã nguồn | Trước dịch từ vựng, đọc byte `.java` | File lưu UTF-8 có `Ω` | Ký tự nguồn `Ω` |
| **Unicode escape nguồn** | Sớm nhất trong ba bước dịch từ vựng của Java | `\u03A9` | Một đơn vị UTF-16 `Ω` trong luồng nguồn |
| **Escape literal** | Khi đã xác định token chuỗi/`char` | `\n`, `\t`, `\\`, `\"` | LF, tab, dấu `\`, dấu `"` trong giá trị |
| Nội dung `String` lúc chạy | Sau biên dịch, phụ thuộc dữ liệu/API | `"\\u0041"` | Sáu ký tự `\`, `u`, `0`, `0`, `4`, `1`; Java không tự dịch thành `A` |

Đặc biệt, `String.translateEscapes()` là API dành cho **escape sequence kiểu literal**; nó không phải bộ phân tích cú pháp `\uXXXX` cho dữ liệu runtime. Nếu nhập từ JSON, database, HTTP hoặc người dùng một chuỗi chứa sáu ký tự `\u0041`, việc có diễn giải thành `A` hay không phụ thuộc **định dạng/protocol/parser** cụ thể. Không thể suy ra từ cơ chế Unicode escape của file `.java`.

## 8. Áp dụng đúng và tránh lỗi

1. **Ưu tiên ký tự trực tiếp** trong nguồn UTF-8 khi dễ đọc: `"Cà phê"`, `"Ω"`. Unicode escape hữu ích khi cần biểu diễn code unit khó gõ hoặc muốn nêu rõ giá trị hex.
2. **Ưu tiên `\n`, `\r`, `\t`, `\"`, `\'`, `\\` trong literal**; tránh `\u000a`, `\u000d`, `\u0022`, `\u0027`, `\u005c` để thay cho các escape ấy, vì việc dịch sớm thay đổi token hóa.
3. **Kiểm tra comment chứa `\uXXXX`**, nhất là escape của CR/LF hay ký tự cấu trúc. IDE syntax highlighting có thể tô comment theo raw text; kết luận cuối cùng phải theo parser/compiler.
4. **Phân biệt code unit và code point**. Một `char` chỉ chứa một code unit UTF-16. Code point ngoài BMP thường cần một cặp surrogate; dùng `codePointCount` hoặc API code point khi đếm ký tự Unicode theo code point.
5. **Đọc lỗi theo từng giai đoạn**. Nếu `javac` báo chuỗi không đóng hoặc escape bất hợp lệ ở vị trí khó hiểu, kiểm tra `\u` trong nguồn trước. Một ký tự tạo sớm có thể gây lỗi ở tokenization hoặc parsing muộn hơn.
6. **Không tạo Unicode escape bằng nối chuỗi tại runtime rồi mong trình biên dịch dịch lại**. Ví dụ `String text = "\\" + "u0041";` tạo ra sáu ký tự thường; Java không biên dịch lại nội dung của `text`.

## 9. Tự kiểm tra

**Câu 1.** Vì sao `"\\u0042"` in `\u0042` chứ không in `B`?

**Đáp án:** vì chuỗi gạch chéo thô liền nhau khiến dấu thứ hai không đủ điều kiện mở Unicode escape; khi phân tích literal, `\\` cho ra một dấu `\` và `u0042` còn nguyên.

**Câu 2.** Đoạn `// \u000a System.out.println("X");` trong thân phương thức có thể in `X` không?

**Đáp án:** có; `\u000a` trở thành LF trước khi xác định điểm kết thúc `//`, nên câu lệnh sau LF được phân tích như mã lệnh.

**Câu 3.** Dùng `'\u000a'` hay `'\n'` để tạo `char` LF?

**Đáp án:** `'\n'`; `'\u000a'` tạo xuống dòng trong mã nguồn quá sớm và gây lỗi biên dịch.

**Câu 4.** Tại sao `"\uD83D\uDE00".length()` bằng `2`, dù đại diện một biểu tượng Unicode?

**Đáp án:** `String.length()` đếm **code unit UTF-16**, còn ký tự ở code point bổ sung cần một cặp surrogate (hai code unit).

## 10. Tài liệu chuẩn

- [Java Language Specification §3.2 — Lexical Translations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.2).
- [Java Language Specification §3.3 — Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.3).
- [Java Language Specification §3.4 — Line Terminators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.4).
- [Java Language Specification §3.10 — Literals và escape sequences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10).

**Ghi nhớ:** Unicode escape của Java được dịch **trước** khi nhận diện dòng, comment và literal. Khi cần một ký tự đặc biệt **trong giá trị chuỗi**, dùng escape của literal; khi cần hiểu cách trình biên dịch đọc **mã nguồn**, áp dụng quy tắc Unicode escape và dấu `\` đủ điều kiện trước tiên.