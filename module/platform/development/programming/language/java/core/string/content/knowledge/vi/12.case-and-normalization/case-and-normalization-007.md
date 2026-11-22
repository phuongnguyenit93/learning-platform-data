# Phân biệt chuẩn hóa Unicode với loại bỏ dấu trong Java

## 1. Hai thao tác khác nhau, dù thường xuất hiện cạnh nhau

Trong Java, một `String` là dãy đơn vị mã UTF-16. Văn bản trông giống nhau có thể được biểu diễn bởi các dãy code point khác nhau, chẳng hạn chữ **é** có thể là:

- Dạng tiền tổ hợp: `U+00E9` (ký tự `é`, một code point).
- Dạng phân rã: `U+0065 U+0301` (chữ `e` và dấu sắc kết hợp, hai code point).

**Chuẩn hóa Unicode (Unicode normalization)** chuyển văn bản về một trong những dạng biểu diễn được Unicode quy định để xử lý các biểu diễn tương đương một cách thống nhất. Ví dụ, NFC biến `e + U+0301` thành `é` khi có dạng ghép thích hợp; NFD chuyển ngược thành `e + U+0301`. **Dấu sắc vẫn còn** trong cả hai trường hợp.

**Loại bỏ dấu (accent/diacritic stripping)** là chính sách biến đổi mang tính ứng dụng, thường nhằm tạo từ khóa tìm kiếm hoặc biểu diễn gần ASCII: `café` thành `cafe`, `Cà phê` thành `Ca phe`. Bước này **thay đổi thông tin văn bản**, có thể làm những từ khác nghĩa trở nên giống nhau. Unicode normalization theo nghĩa chuẩn **không đồng nghĩa** với loại bỏ dấu.

Ba câu hỏi phải tách biệt:
1. **Có cần thống nhất các biểu diễn Unicode tương đương không?** Dùng `java.text.Normalizer` với NFC/NFD (hoặc NFKC/NFKD nếu chủ ý dùng tương đương compatibility).
2. **Có cần bỏ một số dấu thanh, dấu phụ để tìm kiếm không?** Xác định rõ tập dấu được bỏ, script áp dụng, và cách xử lý ký tự không phân rã.
3. **Có cần so sánh/sắp xếp theo ngôn ngữ người dùng không?** Xem `java.text.Collator` với `Locale` phù hợp; không thay thế bằng xóa dấu tùy tiện.

## 2. Phân biệt chữ, code point, đơn vị UTF-16 và dấu kết hợp

`String.length()` đếm **đơn vị mã UTF-16** (`char`), không đếm số ký tự người dùng nhìn thấy. `String.codePointCount(begin,end)` đếm Unicode code point trong khoảng UTF-16. Một *grapheme cluster* có thể gồm chữ cơ sở cộng nhiều dấu kết hợp hoặc một chuỗi emoji phức tạp.

Ví dụ:

```text
Hiển thị:                  é        é
Biểu diễn:                U+00E9    U+0065 U+0301
Số code point:              1        2
Số char UTF-16:             1        2
Chuẩn hóa NFC:            U+00E9   → U+00E9
Chuẩn hóa NFD:       U+0065 U+0301 ← U+00E9
Bỏ dấu sau NFD:           "e"       "e"
```

`U+0301` là một dấu kết hợp thuộc nhóm *Unicode Mark*. Ngược lại, không phải bất kỳ ký tự “nhìn có dấu” nào cũng được tách thành một chữ Latin cơ sở bằng NFD. Chữ tiếng Việt `đ` (`U+0111`) và `Đ` (`U+0110`) là ví dụ quan trọng: chuẩn hóa NFD **không** đổi chúng thành `d`/`D`.

Ký tự ngoài BMP (như một số emoji) lại chiếm **hai** `char` và không vì thế mà chứa “hai ký tự hiển thị”. Không nên xóa dấu bằng cách duyệt `charAt` rồi đoán từ hình dáng ký tự; cần hiểu rõ dữ liệu Unicode và quy tắc của bài toán.

## 3. NFC/NFD giữ dấu; phép loại dấu cần một bước riêng

`Normalizer.normalize(text, Normalizer.Form.NFC)` đưa chuỗi về dạng ghép khi có thể, còn `NFD` đưa về dạng phân rã. **Cả hai vẫn giữ dấu**. `NFKC/NFKD` còn xét tương đương tương thích nhưng bản thân chúng cũng không phải thao tác xóa dấu. Bài riêng về `Normalizer` trình bày bảng đầy đủ cả bốn dạng.

## 4. Thử nghiệm đối chiếu canonical equivalence

```java
String a = "Caf\u00E9";
String b = "Cafe\u0301";
String nfc = java.text.Normalizer.normalize(b, java.text.Normalizer.Form.NFC);
String nfd = java.text.Normalizer.normalize(a, java.text.Normalizer.Form.NFD);
System.out.println(a.equals(b));         // false
System.out.println(nfc.equals(a));       // true
System.out.println(nfd.equals(b));       // true
System.out.println(nfd.equals("Cafe"));  // false: dấu vẫn còn
```

Đây là snippet đặt trong một phương thức. Chuẩn hóa hai phía theo cùng dạng giúp đối chiếu canonical equivalence, nhưng muốn tìm `"Cafe"` từ `"Café"` theo **chính sách bỏ dấu** thì vẫn cần bước lọc độc lập.

## 5. Loại bỏ dấu: một phép biến đổi riêng sau khi phân rã

Một cách thường dùng để tạo **khóa tìm kiếm Latin bỏ dấu** là:
1. Đưa chuỗi về `Normalizer.Form.NFD` để các chữ **có phân rã chuẩn tắc** tách thành chữ cơ sở và dấu kết hợp.
2. Xóa các code point thuộc nhóm Unicode `Mark` theo quy tắc đã định, ví dụ dùng Java regex `\p{M}+`.
3. Nếu sản phẩm cần, ánh xạ thêm những chữ **không phân rã** như `đ → d`, `Đ → D`.

Ví dụ snippet:

```java
String text = "C\u00E0 ph\u00EA s\u1EEFa \u0111\u00E1";
String decomposed = Normalizer.normalize(
        text, Normalizer.Form.NFD);
String withoutMarks = decomposed.replaceAll("\\p{M}+", "");
String asciiLike = withoutMarks
        .replace('\u0111', 'd')
        .replace('\u0110', 'D');
```

Kết quả của `withoutMarks` là **`Ca phe sua đa`**, vì `đ` vẫn được giữ nguyên. `asciiLike` có nội dung **`Ca phe sua da`** sau quy tắc ánh xạ `đ`. Chúng là **kết quả đã biến đổi**, không còn là văn bản gốc chuẩn tắc tương đương.

Trong Java regex:
- `\p{M}` là nhóm Unicode general category **Mark**: bao gồm *Nonspacing Mark* (`Mn`), *Spacing Combining Mark* (`Mc`) và *Enclosing Mark* (`Me`).
- `+` nghĩa là một hoặc nhiều phần tử `Mark` liên tiếp.
- Trong **string literal Java**, phải gõ `"\\p{M}+"` (hai dấu gạch chéo ngược trong mã Java) để truyền chuỗi regex thực `\p{M}+` cho `replaceAll`.
- `replaceAll` nhận **regex**, không phải chuỗi literal; thay bằng `""` xóa các vùng khớp.

`\p{M}` bao phủ nhiều dấu Unicode hơn riêng khối `\p{InCombiningDiacriticalMarks}` (U+0300..U+036F). Nhưng phạm vi rộng cũng đồng nghĩa với **rủi ro xóa các dấu cần thiết ở những hệ chữ khác**. Không xem nó là phép “xóa dấu tiếng Việt an toàn cho mọi ngôn ngữ”.

### Chương trình chạy được: hai bước tạo khóa tiếng Việt

Lưu thành `VietnameseAccentDemo.java`:

```java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class VietnameseAccentDemo {
    private static final Pattern MARKS =
            Pattern.compile("\\p{M}+");

    static String removeMarks(String input) {
        String nfd = Normalizer.normalize(
                input, Normalizer.Form.NFD);
        return MARKS.matcher(nfd).replaceAll("");
    }

    static String vietnameseSearchKey(String input) {
        return removeMarks(input)
                .replace('\u0111', 'd')
                .replace('\u0110', 'D');
    }

    public static void main(String[] args) {
        String phrase = "C\u00E0 ph\u00EA s\u1EEFa \u0111\u00E1";
        String name = "\u0110\u1EB7ng";

        System.out.println(removeMarks(phrase));
        System.out.println(vietnameseSearchKey(phrase));
        System.out.println(removeMarks(name));
        System.out.println(vietnameseSearchKey(name));

        String bothWays = "Caf\u00E9 / Cafe\u0301";
        System.out.println(removeMarks(bothWays));
    }
}
```

```bash
javac -encoding UTF-8 VietnameseAccentDemo.java
java VietnameseAccentDemo
```

```text
Ca phe sua đa
Ca phe sua da
Đang
Dang
Cafe / Cafe
```

Hàm `removeMarks` thể hiện thao tác **xóa Mark sau NFD**. Hàm `vietnameseSearchKey` bổ sung lựa chọn **đ/Đ** dành cho tình huống tạo khóa Latin/tiếng Việt. Các hàm đều trả một `String` mới về nội dung; đầu vào bất biến không bị sửa.

`removeMarks` không có nghĩa “giữ trọn ý nghĩa tiếng Việt”: `"ma"`, `"má"`, `"mà"`, `"mã"`, `"mạ"` có thể trở thành cùng chuỗi. Vì vậy bản bỏ dấu nên là **giá trị phụ trợ tìm kiếm**, không được mặc định thay thế chuỗi gốc lưu trong cơ sở dữ liệu hoặc trình bày cho người dùng.

## 6. Chuẩn hóa *không* làm biến mất dấu; xóa dấu *không* phải chuẩn hóa chuẩn tắc

Xét ba chuỗi:

```text
A = "é"                 (U+00E9)
B = "e" + U+0301         (U+0065 U+0301)
C = "e"                 (U+0065)
```

Hai chuỗi `A` và `B` là **tương đương chuẩn tắc**. NFC có thể biến chúng thành cùng biểu diễn `é`; NFD có thể biến cả hai thành `e + dấu sắc`. Chuỗi `C` không tương đương chuẩn tắc với `A` hay `B`: nó thiếu thông tin về dấu.

Nếu viết:

```java
String a = "\u00E9";
String b = "e\u0301";
String c = "e";

System.out.println(Normalizer.normalize(
        a, Normalizer.Form.NFC).equals(
        Normalizer.normalize(b, Normalizer.Form.NFC))); // true

System.out.println(Normalizer.normalize(
        a, Normalizer.Form.NFC).equals(c)); // false
```

Đây là snippet cần `import java.text.Normalizer;`, dùng trong phương thức `main`. Chính sự khác biệt giữa `A/B` và `C` giải thích vì sao “normalize Unicode” **không phải** “convert to unaccented text”.

Bước xóa dấu có thể tạo ra **va chạm thông tin**: nhiều chuỗi khác nhau chuyển thành cùng khóa. Nếu từ ngữ hoặc tên có dấu là dữ liệu gốc, xóa dấu trước khi lưu mà không giữ lại bản gốc có thể gây mất thông tin không thể khôi phục.

## 7. Không nhầm compatibility normalization với loại dấu

`NFKC/NFKD` có thể biến `ﬃ` (`U+FB03`) thành `ffi`, `①` thành `1` và `Ａ` thành `A`. Những ví dụ đó **không phải loại dấu**. Ngược lại, một chữ tiếng Việt có dấu thanh khi chuyển NFKD vẫn chứa thông tin dấu trừ khi có quy tắc tương thích đặc biệt khác. Đừng dùng `NFKD` chỉ để hy vọng tạo chuỗi ASCII; chọn `NFD` trước bước lọc `Mark` khi chính sách tìm kiếm Latin/tiếng Việt cho phép.

## 8. Sự khác biệt giữa `Normalizer`, `toLowerCase` và `Collator`

Ba tác vụ này liên quan đến văn bản nhưng có **mục tiêu khác nhau**:

| Tác vụ | API thường dùng | Ý nghĩa |
| --- | --- | --- |
| Thống nhất biểu diễn Unicode tương đương | `Normalizer.normalize(text, NFC)` | Chuẩn hóa dạng biểu diễn; giữ phân biệt có/không có dấu |
| Loại bỏ dấu theo chính sách ứng dụng | NFD rồi lọc `Mark`, ánh xạ tùy chọn `đ/Đ` | Tạo dữ liệu đã mất thông tin dấu |
| Chuyển chữ hoa/thường | `toLowerCase(Locale.ROOT)` hoặc locale xác định | Biến đổi case theo quy tắc Java/locale; **không xóa dấu** |
| So sánh có xét ngôn ngữ | `Collator.getInstance(locale)` | So sánh/sắp xếp theo quy tắc ngôn ngữ, có mức độ phân biệt |
| So bằng code unit sau chuẩn hóa | `normalize(a, NFC).equals(normalize(b, NFC))` | Xác định bằng nhau theo biểu diễn canonical đã chọn |

`String.toLowerCase()` phụ thuộc locale mặc định. Nếu tạo khóa tìm kiếm độc lập với ngôn ngữ hệ thống, có thể dùng `Locale.ROOT` một cách tường minh, nhưng phải xác định yêu cầu nghiệp vụ: với ngôn ngữ như tiếng Thổ Nhĩ Kỳ, cách chuyển hoa/thường và mong đợi của người dùng khác với quy tắc trung lập.

`Collator` hỗ trợ so sánh theo locale; có các mức phân biệt (*strength*) như PRIMARY, SECONDARY và TERTIARY. Ở nhiều locale, PRIMARY có thể coi một số khác biệt dấu và hoa/thường là ngang hàng, nhưng **đừng đồng nhất** nó với thao tác xóa `\p{M}`. Quy tắc thật phụ thuộc locale/phiên bản dữ liệu collation và yêu cầu ngôn ngữ. `Collator.compare(a,b) == 0` chỉ nói hai chuỗi tương đương ở mức cấu hình, không có nghĩa chuỗi gốc đã mất dấu hoặc được đổi nội dung.

Đối với hệ thống có ô tìm kiếm, thường nên giữ văn bản nguyên bản cho hiển thị và xây dựng chỉ mục/khóa tìm kiếm riêng theo đặc tả rõ ràng.

## 9. Vì sao xóa `\p{M}` có thể phá văn bản ngoài nhóm Latin?

Unicode `Mark` không chỉ là các dấu sắc, huyền, hỏi, ngã, nặng của tiếng Việt. Nhiều hệ chữ dùng dấu nguyên âm, dấu phụ hoặc ký hiệu kết hợp mang vai trò **cấu thành chữ viết**.

Ví dụ:
- Trong một số hệ chữ Ấn Độ, vowel signs có thể thuộc `Mark`. Xóa tất cả `\p{M}` có thể làm thay đổi cách đọc và cả ý nghĩa từ.
- Chữ Ả Rập có dấu nguyên âm (*harakat*) thuộc các dạng mark; việc loại bỏ chúng có thể đúng trong một số bài toán tìm kiếm nhưng là lựa chọn có tính ngôn ngữ, không phải chuẩn hóa canonical.
- Variation selector của emoji có thể thuộc loại mark. Xóa nó có thể thay đổi kiểu hiển thị emoji/text của cùng ký hiệu, dù không thay đổi chữ Latin có dấu.
- Có dấu kết hợp nằm ngoài riêng khối `U+0300..U+036F`; dùng biểu thức chỉ bắt một khối có thể bỏ sót dấu ở các vùng khác của Unicode.

Vì vậy, câu lệnh `replaceAll("\\p{M}+", "")` chỉ nên xuất hiện trong **hàm ứng dụng có tên rõ ràng** (ví dụ `latinSearchKey`), sau khi đã xác định bộ ngôn ngữ/kiểu dữ liệu cho phép mất dấu. Nếu ứng dụng xử lý đa ngôn ngữ, cân nhắc bộ phân tích ngôn ngữ riêng, Unicode collation, quy tắc transliteration được chỉ định hoặc chỉ tạo khóa phụ cho một tập dữ liệu đã khoanh vùng.

### `đ/Đ` và các ngoại lệ của chuyển tự

`đ` là chữ cái riêng, không phải chữ `d` có combining mark mà NFD sẽ xóa được. Các ký tự như `ø`, `ł` hoặc `æ` cũng không phải lúc nào phân rã thành các chữ ASCII mong muốn theo NFD. Phép **transliteration** (chuyển tự) để có dạng ASCII là một chính sách khác, có thể cần bảng ánh xạ theo ngôn ngữ.

Không khẳng định rằng “NFD + xóa Mark = ASCII”: kết quả vẫn có thể chứa ký tự Unicode ngoài ASCII. Ngay cả sau khi thêm `đ → d`, dữ liệu đầu vào chưa biết ngôn ngữ vẫn có thể cần những quy tắc khác.

## 10. Lưu trữ và tìm kiếm: giữ dữ liệu gốc, tạo khóa phụ khi cần

Thiết kế đơn giản, an toàn về ý nghĩa:

```text
Dữ liệu nhập
    │
    ├── Giá trị hiển thị: giữ nguyên văn bản người dùng nhập
    │
    ├── Giá trị canonical (tùy chính sách): normalize NFC
    │
    └── Khóa tìm kiếm (tùy nhu cầu):
           NFD → bỏ Mark theo quy tắc → ánh xạ đ/Đ
           → biến đổi hoa/thường theo chính sách riêng nếu cần
```

Dùng khóa phụ giúp tìm `"ca phe"` khớp với `"cà phê"` trong trải nghiệm tìm kiếm có chủ đích, nhưng không thay nội dung lưu/hiển thị bằng bản bỏ dấu. Nếu dùng khóa bỏ dấu làm khóa duy nhất của cơ sở dữ liệu, `"ma"`, `"má"`, `"mạ"`, `"mà"` có thể xung đột ngoài ý muốn.

Ví dụ độc lập, lưu `SearchKeyDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class SearchKeyDemo {
    private static final Pattern MARKS =
            Pattern.compile("\\p{M}+");

    static String searchKey(String value) {
        String canonical = Normalizer.normalize(
                value, Normalizer.Form.NFD);
        String noMarks = MARKS.matcher(canonical).replaceAll("");
        return noMarks.replace('\u0111', 'd')
                .replace('\u0110', 'D')
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String displayed = "C\u00E0 ph\u00EA s\u1EEFa \u0111\u00E1";
        String typed = "ca phe sua da";

        System.out.println(displayed);
        System.out.println(searchKey(displayed));
        System.out.println(searchKey(displayed).equals(searchKey(typed)));
        System.out.println(displayed.equals(typed));
    }
}
```

```bash
javac -encoding UTF-8 SearchKeyDemo.java
java SearchKeyDemo
```

```text
Cà phê sữa đá
ca phe sua da
true
false
```

Hàm `searchKey` chỉ phù hợp với **chính sách minh họa cho dữ liệu Latin/tiếng Việt**. Nó tạo một chuỗi phụ để tra cứu gần đúng, không cung cấp thuật toán bảo mật, chuẩn hóa identifier, chuyển tự tổng quát, hay bảo đảm tương đương ngữ nghĩa giữa mọi ngôn ngữ.

Nếu kết quả dùng để kiểm tra mật khẩu, chữ ký, định danh pháp lý, tên file, quyền truy cập hoặc đối chiếu mã hệ thống, cần tuân theo quy tắc canonicalization đúng **đặc tả miền đó**. Không áp dụng tùy tiện normalization compatibility hoặc xóa dấu rồi cho rằng hai định danh là giống nhau.

## 11. Tính đúng đắn, hiệu năng và tính nhất quán

- **Xác định ranh giới chuẩn hóa**: nếu một hệ thống chuẩn hóa NFC trước khi ghi nhưng truy vấn không được chuẩn hóa cùng cách, so sánh chính xác có thể vẫn bỏ sót kết quả.
- **Giữ bản gốc khi xóa dấu**: phép xóa dấu là nhiều-thành-một; không thể phục hồi dấu tiếng Việt chính xác từ `ca phe sua da`.
- **Không dùng `String.length()` để đo số chữ hiển thị**: normalization có thể thay đổi số code point/UTF-16 code unit nhưng giữ văn bản hiển thị tương đương canonical.
- **Phân biệt thứ tự thao tác**: normalize sang NFD trước khi xóa Mark. Nếu xóa Mark trực tiếp từ `"café"` tiền tổ hợp, regex `\p{M}` không khớp chữ `é` (nó thuộc loại Letter), nên dấu không bị xóa.
- **Không mặc định mọi output chỉ có ASCII**: vì NFD không phân rã hết mọi chữ sang Latin cơ sở.
- **Hạn chế cấp phát khi lặp lại liên tục**: chuẩn hóa, regex và đổi chữ đều tạo công việc xử lý và có thể tạo chuỗi mới; khi cần truy vấn nhiều lần, cân nhắc tính khóa tại lúc nhập hoặc lập chỉ mục, nhưng luôn theo một chính sách nhất quán.
- **Hiệu năng không thay thế chuẩn định nghĩa**: đừng tối ưu bằng cách làm mất dấu, mã hóa hoặc phép so sánh nếu nghiệp vụ cần bảo tồn sự khác nhau giữa các giá trị.

Một tính chất hữu ích: chuẩn hóa đúng dạng Unicode có tính **idempotent** về nội dung khi áp dụng lặp lại: `normalize(normalize(x, NFC), NFC)` bằng `normalize(x, NFC)`. Nhưng “idempotent” chỉ nói lặp bước chuẩn hóa không làm thay đổi thêm; nó **không** có nghĩa đã bỏ dấu.

## 12. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `Normalizer.normalize(s, NFC)` sẽ bỏ dấu | NFC tổ chức lại biểu diễn, **giữ dấu** | Dùng bước loại dấu riêng nếu nghiệp vụ yêu cầu |
| NFD làm thành chữ không dấu | NFD tách dấu thành các code point kết hợp; dấu vẫn tồn tại | Phải quyết định có xóa `Mark` hay không |
| `replaceAll("\\p{M}+", "")` áp dụng trực tiếp trên mọi chuỗi | Chữ tiền tổ hợp có dấu như `é` là Letter, không phải Mark riêng | NFD trước khi xóa Mark |
| NFD + xóa Mark biến mọi ký tự thành ASCII | `đ` và nhiều chữ khác không phân rã thành ký tự ASCII | Ánh xạ bổ sung theo ngôn ngữ, hoặc dùng công cụ chuyển tự |
| Xóa `\p{M}` an toàn với mọi hệ chữ | Mark có thể là thành phần cốt lõi của chữ viết | Giới hạn tập ngôn ngữ và đặc tả mục tiêu |
| NFKD/NFKC “giống NFD/NFC nhưng mạnh hơn” mà không có tác dụng phụ | Compatibility normalization cũng biến đổi ligature/số khoanh tròn/fullwidth | Chỉ dùng khi chủ đích gộp các biến thể đó |
| Chuỗi nhìn giống nhau thì `equals` bằng nhau | `String.equals` không chuẩn hóa Unicode | Chuẩn hóa hai vế về cùng dạng trước khi so |
| Loại dấu tương đương so sánh `Collator` | Collation là quy tắc thứ tự/tương đương theo locale và strength | Chọn `Collator` cho nhu cầu ngôn ngữ |
| Bỏ dấu rồi dùng giá trị làm khóa duy nhất | Nhiều từ khác dấu có thể trùng khóa | Giữ bản gốc và thiết kế chính sách va chạm |
| Dùng `toLowerCase()` không chỉ định locale cho khóa hệ thống | Kết quả có thể phụ thuộc locale mặc định | Chọn `Locale.ROOT` hoặc locale nghiệp vụ tường minh |
| Đếm code point và cho rằng bằng số grapheme | Dấu kết hợp, emoji ZWJ có thể tạo một ký tự hiển thị từ nhiều code point | Dùng thuật toán phân đoạn grapheme khi cần |

## 13. Bài tập và đáp án

**Bài 1.** `"Caf\u00E9"` và `"Cafe\u0301"` có `equals` bằng nhau không? Sau khi đưa cả hai về NFC thì sao?

**Bài 2.** Với `"C\u00E0 ph\u00EA"`, NFD làm dấu mất hẳn hay chỉ tách dấu thành code point riêng? Cần bước nào để tạo `"Ca phe"`?

**Bài 3.** Vì sao NFD rồi xóa `\p{M}` trên `"Đặng"` thu được `"Đang"` chứ chưa phải `"Dang"`?

**Bài 4.** Chọn NFC hay NFKC nếu chỉ cần thống nhất biểu diễn canonical của dữ liệu người dùng và **không muốn** số `①` bị gộp thành `1`?

**Bài 5.** Khi xây dựng tìm kiếm bỏ dấu cho tiếng Việt, vì sao phải lưu lại văn bản gốc và kiểm tra các xung đột khóa?

**Đáp án:**
1. So trực tiếp là `false`; sau NFC cho cả hai là `true`.
2. NFD **tách** dấu; sau đó xóa các `Mark` bằng chính sách được xác định.
3. `Đ` không bị phân rã thành `D + Mark` bởi NFD; muốn `Dang` phải ánh xạ thêm `Đ → D`.
4. Dùng **NFC** vì `NFKC` có thể thực hiện compatibility transformations như `① → 1`.
5. Vì bỏ dấu làm mất thông tin và nhiều từ khác nhau có thể trùng khóa; bản gốc cần cho hiển thị, bảo toàn ngữ nghĩa và phân biệt dữ liệu.

## 14. Kết luận thực hành

**Chuẩn hóa Unicode** là thao tác về **biểu diễn**: NFC/NFD đưa các biểu diễn tương đương chuẩn tắc về cùng dạng trong khi vẫn giữ sự khác nhau giữa chữ có dấu và chữ không dấu. **Loại bỏ dấu** là thao tác về **chính sách nội dung**: có thể dùng NFD để tách dấu rồi bỏ các `Mark` và bổ sung quy tắc tiếng Việt như `đ/Đ`, nhưng nó là phép biến đổi mất thông tin, không phải kết quả mặc định của `Normalizer`.

Nếu cần dữ liệu chính xác, hãy giữ văn bản gốc và chuẩn hóa canonical nhất quán. Nếu cần tìm kiếm bỏ dấu, hãy tạo khóa riêng với phạm vi ngôn ngữ và quy tắc rõ ràng. Nếu cần so sánh theo ngôn ngữ, hãy xem `Collator` thay vì coi việc bỏ dấu là phép so sánh Unicode tổng quát.

## Tài liệu Java SE 17

- [`java.text.Normalizer` — NFC, NFD, NFKC, NFKD](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [`java.util.regex.Pattern` — Unicode categories và `\p{M}`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [`java.lang.String` — `equals`, `replaceAll`, `codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`java.text.Collator` — so sánh theo locale và strength](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [`java.util.Locale` — quy tắc locale khi chuyển chữ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
