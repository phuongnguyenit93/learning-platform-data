# `Files.copy` kết hợp `InputStream` hoặc `OutputStream` trong Java

Lớp `java.nio.file.Files` không chỉ sao chép **tệp sang tệp**. Nó còn cung cấp hai overload để chuyển dữ liệu giữa **đường dẫn tệp (`Path`)** và **luồng byte (`InputStream` hoặc `OutputStream`)**:

~~~java
long bytesToFile = Files.copy(inputStream, destinationPath);
long bytesFromFile = Files.copy(sourcePath, outputStream);
~~~

Nhờ đó, chương trình có thể lưu nội dung từ một luồng nhập vào tệp, hoặc gửi nội dung tệp tới một luồng xuất đã có sẵn. Ví dụ: tải byte về từ một nguồn, ghi báo cáo vào nơi nhận do caller quản lý, gửi tệp qua socket, hoặc xuất tệp vào một luồng bộ nhớ để kiểm thử.

Để sử dụng đúng, cần phân biệt **chiều dữ liệu**, **giá trị trả về**, **chính sách tệp đích tồn tại**, **quyền sở hữu stream** và **lỗi có thể xảy ra khi mới ghi được một phần**.

## 1. Ba nhóm overload `Files.copy` dễ nhầm

`Files` có ba hướng sao chép thường dùng:

| Chữ ký rút gọn | Dữ liệu đi từ đâu đến đâu? | Giá trị trả về |
|---|---|---|
| `Files.copy(InputStream in, Path target, CopyOption... options)` | **Luồng nhập → tệp đích** | `long` — số byte đã sao chép |
| `Files.copy(Path source, OutputStream out)` | **Tệp nguồn → luồng xuất** | `long` — số byte đã sao chép |
| `Files.copy(Path source, Path target, CopyOption... options)` | **Tệp nguồn → tệp đích** | `Path` — đường dẫn tệp đích |

Điểm quan trọng là overload được chọn dựa trên **kiểu tham số**, không dựa vào tên biến.

~~~text
1) InputStream ---- Files.copy ----> Path (tệp mới/tệp được thay thế)
2) Path (tệp) ---- Files.copy ----> OutputStream
3) Path (tệp) ---- Files.copy ----> Path (tệp)
~~~

Ví dụ:

~~~java
// in là InputStream; file là Path; out là OutputStream.
long first = Files.copy(in, file);
long second = Files.copy(file, out);
~~~

Đây là **đoạn minh họa**, không chạy độc lập nếu chưa có biến `in`, `file`, `out` và chưa xử lý `IOException`. Ở overload đầu, `file` đóng vai **đích**; ở overload thứ hai, chính `file` đóng vai **nguồn**. Cả hai kết quả kiểu `long` đều đo số **byte**, không phải số ký tự hay số dòng.

## 2. `Files.copy(InputStream, Path)`: lưu byte của stream vào tệp

Cú pháp:

~~~java
long count = Files.copy(sourceStream, targetPath);
~~~

Cách hoạt động theo hợp đồng API:

1. `sourceStream` là nguồn byte đang ở **vị trí đọc hiện tại**.
2. `targetPath` xác định tệp đích mà `Files` sẽ tạo/ghi.
3. Phương thức sao chép các byte từ nguồn đến **cuối luồng** vào tệp đích.
4. Trả về số byte đã chuyển khi hoàn tất.
5. **Không tự đóng `sourceStream`**. Caller vẫn chịu trách nhiệm vòng đời nguồn byte đó.

Nếu `InputStream` đã được đọc trước, chỉ **phần byte còn lại** được sao chép. Nếu nguồn đã ở EOF, số byte sao chép có thể bằng `0`, nhưng lưu ý tệp đích vẫn chịu chính sách tạo/thay thế tương ứng.

Ví dụ:

~~~java
try (InputStream source = new ByteArrayInputStream(
        "Hello".getBytes(StandardCharsets.UTF_8))) {
    long bytes = Files.copy(source, Path.of("hello.txt"));
    System.out.println(bytes); // 5
}
~~~

Đây là một **đoạn code cần đặt trong phương thức** có thể ném `IOException`, với import `java.io.*`, `java.nio.file.*` và `java.nio.charset.StandardCharsets`. `ByteArrayInputStream` không dùng tài nguyên tệp của hệ điều hành; `try-with-resources` ở đây minh họa rằng **caller**, không phải `Files.copy`, quyết định thời điểm đóng input.

### Tệp đích đã tồn tại thì sao?

Với overload `InputStream → Path`, theo mặc định, nếu tệp đích **đã tồn tại**, thao tác sao chép sẽ **thất bại**, thường bằng `FileAlreadyExistsException`. Có thể chủ động cho phép thay thế bằng:

~~~java
long count = Files.copy(
        sourceStream,
        targetPath,
        StandardCopyOption.REPLACE_EXISTING);
~~~

Đây là **đoạn minh họa** và `sourceStream` do caller cấp. Tùy chọn `REPLACE_EXISTING` cho phép thay thế tệp đích theo hợp đồng `Files.copy`. Điều này có thể **làm mất nội dung cũ** nếu bạn chưa có bản sao dự phòng. Không coi nó là thao tác bổ sung vào cuối file.

Với **riêng overload `Files.copy(InputStream, Path, ...)`**, `REPLACE_EXISTING` là tùy chọn sao chép được hỗ trợ theo hợp đồng Java SE 17; đừng áp dụng máy móc các option của `Path → Path` như `COPY_ATTRIBUTES` hoặc `NOFOLLOW_LINKS` vào overload này. Những lựa chọn không được hỗ trợ có thể gây `UnsupportedOperationException`.

Nếu tệp đích tồn tại nhưng không thể ghi, hoặc parent directory không tồn tại/không có quyền, thao tác cũng có thể thất bại vì lý do I/O. `REPLACE_EXISTING` không phải lệnh “bỏ qua mọi vấn đề về quyền và đường dẫn”.

### `Files` có đóng output tệp do nó tự mở không?

Với overload `InputStream → Path`, `Files` tự thực hiện phần mở/ghi tệp đích trong phạm vi thao tác của nó. **Caller không nhận một `OutputStream` tệp đích để phải tự đóng.** Ngược lại, `sourceStream` là stream bên ngoài truyền vào, nên `Files.copy` **không đóng** nó. Nếu nguồn là tài nguyên do mình mở như `Files.newInputStream(...)` hoặc stream mạng, caller đóng đúng lúc theo ownership.

## 3. `Files.copy(Path, OutputStream)`: chuyển byte từ tệp ra stream

Cú pháp:

~~~java
long count = Files.copy(sourcePath, destinationStream);
~~~

Ý nghĩa:

- `sourcePath` là đường dẫn tới tệp **nguồn**.
- `destinationStream` là nơi nhận **byte** đã do caller tạo hoặc được một tầng khác cấp.
- `Files` đọc nội dung tệp nguồn và ghi vào output stream.
- Kết quả kiểu `long` là số byte đã ghi.
- **`destinationStream` không bị đóng bởi `Files.copy`**.

Ví dụ:

~~~java
ByteArrayOutputStream captured = new ByteArrayOutputStream();
long bytes = Files.copy(Path.of("hello.txt"), captured);
System.out.println("Copied: " + bytes);
System.out.println(captured.toString(StandardCharsets.UTF_8));
~~~

Đây là **đoạn minh họa** với tệp `hello.txt` phải có sẵn, thêm import và xử lý `IOException`. `ByteArrayOutputStream` lưu byte trong RAM để kiểm thử hoặc truyền cho xử lý tiếp theo.

Với output là `System.out` hoặc một output của socket, nguyên tắc ownership càng quan trọng:

~~~java
Files.copy(Path.of("report.bin"), System.out);
System.out.flush(); // Chỉ flush khi hợp đồng của nơi nhận yêu cầu.
// Không System.out.close() trong helper chỉ dùng tạm.
~~~

Đoạn này chỉ minh họa: nó có thể **in byte nhị phân không đọc được** ra terminal nếu file không phải văn bản. `Files.copy` không giải mã hay đổi charset.

### Luồng xuất có thể đã có dữ liệu

`Files.copy(Path, OutputStream)` ghi byte vào **vị trí và trạng thái hiện tại** của `destinationStream`; nó không mang ý nghĩa “xóa sạch output và bắt đầu một tệp mới”. Với `ByteArrayOutputStream`, nếu đã ghi `prefix` trước đó thì byte sao chép được thêm vào sau `prefix`. Với file output, việc ghi đè hay nối tiếp phụ thuộc cách caller đã **mở output** (`CREATE`, `TRUNCATE_EXISTING`, `APPEND`, ...), không phải tham số của overload `Path → OutputStream`.

Cũng không nên giả định `Files.copy` sẽ tự `flush()` stream do caller truyền vào. Nếu output có buffer, việc flush/close theo giao thức và ownership là trách nhiệm của bên sở hữu.

## 4. Ví dụ Java 17 hoàn chỉnh: hai chiều copy và sở hữu stream

Chương trình sau chứng minh bằng code rằng:

- `Files.copy(InputStream, Path)` ghi byte từ input vào tệp, nhưng **không đóng input**.
- `Files.copy(Path, OutputStream)` gửi byte tệp sang output, nhưng **không đóng output**.
- Caller vẫn ghi thêm được vào output sau copy.
- Ghi vào một tệp đích đã tồn tại **không có `REPLACE_EXISTING`** gây `FileAlreadyExistsException`.
- Có `REPLACE_EXISTING` thì nội dung tệp được thay thế.
- Tất cả file/directory tạm do chương trình tạo được dọn sau khi sử dụng.

Lưu thành **`FilesCopyStreamsDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class FilesCopyStreamsDemo {
    static final class TrackedInput extends FilterInputStream {
        boolean closed;

        TrackedInput(InputStream source) {
            super(source);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;

        TrackedOutput(OutputStream destination) {
            super(destination);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-streams-");
        Path targetFile = directory.resolve("target.txt");

        try {
            TrackedInput input = new TrackedInput(
                    new ByteArrayInputStream(
                            "Java I/O".getBytes(StandardCharsets.UTF_8)));
            try (input) {
                long bytes = Files.copy(input, targetFile);
                System.out.println("To file: " + bytes);
                System.out.println("Input closed by copy: " + input.closed);
            }
            System.out.println("Input closed by owner: " + input.closed);

            ByteArrayOutputStream captured = new ByteArrayOutputStream();
            TrackedOutput output = new TrackedOutput(captured);
            try (output) {
                long bytes = Files.copy(targetFile, output);
                System.out.println("From file: " + bytes);
                System.out.println("Output closed by copy: " + output.closed);

                output.write('!');
                output.flush();
            }
            System.out.println("Output closed by owner: " + output.closed);
            System.out.println("Captured: "
                    + captured.toString(StandardCharsets.UTF_8));

            try (InputStream second = new ByteArrayInputStream(
                    "Updated".getBytes(StandardCharsets.UTF_8))) {
                try {
                    Files.copy(second, targetFile);
                } catch (FileAlreadyExistsException ex) {
                    System.out.println(
                            "Existing target: FileAlreadyExistsException");
                }
            }

            try (InputStream replacement = new ByteArrayInputStream(
                    "Updated".getBytes(StandardCharsets.UTF_8))) {
                long bytes = Files.copy(replacement, targetFile,
                        StandardCopyOption.REPLACE_EXISTING);
                System.out.println("Replaced bytes: " + bytes);
            }
            System.out.println("File after replace: "
                    + Files.readString(targetFile, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(targetFile);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 FilesCopyStreamsDemo.java
java FilesCopyStreamsDemo
~~~

**Output dự kiến** trong môi trường có quyền tạo/xóa thư mục tạm:

~~~text
To file: 8
Input closed by copy: false
Input closed by owner: true
From file: 8
Output closed by copy: false
Output closed by owner: true
Captured: Java I/O!
Existing target: FileAlreadyExistsException
Replaced bytes: 7
File after replace: Updated
~~~

Giải thích:

1. Chuỗi `Java I/O` có 8 byte ASCII/UTF-8. `Files.copy(input, targetFile)` sao chép 8 byte vào tệp mới và trả `8L`.
2. `TrackedInput.closed` bằng `false` ngay sau lần copy vì `Files.copy` **không đóng nguồn input** được truyền vào. Khi rời `try (input)`, caller đóng input và cờ thành `true`.
3. `Files.copy(targetFile, output)` sao chép 8 byte tệp sang output. Trước khi caller đóng output, cờ vẫn `false` và `output.write('!')` tiếp tục hoạt động.
4. Đóng `TrackedOutput` bằng `try (output)` làm cờ thành `true`. `ByteArrayOutputStream` cho phép lấy nội dung đã ghi ngay cả sau khi bị đóng; không suy rộng hành vi này sang file/socket.
5. Sao chép lần hai tới **cùng tệp đang tồn tại** mà không có option thay thế sẽ ném `FileAlreadyExistsException`. Ví dụ bắt riêng ngoại lệ dự kiến để tiếp tục.
6. `REPLACE_EXISTING` cho phép ghi `Updated` (7 byte) thay cho nội dung cũ. `Files.readString(targetFile, UTF_8)` đọc lại để xác minh.
7. `finally` xóa file và thư mục tạm nếu thao tác môi trường cho phép. Nếu filesystem gặp lỗi, IOException vẫn phải được xem xét; ví dụ không giả định mọi hệ thống có quyền ghi vào thư mục tạm.

Đây là ví dụ có `main` chạy độc lập trên Java 17+, dùng đường dẫn tạm nên không yêu cầu file đầu vào có sẵn. Nó kiểm tra **lời gọi đóng trên wrapper** bằng biến `closed`, không phải công cụ đo trạng thái file descriptor của hệ điều hành.

## 5. So sánh với `InputStream.transferTo(OutputStream)`

Một phương án sao chép khác có từ Java 9 là:

~~~java
long count = input.transferTo(output);
~~~

`transferTo` sao chép **byte còn lại** từ `InputStream` sang `OutputStream`, không tự đóng cả hai stream. Nó khác các overload `Files.copy` ở loại đích/nguồn:

| Tác vụ | Cách ngắn gọn | Ai quản lý stream ngoài? |
|---|---|---|
| InputStream đã có → tệp đích | `Files.copy(input, path)` | Caller quản lý **input** |
| Tệp nguồn → OutputStream đã có | `Files.copy(path, output)` | Caller quản lý **output** |
| InputStream đã có → OutputStream đã có | `input.transferTo(output)` | Caller quản lý **cả hai** |
| Tệp nguồn → tệp đích | `Files.copy(from, to)` | `Files` quản lý thao tác qua hai `Path` |

Nếu bạn tự mở hai đầu luồng của một thao tác sao chép, có thể chọn:

~~~java
try (InputStream input = Files.newInputStream(from);
     OutputStream output = Files.newOutputStream(to)) {
    input.transferTo(output);
}
~~~

Đây là **đoạn minh họa**: `from` và `to` là `Path`, `Files.newOutputStream(to)` có chính sách tạo/cắt ngắn tệp mặc định **khác** chính sách mặc định của `Files.copy(InputStream, to)` khi tệp đích đã tồn tại. Vì vậy hai cách không phải tương đương tuyệt đối về **xử lý tệp đích có sẵn**, dù cùng truyền các byte.

Dùng `Files.copy` theo đúng overload nếu bạn muốn **Files tự quản lý đầu tệp** và caller chỉ cần quản lý đầu stream mà mình có.

## 6. Quyền sở hữu tài nguyên và đóng luồng

Khi làm việc với stream, câu hỏi quan trọng là: **ai mở, ai sở hữu và ai được phép đóng?**

### InputStream truyền vào `Files.copy(input, path)`

~~~java
static long save(Path target, InputStream source) throws IOException {
    return Files.copy(source, target);
}
~~~

Nếu hàm này chỉ **mượn** `source` từ caller, nó **không đóng** nguồn. Caller có thể tự mở file, socket, hoặc cấp luồng dữ liệu theo vòng đời khác. Khi viết JavaDoc cho hàm, nên nêu rõ: “Phương thức sao chép byte còn lại và **không đóng source**”.

Nếu ứng dụng **chủ động chuyển quyền sở hữu** source cho hàm, hàm có thể được thiết kế để đóng source khi kết thúc, nhưng cần hợp đồng rõ; không tự ý thêm `try (source)` vào một helper đang được dùng theo quy tắc mượn.

### OutputStream truyền vào `Files.copy(path, output)`

~~~java
static long send(Path source, OutputStream destination)
        throws IOException {
    return Files.copy(source, destination);
}
~~~

Hàm này cũng **không đóng** output khi chỉ mượn. Ví dụ `send(file, System.out)` không nên đóng `System.out`, bởi những thành phần khác trong chương trình có thể còn in log hoặc kết quả sau đó.

Nếu output đã bọc bằng `BufferedOutputStream`, caller sở hữu lớp bọc và quyết định thời điểm `flush`/`close`. `Files.copy` không có quyền quyết định thời điểm kết thúc toàn bộ nơi nhận.

### Vì sao `try-with-resources` phải đặt đúng chỗ?

**Đúng — caller tự mở, caller tự đóng:**

~~~java
try (InputStream in = Files.newInputStream(sourceFile)) {
    long count = Files.copy(in, newFile);
}
~~~

**Sai nếu helper đang mượn stream của người khác:**

~~~java
static long saveBorrowed(InputStream fromCaller, Path target)
        throws IOException {
    try (InputStream borrowed = fromCaller) {
        return Files.copy(borrowed, target);
    } // Đóng luôn stream của caller!
}
~~~

`try-with-resources` làm đúng việc mà nó được thiết kế: đóng các tài nguyên đã khai báo. Nhưng việc **khai báo một tài nguyên được mượn trong try** có thể vi phạm ownership. Đổi tên `borrowed` không tạo một stream mới hay chuyển quyền sở hữu.

## 7. Copy là byte I/O, không phải tự chuyển mã văn bản

`Files.copy` với `InputStream` hoặc `OutputStream` sao chép **byte nguyên trạng**. Nó không phân biệt file là ảnh, ZIP, PDF, CSV hay văn bản; không tự giải mã ký tự.

Ví dụ một chuỗi tiếng Việt:

~~~java
byte[] bytes = "Cà phê".getBytes(StandardCharsets.UTF_8);
try (InputStream input = new ByteArrayInputStream(bytes)) {
    Files.copy(input, Path.of("coffee.txt"));
}
~~~

Tệp đích nhận **byte UTF-8 do chính đoạn code tạo**, chứ không phải do `Files.copy` chọn charset. Nếu đầu vào vốn được mã hóa bằng một charset khác, `Files.copy` vẫn sao chép đúng byte của charset đó; muốn đọc thành `String` phải biết charset nguồn tương ứng.

Khi cần **chuyển mã** từ một charset sang charset khác, phải giải mã byte thành ký tự rồi mã hóa lại theo charset đích, ví dụ sử dụng `InputStreamReader`/`OutputStreamWriter` với charset tường minh. Tuyệt đối không dùng chuyển đổi ký tự nếu mục tiêu là sao chép dữ liệu nhị phân nguyên trạng.

## 8. Sao chép tệp lớn, stream chậm và xử lý lỗi

Một lời gọi `Files.copy` có thể xử lý lượng byte lớn mà không cần tự tạo `byte[]` chứa toàn bộ dữ liệu. Tuy nhiên, nó không phải phép toán nguyên tử:

- **Byte có thể được ghi một phần rồi mới gặp lỗi.** Với `InputStream → Path`, tệp đích có thể đã tồn tại ở trạng thái chưa hoàn chỉnh khi `IOException` xảy ra. Với `Path → OutputStream`, output caller cũng có thể đã nhận một phần byte.
- **Tác vụ có thể chặn.** Đọc từ socket hoặc pipe khi bên gửi chưa kết thúc dữ liệu có thể khiến `Files.copy(input, path)` chờ tiếp. Nếu input không bao giờ báo EOF, sao chép có thể kéo dài không xác định.
- **Thiếu dung lượng hoặc lỗi quyền:** có thể khiến ghi file đích thất bại. Hãy có chiến lược cleanup, kiểm tra dữ liệu sau ghi và phản hồi người dùng.
- **Không dùng return `long` như checksum:** hai tệp cùng số byte không chứng minh nội dung bằng nhau. Khi cần xác thực toàn vẹn, cân nhắc checksum/hash theo thiết kế giao thức.
- **Không dùng để giới hạn kích thước nguồn tự động:** các overload nêu trên không có tham số “chỉ copy tối đa N byte”. Với input không tin cậy, thiết kế một luồng giới hạn hoặc vòng copy có kiểm soát kích thước trước/sau, tùy yêu cầu.

### Tránh phá file nguồn và file đích trùng nhau

Một sai lầm nguy hiểm là tự mở `OutputStream` trên **chính tệp nguồn**, chẳng hạn:

~~~java
Path file = Path.of("data.bin");
try (OutputStream output = Files.newOutputStream(file)) {
    Files.copy(file, output); // NGUY HIỂM!
}
~~~

Đây là **đoạn minh họa cần tránh**. `Files.newOutputStream(file)` theo mặc định có thể **cắt ngắn tệp ngay khi mở**, trước khi `Files.copy` kịp đọc. Khi cần copy file sang file, nên dùng `Files.copy(Path, Path, ...)` với **đường dẫn nguồn và đích riêng biệt**, cùng chính sách khi đích tồn tại phù hợp.

### Sao chép an toàn khi không muốn file cũ bị hỏng

Nếu cần xuất dữ liệu vào một file đang được người dùng sử dụng, thường nên:

1. Chọn file tạm trong thư mục phù hợp.
2. Sao chép toàn bộ dữ liệu vào file tạm; xử lý lỗi và dọn file tạm nếu không hoàn thành.
3. Kiểm tra/validate dữ liệu theo hợp đồng ứng dụng.
4. Thay thế file đích theo một cơ chế phù hợp filesystem và yêu cầu về atomicity/durability.

`Files.move` với `ATOMIC_MOVE` có thể dùng khi provider hỗ trợ, nhưng **không được mặc định mọi filesystem hỗ trợ atomic move**. Không nhầm `REPLACE_EXISTING` của `Files.copy` với thao tác cập nhật nguyên tử, và cũng không coi `flush` là bảo đảm fsync.

## 9. Dùng `Files.copy(Path, Path)` khi cả hai đầu đều là tệp

Nếu đã có hai đường dẫn tệp và không cần can thiệp stream ở giữa:

~~~java
Path result = Files.copy(
        from,
        to,
        StandardCopyOption.REPLACE_EXISTING);
~~~

Đây là **đoạn minh họa** với hai biến `Path` và xử lý `IOException`. Giá trị trả về là `Path`, **không phải số byte**. Overload `Path → Path` có thêm các lựa chọn đặc thù, như `COPY_ATTRIBUTES` hoặc `LinkOption.NOFOLLOW_LINKS` tùy định dạng và hệ thống tệp. Không nhầm các option này với các overload nhận `InputStream`/`OutputStream`.

Lưu ý: `Files.copy(Path, Path)` có hợp đồng riêng khi source là directory hoặc symbolic link; việc copy một directory **không tự động sao chép đệ quy toàn bộ cây**. Khi làm việc với thư mục hay liên kết mềm, hãy đọc đúng Javadoc của overload và tùy chọn tương ứng.

## 10. Các lỗi thường gặp và cách sửa

| Sai lầm | Vấn đề | Cách sửa |
|---|---|---|
| Gọi `Files.copy(input, path)` và cho rằng input bị đóng | API không đóng stream input đã cấp | Caller quản lý input bằng `try-with-resources` khi sở hữu |
| Gọi `Files.copy(path, out)` rồi cho rằng output bị đóng | Output vẫn thuộc caller | Caller flush/close theo vòng đời của mình |
| Dùng `Files.copy(InputStream, Path)` khi tệp đích đã tồn tại nhưng không có `REPLACE_EXISTING` | Có thể nhận `FileAlreadyExistsException` | Xác định rõ chính sách tránh ghi đè hay thay thế |
| Đưa `COPY_ATTRIBUTES` vào overload InputStream → Path | Không phải tùy chọn được overload này hỗ trợ | Dùng `REPLACE_EXISTING` khi cần hoặc chọn Path → Path |
| Nhầm giá trị trả về của cả ba overload | Path → Path trả `Path`; hai overload stream trả `long` | Kiểm tra chữ ký và kiểu |
| Cố giải mã byte trong quá trình sao chép file ảnh/ZIP | Phá nội dung nhị phân | Copy byte trực tiếp |
| Coi byte count bằng nhau là toàn vẹn dữ liệu | Cùng dung lượng có thể khác nội dung | Kiểm tra hash/chữ ký hoặc đối chiếu theo giao thức |
| Để helper đóng stream được caller truyền vào | Tầng khác có thể mất quyền đọc/ghi | Định nghĩa ownership rõ, không close stream mượn |
| Mở output trên cùng file trước khi copy từ file đó | Có thể cắt ngắn nguồn | Phân biệt source/destination, đừng mở đích phá nguồn |
| Dùng `Files.copy` cho luồng dữ liệu vô hạn mà không kiểm soát | Có thể chặn hoặc tiêu thụ hết dung lượng | Có giới hạn byte, timeout/cancel theo tầng thích hợp |
| Giả định copy lỗi thì file đích luôn nguyên vẹn | Có thể để lại byte đã ghi một phần | Dùng file tạm/cleanup và chiến lược cập nhật an toàn |

## 11. Tự kiểm tra

**Câu 1.** Có một `InputStream` do HTTP client cung cấp và muốn lưu vào `download.bin` chưa tồn tại. Nên gọi overload nào? Ai đóng input?

> Dùng `Files.copy(input, path)` để truyền byte vào file đích. **Bên sở hữu stream HTTP** theo hợp đồng của client phải đóng input; `Files.copy` không tự đóng nó.

**Câu 2.** Có file `archive.zip` và muốn gửi nguyên byte vào `OutputStream` do caller cung cấp. Nên dùng gì?

> `Files.copy(Path.of("archive.zip"), output)` trả số byte đã truyền. Vì `output` do caller quản lý, không được tự đóng output trong helper chỉ mượn.

**Câu 3.** `Files.copy(InputStream, Path)` đang ghi vào tệp đã tồn tại; vì sao phải cân nhắc `REPLACE_EXISTING`?

> Theo mặc định thao tác thất bại khi đích tồn tại. `REPLACE_EXISTING` cho phép thay thế, nhưng có thể làm mất dữ liệu cũ và không tự biến copy thành cập nhật nguyên tử.

**Câu 4.** Gọi `Files.copy(pathA, pathB)` và `Files.copy(pathA, output)` thì hai kết quả cùng kiểu gì?

> **Không.** `Path → Path` trả `Path` của đích; `Path → OutputStream` trả `long` số byte.

**Câu 5.** `Files.copy(sourceFile, System.out)` có tự biến PDF thành văn bản dễ đọc không? Có nên đóng `System.out` ngay sau đó?

> **Không.** Copy giữ nguyên byte nhị phân; PDF không được chuyển thành text. Và `System.out` là stream chung, helper không được tự ý đóng.

**Câu 6.** Gọi `Files.copy(input, path)` được `1024L`. Điều này chứng minh điều gì và chưa chứng minh điều gì?

> Nó báo đã sao chép 1024 **byte** thành công theo giá trị trả về. Nó **không chứng minh** nội dung ứng với một checksum dự kiến, không bảo đảm bền vững trên thiết bị hoặc đầu vào ban đầu phải có đúng 1024 byte nếu stream đã đọc trước một phần.

## Ghi nhớ

- **`Files.copy(InputStream, Path, ...)`:** sao chép byte từ **luồng vào → tệp**, trả `long`, **không đóng input**, mặc định không ghi đè đích tồn tại.
- **`Files.copy(Path, OutputStream)`:** sao chép byte từ **tệp → luồng ra**, trả `long`, **không đóng output**.
- **`Files.copy(Path, Path, ...)`:** sao chép **tệp → tệp**, trả `Path`; các tùy chọn có hợp đồng riêng.
- **`InputStream.transferTo(OutputStream)`:** dành cho trường hợp cả hai đầu đã là stream; **không đóng hai đầu**.
- **Sao chép byte không chọn charset**; stream do bên nào sở hữu thì bên đó chịu trách nhiệm vòng đời.
- **I/O có thể thất bại sau khi ghi một phần**: thiết kế ghi đè, cleanup và xác thực dữ liệu theo yêu cầu thực tế.

**Tham khảo:** [Java SE 17 — `Files.copy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`InputStream.transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)), [`StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).