# Java 7 — Path: Đường dẫn tuyệt đối, tương đối và thư mục làm việc

## Mục tiêu bài học

Khi ứng dụng Java cần mở tệp, tạo thư mục, ghi log hoặc đọc cấu hình, một chuỗi như `"config/app.properties"` **không tự nói rõ tệp nằm ở đâu**. Ý nghĩa của nó phụ thuộc vào ba khái niệm:

1. **Đường dẫn tương đối (relative path):** mô tả vị trí so với một đường dẫn cơ sở, thường là **thư mục làm việc hiện tại** của quá trình chạy.
2. **Đường dẫn tuyệt đối (absolute path):** xác định đường dẫn từ một gốc (root) theo quy tắc của hệ thống tệp/provider hiện hành; không phụ thuộc vào việc nối thêm một thư mục làm việc để có đường dẫn tuyệt đối.
3. **Thư mục làm việc (working directory):** ngữ cảnh dùng để diễn giải nhiều đường dẫn tương đối khi một chương trình chạy. Nó **không nhất thiết là thư mục chứa mã nguồn, tệp `.class`, tệp JAR hay thư mục dự án**.

Java 7 đưa vào NIO.2, gồm `java.nio.file.Path`, `Paths` và `Files`, và các API này vẫn được dùng trên JDK 17+ và các bản Java hiện đại. `Path` biểu diễn một đường dẫn trên hệ thống tệp; `Files` thực hiện những thao tác I/O thực sự. Dùng đúng `Path` giúp code rõ ràng hơn so với tự nối chuỗi bằng `"/"` hoặc `"\\"`.

Sau bài, bạn có thể:

- Dự đoán kết quả của `isAbsolute()`, `getRoot()`, `getParent()`, `getFileName()` và `getNameCount()`.
- Hiểu cách đường dẫn tương đối được diễn giải theo working directory.
- Dùng `resolve`, `resolveSibling`, `normalize`, `relativize` và `toAbsolutePath` đúng ngữ nghĩa.
- Phân biệt phép biến đổi **từ vựng (lexical)** với `toRealPath()` có truy cập hệ thống tệp.
- Phát hiện lỗi “chạy được trong IDE nhưng không chạy được khi triển khai” do nhầm working directory.
- Thiết kế đường dẫn độc lập tương đối với project hoặc một base directory được truyền rõ, thay vì dựa vào nơi code đang được biên dịch.
- Làm việc với tệp thực, URI `file:` và những chi tiết khác nhau giữa Windows/Linux/macOS.
- Nhận ra các giới hạn bảo mật khi xử lý đường dẫn do người dùng cung cấp, đặc biệt `..`, absolute input, symlink và race condition.
- Viết các bài kiểm tra ổn định, không hardcode đường dẫn máy phát triển.

Các chương trình Java hoàn chỉnh dưới đây được **biên dịch bằng `javac --release 17` và chạy trên Windows/JDK hiện đại**. Các ví dụ dùng API hiện vẫn còn hiệu lực; nơi nào đề cập phương thức xuất hiện sau Java 7 sẽ được ghi rõ.

## 1. `Path` không phải chính tệp hay thư mục

Một `Path` là **đối tượng biểu diễn đường dẫn**, không tự tạo tệp và cũng không chứng minh tệp tồn tại. Ví dụ:

```java
Path path = Paths.get("reports", "2026", "summary.txt");
```

Đây là **mảnh minh họa** đặt trong một phương thức, cần import `java.nio.file.Path` và `java.nio.file.Paths`. Chỉ riêng việc tạo `path` không mở hoặc tạo `summary.txt` trên đĩa.

Hai nhóm API cần phân biệt:

| Việc cần làm | API thường dùng | Có đụng đến hệ thống tệp không? |
| --- | --- | --- |
| Biểu diễn một đường dẫn | `Paths.get(...)` / `Path.of(...)` | Không cần tệp phải tồn tại |
| Hỏi đường dẫn có absolute không | `path.isAbsolute()` | Không cần tệp tồn tại |
| Ghép đường dẫn | `base.resolve(child)` | Phần lớn là thao tác từ vựng |
| Xóa `.`, `..` bằng từ vựng | `path.normalize()` | Không cần tệp tồn tại |
| Đổi sang absolute | `path.toAbsolutePath()` | Không mặc định kiểm tra tệp tồn tại |
| Lấy đường dẫn thực | `path.toRealPath()` | Có truy cập hệ thống tệp; có thể ném `IOException` |
| Kiểm tra/đọc/ghi/tạo tệp | `Files.exists`, `Files.readAllBytes`, `Files.write`... | Có truy cập hệ thống tệp |
| Tạo thư mục | `Files.createDirectories(path)` | Có thay đổi hệ thống tệp |

Từ Java 7, tạo `Path` thông qua `Paths.get(...)` là cách tương thích với chủ đề NIO.2. `Path.of(...)` là convenience factory được bổ sung từ **Java 11**; nó cũng hoàn toàn phù hợp khi codebase chạy trên Java hiện đại. Đừng gọi `Path.of` là cú pháp đã có ngay trong Java 7 nếu project cần biên dịch `--release 7`.

### 1.1. Đường dẫn mang ngữ nghĩa của file-system provider

`Path` có thể thuộc hệ thống tệp mặc định hoặc một provider khác. Quy tắc root, ký tự phân cách, cách so sánh path, cách phân tích URI và những giới hạn cụ thể phụ thuộc provider.

Đặc biệt:

- Windows thường dùng ký tự `\` trong đường dẫn hiển thị; nhiều cách viết dùng `/` cũng được provider Windows hiểu trong ngữ cảnh nhất định.
- Linux/macOS theo filesystem mặc định thường dùng `/`.
- Windows có ký hiệu ổ đĩa và đường dẫn mạng UNC; Unix-like thường có root `/`.
- **Case sensitivity** là đặc tính của hệ thống tệp/provider và cấu hình thực tế, không nên tự giả định mọi hệ thống đều so tên theo cùng một cách.
- Tên file hợp lệ, ký tự cấm, độ dài và quyền truy cập cũng có thể khác.

**Khuyến nghị:** Khi muốn ghép các thành phần đường dẫn, dùng `Paths.get("reports", "2026", "summary.txt")` thay vì `"reports\\2026\\summary.txt"`. Đừng biến việc “code chạy trên Windows” thành lý do đưa ký tự `\` hardcoded vào mọi đoạn code đa nền tảng.

## 2. Relative và absolute: khái niệm, không phải phỏng đoán dựa vào dấu gạch

### 2.1. Đường dẫn tương đối

Ví dụ:

```text
config/app.properties
reports/2026/summary.txt
../shared/data.csv
./logs/current.log
```

Đây là các biểu diễn **minh họa trên hệ thống dùng dấu `/`**, không phải những vị trí tuyệt đối có ý nghĩa như nhau trên mọi máy.

Một đường dẫn tương đối chỉ có ý nghĩa đầy đủ khi có một **base**. Nếu working directory là `/srv/myapp` trên Linux, thì `config/app.properties` thường được diễn giải theo:

```text
/srv/myapp/config/app.properties
```

Nếu tiến trình chạy với working directory `/tmp`, cùng một relative path có thể trỏ tới:

```text
/tmp/config/app.properties
```

Không có thay đổi nào về tên tệp trong source code; thứ thay đổi là **ngữ cảnh thực thi**.

### 2.2. Đường dẫn tuyệt đối

Ví dụ theo môi trường:

```text
Linux/macOS: /var/app/config/app.properties
Windows:     C:\apps\myapp\config\app.properties
Windows UNC: \\server\share\reports\summary.txt
```

Những ví dụ trên chỉ minh họa cú pháp của từng loại hệ thống tệp. Chúng không phải đường dẫn có thể lấy dùng trực tiếp trên mọi máy.

Một absolute path có thể được hỏi bằng `isAbsolute()`. Dù là absolute, nó **không tự đảm bảo** tệp tồn tại, có thể truy cập hoặc không bị symlink chuyển hướng.

### 2.3. Cẩn thận với “root” trong Windows

Trên Windows, có nhiều kiểu biểu diễn không tương đương nhau: `C:\folder\file.txt`, `C:folder\file.txt` và `\folder\file.txt`. Các đường dẫn thiếu thông tin ổ đĩa hoặc cách đặt gốc có thể có ngữ nghĩa phụ thuộc drive/current directory và không nhất thiết được xem là fully absolute.

**Không viết hàm `isAbsolute` bằng cách kiểm tra ký tự đầu là `/` hoặc sự xuất hiện của `:`.** Hãy để `Path.isAbsolute()` và filesystem provider phân tích.

## 3. Chương trình A — Khảo sát những thành phần của một Path

Chương trình này cố ý **không in ra working directory thật** để stdout ổn định trên các máy khác nhau. Nó dùng một hàm in chuỗi với `/` chỉ cho mục đích trình bày kết quả; **không** sửa `Path` gốc.

### Tệp `PathFormsDemo.java`

```java
import java.nio.file.Path;
import java.nio.file.Paths;

public final class PathFormsDemo {
    private static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path relative = Paths.get("reports", "2026", "summary.txt");
        Path cwd = Paths.get("").toAbsolutePath().normalize();
        Path absolute = relative.toAbsolutePath().normalize();

        System.out.println("relative=" + portable(relative));
        System.out.println("relativeAbsolute=" + relative.isAbsolute());
        System.out.println("relativeRootNull=" + (relative.getRoot() == null));
        System.out.println("nameCount=" + relative.getNameCount());
        System.out.println("parent=" + portable(relative.getParent()));
        System.out.println("fileName=" + relative.getFileName());
        System.out.println("absoluteIsAbsolute=" + absolute.isAbsolute());
        System.out.println("absoluteEqualsResolvedCwd=" + absolute.equals(
                cwd.resolve(relative).normalize()));
        System.out.println("backToRelative=" + portable(cwd.relativize(absolute)));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 PathFormsDemo.java
java PathFormsDemo
```

**Stdout đã kiểm chứng trên hệ thống tệp mặc định của Windows:**

```text
relative=reports/2026/summary.txt
relativeAbsolute=false
relativeRootNull=true
nameCount=3
parent=reports/2026
fileName=summary.txt
absoluteIsAbsolute=true
absoluteEqualsResolvedCwd=true
backToRelative=reports/2026/summary.txt
```

### 3.1. Phân tích từng kết quả

- `Paths.get("reports", "2026", "summary.txt")` tạo **relative path** gồm ba thành phần tên.
- `isAbsolute() == false` vì nó chưa có root đầy đủ của hệ thống tệp mặc định.
- `relative.getRoot() == null`; relative path trong ví dụ không có root.
- `getNameCount() == 3` cho biết có ba thành phần `reports`, `2026` và `summary.txt`.
- `getParent()` là `reports/2026`, vẫn tương đối.
- `getFileName()` trả thành phần cuối `summary.txt`.
- `relative.toAbsolutePath().normalize()` tạo đường dẫn tuyệt đối theo ngữ cảnh mặc định, rồi loại bỏ các thành phần `.`, `..` từ vựng.
- `cwd.resolve(relative).normalize()` khớp với cách lấy absolute trong môi trường thử nghiệm.
- `cwd.relativize(absolute)` cho đường đi từ `cwd` đến `absolute`; vì `absolute` được dựng từ chính `cwd` và `relative`, kết quả trở về `reports/2026/summary.txt`.

**Điểm cần nhớ:** `relative.toAbsolutePath()` không “đi tìm summary.txt”. Nó đưa đường dẫn về dạng absolute. Tệp vẫn có thể chưa được tạo.

### 3.2. `getParent()` không phải luôn trả một đường dẫn

Ví dụ một `Path` chỉ có một tên như `Paths.get("file.txt")` có thể có `getParent() == null`. Với root `/`, `getFileName()` có thể là `null`. Nếu code nhận path bất kỳ từ người dùng, đừng gọi `getParent().resolve(...)` hoặc `getFileName().toString()` mà bỏ qua các trường hợp biên.

Ngoài ra, việc gọi `getFileName()` không xác minh thành phần cuối là “tệp”; nó có thể là tên thư mục, một mục chưa tồn tại hoặc phần cuối của một đường dẫn khác.

## 4. Thư mục làm việc: nền để hiểu relative path

**Working directory** là ngữ cảnh mà một chương trình được khởi chạy. Trong ứng dụng Java phổ biến, nó có thể được quan sát qua:

```java
String userDir = System.getProperty("user.dir");
Path cwd = Paths.get("").toAbsolutePath().normalize();
```

Đây là mảnh mã minh họa cần import `Path` và `Paths`. `user.dir` là system property thường mô tả working directory của JVM; giá trị được thiết lập lúc khởi chạy theo runtime/environment.

**Không nên coi việc sửa `System.setProperty("user.dir", "...")` khi chương trình đang chạy là phương thức portable để thay đổi working directory thực** của mọi API. File-system provider và native process working directory có thể có hành vi khác nhau; giải pháp đáng tin hơn là truyền một **base path tường minh** hoặc cấu hình working directory lúc launch.

### 4.1. Working directory không đồng nhất với vị trí mã nguồn

Một project có thể có cấu trúc:

```text
my-project/
  src/
    main/
      java/
      resources/
  config/
    app.properties
  build/
    classes/
```

Nếu chạy từ `my-project`, relative path `config/app.properties` có thể đúng. Nếu chạy từ `my-project/build` hoặc chạy JAR trong một service, cùng path có thể chỉ tới chỗ khác.

Không nên suy ra working directory từ:

- Thư mục của file `.java`.
- Thư mục chứa `.class`.
- Thư mục chứa JAR.
- Thư mục hiện hiển thị trong giao diện IDE.
- Thư mục root của Git repository.
- Vị trí `src/main/resources` trong cây source.

Chúng có thể vô tình trùng nhau trong một cách chạy, nhưng **không là một hợp đồng chung**.

### 4.2. IDE, test runner và container

Trong các môi trường khác nhau, cơ chế khởi chạy có thể chọn working directory khác nhau:

| Ngữ cảnh | Điều cần kiểm tra |
| --- | --- |
| Terminal | Bạn đang đứng tại thư mục nào trước khi gọi `java`? |
| IDE | Run configuration đặt working directory là gì? |
| Maven/Gradle test | Test task chạy với working directory nào? Có được cấu hình tường minh không? |
| Docker/container | `WORKDIR` và cách chạy entrypoint là gì? |
| System service | Service manager đặt working directory như thế nào? |
| Scheduled task | Scheduler khởi chạy process tại directory nào? |
| CI pipeline | Bước chạy code đang ở thư mục nào và có đổi `cwd` giữa các bước không? |

Không cần đoán nơi chạy. Hãy **in/log working directory để chẩn đoán** (tránh làm lộ đường dẫn nhạy cảm trong output công khai) và cấu hình base path rõ ràng khi phần mềm phụ thuộc vào vị trí tệp.

## 5. Chương trình B — Quan sát working directory mà không phụ thuộc máy

### Tệp `WorkingDirectoryDemo.java`

```java
import java.nio.file.Path;
import java.nio.file.Paths;

public final class WorkingDirectoryDemo {
    private static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path empty = Paths.get("").toAbsolutePath().normalize();
        Path dot = Paths.get(".").toAbsolutePath().normalize();
        Path config = Paths.get("config", "application.properties");
        Path expected = empty.resolve(config).normalize();

        System.out.println("dotMatchesEmpty=" + dot.equals(empty));
        System.out.println("userDirDefined=" +
                (System.getProperty("user.dir") != null));
        System.out.println("relative=" + portable(config));
        System.out.println("resolvedAgainstCwd=" +
                expected.equals(config.toAbsolutePath().normalize()));
        System.out.println("baseIsAbsolute=" + empty.isAbsolute());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 WorkingDirectoryDemo.java
java WorkingDirectoryDemo
```

**Stdout trên môi trường kiểm chứng:**

```text
dotMatchesEmpty=true
userDirDefined=true
relative=config/application.properties
resolvedAgainstCwd=true
baseIsAbsolute=true
```

### 5.1. Đọc các phép kiểm tra

- `Paths.get("")` và `Paths.get(".")` đều diễn đạt “đây” theo các dạng relative path; đưa chúng sang absolute rồi normalize cho cùng working directory trên môi trường thử.
- `user.dir` có giá trị; điều đó không có nghĩa đường dẫn chứa trong property phải được in ra ở bài học.
- `config/application.properties` vẫn là đường dẫn tương đối.
- `empty.resolve(config)` và `config.toAbsolutePath()` trỏ về cùng đường dẫn absolute theo working directory mặc định trong môi trường được thử.
- `empty.isAbsolute()` là true vì đã gọi `toAbsolutePath()`.

### 5.2. Kết quả có thể khác nếu môi trường đặc biệt

Trên một filesystem provider khác, khi chạy với launch configuration khác hoặc xử lý các root không bình thường, chuỗi đường dẫn cụ thể có thể khác. Điều quan trọng của bài là **quan hệ giữa relative path và base path**, không phải hardcode một đường dẫn đầy đủ trong expected output của test.

Với thư viện dùng được ở nhiều môi trường, truyền `Path baseDirectory` như tham số hoặc dependency cấu hình thường dễ kiểm tra hơn việc truy `user.dir` sâu trong mọi hàm.

## 6. Ghép đường dẫn: `resolve` không phải phép nối chuỗi tùy ý

`base.resolve(other)` nối một relative path vào base. Ví dụ:

```java
Path base = Paths.get("workspace");
Path report = base.resolve(Paths.get("reports", "monthly.csv"));
```

Đây là mảnh mã minh họa. Kết quả về mặt thành phần tương ứng `workspace/reports/monthly.csv`.

Nếu `other` **đã là absolute path**, `resolve` thường trả về chính `other` theo hợp đồng của default filesystem trong ví dụ. Điều này rất quan trọng khi nhận path từ người dùng: không thể mặc định rằng `base.resolve(userInput)` sẽ luôn giữ userInput “nằm bên trong base”.

**Đừng tự nối bằng chuỗi:** `base.toString() + "/" + fileName` dễ sai dấu phân cách, root, double separators hoặc xử lý absolute input. Các thao tác `Path` xử lý cấu trúc đường dẫn theo provider.

### 6.1. `resolveSibling` khác `resolve`

- `file.resolveSibling("other.txt")` tạo đường dẫn **cùng thư mục cha** với file.
- `dir.resolve("other.txt")` tạo một đường dẫn **nằm dưới dir**.

Ví dụ:

```text
path = workspace/exports/log.txt

path.resolveSibling("status.txt")
     = workspace/exports/status.txt

path.resolve("status.txt")
     = workspace/exports/log.txt/status.txt
```

Dòng thứ hai trong ví dụ là phép ghép **từ vựng**, không kiểm tra `log.txt` có thật là tệp không và không cần tệp tồn tại. Do đó, dùng `resolveSibling` khi muốn thay tên file cùng parent.

### 6.2. `normalize` loại bỏ những thành phần thừa bằng từ vựng

Ví dụ:

```text
workspace/reports/../exports/./log.txt
                          |
                          v
normalize()
                          |
                          v
workspace/exports/log.txt
```

Về từ vựng, `.` đại diện một mức hiện tại và `name/..` có thể bị rút gọn. **Nhưng việc rút gọn `..` không chứng minh những phần tử đã tồn tại trên hệ thống tệp** và có thể không tương đương ngữ nghĩa khi đường dẫn đi qua symbolic link. Vì vậy `normalize` không nên được giới thiệu như cách “giải tất cả symlink”.

### 6.3. `relativize` là phép tính từ một đường dẫn đến đường dẫn khác

`base.relativize(target)` tạo **relative path** để từ `base` đi đến `target` trong mô hình đường dẫn.

Ví dụ:

```text
base   = workspace
target = workspace/exports/log.txt
relative = exports/log.txt
```

Hai đường dẫn phải tương thích về loại và filesystem provider. Không trộn bừa một relative path với một absolute path: provider mặc định sẽ báo `IllegalArgumentException` cho trường hợp không phù hợp. Trên Windows, khác root/drive cũng có thể làm phép `relativize` không hợp lệ.

## 7. Chương trình C — `resolve`, `normalize`, `relativize`, `resolveSibling`

### Tệp `PathOperationsDemo.java`

```java
import java.nio.file.Path;
import java.nio.file.Paths;

public final class PathOperationsDemo {
    private static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path base = Paths.get("workspace");
        Path raw = base.resolve(Paths.get(
                "reports", "..", "exports", ".", "log.txt"));
        Path normalized = raw.normalize();

        System.out.println("normalized=" + portable(normalized));
        System.out.println("parent=" + portable(normalized.getParent()));
        System.out.println("sibling=" +
                portable(normalized.resolveSibling("status.txt")));
        System.out.println("relativeFromBase=" +
                portable(base.relativize(normalized)));
        System.out.println("normalizeWithoutDisk=" +
                portable(Paths.get("data", "..", "report.txt").normalize()));

        Path absoluteOther = Paths.get("").toAbsolutePath().normalize()
                .resolve("other.txt");
        System.out.println("resolveAbsoluteOverridesBase=" +
                base.toAbsolutePath().normalize()
                        .resolve(absoluteOther).equals(absoluteOther));
        try {
            base.relativize(absoluteOther);
            System.out.println("mixedTypes=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println("mixedTypes=IllegalArgumentException");
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PathOperationsDemo.java
java PathOperationsDemo
```

**Stdout đúng trên filesystem mặc định đã thử:**

```text
normalized=workspace/exports/log.txt
parent=workspace/exports
sibling=workspace/exports/status.txt
relativeFromBase=exports/log.txt
normalizeWithoutDisk=report.txt
resolveAbsoluteOverridesBase=true
mixedTypes=IllegalArgumentException
```

### 7.1. Phân tích hai ca dễ nhầm

**Trường hợp `resolveAbsoluteOverridesBase=true`:** Khi `other` là absolute, gọi `base.resolve(other)` không buộc kết quả nằm trong `base`. Nếu `other` đến từ input chưa được tin cậy và code dự định ghi file trong một thư mục giới hạn, đây là điểm phải kiểm tra.

**Trường hợp `mixedTypes=IllegalArgumentException`:** `base` là relative (`workspace`), còn `absoluteOther` là absolute. `relativize` yêu cầu hai đường dẫn tương thích; lời gọi với cặp này bị từ chối. Khi có nhu cầu hợp lệ, chuyển cả hai về một hệ tọa độ thống nhất **theo cùng một filesystem**, rồi xét đến root.

### 7.2. Thao tác từ vựng không tạo file

Sau khi `normalizeWithoutDisk=report.txt` được in, chương trình không hề tạo `report.txt`. Tương tự, `resolveSibling` không rename hay move file. Muốn thực hiện thao tác thật:

- Tạo thư mục: `Files.createDirectories(path)`.
- Tạo/ghi file: `Files.write(...)` hoặc `Files.newBufferedWriter(...)`.
- Di chuyển: `Files.move(source, target, ...)`.
- Xóa: `Files.delete(...)` hoặc `Files.deleteIfExists(...)`.

Không trộn “tạo một Path trông đúng” với “đã tạo tài nguyên trên đĩa”.

## 8. `toAbsolutePath()`, `normalize()` và `toRealPath()`: ba phép khác nhau

Một nguồn lỗi lớn là coi cả ba phương thức như “canonicalize”, trong khi tác dụng và điều kiện khác nhau.

| Phương thức | Mục đích chính | Có yêu cầu tệp tồn tại? | Có thực sự theo symbolic link? |
| --- | --- | --- | --- |
| `toAbsolutePath()` | Chuyển đường dẫn sang dạng absolute theo filesystem/working directory | Không | Không tự thực hiện link resolution như `toRealPath` |
| `normalize()` | Loại thành phần `.` và `..` bằng từ vựng | Không | Không tìm đích của symbolic link |
| `toRealPath()` | Lấy đường dẫn thực của một mục đang tồn tại, mặc định giải symbolic links | Thông thường có | Mặc định có; có tùy chọn `NOFOLLOW_LINKS` |

### 8.1. `toAbsolutePath()` không xác minh vật lý

`Paths.get("missing.txt").toAbsolutePath()` vẫn có thể trả một absolute path hợp lệ dù `missing.txt` chưa được tạo. Nếu bạn cần đọc tệp, bản thân bước chuyển sang absolute không đảm bảo `Files.readAllBytes(...)` sẽ thành công.

### 8.2. `normalize()` không phải kiểm tra an toàn tệp

Giả sử:

```text
base/link/../report.txt
```

Nếu `link` là symbolic link đến nơi khác, việc loại bỏ `link/..` thuần từ vựng có thể thay đổi ý nghĩa truy cập so với từng bước theo filesystem. Vì thế `normalize` là công cụ xử lý **thành phần đường dẫn**, không phải phép xác thực security boundary cho mọi filesystem object.

### 8.3. `toRealPath()` truy cập hệ thống tệp

`toRealPath()` thường trả đường dẫn absolute thực và có thể ném `IOException` nếu tệp không tồn tại hoặc không truy cập được. Mặc định, nó theo symbolic links theo hợp đồng API; có thể chỉ định `LinkOption.NOFOLLOW_LINKS` nếu cần hành vi khác.

Đây là phép hữu ích khi **mục hiện hữu** và bạn cần xác định nơi nó thực sự trỏ tới. Tuy nhiên, ngay cả khi kiểm tra `toRealPath()` rồi mới mở tệp, có thể tồn tại **time-of-check/time-of-use race** nếu nội dung thư mục hoặc symlink được thay đổi giữa hai thao tác. Không xem `toRealPath` như phương thuốc duy nhất chống tấn công đường dẫn.

## 9. Chương trình D — Path có thật và không có thật

Để kết quả độc lập vị trí project, ví dụ tạo một thư mục tạm bằng `Files.createTempDirectory`, tạo tệp bên trong, quan sát các phép biến đổi rồi **xóa đúng những gì đã tạo** ở `finally`.

### Tệp `RealPathDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class RealPathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("path-real-demo-");
        Path dir = root.resolve("docs");
        Path file = dir.resolve("notes.txt");
        try {
            Files.createDirectories(dir);
            Files.writeString(file, "hello", StandardCharsets.UTF_8);
            Path lexical = root.resolve("docs").resolve("..")
                    .resolve("docs").resolve("notes.txt");
            System.out.println("created=" + Files.exists(file));
            System.out.println("lexicalMatches=" +
                    lexical.normalize().equals(file));
            System.out.println("realIsAbsolute=" +
                    lexical.toRealPath().isAbsolute());
            System.out.println("realExists=" +
                    Files.exists(lexical.toRealPath()));
            Path missing = root.resolve("missing.txt");
            System.out.println("missingAbsolute=" +
                    missing.toAbsolutePath().isAbsolute());
            try {
                missing.toRealPath();
                System.out.println("missingReal=unexpected");
            } catch (NoSuchFileException ex) {
                System.out.println("missingReal=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RealPathDemo.java
java RealPathDemo
```

**Stdout trên Windows/JDK đã kiểm chứng:**

```text
created=true
lexicalMatches=true
realIsAbsolute=true
realExists=true
missingAbsolute=true
missingReal=NoSuchFileException
```

### 9.1. Những điều chương trình xác nhận

1. `Files.createTempDirectory(...)` tạo một thư mục thực, không phải chỉ một `Path`.
2. `Files.createDirectories(dir)` thực sự tạo thư mục `docs`.
3. `Files.writeString(file,...)` tạo và ghi một tệp trong thư mục đó.
4. `lexical.normalize()` loại bỏ `docs/..` theo từ vựng, cho đường dẫn tương ứng `file`.
5. `lexical.toRealPath()` thành công vì tệp đã tồn tại, và kết quả là absolute path.
6. `missing.toAbsolutePath()` trả absolute path dù tệp `missing.txt` chưa tồn tại.
7. `missing.toRealPath()` ném `NoSuchFileException` ở môi trường được thử.
8. `finally` xóa tệp và các thư mục tạm theo đúng thứ tự từ bên trong ra ngoài.

### 9.2. Tài nguyên của ví dụ và tính tương thích

`Files.writeString` xuất hiện từ **Java 11**. Đây là API hiện đại hợp lệ khi biên dịch/chạy `--release 17`, nhưng **không phải phương thức có từ Java 7**. Nếu codebase buộc tương thích với Java 7, dùng `Files.write(file, bytes)` kết hợp `StandardCharsets.UTF_8` theo chữ ký đã có trên Java 7.

`Files.exists(path)` có ích để hỏi trạng thái quan sát được, nhưng không phải bảo đảm tệp vẫn tồn tại khi thao tác tiếp theo. Với quyền truy cập không đủ hoặc I/O không thể xác minh, `Files.exists` có thể trả `false` mà không có nghĩa chắc chắn không tồn tại. Đồng thời `Files.notExists` cũng không luôn là phủ định của `Files.exists` khi trạng thái không xác định.

**Trong ứng dụng thật**, thường nên thực hiện I/O cần thiết và xử lý exception thay vì liên tục `exists` rồi mới `open`, vì trạng thái filesystem có thể thay đổi giữa hai thao tác.

## 10. Đường dẫn tương đối trong ứng dụng: truyền base rõ ràng

Khi một hàm nghiệp vụ cần đọc tệp cấu hình, có hai mô hình thiết kế:

### 10.1. Mô hình phụ thuộc working directory

```java
Path config = Paths.get("config", "app.properties");
byte[] data = Files.readAllBytes(config);
```

Đây là mảnh mã minh họa, cần import `Path`, `Paths`, `Files` và xử lý `IOException`. Đường dẫn tương đối được diễn giải trong ngữ cảnh filesystem mặc định. Nó có thể đúng khi bạn chạy từ thư mục project và sai khi chạy JAR từ nơi khác.

Mô hình này vẫn phù hợp **nếu working directory là một phần contract triển khai** và được cấu hình rõ ràng. Không có quy tắc “relative path luôn sai”; vấn đề là **phụ thuộc một base không được định nghĩa**.

### 10.2. Mô hình truyền base directory

```java
static Path configFile(Path baseDirectory) {
    return baseDirectory.toAbsolutePath().normalize()
            .resolve(Paths.get("config", "app.properties"));
}
```

Đây là **phương thức minh họa** đặt trong một lớp có import `Path` và `Paths`. Nếu caller truyền `baseDirectory` từ cấu hình ứng dụng hoặc tùy chọn CLI, đường dẫn đích phụ thuộc vào **một tham số được chỉ định**, dễ test hơn.

Có thể cần gọi `normalize()` sau `resolve(...)` nếu các phần nối đến từ input có `.` hoặc `..`. Nếu base là một path không tồn tại, phép ghép vẫn tạo đối tượng `Path`; thao tác đọc có thể lỗi sau đó.

**Quan trọng:** Với đường dẫn do người dùng gửi từ bên ngoài, chỉ `normalize`/`startsWith` chưa đủ làm bảo vệ cuối cùng trước symlink và race; đọc phần an toàn bên dưới.

### 10.3. Cấu hình đường dẫn có thể được lấy từ đâu?

- Tham số CLI như `--config-dir ...`.
- Biến môi trường có hợp đồng rõ.
- Cấu hình deploy/container.
- Thư mục dữ liệu theo quy định của hệ điều hành hoặc tổ chức.
- Tham số truyền vào constructor/service.
- Working directory được service manager đặt rõ ràng.

Đừng lấy mặc định “đường dẫn tương đối là tương đối với classpath” — đó là hai hệ quy chiếu khác nhau.

## 11. File trên filesystem khác resource trong classpath

Đây là nguồn lỗi thực tế: lúc phát triển, bạn thấy một tệp dưới `src/main/resources` và viết:

```java
Path config = Paths.get("src", "main", "resources", "config.json");
```

Đây là mảnh minh họa. Nó chỉ biểu diễn **một filesystem path tương đối**. Khi package ứng dụng thành JAR và chạy nơi khác, source tree `src/main/resources` có thể không hề tồn tại. Tệp có thể đã được **đóng gói vào JAR** và không còn có đường dẫn vật lý thông thường như lúc phát triển.

Nếu dữ liệu là resource đi theo ứng dụng, có thể dùng classloader:

```java
try (InputStream input =
        Example.class.getResourceAsStream("/config.json")) {
    if (input == null) {
        throw new IllegalStateException("Missing resource: /config.json");
    }
    // Đọc nội dung từ stream theo contract.
}
```

Đây là **mảnh minh họa**, cần một lớp `Example`, import `java.io.InputStream` và xử lý checked exceptions khi thao tác đọc. `getResourceAsStream` tìm resource theo cơ chế class/resource loading, **khác với** `Paths.get("config.json")` dùng filesystem working directory. Không phải mọi classpath resource nằm trong JAR đều chuyển trực tiếp thành `Path` của filesystem mặc định.

Nếu resource là **file cấu hình phải sửa được khi triển khai**, nó thường nên nằm trên filesystem ngoài JAR và được chọn bằng path/base do deployment cung cấp, thay vì ghi vào resource đóng gói.

## 12. Tính di động: Path components, separators và root

Với code cần chạy trên Windows và Unix-like, tránh hardcode cách viết:

```java
String bad = "reports\\2026\\summary.txt"; // Windows-oriented.
Path good = Paths.get("reports", "2026", "summary.txt");
```

Đây là đoạn minh họa. Dấu `\` không phải dấu phân cách tên thư mục trên mọi filesystem. Khi dùng `Paths.get` với nhiều thành phần, provider chịu trách nhiệm ghép cho phù hợp.

### 12.1. Đừng sửa `Path` bằng replace để thực hiện I/O

Trong các chương trình demo, hàm:

```java
private static String portable(Path path) {
    return path.toString().replace('\\', '/');
}
```

chỉ dùng để **in stdout dễ so giữa các hệ thống**. Nó không phải codec filesystem hay phép chuyển một path Windows thành path hợp lệ cho Linux. Không lấy kết quả `portable(path)` rồi cho rằng mọi hệ thống đều mở được file đó, đặc biệt nếu có drive, UNC, escaping hoặc ký tự tên không tương thích.

Để chuyển một `Path` cho API cần path, **giữ nguyên đối tượng `Path`**. Khi cần truyền một vị trí file qua một giao thức, xác định URI hoặc format truyền tải phù hợp.

### 12.2. Absolute path không phải lúc nào cũng có cùng root

`Path.getRoot()` có thể trả `null` cho relative path, còn với absolute path thường biểu diễn root theo provider. Trên Windows, drive path và UNC có root khác; trên Linux mặc định có root `/`.

Đừng tự giả định toàn bộ absolute paths trong ứng dụng luôn thuộc cùng một drive/filesystem để `relativize` thành công. Nếu yêu cầu chia sẻ file giữa các máy, một absolute path của máy A không tự có ý nghĩa trên máy B.

### 12.3. Case sensitivity là vấn đề của filesystem

`"Readme.txt"` và `"README.txt"` có thể được coi là cùng một tệp trên một filesystem nhưng là hai tên khác nhau ở filesystem khác. Không ép `toLowerCase()`/`toUpperCase()` đường dẫn để “chuẩn hóa cross-platform” mà không hiểu semantics. Điều này có thể làm sai tên file hợp lệ, gây collision hoặc vi phạm phân quyền.

## 13. Chương trình E — `Path` và file URI

Một file URI có cấu trúc khác với chuỗi filesystem path. Khi cần chuyển đổi cho filesystem mặc định, dùng API `Path.toUri()` và `Paths.get(URI)` thay vì tự nối `"file://"` với đường dẫn theo cách thử-sai.

### Tệp `FileUriDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public final class FileUriDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("path-uri-demo-", ".txt");
        try {
            System.out.println("uriScheme=" + file.toUri().getScheme());
            Path restored = Paths.get(file.toUri());
            System.out.println("uriRoundTrip=" +
                    file.toAbsolutePath().normalize().equals(
                            restored.toAbsolutePath().normalize()));
            System.out.println("fileNameSuffix=" +
                    restored.getFileName().toString().endsWith(".txt"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 FileUriDemo.java
java FileUriDemo
```

**Stdout:**

```text
uriScheme=file
uriRoundTrip=true
fileNameSuffix=true
```

### 13.1. Khi nào `file:` URI hữu ích?

Một `file:` URI là cách biểu diễn vị trí tệp theo cú pháp URI. Nó có thể percent-encode ký tự đặc biệt như dấu cách. Khi một API yêu cầu `URI`, nên đưa `path.toUri()`, không sửa chuỗi bằng tay.

**Không nhầm:** `Paths.get("file:///tmp/a.txt")` với `Paths.get(URI.create("file:///tmp/a.txt"))`. Overload nhận `String` phân tích như **đường dẫn theo filesystem**, trong khi overload nhận `URI` diễn giải URI theo provider. Việc dùng sai overload có thể cho một path khác hoặc ném lỗi.

Không giả định mọi URI scheme đều là filesystem mặc định. Các scheme khác có thể cần provider tương ứng; một số provider có ràng buộc riêng và không phải mọi scheme đều có thể đi qua `Paths.get(URI)`.

## 14. An toàn đường dẫn: `..`, absolute input và giới hạn base directory

Giả sử ứng dụng chỉ cho người dùng tải file trong một thư mục `sandbox`. Một cám dỗ phổ biến là:

```java
Path candidate = sandbox.resolve(userInput);
```

Đây là mảnh minh họa với biến `sandbox`/`userInput`. Nếu `userInput` là absolute, `resolve` có thể chọn hẳn path ngoài sandbox. Nếu `userInput` có `..`, kết quả có thể đi ra ngoài sau `normalize()`. Ngoài ra, symbolic link bên trong sandbox có thể trỏ ra ngoài, nên kiểm tra cú pháp path không đủ để bảo đảm containment.

### 14.1. Kiểm tra từ vựng cơ bản (chưa phải security boundary hoàn chỉnh)

Với đường dẫn từ một hệ thống tệp mặc định:

```java
Path base = Paths.get("storage").toAbsolutePath().normalize();
Path request = Paths.get("reports", "data.csv");

if (request.isAbsolute()) {
    throw new IllegalArgumentException("Absolute input not accepted");
}
Path candidate = base.resolve(request).normalize();
if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Path leaves base");
}
```

Đây là **mảnh minh họa**, không phải chương trình độc lập. Kiểm tra trên có thể ngăn những trường hợp path traversal thuần từ vựng **trước khi thao tác I/O**. Nhưng không đủ cho một hệ thống bảo mật cao:

- `startsWith(Path)` so theo thành phần path (theo provider); đừng thay bằng `candidate.toString().startsWith(base.toString())` vì `sandbox_evil` có thể qua một phép kiểm tra tiền tố chuỗi `sandbox`.
- Symbolic links/reparse points có thể làm một path trông “nằm trong base” nhưng trỏ sang vị trí khác.
- File hoặc symlink có thể thay đổi sau khi kiểm tra, trước khi mở (TOCTOU).
- Các lựa chọn permission, mount, filesystem provider, archive và container boundary cần được xét riêng.
- Một `Path.normalize` không phải giải pháp xác minh filesystem object cuối cùng.

Đối với hệ thống xử lý input không tin cậy, nên dựa trên một kiến trúc filesystem sandbox và API access phù hợp (trong môi trường hỗ trợ, cân nhắc các thao tác directory-relative an toàn như `SecureDirectoryStream`), kết hợp quyền hệ điều hành và chính sách chống symlink/race, thay vì chỉ dùng kiểm tra string.

### 14.2. Chương trình F — Phát hiện một số trường hợp lexical escape

### Tệp `SafeResolveDemo.java`

```java
import java.nio.file.Path;
import java.nio.file.Paths;

public final class SafeResolveDemo {
    private static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path base = Paths.get("").toAbsolutePath()
                .normalize().resolve("sandbox");
        Path good = Paths.get("reports", "report.txt");
        Path bad = Paths.get("..", "outside.txt");
        Path candidate = base.resolve(good).normalize();

        System.out.println("goodInside=" + candidate.startsWith(base));
        System.out.println("goodRelative=" +
                portable(base.relativize(candidate)));
        System.out.println("escapeInside=" +
                base.resolve(bad).normalize().startsWith(base));
        Path absoluteInput = base.getRoot()
                .resolve("absolute-outside.txt");
        System.out.println("absoluteOverrides=" +
                base.resolve(absoluteInput).equals(absoluteInput));
        System.out.println("pathPrefixFalse=" +
                Paths.get("sandbox_evil", "file.txt")
                        .startsWith(Paths.get("sandbox")));
        System.out.println("stringPrefixTrue=" +
                "sandbox_evil/file.txt".startsWith("sandbox"));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SafeResolveDemo.java
java SafeResolveDemo
```

**Stdout đã kiểm chứng:**

```text
goodInside=true
goodRelative=reports/report.txt
escapeInside=false
absoluteOverrides=true
pathPrefixFalse=false
stringPrefixTrue=true
```

### 14.3. Điều được và chưa được chứng minh

- `goodInside=true`: nối một relative child bình thường rồi normalize vẫn ở trong base theo thành phần path.
- `escapeInside=false`: `../outside.txt` có thể thoát base theo từ vựng.
- `absoluteOverrides=true`: absolute input có thể bỏ qua base trong `resolve`.
- `pathPrefixFalse=false`: `Path.startsWith` không nhầm một thành phần `sandbox_evil` thành `sandbox`.
- `stringPrefixTrue=true`: phép so tiền tố chuỗi dễ mắc lỗi đó.

**Không tuyên bố:** chương trình này đã chống mọi path traversal. Nó chỉ là bài học để **phân biệt cách thao tác path đúng** với “bảo vệ filesystem hoàn chỉnh”. Để xử lý file thực của người dùng, cần thêm các biện pháp dựa trên filesystem và quyền truy cập.

## 15. Khi nào dùng `toRealPath` để xác minh vị trí file?

Với file **đã tồn tại**, `path.toRealPath()` có thể giúp bạn kiểm tra một đường dẫn sau khi provider giải symlink mặc định. Ví dụ, khi thao tác trên thư mục chứa các file đã mở ổn định trong môi trường tin cậy, bạn có thể quan sát real path để log/so sánh.

Tuy nhiên:

1. `toRealPath()` có thể ném `IOException` khi thiếu quyền hoặc file không tồn tại.
2. Nếu mục tiêu là **tạo tệp mới**, phần file đích chưa tồn tại nên không thể gọi `target.toRealPath()` rồi mong thành công; có thể cần xử lý real path của thư mục cha đã tồn tại và dùng I/O an toàn.
3. Kiểm tra real path rồi mở file bằng một thao tác khác vẫn có race nếu attacker có thể thay đổi symlink hoặc directory entries.
4. `LinkOption.NOFOLLOW_LINKS` thay đổi cách xử lý symlink theo hợp đồng provider; không phải một cờ “bật bảo mật tự động” cho mọi thao tác.
5. Đường dẫn có thể nằm trên provider khác, filesystem mount hoặc share với quy tắc riêng.

Trong hệ thống có yêu cầu an toàn cao, cân nhắc **giữ directory handle** rồi thực hiện các thao tác tương đối trên handle theo API/provider hỗ trợ, hoặc tách quyền truy cập ở cấp hệ điều hành/container. Tránh đưa ra bảo đảm an ninh chỉ từ một so sánh `startsWith`.

## 16. Những lỗi phổ biến trong code thật

### 16.1. Nghĩ relative path tính từ nơi đặt file `.java`

Vấn đề: code chạy từ IDE một cách tình cờ rồi báo thiếu file ở production. Đường dẫn tương đối thường được xét theo working directory của process, không theo file source.

Cách sửa: xác định/thiết lập working directory hoặc truyền base rõ ràng; với resource đóng gói, dùng cơ chế classpath resource phù hợp.

### 16.2. Nghĩ `toAbsolutePath` đồng nghĩa file tồn tại

Vấn đề: gọi `toAbsolutePath` thành công nhưng `Files.readAllBytes` vẫn lỗi.

Cách sửa: hiểu `toAbsolutePath` là phép biểu diễn đường dẫn; I/O thật cần kiểm tra/exception handling độc lập.

### 16.3. Dùng `normalize` để “xử lý tất cả symlink”

Vấn đề: `normalize` không đọc filesystem; `name/..` có thể mang ý nghĩa khác khi có symlink.

Cách sửa: khi cần thực tế, hiểu `toRealPath` và các ràng buộc race/security. Đừng đánh đồng lexical path với real path.

### 16.4. Dùng dấu phân cách cố định từ Windows trong code đa nền tảng

Vấn đề: `"dir\\file.txt"` có thể là một tên file có dấu `\` trên môi trường khác thay vì hai thành phần.

Cách sửa: `Paths.get("dir", "file.txt")` hoặc `base.resolve("file.txt")`.

### 16.5. Truyền absolute user input vào `resolve` mà không kiểm tra

Vấn đề: có thể tạo path nằm ngoài thư mục dự kiến.

Cách sửa: đặt contract rõ cho loại input được chấp nhận; từ chối absolute path nếu chỉ cho relative child; dùng xác minh filesystem/permission phù hợp.

### 16.6. So chuỗi đường dẫn bằng `startsWith`

Vấn đề: `"sandbox_evil"` có tiền tố text `"sandbox"` nhưng không nằm trong thư mục `sandbox`.

Cách sửa: dùng cấu trúc `Path` khi kiểm tra lexical containment, cùng với các biện pháp bổ sung cho symlink và race.

### 16.7. Dùng `getParent()` mà quên `null`

Vấn đề: một relative path có đúng một tên hoặc root có thể không có parent theo cách code mong đợi.

Cách sửa: kiểm tra `null`, xác định hợp đồng của loại path đầu vào.

### 16.8. Dùng `relativize` giữa absolute và relative

Vấn đề: `IllegalArgumentException` khi các path không cùng loại hoặc không tương thích provider/root.

Cách sửa: quyết định cùng một base/filesystem, normalize/absolute khi cần và xử lý trường hợp các root khác nhau.

### 16.9. Lấy `user.dir` bằng cách sửa system property ở runtime

Vấn đề: property có thể không thay đổi working directory vật lý và không bảo đảm tất cả API nhất quán.

Cách sửa: cấu hình process khi launch hoặc truyền `Path baseDirectory` vào các lớp/hàm.

### 16.10. Tin rằng `Files.exists` luôn là câu trả lời chắc chắn

Vấn đề: quyền truy cập hoặc lỗi I/O có thể làm trạng thái không xác minh được. Sau phép kiểm tra, file cũng có thể bị đổi/xóa trước khi dùng.

Cách sửa: mở/đọc/ghi và xử lý exception thích hợp; không dựa vào chuỗi check-then-use như một cơ chế đảm bảo.

### 16.11. Đưa path filesystem vào cùng ô với URL

Vấn đề: `C:\data\report.txt` không phải URL; `file:///...` là URI có cú pháp và escaping riêng.

Cách sửa: dùng `path.toUri()`/`Paths.get(URI)` khi API cần URI; dùng `Path` cho filesystem operations.

### 16.12. Đóng gói resource vào JAR nhưng vẫn đọc `src/main/resources`

Vấn đề: source tree không nhất thiết tồn tại khi deploy.

Cách sửa: dùng classpath resource cho dữ liệu đóng gói hoặc external config path cho file cấu hình runtime.

### 16.13. Hardcode absolute path của máy phát triển

Vấn đề: `C:\Users\Alice\project\...` hoặc `/home/alice/...` không có ý nghĩa trên môi trường khác và có thể làm lộ thông tin nội bộ.

Cách sửa: cấu hình base/path theo môi trường, không commit đường dẫn cá nhân vào source.

### 16.14. Coi chuỗi path và file identity là một

Hai `Path` có thể chỉ cùng file qua đường khác nhau, symlink hoặc hard link. Ngược lại, path được resolve không có nghĩa file tồn tại. Nếu cần xác định cùng file thực, cân nhắc `Files.isSameFile` theo contract và xử lý `IOException`, chứ không chỉ so `toString()`.

## 17. Ma trận kiểm thử nên có

| Trường hợp | Hành động | Kỳ vọng |
| --- | --- | --- |
| Relative ba thành phần | `Paths.get("reports","2026","summary.txt")` | `isAbsolute=false`, `getNameCount=3` |
| Absolute từ relative | `relative.toAbsolutePath()` | Absolute path, không bắt buộc file tồn tại |
| Resolve theo CWD | `cwd.resolve(relative)` | Cùng location với relative được diễn giải theo CWD |
| Normalize | `workspace/reports/../exports/./log.txt` | `workspace/exports/log.txt` (lexical) |
| Resolve sibling | `workspace/exports/log.txt` → `status.txt` | `workspace/exports/status.txt` |
| Relativize | Base `workspace` → target `workspace/exports/log.txt` | `exports/log.txt` |
| Mix relative và absolute | `relative.relativize(absolute)` | Thông thường bị từ chối |
| Absolute input với resolve | `base.resolve(absoluteOther)` | Có thể trả absoluteOther |
| Missing file | `missing.toAbsolutePath()` | Vẫn trả absolute |
| Missing file real path | `missing.toRealPath()` | Ném lỗi I/O, trong test là `NoSuchFileException` |
| Tạo file thật | `Files.createDirectories` + `Files.writeString` | File tồn tại trong thư mục tạm |
| Trả về file URI | `file.toUri()` | Scheme `file` |
| Decode URI trở lại Path | `Paths.get(file.toUri())` | Path tương ứng trên provider hỗ trợ |
| Traversal lexical | `base.resolve("../outside").normalize()` | Có thể không `startsWith(base)` |
| String prefix sai | `"sandbox_evil".startsWith("sandbox")` | `true` nhưng không chứng minh containment |
| Symlink/race | Resolve/normalize rồi I/O với path bị thay đổi | Cần giải pháp filesystem-security, không chỉ lexical check |

### 17.1. Viết test không hardcode working directory

Không kiểm thử bằng cách mong `toAbsolutePath().toString()` đúng một chuỗi cố định của laptop. Thay vào đó:

- Tạo một **thư mục tạm** bằng `Files.createTempDirectory`.
- Ghi những tệp thử cần thiết vào thư mục đó.
- Đặt `base` của bộ test chính là thư mục tạm.
- Dùng `base.resolve(...)` và assert quan hệ path/file.
- Dọn dẹp file/dir theo thứ tự hợp lệ.
- Tránh test tự do ghi vào working directory hiện tại vì có thể gây xung đột với môi trường CI.

Với test về relative/absolute, assert các thuộc tính `isAbsolute`, `relativize` hoặc kết quả `Files.exists` của file test đã tạo thay vì một đường dẫn thiết bị cụ thể.

### 17.2. Test thêm các trường hợp “không đẹp”

- Relative path rỗng hoặc `"."`.
- Path có `".."` và `"."`.
- Một path chỉ có root hoặc chỉ một tên, dẫn tới parent/fileName có thể null.
- Absolute input được nối vào base.
- Hai đường dẫn khác root trên Windows.
- Ký tự tên không hợp lệ theo OS/provider.
- Tên file có khoảng trắng/Unicode (khi filesystem và locale hỗ trợ).
- Permission denied hoặc file bị xóa giữa các thao tác.
- Symlink trong thư mục được dùng làm base, nếu hệ thống cho phép test.
- Classpath resource trong JAR, không chỉ source tree.
- Các điều kiện bảo mật nếu nhận filename từ nguồn chưa tin cậy.

## 18. Các câu hỏi tự luyện

**Bài 1 — Phân loại:** Cho `"logs/app.log"`, `"/var/log/app.log"` và `"C:\\app\\logs\\app.log"`. Trên mỗi filesystem phù hợp, loại nào là absolute? Vì sao không nên dùng `string.startsWith("/")` làm phép kiểm tra tổng quát?

**Bài 2 — Working directory:** Ứng dụng đọc `Paths.get("config", "db.properties")`. Khi chạy với CWD khác, nó sẽ tìm đâu? Đề xuất một contract CLI để không phụ thuộc CWD ngầm.

**Bài 3 — Resolve:** Base `workspace`, child `reports/2026/data.csv`. Dự đoán kết quả `resolve`. Nếu child trở thành absolute path, điều gì thay đổi?

**Bài 4 — Normalize:** Cho `work/tmp/../reports/./final.txt`. Tính `normalize` bằng tay. Liệu thao tác này đã chứng minh tệp tồn tại chưa?

**Bài 5 — Relativize:** Tính `workspace.relativize(workspace/exports/log.txt)`. Thử `relative.relativize(absolute)` và kiểm tra exception.

**Bài 6 — Parent/fileName:** Cho `reports/2026/summary.txt`, hãy dự đoán `getParent` và `getFileName`. Trường hợp `Paths.get("summary.txt")` có parent thế nào?

**Bài 7 — Real path:** Tạo thư mục tạm, tệp `docs/notes.txt`; so `toAbsolutePath`, `normalize` và `toRealPath`. Sau khi xóa tệp, phương thức nào vẫn có thể tạo absolute path và phương thức nào có thể ném `IOException`?

**Bài 8 — IDE vs JAR:** Một file nằm ở `src/main/resources/config.json` và code đang đọc bằng `Paths.get(...)`. Khi package JAR, có điều gì có thể sai? Khi nào dùng `getResourceAsStream` thay vì filesystem path?

**Bài 9 — URI:** Dùng `file.toUri()` và `Paths.get(URI)` để round-trip trên một tệp tạm. Vì sao tự ghép chuỗi `"file://" + path` không phải cách tổng quát?

**Bài 10 — Path traversal:** Một downloader ghép `base.resolve(userInput)`. Kiểm tra ba input: `images/pic.png`, `../secret.txt` và một absolute path. Đề xuất các bước lexical validation và phần cần giải quyết bằng filesystem access control.

**Bài 11 — Prefix trap:** Tại sao so chuỗi `"/var/app-evil".startsWith("/var/app")` nguy hiểm? `Path.startsWith` cải thiện điều gì? Nó còn thiếu gì khi tồn tại symlink?

**Bài 12 — Test portability:** Chuyển một test phụ thuộc `C:\Users\...` thành test dùng `Files.createTempDirectory` và biến `base` tường minh.

**Bài 13 — Symlink:** Hãy giải thích vì sao `normalize` có thể không biểu diễn chính xác kết quả của một đường dẫn có thành phần symbolic link. Khi nào `toRealPath` có ích và tại sao vẫn phải chú ý race?

**Bài 14 — Contract:** Thiết kế một API `load(Path base, Path relativeName)` có precondition rõ. Nó có nhận absolute `relativeName` không? Nó xử lý missing file, permission, symlink, size limit ra sao?

## 19. Checklist khi áp dụng vào dự án

- [ ] Biết path đang là relative hay absolute và đang thuộc filesystem provider nào.
- [ ] Không nhầm working directory với source/project/JAR directory.
- [ ] Đã xác định base rõ ràng ở biên ứng dụng; log/debug CWD chỉ khi cần.
- [ ] Dùng `Paths.get(parts...)` hoặc `Path.resolve` thay vì tự nối dấu phân cách.
- [ ] Phân biệt `resolve` (ghép), `resolveSibling` (cùng parent), `relativize` (tính đường đi) và `normalize` (rút gọn lexical).
- [ ] Không gọi `relativize` giữa path không tương thích kiểu/root.
- [ ] Không coi `toAbsolutePath` là tồn tại hoặc xác minh vật lý.
- [ ] Dùng `toRealPath` khi cần thông tin của file hiện hữu, và xử lý `IOException`.
- [ ] Không dùng `normalize`/`startsWith` như giải pháp duy nhất chống path traversal.
- [ ] Nhận absolute input và `..` như tình huống cần xác định contract rõ.
- [ ] Không trộn classpath resource với filesystem path.
- [ ] Không giả định separator, drive hoặc case sensitivity giống nhau trên mọi máy.
- [ ] Không hardcode absolute path cá nhân vào mã nguồn.
- [ ] Có test tệp tạm và không phụ thuộc cấu hình IDE.
- [ ] Nếu dữ liệu đến từ người dùng, có kiểm tra filesystem-level security, quyền và các rủi ro symlink/TOCTOU thích hợp.
- [ ] Có phân biệt API Java 7 NIO.2 (`Paths.get`, `Path`) và các tiện ích bổ sung sau đó (`Path.of` từ Java 11, `Files.writeString` từ Java 11).

## Tài liệu chính thức còn hiệu lực

- [Java SE 17 — `java.nio.file.Path` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `isAbsolute`, `getRoot`, `resolve`, `relativize`, `normalize`, `toAbsolutePath`, `toRealPath` và ngữ nghĩa file-system provider.
- [Java SE 17 — `java.nio.file.Paths` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html): `Paths.get(String, String...)` và `Paths.get(URI)`.
- [Java SE 17 — `java.nio.file.Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `createDirectories`, `createTempDirectory`, `writeString`, `readAllBytes`, `isSameFile` và các thao tác I/O.
- [Java SE 17 — `java.nio.file.FileSystems` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): default filesystem và provider.
- [Java SE 17 — `java.nio.file.LinkOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` khi thao tác với link.
- [Java SE 17 — `java.nio.file.SecureDirectoryStream` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác directory-relative trong những provider hỗ trợ nhằm giảm một số race.
- [Java SE 17 — `java.lang.Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getResourceAsStream` và việc tìm resource trên classpath.

**Kết luận:** Một `Path` không tự biết “thư mục dự án”. **Relative path** cần base (thường là working directory), còn **absolute path** có root theo filesystem. `resolve` và `normalize` xử lý **cấu trúc đường dẫn**, `toAbsolutePath` chuyển sang dạng absolute, còn `toRealPath` truy cập mục thật trên filesystem. Chọn base rõ ràng, kiểm thử trên thư mục tạm, phân biệt resource đóng gói với file ngoài và không dùng các phép biến đổi từ vựng làm bảo đảm bảo mật khi xử lý đường dẫn chưa tin cậy.