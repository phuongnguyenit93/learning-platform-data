# Lớp ký tự theo script và thuộc tính Unicode trong Java Regex

## 1. Mục tiêu và phạm vi

Khi xử lý tên người, văn bản đa ngôn ngữ, tìm kiếm hoặc kiểm tra một chuỗi, các khoảng ASCII như `[A-Za-z]` chỉ nhận chữ cái tiếng Anh không dấu. Java cung cấp các **lớp ký tự dựa trên thuộc tính Unicode** trong `java.util.regex.Pattern`, giúp diễn đạt rõ hơn “chữ thuộc hệ chữ Latin”, “một chữ cái bất kỳ”, “chữ số thập phân” hoặc “một ký tự trong khối Unicode”.

Sau bài này, bạn có thể:
- Phân biệt **script**, **block**, **general category** và **binary property**; chọn thuộc tính đúng với yêu cầu.
- Viết và kết hợp `\p{...}`, `\P{...}`, lớp ký tự, phép giao/trừ trong regex Java.
- Áp dụng các lớp đó qua `Pattern`/`Matcher`; hiểu ảnh hưởng của cờ Unicode và cách biểu diễn dấu tiếng Việt.
- Nhận ra giới hạn của regex Unicode khi xử lý combining mark, ký tự ngoài BMP và dữ liệu cần bảo mật.

Các cú pháp cốt lõi này có từ Java 7 và **vẫn được hỗ trợ trong các JDK hiện đại**. Ví dụ bên dưới được viết cho Java 17+; tính tập hợp ký tự cụ thể phụ thuộc phiên bản dữ liệu Unicode đi kèm JDK đang chạy.

## 2. Bốn cách phân loại ký tự Unicode

Một ký tự Unicode có thể đồng thời mang nhiều thuộc tính. Ví dụ, `é` là một **chữ cái viết thường** (general category `Ll`), thuộc **script Latin**, và thuộc một **block** nhất định. Đây là các chiều phân loại khác nhau, không thay thế cho nhau.

| Thuộc tính | Ý nghĩa | Cú pháp Java Regex | Khi nên dùng |
| --- | --- | --- | --- |
| **Script** | Hệ chữ mà mã ký tự được gán, ví dụ Latin, Han, Cyrillic, Hiragana | `\p{sc=Latin}`, `\p{IsHan}` | Lọc/nhận biết hệ chữ |
| **Block** | Khoảng mã liên tiếp được đặt tên trong bảng Unicode | `\p{InGreek}`, `\p{blk=Basic_Latin}` | Xử lý một vùng mã cụ thể |
| **General category** | Loại ký tự: letter, mark, number, punctuation, symbol… | `\p{L}`, `\p{gc=Lu}`, `\p{Nd}` | Kiểm tra loại ký tự không phụ thuộc ngôn ngữ |
| **Binary property** | Thuộc tính đúng/sai: Alphabetic, White_Space, Uppercase… | `\p{IsAlphabetic}`, `\p{IsWhite_Space}` | Kiểm tra một đặc tính Unicode |

**Đơn vị xét** là *Unicode code point*, không nhất thiết là một ký tự hiển thị hoàn chỉnh. Một chữ có dấu có thể gồm một code point đã ghép sẵn (ví dụ `é`) hoặc hai code point (`e` rồi đến dấu sắc kết hợp U+0301). Chúng có thể nhìn giống nhau nhưng được regex phân loại khác nhau.

### 2.1. Script: `\p{sc=...}` và `\p{Is...}`

Script mô tả hệ chữ. Java `Pattern` nhận tên script thông qua `Character.UnicodeScript`; hai kiểu viết sau tương đương:

~~~regex
\p{sc=Latin}
\p{script=Latin}
\p{IsLatin}
~~~

Một số ví dụ đang hữu ích:
- `\p{sc=Latin}`: chữ thuộc hệ Latin như `A`, `é`, `ắ` (ở dạng code point dựng sẵn).
- `\p{sc=Han}` hoặc `\p{IsHan}`: chữ Hán.
- `\p{sc=Hiragana}`: chữ Hiragana; `\p{sc=Katakana}`: Katakana.
- `\p{sc=Arabic}`, `\p{sc=Cyrillic}`, `\p{sc=Greek}`: các hệ chữ tương ứng.
- `\p{sc=Common}`: các ký tự dùng chung cho nhiều hệ chữ; `\p{sc=Inherited}`: nhiều dấu kết hợp có script kế thừa theo ngữ cảnh.

Không được suy ra “mọi thứ xuất hiện trong một từ tiếng Việt đều có script Latin”: dấu kết hợp tách rời có thể thuộc `Inherited`; chữ số và nhiều dấu câu thuộc `Common`. Vì vậy `\p{sc=Latin}+` phù hợp để tìm **chuỗi liên tiếp các code point Latin**, nhưng có thể không nhận nguyên vẹn một từ ở dạng Unicode phân rã.

Script là thuộc tính của code point, **không phải công cụ nhận diện ngôn ngữ**: tiếng Việt, tiếng Anh và nhiều ngôn ngữ khác cùng dùng chữ Latin; nhiều ngôn ngữ cũng dùng kết hợp nhiều hệ chữ.

### 2.2. Block: `\p{In...}` và `\p{blk=...}`

Block là vùng mã Unicode. Cú pháp:

~~~regex
\p{InBasic_Latin}
\p{block=Basic_Latin}
\p{blk=Basic_Latin}
\p{InGreek}
~~~

**Script khác block.** Ký tự `7` thuộc block `Basic_Latin` (vùng ASCII) nhưng không thuộc script `Latin`. Ngược lại, nhiều chữ Latin có dấu ở các block khác `Basic_Latin`. Tương tự, lọc chữ Greek bằng block `Greek` có thể bỏ sót ký tự Greek trong các block khác như `Greek_Extended`.

Nếu yêu cầu là “chữ viết hệ Latin”, thường chọn script; nếu yêu cầu thực sự gắn với một vùng mã Unicode, mới chọn block. Block không phải định nghĩa đầy đủ về một ngôn ngữ.

### 2.3. General category: `\p{L}`, `\p{Nd}`, `\p{gc=...}`

General category phân loại theo chức năng của **từng code point**, không theo hệ chữ.

| Category | Nghĩa | Ví dụ mục đích |
| --- | --- | --- |
| `L` | Tất cả chữ cái (`Lu`, `Ll`, `Lt`, `Lm`, `Lo`) | Tên chứa chữ thuộc nhiều hệ chữ |
| `Lu`, `Ll` | Chữ hoa, chữ thường | Kiểm tra kiểu chữ |
| `Lo` | Chữ cái loại “other letter” | Chữ không có cặp hoa/thường |
| `M` | Dấu kết hợp (`Mn`, `Mc`, `Me`) | Hỗ trợ văn bản Unicode phân rã |
| `Nd` | Chữ số thập phân của nhiều hệ chữ | Nhận số 0–9 và chữ số thập phân Unicode |
| `N` | Mọi loại số Unicode, rộng hơn `Nd` | Phân loại số, không nhất thiết dùng để nhập số |
| `P` | Dấu câu | Phân tách dấu câu |
| `Zs` | Ký tự khoảng cách dạng separator | Một số khoảng trắng Unicode |
| `Sc` | Ký hiệu tiền tệ (currency symbol) | Nhận dấu tiền tệ |

Ví dụ `\p{L}+` nhận dãy chữ cái thuộc nhiều script, trong khi `\p{Lu}+` nhận chữ hoa; `\p{gc=Lu}` và `\p{general_category=Lu}` là các cách viết tương đương. **`\p{Sc}` (chữ S viết hoa)** là category *currency symbol*, không phải tên viết tắt `sc=` của thuộc tính script.

Để kiểm tra số thập phân theo Unicode dùng `\p{Nd}`; nếu giao diện, giao thức hoặc mã định danh yêu cầu đúng chữ số ASCII, dùng `[0-9]`. Đừng mặc định `\p{N}` là “chỉ các chữ số 0–9”.

### 2.4. Binary property: `\p{Is...}`

Các thuộc tính đúng/sai được `Pattern` hỗ trợ gồm:

~~~regex
\p{IsAlphabetic}
\p{IsUppercase}
\p{IsWhite_Space}
\p{IsDigit}
\p{IsIdeographic}
~~~

`\p{IsAlphabetic}` không hoàn toàn đồng nghĩa `\p{L}`: thuộc tính *Alphabetic* có thể bao gồm một số code point ngoài general category Letter. `\p{IsWhite_Space}` cũng không nên nhầm với việc chỉ dùng ký tự dấu cách ASCII `' '`.

Chỉ dùng tên property được **`java.util.regex.Pattern` hỗ trợ trên JDK mục tiêu**. Cú pháp từ JavaScript, Python, ICU hoặc PCRE có thể khác; ví dụ `\p{scx=Latin}` (Script_Extensions) không phải cú pháp được `Pattern` Java 17/21 tài liệu hóa, nên không chuyển nguyên xi từ engine khác sang.

## 3. Cú pháp nhóm và phép toán trên lớp ký tự

| Regex | Ý nghĩa |
| --- | --- |
| `\p{sc=Latin}` | Một code point có script Latin |
| `\P{sc=Latin}` | Một code point **không** có script Latin |
| `\p{L}+` | Một hoặc nhiều code point thuộc category Letter |
| `[\p{sc=Latin}\p{M}]` | Một code point Latin **hoặc** Mark |
| `[\p{sc=Latin}&&[\p{L}]]` | Một code point **vừa** thuộc script Latin **vừa** thuộc Letter |
| `[\p{L}&&[^\p{Lu}]]` | Một Letter **trừ** những chữ có category Lu |
| `(?:\p{sc=Latin}\p{M}*)+` | Nhiều cụm “code point Latin theo sau bởi 0+ Mark” |

Lưu ý `\P{sc=Latin}` cũng có thể khớp số, khoảng trắng, emoji, dấu câu…; nó không có nghĩa “chữ thuộc script khác Latin”. Muốn **chữ** không phải Latin, có thể dùng phép giao `[\p{L}&&[^\p{sc=Latin}]]`.

Với regex Java, ký tự `&&` thực hiện **giao hai lớp**; lớp phủ định bên trong `[^...]` giúp thực hiện phép trừ. Có thể dùng thuộc tính trong hoặc ngoài ngoặc vuông `[...]`. Toán tử `+` lượng hóa lớp/cụm phía trước, chứ không tự biến thuộc tính thành điều kiện cho cả chuỗi.

## 4. Viết đúng trong Java và chọn chế độ khớp

Trong **ngôn ngữ regex**, bạn gõ `\p{sc=Latin}+` (một dấu `\\`). Nhưng khi viết regex dưới dạng **Java string literal**, dấu gạch chéo ngược phải được escape:

~~~java
Pattern latin = Pattern.compile("\\p{sc=Latin}+");
boolean whole = latin.matcher("Café").matches();
Matcher matcher = latin.matcher("Java, 漢字, Café");
while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Đoạn trên là **trích đoạn minh họa**, cần import `Pattern` và `Matcher`; chương trình đầy đủ nằm ở mục 5.

- `matches()` yêu cầu regex khớp **toàn bộ chuỗi**. Hợp với kiểm tra định dạng đầu vào.
- `find()` tìm các **đoạn con** liên tiếp khớp biểu thức. Hợp với tìm/tô sáng văn bản.
- Nếu viết regex có neo, `\A` và `\z` đánh dấu đầu/cuối tuyệt đối; `^`/`$` chịu ảnh hưởng quy tắc dòng và cờ `MULTILINE`.
- Nên `Pattern.compile(...)` một lần rồi tái sử dụng `Pattern` khi xử lý nhiều chuỗi; tạo `Matcher` riêng cho từng lần khớp.

## 5. Ví dụ chạy được trên Java 17+

Lưu tệp tên **`UnicodeRegexDemo.java`** (mã nguồn UTF-8). Chương trình minh họa script, block, category, Unicode decimal digit, chuẩn hóa và các đoạn văn bản tìm được.

~~~java
import java.text.Normalizer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeRegexDemo {
    static void check(String label, String regex, String input) {
        System.out.println(label + ": " + Pattern.matches(regex, input));
    }

    public static void main(String[] args) {
        check("Latin Café", "\\p{sc=Latin}+", "Café");
        check("Latin abc123", "\\p{sc=Latin}+", "abc123");
        check("Han 漢字", "\\p{IsHan}+", "漢字");
        check("Letters Việt", "\\p{L}+", "Việt");
        check("ASCII digit ٣", "[0-9]+", "٣");
        check("Unicode digit ٣", "\\p{Nd}+", "٣");

        String decomposed = "Cafe\u0301"; // e + combining acute accent
        check("NFD Latin", "\\p{sc=Latin}+", decomposed);
        check("NFC Latin", "\\p{sc=Latin}+",
              Normalizer.normalize(decomposed, Normalizer.Form.NFC));

        check("Block includes 7", "\\p{InBasic_Latin}+", "7");
        check("Latin script excludes 7", "\\p{sc=Latin}+", "7");

        String deseret = new String(Character.toChars(0x10400));
        check("Deseret", "\\p{sc=Deseret}+", deseret);
        System.out.println("Deseret UTF-16 length: " + deseret.length());
        System.out.println("Deseret code points: "
                + deseret.codePointCount(0, deseret.length()));

        Matcher matcher = Pattern.compile("\\p{sc=Latin}+")
                                 .matcher("Java, 漢字, Café");
        while (matcher.find()) {
            System.out.println("Run: " + matcher.group());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 UnicodeRegexDemo.java
java -Dfile.encoding=UTF-8 UnicodeRegexDemo
~~~

Kết quả (trong terminal hiển thị UTF-8):

~~~text
Latin Café: true
Latin abc123: false
Han 漢字: true
Letters Việt: true
ASCII digit ٣: false
Unicode digit ٣: true
NFD Latin: false
NFC Latin: true
Block includes 7: true
Latin script excludes 7: false
Deseret: true
Deseret UTF-16 length: 2
Deseret code points: 1
Run: Java
Run: Café
~~~

Giải thích:
1. `Café` chứa các chữ Latin dựng sẵn; `abc123` có chữ số nên không khớp `\p{sc=Latin}+`.
2. `漢字` có script Han; `Việt` gồm các Letter nên `\p{L}+` khớp.
3. Chữ số Ả Rập `٣` thuộc `Nd` nhưng không thuộc `[0-9]`.
4. `Cafe\u0301` chứa dấu kết hợp riêng (thường mang script `Inherited`); sau `Normalizer.Form.NFC`, dạng này có thể ghép thành `Café`, khiến phép kiểm tra script Latin ở ví dụ trở thành đúng.
5. `7` thuộc block `Basic_Latin`, nhưng không thuộc script `Latin`.
6. Deseret U+10400 nằm ngoài BMP: Java `String.length()` đếm **hai đơn vị UTF-16**, còn `codePointCount` đếm **một code point**. `Pattern` vẫn so khớp thuộc tính script cho code point này.
7. `find()` trả về hai đoạn Latin `Java` và `Café`, bỏ qua dấu câu, khoảng trắng và phần chữ Hán.

## 6. Unicode mode, case folding và chuẩn hóa

### 6.1. `UNICODE_CHARACTER_CLASS` / `(?U)`

Trong chế độ mặc định, các lớp dựng sẵn như `\w`, `\d`, `\s` và một số lớp POSIX có phạm vi ASCII theo tài liệu `Pattern`. Bật `Pattern.UNICODE_CHARACTER_CLASS` hoặc cờ nội tuyến `(?U)` để dùng định nghĩa Unicode của chúng:

~~~java
Pattern word = Pattern.compile("(?U)\\w+");
boolean ok = word.matcher("Việt").matches(); // true
~~~

Cờ `(?U)` cũng hàm ý `UNICODE_CASE`. Tuy nhiên **`\w` ở chế độ Unicode không tương đương `\p{sc=Latin}`**: nó chấp nhận nhiều Letter, Mark, Digit, nối chữ… tùy định nghĩa; và `\p{sc=Latin}` đã là thuộc tính Unicode ngay cả khi không bật `(?U)`.

Nếu yêu cầu là tập ký tự cụ thể, hãy viết trực tiếp `\p{L}`, `\p{Nd}`, `\p{sc=Latin}` hoặc một phép giao/trừ thay vì trông chờ `\w` có đúng chính sách.

### 6.2. So khớp không phân biệt hoa/thường

~~~java
Pattern p = Pattern.compile(
        "\\p{sc=Latin}+",
        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
~~~

`CASE_INSENSITIVE` cho khớp không phân biệt hoa/thường; thêm `UNICODE_CASE` khi muốn xử lý Unicode-aware case folding. Điều này **không** phải phép kiểm tra ngôn ngữ, phát hiện ký tự gây nhầm lẫn hay chuẩn hóa Unicode. Không cần bật hai cờ trên chỉ để `\p{sc=Latin}` nhận chữ `A` và `a`; cả hai vốn thuộc cùng script.

### 6.3. Chữ có dấu và combining mark

Hai chuỗi nhìn giống nhau có thể có biểu diễn khác:
- **NFC / composed:** `é` thường là một code point `U+00E9`.
- **NFD / decomposed:** `e` (`U+0065`) + `◌́` (`U+0301`), code point sau thuộc category `Mn`.

Vì `\p{sc=Latin}` kiểm tra từng code point, nó không tự động “nuốt” combining mark. Có hai hướng theo yêu cầu:

1. **Đồng nhất biểu diễn trước khi so khớp:** `Normalizer.normalize(input, Normalizer.Form.NFC)`. Đây thường là cách dễ dự đoán khi cần so sánh/kiểm tra văn bản theo một dạng chuẩn.
2. **Chủ động cho phép mark:** `(?:\p{sc=Latin}\p{M}*)+`. Cách này có thể nhận mark không mong muốn từ hệ chữ khác, vì `\p{M}` là category rộng. Cần xác định chính sách, chuẩn hóa và kiểm thử thực tế.

Java có cờ `CANON_EQ` để so khớp tương đương chính tắc, nhưng có chi phí lớn và rủi ro tài nguyên khi có quá nhiều dấu kết hợp; ưu tiên chuẩn hóa dữ liệu rõ ràng nếu bài toán cho phép.

## 7. Áp dụng vào các tình huống thực tế

**Tìm các đoạn thuộc script Latin trong văn bản hỗn hợp:** `Pattern.compile("\\p{sc=Latin}+")` kết hợp `matcher.find()`. Đây là một cách tìm những đoạn **code point** Latin để tô sáng hoặc thống kê; nó chưa phải thuật toán tách từ hay nhận diện ngôn ngữ.

**Kiểm tra một chuỗi chỉ gồm chữ cái thuộc mọi script:** dùng `\p{L}+` cùng `matches()`, nhưng chuỗi dạng decomposed có thể chứa category `M`. Cần nêu rõ có cho phép dấu kết hợp, khoảng trắng, dấu nối hoặc tên nhiều từ hay không; nếu có, thiết kế regex tương ứng.

**Kiểm tra trường số:** `\p{Nd}+` nhận số thập phân Unicode của nhiều hệ chữ; `[0-9]+` chỉ chấp nhận chữ số ASCII, thích hợp hơn với định dạng giao thức quy định `0`–`9`. Với dữ liệu có tác động kinh doanh, còn cần kiểm tra giá trị và quy tắc chuyển đổi số riêng.

**Dữ liệu định danh hoặc an toàn:** cho phép script không đồng nghĩa chống giả mạo Unicode. Ký tự nhìn giống nhau (confusables), ký tự vô hình, hỗn hợp script, chuẩn hóa và chính sách của từng miền dữ liệu cần giải quyết ở tầng xác thực/nghiệp vụ. Không nên dựa **chỉ** vào `\p{sc=...}` để quyết định một định danh an toàn.

## 8. Lỗi thường gặp và cách tránh

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `[A-Za-z]` cho “mọi chữ Latin” | Bỏ chữ có dấu và nhiều chữ Latin ngoài ASCII | Dùng `\p{sc=Latin}` theo đúng policy |
| Dùng `\p{InBasic_Latin}` thay `\p{sc=Latin}` | Block chứa cả số, dấu câu; script Latin ở nhiều block | Phân biệt mục tiêu script hay block |
| Coi `\p{L}` và `\p{IsAlphabetic}` giống hệt | Hai thuộc tính Unicode có tập giá trị khác nhau | Chọn theo định nghĩa cần kiểm tra |
| Coi `\p{Nd}` là `[0-9]` | `Nd` chứa chữ số thập phân nhiều hệ chữ | Dùng ASCII khi hợp đồng dữ liệu yêu cầu |
| Dùng `\p{sc=Latin}+` trên mọi dạng NFD | Combining mark có thể không thuộc script Latin | Chuẩn hóa NFC hoặc hỗ trợ `\p{M}` có kiểm soát |
| Quên escape dấu `\\` trong Java string | `"\p{L}"` không phải string literal Java hợp lệ | Viết `"\\p{L}"` trong Java |
| Nghĩ `(?U)` bắt buộc để dùng `\p{...}` | Property Unicode hoạt động độc lập cờ này | Chỉ bật `(?U)` khi cần lớp dựng sẵn Unicode |
| Dùng `find()` để xác nhận toàn input | `find()` chấp nhận chỉ một phần khớp | Dùng `matches()` cho toàn chuỗi |
| Đếm `String.length()` như số ký tự Unicode | `length()` đếm đơn vị UTF-16 | Dùng `codePointCount` khi cần code point |
| Sao chép cú pháp property từ engine khác | Các engine không hỗ trợ cùng mọi tên/alias | Kiểm tra Java `Pattern` trên đúng JDK |
| Cho rằng property cố định mọi phiên bản | Dữ liệu Unicode và hỗ trợ property tiến hóa | Test với JDK và bộ dữ liệu triển khai |

## 9. Bài tập tự kiểm tra

1. Với `\p{sc=Latin}+` và `matches()`, dự đoán kết quả cho `"Việt"`, `"Việt7"`, `"Cafe\u0301"`. Sau đó thử chuẩn hóa NFC trường hợp cuối.
2. Viết regex nhận **chỉ những chữ cái** có script Latin, theo giao của hai thuộc tính. Gợi ý: `[\p{sc=Latin}&&[\p{L}]]+`.
3. So sánh `\p{InBasic_Latin}+` với `\p{sc=Latin}+` trên `"42"` và `"Café"`. Giải thích vì sao block không thay được script.
4. Nếu định dạng mã giao dịch chỉ cho phép chữ số ASCII, chọn `\p{Nd}+` hay `[0-9]+`? Vì sao?
5. Dùng `Matcher.find()` và `\p{sc=Han}+` trên `"Java 和 漢字"` để tìm các đoạn Han; giải thích tại sao `matches()` trên cả câu sẽ là `false`.

**Đáp án gợi ý:** (1) `true`, `false`, `false`; sau NFC là `true`. (2) Giao script Latin với category `L`. (3) `"42"` thuộc `Basic_Latin` nhưng không có script Latin; `"Café"` thuộc script Latin nhưng không hoàn toàn thuộc block `Basic_Latin`. (4) `[0-9]+` vì đặc tả yêu cầu ASCII. (5) Các đoạn Han gồm `和` và `漢字`; toàn câu còn script Latin, dấu cách và dấu câu.

## 10. Tài liệu tra cứu hiện hành

- [Java SE 26 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): cú pháp script/block/category/binary property, cờ `UNICODE_CHARACTER_CLASS`, các lớp ký tự và giới hạn.
- [Java SE 26 — `Character.UnicodeScript`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.UnicodeScript.html): tên script và phương thức xác định script cho code point.
- [Java SE 26 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): các dạng chuẩn hóa NFC/NFD/NFKC/NFKD.
- [Unicode Standard Annex #24 — Unicode Script Property](https://www.unicode.org/reports/tr24/): ý nghĩa của Script và Script_Extensions.
- [Unicode Standard Annex #29 — Text Segmentation](https://www.unicode.org/reports/tr29/): ký tự hiển thị (grapheme cluster) khác code point như thế nào.

**Ghi nhớ:** chọn **script** để hỏi “thuộc hệ chữ nào”, **block** để hỏi “nằm trong vùng mã nào”, **category** để hỏi “là loại ký tự gì”, và **binary property** để hỏi “có đặc tính Unicode này hay không”. Regex là một lớp kiểm tra; chính sách dữ liệu, chuẩn hóa và thử nghiệm trên JDK thực tế quyết định kết quả đúng.
