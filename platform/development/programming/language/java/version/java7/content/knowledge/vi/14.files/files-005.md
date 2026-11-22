# Mở InputStream, OutputStream, Reader và Writer bằng `java.nio.file.Files`

## 1. Bài toán và mục tiêu

Khi làm việc với tệp trong Java, bạn cần chọn đúng **dạng dữ liệu** và **chế độ mở tệp**. Một ảnh PNG, tệp ZIP hoặc dữ liệu nhị phân phải được đọc/ghi theo **byte**. Một văn bản tiếng Việt cần được chuyển giữa **byte và ký tự** bằng một **charset rõ ràng**, thường là UTF-8. Nếu mở file ghi sai chế độ, dữ liệu đang có có thể bị xóa ngay lúc mở, dù chương trình chưa gọi `write()`.

Từ **Java 7**, class `java.nio.file.Files` cung cấp bốn phương thức cốt lõi:

~~~java
Files.newInputStream(path, options);
Files.newOutputStream(path, options);
Files.newBufferedReader(path, charset);
Files.newBufferedWriter(path, charset, options);
~~~

Đây là **các chữ ký sử dụng minh họa**, không phải chương trình độc lập: `path` là `java.nio.file.Path`, `charset` là `java.nio.charset.Charset` và `options` là danh sách `OpenOption` nếu cần. Với các trường hợp đơn giản, có thể bỏ tham số `options` để dùng chế độ mặc định. Đối với Reader/Writer, từ **Java 8** còn có overload không cần truyền charset, mặc định UTF-8 theo hợp đồng API. Ví dụ trong bài sử dụng Java 17+ nhưng chỉ giải thích những cơ chế hiện vẫn áp dụng.

Sau bài học, bạn có thể:

1. Chọn **InputStream/OutputStream** cho byte, **BufferedReader/BufferedWriter** cho văn bản; không nhầm hai tầng.
2. Hiểu mặc định mở file đọc hoặc ghi, đặc biệt **CREATE + TRUNCATE_EXISTING + WRITE** khi không chỉ định options của OutputStream/BufferedWriter.
3. Dùng `StandardOpenOption.CREATE_NEW`, `APPEND`, `CREATE`, `TRUNCATE_EXISTING` và `READ/WRITE` đúng ngữ nghĩa, không ghi đè nhầm.
4. Sử dụng **try-with-resources** (có từ Java 7) để đóng stream, reader và writer kể cả khi phát sinh lỗi.
5. Dùng `StandardCharsets.UTF_8` khi đọc/ghi tiếng Việt, nhận biết lỗi mã hóa và phân biệt Reader/Writer với công cụ xử lý byte thô.
6. Đọc/ghi theo buffer để xử lý file lớn mà không nạp toàn bộ file vào bộ nhớ.
7. Xử lý tệp không tồn tại, thư mục cha chưa có, đường dẫn và lỗi quyền truy cập.
8. Hiểu cách ghép `InputStreamReader`/`OutputStreamWriter` khi cần chuyển byte stream thành character stream.
9. Dự đoán chính xác stdout trong các ví dụ Java 17+ đã biên dịch/chạy và sử dụng checklist cho mã sản phẩm.

**Nguyên tắc xuyên suốt:** Chọn đúng **byte hay text**, đúng **charset**, đúng **open options**, và **đóng tài nguyên** đúng hạn. Không vì cùng trả về “stream” mà xem mọi phương thức có thể hoán đổi với nhau.

## 2. Bốn phương thức tương ứng với bốn mục đích

| API | Kết quả | Dữ liệu làm việc | Buffer mặc định? | Chế độ thường dùng |
| --- | --- | --- | --- | --- |
| `Files.newInputStream(Path, OpenOption...)` | `InputStream` | **Byte** đầu vào | **Không**, theo Javadoc; cần wrapper khi muốn buffering | Đọc file từ đầu |
| `Files.newOutputStream(Path, OpenOption...)` | `OutputStream` | **Byte** đầu ra | **Không**, theo Javadoc | Tạo/ghi đè file, ghi nối thêm |
| `Files.newBufferedReader(Path, Charset)` | `BufferedReader` | **Ký tự/văn bản** | **Có**, buffer đọc ký tự | Đọc từng dòng UTF-8 |
| `Files.newBufferedWriter(Path, Charset, OpenOption...)` | `BufferedWriter` | **Ký tự/văn bản** | **Có**, buffer ghi ký tự | Ghi file văn bản UTF-8 |

### 2.1. Luồng byte và luồng ký tự

- `InputStream.read()` trả một **int** biểu diễn byte giá trị `0..255`, hoặc **`-1`** khi hết dữ liệu. Không lấy `0xFF` (255) làm dấu hiệu kết thúc.
- `OutputStream.write(int)` ghi **8 bit thấp** của số nguyên ra luồng; `write(byte[])` ghi dãy byte.
- `Reader.read()` trả một **UTF-16 code unit** dưới dạng int hoặc `-1` khi hết ký tự. Nó **không trực tiếp** hứa trả một Unicode code point hoàn chỉnh đối với ký tự bổ sung cần surrogate pair.
- `Writer.write(...)` nhận ký tự/chuỗi; lớp chuyển charset ở dưới sẽ **mã hóa** thành byte để ghi file.
- `BufferedReader.readLine()` đọc một dòng logic và **bỏ dấu kết thúc dòng**; nếu EOF và không còn dữ liệu để đọc, trả **`null`**.
- `BufferedWriter.write(...)` **không tự xuống dòng**. Gọi `newLine()` khi muốn separator theo nền tảng, hoặc ghi `'\n'` khi format yêu cầu LF cố định.

Ví dụ, ảnh `.png`, file `.zip`, chữ ký số hoặc byte fixture được kiểm tra theo byte: dùng `InputStream`/`OutputStream`. Văn bản UTF-8 cần đọc theo dòng hoặc ghi String: dùng `BufferedReader`/`BufferedWriter`. **Đuôi file không đủ để quyết định** nếu nội dung thực tế không đúng với giả định.

### 2.2. Cách mở theo `Path`

`Files` nhận `Path`, thay vì yêu cầu bạn nối đường dẫn theo chuỗi:

~~~java
Path root = Path.of("data");
Path target = root.resolve("notes.txt");
~~~

Đây là đoạn trong một phương thức với `import java.nio.file.Path;`. `Path.of` là API Java 11+; với target Java 7 có thể dùng `Paths.get("data", "notes.txt")`. Không hardcode separator `"\\\\"` theo Windows hoặc `"/"` theo Unix khi không cần. `resolve` để filesystem provider xử lý cú pháp đường dẫn.

**File là tài nguyên ngoài tiến trình:** Đường dẫn hợp lệ về cú pháp không đảm bảo file tồn tại, có quyền mở, không bị thay thế trong lúc thao tác hoặc đủ dung lượng. Phần mở/đọc/ghi có thể ném `IOException`. Do đó mọi chương trình mẫu thao tác file đều dùng `throws Exception` trong `main` cho dễ quan sát, còn code sản phẩm nên xử lý/lan truyền lỗi phù hợp với hợp đồng tầng ứng dụng.

## 3. Mở `InputStream` — đọc byte, không tự giải mã văn bản

Cách dùng điển hình:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = in.read(buffer)) != -1) {
        // Chỉ xử lý buffer[0..count), không xử lý cả buffer.length.
    }
}
~~~

Đây là đoạn trong một phương thức có `path` kiểu `Path` và import `Files`/`InputStream`. `read(buffer)` trả số byte thực đọc được, không nhất thiết bằng kích thước buffer; `-1` đánh dấu EOF. Khi đọc từng khối, luôn dùng đúng **`count`** cho lần đọc ấy.

Theo Javadoc hiện hành của `Files.newInputStream`:

- Mặc định khi không truyền option là **`READ`**.
- Việc đọc bắt đầu **ở đầu file**.
- Luồng trả về **không buffered** và không bắt buộc hỗ trợ `mark()`/`reset()`.
- API quy định stream an toàn cho truy cập từ nhiều thread, nhưng điều đó **không có nghĩa** mỗi thread có vị trí đọc độc lập. Nhiều thread cùng đọc một stream vẫn chia sẻ trạng thái đọc; nếu mỗi tác vụ cần đọc toàn bộ file từ đầu, hãy mở stream riêng.
- Nếu cần tối ưu nhiều lần đọc nhỏ, có thể bọc `BufferedInputStream`, nhưng với `read(byte[])` theo block hợp lý, không nhất thiết thêm lớp buffer một cách cơ học.
- Việc mở có thể thất bại vì file không tồn tại, quyền bị từ chối, tùy filesystem.

### 3.1. Chương trình Java 17+: đọc byte `0xFF` khác EOF `-1`

Tạo file `BinaryOpenDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class BinaryOpenDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("binary-demo-", ".bin");
        byte[] payload = {0, 65, (byte) 0xFF, 10};

        try {
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write(payload);
            }

            ByteArrayOutputStream data = new ByteArrayOutputStream();
            try (InputStream in = Files.newInputStream(file)) {
                byte[] buffer = new byte[2];
                int count;
                while ((count = in.read(buffer)) != -1) {
                    data.write(buffer, 0, count);
                }
            }

            byte[] restored = data.toByteArray();
            System.out.println("sameBytes=" +
                    Arrays.equals(payload, restored));
            System.out.println("byteCount=" + restored.length);
            System.out.println("unsignedFF=" + (restored[2] & 0xFF));

            try (InputStream in = Files.newInputStream(file)) {
                while (in.read() != -1) { }
                System.out.println("eof=" + in.read());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 BinaryOpenDemo.java
java BinaryOpenDemo
~~~

Stdout đã kiểm chứng:

~~~text
sameBytes=true
byteCount=4
unsignedFF=255
eof=-1
~~~

**Giải thích:**

1. `newOutputStream(file)` ghi đúng bốn byte, kể cả `(byte)0xFF` vốn có biểu diễn `-1` nếu nhìn như `byte` signed trong Java.
2. `InputStream.read()` vẫn phân biệt **byte 0xFF trả int 255** với **EOF trả int -1**.
3. `read(buffer)` không đảm bảo đọc đầy buffer trong một lần; vòng lặp gom đúng `count` byte.
4. So sánh byte bằng `Arrays.equals`, **không** ép file nhị phân thành String rồi so sánh.
5. `ByteArrayOutputStream` chỉ có ý nghĩa minh họa cho **file rất nhỏ**; trong xử lý file lớn, nên truyền buffer trực tiếp tới đích để không giữ toàn bộ file trong RAM.
6. Khối try-with-resources đóng OutputStream **trước khi** mở InputStream để đọc dữ liệu sau khi ghi xong.

Nguồn: [Files.newInputStream Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newInputStream(java.nio.file.Path,java.nio.file.OpenOption...)) và [InputStream Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html).

## 4. Mở `OutputStream` — ghi byte và cẩn thận việc ghi đè

Cú pháp:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(bytes);
}
~~~

Đây là đoạn minh họa cần `path`, `bytes` và import thích hợp. Khi **không cung cấp options**, `Files.newOutputStream(path)` hoạt động như thể có:

~~~java
StandardOpenOption.CREATE
StandardOpenOption.TRUNCATE_EXISTING
StandardOpenOption.WRITE
~~~

Ba dòng này là **ba tên option**, không phải một chương trình Java độc lập.

Ý nghĩa:

- **CREATE:** nếu chưa có file, tạo file; nếu đã có, mở file hiện có.
- **TRUNCATE_EXISTING:** nếu file thường đã tồn tại và mở để ghi, rút ngắn về **0 byte ngay lúc mở**.
- **WRITE:** mở để ghi.

**Hệ quả quan trọng:** Nếu một file đang chứa dữ liệu, chỉ gọi `Files.newOutputStream(path)` đã có thể **xóa nội dung cũ**, trước cả lần `write` đầu tiên. `newBufferedWriter` với charset và không có options cũng có mặc định tương tự.

Vì vậy không được dùng phương thức mặc định để “thêm vài byte cuối file” nếu mục tiêu là append. Cần truyền `APPEND` và cân nhắc `CREATE` nếu phải tạo file mới khi nó chưa tồn tại.

Luồng `OutputStream` do Files mở cũng **không buffered**; có thể bọc `BufferedOutputStream` để giảm số lần ghi nhỏ. Nếu dùng wrapper, try-with-resources đóng wrapper để nó flush và đóng stream nền, không đóng mỗi stream nền mà bỏ sót writer/buffer đang giữ dữ liệu.

### 4.1. `flush()` và `close()` có nghĩa gì?

- Với BufferedWriter hoặc BufferedOutputStream, `flush()` đẩy dữ liệu còn giữ trong buffer xuống tầng dưới.
- `close()` giải phóng tài nguyên; đối với buffer writer/stream, quá trình đóng cũng flush dữ liệu còn lưu và **có thể ném IOException**.
- Flush/close không tự đồng nghĩa dữ liệu đã **durable** trên thiết bị lưu trữ trong mọi điều kiện. Nếu sản phẩm yêu cầu bảo đảm chịu mất điện, cần thiết kế chính sách đồng bộ dữ liệu/metadata phù hợp filesystem và API.
- Không giả định `close()` sẽ không bao giờ lỗi chỉ vì mọi lệnh `write()` trước đó chạy thành công.

## 5. Mở `BufferedReader` — đọc văn bản bằng charset rõ ràng

Dùng khi muốn **ký tự hoặc dòng**, không phải byte. Mẫu Java 17+:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Mỗi line không chứa dấu kết thúc dòng.
    }
}
~~~

Đây là đoạn minh họa với `path` kiểu `Path`, import `BufferedReader`, `Files` và `StandardCharsets`.

- `newBufferedReader` trả **BufferedReader** đã có bộ đệm đọc ký tự; không cần bọc thêm một BufferedReader chỉ để lặp dòng.
- `StandardCharsets.UTF_8` xác định cách biến các byte file thành ký tự Unicode.
- `readLine()` nhận CR, LF và CRLF làm dòng kết thúc, nhưng **không trả separator** trong chuỗi dòng.
- Đọc tới EOF, `readLine()` trả **`null`**. Một dòng rỗng hợp lệ sẽ trả **`""`**, khác `null`.
- Nếu byte file không hợp lệ theo charset, thao tác đọc có thể ném `IOException` (thường là `MalformedInputException`); không nên tin rằng gọi `newBufferedReader` thành công có nghĩa toàn bộ file decode được.
- `Reader.read()` trả code units, không hứa mỗi lời gọi trả một Unicode code point ngoài BMP hoàn chỉnh.

**Khác biệt phiên bản:** Trong Java 7 dùng overload `Files.newBufferedReader(Path, Charset)`. Từ Java 8 có thêm `Files.newBufferedReader(Path)` sử dụng UTF-8 mặc định theo hợp đồng API; code mới vẫn có thể truyền `StandardCharsets.UTF_8` để làm rõ format.

## 6. Mở `BufferedWriter` — ghi văn bản, không lẫn với OutputStream

Mẫu:

~~~java
try (BufferedWriter writer =
             Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
    writer.write('\n');
}
~~~

Đây là đoạn trong phương thức có `path` đã khai báo. `BufferedWriter` ghi ký tự, chuyển sang byte theo UTF-8 qua encoder.

- `write("...")` **không** tự thêm newline.
- `writer.newLine()` thêm **line separator theo hệ thống**. Với file có định dạng bắt buộc LF, ghi `'\n'` rõ ràng thay vì dựa vào `newLine()`.
- Bộ đệm có thể giữ text trong RAM trước khi chuyển xuống file; lỗi encoding/I/O có thể xuất hiện ở `write`, `flush` hoặc `close`.
- `newBufferedWriter(path, UTF_8)` mặc định **CREATE, TRUNCATE_EXISTING, WRITE**, giống `newOutputStream(path)`.
- Java 8+ có overload `Files.newBufferedWriter(path, options...)` dùng UTF-8; Java 7 dùng overload nhận charset tường minh.

### 6.1. Chương trình độc lập: đọc/ghi tiếng Việt và emoji

Tạo file `TextOpenDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextOpenDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("text-demo-", ".txt");
        String first = "Xin chào, Nguyễn";
        String second = "Ký tự: 🚀";

        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(file,
                                 StandardCharsets.UTF_8)) {
                writer.write(first);
                writer.write('\n');
                writer.write(second);
                writer.write('\n');
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(file,
                                 StandardCharsets.UTF_8)) {
                System.out.println("first=" +
                        first.equals(reader.readLine()));
                System.out.println("second=" +
                        second.equals(reader.readLine()));
                System.out.println("eof=" +
                        (reader.readLine() == null));
            }

            String expected = first + "\n" + second + "\n";
            System.out.println("exactText=" +
                    expected.equals(Files.readString(
                            file, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TextOpenDemo.java
java TextOpenDemo
~~~

Stdout:

~~~text
first=true
second=true
eof=true
exactText=true
~~~

Diễn giải:

1. Tên file được tạo tạm và dọn trong `finally`; không ảnh hưởng các file dự án.
2. File có ký tự tiếng Việt và emoji, nhưng các assertion in ra boolean ASCII, dễ so sánh trên terminal thiếu font.
3. `write('\n')` tạo **LF cố định** dù chương trình chạy trên hệ điều hành nào hỗ trợ API.
4. `readLine()` bỏ dấu newline; vì thế chương trình còn dùng `Files.readString` để kiểm tra **toàn bộ nội dung, bao gồm LF cuối**.
5. Việc đóng writer trước khi đọc giúp đảm bảo dữ liệu đã rời khỏi buffer của writer; không mở reader đồng thời rồi dựa vào may mắn.

**Lưu ý:** `Files.readString` có từ Java 11 và phù hợp với file nhỏ. Với file lớn, đọc lần lượt bằng BufferedReader như ở ví dụ thay vì nạp toàn bộ vào một String.

## 7. Open options: quyết định tạo, ghi đè và nối thêm

Các method ghi nhận `OpenOption...`, phổ biến nhất là các giá trị từ `java.nio.file.StandardOpenOption`:

| Option | Tác dụng | Cảnh báo |
| --- | --- | --- |
| `READ` | Yêu cầu mở để đọc | Mặc định của `newInputStream`; **không được** dùng với `newOutputStream` |
| `WRITE` | Yêu cầu ghi | Dùng với các option ghi khi cần rõ ràng |
| `CREATE` | Tạo nếu chưa có; nếu đã có thì mở file hiện có | Không chặn overwrite khi file đã tồn tại |
| `CREATE_NEW` | Tạo file mới, thất bại nếu file đã có hoặc là symbolic link | Thích hợp khi **không được ghi đè**; kiểm tra tồn tại + tạo mang tính atomic theo API |
| `TRUNCATE_EXISTING` | Đưa file thường hiện có về 0 byte khi mở để ghi | Rủi ro xóa dữ liệu cũ |
| `APPEND` | Ghi tại cuối file | Không kết hợp với `READ` hoặc `TRUNCATE_EXISTING` trong hợp đồng byte channel liên quan |
| `SYNC` / `DSYNC` | Yêu cầu đồng bộ dữ liệu/metadata theo ngữ nghĩa được API mô tả | Cần đánh giá hỗ trợ provider và hiệu năng, không dùng bừa |

**Không truyền options** vào `newOutputStream` hoặc `newBufferedWriter(path, UTF_8)` → mặc định **CREATE + TRUNCATE_EXISTING + WRITE**.

**Có truyền options** → cần suy xét **toàn bộ cấu hình mới**, không giả định mặc định truncate luôn tự đi theo. Những cách dùng thông thường:

~~~java
// Đọc:
Files.newInputStream(path); // Mặc định READ.

// Ghi đè / tạo:
Files.newOutputStream(path); // CREATE + TRUNCATE_EXISTING + WRITE.

// Ghi nối vào file đang có:
Files.newOutputStream(path, StandardOpenOption.APPEND);

// Tạo nếu thiếu, nối vào cuối:
Files.newOutputStream(path,
        StandardOpenOption.CREATE, StandardOpenOption.APPEND);

// Chỉ tạo file mới; không được ghi đè:
Files.newOutputStream(path,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

Đây là **các câu lệnh minh họa**; trong ứng dụng phải lưu stream và đóng bằng try-with-resources. Không copy các lời gọi không đóng tài nguyên nguyên xi thành code sản phẩm.

**Lưu ý khi APPEND:**

- `APPEND` **một mình** cần file đã có; nếu file không tồn tại, thao tác mở có thể thất bại.
- `CREATE + APPEND` tạo file khi thiếu, nối vào cuối khi đã tồn tại.
- `APPEND + TRUNCATE_EXISTING` là tổ hợp **không hợp lệ**, vì vừa muốn nối vào file vừa muốn xóa nội dung ngay lúc mở.
- Khi nhiều process/thread cùng append, **không mặc định** mỗi logical record được ghi nguyên vẹn, không xen kẽ với record khác. Tính atomic của thao tác append phụ thuộc filesystem/provider; nếu yêu cầu atomic records, cần thiết kế riêng.
- `CREATE_NEW` khác `CREATE`. Một bước `Files.exists(path)` rồi mở bằng `CREATE` không chặn được race khi process khác tạo file ở giữa; dùng `CREATE_NEW` nếu cần chính sách “chỉ tạo khi chưa tồn tại”.

Nguồn: [Files.newOutputStream Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newOutputStream(java.nio.file.Path,java.nio.file.OpenOption...)), [StandardOpenOption Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardOpenOption.html).

### 7.1. Chương trình kiểm chứng truncate và append

Tạo `OpenOptionsDemo.java`:

~~~java
import java.io.BufferedWriter;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class OpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("options-demo-", ".txt");

        try {
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("AB".getBytes(StandardCharsets.UTF_8));
            }
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("C".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("truncated=" +
                    "C".equals(Files.readString(
                            file, StandardCharsets.UTF_8)));

            try (OutputStream out = Files.newOutputStream(
                    file, StandardOpenOption.APPEND)) {
                out.write("D".getBytes(StandardCharsets.UTF_8));
            }

            try (BufferedWriter writer = Files.newBufferedWriter(
                    file, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
                writer.write("E\n");
            }

            System.out.println("appended=" +
                    "CDE\n".equals(Files.readString(
                            file, StandardCharsets.UTF_8)));

            try (BufferedWriter writer = Files.newBufferedWriter(
                    file, StandardCharsets.UTF_8,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.WRITE)) {
                writer.write("Z");
            }

            System.out.println("explicitTruncate=" +
                    "Z".equals(Files.readString(
                            file, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OpenOptionsDemo.java
java OpenOptionsDemo
~~~

Stdout:

~~~text
truncated=true
appended=true
explicitTruncate=true
~~~

Từng thời điểm:

1. Sau lần đầu, file chứa `AB`.
2. Mở lại `newOutputStream(file)` **mặc định truncate** rồi ghi `C` → file chứa `C`, không phải `ABC`.
3. Mở với `APPEND` và ghi `D` → file chứa `CD`.
4. Mở `newBufferedWriter` với `CREATE + APPEND`, ghi `E\n` → file chứa `CDE\n`.
5. Mở với `TRUNCATE_EXISTING + WRITE`, ghi `Z` → file chỉ chứa `Z`.

Đây là tình huống quan trọng nhất khi review code xuất log, báo cáo hoặc export file: **một thay đổi options nhỏ có thể biến append thành ghi đè**.

## 8. Dùng `CREATE_NEW` khi không được thay file cũ

Nếu hệ thống cần tạo file đầu ra mới và **không chấp nhận overwrite**, dùng `CREATE_NEW` thay cho cách thủ công “check tồn tại rồi create”.

Tạo file `CreateNewDemo.java`:

~~~java
import java.io.OutputStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CreateNewDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("create-new-demo-");
        Path file = directory.resolve("fresh.bin");

        try {
            try (OutputStream out = Files.newOutputStream(file,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                out.write(7);
            }
            System.out.println("created=" + Files.isRegularFile(file));

            boolean rejected = false;
            try (OutputStream ignored = Files.newOutputStream(file,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                // Không vào đây nếu file đã tồn tại.
            } catch (FileAlreadyExistsException expected) {
                rejected = true;
            }

            System.out.println("duplicateRejected=" + rejected);
            System.out.println("bytePreserved=" +
                    (Files.readAllBytes(file)[0] == 7));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CreateNewDemo.java
java CreateNewDemo
~~~

Stdout:

~~~text
created=true
duplicateRejected=true
bytePreserved=true
~~~

**Điều cần biết:**

- Theo API, `CREATE_NEW` thực hiện bước kiểm tra chưa tồn tại và tạo file mới **mang tính atomic** đối với các thao tác filesystem khác.
- Nếu file đã tồn tại, lần mở thứ hai bị từ chối; test bắt subclass cụ thể `FileAlreadyExistsException` trong môi trường đang chạy.
- Một `FileAlreadyExistsException` **không** chứng minh mọi kiểu lỗi mở file đều là “trùng file”; vẫn cần xử lý I/O error và quyền truy cập riêng.
- `CREATE_NEW` bảo vệ điều kiện tạo file, **không** tự bảo đảm một loạt lần ghi sau đó là giao dịch atomic hoặc dữ liệu đã được đồng bộ ra thiết bị lưu trữ.

## 9. Thư mục cha chưa tồn tại và file đầu vào không có

Mặc định, `Files.newOutputStream`/`newBufferedWriter` với `CREATE` tạo **file đích nếu cần**, chứ không tự tạo cả cây **thư mục cha**. Nếu đường dẫn `reports/2026/export.txt` nhưng `reports/2026` chưa tồn tại, thao tác mở để ghi có thể thất bại.

Tương tự, `Files.newInputStream` để đọc một file không có sẽ không tự tạo file rỗng; nó báo lỗi I/O. Đừng “sửa” lỗi đọc file thiếu bằng cách mở OutputStream để tạo file rỗng, vì việc đó thay đổi ý nghĩa xử lý.

### 9.1. Chương trình kiểm tra và tạo thư mục cha

Tạo file `MissingParentDemo.java`:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MissingParentDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("parent-demo-");
        Path parent = root.resolve("nested");
        Path file = parent.resolve("data.txt");

        try {
            boolean missingParent = false;
            try (BufferedWriter writer =
                         Files.newBufferedWriter(file,
                                 StandardCharsets.UTF_8)) {
                writer.write("X");
            } catch (IOException expected) {
                missingParent = true;
            }
            System.out.println("missingParentRejected=" + missingParent);

            Files.createDirectories(parent);

            try (BufferedWriter writer =
                         Files.newBufferedWriter(file,
                                 StandardCharsets.UTF_8)) {
                writer.write("created");
            }
            System.out.println("text=" +
                    Files.readString(file, StandardCharsets.UTF_8));

            boolean missingInput = false;
            try (InputStream ignored =
                         Files.newInputStream(parent.resolve("absent.txt"))) {
                // Input file không tồn tại.
            } catch (IOException expected) {
                missingInput = true;
            }
            System.out.println("missingInputRejected=" + missingInput);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(parent);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MissingParentDemo.java
java MissingParentDemo
~~~

Stdout:

~~~text
missingParentRejected=true
text=created
missingInputRejected=true
~~~

**Giải thích:**

1. Lần mở writer đầu tiên thiếu thư mục `nested`, nên I/O báo lỗi.
2. `Files.createDirectories(parent)` tạo các thư mục cần thiết, sau đó writer mở được file và ghi nội dung.
3. Mở InputStream cho `absent.txt` vẫn thất bại vì nó là file đọc chưa tồn tại.
4. Test bắt `IOException` thay vì phụ thuộc nguyên văn message hoặc một subclass luôn giống nhau trên mọi filesystem.
5. Trong hệ thống thật, nếu đường dẫn do người dùng cung cấp, cần kiểm tra policy, quyền truy cập, traversal và symlink; `createDirectories` không phải giấy phép tạo thư mục ở mọi vị trí.

**Không nên thay toàn bộ exception bằng `false`/chuỗi rỗng nếu sự cố file là lỗi nghiêm trọng.** Quyết định tầng ứng dụng cần báo lỗi, thử lại hay fallback bằng quy tắc nghiệp vụ.

## 10. Charset và lỗi dữ liệu văn bản không hợp lệ

Reader/Writer khác byte stream ở chỗ chúng phải **decode/encode** bằng một charset.

- Với `newBufferedReader(path, StandardCharsets.UTF_8)`, byte không hợp lệ cho UTF-8 có thể làm thao tác đọc ném `IOException`, thường là `MalformedInputException`.
- Với `newBufferedWriter(path, StandardCharsets.UTF_8)`, một `String` chứa surrogate không ghép cặp có thể gây lỗi encoding. Vì writer có buffer, lỗi có thể xuất hiện lúc **write, flush hoặc close**.
- `Files.newInputStream`/`newOutputStream` làm việc với **byte thô**, không tự kiểm tra byte ấy có phải UTF-8 hợp lệ hay không.
- Không dùng một lần chuyển đổi qua charset khác hoặc một decoder với hành vi thay thế để “sửa” file bị hỏng rồi coi dữ liệu không đổi.
- Nếu cần xử lý `REPORT`/`REPLACE` đặc biệt, có thể tạo `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction` phù hợp. Cần phân biệt phương thức tiện ích nào mặc định thay dữ liệu lỗi với phương thức có hợp đồng báo lỗi.

### 10.1. Chương trình Java 17+: Reader/Writer báo malformed

Tạo file `StrictTextIoDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StrictTextIoDemo {
    public static void main(String[] args) throws Exception {
        Path invalid = Files.createTempFile("invalid-utf8-", ".txt");
        Path output = Files.createTempFile("invalid-text-", ".txt");

        try {
            Files.write(invalid,
                    new byte[]{(byte) 0xC3, (byte) 0x28});

            boolean readRejected = false;
            try (BufferedReader reader =
                         Files.newBufferedReader(invalid,
                                 StandardCharsets.UTF_8)) {
                while (reader.read() != -1) { }
            } catch (MalformedInputException expected) {
                readRejected = true;
            }
            System.out.println("badUtf8Rejected=" + readRejected);

            boolean writeRejected = false;
            try (BufferedWriter writer =
                         Files.newBufferedWriter(output,
                                 StandardCharsets.UTF_8)) {
                writer.write("\uD83D");
            } catch (IOException expected) {
                writeRejected = true;
            }
            System.out.println("badSurrogateRejected=" + writeRejected);
        } finally {
            Files.deleteIfExists(invalid);
            Files.deleteIfExists(output);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 StrictTextIoDemo.java
java StrictTextIoDemo
~~~

Stdout:

~~~text
badUtf8Rejected=true
badSurrogateRejected=true
~~~

Giải thích:

1. Byte `C3 28` không tạo thành chuỗi UTF-8 hợp lệ. Writer từ `Files.write(byte[])` vẫn ghi được byte thô, còn BufferedReader với UTF-8 nhận diện lỗi khi giải mã.
2. `"\uD83D"` là một high surrogate đứng một mình, thiếu low surrogate nên không thể mã hóa thành Unicode scalar hợp lệ.
3. `BufferedWriter` có thể chỉ báo lỗi **khi đóng**, vì dữ liệu đang được buffer. Try-with-resources đảm bảo hoạt động đóng được thực hiện trong phạm vi `try/catch`.
4. Ví dụ chỉ dùng dữ liệu lỗi để quan sát contract; không đưa surrogate đơn lẻ vào văn bản sản phẩm.
5. Nếu file chứa các byte rất quan trọng cần bảo toàn nguyên vẹn, chỉ dùng luồng byte; đừng decode rồi encode lại mà không nắm rõ quy tắc xử lý lỗi.

Nguồn: [Files.newBufferedReader/newBufferedWriter Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html), [CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html).

## 11. `readLine()` có đọc được dòng rỗng và giữ newline không?

`BufferedReader.readLine()` đọc đến LF, CR, CRLF hoặc EOF; **không trả ký tự newline**. Nếu có một dòng rỗng, phương thức có thể trả chuỗi `""`; **`null` chỉ dùng cho EOF khi không còn dòng để trả**.

Vì newline bị loại khỏi kết quả từng dòng, không được dùng `readLine()` rồi nối chuỗi bằng newline của hệ thống để tuyên bố file gốc byte-for-byte không thay đổi.

### 11.1. Chương trình minh họa CRLF, LF, CR

Tạo file `ReaderLinesDemo.java`:

~~~java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReaderLinesDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("lines-demo-", ".txt");
        String raw = "mot\r\nhai\nba\r";

        try {
            Files.writeString(file, raw, StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(file,
                                 StandardCharsets.UTF_8)) {
                String a = reader.readLine();
                String b = reader.readLine();
                String c = reader.readLine();
                String end = reader.readLine();

                System.out.println("joined=" +
                        a + "|" + b + "|" + c);
                System.out.println("endIsNull=" + (end == null));
                System.out.println("withoutEol=" +
                        "mot|hai|ba".equals(a + "|" + b + "|" + c));
            }

            System.out.println("rawPreserved=" +
                    raw.equals(Files.readString(
                            file, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ReaderLinesDemo.java
java ReaderLinesDemo
~~~

Stdout:

~~~text
joined=mot|hai|ba
endIsNull=true
withoutEol=true
rawPreserved=true
~~~

Các loại newline khác nhau được `readLine()` diễn giải thành ranh giới dòng logic. Để khôi phục byte ban đầu, phải giữ quy tắc separator từ đầu hoặc dùng `Files.readAllBytes`/đọc nguyên văn text; không thể suy ra mỗi dấu dòng ban đầu chỉ từ `readLine()`.

**Lưu ý thêm:** `BufferedWriter.newLine()` dùng dòng phân cách do `line.separator` của hệ thống xác định, nên có thể tạo byte khác giữa các nền tảng. Với một chuẩn dữ liệu quy định LF, dùng `writer.write('\n')` hoặc ghi chuỗi định dạng có LF tường minh.

## 12. Khi cần chuyển byte stream thành Reader/Writer

Bốn API chính đã đủ cho nhiều tình huống:

- Chỉ cần text từ file: `Files.newBufferedReader(path, UTF_8)`.
- Chỉ cần viết text vào file: `Files.newBufferedWriter(path, UTF_8)`.
- Cần nhận một `InputStream` từ API khác (ví dụ một nguồn dữ liệu stream) nhưng muốn xử lý **ký tự**: bọc `InputStreamReader(stream, UTF_8)`, tùy nhu cầu bọc thêm `BufferedReader`.
- Cần viết String vào một `OutputStream` đã có sẵn: bọc `OutputStreamWriter(stream, UTF_8)`, tùy nhu cầu bọc thêm `BufferedWriter`.

Sơ đồ:

~~~text
InputStream (bytes)
       |
       | InputStreamReader(..., UTF_8)
       v
Reader (UTF-16 code units)
       |
       | BufferedReader (optional)
       v
readLine(), read(char[])

Writer.write(String)
       |
       | BufferedWriter (optional)
       v
OutputStreamWriter(..., UTF_8)
       |
       v
OutputStream (bytes)
~~~

**Tài nguyên sở hữu bởi wrapper:** Trong một chain điển hình, **đóng wrapper ngoài cùng** sẽ đóng các lớp bên dưới. Tránh giữ reference tới stream bên dưới rồi tiếp tục dùng sau khi wrapper đã đóng. Nếu một API trả stream mà **caller không sở hữu quyền đóng**, phải có hợp đồng ownership riêng trước khi bọc và close.

### 12.1. Chương trình độc lập: ghép các lớp

Tạo file `StreamReaderWriterBridgeDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StreamReaderWriterBridgeDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("bridge-demo-", ".txt");
        String value = "Nội dung: 💡";

        try {
            try (BufferedWriter writer = new BufferedWriter(
                    new OutputStreamWriter(Files.newOutputStream(file),
                            StandardCharsets.UTF_8))) {
                writer.write(value);
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(Files.newInputStream(file),
                            StandardCharsets.UTF_8))) {
                System.out.println("sameText=" +
                        value.equals(reader.readLine()));
                System.out.println("endIsNull=" +
                        (reader.readLine() == null));
            }

            System.out.println("hasUtf8=" +
                    value.equals(Files.readString(
                            file, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 StreamReaderWriterBridgeDemo.java
java StreamReaderWriterBridgeDemo
~~~

Stdout:

~~~text
sameText=true
endIsNull=true
hasUtf8=true
~~~

Trong ví dụ này, `OutputStreamWriter` **mã hóa ký tự thành UTF-8**, `InputStreamReader` **giải mã UTF-8 thành ký tự**, và `BufferedReader/BufferedWriter` giúp xử lý văn bản theo buffer. Đóng wrapper bên ngoài đóng chain.

**Một khác biệt cần review:** `OutputStreamWriter`/`InputStreamReader` có thể có chính sách **thay thế** đối với dữ liệu mã hóa không hợp lệ tùy constructor/decoder; đừng mặc định nó xử lý lỗi giống hệt `Files.newBufferedWriter/newBufferedReader`. Khi cần chế độ strict, cấu hình `CharsetEncoder/CharsetDecoder` với `CodingErrorAction.REPORT` theo hợp đồng và test lỗi. Với file văn bản thông thường, API `Files.newBufferedReader/newBufferedWriter` ngắn gọn và tránh bọc lớp không cần thiết.

## 13. Copy file lớn theo block với try-with-resources

Đọc hết file bằng `Files.readAllBytes` rồi ghi lại là cách dễ hiểu với file nhỏ, nhưng có thể tốn rất nhiều bộ nhớ với file lớn. Để copy theo **các khối byte**, đọc từng block vào một buffer và ghi đúng số byte đã đọc.

Mẫu độc lập:

Tạo file `CopyStreamsDemo.java`:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class CopyStreamsDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("copy-streams-");
        Path source = root.resolve("source.bin");
        Path target = root.resolve("target.bin");
        byte[] payload = {0, 1, 10, 127, (byte) 0xFF};

        try {
            Files.write(source, payload);
            long transferred = 0;

            try (InputStream in = Files.newInputStream(source);
                 OutputStream out = Files.newOutputStream(target)) {
                byte[] buffer = new byte[3];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    out.write(buffer, 0, n);
                    transferred += n;
                }
            }

            System.out.println("copiedBytes=" + transferred);
            System.out.println("sameBytes=" +
                    Arrays.equals(payload, Files.readAllBytes(target)));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CopyStreamsDemo.java
java CopyStreamsDemo
~~~

Stdout:

~~~text
copiedBytes=5
sameBytes=true
~~~

**Điểm học tập:**

- Vòng lặp copy theo `buffer[0..n)`, không dùng `buffer.length` như số byte vừa đọc.
- Dùng `InputStream`/`OutputStream` để **bảo toàn byte**, không decode/encode nhầm file.
- Hai resource được khai báo trong cùng try-with-resources; khi rời khối, Java đóng theo **thứ tự ngược với lúc khai báo** (trước tiên `out`, sau đó `in`).
- Nếu lỗi xảy ra giữa quá trình ghi, file `target` **có thể đã được tạo và chứa dữ liệu một phần**. Với yêu cầu publish file an toàn, cần ghi ra file tạm, xác minh và di chuyển/thay thế bằng quy trình thích hợp, cân nhắc hỗ trợ `ATOMIC_MOVE` của filesystem.
- File ví dụ chỉ dài 5 byte để stdout cố định; khi xử lý file lớn có thể dùng buffer 8 KiB hoặc tùy workload. Không suy ra một kích thước buffer là tối ưu cho mọi môi trường.

**Lựa chọn đơn giản hơn:** Nếu chỉ cần sao chép nguyên file, `Files.copy(source, target, options...)` là API cấp cao. Chỉ dùng stream thủ công khi cần xử lý/truyền từng block, đo tiến độ hoặc có logic riêng. Nên biết `Files.copy` và stream copy có hợp đồng overwrite khác nhau; đừng thay thế mà không kiểm tra options.

## 14. Try-with-resources là điều kiện an toàn cơ bản

Cả bốn đối tượng do `Files` trả về đều là tài nguyên cần đóng:

- `InputStream`, `OutputStream`.
- `BufferedReader`, `BufferedWriter`.

Từ Java 7, try-with-resources giúp đóng tự động khi khối kết thúc, **kể cả khi đọc/ghi ném exception**.

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        out.write(buffer, 0, n);
    }
}
~~~

Đây là đoạn trong phương thức có `source`/`target` kiểu `Path`. Nó minh họa khai báo hai resource; chương trình hoàn chỉnh ở mục 13 có cùng cơ chế.

**Những điều cần nhớ:**

1. Tài nguyên được đóng theo **thứ tự ngược** với khai báo.
2. Nếu body và `close()` cùng ném lỗi, lỗi khi close có thể được giữ dưới dạng **suppressed exception** của lỗi chính. Không tự che mất lỗi gốc trong một khối `finally` viết thủ công.
3. `close()` có thể ném `IOException`; không nên bỏ qua nguy cơ lỗi flush khi ghi văn bản.
4. Nếu bạn trả về một stream từ method để caller sử dụng sau, **đừng đóng stream ngay trước khi trả**. Hãy định nghĩa rõ caller có trách nhiệm close.
5. Nếu stream chỉ dùng trong một method, ưu tiên try-with-resources ngay vị trí mở.
6. Nếu dùng wrapper reader/writer, đóng wrapper ngoài cùng, không giữ stream đã bị đóng để tái sử dụng.
7. Try-with-resources không tự biến thao tác file nhiều bước thành transaction/atomic publish. Phải có quy trình riêng nếu cần bảo đảm nội dung đích hoàn chỉnh.

## 15. Lỗi và điều kiện biên khi mở tệp

| Tình huống | Điều xảy ra | Hướng giải quyết |
| --- | --- | --- |
| Đọc file không tồn tại | `newInputStream`/`newBufferedReader` ném `IOException`, thường subclass `NoSuchFileException` | Kiểm tra nguồn theo nghiệp vụ, không tự tạo file khi đang đọc |
| Ghi file ở thư mục cha chưa có | Gọi mở có thể thất bại | Dùng `Files.createDirectories(parent)` khi được phép |
| Ghi vào file đã tồn tại không muốn xóa | Default writer/output stream **truncate** | Dùng `APPEND` hoặc thiết kế `CREATE_NEW`, tùy yêu cầu |
| Ghi file bắt buộc phải mới | Dùng `CREATE` có thể mở file cũ | Dùng `CREATE_NEW` |
| Đặt `APPEND` với `TRUNCATE_EXISTING` | Tổ hợp không hợp lệ | Chọn một chính sách ghi |
| Truyền `READ` vào `newOutputStream` | Không phù hợp với API ghi | Dùng `newInputStream` để đọc |
| Truyền charset sai cho file văn bản | Mojibake hoặc `IOException` | Quy định charset thật, thường UTF-8 |
| UTF-8 byte bị hỏng | Reader có thể ném `MalformedInputException` khi đọc | Bắt lỗi và xử lý theo contract, không tự đoán charset |
| Surrogate không ghép cặp khi viết | Writer strict có thể ném lỗi ở write/flush/close | Kiểm tra nguồn text, tránh cắt giữa surrogate |
| Thao tác nhiều dòng nhưng cần giữ CRLF/LF gốc | `readLine` bỏ newline | Dùng raw text/bytes và định nghĩa canonicalization |
| Phần mềm có đường dẫn do người dùng nhập | Có thể trỏ ngoài vùng cho phép hoặc gặp symlink | Kiểm tra path/ownership/quyền, xử lý race tùy threat model |
| Hai tác vụ cùng append | Thứ tự và mức nguyên tử của logical record không tự đảm bảo | Cần phối hợp, logging framework hoặc kiến trúc ghi một chủ sở hữu |
| Dữ liệu phải sống sót khi mất điện | Flush/close chưa phải chính sách durability đủ | Đánh giá sync/atomic move/provider và yêu cầu lưu trữ |
| File rất lớn | `readAllBytes`/`readString` nạp nhiều dữ liệu | Duyệt bằng InputStream/BufferedReader theo block/dòng |

**Không coi exception message là API ổn định** để parse nghiệp vụ. Chọn loại lỗi ở mức hợp lý, bảo toàn cause/suppressed exceptions và ghi log an toàn.

## 16. So sánh các API liên quan trong Java 17+

Bốn API mở file là trọng tâm, nhưng trong code mới bạn cũng có những lựa chọn ngắn gọn hơn:

| Công việc | API phù hợp | Ghi nhớ |
| --- | --- | --- |
| Đọc một file text **nhỏ** toàn bộ | `Files.readString(path, UTF_8)` | Java 11+, đọc cả file vào String |
| Ghi một String vào file | `Files.writeString(path, text, UTF_8, options...)` | Java 11+, chú ý open options |
| Đọc file binary nhỏ toàn bộ | `Files.readAllBytes(path)` | Dễ dùng nhưng tốn bộ nhớ theo file |
| Ghi một byte array | `Files.write(path, bytes, options...)` | Tương tự cần biết tạo/truncate/append |
| Copy file nguyên vẹn | `Files.copy(source, target, options...)` | Hợp đồng overwrite khác stream output mặc định |
| Đọc text nhiều dòng lớn | `Files.newBufferedReader(path, UTF_8)` | Luôn đóng reader |
| Ghi text tăng dần | `Files.newBufferedWriter(path, UTF_8, options...)` | Ghi String/dòng với buffer |
| Đọc/ghi binary streaming | `newInputStream/newOutputStream` | Xử lý byte theo buffer; không tự encode |
| Chuyển byte stream sang text | `InputStreamReader/OutputStreamWriter` | Đặt charset, quản lý wrapper ownership |
| Muốn truy cập ngẫu nhiên/seek | `Files.newByteChannel` hoặc `FileChannel` | Stream không phải API seek/position chung |

Chọn API theo **dữ liệu, kích thước và semantics**. Không nhất thiết tạo stream khi một thao tác `Files.readString` trên file cấu hình rất nhỏ đã đủ, cũng không nhất thiết nạp file video nhiều GB vào `byte[]`.

## 17. Một quy trình thực hành an toàn

Khi triển khai đọc/ghi file trong hệ thống:

1. **Xác định loại dữ liệu:** nhị phân hay text? Với text, charset nào và có cần giữ byte gốc không?
2. **Xác định Path đích:** `root.resolve(...)`, không nối separator cứng; bảo đảm path được phép truy cập.
3. **Quy định open options:** đọc, ghi đè, append hay chỉ tạo file mới? Không dùng mặc định ghi nếu không muốn truncate.
4. **Kiểm tra thư mục cha:** tạo khi cần và khi được phép; tránh nhầm `CREATE` với việc tạo nhiều cấp thư mục.
5. **Mở resource trong try-with-resources.** Đừng giữ file handle qua quá nhiều tầng khi không cần.
6. **Đọc/ghi đúng đơn vị:** byte[] có `count`; Reader/Writer có String/char; không decode binary.
7. **Ghi newline theo format:** CRLF/LF có thể khác byte; nếu cần byte exact, bảo toàn nguyên văn.
8. **Kiểm tra dữ liệu lỗi:** file UTF-8 malformed, ký tự surrogate không ghép cặp, IOException lúc flush/close.
9. **Kiểm thử trường hợp biên:** file rỗng, file không tồn tại, có sẵn nội dung, thư mục cha thiếu, append vs truncate, CREATE_NEW duplicate.
10. **Test nội dung sau khi đóng writer:** kiểm tra byte/text tương ứng; không chỉ dựa vào `write` không throw.
11. **Với file lớn:** ưu tiên streaming, đo hiệu năng theo workload thay vì tải toàn bộ file.
12. **Với ghi cần an toàn giao dịch:** cân nhắc temp file + validate + move/replace theo semantics filesystem và yêu cầu durability.
13. **Với nhiều thread/process:** định nghĩa ownership và coordination, không mặc định append logical record là atomic.
14. **Với portability:** chạy test trên OS/JDK mục tiêu; tránh hardcode exception message, path tạm và line separators.
15. **Với code review:** làm rõ ai chịu trách nhiệm close, charset nào, quyền ghi đè ra sao.

## 18. Các nhầm lẫn thường gặp

| Ngộ nhận | Sự thật |
| --- | --- |
| “`Files.newInputStream` tự đọc UTF-8 thành ký tự.” | Nó đọc byte, **không decode**. Dùng Reader/decoder khi cần text. |
| “`Files.newBufferedReader` phù hợp mọi file, cả ảnh.” | BufferedReader chỉ phù hợp dữ liệu **text** theo charset. |
| “`newBufferedReader` phải bọc thêm BufferedReader lần nữa.” | API đã trả BufferedReader có buffer. |
| “`newOutputStream` mặc định thêm byte vào cuối.” | Mặc định **CREATE + TRUNCATE_EXISTING + WRITE**. |
| “`newBufferedWriter` mặc định giữ nguyên nội dung cũ.” | Cũng mặc định **truncate**, không phải append. |
| “`APPEND` luôn tạo file khi chưa tồn tại.” | Cần `CREATE + APPEND` nếu muốn tạo khi thiếu. |
| “`CREATE` không bao giờ ghi vào file cũ.” | `CREATE` mở file cũ nếu tồn tại; dùng `CREATE_NEW` nếu cần từ chối. |
| “`CREATE_NEW` bảo đảm ghi file nhiều bước là atomic.” | Chỉ bước kiểm tra/tạo file được bảo vệ theo contract; dữ liệu ghi có thể dở dang nếu lỗi. |
| “Lệnh `Files.exists` trước khi ghi đủ chống race.” | Trạng thái file có thể thay đổi giữa kiểm tra và mở; dùng option phù hợp. |
| “Khi đã buffer thì write() xong chắc chắn file đã có đủ byte.” | Dữ liệu có thể còn trong buffer; close/flush cũng có thể lỗi. |
| “Try-with-resources chỉ đóng khi không có exception.” | Vẫn đóng khi rời khối do exception, với suppressed exceptions khi cần. |
| “`readLine()` trả `""` ở EOF.” | EOF trả **`null`**; dòng rỗng mới là `""`. |
| “`readLine()` giữ nguyên CRLF hay LF ở String trả về.” | Nó **loại dấu kết thúc dòng**. |
| “`newLine()` luôn ghi LF.” | Nó dùng line separator của nền tảng. |
| “`InputStream.read() == -1` có thể là byte 0xFF.” | Không. Byte 0xFF trả int **255**, -1 chỉ EOF. |
| “Luồng byte không cần charset khi chứa text.” | Khi **biến String thành byte**, luôn phải biết charset, dù API cuối là OutputStream. |
| “Dùng encoding mặc định sẽ luôn giống nhau giữa máy.” | Không đảm bảo cho mọi JDK/config; dùng UTF-8 tường minh. |
| “InputStream safe concurrent nghĩa mỗi thread có file offset riêng.” | Thread-safe access không có nghĩa trạng thái đọc độc lập. |
| “Việc Writer đóng thành công luôn đồng nghĩa dữ liệu đã durable trên đĩa.” | Durability cần thiết kế riêng theo filesystem và yêu cầu. |
| “Mở file tạo được đồng nghĩa luôn tạo được thư mục cha.” | Các API trên không tự tạo cả cây thư mục. |

## 19. Câu hỏi tự kiểm tra

**1.** Muốn đọc một tệp `.png`, dùng `newBufferedReader` hay `newInputStream`?  
**Đáp án:** `newInputStream`, vì dữ liệu nhị phân cần bảo toàn byte.

**2.** Muốn đọc từng dòng tiếng Việt UTF-8 mà không tự tạo decoder thủ công?  
**Đáp án:** `Files.newBufferedReader(path, StandardCharsets.UTF_8)`.

**3.** `Files.newOutputStream(path)` làm gì nếu file đã tồn tại?  
**Đáp án:** Theo mặc định nó mở để ghi và **truncate file thường về 0 byte**.

**4.** Muốn nối vào cuối file đã có mà không tạo mới?  
**Đáp án:** Dùng `Files.newOutputStream(path, StandardOpenOption.APPEND)` theo hợp đồng/provider hỗ trợ.

**5.** Muốn append và tạo file nếu thiếu?  
**Đáp án:** `Files.newOutputStream(path, StandardOpenOption.CREATE, StandardOpenOption.APPEND)`; BufferedWriter có options tương ứng.

**6.** Chỉ cho phép file mới, không ghi đè file cũ?  
**Đáp án:** Dùng `CREATE_NEW` thay vì kiểm tra `Files.exists` trước rồi mở bằng `CREATE`.

**7.** `readLine()` trả gì khi EOF và không còn dữ liệu?  
**Đáp án:** `null`. Dòng rỗng hợp lệ là `""`.

**8.** Dùng `writer.newLine()` có luôn tạo LF trên mọi OS?  
**Đáp án:** Không. Nó dùng line separator theo nền tảng.

**9.** Vì sao một file UTF-8 không hợp lệ có thể mở Reader thành công rồi mới lỗi?  
**Đáp án:** Decode diễn ra khi đọc dữ liệu, không nhất thiết kiểm tra toàn file ngay lúc mở.

**10.** `Files.newBufferedWriter` có thể báo lỗi encoding tại `close()` không?  
**Đáp án:** Có, do buffering, việc encode/flush có thể diễn ra khi close.

**11.** `InputStream.read()` trả `-1` có phải vừa đọc byte FF không?  
**Đáp án:** Không. Giá trị byte 0xFF được trả thành int 255; -1 đánh dấu EOF.

**12.** Có nên dùng `Files.readAllBytes` với video lớn nhiều GB không?  
**Đáp án:** Không nên mặc định; dùng stream theo buffer để giới hạn RAM.

**13.** `Files.newOutputStream` tự tạo thư mục cha chưa tồn tại không?  
**Đáp án:** Không; cần `Files.createDirectories` nếu được phép và cần.

**14.** Tại sao phải đóng BufferedWriter trước khi đọc file vừa ghi?  
**Đáp án:** Có thể còn dữ liệu trong buffer, và lỗi flush/close cần được xử lý.

**15.** `OutputStreamWriter` khác `BufferedWriter` ở đâu?  
**Đáp án:** OutputStreamWriter là cầu nối mã hóa ký tự sang byte stream; BufferedWriter thêm **bộ đệm ký tự** và các tiện ích ghi như `newLine()`.

**16.** Nếu cần đọc text từ một InputStream API trả về, lớp nào hỗ trợ?  
**Đáp án:** `InputStreamReader(in, UTF_8)`, có thể bọc `BufferedReader`.

**17.** Muốn đọc bản văn nguyên byte với CRLF/LF gốc, chỉ `readLine()` có đủ không?  
**Đáp án:** Không; readLine bỏ separator, nên cần kiểm tra byte hoặc đọc nguyên văn để giữ thông tin.

**18.** Try-with-resources đóng hai luồng theo thứ tự nào?  
**Đáp án:** Đóng **ngược thứ tự khai báo** trong tài nguyên try.

**19.** `CREATE_NEW` có bảo đảm một bản ghi append cùng lúc với thread khác không xen kẽ?  
**Đáp án:** Không. Đó là hai vấn đề khác nhau: tạo file mới và atomic append/ghi record.

**20.** Nếu mã cần chạy trên Java 7 thì có dùng `Files.newBufferedReader(path)` không?  
**Đáp án:** Không dùng overload không charset ấy ở source level Java 7; sử dụng `Files.newBufferedReader(path, StandardCharsets.UTF_8)`. Overload không charset có từ Java 8.

## 20. Tài liệu chính thức

- [Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): bốn phương thức mở file, mở theo option và I/O errors.
- [Java SE 26 — Files.newInputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newInputStream(java.nio.file.Path,java.nio.file.OpenOption...)): READ mặc định, unbuffered, không cam kết mark/reset.
- [Java SE 26 — Files.newOutputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newOutputStream(java.nio.file.Path,java.nio.file.OpenOption...)): CREATE, TRUNCATE_EXISTING, WRITE mặc định; APPEND, CREATE_NEW.
- [Java SE 26 — Files.newBufferedReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)): đọc text với Charset, malformed bytes.
- [Java SE 26 — Files.newBufferedWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)): ghi text có buffer, chế độ mặc định, encoding errors khi flush/close.
- [Java SE 26 — StandardOpenOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardOpenOption.html): READ/WRITE/CREATE/CREATE_NEW/APPEND/TRUNCATE_EXISTING và sync options.
- [Java SE 26 — StandardCharsets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 tường minh.
- [Java SE 26 — BufferedReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): đọc theo dòng, kết quả null ở EOF.
- [Java SE 26 — BufferedWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedWriter.html): buffer, newline và flush/close.
- [Java SE 26 — InputStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html) và [OutputStreamWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStreamWriter.html): cầu nối giữa byte streams và character streams.
- [Java SE 26 — Path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): Path.resolve, đường dẫn do filesystem provider diễn giải.
- [Java SE 7 — Files](https://docs.oracle.com/javase/7/docs/api/java/nio/file/Files.html): nguồn xác nhận bốn API đã có từ Java 7; dùng như lịch sử ra đời, không thay Javadoc hiện hành.
- [Java SE 7 — Try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): cơ chế đóng tự động, suppressed exceptions.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18 và các giới hạn tương thích.

**Ghi nhớ:** `Files.newInputStream/newOutputStream` làm việc với **byte**, `Files.newBufferedReader/newBufferedWriter` làm việc với **ký tự có charset**. Trước khi mở để ghi, phải hiểu **CREATE/TRUNCATE_EXISTING/APPEND/CREATE_NEW** để không làm mất dữ liệu. Dùng **UTF-8 tường minh**, **try-with-resources**, kiểm tra lỗi ở cả **read/write/close**, và chọn **streaming** cho file lớn.