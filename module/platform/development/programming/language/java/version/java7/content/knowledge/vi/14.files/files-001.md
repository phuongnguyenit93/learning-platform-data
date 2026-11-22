# Java 7 — Files: Tạo tệp, thư mục và các thư mục cha

## Mục tiêu và phạm vi

Khi làm việc với Java NIO.2, bạn có thể có một `Path` biểu diễn `reports/2026/summary.txt` nhưng điều đó **không có nghĩa** tệp đã tồn tại. Muốn tạo một **tệp trống**, một **thư mục đơn** hoặc **toàn bộ cây thư mục cha còn thiếu**, cần gọi đúng các phương thức của `java.nio.file.Files`.

Ba phương thức trung tâm, đã có từ Java 7 và **vẫn đang được sử dụng trên Java 17+**, là:

- `Files.createFile(Path file)` — tạo **một tệp mới, ban đầu rỗng**. Nếu mục đích đã tồn tại thì báo lỗi; phương thức **không tự tạo thư mục cha**.
- `Files.createDirectory(Path dir)` — tạo **một thư mục mới ở một cấp**. Thư mục cha cần tồn tại và mục đích chưa được chiếm bởi một mục khác.
- `Files.createDirectories(Path dir)` — tạo **thư mục đích và các thư mục cha còn thiếu**. Nếu thư mục đích đã tồn tại đúng nghĩa là thư mục, phương thức có thể hoàn tất bình thường.

Cú pháp gần giống nhau, nhưng **hợp đồng khi đối tượng đã tồn tại, khi thiếu thư mục cha và khi một bước tạo thất bại rất khác nhau**. Ngoài ra, việc tạo tệp trống không đồng nghĩa việc ghi dữ liệu vào tệp; nhiều ứng dụng muốn viết nội dung ngay khi tạo sẽ chọn `Files.write`, `Files.newBufferedWriter` hoặc `Files.writeString` với lựa chọn mở phù hợp.

Sau bài này, bạn sẽ biết:

1. Phân biệt `Path` (đường dẫn) với file/directory thật.
2. Chọn đúng `createFile`, `createDirectory` hay `createDirectories` theo mục tiêu.
3. Xử lý `FileAlreadyExistsException`, thư mục cha thiếu, thiếu quyền và xung đột file/directory.
4. Giải thích vì sao `createFile` là thao tác **check-and-create nguyên tử** theo hợp đồng, còn `createDirectories` không là một transaction nguyên tử cho toàn bộ cây.
5. Tạo thư mục cha trước khi ghi file, tránh việc mở file làm mất nội dung hiện có.
6. Dùng `CREATE_NEW`, `CREATE` và `TRUNCATE_EXISTING` đúng mục đích.
7. Tạo tài nguyên tạm bằng `Files.createTempFile` và `Files.createTempDirectory` rồi dọn dẹp đúng phạm vi.
8. Hiểu quan hệ giữa relative path, working directory, tính di động và quyền truy cập filesystem.
9. Đánh giá rủi ro path traversal, symlink, TOCTOU và việc cấp quyền tạo file khi input đến từ bên ngoài.
10. Kiểm thử đường thành công và các đường lỗi với thư mục tạm thay vì sửa tệp thật của dự án.

Các chương trình hoàn chỉnh trong bài đều biên dịch với **`javac --release 17 -encoding UTF-8`** và đã chạy thử trên một hệ thống Windows/JDK hiện đại. Những tiện ích xuất hiện sau Java 7 được **ghi rõ phiên bản**, không được mô tả sai là đã có ở Java 7.

## 1. Một Path không phải thao tác tạo tài nguyên

`Path` được đưa vào NIO.2 để biểu diễn địa chỉ trong một file system. Ví dụ:

```java
Path file = Paths.get("reports", "2026", "summary.txt");
Path dir = file.getParent();
```

Đây là **đoạn mã minh họa**, cần import `java.nio.file.Path` và `java.nio.file.Paths`. Nó chỉ tạo hai đối tượng biểu diễn đường dẫn, **chưa tạo file hay directory trên đĩa**.

- `Paths.get(...)` xây dựng `Path` theo filesystem mặc định.
- `Path.getParent()` trả về đường dẫn thư mục cha **về mặt cú pháp**; không kiểm tra thư mục có tồn tại.
- `Files.createFile(file)` thực sự yêu cầu hệ thống tệp tạo một tệp mới.
- `Files.createDirectory(dir)` thực sự yêu cầu tạo một thư mục.
- `Files.createDirectories(dir)` có thể tạo nhiều thư mục theo chuỗi cha → con.

`Path.of(...)` là một factory tiện dụng cũng được dùng rộng rãi trên Java hiện đại, nhưng nó được bổ sung từ **Java 11**. Nếu học đúng phần NIO.2 từ Java 7, `Paths.get(...)` là lựa chọn phản ánh cú pháp gốc. Cả hai hoạt động tốt khi biên dịch với `--release 17`.

### 1.1. Tệp và thư mục đều là filesystem entries

Một tên như `"report.txt"` **không buộc** đối tượng được tạo là regular file chỉ vì đuôi `.txt`. Chính phương thức tạo quyết định loại mục:

- `Files.createFile(path)` yêu cầu tạo regular file.
- `Files.createDirectory(path)` yêu cầu tạo directory.
- `Files.createDirectories(path)` yêu cầu tạo directory và các directory cha còn thiếu.

Mặc dù có thể chọn tên đuôi `.txt` cho directory, điều đó không biến nó thành regular file. Ngược lại, `createFile` không thể tạo được một regular file mới tại path đã có directory cùng tên.

### 1.2. Java cung cấp IOException, không phải boolean thành/bại kiểu cũ

Các phương thức tạo của `Files` trả về `Path` đại diện mục vừa tạo/được yêu cầu tạo, và sử dụng **checked `IOException`** hoặc các ngoại lệ liên quan khi không thể hoàn thành. Đừng diễn giải chúng như API trả `true`/`false`; ví dụ:

```java
try {
    Files.createFile(path);
} catch (FileAlreadyExistsException e) {
    // Một mục đích đã tồn tại; xử lý theo contract ứng dụng.
}
```

Đây là **mảnh minh họa**: cần định nghĩa `path`, import `Files`/`FileAlreadyExistsException`, và xử lý các `IOException` khác tại nơi phù hợp. `FileAlreadyExistsException` là một loại con của `IOException`, không phải tên trạng thái boolean.

## 2. Bảng quyết định nhanh

| Nhu cầu | API phù hợp | Thiếu thư mục cha? | Đích đã tồn tại? |
| --- | --- | --- | --- |
| Tạo một regular file **rỗng**, phải mới | `Files.createFile(file)` | Lỗi, không tạo cha | Lỗi, thường `FileAlreadyExistsException` |
| Tạo một directory **duy nhất**, phải mới | `Files.createDirectory(dir)` | Lỗi, không tạo cha | Lỗi nếu mục đã tồn tại |
| Đảm bảo có cây directory cha và directory đích | `Files.createDirectories(dir)` | Tự tạo các cha còn thiếu | Không lỗi chỉ vì directory đích đã tồn tại |
| Tạo file **mới và ghi text**, không ghi đè | `Files.writeString(file, text, UTF_8, CREATE_NEW, WRITE)` | Lỗi nếu cha chưa có | Lỗi khi đã tồn tại |
| Tạo/mở file để ghi, chấp nhận cập nhật theo contract | `Files.write` / `newBufferedWriter` và option phù hợp | Cần cha đã tồn tại | Phụ thuộc `CREATE`, `TRUNCATE_EXISTING`, `APPEND`... |
| Tạo tên tệp tạm mới do hệ thống chọn | `Files.createTempFile(...)` | Thư mục chứa phải hợp lệ | API chọn tên mới, tránh trùng theo contract |
| Tạo thư mục tạm mới do hệ thống chọn | `Files.createTempDirectory(...)` | Thư mục chứa phải hợp lệ | API chọn tên mới |

**Điểm nhấn:** `createDirectories` **không** tạo file cuối. Nếu `target` là `data/reports/summary.txt`, đừng truyền cả `target` cho `createDirectories` rồi mong có file; nó sẽ cố tạo **một directory tên `summary.txt`**.

## 3. `Files.createFile` — tạo tệp trống, không ghi đè

Dạng API:

```java
Path created = Files.createFile(file);
```

Đây là đoạn minh họa cần `Path file` đã được tạo và import `Files`.

Những bảo đảm thiết yếu của `createFile`:

- Khi thành công, tạo **regular file mới ban đầu rỗng**.
- Nếu một mục cùng tên đã tồn tại, thao tác thất bại thay vì xóa hoặc ghi đè nội dung cũ.
- **Kiểm tra sự tồn tại và tạo mục mới là một thao tác nguyên tử** đối với các hoạt động filesystem liên quan, theo hợp đồng Java và khả năng provider.
- Nó **không** tìm và tạo mọi directory cha.
- Có overload `FileAttribute<?>... attrs` cho phép yêu cầu thiết lập thuộc tính ban đầu trong lúc tạo; hỗ trợ thuộc tính phụ thuộc provider.
- Không tự ghi dòng văn bản nào; dung lượng ban đầu của regular file trong ví dụ là 0 byte.

### 3.1. Vì sao “kiểm tra trước rồi mới tạo” không tương đương?

Đoạn sau có race:

```java
if (Files.notExists(file)) {
    Files.createFile(file);
}
```

Đây là **mảnh minh họa không nên dùng làm giao thức tránh trùng**. Giữa `notExists` và `createFile`, một luồng/process khác vẫn có thể tạo mục cùng tên. `Files.createFile` đã thực hiện check-and-create có tính nguyên tử, nên khi cần “chỉ tạo nếu chưa tồn tại”, thường **thử tạo thẳng rồi xử lý ngoại lệ** tốt hơn việc coi một phép hỏi trước là bảo đảm chắc chắn.

Đây cũng không phải phép khóa file tổng quát. Tạo một file đánh dấu rồi dùng tên ấy như giao thức khóa có thể dẫn đến file còn sót khi ứng dụng crash hoặc xử lý race phức tạp. Nếu cần locking, nghiên cứu cơ chế khóa chuyên dụng như `FileChannel.lock` theo yêu cầu cụ thể.

### 3.2. Chương trình A: `CreateFileDemo.java`

```java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CreateFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-create-file-");
        Path file = root.resolve("note.txt");
        Path parent = root.resolve("missing");
        Path nested = parent.resolve("child.txt");

        try {
            Files.createFile(file);
            System.out.println("created=" + Files.isRegularFile(file));
            System.out.println("sizeZero=" + (Files.size(file) == 0));

            try {
                Files.createFile(file);
                System.out.println("duplicate=unexpected");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("duplicate=FileAlreadyExistsException");
            }

            try {
                Files.createFile(nested);
                System.out.println("missingParent=unexpected");
            } catch (IOException ex) {
                System.out.println("missingParentRejected=true");
            }

            Files.createDirectories(parent);
            Files.createFile(nested);
            System.out.println("nestedCreated=" + Files.isRegularFile(nested));
        } finally {
            Files.deleteIfExists(nested);
            Files.deleteIfExists(parent);
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 CreateFileDemo.java
java CreateFileDemo
```

**Stdout đã kiểm chứng:**

```text
created=true
sizeZero=true
duplicate=FileAlreadyExistsException
missingParentRejected=true
nestedCreated=true
```

### 3.3. Giải thích kết quả

1. `Files.createTempDirectory` tạo một **directory thật** với tên tạm duy nhất theo API; chương trình chỉ thao tác bên trong đó.
2. `Files.createFile(file)` tạo `note.txt` và `Files.isRegularFile(file)` trả true.
3. `Files.size(file)==0` cho biết tệp ban đầu rỗng.
4. Lần gọi `createFile(file)` thứ hai bị từ chối với `FileAlreadyExistsException` trong filesystem kiểm thử.
5. `nested` có cha `missing` chưa tồn tại. `createFile(nested)` không tạo cha; chương trình bắt `IOException` và in kết quả chung để tránh phụ thuộc tên subtype của provider.
6. Sau khi `Files.createDirectories(parent)`, lời gọi `createFile(nested)` thành công.
7. `finally` dọn đúng những mục mà ví dụ đã tạo theo thứ tự con trước, cha sau.

**Ghi nhớ:** `catch (IOException)` ở chỗ thử mục không có cha là dùng để làm ví dụ dễ chuyển giữa filesystem providers. Trong code sản phẩm, đừng bắt mọi `IOException` rồi bỏ qua vì một lỗi permission, quota hoặc I/O khác cần xử lý theo contract.

## 4. `Files.createDirectory` — chỉ tạo một directory cấp hiện tại

Nếu bạn cần **một thư mục mới** và biết chắc directory cha đã có, dùng:

```java
Files.createDirectory(path);
```

Lời gọi không đi lên tạo toàn bộ các cha chưa có. Nó cũng không trở thành no-op khi chính directory đích đã tồn tại: đó là điểm khác với `Files.createDirectories`.

Những câu hỏi cần xác định:

- Directory cha đã tồn tại chưa?
- Path đích đã bị file, directory hoặc mục khác chiếm chưa?
- Có quyền tạo directory dưới cha không?
- Có cần đặt file attributes khi tạo không?
- Ứng dụng có muốn **báo lỗi nếu directory đã tồn tại**, hay chỉ muốn **đảm bảo directory hiện hữu**?

Nếu yêu cầu là “tạo mới, fail nếu tồn tại”, `createDirectory` phù hợp. Nếu là “đảm bảo cấu trúc thư mục được thiết lập”, thường `createDirectories` phù hợp hơn.

### 4.1. Chương trình B: `CreateDirectoryDemo.java`

```java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CreateDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-create-dir-");
        Path single = root.resolve("single");
        Path nested = root.resolve("new-parent").resolve("child");

        try {
            Files.createDirectory(single);
            System.out.println("singleCreated=" + Files.isDirectory(single));

            try {
                Files.createDirectory(single);
                System.out.println("duplicate=unexpected");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("duplicate=FileAlreadyExistsException");
            }

            try {
                Files.createDirectory(nested);
                System.out.println("missingParent=unexpected");
            } catch (IOException ex) {
                System.out.println("missingParentRejected=true");
            }

            System.out.println("parentAutoCreated=" +
                    Files.exists(nested.getParent()));
            Files.createDirectory(nested.getParent());
            Files.createDirectory(nested);
            System.out.println("manualHierarchyCreated=" +
                    Files.isDirectory(nested));
        } finally {
            Files.deleteIfExists(nested);
            Files.deleteIfExists(nested.getParent());
            Files.deleteIfExists(single);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CreateDirectoryDemo.java
java CreateDirectoryDemo
```

**Stdout đã kiểm chứng:**

```text
singleCreated=true
duplicate=FileAlreadyExistsException
missingParentRejected=true
parentAutoCreated=false
manualHierarchyCreated=true
```

### 4.2. Phân tích

- `singleCreated=true` cho thấy `Files.createDirectory(single)` đã tạo directory.
- Gọi lại với cùng path nhận `FileAlreadyExistsException` trên provider thử.
- `nested` có parent `new-parent` chưa có, nên lần `createDirectory(nested)` đầu thất bại.
- `parentAutoCreated=false` xác nhận method một cấp **không tạo thư mục cha**.
- Sau khi tạo `new-parent` trước, tạo `child` thành công.

### 4.3. Khi nào không cần gọi một cấp?

Với một cấu trúc nhiều cấp, tự viết vòng lặp lần lượt tạo `a`, `b`, `c` vừa dài vừa phải xử lý tình trạng directory đã tồn tại từng cấp. `Files.createDirectories` được thiết kế cho yêu cầu đó. Tuy nhiên, nó có semantics **không fail khi đích đã là directory**, vì vậy nếu contract phải bảo đảm directory là *hoàn toàn mới*, đừng thay `createDirectory` bằng `createDirectories` mà không xét thay đổi hành vi.

## 5. `Files.createDirectories` — tạo các thư mục cha còn thiếu

Ví dụ:

```java
Path folder = Paths.get("data", "reports", "2026");
Files.createDirectories(folder);
```

Đây là mảnh minh họa, cần import `Path`, `Paths` và `Files` cùng xử lý `IOException`.

Nếu cần tạo lần lượt `data`, `data/reports` rồi `data/reports/2026`, `Files.createDirectories(folder)` yêu cầu tạo các directory còn thiếu. Các directory cha đã tồn tại **không cần tạo lại**.

Khác biệt chủ chốt:

- **Idempotent về mục tiêu tạo cây directory:** gọi lặp khi directory đã có không bị lỗi chỉ vì nó đã có.
- Nếu một thành phần cần đi qua **regular file** thay vì directory, việc tạo con bên dưới đó sẽ thất bại.
- Nếu bị lỗi giữa chừng, **có thể đã tạo được một vài directory cha** rồi mới thất bại. Đây **không** phải transaction “tất cả hoặc không gì cả”.
- Mục đích phải là directory; method này không sinh regular file.
- `FileAttribute<?>... attrs` áp dụng cho các directory được tạo mới theo hợp đồng, không phải công cụ tự động thay quyền mọi directory cũ đã có.
- Không bảo đảm cuối cùng bạn có toàn quyền đọc/ghi file trong directory; permission, ACL, mount và trạng thái filesystem còn quyết định.

### 5.1. Chương trình C: `CreateDirectoriesDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CreateDirectoriesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-many-dirs-");
        Path first = root.resolve("a");
        Path second = first.resolve("b");
        Path third = second.resolve("c");
        Path blocker = root.resolve("blocker");

        try {
            Files.createDirectories(third);
            System.out.println("allParentsExist=" +
                    (Files.isDirectory(first)
                    && Files.isDirectory(second)
                    && Files.isDirectory(third)));

            Files.createDirectories(third);
            System.out.println("repeatedCallWorks=" +
                    Files.isDirectory(third));

            Files.createFile(blocker);
            try {
                Files.createDirectories(blocker.resolve("child"));
                System.out.println("fileAsParent=unexpected");
            } catch (IOException ex) {
                System.out.println("fileAsParentRejected=true");
            }

            System.out.println("blockerStillFile=" +
                    Files.isRegularFile(blocker));
        } finally {
            Files.deleteIfExists(blocker);
            Files.deleteIfExists(third);
            Files.deleteIfExists(second);
            Files.deleteIfExists(first);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CreateDirectoriesDemo.java
java CreateDirectoriesDemo
```

Output:

```text
allParentsExist=true
repeatedCallWorks=true
fileAsParentRejected=true
blockerStillFile=true
```

### 5.2. Giải thích

1. `third` biểu diễn `root/a/b/c`. `Files.createDirectories(third)` tạo đủ ba directory con còn thiếu.
2. Lần gọi thứ hai không lỗi chỉ vì `c` đã tồn tại.
3. `blocker` được tạo dưới dạng **regular file**.
4. `blocker.resolve("child")` là một `Path` hợp lệ về mặt mô tả, nhưng filesystem không thể tạo directory bên dưới một regular file đang tồn tại.
5. Chương trình bắt `IOException` và in `fileAsParentRejected=true`. Subtype thông báo có thể khác theo provider; không dựa vào một loại exception cụ thể cho mọi môi trường.
6. `blockerStillFile=true`: thao tác lỗi không tự biến regular file thành directory.

### 5.3. Idempotent không đồng nghĩa an toàn trước mọi input

Nếu path `data/reports/2026` thực sự là **directory** đã tồn tại, `createDirectories` có thể hoàn tất bình thường. Nhưng:

- Nếu `data` là một **file** bình thường, việc tạo `data/reports` thất bại.
- Nếu không có quyền tạo mục dưới `data`, thất bại dù path được viết đúng.
- Nếu `2026` đã là regular file, không phải directory, thao tác không thể coi “tồn tại rồi” là thành công.
- Nếu một phần được tạo rồi gặp lỗi, application cần quyết định có giữ phần đã tạo hay cleanup phần **mình thực sự sở hữu**.
- Nếu nhiều luồng/process cùng làm việc, những directory khác có thể xuất hiện giữa các bước; xử lý lỗi filesystem đúng thay vì giả định snapshot cố định.

### 5.4. Cẩn thận với `getParent()`

Mẫu tạo file cùng thư mục cha:

```java
Path target = Paths.get("data", "reports", "summary.txt");
Path parent = target.getParent();
if (parent != null) {
    Files.createDirectories(parent);
}
Files.createFile(target);
```

Đây là **mảnh minh họa**, không phải chương trình hoàn chỉnh. `getParent()` có thể là `null` nếu path chỉ là một tên như `"note.txt"`. Với mục tiêu tạo file trong working directory hiện tại, không có lý do bắt buộc tạo “parent null”. Đừng gọi `Files.createDirectories(target)` vì điều đó sẽ tạo **directory tên `summary.txt`** thay vì regular file.

**Lưu ý concurrency:** Mẫu trên đảm bảo cha hiện hữu ở thời điểm tạo nhưng không chống mọi thay đổi filesystem giữa hai thao tác, đặc biệt khi thư mục do bên thứ ba kiểm soát. Với input không tin cậy, xét thêm biện pháp filesystem-level security.

## 6. Tạo tệp rỗng khác với tạo và ghi nội dung

Một sự nhầm lẫn thường gặp:

```java
Files.createFile(file);
```

Lời gọi tạo **file rỗng**. Nó **không** viết `"Hello"`, không tự mở text writer. Nếu muốn ghi nội dung, cần một thao tác khác. Với Java hiện đại, ví dụ:

```java
Files.writeString(file, "Hello", StandardCharsets.UTF_8);
```

Đây là **mảnh minh họa**, cần `file`, import `Files`/`StandardCharsets` và xử lý `IOException`. `Files.writeString` xuất hiện từ **Java 11**, chứ **không phải** Java 7. Với Java 7, có thể dùng `Files.write(Path, byte[], OpenOption...)` hoặc `Files.newBufferedWriter(...)`; các API đó vẫn dùng tốt trên Java 17+.

Không phải tình huống nào cũng cần `createFile` rồi `write` ngay sau. Nếu contract là **“tạo mới và ghi dữ liệu, không đụng tệp cũ”**, có thể mở file bằng `CREATE_NEW` trực tiếp, tránh một bước thừa giữa create và write.

### 6.1. Các lựa chọn `StandardOpenOption` quan trọng

| Option | Ý nghĩa | Điều phải cẩn thận |
| --- | --- | --- |
| `CREATE_NEW` | Tạo file mới; thất bại nếu mục đích đã tồn tại; check-and-create nguyên tử | Dùng cho tạo mới **không ghi đè** |
| `CREATE` | Tạo file nếu chưa có; nếu đã có thì mở theo các option khác | **Không** bảo đảm file đã tồn tại được giữ nguyên |
| `WRITE` | Mở để ghi | Cần phối hợp với cách tạo/truncate/append |
| `TRUNCATE_EXISTING` | Nếu mở file hiện hữu để ghi, đưa độ dài về 0 | Có thể **mất dữ liệu cũ** nếu dùng nhầm |
| `APPEND` | Ghi thêm vào cuối file theo khả năng provider | Không tự thiết kế thành cơ chế logging nhiều process an toàn |
| `READ` | Mở để đọc | Không phải option tạo file |

`Files.writeString(path, text, charset)` khi **không chỉ rõ option** có semantics tạo hoặc truncate file theo hợp đồng hiện hành. Vì vậy, với dữ liệu quan trọng, đừng mặc định rằng gọi `writeString` sẽ “chỉ tạo nếu chưa có”. Hãy đặt option **có chủ đích**.

### 6.2. Chương trình D: `WriteNewFileDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class WriteNewFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-write-new-");
        Path data = root.resolve("data");
        Path folder = data.resolve("2026");
        Path file = folder.resolve("message.txt");
        Path empty = folder.resolve("empty.txt");

        try {
            Files.createDirectories(folder);
            Files.writeString(file, "first", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            System.out.println("initialContent=" +
                    Files.readString(file, StandardCharsets.UTF_8));

            try {
                Files.writeString(file, "other", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
                System.out.println("overwrite=unexpected");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("overwritePrevented=true");
            }

            System.out.println("stillFirst=" + Files.readString(file,
                    StandardCharsets.UTF_8).equals("first"));

            Files.createFile(empty);
            System.out.println("emptyFileSize=" + Files.size(empty));
            Files.writeString(empty, "ready", StandardCharsets.UTF_8);
            System.out.println("updatedEmpty=" + Files.readString(empty,
                    StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(empty);
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(data);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 WriteNewFileDemo.java
java WriteNewFileDemo
```

**Stdout chính xác:**

```text
initialContent=first
overwritePrevented=true
stillFirst=true
emptyFileSize=0
updatedEmpty=ready
```

### 6.3. Những gì đã được chứng minh

- `Files.createDirectories(folder)` tạo hai cấp cha còn thiếu.
- `writeString(..., CREATE_NEW, WRITE)` tạo file mới và ghi `"first"`, không cần gọi `createFile` trước.
- Lặp lại với `CREATE_NEW` khi file đã có bị từ chối; nội dung cũ vẫn là `"first"`.
- `Files.createFile(empty)` tạo file rỗng; `Files.size(empty)==0`.
- `Files.writeString(empty,"ready",UTF_8)` sau đó ghi nội dung theo semantics mặc định của overload này.

**Không biến một lần test successful thành bảo đảm mọi I/O hoàn tất toàn vẹn trong mọi lỗi.** Khi ghi dữ liệu lớn hoặc gặp lỗi giữa chừng, file được tạo bằng `CREATE_NEW` có thể đã tồn tại nhưng chỉ có **một phần** nội dung. Nếu cần publish file all-or-nothing, cân nhắc viết hoàn chỉnh vào một file tạm phù hợp rồi move sang đích với contract và tùy chọn cần thiết; atomic move còn phụ thuộc provider và filesystem.

### 6.4. Nếu dự án vẫn nhắm Java 7

Có thể viết bằng API `Files.newBufferedWriter`, đã tồn tại trong NIO.2:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        file,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    writer.write("first");
}
```

Đây là **mảnh minh họa** cần định nghĩa `file`, import `java.io.BufferedWriter`, `Files`, `StandardCharsets`, `StandardOpenOption` và xử lý `IOException`. Với Java 17+, cả cách dùng `newBufferedWriter` và `writeString` đều là kiến thức đang còn áp dụng.

## 7. Tạo tài nguyên tạm: không tự nghĩ ra tên cố định trong thư mục chia sẻ

Ứng dụng thường cần tệp tạm để xử lý dữ liệu trung gian, đệm export hoặc tạo artifact trước khi chuyển vào vị trí chính thức. Đừng dùng một tên cố định như `"/tmp/report.tmp"` rồi giả định nó chưa tồn tại. Nhiều tiến trình có thể va chạm; thư mục chung có thể chứa tệp do người dùng khác sở hữu.

`Files` có các factory chuyên dụng:

- `Files.createTempFile(prefix, suffix)` — tạo một regular file rỗng mới trong khu vực tạm mặc định.
- `Files.createTempFile(dir, prefix, suffix)` — tạo trong **thư mục được chỉ định**.
- `Files.createTempDirectory(prefix)` — tạo một directory tạm mới trong khu vực mặc định.
- `Files.createTempDirectory(dir, prefix)` — tạo directory tạm mới bên trong directory được chỉ định.

Các overload có `FileAttribute<?>... attrs` cũng cho phép yêu cầu thuộc tính ban đầu khi provider hỗ trợ. **Không giả định thư mục tạm luôn có cùng đường dẫn trên mọi hệ điều hành**; hãy sử dụng `Path` trả về từ API.

### 7.1. Chương trình E: `TempResourcesDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TempResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-temp-");
        Path first = null;
        Path second = null;
        Path child = null;

        try {
            first = Files.createTempFile(root, "job-", ".tmp");
            second = Files.createTempFile(root, "job-", ".tmp");
            child = Files.createTempDirectory(root, "results-");

            System.out.println("uniqueNames=" + !first.equals(second));
            System.out.println("firstIsFile=" + Files.isRegularFile(first));
            System.out.println("secondIsFile=" + Files.isRegularFile(second));
            System.out.println("childIsDirectory=" + Files.isDirectory(child));
            System.out.println("emptyFile=" + (Files.size(first) == 0));
            System.out.println("underRoot=" +
                    (first.getParent().equals(root)
                    && second.getParent().equals(root)
                    && child.getParent().equals(root)));
        } finally {
            if (first != null) Files.deleteIfExists(first);
            if (second != null) Files.deleteIfExists(second);
            if (child != null) Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 TempResourcesDemo.java
java TempResourcesDemo
```

Output:

```text
uniqueNames=true
firstIsFile=true
secondIsFile=true
childIsDirectory=true
emptyFile=true
underRoot=true
```

### 7.2. Phân tích vòng đời

- `createTempDirectory` cấp một directory mới; tên thật được API sinh, nhưng chương trình không in nó để output độc lập môi trường.
- Hai `createTempFile` với cùng prefix/suffix cho hai file riêng biệt trong phép thử.
- Các file tạm ban đầu rỗng.
- Tất cả đối tượng được tạo trong thư mục tạm riêng của ví dụ.
- `finally` xóa những file/directory đã được tạo và chỉ xóa root sau khi các mục con đã hết.

**Lưu ý:** `Files.createTempFile` không tự xóa file khi chương trình kết thúc. Nếu cần cleanup, hãy có lifecycle rõ. `deleteOnExit` là một cơ chế khác nhưng không nên được coi là giải pháp duy nhất cho process sống lâu, nhiều tệp tạm hoặc crash bất thường.

### 7.3. Không dùng tệp tạm trong directory thiếu tin cậy mà bỏ qua quyền

Với dữ liệu nhạy cảm, chọn directory tạm có bảo vệ thích hợp và xem xét quyền truy cập/thuộc tính ban đầu. Temp file không tự đồng nghĩa “chỉ chủ sở hữu đọc được” trên mọi provider. Nếu ghi dữ liệu nhạy cảm, thiết kế permission/ACL và cleanup đúng ngay từ lúc tạo, thay vì chỉ đặt phần mở rộng `.tmp`.

## 8. Race condition: vì sao `createFile` là một API có giá trị riêng

Hai luồng chạy đồng thời đều có thể quan sát `Files.notExists(target) == true` rồi cùng quyết định tạo tệp. Vì vậy, mẫu check-then-create không bảo đảm chỉ một luồng thắng. `Files.createFile(target)` thực hiện check-and-create nguyên tử theo contract, nghĩa là **tại cùng một path**, chỉ một lời gọi tạo mới thành công; những lời gọi khác quan sát việc path đã bị chiếm và phải xử lý thất bại.

Để quan sát mà không phụ thuộc lịch scheduling, thử nhiều luồng cùng tạo **một tên file** trong directory tạm.

### 8.1. Chương trình F: `AtomicCreateDemo.java`

```java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class AtomicCreateDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException, ExecutionException {
        Path root = Files.createTempDirectory("files-atomic-");
        Path target = root.resolve("one-winner.txt");
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Boolean>> results = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                results.add(pool.submit(() -> {
                    start.await();
                    try {
                        Files.createFile(target);
                        return true;
                    } catch (FileAlreadyExistsException ex) {
                        return false;
                    }
                }));
            }

            start.countDown();
            int winners = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) winners++;
            }
            System.out.println("successfulCreates=" + winners);
            System.out.println("alreadyExisted=" + (8 - winners));
            System.out.println("finalFilePresent=" +
                    Files.isRegularFile(target));
        } finally {
            pool.shutdownNow();
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 AtomicCreateDemo.java
java AtomicCreateDemo
```

**Stdout trên filesystem kiểm thử:**

```text
successfulCreates=1
alreadyExisted=7
finalFilePresent=true
```

### 8.2. Bài học từ thử nghiệm cạnh tranh

- Tám tác vụ đợi `CountDownLatch` trước khi gọi `createFile(target)`.
- Một tác vụ tạo thành công tệp.
- Các tác vụ còn lại nhận `FileAlreadyExistsException` trên provider kiểm thử và trả false.
- `main` thu kết quả qua `Future`; nếu có lỗi khác không được bắt, exception từ task có thể xuất hiện qua `ExecutionException` thay vì bị biến thành “thất bại hợp lệ”.
- `finally` kết thúc executor và dọn tệp trong directory tạm.
- Kết quả này phản ánh hợp đồng atomic check-and-create của `createFile` trên filesystem đã thử, **không chứng minh** ứng dụng đã có một hệ thống khóa phân tán, timeout hoặc giao dịch publish file toàn vẹn.

**Khuyến nghị:** Khi nghiệp vụ là “create exactly once if absent”, dùng cơ chế tạo mới nguyên tử thay vì tổ hợp `exists` + `create`. Nhưng với mục tiêu **ghi đầy đủ nội dung** rồi công bố, cần giải quyết thêm partial writes, recovery, retry và visibility.

## 9. Mọi thao tác tạo có thể ném IOException: xử lý lỗi có chủ đích

Các phương thức tạo có thể thất bại vì nhiều lý do hơn việc tên đã tồn tại:

- Directory cha không có.
- Không đủ quyền truy cập hoặc quyền ghi.
- Một thành phần đường dẫn là regular file thay vì directory.
- File/directory đích đã tồn tại.
- Hệ thống tệp đầy hoặc hết quota.
- Tên path không hợp lệ theo provider.
- Tệp bị khóa hoặc policy riêng của hệ điều hành cản trở.
- Mục tiêu trên network filesystem bị lỗi I/O hoặc trạng thái thay đổi giữa các tác vụ.
- Một mục/symlink khác xuất hiện trong khi đang thao tác.

### 9.1. Bảng các exception thường gặp

| Ngoại lệ | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `FileAlreadyExistsException` | Một mục đã chiếm tên cần tạo | Nếu `CREATE_NEW` là chủ ý thì báo xung đột; không tự ghi đè |
| `NoSuchFileException` | Một thành phần/tệp cần thiết không tồn tại | Kiểm tra parent, path và logic tạo directory |
| `AccessDeniedException` | Truy cập bị từ chối | Kiểm tra permission, ACL và account chạy |
| `NotDirectoryException` | Một thành phần mong đợi là directory nhưng không phải | Kiểm tra path và loại mục |
| `DirectoryNotEmptyException` | Xóa directory chưa rỗng | Dọn đúng các mục con do ứng dụng sở hữu |
| `IOException` khác | Lỗi I/O chung hoặc điều kiện provider không map sang subtype cụ thể | Log/propagate theo hợp đồng, không đoán trước |

Những subtype cụ thể là **tùy chọn theo filesystem provider trong nhiều tình huống**. Đừng viết business logic dựa trên giả định mọi OS đều ném cùng subtype cho “parent missing” hoặc “file nằm giữa path”. Với test cross-platform, có thể xác minh **hành vi bị từ chối**, đồng thời kiểm tra exception cụ thể trên các provider bạn hỗ trợ.

### 9.2. Không nuốt lỗi chỉ để chương trình “chạy tiếp”

```java
try {
    Files.createDirectories(dir);
} catch (IOException ignored) {
    // Không khuyến nghị: không biết thư mục đã có hay chưa.
}
```

Đây là **mảnh anti-pattern**. Nếu lỗi thật sự là thiếu quyền hoặc disk full, bước ghi file phía sau có thể lỗi khó hiểu. Thay vì bỏ qua:

- Chỉ xử lý lỗi mà caller có thể khắc phục.
- Nếu mục tiêu là “directory đã có vẫn OK”, dùng semantics của `createDirectories`; không cần catch-all để làm giả idempotency.
- Với lỗi không thể xử lý, propagate hoặc translate exception cùng nguyên nhân `cause` theo boundary của ứng dụng.
- Không tự động retry vô hạn mọi `IOException`; với lỗi permission hoặc path sai, retry không làm vấn đề biến mất.

## 10. Không cố dùng `Files.exists` làm một giao thức đồng bộ hóa

`Files.exists(path)` giúp kiểm tra trạng thái tại **thời điểm kiểm tra**, nhưng không loại bỏ race với các tác vụ khác. Thậm chí `Files.exists(path)==false` không luôn chứng minh “chắc chắn không có tệp”; khi thiếu quyền hoặc trạng thái không xác định, cả `exists` và `notExists` có thể không khẳng định được điều bạn cần.

Ví dụ không nên dựa vào:

```java
if (!Files.exists(target)) {
    Files.writeString(target, "data", StandardCharsets.UTF_8);
}
```

Đây là **mảnh minh họa sai đối với yêu cầu “không bao giờ ghi đè”**, vì một tiến trình khác có thể tạo file sau `exists`. Hơn nữa, overload `writeString` không chỉ định option có semantics tạo/truncate, nên có nguy cơ ghi đè khi xảy ra race.

Nếu mục tiêu là chỉ ghi khi chưa có:

```java
Files.writeString(target, "data", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
```

Đây là mảnh minh họa cần import `Files`, `StandardCharsets`, `StandardOpenOption` và xử lý `IOException`. Với Java 7, dùng `newBufferedWriter` hoặc `Files.write` với option `CREATE_NEW`, không dùng `writeString` vì nó xuất hiện từ Java 11.

## 11. An toàn đường dẫn: tạo tài nguyên trong đúng thư mục được phép

Khi đường dẫn đến từ request/API của người dùng, điều nguy hiểm không chỉ là đã tồn tại hay chưa. Nếu một service dự kiến chỉ tạo file trong directory `base` mà cho phép `../secret.txt` hoặc một **absolute path** chưa tin cậy, nó có thể ghi file ngoài phạm vi.

Một kiểm tra từ vựng cơ bản:

```java
Path base = Paths.get("storage").toAbsolutePath().normalize();
Path requested = Paths.get("reports", "summary.txt");

if (requested.isAbsolute()) {
    throw new IllegalArgumentException("Absolute path not allowed");
}
Path target = base.resolve(requested).normalize();
if (!target.startsWith(base)) {
    throw new IllegalArgumentException("Path escapes base");
}
Files.createDirectories(target.getParent());
Files.createFile(target);
```

Đây là **mảnh minh họa**, chưa phải security boundary hoàn chỉnh. Nó có thể ngăn một số trường hợp `..` thuần từ vựng, nhưng **không đủ** để chống symlink/reparse point, mount, race và các quyền filesystem.

### 11.1. Chương trình G: `SafeBaseDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SafeBaseDemo {
    public static void main(String[] args) throws IOException {
        Path base = Files.createTempDirectory("files-safe-base-")
                .toAbsolutePath().normalize();
        Path relative = Path.of("reports", "2026", "data.txt");
        Path parent = base.resolve("reports");
        Path nested = parent.resolve("2026");
        Path target = base.resolve(relative).normalize();

        try {
            System.out.println("relativeIsAbsolute=" + relative.isAbsolute());
            System.out.println("goodWithinBase=" + target.startsWith(base));
            Files.createDirectories(target.getParent());
            Files.createFile(target);
            System.out.println("createdWithinBase=" +
                    Files.isRegularFile(target));

            Path escape = Path.of("..", "outside.txt");
            System.out.println("escapeAllowed=" +
                    base.resolve(escape).normalize().startsWith(base));
            Path absoluteInput = base.getRoot().resolve("elsewhere.txt");
            System.out.println("absoluteInputRejected=" +
                    absoluteInput.isAbsolute());
            System.out.println("stringPrefixIsDangerous=" +
                    "sandbox_evil".startsWith("sandbox"));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(parent);
            Files.deleteIfExists(base);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 SafeBaseDemo.java
java SafeBaseDemo
```

Output:

```text
relativeIsAbsolute=false
goodWithinBase=true
createdWithinBase=true
escapeAllowed=false
absoluteInputRejected=true
stringPrefixIsDangerous=true
```

### 11.2. Vì sao test này có ích và giới hạn của nó

- `Path.of(...)` từ **Java 11**, vẫn phù hợp trong Java 17+; nếu cần code Java 7, dùng `Paths.get(...)`.
- `goodWithinBase=true`: Path được ghép bằng `resolve` và `normalize` còn nằm dưới base về mặt thành phần path.
- `escapeAllowed=false`: đường dẫn `../outside.txt` bị nhận diện là ra ngoài base về mặt từ vựng.
- `absoluteInputRejected=true` cho thấy absolute input cần một chính sách rõ thay vì tin `resolve` sẽ buộc nó nằm trong base.
- `"sandbox_evil".startsWith("sandbox")` trả true trên **String**, chứng minh không thể dùng phép so tiền tố text thay cho `Path.startsWith`.
- Việc tạo file trong temp base thành công **không chứng minh** một sandbox thực sự an toàn trước symlink và race.

Nếu ứng dụng xử lý input không tin cậy, cân nhắc một thiết kế directory-relative có bảo vệ symlink/TOCTOU phù hợp provider, quyền hệ điều hành đúng, directory base không cho attacker sửa, và các API như `SecureDirectoryStream` khi được filesystem hỗ trợ. Không quảng cáo `normalize()+startsWith()` là giải pháp toàn diện.

## 12. Quyền truy cập và các thuộc tính ban đầu

`Files.createFile`, `createDirectory`, `createDirectories` và một số factory temp có overload nhận `FileAttribute<?>... attrs`. Những thuộc tính này được thiết lập khi tạo **mục mới** theo khả năng provider, cho phép tránh một số cửa sổ thời gian do “tạo rồi mới `setPermissions`”.

Ví dụ định hướng trên filesystem hỗ trợ **POSIX file permissions**:

```java
FileAttribute<Set<PosixFilePermission>> ownerOnly =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rwx------"));
Files.createDirectory(directory, ownerOnly);
```

Đây là **mảnh minh họa**, cần import `java.nio.file.attribute.FileAttribute`, `PosixFilePermission`, `PosixFilePermissions` và `java.util.Set`, cùng `Files` và định nghĩa `directory`. **Không phải code portable cho mọi filesystem**: ví dụ Windows default provider thường không hỗ trợ kiểu POSIX attributes này; có thể bị từ chối. Cần kiểm tra provider, policy và hợp đồng permission thực tế, hoặc sử dụng ACL/biện pháp bảo mật tương ứng.

### 12.1. Quyền của cha quan trọng

Muốn tạo `base/child/file.txt`, quyền tạo mục dưới `base/child` ảnh hưởng kết quả. `createDirectories` không phải một công cụ “nâng quyền” hay vượt qua ACL. Trong môi trường container, service account có thể chỉ ghi được vào các directory được mount hoặc cấp quyền; source code đúng chưa đủ.

### 12.2. Những thuộc tính của directory cũ không được áp lại tự động

Nếu `Files.createDirectories(dir, attrs)` gặp một directory cha đã tồn tại, đừng coi lời gọi ấy như lệnh “sửa mọi directory thành quyền attrs”. Thuộc tính áp dụng khi tạo những mục mới theo provider; việc thay quyền một mục đã có là thao tác khác và cần ủy quyền rõ.

## 13. Cleanup và partial failure: luôn biết mình sở hữu mục nào

Không ít lỗi trong môi trường thực tế xảy ra lúc rollback:

- `createDirectories` tạo được `a` và `a/b` rồi lỗi ở `a/b/c`.
- Ứng dụng catch exception rồi xóa `a` một cách đệ quy dù `a` có thể đã tồn tại và chứa dữ liệu do bên khác sở hữu.
- Một tác vụ khác vừa tạo file trong directory mà ứng dụng định xóa.
- Cleanup chỉ bắt đầu sau khi ghi file thất bại nhưng ứng dụng không phân biệt file đã tồn tại trước với file do chính nó vừa tạo.

**Không xóa một directory chỉ vì bạn từng gọi `createDirectories` vào path đó.** Method này có thể không hề tạo directory đích (vì nó đã có), và có thể chỉ tạo một số parent trên đường đi.

### 13.1. Cách kiểm thử an toàn

Trong các chương trình trên:

1. Tạo một directory tạm riêng với `Files.createTempDirectory`.
2. Chỉ thao tác bên trong directory đó.
3. Theo dõi rõ từng file/directory sẽ được tạo.
4. Dùng `try/finally`.
5. Xóa file trước, rồi directory con, cuối cùng mới đến root.
6. Không chạm vào đường dẫn hiện hữu ngoài phạm vi test.

`Files.deleteIfExists(path)` chỉ xóa mục được chỉ định nếu phù hợp; nó không tự xóa đệ quy toàn bộ directory. Nếu directory không rỗng, thao tác có thể ném `DirectoryNotEmptyException`. Điều đó giúp tránh tình trạng một lời gọi vô tình xóa cả cây dữ liệu.

### 13.2. Cleanup tự động bằng tree walk cần ràng buộc rõ

Với cây tạm **hoàn toàn do test sở hữu**, có thể duyệt theo thứ tự sâu trước và xóa từng mục. Nhưng không biến một routine recursive delete thành phương pháp mặc định cho directory đến từ user input. Với symlink, race hoặc directory được dùng chung, một hàm delete đệ quy thiếu kiểm soát có thể gây hậu quả nghiêm trọng.

Giải pháp an toàn nhất cho các ví dụ học tập là **tạo root temp riêng** và dọn đúng những mục được ví dụ tạo. Trong ứng dụng thật, xác định rõ ownership, retention và cách xử lý khi cleanup thất bại.

## 14. Relative paths và working directory khi tạo tài nguyên

Ví dụ:

```java
Files.createDirectories(Paths.get("logs", "2026"));
```

Đây là **mảnh minh họa** cần import `Paths`/`Files` và xử lý `IOException`. Nếu path là relative, location thật phụ thuộc vào **working directory** và provider của process.

Không tự giả định:

- Relative path luôn bắt đầu từ source directory.
- Relative path luôn bắt đầu từ project root.
- Relative path luôn bắt đầu từ thư mục chứa JAR.
- IDE và container đang dùng working directory giống nhau.
- Windows và Linux nhận cùng một cách viết đường dẫn chứa dấu `\`.

Khi các thư mục cần tồn tại ở một vị trí cụ thể, truyền base một cách rõ ràng:

```java
Path base = Paths.get("application-data").toAbsolutePath().normalize();
Path reports = base.resolve("reports").resolve("2026");
Files.createDirectories(reports);
```

Đây là **mảnh minh họa**. Với hệ thống triển khai, tốt hơn là lấy base từ cấu hình, tham số CLI, directory do hệ điều hành cấp hoặc một dependency được xác định, chứ không buộc mọi nơi ngầm phụ thuộc working directory.

### 14.1. Không nhầm resource trong JAR với tệp trên filesystem

`src/main/resources/config.json` là một đường dẫn trong source tree khi phát triển. Khi đóng gói thành JAR, file resource có thể không còn là **regular file** có thể tạo/xóa bằng `Files.createFile` trên default filesystem. Nếu muốn **đọc tài nguyên được đóng gói**, dùng API classpath resource phù hợp, ví dụ `getResourceAsStream`.

Nếu cần **tạo và sửa file cấu hình khi runtime**, hãy chọn một directory ngoài JAR và có quyền ghi, không cố tạo bên trong archive hoặc source tree.

## 15. Các hiểu lầm phổ biến

### 15.1. “createFile tự tạo các thư mục cha”

Không. `Files.createFile(root.resolve("a/b/file.txt"))` có thể thất bại nếu `a` hoặc `b` chưa tồn tại. Muốn đảm bảo cha, dùng `createDirectories(file.getParent())` trước, với kiểm tra `null` và ràng buộc input phù hợp.

### 15.2. “createDirectories tạo cả file cuối nếu tên có đuôi .txt”

Không. `createDirectories` chỉ tạo **directory**, dù tên cuối là `file.txt`. Nếu cần file, tạo cha trước rồi tạo file.

### 15.3. “createDirectory và createDirectories khác nhau chỉ một chữ s”

Sai. `createDirectory` tạo **một cấp** và thất bại nếu đích đã tồn tại. `createDirectories` tạo **các cha cần thiết** và không lỗi chỉ vì directory đích đã tồn tại.

### 15.4. “Nếu directory đã tồn tại, createDirectories luôn thành công”

Nếu directory đích tồn tại đúng nghĩa và không có vấn đề filesystem khác, lời gọi có thể hoàn tất. Nhưng nếu một thành phần cần đi qua **regular file**, quyền bị từ chối hoặc có lỗi I/O, vẫn thất bại. Idempotent không có nghĩa bỏ qua mọi lỗi.

### 15.5. “createFile có thể ghi đè file cũ để tạo file rỗng”

Không. `createFile` dùng semantics tạo mới, không replace nội dung file hiện có. Nếu có file cũ cùng tên, xử lý xung đột đúng contract thay vì tự xóa file cũ.

### 15.6. “Files.writeString mặc định không bao giờ ghi đè”

Không đúng. Overload mặc định có semantics tạo hoặc truncate tệp theo contract. Khi cần tạo mới mà không ghi đè, chọn `CREATE_NEW` và xử lý ngoại lệ.

### 15.7. “Kiểm tra exists trước sẽ làm tạo mới an toàn dưới concurrency”

Không. Check-then-act có race. `CREATE_NEW` hoặc `createFile` là công cụ đúng khi cần atomic create-if-absent theo contract filesystem.

### 15.8. “createDirectories tạo tất cả hoặc không tạo gì”

Không. Một lỗi có thể xảy ra sau khi đã tạo một số directory cha. Đừng rollback bằng cách xóa toàn bộ cây nếu một phần đã thuộc người khác từ trước.

### 15.9. “Files.exists false chứng minh không có mục”

Không phải mọi lúc. Nếu filesystem không xác minh được trạng thái, phép hỏi có thể không cho bằng chứng chắc chắn. Nếu cần thao tác, thử thao tác và xử lý `IOException`.

### 15.10. “Files.createTempFile sẽ tự xóa sau khi chương trình kết thúc”

Không có bảo đảm như vậy. File tạm được tạo là một file thật; cần quản lý retention/cleanup. Với process crash hoặc quyền bị thay đổi, cleanup có thể không thành công.

### 15.11. “normalize + startsWith là sandbox bảo mật hoàn chỉnh”

Không. Kiểm tra lexical bỏ qua ý nghĩa của symlink và một số race filesystem. Nếu dùng đường dẫn chưa tin cậy, cần thiết kế access control và thao tác filesystem thích hợp.

### 15.12. “Đã có quyền tạo file thì cũng có quyền tạo mọi directory cha”

Không. Quyền tạo một mục phụ thuộc directory cha, ACL và chính sách của provider. `createDirectories` không nâng quyền.

### 15.13. “Tạo file thành công tức là dữ liệu đã được ghi bền vững”

`createFile` chỉ tạo file rỗng. `Files.write`/`writeString` còn có khả năng partial write hoặc lỗi I/O; durability/publish semantics là vấn đề riêng. Đừng dùng một boolean `Files.exists` để khẳng định nội dung đã được ghi và đồng bộ tới storage an toàn.

### 15.14. “Cứ xóa directory sau khi lỗi là rollback đúng”

Nếu directory đã tồn tại trước, hoặc chứa dữ liệu do bên khác tạo, xóa có thể phá dữ liệu. Theo dõi ownership của từng mục, không xóa bừa cả cây.

## 16. Ma trận kiểm thử

| Tình huống | API | Kỳ vọng |
| --- | --- | --- |
| Tạo regular file mới | `Files.createFile(file)` | File tồn tại và ban đầu rỗng |
| Tạo lại cùng tên | `Files.createFile(file)` | Thất bại, thường `FileAlreadyExistsException` |
| Cha của file chưa có | `Files.createFile(nested)` | Thất bại, không tạo cha tự động |
| Tạo directory một cấp | `Files.createDirectory(dir)` | Tạo thành công nếu cha có và đích chưa có |
| Tạo lại directory một cấp | `Files.createDirectory(dir)` | Thất bại vì đã tồn tại |
| Cha directory chưa có | `Files.createDirectory(nested)` | Thất bại, không tự tạo cha |
| Directory cha nhiều cấp chưa có | `Files.createDirectories(deep)` | Tạo các cấp còn thiếu |
| Gọi `createDirectories` lần hai | Cùng `deep` | Hoàn tất bình thường nếu là directory |
| Một thành phần cha là file | `createDirectories(file.resolve("child"))` | Thất bại |
| Tạo mới và ghi text | `writeString(..., CREATE_NEW, WRITE)` | Tạo file rồi ghi nội dung |
| Tạo mới trên file đã có | `writeString(..., CREATE_NEW, WRITE)` | Thất bại, không ghi đè |
| Tạo file tạm hai lần | `createTempFile` | Tên khác nhau; file được tạo riêng |
| Thư mục tạm | `createTempDirectory` | Directory được tạo thực sự |
| Tám luồng tạo cùng một file | `createFile` | Chỉ một lời gọi tạo thành công trên test FS |
| Input có `..` | `base.resolve(input).normalize()` | Có thể thoát base; cần kiểm tra |
| Input là absolute | `base.resolve(input)` | Có thể không nằm trong base |
| Symlink ngoài base | Kiểm tra lexical riêng | Không đủ; cần kiểm tra ở mức filesystem |

### 16.1. Test nên dùng directory tạm

Không kiểm thử bằng cách chạy `Files.createFile("README.md")` hay `Files.createDirectories("src/main/resources")` trong repository thật. Thay vào đó, tạo root bằng `Files.createTempDirectory`, chỉ tạo mục phía dưới root đó, in các thuộc tính boolean/kích thước thay vì tên tuyệt đối phụ thuộc máy, và dọn dẹp sau test.

### 16.2. Test failure paths không chỉ kiểm tra catch

Với một trường hợp duplicate file, nên xác nhận **nội dung cũ không bị thay đổi**. Với trường hợp file đứng ở giữa cây directory, xác nhận **file blocker vẫn còn**. Với trường hợp parent thiếu, xác nhận method không âm thầm tạo parent. Với `createDirectories`, xác nhận gọi lại không lỗi khi directory đã tồn tại đúng loại.

### 16.3. Test không được thay thế kiểm tra bảo mật

Test lexical traversal chỉ là một lớp. Với path do user nhập trong ứng dụng xử lý dữ liệu thật, cần kiểm thử cả symlink/reparse points, permission, mount points và concurrency nếu chúng nằm trong threat model.

## 17. Quy trình sử dụng trong ứng dụng

Khi cần tạo `data/reports/summary.txt`:

1. **Xác định root/base** được phép ghi và rõ ràng theo cấu hình.
2. **Xác định file hay directory** là mục tiêu cuối cùng.
3. **Xác định chính sách đã tồn tại**: fail-if-exists, reuse directory, append, overwrite hay versioned filename.
4. **Kiểm tra đầu vào**: relative/absolute, thành phần `..`, tên file hợp lệ, giới hạn ký tự và giới hạn đường dẫn.
5. **Tạo directory cha** bằng `Files.createDirectories(parent)` nếu contract cho phép các directory đã có.
6. **Tạo file** bằng `Files.createFile` hoặc mở writer `CREATE_NEW` nếu không được ghi đè.
7. **Ghi nội dung** bằng API và charset tường minh khi cần, không nhầm tạo file rỗng với ghi file.
8. **Xử lý lỗi có chọn lọc**: duplicate, thiếu quyền, cha không hợp lệ, quota/I/O, symlink.
9. **Đóng stream/writer** với try-with-resources; không để resource mở sau khi hoàn thành.
10. **Quản lý rollback/cleanup** chỉ trên mục thật sự thuộc quyền sở hữu ứng dụng.
11. **Đối với input chưa tin cậy**, bổ sung access control filesystem, chính sách symlink và chống race ở boundary thích hợp.
12. **Kiểm thử đa nền tảng** với test root tạm và hai trạng thái: chưa có mục và đã có mục.

### Checklist trước khi merge

- [ ] Chọn đúng `createFile`, `createDirectory`, `createDirectories` theo hành vi mong muốn.
- [ ] Không dùng `createDirectories` trên đường dẫn kết thúc bằng **file**.
- [ ] Không giả định `createFile` hay `createDirectory` tự tạo thư mục cha.
- [ ] Kiểm tra `getParent() == null` khi path có thể là một tên đơn.
- [ ] Không dựa vào `exists` + `create` để bảo đảm không ghi đè dưới concurrency.
- [ ] Nếu cần tạo file mới có nội dung, dùng `CREATE_NEW` với writer/Files phù hợp.
- [ ] Không dùng `TRUNCATE_EXISTING` nếu dữ liệu cũ cần được bảo toàn.
- [ ] Xử lý checked `IOException` và subtype hữu ích, không nuốt lỗi.
- [ ] Có test cho existing file, existing directory, missing parent và file-as-parent.
- [ ] Không giả định `createDirectories` là transaction nguyên tử toàn cây.
- [ ] Không xóa một directory có thể đã tồn tại hoặc do bên khác sử dụng.
- [ ] Không hardcode filesystem path của developer; ưu tiên base cấu hình.
- [ ] Không nhầm resource classpath/JAR với regular file có thể ghi trực tiếp.
- [ ] Có ràng buộc permission và threat model nếu input đến từ người dùng.
- [ ] Nếu dùng `Files.writeString`/`Path.of`, đã xác định chúng được thêm từ Java 11 và runtime đang hỗ trợ.
- [ ] Tệp tạm được quản lý vòng đời và cleanup đúng phạm vi.

## 18. Bài tập và đáp án định hướng

**Bài 1 — Phân biệt API.** Bạn có một `Path` tới `reports/2026/result.csv`, chưa có directory `reports`. Trong ba phương thức `createFile`, `createDirectory`, `createDirectories`, hãy xác định thứ tự lời gọi để tạo **file rỗng** đúng chỗ.

**Bài 2 — Duplicate.** Tạo `notes.txt` bằng `Files.createFile`, gọi lần hai, quan sát exception. Điều gì xảy ra với nội dung đã có trong file?

**Bài 3 — Một cấp và nhiều cấp.** Viết chương trình tạo `a/b/c` trong root tạm: thử `createDirectory(c)` trước rồi dùng `createDirectories(c)`. Hai kết quả khác nhau thế nào?

**Bài 4 — Idempotency.** Tạo `a/b/c` bằng `createDirectories`, sau đó gọi lại cùng path. Vì sao lần gọi thứ hai là một hành vi mong muốn trong phần khởi tạo cấu trúc ứng dụng?

**Bài 5 — Xung đột loại mục.** Tạo một regular file tên `blocker`; thử tạo directory `blocker/child`. Bắt lỗi, xác minh `blocker` vẫn là file.

**Bài 6 — CREATE_NEW.** Ghi `"first"` vào một file mới bằng `Files.writeString(..., CREATE_NEW, WRITE)`. Gọi lại với `"second"`. Kiểm tra nội dung file vẫn giữ `"first"`.

**Bài 7 — File tạm.** Tạo một temp directory và hai temp files với cùng prefix/suffix. In boolean so sánh tên, loại file/directory và dọn dẹp toàn bộ trong `finally`.

**Bài 8 — Race.** Cho tám luồng cùng tạo một file. Tại sao `Files.createFile` giúp chỉ có một lời gọi thành công hơn so với check-then-create? Vì sao kết quả đó chưa chứng minh tính nguyên tử của một lần **ghi file nhiều byte**?

**Bài 9 — Missing parent.** Viết hàm nhận `Path target`, tạo directory cha nếu cần rồi tạo file. Với path chỉ có tên `"note.txt"`, `getParent()` có thể trả gì?

**Bài 10 — Rollback.** `createDirectories` thất bại sau khi đã tạo một số parent. Giải thích vì sao không được tự động xóa mọi directory dọc đường tạo mà không biết directory nào đã tồn tại từ trước.

**Bài 11 — Path traversal.** Một API nhận `"../outside.txt"` và một absolute path. Hãy đề xuất bước kiểm tra lexical, sau đó nêu ít nhất hai hạn chế liên quan symlink/race.

**Bài 12 — Quyền truy cập.** Nếu ứng dụng có quyền tạo file trong `/app/data` nhưng không có quyền tạo `/app/system`, `createDirectories` có tự vượt permission để thành công không? Cần thay đổi ở deployment hay tại hệ thống tệp?

**Bài 13 — Java 7 so với Java hiện đại.** Vì sao `Files.createDirectories` là một API Java 7 còn `Files.writeString` là Java 11+? Nếu phải biên dịch `--release 7`, bạn sẽ dùng `Files.write` hoặc `newBufferedWriter` như thế nào?

**Bài 14 — Resources.** Vì sao `Paths.get("src/main/resources/config.json")` không đảm bảo đọc được resource sau khi đóng gói JAR? Nếu muốn tạo file cấu hình runtime, nên đặt ở đâu?

**Bài 15 — Test khả chuyển.** Chuyển một test đang ghi vào `C:\\Users\\developer\\Desktop` sang test tạo thư mục tạm. So sánh độ ổn định khi chạy trong IDE, CI, Windows và Linux.

### Đáp án ngắn

- **Bài 1:** Lấy `target.getParent()`, dùng `Files.createDirectories` với parent nếu hợp lệ; sau đó dùng `Files.createFile(target)`.
- **Bài 2:** Lần hai bị từ chối; `createFile` không có semantics ghi đè file cũ.
- **Bài 3:** `createDirectory` không tự tạo parent; `createDirectories` tạo các cấp còn thiếu.
- **Bài 4:** Setup directory tree có thể chạy lại mà không lỗi chỉ vì đã có directory.
- **Bài 5:** File không thể làm directory chứa con; giữ nguyên blocker.
- **Bài 6:** `CREATE_NEW` thất bại khi tên đã có; nội dung trước đó được giữ.
- **Bài 7:** Temp APIs tạo các mục mới; việc dọn file/directory vẫn thuộc trách nhiệm chương trình.
- **Bài 8:** Atomic check-and-create của file khác với atomic publish toàn bộ nội dung.
- **Bài 9:** `getParent()` có thể là null; không gọi createDirectories với null.
- **Bài 10:** Không thể suy directory nào do mình tạo từ kết quả chung; cleanup phải dựa trên ownership.
- **Bài 11:** Xác minh relative và lexical containment; vẫn cần biện pháp filesystem chống symlink/TOCTOU.
- **Bài 12:** Không; thiếu quyền phải xử lý ở permission/deployment hoặc chọn path có quyền phù hợp.
- **Bài 13:** `writeString` là tiện ích hiện đại; Java 7 đã có `newBufferedWriter` và `Files.write`.
- **Bài 14:** Classpath resource có thể nằm trong JAR; cấu hình có thể sửa cần external directory.
- **Bài 15:** Directory tạm riêng giảm phụ thuộc môi trường và tránh thay đổi file của người dùng.

## 19. Tài liệu chính thức còn áp dụng

- [Java SE 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): hợp đồng `createFile`, `createDirectory`, `createDirectories`, `createTempFile`, `createTempDirectory`, `write`, `writeString`, `deleteIfExists` và ngoại lệ.
- [Java SE 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `getParent`, `resolve`, `normalize`, `startsWith` và semantics của filesystem provider.
- [Java SE 17 — `java.nio.file.StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `WRITE`, `TRUNCATE_EXISTING`, `APPEND`.
- [Java SE 17 — `java.nio.file.FileAlreadyExistsException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html): checked exception thường gặp khi tạo mục đã tồn tại.
- [Java SE 17 — `java.nio.file.NoSuchFileException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html): thiếu mục cần thiết.
- [Java SE 17 — `java.nio.file.attribute.PosixFilePermissions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): thuộc tính quyền POSIX khi provider hỗ trợ.
- [Java SE 17 — `java.nio.file.SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): mô hình thao tác directory-relative nhằm giảm một số race trên provider hỗ trợ.
- [Java SE 17 — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 tường minh khi ghi text.

**Kết luận:** `Files.createFile` tạo **tệp mới rỗng** và không ghi đè; `Files.createDirectory` tạo **một cấp directory mới**; `Files.createDirectories` tạo **cây directory cha còn thiếu** và chấp nhận directory đã tồn tại. Khi muốn tạo mới rồi ghi dữ liệu, dùng `CREATE_NEW` với API ghi tương ứng. Luôn xác định base path, quyền truy cập, chính sách khi đã tồn tại, rủi ro concurrent access và trách nhiệm cleanup. Thao tác tạo đúng là bước đầu; tính toàn vẹn nội dung và security boundary cần được thiết kế riêng.