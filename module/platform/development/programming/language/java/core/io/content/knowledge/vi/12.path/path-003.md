# resolve, resolveSibling và ghép đường dẫn trong Java Path

`java.nio.file.Path` biểu diễn **đường dẫn** tới một vị trí trong hệ thống tệp. Khi làm việc với nhiều thư mục, tệp và tên do chương trình tạo, nên dùng `Path.resolve(...)`, `Path.resolveSibling(...)` và `Path.of(...)` để ghép các thành phần thay vì tự nối chuỗi dấu `/` hoặc `\`.

Cần ghi nhớ ngay: **tạo hoặc biến đổi `Path` không tạo thư mục, không tạo tệp và không đọc nội dung**. Chỉ khi gọi các thao tác I/O như `Files.createDirectories`, `Files.writeString` hoặc `Files.newInputStream`, chương trình mới thật sự tương tác với dữ liệu tại đường dẫn đó.

## 1. Phân biệt ba thao tác chính

| API | Ý tưởng | Ví dụ đường dẫn dạng tương đối |
| --- | --- | --- |
| `Path.of(first, more...)` | Tạo đường dẫn từ những thành phần được cung cấp | `Path.of("data", "2026", "report.txt")` |
| `base.resolve(child)` | Giải quyết đường dẫn `child` **dựa trên `base`**, xem `base` như một vị trí thư mục trong trường hợp thông thường | `Path.of("data").resolve("report.txt")` |
| `path.resolveSibling(name)` | Thay tên cuối bằng tên anh em, dựa trên **thư mục cha** của `path` | `Path.of("data", "old.txt").resolveSibling("new.txt")` |

Để dễ hình dung:

```text
Path.of("reports", "2026")          -> reports/2026
  .resolve("summary.txt")           -> reports/2026/summary.txt

Path.of("reports", "2026", "old.txt")
  .resolveSibling("new.txt")        -> reports/2026/new.txt
                                      ^ giữ thư mục cha; thay tên cuối
```

Dấu `/` trong sơ đồ chỉ giúp người đọc dễ quan sát. Khi hiển thị đường dẫn trên Windows, dấu phân tách thường là `\`. Không nên viết bài kiểm thử phụ thuộc vào chuỗi dấu phân tách nếu muốn mã chạy trên nhiều hệ điều hành.

## 2. `Path.of(...)` tạo một đối tượng đường dẫn

`Path.of` là factory method có từ Java 11 để tạo `Path`:

```java
import java.nio.file.Path;

Path file = Path.of("workspace", "docs", "guide.txt");
Path directory = Path.of("workspace", "docs");
Path current = Path.of(".");
```

Các đoạn trên là khai báo minh họa; cần đặt trong một class/phương thức. Chúng chỉ tạo đối tượng đường dẫn: **không cần `workspace` hoặc `docs` đang tồn tại**.

`Path.of("workspace", "docs", "guide.txt")` thường dễ đọc và an toàn về dấu phân tách hơn việc tự ghép `"workspace/" + "docs/" + "guide.txt"`. Một số lưu ý:

- Thành phần đường dẫn phải tuân theo cú pháp của **filesystem provider** hiện tại. Tên không hợp lệ có thể khiến `InvalidPathException` được ném ra khi tạo `Path`.
- `Path.of` không kiểm tra quyền đọc, ghi hoặc tính tồn tại của file.
- `Path` là một đối tượng biểu diễn tên/vị trí; đối tượng nhận từ `resolve` hoặc `normalize` là kết quả đường dẫn mới, không tự sửa `Path` ban đầu.
- `Path.of("report.txt")` là một đường dẫn tương đối một thành phần; nó **không tự có thư mục cha** trong đối tượng đó: `getParent() == null`.

Trong Java 7–10, cách phổ biến là `Paths.get(...)`; với Java 17+, `Path.of(...)` thường rõ ràng hơn.

## 3. `resolve(...)` — đi từ thư mục gốc logic xuống vị trí con

Ví dụ:

```java
Path base = Path.of("storage", "documents");
Path report = base.resolve("2026").resolve("report.txt");
```

Kết quả tương đương đường dẫn được cấu thành bằng `Path.of("storage", "documents", "2026", "report.txt")` trên cùng provider.

`resolve` có hai overload thường gặp:

```java
Path child1 = base.resolve("image.png");             // String
Path child2 = base.resolve(Path.of("2026", "data"));  // Path
```

Khi đối số `other` là đường dẫn **tương đối** thông thường, phương thức nối các thành phần vào `base`. `resolve` không đọc nội dung và không kiểm tra file con có tồn tại hay không.

### `base` được hiểu như thư mục

Hãy xét:

```java
Path path = Path.of("images", "photo.jpg");
Path unexpected = path.resolve("thumbnail.jpg");
```

Về mặt ghép tên, kết quả sẽ có các thành phần `images/photo.jpg/thumbnail.jpg`. `resolve` **không biết** `photo.jpg` là file thông thường; nó chỉ coi đường dẫn bên trái là nơi đặt đường dẫn con. Muốn có `images/thumbnail.jpg`, nên dùng `path.resolveSibling("thumbnail.jpg")` hoặc `path.getParent().resolve("thumbnail.jpg")` sau khi kiểm tra có parent.

### Đối số tuyệt đối và đường dẫn có root

Với các đường dẫn tương đối, `resolve` tạo kết quả ghép có thể dự đoán. Với đối số là **đường dẫn tuyệt đối**, quy tắc thường là kết quả chính là đường dẫn tuyệt đối được truyền vào; các trường hợp đường dẫn có root/drive mang tính đặc thù hệ điều hành hoặc provider nên được xử lý cẩn thận.

Đối với ứng dụng **chỉ cho phép tên file tương đối**, hãy xác thực bằng `child.isAbsolute()` trước khi gọi `base.resolve(child)`, đồng thời kiểm soát `..`. Không coi phép `resolve` tự nó là biện pháp chống path traversal.

### Tên rỗng và đường dẫn đặc biệt

`Path` có thể biểu diễn đường dẫn rỗng và các thành phần `.`, `..`. `resolve` không nhất thiết tự bỏ tất cả các thành phần đặc biệt; nếu muốn rút gọn *theo cú pháp*, gọi `normalize()`. Việc chuẩn hóa cú pháp không xác nhận đường dẫn có tồn tại hoặc an toàn trước symbolic links.

## 4. `resolveSibling(...)` — đường dẫn ngang cấp

`resolveSibling` dùng **parent của đường dẫn hiện tại** làm cơ sở để giải quyết đường dẫn được đưa vào:

```java
Path oldFile = Path.of("reports", "2026", "old.csv");
Path newFile = oldFile.resolveSibling("new.csv");
```

Kết quả là đường dẫn có các thành phần `reports/2026/new.csv`, tức **hai file ngang cấp trong thư mục `2026`**. Đây là thao tác ghép tên; nó **không đổi tên file thật**.

Hãy so sánh:

```java
Path original = Path.of("reports", "old.csv");

Path child = original.resolve("new.csv");
// reports/old.csv/new.csv : coi original là vị trí thư mục.

Path sibling = original.resolveSibling("new.csv");
// reports/new.csv : dùng parent của original.
```

`resolveSibling` hữu ích khi cần tạo một đường dẫn “cùng thư mục, tên khác”, ví dụ:

- Tệp gốc `orders.csv` và tệp kết quả `orders-clean.csv`.
- File cấu hình `service.yml` và file sao lưu `service.yml.bak`.
- Tệp tạo tạm trong cùng thư mục để chuẩn bị thay thế.
- Ảnh gốc `photo.jpg` và bản thu nhỏ `photo-thumb.jpg`.

Tuy vậy, thao tác ghi/đổi tên/move thật phải gọi API `Files`; chỉ `resolveSibling` **không tạo hay sửa** file nào.

### Trường hợp không có parent

Với `Path.of("readme.md")`, `getParent()` trả `null`; theo hợp đồng, `resolveSibling("other.md")` sẽ trả đường dẫn `other.md` được cung cấp (thay vì ném `NullPointerException` vì không có parent).

```java
Path file = Path.of("readme.md");
Path renamed = file.resolveSibling("other.md");

System.out.println(renamed.equals(Path.of("other.md"))); // true
```

Do đó, khi muốn ghép với `getParent()` bằng tay, **phải tự xử lý `null`**, còn `resolveSibling` cung cấp hành vi đã định nghĩa cho tình huống này.

## 5. Bảng minh họa đường dẫn con và đường dẫn ngang cấp

Giả sử:

```java
Path base = Path.of("projects", "demo");
Path file = base.resolve("README.md");
```

| Biểu thức | Các thành phần của kết quả | Ý nghĩa |
| --- | --- | --- |
| `base.resolve("src")` | `projects / demo / src` | Thư mục con logic |
| `base.resolve(Path.of("src", "Main.java"))` | `projects / demo / src / Main.java` | File dưới `src` |
| `file.resolveSibling("LICENSE")` | `projects / demo / LICENSE` | Tên khác cùng cấp `README.md` |
| `base.resolveSibling("demo-backup")` | `projects / demo-backup` | Đường dẫn ngang cấp với **thư mục** `demo` |
| `file.resolve("LICENSE")` | `projects / demo / README.md / LICENSE` | Không phải sibling; dễ sai nếu `README.md` là file |

Điểm cần nhấn mạnh: `resolveSibling` không chỉ dùng cho file. Khi gọi trên một **đường dẫn thư mục**, nó tạo đường dẫn ngang cấp với thư mục đó trong cùng parent (theo logic đường dẫn).

## 6. Chương trình Java 17+ đầy đủ: ghép đường dẫn, không tạo file

Ví dụ sau kiểm tra các quan hệ bằng `Path.equals`, `getFileName` và `getParent` để kết quả **không phụ thuộc ký tự phân tách** giữa Windows/Linux. Không có lệnh đọc, ghi hoặc tạo file.

Lưu thành **`PathComposeDemo.java`**:

```java
import java.nio.file.Path;

public class PathComposeDemo {

    public static void main(String[] args) {
        Path base = Path.of("workspace", "reports");
        Path report = base.resolve("2026").resolve("summary.txt");
        Path joined = Path.of(
                "workspace", "reports", "2026", "summary.txt");

        Path sibling = report.resolveSibling("metrics.csv");
        Path directorySibling = base.resolveSibling("archive");
        Path normalized = base.resolve("drafts")
                .resolve("..")
                .resolve("final.txt")
                .normalize();

        System.out.println("Resolve equals Path.of: "
                + report.equals(joined));
        System.out.println("Report name: " + report.getFileName());
        System.out.println("Sibling name: " + sibling.getFileName());
        System.out.println("Sibling keeps parent: "
                + sibling.getParent().equals(report.getParent()));
        System.out.println("Directory sibling name: "
                + directorySibling.getFileName());
        System.out.println("Normalize result matches: "
                + normalized.equals(base.resolve("final.txt")));
        System.out.println("No-parent sibling: "
                + Path.of("note.txt")
                    .resolveSibling("done.txt")
                    .equals(Path.of("done.txt")));
        System.out.println("Original base unchanged: "
                + base.equals(Path.of("workspace", "reports")));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PathComposeDemo.java
java PathComposeDemo
```

**Stdout chính xác:**

```text
Resolve equals Path.of: true
Report name: summary.txt
Sibling name: metrics.csv
Sibling keeps parent: true
Directory sibling name: archive
Normalize result matches: true
No-parent sibling: true
Original base unchanged: true
```

Giải thích:

1. `Path.of("workspace", "reports", "2026", "summary.txt")` và chuỗi `resolve("2026").resolve("summary.txt")` tạo các thành phần giống nhau.
2. `resolveSibling("metrics.csv")` chỉ đổi thành phần tên cuối, nên parent của sibling vẫn bằng parent của report.
3. `base.resolveSibling("archive")` tạo đường dẫn tới `archive` ngang cấp với `reports`, chứ không đặt `archive` bên trong `reports`.
4. `normalize()` rút gọn đoạn `drafts/..` theo cú pháp; nó không cần file/directory thật.
5. `Path.of("note.txt")` không có parent được ghi trong đường dẫn, nhưng `resolveSibling` vẫn trả đúng tên mới.
6. `Path` ban đầu vẫn giữ nguyên; các phương thức dựng ra đối tượng kết quả.

Ví dụ **không kiểm tra `Files.exists`** vì bài đang minh họa biến đổi đường dẫn, độc lập với file có thực tế tồn tại hay không.

## 7. `normalize()` và `toAbsolutePath()` không mở file

`resolve` thường được dùng cùng `normalize`:

```java
Path input = Path.of("data", "staging", "..", "reports", ".", "a.txt");
Path cleaned = input.normalize();
```

Các thành phần `staging/..` và `.` được xử lý theo quy tắc lexical; kết quả tương ứng có các thành phần `data/reports/a.txt` trong tình huống thông thường. `normalize()` **không thực hiện I/O**. Đặc biệt, với symbolic link, một đường dẫn đã normalize không nhất thiết dẫn tới cùng vị trí thực như đường dẫn trước đó, bởi `..` có thể có ý nghĩa khác sau khi đi qua liên kết.

`toAbsolutePath()` tạo biểu diễn tuyệt đối dựa trên quy tắc provider/thư mục làm việc:

```java
Path relative = Path.of("data", "report.txt");
Path absolute = relative.toAbsolutePath();
```

Nó **không chứng minh file tồn tại**. Cũng không nên dùng kết quả `toAbsolutePath().toString()` làm stdout cố định trong bài học vì máy và thư mục làm việc khác nhau.

`toRealPath(...)` khác ở chỗ thường cần truy cập hệ thống tệp để tìm đường dẫn tồn tại và có thể giải quyết symbolic links theo tùy chọn; phương thức này có thể ném `IOException`. Đừng nhầm ba khái niệm:

- **`normalize()`:** rút gọn đường dẫn theo cú pháp.
- **`toAbsolutePath()`:** tạo đường dẫn tuyệt đối, không yêu cầu file tồn tại.
- **`toRealPath()`:** lấy đường dẫn thực theo khả năng của provider/hệ thống tệp, cần xử lý lỗi I/O.

## 8. Khi nào bắt đầu thao tác hệ thống tệp thật?

Ghép đường dẫn chưa làm xuất hiện file hoặc thư mục mới:

```java
Path root = Path.of("out");
Path output = root.resolve("daily").resolve("report.txt");
```

Muốn **tạo và ghi** thì phải gọi các phương thức `Files`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void writeReport(Path root) throws IOException {
    Path output = root.resolve("daily").resolve("report.txt");

    Files.createDirectories(output.getParent());
    Files.writeString(output, "Kết quả", StandardCharsets.UTF_8);
}
```

Đây là **phương thức minh họa** cần đặt trong class, không phải chương trình độc lập. Trong ví dụ:

1. `resolve` tạo đường dẫn trong bộ nhớ.
2. `Files.createDirectories(...)` mới yêu cầu tạo các thư mục cha cần thiết.
3. `Files.writeString(...)` mới thực sự ghi nội dung; với tùy chọn mặc định, phương thức có thể tạo file mới hoặc **cắt ngắn file đã tồn tại**.

Nếu không được phép ghi đè, có thể truyền tùy chọn phù hợp như `StandardOpenOption.CREATE_NEW` và xử lý `FileAlreadyExistsException`. Không gọi thao tác ghi chỉ để “kiểm tra path”.

Để **đổi tên/move file thực**, cần `Files.move(source, target, ...)`:

```java
Path source = Path.of("reports", "old.csv");
Path target = source.resolveSibling("new.csv");
// Files.move(source, target);  // Chỉ thực thi khi chủ đích di chuyển thật.
```

`resolveSibling` đơn thuần tính toán đích; **`Files.move` mới thực hiện di chuyển**. `Files.move` có thể thất bại do quyền, đích đã tồn tại, khác filesystem hoặc ràng buộc provider; phải xử lý `IOException`.

## 9. Ghép đường dẫn từ đầu vào người dùng: `..` và path traversal

Nếu tên file do người dùng cung cấp, việc gọi `base.resolve(userInput)` **chưa đủ để giới hạn truy cập bên trong `base`**. Ví dụ:

```java
Path base = Path.of("uploads");
Path unsafe = base.resolve("../secrets.txt");
Path normalized = unsafe.normalize();
```

Sau normalize, kết quả có thể **thoát ra ngoài thư mục uploads**. Chỉ vì thao tác đầu tiên là `resolve` không có nghĩa file nằm trong vùng cho phép.

Để kiểm tra đường dẫn về mặt **cú pháp**, một bước thường gặp là:

```java
Path root = Path.of("uploads").toAbsolutePath().normalize();
Path relative = Path.of(userInput); // Chuỗi do người dùng cung cấp.

if (relative.isAbsolute()) {
    throw new IllegalArgumentException("Không chấp nhận đường dẫn tuyệt đối");
}

Path candidate = root.resolve(relative).normalize();
if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Đường dẫn vượt khỏi thư mục cho phép");
}
```

Đây là **đoạn minh họa**, yêu cầu biến `userInput` có sẵn và chạy trong class/phương thức. Kiểm tra `startsWith(Path)` so sánh các **thành phần đường dẫn**, khác với `String.startsWith`: đường dẫn `/data-old` không được xem như nằm dưới `/data` chỉ vì trùng tiền tố ký tự.

**Cảnh báo kỹ thuật:** normalize và startsWith mới chỉ kiểm tra lexical path; symbolic link có thể trỏ ra ngoài, và trạng thái thư mục có thể thay đổi giữa lúc kiểm tra và lúc mở (TOCTOU). Nếu đang triển khai hệ thống xử lý đường dẫn không tin cậy, phải tính đến real path, symlink, quyền truy cập, thao tác mở an toàn theo provider và race. Không coi đoạn trên là bộ kiểm tra bảo mật hoàn chỉnh.

Nếu ứng dụng chỉ cần tên file đơn lẻ, có thể giới hạn rõ thành phần tên (không cho dấu phân tách, `.`, `..` hoặc tên ngoài tập hợp cho phép) trước khi ghép. Chính sách phụ thuộc định dạng và nghiệp vụ.

## 10. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Tự nối đường dẫn bằng `base + "/" + name` | Dễ sai dấu phân tách/kiểu Path và quy tắc provider | `base.resolve(name)` hoặc `Path.of(parts...)` |
| Dùng `file.resolve("new.txt")` để đổi tên cùng cấp | Sẽ coi `file` là vị trí thư mục | `file.resolveSibling("new.txt")` |
| Gọi `file.getParent().resolve("new.txt")` mà không kiểm tra | `getParent()` có thể `null` với path một thành phần | Dùng `resolveSibling` hoặc kiểm tra parent |
| Nghĩ `resolve` tạo file/thư mục | `Path` chỉ là biểu diễn đường dẫn | `Files.createDirectories`/`Files.write*` mới có tác dụng I/O |
| Nghĩ `resolveSibling` đổi tên file thật | Chỉ tính toán đích mới | `Files.move` để thao tác file thực |
| Nghĩ `normalize` kiểm tra tồn tại | Chỉ rút gọn theo cú pháp | `Files.exists` hoặc I/O thật và xử lý ngoại lệ |
| Nghĩ `toAbsolutePath` là canonical/real path | Chỉ tạo biểu diễn tuyệt đối | `toRealPath` khi cần truy vấn đường dẫn thực |
| Xử lý đầu vào tuyệt đối mà không kiểm tra | Có thể bỏ qua/đổi nghĩa gốc dự tính | Kiểm tra `isAbsolute()` và chính sách tên |
| Dùng `String.startsWith` để kiểm tra thư mục gốc | Tiền tố ký tự không phải ranh giới thành phần | Dùng `Path.startsWith` và biện pháp an toàn bổ sung |
| Chỉ normalize để ngăn truy cập ngoài thư mục | Không xử lý đầy đủ symbolic links và race | Xác thực và mở theo chính sách an toàn của hệ thống |
| So sánh string kết quả với dấu `/` cố định | Kém di động giữa hệ điều hành | So sánh `Path` hoặc các thành phần đường dẫn |
| Giả định đuôi `.txt` chứng minh tồn tại/nội dung | Tên file không xác định trạng thái hay format thật | Dùng đúng API metadata và nội dung khi cần |

## 11. Câu hỏi tự kiểm tra

1. **`Path.of("data").resolve("a.txt")` tạo file `a.txt` chưa?** Chưa; chỉ dựng đường dẫn.
2. **Đang có `Path.of("data", "old.txt")`, muốn đường dẫn `data/new.txt` nên dùng gì?** `resolveSibling("new.txt")`.
3. **`Path.of("data", "old.txt").resolve("new.txt")` có cho `data/new.txt` không?** Không; nó ghép thêm thành phần con vào `old.txt`.
4. **Tại sao `resolveSibling` hữu ích với `Path.of("readme.md")`?** Vì trường hợp parent `null` đã có hành vi: trả đường dẫn được truyền vào.
5. **`normalize()` có tạo file hay kiểm tra symlink thật không?** Không; chỉ biến đổi theo cú pháp.
6. **`toAbsolutePath()` có đảm bảo file tồn tại không?** Không.
7. **Muốn tạo file sau khi resolve phải gọi gì?** Một API có tác dụng I/O như `Files.writeString` hoặc `Files.createFile`; nhớ kiểm tra chính sách ghi đè.
8. **`resolveSibling` có thay `Files.move` được không?** Không; nó chỉ tạo đường dẫn đích.
9. **Có thể an toàn tuyệt đối bằng `root.resolve(input).normalize().startsWith(root)` không?** Không; cần xử lý symbolic links, race, quyền và chính sách truy cập.
10. **Muốn ghép các thành phần đường dẫn không phụ thuộc ký tự `/` hay `\` nên chọn cách nào?** `Path.of("a", "b")` hoặc `base.resolve("b")`.

**Quy tắc thực hành:** dùng `Path.of(...)` để khởi tạo đường dẫn từ các thành phần; dùng `resolve(...)` để ghép **đường dẫn con**; dùng `resolveSibling(...)` để ghép **đường dẫn ngang cấp**. Đó đều là thao tác trên biểu diễn đường dẫn; tác dụng tạo/đọc/ghi/di chuyển thật thuộc về các API I/O như `Files`.