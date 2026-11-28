# String.getBytes() và new String(byte[]): nhận diện phụ thuộc vào charset mặc định

## 1. Vấn đề: cùng một chuỗi, tại sao có thể tạo ra các byte khác nhau?

Trong Java, `String` biểu diễn văn bản Unicode; `byte[]` chỉ chứa dữ liệu nhị phân. Khi đưa văn bản ra tệp, gửi qua mạng hoặc đọc dữ liệu từ hệ thống khác, chương trình phải quyết định **charset** (bộ quy tắc ánh xạ ký tự ↔ byte).

Hai thao tác rất thường gặp có một tham số *ngầm*:

```java
String original = "café";
byte[] bytes = original.getBytes(); // String -> byte[]: encode bằng charset mặc định
String decoded = new String(bytes); // byte[] -> String: decode bằng charset mặc định
```

Tham số ngầm đó là `Charset.defaultCharset()`. Vì vậy, hai lời gọi trên có thể đúng khi làm việc với một môi trường nhất định nhưng sai khi trao đổi dữ liệu với một hệ thống có quy ước mã hóa khác. Đây là vấn đề về **hợp đồng định dạng dữ liệu**, kể cả khi ứng dụng chạy trên JDK hiện đại.

### Mục tiêu học tập

- Phân biệt `String`, byte và charset; nhận biết các cách gọi API phụ thuộc charset mặc định.
- Hiểu thay đổi vẫn còn hiệu lực của **Java 18 / JEP 400: UTF-8 by Default**, cùng giới hạn của thay đổi này.
- Chọn charset theo đặc tả của tệp, giao thức hoặc đối tác; chủ động chỉ rõ charset ở cả lúc encode và decode.
- Phát hiện dữ liệu đầu vào không hợp lệ, xử lý lỗi mã hóa và kiểm tra chương trình khi nâng cấp JDK.

## 2. Hợp đồng API thực sự là gì?

| Lời gọi | Công việc | Charset được sử dụng |
| --- | --- | --- |
| `text.getBytes()` | Mã hóa `String` thành `byte[]` | `Charset.defaultCharset()` |
| `new String(bytes)` | Giải mã toàn bộ `byte[]` thành `String` | `Charset.defaultCharset()` |
| `new String(bytes, offset, length)` | Giải mã một phần của `byte[]` | `Charset.defaultCharset()` |
| `text.getBytes(StandardCharsets.UTF_8)` | Mã hóa với UTF-8 | UTF-8, được chỉ rõ |
| `new String(bytes, StandardCharsets.UTF_8)` | Giải mã với UTF-8 | UTF-8, được chỉ rõ |
| `new String(bytes, offset, length, charset)` | Giải mã một phần, có charset | Chính `charset` được truyền vào |

Có hai chiều xử lý:

```text
Văn bản trong String ── encode(charset A) ──> byte[]
Văn bản trong String <── decode(charset B) ── byte[]

Muốn giữ đúng nội dung, A và B phải phù hợp với cùng một định dạng dữ liệu.
```

Không thể quyết định charset chỉ bằng kiểu `byte[]`. Ví dụ, ký tự `é` có hai cách biểu diễn khác nhau:

| Văn bản | UTF-8 (hex) | ISO-8859-1 (hex) |
| --- | --- | --- |
| `café` | `63 61 66 C3 A9` | `63 61 66 E9` |

Nếu byte UTF-8 `63 61 66 C3 A9` bị giải mã theo ISO-8859-1, kết quả là `cafÃ©` thay vì `café`. Đây là ví dụ của *mojibake*: các byte hợp lệ đã được đọc bằng sai quy tắc.

> Số byte không nhất thiết bằng `String.length()`. UTF-8 dùng số byte khác nhau tùy mã điểm Unicode, còn `String.length()` đếm đơn vị mã UTF-16. Đừng dùng số ký tự để suy ra kích thước payload.

## 3. Java 18 thay đổi điều gì và điều gì vẫn cần chú ý?

**JEP 400**, có hiệu lực từ Java 18, quy định **UTF-8 là default charset theo mặc định** cho các Java SE API sử dụng charset mặc định. Điều này vẫn được áp dụng trên các JDK hiện đại: trong cấu hình thông thường, `Charset.defaultCharset()` trả về UTF-8, giúp hành vi thống nhất hơn giữa các hệ điều hành và locale.

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset()); // Thông thường: UTF-8 trên JDK 18+
```

Tuy nhiên, cần hiểu chính xác hai điều:

1. **Default charset vẫn là một phần của cấu hình chạy.** Theo đặc tả `Charset.defaultCharset()`, một JDK có thể hỗ trợ cấu hình từ lúc khởi động, chẳng hạn `-Dfile.encoding=COMPAT` để dùng cách xác định charset theo môi trường hệ điều hành như trước Java 18. Khi đó, `getBytes()` và `new String(bytes)` vẫn phụ thuộc môi trường chạy.
2. **UTF-8 mặc định không chuyển đổi dữ liệu cũ thành UTF-8.** Một tệp hoặc message vốn được mã hóa bằng ISO-8859-1, Windows-1252 hay một charset được quy định riêng vẫn phải được giải mã đúng theo định dạng ấy. Thay đổi default charset không thể tự nhận diện encoding thực của dữ liệu.

Vì vậy, quy tắc thực hành bền vững trên JDK 18 và các JDK mới hơn là: **ở ranh giới nhập/xuất văn bản, truyền charset rõ ràng theo hợp đồng dữ liệu**, ngay cả khi ứng dụng hiện tại đang báo default charset là UTF-8.

## 4. Chương trình kiểm chứng có thể chạy trên Java 18+

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class DefaultCharsetDemo {
    public static void main(String[] args) {
        String original = "café";

        byte[] implicit = original.getBytes();
        byte[] explicit = original.getBytes(StandardCharsets.UTF_8);

        System.out.println("Default charset: " + Charset.defaultCharset());
        System.out.println("getBytes():       " + HexFormat.of().formatHex(implicit));
        System.out.println("getBytes(UTF_8):  " + HexFormat.of().formatHex(explicit));

        String restored = new String(explicit, StandardCharsets.UTF_8);
        System.out.println("Restored:         " + restored);
    }
}
```

Trên JDK 18+ với cấu hình mặc định thông thường, hai dòng hex cùng là `636166c3a9`. Nếu chạy trong một cấu hình tương thích có default charset khác, **chỉ** dòng `getBytes()` có thể thay đổi; `getBytes(UTF_8)` vẫn cho các byte UTF-8 đã xác định.

Không nên viết kiểm thử dựa trên giả định `getBytes()` *luôn* giống UTF-8 trong mọi cấu hình triển khai. Với dữ liệu truyền giữa các tiến trình, kết quả mong đợi nên bắt nguồn từ charset được thỏa thuận, không bắt nguồn từ cài đặt trên máy chạy kiểm thử.

## 5. Nhận diện lỗi khi đọc dữ liệu từ bên ngoài

Giả sử một đối tác vẫn gửi tên sản phẩm theo ISO-8859-1; bốn byte `63 61 66 E9` tương ứng với `café`:

```java
import java.nio.charset.StandardCharsets;

byte[] input = {
    (byte) 0x63, (byte) 0x61, (byte) 0x66, (byte) 0xE9
};

// Không an toàn: cách diễn giải phụ thuộc vào default charset của JVM.
String inferred = new String(input);

// Sai định dạng: byte E9 một mình không hợp lệ trong UTF-8.
String wrong = new String(input, StandardCharsets.UTF_8);

// Đúng hợp đồng bên gửi: các byte được định nghĩa là ISO-8859-1.
String correct = new String(input, StandardCharsets.ISO_8859_1);
System.out.println(correct); // café
```

Trong ví dụ này, `new String(input, StandardCharsets.UTF_8)` thay chuỗi byte UTF-8 không hợp lệ bằng ký tự thay thế (thường hiển thị là `�`), nên không thể khôi phục chữ `é` bằng cách mã hóa lại kết quả. Với `new String(input)`, Javadoc quy định **hành vi khi byte không hợp lệ trong default charset là không được xác định**; đừng dựa vào một ký tự thay thế cụ thể của lời gọi không tham số.

Các dấu hiệu đáng điều tra gồm:

- Chữ tiếng Việt mất dấu, biến thành `�`, hoặc xuất hiện dạng như `Ã`, `Â` sau khi trao đổi file/message.
- Kết quả khác nhau giữa máy lập trình, CI, container và môi trường triển khai.
- Một luồng nhận UTF-8 nhưng chương trình lại dùng `new String(bytes)`, hoặc chương trình phát byte bằng `getBytes()` mà bên nhận đòi một charset cụ thể.
- Kiểm thử chỉ dùng ASCII nên không phát hiện lỗi: các ký tự ASCII cơ bản có cùng byte trong UTF-8 và nhiều charset thông dụng.

**Quan trọng:** Không dùng `new String(bytes)` để “xem thử” nội dung tùy ý của dữ liệu nhị phân, chẳng hạn file nén, ảnh hoặc ciphertext. Chỉ giải mã khi byte thực sự được xác định là văn bản và biết charset của nó.

## 6. Sửa mã tại đúng ranh giới dữ liệu

Khi định dạng là UTF-8, có thể thể hiện hợp đồng ngay trong code:

```java
import java.nio.charset.StandardCharsets;

static byte[] encodePayload(String message) {
    return message.getBytes(StandardCharsets.UTF_8);
}

static String decodePayload(byte[] payload) {
    return new String(payload, StandardCharsets.UTF_8);
}
```

Nếu định dạng đầu vào đã quy định charset khác, sử dụng **đúng charset ấy** thay vì áp UTF-8 cho mọi trường hợp. Ví dụ, API nhận `byte[]` từ một hệ thống cũ có hợp đồng ISO-8859-1 thì gọi `new String(payload, StandardCharsets.ISO_8859_1)`; nếu giao thức quy định UTF-8 thì dùng UTF-8.

Với I/O dạng stream, cùng nguyên tắc được áp dụng tại thời điểm tạo reader/writer:

```java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

// input và output là các stream do tầng I/O cung cấp.
InputStreamReader reader = new InputStreamReader(input, StandardCharsets.UTF_8);
OutputStreamWriter writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);
```

Với thao tác tệp dạng văn bản trên JDK hiện đại, có thể dùng `Files.readString(path, StandardCharsets.UTF_8)` và `Files.writeString(path, text, StandardCharsets.UTF_8)`. Lưu ý, các overload `Files.readString(path)` và `Files.writeString(path, text)` **đã mặc định UTF-8 theo chính hợp đồng API**, không phải ví dụ điển hình của phụ thuộc `Charset.defaultCharset()`. Khi rà soát code, hãy xem đặc tả từng API thay vì suy rằng mọi overload thiếu charset đều có cùng hành vi.

### Bảng quyết định khi gặp lời gọi thiếu charset

| Bối cảnh | Cách xử lý |
| --- | --- |
| Serialize văn bản theo giao thức UTF-8 | Dùng `getBytes(StandardCharsets.UTF_8)`. |
| Parse payload UTF-8 từ mạng, queue hoặc database driver | Dùng `new String(payload, StandardCharsets.UTF_8)` nếu đầu vào thực sự là byte văn bản. |
| Đọc file của đối tác có charset được công bố khác UTF-8 | Giải mã bằng charset đã công bố; không đoán từ default của JVM. |
| Dữ liệu chưa rõ charset | Tra hợp đồng, metadata hoặc nguồn tạo dữ liệu; không mặc định suy đoán. |
| Đầu vào phải được kiểm tra nghiêm ngặt | Dùng `CharsetDecoder` với `CodingErrorAction.REPORT` để phát hiện byte không hợp lệ. |

## 7. Khi cần chặn dữ liệu hỏng thay vì âm thầm thay thế

`new String(bytes, charset)` có đặc tả rõ rằng sẽ **thay thế** các chuỗi byte lỗi hoặc không thể ánh xạ bằng ký tự thay thế mặc định. Cách này phù hợp với một số trường hợp hiển thị văn bản, nhưng có thể che khuất lỗi dữ liệu trong import hoặc tích hợp hệ thống.

Nếu đầu vào bắt buộc là UTF-8 hợp lệ, dùng decoder báo lỗi:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] input) throws CharacterCodingException {
    return StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(input))
            .toString();
}
```

Ví dụ, `decodeUtf8Strict(new byte[] {(byte) 0xE9})` ném `MalformedInputException` (một `CharacterCodingException`) vì `E9` đứng riêng không phải một chuỗi UTF-8 hợp lệ. Hãy xử lý ngoại lệ theo hợp đồng hệ thống: từ chối record, báo lỗi cho bên gửi hoặc ghi lại sự kiện; đừng tự gán một charset khác để “sửa” dữ liệu khi chưa có bằng chứng.

Chiều encode cũng có rủi ro mất dữ liệu: `getBytes(charset)` thay thế ký tự không biểu diễn được trong charset đích. Khi cần cấm mất ký tự, dùng `CharsetEncoder` với `CodingErrorAction.REPORT`, tương tự decoder ở trên.

## 8. Kiểm tra cấu hình và kế hoạch rà soát code

Để kiểm chứng ứng dụng đang chạy bằng charset nào, có thể log thông tin tại thời điểm khởi động:

```java
import java.nio.charset.Charset;

System.out.println("Java: " + Runtime.version());
System.out.println("Default charset: " + Charset.defaultCharset());
System.out.println("file.encoding: " + System.getProperty("file.encoding"));
System.out.println("native.encoding: " + System.getProperty("native.encoding"));
```

`file.encoding` và `native.encoding` hữu ích để **chẩn đoán**; `Charset.defaultCharset()` mới là cách hỏi giá trị default charset JVM đang dùng. Đừng xây dựng giải pháp dựa vào việc `System.setProperty("file.encoding", "...")` sau khi JVM đã khởi động: đây không phải cơ chế di chuyển an toàn các hợp đồng mã hóa của API. Cấu hình tương thích `-Dfile.encoding=COMPAT`, nếu được JDK hỗ trợ, là công cụ phân tích khác biệt môi trường chứ không phải cách sửa lâu dài cho một định dạng dữ liệu chưa rõ.

Khi nâng cấp dự án lên JDK 18+ hoặc rà soát hệ thống hiện tại:

1. Tìm `getBytes()`, `new String(bytes)` và `new String(bytes, offset, length)` trong phần code đổi giữa văn bản và byte.
2. Lần theo nguồn và đích của mỗi `byte[]`: ai ghi, ai đọc, hợp đồng encoding là gì, dữ liệu có thể chứa tiếng Việt hoặc ký tự ngoài ASCII không?
3. Chọn `StandardCharsets.UTF_8` hoặc charset tương ứng với **định dạng thật**; sửa cả chiều phát lẫn chiều nhận khi cùng sở hữu giao thức.
4. Viết ca kiểm thử có `café`, `Tiếng Việt`, ký tự ngoài BMP như `😀`, cùng một payload sai encoding hoặc byte không hợp lệ; kiểm thử cả byte hex và nội dung khôi phục.
5. Với dữ liệu cũ, dùng tập mẫu byte lấy từ nguồn thật và xác nhận charset trước khi chuyển đổi hoặc di trú.

### Ví dụ kiểm thử độc lập với default charset

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String value = "café";
byte[] expected = {
    (byte) 0x63, (byte) 0x61, (byte) 0x66,
    (byte) 0xC3, (byte) 0xA9
};

byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
if (!Arrays.equals(encoded, expected)) {
    throw new AssertionError("UTF-8 bytes do not match the protocol");
}

String decoded = new String(expected, StandardCharsets.UTF_8);
if (!value.equals(decoded)) {
    throw new AssertionError("UTF-8 round-trip failed");
}
```

Bài kiểm thử này kiểm tra hợp đồng byte UTF-8 cụ thể và tiếp tục có ý nghĩa khi thay hệ điều hành, locale hoặc JDK. Với hệ thống thực tế, bổ sung kiểm thử lỗi cho các byte không hợp lệ và đường đi dữ liệu qua các lớp I/O.

## 9. Những nhận định dễ nhầm

- **“Java 18 dùng UTF-8 mặc định nên bỏ charset ở mọi nơi đều an toàn.”** Sai. Charset mặc định có thể được cấu hình và hệ thống bên ngoài có thể dùng encoding khác; hãy chỉ rõ charset ở ranh giới dữ liệu.
- **“Đọc sai encoding thì mã hóa lại là khôi phục được.”** Không chắc. Một số bước decode hoặc encode thay thế ký tự không hợp lệ khiến thông tin gốc mất đi.
- **“`String.getBytes()` trả về mỗi ký tự một byte.”** Sai. Kích thước byte tùy charset và nội dung.
- **“Mọi API Java không nhận charset đều dùng JVM default charset.”** Sai. Cần xem hợp đồng riêng của API; chẳng hạn các overload `Files.readString` không truyền charset đã định nghĩa UTF-8.
- **“In ra console đúng là chứng minh byte trên mạng đúng.”** Sai. Hiển thị terminal còn phụ thuộc cấu hình đầu ra; hãy kiểm tra byte hex thực tế và charset mà phía nhận yêu cầu.

## 10. Tài liệu tham chiếu

- [JEP 400 — UTF-8 by Default (OpenJDK)](https://openjdk.org/jeps/400): thay đổi từ Java 18 và phạm vi tác động của default charset.
- [`String` API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): hợp đồng của `getBytes()`, `getBytes(Charset)`, `String(byte[])`, `String(byte[], Charset)`.
- [`Charset` API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): `defaultCharset()`, quy tắc UTF-8 mặc định và thông tin `file.encoding=COMPAT`.
- [JDK 18 Release Notes — JEP 400 (Oracle)](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): ghi nhận chính thức thay đổi từ JDK 18.
