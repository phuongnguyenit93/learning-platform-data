# Vì sao không dùng luồng ký tự để sao chép dữ liệu nhị phân?

## 1. Vấn đề cốt lõi: sao chép dữ liệu phải giữ nguyên từng byte

Khi sao chép một file **PNG, JPEG, PDF, ZIP, JAR, MP3, video, file nén, file cơ sở dữ liệu hoặc nội dung nhị phân từ mạng**, yêu cầu quan trọng nhất là **dãy byte đầu ra phải giống dãy byte đầu vào**, theo đúng thứ tự và đúng số lượng.

Ví dụ, nếu byte nguồn là:

~~~text
41 FF 00 0D 0A 42
~~~

Thì kết quả sao chép hợp lệ phải vẫn là **41 FF 00 0D 0A 42**. Không được thêm, bỏ hoặc đổi bất kỳ byte nào, kể cả byte **00**, byte **FF**, hay cặp byte **0D 0A**.

Một file nhị phân không nhất thiết biểu diễn văn bản theo bảng mã nào. Dữ liệu của nó có thể gồm mọi giá trị từ **00** đến **FF**, trong đó nhiều tổ hợp **không phải chuỗi ký tự hợp lệ** của UTF-8 hoặc charset khác.

Trong Java, **InputStream/OutputStream** xử lý các byte gần với biểu diễn gốc, trong khi **Reader/Writer** xử lý ký tự. Dùng Reader/Writer để sao chép file nhị phân sẽ thêm bước diễn giải dữ liệu thành văn bản. Bước này **không có cơ sở** khi nội dung vốn không phải văn bản và có thể làm mất tính toàn vẹn dữ liệu.

> Quy tắc: **sao chép byte → dùng luồng byte**. **Đọc, xử lý hoặc xuất văn bản theo charset → dùng luồng ký tự**.

## 2. Khác nhau về đơn vị dữ liệu và công việc thực hiện

| Tiêu chí | Luồng byte | Luồng ký tự |
| --- | --- | --- |
| API Java tiêu biểu | **InputStream**, **OutputStream** | **Reader**, **Writer** |
| Đơn vị xử lý | **byte** (8 bit) | Đơn vị ký tự Java **char** (UTF-16 code unit, 16 bit) |
| Diễn giải charset? | Không cần | Có, khi chuyển giữa byte và ký tự |
| Ví dụ | **FileInputStream**, **FileOutputStream**, **BufferedInputStream**, **BufferedOutputStream** | **FileReader**, **FileWriter**, **BufferedReader**, **BufferedWriter** |
| Phù hợp | Ảnh, ZIP/JAR, PDF, âm thanh, dữ liệu nhị phân, mọi file cần sao chép chính xác | Nội dung văn bản cần đọc theo ký tự hoặc dòng |
| Tiêu chí chính | Bảo toàn dãy byte gốc | Bảo toàn ý nghĩa ký tự theo một mã hóa đã chọn |

**char** trong Java biểu diễn một đơn vị mã UTF-16, không phải lúc nào cũng trùng với một ký tự Unicode hoàn chỉnh. Một số ký tự Unicode ngoài Basic Multilingual Plane cần **hai char** (surrogate pair). Sự khác nhau này càng cho thấy **một char không tương ứng cố định với một byte**.

Một ứng dụng dùng **BufferedInputStream** vẫn đang làm việc theo byte, vì buffering chỉ là tích lũy byte nhằm giảm chi phí I/O; bản thân nó **không biến byte thành ký tự**. Ngược lại, **BufferedReader** là luồng ký tự, không phù hợp với sao chép nhị phân dù có chữ “Buffered” giống nhau.

## 3. Tại sao Reader và Writer có thể thay đổi byte?

### 3.1. Giải mã: byte → ký tự

Khi dữ liệu từ một **InputStream** đi qua **InputStreamReader**, các byte được **giải mã (decode)** theo charset:

~~~text
File nhị phân
  │
  ▼
byte[] gốc
  │
  ▼
InputStreamReader (decode theo charset)
  │
  ▼
ký tự Java (char)
~~~

Ví dụ, trong UTF-8:

- Byte **41** có thể biểu diễn ký tự **A**.
- Dãy **C3 A9** biểu diễn ký tự **é**.
- Byte **FF** đứng một mình **không hợp lệ** trong UTF-8.

Với cấu hình thông dụng dùng **InputStreamReader(..., StandardCharsets.UTF_8)**, chuỗi byte sai mã hóa có thể bị thay bằng ký tự thay thế **U+FFFD (�)**. Khi thông tin byte gốc đã bị thay thế, **không thể suy lại chắc chắn byte FF ban đầu** từ ký tự thay thế đó.

Có thể cấu hình **CharsetDecoder** để **REPORT** và ném lỗi thay vì thay thế ký tự không hợp lệ, nhưng điều đó vẫn không làm Reader trở thành công cụ thích hợp cho sao chép nhị phân: nhiều dãy byte nhị phân hợp lệ vẫn **không phải văn bản UTF-8 hợp lệ**.

### 3.2. Mã hóa: ký tự → byte

Khi ký tự đi qua **OutputStreamWriter**, chúng được **mã hóa (encode)** thành byte theo charset của đầu ra:

~~~text
Reader                   Writer
byte[] nguồn              ký tự đã giải mã              byte[] đích
     └── decode ──────────►     char[]      ── encode ───►     │
     (charset đầu vào)                   (charset đầu ra)
~~~

Nếu Reader gặp byte **FF** và đổi thành U+FFFD, Writer mã hóa U+FFFD trong UTF-8 thành **EF BF BD**. **Một byte FF** đã biến thành **ba byte EF BF BD**, làm lệch dữ liệu ngay cả khi dùng UTF-8 ở **cả đầu vào và đầu ra**.

Nếu mã hóa đầu vào và đầu ra khác nhau, một văn bản có thể được chuyển đổi charset theo ý định. Nhưng với dữ liệu nhị phân, đó là hành động làm biến đổi byte, **không phải sao chép**.

### 3.3. Các thao tác theo dòng có thể làm mất byte kết thúc dòng

**BufferedReader.readLine()** đọc một dòng văn bản và **không giữ dấu kết thúc dòng** trong String trả về. Nó coi **LF (\n)**, **CR (\r)** và **CRLF (\r\n)** là dấu hết dòng.

Nếu sau đó gọi **BufferedWriter.newLine()** hoặc **PrintWriter.println()**, chương trình ghi lại dấu xuống dòng theo quy tắc mới, thường phụ thuộc nền tảng. Dãy **0D 0A** có thể chuyển thành **0A**, hoặc các ranh giới dòng khác bị thay đổi. Điều này cũng xảy ra trên nội dung ASCII thuần, không cần có byte UTF-8 sai.

Ngoài ra, **readLine()** không tự giữ thông tin ranh giới cụ thể của từng dòng. Khi file chứa cả CRLF và LF, chương trình không còn biết mỗi dòng trước đó dùng kiểu xuống dòng nào chỉ từ String nhận được.

**Quan trọng:** bản thân Reader/Writer không tự động đổi mọi byte CRLF khi chỉ dùng **read(char[])** và **write(char[])**. Sự biến đổi xuống dòng xảy ra khi ứng dụng dùng các API mức dòng hoặc tự viết lại dấu xuống dòng; cần phân biệt lỗi do *decode/encode* với lỗi do *xử lý nội dung dạng text*.

## 4. Ví dụ Java 17+: thấy tận mắt byte bị biến đổi

Đoạn code sau tạo dữ liệu byte có giá trị **FF** không hợp lệ trong UTF-8, rồi đối chiếu hai cách sao chép:

1. **Sai cho nhị phân:** decode bằng **InputStreamReader**, sau đó encode bằng **OutputStreamWriter**.
2. **Đúng:** sao chép trực tiếp từ **InputStream** sang **OutputStream** bằng **transferTo**.
3. Thử thêm **readLine()** để thấy CRLF/CR có thể mất khi ghi lại từng dòng.

Lưu thành **BinaryCopyDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class BinaryCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] original = {
                0x41, (byte) 0xFF, 0x00, 0x0D, 0x0A, 0x42
        };

        // SAI đối với dữ liệu nhị phân: chuyển byte -> char -> byte.
        ByteArrayOutputStream textTarget = new ByteArrayOutputStream();
        try (Reader reader = new InputStreamReader(
                    new ByteArrayInputStream(original),
                    StandardCharsets.UTF_8);
             Writer writer = new OutputStreamWriter(
                    textTarget, StandardCharsets.UTF_8)) {
            char[] chars = new char[16];
            int count;
            while ((count = reader.read(chars)) != -1) {
                writer.write(chars, 0, count);
            }
        }
        byte[] viaCharacters = textTarget.toByteArray();

        // ĐÚNG: byte -> byte, không qua bảng mã.
        ByteArrayOutputStream byteTarget = new ByteArrayOutputStream();
        try (InputStream input = new ByteArrayInputStream(original)) {
            input.transferTo(byteTarget);
        }
        byte[] viaBytes = byteTarget.toByteArray();

        System.out.println("original=" +
                HexFormat.of().formatHex(original));
        System.out.println("characters=" +
                HexFormat.of().formatHex(viaCharacters));
        System.out.println("bytes=" +
                HexFormat.of().formatHex(viaBytes));
        System.out.println("characters equal=" +
                Arrays.equals(original, viaCharacters));
        System.out.println("bytes equal=" +
                Arrays.equals(original, viaBytes));

        // CRLF và CR sẽ bị mất khi readLine() bỏ ký tự kết thúc.
        byte[] newlines =
                "A\r\nB\rC\n".getBytes(StandardCharsets.US_ASCII);
        ByteArrayOutputStream lineTarget = new ByteArrayOutputStream();
        try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            new ByteArrayInputStream(newlines),
                            StandardCharsets.UTF_8));
             Writer writer = new OutputStreamWriter(
                    lineTarget, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                writer.write(line);
                writer.write('\n'); // Cố ý dùng LF để minh họa biến đổi.
            }
        }
        System.out.println("lines original=" +
                HexFormat.of().formatHex(newlines));
        System.out.println("lines rewritten=" +
                HexFormat.of().formatHex(lineTarget.toByteArray()));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac BinaryCopyDemo.java
java BinaryCopyDemo
~~~

Stdout dự kiến, cố định vì charset và dấu kết thúc dòng đã chỉ rõ trong code:

~~~text
original=41ff000d0a42
characters=41efbfbd000d0a42
bytes=41ff000d0a42
characters equal=false
bytes equal=true
lines original=410d0a420d430a
lines rewritten=410a420a430a
~~~

Giải thích từng phần:

- **41** tương ứng **A** và được giữ nguyên.
- **FF** là byte UTF-8 không hợp lệ, bị thay bằng ký tự **�**; UTF-8 mã hóa ký tự ấy thành **EF BF BD**.
- **00**, **0D**, **0A** và **42** không tự mất đi chỉ vì decode/encode bằng UTF-8 trong ví dụ đầu. Phần này cho thấy **không phải mọi byte đều nhất thiết bị thay đổi**; chỉ một byte bị đổi đã đủ làm file không còn giống bản gốc.
- **transferTo** chuyển nguyên dãy byte, vì vậy **Arrays.equals** trả về **true**.
- Chuỗi **A\r\nB\rC\n** được đọc thành ba dòng “A”, “B”, “C”. Mỗi dòng được viết lại với **LF (\n)**, nên dữ liệu gốc **0D 0A** và **0D** bị thay thành **0A**.

Ví dụ dùng **ByteArrayInputStream/ByteArrayOutputStream** để tái hiện kết quả mà không cần tạo file thực tế. Nguyên tắc tương tự áp dụng cho **FileInputStream/FileOutputStream** khi làm việc với file trên ổ đĩa.

## 5. Cách sao chép dữ liệu nhị phân đúng trong Java

### 5.1. Cách ngắn nhất để sao chép file: Files.copy

Với hai đường dẫn trên ổ đĩa, API **java.nio.file.Files.copy** là lựa chọn trực tiếp:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyBinaryFile {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("source.bin");
        Path destination = Path.of("copy.bin");

        // Chỉ sao chép nếu đích chưa tồn tại.
        Files.copy(source, destination);

        // -1 nghĩa là nội dung hai file giống nhau từng byte.
        System.out.println("identical=" +
                (Files.mismatch(source, destination) == -1L));
    }
}
~~~

Lưu thành **CopyBinaryFile.java**, đặt một file nguồn tên **source.bin** cùng thư mục chạy, sau đó:

~~~bash
javac CopyBinaryFile.java
java CopyBinaryFile
~~~

Khi sao chép thành công và không có tiến trình khác làm thay đổi file trong lúc kiểm tra, kết quả:

~~~text
identical=true
~~~

**Files.copy(Path, Path)** mặc định sẽ báo lỗi nếu file đích đã tồn tại; ví dụ không chủ động ghi đè. Nếu nghiệp vụ muốn thay file đích, có thể dùng tùy chọn **StandardCopyOption.REPLACE_EXISTING** nhưng phải cân nhắc việc mất dữ liệu đích cũ. Sao chép nội dung byte giống nhau không có nghĩa là mọi metadata file (chẳng hạn owner, timestamp, quyền) đều được giữ hoàn toàn; đó là một yêu cầu khác.

### 5.2. Sao chép giữa hai luồng với InputStream.transferTo

Khi nguồn/đích không nhất thiết là file, chẳng hạn stream từ kết nối, blob hoặc tài nguyên:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(destination)) {
    long copiedBytes = in.transferTo(out);
}
~~~

Đây là **mảnh code minh họa**, giả định đã có biến **source**, **destination** kiểu **Path** và import các lớp cần thiết. **transferTo(OutputStream)** đọc đến EOF và ghi các byte sang OutputStream, không cần chuyển qua Reader/Writer và cũng không yêu cầu mã ứng dụng giữ toàn bộ dữ liệu trong một mảng lớn. Giá trị trả về là tổng số byte đã chuyển. Cả InputStream và OutputStream vẫn cần được đóng khi đã dùng xong; ví dụ dùng **try-with-resources**.

### 5.3. Sao chép theo buffer khi cần tự kiểm soát

Mẫu sao chép từng khối thường dùng **InputStream.read(byte[])** rồi **OutputStream.write(byte[], off, len)**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedBinaryCopy {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("source.bin");
        Path destination = Path.of("copy.bin");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(destination)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }
        }
    }
}
~~~

Lưu thành **BufferedBinaryCopy.java** rồi biên dịch với **javac BufferedBinaryCopy.java** và chạy **java BufferedBinaryCopy** khi có file **source.bin** và đích **copy.bin** chưa tồn tại. **count** là số byte đọc thật trong mỗi lần, có thể ít hơn **buffer.length**. Nếu viết nhầm **out.write(buffer)** thay vì **out.write(buffer, 0, count)**, lần đọc cuối ngắn hơn buffer có thể ghi thêm byte thừa từ vùng chưa được cập nhật.

Mẫu buffer phù hợp khi muốn cập nhật tiến độ, tính hash khi đang đọc, giới hạn tổng byte, hoặc xử lý từng khối trước khi viết. Đối với nguồn dữ liệu không đáng tin cậy, ngoài tính toàn vẹn còn cần giới hạn dung lượng, timeout và cách xử lý khi sao chép gặp lỗi giữa chừng.

## 6. Những trường hợp Reader/Writer thực sự phù hợp

Reader/Writer **không sai**: chúng được thiết kế để xử lý **văn bản**. Nếu nhiệm vụ là **đọc một file UTF-8, tìm/thay chuỗi, chuẩn hóa dòng hoặc chuyển từ một charset sang charset khác**, luồng ký tự là công cụ đúng.

Ví dụ nghiệp vụ muốn đổi toàn bộ dấu xuống dòng sang LF hoặc bỏ một số dòng khỏi file cấu hình: đọc từng dòng bằng **BufferedReader**, xử lý **String**, rồi ghi lại bằng **BufferedWriter** là hợp lý. Đầu ra lúc này được chủ động tạo thành một **văn bản mới**; không có yêu cầu giữ byte gốc.

Nếu muốn **sao chép nguyên văn byte của một file text**, chẳng hạn để lưu bản backup có chữ ký số hoặc hash đã biết, vẫn nên dùng **luồng byte**. File mang đuôi **.txt** cũng có thể có BOM, charset cũ, CRLF hoặc các byte đặc biệt cần bảo toàn. **Phần mở rộng .txt không tự cho phép ứng dụng thay đổi byte**.

| Yêu cầu | Nên chọn | Lý do |
| --- | --- | --- |
| Clone **photo.png**, **document.pdf**, **archive.zip**, **app.jar** | **Files.copy** hoặc InputStream/OutputStream | Giữ nguyên nội dung byte |
| Lưu nguyên payload HTTP nhận được để so hash | **InputStream/OutputStream** | Tránh decode/encode, giữ nội dung gốc |
| Đọc file cấu hình UTF-8 để phân tích từng dòng | **BufferedReader** với charset cụ thể | Đối tượng cần xử lý là text |
| Chuyển một tài liệu từ UTF-8 sang UTF-16 | **Reader + Writer** với charset đầu vào/đầu ra tương ứng | Chủ ý thay biểu diễn byte của văn bản |
| Sao lưu file text **giữ nguyên từng byte** | **Files.copy** | Hash và byte gốc cần giữ |
| Xuất dữ liệu CSV từ các String trong chương trình | **Writer** với charset rõ ràng | Sinh văn bản mới có cấu trúc |
| Đọc nhị phân theo trường (số nguyên, byte array) | **DataInputStream** hoặc ByteBuffer theo format | Diễn giải nhị phân theo giao thức đã định, không phải charset |

## 7. Có ngoại lệ nào mà sao chép qua ký tự vẫn giữ nguyên byte?

Có những trường hợp có thể **tình cờ hoặc có điều kiện** cho ra byte giống nhau, chẳng hạn các byte đầu vào đều hợp lệ trong cùng charset, không có thao tác sửa chuỗi và được mã hóa lại theo cách tương thích. Có charset ánh xạ đơn trị cho mọi giá trị byte, nên một lượt chuyển đổi tương ứng có thể khôi phục byte ban đầu.

Tuy nhiên, **đó không phải hợp đồng chung của Reader/Writer** và không có lý do dựa vào điều đó để sao chép file nhị phân. Với UTF-8, byte **FF** trong ví dụ trên đã cho thấy một phản ví dụ. Còn với **readLine/println**, thậm chí dữ liệu ký tự hoàn toàn hợp lệ cũng có thể biến đổi dấu xuống dòng.

Điểm cần phân biệt:

- **Đúng với một bộ dữ liệu thử nghiệm** không có nghĩa đúng với mọi file.
- **Charset giống nhau ở hai đầu** không đảm bảo không mất thông tin khi dữ liệu đầu vào có chuỗi byte sai charset.
- **Chọn ISO-8859-1 hoặc một charset khác** để ép byte thành ký tự vẫn tạo thêm thao tác không cần thiết; chỉ có thể chấp nhận nếu chương trình thực sự làm **chuyển đổi text** và có hợp đồng dữ liệu rõ ràng.
- **Giữ được chữ hiển thị** không đồng nghĩa với giữ được byte; một văn bản có thể có nội dung người dùng nhìn thấy giống nhau nhưng dùng encoding, BOM hoặc dấu xuống dòng khác.

## 8. Kiểm tra tính toàn vẹn sau khi sao chép

Với dữ liệu cần bảo đảm tính chính xác, kiểm tra kết quả theo **byte**, không dựa vào việc mở file và thấy hiển thị bình thường.

**Files.mismatch(source, copy)** (Java 12+) trả về **-1L** nếu không tìm thấy vị trí byte khác nhau; nếu khác, kết quả chỉ ra vị trí byte đầu tiên khác (hoặc điểm mà một file kết thúc trong khi file kia còn byte). Nó hữu ích khi có hai file nội bộ và muốn so byte chính xác.

Hash như **SHA-256** là cách thực tế để đối chiếu nội dung giữa hai hệ thống hoặc thời điểm khác nhau; hash giống nhau cho bằng chứng rất mạnh rằng nội dung tương đương, nhưng về mặt toán học vẫn là phép kiểm tra xác suất va chạm cực nhỏ, không phải thao tác so từng byte tuyệt đối. Chọn SHA-256 hoặc thuật toán hash mạnh được chấp nhận trong hệ thống thay cho chỉ so kích thước file.

Chỉ so sánh **Files.size(...)** là chưa đủ: hai file có thể cùng kích thước nhưng khác nội dung. Đồng thời, bản sao sẽ **không nhất thiết hoàn chỉnh** nếu đọc hoặc ghi gặp IOException giữa chừng; ứng dụng cần chính sách xử lý file đích dở dang (xóa hoặc ghi vào file tạm rồi thay thế nếu phù hợp).

## 9. Lỗi phổ biến và cách tránh

1. **Sao chép ảnh/PDF bằng FileReader và FileWriter.** Chuyển đổi charset có thể thay byte. Hãy dùng **Files.copy**, **InputStream/OutputStream**, hoặc API NIO byte-based.
2. **Cho rằng đặt cùng UTF-8 ở cả Reader và Writer thì an toàn.** Dữ liệu nhị phân có byte không hợp lệ với UTF-8; decoder có thể thay thế hoặc báo lỗi, làm quá trình khác sao chép.
3. **Dùng BufferedReader.readLine() để lấy nhị phân thành các dòng.** Đây là API dành cho text, bỏ mất dấu kết thúc dòng, không phải khung chia dữ liệu nhị phân.
4. **Dùng println() khi mong giữ nguyên byte.** println tạo định dạng văn bản và có thể thêm dấu xuống dòng theo nền tảng; ghi byte bằng **OutputStream.write**.
5. **Dùng String làm container của binary.** Tạo String từ byte rồi lấy byte ngược trở lại sẽ đi qua charset; dùng **byte[]** hoặc **ByteBuffer**.
6. **Đọc buffer rồi ghi cả buffer bất kể số byte thực nhận.** Phải dùng **out.write(buffer, 0, count)** với **count** từ **in.read(buffer)**.
7. **Cho rằng mọi byte 0 đều kết thúc dữ liệu.** Trong Java, **0x00** là dữ liệu nhị phân hợp lệ; **InputStream.read(...)** báo EOF bằng **-1**, không phải 0.
8. **Không kiểm tra file sao chép.** Nếu tính chính xác quan trọng, dùng **Files.mismatch** hoặc hash để xác nhận.
9. **Nghĩ buffering biến nhị phân thành văn bản.** **BufferedInputStream** an toàn cho byte; **BufferedReader** có chức năng khác hẳn.
10. **Không xử lý file đích đã tồn tại hoặc lỗi sao chép giữa chừng.** Chọn rõ chính sách overwrite, đóng tài nguyên, và xác nhận file đích đầy đủ khi nghiệp vụ cần.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** Một file ZIP gồm các byte tùy ý có thể được copy an toàn bằng **BufferedReader + BufferedWriter** nếu dùng cùng UTF-8 không?  
**Đáp:** Không có đảm bảo. Dữ liệu ZIP không có nghĩa là chuỗi UTF-8 hợp lệ; decode/encode có thể thay các byte sai charset. Dùng luồng byte.

**Câu 2:** Tại sao byte FF thành EF BF BD trong ví dụ?  
**Đáp:** **FF** không hợp lệ khi đứng riêng trong UTF-8, decoder thông dụng thay bằng ký tự **U+FFFD**, rồi UTF-8 encoder tạo **EF BF BD**.

**Câu 3:** **BufferedReader.readLine()** có giữ dãy **0D 0A** không?  
**Đáp:** Không. Nó trả về nội dung dòng không chứa dấu kết thúc. Nếu ghi lại bằng **newLine()**, dấu xuống dòng được tạo mới.

**Câu 4:** File text có cần dùng Reader để backup không?  
**Đáp:** Không. Nếu cần sao chép từng byte y hệt, dùng **Files.copy** dù file là text. Nếu cần chỉnh sửa nội dung ký tự, Reader/Writer phù hợp.

**Câu 5:** Vì sao phải dùng **out.write(buffer, 0, count)**?  
**Đáp:** **read(buffer)** có thể đọc được ít hơn dung lượng buffer, nhất là lần cuối. **count** chỉ đúng lượng byte vừa nhận; ghi cả buffer có thể chèn byte dư.

## 11. Tổng kết

Luồng ký tự **Reader/Writer** phục vụ văn bản: nó **giải mã byte thành ký tự**, cho phép xử lý nội dung ở mức ký tự, sau đó **mã hóa lại thành byte**. Vì dữ liệu nhị phân **không có nghĩa vụ tuân theo charset**, việc giải mã có thể thay thế byte không hợp lệ; xử lý dòng còn có thể thay dấu kết thúc. Chỉ cần thay **một byte** là bản sao đã sai.

Muốn sao chép dữ liệu nhị phân chính xác, dùng **Files.copy(...)**, **InputStream.transferTo(OutputStream)** hoặc vòng lặp **InputStream.read(buffer) / OutputStream.write(buffer, 0, count)**. Nếu cần chắc chắn, kiểm tra lại bằng **Files.mismatch(...)** hoặc hash phù hợp.

### Tham khảo chính thức

- [Oracle Java SE 21 — InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html): chuyển đổi byte thành ký tự và charset.
- [Oracle Java SE 21 — OutputStreamWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStreamWriter.html): chuyển đổi ký tự thành byte.
- [Oracle Java SE 21 — BufferedReader.readLine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html#readLine()): xử lý dấu kết thúc dòng.
- [Oracle Java SE 21 — InputStream.transferTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)): sao chép theo byte.
- [Oracle Java SE 21 — Files.copy và Files.mismatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): sao chép và so sánh file theo byte.
