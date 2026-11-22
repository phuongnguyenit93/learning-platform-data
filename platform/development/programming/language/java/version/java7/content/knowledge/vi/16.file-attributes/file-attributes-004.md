# Java 7 — Thuộc tính tệp: Kiểm tra khả năng hỗ trợ trước khi dùng attribute view

## 1. Bài toán: không phải hệ thống tệp nào cũng có cùng metadata

Java NIO.2 cung cấp API đọc và cập nhật **thuộc tính tệp** (*file attributes*): loại tệp, kích thước, thời điểm sửa đổi, chủ sở hữu, nhóm, quyền POSIX, cờ DOS, ACL hoặc các thuộc tính mở rộng. Các thuộc tính này không tồn tại và không vận hành giống nhau trên mọi hệ điều hành, ổ đĩa, network share, ZIP filesystem hay provider tùy biến.

Ví dụ: ứng dụng chạy trên Linux thường sử dụng quyền POSIX; một số filesystem trên Windows hỗ trợ cờ DOS và ACL; còn ZIP filesystem có thể chỉ hỗ trợ một tập metadata nhỏ hơn. Nếu gọi trực tiếp `Files.readAttributes(path, PosixFileAttributes.class)` mà không xem khả năng của provider/file store, ứng dụng có thể gặp `UnsupportedOperationException`. Nếu lấy `PosixFileAttributeView` và bỏ qua trường hợp nó bằng `null`, code có thể gặp `NullPointerException`. Kể cả khi view được hỗ trợ, **quyền truy cập và lỗi I/O vẫn có thể khiến thao tác thất bại**.

Để viết code portable trên **Java 17+**, cần hiểu ba mức kiểm tra:

1. **`FileSystem.supportedFileAttributeViews()`** — những *tên* view mà `FileSystem` công bố hỗ trợ.
2. **`FileStore.supportsFileAttributeView(...)`** — hỗ trợ trên *kho lưu trữ/volume cụ thể* chứa tệp.
3. **`Files.getFileAttributeView(path, ViewType.class, options...)`** — lấy *typed view của Path cụ thể*, có thể trả `null` nếu loại view không có.

Sau khi kiểm tra, vẫn phải **thực hiện đọc/ghi trong cơ chế xử lý ngoại lệ phù hợp**. Đây là điểm quan trọng nhất của bài.

`FileAttributeView`, `FileSystem`, `FileStore` và các API liên quan đã có từ Java 7 và **vẫn là kiến thức áp dụng hiện nay**. Các ví dụ bên dưới dùng Java 17+, không yêu cầu dùng những phiên bản Java cũ.

## 2. Attribute và attribute view khác nhau như thế nào?

**Attribute** là một giá trị metadata, chẳng hạn:

- `size`: số byte của tệp.
- `lastModifiedTime`: thời gian chỉnh sửa cuối.
- `isDirectory`, `isRegularFile`, `isSymbolicLink`: các thông tin phân loại.
- `owner`, `group`, `permissions`: chủ sở hữu, nhóm và quyền theo mô hình mà provider hỗ trợ.
- `hidden`, `readonly`: một số cờ metadata do DOS attribute view cung cấp.
- ACL entries hoặc các thuộc tính user-defined, **nếu** provider hỗ trợ.

**FileAttributeView** là giao diện định kiểu cho **một nhóm thuộc tính**. Ví dụ `BasicFileAttributeView` có `readAttributes()` và `setTimes(...)`; `PosixFileAttributeView` có thể đọc quyền POSIX và cung cấp thao tác thiết lập quyền; `AclFileAttributeView` đọc/cập nhật ACL.

Quan hệ khái niệm:

```text
Path ──getFileSystem()────► FileSystem
 │                           └── supportedFileAttributeViews()
 │                               (tập tên view ở cấp file system)
 │
 ├── Files.getFileStore(path)► FileStore
 │                           └── supportsFileAttributeView(...)
 │                               (khả năng của nơi lưu trữ cụ thể)
 │
 └── Files.getFileAttributeView(path, ViewType.class)
                             └── ViewType hoặc null
                                 └── readAttributes()/set...()
                                     (I/O thật, vẫn có thể thất bại)
```

Một `Path` là đối tượng vị trí, không phải bằng chứng metadata của tệp tồn tại; việc tạo `Path.of("missing.txt")` không tạo file trên ổ đĩa. `Files.getFileStore(path)` và các lệnh đọc thuộc tính có thể cần truy cập filesystem nên có thể ném `IOException`.

## 3. Những view có thể gặp trong Java SE 17

| Attribute view | Tên view chuẩn | Giá trị thường được truy cập | Tình trạng hỗ trợ |
| --- | --- | --- | --- |
| `BasicFileAttributeView` | `basic` | Kích thước, loại tệp, thời điểm, `fileKey` | **Bắt buộc hỗ trợ** trên mọi FileSystem NIO |
| `PosixFileAttributeView` | `posix` | Quyền owner/group/others, nhóm, chủ sở hữu và basic attributes | **Tùy filesystem/file store** |
| `DosFileAttributeView` | `dos` | Các cờ `readonly`, `hidden`, `system`, `archive` cùng basic attributes | **Tùy filesystem/file store** |
| `AclFileAttributeView` | `acl` | Danh sách Access Control Entries (ACL), owner | **Tùy filesystem/file store** |
| `FileOwnerAttributeView` | `owner` | Chủ sở hữu tệp | **Tùy filesystem/file store** |
| `UserDefinedFileAttributeView` | `user` | Thuộc tính mở rộng theo cặp tên/giá trị byte | **Tùy filesystem/file store** |

Một số provider có thể công bố tên view bổ sung ngoài bảng, ví dụ view mang tính đặc thù của provider. Không hard-code giả định rằng chỉ có đúng sáu tên ở mọi môi trường.

**Quan trọng:** `BasicFileAttributeView` là điểm chung bắt buộc; còn POSIX, DOS, ACL, owner, user-defined đều cần kiểm tra. Tên `dos` là tên API Java SE vẫn được hỗ trợ nơi provider có khả năng; điều đó **không có nghĩa** cờ DOS là cơ chế phân quyền tổng quát nên được ưu tiên cho mọi ứng dụng mới. Khi viết code xử lý quyền, chọn **mô hình quyền thực tế của filesystem** và xác minh khả năng.

### 3.1. Vì sao `basic` là ngoại lệ đặc biệt?

Javadoc `FileSystem.supportedFileAttributeViews()` yêu cầu tập tên luôn chứa `"basic"`. `FileStore.supportsFileAttributeView(BasicFileAttributeView.class)` luôn trả `true`; `Files.getFileAttributeView(path, BasicFileAttributeView.class)` cũng luôn trả một view loại basic theo hợp đồng API.

Tuy vậy, `basic` **được hỗ trợ không đồng nghĩa việc đọc luôn thành công**. Nếu tệp bị xóa giữa lúc kiểm tra và lúc đọc, thiếu quyền hoặc provider lỗi, `basic.readAttributes()` vẫn có thể ném `IOException`. Một số thuộc tính basic là tùy chọn hoặc được provider mô phỏng khi tệp không có thông tin tương ứng; ví dụ độ chính xác timestamp hay tính khả dụng của `fileKey` không giống nhau ở mọi filesystem.

## 4. Kiểm tra tầng 1: FileSystem.supportedFileAttributeViews()

`Path.getFileSystem()` cho biết filesystem sở hữu Path. Từ đó, gọi:

```java
Path path = Path.of("data", "sample.txt");
Set<String> viewNames = path.getFileSystem()
        .supportedFileAttributeViews();

boolean supportsBasic = viewNames.contains("basic");
boolean advertisesPosix = viewNames.contains("posix");
boolean advertisesDos = viewNames.contains("dos");
```

Đây là **snippet trong phương thức** với import `java.nio.file.Path` và `java.util.Set`. `Set<String>` chứa **tên view**, không phải instances của view. Tập được trả về **không cho phép sửa đổi**; đừng gọi `viewNames.add("posix")` hoặc nghĩ thêm phần tử làm filesystem hỗ trợ thêm thuộc tính.

**Dùng khi nào?**

- Liệt kê capability rộng của một `FileSystem` khi khởi động ứng dụng.
- Chọn tính năng UI hoặc đường xử lý có điều kiện theo provider.
- Lọc nhanh các thao tác chắc chắn không hỗ trợ: nếu tên `"posix"` không xuất hiện, không nên gọi code yêu cầu POSIX metadata trên filesystem đó.

**Giới hạn:** Một `FileSystem` có thể gồm **nhiều FileStore** với khả năng khác nhau. Tên view được công bố ở cấp filesystem **không bảo đảm** rằng mọi volume/mount/file trong đó có cùng tập view. Với một Path cụ thể, nên kiểm tra file store tương ứng hoặc typed view trước khi thao tác.

### 4.1. Không nhầm FileSystem với FileStore

`FileSystem` là đối tượng quản lý cách truy cập cây tệp của provider; `FileStore` đại diện storage pool, volume, partition hoặc cơ chế lưu trữ khác. Một default FileSystem trên hệ thống có thể bao gồm nhiều ổ đĩa/mount. Vì vậy:

- `fs.supportedFileAttributeViews().contains("posix")` chỉ là thông tin cấp filesystem.
- `store.supportsFileAttributeView("posix")` nói về file store mà ta đang định dùng.
- `Files.getFileAttributeView(path, PosixFileAttributeView.class)` cho biết typed view có sẵn cho Path cụ thể hay không.

Ba cách kiểm tra **bổ sung nhau**, không hoàn toàn thay thế nhau.

## 5. Kiểm tra tầng 2: FileStore.supportsFileAttributeView()

Khi đã có Path của tệp **đang tồn tại**, lấy FileStore:

```java
Path file = Path.of("data", "sample.txt");
FileStore store = Files.getFileStore(file);

boolean basic = store.supportsFileAttributeView(BasicFileAttributeView.class);
boolean posix = store.supportsFileAttributeView(PosixFileAttributeView.class);
boolean dosByName = store.supportsFileAttributeView("dos");
```

Đây là snippet đặt trong phương thức có import `FileStore`, `Files`, `Path`, `BasicFileAttributeView`, `PosixFileAttributeView` và xử lý `IOException`. Nếu file chưa tồn tại, `Files.getFileStore(file)` có thể ném `NoSuchFileException` hoặc một `IOException` khác; **đừng gọi trước khi có Path tồn tại rồi cho rằng nó mô tả chắc chắn nơi file sẽ được tạo trong tương lai**.

Hai overload:

```java
boolean supportsFileAttributeView(Class<? extends FileAttributeView> type);
boolean supportsFileAttributeView(String name);
```

Đây là **chữ ký rút gọn để học**, không cần khai báo trong code. Overload nhận `Class` có lợi khi bạn đã biết kiểu view cụ thể, còn overload nhận tên thuận tiện cho danh sách capability hoặc cấu hình view-name.

### 5.1. Không hard-code một hệ điều hành thành một tập view

Ngay trên cùng OS, hai FileStore có thể khác nhau: local filesystem, network mount, ZIP provider, filesystem ảo hoặc volume có cấu hình riêng. Đừng viết:

```java
boolean posix = System.getProperty("os.name").contains("Linux");
```

rồi coi đó là điều kiện đủ để gọi POSIX view. Đây là **đoạn minh họa cách suy đoán sai**: tên hệ điều hành không nói chắc capability của **file store thực tế** đang chứa Path.

Thay bằng probe ở tầng filesystem/storage, sau đó đọc view của Path cụ thể và xử lý ngoại lệ.

### 5.2. Hạn chế khi hỏi FileStore từ thiết bị không cục bộ

Javadoc `FileStore.supportsFileAttributeView(...)` lưu ý với **default provider và file store không phải thiết bị local**, phương thức có thể không bảo đảm kết quả chính xác. Network drive, filesystem được mount hoặc provider đặc thù cần được kiểm thử trên môi trường đích.

Do đó, kiểm tra trước chỉ là một **capability probe**. Thành công của thao tác `view.readAttributes()` vẫn là điều phải xác minh. Ngay cả khi probe trả true, vẫn có thể nhận `IOException` vì thiếu quyền, file không còn tồn tại hoặc lỗi I/O.

## 6. Kiểm tra tầng 3: Files.getFileAttributeView(...) trả view hay null

Khi muốn làm việc type-safe với một attribute view cụ thể, dùng:

```java
PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);

if (view != null) {
    PosixFileAttributes attrs = view.readAttributes();
    System.out.println(attrs.permissions());
} else {
    System.out.println("POSIX metadata is unavailable on this path");
}
```

Đây là **snippet trong phương thức** có `Path path`, import `Files`, `PosixFileAttributeView` và `PosixFileAttributes`, đồng thời xử lý `IOException`.

**Hợp đồng quan trọng:** `Files.getFileAttributeView(path, type, options...)` trả **view instance nếu view type được hỗ trợ**, hoặc **`null` nếu loại view không có**. Với `BasicFileAttributeView.class`, Javadoc bảo đảm trả instance. Không gọi `view.readAttributes()` trên một view tùy chọn trước khi kiểm tra `view != null`.

Một view object có thể được tạo mà chưa đọc thành công thuộc tính thực. Đừng coi `view != null` là bảo đảm “file tồn tại, đang cho phép đọc, và thao tác sẽ thành công”.

### 6.1. Với thuộc tính tùy chọn, có nên kiểm tra đủ cả ba tầng?

Trong một ứng dụng cần làm rõ capability theo cấp, trình tự này hữu ích:

```java
boolean declared = path.getFileSystem()
        .supportedFileAttributeViews().contains("posix");

boolean onStore = declared
        && Files.getFileStore(path)
                .supportsFileAttributeView(PosixFileAttributeView.class);

if (onStore) {
    PosixFileAttributeView view = Files.getFileAttributeView(
            path, PosixFileAttributeView.class);
    if (view != null) {
        PosixFileAttributes attrs = view.readAttributes();
        // Xử lý attrs tại đây; vẫn cần bắt IOException bên ngoài.
    }
}
```

Đây là snippet trong phương thức và cần xử lý `IOException`. Đây là mô hình **thăm dò theo ba cấp**, đặc biệt phù hợp khi ứng dụng muốn quyết định cách hiển thị tính năng hoặc chọn một nhánh xử lý.

Tuy nhiên, không bắt buộc **mọi lần đọc đều gọi cả ba tầng**. Nếu chỉ cần POSIX attributes ở một Path, có thể gọi `Files.getFileAttributeView(...)` rồi kiểm tra null và xử lý IOException ngay. Không cần thực hiện ba phép probe liên tiếp trong vòng lặp xử lý hàng triệu file khi hiệu năng là mối quan tâm; tối ưu dựa trên yêu cầu, caching hợp lý và dữ liệu đo thực tế.

### 6.2. Sử dụng `NOFOLLOW_LINKS` khi chính symbolic link là đối tượng cần xem

```java
BasicFileAttributeView ownEntry = Files.getFileAttributeView(
        path,
        BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

BasicFileAttributes attrs = ownEntry.readAttributes();
System.out.println(attrs.isSymbolicLink());
```

Đây là snippet trong phương thức với `Path path` và import `LinkOption`, `BasicFileAttributeView`, `BasicFileAttributes`, `Files`; cần xử lý IOException.

Theo mặc định, các API đọc thuộc tính thường **đi theo symbolic link** tới đích; với `NOFOLLOW_LINKS`, view được yêu cầu đọc **entry link** nếu provider hỗ trợ. Nếu provider không hỗ trợ symbolic links, tùy chọn này có thể được bỏ qua theo hợp đồng. Dùng tùy chọn theo đúng đối tượng nghiệp vụ muốn đọc, không phải như một “công tắc bảo mật tuyệt đối”.

## 7. Chương trình Java 17+ đầy đủ và kết quả thực nghiệm

Ví dụ tạo một file tạm thật, ghi ba byte UTF-8, hỏi capability ở cả ba tầng và chỉ đọc view POSIX/DOS **nếu capability được công bố**. Chương trình **không sửa quyền, owner, ACL hay các metadata đặc biệt**; nó chỉ đọc. File tạm bị xóa trong `finally`.

Tạo tệp **`AttributeViewSupportDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.FileSystem;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Set;

public class AttributeViewSupportDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("attribute-view-demo-", ".txt");
        try {
            Files.writeString(file, "abc", StandardCharsets.UTF_8);

            FileSystem fs = file.getFileSystem();
            FileStore store = Files.getFileStore(file);
            Set<String> supported = fs.supportedFileAttributeViews();

            System.out.println("filesystem has basic = " +
                    supported.contains("basic"));
            System.out.println("store has basic = " +
                    store.supportsFileAttributeView(BasicFileAttributeView.class));

            BasicFileAttributeView basic = Files.getFileAttributeView(
                    file, BasicFileAttributeView.class, LinkOption.NOFOLLOW_LINKS);
            System.out.println("basic view present = " + (basic != null));
            if (basic == null) {
                throw new IllegalStateException("Basic view must be available");
            }
            System.out.println("basic regular file = " +
                    basic.readAttributes().isRegularFile());
            System.out.println("basic size = " + basic.readAttributes().size());

            boolean posixPossible = supported.contains("posix")
                    && store.supportsFileAttributeView(PosixFileAttributeView.class);
            System.out.println("posix advertised = " + posixPossible);
            if (posixPossible) {
                PosixFileAttributeView posix = Files.getFileAttributeView(
                        file, PosixFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);
                if (posix != null) {
                    posix.readAttributes();
                    System.out.println("posix view = usable");
                } else {
                    System.out.println("posix view = unavailable");
                }
            } else {
                System.out.println("posix view = skipped");
            }

            boolean dosPossible = supported.contains("dos")
                    && store.supportsFileAttributeView(DosFileAttributeView.class);
            System.out.println("dos advertised = " + dosPossible);
            if (dosPossible) {
                DosFileAttributeView dos = Files.getFileAttributeView(
                        file, DosFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);
                if (dos != null) {
                    dos.readAttributes();
                    System.out.println("dos view = usable");
                } else {
                    System.out.println("dos view = unavailable");
                }
            } else {
                System.out.println("dos view = skipped");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AttributeViewSupportDemo.java
java AttributeViewSupportDemo
```

**Stdout thực tế trên máy kiểm thử Windows với JDK 24 (không phải output cố định cho mọi OS):**

```text
filesystem has basic = true
store has basic = true
basic view present = true
basic regular file = true
basic size = 3
posix advertised = false
posix view = skipped
dos advertised = true
dos view = usable
```

**Các dòng có thể thay đổi theo nền tảng:** `posix advertised`, `posix view`, `dos advertised`, `dos view`. Chẳng hạn file store hỗ trợ POSIX có thể in `posix advertised = true` rồi `posix view = usable`; một provider không có DOS view sẽ in `dos advertised = false` và `dos view = skipped`. Những khác biệt đó là **mục tiêu của bài**, không phải lỗi chương trình.

**Vì sao một số dòng nên luôn giống nhau khi I/O thành công?**

1. `"basic"` luôn thuộc tập view được hỗ trợ theo hợp đồng `FileSystem`.
2. `FileStore.supportsFileAttributeView(BasicFileAttributeView.class)` trả true theo hợp đồng.
3. `Files.getFileAttributeView(..., BasicFileAttributeView.class)` trả một view không null.
4. File tạm là regular file và nội dung “abc” UTF-8 có ba byte.
5. Các nhánh POSIX/DOS chỉ chạy nếu hai tầng capability công bố hỗ trợ, sau đó còn kiểm tra typed view null trước khi đọc.

Nếu `Files.createTempFile`, `getFileStore`, `readAttributes` hoặc cleanup gặp lỗi filesystem, chương trình có thể ném IOException; đó là hành vi hợp lệ cần xử lý trong ứng dụng thật. Ví dụ dùng `throws IOException` ở `main` để minh họa ngắn, không phải chính sách xử lý lỗi mặc định cho service.

### 7.1. Mục đích của ví dụ, không phải “bắt hệ thống hỗ trợ cả hai”

Chương trình không gọi `setPermissions`, `setReadOnly` hoặc `setAcl` chỉ để thử xem có hỗ trợ không; việc thử ghi metadata có thể thay đổi quyền, tác động file thật hoặc gây lỗi permission. Thay vào đó nó dùng các API capability hiện hành và một tệp tạm do chính chương trình tạo.

Cũng không dùng `System.getProperty("os.name")` để đoán trước sẽ có POSIX/DOS. Điều kiện là capability thực tế của FileSystem/FileStore liên quan tới Path.

## 8. Cách đọc attributes mà không phải cầm một view instance

NIO.2 có nhiều cách truy cập metadata:

### 8.1. Read strongly typed basic attributes

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);
System.out.println(attrs.size());
System.out.println(attrs.lastModifiedTime());
```

Đây là snippet trong phương thức có `Path path`, import `Files` và `BasicFileAttributes`, xử lý IOException. Basic attributes là kiểu chung được bảo đảm hỗ trợ; thao tác đọc vẫn có thể thất bại nếu Path không truy cập được.

### 8.2. Read POSIX attributes có kiểm tra khả năng trước

```java
PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view != null) {
    PosixFileAttributes attrs = view.readAttributes();
    System.out.println(PosixFilePermissions.toString(attrs.permissions()));
} else {
    System.out.println("POSIX attributes are unavailable");
}
```

Đây là snippet với imports `PosixFileAttributeView`, `PosixFileAttributes`, `PosixFilePermissions`, `Files`, `Path`, `LinkOption`; vẫn cần xử lý IOException.

**Không gọi** `Files.readAttributes(path, PosixFileAttributes.class)` một cách vô điều kiện trong ứng dụng cần chạy đa nền tảng. Nếu provider không có POSIX view, overload kiểu class có thể ném `UnsupportedOperationException`. Có thể xử lý lỗi này hoặc dùng typed-view probe.

### 8.3. Dynamic access bằng tên view và tên thuộc tính

```java
Map<String, Object> attrs =
        Files.readAttributes(path, "basic:size,lastModifiedTime");
System.out.println(attrs.get("size"));
```

Đây là snippet trong phương thức với `Path path` và import `java.util.Map`. Chuỗi cú pháp có dạng **`view-name:attribute-list`**, ví dụ `"basic:size,lastModifiedTime"`. Nó hữu ích khi tên thuộc tính được lựa chọn động, nhưng mất một phần kiểm tra kiểu tại compile time; code phải biết loại đối tượng được trả về.

Nếu chuỗi yêu cầu view/thuộc tính không được hỗ trợ, có thể nhận `UnsupportedOperationException` hoặc `IllegalArgumentException` tùy trường hợp; I/O vẫn có thể ném IOException. Đừng dùng dynamic string API để né bước kiểm tra support.

### 8.4. Files.getAttribute / Files.setAttribute

Các API như:

```java
Object size = Files.getAttribute(path, "basic:size");
```

cũng sử dụng tên view/attribute. Với `Files.setAttribute(path, "posix:permissions", value)`, chỉ được thực hiện khi permission model, kiểu giá trị, provider và quyền của process phù hợp. **Việc view tồn tại không xác nhận người dùng có quyền sửa attribute.**

Trong code mới có kiểu attribute rõ ràng, các typed interfaces và `Files.readAttributes(path, AttributeType.class)` thường dễ đọc, ít nhầm kiểu hơn.

## 9. View optional: POSIX, DOS, ACL, owner và user-defined

### 9.1. POSIX permissions

`PosixFileAttributeView` hỗ trợ mô hình owner/group/others theo các cờ quyền đọc, ghi và thực thi của POSIX. Phù hợp với filesystem/provider cung cấp semantics tương ứng. Việc đọc:

```java
PosixFileAttributeView posix = Files.getFileAttributeView(
        file, PosixFileAttributeView.class);
if (posix != null) {
    Set<PosixFilePermission> permissions =
            posix.readAttributes().permissions();
    System.out.println(PosixFilePermissions.toString(permissions));
}
```

Đây là snippet trong phương thức có `Path file` và các imports thuộc `java.nio.file.attribute`, `Files`, `Set`; cần xử lý IOException.

Nếu ứng dụng **bắt buộc** phải đặt quyền POSIX cụ thể để bảo vệ dữ liệu, không nên im lặng bỏ bước thiết lập quyền khi view không hỗ trợ. Khi security requirement không thể thỏa, **fail closed** hoặc chuyển sang cơ chế bảo vệ phù hợp được thiết kế riêng cho provider.

### 9.2. DOS metadata flags

`DosFileAttributeView` cung cấp các cờ như read-only, hidden, system và archive khi provider hỗ trợ:

```java
DosFileAttributeView dos = Files.getFileAttributeView(
        file, DosFileAttributeView.class);
if (dos != null) {
    DosFileAttributes attrs = dos.readAttributes();
    System.out.println(attrs.isHidden());
}
```

Đây là snippet với import `DosFileAttributeView` và `DosFileAttributes`, cộng xử lý IOException. Những cờ này là metadata theo mô hình DOS; **không tương đương hoàn toàn với permission/ACL của hệ thống** và không nên dùng để thay cơ chế authorization của ứng dụng.

### 9.3. ACL metadata

`AclFileAttributeView` mô tả danh sách ACL entries và owner nếu file store hỗ trợ:

```java
AclFileAttributeView acl = Files.getFileAttributeView(
        file, AclFileAttributeView.class);

if (acl != null) {
    int entryCount = acl.getAcl().size();
    System.out.println("ACL entries: " + entryCount);
}
```

Snippet trong phương thức có import `AclFileAttributeView` và xử lý IOException. Không tự log toàn bộ danh sách identity/quyền truy cập vào nơi không được phép, vì ACL có thể chứa dữ liệu nhạy cảm. Cấu trúc và cách diễn giải ACL còn phụ thuộc provider; không mặc định POSIX permission bits có thể biểu diễn mọi ACL entry.

### 9.4. Owner metadata

`FileOwnerAttributeView` cho quyền truy cập thông tin owner ở những provider hỗ trợ. Có thể kiểm tra:

```java
FileOwnerAttributeView owner = Files.getFileAttributeView(
        file, FileOwnerAttributeView.class);

if (owner != null) {
    System.out.println(owner.getOwner().getName());
}
```

Đây là snippet có import và xử lý IOException. Tên owner phụ thuộc hệ thống và không phải định danh portable giữa các máy. Muốn cấp quyền, dùng policy bảo mật của hệ thống tương ứng thay vì chỉ so chuỗi tên owner.

### 9.5. User-defined attributes

`UserDefinedFileAttributeView` cho truy cập các cặp tên/giá trị bytes do provider hỗ trợ, thường liên quan **extended attributes**:

```java
UserDefinedFileAttributeView user = Files.getFileAttributeView(
        file, UserDefinedFileAttributeView.class);

if (user != null) {
    List<String> attributeNames = user.list();
    System.out.println("User attribute count: " + attributeNames.size());
}
```

Đây là snippet trong phương thức với imports `UserDefinedFileAttributeView`, `List` và xử lý IOException. Không lưu dữ liệu bí mật hoặc trạng thái nghiệp vụ quan trọng vào extended attributes một cách tùy tiện: khả năng sao chép, đồng bộ, backup và hỗ trợ trên filesystem khác có thể khác nhau.

### 9.6. Tính sẵn có không đồng nghĩa quyền sửa

Cả `PosixFileAttributeView`, `DosFileAttributeView` và `AclFileAttributeView` đều có các phương thức **có thể sửa metadata**. Dù `supportsFileAttributeView` trả true và `getFileAttributeView` trả view khác null, việc gọi `setPermissions` / `setReadOnly` / `setAcl` vẫn có thể thất bại vì quyền process, chính sách bảo mật, read-only mount hoặc lỗi I/O.

Viết chương trình theo **khả năng, quyền và hợp đồng nghiệp vụ** — không coi capability probe như authorization check.

## 10. Thiết kế fallback: optional feature khác với yêu cầu bắt buộc

Khi view không hỗ trợ, ứng dụng cần quyết định theo bản chất tính năng.

| Tình huống | Cách xử lý hợp lý |
| --- | --- |
| Chỉ hiển thị kích thước, loại file, ngày sửa | Ưu tiên `BasicFileAttributes`, có trên mọi FileSystem NIO |
| Hiển thị thêm quyền POSIX nếu có | Kiểm tra optional; nếu không có, ẩn mục hoặc hiển thị “không hỗ trợ” |
| Yêu cầu bắt buộc phân quyền POSIX trước khi lưu bí mật | Nếu provider không hỗ trợ, **từ chối thao tác** hoặc dùng cơ chế bảo mật được thiết kế khác |
| UI xem cờ DOS/ACL nếu có | Kiểm tra view tương ứng, không ép mọi OS có cùng cờ |
| Lưu metadata mở rộng tùy chọn | Kiểm tra `UserDefinedFileAttributeView` rồi xử lý lỗi; có phương án nếu metadata không được copy |
| Đọc metadata từ network share | Probe capability nhưng vẫn dự kiến IOException và không tin tuyệt đối vào kết quả trên remote storage |
| Đọc metadata cần đúng trạng thái symlink | Chọn `NOFOLLOW_LINKS` và kiểm tra provider, không đoán dựa vào tên file |

### 10.1. Mẫu fallback type-safe không làm mất lỗi âm thầm

```java
static String describePermissions(Path path) throws IOException {
    PosixFileAttributeView view = Files.getFileAttributeView(
            path, PosixFileAttributeView.class);

    if (view == null) {
        return "POSIX permissions unavailable";
    }
    return PosixFilePermissions.toString(
            view.readAttributes().permissions());
}
```

Đây là phương thức minh họa, cần import `Path`, `Files`, `IOException` và các lớp POSIX. Nếu view không có, nó trả thông báo rõ. Nếu view có nhưng đọc lỗi, **IOException được truyền lên** thay vì ngụy trang thành “không hỗ trợ”.

**Phân biệt ba trạng thái:** *(1) Không hỗ trợ; (2) Có hỗ trợ nhưng đọc lỗi; (3) Đọc thành công.* Với ứng dụng quan trọng, không gom cả ba thành một boolean `false` vì sẽ che lỗi permission hoặc lỗi hạ tầng.

### 10.2. Nếu chỉ cần thông tin chung, đừng tự làm khó bằng optional view

Để kiểm tra file thường, size và lastModifiedTime, `Files.readAttributes(path, BasicFileAttributes.class)` là lựa chọn hợp lý và portable hơn cố gọi POSIX/DOS chỉ để lấy dữ liệu mà basic đã có. Tránh phụ thuộc view chuyên biệt khi nhu cầu không đòi hỏi.

## 11. LinkOption.NOFOLLOW_LINKS và symbolic links

Nếu Path là symbolic link, câu hỏi “metadata của cái gì?” phải được xác định:

- **Theo link (mặc định):** đọc thuộc tính của **đích** mà symlink trỏ tới.
- **Không theo link:** dùng `LinkOption.NOFOLLOW_LINKS` để yêu cầu đọc metadata của **chính link entry**.

```java
BasicFileAttributes targetAttrs =
        Files.readAttributes(path, BasicFileAttributes.class);

BasicFileAttributes linkAttrs =
        Files.readAttributes(path, BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet trong phương thức với `Path path` và imports `Files`, `LinkOption`, `BasicFileAttributes`, có xử lý IOException. Nếu Path không là symlink, hai kết quả có thể giống nhau; nếu là symlink, loại, size hoặc timestamp có thể khác.

**Không suy rằng NOFOLLOW_LINKS luôn được mọi provider thực hiện giống nhau**: một số provider không hỗ trợ symbolic links và bỏ qua option này. Ngoài ra, file system có thể thay đổi giữa lúc đọc attributes và lúc mở file thật (*time-of-check/time-of-use race*). NOFOLLOW_LINKS chỉ giải quyết phần **theo hay không theo link** của thao tác cụ thể, không phải sandbox bảo mật tổng quát.

## 12. Lựa chọn kiểm tra theo FileSystem, FileStore và từng Path

### 12.1. FileSystem-level capability — khi nào đủ?

Nếu làm feature discovery một lần, ví dụ UI có nút “Xem POSIX permissions” hay không, `fs.supportedFileAttributeViews()` cho tín hiệu ban đầu. Nhưng nếu ứng dụng thao tác trên nhiều mount, hãy xem nơi thực sự lưu Path vì filesystem có thể gồm nhiều FileStore.

### 12.2. FileStore-level capability — khi nào cần?

Khi bắt đầu thao tác file cụ thể trên một volume, `Files.getFileStore(path)` rồi `supportsFileAttributeView` giúp chọn đường xử lý chính xác hơn. Tuy nhiên, không coi FileStore status là cache vĩnh viễn khi mount, network share hoặc môi trường thực thi thay đổi.

### 12.3. Path-level view — dùng ngay trước I/O

Với thao tác thực, `Files.getFileAttributeView(path, View.class)` giúp lấy typed view hoặc null. Sau đó đọc/ghi metadata, xử lý IOException và lỗi khác phù hợp. Đây là bước quan trọng nhất để tránh dereference view không tồn tại.

### 12.4. Trình tự tham khảo

```text
Có cần metadata chỉ thuộc "basic"?
  ├─ Có → Files.readAttributes(path, BasicFileAttributes.class)
  │        └─ Xử lý IOException.
  └─ Không → Chọn view chuyên biệt thực sự cần.
             │
             ├─ Xem FileSystem.supportedFileAttributeViews()
             ├─ Nếu cần: Files.getFileStore(path)
             │          .supportsFileAttributeView(ViewType.class)
             ├─ Files.getFileAttributeView(path, ViewType.class)
             │    ├─ null → nhánh "không hỗ trợ"
             │    └─ view → readAttributes()/getAcl()/list()...
             │                 ├─ thành công → xử lý metadata
             │                 └─ IOException → xử lý lỗi I/O
             └─ Nếu tính năng là yêu cầu bảo mật bắt buộc:
                        không hỗ trợ → fail closed.
```

Đây là **cây lựa chọn khái niệm**, không phải một thuật toán chống mọi race. Trên remote provider, kết quả kiểm tra có thể kém tin cậy; ở mọi provider, file có thể đổi hoặc bị xóa giữa kiểm tra và thao tác.

## 13. Ngoại lệ và trạng thái nào cần phân biệt?

| Tình huống | Biểu hiện có thể gặp | Cách nghĩ đúng |
| --- | --- | --- |
| View optional không khả dụng | `Files.getFileAttributeView` trả `null` | Nhánh không hỗ trợ, không gọi method trên null |
| Typed `Files.readAttributes` với view không có | `UnsupportedOperationException` | Không suy đó là lỗi permission; kiểm tra khả năng/thiết kế fallback |
| Tên view/attribute dynamic không hợp lệ | `IllegalArgumentException` hoặc `UnsupportedOperationException` tùy API | Sửa tên/schema hoặc kiểm tra provider |
| File không tồn tại tại lúc truy cập | `NoSuchFileException` hoặc IOException tương ứng | Có thể race; không gộp thành unsupported |
| Không có quyền đọc metadata | `AccessDeniedException`/`IOException` hoặc security failure tùy môi trường | Phân biệt lỗi quyền với unsupported |
| FileStore remote trả capability chưa chính xác | Probe có thể không phản ánh kết quả thao tác thật | Thực hiện I/O có xử lý lỗi |
| File là symlink | Có thể theo link hoặc đọc chính link tùy `LinkOption` | Chọn policy trước khi đọc |
| Provider hỗ trợ view nhưng chỉ đọc được | Các setter có thể thất bại | Capability khác quyền sửa |
| Metadata thiếu/không được lưu thật | Giá trị mô phỏng, độ chính xác thấp, `fileKey` null... | Không gán ý nghĩa mạnh hơn đặc tả |

### 13.1. Không bắt `NullPointerException` để đoán view thiếu

Sai:

```java
PosixFileAttributeView posix =
        Files.getFileAttributeView(path, PosixFileAttributeView.class);
posix.readAttributes(); // Có thể NullPointerException.
```

Đây là snippet minh họa **cách viết lỗi**. Thay bằng `if (posix != null)` rồi đọc trong cơ chế xử lý IOException phù hợp. Bắt NullPointerException để “cho qua” có thể che bug khác.

### 13.2. Không nuốt mọi IOException thành “không hỗ trợ”

Sai:

```java
try {
    return Files.readAttributes(path, PosixFileAttributes.class);
} catch (Exception ignored) {
    return null;
}
```

Đây là **mẫu anti-pattern** minh họa trong một phương thức có `Path path`; không phải code khuyên dùng. Nó đánh đồng provider không hỗ trợ với permission denied, file bị xóa, lỗi ổ đĩa và bug logic.

Tốt hơn: kiểm tra capability/null khi cần; ném hoặc ghi nhận IOException thực, và chỉ có fallback khi hợp đồng nghiệp vụ cho phép.

## 14. Đừng coi kiểm tra hỗ trợ là kiểm tra quyền truy cập

`supportsFileAttributeView` nói về **khả năng lưu trữ thuộc tính**, không phải “caller được phép đọc/ghi mọi thuộc tính”. Ví dụ:

- POSIX view được hỗ trợ nhưng process không có quyền thay owner/group.
- ACL view có nhưng người gọi không có quyền sửa ACL.
- File store không read-only nhưng thư mục/tệp lại có ACL giới hạn thao tác.
- Người dùng có thể đọc basic attributes nhưng không có quyền đọc user-defined attributes nhạy cảm.
- Provider cho biết view nhưng dữ liệu nằm trên network share tạm thời không truy cập được.

Vì thế, đừng viết:

```java
if (store.supportsFileAttributeView(PosixFileAttributeView.class)) {
    // Không có nghĩa chắc được setPermissions.
}
```

Nếu nhiệm vụ liên quan tới **bảo mật dữ liệu**, cần xác thực authorization và xử lý thất bại ngay tại thao tác; nếu metadata bắt buộc không đặt được, không được mặc nhiên lưu dữ liệu với quyền rộng hơn.

### 14.1. FileStore.isReadOnly() cũng không thay cho thử thao tác

`store.isReadOnly()` cho biết file store được công bố là chỉ đọc hay không. Nếu true, không thể kỳ vọng sửa dữ liệu; nếu false, vẫn có thể không đủ quyền ở file cụ thể. Với security-sensitive workflows, quyền truy cập phải được kiểm soát trong thiết kế và xử lý lỗi tại I/O thật.

## 15. Provider khác nhau: Windows, Linux, macOS, ZIP và mạng

NIO.2 cho phép làm việc với nhiều loại `FileSystemProvider`. Cùng một API Java nhưng capability không đồng nhất:

- **Windows default filesystem:** có thể công bố `dos` và `acl`; không nên đòi POSIX permissions nếu provider không có.
- **Linux/macOS với filesystem hỗ trợ POSIX:** thường công bố `posix`, nhưng volume/mount đặc biệt có thể khác.
- **ZIP filesystem (`jdk.zipfs`):** view/metadata chỉ theo khả năng ZIP provider; không giả định quyền POSIX/ACL giống file trên ổ đĩa thật.
- **Network share/remote filesystem:** khả năng đọc hoặc cập nhật metadata có thể bị hạn chế; FileStore probe không luôn cho kết quả chính xác như local device.
- **Provider tùy biến:** có thể định nghĩa tên view khác, dữ liệu thuộc tính mở rộng hoặc chỉ hỗ trợ tập metadata rất nhỏ.

Do đó, **không dùng tên OS như một boolean thay thế probe**. Khi ứng dụng thực sự phải chạy trên nhiều provider, test với **filesystem đích** và dữ liệu/permission thực tế.

### 15.1. Không tạo Path mới rồi giả định cùng provider

Một `Path` đã có `getFileSystem()` của riêng nó. Nếu ứng dụng nhận `Path` từ ZIP/provider khác, dùng chính Path đó với `Files.getFileAttributeView` và `Files.getFileStore`; đừng chuyển `path.toString()` rồi gọi `Path.of(...)`, vì cách sau thường đưa về **default provider**, làm mất ý nghĩa filesystem gốc.

### 15.2. Có thể cache kết quả support không?

Kết quả ở cấp filesystem/store đôi khi được cache để tránh probe lặp lại. Nhưng phải cân nhắc:

- FileStore khác có capability khác.
- Mount/connection/provider có thể thay đổi theo vòng đời ứng dụng.
- Remote filesystem có thể phản ánh thông tin không chính xác.
- Các lỗi permission và I/O vẫn phải được xử lý tại từng thao tác.

**Cache là tối ưu hóa, không thay thế xử lý lỗi.** Không giữ cached boolean `posixSupported=true` rồi bỏ mọi null/exception check trong suốt vòng đời service.

## 16. Kiểm thử khả năng tương thích giữa các môi trường

Không nên viết unit test như:

```java
assertTrue(path.getFileSystem()
        .supportedFileAttributeViews().contains("posix"));
```

Đó là **snippet minh họa một giả định không portable**. Nó có thể đúng trên máy dev nhưng sai trên Windows hoặc provider khác. Nếu test nhằm xác nhận một tính năng POSIX-specific, cần **assumption/skip** khi capability không có, đồng thời phải có integration test thực trên filesystem yêu cầu hỗ trợ.

Một số cách kiểm thử tốt:

1. **Test cơ bản trên mọi hệ thống:** `"basic"` có sẵn, `BasicFileAttributeView` không null, file vừa tạo có size đúng.
2. **Test POSIX/DOS có điều kiện:** nếu FileSystem, FileStore và typed view hỗ trợ thì đọc; nếu không, xác nhận ứng dụng chuyển sang nhánh fallback đã định.
3. **Test lỗi permissions:** chạy bằng user/quyền phù hợp để chắc code không biến lỗi quyền thành “unsupported”.
4. **Test `NOFOLLOW_LINKS`:** nếu provider có symbolic links, thử link tới file và so sánh semantics; không bắt buộc trên provider không có symlink.
5. **Test đường dẫn không tồn tại:** nếu check FileStore/readAttributes ném IOException, code phải báo lỗi rõ.
6. **Test provider khác:** ZIP FileSystem nếu sản phẩm sử dụng nó; đảm bảo không mặc định POSIX/ACL.
7. **Test metadata mutation riêng:** chỉ trên file tạm và có cleanup, tuyệt đối không thay owner/permissions file thật của người dùng trong unit test.
8. **Test behavior phụ thuộc môi trường mà không hard-code output:** thông tin POSIX/DOS có thể khác; assert quy tắc xử lý hơn là một giá trị cố định trên mọi OS.

### 16.1. Tách “unsupported” với “cannot read”

Một bài kiểm thử có giá trị là verify ứng dụng báo riêng:

- `UNSUPPORTED` khi view không có (null hoặc capability không được công bố).
- `IO_FAILURE` khi view có nhưng không đọc được do I/O.
- `SUCCESS` khi attributes được đọc đúng.

Tại tầng domain, có thể dùng một kiểu kết quả có ba trạng thái thay vì trả `null` cho mọi lỗi; điều đó giúp vận hành dễ chẩn đoán hơn.

## 17. Hiệu năng và tính nhất quán khi đọc metadata

Mỗi lệnh `Files.getFileStore` hoặc `view.readAttributes()` có thể truy cập OS/provider và tạo I/O. Nếu duyệt hàng trăm nghìn Path, không nhất thiết gọi cả ba tầng probe và đọc nhiều lần trên từng entry.

- **Chỉ dùng basic** khi yêu cầu đủ chung.
- **Đọc theo bulk** nếu có thể, chẳng hạn `Files.readAttributes(path, BasicFileAttributes.class)` hoặc `view.readAttributes()`.
- Khi duyệt cây, `Files.walkFileTree`/`Files.find` có thể cung cấp basic attributes trong callback/matcher, tránh phải đọc lại vô ích; vẫn phải hiểu thời điểm lấy dữ liệu và policy symlink.
- Chỉ dùng optional view nơi thật sự cần.
- Nếu cache view capability, xem xét phạm vi FileSystem/FileStore và khả năng thay đổi môi trường.
- Không giả định snapshot attribute là nguyên tử với mọi thao tác filesystem: Javadoc cho phép một số thuộc tính được đọc theo cách implementation-specific về tính atomicity.

**Quan trọng:** Một lần đọc metadata và một lần mở tệp là **hai thao tác riêng**. Người dùng hoặc tiến trình khác có thể thay file, sửa quyền, đổi symlink giữa các thời điểm; đọc được metadata không khóa file.

## 18. Những lỗi thường gặp

**Lỗi 1 — Giả định POSIX view có mặt vì đang chạy trên Linux.** Không đủ. Kiểm tra provider/file store/path.

**Lỗi 2 — Giả định DOS view có mặt vì đang chạy trên Windows.** Không đủ. Filesystem và provider cụ thể mới quyết định.

**Lỗi 3 — Chỉ kiểm tra `FileSystem.supportedFileAttributeViews()` rồi dùng cho mọi mount.** Một FileSystem có thể gồm nhiều FileStore có khả năng khác nhau.

**Lỗi 4 — Không kiểm tra null của `Files.getFileAttributeView(...)`.** Optional view có thể null; dereference sẽ lỗi.

**Lỗi 5 — Nghĩ hỗ trợ view nghĩa là có quyền đọc/ghi metadata.** Capability khác authorization; I/O vẫn có thể thất bại.

**Lỗi 6 — Gọi `Files.readAttributes(path, PosixFileAttributes.class)` vô điều kiện trong code portable.** View không có có thể gây `UnsupportedOperationException`.

**Lỗi 7 — Bắt mọi Exception rồi bỏ qua.** Che lỗi thiếu quyền, file biến mất hoặc bug logic.

**Lỗi 8 — Nghĩ `Files.getFileStore(path)` không bao giờ cần file tồn tại.** Đây là thao tác có thể truy cập filesystem và ném IOException.

**Lỗi 9 — Coi `FileStore.supportsFileAttributeView` luôn chính xác trên network store.** Javadoc nêu giới hạn của default provider với nonlocal storage.

**Lỗi 10 — Nhầm `FileStoreAttributeView` với `FileAttributeView`.** Hai API hướng tới metadata **của store** và **của từng file**, không thay thế nhau.

**Lỗi 11 — Xem `basic` như một view tùy chọn.** Java NIO đòi hỗ trợ basic; nhưng đọc basic vẫn có thể lỗi I/O.

**Lỗi 12 — Nghĩ timestamp/fileKey luôn đầy đủ chính xác.** Provider có thể mô phỏng hoặc không cung cấp mọi thuộc tính optional; cần theo hợp đồng.

**Lỗi 13 — Dùng `NOFOLLOW_LINKS` rồi cho rằng không có symlink race.** Chính sách link tại một lần đọc không khóa filesystem.

**Lỗi 14 — Coi cờ `dos:readonly` là quyền bảo mật tương đương ACL.** Chúng là các mô hình metadata khác nhau.

**Lỗi 15 — Bắt `NullPointerException` để xử lý unsupported view.** Hãy kiểm tra null rõ ràng để tránh che bug.

**Lỗi 16 — Hard-code danh sách view names là bất biến giữa các provider.** Có thể có view đặc thù ngoài tên chuẩn.

**Lỗi 17 — Dùng String `path.toString()` rồi dựng lại default Path.** Có thể đổi provider từ ZIP/remote sang local, kiểm tra nhầm nơi.

**Lỗi 18 — Chuyển một yêu cầu quyền bắt buộc thành fallback im lặng.** Nếu security policy không thể áp dụng, không được tạo dữ liệu trong trạng thái ít an toàn hơn chỉ để tiếp tục.

**Lỗi 19 — Viết unit test sửa ACL trên file thật của môi trường.** Dễ phá quyền và không portable; dùng file tạm, cleanup, kiểm tra support và quyền.

**Lỗi 20 — Cache capability một lần rồi bỏ exception handling.** Filesystem, mount, quyền, file và trạng thái mạng có thể thay đổi.

## 19. Checklist code review

- [ ] **Metadata thật sự cần** có thuộc nhóm basic không, hay đòi POSIX/DOS/ACL/owner/user?
- [ ] Có tránh suy đoán support bằng tên OS/volume thông thường?
- [ ] Nếu cần feature discovery, có hỏi `FileSystem.supportedFileAttributeViews()` và hiểu đó là danh sách tên?
- [ ] Nếu thao tác trên Path cụ thể, có xét `FileStore.supportsFileAttributeView(...)` khi phù hợp?
- [ ] Có biết `Files.getFileStore(path)` có thể ném IOException và cần path thực tế?
- [ ] Với optional typed view, có **kiểm tra null** trước khi gọi `readAttributes`/setter?
- [ ] Có xử lý IOException ở bước đọc/ghi thật dù capability probe thành công?
- [ ] Có phân biệt unsupported với permission denied/file missing/provider I/O error?
- [ ] Nếu yêu cầu quyền bắt buộc, có **fail closed** khi không thực hiện được?
- [ ] Nếu chỉ đọc size/time/type, có dùng basic view để giảm phụ thuộc platform?
- [ ] Có chọn chính sách `NOFOLLOW_LINKS` đúng mục đích và đánh giá TOCTOU?
- [ ] Có tránh đọc/ghi owner, ACL hoặc extended attributes khi không cần?
- [ ] Có nhận ra FileStore nonlocal và provider khác có giới hạn capability probe?
- [ ] Có xử lý cú pháp dynamic `"view-name:attribute-name"` với schema rõ, không để input tùy ý?
- [ ] Có test trên Windows/Linux/macOS/file system đích thay vì hard-code `posix=true`?
- [ ] Nếu dùng ZIP/custom provider, có đảm bảo Path giữ đúng FileSystem?
- [ ] Có đo chi phí stat/readAttributes khi duyệt nhiều tệp?
- [ ] Có tránh cache capability như một sự thật bất biến và giữ kiểm tra lỗi khi I/O?
- [ ] Có test trường hợp tệp biến mất, symlink thay đổi, quyền bị từ chối?
- [ ] Khi log thông tin owner/ACL, có giới hạn lộ dữ liệu nhạy cảm?

## 20. Câu hỏi tự kiểm tra

**1.** `FileSystem.supportedFileAttributeViews()` trả kiểu gì? — **`Set<String>`** gồm tên các view được filesystem công bố; luôn chứa `"basic"`.

**2.** `FileStore.supportsFileAttributeView(...)` có mấy overload chính? — Nhận **`Class<? extends FileAttributeView>`** hoặc **tên view String**.

**3.** Vì sao cần kiểm tra ở FileStore dù FileSystem báo có view? — Một filesystem có thể gồm nhiều store với capability khác nhau.

**4.** `Files.getFileAttributeView(path, PosixFileAttributeView.class)` có thể trả gì khi provider không có POSIX? — **`null`**.

**5.** `Files.getFileAttributeView(path, BasicFileAttributeView.class)` có bắt buộc khác null không? — **Có** theo hợp đồng Java NIO.

**6.** Basic view luôn có đồng nghĩa `readAttributes()` luôn thành công? — **Không**; I/O, quyền hoặc file biến mất có thể gây lỗi.

**7.** Nếu chỉ cần size và lastModifiedTime, dùng view nào portable nhất? — **BasicFileAttributes/BasicFileAttributeView**.

**8.** Chạy trên Windows thì có thể giả định luôn có ACL view không? — **Không**, còn phụ thuộc file store/provider.

**9.** Muốn đọc quyền POSIX, nên làm gì trước? — Kiểm tra support và typed view không null, sau đó đọc với xử lý IOException.

**10.** Trường hợp view hỗ trợ nhưng không có quyền đọc, nên coi là “unsupported” không? — **Không**; đây là lỗi truy cập/I/O khác.

**11.** `LinkOption.NOFOLLOW_LINKS` có ý nghĩa gì? — Yêu cầu đọc metadata của chính symlink entry thay vì theo tới target khi provider hỗ trợ.

**12.** `NOFOLLOW_LINKS` có khóa entry để không bị thay thế sau kiểm tra? — **Không**, vẫn có TOCTOU race.

**13.** `Files.readAttributes(path, PosixFileAttributes.class)` khi POSIX không hỗ trợ có thể ném gì? — **`UnsupportedOperationException`**.

**14.** `FileStore.supportsFileAttributeView` có hoàn toàn chính xác với file store remote không? — Javadoc không bảo đảm kết quả chính xác cho một số nonlocal store với default provider.

**15.** Cờ DOS read-only có tương đương danh sách ACL không? — **Không**, mô hình metadata khác nhau.

**16.** `FileOwnerAttributeView` dùng làm gì? — Truy cập thông tin **owner** của file nếu provider hỗ trợ.

**17.** `UserDefinedFileAttributeView` dùng cho gì? — Metadata mở rộng theo cặp tên/giá trị bytes nếu filesystem hỗ trợ.

**18.** Có nên cố ghi POSIX permissions rồi silently skip nếu unsupported trong workflow bảo mật bắt buộc không? — **Không**, phải báo lỗi hoặc dùng cơ chế bảo mật thích hợp đã thiết kế.

**19.** Vì sao test portable không nên assert `posix=true` mọi máy? — Vì support phụ thuộc provider/volume, không phải một thuộc tính chung của mọi JVM.

**20.** Có nên tự thay `Path` bằng String rồi dựng lại để hỏi view trên ZIP filesystem không? — **Không**, dễ mất provider gốc và hỏi nhầm local file system.

## Tài liệu chính thức (Java SE 17, kiến thức còn áp dụng)

- [Java SE 17 — FileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttributeView.html): khái niệm typed view của file.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `supportedFileAttributeViews()` và quan hệ filesystem/stores.
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView(Class/String)` và giới hạn nonlocal storage.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `getFileStore`, `getFileAttributeView`, typed/dynamic `readAttributes`, `getAttribute` và `setAttribute`.
- [Java SE 17 — BasicFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html): basic metadata và `readAttributes()`.
- [Java SE 17 — PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): owner/group/permissions trên provider có POSIX.
- [Java SE 17 — DosFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributeView.html): cờ DOS khi provider hỗ trợ.
- [Java SE 17 — AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): đọc/cập nhật ACL khi available.
- [Java SE 17 — UserDefinedFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/UserDefinedFileAttributeView.html): extended attributes theo cặp tên/byte.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): chính sách không theo symbolic link.

**Ghi nhớ:** Trước khi dùng một attribute view tùy chọn, hãy hỏi **FileSystem công bố những view nào**, **FileStore của Path có hỗ trợ không**, và **typed view của chính Path có khác null không**. Với `basic`, Java đảm bảo hỗ trợ; với `posix`, `dos`, `acl`, `owner`, `user` phải kiểm tra theo provider. Dù probe báo có hỗ trợ, **quyền truy cập, thay đổi filesystem và lỗi I/O vẫn phải được xử lý ở thao tác thật**. Nếu metadata là yêu cầu bảo mật bắt buộc, không âm thầm bỏ qua khi không hỗ trợ.