# FileVisitResult: tiếp tục, bỏ nhánh hoặc kết thúc khi duyệt cây thư mục

## 1. Bài toán: kiểm soát hành trình duyệt cây

Khi Java duyệt một thư mục có nhiều tầng, ứng dụng thường không muốn xử lý mọi tệp như nhau. Ta có thể cần:

- Duyệt hết cây để thống kê tệp.
- **Bỏ qua cả một nhánh** như `.git`, `node_modules` hoặc một thư mục không nằm trong phạm vi xử lý.
- **Bỏ qua những phần tử còn lại cùng cấp** sau khi đã tìm được một mục phù hợp.
- **Dừng toàn bộ cuộc duyệt** ngay khi có kết quả hoặc gặp điều kiện nghiêm trọng.
- Tiếp tục sau một lỗi đọc riêng lẻ, hoặc ngừng khi tính toàn vẹn không còn được bảo đảm.

Java NIO.2 cung cấp `Files.walkFileTree(...)` để duyệt cây và `FileVisitor`/`SimpleFileVisitor` để nhận các sự kiện. Sau mỗi callback, ta trả về một **`FileVisitResult`**, là chỉ dẫn cho cơ chế duyệt: tiếp tục, bỏ nhánh, bỏ anh em cùng cấp, hoặc kết thúc.

```text
root/
├── src/
│   ├── Main.java
│   └── App.java
├── build/
│   └── generated.bin
└── README.md

preVisitDirectory(root) → CONTINUE
  preVisitDirectory(src) → CONTINUE
    visitFile(Main.java) → CONTINUE
    visitFile(App.java) → CONTINUE
  postVisitDirectory(src) → CONTINUE
  preVisitDirectory(build) → SKIP_SUBTREE
    generated.bin KHÔNG được thăm
  visitFile(README.md) → CONTINUE
postVisitDirectory(root) → CONTINUE
```

Đây là **sơ đồ minh họa**, không phải thứ tự duyệt được bảo đảm. Thứ tự các mục trong một thư mục phụ thuộc filesystem/provider; nếu cần thứ tự sắp xếp, phải thiết kế thêm một bước có kiểm soát thay vì giả định walker sẽ duyệt theo bảng chữ cái.

Điểm trọng tâm của bài: **giá trị `FileVisitResult` có hiệu lực tùy callback trả nó về**, và “bỏ nhánh” khác căn bản với “bỏ các phần tử cùng cấp” hay “dừng toàn bộ”.

## 2. Khởi động một cuộc duyệt bằng Files.walkFileTree

API cơ bản:

```java
Files.walkFileTree(start, visitor);
```

Biến `start` là `Path`; `visitor` triển khai `FileVisitor<? super Path>`. `Files.walkFileTree` duyệt **depth-first**: với một thư mục, gọi callback trước khi đi vào các mục bên trong; sau khi các mục đã xử lý, gọi callback sau khi thăm thư mục (trừ trường hợp bị bỏ nhánh, dừng sớm và các ngoại lệ theo hợp đồng).

Một overload cho phép chọn cách theo liên kết và giới hạn độ sâu:

```java
Files.walkFileTree(
        start,
        EnumSet.noneOf(FileVisitOption.class),
        4,
        visitor);
```

Đây là **đoạn minh họa**, yêu cầu các import từ `java.nio.file`, `java.util.EnumSet` và biến `start`, `visitor` đã khai báo. `maxDepth = 4` đặt mức sâu tối đa. Lựa chọn `EnumSet.noneOf(FileVisitOption.class)` nghĩa là **không bật `FOLLOW_LINKS`**; mặc định symbolic link không được tự động đi theo như một thư mục bình thường.

`Files.walkFileTree` thường trả lại chính `start` khi cuộc duyệt kết thúc theo hợp đồng, còn chi tiết điều khiển được thực hiện bởi các callback. Nó có thể ném `IOException` (ví dụ một callback ném lỗi), không phải chỉ thông qua các giá trị enum.

### Khi nào dùng FileVisitor thay vì Files.walk?

`Files.walk(start)` trả một `Stream<Path>` lazy, thích hợp cho một số phép lọc/lấy danh sách đơn giản. Nhưng `FileVisitor` cho phép **quyết định tại từng thư mục có đi vào nhánh đó hay không**, cũng như nhận callback riêng trước/sau thư mục và khi thăm thất bại.

Nếu cần **prune** một nhánh trước khi walker đi sâu vào nó, `preVisitDirectory` kết hợp `SKIP_SUBTREE` là công cụ trực tiếp. `Stream.filter(path -> ...)` trên kết quả `Files.walk` chỉ lọc phần tử được **trả ra cho pipeline**, không phải một cam kết rằng walker sẽ tránh mở/đi vào các nhánh đã lọc.

## 3. FileVisitor có bốn callback

`FileVisitor<Path>` định nghĩa bốn phương thức:

| Callback | Được gọi khi nào? | Tham số quan trọng |
| --- | --- | --- |
| `preVisitDirectory(Path dir, BasicFileAttributes attrs)` | Trước khi đi vào các mục của một thư mục | `dir`, thuộc tính thư mục |
| `visitFile(Path file, BasicFileAttributes attrs)` | Khi thăm một tệp/entry không đi vào như thư mục; tùy giới hạn độ sâu, một directory cũng có thể đi qua đây | `file`, thuộc tính |
| `visitFileFailed(Path file, IOException exc)` | Khi không thể thăm entry, ví dụ lỗi đọc thuộc tính/mở thư mục | `file`, nguyên nhân thất bại |
| `postVisitDirectory(Path dir, IOException exc)` | Sau khi duyệt xong các entry/descendant của thư mục, hoặc khi duyệt bị kết thúc sớm theo trường hợp cho phép | `dir`, lỗi khi duyệt nếu có |

`preVisitDirectory` và `postVisitDirectory` không chỉ mang tính thông báo. Chúng cũng trả về `FileVisitResult` để điều khiển bước tiếp theo. Ví dụ cần tạo danh sách trước/sau duyệt thư mục cho một thuật toán xóa cây: phần xử lý thư mục sau khi duyệt con là cực kỳ quan trọng.

`BasicFileAttributes` thuộc `java.nio.file.attribute`, có các phương thức như `isDirectory()`, `isRegularFile()`, `isSymbolicLink()`, `size()` và các mốc thời gian, hữu ích để hạn chế thêm thao tác filesystem.

### Tại sao nên kế thừa SimpleFileVisitor?

Triển khai trực tiếp `FileVisitor<Path>` yêu cầu viết cả bốn callback. Trong nhiều bài, ta chỉ cần ghi đè một hoặc hai phương thức và để `SimpleFileVisitor<Path>` cung cấp phần còn lại.

Mặc định của `SimpleFileVisitor` về cơ bản:

- `preVisitDirectory`: `CONTINUE`.
- `visitFile`: `CONTINUE`.
- `visitFileFailed`: ném lại `IOException` được truyền vào.
- `postVisitDirectory`: `CONTINUE` nếu `exc == null`, ngược lại ném lại lỗi.

Vì vậy, nếu muốn **bỏ qua lỗi không thể truy cập tệp** thay vì để exception làm dừng cuộc duyệt, phải chủ động ghi đè `visitFileFailed`. Còn khi muốn không đi vào một thư mục, ghi đè `preVisitDirectory` là đủ.

## 4. Bốn giá trị của FileVisitResult

Enum `java.nio.file.FileVisitResult` có đúng bốn hằng số:

| Giá trị | Tác dụng chính | Phạm vi |
| --- | --- | --- |
| `CONTINUE` | Tiếp tục cuộc duyệt | Cơ chế đi tiếp theo lịch duyệt |
| `SKIP_SUBTREE` | Không duyệt các entry bên trong **thư mục hiện tại** | Chỉ có ý nghĩa đặc biệt trong `preVisitDirectory` |
| `SKIP_SIBLINGS` | Không duyệt các phần tử **còn lại cùng cấp** với entry hiện tại | Không có nghĩa dừng toàn bộ cây |
| `TERMINATE` | Dừng toàn bộ cuộc duyệt | Toàn bộ walker |

Điều cần nhớ: `FileVisitResult` là **giá trị điều khiển**, không phải exception, và không mang nghĩa “đọc file thành công”. Bất kỳ callback nào cũng có thể ném `IOException` theo chữ ký của nó; exception đó làm kết thúc walker trừ khi đã được xử lý theo cách thích hợp trong visitor.

### 4.1 CONTINUE: đi tiếp

`CONTINUE` là trường hợp mặc định phổ biến. Khi được trả từ `preVisitDirectory(dir)`, walker sẽ cố duyệt các entry bên trong `dir`. Khi được trả từ `visitFile(file)`, walker tiếp tục tới phần tử phù hợp tiếp theo.

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    System.out.println(file.getFileName());
    return FileVisitResult.CONTINUE;
}
```

Đây là **phương thức trong một visitor**, chưa phải chương trình độc lập. Việc trả `CONTINUE` không đảm bảo mọi file đều được thăm thành công; vẫn có thể có lỗi I/O, thư mục không đọc được, giới hạn độ sâu, hoặc nhánh khác được bỏ qua.

### 4.2 SKIP_SUBTREE: bỏ nhánh

`SKIP_SUBTREE` có ý nghĩa đặc biệt khi trả từ **`preVisitDirectory(dir)`**. Walker **không đi vào các entry của thư mục đó**. Với thư mục bị bỏ qua theo cách này, `postVisitDirectory(dir)` **không được gọi**.

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) {
    if (dir.getFileName() != null
            && dir.getFileName().toString().equals("build")) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa**, cần các import của `Path`, `BasicFileAttributes`, `FileVisitResult`. Nếu gặp `build` thì không mở rộng nhánh `build`, còn các mục ngang cấp với nó vẫn có thể được duyệt.

**Điểm tinh tế:** nếu trả `SKIP_SUBTREE` từ `visitFile`, `visitFileFailed` hoặc `postVisitDirectory`, kết quả này có nghĩa **tương đương `CONTINUE`** theo Javadoc enum. Không dùng `SKIP_SUBTREE` ở `visitFile` với hy vọng bỏ qua các file còn lại trong cùng thư mục.

### 4.3 SKIP_SIBLINGS: bỏ anh em cùng cấp

`SKIP_SIBLINGS` thông báo rằng walker không nên thăm **các entry chưa thăm là anh em cùng cấp** của file hoặc directory hiện tại.

Có hai trường hợp nổi bật:

1. Trả từ **`visitFile(file)`**: không thăm các entry còn lại trong cùng thư mục cha; sau đó walker có thể tiếp tục xử lý ở cấp cha cao hơn.
2. Trả từ **`preVisitDirectory(dir)`**: **không đi vào chính `dir`**, không gọi `postVisitDirectory(dir)`, đồng thời bỏ qua các sibling chưa thăm của `dir`.

Nếu trả từ `postVisitDirectory(dir)`, ý nghĩa là không duyệt tiếp các sibling còn lại của `dir` trong thư mục cha. Nếu trả từ `visitFileFailed`, nó cũng có thể được dùng để bỏ các sibling chưa thăm của entry lỗi.

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (file.getFileName().toString().equals("stop-here.flag")) {
        return FileVisitResult.SKIP_SIBLINGS;
    }
    return FileVisitResult.CONTINUE;
}
```

**Đừng nhầm `SKIP_SIBLINGS` với `TERMINATE`.** Lệnh đầu chỉ loại bỏ **những phần tử cùng cấp chưa duyệt**, nên walker vẫn có thể trở lên cây và duyệt các nhánh khác. Lệnh sau dừng toàn bộ hoạt động duyệt.

**Thứ tự không bảo đảm:** nếu một file được tìm thấy giữa các sibling, `SKIP_SIBLINGS` không quay ngược để “bỏ những entry đã duyệt” và cũng không đảm bảo file nào trong thư mục sẽ được thăm đầu tiên. Không nên dùng nó làm cách chọn “file nhỏ nhất theo tên” khi không có sắp xếp.

### 4.4 TERMINATE: kết thúc ngay

`TERMINATE` là cách chủ động dừng **toàn bộ cuộc duyệt**. Ví dụ:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (file.getFileName().toString().equals("found.txt")) {
        found = file;
        return FileVisitResult.TERMINATE;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **đoạn minh họa** trong một visitor có trường `Path found`. Sau khi callback trả `TERMINATE`, walker ngừng gọi các phương thức thăm tiếp theo. Không mong đợi `postVisitDirectory` chạy cho các thư mục còn nằm trên stack. Nếu có tài nguyên nghiệp vụ mở bên trong visitor, phải tự quản lý việc đóng chúng chứ không giả định post-visit đóng vai trò `finally`.

**Định nghĩa “kết thúc thành công”:** `TERMINATE` bản thân không phải lỗi. `Files.walkFileTree` có thể trả về bình thường sau khi visitor yêu cầu dừng; nếu caller cần biết đã tìm thấy mục nào, phải tự lưu trạng thái/cung cấp kết quả (ví dụ biến `found`).

## 5. Ma trận: trả giá trị nào từ callback nào?

| Callback | `CONTINUE` | `SKIP_SUBTREE` | `SKIP_SIBLINGS` | `TERMINATE` |
| --- | --- | --- | --- | --- |
| `preVisitDirectory` | Đi vào thư mục | Không đi vào subtree; không gọi post cho dir này | Không đi vào dir, không gọi post; bỏ sibling của dir | Dừng tất cả |
| `visitFile` | Xét mục kế tiếp | Tương đương CONTINUE | Bỏ sibling chưa xét của file | Dừng tất cả |
| `visitFileFailed` | Bỏ qua lỗi entry và đi tiếp | Tương đương CONTINUE | Bỏ sibling chưa xét của entry lỗi | Dừng tất cả |
| `postVisitDirectory` | Đi tiếp sau thư mục | Tương đương CONTINUE | Bỏ sibling chưa xét của thư mục | Dừng tất cả |

Có hai nhận xét cần thuộc:

- **Chỉ `preVisitDirectory` mới dùng `SKIP_SUBTREE` để chặn việc đi xuống một thư mục**. Đừng trả nó từ `postVisitDirectory` rồi nghĩ sẽ thay đổi những entry đã thăm.
- **`SKIP_SIBLINGS` từ `preVisitDirectory` vừa bỏ subtree của chính directory ấy vừa bỏ các sibling chưa thăm**. Đây là hành vi mạnh hơn `SKIP_SUBTREE`.

Khi callback trả `SKIP_SIBLINGS` vì file đã thăm trong một directory, iteration của directory có thể hoàn tất sớm; tài liệu FileVisitor nêu rằng `postVisitDirectory` của directory đó vẫn có thể được gọi sau việc kết thúc iteration sớm ấy.

## 6. Ví dụ Java 17 chạy được: dùng SKIP_SUBTREE mà vẫn duyệt nhánh khác

Ví dụ tự tạo một cây nhỏ trong thư mục tạm, chỉ có hai thư mục con `keep` và `ignored`. Visitor sẽ bỏ nhánh `ignored` bất kể thứ tự duyệt do filesystem cung cấp. Đầu ra là số lượng, không dựa vào thứ tự sự kiện.

**Tệp `SkipSubtreeDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class SkipSubtreeDemo {
    static final class Visitor extends SimpleFileVisitor<Path> {
        int seenFiles;
        int enteredDirectories;
        boolean ignoredPostCalled;

        @Override
        public FileVisitResult preVisitDirectory(
                Path dir, BasicFileAttributes attrs) {
            if (dir.getFileName() != null
                    && dir.getFileName().toString().equals("ignored")) {
                return FileVisitResult.SKIP_SUBTREE;
            }
            enteredDirectories++;
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            seenFiles++;
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            if (dir.getFileName() != null
                    && dir.getFileName().toString().equals("ignored")) {
                ignoredPostCalled = true;
            }
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("walk-result-");
        Path keep = root.resolve("keep");
        Path ignored = root.resolve("ignored");

        try {
            Files.createDirectory(keep);
            Files.createDirectory(ignored);
            Files.writeString(keep.resolve("a.txt"), "ok",
                    StandardCharsets.UTF_8);
            Files.writeString(ignored.resolve("hidden.txt"), "secret",
                    StandardCharsets.UTF_8);

            Visitor visitor = new Visitor();
            Files.walkFileTree(root, visitor);

            System.out.println("Entered dirs: "
                    + visitor.enteredDirectories);
            System.out.println("Visited files: " + visitor.seenFiles);
            System.out.println("Ignored post called: "
                    + visitor.ignoredPostCalled);
        } finally {
            Files.deleteIfExists(keep.resolve("a.txt"));
            Files.deleteIfExists(ignored.resolve("hidden.txt"));
            Files.deleteIfExists(keep);
            Files.deleteIfExists(ignored);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SkipSubtreeDemo.java
java SkipSubtreeDemo
```

**Stdout chính xác khi các thao tác I/O thành công:**

```text
Entered dirs: 2
Visited files: 1
Ignored post called: false
```

Giải thích: `preVisitDirectory` của `root` và `keep` trả CONTINUE nên `enteredDirectories = 2`. Nhánh `ignored` bị nhận diện ở pre-visit rồi trả SKIP_SUBTREE, nên `hidden.txt` không được thăm và `postVisitDirectory(ignored)` không xảy ra. File `a.txt` trong `keep` vẫn được thăm.

Đây là **ví dụ tự kiểm soát cấu trúc cây**. Ở môi trường thực tế, filesystem có thể bị thay đổi đồng thời hoặc quyền truy cập khác dự kiến, nên khi error/cleanup xảy ra chương trình có thể ném `IOException` thay vì in các dòng trên.

## 7. Ví dụ Java 17: SKIP_SIBLINGS không phải TERMINATE

Tạo một cây mà thư mục `group` chứa hai file; sau khi thăm file đầu tiên (file nào trước là không xác định), visitor trả `SKIP_SIBLINGS`. Hai file không được thăm hết, nhưng thư mục cha có thể hoàn tất callback post. Ví dụ dùng số lượng để không phụ thuộc thứ tự:

**Tệp `SkipSiblingsDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class SkipSiblingsDemo {
    static class Visitor extends SimpleFileVisitor<Path> {
        int filesVisited;
        boolean groupPost;

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            filesVisited++;
            return FileVisitResult.SKIP_SIBLINGS;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            if (dir.getFileName() != null
                    && dir.getFileName().toString().equals("group")) {
                groupPost = true;
            }
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("siblings-");
        Path group = root.resolve("group");

        try {
            Files.createDirectory(group);
            Files.writeString(group.resolve("first.txt"), "1");
            Files.writeString(group.resolve("second.txt"), "2");

            Visitor visitor = new Visitor();
            Files.walkFileTree(root, visitor);

            System.out.println("Files visited: " + visitor.filesVisited);
            System.out.println("Group post called: " + visitor.groupPost);
        } finally {
            Files.deleteIfExists(group.resolve("first.txt"));
            Files.deleteIfExists(group.resolve("second.txt"));
            Files.deleteIfExists(group);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac SkipSiblingsDemo.java
java SkipSiblingsDemo
```

**Stdout chính xác khi I/O thành công:**

```text
Files visited: 1
Group post called: true
```

Lưu ý: `SKIP_SIBLINGS` từ **`visitFile`** làm kết thúc sớm việc duyệt các mục còn lại trong thư mục `group`, nhưng `postVisitDirectory(group)` vẫn được gọi. Điều này **khác** việc trả `SKIP_SIBLINGS` từ **`preVisitDirectory(group)`**, khi đó `group` chưa được đi vào, các entry bị bỏ qua và `postVisitDirectory(group)` không được gọi.

Trên một cây thật với nhiều directory ở các nhánh, lệnh `SKIP_SIBLINGS` ở `group` không tự động dừng các nhánh ở cấp cao khác.

## 8. Ví dụ Java 17: TERMINATE dừng cả cây

Chương trình có đúng một file trong thư mục tạm để tạo kết quả độc lập với thứ tự filesystem. Callback `visitFile` trả `TERMINATE`, ngăn `postVisitDirectory(root)` được gọi.

**Tệp `TerminateWalkDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TerminateWalkDemo {
    static class Visitor extends SimpleFileVisitor<Path> {
        int seen;
        boolean rootPost;

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            seen++;
            return FileVisitResult.TERMINATE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            rootPost = true;
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("terminate-");

        try {
            Files.writeString(root.resolve("item.txt"), "x");
            Visitor visitor = new Visitor();

            Path returned = Files.walkFileTree(root, visitor);

            System.out.println("Visited files: " + visitor.seen);
            System.out.println("Root post called: " + visitor.rootPost);
            System.out.println("Returned start: " + returned.equals(root));
        } finally {
            Files.deleteIfExists(root.resolve("item.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac TerminateWalkDemo.java
java TerminateWalkDemo
```

**Stdout chính xác khi file tạm được tạo/xóa thành công:**

```text
Visited files: 1
Root post called: false
Returned start: true
```

Nếu callback `visitFile` ném một `IOException` thay vì trả `TERMINATE`, `Files.walkFileTree` có thể ném lỗi cho caller. Hai hướng điều khiển này mang ngữ nghĩa khác nhau: `TERMINATE` là **quyết định ngừng có chủ đích**, còn ném exception thường biểu thị **thất bại phải truyền ra ngoài**.

## 9. Trường hợp dễ nhầm: SKIP_SUBTREE trả từ visitFile

Vì `SKIP_SUBTREE` chỉ có ý nghĩa đặc biệt trong `preVisitDirectory`, việc trả nó từ `visitFile` không làm bỏ qua sibling, cũng không có subtree nào để cắt tại thời điểm callback file.

**Tệp `SkipSubtreeFromFileDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class SkipSubtreeFromFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("skip-file-");
        try {
            Files.writeString(root.resolve("one.txt"), "1");
            Files.writeString(root.resolve("two.txt"), "2");

            final int[] seen = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    seen[0]++;
                    return FileVisitResult.SKIP_SUBTREE;
                }
            });

            System.out.println("Files visited: " + seen[0]);
        } finally {
            Files.deleteIfExists(root.resolve("one.txt"));
            Files.deleteIfExists(root.resolve("two.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac SkipSubtreeFromFileDemo.java
java SkipSubtreeFromFileDemo
```

**Stdout chính xác khi thao tác thành công:**

```text
Files visited: 2
```

Điều này minh họa quy tắc của enum: từ `visitFile`, `SKIP_SUBTREE` có tác dụng như `CONTINUE`. Muốn bỏ phần còn lại **cùng cấp**, dùng `SKIP_SIBLINGS`; muốn bỏ **nhánh directory** trước khi đi vào, dùng `SKIP_SUBTREE` ở `preVisitDirectory`.

## 10. Xử lý visitFileFailed: tiếp tục hay dừng?

Một file hoặc directory có thể không được thăm vì quyền, đường dẫn biến mất, lỗi đọc thuộc tính, vòng liên kết (khi có `FOLLOW_LINKS`) hoặc nguyên nhân I/O khác. `visitFileFailed(path, exception)` cho phép visitor quyết định phản ứng.

Ví dụ **bỏ qua lỗi riêng lẻ và tiếp tục**:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) {
    System.err.println("Cannot visit " + file + ": " + exc);
    return FileVisitResult.CONTINUE;
}
```

Đây là phương thức minh họa trong một `SimpleFileVisitor<Path>`; không phải class độc lập. Chỉ dùng chính sách này nếu nghiệp vụ chấp nhận **kết quả không đầy đủ**. Ví dụ quét file để hiển thị những phần truy cập được có thể hợp lý, còn kiểm tra toàn vẹn dữ liệu backup phải ghi nhận rõ tất cả lỗi hoặc từ chối tuyên bố “đã quét đủ”.

Nếu gặp lỗi **không thể bỏ qua**, thường tốt hơn là ném lại `exc`:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    throw exc;
}
```

Điều đó cho caller biết cuộc duyệt thất bại bằng `IOException`. Trả `TERMINATE` cũng ngừng duyệt nhưng **không tự giữ exception trong kết quả**; nếu cần truyền lý do, phải lưu lại trạng thái hoặc ném lỗi có chủ đích.

### Có dùng SKIP_SIBLINGS khi file bị lỗi không?

Có thể: nếu hệ thống muốn bỏ những mục cùng cấp với entry không truy cập được, visitor có thể trả `SKIP_SIBLINGS` từ `visitFileFailed`. Tuy nhiên đây là một chính sách khá mạnh, dễ bỏ lỡ dữ liệu lành ở cùng thư mục. Chỉ dùng khi giao thức duyệt định nghĩa rõ lý do.

### File không đọc được có luôn gọi visitFileFailed không?

Không nên áp đặt một nguyên nhân duy nhất. `visitFileFailed` có thể nhận lỗi đọc metadata, lỗi mở directory và các nguyên nhân làm không thể thăm entry. Trong khi đó, **lỗi khi đang lặp entry của một directory đã mở** có thể được báo qua tham số `exc` của `postVisitDirectory`, không phải lúc nào cũng là một `visitFileFailed` trực tiếp.

## 11. postVisitDirectory: exc khác null nghĩa là gì?

`postVisitDirectory(dir, exc)` được gọi sau khi walker đã duyệt các entry của directory hoặc khi việc lặp directory kết thúc sớm theo trường hợp hợp lệ.

- `exc == null`: không có lỗi I/O khi thực hiện iteration directory được báo qua tham số này; tuy nhiên các lỗi entry trước đó có thể đã được xử lý riêng bằng `visitFileFailed`.
- `exc != null`: có lỗi I/O khiến iteration directory kết thúc bất thường, cần quyết định truyền lỗi hay tiếp tục.
- `postVisitDirectory` vẫn có thể được gọi khi một `visitFile` trả `SKIP_SIBLINGS` và iteration của directory kết thúc sớm.
- `postVisitDirectory(dir)` **không được gọi** đối với dir bị bỏ qua trực tiếp do `preVisitDirectory(dir)` trả `SKIP_SUBTREE` hoặc `SKIP_SIBLINGS`.
- Nếu walker đã bị `TERMINATE`, không chờ các post-callback như một cơ chế dọn dẹp chắc chắn.

Mẫu bảo toàn lỗi thường dùng:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là đoạn minh họa. Nếu cần ghi report cho một directory sau khi hoàn tất con, thực hiện ở đây, nhưng đừng dựa vào callback này để **luôn luôn** chạy khi đã quyết định bỏ nhánh hoặc terminate.

## 12. Giá trị trả về và exception: hai cơ chế riêng

| Tình huống | Cơ chế phù hợp |
| --- | --- |
| Đủ dữ liệu, chủ động dừng tìm kiếm | `TERMINATE` |
| Thư mục không nằm trong phạm vi xử lý | `SKIP_SUBTREE` từ pre-visit |
| Không cần các entry cùng cấp còn lại | `SKIP_SIBLINGS` |
| Đọc lỗi và nghiệp vụ không thể tiếp tục đúng | Ném `IOException` |
| Đọc lỗi nhưng chấp nhận danh sách thiếu | Ghi nhận lỗi, trả `CONTINUE` |
| Cần thoát kèm một kết quả | Ghi kết quả trong visitor, sau walker đọc lại trạng thái |

**Đừng dùng `TERMINATE` làm cách “nuốt lỗi”** trong tác vụ mà caller cần biết rằng kết quả không hoàn chỉnh. Ngược lại, đừng dùng exception như một lệnh điều khiển thông thường khi đã tìm thấy file và không có lỗi: `TERMINATE` diễn đạt ý định rõ hơn.

Trong các framework phức tạp, visitor có thể lưu `List<IOException>` để thống kê lỗi rồi tiếp tục; nhưng cần giới hạn bộ nhớ và tránh in đường dẫn/tên file nhạy cảm vào log không phù hợp.

## 13. maxDepth có ảnh hưởng callback không?

Có. Overload:

```java
Files.walkFileTree(start, options, maxDepth, visitor);
```

cho phép giới hạn độ sâu tối đa. Root bắt đầu ở depth 0. Nếu `maxDepth = 0`, walker chỉ thăm chính start entry (dưới dạng `visitFile` ở giới hạn độ sâu, kể cả khi là directory). Ở độ sâu tối đa, **directory không còn được mở rộng thành các entry con**.

Khi directory ở `maxDepth`, nó có thể được thăm thông qua **`visitFile`** thay vì `preVisitDirectory`, vì walker không tiếp tục vào nhánh đó. Do vậy:

- Không nên mặc định mọi `Path` biểu thị directory luôn đi qua `preVisitDirectory`.
- Nếu cần đếm tất cả directory, phải xác định rõ quy tắc khi gặp maxDepth.
- `SKIP_SUBTREE` từ `visitFile` vẫn tương đương `CONTINUE`.

Chọn `maxDepth` bằng một số có chủ đích để tránh duyệt quá sâu khi nghiệp vụ không cần; điều này bổ sung cho chính sách `SKIP_SUBTREE`, không thay thế nó.

## 14. Symbolic links và FOLLOW_LINKS

Mặc định, `Files.walkFileTree` **không theo symbolic link**. Một symbolic link thường được xem như entry không đi vào, được chuyển qua `visitFile`.

Khi bật `FileVisitOption.FOLLOW_LINKS`, walker có thể đi theo link đến thư mục và làm cây có đường quay ngược hoặc vòng lặp. API có cơ chế phát hiện vòng lặp; lỗi `FileSystemLoopException` có thể được đưa vào `visitFileFailed`.

```java
Files.walkFileTree(
        start,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
```

Đây là đoạn minh họa. Cần hiểu hệ quả an ninh: một symlink trong cây được duyệt có thể trỏ tới dữ liệu **ngoài root ban đầu**. Nếu chỉ muốn quét dưới một ranh giới filesystem thực, không thể xem `SKIP_SUBTREE` hoặc kiểm tra chuỗi `Path.normalize()` là cơ chế bảo mật hoàn chỉnh.

Có thể không theo link, dùng `maxDepth`, kiểm tra real paths và kiểm soát quyền filesystem tùy yêu cầu; vẫn phải xem xét race condition khi thư mục bị đổi trong lúc duyệt.

### Nếu một thư mục xuất hiện dưới dạng symbolic link thì tên dir có giống nhau không?

Khi walker theo link, callback có thể nhận một `Path` mang vị trí link được duyệt, không tự động biến tất cả Path thành canonical real path. Không dùng `dir.getFileName().toString()` làm ranh giới bảo mật nếu một directory có thể được đặt lại tên hoặc symlink trỏ sang nơi khác. Các ví dụ bỏ `ignored` theo tên chỉ dành cho chính sách lọc đơn giản trong một cây được kiểm soát.

## 15. Có chắc thứ tự siblings là ổn định không?

**Không.** `Files.walkFileTree` không hứa sẽ duyệt các entry trong mỗi thư mục theo thứ tự tên. Các filesystem khác nhau, trạng thái directory và các thay đổi đồng thời có thể tạo thứ tự khác nhau.

Do đó, với mã:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    return FileVisitResult.SKIP_SIBLINGS;
}
```

“Bỏ sibling” nghĩa là **sibling chưa được duyệt**, không phải “tất cả file có tên đứng sau trong bảng chữ cái”. Nếu nghiệp vụ cần tìm **file có tên từ điển nhỏ nhất**, cần liệt kê và sắp xếp có chủ đích trước khi chọn; không dựa vào một traversal order ngầm.

Một chiến lược kiểm thử ổn định là:
- Tạo cây test có đúng một mục khi kiểm tra `TERMINATE`.
- Khi kiểm tra `SKIP_SIBLINGS`, chỉ assert **số mục được thăm** thay vì tên file đầu tiên.
- Khi kiểm tra `SKIP_SUBTREE`, assert một nhánh không được đi vào, trong khi các nhánh khác vẫn được xử lý.
- Không viết unit test yêu cầu chuỗi callback được phát theo thứ tự alphabetical trừ khi code tự đảm bảo thứ tự đó.

## 16. Bẫy khi dùng FileVisitResult để xóa cây thư mục

Một ứng dụng xóa đệ quy thường:

1. Xóa file trong `visitFile`.
2. Xóa directory trong `postVisitDirectory` (sau khi xóa các entry).

Nhưng nếu `preVisitDirectory` trả `SKIP_SUBTREE` cho một directory, **`postVisitDirectory` của directory đó không chạy**. Điều này có thể khiến folder vẫn còn nguyên, rồi nỗ lực xóa parent sau đó thất bại vì chưa rỗng.

Tương tự, khi `TERMINATE` xảy ra, nhiều post-callback chưa được thực thi. Không đặt công việc dọn dẹp bắt buộc (đóng resource hoặc xóa file tạm riêng) **chỉ trong `postVisitDirectory`** rồi giả định nó giống `finally`.

Với xóa đệ quy, phải xác định chính sách xử lý nhánh không xóa được và lỗi quyền truy cập. Khi phần còn lại của subtree bị bỏ qua, có thể cần giữ directory cha hoặc báo lỗi, không tự coi công việc hoàn thành.

**An toàn:** ví dụ bài học không tự động xóa cây tùy ý của người dùng. Các demo chỉ tạo và xóa chính những tệp/thư mục tạm mà chương trình đã tạo trong một phạm vi kiểm soát.

## 17. Duyệt cây để tìm file: dùng TERMINATE hay SKIP_SIBLINGS?

Giả sử tìm file tên `config.json` ở bất cứ đâu:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if ("config.json".equals(file.getFileName().toString())) {
        found = file;
        return FileVisitResult.TERMINATE;
    }
    return FileVisitResult.CONTINUE;
}
```

Nếu đã có kết quả đầu tiên và chỉ cần một file, `TERMINATE` đúng nghĩa hơn: **dừng toàn bộ cây**. Nếu trả `SKIP_SIBLINGS`, walker có thể quay lên duyệt các nhánh khác và tìm thêm file cùng tên, không phải hành vi mong muốn.

Ngược lại, nếu nghiệp vụ là “với mỗi directory, chỉ cần một file thỏa điều kiện, sau đó tiếp tục các directory khác”, `SKIP_SIBLINGS` tại một file có thể hợp lý, nhưng phải biết cấu trúc cây và nơi callback đang đứng. Nó loại các sibling còn lại tại cấp đó, không tự tạo quy tắc “mỗi thư mục đúng một file” trong mọi cây đệ quy phức tạp.

## 18. Một visitor cấu hình quy tắc duyệt

Trong ứng dụng thật, có thể xây một class visitor chịu trách nhiệm:

- Danh sách tên directory cần bỏ qua.
- Bộ đếm file và thống kê kích thước.
- Điều kiện tìm file để dừng.
- Chính sách lỗi (fail-fast hay best-effort).
- Giới hạn độ sâu, liên kết tượng trưng.

**Khung minh họa**:

```java
static class SelectiveVisitor extends SimpleFileVisitor<Path> {
    private final Set<String> omittedNames;
    private final String targetName;
    private Path found;

    SelectiveVisitor(Set<String> omittedNames, String targetName) {
        this.omittedNames = omittedNames;
        this.targetName = targetName;
    }

    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) {
        Path name = dir.getFileName();
        if (name != null
                && omittedNames.contains(name.toString())) {
            return FileVisitResult.SKIP_SUBTREE;
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (file.getFileName().toString().equals(targetName)) {
            found = file;
            return FileVisitResult.TERMINATE;
        }
        return FileVisitResult.CONTINUE;
    }

    Path found() {
        return found;
    }
}
```

Đây là **class minh họa**, yêu cầu import `Set`, `Path`, `SimpleFileVisitor`, `BasicFileAttributes`, `FileVisitResult`; không phải chương trình độc lập. Có thể dùng nó để tìm file đầu tiên dưới các nhánh được phép mà không mở rộng directory nằm trong `omittedNames`.

Lưu ý **tên trùng nhau ở nhiều vị trí**: áp dụng quy tắc theo `dir.getFileName()` sẽ bỏ qua mọi directory có tên ấy, không chỉ một path cụ thể. Nếu cần bỏ một subtree chính xác, so sánh Path đã xác định hoặc sử dụng một predicate có hợp đồng rõ ràng.

## 19. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả `SKIP_SUBTREE` từ `visitFile` để bỏ sibling | Không bỏ sibling; hành vi như `CONTINUE` | Dùng `SKIP_SIBLINGS` nếu đúng nhu cầu |
| Trả `SKIP_SIBLINGS` nhưng mong dừng cả cây | Các nhánh cấp trên khác còn có thể được thăm | Dùng `TERMINATE` |
| Trả `SKIP_SIBLINGS` trong `preVisitDirectory` nhưng mong vào dir hiện tại | Chính dir cũng không được đi vào | Dùng `CONTINUE` hoặc `SKIP_SUBTREE` tùy ý định |
| Dựa vào `postVisitDirectory` luôn chạy | Không chạy khi pre-visit skip hay terminate | Quản lý resource bằng `try-with-resources`/`finally` |
| Giả định duyệt theo tên alphabetical | Chọn “file đầu tiên” không ổn định | Liệt kê/sắp xếp có chủ đích |
| Coi `TERMINATE` là lỗi Java | Caller không biết lý do nếu không có state | Dùng result state hoặc exception phù hợp |
| Bỏ qua mọi `visitFileFailed` mà không báo | Kết quả thiếu nhưng trông như đầy đủ | Ghi nhận lỗi hoặc fail-fast |
| Bỏ qua `exc` ở `postVisitDirectory` | Lỗi iteration directory có thể bị mất | Xem/throw `exc` theo policy |
| Cho rằng maxDepth chỉ ảnh hưởng số file, không ảnh hưởng callback | Directory ở maxDepth có thể được thăm như file | Thiết kế đếm và logic đúng |
| Bật FOLLOW_LINKS mà không kiểm soát | Có thể đi ra ngoài root hoặc gặp vòng | Xác định policy link, lỗi và giới hạn |
| Lọc `Files.walk(...).filter(...)` rồi nghĩ đã prune subtree | Walker vẫn có thể đi vào nhánh đã lọc | Dùng `walkFileTree` và pre-visit |
| Đọc số liệu attr từ các thời điểm khác nhau rồi coi nhất quán tuyệt đối | File có thể đổi trong lúc quét | Xác định tolerance/snapshot strategy |
| Duyệt/xóa trên path không tin cậy chỉ với normalize | Symlink/traversal/race không được ngăn | Áp dụng kiểm soát quyền và cơ chế filesystem-aware |

## 20. Checklist trước khi triển khai

Khi viết visitor, trả lời rõ:

1. **Điểm bắt đầu** là file hay directory? Có khả năng symlink không?
2. Có cần theo symbolic link không? `FOLLOW_LINKS` ảnh hưởng biên truy cập ra sao?
3. `maxDepth` bao nhiêu, và directory ở giới hạn được tính thế nào?
4. Muốn bỏ đúng một directory hay mọi directory có cùng tên?
5. Có cần duyệt đầy đủ hay được phép thiếu nhánh?
6. Đang định trả `SKIP_SUBTREE` từ **pre-visit** hay nhầm callback?
7. `SKIP_SIBLINGS` có phù hợp với mục tiêu từng directory không?
8. Khi tìm được file, có cần trả `TERMINATE` và lưu `found`?
9. Lỗi đọc metadata/directory được xử lý tại `visitFileFailed`/`postVisitDirectory` thế nào?
10. Có giả định thứ tự sibling nào không được API bảo đảm?
11. Có tác vụ hậu xử lý nào đặt trong post-visit nhưng sẽ bị bỏ qua khi skip/terminate không?
12. Nếu filesystem thay đổi đồng thời, kết quả quét được mô tả là snapshot hay best-effort?

## 21. Bài tập thực hành

1. Chạy `SkipSubtreeDemo`; đổi tên `ignored` thành `cache` cả ở cây và visitor, kiểm tra số file vẫn bằng 1.
2. Thêm một file thứ hai vào `keep`; giải thích vì sao `SKIP_SUBTREE` chỉ bỏ `ignored`, không ảnh hưởng `keep`.
3. Trong `SkipSiblingsDemo`, đổi kết quả `visitFile` từ `SKIP_SIBLINGS` thành `CONTINUE`, dự đoán số file sẽ thành 2 và `groupPost` vẫn true.
4. Đổi `SKIP_SIBLINGS` thành `SKIP_SUBTREE` trong `visitFile`, giải thích vì sao vẫn duyệt 2 file.
5. Trong `TerminateWalkDemo`, chuyển `TERMINATE` thành `CONTINUE`, kiểm tra `rootPost` trở thành true.
6. Thử `preVisitDirectory(root)` trả `SKIP_SUBTREE` và ghi lại việc `visitFile`/`postVisitDirectory(root)` có được gọi không.
7. Viết visitor dùng `visitFileFailed` để ghi log và `CONTINUE`, sau đó so sánh với phiên bản ném lại `exc`. Thảo luận tình huống quyền truy cập thay đổi đồng thời.
8. Tạo visitor đếm số directory và file với `maxDepth=0`, `1`, `2`. Ghi rõ callback nào nhận directory khi đến mức giới hạn.
9. Dùng `FileVisitOption.FOLLOW_LINKS` với cây kiểm thử có symbolic link vòng (trên filesystem hỗ trợ); kiểm tra `visitFileFailed` nhận loại exception gì.
10. Viết visitor tìm tên file cụ thể, lưu vào `found` và trả `TERMINATE`. Đảm bảo caller phân biệt “không tìm thấy” với “lỗi trong khi duyệt”.
11. Dùng `SKIP_SIBLINGS` tại `preVisitDirectory` trong một cây có hai thư mục cùng cấp; giải thích vì sao chỉ có một số nhánh được duyệt và thứ tự không được bảo đảm.
12. Mô phỏng logic xóa cây có post-visit rồi chủ động skip một directory; giải thích vì sao parent có thể chưa rỗng khi đến lượt xử lý.
13. So sánh `Files.walkFileTree` với `Files.walk`: khi nào filter đủ và khi nào nhất thiết phải prune subtree?
14. Viết một test không phụ thuộc thứ tự filesystem để xác minh đủ cả bốn giá trị `FileVisitResult`.

## 22. Tổng kết

`FileVisitResult` là ngôn ngữ điều khiển hành trình duyệt cây thư mục của `Files.walkFileTree`:

- **`CONTINUE`:** tiếp tục duyệt theo cơ chế bình thường.
- **`SKIP_SUBTREE`:** bỏ entry bên trong directory **khi được trả từ `preVisitDirectory`**. Từ callback khác, nó tương đương `CONTINUE`.
- **`SKIP_SIBLINGS`:** bỏ những entry **chưa duyệt cùng cấp**. Nếu trả từ pre-visit, chính directory đó cũng không được đi vào và không có post-visit cho nó.
- **`TERMINATE`:** dừng toàn bộ hành trình, không chờ phần post-visit còn lại.

Đừng nhầm các giá trị điều khiển với ngoại lệ: khi lỗi I/O cần được truyền cho caller, ném `IOException` hoặc lưu trạng thái lỗi một cách rõ ràng. Đừng giả định thứ tự các sibling hay cho rằng `postVisitDirectory` luôn được gọi. Với yêu cầu duyệt hoặc xóa có liên quan đến bảo mật, đặc biệt khi dùng symbolic link, phải xem xét provider, quyền truy cập, thay đổi đồng thời và giới hạn độ sâu.

### Tài liệu tham khảo

- [Java SE 17: `FileVisitResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html) — bốn giá trị và phạm vi ngữ nghĩa.
- [Java SE 17: `FileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html) — bốn callback và khi nào được gọi.
- [Java SE 17: `SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html) — hành vi mặc định và xử lý lỗi.
- [Java SE 17: `Files.walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)) — duyệt cây với visitor.
- [Dev.java: Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/) — các ví dụ duyệt/bỏ nhánh và cách điều khiển.
