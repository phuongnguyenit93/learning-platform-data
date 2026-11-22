# DirectoryStream và đóng handle thư mục trong Java NIO.2

## 1. Vì sao cần DirectoryStream?

Một thư mục trên hệ thống tệp có thể chứa vài tệp, hàng nghìn phần tử, hoặc một tập hợp thay đổi liên tục khi chương trình đang chạy. Khi cần **duyệt các phần tử trực tiếp bên trong một thư mục**, Java NIO.2 cung cấp `java.nio.file.DirectoryStream<Path>` và phương thức tạo phổ biến nhất:

~~~java
DirectoryStream<Path> stream = Files.newDirectoryStream(directory);
~~~

`DirectoryStream` là một **`Iterable` các đường dẫn `Path`** đến các phần tử được phát hiện trong thư mục. Khác với việc chỉ giữ một danh sách tên trong RAM, nó có thể được triển khai dựa trên tài nguyên duyệt thư mục của hệ điều hành và vì thế **phải được đóng**.

Điều quan trọng nhất của bài này: **`DirectoryStream` là tài nguyên có vòng đời, không chỉ là một tập hợp có thể bỏ mặc cho GC**. Hãy mở nó trong `try-with-resources`, duyệt khi nó còn mở, rồi đóng ngay sau khi hoàn tất hoặc khi có ngoại lệ.

~~~text
           Path thư mục
                │
                ▼
    Files.newDirectoryStream(dir)
                │
                ▼
    DirectoryStream<Path> (OPEN)
       │         │        │
       ▼         ▼        ▼
   file.txt    logs/    image.png
       │         │        │
       └────── duyệt ─────┘
                │
                ▼
       close() qua try-with-resources
                │
                ▼
       Handle thư mục được giải phóng
~~~

Bài học giúp bạn:

- Mở `DirectoryStream` để liệt kê các phần tử **cấp trực tiếp**.
- Hiểu khác biệt giữa `Path` đại diện thư mục, `DirectoryStream` có handle thật và `Stream<Path>` của Java Streams.
- Duyệt bằng vòng `for-each` đúng cách, tránh dùng iterator nhiều lần hoặc tự giả định thứ tự.
- Lọc theo **glob** và `DirectoryStream.Filter<Path>`.
- Xử lý lỗi khi **mở**, **duyệt**, **lọc** và **đóng** thư mục.
- Duyệt thư mục lồng nhau mà không rò rỉ handle.
- Chọn `DirectoryStream`, `Files.list`, `Files.walk` hay `Files.walkFileTree` tùy tình huống.
- Nhận biết rủi ro symbolic link, thay đổi đồng thời, đường dẫn không tin cậy và vòng đời tài nguyên.

## 2. Các API và kiểu dữ liệu cốt lõi

| Thành phần | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `Path` | Mô tả đường dẫn | Tạo `Path` chưa mở thư mục |
| `Files.newDirectoryStream(dir)` | Mở nguồn duyệt các entry trực tiếp của thư mục | Có thể ném `IOException` ngay khi mở |
| `DirectoryStream<Path>` | `Iterable<Path>` đồng thời là `Closeable` | Phải đóng khi xong |
| `DirectoryStream.Filter<Path>` | Điều kiện nhận/bỏ một entry | Có thể ném `IOException` |
| `Files.newDirectoryStream(dir, "*.txt")` | Chỉ lấy entry có tên khớp glob | Glob khác cú pháp regex |
| `DirectoryIteratorException` | Báo lỗi I/O phát sinh **trong lúc duyệt** | Unchecked; truy xuất nguyên nhân bằng `getCause()` |
| `Files.isDirectory(path)` | Kiểm tra đường dẫn đại diện cho thư mục | Hành vi với symbolic link phụ thuộc `LinkOption` |
| `Files.list(dir)` | Trả `Stream<Path>` các entry trực tiếp | `Stream` này cũng cần đóng |
| `Files.walk(root)` | Tạo `Stream<Path>` duyệt sâu hơn | Cần đóng, tránh dùng vô giới hạn |
| `Files.walkFileTree(...)` | Duyệt cây với các callback có kiểm soát | Hữu ích cho đệ quy, lỗi và quyền truy cập |

**`DirectoryStream` không phải `java.util.stream.Stream`.** Nó triển khai `Iterable` và `Closeable`, nên dùng thuận tiện qua vòng `for (Path entry : stream)` nhưng không trực tiếp có các thao tác `map/filter/collect` của Java Streams. Nếu muốn API Stream, `Files.list` là lựa chọn riêng và cũng mang trách nhiệm đóng tài nguyên.

## 3. Mở, duyệt, đóng: mô hình chuẩn

Một hàm đúng cấu trúc:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(directory)) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

Đây là đoạn mã minh họa, chưa phải chương trình độc lập; `directory` là `Path` hợp lệ, phương thức bao ngoài khai báo hoặc bắt `IOException`. Những import cần thiết:

~~~java
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
~~~

Diễn biến của câu lệnh:

1. `Files.newDirectoryStream(directory)` yêu cầu provider mở việc duyệt thư mục.
2. Nếu mở thành công, `entries` đại diện cho một stream có thể sử dụng.
3. `for-each` lấy lần lượt các `Path` con và xử lý chúng.
4. Khi rời khối `try`, Java tự gọi `entries.close()`, kể cả khi trong thân khối có ngoại lệ.
5. Khi tài nguyên đóng, không tiếp tục dùng `DirectoryStream` cũ để duyệt thêm.

Việc tạo `Path.of("folder")` chỉ tạo một đường dẫn trừu tượng. **Không có handle thư mục cần đóng ở bước tạo Path**. Handle có thể xuất hiện khi gọi `Files.newDirectoryStream`, `Files.list`, mở `DirectoryStream` khác hoặc các API I/O thực sự truy cập hệ thống tệp.

### 3.1. Lỗi không đóng stream là gì?

Nếu mở nhiều `DirectoryStream` nhưng quên `close()`, tiến trình có thể giữ các directory handle/file descriptor lâu hơn cần thiết. Hệ quả tùy OS và provider:

- Tăng số handle đang mở, đến ngưỡng không mở thêm được.
- Gây khó khăn cho việc xóa, đổi tên hoặc thay thế một số thư mục trên hệ điều hành có cơ chế khóa.
- Tăng mức sử dụng tài nguyên không cần thiết, đặc biệt khi server xử lý nhiều request.
- Khi có ngoại lệ giữa lúc duyệt, tài nguyên bị bỏ lại nếu chỉ đóng trên nhánh thành công.

Garbage collector **không phải chiến lược vòng đời đáng tin** cho loại tài nguyên này. `try-with-resources` diễn đạt thời điểm giải phóng rõ ràng và an toàn hơn.

## 4. Ví dụ Java 17 đầy đủ: duyệt một thư mục tạm

Để ví dụ chạy được trên nhiều máy mà không phụ thuộc tệp người dùng, chương trình tự tạo thư mục tạm, ba entry và xóa chúng sau khi thử nghiệm. Vì thứ tự liệt kê **không được bảo đảm**, chương trình gom **tên** rồi sắp xếp trước khi in.

Lưu thành **DirectoryStreamBasicsDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamBasicsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("dir-stream-basics-");
        Path alpha = dir.resolve("alpha.txt");
        Path beta = dir.resolve("beta.log");
        Path subdir = dir.resolve("subdir");

        try {
            Files.writeString(alpha, "A", StandardCharsets.UTF_8);
            Files.writeString(beta, "B", StandardCharsets.UTF_8);
            Files.createDirectory(subdir);

            List<String> names = new ArrayList<>();

            try (DirectoryStream<Path> entries =
                         Files.newDirectoryStream(dir)) {
                for (Path entry : entries) {
                    names.add(entry.getFileName().toString());
                }
            }

            Collections.sort(names);
            System.out.println(names);
        } finally {
            Files.deleteIfExists(alpha);
            Files.deleteIfExists(beta);
            Files.deleteIfExists(subdir);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 DirectoryStreamBasicsDemo.java
java DirectoryStreamBasicsDemo
~~~

Kết quả khi filesystem cho phép tạo/duyệt/xóa thư mục tạm:

~~~text
[alpha.txt, beta.log, subdir]
~~~

**Giải thích:**

- `Files.createTempDirectory` tạo thư mục thật với tên ngẫu nhiên; chương trình không in tên đó để stdout ổn định.
- `Files.writeString` và `Files.createDirectory` tạo entry có tên xác định.
- `Files.newDirectoryStream(dir)` duyệt **ba phần tử trực tiếp** của thư mục; nó không đi vào `subdir`.
- `entry.getFileName()` lấy thành phần cuối của đường dẫn để in tên.
- `Collections.sort(names)` làm thứ tự in có thể dự đoán. Bản thân `DirectoryStream` **không hứa thứ tự alphabet**, theo thời gian tạo hay theo thứ tự lưu vật lý.
- `try-with-resources` đóng `DirectoryStream` trước khi `finally` xóa thư mục và tệp. Đây là chi tiết quan trọng trên các nền tảng có kiểm soát handle nghiêm ngặt.

Trong ứng dụng thực, lỗi cleanup cũng có thể ném `IOException` và cần được báo đúng; đây là demo ngắn phục vụ học tập.

## 5. DirectoryStream chỉ duyệt con trực tiếp, không tự đệ quy

Ví dụ cấu trúc:

~~~text
project/
├─ pom.xml
├─ README.md
└─ src/
   ├─ Main.java
   └─ test/
      └─ ExampleTest.java
~~~

`Files.newDirectoryStream(project)` thông thường chỉ đưa về các entry `pom.xml`, `README.md` và `src`. Nó **không tự đi xuống `src/Main.java`** hay `src/test/ExampleTest.java`.

Nếu cần duyệt cấp sâu hơn, bạn phải mở thêm stream cho thư mục con, hoặc dùng API được thiết kế duyệt cây như `Files.walkFileTree`. Việc dùng `DirectoryStream` lồng nhau cần chú ý **mỗi stream có handle riêng**.

### 5.1. Kiểm tra file/thư mục khi duyệt

Bạn có thể xem loại entry:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        if (Files.isDirectory(entry)) {
            // Thư mục theo quy tắc kiểm tra hiện tại.
        } else if (Files.isRegularFile(entry)) {
            // Tệp thường.
        } else {
            // Có thể là symbolic link, entry đặc biệt hoặc không xác định.
        }
    }
}
~~~

Đây là đoạn minh họa với `Path dir` có sẵn. Mặc định `Files.isDirectory` và `Files.isRegularFile` có thể **theo symbolic link**. Nếu cần phân loại bản thân symbolic link hoặc tránh đi theo nó khi đệ quy, cân nhắc `LinkOption.NOFOLLOW_LINKS`. Ngoài ra, `false` không luôn có nghĩa “chắc chắn không thuộc kiểu này”: có thể không truy vấn được do điều kiện hệ thống tệp.

`DirectoryStream` trả các `Path`; không bảo đảm entry vẫn tồn tại hoặc cùng loại khi bạn thực sự mở nó sau đó. Đây là tính chất của filesystem có thể thay đổi đồng thời.

## 6. DirectoryStream là một tài nguyên: thời điểm close() quan trọng

`DirectoryStream<Path>` kế thừa `Closeable`, vì vậy có `close()`. Sau khi đóng, không nên tiếp tục gọi iterator hoặc lặp qua nó. `close()` giải phóng tài nguyên duyệt thư mục của provider; bản thân các `Path` đã lấy ra vẫn là **đối tượng biểu diễn đường dẫn**, không có nghĩa chúng trở nên vô hiệu về mặt kiểu.

Một cấu trúc đúng:

~~~java
List<Path> paths = new ArrayList<>();

try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        paths.add(entry);
    }
}

// Tới đây DirectoryStream đã đóng.
// Đường dẫn vẫn có thể được dùng, nhưng tệp có thể đã thay đổi.
for (Path path : paths) {
    System.out.println(path.getFileName());
}
~~~

Đoạn mã minh họa, cần import `List`/`ArrayList` và API NIO; không phải chương trình độc lập. Nó **tích lũy mọi `Path` vào RAM**, phù hợp cho thư mục nhỏ khi phải dùng kết quả sau khi đóng. Nếu thư mục rất lớn, nên xử lý từng entry ngay trong khối `try` thay vì gom tất cả.

### 6.1. Không trả về iterator phụ thuộc stream đã đóng

Anti-pattern:

~~~java
static Iterator<Path> badIterator(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        return entries.iterator(); // Sai: stream đóng khi return.
    }
}
~~~

Đây là đoạn phương thức minh họa (cần import `java.util.Iterator`). Iterator còn tham chiếu tới nguồn mà phương thức đã đóng; người gọi không thể dựa vào nó để duyệt tiếp.

Thiết kế tốt hơn thường là:

- **Xử lý hoàn tất trong phạm vi `try`** và trả về kết quả nghiệp vụ nhỏ (count, summary...).
- **Trả một danh sách bản sao các Path** nếu số entry nhỏ và đã hoàn tất việc duyệt.
- **Để caller sở hữu DirectoryStream** nếu hợp đồng API công khai yêu cầu caller đóng và quản lý vòng đời.
- Nếu muốn lazy Stream API, cân nhắc `Files.list` nhưng vẫn quy định ai đóng Stream.

Không nên trả một `Stream<Path>` từ `Files.list` mà quên nói rõ trách nhiệm đóng ở caller.

### 6.2. Giao quyền sở hữu một cách tường minh

Nếu hàm tự mở stream, nó thường phải đóng:

~~~java
static long countEntries(Path dir) throws IOException {
    long count = 0;
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        for (Path ignored : entries) {
            count++;
        }
    }
    return count;
}
~~~

Đây là đoạn phương thức minh họa, cần import `IOException`, `DirectoryStream`, `Files`, `Path`. Nó trả số lượng entry đã duyệt thành công; nếu duyệt lỗi, nó không trả một số đếm nửa chừng như kết quả hoàn chỉnh.

Nếu một hàm **nhận** `DirectoryStream` do caller mở, đừng tự đóng nó trừ khi hợp đồng chuyển quyền sở hữu rõ ràng. Tài nguyên có thể vẫn cần được dùng tại nơi gọi.

## 7. Iterator của DirectoryStream: chỉ một iterator và không có thứ tự bảo đảm

`DirectoryStream` là `Iterable<Path>`, nhưng khác nhiều collection thông thường: hợp đồng của nó **chỉ hỗ trợ tạo tối đa một `Iterator`** cho một stream. Nếu yêu cầu iterator lần thứ hai, nó có thể ném `IllegalStateException`.

Vì vậy, không dùng các mẫu dựa trên khả năng lặp lại nhiều lần:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        // Lượt duyệt thứ nhất.
    }
    for (Path entry : entries) {
        // Sai: yêu cầu iterator thứ hai trên cùng DirectoryStream.
    }
}
~~~

Đây là ví dụ về **cách làm sai**, không phải chương trình nên chạy như một demo thành công.

Nếu phải duyệt lại:

- Mở **một DirectoryStream mới** bằng `Files.newDirectoryStream(dir)`.
- Hoặc tích lũy các entry cần dùng vào danh sách trong lượt đầu, chấp nhận dùng RAM.
- Nếu thư mục có thể thay đổi, hiểu rằng lần mở mới có thể cho tập phần tử khác.

Thứ tự nhận các phần tử không được bảo đảm. Không giả định tên tệp sẽ được trả theo alphabet, thứ tự tạo, thứ tự chỉnh sửa hay thứ tự duyệt của command-line. Nếu cần thứ tự để hiển thị hoặc tính toán, hãy sắp xếp có chủ đích và chú ý chi phí bộ nhớ.

### 7.1. Duyệt có thể lazy và yếu nhất quán

Hệ thống tệp có thể bị tiến trình khác thay đổi **trong khi** bạn đang duyệt: thêm tệp, xóa tệp, đổi tên thư mục con. Một iterator dạng này không cung cấp snapshot giao dịch. Nó có thể phản ánh một số thay đổi hoặc không phản ánh, tùy provider và thời điểm.

Không suy ra từ việc đã thấy `entry` rằng:

- Entry chắc chắn còn tồn tại khi gọi `Files.readString(entry)`.
- Entry vẫn là tệp thường sau `Files.isRegularFile(entry)`.
- Tập entry nhận được là ảnh chụp nhất quán toàn bộ thư mục.
- Vòng duyệt đã tự khóa thư mục khỏi các thay đổi khác.

Trong các hệ thống cần bảo toàn tính nhất quán, cần thiết kế cơ chế snapshot/giao dịch/khóa/kiểm tra khác phù hợp môi trường; `DirectoryStream` một mình không cung cấp các bảo đảm đó.

## 8. Lọc theo glob với Files.newDirectoryStream(Path, String)

Để chỉ duyệt những entry có **tên phù hợp một glob**, dùng overload:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, "*.txt")) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

Đây là đoạn minh họa. Mẫu `"*.txt"` được áp dụng theo quy tắc **glob filename** của `Files.newDirectoryStream(dir, glob)`, không phải mẫu regex Java tùy ý.

Điểm cần biết:

- Glob `*` thường khớp một chuỗi ký tự trong tên.
- Glob `?` khớp một ký tự trong tên theo quy tắc glob.
- `"*.txt"` nhắm tới các entry có tên kết thúc bằng `.txt` trong thư mục đang duyệt.
- Việc khớp chữ hoa/chữ thường có thể phụ thuộc provider/filesystem; đừng dựa vào hành vi giống nhau trên mọi nền tảng.
- API này chỉ xét **entry trực tiếp**, không tự tìm mọi tệp `.txt` trong cây con.
- Nó lọc **tên entry**, không mặc nhiên đảm bảo đó là tệp thường: một **thư mục** tên `notes.txt` cũng có thể khớp tên.

### 8.1. Glob không phải regular expression

Một ví dụ khác:

~~~java
Files.newDirectoryStream(dir, "*.{txt,md}");
~~~

Đây là đoạn minh họa; glob chọn tên kết thúc bằng `.txt` **hoặc** `.md` theo cú pháp lựa chọn trong glob của Java. Không diễn giải nó thành Java regex `".*\\.(txt|md)"`: hai ngôn ngữ mẫu có quy tắc khác nhau.

Nếu chỉ cần một tệp mở rộng cụ thể, `"*.txt"` dễ đọc hơn regex phức tạp. Nếu cần kiểm tra kích thước, loại entry hoặc metadata, dùng overload `Filter<Path>` ở phần sau.

### 8.2. Ví dụ Java 17: lọc .txt và xuất kết quả ổn định

Lưu **DirectoryStreamGlobDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamGlobDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("glob-demo-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");
        Path log = dir.resolve("notes.log");
        Path child = dir.resolve("child");

        try {
            Files.writeString(a, "A", StandardCharsets.UTF_8);
            Files.writeString(b, "B", StandardCharsets.UTF_8);
            Files.writeString(log, "log", StandardCharsets.UTF_8);
            Files.createDirectory(child);
            Files.writeString(child.resolve("nested.txt"),
                    "nested", StandardCharsets.UTF_8);

            List<String> names = new ArrayList<>();
            try (DirectoryStream<Path> entries =
                         Files.newDirectoryStream(dir, "*.txt")) {
                for (Path entry : entries) {
                    names.add(entry.getFileName().toString());
                }
            }

            Collections.sort(names);
            System.out.println(names);
        } finally {
            Files.deleteIfExists(child.resolve("nested.txt"));
            Files.deleteIfExists(child);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(log);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamGlobDemo.java
java DirectoryStreamGlobDemo
~~~

Kết quả:

~~~text
[a.txt, b.txt]
~~~

`nested.txt` không xuất hiện dù tên khớp mẫu: đó là entry **bên trong `child`**, không phải entry trực tiếp của `dir`. Đây là khác biệt cốt lõi giữa liệt kê một thư mục và duyệt cả cây.

## 9. Lọc bằng DirectoryStream.Filter<Path>

Khi cần điều kiện ngoài một glob tên tệp, sử dụng overload:

~~~java
DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, entry -> condition(entry));
~~~

Đây là đoạn **minh họa cú pháp**, với `condition(Path)` là hàm giả định trong ứng dụng. `DirectoryStream.Filter<Path>` là một functional interface có phương thức `accept(Path entry)` trả `boolean` và có thể khai báo `throws IOException`.

Ví dụ chọn **tệp thường** có tên bắt đầu bằng `report-` và kết thúc `.txt`:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(
        dir,
        entry -> Files.isRegularFile(entry)
                && entry.getFileName().toString().startsWith("report-")
                && entry.getFileName().toString().endsWith(".txt"))) {

    for (Path entry : entries) {
        // Xử lý các tệp được chọn.
    }
}
~~~

Đoạn này minh họa với `Path dir` có sẵn. `Files.isRegularFile` có thể truy cập metadata filesystem và có quy tắc đi theo symbolic link khi không truyền `LinkOption.NOFOLLOW_LINKS`; nếu không truy vấn được, nó có thể trả false. Nếu logic cần phân biệt lỗi metadata với “không phải tệp thường”, hãy dùng API như `Files.readAttributes` và xử lý `IOException` thay vì coi mọi false là một trường hợp bình thường.

### 9.1. Bộ lọc được gọi trong quá trình duyệt

Một điều kiện lọc không nên có side effect nguy hiểm (xóa/đổi tên entry, ghi nhận giao dịch không thể lặp, thay đổi toàn bộ thư mục), bởi thời điểm và cách thực hiện lọc liên quan đến việc lấy phần tử từ nguồn. Thiết kế filter ưu tiên kiểm tra ngắn gọn, thuần về điều kiện nhận entry.

Nếu filter phải truy cập thuộc tính tệp, nó có thể chậm và lỗi; việc duyệt thư mục lớn cần tính đến chi phí của **mỗi lần kiểm tra**.

### 9.2. IOException trong Filter

`Filter.accept(Path)` có thể ném `IOException`. Theo hợp đồng của `DirectoryStream`, lỗi I/O khi lấy entry, bao gồm lỗi từ filter, có thể xuất hiện dưới dạng **`DirectoryIteratorException`** khi duyệt. Loại này là unchecked, nhưng `getCause()` giữ `IOException` gốc.

Không nên viết `catch(IOException)` quanh toàn bộ vòng lặp rồi giả định sẽ bắt được mọi lỗi phát sinh từ iterator. Nên hiểu hai đường lỗi:

- Lỗi **mở/đóng stream** thường đi qua `IOException`.
- Lỗi **khi iterator tìm entry kế tiếp** thường được bọc trong `DirectoryIteratorException`.

Đoạn xử lý minh họa:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir, filter)) {
    for (Path entry : entries) {
        process(entry);
    }
} catch (DirectoryIteratorException e) {
    IOException cause = e.getCause();
    // Báo lỗi duyệt hoặc lọc, giữ cause.
} catch (IOException e) {
    // Báo lỗi mở hoặc đóng stream.
}
~~~

Đây là đoạn minh họa, **không phải chương trình độc lập**; `dir`, `filter` và `process` do ứng dụng cung cấp. `DirectoryIteratorException.getCause()` theo API trả `IOException`. Tránh chỉ lưu mỗi `getMessage()` mà bỏ stack trace và cause.

## 10. Ví dụ Java 17: lọc bằng lambda và tên entry

Ví dụ dưới kiểm tra tệp thường bắt đầu bằng `report-` và kết thúc `.txt`; thứ tự liệt kê được sắp xếp trước khi in.

Lưu **DirectoryStreamFilterDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class DirectoryStreamFilterDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("filter-demo-");
        Path first = dir.resolve("report-1.txt");
        Path second = dir.resolve("report-2.log");
        Path other = dir.resolve("other.txt");
        Path namedDir = dir.resolve("report-dir.txt");

        try {
            Files.writeString(first, "ok", StandardCharsets.UTF_8);
            Files.writeString(second, "log", StandardCharsets.UTF_8);
            Files.writeString(other, "other", StandardCharsets.UTF_8);
            Files.createDirectory(namedDir);

            List<String> names = new ArrayList<>();

            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(dir, entry ->
                                 Files.isRegularFile(entry)
                                 && entry.getFileName().toString()
                                         .startsWith("report-")
                                 && entry.getFileName().toString()
                                         .endsWith(".txt"))) {
                for (Path entry : stream) {
                    names.add(entry.getFileName().toString());
                }
            }

            Collections.sort(names);
            System.out.println(names);
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(other);
            Files.deleteIfExists(namedDir);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamFilterDemo.java
java DirectoryStreamFilterDemo
~~~

Kết quả:

~~~text
[report-1.txt]
~~~

Hai entry khác đều bị loại vì phần tên không khớp đủ điều kiện. Thư mục `report-dir.txt` tuy có tên phù hợp nhưng không qua `Files.isRegularFile`. Lưu ý: nếu symbolic link trỏ đến tệp thường, `Files.isRegularFile` với tùy chọn mặc định có thể coi nó như tệp thường; cần xác định chính sách liên kết nếu không muốn điều đó.

## 11. Lỗi ở ba giai đoạn: mở, duyệt và đóng

Không nên coi thao tác “liệt kê thư mục” là một bước duy nhất. Nó có ít nhất ba giai đoạn có thể thất bại:

| Giai đoạn | API điển hình | Loại lỗi cần nghĩ tới |
| --- | --- | --- |
| Mở | `Files.newDirectoryStream(dir)` | `NotDirectoryException`, `NoSuchFileException`, `AccessDeniedException` hoặc `IOException` khác |
| Duyệt / áp dụng Filter | `iterator().hasNext()` / `next()` qua for-each | `DirectoryIteratorException` bọc nguyên nhân I/O |
| Đóng | `DirectoryStream.close()` | `IOException` từ việc giải phóng tài nguyên |

Ví dụ, một đường dẫn có thể tồn tại nhưng là **tệp thường**, không phải thư mục. Lời gọi `Files.newDirectoryStream` có thể ném `NotDirectoryException` hoặc `IOException` theo provider. Một thư mục có thể bị xóa hoặc bị mất quyền khi đang duyệt, khiến iterator thất bại sau khi đã trả vài entry.

**Đừng coi lỗi giữa vòng lặp là “đã duyệt xong”.** Kết quả lúc đó có thể chỉ là tập con, không có nghĩa danh sách đầy đủ.

### 11.1. EOF của iterator khác lỗi

Một vòng `for (Path entry : stream)` kết thúc bình thường khi không còn phần tử; không cần ném exception. `DirectoryIteratorException` nghĩa là có lỗi trong quá trình phát hiện phần tử, chứ không phải báo hết thư mục thông thường.

Với dữ liệu nghiệp vụ yêu cầu đếm đủ mọi entry, khi iterator ném exception cần đánh dấu **thất bại**, không trả số đếm đã có như kết quả hoàn chỉnh.

### 11.2. IOException lúc close vẫn quan trọng

Ngay cả khi đã duyệt hết entry, `close()` vẫn có thể báo `IOException`. `try-with-resources` để ngoại lệ này truyền ra đúng chỗ. Nếu thân `try` đã có ngoại lệ và close cũng thất bại, lỗi đóng được giữ dưới dạng **suppressed exception** gắn vào lỗi chính, giúp chẩn đoán đầy đủ.

Nếu có logic bắt `DirectoryIteratorException`, hãy giữ cả `getCause()` và những suppressed exceptions liên quan thay vì chỉ in một chuỗi thông điệp đơn giản.

## 12. Ví dụ kiểm thử lỗi iterator bằng một Filter chủ động ném IOException

Để kiểm chứng đường lỗi mà không phải dựa vào quyền hệ điều hành ngẫu nhiên, ta cố tình tạo filter ném `IOException` cho entry của thư mục thử nghiệm. Chương trình không phụ thuộc thứ tự liệt kê vì thư mục chỉ có một entry.

Lưu **DirectoryStreamErrorDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryStreamErrorDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("iterator-error-");
        Path file = dir.resolve("one.txt");

        try {
            Files.writeString(file, "x", StandardCharsets.UTF_8);

            try (DirectoryStream<Path> entries =
                    Files.newDirectoryStream(dir, entry -> {
                        throw new IOException("Filter failed");
                    })) {
                for (Path ignored : entries) {
                    System.out.println("Unexpected entry");
                }
            } catch (DirectoryIteratorException e) {
                System.out.println("Cause: " + e.getCause().getMessage());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamErrorDemo.java
java DirectoryStreamErrorDemo
~~~

Kết quả với provider hệ thống tệp mặc định theo hợp đồng bọc lỗi filter:

~~~text
Cause: Filter failed
~~~

Mục đích của ví dụ không phải “làm lỗi thật” trên ổ đĩa mà là thực hành **sự khác biệt giữa IOException và DirectoryIteratorException**. `Filter.accept` phát sinh IOException, iterator bọc lỗi để caller thấy qua `DirectoryIteratorException.getCause()`.

`Files.newDirectoryStream` vẫn cần được đóng, dù vòng lặp chưa xử lý được entry nào. `try-with-resources` giúp bảo đảm điều đó.

## 13. Đệ quy an toàn về handle: không mở vô hạn stream lồng nhau

Để duyệt nhiều tầng bằng `DirectoryStream`, một cách trực quan là đệ quy:

~~~java
static void visit(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        for (Path entry : entries) {
            if (Files.isDirectory(entry)) {
                visit(entry);
            } else {
                // Xử lý tệp.
            }
        }
    }
}
~~~

Đây là **đoạn phương thức minh họa**, không phải chương trình độc lập. Nó có những giới hạn đáng lưu ý:

- Mỗi lời gọi `visit` giữ stream của thư mục cha **đang mở** khi mở stream của thư mục con. Với cây thư mục rất sâu, nhiều handle đồng thời có thể tồn tại.
- Đệ quy sâu cũng có nguy cơ dùng nhiều stack và thậm chí `StackOverflowError`.
- `Files.isDirectory(entry)` mặc định có thể theo symbolic link, dẫn tới vòng lặp nếu liên kết tạo chu trình.
- Mỗi stream cần được đóng, kể cả khi đệ quy hoặc xử lý entry thất bại.
- Phân loại entry theo `Files.isDirectory` vẫn có thể gặp TOCTOU: trạng thái có thể đổi ngay sau khi kiểm tra.

Với nghiệp vụ cần duyệt cây sâu và kiểm soát symlink, lỗi, quyền truy cập, nên cân nhắc `Files.walkFileTree` với `FileVisitor` thay vì tự đệ quy đơn giản.

### 13.1. Duyệt hai tầng bằng hai phạm vi try-with-resources

Nếu chỉ cần đi vào vài thư mục con, có thể viết nested try:

~~~java
try (DirectoryStream<Path> top =
        Files.newDirectoryStream(root)) {
    for (Path entry : top) {
        if (Files.isDirectory(entry)) {
            try (DirectoryStream<Path> children =
                    Files.newDirectoryStream(entry)) {
                for (Path child : children) {
                    // Xử lý child.
                }
            }
        }
    }
}
~~~

Đoạn minh họa với `Path root`. Khi thoát khỏi vòng trong, stream con được đóng, còn stream cha vẫn mở để duyệt phần còn lại. Khi thoát khỏi khối ngoài, stream cha được đóng. Điều này kiểm soát tài nguyên tốt hơn việc gom các `DirectoryStream` vào một danh sách và chỉ đóng toàn bộ sau nhiều bước.

Nếu muốn tránh mở stream con khi liên kết trỏ tới thư mục, sử dụng `Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS)`. Đây chỉ là bước nhận diện; cần tiếp tục xử lý lỗi truy cập/entry biến mất tại điểm mở thực sự.

## 14. Symbolic link, thay đổi đồng thời và SecureDirectoryStream

### 14.1. Symbolic link có thể khiến traversal đi xa hơn dự định

Giả sử:

~~~text
root/
  docs/
  jump -> /outside/
~~~

Khi dùng `Files.isDirectory(jump)` với tùy chọn mặc định, một symbolic link trỏ tới thư mục khác có thể được nhận là thư mục. Nếu đệ quy vào nó, chương trình có thể rời ngoài cây `root` hoặc đi vào chu trình.

Để tránh vô tình đi theo liên kết:

~~~java
boolean physicalDirectory =
        Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS);
~~~

Đây là đoạn minh họa; cần import `java.nio.file.LinkOption`. Nó phân biệt việc kiểm tra bản thân entry với việc theo đích liên kết. Nhưng việc kiểm tra rồi mở vẫn tồn tại **race** nếu entry bị thay thế giữa hai thao tác.

Không dùng `normalize()` đơn thuần như biện pháp bảo mật chống path traversal. `normalize()` chỉ rút gọn cú pháp; nó không tự giải quyết symbolic link hay khóa đường dẫn.

### 14.2. SecureDirectoryStream là gì?

Một số provider có thể cung cấp `SecureDirectoryStream<Path>`, một subtype cho phép thực hiện các thao tác tương đối với thư mục đang mở theo cách có khả năng giảm rủi ro race về đường dẫn. Không phải mọi provider đều hỗ trợ.

Mô hình kiểm tra:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    if (entries instanceof SecureDirectoryStream<Path> secure) {
        // Có thể sử dụng API tương đối với thư mục đang mở.
    } else {
        // Provider không cung cấp tính năng này.
    }
}
~~~

Đây là đoạn minh họa; cần import `java.nio.file.SecureDirectoryStream`. Không được giả định phương thức này luôn có trên mọi filesystem. Nếu phần mềm xử lý đường dẫn do người dùng không tin cậy cung cấp, cần đánh giá quyền truy cập và rủi ro race ở cấp kiến trúc, không chỉ dựa vào một lệnh `isDirectory`.

### 14.3. Thư mục thay đổi trong lúc duyệt

`DirectoryStream` thường duyệt theo trạng thái provider và không đóng băng một snapshot giao dịch. Nếu tiến trình khác thêm/xóa/đổi tên entry:

- Một số entry mới có thể không xuất hiện, dù tồn tại khi vòng lặp kết thúc.
- Một entry đã trả có thể biến mất trước khi bạn truy cập nội dung của nó.
- Việc kiểm tra metadata và mở tệp ngay sau đó có thể trả kết quả khác.

Nếu yêu cầu danh sách mang tính kiểm toán, cần quy trình kiểm soát dữ liệu đầu vào, thời điểm chụp, tính bất biến hoặc lưu snapshot theo nghiệp vụ. `DirectoryStream` đơn thuần chỉ là cơ chế liệt kê entry, không phải transaction.

## 15. So sánh DirectoryStream, Files.list, Files.walk và walkFileTree

| Mục đích | API phù hợp | Quản lý tài nguyên |
| --- | --- | --- |
| Duyệt trực tiếp các entry bằng vòng `for-each` | `Files.newDirectoryStream(dir)` | Đóng `DirectoryStream` |
| Duyệt trực tiếp, lọc theo tên glob | `Files.newDirectoryStream(dir, "*.txt")` | Đóng `DirectoryStream` |
| Duyệt trực tiếp, filter theo metadata/custom logic | `Files.newDirectoryStream(dir, filter)` | Đóng `DirectoryStream` |
| Muốn thao tác `filter/map/collect` của Java Stream với con trực tiếp | `Files.list(dir)` | Đóng `Stream<Path>` |
| Duyệt nhiều mức sâu theo `Stream<Path>` | `Files.walk(root, maxDepth)` | Đóng `Stream<Path>` |
| Duyệt cây, cần callback `visitFileFailed` và điều khiển tiếp tục/bỏ qua | `Files.walkFileTree` | API quản lý việc duyệt nội bộ |

### 15.1. Files.list cũng mở tài nguyên cần đóng

~~~java
try (java.util.stream.Stream<Path> paths =
        Files.list(dir)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

Đây là đoạn minh họa với `Path dir` có sẵn. `Files.list` trả `Stream<Path>` lazy, gắn với tài nguyên duyệt thư mục; **không** nên tạo một stream, chỉ lấy iterator rồi bỏ quên việc đóng.

Một `java.util.stream.Stream` nói chung không phải lúc nào cũng gắn với tài nguyên hệ điều hành, nhưng `Files.list` và `Files.walk` là các ví dụ **cần close** theo hợp đồng.

### 15.2. Files.walk có đi sâu hơn nhưng phải giới hạn

~~~java
try (java.util.stream.Stream<Path> paths =
        Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
~~~

Đoạn minh họa với `Path root`. `maxDepth=2` giới hạn số mức đi xuống theo định nghĩa của API; phần tử gốc nằm ở độ sâu 0. Nếu muốn xử lý lỗi từng file và có chính sách bỏ qua/tiếp tục chi tiết, `walkFileTree` có thể rõ ràng hơn.

### 15.3. Files.walkFileTree cho phép xử lý lỗi theo callback

`Files.walkFileTree` gọi các phương thức của `FileVisitor` để duyệt và báo lỗi. Nó hữu ích khi cần duyệt toàn bộ cây, đếm hoặc xử lý tệp, cho phép kiểm soát việc bỏ qua subtree và xử lý `visitFileFailed`. Không nên dùng nó chỉ để liệt kê 2–3 entry trực tiếp nếu `DirectoryStream` đã đủ.

Ví dụ tư duy:

~~~text
DirectoryStream:   mở 1 thư mục → duyệt con trực tiếp → đóng
Files.list:        mở 1 thư mục → Stream operations → đóng
Files.walk:        duyệt sâu với Stream<Path> → đóng
walkFileTree:      duyệt sâu bằng FileVisitor callback
~~~

## 16. Ví dụ Java 17: đếm entry trực tiếp và so sánh với Files.list

Lưu **DirectoryStreamCountDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class DirectoryStreamCountDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("count-demo-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");
        Path child = dir.resolve("child");

        try {
            Files.createFile(a);
            Files.createFile(b);
            Files.createDirectory(child);
            Files.createFile(child.resolve("nested.txt"));

            long viaDirectoryStream = 0;
            try (DirectoryStream<Path> entries =
                         Files.newDirectoryStream(dir)) {
                for (Path ignored : entries) {
                    viaDirectoryStream++;
                }
            }

            long viaFilesList;
            try (Stream<Path> entries = Files.list(dir)) {
                viaFilesList = entries.count();
            }

            System.out.println("DirectoryStream: "
                    + viaDirectoryStream);
            System.out.println("Files.list: " + viaFilesList);
        } finally {
            Files.deleteIfExists(child.resolve("nested.txt"));
            Files.deleteIfExists(child);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DirectoryStreamCountDemo.java
java DirectoryStreamCountDemo
~~~

Kết quả:

~~~text
DirectoryStream: 3
Files.list: 3
~~~

Cả hai API chỉ liệt kê **con trực tiếp** của `dir`. Entry `child` được đếm một lần, còn `child/nested.txt` không nằm trong tập con trực tiếp. Ví dụ cố tình tạo tệp con để làm rõ điều này. Hai stream đều được đóng trước khi chương trình xóa thư mục.

Không suy rằng luôn có cùng số lượng nếu thư mục đang thay đổi đồng thời: đây là ví dụ với bộ dữ liệu do chương trình kiểm soát.

## 17. Xử lý exception: không biến lỗi duyệt thành danh sách hợp lệ

Một lỗi thiết kế phổ biến:

~~~java
List<Path> result = new ArrayList<>();
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        result.add(entry);
    }
} catch (Exception e) {
    // Bỏ qua mọi lỗi.
}
return result;
~~~

Đây là **anti-pattern** minh họa dưới dạng phần thân phương thức, không phải chương trình độc lập. Nếu lỗi xảy ra giữa vòng lặp, caller nhận một danh sách **chỉ chứa một phần entry** nhưng không biết nó chưa hoàn chỉnh.

Cách phù hợp hơn:

1. Để `IOException` và `DirectoryIteratorException` truyền lên nơi có thể quyết định nghiệp vụ.
2. Nếu cần thu thập nhiều thư mục độc lập, ghi trạng thái thành công/thất bại **riêng cho từng thư mục**.
3. Chỉ trả kết quả “đầy đủ” khi vòng duyệt và close kết thúc thành công.
4. Khi cần cung cấp kết quả một phần, dùng kiểu kết quả có trạng thái minh bạch (`partial`, số phần tử xử lý, lỗi gốc...).
5. Giữ `cause`, `suppressed exceptions` và ngữ cảnh đường dẫn đã xử lý an toàn khi log.

### 17.1. Bắt IOException và DirectoryIteratorException ở đúng vị trí

Một phương thức có thể viết:

~~~java
static void printDirectory(Path dir) throws IOException {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(dir)) {
        for (Path entry : entries) {
            System.out.println(entry.getFileName());
        }
    } catch (DirectoryIteratorException e) {
        throw new IOException("Failed while iterating: " + dir,
                e.getCause());
    }
}
~~~

Đây là đoạn phương thức minh họa; cần import `DirectoryIteratorException`, `DirectoryStream`, `Files`, `Path` và `IOException`. Lỗi mở/close vốn là `IOException` nên được truyền lên tự nhiên; lỗi iterator được bọc thành IOException với thông điệp ngữ cảnh và `cause` gốc.

Việc bọc này thích hợp nếu API tầng ngoài chỉ muốn phơi bày checked `IOException`. Nếu tầng ngoài cần phân biệt loại lỗi cụ thể, có thể giữ nguyên `DirectoryIteratorException` hoặc dùng kiểu lỗi nghiệp vụ có mã trạng thái. Tránh bọc mọi lỗi thành cùng một thông điệp vô nghĩa.

### 17.2. try-with-resources khi lỗi xuất hiện đồng thời với close

Nếu thân `try` ném exception và `DirectoryStream.close()` cũng ném exception, Java gắn lỗi close dưới dạng **suppressed** của lỗi chính. Khi cần chẩn đoán, kiểm tra `Throwable.getSuppressed()`. Việc tự đóng trong `finally` thiếu cẩn thận có thể che mất lỗi gốc.

Chỉ gọi `close()` khi thật sự sở hữu stream; không đóng một stream do caller cung cấp nếu hợp đồng không trao quyền sở hữu.

## 18. Quyền truy cập, đường dẫn và tính đúng đắn dữ liệu

### 18.1. DirectoryStream không bảo đảm quyền đọc nội dung từng entry

Có quyền liệt kê thư mục không đồng nghĩa có quyền đọc từng tệp bên trong, mở thư mục con, sửa/xóa entry hoặc đọc metadata của mọi entry. Quyền thực tế tùy filesystem và cơ chế kiểm soát truy cập.

Sau khi duyệt nhận được `Path entry`, thao tác:

~~~java
String text = Files.readString(entry);
~~~

vẫn có thể thất bại vì `entry` đã biến mất, là thư mục, không phải văn bản hoặc không được phép đọc. Đây là đoạn minh họa, không phải vòng lặp hoàn chỉnh.

### 18.2. Không tự tin vào tên tệp từ nguồn không đáng tin

Khi xử lý tên entry thành URL, lệnh shell, truy vấn hay tên tệp đích, cần áp dụng chính sách riêng về escaping, đường dẫn con, symbolic link và quyền. `DirectoryStream` chỉ cung cấp một `Path`; nó không thay thế kiểm tra dữ liệu đầu vào.

Ví dụ nếu duyệt thư mục upload của người dùng, không nên lấy `entry.getFileName().toString()` rồi nối trực tiếp vào chuỗi lệnh shell. Hãy dùng API phù hợp để tránh chèn lệnh và xử lý ký tự đặc biệt.

### 18.3. Kiểm tra rồi thao tác có thể có race

Đoạn:

~~~java
if (Files.isRegularFile(entry)) {
    byte[] bytes = Files.readAllBytes(entry);
}
~~~

là minh họa kiểm tra trước khi đọc. Giữa `isRegularFile` và `readAllBytes`, entry có thể bị thay đổi. Vì vậy ứng dụng vẫn phải xử lý `IOException` của thao tác đọc và không coi kiểm tra trước là bằng chứng tuyệt đối.

## 19. Hiệu năng và bộ nhớ

Một số lưu ý khi duyệt thư mục lớn:

- `DirectoryStream` cho phép lặp dần các `Path`; nó không buộc ứng dụng tạo ngay một `List<Path>` chứa mọi entry.
- Nếu chỉ cần đếm hay xử lý mỗi entry độc lập, dùng một vòng `for-each` trong `try-with-resources` và không tích lũy vô hạn.
- Nếu cần sắp xếp tên để hiển thị, bạn **phải trả chi phí bộ nhớ/CPU** cho việc gom rồi sort (hoặc áp dụng cơ chế sort ngoài bộ nhớ).
- Filter kiểm tra metadata nhiều lần có thể gây nhiều thao tác I/O; tối ưu theo nhu cầu và đo đạc.
- Nếu một thư mục chứa hàng triệu entry, đừng giữ DirectoryStream mở trong thời gian dài chỉ để chờ tương tác người dùng. Duyệt/đóng theo phạm vi công việc, hoặc chuyển sang kiến trúc truy vấn/index phù hợp.
- Không dùng `DirectoryStream` như một cơ chế “watch” báo thay đổi: nếu muốn theo dõi sự kiện tạo/xóa/sửa, xem `WatchService` với quy tắc riêng. Duyệt một lần không thiết lập đăng ký nhận sự kiện.
- Một `DirectoryStream` không có bảo đảm snapshot nhất quán; đừng xây kết luận giao dịch chỉ từ việc vòng lặp đã chạy hết.

### 19.1. Khi nào một collection có vẻ dễ hơn?

Nếu thư mục rất nhỏ và chỉ cần tên để hiển thị, việc tạo `List<String>` đã sort có thể đơn giản hơn thao tác trực tiếp với iterator. Tuy nhiên **việc lấy dữ liệu từ filesystem vẫn phải đóng** `DirectoryStream` hoặc `Stream<Path>`; danh sách kết quả không phải lý do bỏ qua close.

Ví dụ:

~~~java
List<String> names = new ArrayList<>();
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(dir)) {
    for (Path entry : entries) {
        names.add(entry.getFileName().toString());
    }
}
Collections.sort(names);
~~~

Đây là đoạn minh họa, cần các import Java Collections và NIO. Sau close, `names` là dữ liệu trong RAM, có thể dùng an toàn về mặt cấu trúc danh sách; nhưng filesystem có thể tiếp tục thay đổi, nên danh sách không còn phản ánh thời gian thực.

## 20. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Mở `DirectoryStream` rồi quên đóng | Rò rỉ directory handle/file descriptor | `try-with-resources` |
| Tạo `Path` rồi tưởng đã mở thư mục | Lẫn đường dẫn với tài nguyên | Chỉ `newDirectoryStream` mới mở việc duyệt |
| Duyệt sau khi đã rời khối `try` | Stream đã đóng | Xử lý trong khối hoặc trả bản sao dữ liệu |
| Gọi `iterator()` hai lần | `DirectoryStream` chỉ hỗ trợ tối đa một iterator | Mở stream mới hoặc lưu kết quả |
| Giả định kết quả đã sắp xếp | Provider không hứa thứ tự | Thu thập rồi sort nếu cần |
| Giả định sẽ duyệt đệ quy | Chỉ có entry trực tiếp | Tự quản lý tầng con hoặc dùng `walkFileTree` |
| Duyệt cây sâu với stream cha/con không đóng | Có thể mở quá nhiều handle | Nested try hoặc dùng API traversal thích hợp |
| Dùng `isDirectory` mặc định để đệ quy mọi entry | Có thể đi theo symbolic link và gặp chu trình | `NOFOLLOW_LINKS` cùng thiết kế traversal an toàn |
| Dùng glob `*.txt` rồi nghĩ chỉ nhận file thường | Thư mục tên `a.txt` cũng có thể khớp | Thêm `Files.isRegularFile` |
| Nghĩ glob là Java regex | Mẫu khớp sai | Phân biệt cú pháp glob và regex |
| Bắt mỗi `IOException` quanh vòng lặp | Bỏ sót lỗi iterator unchecked | Xử lý `DirectoryIteratorException` |
| Bắt `Exception` rồi trả list đã gom | Che thất bại, tạo kết quả chưa đầy đủ | Báo lỗi hoặc trả trạng thái partial rõ |
| Dùng `Files.list` mà không close | `Stream<Path>` giữ tài nguyên duyệt | `try-with-resources` |
| Tin rằng entry thấy được vẫn tồn tại sau đó | TOCTOU và filesystem đổi đồng thời | Bắt lỗi của thao tác thực |
| Gọi `normalize` và coi đã an toàn với symlink | Normalize không giải quyết filesystem thật | Kiểm soát quyền, liên kết, root và race |
| Dùng DirectoryStream để theo dõi mọi thay đổi | Đây là liệt kê, không phải event watcher | Xem `WatchService` |

## 21. Bài tập thực hành

**Bài 1 — Đếm con trực tiếp.** Tạo thư mục tạm chứa hai tệp và một thư mục con, trong thư mục con có một tệp khác. Nếu duyệt root bằng `DirectoryStream`, bao nhiêu entry được tính?

**Đáp án:** ba entry trực tiếp (hai tệp và thư mục con); tệp sâu hơn không được tính.

**Bài 2 — Glob và loại entry.** Một thư mục chứa `notes.txt` là file và `backup.txt` là **thư mục**. `newDirectoryStream(dir, "*.txt")` có thể trả gì?

**Đáp án:** có thể trả cả hai, vì glob kiểm tra **tên entry**. Muốn chỉ tệp thường, bổ sung `Files.isRegularFile` theo chính sách symbolic link mong muốn.

**Bài 3 — Tại sao phải dùng try-with-resources?** Nếu vòng lặp duyệt thất bại ở entry thứ 10, điều gì xảy ra với handle nếu đoạn code chỉ tự gọi `close()` ở cuối nhánh thành công?

**Đáp án:** có nguy cơ stream không được đóng. `try-with-resources` gọi close khi rời khối kể cả có ngoại lệ.

**Bài 4 — Lỗi mở hay lỗi duyệt?** Khi `Files.newDirectoryStream(dir)` không mở được vì thiếu quyền, có thể gặp ngoại lệ nào? Khi filter ném `IOException` trong lúc lấy phần tử thì sao?

**Đáp án:** lỗi mở thường là `IOException` hoặc lớp con thích hợp như `AccessDeniedException`. Lỗi lọc/duyệt có thể được bọc trong `DirectoryIteratorException` và `getCause()` cho biết IOException gốc.

**Bài 5 — Thứ tự.** Vì sao kết quả `for (Path entry : entries)` không nên dùng trực tiếp để tạo bảng báo cáo luôn phải sắp xếp tên?

**Đáp án:** `DirectoryStream` không bảo đảm thứ tự. Nếu cần thứ tự ổn định, gom dữ liệu và sort theo comparator được định nghĩa rõ.

**Bài 6 — Trách nhiệm đóng.** Một hàm nhận `DirectoryStream<Path>` do caller mở và chỉ đếm vài entry. Ai nên đóng?

**Đáp án:** phần sở hữu theo hợp đồng. Theo mặc định, caller mở và giữ quyền sở hữu thì caller đóng; hàm mượn stream không nên tự đóng mà không có thỏa thuận.

**Bài 7 — Đệ quy.** Vì sao gọi `visit(entry)` khi `Files.isDirectory(entry)` trả true có thể nguy hiểm?

**Đáp án:** có thể theo symbolic link tới bên ngoài hoặc tạo chu trình; đệ quy sâu làm tăng stack/handle. Cần chính sách link, giới hạn độ sâu và xử lý lỗi phù hợp, hoặc `walkFileTree`.

### Thực hành mở rộng

1. Thêm `"report-3.txt"` vào `DirectoryStreamFilterDemo` và bảo đảm kết quả được sắp xếp bất kể thứ tự provider trả về.
2. Thử thay glob `"*.txt"` bằng `"*.{txt,md}"` và tạo một tệp `README.md` để quan sát.
3. Viết một hàm `listNames(Path dir)` dùng `try-with-resources`, trả một `List<String>` đã sort và để lỗi I/O truyền lên, không trả danh sách nửa chừng.
4. Viết hàm duyệt hai tầng bằng nested `try-with-resources`, xác nhận stream con đóng trước khi xóa thư mục.
5. Tạo một `Filter<Path>` có thể ném `IOException`, bắt `DirectoryIteratorException` và in thông điệp cause. Không dựa vào lỗi hệ điều hành ngẫu nhiên.
6. So sánh `Files.list(dir).count()` với việc đếm qua `DirectoryStream` trên một thư mục không đổi, nhớ đóng cả hai nguồn.
7. Xây dựng chính sách đối với symbolic link: phân biệt khi nào muốn đi theo liên kết, khi nào phải bỏ qua nó, và kiểm thử trên filesystem có hỗ trợ liên kết.

## 22. Tổng kết

- **`Files.newDirectoryStream(dir)`** mở một cơ chế duyệt **các phần tử trực tiếp** của thư mục, trả về `DirectoryStream<Path>`.
- **`DirectoryStream` là tài nguyên `Closeable`**, có thể giữ handle thư mục. **Luôn đóng bằng `try-with-resources`** trong mã sở hữu stream; đừng để GC quyết định thời điểm đóng.
- **Một stream chỉ hỗ trợ tối đa một iterator**, không có thứ tự được bảo đảm, và không bảo đảm snapshot nhất quán khi thư mục thay đổi.
- **Glob** như `"*.txt"` lọc tên entry; **`Filter<Path>`** xử lý điều kiện tự định nghĩa, bao gồm metadata khi cần.
- **Lỗi mở/đóng** thường là `IOException`; **lỗi khi lặp** có thể là `DirectoryIteratorException` chứa cause `IOException`.
- **Đệ quy cần quản lý nhiều handle** và symbolic link cẩn thận; với cây sâu/hệ thống phức tạp, `Files.walkFileTree` thường phù hợp hơn.
- **`Files.list` và `Files.walk` cũng phải được đóng** vì chúng trả Stream<Path> gắn với tài nguyên filesystem.
- **Đường dẫn được liệt kê không phải khóa hay xác nhận tồn tại vĩnh viễn**; truy cập nội dung về sau vẫn cần xử lý ngoại lệ và điều kiện thay đổi đồng thời.

### Tài liệu API chính thức (Java SE 17)

- [DirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html)
- [DirectoryStream.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.Filter.html)
- [DirectoryIteratorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryIteratorException.html)
- [Files.newDirectoryStream và Files.list](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor))
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
- [LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
