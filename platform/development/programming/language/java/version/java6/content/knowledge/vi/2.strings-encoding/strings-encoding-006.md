# Tránh phụ thuộc charset mặc định khi trao đổi dữ liệu

## 1. Charset là hợp đồng giữa các bên, không phải đặc điểm của máy gửi

Một chương trình xuất văn bản thành byte để gửi qua mạng hoặc lưu vào tệp. Chương trình khác nhận những byte đó rồi tạo lại ký tự. Hai bước phải tuân thủ cùng quy ước.

```text
bên gửi: String -> encoder -> byte
                            |
                       tệp/giao thức
                            |
bên nhận: String <- decoder <- byte
```

Nếu bên gửi dùng một charset và bên nhận tự chọn charset mặc định khác, đường truyền có thể giữ nguyên mọi byte nhưng nội dung vẫn sai. Đây là lỗi ở ranh giới chuyển đổi ký tự–byte, không nhất thiết là lỗi mạng hoặc font chữ.

Quy tắc thiết kế là: **chọn charset theo định dạng/giao thức và làm cho cả hai đầu thực hiện đúng hợp đồng đó**. Không lấy charset mặc định của máy gửi làm một thông tin mà máy nhận phải tự đoán.

Bài dùng các API hiện đại trên Java 17+, tập trung trao đổi dữ liệu còn áp dụng hiện nay.

## 2. Mặc định UTF-8 không làm hợp đồng dữ liệu trở nên thừa

Từ JDK 18, UTF-8 là charset mặc định cho các API Java SE dựa vào charset mặc định. Điều này giúp giảm khác biệt giữa nền tảng, nhưng vẫn cần biết chính xác API nào dùng mặc định và dữ liệu bên ngoài được tạo bằng gì.

Một triển khai có thể hỗ trợ lựa chọn tương thích như `-Dfile.encoding=COMPAT`; phần mềm ngoài Java cũng có thể dùng quy ước khác. Nâng JDK không tự chuyển các tệp đã tồn tại hoặc thay đổi giao thức của một đối tác. Xem [hướng dẫn về charset mặc định khi chuyển JDK](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html) và [Charset.defaultCharset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html#defaultCharset()).

Hai suy luận cần tránh:

- “Mọi Windows hiện nay đều dùng cùng một charset khác UTF-8.”
- “Đã chạy JDK mới thì mọi tệp, thư viện và đầu cuối chắc chắn hiểu UTF-8.”

Cả hai đều bỏ qua hợp đồng và môi trường thật. Việc đọc/ghi của một API cụ thể phải được xác định từ tài liệu của API đó.

## 3. Tìm các ranh giới chuyển đổi trong luồng dữ liệu

Trước khi sửa mã, vẽ đường đi ngắn của dữ liệu:

```text
nguồn văn bản -> xuất tệp -> tải lên -> đọc ở dịch vụ -> gửi thông điệp -> người nhận
```

Ở mỗi điểm có chuyển đổi giữa ký tự và byte, ghi lại:

| Điểm cần biết | Câu hỏi |
| --- | --- |
| Bên tạo byte | Gọi API nào, charset có được chỉ định không? |
| Định dạng | Đặc tả yêu cầu charset nào, metadata có thể hiện charset không? |
| Bên đọc byte | Decoder nào được dùng, có nhận thông tin charset đúng không? |
| Lỗi | Byte sai dạng hoặc ký tự không biểu diễn được sẽ bị báo lỗi hay thay thế? |
| Chuyển đổi trung gian | Có đọc thành String rồi ghi lại qua charset khác không? |
| Kiểm chứng | Có byte mẫu và nội dung mong đợi đủ ngoài ASCII không? |

Chỉ sửa một lời gọi `getBytes` chưa đủ nếu phía đọc vẫn dùng một decoder khác. Ngược lại, thay decoder ở cuối không phục hồi được dữ liệu đã bị thay bằng ký tự khác ở bước trước.

## 4. Viết mã có charset rõ ràng ở biên

### Mảng byte

Ví dụ minh họa, giả định đã có `String text` và `byte[] payload`:

```java
byte[] encoded = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
String decoded = new String(payload, java.nio.charset.StandardCharsets.UTF_8);
```

Không dùng cùng một charset tùy ý chỉ để hai dòng “khớp nhau”; charset còn phải khớp với hệ thống còn lại. Nếu hợp đồng yêu cầu UTF-8 thì cả hai dòng mới là cách hiện thực phù hợp.

### Luồng ký tự

Khi nhận một `InputStream` chứa văn bản UTF-8, tạo reader với charset đã thống nhất:

```java
var reader = new java.io.InputStreamReader(
        input, java.nio.charset.StandardCharsets.UTF_8);
```

Đây là đoạn mã ở nơi đã có biến `input`. Nó chưa thể hiện vòng đọc hoặc quản lý tài nguyên. Khi tự sở hữu luồng, phạm vi sử dụng cần đóng nó đúng lúc; nếu luồng do bên khác sở hữu, tuân thủ hợp đồng sở hữu thay vì tự ý đóng.

`InputStreamReader(input)` không chỉ định charset sẽ dùng charset mặc định. Còn constructor có `Charset` nêu rõ quy ước của dữ liệu. Xem [InputStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html).

### Tệp văn bản

Với tệp mà ứng dụng định nghĩa là UTF-8:

```java
java.nio.file.Files.writeString(
        path, text, java.nio.charset.StandardCharsets.UTF_8);
String loaded = java.nio.file.Files.readString(
        path, java.nio.charset.StandardCharsets.UTF_8);
```

Đoạn mã giả định `path` là `Path` và nằm trong nơi xử lý `IOException`. Lệnh ghi theo mặc định của API có thể tạo mới hoặc ghi đè tệp đã có; khi áp dụng thật cần chọn cách mở tệp phù hợp.

Không kết luận “không truyền charset tức dùng charset mặc định JVM” cho mọi API. Chẳng hạn `Files.readString(path)` và `Files.writeString(path, text)` quy định UTF-8 ngay trong hợp đồng. Dạng có tham số vẫn có thể được dùng để làm rõ quy ước ở một điểm trao đổi dữ liệu. Xem [Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html).

## 5. Thống nhất cả byte thực tế và thông tin mô tả

Có hai phần phải khớp:

1. **Nội dung byte:** encoder thực sự tạo dãy byte theo charset nào?
2. **Quy ước/metadata:** bên nhận được yêu cầu giải mã dãy byte đó bằng gì?

Chỉ đổi một nhãn metadata sang “UTF-8” không chuyển byte cũ thành UTF-8. Tương tự, gọi `getBytes(UTF_8)` không tự thêm thông tin charset vào mọi kiểu thông điệp.

Với HTTP, tệp CSV hoặc một định dạng khác, tuân thủ đúng quy tắc của media type/giao thức đang dùng. Không có một cách thêm `charset` chung cho mọi định dạng. Nếu định dạng có quy tắc cố định, dùng quy tắc đó thay vì tự thiết kế một biến thể.

Ngoài ra, ranh giới thông điệp và charset là hai vấn đề khác nhau. Gửi từng phần qua mạng không bảo đảm một lần đọc tương ứng với một chuỗi ký tự hoàn chỉnh. Khi đọc theo khối, reader/decoder phải giữ được trạng thái cần thiết; không tùy tiện tạo `new String(chunk, UTF_8)` cho từng khối nếu khối có thể cắt giữa một ký tự nhiều byte.

## 6. Thực nghiệm chạy được: byte đúng, decoder sai

Ví dụ dùng hai phía mô phỏng trong một chương trình: bên gửi tạo UTF-8; bên nhận thứ nhất dùng UTF-8, bên nhận thứ hai cố ý dùng ISO-8859-1.

Tệp `WireCharsetDemo.java`:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.stream.Collectors;

public final class WireCharsetDemo {
    public static void main(String[] args) {
        String original = "caf\u00E9";
        byte[] wire = original.getBytes(StandardCharsets.UTF_8);

        String correct = new String(wire, StandardCharsets.UTF_8);
        String wrong = new String(wire, StandardCharsets.ISO_8859_1);

        System.out.println("defaultCharset=" + Charset.defaultCharset().name());
        System.out.println("wireHex="
                + HexFormat.ofDelimiter(" ").withUpperCase().formatHex(wire));
        System.out.println("correctEquals=" + original.equals(correct));
        System.out.println("wrongEquals=" + original.equals(wrong));
        System.out.println("originalCodePoints=" + codePoints(original));
        System.out.println("wrongCodePoints=" + codePoints(wrong));
    }

    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(point -> String.format("U+%04X", point))
                .collect(Collectors.joining(" "));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 WireCharsetDemo.java
java WireCharsetDemo
```

Trên Zulu OpenJDK 24.0.2 ở môi trường thử, stdout:

```text
defaultCharset=UTF-8
wireHex=63 61 66 C3 A9
correctEquals=true
wrongEquals=false
originalCodePoints=U+0063 U+0061 U+0066 U+00E9
wrongCodePoints=U+0063 U+0061 U+0066 U+00C3 U+00A9
```

Chuỗi gốc là `café`. Ba chữ đầu thuộc ASCII nên cùng byte trong hai charset thử. Ký tự `é` trở thành hai byte `C3 A9` trong UTF-8. Khi đọc hai byte này như ISO-8859-1, bên nhận tạo hai code point khác: U+00C3 và U+00A9.

Đây là lý do dữ liệu chỉ có `ABC` có thể che giấu một lỗi charset: một số charset cho cùng byte ở vùng ký tự ASCII, nhưng khác nhau khi có dấu hoặc ký tự khác.

Lệnh không in trực tiếp chuỗi sai ra terminal mà in code point, giúp phân biệt nội dung ký tự thực sự với khả năng hiển thị của console.

### Khảo sát mặc định mà không đổi hợp đồng dữ liệu

Trên JDK 18 trở lên hỗ trợ các lựa chọn tương ứng:

```shell
java -Dfile.encoding=UTF-8 WireCharsetDemo
java -Dfile.encoding=COMPAT WireCharsetDemo
```

Các lựa chọn này dùng cho phép khảo sát, không phải yêu cầu khởi chạy của chương trình. Vì chương trình đã chỉ định UTF-8 ở phía trao đổi đúng, dãy byte và phép so sánh đúng không dựa vào `Charset.defaultCharset()`.

Trên môi trường thử nêu trên, cả hai lệnh đều in `defaultCharset=UTF-8` và cùng các dòng còn lại. Không suy ra rằng `COMPAT` luôn khác UTF-8, cũng không coi phép thử này là đã kiểm tra trên hai hệ điều hành có charset khác nhau. Để kiểm chứng nhiều môi trường thực, cần chạy trong chính các môi trường đó.

ISO-8859-1 trong nhánh lỗi là lựa chọn **cố ý sai hợp đồng** để tái hiện vấn đề có kiểm soát; không phải đề xuất đổi mặc định hệ thống về charset này.

## 7. Sai charset có thể không tạo ngoại lệ

Một decoder có thể chấp nhận toàn bộ dãy byte nhưng hiểu chúng thành ký tự khác. Nhánh ISO-8859-1 trong ví dụ chứng minh điều đó: mã chạy xong, nhưng `wrongEquals=false`.

Cũng có các tình huống byte không hợp lệ với charset đã chọn. Một số API tiện dụng thay thế dữ liệu lỗi; nếu yêu cầu bảo toàn nghiêm ngặt, dùng decoder với chính sách báo lỗi:

```java
var decoder = java.nio.charset.StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);
String text = decoder.decode(java.nio.ByteBuffer.wrap(payload)).toString();
```

Đây là đoạn mã cần đặt ở nơi đã có `payload` và xử lý `CharacterCodingException`. Decoder có trạng thái; không tự dùng chung đồng thời giữa nhiều luồng.

Báo lỗi nghiêm ngặt giúp phát hiện byte không hợp lệ đối với UTF-8, nhưng không chứng minh charset được chọn đúng với ý định nguồn. Một dãy byte có thể hợp lệ dưới nhiều quy ước mà tạo ý nghĩa khác nhau. Xem [CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html).

Vì thế, cần cả hợp đồng nguồn dữ liệu và chính sách lỗi, không chỉ một decoder không ném ngoại lệ.

## 8. Cách kiểm chứng một luồng trao đổi thật

Một bộ dữ liệu thử nên có:

- Văn bản ASCII để kiểm tra đường cơ bản.
- Tiếng Việt có dấu.
- Ký tự bổ sung như emoji.
- Dữ liệu rỗng và dữ liệu nhiều dòng nếu định dạng cho phép.
- Byte sai dạng để kiểm tra chính sách từ chối/thay thế.
- Kích thước đủ để đi qua nhiều lần đọc nếu xử lý theo luồng.

Với mỗi ca, kiểm tra cả nội dung và byte:

1. Ghi nhận chuỗi đầu vào mong đợi.
2. Chụp một mẫu byte ngay sau encoder ở bên gửi.
3. Xác nhận quy ước charset/metadata được chuyển đúng.
4. Đối chiếu byte bên nhận trước decoder.
5. So sánh chuỗi sau decoder bằng nội dung/code point cần thiết, không chỉ nhìn ảnh chụp màn hình.

Nếu byte bên gửi và bên nhận giống nhau nhưng chuỗi khác, tập trung điều tra decoder và các bước xử lý sau đó. Nếu byte đã khác, kiểm tra các bước chuyển mã hoặc xử lý trung gian.

Không ghi toàn bộ dữ liệu nhạy cảm vào log chỉ để chẩn đoán charset. Dùng mẫu thử kiểm soát được, độ dài và byte mẫu cần thiết.

## 9. Sửa một hệ thống đang dựa vào mặc định

Đừng thay hàng loạt thành UTF-8 mà chưa phân loại dữ liệu hiện hữu. Một tệp đúng theo charset đã công bố khác với một tệp bị mã hóa nhầm nhưng mang tên giống nhau.

Quy trình hợp lý:

1. Kiểm kê các điểm tạo/đọc byte và hợp đồng hiện tại.
2. Xác định dữ liệu nào thực sự là UTF-8, dữ liệu nào có quy ước khác.
3. Thay các phụ thuộc mặc định bằng charset phù hợp ở từng biên.
4. Kiểm thử với mẫu có dấu/emoji và trường hợp lỗi.
5. Nếu cần chuyển dữ liệu đã lưu, giữ bản gốc và thực hiện quá trình đọc theo charset nguồn rồi ghi theo charset đích đã biết.
6. Xác minh đầu ra với bên tiêu thụ trước khi thay thế dữ liệu đang sử dụng.

Không dùng công thức “encode bằng charset A rồi decode bằng charset B” như mẹo sửa mọi chuỗi hỏng. Nó chỉ có thể phục hồi trong một số lịch sử chuyển đổi cụ thể, khi thông tin còn đủ; nếu đã thay ký tự hoặc mất byte thì có thể không khôi phục được.

Không sửa toàn cục `file.encoding` ở giữa chương trình rồi kỳ vọng mọi reader/writer đang tồn tại đổi quy ước theo. Thay đổi thuộc tính hệ thống không phải cơ chế chuyển charset đáng tin cậy cho một đối tượng đã tạo. Chỉ định rõ charset khi dựng điểm chuyển đổi.

## 10. Những ranh giới không nên đánh đồng

| Vấn đề | Vì sao khác |
| --- | --- |
| Charset của tệp mã nguồn Java | Ảnh hưởng cách trình biên dịch đọc nguồn; không tự định nghĩa charset payload runtime |
| Charset mặc định của JVM | Chỉ được API dùng nếu hợp đồng của nó dựa vào giá trị đó |
| Charset của terminal | Ảnh hưởng hiển thị/nhập ở console; không tự phản ánh byte đã gửi qua giao thức |
| Nội dung String | Là dữ liệu ký tự; không mang nhãn “được mã hóa UTF-8” như một mảng byte |
| Chuẩn hóa Unicode | Là quyết định về dạng ký tự; không tự xảy ra chỉ vì chọn UTF-8 |

Tự thực hành:

1. Đổi dữ liệu thử thành ASCII thuần và giải thích vì sao nhánh đọc sai có thể không lộ lỗi.
2. Dùng một mẫu tiếng Việt, so sánh byte trước/sau trao đổi và code point sau giải mã.
3. Tìm một API không nhận tham số charset nhưng có hợp đồng UTF-8 cố định; phân biệt nó với API dùng charset mặc định.
4. Nêu hai tình huống khác nhau: byte sai dạng với UTF-8 và byte hợp lệ nhưng bị đọc sai charset.
5. Viết hợp đồng ngắn cho một tệp xuất: charset, xuống dòng, cách xử lý lỗi và cách bên nhận xác nhận quy ước.
