# Files.readString(), Files.writeString() và UTF-8 mặc định của API

## 1. Mục tiêu bài học

Trong Java 11 trở lên (bao gồm Java 17+), **java.nio.file.Files** cung cấp hai phương thức thuận tiện để **đọc hoặc ghi toàn bộ nội dung văn bản**:

- **Files.readString(Path)**: đọc toàn bộ file và trả về một **String**, **giải mã UTF-8 theo mặc định của chính API**.
- **Files.writeString(Path, CharSequence, OpenOption...)**: ghi nội dung ký tự ra file bằng **UTF-8 theo mặc định của chính API**.
- Cả hai có overload nhận **Charset** để xử lý file có mã hóa khác UTF-8.

Trọng tâm không chỉ là cú pháp ngắn. Điều cần hiểu là **byte trên đĩa khác với ký tự trong String**, lựa chọn charset ảnh hưởng tính đúng đắn, và phương thức một lần đọc/ghi cả file có giới hạn về bộ nhớ, lỗi I/O và chính sách ghi đè.

> Ghi nhớ: **UTF-8 mặc định của Files.readString/writeString là quy định của hai API này**, không phải suy đoán từ charset mặc định của hệ điều hành, terminal hay JVM.

## 2. Từ byte của file đến String: charset có vai trò gì?

File lưu **byte**. String của Java chứa nội dung ký tự Unicode (biểu diễn bằng các đơn vị mã UTF-16 bên trong ngôn ngữ). Một **charset** định nghĩa cách chuyển giữa hai miền đó:

~~~text
Files.readString(path)
    file bytes ──decode UTF-8──> Java String

Files.writeString(path, text)
    Java CharSequence ──encode UTF-8──> file bytes
~~~

Ví dụ:

| Ký tự trong text | Mã Unicode | Byte UTF-8 (hex) |
| --- | --- | --- |
| **A** | U+0041 | **41** |
| **é** | U+00E9 | **C3 A9** |
| **€** | U+20AC | **E2 82 AC** |
| Xuống dòng LF | U+000A | **0A** |

Một ký tự hiển thị không nhất thiết chiếm một byte. Vì thế **Files.size(path)** trả số byte của file có thể khác **text.length()** (đếm số đơn vị mã UTF-16), và khác cả số ký tự Unicode đầy đủ khi có surrogate pair.

**UTF-8** tương thích ASCII với dải U+0000–U+007F, nhưng ký tự ngoài dải ASCII có thể dùng 2–4 byte. Ví dụ chuỗi **"Café\n€"** gồm **6 đơn vị char Java**, trong khi khi ghi bằng UTF-8 sẽ tạo **9 byte**:

~~~text
43 61 66 C3 A9 0A E2 82 AC
C  a  f  é     LF € 
~~~

Bởi vậy, **không dùng String hoặc readString() để sao chép ảnh, ZIP, PDF hay dữ liệu nhị phân**. Hãy dùng **Files.readAllBytes**, **Files.copy** hoặc các InputStream/OutputStream phù hợp.

## 3. Files.readString(Path): đọc cả file thành văn bản UTF-8

Chữ ký tiêu biểu:

~~~java
public static String readString(Path path) throws IOException
public static String readString(Path path, Charset cs) throws IOException
~~~

Ví dụ:

~~~java
Path path = Path.of("notes.txt");
String text = Files.readString(path);
~~~

Đây là **mảnh mã minh họa**; cần import **java.nio.file.Files**, **java.nio.file.Path**, và xử lý **IOException**. **Path.of(...)** chỉ tạo biểu diễn đường dẫn, không tự tạo file.

**Files.readString(path)** đọc tất cả byte của file, giải mã bằng **StandardCharsets.UTF_8** theo đặc tả của API rồi tạo **String**. Nó không dùng **Charset.defaultCharset()** để tự chọn bộ mã khi không truyền tham số. Tham số **Path** chỉ định file cần đọc; stream tài nguyên bên trong được API xử lý, người gọi không phải tự gọi close cho phương thức này.

**Không có thao tác “tự dò encoding”**: nếu file thực tế là Windows-1252, ISO-8859-1 hoặc UTF-16, việc gọi readString không tham số charset có thể thất bại hoặc cho kết quả không mong đợi. Phải biết hoặc xác định encoding của nguồn theo hợp đồng dữ liệu, sau đó truyền charset tương ứng.

### 3.1. Khi file không phải UTF-8 hợp lệ

Nếu dữ liệu byte không hợp lệ với charset, **Files.readString** có thể ném một lỗi **IOException**, điển hình là **MalformedInputException** hoặc lỗi chuyển mã liên quan. Theo API, dữ liệu sai mã hóa không được coi là văn bản hợp lệ và không đơn giản được thay thế âm thầm bằng ký tự **�**.

Ví dụ file chỉ có byte **E9** (hợp lệ cho ký tự **é** trong ISO-8859-1) nhưng không là một chuỗi UTF-8 hợp lệ đầy đủ:

~~~java
Path legacy = Path.of("legacy.txt");
String text = Files.readString(legacy, StandardCharsets.ISO_8859_1);
~~~

Đây là **mảnh mã minh họa** giả định file trên thực tế được mã hóa ISO-8859-1 và cần import **java.nio.charset.StandardCharsets**. Nếu **không biết** charset thực sự của file, không nên đoán bừa: nhiều bảng mã có thể diễn giải cùng byte thành ký tự khác nhau.

### 3.2. Không đọc dữ liệu lớn mà không cân nhắc bộ nhớ

**Files.readString** đọc **toàn bộ** văn bản vào một String. Khi file lớn, bộ nhớ cần cho byte trung gian, giải mã và String có thể đáng kể; lời gọi có thể ném lỗi do thiếu RAM hoặc giới hạn kích thước được API/JVM áp đặt. API còn lưu ý nó **không dành cho file cực lớn**.

Với log hàng chục GB hoặc nguồn dữ liệu lớn, nên dùng **Files.newBufferedReader(path, charset)**, **Files.lines(path, charset)** hoặc một parser có luồng đọc, xử lý từng dòng/khối và đóng tài nguyên đúng cách. Đừng dùng readString rồi split hàng triệu dòng nếu chỉ cần xử lý tuần tự.

## 4. Files.writeString(Path, CharSequence): ghi UTF-8 mặc định

Các overload quan trọng:

~~~java
public static Path writeString(Path path, CharSequence csq,
                               OpenOption... options) throws IOException

public static Path writeString(Path path, CharSequence csq,
                               Charset cs, OpenOption... options)
                               throws IOException
~~~

Ví dụ:

~~~java
Path path = Path.of("notes.txt");
Files.writeString(path, "Xin chào!\nDòng thứ hai");
~~~

Đây là **mảnh minh họa**; cần import **Files/Path** và xử lý **IOException**. **writeString** nhận **CharSequence**, vì vậy String hoặc loại triển khai CharSequence phù hợp đều dùng được. Nó mã hóa nội dung bằng **UTF-8 khi không truyền Charset** rồi ghi các byte ra file. Phương thức trả về **chính Path được truyền vào**, hữu ích nếu muốn kết hợp thao tác, nhưng không trả số byte được ghi.

### 4.1. Hành vi mặc định: tạo mới hoặc ghi đè nội dung

Khi **không chỉ định OpenOption**, hành vi của **Files.writeString(path, text)** tương đương việc mở file để ghi với các lựa chọn **CREATE**, **TRUNCATE_EXISTING** và **WRITE**:

- Nếu file chưa tồn tại nhưng đường dẫn cha tồn tại và có quyền, phương thức **tạo file mới**.
- Nếu file đã tồn tại, nội dung cũ **bị cắt bỏ (truncate)** rồi nội dung mới được ghi.
- Nếu thư mục cha chưa tồn tại, **writeString không tự tạo thư mục cha**.
- Phương thức không tự chèn dấu xuống dòng trước/sau văn bản; chỉ ghi ký tự có trong **CharSequence**.
- Nếu có lỗi ghi giữa chừng, file đích có thể bị thay đổi một phần; phương thức **không bảo đảm việc thay thế nội dung là giao dịch nguyên tử**.

Do vậy, đừng dùng **writeString** với file quan trọng theo thói quen mà quên chính sách ghi đè. Với file cấu hình cần cập nhật an toàn hơn, cân nhắc ghi vào file tạm, xác nhận dữ liệu, rồi di chuyển vào vị trí cuối cùng theo khả năng hệ thống file.

### 4.2. Chọn rõ chính sách với StandardOpenOption

| Mục đích | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tạo mới nếu chưa có, ghi đè nếu có | **Files.writeString(path, text)** | CREATE + TRUNCATE_EXISTING + WRITE mặc định |
| Ghi tiếp cuối file | **Files.writeString(path, text, CREATE, APPEND)** | Không xóa nội dung trước; tạo file nếu chưa có |
| Chỉ tạo mới, từ chối nếu file tồn tại | **Files.writeString(path, text, CREATE_NEW, WRITE)** | Thích hợp khi không được ghi đè |
| Dùng charset không phải UTF-8 | **Files.writeString(path, text, charset)** | Mã hóa theo charset đã chỉ định |

Trong mã thực tế, các hằng được viết dưới dạng **StandardOpenOption.CREATE**, **StandardOpenOption.APPEND**, **StandardOpenOption.CREATE_NEW**, **StandardOpenOption.WRITE** hoặc dùng static import có chủ ý.

Ví dụ ghi thêm:

~~~java
Files.writeString(
        path, "\nDòng bổ sung",
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

Đây là **mảnh code**, giả định **path** kiểu Path đã có và đã import **java.nio.file.StandardOpenOption**. Trong ví dụ này, dấu xuống dòng **\n** do **lập trình viên chủ động đưa vào**. Nếu bỏ ký tự \n, văn bản mới sẽ nối ngay vào cuối nội dung cũ mà không tự sinh thêm dòng.

**Không kết hợp APPEND với TRUNCATE_EXISTING** để mong “vừa append vừa xóa trước”; hai hành vi mâu thuẫn và có thể bị hệ thống từ chối. Trong ứng dụng ghi từ nhiều tiến trình, một lần append không nhất thiết tương đương một bản ghi nguyên tử cấp ứng dụng: khả năng atomic, thứ tự các lời gọi và đồng bộ cần được thiết kế riêng nếu cần.

## 5. UTF-8 mặc định của API khác charset mặc định của JVM

Một nhầm lẫn phổ biến:

~~~java
Charset systemDefault = Charset.defaultCharset();
String content = Files.readString(path);
~~~

Mảnh code này cần import **java.nio.charset.Charset** và các loại Files/Path. Hai biểu thức **không có quan hệ “readString tự dùng systemDefault”**. **Files.readString(path)** luôn dùng UTF-8 theo hợp đồng phương thức kể từ khi API được giới thiệu.

Điều này có ý nghĩa đặc biệt khi ứng dụng chạy giữa các môi trường hoặc các phiên bản JDK:

- Những API khác, chẳng hạn cách tạo một **FileReader** hoặc **InputStreamReader** mà không chỉ định charset, có thể dựa vào charset mặc định tùy phiên bản JDK và cấu hình.
- Kể từ Java 18 (JEP 400), charset mặc định của Java SE được chuẩn hóa là UTF-8 trong điều kiện tiêu chuẩn, với một số ngoại lệ/cấu hình liên quan. Nhưng **Files.readString/writeString đã xác định UTF-8 theo API từ Java 11**, không phải chỉ từ Java 18.
- **System.out** hoặc terminal hiển thị ký tự với encoding nào là vấn đề khác: file byte có thể đúng UTF-8 dù console hiển thị không đúng.

Để code diễn đạt yêu cầu rõ ràng, có thể dùng overload charset tường minh:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

Kết quả mã hóa tương đương dạng không khai báo charset. Tuy nhiên, truyền charset rõ ràng có lợi khi nhóm cần đọc hợp đồng ngay tại chỗ, hoặc cần đổi sang ISO-8859-1, UTF-16, v.v. Không nên kỳ vọng hai overload sẽ tự dò encoding.

## 6. Ví dụ Java 17+ hoàn chỉnh: đọc UTF-8, kiểm tra byte, append, overwrite và file sai mã hóa

Chương trình dưới đây tạo file trong **thư mục tạm mới**, không động đến file người học. Nó dùng **Unicode escape** trong source code để kết quả không phụ thuộc vào encoding của tệp mã nguồn và không cần in ký tự tiếng Việt ra console.

Lưu vào file **TextFilesDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public class TextFilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("text-files-demo-");
        Path note = directory.resolve("note.txt");
        Path legacy = directory.resolve("legacy.txt");

        try {
            // Café + LF + dấu euro, biểu diễn bằng Unicode escapes.
            String content = "Caf\u00E9\n\u20AC";

            // Không truyền charset: Java Files sử dụng UTF-8.
            Files.writeString(note, content);
            String readBack = Files.readString(note);
            byte[] raw = Files.readAllBytes(note);

            System.out.println("chars=" + readBack.length());
            System.out.println("bytes=" + raw.length);
            System.out.println("hex=" + HexFormat.of().formatHex(raw));
            System.out.println("equal=" + content.equals(
                    Files.readString(note, StandardCharsets.UTF_8)));

            // APPEND: ghi tiếp, không tự thêm ký tự xuống dòng.
            Files.writeString(note, "!",
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
            System.out.println("append=" + HexFormat.of().formatHex(
                    Files.readAllBytes(note)));

            // Không chỉ định option: cắt bỏ nội dung cũ rồi ghi "OK".
            Files.writeString(note, "OK");
            System.out.println("overwrite=" + Files.readString(note));

            // Byte E9 đứng đơn độc: hợp lệ với Latin-1, sai UTF-8.
            Files.write(legacy, new byte[] {(byte) 0xE9});
            try {
                Files.readString(legacy);
                System.out.println("unexpected-success");
            } catch (MalformedInputException ex) {
                System.out.println("invalid-utf8=true");
            }
            System.out.println("latin1=" + Files.readString(
                    legacy, StandardCharsets.ISO_8859_1)
                    .equals("\u00E9"));
        } finally {
            // Chỉ dọn đúng những đường dẫn tạm do chương trình tạo.
            Files.deleteIfExists(legacy);
            Files.deleteIfExists(note);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac TextFilesDemo.java
java TextFilesDemo
~~~

Kết quả trong môi trường filesystem bình thường:

~~~text
chars=6
bytes=9
hex=436166c3a90ae282ac
equal=true
append=436166c3a90ae282ac21
overwrite=OK
invalid-utf8=true
latin1=true
~~~

**Giải thích kết quả:**

1. **Café\n€** có 6 đơn vị char Java, nhưng khi ghi UTF-8 có 9 byte. Byte hex là **43 61 66 C3 A9 0A E2 82 AC**.
2. **readString(note)** và **readString(note, UTF_8)** trả cùng nội dung có thể đối chiếu bằng equals.
3. Khi append **!**, có thêm byte **21**, nên chuỗi hex tăng đúng một byte ở cuối.
4. **writeString(note, "OK")** không truyền option nên **cắt bỏ nội dung cũ**. Đọc lại được **OK**.
5. Byte **E9** không hợp lệ nếu đọc như một văn bản UTF-8 độc lập; vì vậy ví dụ bắt **MalformedInputException**. Chỉ định **ISO_8859_1** mới diễn giải byte này thành **é**.

Các giá trị số, hex và boolean đã được chọn để độc lập với ký tự xuất ra console. Ví dụ **không khẳng định** một file bất kỳ luôn có cùng số byte hoặc cùng encoding. Mọi thao tác file thực tế có thể ném IOException khi thiếu quyền, ổ đĩa lỗi hoặc bị tiến trình khác can thiệp; chương trình chủ động dọn đường dẫn tạm trong **finally**.

## 7. readString/writeString có giữ nguyên dấu xuống dòng không?

Hai API này **không tự chuẩn hóa** CRLF thành LF hoặc ngược lại chỉ vì chúng được gọi. Nếu String chứa **\r\n**, khi ghi với UTF-8 byte kết quả có **0D 0A**; nếu chứa **\n**, byte kết quả là **0A**. Khi readString giải mã nội dung hợp lệ, các ký tự kết thúc dòng được trả về như trong dữ liệu đã giải mã.

~~~java
String text = "A\r\nB\nC\rD";
Files.writeString(path, text, StandardCharsets.UTF_8);
String roundTrip = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(text.equals(roundTrip)); // true
~~~

Đây là **mảnh code minh họa** giả định path đã được tạo, phải xử lý IOException. Lưu ý: khi ứng dụng **thao tác dòng** bằng **BufferedReader.readLine()**, phương thức readLine **bỏ dấu kết thúc dòng** trong String trả về; việc dùng **BufferedWriter.newLine()** có thể tạo quy tắc xuống dòng mới. Sự thay đổi đó thuộc **logic xử lý theo dòng**, không phải tác dụng mặc định của Files.readString/writeString.

**Files.writeString không tự thêm BOM (Byte Order Mark) cho UTF-8.** Nếu nội dung String tự chứa ký tự BOM U+FEFF hoặc file ban đầu chứa BOM, ứng dụng cần quyết định xử lý rõ ràng. Không coi BOM là ký tự “luôn bị tự động phát hiện và loại bỏ”. UTF-8 không bắt buộc BOM để giải mã.

## 8. Đọc mã hóa khác UTF-8: phải chỉ định Charset có cơ sở

Không phải tất cả file text đều là UTF-8. Một số phần mềm cũ có thể dùng ISO-8859-1, Windows-1252 hoặc UTF-16. Khi biết chắc encoding từ metadata, chuẩn giao thức hoặc thỏa thuận với bên tạo file, dùng overload Charset:

~~~java
String latin1Text = Files.readString(
        Path.of("legacy.txt"), StandardCharsets.ISO_8859_1);

Files.writeString(
        Path.of("export.txt"),
        latin1Text,
        StandardCharsets.UTF_8);
~~~

Đây là **mảnh minh họa**, cần import **Files**, **Path**, **StandardCharsets** và xử lý IOException. Nếu bước đọc đúng charset, bước ghi có thể **chuyển văn bản sang UTF-8** mà vẫn giữ ý nghĩa các ký tự đại diện được. Tuy nhiên byte file đích không nhất thiết giống byte file nguồn, vì đây là **chuyển mã văn bản**, không phải sao chép byte.

**Không phải mọi charset đều biểu diễn được mọi ký tự.** Nếu cố ghi ký tự ngoài miền hỗ trợ của charset đích, API có thể báo lỗi chuyển mã thay vì âm thầm mang lại văn bản hoàn chỉnh. Không đơn giản “thử UTF-8, nếu lỗi thì Latin-1” như một thuật toán nhận diện tin cậy: Latin-1 có ánh xạ cho mọi byte, nên một file theo encoding khác có thể bị đọc thành ký tự sai mà không ném lỗi.

Với file chưa rõ encoding, nên xác định nguồn gốc, yêu cầu người cung cấp khai báo charset, hoặc dùng công cụ phát hiện encoding với hiểu biết rõ về giới hạn độ tin cậy của nó.

## 9. Những lưu ý quan trọng về file, lỗi và tài nguyên

### 9.1. Đường dẫn và thư mục cha

**Path.of("data", "note.txt")** là đường dẫn tương đối đến thư mục làm việc của tiến trình. Nếu cha **data** chưa tồn tại, writeString **không tự tạo cha**. Cần tạo trước:

~~~java
Path directory = Path.of("data", "notes");
Files.createDirectories(directory);
Files.writeString(directory.resolve("today.txt"), "Hello UTF-8");
~~~

Đây là mảnh minh họa; với dữ liệu thật cần quyết định chính sách tên file, quyền ghi và trường hợp file đích đã tồn tại. **Files.createDirectories** làm việc ở cấp thư mục, trong khi **Files.writeString** làm việc ở cấp file.

### 9.2. Quyền truy cập và lỗi I/O

Các phương thức **readString** và **writeString** ném **IOException** hoặc các lớp con khi thất bại về I/O, ví dụ file không có, lỗi quyền, file là thư mục, lỗi ổ đĩa, hoặc sai encoding. Trường hợp nào xuất hiện phụ thuộc hệ điều hành và filesystem.

Không nên chỉ bắt **Exception** rồi bỏ qua: điều đó làm ứng dụng tưởng đã lưu thành công dù file có thể không tồn tại hoặc bị cắt dở. Với file cấu hình quan trọng, cần báo lỗi cụ thể và cân nhắc sao lưu/ghi thay thế an toàn.

### 9.3. File không được đọc/ghi nguyên tử toàn bộ

Một lần **Files.readString** không “khóa ảnh chụp” vĩnh viễn của file trước mọi thay đổi đồng thời; nếu tiến trình khác đang sửa file, kết quả phụ thuộc hệ thống và thời điểm đọc. Tương tự **writeString** không phải một phép commit nguyên tử đa byte; nếu lỗi xảy ra sau khi file đã bị truncate hoặc đã ghi một phần, nội dung có thể không hoàn chỉnh.

Nếu cần bảo toàn bản cũ khi cập nhật file, có thể ghi sang file tạm nằm trong cùng filesystem, đóng/sync theo mức độ bền cần thiết rồi thử **Files.move** với chính sách replace/atomic phù hợp. **ATOMIC_MOVE** có thể không được hỗ trợ; cần xử lý **AtomicMoveNotSupportedException**.

### 9.4. Vấn đề kích thước và luồng dữ liệu

Nếu muốn đọc từng dòng thay vì gom vào String:

~~~java
try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý line theo từng dòng.
    }
}
~~~

Đây là **mảnh mã minh họa**, giả định path đã khai báo và nằm trong phương thức xử lý IOException. Chọn **Files.lines(path, charset)** cũng có thể phù hợp, nhưng phải **đóng Stream<String>** khi dùng xong, thường bằng try-with-resources. Cả hai lựa chọn giúp xử lý tuần tự mà không buộc giữ toàn bộ nội dung text trong một String lớn.

Nếu muốn giữ nguyên file nhị phân hoặc chỉ sao chép dữ liệu: **Files.copy(...)** hoặc stream byte là lựa chọn đúng. **readString** không có ý nghĩa với file có byte không hợp lệ theo charset đã chọn.

### 9.5. Vấn đề đồng thời và ghi nối tiếp

**APPEND** chỉ là chính sách ghi của file, không phải cơ chế khóa phân tán hay bảo đảm một bản ghi văn bản có nhiều byte sẽ không xen lẫn với ghi của tiến trình khác. Nếu nhiều thread/process cùng viết, cần chiến lược serialize, file locking hoặc một dịch vụ ghi có tính nhất quán theo nhu cầu.

## 10. Các lỗi thường gặp

1. **Nghĩ Files.readString(path) dùng Charset.defaultCharset().** Sai: overload không truyền charset xác định **UTF-8** theo hợp đồng API.
2. **Nghĩ UTF-8 chỉ có từ Java 18.** Sai: các overload không truyền charset này có mặc định UTF-8 kể từ Java 11; thay đổi JEP 400 là câu chuyện về charset mặc định chung.
3. **Đọc ISO-8859-1 bằng readString không truyền charset.** Có thể ném MalformedInputException hoặc trả text sai; chọn charset theo hợp đồng dữ liệu.
4. **Dùng String/readString để sao chép nhị phân.** Byte không hợp lệ theo charset có thể khiến thao tác lỗi hoặc biến đổi dữ liệu; dùng API byte.
5. **Gọi writeString rồi tưởng file cũ vẫn giữ nguyên.** Mặc định là tạo mới hoặc **truncate** file có sẵn.
6. **Dùng APPEND mà quên tạo dấu xuống dòng.** Files.writeString không tự thêm LF/CRLF; muốn xuống dòng phải đưa ký tự vào text.
7. **Cho rằng writeString tự tạo thư mục cha.** Cần **Files.createDirectories(parent)** trước khi ghi vào thư mục chưa tồn tại.
8. **Tưởng readString tiết kiệm RAM như BufferedReader.readLine.** Nó đọc cả nội dung và trả một String; không phù hợp dữ liệu cực lớn.
9. **Bỏ qua byte BOM và quy tắc newline.** Không mặc định loại/ghi BOM hay chuẩn hóa newline; kiểm tra yêu cầu của hệ thống nhận.
10. **Đọc file bằng charset A, ghi bằng B rồi so byte trực tiếp.** Chuyển mã có thể đổi byte dù ký tự tương đương; cần kiểm tra nội dung theo mục tiêu.
11. **Cho rằng writeString là ghi đè nguyên tử.** Lỗi I/O giữa chừng có thể để lại file dở; cần chiến lược update an toàn nếu dữ liệu quan trọng.
12. **Không quản lý file lớn hoặc dữ liệu không tin cậy.** Cân nhắc giới hạn kích thước, bộ nhớ, quyền truy cập và chính sách khi đọc.
13. **So số byte với String.length() rồi coi khác là lỗi.** UTF-8 là mã hóa biến độ dài, String.length() đo UTF-16 code units.
14. **Dựa vào encoding hiển thị của console để phán xét encoding của file.** Hãy kiểm tra byte (Files.readAllBytes/HexFormat) hoặc dùng một trình xem file có charset được chỉ định.
15. **Quên charset tường minh trong các API khác.** Mặc định UTF-8 ở readString/writeString không chứng minh mọi Reader/Writer hoặc thư viện bên ngoài đều dùng cùng charset.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Java 17 chạy trên hệ thống có default charset không phải UTF-8. **Files.readString(path)** mặc định dùng charset nào?  
**Đáp:** Vẫn là **UTF-8**, do API tự quy định.

**Câu 2.** File UTF-8 chứa **"Café\n€"** có bao nhiêu Java char và byte UTF-8?  
**Đáp:** **6 char** theo String.length() và **9 byte** khi mã hóa UTF-8.

**Câu 3.** Gọi **Files.writeString(path, "ABC")** khi file cũ chứa "LONG TEXT" sẽ ra sao?  
**Đáp:** Theo hành vi mặc định, file bị **truncate** rồi ghi **ABC**, không giữ phần chữ cũ.

**Câu 4.** Muốn tạo file chỉ khi chưa tồn tại, không được ghi đè thì dùng option nào?  
**Đáp:** **StandardOpenOption.CREATE_NEW** cùng chế độ ghi thích hợp, ví dụ **WRITE**.

**Câu 5.** Muốn nối thêm "hello" và tự xuống dòng, có thể chỉ viết **writeString(path, "hello", APPEND)** không?  
**Đáp:** Không tự xuống dòng. Nếu muốn LF, phải ghi thêm ký tự **\n** vào text, và cấu hình CREATE khi file chưa tồn tại nếu cần.

**Câu 6.** Nếu **Files.readString(path)** báo MalformedInputException thì chắc chắn file đã bị hỏng?  
**Đáp:** Không nhất thiết. Có thể file hợp lệ theo **charset khác UTF-8**, chẳng hạn ISO-8859-1, nhưng đang được giải mã sai.

**Câu 7.** Khi file là video hàng GB, nên dùng readString để tiện thao tác không?  
**Đáp:** Không. Video là dữ liệu nhị phân và kích thước lớn; dùng Files.copy hoặc luồng byte theo khối.

**Câu 8.** Nếu muốn đọc log lớn từng dòng, API nào phù hợp hơn?  
**Đáp:** **Files.newBufferedReader(path, charset)** hoặc **Files.lines(path, charset)** có quản lý tài nguyên.

## 12. Tổng kết

**Files.readString(Path)** và **Files.writeString(Path, CharSequence)** là các API tiện lợi để đọc/ghi **toàn bộ văn bản**. Mặc định của chính chúng là **UTF-8**, **không phụ thuộc** vào việc JVM đang báo Charset.defaultCharset() gì. Nếu dữ liệu nguồn/đích dùng charset khác, hãy truyền Charset tường minh và chấp nhận rằng chuyển mã có thể thay biểu diễn byte.

Khi viết file, phải hiểu **writeString mặc định tạo hoặc cắt bỏ nội dung cũ**, còn APPEND/CREATE_NEW là lựa chọn có chủ đích. Khi đọc, cần xử lý **IOException và dữ liệu sai charset**, tránh dồn file cực lớn vào RAM. Các phương thức này dành cho text; việc sao chép byte tuyệt đối hoặc xử lý dữ liệu nhị phân cần API luồng byte/Files.copy tương ứng.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — Files.readString / Files.writeString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): overload UTF-8 mặc định, Charset, OpenOption, IOException.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF_8, ISO_8859_1, UTF_16.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE, TRUNCATE_EXISTING, APPEND, CREATE_NEW.
- [Oracle Java SE 17 — MalformedInputException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html): byte không tạo thành input hợp lệ theo charset.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định của Java SE từ JDK 18, khác với UTF-8 cố định của readString/writeString.
