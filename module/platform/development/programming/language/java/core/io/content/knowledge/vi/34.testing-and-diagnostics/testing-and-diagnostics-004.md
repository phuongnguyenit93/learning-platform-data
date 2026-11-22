# Dữ liệu Unicode, BOM và ký tự bị chia giữa các khối khi đọc/ghi Java I/O

## 1. Vấn đề cần giải quyết

Khi một ứng dụng Java đọc hoặc ghi văn bản, nó không thực sự chuyển trực tiếp “ký tự” qua ổ đĩa hay socket. Nó chuyển **byte**. Các byte ấy phải được mã hóa hoặc giải mã theo một **charset** nhất định, chẳng hạn UTF-8 hoặc UTF-16.

Một chương trình có thể xử lý đúng văn bản ASCII nhưng lại làm hỏng tiếng Việt, emoji hoặc tên người khi:

- Chia tệp/network stream thành các **khối byte** rồi gọi `new String(chunk, UTF_8)` cho **từng khối riêng lẻ**.
- Đọc các byte của một ký tự UTF-8 nhiều byte bằng những lượt đọc khác nhau.
- Nhầm **byte**, **UTF-16 code unit**, **Unicode code point** và **ký tự người dùng nhìn thấy**.
- Không nhận diện đúng **BOM** (Byte Order Mark) ở đầu file.
- Giải mã UTF-16 với byte order không phù hợp.
- Thay thế byte lỗi bằng ký tự `�` mà không phát hiện nguồn dữ liệu đã hỏng.
- Nhầm số byte trong network framing với `String.length()`.
- Cắt buffer ở vị trí bất kỳ rồi coi đó là ranh giới ký tự.

Bài này đặt trong nhóm **Kiểm thử và chẩn đoán** của Java Core I/O: ngoài cách giải mã đúng, chúng ta sẽ xây dựng các trường hợp kiểm thử ranh giới, in byte hex, kiểm tra chính sách lỗi, BOM và Unicode normalization.

**Nguyên tắc trung tâm:** Ranh giới một lần `InputStream.read(...)`, `FileChannel.read(...)` hoặc một network packet **không phải** ranh giới Unicode character. Việc giải mã phải duy trì **trạng thái liên tục** giữa các lần nhận byte.

## 2. Unicode không đồng nghĩa với UTF-8

### Unicode code point

Unicode định nghĩa các **code point**, thường được viết dưới dạng `U+XXXX`. Ví dụ:

| Nội dung | Unicode code point | UTF-8 | UTF-16 |
|---|---|---|---|
| `A` | `U+0041` | `41` | `0041` |
| `é` | `U+00E9` | `C3 A9` | `00E9` |
| `☕` | `U+2615` | `E2 98 95` | `2615` |
| `😀` | `U+1F600` | `F0 9F 98 80` | `D83D DE00` (surrogate pair) |

Các dãy UTF-16 trong bảng là **giá trị code unit**; byte thực tế của chúng còn phụ thuộc big-endian/little-endian.

### UTF-8 là encoding biến độ dài

Trong UTF-8, một Unicode code point hợp lệ có thể chiếm **1 đến 4 byte**. Các byte thuộc cùng một code point **có thể nằm ở hai khối đọc khác nhau**.

Ví dụ với `☕`:

```text
Unicode code point: U+2615

UTF-8 bytes: E2 98 95
             ^^ ^^ ^^
             1  2  3

Chunk #1: E2 98
Chunk #2: 95

Cả hai chunk riêng lẻ đều KHÔNG đủ để giải mã U+2615.
```

Nếu người lập trình dùng `new String(chunk1, UTF_8)` và `new String(chunk2, UTF_8)` rồi nối hai chuỗi, mỗi lần giải mã có thể xem phần byte của chunk đó là một chuỗi độc lập bị lỗi, làm xuất hiện ký tự thay thế `U+FFFD`.

### UTF-16 là encoding theo code unit 16 bit

Trong Java, `String` dùng chuỗi **UTF-16 code units** để biểu diễn nội dung (API `char` tương ứng một code unit). Một code point ở vùng bổ sung, ví dụ `😀`, cần **hai code unit**:

```text
U+1F600 -> high surrogate D83D + low surrogate DE00

Java "😀".length() == 2
"😀".codePointCount(0, "😀".length()) == 1
```

Trong file UTF-16, từng code unit gồm hai byte; muốn đọc đúng cần biết **endianness**, đồng thời phải xử lý surrogate pair. File còn có thể bị chia ngay **giữa hai byte của một code unit**, hoặc **giữa hai surrogate**.

## 3. Bốn đơn vị đếm hay bị nhầm

Xét chuỗi:

```java
String text = "A☕B😀C";
```

Các đại lượng khác nhau:

| Đại lượng | Giá trị | Giải thích |
|---|---:|---|
| `text.getBytes(UTF_8).length` | 10 | 1 + 3 + 1 + 4 + 1 byte UTF-8 |
| `text.length()` | 6 | Số UTF-16 code units; emoji chiếm 2 |
| `text.codePointCount(0,text.length())` | 5 | Số Unicode code points |
| Số grapheme clusters người dùng thấy | 5 với ví dụ này | Không phải lúc nào bằng code points |

**Không dùng `String.length()` làm kích thước byte cần gửi**, không cắt byte stream theo số ký tự, không coi một Java `char` luôn là một ký tự Unicode đầy đủ.

Ví dụ ghép ký tự có dấu:

```text
"é"        U+00E9            (một code point)
"e\u0301"  U+0065 U+0301     (hai code points)

Hai chuỗi có thể nhìn gần giống nhau nhưng có biểu diễn khác.
```

Hai cách biểu diễn này có thể có số byte UTF-8 khác nhau, `String.equals` không nhất thiết true, và normalization có thể được cân nhắc theo quy định nghiệp vụ.

Đối với emoji phức tạp có zero-width joiner, variation selector hoặc dấu tổ hợp, “một ký tự nhìn thấy” còn có thể gồm **nhiều** code points. Không giả định `codePointCount` luôn bằng số grapheme clusters.

## 4. Một lần read() không đảm bảo đủ một ký tự

API I/O thường trả về số byte thực nhận được:

```java
int n = inputStream.read(buffer);
```

Một lần read có thể trả **ít byte hơn độ dài buffer**, thậm chí khi nguồn còn nhiều dữ liệu, tùy kiểu stream và thời điểm. Với network socket, một send của peer không tương ứng một read của ứng dụng nhận.

Ví dụ tệp chứa byte UTF-8:

```text
41 E2 98 95 42 F0 9F 98 80 43
 A    ☕      B       😀        C
```

Người đọc lấy từng khối 2 byte:

```text
Khối 1: 41 E2
Khối 2: 98 95
Khối 3: 42 F0
Khối 4: 9F 98
Khối 5: 80 43
```

Không một sự kiện I/O nào nói “đây là một Unicode character”. Ranh giới khối chỉ do buffer, provider và thời điểm truyền dữ liệu quyết định.

### Phản ví dụ: decode từng chunk riêng

```java
byte[] buffer = new byte[2];
StringBuilder text = new StringBuilder();

int n;
while ((n = input.read(buffer)) != -1) {
    text.append(new String(buffer, 0, n, StandardCharsets.UTF_8));
}
```

Đây là **mã minh họa sai về Unicode**, giả định biến `input` là `InputStream`. Từng lời gọi `new String` tạo **một phiên giải mã độc lập**, không nhớ rằng byte `E2` cuối khối trước còn cần `98 95` trong khối sau.

Việc chọn buffer lớn hơn **giảm xác suất** cắt ký tự trong một số bài thử nhưng **không giải quyết triệt để**. Bất kỳ buffer hữu hạn nào cũng có thể kết thúc giữa ký tự.

## 5. Cách dễ nhất: dùng Reader với charset tường minh

Nếu mục tiêu là **đọc văn bản** chứ không cần tự thao tác với byte framing, dùng `InputStreamReader` hoặc `Files.newBufferedReader` với charset đúng:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý cả dòng Unicode đã được decoder ghép đúng.
    }
}
```

Đây là snippet minh họa, cần `BufferedReader`, `Files`, `Path` và `StandardCharsets`; `path` phải được khai báo.

`InputStreamReader` giữ **decoder state giữa những lần read ký tự**. Nếu một code point UTF-8 bị chia qua nhiều lần đọc byte ở dưới, reader có thể giữ phần chưa đủ và chờ byte tiếp theo thay vì giải mã từng byte chunk như một chuỗi hoàn chỉnh.

### Chọn charset một cách tường minh

```java
try (Reader reader = new InputStreamReader(
        Files.newInputStream(path), StandardCharsets.UTF_8)) {
    char[] chars = new char[256];
    int n;
    while ((n = reader.read(chars)) != -1) {
        // Sử dụng đúng n UTF-16 code units.
    }
}
```

Reader trả **UTF-16 code units** vào `char[]`, không trả “đúng n code points”. Dù decoder UTF-8 xử lý byte nhiều phần đúng cách, **một cặp surrogate trong char[] vẫn có thể bị chia qua các lần read ký tự** nếu buffer/khối đọc không đủ hoặc việc đọc dừng đúng ranh giới đó.

Nếu tác vụ chỉ hiển thị/ghi lại văn bản, có thể tiếp tục giữ ký tự trong reader/writer. Nếu cần đếm code point, gắn token/grapheme hoặc validate surrogate, phải xử lý theo API Unicode phù hợp chứ không xem mọi phần tử `char` độc lập.

## 6. CharsetDecoder: giải mã liên tục với ByteBuffer

Khi ứng dụng xử lý **binary protocol**, `ByteBuffer`, hoặc nhận stream theo những đoạn tùy ý, `java.nio.charset.CharsetDecoder` cho phép kiểm soát quá trình giải mã.

Các thành phần:

- `CharsetDecoder`: giữ trạng thái giải mã giữa các lần gọi.
- `ByteBuffer` input: chứa byte mới nhận **và byte dư chưa đủ một character từ lần trước**.
- `CharBuffer` output: nhận UTF-16 code units đã decode.
- `CoderResult.UNDERFLOW`: decoder đã tiêu thụ được những gì có thể từ input hiện tại; có thể còn byte chưa đủ cần giữ lại.
- `CoderResult.OVERFLOW`: output buffer hết chỗ, cần drain `CharBuffer` rồi decode tiếp.
- `CoderResult.isError()`: byte không hợp lệ hoặc unmappable theo charset/error policy.
- `decoder.decode(input, output, endOfInput)`: truyền `true` khi đã xác nhận byte stream thực sự kết thúc.
- `decoder.flush(output)`: hoàn tất phần trạng thái cuối **sau khi decode(..., true) đã trả UNDERFLOW**.

### Chu trình chuẩn với buffer

```text
ByteBuffer ở WRITE MODE
     |   (có thể còn byte từ cuối lượt trước)
     +-- append byte mới
     |
     v
input.flip()  -> READ MODE
     |
     v
decoder.decode(input, chars, eof)
     |
     +-- OVERFLOW -> chars.flip(), drain, chars.clear(), decode tiếp
     |
     +-- ERROR -> throwException / chính sách lỗi
     |
     +-- UNDERFLOW -> giữ byte chưa được tiêu thụ
     |
input.compact() -> dồn byte chưa đủ về đầu, quay WRITE MODE
     |
     +-- nếu chưa EOF: đọc thêm byte vào phần trống, lặp
     |
     +-- nếu EOF: decoder.flush(chars) tới UNDERFLOW
```

`ByteBuffer.compact()` là điểm cốt lõi. Nó **không bỏ phần còn lại**: nó sao chép phần byte ở `[position,limit)` chưa xử lý về đầu và đặt position sau số byte còn tồn. Lượt đọc tiếp chỉ append byte mới phía sau chúng.

Không dùng `input.clear()` sau mọi UNDERFLOW: `clear()` sẽ cho ghi đè toàn bộ input và **đánh mất byte đang chờ**.

## 7. Ví dụ Java 17+ hoàn chỉnh: đọc UTF-8 theo các khối 2 byte

Chương trình dưới đây:

1. Tạo tệp tạm chứa `A☕B😀C` được mã hóa bằng UTF-8.
2. Đọc mỗi lần **tối đa 2 byte**, cố tình cắt ở giữa biểu diễn của `☕` và `😀`.
3. Sử dụng một `CharsetDecoder` xuyên suốt, giữ byte dư bằng `compact()`.
4. Kiểm tra round-trip và so sánh số byte, số UTF-16 code units, số code points.
5. Ghi lại file với **UTF-8 BOM** ở đầu để chứng minh decoder thông thường nhìn thấy `U+FEFF` như một ký tự và cách xử lý BOM theo policy.
6. Đóng/dọn file tạm.

Lưu tên **`UnicodeBoundaryDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnicodeBoundaryDemo {

    public static void main(String[] args) throws IOException {
        String original = "A☕B😀C";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        Path file = Files.createTempFile("unicode-chunk-", ".txt");

        try {
            Files.write(file, utf8);
            String restored = decodeUtf8InTwoByteChunks(file, false);

            System.out.println("UTF-8 bytes: " + utf8.length);
            System.out.println("UTF-16 units: " + original.length());
            System.out.println("Code points: " +
                    original.codePointCount(0, original.length()));
            System.out.println("Split-safe equals: " +
                    original.equals(restored));

            byte[] withBom = new byte[utf8.length + 3];
            withBom[0] = (byte) 0xEF;
            withBom[1] = (byte) 0xBB;
            withBom[2] = (byte) 0xBF;
            System.arraycopy(utf8, 0, withBom, 3, utf8.length);
            Files.write(file, withBom);

            String rawWithBom =
                    decodeUtf8InTwoByteChunks(file, false);
            String clean =
                    decodeUtf8InTwoByteChunks(file, true);

            System.out.println("Leading BOM character: " +
                    rawWithBom.startsWith("\uFEFF"));
            System.out.println("After BOM policy: " + clean);
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static String decodeUtf8InTwoByteChunks(
            Path file, boolean stripLeadingBom) throws IOException {

        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer inputBytes = ByteBuffer.allocate(8);
        CharBuffer outputChars = CharBuffer.allocate(4);
        StringBuilder result = new StringBuilder();

        try (InputStream stream = Files.newInputStream(file)) {
            boolean endOfInput = false;

            while (!endOfInput) {
                int bytesToRead = Math.min(2, inputBytes.remaining());
                if (bytesToRead == 0) {
                    throw new IOException("Input buffer made no progress");
                }

                int n = stream.read(
                        inputBytes.array(),
                        inputBytes.position(),
                        bytesToRead);

                if (n == -1) {
                    endOfInput = true;
                } else if (n == 0) {
                    throw new IOException("Input stream made no progress");
                } else {
                    inputBytes.position(inputBytes.position() + n);
                }

                inputBytes.flip();

                while (true) {
                    CoderResult step = decoder.decode(
                            inputBytes, outputChars, endOfInput);

                    outputChars.flip();
                    result.append(outputChars);
                    outputChars.clear();

                    if (step.isError()) {
                        step.throwException();
                    }
                    if (step.isUnderflow()) {
                        break;
                    }
                    // OVERFLOW: outputChars đã được drain, decode tiếp.
                }

                inputBytes.compact();
            }

            while (true) {
                CoderResult step = decoder.flush(outputChars);

                outputChars.flip();
                result.append(outputChars);
                outputChars.clear();

                if (step.isError()) {
                    step.throwException();
                }
                if (step.isUnderflow()) {
                    break;
                }
                // OVERFLOW: còn ký tự trong decoder, drain tiếp.
            }
        }

        String text = result.toString();
        if (stripLeadingBom && text.startsWith("\uFEFF")) {
            return text.substring(1);
        }
        return text;
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Stdout dự kiến chính xác khi I/O file tạm thành công:**

```text
UTF-8 bytes: 10
UTF-16 units: 6
Code points: 5
Split-safe equals: true
Leading BOM character: true
After BOM policy: A☕B😀C
```

Vì sao ví dụ đúng?

- `inputBytes` trong trạng thái write mode nhận tối đa 2 byte mỗi lượt. Nếu gặp 2 byte đầu của `☕`, decoder trả UNDERFLOW và không xem chúng là lỗi vì chưa phải EOF.
- `inputBytes.compact()` giữ lại các byte chưa được decode. Lượt sau append byte thứ ba, tạo đủ chuỗi `E2 98 95`.
- Tương tự với `😀` có 4 byte UTF-8. Decoder có thể giữ những byte đầu qua nhiều lượt cho tới khi nhận đủ.
- `outputChars` chứa kết quả dạng UTF-16. `StringBuilder.append(CharBuffer)` thêm các code units đã giải mã.
- `CodingErrorAction.REPORT` khiến byte thực sự sai hoặc chuỗi cuối bị cắt dở gây lỗi thay vì lặng lẽ chèn `�`.
- `endOfInput=true` **chỉ khi `read` đã trả `-1`**. Nếu báo true sớm khi chunk chưa chứa đủ byte, decoder có thể coi byte dư là malformed.
- Sau decode cuối, `decoder.flush` hoàn tất trạng thái decoder theo đúng protocol.
- `rawWithBom` bắt đầu bằng ký tự `U+FEFF` được giải mã từ byte `EF BB BF`. Policy ví dụ chỉ bỏ **ký tự U+FEFF đầu tiên**; nó không xóa mọi ký tự tương tự giữa nội dung.

**Giới hạn có chủ đích:** ví dụ dùng buffer nhỏ, file nhỏ và `StringBuilder` để nhìn rõ cơ chế. Khi triển khai thật với file rất lớn hoặc nguồn không tin cậy, cần giới hạn output, quản lý tốc độ/timeout và xử lý trực tiếp phần ký tự đã decode thay vì tích lũy toàn bộ vào một StringBuilder.

## 8. Phân tích sâu các trạng thái CharsetDecoder

### UNDERFLOW

Kết quả UNDERFLOW thường có nghĩa decoder **không thể tiến thêm** với input đã cung cấp. Trong chế độ streaming, `ByteBuffer` có thể còn 1–3 byte đầu của một UTF-8 sequence chưa đủ. Giữ chúng lại bằng `compact()`.

Ví dụ:

```text
Bytes input: E2 98
Decoder: UNDERFLOW
input.remaining(): 2 (chưa tiêu thụ)
compact(): giữ E2 98
append next: 95
decode lại: -> ☕
```

Khi `endOfInput=true`, các byte thiếu ở EOF không còn được chờ tiếp: chúng phải bị xử lý theo malformed-input policy.

### OVERFLOW

`OVERFLOW` không có nghĩa file quá lớn hoặc byte sai. Nó có nghĩa **CharBuffer chưa đủ chỗ chứa các UTF-16 code units kế tiếp**. Có thể giải quyết bằng:

```java
outputChars.flip();
process(outputChars);
outputChars.clear();
```

Đây là đoạn minh họa, `process` do ứng dụng định nghĩa. Sau khi drain, gọi `decode` tiếp **trên input đang ở vị trí hiện tại**, không được bỏ input còn lại hoặc tạo decoder mới.

### ERROR

`CoderResult.isError()` gồm malformed-input hoặc unmappable-character theo bảng mã và chính sách:

- `REPORT`: nhận kết quả lỗi, `throwException()` chuyển thành checked exception phù hợp, ví dụ `MalformedInputException`.
- `REPLACE`: thay bằng một chuỗi/ký tự replacement của decoder và tiếp tục.
- `IGNORE`: bỏ input bị lỗi, có nguy cơ mất thông tin mà không để dấu vết.

`REPORT` thường thích hợp khi kiểm thử data pipeline, đọc file cấu hình, giải mã giao thức có schema hoặc nội dung cần bảo toàn chính xác. `REPLACE` có thể phù hợp với giao diện hiển thị dữ liệu bị hỏng nếu sản phẩm muốn phục hồi “best effort”, nhưng phải có telemetry để biết đã mất byte. `IGNORE` hiếm khi thích hợp cho dữ liệu có ý nghĩa bảo mật, identifier hoặc chữ ký.

## 9. InputStreamReader có giải quyết tất cả không?

`InputStreamReader` là lựa chọn đơn giản và rất tốt cho **byte-to-character streaming** với charset đã biết. Nó giữ `CharsetDecoder` nội bộ và không làm sai Unicode chỉ vì tầng InputStream cung cấp các byte chia nhỏ.

Nhưng cần nhớ:

1. Nó không tự đoán chính xác charset của mọi file; nên quy định rõ.
2. Với UTF-8, nó không tự động loại mọi BOM theo một chính sách ứng dụng có thể dự đoán; nếu cần bỏ BOM đầu file, phải có logic riêng.
3. Nó chuyển byte thành `char`/UTF-16 units. Nếu ứng dụng xử lý các đơn vị `char[]` riêng và cắt surrogate pair, lỗi có thể xuất hiện ở **tầng sau** dù byte decoder đã đúng.
4. Nó không tự parse JSON, XML hay giao thức có length prefix.
5. Nó không giới hạn tổng lượng ký tự được đọc, không tự bảo vệ memory nếu ứng dụng gọi `readAllBytes` hoặc ghép chuỗi không kiểm soát.
6. Với API parser yêu cầu byte offset chính xác, `Reader` có thể không tiện vì một `char` không ánh xạ 1:1 sang một byte.
7. Với các codec và yêu cầu error policy khác, tạo `CharsetDecoder` chủ động có thể giúp báo lỗi thay vì thay ký tự.

### Cắt UTF-16 surrogate pair ở tầng ký tự

Ví dụ:

```java
String emoji = "😀";
char high = emoji.charAt(0);
char low = emoji.charAt(1);

System.out.println(emoji.length()); // 2
System.out.println(Character.isHighSurrogate(high)); // true
System.out.println(Character.isLowSurrogate(low));   // true
```

Đây là một đoạn Java minh họa có thể đặt trong `main`. Nếu sau khi đã decode UTF-8 đúng, một chương trình lại xử lý từng `char` như một code point độc lập, nó vẫn có thể làm hỏng emoji.

Giải pháp ở tầng text: sử dụng `String.codePoints()`, `Character.codePointAt`, hoặc một iterator giữ high/low surrogate giữa các khối `char[]`. Với việc phân đoạn ký tự hiển thị, cần thêm xử lý grapheme clusters (Unicode segmentation) chứ không chỉ code points.

## 10. BOM là gì?

**Byte Order Mark (BOM)** có gốc là ký hiệu Unicode `U+FEFF` được dùng ở đầu một số stream, chủ yếu để chỉ **endianness** hoặc nhận diện encoding. Không phải mọi file Unicode đều có BOM và BOM không phải metadata bảo mật.

Các dãy byte mở đầu phổ biến:

| Encoding/đặc điểm | BOM ở đầu stream |
|---|---|
| UTF-8 | `EF BB BF` |
| UTF-16 big-endian | `FE FF` |
| UTF-16 little-endian | `FF FE` |
| UTF-32 big-endian | `00 00 FE FF` |
| UTF-32 little-endian | `FF FE 00 00` |

**Chú ý:** UTF-8 không có vấn đề byte order; UTF-8 BOM là **dấu hiệu nhận diện** tùy chọn, không phải yêu cầu. Nhiều định dạng/giao thức cấm, bỏ qua hoặc xử lý BOM theo các quy tắc riêng.

### BOM phải ở đầu stream

Nếu ứng dụng quyết định bỏ BOM, chỉ nhận diện BOM ở **đầu nội dung** (sau khi xác định source framing phù hợp). Đừng dùng `text.replace("\uFEFF","")` trên toàn bộ văn bản: bạn sẽ xóa mọi `U+FEFF` xuất hiện trong nội dung, dù nó không được dùng làm BOM đầu stream.

BOM có thể bị chia qua chunk boundaries:

```text
UTF-8 BOM: EF BB BF
Chunk 1: EF
Chunk 2: BB
Chunk 3: BF 41 ...

Không được quyết định “không có BOM” chỉ vì chunk 1 chưa đủ ba byte.
```

Vì vậy BOM detector tự viết cũng phải **giữ lại số byte đầu đủ dài** rồi mới quyết định, hoặc giải mã liên tục từ đầu và xử lý ký tự `U+FEFF` đầu tiên khi định dạng cho phép.

## 11. UTF-8 BOM và Java StandardCharsets.UTF_8

`StandardCharsets.UTF_8` khi giải mã byte `EF BB BF` thông thường trả về **ký tự `U+FEFF`** trong chuỗi. Ví dụ:

```java
byte[] bytes = {
    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
    (byte) 0x41
};

String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text.startsWith("\uFEFF")); // true
System.out.println(text.substring(1));          // A
```

Đây là đoạn code minh họa cần `StandardCharsets` và có thể đặt trong `main`.

Đây là nguồn của một lỗi khó thấy: file cấu hình có BOM UTF-8, ứng dụng kỳ vọng header `"id,name"` nhưng String thực là `"\uFEFFid,name"`. So sánh tên cột đầu tiên thất bại dù mắt thường thấy giống nhau.

Cách xử lý tùy định dạng:

- Nếu format **cho phép BOM**, nhận diện và bỏ BOM **một lần ở đầu**.
- Nếu format **cấm BOM**, từ chối input với thông báo rõ thay vì tự ý sửa.
- Nếu format cần bảo toàn chính xác byte gốc, không loại BOM âm thầm.
- Nếu ứng dụng chỉ hiển thị, nên có quyết định nhất quán để tránh ký tự zero-width ẩn đầu text.

Không tự chèn UTF-8 BOM cho mọi file bằng mặc định; UTF-8 chuẩn không cần BOM để giải mã đúng.

## 12. UTF-16 BOM và byte order

UTF-16 có hai endian-specific charset là `UTF_16BE` và `UTF_16LE`; Java cũng có `StandardCharsets.UTF_16`. Chúng không được sử dụng như nhau trong mọi trường hợp.

- `UTF_16BE`: hai byte đầu của code unit `0x0041` là `00 41`.
- `UTF_16LE`: hai byte đầu là `41 00`.
- `UTF_16`: Java hỗ trợ cơ chế nhận diện BOM để xác định byte order (khi có), dùng byte order mặc định của charset này khi không có BOM theo hợp đồng implementation/documentation.

Ví dụ:

```text
Văn bản "A"

UTF-16BE bytes (không BOM): 00 41
UTF-16LE bytes (không BOM): 41 00

Có BOM:
UTF-16BE: FE FF 00 41
UTF-16LE: FF FE 41 00
```

Nếu code dùng `new String(bytes, UTF_16LE)` để đọc file có BOM UTF-16BE, kết quả sẽ sai; bạn đã chỉ định little-endian trong khi byte thực tế là big-endian. Nếu dùng `UTF_16` trên dữ liệu có BOM chuẩn, decoder có thể nhận diện endian phù hợp.

### Không chỉ kiểm tra hai byte đầu một cách cứng nhắc

Nếu hệ thống hỗ trợ cả UTF-16/UTF-32, thứ tự nhận diện BOM cần chú ý vì `FF FE 00 00` của UTF-32LE bắt đầu bằng `FF FE` (trùng prefix của UTF-16LE). Detector tự viết nên kiểm tra **BOM dài nhất trước**, kết hợp charset được protocol cho phép. Java SE có các charset UTF-8/UTF-16 chuẩn; UTF-32 không nằm trong `StandardCharsets` constant set bắt buộc ở mọi môi trường, nên không tự assume `StandardCharsets.UTF_32LE` tồn tại.

Một ứng dụng tốt thường **không cần tự động dò mọi Unicode encoding**. Nếu format đã quy định UTF-8 thì xử lý như UTF-8 và chỉ quản lý BOM theo spec của format đó.

## 13. Không nhầm BOM với mã hóa file từ nguồn không rõ

“Có BOM” không có nghĩa nội dung phía sau chắc chắn hợp lệ. “Không có BOM” cũng không đủ để kết luận file là ASCII hay UTF-8.

Một số nguồn lỗi:

- Ứng dụng dùng `Charset.defaultCharset()` thay vì charset của giao thức.
- File ghi bằng Windows-1252 hoặc một legacy code page nhưng code đọc bằng UTF-8.
- File UTF-16LE không BOM bị đọc bằng UTF-8, tạo chuỗi có NUL xen kẽ hoặc ký tự không mong đợi.
- File UTF-8 BOM bị ứng dụng xử lý như tên cột CSV thông thường.
- File có byte sai hoặc bị cắt cuối, decoder với `REPLACE` làm mất bằng chứng lỗi.
- Network protocol có length prefix tính theo **số byte**, nhưng writer lại dùng `String.length()`.
- HTTP/content metadata và nội dung thực không nhất quán; ứng dụng vẫn phải theo spec để xử lý.

Không dùng phép suy đoán từ một vài byte để gán charset cho dữ liệu mang ý nghĩa bảo mật hoặc cần trọn vẹn. Nếu không có metadata đáng tin, cần một **hợp đồng/chiến lược phát hiện encoding rõ ràng** và xác nhận ở tầng nghiệp vụ.

## 14. CodingErrorAction: REPORT, REPLACE, IGNORE

Java `CharsetDecoder` cho phép thiết lập:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Đây là đoạn minh họa, cần import `CharsetDecoder`, `StandardCharsets` và `CodingErrorAction`.

Bảng so sánh:

| Chính sách | Hành vi | Nên dùng khi |
|---|---|---|
| `REPORT` | Trả lỗi dạng `CoderResult` / ném exception khi xử lý | Dữ liệu cần đúng byte, cấu hình, protocol, kiểm thử |
| `REPLACE` | Chèn replacement do decoder cung cấp | Hiển thị best-effort được phép mất thông tin |
| `IGNORE` | Bỏ phần input lỗi | Chỉ khi yêu cầu nghiệp vụ cho phép bỏ dữ liệu mà không phá ý nghĩa |

### Malformed UTF-8

Một chuỗi byte có thể sai vì:

- Byte continuation xuất hiện khi chưa có lead byte hợp lệ.
- Lead byte cần thêm continuation nhưng gặp byte không phù hợp.
- Một sequence bị cắt ngay khi EOF.
- Byte dùng encoding **overlong** cho code point (bị UTF-8 chuẩn cấm).
- Sequence tạo surrogate code points hoặc code point ngoài phạm vi Unicode.
- Byte trên một charset khác bị giải mã nhầm UTF-8.

Ví dụ byte thiếu:

```java
byte[] incomplete = {(byte) 0xE2, (byte) 0x98};
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT);

try {
    decoder.decode(ByteBuffer.wrap(incomplete));
} catch (MalformedInputException ex) {
    System.out.println("Truncated UTF-8 detected");
}
```

Đoạn này là **mã minh họa**, cần import `ByteBuffer`, `CharsetDecoder`, `CodingErrorAction`, `MalformedInputException`. Overload `decode(ByteBuffer)` thực hiện một lần giải mã hoàn chỉnh, nên phần 2-byte chưa đủ bị coi là malformed khi kết thúc input. Trong streaming, gọi `decode(input, output, false)` trước EOF sẽ **chờ** byte tiếp theo thay vì báo sai ngay.

### Unicode replacement character không chỉ là chuyện thẩm mỹ

Nếu chương trình lưu `�` vào tên file, key hoặc chữ ký thay vì dữ liệu gốc, nhiều thứ có thể thay đổi:

- Hash/checksum byte.
- So sánh tên user/resource.
- JSON field name hoặc CSV header.
- Truy vấn database và khóa deduplication.
- Nội dung văn bản có ý nghĩa pháp lý, tài chính, y tế hoặc bảo mật.

Vì vậy ở các trường hợp yêu cầu chính xác, nên xử lý lỗi bằng `REPORT` hoặc xác minh encoding nguồn thay vì tự biến input lỗi thành “đã decode thành công”.

## 15. ByteBuffer: flip, compact, clear và các lỗi boundary

`ByteBuffer` có ba trạng thái quan trọng: `capacity`, `position` và `limit`.

### Sau read byte từ I/O

Buffer write mode:

```text
capacity = 8
position = 5
limit = 8
[41 E2 98 95 42 | ...]
```

`flip()` đặt limit bằng position hiện tại, position về 0 để decoder đọc byte hợp lệ:

```text
position = 0
limit = 5
[41 E2 98 95 42 | ...]
```

### Khi decoder chưa xử lý hết bytes

Giả sử cuối buffer có `E2 98` thiếu byte `95`. Sau decode, position trỏ tới hai byte chưa được consume.

`compact()` giữ hai byte đó, position chuyển tới 2, limit về capacity. Lượt I/O kế tiếp ghi nối thêm byte sau vị trí 2.

`clear()` trong tình huống này thì **không giữ nội dung chưa decode**, có thể khiến byte cũ bị ghi đè; đây là nguyên nhân phổ biến của ký tự `�` hoặc mất dữ liệu không ổn định theo buffer size.

### Decoder và CharBuffer cũng có ranh giới riêng

Với `CharBuffer` output quá nhỏ, `decode` trả OVERFLOW. Drain output và gọi `decode` tiếp. Đừng giải thích OVERFLOW là “file nén quá lớn” hay “byte UTF-8 sai”.

Nếu output CharBuffer có chỗ cho một UTF-16 unit nhưng code point kế tiếp cần surrogate pair gồm hai units, decoder có thể phải trả OVERFLOW thay vì đặt nửa cặp không hợp lệ. Chọn buffer đủ lớn để có thể chứa ít nhất cặp surrogate và luôn xử lý OVERFLOW.

## 16. Tự chẩn đoán bằng hex dump

Khi một ký tự bị hỏng, log chuỗi đã được `new String(...)` có thể đánh mất bằng chứng vì byte không hợp lệ đã bị thay. Hãy quan sát **byte gốc** ở một môi trường test/an toàn:

```java
byte[] data = "A☕B😀C".getBytes(StandardCharsets.UTF_8);
StringBuilder hex = new StringBuilder();

for (byte b : data) {
    if (!hex.isEmpty()) {
        hex.append(' ');
    }
    hex.append(String.format("%02X", b & 0xFF));
}

System.out.println(hex);
```

Snippet cần import `StandardCharsets`; có thể đặt trong `main`. `StringBuilder.isEmpty()` là phương thức có trên Java 17 (qua `CharSequence`/`StringBuilder` API tương ứng tùy runtime); để tránh ràng buộc đối với môi trường cũ, có thể thay bằng `hex.length() > 0`.

Đầu ra:

```text
41 E2 98 95 42 F0 9F 98 80 43
```

**Không log raw bytes của password, access token hay dữ liệu cá nhân trong production**. Với lỗi thực tế, ưu tiên log metadata có giới hạn, offset, charset dự kiến và sample bytes đã redacted theo policy.

### Thông tin chẩn đoán nên có

- Encoding/charset đã cấu hình ở cả writer và reader.
- File path/source ID, kích thước file và byte offset nơi phát hiện lỗi.
- Kích thước từng chunk và `ByteBuffer.position/limit`.
- CoderResult là `UNDERFLOW`, `OVERFLOW` hay `MALFORMED`.
- Có BOM hay không; BOM thuộc phần đầu file hay sau một prefix protocol khác.
- Chính sách `REPORT/REPLACE/IGNORE`.
- Dữ liệu có bị gzip/decompress, decrypt hoặc transform trước khi decode không.
- Có đoạn nào tự tạo `new String(chunk)` với charset mặc định không.
- Có logic xóa mọi `\uFEFF` hoặc normalize Unicode không kiểm soát không.

## 17. Chẩn đoán byte offset và char index

Nếu lỗi xảy ra ở byte offset 127, bạn không thể suy ra nó chính là Java `String.charAt(127)` khi dữ liệu dùng UTF-8.

Ví dụ:

```text
Text: A☕B
UTF-8:
  A: byte offset 0, length 1
  ☕: byte offset 1, length 3
  B: byte offset 4, length 1

Java UTF-16 char indexes:
  A index 0
  ☕ index 1
  B index 2
```

Với emoji vùng bổ sung, chênh lệch còn khác hơn vì 4 UTF-8 bytes → 2 UTF-16 units → 1 code point.

Khi báo lỗi parser, hãy nêu rõ offset là:

- **Byte offset** trong file/wire.
- **UTF-16 char index** trong Java String.
- **Code point index** của nội dung.
- **Dòng/cột logic** nếu parser đã định nghĩa chuẩn newline và Unicode.

Nếu một binary protocol có length prefix bằng byte, phải encode trước để tính length, và reader đọc đủ length byte rồi decode đúng **phần payload**, không tính bằng `String.length()`.

## 18. Byte length trong giao thức mạng

Sai lầm điển hình:

```java
String body = "Cà phê ☕";
int declaredLength = body.length();   // Sai nếu protocol yêu cầu byte count.
byte[] wire = body.getBytes(StandardCharsets.UTF_8);
```

Nếu giao thức có frame `[4-byte payload length][payload bytes]`, length phải là `wire.length`, không phải `body.length()`.

Mẫu đúng (mã minh họa):

```java
byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
if (bodyBytes.length > MAX_PAYLOAD_BYTES) {
    throw new IOException("Frame too large");
}
frame.putInt(bodyBytes.length);
frame.put(bodyBytes);
```

Các biến `body`, `MAX_PAYLOAD_BYTES`, `frame` cần được khai báo/cấp đủ capacity trước, và `frame` phải tuân theo `ByteOrder` đã thống nhất với peer. Ở phía đọc, sử dụng đúng số byte length đã công bố, đọc đủ frame (xử lý partial I/O), rồi decode **sau khi đủ byte**. Dù frame bị chia qua TCP packets hoặc file chunks, encoding vẫn có ranh giới logic rõ ràng.

Nếu giao thức dùng text delimiter như newline, còn phải quyết định cách escape, việc nhận `\r\n` bị chia qua buffers và giới hạn dòng. **Ranh giới network I/O không tự biến thành ranh giới record hoặc ký tự Unicode**.

## 19. Unicode normalization: giống về hình thức chưa chắc bằng bytes

Hai chuỗi có thể được hiển thị tương tự nhưng khác mã hóa Unicode:

```java
String a = "\u00E9";
String b = "e\u0301";

System.out.println(a.equals(b)); // false

String na = Normalizer.normalize(a, Normalizer.Form.NFC);
String nb = Normalizer.normalize(b, Normalizer.Form.NFC);
System.out.println(na.equals(nb)); // true
```

Đây là đoạn minh họa cần import `java.text.Normalizer`, chạy được trong method Java 17.

- **NFC** cố gắng tổ hợp canonical equivalents theo chuẩn Unicode.
- **NFD** tách canonical decomposition.
- NFKC/NFKD có compatibility mapping, có thể thay đổi ý nghĩa hoặc kiểu hiển thị của một số ký tự hơn canonical normalization.
- Không normalize âm thầm mọi dữ liệu như identifier, password hoặc chuỗi đã ký nếu protocol không quy định.
- Không coi normalization là phòng chống mọi homograph, spoofing hoặc confusable characters.

Để kiểm thử dữ liệu tiếng Việt, nên có cả dạng precomposed và combining marks, kiểm tra byte round-trip khi cần bảo toàn nguyên bản, và kiểm tra normalization riêng theo rule nghiệp vụ.

## 20. Test cases tối thiểu cho Unicode streaming

Một bộ kiểm thử nên có các chuỗi và tình huống sau:

| Trường hợp | Điều muốn chứng minh |
|---|---|
| ASCII `Hello` | Không cần multibyte, baseline |
| Tiếng Việt `Cà phê` | Unicode ngoài ASCII |
| `☕` chia sau byte 1 và byte 2 | Decoder giữ 1–2 byte còn thiếu |
| `😀` chia sau byte 1, 2 và 3 | Decoder giữ tối đa 3 byte đầu |
| UTF-8 BOM `EF BB BF` chia làm 3 chunks | Policy BOM áp dụng đúng một lần |
| Không BOM | Không vô tình xóa ký tự đầu tiên |
| U+FEFF ở giữa nội dung | Không xóa mọi U+FEFF |
| UTF-16BE/LE với BOM | Đúng endian theo format |
| UTF-16LE không BOM | Chỉ decode đúng khi charset đã được biết |
| Input UTF-8 thiếu byte cuối | `REPORT` phát hiện truncated input khi EOF |
| Byte continuation lẻ `80` | Malformed input đúng |
| Buffer output đầy | `OVERFLOW` được drain, không mất ký tự |
| Decoder chia byte với kích thước chunk 1, 2, 3, 4, 7... | Output bất biến theo cách phân khối |
| String có combining accents | Không lẫn equals với canonical equivalence |
| Emoji với surrogate pair | Không cắt đôi khi xử lý Java char[] |
| Giao thức length-prefixed UTF-8 | Length tính theo byte, không theo String.length |

### Property-style test: bất biến theo ranh giới chunk

Một nguyên tắc mạnh:

> Với cùng một dãy byte UTF-8 hợp lệ, output của decoder stateful phải giống nhau bất kể input được chia thành các chunk 1, 2, 3,... byte như thế nào (miễn là giữ đúng thứ tự byte và báo EOF đúng lúc).

Có thể viết test lặp các kích thước chunk cố định khác nhau, sau đó thêm kiểm thử random partition. Không cần “một packet = một message” để decode text đúng.

Tương tự, với chuỗi UTF-8 không hợp lệ, **chính sách lỗi** phải nhất quán: `REPORT` phát hiện input malformed/truncated, còn `REPLACE` tạo output được định nghĩa theo chính sách replacement; không âm thầm chấp nhận dữ liệu chỉ vì sự cố xảy ra ở boundary khác.

## 21. BOM và đầu vào có prefix/header nhị phân

Trong một số protocol, byte stream bắt đầu bằng **binary header** rồi mới đến một trường text. Khi đó BOM (nếu spec cho phép) phải được kiểm tra **tại đầu trường text**, không nhất thiết ở offset 0 của toàn bộ stream.

Ví dụ:

```text
[magic: 4 bytes][version: 1][textLength: 4][text UTF-8 bytes]
```

Nếu `text UTF-8 bytes` bắt đầu bằng `EF BB BF`, policy BOM áp dụng sau khi parser đã đọc đúng header và xác định vị trí payload. Nếu parser đọc toàn bộ byte stream qua `InputStreamReader` ngay từ byte 0, binary header có thể bị giải mã thành ký tự sai và làm lệch byte offset.

Vì vậy:

1. Parse **binary structure** theo byte trước.
2. Xác định byte range của text payload.
3. Chọn charset từ spec/metadata.
4. Áp policy BOM phù hợp tại **đầu payload**.
5. Decode đầy đủ range bằng stateful decoder hoặc đọc đủ bytes của field rồi decode một lần.

Không tự kết luận mọi `EF BB BF` xuất hiện giữa payload là BOM; nó cũng có thể là byte biểu diễn `U+FEFF` có chủ ý trong nội dung.

## 22. Khi nào decode từng chunk độc lập là hợp lệ?

Không phải mọi phân khối đều sai. Nếu **giao thức định nghĩa từng chunk là một chuỗi UTF-8 độc lập và hoàn chỉnh**, có length prefix rõ và sender bảo đảm không cắt một encoding sequence, thì có thể giải mã từng message riêng.

Ví dụ:

```text
Frame 1: [length=3]["☕" UTF-8 3 bytes]
Frame 2: [length=4]["😀" UTF-8 4 bytes]
```

Reader phải đọc đủ 3 hoặc 4 byte rồi mới tạo String. Nếu tầng network lại chia frame thành nhiều lần read, phải gom **đủ frame bytes** trước. Phần được phép decode độc lập là **message boundary do protocol định nghĩa**, không phải boundary do socket/file buffer ngẫu nhiên.

Một số text protocols như JSON Lines có delimiter rõ; cần parser xác định delimiter đúng theo charset và bảo vệ line length. Với các ký tự Unicode nhiều byte, một byte không thể được tự do hiểu là newline nằm giữa UTF-8 multibyte sequence; nhưng cần đảm bảo parser không nhầm framing và encoding theo một byte order khác.

## 23. Sai lầm thường gặp và cách sửa

1. **`new String(buffer, 0, n, UTF_8)` mỗi lần read byte rồi nối chuỗi.** Sai khi code point bị chia; dùng `InputStreamReader` hoặc `CharsetDecoder` stateful.
2. **Dùng `String.length()` làm số byte ghi lên wire.** Sai với UTF-8; encode trước rồi dùng `byte[].length`.
3. **Coi Java `char` là code point.** Không đúng với surrogate pair; dùng `codePoints()` hoặc API Character thích hợp.
4. **Gọi `ByteBuffer.clear()` khi decoder trả UNDERFLOW còn byte chưa đủ.** Làm mất bytes; dùng `compact()`.
5. **Quên `flip()` trước khi decode.** Decoder có thể đọc sai phạm vi hay không đọc gì.
6. **Không drain `CharBuffer` sau OVERFLOW.** Vòng lặp không tiến hoặc mất output.
7. **Gọi `decode(..., true)` sau mỗi chunk.** Khi chunk kết thúc giữa code point, decoder tưởng đó là EOF và báo malformed.
8. **Không gọi `flush` sau `decode(..., true)`.** Với các decoder stateful, có thể bỏ mất output/bước kết thúc.
9. **Sử dụng một CharsetDecoder cho nhiều stream cùng lúc.** Decoder có state và không được chia sẻ tùy tiện giữa các stream/thread.
10. **Không `reset()` decoder trước khi tái sử dụng cho một stream độc lập mới.** State và quy trình decoding có thể không còn hợp lệ.
11. **Coi `CodingErrorAction.REPLACE` là truyền dữ liệu chính xác.** Replacement đã làm mất thông tin, không dùng cho nội dung cần round-trip.
12. **Bỏ qua malformed bytes (`IGNORE`) mà không đánh giá tác động nghiệp vụ.** Có thể làm thay đổi identifiers/headers.
13. **Mặc định mọi file Unicode có BOM.** UTF-8 BOM là tùy chọn và nhiều format cấm BOM.
14. **Xóa U+FEFF ở mọi vị trí.** Nếu cần strip, chỉ xử lý phần đầu đúng theo spec.
15. **Nhầm BOM UTF-16BE/LE.** Endian sai làm nội dung vô nghĩa.
16. **Nhận diện UTF-16 trước UTF-32 khi hỗ trợ cả hai.** UTF-32LE BOM có prefix FF FE giống UTF-16LE; cần quy tắc match dài nhất.
17. **Cho rằng raw UTF-8 bytes của NFC và NFD giống nhau.** Có thể hiển thị giống nhưng byte/code point khác.
18. **Dựa vào log chuỗi đã decode để xác định byte lỗi.** Replacement có thể che mất byte gốc; quan sát hex an toàn.
19. **Đọc cả file không tin cậy bằng `readAllBytes` trước khi decode.** Dễ cạn bộ nhớ; dùng streaming với quota.
20. **Tưởng `InputStreamReader` trả grapheme clusters nguyên vẹn ở mỗi lần read.** Reader trả `char` units; tầng sau vẫn phải quản lý surrogate/grapheme khi chia char[].
21. **Không kiểm tra EOF cuối file.** UTF-8 bị cắt một nửa chỉ hiện lỗi khi biết chắc không còn byte nữa.
22. **Parser JSON/XML/CSV không thống nhất charset giữa writer/reader.** Cần xác định từ spec, không từ môi trường ngẫu nhiên.
23. **Normalize tất cả text mà không xem hợp đồng.** Có thể thay chữ ký, identifier hoặc dữ liệu cần bảo toàn bytes.
24. **Đoán charset từ extension file.** Tên file không cam kết content encoding.
25. **Cho rằng read của network trùng message boundary.** TCP là byte stream, phải framing riêng.

## 24. Bài tập thực hành

**Bài 1 — Đổi kích thước chunk.** Sửa ví dụ `UnicodeBoundaryDemo` từ 2 byte/lượt thành 1, 3, 4, 5 byte/lượt. Chứng minh `Split-safe equals: true` trong mọi lần nếu file và charset đúng. Không tạo decoder mới cho mỗi vòng.

**Bài 2 — Hỏng byte cuối.** Lấy UTF-8 của `"😀"` và bỏ byte cuối. Dùng `CharsetDecoder` với `REPORT`, gọi `decode(..., true)` khi EOF và xác nhận lỗi malformed. Sau đó thử `REPLACE` để thấy output không còn nguyên bản.

**Bài 3 — UTF-8 BOM bị chia ba lượt.** Ghi byte `EF BB BF 41`, dùng InputStream chỉ trả từng byte một. Đảm bảo detector không nhầm `EF` đơn lẻ là BOM hoàn chỉnh, và output sau policy là `A`.

**Bài 4 — UTF-16BE và UTF-16LE.** Tạo byte sequences của `"A☕"` với `UTF_16BE` và `UTF_16LE`. So sánh hex, giải mã bằng charset đúng, sau đó giải mã nhầm để quan sát khác biệt.

**Bài 5 — Cặp surrogate.** Đọc Unicode emoji thành Java char[]. Chia char[] ngay giữa high và low surrogate, sau đó thiết kế bộ xử lý codepoint giữ high surrogate tới lần nhận tiếp theo.

**Bài 6 — Binary length prefix.** Viết protocol `int32 byteLength + UTF-8 payload`. Truyền text `"Cà phê ☕"`, thử chia payload thành từng read ngẫu nhiên, kiểm tra cuối cùng String bằng bản gốc.

**Bài 7 — Normalization.** So sánh `"\u00E9"` và `"e\u0301"` về `equals`, số code point, byte UTF-8 và kết quả sau `Normalizer.Form.NFC`.

**Bài 8 — Diagnostics.** Khi phát hiện malformed UTF-8, log charset dự kiến, byte offset và chuỗi byte hex **đã redacted**, không log toàn bộ nội dung nhạy cảm. Viết test cho bytes `80` và `E2 98`.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Đọc hai byte `E2 98` rồi kết thúc **một lần read**, có đủ lý do báo UTF-8 hỏng chưa?  
**Không**, nếu byte stream chưa EOF. Đây có thể là prefix hợp lệ của code point ba byte. Decoder cần chờ byte tiếp theo.

**Câu 2.** Nếu đã biết **EOF thực sự** và chỉ còn `E2 98`, kết quả strict decoding?  
**Malformed input**, vì sequence chưa hoàn chỉnh.

**Câu 3.** Vì sao `new String(chunk1,UTF_8)+new String(chunk2,UTF_8)` có thể sai?  
**Vì mỗi decoder độc lập** không nhớ byte đầu của một code point nằm ở chunk trước.

**Câu 4.** `ByteBuffer.compact()` giúp gì trong một incremental decoder?  
**Giữ byte chưa được consume** khi đang chờ chunk tiếp theo và chuẩn bị vùng trống để append.

**Câu 5.** `CoderResult.OVERFLOW` là dữ liệu UTF-8 sai phải không?  
**Không.** Thường là output `CharBuffer` hết chỗ, cần drain rồi decode tiếp.

**Câu 6.** Chuỗi `"😀"` có `length() == 1` không?  
**Không**. `String.length() == 2` do cặp surrogate UTF-16, nhưng có 1 Unicode code point.

**Câu 7.** UTF-8 BOM gồm những byte nào?  
**EF BB BF**. UTF-8 không cần BOM để xác định endian.

**Câu 8.** Java UTF-8 decoder có luôn tự bỏ `EF BB BF` ở đầu không?  
**Không**. Nhiều API giải mã chuẩn đưa nó thành ký tự `U+FEFF`; cần policy rõ.

**Câu 9.** Có nên gọi `text.replace("\uFEFF","")` để xử lý BOM không?  
**Không theo mặc định**, vì thao tác đó xóa U+FEFF ở mọi vị trí. BOM là dấu ở **đầu stream/field**, không phải mọi ký tự U+FEFF.

**Câu 10.** Protocol gửi chuỗi UTF-8 có prefix byte length. Dùng `String.length()` được không?  
**Không**; phải encode rồi lấy số byte thực tế.

**Câu 11.** `InputStreamReader` giải mã UTF-8 đúng qua nhiều byte chunks có tự bảo đảm các lần `read(char[])` không chia đôi cặp surrogate không?  
**Không nên dựa vào điều đó**; tầng xử lý char units vẫn phải chịu trách nhiệm về code points/grapheme boundaries.

**Câu 12.** Vì sao `REPORT` hữu ích trong kiểm thử dữ liệu đầu vào?  
**Nó làm lỗi encoding lộ rõ**, thay vì âm thầm chèn replacement rồi khiến dữ liệu sai được xem là hợp lệ.

**Câu 13.** Hai chuỗi nhìn như `é` có nhất thiết có cùng bytes UTF-8 không?  
**Không**. Một chuỗi có thể là U+00E9, chuỗi kia là U+0065 U+0301.

**Câu 14.** Khi hỗ trợ UTF-16 và UTF-32 BOM, tại sao cần kiểm tra BOM dài nhất trước?  
**Để không hiểu nhầm prefix `FF FE` của UTF-32LE** là BOM hoàn chỉnh của UTF-16LE.

## 26. Checklist triển khai và kiểm thử

- [ ] Xác định chính xác charset từ giao thức hoặc metadata đáng tin cậy, ưu tiên UTF-8 khi spec cho phép.
- [ ] Ghi rõ encoding ở writer và reader; không phụ thuộc charset mặc định.
- [ ] Phân biệt byte offset, Java UTF-16 index, code point và grapheme.
- [ ] Không decode riêng từng byte chunk chưa chắc chứa một message hoàn chỉnh.
- [ ] Với text stream đơn giản, dùng `InputStreamReader`/`BufferedReader` cùng charset.
- [ ] Với binary protocol/ByteBuffer, dùng stateful `CharsetDecoder` và giữ byte dư bằng `compact()`.
- [ ] Đảm bảo `decode(..., true)` **chỉ khi EOF**, sau đó `flush` đúng protocol.
- [ ] Drain output buffer khi OVERFLOW, không mất byte/input state.
- [ ] Chọn `REPORT` cho dữ liệu yêu cầu chính xác; log và xử lý lỗi rõ.
- [ ] Đặt giới hạn bytes/ký tự/CPU/timeouts phù hợp nguồn tin cậy.
- [ ] Có policy BOM: cho phép, loại ở đầu, hoặc từ chối theo định dạng.
- [ ] Với UTF-16, xác định BE/LE; không đoán BOM khi format đã cố định charset.
- [ ] Không strip `U+FEFF` ở giữa nội dung một cách mù quáng.
- [ ] Khi framing network, tính length theo byte sau encoding.
- [ ] Kiểm thử với tiếng Việt, emoji, dấu tổ hợp, UTF-8 BOM, EOF giữa code point.
- [ ] Kiểm thử mọi kích thước chunk nhỏ: 1, 2, 3, 4, ... byte và random splits.
- [ ] So sánh byte round-trip khi yêu cầu bảo toàn chính xác.
- [ ] Đảm bảo normalization theo hợp đồng; không tự động biến NFD thành NFC khi không được phép.
- [ ] Định nghĩa hành vi trước malformed bytes và sai encoding.
- [ ] Không log raw data nhạy cảm trong thông điệp chẩn đoán.

## 27. Tóm tắt

- **Unicode là tập mã code point; UTF-8/UTF-16 là cách biểu diễn chúng thành các đơn vị lưu/truyền.**
- **Một lần đọc byte không tương đương một Unicode character.** UTF-8 từ 1–4 byte/code point, nên phải cho phép sequence nằm qua nhiều chunks.
- **Không dùng `new String` độc lập cho từng chunk tùy ý.** Dùng `InputStreamReader` hoặc `CharsetDecoder` giữ state.
- **`flip()` để chuyển sang đọc; `compact()` giữ byte chưa đủ; `clear()` có thể làm mất chúng.**
- **Báo EOF chỉ khi stream kết thúc**, xử lý decode final + flush và báo malformed khi input bị cắt.
- **BOM UTF-8 là EF BB BF**, tùy chọn; UTF-16 BOM cho biết endian. Policy BOM phải theo format, chỉ áp vào đầu stream/payload.
- **Byte count ≠ `String.length()` ≠ code point count**, đặc biệt khi có tiếng Việt/emoji/combining marks.
- **Kiểm thử ranh giới và error policy là bắt buộc** để không biến dữ liệu sai thành các ký tự thay thế mà không ai phát hiện.

### Tài liệu API Java SE 17

- [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CoderResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
