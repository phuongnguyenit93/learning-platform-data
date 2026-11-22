# Sao chép tệp và chính sách khi đích tồn tại với Files.copy

**Chủ đề:** Java 7 — `Files`  
**Bài học:** Sao chép tệp và chính sách khi đích tồn tại  
**Môi trường:** Java 17+; `java.nio.file.Files.copy` và các `CopyOption` vẫn là API tiêu chuẩn hiện hành của Java. Bài viết dùng UTF-8 tường minh, thư mục tạm cho các ví dụ thực hành và không phụ thuộc chi tiết hệ điều hành không được API cam kết.

## 1. Bài toán thật: copy thành công hay được quyền thay thế?

Có hai câu hỏi **khác nhau** khi sao chép một tệp:

1. Nguồn và đích ở đâu, dữ liệu có được sao chép không?
2. **Nếu đích đã tồn tại**, chương trình phải **báo lỗi**, **thay thế**, **giữ nguyên**, hay chuyển sang một tên tệp khác?

Bài học này tập trung vào câu hỏi thứ hai. Đây là một quyết định nghiệp vụ quan trọng: lặng lẽ ghi đè có thể làm mất dữ liệu người dùng, còn từ chối tất cả tệp trùng tên có thể khiến việc cập nhật tệp cấu hình hay export kết quả không hoạt động.

**Hành vi mặc định của `Files.copy(Path, Path)`:** nếu đích đã tồn tại và nguồn/đích không được nhận diện là cùng một tệp, thao tác thông thường **thất bại với `FileAlreadyExistsException`**. Nó **không tự động ghi đè**.

Nếu muốn cho phép thay thế tệp đích, truyền `StandardCopyOption.REPLACE_EXISTING`. Đây là lựa chọn **tường minh**, có hậu quả lên dữ liệu cũ và cần được xác nhận bằng chính sách ứng dụng.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

// Sao chép và từ chối khi đích đã tồn tại:
Files.copy(source, target);

// Chủ đích thay thế đích có sẵn:
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

Đây là **snippet** đặt trong method đã khai báo/đã xử lý `IOException`; `source` và `target` là các biến `Path`. Tạo `Path` không tự tạo tệp. `Files.copy` là thao tác I/O thực tế.

> **Quy tắc thiết kế:** đừng biến tất cả lời gọi copy thành `REPLACE_EXISTING` “để khỏi lỗi”. Hãy chọn chính sách dựa trên quyền sở hữu, kỳ vọng người dùng, tính idempotent, phiên bản dữ liệu và mức độ cho phép mất dữ liệu.

## 2. Chữ ký API và các CopyOption liên quan

Các overload phổ biến của `java.nio.file.Files`:

```java
// Đường dẫn nguồn và đích:
static Path copy(Path source, Path target, CopyOption... options)
        throws IOException;

// Dữ liệu từ InputStream đến một Path:
static long copy(InputStream in, Path target, CopyOption... options)
        throws IOException;

// Dữ liệu từ một Path đến OutputStream:
static long copy(Path source, OutputStream out)
        throws IOException;
```

Đây là **chữ ký API được rút gọn**, không phải một file Java độc lập. Ba overload không có hoàn toàn cùng bộ tùy chọn và không có cùng hợp đồng ownership đối với stream. `Path → Path` là trọng tâm bài; các biến thể stream được giải thích tại phần 8.

### 2.1. Ba tùy chọn chính của Path → Path

| Tùy chọn | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Không truyền option | Không cho phép thay thế đích có sẵn trong trường hợp thông thường | Khi đích tồn tại, thường ném `FileAlreadyExistsException` |
| `StandardCopyOption.REPLACE_EXISTING` | Nếu đích đã tồn tại, cho phép thay thế theo hợp đồng provider | Có thể vẫn thất bại, đặc biệt với một số thư mục không rỗng, quyền truy cập, lock, hoặc lỗi I/O |
| `StandardCopyOption.COPY_ATTRIBUTES` | Yêu cầu sao chép các thuộc tính tệp được hỗ trợ | Bộ thuộc tính có thể khác nhau theo provider; không coi là chép mọi metadata trên mọi hệ |
| `LinkOption.NOFOLLOW_LINKS` | Khi nguồn là symbolic link, không tự động đi theo link; có thể copy chính link | Hỗ trợ/cách tạo link phụ thuộc filesystem; cần chính sách bảo mật riêng |

`CopyOption` là interface marker cho các tùy chọn được các operation hỗ trợ; `StandardCopyOption` và `LinkOption` đều được dùng theo API cụ thể. **Không phải mọi option hợp lệ ở mọi overload**: ví dụ `COPY_ATTRIBUTES` không phải một option mà `Files.copy(InputStream, Path, ...)` được thiết kế để dùng như `Path → Path`.

### 2.2. Vì sao không có COPY_IF_ABSENT option?

**Không truyền `REPLACE_EXISTING`** chính là cách tự nhiên để yêu cầu **không thay thế tệp đã có**. Nếu code muốn chấp nhận “đã tồn tại” như một trạng thái hợp lệ, hãy bắt `FileAlreadyExistsException` và kiểm tra yêu cầu nghiệp vụ, chứ không cần một `CopyOption` giả định như `COPY_IF_ABSENT`.

**Không có option `ATOMIC_COPY` trong `Files.copy`.** `StandardCopyOption.ATOMIC_MOVE` dành cho `Files.move`, không phải option chung cho copy. Thêm `ATOMIC_MOVE` vào `Files.copy` có thể gây `UnsupportedOperationException` hoặc lỗi provider khác.

## 3. Copy mới và copy thay thế: ví dụ chạy độc lập

Tạo file `CopyExistingPolicyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class CopyExistingPolicyDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("copy-policy-");
        Path source = dir.resolve("source.txt");
        Path target = dir.resolve("target.txt");

        try {
            Files.writeString(
                    source, "alpha", StandardCharsets.UTF_8);
            Path returned = Files.copy(source, target);

            System.out.println(
                    "returned-target=" + returned.equals(target));
            System.out.println(
                    "first-content="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));

            Files.writeString(
                    source, "beta", StandardCharsets.UTF_8);

            try {
                Files.copy(source, target);
                System.out.println("unexpected-overwrite");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("existing-rejected=true");
            }

            System.out.println(
                    "target-preserved="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));

            Files.copy(
                    source, target,
                    StandardCopyOption.REPLACE_EXISTING);

            System.out.println(
                    "replaced="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));
            System.out.println(
                    "source-still="
                    + Files.readString(
                        source, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all CopyExistingPolicyDemo.java
java CopyExistingPolicyDemo
```

**stdout chính xác:**

```text
returned-target=true
first-content=alpha
existing-rejected=true
target-preserved=alpha
replaced=beta
source-still=beta
```

**Đọc từng bước:**

1. `Files.createTempDirectory` tạo một vùng thử nghiệm riêng, tránh ghi đè tệp đang được sử dụng trong dự án.
2. Lần đầu `target` chưa tồn tại, `Files.copy(source,target)` tạo tệp đích và trả về chính `target`.
3. Sau khi sửa nguồn thành `"beta"`, lời gọi copy **không có `REPLACE_EXISTING`** thất bại do `target` đã tồn tại; nội dung đích vẫn `"alpha"` trong ca thử cụ thể này.
4. Thêm `REPLACE_EXISTING` cho phép thay thế; đích trở thành `"beta"`.
5. Copy **không xóa source**. `Files.move` mới là API cho thao tác di chuyển, không nên nhầm với copy.
6. Cleanup dùng `finally` và xóa target/source trước khi xóa thư mục. Code ví dụ không chạm vào tệp người dùng ngoài thư mục tạm.

**Đừng biến stdout minh họa thành bảo đảm cho mọi tình huống lỗi:** một lần copy đang chạy có thể thất bại giữa chừng, để lại tệp đích được tạo mới hoặc nội dung chưa đầy đủ. `Files.copy` **không bảo đảm tính nguyên tử** cho toàn bộ thao tác copy, đặc biệt khi đọc/ghi nhiều byte.

## 4. Phân biệt FileAlreadyExistsException với các lỗi khác

Trong một hệ thống thật, một lời gọi copy có thể thất bại bởi nhiều nguyên nhân:

| Lỗi hoặc điều kiện | Ví dụ |
| --- | --- |
| `FileAlreadyExistsException` | Đích đã tồn tại trong chế độ không cho thay thế |
| `NoSuchFileException` | Source không tồn tại hoặc một thành phần đường dẫn chưa có |
| `AccessDeniedException` | Quyền đọc source hoặc ghi target không đủ |
| `DirectoryNotEmptyException` | Cố thay thế/xóa thư mục đích không rỗng trong tình huống provider từ chối |
| `FileSystemException` / `IOException` khác | Lỗi I/O, filesystem readonly, tài nguyên đang bị giữ, không gian đĩa |
| `SecurityException` | Security policy trong một số môi trường |
| `UnsupportedOperationException` | Copy option hoặc chức năng không được hỗ trợ |

`FileAlreadyExistsException` kế thừa `FileSystemException` → `IOException`. Khi triển khai chính sách “nếu tồn tại thì báo trùng”, nên bắt loại **cụ thể** trước, sau đó để các lỗi I/O khác được xử lý/lan truyền đúng tầng.

Đừng bắt mọi `IOException` rồi coi là “tệp đích đã có”:

```java
try {
    Files.copy(source, target);
} catch (FileAlreadyExistsException ex) {
    // Chính sách: thông báo tên đã sử dụng, trả HTTP 409 nếu phù hợp.
} catch (IOException ex) {
    // Chính sách: báo lỗi I/O khác, lưu cause và cho hệ thống xử lý.
}
```

Đây là snippet trong một method đã có các biến và import thích hợp. `HTTP 409 Conflict` chỉ là một ví dụ cách ánh xạ domain error sang HTTP, không phải quy tắc bắt buộc của API Files.

### 4.1. Phân biệt “không ghi đè” và “bỏ qua”

`Files.copy` mặc định **không tự bỏ qua** khi file đích trùng. Nó báo lỗi. Nếu nghiệp vụ quy định “nếu đã có thì xem như thành công”, bạn cần làm rõ: **đã có gì?**

- Đích có cùng checksum/content không?
- Đích có cùng phiên bản và schema không?
- Source có phải dữ liệu mới hơn không?
- Hai tiến trình có thể đồng thời sửa tệp đích không?
- Có cần ngăn bỏ qua nhầm một file khác trùng tên không?

Cách xử lý `catch (FileAlreadyExistsException ignored) {}` có thể hợp lệ cho một cache dùng khóa nội dung và cơ chế xác minh thích hợp. Nhưng **không** nên áp dụng mặc định cho dữ liệu cần cập nhật; nó có thể che một sai lệch quan trọng.

## 5. Chính sách tồn tại: Fail, Replace, Versioned, Verify

Nên mô tả chính sách bằng một tên rõ ràng ở tầng ứng dụng:

| Chính sách | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Fail if exists** | Đích có sẵn là lỗi | Upload mới, tạo bản sao lưu với tên định danh |
| **Replace existing** | Cho phép nội dung đích bị thay thế | Regenerate artifact do ứng dụng sở hữu |
| **Versioned target** | Tạo tên/version mới thay vì ghi đè | Lịch sử báo cáo và snapshot |
| **Verify and reuse** | Chỉ coi “đã có” là hợp lệ khi nội dung và metadata cần thiết đúng | Cache theo hash hoặc artifact immutable |
| **User-confirmed replace** | Cần quyết định từ user/transaction policy | Ghi đè tài liệu người dùng |
| **Staged replace** | Copy sang tệp tạm trước, chỉ sau khi thành công mới chuyển thành đích | Giảm cửa sổ đích chưa đủ dữ liệu khi cập nhật |

`REPLACE_EXISTING` chỉ triển khai **một phần** của chính sách thay thế: nó cho phép operation cố thay thế đích. Nó không tự versioning, tạo backup, audit trail, rollback hay xác minh checksum.

### 5.1. Ví dụ áp dụng chính sách thành API dễ đọc

Tạo file `NamedCopyPolicyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class NamedCopyPolicyDemo {
    enum ExistingPolicy {
        FAIL_IF_EXISTS,
        REPLACE_EXISTING
    }

    static Path copy(Path source, Path target,
            ExistingPolicy policy) throws IOException {
        return switch (policy) {
            case FAIL_IF_EXISTS ->
                    Files.copy(source, target);
            case REPLACE_EXISTING ->
                    Files.copy(
                        source, target,
                        StandardCopyOption.REPLACE_EXISTING);
        };
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("named-copy-");
        Path source = dir.resolve("source.txt");
        Path target = dir.resolve("target.txt");

        try {
            Files.writeString(
                    source, "v1", StandardCharsets.UTF_8);
            copy(source, target, ExistingPolicy.FAIL_IF_EXISTS);
            System.out.println(
                    "created="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));

            Files.writeString(
                    source, "v2", StandardCharsets.UTF_8);

            try {
                copy(source, target,
                     ExistingPolicy.FAIL_IF_EXISTS);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("fail-policy=conflict");
            }

            copy(source, target,
                 ExistingPolicy.REPLACE_EXISTING);
            System.out.println(
                    "replace-policy="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all NamedCopyPolicyDemo.java
java NamedCopyPolicyDemo
```

```text
created=v1
fail-policy=conflict
replace-policy=v2
```

**Lợi ích:** tên enum nêu rõ ý định của caller. Khi thêm chính sách `VERSIONED` hoặc `VERIFY_SAME_CONTENT`, code phải xây dựng luồng xử lý riêng, không tìm cách “chế” một `CopyOption` không có trong Java.

Trong API public, bạn cũng có thể lựa chọn **không expose policy** và luôn giữ mặc định no-overwrite nếu đó là yêu cầu bất biến. Khi cần cho thay thế, cung cấp method có tên `replaceReport(...)` và yêu cầu quyền cao hơn.

## 6. REPLACE_EXISTING không có nghĩa là “luôn ghi đè được”

Khi truyền `REPLACE_EXISTING`, bạn yêu cầu Files cố thay thế đích **theo khả năng của provider**. Không có bảo đảm thành công trong các tình huống sau:

- Target là thư mục không rỗng, không thể thay thế theo quy tắc filesystem.
- Process thiếu quyền ghi hoặc quyền thay đổi entry trong thư mục cha.
- Tệp đang được mở/khóa bởi ứng dụng khác, nhất là nơi OS có cơ chế sharing/locking nghiêm.
- Source không thể đọc hoặc source là file đặc biệt/provider có semantics khác.
- Đường dẫn cha không tồn tại hoặc bị thay đổi trong lúc thao tác.
- Dữ liệu vượt quota/disk space hoặc filesystem có lỗi.
- Tùy chọn được provider hiện tại không hỗ trợ.

**Không nên xử lý bằng cách xóa đích trước rồi copy trong hai thao tác rời rạc** nếu bạn muốn bảo toàn dữ liệu cũ khi source lỗi:

```java
// Không nên làm như sau nếu cần bảo toàn tệp cũ:
// Files.deleteIfExists(target);
// Files.copy(source, target);
```

Nếu copy thất bại sau khi xóa, tệp cũ đã mất. `REPLACE_EXISTING` có thể tránh nhu cầu tự xóa trước, nhưng **bản thân `Files.copy` cũng không cam kết atomic replace hoặc rollback**. Với nhu cầu integrity cao, áp dụng staging/validation trước khi chuyển đích (phần 12).

### 6.1. Đừng kiểm tra exists trước rồi tin kết quả mãi mãi

Mẫu:

```java
if (!Files.exists(target)) {
    Files.copy(source, target);
}
```

vẫn có **TOCTOU race**: một thread/process khác có thể tạo target giữa lúc `exists` và `copy`. Vì vậy:

- Để không ghi đè, gọi `Files.copy(source,target)` **trực tiếp** và bắt `FileAlreadyExistsException`.
- Để cho phép thay thế, gọi `Files.copy(source,target,REPLACE_EXISTING)` và xử lý các ngoại lệ thật.
- Kiểm tra trước có thể phục vụ UX/diagnostics, nhưng không thay thế thao tác cuối với chính sách đúng.
- Với security/transaction mạnh hơn, kiểm soát cả filesystem permissions và concurrency, không trông chờ API copy đơn lẻ giải quyết mọi race.

## 7. Copy thư mục không phải copy đệ quy

Một nhầm lẫn thường gặp: `Files.copy(sourceDir,targetDir)` **không** tự đi qua toàn bộ cây thư mục và sao chép tất cả file con.

Khi source là directory, operation tạo một **directory mới ở đích**; **entries bên trong không được copy** bởi lời gọi đơn lẻ đó.

Tạo file `CopyDirectoryNonRecursiveDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyDirectoryNonRecursiveDemo {
    public static void main(String[] args)
            throws IOException {
        Path workspace =
                Files.createTempDirectory("copy-dir-");
        Path source = workspace.resolve("source");
        Path target = workspace.resolve("target");
        Path child = source.resolve("nested.txt");

        try {
            Files.createDirectory(source);
            Files.writeString(
                    child, "payload", StandardCharsets.UTF_8);

            Files.copy(source, target);

            System.out.println(
                    "target-is-dir="
                    + Files.isDirectory(target));
            System.out.println(
                    "source-child="
                    + Files.exists(child));
            System.out.println(
                    "target-child="
                    + Files.exists(target.resolve("nested.txt")));
            System.out.println(
                    "source-content="
                    + Files.readString(
                        child, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(child);
            Files.deleteIfExists(source);
            Files.deleteIfExists(workspace);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CopyDirectoryNonRecursiveDemo.java
java CopyDirectoryNonRecursiveDemo
```

```text
target-is-dir=true
source-child=true
target-child=false
source-content=payload
```

**Điểm cần nhớ:** `target-child=false` là hành vi đúng, không phải bug. Nếu thực sự cần copy đệ quy, dùng `Files.walkFileTree` với `FileVisitor`, tạo thư mục đích tương ứng rồi copy từng tệp. Cần thêm chính sách:

- Đích có sẵn thì từ chối, merge hay replace?
- Có theo symbolic links không?
- Có nhận symlink vòng lặp không?
- Có copy file attributes không?
- Có xử lý từng lỗi hay dừng toàn bộ?
- Có cần rollback nếu mới copy một phần cây?
- Có chặn nguồn/đích là cùng cây hoặc đích nằm trong source không?

**Không viết `Files.copy(sourceDir, targetDir, REPLACE_EXISTING)` rồi kỳ vọng tree merge**. `REPLACE_EXISTING` xử lý sự tồn tại **của target entry**, không biến operation thành copy đệ quy. Việc thay thế target directory có nội dung còn có thể thất bại.

## 8. Các overload InputStream và OutputStream: đừng nhầm ownership

Ngoài `Path → Path`, `Files.copy` còn có:

- `Files.copy(InputStream in, Path target, CopyOption... options)`: đọc byte từ một `InputStream` và ghi vào tệp đích, trả **số byte được copy (`long`)**.
- `Files.copy(Path source, OutputStream out)`: đọc byte từ tệp source và ghi vào `OutputStream` đã có, trả số byte.

**Không có encode/decode charset ở các overload này**. Chúng copy **byte**, không chuyển văn bản UTF-8 ↔ UTF-16 hay giải thích nội dung một tệp. Nếu dữ liệu là text và cần đổi charset, phải decode theo charset nguồn rồi encode theo charset đích bằng Reader/Writer hoặc codec phù hợp.

**Ownership:** `Files.copy` không tự đóng `InputStream`/`OutputStream` do caller truyền vào. Người tạo/nhận ownership của stream chịu trách nhiệm đóng hoặc quản lý scope theo hợp đồng.

### 8.1. Khi input là InputStream, đích đã tồn tại thì sao?

`Files.copy(in,target)` mặc định từ chối khi target đã có, giống chính sách no-overwrite. `StandardCopyOption.REPLACE_EXISTING` là option được phép sử dụng với overload stream → path.

Không mang mọi `CopyOption` của Path → Path sang overload này: `COPY_ATTRIBUTES` và `NOFOLLOW_LINKS` **không có cùng ý nghĩa** khi nguồn là stream, không phải một Path có filesystem attributes hoặc symlink.

### 8.2. Ví dụ runnable: stream không bị Files.copy đóng

Tạo `CopyInputStreamDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class CopyInputStreamDemo {
    static final class ProbeStream
            extends ByteArrayInputStream {
        boolean closed;

        ProbeStream(byte[] bytes) {
            super(bytes);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("copy-in-");
        Path target = dir.resolve("target.txt");

        try {
            try (ProbeStream input = new ProbeStream(
                    "alpha".getBytes(StandardCharsets.UTF_8))) {
                long bytes = Files.copy(input, target);
                System.out.println("bytes=" + bytes);
                System.out.println(
                        "closed-by-files=" + input.closed);
            }

            System.out.println(
                    "first-text="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));

            try (ProbeStream updated = new ProbeStream(
                    "beta".getBytes(StandardCharsets.UTF_8))) {
                Files.copy(
                        updated, target,
                        StandardCopyOption.REPLACE_EXISTING);
                System.out.println(
                        "replace-closed-by-files="
                        + updated.closed);
            }

            System.out.println(
                    "after-replace="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CopyInputStreamDemo.java
java CopyInputStreamDemo
```

```text
bytes=5
closed-by-files=false
first-text=alpha
replace-closed-by-files=false
after-replace=beta
```

`Files.copy` không đóng input bên trong. Ở đây TWR chủ động đóng `ProbeStream` khi rời khối `try`. Kết quả `closed-by-files=false` được in **trước khi TWR đóng**, chính xác để phân biệt ownership của library operation và caller.

Trong ứng dụng thực, nếu nguồn là network stream hoặc input gắn với file descriptor, quên `close()` có thể gây rò rỉ. Trái lại, nếu stream chỉ được **mượn** từ framework, phương thức helper không tự đóng nó nếu chưa được chuyển ownership.

### 8.3. Ví dụ runnable: Path → OutputStream

Tạo `CopyOutputStreamDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyOutputStreamDemo {
    static final class ProbeOutputStream
            extends ByteArrayOutputStream {
        boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("copy-out-");
        Path source = dir.resolve("source.txt");

        try {
            Files.writeString(
                    source, "hello", StandardCharsets.UTF_8);

            try (ProbeOutputStream output =
                    new ProbeOutputStream()) {
                long bytes = Files.copy(source, output);
                System.out.println("bytes=" + bytes);
                System.out.println(
                        "closed-by-files=" + output.closed);
                System.out.println(
                        "payload="
                        + output.toString(StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CopyOutputStreamDemo.java
java CopyOutputStreamDemo
```

```text
bytes=5
closed-by-files=false
payload=hello
```

Với `Files.copy(Path,OutputStream)`, API **không có đường dẫn đích** để kiểm tra đã tồn tại hay chưa; trạng thái đích do caller quyết định khi **mở stream** (ví dụ mở file append/truncate/no-overwrite) và lúc copy chỉ ghi vào stream đã được cung cấp.

Nếu output là `FileOutputStream` hoặc `Files.newOutputStream`, cần xác định rõ `OpenOption` khi mở. `Files.copy` không tự override `OutputStream` chỉ vì source là Path.

## 9. COPY_ATTRIBUTES: yêu cầu bảo toàn metadata, không phải phép clone tuyệt đối

Theo mặc định, các thuộc tính metadata như thời gian sửa cuối, quyền truy cập, owner hay ACL **không nên được giả định sẽ giống hoàn toàn** giữa source và target.

Với `Path → Path` có thể yêu cầu:

```java
Files.copy(
        source, target,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Đây là snippet trong method đã xử lý `IOException`. `COPY_ATTRIBUTES` có ý nghĩa yêu cầu provider copy một tập thuộc tính; **bộ thuộc tính cụ thể phụ thuộc implementation và provider**.

Phải phân biệt:

- **Nội dung tệp:** các byte được copy từ source.
- **Basic file attributes:** một số mốc thời gian và thuộc tính cơ bản có thể được chuyển theo contract provider.
- **Permissions/owner/ACL/extended attributes:** không bảo đảm sao chép đầy đủ và đồng nhất trên mọi filesystem.
- **File system identity:** hai entry khác nhau, không phải cùng một inode/file ID mặc định chỉ vì copy.
- **Hard links/symlinks:** có semantics riêng, không tự coi mọi loại link đều tương đương.
- **Security metadata:** cần kiểm tra kết quả và policy nếu quyền truy cập là phần quan trọng của yêu cầu.

### 9.1. Ví dụ chạy độc lập: yêu cầu copy attributes

Tạo `CopyAttributesDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class CopyAttributesDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("copy-attrs-");
        Path source = dir.resolve("source.txt");
        Path target = dir.resolve("target.txt");

        try {
            Files.writeString(
                    source, "metadata", StandardCharsets.UTF_8);

            Files.copy(
                    source, target,
                    StandardCopyOption.COPY_ATTRIBUTES);

            System.out.println(
                    "content-same="
                    + Files.readString(
                        source, StandardCharsets.UTF_8)
                    .equals(Files.readString(
                        target, StandardCharsets.UTF_8)));
            System.out.println(
                    "size-same="
                    + (Files.size(source) == Files.size(target)));
            System.out.println(
                    "two-paths=" + !source.equals(target));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CopyAttributesDemo.java
java CopyAttributesDemo
```

```text
content-same=true
size-same=true
two-paths=true
```

Ví dụ chỉ khẳng định phần **nội dung/size** và việc copy diễn ra ở hai đường dẫn khác nhau, **không hard-code** rằng `lastModifiedTime` hoặc ACL phải khớp trên mọi hệ. Muốn kiểm chứng metadata, hãy dùng `Files.readAttributes` trên từng môi trường được hỗ trợ và định nghĩa các yêu cầu thực sự cần bảo toàn.

**Nếu sao chép giữa các provider khác nhau**, các thuộc tính không được hỗ trợ ở đích có thể không sao chép được hoặc operation thất bại. Không nên “bắt tất cả exception rồi vẫn báo thành công” nếu backup yêu cầu metadata đầy đủ.

## 10. Symbolic link: mặc định theo link nguồn và NOFOLLOW_LINKS

`Files.copy(source,target)` thông thường **theo symbolic link ở nguồn** để copy file được link trỏ tới. Nếu muốn copy **chính symbolic link** như một entry, có thể truyền `LinkOption.NOFOLLOW_LINKS`:

```java
Files.copy(
        sourceLink, targetLink,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet với hai `Path`. Khi `sourceLink` là symbolic link, tùy chọn yêu cầu **không resolve nó sang file đích** trong thao tác copy. Hành vi cụ thể và khả năng tạo symbolic link ở đích phụ thuộc provider/permission. Trên Windows, việc tạo symlink có thể phụ thuộc cấu hình/quyền và policy, vì vậy không nên ép một stdout thống nhất cho bài test symlink trên mọi máy.

Một quy trình đúng cho tài nguyên có link cần định nghĩa:

1. Có muốn copy nội dung của **file được trỏ tới** hay tạo một **symlink mới**?
2. Có cho phép symlink trỏ ra ngoài thư mục tin cậy không?
3. Source có thể bị thay thế giữa lúc kiểm tra và lúc mở không?
4. Nếu target đang là symlink, `REPLACE_EXISTING` có thể thay thế **link target entry**, không nên hiểu là bắt buộc ghi xuyên qua link đến dữ liệu mà link trỏ tới.
5. Người nhận backup cần file thực hay chỉ cần một symlink có thể bị hỏng khi chuyển máy?

**Đừng coi `NOFOLLOW_LINKS` là giải pháp hoàn chỉnh chống path traversal.** Nó chỉ điều chỉnh cách copy **nguồn cuối** được xử lý theo contract; các thành phần thư mục cha, race/TOCTOU, mount points, Windows reparse points và quyền truy cập vẫn cần kiểm soát phù hợp.

Nếu muốn bỏ hoàn toàn mọi link không tin cậy, thường cần validate root và traversal theo hệ thống file thực, chạy dưới quyền hạn chế, và tránh các bước kiểm tra/ghi không nguyên tử do đối tượng bên ngoài có thể thay đổi.

## 11. Một đích là directory hoặc tệp bị khóa

Nếu target đã có và là **directory**, `REPLACE_EXISTING` không tương đương với “xóa toàn bộ cây cũ rồi copy cây mới”. Đặc biệt, nếu target directory **không rỗng**, operation thường thất bại vì không thể thay thế nó như một tệp thường.

Nếu target là một tệp đang mở, hành vi phụ thuộc OS, provider và cách các process mở handle. Một hệ thống có thể cho phép thao tác ở hoàn cảnh mà hệ khác từ chối vì sharing violation. Hãy kiểm thử đúng nền tảng triển khai.

**Mẹo vận hành:**

- Khi export ra một thư mục đã tồn tại, đảm bảo mục tiêu là **file path** (không vô tình truyền directory).
- Khi cần tạo **subdirectory**, gọi `Files.createDirectories` trước; `Files.copy` không tự tạo toàn bộ các thư mục cha bị thiếu.
- Khi gặp `FileSystemException`, log message/cause và đường dẫn liên quan (sau khi ẩn phần nhạy cảm) để phân biệt permission, disk full, sharing violation.
- Không tự động retry vô hạn. Với tệp đang bị lock, cần chính sách retry có giới hạn, backoff và ngữ cảnh nghiệp vụ phù hợp.
- Không dùng `Files.exists(target)` để suy ra chắc chắn “không có file, có thể overwrite không cần option”.

## 12. Copy tạm rồi mới thay đích: staged replacement

`Files.copy(source,target,REPLACE_EXISTING)` có thể thao tác trực tiếp lên đường dẫn đích. Nếu đang ghi mà xảy ra lỗi, trạng thái đích không được API bảo đảm luôn là phiên bản cũ hoặc mới hoàn chỉnh.

Một chiến lược thường gặp khi cập nhật tài liệu quan trọng:

1. Xác định target và parent directory tin cậy.
2. Tạo một tệp tạm **trong cùng thư mục đích**.
3. Copy nội dung source vào tệp tạm.
4. Có thể xác minh kích thước, checksum, schema hoặc chữ ký trước khi xuất bản.
5. Khi đã sẵn sàng, **di chuyển tệp tạm** để thay đích với chính sách được định nghĩa.
6. Dọn tệp tạm nếu có lỗi.

**Rất quan trọng:** staged replacement chỉ giúp thu hẹp phạm vi có thể ảnh hưởng đến target. Nếu dùng `Files.move(stage,target,REPLACE_EXISTING)`, Java **không cam kết move luôn atomic**. Có thể thử `ATOMIC_MOVE` nếu provider hỗ trợ, nhưng semantics khi target đã tồn tại ở chế độ atomic move **phụ thuộc implementation**; đừng khẳng định có portable atomic overwrite chỉ bằng cách thêm hai flags.

### 12.1. Ví dụ runnable: stage rồi replace (không tuyên bố atomic)

Tạo `StagedCopyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class StagedCopyDemo {
    static void stagedReplace(Path source, Path target)
            throws IOException {
        Path parent = target.toAbsolutePath().getParent();
        if (parent == null) {
            throw new IllegalArgumentException("target has no parent");
        }

        Path staging = Files.createTempFile(
                parent, ".stage-", ".tmp");
        try {
            Files.copy(
                    source, staging,
                    StandardCopyOption.REPLACE_EXISTING);

            Files.move(
                    staging, target,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(staging);
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("stage-copy-");
        Path source = dir.resolve("source.txt");
        Path target = dir.resolve("target.txt");

        try {
            Files.writeString(
                    source, "version-2", StandardCharsets.UTF_8);
            Files.writeString(
                    target, "version-1", StandardCharsets.UTF_8);

            stagedReplace(source, target);

            System.out.println(
                    "target="
                    + Files.readString(
                        target, StandardCharsets.UTF_8));
            System.out.println(
                    "source="
                    + Files.readString(
                        source, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all StagedCopyDemo.java
java StagedCopyDemo
```

```text
target=version-2
source=version-2
```

**Vì sao copy vào staging cần `REPLACE_EXISTING`?** `Files.createTempFile` đã **tạo entry thật**. Nếu gọi `Files.copy(source, staging)` mà không option, chính staging sẽ gây `FileAlreadyExistsException`! Ở đây staging là tệp do ứng dụng vừa tạo và sở hữu, nên cho phép thay thế nó là có chủ đích.

**Những giới hạn còn lại:**

- Bản thân `Files.copy` vào staging vẫn có thể bị gián đoạn, nhưng khi chưa move thì target cũ chưa bị thao tác bởi copy. Nếu thất bại, `finally` thử xóa staging.
- `Files.move(..., REPLACE_EXISTING)` có thể thất bại, tùy provider và trạng thái target. Không tuyên bố “atomic rollback” nếu không có bảo đảm cụ thể.
- Nếu cần **atomic publish**, cần xác minh provider hỗ trợ `ATOMIC_MOVE`, xử lý `AtomicMoveNotSupportedException`, và định nghĩa riêng chính sách khi target đã tồn tại. Kết hợp `ATOMIC_MOVE` với `REPLACE_EXISTING` không mặc nhiên cho portable atomic overwrite.
- **Durability** sau crash còn phụ thuộc flush/sync dữ liệu và metadata directory, filesystem và OS. Kể cả thao tác rename nguyên tử, điều đó không tự có nghĩa dữ liệu đã an toàn trên ổ cứng sau mất điện.
- Với nhiều writer, cần thiết kế version check/concurrency control; “copy rồi move” không tự quyết định update nào thắng.
- Tệp đích chỉ nên được thay thế nếu policy/permission cho phép; staging không phải cách né kiểm tra bảo mật.

## 13. Sao chép và kiểm tra tính toàn vẹn

Sau khi copy, ứng dụng có thể cần xác minh dữ liệu đã sao chép đúng.

**Các mức xác minh khác nhau:**

- `Files.size(source) == Files.size(target)`: xác minh kích thước, **không chứng minh bytes giống nhau**.
- `Files.mismatch(source,target) == -1`: trên Java 12+ cho biết hai tệp không có byte khác biệt trong lần so sánh đó. Các nguồn có thể thay đổi đồng thời nên đây **không phải snapshot transaction**.
- Hash mật mã như `SHA-256`: có thể dùng khi cần digest, nhưng phải xác định thời điểm/chính sách kiểm tra và dữ liệu nguồn đáng tin. Hai tệp hash giống nhau là bằng chứng rất mạnh cho nội dung giống nhau, không tự xác minh nguồn gốc/chữ ký.
- So sánh metadata: `COPY_ATTRIBUTES` và các file attributes liên quan; không tự đồng nhất metadata với nội dung byte.
- Schema/format validation: file JSON/CSV/archive hợp lệ cần parser/validator phù hợp; byte giống nhau chưa bảo đảm nội dung được kỳ vọng về nghiệp vụ.

### 13.1. Ví dụ runnable: Files.mismatch

Tạo `CopyVerifyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyVerifyDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("copy-verify-");
        Path source = dir.resolve("source.txt");
        Path target = dir.resolve("target.txt");

        try {
            Files.writeString(
                    source, "abc", StandardCharsets.UTF_8);
            Files.copy(source, target);

            System.out.println(
                    "size-equal="
                    + (Files.size(source) == Files.size(target)));
            System.out.println(
                    "bytes-equal="
                    + (Files.mismatch(source, target) == -1L));

            Files.writeString(
                    target, "abd", StandardCharsets.UTF_8);
            System.out.println(
                    "same-size="
                    + (Files.size(source) == Files.size(target)));
            System.out.println(
                    "bytes-after-change="
                    + (Files.mismatch(source, target) == -1L));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CopyVerifyDemo.java
java CopyVerifyDemo
```

```text
size-equal=true
bytes-equal=true
same-size=true
bytes-after-change=false
```

**Đừng chỉ so kích thước.** Hai tệp có cùng 3 byte nhưng khác nội dung hoàn toàn có thể có size bằng nhau. `Files.mismatch` đọc nội dung và trả về index byte đầu tiên khác nhau hoặc `-1L` khi không có mismatch trong lần đọc.

**Một sự khác biệt cần nhớ:** `Files.mismatch` có từ Java 12, nên là API hiện đại trong Java 17+. Nó không phải lựa chọn cho mã buộc phải chạy trên Java 7; bài này hướng tới JDK 17+ theo ghi chú của module.

## 14. Copy khác move, create, backup và sync

| Operation | Ý nghĩa chính | Điều không tự bảo đảm |
| --- | --- | --- |
| `Files.copy(source,target)` | Tạo bản sao của source ở target | Không xóa source, không atomic, không recursive directory |
| `Files.copy(...,REPLACE_EXISTING)` | Cho phép cố thay target cũ | Không có rollback hoặc atomic replace mặc định |
| `Files.move(source,target)` | Di chuyển/đổi vị trí entry | Không phải copy tạo hai bản độc lập |
| `Files.writeString(path,text,...)` | Ghi nội dung văn bản đã encode | Không copy metadata của file khác, không tự quản lý backup |
| `Files.createFile(path)` | Tạo file mới, báo lỗi nếu đã có | Không tự điền nội dung từ source |
| `Files.createTempFile(...)` | Tạo file tạm mới do ứng dụng quản lý | Không tự xóa khi ra khỏi scope |
| `Files.mismatch(source,target)` | So nội dung byte tại thời điểm thực thi | Không chứng minh giao dịch atomic, nguồn không bị thay đổi |
| `Files.copy(InputStream,target)` | Tiêu thụ stream và ghi đích | Không đóng stream của caller, không tự chuyển charset |

**Một điều hay bị hiểu sai:** `Files.copy` không phải công cụ backup đầy đủ nếu backup yêu cầu snapshot nhất quán, nhiều file có quan hệ với nhau, metadata bảo mật, quyền truy cập, recovery history và durability. Với nhu cầu đó, thiết kế backup/transaction chuyên dụng cần được cân nhắc.

## 15. Security: root, symbolic link và tệp đích không đáng tin

Một service nhận tên file từ người dùng không nên làm ngay:

```java
Path target = uploadRoot.resolve(userFileName);
Files.copy(source, target,
           StandardCopyOption.REPLACE_EXISTING);
```

Đây là snippet. Nếu input chứa `..` hoặc một absolute path, đường dẫn có thể thoát khỏi thư mục dự kiến. Nếu `REPLACE_EXISTING` được dùng không có chính sách, dữ liệu khác trong vùng ứng dụng có thể bị ghi đè.

Một bước **lexical check** ban đầu:

```java
static Path lexicalTarget(Path trustedRoot, String relativeName) {
    Path relative = Path.of(relativeName);
    if (relative.isAbsolute()) {
        throw new IllegalArgumentException("absolute path");
    }
    Path root = trustedRoot.toAbsolutePath().normalize();
    Path target = root.resolve(relative).normalize();
    if (!target.startsWith(root)) {
        throw new IllegalArgumentException("outside root");
    }
    return target;
}
```

Snippet là method hoàn chỉnh nhưng cần import `Path` trong class. **Đây không phải bảo vệ đầy đủ**: symbolic link, junction/reparse point, mount point và việc thay đổi đồng thời có thể làm tệp thực nằm ngoài root dù lexical `startsWith` đúng.

**Đối với dữ liệu không đáng tin, hãy quyết định chính sách chặt hơn:**

- Giới hạn quyền của process và thư mục đích.
- Ưu tiên server-generated filename, opaque ID và thư mục riêng theo tenant.
- Không cho người dùng ghi đè tùy ý lên file hệ thống hoặc file của người khác.
- Giới hạn loại file, kích thước, tổng dung lượng/quota trước và trong lúc nhận dữ liệu.
- Định nghĩa xử lý symbolic links; `NOFOLLOW_LINKS` không giải quyết mọi component của path.
- Đánh giá các primitive như `SecureDirectoryStream` nếu provider hỗ trợ, kết hợp thao tác dựa trên directory handle để hạn chế TOCTOU.
- Có audit log/transaction policy nếu thay thế file có hậu quả nghiệp vụ.
- Kiểm tra nội dung đích theo schema/antivirus nếu ứng dụng nhận upload từ bên ngoài; copy byte chính xác không đồng nghĩa dữ liệu an toàn.

**Đặc biệt với REPLACE_EXISTING:** quyền thay thế tệp thường là quyền nhạy cảm hơn quyền tạo tên mới. Hãy mô hình hóa quyền đó trong API và kiểm tra authorization riêng, thay vì cho mọi request đi qua một method copy tổng quát có bật overwrite.

## 16. Những lỗi phổ biến

| Lỗi | Tại sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `Files.copy` luôn ghi đè | Mặc định từ chối target có sẵn | Chỉ thêm `REPLACE_EXISTING` khi policy cho phép |
| Bắt mọi `IOException` rồi bỏ qua | Có thể là permission, disk full hoặc dữ liệu chưa đầy đủ | Bắt `FileAlreadyExistsException` riêng, báo lỗi khác rõ |
| Xóa target trước rồi mới copy | Nếu copy thất bại, mất bản cũ | Cân nhắc staged update, chính sách replace rõ |
| Dùng `REPLACE_EXISTING` như bảo đảm atomic | API copy không atomic | Nếu cần atomic publish, thiết kế riêng và kiểm tra provider |
| Copy thư mục mong đợi recursive | Một copy không đi qua cây con | Dùng `Files.walkFileTree` với policy rõ |
| Copy rồi cho rằng source bị mất | Copy không move | Dùng `Files.move` nếu thật sự muốn di chuyển |
| Dùng `COPY_ATTRIBUTES` rồi nghĩ mọi metadata khớp | Provider-dependent | Đọc và verify những thuộc tính cần thiết |
| Copy symlink mà không có chính sách | Có thể follow source link theo mặc định | Xác định theo link hay copy link và kiểm tra security |
| Dùng `NOFOLLOW_LINKS` như giải pháp toàn diện | Không ngăn traversal ở parent hoặc TOCTOU | Kiểm tra filesystem và quyền truy cập |
| Truyền `COPY_ATTRIBUTES` cho InputStream overload | Không có metadata Path từ stream | Dùng đúng options được overload hỗ trợ |
| Nghĩ `Files.copy` đóng stream tự động | Caller vẫn sở hữu stream | TWR tại owner |
| Dùng `Files.size` để chứng minh data giống | Size equal vẫn có thể bytes khác | Dùng `Files.mismatch`/checksum nếu cần |
| Tính thêm tên đích từ input rồi bật overwrite | Dễ ghi sai vùng/quyền | Validate target và quyền tại boundary |
| `Files.exists(target)` trước copy, sau đó tin không có race | Check và action tách rời | Xử lý conflict ngay tại copy |
| Copy source vào file temp đã tạo nhưng quên `REPLACE_EXISTING` | Temp entry đã tồn tại | Cho phép thay **temp thuộc sở hữu** hoặc chọn cách tạo temp khác |
| Dùng `ATOMIC_MOVE` làm option cho `Files.copy` | Option thuộc move | Dùng staged copy, move theo hợp đồng |
| Nghĩ close/flush sau copy bảo đảm fsync | Close không đồng nghĩa disk durability | Dùng cơ chế sync và bảo đảm hệ thống nếu cần |

## 17. Checklist review PR

1. Source, target có cùng provider không? Nếu khác provider, có kiểm tra quyền, metadata và khả năng copy không?
2. Target đã tồn tại là **conflict** hay **replace** theo domain?
3. Nếu replace, ai có quyền cho phép và có cần backup/versioning không?
4. Có tình huống source và target là cùng tệp/alias/symlink không?
5. Thư mục cha của target có tồn tại không? Có nên tạo hay từ chối?
6. Có bắt đúng `FileAlreadyExistsException`, không nuốt mọi `IOException` không?
7. Có đang dùng `Files.exists` như cách “khóa” trước copy không?
8. Nguồn/đích có thể là symbolic link? Chính sách follow link là gì?
9. Có cần `COPY_ATTRIBUTES` và có verify metadata thực sự quan trọng không?
10. Có đang copy directory nhưng kỳ vọng cả cây được sao chép không?
11. Dữ liệu có vượt quota, disk space hoặc kích thước tối đa cho phép không?
12. Nếu copy thất bại giữa chừng, target/staging bị dọn thế nào?
13. Nếu cần integrity, có hash/`Files.mismatch`/validation theo hợp đồng không?
14. Nếu dùng stream overload, caller có đóng stream đúng ownership không?
15. Nếu dùng staged replace, có hiểu rằng `Files.move(REPLACE_EXISTING)` không tự bảo đảm atomic không?
16. Có test trên filesystem/OS đích, đặc biệt với link, ACL, lock và provider khác nhau không?
17. Có cần audit/log theo chính sách dữ liệu, và log có tránh lộ đường dẫn nhạy cảm không?

## 18. Bài tập

**Bài 1 — No-overwrite:** chạy `CopyExistingPolicyDemo`, dự đoán kết quả ba lần copy. Đổi `"alpha"` thành chuỗi tiếng Việt; kiểm tra byte và văn bản với UTF-8.

**Bài 2 — Chọn policy:** chạy `NamedCopyPolicyDemo`. Viết thêm policy `VERIFY_AND_REUSE`: nếu target đã có, dùng `Files.mismatch` để kiểm tra nội dung có giống source; nếu khác, ném domain-specific conflict.

**Bài 3 — Directory copy:** chạy `CopyDirectoryNonRecursiveDemo`. Thiết kế một `SimpleFileVisitor<Path>` tạo directory ở đích và copy từng file, chú ý việc target directory đã tồn tại và cycle/link.

**Bài 4 — Stream ownership:** chạy `CopyInputStreamDemo` và `CopyOutputStreamDemo`. Xác định lúc nào `closed` chuyển từ false sang true. Giải thích vì sao không nên đóng borrowed stream của framework.

**Bài 5 — Attributes:** chạy `CopyAttributesDemo` và đọc `Files.getLastModifiedTime` của source/target. Kiểm tra trên filesystem khác và ghi nhận sự khác biệt nếu metadata không được bảo toàn đầy đủ.

**Bài 6 — Staging:** chạy `StagedCopyDemo`, cố tình sử dụng source bị thiếu để thấy staging cleanup; xác minh target cũ không bị đụng tới trước giai đoạn move. Đừng khẳng định atomic overwrite nếu chưa có chứng cứ provider.

**Bài 7 — Verify bytes:** chạy `CopyVerifyDemo`. Thử đổi tệp đích thành `"abd"` để thấy size vẫn bằng mà `Files.mismatch` phát hiện khác nội dung.

**Bài 8 — Security:** thêm endpoint nhận tên đích. Chứng minh tên `"../outside.txt"` phải bị từ chối; giải thích vì sao vẫn cần bảo vệ symlink/TOCTOU bên cạnh kiểm tra lexical.

**Bài 9 — Thiết kế product:** viết một bảng policy cho ba ca sử dụng: upload user document, regenerate build artifact, lưu lịch sử backup. Chọn Fail/Replace/Versioned và giải thích quyền, rủi ro mất dữ liệu và cách recovery.

## 19. Tóm tắt

- **`Files.copy(Path,Path)` mặc định không ghi đè** target đã tồn tại; conflict thường là `FileAlreadyExistsException`.
- **`StandardCopyOption.REPLACE_EXISTING`** cho phép cố thay thế target, nhưng có thể thất bại và **không tự bảo đảm atomic replace, backup hay rollback**.
- **`COPY_ATTRIBUTES`** yêu cầu copy metadata được provider hỗ trợ; **`NOFOLLOW_LINKS`** điều chỉnh hành vi với symbolic link nguồn.
- **Một lần copy directory không recursive**; dùng `walkFileTree` nếu muốn copy cây có kiểm soát.
- **Các overload stream trả số byte và không tự đóng stream của caller**; option hỗ trợ phụ thuộc overload.
- **Staged copy** có thể giúp tránh thao tác trực tiếp lên target cho đến khi dữ liệu staging sẵn sàng, nhưng bước publish vẫn cần chính sách concurrency, atomicity và durability riêng.
- **`Files.mismatch`** kiểm tra nội dung byte mạnh hơn chỉ so kích thước, song vẫn không phải transaction snapshot.
- **Bảo mật path và quyền overwrite** phải được quyết định ở tầng ứng dụng, không được `Files.copy` xử lý tự động.

## Tài liệu chính thức

- [Files.copy — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#copy(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): overload Path → Path, link, attributes và exception.
- [Files.copy — InputStream → Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#copy(java.io.InputStream,java.nio.file.Path,java.nio.file.CopyOption...)): option và stream lifecycle.
- [Files.copy — Path → OutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#copy(java.nio.file.Path,java.io.OutputStream)): số byte copy và ownership.
- [StandardCopyOption — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html): `REPLACE_EXISTING`, `COPY_ATTRIBUTES`, `ATOMIC_MOVE`.
- [LinkOption — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Files.mismatch — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path)): byte comparison.
