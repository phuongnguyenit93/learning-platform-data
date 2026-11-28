# Phân biệt byte, ký tự, code point và code unit khi đọc hoặc ghi tiếng Việt và emoji

## 1. Một chuỗi, nhiều cách đếm

Khi xử lý văn bản Unicode trong Java, câu hỏi **“Chuỗi này dài bao nhiêu ký tự?”** có thể có nhiều đáp án đúng, tùy đang đo cái gì. Điều này đặc biệt rõ với dấu tiếng Việt và emoji.

Ví dụ, emoji `👩‍💻` thường trông như **một biểu tượng** trên màn hình, nhưng gồm **ba Unicode code point**, được biểu diễn bằng **năm UTF-16 code unit** trong API `String` và chiếm **11 byte** nếu mã hóa bằng UTF-8.

Trong phạm vi Java 18 và các JDK hiện đại:

- **Byte:** đơn vị dữ liệu 8 bit của tệp, mạng hoặc mảng `byte[]`. Số byte phụ thuộc charset dùng để mã hóa.
- **Code unit:** đơn vị của một dạng mã hóa Unicode. Với `String` trong Java, chỉ số và `char` biểu thị **UTF-16 code unit, mỗi đơn vị 16 bit**.
- **Code point:** vị trí mã Unicode, thường ký hiệu `U+...`. Một Unicode code point hợp lệ ngoài mặt phẳng BMP được biểu diễn bằng **hai UTF-16 code unit**; trong UTF-8 có thể cần **bốn byte**.
- **Ký tự người dùng nhìn thấy:** thường hiểu là một **grapheme cluster** (*cụm tự vị*): nhóm code point được xử lý như một đơn vị khi con người đọc hoặc chỉnh sửa văn bản. Một grapheme cluster có thể gồm nhiều code point và chưa chắc được vẽ thành đúng một glyph trên mọi font hoặc terminal.

Từ “ký tự” còn xuất hiện trong nhiều tài liệu để chỉ một `char` hoặc một code point, vì vậy phải nêu rõ *đơn vị đếm* trong yêu cầu nghiệp vụ.

### Sơ đồ các tầng biểu diễn

```text
Một cụm người dùng nhìn thấy:       👩‍💻          (1 grapheme cluster)
Các Unicode code point:            U+1F469  U+200D  U+1F4BB
                                      │        │        │
UTF-16 code unit trong String:      2 đơn vị  1 đơn vị  2 đơn vị = 5
UTF-8 byte khi ghi tệp/gửi mạng:    4 byte    3 byte    4 byte   = 11
```

Hai dạng **UTF-8** và **UTF-16** đều biểu diễn cùng nội dung Unicode, nhưng số đơn vị và cách chia chúng khác nhau. Quy tắc UTF-8 mặc định của **JEP 400** (từ JDK 18) không làm `String.length()` đổi sang đếm byte hay code point.

## 2. Bảng đối chiếu tiếng Việt và emoji

Giả sử các chuỗi dưới đây chứa Unicode hợp lệ, mã hóa ra UTF-8 và được phân đoạn theo quy tắc *extended grapheme cluster*.

| Giá trị | Unicode code point | Byte UTF-8 | UTF-16 code unit (`length()`) | Code point | Grapheme cluster |
| --- | --- | ---: | ---: | ---: | ---: |
| `A` | `U+0041` | 1 | 1 | 1 | 1 |
| `ắ` (dạng dựng sẵn, NFC) | `U+1EAF` | 3 | 1 | 1 | 1 |
| `a\u0306\u0301` (chữ `a` + dấu mũ cong + dấu sắc, dạng tổ hợp) | `U+0061 U+0306 U+0301` | 5 | 3 | 3 | 1 |
| `🙂` | `U+1F642` | 4 | 2 | 1 | 1 |
| `👩‍💻` | `U+1F469 U+200D U+1F4BB` | 11 | 5 | 3 | 1 |
| `🇻🇳` | `U+1F1FB U+1F1F3` | 8 | 4 | 2 | 1 |

**Điểm dễ nhầm:**

1. Chữ **`ắ`** có thể có hai cách biểu diễn Unicode tương đương về mặt chuẩn hóa: một code point dựng sẵn `U+1EAF` hoặc ba code point `U+0061 U+0306 U+0301`. Hai chuỗi có thể trông như nhau nhưng số byte, số code unit và `String.equals()` ban đầu khác nhau.
2. Emoji **`🙂`** là một code point ngoài BMP (`U+1F642`), nên trong UTF-16 nó chiếm **hai** `char` (một *surrogate pair*).
3. Emoji **`👩‍💻`** chứa ký tự nối **zero-width joiner — ZWJ (`U+200D`)** giữa hai emoji. Đếm code point sẽ ra ba, nhưng theo phân đoạn grapheme thông thường, cả cụm là một đơn vị.
4. Cờ **`🇻🇳`** gồm hai *regional indicator* code point. Đếm code point sẽ ra hai, còn grapheme cluster thường là một; cách hiển thị còn phụ thuộc font và môi trường.

**Lưu ý về dấu tiếng Việt:** `\u0306` là *combining breve* (dấu trăng), `\u0301` là *combining acute accent* (dấu sắc). Vì đây là dấu kết hợp, chúng không nên được xem là “chữ” độc lập khi xử lý một đơn vị người dùng nhìn thấy.

## 3. Byte: dữ liệu thật khi đọc tệp và trao đổi qua mạng

Bất cứ khi nào chuỗi đi qua ranh giới I/O, ứng dụng phải biết **charset** nào được dùng để đổi `String` thành `byte[]` và ngược lại.

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String text = "ắ🙂";

byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
System.out.println(utf8.length);           // 7 byte = 3 + 4
System.out.println(HexFormat.of().formatHex(utf8));
// e1baaff09f9982

String decoded = new String(utf8, StandardCharsets.UTF_8);
System.out.println(text.equals(decoded));   // true
```

Trong ví dụ, `ắ` được mã hóa thành `E1 BA AF`, còn `🙂` được mã hóa thành `F0 9F 99 82`. Nối các nhóm lại được bảy byte. Con số bảy **không** phải số ký tự nhìn thấy và cũng không phải giá trị `String.length()` (ở đây bằng ba).

Một `byte` trong Java có kiểu `byte` có dấu, nhận giá trị từ `-128` đến `127`. Khi hiển thị hex theo giá trị byte không dấu, có thể dùng `Byte.toUnsignedInt(b)` hoặc `b & 0xFF`.

### Vì sao không được cắt byte theo vị trí bất kỳ?

Giả sử cần giới hạn dữ liệu truyền qua API ở **tối đa 6 byte UTF-8**. Chuỗi `"ắ🙂"` dài bảy byte. Nếu lấy sáu byte đầu, ta cắt mất byte cuối của emoji `🙂` và thu được dãy UTF-8 **không hợp lệ**.

Điều kiện giới hạn byte phải kiểm tra trên **dữ liệu đã mã hóa**. Nếu cần cắt ngắn nội dung để đáp ứng giới hạn, hãy duyệt theo code point hoặc grapheme cluster rồi thử mã hóa lại từng phần; không cắt giữa một dãy UTF-8 nhiều byte.

## 4. Code unit: `char` và `String.length()` trong Java

API `String` có ngữ nghĩa UTF-16: **`length()` trả về số UTF-16 code unit**, `charAt(index)` trả về code unit tại chỉ số đó, và các chỉ số dùng cho `substring()`, `indexOf()`, `offsetByCodePoints()` cũng dựa trên vị trí `char`.

Đây là hợp đồng API hiện hành dù JVM có thể sử dụng cách lưu trữ tối ưu bên trong. Không nên suy ra cấu trúc bộ nhớ nội bộ chỉ từ `length()`.

```java
String emoji = "🙂";

System.out.println(emoji.length());                    // 2
System.out.println(Character.isHighSurrogate(
        emoji.charAt(0)));                             // true
System.out.println(Character.isLowSurrogate(
        emoji.charAt(1)));                             // true
System.out.printf("U+%X%n", emoji.codePointAt(0));      // U+1F642
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
```

UTF-16 sử dụng *surrogate pair* gồm:

- **High surrogate:** giá trị từ `U+D800` đến `U+DBFF`.
- **Low surrogate:** giá trị từ `U+DC00` đến `U+DFFF`.

Vì vậy, một `char` **không bảo đảm** chứa trọn vẹn một Unicode code point. Đây là lý do không nên dùng vòng lặp `for (int i = 0; i < s.length(); i++)` kết hợp `charAt(i)` nếu mục đích là duyệt các code point.

Nguy hiểm tương tự khi cắt chuỗi:

```java
String emoji = "🙂";
String invalidPiece = emoji.substring(0, 1);
// invalidPiece chỉ chứa high surrogate, không còn là biểu diễn
// UTF-16 hợp lệ của emoji ban đầu. Không dùng nó để lưu/gửi văn bản.
```

`substring(0, 1)` hoàn toàn hợp lệ theo chỉ số Java, nhưng kết quả chứa **surrogate đơn lẻ**. Nếu sau đó mã hóa sang UTF-8, bộ mã hóa phải xử lý đơn vị UTF-16 sai hỏng theo chính sách lỗi/thay thế; không thể lấy lại emoji ban đầu từ mảnh chuỗi đó.

## 5. Code point: cách duyệt từng giá trị Unicode

Với Unicode hợp lệ, `String.codePoints()`, `String.codePointAt()` và `String.codePointCount()` giúp thao tác theo code point.

Ví dụ duyệt chuỗi chứa chữ Việt và emoji:

```java
String text = "ắ🙂";

text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp)
);
// U+1EAF
// U+1F642
```

Nếu cần đồng thời giữ vị trí trong `String` (đơn vị UTF-16), tăng chỉ số đúng theo số code unit của mỗi code point:

```java
String text = "ắ🙂";

for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    System.out.printf("index=%d, codePoint=U+%X%n", i, cp);
    i += Character.charCount(cp);
}
// index=0, codePoint=U+1EAF
// index=1, codePoint=U+1F642
```

Hàm `Character.charCount(cp)` trả về `1` hoặc `2` tùy code point. Nếu muốn lấy **code point đầu tiên**, có thể dùng `offsetByCodePoints`:

```java
String text = "🙂ắ";
int end = text.offsetByCodePoints(0, 1); // 2 UTF-16 code unit
String firstCodePoint = text.substring(0, end);
System.out.println(firstCodePoint);      // 🙂
```

Cần phân biệt: đây là phép lấy **một code point**, chưa chắc là **một ký tự người dùng nhìn thấy**. Với `"👩‍💻"`, code point đầu tiên chỉ là `👩`; cả cụm cần thêm ZWJ và `💻`.

Một chuỗi Java về mặt kỹ thuật có thể chứa surrogate đơn lẻ. `codePoints()` khi đó vẫn trả về giá trị surrogate đó như một phần tử riêng, chứ không có nghĩa nội dung đã trở thành chuỗi Unicode scalar value hợp lệ. Khi làm việc với nguồn dữ liệu không tin cậy, cần kiểm tra và xử lý encoding không hợp lệ tại ranh giới nhập.

## 6. Grapheme cluster: đơn vị gần với “một ký tự” trên màn hình

Unicode có quy tắc phân đoạn văn bản để gom các code point liên quan thành *extended grapheme clusters* (Unicode Standard Annex #29). Khái niệm này phù hợp hơn `length()` hay `codePointCount()` khi cần xử lý con trỏ, xóa một ký tự nhìn thấy hoặc tính giới hạn nhập liệu cho người dùng.

Java hỗ trợ mẫu regex **`\X`** để khớp với một Unicode extended grapheme cluster và **`\b{g}`** cho ranh giới cụm. Trong chuỗi ký tự Java, cần viết regex `"\\X"` vì dấu gạch chéo ngược phải được escape:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

Pattern clusterPattern = Pattern.compile("\\X");
String text = "a\u0306\u0301👩‍💻";

Matcher matcher = clusterPattern.matcher(text);
while (matcher.find()) {
    System.out.println("Cụm: [" + matcher.group() + "]");
}
// Cụm: [ắ]    (hiển thị thường giống chữ ắ; dữ liệu vẫn có thể ở dạng tổ hợp)
// Cụm: [👩‍💻]
```

Có thể đếm số cụm bằng:

```java
long graphemeCount = Pattern.compile("\\X")
        .matcher("a\u0306\u0301👩‍💻")
        .results()
        .count();
System.out.println(graphemeCount); // 2
```

**Không đồng nhất grapheme cluster với glyph:** cách font vẽ một cụm có thể khác nhau. Ví dụ một số môi trường không hỗ trợ emoji ZWJ có thể hiển thị các biểu tượng tách rời dù văn bản vẫn gồm một grapheme cluster theo quy tắc phân đoạn.

Quy tắc Unicode và dữ liệu phiên bản đi kèm JDK có thể được cập nhật. Với sản phẩm có yêu cầu phân đoạn Unicode chính xác và đồng nhất giữa nhiều nền tảng/phiên bản, hãy kiểm thử tập ngôn ngữ và emoji thực tế theo phiên bản chuẩn Unicode mà sản phẩm chọn.

## 7. Hai chuỗi nhìn giống nhau chưa chắc có cùng byte

Tiếng Việt thường gặp **chữ dựng sẵn** và **chữ có dấu tổ hợp**. Chúng có thể tương đương theo chuẩn Unicode nhưng không giống nhau từng code unit.

```java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

String composed = "ắ";              // U+1EAF
String decomposed = "a\u0306\u0301"; // U+0061 U+0306 U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.length());           // 1
System.out.println(decomposed.length());         // 3

System.out.println(composed.getBytes(StandardCharsets.UTF_8).length);
// 3
System.out.println(decomposed.getBytes(StandardCharsets.UTF_8).length);
// 5

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

`Normalizer.Form.NFC` đưa văn bản về dạng chuẩn hóa tổng hợp chuẩn tắc khi có thể, thích hợp khi hợp đồng dữ liệu quy định NFC. `Normalizer.Form.NFD` đưa văn bản về dạng phân rã chuẩn tắc. Chuẩn hóa không phải phép thay thế cho xác định charset: **charset quyết định cách các byte biểu diễn Unicode; normalization quyết định cách biểu diễn nội dung bằng chuỗi code point**.

Không tự chuẩn hóa dữ liệu ở mọi nơi nếu có yêu cầu bảo toàn byte chính xác, chữ ký số hoặc giao thức dựa trên chuỗi gốc. Trước khi so sánh, tìm kiếm hoặc lưu trữ, cần có chính sách normalization phù hợp với nghiệp vụ.

## 8. Chương trình thực hành đo cả bốn đơn vị

Ví dụ sau chạy trên Java 18+ và các JDK hiện đại. Chương trình dùng `StandardCharsets.UTF_8` để lấy số byte, API `String` để lấy số code unit và code point, cùng regex `\X` để đo extended grapheme cluster.

```java
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class UnicodeUnitsDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    static void inspect(String label, String value) {
        int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
        int utf16Units = value.length();
        int codePoints = value.codePointCount(0, value.length());
        long clusters = GRAPHEME.matcher(value).results().count();

        String codes = value.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));

        System.out.printf(
                "%-16s bytes=%d units=%d points=%d clusters=%d (%s)%n",
                label, utf8Bytes, utf16Units, codePoints, clusters, codes);
    }

    public static void main(String[] args) {
        inspect("ASCII", "A");
        inspect("a dau NFC", "ắ");
        inspect("a + 2 dau", "a\u0306\u0301");
        inspect("smiley", "🙂");
        inspect("emoji ZWJ", "👩‍💻");
        inspect("co Viet Nam", "🇻🇳");
    }
}
```

Lưu tệp nguồn ở UTF-8, biên dịch và chạy:

```bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
```

Các con số mong đợi (bỏ qua độ rộng căn lề khi in):

```text
ASCII            bytes=1 units=1 points=1 clusters=1 (U+0041)
a dau NFC        bytes=3 units=1 points=1 clusters=1 (U+1EAF)
a + 2 dau        bytes=5 units=3 points=3 clusters=1 (U+0061 U+0306 U+0301)
smiley           bytes=4 units=2 points=1 clusters=1 (U+1F642)
emoji ZWJ        bytes=11 units=5 points=3 clusters=1 (U+1F469 U+200D U+1F4BB)
co Viet Nam      bytes=8 units=4 points=2 clusters=1 (U+1F1FB U+1F1F3)
```

Chương trình kiểm chứng đúng trọng tâm: **cùng một chuỗi nhưng mỗi đơn vị đo cho kết quả khác nhau**. Nếu terminal chưa hỗ trợ font emoji thì cách hiển thị có thể khác; các số đo về dữ liệu vẫn dựa trên API và nội dung Unicode.

## 9. Đọc/ghi tệp tiếng Việt trong bối cảnh JEP 400

**JEP 400** đưa UTF-8 thành charset mặc định của những Java SE API phụ thuộc `Charset.defaultCharset()` kể từ JDK 18. Điều này giúp mã Java ít phụ thuộc hệ điều hành và locale hơn, nhưng **không thay đổi** ý nghĩa UTF-16 code unit của `String.length()`. Cấu hình tương thích khi khởi động `-Dfile.encoding=COMPAT` cũng có thể khiến default charset khác UTF-8 tùy môi trường.

Khi định dạng tệp hoặc giao thức được quy định là UTF-8, hãy nêu charset rõ ràng để hợp đồng dữ liệu có thể kiểm chứng:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class VietnameseUtf8File {
    public static void main(String[] args) throws Exception {
        String original = "Tiếng Việt 🇻🇳 👩‍💻";
        Path file = Path.of("vietnamese-utf8.txt");

        // Ghi và đọc UTF-8 tường minh, bất kể default charset.
        Files.writeString(file, original, StandardCharsets.UTF_8);
        String loaded = Files.readString(file, StandardCharsets.UTF_8);

        System.out.println(original.equals(loaded)); // true
        System.out.println(
                Files.size(file) == original.getBytes(
                        StandardCharsets.UTF_8).length); // true
    }
}
```

Khi đối chiếu kết quả:

- `Files.size(file)` là **số byte thực tế trong tệp** (ở đây ghi đè tệp bằng văn bản UTF-8, không thêm byte ngoài chuỗi).
- `loaded.length()` là **số UTF-16 code unit**.
- `loaded.codePointCount(0, loaded.length())` là **số code point** theo API Java.
- `Pattern.compile("\\X").matcher(loaded).results().count()` là **số extended grapheme cluster**.

`Files.readString(path)` và `Files.writeString(path, text)` vốn đã dùng UTF-8 khi không truyền charset; đây không phải hành vi mới riêng của JEP 400. Vẫn nên truyền `StandardCharsets.UTF_8` khi muốn thể hiện rõ định dạng dữ liệu.

**Khi dữ liệu gốc không phải UTF-8:** chọn đúng charset của tệp nguồn khi đọc. Không thể sửa dữ liệu legacy chỉ bằng cách đổi JDK hay ép `String` thành UTF-8. Với dãy UTF-8 lỗi (ví dụ bị cắt giữa một emoji), `Files.readString` có thể ném ngoại lệ đọc/giải mã; cần phát hiện và xử lý theo yêu cầu ứng dụng thay vì âm thầm coi byte lỗi là ký tự hợp lệ.

## 10. Chọn đúng phép đo cho từng yêu cầu

| Yêu cầu | Đơn vị phù hợp | Cách thực hiện trên Java |
| --- | --- | --- |
| Giới hạn payload/tệp ở 1024 byte UTF-8 | **Byte** | `text.getBytes(StandardCharsets.UTF_8).length` hoặc đo byte khi ghi |
| Tính chỉ số cho `substring`, `charAt`, API nhận offset trong `String` | **UTF-16 code unit** | `text.length()`, `charAt()`; bảo toàn ranh giới surrogate |
| Phân tích từng code point Unicode hoặc chuyển một code point thành ký tự | **Code point** | `codePoints()`, `codePointAt()`, `Character.toChars()` |
| Đếm hoặc xóa từng “ký tự nhìn thấy” trong ô nhập liệu | **Grapheme cluster** | `Pattern.compile("\\X")`, kiểm thử bộ emoji/ngôn ngữ thực tế |
| So sánh chữ tiếng Việt có thể chứa dấu tổ hợp | **Normalization** trước khi so sánh khi hợp đồng yêu cầu | `Normalizer.normalize(text, Normalizer.Form.NFC)` |

Nếu thiết kế API chấp nhận một trường tên `maxCharacters`, phải xác định “characters” là **code point**, **grapheme cluster** hay **UTF-16 code unit**. Không thể mặc định rằng ba cách đếm này luôn bằng nhau.

### Những lỗi thường gặp cần tránh

1. **Đồng nhất `String.length()` với số byte UTF-8:** chỉ đúng trong một số dữ liệu đơn giản, ví dụ ký tự ASCII.
2. **Đồng nhất `char` với một emoji:** emoji ngoài BMP cần hai `char`.
3. **Cắt `substring()` ở vị trí bất kỳ:** có thể chia đôi surrogate pair hoặc cắt ngang một cụm dấu/ZWJ.
4. **Đếm code point rồi tuyên bố đó là số ký tự hiển thị:** chữ có dấu tổ hợp và emoji ghép có thể gồm nhiều code point trong một grapheme cluster.
5. **Cho rằng JEP 400 đã chuẩn hóa mọi chuỗi:** JEP 400 chỉ xác định default charset cho các API liên quan; Unicode normalization là vấn đề riêng.
6. **Nhầm hiển thị terminal với dữ liệu:** terminal thiếu hỗ trợ font/emoji có thể vẽ khác, dù byte, code point và chuỗi Java vẫn đúng.

## 11. Bài tập vận dụng

**Bài 1.** Với chuỗi `"🙂a"`, hãy cho biết số byte UTF-8, `length()` và số code point.

*Đáp án:* `4 + 1 = 5` byte, `2 + 1 = 3` UTF-16 code unit, `1 + 1 = 2` code point. Có hai grapheme cluster.

**Bài 2.** Hai người dùng cùng nhập chữ `ắ`. Một nguồn trả về `"\u1EAF"`; nguồn khác trả về `"a\u0306\u0301"`. Có thể so sánh trực tiếp bằng `equals()` không?

*Đáp án:* Hai cách biểu diễn có thể nhìn giống nhau nhưng `equals()` ban đầu trả về `false`. Nếu nghiệp vụ yêu cầu so sánh tương đương chuẩn tắc, chuẩn hóa hai chuỗi theo cùng `Normalizer.Form.NFC` rồi so sánh.

**Bài 3.** Một API cho phép tối đa 4 byte UTF-8. Chuỗi `"🙂"` có vừa không? `"🙂A"` thì sao? Có thể giảm chuỗi thứ hai xuống bốn byte bằng cách cắt mảng byte tại vị trí 4 không?

*Đáp án:* `"🙂"` vừa đúng bốn byte; `"🙂A"` là năm byte nên vượt giới hạn. Muốn rút ngắn, phải loại bỏ `A` hoặc rút theo ranh giới Unicode phù hợp; không cắt dãy byte tùy tiện. Với chuỗi này, **bốn** byte đầu trọn vẹn emoji là hợp lệ, nhưng đó là vì đã chọn đúng ranh giới mã hóa, không phải vì luôn có thể dùng phép cắt byte tại vị trí 4.

**Bài 4.** Một ô nhập liệu cần giới hạn 20 “ký tự” theo nghĩa người dùng có thể xóa từng cụm emoji và chữ có dấu. Dùng `text.length() <= 20` có phù hợp không?

*Đáp án:* Không phù hợp nếu mỗi grapheme cluster được tính là một ký tự. Nên xác định chính sách đếm theo extended grapheme cluster (ví dụ regex `\X`), thử với dấu tổ hợp, cờ, emoji ZWJ, đồng thời kiểm tra giới hạn byte riêng nếu backend có yêu cầu payload.

## 12. Kết luận

- **Byte** trả lời câu hỏi dữ liệu mã hóa chiếm bao nhiêu chỗ trong tệp hoặc gói tin.
- **UTF-16 code unit** trả lời câu hỏi về các chỉ số và độ dài `String` trong Java.
- **Code point** trả lời câu hỏi về từng vị trí mã Unicode.
- **Grapheme cluster** thường gần nhất với một “ký tự” mà người dùng nhận biết.

Từ Java 18, JEP 400 giúp nhất quán **charset mặc định UTF-8** trên các môi trường JVM thông thường. Khi đọc/ghi tiếng Việt và emoji, hãy nêu UTF-8 rõ ràng ở ranh giới I/O và chọn đúng đơn vị đo cho từng yêu cầu. Đây là kiến thức vẫn áp dụng trên các JDK hiện đại, không phụ thuộc vào các API lỗi thời.

### Tài liệu tham khảo

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — String: UTF-16 code units, codePointAt, codePointCount và codePoints](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html).
- [Oracle Java SE 27 — Character: Unicode code points và UTF-16](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html).
- [Oracle Java SE 27 — Pattern: ký hiệu \X và \b{g}](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Pattern.html).
- [Oracle Java SE 27 — Normalizer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.html).
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://unicode.org/reports/tr29/).
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/).
