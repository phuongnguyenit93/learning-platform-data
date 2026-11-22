# `FileStore`, dung lượng và `supportedFileAttributeViews` trong Java

Khi thao tác file bằng Java NIO.2, chương trình đôi khi cần biết **file đang nằm trên kho lưu trữ nào**, **dung lượng còn có thể sử dụng là bao nhiêu**, hoặc **filesystem có hỗ trợ POSIX permissions, DOS attributes, ACL và các loại metadata khác không**. Đây là những câu hỏi ở tầng **filesystem và thuộc tính**, khác với việc đọc nội dung byte của một file.

Java 17 cung cấp những điểm vào chính:

- `Files.getFileStore(Path)`: tìm `FileStore` gắn với vị trí một đường dẫn.
- `FileStore.getTotalSpace()`, `getUnallocatedSpace()`, `getUsableSpace()`: thông tin dung lượng tính theo **byte**.
- `FileStore.supportsFileAttributeView(...)`: hỏi một store có hỗ trợ loại attribute view cụ thể hay không.
- `FileSystem.supportedFileAttributeViews()`: lấy tập tên các attribute view mà **filesystem** báo hỗ trợ.
- `Files.readAttributes(...)`, `Files.getFileAttributeView(...)`: đọc hoặc truy cập view của **một đường dẫn cụ thể**.

Điểm quan trọng: **dung lượng báo “có thể sử dụng” chỉ là ảnh chụp trạng thái ở một thời điểm, không bảo đảm lệnh ghi tiếp theo thành công**; và **“supportedFileAttributeViews” của `FileSystem` không hoàn toàn đồng nghĩa kiểm tra support trên một `FileStore` riêng lẻ**. Bài này giải thích rõ ba tầng đó qua ví dụ Java 17+, bảng lựa chọn và các lưu ý về quyền, quota, portability và điều kiện cạnh tranh.

## 1. Phân biệt `Path`, `FileSystem`, `FileStore` và attribute view

### `Path` — vị trí của một mục

`Path` là đường dẫn tới file/thư mục hoặc một vị trí chưa tồn tại:

```java
Path path = Path.of("data", "report.txt");
```

Đây là **mã minh họa**, cần import `java.nio.file.Path`. Tạo `Path` không tự mở, tạo hay đọc file. Một `Path` gắn với một `FileSystem` cụ thể và được diễn giải theo quy tắc provider của filesystem đó.

### `FileSystem` — mô hình filesystem do provider cung cấp

`java.nio.file.FileSystem` đại diện cho một filesystem với root, separator, path matcher, attribute view có thể hỗ trợ và tập file store mà provider cho phép liệt kê.

Để lấy filesystem của một path:

```java
FileSystem fs = path.getFileSystem();
```

Đây là **mã minh họa**, cần biến `path` và import `FileSystem`. Để lấy filesystem mặc định:

```java
FileSystem defaultFs = FileSystems.getDefault();
```

Cần import `java.nio.file.FileSystems`. Một ứng dụng có thể còn làm việc với provider khác default, chẳng hạn ZIP filesystem khi đã mở provider tương ứng.

### `FileStore` — nơi lưu trữ, với thông tin dung lượng và metadata

`java.nio.file.FileStore` mô tả một **kho lưu trữ** được filesystem/provider phơi bày. Trên hệ thống thật, nó thường liên hệ tới volume, mount, phân vùng, network share hoặc đối tượng lưu trữ logic, nhưng **không bắt buộc trùng một ổ cứng vật lý**.

```java
FileStore store = Files.getFileStore(path);
```

Đây là **mã minh họa**, cần import `FileStore`, `Files`, biến `path` và xử lý `IOException`. `Files.getFileStore` có thể truy cập filesystem, nên khác với việc chỉ gọi `path.getFileSystem()`.

### Attribute view — nhóm thuộc tính có cấu trúc

`FileAttributeView` là giao diện dùng để truy cập một **nhóm metadata** của file. Những view thường gặp:

| View | Mục đích | API liên quan |
|---|---|---|
| `basic` | Loại file, size, thời điểm tạo/sửa/truy cập, file key khi có | `BasicFileAttributeView`, `BasicFileAttributes` |
| `posix` | Permissions kiểu POSIX, owner, group | `PosixFileAttributeView`, `PosixFileAttributes` |
| `dos` | Hidden, read-only, system, archive | `DosFileAttributeView`, `DosFileAttributes` |
| `acl` | Access-control list theo provider | `AclFileAttributeView` |
| `owner` | Chủ sở hữu file | `FileOwnerAttributeView` |
| `user` | Thuộc tính mở rộng do người dùng đặt, khi có support | `UserDefinedFileAttributeView` |

Không có bảo đảm **mọi filesystem đều hỗ trợ mọi view**. POSIX thường thấy trên các hệ thống kiểu Unix; DOS/ACL/user-defined có thể xuất hiện ở những provider khác, nhưng phải **kiểm tra tại runtime** thay vì suy ra chắc chắn chỉ từ tên hệ điều hành.

## 2. Lấy `FileStore` của đường dẫn

Dùng `Files.getFileStore(path)` khi bạn quan tâm nơi sẽ đọc/ghi dữ liệu:

```java
Path dir = Path.of("data").toAbsolutePath();
FileStore store = Files.getFileStore(dir);
```

Đây là **mã minh họa**, cần import `Path`, `Files`, `FileStore`, và `data` phải là vị trí mà provider xác định được store theo contract. Nếu đường dẫn không tồn tại hoặc không thể tra cứu trong provider, thao tác có thể ném `IOException`; không nên tự giả định mọi path tưởng tượng đều tra ra dung lượng.

Một số phương thức của `FileStore`:

- `name()`: tên được provider báo, **có thể là chuỗi rỗng**.
- `type()`: loại store/filesystem do provider báo, ví dụ một tên định dạng filesystem; không phải mã phân loại chuẩn duy nhất giữa các provider.
- `isReadOnly()`: provider xem store có read-only hay không; **không đủ chứng minh** bạn có quyền ghi vào một file cụ thể.
- `getTotalSpace()`: tổng dung lượng của store.
- `getUnallocatedSpace()`: phần không được cấp phát ở store.
- `getUsableSpace()`: phần dung lượng **có thể dùng bởi Java VM này** theo cách provider đánh giá.
- `supportsFileAttributeView(...)`: kiểm tra khả năng hỗ trợ attribute view ở store.
- `getAttribute(String)`: thuộc tính **store-specific** theo tên được provider hỗ trợ; không phải API tiêu chuẩn chung cho mọi loại thuộc tính.

### Đừng coi `name()` là ID duy nhất

Một chương trình có thể chạy trong container, môi trường ảo, network mount hoặc provider với tên store rỗng. Không nên dùng `store.name()` làm khóa duy nhất để nhận diện file hoặc quyết định hai đường dẫn có cùng thiết bị vật lý.

Trong ví dụ kiểm thử bên dưới trên một filesystem NTFS, `name()` đã trả chuỗi **rỗng**. Do đó, chương trình thực tế phải chấp nhận trường hợp tên hiển thị không có thông tin hữu ích.

## 3. Ba đại lượng dung lượng: total, unallocated, usable

| Phương thức | Đơn vị | Ý nghĩa thực hành |
|---|---|---|
| `getTotalSpace()` | Byte | Dung lượng tổng mà store báo |
| `getUnallocatedSpace()` | Byte | Dung lượng chưa được phân bổ/cấp phát trong store |
| `getUsableSpace()` | Byte | Dung lượng store dự kiến khả dụng cho **Java VM/caller hiện tại** |

Sự khác nhau quan trọng nhất là giữa **unallocated** và **usable**:

- Một filesystem có thể còn nhiều dung lượng trống vật lý nhưng một người dùng/process bị giới hạn quota hoặc phần dung lượng được dành riêng cho hệ thống.
- Khi đó dung lượng **usable** có thể thấp hơn dung lượng **unallocated**.
- Ở một số hệ thống, hai số này bằng nhau; đây chỉ là trạng thái của provider tại thời điểm gọi, không phải quy luật chung.
- Con số được đo trên **store**, không phải kích thước của một file.
- Các số liệu **có thể thay đổi ngay sau khi đọc** vì tiến trình khác ghi/xóa dữ liệu, quota thay đổi, filesystem được mount lại hoặc do đặc tính provider.

Không nên lấy `getUnallocatedSpace()` thay cho `getUsableSpace()` để kết luận rằng ứng dụng **có quyền sử dụng** toàn bộ dung lượng trống. Ngược lại, `getUsableSpace()` cũng **không đảm bảo** một file mới có thể được tạo thành công: còn có ACL, permission, inode/entry limits, path lỗi, quota không được phản ánh tức thì, giới hạn mạng và nhiều nguyên nhân khác.

### Byte, KiB, MiB, GiB khác với kB, MB, GB

Các API dung lượng trả về **byte** dưới dạng `long`. Để trình bày theo đơn vị nhị phân:

- `1 KiB = 1.024 byte`.
- `1 MiB = 1.024 KiB = 1.048.576 byte`.
- `1 GiB = 1.024 MiB = 1.073.741.824 byte`.

Đơn vị thập phân dùng cho một số nhãn của nhà sản xuất lưu trữ:

- `1 kB = 1.000 byte`.
- `1 MB = 1.000.000 byte`.
- `1 GB = 1.000.000.000 byte`.

Hai quy ước không nên bị ghi nhãn lẫn nhau. Ví dụ phép chia `bytes / (1024.0 * 1024.0 * 1024.0)` tạo **GiB**, không phải GB thập phân.

### Đừng ép dữ liệu dung lượng về `int`

`long` là lựa chọn phù hợp cho thông tin byte lớn. Một store dung lượng hàng trăm GiB dễ vượt quá giới hạn `int` 32 bit. Cũng cần chú ý tràn số khi tính `requiredBytes + overhead`: với đầu vào không đáng tin, hãy kiểm tra trước phép cộng hoặc dùng so sánh giới hạn phù hợp.

## 4. Ví dụ 1 — truy vấn dung lượng của một thư mục thật

Tạo tệp `FileStoreCapacityDemo.java` (Java 17+):

```java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class FileStoreCapacityDemo {
    static double toGiB(long bytes) {
        return bytes / (1024.0 * 1024.0 * 1024.0);
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("store-capacity-");
        try {
            FileStore store = Files.getFileStore(dir);
            long total = store.getTotalSpace();
            long unallocated = store.getUnallocatedSpace();
            long usable = store.getUsableSpace();
            System.out.println("store name=" + store.name());
            System.out.println("store type=" + store.type());
            System.out.println("total bytes=" + total);
            System.out.println("unallocated bytes=" + unallocated);
            System.out.println("usable bytes=" + usable);
            System.out.println("nonnegative byte counts="
                    + (total >= 0 && unallocated >= 0 && usable >= 0));
            System.out.printf(Locale.ROOT, "one GiB formatted=%.2f%n",
                    toGiB(1L << 30));
        } finally {
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch, chạy:

```bash
javac -encoding UTF-8 --release 17 FileStoreCapacityDemo.java
java FileStoreCapacityDemo
```

Kết quả **quan sát được trong một lần chạy Java 17 trên NTFS**:

```text
store name=
store type=NTFS
total bytes=499024654336
unallocated bytes=203543601152
usable bytes=203543601152
nonnegative byte counts=true
one GiB formatted=1.00
```

**Không coi các con số trên là stdout cố định trên mọi máy.** `name()`, `type()`, `total`, `unallocated` và `usable` là dữ liệu thực của filesystem nơi ví dụ chạy; chúng có thể khác khi đổi máy, ổ đĩa, quota hoặc đơn giản chỉ một lần chạy sau. Đây là lý do code đọc giá trị thực thay vì hard-code ví dụ dung lượng.

**Cơ chế:**

1. `Files.createTempDirectory` tạo thư mục riêng trên vị trí tạm mặc định, tránh phụ thuộc file người dùng.
2. `Files.getFileStore(dir)` lấy store tương ứng với đường dẫn thư mục vừa tạo.
3. Ba phương thức dung lượng trả `long` và đều có đơn vị **byte**.
4. `toGiB` minh họa phép đổi đơn vị không dùng phép chia số nguyên, tránh mất phần lẻ do `long / long`.
5. Khối `finally` dọn thư mục tạm sau khi query. Nếu filesystem cấm thao tác, lời gọi liên quan có thể ném `IOException` và cần xử lý ở ứng dụng thật.

Không nên kiểm thử theo kiểu assert chính xác một con số dung lượng trên máy test. Những test đáng tin hơn xác nhận kiểu dữ liệu, cơ chế lỗi và phép quy đổi bằng **số giả lập cố định**, còn test tích hợp chỉ kiểm tra thuộc tính với giả định phù hợp môi trường.

## 5. Phân biệt `FileSystem.supportedFileAttributeViews()` và `FileStore.supportsFileAttributeView(...)`

Hai API có tên gần giống nhưng **khác phạm vi**.

### 5.1 Tập view ở tầng `FileSystem`

`FileSystem.supportedFileAttributeViews()` trả một `Set<String>` tên view mà filesystem/provider cho biết hỗ trợ:

```java
Set<String> views =
        FileSystems.getDefault().supportedFileAttributeViews();
```

Đây là **đoạn minh họa**, cần import `java.nio.file.FileSystems` và `java.util.Set`.

Tên có thể là `"basic"`, `"posix"`, `"dos"`, `"acl"`, `"owner"` hoặc `"user"`, tùy provider. **Không được giả định danh sách luôn giống nhau** giữa Windows, Linux, container, network filesystem và provider tùy chỉnh.

`supportedFileAttributeViews()` mang ý nghĩa **provider/filesystem-level**. Nếu provider quản lý nhiều file store, một view có trong tập có thể **không được hỗ trợ tại mọi store hoặc mọi đường dẫn**. Nó cũng không đồng nghĩa bạn đang có **quyền đọc/ghi** toàn bộ metadata ở một file cụ thể.

### 5.2 Kiểm tra view trên một `FileStore`

`FileStore` có hai overload quan trọng:

```java
boolean byName = store.supportsFileAttributeView("posix");
boolean byClass =
        store.supportsFileAttributeView(PosixFileAttributeView.class);
```

Đây là **đoạn minh họa**, cần `store` là `FileStore` và import `PosixFileAttributeView`.

- Dạng `String` nhận **tên view** được provider định nghĩa; với các view chuẩn, dùng `"basic"`, `"posix"`, `"dos"`, v.v.
- Dạng `Class<? extends FileAttributeView>` nhận lớp interface view.
- Một store hỗ trợ `basic` không kéo theo hỗ trợ `posix` hay `acl`.
- Nếu view không được hỗ trợ, kết quả thường là `false` theo contract; cũng cần xử lý các lỗi liên quan đến đối số/provider theo tài liệu cụ thể.

**Đừng nhầm `supportedFileAttributeViews()` (số nhiều, thuộc `FileSystem`) với `supportsFileAttributeView(...)` (hỏi `FileStore` riêng lẻ).** `FileStore` không có cùng phương thức trả `Set<String>` với tên như ở `FileSystem`.

### 5.3 Kiểm tra view tại một `Path` và đọc thuộc tính

Để truy cập view của file cụ thể:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
        path, BasicFileAttributeView.class);
```

Đây là **đoạn minh họa**, cần import `Files` và `BasicFileAttributeView`. Giá trị có thể là `null` nếu view không được hỗ trợ. Nếu có view, lời gọi như `view.readAttributes()` còn có thể ném `IOException` do quyền truy cập, file biến mất hoặc lỗi filesystem.

Đọc một nhóm thuộc tính:

```java
BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class);
long fileSizeBytes = attrs.size();
boolean isDirectory = attrs.isDirectory();
```

Đây là **mã minh họa**, cần import `BasicFileAttributes`, `Files` và xử lý `IOException`. `attrs.size()` là **kích thước của file/entry**, không phải tổng dung lượng của `FileStore`. Hãy phân biệt:

```text
FileStore.getTotalSpace()      -> tổng dung lượng của store (byte)
FileStore.getUsableSpace()     -> dung lượng dự kiến khả dụng cho JVM (byte)
BasicFileAttributes.size()     -> kích thước một mục/path (byte)
```

## 6. Ví dụ 2 — ba cấp kiểm tra attribute view

Tạo tệp `FileStoreViewsDemo.java`:

```java
import java.nio.file.FileStore;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Set;

public class FileStoreViewsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("store-views-");
        try {
            Set<String> providerViews =
                    FileSystems.getDefault().supportedFileAttributeViews();
            FileStore store = Files.getFileStore(dir);
            System.out.println("provider basic="
                    + providerViews.contains("basic"));
            System.out.println("store basic by name="
                    + store.supportsFileAttributeView("basic"));
            System.out.println("store basic by class="
                    + store.supportsFileAttributeView(BasicFileAttributeView.class));
            BasicFileAttributes attrs =
                    Files.readAttributes(dir, BasicFileAttributes.class);
            System.out.println("directory via basic=" + attrs.isDirectory());
            System.out.println("provider posix="
                    + providerViews.contains("posix"));
            System.out.println("store posix="
                    + store.supportsFileAttributeView(PosixFileAttributeView.class));
            System.out.println("store dos="
                    + store.supportsFileAttributeView(DosFileAttributeView.class));
        } finally {
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileStoreViewsDemo.java
java FileStoreViewsDemo
```

Đầu ra **đã kiểm thử trên một môi trường Java 17 dùng NTFS**:

```text
provider basic=true
store basic by name=true
store basic by class=true
directory via basic=true
provider posix=false
store posix=false
store dos=true
```

**Các dòng `posix`/`dos` có thể khác trên Linux, macOS, network store hoặc provider khác.** Đây là kết quả môi trường, **không phải kỳ vọng phổ quát**. Ngay cả trên hai file store cùng hệ điều hành, tập view hỗ trợ có thể khác.

**Ý nghĩa của từng nhóm kiểm tra:**

1. `providerViews.contains("basic")` hỏi tầng filesystem mặc định có khai báo view `basic` không.
2. Hai cách `store.supportsFileAttributeView(...)` hỏi **store nơi thư mục tạm đang nằm** có hỗ trợ `basic` không.
3. `Files.readAttributes(dir, BasicFileAttributes.class)` thực sự truy cập metadata của **đường dẫn** và biết đó là directory.
4. `PosixFileAttributeView` và `DosFileAttributeView` được hỏi riêng vì support là đặc tính provider/store, không phải một lựa chọn mà ứng dụng tự bật.
5. Tất cả truy vấn diễn ra trên môi trường hiện tại. Để chương trình không bị gắn cứng vào Windows/Linux, hãy **nhánh hành vi theo khả năng runtime**.

**Lưu ý:** code chỉ *hỏi* có hỗ trợ, không hề thay đổi permission, hidden flag hoặc ACL. Nếu chức năng chính yêu cầu ghi POSIX permissions, kiểm tra support mới là bước đầu; vẫn cần xử lý quyền truy cập và lỗi thực tế ở lúc gọi `Files.setPosixFilePermissions` hoặc phương thức của view.

## 7. `basic`, `posix`, `dos`, `acl` và `user`: chọn view đúng bài toán

### View `basic`

`BasicFileAttributes` cho biết:

- `size()`: kích thước file/entry, theo byte.
- `lastModifiedTime()`, `lastAccessTime()`, `creationTime()`: các mốc thời gian khi provider có hỗ trợ thích hợp.
- `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `isOther()`: loại mục.
- `fileKey()`: khóa nhận dạng do provider trả, **có thể `null`**.

Đây là nhóm metadata nền tảng, thường dễ dùng nhất khi chỉ cần xem loại file hoặc kích thước. Không cần gọi `Files.getFileStore` chỉ để đọc `BasicFileAttributes` của một đường dẫn.

### View `posix`

`PosixFileAttributeView` và `PosixFileAttributes` cung cấp mô hình permissions, owner/group kiểu POSIX. Trên provider hỗ trợ, có thể dùng:

```java
Set<PosixFilePermission> perms = Files.getPosixFilePermissions(path);
```

Đây là **mã minh họa**; cần import `Set`, `PosixFilePermission` và `Files`; phương thức có thể ném `IOException` hoặc `UnsupportedOperationException` nếu filesystem không hỗ trợ.

**Không viết chương trình luôn gọi `Files.setPosixFilePermissions` mà không kiểm tra**, vì API đó có thể thất bại trên môi trường chỉ hỗ trợ DOS/ACL. Ngoài ra, permission bits POSIX không phản ánh đầy đủ mọi mô hình bảo mật phức tạp.

### View `dos`

`DosFileAttributeView` hỗ trợ các thuộc tính như **read-only**, **hidden**, **system**, **archive** theo provider. Chúng **khác** với `FileStore.isReadOnly()`:

- `FileStore.isReadOnly()` nói về khả năng ghi của **store** nói chung.
- `DosFileAttributes.isReadOnly()` nói về thuộc tính **một file/entry**.
- Một store báo có thể ghi không đồng nghĩa mọi file đều ghi được, vì còn ACL/permission/lock.

### View `acl` và `owner`

`AclFileAttributeView` dành cho access-control list và `FileOwnerAttributeView` cho owner khi provider hỗ trợ. Mô hình phân quyền ACL có thể phức tạp hơn mô hình POSIX 9 bit. Tránh tự chuyển ACL thành chuỗi `rwx` rồi tuyên bố đã giữ nguyên chính sách bảo mật.

### View `user`

`UserDefinedFileAttributeView` cho phép truy cập một số **extended attributes** do ứng dụng đặt, tùy filesystem và provider. Không nên xem nó như một kho key-value bền vững, kích thước không giới hạn hoặc có sẵn ở mọi môi trường. Nếu dữ liệu metadata là phần thiết yếu của ứng dụng, cần có lựa chọn fallback/di chuyển dữ liệu và test phù hợp.

## 8. Dùng khả năng được hỗ trợ để chọn đường xử lý

Một quy trình portable cho chức năng **yêu cầu POSIX permissions** có thể là:

```java
FileStore store = Files.getFileStore(path);
if (!store.supportsFileAttributeView(PosixFileAttributeView.class)) {
    throw new UnsupportedOperationException(
            "POSIX file permissions are not available here");
}
Set<PosixFilePermission> permissions =
        Files.getPosixFilePermissions(path);
```

Đây là **đoạn minh họa**, cần import `FileStore`, `Files`, `PosixFileAttributeView`, `PosixFilePermission`, `Set`, biến `path` và xử lý `IOException`. Nếu view không có, lỗi được trình bày rõ thay vì bí mật thử POSIX rồi bỏ qua thất bại.

Tuy nhiên, **support-check không phải quyền truy cập**: ngay sau khi trả `true`, file vẫn có thể bị xóa, đổi quyền, hoặc operation tiếp theo bị từ chối. **Đừng sử dụng kết quả support-check như cam kết thao tác chắc chắn thành công**.

Nếu POSIX chỉ là tính năng tùy chọn, ứng dụng có thể chọn policy thay thế thích hợp. Ví dụ một công cụ sao lưu có thể ghi lại metadata nào đã có/không có, thay vì âm thầm bỏ qua quyền khi mục tiêu yêu cầu bảo toàn security metadata.

## 9. Khi nào cần lấy danh sách `FileStore` của một filesystem?

Ngoài `Files.getFileStore(path)`, Java cho phép lấy **các FileStore mà FileSystem cung cấp**:

```java
for (FileStore store : FileSystems.getDefault().getFileStores()) {
    System.out.println(store.name() + " / " + store.type());
}
```

Đây là **mã minh họa**, cần import `FileStore` và `FileSystems`. Số store được liệt kê, thứ tự, tên và các store có thể truy cập đều phụ thuộc provider/môi trường.

**Chọn đúng API theo câu hỏi:**

- “File đầu ra ở thư mục `/data/export` sẽ được ghi lên store nào?” → `Files.getFileStore(exportDirectory)`.
- “Provider mặc định cho phép liệt kê những store nào?” → `FileSystems.getDefault().getFileStores()`.
- “Provider/filesystem hỗ trợ những view attribute nào?” → `fileSystem.supportedFileAttributeViews()`.
- “Store đang chứa đường dẫn này có hỗ trợ POSIX không?” → `store.supportsFileAttributeView("posix")`.
- “File cụ thể có thuộc tính hidden/permissions gì?” → `Files.readAttributes` hoặc `Files.getFileAttributeView` với view thích hợp.

Không duyệt `getFileStores()` rồi tự chọn store có tên gần giống với đường dẫn một cách suy đoán. `Files.getFileStore(path)` là câu hỏi đúng khi đã có một đường dẫn đích.

## 10. Kiểm tra dung lượng trước khi ghi: có ích nhưng không phải bảo đảm

Một ứng dụng cần tạo file dung lượng dự kiến 4 GiB có thể muốn cảnh báo nếu store chỉ còn ít byte usable:

```java
FileStore store = Files.getFileStore(destinationDirectory);
long usableBytes = store.getUsableSpace();
if (usableBytes < expectedBytes) {
    throw new IOException("Insufficient estimated usable space");
}
```

Đây là **mã minh họa**, cần biến `destinationDirectory`, `expectedBytes` và xử lý/khai báo `IOException`. `expectedBytes` phải là **số byte dự kiến của dữ liệu thực sự sẽ ghi**, không phải số ký tự `String.length()` khi mã hóa UTF-8.

Nhưng kiểm tra này chỉ là **preflight advisory**:

1. Giữa lúc đọc `usableBytes` và lúc ghi, tiến trình khác có thể dùng hết dung lượng (**TOCTOU**).
2. Dung lượng cho JVM hiện tại không phản ánh đầy đủ quota theo file/user/container hoặc mọi giới hạn hệ thống trong mọi provider.
3. Ghi file có thể cần metadata, directory entry, block allocation hoặc journal overhead.
4. File có thể nằm trên đường dẫn mount khác sau khi chuyển hoặc do symlink/mount thay đổi.
5. Quyền truy cập, permission/ACL, file lock và đường dẫn cha có thể khiến thao tác thất bại dù usable rất lớn.
6. Ghi nén/thưa/sparse/compression có thể làm dung lượng vật lý khác kích thước logic; dự đoán từ payload không luôn chính xác.

**Vì vậy:** dùng `getUsableSpace` để cảnh báo/lập kế hoạch sơ bộ, nhưng vẫn **bắt và xử lý `IOException` trong lúc ghi**, xác nhận kích thước/checksum khi cần, và có chiến lược rollback/cleanup cho file không hoàn chỉnh.

### Khi tính byte cần chú ý encoding

`"Xin chào 😊".length()` là số UTF-16 code unit của chuỗi Java, trong khi dữ liệu UTF-8 có thể dài hơn:

```java
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
long expectedBytes = encoded.length;
```

Đây là **mã minh họa**, cần có `String text` và import `StandardCharsets`. Với stream lớn, không nên tạo `byte[]` chứa toàn bộ payload chỉ để biết độ dài; chọn cách tính/ước lượng byte của format hoặc đếm trong lúc serialize khi kiến trúc cho phép.

## 11. Ví dụ 3 — kiểm tra ước lượng bằng phép so sánh an toàn

Tạo tệp `SpacePreflightDemo.java`:

```java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class SpacePreflightDemo {
    static boolean enoughForEstimate(long estimatedBytes, long usableBytes) {
        if (estimatedBytes < 0 || usableBytes < 0) {
            throw new IllegalArgumentException("Negative size");
        }
        return usableBytes >= estimatedBytes;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("zero estimate="
                + enoughForEstimate(0, 0));
        System.out.println("estimate fits="
                + enoughForEstimate(1024, 4096));
        System.out.println("estimate exceeds="
                + enoughForEstimate(4097, 4096));

        Path temp = Files.createTempDirectory("preflight-space-");
        try {
            FileStore store = Files.getFileStore(temp);
            long usable = store.getUsableSpace();
            System.out.println("usable nonnegative=" + (usable >= 0));
            System.out.println("zero bytes within measured usable="
                    + enoughForEstimate(0, usable));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SpacePreflightDemo.java
java SpacePreflightDemo
```

Kết quả đã kiểm thử trong môi trường có truy vấn dung lượng thành công:

```text
zero estimate=true
estimate fits=true
estimate exceeds=false
usable nonnegative=true
zero bytes within measured usable=true
```

Các phép kiểm thử bằng số cụ thể chứng minh ý nghĩa của phương thức `enoughForEstimate`:

- Nếu dự kiến 1.024 byte và usable 4.096 byte, phép so sánh cho `true`.
- Nếu dự kiến 4.097 byte và usable 4.096 byte, kết quả `false`.
- Nếu dữ liệu đầu vào âm, phương thức ném `IllegalArgumentException` để tránh âm thầm chấp nhận một kích thước vô lý.
- Ví dụ đo trực tiếp `store.getUsableSpace()` trên thư mục tạm do chương trình tạo, không dùng một con số cấu hình giả làm dung lượng thực.

**Quan trọng:** Giá trị `true` có nghĩa *ước lượng không vượt số usable đọc được tại thời điểm kiểm tra*, **không** có nghĩa “ghi chắc chắn thành công”. Trong ví dụ, việc kiểm tra **0 byte** gần như luôn khả dụng nhưng bản thân tạo file mới vẫn có thể thất bại bởi quyền, quota entry/inode, filesystem read-only hoặc lỗi I/O khác.

Nếu nghiệp vụ cần độ tin cậy cao, hãy kết hợp:
- xác định store của **thư mục đích thật**, không phải một ổ đĩa tình cờ khác;
- ước lượng byte và overhead hợp lý;
- ghi file tạm, theo dõi byte đã ghi;
- bắt lỗi ghi, dọn file tạm khi thất bại;
- publish/commit chỉ sau khi ghi và validate hoàn chỉnh.

## 12. `FileStore.isReadOnly()` khác permission của một file

`store.isReadOnly()` trả trạng thái read-only của **file store** theo provider. Đây là tín hiệu có ích nếu bạn cân nhắc thao tác ghi, nhưng không thay thế permission/ACL của đường dẫn.

Một vài tình huống:

- Store báo `isReadOnly() == true`: thao tác ghi lên đó thường không được phép; vẫn phải xem semantics và lỗi cụ thể của provider.
- Store báo `false`: bạn **vẫn có thể không có quyền ghi** vào thư mục vì ACL/POSIX permissions, owner, quota hoặc chính sách khác.
- Một file có DOS read-only flag không đồng nghĩa toàn store read-only.
- File đang được ứng dụng khác sử dụng/khóa có thể khiến ghi thất bại dù store và permissions về lý thuyết cho phép.

Một kiểm tra `Files.isWritable(path)` cũng là thông tin tại một thời điểm, **không bảo đảm lần ghi tiếp theo thành công**. Đặc biệt với một file chưa được tạo, muốn biết có thể tạo file trong directory hay không không thể chỉ dựa trên việc file chưa tồn tại.

## 13. `getAttribute(String)` của `FileStore` có phải API chuẩn cho mọi store?

`FileStore.getAttribute(String attribute)` cho phép lấy một thuộc tính do provider định nghĩa ở tầng **store**. Tên attribute và giá trị trả về **không có một bộ chung bắt buộc** cho mọi filesystem.

Đừng viết:

```java
Object x = store.getAttribute("someProviderKey");
```

rồi nghĩ mọi JVM/provider đều phải hỗ trợ key đó. Đây là **mã minh họa**, tên key chỉ mang ý nghĩa biểu trưng; ứng dụng cần đọc tài liệu provider cụ thể và xử lý `UnsupportedOperationException`/`IOException` khi không hỗ trợ.

Phân biệt:

- `FileStore.getAttribute(...)`: thuộc tính **store-specific**.
- `Files.getAttribute(path, "basic:size")`: thuộc tính **file/path-specific** theo cú pháp view:name của `Files`.
- `Files.readAttributes(path, BasicFileAttributes.class)`: đọc một nhóm metadata file kiểu mạnh.
- `FileStore.getUsableSpace()`: API chuẩn để truy vấn usable bytes; không cần đoán tên attribute provider.

Nếu mục tiêu là dung lượng, ưu tiên ba phương thức dung lượng chuẩn thay vì `getAttribute` không portable.

## 14. Đừng suy ra mọi file đều thuộc cùng một store

Trong một ứng dụng có nhiều mount, container volume, network share hoặc virtual filesystem:

- Hai đường dẫn có thể cùng `FileSystem` provider nhưng nằm trên **các `FileStore` khác nhau**.
- Một đường dẫn bên trong cây directory có thể đi qua mount point sang store khác.
- File tạm do `Files.createTempFile(...)` tạo ở system temp có thể không nằm cùng store với file output.
- Thao tác move qua store có thể không hỗ trợ atomic move; hành vi copy/move và metadata có thể bị giới hạn theo provider.

Do đó, nếu cần kiểm tra dung lượng cho một file dự kiến ghi ở `/data/export`, hãy xác định store liên quan đến **vị trí đích hợp lệ**, thường qua thư mục đích tồn tại. Không lấy dung lượng của `Path.of(".")` rồi áp dụng đại cho mọi nơi.

Để tránh race khi path chưa tồn tại, chương trình có thể xác định **thư mục cha tồn tại** làm điểm tham chiếu cho preflight; tuy nhiên, kết quả vẫn chỉ là ước lượng và cần xử lý filesystem thay đổi sau đó.

## 15. Quyền, symbolic link và trạng thái đường dẫn

`Files.getFileStore(path)` và API attribute có thể chịu tác động của:

- Directory traversal permissions.
- Symbolic link và cách giải quyết đích theo provider.
- File được xóa hoặc thay thế giữa hai phép truy vấn.
- Thiết bị bị tháo/mount lại.
- Network filesystem mất kết nối.
- Một đường dẫn tương đối được diễn giải trên working directory khác nhau.

**Không dùng kết quả `normalize()` như bằng chứng đường dẫn đã được giải quyết trên filesystem.** `Path.normalize()` chỉ xử lý dấu `.` và `..` theo cú pháp, không xác thực symlink hay quyền truy cập.

Với input đường dẫn do người dùng cung cấp, cần xác thực root, quyền truy cập, symbolic link/race theo threat model. Sau khi chọn một `FileStore`, vẫn phải thực hiện thao tác thật và **bắt exception**, không tin rằng metadata đọc trước là cam kết trạng thái tương lai.

Khi truy vấn `Files.getFileAttributeView(path, clazz, LinkOption.NOFOLLOW_LINKS)`, điều đó có thể giúp hỏi attribute của **chính symlink** thay vì target khi provider hỗ trợ. Không giả định mọi view hay thao tác metadata đều hỗ trợ `NOFOLLOW_LINKS` và quyền giống nhau.

## 16. Dùng `supportedFileAttributeViews` để xây ứng dụng portable

Một chiến lược hợp lý cho công cụ quản lý file đa hệ điều hành:

1. Xác định đường dẫn và filesystem provider mà dữ liệu thực sự sử dụng.
2. Hỏi `path.getFileSystem().supportedFileAttributeViews()` để có thông tin **mức filesystem/provider**.
3. Nếu chức năng làm việc với một store cụ thể, hỏi `Files.getFileStore(path)` và `store.supportsFileAttributeView(...)`.
4. Trước thao tác thuộc tính của file, chọn view phù hợp và truy cập bằng `Files.getFileAttributeView` / `Files.readAttributes`.
5. Nếu view không hỗ trợ, từ chối chức năng yêu cầu bắt buộc hoặc dùng fallback **có chủ đích**, không âm thầm giả lập thuộc tính.
6. Dù support-check báo `true`, vẫn xử lý `IOException`, `UnsupportedOperationException` và trường hợp quyền truy cập không đủ.
7. Viết test ít nhất với cấu hình filesystem thực tế cần hỗ trợ, nhất là POSIX/DOS/ACL/ZIP/network mount.
8. Với metadata mang ý nghĩa bảo mật (permissions, ACL), không âm thầm bỏ chúng khi backup/migrate nếu contract yêu cầu giữ nguyên.

### Ví dụ quyết định: tính năng “đặt hidden flag”

Nếu `FileStore` không hỗ trợ DOS attribute view, không thể mặc nhiên gọi `Files.setAttribute(path, "dos:hidden", true)` rồi mong chạy đa nền tảng. Có thể chọn tính năng ẩn theo UI của ứng dụng thay vì sửa attribute file, hoặc báo rõ “không hỗ trợ trên store này”.

Tương tự, đổi owner hoặc chmod theo POSIX cần xác minh view và quyền phù hợp. Không dùng `FileStore` support check thay thế kiểm soát bảo mật thực sự.

## 17. Những sai lầm thường gặp

1. **Nhầm `FileStore` với một file.** `FileStore.getTotalSpace()` là dung lượng store; `BasicFileAttributes.size()` là kích thước một file.
2. **Dùng `getTotalSpace()` để quyết định đủ chỗ ghi.** Total bao gồm cả dung lượng đã dùng; nên tham khảo `getUsableSpace()`.
3. **Coi `getUnallocatedSpace()` luôn bằng `getUsableSpace()`.** Quota/reserved space có thể khiến hai số khác nhau.
4. **Bỏ đơn vị byte.** Các API trả byte, không phải KB/MB/GiB trực tiếp.
5. **Dùng `int` lưu dung lượng.** Có nguy cơ tràn số; dùng `long`.
6. **Dùng `String.length()` để đo byte UTF-8.** Chuỗi Java có UTF-16 code unit; byte mã hóa có thể khác.
7. **Tin rằng usable >= size là ghi chắc thành công.** Dung lượng thay đổi, còn permission/ACL/inode/quota/overhead và lỗi I/O.
8. **Đo dung lượng trên temp rồi áp cho output ở store khác.** Cần tham chiếu vị trí đích thích hợp.
9. **Coi `FileStore.name()` luôn có giá trị hoặc duy nhất.** Provider có thể trả chuỗi rỗng.
10. **Dựa vào `FileStore.type()` như tiêu chuẩn cross-platform.** Đây là chuỗi theo provider, có thể không portable.
11. **Nhầm `FileSystem.supportedFileAttributeViews()` với `FileStore.supportsFileAttributeView(...)`.** Tầng provider vs store cụ thể.
12. **Suy rằng mọi view trong set đều hoạt động ở mọi path.** Store, quyền và trạng thái path vẫn phải được xem xét.
13. **Dùng POSIX API trên hệ thống chỉ có DOS view.** Có thể bị unsupported; cần kiểm tra và có policy.
14. **Tưởng DOS read-only flag giống store read-only.** Một cái là thuộc tính file, một cái là khả năng lưu trữ.
15. **Cho rằng view supported đồng nghĩa có quyền sửa metadata.** Support không phải authorization.
16. **Bỏ qua exception của thao tác đọc metadata.** Path biến mất, quyền đổi hoặc network lỗi vẫn có thể xảy ra.
17. **Lạm dụng `getAttribute("...")` với key provider-specific.** Không có danh sách key chung bắt buộc.
18. **Lấy danh sách `getFileStores()` rồi đoán theo tên.** Cần `Files.getFileStore(path)` khi quan tâm nơi chứa path.
19. **Không xét symlink/mount/quota thay đổi.** Kết quả metadata có thể lỗi thời.
20. **Tưởng `isReadOnly() == false` bảo đảm ghi được.** Vẫn cần mở/ghi và xử lý lỗi thật.

## 18. Bảng chọn API theo câu hỏi

| Câu hỏi cần trả lời | API thích hợp | Lưu ý |
|---|---|---|
| Đường dẫn hiện tại thuộc store nào? | `Files.getFileStore(path)` | Có thể ném `IOException` |
| Có bao nhiêu byte tổng của store? | `store.getTotalSpace()` | Không phải dung lượng khả dụng |
| Có bao nhiêu byte chưa được cấp phát? | `store.getUnallocatedSpace()` | Có thể khác usable |
| JVM hiện có thể sử dụng khoảng bao nhiêu byte? | `store.getUsableSpace()` | Chỉ là snapshot/ước lượng |
| Store có ở chế độ read-only? | `store.isReadOnly()` | Không thay quyền file cụ thể |
| Filesystem provider hỗ trợ view tên nào? | `path.getFileSystem().supportedFileAttributeViews()` | Set tên view ở mức filesystem |
| Store đích hỗ trợ POSIX view không? | `store.supportsFileAttributeView("posix")` | Có thể khác store khác |
| Path cụ thể có metadata basic gì? | `Files.readAttributes(path, BasicFileAttributes.class)` | Lấy thuộc tính của file/entry |
| Có truy cập được một attribute view? | `Files.getFileAttributeView(path, Class)` | Có thể `null` hoặc lỗi khi dùng |
| Filesystem cho phép liệt kê store nào? | `fileSystem.getFileStores()` | Không phải phép ánh xạ path tự động |
| Một file cụ thể dài bao nhiêu byte? | `Files.size(path)` | Không phải dung lượng store |
| Có ghi file đích thành công không? | Mở/ghi/đóng, kiểm tra kết quả | Không thay bằng preflight metadata |

## 19. Câu hỏi tự luyện

**Câu 1.** `getTotalSpace()` và `getUsableSpace()` có cùng ý nghĩa không?  
**Đáp án:** không. Total là dung lượng tổng store; usable là dung lượng mà JVM có thể sử dụng theo provider tại thời điểm đo.

**Câu 2.** Vì sao không dùng `getUnallocatedSpace()` để bảo đảm ứng dụng có thể ghi hết số byte đó?  
**Đáp án:** quyền, quota, reserved space, filesystem overhead và điều kiện cạnh tranh có thể hạn chế byte thực tế có thể ghi.

**Câu 3.** `FileSystem.supportedFileAttributeViews()` khác `FileStore.supportsFileAttributeView("posix")` ở đâu?  
**Đáp án:** lời gọi đầu trả tập tên view ở tầng filesystem/provider; lời gọi sau hỏi view `posix` có được hỗ trợ trên một store cụ thể hay không.

**Câu 4.** Một store báo hỗ trợ `posix`. Có chắc được phép đổi permission trên mọi file của store không?  
**Đáp án:** không. Support không đồng nghĩa quyền thao tác; file có thể bị khóa, xóa hoặc thay quyền.

**Câu 5.** Trên hệ thống NTFS ở ví dụ, `name()` là chuỗi rỗng. Có phải `getFileStore` lỗi không?  
**Đáp án:** không. `name()` là tên do provider cung cấp và có thể rỗng, trong khi các phương thức khác vẫn trả thông tin bình thường.

**Câu 6.** Muốn biết kích thước của `report.txt`, gọi `store.getTotalSpace()` có đúng không?  
**Đáp án:** không; dùng `Files.size(reportPath)` hoặc `BasicFileAttributes.size()`.

**Câu 7.** Preflight thấy `usableBytes >= expectedBytes`. Có thể bỏ qua `IOException` khi ghi không?  
**Đáp án:** không. Đây chỉ là kiểm tra mang tính tư vấn tại thời điểm đo; thao tác ghi vẫn có thể thất bại.

**Câu 8.** Một ứng dụng muốn hiển thị dung lượng theo GiB; nên chia cho 1.000.000.000 hay 1.073.741.824?  
**Đáp án:** GiB dùng 1.073.741.824; GB thập phân mới dùng 1.000.000.000.

**Câu 9.** Nếu muốn kiểm tra DOS hidden của file, chỉ cần xem `store.isReadOnly()` không?  
**Đáp án:** không. Đó là thuộc tính khác; dùng `DosFileAttributeView`/`DosFileAttributes` theo khả năng hỗ trợ.

**Câu 10.** Tại sao một `Path` thuộc cùng default filesystem với path khác chưa chắc nằm trên cùng `FileStore`?  
**Đáp án:** filesystem/provider có thể bao gồm nhiều volume, mount, network share hoặc store logic khác nhau.

## Kết luận

**`FileStore`** là nơi Java hỏi dung lượng và thuộc tính cấp store: `getTotalSpace`, `getUnallocatedSpace`, `getUsableSpace`, `isReadOnly` và `supportsFileAttributeView`. **`FileSystem.supportedFileAttributeViews()`** lại là thông tin hỗ trợ thuộc tính ở mức filesystem/provider. Để đọc thuộc tính một file thật, dùng **`Files.readAttributes` / `Files.getFileAttributeView`** với view thích hợp.

Khi cần quyết định có đủ chỗ ghi file không, ưu tiên **`getUsableSpace`** hơn `getTotalSpace`/`getUnallocatedSpace`, nhưng luôn hiểu đó chỉ là **ước lượng thay đổi được**, không thay thế việc xử lý ngoại lệ, quota, permission và kiểm tra tính toàn vẹn sau ghi. Chọn attribute view **theo support ở môi trường chạy**, không hard-code giả định “Windows thì luôn DOS, Linux thì luôn POSIX” cho mọi provider/store.

### Tài liệu Java SE 17

- [`FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
- [`Files.getFileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystem.supportedFileAttributeViews`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html)
- [`FileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttributeView.html)
- [`BasicFileAttributeView` / `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html)
- [`PosixFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [`DosFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributeView.html)
- [`AclFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html)
- [`UserDefinedFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/UserDefinedFileAttributeView.html)
