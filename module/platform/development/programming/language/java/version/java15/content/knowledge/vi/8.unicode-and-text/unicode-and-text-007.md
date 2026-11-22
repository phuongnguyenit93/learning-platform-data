# Kiểm thử dấu tiếng Việt, emoji và ký tự bổ sung trong Java

## 1. Mục tiêu và phạm vi

Một chương trình xử lý văn bản Java cần đọc, lưu, so sánh, cắt chuỗi và truyền dữ liệu **mà không làm mất dấu tiếng Việt, tách hỏng emoji hoặc biến đổi ký tự Unicode**. Kiểm thử chỉ với `"abc"` sẽ không phát hiện nhiều lỗi vì mỗi chữ ASCII thường chiếm đúng một byte UTF-8, một UTF-16 `char`, một Unicode code point và một cụm ký tự hiển thị. Văn bản tiếng Việt và emoji cho thấy những đại lượng này **không luôn bằng nhau**.

Các kiểm thử trong bài tập trung vào:

1. **Dấu tiếng Việt:** văn bản UTF-8 được bảo toàn, chuỗi có dấu ghép sẵn (*precomposed*) và dấu kết hợp (*decomposed*) được so sánh đúng khi cần chuẩn hóa.
2. **Emoji và ký tự bổ sung:** đếm, duyệt, cắt chuỗi theo UTF-16/code point và nhận diện cặp surrogate hợp lệ.
3. **Cụm ký tự người dùng nhìn thấy:** emoji có `zero-width joiner` (ZWJ) và cờ quốc gia có thể gồm nhiều code point nhưng hiển thị thành một cụm.
4. **Đầu vào/đầu ra:** kiểm tra vòng truyền UTF-8 và từ chối byte UTF-8 không hợp lệ khi nghiệp vụ yêu cầu dữ liệu đúng chuẩn.

Các API dùng ở đây là API Java SE **còn được hỗ trợ**, chạy với **JDK 17 trở lên**, không cần chế độ preview. Đây là nền tảng kiểm thử hữu ích cho ứng dụng Java 15+.

## 2. Phân biệt byte, char, code point và grapheme cluster

| Đơn vị | Ý nghĩa | API/cách kiểm tra trong Java |
| --- | --- | --- |
| **Byte UTF-8** | Số byte khi mã hóa văn bản sang UTF-8. Ký tự ngoài ASCII có thể chiếm nhiều byte. | `s.getBytes(StandardCharsets.UTF_8).length` |
| **UTF-16 code unit** | Mỗi phần tử `char` 16 bit của `String`; ký tự ngoài BMP dùng **hai** code unit (surrogate pair). | `s.length()`, `s.charAt(i)`, `s.chars()` |
| **Unicode code point** | Một giá trị Unicode, có thể nằm trong BMP hoặc ngoài BMP. Một code point ngoài BMP chiếm hai UTF-16 `char`. | `s.codePointCount(0, s.length())`, `s.codePoints()`, `s.codePointAt(i)` |
| **Extended grapheme cluster** | Một cụm văn bản thường được người dùng cảm nhận như một ký tự; có thể gồm nhiều code point ghép dấu hoặc emoji nối bằng ZWJ. | `Pattern.compile("\\X")` và `matcher(...).results().count()` |

**Không dùng `String.length()` để đếm số chữ người dùng nhìn thấy.** Nó trả số UTF-16 code unit. Đếm code point cũng chưa luôn bằng số cụm hiển thị: chữ tiếng Việt dạng dấu kết hợp, quốc kỳ bằng hai regional indicators, và emoji có ZWJ là các ví dụ.

### Bộ ca kiểm thử điển hình

| Giá trị | UTF-16 `length()` | Code point | Cụm `\X` | Giải thích |
| --- | ---: | ---: | ---: | --- |
| `"A"` | 1 | 1 | 1 | ASCII đơn giản |
| `"ắ"` (U+1EAF) | 1 | 1 | 1 | Chữ tiếng Việt ghép sẵn trong BMP |
| `"a\u0306\u0301"` | 3 | 3 | 1 | `a` + dấu breve + dấu sắc, nhìn tương đương `ắ` |
| `"🙂"` (U+1F642) | 2 | 1 | 1 | Emoji là một code point **bổ sung**, dùng một surrogate pair |
| `"👩‍💻"` | 5 | 3 | 1 | Người + ZWJ + máy tính, một cụm emoji |
| `"🇻🇳"` | 4 | 2 | 1 | Hai regional indicators ghép thành một cờ |

Các số trên có thể tự kiểm tra bằng chương trình ở mục 7. Phân đoạn `\X` tuân theo quy tắc Unicode được JDK sử dụng. Unicode và bộ dữ liệu phân loại ký tự có thể được cập nhật giữa các phiên bản JDK; với emoji mới hoặc yêu cầu hiển thị nghiêm ngặt, cần kiểm thử lại trên **JDK đích**.

## 3. Kiểm thử dấu tiếng Việt: NFC và NFD

Unicode cho phép một số chữ có dấu được biểu diễn bằng nhiều chuỗi code point **tương đương về mặt chuẩn hóa**. Ví dụ:

- `"ắ"` có thể dùng một code point ghép sẵn **U+1EAF**.
- `"a\u0306\u0301"` có ba code point: `a`, dấu mũ ngắn (*combining breve*, U+0306) và dấu sắc (*combining acute accent*, U+0301).

Hai chuỗi trên thường trông như cùng một chữ nhưng **`String.equals()` trả `false`** vì các code unit khác nhau. Java không tự chuẩn hóa `String` khi so sánh.

~~~java
import java.text.Normalizer;

String composed = "ắ";
String decomposed = "a\u0306\u0301";

boolean rawSame = composed.equals(decomposed); // false

String left = Normalizer.normalize(composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

boolean canonicalSame = left.equals(right); // true
~~~

Đoạn mã trên là **minh họa**, không phải file độc lập có `main`. Chương trình hoàn chỉnh ở mục 7 kiểm tra cả hai trường hợp.

`java.text.Normalizer` hỗ trợ:

- **NFC:** chuẩn hóa tương đương chính tắc rồi ghép về dạng có thể ghép sẵn; thường phù hợp khi cần thống nhất văn bản tự nhiên cho so sánh/lưu trữ.
- **NFD:** tách thành dạng phân rã chính tắc; có ích cho xử lý dấu có chủ đích.
- **NFKC/NFKD:** chuẩn hóa tương thích, có thể làm mất một số phân biệt hình thức và ngữ nghĩa. Không tự động áp dụng cho mọi dữ liệu người dùng nếu nghiệp vụ không yêu cầu.

**Kiểm thử tối thiểu:** khẳng định raw strings khác nhau, sau NFC thì bằng nhau, và ký tự `ắ` ghép sẵn có `length()==1` trong khi biến thể dấu kết hợp có `length()==3`. Hai dạng vẫn có thể tạo **một cụm hiển thị**.

Lưu ý: **chuẩn hóa Unicode không đồng nghĩa bỏ dấu hoặc không phân biệt hoa/thường**. Khi tìm kiếm tiếng Việt, hãy định nghĩa rõ yêu cầu: so sánh chính xác, chuẩn hóa NFC, tìm kiếm không phân biệt dấu, hay so sánh theo quy tắc locale. Không tự động bỏ dấu vì `ma`, `má` và `mà` có thể mang nghĩa khác nhau.

## 4. Kiểm thử emoji và ký tự bổ sung

### 4.1. Emoji ngoài BMP tạo một surrogate pair

`"🙂"` là Unicode code point **U+1F642** nằm ngoài **Basic Multilingual Plane (BMP)**. Java `String` dùng UTF-16 để biểu diễn, do đó:

~~~java
String emoji = "🙂";

emoji.length();                        // 2 UTF-16 code unit
emoji.codePointCount(0, emoji.length()); // 1 Unicode code point
emoji.codePointAt(0);                  // 0x1F642

Character.isHighSurrogate(emoji.charAt(0)); // true
Character.isLowSurrogate(emoji.charAt(1));  // true
emoji.getBytes(StandardCharsets.UTF_8).length; // 4 byte
~~~

Đây là **đoạn minh họa**; lớp độc lập ở mục 7 chứa các kiểm tra có thể chạy. Các hàm nhận `char` đơn lẻ không tự động có đầy đủ thông tin của ký tự bổ sung.

**Không viết kiểm thử `assertEquals(1, emoji.length())`**: số đúng là 2. Nếu mục tiêu là đếm code point, dùng `codePointCount(...)` hoặc `codePoints().count()`. Nếu cần số cụm hiển thị, dùng thuật toán phân đoạn grapheme phù hợp.

### 4.2. Cắt chuỗi an toàn theo code point

Với `String mixed = "A🙂B";`, vị trí của emoji trong UTF-16 bắt đầu ở chỉ số 1 nhưng chiếm **hai** vị trí. `mixed.substring(1, 2)` cắt chỉ **high surrogate**, tạo chuỗi không có cặp surrogate đầy đủ. Để cắt đúng **một code point**:

~~~java
String mixed = "A🙂B";
int start = mixed.offsetByCodePoints(0, 1);
int end = mixed.offsetByCodePoints(start, 1);
String safeEmoji = mixed.substring(start, end); // "🙂"
~~~

`offsetByCodePoints` đi theo code point nhưng **không bảo đảm cắt nguyên một grapheme cluster**. Nếu chuỗi chứa dấu kết hợp hoặc emoji nối ZWJ, cắt một code point vẫn có thể phá vỡ cụm hiển thị. Khi thao tác mang tính UI (xóa một ký tự người dùng nhìn thấy, di chuyển con trỏ), cần xử lý theo ranh giới grapheme.

### 4.3. Phát hiện surrogate bị tách

`String` có thể chứa **surrogate đơn lẻ không ghép cặp**. `String.codePointCount` không phải trình kiểm định UTF-16: nó vẫn đếm surrogate đơn lẻ như một phần tử. Khi dữ liệu phải hợp lệ, hãy kiểm tra mỗi high surrogate có low surrogate theo sau và không tồn tại low surrogate đứng riêng.

Chương trình ở mục 7 có `wellFormedUtf16(String)` để kiểm tra điều này, đồng thời chủ động thử một chuỗi chỉ chứa `(char) 0xD83D` và khẳng định nó **không hợp lệ**. Việc kiểm tra hữu ích trước khi trao đổi dữ liệu với bộ mã hóa, giao thức hoặc API yêu cầu văn bản Unicode hợp lệ.

## 5. Kiểm thử emoji nối ZWJ và cờ quốc gia

Một biểu tượng người dùng nhìn thấy không nhất thiết chỉ có một code point:

- `"👩‍💻"` gồm **U+1F469** (woman), **U+200D** (zero-width joiner), **U+1F4BB** (laptop). Trong UTF-16 nó có **5 code unit**, **3 code point**, nhưng `\X` có thể nhận diện thành **1 extended grapheme cluster**.
- `"🇻🇳"` gồm hai **regional indicator symbols** (V và N). Nó chiếm **4 UTF-16 code unit**, **2 code point** và **1 grapheme cluster**.

Trong Java regex, `\X` là ký hiệu *extended grapheme cluster*:

~~~java
import java.util.regex.Pattern;

Pattern grapheme = Pattern.compile("\\X");
long count = grapheme.matcher("👩‍💻").results().count(); // 1 trên JDK được kiểm thử
~~~

Trong **chuỗi Java**, cần hai dấu backslash `"\\X"` để truyền một dấu backslash thực cho biểu thức chính quy. API `Matcher.results()` được hỗ trợ từ Java 9 nên dùng được với Java 17+.

**Cần giới hạn kỳ vọng:** một grapheme cluster là đơn vị phân đoạn văn bản theo quy tắc Unicode, không phải bảo đảm giao diện sẽ vẽ thành đúng một hình. Emoji hiển thị thành một biểu tượng hay nhiều biểu tượng còn phụ thuộc font, nền tảng và bộ vẽ. Nếu phần mềm đòi hỏi phân đoạn Unicode/emoji cố định xuyên nhiều phiên bản, hãy cố định JDK/phiên bản thuật toán và đưa các ca Unicode quan trọng vào bộ kiểm thử hồi quy.

## 6. Kiểm thử dữ liệu UTF-8 ở ranh giới I/O

Dấu tiếng Việt và emoji dễ bị lỗi nếu đọc/ghi file hoặc gửi dữ liệu qua các lớp chuyển mã không thống nhất. Cần quy định **UTF-8** tường minh:

~~~java
import java.nio.charset.StandardCharsets;

String value = "Tiếng Việt 🙂";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

boolean roundTrip = value.equals(decoded); // true
~~~

Với file, dùng `Files.readString(path, StandardCharsets.UTF_8)` và `Files.writeString(path, text, StandardCharsets.UTF_8)` khi thích hợp. Khi biên dịch source có dấu tiếng Việt, dùng `javac -encoding UTF-8` để tránh phụ thuộc encoding mặc định của công cụ hoặc máy chạy.

**Vòng mã hóa và giải mã cùng encoding** là một kiểm thử cần thiết nhưng chưa đủ để kiểm tra mọi đầu vào lỗi. Các constructor `new String(bytes, charset)` có thể thay chuỗi byte sai bằng ký tự thay thế `U+FFFD` theo chính sách giải mã. Nếu ứng dụng bắt buộc **từ chối UTF-8 không hợp lệ**, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` để phát hiện `CharacterCodingException`.

Ví dụ hai byte `C3 28` không phải chuỗi UTF-8 hợp lệ vì `C3` đòi một continuation byte, còn `28` không phải continuation byte. Chương trình chạy ở mục 7 kiểm tra bộ giải mã từ chối dữ liệu này.

**Phân biệt lỗi:**

- **Mojibake:** dữ liệu byte được đọc bằng encoding khác encoding nguồn (ví dụ ký tự tiếng Việt biến thành ký tự lạ). Cần kiểm tra byte, charset đầu vào và đầu ra.
- **Normalization mismatch:** hai chuỗi hiển thị giống nhau nhưng `equals` khác do NFC/NFD; đổi charset không giải quyết nguyên nhân này.
- **Surrogate bị cắt:** thao tác trên chỉ số UTF-16 làm vỡ code point bổ sung; chỉ chuyển sang UTF-8 cũng không khôi phục chính xác chuỗi đã bị cắt.

## 7. Chương trình kiểm thử hoàn chỉnh bằng Java 17+

Tạo file **`UnicodeVietnameseEmojiTests.java`** và lưu bằng **UTF-8**. Chương trình chỉ dùng Java SE, mỗi ca sai sẽ ném `AssertionError` và dừng. Không phụ thuộc cờ JVM `-ea` như câu lệnh `assert` thông thường.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeVietnameseEmojiTests {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");
    private static int passed = 0;

    public static void main(String[] args) {
        String accented = "ắ";
        String decomposed = "a\u0306\u0301";
        String emoji = "🙂";
        String joinedEmoji = "👩‍💻";
        String flag = "🇻🇳";
        String sentence = "Tiếng Việt: Nguyễn, Trường, ắ, ộ";

        check("different raw encodings",
                !accented.equals(decomposed));
        check("NFC equivalence",
                Normalizer.normalize(accented, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)));
        check("Vietnamese length",
                accented.length() == 1 && decomposed.length() == 3
                        && accented.codePointCount(0, accented.length()) == 1
                        && decomposed.codePointCount(0, decomposed.length()) == 3);
        check("Vietnamese grapheme",
                graphemeCount(accented) == 1 && graphemeCount(decomposed) == 1);

        check("supplementary emoji",
                emoji.length() == 2 && emoji.codePointCount(0, emoji.length()) == 1
                        && emoji.codePointAt(0) == 0x1F642
                        && Character.isSurrogatePair(emoji.charAt(0), emoji.charAt(1))
                        && emoji.getBytes(StandardCharsets.UTF_8).length == 4);
        String mixed = "A" + emoji + "B";
        int start = mixed.offsetByCodePoints(0, 1);
        int end = mixed.offsetByCodePoints(start, 1);
        check("safe substring by code point",
                mixed.substring(start, end).equals(emoji)
                        && !wellFormedUtf16(mixed.substring(start, start + 1)));
        check("joined emoji grapheme",
                joinedEmoji.length() == 5
                        && joinedEmoji.codePointCount(0, joinedEmoji.length()) == 3
                        && graphemeCount(joinedEmoji) == 1);
        check("flag grapheme",
                flag.length() == 4
                        && flag.codePointCount(0, flag.length()) == 2
                        && graphemeCount(flag) == 1);

        String payload = sentence + " | " + decomposed + " | " + emoji + joinedEmoji + flag;
        byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
        check("UTF-8 round trip",
                payload.equals(new String(bytes, StandardCharsets.UTF_8)));
        check("well formed UTF-16",
                wellFormedUtf16(payload)
                        && !wellFormedUtf16(String.valueOf((char) 0xD83D)));

        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(new byte[]{(byte) 0xC3, (byte) 0x28}));
        } catch (CharacterCodingException ex) {
            rejected = true;
        }
        check("reject malformed UTF-8", rejected);
        System.out.println("TOTAL PASS=" + passed);
    }

    private static long graphemeCount(String input) {
        return GRAPHEME.matcher(input).results().count();
    }

    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        passed++;
        System.out.println("PASS " + label);
    }

    private static boolean wellFormedUtf16(String input) {
        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);
            if (Character.isHighSurrogate(ch)) {
                if (i + 1 == input.length()
                        || !Character.isLowSurrogate(input.charAt(i + 1))) {
                    return false;
                }
                i++;
            } else if (Character.isLowSurrogate(ch)) {
                return false;
            }
        }
        return true;
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeVietnameseEmojiTests.java
java UnicodeVietnameseEmojiTests
~~~

**Stdout chính xác**, đã được kiểm chứng trên JDK 24 khi biên dịch với `--release 17`:

~~~text
PASS different raw encodings
PASS NFC equivalence
PASS Vietnamese length
PASS Vietnamese grapheme
PASS supplementary emoji
PASS safe substring by code point
PASS joined emoji grapheme
PASS flag grapheme
PASS UTF-8 round trip
PASS well formed UTF-16
PASS reject malformed UTF-8
TOTAL PASS=11
~~~

Các nhãn `PASS` cho biết mỗi điều kiện đều đúng. Nếu một ca thất bại, hàm `check` ném `AssertionError` thay vì in `PASS`, nên lỗi không bị bỏ qua do chưa bật `-ea`. Cần chạy lại trên **runtime JDK thực tế** của ứng dụng, đặc biệt nếu phiên bản Unicode hoặc hành vi phân đoạn emoji ảnh hưởng trực tiếp đến sản phẩm.

## 8. Thiết kế bộ kiểm thử cho dự án thực tế

Bên cạnh ví dụ chạy độc lập, nên đưa dữ liệu kiểm thử theo **nhóm trường hợp**:

| Nhóm | Test input gợi ý | Bất biến cần xác minh |
| --- | --- | --- |
| Chữ Việt có dấu ghép sẵn | `"Tiếng Việt"`, `"Nguyễn"`, `"Trường"`, `"ắ"`, `"ộ"` | Sau đọc/ghi UTF-8, nội dung không mất dấu, không biến ký tự thành `?` hoặc `U+FFFD`. |
| Dấu kết hợp | `"ắ"` và `"a\u0306\u0301"` | Raw `equals` khác; sau chuẩn hóa NFC thì bằng nhau. |
| Emoji đơn ngoài BMP | `"🙂"` | `length==2`, `codePointCount==1`, UTF-8 có 4 byte; không cắt lẻ surrogate. |
| Emoji ZWJ | `"👩‍💻"` | Ba code point, một grapheme cluster trên JDK được kiểm thử. |
| Quốc kỳ | `"🇻🇳"` | Hai regional indicators, một grapheme cluster trên JDK được kiểm thử. |
| Dữ liệu hỏng | Byte `C3 28`, hoặc `String` có high surrogate đơn | Có phương án từ chối hoặc xử lý tường minh; không làm mất dữ liệu âm thầm. |
| Trường hợp biên | `""`, chuỗi chỉ dấu kết hợp, xuống dòng, chuỗi có ASCII lẫn emoji | Không lỗi chỉ số, không giả định mọi phần tử dài đúng một `char`. |

Nếu đã dùng **JUnit 5** trong dự án, chuyển các hàm `check` thành `assertTrue`/`assertEquals` tương ứng và cấu hình pipeline chạy chúng trên JDK hỗ trợ. Đoạn chương trình ở mục 7 dùng `main` để người học có thể chạy ngay, không cần cài framework kiểm thử.

Khi thử chức năng nhập liệu, tìm kiếm, cắt chữ hoặc lưu database, kiểm tra cả **chuỗi trước/sau thao tác**, **byte encoding khi vượt biên hệ thống**, và **các đơn vị ký tự** mà logic sử dụng. Kiểm thử bằng mắt qua màn hình chỉ chứng minh cách font đang hiển thị; nó không đủ xác minh byte, code point hoặc chuẩn hóa.

## 9. Lỗi phổ biến và hướng sửa

1. **Dùng `charAt` hoặc `substring` với giả định một emoji dài một `char`:** có thể cắt rời surrogate. Dùng `codePointAt`/`offsetByCodePoints`; nếu thao tác theo cụm hiển thị, xử lý grapheme.
2. **Dùng `length()` để giới hạn “số ký tự” người dùng nhập:** giới hạn đó đang tính UTF-16 code unit. Định nghĩa rõ giới hạn tính theo byte UTF-8, code point hay grapheme cluster.
3. **So sánh hai cách viết chữ Việt có dấu bằng `equals` rồi cho là khác văn bản:** kiểm tra NFC/NFD và chuẩn hóa có chủ đích trước khi so sánh.
4. **Nhầm UTF-8 với UTF-16:** Java `String` dùng chỉ số UTF-16 nhưng byte truyền/ghi có thể được mã hóa UTF-8. Hai bộ biểu diễn có quy tắc độ dài khác nhau.
5. **Cho rằng `codePointCount` tự kiểm tra tính hợp lệ:** surrogate đơn lẻ vẫn có thể được đếm; cần kiểm tra cặp surrogate nếu đầu vào đòi UTF-16 well-formed.
6. **Chỉ thử emoji đơn, bỏ qua ZWJ và quốc kỳ:** xử lý code point đúng vẫn có thể tách rời một cụm hiển thị có nhiều code point.
7. **Dựa vào encoding mặc định:** kết quả có thể thay đổi theo môi trường; chỉ rõ UTF-8 khi biên dịch, đọc/ghi và trao đổi byte.
8. **Dùng `new String(bytes, UTF_8)` và coi mọi đầu vào đều hợp lệ:** nếu yêu cầu phát hiện dữ liệu lỗi, dùng `CharsetDecoder` với `REPORT`.
9. **Giả định chuỗi đã được Java tự chuẩn hóa Unicode:** `String` không tự biến NFD thành NFC; gọi `Normalizer.normalize` khi yêu cầu nghiệp vụ cần.
10. **Coi grapheme là một glyph cố định:** `\X` kiểm tra ranh giới cụm theo Unicode, nhưng kết quả vẽ còn phụ thuộc font/OS; tăng phạm vi kiểm thử UI khi chức năng cần đúng cách hiển thị.

## 10. Tài liệu chính thức còn hiệu lực

- [Java SE 27 — `String` API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): `length`, `codePointCount`, `codePointAt`, `offsetByCodePoints` và mô hình UTF-16.
- [Java SE 27 — `Character` API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html): Unicode code point, high/low surrogate, cặp surrogate và `isSurrogatePair`.
- [Java SE 26 — `Pattern` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): `\X` là Unicode extended grapheme cluster.
- [Java SE — `Normalizer` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): NFC, NFD, NFKC, NFKD.
- [Unicode Consortium — FAQ: Normalization](https://unicode.org/faq/normalization.html): vì sao biểu diễn Unicode tương đương cần chuẩn hóa.

Bộ kiểm thử này sử dụng các API Unicode/UTF-8 hiện hành của Java, không dựa vào phiên bản preview hay API đã ngừng hỗ trợ.