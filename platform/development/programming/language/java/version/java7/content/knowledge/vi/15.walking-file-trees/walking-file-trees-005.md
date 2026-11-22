# Đi qua cây tệp bằng `Files.walkFileTree` trong Java (Java 7+)

> **Phạm vi:** `java.nio.file.Files.walkFileTree` là API NIO.2 xuất hiện từ **Java 7** và vẫn là cách phù hợp trong Java 17+ để đi qua một cây thư mục theo chiều sâu, xử lý từng tệp/thư mục, kiểm soát nhánh cần bỏ qua, giới hạn độ sâu và xử lý lỗi I/O. Bài tập trung vào cách dùng `FileVisitor`/`SimpleFileVisitor`, các callback và `FileVisitResult`, không đi sang các API legacy. Chương trình chạy độc lập dưới đây sử dụng **JDK 17**; `Path.of` và `Files.writeString/readString` có từ Java 11, còn phần lõi `walkFileTree`, `Path` và `FileVisitor` có từ Java 7.

## 1. Khi nào cần đi qua cây tệp?

Một **cây tệp** gồm thư mục gốc, các thư mục con và những tệp bên trong. Khi chỉ cần liệt kê các mục **trực tiếp** trong một thư mục, có thể dùng `Files.list(...)`. Nhưng khi cần xem cả thư mục con, bạn có thể cần duyệt **đệ quy**:

```text
project/
  README.md
  src/
    main/
      App.java
    test/
      AppTest.java
  build/
    app.class
```

Ví dụ câu hỏi:

- Có bao nhiêu tệp thường `.java` dưới `src`?
- Tổng kích thước các tệp thường trong một cây là bao nhiêu?
- Có nên **bỏ qua** thư mục `build` khi thống kê source?
- Làm sao sao chép một cây sang một thư mục khác mà giữ lại cấu trúc tên?
- Nếu đọc thông tin một mục thất bại, nên dừng hay tiếp tục?
- Nếu chỉ muốn duyệt tối đa hai cấp, không đi xuống sâu hơn thì làm thế nào?

`walkFileTree` giải quyết phần **đi lại và thông báo sự kiện** của quá trình đó. Mỗi khi gặp một thư mục/tệp, API gọi method callback tương ứng. Ứng dụng quyết định làm gì với đối tượng hiện tại và trả một `FileVisitResult` để kiểm soát hành trình tiếp theo.

**Không có mặc định “tất cả mọi tệp đều là regular file”.** Có thể gặp thư mục, symbolic link, tệp đặc biệt và I/O failure. `BasicFileAttributes` giúp phân biệt loại đối tượng trước khi áp dụng phép tính hoặc thao tác.

## 2. API chính và những import thường dùng

Có hai overload cốt lõi:

```java
Files.walkFileTree(Path start, FileVisitor<? super Path> visitor);

Files.walkFileTree(
        Path start,
        Set<FileVisitOption> options,
        int maxDepth,
        FileVisitor<? super Path> visitor
);
```

Đây là **cú pháp gọi/khai báo rút gọn để học**, không phải hai phương thức cần tự định nghĩa. Trong Java SE 17 chúng thuộc `java.nio.file.Files`.

| Tham số | Vai trò | Cần lưu ý |
| --- | --- | --- |
| `start` | Vị trí bắt đầu duyệt | Tham chiếu `Path`, có thể là file hoặc directory |
| `visitor` | Đối tượng nhận sự kiện | Thường dùng anonymous class kế thừa `SimpleFileVisitor<Path>` |
| `options` | Lựa chọn khi duyệt | Đáng chú ý nhất là `FOLLOW_LINKS` |
| `maxDepth` | Số cấp tối đa tính từ start | Root có độ sâu 0; giá trị không âm |
| Giá trị trả về | `Path start` khi hoàn tất bình thường | Không phải danh sách kết quả; kết quả được visitor tự thu thập |

Các import khi cần đa số chức năng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileVisitResult;
import java.nio.file.FileVisitOption;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
```

**Một lượt duyệt đơn giản:**

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
            throws IOException {
        System.out.println(file);
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là **snippet** trong method có `throws IOException`, với `Path root` và import thích hợp. Nó in các tệp/entries đã được thăm theo cách API callback quy định; không bảo đảm thứ tự sibling giống nhau trên mọi hệ điều hành. Mặc định **không đi theo symbolic links**.

### 2.1. Vì sao dùng `SimpleFileVisitor`?

`FileVisitor<T>` là interface có **bốn method** mà class tự triển khai interface phải định nghĩa. `SimpleFileVisitor<T>` cung cấp hành vi mặc định hợp lý để ta chỉ override những callback cần thiết.

Ví dụ nếu chỉ muốn thống kê file, thường chỉ cần override `visitFile`; các callback mặc định tiếp tục đi qua thư mục. Khi lỗi I/O xảy ra, `SimpleFileVisitor` mặc định **ném lại ngoại lệ** ở `visitFileFailed` và ở `postVisitDirectory` nếu tham số `exc` không null. Vì vậy nó **không âm thầm bỏ mọi lỗi**.

Đối với bài tập cần chính sách xử lý lỗi riêng, override thêm `visitFileFailed`/`postVisitDirectory`.

### 2.2. `Path.of` và Java 7

Các đoạn code dưới đây dùng `Path.of(...)` vì target Java 17. Nếu viết chương trình phải tương thích **Java 7**, tạo Path bằng `java.nio.file.Paths.get(...)`:

```java
Path path = java.nio.file.Paths.get("data", "reports");
```

`Path.of(...)` xuất hiện từ Java 11. Thay cách tạo Path không làm mất đi tính hiện hành của `walkFileTree` từ Java 7.

## 3. Mô hình đi qua cây: duyệt theo chiều sâu

`walkFileTree` đi theo kiểu **depth-first traversal**: khi gặp một thư mục, nó có thể đi vào các mục con rồi mới hoàn tất callback cho thư mục đó.

Một hành trình qua nhánh đơn giản:

```text
root/
  sub/
    inner/
      item.txt
```

Các sự kiện nếu visitor đi tiếp ở mỗi bước:

```text
preVisitDirectory(root)
  preVisitDirectory(sub)
    preVisitDirectory(inner)
      visitFile(item.txt)
    postVisitDirectory(inner)
  postVisitDirectory(sub)
postVisitDirectory(root)
```

Đặc điểm quan trọng:

1. `preVisitDirectory` được gọi **trước khi** các entry của thư mục được duyệt.
2. `visitFile` được gọi khi một tệp/entry đã có attributes được thăm; còn có trường hợp directory tại giới hạn `maxDepth` được chuyển tới `visitFile`.
3. `postVisitDirectory` được gọi **sau khi** việc duyệt các entries trong thư mục hoàn tất hoặc kết thúc sớm theo ngữ nghĩa API, nếu thư mục đã được mở/duyệt như quy định.
4. `visitFileFailed` nhận các trường hợp API không đọc được attributes/mở được directory, hoặc một số lỗi traversal khác.
5. **Thứ tự giữa các mục con cùng cấp không được bảo đảm.** Không viết logic phụ thuộc tên `a.txt` luôn được duyệt trước `b.txt`.

Nếu chương trình cần bảng kết quả sắp xếp theo tên, hãy **thu thập và sort** sau khi duyệt; không giả định filesystem cung cấp sẵn thứ tự đó.

## 4. Bốn callback của `FileVisitor`

Một visitor hoàn chỉnh có bốn callback có thể override:

| Callback | Khi nào gọi | Tham số chính | Công dụng thường gặp |
| --- | --- | --- | --- |
| `preVisitDirectory(Path dir, BasicFileAttributes attrs)` | Trước khi duyệt nội dung thư mục | Path và attributes của thư mục | Tạo thư mục tương ứng ở đích, log trước, bỏ qua nhánh |
| `visitFile(Path file, BasicFileAttributes attrs)` | Khi thăm file/entry đã đọc được attributes | Path và attributes | Thống kê, lọc theo đuôi tệp, kiểm tra kích thước |
| `visitFileFailed(Path file, IOException exc)` | Khi không thể thăm một entry | Path và lỗi I/O | Ném lại, ghi nhận rồi tiếp tục, hoặc dừng theo chính sách |
| `postVisitDirectory(Path dir, IOException exc)` | Sau khi duyệt thư mục hoặc khi iteration kết thúc sớm | Path và lỗi duyệt thư mục nếu có | Hoàn tất xử lý hậu kỳ, kiểm tra lỗi, dọn thư mục |

### 4.1. `preVisitDirectory`

Thường dùng để:
- Ghi nhận “đã bước vào” thư mục.
- Tạo thư mục đối ứng khi **copy tree**.
- Trả `SKIP_SUBTREE` nếu thư mục không cần duyệt.
- Dừng nếu gặp phạm vi mà ứng dụng không được phép tiếp tục.

Nếu method trả `CONTINUE`, walker xem xét các entry của thư mục. Nếu trả `SKIP_SUBTREE`, không duyệt các entry bên dưới và không gọi `postVisitDirectory` cho thư mục đã bị skip. Nếu trả `SKIP_SIBLINGS` từ `preVisitDirectory` thì vừa không duyệt subtree đó, vừa không duyệt các sibling còn lại ở cấp tương ứng.

### 4.2. `visitFile`

Method nhận `BasicFileAttributes attrs`. Ví dụ:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (attrs.isRegularFile() && file.toString().endsWith(".txt")) {
        System.out.println(file + " bytes=" + attrs.size());
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **snippet bên trong class `SimpleFileVisitor<Path>`**, không phải chương trình độc lập.

`attrs.isRegularFile()` giúp tránh xem mọi entry là file thường. `attrs.size()` là kích thước theo metadata được đọc tại thời điểm traversal; file có thể thay đổi sau đó. Khi so sánh đường dẫn/đuôi tệp, chú ý tên file và quy tắc extension theo ứng dụng; không giả định mọi hệ điều hành phân biệt chữ hoa/thường giống nhau.

### 4.3. `visitFileFailed`

Default `SimpleFileVisitor` thường **ném lại lỗi I/O**. Nếu chỉ muốn thống kê best-effort, có thể chủ động ghi lỗi rồi tiếp tục:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc) {
    System.err.println("Could not inspect: " + file.getFileName());
    return FileVisitResult.CONTINUE;
}
```

Đây là **snippet**; cần cân nhắc log đường dẫn có thể nhạy cảm. Chính sách `CONTINUE` có thể chấp nhận với một báo cáo “đã bỏ qua 2 mục vì lỗi”, nhưng **không phù hợp** nếu ứng dụng yêu cầu kiểm kê đầy đủ để xác thực hoặc tuân thủ.

### 4.4. `postVisitDirectory`

Method này nhận `IOException exc`, có thể là `null` nếu iteration bình thường. Một cách giữ fail-fast:

```java
@Override
public FileVisitResult postVisitDirectory(Path dir, IOException exc)
        throws IOException {
    if (exc != null) throw exc;
    return FileVisitResult.CONTINUE;
}
```

Đây là snippet. Với một thao tác **xóa cây**, callback hậu kỳ thường cần thiết vì phải xử lý các entry trước khi thư mục rỗng; nhưng việc xóa dữ liệu là tác vụ nguy hiểm, không được áp dụng chỉ vì nhìn thấy ví dụ traversal. Trong bài, các chương trình chỉ xóa tài nguyên tạm **do chính test tạo**.

## 5. Chương trình 1: duyệt và thống kê tệp, thư mục, kích thước

Lưu thành `WalkTreeSummaryDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public class WalkTreeSummaryDemo {
    static String name(Path root, Path path) {
        Path relative = root.relativize(path);
        String s = relative.toString().replace('\\', '/');
        return s.isEmpty() ? "." : s;
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-summary-");
        Path docs = root.resolve("docs");
        Path cache = root.resolve("cache");
        Path note = docs.resolve("a.txt");
        Path bytes = cache.resolve("b.bin");
        Path readme = root.resolve("readme.txt");
        try {
            Files.createDirectory(docs);
            Files.createDirectory(cache);
            Files.writeString(note, "hello", StandardCharsets.UTF_8);
            Files.write(bytes, new byte[] {1, 2});
            Files.writeString(readme, "R", StandardCharsets.UTF_8);

            List<String> folders = new ArrayList<>();
            List<String> files = new ArrayList<>();
            long[] bytesTotal = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    folders.add(name(root, dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (attrs.isRegularFile()) {
                        files.add(name(root, file));
                        bytesTotal[0] += attrs.size();
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
            Collections.sort(folders);
            Collections.sort(files);
            System.out.println("dirs=" + folders);
            System.out.println("files=" + files);
            System.out.println("fileCount=" + files.size());
            System.out.println("totalBytes=" + bytesTotal[0]);
        } finally {
            Files.deleteIfExists(note);
            Files.deleteIfExists(bytes);
            Files.deleteIfExists(readme);
            Files.deleteIfExists(docs);
            Files.deleteIfExists(cache);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac -encoding UTF-8 --release 17 WalkTreeSummaryDemo.java
java WalkTreeSummaryDemo
```

Stdout **đã kiểm chứng bằng chương trình thật**:

```text
dirs=[., cache, docs]
files=[cache/b.bin, docs/a.txt, readme.txt]
fileCount=3
totalBytes=8
```

### 5.1. Tại sao output ổn định?

- Test tạo **thư mục tạm riêng**, không đọc bất kỳ thư mục thực nào của người dùng.
- Thư mục gốc được biểu diễn bằng `"."` khi `root.relativize(root)` trả empty Path để tránh in tên temp có phần đuôi ngẫu nhiên.
- Khi hiển thị, code đổi `\` sang `/`; đó là thao tác định dạng output, **không phải cách xây path cho filesystem**.
- Danh sách được `Collections.sort` **sau khi duyệt**; `walkFileTree` không bảo đảm thứ tự của siblings.
- Dữ liệu tạo trong demo có ba regular files: `readme.txt` = 1 byte, `a.txt` chứa `hello` = 5 byte, `b.bin` = 2 byte. Tổng = **8 byte**.
- Các thư mục `root`, `docs`, `cache` được ghi nhận từ `preVisitDirectory`, không bị cộng vào số file thường.
- `finally` dọn chính xác các file/thư mục tạm do demo tạo, không phải một lệnh xóa đệ quy trên input tùy ý.

### 5.2. Vì sao dùng `BasicFileAttributes` thay vì luôn gọi `Files.size(file)`?

`walkFileTree` đã đọc `BasicFileAttributes` để xét mục hiện tại và truyền chúng vào `visitFile`. Dùng `attrs.size()` giảm việc phải gọi một truy vấn metadata khác nếu thông tin cần thiết đã có sẵn. Tuy vậy attributes chỉ phản ánh một **ảnh chụp ở thời điểm đọc**; nếu chương trình khác sửa file ngay sau đó, kết quả không phải một snapshot nguyên tử của toàn bộ cây.

Nếu cần tính toán độ lớn **có thể vượt `long`**, cũng phải cân nhắc overflow. Ví dụ demo dùng `long[]` để tiện cập nhật từ anonymous visitor; nó không phải kiểu counter đồng bộ cho môi trường đa luồng.

## 6. Chương trình 2: quan sát vòng đời callback

Để có output không phụ thuộc thứ tự sibling, demo tạo một cây **chỉ có một nhánh**:

```text
root/
  sub/
    inner/
      item.txt
```

Lưu thành `WalkTreeCallbacksDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public class WalkTreeCallbacksDemo {
    static String rel(Path root, Path item) {
        String text = root.relativize(item).toString().replace('\\', '/');
        return text.isEmpty() ? "." : text;
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-events-");
        Path sub = root.resolve("sub");
        Path inner = sub.resolve("inner");
        Path file = inner.resolve("item.txt");
        try {
            Files.createDirectory(sub);
            Files.createDirectory(inner);
            Files.writeString(file, "x", StandardCharsets.UTF_8);

            List<String> events = new ArrayList<>();
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    events.add("pre:" + rel(root, dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path item, BasicFileAttributes attrs) {
                    events.add("file:" + rel(root, item));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path dir, IOException exc)
                        throws IOException {
                    if (exc != null) throw exc;
                    events.add("post:" + rel(root, dir));
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("events=" + events);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(inner);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 WalkTreeCallbacksDemo.java
java WalkTreeCallbacksDemo
```

Stdout đã kiểm chứng:

```text
events=[pre:., pre:sub, pre:sub/inner, file:sub/inner/item.txt, post:sub/inner, post:sub, post:.]
```

**Đọc output:**

- `pre:.` mở đầu lượt duyệt root.
- `pre:sub` và `pre:sub/inner` xảy ra **trước khi** visitor thăm file dưới chúng.
- `file:sub/inner/item.txt` xảy ra khi đến file thường.
- `post:sub/inner`, `post:sub`, `post:.` xảy ra **ngược thứ tự đi vào** vì đã đi hết mỗi nhánh con.

Điều này tương tự việc duyệt cây với **preorder ở thư mục** và **postorder để hoàn tất thư mục**. Đừng suy ra `postVisitDirectory` luôn được gọi cho mọi directory nếu visitor trả `SKIP_SUBTREE` hoặc `TERMINATE` trước đó.

## 7. `FileVisitResult`: điều khiển hành trình duyệt

`FileVisitor` trả một trong bốn giá trị từ enum `java.nio.file.FileVisitResult`:

| Giá trị | Nghĩa thông thường | Nơi quan trọng nhất |
| --- | --- | --- |
| `CONTINUE` | Tiếp tục theo quy trình bình thường | Tất cả callback |
| `SKIP_SUBTREE` | Không đi vào các entry của thư mục hiện tại | `preVisitDirectory` |
| `SKIP_SIBLINGS` | Bỏ qua các mục cùng cấp còn lại | Ví dụ `visitFile` hoặc `preVisitDirectory` |
| `TERMINATE` | Kết thúc toàn bộ lượt duyệt | Khi tìm đủ kết quả hoặc có chính sách dừng |

**Sắc thái quan trọng trong Javadoc:**

1. `SKIP_SUBTREE` **chỉ có tác dụng riêng** khi trả từ `preVisitDirectory`. Trong các callback khác, nó được xử lý như `CONTINUE`.
2. `SKIP_SIBLINGS` từ `preVisitDirectory` cũng bỏ subtree hiện tại; đồng thời không gọi `postVisitDirectory` cho directory đã skip.
3. `SKIP_SIBLINGS` không có nghĩa **dừng toàn bộ cây**; nó tác động tới những sibling còn lại theo ngữ cảnh duyệt.
4. `TERMINATE` dừng toàn bộ quá trình duyệt. Nếu visitor muốn báo một lỗi cần caller nhận biết, có thể **ném exception** thay vì chỉ `TERMINATE` và để caller tưởng việc đi qua cây hoàn tất đầy đủ.

### 7.1. Bỏ qua thư mục build/cache

```java
@Override
public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
    Path name = dir.getFileName();
    if (name != null && name.toString().equals("build")) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là **snippet** trong `SimpleFileVisitor<Path>`. Nó cấm vào mọi thư mục có tên cuối `build`, kể cả khi cây có nhiều cấp. Nếu chỉ muốn skip một nhánh xác định, hãy so sánh **đúng Path** thay vì mọi tên giống nhau.

Lưu ý: việc bỏ qua nhánh không phải “tệp đã được kiểm tra và xác nhận an toàn”; nó có nghĩa tệp bên dưới **không được thăm**.

### 7.2. Dừng sau khi tìm được file

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (attrs.isRegularFile() &&
            file.getFileName().toString().equals("wanted.txt")) {
        found[0] = file;
        return FileVisitResult.TERMINATE;
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là snippet với `Path[] found` đã có. Trả `TERMINATE` phù hợp cho bài toán “tìm được một kết quả là đủ”. Nếu cần biết **tất cả** file có tên đó, phải tiếp tục duyệt và không dừng sớm.

### 7.3. `SKIP_SIBLINGS` không phải `SKIP_SUBTREE`

Ví dụ một thư mục hiện có nhiều tệp cùng cấp, khi visitor trả `SKIP_SIBLINGS` từ `visitFile` đầu tiên, các sibling còn lại của cấp đó bị bỏ qua. Việc duyệt có thể tiếp tục ở cấp cha khi thích hợp. Ngược lại, `SKIP_SUBTREE` dùng từ `preVisitDirectory` để không đi vào **các descendants của chính directory đó** nhưng vẫn cho phép duyệt siblings khác của directory.

**Không gắn ý nghĩa dừng hoàn toàn cho `SKIP_SIBLINGS`.** Muốn dừng toàn traversal thì dùng `TERMINATE`.

## 8. Giới hạn độ sâu bằng overload có `maxDepth`

Dạng có nhiều tham số:

```java
Files.walkFileTree(
        root,
        EnumSet.noneOf(FileVisitOption.class),
        1,
        visitor
);
```

Đây là snippet với `root` và `visitor` đã có. `EnumSet.noneOf(...)` nghĩa là không bật `FOLLOW_LINKS`, còn `maxDepth=1` cho phép duyệt root ở **độ sâu 0** và các entry trực tiếp của root ở **độ sâu 1**.

**Một chi tiết quan trọng thường bị bỏ qua:** khi chạm giới hạn độ sâu, nếu entry là **directory**, `walkFileTree` gọi `visitFile` cho directory đó thay vì đi xuống và gọi `preVisitDirectory` cho nó. Do đó khi dùng giới hạn chiều sâu, **`visitFile` không đồng nghĩa attributes chắc chắn là regular file**.

Ví dụ:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (attrs.isDirectory()) {
        // Directory ở maxDepth đã được thăm như một entry không đi sâu hơn.
    } else if (attrs.isRegularFile()) {
        // Regular file.
    }
    return FileVisitResult.CONTINUE;
}
```

Đây là snippet trong `SimpleFileVisitor<Path>`. Một chương trình thống kê các file nên có điều kiện `attrs.isRegularFile()`.

### 8.1. Depth 0 và giới hạn hợp lệ

- `maxDepth=0` chỉ xét `start`; nếu start là directory thì callback `visitFile` có thể nhận chính directory tại giới hạn.
- `maxDepth=1` xét start và các entry trực tiếp của start.
- `maxDepth=2` thêm một tầng descendants nữa.
- Dùng `Integer.MAX_VALUE` nếu muốn duyệt tối đa theo giới hạn biểu diễn của API.
- `maxDepth` âm không hợp lệ, gây `IllegalArgumentException`.

Đừng nhầm **độ sâu** với tổng số entries: `maxDepth=1` vẫn có thể duyệt hàng triệu tệp nếu root chứa hàng triệu mục trực tiếp. Nếu cần hạn chế tổng lượng công việc, tự đếm và trả `TERMINATE` hoặc áp dụng cơ chế timeout/giới hạn nghiệp vụ phù hợp.

## 9. Chương trình 3: `SKIP_SUBTREE`, `maxDepth`, `SKIP_SIBLINGS`, `TERMINATE`

Lưu thành `WalkTreeControlDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public class WalkTreeControlDemo {
    static String rel(Path root, Path path) {
        return root.relativize(path).toString().replace('\\', '/');
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-control-");
        Path keep = root.resolve("keep");
        Path ignored = root.resolve("ignored");
        Path one = keep.resolve("one.txt");
        Path hidden = ignored.resolve("hidden.txt");
        Path top = root.resolve("top.txt");
        Path onlyFiles = Files.createTempDirectory("tree-siblings-");
        Path a = onlyFiles.resolve("a.txt");
        Path b = onlyFiles.resolve("b.txt");
        Path c = onlyFiles.resolve("c.txt");
        try {
            Files.createDirectory(keep);
            Files.createDirectory(ignored);
            Files.writeString(one, "1", StandardCharsets.UTF_8);
            Files.writeString(hidden, "H", StandardCharsets.UTF_8);
            Files.writeString(top, "T", StandardCharsets.UTF_8);

            List<String> included = new ArrayList<>();
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (dir.equals(ignored)) return FileVisitResult.SKIP_SUBTREE;
                    return FileVisitResult.CONTINUE;
                }
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    included.add(rel(root, file));
                    return FileVisitResult.CONTINUE;
                }
            });
            Collections.sort(included);
            System.out.println("withoutIgnored=" + included);

            List<String> atOne = new ArrayList<>();
            Files.walkFileTree(root, EnumSet.noneOf(FileVisitOption.class), 1,
                    new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    atOne.add((attrs.isDirectory() ? "D:" : "F:") + rel(root, file));
                    return FileVisitResult.CONTINUE;
                }
            });
            Collections.sort(atOne);
            System.out.println("depthOne=" + atOne);

            Files.writeString(a, "a", StandardCharsets.UTF_8);
            Files.writeString(b, "b", StandardCharsets.UTF_8);
            Files.writeString(c, "c", StandardCharsets.UTF_8);
            int[] skipped = {0};
            Files.walkFileTree(onlyFiles, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    skipped[0]++;
                    return FileVisitResult.SKIP_SIBLINGS;
                }
            });
            System.out.println("skipSiblingsVisits=" + skipped[0]);

            int[] terminated = {0};
            Files.walkFileTree(onlyFiles, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    terminated[0]++;
                    return FileVisitResult.TERMINATE;
                }
            });
            System.out.println("terminateVisits=" + terminated[0]);
        } finally {
            Files.deleteIfExists(one);
            Files.deleteIfExists(hidden);
            Files.deleteIfExists(top);
            Files.deleteIfExists(keep);
            Files.deleteIfExists(ignored);
            Files.deleteIfExists(root);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(c);
            Files.deleteIfExists(onlyFiles);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 WalkTreeControlDemo.java
java WalkTreeControlDemo
```

Stdout đã kiểm chứng:

```text
withoutIgnored=[keep/one.txt, top.txt]
depthOne=[D:ignored, D:keep, F:top.txt]
skipSiblingsVisits=1
terminateVisits=1
```

### 9.1. Tại sao `withoutIgnored` không có `hidden.txt`?

Trong `preVisitDirectory`, khi visitor nhận đường dẫn `ignored`, nó trả `SKIP_SUBTREE` nên API **không duyệt** `ignored/hidden.txt`. Nhánh `keep` vẫn được duyệt và các tệp trực tiếp của root vẫn được xét. Sau khi sort, chỉ còn `keep/one.txt` và `top.txt`.

Đây là mẫu phù hợp để bỏ qua thư mục build, cache hoặc output khi thống kê source. **Không** suy ra `SKIP_SUBTREE` xóa hoặc khóa quyền truy cập thư mục bị bỏ qua; nó chỉ điều khiển lượt duyệt hiện tại.

### 9.2. Tại sao `depthOne` vẫn hiển thị hai thư mục?

Với `maxDepth=1`, `keep` và `ignored` nằm đúng giới hạn độ sâu. Chúng được chuyển tới `visitFile` với `attrs.isDirectory()==true`, nên demo ghi tiền tố `D:`. File `top.txt` nằm cùng cấp và được ghi `F:`.

Không có nội dung bên dưới `keep`/`ignored`, tức `one.txt` và `hidden.txt`, vì các file này nằm ở độ sâu 2. Demo dùng thuộc tính loại entry thay vì tên để xác định loại.

### 9.3. Tại sao demo `SKIP_SIBLINGS` và `TERMINATE` không in tên tệp cụ thể?

Trong `onlyFiles` có ba regular files cùng cấp. Thứ tự sibling **không được bảo đảm**, nên file nào được thăm đầu tiên có thể khác giữa các lần chạy.

- Visitor đầu trả `SKIP_SIBLINGS` sau file thứ nhất; không duyệt những file cùng cấp còn lại, nên `skipSiblingsVisits=1`.
- Visitor sau trả `TERMINATE` sau file đầu; dừng toàn bộ lượt duyệt, nên `terminateVisits=1`.

Kết quả đếm là ổn định trong fixture test này; tên “file đầu tiên” không được hard-code.

## 10. Lỗi I/O trong lúc duyệt: ném lại hay bỏ qua?

Có thể lỗi xảy ra khi:
- File hoặc directory đã bị đổi/xóa sau khi nhận input.
- Quyền đọc metadata hoặc mở thư mục bị từ chối.
- Ổ đĩa/network filesystem bị mất kết nối.
- Theo symbolic link gây vòng lặp hoặc trạng thái không thể đọc được.
- Chính callback của ứng dụng ném `IOException`.

### 10.1. Hai nơi xử lý lỗi khác nhau

**`visitFileFailed(Path, IOException)`** được gọi khi một entry không thể thăm bình thường. Ví dụ không đọc được attributes hoặc không mở được thư mục.

**`postVisitDirectory(Path, IOException)`** được gọi sau khi duyệt thư mục hoặc khi iteration của nó kết thúc sớm theo hợp đồng. Nếu quá trình đọc directory stream gặp I/O error, tham số `exc` có thể **không null**.

Đây không phải một lời hứa rằng mọi exception từ mọi callback đều chuyển qua `visitFileFailed`. Nếu code của bạn tự ném `IOException` trong `visitFile`, nó có thể **lan ra khỏi `walkFileTree`** và hủy duyệt. Vì vậy phải thiết kế lỗi theo đúng lớp phát sinh.

### 10.2. Chính sách fail-fast

Dùng default `SimpleFileVisitor` hoặc override nhưng ném lại:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException {
    throw exc;
}
```

Phù hợp khi một lượt quét thiếu file là không thể chấp nhận, như tạo manifest bắt buộc đầy đủ.

### 10.3. Chính sách best-effort

Ví dụ quét nội dung để hiển thị sơ bộ có thể bỏ qua một số entry, nhưng nên **đếm lỗi**, báo tổng số file đã đọc thành công và số file không thể xử lý:

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc) {
    failures.add(file);
    return FileVisitResult.CONTINUE;
}
```

Đây là snippet với `Collection<Path> failures` đã có. **Không kết luận “quét đầy đủ”** khi `failures` khác rỗng. Hạn chế log raw đường dẫn có thông tin nhạy cảm nếu chúng xuất hiện trong thông báo công khai.

### 10.4. Vòng lặp và khởi động sai

Nếu `start` đã bị xóa trước khi gọi `walkFileTree`, callback `visitFileFailed` có thể nhận một `NoSuchFileException`. Nếu visitor trả `CONTINUE`, lượt duyệt có thể kết thúc bình thường dù **chưa thăm được file nào**. Điều này phù hợp với kiểu best-effort; nếu cần xác minh tồn tại, nên **ném lại**.

## 11. Chương trình 4: kiểm chứng `visitFileFailed` và exception do visitor ném

Lưu thành `WalkTreeFailureDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class WalkTreeFailureDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-errors-");
        Path missing = root.resolve("not-here.txt");
        Path file = root.resolve("exists.txt");
        try {
            boolean[] failedVisited = {false};
            Path returned = Files.walkFileTree(missing, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(Path path, IOException error) {
                    failedVisited[0] = true;
                    System.out.println("failedType=" + error.getClass().getSimpleName());
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("handledFailure=" + failedVisited[0]);
            System.out.println("returnedStart=" + returned.equals(missing));

            try {
                Files.walkFileTree(missing, new SimpleFileVisitor<Path>() {});
                throw new AssertionError("Missing root should fail");
            } catch (NoSuchFileException expected) {
                System.out.println("defaultHandler=" + expected.getClass().getSimpleName());
            }

            Files.writeString(file, "X", StandardCharsets.UTF_8);
            try {
                Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult visitFile(Path path, BasicFileAttributes attrs)
                            throws IOException {
                        throw new IOException("simulated visitor failure");
                    }
                });
                throw new AssertionError("Visitor exception should propagate");
            } catch (IOException expected) {
                System.out.println("visitorError=" + expected.getMessage());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 WalkTreeFailureDemo.java
java WalkTreeFailureDemo
```

Stdout trên provider thử nghiệm:

```text
failedType=NoSuchFileException
handledFailure=true
returnedStart=true
defaultHandler=NoSuchFileException
visitorError=simulated visitor failure
```

### 11.1. Giải thích các trường hợp

- `missing` là một file chưa từng được tạo. Visitor thứ nhất override `visitFileFailed`, nhận lỗi `NoSuchFileException` và trả `CONTINUE`, nên quá trình hoàn tất theo chính sách bỏ qua lỗi.
- `returnedStart=true` xác nhận `walkFileTree` trả lại `start` trong nhánh callback đã cho phép hoàn tất; **không** có nghĩa file missing được thăm thành công.
- Visitor thứ hai giữ default `SimpleFileVisitor`, nên lỗi missing không bị bỏ qua: `NoSuchFileException` được ném cho caller.
- Trong lượt duyệt thứ ba, callback `visitFile` tự ném `IOException("simulated visitor failure")`. Lỗi này lan ra cho caller và không biến thành một `CONTINUE` bình thường.

**Tính portable:** loại subclass cụ thể `NoSuchFileException` cho file mất là điều đã quan sát trên provider thử nghiệm và là trường hợp API thường trả; các filesystem khác có thể cung cấp lỗi I/O khác tương ứng. Hãy kiểm tra hợp đồng và không viết ứng dụng chỉ nhận một subclass nếu hệ thống phải hỗ trợ nhiều provider.

### 11.2. Không bỏ qua lỗi nếu đang làm tác vụ có hậu quả

Nếu đang copy toàn bộ cây để backup, nhưng `visitFileFailed` trả `CONTINUE`, kết quả backup có thể **thiếu file** mà chương trình vẫn kết thúc. Khi tạo backup, kiểm kê dữ liệu pháp lý hoặc kiểm tra tính toàn vẹn, nên fail-fast hoặc trả một báo cáo **partial success** rõ ràng.

## 12. Sao chép một cây nhỏ bằng visitor

`Files.walkFileTree` không tự copy: nó **phát sự kiện duyệt**, còn visitor thực hiện thao tác `Files.createDirectories` và `Files.copy`.

Mẫu ý tưởng:

- `preVisitDirectory(dir)`: tạo thư mục tương ứng ở đích.
- `visitFile(file)`: tạo đường dẫn tương đối `source.relativize(file)`, từ đó tính target và copy file.
- `postVisitDirectory(dir, exc)`: nếu cần, xử lý attrs/timestamps của thư mục sau khi descendants đã hoàn tất.
- `visitFileFailed(file, exc)`: quyết định fail-fast hay partial success.

**Nguyên tắc containment quan trọng:** target directory phải **nằm ngoài** subtree nguồn, nếu không copy có thể tự sinh nội dung mới trong khi đang duyệt hoặc lặp phức tạp. Với dữ liệu đầu vào không đáng tin, kiểm tra quyền, symlink policy, dữ liệu/đường dẫn và tình trạng đồng thời là các bài toán riêng.

## 13. Chương trình 5: copy cây mẫu do chương trình tự tạo

Lưu thành `WalkTreeCopyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public class WalkTreeCopyDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempDirectory("tree-copy-source-");
        Path dest = Files.createTempDirectory("tree-copy-dest-");
        Path sub = source.resolve("docs");
        Path text = sub.resolve("note.txt");
        Path top = source.resolve("readme.txt");
        Path targetSub = dest.resolve("docs");
        Path targetText = targetSub.resolve("note.txt");
        Path targetTop = dest.resolve("readme.txt");
        try {
            Files.createDirectory(sub);
            Files.writeString(text, "HELLO", StandardCharsets.UTF_8);
            Files.writeString(top, "TOP", StandardCharsets.UTF_8);

            List<String> copied = new ArrayList<>();
            Files.walkFileTree(source, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
                        throws IOException {
                    Path relative = source.relativize(dir);
                    Files.createDirectories(dest.resolve(relative));
                    return FileVisitResult.CONTINUE;
                }
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                        throws IOException {
                    if (attrs.isSymbolicLink()) {
                        return FileVisitResult.CONTINUE;
                    }
                    Path relative = source.relativize(file);
                    Path target = dest.resolve(relative);
                    Files.copy(file, target);
                    copied.add(relative.toString().replace('\\', '/'));
                    return FileVisitResult.CONTINUE;
                }
            });
            Collections.sort(copied);
            System.out.println("copied=" + copied);
            System.out.println("noteContent=" +
                    Files.readString(targetText, StandardCharsets.UTF_8));
            System.out.println("sourceRemains=" + Files.exists(text));
        } finally {
            Files.deleteIfExists(text);
            Files.deleteIfExists(top);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(source);
            Files.deleteIfExists(targetText);
            Files.deleteIfExists(targetTop);
            Files.deleteIfExists(targetSub);
            Files.deleteIfExists(dest);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 WalkTreeCopyDemo.java
java WalkTreeCopyDemo
```

Stdout đã kiểm chứng:

```text
copied=[docs/note.txt, readme.txt]
noteContent=HELLO
sourceRemains=true
```

### 13.1. Vì sao tạo directory trong `preVisitDirectory`?

Vì walker đi vào một directory trước descendants, callback này là thời điểm thích hợp để tạo đối ứng bên đích. `source.relativize(dir)` cho biết phần đường dẫn tương đối từ root nguồn tới directory đang xử lý. Khi `dir == source`, kết quả là empty relative path, nên `dest.resolve(relative)` vẫn là vị trí `dest`.

Sau đó, `visitFile` copy từng file sang `dest.resolve(source.relativize(file))`, bảo toàn tên và cấu trúc phân cấp.

### 13.2. Vì sao không có `REPLACE_EXISTING`?

Ví dụ đơn giản thiết kế cho target chưa chứa các file đích. `Files.copy(file, target)` sẽ không âm thầm ghi đè tên đã tồn tại theo cách chúng ta kỳ vọng. Nếu viết code backup/sync thật, cần chính sách rõ cho overwrite, version, checksum, file đang được dùng, quyền và các lỗi trung gian.

### 13.3. Vì sao bỏ qua symbolic link?

Theo mặc định, `walkFileTree` không đi theo symlink; trong `visitFile`, symlink có thể xuất hiện như một entry có `attrs.isSymbolicLink()==true`. Đoạn demo cố ý **bỏ qua** link, thay vì copy target của link hay tạo lại link không kiểm soát. Nếu sản phẩm muốn sao chép symlink, cần policy riêng, kiểm tra target và copy options thích hợp.

**Không gọi ví dụ này là “secure backup” cho cây dữ liệu do attacker có thể sửa.** Có thể có race giữa lúc walker đọc attributes và lúc `Files.copy` mở file; quyền/links có thể đổi. Nội dung có thể bị sửa trong quá trình copy, và `walkFileTree` không tạo snapshot nhất quán toàn cây. Mục tiêu ví dụ là học cấu trúc visitor.

### 13.4. Cleanup trong demo

`finally` xóa **chỉ** các tệp/thư mục tạm được tạo ở các biến cụ thể. Nó **không** đi qua một đường dẫn bất kỳ do user nhập rồi xóa đệ quy. Nếu chương trình thất bại giữa lúc copy một file ở ngoài danh sách tạo sẵn, cleanup thực tế cần chiến lược riêng; không nên áp dụng snippet này trực tiếp cho dữ liệu production.

## 14. Symbolic links: mặc định không theo, `FOLLOW_LINKS` là lựa chọn có rủi ro

`Files.walkFileTree(start, visitor)` **mặc định không tự động đi theo symbolic links**. Thay vào đó, symlink có thể được chuyển tới `visitFile` với attributes có `isSymbolicLink()==true`.

Muốn theo links, overload bốn tham số cho phép:

```java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor
);
```

Đây là snippet. Khi bật `FOLLOW_LINKS`:

- Traversal có thể đi tới thư mục **nằm ngoài root lexical** nếu một symlink trong cây trỏ ra ngoài.
- Một symlink trỏ về tổ tiên có thể tạo **vòng lặp**, và Java phát hiện bằng cơ chế loop detection.
- Khi phát hiện vòng lặp, `visitFileFailed` có thể nhận `FileSystemLoopException`.
- Nếu không đọc được target của link, API có quy tắc thử attributes của chính link và có thể chuyển link tới `visitFile` theo hợp đồng.
- Quyền, file-system provider và tình trạng symlink đồng thời vẫn phải được xem xét; một lượt quét không phải transaction.

**Không bật `FOLLOW_LINKS` chỉ để “quét kỹ hơn”** nếu không có chính sách và yêu cầu rõ. Với công cụ xóa tệp, bỏ qua/không theo symlink thường là quyết định quan trọng để tránh thao tác vượt cây dự kiến.

## 15. Chương trình 6: kiểm thử symlink khi hệ điều hành hỗ trợ

Lưu thành `WalkTreeLinksDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public class WalkTreeLinksDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-links-");
        Path sub = root.resolve("sub");
        Path link = sub.resolve("back");
        try {
            Files.createDirectory(sub);
            try {
                Files.createSymbolicLink(link, root);
            } catch (IOException | UnsupportedOperationException | SecurityException unavailable) {
                System.out.println("symlink=SKIPPED");
                return;
            }

            int[] linksSeen = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (attrs.isSymbolicLink()) linksSeen[0]++;
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("noFollowLinks=" + linksSeen[0]);

            int[] loops = {0};
            Files.walkFileTree(root, EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    Integer.MAX_VALUE, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(Path file, IOException error)
                        throws IOException {
                    if (error instanceof FileSystemLoopException) {
                        loops[0]++;
                        return FileVisitResult.CONTINUE;
                    }
                    throw error;
                }
            });
            System.out.println("loopFound=" + (loops[0] > 0));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 WalkTreeLinksDemo.java
java WalkTreeLinksDemo
```

**Nhánh kỳ vọng nếu provider cho phép tạo symbolic link:**

```text
noFollowLinks=1
loopFound=true
```

**Nhánh thực sự quan sát trên máy kiểm thử không có quyền tạo link:**

```text
symlink=SKIPPED
```

Vì lý do quyền/capability của môi trường, **không tuyên bố nhánh symlink đã PASS**. Chương trình có thể chạy hợp lệ theo nhánh SKIPPED; muốn kiểm chứng vòng lặp link thật, cần chạy ở môi trường hỗ trợ và có quyền cần thiết.

### 15.1. Vì sao ví dụ cố ý tạo một vòng lặp?

`link` trỏ từ `root/sub/back` ngược tới `root`, là một ancestor đang nằm trên đường traversal. Khi không follow link, walker chỉ thấy link như entry. Khi bật `FOLLOW_LINKS`, ý định mở link dẫn về ancestor, tạo tình huống loop. `FileSystemLoopException` được báo tới `visitFileFailed`, để visitor quyết định tiếp tục/báo lỗi.

Đây là **test lỗi trên cây tạm do chương trình sở hữu**. Đừng tự tạo vòng symlink trong cây công việc thật của người dùng để thử nghiệm.

### 15.2. Vì sao phải xử lý cả lỗi khác?

`visitFileFailed` trong ví dụ chỉ bỏ qua `FileSystemLoopException`, còn các `IOException` khác được **ném lại**. Nếu ứng dụng bắt mọi IOException rồi CONTINUE, nó có thể bỏ qua mất quyền đọc hoặc hỏng filesystem mà vẫn báo quét thành công. Cần nêu rõ khi nào một lỗi là chấp nhận được.

## 16. Cẩn trọng với thư mục và dữ liệu đang thay đổi đồng thời

`walkFileTree` không tạo **snapshot filesystem nhất quán**. Trong thời gian đi qua cây:

- Một file có thể được tạo mới sau khi thư mục đã được liệt kê.
- Một file có thể bị xóa hoặc đổi tên trước khi callback xử lý.
- Kích thước hoặc metadata có thể thay đổi giữa lúc đọc attributes và lúc mở file.
- Một symbolic link có thể bị sửa hoặc đích của nó có thể biến mất.
- Đường dẫn có thể trỏ đến entry khác sau kiểm tra, nếu tác nhân khác có quyền thay đổi directory entries.

Do đó, `walkFileTree` phù hợp để **tổ chức traversal**, không tự làm một backup nhất quán, bộ quét an ninh hoàn chỉnh hay một thao tác chuyển cây nguyên tử.

Nếu cần snapshot/consistent backup, phải có cơ chế filesystem snapshot, khóa, versioning hoặc phương án kiểm tra/xác minh phù hợp với hệ thống triển khai. Chỉ đếm file trong visitor rồi tin rằng toàn cây “bất biến từ đầu đến cuối” là một giả định sai.

### 16.1. Path traversal và nguồn không tin cậy

Nếu root do người dùng nhập, hãy xác nhận root thuộc vùng được phép trước khi duyệt. Nếu bật `FOLLOW_LINKS`, sự hiện diện của link có thể khiến traversal đi khỏi vị trí lexical ban đầu. Không coi `Path.normalize()` là đủ để kiểm soát symlinks.

Đặc biệt, **đừng kết hợp `walkFileTree` + `Files.delete` trên một input chưa tin cậy** nếu chưa có chính sách quyền/symlink/containment rõ ràng. Các vấn đề TOCTOU và quyền truy cập không biến mất nhờ trả `CONTINUE`.

### 16.2. Directory lớn và giới hạn tài nguyên

Với cây rất lớn, một lượt duyệt có thể tốn thời gian và I/O đáng kể. Duyệt theo visitor cho phép bạn xử lý từng entry và không bắt buộc nạp toàn bộ danh sách đường dẫn vào bộ nhớ. Tuy nhiên chính **code callback** có thể tích lũy dữ liệu, như các `List<String>` trong ví dụ; nếu thu thập hàng triệu entries rồi sort, bộ nhớ vẫn có thể rất lớn.

Các biện pháp khi cần:
- Dùng `maxDepth` để giới hạn chiều sâu.
- Dùng `SKIP_SUBTREE` cho nhánh không cần.
- Đếm số mục đã xử lý và trả `TERMINATE` khi đạt giới hạn nghiệp vụ.
- Đưa output ra một consumer/stream/lưu trữ có cơ chế giới hạn thích hợp thay vì giữ tất cả trong RAM.
- Xử lý `IOException` theo policy; bảo đảm hệ thống có quyền đọc cần thiết.
- Đo hiệu năng trên filesystem mục tiêu, nhất là ổ mạng.

**`maxDepth` giới hạn độ sâu, không giới hạn số entries ở cùng một cấp.** Một thư mục với rất nhiều mục trực tiếp vẫn có thể tốn tài nguyên dù maxDepth bằng 1.

## 17. So sánh `Files.walkFileTree`, `Files.walk` và `Files.list`

Java hiện đại có nhiều lựa chọn:

| API | Duyệt | Đối tượng kết quả | Khi thường phù hợp |
| --- | --- | --- | --- |
| `Files.list(dir)` | **Một cấp**, entries trực tiếp | `Stream<Path>` | Liệt kê nhanh nội dung thư mục |
| `Files.walk(start, depth)` | Đệ quy, biểu diễn theo stream | `Stream<Path>` | Filter/map/collect kiểu pipeline |
| `Files.find(start, depth, matcher)` | Đệ quy và predicate có attributes | `Stream<Path>` | Tìm file với thuộc tính và điều kiện |
| `Files.walkFileTree(start, visitor)` | Đệ quy theo callback | `Path start`, kết quả phụ thuộc visitor | Copy tree, skip subtree, pre/post directory, kiểm soát failure |

`Files.walk`/`Files.find` có từ **Java 8**, `Files.list` có từ Java 8, vẫn phù hợp hiện nay. Khi dùng stream từ `Files.walk` hoặc `Files.list`, cần **đóng stream** vì nó giữ tài nguyên hệ thống:

```java
try (java.util.stream.Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile).forEach(System.out::println);
}
```

Đây là snippet Java 8+ với `Path root` và import `Files`, **không phải chương trình đầy đủ**. Method reference `Files::isRegularFile` tương thích do varargs options, nhưng predicate đọc trạng thái filesystem tại thời điểm dùng; có thể gặp race.

Với `walkFileTree`, walker quản lý tài nguyên directory traversal trong lời gọi; caller không nhận một stream cần tự đóng. Bù lại, bạn viết visitor và quy tắc điều khiển callback thay vì thuần pipeline.

### 17.1. Chọn API nào để bỏ qua cả một subtree?

Dùng `walkFileTree` thường biểu đạt rõ nhất:

```java
@Override
public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
    if (shouldSkip(dir)) return FileVisitResult.SKIP_SUBTREE;
    return FileVisitResult.CONTINUE;
}
```

Đây là snippet có method `shouldSkip(Path)` giả định thuộc code ứng dụng. Với stream `Files.walk`, filter sau khi path đã được stream đưa ra không phải cùng điều kiện kiểm soát trước khi mở/duyệt cả một subtree. Nếu bài toán đòi thực sự **không đi vào** một nhánh, visitor là lựa chọn dễ kiểm soát hơn.

### 17.2. Chọn API nào để tính tổng kích thước?

Nếu chỉ có một thư mục hoặc file tree nhỏ, `Files.walk` cùng filter/mapToLong/sum có thể ngắn. Tuy nhiên `walkFileTree` cho phép xử lý lỗi và skip subtree chi tiết hơn. Không có API nào tự bảo đảm việc đo kích thước nhất quán khi file thay đổi đồng thời.

## 18. Một số sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách dùng đúng |
| --- | --- | --- |
| Dùng `Files.list` rồi nghĩ đã duyệt mọi subdirectory | `list` chỉ liệt kê trực tiếp | `walkFileTree` hoặc `walk` khi cần đệ quy |
| Nghĩ `FileVisitor` chỉ có `visitFile` | Có 4 callback | Hiểu pre/post directory và lỗi |
| Nghĩ `visitFile` luôn nhận regular file | Có symbolic link, entry khác và directory khi maxDepth chạm giới hạn | Kiểm tra `attrs.isRegularFile`/`isDirectory` |
| Dùng `getFileName` làm nguồn duy nhất cho relative path | Nhiều nơi có tên file trùng nhau | `root.relativize(file)` |
| Tin thứ tự sibling của filesystem | Không có guarantee | Sort output hoặc thiết kế không lệ thuộc thứ tự |
| Trả `SKIP_SUBTREE` từ `visitFile` để skip phần bên dưới | Chỉ có ý nghĩa từ `preVisitDirectory` | Trả đúng callback |
| Nhầm `SKIP_SIBLINGS` với dừng cả quá trình | Nó bỏ qua sibling theo ngữ cảnh | `TERMINATE` để dừng traversal |
| Nghĩ `maxDepth=1` có thể đi hết mọi nhánh cấp sâu | Chỉ root và entries cấp 1 | Tăng depth theo nhu cầu |
| Nghĩ maxDepth làm directory không xuất hiện trong `visitFile` | Directory tại giới hạn có thể được gọi `visitFile` | Xem attrs |
| Dùng default `SimpleFileVisitor` rồi nghĩ tất cả lỗi bị bỏ qua | Default rethrow lỗi I/O | Bắt/override khi muốn best-effort |
| Override `visitFileFailed` luôn CONTINUE rồi báo kết quả đầy đủ | Những entry lỗi đã bị bỏ qua | Ghi partial result/failure count |
| Bỏ qua `exc` của `postVisitDirectory` | Có thể mất lỗi iteration | Kiểm tra và throw/report |
| Bật `FOLLOW_LINKS` mà không xét vòng lặp | Có thể có `FileSystemLoopException` | Policy symlink và handle lỗi rõ |
| Cho rằng không follow symlink là toàn bộ sandbox | Directory entries vẫn có thể thay đổi đồng thời | Permissions và mô hình quyền thực tế |
| Dùng `walkFileTree` để tự động copy/delete | Walker chỉ gọi callback | Tự triển khai thao tác rõ |
| Đặt target copy trong source tree | Có thể tạo nội dung trong lúc duyệt | Đặt target ngoài nguồn |
| Coi callback attributes là snapshot toàn hệ thống | Metadata có thể đổi ngay sau đó | Kiểm chứng theo nhu cầu |
| Dùng `Path.of` với target Java 7 | `Path.of` từ Java 11 | `Paths.get` nếu phải dùng Java 7 |
| Dùng `Files.writeString` với target Java 7 | Method từ Java 11 | `Files.write` hoặc stream trên Java 7 |
| Dùng output path tuyệt đối làm expected stdout portable | Thư mục tạm và separator khác nhau | Dùng relative names và sort |
| Không có giới hạn cho cây untrusted rất lớn | Có thể tốn I/O/bộ nhớ | Depth/entry limits, timeout/policy |
| Dùng `Files.delete` đệ quy trên input user chưa validate | Có nguy cơ xóa sai dữ liệu | Chỉ xóa tài nguyên đã được kiểm soát |

## 19. Các lưu ý về hiệu năng và xử lý sai sót

### 19.1. Không nên gọi `Files.readAllBytes` trên mọi file chỉ để lấy kích thước

Nếu chỉ cần kích thước metadata, dùng `attrs.size()` trong `visitFile`. Đọc nội dung mọi file gây I/O lớn, chiếm RAM và có thể làm chậm đáng kể. Nếu cần hash, nội dung hay parser, hãy dùng streaming API, giới hạn kích thước và xử lý lỗi/đầu vào độc hại.

### 19.2. Không mặc định tổng kích thước directory bằng tổng nội dung thực trên ổ

`BasicFileAttributes.size()` cho biết một kích thước theo provider. Với sparse files, compressed files, hard links, symbolic links hoặc network filesystem, phép cộng `attrs.size()` không nhất thiết bằng **số block vật lý đã chiếm trên thiết bị**. Nếu mục tiêu là quota/billing, cần quy định mô hình đo rõ ràng.

### 19.3. Không giữ Path đến file rồi tin nó vẫn tồn tại

Một `Path` được visitor truyền vào chỉ là reference đến vị trí trong filesystem tại thời điểm đó. Nếu một process khác xóa hoặc đổi tên file sau callback, thao tác tiếp theo có thể thất bại. Luôn xử lý các `IOException` khi thật sự mở/đọc/copy và đừng chuyển lỗi thành kết quả thành công giả.

### 19.4. Không nuốt lỗi với `TERMINATE`

`TERMINATE` nói rằng visitor muốn **kết thúc traversal**, không nói caller vì sao. Nếu chỉ muốn dừng sau khi tìm thấy một kết quả thì phù hợp. Nếu cần thông báo “quét thất bại vì thiếu quyền”, có thể ném `IOException` cụ thể hoặc trả một outcome có lý do lỗi, thay vì chỉ `TERMINATE` rồi báo quét xong.

### 19.5. Hạn chế mức độ song song ngầm

Một lần `walkFileTree` là lượt duyệt thực hiện qua callback. Nó không tự biến việc xử lý từng file thành công việc song song. Nếu callback gửi task vào executor, phải quản lý vòng đời, thứ tự, thread safety và tải I/O. Đặc biệt, code kiểu `Files.walkFileTree(...)` trả về không có nghĩa các async tasks bạn tự spawn cũng hoàn thành.

## 20. Checklist để review một visitor

1. Mục tiêu là liệt kê **một cấp** hay **cả cây**?
2. Root có tồn tại và caller có quyền thăm nó không?
3. Có cần dùng `FOLLOW_LINKS`? Nếu có, đã nghĩ đến vòng lặp và phạm vi ngoài root chưa?
4. Có cần giới hạn `maxDepth` hoặc số lượng entries không?
5. `preVisitDirectory` xử lý bỏ qua nhánh đúng nơi chưa?
6. `visitFile` có kiểm tra `attrs.isRegularFile` trước khi thống kê/copy không?
7. `postVisitDirectory` có kiểm tra `exc` nếu đã override không?
8. `visitFileFailed` đang throw hay CONTINUE? Kết quả có phân biệt **partial success** không?
9. Có hiểu `SKIP_SIBLINGS` khác `TERMINATE` không?
10. Logic có phụ thuộc thứ tự sibling chưa được bảo đảm không?
11. Nếu copy, target có nằm **ngoài** cây nguồn không?
12. Nếu delete, dữ liệu có thực sự được phép xóa và scope có được kiểm soát không?
13. Đã xử lý lỗi I/O hoặc race khi file bị đổi sau lúc visitor nhận Path chưa?
14. Có dùng `root.relativize(file)` khi muốn giữ cấu trúc tên ở đích không?
15. Có giữ tất cả file paths trong RAM không? Nếu quá lớn, cần cơ chế stream/batching?
16. Có unit test cho skip, terminate, depth và lỗi visitor chưa?
17. Có integration test trên OS/provider và quyền thực tế khi symlink là yêu cầu quan trọng không?
18. Có ghi rõ các API phụ trợ Java 11 trong ví dụ JDK 17 và không coi chúng là API Java 7 không?

## 21. Câu hỏi tự kiểm tra và lời giải

**Câu 1.** `walkFileTree` duyệt cây theo kiểu nào?  
**Đáp án:** Theo chiều sâu (*depth-first*), với callback vào thư mục, file và hoàn tất thư mục theo quy tắc traversal.

**Câu 2.** Khi nào `preVisitDirectory` được gọi?  
**Đáp án:** Trước khi thăm entries bên trong một directory được mở cho traversal, nếu nó không bị giới hạn maxDepth ở cách khiến được chuyển tới `visitFile`.

**Câu 3.** Vì sao cần `postVisitDirectory`?  
**Đáp án:** Để xử lý hậu kỳ sau khi descendants đã được thăm, ví dụ hoàn tất thư mục hoặc kiểm tra lỗi iteration.

**Câu 4.** Có cần implement cả bốn callback khi dùng `SimpleFileVisitor` không?  
**Đáp án:** Không. Override những method cần; các callback còn lại có default behavior.

**Câu 5.** `SimpleFileVisitor.visitFileFailed` mặc định làm gì?  
**Đáp án:** Ném lại `IOException` đã khiến entry không được thăm, không tự bỏ qua.

**Câu 6.** `SKIP_SUBTREE` trả từ callback nào thực sự có tác dụng skip descendants?  
**Đáp án:** `preVisitDirectory`. Nếu trả từ callback khác, API xử lý như `CONTINUE`.

**Câu 7.** `SKIP_SIBLINGS` có dừng toàn bộ walk không?  
**Đáp án:** Không. Nó skip các sibling còn lại theo ngữ cảnh; `TERMINATE` mới dừng toàn bộ.

**Câu 8.** Vì sao `maxDepth=1` có thể khiến `visitFile` nhận directory?  
**Đáp án:** Vì directory ở giới hạn không được đi sâu hơn và được gọi `visitFile` với attributes của directory.

**Câu 9.** `maxDepth=0` có nghĩa không thăm cả root không?  
**Đáp án:** Không. Root ở depth 0, có thể được xử lý như entry tại mức giới hạn.

**Câu 10.** `walkFileTree` có tự đi theo symbolic links không?  
**Đáp án:** Mặc định không. Chỉ theo nếu chọn `FileVisitOption.FOLLOW_LINKS` trong overload có options.

**Câu 11.** Nếu FOLLOW_LINKS gặp symlink trỏ về ancestor, có thể xảy ra điều gì?  
**Đáp án:** `visitFileFailed` có thể nhận `FileSystemLoopException` để visitor quyết định dừng/tiếp tục.

**Câu 12.** Một callback `visitFile` tự throw IOException có được `walkFileTree` nuốt bỏ để đi tiếp không?  
**Đáp án:** Không mặc nhiên. Exception có thể lan ra caller và làm dừng lượt duyệt, như demo đã kiểm thử.

**Câu 13.** Thứ tự các file trong cùng thư mục có được bảo đảm theo tên không?  
**Đáp án:** Không. Nếu cần thứ tự tên cho báo cáo/test, thu thập và sort.

**Câu 14.** Khi walker trả `Path start`, có phải đã thăm đủ mọi file?  
**Đáp án:** Không. Visitor có thể skip nhánh, kết thúc sớm hoặc bỏ qua lỗi theo chính sách. Cần một outcome/stats riêng.

**Câu 15.** Muốn copy tree giữ cấu trúc, method nào cho ra đường dẫn tương đối đến một entry?  
**Đáp án:** `source.relativize(file)`, rồi `dest.resolve(relative)` để đặt entry vào đích tương ứng.

**Câu 16.** Duyệt và copy trong khi người khác sửa source có tạo backup nhất quán không?  
**Đáp án:** Không tự động. Cần snapshot/locking/version verification nếu tính nhất quán là yêu cầu.

**Câu 17.** `Files.walk` khác `Files.walkFileTree` về tài nguyên và giao diện thế nào?  
**Đáp án:** `Files.walk` trả Stream cần đóng; `walkFileTree` nhận visitor và xử lý traversal trong một lời gọi, cho kiểm soát pre/post directory và skip chi tiết.

**Câu 18.** `Path.of` và `Files.writeString` có từ Java 7 không?  
**Đáp án:** Không. Chúng có từ Java 11, còn `Files.walkFileTree` có từ Java 7. Các chương trình bài này target JDK 17.

### Thực hành A — Tìm tệp `.java`

Sửa `WalkTreeSummaryDemo` để chỉ thống kê `attrs.isRegularFile()` và tên kết thúc `.java`. Tạo một file `Test.java` trong cây tạm và dự đoán count trước khi chạy.

### Thực hành B — Bỏ qua thư mục cache

Trong `WalkTreeControlDemo`, thay tên `ignored` bằng `cache`, ghi lại danh sách file từ nhánh còn lại. Xác nhận `SKIP_SUBTREE` không cản việc duyệt các sibling thư mục khác.

### Thực hành C — Độ sâu 0, 1, 2

Sử dụng cùng fixture rồi thử `maxDepth=0`, `1`, `2`. Đếm xem những directory nào được gọi qua `preVisitDirectory`, những directory nào đi qua `visitFile` ở maxDepth.

### Thực hành D — Best-effort và strict

Trong `WalkTreeFailureDemo`, thay `visitFileFailed` từ `CONTINUE` thành `throw error`. So sánh cách caller nhận ngoại lệ và trạng thái “quét hoàn tất”.

### Thực hành E — Tìm một tệp rồi dừng

Tạo một cây nhỏ có một file tên `wanted.txt`; dùng `visitFile` trả `TERMINATE` ngay khi gặp nó. Không đưa ra giả định về thứ tự các file cùng cấp. Trả rõ trạng thái `found` cho caller.

### Thực hành F — Sao chép không ghi đè

Chạy `WalkTreeCopyDemo`, sau đó tạo sẵn file đích cùng tên để quan sát lỗi khi `Files.copy` không có `REPLACE_EXISTING`. Thiết kế thông báo partial copy/recovery thay vì xóa source hoặc ghi đè ngầm.

### Thực hành G — Symlink capability

Chạy `WalkTreeLinksDemo` trên môi trường có quyền tạo symlink. Nếu kết quả `SKIPPED`, ghi rõ do capability không có và dùng CI/provider có hỗ trợ để kiểm thử nhánh loop thật.

### Thực hành H — Báo cáo có lỗi

Xây dựng class `ScanReport` có `filesVisited`, `directoriesVisited`, `failedEntries`, `terminatedEarly`. Không trả “thành công đầy đủ” khi có lỗi đã bỏ qua hoặc đã trả `TERMINATE` trước khi hết cây.

## 22. Tài liệu chính thức để đối chiếu

- [Java SE 17 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)): hai overload, depth, symlink, lỗi và quy tắc traversal.
- [Java SE 17 — FileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html): bốn callback và hợp đồng từng callback.
- [Java SE 17 — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): default methods và cách override để thay policy.
- [Java SE 17 — FileVisitResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Java SE 17 — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS`.
- [Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `isRegularFile`, `isDirectory`, `isSymbolicLink`, `size`.
- [Java SE 17 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemLoopException.html): lỗi phát hiện vòng link.
- [Dev.java — Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/): hướng dẫn có ví dụ của cộng đồng Java chính thức.

**Kết luận:** `Files.walkFileTree` là API Java 7 vẫn phù hợp để duyệt cây tệp có kiểm soát trong Java hiện đại. Hãy chọn callback theo đúng vòng đời directory/file, dùng `FileVisitResult` để skip/dừng có chủ đích, `maxDepth` để giới hạn mức đi sâu, chỉ bật `FOLLOW_LINKS` khi đã xét vòng lặp và bảo mật, và xử lý lỗi traversal thay vì giả định mọi file đều được thăm thành công. Các ví dụ dùng thư mục tạm, chương trình Java 17 biên dịch được và kết quả kiểm chứng rõ ràng.
