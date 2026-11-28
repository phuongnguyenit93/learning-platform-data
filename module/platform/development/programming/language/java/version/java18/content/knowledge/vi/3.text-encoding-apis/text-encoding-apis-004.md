# FileReader và FileWriter: khai báo charset, chế độ append và trách nhiệm đóng tài nguyên

## 1. Bài toán: làm việc với file văn bản mà vẫn bảo toàn dữ liệu

Trong module **JAVA_VERSION_JAVA18**, một thay đổi quan trọng còn áp dụng trên các JDK hiện đại là **UTF-8 trở thành charset mặc định theo JEP 400 (Java 18)**. Thay đổi này giúp giảm sự khác biệt giữa các hệ điều hành khi đọc và ghi văn bản. Tuy nhiên, code vẫn phải thể hiện đúng **charset của file**, cách **ghi mới hay nối tiếp**, và **ai chịu trách nhiệm đóng luồng**.

Hai lớp thuận tiện của `java.io` là:

- `FileReader`: đọc byte từ file rồi giải mã thành các ký tự Java (`char`).
- `FileWriter`: nhận ký tự Java, mã hóa thành byte rồi ghi ra file.

Chúng lần lượt kế thừa `InputStreamReader` và `OutputStreamWriter`. Vì vậy, dù là API đọc/ghi **ký tự**, kết quả cuối cùng vẫn phụ thuộc vào **quy tắc chuyển đổi ký tự ↔ byte**. Hai lớp này dành cho **file văn bản**; với ảnh, tệp nén và dữ liệu nhị phân, hãy dùng byte stream hoặc API tương ứng.

Sau bài học, bạn có thể chọn đúng constructor, tránh vô ý cắt ngắn file, nối thêm văn bản an toàn về mặt định dạng, đóng tài nguyên nhất quán, và kiểm chứng byte thực tế trên Java 18+.

## 2. Java 18 và vấn đề charset mặc định

Xét hai lời gọi:

```java
FileReader reader = new FileReader("input.txt");
FileWriter writer = new FileWriter("output.txt");
```

Các constructor trên sử dụng `Charset.defaultCharset()` để giải mã và mã hóa. Trên Java 18+ ở cấu hình thông thường, default charset là **UTF-8** theo **JEP 400 — UTF-8 by Default**. Nhưng có những ngoại lệ cần nhận diện:

1. Một JVM có thể hỗ trợ cấu hình tương thích `-Dfile.encoding=COMPAT`, khiến default charset theo môi trường hệ điều hành, thay vì UTF-8.
2. File có thể do một ứng dụng khác tạo bằng ISO-8859-1, Windows-1252 hoặc một charset đã được quy định từ trước. Java 18 không tự chuyển đổi nội dung file cũ sang UTF-8.
3. Việc một file chứa toàn ASCII không chứng minh nó đang được mã hóa theo UTF-8; nhiều charset có cùng byte đối với các ký tự ASCII thông dụng.

Với file có hợp đồng UTF-8, cách diễn đạt rõ ràng nhất là:

```java
import java.nio.charset.StandardCharsets;

FileReader reader = new FileReader("input.txt", StandardCharsets.UTF_8);
FileWriter writer = new FileWriter("output.txt", StandardCharsets.UTF_8);
```

Các constructor có tham số `Charset` của `FileReader`/`FileWriter` xuất hiện từ **Java 11** và tiếp tục được hỗ trợ trên các JDK hiện đại. Vì thế, đây là giải pháp phù hợp với Java 18+ mà không cần phụ thuộc default charset. Nếu file được quy định bằng một charset khác, sử dụng charset đúng của file ấy thay vì mặc định áp UTF-8.

> Lưu ý: tạo `FileWriter` để ghi một file sẵn có có thể **làm rỗng nội dung cũ ngay khi mở** nếu không bật append. Phần tiếp theo phân biệt rõ các trường hợp.

## 3. So sánh constructor: charset và append

### 3.1. `FileReader` — đọc bằng charset nào?

| Constructor | Cách chọn charset | Hành vi cần biết |
| --- | --- | --- |
| `new FileReader(String name)` | Default charset của JVM | Mở file để đọc từ đầu; không chỉ rõ encoding |
| `new FileReader(File file)` | Default charset của JVM | Tương đương về lựa chọn charset với constructor nhận tên |
| `new FileReader(String name, Charset cs)` | Charset chỉ định | Thích hợp khi file có định dạng đã xác định |
| `new FileReader(File file, Charset cs)` | Charset chỉ định | Thích hợp khi đã có đối tượng `File` |
| `new FileReader(FileDescriptor fd)` | Default charset của JVM | Dùng khi đã có descriptor; phải hiểu quyền sở hữu descriptor |

`FileReader` không có chế độ append vì đây là luồng **đọc**. Muốn đọc một file trong khi ứng dụng khác đang tiếp tục ghi, phải xác định riêng yêu cầu đồng bộ, thời điểm quan sát và xử lý file đang thay đổi.

### 3.2. `FileWriter` — ghi mới hay ghi nối tiếp?

| Constructor | Charset | Chế độ ghi |
| --- | --- | --- |
| `new FileWriter("events.log")` | Default JVM | Ghi từ đầu, làm rỗng file có sẵn |
| `new FileWriter("events.log", true)` | Default JVM | **Append**: ghi byte thêm ở cuối |
| `new FileWriter("events.log", StandardCharsets.UTF_8)` | UTF-8 chỉ định | Ghi từ đầu, làm rỗng file có sẵn |
| `new FileWriter("events.log", StandardCharsets.UTF_8, true)` | UTF-8 chỉ định | Append theo UTF-8 |
| `new FileWriter(file, charset, false)` | Charset chỉ định | Ghi lại từ đầu |
| `new FileWriter(file, charset, true)` | Charset chỉ định | Append vào cuối |

`file` có thể là đối tượng `File`. Các biến thể dùng `String` và `File` đều được hỗ trợ; phiên bản nhận charset với append đã có từ Java 11.

Khi file chưa tồn tại, các constructor ghi file thông thường cố tạo file; nếu không có quyền, đường dẫn trỏ tới thư mục hoặc không thể mở, chúng ném `IOException`. Khi file đã tồn tại:

- **`append == false`** (hoặc bỏ tham số append): nội dung cũ bị cắt ngắn trước khi ghi.
- **`append == true`**: byte mới được ghi ở **cuối file**; dữ liệu cũ vẫn ở phía trước.

Tham số `append` chỉ quyết định vị trí ghi byte. Nó **không tự thêm** khoảng trắng, dấu phẩy, dấu kết thúc dòng, BOM hoặc cấu trúc dữ liệu nào.

### 3.3. Mẫu code nên dùng

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;

// Đọc file UTF-8:
try (FileReader reader = new FileReader(
        "config.txt", StandardCharsets.UTF_8)) {
    // Đọc ký tự qua reader.
}

// Ghi mới hoặc thay toàn bộ nội dung:
try (FileWriter writer = new FileWriter(
        "result.txt", StandardCharsets.UTF_8)) {
    writer.write("Kết quả mới\n");
}

// Ghi nối tiếp vào file:
try (FileWriter writer = new FileWriter(
        "events.log", StandardCharsets.UTF_8, true)) {
    writer.write("2026-11-27,đã hoàn thành\n");
}
```

Đoạn code khai báo charset ở cả hai chiều và sử dụng **try-with-resources** để đóng luồng. Trước khi triển khai, xác nhận chế độ ghi mới hay append là yêu cầu nghiệp vụ thật sự.

## 4. Ví dụ chạy được: ghi mới, append, đọc lại và kiểm tra byte

Chương trình dưới đây tự tạo một file tạm, ghi hai dòng UTF-8 rồi đọc lại. File tạm được xóa ở `finally` để không để lại dữ liệu sau khi chạy.

```java
import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class FileCharsetDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("charset-demo-", ".txt");

        try {
            // Lần mở đầu tiên: thay thế nội dung file bằng một dòng UTF-8.
            try (FileWriter writer = new FileWriter(
                    path.toFile(), StandardCharsets.UTF_8)) {
                writer.write("Cà phê\n");
            }

            // Lần mở thứ hai: nối thêm byte vào cuối file.
            try (FileWriter writer = new FileWriter(
                    path.toFile(), StandardCharsets.UTF_8, true)) {
                writer.write("Tiếng Việt 🌍\n");
            }

            // Chỉ đọc sau khi writer đã được đóng.
            try (BufferedReader reader = new BufferedReader(
                    new FileReader(path.toFile(), StandardCharsets.UTF_8))) {
                System.out.println(reader.readLine()); // Cà phê
                System.out.println(reader.readLine()); // Tiếng Việt 🌍
                System.out.println(reader.readLine()); // null
            }

            byte[] bytes = Files.readAllBytes(path);
            System.out.println(HexFormat.of().formatHex(bytes));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Chạy với JDK 18+:

```text
javac FileCharsetDemo.java
java FileCharsetDemo
```

Kết quả từ `readLine()` gồm hai dòng mong đợi; `readLine()` trả `null` khi hết dữ liệu. Dòng hex giúp xác minh **byte đã thực sự được ghi** theo UTF-8; ví dụ `à` được mã hóa thành `C3 A0`, còn `🌍` thành `F0 9F 8C 8D`.

`Files.createTempFile` tạo file rỗng. `new FileWriter(..., UTF_8)` mở file đó ở chế độ ghi mới, và `new FileWriter(..., UTF_8, true)` bổ sung byte. Nếu bỏ `true` ở lần mở thứ hai, dòng đầu sẽ bị mất vì file bị làm rỗng khi mở lại.

**Vì sao dùng `BufferedReader`?** `FileReader` đọc từng ký tự hoặc khối ký tự. Khi xử lý theo dòng, `BufferedReader.readLine()` tiện hơn, nhưng nó **không giữ ký tự kết thúc dòng**. Nếu cần giữ nguyên từng byte hoặc đúng loại newline, hãy chọn phương pháp đọc/ghi phù hợp thay vì khôi phục file bằng `readLine()` và `newLine()`.

## 5. Append: chỉ nối byte, không bảo đảm cấu trúc văn bản

Một sai sót thường gặp:

```java
try (FileWriter writer = new FileWriter(
        "audit.log", StandardCharsets.UTF_8, true)) {
    writer.write("Bản ghi mới");
}
```

Giả sử file hiện tại kết thúc bằng `"Bản ghi cũ"` mà **không có newline**, kết quả sau append sẽ thành `"Bản ghi cũBản ghi mới"`. FileWriter không nhận biết định dạng bản ghi.

Với định dạng nhật ký mà mỗi record nằm trên một dòng, hãy tự quy định dấu phân cách:

```java
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;

String record = "INFO|đăng nhập thành công";

try (FileWriter writer = new FileWriter(
        "audit.log", StandardCharsets.UTF_8, true)) {
    writer.write(record);
    writer.write('\n'); // Định dạng log quy định LF.
}
```

`'\n'` tạo newline LF nhất quán giữa môi trường. Nếu định dạng file yêu cầu separator theo hệ điều hành, dùng `System.lineSeparator()`. Nếu nối tiếp file hiện có mà không biết nó kết thúc bằng newline hay chưa, cần kiểm tra/chuẩn hóa định dạng trước khi append.

Một số giới hạn quan trọng khác:

- **Charset phải nhất quán.** Nếu nội dung cũ là ISO-8859-1 mà phần append mới là UTF-8, file có thể chứa hai cách mã hóa khác nhau; một lần `FileReader` đơn lẻ không thể giải mã đúng toàn bộ theo cùng một charset.
- **Không tự đồng bộ nhiều người ghi.** Hai tiến trình hoặc hai luồng cùng append không được `FileWriter` bảo đảm mỗi record là một thao tác nguyên tử. Việc append vào vị trí cuối, ranh giới record và thứ tự giữa các writer phụ thuộc cơ chế hệ thống file và cách phối hợp. Khi cần bảo đảm, thiết kế một writer trung tâm hoặc cơ chế đồng bộ/file lock phù hợp.
- **Không dùng append để giả định định dạng có trạng thái.** Với một số charset có trạng thái hoặc phát byte đánh dấu như BOM, việc khởi tạo một encoder mới cho mỗi lần append có thể khiến file cuối cùng không đúng định dạng mong muốn. UTF-8 thông thường tránh phần lớn vấn đề BOM, nhưng vẫn phải bảo đảm file cũ hoàn chỉnh và cùng charset.
- **Không dùng append để cập nhật record ở giữa file.** `FileWriter` chỉ hỗ trợ luồng ghi theo thứ tự, không phải công cụ chỉnh sửa ngẫu nhiên theo vị trí.

Nếu file là nguồn dữ liệu quan trọng, hãy cân nhắc định dạng record có dấu phân cách rõ ràng, chiến lược ghi an toàn và phương án phục hồi khi tiến trình bị ngắt giữa một lần ghi.

## 6. Trách nhiệm đóng tài nguyên: try-with-resources

### 6.1. Vì sao không thể chỉ gọi `write()` rồi bỏ qua `close()`?

`FileWriter` thừa hưởng cơ chế chuyển mã và đệm byte từ `OutputStreamWriter`. Sau một lệnh `write()`, dữ liệu có thể vẫn nằm trong bộ đệm. Nếu chương trình kết thúc mà không `flush()`/`close()`, dữ liệu có thể thiếu hoặc việc giải phóng file handle bị trì hoãn.

Cách nên dùng:

```java
try (FileWriter writer = new FileWriter(
        "report.txt", StandardCharsets.UTF_8)) {
    writer.write("Báo cáo hoàn tất\n");
} // close() tự động, kể cả khi write() phát sinh ngoại lệ.
```

`try-with-resources` bảo đảm gọi `close()` khi thoát khối, kể cả khi có lỗi trong thân khối. Nếu cả phần xử lý và việc đóng tài nguyên cùng ném ngoại lệ, Java giữ ngoại lệ chính và gắn ngoại lệ phát sinh khi đóng vào danh sách **suppressed exceptions**, giúp chẩn đoán rõ nguyên nhân.

Với `FileReader`, `close()` cũng cần thiết để trả handle về hệ thống:

```java
try (FileReader reader = new FileReader(
        "report.txt", StandardCharsets.UTF_8)) {
    char[] buffer = new char[4096];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Xử lý buffer[0..count-1], KHÔNG đọc quá count.
    }
}
```

### 6.2. `flush()` khác `close()` như thế nào?

| Thao tác | Tác dụng | Những gì không bảo đảm |
| --- | --- | --- |
| `writer.write(...)` | Ghi ký tự vào luồng chuyển mã | Không bảo đảm mọi byte đã ra khỏi bộ đệm |
| `writer.flush()` | Đẩy dữ liệu đã đệm xuống luồng bên dưới | Không đồng nghĩa dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ |
| `writer.close()` | Hoàn tất xuất dữ liệu, đóng writer và tài nguyên bên dưới | Không biến thao tác ghi thành transaction nguyên tử |
| `reader.close()` | Giải phóng tài nguyên đọc | Không thay đổi encoding của file đã đọc |

Không cần gọi `flush()` trước `close()` khi dùng try-with-resources thông thường; `close()` đã hoàn tất công việc đóng luồng. Chỉ dùng `flush()` giữa chừng khi luồng phải tiếp tục mở mà bên ngoài cần nhìn thấy dữ liệu đã ghi.

**Lưu ý:** `flush()` ở tầng Java I/O không thay thế biện pháp bảo đảm dữ liệu trên ổ đĩa như `FileChannel.force(...)` khi hệ thống yêu cầu độ bền lưu trữ đặc biệt.

### 6.3. Ai sở hữu luồng?

Nếu chính phương thức mở `FileReader` hoặc `FileWriter`, phương thức đó thường **sở hữu** và đóng tài nguyên.

Nếu reader/writer được truyền từ nơi khác, nên thống nhất người gọi hay người nhận chịu trách nhiệm đóng. Đóng một wrapper như `BufferedReader` cũng đóng reader bên dưới; với `BufferedWriter`, việc đóng wrapper đóng cả `FileWriter` bên dưới:

```java
import java.io.BufferedWriter;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;

try (BufferedWriter writer = new BufferedWriter(
        new FileWriter("report.txt", StandardCharsets.UTF_8))) {
    writer.write("Dòng 1");
    writer.newLine();
    writer.write("Dòng 2");
}
```

Trong ví dụ này, chỉ khai báo `BufferedWriter` làm resource là đủ, vì `close()` của nó đóng `FileWriter` bên trong.

## 7. Lựa chọn giữa FileReader/FileWriter và Files API

Trên JDK hiện đại, `java.nio.file.Files` thường thuận tiện hơn khi đã dùng đối tượng `Path`.

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Xử lý ký tự từng khối từ file | `FileReader(file, charset)` |
| Đọc file văn bản theo dòng | `BufferedReader(new FileReader(file, charset))` hoặc `Files.newBufferedReader(path, charset)` |
| Ghi một lượng văn bản vừa phải | `FileWriter(file, charset)` hoặc `Files.writeString(path, text, charset)` |
| Ghi nhiều dòng lớn | `BufferedWriter(new FileWriter(...))` hoặc `Files.newBufferedWriter(path, charset)` |
| Mở file với lựa chọn `CREATE_NEW`, `APPEND`, `TRUNCATE_EXISTING` rõ ràng | `Files.newBufferedWriter(path, charset, OpenOption...)` |
| Xử lý byte nhị phân | `InputStream`, `OutputStream`, `Files` byte APIs |

### 7.1. Ghi append với `Files.newBufferedWriter`

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path log = Path.of("events.log");

try (var writer = Files.newBufferedWriter(
        log,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    writer.write("Sự kiện mới");
    writer.newLine();
}
```

`CREATE` tạo file khi chưa tồn tại; `APPEND` ghi nối vào cuối. Khi gọi `Files.newBufferedWriter(path, charset)` **không truyền options**, API mặc định tương đương `CREATE`, `TRUNCATE_EXISTING`, `WRITE`: file tồn tại sẽ bị làm rỗng trước khi ghi.

Không kết hợp `APPEND` với `TRUNCATE_EXISTING` cho cùng luồng ghi; đây là yêu cầu mâu thuẫn.

### 7.2. Khác biệt quan trọng về default charset

`Files.readString(path)`, `Files.writeString(path, text)`, `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path)` **mặc định dùng UTF-8 theo hợp đồng riêng của API**. Chúng không tự suy charset từ `Charset.defaultCharset()` giống constructor `FileReader(file)` và `FileWriter(file)`.

Dù vậy, với file có charset khác UTF-8, vẫn phải truyền charset cụ thể. Và `Files.writeString` không tự bảo đảm append: muốn nối tiếp, cần truyền `StandardOpenOption.APPEND` cùng các tùy chọn mở cần thiết.

### 7.3. Phân biệt chiến lược xử lý byte lỗi

Không nên mặc định cho rằng các API đọc file có chính sách xử lý byte lỗi giống nhau. `Files.newBufferedReader(path, charset)` **ném `IOException`** khi gặp chuỗi byte sai định dạng hoặc không thể ánh xạ, trong khi `FileReader(file, charset)` qua `InputStreamReader` thường **thay thế** byte lỗi bằng ký tự thay thế mặc định.

Nếu yêu cầu nhập dữ liệu phải bắt lỗi nghiêm ngặt, chọn API báo lỗi hoặc cấu hình `CharsetDecoder` với `CodingErrorAction.REPORT`:

```java
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("incoming.txt");
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var reader = new InputStreamReader(
        Files.newInputStream(source), decoder)) {
    char[] buffer = new char[1024];
    while (reader.read(buffer) != -1) {
        // Xử lý ký tự đã kiểm chứng theo UTF-8.
    }
}
```

Tương tự, khi việc ghi không được phép làm mất ký tự do charset không biểu diễn được, cân nhắc `Files.newBufferedWriter(path, charset)` vì API này báo lỗi mã hóa không hợp lệ, hoặc chủ động dùng `CharsetEncoder` cấu hình `CodingErrorAction.REPORT`. Trường hợp đọc/ghi dữ liệu quan trọng cần thiết kế quy trình xử lý ngoại lệ và tránh để lại file mới được ghi dở.

## 8. Lỗi thường gặp và tình huống thực tế

### Tình huống A: file tiếng Việt đọc đúng trên máy này nhưng lỗi ở máy khác

```java
// Khó dự đoán nếu chương trình chạy với các default charset khác nhau.
try (FileReader reader = new FileReader("catalog.txt")) {
    // ...
}

// Thể hiện rõ hợp đồng của file:
try (FileReader reader = new FileReader(
        "catalog.txt", StandardCharsets.UTF_8)) {
    // ...
}
```

Nếu file thực sự được tạo bằng Windows-1252 hoặc một charset khác, không tự đổi sang UTF-8. Trước hết cần xác minh nguồn tạo file và định dạng được thỏa thuận.

### Tình huống B: ghi thêm một dòng làm mất mọi dòng cũ

```java
// Mở mặc định: cắt ngắn file cũ.
new FileWriter("audit.log", StandardCharsets.UTF_8);

// Mở append: giữ nội dung file cũ và nối byte ở cuối.
new FileWriter("audit.log", StandardCharsets.UTF_8, true);
```

Các dòng trên chỉ minh họa **sự khác biệt constructor**. Trong ứng dụng thực, phải đóng ngay writer bằng try-with-resources thay vì để đối tượng được tạo mà không đóng.

### Tình huống C: append xong nhưng nội dung bị dính dòng hoặc sai charset

Nguyên nhân có thể là file gốc không kết thúc bằng newline, code không ghi separator hoặc file gốc được mã hóa bằng charset khác. Kiểm tra những byte cuối file và thống nhất định dạng record; thay `append` một cách ngẫu nhiên không giải quyết bản chất lỗi.

### Tình huống D: đọc được ký tự `�` nhưng không báo lỗi

Có thể có byte không hợp lệ trong charset được chọn. Khi cần kiểm tra dữ liệu chặt chẽ, dùng `Files.newBufferedReader(path, charset)` hoặc decoder có `CodingErrorAction.REPORT` để nhận lỗi thay vì âm thầm thay thế.

### Tình huống E: ghi được một phần trước khi phát sinh ngoại lệ

Thao tác ghi file thông thường không phải transaction. Nếu đang thay thế một cấu hình quan trọng, có thể cân nhắc **ghi file tạm, kiểm tra/đóng xong rồi thay thế đích** bằng thao tác di chuyển phù hợp hệ thống file; việc di chuyển nguyên tử có điều kiện hỗ trợ riêng. Không coi `FileWriter` hoặc `flush()` là bảo đảm cập nhật toàn bộ hoặc không cập nhật.

## 9. Danh sách kiểm tra khi rà soát code Java 18+

Khi rà soát các vị trí đọc/ghi file văn bản:

1. **Xác định nguồn dữ liệu**: file do ai tạo, charset nào được quy định, có file lịch sử chưa chuyển đổi không?
2. **Xem constructor**: `FileReader(file)` và `FileWriter(file)` có đang dựa vào JVM default charset không? Nếu có hợp đồng charset, truyền `StandardCharsets.UTF_8` hoặc charset phù hợp.
3. **Xem chế độ ghi**: có chủ ý thay file cũ hay nối tiếp? Với append, phải xác định ranh giới record và tránh trộn charset.
4. **Kiểm tra vòng đời**: file writer/reader có được đặt trong try-with-resources không? Có wrapper nào bị đóng sớm hay có handle nào bị rò rỉ không?
5. **Xử lý lỗi**: khi mở file, chuyển mã, flush hoặc close phát sinh `IOException`, ứng dụng cần ghi nhận/khôi phục thế nào?
6. **Kiểm tra byte thật**: so sánh kết quả UTF-8 theo hex, không chỉ quan sát terminal. Thử các chuỗi như `café`, `Tiếng Việt`, `🌍`.
7. **Kiểm tra hành vi đặc biệt**: file trống, file chưa tồn tại, file thiếu newline cuối, file lớn, charset khác UTF-8 và nội dung byte hỏng.

### Kiểm thử tối thiểu: append không xóa nội dung cũ

```java
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Files.createTempFile("append-check-", ".txt");
try {
    try (FileWriter writer = new FileWriter(file.toFile(), StandardCharsets.UTF_8)) {
        writer.write("dòng 1\n");
    }
    try (FileWriter writer = new FileWriter(file.toFile(), StandardCharsets.UTF_8, true)) {
        writer.write("dòng 2\n");
    }

    String actual = Files.readString(file, StandardCharsets.UTF_8);
    String expected = "dòng 1\ndòng 2\n";
    if (!expected.equals(actual)) {
        throw new AssertionError("Append phải giữ nguyên dòng trước");
    }
} finally {
    Files.deleteIfExists(file);
}
```

Bài kiểm tra xác nhận cả **chế độ append** lẫn nội dung Unicode đọc lại, và không phụ thuộc default charset của JVM. Với hệ thống thực, bổ sung kiểm tra xử lý exception và cấu trúc log nếu nhiều tiến trình cùng ghi.

## 10. Một số nhận định dễ nhầm

- **“Java 18 dùng UTF-8 mặc định nên không cần tham số `Charset`.”** Chỉ đúng rằng cấu hình thông thường dùng UTF-8; file ngoài hệ thống hoặc cấu hình tương thích có thể khác. Truyền charset theo định dạng file giúp hành vi ổn định.
- **“`FileWriter(file, true)` đồng nghĩa append UTF-8.”** Sai. Constructor này vẫn dùng charset mặc định của JVM. Muốn append UTF-8 tường minh, dùng `FileWriter(file, StandardCharsets.UTF_8, true)`.
- **“Không gọi `close()` cũng không sao vì đã gọi `write()`.”** Sai. Có thể còn dữ liệu đệm và file handle chưa được giải phóng.
- **“`flush()` giống `close()`.”** Sai. `flush()` đẩy dữ liệu đệm nhưng để luồng mở; `close()` đóng tài nguyên.
- **“Append sẽ tự ghi newline và bảo đảm nguyên tử mỗi record.”** Sai. Phải tự quy định dấu phân cách và phối hợp nhiều writer nếu cần.
- **“FileReader dùng UTF-8 mà không ném lỗi tức là mọi byte đều đúng.”** Sai. Với chính sách thay thế byte lỗi, nội dung có thể đã bị thay ký tự.
- **“`Files.readString(path)` giống `FileReader(file)` về charset mặc định.”** Sai. `Files.readString(path)` có hợp đồng UTF-8, trong khi `FileReader(file)` dùng default charset của JVM.

## 11. Tài liệu chính thức

- [JEP 400 — UTF-8 by Default (OpenJDK)](https://openjdk.org/jeps/400): thay đổi charset mặc định từ Java 18, các điểm tương thích cần lưu ý.
- [FileReader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/FileReader.html): các constructor, lựa chọn charset và hành vi đọc.
- [FileWriter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/FileWriter.html): các constructor hỗ trợ charset và append, ngoại lệ khi mở file.
- [Files — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `newBufferedReader`, `newBufferedWriter`, `readString`, `writeString` và các `OpenOption`.
- [CharsetDecoder — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [CharsetEncoder — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát lỗi trong chuyển đổi byte ↔ ký tự.
