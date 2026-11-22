# `preVisitDirectory`, `visitFile`, `visitFileFailed` và `postVisitDirectory` trong Java NIO

## 1. Vì sao cần các callback khi duyệt cây thư mục?

Một thư mục có thể chứa tệp, thư mục con và nhiều mức lồng nhau. Khi muốn kiểm kê tệp, tính dung lượng, lọc phần mở rộng, sao chép hoặc xóa cây thư mục, ứng dụng thường cần **xử lý khác nhau trước khi đi vào thư mục, khi gặp tệp, khi truy cập thất bại và sau khi đã duyệt xong thư mục**.

Java NIO.2 cung cấp `Files.walkFileTree(...)` kết hợp giao diện `FileVisitor<Path>`. Bốn callback cốt lõi là:

1. `preVisitDirectory` — được gọi **trước khi duyệt các mục bên trong thư mục**.
2. `visitFile` — được gọi khi gặp một mục được xem là **file** ở mức duyệt hiện tại.
3. `visitFileFailed` — được gọi khi hệ thống **không thể truy cập một mục** theo quy tắc của quá trình duyệt.
4. `postVisitDirectory` — được gọi **sau khi đã duyệt xong thư mục**, hoặc khi gặp lỗi trong quá trình lặp các mục của thư mục đó.

Nhờ tách thành các callback, một thuật toán có thể làm việc tại cả **thời điểm đi xuống** và **thời điểm đi lên** trong cây, thay vì phải tự viết logic đệ quy, mở từng directory stream và quản lý tất cả trường hợp lỗi.

**Điểm cốt lõi:** Đây là các phương thức của **visitor dùng khi duyệt cây**, không phải sự kiện tự động chạy nền mỗi khi filesystem có tệp mới. Chúng được gọi khi ứng dụng thực sự thực hiện `Files.walkFileTree`.

## 2. API và cấu trúc lớp

Các thành phần chính nằm trong `java.nio.file`:

```java
Files.walkFileTree(start, visitor);
Files.walkFileTree(start, options, maxDepth, visitor);
```

Trong đó:

- `start` là một `Path` chỉ nơi bắt đầu duyệt.
- `options` là tập `FileVisitOption`, ví dụ `FOLLOW_LINKS`.
- `maxDepth` giới hạn độ sâu được thăm, tính thư mục bắt đầu ở độ sâu 0.
- `visitor` là đối tượng triển khai `FileVisitor<? super Path>`.
- Các thao tác có thể ném `IOException`.

Để tránh phải triển khai cả bốn phương thức từ đầu, thông thường kế thừa **`SimpleFileVisitor<Path>`** và override các callback cần thiết.

Dạng khai báo của `FileVisitor<T>`:

```java
FileVisitResult preVisitDirectory(
        T dir, BasicFileAttributes attrs) throws IOException;

FileVisitResult visitFile(
        T file, BasicFileAttributes attrs) throws IOException;

FileVisitResult visitFileFailed(
        T file, IOException exc) throws IOException;

FileVisitResult postVisitDirectory(
        T dir, IOException exc) throws IOException;
```

Đây là **các chữ ký API để tham khảo**, không phải tệp Java độc lập. `BasicFileAttributes` đến từ `java.nio.file.attribute`. `FileVisitResult` dùng để cho bộ duyệt biết nên tiếp tục, bỏ nhánh, bỏ các mục ngang hàng hay chấm dứt.

Lớp `SimpleFileVisitor` có hành vi mặc định quan trọng:

- `preVisitDirectory(...)` và `visitFile(...)` mặc định trả `CONTINUE`.
- `visitFileFailed(..., exc)` mặc định **ném lại** `exc`.
- `postVisitDirectory(..., exc)` mặc định tiếp tục nếu `exc == null`, nhưng **ném lại** `exc` nếu có lỗi lặp thư mục.

Vì vậy, “không override callback báo lỗi” thường đồng nghĩa với **dừng và để IOException lan ra ngoài**, không phải âm thầm bỏ qua tệp lỗi.

## 3. Thứ tự callback khi duyệt thành công

Xét một cây đơn giản:

```text
root/
└── docs/
    └── note.txt
```

Khi không bỏ qua nhánh, thứ tự callback thường được hình dung:

```text
preVisitDirectory(root)
  preVisitDirectory(root/docs)
    visitFile(root/docs/note.txt)
  postVisitDirectory(root/docs, null)
postVisitDirectory(root, null)
```

Đây là **duyệt theo chiều sâu (depth-first)**: vào thư mục cha, vào thư mục con, xử lý tệp bên trong, đi ra thư mục con, rồi đi ra thư mục cha.

Nếu trong một thư mục có nhiều mục con, **thứ tự giữa các mục ngang hàng không được bảo đảm theo tên, ngày hay kích thước**. Chương trình không nên viết test giả định luôn gặp `a.txt` trước `b.txt`. Muốn xử lý theo thứ tự xác định, phải có chiến lược liệt kê/sắp xếp riêng thay vì mặc định dựa vào `walkFileTree`.

Không phải mọi phần tử trong cây đều đi qua `visitFile`: thư mục được đi xuống thông thường nhận **`preVisitDirectory` và `postVisitDirectory`**, còn tệp thường đi qua **`visitFile`**. Những ngoại lệ như mục ở giới hạn `maxDepth` hoặc symbolic link không được theo sẽ được giải thích ở phần sau.

## 4. `preVisitDirectory` — trước khi đi vào thư mục

Chữ ký:

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException
```

Đây là **chữ ký minh họa**, phải đặt trong một class kế thừa `SimpleFileVisitor<Path>`, có đủ import.

Callback được gọi khi bộ duyệt đã nhận diện một thư mục và **trước khi duyệt những mục chứa bên trong**. Hai đối số:

- `dir`: `Path` của thư mục đang chuẩn bị duyệt.
- `attrs`: thuộc tính cơ bản được đọc cho mục đó, như `isDirectory()`, `size()`, `creationTime()` và `lastModifiedTime()`.

Các công việc phù hợp:

- Ghi nhận “đã vào thư mục” và tăng độ sâu.
- Tạo thư mục đích trước khi sao chép nội dung con.
- Kiểm tra có nên đi vào một nhánh hay không.
- Loại trừ thư mục như `build`, `node_modules` hoặc thư mục cache theo chính sách của ứng dụng.

Ví dụ **đoạn mã đặt trong visitor**:

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) {
    if (dir.getFileName() != null
            && dir.getFileName().toString().equals("cache")) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
```

`SKIP_SUBTREE` ở đây khiến bộ duyệt **không đi vào thư mục `cache`**. Các tệp và thư mục bên trong nó không nhận callback tương ứng; `postVisitDirectory` cho **chính thư mục bị bỏ qua** cũng không được gọi. Những nhánh khác vẫn có thể được duyệt.

Lưu ý: `preVisitDirectory` không đảm bảo “mở thành công mọi mục con” — khi tiếp tục duyệt, lỗi đọc thư mục hoặc đọc thuộc tính vẫn có thể phát sinh.

## 5. `visitFile` — xử lý mục được thăm như file

Chữ ký:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException
```

Đây là **chữ ký minh họa**, không phải chương trình độc lập.

Thông thường `visitFile` được gọi cho các **tệp không phải thư mục**. Nó nhận `Path` và `BasicFileAttributes` để ứng dụng quyết định xử lý:

- Đếm số tệp và cộng kích thước (theo ý nghĩa `attrs.size()`).
- Kiểm tra phần mở rộng hoặc tên.
- Sao chép tệp sang nơi khác.
- Đọc nội dung, tính hash hoặc kiểm tra định dạng.
- Xóa tệp khi đang thực hiện một tác vụ được cho phép.

Ví dụ đếm tệp:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) {
    if (attrs.isRegularFile()) {
        count++;
    }
    return FileVisitResult.CONTINUE;
}
```

Đoạn này **minh họa** trong một visitor có trường `long count`. Dùng `attrs.isRegularFile()` nếu chỉ muốn đếm file thường; không mặc định mọi mục vào `visitFile` đều là file thường trong mọi lựa chọn duyệt.

Đặc biệt:

- Khi **không theo symbolic link**, liên kết thường được thăm dưới dạng một mục riêng, không tự duyệt cây ở đích của link.
- Khi đã tới **`maxDepth`**, một mục là thư mục cũng có thể được chuyển tới `visitFile` thay vì đi sâu và gọi `preVisitDirectory` cho nó.
- Nếu việc lấy thuộc tính cơ bản của một mục thất bại, bộ duyệt có thể gọi **`visitFileFailed`** thay vì `visitFile`.

`visitFile` không có nghĩa nội dung file đã được mở hoặc đọc toàn bộ. Nó chỉ báo rằng quá trình duyệt đã tới mục đó theo quy tắc của visitor.

## 6. `postVisitDirectory` — sau khi thăm các mục con

Chữ ký:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException
```

Đây là **chữ ký minh họa**, đặt trong visitor.

Callback được gọi sau khi đã đi qua các mục trong thư mục, hoặc khi việc lặp các mục bị lỗi. Khác `preVisitDirectory`, đối số thứ hai **không phải thuộc tính**, mà là:

- `null` khi việc lặp các mục trong thư mục kết thúc bình thường.
- `IOException exc` khi có lỗi trong quá trình lặp thư mục, khiến quá trình lặp kết thúc bất thường.

Cách xử lý thường gặp:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;
    }
    System.out.println("Xong thư mục: " + dir);
    return FileVisitResult.CONTINUE;
}
```

Vị trí này lý tưởng cho công việc **hậu thứ tự (post-order)**:

- Kết thúc tổng hợp thông tin từ các thư mục con.
- Hoàn tất hoặc đóng một cấu trúc ứng dụng tương ứng với thư mục.
- Xóa thư mục **sau khi** đã xóa các file và thư mục con trong một quy trình xóa cây có kiểm soát.
- Ghi nhận “rời thư mục” để cân bằng trạng thái trong thuật toán.

**Không giả định `postVisitDirectory` luôn được gọi cho mọi thư mục.** Nếu `preVisitDirectory` trả `SKIP_SUBTREE`/`SKIP_SIBLINGS` đối với một thư mục, bộ duyệt không đi vào nó và không gọi callback hậu kỳ cho thư mục bị bỏ qua. Nếu visitor chủ động ném ngoại lệ hoặc trả `TERMINATE` giữa chừng, các callback hậu kỳ cho tổ tiên chưa hoàn tất **không được bảo đảm**. Khi thật sự cần giải phóng tài nguyên, sử dụng `try/finally` hoặc `try-with-resources` tại phạm vi sở hữu thay vì chỉ dựa vào callback hậu kỳ.

Ngoài ra, lỗi xảy ra **bên trong `visitFile`** do code nghiệp vụ tự ném không nhất thiết được chuyển thành `exc` của `postVisitDirectory`; nhiều trường hợp ngoại lệ sẽ truyền thẳng ra khỏi `walkFileTree`.

## 7. `visitFileFailed` — khi không thể truy cập mục

Chữ ký:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException
```

Đây là **chữ ký minh họa**, không phải chương trình độc lập.

Callback này có thể được gọi khi:

- Không đọc được thuộc tính cơ bản của mục.
- Không mở được một thư mục để duyệt.
- Gặp lỗi I/O khi đi theo symbolic link, ví dụ liên kết vòng với `FOLLOW_LINKS`.
- Đường dẫn đã bị xóa hoặc thay đổi trước lúc hệ thống truy cập nó.

`exc` chứa nguyên nhân I/O. Ví dụ:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    System.err.println("Không thể thăm " + file
            + ": " + exc.getClass().getSimpleName());
    return FileVisitResult.CONTINUE;
}
```

Nếu trả `CONTINUE`, bộ duyệt **bỏ qua mục thất bại và thử tiếp các mục còn lại** khi có thể. Điều này hữu ích cho tác vụ kiểm kê “best effort” nhưng **không tương đương duyệt thành công toàn bộ cây**. Chương trình nên ghi nhận các mục thất bại và không trả báo cáo là “đủ 100%” nếu đã bỏ qua dữ liệu.

Để **fail fast**, chỉ cần:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    throw exc;
}
```

`SimpleFileVisitor` mặc định cũng có hành vi ném lại ngoại lệ tại đây.

**Phân biệt với `postVisitDirectory(dir, exc)`:**

| Tình huống | Callback thích hợp |
| --- | --- |
| Không đọc được thuộc tính một mục | `visitFileFailed` |
| Không mở được thư mục để liệt kê | `visitFileFailed` |
| Đã mở thư mục, nhưng lỗi khi lặp các mục bên trong | `postVisitDirectory` với `exc != null` |
| Ứng dụng tự ném `IOException` trong `visitFile` | Thường truyền ra khỏi quá trình duyệt, **không** được tự động đổi thành `visitFileFailed` |

Điều này giúp phân biệt **lỗi của hệ thống duyệt** với **lỗi trong xử lý nghiệp vụ của chính visitor**.

## 8. `FileVisitResult` — bốn quyết định điều khiển luồng

Bốn callback trả một giá trị của enum `FileVisitResult`:

| Giá trị | Tác dụng |
| --- | --- |
| `CONTINUE` | Tiếp tục quá trình duyệt bình thường |
| `TERMINATE` | Dừng toàn bộ quá trình duyệt; không thăm tiếp |
| `SKIP_SUBTREE` | Khi trả từ `preVisitDirectory`, không duyệt cây con của thư mục đó |
| `SKIP_SIBLINGS` | Bỏ qua những mục ngang hàng chưa được thăm ở cùng cấp và các hậu duệ của chúng |

Chi tiết theo ngữ cảnh rất quan trọng:

- `SKIP_SUBTREE` chỉ có tác dụng thực chất ở **`preVisitDirectory`**; nếu trả từ `visitFile`, nơi không có cây con để duyệt, nó tương đương `CONTINUE`.
- `SKIP_SIBLINGS` có thể ngăn duyệt các mục còn lại dưới cùng một thư mục cha, nên không dùng chỉ để “bỏ qua tệp hiện tại”.
- Khi muốn bỏ qua **một thư mục và toàn bộ nội dung bên trong nhưng vẫn duyệt thư mục khác cùng cấp**, chọn `SKIP_SUBTREE` từ `preVisitDirectory`.
- `TERMINATE` kết thúc sớm; không phải tín hiệu lỗi tự động. Caller phải tự quyết định một cuộc duyệt dừng sớm là kết quả hợp lệ hay chưa hoàn chỉnh.
- Không trả `null`: kết quả callback phải là một giá trị `FileVisitResult` hợp lệ.

Ví dụ chính sách:

```text
Phát hiện thư mục cache            → SKIP_SUBTREE trong preVisitDirectory
Xử lý file thông thường thành công → CONTINUE trong visitFile
Không thể đọc mục nhưng cho phép bỏ qua → CONTINUE trong visitFileFailed
Gặp kết quả cần tìm và muốn ngừng  → TERMINATE
Kết thúc thư mục không có lỗi      → CONTINUE trong postVisitDirectory
```

**Thận trọng khi dùng `SKIP_SIBLINGS`:** “sibling nào chưa được duyệt” phụ thuộc thứ tự liệt kê của filesystem; không mặc định tên file có thứ tự chữ cái.

## 9. Chương trình Java 17+ chạy được: quan sát đúng thứ tự callback

Tạo tệp **`TreeCallbacksDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeCallbacksDemo {
    private static String label(Path root, Path path) {
        String relative = root.relativize(path).toString()
                .replace('\\', '/');
        return relative.isEmpty() ? "." : relative;
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("callback-demo-");
        Path sub = root.resolve("docs");
        Path note = sub.resolve("note.txt");

        try {
            Files.createDirectory(sub);
            Files.writeString(note, "Hello", StandardCharsets.UTF_8);

            FileVisitor<Path> visitor = new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    System.out.println("PRE " + label(root, dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    System.out.println("FILE " + label(root, file));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(
                        Path file, IOException exc) throws IOException {
                    System.out.println("FAIL " + label(root, file));
                    throw exc;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    System.out.println("POST " + label(root, dir));
                    return FileVisitResult.CONTINUE;
                }
            };

            Files.walkFileTree(root, visitor);
        } finally {
            Files.deleteIfExists(note);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TreeCallbacksDemo.java
java TreeCallbacksDemo
```

Đầu ra khi thao tác tạo/duyệt tệp tạm thành công:

```text
PRE .
PRE docs
FILE docs/note.txt
POST docs
POST .
```

Ví dụ cố ý dùng **một** thư mục con và **một** tệp để thứ tự không phụ thuộc việc sắp xếp các sibling. Đường dẫn thư mục tạm có tên ngẫu nhiên, nhưng hàm `label` chuyển về đường dẫn tương đối để stdout ổn định trên Windows và hệ điều hành dùng dấu phân cách `/`.

Ở chương trình này:

- `PRE .` là callback trước khi liệt kê thư mục gốc.
- `PRE docs` là callback trước khi đi vào `docs`.
- `FILE docs/note.txt` là lần thăm tệp.
- `POST docs` rồi `POST .` phản ánh việc trở ngược từ lá lên gốc.
- Không có `FAIL` vì mọi mục đều truy cập được.
- Khối `finally` chỉ xóa các đường dẫn **do chính chương trình tạo**. Nếu cleanup gặp lỗi, `IOException` vẫn có thể được ném; không áp dụng nguyên xi logic xóa này cho dữ liệu người dùng.

## 10. Chương trình chạy được: bỏ qua nguyên nhánh nhưng vẫn duyệt nhánh khác

`SKIP_SUBTREE` có hành vi dễ nhận thấy nhất khi thư mục bị bỏ qua có các tệp bên trong. Để tránh phụ thuộc thứ tự sibling, ví dụ này ghi lại các mục được thăm rồi in kết luận **sau khi duyệt**.

Tạo tệp **`SkipSubtreeDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashSet;
import java.util.Set;

public class SkipSubtreeDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("skip-demo-");
        Path keep = root.resolve("keep");
        Path skip = root.resolve("skip");
        Path visible = keep.resolve("visible.txt");
        Path hidden = skip.resolve("hidden.txt");

        try {
            Files.createDirectory(keep);
            Files.createDirectory(skip);
            Files.writeString(visible, "ok", StandardCharsets.UTF_8);
            Files.writeString(hidden, "ignored", StandardCharsets.UTF_8);

            Set<Path> entered = new HashSet<>();
            Set<Path> files = new HashSet<>();
            Set<Path> exited = new HashSet<>();

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    entered.add(dir);
                    return dir.equals(skip)
                            ? FileVisitResult.SKIP_SUBTREE
                            : FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    files.add(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    exited.add(dir);
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("entered skip=" + entered.contains(skip));
            System.out.println("visited hidden=" + files.contains(hidden));
            System.out.println("post skip=" + exited.contains(skip));
            System.out.println("visited visible=" + files.contains(visible));
            System.out.println("post root=" + exited.contains(root));
        } finally {
            Files.deleteIfExists(visible);
            Files.deleteIfExists(hidden);
            Files.deleteIfExists(keep);
            Files.deleteIfExists(skip);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SkipSubtreeDemo.java
java SkipSubtreeDemo
```

Đầu ra:

```text
entered skip=true
visited hidden=false
post skip=false
visited visible=true
post root=true
```

Các mục trong `skip` không được duyệt, còn `keep/visible.txt` vẫn được thăm. Vì `skip` đã bị loại trừ từ callback `preVisitDirectory`, chương trình không nhận `postVisitDirectory(skip, ...)`.

Không viết kiểm thử dựa trên việc `keep` hay `skip` xuất hiện trước: thứ tự liệt kê có thể khác giữa các hệ điều hành và filesystem.

## 11. Chương trình chạy được: `visitFileFailed` và chiến lược bỏ qua lỗi

Ví dụ dùng một đường dẫn **không tồn tại trong thư mục tạm vừa tạo** để mô phỏng việc không lấy được thuộc tính. Cách này không phải thay đổi phân quyền và không cần giả lập một filesystem hỏng.

Tạo tệp **`FileVisitFailureDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class FileVisitFailureDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("failure-demo-");
        Path missing = root.resolve("missing.txt");

        try {
            Files.walkFileTree(missing, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(
                        Path file, IOException exc) {
                    System.out.println("Failed: "
                            + file.getFileName());
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("Traversal returned");
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FileVisitFailureDemo.java
java FileVisitFailureDemo
```

Đầu ra với filesystem mặc định hỗ trợ thao tác thư mục tạm bình thường:

```text
Failed: missing.txt
Traversal returned
```

Vì `missing.txt` không tồn tại, bộ duyệt không thể đọc thuộc tính và gọi `visitFileFailed`. Callback trả `CONTINUE`, nên `walkFileTree` kết thúc mà **không ném lại lỗi**. Điều này không có nghĩa tệp đã được thăm thành công; ứng dụng có trách nhiệm báo cáo chính xác những mục đã bỏ qua.

Nếu callback dùng `throw exc;`, chương trình sẽ báo ngoại lệ cho caller. Trong hệ thống sản xuất, kiểu lỗi cụ thể có thể là `NoSuchFileException`, `AccessDeniedException`, `FileSystemLoopException` hoặc loại `IOException` khác tùy tình huống/provider.

## 12. Lỗi khi lặp thư mục và khác biệt với lỗi của code visitor

Một trường hợp khó hơn: thư mục **mở thành công** nhưng đọc danh sách các mục trong thư mục gặp lỗi giữa chừng. Khi đó `postVisitDirectory(dir, exc)` có thể nhận `exc != null`.

Ví dụ đoạn chính sách fail-fast:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw new IOException(
                "Lỗi khi duyệt các mục trong " + dir, exc);
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa** để đặt trong visitor. Vì rất khó mô phỏng một lỗi directory iterator đáng tin trên mọi filesystem, không đưa stdout cố định.

Ngược lại, nếu bên trong `visitFile` có code:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    processFile(file);  // có thể ném IOException
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa**: `processFile` là hàm ứng dụng, không phải API chuẩn của Java. Một `IOException` do `processFile` ném thường **thoát khỏi `walkFileTree`** thay vì tự động được chuyển sang `visitFileFailed`. Không nên dùng hai callback báo lỗi như một cơ chế “bắt mọi lỗi” thay cho quản lý ngoại lệ của ứng dụng.

Nếu ứng dụng muốn tiếp tục khi không đọc được nội dung **một file riêng**, hãy chủ động `try/catch` ngay trong `visitFile`, ghi nhận trạng thái lỗi và trả `CONTINUE` theo một chính sách đã xác định.

## 13. `maxDepth`, symbolic link và vòng lặp

### Giới hạn độ sâu

Overload `Files.walkFileTree(start, options, maxDepth, visitor)` cho phép đặt độ sâu tối đa. `start` có độ sâu 0. Ví dụ dùng `maxDepth = 1` sẽ không đi sâu vào nội dung của thư mục ở độ sâu 1.

Điểm tinh tế: những **thư mục gặp tại độ sâu tối đa có thể được chuyển tới `visitFile`**, vì quá trình duyệt không mở chúng như các thư mục sẽ tiếp tục đi xuống. Do đó nếu chỉ muốn đếm tệp thường, hãy kiểm tra `attrs.isRegularFile()` trong `visitFile`.

`maxDepth < 0` không hợp lệ. Khi cần duyệt không giới hạn thực tế, overload đơn giản dùng cách duyệt mặc định tương ứng.

### Symbolic link

Mặc định `walkFileTree` **không đi theo symbolic link**. Vì vậy symbolic link tới thư mục không mặc nhiên trở thành một nhánh con được duyệt. Có thể cấu hình:

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        10,
        visitor);
```

Đây là **đoạn minh họa**, yêu cầu `Path root`, `FileVisitor<Path> visitor`, import `Files` và `FileVisitOption`, và xử lý `IOException`.

Đi theo liên kết có thể dẫn tới **chu trình**, ví dụ A trỏ B rồi B trỏ A hoặc một thư mục con trỏ lại tổ tiên. Java có cơ chế phát hiện vòng lặp trong chế độ follow links; lỗi như `FileSystemLoopException` có thể được chuyển đến `visitFileFailed`. Không dùng `FOLLOW_LINKS` thiếu suy nghĩ cho thao tác xóa/sao chép dữ liệu quan trọng; cần quy định có xử lý bản thân link hay đích của nó.

### Cây có thể thay đổi giữa lúc duyệt

Filesystem không phải ảnh chụp bất biến: tệp có thể bị đổi tên, xóa, cấp quyền khác hoặc nội dung đổi trong khi đang duyệt. Thuộc tính `attrs` được lấy trong quá trình thăm và **có thể đã cũ** khi bạn xử lý nội dung tệp. Nếu phải xử lý dữ liệu có yêu cầu nhất quán nghiêm ngặt, cần snapshot, phối hợp quyền ghi hoặc quy trình kiểm chứng ở tầng ứng dụng.

## 14. Chọn đúng callback cho từng tác vụ

| Tác vụ | Callback thường phù hợp | Lý do |
| --- | --- | --- |
| Ghi log “vào thư mục” | `preVisitDirectory` | Trước khi gặp con |
| Loại trừ cả nhánh cache | `preVisitDirectory` với `SKIP_SUBTREE` | Không cần đi vào nhánh |
| Tạo cấu trúc thư mục đích khi copy | `preVisitDirectory` | Thư mục cha cần tồn tại trước con |
| Đếm file thường, tính tổng dung lượng | `visitFile` | Có `BasicFileAttributes` của mục |
| Đọc hoặc sao chép nội dung một tệp | `visitFile` | Có đường dẫn tệp cần xử lý |
| Ghi nhận file không truy cập được | `visitFileFailed` | Nhận nguyên nhân thất bại |
| Xử lý lỗi lặp danh sách thư mục | `postVisitDirectory` với `exc != null` | Lỗi xảy ra khi duyệt các mục con |
| Tổng hợp kết quả từ nhánh con | `postVisitDirectory` | Tất cả con đã được thăm theo nhánh |
| Xóa thư mục sau khi xóa hết con | `postVisitDirectory` | Hậu thứ tự |
| Dừng tìm kiếm khi đã thấy mục mong muốn | `visitFile` trả `TERMINATE` | Không cần tiếp tục toàn cây |

### Ví dụ xóa theo hậu thứ tự — chỉ là đoạn minh họa

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs)
            throws IOException {
        Files.delete(file);
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult postVisitDirectory(
            Path dir, IOException exc)
            throws IOException {
        if (exc != null) {
            throw exc;
        }
        Files.delete(dir);
        return FileVisitResult.CONTINUE;
    }
});
```

**Đây không phải chương trình độc lập**: cần `Path root`, các import và xử lý `IOException`. Đoạn code **xóa thật** mọi tệp/thư mục bên dưới `root` mà ứng dụng có quyền thao tác; chỉ dùng với cây dữ liệu do chính bạn tạo để kiểm thử hoặc có xác nhận rõ. Khác với xóa từ cha xuống (dễ gặp `DirectoryNotEmptyException`), hậu thứ tự cho phép xóa file và thư mục con trước khi xóa cha.

Với thư mục chứa dữ liệu quan trọng, phải xem xét symbolic link, phân quyền, thay đổi đồng thời, xử lý lỗi và khả năng khôi phục. `walkFileTree` không biến toàn bộ thao tác xóa thành transaction.

## 15. So sánh `Files.walkFileTree` với `Files.walk`

Cả hai đều giúp đi qua cây thư mục nhưng khác giao diện và cách xử lý lỗi:

| Đặc điểm | `Files.walkFileTree` | `Files.walk` |
| --- | --- | --- |
| API xử lý | Visitor với các callback rõ ràng | `Stream<Path>`, phối hợp `filter`/`map`/`forEach` |
| Trước/sau thư mục | Có `preVisitDirectory` và `postVisitDirectory` | Không có các callback tương đương trực tiếp |
| Lỗi khi duyệt | `visitFileFailed`, `postVisitDirectory(exc)`, `IOException` | Một số lỗi trong quá trình duyệt có thể xuất hiện dưới `UncheckedIOException` |
| Bỏ cả nhánh theo logic visitor | `SKIP_SUBTREE` | Không có một callback `preVisitDirectory` tương ứng để pruning |
| Đóng tài nguyên | API quản lý quá trình duyệt nội bộ | `Stream<Path>` cần `try-with-resources` để đóng |
| Khi phù hợp | Sao chép/xóa/tính kích thước cây, log vào–ra thư mục, xử lý lỗi có ngữ cảnh | Pipeline lọc/liệt kê đường dẫn |

Không dùng `Files.walk(root).filter(...)` với kỳ vọng filter một thư mục tự động ngăn hệ thống đi vào các mục con của nó; filter của Stream quyết định **các phần tử sau khi được phát ra**, không hoạt động như `SKIP_SUBTREE` của visitor.

Nếu tác vụ cần biết chính xác thời điểm trước/sau một thư mục, hoặc cần kiểm soát khi truy cập thất bại, `walkFileTree` thường dễ biểu đạt hơn.

## 16. Lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `preVisitDirectory` chạy sau khi thăm con | Tạo đích, tính trạng thái sai thời điểm | Hiểu đây là callback **trước** |
| Đếm mọi mục qua `visitFile` như file thường | Đếm cả symbolic link hoặc thư mục ở `maxDepth` | Kiểm tra `attrs.isRegularFile()` |
| Nghĩ `postVisitDirectory` luôn chạy | Không cleanup đủ khi bị skip/terminate/throw | Dùng `try/finally` cho cleanup bắt buộc |
| Bỏ qua `exc` trong `postVisitDirectory` | Báo duyệt đầy đủ dù thư mục có lỗi | Kiểm tra, ghi nhận hoặc ném lại lỗi |
| `visitFileFailed` trả `CONTINUE` nhưng báo thành công tuyệt đối | Che mất file/thư mục không đọc được | Thu thập danh sách lỗi và đánh dấu “chưa đầy đủ” |
| Cho rằng lỗi của `processFile` tự chuyển thành `visitFileFailed` | Không bắt được ngoại lệ ở đúng nơi | Xử lý checked exception trong visitor hoặc ngoài `walkFileTree` |
| Dùng `SKIP_SIBLINGS` để bỏ một thư mục nhưng vẫn muốn duyệt anh em của nó | Bỏ luôn các mục ngang hàng chưa được thăm | Dùng `SKIP_SUBTREE` từ `preVisitDirectory` |
| Giả định sibling luôn theo thứ tự tên | Kết quả khác giữa máy hoặc filesystem | Không dựa vào thứ tự, hoặc tự sắp xếp |
| Theo symbolic link mà không xét vòng lặp | Có thể gặp `FileSystemLoopException`, xử lý nhầm đích | Định nghĩa chính sách link và lỗi |
| Dùng `Files.walk` mà quên đóng Stream | Rò tài nguyên hệ thống | `try-with-resources` |
| Dùng visitor xóa dữ liệu nhưng bỏ qua root thật | Có thể xóa nhầm cả cây thư mục | Chỉ thao tác trên root đã xác minh và được phép |
| Coi mọi `IOException` là file không tồn tại | Bỏ sót lỗi quyền, thiết bị, link | Xem loại và nguyên nhân lỗi cụ thể |

## 17. Checklist thiết kế visitor và bài tự luyện

**Trước khi duyệt cây:**

- [ ] Chọn đúng `start`; tránh thao tác nhầm cây dữ liệu.
- [ ] Xác định mục tiêu: liệt kê, lọc, sao chép, tổng hợp hay xóa.
- [ ] Chọn quy tắc theo symbolic link và `maxDepth`.
- [ ] Quyết định callback nào cần override, callback nào dùng mặc định.
- [ ] Chọn `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS` hoặc `TERMINATE` theo ngữ nghĩa yêu cầu.
- [ ] Xác định xử lý khi truy cập một mục thất bại và khi lặp thư mục gặp lỗi.
- [ ] Tránh phụ thuộc thứ tự các sibling.
- [ ] Đảm bảo cleanup tài nguyên ứng dụng không chỉ dựa vào `postVisitDirectory`.

**Bài tự luyện 1 — thứ tự callback:** Tạo cây `root/a/x.txt` và `root/a/b/y.txt`, mỗi thư mục chỉ có một mục con, rồi in `PRE`, `FILE`, `POST`. Vẽ chính xác chuỗi callback theo chiều sâu và giải thích vì sao `POST a/b` xuất hiện trước `POST a`.

**Bài tự luyện 2 — loại trừ:** Thêm nhánh `root/cache/temp.txt` và cho `preVisitDirectory` trả `SKIP_SUBTREE` khi gặp `cache`. Kiểm tra rằng `temp.txt` không đi qua `visitFile` và `postVisitDirectory(cache, ...)` không được gọi, nhưng những nhánh khác vẫn được duyệt.

**Bài tự luyện 3 — lỗi:** Trong một thư mục tạm, gọi `Files.walkFileTree` cho đường dẫn không tồn tại. Thử hai phiên bản `visitFileFailed`: trả `CONTINUE` và `throw exc`. So sánh việc phương thức kết thúc bình thường với việc ném `IOException`.

**Bài tự luyện 4 — hậu thứ tự:** Với cây tạm có hai mức thư mục, hãy dùng `visitFile` để xóa file và `postVisitDirectory` để xóa thư mục. Vì sao xóa thư mục cha trước khi xóa nội dung có thể gây `DirectoryNotEmptyException`?

**Ghi nhớ:** `preVisitDirectory` chạy **trước** nội dung thư mục; `visitFile` xử lý mục được thăm như file; `visitFileFailed` báo **mục không thể truy cập**; `postVisitDirectory` chạy **sau** nội dung thư mục hoặc nhận lỗi khi lặp thư mục. `FileVisitResult` quyết định tiếp tục, bỏ nhánh, bỏ sibling hoặc dừng toàn bộ. Hiểu rõ thứ tự và ngoại lệ giúp duyệt cây an toàn, đúng và có thể kiểm thử trên Java 17+.