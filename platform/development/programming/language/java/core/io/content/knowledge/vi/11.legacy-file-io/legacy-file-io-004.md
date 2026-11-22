# `File.getPath()`, `getAbsolutePath()` và `getCanonicalPath()` trong Java

## 1. Mục tiêu học tập

`java.io.File` là API truyền thống để biểu diễn **tên đường dẫn trừu tượng** (abstract pathname) tới một tệp hoặc thư mục. Khi tạo một đối tượng `File`, Java chưa nhất thiết mở, tạo hay kiểm tra sự tồn tại của tệp trên đĩa. Một đường dẫn có thể là **tương đối**, **tuyệt đối** hoặc được chuyển sang dạng **canonical** theo quy tắc của hệ thống tệp.

Ba phương thức thường gây nhầm lẫn:

- `getPath()`: trả về **chuỗi đường dẫn mà đối tượng `File` đang lưu**.
- `getAbsolutePath()`: trả về **đường dẫn tuyệt đối**, nhưng không bắt buộc xóa `.`, `..` hoặc giải quyết symbolic link.
- `getCanonicalPath()`: chuyển sang **dạng chuẩn tắc theo hệ thống tệp**, thường loại bỏ thành phần dư thừa và giải quyết liên kết tượng trưng khi có thể; có thể ném `IOException`.

Bài học thuộc nhóm **File truyền thống** trong Java Core I/O. Sau bài này, bạn cần biết chính xác ý nghĩa từng phương thức, khả năng phụ thuộc hệ điều hành, vấn đề về file chưa tồn tại, cách so sánh hai đường dẫn và vì sao canonical path **không tự đủ** để bảo vệ ứng dụng trước path traversal hoặc race condition.

> **Ý chính:** `File` biểu diễn *đường dẫn*, không phải tay nắm (handle) gắn bất biến với một file vật lý. Việc chuẩn hóa tên đường dẫn không chứng minh tài nguyên vẫn là cùng một file ở thời điểm sử dụng.

## 2. Khái niệm nền tảng: relative, absolute và canonical

Một đường dẫn tương đối được hiểu dựa trên **thư mục làm việc hiện tại** của quá trình Java. Ví dụ:

```text
Tương đối:             reports/../notes.txt
Thư mục làm việc:      /home/learner
Tuyệt đối (minh họa): /home/learner/reports/../notes.txt
Canonical (minh họa): /home/learner/notes.txt
```

Đây chỉ là minh họa đường dẫn kiểu Unix. Trên Windows, đường dẫn thường dùng dấu `\`, ký hiệu ổ đĩa hoặc UNC; canonical hóa còn có thể thay đổi cách viết hoa/thường của một số thành phần tùy hệ thống tệp và JDK. Không nên viết bài kiểm thử đòi hỏi mọi máy in cùng một chuỗi đường dẫn.

- **Relative pathname:** thiếu thông tin gốc tuyệt đối, cần ngữ cảnh để biết điểm xuất phát.
- **Absolute pathname:** chỉ định vị trí không cần ghép thêm working directory.
- **Canonical pathname:** dạng đại diện chuẩn hóa theo quy tắc hệ thống; có thể phải hỏi hệ thống tệp về symbolic link, định dạng tên và những thành phần đang tồn tại.

Một đường dẫn **tuyệt đối** vẫn có thể chứa `.` hoặc `..`. Vì thế **absolute và canonical không phải từ đồng nghĩa**.

### 2.1. So sánh nhanh ba API

| Phương thức | Kết quả | Có dùng thư mục làm việc khi nguồn tương đối? | Loại bỏ `.` / `..`? | Giải quyết symbolic link? | Checked exception? |
| --- | --- | --- | --- | --- | --- |
| `getPath()` | Chuỗi path đang lưu trong `File` | Không cần để tạo chuỗi trả về | Không được cam kết; có thể có chuẩn hóa dấu phân cách ban đầu | Không | Không |
| `getAbsolutePath()` | Chuỗi path tuyệt đối | Có, khi cần chuyển relative thành absolute | Không được cam kết | Không | Không |
| `getCanonicalPath()` | Chuỗi canonical theo filesystem | Có, nếu nguồn relative | Thường có, theo quy tắc filesystem | Thường có với đường dẫn tồn tại, tùy nền tảng | **`IOException`** |

Điểm đáng nhớ: **không có phương thức nào tự tạo tệp**. Với `new File("missing.txt")`, bạn vẫn có thể lấy `getPath()`, `getAbsolutePath()`; canonical hóa tên chưa tồn tại có thể phụ thuộc tình trạng filesystem và có thể thất bại.

## 3. `getPath()` — tên đường dẫn gắn với đối tượng `File`

Hợp đồng:

```java
public String getPath()
```

Phương thức trả lại chuỗi biểu diễn **abstract pathname của chính đối tượng đó**. Nếu tạo từ tên tương đối, kết quả thường vẫn tương đối; nếu tạo từ tên tuyệt đối, kết quả thường là tuyệt đối.

```java
// Đoạn minh họa, không phải chương trình độc lập.
File relative = new File("reports/../notes.txt");
String raw = relative.getPath();
```

Điều cần hiểu:

1. `getPath()` **không kiểm tra** tệp có tồn tại hay không.
2. Nó không thực hiện thao tác đòi quyền đọc nội dung file.
3. Giá trị có thể giữ thành phần `.` và `..`.
4. Khi khởi tạo `File`, Java có thể chuẩn hóa cách viết dấu phân cách theo nền tảng. Vì thế `getPath()` là path Java đang lưu, không nhất thiết là bản sao từng ký tự chính xác của chuỗi constructor ban đầu.
5. Nếu tên tương đối, việc đổi ngữ cảnh làm việc tại môi trường khác sẽ khiến **cùng chuỗi** trỏ tới nơi khác.

Ví dụ `File f = new File("notes.txt");`: `f.getPath()` là `"notes.txt"`; không phải `"/..."` hay `"C:\..."`. Tên này mô tả *vị trí theo ngữ cảnh*, không nói liệu tài nguyên thật có mặt hay không.

### 3.1. `getPath()` khác `getName()` và `getParent()`

- `getName()` lấy thành phần tên cuối của abstract pathname, ví dụ `"notes.txt"`.
- `getParent()` lấy phần cha ở dạng chuỗi theo pathname đang lưu; với `new File("notes.txt")`, `getParent()` trả `null`.
- `getPath()` trả chuỗi biểu diễn toàn bộ pathname đang lưu, có thể gồm phần cha.

Đừng sử dụng `getName()` để ghép với một root rồi mặc nhiên cho rằng đã kiểm soát được mọi trường hợp đường dẫn không đáng tin. Việc kiểm soát phạm vi filesystem cần xử lý theo mô hình `Path`/quyền truy cập và quy tắc bảo mật phù hợp.

## 4. `getAbsolutePath()` — chuyển thành vị trí tuyệt đối

Hợp đồng:

```java
public String getAbsolutePath()
```

Nếu `File` đang có pathname tuyệt đối, phương thức trả dạng tuyệt đối tương ứng. Nếu pathname tương đối, nó được **giải quyết dựa trên thư mục người dùng hiện tại** của Java (thông thường gắn với thuộc tính hệ thống `user.dir`). Có khác biệt theo nền tảng, nhất là đối với đường dẫn gắn ổ đĩa trên Windows.

Ví dụ khái niệm:

```text
user.dir:         /work/course
File path:        assets/../notes.txt
getPath():        assets/../notes.txt
getAbsolutePath(): /work/course/assets/../notes.txt
```

**Quan trọng:** phần `assets/..` có thể vẫn có mặt trong kết quả tuyệt đối. `getAbsolutePath()` giải quyết **điểm gốc của relative path**; nó không đảm bảo kết quả đã canonical hóa hay kiểm tra symlink.

`File.isAbsolute()` cho biết abstract pathname đã là absolute theo hệ thống tệp hiện tại. `getAbsoluteFile()` trả về một **đối tượng `File`** ở dạng absolute, thay vì `String`. Mọi nhận định về quyền truy cập và tồn tại vẫn cần thao tác kiểm tra riêng.

### 4.1. Đường dẫn tương đối và tính di động

`new File("data/config.txt")` trong chương trình chạy từ thư mục khác có thể trỏ tới file khác. Khi thấy “file không tồn tại” dù dự án chứa `data/config.txt`, trước tiên hãy kiểm tra `System.getProperty("user.dir")` hoặc in giá trị absolute để biết chương trình đang tìm ở đâu.

Tránh giả định directory hiện tại luôn bằng thư mục mã nguồn hoặc thư mục chứa file `.class`/JAR. IDE, Maven/Gradle, container, service manager và script có thể thiết lập working directory khác nhau.

## 5. `getCanonicalPath()` — đường dẫn chuẩn tắc theo filesystem

Hợp đồng:

```java
public String getCanonicalPath() throws IOException
```

Java trước hết chuyển đường dẫn sang dạng tuyệt đối nếu cần, rồi thực hiện canonical hóa theo quy tắc filesystem. Điển hình:

- Bỏ các thành phần dư thừa như `.` và `..` khi có thể.
- Giải quyết symbolic link của các thành phần đường dẫn đang tồn tại (đặc biệt trên Unix).
- Chuẩn hóa một số cách biểu diễn khác nhau của cùng đường dẫn; tùy nền tảng có thể gồm cách viết hoa/thường của drive letter hoặc tên.
- Có thể phát sinh `IOException` vì canonical hóa cần thông tin hệ thống tệp hoặc gặp lỗi.

**Canonical path phụ thuộc trạng thái hệ thống tệp.** Với pathname chưa tồn tại, cách canonical hóa có thể khác với sau khi tệp/thư mục được tạo; không coi kết quả đã được ghi nhớ là bất biến nếu filesystem thay đổi.

### 5.1. `getCanonicalPath()` và `getCanonicalFile()`

`getCanonicalPath()` trả `String`; `getCanonicalFile()` trả một `File` đại diện cho pathname canonical. Cả hai có thể ném `IOException`.

```java
// Đoạn minh họa; file là một File hợp lệ.
String canonicalName = file.getCanonicalPath();
File canonicalFile = file.getCanonicalFile();
```

Chỉ cần chuỗi để hiển thị thì dùng phương thức String; cần tiếp tục làm việc với đối tượng File thì dùng `getCanonicalFile()`. Trong code mới với NIO.2, `Path` và `Files` thường cho phép mô hình hóa thao tác filesystem rõ hơn.

### 5.2. Canonical hóa có đồng nghĩa “file này chắc chắn tồn tại”?

**Không.** API `File.getCanonicalPath()` có thể canonical hóa một pathname chưa tồn tại; trên một số hệ thống hoặc trong một số trạng thái, thao tác có thể lỗi. Canonical pathname không phải bản xác nhận rằng file đã được mở thành công.

Để kiểm tra file có tồn tại, có thể dùng `Files.exists(path)` hoặc `File.exists()` như một phép kiểm tra tại thời điểm gọi. Kết quả vẫn có thể cũ ngay sau đó vì tài nguyên có thể bị tạo, xóa, đổi tên hoặc thay thế đồng thời. Khi thực sự đọc/ghi, hãy xử lý ngoại lệ của chính thao tác đọc/ghi.

## 6. Ví dụ Java 17+ chạy được, không phụ thuộc chuỗi đường dẫn hệ điều hành

Chương trình sau minh họa cả **relative → absolute** và **đường dẫn có `..` → canonical**. Nó tự tạo thư mục tạm, tệp thử và xóa sau khi kiểm tra. Để stdout ổn định trên Windows, macOS và Linux, chương trình in các **kết quả logic** thay vì in toàn bộ đường dẫn tuyệt đối.

Lưu mã bằng UTF-8 với tên **`FilePathFormsDemo.java`**:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePathFormsDemo {
    public static void main(String[] args) throws IOException {
        File relative = new File("notes.txt");

        System.out.println("getPath: " + relative.getPath());
        System.out.println("Relative: " + !relative.isAbsolute());
        System.out.println("Absolute result: "
                + new File(relative.getAbsolutePath()).isAbsolute());

        Path root = Files.createTempDirectory("file-path-demo-");
        Path nested = root.resolve("nested");
        Path direct = root.resolve("lesson.txt");

        try {
            Files.createDirectory(nested);
            Files.writeString(direct, "Java", StandardCharsets.UTF_8);

            File viaParent = nested.resolve("..")
                    .resolve("lesson.txt").toFile();
            File actual = direct.toFile();

            System.out.println("getPath keeps ..: "
                    + viaParent.getPath().contains(".."));
            System.out.println("absolute keeps ..: "
                    + viaParent.getAbsolutePath().contains(".."));
            System.out.println("canonical matches actual: "
                    + viaParent.getCanonicalPath()
                            .equals(actual.getCanonicalPath()));
        } finally {
            Files.deleteIfExists(direct);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 FilePathFormsDemo.java
java FilePathFormsDemo
```

**Stdout dự kiến khi thao tác filesystem thành công:**

```text
getPath: notes.txt
Relative: true
Absolute result: true
getPath keeps ..: true
absolute keeps ..: true
canonical matches actual: true
```

**Giải thích:**

1. `new File("notes.txt")` tạo một pathname tương đối, không cần file `notes.txt` tồn tại.
2. `getPath()` giữ tên đang lưu, ở đây là `notes.txt`; `isAbsolute()` của pathname này là `false`.
3. `getAbsolutePath()` tạo một pathname tuyệt đối theo môi trường đang chạy; chương trình không in chuỗi cụ thể để không phụ thuộc `user.dir`.
4. `viaParent` được tạo qua `nested/../lesson.txt`. `getPath()` và `getAbsolutePath()` vẫn chứa `..` vì không tự canonical hóa.
5. `viaParent.getCanonicalPath()` và `actual.getCanonicalPath()` cùng trỏ tới tệp thử đã tồn tại, nên bằng nhau khi filesystem hoạt động bình thường.
6. `try/finally` dọn tệp và hai thư mục. Lỗi tạo/đọc/xóa file được biểu diễn bằng `IOException`, không bị nuốt.

**Lưu ý về môi trường:** Bài tập chạy trên filesystem thông thường có quyền tạo/xóa tệp. Một filesystem đặc biệt hoặc chính sách quyền hạn có thể khiến thao tác tạo/canonical hóa thất bại; đó là lỗi I/O cần được xử lý chứ không phải bằng chứng rằng canonical hóa luôn giống nhau trên mọi hệ thống.

### 6.1. Vì sao không kiểm tra bằng chuỗi đường dẫn tuyệt đối cố định?

Một bài kiểm thử viết:

```java
// SAI nếu kỳ vọng chạy trên mọi máy:
boolean ok = file.getAbsolutePath()
        .equals("/home/alice/project/notes.txt");
```

không thể portable vì working directory, tên người dùng và ký tự phân cách phụ thuộc môi trường. Khi cần kiểm tra ý nghĩa, hãy so sánh các thuộc tính như `isAbsolute()`, phần tử `Path` và canonical/real path của các nguồn đã xác định rõ, thay vì so với tên máy người viết ví dụ.

## 7. Những điểm khác nhau trên Windows, Linux và macOS

### 7.1. Dấu phân cách

- Unix/macOS thông thường dùng `/`.
- Windows thường hiển thị `\` và có thể có drive letter hoặc đường dẫn UNC.
- `File.separator` hoặc `Path.resolve(...)` giúp ghép path mà không phụ thuộc vào việc tự chèn dấu phân cách.

Nên dùng `new File(parent, child)` hoặc `Path.resolve(...)`, thay vì ghép chuỗi thủ công `parent + "/" + child` cho mọi đường dẫn.

### 7.2. Phân biệt hoa/thường

Một số filesystem phân biệt hoa/thường, một số không, và quy tắc có thể thay đổi theo volume/cấu hình. `getCanonicalPath()` có thể chuẩn hóa một số khác biệt nhưng **đừng coi kết quả string-equality là bài kiểm tra identity đáng tin cho mọi filesystem và mọi thời điểm**. Nếu hai file đang tồn tại, `Files.isSameFile(path1, path2)` biểu đạt trực tiếp câu hỏi “hai Path này có chỉ tới cùng một file không?”, song thao tác có thể truy cập filesystem và ném `IOException`.

### 7.3. Symlink và đường dẫn chưa tồn tại

- `getAbsolutePath()` không có hợp đồng giải quyết symlink.
- `getCanonicalPath()` thường giải quyết symlink của thành phần tồn tại nhưng chi tiết phụ thuộc platform.
- Nếu muốn **đường dẫn thực của một file đang tồn tại** với NIO.2, `Path.toRealPath()` có hợp đồng rõ ràng hơn: mặc định yêu cầu đường dẫn tồn tại và xử lý symbolic link; dùng `LinkOption.NOFOLLOW_LINKS` khi bài toán yêu cầu semantics khác.
- Với file chưa tồn tại, `toRealPath()` thường ném `NoSuchFileException`, còn `getCanonicalPath()` có thể vẫn trả canonical pathname dự kiến.

Không tự cho rằng cùng pathname canonical hôm nay chắc chắn trỏ tới cùng tài nguyên ngày mai khi symlink, mount hoặc file bị thay thế.

## 8. So sánh với `java.nio.file.Path` và `Files`

NIO.2 từ Java 7 cung cấp `Path` và `Files` với API rõ ràng cho các thao tác đường dẫn và filesystem.

| Nhu cầu | `java.io.File` | NIO.2 |
| --- | --- | --- |
| Chuỗi path hiện tại | `file.getPath()` | `path.toString()` |
| Chuyển thành absolute | `file.getAbsolutePath()` | `path.toAbsolutePath()` |
| Chuẩn hóa cú pháp `.`, `..` | Không có phương thức riêng tương đương | `path.normalize()` |
| Canonical hóa có tương tác filesystem | `file.getCanonicalPath()` | `path.toRealPath()` cho path tồn tại; semantics khác với File canonical |
| Kiểm tra tồn tại | `file.exists()` | `Files.exists(path)` |
| Kiểm tra hai path có chỉ tới cùng file | Không nên chỉ so `getPath()` | `Files.isSameFile(a, b)` |
| Đọc/ghi file | Các lớp stream truyền thống hoặc method File hạn chế | `Files.newInputStream`, `Files.readString`, `Files.writeString`, ... |
| Đổi `File` ↔ `Path` | `file.toPath()` | `path.toFile()` khi provider hỗ trợ |

Cần phân biệt kỹ:

- `Path.normalize()` là **chuẩn hóa cú pháp**, loại bỏ thành phần dư thừa mà không yêu cầu file tồn tại; nó không xác nhận quyền truy cập hoặc đường dẫn thật.
- `Path.toAbsolutePath()` tạo absolute path và không mặc nhiên giải quyết symbolic link.
- `Path.toRealPath()` tương tác filesystem, thường yêu cầu file tồn tại và có thể ném `IOException`.
- `File.getCanonicalPath()` cũng có thể truy cập filesystem nhưng **không thể coi là phép thay thế chính xác cho `toRealPath()` trong mọi trường hợp**, đặc biệt khi file chưa tồn tại và khi có `NOFOLLOW_LINKS`.

### 8.1. Ví dụ ngắn với `Path.normalize()`

```java
// Đoạn minh họa không phụ thuộc filesystem tồn tại.
Path p = Path.of("reports", "..", "notes.txt");
Path cleaned = p.normalize();

System.out.println(cleaned.equals(Path.of("notes.txt"))); // true
System.out.println(p.toAbsolutePath().isAbsolute());       // true
```

Đoạn mã này cần `import java.nio.file.Path;` trong chương trình chạy đầy đủ. `normalize()` chỉ xử lý chuỗi thành phần; nó không kiểm tra `reports` có tồn tại hay là symlink. Do đó `p.normalize()` và `p.toRealPath()` có thể cho kết quả khác hoặc `toRealPath()` có thể lỗi.

### 8.2. Chọn API nào trong code mới?

- Nếu mã cũ dùng `File`, hiểu ba phương thức này giúp debug và tương tác với thư viện cũ.
- Nếu cần duyệt thư mục, đọc/ghi nội dung, thuộc tính, symlink, copy/move hoặc kiểm soát mở file, ưu tiên các API `Path`/`Files` có hợp đồng thao tác rõ ràng.
- Nếu chỉ muốn hiển thị vị trí tham chiếu, `getAbsolutePath()` hoặc `toAbsolutePath()` thường đủ.
- Nếu cần đối chiếu các đường dẫn trỏ tới cùng file đã tồn tại, xem `Files.isSameFile(...)` hoặc `toRealPath()` theo semantics phù hợp.

## 9. Canonical path và an toàn đường dẫn

Canonical hóa hữu ích để phát hiện một số cách viết khác nhau như `a/../b`, nhưng **không tự tạo một ranh giới bảo mật hoàn chỉnh** khi đường dẫn đến từ người dùng.

### 9.1. Cảnh giác path traversal

Giả sử ứng dụng chỉ cho đọc bên dưới thư mục dữ liệu, nhưng người dùng gửi `../secret.txt`. Việc nối chuỗi rồi kiểm tra bằng:

```java
// Ví dụ SAI: so sánh tiền tố chuỗi dễ gây nhầm lẫn.
if (candidatePath.startsWith(allowedRootString)) {
    // ...
}
```

có thể sai với đường dẫn như `/srv/data-backup` khi root là `/srv/data`. Cần so sánh **thành phần path**, không phải tiền tố chuỗi tùy ý, và xử lý symlink/đường dẫn đích thật theo mô hình tin cậy.

Một lớp kiểm tra cú pháp sơ bộ với `Path`:

```java
// Minh họa; root là Path đã xác định, userName do caller cung cấp.
Path normalizedRoot = root.toAbsolutePath().normalize();
Path candidate = normalizedRoot.resolve(userName).normalize();
if (!candidate.startsWith(normalizedRoot)) {
    throw new SecurityException("Path outside allowed directory");
}
```

Đoạn này **chỉ phát hiện việc thoát khỏi root theo cú pháp**; nó chưa đủ để chống symlink và các thay đổi filesystem đồng thời. Nếu một thành phần bên trong root là symbolic link trỏ ra ngoài, kiểm tra lexical `startsWith` vẫn có thể cho kết quả cho phép.

### 9.2. Race condition (TOCTOU)

Chuỗi thao tác nguy hiểm:

1. Canonical hóa candidate và kiểm tra nó thuộc root.
2. Một tiến trình khác thay đổi symlink hoặc đổi tên một thành phần đường dẫn.
3. Chương trình mở file bằng pathname cũ.
4. Tệp thực tế được mở có thể khác tệp đã kiểm tra.

Vì vậy, ứng dụng xử lý path không đáng tin không thể dựa **chỉ** vào `getCanonicalPath()` rồi dùng lại chuỗi như một quyền truy cập bất biến. Tùy môi trường, cân nhắc dùng xử lý dựa trên file handle/descriptor và các API mở file an toàn có hỗ trợ của filesystem; `SecureDirectoryStream` là một khả năng NIO.2 khi provider hỗ trợ. Luôn xác định root tin cậy, quyền đọc/ghi và chính sách symbolic link; không cố “chữa” race chỉ bằng `normalize()`.

### 9.3. So sánh bằng `String.equals` có đủ không?

Cùng một file có thể có nhiều tên do hard link, symlink, mount hoặc chính sách filesystem. `getCanonicalPath().equals(...)` có ích ở nhiều trường hợp, nhưng không phải phép thử file identity tổng quát. Với path tồn tại, `Files.isSameFile(...)` thường phù hợp hơn. Tuy vậy, bất kỳ kết quả kiểm tra nào cũng có giới hạn thời điểm nếu tài nguyên bị thay đổi đồng thời.

## 10. Lỗi phổ biến khi sử dụng ba phương thức

1. **Nghĩ `getPath()` luôn trả absolute:** nó có thể vẫn relative.
2. **Nghĩ `getAbsolutePath()` xóa `..`:** absolute không đồng nghĩa canonical.
3. **Nghĩ `getCanonicalPath()` chỉ là xử lý chuỗi:** nó có thể cần filesystem và ném `IOException`.
4. **Bỏ qua `IOException`:** dùng canonical hóa trong code đọc/ghi phải có chính sách xử lý lỗi đúng tầng.
5. **Nghĩ gọi `new File(...)` là đã tạo tệp:** đây mới là đối tượng pathname.
6. **Cho rằng canonical path chứng minh file tồn tại:** đối tượng/path có thể được canonical hóa dù tệp chưa tồn tại.
7. **Cho rằng hai chuỗi absolute bằng nhau mới cùng một file:** symlink/hard link và quy tắc filesystem có thể làm phức tạp identity.
8. **Dựa vào đường dẫn kiểu Unix cho mọi OS:** dấu phân cách, drive letter, UNC và quy tắc tên khác nhau.
9. **Dùng `System.getProperty("user.dir")` như một hằng số nội tại của project:** working directory do môi trường chạy quyết định.
10. **Ghép chuỗi `parent + "/" + name` tràn lan:** dùng `Path.resolve` hoặc constructor cha/con để tránh lỗi phân cách.
11. **Dùng `normalize()` làm kiểm tra an toàn đủ:** symlink/TOCTOU không được giải quyết bởi thao tác lexical.
12. **So `startsWith` trên chuỗi:** `"/data2"` có thể bị nhầm là con của `"/data"`; khi kiểm tra containment, dùng đối tượng `Path` và thêm kiểm soát filesystem phù hợp.
13. **Tin kết quả kiểm tra sẽ đúng mãi:** symlink, tệp và directory có thể thay đổi sau khi kiểm tra.
14. **Dùng `getCanonicalPath()` để xác định nội dung tệp:** canonical hóa giải quyết tên, không đọc hay xác minh byte nội dung.
15. **Nhầm `File` với `FileInputStream`:** `File` tự nó không phải luồng dữ liệu đang mở.

## 11. Checklist chọn phương thức

| Bạn cần làm gì? | Lựa chọn khởi đầu |
| --- | --- |
| Hiển thị tên đường dẫn mà đối tượng `File` đang lưu | `getPath()` |
| Debug chương trình đang tìm file relative tại đâu | `getAbsolutePath()` và kiểm tra working directory |
| Loại bỏ thành phần `.` / `..` trong path một cách **thuần cú pháp** | `Path.normalize()` |
| Lấy canonical pathname theo semantics `File` | `getCanonicalPath()`, xử lý `IOException` |
| Xác định real path của một file đã tồn tại | `Path.toRealPath()` |
| Kiểm tra hai path trỏ cùng file hiện hữu | `Files.isSameFile(...)` |
| Chỉ kiểm tra sự tồn tại tại thời điểm gọi | `Files.exists(...)` hoặc `File.exists()`, sau đó vẫn xử lý lỗi khi dùng |
| Xử lý đường dẫn từ input không đáng tin | Kiểm tra cấu trúc path, root cho phép, symlink, permissions và TOCTOU; không chỉ canonical hóa |

## 12. Bài tập tự đánh giá

1. **Relative → absolute:** tạo `new File("docs/notes.txt")` và in `getPath()`, `getAbsolutePath()`. Giải thích kết quả khác nhau thế nào khi chạy ở hai working directory.
2. **Canonical:** tạo file thật ở `temp/nested/../notes.txt` (thư mục `nested` tồn tại), so sánh `getAbsolutePath()` và `getCanonicalPath()`. Chỉ ra thành phần `..` trong mỗi kết quả.
3. **File chưa tồn tại:** tạo `new File("missing.txt")` (không cần tạo tệp trên đĩa), lấy `getPath()` và `getAbsolutePath()`. `getCanonicalPath()` có luôn chứng minh file tồn tại không?
4. **So sánh path:** xem `Path.of("/srv/data-backup")` có là con của `Path.of("/srv/data")` không (trên hệ Unix minh họa). Vì sao so sánh `String.startsWith` có thể gây sai?
5. **Symlink:** nếu môi trường cho phép, tạo symlink `shortcut` trỏ đến thư mục thật rồi so sánh absolute/canonical/real path. Giải thích điều gì thay đổi khi sửa đích symlink.
6. **NIO.2:** viết lại thao tác `getAbsolutePath()` bằng `Path.toAbsolutePath()` và một ví dụ chuẩn hóa cú pháp bằng `normalize()`.
7. **Kiểm thử đa nền tảng:** thay các assertion phụ thuộc `"/home/..."` bằng assertion mang ý nghĩa logic để ví dụ chạy được trên Windows/macOS/Linux.
8. **Phân tích bảo mật:** tại sao việc kiểm tra canonical path nằm trong root rồi vài giây sau mới mở file vẫn có nguy cơ với filesystem có writer khác?

**Tiêu chí hoàn thành:** Bạn có thể trả lời chính xác **“Path đang lưu?” → `getPath()`**, **“Absolute từ relative?” → `getAbsolutePath()`**, **“Canonical theo filesystem?” → `getCanonicalPath()`**; đồng thời phân biệt được canonical với thao tác thuần cú pháp `Path.normalize()` và hiểu giới hạn của một phép kiểm tra pathname đối với tài nguyên có thể thay đổi.