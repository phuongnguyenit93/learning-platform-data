# Thuộc tính DOS trên Windows trong Java NIO.2

Trên Windows, tệp và thư mục có một nhóm cờ thuộc tính quen thuộc: **Read-only**, **Hidden**, **System** và **Archive**. Java NIO.2 cung cấp các giao diện `DosFileAttributes` và `DosFileAttributeView` để đọc, sửa những cờ này trên hệ thống tệp hỗ trợ chúng, thường gặp ở các định dạng FAT/NTFS trên Windows.

Điểm quan trọng: **thuộc tính DOS là metadata của file system, không phải nội dung tệp, không phải phần mở rộng tên và không tương đương toàn bộ quyền truy cập Windows ACL hoặc POSIX**. Một file có cờ `hidden` vẫn có thể được đọc nếu chương trình có quyền; một file có `readonly` không mặc nhiên là “không ai có thể chỉnh sửa hoặc xóa” trong mọi trường hợp.

Bài học sử dụng Java 17+, trình bày cách đọc/sửa cờ bằng API kiểu tường minh hoặc tên thuộc tính dạng chuỗi, cách nhận biết provider không hỗ trợ, lỗi thường gặp, symbolic link và ví dụ tự tạo file tạm an toàn.

## 1. Bốn thuộc tính DOS cần nhớ

| Thuộc tính | Trong Java | Ý nghĩa thường gặp | Điều **không** nên suy ra |
|---|---|---|---|
| **Read-only** | `isReadOnly()` / `setReadOnly(boolean)` | Đánh dấu tệp chỉ đọc theo kiểu DOS | Không đồng nghĩa toàn bộ chính sách quyền ACL, không phải cam kết bất khả xâm phạm |
| **Hidden** | `isHidden()` / `setHidden(boolean)` | Đánh dấu mục nên được ẩn khỏi giao diện hiển thị thông thường | Không phải mã hóa, không phải kiểm soát truy cập |
| **System** | `isSystem()` / `setSystem(boolean)` | Đánh dấu mục liên quan hệ thống | Không biến tệp thành thành phần hệ điều hành hợp lệ |
| **Archive** | `isArchive()` / `setArchive(boolean)` | Gợi ý trạng thái có thể cần lưu trữ/sao lưu | Không bảo đảm backup đã hoặc sẽ diễn ra |

Các cờ có thể được kết hợp. Một tệp có thể vừa `hidden` vừa `readonly`; cập nhật một cờ không có nghĩa phải đặt lại tất cả cờ còn lại.

Java chỉ cung cấp mô hình truy cập các cờ. **Khả năng hỗ trợ và mức thực thi** vẫn do file-system provider, hệ điều hành, loại ổ lưu trữ và quyền của tiến trình quyết định.

### Đối chiếu với File Explorer

Trên Windows, thuộc tính này thường thấy trong hộp thoại **Properties** của File Explorer hoặc qua công cụ dòng lệnh `attrib`. Tuy nhiên, một số cờ như System/Archive không nhất thiết được trình bày giống Read-only/Hidden trong giao diện đơn giản, và cách File Explorer xử lý thư mục có thể khác tệp.

Không thay thế việc đọc metadata từ Java bằng suy đoán dựa trên giao diện Explorer, tên bắt đầu bằng dấu chấm hay đuôi file.

## 2. Hai giao diện cốt lõi

Cả hai ở package:

~~~java
import java.nio.file.attribute.DosFileAttributes;
import java.nio.file.attribute.DosFileAttributeView;
~~~

### `DosFileAttributes`: ảnh chụp thuộc tính để **đọc**

`DosFileAttributes` kế thừa `BasicFileAttributes`. Ngoài bốn phương thức riêng `isReadOnly()`, `isHidden()`, `isSystem()`, `isArchive()`, nó còn có các phương thức cơ bản:

- `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `isOther()`.
- `size()` cho kích thước do provider báo (byte đối với tệp thường).
- `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`.
- `fileKey()` nếu provider có khóa nhận dạng.

Một đối tượng `DosFileAttributes` là **kết quả đọc tại một thời điểm**; nó không tự cập nhật khi ai đó đổi cờ sau đó. Muốn nhận trạng thái mới, gọi `Files.readAttributes(...)` hoặc `view.readAttributes()` lần nữa.

### `DosFileAttributeView`: giao diện **đọc và cập nhật**

`DosFileAttributeView` kế thừa `BasicFileAttributeView` và có các phương thức:

~~~java
DosFileAttributes readAttributes() throws IOException;
void setReadOnly(boolean value) throws IOException;
void setHidden(boolean value) throws IOException;
void setSystem(boolean value) throws IOException;
void setArchive(boolean value) throws IOException;
~~~

Đây là **các chữ ký minh họa**; để dùng phải có `DosFileAttributeView` gắn với một `Path`. Tên của view này theo Javadoc là `"dos"`, dùng trong các lệnh truy cập động như `"dos:hidden"`.

Lưu ý: không phải mỗi lần sửa cờ đều là thao tác nguyên tử với các hoạt động file system khác. Tài liệu `DosFileAttributeView` cho phép triển khai phải đọc các cờ trước rồi mới cập nhật; việc nhiều tiến trình đồng thời sửa thuộc tính cần được thiết kế và kiểm thử riêng.

## 3. Cách đọc thuộc tính DOS bằng API kiểu tường minh

Có hai cách chính.

### Cách A: `Files.readAttributes`

~~~java
// Mảnh mã minh họa: path là Path của mục cần đọc.
DosFileAttributes attrs =
        Files.readAttributes(path, DosFileAttributes.class);

boolean readOnly = attrs.isReadOnly();
boolean hidden = attrs.isHidden();
boolean system = attrs.isSystem();
boolean archive = attrs.isArchive();
~~~

Nếu file system không hỗ trợ loại thuộc tính yêu cầu, `readAttributes(path, DosFileAttributes.class)` có thể ném `UnsupportedOperationException`. Các lỗi truy cập đường dẫn có thể là `IOException`; chính sách bảo mật có thể tạo `SecurityException`.

### Cách B: `Files.getFileAttributeView`

~~~java
// Mảnh mã minh họa: path là Path hợp lệ.
DosFileAttributeView view =
        Files.getFileAttributeView(path, DosFileAttributeView.class);

if (view == null) {
    // Provider không cung cấp view này.
} else {
    DosFileAttributes attrs = view.readAttributes();
    System.out.println(attrs.isHidden());
}
~~~

`Files.getFileAttributeView(...)` trả `null` khi loại view không khả dụng. Đây là đường đi thuận tiện nếu muốn **kiểm tra hỗ trợ trước khi đọc hoặc cập nhật**.

**Đừng nhầm:** có được một view không bảo đảm mọi thao tác đọc/ghi chắc chắn thành công: tệp có thể không còn tồn tại, quyền không đủ, ổ đĩa gặp lỗi hoặc thao tác bị provider từ chối. Khi dùng view vẫn cần xử lý `IOException`.

## 4. Xác định hỗ trợ thay vì kiểm tra tên hệ điều hành

Không nên viết quy tắc:

~~~java
// Mảnh mã KHÔNG nên dùng làm phép xác định khả năng DOS view.
boolean supported =
        System.getProperty("os.name").contains("Windows");
~~~

Tên OS không phản ánh đầy đủ tính năng của **file system nơi Path nằm**. Cùng một máy Windows có thể truy cập ổ mạng, ZIP file system hoặc provider khác; một nhà cung cấp `FileSystem` trên nền tảng khác cũng có thể cung cấp mô hình DOS.

Các API xác định hỗ trợ:

~~~java
// Mảnh mã minh họa.
boolean providerAdvertises =
        path.getFileSystem()
                .supportedFileAttributeViews().contains("dos");

boolean storeSupports =
        Files.getFileStore(path)
                .supportsFileAttributeView(DosFileAttributeView.class);

DosFileAttributeView view =
        Files.getFileAttributeView(path, DosFileAttributeView.class);
boolean viewAvailable = view != null;
~~~

Điểm khác nhau:

- `supportedFileAttributeViews()` là tập tên view mà **FileSystem** công bố; có thể không mô tả đầy đủ những hạn chế riêng của từng file store.
- `FileStore.supportsFileAttributeView(...)` hỏi **file store**; ngay cả khi báo hỗ trợ, vẫn có thể gặp lỗi theo môi trường hoặc tài nguyên cụ thể. Với default provider, kết quả trên thiết bị không phải lưu trữ cục bộ có thể có giới hạn độ chính xác theo Javadoc.
- `getFileAttributeView(...)` lấy một đối tượng view cho `Path`; nếu không có thì trả `null`, nhưng thao tác thực tế sau đó mới xác nhận truy cập thành công.
- `Files.getFileStore(path)` cũng có thể ném `IOException` nếu không tìm được file store.

Một cách thực hành vững là **lấy view và kiểm tra `null`, rồi xử lý lỗi khi sử dụng**. Nếu chương trình chạy đa nền tảng, hãy định nghĩa rõ nhánh khi DOS view không hỗ trợ thay vì ép kiểu hoặc cố truy cập thuộc tính bằng mọi giá.

## 5. Ví dụ Java 17+: đọc cờ trên file tạm và nhận biết nơi không hỗ trợ

Tạo file **`DosFlagsProbe.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.DosFileAttributes;

public class DosFlagsProbe {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("dos-probe-", ".txt");

        try {
            DosFileAttributeView view =
                    Files.getFileAttributeView(
                            file, DosFileAttributeView.class);

            if (view == null) {
                System.out.println("dosView=unsupported");
            } else {
                DosFileAttributes attrs = view.readAttributes();

                System.out.println("dosView=available");
                System.out.println("regularFile=" + attrs.isRegularFile());
                System.out.println("readonly=" + attrs.isReadOnly());
                System.out.println("hidden=" + attrs.isHidden());
                System.out.println("system=" + attrs.isSystem());
                System.out.println("archive=" + attrs.isArchive());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DosFlagsProbe.java
java DosFlagsProbe
~~~

Nếu provider **không hỗ trợ**:

~~~text
dosView=unsupported
~~~

Nếu provider hỗ trợ và đọc thành công, đầu ra có dạng:

~~~text
dosView=available
regularFile=true
readonly=<boolean>
hidden=<boolean>
system=<boolean>
archive=<boolean>
~~~

Trong khối trên, `<boolean>` là **ký hiệu giải thích**, không phải stdout cố định: Java thực sự in `true` hoặc `false`. Các giá trị ban đầu của cờ phụ thuộc file system và cách tạo file; vì thế **không nên bịa một bộ giá trị duy nhất cho mọi máy**. Ví dụ này được thiết kế để tự động chọn nhánh tùy môi trường.

File được tạo bằng `Files.createTempFile` và được xóa trong `finally`. Nếu có lỗi đọc quyền/thiết bị, chương trình có thể ném `IOException` — đó là hành vi bình thường của tác vụ truy cập file system.

## 6. Cập nhật bốn cờ với DosFileAttributeView

Sau khi xác nhận view có sẵn, dùng các setter:

~~~java
// Mảnh mã minh họa, tác động lên file thật: cần quyền và chính sách rõ.
view.setReadOnly(true);  // Bật cờ Read-only.
view.setHidden(true);    // Bật cờ Hidden.
view.setArchive(true);   // Bật cờ Archive.
view.setSystem(true);    // Bật cờ System.
~~~

Đặt `false` để tắt cờ tương ứng. Nhưng **không nên bật System hoặc Read-only tùy tiện trên file thật**: các ứng dụng khác có thể phụ thuộc vào những cờ này; tùy nền tảng, xóa/chỉnh file có thể bị từ chối sau khi bật read-only. Hơn nữa, “System=true” **không** đồng nghĩa file được hệ điều hành xác nhận là thành phần hệ thống.

Khi thao tác trên dữ liệu thực:

1. Đọc trạng thái trước đó để quyết định có cần thay đổi không.
2. Xác nhận chương trình có quyền và thực sự sở hữu tài nguyên.
3. Sửa **chỉ cờ mong muốn**.
4. Đọc lại thuộc tính để xác minh kết quả.
5. Xử lý `IOException`/`SecurityException` và tránh retry vô hạn.
6. Nếu chỉ thay đổi tạm thời, phục hồi trạng thái khi kết thúc.

Không dùng `Files.setAttribute(...)` hoặc setter của view để thử nghiệm trực tiếp trên tệp cấu hình hệ thống, thư mục Windows hay dữ liệu người dùng mà chưa được cho phép.

## 7. Ví dụ Java 17+: bật/tắt Hidden trên file tạm rồi phục hồi

Tạo file **`DosHiddenRoundTrip.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;

public class DosHiddenRoundTrip {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("dos-hidden-", ".txt");

        try {
            DosFileAttributeView view =
                    Files.getFileAttributeView(
                            file, DosFileAttributeView.class);

            if (view == null) {
                System.out.println("dosView=unsupported");
            } else {
                boolean original = view.readAttributes().isHidden();

                try {
                    view.setHidden(!original);
                    boolean updated =
                            view.readAttributes().isHidden();
                    System.out.println("changed=" + (updated != original));
                } finally {
                    // Phục hồi cờ ban đầu trên chính file tạm.
                    view.setHidden(original);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DosHiddenRoundTrip.java
java DosHiddenRoundTrip
~~~

Trên provider **không hỗ trợ**:

~~~text
dosView=unsupported
~~~

Trên provider **hỗ trợ và cho phép cập nhật thành công**:

~~~text
changed=true
~~~

Nếu file system hỗ trợ view nhưng cấm sửa cờ, lệnh setter có thể ném `IOException`; **đó không phải là một đầu ra ổn định** và cần được xử lý theo ứng dụng thực. Trong ví dụ, trạng thái Hidden ban đầu được lưu rồi phục hồi ở `finally`; sau đó chỉ xóa file tạm.

Việc thay đổi thuộc tính qua Java được thực thi trên file system thật, không phải chỉ đổi một biến Java. Nếu ứng dụng tạo nhiều tác vụ đồng thời hoặc bên ngoài cùng sửa cờ, ví dụ đơn giản này không đảm bảo bảo toàn thay đổi của tác nhân khác. Với file riêng do chương trình tạo, rủi ro này dễ kiểm soát hơn.

## 8. API động: "dos:readonly", "dos:hidden", "dos:system", "dos:archive"

Ngoài giao diện có kiểu, Java hỗ trợ đọc/sửa thuộc tính theo tên view và tên thuộc tính dạng chuỗi:

~~~java
// Mảnh mã minh họa; path là Path thuộc file system hỗ trợ DOS.
Object hidden = Files.getAttribute(path, "dos:hidden");
Files.setAttribute(path, "dos:hidden", Boolean.TRUE);
Files.setAttribute(path, "dos:readonly", Boolean.FALSE);
~~~

Bốn tên thuộc tính động được định nghĩa trong Javadoc:

| Tên đầy đủ | Kiểu khi đọc | Setter tương ứng |
|---|---|---|
| `"dos:readonly"` | `Boolean` | `setReadOnly(boolean)` |
| `"dos:hidden"` | `Boolean` | `setHidden(boolean)` |
| `"dos:system"` | `Boolean` | `setSystem(boolean)` |
| `"dos:archive"` | `Boolean` | `setArchive(boolean)` |

**Chú ý tên:** key động là `readonly` viết liền và chữ thường, **không phải** `readOnly`, `read-only` hay `ReadOnly`. Đừng nhầm tên thuộc tính với tên phương thức Java `isReadOnly()`.

Đọc nhiều thuộc tính một lượt:

~~~java
// Mảnh mã minh họa; cần import java.util.Map.
Map<String, Object> flags = Files.readAttributes(
        path, "dos:readonly,hidden,system,archive");
Boolean isHidden = (Boolean) flags.get("hidden");
~~~

Map chứa các key ngắn như `"readonly"`, `"hidden"`, `"system"`, `"archive"`, **không** bắt buộc gắn tiền tố `"dos:"` trên mỗi key. Với provider không hỗ trợ, thao tác có thể ném `UnsupportedOperationException`; lỗi truy cập file vẫn có thể ném `IOException`.

Nếu dùng API kiểu tường minh, trình biên dịch kiểm tra được tên phương thức. API động hữu ích khi phải xây dựng trình xem metadata tổng quát, nhưng dễ mắc lỗi gõ sai tên và ép kiểu. Với bốn cờ DOS cố định, dùng `DosFileAttributes`/`DosFileAttributeView` thường rõ nghĩa hơn.

## 9. Ví dụ chạy được: nhất quán giữa API kiểu và API động

Tạo file **`DosAttributeApiComparison.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.DosFileAttributes;
import java.util.Map;

public class DosAttributeApiComparison {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("dos-compare-", ".txt");

        try {
            DosFileAttributeView view =
                    Files.getFileAttributeView(
                            file, DosFileAttributeView.class);

            if (view == null) {
                System.out.println("dosView=unsupported");
                return;
            }

            DosFileAttributes typed = view.readAttributes();
            Map<String, Object> dynamic = Files.readAttributes(
                    file, "dos:readonly,hidden,system,archive");

            boolean equal =
                    typed.isReadOnly() == (Boolean) dynamic.get("readonly")
                    && typed.isHidden() == (Boolean) dynamic.get("hidden")
                    && typed.isSystem() == (Boolean) dynamic.get("system")
                    && typed.isArchive() == (Boolean) dynamic.get("archive");

            System.out.println("sameFlags=" + equal);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DosAttributeApiComparison.java
java DosAttributeApiComparison
~~~

Nếu không hỗ trợ DOS view:

~~~text
dosView=unsupported
~~~

Nếu view được hỗ trợ và không có tác nhân nào đồng thời thay đổi thuộc tính giữa hai lần đọc:

~~~text
sameFlags=true
~~~

Hai phép đọc được thực hiện **không đồng thời**, nên kết quả trên là mô hình cho một file tạm không bị bên khác sửa; nếu có thay đổi giữa hai phép đọc, giá trị so sánh có thể khác. Mục tiêu là cho thấy **bốn tên động tương ứng** với bốn getter có kiểu.

## 10. Thuộc tính DOS khác quyền Windows ACL và POSIX

Đây là chỗ dễ hiểu sai nhất khi xây dựng phần mềm quản lý file.

### DOS Read-only không thay thế ACL

Cờ `readonly` thường dùng như một dấu đánh dấu nhằm hạn chế cập nhật, nhưng Javadoc `DosFileAttributes` nói rõ **có hay không có cơ chế cưỡng chế ngăn sửa/xóa tùy thuộc triển khai**. Trên Windows, NTFS còn có **ACL** quyết định tài khoản hoặc nhóm nào có quyền đọc, ghi, xóa, thay đổi quyền...

Vì vậy:

- `attrs.isReadOnly() == false` **không** chứng minh tiến trình có quyền ghi file.
- `attrs.isReadOnly() == true` **không** là bằng chứng tuyệt đối rằng file không thể bị thay đổi trong mọi ngữ cảnh.
- `Files.isWritable(path)` phản ánh khả năng ghi từ góc nhìn JVM hiện tại nhưng cũng có hạn chế, có thể lỗi thời ngay sau khi kiểm tra.
- Để đọc/sửa ACL, xem `AclFileAttributeView` khi provider hỗ trợ, và luôn áp chính sách phân quyền đúng hệ điều hành.

Không xây dựng kiểm soát truy cập dữ liệu nhạy cảm dựa duy nhất trên DOS Read-only hoặc Hidden.

### DOS Hidden khác tên bắt đầu bằng dấu chấm trên Unix

`Files.isHidden(path)` có quy tắc **phụ thuộc platform/provider**. Theo Javadoc:

- Trên Windows, việc một mục được coi là hidden thường dựa vào **DOS hidden flag**.
- Trên Unix, tên bắt đầu bằng dấu chấm `.` thường được coi là hidden.
- Một file tên `.secret` trên Windows **không tự động có cờ DOS Hidden chỉ vì tên bắt đầu bằng dấu chấm**.
- Một file có cờ DOS Hidden không cần có tiền tố `.` ở tên.

Bởi vậy `Files.isHidden(path)` là API tương đối portable nếu mục tiêu là **“hệ điều hành này coi tệp có ẩn không?”**. Nếu mục tiêu là **đọc/sửa đúng cờ DOS**, hãy dùng `DosFileAttributes.isHidden()` hoặc `DosFileAttributeView.setHidden(...)`.

### DOS khác POSIX permissions

Trên Unix/Linux, quyền phổ biến như `rwxr-x---` được quản lý bởi `PosixFilePermissions`/`PosixFileAttributeView`. Nó không tương đương một-một với bốn cờ DOS. Cùng một chương trình muốn chạy trên Windows và Linux phải chọn abstraction phù hợp, hoặc viết nhánh xử lý capability-based thay vì giả định cả hai mô hình giống nhau.

## 11. Symlink, NOFOLLOW_LINKS và rủi ro thay đổi đích

Các API `Files.getFileAttributeView(...)` và `Files.readAttributes(...)` nhận `LinkOption...`. Mặc định chúng **theo symbolic link** tới đích cuối nếu provider hỗ trợ link:

~~~java
// Mảnh mã minh họa; cần import LinkOption.
DosFileAttributes targetAttrs = Files.readAttributes(
        link, DosFileAttributes.class);

DosFileAttributes linkAttrs = Files.readAttributes(
        link, DosFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
~~~

`NOFOLLOW_LINKS` yêu cầu xét **đối tượng link**, không đi theo tới target cuối, trong trường hợp provider hỗ trợ. Nhưng không có bảo đảm mọi provider đều cung cấp DOS view trên bản thân symbolic link. Một số file system có thể không hỗ trợ thao tác đọc/sửa một cờ DOS trên link hoặc có quy tắc riêng.

Tương tự với view dùng để sửa:

~~~java
// Mảnh mã minh họa.
DosFileAttributeView linkView = Files.getFileAttributeView(
        link, DosFileAttributeView.class, LinkOption.NOFOLLOW_LINKS);
~~~

Đừng coi `getFileAttributeView(..., NOFOLLOW_LINKS)` là cách phòng chống mọi cuộc tấn công race: một liên kết hoặc đường dẫn có thể bị thay đổi giữa thời điểm chọn view và khi cập nhật. Trong ứng dụng thao tác trên path không tin cậy, cần kiểm soát ownership, quyền, link và khả năng thay đổi của file system.

Với path do người dùng cung cấp, kể cả thao tác tưởng nhỏ như bật Hidden cũng là **thay đổi trạng thái của tài nguyên thật**. Nên giới hạn quyền và chỉ thay đổi những file mà ứng dụng quản lý.

## 12. Thứ tự thay đổi cờ và vấn đề nhất quán

Giả sử ứng dụng muốn bật cả `hidden` và `archive`:

~~~java
// Mảnh mã minh họa trên view có quyền sửa.
view.setHidden(true);
view.setArchive(true);
~~~

Hai lệnh này **không được cam kết tạo thành một transaction**. Có thể bật Hidden thành công rồi bật Archive thất bại, khiến file ở trạng thái cập nhật một phần. Ngoài ra, giữa hai lời gọi, một thread hoặc process khác có thể đọc/sửa cờ.

Khi nghiệp vụ yêu cầu một trạng thái nhất quán:

1. Xác định thuộc tính nào thực sự cần chỉnh, không tự ý sửa System/Archive cho mọi file.
2. Tính đến khả năng một phần thao tác đã hoàn thành.
3. Đọc lại trạng thái sau khi sửa.
4. Cân nhắc cơ chế phối hợp giữa những process có quyền thay đổi cùng file.
5. Thiết kế cách xử lý thất bại nhưng không xóa các thay đổi hợp lệ của tiến trình khác.

Không giả định `Files.readAttributes(...)` luôn là một ảnh chụp nguyên tử hoàn toàn tương ứng với mọi thao tác đồng thời; Javadoc cho biết tính nguyên tử của phép đọc bulk **phụ thuộc triển khai**.

### Archive flag không phải hệ thống sao lưu

`archive` là cờ truyền thống thường được phần mềm backup sử dụng để gợi ý dữ liệu đã thay đổi hoặc cần lưu trữ. Nhưng có các lưu ý:

- Không có nghĩa Windows hay Java đã sao lưu file.
- Công cụ backup khác nhau có thể dùng hoặc bỏ qua cờ này.
- Một số hoạt động ghi/sửa có thể cập nhật cờ theo quy tắc của file system.
- Không dùng `archive=false` làm bằng chứng chắc chắn rằng dữ liệu đã được backup an toàn.

Nếu hệ thống có yêu cầu khôi phục sau mất dữ liệu, phải có chính sách backup, kiểm tra snapshot và thử khôi phục thực tế.

## 13. Lỗi thường gặp và xử lý

| Trường hợp | Hành vi/cách hiểu | Xử lý phù hợp |
|---|---|---|
| `getFileAttributeView(..., DosFileAttributeView.class)` trả `null` | DOS view không khả dụng cho path/provider | Dùng nhánh fallback hoặc báo không hỗ trợ |
| `Files.readAttributes(..., DosFileAttributes.class)` ném `UnsupportedOperationException` | View yêu cầu không được hỗ trợ | Tránh giả định mọi OS đều có |
| Setter ném `IOException` | Lỗi quyền, I/O, path biến mất hoặc provider từ chối | Giữ ngữ cảnh lỗi, không retry vô hạn |
| `Files.setAttribute(path, "dos:readOnly", ...)` | Sai tên thuộc tính động | Dùng `"dos:readonly"` |
| `Files.setAttribute(path, "dos:hidden", "true")` | Giá trị là chuỗi, không phải `Boolean` | Dùng `Boolean.TRUE` hoặc `true` |
| Đổi `readonly` rồi quên phục hồi | Có thể ảnh hưởng thao tác ghi/xóa sau này | Sửa cờ trên file sở hữu, lưu trạng thái cũ |
| Coi `hidden` là cách bảo mật nội dung | Hidden chỉ là metadata/hiển thị | Dùng quyền/ACL, mã hóa hoặc cơ chế bảo mật thực |
| Cho rằng dấu `.` ở đầu file tương đương DOS Hidden | Quy tắc khác giữa Unix/Windows | Phân biệt `Files.isHidden` và DOS view |
| Đọc một lần rồi coi attrs cập nhật trực tiếp | `DosFileAttributes` là kết quả snapshot | Gọi `readAttributes()` lại |
| Sửa nhiều cờ và mong nguyên tử | Không có transaction mặc định | Thiết kế xử lý cập nhật một phần |
| Mở một đường dẫn có link và giả định không follow | Mặc định nhiều API theo symlink | Xác định rõ `NOFOLLOW_LINKS` và khả năng hỗ trợ |
| Dùng `archive` để xác nhận backup đã hoàn tất | Cờ Archive không là chứng nhận backup | Kiểm tra hệ thống sao lưu thực tế |

### Ngoại lệ cần dự liệu

- `IOException`: lỗi truy cập file, path không còn tồn tại, thiết bị hay provider gặp trục trặc.
- `UnsupportedOperationException`: attribute view không hỗ trợ; thường gặp trên provider không có DOS attributes.
- `IllegalArgumentException`: tên thuộc tính động sai/không phù hợp, tùy API.
- `ClassCastException`: truyền giá trị sai kiểu vào API động `Files.setAttribute(...)`.
- `SecurityException`: chính sách quyền Java/triển khai từ chối thao tác.

Trước khi xử lý ngoại lệ, phân biệt đây là **lỗi kỹ thuật** hay **tính năng vốn không hỗ trợ trên nền tảng**. Với ứng dụng đa nền tảng, không nên làm cả chương trình thất bại chỉ vì phần hiển thị một cờ DOS không tồn tại nếu nghiệp vụ cho phép bỏ qua.

## 14. Khi nào nên chọn API nào?

| Nhu cầu | API khuyến nghị | Lý do |
|---|---|---|
| Kiểm tra file được OS coi là ẩn hay không | `Files.isHidden(path)` | Có abstraction theo platform |
| Đọc chính xác bốn cờ DOS | `Files.readAttributes(path, DosFileAttributes.class)` | Kiểu rõ ràng, đọc nhiều thuộc tính |
| Đọc rồi thay đổi cờ | `Files.getFileAttributeView(path, DosFileAttributeView.class)` | Kiểm tra `null` và dùng getter/setter |
| Chỉ lấy một cờ động | `Files.getAttribute(path, "dos:hidden")` | Thuận tiện khi xây dựng metadata viewer |
| Sửa một cờ động | `Files.setAttribute(path, "dos:hidden", true)` | Hợp đồng tên thuộc tính rõ ràng |
| Kiểm tra quyền ghi thực tế của JVM | `Files.isWritable(path)` kèm xử lý thao tác ghi thật | DOS readonly không đủ thay ACL |
| Quản lý Windows ACL | `AclFileAttributeView` (nếu hỗ trợ) | ACL là mô hình quyền riêng |
| Quản lý quyền Unix | `PosixFileAttributeView` (nếu hỗ trợ) | POSIX permission bits riêng |
| Ứng dụng chạy trên nhiều provider | Capability check + graceful fallback | Không hard-code `os.name` |

Lựa chọn giữa `DosFileAttributes` và `DosFileAttributeView` cũng là lựa chọn giữa **đọc một snapshot** và **có đối tượng cho phép đổi thuộc tính**. Đừng thêm quyền ghi metadata vào một module chỉ cần quan sát.

## 15. Checklist thực hành an toàn

1. Tạo `Path` đúng provider; đừng suy ra hỗ trợ DOS view chỉ vì OS là Windows.
2. Lấy `DosFileAttributeView` và kiểm tra `null`, hoặc gọi `Files.readAttributes` rồi xử lý `UnsupportedOperationException`.
3. Khi chỉ muốn đọc, dùng getter; không sửa cờ để “thử xem có hỗ trợ không” trên file thật.
4. Khi cần cập nhật, chỉ sửa cờ được yêu cầu và nhớ rằng setter có thể ném `IOException`.
5. Nếu sửa tạm thời, lưu cờ cũ và cố gắng khôi phục trong `finally`; thử nghiệm trên file tạm.
6. Với Read-only, Hidden, System và Archive, hiểu đúng vai trò của từng cờ, không biến chúng thành cơ chế bảo mật tự chế.
7. Định rõ xử lý symbolic link; sử dụng `NOFOLLOW_LINKS` nếu cần và provider hỗ trợ.
8. Đọc lại attrs nếu cần trạng thái sau sửa; không coi object `DosFileAttributes` cũ là live.
9. Khi truy cập nhiều file hoặc thay nhiều cờ, tính tới race và cập nhật một phần; không hứa tính nguyên tử ngoài hợp đồng API.
10. Với dữ liệu quan trọng, phân biệt DOS flag, file permissions, ACL, và chiến lược sao lưu thực sự.

## 16. Ghi nhớ cốt lõi

- **DOS attributes trên Windows** gồm bốn cờ: `readonly`, `hidden`, `system`, `archive`.
- **`DosFileAttributes`** để đọc (gồm các thuộc tính `BasicFileAttributes`); **`DosFileAttributeView`** để đọc và cập nhật.
- **`Files.getFileAttributeView(...)` có thể trả `null`** nếu view không khả dụng; đừng giả định mọi file system đều hỗ trợ DOS.
- **`Files.getAttribute/setAttribute`** dùng tên dạng `"dos:hidden"`, `"dos:readonly"`, v.v.
- **Hidden không phải bảo mật; Read-only không thay ACL; Archive không xác nhận đã backup.**
- Cần xử lý lỗi I/O, symbolic link, khác biệt provider và trạng thái thay đổi giữa các thao tác.

### Tham khảo chính thức

- [Java SE 17 — DosFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributes.html)
- [Java SE 17 — DosFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributeView.html)
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
