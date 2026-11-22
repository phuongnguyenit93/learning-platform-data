# Độ dài của tiếng Việt, dấu kết hợp và emoji trong Java

## 1. Vì sao đếm ký tự lại khó?

Khi người dùng nhập **“Việt”**, **“ắ”**, **“😊”** hoặc **“👩‍💻”**, mỗi hình thức hiển thị có vẻ gồm những chữ hoặc biểu tượng rõ ràng. Tuy nhiên, một chuỗi có thể được đo theo nhiều đơn vị khác nhau. Trong Java, gọi **String.length()** không đồng nghĩa với “đếm bao nhiêu chữ người dùng nhìn thấy”.

Ví dụ:

- Chữ **“ắ”** viết sẵn dưới dạng Unicode U+1EAF có **1 đơn vị mã UTF-16**, **1 code point**, **1 cụm ký tự hiển thị**.
- Chữ có hình thức tương tự nhưng được tạo từ **a + dấu breve + dấu sắc** (**a\u0306\u0301**) có **3 đơn vị mã**, **3 code point**, nhưng vẫn là **1 cụm ký tự hiển thị**.
- Emoji **“😊”** gồm **1 code point** nhưng cần **2 đơn vị mã UTF-16**.
- Emoji **“👩‍💻”** gồm **3 code point** liên kết thành **1 biểu tượng**; trong Java, chuỗi này dài **5 đơn vị mã UTF-16**.

Vì vậy, trước khi giới hạn tên người dùng, cắt văn bản, định vị con trỏ hay đo dung lượng byte, phải xác định **“độ dài” đang nói đến loại đơn vị nào**.

## 2. Bốn đơn vị cần phân biệt

| Đơn vị | Diễn giải | Cách đo trong Java | Dùng khi nào? |
| --- | --- | --- | --- |
| **UTF-16 code unit** | Một đơn vị 16 bit trong giao diện chuỗi Java | **s.length()**; chỉ số của **charAt()**, **substring()** | Tương thích API, lấy chỉ số UTF-16 |
| **Unicode code point** | Giá trị mã Unicode, ví dụ U+1F60A | **s.codePointCount(0, s.length())** hoặc **s.codePoints().count()** | Duyệt/kiểm tra các giá trị Unicode |
| **Extended grapheme cluster** | Cụm code point thường được người dùng cảm nhận như một ký tự | Regex **\\X** hoặc thư viện phân đoạn Unicode | Giới hạn số ký tự hiển thị, cắt gần với thao tác nhập liệu |
| **Byte sau khi mã hóa** | Số byte của chuỗi ở một charset xác định | **s.getBytes(StandardCharsets.UTF_8).length** | Kích thước payload, tệp, giới hạn lưu trữ |

**UTF-16 code unit không phải byte UTF-8.** Một Java **char** chứa một code unit UTF-16; với ký tự ngoài Basic Multilingual Plane (BMP), một code point phải dùng **hai char** là *surrogate pair*. Ngược lại, một grapheme có thể chứa nhiều code point, chẳng hạn chữ có dấu kết hợp hoặc emoji ghép.

Từ Java 9, triển khai String có thể dùng cơ chế *compact strings* để tối ưu bộ nhớ. Điều đó **không làm thay đổi** quy tắc của các API tính theo UTF-16 code unit. Không suy ra kích thước vật lý của đối tượng String từ **length()**.

### Bảng giá trị minh họa

Các ví dụ dưới đây là những chuỗi cụ thể, với dấu tiếng Việt trong cột NFC được dùng ở dạng dựng sẵn:

| Chuỗi | UTF-16 units | Code points | Grapheme clusters | UTF-8 bytes |
| --- | ---: | ---: | ---: | ---: |
| **“Việt”** (NFC) | 4 | 4 | 4 | 6 |
| **“Việt”** (NFD: chữ **ệ** tách thành **e + dấu nặng + dấu mũ**) | 6 | 6 | 4 | 8 |
| **“ắ”** (NFC) | 1 | 1 | 1 | 3 |
| **“a\u0306\u0301”** (NFD; a + hai dấu kết hợp) | 3 | 3 | 1 | 5 |
| **“😊”** | 2 | 1 | 1 | 4 |
| **“👍🏽”** (ngón tay cái + tông da) | 4 | 2 | 1 | 8 |
| **“👩‍💻”** (người phụ nữ + ZWJ + máy tính) | 5 | 3 | 1 | 11 |
| **“🇻🇳”** (hai regional indicator) | 4 | 2 | 1 | 8 |

Số grapheme ở bảng theo quy tắc **extended grapheme cluster** của Unicode áp dụng cho các tổ hợp được nêu. Bộ dữ liệu Unicode trong JDK hoặc thư viện cụ thể có thể ảnh hưởng việc nhận diện những emoji mới xuất hiện sau phiên bản được hỗ trợ.

## 3. Tiếng Việt: dấu dựng sẵn và dấu kết hợp

### 3.1. Hai cách mã hóa có thể nhìn giống nhau

Một chữ tiếng Việt có dấu đôi khi là **một code point dựng sẵn (precomposed)**, đôi khi là **chữ cơ sở cộng các combining mark**.

Với chữ **“ắ”**:

- Dạng dựng sẵn NFC: **U+1EAF** — LATIN SMALL LETTER A WITH BREVE AND ACUTE.
- Dạng tách NFD: **U+0061** (a) + **U+0306** (COMBINING BREVE) + **U+0301** (COMBINING ACUTE).

Cả hai thường được hiển thị như cùng một chữ **ắ**. Tuy nhiên:

~~~java
String composed = "\u1EAF";
String decomposed = "a\u0306\u0301";

System.out.println(composed.length());        // 1
System.out.println(decomposed.length());      // 3
System.out.println(composed.equals(decomposed)); // false
~~~

Đây là **đoạn mã minh họa** đặt trong một phương thức. Phép **equals()** so sánh nội dung theo các code unit, không tự nhận diện rằng hai cách mã hóa tương đương về chuẩn Unicode.

Trong văn bản tiếng Việt, các chữ có tổ hợp dấu như **ắ, ậ, ệ, ỡ, ự** có thể có dạng dựng sẵn và dạng tách. Với từ **“Việt”**, chuỗi NFC có 4 code point; khi chuyển sang NFD, **ệ** trở thành **e + dấu nặng (U+0323) + dấu mũ (U+0302)**, đưa tổng số lên 6 code point. Số chữ mà người đọc nhận thấy vẫn là 4.

Dấu có thể trông khác đôi chút tùy phông, hệ thống vẽ chữ và quy tắc kết hợp dấu; chỉ nhìn hình ảnh không phải là cách xác nhận nội dung Unicode.

### 3.2. Unicode normalization

Lớp **java.text.Normalizer** cung cấp phép chuẩn hóa có định nghĩa rõ ràng:

- **NFC** (*Normalization Form C*): dùng canonical decomposition rồi canonical composition, giúp biểu diễn những chuỗi tương đương chuẩn theo dạng kết hợp khi có thể.
- **NFD** (*Normalization Form D*): tách các ký tự có canonical decomposition thành thành phần cơ sở và dấu kết hợp, đồng thời sắp xếp canonical combining mark theo quy tắc Unicode.
- **NFKC/NFKD**: còn thực hiện compatibility normalization, có thể biến đổi những khác biệt mang ý nghĩa trình bày hoặc tương thích. Chỉ dùng khi bài toán thực sự yêu cầu.

Ví dụ:

~~~java
import java.text.Normalizer;

String left = "\u1EAF";
String right = "a\u0306\u0301";

String normalizedLeft = Normalizer.normalize(left, Normalizer.Form.NFC);
String normalizedRight = Normalizer.normalize(right, Normalizer.Form.NFC);
System.out.println(normalizedLeft.equals(normalizedRight)); // true
~~~

**NFC không bỏ dấu tiếng Việt.** Chuẩn hóa cũng không phải phép chuyển tiếng Việt sang không dấu (*transliteration*). Nếu cần so sánh hoặc tìm kiếm bỏ dấu, phải thiết kế nghiệp vụ riêng vì việc xóa combining mark có thể làm mất thông tin và không giải quyết đầy đủ mọi chữ (ví dụ **đ** không tự trở thành **d** chỉ bằng NFD).

**Không chuẩn hóa một cách tùy tiện** đối với chữ ký số, tên tài nguyên yêu cầu đối chiếu byte chính xác, dữ liệu phải giữ nguyên bản gốc hoặc hợp đồng API có quy tắc cụ thể. Nếu nghiệp vụ định chuẩn hóa, hãy làm nhất quán tại ranh giới nhập dữ liệu, lưu trữ và so sánh.

## 4. Emoji và surrogate pair

### 4.1. Emoji gồm một code point nhưng hai code unit

Emoji **“😊”** là code point **U+1F60A**, nằm ngoài BMP. Trong UTF-16, nó được mã hóa bằng surrogate pair **U+D83D U+DE0A**:

~~~java
String emoji = "😊";

System.out.println(emoji.length());                           // 2
System.out.println(emoji.codePointCount(0, emoji.length()));  // 1
System.out.println(Character.isHighSurrogate(emoji.charAt(0))); // true
System.out.println(Character.isLowSurrogate(emoji.charAt(1)));  // true
System.out.printf("U+%X%n", emoji.codePointAt(0));              // U+1F60A
~~~

Mỗi lệnh trong đoạn trên phù hợp khi đặt vào một phương thức Java. **charAt(0)** trả về phần đầu của surrogate pair, **không phải emoji hoàn chỉnh**. Cắt **emoji.substring(0, 1)** tạo String chỉ chứa một high surrogate không ghép cặp, có thể gây hiển thị hoặc chuyển mã sai.

Để đi qua từng code point, có thể dùng **codePoints()**, **codePointAt(...)** hoặc **offsetByCodePoints(...)**. Tuy vậy, đi theo code point vẫn chưa đảm bảo không chia cắt một emoji do nhiều code point ghép lại.

### 4.2. Modifier, dấu nối ZWJ và quốc kỳ

Một số emoji gồm **nhiều code point**:

- **“👍🏽”** gồm U+1F44D (thumbs up) và U+1F3FD (skin tone modifier). Hai code point, bốn code unit UTF-16, thường hiển thị một biểu tượng.
- **“👩‍💻”** gồm U+1F469 (woman), U+200D (ZERO WIDTH JOINER, ZWJ) và U+1F4BB (laptop). Ba code point nhưng là một extended grapheme cluster theo quy tắc liên quan.
- **“🇻🇳”** là cặp regional indicator U+1F1FB và U+1F1F3. Hai code point, bốn UTF-16 code unit, thường hiển thị một lá cờ.
- Một số trình tự emoji còn dùng variation selector như U+FE0F để yêu cầu cách trình bày emoji. Variation selector cũng là code point và góp vào độ dài.

Vì thế, ngay cả **codePointCount()** cũng có thể cho kết quả lớn hơn số biểu tượng người dùng nhìn thấy. Hình dạng emoji thật sự phụ thuộc hỗ trợ của font, nền tảng và phiên bản dữ liệu Unicode; một cụm hợp lệ có thể hiện thành nhiều hình riêng khi môi trường không hỗ trợ ghép.

## 5. Grapheme cluster: đơn vị gần với ký tự người dùng

Unicode Standard Annex #29 định nghĩa quy tắc *grapheme cluster boundaries*. Một **extended grapheme cluster** có thể gồm chữ cái và dấu kết hợp, base emoji cộng modifier, trình tự ZWJ hoặc cặp regional indicator.

Java 17 hỗ trợ ký hiệu regex **\\X**, khớp một extended grapheme cluster theo dữ liệu Unicode được JDK sử dụng. Ví dụ:

~~~java
import java.util.regex.Pattern;

Pattern grapheme = Pattern.compile("\\X");
String text = "A👩‍💻B";

long visibleUnits = grapheme.matcher(text).results().count();
System.out.println(visibleUnits); // 3
~~~

Phương thức **Matcher.results()** trả về Stream các kết quả khớp; mỗi kết quả của regex này ứng với một grapheme cluster. Cách đếm này phù hợp với nhiều giới hạn ký tự ở giao diện, nhưng *grapheme cluster* vẫn là một đơn vị phân đoạn Unicode, **không phải** bảo đảm rằng hình hiển thị có bề rộng một cột hay đúng một glyph. Về chiều rộng trên terminal/UI, còn phải xét font, shaping, layout và grapheme rendering.

**BreakIterator.getCharacterInstance(...)** là một API phân đoạn khác trong Java. Khả năng phân đoạn các chuỗi emoji phức tạp và phiên bản dữ liệu Unicode cần được kiểm tra theo JDK thực tế. Khi cần kết quả nhất quán giữa web, mobile và server, hoặc emoji mới nhất, hãy quy định phiên bản Unicode và cân nhắc thư viện chuyên dụng như ICU4J; chạy bộ kiểm thử với các chuỗi thực tế.

## 6. Ví dụ Java 17+ hoàn chỉnh: so sánh cả bốn loại độ dài

Lưu chương trình sau thành tệp **UnicodeLengthDemo.java** với mã hóa UTF-8.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeLengthDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void describe(String label, String value) {
        int units = value.length();
        int points = value.codePointCount(0, units);
        long clusters = GRAPHEME.matcher(value).results().count();
        int bytes = value.getBytes(StandardCharsets.UTF_8).length;

        System.out.printf(
                "%s | units=%d | points=%d | clusters=%d | UTF8=%d%n",
                label, units, points, clusters, bytes);
    }

    public static void main(String[] args) {
        String vietnameseNfc = "Việt";
        String vietnameseNfd = Normalizer.normalize(
                vietnameseNfc, Normalizer.Form.NFD);

        String aNfc = "\u1EAF";
        String aNfd = "a\u0306\u0301";

        describe("VIET_NFC", vietnameseNfc);
        describe("VIET_NFD", vietnameseNfd);
        describe("A_NFC", aNfc);
        describe("A_NFD", aNfd);
        describe("SMILE", "😊");
        describe("TONE", "👍🏽");
        describe("ZWJ", "👩‍💻");
        describe("FLAG", "🇻🇳");

        System.out.println("plain equals: " + aNfc.equals(aNfd));
        String normalizedA = Normalizer.normalize(
                aNfc, Normalizer.Form.NFC);
        String normalizedB = Normalizer.normalize(
                aNfd, Normalizer.Form.NFC);
        System.out.println(
                "NFC equals: " + normalizedA.equals(normalizedB));

        String emoji = "😊";
        System.out.println(
                "emoji high surrogate: " +
                Character.isHighSurrogate(emoji.charAt(0)));
        System.out.printf("emoji point=U+%X%n", emoji.codePointAt(0));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 UnicodeLengthDemo.java
java UnicodeLengthDemo
~~~

Kết quả stdout cho các chuỗi mẫu với quy tắc grapheme nêu ở trên:

~~~text
VIET_NFC | units=4 | points=4 | clusters=4 | UTF8=6
VIET_NFD | units=6 | points=6 | clusters=4 | UTF8=8
A_NFC | units=1 | points=1 | clusters=1 | UTF8=3
A_NFD | units=3 | points=3 | clusters=1 | UTF8=5
SMILE | units=2 | points=1 | clusters=1 | UTF8=4
TONE | units=4 | points=2 | clusters=1 | UTF8=8
ZWJ | units=5 | points=3 | clusters=1 | UTF8=11
FLAG | units=4 | points=2 | clusters=1 | UTF8=8
plain equals: false
NFC equals: true
emoji high surrogate: true
emoji point=U+1F60A
~~~

**Giải thích kết quả:**

1. **VIET_NFC** và **VIET_NFD** giữ bốn chữ người dùng nhìn thấy; dạng NFD tăng số code unit, code point và byte vì dấu của **ệ** được tách riêng.
2. **A_NFC** và **A_NFD** hiển thị tương đương nhưng có độ dài code unit khác nhau. **equals()** trả về **false** trước chuẩn hóa, **true** sau NFC.
3. Emoji đơn **😊** có 2 code unit nhưng 1 code point. **👍🏽**, **👩‍💻** và **🇻🇳** có nhiều code point, song mỗi chuỗi mẫu là 1 grapheme cluster.
4. **UTF8** là độ dài của dữ liệu *sau khi mã hóa UTF-8*, không phải **String.length()**; với trình tự ZWJ trong ví dụ, đó là 11 byte.
5. **codePointAt(0)** đọc toàn bộ code point U+1F60A khi vị trí 0 là đầu một surrogate pair hợp lệ.

Lưu ý: file nguồn phải được lưu dưới UTF-8 để literal tiếng Việt và emoji trong chương trình giữ đúng giá trị. Tham số **-encoding UTF-8** quy định cách trình biên dịch đọc file nguồn.

## 7. Cắt chuỗi theo grapheme thay vì vị trí UTF-16

Giả sử đầu vào là **“A👩‍💻B”**. Chuỗi gồm 7 code unit UTF-16: A (1) + emoji ZWJ (5) + B (1), nhưng gồm **3 grapheme cluster**.

Cắt **substring(0, 2)** sẽ không giữ nguyên biểu tượng emoji; nó chọn A và một phần surrogate pair của ký tự đầu trong tổ hợp. Cắt theo 2 code point cũng không phải giữ đủ emoji “👩‍💻”.

Nếu yêu cầu sản phẩm là “giữ hai ký tự người dùng nhìn thấy đầu tiên”, nên tìm ranh giới grapheme. Lưu đoạn dưới trong **GraphemeTruncateDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeTruncateDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    static String firstGraphemes(String value, int maxClusters) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        if (maxClusters < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        Matcher matcher = GRAPHEME.matcher(value);
        int end = 0;

        for (int i = 0; i < maxClusters && matcher.find(); i++) {
            end = matcher.end();
        }

        return value.substring(0, end);
    }

    public static void main(String[] args) {
        String original = "A👩‍💻B";

        System.out.println(original.length());
        System.out.println(GRAPHEME.matcher(original).results().count());
        System.out.println(firstGraphemes(original, 2));
        System.out.println(firstGraphemes(original, 0).isEmpty());
        System.out.println(firstGraphemes(original, 99));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GraphemeTruncateDemo.java
java GraphemeTruncateDemo
~~~

~~~text
7
3
A👩‍💻
true
A👩‍💻B
~~~

Phương thức **Matcher.end()** trả về vị trí cuối của kết quả khớp trong **chỉ số UTF-16** — chính loại chỉ số mà **substring(0, end)** mong đợi. Việc lấy ranh giới từ kết quả phân đoạn giúp không cắt giữa cluster đối với các chuỗi mà regex nhận diện đúng. Nếu giới hạn là 0, chuỗi trả về rỗng; nếu giới hạn lớn hơn số cluster, kết quả là chuỗi gốc.

Đây là phương pháp phân đoạn văn bản, không phải biện pháp rút gọn để vừa số byte. Với payload có giới hạn byte, cần một thuật toán khác vừa tôn trọng ranh giới grapheme vừa đo bytes sau encoding.

## 8. Chọn đúng đơn vị độ dài theo yêu cầu nghiệp vụ

| Bài toán | Đơn vị thường phù hợp | Lưu ý |
| --- | --- | --- |
| API Java yêu cầu vị trí cho **substring**, **charAt** | UTF-16 code unit | Không được đưa chỉ số code point vào API như thể chúng là offset UTF-16. |
| Duyệt các scalar Unicode hoặc phân tích code point | Code point | Chuỗi Java có thể chứa surrogate lẻ; cần chính sách xử lý dữ liệu không hợp lệ. |
| Form nhập “tối đa 20 ký tự người dùng nhìn thấy” | Grapheme cluster | Đồng bộ quy tắc phân đoạn giữa client/server và xác định Unicode version. |
| HTTP body hoặc cột lưu trữ có giới hạn byte | Byte theo charset được xác định | Đếm **getBytes(UTF_8).length** sau khi quyết định normalization. |
| Tìm kiếm tên tiếng Việt tương đương chuẩn | Chọn normalization phù hợp, thường NFC | Chuẩn hóa trước so sánh theo hợp đồng; cân nhắc cả case, locale và diacritics. |
| Trích đoạn giao diện | Grapheme boundary + quy tắc layout | Tránh cắt giữa dấu kết hợp/emoji; chiều rộng hiển thị vẫn do renderer quyết định. |

Một hệ thống có thể cần **hai giới hạn cùng lúc**: tối đa 30 grapheme cho trải nghiệm nhập liệu và tối đa 255 byte UTF-8 để tương thích giao thức. Các giới hạn này độc lập; không thể thay thế một giới hạn bằng phép đo của giới hạn kia.

Nếu ứng dụng lưu dữ liệu và kiểm tra độ dài ở cả client lẫn server, cần định nghĩa rõ: có chuẩn hóa NFC trước khi kiểm tra không, dùng quy tắc phân đoạn Unicode phiên bản nào, tính emoji ghép như thế nào và phần nào chịu trách nhiệm kiểm tra byte.

## 9. Các lỗi thường gặp

**Lỗi 1 — Dùng String.length() để giới hạn số chữ người dùng nhập.** Một chữ tiếng Việt NFD có thể cần 2–3 code unit; một emoji nhiều thành phần có thể cần 4–11 code unit hoặc nhiều hơn. Giới hạn theo **length()** có thể từ chối đầu vào hợp lý hoặc cắt không trọn cụm. Hãy chọn đơn vị đo dựa trên yêu cầu cụ thể.

**Lỗi 2 — Tưởng codePointCount() cho số emoji hiển thị.** **“👩‍💻”** là ba code point nhưng thường được vẽ thành một biểu tượng. Với giao diện nhập liệu, cần phân đoạn grapheme.

**Lỗi 3 — Cắt giữa surrogate pair.** **substring()** nhận UTF-16 offset; giá trị cắt tùy ý có thể tạo String chứa surrogate lẻ. Khi thao tác theo code point, dùng **offsetByCodePoints()**; khi thao tác theo ký tự hiển thị, dùng ranh giới grapheme.

**Lỗi 4 — So sánh hai chữ tiếng Việt nhìn giống nhau bằng equals() mà không xét normalization.** NFC và NFD có thể khác số code unit nên **equals()** trả về **false**. Chỉ chuẩn hóa nếu chính sách dữ liệu yêu cầu; phải bảo toàn bản gốc nếu có yêu cầu về byte chính xác.

**Lỗi 5 — Đổi NFD rồi xóa mọi dấu để “chuẩn hóa”.** Việc này là **bỏ dấu**, có thể làm mất ý nghĩa từ tiếng Việt. NFC/NFD đúng nghĩa Unicode không có mục tiêu xóa dấu; các thao tác so khớp bỏ dấu cần quy định riêng.

**Lỗi 6 — Coi String.length() là số byte UTF-8.** Emoji **😊** có **length()==2** nhưng UTF-8 là **4 byte**. Để kiểm tra giới hạn truyền/lưu, hãy mã hóa bằng charset xác định rồi đếm byte.

**Lỗi 7 — Tin rằng mọi môi trường đều hiển thị emoji giống nhau.** Unicode định nghĩa code point và nhiều quy tắc phân đoạn; hình ảnh cuối cùng phụ thuộc font, trình dựng chữ và hỗ trợ emoji của nền tảng. Cần thử nghiệm các chuỗi ZWJ, modifier, cờ và ký tự tổ hợp ở môi trường mục tiêu.

**Lỗi 8 — Đồng nhất code point với mọi scalar Unicode hợp lệ.** Java String có thể chứa **unpaired surrogate** do thao tác sai hoặc dữ liệu không hợp lệ. **codePointCount()** vẫn xử lý số vị trí theo API, nhưng điều đó không chứng minh chuỗi Unicode được mã hóa hợp lệ. Khi cần chuẩn Unicode nghiêm ngặt, phải kiểm tra đầu vào và chính sách thay thế/từ chối.

## 10. Câu hỏi tự kiểm tra

1. Tại sao hai cách biểu diễn chữ **ắ** có thể có **length()** bằng 1 và 3? — Vì một dạng dùng code point dựng sẵn, một dạng gồm chữ cơ sở và hai combining mark.
2. Vì sao **"😊".length() == 2** nhưng **codePointCount(...) == 1**? — Vì code point ngoài BMP dùng một surrogate pair trong UTF-16.
3. Vì sao **"👩‍💻"** có 3 code point nhưng có thể là 1 grapheme? — Vì các thành phần được nối bằng ZWJ thành một extended grapheme cluster.
4. Khi nào chọn **Normalizer.Form.NFC**? — Khi nghiệp vụ cần quy về dạng Unicode canonical nhất quán trước so sánh/xử lý; cần quy định cùng chính sách cho mọi dữ liệu liên quan.
5. Giới hạn 200 byte UTF-8 có nên dùng **s.length() <= 200** không? — Không. Cần đo byte UTF-8 sau khi áp dụng chuẩn hóa (nếu chính sách có).
6. Regex Java nào dùng để tìm các extended grapheme cluster? — **Pattern.compile("\\X")**, sau đó duyệt từng **Matcher.find()** hoặc dùng **results()**.
7. Vì sao phải quan tâm Unicode version của JDK? — Vì dữ liệu thuộc tính và phân đoạn có thể thay đổi khi Unicode cập nhật, nhất là với emoji mới.

## 11. Ghi nhớ

- **length() = UTF-16 code unit**, phù hợp với chỉ số của các API String nhưng không biểu thị đúng số ký tự nhìn thấy.
- **codePointCount() = số code point được đếm theo biểu diễn UTF-16**, chưa phải số biểu tượng emoji hay grapheme.
- **Grapheme cluster** là đơn vị hữu ích khi xử lý dấu tiếng Việt, emoji modifier, ZWJ và cờ trong giao diện nhập liệu.
- **NFC/NFD** có thể làm thay đổi độ dài của văn bản tiếng Việt mà vẫn giữ biểu diễn tương đương chuẩn về Unicode.
- **UTF-8 byte length** là phép đo riêng biệt, cần cho giới hạn truyền tải và lưu trữ.

Tài liệu kỹ thuật nền tảng: **java.lang.String**, **java.text.Normalizer**, **java.util.regex.Pattern** của Java SE 17 và **Unicode Standard Annex #29 — Unicode Text Segmentation**.