# Phân biệt charset với Base64 và nén dữ liệu trong Java

**Charset, Base64 và nén dữ liệu giải quyết ba bài toán khác nhau** dù đều có thể biến đổi dãy byte:

- **Charset** quy định cách **mã hóa văn bản thành byte** và **giải mã byte thành văn bản**, chẳng hạn UTF-8.
- **Base64** biến **byte bất kỳ thành biểu diễn văn bản ASCII** có thể truyền qua môi trường chỉ nhận ký tự an toàn, rồi chuyển ngược về chính các byte đó.
- **Nén dữ liệu** biến **byte thành dạng byte được biểu diễn gọn hơn khi có thể**, và giải nén khôi phục byte gốc; kết quả nén không nhất thiết nhỏ hơn đầu vào.

Một chuỗi Base64 không cho biết văn bản ban đầu dùng charset nào; một luồng GZIP cũng không tự biến byte thành ký tự. Chọn sai lớp biến đổi sẽ tạo lỗi kiểu “chữ tiếng Việt bị vỡ”, “không giải mã được”, “file giải nén lỗi” hoặc “tưởng đã mã hóa bảo mật nhưng dữ liệu vẫn đọc được”.

## 1. Nhìn từ kiểu dữ liệu và mục đích

| Khái niệm | Đầu vào | Đầu ra | Mục đích | Có làm nhỏ dữ liệu không? |
| --- | --- | --- | --- | --- |
| Charset, ví dụ UTF-8 | Văn bản Unicode | Byte đã mã hóa | Biểu diễn ký tự thành byte để lưu/truyền | Không phải kỹ thuật nén |
| Giải mã charset | Byte hợp lệ theo charset | Văn bản Unicode | Khôi phục ký tự từ byte | Không phải giải nén |
| Base64 encode | Byte bất kỳ | Dãy ký tự ASCII | Đưa dữ liệu nhị phân qua kênh văn bản | Thường **tăng** dung lượng |
| Base64 decode | Dãy ký tự Base64 hợp lệ | Byte ban đầu | Phục hồi byte từ biểu diễn Base64 | Không phải giải nén |
| Nén lossless, ví dụ GZIP | Byte bất kỳ | Byte đã nén | Giảm lượng byte nếu dữ liệu có cấu trúc lặp/phù hợp | Thường giảm với dữ liệu thích hợp; có thể tăng |
| Giải nén GZIP | Byte GZIP hợp lệ | Byte ban đầu | Khôi phục chính xác byte gốc | Kết quả có thể lớn hơn rất nhiều |

Với các thao tác thông thường trong Java:

```text
               charset UTF-8
"Chào Java"  --------------------> byte[] UTF-8
     ^                                  |
     |                                  | Base64 encode
     | UTF-8 decode                     v
     +----------- byte[] <--------- "Q2jDoG8gSmF2YQ=="
                    ^                Base64 decode
                    |
          GZIP là một cách biến đổi
          byte[] -> byte[] riêng biệt
```

Sơ đồ chỉ mô tả mối quan hệ, không có nghĩa GZIP tự xuất hiện trong chuỗi Base64 bên phải. Khi kết hợp các bước, **thứ tự thực hiện và thứ tự đảo ngược** là yếu tố quyết định để lấy lại dữ liệu.

## 2. Charset: ý nghĩa của byte trong văn bản

Một `Charset` xác định quy tắc ánh xạ giữa ký tự Unicode và các byte, với quá trình encode/decode. Trong Java, `String` chứa văn bản dưới dạng các đơn vị mã UTF-16; còn file, socket hoặc `OutputStream` vận chuyển byte. `String.getBytes(StandardCharsets.UTF_8)` và `new String(bytes, StandardCharsets.UTF_8)` là hai hướng chuyển đổi thường gặp.

Ví dụ:

```java
import java.nio.charset.StandardCharsets;

String text = "Café";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(utf8, StandardCharsets.UTF_8);
```

Đoạn này là minh họa cần đặt trong một class/phương thức. Với `Café`, dãy byte UTF-8 (viết dưới dạng hexadecimal) là:

```text
43 61 66 C3 A9
 C  a  f   é
```

Chữ `é` dùng **hai byte** `C3 A9`, không phải hai ký tự. Trong UTF-8, ký tự ASCII thường có 1 byte, ký tự khác có thể dùng 2, 3 hoặc 4 byte. Ngược lại, một `char` của Java là một đơn vị UTF-16; ký tự ngoài BMP như `🙂` dùng cặp surrogate, tức hai `char`. Vì vậy phải phân biệt **byte**, **`char`** và **Unicode code point**.

Nếu chọn nhầm charset khi *decode*:

```java
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
```

Chuỗi `Café` có thể trở thành `CafÃ©`. Đây là **lỗi giải mã charset**, không liên quan đến Base64 hoặc nén. Không thể sửa đúng bằng cách “Base64 thêm một lần” hoặc “giải nén”.

Các nguyên tắc cần nhớ:

1. Charset đúng phải đến từ quy ước dữ liệu, giao thức, metadata đáng tin hoặc cấu hình nguồn/đích; **không tự đoán** charset từ kết quả hiển thị.
2. Ghi rõ `StandardCharsets.UTF_8` khi định dạng yêu cầu UTF-8. Tránh phụ thuộc default charset nếu dữ liệu cần tương thích giữa các môi trường.
3. Thao tác trên dữ liệu nhị phân (ảnh, ZIP, GZIP, byte đã mã hóa) thì giữ `byte[]` hoặc `InputStream`; không gọi `new String(binaryBytes, UTF_8)` chỉ để “chứa dữ liệu”.
4. Nếu byte lỗi hoặc ký tự không được charset hỗ trợ, encode/decode có thể **thay thế** dữ liệu hoặc ném lỗi tùy API/chính sách `CodingErrorAction`. Muốn kiểm tra nghiêm ngặt, dùng `CharsetDecoder`/`CharsetEncoder` được cấu hình `REPORT`.

## 3. Base64: biểu diễn byte bằng ký tự ASCII

Base64 chuẩn thường dùng bảng 64 ký tự:

```text
A-Z   a-z   0-9   +   /
```

Nó mã hóa từng nhóm **3 byte đầu vào thành 4 ký tự Base64**; khi phần cuối không đủ 3 byte, biểu diễn có thể có dấu đệm `=`. Vì vậy kích thước Base64 chuẩn có padding xấp xỉ **4/3** kích thước byte gốc, chưa tính thông tin bao bọc hoặc xuống dòng:

```text
byte[] { 0x4D, 0x61, 0x6E }    ASCII: "Man"
                |
                | Base64 encode
                v
             "TWFu"
                |
                | Base64 decode
                v
byte[] { 0x4D, 0x61, 0x6E }
```

**Base64 không sử dụng charset của văn bản gốc để hiểu ký tự**; nó chỉ biến dãy byte thành biểu diễn ASCII và quay lại. Với file ảnh, đầu vào vẫn là byte ảnh, không phải `String`.

Trong Java:

```java
import java.util.Base64;

byte[] rawBytes = /* dữ liệu nhị phân có sẵn */;
String encoded = Base64.getEncoder().encodeToString(rawBytes);
byte[] decoded = Base64.getDecoder().decode(encoded);
```

Đây là đoạn minh họa cần biến `rawBytes` được cung cấp từ nơi khác. `decoded` khớp với `rawBytes` nếu Base64 hợp lệ. `Base64.getDecoder().decode(...)` có thể ném `IllegalArgumentException` khi biểu diễn Base64 sai.

Nếu đầu vào ban đầu là văn bản, **phải chọn charset trước khi Base64**:

```java
String message = "Xin chào";
String encoded = Base64.getEncoder().encodeToString(
        message.getBytes(StandardCharsets.UTF_8));

byte[] raw = Base64.getDecoder().decode(encoded);
String restored = new String(raw, StandardCharsets.UTF_8);
```

`StandardCharsets` và `Base64` cần import tương ứng. Chú ý: `Base64.decode` chỉ trả về **byte**, còn `new String(..., UTF_8)` mới quyết định cách diễn giải byte thành ký tự.

### Chọn biến thể Base64

`java.util.Base64` có các biến thể đáp ứng bối cảnh khác nhau:

| Java API | Đặc điểm | Trường hợp điển hình |
| --- | --- | --- |
| `Base64.getEncoder()` / `getDecoder()` | Bảng chuẩn có `+`, `/` và padding mặc định | Nội dung Base64 thông thường |
| `Base64.getUrlEncoder()` / `getUrlDecoder()` | Dùng `-`, `_` thay cho `+`, `/` | Token/thành phần URL theo format cho phép Base64URL |
| `Base64.getMimeEncoder()` / `getMimeDecoder()` | Hỗ trợ biểu diễn MIME xuống dòng | MIME/email theo quy ước tương ứng |

Không tự hoán đổi hai bộ alphabet khi hệ thống gửi/nhận yêu cầu định dạng cố định. Padding có thể được bỏ bằng `withoutPadding()` khi giao thức cho phép; bên nhận phải tuân thủ đúng chuẩn biểu diễn đã chọn. **Base64 không phải mã hóa bảo mật**: bất kỳ ai có chuỗi Base64 hợp lệ đều có thể decode mà không cần khóa.

## 4. Nén: biến đổi byte để giảm dung lượng khi có thể

Nén **lossless** như GZIP cố biểu diễn cùng dữ liệu bằng ít byte hơn dựa trên mẫu lặp và cấu trúc dữ liệu. Khi giải nén thành công, byte đầu ra phải **giống chính xác** byte trước khi nén.

```text
byte[] nguyên bản
      |
      | GZIP compress
      v
byte[] GZIP (binary, gồm thông tin định dạng và dữ liệu nén)
      |
      | GZIP decompress
      v
byte[] nguyên bản
```

Ví dụ API chuẩn Java:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

static byte[] gzip(byte[] input) throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    try (GZIPOutputStream compressor = new GZIPOutputStream(out)) {
        compressor.write(input);
    }
    return out.toByteArray();
}

static byte[] gunzip(byte[] compressed) throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    try (GZIPInputStream decompressor = new GZIPInputStream(
            new ByteArrayInputStream(compressed))) {
        decompressor.transferTo(out);
    }
    return out.toByteArray();
}
```

Hai phương thức này cần đặt trong một class. `GZIPOutputStream.close()` hoàn tất luồng GZIP, vì vậy `out.toByteArray()` chỉ được gọi sau khi khối `try-with-resources` đóng compressor. `GZIPInputStream` phải được cung cấp byte **thực sự theo định dạng GZIP**; nó không phải một công cụ “giải mã charset”.

Vì GZIP chứa header/trailer và metadata phục vụ giải nén/kiểm tra, với văn bản ngắn hoặc dữ liệu đã nén, **kết quả có thể lớn hơn đầu vào**. Các thuật ngữ và format cũng cần tách bạch:

- **GZIP** (ví dụ `GZIPInputStream`) là định dạng dòng nén theo quy cách GZIP, không phải file ZIP nhiều entry.
- **ZIP** (ví dụ `ZipInputStream`/`ZipOutputStream`) là định dạng container lưu nhiều entry và metadata.
- **DEFLATE** là thuật toán nén được dùng trong các format khác nhau; không nên giả định “cùng thuật toán” thì có thể mở tùy ý bằng bất kỳ lớp `GZIP`, `ZIP` hoặc `Inflater` nào.
- Nén **lossless** khác với nén có mất mát như một số codec ảnh/âm thanh. Trong xử lý `byte[]` và trao đổi dữ liệu cần khôi phục chính xác, phải chọn nén lossless.

## 5. Khi kết hợp: thứ tự tạo dữ liệu và khôi phục

Giả sử phải gửi **văn bản tiếng Việt**, muốn nén, nhưng kênh truyền chỉ nhận một chuỗi ký tự Base64. Pipeline đúng:

```text
CHIỀU GỬI
String Unicode
  -- UTF-8 encode --> byte[] UTF-8
  -- GZIP compress --> byte[] GZIP
  -- Base64 encode --> String ASCII Base64

CHIỀU NHẬN (ĐẢO THỨ TỰ)
String ASCII Base64
  -- Base64 decode --> byte[] GZIP
  -- GZIP decompress --> byte[] UTF-8
  -- UTF-8 decode --> String Unicode
```

Dữ liệu GZIP vốn là byte nhị phân. Ta chỉ đưa qua Base64 **nếu** giao thức đòi biểu diễn bằng chuỗi văn bản (chẳng hạn một trường JSON chứa Base64). Trong giao thức hỗ trợ binary, có thể gửi byte GZIP trực tiếp và bỏ qua Base64.

GZIP nên áp dụng trên byte văn bản **trước** Base64: Base64 làm tăng số ký tự và có thể giảm hiệu quả nén hoặc tạo thêm công việc. Tuy vậy, hiệu quả thực tế phụ thuộc dữ liệu và thiết lập, vì vậy đừng khẳng định mọi lần nén đều giảm kích thước.

### Ví dụ đầu-cuối Java 17+ chạy được

Ví dụ dùng cả ba biến đổi, sau đó giải theo thứ tự ngược. Ngoài ra chương trình kiểm tra trường hợp **chọn sai charset** để chỉ ra rằng giải được Base64 không đồng nghĩa đọc đúng tiếng Việt.

Lưu file đúng tên **`TextTransformsDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class TextTransformsDemo {

    public static void main(String[] args) throws IOException {
        String sourceText = "Chào Java ☕";

        // Bước 1: Charset encode (String -> byte UTF-8).
        byte[] utf8 = sourceText.getBytes(StandardCharsets.UTF_8);

        // Base64 riêng lẻ: không có tác dụng nén.
        String b64Text = Base64.getEncoder().encodeToString(utf8);
        byte[] decodedB64 = Base64.getDecoder().decode(b64Text);

        System.out.println("Source UTF-8 bytes: " + utf8.length);
        System.out.println("Base64 text length: " + b64Text.length());
        System.out.println("Base64 round-trip bytes equal: " +
                Arrays.equals(utf8, decodedB64));

        // Bước 2: GZIP (byte UTF-8 -> byte GZIP).
        ByteArrayOutputStream compressedOut = new ByteArrayOutputStream();
        try (GZIPOutputStream zipper =
                     new GZIPOutputStream(compressedOut)) {
            zipper.write(utf8);
        }
        byte[] compressed = compressedOut.toByteArray();

        // Bước 3: Base64 (byte GZIP -> chuỗi ASCII).
        String transmitted = Base64.getEncoder()
                .encodeToString(compressed);

        // Bước 4: đảo chiều: Base64 -> GZIP bytes.
        byte[] receivedCompressed =
                Base64.getDecoder().decode(transmitted);

        // Bước 5: giải nén -> byte UTF-8.
        ByteArrayOutputStream restoredOut = new ByteArrayOutputStream();
        try (GZIPInputStream unzipper = new GZIPInputStream(
                new ByteArrayInputStream(receivedCompressed))) {
            unzipper.transferTo(restoredOut);
        }
        byte[] restoredBytes = restoredOut.toByteArray();

        // Bước 6: Charset decode (byte UTF-8 -> String).
        String restoredText =
                new String(restoredBytes, StandardCharsets.UTF_8);

        System.out.println("GZIP + Base64 round-trip bytes equal: " +
                Arrays.equals(utf8, restoredBytes));
        System.out.println("Restored text: " + restoredText);

        // Cùng byte, charset sai -> kết quả ký tự sai.
        String decodedWrongly =
                new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("Wrong charset changes text: " +
                !sourceText.equals(decodedWrongly));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên, dùng terminal lưu được UTF-8:

```bash
javac -encoding UTF-8 TextTransformsDemo.java
java TextTransformsDemo
```

**Stdout chính xác:**

```text
Source UTF-8 bytes: 14
Base64 text length: 20
Base64 round-trip bytes equal: true
GZIP + Base64 round-trip bytes equal: true
Restored text: Chào Java ☕
Wrong charset changes text: true
```

Vì sao kết quả là như vậy?

- Chuỗi `"Chào Java ☕"` chiếm **14 byte UTF-8**: `Ch` = 2, `à` = 2, `o` = 1, khoảng trắng = 1, `Java` = 4, khoảng trắng = 1, `☕` = 3. Tổng `2 + 2 + 1 + 1 + 4 + 1 + 3 = 14`.
- Base64 chuẩn với padding của 14 byte cần `4 × ceil(14 / 3) = 20` ký tự ASCII. Base64 chỉ tạo biểu diễn văn bản; byte sau decode phải giống byte trước encode.
- GZIP rồi Base64, sau đó decode Base64 và giải nén GZIP, khôi phục **đúng từng byte**: `Arrays.equals` trả `true`. Việc so sánh `byte[]` là bằng chứng mạnh hơn chỉ nhìn dòng chữ hiển thị.
- Giải mã đúng UTF-8 khôi phục `"Chào Java ☕"`. Dùng ISO-8859-1 trên chính byte UTF-8 đó làm sai chữ có dấu và ký tự `☕`.

Chương trình cố ý **không in kích thước byte GZIP**, vì bài học là sự phân biệt ba cơ chế, còn byte GZIP dài bao nhiêu có thể phụ thuộc bản triển khai, mức nén và dữ liệu. Không được dùng ví dụ ngắn này để kết luận GZIP luôn giảm kích thước.

## 6. Chọn API nào trong một bài toán thực tế?

| Tình huống | Đúng hướng xử lý |
| --- | --- |
| Ghi nội dung Unicode vào file UTF-8 | `text.getBytes(UTF_8)` rồi ghi byte, hoặc `OutputStreamWriter` / `Files.writeString` với UTF-8 |
| Đọc file văn bản UTF-8 | `InputStreamReader(input, UTF_8)` / `Files.newBufferedReader(path, UTF_8)` |
| Gửi ảnh trong trường JSON Base64 theo hợp đồng API | Đọc byte ảnh rồi `Base64.getEncoder().encodeToString(bytes)` |
| Nhận trường JSON Base64 chứa ảnh | `Base64.getDecoder().decode(value)`, rồi xử lý như byte ảnh; **không** ép thành UTF-8 |
| Gửi file nhị phân qua kênh hỗ trợ binary | Gửi byte trực tiếp; không cần charset hoặc Base64 |
| Nén một luồng byte theo định dạng GZIP | `GZIPOutputStream`; bên nhận dùng `GZIPInputStream` |
| Gửi văn bản vừa nén vừa ở dạng Base64 | UTF-8 encode → GZIP → Base64; nhận thì đảo ngược |
| Giải nội dung ZIP nhiều file | Dùng `ZipInputStream` hoặc API ZIP thích hợp; không dùng `GZIPInputStream` |
| Tăng tính bí mật của dữ liệu | Dùng **mã hóa mật mã** phù hợp, ví dụ TLS khi truyền hoặc cơ chế encryption xác thực; Base64 và GZIP không bảo vệ bí mật |

### Ví dụ đọc một trường Base64 trong JSON

Một API có thể quy định trường `payload` chứa **Base64 của byte UTF-8**, không hề nén. Sau khi parser JSON đã lấy ra `String payload`:

```java
byte[] bytes = Base64.getDecoder().decode(payload);
String text = new String(bytes, StandardCharsets.UTF_8);
```

Đây là đoạn mã minh họa cần `payload`, import `Base64` và `StandardCharsets`. **Không gọi `GZIPInputStream`** nếu hợp đồng API không nói dữ liệu đã nén GZIP. Ngược lại, nếu API quy định “Base64 của GZIP”, cần thêm đúng bước giải nén sau Base64 decode rồi mới giải mã charset.

## 7. Phân biệt “encoding” với “encryption”

Cụm “mã hóa” trong tiếng Việt có thể chỉ *character encoding*, *binary-to-text encoding* hoặc *encryption*, nhưng chúng có mục tiêu rất khác nhau:

- **Character encoding** như UTF-8: biểu diễn chữ thành byte theo quy tắc chung, không có khóa bí mật.
- **Binary-to-text encoding** như Base64: biểu diễn byte thành ký tự an toàn theo quy tắc chung, không có khóa bí mật.
- **Compression** như GZIP: giảm độ dài biểu diễn trong các trường hợp phù hợp, không có khóa bí mật.
- **Encryption (mật mã)**: dùng khóa và thuật toán mật mã để bảo vệ nội dung. Ví dụ TLS bảo vệ dữ liệu khi truyền; mã hóa có xác thực còn cung cấp kiểm tra tính toàn vẹn và xác thực theo đặc tính thuật toán/giao thức.

Một chuỗi Base64 “trông khó đọc” vẫn có thể decode được bằng công cụ công khai. GZIP không phải encryption: ai có dữ liệu GZIP hợp lệ đều có thể giải nén. Nếu cần giữ bí mật, **không dựa vào Base64 hoặc GZIP**.

## 8. Các lỗi hay gặp và cách kiểm chứng

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Chào` trở thành ký tự lạ như `ChÃ o` | Byte UTF-8 được decode theo charset khác | Xác định charset thực tế; decode lại từ byte gốc |
| Base64 decode thành công nhưng text sai | Base64 phục hồi byte đúng, nhưng charset decode sai | So sánh byte; dùng đúng charset ở bước tiếp theo |
| `IllegalArgumentException` khi Base64 decode | Chuỗi sai alphabet/padding/định dạng hoặc dùng nhầm Base64URL | Kiểm tra format nguồn và decoder tương ứng |
| `ZipException: Not in GZIP format` | Đầu vào không phải GZIP, hoặc chưa Base64 decode, hoặc bị hỏng | Kiểm tra thứ tự và format thực tế |
| Nén dữ liệu ngắn ra file lớn hơn | Header/trailer và overhead vượt phần tiết kiệm | Thử trên dữ liệu thực, không coi tăng kích thước là lỗi |
| Ghi byte GZIP bằng `new String(gzipBytes, UTF_8)` | Dữ liệu nhị phân bị giải mã như văn bản và có thể bị thay thế | Ghi binary trực tiếp; nếu cần text, Base64 encode byte GZIP |
| Gửi chuỗi Base64 để “giấu” mật khẩu | Base64 chỉ là biểu diễn công khai | Dùng giao thức bảo vệ thích hợp; không coi Base64 là bí mật |
| Mở file `.zip` bằng `GZIPInputStream` | ZIP và GZIP là format khác nhau | Chọn đúng bộ đọc theo định dạng |
| Nén sau Base64 và kết luận mọi trường hợp nhỏ hơn | Base64 không phải nén, hiệu quả phụ thuộc dữ liệu | Nén byte trước Base64 khi cần cả hai; đo kết quả |
| Không giới hạn kích thước dữ liệu giải nén | Một đầu vào nén nhỏ có thể bung thành lượng byte rất lớn | Với dữ liệu không tin cậy, giới hạn byte đầu ra, thời gian, bộ nhớ và xử lý lỗi |

Khi cần chứng minh một chu trình khôi phục *lossless* là đúng, kiểm tra **byte ban đầu và byte sau toàn bộ chuỗi đảo ngược** bằng `Arrays.equals` cho dữ liệu nhỏ, hoặc hash/checksum, kích thước và quy trình xác minh đáng tin với dữ liệu lớn. Đừng chỉ nhìn hai chuỗi có vẻ giống nhau trên terminal: terminal, normalization Unicode và charset sai có thể che khuất khác biệt.

## 9. Câu hỏi tự kiểm tra

1. **Vì sao `Base64.decode` không thể tự biết “đây là tiếng Việt”?** Vì nó chỉ biết quy tắc khôi phục byte. Bên gọi phải biết charset để giải mã byte thành ký tự.
2. **UTF-8 có nén tốt hơn GZIP không?** Không thể so sánh như hai thuật toán nén: UTF-8 là character encoding, GZIP là nén lossless byte.
3. **Base64 có giữ nguyên dãy byte qua encode/decode không?** Có, với cặp encoder/decoder phù hợp và đầu vào biểu diễn hợp lệ; nó không có mục tiêu giữ nguyên số ký tự hay dung lượng.
4. **Tại sao 14 byte UTF-8 có thể thành 20 ký tự Base64?** Vì chuẩn Base64 dùng 4 ký tự cho mỗi nhóm tối đa 3 byte, thêm padding khi cần.
5. **Nhận một payload “Base64 của GZIP của UTF-8” thì xử lý theo thứ tự nào?** Base64 decode → GZIP decompress → UTF-8 decode.
6. **Có nên Base64 hóa byte ảnh rồi chuyển qua `String.getBytes(UTF_8)`?** Nếu giao thức cần truyền dạng text bằng byte UTF-8 thì có thể encode chuỗi Base64 ASCII ra byte UTF-8; nhưng việc này không làm ảnh thành văn bản Unicode. Khi nhận phải đảo đủ các bước và không decode trực tiếp byte ảnh như text.
7. **Vì sao GZIP không bảo mật?** Nó là format nén không dùng khóa bí mật; bất kỳ người nhận có dữ liệu GZIP hợp lệ đều có thể giải nén.

**Ghi nhớ ba câu:** **Charset quyết định byte đại diện cho chữ gì. Base64 quyết định byte được trình bày dưới dạng ký tự an toàn ra sao. Nén quyết định byte có thể được lưu/truyền gọn hơn như thế nào.** Muốn khôi phục chính xác, phải áp dụng các bước ngược theo thứ tự đảo và với đúng charset/format.