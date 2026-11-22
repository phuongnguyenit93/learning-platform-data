# Đường dẫn tương đối được lưu trong liên kết (symbolic link) của Java

**Chủ đề:** Java 7 — Liên kết tệp  
**Bài học:** Đường dẫn tương đối được lưu trong liên kết  
**Thực hành:** Java 17+ với NIO.2, đặc biệt `Files.createSymbolicLink`, `Files.readSymbolicLink`, `Files.isSymbolicLink`, `LinkOption.NOFOLLOW_LINKS`, `Path.resolve`, `Path.relativize` và `Path.toRealPath`. Đây đều là các API hiện hành; bài không dựa vào kỹ thuật Java đã lỗi thời.

## 1. Vấn đề cốt lõi: một symbolic link lưu gì?

**Symbolic link** (liên kết tượng trưng, thường gọi là *symlink*) là một entry trong filesystem mang thông tin chỉ đến một đường dẫn khác. Với NIO.2, bạn có thể tạo liên kết, đọc lại đường dẫn đích được lưu và yêu cầu filesystem truy cập qua liên kết.

Có hai loại đích:

- **Đích tuyệt đối:** một đường dẫn có root, ví dụ trên Unix là `/srv/app/data/report.txt`. Đường dẫn này gắn với vị trí tuyệt đối của filesystem có ý nghĩa tại thời điểm sử dụng.
- **Đích tương đối:** một đường dẫn không có root, ví dụ `../data/report.txt`. **Điểm gốc để diễn giải đường dẫn này là thư mục chứa symbolic link**, không phải working directory của JVM, không phải thư mục project, không phải vị trí source `.java` và không nhất thiết là thư mục nơi bạn đang chạy lệnh terminal.

Hãy tưởng tượng cấu trúc:

```text
workspace/
├── data/
│   └── report.txt          (file thật)
└── links/
    └── latest.txt          (symbolic link)
        ↳ ../data/report.txt
```

`latest.txt` lưu đường dẫn tương đối `../data/report.txt`. Khi chương trình mở `workspace/links/latest.txt`, filesystem bắt đầu từ **`workspace/links/`** rồi diễn giải `..` sang `workspace/` và tiếp đến `data/report.txt`.

Sơ đồ:

```text
Link path:     workspace/links/latest.txt
Link parent:   workspace/links/
Stored target: ../data/report.txt
Interpret:     workspace/links/ + ../data/report.txt
Lexical result: workspace/data/report.txt
```

**Đó là ngữ nghĩa của đích tương đối trong symlink.** Không tự đem `../data/report.txt` đi resolve từ `System.getProperty("user.dir")` rồi kết luận về nơi symlink trỏ tới.

> Ghi nhớ: `Files.readSymbolicLink(link)` trả về **đường dẫn đích được lưu**; còn để hiểu ý nghĩa một đích tương đối, cần biết **vị trí của chính liên kết**.

## 2. Hai Path khác nhau: đường dẫn của link và đường dẫn được lưu

Chữ ký API chính:

```java
Path Files.createSymbolicLink(
        Path link,
        Path target,
        FileAttribute<?>... attrs) throws IOException;

Path Files.readSymbolicLink(Path link)
        throws IOException;
```

Đây là chữ ký rút gọn cho việc học; chữ ký thực sự là static methods của `java.nio.file.Files`.

- `link` xác định **nơi tạo entry symbolic link** trong filesystem.
- `target` là đường dẫn đích **được lưu trong entry**. Có thể tuyệt đối hoặc tương đối; về nguyên tắc có thể chưa tồn tại khi tạo.
- `attrs` là các attributes tùy chọn mà provider hỗ trợ đặt lúc tạo symlink.
- `readSymbolicLink(link)` trả lại một `Path` mang đích mà link lưu, thuộc cùng filesystem với `link`. Method không tự bảo đảm đích tồn tại.
- Tạo symlink là **optional operation**: provider, filesystem hoặc quyền OS có thể không cho phép. Nó có thể ném `UnsupportedOperationException` hoặc `IOException`.

Ví dụ tạo:

```java
Path link = Path.of("workspace", "links", "latest.txt");
Path storedTarget = Path.of("..", "data", "report.txt");

Files.createSymbolicLink(link, storedTarget);
```

Đây chỉ là snippet trong một method xử lý `IOException`. Thư mục cha của `link` phải tồn tại; ví dụ không tự tạo tree hay tệp đích. Việc `storedTarget` là relative không khiến JVM ghi nó dưới dạng một absolute path.

**Quan trọng:** một liên kết tương đối có thể dùng để làm layout dự án *di chuyển cùng nhau* thuận tiện hơn. Nếu cả thư mục `workspace` được chuyển mà cấu trúc `links/` và `data/` bên trong vẫn giữ nguyên, quan hệ `../data/report.txt` có thể vẫn đúng. Nếu chỉ chuyển **mỗi entry symlink** sang thư mục khác, cách diễn giải có thể đổi hoàn toàn.

### 2.1. Symlink không phải một alias Java object

`Path` chỉ mô hình hóa pathname. Một symlink là **entry thực trong filesystem**; nó có thể tồn tại ngay cả khi chưa có target. Gọi:

```java
Path a = Path.of("links", "latest.txt");
Path b = Path.of("data", "report.txt");
```

chỉ tạo hai object `Path`, **không tạo symbolic link**. `Files.createSymbolicLink(a,b)` mới là thao tác yêu cầu filesystem tạo liên kết với đích `b`. Và vì `b` tương đối, nó được diễn giải từ **thư mục của `a`**, không từ vị trí làm việc khi bạn gọi `Path.of`.

Đừng đồng nhất:

- **Giá trị `Path`:** biểu diễn tên đường dẫn.
- **Entry symbolic link:** một filesystem object mang đích được lưu.
- **File thật được link trỏ đến:** có thể tồn tại, biến mất, thay thế hoặc nằm ngoài phạm vi ứng dụng.
- **Hard link:** thêm một directory entry đến cùng đối tượng file, **không lưu chuỗi đường dẫn đích tương đối** theo kiểu symbolic link.

## 3. Tính trước đích tương đối bằng Path.relativize

Nếu bạn có một `Path link` và một `Path target` đã biết, cách thông dụng để tìm đường dẫn tương đối **từ thư mục của link đến target** là:

```java
Path link = root.resolve("links").resolve("latest.txt");
Path target = root.resolve("data").resolve("report.txt");

Path storedTarget =
        link.getParent().relativize(target);
```

Đây là snippet; `root` là một `Path` absolute/normalized thích hợp, và các đường dẫn phải cùng filesystem/provider tương thích. Kết quả trong sơ đồ sẽ là `../data/report.txt`.

**Vì sao `link.getParent()`, không phải `link.relativize(target)`?** Vì target relative được diễn giải bắt đầu từ **directory chứa link**. Nếu lấy đường dẫn tương đối từ chính pathname `latest.txt` (một entry file), bạn đã chọn sai điểm gốc về mặt khái niệm.

**Vì sao cần sự tương thích?** `relativize` chỉ xác định quan hệ trên các `Path` tương thích. Đường dẫn absolute và relative, hoặc hai file systems khác nhau, không thể tùy tiện được relativize. Với các layout phức tạp có symlink trong đường dẫn cha, phép tính là **lexical**, không nhất thiết giữ nguyên đối tượng filesystem vật lý sau khi resolve.

### 3.1. Ví dụ runnable hoàn toàn đa nền tảng: chỉ tính Path

Tạo file `RelativeTargetPlanningDemo.java`:

```java
import java.nio.file.Path;

public class RelativeTargetPlanningDemo {
    static String portable(Path p) {
        return p.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path root = Path.of("workspace")
                .toAbsolutePath().normalize();

        Path link = root.resolve("links")
                .resolve("latest.txt");
        Path target = root.resolve("data")
                .resolve("report.txt");

        Path stored = link.getParent().relativize(target);
        Path interpreted = link.getParent()
                .resolve(stored).normalize();

        Path wrongFromWorkspace =
                root.resolve(stored).normalize();

        System.out.println("stored=" + portable(stored));
        System.out.println(
                "stored-relative=" + !stored.isAbsolute());
        System.out.println(
                "interpreted-right="
                + interpreted.equals(target));
        System.out.println(
                "wrong-from-root="
                + wrongFromWorkspace.equals(target));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all RelativeTargetPlanningDemo.java
java RelativeTargetPlanningDemo
```

**stdout chính xác trên Windows/Linux/macOS:**

```text
stored=../data/report.txt
stored-relative=true
interpreted-right=true
wrong-from-root=false
```

Bài kiểm tra chỉ làm việc với `Path` trong bộ nhớ, **không tạo symlink** và **không cần file thật tồn tại**. `portable` chỉ chuẩn hóa dấu phân tách khi in stdout để kết quả dễ kiểm tra trên nhiều OS; không thay đổi path dùng cho I/O.

Phân tích: nếu mistakenly resolve `stored` từ `root` thay vì `link.getParent()`, kết quả khác. Đây là nguồn gốc của nhiều bug khi người lập trình gọi `Files.readSymbolicLink` nhưng sau đó tự resolve từ `user.dir`.

### 3.2. Không cần tạo rel path bằng ghép String

Tránh:

```java
String stored = "../../" + name;
```

trong trường hợp chương trình đã có hai `Path` tương thích. Việc ghép String với dấu phân tách có thể giả định sai nền tảng và dễ tính sai số tầng `..`. Thay vào đó, cân nhắc `link.getParent().relativize(target)` trên các path được chuẩn hóa và có cùng semantics.

Tuy vậy, **không tự động normalize đường dẫn đích được lấy từ nguồn không tin cậy rồi cho rằng đã an toàn**. Việc tính đúng đường dẫn và việc cho phép truy cập là hai vấn đề khác nhau. Phần 13 giải thích điều đó.

## 4. Đọc đích đã lưu bằng Files.readSymbolicLink

Sau khi symlink tồn tại:

```java
Path stored = Files.readSymbolicLink(link);
```

`stored` là **đường dẫn đích của link**. Method không tự mở file cuối để đọc nội dung, không tự convert thành absolute và không kiểm tra tính hợp lệ về mặt nghiệp vụ của vị trí đích.

Nếu `stored.isAbsolute() == false`, một cách diễn giải **theo cú pháp** để hiển thị hoặc kiểm tra layout là:

```java
Path parent = link.toAbsolutePath().getParent();

Path candidate = stored.isAbsolute()
        ? stored
        : parent.resolve(stored);

Path lexicalLocation = candidate.normalize();
```

Đây là snippet. Khi `link` đã là absolute, có thể dùng trực tiếp `link.getParent()`. Nếu `link` là relative, việc dùng `toAbsolutePath()` ở đây chỉ giúp xác định vị trí directory của symlink dưới working directory; **nó không tự kiểm tra link tồn tại**.

**Điều quan trọng hơn:** `lexicalLocation` là kết quả phép tính pathname. Khi filesystem chứa symlink ở các thành phần khác, phép `normalize()` có thể thay đổi ý nghĩa của một path có `..`. Để xác định đối tượng **thực đang tồn tại**, dùng `toRealPath()` hoặc thao tác I/O tương ứng theo contract và xử lý `IOException` — nhưng một lần check cũng không loại bỏ TOCTOU.

### 4.1. Chương trình runnable: tạo và đọc một liên kết tương đối

Tạo `RelativeSymlinkDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RelativeSymlinkDemo {
    static String portable(Path p) {
        return p.toString().replace('\\', '/');
    }

    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("rel-symlink-");
        Path data = root.resolve("data");
        Path links = root.resolve("links");
        Path file = data.resolve("report.txt");
        Path link = links.resolve("latest.txt");
        Path storedTarget =
                Path.of("..", "data", "report.txt");

        try {
            Files.createDirectories(data);
            Files.createDirectories(links);
            Files.writeString(
                    file, "HELLO", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(link, storedTarget);
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            Path stored = Files.readSymbolicLink(link);

            System.out.println("symlink=created");
            System.out.println(
                    "stored=" + portable(stored));
            System.out.println(
                    "stored-relative=" + !stored.isAbsolute());
            System.out.println(
                    "interpreted-target="
                    + link.getParent().resolve(stored)
                        .normalize().equals(file));
            System.out.println(
                    "read-through="
                    + Files.readString(
                        link, StandardCharsets.UTF_8));
            System.out.println(
                    "same-file=" + Files.isSameFile(link, file));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(file);
            Files.deleteIfExists(links);
            Files.deleteIfExists(data);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all RelativeSymlinkDemo.java
java RelativeSymlinkDemo
```

**stdout khi filesystem cho phép tạo symlink:**

```text
symlink=created
stored=../data/report.txt
stored-relative=true
interpreted-target=true
read-through=HELLO
same-file=true
```

**stdout khi provider/quyền không cho phép thao tác tạo link:**

```text
symlink=unavailable
```

Trên một số cấu hình Windows, tạo symbolic link có thể yêu cầu điều kiện đặc biệt về quyền hoặc Developer Mode. Ví dụ **không yêu cầu nâng quyền**, chỉ ghi rõ bài test không thể chạy nhánh tạo link trong môi trường đó. Đừng áp dụng nhánh bắt mọi `IOException` rồi trả “thành công” trong ứng dụng thật nếu symlink là tính năng bắt buộc; ở đây chỉ dùng để làm ví dụ portable.

**Điều đã được kiểm chứng khi nhánh tạo thành công:**

1. `Files.createSymbolicLink(link, storedTarget)` lưu đích tương đối.
2. `Files.readSymbolicLink(link)` đọc lại đích tương ứng, không trả absolute target theo mặc định.
3. `link.getParent().resolve(stored).normalize()` trùng đường dẫn file thật trong layout do demo tạo.
4. `Files.readString(link, UTF_8)` đi qua link để đọc nội dung của file đích.
5. `Files.isSameFile(link,file)` xác nhận hai đường dẫn tham chiếu cùng một file trong tình huống đã setup.
6. Cleanup xóa **symlink trước**, sau đó mới xóa file đích và các thư mục.

Lưu ý: nếu provider trả một biểu diễn pathname khác nhưng tương đương về filesystem, không nên yêu cầu từng byte ký tự từ `readSymbolicLink` phải giống hệt chuỗi text nguyên thủy; hãy dùng `Path` và contract của provider cho so sánh.

## 5. Đường dẫn tương đối không phải luôn dựa vào user.dir

Một nhầm lẫn rất phổ biến:

```java
Path stored = Files.readSymbolicLink(link);

// Sai điểm gốc nếu stored là target tương đối của symlink:
Path wrong = stored.toAbsolutePath();
```

`stored.toAbsolutePath()` dùng thư mục làm việc của process (theo provider), **không dùng thư mục chứa link**. Đường dẫn `wrong` có thể trỏ tới một file khác hoặc không tồn tại.

Mẫu đúng để tính layout theo cú pháp:

```java
Path absoluteLink = link.toAbsolutePath();
Path stored = Files.readSymbolicLink(absoluteLink);

Path candidate = stored.isAbsolute()
        ? stored
        : absoluteLink.getParent().resolve(stored);
```

Đây là snippet. `candidate` vẫn chỉ là pathname được suy ra; nếu cần chắc chắn file tồn tại và link thực sự dẫn tới đâu ở thời điểm kiểm tra, phải thực hiện thao tác có filesystem access và xử lý lỗi.

### 5.1. Hai mức “relative” cần tách

Ví dụ `link` bạn truyền vào `Files.createSymbolicLink` có thể cũng là relative:

```java
Path link = Path.of("links", "latest.txt");
Path target = Path.of("..", "data", "report.txt");
Files.createSymbolicLink(link, target);
```

Có **hai quan hệ khác nhau**:

- `link` là pathname relative khi ứng dụng chỉ vị trí **tạo entry liên kết**; nó được xác định trong default filesystem theo current working directory của process.
- `target` là pathname relative được **lưu bên trong entry liên kết**; sau khi tạo, khi truy cập qua link nó được diễn giải từ **parent của link**.

Nếu working directory thay đổi ở thời điểm khác hoặc người dùng mở link từ một shell khác, đích tương đối **không thay đổi để chạy theo working directory của người mở**. Điểm gốc vẫn là vị trí entry symlink trong filesystem.

### 5.2. Đích với nhiều tầng và dấu chấm

Giả sử layout:

```text
app/
├── shared/
│   └── config.yml
└── modules/
    └── billing/
        └── config-link.yml -> ../../shared/config.yml
```

Link tại `app/modules/billing/config-link.yml` lưu `../../shared/config.yml`:

- Một `..` từ billing về modules.
- Một `..` nữa từ modules về app.
- Sau đó đi xuống shared/config.yml.

Nếu bạn tính `../shared/config.yml`, nó trỏ vào `app/modules/shared/config.yml`, không đúng. `relativize` từ `link.getParent()` giúp tránh lỗi đếm tầng khi hai `Path` đã có cùng root logic.

## 6. Khi di chuyển link, đích có thể đổi mà chuỗi lưu không đổi

Đây là hệ quả quan trọng nhất của relative symlink: **đích được hiểu theo vị trí hiện tại của entry link**.

Ví dụ ban đầu:

```text
project/
├── from/
│   ├── data.txt       nội dung FROM
│   └── shortcut.txt -> data.txt
└── to/
    └── data.txt       nội dung TO
```

Nếu chỉ di chuyển `shortcut.txt` từ `from/` sang `to/` bằng `Files.move`, liên kết vẫn lưu `data.txt`. Nhưng giờ nó nằm trong `to/`, vì vậy nó trỏ tới `to/data.txt` và đọc được nội dung `TO`.

**Không phải `Files.move` đã sửa chuỗi lưu; mà là vị trí cha của link đã đổi.**

### 6.1. Ví dụ runnable: di chuyển link đổi file được trỏ tới

Tạo `RelativeLinkMoveDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RelativeLinkMoveDemo {
    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("move-link-");
        Path from = root.resolve("from");
        Path to = root.resolve("to");
        Path firstData = from.resolve("data.txt");
        Path secondData = to.resolve("data.txt");
        Path originalLink = from.resolve("shortcut.txt");
        Path movedLink = to.resolve("shortcut.txt");

        try {
            Files.createDirectory(from);
            Files.createDirectory(to);
            Files.writeString(
                    firstData, "FROM", StandardCharsets.UTF_8);
            Files.writeString(
                    secondData, "TO", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        originalLink, Path.of("data.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            Path before = Files.readSymbolicLink(originalLink);
            String contentBefore = Files.readString(
                    originalLink, StandardCharsets.UTF_8);

            Files.move(originalLink, movedLink);

            Path after = Files.readSymbolicLink(movedLink);
            String contentAfter = Files.readString(
                    movedLink, StandardCharsets.UTF_8);

            System.out.println("symlink=created");
            System.out.println("before=" + contentBefore);
            System.out.println("stored-after=" + after);
            System.out.println("after=" + contentAfter);
            System.out.println(
                    "stored-unchanged=" + before.equals(after));
        } finally {
            Files.deleteIfExists(movedLink);
            Files.deleteIfExists(originalLink);
            Files.deleteIfExists(firstData);
            Files.deleteIfExists(secondData);
            Files.deleteIfExists(from);
            Files.deleteIfExists(to);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all RelativeLinkMoveDemo.java
java RelativeLinkMoveDemo
```

**stdout nếu tạo symlink được:**

```text
symlink=created
before=FROM
stored-after=data.txt
after=TO
stored-unchanged=true
```

**stdout nếu không thể tạo symlink:**

```text
symlink=unavailable
```

Ví dụ dùng hai file có nội dung khác nhau để chứng minh **đối tượng đích đã đổi**. `Files.move` di chuyển **chính entry symlink**, không di chuyển file `from/data.txt`. Trong cùng một filesystem và điều kiện cho phép, relative target được lưu vẫn là `data.txt`.

Khi triển khai hệ thống build/package/deploy, **đừng move riêng lẻ symlink tương đối mà không xét vị trí cha mới**. Nếu mục tiêu là giữ link trỏ tới một file cụ thể, bạn có thể cần **tạo lại symlink với một relative target mới** tính theo parent mới hoặc lựa chọn absolute target phù hợp với môi trường.

### 6.2. Khi di chuyển cả cây thư mục

Nếu bạn chuyển cả cây `project` mà **quan hệ giữa links và target vẫn giữ nguyên**, các relative symlinks nội bộ thường giữ được ý nghĩa vì đường dẫn tương đối giữa các entry không thay đổi. Tuy nhiên, link trỏ **ra ngoài cây** hoặc link có ancestor symlink/mount khác có thể bị hỏng hoặc thay đổi đối tượng.

Chỉ dùng symlink tương đối như một kỹ thuật tạo layout relocatable khi bạn kiểm soát tương đối đầy đủ **cấu trúc thư mục, package và vòng đời**. Không có lời hứa “mọi symlink relative vẫn đúng dù move đến đâu”.

## 7. Link tồn tại nhưng target không tồn tại: dangling symlink

**Dangling symlink** (hay broken symlink) là entry liên kết còn tồn tại nhưng đường dẫn đích không resolve đến một đối tượng tồn tại/được truy cập. Điều này xảy ra khi:

- Target bị xóa sau khi tạo link.
- Link bị di chuyển sang parent khác.
- Một relative path được tính sai.
- Target nằm trên mount/volume chưa gắn.
- Đường dẫn vòng lặp symlink hoặc không thể resolve.
- Provider/permissions khiến đích không thể được xác định.

Vì `Files.createSymbolicLink` cho phép target **không tồn tại**, link có thể dangling ngay khi tạo trên filesystem phù hợp.

### 7.1. Hai cách hỏi “tồn tại” khác nhau

`Files.exists(link)` mặc định **theo symbolic link**, nghĩa là nó hỏi trạng thái của đích được resolve. Với dangling symlink, nó thường trả `false`.

`Files.exists(link, LinkOption.NOFOLLOW_LINKS)` hỏi trạng thái **của chính entry link**, không follow; nếu link entry tồn tại và xác định được, nó trả `true`.

Ngoài ra:

- `Files.isSymbolicLink(link)` hỏi path có là symbolic link entry không; nếu không thể xác định được có thể trả false.
- `Files.readSymbolicLink(link)` có thể trả stored target **ngay cả khi target không tồn tại**.
- `Files.isRegularFile(link)` mặc định follow link, vì vậy một link dangling không được xem là regular file qua đích.
- `Files.readString(link)` cần mở target thực; có thể ném `NoSuchFileException` hoặc lỗi provider khác khi target không tồn tại.

**Không coi `Files.exists(link)==false` là chứng minh “có thể tạo một entry khác tên đó mà không trùng”.** Một dangling symlink vẫn có thể chiếm pathname, làm `createFile`/`createSymbolicLink` báo đã tồn tại.

### 7.2. Ví dụ runnable: một relative target chưa có thật

Tạo `DanglingRelativeLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class DanglingRelativeLinkDemo {
    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("dangling-");
        Path link = root.resolve("shortcut.txt");
        Path stored = Path.of("missing.txt");

        try {
            try {
                Files.createSymbolicLink(link, stored);
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            System.out.println("symlink=created");
            System.out.println(
                    "is-link=" + Files.isSymbolicLink(link));
            System.out.println(
                    "follows-exists=" + Files.exists(link));
            System.out.println(
                    "nofollow-exists="
                    + Files.exists(
                        link, LinkOption.NOFOLLOW_LINKS));
            System.out.println(
                    "stored=" + Files.readSymbolicLink(link));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DanglingRelativeLinkDemo.java
java DanglingRelativeLinkDemo
```

**stdout trên provider có thể tạo symlink dangling:**

```text
symlink=created
is-link=true
follows-exists=false
nofollow-exists=true
stored=missing.txt
```

**stdout khi không thể tạo symlink:**

```text
symlink=unavailable
```

**Giới hạn của `Files.exists`:** trả `false` cũng có thể có nghĩa không xác định được trạng thái do I/O/permission, không phải bằng chứng tuyệt đối về không tồn tại. Với nghiệp vụ cần phân biệt thật rõ, dùng `Files.readAttributes(..., NOFOLLOW_LINKS)` và xử lý checked `IOException`.

### 7.3. Path của link và Path của target không phải một

Với ví dụ ở trên:

- `link` có pathname tuyệt đối nằm trong thư mục tạm.
- `stored` bằng `missing.txt` và **là relative**.
- `link.getParent().resolve(stored)` là một pathname dưới thư mục tạm.
- Không có file thật ở pathname này, nhưng **entry symlink vẫn có thể tồn tại**.

Khi cần xóa một broken link, `Files.deleteIfExists(link)` xóa entry liên kết đó, không tự cố xóa một target không tồn tại.

## 8. normalize, toAbsolutePath và toRealPath khác nhau thế nào?

Các phương thức `Path` có mục đích khác nhau:

| API | Ý nghĩa | Có cần target thật? |
| --- | --- | --- |
| `normalize()` | Loại bỏ `.`/`..` theo **cú pháp** provider | Không |
| `toAbsolutePath()` | Đưa pathname về dạng absolute theo provider/working dir | Không nhất thiết |
| `resolve(other)` | Ghép/giải quyết pathname theo quy tắc `Path` | Không |
| `relativize(other)` | Tính path tương đối từ một path đến path khác | Không |
| `Files.readSymbolicLink(link)` | Đọc target được **lưu** trong entry symlink | **Link** phải tồn tại và là symlink; target có thể không tồn tại |
| `toRealPath()` | Tìm real path của entry đang tồn tại; mặc định follow symlink | Có, có thể ném `IOException` |
| `toRealPath(NOFOLLOW_LINKS)` | Lấy real path nhưng yêu cầu không resolve symlink theo option | Cần xác định entry thực, phụ thuộc provider |
| `Files.isSameFile(a,b)` | Kiểm tra hai path chỉ cùng file thực theo contract | Thường cần truy cập file system; có thể ném `IOException` |

**Đặc biệt:** `normalize()` có thể đổi đối tượng filesystem được trỏ đến nếu thành phần trước `..` là một symlink. Vì vậy **không coi lexical normalization là thay thế hoàn hảo của realpath**.

### 8.1. Ví dụ runnable: realpath theo link và thuộc tính link

Tạo `LinkRealPathDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class LinkRealPathDemo {
    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("realpath-link-");
        Path target = root.resolve("real.txt");
        Path link = root.resolve("alias.txt");

        try {
            Files.writeString(
                    target, "REAL", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        link, Path.of("real.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            BasicFileAttributes linkAttrs =
                    Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

            System.out.println("symlink=created");
            System.out.println(
                    "lexical-different="
                    + !link.normalize().equals(
                        target.normalize()));
            System.out.println(
                    "follow-same-real="
                    + link.toRealPath().equals(
                        target.toRealPath()));
            System.out.println(
                    "nofollow-is-link="
                    + linkAttrs.isSymbolicLink());
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LinkRealPathDemo.java
java LinkRealPathDemo
```

**stdout nếu tạo symlink được:**

```text
symlink=created
lexical-different=true
follow-same-real=true
nofollow-is-link=true
```

**stdout nếu không thể tạo symlink:**

```text
symlink=unavailable
```

`link.normalize()` và `target.normalize()` là hai pathname khác nhau, nhưng `toRealPath()` khi được gọi trên link mặc định **follow** tới target nên cùng real location. `BasicFileAttributes` với `NOFOLLOW_LINKS` mô tả **entry liên kết** chứ không mô tả file `real.txt`.

Khi code chỉ cần biết **stored target** để ghi nhận trong một report về links, dùng `Files.readSymbolicLink`. Khi code cần biết **đang trỏ tới file nào và target phải tồn tại**, dùng cơ chế truy cập filesystem và `toRealPath`/`Files.isSameFile` theo nhu cầu; phải xử lý ngoại lệ và thay đổi đồng thời.

## 9. Symlink trỏ tới thư mục cũng theo cùng nguyên tắc

Một symlink có thể lưu relative target trỏ tới **directory**, không chỉ file thường:

```text
workspace/
├── data/
│   └── guide.txt
└── links/
    └── current -> ../data
```

Ở đây `links/current` trỏ tới directory `data`. Khi gọi `links/current/guide.txt`, filesystem đi qua entry link để truy cập tệp `data/guide.txt` theo quan hệ.

Đừng nhầm:

- `Files.isDirectory(link)` mặc định theo link, nên có thể true.
- `Files.isDirectory(link, NOFOLLOW_LINKS)` kiểm tra entry link, nên không coi nó là directory khi nó là symlink.
- `Files.isSymbolicLink(link)` phân biệt entry liên kết.
- `Files.readSymbolicLink(link)` trả stored target `../data`; không phải full tree đích.
- `Files.walkFileTree` mặc định không follow symbolic links trừ khi yêu cầu `FOLLOW_LINKS` theo contract.

### 9.1. Ví dụ runnable: relative link tới thư mục

Tạo `RelativeDirectoryLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class RelativeDirectoryLinkDemo {
    static String portable(Path p) {
        return p.toString().replace('\\', '/');
    }

    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("dir-link-");
        Path data = root.resolve("data");
        Path links = root.resolve("links");
        Path guide = data.resolve("guide.txt");
        Path link = links.resolve("current");

        try {
            Files.createDirectory(data);
            Files.createDirectory(links);
            Files.writeString(
                    guide, "GUIDE", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                    link, Path.of("..", "data"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            System.out.println("symlink=created");
            System.out.println(
                    "stored="
                    + portable(Files.readSymbolicLink(link)));
            System.out.println(
                    "follow-directory=" + Files.isDirectory(link));
            System.out.println(
                    "nofollow-directory="
                    + Files.isDirectory(
                        link, LinkOption.NOFOLLOW_LINKS));
            System.out.println(
                    "nested-read="
                    + Files.readString(
                        link.resolve("guide.txt"),
                        StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(guide);
            Files.deleteIfExists(data);
            Files.deleteIfExists(links);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all RelativeDirectoryLinkDemo.java
java RelativeDirectoryLinkDemo
```

**stdout nếu tạo symlink được:**

```text
symlink=created
stored=../data
follow-directory=true
nofollow-directory=false
nested-read=GUIDE
```

**stdout khi provider/permission không cho phép:**

```text
symlink=unavailable
```

Windows có thể có yêu cầu riêng về loại symlink dành cho file hoặc directory; vì vậy demo tạo **directory đích có thật** trước khi tạo link. Với chương trình triển khai thực tế, không giả định mọi filesystem/provider cho phép tạo link đến directory, và cần xử lý quyền/exception phù hợp.

## 10. Copy một symlink có đích tương đối: theo link hay copy chính link?

`Files.copy(source,target)` có hai kiểu hành vi quan trọng khi `source` là symlink:

- **Mặc định:** theo symlink nguồn và copy nội dung file được trỏ đến nếu có thể.
- **Với `LinkOption.NOFOLLOW_LINKS`:** yêu cầu copy **chính entry symbolic link** thay vì target; provider đích phải hỗ trợ tạo symlink.

**Hệ quả của việc copy chính symlink:** stored target có thể giữ nguyên `data.txt`, nhưng **entry copy nằm trong một thư mục cha khác**, nên nó có thể trỏ tới file khác hoặc trở thành dangling link.

Không coi thao tác copy symlink bằng `NOFOLLOW_LINKS` giống copy nội dung target; và cũng không coi `Files.copy` là công cụ tự sửa lại đường dẫn tương đối khi destination thay đổi.

### 10.1. Ví dụ runnable: hai cách copy cho hai kết quả khác nhau

Tạo `CopyRelativeLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class CopyRelativeLinkDemo {
    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("copy-link-");
        Path from = root.resolve("from");
        Path to = root.resolve("to");
        Path fromData = from.resolve("data.txt");
        Path toData = to.resolve("data.txt");
        Path original = from.resolve("shortcut.txt");
        Path contentCopy = to.resolve("content.txt");
        Path linkCopy = to.resolve("link-copy.txt");

        try {
            Files.createDirectory(from);
            Files.createDirectory(to);
            Files.writeString(
                    fromData, "FROM", StandardCharsets.UTF_8);
            Files.writeString(
                    toData, "TO", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                    original, Path.of("data.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            Files.copy(original, contentCopy);
            Files.copy(
                    original, linkCopy,
                    LinkOption.NOFOLLOW_LINKS);

            System.out.println("symlink=created");
            System.out.println(
                    "content-copy-is-link="
                    + Files.isSymbolicLink(contentCopy));
            System.out.println(
                    "content-copy-text="
                    + Files.readString(
                        contentCopy, StandardCharsets.UTF_8));
            System.out.println(
                    "link-copy-is-link="
                    + Files.isSymbolicLink(linkCopy));
            System.out.println(
                    "link-copy-stored="
                    + Files.readSymbolicLink(linkCopy));
            System.out.println(
                    "original-text="
                    + Files.readString(
                        original, StandardCharsets.UTF_8));
            System.out.println(
                    "link-copy-text="
                    + Files.readString(
                        linkCopy, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(linkCopy);
            Files.deleteIfExists(contentCopy);
            Files.deleteIfExists(original);
            Files.deleteIfExists(fromData);
            Files.deleteIfExists(toData);
            Files.deleteIfExists(from);
            Files.deleteIfExists(to);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CopyRelativeLinkDemo.java
java CopyRelativeLinkDemo
```

**stdout khi provider hỗ trợ tạo và copy symlink:**

```text
symlink=created
content-copy-is-link=false
content-copy-text=FROM
link-copy-is-link=true
link-copy-stored=data.txt
original-text=FROM
link-copy-text=TO
```

**stdout khi không tạo được symlink ban đầu:**

```text
symlink=unavailable
```

Vì `to/data.txt` có nội dung `TO`, bản sao link với stored target `data.txt` ở `to/link-copy.txt` trỏ đến **file của thư mục to**, không phải `from/data.txt`. Trong khi đó, copy mặc định tạo tệp nội dung `content.txt` chứa `FROM` và **không phải symlink**.

**Portability:** nếu provider cho phép tạo link ban đầu nhưng không hỗ trợ copy link với `NOFOLLOW_LINKS` ở filesystem đích, thao tác copy thứ hai có thể ném `IOException`/`UnsupportedOperationException`. Code demo để lỗi đó lan ra thay vì âm thầm giả vờ thành công; ứng dụng thật cần chọn policy rõ ràng (materialize target bytes, báo không hỗ trợ, hoặc tạo lại link theo vị trí mới).

### 10.2. Sao chép một link thành dangling link

Nếu `to/data.txt` **không** tồn tại, bản sao `to/link-copy.txt` vẫn có thể tồn tại dưới dạng symbolic link có stored target `data.txt`, nhưng mặc định follow sẽ không tìm thấy đích. `Files.exists(toLink,NOFOLLOW_LINKS)` có thể true trong khi `Files.exists(toLink)` false.

**Không nên “sửa link” bằng cách lấy raw `readSymbolicLink` rồi gọi `toAbsolutePath()`**: khi đó bạn đã dùng working directory thay vì parent của link nguồn. Nếu cần giữ đúng đối tượng đích, xác định source link target theo đúng ngữ nghĩa, sau đó tính relative path mới **từ parent của link đích**.

## 11. Xóa symbolic link không xóa tệp đích

`Files.delete(link)` hoặc `Files.deleteIfExists(link)` xóa **entry symbolic link**, không xóa nội dung tệp cuối được link trỏ tới. Điều này quan trọng với cleanup và quản lý symlink dangling.

### 11.1. Ví dụ runnable: unlink rồi file thật vẫn còn

Tạo `DeleteRelativeLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class DeleteRelativeLinkDemo {
    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("delete-link-");
        Path target = root.resolve("file.txt");
        Path link = root.resolve("alias.txt");

        try {
            Files.writeString(
                    target, "SAFE", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                    link, Path.of("file.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println("symlink=unavailable");
                return;
            }

            System.out.println("symlink=created");
            Files.delete(link);

            System.out.println(
                    "link-removed="
                    + !Files.exists(
                        link, LinkOption.NOFOLLOW_LINKS));
            System.out.println(
                    "target-preserved="
                    + Files.readString(
                        target, StandardCharsets.UTF_8)
                        .equals("SAFE"));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DeleteRelativeLinkDemo.java
java DeleteRelativeLinkDemo
```

**stdout nếu tạo symlink được:**

```text
symlink=created
link-removed=true
target-preserved=true
```

**stdout nếu tạo symlink không khả dụng:**

```text
symlink=unavailable
```

Đừng nhầm với `Files.delete(link.resolve("child.txt"))` nếu `link` trỏ tới **directory**: thao tác đó tác động đến entry `child.txt` dưới directory đích sau khi traversal theo link, không phải chỉ xóa link directory. Khi dọn cây thư mục không đáng tin, nên dùng visitor và chính sách follow-link rõ, không tự tạo pathname dưới link rồi gọi delete bừa bãi.

## 12. Symlink khác hard link và shortcut

**Symbolic link:** lưu một target pathname; target có thể tương đối/tuyệt đối, có thể không tồn tại, có thể thay đổi ý nghĩa khi link đổi parent.

**Hard link:** một directory entry khác trỏ đến cùng đối tượng file. `Files.createLink(newLink,existing)` dùng cơ chế hard link khi provider hỗ trợ. Nó không lưu một chuỗi pathname “`../data/real.txt`” để resolver lại mỗi lần dùng. Vì vậy mô hình “stored relative path” của bài này **không áp dụng cho hard link**.

**Shortcut/alias của ứng dụng:** ví dụ một tệp Windows `.lnk` là định dạng riêng, không mặc nhiên là filesystem symbolic link do `Files.isSymbolicLink` nhận diện. Đừng nhầm file `.lnk` với một entry symlink NIO.2.

**Không suy giống nhau chỉ từ giao diện người dùng:** các file managers có thể hiển thị icon mũi tên cho nhiều kiểu liên kết khác nhau. Với Java, lựa chọn API theo loại entry thực tế.

| Đặc điểm | Symbolic link | Hard link |
| --- | --- | --- |
| Lưu pathname đích để resolve? | Có | Không theo mô hình symlink |
| Target pathname có thể relative? | Có | Không có khái niệm stored target path tương ứng |
| Target chưa có khi tạo? | Có thể | Không, hard link cần đối tượng file có thật |
| Đổi parent của link ảnh hưởng stored relative path? | Có thể thay target được resolve | Không theo cơ chế stored target |
| `Files.readSymbolicLink` dùng được? | Có, nếu provider hỗ trợ | Không phải symlink; thường thất bại |
| `Files.delete(link)` | Xóa entry link | Xóa directory entry; dữ liệu có thể vẫn còn qua hard links khác |

## 13. Bảo mật: đích tương đối có thể thoát khỏi root

Giả sử ứng dụng cho phép tạo symlink trong thư mục `uploads/links` và client được gửi một target như `../data/report.txt`. Nếu không kiểm soát, client có thể cung cấp nhiều `..` hơn, một đường dẫn tuyệt đối hoặc liên kết đến khu vực nhạy cảm.

Một **kiểm tra lexical** tối thiểu để minh họa:

1. Root tin cậy là một `Path` absolute đã normalize.
2. Symlink entry dự kiến nằm dưới root theo cấu trúc ứng dụng.
3. Nếu policy chỉ cho relative target, từ chối `stored.isAbsolute()`.
4. Resolve stored **từ parent của link**, không từ JVM working directory.
5. Normalize kết quả **cho kiểm tra cú pháp** và dùng `Path.startsWith(root)` theo thành phần, không dùng `String.startsWith`.

### 13.1. Ví dụ runnable: kiểm tra lexical path, không cần quyền tạo symlink

Tạo `RelativeLinkBoundaryDemo.java`:

```java
import java.nio.file.Path;

public class RelativeLinkBoundaryDemo {
    static boolean lexicalInside(
            Path trustedRoot,
            Path link,
            Path storedTarget) {
        Path root = trustedRoot
                .toAbsolutePath().normalize();
        Path location = link
                .toAbsolutePath().normalize();

        if (!location.startsWith(root)
                || storedTarget.isAbsolute()) {
            return false;
        }

        Path candidate = location.getParent()
                .resolve(storedTarget).normalize();
        return candidate.startsWith(root);
    }

    public static void main(String[] args) {
        Path root = Path.of("sandbox")
                .toAbsolutePath().normalize();
        Path link = root.resolve("links")
                .resolve("current.txt");

        Path within = Path.of(
                "..", "data", "report.txt");
        Path escapes = Path.of(
                "..", "..", "private.txt");
        Path absolute = root.resolve("secret.txt");

        System.out.println(
                "inside-lexically="
                + lexicalInside(root, link, within));
        System.out.println(
                "escape-lexically="
                + lexicalInside(root, link, escapes));
        System.out.println(
                "absolute-lexically="
                + lexicalInside(root, link, absolute));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all RelativeLinkBoundaryDemo.java
java RelativeLinkBoundaryDemo
```

**stdout chính xác trên mọi hệ điều hành:**

```text
inside-lexically=true
escape-lexically=false
absolute-lexically=false
```

**Giới hạn cực kỳ quan trọng:** hàm này chỉ xét **tên đường dẫn theo cú pháp**. Nó **không chứng minh** mọi I/O sau đó vẫn nằm trong root khi:

- Một thành phần cha của link/target là symlink trỏ ra ngoài.
- Một tiến trình khác thay entry giữa lúc check và lúc mở file (TOCTOU).
- Filesystem có mount points, junctions/reparse points, hard links hoặc identity aliases.
- Caller có quyền cao hơn và có thể đi qua các lớp security khác.
- Đích tồn tại tại một vị trí được root lexical chấp nhận nhưng thực tế đi qua một symlink khác.

Với dữ liệu không đáng tin, **không dùng đoạn kiểm tra trên như một sandbox hoàn chỉnh**. Giải pháp thực tế cần giới hạn quyền của process, chỉ thao tác trong directory do server quản lý, xác minh real location theo policy và cân nhắc primitive dựa trên directory handle như `SecureDirectoryStream` khi provider hỗ trợ, cùng biện pháp chống race. Đối với phần lớn dịch vụ, **tránh cho client tự tạo symlink tùy ý** là lựa chọn dễ kiểm soát hơn.

### 13.2. Không tin rằng NOFOLLOW_LINKS giải quyết mọi vấn đề

`LinkOption.NOFOLLOW_LINKS` điều chỉnh cách một số thao tác cụ thể xử lý **symlink cuối cùng** hoặc attributes. Nó không tự đảm bảo mọi **thư mục cha** trong pathname là đường dẫn thông thường và không loại bỏ TOCTOU.

Ví dụ, `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)` có thể cho biết entry cuối là symlink. Nhưng nếu parent `uploads/links` là một symlink do actor khác quản lý, chính thao tác tìm đến entry đã đi qua parent đó theo quy tắc provider.

Cần hiểu **từng overload**: `NOFOLLOW_LINKS` không có ý nghĩa giống nhau cho mọi API. Không truyền nó tùy tiện vào mọi method rồi khẳng định đã chống đường dẫn ngoài root.

### 13.3. Tránh so sánh prefix bằng chuỗi

Sai:

```java
boolean allowed = candidate.toString()
        .startsWith(root.toString());
```

`/data/private-extra` có prefix text `/data/private` nhưng không phải entry dưới directory `/data/private`. `Path.startsWith(root)` so theo **name elements** của provider, là lựa chọn phù hợp hơn cho kiểm tra lexical. **Vẫn cần kiểm soát symlinks và race** ở mức filesystem.

## 14. Tạo, di chuyển, copy và xóa: bảng hành vi so sánh

| Tác vụ | Method | Tác động với stored relative target |
| --- | --- | --- |
| Tạo link | `Files.createSymbolicLink(link, stored)` | Lưu stored target relative/absolute theo khả năng provider |
| Đọc link | `Files.readSymbolicLink(link)` | Trả stored target; không yêu cầu target tồn tại |
| Đọc nội dung qua link | `Files.readString(link, UTF_8)` | Theo link để đọc nội dung file target |
| Kiểm tra entry link | `Files.isSymbolicLink(link)` | Hỏi pathname có là symlink không |
| Kiểm tra tồn tại mặc định | `Files.exists(link)` | Follow link; dangling thường false |
| Kiểm tra tồn tại không follow | `Files.exists(link, NOFOLLOW_LINKS)` | Hỏi entry link; dangling thường true |
| Đọc attributes không follow | `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Thuộc tính của entry link |
| Tính real path mặc định | `link.toRealPath()` | Follow link, cần target tồn tại |
| Copy mặc định | `Files.copy(link,dest)` | Copy **nội dung target** nếu có thể |
| Copy không follow | `Files.copy(link,dest,NOFOLLOW_LINKS)` | Copy **entry link** nếu provider hỗ trợ; stored relative target có thể đổi ý nghĩa |
| Move link | `Files.move(link,dest)` | Di chuyển entry link; không tự tính lại target relative |
| Xóa link | `Files.deleteIfExists(link)` | Xóa entry link, không xóa tệp cuối |
| Tạo hard link | `Files.createLink(newEntry,existingFile)` | Không lưu target pathname kiểu symlink |

**Chọn API theo mục tiêu thực tế**: bạn muốn copy nội dung file, copy entry link, giữ một relationship relative có thể di chuyển, hay giữ nguyên một file cuối? Bốn việc đó không hoàn toàn giống nhau.

## 15. Portability trên Windows, Unix và provider khác

Symlinks là **tính năng filesystem/provider**, không phải API Java đảm bảo tạo được ở mọi nơi. Cùng chương trình có thể gặp:

- `UnsupportedOperationException`: implementation không hỗ trợ symbolic links.
- `IOException`/`FileSystemException`: filesystem, quyền, điều kiện tạo link hoặc I/O không cho phép.
- `FileAlreadyExistsException`: tên link đã có entry; thường là subtype của `IOException`.
- `NotLinkException`: cố `readSymbolicLink` trên entry không phải symlink, trên provider báo được subtype này.
- `NoSuchFileException`: link entry không tồn tại hoặc thao tác follow target không thể tìm thấy file.
- `SecurityException`: chính sách quyền liên quan hoạt động của provider/JVM.
- `FileSystemLoopException` hoặc lỗi I/O khác: symlink chain có cycle khi cố resolve.

**Windows:** có thể cần quyền/thiết lập OS cụ thể để tạo symlink. Demo trên Java không nên yêu cầu người học nâng quyền quản trị chỉ để chạy một ví dụ. Nếu môi trường thiếu quyền, có thể đọc phần tính pathname trên mọi máy và chạy integration tests trên một môi trường Linux/POSIX phù hợp, hoặc cấu hình Windows theo chính sách của tổ chức.

**Unix/Linux:** symlink thường được hỗ trợ trên filesystem phổ biến, nhưng permission, mount policy, namespace/container và filesystem đặc biệt vẫn có thể khiến tạo/đọc link thất bại.

**ZIP/JAR filesystem:** không nên giả định mọi provider có symbolic link entries hoặc có cách lưu đích giống default provider. Test support trên filesystem thực tế và để lỗi không hỗ trợ lan ra đúng tầng.

### 15.1. Test feature thay vì hard-code tên hệ điều hành

Đừng viết:

```java
if (System.getProperty("os.name").contains("Windows")) {
    // Luôn không có symlink.
}
```

Cấu hình Windows khác nhau có thể cho phép symlink, còn một POSIX OS cũng có file store hạn chế. Thay vào đó, với **integration test**, thử tạo link trong một thư mục tạm thuộc chính filesystem mục tiêu, xử lý ngoại lệ, dọn an toàn và **phân biệt test bị skip với tính năng đã được kiểm chứng**.

Nếu symlink là **yêu cầu bắt buộc của sản phẩm**, ứng dụng nên fail rõ khi không tạo được, không lặng lẽ chuyển sang copy tệp hay tạo shortcut `.lnk` rồi coi đó là cùng semantics.

## 16. Các tình huống ứng dụng

### 16.1. Cấu trúc deploy có thể di chuyển

Một package có:

```text
release/
├── versions/
│   └── 2026-11/
│       └── config.json
└── config-current.json -> versions/2026-11/config.json
```

Liên kết tương đối mang relation nội bộ nên khi cả `release` được di chuyển cùng cấu trúc, nó có thể tiếp tục đúng. Nhưng cần kiểm soát thay đổi phiên bản, quyền truy cập và atomically publishing policy; symlink không tự trở thành transaction hoặc backup.

### 16.2. Plugin có thư viện dùng chung

`plugins/example/resources` có thể lưu target relative như `../../shared/resources`. Khi copy chỉ mỗi plugin sang directory khác, đường dẫn tương đối có thể trỏ sai. Packaging tool cần quyết định copy **target content** hay copy **link entry** hoặc tính lại relative target từ vị trí mới.

### 16.3. Development workspace

Một symlink `current` có thể trỏ tới bản build hiện tại để scripts không phải đổi đường dẫn mỗi lần build. Nếu chỉ đổi target file, symlink vẫn lưu pathname tương đối; nếu đổi parent của link, cùng stored target sẽ có ý nghĩa khác. Khi cần cập nhật link, hãy cân nhắc tạo entry tạm/rename theo hợp đồng của filesystem thay vì xóa link rồi để một khoảng trống không kiểm soát.

### 16.4. Backup và archive

Nếu backup chỉ lưu **nội dung target** của mọi symlink, khôi phục sẽ không bảo toàn topology của links. Nếu backup lưu **stored relative target**, phục hồi vào cấu trúc directory khác có thể tạo dangling links hoặc link trỏ tới file khác. Phải xác định backup contract: nội dung, metadata, link topology, root mapping và chính sách security.

**Không coi symlink tự động là file duplicate**: link không nhất thiết làm nội dung target được nhân đôi trên ổ đĩa.

## 17. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Đọc `readSymbolicLink(link)` rồi gọi `toAbsolutePath` | Giải từ working directory thay vì parent link | Relative stored target cần diễn giải từ `link.getParent()` |
| Tính target bằng `link.relativize(target)` | Chọn sai mốc so với directory chứa link | Dùng `link.getParent().relativize(target)` |
| Tự nối `"../"` nhiều lần bằng String | Dễ sai tầng và dấu phân tách OS | Dùng Path/relativize với các path tương thích |
| Nghĩ `Files.createSymbolicLink` tạo cả file target | Nó chỉ tạo entry link | Tạo target riêng khi nghiệp vụ yêu cầu |
| Nghĩ target phải tồn tại khi tạo link | Có thể tạo dangling symlink | Xác định nếu sản phẩm cho phép dangling hay không |
| Nghĩ `Files.exists(link) == false` thì tên entry rảnh | Dangling link có thể tồn tại | Kiểm tra `NOFOLLOW_LINKS` và xử lý create conflict |
| Nghĩ stored target luôn absolute | Link có thể lưu relative | Kiểm tra `stored.isAbsolute()` |
| Nghĩ di chuyển link không đổi nơi nó trỏ đến | Parent mới làm relative target đổi ý nghĩa | Kiểm tra/viết lại target tương đối sau move nếu cần |
| Nghĩ copy link theo mặc định luôn giữ link | Copy mặc định thường theo source link | Dùng `NOFOLLOW_LINKS` khi chủ đích copy link entry |
| Nghĩ NOFOLLOW copy link luôn giữ cùng file cuối | Parent của link copy khác parent ban đầu | Tính lại relative target cho vị trí mới khi cần |
| Nghĩ `Files.delete(link)` xóa target | Xóa link entry | Phân biệt xóa alias và file thật |
| Nghĩ `normalize()` là realpath | Normalize chỉ lexical, có thể đổi semantics qua symlink + `..` | Dùng file system operations khi cần xác minh thực |
| Nghĩ `NOFOLLOW_LINKS` tự chặn symlink ở mọi parent | Phạm vi option phụ thuộc method | Thiết kế boundary/permissions/TOCTOU riêng |
| Nghĩ Windows luôn không hỗ trợ symlink | Khả năng phụ thuộc quyền, cấu hình và file store | Test trên filesystem thực, không suy từ tên OS |
| Coi hard link là symlink lưu pathname | Hard link không lưu relative target | Dùng `createLink`/`createSymbolicLink` đúng intent |
| Truyền `http:` URI vào `createSymbolicLink` như tệp local | URI không phải Path filesystem tương ứng | Tạo Path trong provider phù hợp; HTTP không phải local file link |
| Đưa symlink target từ client vào đường dẫn root rồi tin lexical prefix | Symlink + TOCTOU có thể thoát root | Hạn chế capability, kiểm tra real boundary và quyền OS |

## 18. Checklist code review

1. **Entry link** đang nằm ở đâu? `link` có absolute không, parent có rõ ràng không?
2. Đích được lưu là **relative hay absolute**? Có lý do lựa chọn này không?
3. Relative target được tính **từ parent của link**, không từ `user.dir` chứ?
4. Có dùng `Path.relativize` trên hai paths cùng root/provider thích hợp không?
5. Link được tạo vào một thư mục cha tồn tại và do ứng dụng kiểm soát không?
6. Có xử lý `UnsupportedOperationException`, `IOException` và quyền tạo symlink không?
7. Có phân biệt link entry tồn tại với file cuối tồn tại bằng `NOFOLLOW_LINKS` khi cần không?
8. Có dùng `Files.readSymbolicLink` để đọc stored target thay vì đoán bằng `toRealPath` không?
9. Nếu cần xác minh file thật, có xử lý `toRealPath` và thời điểm kiểm tra không?
10. Nếu move/copy link sang parent mới, có cập nhật/revalidate relative target không?
11. Với `Files.copy`, có chọn follow target hay `NOFOLLOW_LINKS` theo contract không?
12. Nếu xóa link, có tránh xóa file thật bằng cách thao tác nhầm dưới link directory không?
13. Có symlink chain nhiều lớp, vòng lặp hoặc dangling target không?
14. Có phân biệt symbolic link với hard link và shortcut của ứng dụng không?
15. Có kiểm tra symbolic link entries trong backup/restore và package deploy không?
16. Có hạn chế quyền của process để tránh link traversal vào khu vực nhạy cảm không?
17. Có chống TOCTOU và symlink ở parent paths bằng thiết kế filesystem-level phù hợp không?
18. Có test thành công trên provider hỗ trợ symlink và test nhánh không có permission không?
19. Có test Windows/macOS/Linux và mount/filesystem đích theo hỗ trợ thực tế không?
20. Có phân biệt skip do giới hạn môi trường với QA nội dung Java đã chạy đúng không?

## 19. Bài tập

**Bài 1 — Tính relative target.** Chạy `RelativeTargetPlanningDemo`, đổi layout thành `app/modules/billing/link` và `app/shared/config.yml`. Dự đoán target lưu bằng cách đếm `..`, rồi xác minh `link.getParent().relativize(target)`.

**Bài 2 — Tạo link có đích tương đối.** Chạy `RelativeSymlinkDemo` trên filesystem cho phép symlink, kiểm tra `Files.readSymbolicLink` trả relative `Path` và `Files.readString(link)` đọc nội dung tệp thật.

**Bài 3 — Move link.** Chạy `RelativeLinkMoveDemo` và giải thích vì sao stored target `data.txt` không đổi nhưng nội dung đọc qua symlink lại thay đổi. Thử move cả directory tree và phân tích trường hợp giữ nguyên quan hệ nội bộ.

**Bài 4 — Dangling link.** Chạy `DanglingRelativeLinkDemo`. So sánh `Files.exists(link)`, `Files.exists(link,NOFOLLOW_LINKS)` và `Files.isSymbolicLink(link)`. Tạo target thật sau đó và dự đoán kết quả.

**Bài 5 — Realpath.** Chạy `LinkRealPathDemo`; tìm khác biệt giữa `link.normalize()` và `link.toRealPath()`. Giải thích vì sao một lexical path không đủ làm chứng minh security boundary.

**Bài 6 — Link tới directory.** Chạy `RelativeDirectoryLinkDemo`. Thử tạo nested directory dưới `data` rồi đọc qua `links/current`. Vì sao `Files.isDirectory(link,NOFOLLOW_LINKS)` không đồng ý với `Files.isDirectory(link)`?

**Bài 7 — Copy target và copy link.** Chạy `CopyRelativeLinkDemo`; xóa `to/data.txt` trong setup, tạo bản sao symlink với `NOFOLLOW_LINKS` và phân tích tại sao bản sao link trở thành dangling nhưng nội dung copy mặc định vẫn là `FROM`.

**Bài 8 — Xóa link.** Chạy `DeleteRelativeLinkDemo`. Giải thích vì sao xóa symlink không xóa file target, và vì sao xóa một file con dưới symlink-directory có thể tác động đến thư mục thực.

**Bài 9 — Bảo mật.** Chạy `RelativeLinkBoundaryDemo`. Thêm input `../../../secrets.txt` và giải thích vì sao lexical guard từ chối, nhưng vẫn chưa chống được symlink parent hoặc concurrent replacement.

**Bài 10 — Thiết kế package.** Một build tool copy folder `plugins/feature` chứa symlink `resources -> ../../shared/resources` vào vị trí khác. Thiết kế cách lựa chọn: copy nội dung, preserve link topology hay tính lại relative target; nêu policy khi target không tồn tại và khi filesystem không hỗ trợ symlink.

**Bài 11 — Support matrix.** Viết integration test trên Windows và Linux; dùng thư mục tạm trên file store thực, kiểm tra create/read/delete symlink. Khi tạo symlink lỗi do quyền, báo **SKIPPED_UNAVAILABLE** cho test tùy chọn, nhưng **fail rõ** nếu tính năng sản phẩm bắt buộc.

## 20. Kết luận

- **Symlink relative lưu pathname không có root**, ví dụ `../data/report.txt`.
- **Filesystem diễn giải đích tương đối từ thư mục của chính symlink**, không từ working directory của JVM hay nơi người dùng mở liên kết.
- **`Files.createSymbolicLink(link,target)`** tạo entry link nếu provider/quyền cho phép; target có thể chưa tồn tại.
- **`Files.readSymbolicLink(link)`** trả stored target, không tự đảm bảo target tồn tại hoặc trả realpath.
- **`link.getParent().relativize(target)`** thường là cách hợp lý để tính stored relative target khi hai `Path` tương thích; `link.getParent().resolve(stored)` diễn giải theo cú pháp khi cần.
- **Move/copy entry symlink đến parent khác có thể làm relative target đổi nghĩa** dù chuỗi lưu vẫn như cũ.
- **Dangling symlink** có thể làm `Files.exists(link)` false nhưng `Files.exists(link,NOFOLLOW_LINKS)` true.
- **`normalize` khác `toRealPath`**; kiểm tra lexical không thay thế việc kiểm soát symlink, quyền, TOCTOU và truy cập thực tế.
- **`NOFOLLOW_LINKS`** hữu ích cho kiểm tra/copy link entry nhưng không phải giải pháp bảo mật tổng thể.
- **Java 17+ dùng NIO.2 hiện hành**; việc tạo symlink là optional nên test khả năng provider và phân biệt branch không có quyền, không coi đó là lỗi thời của Java.

## Tài liệu chính thức

- [Files — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `createSymbolicLink`, `readSymbolicLink`, `isSymbolicLink`, `exists`, `copy`, `move` và `delete`.
- [Path — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `getParent`, `resolve`, `relativize`, `normalize` và `toRealPath`.
- [LinkOption — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [BasicFileAttributes — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `isSymbolicLink` và thuộc tính của entry.
- [FileVisitOption — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` trong duyệt cây.
