# Java 7 — Duyệt cây tệp: FileVisitor, SimpleFileVisitor và thứ tự callback

## Mục tiêu bài học

Khi thao tác với một thư mục chứa nhiều cấp, chỉ gọi `Files.list(...)` lên thư mục gốc không đủ để tìm toàn bộ tệp bên dưới. Java NIO.2 cung cấp `Files.walkFileTree(...)` cùng giao diện `FileVisitor<T>` và lớp tiện ích `SimpleFileVisitor<T>` để **duyệt theo chiều sâu (depth-first)** một cây thư mục, nhận callback mỗi khi bắt đầu một thư mục, gặp một tệp, đọc không được một entry hoặc kết thúc một thư mục.

Các API `java.nio.file.FileVisitor`, `SimpleFileVisitor`, `FileVisitResult` và `Files.walkFileTree` có từ **Java 7** và vẫn được dùng trên **Java 17+**. Chúng phù hợp cho bài toán liệt kê, kiểm kê, tìm tệp, tính toán thống kê, copy cấu trúc, xác minh nội dung hoặc xóa cây **khi thật sự có quyền và chủ ý**.

Bài này tập trung vào câu hỏi cốt lõi: **Callback nào được gọi, theo thứ tự nào, và những điều kiện nào khiến thứ tự thông thường thay đổi?**

Sau bài, bạn có thể:

1. Nắm đủ **bốn callback**: `preVisitDirectory`, `visitFile`, `visitFileFailed` và `postVisitDirectory`.
2. So sánh tự triển khai `FileVisitor<Path>` với kế thừa `SimpleFileVisitor<Path>`.
3. Mô tả chính xác quan hệ thứ tự: callback trước của một thư mục, các entry con và callback sau của thư mục đó.
4. Hiểu vì sao **thứ tự các mục cùng cấp không được bảo đảm**, dù traversal là depth-first.
5. Phân biệt callback xử lý lỗi khi **không đọc được entry** với `IOException` được ném từ chính callback.
6. Sử dụng đúng `FileVisitResult.CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS` và `TERMINATE`.
7. Hiểu việc trả `SKIP_SUBTREE` ở `preVisitDirectory` **không gọi `postVisitDirectory` cho thư mục bị skip**.
8. Đọc ý nghĩa của `BasicFileAttributes` và tham số `IOException exc` ở callback hậu duyệt.
9. Dùng overload `walkFileTree` với `maxDepth`, `FileVisitOption.FOLLOW_LINKS` và các giới hạn an toàn.
10. Viết test độc lập hệ điều hành, không so sánh thứ tự anh em vốn không được đặc tả.

**Special Note của module:** Chỉ sử dụng kiến thức và API còn áp dụng trên Java hiện nay. Ví dụ hoàn chỉnh được kiểm chứng bằng `javac --release 17` trên JDK hiện đại; những phương thức bổ sung sau Java 7 được ghi chú rõ khi xuất hiện.

## 1. Mô hình cây và callback

Giả sử có cây tệp đơn giản:

```text
root/
  inner/
    one.txt
```

Khi duyệt `root` theo chiều sâu, với mọi callback trả `CONTINUE` và không gặp lỗi, có thể hình dung:

```text
preVisitDirectory(root)
    preVisitDirectory(inner)
        visitFile(one.txt)
    postVisitDirectory(inner, null)
postVisitDirectory(root, null)
```

Bốn callback có ý nghĩa:

| Callback | Được gọi khi nào? | Tham số chính | Dùng để làm gì? |
| --- | --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi duyệt nội dung một directory mở được | Path directory, thuộc tính cơ bản | Khởi tạo state, tạo thư mục đích khi copy, quyết định skip |
| `visitFile(file, attrs)` | Với một entry được duyệt như file, kể cả một số entry không phải regular file | Path entry, thuộc tính cơ bản | Đếm, lọc, copy, kiểm tra, xử lý file |
| `visitFileFailed(file, exc)` | Không thể đọc thuộc tính entry hoặc không thể mở directory để duyệt | Path entry, lỗi `IOException` | Ghi nhận lỗi, retry/skip theo policy, hoặc propagate |
| `postVisitDirectory(dir, exc)` | Sau khi đã kết thúc duyệt nội dung directory đã được mở, kể cả kết thúc sớm trong một số trường hợp | Path directory, lỗi lặp directory có thể null | Hoàn tất tổng hợp, xóa directory sau khi xóa con, propagate lỗi |

**Không suy ra rằng cứ có `preVisitDirectory` thì chắc chắn có một `postVisitDirectory`.** Khi `preVisitDirectory` trả `SKIP_SUBTREE` hoặc `SKIP_SIBLINGS`, việc duyệt subtree bị bỏ qua và không gọi `postVisitDirectory` cho thư mục đó. Nếu callback ném exception hoặc trả `TERMINATE`, traversal cũng có thể kết thúc trước callback hậu duyệt.

### 1.1. Thứ tự depth-first khác thứ tự alphabet

`Files.walkFileTree` duyệt theo chiều sâu. Điều đó bảo đảm về **quan hệ cha–con**, không bảo đảm rằng `a.txt` phải xuất hiện trước `z.txt` hoặc directory `alpha` trước `beta`. Thứ tự entry cùng cấp phụ thuộc filesystem/provider và thời điểm liệt kê.

Ví dụ với cây:

```text
root/
  a.txt
  logs/
    app.log
  z.txt
```

Có thể gặp nhiều trace hợp lệ. Một trace có thể là:

```text
pre root
file a.txt
pre logs
file app.log
post logs
file z.txt
post root
```

Nhưng không được đặt test mặc định yêu cầu chính xác trace ấy trên mọi hệ thống. Thứ tự `a.txt`, `logs`, `z.txt` ở cùng cấp có thể khác. **Bất biến** là nếu đã đi vào `logs` thì `pre logs` phải đi trước các file con, và `post logs` sau khi kết thúc duyệt bên trong nó, trừ đường đi bị skip/terminate/error.

Nếu yêu cầu **thứ tự tên tăng dần**, `walkFileTree` không có một flag “sorted traversal”. Cần thiết kế thuật toán liệt kê và sắp xếp entry riêng, đồng thời quản lý tài nguyên và chi phí nếu directory chứa rất nhiều mục. Đừng cho rằng `SimpleFileVisitor` tự sắp xếp.

## 2. Hai cách định nghĩa visitor

### 2.1. `FileVisitor<T>` — giao diện đầy đủ

`FileVisitor<T>` là interface có **bốn phương thức trừu tượng**. Với cây filesystem dùng NIO.2, bạn thường sử dụng `FileVisitor<Path>`. Khi trực tiếp triển khai interface, lớp phải định nghĩa đủ:

```java
FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
        throws IOException;

FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
        throws IOException;

FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException;

FileVisitResult postVisitDirectory(Path dir, IOException exc)
        throws IOException;
```

Đây là **các chữ ký minh họa**, không phải một lớp Java hoàn chỉnh. Kiểu trả về `FileVisitResult` điều khiển việc tiếp tục, skip hoặc kết thúc. `throws IOException` cho phép callback chuyển lỗi file system ra caller của `Files.walkFileTree`.

Ưu điểm: buộc người triển khai **chủ động xác định hành vi của cả bốn tình huống**. Phù hợp khi cần một policy nghiêm ngặt cho lỗi I/O và thứ tự thao tác.

### 2.2. `SimpleFileVisitor<T>` — lớp có hành vi mặc định

`SimpleFileVisitor<T>` đã triển khai `FileVisitor<T>` và cung cấp mặc định:

- `preVisitDirectory(...)`: trả `CONTINUE`.
- `visitFile(...)`: trả `CONTINUE`.
- `visitFileFailed(...)`: ném lại chính `IOException` nhận được.
- `postVisitDirectory(dir, exc)`: trả `CONTINUE` khi `exc == null`; nếu `exc != null` thì ném lại lỗi ấy.

Vì vậy, nếu chỉ cần xử lý file, bạn có thể override **một** phương thức `visitFile` và kế thừa hành vi mặc định của ba phương thức còn lại. Đó là lợi ích chính của `SimpleFileVisitor`: **ít mã khung nhưng vẫn không bỏ qua lỗi I/O theo mặc định**.

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
        System.out.println(file.getFileName());
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là **mảnh minh họa** cần `root` kiểu `Path` và import `Files`, `SimpleFileVisitor`, `FileVisitResult`, `BasicFileAttributes`, `Path`. Nếu `walkFileTree` gặp lỗi I/O chưa xử lý, cần `throws IOException` hoặc catch ở caller.

**Đừng nhầm “Simple” với “silently ignore errors”.** Mặc định của `SimpleFileVisitor` vẫn propagate lỗi từ `visitFileFailed` và `postVisitDirectory`.

### 2.3. So sánh

| Tiêu chí | `FileVisitor<Path>` | `SimpleFileVisitor<Path>` |
| --- | --- | --- |
| Bản chất | Interface | Lớp triển khai interface |
| Phải viết bao nhiêu phương thức? | Đủ bốn | Chỉ override callback cần đổi |
| Mặc định khi không đọc được file | Không có mặc định: bạn phải viết | Ném lại `IOException` |
| Mặc định khi kết thúc directory có lỗi | Không có mặc định | Ném lại `IOException` |
| Mặc định khi visit bình thường | Do bạn quyết định | `CONTINUE` |
| Khi nên chọn | Policy tường minh cho tất cả callback | Visitor chỉ thêm một vài hành vi |
| Khả năng dùng trên Java hiện đại | Có | Có |

Không cần tạo một lớp con phức tạp khi chỉ đếm số tệp. Ngược lại, với thao tác thay đổi filesystem và xử lý lỗi nhiều loại, có thể đáng để code đầy đủ bốn callback và review policy rõ.

## 3. Chương trình A — Quan sát thứ tự callback trên cây chỉ có một nhánh

Để tránh kết quả không ổn định do thứ tự anh em, ví dụ chỉ tạo **một thư mục con và một tệp**. Khi không có cạnh tranh hay lỗi I/O, trace minh họa thể hiện thứ tự depth-first rõ ràng.

Lưu tệp **`CallbackOrderDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public final class CallbackOrderDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-order-");
        Path inner = root.resolve("inner");
        Path file = inner.resolve("one.txt");
        try {
            Files.createDirectory(inner);
            Files.createFile(file);

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                private String name(Path p) {
                    return p.equals(root) ? "root" : p.getFileName().toString();
                }

                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes a) {
                    System.out.println("pre:" + name(dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path p, BasicFileAttributes a) {
                    System.out.println("file:" + name(p));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException error) throws IOException {
                    if (error != null) throw error;
                    System.out.println("post:" + name(dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(
                        Path p, IOException error) throws IOException {
                    throw error;
                }
            });
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(inner);
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 CallbackOrderDemo.java
java CallbackOrderDemo
```

**Stdout đã xác minh:**

```text
pre:root
pre:inner
file:one.txt
post:inner
post:root
```

### 3.1. Vì sao `post` theo thứ tự ngược?

`postVisitDirectory` chỉ đến sau khi directory hiện tại đã xử lý xong các entry con. Với cây một nhánh:

- `root` bắt đầu trước.
- `inner` bắt đầu sau khi được gặp trong `root`.
- `one.txt` được visit khi đi sâu trong `inner`.
- `inner` hoàn tất trước `root`.
- `root` hoàn tất cuối cùng.

Đây là quy luật “**vào trước, ra sau**” của depth-first traversal. Nó hữu ích khi:

- Tạo cây đích khi copy: tạo directory trong `preVisitDirectory`.
- Tổng hợp số liệu từ các nhánh con: hoàn thiện trong `postVisitDirectory`.
- Xóa cây: xóa file con trong `visitFile`, xóa directory cha trong `postVisitDirectory`.

Ví dụ tạo tệp và thư mục trong directory tạm, không tác động thư mục của người dùng. Dùng `Files.deleteIfExists` ở `finally` vì các mục có thể đã được xóa trong một phần xử lý trước đó.

### 3.2. Không phải entry nào cũng có đủ bốn callback

Một **regular file đơn lẻ** được dùng làm root có thể chỉ kích hoạt `visitFile`. Một directory mở không được có thể đi vào `visitFileFailed` mà không có `preVisitDirectory`. Một directory bị skip có `pre` nhưng không có `post`. Do đó, không viết logic giả định “mỗi entry luôn có bốn callback”.

## 4. Chương trình B — Triển khai trực tiếp `FileVisitor<Path>`

Ví dụ đầy đủ này cho thấy sự khác nhau về API: tự viết `FileVisitor` đòi hỏi **cung cấp cả bốn phương thức**, dù không có lỗi trong lần chạy bình thường.

Lưu **`InterfaceVisitorDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public final class InterfaceVisitorDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-interface-");
        Path sub = root.resolve("sub");
        Path file = sub.resolve("a.txt");
        try {
            Files.createDirectory(sub);
            Files.createFile(file);
            int[] count = new int[4];

            FileVisitor<Path> visitor = new FileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path p, BasicFileAttributes a) {
                    count[0]++;
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path p, BasicFileAttributes a) {
                    count[1]++;
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(
                        Path p, IOException exc) throws IOException {
                    count[2]++;
                    throw exc;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path p, IOException exc) throws IOException {
                    count[3]++;
                    if (exc != null) throw exc;
                    return FileVisitResult.CONTINUE;
                }
            };

            Path result = Files.walkFileTree(root, visitor);
            System.out.println("rootReturned=" + result.equals(root));
            System.out.println("pre=" + count[0]);
            System.out.println("visit=" + count[1]);
            System.out.println("failed=" + count[2]);
            System.out.println("post=" + count[3]);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InterfaceVisitorDemo.java
java InterfaceVisitorDemo
```

**Stdout chính xác:**

```text
rootReturned=true
pre=2
visit=1
failed=0
post=2
```

### 4.1. Đọc kết quả

- `rootReturned=true`: overload `Files.walkFileTree(start, visitor)` trả về chính `start` khi hoàn tất.
- `pre=2`: hai directory `root` và `sub` được mở, nên hai callback trước.
- `visit=1`: một regular file `a.txt`.
- `failed=0`: không có entry nào gặp lỗi đọc thuộc tính/mở directory trong test.
- `post=2`: cả hai directory đều hoàn tất bình thường, không bị skip.

Đừng áp đặt `preCount == postCount` như invariant **mọi lúc**. Nó chỉ đúng trong trường hợp traversal diễn ra bình thường, không skip, terminate hoặc ngoại lệ.

### 4.2. Dùng đúng `BasicFileAttributes`

Callback `visitFile(file, attrs)` nhận sẵn `BasicFileAttributes` để biết những thông tin cơ bản đã đọc được, ví dụ:

```java
boolean regular = attrs.isRegularFile();
boolean directory = attrs.isDirectory();
boolean link = attrs.isSymbolicLink();
long size = attrs.size();
```

Đây là **mảnh minh họa** trong callback có `attrs` kiểu `BasicFileAttributes`. Không cần gọi lại `Files.readAttributes` cho mỗi entry chỉ để lấy những thông tin đã có trong `attrs`. Lưu ý attributes là quan sát tại một thời điểm; nếu filesystem thay đổi đồng thời thì thông tin ấy không phải khóa nhận dạng bất biến.

## 5. `preVisitDirectory` và quyết định có đi vào thư mục hay không

Callback:

```java
FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException;
```

được gọi **trước khi** liệt kê và đi vào entries con của directory đã mở được.

Các tác vụ hợp lý đặt ở đây:

- Ghi nhận bắt đầu một nhánh.
- Đếm số directory được duyệt.
- Chuẩn bị directory tương ứng ở đích khi copy.
- Kiểm tra điều kiện bỏ qua thư mục như cache hoặc build outputs.
- Đặt một trạng thái gắn với nhánh, sẽ được kết thúc trong `postVisitDirectory` nếu nhánh thật sự được duyệt.

Nếu trả `CONTINUE`, traversal tiếp tục với entries bên trong. Nếu trả `SKIP_SUBTREE`, không duyệt children của directory ấy, **và không gọi `postVisitDirectory` cho chính nó**. Nếu trả `SKIP_SIBLINGS`, cũng không đi vào subtree, đồng thời yêu cầu bỏ qua các mục cùng cấp còn lại.

### 5.1. Đừng đặt cleanup bắt buộc trong `post` nếu đã cho phép skip

Nếu bạn mở một resource trong `preVisitDirectory` rồi return `SKIP_SUBTREE`, không nên chờ `postVisitDirectory` đóng resource ấy, vì `post` cho directory bị skip sẽ không được gọi. Hoặc phải quyết định skip trước khi mở resource, hoặc tự cleanup ngay trước return, hoặc quản lý vòng đời theo một cấu trúc riêng.

Đây là một lỗi thực tế thường bị che bởi test chỉ dùng `CONTINUE`.

## 6. Chương trình C — `SKIP_SUBTREE` không gọi `post` của nhánh bị skip

Ví dụ tạo hai directory cùng cấp: `blocked` và `visible`. Thứ tự provider duyệt hai directory là bất kỳ; chương trình **đếm callback**, không in trace thứ tự anh em, nên output không phụ thuộc việc directory nào xuất hiện trước.

Lưu **`SkipSubtreeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public final class SkipSubtreeDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-skip-");
        Path blocked = root.resolve("blocked");
        Path visible = root.resolve("visible");
        Path hiddenFile = blocked.resolve("secret.txt");
        Path visibleFile = visible.resolve("public.txt");
        try {
            Files.createDirectory(blocked);
            Files.createDirectory(visible);
            Files.createFile(hiddenFile);
            Files.createFile(visibleFile);
            int[] count = new int[4];

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes a) {
                    count[0]++;
                    if (dir.equals(blocked)) {
                        count[3]++;
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path p, BasicFileAttributes a) {
                    count[1]++;
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path p, IOException exc) throws IOException {
                    if (exc != null) throw exc;
                    count[2]++;
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("pre=" + count[0]);
            System.out.println("files=" + count[1]);
            System.out.println("post=" + count[2]);
            System.out.println("skippedDirectories=" + count[3]);
            System.out.println("hiddenFileStillExists=" +
                    Files.isRegularFile(hiddenFile));
        } finally {
            Files.deleteIfExists(hiddenFile);
            Files.deleteIfExists(visibleFile);
            Files.deleteIfExists(blocked);
            Files.deleteIfExists(visible);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SkipSubtreeDemo.java
java SkipSubtreeDemo
```

**Stdout đã kiểm chứng:**

```text
pre=3
files=1
post=2
skippedDirectories=1
hiddenFileStillExists=true
```

### 6.1. Vì sao 3 `pre` nhưng chỉ 2 `post`?

- `pre=3`: root, blocked và visible đều được gặp.
- `preVisitDirectory(blocked)` trả `SKIP_SUBTREE`: không duyệt `secret.txt`.
- `visible` vẫn được duyệt; `public.txt` tạo ra một `visitFile`.
- `post=2`: callback sau chỉ đến với `visible` và root. **Không có `postVisitDirectory(blocked)`**.
- `hiddenFileStillExists=true`: bỏ qua traversal không xóa file. `SKIP_SUBTREE` **không phải API xóa**.

Điểm thiết kế quan trọng: thuật toán phải xử lý trường hợp “đã gọi pre nhưng không gọi post” nếu nó dùng callback để quản lý state.

## 7. `visitFile`: mọi entry được xử lý dưới dạng file

Chữ ký:

```java
FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException;
```

Nó thường được gọi cho regular files, nhưng **không phải chỉ regular file**. Theo hợp đồng `walkFileTree`:

- Khi một entry được đọc thuộc tính và **không được nhận diện là directory để đi vào**, callback `visitFile` được gọi.
- Symbolic link được xử lý như entry mà không theo target khi không bật `FOLLOW_LINKS`.
- Khi đụng **giới hạn `maxDepth`**, một directory ở mức giới hạn được đưa tới `visitFile` thay vì `preVisitDirectory`.
- Các loại entry khác (không phải regular file) cũng có thể được visit theo cách này, tùy provider.

Do đó, tên phương thức “visitFile” **không tự đảm bảo `attrs.isRegularFile()==true`**.

Nếu ứng dụng chỉ muốn xử lý regular file:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
        throws IOException {
    if (attrs.isRegularFile()) {
        // Chỉ xử lý regular file theo yêu cầu nghiệp vụ.
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **mảnh minh họa** cần đặt trong lớp visitor. Nó kiểm tra đúng loại entry thay vì dựa vào tên callback.

### 7.1. Không đoán tên bằng phần mở rộng

`file.toString().endsWith(".txt")` chỉ kiểm tra chuỗi tên, không kiểm tra loại mục hoặc nội dung tệp. Nếu cần chỉ các regular files thuộc dạng `.txt`, kết hợp `attrs.isRegularFile()` với kiểm tra filename/format/charset theo nhu cầu. Symlink, file đặc biệt và directory có thể có tên trông giống file.

### 7.2. Chú ý công việc làm thay đổi filesystem trong callback

Khi `visitFile` xóa, di chuyển hoặc sửa entry trong một cây đang được duyệt, traversal không trở thành một snapshot nhất quán. Việc xử lý có thể ảnh hưởng các mục chưa visit hoặc kết quả lần sau. Hãy có chính sách rõ, giới hạn phạm vi và test trên file tạm; tránh tự giả định các entry chưa duyệt là bất biến.

## 8. `postVisitDirectory`: kết thúc nhánh và tham số `exc`

Chữ ký:

```java
FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException;
```

Hàm này được gọi **sau khi directory đã được duyệt** và các mục con của nó đã được xử lý, hoặc khi quá trình lặp nội dung directory **kết thúc sớm** trong một số trường hợp.

Ý nghĩa của `exc`:

- `exc == null`: không có lỗi I/O từ bước iteration của directory được chuyển vào callback. Thư mục có thể đã được duyệt hoàn toàn, hoặc iteration kết thúc sớm do một kết quả như `SKIP_SIBLINGS`.
- `exc != null`: có lỗi I/O khiến quá trình lặp entries kết thúc sớm; caller cần xử lý rõ, thường bằng cách `throw exc;`.
- `exc` **không phải** một danh sách tổng hợp mọi lỗi đã từng xảy ra ở các file con. Nếu `visitFileFailed` tự ghi log và trả `CONTINUE`, một số lỗi con đã được xử lý riêng không nhất thiết xuất hiện ở `postVisitDirectory`.

### 8.1. Mẫu callback hậu duyệt đúng với lỗi

```java
@Override
public FileVisitResult postVisitDirectory(Path dir, IOException exc)
        throws IOException {
    if (exc != null) {
        throw exc;
    }
    // Ví dụ: hoàn tất số liệu hoặc xóa directory rỗng đã được cấp phép.
    return FileVisitResult.CONTINUE;
}
```

Đây là **mảnh minh họa**. Đừng bỏ qua `exc` và luôn trả `CONTINUE` nếu yêu cầu nghiệp vụ cần phát hiện traversal chưa đầy đủ.

### 8.2. Dùng `post` để xóa cây theo thứ tự đúng

Với một directory cần xóa:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
        throws IOException {
    Files.delete(file);
    return FileVisitResult.CONTINUE;
}

@Override
public FileVisitResult postVisitDirectory(Path dir, IOException exc)
        throws IOException {
    if (exc != null) throw exc;
    Files.delete(dir);
    return FileVisitResult.CONTINUE;
}
```

Đây là **hai callback minh họa**, không phải chương trình độc lập. Chỉ dùng với **cây do ứng dụng sở hữu và được ủy quyền xóa**. Directory phải được xóa **sau** file/dir con; ngược thứ tự sẽ dễ gặp `DirectoryNotEmptyException`.

**Không tự động bật `FOLLOW_LINKS` khi xóa cây**, bởi target của symlink có thể nằm ngoài phạm vi đã cho phép. Cũng không coi `walkFileTree` như transaction xóa nguyên tử: lỗi giữa chừng có thể để lại một phần cây.

## 9. `visitFileFailed`: entry không được truy cập/đọc thuộc tính

Chữ ký:

```java
FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException;
```

Callback này được gọi khi walker **không đọc được BasicFileAttributes**, hoặc với một directory **không thể mở để duyệt**, cùng những trường hợp lỗi truy cập liên quan được Java API mô tả.

Điểm rất quan trọng:

- Nếu **walker** không truy cập được entry, `visitFileFailed` có thể được gọi với nguyên nhân `IOException`.
- Nếu **chính code trong `visitFile` ném `IOException`**, walker **không hứa tự chuyển lỗi đó sang `visitFileFailed`**. Thay vào đó, exception do visitor ném thường được truyền ra `Files.walkFileTree`, và traversal chấm dứt.
- Một `IOException` ở lúc **lặp nội dung directory sau khi mở** có thể được truyền dưới dạng `exc` vào `postVisitDirectory`.
- Nếu `visitFileFailed` **trả `CONTINUE`**, traversal có thể đi tiếp theo policy; nếu nó **ném lại `exc`**, traversal dừng và lỗi đến caller.

### 9.1. Mặc định của `SimpleFileVisitor` là propagate lỗi

`SimpleFileVisitor.visitFileFailed` mặc định ném lại lỗi I/O. `SimpleFileVisitor.postVisitDirectory` cũng ném lỗi lặp directory nếu `exc != null`. Do đó, với visitor chỉ override `visitFile`, các lỗi filesystem không bị bỏ qua âm thầm theo mặc định.

### 9.2. Kiểm tra thiếu file đầu vào

Ví dụ đặc biệt hữu ích: bắt đầu traversal tại một `Path` **không tồn tại**. Trên provider mặc định Windows được thử, walker gọi `visitFileFailed` với `NoSuchFileException`. Còn khi dùng `SimpleFileVisitor` mặc định, exception ấy được rethrow tới caller.

## 10. Chương trình D — Xác minh `visitFileFailed` và mặc định của `SimpleFileVisitor`

Lưu **`VisitFailureDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public final class VisitFailureDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-failed-");
        Path missing = root.resolve("missing.txt");
        try {
            int[] counts = new int[3];
            Files.walkFileTree(missing, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(
                        Path path, IOException exc) {
                    counts[0]++;
                    System.out.println("failureType=" +
                            exc.getClass().getSimpleName());
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult preVisitDirectory(
                        Path path, BasicFileAttributes attrs) {
                    counts[1]++;
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path path, IOException exc) {
                    counts[2]++;
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("failedCount=" + counts[0]);
            System.out.println("preCount=" + counts[1]);
            System.out.println("postCount=" + counts[2]);

            try {
                Files.walkFileTree(missing, new SimpleFileVisitor<Path>() {});
                System.out.println("defaultThrows=unexpected");
            } catch (NoSuchFileException ex) {
                System.out.println("defaultThrows=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 VisitFailureDemo.java
java VisitFailureDemo
```

**Stdout trên Windows/JDK kiểm thử:**

```text
failureType=NoSuchFileException
failedCount=1
preCount=0
postCount=0
defaultThrows=NoSuchFileException
```

### 10.1. Phân tích

- `missing.txt` chưa hề được tạo.
- Lần traversal đầu, visitor override `visitFileFailed` và trả `CONTINUE`, nên caller không nhận exception từ callback này.
- Không có một directory được mở và đi vào trong lần duyệt, nên `preCount=0` và `postCount=0`.
- Lần traversal thứ hai dùng `new SimpleFileVisitor<Path>() {}` — giữ nguyên mặc định; lỗi thiếu file được ném ra.
- `NoSuchFileException` ở ví dụ là subtype xảy ra trên filesystem thử, không phải tên exception duy nhất được cam kết cho **mọi provider**.

**Trong code thực:** Nếu cần tiếp tục khi một file không đọc được, override `visitFileFailed` và quyết định policy, ví dụ log file, thu thập lỗi, trả `CONTINUE`. Đừng tự biến mọi lỗi access-denied thành “không có tệp” hoặc bỏ qua khi kết quả phải đầy đủ.

## 11. Callback tự ném IOException thì điều gì xảy ra?

Trong một visitor, bạn có thể ném `IOException` trực tiếp vì logic ứng dụng:

```java
@Override
public FileVisitResult visitFile(Path path, BasicFileAttributes attrs)
        throws IOException {
    throw new IOException("visitor failed");
}
```

Đây là **mảnh minh họa**. Theo hợp đồng `Files.walkFileTree`, khi một callback ném `IOException` chưa được xử lý, traversal **chấm dứt**, và lỗi được propagate tới caller. **Đừng giả định `visitFileFailed` sẽ được gọi để bắt lỗi do chính `visitFile` ném.**

### 11.1. Chương trình E — Callback exception làm dừng traversal

Lưu **`VisitorExceptionDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public final class VisitorExceptionDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-throw-");
        Path file = root.resolve("a.txt");
        int[] callbacks = {0, 0, 0};
        try {
            Files.createFile(file);
            try {
                Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult preVisitDirectory(
                            Path dir, BasicFileAttributes attrs) {
                        callbacks[0]++;
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFile(
                            Path p, BasicFileAttributes attrs)
                            throws IOException {
                        callbacks[1]++;
                        throw new IOException("visitor failed");
                    }

                    @Override
                    public FileVisitResult postVisitDirectory(
                            Path dir, IOException exc) {
                        callbacks[2]++;
                        return FileVisitResult.CONTINUE;
                    }
                });
            } catch (IOException ex) {
                System.out.println("propagated=" + ex.getMessage());
            }

            System.out.println("pre=" + callbacks[0]);
            System.out.println("visit=" + callbacks[1]);
            System.out.println("post=" + callbacks[2]);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 VisitorExceptionDemo.java
java VisitorExceptionDemo
```

**Stdout:**

```text
propagated=visitor failed
pre=1
visit=1
post=0
```

### 11.2. Bài học về callback pairing

- `pre=1`: walker đã mở directory `root`.
- `visit=1`: nó đã gặp `a.txt`.
- `visitFile` **ném** `IOException("visitor failed")`.
- Lỗi truyền ra ngoài và walker dừng. `postVisitDirectory(root)` **không được gọi**, nên `post=0`.

Đây là lý do không được đặt công việc cleanup quan trọng **chỉ** trong `postVisitDirectory` mà không có phương án khi callback trước đó ném lỗi hoặc khi traversal bị terminate.

## 12. Bốn giá trị điều khiển `FileVisitResult`

Mọi callback `FileVisitor` trả một giá trị **không null** thuộc `FileVisitResult`:

| Giá trị | Ngữ nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `CONTINUE` | Tiếp tục traversal | Khi trả ở `preVisitDirectory`, sẽ đi vào entries con |
| `SKIP_SUBTREE` | Bỏ qua các entry bên trong directory hiện tại | **Chỉ có ý nghĩa riêng khi trả từ `preVisitDirectory`**; nếu trả từ callback khác thì tương đương `CONTINUE` |
| `SKIP_SIBLINGS` | Bỏ qua các entry **cùng cấp** còn lại với entry hiện tại | Nếu trả từ `preVisitDirectory` thì **cũng** bỏ subtree và không gọi `postVisitDirectory` cho directory đó |
| `TERMINATE` | Dừng toàn bộ quá trình duyệt | Không bảo đảm có callback hậu duyệt cho các directory đã đi vào |

### 12.1. `SKIP_SUBTREE` không đồng nghĩa `SKIP_SIBLINGS`

Giả sử:

```text
root/
  blocked/
    secret.txt
  visible/
    public.txt
```

Khi `preVisitDirectory(blocked)` trả `SKIP_SUBTREE`, **chỉ** nhánh `blocked` không đi sâu. Nhánh `visible` vẫn có thể được duyệt.

Nếu cùng callback trả `SKIP_SIBLINGS`, không chỉ nhánh `blocked` bị bỏ qua mà còn các siblings chưa được thăm ở cấp cha. Vì thứ tự siblings không được bảo đảm, việc chọn nhánh nào “tình cờ đến trước” có thể ảnh hưởng kết quả.

### 12.2. `SKIP_SIBLINGS` từ `visitFile` có nghĩa gì?

Nó yêu cầu bỏ qua các file/directory cùng cấp **chưa được thăm** với file hiện tại. Với directory cha đã mở, callback `postVisitDirectory` của cha vẫn có thể được gọi khi iterator được kết thúc sớm. Đừng viết logic tưởng SKIP_SIBLINGS luôn ngăn **mọi** `postVisitDirectory`.

### 12.3. `TERMINATE` dừng toàn bộ

`TERMINATE` không chỉ bỏ một nhánh hoặc siblings. Nó chấm dứt tree walk. Cơ chế này phù hợp khi bạn đã tìm được mục tiêu và không cần tiếp tục duyệt; tuy nhiên nếu đang giữ tài nguyên trong visitor, cần cleanup bằng control flow bảo đảm thay vì đợi các callback hậu duyệt chưa chắc xuất hiện.

### 12.4. Trả `null` là lỗi

Java API quy định khi một phương thức visitor trả `null`, `Files.walkFileTree` ném `NullPointerException`. Luôn trả một giá trị `FileVisitResult` hợp lệ; không dùng `null` để biểu thị “không có quyết định”.

## 13. Chương trình F — `SKIP_SIBLINGS` và `TERMINATE`

Ví dụ tạo hai directory cùng cấp, nhưng **chỉ in số lần gọi**, không dựa vào directory nào được provider duyệt trước.

Lưu **`SkipAndTerminateDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public final class SkipAndTerminateDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-control-");
        Path a = root.resolve("a");
        Path b = root.resolve("b");
        try {
            Files.createDirectory(a);
            Files.createDirectory(b);
            int[] skip = {0, 0};

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    skip[0]++;
                    return dir.equals(root)
                            ? FileVisitResult.CONTINUE
                            : FileVisitResult.SKIP_SIBLINGS;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) throw exc;
                    skip[1]++;
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("skipPre=" + skip[0]);
            System.out.println("skipPost=" + skip[1]);

            int[] terminate = {0, 0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    terminate[0]++;
                    return FileVisitResult.TERMINATE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) {
                    terminate[1]++;
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("terminatePre=" + terminate[0]);
            System.out.println("terminatePost=" + terminate[1]);
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SkipAndTerminateDemo.java
java SkipAndTerminateDemo
```

**Stdout đúng:**

```text
skipPre=2
skipPost=1
terminatePre=1
terminatePost=0
```

### 13.1. Phân tích `SKIP_SIBLINGS`

- `skipPre=2`: walker vào root và vào **một** trong hai directory con.
- Callback `preVisitDirectory` của directory con đầu tiên gặp được trả `SKIP_SIBLINGS`.
- Subtree của directory ấy bị bỏ qua, và sibling directory còn lại cũng không được visit.
- `skipPost=1`: chỉ có `postVisitDirectory(root)` được gọi; không gọi post cho directory con vừa skip.

Không cần biết entry `a` hay `b` được duyệt trước để xác minh contract. Đây là cách viết test thích hợp khi thứ tự siblings không được bảo đảm.

### 13.2. Phân tích `TERMINATE`

- Lần walk thứ hai: callback đầu tiên là `preVisitDirectory(root)`.
- Trả `TERMINATE` ngay lập tức.
- Không có callback hậu duyệt cho root, nên `terminatePost=0`.

**Không đặt một lời hứa “post luôn chạy khi pre đã chạy” vào thuật toán cleanup.** Đây là ca phản chứng rất nhỏ, dễ chạy trên mọi filesystem thông thường.

## 14. Giới hạn độ sâu: directory ở `maxDepth` có thể gọi `visitFile`

Overload đầy đủ:

```java
Files.walkFileTree(
        start,
        options,
        maxDepth,
        visitor);
```

Trong đó:

- `start`: path bắt đầu, bản thân start có độ sâu **0** trong traversal.
- `options`: `Set<FileVisitOption>`, ví dụ `EnumSet.noneOf(FileVisitOption.class)` hoặc `EnumSet.of(FileVisitOption.FOLLOW_LINKS)`.
- `maxDepth`: giới hạn số cấp directory được đi sâu; phải không âm.
- `visitor`: object thực hiện bốn callbacks.

**Ngữ nghĩa dễ sai:** Với `maxDepth=0` và `start` là directory, walker xử lý start bằng `visitFile` thay vì gọi `preVisitDirectory`. Tại một cấp đạt giới hạn, directory được visit giống file ở mức callback vì walker **không mở để duyệt sâu**.

Điều này có nghĩa bạn không nên viết `visitFile` theo giả định mọi `Path` tại callback đó đều có `attrs.isRegularFile()==true`.

### 14.1. Chương trình G — `MaxDepthDemo.java`

Lưu:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public final class MaxDepthDemo {
    private static int[] count(Path root, int depth) throws IOException {
        int[] result = new int[3];
        Files.walkFileTree(
                root,
                EnumSet.noneOf(FileVisitOption.class),
                depth,
                new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult preVisitDirectory(
                            Path p, BasicFileAttributes attrs) {
                        result[0]++;
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFile(
                            Path p, BasicFileAttributes attrs) {
                        result[1]++;
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult postVisitDirectory(
                            Path p, IOException exc) throws IOException {
                        if (exc != null) throw exc;
                        result[2]++;
                        return FileVisitResult.CONTINUE;
                    }
                });
        return result;
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("visitor-depth-");
        Path child = root.resolve("sub");
        Path file = child.resolve("a.txt");
        try {
            Files.createDirectory(child);
            Files.createFile(file);
            for (int depth = 0; depth <= 2; depth++) {
                int[] n = count(root, depth);
                System.out.println("depth=" + depth +
                        " pre=" + n[0] +
                        " file=" + n[1] +
                        " post=" + n[2]);
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MaxDepthDemo.java
java MaxDepthDemo
```

**Stdout chính xác:**

```text
depth=0 pre=0 file=1 post=0
depth=1 pre=1 file=1 post=1
depth=2 pre=2 file=1 post=2
```

### 14.2. Đọc từng mức

| `maxDepth` | Cách walker xử lý | Số `pre` | Số `visitFile` | Số `post` |
| --- | --- | ---: | ---: | ---: |
| 0 | Start là directory nhưng ở độ sâu tối đa, nên được đưa tới `visitFile` | 0 | 1 | 0 |
| 1 | Root được mở; `sub` nằm ở giới hạn và được đưa tới `visitFile` | 1 | 1 | 1 |
| 2 | Root + `sub` được mở; `a.txt` được visit như regular file | 2 | 1 | 2 |

Kết quả trên giúp bạn tránh lỗi thống kê “số file = số lần `visitFile`”, vì ở những độ sâu bị chặn, `visitFile` có thể nhận **directory**. Nếu cần đếm **regular file**, kiểm tra `attrs.isRegularFile()` trong callback.

### 14.3. Khi nào giới hạn depth hữu ích?

- Chỉ cần hiển thị vài cấp đầu của cây.
- Đảm bảo một công cụ kiểm kê không đi xuống vô hạn trong cây lớn.
- Tránh traversal vào những directory sâu không thuộc mục tiêu.
- Kết hợp policy giới hạn depth với số file tối đa và quyền truy cập.

Đừng coi `maxDepth` như cơ chế bảo mật duy nhất. Symlink, mount, concurrency và quyền filesystem vẫn cần được đánh giá theo yêu cầu ứng dụng.

## 15. Symbolic link, `FOLLOW_LINKS` và lỗi vòng lặp

Overload đơn giản:

```java
Files.walkFileTree(start, visitor);
```

theo hợp đồng tương đương với:

```java
Files.walkFileTree(
        start,
        EnumSet.noneOf(FileVisitOption.class),
        Integer.MAX_VALUE,
        visitor);
```

Tức là **mặc định không đi theo symbolic links**, và có thể đi sâu toàn bộ cây. Các đoạn trên là mảnh minh họa với `start` và `visitor` đã được tạo.

### 15.1. Không follow links theo mặc định

Nếu một directory chứa symbolic link trỏ tới directory khác, walker mặc định **không tự đi vào cây target** qua link ấy. Symbolic link là một entry được xử lý theo thuộc tính của chính link trong quá trình traversal.

Đây là mặc định hữu ích khi bạn chỉ muốn khảo sát hoặc xóa cây thuộc phạm vi của một directory. Nó giúp giảm nguy cơ “theo link ra ngoài scope”, nhưng **không đủ thành một security boundary hoàn chỉnh** nếu một actor khác có thể thay các entry hoặc directory trong lúc traversal.

### 15.2. Chủ động bật `FOLLOW_LINKS`

```java
Files.walkFileTree(
        start,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
```

Đây là mảnh minh họa, cần import `EnumSet` và `FileVisitOption`. Chỉ bật khi yêu cầu nghiệp vụ **thực sự cần đi vào target của symbolic links** và bạn đã cân nhắc:

- Target có thể nằm ngoài base/root logic mong muốn.
- Có thể dẫn đến lặp đi lặp lại qua links giữa directories.
- File target có thể biến mất hoặc thiếu quyền truy cập.
- Chỉ số lượng entry và `maxDepth` có thể chưa đủ bảo vệ tài nguyên của ứng dụng.
- Nếu callback thực hiện xóa/copy/ghi file, hệ quả theo link có thể rất khác so với chỉ kiểm kê.

### 15.3. Chu trình link và `FileSystemLoopException`

Khi `FOLLOW_LINKS` bật, `walkFileTree` theo dõi những directory đã đi qua để phát hiện chu trình do một link trỏ ngược về ancestor. Khi phát hiện loop, Java có thể chuyển `FileSystemLoopException` đến `visitFileFailed`.

Nếu bạn sử dụng `SimpleFileVisitor` mặc định, lỗi này sẽ được ném ra. Nếu muốn bỏ qua một loop để tiếp tục, bạn cần quyết định policy ở `visitFileFailed`, không được cố đếm loop như file bình thường mà không xét an toàn.

### 15.4. Vì sao ví dụ chính không tạo symlink?

Trên Windows, việc tạo symbolic link có thể phụ thuộc quyền, chế độ hệ thống hoặc cấu hình máy; trên các provider khác cũng có hạn chế riêng. Những chương trình runnable của bài ưu tiên chạy ổn định với temporary files **không yêu cầu đặc quyền tạo symlink**. Test về `FOLLOW_LINKS`/loop nên là bộ test **có điều kiện** trên các môi trường hỗ trợ, với cleanup và giới hạn phạm vi rõ.

## 16. Bảng quyết định khi trả `FileVisitResult`

| Mục tiêu | Callback thường chọn | Giá trị trả về | Hệ quả |
| --- | --- | --- | --- |
| Duyệt toàn cây bình thường | Tất cả callback thành công | `CONTINUE` | Đi tiếp theo chiều sâu |
| Bỏ qua thư mục cache/build | `preVisitDirectory` | `SKIP_SUBTREE` | Không đi vào con, không post thư mục bị skip |
| Không xử lý các entry cùng cấp còn lại | `preVisitDirectory` hoặc `visitFile` | `SKIP_SIBLINGS` | Bỏ các siblings chưa visit, và bỏ subtree nếu trả từ pre |
| Đã tìm thấy mục tiêu cần tìm | `visitFile` | `TERMINATE` | Dừng toàn bộ traversal |
| Không đọc được file nhưng được phép bỏ qua | `visitFileFailed` | `CONTINUE` | Tiếp tục theo policy; cần báo lỗi nếu kết quả không đầy đủ |
| Lỗi phải làm tác vụ thất bại | `visitFileFailed` hoặc `postVisitDirectory` | `throw exc` | Dừng traversal, caller nhận IOException |
| Tạo thư mục đích trước khi copy con | `preVisitDirectory` | `CONTINUE` | Bảo đảm directory đích đã sẵn sàng |
| Xóa directory sau khi xóa con | `postVisitDirectory` | `CONTINUE` sau `Files.delete(dir)` | Directory được xóa sau các entry bên dưới |
| Chỉ xử lý depth nông | Overload `walkFileTree` | `maxDepth` | Entry directory tại biên có thể đi vào `visitFile` |

### 16.1. “Không xử lý tiếp” có nhiều nghĩa

Không trộn ba lựa chọn:

- `SKIP_SUBTREE`: bỏ **con của directory đang ở pre**, nhưng vẫn tiếp tục siblings.
- `SKIP_SIBLINGS`: bỏ **các mục cùng cấp còn lại**; nếu ở pre thì cũng bỏ cả subtree của directory hiện tại.
- `TERMINATE`: dừng **toàn bộ** walk.

Một bug phổ biến là dùng `SKIP_SUBTREE` khi đã tìm thấy mục tiêu trong `visitFile`, rồi mong walk dừng. Java API quy định `SKIP_SUBTREE` từ callback khác `preVisitDirectory` tương đương `CONTINUE`. Muốn dừng hoàn toàn, hãy trả `TERMINATE`.

## 17. Không có bảo đảm cân bằng callback ở mọi trường hợp

Có thể học thuộc trace căn bản:

```text
pre(dir)
    entries...
post(dir)
```

nhưng đây **không phải** một cặp `try/finally` tự động. Các tình huống phá “cặp cân bằng” gồm:

1. `preVisitDirectory(dir)` trả `SKIP_SUBTREE` → không `post` của dir.
2. `preVisitDirectory(dir)` trả `SKIP_SIBLINGS` → cũng không `post` của dir.
3. Một callback trả `TERMINATE` → những directory đang mở chưa chắc có `post`.
4. Callback tự ném `IOException`/runtime exception → traversal chấm dứt, không có bảo đảm phát sinh `post` còn thiếu.
5. Một directory không mở được → thường gọi `visitFileFailed`, không có `pre`/`post` cho directory ấy.
6. Directory tại `maxDepth` → `visitFile` thay vì cặp `pre`/`post`.

### 17.1. Quản lý resource an toàn trong visitor

Nếu cần mở một resource trong `preVisitDirectory`, phải có kế hoạch đóng cả khi:

- pre quyết định skip,
- một callback con ném exception,
- nhận `TERMINATE`,
- error xảy ra trong iterator,
- một nhánh chưa bao giờ post.

Giải pháp có thể là dùng scope/ownership ngoài callback, `try/finally` bao quanh toàn bộ `walkFileTree`, hoặc tổ chức visitor với stack state và cleanup ở boundary. **Không dựa duy nhất vào `postVisitDirectory` như một `finally` toàn cục.**

### 17.2. `postVisitDirectory(exc)` không phải callback mọi lỗi

Nếu `visitFile` tự ném exception, walker chấm dứt ngay; nó không cần gọi `postVisitDirectory` cho ancestor. Nếu `visitFileFailed` trả `CONTINUE` vì đã chấp nhận bỏ qua một file, `postVisitDirectory` không nhất thiết nhận chính lỗi đó trong `exc`. Muốn có thống kê lỗi tổng hợp, hãy tự theo dõi state hoặc thu thập báo cáo rõ ràng.

## 18. Bài toán thực tế: liệt kê và thống kê

### 18.1. Chỉ đếm regular files

Có thể dùng `SimpleFileVisitor`:

```java
final long[] regularCount = {0};

Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()) {
            regularCount[0]++;
        }
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là **mảnh minh họa**, cần import các lớp NIO.2 và định nghĩa `root`. Vì walker mặc định đi sâu toàn cây và không follow symlink, count có ý nghĩa theo cách visit đó. Nếu có lỗi đọc file, visitor mặc định sẽ rethrow thay vì ngầm trả một con số “đã kiểm đầy đủ”.

### 18.2. Tính dung lượng theo thuộc tính

Trong `visitFile`, có thể cộng `attrs.size()` khi `attrs.isRegularFile()`. Tuy nhiên, đó là thông tin quan sát filesystem tại lúc walker đọc thuộc tính. File có thể đang được process khác ghi nên tổng size không phải snapshot atomic của toàn cây.

Cần chú ý overflow nếu cộng rất nhiều kích thước vào `long`; có thể dùng `Math.addExact` để phát hiện overflow nếu đặc tả tính toán yêu cầu tính chính xác tuyệt đối.

### 18.3. Tìm một file đầu tiên rồi dừng

Trong `visitFile`, sau khi tìm đúng điều kiện, có thể lưu `Path` đã tìm và return `TERMINATE`. Nhưng “đầu tiên” ở đây là **đầu tiên theo thứ tự traversal của provider**, không phải file có tên nhỏ nhất theo alphabet. Nếu cần file “nhỏ nhất theo tên” thì phải duyệt/sắp xếp theo một quy tắc đã thiết kế.

### 18.4. Bỏ qua directory không liên quan

Với các cây chứa cache/generated outputs, `preVisitDirectory` có thể trả `SKIP_SUBTREE` dựa trên một quy tắc xác định, ví dụ đường dẫn có tên directory nằm trong allowlist/blocklist. Khi cần bảo mật hoặc correctness, tránh quyết định theo tên quá rộng như `contains("temp")` không có kiểm soát; xét path components và policy.

## 19. Bài toán thực tế: copy hoặc xóa cây

### 19.1. Copy cây

Một cách tổ chức phổ biến là:

- `preVisitDirectory`: tính `target.resolve(source.relativize(dir))` và bảo đảm directory đích có tồn tại.
- `visitFile`: copy từng file sang vị trí tương ứng.
- `postVisitDirectory`: hoàn tất thuộc tính/metadata của directory nếu format cần.
- `visitFileFailed`: propagate hoặc thu thập lỗi rõ.

Đây chỉ là **khung tổ chức**, không phải một thuật toán copy hoàn chỉnh. Copy metadata, symbolic links, file permissions, xung đột tên và source/target overlap cần các quy tắc riêng; đừng bỏ qua chúng chỉ vì callback được gọi đúng thứ tự.

### 19.2. Xóa cây

Một cách tổ chức là:

- `visitFile`: xóa mục con đã được visitor thăm.
- `postVisitDirectory`: sau khi xóa hết mục con và `exc == null`, xóa directory.
- `visitFileFailed`: nếu không thể thăm một mục, propagate lỗi nếu yêu cầu phải xóa hết.
- Mặc định **không follow links**, để không đi vào target ngoài cây.
- Có giới hạn/root do ứng dụng kiểm soát, không duyệt/xóa từ path do người dùng nhập mà chưa xác minh.

**Vấn đề phải nói rõ:** `walkFileTree` không là transaction xóa. Nếu lỗi xảy ra giữa chừng, có thể đã xóa một số file nhưng chưa xóa các file khác. Nếu thao tác có yêu cầu rollback, backup hoặc audit, cần thiết kế ở tầng nghiệp vụ.

## 20. Khác biệt giữa `Files.walkFileTree` và `Files.walk`

Trên Java hiện đại có hai cách thường gặp:

| Đặc điểm | `Files.walkFileTree` | `Files.walk` |
| --- | --- | --- |
| Xuất hiện từ | Java 7 | Java 8 |
| Cơ chế | Callback visitor | `Stream<Path>` |
| Callback trước/sau directory | Có `preVisitDirectory`/`postVisitDirectory` | Không có hai callback tương đương trực tiếp |
| Xử lý lỗi theo callback | Có `visitFileFailed`/`postVisitDirectory(exc)` | Một số I/O khi stream đang đọc có thể được bọc thành `UncheckedIOException` |
| Kiểm soát skip subtree/siblings | `FileVisitResult` | Không có cùng mô hình control flow |
| Dùng khi | Copy/xóa cây, chính sách lỗi/điều hướng theo cấp | Liệt kê/filter/map theo stream |
| Đóng tài nguyên | Walker quản lý các directory stream trong traversal | **Phải đóng Stream** bằng try-with-resources |

Ví dụ đọc danh sách qua Stream:

```java
try (Stream<Path> paths = Files.walk(root)) {
    long count = paths.filter(Files::isRegularFile).count();
    System.out.println(count);
}
```

Đây là **mảnh minh họa**, cần import `java.util.stream.Stream`, `Path`, `Files`, định nghĩa `root` và xử lý `IOException`. Với `Files.walk`, cần đóng stream để giải phóng directory handles. `walkFileTree` phù hợp hơn nếu bạn thực sự cần biết “trước khi đi vào directory” và “sau khi đi ra” hoặc muốn điều khiển chính xác việc skip.

Không nói `walkFileTree` là legacy chỉ vì đã có Stream API: **hai cách đều đang được hỗ trợ** và giải quyết các nhu cầu khác nhau.

## 21. Cạnh tranh, quyền truy cập và tính an toàn khi traversal

Duyệt cây filesystem không phải đọc một snapshot bất biến. Trong lúc walker đang chạy:

- Một thread/process khác có thể tạo entry mới.
- Một file được thấy trong lúc liệt kê nhưng biến mất khi đọc attributes.
- Một directory có thể bị đổi permission, không mở được hoặc bị move.
- Một symbolic link có thể được thêm hoặc đổi target.
- Các thuộc tính file có thể thay đổi trước khi callback xử lý.

Vì vậy:

1. **Không dựa vào kết quả kiểm kê như số liệu giao dịch atomic** nếu filesystem đang bị sửa đồng thời.
2. Xác định lỗi nào làm công việc thất bại; nếu bỏ qua file, báo rõ phạm vi kết quả đã thiếu.
3. Không coi `Files.exists` trước callback như cách tránh race.
4. Nếu visitor xóa/di chuyển file, biết rằng thao tác có thể tác động đến traversal còn lại.
5. Không theo symlink ra ngoài vùng cho phép khi copy/xóa.
6. Với input không tin cậy, xác minh root/base, path traversal, symlink, quyền và TOCTOU ở cấp filesystem. `normalize` và `startsWith` chỉ là kiểm tra **từ vựng**, không bảo đảm mọi thao tác sau đó đều bị giới hạn đúng.
7. Đặt giới hạn số file/độ sâu/thời gian và xử lý error policy khi cây có thể rất lớn.
8. Tránh ghi log đường dẫn nhạy cảm trực tiếp cho người không có quyền xem.

### 21.1. Khi nào nên tiếp tục sau lỗi?

Trong một trình **quét báo cáo**, có thể chấp nhận bỏ qua file không đọc được, tăng counter lỗi và tiếp tục. Nhưng trong một trình **xóa toàn bộ cây**, việc bỏ qua lỗi có thể khiến directory cha không rỗng và thao tác xóa thất bại sau đó. Trong một trình **copy backup**, bỏ qua file có thể làm bản backup không đầy đủ.

Không có chính sách chung cho mọi ứng dụng; visitor phải thể hiện rõ logic nghiệp vụ.

### 21.2. `FileVisitor` không tự tạo môi trường đa luồng

`Files.walkFileTree` không định nghĩa một cơ chế traversal parallel giúp callback được gọi đồng thời trên nhiều thread. Không nên mặc định các callback sẽ chạy song song và cũng không nên dùng việc callback chạy theo thứ tự trên một lần walk làm lời hứa mọi tài nguyên trong hệ thống đều thread-safe.

Nếu bạn tự đưa công việc trong callback vào executor, bạn phải quản lý riêng lifecycle, thứ tự hoàn thành, error propagation, kiểm soát resource, tránh việc `postVisitDirectory` chạy trước khi asynchronous tasks thực sự hoàn tất.

## 22. Kiểm thử callback: kiểm điều được bảo đảm, không kiểm điều không được bảo đảm

Một bộ kiểm thử tốt cho `FileVisitor` nên có:

| Trường hợp | Kỳ vọng theo contract | Ví dụ kiểm chứng |
| --- | --- | --- |
| Một directory với một file | `pre` trước `visitFile`, `post` sau | `CallbackOrderDemo` |
| Triển khai interface đầy đủ | Có đủ 4 callback, phương thức được gọi khi phù hợp | `InterfaceVisitorDemo` |
| `SimpleFileVisitor` mặc định | Thường `CONTINUE` khi bình thường, rethrow lỗi I/O | `VisitFailureDemo` |
| `SKIP_SUBTREE` từ pre | Không đi vào children, không post directory bị skip | `SkipSubtreeDemo` |
| `SKIP_SIBLINGS` từ pre | Bỏ subtree và siblings chưa thăm; không post cho directory đó | `SkipAndTerminateDemo` |
| `TERMINATE` từ pre | Dừng walk, không bắt buộc post | `SkipAndTerminateDemo` |
| Directory ở `maxDepth` | Có thể được đưa vào `visitFile` | `MaxDepthDemo` |
| Entry không đọc được | `visitFileFailed` nếu walker không đọc được/mở được | `VisitFailureDemo` |
| `visitFile` tự ném IOException | Walker dừng, lỗi propagate, post không được bảo đảm | `VisitorExceptionDemo` |
| Nhiều siblings | Quan hệ cha–con đúng, **thứ tự siblings không cố định** | Không assert alphabet |
| Symlink thường | Mặc định không follow | Test tùy môi trường |
| `FOLLOW_LINKS` có cycle | `visitFileFailed` có thể nhận `FileSystemLoopException` | Test tùy môi trường |
| `postVisitDirectory(exc)` có lỗi iteration | Không bỏ qua `exc` nếu cần đầy đủ | Test có kiểm soát lỗi/provider hỗ trợ |

### 22.1. Cách giữ stdout ổn định

Các demo chỉ in **tên file trong cây tạm**, kết quả boolean hoặc số callback — không in đường dẫn temp absolute (thường chứa tên ngẫu nhiên hoặc tên người dùng). Với nhiều mục cùng cấp, demo in counter chứ không in thứ tự. Nhờ vậy kết quả dễ kiểm tra trên nhiều máy hơn.

Các kết quả exception như `NoSuchFileException` phụ thuộc provider; trong bài, các stdout đã được chạy thử trên **Windows/JDK**, không được diễn giải là cam kết mọi subtype trên mọi filesystem.

### 22.2. Test cần kiểm cả đường bỏ qua và đường lỗi

Nếu chỉ test một tree bình thường, bạn có thể lầm tưởng:

- `post` luôn được gọi;
- `visitFileFailed` sẽ xử lý exception do `visitFile` ném;
- `visitFile` luôn là regular file;
- thứ tự siblings là alphabet;
- `SKIP_SUBTREE` dùng được trong mọi callback để dừng toàn bộ walk.

Bộ test cần cố ý kích hoạt `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`, `maxDepth` và missing path/IOException để thấy những khác biệt quan trọng.

## 23. Các lỗi sai thường gặp

### 23.1. Ghi “pre → file → post” như một thứ tự hoàn chỉnh tuyệt đối

Đây là thứ tự mẫu cho một nhánh thành công, không bao hàm mọi trường hợp skip, exception hay giới hạn độ sâu. Đọc contract của từng callback.

### 23.2. Assert thứ tự siblings theo tên

Thứ tự entry cùng cấp không được bảo đảm. Hãy assert **bất biến callback**, số lượng hoặc set đường dẫn được thăm; nếu cần thứ tự tên, sắp xếp riêng trong thuật toán.

### 23.3. Cho rằng mọi `preVisitDirectory` đều có `postVisitDirectory`

Bị phản chứng bởi `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE` và exception. Resource lifecycle phải có kế hoạch khác.

### 23.4. Trả `SKIP_SUBTREE` trong `visitFile` rồi tưởng bỏ cả cây

Theo `FileVisitResult`, `SKIP_SUBTREE` chỉ có ý nghĩa đặc biệt từ `preVisitDirectory`; từ callback khác nó tương đương `CONTINUE`. Để dừng toàn bộ, dùng `TERMINATE`.

### 23.5. Trả `SKIP_SIBLINGS` và quên nó ảnh hưởng siblings khác

Nó bỏ các entries còn lại cùng cấp, không chỉ thư mục/file hiện tại. Kết quả có thể phụ thuộc thứ tự siblings mà provider đưa ra.

### 23.6. Không xử lý `IOException exc` ở `postVisitDirectory`

`exc` khác null báo lỗi iteration của directory. Bỏ qua có thể che mất việc traversal chưa đầy đủ. Với yêu cầu đúng đầy đủ, thường rethrow.

### 23.7. Coi `visitFileFailed` như một catch cho mọi lỗi trong visitor

Lỗi do chính callback ném được propagate và có thể dừng traversal ngay; không bảo đảm gọi lại `visitFileFailed`.

### 23.8. Override `visitFileFailed`, luôn trả `CONTINUE` rồi báo “SUCCESS”

Tiếp tục là lựa chọn policy, không tự biến file không đọc được thành đã xử lý thành công. Cần đếm lỗi/ghi báo cáo khi tính đầy đủ quan trọng.

### 23.9. Cho rằng `SimpleFileVisitor` âm thầm bỏ qua lỗi

Mặc định nó **ném lại** lỗi trong `visitFileFailed` và `postVisitDirectory` khi có `exc`. Chỉ override nếu có lý do.

### 23.10. Dùng `visitFile` như synonym “regular file”

Directory ở độ sâu max, symbolic link, special entry có thể đi vào `visitFile`. Kiểm tra `attrs.isRegularFile()` nếu đó là tiêu chí.

### 23.11. Dùng `FOLLOW_LINKS` khi xóa/copy mà chưa hiểu link target

Có thể đi vào khu vực ngoài phạm vi được phép hoặc gặp vòng lặp. Mặc định không follow; bật chỉ khi có contract rõ.

### 23.12. Không giới hạn số lượng công việc trên cây lớn

Một cây rất sâu/rộng có thể tạo chi phí I/O và thời gian lớn. Cân nhắc `maxDepth`, quotas và `TERMINATE` theo nhu cầu.

### 23.13. Hardcode đường dẫn máy phát triển trong test

Dùng `Files.createTempDirectory` và cleanup trong `finally` để không thay đổi file thực của dự án/người dùng.

### 23.14. Xóa directory trong `preVisitDirectory`

Directory vẫn chứa các mục con; xóa ngay có thể nhận `DirectoryNotEmptyException`. Với một cây được phép xóa, thường dùng `postVisitDirectory` sau khi xóa con.

### 23.15. Coi walker là snapshot filesystem

Các file có thể thay đổi giữa lúc liệt kê và lúc xử lý. Đừng xem thống kê là atomic trên filesystem đang có writer khác.

### 23.16. Trộn `Files.walk` và `walkFileTree` như cùng API

`Files.walk` trả `Stream<Path>` và cần đóng stream; `walkFileTree` dùng visitor callbacks và `FileVisitResult`. Lựa chọn theo mục tiêu thao tác.

## 24. Checklist khi review code

- [ ] Xác định chính xác root bắt đầu, liệu nó có phải directory hay file.
- [ ] Đã chọn `FileVisitor<Path>` hay `SimpleFileVisitor<Path>` theo policy.
- [ ] Biết đủ bốn callback và ý nghĩa của tham số `exc`.
- [ ] Không phụ thuộc thứ tự siblings khi không có sorting algorithm riêng.
- [ ] Đã xử lý `SKIP_SUBTREE` không gọi post trên directory bị skip.
- [ ] Đã hiểu `SKIP_SIBLINGS` ở pre bỏ luôn subtree và siblings còn lại.
- [ ] `TERMINATE` không được coi là đảm bảo unwind đầy đủ qua post callbacks.
- [ ] Không trả `null` từ một visitor method.
- [ ] Có đường xử lý `IOException` và không bỏ qua lỗi quan trọng.
- [ ] Nếu chỉ đếm regular files, kiểm tra `attrs.isRegularFile()`.
- [ ] Kiểm tra semantics của `maxDepth` khi đếm file/dir.
- [ ] Có policy với symlinks và `FOLLOW_LINKS`/loops.
- [ ] Không dùng walker với xóa/copy ngoài phạm vi root được phép.
- [ ] Có kế hoạch cleanup khi visitor bị skip, terminate hoặc ném exception.
- [ ] Khi dùng `Files.walk` stream, có try-with-resources để đóng stream.
- [ ] Dùng temp directories trong test, không chạm file thật của người dùng.
- [ ] Có test sibling-order-independent và error/skip paths.
- [ ] Phân biệt API Java 7 và tiện ích xuất hiện ở các bản sau.

## 25. Bài tập thực hành

**Bài 1 — Thứ tự một nhánh.** Với cây `root/dir/file.txt`, hãy viết thứ tự callback nếu không có lỗi và tất cả trả `CONTINUE`. Vì sao `postVisitDirectory(root)` cuối cùng?

**Bài 2 — Đủ bốn phương thức.** Tự viết lớp thực thi `FileVisitor<Path>` để đếm pre, visit, failed và post. So sánh với việc kế thừa `SimpleFileVisitor<Path>`.

**Bài 3 — Bỏ qua thư mục.** Cho cây gồm `blocked/secret.txt` và `visible/public.txt`. Viết visitor trả `SKIP_SUBTREE` khi pre thấy blocked, rồi dự đoán số `pre`/`visitFile`/`post`.

**Bài 4 — Sibling order.** Vì sao test viết “a.txt luôn được thăm trước z.txt” là sai khi dùng `walkFileTree` bình thường? Sửa test để kiểm tra set tệp và quan hệ callback.

**Bài 5 — Dừng sớm.** Viết `visitFile` trả `TERMINATE` khi tìm được một file thỏa điều kiện. Vì sao không được đợi mọi directory đã pre có post?

**Bài 6 — `SKIP_SUBTREE` ở sai chỗ.** Hãy cho biết kết quả khi trả `SKIP_SUBTREE` từ `visitFile`. Giá trị nào cần dùng nếu muốn dừng toàn bộ?

**Bài 7 — `SKIP_SIBLINGS`.** Tạo hai thư mục con cùng cấp và trả `SKIP_SIBLINGS` từ pre của thư mục con đầu tiên walker gặp. Dự đoán số pre/post không phụ thuộc thứ tự provider.

**Bài 8 — Default errors.** Duyệt một path không tồn tại bằng `SimpleFileVisitor` mặc định; sau đó override `visitFileFailed` trả `CONTINUE` và so kết quả.

**Bài 9 — IOException trong callback.** Ném `IOException` từ `visitFile`. `visitFileFailed` có tự nhận exception ấy không? `postVisitDirectory` có được bảo đảm chạy không?

**Bài 10 — `maxDepth`.** Cho cây `root/sub/a.txt`, chạy các mức 0, 1, 2. Vì sao `visitFile` có thể nhận root hoặc sub directory ở mức giới hạn?

**Bài 11 — Regular files.** Viết một visitor đếm `attrs.isRegularFile()` thay vì đếm mọi lần gọi `visitFile`. So với kết quả `MaxDepthDemo`.

**Bài 12 — Theo symbolic link.** Nếu filesystem hỗ trợ, tạo symlink tới một directory khác. Thử walk mặc định và với `FOLLOW_LINKS` trong phạm vi test. Giải thích lý do phải có giới hạn và policy xử lý loop.

**Bài 13 — Xóa cây.** Chỉ trên một temp directory do test tạo, viết visitor xóa file ở `visitFile` và xóa directory ở `postVisitDirectory`. Giải thích vì sao không xóa directory từ `preVisitDirectory`.

**Bài 14 — Post error.** Nếu callback `postVisitDirectory(dir, exc)` nhận `exc != null`, nên xử lý ra sao trong công cụ sao lưu yêu cầu không được bỏ file?

**Bài 15 — Không đảm bảo snapshot.** Một process khác liên tục tạo/xóa file trong khi bạn walk. Những kết quả nào có thể thiếu hoặc không đồng bộ? Làm gì nếu ứng dụng cần bản kiểm kê nhất quán?

**Bài 16 — Resource lifecycle.** Một visitor mở resource ở pre rồi trả `SKIP_SUBTREE`. Tại sao đóng ở post là chưa đủ? Đề xuất một nơi cleanup chắc chắn.

### Gợi ý đáp án ngắn

- **Bài 1:** pre root, pre dir, file, post dir, post root.
- **Bài 2:** Interface cần đủ bốn method, SimpleFileVisitor có mặc định.
- **Bài 3:** 3 pre, 1 file, 2 post với tree mẫu.
- **Bài 4:** Siblings không có thứ tự đảm bảo; assert set và quan hệ cha/con.
- **Bài 5:** `TERMINATE` dừng walk; hậu duyệt không được bảo đảm chạy cho các directory mở.
- **Bài 6:** `SKIP_SUBTREE` từ visitFile giống `CONTINUE`; dùng `TERMINATE` để dừng.
- **Bài 7:** Root pre, một con pre rồi skip siblings; chỉ root post.
- **Bài 8:** Mặc định rethrow; override có thể chấp nhận bỏ qua lỗi và đi tiếp.
- **Bài 9:** Lỗi do callback tự ném truyền ra caller; không chuyển thành visitFileFailed.
- **Bài 10:** Directory ở maxDepth được visit như file để không mở sâu hơn.
- **Bài 11:** Dựa trên thuộc tính regular file, không dựa vào tên callback.
- **Bài 12:** Default không follow; FOLLOW_LINKS cần loop/escape policy.
- **Bài 13:** Xóa con trước cha; cần scope/permission rõ.
- **Bài 14:** Truyền lại lỗi hoặc báo thất bại để không tuyên bố backup đầy đủ.
- **Bài 15:** Walker không là snapshot; cần thiết kế synchronization/snapshot filesystem riêng.
- **Bài 16:** Skip pre không có post, nên phải cleanup riêng.

## Tài liệu chính thức còn hiệu lực

- [Java SE 17 — `FileVisitor<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html): bốn callback, thứ tự pre/post, xử lý failure.
- [Java SE 17 — `SimpleFileVisitor<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): hành vi mặc định `CONTINUE` và rethrow lỗi I/O.
- [Java SE 17 — `FileVisitResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE` và giới hạn áp dụng.
- [Java SE 17 — `Files.walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)): depth-first, `maxDepth`, `FOLLOW_LINKS`, cycle detection và lỗi.
- [Java SE 17 — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): thuộc tính cơ bản được đưa vào callback.
- [Java SE 17 — `FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): tùy chọn duyệt liên kết.
- [Java SE 17 — `FileSystemLoopException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemLoopException.html): trường hợp phát hiện cycle theo symbolic link.
- [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): thao tác filesystem, `walkFileTree` và `walk` hiện đại.

**Kết luận:** `FileVisitor` mô tả bốn callback, `SimpleFileVisitor` cung cấp mặc định để bạn chỉ override các callback cần thiết. Trong một nhánh thành công, thứ tự là **`preVisitDirectory` → xử lý các entry con → `postVisitDirectory`**; nhưng thứ tự siblings **không được bảo đảm**, và khi skip, terminate hoặc lỗi, `post` không nhất thiết xuất hiện. Sử dụng chính xác `FileVisitResult`, phân biệt lỗi của walker với lỗi tự ném từ visitor, và hiểu `maxDepth`/symbolic links để duyệt cây an toàn, đúng phạm vi và có kết quả đáng tin.