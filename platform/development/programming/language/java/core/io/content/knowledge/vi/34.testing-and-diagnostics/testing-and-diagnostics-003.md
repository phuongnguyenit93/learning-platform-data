# Kiểm tra nội dung byte chính xác và round-trip văn bản trong Java I/O

Khi kiểm thử thao tác đọc/ghi file, copy stream, encode/decode text hoặc giao tiếp qua socket, thông báo “không có exception” **chưa đủ chứng minh dữ liệu đúng**. Một tác vụ I/O có thể hoàn thành nhưng làm thiếu byte cuối, thêm BOM, đổi `\n` thành `\r\n`, dùng sai charset, thay ký tự không biểu diễn được hoặc vô tình chuẩn hóa văn bản. Những lỗi ấy có thể không dễ nhìn thấy khi chỉ mở file trong editor.

Bài học này phân biệt **kiểm tra byte-for-byte** và **kiểm tra round-trip văn bản**; hướng dẫn thiết kế assertions, golden fixtures, diagnostics bằng hexadecimal và offset sai lệch, sử dụng `Arrays.equals`, `Arrays.mismatch`, `Files.mismatch`, `HexFormat`, `StandardCharsets` và bộ `CharsetDecoder/CharsetEncoder` trong Java 17+. Mục tiêu không chỉ là kiểm tra “đọc lại được”, mà còn biết **đang chứng minh tính chất nào, có thể mất thông tin ở đâu và kiểm tra sai lệch ra sao**.

## 1. Ba yêu cầu đúng đắn thường bị nhầm lẫn

Hãy phân biệt ba câu hỏi:

| Yêu cầu | Điều phải so sánh | Ví dụ |
| --- | --- | --- |
| **Byte exactness** | Toàn bộ dãy byte nguồn và dãy byte đích phải giống nhau từng byte, cùng thứ tự, cùng độ dài. | Copy file nhị phân, chuyển bytes từ mạng vào file, lưu artifact bất biến. |
| **Text round-trip** | Văn bản `String` ban đầu, sau khi encode → write → read → decode, phải giống văn bản ban đầu theo **tiêu chí so sánh đã chọn**. | Lưu rồi đọc lại văn bản UTF-8. |
| **Logical equivalence** | Hai đối tượng/text có cùng ý nghĩa theo schema hoặc quy tắc canonicalization, dù raw bytes có thể khác. | JSON khác spacing, Unicode NFC/NFD, file có LF/CRLF theo policy. |

Ba tính chất không tự suy ra nhau. Một văn bản khi đọc có thể “nhìn đúng” nhưng byte khác; ngược lại, hai file giống byte hoàn toàn không chứng minh nội dung là UTF-8 hợp lệ hay đúng schema nghiệp vụ.

Sơ đồ:

```text
String ban đầu
      |
      | encode(StandardCharsets.UTF_8)
      v
Bytes dự kiến ------ so sánh byte-for-byte ------> Bytes đọc từ file
      |                                               |
      | write                                         | decode(UTF-8)
      v                                               v
   File / stream                                String đọc lại
                                                      |
                                             String.equals(original)
```

**Quy tắc thiết kế test:** trước khi viết assertion, phải quyết định cần **byte exactness**, **text equality** hay **logical equivalence**. Không nên thay một tiêu chí bằng tiêu chí yếu hơn chỉ vì dễ kiểm thử.

## 2. Byte-for-byte nghĩa là gì?

Cho hai dãy byte `A` và `B`, bằng nhau từng byte khi:

1. `A.length == B.length`; và
2. Với mọi index `i` từ 0 đến length - 1, `A[i] == B[i]`.

Các khác biệt dù chỉ một byte đều phải làm test thất bại:

```text
Expected:  41 42 43 0a          "ABC\n" UTF-8
Actual:    41 42 43 0d 0a       "ABC\r\n" UTF-8
                     ^
                Từ index 3 đã khác.
```

Đừng kiểm thử copy nhị phân bằng `String.equals` hoặc `Files.readString`: file PNG, ZIP, protobuf hoặc ciphertext không phải chuỗi ký tự. Việc decode bytes nhị phân rồi encode lại có thể làm thay đổi dữ liệu, thậm chí khi không ném exception.

Với dữ liệu nhỏ trong test:

```java
byte[] expected = {0x00, 0x01, (byte) 0xFF};
byte[] actual   = Files.readAllBytes(path);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Bytes differ");
}
```

Đây là **snippet** với `path` được khai báo ngoài, cần import `java.nio.file.Files`, `java.util.Arrays`. Ép `(byte) 0xFF` vì Java `byte` là kiểu signed -128..127, nhưng biểu diễn trên file vẫn là byte unsigned `FF`.

Một lỗi dễ mắc: `Arrays.toString(byte[])` hiển thị số signed, ví dụ byte `FF` thành `-1`. Khi cần phân tích ở cấp byte, in hexadecimal bằng `HexFormat` hoặc dùng `Byte.toUnsignedInt(byte)`.

## 3. Arrays.equals, Arrays.mismatch và Files.mismatch

Ba API giúp kiểm tra nhanh:

| API | Input | Output | Khi phù hợp |
| --- | --- | --- | --- |
| `Arrays.equals(byte[], byte[])` | Hai mảng trong RAM | `boolean` | Fixture nhỏ và dữ liệu đã được đọc đầy đủ. |
| `Arrays.mismatch(byte[], byte[])` | Hai mảng trong RAM | Index khác đầu tiên, hoặc `-1` nếu giống nhau | Chẩn đoán vị trí sai; nếu một mảng là prefix của mảng khác, index là độ dài mảng ngắn hơn. |
| `Files.mismatch(Path, Path)` | Hai file | Offset byte đầu tiên khác, hoặc `-1L` nếu giống nhau | So sánh file trực tiếp, tránh tự viết vòng readAllBytes cho file lớn. |

Ví dụ:

```java
byte[] expected = {1, 2, 3, 4};
byte[] actual = {1, 2, 9, 4};

System.out.println(Arrays.equals(expected, actual));  // false
System.out.println(Arrays.mismatch(expected, actual)); // 2
```

Đây là snippet. `Arrays.mismatch` và `Files.mismatch` có từ các bản JDK trước Java 17 và sử dụng được trong Java 17+. `Files.mismatch` có thể ném `IOException`; nếu file đang bị process khác sửa trong lúc kiểm tra, kết quả có thể không phản ánh một snapshot ổn định.

**Chú ý riêng `Files.mismatch`:** trả `-1L` khi nội dung byte giống nhau; trả offset **0-based** khi khác. Với file chỉ khác phần đuôi, kết quả có thể bằng vị trí ngay sau byte cuối của file ngắn hơn.

Đừng chỉ so `Files.size(source) == Files.size(target)`: hai file khác nội dung vẫn có thể cùng số byte. Đừng chỉ so timestamp hoặc tên file. Để chứng minh toàn bộ byte giống nhau, dùng so sánh bytes thực, hoặc digest của nguồn và đích phù hợp threat model.

## 4. Diagnostics bằng hex, offset và context

Nếu một bài kiểm thử chỉ báo `expected != actual`, việc debug sẽ khó khi file dài vài MB. Nên báo:

- Đường dẫn hoặc ID file (đã được lọc để không lộ thông tin nhạy cảm).
- Tổng độ dài expected/actual.
- **Offset byte đầu tiên sai**, tính từ 0.
- Một cửa sổ hex xung quanh offset, ví dụ 16 byte trước và sau.
- Charset/encoding, newline và BOM policy liên quan.
- Chú thích rằng dump là byte gốc, không phải ký tự “trông giống”.

Java 17 có `HexFormat`:

```java
byte[] bytes = {(byte) 0xEF, (byte) 0xBB, (byte) 0xBF};
System.out.println(HexFormat.of().formatHex(bytes)); // efbbbf
byte[] reconstructed = HexFormat.of().parseHex("efbbbf");
```

Snippet cần import `java.util.HexFormat`. Với dữ liệu nhạy cảm (token, private key, thông tin cá nhân), **không** log nguyên văn hex dump chỉ để debug: hex vẫn tiết lộ dữ liệu. Log offset, chiều dài và digest không bí mật theo chính sách; chỉ dump bytes nếu được phép và có cơ chế redact.

Ví dụ helper đưa ra lỗi có cấu trúc:

```java
static void assertExact(byte[] expected, byte[] actual) {
    int mismatch = Arrays.mismatch(expected, actual);
    if (mismatch >= 0) {
        throw new AssertionError(
                "Byte mismatch at offset=" + mismatch
                + "; expectedLength=" + expected.length
                + "; actualLength=" + actual.length);
    }
}
```

Đây là snippet trong class có import `java.util.Arrays`. Trong các bài test, helper này có thể được thay bằng `assertArrayEquals` của JUnit 5 và bổ sung hex context khi một case thất bại.

## 5. Charset phải được chỉ định tường minh

Khi chuyển giữa `String` và bytes, charset là một phần của hợp đồng dữ liệu:

```java
String original = "Tiếng Việt";
byte[] data = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);

if (!original.equals(restored)) {
    throw new AssertionError("Text round-trip failed");
}
```

Đây là snippet; `StandardCharsets.UTF_8` cung cấp charset cụ thể. Tránh các overload như `str.getBytes()` hoặc `new String(bytes)` khi định dạng dữ liệu cần tồn tại lâu hoặc di chuyển giữa máy: charset mặc định phụ thuộc môi trường/JDK. Đặc biệt với Java 17 và những bản JDK trước thay đổi mặc định charset của Java 18, cùng code không chỉ định charset có thể xử lý bytes khác trên các máy.

Một số charset phổ biến:

| Charset | Hợp đồng | Rủi ro khi dùng sai |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode biến độ dài, là lựa chọn mặc định phù hợp với dữ liệu text mới. | Dùng charset khác để decode sẽ gây mojibake hoặc lỗi. |
| `StandardCharsets.US_ASCII` | Chỉ mã hóa tập ASCII cơ bản. | Ký tự `đ`, `é`, emoji không biểu diễn được. |
| `StandardCharsets.ISO_8859_1` | Một byte cho các giá trị 0–255 của bảng mã đó. | Không chứa đầy đủ tiếng Việt hoặc emoji. |
| `UTF_16LE`/`UTF_16BE` | Mã hóa các UTF-16 code units theo thứ tự byte rõ ràng. | Dùng sai endian hoặc sai BOM protocol dẫn tới văn bản sai. |

**Không thể kết luận byte exactness chỉ từ** `String.equals`. Nếu code đã decode sai nhưng theo chính sách thay invalid bytes bằng ký tự thay thế, một phép so chuỗi vẫn không tìm lại được bytes gốc.

## 6. “Round-trip văn bản” có hai chiều cần kiểm tra riêng

### Chiều A: String → encode → decode → String

Với một chuỗi Java hợp lệ, charset có thể biểu diễn đầy đủ dữ liệu và không có bước biến đổi, ta mong đợi:

```text
originalText == decode(encode(originalText, charset), charset)
```

Với UTF-8 và dữ liệu Unicode hợp lệ, thao tác này thường bảo toàn chính xác chuỗi. Tuy nhiên, chuỗi Java có thể chứa **surrogate lẻ** (unpaired surrogate), vốn không phải Unicode scalar value hợp lệ; nếu dùng encoder có replacement policy, round-trip **có thể mất thông tin**. Hãy chọn chế độ báo lỗi khi format đòi strict encoding.

### Chiều B: raw bytes → decode → encode → raw bytes

Chiều này mạnh hơn:

```text
originalBytes == encode(decode(originalBytes, charset), charset)
```

Nó chỉ đúng khi byte sequence hợp lệ và phép giải mã/tái mã hóa theo protocol cho một biểu diễn byte tương ứng. Với invalid UTF-8, encoding lỗi, charset có nhiều biểu diễn, chính sách replacement hay canonicalization, không có bảo đảm raw bytes được tái tạo.

**Kiểm thử hai chiều khi thực sự cần cả hai**. Với file nhị phân, không có yêu cầu decode text thì chỉ so bytes. Với tài liệu chuẩn hóa theo policy, phải xác định tính tương đương logic thay vì đòi byte exactness.

## 7. Ví dụ Java 17+ chạy độc lập: file bytes, UTF-8 round-trip và các bẫy

Chương trình tự tạo file tạm, ghi văn bản có tiếng Việt, emoji và dấu newline. Nó copy file, kiểm tra bytes bằng `Arrays.equals` và `Files.mismatch`, sau đó đọc text rồi encode lại. Ví dụ cũng xác minh byte UTF-8 của `é`, so Unicode normalization, line ending và cơ chế từ chối UTF-8 lỗi.

Lưu đúng tên **`ByteExactRoundTripDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;

public class ByteExactRoundTripDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("roundtrip-source-", ".txt");
        Path copy = Files.createTempFile("roundtrip-copy-", ".txt");
        try {
            String text = "Tiếng Việt 😀\nDòng 2";
            byte[] expected = text.getBytes(StandardCharsets.UTF_8);

            Files.write(source, expected);
            Files.copy(source, copy,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            byte[] actual = Files.readAllBytes(copy);

            check(Arrays.equals(expected, actual), "Bytes changed");
            check(Files.mismatch(source, copy) == -1, "Files differ");

            String decoded = Files.readString(copy, StandardCharsets.UTF_8);
            check(text.equals(decoded), "Text changed");
            check(Arrays.equals(expected,
                    decoded.getBytes(StandardCharsets.UTF_8)),
                    "Re-encoding changed bytes");

            System.out.println("bytes-equal=true");
            System.out.println("files-mismatch=-1");
            System.out.println("text-roundtrip=true");
            System.out.println("reencode-equal=true");
            System.out.println("utf8-accent=" + HexFormat.of().formatHex(
                    "é".getBytes(StandardCharsets.UTF_8)));

            String composed = "café";
            String decomposed = "cafe\u0301";
            System.out.println("nfc-nfd-byte-equal=" + Arrays.equals(
                    composed.getBytes(StandardCharsets.UTF_8),
                    decomposed.getBytes(StandardCharsets.UTF_8)));
            System.out.println("nfc-nfd-normalized-equal=" +
                    Normalizer.normalize(composed, Normalizer.Form.NFC)
                            .equals(Normalizer.normalize(
                                    decomposed, Normalizer.Form.NFC)));

            System.out.println("lf-crlf-byte-equal=" + Arrays.equals(
                    "A\nB".getBytes(StandardCharsets.UTF_8),
                    "A\r\nB".getBytes(StandardCharsets.UTF_8)));

            boolean rejected = false;
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(
                                new byte[] {(byte) 0xC3, (byte) 0x28}));
            } catch (CharacterCodingException expectedError) {
                rejected = true;
            }
            check(rejected, "Malformed UTF-8 was accepted");
            System.out.println("malformed-rejected=true");
        } finally {
            Files.deleteIfExists(copy);
            Files.deleteIfExists(source);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 ByteExactRoundTripDemo.java
java ByteExactRoundTripDemo
```

Stdout đã được kiểm chứng bằng cách biên dịch và thực thi:

```text
bytes-equal=true
files-mismatch=-1
text-roundtrip=true
reencode-equal=true
utf8-accent=c3a9
nfc-nfd-byte-equal=false
nfc-nfd-normalized-equal=true
lf-crlf-byte-equal=false
malformed-rejected=true
```

**Giải thích từng bước:**

1. `text` chứa tiếng Việt và emoji ngoài BMP; `text.getBytes(UTF_8)` tạo chuỗi bytes theo mã hóa tường minh.
2. `Files.write(source, expected)` ghi bytes gốc; `Files.copy` sao chép sang file tạm khác. `Arrays.equals` so mảng bytes; `Files.mismatch == -1` xác nhận cả hai file có byte content giống nhau.
3. `Files.readString(copy, UTF_8)` đọc văn bản. `String.equals` kiểm tra sequence UTF-16 code units; phép encode lại kiểm tra được cùng bytes trong trường hợp UTF-8 hợp lệ này.
4. `"é"` theo UTF-8 là `C3 A9`; `HexFormat` cho `c3a9`.
5. `"café"` dùng ký tự `é` dựng sẵn, còn `"cafe\u0301"` dùng `e` + combining acute accent. Bytes khác, nhưng sau `Normalizer.normalize(..., NFC)` chúng so bằng nhau.
6. `"A\nB"` và `"A\r\nB"` khác bytes: `0A` so với `0D 0A`. Editor có thể hiển thị hai tệp như nhau, nên text rendering không đủ chứng minh byte equality.
7. Dãy byte `C3 28` không phải UTF-8 hợp lệ. `CharsetDecoder` với `CodingErrorAction.REPORT` báo lỗi để test phát hiện thay vì âm thầm thay bằng `U+FFFD`.
8. `finally` dọn hai file tạm. Demo dùng dữ liệu nhỏ; với file rất lớn nên tránh `Files.readAllBytes` để giới hạn memory.

**Bài học quan trọng:** ví dụ chứng minh **ba mệnh đề độc lập**: copy bytes nguyên vẹn, text round-trip đúng khi charset phù hợp và decoder strict từ chối input không hợp lệ. Không dùng kết quả một mệnh đề để thay assertion cho mệnh đề khác.

## 8. Kiểm tra bytes sau FileChannel hoặc stream có partial I/O

Với `InputStream.read(buffer)`, giá trị trả về là số byte **thực sự được đọc** hoặc `-1` ở EOF. Không giả định một lần `read` sẽ đổ đầy mảng, đặc biệt khi đọc socket, pipe hoặc dữ liệu dài.

Khi copy theo chunk, nguyên tắc:

```java
// Snippet: in và out là InputStream/OutputStream đã mở.
byte[] buf = new byte[8192];
for (int n; (n = in.read(buf)) != -1; ) {
    out.write(buf, 0, n);
}
```

Đoạn trên là snippet, cần xử lý `IOException` và `try-with-resources` ở caller. Với `InputStream` thông thường, `read(byte[])` có thể trả ít byte hơn `buf.length`; dùng `out.write(buf)` thay vì `out.write(buf,0,n)` sẽ ghi thêm các bytes cũ ở cuối mảng.

Với `FileChannel` và `ByteBuffer`:

```java
// Snippet: source và target là FileChannel,
// buffer có dung lượng > 0.
while (true) {
    int n = source.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        throw new IOException("Reading made no progress");
    }
    buffer.flip();
    while (buffer.hasRemaining()) {
        if (target.write(buffer) == 0) {
            throw new IOException("Writing made no progress");
        }
    }
    buffer.clear();
}
```

Đây là mẫu fail-fast cho file channel blocking trong ngữ cảnh do ứng dụng kiểm soát; **không** bê nguyên chính sách `n==0` sang `SocketChannel` non-blocking, nơi cần chờ readiness thay vì ném lỗi. Kiểm thử sau copy bằng `Files.mismatch` hoặc digest đáng tin có ý nghĩa thực tế hơn chỉ kiểm tra số byte đã gọi `write`.

Nếu code có dùng `ByteBuffer.array()`, chú ý mảng backing có thể lớn hơn vùng dữ liệu hợp lệ, buffer có thể là direct/read-only/sliced và không hỗ trợ `array()`. Dùng `position/limit/remaining` hoặc view đúng vùng, không giả định toàn bộ mảng luôn là payload.

## 9. Ký tự, code point, UTF-16 code units và số byte

Java `String` là chuỗi **UTF-16 code units**. Vì vậy:

- `String.length()` trả số code units, không phải số Unicode code points và không phải số byte UTF-8.
- Ký tự supplementary, ví dụ `😀`, chiếm **hai UTF-16 code units** và thường **bốn byte UTF-8**.
- Ký tự `é` dựng sẵn thường dài một code unit và hai byte UTF-8.
- Ký tự kết hợp có thể tạo một glyph từ nhiều code points/code units; số glyph hiển thị không bằng `String.length()`.

Ví dụ minh họa:

```java
String emoji = "😀";
System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length); // 4
```

Đây là snippet. Nếu protocol yêu cầu header ghi độ dài payload **theo byte**, dùng `data.length` của byte array đã encode, không dùng `str.length()`. Trong binary protocol, dùng byte count không đúng dẫn tới thiếu payload hoặc đọc quá phần dữ liệu tiếp theo.

Nếu muốn duyệt Unicode code points, cân nhắc `String.codePoints()`, nhưng ngay cả code point count cũng không bằng số grapheme clusters người dùng nhìn thấy. Với so sánh byte exactness, đơn vị phù hợp vẫn là **byte sequence**.

## 10. Unicode normalization: “nhìn như nhau” chưa chắc String.equals

Ví dụ biểu diễn chữ có dấu:

```text
NFC / composed: "é"           U+00E9        UTF-8 C3 A9
NFD / decomposed: "e◌́"        U+0065 U+0301 UTF-8 65 CC 81
```

Hai chuỗi có thể hiện giống nhau trong UI nhưng bytes khác, và Java `String.equals` cũng thường trả false vì các UTF-16 code units khác nhau. Nếu nghiệp vụ yêu cầu coi chúng tương đương theo Unicode canonical equivalence, cần **quy tắc normalize** rõ:

```java
String left = Normalizer.normalize(sourceText, Normalizer.Form.NFC);
String right = Normalizer.normalize(restoredText, Normalizer.Form.NFC);
boolean sameMeaningByPolicy = left.equals(right);
```

Đây là snippet với imports `java.text.Normalizer`, các biến string do ứng dụng cung cấp. Nên dùng **NFC** khi sản phẩm cần canonical normalization, nhưng việc normalize không phải luôn vô hại: nếu đang kiểm tra file raw, chữ ký số, protocol bytes, đường dẫn hoặc dữ liệu đòi byte-exact thì normalization thay đổi byte và **không được tự thực hiện**.

Các form `NFC`, `NFD`, `NFKC`, `NFKD` có mục đích khác nhau; compatibility normalization như NFKC có thể biến một số ký tự tương thích thành chuỗi khác về biểu diễn/ý nghĩa thị giác. Chọn theo hợp đồng, không dùng mặc định để “sửa lỗi encoding”.

## 11. Line endings và các API làm mất ranh giới dòng

Ba dạng line ending thường gặp:

| Dạng | Hex | Ứng dụng |
| --- | --- | --- |
| LF | `0A` | Thường dùng trong môi trường Unix/Linux và nhiều giao thức. |
| CRLF | `0D 0A` | Phổ biến trên Windows và một số protocol mạng. |
| CR | `0D` | Tồn tại trong dữ liệu cũ hoặc một số định dạng riêng. |

`BufferedReader.readLine()` trả nội dung dòng **không kèm ký tự kết thúc dòng**. Vì vậy việc đọc nhiều dòng bằng `readLine()` rồi ghi ra bằng `writer.newLine()` có thể thay đổi bytes của file gốc:

- File có `\n` nhưng máy đích tạo `\r\n`.
- File có hoặc không có newline ở cuối: phân biệt này có thể bị mất.
- Hai kiểu newline trộn lẫn trong cùng file không được bảo toàn.
- Các ranh giới CR/LF riêng có thể bị xử lý theo chính sách của reader.

Tương tự, các API dòng cao cấp như `Files.readAllLines` và `Files.lines` thích hợp cho xử lý **nội dung từng dòng**, nhưng không phải công cụ kiểm tra bảo toàn dấu ngắt dòng byte-for-byte.

Khi muốn giữ nguyên file, xử lý qua bytes hoặc bảo toàn chính xác các line separators. Khi nghiệp vụ muốn chuẩn hóa line ending, phải viết test riêng chứng minh **kết quả đã chuẩn hóa** và ghi rõ đây là chuyển đổi có chủ ý, không gọi đó là raw byte round-trip.

## 12. BOM và các byte vô hình ở đầu file

Một số text file có **Byte Order Mark (BOM)**. Ví dụ UTF-8 BOM là ba byte:

```text
EF BB BF
```

UTF-8 không cần BOM để xác định thứ tự byte; tuy nhiên một số phần mềm vẫn tạo file UTF-8 có BOM. Hai file có cùng nội dung ký tự hiển thị nhưng một file có BOM còn file kia không có **sẽ khác SHA-256, kích thước và byte exactness**.

Các điểm phải xác định:

1. Protocol có cho phép BOM không?
2. Parser có tự nhận diện/bỏ BOM không, hay coi nó là một code point `U+FEFF`?
3. Writer có luôn thêm BOM, luôn không thêm BOM, hay sao chép nguyên trạng?
4. UTF-16 sử dụng endian nào; có BOM hay đang chỉ định `UTF_16LE`/`UTF_16BE` rõ?

Nếu yêu cầu byte exactness, **BOM là dữ liệu cần kiểm tra như mọi byte khác**. Nếu yêu cầu semantic text round-trip, hai bên phải thống nhất quy tắc BOM trước khi so chuỗi. Không thêm hoặc bỏ BOM âm thầm chỉ vì editor của một hệ điều hành xử lý khác.

## 13. Strict decoding và lỗi dữ liệu không hợp lệ

Một số convenience API xử lý input malformed bằng **ký tự thay thế**, dẫn tới mất thông tin. Khi định dạng yêu cầu UTF-8 chính xác, nên dùng decoder có `CodingErrorAction.REPORT`:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    CharBuffer result = decoder.decode(ByteBuffer.wrap(bytes));
    String restored = result.toString();
} catch (CharacterCodingException invalid) {
    throw new IOException("Malformed UTF-8 input", invalid);
}
```

Đây là snippet, cần imports `java.nio.ByteBuffer`, `java.nio.CharBuffer`, `java.nio.charset.CharsetDecoder`, `java.nio.charset.CodingErrorAction`, `java.nio.charset.CharacterCodingException` và các biến phù hợp.

**Malformed** thường là chuỗi byte sai cấu trúc encoding; **unmappable** là dữ liệu không có biểu diễn ký tự hợp lệ theo charset. Với UTF-8, một ví dụ malformed là `C3 28`: byte `C3` yêu cầu byte continuation phù hợp nhưng byte kế là `28`.

Tương tự khi encode text sang charset không đủ ký tự:

```java
CharsetEncoder strictAscii = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
try {
    ByteBuffer encoded = strictAscii.encode(CharBuffer.wrap("Tiếng Việt"));
} catch (CharacterCodingException unsupported) {
    // Dữ liệu có ký tự không biểu diễn được trong ASCII.
}
```

Đây là snippet. `String.getBytes(Charset)` có thể thay ký tự không biểu diễn được/chuỗi sai bằng bytes replacement theo API, nên để **phát hiện dữ liệu lỗi** thay vì thay thế âm thầm hãy dùng `CharsetEncoder` strict như trên. Tránh vô tình “test passed” vì cả phía ghi lẫn đọc đã cùng dùng chính sách thay thế mất mát.

## 14. Golden fixtures và các trường hợp kiểm thử bắt buộc

Test tốt không chỉ round-trip cùng một hàm encode/decode; nếu cả hai đều mắc cùng một lỗi, chúng có thể tự xác nhận sai. Cần có **golden bytes độc lập** với code đang được kiểm thử.

Bộ fixture khuyến nghị:

| Fixture | Byte đặc trưng hoặc nội dung | Điều cần bắt lỗi |
| --- | --- | --- |
| Empty file | Không byte nào. | Không thêm BOM/newline/header ngoài dự kiến. |
| ASCII ngắn | `abc` = `61 62 63` | Dữ liệu đơn giản và content length. |
| Byte null | `00` nằm giữa payload. | Không coi null là kết thúc chuỗi C-style. |
| Byte cao | `80 FF` | Signed byte, không decode text nhầm. |
| UTF-8 dấu tiếng Việt | `đ, ế, ộ` | Charset sai / replacement. |
| Emoji supplementary | `😀` | Surrogate pairs và byte count. |
| NFC so NFD | `C3 A9` so `65 CC 81` | Visual equality không đồng nghĩa byte equality. |
| LF và CRLF | `0A` so `0D 0A` | Line ending rewrite. |
| Có/không BOM | `EF BB BF` trước text | BOM policy. |
| Malformed UTF-8 | `C3 28` hoặc truncated multibyte | Strict decoder phải từ chối. |
| Unpaired UTF-16 surrogate | Ví dụ một high surrogate không có low surrogate | Strict encoder phải từ chối. |
| Nhiều chunk | Dữ liệu dài hơn buffer, chunk cuối ngắn | Partial reads và stale bytes. |
| File nhị phân thật | PNG/ZIP fixture nhỏ đã xác minh | Không dùng String làm trung gian. |
| File lớn | Nhiều MiB/GB theo hạ tầng test | Streaming, memory, timeout, chính sách bảo vệ. |

Đối với fixture tính bằng hex, tạo bytes kỳ vọng bằng `HexFormat.parseHex` từ một chuỗi đã được review hoặc chuẩn protocol. Tránh tạo expected bằng chính API encode bạn đang kiểm thử rồi tuyên bố đã kiểm tra encoding đúng.

## 15. Ví dụ JUnit 5: assertions chính xác (snippet phụ thuộc JUnit)

Trong một dự án đã cài JUnit Jupiter, có thể sử dụng:

```java
import static org.junit.jupiter.api.Assertions.*;

byte[] expected = HexFormat.of().parseHex("61c3a90a");
byte[] actual = "aé\n".getBytes(StandardCharsets.UTF_8);
assertArrayEquals(expected, actual);

String text = "Tiếng Việt 😀";
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
assertEquals(text, new String(encoded, StandardCharsets.UTF_8));
```

Đây là **snippet cần JUnit 5**, không phải chương trình standalone. Nó giả định imports `HexFormat` và `StandardCharsets`, chạy trong test method có dependency `org.junit.jupiter:junit-jupiter` phù hợp.

Để chẩn đoán sai lệch:

```java
int offset = Arrays.mismatch(expected, actual);
assertEquals(-1, offset,
        () -> "Mismatch at byte index " + offset
                + "; expectedHex=" + HexFormat.of().formatHex(expected)
                + "; actualHex=" + HexFormat.of().formatHex(actual));
```

Đây là snippet test khác; không in payload nhạy cảm trong message. JUnit `assertArrayEquals` thường thuận tiện cho array equality, còn `mismatch` hữu ích nếu bạn cần báo đúng offset.

Với file lớn, tránh đưa cả file vào assertion message. Tách integration test so bằng `Files.mismatch`, lưu kích thước, offset đầu tiên sai và log context có giới hạn.

## 16. Round-trip với Reader/Writer và CharsetDecoder

Nếu ứng dụng thật sự đọc và ghi **văn bản**, các API `Reader/Writer` phù hợp vì chúng làm việc với ký tự thay vì bytes. Nhưng test phải hiểu rằng đọc text rồi ghi lại sẽ **encode dữ liệu một lần nữa**:

```java
// Snippet: source, target là Paths đã kiểm soát.
try (BufferedReader reader = Files.newBufferedReader(
         source, StandardCharsets.UTF_8);
     BufferedWriter writer = Files.newBufferedWriter(
         target, StandardCharsets.UTF_8)) {
    char[] chars = new char[4096];
    int n;
    while ((n = reader.read(chars)) != -1) {
        writer.write(chars, 0, n);
    }
}
```

Đây là snippet, cần imports `BufferedReader`, `BufferedWriter`, `Files`, `StandardCharsets` và xử lý IOException. Lưu ý khác biệt giữa copy **từng mảng char** và copy **từng dòng**: đọc/ghi char liên tục có thể giữ các ký tự newline như đã giải mã, trong khi `readLine/newLine` có thể thay đổi chúng.

Nhưng việc dùng `Reader/Writer` vẫn **không** tự bảo đảm byte-exact: decoder/encoder có thể xử lý BOM, malformed input, replacement, charset hoặc canonicalization khác nhau. Nếu bytes gốc là dữ liệu chuẩn cần giữ y nguyên, copy ở tầng byte trước, rồi kiểm tra bằng file mismatch.

Với stream mã hóa dài, `CharsetDecoder.decode(ByteBuffer, CharBuffer, boolean)` ở cấp thấp có cơ chế incremental state để xử lý ký tự bị cắt giữa hai chunk; đừng tạo `new String(chunk, UTF_8)` độc lập cho mỗi phần bytes nhận từ socket vì một ký tự multibyte có thể bị tách giữa các chunk.

## 17. Chẩn đoán Unicode bị cắt ngang các chunk

UTF-8 mã hóa `é` là:

```text
Chunk 1: C3
Chunk 2: A9
Toàn stream: C3 A9  -> U+00E9
```

Nếu dùng:

```java
String a = new String(new byte[] {(byte) 0xC3},
        StandardCharsets.UTF_8);
String b = new String(new byte[] {(byte) 0xA9},
        StandardCharsets.UTF_8);
String result = a + b;
```

đó **không** phải giải mã đúng toàn bộ sequence `C3 A9`. Từng chunk riêng không hợp lệ và decoder convenience có thể tạo replacement characters.

Cách đúng:

- Với dữ liệu ít, **tích lũy bytes** cho đến khi có toàn bộ message rồi decode một lần.
- Với stream lớn, dùng `InputStreamReader`/`BufferedReader` đọc từ stream liên tục để decoder duy trì trạng thái qua ranh giới buffer nội bộ.
- Hoặc quản lý `CharsetDecoder` incremental với `CoderResult`, trạng thái `endOfInput`, `flush()` và buffer có `compact()` khi còn bytes UTF-8 dang dở.

Nếu parser protocol xác định frame theo **byte length**, trước hết xác định bytes của frame đã đủ rồi mới decode; không cộng `String.length()` làm số bytes trong header.

## 18. Xử lý file lớn mà không chiếm RAM vô hạn

Các convenience APIs như `Files.readAllBytes` và `Files.readString` rất hữu ích cho **unit tests với fixture nhỏ**. Với file lớn, việc nạp tất cả bytes/text vào RAM có thể làm hết heap, kéo dài GC hoặc làm test không phản ánh code production streaming.

Một số chiến lược:

1. **File-to-file exact check:** dùng `Files.mismatch(pathA, pathB)` để có offset sai đầu tiên.
2. **Streaming compare:** mở hai input streams; đọc theo chunk, so sánh nội dung hữu hiệu từng lần đọc, đồng thời xử lý khác kích thước và partial reads.
3. **Hash theo luồng:** khi cần kiểm tra với một digest tham chiếu đã đáng tin, tính SHA-256 bằng `MessageDigest`/`DigestInputStream` mà không giữ tất cả bytes.
4. **Golden fixture nhỏ:** với protocol serializer, chọn test vectors đại diện cho boundary cases hơn là toàn bộ file nhiều GB.
5. **Boundary tests:** kích thước 0, 1, bufferSize-1, bufferSize, bufferSize+1, nhiều lần bufferSize+1; đặc biệt test chunk cuối ngắn.
6. **Resource closure:** dùng `try-with-resources` cho streams/channels và xử lý lỗi khi đóng.
7. **Concurrency:** nếu source đang bị process khác sửa, so sánh/hash có thể không tương ứng với snapshot nhất quán. Tách nguồn bất biến, dùng snapshot hoặc phối hợp writer trước khi kiểm tra.

Không nên dùng `MessageDigest.isEqual` để “thay thế so sánh nội dung file” khi cả hai digest đều tự tính từ các file có thể bị sửa đồng thời và ứng dụng cần bảo đảm phiên bản cụ thể. Digest comparison phù hợp khi đối tượng được đọc ổn định và tiêu chí trust/reference được định nghĩa rõ.

## 19. Lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test pass nhưng file có byte thừa ở cuối | So chuỗi sau trim, hoặc chỉ so prefix. | So byte length và toàn bộ byte bằng `Arrays.equals/Files.mismatch`. |
| Text giống trên editor nhưng mismatch | Khác BOM, line endings, Unicode normalization hoặc whitespace vô hình. | In hex/offset, xác nhận raw bytes trước. |
| Emoji làm sai byte length | Dùng `String.length()` như số byte UTF-8. | Encode và lấy `byte[].length`. |
| Chỉ chunk cuối bị sai | Ghi cả buffer thay vì đúng `n` byte mới đọc. | Dùng `write(buffer,0,n)` hoặc `ByteBuffer.limit` đúng. |
| Byte `FF` hiển thị `-1` | Java byte là signed. | Dùng `Byte.toUnsignedInt` và hex. |
| Sai charset chỉ trên máy khác | Dùng default charset thay vì chỉ định rõ. | Dùng `StandardCharsets.UTF_8` xuyên suốt. |
| Decode text lỗi nhưng test không fail | Decoder âm thầm replace invalid input. | Dùng `CharsetDecoder` với `CodingErrorAction.REPORT`. |
| Encode ASCII vẫn “chạy được” với tiếng Việt | Encoder thay ký tự không biểu diễn được. | Dùng strict `CharsetEncoder` và assert lỗi. |
| Text bị đổi `LF → CRLF` | `BufferedReader.readLine` rồi `newLine()`. | Copy bytes hoặc giữ line endings theo policy. |
| Dữ liệu mất khi decode stream theo chunks | UTF-8 multibyte bị cắt giữa hai lần read. | Decoder streaming có state hoặc tích lũy đúng. |
| Hash khớp nhưng file là sai version | Hash tham chiếu không gắn với identity/version. | Manifest đáng tin gồm algorithm, path, version, digest. |
| Copy qua text API làm ZIP hỏng | Cố decode bytes nhị phân thành String. | Dùng `InputStream/OutputStream` hoặc `FileChannel`. |
| Test không tái lập trên CI | Phụ thuộc locale, timezone, EOL, default charset hoặc path separator. | Fixture xác định và cấu hình explicit. |
| File đang bị process khác ghi nên test flake | So sánh không có snapshot, file đổi trong lúc đọc. | Đảm bảo file bất biến hoặc copy/snapshot trước khi kiểm tra. |
| In log toàn bộ hex để debug | Tiết lộ dữ liệu nhạy cảm hoặc làm log khổng lồ. | Chỉ log offset và vùng context có giới hạn khi được phép. |

## 20. Thiết kế bộ kiểm thử đáng tin

Một suite tốt nên có nhiều tầng:

**Unit tests cho encoder/decoder:** kiểm tra golden bytes độc lập; test UTF-8 hợp lệ và sai; assert được lỗi khi unpaired surrogate hoặc byte sequence malformed; test charset được chỉ định, không phụ thuộc default.

**Tests cho read/write helper:** dùng bytes có `00`, `FF`, dữ liệu ngẫu nhiên seeded deterministic, size qua nhiều ranh giới buffer; so bytes exact sau một vòng copy.

**Round-trip text tests:** kiểm tra tiếng Việt, emoji, combining marks, ký tự xuống dòng, dòng rỗng cuối, BOM policy; xác định test muốn exact `String.equals` hay normalization equivalence.

**Integration tests:** ghi file, đóng resource, mở lại từ disk, so `Files.mismatch`, kiểm tra behavior trên Windows/Linux khi cần; ghi rõ các giả định có thể khác OS.

**Regression tests:** mỗi lỗi encoding/copy đã phát hiện nên có fixture thể hiện đúng byte đã lỗi. Đừng “sửa” expected output để test pass mà không xác nhận hợp đồng dữ liệu thực.

**Negative tests:** dữ liệu truncate, invalid UTF-8, file không đọc được, disk full/permission khi môi trường test hỗ trợ, corrupt frame, duplicate bytes, source đổi trong quá trình đọc; kết quả phải thất bại rõ ràng, không trả thành công giả.

Đặc biệt, đối với serializer/protocol, tránh phép thử tự xác nhận duy nhất kiểu:

```text
actualBytes = encode(input)
restored = decode(actualBytes)
assertEquals(input, restored)
```

Nếu encode và decode cùng mắc một lỗi đối xứng, phép thử có thể vẫn pass. Bổ sung một **golden vector bytes** chuẩn và bài test độc lập cho cả encode và decode.

## 21. Bài tập thực hành

**Bài 1 — Golden UTF-8.** Dùng `HexFormat.parseHex("61c3a90a")` làm expected cho văn bản `"aé\n"`. Viết JUnit test so chính xác bằng `assertArrayEquals` và giải thích vì sao phải dùng hex fixture độc lập thay vì tạo expected bằng chính logic cần test.

**Bài 2 — Một byte hỏng.** Tạo `byte[]` chứa 1.024 byte, thay byte ở index 511 rồi dùng `Arrays.mismatch` xác nhận vị trí sai. Kiểm thử thêm trường hợp mảng dài khác nhau nhưng chung prefix.

**Bài 3 — BOM.** Tạo hai file UTF-8 chứa `abc`, một file có prefix `EF BB BF`. Dùng `Files.mismatch`, `Files.size` và hex để báo khác biệt. Quy định rõ test “raw exact” và test “semantic text” có chấp nhận BOM hay không.

**Bài 4 — Line endings.** Viết fixture với CRLF, LF và một file trộn cả hai. Copy với streams (không dùng readLine) rồi so nguyên byte; tiếp theo chủ động normalize newline và kiểm tra output theo policy mới.

**Bài 5 — NFC/NFD.** So hai chuỗi `"café"` và `"cafe\u0301"` bằng `equals`, byte arrays UTF-8 và `Normalizer.Form.NFC`. Giải thích vì sao kết luận khác nhau và khi nào normalization bị cấm.

**Bài 6 — Invalid UTF-8.** Dùng mảng `C3 28`. So hành vi decoder strict với API convenience có replacement. Đảm bảo một pipeline yêu cầu dữ liệu chính xác phải báo lỗi, không sửa byte âm thầm.

**Bài 7 — Multibyte bị cắt.** Gửi bytes `C3 A9` qua hai read chunks `C3` và `A9`. So kết quả decode từng chunk với decode toàn stream. Sửa bằng `InputStreamReader` hoặc `CharsetDecoder` incremental.

**Bài 8 — File lớn.** Sinh file dữ liệu có seed và kích thước lớn hơn nhiều lần buffer, rồi copy qua `FileChannel`; so `Files.mismatch == -1`. Chèn lỗi cố ý ở byte giữa file để in offset sai. Không log toàn bộ nội dung.

**Bài 9 — Text length và payload length.** Tạo protocol gửi `"Việt 😀"` dưới dạng UTF-8 với header 4 byte chiều dài; xác nhận dùng `encoded.length`, không dùng `String.length()`. Mô phỏng receiver đọc payload qua nhiều chunk.

**Bài 10 — Regression fixture.** Chọn một lỗi thật như BOM bị thêm hoặc LF bị đổi thành CRLF. Lưu fixture trước và sau dưới dạng hex kèm expected mismatch offset; viết test để lỗi không quay lại.

### Câu hỏi tự kiểm tra

1. `String.equals` chứng minh byte-for-byte equality được không?
2. `Files.mismatch` trả về giá trị gì khi hai file hoàn toàn giống nhau?
3. Khi source stream đọc 7 byte vào mảng 8.192 byte, nên ghi bao nhiêu byte?
4. Vì sao `getBytes()` không truyền charset có thể làm test không ổn định trên môi trường khác?
5. `String.length()` của một emoji supplementary là bao nhiêu và UTF-8 dùng mấy byte?
6. Khi nào hai chuỗi cùng hiển thị nhưng `Arrays.equals(utf8A, utf8B) == false`?
7. `readLine/newLine` tác động thế nào đến line ending raw bytes?
8. Vì sao decoder strict cần thiết với dữ liệu văn bản phải toàn vẹn?
9. Vì sao không nên decode một phần byte UTF-8 riêng lẻ cho mỗi chunk?
10. Một bộ test encode→decode pass có đủ chứng minh encoder tuân thủ golden wire format không?

## 22. Tham khảo

- [Java SE 21 — Arrays](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `equals`, `mismatch` với các mảng primitive.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readAllBytes`, `readString`, `write`, `copy`, `mismatch`.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn có sẵn.
- [Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): cách phát hiện malformed/unmappable input.
- [Java SE 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát lỗi khi encode String ra bytes.
- [Java SE 21 — HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): đọc/ghi byte dưới dạng hex.
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): Unicode normalization NFC/NFD/NFKC/NFKD.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/remaining và thao tác NIO.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions và data-driven tests.

**Ghi nhớ:** Với yêu cầu **byte-exact**, hãy kiểm tra từng byte thực tế qua `Arrays.equals/Arrays.mismatch/Files.mismatch` và báo offset khi lỗi. Với **text round-trip**, chỉ định charset tường minh, kiểm thử cả encode/decode lẫn golden bytes, và kiểm soát BOM, newline, Unicode normalization cùng lỗi malformed. “Nhìn đúng trên màn hình” và “không có exception” không thay thế bằng chứng nội dung đã được bảo toàn.
