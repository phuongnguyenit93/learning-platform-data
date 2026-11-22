# Files.newBufferedReader và Files.newBufferedWriter trong Java

## 1. Tổng quan: đọc và ghi văn bản qua Files API

Khi xử lý tệp văn bản trong Java 17+, hai phương thức rất hữu ích của lớp `java.nio.file.Files` là:

- **`Files.newBufferedReader(Path, Charset)`**: mở tệp để **đọc văn bản**, tạo `BufferedReader` với bộ đệm ký tự.
- **`Files.newBufferedWriter(Path, Charset, OpenOption...)`**: mở/tạo tệp để **ghi văn bản**, tạo `BufferedWriter` với bộ đệm ký tự.

Chúng nối thế giới tệp (byte) với thế giới chuỗi và ký tự Java, đồng thời sử dụng `Path` của NIO.2. Khi văn bản được đọc từ ổ đĩa, dữ liệu byte phải được **giải mã** (*decode*) theo một `Charset`; khi ghi, ký tự Java được **mã hóa** (*encode*) thành byte.

~~~text
ĐỌC
File UTF-8 (byte) ─► Files.newBufferedReader(path, UTF_8)
                                 │ giải mã + bộ đệm
                                 ▼
                          BufferedReader
                         ├─ readLine() → String
                         └─ read(char[]) → khối char

GHI
String / char[] ─► BufferedWriter
                     │ write(), newLine(), flush(), close()
                     ▼ mã hóa + bộ đệm
                 File UTF-8 (byte)
                 Files.newBufferedWriter(path, UTF_8, ...)
~~~

Đây là **I/O văn bản**, không phải lựa chọn mặc định cho ảnh, file ZIP hay payload nhị phân. Nếu cần bảo toàn chính xác các byte không có ngữ nghĩa văn bản, sử dụng `Files.newInputStream`, `Files.newOutputStream` hoặc NIO byte API.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tạo `BufferedReader` / `BufferedWriter` từ `Path`, chỉ định charset rõ ràng và đóng tài nguyên đúng vòng đời.
2. Đọc từng dòng bằng `readLine()` và phân biệt EOF với dòng rỗng.
3. Đọc/ghi từng khối `char[]` bằng số ký tự thực tế, tránh lỗi ghi thừa phần buffer.
4. Hiểu `newLine()`, `flush()`, `close()` và ranh giới giữa “đã ghi vào bộ đệm” với “đã lưu bền vững”.
5. Chọn `StandardOpenOption` để tạo mới, ghi đè, nối tiếp hoặc ngăn ghi đè tệp đã tồn tại.
6. Nhận diện lỗi tệp, charset, đọc/ghi và xử lý ngoại lệ theo đúng giai đoạn.
7. Xác định khi nào nên dùng `Files.readString` / `Files.writeString`, `Files.lines` hoặc `newBufferedReader/newBufferedWriter`.

## 2. Các kiểu dữ liệu và thành phần liên quan

| API/kiểu | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `Path` | Biểu diễn đường dẫn trên một `FileSystem` | `Path.of(...)` không tự tạo hoặc mở tệp |
| `Files` | Các thao tác NIO.2 với tệp/thư mục | Nhiều thao tác ném `IOException` |
| `Charset` | Quy tắc giải mã/mã hóa giữa byte và ký tự | Chọn theo định dạng tệp, thường là UTF-8 |
| `StandardCharsets.UTF_8` | Charset UTF-8 dựng sẵn | Không phụ thuộc charset mặc định môi trường |
| `BufferedReader` | Reader có bộ đệm ký tự | `readLine()`, `read(char[])`, `lines()` |
| `BufferedWriter` | Writer có bộ đệm ký tự | `write(...)`, `newLine()`, `flush()` |
| `StandardOpenOption` | Quyết định cách mở tệp để ghi | `CREATE`, `CREATE_NEW`, `APPEND`, `TRUNCATE_EXISTING`... |
| `IOException` | Báo lỗi nhập/xuất (checked exception) | Xử lý hoặc khai báo `throws` |
| `try-with-resources` | Đóng tài nguyên tự động | Đóng cả khi thân khối ném ngoại lệ |

Ví dụ khung chương trình:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
~~~

Các import này đủ cho những thao tác đọc/ghi văn bản đơn giản. Khi dùng `StandardOpenOption`, cần import từ `java.nio.file` hoặc viết tên đầy đủ.

**Lưu ý:** `Path` là đối tượng mô tả đường dẫn, không cần gọi `close()`. Tài nguyên cần đóng là `BufferedReader` / `BufferedWriter` được mở từ tệp.

## 3. Files.newBufferedReader: mở tệp văn bản để đọc

### 3.1. Cú pháp và ý nghĩa

~~~java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);
~~~

Đây là **đoạn mã minh họa**; biến `path` có kiểu `Path`, phương thức bao ngoài phải xử lý `IOException`. `Files.newBufferedReader` mở tệp để đọc và trả `BufferedReader`. Byte trong tệp được giải mã bằng UTF-8 để chương trình thao tác trên ký tự Java.

Ở Java 17 còn có dạng:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
~~~

Dạng không truyền charset sử dụng **UTF-8** theo hợp đồng `Files.newBufferedReader(Path)`, nhưng việc truyền `StandardCharsets.UTF_8` tường minh làm ý định dễ nhìn, đặc biệt khi định dạng đầu vào có charset được quy định.

Không nhầm với `new FileReader(file)` của API truyền thống: lựa chọn charset và cách biểu đạt đường dẫn có thể khác tùy constructor, phiên bản Java và ngữ cảnh. Khi thiết kế mới, sử dụng `Path` và charset rõ ràng giúp giảm phụ thuộc môi trường.

### 3.2. Reader đọc ký tự, không đọc byte thô

Nếu tệp chứa byte UTF-8 của chữ `"Hà Nội"`, `BufferedReader` cung cấp các đơn vị `char` đã giải mã. Số byte trên đĩa có thể lớn hơn `String.length()` do chữ có dấu hoặc emoji.

`Reader.read()` trả về `int`: đơn vị `char` không âm hoặc `-1` ở EOF. `Reader.read(char[])` trả về số **đơn vị ký tự thực đọc** (hoặc `-1` ở cuối), không phải số byte trên đĩa. Vì vậy không dùng kết quả `read(char[])` để suy trực tiếp kích thước UTF-8 của tệp.

### 3.3. try-with-resources: cách sử dụng thường gặp

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý line.
    }
}
~~~

Đoạn trên là khối minh họa với `Path path` có sẵn. `BufferedReader` triển khai `Closeable`, nên `try-with-resources` gọi `close()` ở cuối khối kể cả khi xảy ra ngoại lệ. Không dùng lại `reader` sau khi đã đóng.

Đừng dựa vào garbage collector để đóng tài nguyên tệp. `Reader` có thể giữ descriptor/handle của hệ điều hành; sử dụng `try-with-resources` giúp vòng đời rõ ràng và tránh rò rỉ.

## 4. BufferedReader.readLine(): đọc theo dòng

`readLine()` trả một `String` chứa **nội dung dòng** nhưng **không bao gồm dấu kết thúc dòng**, hoặc trả `null` khi đã hết dữ liệu. Java nhận diện một dòng kết thúc bởi `\n`, `\r` hoặc `\r\n` theo hợp đồng `BufferedReader.readLine()`.

Điều này có các hệ quả:

- **Dòng trống hợp lệ** được biểu diễn bằng `""` (chuỗi rỗng).
- **Kết thúc tệp** được biểu diễn bằng `null`.
- `readLine()` **loại bỏ dấu xuống dòng**: không thể dựa riêng vào kết quả để tái tạo chính xác kiểu kết thúc dòng nguyên bản.
- Một tệp kết thúc bằng `\n` sau dòng có nội dung **không nhất thiết sinh ra một dòng rỗng mới** sau dấu kết thúc cuối cùng.

### 4.1. Ví dụ độc lập với CRLF, dòng trắng và LF

Lưu chương trình **ReadLinesDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("reader-lines-", ".txt");

        try {
            Files.writeString(path, "first\r\n\r\nlast\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                    Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                int lineNumber = 0;
                while ((line = reader.readLine()) != null) {
                    lineNumber++;
                    System.out.println(lineNumber + ":[" + line + "]");
                }
                System.out.println("Lines: " + lineNumber);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 ReadLinesDemo.java
java ReadLinesDemo
~~~

Kết quả:

~~~text
1:[first]
2:[]
3:[last]
Lines: 3
~~~

Giải thích chính xác: chuỗi nguồn có `first` + CRLF, một dòng rỗng + CRLF, và `last` + LF. `readLine()` lần lượt trả `"first"`, `""`, `"last"`, rồi `null`. Nếu viết `while ((line = reader.readLine()) != null)`, dòng rỗng vẫn được xử lý đúng. Ngược lại, `while (!line.isEmpty())` sẽ sai cả về ngữ nghĩa lẫn điều kiện EOF.

Vì tên tệp tạm được hệ thống chọn, ví dụ chỉ in nội dung đã đọc, không in đường dẫn ngẫu nhiên, nên output ổn định.

### 4.2. Không thể bảo toàn nguyên trạng xuống dòng bằng readLine/newLine

Giả sử tệp gốc chứa nhiều kiểu dấu kết thúc:

~~~text
alpha\r\nbeta\ngamma\r
~~~

Ký hiệu trên biểu diễn: `alpha` kết thúc bằng CRLF, `beta` bằng LF và `gamma` bằng CR. Nếu đọc bằng `readLine()` rồi ghi lại qua `writer.newLine()`, chương trình sẽ **thay tất cả dấu xuống dòng bằng quy tắc của môi trường đang chạy**, thay vì giữ từng kiểu cũ.

Điều này hợp lý nếu mục đích là **chuẩn hóa xuống dòng**; nhưng sẽ không đúng nếu mục tiêu là sao chép chính xác nội dung ký tự. Khi muốn bảo toàn từng `\r` và `\n`, hãy dùng `read(char[])` và `write(char[], off, count)` như phần tiếp theo.

### 4.3. Khi nào readLine không phù hợp?

`readLine()` thường thích hợp cho file log, danh sách, cấu hình văn bản dòng đơn, hoặc dữ liệu mà dấu xuống dòng chỉ phân chia bản ghi. Nó kém phù hợp khi:

- Cần giữ nguyên chính xác kiểu kết thúc dòng.
- Một bản ghi có thể trải qua nhiều dòng theo cú pháp phức tạp, ví dụ CSV có trường được trích dẫn chứa newline.
- Dòng có thể cực dài đến mức cần giới hạn bộ nhớ.
- Dữ liệu không thực sự là văn bản.

Lưu ý rằng `readLine()` có thể phải tích lũy một dòng rất dài trước khi trả về `String`. Với đầu vào không tin cậy, cần cân nhắc giới hạn độ dài dòng hoặc thiết kế parser xử lý có giới hạn bộ nhớ.

## 5. Đọc theo khối char[]: bảo toàn mọi ký tự và kiểm soát RAM

Ngoài `readLine()`, `BufferedReader` còn kế thừa `Reader.read(char[])` và `read(char[], off, len)`. Đây là phương án khi muốn chuyển văn bản theo từng khối, không phụ thuộc ranh giới dòng.

~~~java
char[] buffer = new char[4096];
int count;

while ((count = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, count);
}
~~~

Đây là đoạn minh họa có `BufferedReader reader` và `BufferedWriter writer` đã mở. `read` có thể trả số dương **nhỏ hơn** kích thước buffer; phải ghi đúng `count` đơn vị ký tự hợp lệ. Đặc biệt trong lần đọc cuối, các phần tử còn lại của mảng có thể chứa dữ liệu từ lượt trước.

Không dùng:

~~~java
while ((count = reader.read(buffer)) != -1) {
    writer.write(buffer); // Sai: có thể ghi ký tự cũ ở cuối mảng.
}
~~~

Vì `write(buffer)` ghi toàn bộ mảng, không chỉ đoạn mới đọc. Cú pháp đúng là `writer.write(buffer, 0, count)`. Hai tham số số nguyên cuối cùng có nghĩa **offset** và **length**, không phải vị trí đầu và vị trí kết thúc.

### 5.1. Đọc theo char không phải xử lý theo code point

Java `char` là một đơn vị mã UTF-16. Ký tự ngoài BMP như nhiều emoji được biểu diễn bởi một cặp surrogate (hai `char`). Một khối `char[]` có thể dừng giữa cặp đó.

Nếu chỉ sao chép tuần tự các đơn vị `char` mà không biến đổi, Reader và Writer cùng một chuỗi liên tục vẫn có thể giữ nội dung đúng. Nhưng không nên cắt riêng từng chunk, đảo chuỗi hoặc tự phân tích “mỗi char là một ký tự hiển thị” mà bỏ qua cặp surrogate. Với xử lý Unicode nâng cao, cân nhắc các API code point và giữ trạng thái giữa các khối.

### 5.2. Reader/Writer không dành cho bảo toàn byte nhị phân

Đọc UTF-8 bằng `newBufferedReader` rồi ghi UTF-8 bằng `newBufferedWriter` thực hiện giải mã/mã hóa. Với văn bản UTF-8 hợp lệ, có thể giữ nguyên nội dung Unicode. Nhưng đây **không phải cách sao chép byte bất kỳ**: byte đầu vào có thể không hợp lệ với charset, hoặc kết quả có thể phụ thuộc cách chuyển mã nếu hai charset khác nhau.

Nếu phải sao chép ảnh, archive, file đã nén hay bất kỳ payload nhị phân, dùng `Files.copy` hoặc API byte. Không tạo `String` từ dữ liệu nhị phân không có encoding văn bản.

## 6. Files.newBufferedWriter: mở tệp để ghi văn bản

### 6.1. Cú pháp cơ bản

~~~java
BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa: `Path path` có sẵn và phương thức phải xử lý `IOException`. `newBufferedWriter` tạo writer mã hóa văn bản thành byte theo charset được chọn và ghi ra tệp với bộ đệm.

Một chương trình thường dùng:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào Java!");
    writer.newLine();
    writer.write("Dòng thứ hai");
}
~~~

Đây là khối minh họa. `newLine()` ghi dấu kết thúc dòng theo nền tảng, còn `write` không tự thêm newline. `try-with-resources` bảo đảm writer được đóng khi kết thúc khối, và `close()` đưa dữ liệu còn đệm xuống đích bên dưới theo hợp đồng của lớp.

### 6.2. Mặc định khi không truyền OpenOption

Với overload nhận `OpenOption...`, nếu **không cung cấp option**, hành vi ghi mặc định tương đương:

- `StandardOpenOption.CREATE`: tạo tệp nếu nó chưa tồn tại.
- `StandardOpenOption.TRUNCATE_EXISTING`: nếu tệp đã tồn tại, **cắt ngắn nội dung cũ** trước khi ghi.
- `StandardOpenOption.WRITE`: mở để ghi.

Đây là một trong những điều quan trọng nhất cần ghi nhớ: **`Files.newBufferedWriter(path, UTF_8)` không có nghĩa “append vào cuối tệp đang có”**. Nó có thể xóa toàn bộ nội dung cũ vì mở trong chế độ truncate. Trước khi mở, hãy xác định chính sách: tạo mới duy nhất, ghi đè, hay nối thêm.

### 6.3. Chỉ định OpenOption rõ ràng

Một số lựa chọn tiêu biểu từ `StandardOpenOption`:

| Option | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `CREATE` | Tạo tệp nếu chưa có | Dự kiến cho phép tạo mới hoặc dùng tệp cũ |
| `CREATE_NEW` | Chỉ tạo tệp mới, thất bại nếu đã tồn tại | Tránh vô ý ghi đè |
| `TRUNCATE_EXISTING` | Khi mở để ghi, rút kích thước tệp đã có về 0 | Thay toàn bộ nội dung |
| `APPEND` | Ghi thêm ở cuối tệp | Log/bản ghi nối tiếp |
| `WRITE` | Mở để ghi | Thường đi cùng mode được chỉ định |
| `SYNC` hoặc `DSYNC` | Yêu cầu đồng bộ theo hợp đồng I/O/đích | Khi yêu cầu durability cao hơn, vẫn cần xem giới hạn filesystem |

Khi cung cấp options, **không tự giả định bộ ba option mặc định vẫn được thêm vào**. Hãy viết đầy đủ các điều kiện cần thiết theo mục tiêu. Một số tổ hợp không hợp lệ, chẳng hạn `APPEND` cùng `TRUNCATE_EXISTING`: hai yêu cầu trái nhau.

Ví dụ ghi nối tiếp:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    writer.write("bổ sung");
}
~~~

Đoạn minh họa yêu cầu import `java.nio.file.StandardOpenOption`. `CREATE` cho phép tạo tệp nếu chưa có; `APPEND` yêu cầu nối cuối thay vì xóa nội dung cũ. Nếu cần thêm một dòng, nhớ tự ghi `newLine()` theo vị trí mong muốn — `APPEND` **không tự chèn newline**.

Ví dụ tạo mới mà không ghi đè:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    writer.write("Dữ liệu mới");
}
~~~

Nếu tệp đã tồn tại, có thể nhận `FileAlreadyExistsException`. Không dùng mô hình `if (!Files.exists(path))` rồi mới mở để ngăn ghi đè vì có điều kiện đua (*TOCTOU*); `CREATE_NEW` là cách đặt yêu cầu tạo mới trong thao tác mở.

## 7. Ví dụ Java 17: mặc định ghi đè và chế độ APPEND

Lưu **WriteModesDemo.java**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class WriteModesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("writer-modes-", ".txt");

        try {
            try (BufferedWriter writer =
                    Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write("old");
            }

            // Không truyền option: tệp cũ bị cắt ngắn.
            try (BufferedWriter writer =
                    Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write("new");
            }

            // Thêm dữ liệu mà không xóa nội dung hiện tại.
            try (BufferedWriter writer = Files.newBufferedWriter(
                    path, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND)) {
                writer.write("+append");
            }

            System.out.println("Content: "
                    + Files.readString(path, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 WriteModesDemo.java
java WriteModesDemo
~~~

Kết quả:

~~~text
Content: new+append
~~~

Giải thích:

1. `Files.createTempFile` tạo tệp tạm thật.
2. Writer đầu ghi `old`; writer thứ hai dùng mode mặc định và **thay thế nội dung bằng `new`**.
3. Writer thứ ba dùng `CREATE, APPEND`, ghi thêm `+append` vào cuối.
4. Mỗi writer được đóng trước khi mở writer tiếp theo; chương trình không phụ thuộc việc dữ liệu còn nằm trong bộ đệm.
5. `finally` dọn tệp. Trong môi trường tệp không cho tạo/ghi/xóa, thao tác có thể ném `IOException` thay vì in output; đây là hành vi báo lỗi đúng, không phải lỗi ngôn ngữ Java.

Mã nguồn dùng ASCII trong dữ liệu để kết quả độc lập với cách hiển thị ký tự trên console. Ví dụ có thể mở rộng bằng tiếng Việt để thực hành charset.

## 8. readLine/newLine và lựa chọn chuẩn hóa dấu xuống dòng

Một cách chép tệp **theo dòng**:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    writer.write(line);
    writer.newLine();
}
~~~

Đây là đoạn minh họa với Reader/Writer đã mở. Cách viết này **thay đổi** định dạng xuống dòng nếu:

- Tệp nguồn sử dụng CRLF nhưng hệ thống đích dùng LF, hoặc ngược lại.
- Dòng cuối nguồn **không có** dấu kết thúc dòng: đoạn trên lại thêm một dấu mới.
- Nguồn có hỗn hợp CR, LF, CRLF.

Nếu mục tiêu là chuyển mọi dòng sang định dạng kết thúc dòng theo hệ điều hành hiện tại, đây có thể là quyết định hợp lệ. Còn nếu mục tiêu là sao chép nội dung ký tự **không đổi**, dùng `read(char[])` và `write(buffer, 0, count)`.

Khi định dạng đòi hỏi một kiểu newline cố định (ví dụ LF), ghi rõ:

~~~java
writer.write("\n");
~~~

Đây là đoạn minh họa; nó luôn ghi ký tự LF thay vì gọi `newLine()` theo nền tảng. Nhưng hãy xác định điều đó thuộc **quy ước định dạng của ứng dụng**, không phải hành vi mặc định “đúng cho mọi tệp”.

### 8.1. Dòng rỗng không phải kết thúc tệp

Đây là lỗi phổ biến:

~~~java
while (!(line = reader.readLine()).isEmpty()) {
    // Sai: dừng ở dòng trống, có thể NPE khi readLine() trả null.
}
~~~

Đoạn trên là ví dụ **sai**: `""` là một dòng rỗng hợp lệ, còn `null` mới là EOF. Cách đúng là:

~~~java
while ((line = reader.readLine()) != null) {
    // Dòng rỗng vẫn được xử lý.
}
~~~

Với văn bản cấu hình có dòng trống phân cách nhóm, cần phân biệt rõ hai trạng thái này.

## 9. Ví dụ Java 17: sao chép văn bản giữ nguyên ký tự và xuống dòng

Lưu **CopyTextWithBuffersDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class CopyTextWithBuffersDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("copy-text-buffers-");
        Path source = folder.resolve("source.txt");
        Path target = folder.resolve("target.txt");

        String original = "Chào\r\nJava\n😀";

        try {
            Files.writeString(source, original, StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(source, StandardCharsets.UTF_8);
                 BufferedWriter writer =
                         Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
                char[] buffer = new char[3];
                int count;

                while ((count = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, count);
                }
            }

            String restored = Files.readString(
                    target, StandardCharsets.UTF_8);
            boolean sameBytes = Arrays.equals(
                    Files.readAllBytes(source), Files.readAllBytes(target));

            System.out.println("Same text: " + original.equals(restored));
            System.out.println("Same UTF-8 bytes: " + sameBytes);
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CopyTextWithBuffersDemo.java
java CopyTextWithBuffersDemo
~~~

Kết quả khi các thao tác tệp thành công:

~~~text
Same text: true
Same UTF-8 bytes: true
~~~

Lý do ví dụ chính xác:

- Writer/Reader dùng **cùng charset UTF-8** cho văn bản hợp lệ.
- `read(char[])` nhận từng khối đơn vị UTF-16; `write(buffer, 0, count)` chuyển **đúng phần hợp lệ** cho writer.
- Chương trình không xóa, thay thế hoặc tự thêm `\r`/`\n`, nên sự pha trộn CRLF và LF trong chuỗi được giữ lại.
- Emoji ngoài BMP gồm hai `char`. Buffer ba đơn vị có thể tạo ranh giới nằm gần cặp surrogate; dù vậy, vì không biến đổi dữ liệu và writer nhìn thấy toàn bộ chuỗi ký tự tuần tự, nội dung được bảo toàn.
- `Arrays.equals` kiểm tra byte thực tế trên tệp trong demo, chứ không chỉ kiểm tra hai chuỗi sau giải mã.

**Giới hạn:** Đây là ví dụ sao chép một tệp đã biết là UTF-8 hợp lệ. Không dùng chiến lược ký tự để khẳng định bảo toàn mọi loại tệp nhị phân. Nếu cần sao chép byte tổng quát, `Files.copy(source, target)` hoặc byte stream phù hợp hơn.

## 10. Charset, mã hóa và xử lý dữ liệu lỗi

### 10.1. Charset phải thống nhất với định dạng dữ liệu

`StandardCharsets.UTF_8` là lựa chọn phổ biến, hỗ trợ Unicode. Nhưng một tệp được tạo theo charset khác (ví dụ UTF-16LE hoặc Windows-1258) cần được đọc đúng charset của nó.

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_16LE)) {
    // Đọc văn bản UTF-16LE.
}
~~~

Đây là đoạn minh họa với `Path path`. Không nên thử nhiều charset tùy tiện rồi chọn đầu ra “trông có vẻ đúng” trong hệ thống đòi tính chính xác. Hãy lấy encoding từ hợp đồng định dạng, metadata đáng tin cậy hoặc quy trình phát hiện được thiết kế rõ.

Với dữ liệu không phải UTF-8 nhưng bị đọc là UTF-8, quá trình giải mã có thể thất bại hoặc đưa ra văn bản sai. Việc thêm buffer lớn hơn không sửa được sai charset.

### 10.2. Byte không hợp lệ có thể dẫn đến MalformedInputException

Theo hợp đồng `Files.newBufferedReader`, Reader sẽ báo `IOException` khi gặp dữ liệu malformed/unmappable theo cách giải mã mà API sử dụng. Với một chuỗi byte UTF-8 không hợp lệ, có thể nhận `MalformedInputException` (một kiểu con của `CharacterCodingException`, tiếp tục kế thừa `IOException`).

Ví dụ: byte đầu `C3` trong UTF-8 cần byte tiếp theo thuộc khoảng continuation hợp lệ. Nếu sau đó lại có byte `28` (ký tự `(` trong ASCII), chuỗi byte này không hợp lệ làm mã hóa UTF-8.

### 10.3. Demo Java 17: phát hiện tệp UTF-8 không hợp lệ

Lưu **InvalidUtf8Demo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class InvalidUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("invalid-utf8-", ".txt");

        try {
            Files.write(path, new byte[]{(byte) 0xC3, (byte) 0x28});

            try (BufferedReader reader =
                    Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                while (reader.read() != -1) {
                    // Đọc để buộc quá trình giải mã.
                }
                System.out.println("Decoded successfully");
            } catch (MalformedInputException e) {
                System.out.println("Invalid UTF-8: true");
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 InvalidUtf8Demo.java
java InvalidUtf8Demo
~~~

Kết quả cho dữ liệu được tạo trong chương trình:

~~~text
Invalid UTF-8: true
~~~

Điểm quan trọng: **mở được Reader không đồng nghĩa toàn bộ nội dung tệp đã được giải mã thành công**. Lỗi ký tự có thể phát sinh trong quá trình gọi `read`. Vì vậy, báo “đọc thành công” chỉ sau khi đã xử lý toàn bộ nội dung và hoàn tất việc đóng tài nguyên theo yêu cầu.

Nếu ứng dụng cần chính sách thay thế ký tự lỗi bằng ký tự `�` thay vì báo lỗi, có thể tự tạo `CharsetDecoder` với `CodingErrorAction.REPLACE` rồi bọc qua `InputStreamReader`; không giả định `Files.newBufferedReader` có tham số bật/tắt chính sách này.

### 10.4. Lỗi khi ghi: ký tự Unicode không thể mã hóa

Với charset đầu ra không hỗ trợ một ký tự, quá trình encode có thể thất bại nếu encoder sử dụng chính sách báo lỗi. Ví dụ, nếu chọn US-ASCII nhưng dữ liệu chứa nhiều ký tự tiếng Việt, không được mặc định rằng byte đầu ra vẫn giữ nguyên nội dung. Hãy chọn charset đủ biểu diễn dữ liệu (UTF-8 thường phù hợp) hoặc định nghĩa rõ chính sách thay thế/báo lỗi.

Một vấn đề khác là surrogate chưa hoàn chỉnh: nếu dữ liệu chỉ chứa một nửa cặp surrogate (không phải chuỗi UTF-16 hợp lệ), encoder có thể báo malformed. Điều này quan trọng khi xử lý `char[]` theo khối có biến đổi, hoặc tự xây dựng chuỗi không hợp lệ.

## 11. newLine(), flush() và close(): ba hành động khác nhau

`BufferedWriter` có thể giữ ký tự trong bộ đệm RAM trước khi gửi cho lớp ghi dưới. Ba hành động cần phân biệt:

- **`newLine()`**: *ghi ký tự xuống dòng* theo quy tắc line separator của hệ thống. Nó không bảo đảm dữ liệu đã được chuyển xuống tệp.
- **`flush()`**: yêu cầu đẩy nội dung đang đệm qua writer bên dưới. `flush()` **không bảo đảm** dữ liệu đã được đồng bộ bền vững lên ổ đĩa vật lý.
- **`close()`**: kết thúc việc dùng writer; với `BufferedWriter`, nó thực hiện việc chuyển dữ liệu còn đệm và đóng tài nguyên bên dưới. Nó có thể ném `IOException`.

Ví dụ:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("A");
    writer.newLine();
    writer.write("B");
    writer.flush();
}
~~~

Đây là đoạn minh họa. `flush()` hữu ích khi một thành phần khác cần đọc nội dung đã được đẩy xuống writer bên dưới **trước khi** writer đóng, nhưng nó không thay thế `close()`. Trong các chương trình chỉ ghi rồi kết thúc, `try-with-resources` đủ để gọi `close()`, thường không cần tự flush ở mọi lần write.

### 11.1. Dữ liệu bền vững không chỉ là flush

Đừng kết luận rằng:

~~~java
writer.flush();
System.out.println("Permanently saved!");
~~~

là một chứng minh tệp đã bền vững trước mất điện. Cache hệ điều hành, filesystem và phần cứng có thể ảnh hưởng. Khi yêu cầu durability cao hơn, xem xét thiết kế đồng bộ với `FileChannel.force(...)` hoặc open options và cơ chế giao dịch/thay tệp phù hợp. Ngay cả khi đó, cần hiểu giới hạn bảo đảm của môi trường, không tự khẳng định an toàn tuyệt đối.

### 11.2. Không gọi close rồi tiếp tục write

`BufferedWriter` đóng xong không nên được sử dụng tiếp. Gọi `write` hoặc `flush` trên writer đã đóng thường ném `IOException`. Khác với một số lớp stream bộ nhớ có `close()` không tác động, writer gắn với tệp phải được coi là tài nguyên có vòng đời thật.

## 12. Lỗi mở, đọc, ghi và đóng

Hai phương thức của `Files` có thể báo lỗi tại nhiều giai đoạn:

| Giai đoạn | Ví dụ nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mở đọc | Thiếu tệp hoặc thiếu quyền đọc | `NoSuchFileException` / `AccessDeniedException` hoặc `IOException` phù hợp |
| Mở ghi | Thư mục cha không tồn tại, thiếu quyền, chế độ `CREATE_NEW` gặp tệp đã có | Kiểm tra mode, quyền, thư mục; bắt ngoại lệ đúng API |
| Đọc | Lỗi thiết bị, dữ liệu không hợp lệ theo charset | Không biến lỗi thành EOF hợp lệ; báo thất bại |
| Ghi | Hết dung lượng, thiết bị lỗi, dữ liệu không mã hóa được | Không mặc định có thể thử ghi lại toàn bộ mà không ghi trùng |
| Flush | Lỗi khi chuyển dữ liệu đã đệm xuống tầng dưới | Xử lý tương đương lỗi ghi, không bỏ qua |
| Close | Lỗi khi chuyển nốt buffer/đóng handle | Giữ lỗi và tránh coi kết quả là thành công chắc chắn |

Một API mới không bảo đảm môi trường hoàn hảo. `Path`, `Files`, `BufferedReader` và `BufferedWriter` vẫn dựa trên tài nguyên hệ thống tệp khi xử lý file thực.

### 12.1. Catch đúng chỗ

Có thể để một phương thức đọc/ghi khai báo `throws IOException` và để tầng cao hơn quyết định thông báo người dùng, retry hay từ chối yêu cầu. Ví dụ:

~~~java
static void appendLine(Path path, String line) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            path, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
        writer.write(line);
        writer.newLine();
    }
}
~~~

Đây là **đoạn phương thức độc lập về cú pháp nhưng cần đặt trong lớp** và thêm import `BufferedWriter`, `IOException`, `Path`, `Files`, `StandardCharsets`, `StandardOpenOption`. Nó chủ động đóng writer do chính mình tạo.

Nếu append thất bại giữa chừng, không được tự động retry toàn bộ bản ghi mà không biết đã ghi được bao nhiêu byte/ký tự. Một số hệ thống cần giao thức có transaction, khóa hoặc idempotency để tránh bản ghi trùng/dở dang.

### 12.2. try-with-resources giữ suppressed exception

Nếu lỗi xảy ra trong thân `try` và tiếp tục có lỗi khi `close()`, `try-with-resources` giữ lỗi trong thân là ngoại lệ chính, còn lỗi đóng được gắn bằng `Throwable.getSuppressed()`. Điều này giúp không mất thông tin chẩn đoán.

Không viết `catch(IOException e) { return ""; }` cho một thao tác đọc bắt buộc: chuỗi rỗng có thể là nội dung tệp hợp lệ, còn lỗi I/O là một trạng thái khác. Nên ném tiếp, trả kiểu kết quả có trạng thái lỗi, hoặc xử lý cụ thể theo hợp đồng nghiệp vụ.

## 13. Sự khác biệt giữa Files.readString, readAllLines, lines và newBufferedReader

Khi chỉ cần đọc văn bản, không phải lúc nào cũng cần tự mở `BufferedReader`. Chọn API theo lượng dữ liệu và cách xử lý.

| API | Kết quả | Đặc tính |
| --- | --- | --- |
| `Files.readString(path, charset)` | Một `String` chứa toàn bộ tệp | Thuận tiện cho tệp nhỏ; phải giữ cả nội dung trong RAM |
| `Files.readAllLines(path, charset)` | `List<String>` của các dòng | Tiện cho tệp nhỏ/vừa; giữ toàn bộ dòng trong RAM |
| `Files.lines(path, charset)` | `Stream<String>` đọc dòng một cách lazy | Cần **đóng Stream** vì nó giữ tài nguyên I/O |
| `Files.newBufferedReader(path, charset)` | `BufferedReader` | Linh hoạt: readLine, read(char[]), mark/reset nếu phù hợp |

`Files.readAllLines` trả danh sách dòng đã đọc và cũng loại bỏ dấu kết thúc dòng tương tự quy tắc đọc dòng. `Files.lines` cho phép xử lý dòng dưới dạng Stream, nhưng vẫn là tài nguyên cần đóng:

~~~java
try (java.util.stream.Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(s -> !s.isBlank()).forEach(System.out::println);
}
~~~

Đây là đoạn minh họa với `Path path`; Stream đóng sẽ đóng tài nguyên do `Files.lines` mở.

Ngược lại, `BufferedReader.lines()` trả một Stream lấy các dòng từ **BufferedReader đang có**. Đóng Stream đó không thay thế trách nhiệm đóng Reader bên ngoài. Cách quản lý rõ ràng:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines().forEach(System.out::println);
}
~~~

Đây là đoạn minh họa: Reader vẫn được đóng bằng `try-with-resources`. Không nên vừa đọc thủ công `reader.readLine()` vừa vận hành Stream `reader.lines()` song song trên cùng Reader; đó là một nguồn tiêu thụ tuần tự có trạng thái.

## 14. So sánh Files.writeString và newBufferedWriter

`Files.writeString(path, text, charset, options...)` là phương án ngắn khi đã có toàn bộ `String`. Nó mở, ghi và đóng tài nguyên theo hợp đồng của lời gọi. Ví dụ:

~~~java
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa với `Path path` có sẵn. `newBufferedWriter` hữu ích hơn nếu phải ghi nhiều lần, xử lý dòng từng bước, stream đầu vào dài hoặc tạo nội dung dần mà không giữ toàn bộ thành một String.

Không có quy tắc “luôn dùng BufferedWriter nhanh hơn”: hiệu năng tùy số lần write, kích thước dữ liệu, lớp đệm và filesystem. Đối với tệp rất nhỏ và đã có sẵn String, `Files.writeString` có thể rõ ràng hơn. Đối với quá trình ghi lặp nhiều mảnh, `BufferedWriter` tránh mở lại tệp cho mỗi mảnh và cung cấp API quản lý writer xuyên suốt tác vụ.

### 14.1. Không mở writer mới cho từng dòng với mode mặc định

Cách sai:

~~~java
for (String line : lines) {
    try (BufferedWriter writer =
            Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
        writer.write(line);
    }
}
~~~

Đây là đoạn minh họa sai về logic; `lines` và `path` có sẵn. Vì mỗi lần mở mặc định **cắt ngắn tệp**, kết quả thường chỉ còn dòng cuối. Ngoài ra, việc mở/đóng cho mỗi dòng làm tăng overhead.

Cách phù hợp nếu muốn ghi nhiều dòng liên tiếp:

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    for (String line : lines) {
        writer.write(line);
        writer.newLine();
    }
}
~~~

Đây là đoạn minh họa với `Iterable<String> lines` được xác định. Writer được mở một lần rồi đóng sau cùng; tệp bị thay toàn bộ có chủ đích. Nếu muốn append vào tệp cũ, thêm các open options thích hợp.

## 15. Mở nhiều tài nguyên và thứ tự đóng

Một thao tác chuyển dữ liệu từ tệp nguồn sang tệp đích có thể mở cả Reader và Writer:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(source, StandardCharsets.UTF_8);
     BufferedWriter writer =
             Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
    char[] buffer = new char[8192];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        writer.write(buffer, 0, count);
    }
}
~~~

Đây là đoạn minh họa với `Path source` và `Path target`. Tài nguyên được đóng theo **thứ tự ngược với khai báo**: writer trước, reader sau.

Không nên đặt source và target thành **cùng đường dẫn** trong ví dụ ghi đè: khi writer mở ở chế độ mặc định, tệp đích (cũng là nguồn) có thể bị cắt ngắn, làm mất dữ liệu đang cần đọc. Nếu muốn biến đổi tệp tại chỗ, cân nhắc ghi ra **tệp tạm khác**, đóng đầy đủ, kiểm tra kết quả rồi chuyển tệp tạm sang đích theo chính sách phù hợp.

### 15.1. Nếu một bên mở thất bại

`try-with-resources` cũng có lợi khi mở nhiều tài nguyên: nếu Reader mở thành công nhưng mở Writer ném ngoại lệ, Reader đã mở sẽ được đóng trong quá trình thoát. Cách này hạn chế rò rỉ handle so với việc tự gán biến và quản lý đóng thủ công.

### 15.2. Không tự đóng tài nguyên của bên khác

Nếu một phương thức **nhận** `BufferedReader` hoặc `BufferedWriter` từ caller, nó thường không nên tự đóng nếu hợp đồng không trao quyền sở hữu. Ngược lại, khi phương thức tự gọi `Files.newBufferedReader` / `newBufferedWriter` để mở tệp phục vụ chính tác vụ đó, phương thức có trách nhiệm đóng tài nguyên khi xong.

## 16. Chọn dung lượng buffer và chú ý hiệu năng

`BufferedReader` / `BufferedWriter` có bộ đệm ký tự nội bộ. Khi sử dụng `Files.newBufferedReader` / `newBufferedWriter`, kích thước bộ đệm được chọn theo cách triển khai của API; không nên phụ thuộc một con số cụ thể để dự đoán hành vi.

Nếu ứng dụng cần buffer `char[]` của riêng mình để sao chép theo khối, có thể dùng `new char[4096]` hoặc `new char[8192]` làm kích thước thử nghiệm. Không có con số tối ưu cho mọi workload. Kích thước nhỏ hơn vẫn cho kết quả chính xác nếu sử dụng `count`; kích thước lớn hơn có thể giảm số lần gọi nhưng tăng một lượng bộ nhớ nhất định.

**Những vấn đề quan trọng hơn vài kilobyte buffer:**

- Không mở/đóng tệp lại cho từng token/dòng khi có thể xử lý liên tục.
- Không tích lũy tệp rất lớn thành một `String` khi chỉ cần quét tuần tự.
- Không dùng `readLine` với dòng có thể dài vô hạn mà không có chính sách giới hạn dữ liệu.
- Không flush ở mỗi ký tự nếu không có yêu cầu hiển thị/đồng bộ tương ứng.
- Phân biệt chất lượng xử lý lỗi, charset và dữ liệu với tối ưu tốc độ.

## 17. Các lỗi phổ biến với newBufferedReader/newBufferedWriter

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Không chọn charset phù hợp | Văn bản có dấu sai hoặc lỗi giải mã | Chỉ định charset theo định dạng |
| Tưởng Writer mặc định append | Nội dung cũ bị xóa | Dùng `CREATE, APPEND` khi muốn nối |
| Mở Writer mới cho từng dòng mà không đặt APPEND | Chỉ giữ dòng cuối | Mở một Writer cho toàn bộ tác vụ |
| Dùng `readLine() == ""` để xét EOF | Bỏ dòng trống hoặc NPE khi null | Chỉ `null` mới là EOF |
| Dùng `readLine()+newLine()` để copy nguyên trạng | Chuẩn hóa/mất kiểu dấu xuống dòng gốc | Dùng `read(char[])` + `write(...,count)` |
| Ghi toàn bộ buffer sau lần đọc ngắn | Chèn ký tự cũ ở cuối mảng | Dùng `writer.write(buffer,0,count)` |
| Dùng Reader/Writer cho dữ liệu nhị phân | Byte có thể bị chuyển mã và hỏng | Sử dụng byte stream/NIO |
| Không đóng Writer | Dữ liệu còn đệm có thể chưa tới đích; rò rỉ handle | `try-with-resources` |
| Tưởng `flush()` đồng nghĩa fsync | Đánh giá sai tính bền vững | Phân biệt flush/close/force |
| Đọc tệp rất lớn bằng readString | Có thể thiếu heap | Xử lý theo dòng hoặc khối |
| Đọc và ghi cùng đường dẫn bằng writer mặc định | Cắt ngắn nguồn đang đọc | Tệp tạm hoặc thiết kế in-place an toàn |
| Bỏ qua IOException từ close | Có thể mất tín hiệu ghi lỗi cuối | Để lỗi truyền lên hoặc xử lý đúng |
| Tưởng đường dẫn luôn tồn tại khi gọi `Path.of` | Mở đọc thất bại | Bắt ngoại lệ khi mở thực |
| Kết luận readLine đã giữ nguyên CRLF | Mất thông tin dấu dòng | Xử lý trực tiếp ký tự nếu cần |
| Dùng charset mặc định không nhất quán ở nhiều tầng | Tệp đọc/ghi khác nội dung | Chọn charset tường minh xuyên suốt |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `Files.newBufferedWriter(path, UTF_8)` mở một tệp đã có nội dung. Nội dung cũ có được giữ lại không?

**Đáp án:** mặc định không. Khi không truyền open option, writer dùng chế độ tương đương `CREATE`, `TRUNCATE_EXISTING`, `WRITE`: tệp hiện hữu bị cắt ngắn. Muốn nối thêm, chỉ định `CREATE` và `APPEND` phù hợp.

**Câu 2.** `readLine()` trả `""` thì đã EOF chưa?

**Đáp án:** chưa. Đó là một dòng rỗng. `null` mới là dấu hiệu hết dữ liệu.

**Câu 3.** Đọc bằng `readLine` rồi ghi bằng `newLine` có bảo toàn CRLF của tệp nguồn trên mọi hệ điều hành không?

**Đáp án:** không. `readLine` loại bỏ dấu kết thúc dòng, `newLine` tạo dấu kết thúc phù hợp môi trường đích. Muốn giữ nguyên chuỗi ký tự xuống dòng, dùng `read(char[])`/`write(char[],0,count)`.

**Câu 4.** Khi `reader.read(buffer)` trả 5 và mảng dài 1024, nên ghi bao nhiêu ký tự?

**Đáp án:** 5, bằng `writer.write(buffer, 0, 5)`; không ghi cả mảng.

**Câu 5.** `flush()` có bảo đảm byte đã được lưu bền vững trên thiết bị vật lý không?

**Đáp án:** không. Flush đẩy dữ liệu qua tầng bộ đệm mà writer quản lý; yêu cầu durability khác với việc xả buffer.

**Câu 6.** Vì sao không mở `newBufferedWriter(sourcePath, UTF_8)` cùng lúc để “sửa tại chỗ” một tệp đang được Reader đọc?

**Đáp án:** mặc định Writer có thể cắt ngắn chính tệp nguồn; dữ liệu gốc bị mất trước khi đọc xong. Nên dùng tệp tạm và quy trình thay thế an toàn.

**Câu 7.** `Files.lines` và `BufferedReader.lines` có cùng trách nhiệm đóng tài nguyên không?

**Đáp án:** với `Files.lines`, đóng Stream để đóng tài nguyên do phương thức mở. Với `BufferedReader.lines`, vẫn phải quản lý/đóng BufferedReader gốc; không cho rằng đóng Stream tự đóng Reader.

**Câu 8.** Vì sao Writer đọc/ghi UTF-8 có thể ném IOException sau khi mở thành công?

**Đáp án:** lỗi có thể xuất hiện ở ghi xuống hệ thống tệp, flush/close, hoặc chuyển mã ký tự không hợp lệ theo charset; mở thành công không bảo đảm các thao tác tiếp theo thành công.

### Bài tập thực hành

1. **Đọc dòng rỗng:** sửa `ReadLinesDemo` với nguồn `"A\n\nB"`; dự đoán số dòng và giá trị từng dòng. Kiểm tra rằng không đánh đồng dòng rỗng với EOF.
2. **Append:** sửa `WriteModesDemo` để ghi thêm `"+1"` và `"+2"` bằng một `BufferedWriter` duy nhất. So sánh kết quả với việc mở writer mới mỗi lần.
3. **Ghi đè an toàn:** thử `CREATE_NEW` khi tệp đã tồn tại và bắt `FileAlreadyExistsException`. Không xóa tệp chỉ để làm bài kiểm thử này thành công.
4. **Charset:** ghi một văn bản tiếng Việt bằng UTF-8 rồi đọc lại. Thử dùng charset khác trong môi trường thử nghiệm để quan sát lý do phải biết encoding nguồn; không đưa kết quả chuyển mã sai vào sản phẩm.
5. **Giữ xuống dòng:** dùng văn bản chứa CRLF, LF và CR, sao chép bằng hai chiến lược (theo dòng và theo khối ký tự), sau đó so sánh bằng `Arrays.equals(Files.readAllBytes(a), Files.readAllBytes(b))` để thấy sự khác biệt.
6. **Tệp lớn:** thiết kế hàm nhận `Path source` và `Path target`, copy văn bản bằng buffer `char[]`, không giữ toàn bộ tệp trong RAM, và bảo đảm đóng cả Reader lẫn Writer khi có ngoại lệ.

## 19. Tổng kết

- **`Files.newBufferedReader(path, charset)`** mở tệp cho việc đọc văn bản đã giải mã; có thể dùng `readLine()` hoặc đọc từng khối ký tự.
- **`Files.newBufferedWriter(path, charset, options...)`** tạo Writer có bộ đệm để ghi văn bản; **mode mặc định có thể xóa nội dung tệp hiện có**.
- **`readLine()` loại bỏ dấu kết thúc dòng**, trả `null` ở EOF và trả `""` cho dòng trống. `newLine()` ghi dấu xuống dòng theo nền tảng.
- **`read(char[])` và `write(buffer,0,count)`** phù hợp khi cần giữ nguyên chuỗi ký tự và xử lý tệp lớn theo từng phần.
- **UTF-8 là charset nên nêu rõ** khi định dạng tệp dùng UTF-8; charset sai hoặc dữ liệu malformed có thể gây lỗi đọc/ghi.
- **`try-with-resources` quản lý close**, giúp tránh rò rỉ tệp và giữ lỗi đóng; `flush` không phải lời hứa lưu dữ liệu bền vững trên thiết bị.
- **Chọn API theo mục tiêu**: `readString/writeString` cho dữ liệu nhỏ, `Files.lines` cho stream dòng, và `newBufferedReader/newBufferedWriter` khi cần điều khiển quá trình đọc/ghi.

### Tài liệu Java SE 17

- [Files.newBufferedReader(Path, Charset)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset))
- [Files.newBufferedWriter(Path, Charset, OpenOption...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...))
- [BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Files.readString, writeString và lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
