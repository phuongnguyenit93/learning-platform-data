# Vì sao String.compareTo không tương đương thứ tự từ điển địa phương

Khi làm ứng dụng Java đa ngôn ngữ, một danh sách được sắp xếp bằng **String.compareTo** có thể tạo ra thứ tự khiến người dùng ngạc nhiên: những tên viết hoa đứng trước tên viết thường; từ có dấu bị đẩy xa từ không dấu; và **file10** xuất hiện trước **file2**. Không phải do Java sắp xếp sai. Vấn đề nằm ở chỗ **String.compareTo** thực hiện một phép so sánh kỹ thuật theo các đơn vị **UTF-16**, còn **thứ tự từ điển** là tập quy tắc của ngôn ngữ/vùng, có thể tính đến chữ cái cơ sở, dấu, chữ hoa/thường và những biến thể khác.

Để sắp tên, nhãn, tiêu đề hoặc nội dung mà người dùng nhìn thấy, Java Core có **java.text.Collator**. Đối tượng này dùng **Locale** và bộ quy tắc collation của runtime để quyết định hai chuỗi đứng trước/sau nhau. Bài học giải thích bản chất của cả hai phương pháp, các cấp phân biệt của Collator, Unicode normalization, tác động lên SortedSet/SortedMap, CollationKey, hiệu năng, tính nhất quán giữa server và database, cùng ví dụ Java 17+.

## 1. “So sánh chuỗi” có thể là nhiều nghiệp vụ khác nhau

Xét các chuỗi:

~~~text
An
an
Ánh
Anh
Đào
dũng
Zebra
file2
file10
~~~

Có thể đặt ra những yêu cầu hoàn toàn khác:

| Mục đích | Quan hệ thứ tự mong muốn | Hướng giải quyết |
| --- | --- | --- |
| Tạo thứ tự kỹ thuật cố định cho String | So code unit UTF-16 | String.compareTo |
| Sắp danh bạ theo ngôn ngữ người xem | Collation theo Locale | Collator.getInstance(locale) |
| So hai cách mã hóa cùng chữ có dấu | Canonical Unicode equivalence | Normalizer NFC/NFD theo hợp đồng |
| Sắp tên tệp có số như file2, file10 | Natural/numeric-aware sorting | Comparator chuyên biệt |
| So ID, tên khóa giao thức | Theo quy định định danh/giao thức | Exact equality hoặc normalization được đặc tả |
| Tìm kiếm gần đúng, không phân biệt case/dấu | Phép matching, không nhất thiết là sorting | Search key hoặc search engine |
| Sắp theo nhiều trường | Tên theo Locale và ID làm tie-breaker | Comparator kết hợp |

**Không nên dùng cùng một comparator cho mọi vai trò.** Một thứ tự phù hợp cho menu người dùng chưa chắc đúng cho unique key, chữ ký, tên file kỹ thuật hoặc phân trang cơ sở dữ liệu.

## 2. String.compareTo so sánh UTF-16 như thế nào?

Theo hợp đồng Java 17, **String.compareTo(String anotherString)** so hai chuỗi theo thứ tự từ điển của các giá trị **char** (đơn vị UTF-16), từ trái sang phải.

- Khi gặp vị trí đầu tiên có hai char khác nhau, kết quả dựa trên hiệu giá trị của chúng.
- Nếu một chuỗi là tiền tố giống hệt của chuỗi còn lại, chuỗi ngắn hơn đứng trước.
- Giá trị trả về **nhỏ hơn 0**, **bằng 0** hoặc **lớn hơn 0** biểu thị quan hệ trước, bằng hoặc sau.
- Phương thức không tra **Locale**, không tự hạ chữ hoa, không nhận biết ngôn ngữ và không chuẩn hóa Unicode.
- Đối với ký tự ngoài BMP, một code point có thể gồm **hai char surrogate**, nên thứ tự UTF-16 không nhất thiết giống thứ tự theo giá trị số Unicode code point.

Ví dụ:

~~~text
'Z' = U+005A = 90
'a' = U+0061 = 97

"Z".compareTo("a") = 90 - 97 = -7
~~~

Kết quả đó đúng theo quy tắc kỹ thuật. Nhưng trong một từ điển, người đọc thường mong chữ A và a được xếp gần nhau thay vì toàn bộ chữ hoa tách khỏi toàn bộ chữ thường.

### 2.1. Chương trình có stdout chính xác

**File RawCompareDemo.java**

~~~java
import java.text.Normalizer;

public class RawCompareDemo {
    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Z-before-a="
                + ("Z".compareTo("a") < 0));

        System.out.println("file10-before-file2="
                + ("file10".compareTo("file2") < 0));

        System.out.println("raw-equal="
                + precomposed.equals(decomposed));

        String n1 = Normalizer.normalize(
                precomposed, Normalizer.Form.NFC);
        String n2 = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC-equal=" + n1.equals(n2));
        System.out.println("Z-vs-a=" + "Z".compareTo("a"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RawCompareDemo.java
java RawCompareDemo
~~~

Stdout:

~~~text
Z-before-a=true
file10-before-file2=true
raw-equal=false
NFC-equal=true
Z-vs-a=-7
~~~

**Giải thích:** số 10 bắt đầu bằng ký tự **1** nhỏ hơn **2**, cho nên String.compareTo đặt file10 trước file2. Chuỗi **é** dựng sẵn và chuỗi **e + dấu sắc kết hợp** có các code unit khác nhau, vì vậy equals trả false. Chuẩn hóa NFC đưa chúng về một dạng tương đương chính tắc. Nhưng **NFC vẫn không xác định thứ tự từ điển**; nó chỉ giải quyết sự khác nhau ở cấp biểu diễn Unicode.

### 2.2. compareTo không so theo Unicode code point trong mọi trường hợp

String dùng UTF-16, cho nên một code point như U+1F600 cần một surrogate pair. Trong khi đó, U+E000 là một code point BMP biểu diễn bằng một char. Thứ tự số code point sẽ đặt U+E000 trước U+1F600, nhưng giá trị high surrogate U+D83D nhỏ hơn U+E000, nên cách so theo char của String.compareTo có thể cho chiều ngược lại.

Điều này nhắc rằng **thứ tự compareTo là một định nghĩa cụ thể trên UTF-16**, không phải quy tắc tổng quát về mọi ký tự Unicode. Không nên diễn giải “so sánh theo mã Unicode” một cách quá đơn giản, nhất là với emoji và các hệ chữ ngoài BMP.

## 3. Thứ tự từ điển địa phương đòi hỏi gì?

Một hệ ngôn ngữ có thể sắp theo nhiều cấp trọng số, không chỉ code unit:

1. **Chữ cái cơ sở:** thứ tự chữ trong bảng chữ cái của ngôn ngữ.
2. **Dấu và biến thể:** cách sắp ký tự có dấu hoặc các dạng chữ cái đặc thù.
3. **Chữ hoa/thường:** có thể là khác biệt ưu tiên thấp hơn chữ cái cơ sở.
4. **Tổ hợp chữ:** một số ngôn ngữ có quy tắc so các tổ hợp ký tự.
5. **Dấu câu và khoảng trắng:** cách xếp dấu nháy, gạch nối, ký tự tách từ.
6. **Các dạng Unicode tương đương:** ký tự dựng sẵn và các dấu kết hợp.
7. **Locale và phiên bản quy tắc:** cùng một chữ có thể được cân nhắc khác ở các ngôn ngữ hoặc provider khác nhau.

Với tiếng Việt, các chữ như **ă, â, đ, ê, ô, ơ, ư** và các dấu thanh không thể được xử lý bằng cách chỉ lấy giá trị của một char. Với các ngôn ngữ khác, chữ **ä**, **å**, **ö** cũng có các truyền thống sắp xếp riêng.

**Không có một “alphabetical order quốc tế” áp dụng chính xác cho mọi ngôn ngữ.** Khi giao diện hứa hẹn “A–Z”, ứng dụng phải biết A–Z đang được hiểu theo lựa chọn ngôn ngữ của ai.

## 4. java.text.Collator giải quyết phần khác biệt ngôn ngữ

**Collator** là lớp cơ sở của Java dùng để so sánh chuỗi theo quy tắc địa phương hóa.

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);

int result = collator.compare(first, second);
~~~

Đây là đoạn minh họa trong một phương thức; cần import **java.text.Collator**, **java.util.Locale** và các biến **String first**, **String second**.

**Collator.getInstance(locale)** chọn comparator phù hợp với Locale và dữ liệu do JDK/provider cung cấp. Giá trị so sánh vẫn là âm/0/dương, nhưng quan hệ không còn được xác định bởi hiệu mã UTF-16 đầu tiên.

**Sự khác biệt mấu chốt:**

| String.compareTo | Collator.compare |
| --- | --- |
| So trực tiếp các char UTF-16 | Dựa trên trọng số collation |
| Không nhận Locale | Nhận Locale đã chọn |
| Không biết chữ và dấu theo ngôn ngữ | Có thể phân biệt nhiều cấp ngôn ngữ |
| Thích hợp cho thứ tự kỹ thuật | Thích hợp cho danh sách hiển thị |
| Thứ tự độc lập dữ liệu CLDR | Có thể đổi theo JDK/provider |
| Trả 0 khi String có cùng nội dung theo quan hệ compareTo | Có thể trả 0 cho hai String khác nhau ở cấp strength cấu hình |
| Không tự sắp file có số như số tự nhiên | Cũng không bảo đảm numeric natural sort |

**Collator không phải công cụ thay thế mọi phần mềm xử lý ngôn ngữ.** Nó không dịch văn bản, không sửa lỗi chính tả, không tự phân tích số trong tên và không đảm bảo ngăn được ký tự giả mạo trực quan.

## 5. Ví dụ sắp tên bằng Collator vi-VN

**File LocalizedNames.java**

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class LocalizedNames {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        Collator collator = Collator.getInstance(locale);

        List<String> names = new ArrayList<>(List.of(
                "Dung", "đào", "Anh", "Ánh", "an", "Zebra"));

        names.sort(collator::compare);

        names.forEach(System.out::println);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalizedNames.java
java LocalizedNames
~~~

Chương trình in sáu tên sau khi sắp theo collation vi-VN do runtime cung cấp. **Không ấn định một stdout duy nhất cho mọi phiên bản Java**, vì quy tắc locale, cách fallback và dữ liệu CLDR/provider có thể thay đổi. Mục tiêu là sử dụng đúng bộ quy tắc ngôn ngữ, thay vì lặng lẽ dùng thứ tự UTF-16.

Với Java 17, biểu thức **collator::compare** có thể được dùng tại vị trí chấp nhận comparator của String. Nếu danh sách có phần tử khác String hoặc null, cần xử lý đúng kiểu dữ liệu và null policy.

### 5.1. Sử dụng Locale người dùng đã được resolve

Ứng dụng có thể nhận ngôn ngữ từ hồ sơ, tùy chọn giao diện hoặc header Accept-Language. Nếu header chứa nhiều mục, phải phân tích, xác định mức ưu tiên và chọn trong **danh sách Locale được hỗ trợ**, không coi nguyên header là một language tag đơn.

Ví dụ:

~~~java
Locale displayLocale =
        Locale.forLanguageTag("vi-VN");

Collator collator =
        Collator.getInstance(displayLocale);
~~~

Không dùng **Locale.setDefault(...)** trên server để đổi ngôn ngữ cho từng request: đây là trạng thái toàn JVM, có thể ảnh hưởng request đồng thời. Truyền Locale tường minh là cách dự đoán được hơn.

Một danh sách chia sẻ nhiều người dùng có thể cần một Locale cố định do tổ chức quyết định. Khi đó thứ tự có thể không giống mong đợi của từng người, nhưng sẽ thống nhất nếu đó là hợp đồng của sản phẩm.

## 6. Strength: các cấp phân biệt của Collator

Collator cho phép chọn mức độ khác biệt được xem là quan trọng:

| Mức | Ý nghĩa khái quát |
| --- | --- |
| **Collator.PRIMARY** | So khác biệt cơ bản của các chữ/chuỗi theo collation |
| **Collator.SECONDARY** | Xét thêm khác biệt thứ cấp, thường gồm một số dấu |
| **Collator.TERTIARY** | Xét thêm khác biệt mức ba, thường gồm case/biến thể |
| **Collator.IDENTICAL** | Phân biệt sâu hơn khi các cấp trước ngang nhau |

Không nên diễn giải PRIMARY là “bỏ dấu của mọi ngôn ngữ” hoặc TERTIARY là “chắc chắn khác mọi chuỗi có code point khác nhau”. Việc phân bố trọng số cụ thể phụ thuộc vào **locale và dữ liệu/rule set**.

Với tiếng Anh Hoa Kỳ thông dụng, ở PRIMARY chữ **A** và **a** thường được xem là tương đương, còn ở TERTIARY chúng có thể được phân biệt. Cặp **cafe** và **café** thường biểu hiện khác biệt thứ cấp nhưng phải kiểm tra theo locale cần sử dụng.

### 6.1. Ví dụ quan sát mức strength

**File CollatorStrengthDemo.java**

~~~java
import java.text.Collator;
import java.util.Locale;

public class CollatorStrengthDemo {
    private static String relation(
            Collator c, String left, String right) {
        int order = c.compare(left, right);
        if (order == 0) return "equal";
        return order < 0 ? "before" : "after";
    }

    public static void main(String[] args) {
        Collator c = Collator.getInstance(Locale.US);
        c.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        c.setStrength(Collator.PRIMARY);
        System.out.println("PRIMARY A/a="
                + relation(c, "A", "a"));

        c.setStrength(Collator.SECONDARY);
        System.out.println("SECONDARY A/a="
                + relation(c, "A", "a"));

        c.setStrength(Collator.TERTIARY);
        System.out.println("TERTIARY A/a="
                + relation(c, "A", "a"));

        System.out.println("raw A/a="
                + "A".compareTo("a"));
    }
}
~~~

Chạy:

~~~bash
javac CollatorStrengthDemo.java
java CollatorStrengthDemo
~~~

Dòng cuối luôn là **raw A/a=-32** theo giá trị UTF-16. Ba dòng đầu **cố ý cho biết mối quan hệ do bộ collation hiện tại quyết định**, thường là equal ở PRIMARY/SECONDARY, còn TERTIARY phân biệt. Nếu cần snapshot nguyên văn, phải cố định JDK và provider mục tiêu.

**Không bao giờ viết điều kiện dựa trên kết quả Collator bằng -1 hoặc +1**. Chỉ xét giá trị âm, 0 và dương. Một comparator hợp lệ có thể trả những số nguyên âm/dương khác.

### 6.2. Strength ảnh hưởng cả equality của comparator

Nếu **compare(a,b) == 0**, Collator coi hai giá trị ngang nhau ở cấp cấu hình đang dùng. Điều đó không có nghĩa **a.equals(b)** là true. Hai phép kiểm tra phục vụ hai hợp đồng khác nhau.

Vì vậy, không được sử dụng strength thấp làm cơ chế khẳng định hai hồ sơ người dùng là một; một số khác biệt dấu/case có thể bị gom theo chủ đích sắp xếp.

## 7. Decomposition: thứ tự từ điển và biểu diễn Unicode

Một chữ **é** có thể được viết dưới hai dạng:

~~~text
U+00E9        é dựng sẵn
U+0065 U+0301 e + COMBINING ACUTE ACCENT
~~~

Hai String có thể trông như nhau nhưng **String.equals** và **String.compareTo** không tự xem chúng đồng nhất. Đây là **tương đương chính tắc**, khác với thứ tự từ điển.

Collator có ba lựa chọn decomposition:

| Chế độ | Vai trò |
| --- | --- |
| **Collator.NO_DECOMPOSITION** | Không thực hiện bước decomposition trước khi so sánh |
| **Collator.CANONICAL_DECOMPOSITION** | Phân rã chính tắc theo quy tắc Unicode khi collation |
| **Collator.FULL_DECOMPOSITION** | Cho phép phân rã tương thích rộng hơn |

Ví dụ cấu hình:

~~~java
Collator collator = Collator.getInstance(locale);
collator.setStrength(Collator.TERTIARY);
collator.setDecomposition(
        Collator.CANONICAL_DECOMPOSITION);
~~~

Đoạn trên dùng biến locale có sẵn. **Strength** là cấp phân biệt của collation; **decomposition** là cách xử lý biểu diễn Unicode. Chúng không phải hai tên gọi cho cùng một tùy chọn.

### 7.1. Normalizer không thay thế Collator

**Normalizer.normalize(s, Form.NFC)** biến chuỗi về dạng composed chính tắc, nên hai cách mã hóa tương đương có thể so bằng equals sau khi chuẩn hóa.

**Collator.compare(s,t)** áp các trọng số ngôn ngữ theo Locale và cấu hình. Một Collator PRIMARY có thể coi hai chuỗi không tương đương chính tắc là ngang nhau về thứ tự; còn NFC không làm được điều đó.

~~~java
String a = "\u00E9";
String b = "e\u0301";

boolean equalAfterNFC =
        Normalizer.normalize(
                a, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(
                b, Normalizer.Form.NFC));
~~~

Đây là đoạn minh họa cần import **java.text.Normalizer**, đặt trong phương thức. **equalAfterNFC** là true. Nhưng kết luận này chỉ nói về canonical equivalence của Unicode, chưa nói vị trí của chữ ấy trong từ điển tiếng Việt hoặc tiếng Pháp.

**FULL_DECOMPOSITION không phải tùy chọn mặc định tốt nhất cho mọi dữ liệu.** Compatibility decomposition có thể gom những dạng ký tự mang khác biệt trình bày hoặc ý nghĩa, như một số ligature và ký tự fullwidth. Cần xác định yêu cầu trước khi dùng.

## 8. Chữ có dấu trong tiếng Việt làm lộ giới hạn compareTo

Tiếng Việt có các chữ cái và tổ hợp dấu như **ă, â, đ, ê, ô, ơ, ư** và các dấu thanh. Một số ký tự là chữ cái độc lập trong bảng chữ cái, số khác là tổ hợp nhiều code point tùy cách mã hóa.

Nếu chỉ so giá trị UTF-16:

- Hai dạng dựng sẵn và decomposed có thể xếp khác.
- Chữ hoa và chữ thường có thể bị tách thành hai nhóm lớn.
- Chữ có dấu không chắc được đặt cạnh chữ cơ sở theo quy tắc từ điển.
- Các tên có nhiều ký tự khác nhau có thể bị quyết định thứ tự ở điểm Unicode hoàn toàn không liên quan ngữ nghĩa.

Tập dữ liệu kiểm thử nên có:

~~~text
An
Anh
Ánh
ân
ăn
Đào
Dung
Dũng
Thu
Thúy
Tú
Từ
~~~

Đây là dữ liệu **đầu vào**, không phải một bảng thứ tự từ điển được khẳng định sẵn. Hãy chạy Collator vi-VN trên JDK được hỗ trợ rồi đối chiếu với quy ước thực tế của sản phẩm.

Một số ứng dụng chuyên biệt như thư viện, cơ sở dữ liệu ngôn ngữ, từ điển học thuật có thể cần một bộ collation tailoring riêng. Locale mặc định từ JDK là một điểm khởi đầu tốt, nhưng không tự bảo đảm đáp ứng mọi quy chuẩn phân loại chuyên ngành.

## 9. compareToIgnoreCase cũng không tương đương collation

**String.compareToIgnoreCase** và **String.CASE_INSENSITIVE_ORDER** xử lý một phần khác biệt chữ hoa/chữ thường qua quy tắc case của Java. Chúng **không** tự động áp thứ tự từ điển của vi-VN, sv-SE hay tr-TR.

Những hạn chế quan trọng:

1. Không có tham số Locale cho phép chọn bộ quy tắc từ điển.
2. Không đưa toàn bộ dấu/cấu trúc chữ về trọng số thích hợp của mỗi ngôn ngữ.
3. Không phải phép Unicode full case folding cho mọi chuỗi.
4. Không tự chuẩn hóa canonical Unicode.
5. Không sắp số trong nhãn theo giá trị số.

Việc gọi **toLowerCase(Locale.ROOT)** trước khi compare có thể là một phần của *search key* theo hợp đồng cụ thể, nhưng không tự biến kết quả thành collation đúng. Lowercasing còn có những đặc tính theo ngôn ngữ, ví dụ các chữ liên quan **I/i** trong tiếng Thổ Nhĩ Kỳ.

**Sắp xếp**, **tìm kiếm gần đúng** và **so danh tính** phải được thiết kế riêng.

## 10. CollationKey cho việc so sánh nhiều lần

**java.text.CollationKey** biểu diễn khóa phục vụ so sánh theo một Collator cụ thể. Nếu cần sắp xếp một danh sách lớn với nhiều phép so lặp lại, tạo key trước có thể hữu ích.

~~~java
Collator collator = Collator.getInstance(locale);

CollationKey firstKey =
        collator.getCollationKey(first);
CollationKey secondKey =
        collator.getCollationKey(second);

int result = firstKey.compareTo(secondKey);
~~~

Đoạn minh họa cần import **Collator**, **CollationKey**, **Locale**, cùng các biến **locale**, **first**, **second**. Chỉ nên so sánh keys được tạo với **cùng một bộ quy tắc/cấu hình**: Locale, strength, decomposition và provider liên quan.

### 10.1. Ví dụ sắp bằng CollationKey

**File CollationKeyDemo.java**

~~~java
import java.text.CollationKey;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CollationKeyDemo {
    record Item(String text, CollationKey key) {}

    public static void main(String[] args) {
        Collator col = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        col.setStrength(Collator.TERTIARY);
        col.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        List<String> names = List.of(
                "Dung", "Dũng", "Ánh", "Anh", "Đào");

        List<Item> items = new ArrayList<>();
        for (String name : names) {
            items.add(new Item(
                    name, col.getCollationKey(name)));
        }

        items.sort(Comparator
                .comparing(Item::key)
                .thenComparing(Item::text));

        items.forEach(item ->
                System.out.println(item.text()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CollationKeyDemo.java
java CollationKeyDemo
~~~

Chương trình in năm tên theo khóa của bộ collation vi-VN đang có. Dùng **thenComparing(Item::text)** để xác định thứ tự phụ bằng raw String nếu hai khóa collation ngang nhau. Vì thứ tự tên phụ thuộc dữ liệu locale của JDK, không đưa stdout cố định cho mọi môi trường.

**Không lưu CollationKey vĩnh viễn trong database rồi mặc định nó còn hợp lệ sau nâng cấp JDK/CLDR.** Nếu dùng key vật lý cho index, phải có chính sách versioning và rebuild phù hợp. Cũng không được trộn keys được tạo dưới hai Locale/strength khác nhau.

## 11. TreeSet, TreeMap và rủi ro comparator trả 0

Đây là hậu quả thực tế rất quan trọng. **TreeSet** và **TreeMap** dựa trên **comparator equality**, không chỉ dựa trên String.equals.

~~~java
import java.text.Collator;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class CollatedSetExample {
    public static void main(String[] args) {
        Collator collator =
                Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);

        Set<String> names =
                new TreeSet<>(collator::compare);

        names.add("A");
        names.add("a");

        System.out.println(
                "rawEqual=" + "A".equals("a"));
        System.out.println(
                "collationEqual=" +
                (collator.compare("A", "a") == 0));
        System.out.println("size=" + names.size());
    }
}
~~~

Lưu **CollatedSetExample.java**, biên dịch bằng **javac CollatedSetExample.java** và chạy bằng **java CollatedSetExample**. Với rule set en-US điển hình ở PRIMARY, **rawEqual=false**, **collationEqual=true** và **size=1**. Đây là ví dụ về khác biệt giữa **identity dữ liệu** và **equality của comparator**, không phải khuyến nghị dùng TreeSet PRIMARY để loại dữ liệu người dùng.

**Khi dùng TreeMap**, đưa key mới có compare == 0 với key hiện có có thể cập nhật value của cùng entry. Nếu code coi hai tên khác chữ hoa hoặc dấu là hai thực thể khác nhau, dữ liệu có thể bị mất hoặc ghi đè ngoài ý muốn.

Để giữ mọi thực thể:

- Dùng **ID nghiệp vụ** riêng làm khóa định danh.
- Sắp các display name bằng Collator cho mục đích trình bày.
- Với TreeSet chứa String khác nhau, dùng một comparator có **tie-breaker** trả 0 chỉ khi raw String thật sự tương đương theo chính sách.
- Không thay strength của comparator sau khi cấu trúc SortedSet/SortedMap đã chứa dữ liệu, vì quan hệ thứ tự có thể bị thay đổi.

## 12. Tie-breaker và thứ tự toàn phần ổn định

Trong UI, hai chuỗi có thể ngang nhau theo Collator ở strength đang dùng. Một số sort như **List.sort** là **stable sort**, nên các phần tử comparator-equal giữ thứ tự tương đối ban đầu. Nhưng nếu dữ liệu đến từ database, API phân trang hay nhiều nguồn khác nhau, thứ tự đầu vào không phải lúc nào ổn định.

Một comparator gồm hai cấp:

~~~java
Comparator<String> order = (left, right) -> {
    int localized = collator.compare(left, right);
    if (localized != 0) {
        return localized;
    }
    return left.compareTo(right);
};
~~~

Đoạn minh họa nằm trong phương thức, cần import **Comparator** và biến Collator đã cấu hình. Cấp đầu dùng locale collation; cấp hai chỉ giải quyết những trường hợp collation-equivalent bằng thứ tự UTF-16.

**Ưu:** tránh trường hợp hai String khác nhau hoàn toàn bị coi cùng key chỉ vì strength thấp; tạo thứ tự phụ có thể dự đoán.

**Nhược:** thứ tự phụ không có tính ngôn ngữ; điều này chấp nhận được nếu nó chỉ áp dụng cho các mục đã ngang nhau theo quy tắc ngôn ngữ. Nếu nghiệp vụ muốn coi hai tên là cùng một khóa, không nên thêm tie-breaker rồi vô tình thay chính sách equality.

Với danh sách object, nên dùng một **ID bất biến** làm thứ tự phụ:

~~~java
records.sort(Comparator
        .comparing(Record::getDisplayName, collator::compare)
        .thenComparing(Record::getId));
~~~

Đây là **mã minh họa**, không phải chương trình độc lập: cần một class Record do dự án định nghĩa với getDisplayName/getId, cùng biến records và collator. Đừng sao chép nếu chưa có các kiểu và phương thức tương ứng.

## 13. Natural sorting không phải ngầm định của Collator

Trong danh sách file:

~~~text
file1
file2
file10
file20
~~~

người dùng thường muốn **file2** đứng trước **file10** vì xét giá trị số 2 nhỏ hơn 10. Nhưng String.compareTo đặt **file10** trước **file2**, vì tại vị trí khác đầu tiên chữ **1** nhỏ hơn **2**.

**Locale collation không đồng nghĩa natural/numeric sorting.** API java.text.Collator của Java Core không có một hợp đồng toàn cục bảo đảm nhận mọi dãy số trong tên rồi so chúng bằng giá trị số.

Nếu sản phẩm cần numeric ordering:

1. Xác định cách token hóa chữ và chữ số.
2. Xử lý số có số 0 ở đầu: **file2** so với **file02**.
3. Xử lý số quá lớn để đưa vào int/long.
4. Quy định ký tự chữ số Unicode được chấp nhận.
5. Xử lý nhãn có nhiều đoạn số, dấu chấm, version và hậu tố.
6. Kiểm tra tính bắc cầu và nhất quán của comparator tùy biến.

Không tự giải quyết bằng cách gọi **Integer.parseInt** trên toàn tên file; nó không xử lý được dữ liệu hỗn hợp. Với version **1.10** so với **1.2**, quy tắc lại khác và có thể cần parser version riêng.

## 14. Collation, tìm kiếm và chuẩn hóa là ba quyết định khác nhau

Các nhu cầu:

- “Tên nào đứng trước?” là **sorting**.
- “Gõ anh có tìm được Ánh không?” là **matching/search**.
- “Hai chuỗi e+dấu sắc và é có cùng nội dung Unicode không?” là **canonical equivalence**.
- “Hai tên có cùng định danh tài khoản không?” là **identity/uniqueness**.

Tất cả có thể liên quan đến Locale/Unicode, nhưng không dùng cùng một hàm rồi suy ra chúng tương đương.

Ví dụ, một Collator PRIMARY có thể coi một số dấu ở cấp phụ là không đáng kể. Nhưng không được tuyên bố “PRIMARY bỏ toàn bộ dấu trong mọi ngôn ngữ”. Chữ **đ** hay các dạng chữ khác có thể được coi là một chữ riêng theo quy tắc ngôn ngữ.

Với search cần accent-insensitive, có thể phải tạo một search key riêng hoặc dùng search engine hỗ trợ ngôn ngữ. **Không ghi đè bản gốc đã dịch hoặc tên người** chỉ vì muốn tìm kiếm linh hoạt.

## 15. Collator và phiên bản JDK, dữ liệu CLDR

**Collator.getInstance(locale)** dựa trên dữ liệu và quy tắc mà runtime hỗ trợ. Vì vậy:

- Kết quả có thể thay đổi khi cập nhật JDK hoặc provider.
- Locale không được hỗ trợ đầy đủ có thể được fallback theo cơ chế runtime.
- Strength và decomposition làm thay đổi quy tắc so ngay cả khi hai chuỗi không đổi.
- Các quy tắc dành cho tiếng Việt hoặc ngôn ngữ khác có thể có tailoring đặc biệt.
- Một thứ tự chuyên ngành (thư viện, từ điển học thuật, hồ sơ pháp lý) có thể cần chuẩn sắp xếp được phiên bản hóa, khác quy tắc mặc định.

**Đừng viết test snapshot một thứ tự locale tuyệt đối nếu không xác định JDK/provider.** Có thể test các tính chất của API và chạy bộ dữ liệu locale trên những runtime thực sự được triển khai. Nếu tổ chức yêu cầu một thứ tự bất biến nhiều năm, phải xác định phiên bản của bộ quy tắc collation, không chỉ chỉ định Locale.

### 15.1. Backend, database và client có thể sắp khác nhau

Một database có collation riêng, ví dụ quy tắc ORDER BY của engine. Java Collator và collation database có thể không đồng nhất. Nếu backend phân trang theo một thứ tự rồi client tự sắp từng trang theo Collator khác, danh sách không còn được sắp toàn cục:

~~~text
Database xếp tất cả record và chia thành trang
       |
       v
Client chỉ resort trong mỗi trang
       |
       v
Không bảo đảm toàn danh sách đúng thứ tự client muốn
~~~

Giải pháp là chọn một nguồn quyết định thứ tự **toàn bộ dữ liệu** trước khi phân trang, hoặc dùng bộ quy tắc hai bên đã kiểm tra tương thích. Khi các tên ngang nhau ở cấp collation, dùng tie-breaker ID để việc phân trang nhất quán hơn.

Không lưu/copy CollationKey của Java sang database rồi mặc định engine khác sẽ hiểu cùng quy tắc.

## 16. Null, chuỗi trống, dấu câu và emoji

Khi dữ liệu có null, cần quy định null đứng đầu hay cuối. Không để Collator tự quyết định:

~~~java
Comparator<String> order =
        Comparator.nullsLast(collator::compare);
~~~

Đoạn minh họa dùng import **Comparator** và biến collator. Với danh sách chứa String rỗng, tên bắt đầu bằng dấu gạch nối, apostrophe, khoảng trắng hoặc emoji, quy tắc sắp xếp có thể tùy locale.

Một số lưu ý:

- Normalizer không tự loại bỏ control characters và không phải công cụ phát hiện mọi ký tự vô hình.
- Chuỗi giống nhau về mặt hình ảnh có thể là nhiều code point khác nhau thuộc những hệ chữ khác nhau.
- Comparator không làm nhiệm vụ kiểm tra input có an toàn hay không.
- Đừng biến đổi dữ liệu gốc bằng trim/replace/lowercase tùy tiện chỉ để sort.
- Với dữ liệu hỗn hợp nhiều hệ chữ, cần test các tên thực tế của sản phẩm.

Nếu UI cần nullsFirst, dùng **Comparator.nullsFirst(...)**. Chọn rõ chính sách thay vì dựa trên ngoại lệ hoặc mặc định của các lớp dữ liệu.

## 17. Hiệu năng và tính an toàn đồng thời

**String.compareTo** thường rẻ vì chỉ so trực tiếp code unit. **Collator** có thể phải tra nhiều trọng số ngôn ngữ; **CollationKey** có thể hỗ trợ khi một danh sách lớn cần nhiều phép so lặp.

Tuy nhiên, tạo CollationKey, lưu key và xây danh sách trung gian đều tốn bộ nhớ/CPU. Trước khi tối ưu, đo thời gian trên dữ liệu thực tế. Đối với danh sách nhỏ, code rõ ràng thường quan trọng hơn kỹ thuật cache.

**Collator là đối tượng có trạng thái mutable**, chứa strength và decomposition. Không nên chia sẻ một instance rồi sửa các setter trong khi các request khác đang so. Một chiến lược là tạo Collator theo request/thao tác hoặc tạo bản riêng cho mỗi luồng (có thể clone cấu hình gốc khi phù hợp và được kiểm thử).

**Không thay Comparator giữa lúc sort hoặc khi TreeMap đã có dữ liệu.** Comparator phải giữ quan hệ nhất quán và tính bắc cầu; nếu strength thay đổi trong khi so, các thuật toán có thể cho kết quả bất thường hoặc lỗi.

## 18. Bộ test phù hợp với Java 17+

Nên kiểm tra:

| Tình huống | Điều xác minh |
| --- | --- |
| Z và a | compareTo phụ thuộc mã UTF-16, không phải từ điển |
| file10 và file2 | Lexicographic khác natural sort |
| é dựng sẵn và e+dấu sắc | Raw equality khác canonical equivalence |
| A/a dưới Collator PRIMARY/TERTIARY | Strength thay quan hệ theo rule set |
| Tên có ă, â, đ, ê, ô, ơ, ư | Quy tắc vi-VN trong JDK mục tiêu |
| Locale.US khác vi-VN | Locale được truyền đúng, không ngầm dùng default |
| Collator decomposition | Canonical forms có chính sách rõ |
| TreeSet và TreeMap | Không làm mất key ngoài ý muốn |
| CollationKey | Chỉ so keys cùng cấu hình |
| Tie-breaker ID | Duy trì thứ tự khi các tên ngang collation |
| Tên có null, dấu câu, emoji | Có chính sách rõ |
| JDK/CLDR nâng cấp | Biết khi nào bộ quy tắc collation đổi |
| Backend và database | Toàn bộ danh sách và phân trang thống nhất |

### 18.1. Kiểm thử thuộc tính Comparator

Với comparator tự viết:

1. **Phản đối xứng về dấu:** nếu a đứng trước b thì b đứng sau a.
2. **Bắc cầu:** a trước b và b trước c thì a trước c.
3. **Nhất quán khi trả 0:** a và b được coi tương đương trong các phép so với c.
4. **Không thay đổi cấu hình giữa phép so:** cùng cặp đầu vào cho một quan hệ trong một lần sort.
5. **Tie-breaker có chủ đích:** cùng tên theo collation không làm mất thực thể riêng.
6. **Không có side effect:** comparator không tự sửa tên hoặc Locale toàn cục.

Đặc biệt khi tự tạo natural comparator, nên kiểm thử nhiều tổ hợp số dài, số 0 đầu và nhiều đoạn chữ-số; một comparator không bắc cầu có thể làm thuật toán sort lỗi khó chẩn đoán.

### 18.2. Tránh assert nguyên văn không cần thiết

Những tính chất thuần Java như **"Z".compareTo("a") == -7** là ổn định. Nhưng thứ tự một danh sách Việt ngữ dài theo Collator có thể chịu dữ liệu locale khác nhau. Hãy xác định test nào kiểm tra Java API, test nào kiểm tra rule set mà sản phẩm đã chọn.

Nếu phải chính xác từng kết quả trong CI, ghi rõ phiên bản JDK/provider, ví dụ chạy trên cùng runtime đóng gói với production.

## 19. Những sai lầm thường gặp

### Lỗi 1: Dùng Collections.sort(names) cho danh sách UI

Không truyền comparator đồng nghĩa sắp String bằng compareTo, không hề có locale collation. Đổi sang Collator theo locale nếu sản phẩm yêu cầu từ điển địa phương.

### Lỗi 2: Dùng compareToIgnoreCase rồi coi là xong

Bỏ qua case không thay thế quy tắc dấu, chữ ghép và thứ tự chữ theo ngôn ngữ. Cần Collator phù hợp.

### Lỗi 3: Dùng Collator.getInstance() không tham số trên server

Locale mặc định JVM có thể khác ngôn ngữ người dùng. Truyền locale tường minh.

### Lỗi 4: Dùng PRIMARY để định danh dữ liệu

Hai chuỗi khác nhau có thể trả compare == 0 theo một locale; không lấy comparator UI làm tiêu chuẩn uniqueness nếu không có chính sách.

### Lỗi 5: Cho rằng Collator trả 0 thì String.equals cũng true

Equality theo collation và equality UTF-16 là hai quan hệ khác nhau. TreeSet/TreeMap sẽ dựa vào comparator.

### Lỗi 6: Trộn CollationKey giữa các Locale

Keys chỉ nên được so khi cùng cấu hình Collator. Không dùng keys của hai hệ rule khác nhau để tạo thứ tự chung.

### Lỗi 7: Lưu CollationKey mãi mãi

Key có thể mất ý nghĩa khi đổi JDK/provider. Nếu persist, cần versioning và rebuild.

### Lỗi 8: Mong file2 đứng trước file10 chỉ bằng Collator

Natural/numeric ordering là yêu cầu bổ sung; phải xử lý tường minh.

### Lỗi 9: Dùng NFC như thay thế cho thứ tự từ điển

Normalizer giúp thống nhất biểu diễn Unicode, không quyết định vị trí từ điển. NFD/NFC cũng không tự bỏ dấu.

### Lỗi 10: Dùng raw compareTo để giải quyết mọi hệ chữ

Thứ tự UTF-16 không có tri thức từ điển của từng ngôn ngữ; nhất là khi nội dung có dấu, ký tự ngoài BMP, chữ từ nhiều hệ.

### Lỗi 11: Sắp riêng từng trang trong UI

Nếu server phân trang theo quy tắc khác, client sort từng trang không thể tạo thứ tự toàn cục đúng. Sắp ở tầng quyết định phân trang.

### Lỗi 12: Thay strength khi SortedSet đã được xây

Thứ tự của comparator thay đổi có thể khiến các phép tìm kiếm, thêm/xóa không còn đúng với cấu trúc hiện có. Cấu hình comparator trước khi xây tập.

### Lỗi 13: Chia sẻ Collator mutable và sửa theo request

Các request khác nhau có thể ảnh hưởng cấu hình. Tạo đối tượng riêng hoặc cách ly.

### Lỗi 14: Tưởng quy tắc Collator là bất biến qua mọi bản JDK

Dữ liệu ngôn ngữ có thể được nâng cấp. Với hợp đồng sắp xếp cố định, kiểm soát phiên bản bộ quy tắc hoặc kiểm thử kỹ thay đổi.

## 20. Checklist trước khi đưa vào sản phẩm

- [ ] Xác định nhu cầu là thứ tự kỹ thuật, locale-aware hay natural/numeric sort.
- [ ] Không mặc định String.compareTo là thứ tự từ điển của người dùng.
- [ ] Resolve Locale từ danh sách hỗ trợ, không ngầm lấy default JVM.
- [ ] Dùng Collator.getInstance(locale) khi cần sắp tên/ngôn ngữ.
- [ ] Hiểu PRIMARY, SECONDARY, TERTIARY và IDENTICAL.
- [ ] Hiểu NO_DECOMPOSITION, CANONICAL_DECOMPOSITION và FULL_DECOMPOSITION.
- [ ] Tách canonical normalization khỏi collation và search matching.
- [ ] Xác định comparator equality có phù hợp với TreeSet/TreeMap không.
- [ ] Thêm tie-breaker String hoặc ID khi muốn thứ tự toàn phần rõ ràng.
- [ ] Không so CollationKey từ cấu hình khác nhau.
- [ ] Không chia sẻ/sửa Collator mutable giữa nhiều luồng không bảo vệ.
- [ ] Kiểm thử tên tiếng Việt có đủ dấu và chữ đặc thù.
- [ ] Kiểm thử ký tự dựng sẵn và dấu kết hợp.
- [ ] Kiểm thử số trong nhãn, null, emoji, dấu câu và dữ liệu nhiều script.
- [ ] Đồng bộ quy tắc sắp giữa Java, database, backend và client khi phân trang.
- [ ] Kiểm tra JDK/provider/CLDR khi nâng cấp để phát hiện khác biệt collation.
- [ ] Giữ bản gốc và dùng ID nghiệp vụ thay vì coi displayName là khóa định danh.

## 21. Tổng kết

**String.compareTo không tương đương thứ tự từ điển địa phương** vì nó so trực tiếp những đơn vị **char UTF-16**, không xem xét ngôn ngữ, trọng số chữ cái, dấu, case hoặc truyền thống sắp xếp của từng locale. Nó phù hợp cho thứ tự kỹ thuật, nhưng không nên là lựa chọn mặc định cho danh sách tên và nhãn được người dùng đọc.

Với sắp xếp theo ngôn ngữ, sử dụng **Collator.getInstance(locale)**, chọn strength và decomposition có chủ đích, kiểm thử trên JDK/provider mục tiêu và thêm tie-breaker khi cần. **Normalizer** xử lý tương đương biểu diễn Unicode, **CollationKey** có thể giúp tối ưu so sánh lặp lại, còn **natural sorting** là bài toán khác. Thiết kế đúng phải tách thứ tự hiển thị, tìm kiếm, kiểm tra định danh và sắp xếp phục vụ phân trang.
