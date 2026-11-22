# Kiểm thử quyền truy cập và hỗ trợ của hệ điều hành khi làm việc với liên kết tệp

**Chủ đề:** Java 7 — Liên kết tệp  
**Bài học:** Kiểm thử quyền truy cập và hỗ trợ của hệ điều hành  
**Nền tảng:** Java 17+ và NIO.2 (`java.nio.file`). Những API `Files.createSymbolicLink`, `Files.createLink`, `Files.readSymbolicLink`, `Files.isSymbolicLink`, `Files.isSameFile`, `FileStore` và `LinkOption.NOFOLLOW_LINKS` vẫn là kiến thức áp dụng với Java hiện đại.

## 1. Vấn đề: API Java tồn tại không có nghĩa OS cho phép thao tác

Ứng dụng có thể viết Java đúng cú pháp và biên dịch sạch nhưng vẫn thất bại khi tạo symbolic link hoặc hard link. Nguyên nhân có thể đến từ **filesystem**, **file provider**, **quyền của tài khoản**, **chính sách của hệ điều hành**, **container/mount**, trạng thái **file đang dùng** hoặc chính dữ liệu đầu vào.

Phải tách ít nhất ba câu hỏi:

1. **Tính năng có được provider/filesystem hỗ trợ không?** Ví dụ filesystem trong một ZIP provider có thể không hỗ trợ symbolic link, dù `Path` và `Files` vẫn tồn tại.
2. **Tiến trình hiện tại có được phép thực hiện operation không?** Trên một số cấu hình Windows, tạo symbolic link có thể bị từ chối do quyền/chính sách; điều đó không chứng minh mọi Windows machine đều không hỗ trợ symlink.
3. **Thao tác cụ thể có thành công lúc này không?** Ngay cả khi quyền và tính năng phù hợp, source có thể đã biến mất, entry đích đã có tên, path nằm trên file store khác hoặc I/O phát sinh lỗi.

**Nguyên tắc kiểm thử:** tạo môi trường tạm **trên chính filesystem mục tiêu**, chạy thao tác thật, quan sát **exception class/cause**, verify trạng thái đã tạo và dọn đúng ownership. Không kết luận support dựa duy nhất vào tên OS, và không sửa quyền của toàn hệ thống chỉ để ép một bài test xanh.

### 1.1. Bản đồ câu hỏi và API

| Điều cần kiểm tra | API có ích | Điều KHÔNG được suy ra |
| --- | --- | --- |
| Có thể tạo symbolic link ở thư mục này? | `Files.createSymbolicLink(link,target)` trong test cô lập | Không thể kết luận chỉ từ `os.name` |
| Có thể tạo hard link đến tệp này? | `Files.createLink(alias,existing)` | Không giống quyền tạo symbolic link |
| Entry có là symlink? | `Files.isSymbolicLink(path)`; `readAttributes(..., NOFOLLOW_LINKS)` | Không chứng minh target cuối tồn tại |
| Target được lưu là gì? | `Files.readSymbolicLink(link)` | Không tự trả real path hoặc chứng minh target an toàn |
| Hai đường dẫn trỏ cùng một file? | `Files.isSameFile(a,b)` | Không phải luôn kiểm tra I/O nếu hai `Path` đã bằng nhau |
| File có vẻ đọc/ghi/thực thi được? | `Files.isReadable`, `isWritable`, `isExecutable` | Không bảo đảm thao tác tiếp theo thành công |
| Provider hỗ trợ metadata POSIX/ACL? | `Files.getFileAttributeView`, `FileStore.supportsFileAttributeView` | Không chứng minh tạo symlink/hard link được |
| File thật có đọc/ghi được bây giờ? | `Files.newInputStream`, `readString`, `writeString` | Không khóa trạng thái quyền mãi mãi |
| Link có bị đứt target? | `Files.exists(link)` và `exists(link,NOFOLLOW_LINKS)` | `false` không luôn là chứng minh “entry chưa tồn tại” |

Một chương trình kiểm thử tốt báo **PASS**, **SKIPPED / NOT AVAILABLE IN THIS ENVIRONMENT** hoặc **FAIL**, theo contract cụ thể. Không nên biến mọi `IOException` thành “không hỗ trợ”.

## 2. Phân biệt symbolic link và hard link trước khi kiểm thử

**Symbolic link** lưu một target pathname; target có thể tương đối hoặc tuyệt đối, có thể không tồn tại tại thời điểm tạo. Khi mở qua liên kết, filesystem diễn giải target theo quy tắc provider.

```java
Path link = dir.resolve("alias.txt");
Path targetStored = Path.of("real.txt");
Files.createSymbolicLink(link, targetStored);
```

Đây là **snippet**, cần import `Path`/`Files` và xử lý `IOException`. Target tương đối `real.txt` được diễn giải từ **parent của link**, không phải từ working directory của JVM.

**Hard link** là directory entry khác tham chiếu **cùng file** trên filesystem có hỗ trợ; nó không lưu một target string như symlink.

```java
Path existing = dir.resolve("real.txt");
Path alias = dir.resolve("hard-alias.txt");
Files.createLink(alias, existing);
```

Đây cũng là snippet. `existing` phải là file phù hợp đã tồn tại; các hạn chế của file store/provider áp dụng. Hard link nói chung cần cùng filesystem, và việc tạo hard link tới directory thường bị giới hạn hoặc không được hỗ trợ.

**Đừng trộn hai nhóm kiểm thử**: một runtime có thể hỗ trợ hard links mà không cho tài khoản hiện tại tạo symbolic links; hoặc ngược lại tùy provider/chính sách. Nếu test symlink bị từ chối, điều đó không xác định kết quả hard-link test.

### 2.1. Bảng so sánh dùng khi viết integration tests

| Tình huống | Symlink | Hard link |
| --- | --- | --- |
| Tên đích khi tạo | Có thể là relative/absolute pathname | Là `Path existing` của file có thật |
| Có thể target chưa tồn tại? | Có thể trên provider hỗ trợ | Không phải mô hình hard link |
| Hai alias trỏ cùng đối tượng file? | Khi target được resolve và còn tồn tại | Có, ở thời điểm đang tham chiếu cùng file |
| Target bị xóa khỏi thư mục ban đầu | Link có thể dangling | Alias khác vẫn có thể truy cập dữ liệu |
| Đổi parent của alias | Có thể đổi ý nghĩa relative symlink | Không đổi target theo relative pathname |
| Quyền tạo | Có thể có yêu cầu/quy định đặc biệt của OS | Có thể chịu quota/ACL/volume/same-file-store policy |
| `Files.readSymbolicLink` | Dùng để đọc target string | Không dùng cho hard link |
| `Files.isSameFile` | Khi link còn dẫn tới file tồn tại | Có thể xác minh cùng file |
| Xóa alias | Xóa entry link, không tự xóa target file | Xóa một directory entry; dữ liệu có thể còn qua entry khác |

Đừng dùng `Files.copy` làm phép thay thế tương đương cho `Files.createLink`: copy dữ liệu có thể tạo **hai file riêng**, không có semantics chia sẻ cùng đối tượng file.

## 3. Thiết kế ma trận kiểm thử theo hệ điều hành và provider

Một ma trận kết quả nên có ít nhất:

- **PASS:** operation tạo link thành công, và assertions về hành vi link đều đúng.
- **SKIPPED_CREATE_UNAVAILABLE:** thử tạo link trong test tự chứa nhưng không thực hiện được do giới hạn môi trường đã ghi nhận; các assertions yêu cầu link thật **không được chạy**.
- **FAIL:** tạo được link nhưng dữ liệu/định danh không đúng, hoặc một lỗi phát sinh trong quá trình verify, cleanup, hoặc ngoài nhánh được phép skip.
- **CONFLICT:** pathname đích đã tồn tại, là một lỗi setup hay vấn đề concurrency, **không phải** bằng chứng “filesystem không hỗ trợ link”.
- **ENVIRONMENT_ERROR:** thiếu quyền, mount không sẵn sàng, đường dẫn không hợp lệ hoặc lỗi thiết lập tệp tạm; cần phân loại cụ thể theo log/cause.

Trong bài học tự chạy này, ví dụ dùng `symlink=UNAVAILABLE_CREATE` hoặc `hardlink=UNAVAILABLE_CREATE` chỉ để thông báo **chưa kiểm thử được đường thành công trong runtime hiện tại**. Không nên tự khẳng định nguyên nhân duy nhất là thiếu feature; `IOException` có thể là một lỗi môi trường khác. Trong CI production, hãy phân biệt các exception và ràng buộc chính sách nghiêm ngặt hơn.

### 3.1. Ma trận tối thiểu cho CI

| Hệ thống cần hỗ trợ | Test | Kỳ vọng hợp lý |
| --- | --- | --- |
| Linux/POSIX trên filesystem hỗ trợ link | Tạo/read/delete symlink + relative target | PASS; lỗi là tín hiệu cần điều tra |
| Windows có cấu hình cho phép symlink | Tạo/read/delete symlink | PASS, kiểm thử loại target file/directory |
| Windows thiếu quyền/chính sách symlink | Tạo symlink | Nếu tính năng tùy chọn: SKIP có lý do; nếu bắt buộc: FAIL setup |
| Filesystem hỗ trợ hard link | `Files.createLink`, `Files.isSameFile` | PASS; không dựa vào symlink test |
| Provider không hỗ trợ link | Tạo symlink/hard link | Optional test skip, mandatory feature fail |
| Volume/cloud/network mount đặc thù | Kiểm tra các operation thật tại mount đó | Không suy từ kết quả test trên ổ hệ thống |
| Vùng dữ liệu không đáng tin | Symlink traversal và path boundary | Kiểm tra thêm security, TOCTOU và root policy |

**Một test được skip không phải chứng cứ tính năng đã được xác minh.** Dashboard CI cần thể hiện số test skipped và lý do; nếu symlink là tính năng bắt buộc nhưng cả pipeline chỉ chạy các nhánh skip, đừng xuất bản trạng thái “đã test symlink đầy đủ”.

## 4. Thư mục tạm nên tạo ở đâu?

`Files.createTempDirectory("link-test-")` tạo directory độc lập trong vùng temp của default filesystem. Phù hợp cho bài học và unit/integration test cơ bản vì không đụng tới thư mục ứng dụng thật.

Tuy nhiên, **support có thể khác theo volume và mount**. Nếu sản phẩm cần thao tác trong một directory do application quản lý, hãy tạo thư mục tạm **bên dưới parent được phép** trên chính filesystem đó, sau khi đã xác minh root đáng tin.

```java
Path root = Path.of("approved", "workspace");
Path sandbox = Files.createTempDirectory(root, "link-test-");
```

Đây là snippet; `root` phải tồn tại, quyền tạo directory phải hợp lệ. Nó không mặc nhiên tạo `approved/workspace`. Dữ liệu test chỉ được dọn trong sandbox riêng và phải tránh race/hậu quả nếu root bị kẻ khác thay đổi.

### 4.1. Khi cleanup, chỉ xóa những gì test đã tạo

Với symbolic link: `Files.deleteIfExists(link)` xóa **entry link**, không xóa file target qua link. Với hard link, xóa alias cũng chỉ xóa directory entry đó; nếu entry gốc còn tồn tại thì nội dung vẫn có thể truy cập.

**Thứ tự cleanup đề nghị:**

1. Đóng streams/file handles do test mở.
2. Xóa symlink/hard-link aliases trong test.
3. Xóa source/target test files do test sở hữu.
4. Xóa các thư mục con rồi đến thư mục sandbox.
5. Không chạy thao tác recursive delete trên một `Path` từ client hoặc symlink traversal không đáng tin.

Không để catch trong phần kiểm thử tạo link **ăn luôn lỗi cleanup** rồi báo PASS. Trong các ví dụ, chỉ catch quanh `Files.createSymbolicLink` hoặc `Files.createLink` khi quyết định skip; một lỗi xảy ra **sau khi đã tạo link** vẫn được xem là lỗi test.

## 5. Kiểm tra attribute views và file store: giới hạn của feature detection

`FileStore` cho phép hỏi một file store có hỗ trợ **attribute view** như basic, POSIX hoặc ACL hay không. `Files.getFileAttributeView` lấy view gắn với một `Path`.

Ví dụ:

```java
FileStore store = Files.getFileStore(path);
boolean posixView = store.supportsFileAttributeView("posix");
boolean aclView = store.supportsFileAttributeView("acl");

PosixFileAttributeView posix =
        Files.getFileAttributeView(
            path, PosixFileAttributeView.class);
```

Đây là snippet với các import và `path` đã có. Nó giúp xác định **khả năng quản lý metadata**, không phải khả năng tạo link.

**Sai lầm lớn:** `posixView == true` không suy ra `Files.createSymbolicLink` chắc chắn thành công; `aclView == true` không suy ra hard link được hỗ trợ. Ngay trong cùng filesystem, quyền tạo entry phụ thuộc directory, identity hiện tại và chính sách OS.

Các view thường gặp:

| View | Phạm vi |
| --- | --- |
| `BasicFileAttributeView` | Loại file, size, timestamps và basic attributes; khả dụng theo contract NIO.2 |
| `PosixFileAttributeView` | Owner/group và chín bit quyền POSIX |
| `AclFileAttributeView` | Entries trong access control list, hữu ích trên provider ACL |
| `DosFileAttributeView` | DOS attributes như readonly/hidden, tùy provider |
| `FileOwnerAttributeView` | Owner theo cơ chế provider |

Không tự map ACL của Windows sang một chuỗi `rwxrwxrwx` đầy đủ rồi dùng để quyết định quyền thực tế: mô hình ACL có named principals, inheritance và access rules phong phú hơn chín bit.

### 5.1. Ví dụ runnable: nhận diện view mà không suy đoán symlink support

Tạo `LinkEnvironmentProbeDemo.java`:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;

public class LinkEnvironmentProbeDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("link-env-");
        Path file = dir.resolve("data.txt");

        try {
            Files.writeString(file, "data");

            FileStore store = Files.getFileStore(file);
            BasicFileAttributeView basic =
                    Files.getFileAttributeView(
                        file, BasicFileAttributeView.class);
            PosixFileAttributeView posix =
                    Files.getFileAttributeView(
                        file, PosixFileAttributeView.class);
            AclFileAttributeView acl =
                    Files.getFileAttributeView(
                        file, AclFileAttributeView.class);

            // Chỉ probe capability metadata; không đoán khả năng tạo link.
            boolean probeComplete = store != null
                    && basic != null
                    && (posix == null
                        || posix.name().equals("posix"))
                    && (acl == null
                        || acl.name().equals("acl"));

            System.out.println(
                    "attribute-probe-complete=" + probeComplete);
            System.out.println(
                    "temporary-file-exists="
                    + Files.isRegularFile(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LinkEnvironmentProbeDemo.java
java LinkEnvironmentProbeDemo
```

```text
attribute-probe-complete=true
temporary-file-exists=true
```

Program chạy cả khi `posix` hoặc `acl` không có trên provider hiện tại: kết quả **không in một giá trị support cố định** phụ thuộc OS. Việc `BasicFileAttributeView` khả dụng không đồng nghĩa filesystem hỗ trợ symbolic link, nhưng xác nhận cách truy vấn metadata chuẩn.

Trong production, có thể log `store.type()`, `store.name()` và `store.supportsFileAttributeView(...)` khi troubleshooting, nhưng cần xem đó là **thông tin hỗ trợ chẩn đoán**, không phải cơ sở duy nhất để authorize thao tác.

## 6. Integration test: thử tạo symbolic link thật

`Files.createSymbolicLink(link, storedTarget)` là phép thử trực tiếp. Một test chỉ kiểm tra `Files.isSymbolicLink` trên một pathname chưa được tạo **không xác minh rằng process hiện tại có thể tạo link**.

Nên tạo source và link trong một sandbox mới, sử dụng **relative stored target** để tránh phụ thuộc absolute temp path. Sau khi tạo thành công, kiểm tra:

1. `Files.isSymbolicLink(link)` trả true.
2. `Files.readSymbolicLink(link)` trả target được lưu.
3. `Files.isSameFile(link,source)` true khi target còn tồn tại.
4. `Files.readString(link)` đọc được nội dung file thật.
5. Xóa link không làm source biến mất.

### 6.1. Ví dụ runnable: tạo, xác minh và dọn symlink

Tạo `SymbolicLinkCapabilityDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SymbolicLinkCapabilityDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("symlink-test-");
        Path source = dir.resolve("real.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(
                    source, "ONE", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        link, Path.of("real.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                // Chỉ nhánh tạo link là optional trong ví dụ.
                System.out.println(
                        "symlink=UNAVAILABLE_CREATE");
                return;
            }

            System.out.println("symlink=SUPPORTED");
            System.out.println(
                    "stored="
                    + Files.readSymbolicLink(link));
            System.out.println(
                    "is-link="
                    + Files.isSymbolicLink(link));
            System.out.println(
                    "same-file="
                    + Files.isSameFile(link, source));
            System.out.println(
                    "read-through="
                    + Files.readString(
                        link, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SymbolicLinkCapabilityDemo.java
java SymbolicLinkCapabilityDemo
```

**stdout nếu tạo symlink được:**

```text
symlink=SUPPORTED
stored=real.txt
is-link=true
same-file=true
read-through=ONE
```

**stdout khi lần tạo link bị từ chối/không khả dụng:**

```text
symlink=UNAVAILABLE_CREATE
```

**Quan trọng:** dòng `UNAVAILABLE_CREATE` không có nghĩa Java đã xác định nguyên nhân chính xác là “provider không hỗ trợ”. Exception có thể cho thấy quyền/chính sách, tên file xung đột hay lỗi I/O khác. Ví dụ chỉ có nhánh skip để học sinh chạy được trên các máy không có quyền symlink; một CI kiểm thử tính năng **bắt buộc** phải phân loại exception theo phần 11 và FAIL thay vì skip.

Các lệnh kiểm thử **không yêu cầu** bật chế độ quản trị Windows, chạy `mklink` hay sửa ACL toàn hệ thống. Nếu muốn test nhánh thành công, hãy chạy trên một filesystem/environment mà tổ chức đã cho phép tạo symlink.

## 7. Integration test: hard link là tính năng riêng

`Files.createLink(alias,existing)` tạo hard link đến file có thật khi provider/FS/quyền cho phép. Không nên suy rằng kết quả của `createSymbolicLink` quyết định kết quả của `createLink`.

Một test hard link tốt nên xác minh **identity** qua `Files.isSameFile`, thay vì chỉ so nội dung bytes. Hai file copy độc lập vẫn có nội dung bằng nhau nhưng **không phải** hard links.

Sau khi tạo hard link, ghi nội dung qua một alias và đọc qua alias khác chứng minh hai entry dùng cùng file data trong ca kiểm thử. Xóa một alias không xóa file nếu còn entry kia.

### 7.1. Ví dụ runnable: identity và chia sẻ nội dung

Tạo `HardLinkCapabilityDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class HardLinkCapabilityDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("hardlink-test-");
        Path existing = dir.resolve("real.txt");
        Path alias = dir.resolve("hard-alias.txt");

        try {
            Files.writeString(
                    existing, "A", StandardCharsets.UTF_8);

            try {
                Files.createLink(alias, existing);
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println(
                        "hardlink=UNAVAILABLE_CREATE");
                return;
            }

            System.out.println("hardlink=SUPPORTED");
            System.out.println(
                    "same-file="
                    + Files.isSameFile(existing, alias));

            Files.writeString(
                    alias, "B", StandardCharsets.UTF_8);
            System.out.println(
                    "shared-content="
                    + Files.readString(
                        existing, StandardCharsets.UTF_8)
                        .equals("B"));

            Files.delete(alias);
            System.out.println(
                    "source-survived="
                    + Files.readString(
                        existing, StandardCharsets.UTF_8)
                        .equals("B"));
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(existing);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all HardLinkCapabilityDemo.java
java HardLinkCapabilityDemo
```

**stdout khi tạo hard link được:**

```text
hardlink=SUPPORTED
same-file=true
shared-content=true
source-survived=true
```

**stdout khi không tạo được trong môi trường này:**

```text
hardlink=UNAVAILABLE_CREATE
```

**Khác biệt với `Files.copy`:** nếu bạn chỉ `Files.copy(existing,alias)`, sau đó ghi vào `alias` thì `existing` không mặc nhiên cập nhật theo. Dùng `Files.isSameFile` là cách rõ hơn để xác minh identity.

Cần chú ý `Files.isSameFile(a,a)` có thể trả `true` ngay khi hai `Path` equals **mà không cần truy cập filesystem**. Vì vậy dùng **hai pathname khác nhau thực sự** trong test để tránh một phép xác minh rỗng.

### 7.2. Khi test hard link cần lưu ý

- Hard link thường không thể trỏ xuyên hai file stores; test trên volume thực.
- Một số provider cấm hard link tới directory hoặc các loại file đặc biệt.
- File phải tồn tại trước khi tạo hard-link alias.
- Source/alias có thể chia sẻ metadata theo filesystem semantics, nhưng đừng hard-code mọi thuộc tính timestamp/fileKey giống nhau trên tất cả provider.
- Xóa một alias không có nghĩa mọi alias khác bị xóa.
- Trên storage đồng bộ/backup có thể tồn tại quy tắc copy-on-write hoặc behavior provider-specific; kiểm tra trên môi trường deploy thực tế.
- Một exception khi tạo hard link không đủ để xác định đó là thiếu quyền, khác file store hay không hỗ trợ; cần giữ diagnostics.

## 8. Dangling symlink: kiểm tra “link tồn tại” khác “target tồn tại”

Một symbolic link có thể lưu pathname đến target **chưa tồn tại** (nếu provider cho phép). Gọi là *dangling* hoặc *broken symbolic link*.

Quan sát khác nhau:

- `Files.exists(link)` mặc định **theo link**; nếu target không tồn tại, nó thường trả `false`.
- `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` kiểm tra **entry link** và có thể trả `true`.
- `Files.isSymbolicLink(link)` giúp xác định entry đó là link.
- `Files.readSymbolicLink(link)` vẫn đọc target pathname đã lưu, không bắt buộc target tồn tại.
- `Files.readString(link)` khi target thiếu thường ném `NoSuchFileException` hoặc loại `IOException` thích hợp.

**Không dùng `if (!Files.exists(link)) { Files.createSymbolicLink(...); }` như bằng chứng tên còn trống.** Một dangling symlink vẫn có thể chiếm entry, và trạng thái có thể đổi giữa check và create (TOCTOU).

### 8.1. Ví dụ runnable: test entry với NOFOLLOW_LINKS

Tạo `DanglingLinkAccessDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class DanglingLinkAccessDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("dangling-test-");
        Path link = dir.resolve("alias.txt");

        try {
            try {
                Files.createSymbolicLink(
                        link, Path.of("missing.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println(
                        "dangling=UNAVAILABLE_CREATE");
                return;
            }

            System.out.println("dangling=SUPPORTED");
            System.out.println(
                    "is-link=" + Files.isSymbolicLink(link));
            System.out.println(
                    "link-entry-exists="
                    + Files.exists(
                        link, LinkOption.NOFOLLOW_LINKS));
            System.out.println(
                    "target-exists=" + Files.exists(link));
            System.out.println(
                    "stored=" + Files.readSymbolicLink(link));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DanglingLinkAccessDemo.java
java DanglingLinkAccessDemo
```

**stdout nếu có thể tạo dangling symlink:**

```text
dangling=SUPPORTED
is-link=true
link-entry-exists=true
target-exists=false
stored=missing.txt
```

**stdout khi không thể tạo link:**

```text
dangling=UNAVAILABLE_CREATE
```

Ví dụ có một directory tạm mới và **không tạo `missing.txt`**, nên trên provider hỗ trợ symlink đích không tồn tại trong setup. Trường hợp I/O không xác định được trạng thái có thể khiến `Files.exists` trả false vì lý do khác; đối với kiểm kê cần phân biệt tình trạng, hãy dùng `Files.readAttributes` với `NOFOLLOW_LINKS` và xử lý `IOException` thay vì chỉ dùng boolean.

## 9. File access checks: observation khác enforcement

Java có các phương thức tiện lợi:

```java
boolean canRead = Files.isReadable(path);
boolean canWrite = Files.isWritable(path);
boolean canExecute = Files.isExecutable(path);
```

**Ý nghĩa:** chúng kiểm tra khả năng truy cập theo quyền mà JVM/provider quan sát tại thời điểm gọi. Giá trị `false` có thể nghĩa là không có quyền, file không tồn tại, hoặc không xác định được.

Chúng **không phải security gate nguyên tử**. Sau khi `isWritable(path)` trả `true`:

- File có thể bị xóa hoặc đổi thành symlink.
- Quyền ACL/mode có thể được sửa bởi actor khác.
- Mount có thể chuyển read-only, quota hết hoặc disk full.
- Path có thể trỏ đến một đối tượng khác ngay trước khi ghi.

**Đối với thao tác quan trọng, hãy thực hiện chính I/O dự kiến và xử lý `IOException`**. Pre-check đôi khi có ích cho UX/diagnostics, không thay thế authorization, filesystem permissions và error handling.

### 9.1. Quyền execute có nghĩa khác với directory

Trên Unix-like systems, `Files.isExecutable(directory)` liên quan khả năng **traverse/search directory**; với regular file nó liên quan khả năng execute theo OS. Nhưng cả hai đều không chứng minh chương trình có thể chạy thành công (định dạng, interpreter và mount policy còn ảnh hưởng).

Đừng dùng `Files.isExecutable(file)` để kết luận file đó là chương trình an toàn hoặc được phép chạy trong ứng dụng. Việc chạy subprocess nên theo allowlist, quyền tối thiểu và input policy riêng.

### 9.2. Ví dụ runnable: quan sát prechecks, xác minh bằng I/O thật

Tạo `FileAccessProbeDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class FileAccessProbeDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("access-probe-");
        Path file = dir.resolve("payload.txt");

        try {
            Files.writeString(
                    file, "ONE", StandardCharsets.UTF_8);

            Map<String, Boolean> observations = Map.of(
                    "read", Files.isReadable(file),
                    "write", Files.isWritable(file),
                    "execute", Files.isExecutable(file));

            System.out.println(
                    "access-checks=" + observations.size());

            String read = Files.readString(
                    file, StandardCharsets.UTF_8);
            Files.writeString(
                    file, read + "-TWO",
                    StandardCharsets.UTF_8);

            System.out.println(
                    "actual-io-ok="
                    + Files.readString(
                        file, StandardCharsets.UTF_8)
                        .equals("ONE-TWO"));
            System.out.println(
                    "source-is-file="
                    + Files.isRegularFile(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FileAccessProbeDemo.java
java FileAccessProbeDemo
```

```text
access-checks=3
actual-io-ok=true
source-is-file=true
```

Kết quả không in `Files.isReadable`/`isWritable`/`isExecutable` dưới dạng true/false cố định vì chúng phụ thuộc provider và quyền. Nhưng chương trình **có thu thập đủ ba observation** và sau đó thật sự thực hiện I/O đọc/ghi trong thư mục do nó tạo.

Nếu bạn chạy trong filesystem được mount read-only hoặc nơi temp directory không writable, chương trình có thể thất bại **trước** khi đến đoạn log. Đó là lỗi môi trường cần được báo, không phải bằng chứng mọi Java runtime đều cho I/O thất bại.

## 10. Test NOFOLLOW_LINKS: phân biệt link entry và target

Khi kiểm tra loại entry của path:

- `Files.isSymbolicLink(link)` hỏi link entry có phải symlink.
- `Files.readAttributes(link, BasicFileAttributes.class)` mặc định **theo symlink**, nên thường trả attributes của target.
- `Files.readAttributes(link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)` yêu cầu attributes của **chính link entry**.
- `Files.isRegularFile(link)` mặc định theo link.
- `Files.isRegularFile(link, NOFOLLOW_LINKS)` sẽ không xem symlink entry là regular target file.

**Đừng dùng `NOFOLLOW_LINKS` như cơ chế sandbox toàn diện**: tùy API, option này chủ yếu kiểm soát entry cuối, không tự chứng minh các **thư mục cha** không chứa symlinks hoặc junctions; và một actor khác có thể thay path giữa check và operation.

### 10.1. Ví dụ runnable: loại file được quan sát khác khi follow

Tạo `NoFollowLinkBehaviorDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class NoFollowLinkBehaviorDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("nofollow-test-");
        Path source = dir.resolve("real.txt");
        Path link = dir.resolve("link.txt");

        try {
            Files.writeString(
                    source, "x", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        link, Path.of("real.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println(
                        "nofollow=UNAVAILABLE_CREATE");
                return;
            }

            BasicFileAttributes linkAttrs =
                    Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes targetAttrs =
                    Files.readAttributes(
                        link, BasicFileAttributes.class);

            System.out.println("nofollow=SUPPORTED");
            System.out.println(
                    "link-attributes-is-link="
                    + linkAttrs.isSymbolicLink());
            System.out.println(
                    "target-attributes-regular="
                    + targetAttrs.isRegularFile());
            System.out.println(
                    "nofollow-regular="
                    + Files.isRegularFile(
                        link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all NoFollowLinkBehaviorDemo.java
java NoFollowLinkBehaviorDemo
```

**stdout nếu symbolic links dùng được:**

```text
nofollow=SUPPORTED
link-attributes-is-link=true
target-attributes-regular=true
nofollow-regular=false
```

**stdout nếu lần tạo symlink không khả dụng:**

```text
nofollow=UNAVAILABLE_CREATE
```

Bài test không cố đọc private metadata hay thay quyền bất kỳ file thật nào. Nó chỉ quan sát các path trong sandbox. Nếu việc đọc attributes thất bại sau khi tạo link, chương trình ném `IOException` để test **FAIL**; không được đánh dấu SKIP khi xác minh không đạt.

## 11. Phân loại failure thay vì gộp thành unsupported

Một vài exception quan trọng ở boundary tạo link:

| Ngoại lệ | Ý nghĩa nên điều tra |
| --- | --- |
| `UnsupportedOperationException` | Implementation/provider không hỗ trợ operation (theo contract) |
| `FileAlreadyExistsException` | Tên entry `link` đã tồn tại; thường là lỗi setup hoặc concurrent writer |
| `AccessDeniedException` | OS/provider từ chối quyền truy cập; không tự chứng minh thiếu feature |
| `SecurityException` | Một chính sách bảo mật/tầng kiểm tra quyền từ chối thao tác |
| `FileSystemException` | Lỗi filesystem với lý do provider/OS; cần xem `getReason()` |
| `NoSuchFileException` | Một path cần thiết thiếu; với hard link có thể là file đích chưa tồn tại |
| `IOException` khác | Có thể quota, readonly, lock, mount, I/O; không gộp là unsupported |

`FileSystemException` có thể chứa `getFile()`, `getOtherFile()` và `getReason()`. Các thông tin này hữu ích cho diagnostics nhưng có thể chứa path nhạy cảm; hạn chế log theo policy.

**Không phân loại chỉ từ chuỗi message tự do** như “privilege not held” thành quy tắc portable: message có thể thay đổi theo OS locale, provider, JVM và cấu hình hệ thống.

### 11.1. Ví dụ runnable: phân loại exception mô phỏng

Tạo `LinkFailureClassificationDemo.java`:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystemException;
import java.nio.file.NoSuchFileException;

public class LinkFailureClassificationDemo {
    static String category(Throwable error) {
        if (error instanceof UnsupportedOperationException) {
            return "NOT_SUPPORTED";
        }
        if (error instanceof FileAlreadyExistsException) {
            return "NAME_CONFLICT";
        }
        if (error instanceof AccessDeniedException
                || error instanceof SecurityException) {
            return "ACCESS_DENIED";
        }
        if (error instanceof NoSuchFileException) {
            return "PATH_MISSING";
        }
        if (error instanceof FileSystemException) {
            return "FILESYSTEM_ERROR";
        }
        if (error instanceof IOException) {
            return "OTHER_IO";
        }
        return "OTHER_ERROR";
    }

    public static void main(String[] args) {
        System.out.println(
                "unsupported="
                + category(new UnsupportedOperationException()));
        System.out.println(
                "exists="
                + category(new FileAlreadyExistsException("link")));
        System.out.println(
                "denied="
                + category(new AccessDeniedException("link")));
        System.out.println(
                "missing="
                + category(new NoSuchFileException("target")));
        System.out.println(
                "filesystem="
                + category(new FileSystemException("link")));
        System.out.println(
                "io=" + category(new IOException("storage error")));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LinkFailureClassificationDemo.java
java LinkFailureClassificationDemo
```

```text
unsupported=NOT_SUPPORTED
exists=NAME_CONFLICT
denied=ACCESS_DENIED
missing=PATH_MISSING
filesystem=FILESYSTEM_ERROR
io=OTHER_IO
```

Đây là **unit test giả lập các loại exception**, không phải kiểm thử thực tế rằng OS đã tạo link. Phân loại đúng giúp CI/service không đánh dấu `FileAlreadyExistsException` thành “symlink unsupported” hoặc nuốt mất lỗi I/O.

Một `FileSystemException` cụ thể có thể diễn tả chính sách không hỗ trợ **hoặc** thiếu quyền tùy provider; cần xem mã lỗi và môi trường triển khai. Không suy “NOT_SUPPORTED” tự động chỉ vì nó là subclass của `IOException`.

### 11.2. Chính sách production nên khác bài demo

Một test **tùy chọn** có thể dùng `SKIP` khi biết môi trường CI đã được quản lý và loại operation không thể thực thi. Một tính năng **bắt buộc** phải fail với message và context đủ để sửa cấu hình. Khi bất kỳ loại exception nào phát sinh trong **verification sau create**, mặc định báo FAIL, không skip.

Một cách thiết kế report:

```text
TEST_NAME           ENVIRONMENT        RESULT                   REASON
symbolic-link       Windows + temp FS  SKIPPED_CREATE           AccessDenied / provider detail
hard-link           Windows + temp FS  PASS                     Same-file verified
relative-target     Java Path only     PASS                     Lexical semantics
nofollow-attributes POSIX temp FS      PASS                     Link attributes verified
```

Đây chỉ là **bảng mẫu minh họa**, không phải kết quả khẳng định cho mọi máy Windows hoặc CI. Thực tế phải điền từ output của môi trường cụ thể.

## 12. Di chuyển link giữa hai thư mục: kiểm thử portability của relative target

Một symlink có stored target **tương đối** như `data.txt` được diễn giải từ parent hiện tại của link. Khi di chuyển entry symlink sang directory khác, target được resolve có thể thay đổi dù `Files.readSymbolicLink` vẫn trả `data.txt`.

Bài test này hữu ích khi packaging artifact, staging release hoặc restore backup: bạn cần xác định công cụ đang **di chuyển link entry** hay copy **nội dung target**.

### 12.1. Ví dụ runnable: move link đổi file cuối

Tạo `LinkMoveSemanticsDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LinkMoveSemanticsDemo {
    public static void main(String[] args)
            throws IOException {
        Path root = Files.createTempDirectory("link-move-");
        Path from = root.resolve("from");
        Path to = root.resolve("to");
        Path first = from.resolve("data.txt");
        Path second = to.resolve("data.txt");
        Path original = from.resolve("alias.txt");
        Path moved = to.resolve("alias.txt");

        try {
            Files.createDirectory(from);
            Files.createDirectory(to);
            Files.writeString(
                    first, "FROM", StandardCharsets.UTF_8);
            Files.writeString(
                    second, "TO", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        original, Path.of("data.txt"));
            } catch (IOException
                    | UnsupportedOperationException
                    | SecurityException ex) {
                System.out.println(
                        "move-link=UNAVAILABLE_CREATE");
                return;
            }

            Path storedBefore = Files.readSymbolicLink(original);
            String before = Files.readString(
                    original, StandardCharsets.UTF_8);

            Files.move(original, moved);

            Path storedAfter = Files.readSymbolicLink(moved);
            String after = Files.readString(
                    moved, StandardCharsets.UTF_8);

            System.out.println("move-link=SUPPORTED");
            System.out.println("before=" + before);
            System.out.println("after=" + after);
            System.out.println(
                    "stored-same="
                    + storedBefore.equals(storedAfter));
        } finally {
            Files.deleteIfExists(moved);
            Files.deleteIfExists(original);
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(from);
            Files.deleteIfExists(to);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LinkMoveSemanticsDemo.java
java LinkMoveSemanticsDemo
```

**stdout khi symlink được tạo và move thành công:**

```text
move-link=SUPPORTED
before=FROM
after=TO
stored-same=true
```

**stdout khi không thể tạo link:**

```text
move-link=UNAVAILABLE_CREATE
```

**Đây không phải tính năng “update relative target” của `Files.move`.** Stored target vẫn là `data.txt`. Vị trí chứa link đổi từ `from` sang `to`, nên target được giải nghĩa theo parent mới. Nếu ứng dụng cần link luôn trỏ tới cùng file cuối, phải tính và tạo lại link phù hợp hoặc thay đổi layout, không trông chờ `move` tự sửa target.

## 13. Policy đường dẫn: kiểm thử lexical không thay thế permission

Nếu cho người dùng chỉ định tên link/target, cần bảo vệ root boundary. Cần phân biệt:

- **Kiểm tra cú pháp (lexical):** path không absolute, normalize và startsWith(root) theo components.
- **Kiểm tra filesystem thật:** các thành phần đường dẫn có thể là symlinks/mounts; kết quả truy cập phụ thuộc permissions/ACL và race.
- **Kiểm tra quyền ứng dụng:** caller/tenant được phép tạo link tới tài nguyên nào.

Một kiểm tra lexical đơn giản có thể loại bỏ target `../../secrets.txt` thoát khỏi root, nhưng nó **không** bảo đảm chống symlink parent, TOCTOU, mount aliases hay ACL.

### 13.1. Ví dụ runnable: bảo vệ ranh giới theo cú pháp

Tạo `LinkPathBoundaryDemo.java`:

```java
import java.nio.file.Path;

public class LinkPathBoundaryDemo {
    static boolean lexicallyWithin(
            Path trustedRoot,
            Path link,
            Path storedTarget) {
        Path root = trustedRoot
                .toAbsolutePath().normalize();
        Path location = link
                .toAbsolutePath().normalize();

        if (storedTarget.isAbsolute()
                || !location.startsWith(root)) {
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
                .resolve("alias.txt");

        Path permitted = Path.of(
                "..", "data", "report.txt");
        Path escaped = Path.of(
                "..", "..", "private.txt");
        Path absolute = root.resolve("secrets.txt");

        System.out.println(
                "inside="
                + lexicallyWithin(root, link, permitted));
        System.out.println(
                "escape="
                + lexicallyWithin(root, link, escaped));
        System.out.println(
                "absolute="
                + lexicallyWithin(root, link, absolute));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LinkPathBoundaryDemo.java
java LinkPathBoundaryDemo
```

```text
inside=true
escape=false
absolute=false
```

**Lưu ý bắt buộc:** đoạn code trên chỉ xác minh quan hệ **lexical**. Kết quả `inside=true` không chứng minh target thực nằm trong root nếu có symbolic link ở các thư mục cha, hoặc một actor khác đổi entry giữa check và open. Khi cần bảo đảm security thực tế, cần root do server quản lý, quyền tối thiểu và primitive filesystem/provider phù hợp (xem `SecureDirectoryStream` khi được hỗ trợ).

## 14. Không nên thay đổi quyền hệ thống để tạo test “permission denied”

Một cách kiểm thử thiếu ổn định là đổi permission của một directory (ví dụ `chmod 000`) rồi đoán rằng mọi lần tạo symlink/hard link sẽ thất bại.

Lý do:

- Windows thường có mô hình ACL và quyền tạo symlink khác POSIX.
- Trên Linux, process chạy với `root` hoặc capabilities nhất định có thể vượt qua một số permission checks.
- NFS/SMB, container volumes và file stores khác có thể có semantics riêng.
- `FileStore` hỗ trợ POSIX view không chứng minh chmod đem lại đúng kết quả với mọi user.
- CI có thể chạy dưới tài khoản khác tài khoản dev.
- Thao tác thay quyền vào thư mục chung của repo có thể phá workflow của người khác hoặc cleanup.

**Giải pháp kiểm thử sạch:**

1. Với **unit test**, dùng exception giả lập để kiểm tra logic phân loại và mapping error (như `LinkFailureClassificationDemo`).
2. Với **integration test**, tạo sandbox riêng, thực hiện `Files.createSymbolicLink`/`createLink` thật, xác nhận outcome.
3. Với **permission test bắt buộc**, chạy trong sandbox/container/OS account được cấu hình trước để mô phỏng quyền, không sửa quyền thư mục production.
4. Với **CI cross-platform**, lập ma trận môi trường và đánh dấu rõ test nào bắt buộc PASS, test nào được skip khi capability không có.
5. Với lỗi I/O/permission thật, giữ exception cause, không log quá nhiều path/tên file nhạy cảm.

### 14.1. POSIX permissions không phải Windows ACL

Trên POSIX filesystem, có thể đọc `PosixFileAttributes`/`PosixFilePermissions` để hiểu owner/group/others. Windows/NTFS thường có ACL làm mô hình quyền trọng tâm, và một ứng dụng muốn chỉnh quyền cần chọn API provider tương ứng.

**Không tạo file mới chứa secret với quyền rộng rồi coi việc gọi `isWritable` là bảo vệ**. Phải có policy tạo file/dir an toàn ngay từ đầu, giới hạn root, kiểm soát ownership, và xử lý trường hợp provider không hỗ trợ chính sách đặt attributes.

### 14.2. Environment isolation và test containers

Một container có thể chạy trên Linux kernel nhưng mount storage từ host hoặc volume có policy khác. Bài test trong container trên directory nội bộ có thể PASS trong khi tạo link trên shared volume lại bị từ chối.

Test đúng nơi sản phẩm sử dụng storage:

- Chọn một **test directory được cấp phép** trên file store thực.
- Xác minh root không phải dữ liệu người dùng khác.
- Tạo tệp nhỏ, làm test link, readback và cleanup.
- Không cần thay đổi hostname, PATH, ACL hay security settings của host.
- Lưu OS/container/volume metadata để hỗ trợ phân tích, nhưng **đừng dùng những tên đó để kết luận thay cho thao tác thật**.

## 15. JUnit 5: cơ chế skip có điều kiện trong test framework

Nếu dự án đã dùng **JUnit Jupiter**, có thể diễn đạt test tùy chọn:

```java
@org.junit.jupiter.api.Test
void symbolicLinkWhenAvailable(
        @org.junit.jupiter.api.io.TempDir Path dir)
        throws IOException {
    Path source = dir.resolve("file.txt");
    Path link = dir.resolve("alias.txt");
    Files.writeString(source, "ok");

    try {
        Files.createSymbolicLink(link, Path.of("file.txt"));
    } catch (UnsupportedOperationException ex) {
        org.junit.jupiter.api.Assumptions
                .abort("Provider does not support symlink");
    }

    org.junit.jupiter.api.Assertions.assertTrue(
            Files.isSymbolicLink(link));
    org.junit.jupiter.api.Assertions.assertTrue(
            Files.isSameFile(link, source));
}
```

**Đây là snippet trong class test** cần import `java.nio.file.Files`, `Path`, `java.io.IOException` và dependency **JUnit 5**; nó không phải chương trình Java chạy bằng `java ClassName` và không được liệt kê trong bộ demo `javac` thuần JDK.

Ví dụ chỉ abort khi `UnsupportedOperationException` được ném trực tiếp. Với `AccessDeniedException` hoặc `FileSystemException`, cần chính sách CI xác định rõ có cho skip trong môi trường đã biết không; **không catch mọi IOException rồi luôn abort** vì có thể che regression.

**Điểm thiết kế:** dùng `@TempDir` để tạo sandbox và framework quản lý cleanup. Cũng cần định nghĩa test tier: nếu symlink là yêu cầu bắt buộc của sản phẩm, một `Assumption` skip vô điều kiện không đủ để xác nhận pipeline.

## 16. Những anti-pattern phổ biến

| Lỗi | Tại sao sai | Cách đúng |
| --- | --- | --- |
| `if (osName.contains("Windows")) return;` | Windows có nhiều cấu hình quyền/file stores | Thử operation thật trong sandbox, ghi outcome |
| `FileStore.supportsFileAttributeView("posix")` là symlink feature check | POSIX metadata khác support link creation | Không suy trực tiếp, dùng `createSymbolicLink` |
| Symlink fail nên hard link cũng fail | Hai operations và yêu cầu quyền khác nhau | Test độc lập `createLink` |
| Hard link content giống source nên kết luận cùng file | Bản copy có thể cũng giống bytes | `Files.isSameFile` trên hai path khác nhau |
| Coi `Files.isReadable(path)` là authorization vĩnh viễn | Check có thể lỗi thời/không xác định | Thực hiện I/O, xử lý exception |
| `Files.exists(link)==false` nghĩa pathname chưa có | Dangling symlink vẫn có entry | `NOFOLLOW_LINKS` và xử lý create conflict |
| Bắt mọi `IOException` và gán NOT_SUPPORTED | Có thể permission, name conflict, quota, disk I/O | Phân loại theo exception và context |
| Catch lỗi verification rồi coi là SKIPPED | Che lỗi khi feature đã được tạo thành công | Skip chỉ ở nhánh creation được cho phép; verify failure = FAIL |
| Thao tác thẳng trong thư mục production | Nguy cơ ghi/xóa dữ liệu thật | Sandbox temp riêng trên store cần test |
| Xóa source trước alias trong test và nghĩ alias mất | Hard link vẫn giữ dữ liệu nếu alias còn | Cleanup đúng ownership và kiểm chứng semantics |
| Tạo symlink rồi quên `Files.deleteIfExists(link)` | Rò rỉ entry, test sau conflict | `finally`/framework temp cleanup |
| Test bằng cách sửa ACL toàn máy | Không an toàn, khó phục hồi | Dùng account/container/volume dành riêng |
| Bật `777` hoặc Administrator chỉ để “test xanh” | Mở rộng quyền không cần thiết | Có CI environment được quản trị phù hợp |
| Dùng `Path.toRealPath` như kiểm tra bất biến | Target có thể bị thay đổi sau check | Kiểm soát TOCTOU và permissions |
| Dựa vào `normalize().startsWith(root)` như sandbox đủ | Symlink parent/junction có thể thoát root | Defense-in-depth, root/handle-relative nơi phù hợp |
| Nghĩ JUnit `@TempDir` đảm bảo file store production | Temp có thể khác volume deploy | Đặt temp dưới target root khi được phép |
| Bắt `SecurityException` rồi log tất cả path | Có thể lộ dữ liệu tên file | Log theo policy bảo mật |
| Link creation skip nhưng báo “FULL PASS” | Không test nhánh chức năng thực | Report SKIPPED và coverage rõ |
| Một test hard link trên default FS đại diện mọi provider | File stores khác nhau có policy khác | Tái chạy trên từng target store |

## 17. Checklist trước khi merge PR

1. Có xác định requirement **symbolic link** hay **hard link** hoặc cả hai?
2. Có test thực tế trên filesystem mục tiêu, không chỉ hỏi `os.name`?
3. Test nào **bắt buộc PASS**, test nào **được SKIP** khi không có quyền?
4. Test uses temp sandbox riêng, không chạm dữ liệu production hay người khác?
5. Có tạo source có thật khi test hard link?
6. Có tách `createSymbolicLink` và `createLink` thành hai phép thử độc lập?
7. Với symlink, có kiểm tra `readSymbolicLink`, `isSymbolicLink`, `isSameFile`/nội dung?
8. Với hard link, có xác minh **identity** chứ không chỉ checksum?
9. Có kiểm tra broken symlink bằng `exists(...,NOFOLLOW_LINKS)` khi cần?
10. Có phân biệt `UnsupportedOperationException`, `AccessDeniedException`, `FileAlreadyExistsException`, `FileSystemException`?
11. Có tránh skip trên mọi `IOException` trong CI bắt buộc?
12. Có xử lý permissions POSIX/ACL theo provider, thay vì dùng chín bit làm universal model?
13. Có hiểu `Files.isReadable/isWritable` là pre-check, không phải hành động I/O cuối?
14. Có test parent directory và quyền tạo entry, không chỉ quyền của source file?
15. Có kiểm tra source và alias có cùng file store với hard link test?
16. Có thử symlink tới file/directory nếu sản phẩm yêu cầu cả hai?
17. Có test relative symlink khi di chuyển parent và kiểm tra stored target?
18. Có chính sách cho symlink loops, traversal, dangling target, race và TOCTOU?
19. Có xác định security root và tránh path do client điều khiển đi ra ngoài?
20. Có cleanup cả nhánh success và nhánh creation failed, đóng streams trước?
21. Có tránh đánh giá false positive khi hai input của `isSameFile` bằng nhau?
22. Có kiểm tra behavior nếu file bị xóa/đổi tên giữa check và use?
23. Có ghi test report theo tên OS/provider/file store mà không lộ dữ liệu nhạy cảm?
24. Có xác định behavior khi chạy trong container hoặc mounted network filesystem?
25. Có liên kết tài liệu API/exception và sử dụng Java 17+ hiện hành?

## 18. Bài tập thực hành

**Bài 1 — Capability probe.** Chạy `LinkEnvironmentProbeDemo`. Thêm logging an toàn cho tên FileStore và các attribute views được hỗ trợ; giải thích vì sao kết quả POSIX/ACL không quyết định khả năng tạo symbolic link.

**Bài 2 — Symbolic link.** Chạy `SymbolicLinkCapabilityDemo`. Nếu output `UNAVAILABLE_CREATE`, ghi loại exception trong một phiên bản test riêng. Nếu bắt buộc support symlink, điều chỉnh test thành FAIL thay vì SKIP.

**Bài 3 — Hard link.** Chạy `HardLinkCapabilityDemo`. So sánh `Files.createLink` với `Files.copy`: tạo hai đường dẫn, sửa nội dung alias và dùng `Files.isSameFile` để kiểm chứng identity.

**Bài 4 — Dangling link.** Chạy `DanglingLinkAccessDemo`. Vì sao `Files.exists(link)` và `Files.exists(link,NOFOLLOW_LINKS)` có thể khác nhau? Tạo target `missing.txt` rồi chạy lại checks.

**Bài 5 — Access observations.** Chạy `FileAccessProbeDemo` và log riêng `isReadable/isWritable/isExecutable` (không hard-code stdout). Giải thích ba lý do khiến pre-check đúng nhưng operation tiếp theo thất bại.

**Bài 6 — NOFOLLOW_LINKS.** Chạy `NoFollowLinkBehaviorDemo`. Dùng `Files.readAttributes` với và không có `NOFOLLOW_LINKS` để so sánh loại entry; giải thích giới hạn với symlink ở parent.

**Bài 7 — Failure taxonomy.** Chạy `LinkFailureClassificationDemo`. Bổ sung `SecurityException` và một `FileSystemException` có `reason`; chỉ phân loại theo type và context thay vì suy cause bằng substring.

**Bài 8 — Move semantics.** Chạy `LinkMoveSemanticsDemo`. Nếu move alias sang parent khác, cùng stored target có thể trỏ tới nội dung nào? Thử move cả directory tree và phân tích điểm khác.

**Bài 9 — Path boundary.** Chạy `LinkPathBoundaryDemo` với `../../secrets.txt` và một absolute path; nêu những rủi ro chưa được lexical check giải quyết.

**Bài 10 — Policy CI.** Lập ma trận Windows (có và không có quyền symlink), Linux và một volume mounted. Tách test bắt buộc/tùy chọn và report PASS/SKIPPED/FAIL.

**Bài 11 — Security review.** Một service cho user tự truyền target tương đối để tạo symlink. Xác định privilege model, parent permissions, root boundary, symlink traversal và TOCTOU trước khi triển khai.

**Bài 12 — Restore/backup.** Thiết kế kiểm thử backup giữ được hard-link identity và symbolic-link stored target; giải thích vì sao copy bytes không bảo đảm phục hồi topology.

**Bài 13 — Test isolation.** Chạy các chương trình trong sandbox riêng của project thay vì temp mặc định, nhưng chỉ nếu directory được cấp phép. Kiểm tra kết quả trên đúng file store mà production dùng.

## 19. Tổng kết

- **Tính năng, quyền và kết quả I/O là ba khái niệm khác nhau.** Không suy ra support symlink/hard link chỉ từ API tồn tại hoặc tên hệ điều hành.
- **`Files.createSymbolicLink` và `Files.createLink` phải được kiểm thử riêng**. Symlink có thể bị chặn bởi OS policy trong khi hard link vẫn dùng được.
- **Attribute views** như POSIX/ACL giúp làm việc với metadata, không thay thế test thao tác tạo link thật.
- **`Files.isReadable/isWritable/isExecutable` là quan sát tại thời điểm gọi**; thao tác thực tế mới quyết định success/failure, và ngay cả check thành công cũng không loại bỏ race.
- **`Files.isSameFile`** hữu ích để verify identity, nhưng cần hai pathname khác nhau để tránh trường hợp equals shortcut.
- **`NOFOLLOW_LINKS`** cần để phân biệt entry symlink với target, đặc biệt khi target dangling, nhưng không phải sandbox đầy đủ.
- **Phân loại exception đúng:** unsupported, access denied, name conflict, missing path và filesystem I/O là các trạng thái khác nhau.
- **Test có giới hạn môi trường phải báo SKIP rõ**; nếu chức năng bắt buộc mà không test được thì không coi là full pass.
- **Cleanup an toàn và security boundary** quan trọng ngang assertion: chỉ thao tác file test sở hữu, tránh sửa quyền hệ thống, chống symlink traversal/TOCTOU.
- Những kỹ thuật trên sử dụng **Java NIO.2 và Java 17+ hiện hành**, không cần dựa vào API legacy.

## Tài liệu chính thức

- [Files — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `createSymbolicLink`, `createLink`, `readSymbolicLink`, `isSameFile`, `isReadable`, `isWritable`, `isExecutable`, `exists`, `readAttributes`.
- [Path — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `resolve`, `relativize`, `normalize`, `toRealPath` và filesystem providers.
- [LinkOption — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [FileStore — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView` và metadata khả năng file store.
- [BasicFileAttributes — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): loại file và `isSymbolicLink()`.
- [PosixFileAttributeView — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): owner/group/permissions khi provider hỗ trợ.
- [AclFileAttributeView — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): access control lists theo filesystem provider.
