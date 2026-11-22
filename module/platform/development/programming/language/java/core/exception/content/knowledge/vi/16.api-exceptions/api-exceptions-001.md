# IOException, FileNotFoundException và lỗi đọc ghi trong Java

## 1. Bức tranh tổng quan

Đọc và ghi dữ liệu là những tác vụ thường xuyên phải làm việc với **tài nguyên bên ngoài**: tệp, thiết bị, socket, hệ thống tệp mạng, luồng dữ liệu hoặc các API cung cấp input/output. Những thao tác ấy có thể thất bại bởi các nguyên nhân không hoàn toàn do chương trình kiểm soát: tệp không tồn tại, mất quyền truy cập, đường dẫn không hợp lệ, thiết bị ngắt kết nối, hết dung lượng lưu trữ, lỗi giải mã, hoặc lỗi ngay cả khi đóng tài nguyên.

Trong Java, nhóm lỗi được đại diện nổi bật bằng **`java.io.IOException`**, là **checked exception**. Một lớp con quen thuộc là **`java.io.FileNotFoundException`**, thường xuất hiện khi mã dùng các API I/O cổ điển để mở tệp thất bại. Trong API hiện đại **NIO.2** (`java.nio.file.Files`, `Path`), lỗi cụ thể thường được diễn đạt bởi các lớp khác như `NoSuchFileException`, `AccessDeniedException` hoặc `FileAlreadyExistsException`, cũng nằm trong nhánh `IOException`.

Mục tiêu sau bài học:

- Phân biệt `IOException`, `FileNotFoundException` và một số ngoại lệ liên quan tới tệp trong `java.nio.file`.
- Hiểu **checked exception**: lời gọi phương thức phải `catch` hoặc khai báo `throws` khi cần.
- Biết vì sao `FileNotFoundException` không phải lời giải thích duy nhất cho mọi sự cố I/O và vì sao Java NIO.2 có thể ném `NoSuchFileException`.
- Phân biệt **kết thúc dữ liệu bình thường (EOF)** với một **lỗi đọc thực sự**.
- Mở, đọc, ghi, đóng file an toàn bằng `Files`, `InputStream`, `OutputStream`, `Reader`, `Writer` và `try-with-resources`.
- Giữ được lỗi chính, lỗi dọn dẹp và `cause` khi có nhiều thất bại.
- Biết những tình huống cần kiểm tra đường dẫn, charset, quyền sở hữu tài nguyên, chế độ ghi và chiến lược phục hồi.
- Viết thông báo lỗi/log rõ ngữ cảnh nhưng không suy đoán sai nguyên nhân.

Các ví dụ đầy đủ dùng **Java 17+**, có tên tệp, lệnh `javac`/`java` và `stdout` xác định. Một số mã minh họa không độc lập được ghi rõ.

## 2. Cây kế thừa của những ngoại lệ I/O thường gặp

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException                 [checked]
        ├── java.io.FileNotFoundException
        ├── java.io.EOFException
        ├── java.io.UTFDataFormatException
        ├── java.io.InterruptedIOException
        ├── java.io.CharConversionException
        ├── java.io.UnsupportedEncodingException
        └── java.nio.file.FileSystemException
            ├── java.nio.file.NoSuchFileException
            ├── java.nio.file.AccessDeniedException
            ├── java.nio.file.FileAlreadyExistsException
            └── java.nio.file.DirectoryNotEmptyException
```

Sơ đồ chỉ liệt kê **một phần** cây exception, không phải toàn bộ các subtype của `IOException`. Trong thực tế, mỗi API có thể chọn kiểu lỗi cụ thể phù hợp với ngữ nghĩa của nó.

| Loại ngoại lệ | Ý nghĩa thông thường | Ví dụ ngữ cảnh |
| --- | --- | --- |
| `IOException` | Lỗi chung của thao tác input/output | Đọc, ghi, đóng hoặc truyền dữ liệu thất bại |
| `FileNotFoundException` | Không mở được file theo API I/O cổ điển; không nhất thiết chỉ vì “không tồn tại” | `new FileInputStream(file)` |
| `NoSuchFileException` | Một thao tác NIO báo không có tệp/đường dẫn mục tiêu | `Files.readString(path)` với file không tồn tại |
| `AccessDeniedException` | Hệ thống tệp báo không đủ quyền truy cập | Mở hoặc ghi một path bị từ chối |
| `FileAlreadyExistsException` | API yêu cầu tạo mới nhưng mục tiêu đã tồn tại | `Files.createFile(existingPath)` |
| `DirectoryNotEmptyException` | Không thể xóa thư mục đang chứa mục | `Files.delete(nonemptyDir)` |
| `EOFException` | Một số API cần đọc đủ dữ liệu có cấu trúc nhưng gặp hết dữ liệu quá sớm | `DataInputStream.readInt()` khi thiếu byte |
| `MalformedInputException` | Dữ liệu byte không hợp lệ theo charset đang giải mã | Đọc dữ liệu UTF-8 sai cấu trúc |

**Điểm quan trọng:** `MalformedInputException` là subtype của `CharacterCodingException`, rồi tới `IOException`; sơ đồ rút gọn ở trên không liệt kê mọi nhánh trung gian. Khi cần xử lý chính xác, hãy tra cây kế thừa trong API cụ thể.

### `IOException` là checked exception

`IOException` kế thừa `Exception` nhưng **không** thuộc nhánh `RuntimeException`, do đó compiler kiểm tra đường truyền checked exception. Một phương thức gọi API có thể ném `IOException` phải:

1. **Bắt** bằng `try/catch` và xử lý thích hợp; hoặc
2. **Khai báo** `throws IOException` (hoặc kiểu checked rộng tương thích) để caller chịu trách nhiệm.

Khác với `ArithmeticException` hay `IllegalArgumentException`, `IOException` **không phải unchecked exception**. Không cần cố chuyển nó thành `RuntimeException` chỉ để bỏ nghĩa vụ thiết kế xử lý lỗi.

## 3. `IOException` và `FileNotFoundException`: quan hệ cha–con

`FileNotFoundException extends IOException`, nên mọi handler `catch (IOException e)` có thể bắt cả `FileNotFoundException`. Nhưng điều ngược lại không đúng: handler `catch (FileNotFoundException e)` **không** bắt một `IOException` bất kỳ.

Ví dụ **mảnh mã**:

```java
try {
    java.io.InputStream input =
            new java.io.FileInputStream("data.txt");
    input.close();
} catch (java.io.FileNotFoundException notFound) {
    System.out.println("Cannot open the file");
} catch (java.io.IOException otherIo) {
    System.out.println("Another I/O failure");
}
```

Đoạn trên có một rủi ro quản lý tài nguyên: nếu xảy ra lỗi giữa mở và đóng, việc đóng có thể bị bỏ qua. Mục tiêu ở đây chỉ minh họa **thứ tự catch**. Với mã thực, hãy dùng `try-with-resources` thay vì mở rồi đóng thủ công như trên.

Handler phải đặt **kiểu con trước kiểu cha**. Nếu `catch (IOException)` đặt trước `catch (FileNotFoundException)`, nhánh riêng phía sau sẽ không thể nhận một ngoại lệ nào mà nhánh cha chưa bắt và javac có thể báo handler không thể truy cập.

### Chương trình độc lập: quan hệ kế thừa

Tạo file **`IOExceptionHierarchyDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class IOExceptionHierarchyDemo {
    static void simulate() throws IOException {
        throw new FileNotFoundException("report.csv");
    }

    public static void main(String[] args) {
        try {
            simulate();
        } catch (FileNotFoundException failure) {
            System.out.println("specific="
                    + failure.getClass().getSimpleName());
            System.out.println("also IOException="
                    + (failure instanceof IOException));
        } catch (IOException failure) {
            System.out.println("other IO error");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac IOExceptionHierarchyDemo.java
java IOExceptionHierarchyDemo
```

`stdout`:

```text
specific=FileNotFoundException
also IOException=true
```

Trong chương trình:

- `simulate()` công bố kiểu rộng `throws IOException` nhưng thực sự ném `FileNotFoundException`.
- `catch (FileNotFoundException)` xử lý lỗi cụ thể trước.
- `instanceof IOException` trả `true` vì quan hệ kế thừa.
- Nhánh `catch (IOException)` dự phòng cho những `IOException` không thuộc kiểu cụ thể trước.

Khi một API công bố `throws IOException`, nó có thể ném **nhiều subclass khác nhau**, không chỉ `FileNotFoundException`.

## 4. `FileNotFoundException` không có nghĩa chính xác “tệp không tồn tại”

Tên class dễ dẫn đến hiểu nhầm. Với `FileInputStream` hoặc `FileOutputStream` kiểu cổ điển, một `FileNotFoundException` có thể xuất hiện khi **không thể mở file** vì đường dẫn không tồn tại, file không thể truy cập, trỏ tới thư mục, hoặc một vấn đề mở file phụ thuộc hệ điều hành.

Ví dụ:

```java
try (java.io.FileInputStream input =
        new java.io.FileInputStream("orders.csv")) {
    int firstByte = input.read();
}
```

Đây là **mảnh mã trong phương thức xử lý/khai báo `IOException`**. Nếu không mở được tệp, constructor có thể ném `FileNotFoundException` ngay trước khi vào thân `try`.

Những nguyên nhân có thể gồm:

- File không tồn tại tại **đường dẫn đang được chương trình dùng**.
- Đường dẫn tương đối được giải theo thư mục làm việc khác với dự đoán.
- File nằm trong một thư mục không truy cập được.
- Hệ điều hành từ chối quyền mở theo chế độ yêu cầu.
- Path trỏ đến đối tượng không phù hợp với API (ví dụ directory thay vì regular file).
- Tệp đang bị khóa hoặc chia sẻ không phù hợp trên một số nền tảng.

Không được mặc định rằng **mọi `FileNotFoundException` có thể sửa bằng cách tự tạo file mới**. Nếu nguyên nhân là thiếu quyền hoặc chế độ mở không phù hợp, tự tạo/tự ghi đè có thể khiến dữ liệu xấu hơn.

## 5. `FileNotFoundException` cổ điển và `NoSuchFileException` của NIO.2

Java hỗ trợ nhiều nhóm API:

**I/O cổ điển (`java.io`):**

```java
new java.io.FileInputStream("missing.txt");
```

**NIO.2 (`java.nio.file.Files`):**

```java
java.nio.file.Files.readString(
        java.nio.file.Path.of("missing.txt"));
```

Hai biểu thức trên là **mảnh minh họa**. Với tệp thực sự không tồn tại, `FileInputStream` thường ném `FileNotFoundException`; `Files.readString` trên hệ thống tệp mặc định thường ném `NoSuchFileException`. Cả hai nằm dưới `IOException`.

Điểm khác nhau là **API và phân loại lỗi**: bạn không nên mặc định mọi cách mở file đều phát ra cùng subclass.

### Chương trình chạy được: cùng file thiếu nhưng khác subclass

Tạo file **`MissingFileApisDemo.java`**:

```java
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class MissingFileApisDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("io-example-");
        Path missing = directory.resolve("not-created.txt");

        try {
            try (FileInputStream input =
                    new FileInputStream(missing.toFile())) {
                System.out.println(input.read());
            } catch (FileNotFoundException failure) {
                System.out.println("classic="
                        + failure.getClass().getSimpleName());
            }

            try {
                Files.readString(missing);
            } catch (NoSuchFileException failure) {
                System.out.println("nio="
                        + failure.getClass().getSimpleName());
            }
        } finally {
            Files.delete(directory);
        }
    }
}
```

```bash
javac MissingFileApisDemo.java
java MissingFileApisDemo
```

`stdout` trong một môi trường chạy bình thường với hệ thống tệp mặc định hỗ trợ thư mục tạm:

```text
classic=FileNotFoundException
nio=NoSuchFileException
```

Chương trình tạo **một thư mục tạm mới** để đảm bảo file `not-created.txt` không nằm ở đó. Vì vậy kết quả không phụ thuộc có sẵn một file tên `missing.txt` trong working directory hay không.

Chú ý:

- `Files.createTempDirectory` có thể tự ném `IOException` do vấn đề môi trường. Đây không phải tình huống “bài chạy chắc chắn thành công bất kể quyền của máy”.
- `Files.delete(directory)` có thể ném `IOException` nếu môi trường can thiệp; ví dụ dùng tài nguyên tạm trong môi trường cho phép.
- `NoSuchFileException` kế thừa `FileSystemException`, rồi `IOException`; **không phải subclass của `FileNotFoundException`**.
- Để phục vụ nhiều API khác nhau, `catch (IOException)` thường là ranh giới chung; phân loại subclass khi thật sự cần hành vi phục hồi khác biệt.

## 6. `NoSuchFileException`, `AccessDeniedException` và các lỗi NIO khác

NIO.2 cung cấp các subclass cho thông tin về hệ thống tệp chi tiết hơn so với `FileNotFoundException` tổng quát.

Ví dụ chữ ký minh họa:

```java
static String load(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
```

Caller có thể tổ chức `catch` theo **kiểu con trước, kiểu cha sau**:

```java
try {
    String content = load(path);
    System.out.println(content);
} catch (java.nio.file.NoSuchFileException failure) {
    System.out.println("File missing");
} catch (java.nio.file.AccessDeniedException failure) {
    System.out.println("Access denied");
} catch (java.io.IOException failure) {
    System.out.println("Other I/O failure");
}
```

Đây là **mảnh minh họa** có biến `path` kiểu `Path` và phương thức `load` từ đoạn trước. Nó không thay thế việc phân quyền phía hệ điều hành, log/giám sát hay kiểm tra input.

### Không đoán loại IOException từ text của `getMessage()`

Thông điệp hệ thống có thể chứa đường dẫn, mã lỗi và cách diễn đạt khác nhau giữa hệ điều hành, provider, locale và JDK. **Không dùng `failure.getMessage().contains("No such file")` làm hệ thống phân loại lỗi**, vì thông điệp không phải hợp đồng ổn định.

Nếu cần phân biệt trường hợp file bị từ chối, dùng `instanceof AccessDeniedException` hoặc nhánh `catch` cụ thể. Nhưng cũng cần chấp nhận rằng provider không bắt buộc phân biệt mọi tình huống theo cùng một subclass trong mọi môi trường.

### `FileSystemException` có thông tin gì?

`FileSystemException` có thể cung cấp `getFile()`, `getOtherFile()` và `getReason()`. Chúng hữu ích để chẩn đoán **tệp nguồn, tệp đích và lý do** ở các hoạt động như `Files.move` hoặc `Files.copy`.

Hãy cân nhắc bảo mật khi ghi đường dẫn vào log; đường dẫn người dùng và tên tệp có thể chứa dữ liệu riêng tư. Cần phân biệt log nội bộ và thông báo hiển thị ra bên ngoài.

## 7. Đọc/ghi thành công bằng `Files` và UTF-8

Đối với file văn bản, `Files.writeString`, `Files.readString` hoặc `newBufferedReader`/`newBufferedWriter` thường rõ ràng hơn việc quản lý mảng byte thủ công. Chọn charset rõ ràng để tránh phụ thuộc mã hóa mặc định.

### Chương trình hoàn chỉnh: tạo, ghi, đọc, xóa file tạm

Tạo file **`SuccessfulFileIODemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SuccessfulFileIODemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java-io-", ".txt");

        try {
            Files.writeString(
                    file, "alpha\nbeta\n", StandardCharsets.UTF_8);

            try (BufferedReader reader = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("line1=" + reader.readLine());
                System.out.println("line2=" + reader.readLine());
                System.out.println("end=" + reader.readLine());
            }

            System.out.println("full="
                    + Files.readString(file, StandardCharsets.UTF_8)
                            .replace("\n", "|"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac SuccessfulFileIODemo.java
java SuccessfulFileIODemo
```

`stdout`:

```text
line1=alpha
line2=beta
end=null
full=alpha|beta|
```

Vì file được tạo mới và ghi chuỗi xác định, dữ liệu không phụ thuộc file sẵn có. `StandardCharsets.UTF_8` được chỉ định khi đọc và ghi.

Các ý cần nhớ:

- `Files.createTempFile` và `Files.writeString` đều có thể ném `IOException`; `main throws IOException` là một chính sách truyền lỗi phù hợp cho **bài chạy thử**, không tự giải quyết lỗi.
- `BufferedReader.readLine()` trả `null` khi hết dòng — đó là **điều kiện kết thúc dữ liệu bình thường**, không phải ngoại lệ.
- `try-with-resources` tự đóng reader ngay cả khi `readLine()` thất bại.
- `Files.deleteIfExists` ở `finally` có thể thất bại; nếu cleanup rất quan trọng, cần dùng một phạm vi quản lý/ghi nhận lỗi phù hợp để không mất lỗi chính.
- Trong ứng dụng thực, thường không xóa file vừa tạo ngay: ví dụ xóa để không để lại dữ liệu tạm sau khi chạy.

### Khi nào dùng stream/reader?

- `InputStream` / `OutputStream`: làm việc với **byte**; phù hợp file nhị phân, giao thức, ảnh, dữ liệu nén.
- `Reader` / `Writer`: làm việc với **ký tự** và charset ở lớp chuyển đổi.
- `BufferedReader`: tiện đọc từng dòng văn bản.
- `Files.readString` / `Files.writeString`: tiện thao tác văn bản ở mức cao khi kích thước dữ liệu phù hợp.
- `Files.newInputStream` / `newOutputStream`: làm việc trực tiếp với luồng byte của hệ thống tệp.

Đừng dùng `Reader` để xử lý file nhị phân tùy ý: giải mã ký tự sai có thể làm biến dạng byte hoặc phát sinh lỗi giải mã.

## 8. EOF bình thường **không** phải `IOException`

Một trong những nhầm lẫn phổ biến nhất là: “`read()` không còn dữ liệu thì ném ngoại lệ.” Với nhiều API stream cơ bản, đó là **sai**.

Ví dụ `InputStream.read()`:

- Trả giá trị `0..255` nếu đọc được một byte.
- Trả `-1` nếu đã đến cuối stream bình thường.
- Có thể **ném `IOException`** nếu thao tác đọc thực sự thất bại.

Tương tự `Reader.read()` thường trả một mã ký tự hoặc `-1` khi EOF; `BufferedReader.readLine()` trả `null` khi đã hết dòng. Đây là **giá trị sentinel**, không phải checked exception.

### Chương trình chạy được: EOF và lỗi đọc thực

Tạo file **`EofVersusIOExceptionDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class EofVersusIOExceptionDemo {
    static class BrokenInput extends InputStream {
        @Override
        public int read() throws IOException {
            throw new IOException("device disconnected");
        }
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input = new ByteArrayInputStream(
                "A".getBytes(StandardCharsets.US_ASCII))) {
            System.out.println("first=" + input.read());
            System.out.println("second=" + input.read());
        }

        try (InputStream broken = new BrokenInput()) {
            System.out.println(broken.read());
        } catch (IOException failure) {
            System.out.println("error=" + failure.getMessage());
        }
    }
}
```

```bash
javac EofVersusIOExceptionDemo.java
java EofVersusIOExceptionDemo
```

`stdout`:

```text
first=65
second=-1
error=device disconnected
```

Phân tích:

1. ASCII `A` có byte value 65. Lần đọc đầu trả 65.
2. Lần đọc thứ hai trả `-1`, báo **đã đọc hết** chứ không báo lỗi.
3. `BrokenInput` chủ động ném `IOException("device disconnected")` để mô phỏng lỗi thiết bị. Handler bắt đúng ngoại lệ.
4. `ByteArrayInputStream` là một resource trong bộ nhớ để demo EOF ổn định; `BrokenInput` là resource mô phỏng lỗi, không cần thiết bị thật.

### `EOFException` có mâu thuẫn không?

Không. `EOFException` là một subclass của `IOException` xuất hiện từ **những API đòi hỏi đủ một cấu trúc dữ liệu**, ví dụ `DataInputStream.readInt()` cần đọc đúng 4 byte. Nếu stream hết sau 1 byte, nó không thể trả một `int` hợp lệ nên ném `EOFException`.

Cùng là hết dữ liệu, **hợp đồng phương thức khác nhau**:

| API | Hết dữ liệu bình thường/thiếu dữ liệu | Cách báo |
| --- | --- | --- |
| `InputStream.read()` | Không còn byte | Trả `-1` |
| `Reader.read()` | Không còn ký tự | Trả `-1` |
| `BufferedReader.readLine()` | Không còn dòng | Trả `null` |
| `DataInputStream.readInt()` | Không đủ 4 byte để giải mã `int` | Ném `EOFException` |
| `InputStream.readNBytes(int)` | Có thể trả ít byte hơn yêu cầu khi EOF | Trả mảng ngắn hơn |
| `DataInputStream.readFully(byte[])` | Không đủ byte để lấp đầy buffer | Ném `EOFException` |

Vì vậy, đừng viết một handler `catch (EOFException)` cho `BufferedReader.readLine()` rồi kỳ vọng nó hoạt động khi hết file bình thường.

## 9. Chương trình độc lập: `DataInputStream` và `EOFException`

Tạo file **`EofExceptionDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;

public class EofExceptionDemo {
    public static void main(String[] args) throws IOException {
        byte[] incomplete = {1, 2};

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(incomplete))) {
            System.out.println("reading int");
            System.out.println(input.readInt());
        } catch (EOFException failure) {
            System.out.println("not enough bytes for int");
        }
    }
}
```

```bash
javac EofExceptionDemo.java
java EofExceptionDemo
```

`stdout`:

```text
reading int
not enough bytes for int
```

`DataInputStream.readInt()` cần đọc đúng bốn byte theo định dạng của nó. Ví dụ cố ý chỉ cung cấp hai byte, nên method không thể trả một `int` và ném `EOFException`.

Đừng dùng `EOFException` chung cho mọi trường hợp thiếu file. `FileNotFoundException`/`NoSuchFileException` liên quan **mở hoặc truy cập file**, trong khi `EOFException` của ví dụ liên quan **dữ liệu bên trong một stream đã có** nhưng không đủ cho thao tác cần thực hiện.

## 10. Lỗi ghi: `IOException` có thể xảy ra muộn

Với `OutputStream`, một lệnh `write` có thể thất bại ngay lúc ghi. Với buffered writer/stream, lỗi có thể chỉ hiện ra ở thời điểm `flush()` hoặc `close()`, tùy cấu trúc buffer và implementation. Đừng mặc định chỉ có `write` mới cần xử lý exception.

### Chương trình chạy được: mô phỏng lỗi `write()`

Tạo file **`WriteIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;

public class WriteIOExceptionDemo {
    static class BrokenOutput extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("write failed");
        }
    }

    public static void main(String[] args) {
        try (OutputStream output = new BrokenOutput()) {
            output.write(65);
            System.out.println("unexpected success");
        } catch (IOException failure) {
            System.out.println("error=" + failure.getMessage());
        }
    }
}
```

```bash
javac WriteIOExceptionDemo.java
java WriteIOExceptionDemo
```

`stdout`:

```text
error=write failed
```

`BrokenOutput` chủ động ném lỗi khi ghi một byte, nên `unexpected success` không chạy. Đây là lỗi **ghi**, không phải EOF và không phải tự động là `FileNotFoundException`.

### Buffered output và ý nghĩa của `flush()`

Một buffered output stream có thể tích lũy dữ liệu trong RAM trước khi chuyển đến delegate hoặc hệ điều hành. Vì thế:

- `write(...)` có thể chỉ ghi vào buffer.
- `flush()` yêu cầu đẩy những dữ liệu còn đệm xuống tầng bên dưới, nhưng **không đồng nghĩa** bảo đảm dữ liệu đã được ghi bền vững lên đĩa trong mọi hệ thống.
- `close()` thường xử lý dọn dẹp và có thể flush trước khi đóng, tùy API.
- Lỗi có thể nảy sinh khi **flush/close** dù những lời gọi `write` trước đó không báo lỗi.
- Với tính bền vững của dữ liệu tệp, API như `FileChannel.force(...)` hoặc thiết kế commit/rename có thể cần được xem xét theo yêu cầu; không suy ra “không có IOException” nghĩa là có transaction an toàn.

Khi điều khiển dữ liệu quan trọng, hãy hoàn tất đóng/flush theo đúng hợp đồng trước khi thông báo thao tác ghi thành công.

### `PrintStream` và `PrintWriter` là trường hợp đặc biệt

Không phải mọi API ghi đều **ném checked IOException ra caller**. `PrintStream` và `PrintWriter` thường **không ném IOException trực tiếp từ những phương thức in thông thường**; chúng có cơ chế trạng thái lỗi như `checkError()`.

Do đó, `System.out.println(...)` có thể không báo checked `IOException` giống một `OutputStream.write(...)` thông thường. Khi chọn API output, cần hiểu hợp đồng của class cụ thể, không xem mọi thao tác “ghi” có hành vi ngoại lệ giống nhau.

## 11. Lỗi mã hóa và giải mã: vẫn thuộc nhóm I/O

Đọc văn bản nghĩa là chuyển **byte** thành **ký tự** theo một charset. Nếu file không chứa byte hợp lệ cho charset được chọn, các API giải mã với hành vi báo lỗi có thể ném ngoại lệ thuộc họ `IOException`, ví dụ `MalformedInputException`.

Một chương trình có thể mở file thành công nhưng vẫn lỗi **khi bắt đầu đọc và giải mã**. Vì vậy “mở được file” chưa có nghĩa “file đúng định dạng”.

### Chương trình chạy được: byte không hợp lệ với UTF-8

Tạo file **`MalformedUtf8Demo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MalformedUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("invalid-utf8-", ".txt");

        try {
            Files.write(file, new byte[] {(byte) 0xC3, (byte) 0x28});

            try (BufferedReader reader = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {
                System.out.println(reader.readLine());
            } catch (MalformedInputException failure) {
                System.out.println("invalid UTF-8");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac MalformedUtf8Demo.java
java MalformedUtf8Demo
```

`stdout`:

```text
invalid UTF-8
```

`0xC3 0x28` là cặp byte không tạo thành chuỗi UTF-8 hợp lệ: sau leading byte `0xC3` phải là continuation byte hợp lệ, trong khi `0x28` không có dạng đó. `Files.newBufferedReader(path, UTF_8)` dùng một decoder được cấu hình để **báo lỗi** thay vì tùy tiện thay thế byte sai bằng ký tự khác.

Điểm cần phân biệt:

- `FileNotFoundException`/`NoSuchFileException`: thường liên quan **tồn tại/mở file**.
- `MalformedInputException`: file có thể tồn tại và mở được, nhưng **nội dung byte không hợp lệ** theo charset.
- Các API giải mã khác có thể được cấu hình `CodingErrorAction.REPLACE` để thay ký tự lỗi, thay vì ném. Không suy ra mọi cách đọc text đều phát sinh cùng exception.

Nếu file đến từ nguồn không tin cậy, cần chọn charset có chủ ý, xử lý dữ liệu không hợp lệ đúng chính sách và không dùng default charset tùy môi trường một cách vô thức.

## 12. `try-with-resources`: đóng tài nguyên ngay cả khi đọc/ghi lỗi

Resource I/O thường triển khai `Closeable` (một subtype của `AutoCloseable`). Khi `close()` được gọi sai thời điểm hoặc không được gọi, có thể xảy ra leak handle, giữ khóa file, socket không giải phóng, hoặc dữ liệu buffered không hoàn tất.

Mẫu khuyến nghị:

```java
try (java.io.InputStream input =
        java.nio.file.Files.newInputStream(path)) {
    // Đọc dữ liệu.
}
```

Đây là **mảnh mã** với biến `path` và ngữ cảnh xử lý/khai báo `IOException`. TWR tự gọi `input.close()` khi khối hoàn thành bình thường hoặc có ngoại lệ.

### Khi close cũng thất bại: `getSuppressed()`

Nếu thân `try` ném `IOException("read failed")` và `close()` ném `IOException("close failed")`, Java giữ lỗi đọc là **primary** và gắn lỗi close là **suppressed exception**, quan sát bằng `getSuppressed()`.

### Chương trình chạy được: giữ cả lỗi xử lý và lỗi đóng

Tạo file **`IoSuppressedDemo.java`**:

```java
import java.io.IOException;

public class IoSuppressedDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed count="
                    + failure.getSuppressed().length);
            System.out.println("suppressed="
                    + failure.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac IoSuppressedDemo.java
java IoSuppressedDemo
```

`stdout`:

```text
closing
primary=read failed
suppressed count=1
suppressed=close failed
```

Nếu thân `try` hoàn thành **bình thường** nhưng `close()` thất bại, lỗi close thường trở thành primary, chứ không nhất thiết là suppressed.

**Quan trọng:** không viết `finally { resource.close(); }` thêm lần nữa cho một resource đã được TWR quản lý. Đóng lặp không được bảo đảm an toàn cho mọi `AutoCloseable`.

### Chỉ đóng resource **mình sở hữu**

Nếu hàm nhận một `InputStream` **mượn từ caller**, việc viết `try (input)` (Java 9+) sẽ đóng đúng stream của caller, có thể phá vỡ các thao tác sau. TWR tự động đóng theo cú pháp, **không tự biết ai có quyền đóng**. Hãy công bố rõ ownership của phương thức và đặt TWR ở scope chịu trách nhiệm giải phóng resource.

## 13. Không dùng `Files.exists` để “bảo đảm không có FileNotFoundException”

Mã dễ bị hiểu sai:

```java
if (java.nio.file.Files.exists(path)) {
    return java.nio.file.Files.readString(path);
}
return "";
```

Đây là mảnh phương thức minh họa. Nó có vấn đề **time-of-check to time-of-use (TOCTOU)**: file có thể bị xóa, đổi quyền hoặc thay thế **giữa lúc kiểm tra và lúc đọc**. `Files.exists(path)` cũng không phải bằng chứng chắc chắn file có thể mở/đọc.

Bởi vậy:

- Nếu thao tác yêu cầu đọc file, hãy **thực hiện thao tác** và xử lý `IOException` từ chính lời gọi đó.
- Kiểm tra trước có thể hữu ích cho UX hoặc validation, nhưng **không thay thế** việc xử lý lỗi tại thời điểm I/O.
- Không thiết kế retry vô hạn nếu file không tồn tại thật; cần giới hạn và chính sách lỗi.
- Cần phòng rủi ro đường dẫn không đáng tin, symlink/path traversal nếu path nhận từ người dùng.

Ví dụ một pattern đơn giản:

```java
try {
    String text = java.nio.file.Files.readString(path);
    consume(text);
} catch (java.nio.file.NoSuchFileException failure) {
    reportMissingFile();
} catch (java.io.IOException failure) {
    reportIoFailure(failure);
}
```

Đây là **mảnh minh họa**, cần định nghĩa `consume`, `reportMissingFile` và `reportIoFailure`. Phân loại lỗi theo kiểu exception giúp code đáng tin hơn dựa trên việc parse `getMessage()`.

## 14. Đường dẫn, thư mục làm việc và quyền truy cập

Nhiều lỗi `FileNotFoundException` xuất phát từ **đường dẫn tương đối**. Ví dụ `Path.of("config.txt")` không tự tìm file trong thư mục chứa source code; nó được giải theo **working directory** của tiến trình trong hệ thống tệp mặc định.

```java
java.nio.file.Path path =
        java.nio.file.Path.of("config.txt").toAbsolutePath();
System.out.println(path);
```

Đây là **mảnh minh họa**, output phụ thuộc máy nên không ghi một đường dẫn cụ thể. Dùng `toAbsolutePath()` để hỗ trợ chẩn đoán, nhưng không dùng nó để tự tạo một path an toàn nếu đầu vào không đáng tin.

### Phân biệt “có file” với “có quyền đọc/ghi”

Một file có thể tồn tại nhưng thao tác vẫn thất bại:

- Caller thiếu quyền đọc hoặc ghi.
- Resource thuộc một mount có chính sách riêng.
- Path không phải regular file như API mong đợi.
- Hệ thống tệp có lỗi, không còn sẵn sàng, hoặc quota/dung lượng không đủ.
- Khả năng share/lock khác nhau theo platform.
- File được thay đổi bởi tiến trình khác trong khi thao tác đang chạy.

Các phương thức `Files.isReadable`, `isWritable` hoặc `exists` chỉ là **kiểm tra tại một thời điểm**, có thể phụ thuộc provider và quyền truy cập; không phải chứng chỉ bảo đảm thao tác tiếp theo sẽ thành công. Hãy xử lý exception từ operation thực.

### Không gắn cứng một loại lỗi quyền truy cập cho mọi hệ điều hành

`AccessDeniedException` của NIO được dùng khi provider báo cụ thể kiểu lỗi đó, nhưng cùng sự cố quyền truy cập có thể được biểu diễn khác tùy API/provider. Với `FileInputStream` cổ điển, một số tình huống quyền có thể xuất hiện dưới dạng `FileNotFoundException`. Đừng thiết kế logic chỉ hoạt động khi mọi hệ thống đều ném đúng một subtype cho mỗi nguyên nhân.

## 15. Mở file để ghi: ghi đè, nối thêm và tạo mới

Lỗi dữ liệu nghiêm trọng có thể xuất phát không phải từ exception, mà từ **chọn sai chế độ mở file**.

Với `Files.newOutputStream` và `Files.writeString`, các tùy chọn `StandardOpenOption` điều khiển việc tạo và ghi:

- `CREATE`: tạo nếu chưa tồn tại, nếu được phép.
- `CREATE_NEW`: chỉ tạo mới; nếu đã tồn tại, phát sinh lỗi thay vì ghi đè.
- `TRUNCATE_EXISTING`: khi mở để ghi, có thể làm file hiện có rỗng trước khi ghi nội dung mới.
- `APPEND`: ghi thêm vào cuối file theo semantics/provider.
- `WRITE`: mở phục vụ ghi.

Cần đọc hợp đồng riêng của từng API về **mặc định khi không truyền options**. Chẳng hạn `Files.writeString` theo mặc định tạo file nếu chưa có và ghi đè nội dung hiện có (truncation), không phải mặc định append.

### Mảnh minh họa: chỉ tạo file nếu chưa có

```java
java.nio.file.Files.writeString(
        path,
        text,
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE_NEW,
        java.nio.file.StandardOpenOption.WRITE);
```

Mảnh này giả định có `Path path` và `String text` trong phương thức khai báo/handle `IOException`. Nếu file đã tồn tại, `CREATE_NEW` được thiết kế để **không âm thầm ghi đè**.

### Mảnh minh họa: thêm nội dung

```java
java.nio.file.Files.writeString(
        path,
        additionalText,
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND);
```

Đây là mảnh mã, không phải chương trình độc lập. Phương thức `writeString` vẫn có thể ném `IOException` do mở file, ghi dữ liệu hoặc đóng luồng.

Không cố dùng `catch (FileNotFoundException)` để sửa một thao tác ghi đè nhầm: nếu bạn chọn chế độ mở sai và thao tác thành công thì **không có exception nào cứu dữ liệu cũ**.

## 16. Sao chép stream: lỗi đọc, ghi và đóng đều có thể xuất hiện

Khi sao chép dữ liệu, có ít nhất ba giai đoạn:

1. Mở nguồn và đích.
2. Đọc từ nguồn, ghi vào đích.
3. Đóng/flush tài nguyên và hoàn tất thao tác.

Có thể gặp `IOException` ở **bất cứ giai đoạn nào**. Một số ví dụ:

- Mở source: `NoSuchFileException` hoặc lỗi quyền.
- Mở target: lỗi đường dẫn, quyền hoặc chế độ tạo.
- `read`: nguồn I/O lỗi giữa chừng.
- `write`: thiết bị đích hỏng, hết dung lượng hoặc kết nối ngắt.
- `close`: lỗi cleanup/flush.
- Cleanup file đích nửa chừng: cũng có thể thất bại.

### Chương trình chạy được: sao chép bằng `InputStream.transferTo`

Tạo tệp **`CopyStreamsDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyStreamsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-demo-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "hello", StandardCharsets.UTF_8);

            long copied;
            try (InputStream input = Files.newInputStream(source);
                 OutputStream output = Files.newOutputStream(target)) {
                copied = input.transferTo(output);
            }

            System.out.println("bytes=" + copied);
            System.out.println("target="
                    + Files.readString(target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.delete(directory);
        }
    }
}
```

```bash
javac CopyStreamsDemo.java
java CopyStreamsDemo
```

`stdout` khi môi trường cấp tệp tạm bình thường:

```text
bytes=5
target=hello
```

`"hello"` trong UTF-8 chứa 5 byte. `InputStream.transferTo(OutputStream)` có thể ném `IOException` từ việc đọc source hoặc ghi target. TWR đóng cả `output` và `input` theo thứ tự ngược của header. Đọc lại file target là một bước kiểm chứng nội dung, không phải cơ chế transaction.

**Giới hạn:** nếu ghi thất bại giữa chừng, target có thể đã có **một phần dữ liệu**. Xử lý ngoại lệ không tự rollback nội dung đã ghi. Với dữ liệu quan trọng, hãy cân nhắc chiến lược ghi vào file tạm, xác nhận thành công rồi chuyển/rename theo điều kiện hệ thống tệp; không giả định mọi lần move đều atomic trên mọi provider.

## 17. Bọc `IOException` nhưng giữ nguyên nguyên nhân

Ở tầng ứng dụng, bạn có thể muốn chuyển `IOException` thành một ngoại lệ nghiệp vụ có tên/ý nghĩa rõ hơn. Khi đó, **không đánh mất throwable gốc**.

### Mảnh mã đúng

```java
try {
    loadConfiguration();
} catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Application configuration cannot be loaded", original);
}
```

Đây là mảnh minh họa, cần định nghĩa `loadConfiguration()`. `IllegalStateException` là unchecked, nên caller không bị buộc catch/throws ở compile time, nhưng lỗi I/O vẫn **còn trong `getCause()`**.

### Mảnh mã sai về khả năng chẩn đoán

```java
try {
    loadConfiguration();
} catch (java.io.IOException original) {
    throw new IllegalStateException(original.getMessage());
}
```

Đây là mảnh cố ý thể hiện anti-pattern: chỉ sao chép message. Lỗi `IOException` gốc, stack trace và suppressed exceptions của nó không được liên kết vào wrapper.

### Chương trình chạy được: giữ cause

Tạo file **`IOExceptionCauseDemo.java`**:

```java
import java.io.IOException;

public class IOExceptionCauseDemo {
    static class ImportException extends Exception {
        ImportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void readData() throws IOException {
        throw new IOException("storage unavailable");
    }

    static void importData() throws ImportException {
        try {
            readData();
        } catch (IOException original) {
            throw new ImportException("import failed", original);
        }
    }

    public static void main(String[] args) {
        try {
            importData();
        } catch (ImportException failure) {
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getClass().getSimpleName());
            System.out.println("cause message="
                    + failure.getCause().getMessage());
        }
    }
}
```

```bash
javac IOExceptionCauseDemo.java
java IOExceptionCauseDemo
```

`stdout`:

```text
outer=import failed
cause=IOException
cause message=storage unavailable
```

`super(message, cause)` trong custom exception bảo đảm công cụ logging và caller có thể lần theo `getCause()`. Không cần tạo lại một `IOException` mới chỉ để “giữ message”.

### Khi nào không nên bọc?

Nếu hợp đồng phương thức đã là `throws IOException` và tầng hiện tại **không thêm thông tin hữu ích**, có thể để IOException lan truyền nguyên dạng. Bọc ở mọi lớp mà không có ranh giới trừu tượng khiến chuỗi lỗi dài và khó đọc.

## 18. Retry: không phải `IOException` nào cũng nên thử lại

Một lỗi I/O có thể **tạm thời** hoặc **mang tính cấu hình/dữ liệu cố định**. Không thể chọn chính sách retry chỉ từ việc đối tượng là `IOException`.

Ví dụ:

- Mạng mất kết nối ngắn hạn: một số thao tác **có thể** phục hồi sau retry, nếu request an toàn để thử lại.
- File chưa được tạo do một tiến trình khác đang chuẩn bị: có thể chờ trong giới hạn nếu ứng dụng có hợp đồng đồng bộ rõ ràng.
- File path sai, dữ liệu UTF-8 hỏng, không có quyền truy cập: retry cùng input/cấu hình không thay đổi thường không giải quyết được.
- Ghi dữ liệu thành công một phần rồi exception: retry mù quáng có thể **ghi trùng**, nhất là với append hoặc request không idempotent.
- Đích hết dung lượng: có thể yêu cầu can thiệp, không nên retry liên tục.

Nếu muốn retry, hãy xác định:

1. **Phân loại lỗi** từ ngữ cảnh và subtype khi đáng tin.
2. **Tính idempotent** của thao tác (đọc, ghi đè có điều kiện, append, giao dịch).
3. **Số lần giới hạn**, timeout và backoff phù hợp.
4. **Trạng thái còn lại sau lỗi**, nhất là file/transaction đích đã bị ghi một phần.
5. Khi nào cần trả thông tin lỗi gốc về caller thay vì tiếp tục che lỗi.

Ví dụ không nên thiết kế:

```java
while (true) {
    try {
        writeImportantData();
        break;
    } catch (java.io.IOException ignored) {
        // Không retry vô hạn hoặc nuốt mọi IOException.
    }
}
```

Đây là mảnh mã **cố ý minh họa anti-pattern**. Nó có thể kẹt vô hạn, che lỗi quyền/đĩa và ghi trùng trong một số trường hợp. Chỉ triển khai retry với chính sách rõ ràng và khả năng xác định kết quả thao tác trước đó.

## 19. Phân biệt ngoại lệ của API với các lỗi lập trình khác

Không phải mọi lỗi khi làm việc với đường dẫn, stream và file đều là `IOException`:

- `NullPointerException`: truyền `null` vào một API không chấp nhận.
- `IllegalArgumentException`: truyền tham số không hợp lệ.
- `InvalidPathException`: chuỗi tạo `Path` không hợp lệ, là unchecked exception.
- `SecurityException`: có thể phát sinh nếu bộ kiểm soát truy cập áp hạn chế trong những môi trường liên quan.
- `UnsupportedOperationException`: yêu cầu thao tác không được provider/API hỗ trợ.
- `ClosedChannelException`: một ví dụ **checked IOException** khi truy cập channel đã đóng, khác với những unchecked exception kể trên.

Vì vậy `catch (IOException)` không phải handler cho **mọi sự cố có liên quan file**. Đừng bắt `Exception` quá rộng rồi tuyên bố tất cả đều là lỗi đọc/ghi; nhiều lỗi phản ánh bug hoặc cấu hình sai cần xử lý khác.

### Tên file, đường dẫn và dữ liệu bên ngoài

Khi lấy path từ người dùng:

- Chọn thư mục gốc được phép và chuẩn hóa/kiểm soát path phù hợp với mô hình bảo mật.
- Không tin hoàn toàn vào việc nối chuỗi path thủ công.
- Không nhúng trực tiếp thông tin nhạy cảm trong message hoặc log nếu không cần.
- Dùng charset và format dữ liệu đã thống nhất.
- Không biến một `IOException` thành thông báo “không tìm thấy file” khi chưa xác định nguyên nhân.

## 20. Một ví dụ lớp tiện ích: bắt lỗi có ngữ cảnh, dùng TWR đúng scope

Tạo file **`SafeTextLoaderDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class SafeTextLoaderDemo {
    static String readFirstLine(BufferedReader reader)
            throws IOException {
        // Reader được mượn từ caller, KHÔNG tự đóng ở đây.
        return reader.readLine();
    }

    static String loadOwnedText(String data) throws IOException {
        try (BufferedReader reader =
                new BufferedReader(new StringReader(data))) {
            return readFirstLine(reader);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("result="
                    + loadOwnedText("first\nsecond"));
        } catch (IOException failure) {
            System.out.println("IO failure="
                    + failure.getMessage());
        }
    }
}
```

```bash
javac SafeTextLoaderDemo.java
java SafeTextLoaderDemo
```

`stdout`:

```text
result=first
```

Điểm đáng chú ý là **quyền sở hữu tài nguyên**:

- `readFirstLine` nhận `BufferedReader` do caller cung cấp; nó chỉ **mượn** reader để đọc và để caller quyết định khi nào đóng.
- `loadOwnedText` **tự tạo** reader của mình và sử dụng TWR trong scope sở hữu.
- Hai method đều khai báo `throws IOException` để giữ checked exception đúng hợp đồng, dù `StringReader` trong ví dụ không cần hệ thống tệp.

Nếu helper tự dùng `try (reader)` (Java 9+) trên reader **mượn**, nó sẽ đóng resource của caller trước thời điểm caller mong muốn. TWR không tự suy luận quyền sở hữu.

## 21. Bảng xử lý nhanh

| Tình huống | Dấu hiệu/API | Cách xử lý thường phù hợp |
| --- | --- | --- |
| File không tồn tại với `FileInputStream` | `FileNotFoundException` | Kiểm tra cấu hình/path; phân biệt với lỗi quyền |
| File không tồn tại với `Files.readString` | `NoSuchFileException` | Phân loại missing file, không dùng message để đoán |
| File có nhưng không có quyền | `AccessDeniedException` hoặc dạng `IOException` khác | Sửa quyền/cấu hình, không retry vô hạn |
| Đọc `InputStream.read()` được `-1` | EOF bình thường | Kết thúc vòng đọc, không ném lỗi giả |
| `DataInputStream.readInt()` thiếu byte | `EOFException` | Xác nhận dữ liệu có cấu trúc đầy đủ |
| `write`/`flush`/`close` thất bại | `IOException` | Báo thất bại, bảo toàn primary và suppressed |
| Mở file làm text nhưng byte sai charset | `MalformedInputException` | Dùng charset đúng, chính sách decode rõ ràng |
| `CREATE_NEW` mà file đã có | `FileAlreadyExistsException` (NIO) | Quyết định có được phép ghi đè không |
| Ghi một phần rồi mất kết nối | `IOException`, target có thể đã thay đổi | Kiểm tra idempotency trước khi retry |
| Bọc lỗi cho tầng nghiệp vụ | `new DomainException(context, original)` | Giữ cause, đừng chỉ copy message |
| Resource bị đóng trong helper dùng borrowed stream | Lỗi vòng đời có thể xảy ra về sau | Đóng ở scope owner, không ở helper |
| Đọc/ghi từ source không tin cậy | Nhiều lỗi khác nhau | Kiểm tra path, encoding, quyền, lỗi và chính sách bảo mật |

Bảng chỉ nêu các khả năng **thường gặp**. Provider hệ thống tệp hoặc thư viện có thể ném subtype khác; đọc hợp đồng phương thức cụ thể vẫn là điều bắt buộc.

## 22. Sai lầm và nhầm lẫn phổ biến

**“`IOException` là unchecked nên không cần `throws`.”** Sai. Nó là checked exception.

**“`FileNotFoundException` không phải `IOException`.”** Sai. Nó là subtype trực tiếp của `IOException`.

**“Hễ thiếu file thì mọi API Java đều ném `FileNotFoundException`.”** Sai. NIO.2 thường dùng `NoSuchFileException`.

**“`FileNotFoundException` chỉ xuất hiện nếu file thật sự không tồn tại.”** Sai. Mở file có thể thất bại vì quyền, path không hợp lệ cho thao tác hoặc hạn chế nền tảng.

**“Đặt `catch (IOException)` trước `catch (FileNotFoundException)` là tốt hơn.”** Sai. Kiểu con phải trước kiểu cha nếu muốn phân loại riêng.

**“EOF luôn tạo `EOFException`.”** Sai. `InputStream.read()` thường trả `-1`, `BufferedReader.readLine()` trả `null` khi hết dữ liệu bình thường.

**“`DataInputStream.readInt()` thiếu byte thì trả `-1`.”** Sai. Nó ném `EOFException` nếu không đọc đủ bốn byte.

**“Đọc file thành công một lần bảo đảm lần sau không có `IOException`.”** Sai. File có thể bị thay đổi và hệ thống tệp có thể thất bại giữa các lần thao tác.

**“`Files.exists(path)` trả true thì `Files.readString(path)` chắc chắn thành công.”** Sai. Kiểm tra trước không loại bỏ race condition hoặc lỗi quyền.

**“Có thể dựa trên `getMessage()` để phân biệt lỗi quyền với lỗi thiếu file.”** Không an toàn; văn bản message thay đổi theo OS/provider.

**“Không có lỗi ở `write()` nghĩa là ghi đã hoàn tất và bền vững.”** Sai. Lỗi có thể xảy ra khi flush/close; tính bền vững còn cần hợp đồng riêng.

**“`PrintWriter` và `OutputStream` ném checked IOException giống nhau ở mọi phương thức.”** Sai. `PrintWriter` có cách báo lỗi khác, như `checkError()`.

**“Đọc text byte không hợp lệ luôn tự thay bằng ký tự thay thế.”** Không hẳn. Decoder có thể chọn báo `MalformedInputException`.

**“Đã dùng TWR thì lỗi đóng không quan trọng.”** Sai. Nó có thể là lỗi chính hoặc suppressed; dữ liệu vẫn có thể chưa được ghi đúng.

**“TWR trên một tham số stream mượn không đóng stream của caller.”** Sai. Nó đóng chính đối tượng đã đưa vào header, trừ khi một adapter có semantics đặc biệt.

**“Bọc `IOException` bằng `new RuntimeException(original.getMessage())` đã giữ lỗi gốc.”** Sai. Hãy truyền `original` như cause.

**“IOException nào cũng có thể retry ngay nhiều lần.”** Sai. Một số lỗi cố định, một số thao tác có side effect không idempotent.

**“Ghi thất bại sẽ tự rollback file đích.”** Sai. File đích có thể đã bị ghi một phần.

**“`InvalidPathException` là một subclass của `IOException`.”** Sai. Nó là unchecked exception.

**“Để chắc file luôn được đóng, cứ gọi `close()` hai lần.”** Sai. Một số `AutoCloseable` không bảo đảm đóng lặp không có side effect.

## 23. Bài tập tự kiểm tra

1. **`IOException` checked hay unchecked?** Checked.
2. **`FileNotFoundException` có được `catch (IOException)` bắt không?** Có.
3. **`NoSuchFileException` có phải subclass của `FileNotFoundException` không?** Không; cả hai thuộc họ `IOException` qua những nhánh khác nhau.
4. **`FileInputStream` mở file không tồn tại thường ném gì?** `FileNotFoundException`.
5. **`Files.readString` không tìm thấy file thường ném gì?** `NoSuchFileException` trên provider mặc định.
6. **`InputStream.read()` trả `-1` nghĩa là gì?** EOF bình thường.
7. **`BufferedReader.readLine()` trả `null` nghĩa là gì?** Hết dòng, không phải tự động lỗi I/O.
8. **`DataInputStream.readInt()` khi chỉ còn hai byte ném gì?** `EOFException`.
9. **Khi một thao tác ghi đã cập nhật nửa file rồi báo IOException, nên retry mù quáng?** Không; cần đánh giá dữ liệu đích và idempotency.
10. **`try-with-resources` đóng reader khi `readLine()` ném lỗi không?** Có, theo ngữ nghĩa TWR khi resource đã khởi tạo thành công.
11. **`close()` cũng ném trong khi phần thân đã ném: xem lỗi cleanup ở đâu?** Thường trong `getSuppressed()` của primary.
12. **Nếu chỉ `close()` lỗi mà phần thân thành công, lỗi close có luôn là suppressed không?** Không; nó có thể là primary.
13. **Có thể tìm nguyên nhân `IOException` chỉ bằng `getMessage()` và bỏ stack trace?** Không nên; cần xem Throwable và cause/suppressed khi chẩn đoán.
14. **Bọc lỗi từ tầng dưới bằng `new ImportException("...", original)` có tác dụng gì?** Thêm ngữ cảnh và giữ original làm cause.
15. **`Files.exists` có thay thế `catch (IOException)` không?** Không.
16. **Chọn sai chế độ `TRUNCATE_EXISTING` nhưng thao tác thành công có phát sinh IOException để cứu nội dung cũ không?** Không.
17. **Tại sao cần chỉ định UTF-8 khi đọc/ghi văn bản?** Để khớp mã hóa dữ liệu, tránh giả định charset không rõ ràng.
18. **Lỗi byte không hợp lệ với UTF-8 có thể gây ngoại lệ loại gì?** `MalformedInputException` nếu decoder được cấu hình báo lỗi.
19. **Nếu helper nhận input stream từ caller nhưng caller còn cần dùng, helper có nên `try (stream)` không?** Không, nếu ownership vẫn ở caller.
20. **Khi NIO báo AccessDeniedException, có nên luôn tạo file mới để sửa?** Không; phải giải quyết quyền/truy cập theo hợp đồng.
21. **`PrintWriter.println` có nhất thiết ném IOException trực tiếp giống `OutputStream.write` không?** Không; đọc hợp đồng `PrintWriter` và kiểm tra trạng thái lỗi khi cần.
22. **`IOException` có thể xuất hiện trong `close()` mà không phải ở `read()`/`write()` không?** Có.
23. **Lỗi từ `Files.createTempFile` có thể xảy ra trước khi vào `try` đóng reader không?** Có; phải xét chính xác thời điểm resource được tạo và scope chịu trách nhiệm.
24. **Vì sao `catch (Exception)` chung không phải lựa chọn mặc định tốt cho mọi lỗi I/O?** Nó gom cả các loại lỗi không liên quan, có thể che bug và làm mất chính sách phục hồi theo từng loại.

## 24. Tài liệu Java 17 chính thức

- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked exception chung của lỗi I/O.
- [Java SE 17 — FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): lỗi mở file của API cổ điển.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): các thao tác NIO.2 đọc, ghi, tạo, xóa và sao chép.
- [Java SE 17 — NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html): kiểu thông báo tệp không tồn tại trong NIO.
- [Java SE 17 — AccessDeniedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html): lỗi quyền truy cập tệp.
- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): file/reason của lỗi hệ thống tệp.
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read()`, EOF bằng `-1` và `transferTo`.
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và kết quả `null` ở EOF.
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()`, `readFully()` và `EOFException`.
- [Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): `write`, `flush`, `close`.
- [Java SE 17 — PrintWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html) và [PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): `checkError()` và contract ngoại lệ.
- [Java SE 17 — MalformedInputException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html): dữ liệu byte sai charset.
- [Java Language Specification 17 — `11 Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exception và các quy tắc catch/throws.
- [Java Language Specification 17 — `14.20.3 Try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): đóng tài nguyên tự động và suppressed exception.

**Ghi nhớ:** `IOException` là **checked exception** cho những thất bại I/O. `FileNotFoundException` là một subtype thường gặp khi **mở file bằng API cổ điển**, còn NIO.2 có thể trả `NoSuchFileException` hoặc `AccessDeniedException` cụ thể hơn. Đừng nhầm **EOF bình thường** (`read() == -1`, `readLine() == null`) với **lỗi I/O**, và đừng coi mở file thành công là bảo đảm đọc/ghi/đóng sẽ thành công. Hãy chọn API/charset/chế độ mở phù hợp, dùng `try-with-resources` khi sở hữu tài nguyên, giữ cause/suppressed để chẩn đoán, và xây chiến lược retry/cleanup dựa trên hợp đồng thực tế.
