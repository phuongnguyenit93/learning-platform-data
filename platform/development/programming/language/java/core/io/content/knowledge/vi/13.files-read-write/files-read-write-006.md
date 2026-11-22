# `Files.newInputStream`, `Files.newOutputStream` và các lựa chọn mở tệp trong Java

Khi ứng dụng Java phải **đọc hoặc ghi byte của file** theo dòng dữ liệu (stream), hai phương thức `java.nio.file.Files.newInputStream(Path, OpenOption...)` và `Files.newOutputStream(Path, OpenOption...)` cung cấp cách mở file bằng đối tượng `Path` và trả về `InputStream`/`OutputStream` quen thuộc của Java I/O.

Một vấn đề quan trọng hơn cú pháp là **lựa chọn cách mở file**: đọc một file đã tồn tại, tạo mới, ghi đè nội dung cũ, ghi thêm cuối file, hoặc từ chối khi đường dẫn đã tồn tại. Sai một `OpenOption` có thể dẫn đến **mất dữ liệu**, ghi đè file người dùng, tưởng đã ghi thêm nhưng thực tế xóa nội dung trước đó, hoặc ghi nửa file mà không phát hiện lỗi.

Bài học thuộc nhóm **Đọc ghi bằng Files** của Java Core I/O. Mục tiêu là hiểu hành vi mặc định và tùy chọn của hai API, phối hợp chúng với buffering và chuyển mã văn bản, xử lý lỗi/tài nguyên, đồng thời lựa chọn giải pháp phù hợp cho các tình huống thực tế.

## 1. Ba thành phần: `Path`, `Files` và byte stream

**`Path`** là mô hình đường dẫn của Java NIO.2, ví dụ `Path.of("data", "input.bin")`. Tạo `Path` không tạo hay mở file. Nó chỉ mô tả vị trí file theo quy tắc filesystem/provider.

**`Files`** là lớp tiện ích có các phương thức tĩnh thao tác trên đường dẫn. Hai phương thức chính của bài:

```java
InputStream in = Files.newInputStream(path);
OutputStream out = Files.newOutputStream(path);
```

Đây là **mã minh họa**, cần import `java.io.InputStream`, `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path`; biến `path` phải được khai báo và thao tác mở có thể ném `IOException`.

**`InputStream` và `OutputStream`** thao tác trên **byte**, không tự hiểu text, charset, newline hay cấu trúc định dạng file. `InputStream.read()` trả một byte dưới dạng số `0..255` hoặc `-1` ở EOF. `OutputStream.write(int)` ghi một byte (8 bit thấp).

Sơ đồ:

```text
Đọc:
Path -- Files.newInputStream(...) --> InputStream -- read() --> byte
                                                                   |
                                                 giải mã nếu cần text
                                                                   v
                                                        String / dữ liệu ứng dụng

Ghi:
String / dữ liệu ứng dụng -- mã hóa nếu là text --> byte
                                                    |
Path -- Files.newOutputStream(...) --> OutputStream -- write() --> file
```

`Files.newInputStream` **không giống** `Files.readAllBytes`: nó không yêu cầu đưa toàn bộ file vào RAM rồi mới xử lý. Tương tự, `Files.newOutputStream` thuận tiện khi ghi tuần tự theo từng byte hoặc từng khối, không cần tạo sẵn mảng byte chứa toàn bộ output.

## 2. Cú pháp và phiên bản Java

Các khai báo khái quát:

```java
public static InputStream newInputStream(Path path, OpenOption... options)
        throws IOException;

public static OutputStream newOutputStream(Path path, OpenOption... options)
        throws IOException;
```

Trong phần trên, `OpenOption` là interface đánh dấu tùy chọn mở file, còn `StandardOpenOption` là enum gồm các lựa chọn thường dùng như `READ`, `WRITE`, `APPEND`, `CREATE` và `CREATE_NEW`. Cả hai API có từ **Java 7** trong NIO.2 và có thể dùng trực tiếp với Java 17.

Ví dụ code thông dụng:

```java
try (InputStream input = Files.newInputStream(Path.of("input.bin"))) {
    // Đọc byte.
}

try (OutputStream output = Files.newOutputStream(Path.of("output.bin"))) {
    // Ghi byte.
}
```

Đây là **mã minh họa**, cần đặt trong phương thức khai báo/giải quyết `IOException`. `try-with-resources` tự đóng stream khi ra khỏi khối, cả khi có exception.

Điểm quan trọng: `OpenOption...` là tham số **varargs**, nên có thể bỏ qua hoặc truyền nhiều lựa chọn. **Không truyền gì** không đồng nghĩa với “không có hành vi mặc định”; đặc biệt **mặc định của input khác output**.

## 3. Mặc định của `Files.newInputStream`

Cách gọi:

```java
InputStream input = Files.newInputStream(path);
```

mặc định tương đương **mở để đọc** với `StandardOpenOption.READ`. File mục tiêu phải có thể mở để đọc; API **không tự tạo file nếu chưa tồn tại**.

Ví dụ:

```java
try (InputStream input = Files.newInputStream(Path.of("existing.dat"))) {
    byte[] buffer = new byte[4096];
    int n;
    while ((n = input.read(buffer)) != -1) {
        // Xử lý buffer[0..n), không phải toàn bộ 4096 phần tử.
    }
}
```

Đây là **đoạn minh họa** có thể ném `IOException`, dùng file `existing.dat` có sẵn. Khi một lần `read(buffer)` trả số dương nhỏ hơn chiều dài buffer, đó có thể là một **short read hợp lệ**, không nhất thiết đã tới EOF. Chỉ `-1` thể hiện EOF theo hợp đồng.

### Tùy chọn cho input

`StandardOpenOption.READ` là lựa chọn chuẩn, rõ nghĩa nhất để truyền tường minh:

```java
try (InputStream input = Files.newInputStream(
        path, StandardOpenOption.READ)) {
    // Xử lý byte.
}
```

Đây là **mã minh họa**; cần import `StandardOpenOption`, `Files`, `InputStream` và chuẩn bị biến `path`. Với `newInputStream`, hợp đồng chuẩn chỉ yêu cầu hỗ trợ `READ`, ngoài ra implementation/provider có thể hỗ trợ những tùy chọn riêng. **Không** dùng `APPEND`, `TRUNCATE_EXISTING` hoặc `CREATE_NEW` như thể đây là tùy chọn đọc chuẩn được hỗ trợ; chúng thuộc ngữ cảnh mở để ghi.

Nếu truyền lựa chọn không hợp lệ hoặc không hỗ trợ, API có thể ném `UnsupportedOperationException`, `IllegalArgumentException` hay ngoại lệ khác theo contract/provider. Nếu file không tồn tại, trên filesystem thông thường sẽ có `NoSuchFileException`; nếu quyền truy cập bị từ chối, có thể nhận `AccessDeniedException` hoặc một `IOException` khác.

**`InputStream` không cung cấp random access.** Đọc tuần tự từ đầu theo semantics của stream; nếu cần `position()`/`seek`, nên xem `FileChannel` hoặc `SeekableByteChannel`, không cố tự giả lập random access bằng `skip()` trong mọi trường hợp.

## 4. Mặc định của `Files.newOutputStream` — điểm dễ mất dữ liệu

Cách gọi:

```java
OutputStream output = Files.newOutputStream(path);
```

khi **không truyền option** tương đương:

```java
Files.newOutputStream(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

Ba ý nghĩa phối hợp:

1. **`CREATE`:** nếu file chưa tồn tại, cho phép tạo file mới.
2. **`TRUNCATE_EXISTING`:** nếu file đã tồn tại và được mở để ghi, **cắt nội dung cũ về độ dài 0** khi mở.
3. **`WRITE`:** mở file để ghi byte.

Vì thế, `Files.newOutputStream(path)` **không phải append**. Nếu file có dữ liệu trước đó, nội dung có thể bị xóa **ngay khi mở stream thành công**, thậm chí chương trình chưa gọi `write()` lần nào.

Ví dụ:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    output.write("Mới".getBytes(StandardCharsets.UTF_8));
}
```

Đây là **mã minh họa**: biến `path` phải có, cần import `Files`, `OutputStream` và `StandardCharsets`. Nếu file cũ chứa `"Dữ liệu quan trọng"`, lời gọi mặc định có thể thay toàn bộ nội dung bằng byte UTF-8 của `"Mới"`.

**Nếu không muốn ghi đè**, chọn `CREATE_NEW` thay vì mặc định. **Nếu muốn ghi thêm**, dùng `APPEND` và quyết định có `CREATE` hay không. **Nếu muốn thay nội dung một file quan trọng theo cách hạn chế file dở dang**, cân nhắc ghi file tạm rồi di chuyển có kiểm soát, không nhầm `newOutputStream` với transaction.

## 5. Các `StandardOpenOption` chính dùng với output

| Option | Hành vi | Nên dùng khi |
|---|---|---|
| `WRITE` | Mở để ghi, không tự cắt ngắn hay tạo file nếu chỉ truyền một mình | File đã tồn tại; muốn ghi từ đầu theo cách không tự truncate |
| `APPEND` | Ghi byte ở cuối file; hành vi ghi đồng thời phụ thuộc provider | Nhật ký append hoặc nối dữ liệu cuối file |
| `TRUNCATE_EXISTING` | Khi mở file đã tồn tại để ghi, cắt ngắn về 0; nếu không có tác dụng do cách mở, xem contract | Chủ động thay toàn bộ nội dung cũ |
| `CREATE` | Tạo file nếu chưa tồn tại, còn file đã có thì mở theo những option ghi khác | Tạo hoặc mở để ghi |
| `CREATE_NEW` | Chỉ tạo mới; nếu đường dẫn đã tồn tại, thao tác thất bại; thao tác kiểm tra-tạo là nguyên tử theo contract | Không được ghi đè file sẵn có |
| `SYNC` | Yêu cầu cập nhật nội dung **và metadata** liên quan đồng bộ theo semantics provider | Một số bài toán yêu cầu đồng bộ lưu trữ |
| `DSYNC` | Yêu cầu cập nhật nội dung file đồng bộ theo semantics provider | Khi có yêu cầu độ bền dữ liệu ở mức option này |

**`APPEND` và `TRUNCATE_EXISTING` không phải cặp option hợp lý để dùng chung.** Một cái yêu cầu ghi ở cuối nội dung cũ, một cái xóa nội dung cũ trước khi ghi. Tổ hợp này không hợp lệ theo hợp đồng `newOutputStream` và có thể gây `IllegalArgumentException`.

### Lưu ý đặc biệt về `WRITE` đơn lẻ

Một trong những lỗi nguy hiểm nhất là nghĩ:

```java
Files.newOutputStream(path, StandardOpenOption.WRITE)
```

sẽ **thay thế trọn nội dung file**. Thực tế, với file thường trên provider mặc định, stream bắt đầu ở **đầu file**; nếu ghi một số byte ít hơn nội dung cũ mà không truyền `TRUNCATE_EXISTING`, **phần đuôi cũ có thể vẫn còn**.

Ví dụ file ban đầu có byte ASCII `ABCDEF`, mở với `WRITE` và ghi `XY` có thể cho nội dung **`XYCDEF`**, không phải `XY`. Điều này tạo file sai định dạng rất dễ bị bỏ qua.

### `CREATE` khác `CREATE_NEW`

- `CREATE` cho phép tạo nếu chưa tồn tại **hoặc** mở file đang tồn tại. Độ dài/nội dung file cũ sau đó phụ thuộc `TRUNCATE_EXISTING`, `APPEND` và các option khác.
- `CREATE_NEW` yêu cầu tạo file mới và **thất bại khi đường dẫn đã tồn tại**. Theo contract, sự tồn tại của symbolic link tại đường dẫn cũng có thể khiến nó thất bại, dù link trỏ tới mục tiêu không tồn tại.
- `CREATE_NEW` hữu ích khi cần “không ghi đè”. Khi thêm logic `if (!Files.exists(path)) ...` trước `CREATE`, vẫn có **TOCTOU race** vì đường dẫn có thể được tạo đồng thời.
- `CREATE_NEW` không bảo đảm toàn bộ **quá trình ghi nội dung** là nguyên tử; nó chỉ giải quyết điều kiện tạo mới. Lỗi giữa chừng vẫn có thể để lại file chưa ghi đủ.

### `SYNC`/`DSYNC` không thay cho thiết kế lưu trữ

Các option đồng bộ có thể ảnh hưởng mạnh đến hiệu năng và phụ thuộc provider/filesystem. `DSYNC` liên quan dữ liệu, `SYNC` còn bao gồm metadata theo contract; không nên bật chúng chỉ để “an toàn hơn” mà chưa biết yêu cầu. Không coi `flush()` là cùng một điều với bảo đảm dữ liệu bền vững khi mất điện.

## 6. Bảng chọn cách mở output nhanh

| Mong muốn | Lời gọi gợi ý | Điều cần nhớ |
|---|---|---|
| Tạo file nếu thiếu và **thay toàn bộ** nội dung cũ | `Files.newOutputStream(path)` | Mặc định `CREATE + TRUNCATE_EXISTING + WRITE` |
| Chỉ tạo file mới, không ghi đè | `newOutputStream(path, CREATE_NEW, WRITE)` | Thất bại nếu đường dẫn đã tồn tại |
| Ghi thêm vào file đang tồn tại | `newOutputStream(path, APPEND)` | Có thể thất bại nếu file chưa tồn tại |
| Ghi thêm, tạo file nếu chưa có | `newOutputStream(path, CREATE, APPEND)` | Không tự thêm newline |
| Ghi từ đầu mà giữ phần đuôi chưa bị ghi đè | `newOutputStream(path, WRITE)` | Thường cần rất thận trọng |
| Mở file đang tồn tại để **thay trọn** nội dung | `newOutputStream(path, WRITE, TRUNCATE_EXISTING)` | Không tự tạo file mới nếu thiếu `CREATE` |
| Đọc file có sẵn | `Files.newInputStream(path)` | Mặc định đọc, không tạo file |

Đây là các dạng dùng trên filesystem thông thường. Mọi thao tác có thể ném `IOException` vì quyền truy cập, hệ thống file, file đang được sử dụng, thiết bị lỗi hoặc lý do khác. Nếu ứng dụng đòi hỏi ràng buộc chính xác về concurrent writes, atomicity hoặc symlink, phải đọc contract của provider và thiết kế cao hơn việc chọn một option đơn lẻ.

## 7. Ví dụ 1 — `WRITE`, `APPEND`, mặc định, `CREATE_NEW` và lỗi file thiếu

Tạo tệp `OpenOptionsDemo.java` (Java 17+):

```java
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class OpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("options-");
        Path file = dir.resolve("demo.txt");
        try {
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("ABCDEF".getBytes(StandardCharsets.UTF_8));
            }
            try (OutputStream out = Files.newOutputStream(file, StandardOpenOption.WRITE)) {
                out.write("XY".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("WRITE only=" + Files.readString(file, StandardCharsets.UTF_8));

            try (OutputStream out = Files.newOutputStream(file, StandardOpenOption.APPEND)) {
                out.write("Z".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("APPEND=" + Files.readString(file, StandardCharsets.UTF_8));

            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("Q".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("default output=" + Files.readString(file, StandardCharsets.UTF_8));

            try (OutputStream ignored =
                    Files.newOutputStream(file, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                System.out.println("unexpected new file");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("CREATE_NEW existing=FileAlreadyExistsException");
            }

            try (var ignored = Files.newInputStream(dir.resolve("missing.txt"))) {
                System.out.println("unexpected missing input");
            } catch (NoSuchFileException expected) {
                System.out.println("missing input=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 OpenOptionsDemo.java
java OpenOptionsDemo
```

Kết quả đã kiểm thử với Java 17 trên filesystem mặc định:

```text
WRITE only=XYCDEF
APPEND=XYCDEFZ
default output=Q
CREATE_NEW existing=FileAlreadyExistsException
missing input=NoSuchFileException
```

Giải thích theo từng bước:

1. Tạo thư mục tạm riêng và file `demo.txt` chứa `ABCDEF`.
2. Mở lại chỉ với `WRITE`; ghi `XY` ở đầu, **không truncate**, nên phần đuôi `CDEF` còn lại.
3. Mở với `APPEND`; ghi `Z` vào cuối, tạo `XYCDEFZ`.
4. Mở `newOutputStream(file)` không option và ghi `Q`. Mặc định file được **truncate khi mở**, nên giờ chỉ còn `Q`.
5. `CREATE_NEW` từ chối mở đường dẫn đã tồn tại và ném `FileAlreadyExistsException`, bảo vệ chống ghi đè ngoài ý muốn.
6. `newInputStream` trên file thiếu ném `NoSuchFileException` theo provider mặc định, vì input stream **không tự tạo nguồn đọc**.
7. Khối `finally` dọn file và thư mục tạm do chương trình tạo, không động tới dữ liệu người dùng.

**Lưu ý về ngoại lệ:** ví dụ trình bày các subtype trên một filesystem thông dụng; hệ điều hành/provider khác có thể từ chối thao tác với `IOException` theo ngữ cảnh riêng. Không viết nghiệp vụ giả định mọi lỗi đều là `NoSuchFileException` hoặc `FileAlreadyExistsException`.

## 8. Ví dụ 2 — sao chép byte streaming, không tải toàn file vào RAM

Dùng `newInputStream` và `newOutputStream` để truyền byte theo các khối có kích thước giới hạn. Đây là tình huống thích hợp cho file lớn, ví dụ sao chép tệp nhị phân hoặc xử lý nội dung trước khi lưu.

Tạo tệp `StreamingCopyDemo.java`:

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class StreamingCopyDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("copy-stream-");
        Path source = dir.resolve("source.txt");
        Path dest = dir.resolve("dest.txt");
        String text = "Line 1\nTiếng Việt 😊\n";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
        try {
            try (OutputStream output = Files.newOutputStream(
                    source, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                output.write(encoded);
            }

            long copied = 0;
            try (InputStream input = Files.newInputStream(source);
                 OutputStream output = Files.newOutputStream(
                         dest, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                byte[] buffer = new byte[4];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    output.write(buffer, 0, count);
                    copied += count;
                }
            }

            System.out.println("copied all bytes=" + (copied == encoded.length));
            System.out.println("files equal=" + (Files.mismatch(source, dest) == -1));
            System.out.println("text preserved=" + text.equals(
                    Files.readString(dest, StandardCharsets.UTF_8)));
            System.out.println("bytes exceed UTF-16 units=" + (encoded.length > text.length()));
        } finally {
            Files.deleteIfExists(dest);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StreamingCopyDemo.java
java StreamingCopyDemo
```

```text
copied all bytes=true
files equal=true
text preserved=true
bytes exceed UTF-16 units=true
```

Mặc dù ví dụ khởi tạo sẵn một chuỗi ngắn làm dữ liệu thử, **vòng lặp copy** chỉ cần một buffer 4 byte ở thời điểm xử lý; với nguồn là file rất lớn, thuật toán không phải đọc hết file vào một mảng duy nhất.

Các nguyên tắc quan trọng:

- `input.read(buffer)` có thể trả ít hơn `buffer.length`. **Luôn ghi `output.write(buffer, 0, count)`**, không dùng `output.write(buffer)` nếu phần sau buffer còn dữ liệu cũ.
- EOF là `-1`; không dùng `available() == 0` để kết luận nguồn đã hết.
- Dữ liệu được sao chép ở **tầng byte**, giữ nguyên thứ tự các byte UTF-8, kể cả khi một ký tự nhiều byte bị chia giữa hai lượt đọc. Không giải mã từng khối rồi mã hóa tùy tiện nếu yêu cầu copy nhị phân chính xác.
- `Files.mismatch(source, dest)` (Java 12+) trả `-1` nếu không tìm thấy vị trí byte khác nhau giữa hai file tại thời điểm so sánh. Với file có thể bị sửa đồng thời, phép so sánh không tự bảo đảm snapshot nhất quán.
- `Files.size(path)` trả số **byte**; `text.length()` trả số UTF-16 code unit. Nội dung tiếng Việt và emoji minh họa hai kích thước này khác nhau.
- Stream phải được đóng. Nếu quá trình copy thất bại giữa chừng, file `dest` có thể **đã tồn tại nhưng chưa đủ nội dung**; nên có phương án file tạm + commit khi yêu cầu tính toàn vẹn.

Bộ đệm 4 byte chỉ để dễ quan sát và kiểm thử; trong ứng dụng hiệu năng, buffer vài KB hoặc lớn hơn thường phù hợp hơn, tùy nguồn và workload.

### Khi chỉ cần copy nguyên file: `Files.copy`

`Files.copy(source, target)` có thể đơn giản hơn việc tự mở hai stream, đặc biệt khi không cần biến đổi nội dung. `Files.copy` vẫn cần quyết định overwrite, metadata, symlink và các option khi phù hợp.

Nếu cần **lọc, mã hóa, nén, tính checksum từng khối** hoặc ghép dữ liệu theo giao thức, stream hữu ích vì caller có quyền kiểm soát từng đoạn byte. Chỉ nên tự viết loop khi việc kiểm soát đó có giá trị, không phải vì bắt buộc phải làm lại chức năng copy đã có.

## 9. Input/output stream là byte; đọc ghi text cần charset

`Files.newInputStream` trả về `InputStream`; nó **không có `readLine()`** và không giải mã Unicode. `Files.newOutputStream` trả về `OutputStream`; phương thức `write` chỉ ghi byte.

Để đọc text bằng các stream này, bọc qua:

- `InputStreamReader(input, charset)`: **giải mã byte thành UTF-16 `char`**.
- `OutputStreamWriter(output, charset)`: **mã hóa UTF-16 `char` thành byte**.
- `BufferedReader`/`BufferedWriter`: tối ưu thao tác ký tự nhỏ và hỗ trợ đọc dòng/`newLine()`.
- Nếu không cần quyền kiểm soát thấp ở tầng byte, `Files.newBufferedReader(path, charset)` và `Files.newBufferedWriter(path, charset, options...)` thường gọn hơn.

**Không viết `writer.write("Tiếng Việt".getBytes())` theo charset mặc định mơ hồ.** Hãy xác định charset theo format/giao thức, thường là `StandardCharsets.UTF_8`. Charset mặc định có thể thay đổi theo phiên bản Java, cấu hình runtime hoặc API cụ thể; sự rõ ràng tốt hơn việc hy vọng môi trường luôn giống máy phát triển.

### Ví dụ 3 — bọc byte stream bằng reader/writer UTF-8

Tạo tệp `StreamTextBridgeDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class StreamTextBridgeDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("charset-bridge-");
        Path file = dir.resolve("lines.txt");
        String first = "Xin chào";
        String second = "Java 😊";
        try {
            try (BufferedWriter writer = new BufferedWriter(
                    new OutputStreamWriter(Files.newOutputStream(
                            file, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                            StandardCharsets.UTF_8))) {
                writer.write(first);
                writer.write('\n');
                writer.write(second);
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(Files.newInputStream(file),
                            StandardCharsets.UTF_8))) {
                System.out.println("first matches=" + first.equals(reader.readLine()));
                System.out.println("second matches=" + second.equals(reader.readLine()));
                System.out.println("EOF=" + (reader.readLine() == null));
            }
            System.out.println("byte length larger than char count="
                    + (Files.size(file) > (first + "\n" + second).length()));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StreamTextBridgeDemo.java
java StreamTextBridgeDemo
```

```text
first matches=true
second matches=true
EOF=true
byte length larger than char count=true
```

**Diễn giải:**

1. `newOutputStream` mở file mới, `OutputStreamWriter` mã hóa ký tự theo UTF-8, `BufferedWriter` đệm việc ghi text.
2. Chương trình dùng literal `'\n'`, do đó dấu kết thúc dòng là **LF** bất kể hệ điều hành. Nếu muốn dấu xuống dòng theo nền tảng, có thể chọn `BufferedWriter.newLine()` thay vì `'\n'`.
3. Khi thoát `try-with-resources`, việc đóng `BufferedWriter` hoàn tất ghi dữ liệu đệm và đóng các lớp writer/stream bên dưới. Sau đó mở nguồn để đọc.
4. `InputStreamReader` giải mã đúng UTF-8; `BufferedReader.readLine()` đọc từng dòng và **bỏ dấu kết thúc dòng**. Lần thứ ba trả `null` vì EOF.
5. `Files.size(file)` đo byte; với tiếng Việt và emoji, byte UTF-8 nhiều hơn số UTF-16 code unit của chuỗi Java tương ứng.

**Điều cần phân biệt:** API byte stream không tự đặt newline, không tự chuyển encoding, không xác thực định dạng nghiệp vụ. Việc bọc writer/reader là quyết định của chương trình.

## 10. `try-with-resources`, `close()`, `flush()` và vòng đời file

`InputStream` và `OutputStream` là các kiểu `AutoCloseable`/`Closeable`, nên dùng `try-with-resources` để bảo đảm đóng:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    in.transferTo(out);
}
```

Đây là **đoạn minh họa**, cần có `Path source` và `Path target`, các import, cùng xử lý `IOException`. `InputStream.transferTo(OutputStream)` (Java 9+) truyền các byte còn lại đến EOF, trả tổng số byte đã chuyển; phương thức **không tự đóng** input hay output, vì vậy khối `try-with-resources` vẫn cần thiết.

### Khi nào `flush()` cần thiết?

`OutputStream.flush()` được dùng để đẩy dữ liệu đang đệm (nếu stream/wrapper có buffering) xuống tầng dưới. Một số stream có implementation `flush` gần như không làm gì; wrapper như `BufferedOutputStream` có dữ liệu đệm cần được đẩy ra.

**`flush()` không đồng nghĩa dữ liệu đã ghi bền vững xuống ổ đĩa**. Nếu ứng dụng yêu cầu durability khi mất điện, phải xem xét filesystem, `FileChannel.force(...)` hoặc `SYNC`/`DSYNC` theo hợp đồng và khả năng provider.

`close()` đóng stream. Khi stream là wrapper sở hữu stream bên dưới, đóng wrapper thường cũng đóng nguồn bên dưới; ví dụ `BufferedOutputStream` hoặc `OutputStreamWriter` bọc `newOutputStream`.

### Nếu ghi lỗi giữa chừng thì sao?

Nếu `OutputStream.write` ném `IOException` sau khi đã ghi một phần, không nên tự báo “file đã ghi thành công”. File đích có thể chỉ có **phần đầu nội dung**. Với file quan trọng, nên ghi vào file tạm, validate hoàn tất, rồi publish theo chiến lược move có kiểm soát.

**Không dựa vào thành công của `close()` như một phép xác thực nội dung.** Thành công ở tầng I/O không thay cho số byte kỳ vọng, checksum, cú pháp file hoặc kiểm tra bản ghi nghiệp vụ.

## 11. Buffering: khi nào nên bọc `BufferedInputStream`/`BufferedOutputStream`?

`Files.newInputStream` và `newOutputStream` cung cấp stream đọc/ghi byte. Khi chương trình đọc/ghi nhiều lần các đoạn nhỏ, buffering có thể giảm số lần gọi xuống hệ thống file:

```java
try (InputStream in = new BufferedInputStream(Files.newInputStream(source));
     OutputStream out = new BufferedOutputStream(Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE))) {
    byte[] block = new byte[8192];
    int n;
    while ((n = in.read(block)) != -1) {
        out.write(block, 0, n);
    }
}
```

Đây là **mã minh họa** cần import `BufferedInputStream`, `BufferedOutputStream`, `InputStream`, `OutputStream`, `Files`, `StandardOpenOption` và khai báo `source`/`target`.

- Buffer làm thay đổi **cách tổ chức thao tác I/O**, không thay đổi ý nghĩa byte.
- Ghi bằng `write(buffer, 0, n)` để tránh dữ liệu dư ở cuối mảng.
- Không coi buffer lớn luôn tốt hơn. Với nhiều stream đồng thời, bộ nhớ dành cho buffer cũng là tài nguyên.
- Khi đã dùng `Files.newBufferedReader`/`newBufferedWriter` cho text, API đã cung cấp buffering ký tự; không cần tự thêm nhiều tầng buffer mà không có lý do đo đạc.
- `BufferedInputStream` có khả năng `mark/reset` trong giới hạn phù hợp, khác với việc một `InputStream` bất kỳ đều hỗ trợ tua ngược.

Đối với sao chép nguyên file, có thể thử `Files.copy`, `InputStream.transferTo` hoặc các phương thức channel phù hợp, thay vì mặc định tự viết bộ đệm phức tạp.

## 12. Chọn `newInputStream/newOutputStream` hay API khác trong `Files`?

| Nhu cầu | API thường chọn | Vì sao |
|---|---|---|
| Đọc một file nhỏ thành mảng byte | `Files.readAllBytes(path)` | Gọn, nhưng giữ toàn bộ dữ liệu trong RAM |
| Ghi sẵn một mảng byte | `Files.write(path, bytes, options...)` | Trực tiếp, không tự viết loop |
| Đọc file lớn theo các khối byte | `Files.newInputStream(path)` | Kiểm soát bộ nhớ và từng khối |
| Ghi dữ liệu byte sinh dần | `Files.newOutputStream(path, options...)` | Không cần giữ toàn bộ output trước |
| Sao chép file không biến đổi | `Files.copy(source, target, options...)` | API copy trực tiếp, xử lý tùy chọn rõ |
| Đọc text nhỏ | `Files.readString(path, UTF_8)` | Gọn, charset tường minh |
| Ghi text nhỏ | `Files.writeString(path, text, UTF_8, options...)` | Gọn, có open options |
| Đọc text theo dòng | `Files.newBufferedReader(path, UTF_8)` hoặc `Files.lines` | Text/line API, không phải byte API |
| Ghi text từng dòng | `Files.newBufferedWriter(path, UTF_8, options...)` | Buffered character writer |
| Di chuyển vị trí đọc/ghi | `Files.newByteChannel`/`FileChannel` | Có khả năng position/seek |
| Khóa file hoặc đồng bộ qua channel | `FileChannel` và API tương ứng | Đặc tính vượt quá `InputStream`/`OutputStream` |
| Thao tác file tạm | `Files.createTempFile`, `createTempDirectory` | Giảm tự đặt tên đoán trước |

### Không dùng `newInputStream` cho nhu cầu “đọc bản ghi text”

Một byte trong UTF-8 không phải luôn là một ký tự. Nếu file chứa tiếng Việt và muốn xử lý theo **dòng**, dùng `BufferedReader` hoặc `Files.newBufferedReader`. Nếu đọc byte vì protocol, hãy để parser xác định framing và charset.

### Khi cần đọc-ghi đồng thời, vị trí ngẫu nhiên hoặc khóa file

`OutputStream` chỉ định hướng ghi tuần tự; `InputStream` chỉ định hướng đọc tuần tự. Nếu nghiệp vụ cần mở cùng file để đọc và ghi ở vị trí xác định hoặc cần `seek`, hãy xem `SeekableByteChannel`/`FileChannel` cùng tập `StandardOpenOption` tương ứng. **Không giả định các option mở channel đều có cùng semantics khi dùng với `newInputStream`/`newOutputStream`**.

## 13. File không tồn tại, quyền truy cập và exception

Nhiều tình huống lỗi cần được tách rõ:

- `NoSuchFileException`: một thao tác cần file có sẵn không tìm được mục tiêu.
- `FileAlreadyExistsException`: `CREATE_NEW` gặp đường dẫn đã tồn tại.
- `AccessDeniedException`: provider báo từ chối quyền truy cập.
- `IOException`: ngoại lệ tổng quát cho lỗi file, thiết bị, filesystem.
- `UnsupportedOperationException` / `IllegalArgumentException`: có thể xảy ra với option không được hỗ trợ hoặc kết hợp option không hợp lệ.
- `SecurityException`: có thể phát sinh từ kiểm tra security theo môi trường/provider, dù Java hiện đại đã thay đổi vai trò của Security Manager.

Không nên bắt `IOException` chung rồi trả chuỗi rỗng hoặc `false`, vì caller sẽ mất thông tin “đầu vào trống thật” khác “không thể đọc file”.

Ví dụ xử lý phần lỗi một cách có định hướng (mã minh họa, cần biến `target`):

```java
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    out.write(data);
} catch (FileAlreadyExistsException e) {
    // Báo người dùng: không ghi đè file đang có.
} catch (IOException e) {
    // Báo hoặc ghi log nguyên nhân I/O và xử lý thất bại.
}
```

Đoạn này cần `byte[] data` và các import. **Chú ý:** `CREATE_NEW` đảm bảo không thay thế file cũ nhưng nếu lỗi ở giữa quá trình ghi thì file mới có thể đã được tạo và chỉ có một phần dữ liệu; chiến lược dọn file lỗi tùy yêu cầu.

Một số filesystem hoặc provider không thể báo đúng subtype giống nhau, nên vẫn cần fallback xử lý `IOException`.

## 14. Parent directory, loại file và quyền filesystem

Mở output có `CREATE` hoặc `CREATE_NEW` **không tự tạo tất cả thư mục cha**. Nếu `Path.of("reports", "daily", "out.bin")` trỏ tới thư mục `reports/daily` chưa có, `newOutputStream` có thể thất bại dù bạn đã chọn `CREATE`.

Khi được phép tạo cấu trúc thư mục, chủ động:

```java
Path parent = target.toAbsolutePath().getParent();
Files.createDirectories(parent);
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    out.write(data);
}
```

Đây là **mã minh họa**; cần khai báo `target`, `data` và xử lý `IOException`. Không phải mọi đường dẫn do người dùng nhập đều được phép tạo thư mục; cần xác thực root và quyền sở hữu trước.

`Files.isRegularFile(path)`, `Files.isDirectory(path)` và `Files.isReadable(path)` có thể giúp giao diện báo trước trạng thái, nhưng **không bảo đảm** file vẫn giữ trạng thái đó đến lúc mở. Hãy xử lý kết quả thật của `newInputStream`/`newOutputStream`.

Trong môi trường có symbolic link, đường dẫn có thể được thay đổi giữa bước kiểm tra và thao tác. Đặc biệt, `CREATE_NEW` bảo vệ điều kiện tên file đích chưa tồn tại tại thời điểm tạo, nhưng không giải quyết toàn bộ vấn đề directory traversal, symlink ở thư mục cha hoặc quyền filesystem.

## 15. `CREATE_NEW`, tránh TOCTOU và bảo vệ dữ liệu hiện có

Một anti-pattern:

```java
if (!Files.exists(target)) {
    try (OutputStream out = Files.newOutputStream(target)) {
        out.write(data);
    }
}
```

Đây là **mã minh họa SAI nếu mục tiêu là không được ghi đè**: sau `exists`, tiến trình khác có thể tạo file. `newOutputStream(target)` mặc định `CREATE + TRUNCATE_EXISTING + WRITE` sẽ cắt ngắn dữ liệu mới tạo đó.

Cách phù hợp hơn khi chỉ muốn tạo mới:

```java
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
    out.write(data);
}
```

Đây là **mã minh họa đúng về điều kiện tạo mới**, cần có `target`, `data` và xử lý ngoại lệ. `CREATE_NEW` yêu cầu kiểm tra tồn tại và tạo mục mới là một thao tác nguyên tử theo contract. Nó không phải “khóa file toàn thời gian”, không bảo vệ khỏi thay đổi ở thư mục cha và không đảm bảo quá trình ghi thành công toàn bộ.

Khi ứng dụng ghi file quan trọng được công bố cho người khác, nên còn kiểm tra hoàn chỉnh payload, checksum hoặc yêu cầu nghiệp vụ, rồi mới đưa file vào vị trí đích. Đừng xem “đã tạo file thành công” như “đã có dữ liệu hoàn chỉnh”.

## 16. Ghi file tạm rồi công bố: khác biệt giữa truncate và atomic move

`Files.newOutputStream(path)` trực tiếp truncate file cũ. Nếu ứng dụng crash khi mới ghi được một nửa, file đích có thể mất nội dung ban đầu và chỉ còn bản không hoàn chỉnh.

Một chiến lược thực tế cho file cấu hình hoặc artifact quan trọng:

1. Tạo một file tạm trong thư mục phù hợp (`Files.createTempFile`), lý tưởng cùng filesystem với đích.
2. Mở file tạm để ghi đầy đủ nội dung; đóng stream, xử lý lỗi ghi.
3. Kiểm tra kích thước, checksum hoặc parse thử nếu định dạng yêu cầu.
4. Dùng `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE)` khi cần và được filesystem hỗ trợ.
5. Nếu gặp `AtomicMoveNotSupportedException`, quyết định rõ: **từ chối** nếu atomicity bắt buộc, hoặc thực hiện fallback không nguyên tử khi contract cho phép.
6. Dọn file tạm khi thất bại, đồng thời không vô tình xóa bản đã được công bố.

**Cảnh báo:** `ATOMIC_MOVE` không đồng nghĩa `fsync`/durability. Khi phải chống mất dữ liệu do mất điện, cần xem yêu cầu ghi đồng bộ file/thư mục và cơ chế filesystem. Với `ATOMIC_MOVE`, hành vi thay thế một đích đã tồn tại còn có khác biệt provider, nên phải kiểm tra contract khi bảo toàn dữ liệu quan trọng.

Có thể dùng `Files.writeString` vào temp với encoding rõ rồi move, hoặc dùng `newOutputStream` cho payload streaming. Đừng mặc định `REPLACE_EXISTING` hay fallback phá bảo đảm không ghi đè vốn đã được yêu cầu.

## 17. `APPEND` và vấn đề ghi đồng thời

`APPEND` định vị các lượt ghi tới **cuối file** theo semantics provider. Đây là lựa chọn cho nhật ký hoặc dồn nội dung mới vào file đã có. Nhưng có các điểm phải xác định:

- `APPEND` có **tự tạo file không**? Nếu muốn tạo khi file thiếu, truyền `CREATE, APPEND`. Nếu chỉ `APPEND`, có thể thất bại với file chưa tồn tại.
- `APPEND` **không tự chèn newline**. Hai lần ghi `"hello"` và `"world"` có thể thành `"helloworld"` nếu caller không tự quy định dấu phân cách.
- Việc định vị-cuối-file và ghi nội dung khi **nhiều tiến trình/thread** cùng append có phải nguyên tử hay không phụ thuộc filesystem/provider. Không thể tự khẳng định một dòng log được ghi trong nhiều `write` sẽ không bị chen dữ liệu của writer khác.
- Nếu muốn giữ thứ tự bản ghi, có thể cần một writer tập trung, khóa hoặc cơ chế logging/queue chuyên dụng.
- Nếu phải chống mất dữ liệu khi crash, cần thiết kế flush/sync; `APPEND` đơn lẻ không có nghĩa đã lưu bền vững.

Trên một file đã tồn tại, chỉ truyền `APPEND` giúp ghi cuối file; truyền `CREATE, APPEND` giúp tạo nếu thiếu. Không kết hợp `APPEND` với `TRUNCATE_EXISTING`.

## 18. EOF, partial read và incomplete output

`InputStream.read(buffer)` có thể nhận ít hơn kích thước buffer mà không báo lỗi. Vòng lặp đúng chỉ dừng tại `-1` (với yêu cầu length dương); output phải dùng đúng `n` byte đã đọc.

Nếu một **giao thức** yêu cầu header dài cố định hay payload dài N byte, việc đọc đến EOF có thể chưa đủ: ứng dụng phải đếm byte và xác nhận `actual == expected`. `InputStream.readNBytes(n)` có thể trả ít hơn n khi EOF; `DataInputStream.readFully(...)` ném `EOFException` khi không đủ. Đây là điều kiện ở tầng **định dạng**, không phải do chọn `newInputStream`.

Tương tự, `OutputStream.write(...)` có thể ném lỗi sau khi đã ghi một phần. Sau thất bại, không công bố output như một file hợp lệ nếu yêu cầu ghi đủ. Có thể kiểm tra kích thước và integrity sau khi đóng, tùy tình huống.

**`InputStream.available()` không phải phép kiểm tra EOF hay “số byte còn lại trong toàn file”.** Nó chủ yếu cho biết số byte có thể đọc mà không chặn theo đặc tính stream; không sử dụng nó làm điều kiện dừng hoặc kết luận file đã đọc đủ.

## 19. File đang bị sửa trong lúc đọc/ghi

Một stream mở từ file không tự tạo **snapshot bất biến** của nội dung. Nếu tiến trình khác sửa, cắt ngắn hoặc di chuyển file trong lúc thao tác, những gì caller thấy phụ thuộc filesystem, cách mở và thời điểm. Có thể xảy ra đọc thiếu, nội dung thay đổi hoặc exception; không được giả định một lần `Files.newInputStream` đảm bảo toàn bộ bản đọc nhất quán với file ở thời điểm mở.

Nếu cần snapshot hoặc version chính xác, cân nhắc:

- Cơ chế snapshot/immutable version ở tầng ứng dụng.
- Kiểm tra length và hash với giá trị kỳ vọng đáng tin.
- Quy ước không chỉnh sửa file đang được đọc hoặc dùng file lock trong môi trường thích hợp.
- File tạm và publish atomically khi ghi bản mới, với các giới hạn về atomicity/durability như phần trước.

`Files.size(path)` đọc độ dài ở một thời điểm; file có thể thay đổi ngay sau đó. Đừng dùng riêng kết quả `Files.size` để đảm bảo việc đọc sẽ luôn đúng số byte kỳ vọng.

## 20. Các lỗi thường gặp và cách tránh

1. **Quên rằng output mặc định truncate.** `Files.newOutputStream(path)` có thể xóa nội dung file đang có ngay khi mở. Dùng `CREATE_NEW` nếu tuyệt đối không ghi đè.
2. **Nghĩ `WRITE` một mình sẽ thay toàn bộ file.** Nó thường ghi từ đầu nhưng giữ phần đuôi cũ nếu không chọn truncate.
3. **Dùng `APPEND` nhưng mong tự tạo file mới.** Thêm `CREATE` khi hợp đồng yêu cầu tạo nếu thiếu.
4. **Dùng `APPEND` với `TRUNCATE_EXISTING`.** Hai mục đích trái nhau, kết hợp không hợp lệ.
5. **Dùng `CREATE` thay `CREATE_NEW` để tránh ghi đè.** `CREATE` không từ chối file đang tồn tại.
6. **Quên xác thực parent directory.** `CREATE` không tự tạo mọi thư mục cha; `Files.createDirectories` chỉ dùng sau khi xác minh được phép tạo.
7. **Quên đóng stream.** File descriptor/handle có thể rò rỉ; dùng `try-with-resources`.
8. **Quên `flush`/`close` của buffered writer.** Dữ liệu còn đệm có thể chưa được chuyển xuống dưới. Dùng đúng vòng đời sở hữu wrapper.
9. **Nghĩ `flush` là ghi bền vững xuống đĩa.** Durability cần cơ chế riêng; `SYNC`/`DSYNC` không đồng nghĩa mọi hệ thống đều đảm bảo giống nhau.
10. **Gọi `out.write(buffer)` sau short read.** Phần tử cũ chưa cập nhật trong buffer có thể bị ghi nhầm; dùng `write(buffer, 0, n)`.
11. **Dùng `newInputStream` đọc text rồi cast mỗi byte thành `char`.** UTF-8 có ký tự nhiều byte; giải mã bằng `InputStreamReader` hoặc `Files.newBufferedReader`.
12. **Dùng charset mặc định vô thức.** Chọn `StandardCharsets.UTF_8` hoặc charset do format quy định.
13. **Đọc cả file lớn bằng `Files.readAllBytes` mà không đo memory.** Streaming theo khối thường hợp lý hơn.
14. **Dùng `available() == 0` làm EOF.** Không an toàn; đọc đến `-1` hoặc dùng framing/length của format.
15. **Coi stream I/O là random access.** Cần `SeekableByteChannel`/`FileChannel` nếu phải di chuyển vị trí.
16. **Đặt `try-with-resources` nhưng không xử lý exception.** Đóng tự động không biến lỗi I/O thành thành công; vẫn phải xử lý `IOException`.
17. **Tưởng output stream tự ghi atomically.** File có thể mới chỉ được ghi một phần khi lỗi xảy ra.
18. **Tưởng `CREATE_NEW` giải quyết mọi symlink race.** Nó chỉ cam kết điều kiện tạo mới ở tên mục tiêu; đường dẫn cha và môi trường vẫn cần bảo vệ.
19. **Không kiểm thử trên filesystem thực tế.** Permissions, đặc tính provider, symbolic link và nguyên tử của append/move có thể khác nền tảng.
20. **Dùng một bộ OpenOption cho mọi API.** `newInputStream`, `newOutputStream` và `newByteChannel` có tập option/contract khác nhau.

## 21. Checklist trước khi triển khai

| Câu hỏi | Nếu câu trả lời là... | Chọn hoặc kiểm tra |
|---|---|---|
| Dữ liệu cần là byte hay text? | Text | Reader/writer với charset rõ hoặc `Files.readString/writeString` |
| File input phải có sẵn? | Có | `newInputStream`, xử lý thiếu/quyền truy cập |
| Output được phép ghi đè? | Không | `CREATE_NEW`, xử lý `FileAlreadyExistsException` |
| Output phải thay toàn bộ nội dung cũ? | Có | `TRUNCATE_EXISTING + WRITE`; cân nhắc file tạm nếu quan trọng |
| Output phải ghi thêm? | Có | `APPEND`; thêm `CREATE` nếu cho phép tạo mới |
| File lớn hoặc dữ liệu phát sinh từng phần? | Có | `newInputStream`/`newOutputStream` + block/transfer |
| Muốn đọc/ghi tại vị trí bất kỳ? | Có | `SeekableByteChannel`/`FileChannel` |
| Nhiều writer cùng ghi? | Có | Xác định chiến lược concurrency và bản ghi nguyên tử |
| Yêu cầu durability khi mất điện? | Có | Xem `SYNC`/`DSYNC`, force, filesystem và chiến lược recovery |
| Yêu cầu công bố bản hoàn chỉnh? | Có | File tạm, validate, move/publish có kiểm soát |
| Có đường dẫn do người dùng cung cấp? | Có | Validate root, symlink, quyền, race và giới hạn ghi |
| Kết quả cần đúng N byte? | Có | Đếm byte, kiểm tra EOF/integrity; không chỉ trông chờ stream đóng |

## 22. Tự kiểm tra kiến thức

**Câu 1.** Gọi `Files.newOutputStream(path)` khi file đã có dữ liệu, nhưng chưa gọi `write`. Nội dung file cũ có thể đã bị ảnh hưởng chưa?  
**Đáp án:** có. Mặc định output dùng `TRUNCATE_EXISTING` và có thể xóa nội dung khi mở thành công.

**Câu 2.** File ban đầu có `ABCDEF`, mở với `StandardOpenOption.WRITE` rồi ghi hai byte `XY`. Kết quả điển hình là gì?  
**Đáp án:** `XYCDEF` (mở ở đầu file, không tự truncate); khác với mở mặc định.

**Câu 3.** Muốn tạo file mới mà **không ghi đè** mục đã tồn tại, chọn `CREATE` hay `CREATE_NEW`?  
**Đáp án:** `CREATE_NEW`, vì nó từ chối khi đường dẫn đã tồn tại và điều kiện kiểm tra-tạo là nguyên tử theo contract.

**Câu 4.** `Files.newInputStream(path)` có tạo file nếu file thiếu không?  
**Đáp án:** không. Nó là API mở để đọc; caller phải xử lý lỗi thiếu nguồn.

**Câu 5.** Với output, có thể kết hợp `APPEND` và `TRUNCATE_EXISTING` để “xóa rồi nối” không?  
**Đáp án:** không. Hai option mâu thuẫn, không phải cách mở hợp lệ. Nếu muốn thay nội dung, dùng truncate; nếu muốn nối, dùng append.

**Câu 6.** Đọc file tiếng Việt bằng `Files.newInputStream` có tự trả `String` không?  
**Đáp án:** không. API trả byte stream; cần biết charset và giải mã khi muốn text.

**Câu 7.** Vòng lặp `read(buffer)` trả 7 trong khi buffer dài 4096. Có nên ghi cả mảng sang output không?  
**Đáp án:** không. Chỉ ghi `write(buffer, 0, 7)`.

**Câu 8.** Đóng stream có đảm bảo file output có đủ payload theo protocol và bền vững sau mất điện không?  
**Đáp án:** không. Cần kiểm tra số byte/format/integrity và cơ chế đồng bộ phù hợp với yêu cầu durability.

**Câu 9.** Với file lớn, khi nào `Files.readAllBytes` kém phù hợp hơn `newInputStream`?  
**Đáp án:** khi không muốn giữ toàn file trong RAM, cần xử lý từng khối hoặc truyền dữ liệu qua pipeline streaming.

**Câu 10.** Cần mở file để đọc/ghi theo vị trí ngẫu nhiên, có nên chọn `InputStream`/`OutputStream` làm API chính không?  
**Đáp án:** thường không. Dùng `SeekableByteChannel` hoặc `FileChannel` cho thao tác position/seek.

## Kết luận

**`Files.newInputStream(path)`** mặc định mở file **để đọc**, không tạo file khi thiếu. **`Files.newOutputStream(path)`** mặc định **`CREATE + TRUNCATE_EXISTING + WRITE`**, nên có thể tạo file mới **hoặc xóa nội dung cũ khi mở**. Khi cần hành vi khác, hãy truyền `StandardOpenOption` tường minh: `CREATE_NEW` để không ghi đè, `APPEND` để nối vào cuối, `CREATE` nếu cho phép tạo, `WRITE` và `TRUNCATE_EXISTING` khi thay nội dung có chủ đích.

Chọn byte stream cho dữ liệu nhị phân hoặc streaming dung lượng lớn, kết hợp reader/writer và charset rõ khi xử lý text. Luôn dùng `try-with-resources`, kiểm tra read/write lỗi, phân biệt flush với durability, và không đánh đồng mở stream thành công với tính nguyên vẹn của file cuối cùng.

### Tài liệu Java SE 17

- [`Files` — `newInputStream` và `newOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [`OpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/OpenOption.html)
- [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [`BufferedInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html) và [`BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html)
- [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) và [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [`FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html), [`SeekableByteChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SeekableByteChannel.html)
