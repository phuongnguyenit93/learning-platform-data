# Không cắt chuỗi byte hoặc char tùy ý giữa một ký tự

## 1. Vấn đề: một ký tự nhìn thấy không nhất thiết là một byte hay một `char`

Trong Java I/O, tệp và kết nối truyền **byte**, còn `String`, `Reader`, `Writer` làm việc với dữ liệu ký tự. Khi chuyển văn bản thành byte (encoding), một ký tự Unicode có thể cần nhiều byte. Khi biểu diễn văn bản trong `String` Java (UTF-16), một Unicode code point cũng có thể cần **hai `char`**.

Do đó, câu “cắt một đoạn dài N ký tự” cần làm rõ đơn vị muốn đếm:

1. **Byte**: đơn vị lưu trữ/truyền dữ liệu; trong UTF-8 một Unicode code point có thể chiếm 1–4 byte.
2. **UTF-16 code unit**: một giá trị `char` trong Java, dài 16 bit; một code point ngoài BMP chiếm hai code unit.
3. **Unicode code point**: giá trị Unicode (ví dụ U+1F600 cho 😀); một code point có thể chiếm một hoặc hai `char`.
4. **Grapheme cluster**: một cụm người đọc nhìn như một ký tự, đôi khi gồm nhiều code point (ví dụ chữ `e` kết hợp dấu sắc, hoặc emoji ghép bằng ZWJ).

Nếu cắt ở vị trí bất kỳ, chương trình có thể chia đôi byte UTF-8, tách một cặp surrogate UTF-16, hoặc giữ code point nguyên vẹn nhưng vẫn cắt giữa một **cụm ký tự hiển thị**.

### Minh họa với `A😀B`

| Biểu diễn | Các đơn vị | Độ dài |
| --- | --- | ---: |
| Unicode code point | `A` · `😀` · `B` | 3 code point |
| Java UTF-16 `char` | `0041` · `D83D` · `DE00` · `0042` | 4 code unit |
| UTF-8 byte (hex) | `41` · `F0 9F 98 80` · `42` | 6 byte |

Chữ `A` chiếm một byte UTF-8 và một `char`; emoji 😀 chiếm **bốn byte UTF-8** và **hai `char` UTF-16**. Vì vậy:

- Cắt mảng UTF-8 sau byte `F0`, `9F` hoặc `98` sẽ chia dở chuỗi mã hóa của emoji.
- `"A😀B".substring(0, 2)` giữ `A` cùng **nửa đầu** cặp surrogate; kết quả là chuỗi UTF-16 không hợp lệ về cấu trúc cặp.
- `"A😀B".substring(0, 3)` giữ được hai code point `A` và 😀 nguyên vẹn.

Đây là nguyên tắc áp dụng cho mọi thao tác đọc theo block, gửi từng packet, giới hạn kích thước trường dữ liệu, chia chunk, rút gọn nội dung hoặc cắt `String`.

## 2. Vì sao UTF-8 không được cắt ở offset byte bất kỳ?

UTF-8 là mã hóa độ dài thay đổi: code point ASCII dùng một byte, nhiều ký tự tiếng Việt thường dùng 2–3 byte, và code point ngoài BMP như 😀 dùng bốn byte. Một byte mở đầu cho biết độ dài chuỗi mã hóa; các byte tiếp theo là **continuation byte**, có dạng bit `10xxxxxx`.

Ví dụ emoji 😀 (U+1F600):

```text
Unicode code point:    U+1F600
UTF-8 đầy đủ:          F0 9F 98 80
Cắt sau 1 byte:        F0 | 9F 98 80
Cắt sau 2 byte:        F0 9F | 98 80
Cắt sau 3 byte:        F0 9F 98 | 80
Ranh giới hợp lệ:      | F0 9F 98 80 |
```

Với ba cách cắt sai, cả hai mảnh riêng lẻ không còn là chuỗi UTF-8 hợp lệ tương ứng với emoji ban đầu. Nếu giải mã **riêng từng mảnh** rồi nối các `String`, decoder có thể trả ký tự thay thế `U+FFFD` (�), báo lỗi hoặc bỏ dữ liệu tùy cách cấu hình. Nối byte **trước khi giải mã** thì có thể khôi phục nguyên vẹn vì các byte chưa bị biến đổi.

**Quy tắc:** Ranh giới chunk **truyền/đọc byte** có thể nằm ở mọi vị trí, miễn là bộ giải mã giữ được trạng thái và các byte còn dở; ranh giới **văn bản đã được giải mã độc lập** thì phải tôn trọng mã hóa. Không thể áp đặt rằng mỗi lần `InputStream.read(byte[])` sẽ dừng ở cuối một Unicode code point: `InputStream` không biết charset.

### Chỉ nhìn bit `10xxxxxx` chưa đủ để kiểm tra văn bản

Trong dữ liệu UTF-8 **được xác nhận hợp lệ**, một offset nằm ngay trước byte mở đầu (hoặc EOF) là ứng viên ranh giới code point. Nhưng việc tìm byte không có dạng continuation **không thay thế một bộ giải mã có kiểm tra**: đầu vào vẫn có thể bị overlong encoding, surrogate được mã hóa trái phép, code point ngoài phạm vi Unicode hoặc thiếu byte cuối. Khi xử lý dữ liệu không tin cậy, hãy dùng `CharsetDecoder` có chính sách lỗi rõ ràng.

## 3. UTF-16 trong Java: `char` không phải luôn là một ký tự hoàn chỉnh

Java `String` được truy cập bằng **UTF-16 code unit**:

- `String.length()` là số code unit UTF-16, **không phải** số code point hay số ký tự hiển thị.
- `String.charAt(index)`, `substring(begin, end)`, `StringBuilder.delete(...)` và mảng `char[]` làm việc theo **chỉ số code unit**.
- Với code point từ U+10000 đến U+10FFFF, UTF-16 dùng **surrogate pair**: high surrogate (`D800–DBFF`) rồi low surrogate (`DC00–DFFF`).
- Một `char` surrogate riêng lẻ không phải Unicode scalar value hợp lệ; mã hóa nó độc lập có thể gây thay thế ký tự hoặc báo lỗi.

Ví dụ:

```java
String text = "A😀B";
System.out.println(text.length());                       // 4 UTF-16 units
System.out.println(text.codePointCount(0, text.length())); // 3 code points
```

Đây là một **đoạn minh họa trong ngữ cảnh**: hai dòng lần lượt in `4` và `3`. Để xử lý nguyên từng code point, nên dùng `codePointAt`, `codePointBefore`, `offsetByCodePoints`, `codePoints()`, `Character.charCount` và `StringBuilder.appendCodePoint`.

### Tại sao `substring` không tự bảo vệ cặp surrogate?

`substring(begin, end)` nhận offset theo code unit nên Java cho phép tạo một `String` kết thúc bằng high surrogate đơn lẻ. Điều đó không khiến chương trình Java lập tức lỗi. Lỗi thường xuất hiện **sau đó**: khi mã hóa sang UTF-8, ghi tệp, truyền mạng, áp dụng thuật toán yêu cầu văn bản Unicode hợp lệ, hoặc hiển thị.

Mã dưới đây có nguy cơ làm hỏng văn bản:

```java
// Sai về ý nghĩa “giữ hai code point đầu tiên”.
String result = "A😀B".substring(0, 2);
```

Nếu cần lấy **hai code point đầu tiên**, xác định ranh giới UTF-16 bằng `offsetByCodePoints`:

```java
String text = "A😀B";
int end = text.offsetByCodePoints(0, 2);
String firstTwoCodePoints = text.substring(0, end); // "A😀"
```

`String.offsetByCodePoints` giúp bước đi qua cặp surrogate hoàn chỉnh; tuy nhiên nếu chuỗi đầu vào **đã chứa surrogate lẻ**, hãy xác thực dữ liệu trước khi coi nó là văn bản Unicode hợp lệ.

## 4. Ví dụ Java 17: cắt sai và cắt đúng

Chương trình chạy độc lập bên dưới minh họa cả ranh giới byte UTF-8 lẫn code unit UTF-16, với output không phụ thuộc font console.

**Tệp `UnicodeBoundaryDemo.java`** (lưu mã nguồn UTF-8):

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class UnicodeBoundaryDemo {
    public static void main(String[] args) {
        String text = "A😀B";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 hex: "
                + HexFormat.of().withUpperCase().formatHex(bytes));
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));

        // Cắt sau hai UTF-16 code unit: A + high surrogate.
        String wrongCharPrefix = text.substring(0, 2);
        System.out.println("Ends with high surrogate: "
                + Character.isHighSurrogate(
                        wrongCharPrefix.charAt(wrongCharPrefix.length() - 1)));

        // Cắt đúng sau hai Unicode code point: A + emoji.
        int safeEnd = text.offsetByCodePoints(0, 2);
        String left = text.substring(0, safeEnd);
        String right = text.substring(safeEnd);
        System.out.println("Safe substring round-trip: "
                + (left + right).equals(text));

        // Cắt sau byte số 3: A + hai byte đầu của emoji bốn byte.
        byte[] invalidPrefix = Arrays.copyOfRange(bytes, 0, 3);
        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidPrefix));
        } catch (CharacterCodingException expected) {
            rejected = true;
        }
        System.out.println("Incomplete UTF-8 rejected: " + rejected);
        System.out.println("Full UTF-8 round-trip: "
                + text.equals(new String(bytes, StandardCharsets.UTF_8)));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Stdout chính xác:**

```text
UTF-8 hex: 41F09F988042
UTF-16 units: 4
Code points: 3
Ends with high surrogate: true
Safe substring round-trip: true
Incomplete UTF-8 rejected: true
Full UTF-8 round-trip: true
```

Tại sao decoder nghiêm ngặt báo lỗi trong ví dụ? Vì `CharsetDecoder.decode(ByteBuffer)` dạng tiện ích được gọi như một thao tác **giải mã toàn bộ input**, nên đoạn `A F0 9F` kết thúc khi sequence UTF-8 cho 😀 vẫn chưa đủ bốn byte. Đó là **dữ liệu cụt ở EOF**. Trong quá trình đọc streaming, một đoạn byte chưa hoàn chỉnh giữa các lần đọc **chưa phải EOF** và cần được giữ lại cho lần kế tiếp.

## 5. Đọc luồng byte thành text: phải mang trạng thái giải mã qua các lần đọc

Giả sử một luồng mạng trả hai byte đầu UTF-8 ở lần `read` thứ nhất, rồi trả hai byte còn lại ở lần sau. Luồng byte **không sai**: ranh giới các lần `read` là chi tiết truyền tải. Cách xử lý sai là:

```java
// Mã minh họa sai: chỉ có ý nghĩa nếu byteChunks là danh sách
// các khối byte nhận được từ I/O.
for (byte[] chunk : byteChunks) {
    text.append(new String(chunk, StandardCharsets.UTF_8));
}
```

Mỗi lần `new String(chunk, UTF_8)` tạo decoder mới, coi chunk là một văn bản UTF-8 **độc lập**. Nếu chunk dừng giữa byte sequence, thông tin dở dang không được nối sang lượt tiếp theo.

**Cách an toàn thông dụng:** bọc `InputStream` bằng **`InputStreamReader`** với `StandardCharsets.UTF_8` hoặc `CharsetDecoder` được cấu hình, rồi đọc `char[]`. Reader sẽ xử lý trạng thái giải mã giữa các lượt lấy byte từ luồng bên dưới. Có thể dùng `BufferedReader` cho đọc text theo dòng.

```java
// Đoạn minh họa, InputStream source đã mở và caller chuyển quyền sở hữu.
try (Reader reader = new InputStreamReader(source, StandardCharsets.UTF_8)) {
    char[] buffer = new char[2048];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Xử lý đúng buffer[0 .. count), tiếp tục cân nhắc surrogate.
    }
}
```

Reader **không tự biến mỗi mảng `char[]` thành một cụm ký tự hiển thị hoàn chỉnh**. Nó giải mã byte đúng thành code unit UTF-16, nhưng một cặp surrogate có thể bị tách ở ranh giới một `read(char[])`. Nếu chỉ sao chép và nối tất cả code unit theo đúng thứ tự, dữ liệu được giữ nguyên; nếu xử lý từng chunk **như một chuỗi Unicode độc lập**, vẫn phải kiểm soát các cặp surrogate ở ranh giới.

### Ví dụ chạy được: InputStream luôn trả tối đa một byte

Chương trình tạo luồng giả lập mà mỗi lần được yêu cầu đọc một mảng byte thì luồng chỉ cho tối đa **một byte**. Việc này cố ý khiến các byte UTF-8 của tiếng Việt và emoji bị chia rời.

**Tệp `FragmentedUtf8Read.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class FragmentedUtf8Read {
    static class OneByteAtATime extends FilterInputStream {
        OneByteAtATime(InputStream delegate) {
            super(delegate);
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (len == 0) {
                return 0;
            }
            return in.read(b, off, Math.min(len, 1));
        }
    }

    public static void main(String[] args) throws IOException {
        String original = "Hà Nội 😀";
        byte[] sourceBytes = original.getBytes(StandardCharsets.UTF_8);
        StringBuilder restored = new StringBuilder();

        try (Reader reader = new InputStreamReader(
                new OneByteAtATime(new ByteArrayInputStream(sourceBytes)),
                StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                restored.append(buffer, 0, count);
            }
        }

        System.out.println("Round-trip equal: "
                + original.contentEquals(restored));
        System.out.println("Unicode code points equal: "
                + (original.codePointCount(0, original.length())
                == restored.codePointCount(0, restored.length())));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FragmentedUtf8Read.java
java FragmentedUtf8Read
```

**Stdout chính xác:**

```text
Round-trip equal: true
Unicode code points equal: true
```

Mỗi lần một mảng byte được đọc từ nguồn đều có thể trả một byte; `InputStreamReader` vẫn giải mã thành Unicode đúng nhờ giữ trạng thái decoder. `StringBuilder.append(buffer, 0, count)` nối **đúng số `char` đã nhận** và giữ thứ tự. Trong ví dụ, ta không giải mã mỗi byte riêng lẻ và cũng không mã hóa độc lập mỗi khối `char[]`.

## 6. Xử lý từng code point từ Reader khi không được tách cặp surrogate

Một số thuật toán cần xử lý từng code point, chẳng hạn kiểm tra ký tự được phép, phân loại Unicode, hoặc tự xây dựng các đoạn logic theo code point. Khi đó đọc **một `char`** rồi coi đó là toàn bộ code point sẽ sai nếu gặp emoji hoặc một code point khác ngoài BMP.

Cần đọc và ghép high surrogate với low surrogate liền sau:

```java
static int nextCodePoint(Reader reader) throws IOException {
    int first = reader.read();
    if (first == -1) {
        return -1; // EOF
    }

    char ch = (char) first;
    if (Character.isLowSurrogate(ch)) {
        throw new IOException("Unexpected low surrogate");
    }
    if (!Character.isHighSurrogate(ch)) {
        return first;
    }

    int second = reader.read();
    if (second == -1 || !Character.isLowSurrogate((char) second)) {
        throw new IOException("Broken surrogate pair");
    }
    return Character.toCodePoint(ch, (char) second);
}
```

Đây là **phương thức minh họa**, cần import `java.io.Reader`, `java.io.IOException`; chưa phải chương trình độc lập. Nó trả `-1` ở EOF và một code point hợp lệ ở các lần khác. Trong nhánh high surrogate, lời gọi đọc tiếp là bắt buộc để biết cặp có hợp lệ hay không. Nếu dữ liệu có low surrogate lẻ hoặc high surrogate không đi cùng low surrogate, ví dụ chọn **báo lỗi** thay vì âm thầm thay ký tự.

Nếu đã có `String` trong bộ nhớ và biết nó là văn bản Unicode hợp lệ, thường chỉ cần dùng `String.codePoints()` hoặc `offsetByCodePoints`, không cần tự viết bộ lặp.

## 7. Cắt String theo số code point, không lấy `substring(0, n)` một cách mù quáng

`String.substring(0, n)` lấy **n UTF-16 code unit**, trong khi mô tả “lấy n code point” là ý nghĩa khác. Một hàm cắt theo code point có thể viết như sau:

```java
// Hàm trong ngữ cảnh: cần String value và số lượng n phù hợp.
static String prefixByCodePoints(String value, int n) {
    int count = value.codePointCount(0, value.length());
    if (n < 0 || n > count) {
        throw new IllegalArgumentException("Invalid code-point count");
    }
    int end = value.offsetByCodePoints(0, n);
    return value.substring(0, end);
}
```

Hàm này không chia đôi **cặp surrogate được ghép đúng**. Nhưng `codePointCount` và `offsetByCodePoints` vẫn có thể bước qua surrogate lẻ như một code point riêng biệt theo quy tắc API; vì vậy nếu tính hợp lệ Unicode là điều kiện bảo mật/dữ liệu, hãy xác thực chuỗi trước.

Khi chia String thành nhiều đoạn, nên xác định **mỗi ranh giới theo code point** rồi lấy các đoạn `substring(start, end)`. Không tính toán offset theo `index += n` code unit và cũng không lấy `text.length() / parts` rồi cắt trực tiếp.

### Ranh giới code point vẫn chưa là ranh giới ký tự hiển thị

Ví dụ chữ `é` có thể được biểu diễn bằng **hai code point**: `e` (U+0065) + dấu sắc kết hợp (U+0301). Nếu chia sau `e`, cả hai code point vẫn hợp lệ, nhưng dấu có thể bị bỏ lại đầu đoạn kế tiếp. Một emoji gia đình nối bằng zero-width joiner (ZWJ) hoặc một biểu tượng lá cờ cũng có thể gồm nhiều code point.

Nếu yêu cầu là “không cắt giữa một ký tự mà người dùng nhìn thấy”, đơn vị cần giữ nguyên là **extended grapheme cluster**, không chỉ Unicode code point. Java có `BreakIterator.getCharacterInstance(locale)` cho các quy tắc ngắt ký tự; tuy nhiên cần kiểm tra khả năng tương thích Unicode/emoji của **phiên bản JDK cụ thể**. Khi ứng dụng phụ thuộc chính xác vào các cụm emoji hiện đại, có thể dùng thư viện segmentation tuân theo Unicode UAX #29 và kiểm thử từng tổ hợp (ví dụ ICU4J). Đừng khẳng định chỉ dùng `codePoints()` là đủ cho mọi thao tác cắt chữ trên giao diện.

## 8. Khi trường dữ liệu giới hạn số byte UTF-8: tính theo từng code point

Một lỗi hay gặp là giới hạn payload “tối đa 5 byte” rồi cắt `Arrays.copyOf(utf8, 5)` mà không biết byte thứ năm có đang nằm trong một sequence hay không. Thay vào đó, với **văn bản Unicode hợp lệ**, duyệt từng code point, tính số byte sau mã hóa UTF-8 và chỉ thêm cả code point khi đủ ngân sách.

**Tệp `Utf8ByteBudget.java`:**

```java
import java.nio.charset.StandardCharsets;

public class Utf8ByteBudget {
    static String prefixWithinUtf8Bytes(String text, int maxBytes) {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Negative byte budget");
        }

        StringBuilder result = new StringBuilder();
        int used = 0;

        for (int offset = 0; offset < text.length();) {
            int codePoint = text.codePointAt(offset);
            // Không chấp nhận một surrogate đơn lẻ.
            if (codePoint >= Character.MIN_SURROGATE
                    && codePoint <= Character.MAX_SURROGATE) {
                throw new IllegalArgumentException("Unpaired surrogate");
            }

            String single = new String(Character.toChars(codePoint));
            int byteCount = single.getBytes(StandardCharsets.UTF_8).length;

            if (byteCount > maxBytes - used) {
                break;
            }
            result.appendCodePoint(codePoint);
            used += byteCount;
            offset += Character.charCount(codePoint);
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String text = "A😀B";
        String at3 = prefixWithinUtf8Bytes(text, 3);
        String at5 = prefixWithinUtf8Bytes(text, 5);
        String at6 = prefixWithinUtf8Bytes(text, 6);

        System.out.println("Budget 3 bytes: "
                + at3.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("Budget 5 bytes: "
                + at5.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("Budget 6 bytes: "
                + at6.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("Budget 5 is A+emoji: " + at5.equals("A😀"));
        System.out.println("Budget 6 is all text: " + at6.equals(text));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Utf8ByteBudget.java
java Utf8ByteBudget
```

**Stdout chính xác:**

```text
Budget 3 bytes: 1
Budget 5 bytes: 5
Budget 6 bytes: 6
Budget 5 is A+emoji: true
Budget 6 is all text: true
```

Vì `A` chiếm một byte và 😀 chiếm bốn byte, ngân sách ba byte chỉ giữ `A`; ngân sách năm byte giữ `A😀`; ngân sách sáu byte giữ cả `A😀B`. Hàm này giữ **prefix liên tục**: nếu code point tiếp theo không còn đủ chỗ thì dừng, chứ không bỏ qua nó để lấy ký tự ở phía sau.

Mã cố ý thiên về dễ hiểu: tạo một `String` và mảng byte tạm cho từng code point có thể tốn thời gian/bộ nhớ với chuỗi rất dài. Khi tối ưu, có thể viết bộ đếm số byte UTF-8 dựa trên dải code point đã xác thực hoặc dùng `CharsetEncoder` với buffer giới hạn. Tuyệt đối không tối ưu bằng cách cắt mảng byte ở vị trí bất kỳ rồi hy vọng decoder tự sửa.

**Lưu ý phạm vi:** hàm này giữ nguyên từng Unicode code point, nhưng vẫn có thể cắt giữa **cụm grapheme** như chữ kèm combining mark. Nếu giới hạn byte đi cùng yêu cầu không tách ký tự hiển thị, trước hết phân đoạn theo grapheme rồi mã hóa/tính byte cho cả cụm.

## 9. Kỹ thuật giải mã streaming bằng CharsetDecoder

Khi làm việc ở tầng thấp (ví dụ một parser nhận `ByteBuffer` từ network), `CharsetDecoder` cho phép kiểm soát chính xác việc tiếp nhận dữ liệu chưa đủ byte:

```text
Chunk 1: [F0 9F]             -- chưa đủ UTF-8 cho 😀
                |
                v
    Decoder (endOfInput=false)
                |
    UNDERFLOW: giữ lại F0 9F
                |
                v
Chunk 2: [98 80] + bytes còn lại
                |
                v
    Decoder hoàn tất F0 9F 98 80 -> surrogate pair UTF-16
```

Các khái niệm quan trọng:

- `CharsetDecoder.decode(input, output, false)` có thể trả `CoderResult.UNDERFLOW` khi không còn byte đủ để tạo thêm ký tự; nếu input còn byte dở, **giữ lại** các byte đó và ghép với chunk sau.
- `CoderResult.OVERFLOW` nghĩa là buffer output hết chỗ; cần xử lý/giải phóng `CharBuffer` và gọi `decode` tiếp với byte còn lại.
- Khi thật sự đã đến EOF, gọi `decode(..., true)`, sau đó `flush(output)` theo vòng đời decoder để xử lý trạng thái cuối. Lúc này byte UTF-8 cụt mới được phân loại là malformed tùy chính sách lỗi.
- Sau một lần decode, `ByteBuffer.compact()` có thể dồn các byte chưa tiêu thụ về đầu buffer; sau đó ghi thêm byte mới và `flip()` trước lần decode tiếp.
- `onMalformedInput(CodingErrorAction.REPORT)` và `onUnmappableCharacter(CodingErrorAction.REPORT)` cho phép báo lỗi thay vì tự thay; hai lựa chọn còn lại của `CodingErrorAction` là `REPLACE` hoặc `IGNORE`.

Đoạn trên là **sơ đồ quy trình**, không phải code chương trình độc lập. Khi dùng decoder stateful, cần thực hiện đúng các bước `decode`/`flush`, phân biệt EOF thật với ranh giới chunk, và xử lý cả `UNDERFLOW` lẫn `OVERFLOW`. Đối với hầu hết tác vụ file text, dùng `InputStreamReader` với charset đúng đơn giản và ít rủi ro hơn.

### Khi dữ liệu không hợp lệ cần xử lý thế nào?

Nếu decoder được cấu hình `REPORT`, một UTF-8 sequence lỗi có thể gây `MalformedInputException` hoặc `UnmappableCharacterException`. Với `REPLACE`, ký tự thay thế có thể xuất hiện và **không thể khôi phục dữ liệu ban đầu** từ văn bản đã thay thế. Với `IGNORE`, dữ liệu lỗi có thể bị bỏ qua.

Tùy bối cảnh: log có thể chấp nhận `REPLACE` để tiếp tục hiển thị, còn tệp cấu hình, dữ liệu chữ ký hoặc hệ thống cần tính toàn vẹn thường nên dùng `REPORT` và ghi nhận lỗi. Đừng coi một chuỗi `String` hiện ra không có lỗi lập trình là bằng chứng bytes gốc đúng charset.

## 10. Ghi text theo chunk: đừng mã hóa nửa cặp surrogate một cách độc lập

Sai lầm đối xứng với lỗi giải mã byte là **mã hóa từng mảnh `String`/`char[]` bằng encoder mới** khi mảnh bị cắt giữa high surrogate và low surrogate:

```java
// Minh họa lỗi: giả sử halves được lấy tại offset char bất kỳ.
byte[] part1 = halves[0].getBytes(StandardCharsets.UTF_8);
byte[] part2 = halves[1].getBytes(StandardCharsets.UTF_8);
// Nối part1, part2 sẽ không nhất thiết bằng mã hóa cả chuỗi gốc.
```

Hai lời gọi `getBytes` tạo hai thao tác mã hóa hoàn chỉnh độc lập. Nếu `halves[0]` kết thúc bằng high surrogate và `halves[1]` mở đầu bằng low surrogate, mỗi thao tác chỉ thấy **nửa cặp**, có thể thay thế dữ liệu hoặc báo lỗi. Cách giải quyết là:

1. Nếu đã có cả `String`, dùng ranh giới `offsetByCodePoints` (hoặc grapheme khi cần) trước khi chia thành các đoạn cần mã hóa **độc lập**.
2. Nếu cần ghi một luồng text liên tục, giữ **một Writer/CharsetEncoder** trong suốt vòng đời luồng và đóng nó đúng cách; không liên tục tạo encoder mới từ mỗi chunk tùy ý.
3. Nếu chuyển dữ liệu từ `Reader` sang `Writer`, dùng một pipeline text liên tục; nếu xử lý mỗi chunk theo code point, mang một high surrogate còn dở sang chunk sau.
4. Nếu dữ liệu ban đầu là byte UTF-8 và chỉ cần chuyển tải, tốt nhất giữ nguyên byte và tránh giải mã rồi mã hóa lại không cần thiết.

Một writer liên tục có thể giữ trạng thái mã hóa; tuy nhiên đừng giả định `flush()` ở ranh giới ngẫu nhiên là đủ để kết thúc hợp lệ một nửa surrogate. Đối với encoder được quản lý thủ công, phải chỉ rõ khi nào thực sự kết thúc input (`endOfInput`) và khi nào còn ký tự ở lần sau.

## 11. Khi nào “được cắt” và khi nào “không được cắt”?

| Tác vụ | Có thể chia ở mọi offset không? | Nguyên tắc đúng |
| --- | --- | --- |
| Truyền byte UTF-8 qua socket thành nhiều lần ghi | Có, nếu bên nhận giữ liên tục và giải mã sau/decoder streaming | Ranh giới TCP/byte chunk không phải ranh giới ký tự |
| Lưu byte thô thành các block rồi nối lại nguyên thứ tự | Có | Không giải mã từng block như văn bản độc lập |
| Tạo nhiều file UTF-8 mà file nào cũng phải đọc độc lập | Không | Cắt tại ranh giới UTF-8 code point hoặc văn bản cao hơn |
| `substring` để giới hạn số code point | Không | `offsetByCodePoints` trước khi `substring` |
| Chia đoạn hiển thị trong UI mà không tách emoji ghép | Không, kể cả chỉ cắt theo code point | Cần ranh giới grapheme cluster |
| Đọc file text thành các `char[]` rồi ghép nguyên thứ tự | Có, nếu không làm hỏng/thay đổi từng mảng độc lập | `Reader` giải mã byte, ghép đủ code unit |
| Đếm giới hạn cột DB tính theo UTF-8 bytes | Không | Tính số byte mã hóa cho từng code point/cụm hợp lệ |
| Chia chunk để gửi từng `String.getBytes(UTF_8)` độc lập | Không, nếu cắt giữa surrogate | Cắt trước theo ranh giới an toàn, rồi mã hóa |
| Cần đúng cùng số byte sau copy | Có thể chia block ở vị trí bất kỳ | Dùng byte stream; không convert text vô cớ |

Nói cách khác, **không phải việc chia buffer tự nó là lỗi**. Lỗi là coi những mảnh chưa hoàn chỉnh của **một biểu diễn mã hóa** như các ký tự hoặc văn bản độc lập, hoặc biến đổi mảnh rồi mất thông tin cần để ghép lại.

## 12. Các lỗi phổ biến và cách phát hiện

### 12.1 Một ký tự bị thay bằng �

Nguyên nhân thường là giải mã một fragment UTF-8 không đầy đủ như một văn bản trọn vẹn hoặc chọn charset sai. Hãy kiểm tra byte gốc ở dạng hex, charset phía tạo dữ liệu và logic theo chunk. Dùng decoder `REPORT` trong kiểm thử để phát hiện lỗi sớm thay vì mặc định thay ký tự.

### 12.2 `String.length()` nhỏ/lớn khác với số chữ nhìn thấy

`String.length()` là số code unit UTF-16. Với emoji ngoài BMP, số này **lớn hơn số code point**; với chữ kết hợp dấu hoặc emoji ghép, **số code point còn có thể lớn hơn số grapheme**. Đừng dùng `length()` một mình để tính số ký tự hiển thị trong UI.

### 12.3 Chữ vẫn hiển thị đúng khi test ASCII, nhưng lỗi với tiếng Việt/emoji

ASCII là tập con của UTF-8 mà mỗi code point chỉ chiếm một byte và một UTF-16 code unit. Test `Hello` không bộc lộ lỗi ranh giới. Cần có dữ liệu kiểm thử chứa cả ASCII, chữ Việt có dấu, ký tự 2–3 byte, emoji bốn byte, combining mark và ranh giới chunk ngẫu nhiên.

### 12.4 Đọc char buffer nhỏ rồi xử lý từng mảng như “một câu hoàn chỉnh”

`Reader.read(char[])` chỉ trả số code unit thực đọc được, có thể kết thúc giữa một cặp surrogate. Giữ mảnh chưa hoàn chỉnh hoặc xử lý qua iterator code point có trạng thái; tránh gọi `new String(buffer, 0, count)` rồi mã hóa **mỗi mảnh độc lập** mà không kiểm tra ranh giới surrogate.

### 12.5 Dùng `CharsetDecoder.decode` độc lập cho từng ByteBuffer

Phương thức tiện ích `decode(ByteBuffer)` có ý nghĩa decode trọn input, nên một block bị cụt có thể gây lỗi cuối input. Nếu cần xử lý streaming, tái sử dụng decoder qua các chunk với `decode(..., false)` và chỉ kết thúc bằng `true` tại EOF thực. Đọc text thông thường nên dùng `InputStreamReader`.

### 12.6 Cắt tại code point nhưng vẫn bể glyph trên màn hình

Từ có combining mark, emoji ZWJ hoặc emoji lá cờ có thể chứa nhiều code point trong một grapheme. Tách tại code point boundary vẫn có thể chia một ký tự hiển thị. Với yêu cầu UI, cần phân đoạn grapheme theo thuật toán Unicode thích hợp.

## 13. Chiến lược kiểm thử ranh giới và tính toàn vẹn

Khi triển khai hệ thống I/O text hoặc API chia chunk, nên kiểm tra **bất biến** thay vì chỉ nhìn bằng mắt:

- **Bất biến byte:** đối với thao tác chỉ chia/gom byte, `Arrays.equals(originalBytes, joinedChunks)` phải là `true`.
- **Bất biến văn bản:** đối với input UTF-8 hợp lệ, giải mã liên tục theo cùng charset phải tái tạo đúng chuỗi gốc: `original.equals(decoded)`.
- **Bất biến cặp surrogate:** các `String` con được tuyên bố là Unicode hợp lệ không được kết thúc bằng high surrogate lẻ hay bắt đầu bằng low surrogate lẻ.
- **Bất biến ngân sách byte:** `prefix.getBytes(UTF_8).length <= maxBytes`, đồng thời `prefix` phải là prefix liên tục của input theo đơn vị đã chọn.
- **Bất biến cụm hiển thị:** với yêu cầu giao diện, không chia giữa grapheme cluster, bao gồm trường hợp combining mark và emoji phức hợp.
- **Bất biến EOF:** chunk tạm thời hết byte không đồng nghĩa đã kết thúc stream; chỉ gọi decoder end-of-input khi có EOF thật.

Test ranh giới quan trọng nhất là cắt **ngay sau từng byte** của các chuỗi UTF-8 nhiều byte và **ngay giữa high/low surrogate**. Với `A😀B`, hãy thử mọi vị trí cắt từ byte 1 đến byte 5 và từ UTF-16 offset 1 đến 3; so sánh việc giải mã riêng từng mảnh với giải mã trên luồng được ghép.

Với dữ liệu không tin cậy, thêm ca UTF-8 malformed: byte continuation thiếu starter, starter thiếu continuation, chuỗi overlong, surrogate code point và code point ngoài dải hợp lệ. `CharsetDecoder` ở chế độ `REPORT` giúp kiểm tra phản ứng nhất quán trước lỗi.

## 14. Bài tập thực hành

1. Với chuỗi `"Xé😀Y"`, hãy ghi ra `length()`, `codePointCount(0, length())` và số byte UTF-8. Giải thích vì sao các con số khác nhau.
2. Tự cắt byte UTF-8 của emoji 😀 ở ba vị trí sai, giải mã từng đoạn bằng `new String(bytes, UTF_8)`, quan sát ký tự thay thế, rồi thử nối **byte** trước khi giải mã.
3. Dùng `String.offsetByCodePoints(0, n)` viết hàm lấy `n` code point đầu, sau đó kiểm thử với chữ Việt, emoji và ký tự kết hợp dấu.
4. Sửa ví dụ `FragmentedUtf8Read` để tạo mỗi lần đọc tối đa hai byte. Kiểm tra `Round-trip equal: true` vẫn giữ nguyên.
5. Sửa `Utf8ByteBudget` cho các ngân sách 0, 1, 4, 5 và 6 byte; viết assertion rằng đoạn trả về luôn giải mã UTF-8 đúng.
6. Xây dựng ví dụ chứa `"e\u0301"` (chữ `e` và combining acute accent). Hãy giải thích vì sao cắt theo một code point vẫn không bảo toàn cụm ký tự hiển thị.
7. Giả sử một hệ thống gửi nội dung UTF-8 qua network theo các chunk không cố định. So sánh ba cách: giải mã từng chunk bằng `new String`, gom toàn bộ byte rồi giải mã một lần, và dùng `InputStreamReader`/decoder streaming. Chọn cách phù hợp khi nội dung có thể rất lớn.
8. Cho `byte[]` chứa dữ liệu UTF-8 sai. Viết phương thức trả lỗi khi gặp byte sai bằng `newDecoder().onMalformedInput(REPORT)`, rồi giải thích vì sao cách này giúp tránh âm thầm mất dữ liệu.

## 15. Ghi nhớ và tài liệu đọc thêm

Điểm cốt lõi không phải tránh mọi phép chia buffer, mà là **giữ đúng ranh giới của đơn vị cần xử lý**:

1. **Byte stream** được phép chia thành các block bất kỳ nếu ghép byte lại đúng thứ tự trước khi decode, hoặc dùng decoder giữ trạng thái.
2. **UTF-8 text độc lập** phải giữ nguyên từng chuỗi byte của code point; mảnh byte thiếu không phải một ký tự hoàn chỉnh.
3. **Java `char` là UTF-16 code unit**; không cắt đôi high/low surrogate khi muốn tách code point. Sử dụng `String.offsetByCodePoints`/`codePoints`.
4. **Ký tự hiển thị** có thể gồm nhiều code point; phân đoạn theo grapheme khi ứng dụng/UI cần không tách chữ mà người dùng nhìn thấy.
5. **Lỗi decoding/encoding** cần chính sách rõ ràng (`REPORT`, `REPLACE`, `IGNORE`) và kiểm thử đầu vào nhiều byte, không chỉ ASCII.

Tài liệu chính thức để tra cứu: [`String` trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [`Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html), và [Unicode Text Segmentation (UAX #29)](https://unicode.org/reports/tr29/).
