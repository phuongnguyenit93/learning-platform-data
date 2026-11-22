# Độc lập giữa biểu diễn UTF-16 trong bộ nhớ và mã hóa tệp

Một chuỗi Java không bắt buộc phải được ghi ra tệp UTF-16. Bạn có thể đọc tệp UTF-8 thành `String`, xử lý bằng API chuỗi Java, rồi ghi kết quả thành UTF-8 hoặc một mã hóa khác phù hợp.

Để tránh nhầm, hãy tách ba tầng: **hợp đồng của API chuỗi**, **cách JVM tổ chức bộ nhớ**, và **dãy byte trong tệp**.

## 1. Ba tầng cần phân biệt

| Tầng | Điều cần quan tâm |
| --- | --- |
| API `String`, `char` và chỉ số | Đơn vị mã UTF-16, cặp surrogate, điểm mã |
| Bộ nhớ vật lý trong JVM | Chi tiết triển khai, cấu trúc đối tượng, tối ưu lưu trữ |
| Tệp hoặc dữ liệu trên mạng | Dãy byte được tạo/đọc theo charset đã chọn |

Theo hợp đồng `String`, chỉ số tính theo đơn vị mã UTF-16. Ký tự bổ sung dùng một cặp surrogate nên chiếm hai vị trí. [Tài liệu String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)

Điều đó không có nghĩa tệp chứa chuỗi phải có hai byte cho mỗi vị trí, hoặc mọi `String` luôn nằm trong một mảng `char[]`.

OpenJDK hiện đại có tối ưu Compact Strings, dùng cấu trúc lưu trữ có thể tận dụng Latin-1 khi phù hợp hoặc biểu diễn UTF-16. Đây là chi tiết triển khai; API `charAt` và `length` vẫn giữ hợp đồng. [Mã nguồn String của OpenJDK](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/String.java)

Vì thế, câu “Java dùng UTF-16” trong bài xử lý chuỗi nên được hiểu ở tầng biểu diễn và API. Nó không phải công thức đo chính xác tổng bộ nhớ của đối tượng hoặc một quy tắc chọn mã hóa tệp.

## 2. Ranh giới chuyển đổi là nơi có byte

Quá trình đọc và ghi:

```text
Byte trong tệp
    │ giải mã (decode) theo charset đầu vào
    ▼
String trong chương trình
    │ xử lý bằng API Java
    │ mã hóa (encode) theo charset đầu ra
    ▼
Byte trong tệp mới
```

Hai chiều tương ứng trong mã:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] output = text.getBytes(StandardCharsets.UTF_8);
```

Đây là hai câu lệnh minh họa bên trong phương thức, với biến `bytes` đã có và đã nhập `java.nio.charset.StandardCharsets`.

`String` sau giải mã không mang một thuộc tính “charset gốc” để tự ghi lại đúng định dạng ban đầu. Nếu ứng dụng cần bảo toàn lựa chọn mã hóa đầu vào, hãy giữ thông tin đó riêng.

Đuôi `.txt` hay `.csv` cũng không tự quyết định charset. Cần hợp đồng dữ liệu, cấu hình hoặc siêu dữ liệu đáng tin.

## 3. Cùng nội dung, các dãy byte khác nhau

Xét chuỗi `Aé😀`:

```text
Điểm mã:          U+0041 U+00E9 U+1F600
Đơn vị UTF-16:      0041   00E9   D83D DE00
```

Ở tầng API Java:

- `length()` bằng 4 đơn vị mã.
- Số điểm mã bằng 3.

Khi ghi không thêm BOM:

| Charset | Dãy byte hex | Kích thước |
| --- | --- | --- |
| UTF-8 | `41 C3 A9 F0 9F 98 80` | 7 byte |
| UTF-16LE | `41 00 E9 00 3D D8 00 DE` | 8 byte |
| UTF-16BE | `00 41 00 E9 D8 3D DE 00` | 8 byte |

Hai byte của một đơn vị UTF-16 được ghi theo thứ tự little-endian hoặc big-endian. Đây là thứ tự **byte**, khác với thứ tự surrogate cao–thấp: cặp surrogate vẫn theo đúng thứ tự hai đơn vị mã.

`StandardCharsets` cung cấp các hằng như `UTF_8`, `UTF_16LE` và `UTF_16BE` để chỉ định rõ lựa chọn. [Tài liệu StandardCharsets](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html)

Không lấy `text.length()` làm kích thước tệp UTF-8. Nếu cần biết số byte được tạo, hãy xét kết quả mã hóa hoặc đo tệp.

## 4. Chương trình ghi và đọc hai mã hóa

Chương trình sau tạo một thư mục riêng dưới thư mục tạm, ghi hai tệp, kiểm tra byte rồi dọn những tệp nó vừa tạo. Nếu tên thư mục đã tồn tại thì `createDirectory` báo lỗi; chương trình không dùng lại một thư mục cũ.

Lưu thành **FileEncodingDemo.java**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileEncodingDemo {
    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < bytes.length; i++) {
            if (i > 0) out.append(' ');
            out.append(String.format("%02X", bytes[i] & 0xFF));
        }
        return out.toString();
    }

    public static void main(String[] args) throws Exception {
        String text = new StringBuilder()
                .append('A').append((char) 0x00E9)
                .appendCodePoint(0x1F600).toString();

        Path folder = Path.of(System.getProperty("java.io.tmpdir"),
                "encoding-boundary-" + Long.toUnsignedString(System.nanoTime()));
        Files.createDirectory(folder);
        Path utf8 = folder.resolve("utf8.txt");
        Path utf16le = folder.resolve("utf16le.txt");
        try {
            Files.writeString(utf8, text, StandardCharsets.UTF_8);
            Files.writeString(utf16le, text, StandardCharsets.UTF_16LE);

            System.out.println("UTF-16 units=" + text.length());
            System.out.println("code points="
                    + text.codePointCount(0, text.length()));
            System.out.println("UTF-8 bytes=" + Files.size(utf8));
            System.out.println("UTF-8 hex=" + hex(Files.readAllBytes(utf8)));
            System.out.println("UTF-16LE bytes=" + Files.size(utf16le));
            System.out.println("UTF-16LE hex="
                    + hex(Files.readAllBytes(utf16le)));

            String from8 = Files.readString(utf8, StandardCharsets.UTF_8);
            String from16 = Files.readString(utf16le, StandardCharsets.UTF_16LE);
            System.out.println("UTF-8 round trip=" + text.equals(from8));
            System.out.println("UTF-16LE round trip=" + text.equals(from16));

            String wrong = Files.readString(utf8, StandardCharsets.ISO_8859_1);
            System.out.println("wrong charset equal=" + text.equals(wrong));

            byte[] malformed = {(byte) 0xC3, (byte) 0x28};
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(malformed));
            } catch (CharacterCodingException ex) {
                System.out.println("malformed UTF-8 rejected");
            }
        } finally {
            Files.deleteIfExists(utf8);
            Files.deleteIfExists(utf16le);
            Files.deleteIfExists(folder);
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 FileEncodingDemo.java
java FileEncodingDemo
```

Stdout:

```text
UTF-16 units=4
code points=3
UTF-8 bytes=7
UTF-8 hex=41 C3 A9 F0 9F 98 80
UTF-16LE bytes=8
UTF-16LE hex=41 00 E9 00 3D D8 00 DE
UTF-8 round trip=true
UTF-16LE round trip=true
wrong charset equal=false
malformed UTF-8 rejected
```

Hai dòng `round trip=true` chứng minh các dãy byte khác nhau có thể giải mã về cùng nội dung khi chọn charset phù hợp. Chúng không có nghĩa hai tệp giống nhau về byte.

Chương trình chỉ in số và hex để không phụ thuộc việc terminal có phông emoji hay đang dùng bảng mã nào.

`Files.readString(path, charset)` và `writeString(path, text, charset)` cho phép nêu rõ charset ngay tại ranh giới tệp. [Tài liệu Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#readString(java.nio.file.Path,java.nio.charset.Charset))

## 5. Đọc sai charset có thể không báo lỗi

Chương trình cố ý đọc byte UTF-8 bằng ISO-8859-1:

```java
String wrong = Files.readString(utf8, StandardCharsets.ISO_8859_1);
```

Đây là sai hợp đồng, dù thao tác đọc thành công. Byte `C3 A9` vốn cùng biểu diễn é trong UTF-8 bị diễn giải thành các giá trị khác khi đọc theo ISO-8859-1. Nội dung trở thành văn bản sai mã, thường gọi là mojibake.

Tình huống này cho thấy hai điều:

1. Không có ngoại lệ không chứng minh bạn đã chọn đúng charset.
2. Biết cách `String` đánh chỉ số theo UTF-16 không giúp đoán charset của một tệp bất kỳ.

Sau khi giải mã sai, ghi chuỗi ấy bằng UTF-8 chỉ mã hóa nội dung đã sai sang UTF-8. Việc chọn UTF-8 ở bước sau không tự khôi phục ý nghĩa ban đầu.

Khi sửa dữ liệu, cần xác định dãy byte gốc và đường chuyển đổi đã xảy ra; không thay ký tự bằng phỏng đoán nếu chưa biết dữ liệu bị thay đổi ở bước nào.

## 6. Phân biệt dữ liệu lỗi và ký tự không thể mã hóa

Hai nhóm lỗi ở ranh giới byte:

| Trường hợp | Ví dụ |
| --- | --- |
| Dãy byte sai cấu trúc với charset được khai báo | `C3 28` không phải dãy UTF-8 hợp lệ |
| Nội dung không biểu diễn được trong charset đầu ra | Emoji khi đầu ra yêu cầu US-ASCII |

Có API thay dữ liệu lỗi bằng ký hiệu thay thế; có API báo lỗi. Khi cần tránh mất dữ liệu âm thầm, chọn chính sách rõ ràng.

Phần cuối chương trình cấu hình `CharsetDecoder` với `CodingErrorAction.REPORT` rồi giải mã dãy UTF-8 lỗi. [Tài liệu CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html)

Với chiều mã hóa, có thể dùng `CharsetEncoder` tương tự. Ví dụ sau minh họa trong phương thức, cần nhập `StandardCharsets`, `CodingErrorAction` và xử lý `CharacterCodingException`:

```java
StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(java.nio.CharBuffer.wrap(text));
```

Nếu `text` chứa emoji, mã hóa sang US-ASCII sẽ bị từ chối theo chính sách này. Đừng chọn một charset không đủ khả năng biểu diễn rồi xem ký hiệu thay thế là kết quả chấp nhận được, trừ khi đó chính là yêu cầu dữ liệu.

Một `String` có surrogate rời cũng có thể gây lỗi khi mã hóa nghiêm ngặt. Khả năng lưu được các đơn vị mã trong Java không đồng nghĩa chúng tạo thành dữ liệu Unicode hợp lệ để xuất ra.

## 7. UTF-16, BOM và charset mặc định

BOM là dấu có thể cung cấp thông tin nhận diện hoặc thứ tự byte tùy mã hóa. Trong Java, `UTF_16` và `UTF_16LE`/`UTF_16BE` là những lựa chọn có hợp đồng khác nhau; không nên tráo đổi chỉ vì tên cùng chứa “UTF-16”.

Trong ví dụ, chọn `UTF_16LE` để thứ tự byte rõ ràng và dãy byte không có BOM. Nếu định dạng trao đổi yêu cầu BOM, hãy thực hiện đúng hợp đồng đó và kiểm tra byte đầu tệp.

Không mặc định mọi API đọc văn bản đều dùng cùng một charset. Chẳng hạn, các overload `Files.readString`/`writeString` không truyền charset dùng UTF-8, còn một số API khác dùng charset mặc định theo hợp đồng riêng. Khi dữ liệu cần trao đổi ổn định, chỉ định charset rõ ràng giúp ý định dễ kiểm tra.

Charset của **tệp mã nguồn Java**, được nêu qua `javac -encoding UTF-8`, là một ranh giới khác: nó hướng dẫn trình biên dịch đọc mã nguồn. Nó không quyết định charset của các tệp ứng dụng ghi bằng `Files.writeString`.

Tương tự, cấu hình terminal ảnh hưởng cách stdout được hiển thị, không tự thay đổi lựa chọn charset của một lệnh ghi tệp đã chỉ định rõ.

## 8. Các lỗi thiết kế thường gặp

| Giả định | Cách xử lý đúng |
| --- | --- |
| Chuỗi Java dùng UTF-16 nên tệp phải UTF-16 | Chọn charset theo định dạng trao đổi |
| `length()` là số byte trên đĩa | Đếm byte sau mã hóa hoặc đo tệp |
| `String` nhớ charset từ lúc đọc | Giữ charset riêng nếu ứng dụng cần |
| Tệp đọc thành công nghĩa là đúng charset | Kiểm tra hợp đồng và nội dung đại diện |
| UTF-8 ở bước ghi sửa được chuỗi đã giải mã sai | Tìm nguyên nhân ở ranh giới byte trước đó |
| Mọi `String` luôn là `char[]` và hai byte mỗi ký tự | Tách API khỏi chi tiết lưu trữ JVM |
| Đổi đuôi tệp làm đổi mã hóa | Đọc rồi ghi lại bằng charset đích phù hợp |

Quy trình chuyển mã đúng là **giải mã nguồn bằng charset nguồn → xử lý String → mã hóa đích bằng charset đích**. Nếu nguồn và đích đều biểu diễn đầy đủ nội dung và chính sách lỗi được xử lý đúng, việc đổi mã hóa không cần làm thay đổi các điểm mã.

## 9. Tự kiểm tra

1. Vì sao chuỗi trong bài dài 4 theo `length()` nhưng tệp UTF-8 dài 7 byte?
2. Đọc tệp UTF-8 thành `String` có biến tệp gốc thành UTF-16 không?
3. Vì sao dùng ISO-8859-1 để đọc byte UTF-8 có thể không ném lỗi?
4. `javac -encoding UTF-8` có buộc chương trình ghi mọi tệp bằng UTF-8 không?

Đối chiếu:

1. Hai phép đo dùng đơn vị khác nhau; UTF-8 và UTF-16 có quy tắc biểu diễn riêng.
2. Không; thao tác đọc chỉ tạo nội dung trong chương trình, không viết lại tệp.
3. Một charset khác có thể diễn giải được các byte ấy nhưng tạo nội dung khác ý định.
4. Không; đó là charset của mã nguồn ở bước biên dịch, độc lập với charset tại ranh giới I/O khi chạy.
