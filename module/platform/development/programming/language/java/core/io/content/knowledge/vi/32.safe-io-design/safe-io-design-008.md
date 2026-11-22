# Kiểm tra tính toàn vẹn bằng hash khi bài toán yêu cầu (Java I/O)

Khi ứng dụng đọc, sao chép, tải xuống, giải nén hoặc lưu trữ tệp, câu hỏi quan trọng đôi khi không chỉ là **I/O có kết thúc không**, mà còn là: **“Những byte nhận được có đúng là những byte mình mong đợi không?”**. Nếu bài toán yêu cầu phát hiện nội dung bị thay đổi, mất byte, trộn byte hoặc sai phiên bản, ta có thể dùng **hàm băm mật mã** như SHA-256 để tính **digest** của dữ liệu và so sánh với một digest tham chiếu.

Tuy nhiên, **hash không phải lời giải cho mọi vấn đề an toàn**. Một giá trị SHA-256 chỉ giúp kiểm tra tính khớp khi có **digest tham chiếu đủ đáng tin**; nếu kẻ tấn công có thể thay cả file **lẫn hash đính kèm**, việc so sánh vẫn cho kết quả đúng với dữ liệu đã bị thay. Khi cần xác thực ai tạo dữ liệu, sử dụng HMAC/chữ ký số với quản lý khóa và xác thực nguồn thích hợp.

Bài này trình bày: chọn đúng lúc cần hash, khác biệt giữa hash/CRC/HMAC/chữ ký, cách tính SHA-256 theo luồng bằng `MessageDigest`, `DigestInputStream`, `FileChannel` và `ByteBuffer`, cách kiểm tra sau sao chép, đối phó dữ liệu thay đổi đồng thời, chi phí I/O, bảo mật và bài tập Java 17+.

## 1. Hash là gì và kiểm tra điều gì?

Hàm băm mật mã `H` nhận một chuỗi byte độ dài bất kỳ và tạo ra digest độ dài cố định:

```text
Bytes nguồn                    SHA-256                      Digest 32 byte
"abc" (ASCII)          ──────────────────────>    ba7816bf8f01cfea...
"abd" (ASCII)          ──────────────────────>    a52d159f262b2c6d...

Khi kiểm tra:
actual = SHA-256(bytes đọc thực tế)
expected = digest tham chiếu đã được xác thực/đáng tin
PASS chỉ khi actual và expected khớp nhau.
```

SHA-256 có đầu ra **256 bit = 32 byte**, thường hiển thị thành **64 ký tự hexadecimal**. Đây không phải thuật toán nén có thể đảo ngược: không thể “giải mã hash” để lấy lại file. Một thay đổi nhỏ ở đầu vào thông thường làm digest thay đổi rõ rệt.

Các thuộc tính của một hàm băm mật mã tốt gồm khả năng chống tìm preimage, second preimage và collision trong phạm vi độ an toàn phù hợp; không nên viết phần mềm dựa vào giả định **không bao giờ** có collision về mặt toán học. Với SHA-256, xác suất collision ngẫu nhiên là cực nhỏ trong các quy mô thực tế thông thường, nhưng đánh giá bảo mật còn tùy mô hình đe dọa.

Điều kiện kiểm tra đúng phải rõ:

- **Đối tượng được hash**: raw bytes file, dữ liệu sau giải nén, payload đã giải mã hay serialized representation?
- **Thời điểm**: trước sao chép, sau sao chép, sau tải xuống, trước tiêu thụ hay khi khởi động?
- **Nguồn của expected digest**: manifest đã ký, cơ sở dữ liệu tin cậy, hash độc lập qua kênh an toàn hay chỉ một file `.sha256` tải cùng chỗ không được bảo vệ?
- **Kết quả khi mismatch**: từ chối dùng file, xóa bản tạm, retry từ nguồn tin cậy, cảnh báo hay tiếp tục theo chính sách?

## 2. Khi nào thực sự cần hash?

Hash rất hữu ích khi sự **khớp byte-for-byte** có giá trị đối với quyết định nghiệp vụ:

| Tình huống | Hash giúp gì? | Cần bổ sung gì? |
| --- | --- | --- |
| Tải artifact/plugin từ nguồn phát hành | Kiểm tra file tải có đúng digest phát hành. | Digest phải qua kênh tin cậy hoặc có chữ ký số; không tin file hash tùy ý. |
| Sao chép file quan trọng | So source/copy để phát hiện sai byte hoặc thiếu byte. | Quản lý file thay đổi đồng thời, lỗi ghi, snapshot và việc sử dụng sau kiểm tra. |
| Đồng bộ, lưu trữ, backup | Phát hiện content drift, dedup theo nội dung. | Manifest, versioning, identity, recovery; hash không thay thế backup. |
| Pipeline ingest dữ liệu | Xác minh payload trước khi commit/xử lý. | Giới hạn kích thước, schema validation, auth, transaction. |
| Chuyển dữ liệu qua nhiều bước | Đối chiếu hash đầu vào và đầu ra cùng representation. | Định nghĩa rõ có bước chuyển đổi hợp lệ (nén, mã hóa, newline) hay không. |
| Xác minh cache | Đảm bảo giá trị cache tương ứng nội dung mong đợi. | Key/version, chống race và chiến lược invalidation. |

Không nên tính SHA-256 cho mọi lần đọc file nếu bài toán không cần sự đảm bảo ấy và chi phí CPU/I/O không đáng. Chẳng hạn một bản ghi log tạm không quan trọng có thể chỉ cần kiểm tra kết quả write và retry; một artifact được dùng chạy code hoặc cập nhật phần mềm cần xác thực mạnh hơn một checksum.

**Hash không thay thế** việc kiểm tra số byte thực sự đọc/ghi, `IOException`, close/flush, permission, file format, schema hay input validation. Một file bị lỗi định dạng vẫn có thể có SHA-256 khớp với hash của chính nó.

## 3. Hash, checksum, CRC, HMAC và chữ ký số khác nhau thế nào?

| Công cụ | Mục đích chính | Có chống sửa đổi có chủ đích khi đối thủ thay được dữ liệu và checksum không? |
| --- | --- | --- |
| Tổng byte/kích thước file | Phát hiện thiếu dữ liệu thô sơ. | Không. Hai file khác nhau vẫn cùng kích thước. |
| CRC-32 (`java.util.zip.CRC32`) | Phát hiện lỗi truyền/lưu trữ tình cờ với chi phí thấp. | Không. CRC không phải cryptographic MAC. |
| SHA-256/SHA-512 (`MessageDigest`) | Digest mật mã cho so khớp nội dung. | Chỉ có ý nghĩa xác thực nếu expected digest được bảo vệ đáng tin. |
| HMAC-SHA-256 (`javax.crypto.Mac`) | Xác thực toàn vẹn với **khóa bí mật chung**. | Có, với điều kiện khóa an toàn, protocol đúng và thuật toán còn phù hợp. |
| Chữ ký số (`Signature`) | Xác thực dữ liệu bằng private key, kiểm tra bằng public key được tin cậy. | Có, nếu khóa công khai/chuỗi tin cậy được xác minh đúng. |
| AEAD (ví dụ AES-GCM) | Mã hóa và kiểm tra tag xác thực kèm context dữ liệu. | Có, nếu khóa/nonce/AAD được dùng theo thiết kế đúng. |

Ví dụ **không an toàn** để chứng minh tính xác thực: tải `program.jar` cùng `program.jar.sha256` từ cùng một vị trí mà kẻ tấn công có thể sửa cả hai, sau đó nói file “đã được xác thực”. Kẻ tấn công có thể tạo digest mới cho file giả.

Ví dụ có ý nghĩa hơn: ứng dụng đã có **expected SHA-256 được phân phối qua kênh tin cậy độc lập**, hoặc manifest được ký bởi publisher với khóa công khai đã xác thực trước. Khi so sánh digest, ứng dụng phát hiện bytes nhận không khớp bản đã phát hành.

**CRC-32** phù hợp kiểm tra lỗi ngẫu nhiên của ZIP và nhiều protocol; không dùng CRC thay SHA-256/HMAC cho quyết định bảo mật.

**MD5 và SHA-1** có những vấn đề collision đã biết, không nên lựa chọn cho hệ thống mới có đối thủ chủ động. Đối với kiểm tra toàn vẹn file hiện đại, SHA-256 là mặc định thực dụng; chính sách thuật toán dài hạn có thể cần cập nhật theo yêu cầu tổ chức.

## 4. Java API cơ bản: MessageDigest và SHA-256

`java.security.MessageDigest` là API tiêu chuẩn:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update(new byte[] {0x61, 0x62, 0x63});
byte[] result = digest.digest();
String hex = HexFormat.of().formatHex(result);
```

Đây là **snippet** cần import `java.security.MessageDigest`, `java.util.HexFormat` và xử lý `NoSuchAlgorithmException`. Bytes `0x61, 0x62, 0x63` là chuỗi ASCII `abc`. Với Java 17+, `HexFormat` là tiện ích chuẩn để in/đọc hexadecimal.

Hai cách sử dụng:

- **Một lần**: `digest.digest(allBytes)`, chỉ phù hợp khi dữ liệu đã nằm sẵn trong bộ nhớ với kích thước an toàn.
- **Nhiều chunk**: gọi `digest.update(chunk...)` nhiều lần theo **đúng thứ tự byte**, sau đó gọi `digest.digest()` một lần để lấy kết quả.

Ví dụ về tính nối tiếp:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update("a".getBytes(StandardCharsets.US_ASCII));
digest.update("bc".getBytes(StandardCharsets.US_ASCII));
byte[] result = digest.digest(); // Cùng SHA-256 với bytes "abc".
```

Phần này là snippet, cần imports và handling checked exception. Không cần nối mọi chunk thành một mảng lớn: `MessageDigest` xử lý trạng thái băm tăng dần.

**Chú ý lifecycle:** `digest()` kết thúc phép tính và reset trạng thái digest theo hợp đồng API. Nếu tiếp tục gọi `update` sau khi đã `digest()` thì đang băm một thông điệp mới, không phải nối tiếp thông điệp cũ. `MessageDigest` cũng không phải một đối tượng tự động thread-safe: dùng instance riêng cho từng luồng/tác vụ trừ khi có đồng bộ hóa rõ ràng.

## 5. Hash của byte, không phải “ký tự nhìn giống nhau”

SHA-256 làm việc trên **byte sequence**. Với text, cùng một câu hiển thị có thể có bytes khác nhau do:

- Charset: UTF-8, UTF-16, legacy code page.
- Unicode normalization: NFC và NFD có thể biểu diễn ký tự có dấu khác nhau.
- Dấu xuống dòng: `\n`, `\r\n`, hoặc file có BOM.
- Khoảng trắng cuối dòng, tabs, encoding khác nhau, byte thừa/thiếu.
- JSON có thay đổi thứ tự key, spacing hoặc number serialization; XML có canonicalization riêng.

Ví dụ:

```java
byte[] a = "abc".getBytes(StandardCharsets.UTF_8);
byte[] b = "abc\n".getBytes(StandardCharsets.UTF_8);
// Hai mảng khác độ dài nên SHA-256 phải được tính độc lập.
```

Đây là snippet. Nếu yêu cầu **tính toàn vẹn file**, hash **raw bytes** như được lưu thực tế; đừng tự đọc text rồi ghi lại để chuẩn hóa mà không có yêu cầu rõ. Nếu bài toán yêu cầu tương đương **về nội dung logic**, hãy định nghĩa quy tắc canonicalization rõ ràng và áp dụng giống nhau ở bên phát hành/nhận trước khi hash.

Với định dạng nén/mã hóa, phải xác định hash là của:

1. **Bytes ZIP/đã nén** (kiểm tra chính xác archive nhận), hay
2. **Bytes entry sau giải nén** (kiểm tra chính xác nội dung gốc), hay
3. **Object đã parse/canonicalize** (kiểm tra tương đương logic).

Ba digest đó không thể thay thế nhau. Một ZIP được tạo lại với timestamp khác có thể có raw archive hash khác dù payload file giống nhau.

## 6. Hash file lớn theo luồng với DigestInputStream

Không dùng `Files.readAllBytes(file)` cho file rất lớn hoặc không tin cậy chỉ để tính SHA-256. Hãy đọc theo chunk và cập nhật digest:

```java
// Snippet: file là Path có quyền đọc và đã được kiểm soát.
MessageDigest digest = MessageDigest.getInstance("SHA-256");
try (InputStream in = new DigestInputStream(
        Files.newInputStream(file), digest)) {
    byte[] buffer = new byte[8192];
    while (in.read(buffer) != -1) {
        // DigestInputStream đã cập nhật digest theo byte thực được đọc.
    }
}
byte[] actual = digest.digest();
```

Đoạn trên cần các imports `java.io.InputStream`, `java.security.DigestInputStream`, `java.security.MessageDigest`, `java.nio.file.Files` và xử lý exceptions. `DigestInputStream` được dùng để cập nhật digest **trong lúc read**, không cần gọi `digest.update(buffer)` thêm lần nữa; gọi thêm sẽ băm bytes **hai lần** và kết quả sai.

Nếu tự dùng InputStream thuần:

```java
try (InputStream in = Files.newInputStream(file)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > 0) {
            digest.update(buffer, 0, n);
        }
    }
}
```

Đây là snippet dùng `digest` mới, chưa finalize; việc đọc phải có logic phù hợp loại stream. Cần luôn dùng **n**, không update toàn bộ mảng `buffer`: lần đọc cuối thường có ít byte hơn `buffer.length`; phần đuôi chứa byte cũ từ lần trước không thuộc dữ liệu mới.

Kích thước chunk như 8 KiB hoặc 64 KiB ảnh hưởng hiệu năng, nhưng không ảnh hưởng kết quả nếu thứ tự và tập bytes giống hệt nhau.

## 7. FileChannel và ByteBuffer: băm cùng bytes được ghi ra

Với NIO, `FileChannel.read(ByteBuffer)` cập nhật `position` theo số byte đọc thực tế; sau `flip()`, vùng `[position, limit)` là dữ liệu vừa nhận. Muốn **vừa copy vừa hash**, có thể tạo view của chunk để đọc byte cho digest mà không thay đổi `position` của buffer gốc dùng cho `FileChannel.write()`:

```java
// Snippet: in/out là FileChannel; chunk là ByteBuffer ở pha ghi.
int n = in.read(chunk);
if (n > 0) {
    chunk.flip();
    digest.update(chunk.asReadOnlyBuffer()); // View có position riêng.
    while (chunk.hasRemaining()) {
        int written = out.write(chunk);
        if (written == 0) {
            throw new IOException("Không có tiến triển khi ghi");
        }
    }
    chunk.clear();
}
```

Đây là snippet; với file blocking thông thường chính sách fail-fast khi write trả 0 giúp tránh busy loop. Không sao chép nguyên chính sách cho `SocketChannel` non-blocking: `write() == 0` có thể là trạng thái hợp lệ và cần chờ `OP_WRITE`.

Điểm cốt lõi:

- `asReadOnlyBuffer()` tạo **view dùng chung bytes nhưng position/limit độc lập** với buffer gốc; `digest.update(ByteBuffer)` tiêu thụ view từ position đến limit.
- `FileChannel.write(chunk)` vẫn thấy position gốc ở 0 và gửi **đúng các byte vừa được hash**.
- Vì `write` có thể partial, lặp `while (chunk.hasRemaining())` trước khi `clear()`.
- Nếu gặp `n == -1`, đó là EOF; stop. Nếu `n == 0` trên đường đọc file blocking mà buffer vẫn có chỗ, ứng dụng cần chính sách không tiến triển.
- Đừng hash toàn bộ buffer capacity thay cho dữ liệu thực vừa đọc.

**Giới hạn an toàn:** digest tính lúc copy xác nhận tập byte mà ứng dụng đã **định ghi**, không tự bảo đảm các bytes thực sự tồn tại ở file đích sau lỗi hệ thống hoặc bị process khác sửa. Nếu cần quyết định sử dụng file đích, phải **đọc lại file đích để hash và đối chiếu với digest tham chiếu** trước khi commit/tiêu thụ theo chính sách.

## 8. Ví dụ Java 17+ chạy độc lập: copy, đối chiếu, phát hiện thay đổi

Bài thử dùng known-answer vector `SHA-256("abc")` với giá trị hex chuẩn:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Chương trình tạo hai file tạm, ghi `abc` vào file nguồn, dùng `FileChannel` và buffer **2 byte** để buộc dữ liệu được xử lý thành nhiều lượt, tính SHA-256 khi copy. Sau đó nó kiểm tra digest nguồn và digest file đích. Cuối cùng đổi dữ liệu đích thành `abd` để chứng minh digest không còn khớp. Trong ví dụ, giá trị SHA-256 tham chiếu được **hardcode để thực hành**; trong ứng dụng thật phải lấy giá trị mong đợi từ một nguồn được xác thực.

Lưu thành **`FileHashIntegrityDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class FileHashIntegrityDemo {
    private static final String TRUSTED_SHA256 =
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossibleOnStandardJdk) {
            throw new IllegalStateException(impossibleOnStandardJdk);
        }
    }

    private static byte[] sha256(Path file) throws IOException {
        MessageDigest digest = newSha256();
        try (InputStream stream = new DigestInputStream(
                Files.newInputStream(file), digest)) {
            byte[] chunk = new byte[8192];
            while (stream.read(chunk) != -1) {
                // DigestInputStream updates the digest as bytes are read.
            }
        }
        return digest.digest();
    }

    private static byte[] copyAndHash(Path source, Path target)
            throws IOException {
        MessageDigest digest = newSha256();
        ByteBuffer chunk = ByteBuffer.allocate(2);
        try (FileChannel in = FileChannel.open(source,
                     StandardOpenOption.READ);
             FileChannel out = FileChannel.open(target,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING)) {
            while (true) {
                int n = in.read(chunk);
                if (n == -1) break;
                if (n == 0) throw new IOException("Read without progress");
                chunk.flip();

                // Read-only duplicate has independent position.
                digest.update(chunk.asReadOnlyBuffer());
                while (chunk.hasRemaining()) {
                    if (out.write(chunk) == 0) {
                        throw new IOException("Write without progress");
                    }
                }
                chunk.clear();
            }
        }
        return digest.digest();
    }

    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("hash-src-", ".txt");
        Path target = Files.createTempFile("hash-dst-", ".txt");
        try {
            Files.writeString(source, "abc", StandardCharsets.US_ASCII);
            byte[] expected = HexFormat.of().parseHex(TRUSTED_SHA256);
            byte[] copiedDigest = copyAndHash(source, target);
            System.out.println("sha256=" +
                    HexFormat.of().formatHex(copiedDigest));
            System.out.println("source-valid=" +
                    MessageDigest.isEqual(expected, sha256(source)));
            System.out.println("copied-valid=" +
                    MessageDigest.isEqual(expected, copiedDigest));
            System.out.println("destination-valid=" +
                    MessageDigest.isEqual(expected, sha256(target)));

            Files.writeString(target, "abd", StandardCharsets.US_ASCII,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            System.out.println("after-tamper-valid=" +
                    MessageDigest.isEqual(expected, sha256(target)));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FileHashIntegrityDemo.java
java FileHashIntegrityDemo
```

Stdout đã được đối chiếu bằng biên dịch và chạy trên JDK 17+:

```text
sha256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
source-valid=true
copied-valid=true
destination-valid=true
after-tamper-valid=false
```

**Giải thích:**

1. `Files.writeString(source, "abc", US_ASCII)` tạo đúng ba byte `61 62 63`. Digest chuẩn được dùng như expected từ một test vector đã biết.
2. `copyAndHash` mở hai `FileChannel` trong `try-with-resources`, đọc tối đa hai byte một lượt và cập nhật `MessageDigest` bằng read-only view.
3. `while (chunk.hasRemaining())` đảm bảo mỗi chunk được chuyển trọn sang file đích theo vị trí `ByteBuffer` trước khi đọc chunk tiếp.
4. `MessageDigest.isEqual` so sánh hai mảng digest thực. `source-valid=true` và `copied-valid=true` cho biết data nguồn và các byte đã đưa qua quy trình copy khớp expected.
5. `destination-valid=true` vì chương trình **đọc lại file đích** rồi băm độc lập; điều này bổ sung một phép kiểm soát so với chỉ tin số byte đã write.
6. Khi thay `abc` bằng `abd`, digest của file đích thay đổi; so sánh với expected cũ cho `after-tamper-valid=false`.
7. Hai file tạm được xóa ở `finally`, channel/input stream được đóng an toàn trước cleanup.

**Giới hạn demo:** chỉ một chương trình thao tác trên các file temp, không có writer ngoài đồng thời. Nó minh họa đúng kỹ thuật băm và so khớp, **không** tự đảm bảo chống TOCTOU, file đã fsync, hoặc dữ liệu không thể bị sửa sau thời điểm kiểm tra. Trong production, cần xem phần quản lý vòng đời và nguồn tin cậy bên dưới.

## 9. So sánh digest đúng cách và đọc expected hash

Một digest SHA-256 thực có **32 byte**. Với nguồn tham chiếu ở dạng hex, xác minh độ dài/encoding trước khi dùng:

```java
// Snippet: expectedHex lấy từ manifest đã xác thực.
String expectedHex = expectedHexFromTrustedManifest;
if (!expectedHex.matches("[0-9a-fA-F]{64}")) {
    throw new IOException("Expected SHA-256 không hợp lệ");
}
byte[] expected = HexFormat.of().parseHex(expectedHex);
byte[] actual = sha256(downloadedFile);
if (!MessageDigest.isEqual(expected, actual)) {
    throw new IOException("Integrity check failed");
}
```

Đây là snippet với `downloadedFile`, `expectedHexFromTrustedManifest` và `sha256(...)` đã được khai báo bên ngoài; `HexFormat` có trong Java 17. Nếu manifest chứa thuật toán `SHA-512`, độ dài digest khác; không đoán độ dài từ một chuỗi hash tùy ý.

`MessageDigest.isEqual(byte[], byte[])` là tiện ích so sánh digest thích hợp hơn việc tự ghép chuỗi và so theo code nhiều nhánh; tuyệt đối không khẳng định từ API này rằng cả quy trình đã có chống timing side-channel hoàn hảo. Nếu xác thực dùng secret và giao thức nhạy timing, tuân thủ thiết kế MAC/chữ ký đã được kiểm tra chuyên sâu.

Tính **hash bằng một `MessageDigest` mới cho mỗi đối tượng/tác vụ**; tránh dùng một instance toàn cục rồi nhiều thread `update` đồng thời. Ghi hash ra log nên kèm thuật toán, phiên bản schema, identity file/version và bối cảnh; đừng vô tình dùng digest như password hashing hoặc kho lưu token bí mật.

## 10. Hash được lưu ở đâu và độ tin cậy đến từ đâu?

Bảng quyết định:

| Expected hash lấy từ | Có thể tin để chống sửa file không? | Lý do |
| --- | --- | --- |
| SHA-256 cùng tải từ URL do attacker kiểm soát | **Không**. | Đối thủ có thể tạo đồng thời file và hash giả. |
| Hash trong DB tin cậy có phân quyền/kiểm toán | Có thể dùng, tùy mức bảo vệ DB và quy trình tạo hash. | Integrity của reference là yếu tố then chốt. |
| Hash hardcode trong bản ứng dụng được phân phối tin cậy | Có thể dùng cho artifact/version cụ thể. | Hash không tự bảo vệ binary ứng dụng khỏi bị sửa. |
| Manifest ký số có public key được ghim/xác minh tin cậy | Có thể cho xác thực publisher nếu protocol và khóa đúng. | Chữ ký bảo vệ manifest hash và metadata gắn kết. |
| HMAC của payload với secret key không lộ | Có thể cho xác thực giữa các bên biết khóa. | Không phù hợp nếu mọi bên được phát hành public đều phải kiểm chứng mà không biết secret. |

Cần gắn digest với đúng **đối tượng**. Nếu chỉ có danh sách SHA-256 mà không biết digest tương ứng với tên artifact, version, kích thước hoặc ngữ cảnh nào, người kiểm tra có thể xác nhận một file hợp lệ nhưng **sai phiên bản**. Manifest nên xác thực cả đường dẫn logic, version, thuật toán, digest và những metadata định danh quan trọng theo nhu cầu.

**Hash đơn lẻ không chứng minh người gửi là ai.** Nó chỉ là một phép tính xác định trên bytes; phần **nguồn tin cậy** đến từ protected manifest, MAC, signature, TLS/authentication và quyền truy cập được thiết kế riêng.

## 11. HMAC và chữ ký số khi cần chống giả mạo

Khi hai hệ thống giữ **khóa bí mật chung**, HMAC giúp kiểm tra dữ liệu có do bên biết khóa tạo ra và không bị đổi trên đường đi:

```java
// Snippet minh họa: secret là byte[] lấy từ kho khóa an toàn,
// không hardcode khóa trong code hoặc log.
Mac mac = Mac.getInstance("HmacSHA256");
SecretKeySpec key = new SecretKeySpec(secret, "HmacSHA256");
mac.init(key);
byte[] tag = mac.doFinal(payload);
```

Snippet cần imports `javax.crypto.Mac`, `javax.crypto.spec.SecretKeySpec` và xử lý exceptions; `payload` là bytes. Không dùng cùng một khóa bí mật cho nhiều mục đích không liên quan; định nghĩa protocol gắn cả identity/version/nonce hoặc context tùy threat model. Một HMAC hợp lệ không tự cung cấp chống replay nếu ứng dụng chấp nhận lặp lại cùng một thông điệp mà không kiểm tra sequence/expiry/idempotency.

Khi cần phát hành cho nhiều người có thể kiểm chứng mà **không** tiết lộ private key, dùng **chữ ký số**. Người phát hành ký manifest hoặc digest có cấu trúc; người nhận kiểm tra chữ ký bằng public key/chuỗi tin cậy đúng. Đừng lấy public key từ cùng nguồn không được xác thực rồi coi như đã giải quyết bài toán giả mạo.

**Đừng phát minh chữ ký bằng cách viết `SHA-256(key || message)`.** Dùng HMAC hoặc signature algorithms được định nghĩa và thư viện crypto chuẩn. Với lưu password, không dùng SHA-256 trực tiếp: password hashing cần salt và thuật toán chuyên dụng có chi phí phù hợp (ví dụ Argon2id, scrypt, PBKDF2 theo chính sách).

## 12. Hash trong quy trình tải xuống/sao chép an toàn

Một quy trình mẫu để xuất bản file đích:

```text
expected hash đã xác thực + identity/version
             |
             v
Tạo file đích TẠM trong thư mục/quyền được kiểm soát
             |
             v
Tải hoặc copy bytes theo chunk, kiểm tra n và quota
             |
             v
Đóng/flush các resource tương ứng, kiểm tra I/O error
             |
             v
Băm lại file tạm, so với expected SHA-256
             |
     +-------+--------+
     |                |
  MISMATCH           MATCH
     |                |
Xóa/quarantine    Tùy yêu cầu: force/sync và atomic publish
Không commit      file đã xác thực, quản lý quyền truy cập
                      |
                      v
                Người tiêu thụ sử dụng đúng version đó
```

Nguyên tắc:

1. Viết vào file **tạm chưa được client khác coi là bản hợp lệ**; không ghi đè trực tiếp bản sản xuất trước khi verify.
2. Dùng expected digest đáng tin; lấy qua một cơ chế riêng hoặc manifest được ký.
3. Chỉ xử lý file sau khi kiểm tra actual digest khớp; thất bại phải **fail closed** đối với dữ liệu quan trọng.
4. Chọn cơ chế publish có atomicity theo nền tảng, ví dụ `Files.move(..., ATOMIC_MOVE)` nếu provider hỗ trợ và hợp đồng replace phù hợp. Phải xử lý `AtomicMoveNotSupportedException`, lỗi permission và khả năng thay file đích khác nhau.
5. Nếu cần độ bền sau mất điện, xem xét `FileChannel.force(true)` cho file và cơ chế sync thư mục mà hệ điều hành/provider cho phép. Atomic rename không tự đồng nghĩa dữ liệu đã được fsync.
6. Không để producer khác sửa file tạm sau kiểm tra; điều phối ownership, quyền truy cập, lock/rename và thời điểm sử dụng.

**TOCTOU:** kiểm tra hash tại T1 rồi đọc lại cùng đường dẫn tại T2 **không bảo đảm** bytes vẫn như cũ nếu file bị thay thế/ghi đè giữa hai mốc. Ưu tiên lưu file verified trong vùng bất biến theo chính sách, dùng định danh version/content-addressed storage, quản lý handle và quyền ghi, xác minh gần thời điểm dùng khi cần.

## 13. Dữ liệu nguồn thay đổi trong lúc hash/copy

Bài toán khó xuất hiện khi file lớn và có writer khác đang cập nhật:

```text
T0: SHA-256 bắt đầu đọc file X
T1: Writer khác thay đổi đoạn giữa của X
T2: SHA-256 đọc phần còn lại
T3: Digest thu được từ một chuỗi byte có thể không
    tương ứng với snapshot nhất quán của file ở bất kỳ thời điểm nào.
```

Một số lưu ý quan trọng:

- Đọc file theo chunk không cung cấp **snapshot isolation**.
- Kiểm tra `Files.size()` và `Files.getLastModifiedTime()` trước/sau có thể hỗ trợ phát hiện thay đổi, nhưng không phải chứng minh an toàn: timestamps có độ phân giải, có thể bị chỉnh và file có thể đổi rồi đổi lại.
- `FileChannel.lock()` có tác dụng theo OS/file system và mức hợp tác của writer; không đảm bảo mọi chương trình đều tôn trọng.
- Nếu cần khẳng định hash của một **phiên bản bất biến**, dùng snapshot, copy-on-write, quy trình producer hoàn tất rồi rename/publish, content-addressed object hoặc giao thức đồng bộ được kiểm soát.
- File được mở bằng một handle cũng không mặc nhiên chặn mọi thay đổi của process khác tới nội dung; phải hiểu đúng locking và sharing semantics trên OS.

Ví dụ với backup: không nên dùng SHA-256 của file đang bị update liên tục rồi suy rằng bạn đã sao lưu phiên bản hợp lệ của database. Cần backup snapshot hoặc protocol riêng của database.

## 14. Chi phí hiệu năng và chiến lược tối ưu

SHA-256 được tính tuyến tính theo số byte đầu vào: **O(n)** về thời gian và có thể dùng **O(1)** bộ nhớ phụ với buffer kích thước cố định. Tuy nhiên, công cụ thực tế còn chịu overhead đọc đĩa, I/O mạng và đối chiếu file đích.

| Cách làm | Số lần đi qua dữ liệu | Điểm mạnh | Điểm yếu |
| --- | --- | --- | --- |
| Copy rồi hash file nguồn và đích | Copy + ít nhất hai lượt đọc để băm | Phát hiện sai lệch ở cả hai phía, dễ giải thích. | Tốn I/O đọc thêm. |
| Hash khi copy qua `MessageDigest.update` | Hash phần bytes đang copy | Ít lượt xử lý hơn, thuận tiện streaming. | Chưa xác minh bytes đã persist tại đích sau write. |
| Hash lại file đích sau copy | Thêm một lượt đọc file đích | Kiểm tra độc lập nội dung đã đọc lại. | Có thêm I/O; vẫn có race với writer khác. |
| Hash theo block/chunk có manifest | Mỗi block có digest riêng | Hỗ trợ resume/dedup/kiểm tra cục bộ. | Phải xác thực manifest và thứ tự/index chunk. |
| Hash toàn file trước mỗi lần dùng | Đọc hết bytes mỗi lần | Kiểm tra nội dung gần thời điểm sử dụng. | Tốn chi phí cho dữ liệu lớn, không loại trừ TOCTOU hoàn toàn. |

Không nên tối ưu bằng cách bỏ kiểm tra nếu rủi ro nghiệp vụ yêu cầu nó. Mặt khác, với cache nội bộ có semantics rõ, có thể dùng metadata/version/content ID để tránh băm lại khi đã có bằng chứng bất biến đáng tin; đo workload trước khi chọn.

Một `MessageDigest` dùng chung không có lý do phải cập nhật theo từng byte; đọc buffer đủ lớn để giảm syscall overhead. Trong Java 17, `MessageDigest.update(ByteBuffer)` hỗ trợ trực tiếp buffer heap/direct; không nhất thiết phải copy sang `byte[]`.

## 15. Những giới hạn hash không giải quyết

**Hash không kiểm chứng định dạng.** Một file có SHA-256 khớp expected vẫn có thể chứa lệnh nguy hiểm hoặc dữ liệu không tuân thủ schema. Vì vậy validate JSON/ZIP/protocol sau integrity check.

**Hash không mã hóa dữ liệu.** SHA-256 không giấu bytes, không tạo confidentiality. Nếu cần bảo mật nội dung, dùng encryption/authenticated encryption phù hợp.

**Hash không chứng minh timestamp hay filename.** Hai file khác tên nhưng cùng bytes sẽ có cùng SHA-256. Nếu identity/version/name quan trọng, bảo vệ và kiểm tra metadata đó bằng manifest được xác thực.

**Hash không đồng nghĩa durability.** Digest khớp khi đọc lại không xác nhận ổ đĩa sẽ giữ nguyên sau mất điện; `force` và storage protocol là một trách nhiệm riêng.

**Hash không chống replay.** Bên gửi có thể gửi lại bản hợp lệ cũ kèm digest hợp lệ; chống downgrade/replay cần version monotonic, expiry, nonce, signature context và quy tắc ứng dụng.

**Hash không chống đường dẫn độc hại.** Dù archive ZIP có SHA-256 khớp, việc giải nén vẫn phải bảo vệ khỏi Zip Slip, symlink, zip bomb và resource exhaustion.

**Hash không sửa lỗi tự động.** Nếu mismatch, không được “bỏ qua cảnh báo để tiếp tục”. Hệ thống cần retry/quarantine/khôi phục từ nguồn an toàn; bản hash không chứa thông tin để dựng lại dữ liệu hỏng.

## 16. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hash thay đổi dù text nhìn giống nhau | Charset, BOM, newline, Unicode normalization, whitespace khác. | Xác định hash raw bytes hay canonicalized content; thống nhất quy tắc. |
| Hash sai ở chunk cuối | Gọi `digest.update(buffer)` với cả mảng thay vì đúng `n` byte mới. | Dùng `update(buffer, 0, n)` hoặc `DigestInputStream`. |
| Hash khác khi dùng NIO | Hash cả capacity/thừa byte, hoặc buffer position đã bị `write` tiêu thụ. | `flip()` đúng; dùng duplicate/read-only view trước write. |
| Kết quả hash chỉ đúng lần đầu | Gọi `digest()` rồi tiếp tục update trên state đã reset, hoặc reuse chung giữa threads. | Instance mới cho mỗi phép hash; finalize một lần. |
| File copy bị thiếu byte | Chỉ gọi `FileChannel.write()` một lần, không xử lý partial write. | `while (buffer.hasRemaining())` trước `clear()`. |
| Không phát hiện file bị đổi | Expected digest bị thay cùng file. | Bảo vệ expected bằng chữ ký/HMAC/kênh tin cậy. |
| Reader coi SHA-256 khớp là bằng chứng người gửi | Hash không có khóa/xác thực. | HMAC hoặc chữ ký số, xác thực khóa đúng. |
| Hash file nguồn khớp nhưng đích sai | File đích bị đổi sau copy hoặc write lỗi. | Băm lại đích, giữ file tạm riêng và publish sau verify. |
| Digest khớp nhưng khi dùng nội dung khác | TOCTOU giữa hash và open/consume, đường dẫn bị thay. | Quản lý immutable artifact/handle/ownership, verify gần lúc dùng. |
| File đang ghi cho kết quả không nhất quán | Không có snapshot và writer sửa trong lúc đọc. | Dùng snapshot/producer publish protocol. |
| Dùng MD5/CRC cho xác thực tải code | Không chống giả mạo có chủ đích. | SHA-256 tham chiếu tin cậy + chữ ký/HMAC theo mô hình đe dọa. |
| Dùng SHA-256 của mật khẩu để lưu trữ | Hash quá nhanh, thiếu thiết kế chống brute-force. | Password hashing chuyên dụng với salt/cost theo policy. |
| Chuỗi hex không parse được | Dính newline, dấu cách, prefix hoặc độ dài sai. | Chuẩn hóa đầu vào theo format có kiểm soát, validate đúng 64 hex cho SHA-256. |
| Hash sau decompression khác hash file ZIP | Băm hai representation khác nhau. | Xác định lớp dữ liệu và thứ tự xử lý thống nhất. |

## 17. Kiểm thử hệ thống có hash

Một bộ kiểm thử tốt cần bao gồm:

1. **Known answer:** `SHA-256("abc")` đúng giá trị hex trong bài. Dùng fixture chuẩn, không lấy expected bằng chính hàm vừa viết rồi tự gọi đó là test độc lập.
2. **Roundtrip:** copy dữ liệu, hash source, hash target, so với expected đã xác thực. Kiểm tra size, bytes và hash.
3. **Tài liệu trống:** hash của file rỗng cũng là một digest SHA-256 hợp lệ, không phải chuỗi rỗng.
4. **File không cùng size:** ứng dụng nhận ra mismatch không chỉ qua digest mà còn lỗi I/O/size khi phù hợp.
5. **Sửa một byte:** thay một byte ở đầu, giữa và cuối; digest so expected không khớp.
6. **Sửa tên file nhưng giữ bytes:** digest raw bytes không đổi; manifest phải định nghĩa policy cho tên/đường dẫn.
7. **Chunking:** tính với buffer 1, 2, 8192 byte và direct buffer; digest phải giống nhau.
8. **Quyền truy cập và disk full:** bắt `IOException`, không publish file tạm chưa verify.
9. **Concurrent writer:** mô phỏng file bị sửa trong lúc copy để kiểm tra chính sách snapshot hoặc từ chối commit.
10. **Expected bị thay:** chứng minh hash thuần của file + hash giả **không** tạo xác thực; kiểm thử signature/HMAC path thật sự.
11. **TOCTOU:** sau verify, thay file/đường dẫn trước khi tiêu thụ; thiết kế kiểm soát việc sử dụng artifact đã kiểm tra.
12. **Giới hạn nguồn lực:** file lớn, đọc chậm, network timeout, deadline, queue backlog và quota.
13. **Replay/version:** file bản cũ vẫn có hash hợp lệ nhưng không được chấp nhận nếu policy yêu cầu bản mới hơn.

Nếu chương trình xuất ra `hash-valid=true`, cần định nghĩa rõ “valid so với expected nào và expected đến từ đâu”. Test chỉ hash cùng một input hai lần rồi so chúng với nhau **không chứng minh** integrity so với nguồn độc lập.

## 18. Bài tập thực hành

**Bài tập 1 — Hash các bytes file thay vì text.** Tạo hai file: một file chứa `"Xin chào\n"` UTF-8, file kia chứa `"Xin chào\r\n"` UTF-8. Tính SHA-256 bằng `DigestInputStream`; giải thích vì sao hash khác dù khi hiển thị có thể trông tương tự.

**Bài tập 2 — Streaming chunk sizes.** Chỉnh `ByteBuffer.allocate(2)` thành `allocate(1)`, `allocate(16)` và `allocate(8192)`. Kiểm tra digest của `abc` và việc copy file luôn giống nhau; nêu điều kiện `flip/clear/hasRemaining` bảo vệ khỏi mất/trùng byte.

**Bài tập 3 — Sửa một byte.** Trong chương trình mẫu, thử `"abc"` → `"aBc"`, `"abd"` và `"abc\n"`. So SHA-256 trước/sau. Vì sao chỉ dùng `Files.size()` sẽ bỏ qua thay đổi `abc → abd`?

**Bài tập 4 — Xác thực manifest.** Định nghĩa một manifest có `artifactId`, `version`, `length`, `algorithm`, `digest`. Nêu cách lấy manifest có chữ ký và xác minh public key đáng tin; không coi file manifest tải cùng nguồn không bảo vệ là bằng chứng.

**Bài tập 5 — Download an toàn.** Viết hàm nhận dữ liệu qua stream vào file tạm, có quota tổng 50 MiB, deadline và đếm bytes. Sau tải xuống, băm lại file tạm, so expected SHA-256 và chỉ publish bằng move có kiểm tra atomicity; khi mismatch phải xóa/quarantine.

**Bài tập 6 — Phân biệt CRC32 và SHA-256.** Tính cả hai trên cùng payload. Giải thích vì sao CRC32 phù hợp kiểm tra lỗi ZIP thông thường nhưng không làm người sửa archive có chủ đích thất bại nếu họ cũng tính lại CRC.

**Bài tập 7 — Race và immutable source.** Cho một thread/tiến trình sửa file trong lúc thread khác hash; quan sát sự khác biệt. Thiết kế producer tạo tệp tạm → flush/đóng → publish tên cố định → gửi manifest tin cậy, để consumer không hash file còn đang bị ghi.

**Bài tập 8 — HMAC.** Dùng `javax.crypto.Mac` và key lấy từ nơi quản lý key thử nghiệm để tạo HMAC-SHA-256 cho payload. Thay đổi một byte rồi kiểm tra tag không còn đúng; giải thích tại sao HMAC cần khóa bí mật còn SHA-256 thuần không.

**Bài tập 9 — Bảo vệ chống replay.** Tạo hai artifact v1/v2 đều có chữ ký/hash hợp lệ. Thiết kế policy không chấp nhận v1 sau khi đã kích hoạt v2. Vì sao digest khớp không đủ để quyết định phiên bản được phép sử dụng?

**Bài tập 10 — Hash ZIP.** Tạo hai ZIP chứa cùng file text nhưng timestamp của entry khác nhau. So SHA-256 **toàn ZIP** và SHA-256 **bytes entry giải nén**; giải thích sự khác biệt và chọn representation phù hợp yêu cầu.

### Câu hỏi tự kiểm tra

- `MessageDigest.update` nhận bytes theo luồng khác gì đọc toàn bộ file vào mảng?
- Khi read chỉ trả `n=7` vào mảng 8192 byte, phải cập nhật digest bao nhiêu byte?
- `DigestInputStream` có cần gọi `digest.update(buffer)` thêm sau mỗi lần đọc không?
- Vì sao hash file nguồn trong lúc copy không tự chứng minh file đích không bị thay?
- Nếu expected digest do attacker cung cấp cùng file, so sánh có tạo authentication không?
- Khi muốn xác nhận chính publisher đã phát hành artifact, dùng HMAC hay chữ ký số trong bối cảnh nào?
- CRC32 có chức năng gì so với SHA-256?
- Vì sao file đang được writer sửa có thể không có snapshot ổn định khi hash?
- Hash khớp có đồng nghĩa file format hợp lệ, bản không bị replay và dữ liệu đã fsync không?
- Tại sao raw ZIP bytes và bytes giải nén từ entry thường có SHA-256 khác nhau?

## 19. Tài liệu tham khảo chính thức

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): tạo SHA-256, `update`, `digest`, `isEqual`.
- [Java SE 21 — DigestInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DigestInputStream.html): băm tự động dữ liệu đọc từ stream.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): read/write, buffer position, force và lifecycle.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `remaining`, `asReadOnlyBuffer`.
- [Java SE 21 — HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): chuyển digest sang và từ chuỗi hexadecimal.
- [Java SE 21 — Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html): HMAC với khóa bí mật.
- [Java SE 21 — Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): ký và xác minh chữ ký số.
- [NIST FIPS 180-4 — Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final): đặc tả SHA-256 và họ Secure Hash Algorithm.

**Ghi nhớ:** Khi bài toán yêu cầu byte-for-byte integrity, tính SHA-256 của **đúng bytes** theo luồng và so với **digest tham chiếu đáng tin**. Hash có thể giúp phát hiện khác biệt, nhưng không tự xác thực nguồn, ngăn sửa đổi sau kiểm tra, tránh replay hoặc đảm bảo độ bền vật lý. Hãy gắn nó vào quy trình quản lý file tạm, quyền truy cập, phiên bản, chữ ký/HMAC và chính sách fail-closed phù hợp rủi ro.
