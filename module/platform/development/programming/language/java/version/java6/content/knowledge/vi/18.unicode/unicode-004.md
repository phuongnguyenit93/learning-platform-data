# Unicode trong Java: Ký tự dựng sẵn, ký tự tổ hợp và văn bản tiếng Việt

## Mục tiêu học tập

Một đoạn văn bản tiếng Việt có thể **nhìn như nhau** nhưng lại chứa **chuỗi mã Unicode khác nhau**. Ví dụ chữ **ắ** có thể là một ký tự dựng sẵn **U+1EAF**, hoặc một chuỗi gồm **a (U+0061) + dấu breve (U+0306) + dấu sắc (U+0301)**. Hai biểu diễn này tương đương theo chuẩn Unicode, nhưng khi so sánh trực tiếp bằng **String.equals(...)** trong Java, chúng không bằng nhau vì các đơn vị mã lưu trong chuỗi khác nhau.

Bài này giải thích cơ chế và cách xử lý hiện hành của Unicode trong Java 17+, tập trung vào tiếng Việt có dấu và những tình huống thường gặp trong API, cơ sở dữ liệu, tìm kiếm, xử lý văn bản và kiểm thử.

Sau bài học, bạn có thể:

1. Phân biệt **ký tự dựng sẵn (precomposed character)** với **chuỗi ký tự cơ sở + dấu tổ hợp (base character + combining marks)**.
2. Hiểu **code point**, **UTF-16 code unit (char)** và **extended grapheme cluster** khác nhau thế nào; không đánh đồng số lượng ký tự nhìn thấy với **String.length()**.
3. Đọc và biểu diễn các dấu tiếng Việt như **sắc, huyền, hỏi, ngã, nặng**, cùng dấu tạo dạng chữ **ă, â, ê, ô, ơ, ư** theo Unicode.
4. Dùng **java.text.Normalizer**, đặc biệt **NFC** và **NFD**, để so sánh/lưu trữ các chuỗi tương đương về mặt chính tắc.
5. Tránh dùng **NFKC/NFKD** như phép chuyển đổi “vô hại” khi ứng dụng cần bảo toàn phân biệt tương thích; hiểu vì sao bỏ dấu khi tìm kiếm là một chính sách **mất thông tin**, không phải normalization thuần túy.
6. Viết và chạy một chương trình Java 17+ in **code points**, độ dài **UTF-16**, số code points, số **grapheme clusters** và số byte UTF-8 của hai biểu diễn tiếng Việt.
7. Thiết kế quy tắc normalize nhất quán ở biên dữ liệu, không tự ý biến đổi mật khẩu, chữ ký số hoặc các định danh có contract xác định theo byte.

**Phạm vi:** Chỉ sử dụng kiến thức Unicode và Java API còn được áp dụng trong các JDK hiện đại. Ví dụ tự chạy đã được kiểm chứng trên **OpenJDK 24.0.2** bằng tùy chọn **--release 17**.

## 1. Vì sao một chữ tiếng Việt có nhiều cách biểu diễn?

Xét **ắ** — chữ *a có dấu breve và dấu sắc*. Nó có hai biểu diễn Unicode canonically equivalent:

~~~text
Cách 1 — dựng sẵn (precomposed):
    ắ
    U+1EAF                         (một code point)

Cách 2 — tổ hợp (decomposed):
    a       + ◌̆       + ◌́
    U+0061  + U+0306   + U+0301   (ba code points)

Cả hai thường được hiển thị gần như cùng một chữ: ắ.
~~~

Ký hiệu **◌** đứng trước dấu là vòng tròn chấm dùng khi minh họa một **combining mark** đứng độc lập; nó không phải một phần của dữ liệu gốc.

- **Precomposed**: Unicode đã định nghĩa riêng một code point cho tổ hợp chữ + dấu, ví dụ **U+1EAF LATIN SMALL LETTER A WITH BREVE AND ACUTE**.
- **Decomposed**: Unicode biểu diễn cùng nội dung bằng **ký tự cơ sở** và một hoặc nhiều **combining code points**.
- **Canonical equivalence**: hai chuỗi được Unicode xem là những biểu diễn tương đương theo quy tắc chính tắc, dù dãy code points và bytes khác nhau.
- **Rendering**: hệ thống hiển thị cần font, shaping và môi trường phù hợp để đặt dấu tổ hợp đúng vị trí. Khả năng render đúng không có nghĩa bytes bên dưới bằng nhau.

Đây không phải lỗi của Java hoặc lỗi gõ tiếng Việt. Các hệ điều hành, bộ gõ, trình soạn thảo, cơ sở dữ liệu và nguồn nhập khác nhau có thể sử dụng dạng Unicode khác nhau nhưng đều hợp lệ.

### 1.1. Một chữ nhìn thấy không luôn là một code point

Một người dùng có thể nhìn **ắ** như một đơn vị chữ viết. Tuy nhiên:

| Đơn vị đếm | Dạng dựng sẵn **ắ** | Dạng tổ hợp **a + ◌̆ + ◌́** |
| --- | ---: | ---: |
| Số **UTF-16 code units** trong Java String | 1 | 3 |
| Số Unicode **code points** | 1 | 3 |
| Số **extended grapheme clusters** | 1 | 1 |
| Số byte khi mã hóa **UTF-8** | 3 | 5 |

Những con số này đã được kiểm chứng trong ví dụ Java ở phần sau. Sự khác biệt chỉ nằm ở cách biểu diễn; cả hai có thể tạo cùng một chữ khi render.

**Không nên dùng String.length() để trả lời câu hỏi “người dùng nhìn thấy bao nhiêu ký tự”**. length() trả số code units UTF-16, không đếm grapheme clusters.

### 1.2. Ví dụ một dấu đơn giản hơn

Chữ **á** có thể là:

~~~text
Dựng sẵn:  á        U+00E1
Tổ hợp:    a + ◌́    U+0061 U+0301
~~~

Với **ắ**, chuỗi NFD có nhiều dấu hơn do cả **breve** và **sắc** đều có thể là combining code points. Đây là lý do tiếng Việt thể hiện rất rõ các khác biệt giữa Unicode normalization, độ dài code point và độ dài hiển thị.

## 2. Ba tầng phải phân biệt: code unit, code point, grapheme cluster

### 2.1. Java String dùng UTF-16

Trong Java, **String.length()** cho biết số **UTF-16 code units**. Kiểu nguyên thủy **char** biểu diễn một code unit 16 bit, không phải luôn một ký tự Unicode đầy đủ.

- Một code point thuộc **Basic Multilingual Plane (BMP)** thông thường nằm trong một UTF-16 code unit.
- Code point nằm ngoài BMP cần **hai UTF-16 code units**, còn gọi là **surrogate pair**.
- Dấu tổ hợp là các code points riêng, nên tổng số code units có thể tăng dù màn hình chỉ hiển thị một cụm ký tự.

Ví dụ minh họa:

~~~java
// Mảnh mã chạy được trong phương thức main; không phải file độc lập.
String composed = "\u1EAF";         // ắ
String decomposed = "a\u0306\u0301"; // a + breve + acute

System.out.println(composed.length());   // 1
System.out.println(decomposed.length()); // 3
~~~

**\uXXXX** trong Java source là cú pháp Unicode escape thuộc chương trình, không có nghĩa mọi text nhận từ mạng/database đều mang dạng escape đó. Trong file thật, bạn cũng có thể viết literal Unicode nếu source và compiler được cấu hình UTF-8 thích hợp.

### 2.2. Code point là gì?

**Unicode code point** là một giá trị số được Unicode dùng để định danh một ký tự hoặc ký hiệu theo chuẩn. Java có các API:

- **String.codePoints()**: stream các code points trong chuỗi.
- **String.codePointCount(beginIndex, endIndex)**: đếm code points trong một khoảng index theo UTF-16 code units.
- **String.codePointAt(index)**: đọc code point bắt đầu ở một UTF-16 index.
- **Character.charCount(codePoint)**: số UTF-16 units cần thiết cho code point đó.
- **String.offsetByCodePoints(...)**: dịch vị trí theo code points thay vì di chuyển tùy tiện theo char indices.

Với các dấu tổ hợp, **mỗi combining mark vẫn là một code point**. Vì vậy đếm code points không tương đương đếm các chữ người dùng nhận ra.

**Không cắt một String ở index tùy ý nếu index có thể nằm giữa surrogate pair hoặc giữa các thành phần trong grapheme cluster.** Nếu đang triển khai trình soạn thảo, thao tác chọn/xóa ký tự phải xét ranh giới phù hợp.

### 2.3. Extended grapheme cluster là gì?

**Extended grapheme cluster** là một đơn vị phân đoạn văn bản theo quy tắc Unicode, thường gần với một “ký tự người dùng cảm nhận”. Một cluster có thể gồm chữ cơ sở kèm nhiều combining marks; ở emoji và các hệ chữ khác nó còn có các quy tắc ghép phức tạp.

Java regex hỗ trợ:

~~~java
// Mảnh minh họa; không phải một file độc lập.
Pattern grapheme = Pattern.compile("\\X");
Matcher matcher = grapheme.matcher(text);
int count = 0;
while (matcher.find()) {
    count++;
}
~~~

Trong **java.util.regex.Pattern**, **\\X** ở Java string tạo thành pattern regex **\X**, có nghĩa **một Unicode extended grapheme cluster**. Với cả hai biểu diễn **ắ**, đoạn đếm sẽ cho kết quả **1**.

**Grapheme cluster không đồng nghĩa một “chữ cái tiếng Việt” theo mọi quy tắc ngôn ngữ hoặc một cột trong UI.** Chiều rộng hiển thị còn phụ thuộc font, terminal, emoji và shaping. Dùng thuật toán phân đoạn phù hợp khi xử lý cursor/backspace; đừng tự cắt String bằng length().

## 3. Các dấu tiếng Việt trong Unicode

Tiếng Việt có những chữ cái với dấu tạo dạng chữ và dấu thanh. Khi phân rã chính tắc bằng **NFD**, nhiều dấu có biểu diễn là combining marks riêng.

### 3.1. Năm dấu thanh thường gặp

| Dấu thanh | Tên Unicode của combining mark | Code point |
| --- | --- | --- |
| Huyền | COMBINING GRAVE ACCENT | **U+0300** |
| Sắc | COMBINING ACUTE ACCENT | **U+0301** |
| Ngã | COMBINING TILDE | **U+0303** |
| Hỏi | COMBINING HOOK ABOVE | **U+0309** |
| Nặng | COMBINING DOT BELOW | **U+0323** |

Dấu ngang (không đánh dấu thanh riêng) không cần combining code point bổ sung. Khi dùng tiếng Việt, đừng chọn ký tự có tên gần giống rồi mặc định nó là dấu thanh đúng. Unicode khuyến nghị các combining marks nói trên cho tiếng Việt.

### 3.2. Các dấu tạo dạng nguyên âm

Một số dạng chữ tiếng Việt có thể phân rã thành base letter và combining marks:

| Dạng chữ | Dạng NFD điển hình | Ký hiệu |
| --- | --- | --- |
| **ă** | a + COMBINING BREVE | **U+0061 + U+0306** |
| **â** | a + COMBINING CIRCUMFLEX ACCENT | **U+0061 + U+0302** |
| **ê** | e + COMBINING CIRCUMFLEX ACCENT | **U+0065 + U+0302** |
| **ô** | o + COMBINING CIRCUMFLEX ACCENT | **U+006F + U+0302** |
| **ơ** | o + COMBINING HORN | **U+006F + U+031B** |
| **ư** | u + COMBINING HORN | **U+0075 + U+031B** |

Đối với một số ký tự có cả dấu dạng chữ và dấu thanh, bản NFD sẽ có **hai combining marks hoặc nhiều thành phần**. Ví dụ **ắ** là **a + ◌̆ + ◌́**.

### 3.3. Trường hợp đặc biệt: đ không phải d + dấu tổ hợp

Chữ **đ** là một chữ cái riêng trong Unicode (**U+0111**, chữ hoa **Đ** là **U+0110**). **NFD không tự biến đ thành d**. Nếu ứng dụng muốn tạo khóa tìm kiếm không dấu và coi đ tương đương d, đó là một **quy tắc xử lý riêng** của sản phẩm, không phải kết quả chuẩn của Unicode normalization.

Ví dụ:

~~~text
"Đặng" --NFD--> giữ chữ Đ; ặ phân rã thành các thành phần
      --loại marks--> "Đang" (theo từng dữ liệu thực tế)
      --map Đ→D--> "Dang"
      --lowercase--> "dang"
~~~

Quy tắc map này có ích cho một số kiểu tìm kiếm không dấu, nhưng **mất thông tin**. Các từ có dấu khác nhau có thể trở thành cùng một khóa.

### 3.4. Đặt đúng dấu thanh là vấn đề ngôn ngữ, không chỉ Unicode

Normalizer biết quy tắc Unicode composition/decomposition và thứ tự chính tắc của combining marks. Nó **không tự sửa lỗi chính tả hoặc quy tắc đặt dấu thanh trong một âm tiết tiếng Việt**.

Nếu người dùng đặt dấu lên sai chữ, bỏ dấu, chọn nhầm dấu hoặc có lỗi typing, NFC không biến nội dung sai thành từ đúng. Không sử dụng **Normalizer.normalize(...)** như công cụ kiểm tra chính tả tiếng Việt.

## 4. Unicode normalization: NFC, NFD, NFKC, NFKD

Java cung cấp **java.text.Normalizer** và enum **Normalizer.Form**. Bốn forms vẫn là cách phân loại hiện hành của Unicode:

| Form | Tác dụng | Thường dùng khi |
| --- | --- | --- |
| **NFD** | Canonical decomposition; phân rã chính tắc | Phân tích combining marks, thao tác nội bộ có kiểm soát |
| **NFC** | Canonical decomposition rồi canonical composition | Chuẩn hóa text thông thường, so sánh và lưu trữ thống nhất |
| **NFKD** | Compatibility decomposition | Các pipeline cần biến đổi tương thích có chủ đích |
| **NFKC** | Compatibility decomposition rồi composition | Những quy tắc đặc biệt cho identifier/normalization mà hệ thống đã định nghĩa |

**NFC và NFD bảo toàn canonical equivalence**. **NFKC và NFKD** có thể gộp các ký tự vốn có sự phân biệt **compatibility** như dạng trình bày hoặc ký hiệu, vì vậy không thay thế NFC một cách mặc định cho nội dung tiếng Việt cần giữ nguyên nghĩa.

### 4.1. NFC: chọn dạng dùng chung cho text

~~~java
// Mảnh minh họa, không phải chương trình độc lập.
String canonical = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

NFC chuyển các chuỗi canonically equivalent thành dạng chuẩn tương ứng. Với ví dụ **ắ**, cả biểu diễn dựng sẵn và tổ hợp được đưa về **U+1EAF**.

NFC là lựa chọn thực tế phổ biến cho nhiều hệ thống lưu trữ text và so sánh, nhưng phải là **quy ước được áp dụng đồng nhất** trên các điểm nhập dữ liệu, ghi database, cập nhật index và truy vấn.

**Không bảo đảm mọi grapheme đều trở thành một code point sau NFC.** Có những chuỗi hợp lệ không có ký tự dựng sẵn cho toàn bộ tổ hợp; NFC chỉ compose khi Unicode định nghĩa được theo quy tắc.

### 4.2. NFD: hữu ích khi cần nhìn từng thành phần

~~~java
String decomposed = Normalizer.normalize(input, Normalizer.Form.NFD);
~~~

NFD phân rã những ký tự có canonical decomposition mapping và sắp xếp combining marks theo quy tắc normalization. Với **ắ**, output có các code points **U+0061 U+0306 U+0301**.

NFD không có nghĩa là “bỏ dấu”. Dấu vẫn tồn tại, chỉ ở dạng **code points riêng**. Nếu xóa combining marks sau NFD, bạn đang làm **diacritic stripping** — một phép biến đổi làm mất thông tin ngôn ngữ.

### 4.3. NFKC/NFKD: khác ở compatibility

Chẳng hạn những ký hiệu có compatibility decomposition có thể đổi sang dạng chữ/số thông thường dưới NFKC/NFKD. Tùy domain, điều đó có thể tiện cho nhận dạng identifier hoặc tìm kiếm, nhưng nó cũng có thể xóa đi những khác biệt mà ứng dụng cần giữ lại.

Đối với văn bản tiếng Việt bình thường, dùng **NFC** khi muốn một canonical storage form nhất quán. Chỉ dùng compatibility normalization khi bạn **có chính sách rõ** về các biến đổi làm mất phân biệt.

### 4.4. Kiểm tra trạng thái đã normalize

~~~java
// Mảnh minh họa: đã chuẩn hóa NFC hay chưa?
boolean normalized = Normalizer.isNormalized(
        text, Normalizer.Form.NFC);
~~~

**isNormalized(...)** kiểm tra text có đang ở form đó hay không; nó không thay đổi text. Nếu input không phải NFC, gọi **normalize(...)** để tạo String kết quả. Tránh gọi normalize liên tục không cần thiết trên một dữ liệu đã có contract lưu trữ rõ.

## 5. So sánh hai chuỗi tiếng Việt đúng mức ngữ nghĩa

### 5.1. String.equals so sánh code units

Java **String.equals(...)** so sánh nội dung char sequence ở cấp UTF-16 code units. Nó **không tự coi hai chuỗi canonically equivalent là bằng nhau**.

~~~java
String precomposed = "\u1EAF";
String combining = "a\u0306\u0301";

System.out.println(precomposed.equals(combining)); // false
~~~

Hai chuỗi trên thường được hiển thị như nhau nhưng dãy code units khác nhau. **String.compareTo(...)**, nhiều map/set keys và phép kiểm tra unique dựa vào String equality cũng bị ảnh hưởng nếu input không cùng form.

### 5.2. So sánh sau NFC

~~~java
String left = Normalizer.normalize(precomposed, Normalizer.Form.NFC);
String right = Normalizer.normalize(combining, Normalizer.Form.NFC);

System.out.println(left.equals(right)); // true
~~~

Đây là **so sánh canonical equivalence**. Nếu mục tiêu của bạn là xem hai chuỗi có cùng nội dung Unicode chuẩn hay không, normalize cả hai về **cùng một form** trước khi so sánh.

Trong một ứng dụng lớn, thông thường nên chọn form ở **biên dữ liệu** và lưu đúng form đó, thay vì mỗi tầng tự normalize khác nhau. Ví dụ: validate input → NFC → persist → index/query đều dùng NFC. Cần thống nhất cả với dữ liệu đã tồn tại, bởi đổi quy tắc giữa chừng có thể làm xuất hiện các xung đột unique keys trước đó chưa thấy.

### 5.3. Canonical equality khác so sánh không phân biệt chữ hoa/dấu

Ba yêu cầu khác nhau:

1. **Bằng nhau theo code units**: String.equals; phân biệt mọi khác biệt bit-level trong UTF-16.
2. **Bằng nhau theo Unicode canonical equivalence**: normalize hai bên cùng NFC/NFD rồi dùng equals.
3. **Tìm kiếm không phân biệt dấu và/hoặc chữ hoa**: cần một **search policy** riêng, có thể dùng NFD + loại combining marks + map đ/Đ + xử lý hoa/thường.

Các từ **ma**, **má**, **mà**, **mã**, **mạ**, **mả** có thể phân biệt về nghĩa. Gộp chúng thành **ma** là một quyết định **tìm kiếm gần đúng**, không phải canonical equality.

**Không dùng “bỏ dấu” làm điều kiện để so sánh định danh bảo mật hoặc dữ liệu cần giữ nguyên khác biệt.** Nó có thể khiến các input khác nhau trở thành cùng một key.

## 6. Ví dụ chạy được trên Java 17+: in code points và các loại độ dài

Tạo đúng một file **VietnameseUnicodeDemo.java**. Chương trình:

- Tạo **ắ** theo hai cách: dựng sẵn U+1EAF và tổ hợp **a + U+0306 + U+0301**.
- In dãy code points bằng **String.codePoints()**.
- So sánh raw equality, NFC equality và NFD equality.
- Đếm UTF-16 units, code points, grapheme clusters bằng regex **\\X**.
- So sánh byte lengths dưới UTF-8.
- Thử với cả cụm **Tiếng Việt**.
- Minh họa cách xây **searchKey** có chủ đích mất dấu/đ → d, không nhầm với NFC.

### 6.1. Code đầy đủ

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public final class VietnameseUnicodeDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static int graphemeCount(String text) {
        Matcher matcher = GRAPHEME.matcher(text);
        int count = 0;
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    private static String searchKey(String text) {
        String decomposed = Normalizer.normalize(text, Normalizer.Form.NFD);
        String withoutMarks = decomposed.replaceAll("\\p{M}+", "");
        return withoutMarks.replace('đ', 'd')
                .replace('Đ', 'D')
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String composed = "\u1EAF";
        String decomposed = "a\u0306\u0301";

        System.out.println("composed=" + codePoints(composed));
        System.out.println("decomposed=" + codePoints(decomposed));
        System.out.println("rawEqual=" + composed.equals(decomposed));
        System.out.println("nfcEqual="
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)));
        System.out.println("nfdEqual="
                + Normalizer.normalize(composed, Normalizer.Form.NFD)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFD)));
        System.out.println("utf16Units=" + composed.length() + "/"
                + decomposed.length());
        System.out.println("codePoints=" + composed.codePointCount(0, composed.length())
                + "/" + decomposed.codePointCount(0, decomposed.length()));
        System.out.println("graphemes=" + graphemeCount(composed)
                + "/" + graphemeCount(decomposed));
        System.out.println("utf8Bytes="
                + composed.getBytes(StandardCharsets.UTF_8).length + "/"
                + decomposed.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("nfdOfComposed="
                + codePoints(Normalizer.normalize(composed, Normalizer.Form.NFD)));
        String phrase = "Tiếng Việt";
        String alternate = Normalizer.normalize(phrase, Normalizer.Form.NFD);
        System.out.println("phraseRawEqual=" + phrase.equals(alternate));
        System.out.println("phraseNfcEqual="
                + Normalizer.normalize(phrase, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(alternate, Normalizer.Form.NFC)));
        System.out.println("searchKey=" + searchKey("Đặng"));
        System.out.println("nfcCheck=" + Normalizer.isNormalized(composed,
                Normalizer.Form.NFC));
    }
}
~~~

**Đây là một chương trình Java độc lập, không cần dependency ngoài JDK.** Dùng **Unicode escapes** cho ký tự dựng sẵn và combining marks giúp test không phụ thuộc vào cách trình soạn thảo lưu chữ **ắ** khi chép file.

### 6.2. Biên dịch và chạy

Ở thư mục chứa file **VietnameseUnicodeDemo.java**, yêu cầu **JDK 17 hoặc cao hơn**:

~~~bash
javac -encoding UTF-8 --release 17 VietnameseUnicodeDemo.java
java VietnameseUnicodeDemo
~~~

Trên PowerShell, hai lệnh cũng có dạng tương tự:

~~~powershell
javac -encoding UTF-8 --release 17 VietnameseUnicodeDemo.java
java VietnameseUnicodeDemo
~~~

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2:**

~~~text
composed=U+1EAF
decomposed=U+0061 U+0306 U+0301
rawEqual=false
nfcEqual=true
nfdEqual=true
utf16Units=1/3
codePoints=1/3
graphemes=1/1
utf8Bytes=3/5
nfdOfComposed=U+0061 U+0306 U+0301
phraseRawEqual=false
phraseNfcEqual=true
searchKey=dang
nfcCheck=true
~~~

### 6.3. Phân tích output

- **composed=U+1EAF**: dạng dựng sẵn của **ắ** chỉ có một code point.
- **decomposed=U+0061 U+0306 U+0301**: cùng chữ có dạng một base code point và hai combining marks.
- **rawEqual=false**: Java String.equals không tự áp dụng canonical equivalence.
- **nfcEqual=true** và **nfdEqual=true**: cả hai chuỗi về cùng một Unicode normalization form có nội dung bằng nhau.
- **utf16Units=1/3**: String.length trả số UTF-16 code units. Với các ký tự trong ví dụ, mỗi code point đều ở BMP nên code units cũng bằng số code points.
- **codePoints=1/3**: code point count vẫn khác nhau giữa composed và decomposed.
- **graphemes=1/1**: regex **\X** xem cả hai biểu diễn là một extended grapheme cluster.
- **utf8Bytes=3/5**: việc serialize UTF-8 có số byte khác nhau nếu chưa normalize; charset không tự áp dụng NFC.
- **nfdOfComposed=...**: cho thấy bộ phân rã chính tắc của Normalizer.
- **phraseRawEqual=false / phraseNfcEqual=true**: vấn đề không giới hạn trong một chữ cái, mà có thể xuất hiện ở văn bản **Tiếng Việt** thực tế.
- **searchKey=dang**: ví dụ tùy chọn bỏ dấu và map **Đ** thành **D**, sau đó lowercase. Đây là phép biến đổi mất thông tin, không phải canonical normalization.
- **nfcCheck=true**: biểu diễn dựng sẵn trong ví dụ đã ở form NFC.

Nếu sửa input hoặc thay version Unicode mà JDK hỗ trợ, kết quả ở các trường hợp khác có thể cần kiểm thử lại. Đặc biệt, không lấy **13 dòng output** này để suy ra mọi chuỗi hoặc mọi hệ chữ có cùng số code points/grapheme.

## 7. Vì sao UTF-8 không tự sửa sự khác nhau của Unicode?

**UTF-8** là **encoding** chuyển Unicode code points thành byte sequence. **Unicode normalization** là quy tắc chọn một biểu diễn chuẩn của các chuỗi canonically/compatibility equivalent. Hai việc này khác nhau.

~~~text
"ắ" ở NFC: U+1EAF
      │ UTF-8 encoding
      ▼
     3 bytes

"a" + U+0306 + U+0301
      │ UTF-8 encoding
      ▼
     5 bytes

Nội dung hiển thị gần giống; bytes khác nhau.
~~~

**new String(bytes, StandardCharsets.UTF_8)** giải mã bytes; nó **không có contract sẽ tự normalize NFC**. Tương tự, **getBytes(StandardCharsets.UTF_8)** mã hóa code points hiện có chứ không tự gộp combining marks.

Nếu ứng dụng nhận nội dung qua HTTP, file, message queue hoặc database, cần:

1. **Giải mã đúng encoding** để có Java String hợp lệ.
2. **Normalize có chủ đích** theo quy tắc được thống nhất (ví dụ NFC cho nội dung tiếng Việt).
3. **Validate** theo yêu cầu sản phẩm; đừng để normalization thay thế quy tắc kiểm tra đầu vào.
4. **Lưu trữ và index** cùng một dạng nếu đó là contract.
5. **Normalize truy vấn** bằng quy tắc tương tự khi cần exact matching.
6. **Mã hóa trở lại UTF-8** khi trao đổi qua network/file, với charset được xác định rõ ràng.

Nếu dữ liệu đã bị giải mã sai charset và xuất hiện ký tự lỗi, Normalizer không thể biết byte gốc và tự phục hồi tiếng Việt chuẩn.

## 8. So sánh, tìm kiếm và sắp xếp là ba bài toán riêng

### 8.1. Exact matching

Khi định danh là văn bản người dùng và hợp đồng chấp nhận canonical equivalence, có thể thực hiện:

~~~java
// Mảnh minh họa.
static String canonicalText(String raw) {
    return Normalizer.normalize(raw, Normalizer.Form.NFC);
}

// Sau khi chuẩn hóa hai vế:
boolean equal = canonicalText(left).equals(canonicalText(right));
~~~

Quan trọng: đây không phải lời khuyên normalize mọi ID/bí mật của hệ thống. Với **opaque token**, **hash**, **digital signature input**, **password** và dữ liệu có hợp đồng byte-level, phải giữ nguyên quy tắc do giao thức/chính sách xác thực định nghĩa. Tự thêm normalization ở một phía có thể làm sai chữ ký, thay đổi khóa so khớp hoặc tạo lỗ hổng hợp nhất dữ liệu.

### 8.2. Tìm kiếm tiếng Việt không dấu

Một số sản phẩm muốn **Đặng** và **dang** cùng trả kết quả tìm kiếm. Khi đó một search key riêng có thể dùng:

~~~java
// Mảnh minh họa trích từ ví dụ chạy được.
private static String searchKey(String text) {
    String nfd = Normalizer.normalize(text, Normalizer.Form.NFD);
    String noMarks = nfd.replaceAll("\\p{M}+", "");
    return noMarks.replace('đ', 'd')
            .replace('Đ', 'D')
            .toLowerCase(Locale.ROOT);
}
~~~

**\\p{M}** trong Java string là regex Unicode category **Mark** (bao gồm nonspacing marks và các nhóm marks khác). Loại bỏ marks sau NFD không chỉ loại bỏ năm dấu thanh tiếng Việt mà còn có thể loại bỏ dấu tạo dạng chữ và dấu của nhiều ngôn ngữ khác.

Cách làm này hữu ích trong **chỉ mục tìm kiếm gần đúng**, nhưng có các giới hạn:

- **ma**, **má**, **mà**, **mả**, **mã**, **mạ** đều có thể thành **ma**.
- **đ** không tự biến thành d qua NFD; ví dụ map riêng để phù hợp mục tiêu tìm kiếm.
- Cách xử lý **Locale.ROOT** là case mapping chung, không phải thuật toán tìm kiếm tiếng Việt hoàn chỉnh với mọi quy tắc ngôn ngữ.
- NFKC/NFKD hoặc diacritic stripping có thể tác động lên văn bản nhiều ngôn ngữ ngoài dự kiến.
- Search key nên được lưu trong **cột/index phụ**, không ghi đè bản tiếng Việt nguyên gốc mà người dùng muốn hiển thị.
- Với tìm kiếm phức tạp, cân nhắc tokenizer, analyzer hoặc thư viện Unicode/collation phù hợp và kiểm thử với dữ liệu thực tế.

### 8.3. Sắp xếp theo quy tắc tiếng Việt

**Sắp xếp** không giống **equals**. Java **String.compareTo** so sánh chuỗi theo đơn vị mã; nó không phải bộ sắp xếp từ điển tiếng Việt.

Java cung cấp **java.text.Collator**:

~~~java
// Mảnh code minh họa: cần import java.text.Collator, java.util.Locale.
Collator collator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
words.sort(collator::compare);
~~~

**Collator** là cơ chế so sánh theo locale/collation, nhưng thứ tự cụ thể, lựa chọn strength và dữ liệu bản địa hóa phụ thuộc JDK/provider. Hãy kiểm thử với bộ từ tiếng Việt đại diện cho sản phẩm (đ/ d, dấu thanh, chữ hoa, các nguyên âm có dấu). **Collator không thay thế Normalizer như một quy ước lưu trữ**.

Không dựa vào một thứ tự output cố định giữa mọi JDK/vendor khi bài toán yêu cầu tính lặp lại tuyệt đối; nếu cần, hãy chọn policy và phiên bản collation rõ ràng.

## 9. Ứng dụng trong cơ sở dữ liệu và API

### 9.1. Hiện tượng duplicate key nhìn giống nhau

Giả sử database lưu hai bản ghi tên hiển thị là **"ắ"**. Một bản được lấy từ bộ gõ tạo NFC, bản kia từ tài liệu có NFD. Nếu cột uniqueness hoặc cơ chế compare dựa trên bytes/code units và không được cấu hình canonical equivalence, hai bản ghi có thể qua được kiểm tra trùng hoặc bị xử lý bất nhất giữa Java và database.

Một chiến lược rõ ràng:

~~~text
HTTP/file input
      │
      ▼
UTF-8 decode
      │
      ▼
validate text policy
      │
      ▼
Normalizer.normalize(..., NFC)
      │
      ├── persist canonical value
      ├── derive canonical unique key
      └── index/query canonical value
~~~

**Không khẳng định mọi database luôn so sánh khác nhau**: collation, encoding và normalization behavior của database phụ thuộc sản phẩm/cấu hình. Hệ thống cần thống nhất hành vi **Java layer + persistence layer + search index**, và kiểm thử các trường hợp composed/decomposed thực tế.

### 9.2. Migration dữ liệu đã có

Nếu quyết định lưu mới bằng NFC nhưng dữ liệu cũ chứa cả NFC/NFD:

1. Xác định contract hiện tại và mức độ ảnh hưởng tới business keys.
2. Chạy thống kê trong phạm vi được phép để tìm những khóa canonical-equivalent sau khi normalize.
3. Quy định **cách giải quyết collision**; không mặc định gộp hai bản ghi chỉ vì canonical text bằng nhau.
4. Migration có khả năng rollback và backup; bảo vệ các quan hệ khóa ngoại hoặc unique constraints liên quan.
5. Cập nhật cả đường ghi mới, tìm kiếm, validation và API clients.
6. Thử nghiệm với tên tiếng Việt, dữ liệu đa ngôn ngữ và text ngoài BMP.

Không normalize trực tiếp toàn bộ database production mà chưa phân tích tác động: normalization có thể làm đổi byte representation và tạo collision ở những trường có unique index.

### 9.3. Biên giới API cần có policy

Một API nhận field **displayName** có thể có contract NFC phù hợp. Nhưng một field **opaqueId** hoặc **signaturePayload** thường có contract khác. Không nên viết interceptor “normalize mọi String field” không phân biệt loại dữ liệu.

Nên ghi rõ trong API contract: field nào được normalize, tại lúc nào, so sánh bằng cơ chế gì, và ứng dụng có giữ nguyên text người dùng khi hiển thị hay không.

## 10. Cắt, đếm và sửa chuỗi mà không phá dấu

### 10.1. Không cắt dựa trên String.length khi hiển thị

Ví dụ **ắ** ở dạng NFD có length 3. Nếu cắt bằng **substring(0, 1)**, bạn sẽ chỉ giữ lại **a**, làm mất dấu. Nếu cắt ở giữa dấu, có thể sinh một combining mark đứng đầu chuỗi, gây hiển thị bất thường khi ghép với đoạn tiếp.

Với ký tự ngoài BMP, cắt ở một chỉ số UTF-16 cũng có thể chia đôi surrogate pair. Cần chọn thuật toán theo đúng đơn vị:

| Mục tiêu | Đơn vị phù hợp |
| --- | --- |
| Giới hạn số UTF-16 code units theo một giao thức cụ thể | **String.length()** |
| Duyệt Unicode scalar/code point | **codePoints()**, **offsetByCodePoints(...)** |
| Di chuyển cursor/xóa một cụm ký tự người dùng nhìn thấy | **Extended grapheme clusters** |
| Giới hạn byte size của dữ liệu UTF-8 | **getBytes(UTF_8).length** hoặc streaming encoder thích hợp |
| Giới hạn chiều rộng hiển thị terminal/UI | Cơ chế layout/font/width theo môi trường, không chỉ length hoặc grapheme count |

Một số giao diện yêu cầu tính “độ dài tên” theo grapheme clusters. Nếu bạn chỉ đếm code points, các chuỗi có nhiều combining marks có thể bị đối xử không công bằng.

### 10.2. Quy tắc grapheme cũng không giải quyết hết mọi vấn đề UI

**Pattern.compile("\\X")** cho phép phân đoạn extended grapheme cluster. Tuy nhiên:

- Một cluster có thể là chữ với nhiều dấu, emoji sequence hoặc thành phần viết phức tạp.
- Chiều rộng pixel phụ thuộc font/rendering, không thể suy từ số cluster.
- Việc chọn từ, xác định dấu câu, tìm vị trí cursor theo từ hoặc câu cần thêm các quy tắc segment khác.
- Phiên bản Unicode/JDK ảnh hưởng những quy tắc được thư viện triển khai theo thời gian; kiểm thử với loại văn bản bạn hỗ trợ.

Không dùng việc chuẩn hóa NFC như một cách “giảm length để vừa UI”. Một NFD hợp lệ có thể có số code units cao hơn mà vẫn biểu diễn cùng grapheme.

## 11. Regex và các ký tự tổ hợp

### 11.1. Vì sao biểu thức kiểm tra chữ cái có thể sai?

Một regex dựa trên **[A-Za-z]** chỉ nhận ASCII letters. Nó không nhận đầy đủ chữ cái tiếng Việt dựng sẵn hoặc những dấu kết hợp. Một regex dùng **\p{L}** nhận letter code points nhưng **combining mark** thuộc Unicode category **Mark**, không phải Letter.

Ví dụ:

~~~java
// Mảnh minh họa; không phải validation hoàn chỉnh cho tên tiếng Việt.
String regex = "[\\p{L}\\p{M}]+";
boolean matching = Pattern.matches(regex, text);
~~~

Điều này cho phép các code points thuộc category L hoặc M, nhưng **không** bảo đảm một tên người hợp lệ: chuỗi chỉ có dấu tổ hợp cũng có thể match, và tên thực tế có khoảng trắng, dấu nháy hoặc gạch nối tùy chính sách. Validation sản phẩm phải được định nghĩa rõ và có test với text NFC/NFD.

### 11.2. Pattern.CANON_EQ và chiến lược normalize trước

Java regex có flag **Pattern.CANON_EQ** để xem xét canonical equivalence khi matching. Tuy nhiên, nếu hệ thống cần canonical text ổn định trên toàn pipeline, việc **normalize dữ liệu về cùng form trước rồi match bằng regex bình thường** thường dễ kiểm soát và thống nhất với storage/index hơn.

Không dùng CANON_EQ như cách thay thế thiết kế input contract. Cần hiểu giới hạn, chi phí và các trường hợp regex phù hợp; tránh áp dụng mặc định lên text không tin cậy hoặc pattern quá phức tạp.

## 12. Normalization và bảo mật: không tự ý biến đổi mọi dữ liệu

**Unicode canonical equivalence** không có nghĩa mọi chuỗi nhìn giống nhau đều an toàn khi coi là một. Ví dụ các ký tự trông tương tự (homoglyph/confusable) có thể thuộc các scripts hoặc code points khác nhau mà **NFC không hợp nhất chúng**.

Các nguyên tắc cần biết:

1. **NFC không phải bộ phát hiện confusable hoặc phishing.** Nếu xử lý identifier công khai, username hay domain, còn cần quy tắc kiểm tra script, confusable, mixed-script và policy tương ứng.
2. **NFKC làm mất một số phân biệt compatibility.** Chỉ dùng khi domain có contract rõ, không âm thầm áp dụng lên mọi văn bản/khóa.
3. **Không tự ý normalize password/passphrase.** Nếu hệ thống xác thực có chính sách normalization xác định, cả lúc đăng ký và lúc verify phải áp dụng thống nhất; thêm normalization một phía có thể làm mất khả năng đăng nhập hoặc tạo ra trường hợp aliasing không mong muốn.
4. **Không sửa text trước khi xác minh chữ ký số/hash nếu giao thức ký bytes nguyên gốc.** Thay đổi normalization có thể thay đổi bytes dù văn bản trông giống nhau.
5. **Không dùng accent-insensitive key làm unique identity mặc định.** Những từ tiếng Việt khác nhau có thể trùng sau khi bỏ dấu.
6. **Chuẩn hóa không sửa dữ liệu lỗi encoding.** Tách rõ decoding, validation, normalization và domain-specific matching.
7. **Test text nhiều ngôn ngữ.** Một quy tắc dùng được với tiếng Việt có thể làm hỏng tên người hoặc nội dung thuộc ngôn ngữ khác.

Trong bài toán tìm kiếm hỗ trợ người dùng, có thể lưu **search key không dấu** như một chỉ mục phụ nhưng vẫn giữ **display text** đúng dấu.

## 13. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| Hai chuỗi hiển thị là **ắ** nhưng equals trả false | Một chuỗi NFC, một chuỗi NFD | In code points; chuẩn hóa cùng NFC/NFD trước khi compare |
| Tên tiếng Việt có dấu đếm length lớn bất ngờ | Dấu tổ hợp là code points riêng | Dùng **Pattern \\X** nếu muốn đếm grapheme clusters |
| Cắt một ký tự làm mất dấu | substring cắt giữa base và combining mark | Cắt theo grapheme boundary, không cắt tùy tiện bằng code units |
| Lưu UTF-8 rồi đọc lại vẫn rawEqual false | Encoding không tự normalize | Chọn NFC/NFD tại biên trước khi serialize |
| Search không dấu không tìm ra **Đặng** khi gõ dang | NFD không tự map đ→d | Đặt search policy có mapping đ/Đ nếu nghiệp vụ yêu cầu |
| Bỏ dấu làm nhiều từ trùng nhau | Diacritic stripping mất thông tin | Không dùng làm identity/unique key, giữ văn bản gốc |
| Dùng \p{L} không match dấu tách rời | Combining mark thuộc category M | Có rule xử lý marks và validate theo ngữ cảnh |
| Dùng equalsIgnoreCase tưởng đã normalize | Case-insensitive matching khác canonical equivalence | Normalize riêng; xác định case policy rõ |
| Regex chỉ nhận ASCII | [A-Za-z] không đầy đủ Unicode | Dùng Unicode properties và kiểm thử NFC/NFD |
| Sort text tiếng Việt theo String.compareTo cho kết quả lạ | So sánh UTF-16 không phải collation tiếng Việt | Xem xét Collator theo locale phù hợp |
| Tiếng Việt hiển thị sai dấu dù code points hợp lệ | Font/shaping/terminal không hỗ trợ hoặc mark không đúng | Kiểm tra code points, font và rendering; không đổ lỗi ngay cho Normalizer |
| Database có duplicate keys trông giống nhau | Unique constraint/collation và normal form không nhất quán | Thiết kế canonical key và migration plan |
| Normalize rồi signature không còn hợp lệ | Byte sequence được ký đã đổi | Tôn trọng hợp đồng chữ ký và xác thực bytes theo protocol |
| NFKC biến nhiều ký hiệu khác nhau thành một dạng | Compatibility transformation có chủ ý mất phân biệt | Chỉ dùng NFKC theo quy tắc rõ |
| Dữ liệu lỗi font/mojibake không được sửa | Normalizer không giải mã lại bytes sai | Sửa encoding/decoding ở nguồn |
| Grapheme count thay đổi theo version JDK | Unicode segmentation rules thay đổi theo phiên bản hỗ trợ | Test với toolchain đã chọn và quy tắc sản phẩm |

### 13.1. Quy trình điều tra một bug tiếng Việt

Khi nhận báo cáo “hai tên giống nhau mà không tìm được”:

1. Lấy hai chuỗi trong test hoặc môi trường kiểm tra được phép; tránh ghi dữ liệu cá nhân nhạy cảm vào log production.
2. In **dãy code points** theo dạng U+XXXX trong test/dev để phát hiện precomposed vs combining.
3. Kiểm tra **Normalizer.isNormalized(text, NFC)** và so sánh kết quả **Normalizer.normalize(..., NFC)**.
4. Xác nhận charset ở đầu vào và serialization; không coi UTF-8 là normalization.
5. Kiểm tra database collation/unique constraints và search index mapping có cùng policy không.
6. Tách rõ exact matching, case-insensitive matching và accent-insensitive search.
7. Kiểm thử cả **đ/Đ** vì NFD không xóa nét của chúng.
8. Nếu lỗi liên quan cursor, substring hay độ dài, so sánh code units, code points và grapheme clusters.
9. Nếu liên quan security identifiers, ký số hoặc password, kiểm tra protocol trước khi thay đổi normalization.

## 14. Checklist khi viết ứng dụng Java xử lý tiếng Việt

- [ ] Chuẩn bị ví dụ thử cả NFC và NFD, đặc biệt các chữ như **ắ, ộ, ơ, ư**.
- [ ] Phân biệt các tầng **UTF-16 units / Unicode code points / grapheme clusters**.
- [ ] Chọn **NFC** hay form khác theo contract, không dựa vào giả định mọi input đã cùng form.
- [ ] Normalize nhất quán ở nhập, lưu trữ, index và truy vấn khi cần canonical text.
- [ ] Không dùng String.equals để kỳ vọng canonical equivalence nếu chưa normalize.
- [ ] Không xóa combining marks trong dữ liệu hiển thị nếu cần giữ dấu.
- [ ] Nếu có accent-insensitive search, lưu search key riêng và định nghĩa rõ quy tắc với **đ/Đ**.
- [ ] Không coi bỏ dấu là cùng nghĩa hoặc cùng danh tính.
- [ ] Cắt/đếm ký tự hiển thị bằng segmentation phù hợp, không chỉ String.length().
- [ ] Dùng UTF-8 rõ ràng ở ranh giới byte nhưng nhớ encoding không tự normalize.
- [ ] Kiểm thử database unique constraints, các phiên bản JDK và collation của sản phẩm.
- [ ] Không biến đổi password, signature bytes hoặc opaque identifiers ngoài protocol.
- [ ] Giữ dữ liệu tiếng Việt gốc để hiển thị đúng với người dùng.

## 15. Bài tập tự luyện

1. Tạo hai chuỗi **á** theo U+00E1 và U+0061 U+0301. In code points, length và UTF-8 bytes length; giải thích vì sao raw equals khác sau NFC.
2. Tạo một String gồm **ắ, ộ, ơ, ư** rồi chuyển sang NFD. Dùng **codePoints()** liệt kê các combining marks xuất hiện.
3. Viết hàm **sameCanonicalText(a,b)** normalize hai đầu vào cùng NFC và so sánh. Kiểm thử với **Tiếng Việt** ở NFC/NFD.
4. Sửa hàm **searchKey** để xử lý chuỗi người dùng nhiều từ, nhưng vẫn giữ bản gốc có dấu. Thử các từ **ma, má, mã, mạ** và đánh giá collision.
5. Viết test cho **Đặng**: xác nhận NFD và chỉ xóa marks **không** biến Đ thành D; sau đó áp dụng mapping riêng để nhận kết quả mong muốn.
6. Tạo một String có emoji ngoài BMP; so sánh **length**, **codePointCount** và **\\X**. Vì sao số lượng có thể khác nhau?
7. Tạo chức năng cắt tên theo tối đa **5 extended grapheme clusters** mà không chia đôi dấu tổ hợp. Viết kiểm thử cả NFC và NFD.
8. So sánh danh sách tên tiếng Việt bằng **String.compareTo** và **Collator** với locale **vi-VN**; xem khác biệt và kiểm tra output theo JDK bạn sử dụng.
9. Giả sử backend cần đưa ra unique index cho displayName đã lưu nhiều năm. Lập migration plan khi NFC có thể làm hai keys cũ trở thành một.
10. Kiểm tra pipeline dùng chữ ký số: nếu bytes được ký ở NFD và bên nhận tự đổi sang NFC, điều gì có thể xảy ra? Thiết kế lại contract để tránh sửa bytes đã được ký.

## Kết luận

**Một chữ người dùng nhìn thấy không nhất thiết là một code point, và một code point không đồng nghĩa một Java char trong mọi trường hợp.** Với tiếng Việt, dấu thanh/dấu tạo dạng chữ có thể được lưu dưới dạng **ký tự dựng sẵn** hoặc **ký tự cơ sở + dấu tổ hợp**, hai cách canonically equivalent nhưng khác dãy code units và bytes.

Trong Java, **java.text.Normalizer** là công cụ chuẩn để đưa text về NFC hoặc NFD; **String.codePoints()** giúp quan sát mã Unicode, còn regex **\\X** hỗ trợ đếm extended grapheme clusters. Dùng NFC theo policy thống nhất cho nhiều bài toán exact text, và tách riêng nghiệp vụ **bỏ dấu tìm kiếm**, **collation**, **UI segmentation** và **security-sensitive byte matching**. Không nhầm Unicode normalization với encoding hoặc sửa lỗi chính tả tiếng Việt.

**Tài liệu tham khảo chính thức, còn áp dụng:**

- [Unicode Standard Annex #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
- [Unicode Standard, chương về Latin và tiếng Việt](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-7/)
- [Unicode FAQ: Normalization](https://unicode.org/faq/normalization.html)
- [Java SE 25: java.text.Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 25: Normalizer.Form](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.Form.html)
- [Java SE 25: java.util.regex.Pattern và \\X](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 25: java.lang.String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [Java SE 25: java.text.Collator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Collator.html)