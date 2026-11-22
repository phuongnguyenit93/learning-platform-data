# POSIX permission và PosixFileAttributeView trong Java NIO.2

Một ứng dụng Java xử lý file có thể cần đọc quyền hiện tại, giới hạn ai được đọc/ghi một file chứa dữ liệu riêng tư, hoặc cấp quyền thực thi cho một script. Trên những filesystem hỗ trợ **POSIX file attributes**, Java NIO.2 cung cấp `PosixFilePermission`, `PosixFilePermissions`, `PosixFileAttributes` và **`PosixFileAttributeView`** để thao tác các thuộc tính này bằng API có kiểu, thay vì ghép lệnh shell `chmod`.

Tuy nhiên, không phải hệ điều hành hay filesystem nào cũng hỗ trợ giao diện POSIX. Kể cả khi có, quyền truy cập hiệu lực vẫn có thể chịu ảnh hưởng bởi chủ sở hữu, nhóm, ACL, quyền trên thư mục cha và cơ chế bảo mật của hệ thống. Bài học này chỉ ra cách **phát hiện khả năng hỗ trợ**, **đọc/ghi quyền đúng API**, **xử lý lỗi** và tránh tạo ra lỗ hổng quyền truy cập.

## 1. POSIX permission là gì?

POSIX-style permission cơ bản mô tả ba nhóm người dùng và ba loại quyền:

- **Owner (`u`):** chủ sở hữu file hoặc thư mục.
- **Group (`g`):** thành viên của nhóm sở hữu.
- **Others (`o`):** những chủ thể không thuộc hai trường hợp trên theo cơ chế phân loại thích hợp của hệ thống.
- **Read (`r`):** quyền đọc.
- **Write (`w`):** quyền ghi.
- **Execute (`x`):** quyền thực thi, hoặc quyền tìm kiếm/đi qua thư mục tùy loại đối tượng.

Một chuỗi quyền phổ biến là:

~~~text
rwxr-x---
│││││││││
││││││└┴┴─ others: --- (không có r/w/x)
│││└┴┴──── group:  r-x (đọc + thực thi)
└┴┴──────── owner:  rwx (đọc + ghi + thực thi)
~~~

Chuỗi trên có **đúng 9 ký tự**: ba ký tự đầu dành cho owner, ba ký tự tiếp theo dành cho group và ba ký tự cuối dành cho others.

Ví dụ thường gặp:

| Dạng ký tự | Dạng bát phân (octal) quen dùng | Ý nghĩa |
|---|---|---|
| `rw-------` | `0600` | Owner đọc/ghi; group và others không có quyền |
| `rw-r-----` | `0640` | Owner đọc/ghi; group chỉ đọc; others không có quyền |
| `rw-r--r--` | `0644` | Owner đọc/ghi; group và others chỉ đọc |
| `rwx------` | `0700` | Owner đọc/ghi/thực thi; hai nhóm khác không có quyền |
| `rwxr-x---` | `0750` | Owner đầy đủ; group đọc/thực thi; others không có quyền |
| `rwxr-xr-x` | `0755` | Owner đầy đủ; group và others đọc/thực thi |

Quy ước số: `r = 4`, `w = 2`, `x = 1` trong từng nhóm; ví dụ `rwx = 7`, `r-x = 5`, `--- = 0`. API `PosixFilePermissions.fromString` nhận chuỗi **9 ký tự**, không nhận trực tiếp chuỗi `"0755"`.

### Quyền trên file và thư mục có ý nghĩa khác nhau

| Quyền | File thông thường | Thư mục |
|---|---|---|
| `r` | Cho phép đọc dữ liệu file theo chính sách hệ thống | Thường cho phép liệt kê tên các mục bên trong |
| `w` | Cho phép sửa nội dung file theo chính sách hệ thống | Cùng quyền `x`, thường cho phép tạo/xóa/đổi tên mục trong thư mục |
| `x` | Cho phép thực thi file nếu định dạng và hệ thống hỗ trợ | Cho phép **search/traverse**: đi qua thư mục để truy cập mục theo tên |

Một file có quyền đọc **không bảo đảm** bạn mở được bằng đường dẫn đầy đủ nếu thiếu quyền đi qua một thư mục cha. Ngược lại, quyền xóa file thường được quyết định bởi **quyền trên thư mục chứa nó**, không đơn giản bởi bit `w` của file.

Bảng chỉ giải thích ba bộ bit quyền cơ bản. Những cơ chế khác như ACL, sticky bit, setuid/setgid, mount options và chính sách bảo mật của hệ thống có thể làm quyền hiệu lực khác với suy luận từ chín ký tự này.

## 2. Các lớp và giao diện Java liên quan

Những kiểu chính trong `java.nio.file.attribute`:

| API | Nhiệm vụ |
|---|---|
| `PosixFilePermission` | Enum gồm 9 giá trị quyền cho owner, group, others |
| `PosixFilePermissions` | Chuyển đổi giữa chuỗi như `rw-r-----` và `Set<PosixFilePermission>`; tạo `FileAttribute` để cấp quyền lúc tạo file |
| `PosixFileAttributes` | Gói thông tin file kiểu POSIX: `permissions()`, `owner()`, `group()` và thuộc tính cơ bản kế thừa |
| `PosixFileAttributeView` | View để **đọc và sửa** thuộc tính POSIX của đối tượng file cụ thể |
| `Files.getPosixFilePermissions` | Phương thức tiện ích đọc bộ quyền |
| `Files.setPosixFilePermissions` | Phương thức tiện ích ghi bộ quyền |
| `Files.getFileAttributeView` | Lấy đối tượng view nếu provider hỗ trợ loại view tương ứng |

`PosixFilePermission` bao gồm các hằng:

~~~java
OWNER_READ
OWNER_WRITE
OWNER_EXECUTE
GROUP_READ
GROUP_WRITE
GROUP_EXECUTE
OTHERS_READ
OTHERS_WRITE
OTHERS_EXECUTE
~~~

Các tên trên là **hằng enum**, không phải biến tự do. Khi dùng trong Java phải có kiểu hoặc static import, ví dụ `PosixFilePermission.OWNER_READ`.

Cơ chế qua view:

~~~text
Path --------------------------> Files.getFileAttributeView(...)
                                      |
                                      v
                              PosixFileAttributeView
                                |       |       |
                                |       |       +-- setGroup(...)
                                |       +---------- setPermissions(...)
                                +------------------ readAttributes()
                                      |
                                      v
                              PosixFileAttributes
                               owner / group / permissions
~~~

Một view là **đối tượng truy cập thuộc tính của một path**, không phải bản sao nội dung file. Khi gọi `readAttributes()`, chương trình yêu cầu filesystem cung cấp một bộ thuộc tính tại thời điểm đọc.

## 3. Chuyển đổi chuỗi quyền bằng `PosixFilePermissions`

Khai báo bộ quyền từ chuỗi:

~~~java
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-r-----");
System.out.println(PosixFilePermissions.toString(permissions));
// rw-r-----
~~~

Đây là **đoạn minh họa** có thể đặt trong `main`; nó chỉ chuyển đổi dữ liệu trong bộ nhớ, **không tự đổi quyền của bất kỳ file nào**.

Bạn cũng có thể xây bộ quyền trực tiếp:

~~~java
Set<PosixFilePermission> privateReadWrite = Set.of(
        PosixFilePermission.OWNER_READ,
        PosixFilePermission.OWNER_WRITE);
~~~

Trong `Set` trên chỉ có hai quyền của owner, tương ứng `rw-------`. Hai cách biểu diễn là tương đương về **chín permission bit cơ bản**.

Các ví dụ sai:

~~~java
// Không hợp lệ cho fromString: phải có đúng 9 ký tự rwx/-.
PosixFilePermissions.fromString("0644");
PosixFilePermissions.fromString("rwx");
~~~

Đây là các **dòng minh họa lỗi**, không nên cho vào chương trình chạy thật. `fromString` ném `IllegalArgumentException` khi chuỗi có cấu trúc/ký tự không hợp lệ.

Không được nhầm `PosixFilePermissions.toString(permissions)` với `permissions.toString()` của `Set`: một bên cho chuỗi 9 ký tự quyền Unix quen thuộc; một bên chỉ là cách biểu diễn tập enum theo Java.

## 4. Kiểm tra hệ thống có hỗ trợ POSIX không

`PosixFileAttributeView` chỉ khả dụng khi **file system provider** hỗ trợ. Một mã chạy ổn trên Linux với filesystem hỗ trợ POSIX có thể không chạy theo cùng cách trên một provider mặc định của Windows hoặc trên filesystem đặc biệt.

Cách kiểm tra trực tiếp cho một path:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;

PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);

if (view == null) {
    System.out.println("Không có POSIX attribute view.");
} else {
    System.out.println("Có thể thử đọc thuộc tính POSIX.");
}
~~~

Đây là **đoạn minh họa**, `path` phải có giá trị phù hợp. Khi provider **không hỗ trợ** view được yêu cầu, `getFileAttributeView` trả `null`. Việc lấy được view **không bảo đảm** thao tác đọc hoặc sửa quyền sau đó luôn thành công: file có thể mất, quyền bị từ chối hoặc provider gặp lỗi I/O.

Cách kiểm tra khả năng ở cấp filesystem store:

~~~java
boolean supported = Files.getFileStore(path)
        .supportsFileAttributeView("posix");
~~~

Cần xử lý `IOException` khi truy cập file store. Đối với thao tác thật trên một file, lấy view trực tiếp tại path rồi xử lý lỗi tại bước đọc/ghi thường rõ hơn.

**Lưu ý quan trọng về portability:** Không tự diễn giải tên file hoặc hệ điều hành thành bảo đảm có POSIX view. Một nhà cung cấp filesystem tùy biến, ổ mạng, file ZIP hoặc quyền filesystem khác có thể có mức hỗ trợ không giống hệ điều hành nền.

## 5. Đọc permission bằng `Files` hoặc bằng `PosixFileAttributeView`

### Cách ngắn: `Files.getPosixFilePermissions`

~~~java
Set<PosixFilePermission> current =
        Files.getPosixFilePermissions(path);

System.out.println(PosixFilePermissions.toString(current));
~~~

Đây là **đoạn minh họa**; cần các import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.attribute.*`, `java.util.Set` và xử lý `IOException`. `Files.getPosixFilePermissions(path)` có thể ném `UnsupportedOperationException` nếu provider không hỗ trợ thuộc tính POSIX.

### Cách qua view: `readAttributes()`

~~~java
PosixFileAttributeView view =
        Files.getFileAttributeView(path, PosixFileAttributeView.class);

if (view != null) {
    PosixFileAttributes attrs = view.readAttributes();
    Set<PosixFilePermission> permissions = attrs.permissions();
    System.out.println(PosixFilePermissions.toString(permissions));
    System.out.println("Owner: " + attrs.owner().getName());
    System.out.println("Group: " + attrs.group().getName());
}
~~~

Đây là **đoạn minh họa**. `readAttributes()` trả một đối tượng `PosixFileAttributes`, trong đó `owner()` và `group()` là các đối tượng `UserPrincipal` và `GroupPrincipal`, không phải những số UID/GID được Java bảo đảm ở mọi provider.

Ưu điểm của view là có thể đọc cùng lúc nhiều thuộc tính có liên quan thay vì gọi các phương thức riêng nhiều lần. Nhưng đừng coi snapshot thuộc tính là khóa file: các thuộc tính có thể thay đổi sau khi đã đọc.

## 6. Ghi permission: `Files.setPosixFilePermissions` và `view.setPermissions`

Khi muốn đặt quyền cơ bản cho file **do ứng dụng sở hữu/quản lý**, có thể gọi:

~~~java
Set<PosixFilePermission> restricted =
        PosixFilePermissions.fromString("rw-------");

Files.setPosixFilePermissions(path, restricted);
~~~

Hoặc qua view:

~~~java
PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);

if (view == null) {
    throw new UnsupportedOperationException("Không hỗ trợ POSIX");
}
view.setPermissions(restricted);
~~~

Các đoạn trên cần đặt trong phương thức có import và xử lý `IOException`. `setPermissions` cập nhật tập **chín permission bit cơ bản** của file, không phải một cơ chế cấp quyền trừu tượng hoạt động đồng nhất ở mọi hệ thống.

Các điểm cần hiểu:

1. `Set<PosixFilePermission>` là tập các quyền cần có, không phải lệnh “thêm từng quyền vào tập hiện tại” theo mặc định.
2. Nếu bạn truyền tập chỉ chứa `OWNER_READ`, mọi bit quyền khác trong mô hình POSIX cơ bản có thể bị **loại bỏ**. Hãy kiểm tra nhu cầu của ứng dụng trước khi cập nhật.
3. Muốn **thêm đúng một bit** mà giữ các bit khác, cần đọc quyền hiện tại, tạo một tập có thể sửa, thêm enum tương ứng, rồi ghi lại. Đây là thao tác đọc–sửa–ghi có thể gặp race khi nhiều tiến trình cùng sửa quyền.
4. Chỉ nên chỉnh sửa quyền đối với đối tượng bạn được phép quản lý; hệ thống có thể ném `IOException` hoặc `SecurityException` tùy provider và môi trường.
5. Đừng mặc định gọi `setPosixFilePermissions` trên Windows/native provider không hỗ trợ: `UnsupportedOperationException` là một kết quả cần xử lý.
6. Việc đặt quyền thay đổi metadata của đối tượng có thật, không phải thay đổi nội dung file; tuy nhiên nó có thể ảnh hưởng trực tiếp đến khả năng truy cập của các tiến trình khác.

### Thêm quyền mà không xóa quyền khác

~~~java
Set<PosixFilePermission> updated = new HashSet<>(
        Files.getPosixFilePermissions(path));

updated.add(PosixFilePermission.GROUP_READ);
Files.setPosixFilePermissions(path, updated);
~~~

Đây là **đoạn minh họa** với import `java.util.HashSet`, `java.nio.file.*` và `java.nio.file.attribute.*`. Nếu chương trình chỉ muốn thử sửa quyền trong bài tập, dùng **tệp tạm do chính mình tạo**, không dùng tệp cấu hình hoặc dữ liệu thật của người khác.

### Đặt owner/group không giống đặt permission

`PosixFileAttributeView` còn có phương thức như `setGroup(GroupPrincipal)` và kế thừa thao tác đổi owner qua `setOwner(UserPrincipal)`. Đổi chủ sở hữu hoặc nhóm thường có yêu cầu đặc quyền riêng; không thể suy ra rằng sửa được permission thì chắc chắn đổi được owner/group.

**Quyền owner, group và các bit permission là những thuộc tính liên quan nhưng độc lập.** Khi thay owner/group, tác động quyền hiệu lực có thể thay đổi ngay cả khi chuỗi `rwxr-x---` không đổi.

## 7. Ví dụ Java 17 hoàn chỉnh: chỉ thay quyền tệp tạm

Chương trình sau tạo **một file tạm**, kiểm tra `PosixFileAttributeView`, đặt `rw-------` nếu view có sẵn và đọc lại để xác minh. Nó không đụng vào quyền của file thực thuộc người học.

Lưu thành **`PosixPermissionsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixPermissionsDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("posix-demo-", ".txt");

        try {
            PosixFileAttributeView view = Files.getFileAttributeView(
                    file, PosixFileAttributeView.class,
                    LinkOption.NOFOLLOW_LINKS);

            if (view == null) {
                System.out.println("POSIX view available: false");
            } else {
                System.out.println("POSIX view available: true");

                Set<PosixFilePermission> requested =
                        PosixFilePermissions.fromString("rw-------");
                view.setPermissions(requested);

                PosixFileAttributes attrs = view.readAttributes();
                System.out.println("Requested: "
                        + PosixFilePermissions.toString(requested));
                System.out.println("Read back: "
                        + PosixFilePermissions.toString(attrs.permissions()));
                System.out.println("Exact match: "
                        + attrs.permissions().equals(requested));

                Set<PosixFilePermission> viaFiles =
                        Files.getPosixFilePermissions(file);
                System.out.println("Files getter agrees: "
                        + viaFiles.equals(attrs.permissions()));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 PosixPermissionsDemo.java
java PosixPermissionsDemo
~~~

Trên filesystem hỗ trợ POSIX thông thường, khi người chạy có quyền sửa permission và provider chấp nhận yêu cầu, kết quả dự kiến:

~~~text
POSIX view available: true
Requested: rw-------
Read back: rw-------
Exact match: true
Files getter agrees: true
~~~

Nếu provider **không hỗ trợ** `PosixFileAttributeView`, chương trình in:

~~~text
POSIX view available: false
~~~

Các trường hợp lỗi quyền, lỗi I/O hoặc filesystem đặc biệt có thể khiến chương trình ném ngoại lệ thay vì in đầy đủ các dòng của nhánh hỗ trợ. Đó là hành vi cần xử lý trong ứng dụng thực; không nên che giấu bằng cách âm thầm bỏ qua vấn đề bảo mật.

**Giải thích:**

1. `Files.createTempFile` tạo một file mới và trả đường dẫn tới nó. Ví dụ chỉ thay quyền trên file mới này.
2. `Files.getFileAttributeView(file, PosixFileAttributeView.class, NOFOLLOW_LINKS)` yêu cầu view để làm việc với **chính path** mà không theo symbolic link ở bước tra cứu thuộc tính. Vì file do chương trình vừa tạo là file thông thường, nhánh symlink không tham gia.
3. Nếu view không có, chương trình **không thử gọi `setPermissions`**.
4. Nếu có, `fromString("rw-------")` tạo tập gồm đúng `OWNER_READ` và `OWNER_WRITE`, rồi `view.setPermissions` yêu cầu cập nhật quyền.
5. `view.readAttributes().permissions()` đọc lại tập quyền, chuyển sang chuỗi và so sánh bằng `Set.equals`.
6. `Files.getPosixFilePermissions(file)` là phương thức tiện ích đọc quyền POSIX. Trên file không thay đổi đồng thời trong ví dụ, kết quả khớp với view.
7. Khối `finally` xóa file tạm dù nhánh xử lý thành công hay ném ngoại lệ. Nếu xóa file cũng thất bại, Java có thể báo `IOException` cho bước dọn dẹp; đây là một yếu tố cần theo dõi trong mã sản xuất.

**Lưu ý về kiểm thử:** chương trình chỉ kiểm tra rằng provider **báo đã lưu các permission bit được yêu cầu**. Nó không kiểm thử hành vi thực tế của từng user/group, và không bảo đảm mọi hệ thống thực thi kiểm soát truy cập giống nhau.

## 8. `PosixFileAttributeView` và symbolic link

Symbolic link là một mục trong filesystem trỏ tới mục khác. Nếu path `link` là symlink trỏ tới `target`, cần quyết định muốn thao tác thuộc tính của **đích** hay của **chính liên kết**.

Theo mặc định, nhiều lời gọi Files đọc thuộc tính **theo symbolic link** tới đích. `LinkOption.NOFOLLOW_LINKS` cho phép yêu cầu **không theo liên kết**:

~~~java
PosixFileAttributeView noFollowView = Files.getFileAttributeView(
        link,
        PosixFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
~~~

Đây là **đoạn minh họa**, trong đó `link` là `Path` đã có. Một số filesystem **không cho phép đọc/đổi permission của bản thân symlink theo cùng cách với file đích**; không được suy ra rằng `NOFOLLOW_LINKS` khiến mọi thao tác `setPermissions` trên symlink đều được hỗ trợ.

Nếu không chủ đích thay quyền của **file target**, hãy xác định link policy trước khi gọi. Đây là vấn đề bảo mật: một kẻ khác có thể thay thế link trong khoảng thời gian từ khi ứng dụng kiểm tra path đến khi sửa quyền hoặc mở file (**time-of-check/time-of-use**). `NOFOLLOW_LINKS` ở một bước không tự loại bỏ mọi race ở các bước khác.

Khi xử lý đường dẫn do người dùng không tin cậy cung cấp, nên xác định thư mục gốc được phép, quyền truy cập và chiến lược mở file an toàn ở cấp nền tảng. **Không biến thao tác chỉnh permission thành cơ chế tự động “sửa mọi lỗi truy cập”**.

## 9. Quyền khởi tạo lúc tạo file và `umask`

Một vấn đề thường gặp là tạo file xong rồi mới gọi `setPosixFilePermissions`. Nếu dữ liệu nhạy cảm đã được ghi trước lúc siết quyền, có thể tồn tại một khoảng thời gian file có quyền rộng hơn mong muốn.

Khi provider hỗ trợ POSIX, Java cho phép chỉ định permission **ngay trong thao tác tạo** thông qua `FileAttribute`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

FileAttribute<Set<PosixFilePermission>> privateFile =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rw-------"));

Path newFile = Files.createFile(path, privateFile);
~~~

Đây là **đoạn minh họa**, `path` phải trỏ tới file chưa tồn tại và caller xử lý `IOException`. Lựa chọn này hữu ích nếu **bảo mật tại thời điểm tạo** là yêu cầu. Khi file đã tồn tại, `Files.createFile` không ghi đè file đó mà thất bại.

Tương tự, `Files.createTempFile` có overload nhận file attributes, và có thể dùng `asFileAttribute` theo chính sách của bạn. Tuy nhiên:

- Tạo file với attributes POSIX trên provider không hỗ trợ có thể thất bại.
- Quyền thực tế khi tạo có thể bị giới hạn bởi chính sách filesystem và **umask** của môi trường; cần đọc lại thuộc tính nếu ứng dụng yêu cầu xác minh.
- Việc chỉ định quyền khi tạo không thay thế kiểm tra owner/group, ACL, quyền của thư mục cha hoặc cơ chế bảo vệ dữ liệu nhạy cảm khác.
- Không viết chuỗi mật khẩu/dữ liệu riêng tư vào một file “tạm mặc định” rồi chỉ siết quyền ở bước cuối và giả định không có cửa sổ rủi ro.

**Umask** là cơ chế POSIX thường dùng để loại bớt những bit quyền được yêu cầu lúc tạo mới. Ví dụ umask `022` có thể khiến file mặc định được tạo với quyền ít hơn so với yêu cầu rộng hơn. Không coi umask là một thuộc tính mà `PosixFilePermission` tự động mô hình hóa trong tập 9 enum.

## 10. Quyền POSIX, ACL và quyền truy cập thực tế

Chín bit `rwxrwxrwx` chỉ là mô hình cơ bản. Một ứng dụng có thể gặp:

- **POSIX ACL:** điều khoản quyền bổ sung/ghi đè theo từng user hoặc group, tùy filesystem và cách diễn giải quyền hiệu lực.
- **Windows ACL:** mô hình quyền khác, không nên ép vào chuỗi 9 ký tự như thể đầy đủ.
- **Sticky bit** trên một số thư mục; **setuid/setgid** trên file hoặc directory; không được biểu diễn trong chính `Set<PosixFilePermission>` chín giá trị.
- **Quyền root/superuser**, capabilities hoặc chính sách an ninh bắt buộc có thể ảnh hưởng khả năng mở, đọc, sửa hay xóa.
- **Thuộc tính thư mục cha** và trạng thái mount (ví dụ filesystem chỉ đọc) ảnh hưởng thao tác dù file có `rw-------`.
- **Cache và thay đổi đồng thời** làm thuộc tính đọc được tại thời điểm trước không còn phản ánh trạng thái ở thời điểm dùng.

Trên provider hỗ trợ `AclFileAttributeView`, API khác có thể cho thông tin ACL. Không được kết luận “không có quyền” hoặc “chắc chắn có quyền” chỉ từ một thao tác kiểm tra đơn lẻ mà bỏ qua lỗi khi thực sự mở hoặc ghi dữ liệu.

`Files.isReadable(path)`, `Files.isWritable(path)` và `Files.isExecutable(path)` là các kiểm tra tiện ích nhưng không phải hàng rào bảo mật bất biến; file hoặc quyền có thể thay đổi ngay sau khi kiểm tra. Nên thử thao tác thật trong khối xử lý lỗi phù hợp với nghiệp vụ thay vì chỉ dựa vào kiểm tra trước.

## 11. Xử lý lỗi và portability trong ứng dụng thật

| Tình huống | Khả năng xảy ra | Phản ứng đúng |
|---|---|---|
| View POSIX không có | `getFileAttributeView` trả `null` | Tránh dereference; chọn đường xử lý tương thích hoặc thông báo không hỗ trợ |
| Truy cập POSIX attribute bằng Files API nhưng provider không hỗ trợ | `UnsupportedOperationException` | Không ép sửa quyền; dùng cơ chế hợp đồng của provider |
| File không tồn tại hoặc bị xóa đồng thời | `IOException`, ví dụ `NoSuchFileException` | Báo lỗi hoặc retry có kiểm soát |
| Không có quyền đọc/sửa thuộc tính | `IOException` hay `SecurityException` tùy môi trường | Báo rõ quyền hạn, không tự mở rộng quyền bừa bãi |
| Chuỗi permission sai định dạng | `IllegalArgumentException` từ `fromString` | Kiểm tra đúng 9 ký tự, chỉ dùng `rwx-` |
| Thao tác trên symlink | Có thể đi theo link hoặc không, tùy option | Xác định chính xác file đích hay link là đối tượng cần sửa |
| FileStore có view nhưng path không dùng được | Lỗi thuộc tính cụ thể vẫn có thể xảy ra | Thử thao tác trong `try/catch` và xử lý lỗi thực tế |
| Đổi quyền giữa hai tiến trình | Có thể mất cập nhật trong chuỗi đọc–sửa–ghi | Cần điều phối khi ứng dụng có concurrent writers |

Mẫu helper kiểm tra view trước khi đọc:

~~~java
static String permissionText(Path file) throws IOException {
    PosixFileAttributeView view = Files.getFileAttributeView(
            file, PosixFileAttributeView.class);
    if (view == null) {
        throw new UnsupportedOperationException(
                "POSIX attributes are unavailable for " + file);
    }
    return PosixFilePermissions.toString(
            view.readAttributes().permissions());
}
~~~

Đây là **phương thức minh họa** trong một lớp Java với các import `java.io.IOException`, `java.nio.file.*`, `java.nio.file.attribute.*`. Caller nhận được chuỗi 9 ký tự nếu đọc thành công; nếu không, lỗi được phân biệt thay vì trả về một giá trị giả như `rwxrwxrwx`.

Một hệ thống đa nền tảng có thể cung cấp **giao diện trừu tượng mức ứng dụng**: nếu POSIX có sẵn thì dùng permission view; nếu không, chọn API quyền thích hợp của provider hoặc dừng với thông báo rõ. Đừng âm thầm biến yêu cầu bảo vệ file thành “bỏ qua chỉnh quyền” trên nền tảng không hỗ trợ nếu mức bảo mật đó là điều kiện bắt buộc.

## 12. Lỗi phổ biến

| Nhầm lẫn | Hậu quả | Cách làm đúng |
|---|---|---|
| Cho rằng `PosixFileAttributeView` luôn có trên mọi máy chạy Java | `null`/unsupported trên provider không tương thích | Kiểm tra hỗ trợ, có chiến lược thay thế |
| Dùng `"755"` cho `fromString` | Sai định dạng API | Dùng `"rwxr-xr-x"` |
| Tưởng `getPosixFilePermissions` đã sửa quyền | Chỉ đọc metadata | Dùng `setPosixFilePermissions` hoặc `view.setPermissions` |
| Tưởng `setPermissions` là “thêm các quyền mới” | Có thể xóa các bit không nằm trong tập mới | Xây tập quyền đầy đủ trước khi set |
| Đặt `rwxrwxrwx` để “sửa lỗi không truy cập được” | Mở quyền rộng nguy hiểm, chưa chắc giải quyết được lỗi | Xác định owner/group, thư mục cha, ACL và nhu cầu thực |
| Coi `r` của thư mục như quyền đi qua thư mục | Trên POSIX, duyệt theo tên thường cần `x` | Phân biệt ý nghĩa r/w/x file và directory |
| Quên chính sách symlink | Sửa nhầm quyền file khác | Chọn follow/nofollow phù hợp, chống race |
| Tin rằng có view thì chắc chắn set thành công | Permission change có thể bị cấm | Bắt lỗi I/O và không đoán |
| Ghi bí mật trước rồi mới siết quyền | Có thể có khoảng thời gian file lộ quyền rộng | Chỉ định thuộc tính khi tạo nếu cần |
| Tin rằng 9 bit đủ mô tả quyền hiệu lực | ACL và cơ chế hệ thống còn ảnh hưởng | Kết hợp kiểm tra thực tế và policy |
| Không phân biệt quyền file và quyền thư mục cha | Có thể không truy cập dù file có r/w | Xem đường đi và directory traversal |
| Bắt mọi lỗi rồi im lặng | Ứng dụng tưởng đã bảo vệ dữ liệu | Báo lỗi và dừng nếu bảo mật là bắt buộc |

## 13. Bài tập tự kiểm tra

**Câu 1.** Chuỗi `rw-r-----` có nghĩa gì? Tương ứng dạng bát phân nào?

> Owner được đọc và ghi, group chỉ được đọc, others không có quyền. Đó là `0640` trong ký hiệu octal quen dùng.

**Câu 2.** Vì sao `Files.getFileAttributeView(file, PosixFileAttributeView.class)` có thể trả `null`?

> Vì filesystem provider của file không hỗ trợ view POSIX. Phải kiểm tra kết quả trước khi gọi `readAttributes` hay `setPermissions`.

**Câu 3.** Muốn lấy quyền hiện tại từ `PosixFileAttributes`, dùng phương thức nào? Muốn đổi quyền, dùng gì?

> Dùng `view.readAttributes().permissions()` để lấy tập quyền. Để đổi quyền, dùng `view.setPermissions(set)` hoặc `Files.setPosixFilePermissions(file, set)`.

**Câu 4.** Có một file đang có `rw-r-----`. Nếu gọi `setPermissions(fromString("rw-------"))` thì có còn `GROUP_READ` không?

> **Không** trong tập chín quyền cơ bản: tập mới yêu cầu chỉ owner đọc/ghi. `GROUP_READ` không còn trong tập được đặt.

**Câu 5.** Khi muốn tạo file bí mật, vì sao truyền `PosixFilePermissions.asFileAttribute` vào `Files.createFile` có lợi hơn so với chỉnh quyền sau khi ghi dữ liệu?

> Vì có thể yêu cầu quyền phù hợp **ngay tại thời điểm tạo**, tránh khoảng hở giữa tạo/ghi và siết quyền. Vẫn cần tính đến provider, umask, ACL và chính sách hệ thống.

**Câu 6.** Trong một thư mục, có quyền `r` nhưng thiếu `x`. Có chắc ứng dụng mở được file con theo đường dẫn tên file không?

> Không. Quyền `x` trên thư mục thường cần cho việc đi qua/tìm mục theo tên. `r` của thư mục không thay thế `x`.

**Câu 7.** `NOFOLLOW_LINKS` có khiến mọi hệ điều hành đều cho đổi permission của một symbolic link không?

> Không. Nó chỉ yêu cầu không theo symbolic link trong bước truy cập thuộc tính; khả năng đọc/sửa metadata của bản thân link còn phụ thuộc provider/filesystem.

**Câu 8.** Có quyền `rw-------` trên file, vậy ứng dụng chắc chắn có thể ghi file bằng mọi cách không?

> Không. Quyền hiệu lực còn tùy danh tính tiến trình, quyền trên thư mục cha, ACL, trạng thái filesystem, mount policy và thay đổi đồng thời. Phải xử lý lỗi khi thực hiện I/O.

## Ghi nhớ

- **`PosixFilePermission`** là enum cho chín quyền owner/group/others × read/write/execute.
- **`PosixFilePermissions`** giúp chuyển giữa `"rwxr-x---"` và `Set<PosixFilePermission>`, hoặc cấp thuộc tính lúc tạo file.
- **`PosixFileAttributeView`** cho phép đọc thuộc tính POSIX và sửa quyền, owner, group khi hệ thống hỗ trợ và caller có đủ quyền.
- **`Files.getPosixFilePermissions` / `Files.setPosixFilePermissions`** là hai phương thức tiện ích cho các thao tác thông dụng.
- **Không mặc định POSIX luôn khả dụng**; kiểm tra view, xử lý `IOException` / `UnsupportedOperationException` và tôn trọng provider.
- **Chín bit quyền không phải toàn bộ mô hình bảo mật**. Hãy hiểu permission trên file/thư mục, ACL, symbolic link, umask và quyền của môi trường trước khi thao tác.

**Tài liệu tham khảo:** [Java SE 17 — `PosixFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html), [`PosixFilePermission`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermission.html), [`PosixFilePermissions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html), [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).