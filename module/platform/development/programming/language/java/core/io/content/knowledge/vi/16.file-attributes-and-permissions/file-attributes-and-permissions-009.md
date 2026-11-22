# Thiết lập thuộc tính khi tạo tệp trong Java NIO.2

## 1. Vấn đề: không chỉ tạo được tệp, mà cần tạo với thuộc tính đúng

Khi ứng dụng ghi cấu hình, khóa riêng, báo cáo, tệp tạm hoặc dữ liệu của người dùng, câu hỏi không chỉ là “tạo tệp thành công chưa?” mà còn là **tệp mới có quyền truy cập, chủ sở hữu và những thuộc tính cần thiết hay chưa?**

Java NIO.2 hỗ trợ truyền các **thuộc tính ban đầu** (*initial file attributes*) vào một số phương thức tạo tệp và thư mục. Ví dụ, trên hệ thống tệp hỗ trợ quyền POSIX, ta có thể yêu cầu tạo một tệp chỉ cho **chủ sở hữu** đọc và ghi:

~~~java
Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-------");

FileAttribute<Set<PosixFilePermission>> attrs =
        PosixFilePermissions.asFileAttribute(permissions);

Files.createFile(path, attrs);
~~~

Đây là **đoạn mã minh họa**: biến `path` là một `Path` chưa tồn tại, và cần các import từ `java.nio.file`, `java.nio.file.attribute`, `java.util.Set`. Lệnh có thể ném `IOException` hoặc `UnsupportedOperationException` tùy hệ thống tệp. Chương trình độc lập và cách kiểm tra hỗ trợ nằm ở các phần bên dưới.

**Ý tưởng cốt lõi:** yêu cầu thuộc tính **ngay trong thao tác tạo** thường tránh được “khoảng thời gian tệp tồn tại với quyền mặc định rồi mới được sửa”, nếu provider hỗ trợ thuộc tính đó tại thời điểm tạo. Đây là vấn đề đặc biệt quan trọng với thông tin nhạy cảm. Tuy nhiên, không phải mọi provider chấp nhận mọi thuộc tính, và hệ điều hành/file system vẫn có chính sách riêng về quyền hiệu lực.

Bài này tập trung vào **thiết lập thuộc tính khi tạo tệp** với `Files` của Java 17. Bạn sẽ học:

1. Phân biệt **thuộc tính ban đầu**, **tùy chọn mở tệp** và **thuộc tính thay đổi sau khi tạo**.
2. Dùng `FileAttribute<?>` với `Files.createFile`, `Files.createDirectory`, `Files.createTempFile` và `Files.newByteChannel`.
3. Tạo yêu cầu quyền **POSIX** bằng `PosixFilePermissions.fromString` và `asFileAttribute`.
4. Hiểu phạm vi hỗ trợ của provider, Windows/POSIX và giới hạn của việc tự đặt `chmod` sau khi tạo.
5. Kiểm tra kết quả, xử lý lỗi và giữ an toàn khi tạo tệp không được phép ghi đè.
6. Áp dụng Java 17 qua các ví dụ có thể biên dịch, chạy và đối chiếu đầu ra.

## 2. File attributes, permissions và open options là những khái niệm khác nhau

Hệ thống tệp có thể lưu những loại thông tin về một entry như:

- **Tên, loại và kích thước:** tệp thường, thư mục, symbolic link; số byte; thông tin cơ bản.
- **Dấu thời gian:** thời điểm tạo, sửa, truy cập (khả năng và độ chính xác tùy provider).
- **Quyền truy cập POSIX:** các bit đọc/ghi/thực thi cho chủ sở hữu, nhóm và đối tượng khác.
- **Chủ sở hữu/nhóm:** thông tin người dùng và nhóm gắn với entry, nếu hệ thống tệp hỗ trợ.
- **ACL:** danh sách kiểm soát truy cập chi tiết trên một số filesystem.
- **Thuộc tính DOS:** ví dụ hidden, read-only, system, archive khi provider hỗ trợ.
- **Thuộc tính do provider định nghĩa:** không có bảo đảm sử dụng được trên mọi hệ thống.

Ba nhóm tham số rất dễ bị nhầm:

| Loại | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| `FileAttribute<?>` ban đầu | `PosixFilePermissions.asFileAttribute(...)` | *Tạo mới với thuộc tính nào?* |
| `OpenOption` | `CREATE_NEW`, `WRITE`, `APPEND` | *Mở/tạo tệp bằng chế độ nào?* |
| Phương thức đặt thuộc tính sau tạo | `Files.setPosixFilePermissions`, `Files.setAttribute`, `Files.setOwner` | *Thay đổi thuộc tính entry đã tồn tại ra sao?* |

Không dùng `StandardOpenOption.CREATE_NEW` để thể hiện “chỉ cho owner đọc”. Nó quyết định điều kiện tạo/mở, **không phải một bộ quyền**. Tương tự, `PosixFilePermissions.asFileAttribute` không tự quyết định ghi đè hay append.

### 2.1. Thuộc tính ban đầu không có nghĩa mọi metadata đều đặt được

Mỗi `FileAttribute<T>` có **tên** thuộc tính và **giá trị**. Java có nhiều `FileAttributeView` để đọc/ghi metadata, nhưng **không có bảo đảm mọi thuộc tính đọc/ghi được đều có thể truyền vào lúc tạo**.

Ví dụ, một filesystem có thể cho phép sửa thời gian truy cập **sau** khi tệp đã có, nhưng không hỗ trợ thiết lập thời gian đó như initial attribute trong `Files.createFile`. Với thuộc tính không hỗ trợ khi tạo, provider có thể ném `UnsupportedOperationException`.

Hãy đọc hợp đồng phương thức tạo và thử trên provider thật thay vì phỏng đoán từ việc một attribute view tồn tại.

## 3. Những API nhận FileAttribute<?> lúc tạo

Các phương thức sau có tham số cuối `FileAttribute<?>... attrs`:

| Phương thức | Tác dụng | Điểm lưu ý về attrs |
| --- | --- | --- |
| `Files.createFile(path, attrs)` | Tạo tệp mới; không ghi đè tệp đã tồn tại | Áp dụng các thuộc tính được hỗ trợ ngay lúc tạo |
| `Files.createDirectory(path, attrs)` | Tạo một thư mục mới; thư mục cha phải tồn tại | Có thể yêu cầu quyền ban đầu của thư mục |
| `Files.createDirectories(path, attrs)` | Tạo các thư mục cha cần thiết | Thuộc tính áp dụng cho những thư mục **được tạo mới**; thư mục hiện hữu không được đặt lại |
| `Files.createTempFile(dir, prefix, suffix, attrs)` | Tạo tệp tạm mới trong thư mục chỉ định | Có thể yêu cầu thuộc tính ban đầu |
| `Files.createTempDirectory(dir, prefix, attrs)` | Tạo thư mục tạm mới | Phù hợp làm thư mục riêng cho dữ liệu nhạy cảm |
| `Files.newByteChannel(path, options, attrs)` | Mở kênh byte, có thể tạo tệp | Thuộc tính ban đầu chỉ có ý nghĩa **khi tệp được tạo mới** |
| `Files.createSymbolicLink(link, target, attrs)` | Tạo liên kết tượng trưng nếu được hỗ trợ | Nhiều provider không hỗ trợ initial attrs cho symbolic link; không suy ra quyền đích |

`Files.createFile` và `Files.createDirectory` cung cấp API trực tiếp cho mục tiêu “tạo entry mới với thuộc tính”. Nếu cần mở và ghi ngay trong một lần thao tác, `Files.newByteChannel` là lựa chọn đáng xem xét khi bạn cần cung cấp `FileAttribute<?>...` cùng các `OpenOption`.

Không phải mọi phương thức ghi của `Files` đều có tham số thuộc tính ban đầu. Đặc biệt, overload `Files.newOutputStream(path, options...)` nhận **OpenOption**, không có varargs `FileAttribute<?>`. Nếu cần áp dụng initial attributes mà chỉ dùng `newOutputStream`, không thể mặc định truyền thêm `FileAttribute` vào overload không tồn tại.

## 4. FileAttribute<?> là gì?

`java.nio.file.attribute.FileAttribute<T>` là interface mô tả một thuộc tính:

~~~java
public interface FileAttribute<T> {
    String name();
    T value();
}
~~~

Đây là **chữ ký API minh họa** (không cần tạo lại interface trong ứng dụng). Tên thường có dạng `view-name:attribute-name`, ví dụ `"posix:permissions"`. Giá trị thuộc tính tương ứng là một kiểu Java được hợp đồng đó định nghĩa.

Với quyền POSIX, Java cung cấp helper tạo `FileAttribute<Set<PosixFilePermission>>`:

~~~java
Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-------");
FileAttribute<Set<PosixFilePermission>> initial =
        PosixFilePermissions.asFileAttribute(permissions);
~~~

Đây là đoạn minh họa, với import:

~~~java
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;
~~~

Phần lớn bài toán thông dụng không cần tự viết implementation của `FileAttribute`; dùng helper chính thức sẽ rõ nghĩa và giảm lỗi tên/kiểu attribute.

### 4.1. Tham số varargs có nghĩa gì?

Một chữ ký như:

~~~java
Files.createFile(Path path, FileAttribute<?>... attrs)
~~~

cho phép truyền **không có**, **một** hoặc **nhiều** thuộc tính ban đầu (nếu hợp lệ và provider hỗ trợ). Về cú pháp:

~~~java
Files.createFile(path);                 // Không yêu cầu attrs tường minh.
Files.createFile(path, permissionsAttr); // Một thuộc tính ban đầu.
~~~

Đây là đoạn minh họa với `permissionsAttr` và `path` đã có. Tên thuộc tính có thể bị trùng khi cung cấp nhiều lần; theo hợp đồng các phương thức `Files`, nếu một tên xuất hiện nhiều lần thì thường chỉ giá trị của **lần xuất hiện cuối** được sử dụng. Tuy nhiên, việc cung cấp trùng thuộc tính là lỗi thiết kế dễ nhầm; tốt hơn hãy chỉ truyền một giá trị cuối được xác định rõ ràng.

Đừng thêm thuộc tính tùy ý mà không kiểm tra sự hỗ trợ: phần còn lại có thể hoàn toàn hợp lệ nhưng **một thuộc tính không được hỗ trợ** khiến lời gọi tạo tệp thất bại.

## 5. Quyền POSIX: ba nhóm và ba hành động

Trên filesystem hỗ trợ quyền POSIX, mode thường được biểu diễn thành 9 ký tự:

~~~text
rwxrwxrwx
│││││││││
││││││└┴┴─ Other: read/write/execute
│││└┴┴──── Group: read/write/execute
└┴┴─────── Owner: read/write/execute
~~~

Các vị trí tương ứng quyền:

| Nhóm | Read | Write | Execute |
| --- | --- | --- | --- |
| Owner | `OWNER_READ` | `OWNER_WRITE` | `OWNER_EXECUTE` |
| Group | `GROUP_READ` | `GROUP_WRITE` | `GROUP_EXECUTE` |
| Others | `OTHERS_READ` | `OTHERS_WRITE` | `OTHERS_EXECUTE` |

Trong Java, từng quyền là một giá trị enum `PosixFilePermission`. `Set<PosixFilePermission>` lưu bộ quyền đã chọn, không có thứ tự quan trọng.

Ví dụ ký hiệu:

| Chuỗi mode | Ý nghĩa | Trường hợp |
| --- | --- | --- |
| `rw-------` | Owner đọc/ghi; group và others không có bit nào | File bí mật hoặc dữ liệu riêng |
| `r--------` | Chỉ owner đọc | Một file chỉ đọc sau tạo (cần xem khả năng ghi nội dung) |
| `rw-r-----` | Owner đọc/ghi, group đọc | Tệp chia sẻ trong nhóm được kiểm soát |
| `rw-r--r--` | Owner đọc/ghi, group/others đọc | Tệp công khai trên hệ thống phù hợp |
| `rwx------` | Owner đọc/ghi/traverse; nhóm khác không có | Thư mục riêng |
| `rwxr-x---` | Owner có đủ quyền; group đọc/traverse | Thư mục chia sẻ nhóm |

Quyền `x` trên **thư mục** liên quan khả năng **đi xuyên/traverse** đường dẫn; không hoàn toàn giống ý nghĩa chạy tệp thực thi. Một thư mục owner chỉ có `rw-------` mà không có `x` có thể khiến người dùng không truy cập được các entry bên trong theo mô hình POSIX. Vì vậy mode của tệp và thư mục không nên sao chép y hệt nhau chỉ vì muốn “riêng tư”.

### 5.1. fromString và toString

`PosixFilePermissions.fromString(String)` chuyển chuỗi 9 ký tự theo cú pháp POSIX thành `Set<PosixFilePermission>`. `toString(Set<PosixFilePermission>)` chuyển ngược thành chuỗi mode, hữu ích để in/kiểm tra một bộ quyền.

~~~java
Set<PosixFilePermission> p =
        PosixFilePermissions.fromString("rw-r-----");
System.out.println(PosixFilePermissions.toString(p));
~~~

Kết quả:

~~~text
rw-r-----
~~~

Đây là đoạn minh họa, cần đặt trong phương thức/lớp và import như trên. Nếu chuỗi mode không hợp lệ về độ dài hoặc ký tự, API ném `IllegalArgumentException`.

## 6. Tạo tệp mới với quyền ban đầu

### 6.1. Ví dụ Java 17 độc lập: tạo file riêng tư

Tệp **CreatePrivateFileDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class CreatePrivateFileDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("private-file-demo-");
        Path file = dir.resolve("private.txt");

        try {
            Set<PosixFilePermission> mode =
                    PosixFilePermissions.fromString("rw-------");
            FileAttribute<Set<PosixFilePermission>> initial =
                    PosixFilePermissions.asFileAttribute(mode);

            // Ví dụ này cần một provider hỗ trợ quyền POSIX.
            Files.createFile(file, initial);

            Files.writeString(file, "secret", StandardCharsets.UTF_8);

            Set<PosixFilePermission> actual =
                    Files.getPosixFilePermissions(file);
            System.out.println("Readable text: " +
                    Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("Requested mode: " +
                    PosixFilePermissions.toString(mode));
            System.out.println("Actual mode: " +
                    PosixFilePermissions.toString(actual));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 CreatePrivateFileDemo.java
java CreatePrivateFileDemo
~~~

Ví dụ đầu ra trên một POSIX filesystem chấp nhận đúng bộ quyền và không có chính sách làm giảm quyền:

~~~text
Readable text: secret
Requested mode: rw-------
Actual mode: rw-------
~~~

**Điều kiện thực thi:** Ví dụ này **không dành để chạy nguyên xi trên mọi Windows/provider**; nếu provider không hỗ trợ thuộc tính POSIX, thao tác có thể ném `UnsupportedOperationException`. Giá trị `Actual mode` phải được **đọc lại**, không mặc định bằng yêu cầu trên mọi filesystem. Các chính sách như umask, quyền kế thừa/ACL và provider có thể ảnh hưởng quyền hiệu lực.

Chúng ta không in tên đường dẫn tạm (được JVM chọn ngẫu nhiên), giúp phần output có thể dự đoán theo điều kiện đã nêu.

### 6.2. Tại sao tạo trước rồi set quyền không hoàn toàn tương đương?

Mẫu:

~~~java
Files.createFile(path);
Files.setPosixFilePermissions(
        path, PosixFilePermissions.fromString("rw-------"));
~~~

là đoạn minh họa có **hai thao tác filesystem riêng**. Giữa lần tạo và lần sửa quyền, tệp có thể đã tồn tại với quyền mặc định của provider, gây ra **cửa sổ thời gian** mà chính sách mong muốn chưa được áp dụng. Với dữ liệu nhạy cảm, đây có thể là vấn đề bảo mật.

Mẫu ưu tiên trên POSIX provider hỗ trợ:

~~~java
FileAttribute<Set<PosixFilePermission>> attrs =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rw-------"));
Files.createFile(path, attrs);
~~~

giúp yêu cầu thuộc tính **ngay khi tạo**; theo hợp đồng của `Files.createFile`, việc kiểm tra tệp chưa tồn tại và tạo tệp là thao tác nguyên tử đối với các hoạt động filesystem ảnh hưởng thư mục. Các thuộc tính ban đầu cũng được đặt nguyên tử khi tạo nếu provider hỗ trợ. Nhưng **đây không phải giao dịch nhiều bước cho mọi hành động tiếp theo**, cũng không đảm bảo nội dung được ghi bền vững trên ổ đĩa.

## 7. Đừng nhầm “quyền yêu cầu” và “quyền thật sự”

Có ít nhất ba khái niệm:

1. **Requested permissions**: `Set<PosixFilePermission>` mà chương trình yêu cầu.
2. **Observed mode bits**: bộ quyền trả về bởi `Files.getPosixFilePermissions(file)` sau khi tạo.
3. **Effective access**: ứng dụng/người dùng có thể làm gì trên thực tế, còn phụ thuộc nhóm hiệu lực, ACL, chính sách OS, thư mục cha và các yếu tố khác.

Trên một số POSIX hệ thống, **umask** và chính sách tạo của OS/filesystem có thể làm quyền quan sát được **hẹp hơn** hoặc khác kỳ vọng. Đừng khẳng định tuyệt đối rằng `Files.createFile(..., attrs)` luôn tạo đúng mọi bit được yêu cầu trong mọi môi trường. Hãy kiểm tra quyền thật nếu điều đó là một **hậu điều kiện bắt buộc**.

Với tệp bí mật, nếu không chứng minh được quyền hiệu lực phù hợp, ứng dụng nên **từ chối xử lý nội dung nhạy cảm** hoặc chọn cơ chế bảo vệ theo hệ thống, thay vì bỏ qua kiểm tra rồi ghi dữ liệu.

### 7.1. Kiểm tra quyền sau tạo

~~~java
Set<PosixFilePermission> actual =
        Files.getPosixFilePermissions(path);

Set<PosixFilePermission> expected =
        PosixFilePermissions.fromString("rw-------");

if (!actual.equals(expected)) {
    throw new IOException("File permissions do not match policy");
}
~~~

Đây là đoạn minh họa với `Path path`, các import cần thiết và môi trường POSIX. Việc so sánh chính xác mode là **chính sách ví dụ**, có thể quá chặt hoặc không đủ với ứng dụng khác. Nếu chỉ yêu cầu “không cho group/others”, kiểm tra rằng các bit tương ứng **không xuất hiện** có thể phù hợp hơn kiểm tra equality tuyệt đối.

Quyền mode không phải tất cả bảo đảm bảo mật. Một filesystem với ACL khác hoặc cơ chế sandbox riêng có thể cần thêm bước kiểm tra.

## 8. Tạo thư mục với quyền ban đầu

Đối với thư mục cần chứa dữ liệu riêng, yêu cầu phổ biến là `rwx------`: chỉ owner được đọc danh sách, tạo/xóa (tùy quyền parent) và traverse vào thư mục.

~~~java
Set<PosixFilePermission> privateDirMode =
        PosixFilePermissions.fromString("rwx------");

FileAttribute<Set<PosixFilePermission>> dirAttrs =
        PosixFilePermissions.asFileAttribute(privateDirMode);

Files.createDirectory(path, dirAttrs);
~~~

Đây là đoạn minh họa, cần `Path path` chưa tồn tại và provider hỗ trợ POSIX. `Files.createDirectory` tạo **một** thư mục; nó không tự tạo toàn bộ cha nếu chưa có.

Với chuỗi thư mục lồng nhau:

~~~java
Files.createDirectories(path, dirAttrs);
~~~

`Files.createDirectories` tạo những thư mục còn thiếu; thuộc tính ban đầu áp dụng cho **những thư mục thực sự được tạo**. Các thư mục đã tồn tại không được thay quyền chỉ vì xuất hiện trong đường dẫn. Mặt khác, việc tạo nhiều thư mục **không phải một giao dịch nguyên tử duy nhất**: nếu bước giữa thất bại, một số thư mục cha có thể đã được tạo.

Đây là khác biệt cần nhớ khi cấu hình bảo mật cho toàn bộ cây thư mục. Nếu có thư mục cha do bên khác sở hữu hoặc có quyền mở rộng, đặt quyền cho thư mục con không tự giải quyết mọi nguy cơ đường dẫn.

### 8.1. Ví dụ Java 17: tạo thư mục riêng POSIX có kiểm tra hỗ trợ

Lưu **CreatePrivateDirectoryDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class CreatePrivateDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path parent = Files.createTempDirectory("private-dir-parent-");
        Path child = parent.resolve("private");

        try {
            FileStore store = Files.getFileStore(parent);
            if (!store.supportsFileAttributeView("posix")) {
                System.out.println("POSIX unsupported");
                return;
            }

            Set<PosixFilePermission> p =
                    PosixFilePermissions.fromString("rwx------");
            FileAttribute<Set<PosixFilePermission>> attr =
                    PosixFilePermissions.asFileAttribute(p);

            Files.createDirectory(child, attr);

            Set<PosixFilePermission> actual =
                    Files.getPosixFilePermissions(child);
            System.out.println("Created: " + Files.isDirectory(child));
            System.out.println("Owner access: " +
                    (actual.contains(PosixFilePermission.OWNER_READ)
                     && actual.contains(PosixFilePermission.OWNER_WRITE)
                     && actual.contains(PosixFilePermission.OWNER_EXECUTE)));
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(parent);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreatePrivateDirectoryDemo.java
java CreatePrivateDirectoryDemo
~~~

Có hai loại kết quả có chủ đích:

~~~text
POSIX unsupported
~~~

hoặc, trên môi trường POSIX cho phép tạo thư mục với các quyền owner yêu cầu:

~~~text
Created: true
Owner access: true
~~~

Ví dụ **không tự động hạ chuẩn bảo mật**: nếu không có POSIX view, nó thông báo không hỗ trợ thay vì tạo thư mục dùng quyền không xác định rồi coi như tương đương. Ngay cả khi `FileStore.supportsFileAttributeView("posix")` trả true, thao tác tạo có thể thất bại vì quyền, cấu hình cụ thể hoặc thuộc tính ban đầu không được hỗ trợ; chương trình để ngoại lệ đi lên thay vì giả thành công.

## 9. Thuộc tính khi tạo tệp tạm

Tệp tạm không đồng nghĩa “tệp không quan trọng”. Tên ngẫu nhiên giúp tránh trùng, nhưng **không phải thay thế** cho việc bảo vệ quyền đọc/ghi. Nếu tệp tạm chứa token truy cập, dữ liệu y tế, bản xuất chưa công bố hoặc khóa, cần đặt chính sách bảo mật phù hợp.

NIO cung cấp các overload:

~~~java
Files.createTempFile(dir, "session-", ".tmp", attrs);
Files.createTempDirectory(dir, "private-", attrs);
~~~

Đây là đoạn minh họa với `Path dir` và `FileAttribute<?> attrs` đã có. API trả lại `Path` đến entry **được tạo thật**. Dữ liệu mới tạo khác với một chuỗi tên được dự đoán sẵn.

### 9.1. Ví dụ Java 17: tệp tạm với yêu cầu POSIX

Lưu **PrivateTempFileDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PrivateTempFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("temp-policy-root-");
        Path temp = null;

        try {
            FileStore store = Files.getFileStore(root);
            if (!store.supportsFileAttributeView("posix")) {
                System.out.println("POSIX unsupported");
                return;
            }

            FileAttribute<Set<PosixFilePermission>> attr =
                    PosixFilePermissions.asFileAttribute(
                            PosixFilePermissions.fromString("rw-------"));

            temp = Files.createTempFile(root, "private-", ".txt", attr);
            Files.writeString(temp, "one", StandardCharsets.UTF_8);

            System.out.println("Exists: " + Files.isRegularFile(temp));
            System.out.println("Contents: " +
                    Files.readString(temp, StandardCharsets.UTF_8));
        } finally {
            if (temp != null) {
                Files.deleteIfExists(temp);
            }
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateTempFileDemo.java
java PrivateTempFileDemo
~~~

Các kết quả mong đợi tùy provider:

~~~text
POSIX unsupported
~~~

hoặc khi provider POSIX hỗ trợ việc tạo:

~~~text
Exists: true
Contents: one
~~~

Chương trình không in tên tệp ngẫu nhiên. `Files.createTempFile` tự cấp một tên không trùng theo hợp đồng, thay vì ứng dụng tự ghép `System.currentTimeMillis()` rồi nghĩ rằng tên đó an toàn. Nếu tệp không được phép rò rỉ, trước khi ghi nội dung nhạy cảm vẫn nên kiểm tra hậu điều kiện và quản lý cleanup chắc chắn.

### 9.2. Một số default attributes có thể đã khác Files.createFile

Các overload tạo **tệp tạm** có thể sử dụng các thuộc tính mặc định khác khi không chỉ định attrs, tùy provider, ví dụ có xu hướng hạn chế hơn ở một số hệ thống. Nhưng không nên xây cam kết bảo mật trên phỏng đoán “temp luôn là private”: nếu có yêu cầu cụ thể, hãy **truyền thuộc tính phù hợp và xác minh** bằng API/platform hỗ trợ.

## 10. Mở và tạo ngay bằng Files.newByteChannel

`Files.newByteChannel(Path, Set<? extends OpenOption>, FileAttribute<?>... attrs)` cho phép vừa khai báo cách mở, vừa cung cấp thuộc tính khi tệp cần được tạo mới.

Một mẫu tạo tệp mới tuyệt đối không ghi đè:

~~~java
Set<OpenOption> options = Set.of(
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);

try (SeekableByteChannel channel =
        Files.newByteChannel(path, options, initialAttr)) {
    // Ghi các byte thông qua channel.
}
~~~

Đây là đoạn minh họa; cần `Path path`, `FileAttribute<?> initialAttr`, các import `java.nio.channels.SeekableByteChannel`, `java.nio.file.Files`, `java.nio.file.OpenOption`, `java.nio.file.StandardOpenOption`, `java.util.Set`. Tùy chọn `CREATE_NEW` yêu cầu tệp **chưa tồn tại**; việc kiểm tra trùng tên và tạo được gắn với cùng thao tác tạo theo hợp đồng. `WRITE` yêu cầu quyền ghi.

Nếu tệp **đã tồn tại**, `CREATE_NEW` làm thao tác thất bại; initial attrs không dùng để thay quyền của tệp cũ. Với `CREATE` và một tệp hiện hữu, `attrs` cũng không tự động cập nhật quyền hiện tại.

### 10.1. Ví dụ Java 17: tạo tệp và ghi byte với initial attributes

Lưu **CreateWithChannelDemo.java**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class CreateWithChannelDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("channel-create-");
        Path file = dir.resolve("entry.txt");

        try {
            FileStore store = Files.getFileStore(dir);
            if (!store.supportsFileAttributeView("posix")) {
                System.out.println("POSIX unsupported");
                return;
            }

            FileAttribute<Set<PosixFilePermission>> attr =
                    PosixFilePermissions.asFileAttribute(
                            PosixFilePermissions.fromString("rw-------"));

            Set<OpenOption> options =
                    Set.of(StandardOpenOption.CREATE_NEW,
                           StandardOpenOption.WRITE);

            try (SeekableByteChannel channel =
                         Files.newByteChannel(file, options, attr)) {
                ByteBuffer bytes = ByteBuffer.wrap(
                        "hello".getBytes(StandardCharsets.UTF_8));
                while (bytes.hasRemaining()) {
                    channel.write(bytes);
                }
            }

            System.out.println("Text: " +
                    Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("Bytes: " + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreateWithChannelDemo.java
java CreateWithChannelDemo
~~~

Kết quả khi provider POSIX đáp ứng yêu cầu:

~~~text
Text: hello
Bytes: 5
~~~

Hoặc:

~~~text
POSIX unsupported
~~~

**Tại sao có vòng `while (bytes.hasRemaining())`?** `SeekableByteChannel.write(ByteBuffer)` không nên bị giả định sẽ ghi toàn bộ lượng byte còn lại trong một lời gọi trên mọi triển khai. Lặp đến khi buffer hết giúp xử lý các lần ghi một phần, dù trong ứng dụng thực còn cần xem xét tình huống không tiến triển hay channel không chặn theo loại channel thực tế.

**Phân biệt với `Files.newOutputStream`:** overload stream nhận các open options nhưng không có đối số initial attributes. Khi cần truyền `FileAttribute<?>` cùng chế độ mở, `newByteChannel` là lựa chọn NIO trực tiếp.

## 11. CREATE, CREATE_NEW và nguy cơ ghi đè

Hai option dễ nhầm:

- **`CREATE`**: nếu tệp thiếu, cho phép tạo; nếu tệp đã có, có thể mở tệp hiện hữu theo những option còn lại.
- **`CREATE_NEW`**: bắt buộc tạo mới; khi tệp đã tồn tại, thao tác thường ném `FileAlreadyExistsException`. Yêu cầu này đặc biệt hữu ích khi không được phép ghi đè dữ liệu khác.

Mẫu nguy hiểm:

~~~java
if (!Files.exists(path)) {
    Files.createFile(path, attrs);
}
~~~

Đoạn minh họa có điều kiện đua (*TOCTOU*). Giữa bước kiểm tra và bước tạo, một tiến trình khác có thể tạo tệp. Kết quả kiểm tra trước không bảo đảm thao tác sau thành công.

Tốt hơn:

~~~java
try {
    Files.createFile(path, attrs);
} catch (FileAlreadyExistsException e) {
    // Phân xử tình huống trùng tên: không ghi đè.
}
~~~

Đây là đoạn minh họa. `Files.createFile` vốn đã kiểm tra sự không tồn tại và tạo theo hợp đồng nguyên tử đối với thao tác filesystem ảnh hưởng thư mục.

**Lưu ý:** “Tạo tệp và đặt thuộc tính ban đầu nguyên tử” không có nghĩa “ghi toàn bộ nội dung, tính checksum, đóng và chuyển tên” đều nằm trong cùng một transaction. Nếu cần cập nhật tài liệu quan trọng, còn phải thiết kế quy trình ghi tệp tạm, xác minh và thay thế đích phù hợp.

## 12. Kiểm tra provider và view trước khi dùng POSIX

Không phải môi trường nào cũng hỗ trợ quyền `PosixFilePermission`. Ví dụ nhiều hệ thống Windows thường dùng ACL theo chính sách hệ điều hành; việc cố dùng `PosixFilePermissions` trực tiếp có thể không được hỗ trợ.

Hai cách kiểm tra phổ biến:

~~~java
boolean posixSupported = Files.getFileStore(dir)
        .supportsFileAttributeView("posix");
~~~

hoặc:

~~~java
boolean posixSupported =
        Files.getFileAttributeView(dir,
                PosixFileAttributeView.class) != null;
~~~

Cả hai là đoạn minh họa; `dir` là `Path` của thư mục hiện hữu. `FileStore.supportsFileAttributeView("posix")` hỏi capability của store; `Files.getFileAttributeView` lấy một view khả dụng đối với path và provider hiện tại.

**Các phép kiểm tra capability không phải lời hứa tuyệt đối rằng thao tác tạo sắp tới sẽ luôn thành công.** Quyền, trạng thái mount, chính sách provider và thay đổi filesystem vẫn có thể làm lời gọi tạo thất bại; luôn xử lý ngoại lệ ngay tại thao tác.

### 12.1. Khi POSIX không được hỗ trợ phải làm gì?

Không nên:

~~~java
try {
    Files.createFile(path, posixAttrs);
} catch (UnsupportedOperationException ignored) {
    Files.createFile(path); // Có thể làm giảm yêu cầu bảo mật.
}
~~~

Đây là **anti-pattern** nếu mục tiêu là “file bắt buộc chỉ owner đọc được”. Tạo tệp với mặc định khi chính sách POSIX không thể áp dụng có thể làm tệp mới rộng quyền hơn dự định.

Các chiến lược phù hợp hơn:

1. **Dừng và báo không hỗ trợ** nếu hệ thống bắt buộc có quyền POSIX cụ thể.
2. **Thiết kế chính sách riêng cho Windows/ACL** bằng các API/provider hỗ trợ, và kiểm chứng hiệu lực trên OS mục tiêu.
3. **Dùng thư mục bảo vệ đã được provisioning** theo chính sách nền tảng; không suy rằng directory permissions của POSIX tương đương ACL của mọi hệ thống khác.
4. **Chọn lưu trữ phù hợp với mức nhạy cảm** (ví dụ kho bí mật, dịch vụ quản lý khóa hoặc môi trường có policy cụ thể), thay vì cố gắng mô phỏng chmod trên mọi máy.
5. **Ghi rõ khả năng tương thích của ứng dụng** trong tài liệu triển khai và kiểm thử trên filesystem đích.

Nếu dữ liệu không nhạy cảm và không có yêu cầu quyền chặt chẽ, có thể lựa chọn hành vi portable hơn. Nhưng đó là **quyết định nghiệp vụ**, không phải một fallback âm thầm sau khi bảo mật thất bại.

## 13. Một FileAttributeView có thể tồn tại nhưng không đặt được lúc tạo

Ví dụ các view:

| View | API thường gặp | Mục đích |
| --- | --- | --- |
| `BasicFileAttributeView` | `Files.readAttributes`, `Files.getLastModifiedTime` | Kích thước, loại, thời gian |
| `PosixFileAttributeView` | `Files.getPosixFilePermissions`, `Files.setPosixFilePermissions` | POSIX owner/group/mode |
| `DosFileAttributeView` | `Files.readAttributes(path, DosFileAttributes.class)`, `Files.setAttribute(path, "dos:hidden", ...)` | DOS read-only/hidden/archive/system |
| `AclFileAttributeView` | `Files.getFileAttributeView(path, AclFileAttributeView.class)` | Access control lists |
| `FileOwnerAttributeView` | `Files.getOwner`, `Files.setOwner` | Chủ sở hữu |

API đọc hoặc cập nhật một view **sau khi tạo** không tự chứng minh provider chấp nhận thuộc tính đó trong mảng `FileAttribute<?>...` truyền lúc tạo.

Ví dụ, `Files.setAttribute(path, "dos:hidden", true)` (nếu provider hỗ trợ) là **thao tác sau khi entry đã tồn tại**, không có nghĩa một `FileAttribute<Boolean>` tự tạo có tên `"dos:hidden"` chắc chắn được chấp nhận lúc `Files.createFile`.

Tương tự, việc yêu cầu đổi owner hoặc ACL ở thời điểm tạo cần xem đúng hợp đồng/khả năng provider, và không mặc định mọi ứng dụng được phép đặt chủ sở hữu thành người khác.

## 14. Những trường hợp thực tế

### 14.1. File cấu hình chứa token

Yêu cầu: file chỉ owner được đọc/ghi trên POSIX.

Thiết kế hợp lý:

1. Đảm bảo thư mục cha do thành phần tin cậy sở hữu và không cho đối tượng ngoài sửa tên entry.
2. Xác định POSIX view/initial attribute có được hỗ trợ không.
3. Tạo bằng `Files.createFile(path, posixAttr)` hoặc `Files.newByteChannel(path, CREATE_NEW+WRITE, attr)`.
4. Đọc lại quyền và kiểm tra hậu điều kiện trước khi ghi dữ liệu nhạy cảm nếu chính sách yêu cầu.
5. Quản lý writer/channel bằng `try-with-resources`, xử lý lỗi ghi/close.
6. Không ghi đè một tệp có sẵn bằng tên do người dùng không tin cậy cung cấp.

### 14.2. Thư mục làm việc riêng

Yêu cầu: chỉ owner có thể liệt kê/traverse thư mục.

Trên POSIX, yêu cầu `rwx------` khi tạo `Files.createDirectory` hoặc `Files.createTempDirectory`. Nhưng cũng cần xem quyền của **thư mục cha**, đặc biệt nếu đường dẫn nằm ở vùng chia sẻ hoặc được tạo từ input bên ngoài.

### 14.3. Tệp báo cáo nhóm

Yêu cầu: owner đọc/ghi, group đọc.

`rw-r-----` là một tập mode POSIX có thể thích hợp. Nhưng group thực tế của tệp thường phụ thuộc chính sách owner/group, setgid của thư mục và hệ thống tệp; **chỉ đặt mode chưa bảo đảm file thuộc đúng group được phép đọc**. Khi có yêu cầu chia sẻ nhóm nghiêm ngặt, cần kiểm tra cả group và quyền hiệu lực.

### 14.4. Tệp chỉ đọc ngay khi tạo

`r--------` biểu thị owner read-only. Tuy nhiên, nếu ngay sau khi tạo chương trình muốn ghi nội dung bằng một stream khác, một số cách ghi có thể không được phép; và trạng thái file descriptor đã mở trước thay đổi quyền có thể có quy tắc OS riêng.

Thông thường nên:
- Tạo tệp riêng tư cho quá trình ghi bằng quyền phù hợp (như `rw-------`).
- Hoàn tất dữ liệu và đóng đúng tài nguyên.
- Nếu nghiệp vụ đòi file cuối cùng chỉ đọc, đặt quyền cuối theo chính sách rõ ràng và chấp nhận rằng đây là một bước khác cần quản lý lỗi.
- Nếu có yêu cầu “không tồn tại bất kỳ cửa sổ quyền nào rộng hơn chính sách”, cần thiết kế provisioning/atomic publication phù hợp.

“Chỉ owner đọc” và “chương trình cần ghi nội dung ban đầu” là hai mục tiêu phải được phối hợp, không đơn thuần nhồi cùng một mode cho mọi giai đoạn.

## 15. Thay đổi thuộc tính sau khi tạo: khác biệt và rủi ro

Java có thể thay quyền sau tạo:

~~~java
Files.setPosixFilePermissions(
        path, PosixFilePermissions.fromString("rw-------"));
~~~

hoặc dùng một `FileAttributeView` tương ứng. Điều này hữu ích khi quản trị tệp hiện hữu, hoặc khi muốn thay đổi quyền **sau khi đã ghi xong nội dung**.

Nhưng hai chiến lược này khác nhau:

~~~text
A. Initial attrs:
   Files.createFile(path, attrs)
   └─ Tạo mới + yêu cầu áp dụng attrs tại thời điểm tạo

B. Post-creation update:
   Files.createFile(path)
   └─ Tệp tồn tại với thuộc tính ban đầu mặc định
       └─ Files.setPosixFilePermissions(path, ...)
           └─ Có khoảng thời gian giữa hai thao tác
~~~

Nếu ứng dụng tạo file rồi đổi quyền, ngay cả khi hai lời gọi nằm liên tiếp trong cùng thread, thread/process khác vẫn có thể quan sát file trong khoảng giữa. Với dữ liệu cần bảo mật ngay từ khi xuất hiện, ưu tiên initial attributes **khi provider hỗ trợ**.

Với tệp hiện hữu, `FileAttribute<?>` không phải công cụ “sửa mode” qua `Files.createFile`: vì `createFile` yêu cầu chưa tồn tại, nó sẽ thất bại với entry đang có. Chọn API set thuộc tính riêng và đánh giá kiểm soát truy cập thích hợp.

## 16. Lỗi thường gặp và ngoại lệ liên quan

| Lỗi/tình huống | Loại ngoại lệ/hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo file nhưng path đã tồn tại | Thường `FileAlreadyExistsException` | Không tự ghi đè; quyết định conflict |
| Thư mục cha không tồn tại | Có thể `NoSuchFileException` | Tạo cha theo chính sách hoặc báo lỗi |
| Không có quyền tạo trong thư mục cha | `AccessDeniedException` hoặc `IOException` khác | Báo lỗi/quyền, không nâng đặc quyền tùy tiện |
| Thuộc tính ban đầu không được hỗ trợ | `UnsupportedOperationException` | Dừng hoặc chiến lược provider riêng được duyệt |
| Đối số `null` không hợp lệ | `NullPointerException` | Xác thực API inputs |
| Chuỗi POSIX permissions sai cú pháp | `IllegalArgumentException` | Kiểm tra chính xác 9 ký tự |
| Nhiều attrs có cùng name | Hành vi dùng giá trị sau cùng theo hợp đồng áp dụng | Tránh truyền tên trùng |
| Tạo nhiều thư mục với `createDirectories` rồi lỗi giữa chừng | Một số thư mục cha đã được tạo | Xử lý cleanup/rollback theo nghiệp vụ |
| Đã tạo file với attrs, nhưng ghi nội dung lỗi | File trống hoặc dở dang có thể còn lại | Dọn/tạm hóa/thay thế có kiểm soát |
| Kiểm tra mode sau tạo không như yêu cầu | Chính sách OS/provider thay đổi quyền hiệu lực | Không coi tác vụ bảo mật là thành công |
| Kiểm tra `Files.exists` trước `createFile` | TOCTOU, vẫn có thể trùng tên | Dựa vào thao tác create và bắt lỗi |
| Tạo Path bên trong vùng có symbolic link ngoài ý muốn | Có thể trỏ tới vị trí khác | Kiểm soát thư mục cha, owner, symlink và race |

**Không phân loại lỗi bằng chuỗi thông báo hệ điều hành** như `"Permission denied"` vì thông điệp phụ thuộc OS/provider và có thể thay đổi. Bắt lớp con `IOException` phù hợp, giữ nguyên `cause`, và log thao tác/đường dẫn an toàn.

### 16.1. Khi nào là IOException, khi nào là UnsupportedOperationException?

`IOException` là checked exception cho lỗi I/O, ví dụ thiếu đường dẫn hoặc thiết bị. `UnsupportedOperationException` là unchecked exception thường biểu thị rằng provider không hỗ trợ lựa chọn/thuộc tính được yêu cầu.

Nếu ứng dụng có chính sách bắt buộc quyền POSIX, `UnsupportedOperationException` là **lỗi khả năng đáp ứng yêu cầu**, không phải một tình huống để tạo file rộng quyền “cho xong”.

Cũng cần lưu ý `SecurityException` trong những môi trường có cơ chế kiểm soát truy cập phù hợp; nó không phải `IOException`.

## 17. Kiểm thử đúng cách khi nhiều hệ thống tệp khác nhau

Không phải mọi môi trường Windows đều giống nhau; cũng không phải mọi thư mục trên một máy Linux đều nằm trên cùng filesystem/provider. Có thể có NTFS, FAT, tmpfs, network mount, ZIP filesystem hoặc provider đặc biệt.

Một chiến lược kiểm thử:

1. Tạo một thư mục thử nghiệm trong **đúng vùng filesystem** ứng dụng sẽ sử dụng.
2. Kiểm tra hỗ trợ của `FileStore`/`FileAttributeView` khi quan trọng.
3. Tạo file mới với `FileAttribute<?>` theo chính sách.
4. Đọc lại thuộc tính sau tạo; đừng chỉ kiểm tra `Files.exists`.
5. Kiểm tra tệp không bị ghi đè nếu path đã tồn tại.
6. Kiểm thử thiếu quyền và giới hạn khác bằng fixture kiểm soát, không làm thay đổi quyền của dữ liệu thật.
7. Kiểm thử lỗi khi ghi nội dung để xem file dở dang có bị để lại hay không.
8. Kiểm tra cleanup hoạt động trên filesystem mục tiêu.
9. Không giả định việc set mode 9 ký tự mô tả đầy đủ ACL của Windows.

### 17.1. Kiểm tra thuộc tính theo bất biến bảo mật

Với chính sách “group và others **không được có quyền mode**”, có thể kiểm tra các phần tử trong set:

~~~java
Set<PosixFilePermission> actual =
        Files.getPosixFilePermissions(path);

boolean restricted =
        !actual.contains(PosixFilePermission.GROUP_READ)
        && !actual.contains(PosixFilePermission.GROUP_WRITE)
        && !actual.contains(PosixFilePermission.GROUP_EXECUTE)
        && !actual.contains(PosixFilePermission.OTHERS_READ)
        && !actual.contains(PosixFilePermission.OTHERS_WRITE)
        && !actual.contains(PosixFilePermission.OTHERS_EXECUTE);
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. **Bất biến mode-bit** này là một bước kiểm tra cụ thể, không tự chứng minh mọi quyền hiệu lực nếu có ACL/đặc quyền/quy tắc OS khác. Khi yêu cầu bảo mật cao, phải đánh giá trên đúng filesystem và mô hình quyền của ứng dụng.

### 17.2. Tránh test bằng tên cố định trong thư mục người dùng

Không nên chọn một tên như `"test.txt"` trong thư mục làm việc, xóa tệp nếu tồn tại rồi chạy test: điều đó có thể xóa dữ liệu của người dùng khác hoặc dữ liệu ứng dụng. Sử dụng `Files.createTempDirectory` để tạo vùng thử nghiệm riêng, thực hiện các thao tác bên trong rồi xóa **đúng những entry do test tạo**.

## 18. Chọn giải pháp nào cho từng nhu cầu?

| Nhu cầu | Lựa chọn có ý nghĩa |
| --- | --- |
| Tạo tệp mới, không ghi đè, kèm POSIX mode | `Files.createFile(path, PosixFilePermissions.asFileAttribute(...))` |
| Tạo thư mục riêng tư | `Files.createDirectory(path, attrs)` hoặc `createTempDirectory(..., attrs)` |
| Tạo nhiều thư mục cha còn thiếu | `Files.createDirectories(path, attrs)`; nhớ không bảo đảm atomic toàn cây |
| Tạo và mở kênh byte để ghi ngay với attrs | `Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE), attrs)` |
| Tạo tệp tạm có quyền cụ thể | `Files.createTempFile(dir, prefix, suffix, attrs)` |
| Đặt quyền của tệp đã tồn tại | `Files.setPosixFilePermissions(path, permissions)` |
| Cần ACL của filesystem không POSIX | Tìm hiểu `AclFileAttributeView`/provider và chính sách triển khai |
| Chỉ cần tệp mới với quyền mặc định, không có policy riêng | `Files.createFile(path)` hoặc overload tạo tệp thích hợp |
| Cần ngăn race “đã tồn tại” | `Files.createFile` hoặc `CREATE_NEW`, không dùng `exists` rồi mới tạo |
| Cần chống mất dữ liệu khi ghi lỗi | Ghi tệp tạm/đóng/xác minh/thay thế theo policy; initial attrs chỉ giải quyết một phần |

## 19. Những hiểu sai phổ biến

**Hiểu sai 1: `FileAttribute<?>` là cách đổi quyền sau khi đã mở một tệp.**

Không. Nó mô tả **thuộc tính ban đầu** trong các overload có hỗ trợ khi tạo. Với entry tồn tại, dùng API `set...` tương ứng nếu hệ thống cho phép.

**Hiểu sai 2: Chỉ cần gọi `Files.createFile(path)` rồi `Files.setPosixFilePermissions` ngay sau đó là hoàn toàn nguyên tử.**

Không. Hai lần gọi tạo một khoảng thời gian có thể quan sát được. Nếu policy buộc có mode ngay lúc xuất hiện, hãy dùng overload nhận attrs trên provider hỗ trợ.

**Hiểu sai 3: `CREATE_NEW` chính là quyền file riêng tư.**

Không. Nó chỉ định thao tác tạo mới không ghi đè. Quyền file do initial attributes và chính sách của hệ thống tệp quyết định.

**Hiểu sai 4: POSIX mode 9 ký tự hoạt động như nhau trên mọi Windows, ZIP và network filesystem.**

Không. Các view được hỗ trợ phụ thuộc provider. Windows thường dựa trên ACL/NTFS; POSIX mode không phải mô hình quyền chung cho mọi môi trường.

**Hiểu sai 5: Nếu provider không hỗ trợ attrs, chỉ cần bỏ attrs và tạo file mặc định, vẫn bảo mật tương đương.**

Không chắc và có thể nguy hiểm. Với tệp nhạy cảm, cần từ chối hoặc dùng phương án bảo mật đã được kiểm chứng cho nền tảng.

**Hiểu sai 6: Set initial attrs thành công tức là đã ghi xong nội dung an toàn.**

Không. Tạo tệp, ghi dữ liệu, close, đồng bộ và publish kết quả là các vấn đề khác nhau. Nếu cần cập nhật quan trọng, phải thiết kế toàn bộ vòng đời.

**Hiểu sai 7: Có quyền POSIX owner-only là chắc chắn không ai khác truy cập được trong mọi hoàn cảnh.**

Không. Quyền hiệu lực còn phụ thuộc ACL, đặc quyền OS, quyền của thư mục cha và mô hình bảo mật của hệ thống. Chỉ khẳng định trong phạm vi đã kiểm tra.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Sự khác nhau giữa `Files.createFile(path, attrs)` và `Files.setPosixFilePermissions(path, perms)`?

**Đáp án:** lệnh đầu tạo tệp mới và yêu cầu thuộc tính ngay khi tạo; lệnh thứ hai sửa quyền một entry đã tồn tại. Nếu tạo rồi mới sửa, có thể có cửa sổ thời gian với quyền chưa đúng.

**Câu 2.** `FileAttribute<Set<PosixFilePermission>>` dùng để làm gì?

**Đáp án:** là đối tượng kiểu hóa tên/giá trị thuộc tính được truyền vào các phương thức tạo có tham số `FileAttribute<?>...`. `PosixFilePermissions.asFileAttribute(...)` tạo giá trị thích hợp cho POSIX permissions.

**Câu 3.** Mode `rw-------` là gì?

**Đáp án:** owner đọc và ghi; group/others không được cấp bit nào trong POSIX mode. Nó không tự nói hết về ACL hoặc đặc quyền khác.

**Câu 4.** Với một thư mục riêng tư, `rw-------` có phù hợp như một thư mục cần traverse hay không?

**Đáp án:** thường không. Thư mục cần quyền `x` để traverse trong mô hình POSIX; `rwx------` là mẫu điển hình khi chỉ owner cần truy cập.

**Câu 5.** Truyền attrs vào `Files.createDirectories` có tự đổi quyền của thư mục cha đã có không?

**Đáp án:** không. Chúng áp dụng cho thư mục được tạo mới theo hợp đồng, không tự cập nhật entry hiện hữu. Và toàn bộ việc tạo nhiều cấp không phải một transaction duy nhất.

**Câu 6.** Nếu đang dùng một filesystem không hỗ trợ POSIX, nên tự bắt `UnsupportedOperationException` rồi tạo tệp không có attrs không?

**Đáp án:** chỉ khi policy nghiệp vụ cho phép và đã hiểu quyền mặc định. Nếu cần owner-only theo tiêu chuẩn bắt buộc, không được fallback âm thầm.

**Câu 7.** Khi dùng `Files.newByteChannel(path, Set.of(CREATE, WRITE), attrs)` trên tệp đã có, attrs có tự thay mode của tệp cũ?

**Đáp án:** không. Initial attributes chỉ được dùng khi **thật sự tạo mới**. Thao tác mở tệp đã tồn tại không phải một yêu cầu sửa quyền.

**Câu 8.** Vì sao nên dùng `CREATE_NEW` khi không được phép ghi đè?

**Đáp án:** nó yêu cầu quá trình tạo mới và từ chối nếu đã tồn tại theo hợp đồng, tránh mô hình kiểm tra `Files.exists` rồi tạo gây TOCTOU.

**Câu 9.** Với tệp nhạy cảm, chỉ kiểm tra `Files.exists(file)` sau khi tạo đã đủ?

**Đáp án:** chưa. Cần xác minh quyền, quyền sở hữu/ACL theo chính sách, việc ghi/đóng thành công và các điều kiện an toàn liên quan.

### Bài tập thực hành

1. Viết chương trình tạo một tệp qua `Files.createFile` với `rw-------`, đọc lại bằng `Files.getPosixFilePermissions` và in theo `PosixFilePermissions.toString`. Nếu provider không hỗ trợ, báo rõ và không tạo dữ liệu nhạy cảm.
2. Tạo thư mục bằng `rwx------` với `Files.createDirectory`. Thử tạo một tệp bên trong rồi xóa cả hai ở cuối chương trình.
3. Dùng `Files.createTempFile` với initial attrs; xác minh kết quả không dựa vào tên tệp ngẫu nhiên.
4. Dùng `Files.newByteChannel` với `CREATE_NEW` + `WRITE` + attrs, ghi 5 byte UTF-8 và kiểm tra kích thước.
5. Thử tạo lại cùng đường dẫn bằng `Files.createFile` để thấy `FileAlreadyExistsException`; đừng xóa tệp gốc khi thử.
6. Đặt chính sách nhóm `rw-r-----` và tìm hiểu vì sao group thực tế của file cũng cần được kiểm tra.
7. Tạo một thư mục con bằng `Files.createDirectories`, so sánh quyền của thư mục đã tồn tại và thư mục mới được tạo; đừng giả định thư mục cũ được đổi quyền.
8. Thiết kế nhánh xử lý cho Windows/ACL và POSIX mà không bỏ qua ràng buộc bảo mật, ghi rõ khả năng hỗ trợ trước khi triển khai.

## 21. Kết luận

- **`FileAttribute<?>`** là cách diễn đạt thuộc tính ban đầu khi tạo entry thông qua những overload `Files` có hỗ trợ.
- **`Files.createFile(path, attrs)`** và **`Files.createDirectory(path, attrs)`** cho phép yêu cầu thuộc tính lúc tạo; `Files.createDirectories` áp dụng attrs cho entry mới chứ không tự sửa entry cũ.
- **`PosixFilePermissions.fromString`** và **`asFileAttribute`** là bộ công cụ gọn để tạo yêu cầu quyền POSIX; mode `rw-------` thường dùng cho tệp riêng, `rwx------` cho thư mục riêng.
- **Tạo với attrs khác với “tạo xong rồi chmod”.** Khi provider hỗ trợ, đặt thuộc tính ngay lúc tạo hạn chế race về quyền mặc định.
- **Provider quyết định khả năng hỗ trợ và quyền hiệu lực.** Không giả định mọi hệ thống tệp hiểu POSIX, ACL hay metadata giống nhau; kiểm tra và báo lỗi nếu chính sách không được đáp ứng.
- **`CREATE_NEW` ngăn ghi đè**, còn `CREATE` không tự thay đổi thuộc tính của tệp đã tồn tại.
- **Tạo đúng quyền chưa đủ cho độ an toàn toàn diện.** Vẫn cần quản lý luồng ghi, close, lỗi dở dang, đồng bộ dữ liệu và kiểm soát đường dẫn.

### Tài liệu tham khảo Java SE 17

- [Files.createFile / createDirectory / createDirectories / createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Files.newByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newByteChannel(java.nio.file.Path,java.util.Set,java.nio.file.attribute.FileAttribute...))
- [FileAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttribute.html)
- [PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html)
- [PosixFilePermission](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermission.html)
- [FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html)
