# Phân biệt dữ liệu nhị phân với văn bản trong Java I/O

## 1. Cùng lưu thành byte, khác cách diễn giải

Trong bộ nhớ, trên đĩa và khi truyền qua mạng, nội dung cuối cùng đều được biểu diễn bằng **byte**. **Dữ liệu văn bản (text)** là dữ liệu mà các byte được chuyển đổi thành ký tự theo một **bảng mã (charset/character encoding)**. **Dữ liệu nhị phân (binary)** theo cách phân loại I/O thường là dữ liệu được diễn giải theo cấu trúc byte riêng của một định dạng: ảnh, file nén, số nguyên, bản ghi giao thức, trường độ dài cố định...

Do đó **file text cũng là một dãy byte**. Sự khác nhau nằm ở *hợp đồng diễn giải*, không phải việc một file có dùng bit hay không:

- Với **text**, phải biết charset để mã hóa ký tự thành byte và giải mã byte thành ký tự.
- Với **binary có cấu trúc**, phải biết quy tắc byte: thứ tự trường, kích thước, endianness, phiên bản hoặc parser phù hợp.
- Có **định dạng hỗn hợp**: thông điệp HTTP có header dạng text và body có thể chứa JSON, ZIP, ảnh hoặc byte bất kỳ; file binary cũng có thể chứa trường chuỗi UTF-8.

Ví dụ, “Aé” có hai Unicode code point nhưng chiếm ba byte trong UTF-8:

~~~text
Ký tự            A        é
Code point       U+0041   U+00E9
UTF-8 hex        41       C3 A9
Toàn bộ byte     41 C3 A9
~~~

Giải mã dãy byte 41 C3 A9 bằng UTF-8 cho ra “Aé”; nếu giải mã bằng ISO-8859-1 lại thành “AÃ©”. **Bản thân byte không tự cho biết charset**: ứng dụng phải có quy ước, đặc tả hay metadata để xác định nó.

## 2. Khái niệm nền tảng

| Khái niệm | Cách hiểu | Ví dụ |
| --- | --- | --- |
| Bit/byte | Đơn vị dữ liệu thô, mỗi byte gồm 8 bit | Byte 0x41 |
| Unicode code point | Mã Unicode biểu diễn một đơn vị ký tự | é = U+00E9 |
| Charset/encoding | Quy tắc biến ký tự thành byte và ngược lại | UTF-8, UTF-16LE, ISO-8859-1 |
| String trong Java | Chuỗi ký tự trong bộ nhớ, không kèm “charset của file” | “Aé” |
| File format | Quy tắc tổ chức nội dung | CSV, JSON, PNG, ZIP |
| Extension/MIME | Tín hiệu/khai báo loại file, không bảo đảm nội dung | .txt, .png, image/png |

**String.length() của Java đếm đơn vị mã UTF-16 (char)**, không phải byte UTF-8 hay luôn là số Unicode code point. Một code point ngoài Basic Multilingual Plane có thể dùng hai char (surrogate pair); một ký tự người dùng nhìn thấy cũng có thể gồm nhiều code point ghép dấu. Dùng codePointCount(...) để đếm code point; dùng getBytes(charset).length hoặc đọc byte thực tế để biết kích thước sau mã hóa.

UTF-8 mã hóa Unicode thành 1–4 byte cho mỗi code point; ký tự ASCII dùng một byte tương ứng. UTF-16LE/UTF-16BE dùng quy tắc và byte order khác. **BOM (byte order mark)** là dấu hiệu tùy chọn: BOM UTF-8 có các byte EF BB BF, **UTF-8 không yêu cầu BOM**. Với UTF-16, BOM có thể dùng để biểu thị byte order; không có BOM thì cần biết encoding từ nguồn khác.

Kết thúc dòng cũng là byte: LF = 0A hex, CRLF = 0D 0A hex. Hai file hiển thị cùng chữ vẫn có thể khác byte. Khi cần checksum hoặc chữ ký số phải xét byte; khi so sánh text theo ngữ nghĩa, cần thống nhất charset và quy tắc xuống dòng/chuẩn hóa.

## 3. Trong Java chọn byte stream hay character stream?

| Nhu cầu | API Java | Điều cần lưu ý |
| --- | --- | --- |
| Copy file bất kỳ mà giữ nguyên byte | InputStream, OutputStream, Files.copy | Không đi qua String |
| Đọc/ghi dữ liệu byte | Files.readAllBytes, Files.write | Không tự giải mã |
| Đọc/ghi văn bản | Reader, Writer, Files.readString, Files.writeString | Chọn charset rõ ràng |
| Kết nối byte với ký tự | InputStreamReader, OutputStreamWriter | Charset là phần bắt buộc của hợp đồng |
| Đọc cấu trúc binary | DataInputStream, ByteBuffer, thư viện parser | Biết schema, byte order, version |

**InputStream/OutputStream làm việc với byte**; **Reader/Writer làm việc với ký tự**. InputStreamReader là cầu nối *byte → ký tự*, OutputStreamWriter là cầu nối *ký tự → byte*. Những cầu nối này hiểu encoding, nhưng **không** tự giải mã định dạng PNG, ZIP hoặc protobuf.

Với text được quy định là UTF-8, dùng StandardCharsets.UTF_8 ở cả hai chiều. Khi định dạng yêu cầu charset khác thì dùng đúng charset ấy. Tránh vô tình dựa vào encoding mặc định của môi trường nếu dữ liệu cần chạy qua nhiều hệ thống.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu đoạn sau thành **BinaryVsTextDemo.java**, mã nguồn UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class BinaryVsTextDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-text-", ".txt");
        try {
            String original = "Aé";
            Files.writeString(file, original, StandardCharsets.UTF_8);

            byte[] raw = Files.readAllBytes(file);
            String restored = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("utf16Units=" + original.length());
            System.out.println("codePoints="
                    + original.codePointCount(0, original.length()));
            System.out.println("utf8Bytes=" + raw.length);
            System.out.println("hex=" + HexFormat.of().formatHex(raw));
            System.out.println("restored=" + restored);
            System.out.println("roundTrip=" + original.equals(restored));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 BinaryVsTextDemo.java
java BinaryVsTextDemo
~~~

Stdout:

~~~text
utf16Units=2
codePoints=2
utf8Bytes=3
hex=41c3a9
restored=Aé
roundTrip=true
~~~

**Files.writeString** đã mã hóa String thành byte UTF-8. **Files.readAllBytes** trả về chính ba byte trong file, không diễn giải thành ký tự. **Files.readString** dùng UTF-8 để giải mã byte thành String. Độ dài 2 đơn vị UTF-16 và 3 byte UTF-8 không hề mâu thuẫn. Ví dụ tạo file tạm và xóa trong finally nên không cần đường dẫn phụ thuộc máy.

readAllBytes/readString thích hợp khi dữ liệu đủ nhỏ. Với file lớn, đọc toàn bộ file một lần có thể tốn nhiều RAM; hãy xử lý tuần tự bằng InputStream/Reader và buffer.

## 5. Những tình huống thực tế

### 5.1. Sao chép ảnh, ZIP hoặc bất kỳ file nào

Khi yêu cầu là sao chép nguyên nội dung, thao tác ở tầng byte. Đây là **mảnh code minh họa** đặt trong phương thức đã có hai biến Path source và destination, có import Files và xử lý IOException:

~~~java
try (var input = Files.newInputStream(source);
     var output = Files.newOutputStream(destination)) {
    input.transferTo(output);
}
~~~

transferTo truyền byte, không mã hóa hay giải mã. File PNG mở đầu bằng signature gồm các byte **89 50 4E 47 0D 0A 1A 0A** (hex); nếu xử lý PNG bằng Reader và Writer, byte không hợp lệ theo charset có thể bị thay thế khiến file ảnh hỏng. Đổi tên .png thành .txt cũng không biến dữ liệu ảnh thành văn bản.

### 5.2. Đọc CSV, JSON và TXT

Nếu hợp đồng nói rõ dữ liệu là text UTF-8, giải mã byte thành String:

~~~java
String json = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây chỉ là **mảnh code** khi đã có Path path và import phù hợp. Nó thực hiện **decode**, chưa phải **parse**. JSON cần parser JSON; CSV cần parser xử lý dấu ngoặc kép, dấu phân cách và newline trong một trường dữ liệu. Charset và cú pháp định dạng là hai trách nhiệm khác nhau.

### 5.3. Đọc số nhị phân

Chuỗi text “1234” có byte UTF-8 **31 32 33 34**. Một trường integer 32-bit trong định dạng binary có thể cũng chiếm bốn byte nhưng mang giá trị khác và có byte order riêng. Muốn đọc cần biết độ dài trường, signed/unsigned, big-endian/little-endian và version. DataInputStream hoặc ByteBuffer có thể hỗ trợ các thao tác đó; chúng không tự đoán schema của file chưa rõ định dạng.

### 5.4. Nhúng binary vào JSON

Nếu muốn gửi ảnh trong JSON, có thể dùng **Base64** để biến một dãy byte thành chuỗi ký tự ASCII, rồi phía nhận giải mã Base64 để phục hồi byte gốc. Base64 **không biến ảnh thành text theo nghĩa dữ liệu gốc**, không phải nén và không phải mã hóa bảo mật. Không nên tạo String từ byte ảnh tùy ý bằng một charset để đưa vào JSON vì có nguy cơ đổi byte.

### 5.5. Nội dung hỗn hợp

Một định dạng binary có thể chứa tên file, ghi chú hoặc metadata là chuỗi UTF-8; một tài liệu JSON lại có thể chứa trường Base64 của ảnh. Trong mỗi trường hợp, dùng parser đúng định dạng trước, rồi áp dụng decoding tại những trường mà đặc tả quy định là text.

## 6. Byte không hợp lệ và cách phát hiện lỗi charset

Nếu byte C3 A9 của “é” được giải mã theo ISO-8859-1, chữ sẽ hiện thành “Ã©” (mojibake). Nếu một chuỗi byte không hợp lệ theo UTF-8 được đưa qua new String(bytes, StandardCharsets.UTF_8), ký tự bị lỗi có thể được thay thế bằng **U+FFFD**. Nếu lại mã hóa và ghi ra file, các byte gốc có thể không phục hồi được.

Để **từ chối** byte không hợp lệ thay vì chấp nhận thay thế, dùng CharsetDecoder cùng CodingErrorAction.REPORT.

Tạo file **StrictUtf8Demo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Demo {
    public static void main(String[] args) {
        byte[] input = {(byte) 0xC3, (byte) 0x28};

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            decoder.decode(ByteBuffer.wrap(input));
            System.out.println("valid UTF-8");
        } catch (CharacterCodingException e) {
            System.out.println("invalid UTF-8");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictUtf8Demo.java
java StrictUtf8Demo
~~~

Stdout:

~~~text
invalid UTF-8
~~~

Byte C3 cần một byte tiếp nối theo quy tắc UTF-8; byte 28 không phải byte tiếp nối hợp lệ. Decoder ném lỗi, chương trình in “invalid UTF-8”. Tuy nhiên, **một dãy byte hợp lệ UTF-8 chưa đủ chứng minh nó là text**: nội dung binary có thể tình cờ gồm byte UTF-8 hợp lệ.

## 7. Nhận diện loại file khi không có thông tin đầy đủ

Không tồn tại phép thử tổng quát 100% chỉ từ nội dung byte để khẳng định “đây là text” hay “đây là binary”. Các byte **41 42 43** có thể biểu diễn chữ “ABC” theo ASCII/UTF-8, nhưng cũng có thể là ba byte của một bản ghi nhị phân.

Quy trình hợp lý:

1. **Xem hợp đồng dữ liệu**: tài liệu API, schema, giao thức, Content-Type và charset khi đáng tin, hoặc metadata của nguồn file.
2. **Đối chiếu định dạng**: header, magic bytes, version, parser; extension chỉ là gợi ý và có thể bị đổi.
3. **Nếu xác định là text**, chọn encoding được yêu cầu; dùng decoder báo lỗi nếu cần bảo vệ tính toàn vẹn.
4. **Nếu chưa rõ**, giữ bản gốc dưới dạng byte, xem hex dump hoặc hỏi đặc tả; đừng mở bằng text editor rồi ghi lại với encoding phỏng đoán.

Những đặc điểm như byte 00, tỷ lệ ký tự in được, ký tự điều khiển, BOM đều **chỉ là heuristic**. Văn bản UTF-16 có thể chứa byte 00; file nhị phân có thể chứa nhiều chuỗi chữ nhìn thấy được. Kiểm tra hợp lệ UTF-8 là kiểm tra *một encoding*, không phải parser nhận dạng mọi file.

## 8. Lỗi thường gặp và cách tránh

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Quyết định chỉ dựa vào .txt/.bin | Phân loại sai nếu đuôi bị đổi | Dùng schema, metadata và signature |
| Dùng Reader/Writer để copy ảnh | Có thể đổi byte, hỏng ảnh | Copy bằng byte stream |
| Không chỉ định charset cho text | Chữ Việt sai trên môi trường khác | Chọn charset ở cả đọc/ghi |
| Dùng String.length() làm số byte | Sai với ký tự đa byte/surrogate pair | Đếm byte sau mã hóa |
| Bỏ qua newline và BOM | Byte/checksum khác dù hiển thị giống nhau | Xác định quy ước ngay từ đầu |
| Thấy UTF-8 hợp lệ liền coi là text | Nhận diện nhầm định dạng | Dùng hợp đồng và parser |
| Đọc cả file rất lớn vào byte[] | Tốn RAM | Stream/buffer theo khối |
| Coi Base64 là encryption | Hiểu sai bảo mật | Chỉ dùng Base64 làm biểu diễn byte |

## 9. Tự kiểm tra kèm giải đáp

**Câu 1.** “Aé” có 2 code point nhưng 3 byte UTF-8: Java có làm mất dữ liệu không?  
**Đáp án:** Không. A chiếm 1 byte, é chiếm 2 byte UTF-8; nếu ghi và đọc cùng charset, chuỗi được phục hồi chính xác.

**Câu 2.** Có thể copy file ZIP bằng byte stream mà không hiểu ZIP?  
**Đáp án:** Có. Copy nguyên byte không đòi hỏi parser định dạng; chỉ khi phân tích/chỉnh sửa bên trong ZIP mới cần hiểu cấu trúc.

**Câu 3.** File không có BOM có thể là UTF-8 không?  
**Đáp án:** Có. UTF-8 BOM là tùy chọn, không bắt buộc.

**Câu 4.** Giải mã UTF-8 thành công có đủ kết luận đó là file text?  
**Đáp án:** Không. Binary cũng có thể vô tình là dãy UTF-8 hợp lệ.

**Câu 5.** Vì sao không dùng new String(imageBytes, UTF_8) để đưa ảnh vào JSON?  
**Đáp án:** Byte không hợp lệ có thể bị thay thế. Dùng Base64 để biểu diễn và phục hồi đúng mọi byte.

**Câu 6.** Files.readString(path, UTF_8) có phân tích cú pháp CSV/JSON chưa?  
**Đáp án:** Chưa. Phương thức chỉ decode byte thành String; cần parser riêng để hiểu các trường của file.

**Ghi nhớ:** Luôn xác định **định dạng và charset** trước khi diễn giải byte. Java byte stream dùng để xử lý/bảo toàn byte; Java character stream dùng để xử lý ký tự theo bảng mã được chọn.
