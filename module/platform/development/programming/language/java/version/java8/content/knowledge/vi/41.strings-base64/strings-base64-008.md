# Stream wrapper để encode, decode dữ liệu Base64 trong Java

Trong chủ đề **Chuỗi và Base64**, hai API quan trọng là **`Base64.Encoder.wrap(OutputStream)`** và **`Base64.Decoder.wrap(InputStream)`**. Chúng biến một stream bình thường thành stream có khả năng encode hoặc decode Base64 **trong lúc dữ liệu chảy qua**, rất phù hợp khi truyền file, xử lý attachment, đọc dữ liệu nhị phân từ nguồn I/O và lưu nội dung qua một kênh chỉ hỗ trợ ký tự.

Khác với `encodeToString(byte[])` hoặc `decode(String)`, hai phương thức `wrap` không yêu cầu bạn gom toàn bộ nội dung vào một mảng ở bộ nhớ trước khi xử lý. Nhưng chúng cũng có những quy tắc dễ quên: **encoder bọc đầu ra, decoder bọc đầu vào; encoder phải được đóng để hoàn tất byte cuối/padding; đóng wrapper sẽ đóng stream bên dưới; decoder stream báo lỗi qua IOException; Basic, URL và MIME không thể thay thế tùy tiện**.

Bài này giới thiệu nguyên lý Base64, chiều hoạt động của wrapper, cách copy dữ liệu theo từng phần, lựa chọn alphabet, charset, ownership, flush/close, tình huống sai định dạng, kiểm soát tài nguyên và chương trình Java **JDK17+** độc lập có stdout đã chạy kiểm chứng. Các API Base64 là API Java 8 hiện vẫn được hỗ trợ; tiện ích JDK9+ được chú thích rõ khi sử dụng.

## 1. Base64 là chuyển đổi byte sang ký tự, không phải mã hóa bảo mật

Base64 biểu diễn dữ liệu nhị phân bằng bảng chữ cái gồm 64 ký tự. Cứ 3 byte (24 bit) có thể chuyển thành 4 ký tự Base64. Với nhóm thiếu byte, encoder mặc định thêm `=` để đủ bốn ký tự.

~~~text
Raw bytes:   M      -> Base64: TQ==
Raw bytes:   Ma     -> Base64: TWE=
Raw bytes:   Man    -> Base64: TWFu
Raw bytes:   Many   -> Base64: TWFueQ==
~~~

Chi phí lưu trữ của Basic Base64 có padding thường là `4 * ceil(n / 3)` byte ký tự ASCII cho `n` byte gốc, chưa tính line breaks nếu dùng MIME. Khi dữ liệu lớn, output tăng xấp xỉ một phần ba. Base64 **không phải compression, hashing, encryption hoặc signing**. Ai nhận được chuỗi Base64 có thể giải mã mà không cần khóa.

Base64 hữu ích khi format hoặc giao thức yêu cầu dữ liệu dạng văn bản, nhưng không nên thêm Base64 vào mọi binary HTTP body nếu kênh đã hỗ trợ bytes gốc. Tính toàn vẹn, xác thực và bảo mật truyền tải cần cơ chế tương ứng như checksum/MAC/chữ ký, authentication và TLS.

## 2. Hai chiều wrapper phải hiểu chính xác

### 2.1. Encode là ghi byte gốc vào một OutputStream được bọc

~~~text
InputStream chứa bytes gốc
            |
            | copy bytes
            v
OutputStream bọc bằng Base64.Encoder.wrap(...)
            |
            | ghi các byte ký tự Base64
            v
OutputStream đích: file, socket, buffer ...
~~~

Method:

~~~java
OutputStream encoded = Base64.getEncoder().wrap(target);
~~~

`target` ở đây là một `OutputStream` có sẵn. Caller ghi **byte gốc** vào `encoded.write(...)`. Encoder không yêu cầu caller tự chia các byte theo nhóm ba; nó lưu trạng thái còn dư giữa các lần ghi và xuất Base64 xuống target.

~~~java
ByteArrayOutputStream result = new ByteArrayOutputStream();
try (OutputStream out = Base64.getEncoder().wrap(result)) {
    out.write("Man".getBytes(StandardCharsets.US_ASCII));
}
String ascii = result.toString(StandardCharsets.US_ASCII);
// ascii == "TWFu"
~~~

Đây là đoạn code trong một phương thức với import `java.io.*`, `java.util.Base64` và `java.nio.charset.StandardCharsets`. `ByteArrayOutputStream` dùng để minh họa dữ liệu nhỏ; mục tiêu streaming file lớn sẽ dùng `Files.newOutputStream`.

### 2.2. Decode là đọc bytes gốc từ một InputStream được bọc

~~~text
InputStream nguồn chứa ký tự Base64
            |
            v
InputStream bọc bằng Base64.Decoder.wrap(...)
            |
            | đọc ra bytes nhị phân gốc
            v
OutputStream đích: file, buffer, socket ...
~~~

Method:

~~~java
InputStream decoded = Base64.getDecoder().wrap(source);
~~~

`source` là một `InputStream` chứa bytes **ký tự Base64**, không phải bytes gốc.

~~~java
byte[] base64 = "TWFu".getBytes(StandardCharsets.US_ASCII);
try (InputStream in = Base64.getDecoder().wrap(
        new ByteArrayInputStream(base64))) {
    byte[] raw = in.readAllBytes();
    System.out.println(new String(raw, StandardCharsets.US_ASCII));
}
~~~

Stdout là `Man`. Đoạn này dùng `readAllBytes` từ JDK9+, chỉ hợp lý cho dữ liệu nhỏ và có giới hạn. Khi xử lý file lớn, hãy copy từ decoder stream theo buffer vào target.

### 2.3. Bảng phân biệt API

| Mục tiêu | Nguồn | Wrapper/API | Cách sử dụng | Kết quả |
|---|---|---|---|---|
| Encode theo stream | Raw bytes | `Encoder.wrap(OutputStream)` | `write(raw)` | Base64 bytes tới output đích |
| Decode theo stream | Base64 ASCII bytes | `Decoder.wrap(InputStream)` | `read(decoded)` | Raw bytes từ wrapper |
| Encode dữ liệu nhỏ | `byte[]` | `encodeToString(bytes)` | Trả một chuỗi | Base64 String |
| Decode dữ liệu nhỏ | `String` | `decode(text)` | Trả một mảng | Raw byte[] |

Không có method `Base64.Encoder.wrap(InputStream)` hay `Base64.Decoder.wrap(OutputStream)` trong `java.util.Base64`. Và từ “Stream” ở đây có nghĩa `java.io.InputStream/OutputStream`, **khác** `java.util.stream.Stream<T>`.

## 3. Ba họ Base64 theo protocol

Java cung cấp Basic, URL-safe và MIME. Encoder và decoder phải phù hợp định dạng dữ liệu thực tế, không nên chọn tùy ý.

| Biến thể | Encoder | Decoder | Đặc trưng |
|---|---|---|---|
| Basic | `getEncoder()` | `getDecoder()` | Bảng `A–Z a–z 0–9 + /`, không tự xuống dòng |
| URL/filename-safe | `getUrlEncoder()` | `getUrlDecoder()` | Thay `+`/`/` thành `-`/`_`, không tự xuống dòng |
| MIME | `getMimeEncoder()` | `getMimeDecoder()` | Chia tối đa 76 ký tự/dòng với CRLF; decoder dung thứ ký tự ngoài bảng |

### 3.1. Basic

~~~java
Base64.Encoder encoder = Base64.getEncoder();
Base64.Decoder decoder = Base64.getDecoder();
~~~

Basic encoder không thêm linebreak. **Basic decoder từ chối ký tự ngoài bảng**, bao gồm dấu xuống dòng MIME. Nó là lựa chọn hợp lý cho một protocol yêu cầu Base64 liên tục trên một dòng, nhưng không phù hợp khi input đã được MIME line-wrap.

### 3.2. URL-safe và no padding

~~~java
Base64.Encoder encoder =
        Base64.getUrlEncoder().withoutPadding();
Base64.Decoder decoder = Base64.getUrlDecoder();
~~~

Ví dụ bytes `0xFB 0xFF` được URL-safe encode thành `-_8` nếu bỏ padding; Basic tương ứng là `+/8=`. `withoutPadding()` chỉ bỏ `=` cuối khi cần; không làm thay đổi bảng chữ cái. Java decoder chấp nhận một số final group không padding hợp lệ, nhưng **hợp đồng protocol bên nhận** có thể yêu cầu padding hoặc cấm padding. Cần thống nhất điều đó, đặc biệt trong token/URL.

### 3.3. MIME và line breaks

~~~java
Base64.Encoder encoder = Base64.getMimeEncoder();
Base64.Decoder decoder = Base64.getMimeDecoder();
~~~

MIME encoder mặc định ngắt dòng sau nhiều nhất 76 ký tự, dùng `\r\n` giữa các dòng, không tự thêm linebreak ở cuối. MIME decoder **bỏ qua line separators và những ký tự khác ngoài bảng Base64**, nên có thể nhận dữ liệu mà Basic decoder từ chối.

**Hệ quả an toàn:** nếu giao thức yêu cầu strict Base64, đừng dùng MIME decoder chỉ để tránh báo lỗi input. Khả năng bỏ qua ký tự không hợp lệ có thể che dữ liệu đã bị sửa hoặc không đáp ứng định dạng. Dùng MIME khi **đúng** format nguồn là MIME.

## 4. Encoder phải được đóng để finalize dữ liệu

Base64 encode cần xử lý nhóm cuối 1 hoặc 2 byte khi không chia hết cho 3. Nếu chỉ ghi rồi bỏ wrapper mà không close, nhóm chưa đầy có thể nằm trong trạng thái nội bộ và chưa được xuất đầy đủ.

~~~java
ByteArrayOutputStream output = new ByteArrayOutputStream();
try (OutputStream b64 = Base64.getEncoder().wrap(output)) {
    b64.write('M');
}
String encoded = output.toString(StandardCharsets.US_ASCII);
// "TQ=="
~~~

**`close()` của encoder wrapper** flush phần còn dư/padding và **đóng cả underlying OutputStream**. Oracle khuyến nghị đóng wrapper kịp thời sau khi sử dụng.

### 4.1. flush không đồng nghĩa hoàn tất

`flush()` đẩy dữ liệu output đang có xuống bên dưới theo hợp đồng stream, nhưng không hứa báo “đã kết thúc dữ liệu Base64” để encoder xuất padding cho nhóm cuối. Vì vậy, **không dùng `flush()` thay `close()`** sau khi kết thúc một thông điệp Base64.

### 4.2. Một wrapper cho toàn bộ thông điệp

Sai:

~~~java
for (byte[] chunk : chunks) {
    try (OutputStream b64 = Base64.getEncoder().wrap(target)) {
        b64.write(chunk);
    }
}
~~~

Đây là **mảnh phản ví dụ** với `chunks`/`target` do ứng dụng định nghĩa. Mỗi chunk lại được finalize/pad như một thông điệp riêng; hơn nữa lần close đầu có thể đóng target. Ghép nhiều đoạn có padding giữa chừng không giống encode cả file như một chuỗi duy nhất.

Đúng:

~~~java
try (OutputStream b64 = Base64.getEncoder().wrap(target)) {
    for (byte[] chunk : chunks) {
        b64.write(chunk);
    }
}
~~~

Chỉ tạo wrapper một lần, ghi từng chunk rồi close **sau chunk cuối**. Encoder tự quản lý nhóm dư giữa các lần `write`. Với file, có thể dùng `InputStream.transferTo(b64)` thay vòng lặp thủ công.

### 4.3. Nhóm cuối và padding

| Số byte raw | Ví dụ | Basic Base64 |
|---|---|---|
| 0 | Rỗng | Rỗng |
| 1 | `M` | `TQ==` |
| 2 | `Ma` | `TWE=` |
| 3 | `Man` | `TWFu` |
| 4 | `Many` | `TWFueQ==` |

Nếu dùng `withoutPadding`, các ký tự `=` cuối được bỏ theo đúng quy ước, không đổi chuỗi mã hóa của những nhóm đầy đủ.

## 5. Stream ownership: close wrapper đóng cả stream gốc

Đây là rủi ro vận hành rất quan trọng.

- `Encoder.wrap(OutputStream)` trả stream có `close()` **đóng underlying output**.
- `Decoder.wrap(InputStream)` trả stream có `close()` **đóng underlying input**.
- Decoder là một InputStream thực, nên có thể trả `IOException` khi `read` thất bại và phải được đóng để giải phóng nguồn.

~~~text
encoded.close()
  -> xuất byte/padding cuối
  -> đóng raw output được bọc

decoded.close()
  -> đóng raw input được bọc
~~~

Nếu chính bạn tạo file input/output cho một thao tác, việc wrapper đóng chúng khi xong là hợp lý. Nếu framework hoặc caller vẫn cần socket/HTTP response stream sau thao tác, **không được mặc định đóng**. Phải quy định ai sở hữu stream, điểm hoàn tất thông điệp và giao thức bảo toàn lifecycle; không dùng adapter “non-closing” tùy tiện rồi quên finalize encoder.

### 5.1. Với file output do method tạo

~~~java
try (InputStream raw = Files.newInputStream(sourcePath);
     OutputStream encoded = Base64.getEncoder().wrap(
             Files.newOutputStream(destPath))) {
    raw.transferTo(encoded);
}
~~~

Mảnh Java17+ ở trong một method có `throws IOException`, cần `Path` và `Files`. Encoded wrapper sở hữu file output; đóng sau khi transferTo hoàn tất sẽ finalize rồi đóng file. Input raw đóng riêng.

### 5.2. Với file input do method tạo

~~~java
try (InputStream decoded = Base64.getDecoder().wrap(
             Files.newInputStream(encodedPath));
     OutputStream target = Files.newOutputStream(decodedPath)) {
    decoded.transferTo(target);
}
~~~

Mảnh Java17+ này đóng target và decoded wrapper khi kết thúc. Decoder.close sẽ đóng file input bên dưới. Nội dung ghi ra target là **byte nhị phân gốc**, không phải ký tự Base64.

### 5.3. Không nên quản lý raw và wrapper như hai tài nguyên độc lập không cần thiết

~~~java
try (OutputStream raw = Files.newOutputStream(path);
     OutputStream encoded = Base64.getEncoder().wrap(raw)) {
    encoded.write(data);
}
~~~

Với các file streams chuẩn, close nhiều lần thường không gây vấn đề, nhưng code đã để wrapper đóng raw rồi try-with-resources đóng raw **thêm lần nữa**. Với custom stream, double close có thể có side effect khác. Mẫu tạo raw trực tiếp bên trong `wrap` khiến ownership rõ và giảm rủi ro.

## 6. Encode và decode một file lớn

Có `Path inputFile` (file nhị phân), `Path encodedFile` (Base64 ASCII) và `Path decodedFile` (file phục hồi).

### 6.1. Encode theo luồng

~~~java
void encodeFile(Path inputFile, Path encodedFile)
        throws IOException {
    try (InputStream raw = Files.newInputStream(inputFile);
         OutputStream encoded = Base64.getEncoder().wrap(
                 Files.newOutputStream(encodedFile))) {
        raw.transferTo(encoded);
    }
}
~~~

Đây là một method Java17+; cần imports `java.io.*`, `java.nio.file.*`, `java.util.Base64`. `transferTo` có từ Java9, copy từ raw đến EOF và trả số byte raw đã copy. Khi scope kết thúc, encoder.close finalize các byte cuối/padding.

### 6.2. Decode theo luồng

~~~java
void decodeFile(Path encodedFile, Path decodedFile)
        throws IOException {
    try (InputStream decoded = Base64.getDecoder().wrap(
                 Files.newInputStream(encodedFile));
         OutputStream raw = Files.newOutputStream(decodedFile)) {
        decoded.transferTo(raw);
    }
}
~~~

Output chứa các byte gốc — có thể là PDF, ZIP, image, file data, không phải một Java String. Đừng chuyển dữ liệu nhị phân sang text bằng `new String(...)` ở giữa pipeline; thao tác charset có thể làm hỏng bytes.

### 6.3. Nếu vẫn chạy Java 8

`Base64.Encoder.wrap` và `Base64.Decoder.wrap` có từ Java8, nhưng `InputStream.transferTo` bắt đầu ở Java9. Với Java8, thay `transferTo` bằng:

~~~java
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    output.write(buffer, 0, count);
}
~~~

Đây là **mảnh code** với `InputStream input` và `OutputStream output` đã khởi tạo. Copy qua một byte buffer không cần tự chia theo nhóm 3: Base64 wrapper giữ state giữa những lần write/read. Các input streams phổ biến như file streams tuân theo contract đọc block; với custom stream có trường hợp trả 0, cần xử lý theo hợp đồng riêng để tránh vòng lặp nóng.

### 6.4. Không ghi đè file đang được đọc

Nếu mở `decodedFile` cùng path `encodedFile`, output có thể bị truncate trước khi input đọc hết. Hãy kiểm đường dẫn, chính sách overwrite, quyền file và khả năng đổi tên; dùng một file tạm cho output nhạy cảm.

## 7. Decode errors: các loại ngoại lệ và partial output

Các decoder có thể báo lỗi khác nhau tùy cách gọi:

| API decode | Đầu vào | Lỗi Base64 không hợp lệ |
|---|---|---|
| `decode(String)` | Toàn chuỗi | `IllegalArgumentException` |
| `decode(byte[])` | Toàn mảng | `IllegalArgumentException` |
| `decode(ByteBuffer)` | Buffer | `IllegalArgumentException` |
| `Decoder.wrap(InputStream)` | Stream, lỗi khi đọc | `IOException` |

Ví dụ:

~~~java
try (InputStream decoded =
        Base64.getDecoder().wrap(encodedInput)) {
    decoded.transferTo(rawOutput);
} catch (IOException ex) {
    // Lỗi đọc/giải mã/ghi: không công bố output dở dang.
    reportError(ex);
}
~~~

Đây là **mảnh minh họa** với `encodedInput`, `rawOutput` và `reportError` của ứng dụng. Lỗi có thể đến từ base64 syntax, input network/file hoặc output sink. Đừng chỉ bắt `IllegalArgumentException` khi đang đọc qua decoder wrapper.

### 7.1. Phần output có thể đã được ghi trước lỗi

Nếu decoder đã xuất 10 MB rồi gặp ký tự sai, file output đang mở có thể tồn tại với 10 MB không hoàn chỉnh. Tốt nhất với dữ liệu nghiệp vụ:

1. Decode vào **file tạm**, có giới hạn kích thước.
2. Chỉ đổi tên/commit file sau khi decode đến cuối theo protocol và thành công.
3. Kiểm checksum/chữ ký nếu cần bảo đảm integrity/authenticity.
4. Xóa temp file khi lỗi; không để file partial bị coi là dữ liệu hợp lệ.
5. Nếu muốn `ATOMIC_MOVE`, kiểm hệ thống file hỗ trợ; không mặc định nó luôn thành công.

### 7.2. Padding và input xấu

Java decoder chấp nhận những nhóm Base64 cuối có 2/3 ký tự hợp lệ thiếu padding trong một số trường hợp. Nhưng khi có dấu `=` thì padding cần đúng số lượng. `getDecoder()` Basic từ chối ký tự ngoài alphabet. `getMimeDecoder()` dung thứ ký tự ngoài alphabet theo MIME, vì vậy chọn nó chỉ khi protocol thật sự cho phép.

### 7.3. Decoder stream có thể dừng sau padding

**Một chi tiết đáng chú ý đã kiểm thử:** với bytes `TQ==TRAIL`, stream `Base64.getDecoder().wrap(...)` trên JDK thử nghiệm có thể đọc ra `M` rồi kết thúc tại padding, trong khi `Base64.getDecoder().decode(byte[])` từ chối hậu tố thừa.

Không nên suy diễn từ một implementation rằng wrapper stream **luôn xác thực toàn bộ bytes sau padding**. Nếu cần kiểm nghiêm ngặt toàn bộ input, phải thiết kế **framing** và quy tắc tiêu thụ/validate phần còn lại, hoặc với payload nhỏ có giới hạn thì decode toàn mảng/chuỗi theo API strict tương ứng.

## 8. Charset: Base64 xử lý byte, Java String xử lý ký tự

Một `String` có dấu tiếng Việt cần được đổi sang bytes bằng charset rõ ràng:

~~~java
String message = "Xin chào";
byte[] plain = message.getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(plain);

byte[] restored = Base64.getDecoder().decode(encoded);
String same = new String(restored, StandardCharsets.UTF_8);
~~~

Chuỗi text đi theo pipeline:

~~~text
Java String (Unicode)
  -> UTF-8 encode -> raw bytes
    -> Base64 encode -> ASCII Base64
      -> Base64 decode -> raw bytes
        -> UTF-8 decode -> Java String ban đầu
~~~

`US_ASCII` là lựa chọn rõ nghĩa để hiển thị bytes Base64 Basic/URL/MIME thành `String`. Nhưng khi decoded bytes là một file nhị phân, **không** dùng String/UTF-8 để lưu rồi chuyển lại. Làm việc trực tiếp với `InputStream`/`OutputStream` và so sánh bytes khi kiểm roundtrip.

Dùng `getBytes()` hoặc `new String(byte[])` không khai báo charset có thể phụ thuộc môi trường. JDK17 chạy ổn trong chương trình minh họa vì charset đã được chỉ định.

## 9. Bài toán dữ liệu lớn và quota an toàn

Wrapper giảm nhu cầu giữ cả dữ liệu trong RAM, nhưng **không tự hạn chế kích thước**. Nếu gọi `decoded.readAllBytes()` trên input nhiều GB hoặc copy đến `ByteArrayOutputStream` không giới hạn, chương trình vẫn có thể tốn RAM.

Với dữ liệu từ nguồn không tin cậy:

- Giới hạn **encoded bytes** nhận và **decoded bytes** ghi.
- Chọn đúng Basic/URL/MIME theo spec.
- Kiểm path traversal, quyền ghi, file overwrite.
- Không công bố output partial nếu decode lỗi.
- Không log toàn bộ Base64 payload vì có thể phục hồi nội dung bí mật.
- Không coi Base64 là chữ ký hoặc xác thực.
- Nếu phía sau có giải nén, kiểm cả giới hạn dung lượng **sau giải nén**.
- Khi truyền qua mạng, dùng TLS và policy timeout/backpressure của transport.

### 9.1. Base64 làm tăng payload

Basic/Base64URL thường tăng dữ liệu xấp xỉ 33% (chưa tính padding và HTTP framing), MIME thêm CRLF. Nếu protocol chấp nhận raw binary, truyền binary sẽ giảm overhead của bước encode/decode. Chỉ dùng Base64 khi cần phù hợp hợp đồng format.

### 9.2. Throughput cần ghi đúng đơn vị

Báo cáo gồm raw MiB/s, encoded MiB/s, CPU, allocations, memory và I/O throughput. Không so một benchmark `ByteArrayInputStream` nhanh trên RAM rồi tuyên bố file/network production sẽ đạt tốc độ tương đương. Hãy test với cùng số byte, kích thước block và loại đích thực tế.

## 10. Chương trình Java hoàn chỉnh, có expected stdout đã kiểm chứng

Lưu thành **`Base64StreamWrapDemo.java`** và dùng JDK17+. Không cần thư viện ngoài. Ví dụ thử:

- Basic encode `hello Java` và roundtrip;
- Roundtrip UTF-8 có dấu/emoji;
- URL-safe không padding với bytes `0xFB 0xFF`;
- MIME với input đủ dài để xuất CRLF;
- Basic decoder từ chối MIME newline, decoder stream ném IOException với ký tự xấu;
- Close encoder hoàn tất `TQ==` và đóng underlying output;
- Close decoder đóng underlying input;
- Nhóm cuối 1, 2 và 3 bytes;
- Nhị phân 65.537 bytes (không chia hết cho 3) giữ đúng mọi byte.

~~~java
import java.io.*;
import java.nio.charset.*;
import java.util.*;

public class Base64StreamWrapDemo {
    static byte[] encode(byte[] plain, Base64.Encoder encoder)
            throws IOException {
        ByteArrayOutputStream target = new ByteArrayOutputStream();
        try (InputStream input = new ByteArrayInputStream(plain);
             OutputStream wrapped = encoder.wrap(target)) {
            input.transferTo(wrapped);
        }
        return target.toByteArray();
    }

    static byte[] decode(byte[] encoded, Base64.Decoder decoder)
            throws IOException {
        ByteArrayOutputStream target = new ByteArrayOutputStream();
        try (InputStream wrapped = decoder.wrap(
                new ByteArrayInputStream(encoded))) {
            wrapped.transferTo(target);
        }
        return target.toByteArray();
    }

    static class TrackedOutput extends ByteArrayOutputStream {
        boolean closed;
        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static class TrackedInput extends ByteArrayInputStream {
        boolean closed;
        TrackedInput(byte[] data) {
            super(data);
        }
        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] ascii = "hello Java".getBytes(StandardCharsets.UTF_8);
        byte[] basic = encode(ascii, Base64.getEncoder());
        System.out.println("Basic ASCII: "
                + new String(basic, StandardCharsets.US_ASCII));
        System.out.println("Basic roundtrip: "
                + Arrays.equals(ascii, decode(basic, Base64.getDecoder())));

        byte[] utf8 = "Xin chào Java 🌿".getBytes(StandardCharsets.UTF_8);
        System.out.println("UTF-8 roundtrip: "
                + Arrays.equals(utf8, decode(
                        encode(utf8, Base64.getEncoder()),
                        Base64.getDecoder())));

        byte[] urlSource = {(byte) 0xFB, (byte) 0xFF};
        byte[] url = encode(urlSource, Base64.getUrlEncoder().withoutPadding());
        System.out.println("URL without padding: "
                + new String(url, StandardCharsets.US_ASCII));
        System.out.println("URL roundtrip: "
                + Arrays.equals(urlSource,
                        decode(url, Base64.getUrlDecoder())));

        byte[] multiline = "a".repeat(96).getBytes(StandardCharsets.US_ASCII);
        byte[] mime = encode(multiline, Base64.getMimeEncoder());
        String mimeText = new String(mime, StandardCharsets.US_ASCII);
        System.out.println("MIME contains CRLF: "
                + mimeText.contains("\r\n"));
        System.out.println("MIME roundtrip: "
                + Arrays.equals(multiline,
                        decode(mime, Base64.getMimeDecoder())));

        boolean basicRejectsNewline = false;
        try {
            decode(mime, Base64.getDecoder());
        } catch (IOException expected) {
            basicRejectsNewline = true;
        }
        System.out.println("Basic rejects MIME CRLF: "
                + basicRejectsNewline);

        boolean invalidReported = false;
        try {
            decode("@@@".getBytes(StandardCharsets.US_ASCII),
                    Base64.getDecoder());
        } catch (IOException expected) {
            invalidReported = true;
        }
        System.out.println("Malformed stream throws IOException: "
                + invalidReported);

        TrackedOutput target = new TrackedOutput();
        try (OutputStream wrapped = Base64.getEncoder().wrap(target)) {
            wrapped.write('M');
        }
        System.out.println("Encoder close added padding: "
                + target.toString(StandardCharsets.US_ASCII));
        System.out.println("Encoder closes source target: " + target.closed);

        TrackedInput source = new TrackedInput(basic);
        try (InputStream wrapped = Base64.getDecoder().wrap(source)) {
            wrapped.readAllBytes();
        }
        System.out.println("Decoder closes source input: " + source.closed);

        String groups = String.join(" | ",
                new String(encode(new byte[]{'M'}, Base64.getEncoder()),
                        StandardCharsets.US_ASCII),
                new String(encode(new byte[]{'M', 'a'}, Base64.getEncoder()),
                        StandardCharsets.US_ASCII),
                new String(encode(new byte[]{'M', 'a', 'n'}, Base64.getEncoder()),
                        StandardCharsets.US_ASCII));
        System.out.println("Partial groups: " + groups);

        byte[] binary = new byte[65_537];
        for (int i = 0; i < binary.length; i++) {
            binary[i] = (byte) (i * 31 + 7);
        }
        System.out.println("Binary 65537 bytes roundtrip: "
                + Arrays.equals(binary,
                        decode(encode(binary, Base64.getEncoder()),
                                Base64.getDecoder())));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 Base64StreamWrapDemo.java
java Base64StreamWrapDemo
~~~

Stdout đã chạy kiểm chứng:

~~~text
Basic ASCII: aGVsbG8gSmF2YQ==
Basic roundtrip: true
UTF-8 roundtrip: true
URL without padding: -_8
URL roundtrip: true
MIME contains CRLF: true
MIME roundtrip: true
Basic rejects MIME CRLF: true
Malformed stream throws IOException: true
Encoder close added padding: TQ==
Encoder closes source target: true
Decoder closes source input: true
Partial groups: TQ== | TWE= | TWFu
Binary 65537 bytes roundtrip: true
~~~

### 10.1. Diễn giải kết quả

`Basic ASCII: aGVsbG8gSmF2YQ==` là Base64 ASCII của `hello Java`. `URL without padding: -_8` cho thấy bảng chữ cái URL-safe. Hai cặp `roundtrip: true` đảm bảo dữ liệu phục hồi trùng bytes ban đầu, kể cả byte từ UTF-8.

`MIME contains CRLF: true` và `Basic rejects MIME CRLF: true` xác nhận khác biệt giữa format MIME và Basic strict. `Malformed stream throws IOException: true` minh họa ngoại lệ của decode qua InputStream.

Hai dòng `Encoder closes ...` và `Decoder closes ...` được đo bằng stream theo dõi close, không dựa vào suy luận. `Partial groups` cho thấy nhóm cuối/padding. Test nhị phân dài bảo vệ trước lỗi biên theo kích thước không chia hết cho ba.

## 11. Nối Base64 với những wrapper I/O khác

Có thể kết hợp với buffering và compression, miễn là **thứ tự biến đổi** rõ ràng.

### 11.1. Buffer

`BufferedInputStream`/`BufferedOutputStream` giúp giảm số lần I/O nhỏ tới underlying sink tùy loại source/sink. Nhưng không phải mọi pipeline sẽ nhanh hơn: `transferTo`, filesystem và network có thể đã có buffering. Benchmark khi cần tối ưu, đừng tạo buffer lồng nhiều lớp không rõ lý do.

### 11.2. Nén rồi Base64

Nếu protocol là `base64(gzip(raw))`, thứ tự byte là:

~~~text
Raw bytes -> GZIP compressor -> Base64 encoder -> output bytes
Encoded input -> Base64 decoder -> GZIP decompressor -> Raw bytes
~~~

Một cấu trúc encode Java17+:

~~~java
try (OutputStream base64 = Base64.getEncoder().wrap(
             Files.newOutputStream(destPath));
     GZIPOutputStream gzip = new GZIPOutputStream(base64)) {
    source.transferTo(gzip);
}
~~~

Mảnh này cần `GZIPOutputStream`, `Files` và `source` đã mở. **GZIP phải finalize trailer trước Base64 finalize padding**. Try-with-resources đóng gzip trước base64 theo thứ tự ngược khai báo. `gzip.close` cũng có thể đóng base64 nằm dưới; nếu muốn tránh double close với custom streams, quản lý vòng đời outermost wrapper thật chặt.

Không đảo thứ tự rồi mong decoder tự hiểu: compression và Base64 là hai lớp biến đổi khác nhau. Hãy giới hạn dung lượng sau giải nén khi input không tin cậy.

## 12. Ma trận kiểm thử nên có

| Test | Kỳ vọng |
|---|---|
| Input rỗng | Encode và decode được rỗng |
| 1 raw byte | Basic có hai dấu `=` |
| 2 raw bytes | Basic có một dấu `=` |
| 3 raw bytes | Không padding |
| 3n+1 hoặc 3n+2 bytes | Byte cuối được giữ nguyên |
| Ghi thành từng chunk 1/7/8192 bytes | Cùng một wrapper vẫn đúng |
| UTF-8 chứa dấu và emoji | Roundtrip byte-for-byte |
| Binary chứa 0x00 và 0xFF | Không bị diễn giải như text |
| URL-safe không padding | Decoder URL phục hồi chính xác |
| MIME nhiều dòng | Có CRLF và MIME decoder đọc được |
| Basic gặp ký tự sai | IOException từ stream read |
| Basic gặp CRLF MIME | Từ chối |
| Padding sai | Được xử lý như dữ liệu không hợp lệ |
| Trailing bytes sau padding | Không mặc định stream validate toàn bộ |
| Encoder không close | Test phát hiện thiếu finalize khi còn byte dư |
| Close wrapper | Underlying stream cũng close |
| Output I/O lỗi giữa chừng | Không công bố file partial |
| Input/output rất lớn | Không dùng readAllBytes hoặc byte-array vô hạn |
| Same input/output path | Được ngăn chặn |
| Encoded input vượt quota | Dừng, đóng tài nguyên và báo lỗi |

Tính chất quan trọng:

~~~text
decode(encode(raw)) == raw
~~~

Kiểm bằng `Arrays.equals` đối với bytes gốc/bytes phục hồi, không chỉ kiểm chuỗi hiển thị hoặc độ dài. Các phép test trong demo bao phủ nhóm đại diện; production cần test thêm fault injection ở nguồn/đích, nhiều cỡ buffer, MIME/URL và chính sách giới hạn.

## 13. Các lỗi thường gặp

**1. Nhầm chiều wrapper.** Encoder bọc OutputStream, decoder bọc InputStream.

**2. Ghi byte Base64 sẵn có vào encoder.** Vô tình encode lần hai.

**3. Quên close encoder.** Có thể mất nhóm byte cuối hoặc thiếu padding.

**4. Coi flush là finalize.** Không đúng contract close của Base64 encoder.

**5. Tạo wrapper mới cho từng chunk.** Padding giữa thông điệp và đóng target quá sớm.

**6. Không biết wrapper.close đóng stream gốc.** Dễ đóng response/socket của caller.

**7. Dùng Basic decoder cho MIME CRLF.** Basic từ chối ký tự xuống dòng.

**8. Dùng MIME decoder để né input xấu.** MIME dung thứ ký tự ngoài bảng.

**9. Dùng Basic cho URL-safe có - và _.** Chọn đúng decoder URL.

**10. Bỏ qua padding requirements của protocol.** Không phải mọi hệ thống cho phép no-padding.

**11. Bắt IllegalArgumentException thay cho IOException với Decoder.wrap.** Lỗi xảy ra lúc đọc stream.

**12. Coi decoder stream đã kiểm mọi bytes sau padding.** Có thể bỏ sót trailing data.

**13. Xử lý binary qua String/UTF-8.** Có thể làm hỏng payload nhị phân.

**14. Dùng default charset.** Unicode có thể không roundtrip nhất quán.

**15. Dùng readAllBytes với file lớn không giới hạn.** Mất lợi ích memory của streaming.

**16. Không giới hạn input/output.** Dễ gây cạn disk/RAM.

**17. Để file decode lỗi được coi như file thành công.** Phải temp/commit theo protocol.

**18. Mở output trùng source path.** Có thể truncate nguồn.

**19. Tin Base64 mã hóa bí mật.** Nó chỉ là phép biểu diễn đảo ngược được.

**20. Không test cỡ 1/2 bytes và chunk boundaries.** Dễ bỏ sót lỗi finalize.

**21. Nối GZIP và Base64 sai thứ tự.** Kết quả không decode tương thích.

**22. Không đo tài nguyên thật.** Benchmark trên RAM không phản ánh network/storage.

## 14. Bài tập thực hành

1. Encode wrapper nhận InputStream hay OutputStream?
2. Decode wrapper nhận InputStream hay OutputStream?
3. Ghi `M` vào encoder rồi close sẽ xuất chuỗi nào?
4. Nếu chỉ flush và bỏ encoder, vì sao kết quả có thể chưa hoàn chỉnh?
5. Nhiều chunk thuộc một thông điệp nên dùng mấy wrapper?
6. Close encoder wrapper có đóng underlying output không?
7. Close decoder wrapper có đóng underlying input không?
8. Basic khác URL-safe ở ký tự nào?
9. MIME decoder khác Basic trong xử lý CRLF và ký tự ngoài bảng thế nào?
10. `withoutPadding` có đổi bảng chữ cái không?
11. Dùng API nào cho file 4 GB mà không cần byte array 4 GB?
12. `InputStream.transferTo` xuất hiện từ Java mấy?
13. Dùng Java8 thay transferTo bằng cấu trúc nào?
14. Decoder.wrap đọc input không hợp lệ thường ném loại exception nào?
15. `decode(String)` không hợp lệ thường ném loại exception nào?
16. Vì sao không được chỉ dựa decoder stream để chứng minh mọi trailing bytes sau padding đều hợp lệ?
17. Đối với file ZIP, có nên convert decoded bytes qua String không?
18. Chuyển String Unicode sang bytes nên dùng charset nào?
19. Khi decode thất bại sau khi ghi vài MB, phải xử lý output thế nào?
20. Base64 có đảm bảo dữ liệu bí mật và tính toàn vẹn không?
21. Nên đặt GZIP trước hay sau Base64 khi encode?
22. Kiểm roundtrip bằng phương pháp nào đáng tin hơn so chiều dài?
23. Tại sao cần giới hạn decoded output khi nhận nội dung từ mạng?
24. Tại sao không nên tin một benchmark ByteArrayOutputStream để dự đoán file/network throughput?

**Gợi ý đáp án:** (1) OutputStream. (2) InputStream. (3) `TQ==`. (4) Có thể còn nhóm cuối/padding chờ close. (5) Một. (6) Có. (7) Có. (8) URL thay + và / bằng - và _. (9) MIME bỏ qua nhiều ký tự ngoài alphabet, Basic từ chối. (10) Không. (11) Encoder.wrap/Decoder.wrap kết hợp copy theo buffer. (12) Java9. (13) Vòng byte[8192] read/write. (14) IOException. (15) IllegalArgumentException. (16) Decoder có thể dừng sau padding, không tiêu thụ hậu tố. (17) Không. (18) UTF-8. (19) Đánh dấu lỗi/xóa temp, không công bố file partial. (20) Không. (21) GZIP rồi Base64; ngược lại khi decode. (22) `Arrays.equals(raw, restored)`. (23) Tránh DoS/cạn tài nguyên. (24) Network/disk/buffering/latency khác RAM.

## Tổng kết

`Base64.Encoder.wrap(OutputStream)` biến **byte gốc được ghi** thành Base64 tại output đích; `Base64.Decoder.wrap(InputStream)` trả **byte gốc khi đọc** từ nguồn Base64. Mỗi thông điệp nên dùng **một wrapper xuyên suốt**; encoder phải close để xuất đầy đủ nhóm cuối/padding, đồng thời cả hai wrapper đều **đóng underlying stream** khi đóng. Chọn đúng Basic/URL/MIME, chỉ rõ UTF-8 với văn bản, tránh String với binary, xử lý IOException/partial output, giới hạn tài nguyên và kiểm cả trailing bytes nếu protocol yêu cầu. Base64 không phải bảo mật. Hãy kiểm roundtrip bằng byte-for-byte equality, kể cả kích thước không chia hết cho ba.

### Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — Base64](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html)
- [Oracle Java SE 26 — Base64.Encoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Encoder.html)
- [Oracle Java SE 26 — Base64.Decoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Decoder.html)
- [Oracle Java SE 26 — InputStream và transferTo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html)
- [Oracle Java SE 26 — OutputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStream.html)
- [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [Oracle Java SE 26 — StandardCharsets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html)
