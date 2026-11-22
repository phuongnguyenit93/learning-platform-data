# Tạo mới, ghi đè và ghi nối bằng OpenOption (Java 11+)

## 1. Vì sao cần chỉ rõ chế độ ghi tệp?

Khi thao tác với **tệp văn bản**, cùng một câu lệnh ghi có thể gây ra ba kết quả rất khác nhau: tạo tệp khi chưa có, thay toàn bộ nội dung tệp cũ, hoặc nối thêm nội dung vào cuối. Nếu chọn sai chế độ, chương trình có thể làm mất dữ liệu hoặc giữ lại phần đuôi cũ không mong muốn.

Java NIO giải quyết điều này bằng các **tùy chọn mở tệp**. `OpenOption` là giao diện biểu diễn một tùy chọn; `StandardOpenOption` là enum triển khai giao diện đó, cung cấp các giá trị `CREATE_NEW`, `CREATE`, `WRITE`, `TRUNCATE_EXISTING`, `APPEND` và nhiều tùy chọn khác.

Trong Java 11+, phương thức `Files.writeString` là cách gọn để ghi chuỗi văn bản, có thể nhận các `OpenOption` và sử dụng UTF-8 mặc định. Đây là API hiện hành, tiếp tục được hỗ trợ trên các JDK hiện đại.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
```

Thay vì tự kiểm tra tệp rồi đoán cách ghi, hãy **quyết định chính sách dữ liệu** trước khi mở: chỉ được tạo một lần, được phép thay thế, hay chỉ được ghi thêm.

## 2. Năm StandardOpenOption cần phân biệt

| Option | Chức năng | Lưu ý |
| --- | --- | --- |
| `WRITE` | Mở tệp để ghi | Không tự tạo tệp, cũng không mặc nhiên xóa nội dung cũ |
| `CREATE` | Tạo tệp mới nếu chưa tồn tại | Tệp đã tồn tại sẽ không tự bị cắt về `0` byte |
| `CREATE_NEW` | Chỉ tạo mới; báo lỗi nếu đường dẫn đã có | Kiểm tra và tạo mới được thực hiện nguyên tử ở bước mở |
| `TRUNCATE_EXISTING` | Nếu mở tệp đã tồn tại để ghi, cắt kích thước về `0` byte | Dùng để **thay toàn bộ** nội dung |
| `APPEND` | Đặt vị trí ghi ở cuối tệp | Dùng để **ghi nối**; không kết hợp với `TRUNCATE_EXISTING` |

**`CREATE` không có nghĩa là ghi đè**. Nó chỉ nói rằng khi đường dẫn **chưa có tệp**, Java có thể tạo tệp mới. Việc xóa nội dung cũ phải được chỉ định riêng bằng `TRUNCATE_EXISTING`.

**`CREATE_NEW` khác `CREATE`**: nếu đường dẫn đã tồn tại, `CREATE_NEW` từ chối mở để tạo mới. `CREATE_NEW` cũng từ chối đường dẫn là symbolic link dù đích liên kết không còn. Trong trường hợp đồng thời, thao tác kiểm tra tồn tại và tạo tệp mới là nguyên tử theo hợp đồng API; điều đó không bảo đảm mọi byte của nội dung được ghi như một giao dịch nguyên tử.

## 3. Các mẫu ghi thường dùng trong Java 11+

Các đoạn code sau giả sử biến `file` đã là một `Path` hợp lệ, thư mục cha có sẵn và phương thức gọi có xử lý `IOException`. Xem chương trình độc lập ở mục 4 nếu muốn biên dịch và chạy ngay.

### 3.1. Chỉ tạo lần đầu, không được thay tệp cũ

```java
Files.writeString(file, "Nội dung mới\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Nếu tệp chưa tồn tại, Java tạo rồi ghi. Nếu đường dẫn đã có, thao tác thất bại; trên hệ thống tệp thông dụng thường nhận `FileAlreadyExistsException`, một lớp con của `IOException`.

Sử dụng `CREATE_NEW` khi nội dung cũ **phải được bảo toàn**: không làm `if (!Files.exists(file))` rồi mở tệp theo cách cho phép ghi đè, vì tệp có thể xuất hiện giữa lúc kiểm tra và lúc ghi. `CREATE_NEW` gộp bước kiểm tra và tạo mới vào một thao tác mở.

### 3.2. Tạo nếu thiếu, ghi đè toàn bộ nếu đã tồn tại

```java
Files.writeString(file, "Nội dung thay thế\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

`CREATE` cho phép tạo tệp nếu thiếu. `TRUNCATE_EXISTING` cắt nội dung cũ về độ dài `0` khi đã có tệp; sau đó `WRITE` ghi dữ liệu mới.

Khi **không truyền bất kỳ option nào**, `Files.writeString` dùng mặc định tương đương **`CREATE + TRUNCATE_EXISTING + WRITE`**, đồng thời mã hóa văn bản thành UTF-8:

```java
Files.writeString(file, "Nội dung thay thế\n");
```

Vì vậy, cú pháp ngắn `Files.writeString(file, text)` **không phải ghi nối**. Nếu tệp đã có, nội dung cũ có thể bị thay thế toàn bộ.

### 3.3. Tạo nếu thiếu, ghi nối nếu đã tồn tại

```java
Files.writeString(file, "Bản ghi tiếp theo\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND,
        StandardOpenOption.WRITE);
```

Tổ hợp `CREATE + APPEND + WRITE` cho phép tạo tệp khi chưa có và nối thêm nội dung vào cuối khi đã tồn tại. Chỉ dùng `APPEND` mà không `CREATE` không phải chính sách “tự tạo nếu thiếu”.

**`Files.writeString` không tự chèn dấu xuống dòng**. Nếu muốn mỗi lần ghi nối có một dòng, dữ liệu truyền vào phải có `\n` hoặc `System.lineSeparator()`. Nếu không, hai lần ghi `"hello"` và `"world"` có thể tạo `"helloworld"`.

### 3.4. Chỉ thay thế khi tệp đã tồn tại

```java
Files.writeString(file, "Nội dung mới\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
```

Không có `CREATE` nên tệp thiếu sẽ gây lỗi I/O, thay vì âm thầm được tạo. Dùng cách này khi việc thiếu tệp phải được phát hiện.

### 3.5. Bẫy: chỉ `WRITE` có thể để lại phần đuôi cũ

```java
// File có nội dung "abcdef".
Files.writeString(file, "XY",
        StandardCharsets.UTF_8,
        StandardOpenOption.WRITE);
```

Với tệp `abcdef`, dữ liệu ghi từ đầu có thể tạo **`XYcdef`**: hai byte đầu bị thay, các byte còn lại không bị cắt bỏ. Nếu nội dung mới được mã hóa bằng UTF-8 nhiều byte, phần đuôi cũ có thể còn gây lỗi dữ liệu ký tự.

Nếu ý định là ghi đè **toàn bộ tệp**, luôn chỉ rõ `TRUNCATE_EXISTING` thay vì dựa riêng vào `WRITE`.

## 4. Chương trình hoàn chỉnh có thể biên dịch và chạy

Ví dụ sau được thiết kế an toàn khi học: tạo một thư mục tạm, ghi ba tệp **trong chính thư mục đó** rồi xóa chúng ở `finally`. Không cần thư viện bên ngoài JDK.

Tạo tệp **`TextOpenOptionDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import static java.nio.file.StandardOpenOption.*;

public class TextOpenOptionDemo {
    private static void show(String label, Path path) throws IOException {
        String text = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println(label + ": " + text.replace("\n", "\\n"));
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("open-options-");
        Path file = dir.resolve("notes.txt");
        Path simple = dir.resolve("simple.txt");
        Path tail = dir.resolve("tail.txt");
        try {
            Files.writeString(file, "first\n", StandardCharsets.UTF_8,
                    CREATE_NEW, WRITE);
            show("create-new", file);

            try {
                Files.writeString(file, "wrong\n", StandardCharsets.UTF_8,
                        CREATE_NEW, WRITE);
            } catch (FileAlreadyExistsException e) {
                System.out.println("create-new again: blocked");
            }

            Files.writeString(file, "reset\n", StandardCharsets.UTF_8,
                    CREATE, TRUNCATE_EXISTING, WRITE);
            show("overwrite", file);

            Files.writeString(file, "more\n", StandardCharsets.UTF_8,
                    CREATE, APPEND, WRITE);
            show("append", file);

            Files.writeString(simple, "original\n");
            Files.writeString(simple, "new\n");
            show("defaults", simple);

            Files.writeString(tail, "abcdef");
            Files.writeString(tail, "XY", StandardCharsets.UTF_8, WRITE);
            show("write-only", tail);

            Files.writeString(tail, "OK", StandardCharsets.UTF_8,
                    WRITE, TRUNCATE_EXISTING);
            show("truncate", tail);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(simple);
            Files.deleteIfExists(tail);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy từ thư mục chứa tệp, bằng JDK 11 trở lên. Tùy chọn `--release 11` bảo đảm mã có thể biên dịch theo API và cú pháp Java 11:

```bash
javac --release 11 TextOpenOptionDemo.java
java TextOpenOptionDemo
```

Kết quả đã xác minh khi biên dịch ở mức Java 11:

```text
create-new: first\n
create-new again: blocked
overwrite: reset\n
append: reset\nmore\n
defaults: new\n
write-only: XYcdef
truncate: OK
```

Hàm `show` thay ký tự xuống dòng thật bằng hai ký tự `\` và `n`, giúp thấy rõ nội dung tệp. Chương trình thực hiện lần lượt:

1. **Tạo mới:** `CREATE_NEW, WRITE` tạo `notes.txt` chứa `first\n`.
2. **Tạo lại:** đường dẫn đã tồn tại, nên `CREATE_NEW` thất bại; không ghi `wrong\n` lên nội dung cũ.
3. **Ghi đè:** `CREATE, TRUNCATE_EXISTING, WRITE` làm tệp chỉ còn `reset\n`.
4. **Ghi nối:** `CREATE, APPEND, WRITE` thêm `more\n`, cho kết quả `reset\nmore\n`.
5. **Mặc định:** hai lần `writeString` không option làm tệp cuối cùng chỉ còn `new\n`.
6. **Ghi từ đầu:** ghi `XY` với `WRITE` cho ra `XYcdef`; thêm `TRUNCATE_EXISTING` khiến tệp chỉ còn `OK`.

Ví dụ bắt `FileAlreadyExistsException` là loại ngoại lệ cụ thể phổ biến trên hệ thống tệp mặc định. Tùy provider, lỗi I/O có thể được biểu diễn khác; ứng dụng vẫn cần chính sách xử lý `IOException`.

## 5. Bảng lựa chọn nhanh

| Yêu cầu | Tổ hợp option | Tệp chưa có | Tệp đã có |
| --- | --- | --- | --- |
| Chỉ tạo duy nhất, không đụng tệp cũ | `CREATE_NEW, WRITE` | Tạo, ghi | Báo lỗi |
| Tạo hoặc ghi đè **toàn bộ** | `CREATE, TRUNCATE_EXISTING, WRITE` | Tạo, ghi | Cắt về `0` rồi ghi |
| Tạo hoặc ghi **nối cuối** | `CREATE, APPEND, WRITE` | Tạo, ghi | Thêm cuối tệp |
| Chỉ ghi đè khi đã tồn tại | `WRITE, TRUNCATE_EXISTING` | Báo lỗi | Cắt về `0` rồi ghi |
| Chỉ ghi từ đầu và giữ phần đuôi | `WRITE` | Báo lỗi | Có thể giữ phần đuôi cũ |
| Gọi `Files.writeString(path, text)` không option | Mặc định `CREATE, TRUNCATE_EXISTING, WRITE` | Tạo, ghi | Cắt về `0` rồi ghi |

Bảng trên mô tả ngữ nghĩa khi ghi qua `Files.writeString`. Các phương thức mở tệp khác có thể có quy tắc mặc định riêng; khi đổi API, cần xem Javadoc của phương thức đó.

## 6. UTF-8, xuống dòng và thư mục cha

### Mã hóa văn bản

`Files.writeString(Path, CharSequence)` dùng charset **UTF-8** theo mặc định trong Java 11+. Có thể truyền `StandardCharsets.UTF_8` tường minh nếu dự án yêu cầu làm rõ encoding:

```java
Files.writeString(file, "Xin chào, Java!\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND,
        StandardOpenOption.WRITE);
```

Khi đọc lại, nên thống nhất charset:

```java
String content = Files.readString(file, StandardCharsets.UTF_8);
```

`writeString` ghi các ký tự được truyền vào, **không tự thêm `\n`**. Dùng `"\n"` nếu định dạng tệp quy định LF; dùng `System.lineSeparator()` nếu muốn dấu kết thúc dòng theo môi trường chạy.

### Thư mục cha không tự sinh

`CREATE` cho phép tạo **tệp mới**, không tạo toàn bộ thư mục cha. Khi `output/reports` chưa có, cần chủ động tạo:

```java
// Mảnh mã trong phương thức xử lý IOException.
Path file = Path.of("output", "reports", "note.txt");
Files.createDirectories(file.getParent());

Files.writeString(file, "Báo cáo\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

Đường dẫn tương đối được tính từ thư mục làm việc của tiến trình. Với ứng dụng thực, lấy đường dẫn từ cấu hình, xác minh quyền ghi và chỉ tạo thư mục nếu chính sách cho phép.

## 7. Trường hợp sai, lỗi I/O và giới hạn an toàn

### Không kết hợp `APPEND` với `TRUNCATE_EXISTING`

`APPEND` muốn giữ nội dung cũ và nối ở cuối, trong khi `TRUNCATE_EXISTING` yêu cầu cắt nội dung. Đây là tổ hợp không hợp lệ:

```java
// CỐ Ý SAI: không dùng chung APPEND với TRUNCATE_EXISTING.
Files.writeString(file, "x", StandardCharsets.UTF_8,
        StandardOpenOption.APPEND,
        StandardOpenOption.TRUNCATE_EXISTING);
```

`APPEND` cũng không được dùng chung với `READ` trong quy tắc mở kênh `Files.newByteChannel`. Chọn chính sách ghi nối hoặc ghi đè theo nhu cầu, không trộn các option trái nghĩa.

### Ghi nối không bảo đảm mọi tiến trình ghi nguyên tử

`APPEND` xác định vị trí ghi ở cuối tệp. Tuy nhiên, việc chuyển đến cuối và ghi dữ liệu có thể **không nguyên tử giữa nhiều tiến trình** trên mọi hệ thống tệp. Khi nhiều thread hoặc chương trình cùng ghi một tệp, cần thiết kế đồng bộ/file lock hoặc cơ chế logging đáng tin cậy.

### `CREATE_NEW` nguyên tử ở lúc tạo, không nguyên tử toàn bộ nội dung

`CREATE_NEW` bảo vệ thao tác **kiểm tra đường dẫn tồn tại và tạo tệp**. Nó không bảo đảm dữ liệu ghi xong nếu giữa chừng có lỗi I/O, mất điện hoặc hết dung lượng. Tương tự, `TRUNCATE_EXISTING` có thể cắt tệp trước khi hoàn tất ghi; sau lỗi, nội dung có thể rỗng hoặc chỉ có một phần.

Nếu hệ thống cần thay tệp quan trọng an toàn hơn, có thể viết dữ liệu sang một tệp tạm cùng hệ thống tệp, rồi dùng `Files.move` với `StandardCopyOption.ATOMIC_MOVE` **khi provider hỗ trợ**. Cần xử lý lỗi move và các yêu cầu về đồng bộ/durability riêng; bản thân `writeString` không phải giao dịch cơ sở dữ liệu.

### Bảng lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| `FileAlreadyExistsException` | `CREATE_NEW` gặp đường dẫn đã tồn tại | Giữ nguyên tệp; chỉ đổi sang chế độ thay thế nếu nghiệp vụ cho phép |
| `NoSuchFileException` | Thiếu tệp khi chỉ có `WRITE`, hoặc thiếu thư mục cha | Cân nhắc `CREATE` hoặc tạo thư mục cha bằng `createDirectories` |
| Nội dung đuôi cũ còn lại | Có `WRITE` nhưng thiếu `TRUNCATE_EXISTING` | Với ghi đè toàn bộ, thêm `TRUNCATE_EXISTING` |
| Hai bản ghi dính vào nhau | `writeString` không chèn xuống dòng | Thêm `\n`/`System.lineSeparator()` |
| `IllegalArgumentException` về option | Tổ hợp không hợp lệ, như `APPEND` và `TRUNCATE_EXISTING` | Chọn tổ hợp rõ chính sách |
| `AccessDeniedException` hoặc `IOException` | Quyền, đường dẫn, thiết bị, lỗi I/O hoặc file system | Kiểm tra thông tin ngoại lệ và điều kiện vận hành |
| Ký tự bị lỗi | Charset đọc/ghi không thống nhất hoặc tệp hỏng khi ghi dở | Sử dụng UTF-8 nhất quán và xử lý lỗi ghi |

Không tự coi việc mở/ghi là luôn thành công. Trong code sản xuất, xử lý ngoại lệ theo chính sách ứng dụng, báo rõ lỗi có thể khắc phục và tránh bỏ qua lỗi ghi.

## 8. Nhiều lần ghi: Files.newBufferedWriter

Khi muốn viết nhiều đoạn hoặc nhiều dòng trong một lần mở tệp, `Files.newBufferedWriter` vẫn là API phù hợp. Nó nhận cùng họ `StandardOpenOption`; đóng tài nguyên qua `try`-with-resources. Ví dụ dưới là **mảnh mã** đặt trong phương thức xử lý `IOException`:

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import static java.nio.file.StandardOpenOption.*;

Path log = Path.of("logs", "events.txt");
Files.createDirectories(log.getParent());

try (BufferedWriter out = Files.newBufferedWriter(
        log, StandardCharsets.UTF_8, CREATE, APPEND, WRITE)) {
    out.write("event A");
    out.newLine();
    out.write("event B");
    out.newLine();
}
```

`BufferedWriter.newLine()` dùng dấu xuống dòng của nền tảng. `try`-with-resources tự đóng writer kể cả khi có ngoại lệ sau khi mở. Nếu ứng dụng yêu cầu logging nhiều tiến trình, xoay vòng và retention, hãy dùng framework logging phù hợp; ví dụ này nhằm giải thích chính sách mở tệp.

## 9. Bài tập tự kiểm tra

**Bài 1.** Muốn tạo file `invoice.txt` mới nhưng không được thay thế file đã có, sử dụng gì?

**Đáp án:** `CREATE_NEW + WRITE`. Không kiểm tra `Files.exists` rồi ghi bằng chế độ thay thế.

**Bài 2.** Một file chứa `abcdef`, ghi `XY` bằng `WRITE` có thể cho kết quả nào? Muốn chỉ còn `XY` phải làm gì?

**Đáp án:** `XYcdef`, vì byte cũ ở phần đuôi có thể còn lại. Thêm `TRUNCATE_EXISTING`.

**Bài 3.** Muốn ghi từng dòng sự kiện vào cuối `events.txt` và tự tạo file khi thiếu?

**Đáp án:** `CREATE + APPEND + WRITE`, kèm xuống dòng trong dữ liệu hoặc `BufferedWriter.newLine()`, đồng thời tạo thư mục cha nếu chưa có.

**Bài 4.** `Files.writeString(file, "new")` không truyền option có mặc định là nối hay thay?

**Đáp án:** **Thay toàn bộ**, vì mặc định `CREATE + TRUNCATE_EXISTING + WRITE`.

**Bài 5.** Khi dùng `CREATE_NEW`, điều gì là nguyên tử và điều gì không được bảo đảm nguyên tử?

**Đáp án:** Kiểm tra-tạo tệp khi mở là nguyên tử; toàn bộ việc ghi dữ liệu không được bảo đảm là một giao dịch nguyên tử.

## 10. Ghi nhớ

Với tệp văn bản Java 11+, `Files.writeString` là cách đơn giản để ghi UTF-8, nhưng phải chọn rõ chính sách mở tệp:

- **Tạo duy nhất, không ghi đè:** `CREATE_NEW + WRITE`.
- **Tạo hoặc thay toàn bộ:** `CREATE + TRUNCATE_EXISTING + WRITE`.
- **Tạo hoặc ghi nối cuối:** `CREATE + APPEND + WRITE`.
- **Chỉ thay file có sẵn:** `WRITE + TRUNCATE_EXISTING`.

`Files.writeString` không tự thêm dòng mới. Không có option thì nó mặc định **tạo hoặc ghi đè toàn bộ**, còn `WRITE` đơn lẻ có thể giữ phần đuôi cũ. Các kỹ thuật này vẫn là kiến thức áp dụng được hiện nay; cần thêm xử lý lỗi, chính sách file path, đồng thời và an toàn dữ liệu theo mức độ quan trọng của tệp.

### Tài liệu chính thức

- [Java SE 25 — StandardOpenOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [Java SE 25 — Files.writeString, newBufferedWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 11 — Files.writeString (Since: 11)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 25 — OpenOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/OpenOption.html)
