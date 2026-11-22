# Đếm ký tự theo char, code point và cụm hiển thị trong Java

Trong Java, câu hỏi **“chuỗi có bao nhiêu ký tự?”** không có một đáp án duy nhất nếu chưa xác định cách đếm. Một chữ Việt có dấu có thể được viết bằng một code point hoặc nhiều code point kết hợp; emoji có thể nằm ngoài vùng Unicode BMP và cần hai **UTF-16 code unit**; một hình emoji gồm nhiều thành phần có thể được nối lại thành **một cụm hiển thị**.

Bài thực hành này hướng dẫn đếm, so sánh và cắt chuỗi theo ba mức:

1. **char / UTF-16 code unit**: đơn vị mà các API như **String.length()** và **charAt()** làm việc.
2. **Unicode code point**: điểm mã Unicode, đếm bằng **codePointCount()** hoặc **codePoints()**.
3. **Cụm hiển thị (extended grapheme cluster)**: nhóm code point thường được coi là một ký tự khi người dùng di chuyển con trỏ hoặc lựa chọn văn bản; có thể phân đoạn bằng regex **\X** trong Java.

## 1. Nền tảng: char không đồng nghĩa “một ký tự nhìn thấy”

### UTF-16 code unit và String.length()

Trong Java, mỗi **char** có kích thước 16 bit và biểu diễn **một UTF-16 code unit**. **String.length()** trả về số code unit của chuỗi, chứ không phải số byte UTF-8 và cũng không luôn bằng số ký tự hiển thị.

Ví dụ:

~~~java
System.out.println("ABC".length());           // 3
System.out.println("Vi\u1EC7t".length());      // 4
System.out.println("\uD83D\uDE42".length());  // 2
~~~

Đoạn mã này là snippet để đặt trong phương thức, trong đó **Vi\u1EC7t** tương đương **Việt** và **\uD83D\uDE42** tương đương **🙂**.

Vì sao **🙂** có **length() = 2**? Unicode code point U+1F642 nằm ngoài **Basic Multilingual Plane (BMP)**; UTF-16 biểu diễn nó bằng **hai char liên tiếp**: *high surrogate* và *low surrogate*. Gọi **charAt(0)** chỉ lấy phần đầu của cặp, không phải toàn bộ emoji.

Trong các JVM hiện đại, String có thể dùng **Compact Strings** để lưu byte[] hiệu quả hơn. Điều này **không làm thay đổi** ý nghĩa của **String.length()**: API vẫn trả về số UTF-16 code unit.

### Unicode code point

**Code point** là giá trị được xác định bởi Unicode, ví dụ:

- **A**: U+0041.
- **ệ**: U+1EC7.
- **🙂**: U+1F642.
- Ký tự nối **ZWJ**: U+200D.

Một code point thuộc BMP thường ứng với một UTF-16 code unit. Một code point ngoài BMP dùng **hai** UTF-16 code unit. Do đó **codePointCount** có thể nhỏ hơn **length**.

**String.codePointCount(beginIndex, endIndex)** nhận **chỉ số code unit UTF-16**, không nhận chỉ số code point; giá trị của nó là số code point trong phạm vi UTF-16 đã chọn:

~~~java
String smile = "\uD83D\uDE42";
System.out.println(smile.length());                             // 2
System.out.println(smile.codePointCount(0, smile.length()));     // 1
System.out.println(smile.codePoints().count());                 // 1
~~~

**Lưu ý về dữ liệu không hợp lệ:** với một surrogate đơn lẻ không ghép thành cặp, Java API có thể đếm nó như một code point theo quy tắc của **codePointCount** dù nó không phải Unicode scalar value hợp lệ. Đừng mặc định mọi String bất kỳ đều chứa các cặp surrogate hợp lệ.

### Cụm hiển thị / grapheme cluster

**Extended grapheme cluster** là một đoạn gồm một hoặc nhiều code point theo quy tắc phân đoạn Unicode, thường gần với đơn vị “một ký tự” trong giao diện người dùng. Ví dụ:

- **e + dấu sắc kết hợp**: hai code point nhưng thường hiển thị thành **é** như một cụm.
- **👩‍💻**: **👩** + **ZWJ** + **💻**; ba code point nhưng thường là **một cụm emoji**.
- **🇻🇳**: hai *regional indicator* code point tạo thành một cụm cờ.
- **👍🏽**: emoji bàn tay và modifier màu da tạo thành một cụm.

**Một grapheme cluster không bắt buộc là đúng một glyph vật lý trên màn hình.** Việc hiển thị còn phụ thuộc font, shaping engine, hệ điều hành và phiên bản Unicode/emoji. Đếm cụm grapheme là một quy tắc phân đoạn văn bản, không phải phép đếm ảnh glyph mà màn hình thực sự vẽ.

## 2. Các API Java phù hợp với từng cách đếm

| Mục tiêu | API / cách làm | Đơn vị |
| --- | --- | --- |
| Đếm UTF-16 code unit | **s.length()** | char/code unit |
| Đếm code point | **s.codePointCount(0, s.length())** | code point |
| Duyệt code point | **s.codePoints()** | stream giá trị int |
| Lấy code point tại vị trí UTF-16 | **s.codePointAt(index)** | code point |
| Di chuyển n code point | **s.offsetByCodePoints(index, n)** | kết quả là chỉ số UTF-16 |
| Đếm grapheme | **Pattern.compile("\\X").matcher(s)** và đếm các lần match | extended grapheme cluster |
| Duyệt grapheme | Mỗi lần **Matcher.find()**, dùng **group()**, **start()**, **end()** | đoạn String/cặp chỉ số UTF-16 |

Trong regex của Java, **\X** biểu diễn một **Unicode extended grapheme cluster**. Vì regex nằm trong Java String literal, phải viết **"\\X"**, không phải **"\X"**; cách sau không phải escape hợp lệ của Java String.

**Matcher.results().count()** (Java 9+) hoặc vòng lặp **while (matcher.find())** đều có thể đếm số lần khớp **\X**. **Pattern** có thể dùng lại cho nhiều chuỗi; tạo một **Matcher** mới cho mỗi chuỗi cần xử lý. Không dùng chung một Matcher có trạng thái để xử lý đồng thời nhiều luồng.

## 3. Bài thực hành Java 17+ hoàn chỉnh

Lưu thành **CharacterCountingDemo.java**:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class CharacterCountingDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void report(String label, String text) {
        int codeUnits = text.length();
        int codePoints = text.codePointCount(0, codeUnits);
        long clusters = GRAPHEME.matcher(text).results().count();

        System.out.println(label + ": units=" + codeUnits
                + ", points=" + codePoints
                + ", clusters=" + clusters);
    }

    public static void main(String[] args) {
        String precomposed = "Vi\u1EC7t";
        String decomposed = "Vie\u0323\u0302t";
        String smile = "\uD83D\uDE42";
        String zwj = "\uD83D\uDC69\u200D\uD83D\uDCBB";

        report("ASCII", "ASCII");
        report("Vietnamese NFC", precomposed);
        report("Vietnamese NFD", decomposed);
        report("Emoji", smile);
        report("Emoji ZWJ", zwj);
        report("Flag", "\uD83C\uDDFB\uD83C\uDDF3");
        report("Skin tone", "\uD83D\uDC4D\uD83C\uDFFD");
        report("CRLF", "A\r\nB");
        report("Empty", "");

        System.out.println("equal before NFC: "
                + precomposed.equals(decomposed));
        System.out.println("equal after NFC: "
                + precomposed.equals(
                        Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));

        System.out.println("smile high surrogate: "
                + Character.isHighSurrogate(smile.charAt(0)));
        System.out.println("smile code point: U+"
                + Integer.toHexString(smile.codePointAt(0))
                        .toUpperCase(Locale.ROOT));

        int onePointEnd = zwj.offsetByCodePoints(0, 1);
        System.out.println("ZWJ first code point units: "
                + zwj.substring(0, onePointEnd).length());

        Matcher matcher = GRAPHEME.matcher(zwj);
        if (matcher.find()) {
            System.out.println("ZWJ first cluster units: "
                    + matcher.group().length());
        }
    }
}
~~~

Chương trình dùng **Unicode escape** để biểu diễn chính xác dữ liệu Việt và emoji, tránh phụ thuộc font/encoding của trình soạn thảo hoặc terminal. Tên các mẫu và thông báo đều dùng ASCII, nên kết quả console dễ đối chiếu.

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CharacterCountingDemo.java
java CharacterCountingDemo
~~~

Stdout mẫu đã kiểm chứng trên JDK hỗ trợ quy tắc grapheme cho các trường hợp đã chọn:

~~~text
ASCII: units=5, points=5, clusters=5
Vietnamese NFC: units=4, points=4, clusters=4
Vietnamese NFD: units=6, points=6, clusters=4
Emoji: units=2, points=1, clusters=1
Emoji ZWJ: units=5, points=3, clusters=1
Flag: units=4, points=2, clusters=1
Skin tone: units=4, points=2, clusters=1
CRLF: units=4, points=4, clusters=3
Empty: units=0, points=0, clusters=0
equal before NFC: false
equal after NFC: true
smile high surrogate: true
smile code point: U+1F642
ZWJ first code point units: 2
ZWJ first cluster units: 5
~~~

Ý nghĩa ba cột:

- **units** = số UTF-16 code unit, cũng là **String.length()**.
- **points** = số code point theo Java API.
- **clusters** = số lần regex **\X** khớp, theo triển khai quy tắc Unicode của JDK đang chạy.

Kết quả phụ thuộc bảng Unicode của JDK với các cụm Unicode/emoji mới; các ví dụ phổ biến trên đã được kiểm chứng trong môi trường Java kiểm tra. Khi áp dụng cho bộ emoji mới hoặc bản JDK khác, hãy chạy lại để xác nhận sự tương thích.

## 4. Phân tích từng trường hợp trong bảng

### 4.1. ASCII: ba đại lượng bằng nhau

**"ASCII"** gồm năm ký tự A, S, C, I, I. Mỗi ký tự chiếm một UTF-16 code unit, là một code point và tự tạo một grapheme cluster.

Vì vậy: **units=5, points=5, clusters=5**.

Trường hợp này thường làm lập trình viên tưởng rằng **length() luôn là số ký tự**, vì ở dữ liệu ASCII đơn giản ba kết quả trùng nhau. Kết luận ấy không còn đúng với Unicode tổng quát.

### 4.2. Tiếng Việt dạng dựng sẵn: đa số vẫn dùng một unit

**"Việt"** với chữ **ệ** dựng sẵn (U+1EC7) có bốn chữ và bốn code point, đều nằm trong BMP; mỗi code point dùng một UTF-16 unit. Trong phép phân đoạn đã chọn, mỗi chữ là một grapheme cluster.

Kết quả: **units=4, points=4, clusters=4**.

**Không suy ra** từ đây rằng mọi văn bản tiếng Việt luôn có ba đại lượng bằng nhau. Cùng một chữ mang dấu có thể được viết bằng nhiều code point tổ hợp, như ví dụ sau.

### 4.3. Tiếng Việt dạng phân rã: nhiều code point cho một chữ

Chuỗi **Việt** được khai báo bằng:

~~~java
String decomposed = "Vie\u0323\u0302t";
~~~

Nó có sáu code point: **V**, **i**, **e**, dấu chấm dưới, dấu mũ và **t**. Dấu chấm dưới và dấu mũ kết hợp với chữ e, nên bộ phân đoạn grapheme tạo ra bốn cụm.

- **units=6** vì cả sáu code point đều nằm trong BMP.
- **points=6** vì không có surrogate pair.
- **clusters=4** vì e cùng hai dấu tạo **một cụm**, không phải ba cụm riêng.

Trong cùng chương trình:

~~~java
String composed = "Vi\u1EC7t";
String decomposed = "Vie\u0323\u0302t";
System.out.println(composed.equals(decomposed)); // false
System.out.println(
        composed.equals(Normalizer.normalize(
                decomposed, Normalizer.Form.NFC))); // true
~~~

Đây là snippet để đặt trong phương thức và import **java.text.Normalizer**. Java String.equals so sánh nội dung mã hóa thực tế, nên trước chuẩn hóa hai chuỗi không bằng nhau; chuẩn hóa NFC chuyển dạng tổ hợp về dạng tương đương khi có dạng dựng sẵn thích hợp.

**Grapheme count bằng nhau không kéo theo equals bằng nhau.** Nếu yêu cầu nghiệp vụ coi các dạng chuẩn hóa Unicode tương đương là cùng dữ liệu, cần chuẩn hóa trước khi so sánh hoặc làm khóa collection.

### 4.4. Emoji đơn: hai char nhưng một code point

Với **🙂** (U+1F642):

- **units=2**: surrogate pair gồm hai UTF-16 unit.
- **points=1**: một code point.
- **clusters=1**: một grapheme cluster.

**smile.charAt(0)** trả về high surrogate; **smile.codePointAt(0)** trả về U+1F642. Với chuỗi hợp lệ và ở vị trí đúng, codePointAt kết hợp hai char của surrogate pair để cho code point hoàn chỉnh.

### 4.5. Emoji ZWJ: nhiều code point thành một cụm

Chuỗi **👩‍💻** gồm:

1. **👩**: U+1F469, hai UTF-16 unit.
2. **ZWJ**: U+200D, một UTF-16 unit.
3. **💻**: U+1F4BB, hai UTF-16 unit.

Tổng cộng **5 unit, 3 point, 1 cluster**.

Đây là ví dụ cho thấy **đếm theo code point** vẫn không đủ khi yêu cầu là “một ký tự người dùng nhìn thấy”. Nếu chỉ lấy code point đầu tiên, ta lấy **👩**, không lấy toàn cụm **👩‍💻**.

### 4.6. Cờ và emoji có màu da

**🇻🇳** gồm hai regional indicator code point ngoài BMP, nên **4 UTF-16 unit**, **2 code point**, thường là **1 grapheme cluster**.

**👍🏽** gồm emoji bàn tay và emoji modifier màu da, nên **4 unit**, **2 point** và **1 cluster** trong trường hợp này.

Không phải mọi emoji đều có cùng cách cấu thành. Có emoji một code point, emoji có variation selector, modifier, cờ, chuỗi ZWJ và chuỗi dài hơn. Không thể suy “một emoji = hai char” hoặc “một emoji = một code point”.

### 4.7. Xuống dòng CRLF và chuỗi rỗng

**"A\r\nB"** gồm A, CR, LF, B:

- **length() = 4**.
- **codePointCount() = 4**.
- **\X** nhóm CRLF thành **một grapheme cluster** theo quy tắc phân đoạn, nên tổng cộng **3** cụm: A, CRLF, B.

CRLF không phải một biểu tượng hiển thị, minh họa rằng **grapheme cluster là đơn vị phân đoạn văn bản**, không bắt buộc mỗi cụm tương ứng một hình glyph nhìn thấy.

Chuỗi rỗng có **0** unit, **0** code point và **0** grapheme cluster. Không nên gọi **charAt(0)** trên chuỗi rỗng.

## 5. Không cắt chuỗi giữa surrogate pair

Sai lầm điển hình khi xử lý emoji:

~~~java
String smile = "\uD83D\uDE42";
String broken = smile.substring(0, 1);
~~~

**broken** chỉ gồm high surrogate, là một mảnh không hoàn chỉnh của emoji. Khi mã hóa ra UTF-8, API có thể dùng replacement để biểu diễn mã không hợp lệ; không nên kỳ vọng có thể tạo lại emoji ban đầu.

Nếu yêu cầu là **lấy n code point**, dùng **offsetByCodePoints** để chuyển từ số code point sang chỉ số UTF-16:

~~~java
String smile = "\uD83D\uDE42";
int end = smile.offsetByCodePoints(0, 1);
String firstPoint = smile.substring(0, end);

// end == 2; firstPoint chứa toàn bộ 🙂.
~~~

**substring** vẫn nhận offset UTF-16; **offsetByCodePoints** chỉ giúp tính đúng vị trí kết thúc theo code point. Đoạn này tránh cắt surrogate pair hợp lệ, nhưng vẫn có thể cắt một grapheme có nhiều code point.

Ví dụ với **👩‍💻**, lấy một code point đầu tiên chỉ nhận emoji **👩** (2 UTF-16 unit), bỏ lại ZWJ và emoji 💻.

## 6. Cắt chuỗi theo grapheme cluster

Nếu yêu cầu là **lấy một cụm grapheme đầu tiên**, có thể dùng **Matcher.find()**:

~~~java
Pattern grapheme = Pattern.compile("\\X");
String value = "\uD83D\uDC69\u200D\uD83D\uDCBB";

Matcher matcher = grapheme.matcher(value);
if (matcher.find()) {
    String firstCluster = matcher.group();
    int begin = matcher.start();
    int end = matcher.end();

    // firstCluster là toàn bộ chuỗi 👩‍💻 trong trường hợp này.
    // begin == 0, end == 5 (offset UTF-16).
}
~~~

Đây là snippet, cần import **java.util.regex.Pattern**, **Matcher** và đặt trong phương thức.

**Matcher.start()**, **end()** cũng trả về **chỉ số UTF-16**, không phải số code point. Nhờ vậy có thể truyền các chỉ số đó trực tiếp cho **substring** để lấy toàn bộ cụm theo phép phân đoạn.

Muốn lấy tối đa **n cụm đầu**, dùng vòng lặp đếm các lần find, nhận **end()** của cụm thứ n rồi cắt ở vị trí đó. Với đầu vào rỗng, xử lý riêng để không giả định Matcher tìm được cụm đầu.

Một hàm tiện ích (snipppet cần đặt trong lớp):

~~~java
static String takeClusters(String text, int limit) {
    if (limit < 0) {
        throw new IllegalArgumentException("limit must be >= 0");
    }
    if (limit == 0 || text.isEmpty()) {
        return "";
    }

    Matcher matcher = Pattern.compile("\\X").matcher(text);
    int end = 0;
    int taken = 0;

    while (taken < limit && matcher.find()) {
        end = matcher.end();
        taken++;
    }
    return text.substring(0, end);
}
~~~

Nếu có ít hơn **limit** cụm, vòng lặp chạy đến hết và trả về cả chuỗi. Với ứng dụng gọi thường xuyên, nên tái sử dụng **Pattern** thay vì compile mỗi lần.

**Giới hạn quan trọng:** cụm grapheme theo quy tắc Unicode/phiên bản JDK không đồng nghĩa chắc chắn với một glyph được render bằng font thực tế. Đây vẫn là cách cắt văn bản phù hợp hơn nhiều so với substring theo char khi cần tránh chia các thành phần của một grapheme.

## 7. String.length, codePointCount và grapheme count phục vụ bài toán nào?

| Bài toán | Cách đếm nên ưu tiên | Lý do |
| --- | --- | --- |
| API Java cần chỉ số char của substring/charAt | UTF-16 unit | Phần lớn index String sử dụng UTF-16 offset |
| Ghi log chỉ số **char** hoặc phân tích mã UTF-16 | **length()** | Đúng đơn vị của dữ liệu đang khảo sát |
| Duyệt Unicode scalar/code point của văn bản hợp lệ | **codePoints()** / **codePointCount()** | Không tách surrogate pair hợp lệ |
| UI giới hạn ký tự người dùng cảm nhận | Grapheme cluster | Dấu kết hợp/emoji ZWJ cần được tính chung thành cụm |
| Cắt một chuỗi emoji ZWJ còn nguyên cụm | Matcher regex **\X** | Tránh chia giữa các thành phần của cụm |
| Giới hạn kích thước HTTP/file UTF-8 | **getBytes(UTF_8).length** | Byte mã hóa không bằng ba loại “ký tự” ở trên |
| So sánh hai cách viết chữ có dấu | Chuẩn hóa Unicode rồi so nội dung | Đếm bằng nhau chưa có nghĩa chuỗi bằng nhau |
| Vẽ glyph trên UI | Hệ thống shaping/rendering | Một grapheme có thể được vẽ bằng nhiều glyph và phụ thuộc font |

Không có API nào trong ba phép đếm tự giải quyết mọi bài toán Unicode. Phải lựa chọn đơn vị khớp với yêu cầu dữ liệu hoặc giao diện.

## 8. Vấn đề phiên bản Unicode và Java BreakIterator

**Pattern "\\X"** là giải pháp có sẵn trong Java regex cho **extended grapheme cluster**. Nó tránh phụ thuộc thư viện ngoài trong nhiều bài thực hành và làm việc với các ví dụ Unicode phổ biến của bài.

Tuy nhiên, bảng quy tắc Unicode/emoji do JDK triển khai có thể khác nhau theo phiên bản. Các chuỗi emoji mới, chuỗi kết hợp phức tạp và trình tự ZWJ mới cần được kiểm tra lại trên JDK của sản phẩm. Không dựa vào số cụm cứng của một ví dụ rồi cho rằng mọi JDK đều phân đoạn mọi emoji giống hệt.

**BreakIterator.getCharacterInstance()** cũng cung cấp cơ chế phân đoạn ký tự, nhưng không nên mặc định kết quả của nó trên mọi phiên bản JDK/locale đều bằng **Pattern "\\X"** hoặc luôn xử lý đúng mọi chuỗi emoji ZWJ. Với hệ thống cần tương thích Unicode UAX #29 nghiêm ngặt hoặc tập emoji mới, có thể dùng công cụ/thư viện phân đoạn grapheme phù hợp như ICU4J và kiểm thử trên bộ dữ liệu mục tiêu.

Cũng không nhầm việc **có một cụm** với việc *người dùng chắc chắn nhìn thấy một hình*. Hỗ trợ font và bộ dựng chữ có thể khác nhau giữa trình duyệt/hệ điều hành.

## 9. Hiệu năng của ba phép đếm

**String.length()** trả trực tiếp số UTF-16 unit đã được biểu diễn trong String; đây là phép lấy độ dài, thường có chi phí hằng số.

**codePointCount()** phải xét nội dung để nhận diện surrogate pair trong phạm vi được yêu cầu; chi phí phụ thuộc số UTF-16 unit đang duyệt.

**Đếm grapheme bằng regex \X** phải chạy bộ máy phân đoạn trên chuỗi; nhìn chung tốn công hơn chỉ đọc độ dài. Nếu thao tác nhiều lần với cùng văn bản, hãy cân nhắc lưu kết quả đếm hoặc chỉ số cụm khi dữ liệu bất biến, thay vì tính lại sau từng lần render.

Không so sánh một phép **length()** với một phép **Matcher.find()** duy nhất rồi kết luận chắc chắn về thời gian của ứng dụng. Muốn benchmark các phương pháp trên dữ liệu lớn:

1. Chuẩn bị đầu vào ASCII, tiếng Việt dựng sẵn, dấu tổ hợp, emoji đơn, emoji ZWJ với cỡ mẫu và tỷ lệ xác định.
2. Ghi rõ so sánh theo số **UTF-16 unit**, **code point** hay **grapheme** tương đương.
3. Dùng JMH với warm-up, nhiều fork và sử dụng kết quả (Blackhole) để tránh JIT loại bỏ công việc.
4. Ghi phiên bản Java, Unicode, cấu hình JVM, kích thước chuỗi, đơn vị ns/op hoặc ops/s.
5. Đo thêm allocation nếu vòng lặp tạo Matcher/stream liên tục là vấn đề của ứng dụng.

**Dùng Pattern tái sử dụng** khi đếm nhiều chuỗi bằng cùng regex. Pattern có thể chia sẻ giữa các thread; Matcher cần tạo riêng cho từng thao tác vì giữ trạng thái khi find.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| **"🙂".length() là 1** | Emoji ngoài BMP cần hai code unit | Kiểm tra **length=2**, **codePointCount=1** |
| **substring(0, 1) luôn lấy ký tự đầu tiên** | Có thể cắt giữa surrogate pair | Dùng offsetByCodePoints hoặc cắt theo grapheme |
| **Một code point luôn là một chữ hiển thị** | Dấu kết hợp và emoji ZWJ có thể ghép nhiều điểm mã | Phân đoạn grapheme với **\X** |
| **codePointCount(0, n)** với n là số code point | Các chỉ số đầu/cuối là UTF-16 offset | Dùng **s.length()** làm cận cuối khi đếm cả chuỗi |
| **"\\X"** bị gõ thành **"\X"** | Java String cần escape dấu gạch chéo ngược | Viết **"\\X"** trong mã nguồn Java |
| Chuỗi tiếng Việt nhìn giống mà **equals=false** | Dạng Unicode dựng sẵn/phân rã | Chuẩn hóa NFC khi yêu cầu nghiệp vụ |
| Đếm grapheme coi CRLF là hai chữ hiển thị | CRLF được phân đoạn thành một cụm dù không phải glyph | Hiểu grapheme là đơn vị phân đoạn, không phải hình |
| Đếm theo grapheme rồi dùng số cụm làm offset substring | substring dùng UTF-16 offset | Lấy **Matcher.start()/end()** hoặc chuyển đổi offset đúng |
| Số cụm của emoji mới thay đổi giữa JDK | Phiên bản dữ liệu Unicode/quy tắc phân đoạn khác nhau | Kiểm thử các mẫu emoji cụ thể trên JDK dùng thực tế |
| Dùng length để giới hạn byte upload | byte UTF-8 khác số UTF-16 unit | Đo **getBytes(UTF_8).length** |

## 11. Bài tập củng cố

**Bài 1: Phân biệt đơn vị**

Dự đoán ba phép đếm cho chuỗi **"A🙂B"**: **String.length()**, **codePointCount()** và regex **\X**. Đáp án: **4 UTF-16 unit**, **3 code point**, **3 grapheme cluster** (A, 🙂, B). Nếu gọi **substring(0, 2)**, kết quả chứa A và nửa đầu surrogate của emoji, không hợp lệ để coi là chuỗi hai ký tự đầy đủ.

**Bài 2: Dấu kết hợp**

Với **"a\u0301"** (a rồi dấu sắc kết hợp), số unit là **2**, code point là **2** nhưng số grapheme cluster là **1**. Thử so sánh với chữ **á** U+00E1 bằng equals trước và sau **Normalizer.Form.NFC**.

**Bài 3: Lấy cụm đầu của emoji nối**

Với **"👩‍💻"**, **offsetByCodePoints(0, 1)** trả chỉ số kết thúc sau code point đầu là **2** UTF-16 unit; trong khi một lần match **\X** cho cụm đầu dài **5** UTF-16 unit. Giải thích vì sao hai cách cắt phục vụ hai yêu cầu khác nhau.

**Bài 4: Thử dữ liệu thật**

Tạo các chuỗi gồm tiếng Việt NFC/NFD, cờ, emoji có modifier, emoji ZWJ và CRLF. Chạy chương trình ở phần 3, rồi thêm một dòng **report** cho mỗi chuỗi. Ghi lại phiên bản JDK, ba số đếm và nhận xét trường hợp số đơn vị khác nhau.

**Bài 5: Giới hạn 10 ký tự giao diện**

Viết chức năng kiểm tra đầu vào theo tối đa **10 grapheme cluster** thay vì **10 char**; sử dụng Matcher regex **\X** như phần 6. Kiểm thử ít nhất một chuỗi emoji ZWJ để tránh cắt dở cụm.

## 12. Tổng kết kiến thức

Khi xử lý Unicode trong Java, hãy luôn hỏi **đang đếm đơn vị nào?**

- **String.length()** đếm UTF-16 code unit, phù hợp với mô hình chỉ số String.
- **codePointCount()** đếm Unicode code point, tránh coi surrogate pair hợp lệ là hai điểm mã.
- **Pattern "\\X"** đếm extended grapheme cluster, thường phù hợp hơn khi làm việc với ký tự người dùng cảm nhận, nhất là tiếng Việt có dấu tổ hợp và emoji ZWJ.

Một văn bản nhìn như **một** emoji có thể cần **nhiều char và nhiều code point**. Lựa chọn đúng đơn vị để đếm, để cắt và để kiểm thử mới tránh lỗi làm hỏng dữ liệu Unicode.
