# Chọn charset tường minh khi đọc và ghi văn bản trong Java

Một chương trình có thể ghi tệp thành công nhưng khi đọc lại xuất hiện chữ **“Ã©”, “Tiáº¿ng” hoặc ký tự “�”**. Nguyên nhân thường nằm ở cách chương trình **mã hóa ký tự thành byte khi ghi** và **giải mã byte thành ký tự khi đọc**. Chọn charset tường minh giúp quy định cùng một cách diễn giải dữ liệu ở cả hai phía, tránh phụ thuộc vào môi trường chạy.

Trong Java, hãy ưu tiên truyền một đối tượng `Charset` cụ thể, thường là `StandardCharsets.UTF_8`, ở ranh giới chuyển đổi **byte ↔ văn bản**. Điều quan trọng không chỉ là “dùng UTF-8”, mà còn là biết hệ thống và tệp thực sự đã sử dụng charset nào.

## 1. Charset làm nhiệm vụ gì?

Java biểu diễn văn bản trong các đối tượng như `String`, `char`, `Reader` và `Writer`. Trong khi đó, tệp và nhiều kết nối I/O lưu hoặc truyền **byte**. `java.nio.charset.Charset` mô tả cách ánh xạ giữa ký tự Unicode và một dãy byte.

- **Encoding (mã hóa):** ký tự → byte, diễn ra khi ghi văn bản ra tệp hoặc gửi byte trên mạng.
- **Decoding (giải mã):** byte → ký tự, diễn ra khi đọc byte từ tệp hoặc mạng thành văn bản.
- **Charset:** quy tắc cho hai phép chuyển đổi; ví dụ `UTF-8`, `UTF-16`, `ISO-8859-1`.
- **Charset của dữ liệu** cần được xác định từ quy ước định dạng, giao thức, tài liệu nguồn hoặc metadata đáng tin cậy; không thể chắc chắn suy ra chỉ từ kiểu `String` của Java.

~~~text
                    GHI VĂN BẢN
String/char --encode UTF-8--> byte[] / tệp / luồng mạng
    "é"                        C3 A9

                    ĐỌC VĂN BẢN
byte[] / tệp / luồng mạng --decode UTF-8--> String/char
          C3 A9                             "é"
~~~

Ví dụ, `é` có mã Unicode U+00E9. Khi mã hóa bằng UTF-8, ký tự này thành **hai byte `C3 A9`** (hệ thập lục phân). Đọc hai byte đó bằng UTF-8 thì nhận lại `é`; đọc bằng ISO-8859-1 lại thành **`Ã©`**, vì charset này gán ý nghĩa khác cho từng byte.

**Không có “UTF-8 String” theo nghĩa String giữ nguyên byte UTF-8 bên trong.** `String` là dữ liệu văn bản Unicode; charset chỉ tham gia khi chuyển sang hoặc từ biểu diễn byte. Gọi `text.getBytes(charset)` mới tạo ra byte được mã hóa, còn `new String(bytes, charset)` mới giải mã byte thành chuỗi.

## 2. Tại sao phải chọn charset tường minh?

Một số API cũ sử dụng **charset mặc định của môi trường chạy** nếu bạn không cung cấp tham số. Ví dụ:

~~~java
// Dễ phụ thuộc môi trường: không nêu charset để đọc/ghi.
String text = new String(bytes);
byte[] encoded = text.getBytes();

Reader reader = new InputStreamReader(inputStream);
Writer writer = new OutputStreamWriter(outputStream);
~~~

Đây là **các dòng minh họa**, các biến `bytes` và `inputStream`/`outputStream` phải có sẵn; không phải chương trình độc lập. Những overload không có tham số charset dễ bị hiểu nhầm thành “luôn UTF-8”.

Lịch sử môi trường quan trọng:

- Trên **Java 17 và các bản trước**, charset mặc định của Java có thể thay đổi theo hệ điều hành, thiết lập locale hoặc cấu hình JVM; một chương trình chạy trên hai máy có thể ghi các byte khác nhau nếu dựa vào mặc định.
- Từ **Java 18**, JEP 400 chuẩn hóa charset mặc định thành UTF-8 trong đa số trường hợp, nhưng vẫn có ngoại lệ hoặc thiết lập tương thích, và không phải API nào cũng có cùng quy tắc. Vì vậy, code trao đổi dữ liệu nên tiếp tục khai báo charset theo **hợp đồng dữ liệu**.
- Một số API hiện đại đã **quy định mặc định UTF-8**, như `Files.readString(path)` hoặc `Files.writeString(path, text)`. Dẫu vậy, truyền `StandardCharsets.UTF_8` giúp người đọc thấy rõ ý định và dễ thay đổi khi tệp yêu cầu encoding khác.
- Không nên giả định charset của terminal, console, tệp CSV do bên thứ ba tạo hoặc header HTTP giống charset mặc định của JVM.

Ví dụ nên dùng:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

Reader reader = new InputStreamReader(inputStream, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
~~~

Đây cũng là các dòng minh họa, dùng import `java.nio.charset.StandardCharsets`, `java.io.Reader`, `java.io.Writer`, `java.io.InputStreamReader` và `java.io.OutputStreamWriter`. Trong chương trình thực, stream phải được quản lý vòng đời đúng hợp đồng ownership.

**Mục tiêu của chọn charset tường minh:** dữ liệu đi qua ranh giới byte/văn bản phải được hiểu theo **một quy ước đã xác định**, không thay đổi chỉ vì ứng dụng được chạy ở môi trường khác.

## 3. Chọn charset nào?

### UTF-8 thường là lựa chọn mặc định tốt cho văn bản mới

`StandardCharsets.UTF_8` là charset Unicode phổ biến, biểu diễn ký tự bằng số lượng byte biến thiên và tương thích với ASCII cho các ký tự ASCII. Nó biểu diễn tiếng Việt và hầu hết văn bản đa ngôn ngữ, được sử dụng rộng rãi trong hệ thống và định dạng hiện đại.

Ví dụ:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset charset = StandardCharsets.UTF_8;
~~~

Không cần tự xây tên charset bằng chuỗi nếu Java đã có hằng số chuẩn. `StandardCharsets` bảo đảm có sẵn các charset như `UTF_8`, `UTF_16`, `UTF_16BE`, `UTF_16LE`, `ISO_8859_1`, `US_ASCII`, nên cũng tránh sai chính tả khi viết tên.

### Nhưng phải tôn trọng charset thực tế của dữ liệu

Nếu đặc tả yêu cầu UTF-16LE, dữ liệu đã được xuất bằng ISO-8859-1, hoặc một hệ thống kế thừa sử dụng một charset khác, **không tự áp UTF-8 để “chữa” tệp**. Phải đọc đúng charset ban đầu, sau đó nếu cần mới chủ động **chuyển mã** sang UTF-8 khi xuất.

Ví dụ định dạng cho biết nguồn là ISO-8859-1:

~~~java
String decoded = new String(sourceBytes, StandardCharsets.ISO_8859_1);
byte[] utf8Bytes = decoded.getBytes(StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa với `sourceBytes` có sẵn: trước tiên **giải mã theo encoding nguồn**, sau đó **mã hóa theo encoding đích**. Không thể “đổi encoding” bằng cách đổi tên tệp hay gọi `new String` với một charset ngẫu nhiên.

Đặc biệt, **không dùng `US_ASCII` hoặc `ISO_8859_1` cho văn bản chứa mọi loại ký tự tiếng Việt**: các charset này không biểu diễn được tất cả ký tự cần thiết. Một số API mã hóa có thể thay ký tự không biểu diễn được bằng ký tự thay thế, dẫn đến **mất dữ liệu không phục hồi được**.

## 4. Đọc và ghi tệp text: `Files.readString` và `Files.writeString`

Với tệp văn bản tương đối nhỏ, API của `java.nio.file.Files` là lựa chọn đơn giản:

~~~java
Path path = Path.of("note.txt");
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
String value = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa, cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`; ngoại lệ I/O phải được xử lý hoặc khai báo. Charset ở phía ghi và phía đọc **khớp nhau**.

- `Files.writeString(path, text, charset)` mã hóa nội dung theo charset được truyền rồi ghi ra tệp; theo lựa chọn mở mặc định, tệp có thể được tạo hoặc nội dung tệp đang có bị ghi thay thế.
- `Files.readString(path, charset)` đọc nội dung tệp rồi giải mã thành `String` bằng charset đã chỉ định.
- Hai API có thể yêu cầu bộ nhớ tương ứng với kích thước văn bản. Với tệp lớn hoặc cần xử lý theo dòng, hãy dùng reader/writer theo luồng.

### Chương trình Java 17+ chạy độc lập

Lưu thành tệp **`ExplicitCharsetDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class ExplicitCharsetDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("explicit-charset-", ".txt");
        String original = "Tiếng Việt: cà phê ☕";

        try {
            Files.writeString(file, original, StandardCharsets.UTF_8);

            byte[] storedBytes = Files.readAllBytes(file);
            String restored = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("Round-trip: " + original.equals(restored));
            System.out.println("Text: " + restored);
            System.out.println("Bytes equal: " + Arrays.equals(
                    storedBytes, restored.getBytes(StandardCharsets.UTF_8)));

            byte[] eAcuteUtf8 = "é".getBytes(StandardCharsets.UTF_8);
            System.out.println("Correct decode: "
                    + new String(eAcuteUtf8, StandardCharsets.UTF_8));
            System.out.println("Wrong decode: "
                    + new String(eAcuteUtf8, StandardCharsets.ISO_8859_1));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac -encoding UTF-8 ExplicitCharsetDemo.java
java ExplicitCharsetDemo
~~~

Với terminal hỗ trợ hiển thị Unicode, kết quả chuẩn là:

~~~text
Round-trip: true
Text: Tiếng Việt: cà phê ☕
Bytes equal: true
Correct decode: é
Wrong decode: Ã©
~~~

Điểm cần quan sát:

1. `Files.writeString` **mã hóa** `original` thành byte UTF-8 trong tệp.
2. `Files.readAllBytes` lấy đúng byte thô; chưa giải mã chúng.
3. `Files.readString` **giải mã** cùng byte bằng UTF-8 nên thu lại chuỗi ban đầu. Dòng `Round-trip: true` chứng minh văn bản khôi phục bằng chuỗi gốc trong ví dụ.
4. So sánh `storedBytes` với `restored.getBytes(UTF_8)` kiểm tra chuỗi được mã hóa lại cho ra đúng byte của tệp.
5. Hai dòng cuối dùng **cùng byte UTF-8 của `é`** và đổi duy nhất charset lúc đọc: UTF-8 → `é`, ISO-8859-1 → `Ã©`. Đây là hiện tượng *mojibake* — dữ liệu byte bị diễn giải theo quy tắc sai.
6. `finally` xóa tệp tạm để ví dụ không phụ thuộc vào tên tệp cố định và không để lại tệp được tạo trên hệ thống khi chương trình kết thúc thông thường.

Tùy cấu hình terminal, **việc hiển thị Unicode trên console** có thể khác với nội dung Unicode trong `String`. Lệnh `javac -encoding UTF-8` là **charset để trình biên dịch đọc tệp mã nguồn Java**, không tự quyết định charset của những tệp mà ứng dụng ghi/đọc; hai vấn đề cần phân biệt rõ.

## 5. Đọc và ghi văn bản theo luồng bằng `Reader`/`Writer`

Khi xử lý dữ liệu lớn hoặc liên tục, sử dụng cầu nối rõ charset:

- `InputStreamReader`: giải mã **byte từ `InputStream`** thành ký tự cho code đọc.
- `OutputStreamWriter`: mã hóa **ký tự từ code** thành byte cho `OutputStream`.
- `BufferedReader`/`BufferedWriter`: thêm buffer và API tiện lợi khi đọc/ghi văn bản; không thay charset của tầng chuyển đổi bên dưới.

Sơ đồ:

~~~text
ĐỌC: InputStream --[InputStreamReader + UTF-8]--> Reader/String
GHI: Writer/String --[OutputStreamWriter + UTF-8]--> OutputStream
~~~

Ví dụ là các phương thức trong cùng một lớp (được gọi từ ứng dụng khác):

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileLines {
    public static void writeTwoLines(Path file) throws IOException {
        try (BufferedWriter writer =
                     Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
            writer.write("Hà Nội");
            writer.newLine();
            writer.write("Đà Nẵng");
            writer.newLine();
        }
    }

    public static void readLines(Path file) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        }
    }
}
~~~

Đây là **lớp tiện ích độc lập có thể biên dịch**, nhưng không có `main`; một caller tạo `Path` và gọi `writeTwoLines(file)` rồi `readLines(file)` để thấy hai dòng tên địa điểm. `readLine()` trả lại nội dung từng dòng **không bao gồm** ký tự kết thúc dòng. `writer.newLine()` thêm dấu xuống dòng theo quy ước hệ thống; điều này **khác** với charset: charset kiểm soát ký tự được chuyển thành byte như thế nào.

Bạn cũng có thể tạo cầu nối trực tiếp khi nguồn/đích chưa phải tệp:

~~~java
// Các biến input/output là stream đã được caller cung cấp.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(input, StandardCharsets.UTF_8));
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8));
~~~

Hai dòng trên là **minh họa**: nếu bọc thêm `try-with-resources` để đóng wrapper, hãy chắc chắn phương thức hiện tại **sở hữu** cả stream gốc. Đóng `BufferedReader`/`BufferedWriter` thường đóng cả luồng nằm bên dưới; đừng vô tình đóng `System.in`, `System.out` hoặc stream framework/caller còn đang dùng.

Nếu dùng `Files.newBufferedReader(file)` hoặc `Files.newBufferedWriter(file)` mà không truyền charset, các overload cụ thể đó đã dùng UTF-8 theo hợp đồng API, nhưng phiên bản có `StandardCharsets.UTF_8` thể hiện rõ quy ước của bài học.

## 6. Phân biệt byte stream và character stream

| Nhiệm vụ | API tiêu biểu | Charset cần ở đâu? |
|---|---|---|
| Sao chép ảnh, ZIP, PDF, byte bất kỳ | `InputStream`, `OutputStream`, `Files.copy` | **Không** tự decode/encode; giữ nguyên byte |
| Ghi một `String` thành tệp text | `Files.writeString(path, text, charset)` | Tại bước **mã hóa** |
| Đọc một tệp text thành `String` | `Files.readString(path, charset)` | Tại bước **giải mã** |
| Đọc text theo dòng | `Files.newBufferedReader(path, charset)` | Reader áp dụng charset khi đọc byte |
| Ghi text theo dòng | `Files.newBufferedWriter(path, charset)` | Writer áp dụng charset khi ghi byte |
| Cần làm việc với luồng mạng chứa text | `InputStreamReader`, `OutputStreamWriter` | Charset đúng theo **giao thức dữ liệu** |
| Đã có byte và cần chuỗi | `new String(bytes, charset)` | Tại bước **giải mã** |
| Đã có chuỗi và cần byte | `text.getBytes(charset)` | Tại bước **mã hóa** |

Không nên đọc ảnh thành chuỗi rồi ghi lại bằng charset UTF-8: byte của ảnh có thể không hợp lệ dưới góc nhìn văn bản và sẽ bị thay đổi. Khi chỉ cần sao chép nguyên trạng, dùng luồng byte; khi cần hiểu nội dung văn bản, chọn charset và dùng API text.

## 7. Dữ liệu cũ và charset không khớp: xử lý ra sao?

Giả sử một tệp đã chứa byte biểu diễn text theo charset X, trong khi chương trình lại giải mã theo Y. Một trong hai tình huống thường gặp:

- **Byte vẫn hợp lệ dưới Y nhưng tạo ký tự sai:** ví dụ hai byte UTF-8 của `é` được đọc theo ISO-8859-1 và trở thành `Ã©`. Chương trình có thể không ném lỗi dù nội dung hiển thị sai.
- **Dãy byte không hợp lệ dưới Y:** một decoder kiểm tra nghiêm ngặt có thể ném lỗi; một decoder khác có thể thay các chuỗi lỗi bằng **U+FFFD REPLACEMENT CHARACTER (`�`)** hoặc ký tự thay thế khác tùy chính sách API.

Phân biệt **lỗi ở bước giải mã** với **lỗi ở bước mã hóa**:

1. Xác định byte gốc có còn nguyên vẹn không, bằng cách đọc **byte thô** trước (không qua text reader).
2. Tìm charset thật của nguồn từ tài liệu/giao thức/export settings; xem xét BOM/metadata nếu định dạng sử dụng, nhưng không coi chúng là bằng chứng chắc chắn cho mọi tệp.
3. Giải mã byte gốc bằng charset đúng, kiểm tra các ký tự có dấu và ký tự ngoài ASCII.
4. Nếu cần chuẩn hóa, **mã hóa lại** văn bản đúng thành UTF-8 để ghi tệp mới. Bảo toàn bản gốc khi chưa chắc chắn.
5. Nếu bản thân byte đã bị thay thế/ghi đè từ trước thì việc đọc lại bằng charset mới có thể **không cứu được** nội dung đã mất.

### Kiểm soát lỗi giải mã với `CharsetDecoder`

Khi cần **phát hiện byte UTF-8 không hợp lệ** thay vì âm thầm thay thế, có thể chọn chính sách `CodingErrorAction.REPORT`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StrictUtf8Reader {
    public static void readStrictly(Path file) throws IOException {
        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (InputStream bytes = Files.newInputStream(file);
             Reader reader = new InputStreamReader(bytes, decoder)) {
            char[] buffer = new char[4096];
            while (reader.read(buffer) != -1) {
                // Xử lý phần ký tự vừa đọc theo chiều dài thực tế.
            }
        }
    }
}
~~~

Đây là **lớp tiện ích biên dịch được** và không có `main`. Ví dụ chủ yếu cho thấy cách **cấu hình decoder**; khi triển khai xử lý thật phải lưu kết quả của `reader.read(buffer)` rồi chỉ sử dụng số ký tự đã đọc. `REPORT` khiến lỗi giải mã được báo qua ngoại lệ I/O thay vì chấp nhận ký tự thay thế. Khi dùng `new String(bytes, charset)`, đừng mặc nhiên cho rằng API sẽ ném lỗi với mọi byte không hợp lệ: hành vi thay thế/lỗi phụ thuộc API và decoder.

Đối với mã hóa ký tự không thể biểu diễn trong charset đích, `CharsetEncoder` cũng có thể được cấu hình với `CodingErrorAction.REPORT`. Việc báo lỗi sớm đặc biệt hữu ích với dữ liệu cần bảo toàn đầy đủ, chẳng hạn xuất/nhập văn bản có tên riêng tiếng Việt.

## 8. Các điểm thực tế cần thận trọng

### Encoding của mã nguồn khác với encoding của dữ liệu runtime

- `javac -encoding UTF-8 Main.java`: chỉ định cách compiler **đọc mã nguồn**.
- `Files.readString(path, StandardCharsets.UTF_8)`: chỉ định cách ứng dụng **đọc nội dung tệp lúc chạy**.
- `System.out.println(text)`: chuỗi là Unicode nhưng quá trình chuyển ra byte và hiển thị trên terminal còn phụ thuộc cấu hình luồng chuẩn/terminal. Nó **không thay thế** việc kiểm tra byte trong file.

Ba khâu này có thể dùng các thiết lập khác nhau. Đừng dùng việc console in “đúng dấu” để kết luận tệp đã được lưu đúng byte.

### Đảm bảo hai phía đồng thuận

Với một giao thức hoặc API trao đổi text, charset nên là một phần của **hợp đồng**. Người gửi mã hóa UTF-8 và người nhận giải mã UTF-8. Nếu giao thức có metadata charset (ví dụ `Content-Type` của một định dạng HTTP thích hợp), hãy xử lý theo đặc tả giao thức tương ứng; không tự áp một charset bất kể metadata hợp lệ.

Nếu sản phẩm cho phép người dùng chọn mã hóa khi import, cần công khai lựa chọn và dùng chính lựa chọn đó để đọc. Đối với tệp do ứng dụng tự quản lý, chọn **một charset cố định**, ghi rõ trong tài liệu và kiểm thử bằng chuỗi có dấu.

### BOM, newline và dữ liệu không phải text

Một số tệp có **byte-order mark (BOM)** ở đầu. Cách xử lý BOM phụ thuộc charset và API; đừng giả định mọi text reader tự động bỏ BOM. Với UTF-8, BOM không bắt buộc. Nếu định dạng của bạn cho phép hoặc yêu cầu BOM, cần quy định rõ cách ghi/đọc.

**Dấu xuống dòng** như LF/CRLF là vấn đề **quy ước nội dung**; một charset đúng không tự chuẩn hóa tất cả xuống dòng. Nếu so sánh byte giữa hai hệ thống, cần tính cả dấu xuống dòng và BOM chứ không chỉ ký tự hiển thị.

## 9. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| `new String(bytes)` mà không biết default charset | Cùng byte có thể cho kết quả khác khi đổi môi trường | `new String(bytes, StandardCharsets.UTF_8)` nếu nguồn thực sự UTF-8 |
| `text.getBytes()` khi xuất dữ liệu cho dịch vụ khác | Byte đầu ra phụ thuộc charset mặc định của API/JVM | `text.getBytes(StandardCharsets.UTF_8)` theo hợp đồng |
| Đọc UTF-8 bằng ISO-8859-1 | Văn bản dạng `Ã©` thay vì `é` | Đọc theo đúng charset gốc |
| Ghi tiếng Việt bằng US-ASCII | Ký tự ngoài bảng mã có thể bị thay thế | Dùng UTF-8 hoặc charset đích có khả năng biểu diễn |
| Dùng `Reader`/`Writer` để sao chép ảnh/ZIP | Có thể phá hủy byte nhị phân | Dùng stream byte |
| Nghĩ `javac -encoding UTF-8` giải quyết lỗi file lúc chạy | Chỉ ảnh hưởng cách compiler đọc source | Chỉ định charset tại thao tác runtime |
| Quên đóng reader/writer do mình mở | Có thể mất dữ liệu còn trong bộ đệm hoặc rò rỉ tài nguyên | Sử dụng `try-with-resources` khi sở hữu |
| Thấy console đúng dấu rồi kết luận file đúng encoding | Terminal có cơ chế hiển thị riêng | Kiểm tra file bằng byte hoặc đọc lại đúng charset |
| Nghĩ mọi overload `Files` đều dùng charset mặc định | Một số overload đã có UTF-8 được chỉ định rõ | Đọc hợp đồng từng API; truyền charset khi cần làm rõ |

## 10. Tự kiểm tra

**Câu 1.** Ứng dụng A ghi chuỗi `"Cà phê"` thành UTF-8; ứng dụng B đọc cùng tệp bằng ISO-8859-1. Vấn đề ở bước nào?

> Ở bước **giải mã của B**: B diễn giải byte theo charset không đúng với quy ước lúc A mã hóa. Cần cho B sử dụng đúng UTF-8, miễn là byte gốc vẫn còn nguyên.

**Câu 2.** Tại sao `Files.readAllBytes(path)` không có tham số charset nhưng `Files.readString(path, charset)` lại có?

> `readAllBytes` chỉ lấy **byte thô**, không diễn giải thành ký tự. `readString` cần **giải mã** byte thành văn bản nên phải có quy tắc charset.

**Câu 3.** Muốn sao chép một tệp ZIP không thay đổi nội dung, có cần chọn UTF-8 không?

> **Không.** ZIP là dữ liệu nhị phân; nên sao chép byte. Charset chỉ dùng khi cần đọc/ghi **phần văn bản** ở một định dạng mà đặc tả có quy định.

**Câu 4.** Code chạy trên Java 17 và Java 21, nên dùng `new String(bytes)` nếu biết tệp UTF-8 không?

> Nên dùng **`new String(bytes, StandardCharsets.UTF_8)`**. Điều này làm rõ quy ước của tệp và tránh ảnh hưởng của sự khác nhau về default charset, phiên bản hoặc cấu hình JVM.

**Câu 5.** Một tệp gốc là ISO-8859-1. Muốn đổi sang UTF-8 thì bước nào phải làm trước?

> **Giải mã byte gốc bằng ISO-8859-1**, sau đó **mã hóa chuỗi Unicode thu được bằng UTF-8**. Không diễn giải trực tiếp byte gốc theo UTF-8 khi chúng không được mã hóa bằng UTF-8.

## Ghi nhớ

Khi **ghi văn bản**, chọn charset để **encode ký tự thành byte**; khi **đọc văn bản**, chọn charset để **decode byte thành ký tự**. Trong code Java mới, ưu tiên **`StandardCharsets.UTF_8`** cho dữ liệu do mình kiểm soát, nhưng luôn tôn trọng encoding thực tế hoặc quy định của định dạng/giao thức. Việc chỉ định charset ở đúng ranh giới byte/văn bản là một phần của hợp đồng dữ liệu và là cách ngăn lỗi hiển thị sai dấu trên nhiều môi trường.

**Tài liệu tham khảo:** [Java SE 17 — `Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html), [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).