# MessageDigest: dữ liệu đầu vào và biểu diễn kết quả trong Java

## 1. Mục tiêu

`java.security.MessageDigest` thuộc Java Cryptography Architecture (JCA), cung cấp chức năng **băm mật mã (cryptographic message digest)**. Đầu vào của hàm băm là một chuỗi **byte** với độ dài bất kỳ; đầu ra là một `byte[]` có độ dài cố định theo thuật toán.

Sau bài này, bạn có thể:

- Chọn `SHA-256`, `SHA-512`, `SHA3-256` cho những tình huống băm hiện đại phù hợp.
- Biết chính xác dữ liệu nào được đưa vào `MessageDigest` khi đầu vào là chuỗi Unicode, file nhị phân, Base64 hoặc hex.
- Dùng `getInstance`, `update`, `digest` và `reset` đúng vòng đời; hash dữ liệu theo khối và đọc stream.
- Phân biệt **digest nhị phân**, **chuỗi hex** và **chuỗi Base64**, biết đổi qua lại mà không làm hỏng byte.
- Viết kiểm thử bằng test vector chuẩn và hiểu giới hạn bảo mật của một hash không có khóa.

**Phiên bản Java:** `MessageDigest` và các thuật toán SHA-2/SHA-3 tiếp tục được sử dụng trong Java hiện đại. `SHA3-256` có trong nền tảng Java từ Java 9. Chương trình mẫu dùng `HexFormat` (API được bổ sung ở Java 17) nên yêu cầu **JDK 17+**. Bài học tập trung vào API và cách dùng còn phù hợp hiện nay.

## 2. Băm mật mã là gì?

Mô hình xử lý:

```text
Thông điệp gốc
   |
   v
Chuỗi byte chính xác (byte[])
   |
   v
MessageDigest "SHA-256"
   |
   v
32 byte digest ────> 64 ký tự hex lowercase
   |
   +───────────────> 44 ký tự Base64 chuẩn (có padding)
```

Những thuộc tính cần hiểu:

- **Tính xác định:** Cùng thuật toán và cùng thứ tự byte đầu vào thì digest giống nhau, không phụ thuộc việc nạp hết một lần hay chia thành nhiều khối.
- **Một chiều:** Không có phép “giải mã” digest để lấy lại thông điệp gốc. Hash không phải là mã hóa đối xứng hay nén có thể hoàn nguyên.
- **Độ dài cố định:** `SHA-256` cho 32 byte; `SHA-512` cho 64 byte; `SHA3-256` cho 32 byte.
- **Kháng va chạm:** Thuật toán hiện đại hướng tới việc khiến tìm hai thông điệp có cùng hash rất khó. Không có bảo đảm toán học rằng hai đầu vào bất kỳ luôn có hash khác nhau.
- **Không xác thực nguồn gửi:** Nếu đối thủ có thể sửa cả dữ liệu và chuỗi hash tham chiếu, phép so sánh hash đơn thuần không phát hiện được sự giả mạo. Muốn xác thực thông điệp cần **HMAC có khóa** (`javax.crypto.Mac`), chữ ký số, hoặc nguồn cung cấp hash đã được xác thực.
- **Không dùng để lưu mật khẩu:** SHA-256 là hash nhanh. Lưu mật khẩu phải dùng password-hashing/KDF phù hợp, có salt và chi phí tính toán được quản lý (chẳng hạn Argon2id, scrypt hoặc PBKDF2 khi thích hợp).

Ví dụ sử dụng đúng: tạo SHA-256 checksum cho file phát hành, xác nhận file tải về khớp checksum đáng tin; tạo khóa định danh nội dung byte trong kho lưu trữ; kiểm tra tính nhất quán của một pipeline truyền dữ liệu mà hash tham chiếu được bảo vệ.

## 3. Thuật toán và vòng đời MessageDigest

### Thuật toán thường dùng

| Tên truyền cho `getInstance` | Độ dài kết quả | Độ dài hex không có delimiter | Đặc điểm |
| --- | --- | --- | --- |
| `"SHA-256"` | 32 byte = 256 bit | 64 ký tự | Họ SHA-2, phổ biến cho fingerprint/checksum bảo mật hiện đại |
| `"SHA-512"` | 64 byte = 512 bit | 128 ký tự | Họ SHA-2, độ dài lớn hơn |
| `"SHA3-256"` | 32 byte = 256 bit | 64 ký tự | Họ SHA-3, khác SHA-256 dù cùng chiều dài |

Không suy ra thuật toán từ số ký tự hex: `SHA-256` và `SHA3-256` đều có 64 ký tự hex nhưng digest không tương thích. Hãy lưu **tên thuật toán** cùng digest trong metadata hoặc hợp đồng giao tiếp.

### API và trạng thái

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update(part1);
digest.update(part2);
byte[] hash = digest.digest();
```

Đây là **đoạn minh họa**, giả sử `part1` và `part2` đã là `byte[]` và phương thức chứa mã xử lý `NoSuchAlgorithmException`.

| API | Công dụng | Cạm bẫy |
| --- | --- | --- |
| `getInstance(String algorithm)` | Tạo đối tượng digest từ JCA provider hỗ trợ thuật toán | Có thể ném `NoSuchAlgorithmException` khi không hỗ trợ hoặc bị cấu hình hạn chế |
| `update(byte[])` | Nạp thêm toàn bộ mảng byte | Thứ tự các lần gọi quyết định thông điệp được băm |
| `update(byte[], offset, length)` | Nạp đúng một phần mảng | Quan trọng cho buffer đọc từ file/stream |
| `update(ByteBuffer)` | Nạp các byte còn lại từ `position` đến `limit` | Sau gọi, `position` tiến đến `limit`; đừng hash nhầm cùng vùng buffer lần nữa |
| `digest()` | Kết thúc hash các phần đã nạp, trả `byte[]` | **Tự reset** trạng thái để có thể băm thông điệp mới |
| `digest(byte[] input)` | Nạp `input` rồi kết thúc | Tương đương `update(input)` + `digest()` khi đối tượng đang ở trạng thái ban đầu |
| `reset()` | Hủy trạng thái đang nạp | Không cần gọi thêm ngay sau `digest()` |
| `MessageDigest.isEqual(a,b)` | So sánh hai digest ở dạng byte | Nên decode hex/Base64 về byte trước khi so |

Quy trình một thông điệp là **tạo → nạp dữ liệu (0 hoặc nhiều lần) → digest → tự reset**. Nếu gọi `digest()` rồi gọi `digest()` tiếp mà không `update`, lần thứ hai là hash của **thông điệp rỗng**, không phải kết quả cũ. Nếu muốn dùng lại kết quả, hãy lưu `byte[]` trả về.

Đối tượng `MessageDigest` **có trạng thái thay đổi được**; không chia sẻ một instance cho các tác vụ đồng thời. Dùng instance riêng theo request/luồng. `getDigestLength()` có thể trả 0 nếu provider không hỗ trợ xác định độ dài; muốn biết kích thước kết quả thực tế, dùng `hash.length`.

Không tự động đổi sang thuật toán bảo mật yếu khi `getInstance` lỗi. Với runtime/provider bị giới hạn, xác nhận thuật toán hợp lệ khi khởi động và báo lỗi cấu hình rõ ràng.

## 4. Dữ liệu đầu vào: điều gì thực sự được băm?

`MessageDigest` chỉ nhận byte. Phần quan trọng nhất trong một hệ thống đa ngôn ngữ hoặc nhiều dịch vụ là **quy tắc biến đổi dữ liệu nguồn thành đúng cùng một dãy byte**.

### 4.1. Từ String sang byte: cố định UTF-8

```java
byte[] data = "Xin chào".getBytes(StandardCharsets.UTF_8);
byte[] hash = MessageDigest.getInstance("SHA-256").digest(data);
```

Đoạn code minh họa sử dụng `java.nio.charset.StandardCharsets` và `java.security.MessageDigest`, cần được đặt trong phương thức xử lý checked exception. Khi cùng dữ liệu được hash ở nhiều máy, luôn chỉ rõ charset; tránh `getBytes()` không tham số nếu hợp đồng yêu cầu UTF-8.

Ví dụ `"abc"` trong UTF-8 gồm ba byte `61 62 63`. Nhưng `String.length()` trong Java đếm đơn vị UTF-16, không phải byte. Một ký tự tiếng Việt hoặc emoji có thể chiếm nhiều byte UTF-8. **Digest phụ thuộc vào số byte và giá trị từng byte, không phụ thuộc vẻ ngoài của chuỗi.**

### 4.2. Khác byte là khác đầu vào

Các ví dụ rất dễ gây lệch checksum:

- `"abc"` và `"abc\n"` (thêm một ký tự xuống dòng).
- LF (`\n`) và CRLF (`\r\n`); cùng văn bản nhưng các byte xuống dòng khác.
- Chữ `é` dưới dạng code point `U+00E9` và dạng `e` + dấu kết hợp `U+0301`; hiển thị có thể giống, byte khác.
- UTF-8 và UTF-16LE; UTF-8 có hoặc không có byte-order mark (BOM).
- Hai JSON biểu diễn cùng đối tượng nhưng thứ tự trường, khoảng trắng hoặc cách escape khác nhau.
- Text chứa dấu cách ở cuối dòng hoặc newline ở cuối file.

Nếu giao thức cần coi những biến thể Unicode là tương đương, hãy **định nghĩa canonicalization** (ví dụ chuẩn hóa NFC bằng `java.text.Normalizer`) trước khi mã hóa byte; áp dụng giống nhau ở cả hai phía. Đừng tự động normalize file nhị phân hoặc dữ liệu đã được ký, vì như vậy làm thay đổi thông điệp đang bảo vệ.

### 4.3. File nhị phân, Base64 và hex

- **File:** Băm byte thực được đọc qua `InputStream` hoặc `Files.newInputStream`. Cùng một hình ảnh nhưng file PNG khác JPEG, hoặc chỉ khác metadata file, thì checksum file thường khác.
- **Base64:** Nếu chuỗi `"SGVsbG8="` chứa dữ liệu nhị phân muốn kiểm tra, hãy gọi `Base64.getDecoder().decode(...)` rồi hash các byte kết quả (tương ứng `Hello`). Hash trực tiếp ký tự Base64 là **một thông điệp khác**.
- **Hex:** `HexFormat.of().parseHex(hexText)` lấy lại byte mà chuỗi hex đại diện; `hexText.getBytes(UTF_8)` lại tạo byte của các ký tự `0-9a-f`.
- **JSON/đối tượng:** Nếu muốn hash một đối tượng logic ổn định giữa các hệ thống, trước hết phải chốt serialization/canonicalization. `MessageDigest` không tự chuẩn hóa JSON.

Nguyên tắc khi debug: **in/kiểm tra byte đầu vào theo hex trong môi trường test**; đừng chỉ so sánh hai chuỗi mà mắt thường thấy “giống nhau”.

## 5. Dạng kết quả: nhị phân, hex, Base64

`digest()` trả `byte[]`. Biến nó thành văn bản chỉ khi cần lưu hoặc trao đổi trong trường text.

| Biểu diễn | API Java | Với SHA-256 | Lưu ý |
| --- | --- | --- | --- |
| Raw byte | `digest.digest(input)` | 32 byte | Tốt nhất để so sánh nội bộ hoặc lưu binary |
| Hex lowercase | `HexFormat.of().formatHex(hash)` | 64 ký tự | Mỗi byte đúng 2 ký tự; kể cả byte `00` |
| Base64 chuẩn | `Base64.getEncoder().encodeToString(hash)` | 44 ký tự gồm padding `=` | Bảng ký tự chuẩn, thuận tiện cho text |
| Base64 URL-safe, bỏ padding | `Base64.getUrlEncoder().withoutPadding().encodeToString(hash)` | 43 ký tự | Dành cho giao thức cần dạng phù hợp URL |

`HexFormat` có từ Java 17, bất biến và an toàn để tái sử dụng. `HexFormat.of()` sinh hex chữ thường, không delimiter. `HexFormat.of().parseHex(text)` chuyển hex hợp lệ về byte và báo lỗi với chuỗi sai định dạng. `HexFormat.of().withUpperCase()` hoặc `HexFormat.ofDelimiter(":")` tạo kiểu hiển thị khác, nhưng nội dung byte không đổi.

**Hex/Base64 không phải thuật toán hash.** Chuyển 32 byte SHA-256 thành 64 ký tự hex không biến nó thành 64 byte digest. Nếu phía nhận yêu cầu Base64 URL-safe, hãy dùng đúng encoder tương ứng; không tự ý thay alphabet/padding bằng string replacement.

**Không** dùng `new String(hashBytes, StandardCharsets.UTF_8)` để hiển thị digest: 32 byte hash không đảm bảo là chuỗi UTF-8 hợp lệ. `Arrays.toString(hash)` chỉ là biểu diễn debug các số byte có dấu, không phải hex. Khi so sánh, decode các dạng biểu diễn về `byte[]` trước.

## 6. Chương trình Java 17+ chạy độc lập

Ví dụ sau kiểm tra một thông điệp từ đầu đến cuối: băm một lần, băm theo nhiều phần, băm qua stream, encode/decode hex, đối chiếu SHA-256 và SHA3-256. Đầu vào `"abc"` được dùng vì có **test vector chuẩn, bất biến**.

Lưu trọn mã thành tệp `DigestDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;

public class DigestDemo {
    public static void main(String[] args) throws Exception {
        byte[] input = "abc".getBytes(StandardCharsets.UTF_8);
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        byte[] result = sha256.digest(input);

        HexFormat hex = HexFormat.of();
        String digestHex = hex.formatHex(result);
        String digestBase64 = Base64.getEncoder().encodeToString(result);
        System.out.println("SHA-256 (hex): " + digestHex);
        System.out.println("SHA-256 (Base64): " + digestBase64);
        System.out.println("Bytes in digest: " + result.length);

        MessageDigest piecewise = MessageDigest.getInstance("SHA-256");
        piecewise.update("a".getBytes(StandardCharsets.UTF_8));
        piecewise.update("bc".getBytes(StandardCharsets.UTF_8));
        byte[] byPieces = piecewise.digest();

        byte[] byStream;
        try (InputStream in = new ByteArrayInputStream(input)) {
            byStream = hashStream(in);
        }
        System.out.println("Chunks match: " + MessageDigest.isEqual(result, byPieces));
        System.out.println("Stream matches: " + MessageDigest.isEqual(result, byStream));
        System.out.println("Hex decodes: "
                + MessageDigest.isEqual(result, hex.parseHex(digestHex)));

        byte[] sha3 = MessageDigest.getInstance("SHA3-256").digest(input);
        System.out.println("SHA3-256 (hex): " + hex.formatHex(sha3));
    }

    static byte[] hashStream(InputStream in) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];
        int n;
        while ((n = in.read(buffer)) != -1) {
            if (n > 0) {
                digest.update(buffer, 0, n);
            }
        }
        return digest.digest();
    }
}
```

Chạy trong thư mục chứa file nguồn:

```bash
javac -encoding UTF-8 DigestDemo.java
java DigestDemo
```

**Stdout chính xác** trên JDK có provider cung cấp hai thuật toán này:

```text
SHA-256 (hex): ba7816bf8f01cfea414140de5dae2223b00361f20015ad
SHA-256 (Base64): ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=
Bytes in digest: 32
Chunks match: true
Stream matches: true
Hex decodes: true
SHA3-256 (hex): 3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532
```

**Ý nghĩa kết quả:**

1. `SHA-256 (hex)` là hash 32 byte của chính xác ba byte UTF-8 `61 62 63`.
2. `SHA-256 (Base64)` chỉ là cách hiển thị khác của **cùng 32 byte**; dòng `Bytes in digest: 32` xác nhận độ dài nhị phân.
3. `Chunks match: true` xác nhận `update("a") + update("bc") + digest()` tạo ra cùng hash với `digest("abc")`. Vị trí chia chunk không thuộc nội dung thông điệp.
4. `Stream matches: true` xác nhận dữ liệu được đọc qua `InputStream` có cùng byte và cùng kết quả.
5. `Hex decodes: true` xác nhận chuỗi hex không làm mất byte đầu hoặc thay đổi độ dài.
6. `SHA3-256` có output 32 byte nhưng dùng thuật toán khác, nên kết quả hex khác `SHA-256`.

`try-with-resources` đóng input stream. `hashStream` dùng đúng `n` byte thực nhận trong mỗi lần đọc; với stream chuẩn, `read` trả `-1` khi kết thúc. Mỗi lần xử lý tạo một `MessageDigest` độc lập, tránh trạng thái bị trộn giữa thông điệp.

Ví dụ để `throws Exception` trên `main` cho ngắn. Trong ứng dụng thật hãy phân biệt `NoSuchAlgorithmException` (runtime/provider) và `IOException` (I/O), không bỏ qua exception hay tạo checksum từ dữ liệu mới đọc được một phần.

## 7. Băm tệp lớn theo stream

Nếu input là tệp thực, sử dụng `Files.newInputStream` thay cho `ByteArrayInputStream`. Đoạn **minh họa chèn vào cùng lớp `DigestDemo`** dưới đây cần import `java.nio.file.Files`, `java.nio.file.Path`; tệp `release.zip` phải tồn tại:

```java
try (InputStream in = Files.newInputStream(Path.of("release.zip"))) {
    byte[] checksum = hashStream(in);
    String hexChecksum = HexFormat.of().formatHex(checksum);
    System.out.println(hexChecksum);
}
```

Không đưa `buffer.length` byte vào `update` ở mọi vòng. Nếu buffer có 8192 vị trí nhưng lần đọc cuối chỉ nhận 150 byte, phải gọi `update(buffer, 0, 150)`. Việc băm toàn bộ buffer sẽ vô tình thêm byte thừa hoặc byte cũ.

Để băm tệp lớn, **không cần** `Files.readAllBytes(path)` vì nó tải cả tệp vào RAM; cách cập nhật từng chunk hoạt động với lượng bộ nhớ cố định. Nếu file bị sửa trong khi đang đọc, hash chỉ phản ánh dãy byte thật sự được trả về từ stream; cần artifact bất biến hoặc snapshot khi quy trình phát hành đòi kết quả tái lập.

Checksum chỉ phát hiện thay đổi so với **hash tham chiếu đáng tin**. File và checksum cùng đến từ một nguồn kẻ tấn công kiểm soát thì không đảm bảo nguồn gốc/tính xác thực.

## 8. Nhận checksum từ bên ngoài và so sánh

Giả sử giao thức cung cấp SHA-256 hex cho `"abc"`. Sau khi nhận và xác minh định dạng, decode về byte:

```java
String expectedHex =
        "ba7816bf8f01cfea414140de5dae2223b00361f20015ad";
byte[] expected = HexFormat.of().parseHex(expectedHex);

byte[] actual = MessageDigest.getInstance("SHA-256")
        .digest("abc".getBytes(StandardCharsets.UTF_8));

boolean matches = MessageDigest.isEqual(expected, actual); // true
```

Đoạn trên cần import và xử lý checked exception như phần trước, không phải chương trình độc lập. `HexFormat.parseHex` ném `IllegalArgumentException` với hex không hợp lệ; hệ thống phải từ chối checksum lỗi định dạng. Nên kiểm tra cả thuật toán và số byte kỳ vọng (32 đối với SHA-256), tránh chấp nhận nhầm các loại digest khác nhau.

`MessageDigest.isEqual(byte[], byte[])` so sánh trực tiếp byte digest, có thiết kế giảm khác biệt thời gian so sánh do **nội dung**. Dù vậy, **so sánh bằng isEqual không khiến một hash không khóa trở thành bằng chứng xác thực**. Nếu đối thủ có thể sửa dữ liệu và digest, cần dùng `Mac.getInstance("HmacSHA256")` với khóa bí mật được bảo vệ hoặc chữ ký số; đó là các cơ chế xác thực khác với `MessageDigest`.

## 9. Cách kiểm thử hiệu quả

| Test case | Điều cần khẳng định |
| --- | --- |
| `SHA-256("abc")` | Hex phải đúng `ba7816bf8f01cfea414140de5dae2223b00361f20015ad` |
| `SHA3-256("abc")` | Hex phải đúng `3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532` |
| Một lần băm vs nhiều `update` | Chia cùng một chuỗi byte ở nhiều vị trí khác nhau vẫn cho digest bằng nhau |
| Byte stream vs mảng byte | Hash giống nhau khi toàn bộ byte được đọc theo thứ tự |
| Chuỗi Unicode | Charset được chỉ định; byte input và test vector được thống nhất với dịch vụ đối tác |
| `"abc"` vs `"abc\n"` | Biết rõ hai chuỗi có byte khác; nếu muốn chuẩn hóa newline phải có đặc tả |
| Hex/Base64 encode → decode | Kết quả phải giống toàn bộ `byte[]` gốc; không bị mất byte `00` |
| File rỗng, file lớn, lần đọc thiếu buffer | Hash chỉ tính byte thực nhận; không phụ thuộc kích thước buffer |
| Dùng lại instance sau `digest` | Không nối dữ liệu thông điệp trước vào thông điệp sau |
| Hex sai/thuật toán không hỗ trợ | Nhận lỗi phù hợp, không im lặng fallback |
| Input đọc bị lỗi giữa chừng | Không chấp nhận hash của dữ liệu chưa hoàn chỉnh như file đầy đủ |

Có thể thêm lớp JUnit 5 sau vào source set test của dự án đã có JUnit Jupiter. **Đây là test JUnit, không có `main`, cần chạy bằng JUnit Platform/Gradle hoặc IDE.**

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;

class DigestContractTest {
    @Test
    void sha256KnownAnswer() throws Exception {
        byte[] input = "abc".getBytes(StandardCharsets.UTF_8);
        byte[] actual = MessageDigest.getInstance("SHA-256").digest(input);

        assertEquals(
                "ba7816bf8f01cfea414140de5dae2223b00361f20015ad",
                HexFormat.of().formatHex(actual)
        );
        assertEquals(32, actual.length);
    }

    @Test
    void incrementalAndHexRoundTrip() throws Exception {
        byte[] full = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));

        MessageDigest parts = MessageDigest.getInstance("SHA-256");
        parts.update("a".getBytes(StandardCharsets.UTF_8));
        parts.update("bc".getBytes(StandardCharsets.UTF_8));
        byte[] split = parts.digest();

        assertArrayEquals(full, split);
        assertArrayEquals(
                full, HexFormat.of().parseHex(HexFormat.of().formatHex(full))
        );
    }
}
```

Hai nhóm assertion bảo vệ cả **cách lấy byte** lẫn **vòng đời update/digest**. Một test chỉ so sánh độ dài chuỗi hex 64 ký tự không bắt được việc chọn sai thuật toán hoặc hash nhầm chuỗi `"abc\n"`.

## 10. Lỗi phổ biến và cách xử lý

| Lỗi | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Hai máy có hash khác nhau cho text “giống nhau” | Charset, BOM, LF/CRLF, Unicode normalization khác | In byte đầu vào ở môi trường test; thống nhất UTF-8 và canonicalization |
| Hash của Base64 không khớp checksum file gốc | Hash text Base64 thay vì byte đã decode | Dùng `Base64.getDecoder().decode` trước khi băm binary |
| Hash file bị sai ở chunk cuối | `update(buffer)` nạp cả vùng buffer không sử dụng | `update(buffer, 0, n)` với `n` thực nhận |
| Kết quả hex mất các số 0 đầu | Chuyển byte-array qua số nguyên hoặc tự format không đủ hai ký tự/byte | `HexFormat.of().formatHex` |
| Digest thành ký tự lạ hoặc `�` | Ép `byte[]` sang UTF-8 `String` | Hex/Base64 để hiển thị; byte-array để tính toán |
| Gọi `digest` lần thứ hai trả kết quả khác | Sau `digest`, trạng thái đã reset; lần thứ hai băm thông điệp rỗng | Lưu kết quả lần đầu; nạp dữ liệu mới rõ ràng |
| Hash các request bất ổn khi chạy song song | Dùng chung một `MessageDigest` mutable | Mỗi tác vụ dùng instance riêng |
| Test có 64 ký tự hex vẫn pass dù dữ liệu sai | Chỉ kiểm độ dài thay vì expected digest | Dùng known-answer vector và input byte cố định |
| Dùng checksum để chứng minh người gửi | Hash không chứa khóa bí mật | HMAC/chữ ký hoặc kênh tham chiếu checksum tin cậy |
| Dùng raw SHA-256 để lưu mật khẩu | Hash nhanh, dễ thử nhiều password | Password KDF có salt/work factor; theo chuẩn bảo mật hiện hành |
| Bỏ qua I/O exception giữa quá trình đọc | Digest được tính trên file chưa đầy đủ | Chỉ hoàn tất/ghi nhận sau khi stream kết thúc thành công |
| Tự fallback khi provider thiếu thuật toán | Làm sai giao thức và có thể giảm mức bảo vệ | Fail rõ ràng, kiểm tra cấu hình và thuật toán hỗ trợ |

## 11. Checklist khi triển khai

- [ ] Thuật toán đã được chỉ rõ bằng tên JCA chuẩn, phù hợp mục đích và môi trường.
- [ ] Xác định chính xác byte của thông điệp; với text thì dùng charset và quy tắc chuẩn hóa đã thỏa thuận.
- [ ] Với file lớn, xử lý stream theo `n` byte thực đọc, không tải cả file vào RAM khi không cần.
- [ ] Mỗi tác vụ có một `MessageDigest` riêng; chỉ gọi `digest` sau khi nạp đủ dữ liệu.
- [ ] Kết quả nhị phân được biểu diễn nhất quán bằng hex hoặc Base64; encode/decode không làm mất byte.
- [ ] Khi so sánh, parse chuỗi và kiểm tra thuật toán/độ dài trước; so sánh byte digest.
- [ ] Chỉ tin checksum tham chiếu khi có kênh tin cậy; nếu cần xác thực dùng HMAC/chữ ký.
- [ ] Không dùng SHA-256/SHA3 đơn thuần để lưu mật khẩu.
- [ ] Có test vector chuẩn, test chunking, Unicode, file rỗng/lớn và đường lỗi I/O.

## 12. Câu hỏi ôn tập

1. Vì sao `"abc"` và `"abc\n"` có SHA-256 khác nhau?
2. Khi `update(buffer, 0, 120)` thì những byte nào được băm?
3. Sau `digest()`, nếu gọi `digest()` thêm lần nữa mà không nạp byte thì tính hash của dữ liệu nào?
4. 32 byte SHA-256 hiển thị thành mấy ký tự hex và Base64 chuẩn?
5. Khi nhận Base64 chứa bytes của ảnh, vì sao hash chuỗi Base64 không giống hash file ảnh?
6. Nếu file tải về khớp với hash do cùng một website không đáng tin cung cấp thì đã xác minh được tác giả chưa?
7. Trường hợp nào nên dùng `MessageDigest`, trường hợp nào cần `Mac` hoặc chữ ký số?

**Gợi ý trả lời:** (1) Khác byte newline; (2) đúng 120 byte từ index 0; (3) thông điệp rỗng vì `digest` reset; (4) 64 hex, 44 Base64 có padding; (5) khác chuỗi byte đầu vào; (6) chưa, cần nguồn hash đáng tin hoặc xác thực mật mã; (7) hash cho fingerprint/checksum, HMAC/chữ ký khi cần kiểm tra nguồn gốc chống giả mạo.

## Tài liệu tham khảo

- [Oracle Java SE 21: MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Oracle Java SE 21: HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html)
- [Oracle Java SE 21: Base64](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html)
- [Oracle Java SE 21: Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

Một phép kiểm tra digest đáng tin cậy bắt đầu từ **byte đầu vào được xác định rõ**; sau đó mới đến thuật toán, vòng đời cập nhật, cách biểu diễn kết quả và mô hình tin cậy của checksum tham chiếu.