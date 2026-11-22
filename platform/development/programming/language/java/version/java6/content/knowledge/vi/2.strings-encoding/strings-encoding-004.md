# String.getBytes với Charset tường minh

## 1. Từ chuỗi sang byte cần một quy ước

`String` là dữ liệu ký tự trong Java. Tệp, gói tin và nhiều giao thức lại làm việc với byte. Muốn chuyển từ chuỗi sang byte, phải chọn cách biểu diễn ký tự thành các giá trị byte — đó là vai trò của **bộ mã ký tự (`Charset`)**.

```text
String --mã hóa theo Charset--> byte[]
byte[] --giải mã theo Charset--> String
```

Hai phía phải thống nhất charset theo hợp đồng dữ liệu. Dùng cùng một chuỗi nhưng charset khác có thể tạo dãy byte khác; dùng đúng byte nhưng giải mã sai charset cũng có thể tạo nội dung sai.

Ở đây, “mã hóa” là chuyển biểu diễn ký tự, không phải mã hóa bảo mật. `getBytes` không che giấu nội dung, không băm và không tạo Base64.

Bài sử dụng Java 17+ để minh họa cách dùng còn áp dụng hiện nay. Overload nhận `Charset` có từ Java 6; `StandardCharsets` có từ Java 7 và là cách thuận tiện trên Java hiện đại.

## 2. Dùng overload nhận Charset

Ví dụ ở nơi đã có biến `String text`:

```java
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

Điều này nói rõ dữ liệu đầu ra dùng UTF-8. Bên nhận tạo lại chuỗi bằng cùng quy ước:

```java
String restored = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
```

`getBytes(Charset)` trả về một mảng byte mới; nó không thay đổi nội dung `String`. Nếu `text` là `null`, lời gọi instance ném `NullPointerException`. Truyền một `Charset` bằng `null` cũng không có nghĩa “dùng mặc định”.

Các hằng như `StandardCharsets.UTF_8`, `US_ASCII` hoặc `ISO_8859_1` tránh phải viết tên charset bằng chuỗi ở mọi nơi. Những charset chuẩn này được nền tảng Java bảo đảm hỗ trợ. Xem [StandardCharsets](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html).

Không cần bắt `UnsupportedEncodingException` cho lời gọi nhận `Charset`. Nếu tên charset đến từ cấu hình bên ngoài, phải xác thực nó bằng API tra cứu phù hợp và xử lý tên không hợp lệ/không được hỗ trợ ở biên cấu hình; đừng âm thầm chuyển sang charset khác.

## 3. Vì sao vẫn nên ghi rõ charset?

Lời gọi không tham số:

```java
byte[] implicit = text.getBytes();
```

dùng charset mặc định của JVM. Java hiện đại mặc định UTF-8, nhưng cơ chế thay đổi theo cách triển khai và môi trường cần được đối chiếu với JDK thực tế.

Tường minh vẫn có giá trị ngay cả khi mặc định cũng là UTF-8:

- Hợp đồng tệp/giao thức được nhìn thấy ngay trong mã.
- Không phụ thuộc một cấu hình mặc định ở nơi khác.
- Đọc lại hoặc tích hợp với hệ thống khác có cùng quy ước rõ ràng.
- Người sửa mã không phải suy luận từ máy hoặc phiên bản JDK.

Không nói rằng `getBytes()` luôn dùng một charset cũ đặc thù Windows, cũng không nói mọi nơi trong Java đều dùng cùng charset vì JVM mặc định UTF-8. Đó là những khẳng định quá rộng. Xem [Charset mặc định](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html#defaultCharset()).

Lựa chọn charset phải theo định dạng/giao thức. UTF-8 thường phù hợp cho văn bản Unicode, nhưng nếu đang giao tiếp với một định dạng yêu cầu charset cụ thể thì cần tuân thủ yêu cầu đó, không tự đổi vì sở thích của một bên.

## 4. Số byte không bằng độ dài String

Trong API Java, `String.length()` đếm đơn vị mã UTF-16, không phải số byte UTF-8 và cũng không nhất thiết là số ký tự mà người dùng nhìn thấy.

Xét chuỗi có nội dung `Aé😀`:

| Thành phần | Code point | Số đơn vị UTF-16 | Byte UTF-8 |
| --- | --- | --- | --- |
| `A` | U+0041 | 1 | `41` |
| `é` | U+00E9 | 1 | `C3 A9` |
| `😀` | U+1F600 | 2 | `F0 9F 98 80` |

Cả chuỗi có 4 đơn vị UTF-16, 3 code point và 7 byte UTF-8.

Vì vậy:

- Không cấp phát bộ đệm byte chỉ theo `text.length()` rồi giả định luôn đủ.
- Nếu giao thức yêu cầu độ dài payload theo byte, đo `bytes.length` của nội dung thực sự gửi.
- Không cắt tùy ý một dãy UTF-8 giữa các byte của cùng một ký tự.
- Không ép từng `char` sang `byte` để thay thế một encoder.

Biểu diễn lưu trữ nội bộ mà JVM tối ưu cho `String` không thay đổi hợp đồng `length()` hoặc quy tắc charset đầu ra. Không coi `getBytes(UTF_8)` là thao tác lấy nguyên bộ nhớ bên trong đối tượng.

## 5. Chọn đúng charset chưa đủ nếu dữ liệu không biểu diễn được

UTF-8 biểu diễn được các ký tự Unicode hợp lệ. US-ASCII chỉ biểu diễn một tập hẹp hơn, nên các ký tự như `é` hoặc emoji không thể mã hóa đúng thành ASCII.

Điểm dễ bỏ sót: `String.getBytes(Charset)` thay thế đầu vào sai dạng hoặc không ánh xạ được bằng byte thay thế của charset. Nó không tự ném lỗi cho mọi trường hợp mất dữ liệu.

Ví dụ minh họa:

```java
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
```

Nếu `text` chứa ký tự ngoài ASCII, lời gọi vẫn có thể trả mảng byte, nhưng không còn biểu diễn nguyên nội dung ban đầu. Khi giải mã lại bằng ASCII, không thể phục hồi các ký tự đã bị thay thế.

Ngay cả `String` cũng có thể chứa surrogate đơn lẻ không hợp lệ, ví dụ một high surrogate không có low surrogate đi cùng. Khi cần phát hiện các trường hợp này, không chỉ chọn UTF-8 rồi coi mọi dữ liệu đầu vào đều hợp lệ.

Hợp đồng thay thế lỗi xem [String.getBytes(Charset)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#getBytes(java.nio.charset.Charset)).

### Khi nào cần CharsetEncoder?

Nếu dữ liệu phải được bảo toàn hoặc yêu cầu từ chối đầu vào không hợp lệ, dùng `CharsetEncoder` với chính sách báo lỗi:

```java
var encoder = java.nio.charset.StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);
```

Đây là đoạn tạo encoder, chưa phải chương trình độc lập. `MalformedInput` nói về dữ liệu ký tự sai dạng; `UnmappableCharacter` nói về ký tự hợp lệ nhưng charset đích không biểu diễn được.

Encoder là đối tượng có trạng thái, không được mặc nhiên dùng chung đồng thời giữa nhiều luồng. `Charset` có thể dùng chung, còn encoder cần được quản lý phù hợp. Xem [CharsetEncoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html).

## 6. Ví dụ đầy đủ: byte, round-trip và lỗi mã hóa

Tệp `ExplicitCharsetDemo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class ExplicitCharsetDemo {
    public static void main(String[] args) {
        String text = "A\u00E9\uD83D\uDE00";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("hex="
                + HexFormat.ofDelimiter(" ").withUpperCase().formatHex(utf8));
        System.out.println("utf8RoundTrip="
                + text.equals(new String(utf8, StandardCharsets.UTF_8)));
        System.out.println("wrongCharsetRoundTrip="
                + text.equals(new String(utf8, StandardCharsets.ISO_8859_1)));

        byte[] ascii = text.getBytes(StandardCharsets.US_ASCII);
        System.out.println("asciiRoundTrip="
                + text.equals(new String(ascii, StandardCharsets.US_ASCII)));

        reportStrict("asciiStrict", text, StandardCharsets.US_ASCII);
        reportStrict("malformedStrict", "\uD800", StandardCharsets.UTF_8);
    }

    private static void reportStrict(String label, String text, Charset charset) {
        try {
            charset.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(text));
            System.out.println(label + "=OK");
        } catch (CharacterCodingException failure) {
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ExplicitCharsetDemo.java
java ExplicitCharsetDemo
```

Stdout:

```text
utf16Units=4
codePoints=3
utf8Bytes=7
hex=41 C3 A9 F0 9F 98 80
utf8RoundTrip=true
wrongCharsetRoundTrip=false
asciiRoundTrip=false
asciiStrict=UnmappableCharacterException
malformedStrict=MalformedInputException
```

Chuỗi được viết bằng Unicode escape để không phụ thuộc cách trình soạn thảo lưu các ký tự `é` và emoji. Nội dung runtime vẫn là `Aé😀`.

Giải thích từng nhóm:

1. **Kích thước:** 4 đơn vị UTF-16, 3 code point nhưng 7 byte UTF-8.
2. **Cùng charset:** mã hóa và giải mã UTF-8 khôi phục đúng chuỗi hợp lệ ban đầu.
3. **Sai charset:** đọc byte UTF-8 như ISO-8859-1 tạo nội dung khác; một phép giải mã không ném ngoại lệ vẫn có thể sai hợp đồng.
4. **Mất dữ liệu:** mã hóa bằng ASCII qua `getBytes(Charset)` không giữ được chuỗi ban đầu.
5. **Báo lỗi nghiêm ngặt:** encoder ASCII từ chối ký tự không ánh xạ được; encoder UTF-8 từ chối surrogate đơn lẻ.

`HexFormat` chỉ giúp hiển thị byte bằng số hex, không tham gia mã hóa ký tự. Chương trình chỉ in thông tin ASCII/hex để việc kiểm chứng stdout không phụ thuộc khả năng hiển thị emoji của terminal.

## 7. Áp dụng ở biên tệp và mạng

### Khi có sẵn String và cần byte

```java
byte[] payload = message.getBytes(java.nio.charset.StandardCharsets.UTF_8);
output.write(payload);
```

Đoạn mã minh họa giả định đã có `String message` và một `OutputStream output`. Nó không tự mở/đóng luồng. Phạm vi gọi phải xác định ai sở hữu luồng, khi nào flush/đóng và cách xử lý lỗi I/O.

Nếu giao thức có trường charset, giá trị khai báo phải khớp với byte thực tế. `getBytes(UTF_8)` không tự thêm HTTP header hoặc metadata charset vào một định dạng bất kỳ.

### Khi ghi văn bản lớn

`getBytes` tạo mảng chứa toàn bộ kết quả. Với văn bản rất lớn hoặc dữ liệu đến theo từng phần, có thể cần cơ chế ghi/encode theo luồng thay vì tạo thêm một mảng lớn cho toàn nội dung.

Một `Writer` hoặc encoder cũng cần charset và chính sách lỗi phù hợp; chuyển sang API khác không tự loại bỏ quyết định này. Khi dùng encoder tăng dần, phải tôn trọng trạng thái và ranh giới đầu vào, không mã hóa từng khối tách rời một cách tùy ý.

### Khi dữ liệu thực chất là nhị phân

Không biến ảnh, ZIP hoặc byte bất kỳ thành `String` bằng UTF-8 chỉ để chứa nó, rồi mong `getBytes(UTF_8)` lấy lại nguyên byte. Dữ liệu nhị phân có thể không phải chuỗi UTF-8 hợp lệ và có thể bị thay thế trong quá trình giải mã.

Giữ dữ liệu nhị phân dưới dạng byte; nếu cần biểu diễn văn bản cho nó thì chọn một định dạng phù hợp như Base64 theo hợp đồng truyền nhận. Charset và Base64 giải quyết hai vấn đề khác nhau.

## 8. Lỗi thường gặp và dấu hiệu nhận biết

| Lỗi | Hậu quả/cách kiểm tra |
| --- | --- |
| Mã hóa UTF-8 nhưng giải mã charset khác | Nội dung sai dù các bước đều chạy xong; đối chiếu byte hex và charset hai phía |
| Dùng `text.length()` làm độ dài byte | Sai khi có ký tự nhiều byte; tính từ payload đã mã hóa |
| Dùng ASCII cho văn bản cần giữ dấu/emoji | Có thể thay thế ký tự; dùng encoder báo lỗi khi không được phép mất dữ liệu |
| Gọi `bytes.toString()` để đọc nội dung | Không giải mã mảng byte; dùng `new String(bytes, charset)` cho văn bản |
| Gọi `getBytes` trên null | `NullPointerException`; xác định chính sách thiếu dữ liệu trước |
| “Sửa lỗi font” bằng cách encode/decode qua nhiều charset đoán mò | Có thể làm hỏng thêm dữ liệu; tìm chính xác bước dùng sai charset |
| Cho rằng charset tường minh tự chuẩn hóa Unicode | Các chuỗi code point khác nhau vẫn có thể tạo byte khác dù nhìn giống nhau |

Nếu byte đã mất thông tin do thay thế, đổi sang UTF-8 ở bước cuối không tự phục hồi dữ liệu gốc. Cần sửa tại biên nơi phép chuyển đổi sai xảy ra và đọc lại dữ liệu nguồn còn nguyên nếu có.

Một phép round-trip thành công là bằng chứng hữu ích cho chuỗi thử với charset đã chọn; nó không tự chứng minh mọi dữ liệu tương lai, mọi dạng Unicode hoặc mọi phía giao tiếp đều tuân thủ hợp đồng.

## 9. Tự thực hành

1. Đổi chuỗi thành `"ABC"`; dự đoán `length()` và số byte UTF-8 rồi chạy xác nhận.
2. Giữ chuỗi có dấu/emoji, đổi charset đích thành ASCII và giải thích vì sao `getBytes` vẫn có thể trả kết quả.
3. Với một giao thức có độ dài payload, nêu nên dùng `String.length()` hay `byte[].length` và ở thời điểm nào.
4. Phân biệt ba lỗi: dùng sai charset, ký tự không biểu diễn được và đầu vào surrogate sai dạng.
5. Chọn chính sách lỗi cho xuất dữ liệu cần bảo toàn: thay thế, bỏ qua hay báo lỗi; giải thích quyết định.
