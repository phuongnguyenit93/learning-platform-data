# Quan hệ giữa byte, `char` UTF-16, code point và ký tự hiển thị

> **Phạm vi:** Java Core – I/O → Mã hóa văn bản. Bài học giải thích vì sao “một ký tự” không luôn tương ứng với một `byte`, một Java `char` hoặc một Unicode code point; cách đọc, ghi, đếm, cắt và hiển thị văn bản đúng trong Java. Ví dụ dùng Java 17 trừ khi có ghi phiên bản khác.

## 1. Bốn tầng dữ liệu cần phân biệt

Khi lưu một tên người hoặc một biểu tượng cảm xúc vào tệp, hệ thống đi qua nhiều cách biểu diễn khác nhau:

`Văn bản người dùng nhìn thấy → cụm grapheme → dãy Unicode code point → dãy UTF-16 code unit trong API String/char → byte[] theo charset khi mã hóa ra I/O.`

Chiều đọc tệp diễn ra theo hướng ngược lại: **byte** cần được **giải mã** bằng một charset để tạo chuỗi ký tự. Không thể suy ra byte có nghĩa gì nếu thiếu thông tin mã hóa.

| Tầng | Đơn vị đo | Biểu diễn trong Java | Điều cần nhớ |
| --- | --- | --- | --- |
| **Byte** | 8 bit, giá trị bit 0–255 | `byte`/`byte[]`, `InputStream`, `ByteBuffer` | Java `byte` có giá trị signed -128…127, nhưng mẫu bit của nó vẫn là 8 bit. Số byte phụ thuộc charset. |
| **UTF-16 code unit** | 16 bit | Một phần tử `char`; `String.length()` đếm số code unit | Một code point ngoài BMP dùng **hai** `char` (surrogate pair). |
| **Unicode code point** | Giá trị `U+0000`…`U+10FFFF` | Thường dùng `int`, `String.codePoints()`, `codePointAt` | Đơn vị nhận dạng mã Unicode; một “ký tự nhìn thấy” vẫn có thể gồm **nhiều** code point. |
| **Grapheme cluster** (cụm ký tự mở rộng) | Một đơn vị văn bản mà người dùng thường coi là “một ký tự” khi chọn/xóa | Không có kiểu dữ liệu nguyên thủy tương ứng; có thể phân đoạn bằng regex `\X` từ Java 9 | Một cụm có thể gồm chữ + dấu tổ hợp, emoji + bộ đổi kiểu, emoji + ZWJ hoặc cặp regional indicator. |
| **Glyph / hình vẽ** | Hình do font và bộ dựng chữ tạo ra | Thuộc trình render UI, không phải một kiểu `String` | Số glyph, số ô hiển thị và số grapheme **không nhất thiết bằng nhau**. |

**Từ ngữ chính xác:** trong phần đặc tả Java, `char` là một **UTF-16 code unit**, không bảo đảm là một “ký tự Unicode hoàn chỉnh”. `String` cung cấp API và chỉ số theo UTF-16 code unit, dù Java runtime hiện đại có thể tối ưu lưu trữ nội bộ bằng cơ chế khác (ví dụ compact strings). Đừng suy ra bố cục byte trong bộ nhớ chỉ từ `String.length()`.

### Byte khác ký tự thế nào?

- `A` là code point **U+0041**. UTF-8 lưu thành **1 byte** `41`; UTF-16 cần **1 code unit** `0041`.
- `é` dạng ghép sẵn là **U+00E9**. UTF-8 lưu thành **2 byte** `C3 A9`; UTF-16 cần **1 code unit** `00E9`.
- `🙂` là **U+1F642**, ngoài BMP. UTF-8 lưu thành **4 byte** `F0 9F 99 82`; UTF-16 dùng hai code unit `D83D DE42` nhưng chỉ **1 code point** và thông thường **1 grapheme cluster**.
- `é` dạng chữ `e` cộng dấu kết hợp là **U+0065 U+0301**. UTF-8 gồm **3 byte** `65 CC 81`, UTF-16 gồm **2 code unit**, có **2 code point**, nhưng người đọc thường nhìn như **1 grapheme cluster** (trông giống `é`).
- Emoji **👩‍💻** thường là dãy `U+1F469` (người phụ nữ), `U+200D` (zero-width joiner), `U+1F4BB` (máy tính). Dãy này gồm **11 byte UTF-8**, **5 UTF-16 code unit**, **3 code point**, thường là **1 extended grapheme cluster**; font hoặc phần mềm không hỗ trợ có thể vẽ nó thành nhiều hình.

Hai từ “ký tự” và “độ dài” sẽ dễ gây nhầm nếu không ghi rõ đang đo **bytes**, **code units**, **code points** hay **grapheme clusters**.

## 2. UTF-8 và UTF-16 nằm ở hai bước khác nhau

**Unicode** định nghĩa hệ thống code point và các quy tắc xử lý văn bản. **UTF-8** và **UTF-16** là các cách biến code point thành đơn vị mã hóa (code unit). Một **charset** còn bao gồm các quy tắc encode/decode tương ứng. Code point không đồng nghĩa với byte.

- **UTF-8:** một Unicode scalar value được mã hóa thành **1–4 byte**. ASCII U+0000…U+007F dùng 1 byte. Những ký tự ngoài ASCII có thể chiếm 2, 3 hoặc 4 byte. UTF-8 có độ dài thay đổi nhưng không phụ thuộc thứ tự byte kiểu UTF-16.
- **UTF-16:** một Unicode scalar value thuộc BMP và không phải surrogate cần **1 code unit 16 bit**; code point `U+10000`…`U+10FFFF` cần **2 code unit** tạo thành surrogate pair. Khi ghi UTF-16 ra tệp, mỗi code unit lại phải được đưa thành **byte** theo thứ tự byte thích hợp, ví dụ UTF-16BE hoặc UTF-16LE.
- **Java `String` và `char`:** xét về ngữ nghĩa API, chỉ số của `String` theo UTF-16 code unit. Nhưng khi đọc/ghi tệp UTF-8, Java encode/decode giữa các đơn vị này và dãy byte; không có nghĩa tệp phải lưu UTF-16.
- **BOM:** một số tệp UTF-16 có byte-order mark giúp nhận biết endian; UTF-8 không cần BOM để xác định thứ tự byte. Đừng tự bỏ/giữ BOM vô điều kiện: hãy bám vào hợp đồng định dạng dữ liệu.
- Một `byte` trong Java là signed; khi in hex dùng `b & 0xFF` để nhận giá trị unsigned 0–255. Không dùng `String.length()` làm kích thước byte mà một payload UTF-8 sẽ chiếm.

### 2.1. Chuyển đổi byte và chuỗi luôn cần charset

~~~java
import java.nio.charset.StandardCharsets;

// Ví dụ fragment: dữ liệu đầu vào hợp lệ theo UTF-8.
String text = "Tiếng Việt 🙂";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);       // Encode
String restored = new String(bytes, StandardCharsets.UTF_8); // Decode
boolean equal = text.equals(restored);                      // true
~~~

Đây là **fragment** nhằm trình bày bước chuyển đổi; `StandardCharsets.UTF_8` giúp kết quả không phụ thuộc charset mặc định của máy. Với payload đến từ mạng, database hoặc tệp cũ, **không thể mặc định byte luôn là UTF-8**; cần biết contract thực tế. Từ JDK 18, JEP 400 quy định UTF-8 là default charset cho các Java SE API chịu tác động, nhưng thay đổi này không tự chuyển đổi tệp legacy.

Với dữ liệu UTF-8 hợp lệ, encode rồi decode cùng charset sẽ giữ nội dung. Nếu mảng byte không đúng encoding, constructor `new String(bytes, UTF_8)` có thể thay chuỗi byte lỗi bằng ký tự thay thế; khi cần kiểm tra nghiêm ngặt, dùng `CharsetDecoder` và cấu hình lỗi dạng `CodingErrorAction.REPORT`.

## 3. `char` và surrogate pair trong Java

Kiểu `char` chứa **16 bit**. Unicode từng có thể biểu diễn các mã thông dụng trong một đơn vị 16 bit, nhưng ngày nay nhiều code point ngoài **Basic Multilingual Plane (BMP, U+0000…U+FFFF)**. UTF-16 biểu diễn code point bổ sung bằng hai `char`:

- **High surrogate:** từ `U+D800` tới `U+DBFF`.
- **Low surrogate:** từ `U+DC00` tới `U+DFFF`.
- Một high surrogate theo ngay sau bởi low surrogate hợp lệ đại diện cho một code point từ `U+10000` tới `U+10FFFF`.

Ví dụ:

~~~text
Emoji 🙂 = U+1F642
UTF-16 high surrogate = 0xD83D
UTF-16 low surrogate  = 0xDE42
"🙂".length()          = 2
"🙂".codePointCount(0, 2) = 1
~~~

**Chú ý về Unicode scalar value:** tổng không gian code point là `U+0000`…`U+10FFFF`, nhưng **U+D800…U+DFFF** được dành riêng cho surrogate và **không phải** Unicode scalar value hợp lệ để mã hóa trực tiếp bằng UTF-8. Một `String` vẫn có thể chứa surrogate lẻ do thao tác cắt hoặc nguồn dữ liệu bất thường. Khi ấy `codePoints()`/`codePointCount()` xử lý các surrogate lẻ theo hợp đồng API, **không chứng minh chuỗi là Unicode scalar sequence hợp lệ**.

Các API nên nhớ:

| API | Đơn vị trả về / thao tác |
| --- | --- |
| `s.length()` | Số **UTF-16 code unit** trong chuỗi |
| `s.charAt(i)` | Một `char` tại **chỉ số UTF-16**, có thể chỉ là một nửa surrogate pair |
| `s.codePointAt(i)` | Code point tại vị trí UTF-16 `i` nếu gặp cặp surrogate hợp lệ; trả giá trị đơn vị đơn nếu lẻ |
| `s.codePointCount(begin, end)` | Số code point trong khoảng **chỉ số UTF-16**, gồm cả surrogate lẻ được tính riêng |
| `s.codePoints()` | `IntStream` dãy code point; surrogate pair hợp lệ được gộp |
| `s.chars()` | `IntStream` dãy giá trị **char code unit**; không gộp cặp surrogate |
| `s.offsetByCodePoints(index, count)` | Dịch một vị trí UTF-16 theo số **code point**, trả về vị trí UTF-16 |
| `Character.charCount(cp)` | Số UTF-16 code unit để biểu diễn code point (1 hoặc 2) |
| `Character.toChars(cp)` / `StringBuilder.appendCodePoint(cp)` | Chuyển code point thành một hoặc hai code unit để đưa vào chuỗi |

**Cảnh báo quan trọng:** các chỉ số của `substring(begin,end)`, `charAt(i)`, `indexOf`/`lastIndexOf` và phần lớn API xử lý vị trí `String` đều là **vị trí UTF-16**. Nếu bạn lấy `substring(0, 1)` của chuỗi bắt đầu bằng emoji ngoài BMP, có thể cắt mất một nửa surrogate pair.

### 3.1. Duyệt code point đúng cách

~~~java
// Fragment: 's' là một String Java đã được khởi tạo.
for (int i = 0; i < s.length(); ) {
    int cp = s.codePointAt(i);
    // Xử lý cp ở đây, ví dụ Character.isLetter(cp).
    i += Character.charCount(cp);
}
~~~

Đoạn trên tiến theo **code point**, không theo grapheme. Với chuỗi tiếng Việt chứa combining marks, một lần lặp có thể nhận chữ cơ sở và lần tiếp theo nhận dấu tổ hợp; với emoji ZWJ, nó gặp nhiều code point dù người dùng thấy một emoji ghép.

## 4. Một “ký tự hiển thị” có thể gồm nhiều code point

Các phần mềm xử lý text thường dùng **extended grapheme cluster** theo Unicode Text Segmentation (UAX #29) làm gần đúng đơn vị người dùng nhận biết. Ví dụ quan trọng:

| Dữ liệu | Dãy code point | Số code point | Grapheme thường thấy |
| --- | --- | --- | --- |
| `A` | `U+0041` | 1 | 1 |
| `é` ghép sẵn | `U+00E9` | 1 | 1 |
| `é` phân rã | `U+0065 U+0301` | 2 | 1 |
| `🙂` | `U+1F642` | 1 | 1 |
| `🇻🇳` | `U+1F1FB U+1F1F3` (regional indicators) | 2 | 1 |
| `👩‍💻` | `U+1F469 U+200D U+1F4BB` | 3 | 1 |

Các quy tắc kết hợp phụ thuộc **phiên bản Unicode** và thư viện phân đoạn; thêm emoji mới có thể đổi kết quả theo phiên bản runtime. Trình render còn phụ thuộc font, hệ điều hành, thư viện định hình chữ và ngôn ngữ. Một grapheme không bảo đảm là **một glyph**, một pixel width hay một ô monospace.

### 4.1. Java regex `\X` cho extended grapheme cluster

Từ **Java 9**, `java.util.regex.Pattern` hỗ trợ `\X` (khớp một extended grapheme cluster) và `\b{g}` (biên cụm grapheme). Trong Java string literal, dấu backslash cần được escape: viết `"\\X"` để regex nhận ký hiệu `\X`.

~~~java
// Fragment dành cho Java 9+.
java.util.regex.Matcher m =
    java.util.regex.Pattern.compile("\\X").matcher(text);
int graphemes = 0;
while (m.find()) {
    graphemes++;
}
~~~

`text` là chuỗi cần đếm. Với Java 8, **không dựa vào `\X`** vì tài liệu regex Java 8 không có cú pháp đó. Nếu ứng dụng yêu cầu phân đoạn grapheme đúng theo một phiên bản Unicode cụ thể trên nhiều JDK, cần kiểm tra phiên bản thuật toán, thử dữ liệu thực tế, và cân nhắc thư viện Unicode chuyên biệt như ICU4J theo yêu cầu dự án.

### 4.2. `BreakIterator` có phải là `\X` không?

`java.text.BreakIterator.getCharacterInstance(locale)` có thể tìm ranh giới ký tự cho tác vụ giao diện, nhưng **không nên mặc định** kết quả giống hoàn toàn quy tắc **extended grapheme cluster** của regex `\X` ở mọi phiên bản JDK/locale, nhất là emoji ghép bằng ZWJ. Nếu yêu cầu kỹ thuật là Unicode UAX #29 cụ thể, hãy **kiểm thử** ranh giới với chuỗi mẫu và môi trường triển khai.

## 5. Ví dụ chạy độc lập: đếm cả bốn tầng

Lưu là **`UnicodeLayers.java`** (mã chạy với Java 17, sử dụng `\X` vốn có từ Java 9):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeLayers {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static int graphemeCount(String value) {
        Matcher matcher = GRAPHEME.matcher(value);
        int count = 0;
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    private static void inspect(String label, String value) {
        int bytes = value.getBytes(StandardCharsets.UTF_8).length;
        int chars = value.length();
        int codePoints = value.codePointCount(0, chars);
        int graphemes = graphemeCount(value);
        System.out.printf(
            "%s: bytes=%d, chars=%d, codePoints=%d, graphemes=%d%n",
            label, bytes, chars, codePoints, graphemes
        );
    }

    public static void main(String[] args) {
        inspect("A", "A");
        inspect("e-composed", "\u00E9");
        inspect("e-decomposed", "e\u0301");
        inspect("smile", "\uD83D\uDE42");
        inspect("woman-technologist", "\uD83D\uDC69\u200D\uD83D\uDCBB");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 UnicodeLayers.java
java UnicodeLayers
~~~

**Stdout đã kiểm tra:**

~~~text
A: bytes=1, chars=1, codePoints=1, graphemes=1
e-composed: bytes=2, chars=1, codePoints=1, graphemes=1
e-decomposed: bytes=3, chars=2, codePoints=2, graphemes=1
smile: bytes=4, chars=2, codePoints=1, graphemes=1
woman-technologist: bytes=11, chars=5, codePoints=3, graphemes=1
~~~

Điều cần quan sát:

1. `e-composed` và `e-decomposed` thường trông giống nhau nhưng có **số byte, số code unit, số code point khác nhau**.
2. `smile` chỉ có **1 code point** nhưng `String.length() == 2` vì surrogate pair.
3. `woman-technologist` là **một cụm grapheme mở rộng** nhưng gồm nhiều code point do ZWJ kết hợp.
4. Các con số byte được đo theo **UTF-8** đã chỉ định; mã hóa tệp ra UTF-16 sẽ cho số byte khác. Các con số grapheme là kết quả của thuật toán phân đoạn Java đang chạy, không phải đo “số hình vẽ” trên màn hình.

## 6. Ví dụ chạy độc lập: vì sao `charAt`/`substring` dễ cắt sai

Lưu là **`UnicodeIndex.java`**:

~~~java
public class UnicodeIndex {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE42B"; // A + 🙂 + B

        System.out.println("utf16=" + text.length());
        System.out.println("codePoints="
            + text.codePointCount(0, text.length()));
        System.out.printf("charAt(1)=U+%04X%n", (int) text.charAt(1));
        System.out.printf("codePointAt(1)=U+%04X%n", text.codePointAt(1));

        int afterTwoPoints = text.offsetByCodePoints(0, 2);
        System.out.println("indexAfterTwoCodePoints=" + afterTwoPoints);
        System.out.println("middle=" + text.substring(1, afterTwoPoints));
        System.out.println("splitSurrogate="
            + Character.isHighSurrogate(text.substring(1, 2).charAt(0)));
    }
}
~~~

~~~bash
javac --release 17 UnicodeIndex.java
java UnicodeIndex
~~~

Stdout:

~~~text
utf16=4
codePoints=3
charAt(1)=U+D83D
codePointAt(1)=U+1F642
indexAfterTwoCodePoints=3
middle=🙂
splitSurrogate=true
~~~

Chuỗi có bốn vị trí UTF-16: vị trí 0 là `A`, vị trí 1–2 là high/low surrogate của `🙂`, vị trí 3 là `B`. `substring(1,2)` chỉ chứa **một high surrogate lẻ**; nó **không phải** ký tự emoji hoàn chỉnh. `offsetByCodePoints(0,2)` trả **chỉ số UTF-16 bằng 3**, không phải “giá trị code point thứ hai”.

Đây là cách xử lý **ranh giới code point**, vẫn chưa bảo đảm ranh giới **grapheme cluster**. Nếu chuỗi là `e\u0301`, cắt sau code point `e` sẽ tách dấu ra khỏi chữ; muốn thao tác theo “ký tự người dùng”, cần phân đoạn grapheme.

## 7. Chuỗi trông giống nhau nhưng `equals` trả `false`: normalization

Unicode cho phép cùng một văn bản được biểu diễn bằng chuỗi code point khác nhau. Ví dụ `é` ghép sẵn `U+00E9` và `e` + `U+0301` có thể trông giống nhau nhưng chuỗi Java khác từng code unit.

~~~java
// Fragment có thể đặt trong main; java.text.Normalizer thuộc Java SE.
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(
    java.text.Normalizer.normalize(
        composed, java.text.Normalizer.Form.NFC
    ).equals(
        java.text.Normalizer.normalize(
            decomposed, java.text.Normalizer.Form.NFC
        )
    )
); // true
~~~

- **NFC** tạo dạng chuẩn hóa canonical với việc composition khi áp dụng được; **NFD** decomposition canonical. `Normalizer` thuộc Java SE, không phải dependency ngoài.
- **Normalization không phải encode/decode**: nó có thể đổi chuỗi code point biểu diễn cùng nội dung canonically equivalent, còn encode/decode là chuyển giữa ký tự và byte theo charset.
- `String.equals` kiểm tra nội dung tuần tự của các code unit, không tự NFC/NFD, không so sánh theo locale và không so sánh “trông giống nhau”.
- **Không chuẩn hóa mù quáng** dữ liệu dùng để hash, ký số, so khớp định danh, mật khẩu, protocol hoặc truy vấn database; quy tắc normalization phải được quy định chung ở mọi đầu vào và bên lưu trữ. Ký tự nhìn gần giống nhưng thuộc **code point khác nhau** (homoglyph) cũng không được đảm bảo hợp nhất bởi normalization.
- Với sort/compare theo ngôn ngữ, cân nhắc API `Collator` và quy tắc locale; đó là câu chuyện khác với đếm byte/UTF-16/code point/grapheme.

## 8. Đọc/ghi file: vị trí của encoding trong đường đi dữ liệu

~~~text
           GHI                                ĐỌC
String/char (UTF-16 API)                  byte[]/InputStream
        |                                         |
   UTF-8 encoder                             UTF-8 decoder
        |                                         |
  byte[] / OutputStream                    String/char (UTF-16 API)
        |                                         |
    tệp / mạng                             xử lý code point/
                                          grapheme khi cần
~~~

**Đúng:** API có hợp đồng charset rõ ràng, ví dụ `Files.writeString(path, text, StandardCharsets.UTF_8)` và `Files.readString(path, StandardCharsets.UTF_8)` (từ Java 11); hoặc `InputStreamReader(input, StandardCharsets.UTF_8)` cho stream trong Java 8.

**Sai thường gặp:** đọc từng byte UTF-8 rồi ép mỗi byte sang `char` để ghép thành chuỗi tiếng Việt. Ví dụ `é` có byte `C3 A9`, không phải hai “chữ” tương ứng với hai byte. Cần decoder UTF-8 xử lý chuỗi byte hoàn chỉnh hoặc decoder có trạng thái qua những lần đọc.

**Ranh giới buffer:** chuỗi byte UTF-8 của một code point có thể bị chia giữa hai lần `InputStream.read(...)`. Đừng decode từng chunk bằng cách tạo `new String(chunk, UTF_8)` riêng rẽ nếu chunk có thể kết thúc ở giữa một chuỗi nhiều byte; phải dùng decoder có trạng thái hoặc lớp `Reader` duy trì trạng thái decoder qua các lần đọc.

**Dữ liệu lỗi:** trên hệ thống cần từ chối malformed UTF-8 thay vì âm thầm thay thế, có thể sử dụng:

~~~java
// Fragment: ví dụ kiểm tra byte sai UTF-8.
java.nio.charset.CharsetDecoder decoder =
    java.nio.charset.StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);

byte[] invalid = {(byte) 0xC3, (byte) 0x28};
// decoder.decode(ByteBuffer.wrap(invalid)) ném CharacterCodingException.
~~~

Đoạn này mô tả cách cấu hình; để thực thi, cần gọi `decoder.decode(java.nio.ByteBuffer.wrap(invalid))` bên trong method có `throws java.nio.charset.CharacterCodingException` hoặc khối `try/catch`. Quan hệ cần nhớ: **bytes** được giải mã thành **UTF-16 code units trong String API**; từ đó code point và grapheme phục vụ xử lý văn bản, không phải tạo lại encoding một lần nữa.

## 9. Đếm độ dài, cắt chuỗi và giới hạn nhập liệu

Đừng đặt tên biến mơ hồ như `maxCharacters` khi giới hạn chưa xác định. Câu hỏi trước khi chọn API là: **giới hạn bằng đơn vị gì?**

| Yêu cầu | Phép đo/giải pháp | Cạm bẫy |
| --- | --- | --- |
| API, giao thức giới hạn **byte UTF-8** | `s.getBytes(UTF_8).length` | `s.length()` không phải độ dài payload; đừng cắt byte giữa sequence UTF-8. |
| Thư viện/API định nghĩa độ dài bằng **UTF-16 code unit** | `s.length()` | Emoji ngoài BMP được tính hai. |
| Phân tích Unicode theo **code point** | `s.codePointCount(0,s.length())`, `s.codePoints()` | Dấu kết hợp, ZWJ, cờ emoji có nhiều code point; surrogate lẻ cần validation. |
| Giao diện đếm ký tự người dùng | Phân đoạn **extended grapheme clusters** | Các bản Unicode khác nhau và quy tắc sản phẩm có thể cần kiểm thử. |
| Cắt/truncate chuỗi để hiển thị | Cắt tại **ranh giới grapheme** đã tính và render thử | Cắt theo code point vẫn có thể tách combining mark/ZWJ; chỉ grapheme count cũng không đo chiều rộng trên màn hình. |
| Chiều rộng terminal, căn cột | Thư viện đo display width phù hợp terminal/font | Một grapheme có thể rộng 0, 1, 2 hay khác tùy renderer; ANSI control cũng ảnh hưởng. |
| Chuẩn hóa tìm kiếm/so khớp | Quy định normalization, case folding, locale/collation | `equalsIgnoreCase` không giải quyết mọi quy tắc Unicode/locale hoặc văn bản dễ nhầm. |

**Ví dụ thực tế:** Một form giới hạn “10 ký tự” cho nickname có thể mong đợi 10 grapheme, trong khi API kiểm tra 10 UTF-16 code unit sẽ tính nhiều emoji là hai và phân biệt chữ có dấu dạng ghép với dạng phân rã. Nếu backend còn có giới hạn 40 byte UTF-8, cần **hai** ràng buộc riêng: grapheme theo UX và byte theo lưu trữ. Ranh giới byte có thể nhỏ hơn hoặc lớn hơn số grapheme dựa vào nội dung.

**Khi cần cắt theo code point:** dùng `offsetByCodePoints` để tìm chỉ số UTF-16 cho `substring`. **Khi cần cắt theo grapheme:** duyệt matcher `\X`, lấy `matcher.end()` (vị trí UTF-16 sau cụm) rồi cắt ở đó. Java regex indices tính bằng UTF-16 code unit, nhưng matcher đã xác định điểm kết thúc cụm.

~~~java
// Fragment Java 9+: lấy tối đa 3 grapheme, giữ nguyên dữ liệu gốc.
java.util.regex.Matcher matcher =
    java.util.regex.Pattern.compile("\\X").matcher(text);
int endIndex = 0;
int count = 0;
while (count < 3 && matcher.find()) {
    endIndex = matcher.end();
    count++;
}
String firstThreeGraphemes = text.substring(0, endIndex);
~~~

Đoạn trên chỉ hợp lệ khi `text` được khai báo `String` trong scope. Nếu ít hơn 3 grapheme, kết quả là toàn bộ chuỗi; nếu không có, kết quả chuỗi rỗng. Với giới hạn nghiêm ngặt, phải quyết định cách xử lý các cluster có code point lạ hoặc Unicode version cũ.

## 10. Lỗi phổ biến cần tránh

1. **“Một `char` là một chữ Unicode.”** `char` là code unit 16 bit; code point ngoài BMP cần surrogate pair.
2. **“`String.length()` là số chữ nhìn thấy.”** Nó đếm code unit; không đo byte, code point hay grapheme.
3. **“`codePointCount` là số ký tự nhập liệu.”** Combining sequence/emoji ZWJ/cờ thường nhiều code point nhưng một grapheme.
4. **“UTF-8 mỗi ký tự một byte.”** Đúng chỉ với ASCII; UTF-8 có từ 1 đến 4 byte mỗi Unicode scalar value.
5. **“`String` lưu như byte[] UTF-8.”** API biểu diễn chuỗi theo UTF-16; cách tối ưu bộ nhớ của JDK là chi tiết triển khai.
6. **“`substring` cắt theo code point.”** Indices là UTF-16; dễ chẻ surrogate pair.
7. **“Dùng `String.chars()` để duyệt code point.”** `chars()` cho code unit; dùng `codePoints()` cho code point.
8. **“`new String(bytes)` luôn đọc đúng tiếng Việt.”** Constructor không chỉ định charset phụ thuộc default charset; cần biết encoding thật.
9. **“Decode từng buffer riêng biệt sẽ luôn đúng.”** Một sequence byte có thể nằm ở hai buffer; giữ trạng thái decoder.
10. **“`equals` so sánh theo mắt nhìn.”** Chữ ghép sẵn và chữ + combining mark có thể `equals == false`.
11. **“Một grapheme = một glyph = một ô hiển thị.”** Renderer/font/shaping quyết định glyph và chiều rộng.
12. **“Surrogate lẻ là ký tự Unicode hợp lệ để encode.”** Đây là dữ liệu UTF-16 lỗi theo nghĩa Unicode scalar sequence; cần quyết định báo lỗi hay thay thế.
13. **“Chỉ cần nâng JDK là emoji mới luôn hiển thị đúng.”** Hiển thị còn phụ thuộc font/UI và phiên bản Unicode; segmenter và renderer là hai bước khác nhau.

## 11. Bài tập tư duy

1. Chuỗi `"🙂"` chiếm bao nhiêu byte UTF-8, `char` UTF-16, code point và grapheme cluster?
2. Hai chuỗi `"\u00E9"` và `"e\u0301"` có `equals` không? Có thể chuẩn hóa để so sánh canonical thế nào?
3. Vì sao `"A🙂B".substring(1,2)` không phải emoji hoàn chỉnh? Hãy dùng `offsetByCodePoints`.
4. API nhận nickname tối đa 12 “ký tự nhìn thấy”, nhưng storage cho tối đa 48 byte UTF-8: cần kiểm tra bao nhiêu loại giới hạn?
5. Một file UTF-8 được đọc theo block 4096 byte. Code point 4 byte nằm vắt qua ranh giới block: decoder phải làm gì?
6. Tại sao ký hiệu `👩‍💻` có thể có 3 code point nhưng chỉ một grapheme và vẫn có thể hiển thị thành nhiều hình?

**Đáp án định hướng:**

1. **4 byte UTF-8, 2 UTF-16 code unit, 1 code point, thường 1 grapheme**.
2. `equals` là `false` vì khác dãy UTF-16; chuẩn hóa hai bên bằng `Normalizer.Form.NFC` rồi so sánh.
3. Khoảng `1..2` chỉ chứa high surrogate. Lấy điểm kết thúc bằng `offsetByCodePoints(1,1)` (trả 3), rồi `substring(1,3)`.
4. Hai giới hạn độc lập: tối đa 12 grapheme theo UX và tối đa 48 byte UTF-8 theo giao thức/lưu trữ.
5. Giữ byte chưa đủ hoặc trạng thái decoder qua lần đọc tiếp theo, sau đó mới quyết định code point; không decode chunk riêng bằng constructor `String`.
6. Zero-width joiner nối sequence theo quy tắc grapheme/emoji; renderer vẫn có thể thiếu font hoặc hỗ trợ tổ hợp.

## 12. Tài liệu tham khảo

- Oracle Java SE 21 – [`String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): UTF-16 representation, `length`, `charAt`, `codePointCount`, `offsetByCodePoints`, `chars` và `codePoints`.
- Oracle Java SE 21 – [`Character`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): BMP, supplementary code point, surrogate pair, `toChars` và `charCount`.
- Oracle Java SE 9 – [`Pattern`](https://docs.oracle.com/javase/9/docs/api/java/util/regex/Pattern.html): regex `\X` và `\b{g}`.
- Oracle Java SE 21 – [`Normalizer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode NFC/NFD/NFKC/NFKD.
- Unicode Consortium – [UAX #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): ranh giới grapheme.
- OpenJDK – [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400): ảnh hưởng charset mặc định từ Java 18.

**Ghi nhớ:** `byte[]` đo dữ liệu đã encode; `String.length()` đo đơn vị UTF-16; `codePointCount()` đo đơn vị Unicode code point; **grapheme segmentation** gần với thao tác ký tự người dùng. Xác định loại độ dài trước khi đọc/ghi, validate, substring hoặc dựng giao diện.