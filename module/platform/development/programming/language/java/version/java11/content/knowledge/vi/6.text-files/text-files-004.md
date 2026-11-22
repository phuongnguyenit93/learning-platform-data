# Files.writeString với CharSequence — ghi tệp văn bản đúng cách (Java 11+)

> **Ngữ cảnh:** Java 11 giới thiệu `Files.writeString` trong `java.nio.file.Files`. API này vẫn được hỗ trợ trên các JDK hiện đại. Nó ghi một `CharSequence` ra tệp văn bản qua `Path`, mặc định mã hóa UTF-8. Đây là lựa chọn gọn cho nội dung có kích thước vừa và có thể tạo sẵn dưới dạng chuỗi ký tự.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của `Path`, `CharSequence`, `Charset`, `OpenOption` và kết quả `Path` trong `Files.writeString`.
2. Viết tệp văn bản từ `String`, `StringBuilder` hoặc `CharSequence` tương thích Java 11.
3. Phân biệt **mặc định ghi đè**, **ghi nối thêm** và **chỉ tạo tệp mới**; tránh làm mất nội dung do chọn sai tùy chọn.
4. Xác định chính xác **UTF-8**, **xuống dòng** và **byte trên đĩa** khác nhau như thế nào.
5. Đọc lại nội dung, xử lý `IOException` và hiểu giới hạn của thao tác ghi một lần.
6. Chọn `Files.writeString`, `Files.write` hoặc `Files.newBufferedWriter` cho đúng tình huống.

## 2. Chữ ký API và hợp đồng quan trọng

Có hai overload chính của `Files.writeString`, đều xuất hiện từ **Java 11**:

~~~java
// Mặc định mã hóa UTF-8
static Path writeString(
    Path path,
    CharSequence csq,
    OpenOption... options
) throws IOException;

// Chỉ định bộ mã hóa
static Path writeString(
    Path path,
    CharSequence csq,
    Charset cs,
    OpenOption... options
) throws IOException;
~~~

Đây là **chữ ký rút gọn để giải thích**, không phải một chương trình Java độc lập. Phương thức thực sự được gọi dưới tên `Files.writeString(...)`, không cần tự viết lại chữ ký.

| Thành phần | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `path` — `java.nio.file.Path` | Định vị tệp cần ghi | `Path.of("notes.txt")` là đường dẫn tương đối; `Files` xử lý I/O |
| `csq` — `CharSequence` | Nội dung ký tự cần ghi | Có thể là `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` hoặc implementation khác |
| `cs` — `Charset` | Chuyển ký tự thành các byte lưu trên đĩa | Nếu không truyền, **UTF-8**; không tự lấy charset mặc định hệ điều hành |
| `options` — `OpenOption...` | Quy định tạo mới, ghi đè, nối thêm... | Không truyền tùy chọn nghĩa là tạo tệp nếu thiếu và **xóa nội dung cũ** nếu tệp đã tồn tại |
| Kết quả `Path` | Trả về chính `path` được truyền vào | Không trả về chuỗi, số ký tự hoặc số byte đã ghi |
| `IOException` | Báo lỗi tạo/ghi tệp hoặc lỗi mã hóa | Người gọi phải xử lý hoặc khai báo `throws IOException` |

**Hợp đồng mặc định:**

~~~java
Files.writeString(path, csq);
~~~

Tương đương về charset và chế độ mở tệp với ý định:

~~~java
Files.writeString(
    path,
    csq,
    StandardCharsets.UTF_8,
    StandardOpenOption.CREATE,
    StandardOpenOption.TRUNCATE_EXISTING,
    StandardOpenOption.WRITE
);
~~~

Nói cách khác: nếu chưa có tệp thì tạo; nếu tệp thường đã tồn tại thì **ghi nội dung mới thay cho nội dung cũ**. Đừng gọi cách mặc định khi bạn muốn *append* một dòng log.

**Từng ký tự được ghi đúng theo `CharSequence`:** nếu chuỗi có `"\n"`, dấu xuống dòng đó được ghi; nếu không có, `writeString` **không tự thêm** ký tự xuống dòng cuối tệp, dấu phân cách hoặc BOM. Số ký tự Java và số byte UTF-8 có thể khác nhau.

## 3. Vì sao tham số là CharSequence, không chỉ String?

`CharSequence` là interface biểu diễn một chuỗi ký tự, khai báo các thao tác như `length()`, `charAt(int)` và `subSequence(int,int)`. `String` là một implementation phổ biến nhưng không phải loại duy nhất.

Ví dụ **minh họa các lời gọi**, giả sử biến `path` đã trỏ tới tệp có thể ghi:

~~~java
Files.writeString(path, "Hello");                 // String

StringBuilder builder = new StringBuilder();
builder.append("Xin chào");
builder.append(" Java 11");
Files.writeString(path, builder);                  // StringBuilder

CharSequence message = new StringBuilder("Ready");
Files.writeString(path, message);                  // Biến kiểu CharSequence
~~~

Các lần gọi trên **thay thế nội dung tệp** theo thứ tự; kết quả cuối của tệp là `Ready`. Đoạn này không phải chương trình độc lập; muốn chạy cần tạo `Path`, import các class và xử lý `IOException`.

Phân biệt thêm:

- `String` không đổi nội dung sau khi tạo. `StringBuilder` có thể thêm, xóa hoặc thay ký tự; nó **không bảo đảm an toàn luồng** nếu bị nhiều thread sửa đồng thời.
- `Files.writeString(path, builder)` ghi nội dung **tại lần thực hiện lệnh ghi**. Sửa `builder` sau khi phương thức trả về không cập nhật tệp tự động.
- Tránh sửa `CharSequence` trong lúc thread khác đang ghi, vì API không cam kết một bản chụp nhất quán khi nguồn mutable bị thay đổi đồng thời. Nếu cần nội dung ổn định, tạo một `String` snapshot trước khi ghi.
- `CharSequence` biểu diễn **ký tự**, còn tệp chứa **byte**. `Charset` quyết định cách chuyển từ chuỗi ký tự sang byte; không nên suy ra kích thước tệp từ `csq.length()`.

**Khi nào nên dùng `StringBuilder`?** Khi xây dựng nội dung từ nhiều phần, ví dụ ghép header, dữ liệu và dòng tổng kết. Bạn có thể truyền builder trực tiếp cho `Files.writeString`, không bắt buộc gọi `toString()` chỉ để đáp ứng kiểu tham số.

## 4. Chương trình đầy đủ: ghi, đọc lại, append, ghi đè và tạo mới

Ví dụ sau cố ý tạo **thư mục tạm riêng** để tránh sửa tệp có sẵn của bạn. Sau khi in kết quả, nó xóa các tệp thử và thư mục tạm. Các thao tác `Files.writeString` dùng API Java 11 tiêu chuẩn.

Tạo tệp **`WriteStringDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class WriteStringDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("write-string-demo-");
        Path note = dir.resolve("note.txt");
        Path ascii = dir.resolve("ascii.txt");

        try {
            // 1. CharSequence có thể là StringBuilder.
            CharSequence original = new StringBuilder("Xin chao");
            Path returned = Files.writeString(note, original);

            System.out.println("samePath=" + returned.equals(note));
            System.out.println("initial=" + Files.readString(note));

            // 2. Nối thêm đúng một ký tự xuống dòng và một dòng văn bản.
            Files.writeString(
                    note,
                    "\nJava 11",
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND
            );
            System.out.println(
                    "append=" + Files.readString(note).replace("\n", " | ")
            );

            // 3. Không có options: nội dung cũ bị thay bằng nội dung mới.
            Files.writeString(note, "Moi");
            System.out.println("replace=" + Files.readString(note));

            // 4. CREATE_NEW từ chối ghi lên tệp đang tồn tại.
            try {
                Files.writeString(
                        note,
                        "failed",
                        StandardOpenOption.CREATE_NEW
                );
            } catch (FileAlreadyExistsException ex) {
                System.out.println("createNew=exists");
            }

            // 5. Chỉ định charset khi giao thức/tệp yêu cầu.
            Files.writeString(
                    ascii,
                    "A-B",
                    StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW
            );
            System.out.println(
                    "ascii=" + Files.readString(ascii, StandardCharsets.US_ASCII)
            );
        } finally {
            Files.deleteIfExists(ascii);
            Files.deleteIfExists(note);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 11 trở lên:

~~~bash
javac WriteStringDemo.java
java WriteStringDemo
~~~

Nếu dùng JDK mới hơn và vẫn cần giới hạn mã nguồn ở Java 11, có thể biên dịch bằng `javac --release 11 WriteStringDemo.java` khi compiler hỗ trợ target release đó.

**Stdout đã kiểm thử trên JDK với filesystem mặc định:**

~~~text
samePath=true
initial=Xin chao
append=Xin chao | Java 11
replace=Moi
createNew=exists
ascii=A-B
~~~

Giải thích theo đúng thứ tự:

1. `Files.writeString` tạo `note.txt` vì trước đó chưa có tệp. Nó trả về chính `Path` đã truyền, nên phép so sánh `returned.equals(note)` đúng.
2. `Files.readString(note)` (cũng có từ Java 11) đọc nội dung và mặc định dùng UTF-8.
3. `CREATE` kết hợp `APPEND` thêm `"\nJava 11"` vào cuối tệp; `replace("\n", " | ")` **chỉ thay cách hiển thị trên console** cho dễ xem, không thay nội dung tệp.
4. Gọi `Files.writeString(note, "Moi")` không có tùy chọn sẽ truncate và ghi nội dung mới, vì vậy kết quả chỉ còn `Moi`.
5. `CREATE_NEW` yêu cầu tạo **một tệp mới**; khi tệp hiện có, trên filesystem thông dụng của JDK sẽ nhận `FileAlreadyExistsException`. Javadoc đánh dấu đây là ngoại lệ cụ thể có thể có; các triển khai/provider khác vẫn có thể báo lỗi I/O phù hợp.
6. Overload có `StandardCharsets.US_ASCII` ghi và đọc tệp chỉ chứa ký tự ASCII. Nếu văn bản có tiếng Việt, ưu tiên UTF-8.

**Chú ý:** `finally` cố gắng dọn sạch tệp/thư mục tạm, nhưng việc xóa có thể ném `IOException` (ví dụ tệp đang bị tiến trình khác giữ). Với ứng dụng thực tế, xử lý cleanup theo chính sách lỗi của chương trình. Bài kiểm thử không in đường dẫn thư mục tạm để stdout không phụ thuộc máy.

## 5. Tùy chọn mở tệp: chọn đúng hành vi

Đối số `OpenOption...` thường sử dụng các giá trị thuộc `StandardOpenOption`. Bảng dưới cho thấy các cách thường gặp:

| Yêu cầu | Lời gọi | Hành vi quan trọng |
| --- | --- | --- |
| Ghi văn bản mới, tạo nếu chưa có và **ghi đè** nếu đã có | `Files.writeString(path, text)` | Mặc định `CREATE` + `TRUNCATE_EXISTING` + `WRITE` |
| Chỉ tạo nếu tệp chưa tồn tại | `Files.writeString(path, text, CREATE_NEW)` | Tránh ghi đè tệp đang tồn tại |
| Thêm vào cuối tệp, tạo nếu chưa có | `Files.writeString(path, text, CREATE, APPEND)` | Không tự thêm xuống dòng; tự đưa dấu phân cách vào `text` |
| Chỉ ghi nội dung mới vào tệp đang tồn tại | `Files.writeString(path, text, WRITE, TRUNCATE_EXISTING)` | Không chỉ định `CREATE`, nên tệp chưa có sẽ dẫn tới lỗi |
| Tạo nếu thiếu hoặc ghi lại rõ ràng | `Files.writeString(path, text, CREATE, TRUNCATE_EXISTING, WRITE)` | Cách diễn đạt tường minh mục đích ghi đè |

Trong bảng, các tên `CREATE`, `APPEND`, `WRITE`, `TRUNCATE_EXISTING` và `CREATE_NEW` là hằng số `StandardOpenOption`; trong mã đầy đủ cần import hoặc viết `StandardOpenOption.CREATE`, v.v.

### 5.1. APPEND không thêm newline

Hai lệnh:

~~~java
Files.writeString(path, "Dòng 1");
Files.writeString(path, "Dòng 2", StandardOpenOption.APPEND);
~~~

tạo văn bản **`Dòng 1Dòng 2`** vì không lệnh nào thêm `\n`. Nếu muốn xuống dòng:

~~~java
Files.writeString(path, "Dòng 1" + System.lineSeparator());

Files.writeString(
        path,
        "Dòng 2" + System.lineSeparator(),
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND
);
~~~

`System.lineSeparator()` dùng dấu kết thúc dòng của nền tảng; nếu định dạng file/giao thức yêu cầu nhất quán ký tự LF `\n`, hãy dùng `\n` tường minh. Không cần `System.lineSeparator()` trong mọi tình huống.

### 5.2. Các kết hợp không hợp lệ

- **`APPEND` và `TRUNCATE_EXISTING`** là hai ý định trái nhau; không phối hợp chúng. Tài liệu `StandardOpenOption` quy định việc phối hợp này không hợp lệ trên một số ngữ cảnh mở tệp.
- `CREATE_NEW` khác `CREATE`: `CREATE` chấp nhận tệp đã có; `CREATE_NEW` yêu cầu không có tệp đang tồn tại và tạo mới một cách nguyên tử đối với việc kiểm tra-tạo tệp theo hợp đồng filesystem.
- `CREATE` không có nghĩa là tự tạo toàn bộ **thư mục cha**. Nó chỉ có thể tạo tệp trong thư mục cha đã tồn tại.
- Các `OpenOption` không hợp lệ hoặc không được filesystem provider hỗ trợ có thể dẫn tới `IllegalArgumentException` hoặc `UnsupportedOperationException`.
- Đừng dựa vào “lệnh chạy được một lần” để kết luận một tổ hợp tùy chọn được hỗ trợ trên mọi filesystem.

### 5.3. CREATE_NEW phù hợp khi nào?

Nếu người dùng tạo báo cáo lần đầu và chương trình **không được ghi đè báo cáo cũ**, sử dụng `CREATE_NEW`. Tránh kiểu kiểm tra không an toàn:

~~~java
// Có khoảng thời gian giữa kiểm tra và hành động: không phù hợp
// khi nhiều tiến trình có thể cùng tạo tệp.
if (!Files.exists(path)) {
    Files.writeString(path, text);
}
~~~

Việc dùng `CREATE_NEW` kết hợp kiểm tra tồn tại và tạo tệp thành một yêu cầu tạo mới có bảo đảm phù hợp hơn cho cạnh tranh tạo tệp. Tuy nhiên, bạn vẫn phải xử lý `IOException` đúng cách và hiểu hành vi cụ thể của filesystem/provider.

## 6. UTF-8, Charset và dữ liệu tiếng Việt

`CharSequence` chứa **ký tự**, không phải byte. `Files.writeString(path, text)` mã hóa các ký tự thành **UTF-8**, **kể cả trên Windows**. Đây là quy tắc của chính overload này từ Java 11; không cần đoán `Charset.defaultCharset()` hay phụ thuộc cấu hình locale của người dùng.

~~~java
Path path = Path.of("loi-chao.txt");

// UTF-8 mặc định.
Files.writeString(path, "Xin chào Java");

// Cách viết rõ charset, tương đương về mã hóa.
Files.writeString(path, "Xin chào Java", StandardCharsets.UTF_8);

// Khi đọc lại, dùng cùng charset đã ghi.
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đoạn trên là ví dụ minh họa **cần import, xử lý IOException và thư mục làm việc thích hợp**. Hai lần gọi `writeString` thay thế nội dung tệp; chúng không tự nối thêm.

Một ví dụ gần với cấu trúc thực tế:

~~~java
Path directory = Path.of("output");
Files.createDirectories(directory);

Path file = directory.resolve("message.txt");
CharSequence content = new StringBuilder()
        .append("Tác giả: An")
        .append("\n")
        .append("Trạng thái: hoàn thành")
        .append("\n");

Files.writeString(file, content, StandardCharsets.UTF_8);
~~~

Nếu được thực thi trong một phương thức đã xử lý `IOException` và có các import tương ứng, đoạn này sẽ tạo thư mục `output` nếu cần và ghi `output/message.txt`. `Files.createDirectories(directory)` là bước riêng; `Files.writeString` không tự tạo thư mục cha.

### 6.1. Độ dài ký tự khác số byte

Ví dụ, ký tự ASCII `A` chiếm một byte UTF-8; nhiều ký tự tiếng Việt có dấu cần nhiều byte; một số ký tự Unicode có thể dùng bốn byte UTF-8. Vì vậy:

~~~java
String content = "Xin chào";
// content.length() không phải là kích thước file UTF-8.
int numberOfBytes = content.getBytes(StandardCharsets.UTF_8).length;
~~~

- `String.length()` đếm **đơn vị UTF-16**, không phải số Unicode code point và không phải số byte sau mã hóa.
- `Files.size(path)` (sau khi ghi) cho biết kích thước tệp dưới dạng **byte**, có thể khác với cả `length()` và số code point.
- Nếu chuỗi chứa ký tự không thể mã hóa bằng `Charset` đã chọn, `Files.writeString` có thể báo `IOException` theo hợp đồng; không nên âm thầm trông đợi việc chuyển thành dấu hỏi.
- Không ghi bằng UTF-8 rồi đọc lại bằng một charset khác. Điều này có thể tạo nội dung sai hoặc lỗi giải mã.

### 6.2. Không tự thêm BOM

`writeString` không tự thêm dấu BOM hoặc tiền tố file. Nếu định dạng bên ngoài yêu cầu BOM, đó là một yêu cầu định dạng riêng cần được triển khai và kiểm chứng. Đối với tệp UTF-8 thông thường, không cần thêm BOM chỉ để các dấu tiếng Việt hiển thị đúng.

## 7. CharSequence chứa dòng, không phải danh sách dòng

So sánh hai cách API:

~~~java
Files.writeString(path, "A\nB");  // Ghi đúng ký tự A, LF, B
~~~

và:

~~~java
Files.write(
        path,
        java.util.List.of("A", "B"),
        StandardCharsets.UTF_8
);
~~~

Ở cách thứ nhất, `writeString` ghi **nguyên chuỗi**, không thêm newline sau `B`. Ở cách thứ hai, overload `Files.write(path, Iterable<? extends CharSequence> lines, Charset, ...)` ghi **từng phần tử như một dòng** và thêm ký tự kết thúc dòng theo nền tảng sau mỗi phần tử, theo hợp đồng phương thức.

Vì vậy:

- Ghi sẵn một nội dung văn bản đầy đủ, bao gồm newline: **`Files.writeString`**.
- Có sẵn một danh sách các dòng và muốn API xử lý dấu xuống dòng: có thể dùng **`Files.write` với `Iterable<? extends CharSequence>`**.
- Nếu dữ liệu lớn, được sinh ra liên tục hoặc cần xử lý theo luồng: dùng **`Files.newBufferedWriter`** cùng `try-with-resources` để ghi từng phần, thay vì xây dựng một `StringBuilder` khổng lồ.

Ví dụ minh họa cách ghi từng dòng theo luồng, trong một method đã khai báo `throws IOException`:

~~~java
try (var writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING
)) {
    writer.write("Hàng 1");
    writer.newLine();
    writer.write("Hàng 2");
    writer.newLine();
}
~~~

`var` được hỗ trợ từ Java 10 nên ví dụ trên tương thích Java 11. Với `newBufferedWriter`, bạn **phải** đóng writer bằng `try-with-resources` hoặc cơ chế tương đương; còn `Files.writeString` tự quản lý việc mở và đóng tài nguyên cho một lời gọi.

## 8. Ngoại lệ, ghi dở và tính an toàn dữ liệu

`Files.writeString` khai báo `throws IOException` vì quá trình tạo/ghi tệp có thể thất bại. Nguyên nhân thường gặp: thiếu thư mục cha, không có quyền ghi, đĩa đầy, đường dẫn trỏ tới thư mục, lỗi filesystem, không mã hóa được ký tự bằng charset được chọn hoặc cạnh tranh thao tác với tiến trình khác.

Các ngoại lệ liên quan:

| Loại lỗi | Bối cảnh điển hình | Phản ứng phù hợp |
| --- | --- | --- |
| `IOException` | Lỗi I/O hoặc mã hóa, kể cả lỗi phát sinh sau khi đã mở tệp | Xử lý ở ranh giới I/O, thông báo đường dẫn/thao tác và giữ nguyên nguyên nhân |
| `NoSuchFileException` | Thư mục cha không tồn tại hoặc tệp cần mở không có | Xác nhận/`createDirectories` cho thư mục được phép; không tự tạo ngẫu nhiên mọi path |
| `FileAlreadyExistsException` | `CREATE_NEW` khi tên đã tồn tại, nếu provider báo loại lỗi cụ thể này | Đổi tên, yêu cầu xác nhận hoặc giữ tệp cũ |
| `IllegalArgumentException` | Kết hợp `OpenOption` không hợp lệ | Sửa tổ hợp tùy chọn trong code |
| `UnsupportedOperationException` | Tùy chọn không được provider hỗ trợ | Chọn tùy chọn hợp lệ theo filesystem thực tế |
| `NullPointerException` | Truyền tham số bắt buộc `null` | Kiểm tra/chặn null ở tầng gọi phù hợp |

Ví dụ mô hình xử lý cho một ứng dụng CLI:

~~~java
try {
    Files.writeString(path, text, StandardCharsets.UTF_8);
    System.out.println("Đã ghi tệp");
} catch (IOException ex) {
    System.err.println("Không thể ghi: " + path + " (" + ex + ")");
}
~~~

Đây là **đoạn minh họa nằm trong method**, sử dụng `path` và `text` đã được khai báo; không phải tệp chạy độc lập.

### 8.1. Ghi thành công không đồng nghĩa ghi nguyên tử

Đặc biệt với chế độ ghi đè, một lần `Files.writeString` **không cam kết** cập nhật tệp như một giao dịch nguyên tử. Nếu gặp lỗi I/O, tệp đích có thể đã được tạo, đã bị truncate hoặc mới ghi được một phần nội dung. Cũng không nên coi lời gọi này là bảo đảm đồng bộ dữ liệu đã được lưu bền vững xuống thiết bị trong mọi tình huống.

Nếu bài toán yêu cầu bảo toàn phiên bản cũ đến khi phiên bản mới hoàn chỉnh, cân nhắc mô hình **ghi vào tệp tạm cùng filesystem, rồi thay thế bằng thao tác move thích hợp**. `StandardCopyOption.ATOMIC_MOVE` chỉ dùng khi provider hỗ trợ; vẫn phải xử lý việc move thất bại và kiểm thử trên filesystem triển khai. Đây là bài toán nâng cao về độ tin cậy, không phải mặc định của `Files.writeString`.

### 8.2. Nhiều thread/process cùng ghi

- `Files.writeString` không tự cung cấp khóa hoặc bảo đảm **mỗi lời gọi append của toàn bộ đoạn text** là một khối nguyên tử khi nhiều tiến trình/thread ghi đồng thời.
- Nếu các writer phải cùng cập nhật một tệp, hãy thiết kế cơ chế đồng bộ/ghi theo hàng đợi hoặc hệ thống lưu trữ phù hợp; không trông đợi thứ tự ghi ngẫu nhiên.
- Với log ứng dụng có nhiều thread, dùng logging framework được cấu hình thích hợp sẽ phù hợp hơn so với tự gọi `Files.writeString` nối tiếp ở nhiều chỗ.

## 9. Viết helper để sử dụng trong ứng dụng

`Files.writeString` thích hợp đặt trong một helper I/O nhỏ thay vì rải lệnh ghi tệp khắp logic nghiệp vụ.

Ví dụ method có thể đặt trong một lớp utility:

~~~java
static Path saveText(Path file, CharSequence text) throws IOException {
    Path parent = file.toAbsolutePath().getParent();
    if (parent != null) {
        Files.createDirectories(parent);
    }
    return Files.writeString(
            file,
            text,
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
            StandardOpenOption.WRITE
    );
}
~~~

Đây là **method minh họa**, không phải chương trình độc lập; cần import `Path`, `Files`, `IOException`, `StandardCharsets` và `StandardOpenOption`, đồng thời có lớp bao ngoài.

Helper này nhận `CharSequence`, tạo thư mục cha cho đường dẫn được truyền, rồi **ghi đè tệp** theo chính sách được ghi rõ trong code. Bởi vậy:

- Với tệp chứa dữ liệu quan trọng, cần quyết định chính sách ghi đè ở tầng gọi; không nên mặc định mọi tác vụ đều được phép thay nội dung.
- Nếu ứng dụng chấp nhận đường dẫn từ người dùng, phải kiểm tra quyền truy cập và phạm vi thư mục hợp lệ ở tầng nghiệp vụ; việc gọi `toAbsolutePath()` không tự làm đường dẫn “an toàn”.
- Dùng `Files.writeString` khi nội dung sẵn có trong bộ nhớ. Nếu nội dung lớn đến mức xây dựng toàn bộ `CharSequence` gây tốn RAM, chọn cách ghi theo dòng hoặc chunk.

## 10. Kiểm thử đúng cách

Khi viết test cho lệnh ghi tệp, hãy kiểm **nội dung thực tế** và **các điều kiện mở tệp**, không chỉ kiểm sự tồn tại của file.

Các trường hợp đáng kiểm:

1. **Tệp chưa có:** `writeString` mặc định tạo tệp và trả về `Path` mong muốn.
2. **Tệp có nội dung cũ:** gọi mặc định phải thay thế nội dung, không nối thêm.
3. **Append:** `CREATE, APPEND` phải giữ nội dung cũ và nối đúng chuỗi mới, gồm newline nếu người gọi cung cấp.
4. **Unicode:** ghi/đọc bằng cùng UTF-8, ví dụ tiếng Việt, các ký tự đa byte hoặc emoji; so sánh chuỗi đọc lại với chuỗi gốc.
5. **Tệp đang tồn tại với CREATE_NEW:** việc tạo mới phải thất bại; nội dung cũ không bị cố ý ghi đè.
6. **Thiếu thư mục cha:** xác nhận lỗi hoặc logic tạo thư mục theo thiết kế.
7. **Dữ liệu rỗng:** truyền `""` là hợp lệ; khi ghi đè, có thể khiến tệp có độ dài 0 byte. Đừng nhầm với `null`.
8. **Lỗi I/O:** test phải xử lý đúng ngoại lệ và dọn tài nguyên tạm ngay cả khi thất bại.

Đoạn kiểm tra ngắn sau (trong một method đã khai báo `throws IOException`) thể hiện nguyên tắc:

~~~java
Path temp = Files.createTempFile("content-check-", ".txt");
try {
    String expected = "Tiếng Việt\nJava 11";
    Files.writeString(temp, expected, StandardCharsets.UTF_8);
    String actual = Files.readString(temp, StandardCharsets.UTF_8);

    if (!expected.equals(actual)) {
        throw new AssertionError("Readback does not match");
    }
} finally {
    Files.deleteIfExists(temp);
}
~~~

Dùng `Files.createTempFile` để tránh phụ thuộc tên tệp cố định và tránh sửa file người dùng. Không chỉ assert `Files.exists(temp)`: một tệp tồn tại vẫn có thể chứa dữ liệu thiếu hoặc sai charset.

## 11. Lỗi thường gặp và cách khắc phục

| Nhầm lẫn | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “Gọi `writeString` nhiều lần sẽ nối nội dung.” | Mỗi lời gọi mặc định ghi đè nội dung trước | Dùng `CREATE, APPEND` khi cần nối |
| “Phương thức tự thêm dấu xuống dòng.” | Các dòng bị dính liền | Ghép `"\n"` hoặc `System.lineSeparator()` vào nội dung |
| “Máy Windows dùng charset Windows mặc định.” | Suy luận sai về dữ liệu byte | Overload không truyền `Charset` **luôn dùng UTF-8** |
| “`StringBuilder` phải gọi `toString()` mới ghi được.” | Thừa bước trong trường hợp đơn giản | `StringBuilder` là `CharSequence` nên có thể truyền trực tiếp |
| “`csq.length()` là số byte trong file.” | Kích thước bị tính sai với Unicode | Tính số byte UTF-8 hoặc đọc `Files.size(path)` sau khi ghi |
| “`CREATE` tự tạo mọi thư mục cấp cha.” | Gặp `NoSuchFileException` | Chủ động tạo thư mục bằng `Files.createDirectories` nếu được phép |
| “`CREATE_NEW` và `CREATE` giống nhau.” | Vô tình ghi lên tệp có sẵn hoặc lỗi tạo mới | Chọn `CREATE_NEW` nếu bắt buộc không ghi đè |
| “`writeString` ghi xong nghĩa là update file nguyên tử.” | Có thể để lại dữ liệu dở khi lỗi | Thiết kế ghi tạm và move nếu yêu cầu toàn vẹn cao |
| “Bắt hết exception rồi bỏ qua.” | Mất dữ liệu mà ứng dụng không biết | Xử lý `IOException` có ngữ cảnh và giữ nguyên thông tin lỗi |
| “Đọc bằng charset bất kỳ vẫn được.” | Sai nội dung hoặc lỗi giải mã | Ghi/đọc bằng cùng charset |
| “Dùng `Files.writeString` cho dữ liệu cực lớn.” | Tăng dùng RAM vì phải có toàn bộ chuỗi trong bộ nhớ | Viết theo dòng/chunk bằng `BufferedWriter` |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Cho `CharSequence text = new StringBuilder("A");` và tệp `a.txt` chưa tồn tại. Gọi `Files.writeString(Path.of("a.txt"), text)` sẽ tạo tệp gì, mã hóa nào?

**Đáp án:** Tạo tệp `a.txt` trong thư mục làm việc nếu có quyền; ghi ký tự `A` bằng **UTF-8**. `StringBuilder` được chấp nhận vì triển khai `CharSequence`.

**Câu 2.** Chạy `Files.writeString(path, "A");` rồi `Files.writeString(path, "B");`. Nội dung sau cùng là gì?

**Đáp án:** `B`. Không có `APPEND` thì lần ghi thứ hai thay nội dung lần đầu.

**Câu 3.** Muốn tệp có `A` và `B` trên hai dòng riêng, không được làm mất dữ liệu trước đó. Bạn cần lưu ý gì?

**Đáp án:** Sử dụng chế độ `APPEND` (thường kèm `CREATE`), tự thêm ký tự xuống dòng thích hợp giữa các phần. `APPEND` không tự tách dòng.

**Câu 4.** `Files.writeString(path, text, StandardCharsets.UTF_16)` có giống overload mặc định không?

**Đáp án:** Không. Nó dùng **UTF-16** thay vì UTF-8. Khi đọc lại phải dùng charset tương ứng, ví dụ `Files.readString(path, StandardCharsets.UTF_16)`.

**Câu 5.** Vì sao gọi `Files.writeString` không bảo đảm giữ nguyên tệp cũ nếu bị lỗi ghi đĩa?

**Đáp án:** Mặc định có thể truncate tệp trước khi ghi, và lỗi có thể xảy ra sau khi mới ghi một phần dữ liệu. Phải có cơ chế cập nhật an toàn hơn nếu nghiệp vụ yêu cầu thay thế nguyên tử hoặc phục hồi.

## 13. Checklist áp dụng vào code thực tế

- `Path` trỏ đúng vị trí, có thư mục cha và có quyền ghi.
- Dữ liệu đầu vào là `CharSequence` hợp lệ, không bị thay đổi đồng thời trong lúc ghi.
- Đã quyết định rõ **ghi đè**, **ghi nối** hay **không ghi đè tệp có sẵn**.
- Charset ghi và đọc đã thống nhất, ưu tiên **UTF-8** cho văn bản mới.
- Dấu xuống dòng được đưa vào nội dung khi cần; không kỳ vọng API thêm giúp.
- Dữ liệu đủ nhỏ để tạo một chuỗi trong bộ nhớ; nếu không, dùng writer/stream.
- `IOException` được xử lý hoặc truyền đúng tầng ứng dụng; biết rằng lỗi có thể để lại tệp ghi dở.
- Test có kiểm nội dung đọc lại và trường hợp tệp đã tồn tại.

## Tài liệu chính thức, đối chiếu Java 11 và JDK hiện đại

- [Java SE 11 — `Files` API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `writeString`, `readString`, mặc định UTF-8, `Charset` và các `OpenOption`.
- [Java SE 26 — `Files` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): đối chiếu hợp đồng `writeString` còn được hỗ trợ trong JDK hiện đại.
- [Java SE 11 — `StandardOpenOption`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/StandardOpenOption.html): ý nghĩa `CREATE`, `CREATE_NEW`, `APPEND`, `WRITE` và `TRUNCATE_EXISTING`.
- [Java SE 11 — `CharSequence`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/CharSequence.html): hợp đồng chuỗi ký tự và các triển khai.
- [Java SE 11 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như `UTF_8`, `US_ASCII` và `UTF_16`.

**Ghi nhớ:** `Files.writeString(path, csq)` **ghi một `CharSequence` dưới dạng UTF-8 và mặc định thay nội dung cũ**. Muốn nối thêm, bảo vệ tệp đã có hoặc dùng charset khác, phải chỉ định các tham số tương ứng. Những quy tắc này vẫn đúng với Java 11 và JDK hiện đại.