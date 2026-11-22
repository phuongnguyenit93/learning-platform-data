# Hex, Base64, mã hóa ký tự và mã hóa bảo mật là các việc khác nhau

Khi làm việc với dữ liệu trong Java 17, ta thường gặp các từ **hex**, **Base64**, **UTF-8**, **encode**, **decode**, **encrypt** và **hash**. Chúng có liên quan đến việc biến đổi dữ liệu, nhưng không cùng mục đích.

Ví dụ, một chuỗi tiếng Việt có thể được chuyển thành byte theo UTF-8; dãy byte đó có thể được biểu diễn bằng hex hoặc Base64 để lưu trong văn bản; nếu cần giữ bí mật, dữ liệu phải được mã hóa bằng thuật toán mật mã với khóa. Mỗi bước giải quyết một vấn đề riêng.

| Khái niệm | Biến đổi gì? | Mục đích chính | Có tự bảo mật dữ liệu? |
|---|---|---|---|
| **Hex (hệ 16)** | Byte thành các chữ số hex và ngược lại | Biểu diễn byte dễ đọc, debug, lưu văn bản | Không |
| **Base64** | Byte thành các ký tự thuộc bảng Base64 và ngược lại | Chuyển dữ liệu nhị phân qua kênh văn bản | Không |
| **Mã hóa ký tự (charset encoding)** | Văn bản thành byte và ngược lại | Xác định byte nào biểu diễn ký tự nào | Không |
| **Mã hóa bảo mật (encryption)** | Bản rõ thành bản mã bằng thuật toán và khóa | Bảo mật nội dung | Có, nếu dùng đúng thuật toán và quản lý khóa đúng |
| **Băm (hashing)** | Dữ liệu bất kỳ thành digest có độ dài cố định | Kiểm tra toàn vẹn, định danh, xây dựng cơ chế xác thực | Không thể giải mã ngược |

Điểm quan trọng nhất: **hex và Base64 là cách biểu diễn byte; UTF-8 là cách chuyển đổi giữa ký tự và byte; encryption là cơ chế mật mã dùng khóa**. Chúng có thể được kết hợp trong cùng một quy trình nhưng không thay thế cho nhau.

## 1. Bắt đầu từ văn bản, ký tự và byte

Máy tính lưu và truyền dữ liệu dưới dạng byte. Một `String` trong Java là văn bản; để ghi ra file, gửi qua mạng hoặc đưa vào một API xử lý byte, ứng dụng cần chuyển nó thành dãy byte bằng một **character encoding** (mã hóa ký tự).

Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class TextToBytes {
    public static void main(String[] args) {
        String text = "Xin chào Java 17";

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        System.out.println(Arrays.toString(bytes));

        String restored = new String(bytes, StandardCharsets.UTF_8);
        System.out.println(restored);
    }
}
```

Quy trình:

```text
String "Xin chào Java 17"
          |
          | UTF-8 encoding
          v
      byte[] dữ liệu
          |
          | UTF-8 decoding
          v
String "Xin chào Java 17"
```

- `getBytes(StandardCharsets.UTF_8)` chuyển chuỗi thành byte theo UTF-8.
- `new String(bytes, StandardCharsets.UTF_8)` diễn giải byte theo UTF-8 để tạo lại chuỗi.
- Nếu dùng cùng charset và byte hợp lệ, văn bản được khôi phục chính xác.

### 1.1. Ký tự không đồng nghĩa với một byte

Các ký tự khác nhau có thể cần số byte khác nhau trong UTF-8:

| Ký tự | Unicode code point | Số byte UTF-8 |
|---|---|---:|
| `A` | U+0041 | 1 |
| `é` | U+00E9 | 2 |
| `中` | U+4E2D | 3 |
| `😀` | U+1F600 | 4 |

Vì thế, không được giả định một ký tự luôn tương ứng với một byte. Chuỗi có tiếng Việt, tiếng Trung hoặc emoji có thể chiếm nhiều byte hơn số ký tự mà ta nhìn thấy.

Java `String` sử dụng biểu diễn UTF-16 ở mức code unit; điều đó không có nghĩa dữ liệu khi ghi file mặc định là UTF-16. Charset dùng để chuyển đổi chuỗi thành byte là lựa chọn riêng của ứng dụng.

### 1.2. Vì sao cần chỉ định charset rõ ràng?

Trong Java 17, lời gọi:

```java
byte[] bytes = text.getBytes();
```

sử dụng **charset mặc định của môi trường chạy**. Charset mặc định có thể khác giữa máy phát triển, máy chủ, container và hệ điều hành.

Tương tự:

```java
String text = new String(bytes);
```

cũng phụ thuộc charset mặc định. Nếu nơi ghi và nơi đọc dùng charset khác nhau, văn bản có thể bị lỗi ký tự.

Nên chỉ định rõ:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String textAgain = new String(bytes, StandardCharsets.UTF_8);
```

`StandardCharsets.UTF_8` là hằng số có sẵn trong Java, không cần tra cứu tên charset bằng chuỗi và không phát sinh checked exception.

**Lưu ý phiên bản:** từ Java 18, UTF-8 được chuẩn hóa làm charset mặc định theo JEP 400. Nhưng với dự án Java 17, không nên dựa vào thay đổi của Java 18; chỉ định UTF-8 tường minh vẫn là cách rõ ràng và ổn định.

## 2. Hex là gì?

**Hexadecimal (hex, hệ thập lục phân)** dùng 16 ký hiệu:

```text
0 1 2 3 4 5 6 7 8 9 A B C D E F
```

Một chữ số hex biểu diễn giá trị từ 0 đến 15. Một byte có 8 bit, nên biểu diễn bằng đúng **hai chữ số hex**:

| Byte (nhị phân) | Giá trị thập phân không dấu | Hex |
|---|---:|---|
| `0000 0000` | 0 | `00` |
| `0000 1010` | 10 | `0A` |
| `0111 1111` | 127 | `7F` |
| `1000 0000` | 128 | `80` |
| `1111 1111` | 255 | `FF` |

Ví dụ byte `0x4A` có giá trị 74 ở hệ thập phân. Khi viết hex, thường thêm tiền tố `0x` để người đọc biết đó là số hệ 16.

**Hex không phải mã hóa ký tự.** Chuỗi hex `41` có thể biểu diễn một byte có giá trị 65; nếu giải mã byte đó bằng ASCII hoặc UTF-8 thì nhận ký tự `A`. Nhưng nếu dữ liệu ban đầu là byte nhị phân bất kỳ, `41` chỉ là cách ghi lại byte, không tự mang ý nghĩa văn bản.

### 2.1. Chuyển byte thành hex bằng Java 17 `HexFormat`

Từ Java 17, lớp `java.util.HexFormat` cung cấp API chuẩn để chuyển đổi byte array và chuỗi hex.

```java
import java.util.HexFormat;

public class HexDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x41, 0x42, 0x43, 0x0A, (byte) 0xFF
        };

        String hex = HexFormat.of().formatHex(data);

        System.out.println(hex);
    }
}
```

Kết quả:

```text
4142430aff
```

`HexFormat.of()` mặc định dùng chữ thường và không chèn dấu phân cách. Có thể chọn chữ hoa hoặc thêm delimiter:

```java
import java.util.HexFormat;

byte[] data = {0x41, 0x42, 0x43, 0x0A};

String lower = HexFormat.of().formatHex(data);
String upper = HexFormat.of().withUpperCase().formatHex(data);
String separated = HexFormat.ofDelimiter(":").formatHex(data);

System.out.println(lower);     // 4142430a
System.out.println(upper);     // 4142430A
System.out.println(separated); // 41:42:43:0a
```

Dấu phân cách chỉ phục vụ trình bày. Nó không phải byte nằm trong dữ liệu gốc.

### 2.2. Chuyển chuỗi hex trở lại byte

Dùng `parseHex`:

```java
import java.util.HexFormat;
import java.util.Arrays;

String hex = "48656c6c6f";
byte[] bytes = HexFormat.of().parseHex(hex);

System.out.println(Arrays.toString(bytes));
System.out.println(new String(bytes, java.nio.charset.StandardCharsets.UTF_8));
```

Kết quả:

```text
[72, 101, 108, 108, 111]
Hello
```

`parseHex` biến hai ký tự hex thành một byte. Chuỗi hex cần có số chữ số chẵn; ký tự không phải hex hoặc chuỗi có cấu trúc sai sẽ gây `IllegalArgumentException`.

Có thể dùng định dạng có delimiter tương ứng khi parse:

```java
HexFormat colonHex = HexFormat.ofDelimiter(":");
byte[] bytes = colonHex.parseHex("48:65:6c:6c:6f");
```

Định dạng parse cần phù hợp với cách biểu diễn đã chọn; không nên xóa dấu phân cách tùy tiện nếu dữ liệu có quy ước riêng.

### 2.3. Vì sao byte trong Java có thể hiện số âm?

Kiểu `byte` của Java là số nguyên có dấu, phạm vi từ -128 đến 127. Nhưng một byte dữ liệu thường được diễn giải như giá trị không dấu từ 0 đến 255.

Ví dụ:

```java
byte value = (byte) 0xFF;

System.out.println(value);          // -1
System.out.println(value & 0xFF);   // 255
```

Phép `& 0xFF` giúp lấy giá trị byte theo cách nhìn không dấu. Khi dùng `HexFormat`, không cần tự xử lý từng byte như vậy; thư viện đảm nhiệm việc biểu diễn đúng hai chữ số hex.

## 3. Base64 là gì?

**Base64** chuyển dữ liệu byte thành chuỗi ký tự thuộc một bảng ký tự có thể truyền qua nhiều hệ thống văn bản. Nó thường được dùng khi cần đưa dữ liệu nhị phân vào JSON, email, cấu hình hoặc giao thức chỉ thuận tiện với text.

Bảng Base64 cơ bản gồm:

- `A-Z`: 26 ký tự.
- `a-z`: 26 ký tự.
- `0-9`: 10 ký tự.
- `+` và `/`: 2 ký tự.

Tổng cộng 64 ký tự. Dấu `=` có thể xuất hiện để **padding** ở cuối.

Base64 nhóm dữ liệu theo **3 byte đầu vào thành 4 ký tự Base64** (24 bit chia thành bốn nhóm 6 bit). Do đó kích thước chuỗi thường lớn hơn dữ liệu gốc khoảng 1/3, chưa tính padding hoặc delimiter.

### 3.1. Ví dụ bằng Java 17

Dùng `java.util.Base64`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64Demo {
    public static void main(String[] args) {
        String text = "Hello Java 17";

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(bytes);
        System.out.println(encoded);

        byte[] decoded = Base64.getDecoder().decode(encoded);
        String restored = new String(decoded, StandardCharsets.UTF_8);

        System.out.println(restored);
    }
}
```

Kết quả:

```text
SGVsbG8gSmF2YSAxNw==
Hello Java 17
```

Quy trình:

```text
String
  |
  | UTF-8
  v
byte[]
  |
  | Base64 encode
  v
String Base64
  |
  | Base64 decode
  v
byte[]
  |
  | UTF-8
  v
String ban đầu
```

Lưu ý: Base64 encode nhận **byte[]**, không nhận trực tiếp ý nghĩa ký tự. Muốn khôi phục văn bản, phải biết charset đã dùng ở bước đầu.

### 3.2. Ba biến thể encoder/decoder trong Java

`Base64` cung cấp ba cặp encoder/decoder chính:

| API | Bảng ký tự | Mục đích |
|---|---|---|
| `Base64.getEncoder()` | Basic Base64 (`+`, `/`), có padding | Dữ liệu Base64 thông thường |
| `Base64.getUrlEncoder()` | URL-safe (`-`, `_`), có padding mặc định | Dữ liệu dùng trong URL hoặc tên tệp |
| `Base64.getMimeEncoder()` | Basic Base64, có thể ngắt dòng theo MIME | Nội dung dạng MIME/email |

Ví dụ URL-safe không padding:

```java
byte[] data = {0x01, 0x02, (byte) 0xFB, (byte) 0xFF};

String basic = Base64.getEncoder().encodeToString(data);

String urlSafe = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(data);

System.out.println(basic);
System.out.println(urlSafe);
```

URL-safe thay `+` bằng `-` và `/` bằng `_`. Gọi `withoutPadding()` để bỏ ký tự `=` cuối chuỗi khi giao thức cho phép.

Không nên tự thay ký tự Base64 bằng thao tác chuỗi nếu có thể dùng đúng encoder/decoder tương ứng. Hai phía phải thống nhất cùng biến thể.

### 3.3. Base64 có phải mã hóa để giữ bí mật không?

**Không.** Base64 chỉ là phép biểu diễn có thể đảo ngược, không dùng khóa và không có tính bảo mật.

Bất kỳ ai có chuỗi Base64 đều có thể decode:

```java
String encoded = "cGFzc3dvcmQ=";

byte[] bytes = Base64.getDecoder().decode(encoded);
String text = new String(bytes, StandardCharsets.UTF_8);

System.out.println(text); // password
```

Không dùng Base64 để che mật khẩu, token, API key hoặc dữ liệu cá nhân. Nếu nội dung cần bí mật, phải dùng cơ chế mã hóa bảo mật thích hợp.

### 3.4. Base64 MIME và dữ liệu nhiều dòng

Encoder MIME có thể chèn line separator theo quy tắc MIME:

```java
Base64.Encoder mimeEncoder = Base64.getMimeEncoder();
String mimeText = mimeEncoder.encodeToString(data);
```

Basic decoder thường yêu cầu dữ liệu theo bảng Base64 cơ bản; MIME decoder có quy tắc chấp nhận ký tự không thuộc bảng Base64 để phù hợp với nội dung MIME có line break hoặc ký tự phụ trợ.

Không chọn MIME chỉ vì chuỗi dài. Hãy dùng encoder tương ứng với giao thức hoặc định dạng mà hệ thống đích yêu cầu.

## 4. Hex và Base64 khác nhau ở đâu?

Cả hai đều có thể biểu diễn cùng một dãy byte thành văn bản, nhưng cách biểu diễn khác nhau.

| Tiêu chí | Hex | Base64 |
|---|---|---|
| Đơn vị nhóm | 1 byte thành 2 chữ số | 3 byte thành 4 ký tự |
| Kích thước văn bản | Khoảng gấp 2 lần byte gốc | Khoảng 4/3 lần byte gốc |
| Ký tự | `0-9`, `a-f` (hoặc chữ hoa) | 64 ký tự, có thể có `=` padding |
| Đọc bằng mắt | Dễ đối chiếu từng byte | Gọn hơn nhưng khó đọc byte riêng |
| Thường dùng | Debug, hash, dump byte, định danh dạng hex | API text, email, payload nhị phân trong JSON |
| Bảo mật | Không | Không |

Ví dụ cùng byte `Hello` (ASCII/UTF-8):

```java
byte[] data = "Hello".getBytes(StandardCharsets.UTF_8);

String hex = HexFormat.of().formatHex(data);
String base64 = Base64.getEncoder().encodeToString(data);

System.out.println(hex);
System.out.println(base64);
```

Kết quả:

```text
48656c6c6f
SGVsbG8=
```

Hai chuỗi nhìn khác nhau nhưng khi decode đúng cách, đều khôi phục cùng byte array.

### 4.1. Chọn hex khi cần nhìn từng byte

Hex thường phù hợp với:

- Hiển thị dữ liệu nhị phân khi debug.
- Ghi digest SHA-256 trong log hoặc file checksum.
- Đọc byte dump của giao thức hoặc tệp.
- Biểu diễn định danh có độ dài cố định theo quy ước hệ thống.

Ví dụ SHA-256 thường được in thành 64 ký tự hex vì digest có 32 byte.

### 4.2. Chọn Base64 khi cần chuỗi ngắn hơn

Base64 thường phù hợp với:

- Nhúng ảnh hoặc dữ liệu nhị phân vào JSON.
- Đóng gói byte trong giao thức text.
- Biểu diễn byte trong nội dung MIME/email.
- Biểu diễn token nhị phân trong URL khi dùng biến thể URL-safe.

Base64 ngắn hơn hex cho cùng dữ liệu, nhưng vẫn là chuỗi có thể giải mã công khai.

## 5. Mã hóa ký tự (charset encoding) là việc khác

Charset encoding trả lời câu hỏi:

> Những byte nào biểu diễn văn bản này?

Một số charset thường gặp:

- **UTF-8:** mã hóa Unicode bằng 1–4 byte cho một Unicode code point; phổ biến trong web và hệ thống hiện đại.
- **UTF-16:** mã hóa bằng code unit 16 bit; một số code point cần surrogate pair.
- **ISO-8859-1:** bảng ký tự một byte cho tập ký tự giới hạn.
- **Windows-1252:** charset một byte thường gặp trong dữ liệu Windows cũ.

Không thể chỉ nhìn một dãy byte rồi luôn biết văn bản nếu không biết charset hoặc quy ước của dữ liệu.

Ví dụ cùng một byte có thể có cách diễn giải khác nhau theo charset:

```java
byte[] bytes = {(byte) 0xE9};

String latin1 = new String(bytes, java.nio.charset.StandardCharsets.ISO_8859_1);
String utf8 = new String(bytes, StandardCharsets.UTF_8);

System.out.println(latin1);
System.out.println(utf8);
```

`0xE9` là ký tự `é` trong ISO-8859-1. Nhưng một byte đơn `E9` không phải chuỗi UTF-8 hợp lệ hoàn chỉnh cho `é` (UTF-8 của `é` là `C3 A9`); constructor `String` mặc định thay thế dãy byte lỗi bằng ký tự thay thế.

Ví dụ này cho thấy **decode sai charset có thể làm hỏng văn bản** dù byte không thay đổi.

### 5.1. UTF-8 round-trip

Ví dụ:

```java
String original = "Tiếng Việt: Chào bạn!";

byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

System.out.println(original.equals(decoded)); // true
```

Khi cần truyền văn bản giữa các hệ thống, hãy quy định charset trong giao thức (chẳng hạn UTF-8), không để mỗi bên tự đoán.

### 5.2. Decode nghiêm ngặt khi cần phát hiện byte lỗi

`new String(bytes, charset)` có thể thay thế dãy byte không hợp lệ bằng ký tự thay thế. Nếu dữ liệu bắt buộc phải hợp lệ, dùng `CharsetDecoder` với chế độ `REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Với cách này, dữ liệu không hợp lệ làm phát sinh `CharacterCodingException` thay vì âm thầm được thay thế. Điều này hữu ích cho file import, giao thức hoặc dữ liệu cần kiểm soát chất lượng nghiêm ngặt.

## 6. Mã hóa bảo mật (encryption) là gì?

**Encryption** biến bản rõ (*plaintext*) thành bản mã (*ciphertext*) bằng thuật toán mật mã và khóa. Người có khóa phù hợp mới có thể giải mã trở lại.

```text
Plaintext + Key + Algorithm + Parameters
                    |
                    | Encrypt
                    v
               Ciphertext
                    |
                    | Decrypt với key phù hợp
                    v
                Plaintext
```

Khác với hex và Base64:

- Encryption phụ thuộc vào khóa.
- Cùng plaintext có thể tạo ciphertext khác nhau khi sử dụng nonce/IV ngẫu nhiên đúng cách.
- Người không có khóa không thể đơn giản decode để đọc nội dung, nếu thuật toán và quản lý khóa an toàn.
- Mã hóa không làm dữ liệu trở thành text; ciphertext thường vẫn là byte và có thể cần Base64/hex để truyền hoặc lưu trong hệ thống text.

### 6.1. Mã hóa đối xứng và bất đối xứng

| Loại | Cách dùng khóa | Ví dụ | Ứng dụng |
|---|---|---|---|
| Đối xứng | Cùng một khóa bí mật để mã hóa và giải mã | AES-GCM | Mã hóa dữ liệu lưu trữ, payload |
| Bất đối xứng | Cặp public key/private key; vai trò mã hóa/giải mã hoặc ký/xác minh tùy thuật toán | RSA-OAEP, EC-based schemes | Trao đổi khóa, chữ ký số, giao thức bảo mật |

Trong ứng dụng Java thông thường, AES-GCM là lựa chọn phù hợp cho mã hóa dữ liệu đối xứng vì nó vừa bảo vệ tính bí mật, vừa xác thực tính toàn vẹn của ciphertext và dữ liệu bổ sung nếu có.

Không nên tự thiết kế thuật toán mã hóa. Hãy dùng API chuẩn của Java Cryptography Architecture (JCA/JCE) và cấu hình được khuyến nghị.

## 7. Ví dụ AES-GCM trong Java 17

Ví dụ sau minh họa quy trình tạo khóa AES, sinh IV ngẫu nhiên, mã hóa byte và giải mã. Khóa trong ví dụ chỉ được tạo trong bộ nhớ để học; ứng dụng thật cần quản lý và lưu khóa an toàn.

```java
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

public class AesGcmDemo {
    private static final int IV_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    static SecretKey newKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        return generator.generateKey();
    }

    static byte[] encrypt(byte[] plaintext, SecretKey key)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_LENGTH];
        RANDOM.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_LENGTH_BITS, iv);

        cipher.init(Cipher.ENCRYPT_MODE, key, parameters);
        byte[] ciphertext = cipher.doFinal(plaintext);

        // Đóng gói IV + ciphertext (ciphertext có kèm authentication tag).
        byte[] result = new byte[iv.length + ciphertext.length];
        System.arraycopy(iv, 0, result, 0, iv.length);
        System.arraycopy(ciphertext, 0, result, iv.length, ciphertext.length);

        return result;
    }

    static byte[] decrypt(byte[] envelope, SecretKey key)
            throws GeneralSecurityException {
        if (envelope.length < IV_LENGTH + TAG_LENGTH_BITS / 8) {
            throw new IllegalArgumentException("Encrypted data is too short");
        }

        byte[] iv = Arrays.copyOfRange(envelope, 0, IV_LENGTH);
        byte[] ciphertext = Arrays.copyOfRange(
                envelope, IV_LENGTH, envelope.length
        );

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec parameters =
                new GCMParameterSpec(TAG_LENGTH_BITS, iv);

        cipher.init(Cipher.DECRYPT_MODE, key, parameters);
        return cipher.doFinal(ciphertext);
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newKey();

        String message = "Dữ liệu cần được bảo mật";
        byte[] plaintext = message.getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encrypt(plaintext, key);
        String encoded = Base64.getEncoder().encodeToString(encrypted);

        System.out.println("Ciphertext (Base64): " + encoded);

        byte[] decodedEnvelope = Base64.getDecoder().decode(encoded);
        byte[] restored = decrypt(decodedEnvelope, key);

        System.out.println(
                new String(restored, StandardCharsets.UTF_8)
        );
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 AesGcmDemo.java
java AesGcmDemo
```

Dòng Base64 ciphertext sẽ thay đổi giữa các lần chạy vì IV được sinh ngẫu nhiên. Dòng cuối phải khôi phục đúng:

```text
Dữ liệu cần được bảo mật
```

### 7.1. Vai trò của IV/nonce trong AES-GCM

- IV (initialization vector) là tham số đi kèm khi khởi tạo cipher.
- Ví dụ dùng IV dài 12 byte (96 bit), là kích thước được khuyến nghị phổ biến cho GCM.
- IV không cần giữ bí mật; nó phải được lưu cùng ciphertext để giải mã.
- **Không được tái sử dụng cùng IV với cùng khóa AES-GCM.** Việc tái sử dụng nonce có thể làm suy giảm nghiêm trọng bảo mật.
- Ví dụ tạo IV mới bằng `SecureRandom` cho mỗi lần mã hóa. Với hệ thống có lưu lượng lớn, cần có thiết kế quản lý nonce đáp ứng giới hạn và không trùng lặp.

Tag 128 bit giúp phát hiện ciphertext hoặc dữ liệu xác thực bị sửa. Nếu tag không hợp lệ, `doFinal()` khi giải mã ném `AEADBadTagException` (một dạng `GeneralSecurityException`). Không được bỏ qua lỗi này hoặc trả về plaintext một phần.

### 7.2. Khóa phải được quản lý riêng

Ví dụ `KeyGenerator` tạo khóa mới mỗi lần chạy. Nếu mã hóa ở lần chạy thứ nhất rồi ứng dụng kết thúc, khóa trong bộ nhớ biến mất; chương trình chạy lần sau không thể giải mã ciphertext cũ nếu không có đúng khóa ban đầu.

Trong ứng dụng thật:

- Lưu khóa trong hệ thống quản lý khóa phù hợp (KMS, HSM hoặc Java KeyStore với quy trình bảo vệ thích hợp).
- Giới hạn quyền truy cập khóa.
- Không hard-code khóa trong mã nguồn hoặc commit vào Git.
- Không gửi khóa cùng ciphertext qua cùng một kênh.
- Có kế hoạch sao lưu, luân chuyển và thu hồi khóa.
- Không dùng mật khẩu người dùng trực tiếp làm AES key; nếu bắt buộc tạo khóa từ password, cần KDF chuyên dụng như PBKDF2 với salt và tham số phù hợp, hoặc cơ chế quản lý bí mật chuyên nghiệp.

**Base64 ciphertext không thay thế bảo vệ khóa.** Ai có cả ciphertext và khóa đều có thể giải mã; ai có khóa có thể làm mất ý nghĩa của cơ chế bảo mật.

### 7.3. Vì sao không dùng AES/ECB?

Không dùng cấu hình `AES/ECB` cho dữ liệu thông thường cần bảo mật. ECB mã hóa từng block độc lập và làm lộ các mẫu lặp trong plaintext. Với ứng dụng mới, ưu tiên chế độ có xác thực như AES-GCM, dùng IV/nonce đúng cách và xử lý lỗi xác thực.

Cũng không nên dùng AES-CBC mà bỏ qua cơ chế xác thực riêng. Mã hóa bảo mật cần bảo vệ **cả tính bí mật lẫn tính toàn vẹn**, không chỉ làm dữ liệu khó đọc.

## 8. Hashing không phải encryption

Hash function nhận dữ liệu có độ dài bất kỳ và tạo digest có độ dài cố định. Ví dụ `SHA-256` tạo digest 256 bit (32 byte).

```text
Input (bất kỳ độ dài)
       |
       | SHA-256
       v
Digest 32 byte
```

Hashing là phép biến đổi **một chiều** theo mục đích thiết kế. Không có khóa giải mã để khôi phục chính xác input ban đầu từ digest.

Ví dụ Java 17:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class HashDemo {
    public static void main(String[] args) throws Exception {
        String text = "Hello Java 17";

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(
                text.getBytes(StandardCharsets.UTF_8)
        );

        System.out.println(HexFormat.of().formatHex(hash));
    }
}
```

Digest SHA-256 có 32 byte, nên khi biểu diễn hex sẽ có 64 chữ số hex.

### 8.1. Hash dùng để làm gì?

- Kiểm tra dữ liệu có thay đổi so với digest đã biết không.
- Định danh nội dung trong hệ thống lưu trữ.
- Tạo thành phần của chữ ký số và nhiều giao thức mật mã.
- Làm đầu vào cho HMAC hoặc các cơ chế dẫn xuất khóa.

Một digest đơn thuần không xác thực được nguồn gửi. Kẻ tấn công có thể sửa dữ liệu rồi tính lại SHA-256. Nếu cần xác thực bằng bí mật chung, dùng HMAC; nếu cần xác minh danh tính bằng khóa công khai, dùng chữ ký số.

### 8.2. Không lưu mật khẩu bằng SHA-256 đơn thuần

Mật khẩu người dùng có entropy thấp và dễ bị thử đoán. SHA-256 rất nhanh, nên kẻ tấn công có thể thử lượng lớn mật khẩu ngoại tuyến nếu lấy được database hash.

Để lưu mật khẩu, dùng password hashing/KDF chuyên dụng như:

- **Argon2id** (thường được khuyến nghị khi có thư viện phù hợp).
- **bcrypt** hoặc **scrypt**.
- **PBKDF2** với HMAC và tham số chi phí được chọn phù hợp, có salt ngẫu nhiên riêng cho mỗi mật khẩu.

Không tự chế thuật toán bằng cách nối password với chuỗi rồi SHA-256 một lần. Salt không phải bí mật, nhưng phải ngẫu nhiên và riêng cho mỗi mật khẩu; KDF còn cần tham số chi phí đủ mạnh. Hãy dùng thư viện và hướng dẫn bảo mật hiện hành của nền tảng.

## 9. HMAC: kiểm tra toàn vẹn có khóa

HMAC kết hợp hàm hash với **khóa bí mật** để tạo mã xác thực thông điệp. Người có cùng khóa có thể xác minh dữ liệu có bị sửa hay không và có nguồn biết khóa hay không.

Ví dụ với HMAC-SHA-256:

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

byte[] secret = /* lấy khóa bí mật từ nơi quản lý an toàn */;
byte[] message = "transfer=100".getBytes(StandardCharsets.UTF_8);

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secret, "HmacSHA256"));

byte[] tag = mac.doFinal(message);
String tagHex = HexFormat.of().formatHex(tag);
```

`tagHex` là biểu diễn hex của kết quả HMAC. Hex chỉ là cách in tag; tính xác thực đến từ thuật toán HMAC và khóa bí mật.

Khi xác minh, nên so sánh tag bằng phương thức so sánh constant-time phù hợp (ví dụ `MessageDigest.isEqual` cho hai byte array), tránh tự viết vòng lặp dừng ngay khi thấy byte khác nhau.

HMAC không mã hóa nội dung. Người nhận vẫn có thể đọc `transfer=100`; HMAC giúp phát hiện dữ liệu bị sửa bởi người không có khóa.

## 10. Ghép các bước đúng thứ tự

Một hệ thống có thể dùng nhiều cơ chế trong một pipeline:

### 10.1. Biểu diễn văn bản để truyền đi

```text
String
  |
  | UTF-8
  v
byte[]
  |
  | Base64
  v
Chuỗi Base64 để đặt trong JSON
```

Ví dụ:

```java
String text = "Chào Java 17";

String base64 = Base64.getEncoder().encodeToString(
        text.getBytes(StandardCharsets.UTF_8)
);

String jsonValue = "{\\"message\\":\\"" + base64 + "\\"}";
```

Đây chỉ là ví dụ minh họa giá trị. Trong ứng dụng thật, nên dùng JSON library để escape và serialize đúng cú pháp thay vì tự ghép chuỗi.

### 10.2. Mã hóa bảo mật rồi biểu diễn ciphertext

```text
Plaintext String
      |
      | UTF-8
      v
  Plaintext bytes
      |
      | AES-GCM + key + fresh IV
      v
 Ciphertext bytes (+ authentication tag)
      |
      | Base64
      v
 Chuỗi có thể lưu trong JSON/database text
```

Khi nhận:

1. Base64 decode để lấy envelope byte.
2. Tách IV và ciphertext theo giao thức đã định nghĩa.
3. Dùng đúng khóa để AES-GCM decrypt và xác minh tag.
4. Chỉ sau khi giải mã và xác thực thành công mới diễn giải plaintext byte bằng UTF-8.

Không decode Base64 rồi nghĩ nội dung đã được giải mã bảo mật. Base64 chỉ tháo lớp biểu diễn; bước AES-GCM mới là bước giải mã mật mã.

### 10.3. Hash và biểu diễn digest

```text
Dữ liệu bytes
     |
     | SHA-256
     v
Digest bytes (32 byte)
     |
     | Hex
     v
64 ký tự hex
```

Hash không có bước decode ngược. Hex ở cuối chỉ giúp hiển thị digest dưới dạng text.

## 11. Bảng so sánh để chọn đúng API Java 17

| Nhu cầu | API phù hợp | Đầu vào | Đầu ra |
|---|---|---|---|
| String thành byte theo UTF-8 | `String.getBytes(StandardCharsets.UTF_8)` | `String` | `byte[]` |
| Byte thành String UTF-8 | `new String(bytes, StandardCharsets.UTF_8)` | `byte[]` | `String` |
| Byte thành hex | `HexFormat.of().formatHex(bytes)` | `byte[]` | `String` |
| Hex thành byte | `HexFormat.of().parseHex(hex)` | `String` | `byte[]` |
| Byte thành Base64 | `Base64.getEncoder().encodeToString(bytes)` | `byte[]` | `String` |
| Base64 thành byte | `Base64.getDecoder().decode(text)` | `String` | `byte[]` |
| Mã hóa AES-GCM | `Cipher.getInstance("AES/GCM/NoPadding")` | `byte[]` + key + IV | `byte[]` ciphertext |
| Hash SHA-256 | `MessageDigest.getInstance("SHA-256")` | `byte[]` | `byte[]` digest |
| HMAC-SHA-256 | `Mac.getInstance("HmacSHA256")` | `byte[]` + secret key | `byte[]` tag |

Các API trên đều có trong Java 17. `HexFormat` được bổ sung từ Java 17; `Base64` có từ Java 8; `StandardCharsets`, `MessageDigest`, `Cipher` và `Mac` thuộc các API Java nền tảng.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chuỗi tiếng Việt bị lỗi ký tự | Ghi bằng charset này, đọc bằng charset khác | Chỉ định UTF-8 ở cả hai đầu |
| Hex decode báo lỗi | Có ký tự không phải hex, số chữ số lẻ hoặc delimiter không đúng | Kiểm tra định dạng; dùng `HexFormat` tương ứng |
| Base64 decoder báo lỗi | Dùng sai biến thể hoặc chuỗi bị cắt/hỏng | Xác định Basic, URL-safe hay MIME; bảo toàn padding theo giao thức |
| Base64 string dài hơn dữ liệu gốc | Đây là overhead bình thường | Base64 tăng khoảng 1/3 kích thước |
| Nghĩ Base64 đã bảo vệ bí mật | Nhầm encoding với encryption | Dùng encryption phù hợp nếu cần confidentiality |
| AES-GCM decrypt báo tag không hợp lệ | Sai khóa, IV, ciphertext bị sửa hoặc AAD không khớp | Xác minh envelope, khóa, nonce và dữ liệu xác thực; không bỏ qua lỗi |
| Giải mã AES không được sau khi restart | Khóa sinh ngẫu nhiên không được lưu an toàn | Quản lý khóa bền vững bằng KMS/keystore |
| Dùng SHA-256 để lưu mật khẩu | Hash nhanh, dễ bị brute-force | Dùng Argon2id, bcrypt, scrypt hoặc PBKDF2 cấu hình đúng |
| Đường dẫn Windows bị biến thành tab/newline | Dùng `translateEscapes()` lên chuỗi chứa backslash có chủ ý | Không dịch escape nếu dữ liệu không theo cú pháp escape Java |

### 12.1. Lỗi hex do byte âm

Đừng tự định dạng byte bằng `Integer.toHexString(value)` mà không xử lý giá trị không dấu:

```java
byte b = (byte) 0xFF;

System.out.println(Integer.toHexString(b));       // ffffffff
System.out.println(Integer.toHexString(b & 0xFF)); // ff
```

`byte` được sign-extend khi chuyển thành `int`. Dùng `b & 0xFF` hoặc `HexFormat` để có biểu diễn byte chính xác.

### 12.2. Lỗi do mất padding Base64

Nếu giao thức dùng Basic Base64 mặc định, đừng tự bỏ `=` padding rồi mong decoder nào cũng chấp nhận mọi dạng. Chỉ dùng `withoutPadding()` khi hai phía đã thống nhất quy ước; với URL-safe, chọn `getUrlEncoder()` và `getUrlDecoder()`.

### 12.3. Lỗi do dùng charset mặc định

Không dựa vào `new String(bytes)` hoặc `text.getBytes()` trong dữ liệu cần trao đổi giữa hệ thống. Chỉ định charset giúp kết quả nhất quán qua máy phát triển, server và container.

### 12.4. Lỗi do dùng Base64 để “ẩn” thông tin

Nếu chuỗi có thể được decode mà không cần secret key, nội dung không được giữ bí mật. Token hoặc mật khẩu không nên chỉ được Base64 hóa rồi lưu ở nơi công khai.

## 13. Ví dụ hoàn chỉnh: UTF-8, hex và Base64 trên cùng dữ liệu

Tạo file `EncodingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;

public class EncodingDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt - Java 17";

        // Bước 1: văn bản -> bytes bằng UTF-8.
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        // Bước 2a: biểu diễn cùng bytes bằng hex.
        String hex = HexFormat.of().formatHex(bytes);

        // Bước 2b: biểu diễn cùng bytes bằng Base64.
        String base64 = Base64.getEncoder().encodeToString(bytes);

        System.out.println("Original: " + original);
        System.out.println("Hex:      " + hex);
        System.out.println("Base64:   " + base64);

        // Bước 3a: decode hex -> bytes -> UTF-8.
        byte[] fromHex = HexFormat.of().parseHex(hex);
        String textFromHex = new String(fromHex, StandardCharsets.UTF_8);

        // Bước 3b: decode Base64 -> bytes -> UTF-8.
        byte[] fromBase64 = Base64.getDecoder().decode(base64);
        String textFromBase64 =
                new String(fromBase64, StandardCharsets.UTF_8);

        System.out.println("From hex:    " + textFromHex);
        System.out.println("From Base64: " + textFromBase64);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 EncodingDemo.java
java EncodingDemo
```

Giá trị hex và Base64 cụ thể được tính từ byte UTF-8 của chuỗi. Hai dòng cuối phải khôi phục đúng văn bản ban đầu.

**Hãy quan sát:** hex và Base64 được tạo từ cùng một `byte[]`. Chúng không thực hiện mã hóa ký tự; UTF-8 mới là bước chuyển văn bản thành byte. Cũng không có bước nào trong ví dụ giữ bí mật dữ liệu.

## 14. Bài tập tự luyện

### Bài 1 — Nhận diện từng phép biến đổi

Cho chuỗi `"A"`. Hãy mô tả chuỗi thao tác sau:

```java
byte[] bytes = "A".getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(bytes);
String base64 = Base64.getEncoder().encodeToString(bytes);
```

**Đáp án:**

- `"A"` là văn bản.
- UTF-8 chuyển thành byte `0x41`.
- Hex biểu diễn byte đó thành `"41"`.
- Base64 biểu diễn byte đó thành `"QQ=="`.
- Cả `"41"` và `"QQ=="` đều có thể chuyển lại byte `0x41`; chúng không phải ciphertext.

### Bài 2 — Vì sao Base64 không phải encryption?

```java
String secret = "my-token";
String encoded = Base64.getEncoder().encodeToString(
        secret.getBytes(StandardCharsets.UTF_8)
);
```

**Đáp án:** Bất kỳ ai cũng có thể gọi `Base64.getDecoder().decode(encoded)` để khôi phục byte và đọc token. Không có khóa bí mật hay thuật toán mã hóa trong thao tác này.

### Bài 3 — Chọn charset

Một ứng dụng Java 17 ghi chuỗi tiếng Việt thành byte trên Windows và ứng dụng Linux đọc lại. Cần làm gì?

**Đáp án:** Chỉ định cùng charset ở cả hai đầu, thường là `StandardCharsets.UTF_8`. Không để hai môi trường tự dùng charset mặc định.

### Bài 4 — Hash hay encryption?

Bạn cần lưu dấu kiểm tra để phát hiện file có bị thay đổi, nhưng không cần khôi phục file từ giá trị kiểm tra. Chọn gì?

**Đáp án:** Dùng hàm hash như SHA-256 để tạo digest. Nếu cần xác thực digest trước kẻ tấn công có thể tự tính lại, dùng HMAC hoặc chữ ký số theo mô hình tin cậy.

### Bài 5 — Cần lưu bí mật có thể khôi phục

Bạn cần lưu một thông điệp và sau đó đọc lại, nhưng người không có khóa không được đọc nội dung. Chọn gì?

**Đáp án:** Dùng encryption có xác thực như AES-GCM, quản lý khóa an toàn. Nếu cần đưa ciphertext vào JSON, có thể Base64 hóa ciphertext bytes sau khi mã hóa. Base64 chỉ là lớp biểu diễn, không thay thế encryption.

## 15. Ghi nhớ

- **Charset encoding** chuyển văn bản thành byte; chọn rõ UTF-8 để tránh phụ thuộc môi trường.
- **Hex** biểu diễn mỗi byte bằng hai chữ số hệ 16; hữu ích cho debug và đọc byte.
- **Base64** nhóm ba byte thành bốn ký tự; hữu ích khi truyền dữ liệu nhị phân qua kênh text.
- **Hex và Base64 không giữ bí mật.** Ai cũng có thể chuyển ngược nếu biết định dạng.
- **Encryption** dùng khóa và thuật toán mật mã để bảo vệ nội dung; cần quản lý khóa, IV/nonce và xác thực đúng.
- **Hash** là phép băm một chiều; không phải phương pháp mã hóa có thể giải mã.
- **HMAC** dùng khóa để xác thực dữ liệu nhưng không che nội dung.
- Các lớp có thể kết hợp: UTF-8 tạo byte, AES-GCM mã hóa byte, Base64 biểu diễn ciphertext, rồi Base64 decode và AES-GCM decrypt ở phía nhận.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 API — `java.util.HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html).
- [Java SE 17 API — `java.util.Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html).
- [Java SE 17 API — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Java SE 17 API — `java.nio.charset.CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Java SE 17 API — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html).
- [Java SE 17 API — `javax.crypto.spec.GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html).
- [Java SE 17 API — `java.security.MessageDigest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html).
- [Java SE 17 API — `javax.crypto.Mac`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html).
- [JEP 400 — UTF-8 by Default (Java 18)](https://openjdk.org/jeps/400).

