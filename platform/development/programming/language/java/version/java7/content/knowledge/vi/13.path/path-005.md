# Java 7 — Path: Ghép bằng resolve, resolveSibling

## 1. Mục tiêu của bài

`java.nio.file.Path` là abstraction biểu diễn **đường dẫn tới file hoặc thư mục** trong một `FileSystem`. Nó được giới thiệu cùng NIO.2 từ Java 7 và vẫn là API chuẩn, được dùng rộng rãi trên Java 17+.

Hai phương thức dễ nhầm nhất khi ghép đường dẫn là:

- **`resolve(other)`:** ghép `other` **vào cuối chính Path hiện tại** như thể Path hiện tại là một thư mục. Thường dùng để tạo đường dẫn con, ví dụ `directory.resolve("report.csv")`.
- **`resolveSibling(other)`:** ghép `other` **vào thư mục cha** của Path hiện tại, về mặt khái niệm thay thành phần tên cuối cùng bằng một tên/đường dẫn khác. Thường dùng để tạo đường dẫn ngang cấp như file backup, file đổi tên hoặc một thư mục khác cùng cha.

Ví dụ:

```java
Path directory = Path.of("workspace", "reports");
Path source = directory.resolve("report.txt");

Path child = directory.resolve("summary.csv");
Path sibling = source.resolveSibling("report.bak");
```

Đây là **snippet cần đặt trong phương thức** sau khi `import java.nio.file.Path;`. Trên một hệ thống dùng dấu `/` để phân tách thành phần, `child` biểu diễn `workspace/reports/summary.csv` và `sibling` biểu diễn `workspace/reports/report.bak`.

**Điều quan trọng nhất:** Hai phép ghép này chủ yếu là **thao tác trên đối tượng Path**, không tự tạo file, không mở thư mục, không di chuyển hay đổi tên file trên đĩa. Để thao tác với dữ liệu thực, phải dùng API như `Files.createDirectories`, `Files.copy`, `Files.move`, `Files.readString`, ... với quyền truy cập và xử lý ngoại lệ phù hợp.

Trong bài, ví dụ chính chạy bằng JDK 17+, có kết quả ổn định giữa Windows và Linux/macOS bằng cách chỉ chuẩn hóa **dấu phân cách cho mục đích in log**. Không thay đổi Path thật để ép hệ điều hành dùng dấu `/`.

## 2. Path là đối tượng đường dẫn, không phải chuỗi nối thủ công

Khai báo:

```java
Path base = Path.of("workspace", "reports");
```

tạo một Path **tương đối**, gồm hai thành phần `workspace` và `reports`. Trên Windows, biểu diễn chuỗi có thể là `workspace\reports`; trên Linux/macOS có thể là `workspace/reports`. Cả hai vẫn biểu diễn cùng cấu trúc **tương đối** trong file system mặc định của môi trường tương ứng.

**Phân biệt:**

- `Path` có thể **relative** (ví dụ `reports/2026.csv`) hoặc **absolute** (ví dụ `/srv/reports/2026.csv` trên hệ UNIX, hoặc `C:\reports\2026.csv` trên một hệ Windows).
- `Path.of(...)` và `Paths.get(...)` tạo đối tượng Path dựa trên cú pháp của provider.
- `Path.of(...)` xuất hiện từ **Java 11**; nếu đang bảo trì mã Java 7 theo nghĩa lịch sử, `Paths.get(...)` là API tương đương đã có từ Java 7. Trong code Java 17+ nên dùng `Path.of(...)` khi phù hợp.
- `Path` chỉ mô tả vị trí; **không bảo đảm file/thư mục tồn tại**. `Files.exists(path)` hoặc thao tác I/O cụ thể mới tương tác với file system.
- Một đối tượng `Path` là **immutable**, tức phép ghép trả về một Path kết quả và không sửa đối tượng ban đầu.

Ví dụ đọc rõ hơn nối chuỗi:

```java
Path report = Path.of("data", "reports").resolve("annual.csv");
```

thay cho:

```java
String reportName = "data" + "/" + "reports" + "/" + "annual.csv";
```

Đoạn thứ hai chỉ là một chuỗi; nó không nắm rõ root, thành phần tên, ký tự phân cách riêng của file system hoặc cách các provider xử lý path. Khi xây đường dẫn filesystem, ưu tiên `Path` và các phương thức của nó.

## 3. Chữ ký API cần nhớ

Các phương thức có trên `java.nio.file.Path`:

```java
Path resolve(Path other);
Path resolve(String other);

Path resolveSibling(Path other);
Path resolveSibling(String other);
```

Đây là **các chữ ký rút gọn để học**, không phải code cần tự khai báo lại.

Overload nhận `String` sẽ chuyển tên/đường dẫn chuỗi sang `Path` bằng file system của receiver rồi thực hiện phép ghép tương ứng. Overload nhận `Path` hữu ích khi bạn đã có một Path hoặc muốn ghép nhiều thành phần đã được tạo rõ ràng.

Hai quy tắc diễn đạt nhanh:

```text
base.resolve(other)          ≈ base / other

file.resolveSibling(other)   ≈ file.getParent() / other
                               nếu file có parent
```

Ký hiệu `/` ở đây là **minh họa cấu trúc**, không phải một toán tử Java. Dòng thứ hai có ngoại lệ quan trọng: nếu `file.getParent() == null`, `resolveSibling(other)` trả về chính `other` (xem phần 6).

Các trường hợp `other` tuyệt đối hoặc có root thành phần đặc biệt phải hiểu theo hợp đồng `Path`; không thể coi `resolve` như “nối hai String” trong mọi tình huống.

## 4. resolve(): ghép đường dẫn con từ một thư mục gốc

### 4.1. Cơ chế cơ bản

```java
Path directory = Path.of("workspace", "reports");
Path file = directory.resolve("summary.csv");
```

Nếu `other` tương đối và không có thành phần root đặc biệt, `resolve` trả đường dẫn có các thành phần của `directory`, sau đó là các thành phần của `other`. Với biểu diễn dùng `/`, kết quả là:

```text
workspace/reports/summary.csv
```

Phương thức **không tự kiểm tra rằng `workspace/reports` thật sự là thư mục**. Nó chỉ coi Path hiện tại là cơ sở để ghép. Nếu Path hiện tại trỏ tới một file có thật, `file.resolve("nested.txt")` vẫn tạo được Path có cấu trúc `file/nested.txt`; lỗi chỉ có thể xuất hiện khi thao tác I/O về sau.

### 4.2. Ghép Path có nhiều thành phần

```java
Path root = Path.of("workspace", "reports");
Path nested = root.resolve(Path.of("2026", "q1.csv"));
```

Kết quả có cấu trúc:

```text
workspace/reports/2026/q1.csv
```

Bạn cũng có thể ghép theo chuỗi lời gọi:

```java
Path nested = root.resolve("2026").resolve("q1.csv");
```

Kết quả về mặt thành phần đường dẫn là tương đương khi `other` chỉ gồm các thành phần tương đối bình thường. Cách chain hữu ích khi mỗi cấp được tính từ một giá trị riêng.

### 4.3. resolve() không tự normalize dấu chấm

```java
Path root = Path.of("workspace", "reports");
Path raw = root.resolve("..").resolve("private.txt");

System.out.println(raw.normalize());
```

Đây là snippet trong phương thức. `raw` vẫn chứa thành phần `..` khi mới ghép. `normalize()` sẽ loại bỏ các thành phần thừa theo quy tắc *lexical* của provider, ví dụ kết quả cấu trúc là `workspace/private.txt`. **`resolve()` không tự gọi `normalize()`.**

Nếu Path có liên quan tới symbolic link, việc loại bỏ `..` trên chuỗi path có thể thay đổi file mà nó trỏ tới; vì vậy `normalize()` không được xem là một phép kiểm tra an toàn vật lý đối với hệ thống file.

### 4.4. resolve() nhận Path tuyệt đối

Theo hợp đồng `Path.resolve(Path)`, nếu `other.isAbsolute() == true` thì **kết quả là `other`**, không nối thêm vào `base`.

```java
Path base = Path.of("workspace", "reports");
Path absolute = base.toAbsolutePath().getRoot().resolve("fixed.txt");

System.out.println(base.resolve(absolute).equals(absolute)); // true
```

Đây là snippet trong phương thức. `getRoot()` từ absolute path của filesystem mặc định trong ví dụ tạo một root phù hợp; mục tiêu là kiểm tra hành vi, không in chính ổ đĩa hoặc working directory.

**Hậu quả thiết kế:** nếu nhận đường dẫn từ người dùng và gọi `trustedRoot.resolve(userSuppliedPath)`, một đầu vào **absolute** có thể **thay hoàn toàn trustedRoot**. Đừng coi `resolve` là cơ chế tự động ép mọi đường dẫn con nằm trong một root an toàn.

Ngoài đường dẫn hoàn toàn tuyệt đối, một số provider (đặc biệt Windows với drive-relative hoặc root-relative syntax) có những loại Path mang root nhưng chưa phải absolute đầy đủ. Javadoc nói cách resolve loại này **phụ thuộc implementation**; không áp quy tắc POSIX cho mọi provider.

## 5. resolveSibling(): ghép từ thư mục cha

### 5.1. Thay tên file trong cùng thư mục

```java
Path source = Path.of("workspace", "reports", "report.txt");
Path backup = source.resolveSibling("report.bak");
```

Trong ví dụ đường dẫn tương đối này:

```text
source = workspace/reports/report.txt
backup = workspace/reports/report.bak
```

Đặt cạnh `resolve` để thấy khác biệt:

```java
Path child = source.resolve("report.bak");
Path sibling = source.resolveSibling("report.bak");
```

Kết quả ở biểu diễn dùng `/`:

```text
child   = workspace/reports/report.txt/report.bak
sibling = workspace/reports/report.bak
```

Vì `resolve` coi **toàn bộ source** là base directory, trong khi `resolveSibling` lấy **parent của source** làm base. Nếu `source` đại diện cho một file, `resolve("...")` thường không phải ý định khi muốn đổi tên file; hãy dùng `resolveSibling`.

### 5.2. Không nhất thiết `other` chỉ là một tên file

```java
Path source = Path.of("workspace", "reports", "report.txt");
Path archived = source.resolveSibling(Path.of("archive", "report.txt"));
```

Kết quả là `workspace/reports/archive/report.txt` (theo dạng có `/`). `other` ở đây là một **đường dẫn tương đối gồm hai thành phần**, được ghép từ parent của source. Vì thế cách mô tả chính xác của `resolveSibling` là **resolve `other` against parent**, chứ không phải “chỉ thay đuôi tên file”.

### 5.3. Path hiện tại có thể là thư mục

```java
Path directory = Path.of("workspace", "drafts");
Path otherDirectory = directory.resolveSibling("final");
```

Kết quả tương đương `workspace/final`. `resolveSibling` hoạt động cho **Path bất kỳ**, không yêu cầu Path phải có đuôi file, là file thật hoặc đã tồn tại.

### 5.4. Một đối số tuyệt đối vẫn thắng

Khi `other` là absolute, `source.resolveSibling(other)` trả `other`. Đừng dùng phương thức này như một cơ chế hạn chế đường dẫn đầu vào: nó có cùng rủi ro “đầu vào absolute làm thoát root” như `resolve`.

## 6. Trường hợp đặc biệt: parent == null, Path rỗng và root

### 6.1. Không có parent: resolveSibling trả other

Theo Javadoc, nếu receiver **không có parent**, `resolveSibling(other)` trả chính `other`. Ví dụ:

```java
Path simple = Path.of("report.txt");
Path renamed = simple.resolveSibling("renamed.txt");

System.out.println(renamed); // renamed.txt
```

Đây là snippet trong phương thức. `simple.getParent() == null` vì chỉ có một thành phần tên tương đối, nên phương thức không thể ghép với một parent không tồn tại. Nó chỉ trả đối số `renamed.txt`.

Người mới học đôi khi nghĩ kết quả sẽ là `./renamed.txt`. Về địa chỉ trong working directory, hai biểu diễn có thể chỉ cùng vị trí, nhưng **đối tượng trả về theo quy tắc API** chính là `other`.

### 6.2. `resolve` với đường dẫn rỗng

Theo hợp đồng, nếu `other` là **empty Path**, `base.resolve(other)` trả về `base`.

```java
Path base = Path.of("workspace", "reports");
Path unchanged = base.resolve(Path.of(""));

System.out.println(unchanged.equals(base)); // true
```

Đây là snippet trong phương thức. Dùng `Path.of("")` làm ví dụ empty Path; nó **không phải null**.

### 6.3. `resolveSibling` với đường dẫn rỗng

Đây là trường hợp dễ bỏ sót:

```java
Path file = Path.of("workspace", "reports", "report.txt");
Path parent = file.resolveSibling(Path.of(""));
```

Theo Javadoc, kết quả của `resolveSibling(empty Path)` là **parent của file** nếu có; với ví dụ trên là `workspace/reports`. Nếu receiver không có parent thì kết quả là **empty Path**. Đây không phải cách thay thế tốt cho `getParent()` trong code rõ nghĩa, nhưng là một đặc tính cần hiểu nếu đối số có thể rỗng.

### 6.4. Path chỉ có root

Một Path biểu diễn riêng filesystem root có thể không có parent, do đó `resolveSibling(other)` có thể đơn giản trả `other`. Nếu đang làm việc với root, hãy kiểm tra `getParent()` và thiết kế nghiệp vụ thay vì suy rằng mọi Path đều có parent.

## 7. Chương trình Java 17+ hoàn chỉnh, không cần tạo file

Chương trình sau chỉ tạo và so sánh **Path objects**, không tạo file, không ghi ổ đĩa. Dùng method `portable` để đổi dấu `\` thành `/` **chỉ khi in ra màn hình**, giúp stdout có cùng cấu trúc khi chạy trên Windows và Linux/macOS (với filesystem mặc định thông thường).

Tạo tệp **`PathComposeDemo.java`**:

```java
import java.nio.file.Path;

public class PathComposeDemo {
    private static String portable(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path directory = Path.of("workspace", "reports");
        Path source = directory.resolve("report.txt");

        System.out.println("resolve name = " +
                portable(directory.resolve("summary.csv")));
        System.out.println("resolve nested = " +
                portable(directory.resolve(Path.of("2026", "q1.csv"))));
        System.out.println("resolve chained = " +
                portable(directory.resolve("2026").resolve("q1.csv")));

        System.out.println("sibling file = " +
                portable(source.resolveSibling("report.bak")));
        System.out.println("sibling nested = " +
                portable(source.resolveSibling(Path.of("archive", "report.txt"))));
        System.out.println("no parent = " +
                portable(Path.of("report.txt").resolveSibling("renamed.txt")));

        Path absolute = directory.toAbsolutePath().getRoot().resolve("fixed.txt");
        System.out.println("absolute replaces base = " +
                directory.resolve(absolute).equals(absolute));
        System.out.println("absolute sibling = " +
                source.resolveSibling(absolute).equals(absolute));
        System.out.println("empty keeps base = " +
                directory.resolve(Path.of("")).equals(directory));

        Path withParentTraversal = directory.resolve("..").resolve("private.txt");
        System.out.println("before normalize = " + portable(withParentTraversal));
        System.out.println("after normalize = " + portable(withParentTraversal.normalize()));

        Path allowedRoot = directory.toAbsolutePath().normalize();
        Path outside = allowedRoot.resolve("..").resolve("secret.txt").normalize();
        System.out.println("outside allowed root = " +
                !outside.startsWith(allowedRoot));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 PathComposeDemo.java
java PathComposeDemo
```

**Stdout với file system mặc định Windows/Linux/macOS thông dụng:**

```text
resolve name = workspace/reports/summary.csv
resolve nested = workspace/reports/2026/q1.csv
resolve chained = workspace/reports/2026/q1.csv
sibling file = workspace/reports/report.bak
sibling nested = workspace/reports/archive/report.txt
no parent = renamed.txt
absolute replaces base = true
absolute sibling = true
empty keeps base = true
before normalize = workspace/reports/../private.txt
after normalize = workspace/private.txt
outside allowed root = true
```

**Giải thích:**

1. Ba dòng đầu mô tả `resolve` ghép relative name/path vào chính thư mục `workspace/reports`.
2. Hai dòng `sibling` dùng **parent của source** (`workspace/reports`), nên có tên file mới ngang cấp hoặc một đường dẫn lồng tương đối tính từ parent.
3. `no parent` cho thấy `Path.of("report.txt")` không có parent, vì thế `resolveSibling` trả Path đối số.
4. Hai dòng `absolute` minh họa đối số absolute trả về chính nó, không bị gắn dưới base.
5. `empty keeps base` cho thấy `base.resolve(Path.of(""))` không thêm thành phần.
6. `normalize()` rút gọn `reports/..` thành đường dẫn cấp trên về mặt lexical. Nó **không kiểm tra thư mục tồn tại hoặc xử lý symbolic link theo nghĩa filesystem**.
7. Dòng cuối tạo một Path có `..` và chuẩn hóa; `startsWith(allowedRoot)` cho thấy **lexical prefix** đã bị thoát trong ví dụ. Đây chỉ là ví dụ phát hiện tình huống đơn giản, **không phải một sandbox filesystem hoàn chỉnh an toàn trước symlink/race**.

Ví dụ không in ổ đĩa gốc/working directory cụ thể, vì những giá trị đó phụ thuộc máy. Nó kiểm tra kết quả so sánh boolean thay vì đưa đường dẫn tuyệt đối không ổn định vào stdout.

## 8. Bảng so sánh nhanh resolve và resolveSibling

Giả sử:

```java
Path p = Path.of("root", "docs", "a.txt");
Path directory = Path.of("root", "docs");
```

Bảng dưới biểu diễn kết quả theo dấu `/`; dấu phân cách thực tế phụ thuộc hệ điều hành.

| Biểu thức | Kết quả minh họa | Vì sao |
| --- | --- | --- |
| `directory.resolve("b.txt")` | `root/docs/b.txt` | Ghép vào directory |
| `p.resolve("b.txt")` | `root/docs/a.txt/b.txt` | Coi toàn bộ p là base |
| `p.resolveSibling("b.txt")` | `root/docs/b.txt` | Ghép vào parent của p |
| `p.resolveSibling(Path.of("archive","b.txt"))` | `root/docs/archive/b.txt` | Other có nhiều thành phần tương đối |
| `Path.of("a.txt").resolveSibling("b.txt")` | `b.txt` | Receiver không có parent |
| `directory.resolve(Path.of(""))` | `root/docs` | Other là empty Path |
| `p.resolveSibling(Path.of(""))` | `root/docs` | Empty sibling → parent |
| `directory.resolve(Path.of("..","secret.txt"))` | `root/docs/../secret.txt` (chưa normalize) | Resolve không tự loại `..` |
| `directory.resolve(Path.of("..","secret.txt")).normalize()` | `root/secret.txt` | Chuẩn hóa lexical |
| `p.resolveSibling(absolute)` | `absolute` | Other absolute thắng parent |

Đây là **bảng ngữ nghĩa Path**, không có bước đọc/ghi file và không đòi hỏi các đường dẫn thực sự tồn tại. Nếu một đối số chứa cú pháp root đặc biệt của provider, kết quả có thể provider-dependent; không suy rộng bảng POSIX sang mọi trường hợp đường dẫn Windows.

## 9. Dùng resolve cho cây thư mục cấu hình hoặc output

Một tình huống phù hợp là ứng dụng có một base directory do hệ thống xác định:

```java
Path dataDirectory = Path.of("data", "exports");
Path reportFile = dataDirectory.resolve("monthly.csv");
Path archiveDirectory = dataDirectory.resolve("archive");
Path archivedReport = archiveDirectory.resolve("monthly.csv");
```

Đây là snippet trong phương thức. Ưu điểm là mọi path con có chung điểm xuất phát, không cần thao tác nối chuỗi. Tuy nhiên, các lệnh này **chưa tạo thư mục**.

Khi thực sự muốn tạo thư mục và ghi file:

```java
Files.createDirectories(dataDirectory);
Files.writeString(
        reportFile,
        "report contents",
        StandardCharsets.UTF_8);
```

Đây là **mã minh họa** với import `java.nio.file.Files` và `java.nio.charset.StandardCharsets`, nằm trong phương thức có xử lý `IOException`. `Files.createDirectories` thực hiện I/O và có thể thất bại do quyền truy cập, đường dẫn trùng file hoặc lỗi hệ thống. `Files.writeString` ghi nội dung thực; đoạn mã cần được điều chỉnh theo chính sách ghi đè/atomicity của dự án. Đừng lẫn nó với việc tạo một `Path`.

### 9.1. Thư mục hiện tại được tính ở đâu?

`Path.of("data","exports")` là **relative Path**. Khi dùng vào I/O với file system mặc định, vị trí được hiểu tương đối với working directory theo môi trường. Nếu ứng dụng chạy từ thư mục khác nhau, file output có thể xuất hiện ở vị trí khác. Với dịch vụ hoặc tác vụ định kỳ, có thể chọn một root tuyệt đối cấu hình rõ ràng và kiểm tra quyền, thay vì phụ thuộc working directory không được kiểm soát.

## 10. Dùng resolveSibling để tính tên backup, rename và file đích

### 10.1. Tính đường dẫn backup

```java
Path original = Path.of("data", "exports", "report.csv");
Path backup = original.resolveSibling("report.csv.bak");
```

Kết quả cấu trúc là:

```text
original = data/exports/report.csv
backup   = data/exports/report.csv.bak
```

**Đây mới là tính toán đường dẫn.** File `report.csv.bak` chưa tự động tồn tại. Nếu cần thực sự tạo bản sao:

```java
Files.copy(original, backup);
```

Đây là snippet trong phương thức có import `Files` và xử lý `IOException`. Cần xác định có cho phép ghi đè file backup hay không; hành vi mặc định của `Files.copy` không nhất thiết thay thế file đích đã tồn tại. Với backup quan trọng, còn phải tính đến ghi chưa hoàn chỉnh, quyền truy cập và tính nhất quán của dữ liệu.

### 10.2. Đổi tên file thực tế cần Files.move

```java
Path current = Path.of("data", "exports", "draft.csv");
Path renamed = current.resolveSibling("final.csv");

// Lệnh sau mới thực hiện di chuyển/đổi tên trên file system.
Files.move(current, renamed);
```

Đoạn trên là snippet đặt trong phương thức, có import `java.nio.file.Files` và xử lý `IOException`. `resolveSibling` chỉ tính target. `Files.move` mới là hành vi I/O; có thể thất bại nếu source không tồn tại, target bị chặn, thiếu quyền hoặc file system không hỗ trợ một thao tác mong muốn.

**Không tự mặc định `Files.move` luôn atomic.** Nếu nghiệp vụ yêu cầu thao tác atomic, phải kiểm tra và dùng option/hợp đồng phù hợp, chẳng hạn `StandardCopyOption.ATOMIC_MOVE` khi hệ thống hỗ trợ và xử lý `AtomicMoveNotSupportedException`.

### 10.3. Thay đuôi file có an toàn không?

Lấy tên file rồi dùng chuỗi để thay một suffix như `".txt"` là một **quy ước tên file**, không phải chức năng “replace extension” sẵn có của `Path`. Nếu code muốn tạo `report.bak`, có thể tính tên mới và gọi `resolveSibling(newName)`. Hãy xử lý rõ tên file không có dấu chấm, tên bắt đầu bằng dấu chấm, nhiều dấu chấm hoặc các trường hợp tên đặc biệt theo yêu cầu dự án. `resolveSibling` không tự suy ra quy tắc đuôi file.

## 11. Phối hợp với getParent, getFileName và normalize

Một số API thường đi cùng:

```java
Path p = Path.of("root", "docs", "report.txt");

System.out.println(p.getFileName()); // report.txt
System.out.println(p.getParent());   // root/docs (theo biểu diễn '/')
```

Đây là snippet trong phương thức. `getParent()` có thể trả `null`; đừng gọi `p.getParent().resolve(name)` mà không xét trường hợp đó. Nếu ý định là thay tên ở cùng cấp, `p.resolveSibling(name)` đã có quy tắc định sẵn cho trường hợp parent null.

`normalize()` loại bỏ thành phần dư thừa như `.` hoặc cặp `name/..` theo cách *lexical* được implementation hỗ trợ; **không cần truy cập file system**. `toAbsolutePath()` chuyển biểu diễn thành absolute theo môi trường/provider; **không đòi hỏi file tồn tại**. Ngược lại, `toRealPath()` yêu cầu file tồn tại và xử lý file system, có thể theo symbolic link và ném `IOException`.

| API | Mục đích | Có phải I/O? |
| --- | --- | --- |
| `p.resolve(other)` | Ghép từ chính p | Không |
| `p.resolveSibling(other)` | Ghép từ parent của p | Không |
| `p.getParent()` | Lấy parent về mặt path components | Không |
| `p.getFileName()` | Lấy phần tử tên cuối | Không |
| `p.normalize()` | Rút gọn thành phần dư thừa về mặt lexical | Không |
| `p.toAbsolutePath()` | Lấy Path absolute theo môi trường | Thường không kiểm tra file tồn tại; có thể phụ thuộc provider |
| `p.toRealPath()` | Tìm đường dẫn thực của file đang tồn tại | **Có**, có thể lỗi I/O |
| `Files.move(p, target)` | Di chuyển/đổi tên trên file system | **Có** |

**Đừng gọi `normalize()` là xác nhận path an toàn hoặc xác nhận đường dẫn thật.** Chỉ so sánh các chuỗi path trước khi tương tác với file system có thể không nắm được symbolic link hoặc thay đổi filesystem trong lúc chạy.

## 12. Phân biệt resolve với relativize

`resolve` và `relativize` không phải cùng thao tác:

- `base.resolve(relative)`: **ghép** một relative path dưới base.
- `base.relativize(target)`: tính một **relative path từ base tới target**, khi hai Path tương thích.

Ví dụ:

```java
Path base = Path.of("workspace", "reports");
Path target = Path.of("workspace", "reports", "2026", "q1.csv");

Path relative = base.relativize(target);
// relative tương đương 2026/q1.csv
Path rebuilt = base.resolve(relative);
// rebuilt tương đương workspace/reports/2026/q1.csv
```

Đây là snippet trong phương thức. `relativize` có thể lỗi nếu Path không tương thích, chẳng hạn một bên absolute còn bên kia relative, hoặc khác provider/drive tùy hệ thống. Với các Path chuẩn hóa tương thích, có quan hệ hữu ích giữa `resolve` và `relativize`; nhưng nó **không thay thế** việc kiểm tra tồn tại hoặc giải quyết symlink.

Nếu bài toán là thay tên file ở cùng thư mục, không cần dùng `relativize` phức tạp: `resolveSibling` diễn đạt đúng mục tiêu hơn.

## 13. Bảo mật: resolve() không chặn path traversal

Tình huống thường gặp: server có thư mục được phép là `/srv/uploads` và muốn tạo Path từ tên file người dùng gửi. Một cách viết thiếu an toàn:

```java
Path target = uploadRoot.resolve(userInput);
```

Đây là **mã minh họa** với `Path uploadRoot` và `Path userInput`. Nếu `userInput` là absolute, `resolve` có thể trả chính đường dẫn absolute đó. Nếu nó có `..`, kết quả sau chuẩn hóa có thể trỏ **ra ngoài** uploadRoot. `resolve` **không phải security boundary**.

### 13.1. Kiểm tra lexical containment là một lớp phòng vệ, chưa đủ mọi trường hợp

Ví dụ **minh họa việc kiểm tra lexical** cho một ứng dụng chỉ chấp nhận tên file con; không coi đây là một giải pháp upload an toàn hoàn chỉnh:

```java
static Path checkLexicalPath(Path root, Path userRelativePath) {
    if (userRelativePath.isAbsolute()) {
        throw new IllegalArgumentException("Absolute path is not allowed");
    }

    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(userRelativePath).normalize();

    if (!candidate.startsWith(normalizedRoot)) {
        throw new IllegalArgumentException("Path escapes allowed root");
    }
    return candidate;
}
```

Phương thức trên hợp lệ trong một class có import `java.nio.file.Path`. Nó kiểm tra đường dẫn absolute và việc `..` đưa Path chuẩn hóa ra ngoài root **theo tên/thành phần Path**. Dùng `Path.startsWith(Path)` thay vì `candidate.toString().startsWith(root.toString())`: so khớp chuỗi có thể bị đánh lừa bởi tên thư mục chung prefix, như `/safe/data` và `/safe/database`.

**Giới hạn bảo mật:**

- `normalize()` không duyệt file system và không tự giải quyết symbolic link.
- Một thư mục con có thể là symlink trỏ ra ngoài root; lexical `startsWith` không chứng minh file thực nằm trong root.
- File system có thể thay đổi giữa lúc kiểm tra và lúc mở file (*time-of-check/time-of-use race*).
- Nếu cho phép đường dẫn con tùy ý do người dùng kiểm soát, phải có chính sách component/filename rõ ràng, xử lý case, root, ký tự đặc biệt và cách provider diễn giải.
- Với truy cập hiện hữu, `toRealPath()` có thể giúp kiểm tra canonical/real path theo symlink policy phù hợp; nhưng **chỉ check rồi open** không đủ chống mọi race.
- Với bài toán bảo mật nhạy cảm, cân nhắc thao tác relative theo file descriptor/handle thư mục và API như `SecureDirectoryStream` nơi file system provider hỗ trợ, cùng cơ chế tạo file an toàn và quyền OS phù hợp.

Không sử dụng ví dụ check lexical ở trên như một “sandbox đủ an toàn cho upload công khai” khi chưa thiết kế symlink/race và quyền truy cập ở mức hệ thống.

### 13.2. resolveSibling cũng có rủi ro từ đầu vào không tin cậy

`source.resolveSibling(userProvidedName)` có thể dùng parent của source **hoặc trả nguyên đường dẫn tuyệt đối do người dùng đưa**. Nếu mục đích chỉ là đổi tên một file ngang cấp, tốt hơn là **validate một filename đơn**, không cho phép separator, absolute path và các thành phần `.`/`..` theo quy tắc provider, thay vì chấp nhận mọi Path.

Với ứng dụng thao tác tài liệu, cách suy nghĩ đúng là: **“Mình có quyền tạo file nào?”** trước, rồi mới chọn `resolve` hoặc `resolveSibling` để tính vị trí.

## 14. Tương thích Windows, Linux, macOS và FileSystem provider

`Path` giúp tránh hard-code dấu phân cách nhưng **không xóa khác biệt hệ điều hành**:

1. Windows thường dùng `\` trong `Path.toString()`; UNIX thường dùng `/`.
2. Windows có ký hiệu drive, UNC và các dạng path root-relative/drive-relative; không phải chuỗi có root nào cũng là absolute đầy đủ.
3. Quy tắc phân biệt hoa/thường, ký tự tên file không hợp lệ, reserved names và behavior của symbolic link có thể khác.
4. Một Path do zip filesystem hoặc provider khác tạo có quy tắc riêng; ghép Path từ hai provider không nên được giả định hợp lệ.
5. `Path.of("a", "b")` dùng cú pháp provider mặc định; không cần truyền thủ công `File.separator` giữa các phần tử.
6. Trong unit test, ưu tiên so sánh **Path với Path** hoặc in theo quy ước minh họa, không hard-code kết quả `toString()` dùng dấu `/` rồi áp cho mọi máy.

Ví dụ có thể dùng:

```java
Path expected = Path.of("data", "reports", "result.txt");
Path actual = Path.of("data", "reports").resolve("result.txt");

System.out.println(actual.equals(expected)); // true với provider mặc định
```

Đây là snippet trong phương thức. So sánh Path rõ nghĩa hơn so chuỗi có dấu phân cách; nhưng `equals` trên Path vẫn phụ thuộc provider và các quy tắc tên path, không phải so sánh “hai đường dẫn trỏ đúng cùng một file vật lý” trong mọi trường hợp. Nếu muốn xác định hai Path tương đương file thật, cần xem `Files.isSameFile` và các ngoại lệ I/O liên quan.

### 14.1. Không nhầm `Path` với URL

Dấu `/` trong URL và hệ thống file path là hai miền khác nhau. Nếu cần xây một HTTP URL từ những đoạn path, không sử dụng `Path.resolve` một cách mặc định; nó áp dụng cú pháp file system, có thể mang dấu `\` và xử lý drive khác. Dùng URI/URL API thích hợp cho URL, đồng thời xử lý encoding của URI path segments đúng cách.

## 15. Những lỗi phổ biến khi ghép Path

**Lỗi 1 — Dùng `file.resolve("backup.txt")` khi muốn tạo file ngang cấp.** Nó coi cả tên file cũ là thư mục, tạo cấu trúc `file/backup.txt`. Dùng `file.resolveSibling("backup.txt")`.

**Lỗi 2 — Nghĩ `resolveSibling` sẽ đổi tên file trên ổ đĩa.** Không. Nó chỉ trả Path đích; `Files.move` mới thực hiện đổi tên/di chuyển.

**Lỗi 3 — Nghĩ `resolve` sẽ tạo thư mục.** Không. Cần `Files.createDirectories` nếu muốn tạo thư mục thực.

**Lỗi 4 — Bỏ qua `getParent() == null`.** Một path đơn như `report.txt` không có parent; `resolveSibling("new.txt")` trả `new.txt`.

**Lỗi 5 — Ghép một Path absolute và tưởng nó vẫn bị buộc dưới base.** Trong `base.resolve(absolute)`, `absolute` thắng; không được xem resolve là phép hạn chế quyền truy cập.

**Lỗi 6 — Trông đợi `resolve` tự loại `.` và `..`.** Không. Nếu cần rút gọn lexical, gọi `normalize()` có chủ đích.

**Lỗi 7 — Coi `normalize()` là `toRealPath()`.** Sai. Normalize không truy cập file system; symbolic link và đường dẫn thực cần xử lý riêng.

**Lỗi 8 — Dùng kiểm tra `String.startsWith` để đảm bảo nằm trong thư mục an toàn.** Chuỗi prefix không đồng nghĩa prefix các thành phần Path. Dùng `Path.startsWith` cho lexical check, nhưng vẫn cần kiểm soát symlink/race khi security quan trọng.

**Lỗi 9 — Cho rằng mọi Path dùng dấu `/`.** Không. `toString()` phụ thuộc provider/OS. Chọn `Path.of("a","b")` và so sánh Path.

**Lỗi 10 — Dùng `resolveSibling` với tên mới chứa thư mục rồi tưởng nó chỉ thay phần tên cuối.** `other` có thể là một relative path nhiều phần; nó được ghép từ parent.

**Lỗi 11 — So sánh `Path.equals` để khẳng định cùng file vật lý.** Không chắc; `equals` không truy cập file system và không theo symbolic link. Với yêu cầu đó cân nhắc `Files.isSameFile`.

**Lỗi 12 — Dùng `Path.of(...)` rồi gọi là cú pháp từ Java 7.** `Path` có từ Java 7, nhưng factory `Path.of` có từ Java 11; JDK 17+ dùng được. Với source Java 7, từng dùng `Paths.get`.

**Lỗi 13 — Giả định `resolveSibling(empty)` trả nguyên file cũ.** Với Path có parent, nó trả parent; với Path không có parent, trả empty Path.

**Lỗi 14 — Bỏ qua case Windows drive-relative/root-relative.** Những Path có root nhưng không absolute đầy đủ có behavior phụ thuộc implementation. Test với provider thực tế nếu ứng dụng nhận dữ liệu kiểu đó.

**Lỗi 15 — Để đầu vào của người dùng tự do là Path rồi chỉ gọi normalize.** Symlink, race, file permissions và các format đặc biệt có thể khiến kiểm tra lexical không đủ.

## 16. Checklist áp dụng trong code review

- [ ] Nhiệm vụ là **ghép con vào thư mục** hay **thay mục cùng parent**? Chọn `resolve` hoặc `resolveSibling` đúng ý nghĩa.
- [ ] `base` có thật sự được coi là thư mục không? Có trường hợp nó là file hoặc empty Path?
- [ ] Có trường hợp `getParent() == null` không? Kết quả mong muốn khi `resolveSibling` trong trường hợp đó?
- [ ] `other` là relative, absolute, empty hay có root đặc biệt? Có làm base bị thay thế không?
- [ ] Có cần `normalize()`? Nếu có, nó chỉ là lexical, không thay thế `toRealPath()`.
- [ ] Đã phân biệt **tạo Path** với **tạo/đổi tên/copy file thật** chưa?
- [ ] Nếu `other` đến từ input không tin cậy, có chính sách cho phép cụ thể đối với tên file/đường dẫn không?
- [ ] Nếu cần hạn chế dưới một root, có kiểm tra cấu trúc Path thay vì String prefix không?
- [ ] Nếu security là yêu cầu thực, đã đánh giá symlink, race, quyền file system và provider chưa?
- [ ] Có hard-code dấu phân cách hoặc đường dẫn Windows/UNIX không? Ưu tiên `Path.of(segments...)`.
- [ ] Test có dùng Path equality để tránh phụ thuộc dấu phân cách khi không cần print không?
- [ ] Có kiểm thử Path đơn, Path rỗng, Path absolute, `..`, Path không tồn tại, parent null không?
- [ ] Các thao tác I/O thực đã có xử lý `IOException`, policy ghi đè và ownership đúng chưa?
- [ ] Có bị lẫn `relativize` với `resolve` hoặc ghép URL bằng Path API không?
- [ ] Nếu project biên dịch Java 17+, code dùng `Path.of` hợp lệ; nếu target khác, có kiểm tra release API không?

## 17. Câu hỏi tự kiểm tra

**1.** `Path.of("a","b").resolve("c.txt")` có cấu trúc gì? — **`a/b/c.txt`** theo cách in dấu `/`.

**2.** `Path.of("a","b","old.txt").resolveSibling("new.txt")`? — **`a/b/new.txt`**.

**3.** `Path.of("a","b","old.txt").resolve("new.txt")`? — **`a/b/old.txt/new.txt`**. `resolve` coi receiver là base.

**4.** `Path.of("old.txt").resolveSibling("new.txt")`? — **`new.txt`**, vì old.txt không có parent.

**5.** `base.resolve(absolutePath)` giữ base không? — **Không**. Theo hợp đồng, nó trả absolutePath.

**6.** `base.resolve(Path.of(""))` trả gì? — **base**, vì other là empty Path.

**7.** `Path.of("a","b","c.txt").resolveSibling(Path.of(""))`? — **`a/b`** theo cấu trúc thông thường.

**8.** `resolveSibling("backup.txt")` có tự tạo file backup không? — **Không**; phải dùng một API thao tác file, ví dụ `Files.copy`.

**9.** Muốn đổi tên file thật từ old.txt sang new.txt cần gì? — Tính target bằng `resolveSibling`, rồi gọi **`Files.move`** với xử lý lỗi và options phù hợp.

**10.** `Path.of("a","b").resolve("..").resolve("secret").normalize()`? — **`a/secret`** về mặt lexical trên provider mặc định thông thường.

**11.** `normalize()` có bảo đảm Path không qua symlink ra ngoài root không? — **Không**, vì không truy cập file system.

**12.** Tại sao `Files.isSameFile` khác `Path.equals`? — Vì `Files.isSameFile` kiểm tra danh tính file thực theo hợp đồng I/O, còn `Path.equals` là so sánh Path theo provider.

**13.** Với JDK 17+, dùng `Path.of` được không? — **Có**. Nhưng đây là factory có từ Java 11, không phải từ Java 7.

**14.** Một Path trỏ tới thư mục `drafts` có thể gọi `resolveSibling("final")` không? — **Có**; phương thức không yêu cầu receiver là file.

**15.** Khi kiểm tra root directory, vì sao nên dùng `candidate.startsWith(root)` thay vì so prefix String? — Vì `Path.startsWith` so **thành phần path**, tránh nhầm prefix các tên như `data` với `database`; tuy vậy vẫn chưa xử lý symlink/race.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 API — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `resolveSibling`, `getParent`, `normalize`, `toRealPath`, `relativize`, các trường hợp absolute, empty và no-parent.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): các thao tác I/O thật như `move`, `copy`, `createDirectories` và `isSameFile`.
- [Java SE 17 API — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác trên thư mục nhạy cảm với race nếu provider hỗ trợ.
- [Java SE 17 API — Paths](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html): factory `Paths.get` từng dùng từ Java 7; code mới JDK 17+ có thể dùng `Path.of`.

**Ghi nhớ:** `resolve()` nối `other` từ **chính Path hiện tại**; `resolveSibling()` nối `other` từ **parent của Path hiện tại**. Cả hai **không thao tác file**. Phải xét `other` absolute, receiver không có parent và `..`; dùng `normalize()` cho chuẩn hóa *lexical*, không xem nó là bảo vệ chống path traversal trong hệ thống file thực.