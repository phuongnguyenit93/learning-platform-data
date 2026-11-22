# UTF-16 của mô hình String khác với charset của tệp trong Java

Khi học Java, người ta thường nói “`String` dùng UTF-16”, nhưng tệp văn bản lại có thể mang charset UTF-8, UTF-16LE hoặc một charset khác. **Hai phát biểu này mô tả hai tầng khác nhau**: mô hình thao tác với ký tự trong Java và cách biểu diễn văn bản thành **byte** khi lưu ra tệp hay truyền qua mạng. Nhầm lẫn hai tầng dẫn đến lỗi đếm độ dài, cắt chuỗi, đọc sai tiếng Việt, lỗi ký tự thay thế và chọn sai charset.

## 1. Phân biệt Unicode, mô hình String và charset

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Unicode code point | Giá trị định danh một phần tử ký tự Unicode | `U+0041` là A, `U+00E9` là é, `U+1F600` là 😀 |
| UTF-16 code unit | Đơn vị mã 16 bit; một code point có thể chiếm một hoặc hai đơn vị | Emoji 😀 cần cặp surrogate `D83D DE00` |
| Mô hình `String` Java | Chỉ số và các API như `length()`, `charAt()` được định nghĩa dựa trên UTF-16 code unit | `"😀".length() == 2` |
| Charset của tệp | Quy tắc mã hóa/giải mã văn bản thành/từ các byte | UTF-8, UTF-16LE, UTF-16BE, Windows-1252 |

**Mô hình `String`** là cách API Java nhìn nhận chuỗi. Một `char` là một đơn vị mã UTF-16; `length()` tính số đơn vị mã; chỉ số `charAt()` và `substring()` cũng tính theo đơn vị mã này. **Charset của tệp** là lựa chọn tại điểm chuyển đổi từ chuỗi sang byte (encode) hoặc từ byte sang chuỗi (decode).

Vì thế, cùng một đối tượng `String` có thể được lưu thành tệp UTF-8 hoặc UTF-16LE. Khi đọc hai tệp bằng charset tương ứng, ta có thể khôi phục **cùng nội dung `String`**. Charset từng dùng để lưu tệp không trở thành thuộc tính cố định của `String`.

### “String dùng UTF-16” không có nghĩa “bộ nhớ luôn là char[]”

Đừng suy diễn rằng mọi JVM luôn giữ bên trong đối tượng `String` một mảng gồm hai byte cho mỗi `char`. OpenJDK từ Java 9 có tối ưu **Compact Strings**, cho phép biểu diễn gọn hơn đối với các chuỗi phù hợp Latin-1. Chi tiết bố trí bộ nhớ nội bộ tùy triển khai, còn các hành vi quan sát qua `String.length()`, `charAt()`, `codePointCount()` vẫn theo hợp đồng API liên quan UTF-16. Đặc biệt, byte nội bộ của `String` **không phải** byte ghi ra tệp.

## 2. Minh họa: một chuỗi nhưng ba cách đếm

Xét chuỗi:

~~~java
String text = "Aé😀";
~~~

| Ký tự | Unicode code point | UTF-16 code unit | Byte UTF-8 |
| --- | --- | --- | --- |
| A | `U+0041` | `0041` (1 unit) | `41` (1 byte) |
| é | `U+00E9` | `00E9` (1 unit) | `C3 A9` (2 byte) |
| 😀 | `U+1F600` | `D83D DE00` (2 unit) | `F0 9F 98 80` (4 byte) |
| **Tổng** | **3 code point** | **4 UTF-16 unit** | **7 byte UTF-8** |

Do đó:

- `text.length()` bằng **4**, vì UTF-16 cần bốn đơn vị mã.
- `text.codePointCount(0, text.length())` bằng **3**.
- `Character.isHighSurrogate(text.charAt(2))` bằng `true`: vị trí 2 là nửa đầu của cặp surrogate của emoji.
- `text.getBytes(StandardCharsets.UTF_8).length` bằng **7**.
- `text.getBytes(StandardCharsets.UTF_16LE).length` bằng **8** (4 đơn vị nhân 2 byte).

**Đừng đồng nhất code point với ký tự người đọc thấy.** Một cụm ký tự hiển thị có thể bao gồm nhiều code point, ví dụ chữ cái cộng dấu kết hợp hoặc emoji ghép. Với dữ liệu Unicode, đơn vị mã UTF-16, code point và cụm ký tự hiển thị (*grapheme cluster*) là ba khái niệm riêng.

## 3. Luồng chuyển đổi từ String sang tệp và ngược lại

~~~text
Nội dung Unicode, ví dụ "Aé😀"
               |
               v
     Java String (API UTF-16)
     length() / charAt() / substring()
               |
               | ENCODE: getBytes(charset)
               | hoặc Files.writeString(path, text, charset)
               v
     Dãy byte theo charset đã chọn
     UTF-8   : 41 C3 A9 F0 9F 98 80
     UTF-16LE: 41 00 E9 00 3D D8 00 DE
               |
               v
         Tệp trên ổ đĩa
               |
               | DECODE: new String(bytes, charset)
               | hoặc Files.readString(path, charset)
               v
     Java String (API vẫn theo UTF-16)
~~~

Encoding và decoding là **các thao tác chuyển đổi dữ liệu**, không phải thao tác thay đổi “loại” của một `String`. Byte được tạo từ UTF-8 và UTF-16LE có thể khác hoàn toàn, nhưng khi giải mã **đúng charset và dữ liệu hợp lệ** sẽ thu lại cùng chuỗi.

Đuôi tệp `.txt` không tự bảo đảm charset. Cần biết charset từ đặc tả định dạng, giao thức, metadata hoặc thỏa thuận với hệ thống tạo dữ liệu. Không thể suy ra một charset luôn chính xác cho mọi dãy byte.

## 4. Ví dụ Java 17+ chạy độc lập: kiểm tra UTF-16 và byte thực tế

Tạo tệp **StringCharsetDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

public class StringCharsetDemo {
    public static void main(String[] args) throws Exception {
        String text = "Aé😀";

        System.out.println("UTF-16 units = " + text.length());
        System.out.println("Unicode code points = "
                + text.codePointCount(0, text.length()));
        System.out.println("high surrogate at index 2 = "
                + Character.isHighSurrogate(text.charAt(2)));

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] utf16le = text.getBytes(StandardCharsets.UTF_16LE);
        byte[] utf16 = text.getBytes(StandardCharsets.UTF_16);
        HexFormat hex = HexFormat.ofDelimiter(" ").withUpperCase();

        System.out.println("UTF-8 bytes = " + utf8.length);
        System.out.println("UTF-8 hex = " + hex.formatHex(utf8));
        System.out.println("UTF-16LE bytes = " + utf16le.length);
        System.out.println("UTF-16LE hex = " + hex.formatHex(utf16le));
        System.out.println("UTF-16 bytes = " + utf16.length);
        System.out.println("UTF-16 hex = " + hex.formatHex(utf16));

        String decoded = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("UTF-8 decode equals original = "
                + text.equals(decoded));

        Path tempFile = Files.createTempFile("string-charset-", ".txt");
        try {
            Files.writeString(tempFile, text, StandardCharsets.UTF_8);
            String loaded = Files.readString(tempFile, StandardCharsets.UTF_8);

            System.out.println("file round-trip = " + text.equals(loaded));
            System.out.println("file bytes equal UTF-8 = "
                    + Arrays.equals(Files.readAllBytes(tempFile), utf8));
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên và chạy:

~~~bash
javac -encoding UTF-8 StringCharsetDemo.java
java StringCharsetDemo
~~~

**Kết quả chuẩn:**

~~~text
UTF-16 units = 4
Unicode code points = 3
high surrogate at index 2 = true
UTF-8 bytes = 7
UTF-8 hex = 41 C3 A9 F0 9F 98 80
UTF-16LE bytes = 8
UTF-16LE hex = 41 00 E9 00 3D D8 00 DE
UTF-16 bytes = 10
UTF-16 hex = FE FF 00 41 00 E9 D8 3D DE 00
UTF-8 decode equals original = true
file round-trip = true
file bytes equal UTF-8 = true
~~~

Giải thích từng kết quả:

1. **4 UTF-16 units** phản ánh mô hình API của `String`, không phải 4 byte trong tệp.
2. **7 byte UTF-8** và **8 byte UTF-16LE** đều mã hóa cùng ba code point.
3. Với `StandardCharsets.UTF_16`, bộ mã hóa Java ghi BOM `FE FF`, sau đó ghi UTF-16 big-endian: `00 41 00 E9 D8 3D DE 00`. Do đó tổng cộng **10 byte**. BOM nằm trong **đầu ra byte**, không phải hai byte ẩn mà mọi `String` đều có.
4. `new String(utf8, StandardCharsets.UTF_8)` giải mã về văn bản, nên `equals()` trả về `true`.
5. `Files.writeString` lưu **byte UTF-8** theo charset được truyền; chương trình đọc tệp bằng UTF-8, đối chiếu nội dung và cả byte thực tế, rồi xóa tệp tạm trong `finally`.

Cờ `javac -encoding UTF-8` chỉ báo cho trình biên dịch rằng **tệp mã nguồn Java** được lưu bằng UTF-8. Nó không đặt charset tự động cho mọi tệp dữ liệu do chương trình tạo; charset tệp trong ví dụ đến từ đối số `StandardCharsets.UTF_8` của API I/O.

## 5. UTF-16 của API và charset UTF-16 của tệp khác nhau ở đâu?

| Charset | Khi xuất dữ liệu thành byte | Chi tiết cần chú ý |
| --- | --- | --- |
| UTF-8 | Mỗi code point thường dùng 1–4 byte | Không có byte order của đơn vị 16-bit |
| UTF-16LE | Mỗi UTF-16 code unit dùng 2 byte, byte thấp trước | `U+0041` thành `41 00`; encoder Java không tự ghi BOM |
| UTF-16BE | Mỗi UTF-16 code unit dùng 2 byte, byte cao trước | `U+0041` thành `00 41`; encoder Java không tự ghi BOM |
| UTF-16 (`StandardCharsets.UTF_16`) | Có quy ước dùng BOM để xác định thứ tự byte lúc giải mã | Java mã hóa mặc định có BOM `FE FF` và nội dung big-endian; decoder dùng big-endian khi thiếu BOM |

**BOM** (*byte order mark*) là dấu byte dùng để nhận biết thứ tự byte ở một số cách mã hóa. Chẳng hạn, `FE FF` biểu thị big-endian trong UTF-16 và `FF FE` biểu thị little-endian. Điều đó không có nghĩa mọi tệp UTF-8 hay UTF-16LE đều phải có BOM. Cần tuân thủ quy ước của nguồn dữ liệu và API sử dụng.

Ví dụ chữ A được biểu diễn khác nhau:

- `UTF-8`: `41`.
- `UTF-16LE`: `41 00`.
- `UTF-16BE`: `00 41`.
- `UTF-16` do encoder Java ghi: `FE FF 00 41` (bao gồm BOM).

Cả bốn trường hợp đều có thể giải mã thành `String "A"` với `length() == 1`. Charset UTF-16 dùng để **lưu/đọc byte** có thêm mối quan tâm thứ tự byte, khác với hợp đồng `charAt()`, `length()` khi thao tác trên `String`.

## 6. Đọc và ghi tệp với charset tường minh

Ví dụ dùng `Files.writeString()` và `Files.readString()`, có từ Java 11 trở lên. Tạo tệp **Utf8FileExample.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes-utf8.txt");

        String original = "Xin chào Java 😀";
        Files.writeString(path, original, StandardCharsets.UTF_8);

        String restored = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println(original.equals(restored));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 Utf8FileExample.java
java Utf8FileExample
~~~

Stdout:

~~~text
true
~~~

Chương trình tạo/ghi đè `notes-utf8.txt` tại thư mục chạy. Khi dùng trong ứng dụng thật cần kiểm soát đường dẫn, quyền truy cập và chính sách ghi đè. Nội dung lúc còn ở `String original` vẫn có ngữ nghĩa UTF-16 theo API Java; nó **được mã hóa thành UTF-8 tại lời gọi ghi tệp**.

Với tệp đã biết mang UTF-16LE, đoạn mã sau phải đọc theo UTF-16LE:

~~~java
String text = Files.readString(
        Path.of("external-utf16le.txt"),
        StandardCharsets.UTF_16LE);
~~~

Đây chỉ là **đoạn code minh họa** trong một phương thức có xử lý hoặc khai báo `IOException` và có import `Files`, `Path`, `StandardCharsets`. Chọn đúng charset theo dữ liệu thực tế của tệp. Khi đã giải mã, `text` là `String` Java bình thường.

**Lưu ý về mặc định:** Hai overload `Files.readString(path)` và `Files.writeString(path, text)` sử dụng UTF-8 theo hợp đồng API Java 11+. Nhưng các API khác như `FileReader`, `InputStreamReader`, `FileWriter` hoặc `String.getBytes()` có overload dùng **default charset** nếu không chỉ định. Từ JDK 18, JEP 400 chuẩn hóa UTF-8 làm default charset cho phần lớn trường hợp trong cấu hình chuẩn, song điều đó không đảm bảo mọi dữ liệu cũ hoặc dữ liệu do hệ thống khác cung cấp đều là UTF-8. Để kết nối ổn định, **truyền charset tường minh theo hợp đồng dữ liệu**.

## 7. Lỗi đọc sai charset: mojibake và ký tự thay thế

Giả sử tệp lưu chuỗi `café` dưới UTF-8. Chữ `é` được mã hóa thành `C3 A9`. Nếu áp dụng bộ giải mã Windows-1252 lên các byte này, người dùng có thể thấy `cafÃ©`. Hiện tượng này gọi là **mojibake**: byte được hiểu bằng quy tắc khác với charset đã dùng để tạo nó. Chuỗi Java thu được vẫn là `String` với ngữ nghĩa API UTF-16; **nội dung bị sai ngay ở bước giải mã**.

Có hai loại lỗi:

- Dữ liệu byte hợp lệ theo charset **sai**: bộ giải mã có thể tạo ra các ký tự khác, không ném lỗi.
- Byte không hợp lệ theo charset đang dùng: decoder có thể thay ký tự lỗi bằng `U+FFFD` (ký tự thay thế), hoặc báo ngoại lệ, tùy API và cấu hình.

Nếu cần phát hiện byte UTF-8 lỗi **thay vì thay thế âm thầm**, dùng `CharsetDecoder` và cấu hình `CodingErrorAction.REPORT`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

// Đoạn code đặt trong một phương thức Java:
byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
try {
    String decoded = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(invalidUtf8))
            .toString();
    System.out.println(decoded);
} catch (CharacterCodingException ex) {
    System.out.println("Invalid UTF-8");
}
~~~

Stdout của đoạn mã khi thực thi trong phương thức:

~~~text
Invalid UTF-8
~~~

Byte `C3` bắt đầu một chuỗi UTF-8 cần byte tiếp nối, nhưng `28` không phải byte tiếp nối hợp lệ. Cấu hình `REPORT` giúp phát hiện dữ liệu hỏng. Nếu dùng API tiện lợi `new String(bytes, StandardCharsets.UTF_8)`, các chuỗi byte lỗi thường được thay bằng ký tự thay thế theo hợp đồng constructor, vì vậy không nên coi việc không ném lỗi là bằng chứng dữ liệu gốc hợp lệ.

### Cắt chuỗi có thể phá surrogate pair

Đoạn mã sau chứng minh `substring()` cũng dùng chỉ số UTF-16:

~~~java
String s = "A😀B";
System.out.println(s.length()); // 4
System.out.println(s.substring(1, 3).equals("😀")); // true
System.out.println(s.substring(1, 2).length()); // 1, chi lay high surrogate
~~~

Đây là **đoạn code minh họa** đặt trong một phương thức. Cắt `[1, 3)` giữ cả hai đơn vị UTF-16 của emoji; cắt `[1, 2)` lấy một surrogate lẻ nên không còn emoji hoàn chỉnh. Nếu phạm vi cần thao tác theo code point, tham khảo `codePointCount()`, `offsetByCodePoints()` và `codePoints()`. Nếu yêu cầu không tách cụm ký tự người dùng nhìn thấy, cần thêm cơ chế phân đoạn theo *grapheme cluster*.

## 8. Lỗi phổ biến và cách sửa

| Nhầm lẫn hoặc thao tác sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| “`String` dùng UTF-16 nên tệp nhất định là UTF-16” | Chọn sai cách đọc/ghi byte | Chỉ định đúng charset khi I/O |
| Dùng `s.length()` làm số byte UTF-8 | Sai kích thước với dấu, emoji và nhiều ký tự khác | `s.getBytes(StandardCharsets.UTF_8).length` |
| Dùng `substring()` tùy tiện giữa surrogate pair | Tạo chuỗi có surrogate lẻ | Đặt ranh giới phù hợp với code point hoặc cụm hiển thị |
| Ghi UTF-8 nhưng đọc bằng UTF-16LE | Văn bản sai hoặc lỗi giải mã | Dùng charset tương ứng với byte gốc |
| Dùng `new String(bytes)` khi không biết default charset | Kết quả có thể khác giữa cấu hình/môi trường hoặc dữ liệu không đúng charset | `new String(bytes, expectedCharset)` |
| Tưởng `javac -encoding UTF-8` quyết định charset của tệp lúc chạy | Dữ liệu đầu ra có thể khác dự kiến | Charset mã nguồn và charset dữ liệu là hai quyết định riêng |
| Tưởng BOM bắt buộc cho mọi UTF-8/UTF-16LE | Ghi thêm/thiếu BOM so với giao thức | Tuân theo đặc tả định dạng và tên charset |
| Tin rằng đuôi `.txt` xác định charset | Giải mã sai tệp không có metadata | Lấy charset từ thỏa thuận hoặc định dạng |
| Tin rằng `char` luôn là một ký tự trọn vẹn | Cắt hỏng code point ngoài BMP | Dùng API code point khi thích hợp |
| Coi byte nội bộ của JVM là dữ liệu tệp | Phụ thuộc chi tiết triển khai | Chỉ dựa vào API encode/decode |

## 9. Quy trình kiểm tra khi gặp lỗi tiếng Việt hoặc emoji trong tệp

1. **Làm rõ nguồn byte:** tệp được tạo từ chương trình nào, có charset nào, có BOM hoặc metadata hay không?
2. **Kiểm tra đoạn đọc:** `Files.readString(path, charset)` hoặc `InputStreamReader(input, charset)` có dùng đúng charset nguồn không?
3. **Kiểm tra `String` sau khi decode:** so sánh code point, `equals()` và các giá trị mong đợi; đừng dùng `length()` như kích thước byte.
4. **Kiểm tra đoạn ghi:** `Files.writeString(path, content, charset)` hoặc `getBytes(charset)` có dùng charset mà hệ thống nhận yêu cầu không?
5. **Kiểm tra byte thật:** in hex hoặc đọc byte bằng `Files.readAllBytes()`, quan sát BOM và chuỗi byte UTF-8/UTF-16.
6. **Round-trip:** với mẫu có chữ ASCII, tiếng Việt có dấu, emoji, thử encode rồi decode với cùng charset; kiểm tra `original.equals(restored)`.
7. **Quy định cách báo lỗi:** với tệp quan trọng, quyết định việc dùng decoder báo lỗi nghiêm ngặt thay vì lặng lẽ thay ký tự hỏng.

## 10. Tự kiểm tra

**Câu 1.** `String s = "😀";` thì `s.length()` bằng mấy và lưu s dưới UTF-8 (không BOM) cần bao nhiêu byte?

**Đáp án:** `length() == 2` vì emoji dùng hai UTF-16 code unit; UTF-8 của emoji dùng **4 byte**, `F0 9F 98 80`.

**Câu 2.** Chuỗi `"Aé"` có hai Unicode code point. Số byte UTF-8 có bằng 2 không?

**Đáp án:** không. A chiếm 1 byte, é chiếm 2 byte; tổng cộng **3 byte**.

**Câu 3.** Sau khi `Files.writeString(path, s, StandardCharsets.UTF_8)`, biến `s` có đổi loại thành “String UTF-8” không?

**Đáp án:** không. Chỉ đầu ra byte được mã hóa theo UTF-8; API `String` vẫn làm việc với đơn vị UTF-16.

**Câu 4.** Tại sao bytes `FE FF 00 41` đọc qua charset UTF-16 cho ra chuỗi có nội dung A?

**Đáp án:** `FE FF` là BOM chỉ big-endian, còn `00 41` là UTF-16 code unit của A.

**Câu 5.** Đọc một tệp lưu bằng UTF-8 nhưng dùng `StandardCharsets.UTF_16LE` có đảm bảo khôi phục đúng không?

**Đáp án:** không; mã hóa và giải mã phải sử dụng cùng quy ước (hoặc các quy ước tương thích theo đặc tả). Kết quả sai charset có thể tạo ký tự sai hoặc bị coi là dữ liệu không hợp lệ.

## Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): quy ước UTF-16 trong API chuỗi, `length`, `charAt`, `getBytes`, `codePointCount`.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): tên và đặc tính charset chuẩn.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `writeString`, `readString`, `readAllBytes`.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): xử lý byte lỗi và `CodingErrorAction`.
- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254): tối ưu biểu diễn nội bộ `String`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định kể từ JDK 18.
