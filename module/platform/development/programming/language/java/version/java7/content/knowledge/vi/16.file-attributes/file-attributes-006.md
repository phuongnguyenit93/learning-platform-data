# Quyền POSIX theo người sở hữu, nhóm và bên khác trong Java

**Chủ đề:** Java 7 — Thuộc tính tệp  
**Bài học:** Quyền POSIX theo người sở hữu, nhóm và bên khác  
**Môi trường thực hành:** Java 17+; sử dụng `java.nio.file.attribute.PosixFilePermission`, `PosixFilePermissions`, `PosixFileAttributes`, `PosixFileAttributeView` và `java.nio.file.Files`. Các API NIO.2 này được giới thiệu từ Java 7 và **vẫn áp dụng trong Java hiện hành**.

## 1. Tại sao cần hiểu POSIX permissions?

Khi một ứng dụng tạo tệp báo cáo, khóa bí mật, ảnh tải lên hoặc thư mục chia sẻ, nó cần phân biệt **ai có quyền đọc, ghi và thực thi/truy cập**. Trên những filesystem hỗ trợ mô hình POSIX, chín bit quyền phổ biến được chia thành ba lớp:

- **Owner (người sở hữu):** tài khoản sở hữu entry.
- **Group (nhóm sở hữu):** nhóm được gắn với entry; quyền áp dụng cho chủ thể thuộc nhóm khi điều kiện kiểm tra quyền phù hợp.
- **Others (bên khác):** những chủ thể không thuộc hai lớp bên trên theo phép kiểm tra POSIX thông thường.

Mỗi lớp có ba quyền `r` (*read*), `w` (*write*) và `x` (*execute/search*). Đọc đúng cấu trúc này giúp tránh vô tình làm tệp bí mật có thể đọc bởi người dùng khác, hoặc làm thư mục dùng chung thiếu quyền truy cập cần thiết.

**Quy tắc quan trọng:** chín bit `rwx` là **mô hình quyền POSIX cơ bản**, không phải một quyết định ủy quyền hoàn chỉnh cho mọi OS, filesystem hoặc quy trình. Quyền thực tế còn bị tác động bởi danh tính tiến trình, nhóm bổ sung, ACL, quyền trên thư mục cha, mount policy, symlink và trạng thái hệ thống.

Ví dụ thường gặp:

```text
rwxr-x---
│││││││││
││││││└┴┴── others: --- (không quyền)
│││└┴┴───── group:  r-x (đọc, thực thi/search)
└┴┴──────── owner:  rwx (đọc, ghi, thực thi/search)
```

Biểu diễn này có **9 ký tự**. Một dòng hiển thị kiểu `ls -l` trên Unix còn có ký tự đầu thể hiện loại entry (`-` cho file thường, `d` cho thư mục...) và có thể hiển thị thông tin ACL/special bits. **`PosixFilePermissions.toString(...)` chỉ trả chuỗi 9 ký tự** trong phạm vi quyền cơ bản, không phải bản sao toàn bộ kết quả `ls -l`.

## 2. Ba lớp quyền: owner, group, others

### 2.1. Owner không đồng nghĩa người đang chạy ứng dụng

Một tệp có **owner** là một `UserPrincipal` của filesystem. Process Java có thể chạy dưới danh tính khác với owner, kể cả khi source code là cùng một chương trình.

Nếu process đang chạy dưới owner, các bit của owner là lớp được xét theo logic quyền POSIX cơ bản; **không** gộp owner và group bằng phép OR chỉ vì owner cũng là thành viên của group. Với identity không phải owner nhưng thuộc owning group, group class có vai trò; nếu không thuộc hai trường hợp, others class được xét.

Các file ACL và cơ chế quyền bổ sung có thể mở rộng/điều chỉnh quy tắc đơn giản này; không nên tự mô phỏng kết quả truy cập thực tế chỉ bằng một biểu thức `contains(OWNER_READ) || contains(GROUP_READ)`.

### 2.2. Group là nhóm *sở hữu tệp*, không phải nhóm tùy ý trong ứng dụng

Trong `PosixFileAttributes`:

- `owner()` trả về `UserPrincipal` đại diện owner.
- `group()` trả về `GroupPrincipal` đại diện owning group.
- `permissions()` trả về `Set<PosixFilePermission>` biểu diễn chín quyền.

Một tiến trình có thể có **primary group** và **supplementary groups**; việc khớp nhóm thuộc cơ chế danh tính/quyền của hệ điều hành. Thay một bit `GROUP_READ` **không tự đổi** nhóm sở hữu, không tạo user mới và không đưa user vào nhóm.

**Group-owner và ACL entries là các khái niệm khác nhau.** Một ACL có thể cấp quyền cho nhiều user/group khác, trong khi mô hình `owner/group/others` đơn giản chỉ nêu một nhóm sở hữu.

### 2.3. Others không có nghĩa “Internet công khai”

`OTHERS_READ` là bit quyền filesystem cho lớp others trong môi trường xét quyền POSIX, **không trực tiếp mở một file ra Internet**. Nhưng trên hệ thống nhiều tài khoản, container có volume chia sẻ hoặc server lưu dữ liệu nhạy cảm, bật `OTHERS_READ` có thể làm nhiều chủ thể cục bộ đọc được nội dung không nên thấy.

Ngược lại, bỏ mọi bit others cũng **không phải** cơ chế bảo vệ dữ liệu đủ mạnh nếu ứng dụng dùng cùng tài khoản với tiến trình khác, dữ liệu bị lộ qua API, ACL khác cho phép truy cập hoặc hệ thống có đặc quyền cao.

## 3. Ba quyền r, w, x có ý nghĩa khác nhau trên file và directory

Đây là phần rất dễ hiểu nhầm khi chuyển từ cách nhìn file sang thư mục.

| Quyền | File thường | Directory |
| --- | --- | --- |
| `r` — read | Cho phép đọc nội dung file theo cơ chế quyền áp dụng | Cho phép **liệt kê tên các entry** trong directory theo quy tắc hệ thống |
| `w` — write | Cho phép sửa/ghi nội dung file theo quyền áp dụng | Liên quan khả năng **tạo, xóa, đổi tên entry** trong directory, thường cần đồng thời `x` |
| `x` — execute/search | Cho phép thực thi file khi định dạng/hệ thống cho phép | Cho phép **đi xuyên/tra cứu thành phần tên** qua directory; rất quan trọng để mở file ở bên trong |

**Ví dụ:** directory có quyền `r--` nhưng không có `x` có thể cho phép liệt kê một số tên tùy hệ thống nhưng không đủ để truy cập nội dung entry theo pathname. Một directory có `--x` có thể cho phép đi xuyên nếu đã biết tên entry nhưng không cho liệt kê đầy đủ danh sách tên.

Để **tạo/xóa một entry trong directory**, thông thường cần quyền `w` **và** `x` trên directory cha, cùng các ràng buộc khác (sticky bit, ACL, chính sách bảo mật). Quyền `w` trên file **không quyết định một mình** việc có thể xóa tên file khỏi directory hay không.

Nếu file có quyền `rwx------` thì owner được biểu diễn là có read/write/execute; điều đó không bảo đảm chạy được file nếu nó không phải định dạng thực thi phù hợp, không có interpreter hoặc mount có `noexec`. Nếu directory có `rwx------`, `x` có nghĩa *search/traverse*, không phải “chạy thư mục”.

### 3.1. Các ví dụ đọc nhanh

| Chuỗi quyền | Octal | Ý nghĩa theo lớp |
| --- | --- | --- |
| `rw-------` | `600` | Owner đọc/ghi; group và others không có bit nào |
| `rwx------` | `700` | Owner đủ r/w/x; group/others không có |
| `rw-r-----` | `640` | Owner đọc/ghi; group chỉ đọc; others không có |
| `rwxr-x---` | `750` | Owner r/w/x; group r/x; others không có |
| `rwxr-xr-x` | `755` | Owner r/w/x; group và others r/x |
| `rw-r--r--` | `644` | Owner đọc/ghi; group/others chỉ đọc |
| `---------` | `000` | Không bật bit r/w/x nào trong chín bit cơ bản |

**Cảnh báo:** `755` thường có ý nghĩa hợp lý trên một số directory công khai/traversable, nhưng không nên chọn làm quyền mặc định cho **file bí mật**. `644` là mode dễ gặp ở file văn bản không bí mật trên Unix, song không phải policy nên áp dụng cho mọi tệp trong ứng dụng.

## 4. Java biểu diễn chính xác chín quyền POSIX như thế nào?

`java.nio.file.attribute.PosixFilePermission` là enum có đúng chín giá trị sau:

```text
OWNER_READ       OWNER_WRITE       OWNER_EXECUTE
GROUP_READ       GROUP_WRITE       GROUP_EXECUTE
OTHERS_READ      OTHERS_WRITE      OTHERS_EXECUTE
```

Khi viết Java, đừng dùng `FilePermission` trong `java.io` để thay thế. `java.io.FilePermission` là kiểu liên quan mô hình permission/security của Java, **không phải enum chín bit POSIX**. Cũng không nên dùng `File.canRead()` hay `File.canWrite()` để suy ngược đầy đủ chín bit, vì chúng chỉ cung cấp phép kiểm tra có giới hạn theo môi trường thực thi.

Các API chuyển đổi trong `PosixFilePermissions`:

- `fromString("rwxr-x---")`: phân tích chính xác chuỗi chín ký tự thành `Set<PosixFilePermission>`.
- `toString(perms)`: trả lại chuỗi chín ký tự chuẩn.
- `asFileAttribute(perms)`: chuyển tập quyền thành `FileAttribute<Set<PosixFilePermission>>` để truyền khi tạo file/directory.

### 4.1. Ví dụ runnable: từ chuỗi 9 bit sang enum

Tạo file `PosixModeBasicsDemo.java`:

```java
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixModeBasicsDemo {
    public static void main(String[] args) {
        Set<PosixFilePermission> permissions =
                PosixFilePermissions.fromString("rwxr-x---");

        System.out.println(
                "mode="
                + PosixFilePermissions.toString(permissions));
        System.out.println(
                "owner-write="
                + permissions.contains(
                    PosixFilePermission.OWNER_WRITE));
        System.out.println(
                "group-execute="
                + permissions.contains(
                    PosixFilePermission.GROUP_EXECUTE));
        System.out.println(
                "others-read="
                + permissions.contains(
                    PosixFilePermission.OTHERS_READ));
        System.out.println(
                "enabled-bits=" + permissions.size());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixModeBasicsDemo.java
java PosixModeBasicsDemo
```

**stdout chính xác:**

```text
mode=rwxr-x---
owner-write=true
group-execute=true
others-read=false
enabled-bits=5
```

Đây là **thao tác trên giá trị enum trong bộ nhớ**, nên chạy được ngay cả trên Windows không cung cấp `PosixFileAttributeView` cho filesystem. Nó **không đổi quyền file nào**.

Tập quyền chứa 5 enum: owner có r/w/x (3), group có r/x (2), others không có quyền (0). Không có một enum tên `OWNER_ALL` hoặc `GROUP_NONE` trong kiểu này.

### 4.2. Chuỗi quyền phải đúng cấu trúc

`PosixFilePermissions.fromString` yêu cầu đúng **9 ký tự** với các vị trí tương ứng `r`, `w`, `x` hoặc `-`. Chẳng hạn:

```java
PosixFilePermissions.fromString("rw-r-----"); // Hợp lệ.
PosixFilePermissions.fromString("rwxr-x---"); // Hợp lệ.
PosixFilePermissions.fromString("rw-r--");    // Sai độ dài.
```

Đây là snippet minh họa. Đầu vào sai ném `IllegalArgumentException`. Đừng truyền trực tiếp chuỗi dạng `"-rw-r-----"` hoặc `"drwxr-x---"` từ `ls -l` cho `fromString`: chúng có **ký tự loại file ở đầu**, còn parser này chỉ nhận **9 bit**.

Cũng không thể truyền trực tiếp chuỗi `"750"` cho `fromString`. Đó là **dạng số bát phân** cần chuyển sang chín bit hoặc được xử lý theo bộ giải mã tương ứng.

## 5. Mode bát phân: vì sao r=4, w=2, x=1?

Trong mỗi bộ ba:

- `r` tương đương bit `4`.
- `w` tương đương bit `2`.
- `x` tương đương bit `1`.

Cộng các bit bật trong mỗi bộ ba, rồi ghép ba chữ số theo thứ tự **owner / group / others**.

Ví dụ:

```text
rw-r-----  => (4 + 2 + 0) (4 + 0 + 0) (0 + 0 + 0) => 640
rwxr-x---  => (4 + 2 + 1) (4 + 0 + 1) (0 + 0 + 0) => 750
rwx------  => 700
rw-------  => 600
```

Trong Unix shell bạn thường gặp `chmod 640 file.txt` hoặc `chmod 750 some-directory`; trong Java hãy ưu tiên `PosixFilePermissions.fromString(...)` vì ý nghĩa các bit rõ ngay trong source.

**Đừng nhầm mode `600` với số thập phân 600.** Trong Java, integer literal `0600` là bát phân theo cú pháp số nguyên với tiền tố `0`; nhưng `"600"` vẫn chỉ là chuỗi và `PosixFilePermissions.fromString("600")` không hợp lệ.

### 5.1. Ví dụ runnable: chuyển tập quyền thành mode octal

Tạo `PosixOctalDemo.java`:

```java
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixOctalDemo {
    static int digit(Set<PosixFilePermission> permissions,
            PosixFilePermission read,
            PosixFilePermission write,
            PosixFilePermission execute) {
        return (permissions.contains(read) ? 4 : 0)
             + (permissions.contains(write) ? 2 : 0)
             + (permissions.contains(execute) ? 1 : 0);
    }

    static String toOctal(String pattern) {
        Set<PosixFilePermission> perms =
                PosixFilePermissions.fromString(pattern);

        int owner = digit(perms,
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE);
        int group = digit(perms,
                PosixFilePermission.GROUP_READ,
                PosixFilePermission.GROUP_WRITE,
                PosixFilePermission.GROUP_EXECUTE);
        int others = digit(perms,
                PosixFilePermission.OTHERS_READ,
                PosixFilePermission.OTHERS_WRITE,
                PosixFilePermission.OTHERS_EXECUTE);

        return "" + owner + group + others;
    }

    public static void main(String[] args) {
        for (String pattern : new String[] {
            "rw-r-----", "rwxr-x---", "rwx------",
            "rw-------", "---------"
        }) {
            System.out.println(
                    pattern + "=" + toOctal(pattern));
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixOctalDemo.java
java PosixOctalDemo
```

```text
rw-r-----=640
rwxr-x---=750
rwx------=700
rw-------=600
---------=000
```

Đây cũng là chương trình **độc lập với filesystem**, phù hợp làm unit test trên mọi hệ điều hành. Thử thêm `"rw-r--r--"` và dự đoán `644`; thử `"rwxrwxrwx"` và dự đoán `777`, rồi giải thích vì sao `777` là cấu hình nguy hiểm trong nhiều ngữ cảnh triển khai.

## 6. Quy tắc nhóm và thứ tự chọn lớp quyền

Một cách tiếp cận sai khi ứng dụng muốn “xem ai được đọc” là lấy phép OR của ba lớp:

```java
// Sai nếu dùng làm quyết định OS-level cho một principal:
boolean anyoneCanRead = permissions.contains(OWNER_READ)
        || permissions.contains(GROUP_READ)
        || permissions.contains(OTHERS_READ);
```

Biến `anyoneCanRead` chỉ mô tả **có ít nhất một lớp** bật bit read; nó **không** trả lời “principal cụ thể này có thể đọc file không?”.

Trong mô hình POSIX cơ bản, hệ thống cần xét quan hệ của **process identity** với owner và owning group. Một cách diễn giải khái niệm:

1. Nếu effective user identity khớp owner: xét bộ ba **owner**.
2. Nếu không phải owner nhưng thuộc owning group: xét **group** (có thể còn ACL mask/entries).
3. Nếu không thuộc hai lớp: xét **others**.
4. Tiếp đó còn ACL, filesystem/mount, đặc quyền, directory traversal và các điều kiện khác.

**Đây không phải thuật toán được Java tự áp dụng trong source code.** Không nên tự kiểm tra user/group string trong ứng dụng rồi suy ra thay cho OS, nhất là trên Windows/ACL hoặc hệ thống phân tán.

### 6.1. Ví dụ runnable: tra bit theo một lớp giả định

Tạo `PosixClassPolicyDemo.java`:

```java
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixClassPolicyDemo {
    enum FileClass {
        OWNER, GROUP, OTHERS
    }

    enum Operation {
        READ, WRITE, EXECUTE
    }

    static PosixFilePermission bit(
            FileClass fileClass, Operation operation) {
        return switch (fileClass) {
            case OWNER -> switch (operation) {
                case READ -> PosixFilePermission.OWNER_READ;
                case WRITE -> PosixFilePermission.OWNER_WRITE;
                case EXECUTE -> PosixFilePermission.OWNER_EXECUTE;
            };
            case GROUP -> switch (operation) {
                case READ -> PosixFilePermission.GROUP_READ;
                case WRITE -> PosixFilePermission.GROUP_WRITE;
                case EXECUTE -> PosixFilePermission.GROUP_EXECUTE;
            };
            case OTHERS -> switch (operation) {
                case READ -> PosixFilePermission.OTHERS_READ;
                case WRITE -> PosixFilePermission.OTHERS_WRITE;
                case EXECUTE -> PosixFilePermission.OTHERS_EXECUTE;
            };
        };
    }

    static boolean enabled(
            Set<PosixFilePermission> mode,
            FileClass cls, Operation op) {
        return mode.contains(bit(cls, op));
    }

    public static void main(String[] args) {
        Set<PosixFilePermission> mode =
                PosixFilePermissions.fromString("rw-r-----");

        System.out.println(
                "owner-write="
                + enabled(mode, FileClass.OWNER, Operation.WRITE));
        System.out.println(
                "group-read="
                + enabled(mode, FileClass.GROUP, Operation.READ));
        System.out.println(
                "group-write="
                + enabled(mode, FileClass.GROUP, Operation.WRITE));
        System.out.println(
                "others-read="
                + enabled(mode, FileClass.OTHERS, Operation.READ));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixClassPolicyDemo.java
java PosixClassPolicyDemo
```

```text
owner-write=true
group-read=true
group-write=false
others-read=false
```

Chương trình **chỉ trả lời liệu một bit mode của lớp được chỉ định có bật hay không**. Nó **không** tìm effective UID/group của process, không đọc ACL và không kiểm tra khả năng truy cập file thực tế. Phân biệt này đặc biệt quan trọng nếu xây dựng hệ thống authorization: xác thực quyền nghiệp vụ phải đặt ở domain/security layer, còn permission bits chỉ là một trong các biện pháp bảo vệ I/O.

## 7. Đọc POSIX attributes qua Files

Các API hữu ích trên filesystem có POSIX view:

```java
Set<PosixFilePermission> perms =
        Files.getPosixFilePermissions(path);

PosixFileAttributes attrs =
        Files.readAttributes(
            path, PosixFileAttributes.class);

UserPrincipal owner = attrs.owner();
GroupPrincipal group = attrs.group();
Set<PosixFilePermission> bits = attrs.permissions();
```

Đây là snippet; `path` và các import đã tồn tại. `getPosixFilePermissions` trả tập quyền; `readAttributes` lấy nhiều thuộc tính POSIX trong một lần đọc API. Không suy rằng tất cả thuộc tính được chụp thành snapshot nguyên tử trên mọi provider.

**Quan trọng về portability:** không phải default filesystem nào cũng hỗ trợ `PosixFileAttributeView`. Ví dụ Windows thường hỗ trợ các mô hình ACL riêng nhưng **không hỗ trợ trực tiếp chín bit POSIX qua view này**. `Files.getPosixFilePermissions` có thể ném `UnsupportedOperationException` khi provider không hỗ trợ.

### 7.1. Phát hiện khả năng trước khi đọc

Một cách tiếp cận hiện đại:

```java
PosixFileAttributeView view =
        Files.getFileAttributeView(
            path, PosixFileAttributeView.class,
            LinkOption.NOFOLLOW_LINKS);

if (view == null) {
    // Provider không cung cấp view này cho path.
} else {
    PosixFileAttributes attrs = view.readAttributes();
    // attrs.owner(), attrs.group(), attrs.permissions().
}
```

Đây là snippet, không phải runnable class. Có thể kiểm tra cấp filesystem bằng `Files.getFileStore(path).supportsFileAttributeView("posix")` hoặc overload nhận class, nhưng đừng chỉ nhìn tên OS rồi mặc định mọi mount/provider đều có cùng tính năng.

**Hai chính sách khác nhau khi provider không hỗ trợ:**

- **Bỏ qua có thông báo rõ**: với một báo cáo/diagnostics tùy chọn, cho phép chạy mà không hiện quyền POSIX.
- **Fail closed**: với yêu cầu bảo mật bắt buộc như tệp chứa key cần mode riêng tư, từ chối thao tác hoặc dùng một cơ chế kiểm soát quyền **tương đương theo provider**. Không tạo file rộng quyền rồi in “đã bảo vệ” chỉ vì bạn bỏ qua bước POSIX.

### 7.2. Ví dụ runnable: kiểm tra view và đọc attributes có điều kiện

Tạo `PosixAttributeProbeDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFileAttributes;
import java.nio.file.attribute.PosixFilePermissions;

public class PosixAttributeProbeDemo {
    public static void main(String[] args)
            throws IOException {
        Path file = Files.createTempFile(
                "posix-probe-", ".txt");

        try {
            PosixFileAttributeView view =
                    Files.getFileAttributeView(
                        file, PosixFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);

            boolean verified = true;
            if (view != null) {
                PosixFileAttributes attrs =
                        view.readAttributes();
                verified = attrs.owner() != null
                        && attrs.group() != null
                        && PosixFilePermissions.toString(
                            attrs.permissions()).length() == 9;
            }

            System.out.println(
                    "provider-check-complete=" + verified);
            System.out.println(
                    "file-exists=" + Files.isRegularFile(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixAttributeProbeDemo.java
java PosixAttributeProbeDemo
```

```text
provider-check-complete=true
file-exists=true
```

Nếu POSIX view không hỗ trợ, chương trình **chủ động bỏ qua kiểm tra thuộc tính POSIX**, không cố gọi `Files.getPosixFilePermissions` rồi gây lỗi. Nếu view hỗ trợ, nó xác minh attributes có owner, group và một mode có thể hiển thị bằng 9 ký tự. **Nó không kết luận file đang có quyền bảo mật cụ thể.**

Không in tên owner/group ra stdout mẫu vì chúng phụ thuộc máy và có thể là thông tin nhạy cảm. Khi debug thực tế, lấy tên bằng `attrs.owner().getName()`/`attrs.group().getName()` theo chính sách logging.

## 8. Đổi quyền một tệp đã tồn tại

Trên filesystem hỗ trợ POSIX, dùng:

```java
Set<PosixFilePermission> privateMode =
        PosixFilePermissions.fromString("rw-------");

Files.setPosixFilePermissions(path, privateMode);
```

Đây là snippet trong method xử lý `IOException`. Nó tương ứng ý định cấp owner đọc/ghi, không cấp bit nào cho group/others.

**`Files.setPosixFilePermissions` không cấp quyền administrator cho process**. Lời gọi có thể thất bại vì thiếu quyền, file readonly, mount policy hoặc provider không hỗ trợ. Xử lý lỗi theo yêu cầu bảo mật; đừng catch rồi tuyên bố đã đặt mode.

**Đổi permission không đổi owner/group.** Các thao tác set owner/group có API khác và điều kiện đặc quyền riêng. Không nên “sửa” lỗi không đọc được file bằng cách tùy tiện bật `OTHERS_READ`.

### 8.1. Ví dụ runnable: chỉ đổi trên filesystem có POSIX view

Tạo `PosixSetModeDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixSetModeDemo {
    public static void main(String[] args)
            throws IOException {
        Path file = Files.createTempFile(
                "posix-update-", ".txt");

        try {
            PosixFileAttributeView view =
                    Files.getFileAttributeView(
                        file, PosixFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);

            if (view != null) {
                Set<PosixFilePermission> original =
                        view.readAttributes().permissions();

                try {
                    Set<PosixFilePermission> desired =
                            PosixFilePermissions.fromString(
                                "rw-------");

                    Files.setPosixFilePermissions(file, desired);

                    Set<PosixFilePermission> actual =
                            Files.getPosixFilePermissions(
                                file, LinkOption.NOFOLLOW_LINKS);
                    if (!desired.equals(actual)) {
                        throw new IOException(
                                "POSIX mode did not match");
                    }
                } finally {
                    Files.setPosixFilePermissions(file, original);
                }
            }

            System.out.println(
                    "permission-operation-complete=true");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixSetModeDemo.java
java PosixSetModeDemo
```

```text
permission-operation-complete=true
```

**Trên POSIX provider:** ví dụ lưu mode cũ, đặt `rw-------`, đọc lại để kiểm tra, rồi khôi phục mode cũ trong `finally` trước khi xóa tệp tạm. **Trên provider thiếu POSIX view:** nó bỏ qua thao tác quyền có điều kiện, nhưng vẫn tạo và xóa tệp tạm, do đó chương trình chạy trên Windows thường vẫn thành công.

Đây là **bài demo**, không phải implementation yêu cầu bảo mật bất biến. Đối với dữ liệu bí mật, nếu POSIX view thiếu và bạn không có kiểm soát quyền tương đương theo provider, **phải fail closed**, không tự skip như test portability.

### 8.2. Vì sao không phải cứ get/set là atomic transaction?

Hai lời gọi đọc và đặt quyền có thể bị ngăn cách bởi thay đổi của tiến trình khác. Sau khi bạn đặt mode, actor khác có quyền vẫn có thể đổi lại. Không có một transaction Java tiêu chuẩn nào đảm bảo permission snapshot giữa tất cả thao tác đọc/ghi tệp.

Ngoài ra:

- Path có thể bị thay thế giữa lúc kiểm tra và lúc sửa (TOCTOU).
- Symlink có thể chuyển hướng thao tác nếu code không có chính sách rõ.
- Một metadata read có thể thấy trạng thái khác một metadata read tiếp theo.
- Quyền ghi entry trên thư mục cha, ACL và đặc quyền có thể ảnh hưởng hành vi.

Với hệ thống nhạy cảm, thiết kế ownership của file/path, dùng thư mục do server quản lý, hạn chế account của process và cân nhắc primitive dựa trên handle/provider nơi khả dụng.

## 9. Tạo tệp với mode riêng tư ngay từ đầu

Một mẫu có vấn đề:

```java
Path secret = Files.createFile(path);
Files.setPosixFilePermissions(
        secret,
        PosixFilePermissions.fromString("rw-------"));
```

Đây là snippet. Nếu file được tạo với quyền rộng hơn rồi mới giảm quyền, **có thể tồn tại một khoảng thời gian giữa hai bước**. Nếu tệp chứa dữ liệu nhạy cảm hoặc có actor đồng thời, đây là nguy cơ tránh được khi provider cho phép đặt **initial permissions lúc tạo**.

Java NIO.2 cung cấp `PosixFilePermissions.asFileAttribute(perms)`:

```java
Set<PosixFilePermission> privateMode =
        PosixFilePermissions.fromString("rw-------");

FileAttribute<Set<PosixFilePermission>> attributes =
        PosixFilePermissions.asFileAttribute(privateMode);

Path secret = Files.createFile(path, attributes);
```

Đây là snippet; cần import `Set`, `PosixFilePermission`, `PosixFilePermissions`, `FileAttribute`, `Files`, `Path`, và method xử lý `IOException`.

**Điểm cực kỳ quan trọng từ JavaDoc:** ngay cả khi provider hỗ trợ đặt initial POSIX permissions, **actual permissions có thể *hẹp hơn* requested**. Ví dụ trên Unix, `umask` của process có thể tắt thêm các bit. JavaDoc yêu cầu kết quả không rộng hơn tập được cung cấp khi implementation hỗ trợ việc đặt initial permissions. Vì vậy **không được hard-code rằng mode sẽ luôn bằng chính xác `rw-------` trên mọi runtime** mà không đọc lại.

Không phải mọi provider hỗ trợ POSIX attribute view đều hỗ trợ đặt initial permissions trong mọi tình huống. Nếu đây là yêu cầu bắt buộc, xử lý `UnsupportedOperationException`/`IOException` theo hướng **không báo thành công giả**.

### 9.1. Ví dụ runnable: tạo file với attribute, tôn trọng umask

Tạo `PosixCreateModeDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixCreateModeDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory(
                "posix-create-");
        Path file = dir.resolve("secret.txt");

        try {
            PosixFileAttributeView view =
                    Files.getFileAttributeView(
                        dir, PosixFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);

            if (view != null) {
                Set<PosixFilePermission> requested =
                        PosixFilePermissions.fromString(
                            "rw-------");
                FileAttribute<Set<PosixFilePermission>> attr =
                        PosixFilePermissions.asFileAttribute(
                            requested);

                Files.createFile(file, attr);
                Set<PosixFilePermission> actual =
                        Files.getPosixFilePermissions(file);

                if (!requested.containsAll(actual)) {
                    throw new IOException(
                            "Actual permissions are too broad");
                }
            } else {
                // Chỉ là fallback để demo chạy trên non-POSIX.
                Files.createFile(file);
            }

            System.out.println(
                    "created=" + Files.isRegularFile(file));
            System.out.println(
                    "directory-exists="
                    + Files.isDirectory(dir));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixCreateModeDemo.java
java PosixCreateModeDemo
```

```text
created=true
directory-exists=true
```

Trên POSIX, chương trình yêu cầu `rw-------` **ngay khi tạo** và kiểm tra không có bit nào ngoài tập requested. Nếu `umask` làm quyền hẹp hơn, kiểm tra vẫn hợp lệ. Trên non-POSIX, ví dụ chỉ tạo một file bình thường để chạy được nhưng **không tuyên bố file đã đạt bảo mật mode 600**.

**Đối với secret thật:** phải quyết định policy khi không có POSIX view. Hãy dùng cơ chế ACL/quyền riêng của provider hoặc fail closed. Không biến fallback của bài kiểm thử thành logic bảo mật production.

## 10. Umask và mode khi tạo file/directory

**`umask`** trong hệ thống kiểu Unix thường loại bớt quyền được yêu cầu lúc tạo tệp/thư mục.

- Mode requested là **giới hạn trên** cho các bit được bật sau khi tạo theo quy tắc provider.
- `umask` có thể **loại** bit, không phải tự cấp thêm quyền ngoài yêu cầu.
- Mode cuối cùng còn phụ thuộc cách API/provider tạo entry, default ACL và cấu hình filesystem.
- Khi dùng `asFileAttribute` lúc tạo, giá trị thực tế có thể khác requested; đọc lại để xác nhận những điều bảo mật yêu cầu.
- Một số filesystem có policy/ACL phức tạp, không nên mô phỏng tất cả bằng phép `requested & ~umask` trong logic portable Java rồi coi đó là sự thật duy nhất.

Ví dụ minh họa khái niệm:

```text
Requested file mode:  rw-rw-rw-  (666)
Ví dụ umask:          ----w--w-  (022, chỉ để hình dung bit bị loại)
Result thường thấy: rw-r--r--  (644)
```

Dãy trên là **mô hình minh họa**; policy tạo file cụ thể và filesystem có thể làm kết quả khác. Việc chọn initial private mode **`rw-------`** an toàn về mặt không bật group/others hơn tạo mode rộng rồi tìm cách thu hẹp sau.

### 10.1. Thư mục có mode khác file

Tệp dữ liệu thông thường không cần bit `x`. Thư mục có nhu cầu traversable cần `x`, ví dụ:

- Tệp riêng: `rw-------` (mode 600).
- Thư mục riêng: `rwx------` (mode 700).
- Thư mục chia sẻ cho nhóm đọc/traverse: `rwxr-x---` (mode 750).
- File nhóm được phép đọc: `rw-r-----` (mode 640).

**Đừng đặt directory `rw-------` chỉ vì đó là mode 600 “an toàn” cho file**: thiếu `x` làm việc truy cập các file bên trong qua pathname có thể thất bại. Ngược lại, đừng cấp bit `x` cho file dữ liệu chỉ vì directory dùng 750.

### 10.2. Ví dụ runnable: kiểm tra mode file và directory theo mục đích

Tạo `PosixDirectoryModeDemo.java`:

```java
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class PosixDirectoryModeDemo {
    public static void main(String[] args) {
        Set<PosixFilePermission> file =
                PosixFilePermissions.fromString("rw-------");
        Set<PosixFilePermission> directory =
                PosixFilePermissions.fromString("rwxr-x---");

        System.out.println(
                "private-file-owner-read="
                + file.contains(PosixFilePermission.OWNER_READ));
        System.out.println(
                "private-file-group-read="
                + file.contains(PosixFilePermission.GROUP_READ));
        System.out.println(
                "group-can-traverse-dir="
                + directory.contains(
                    PosixFilePermission.GROUP_EXECUTE));
        System.out.println(
                "group-can-write-dir="
                + directory.contains(
                    PosixFilePermission.GROUP_WRITE));
        System.out.println(
                "others-can-list-dir="
                + directory.contains(
                    PosixFilePermission.OTHERS_READ));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixDirectoryModeDemo.java
java PosixDirectoryModeDemo
```

```text
private-file-owner-read=true
private-file-group-read=false
group-can-traverse-dir=true
group-can-write-dir=false
others-can-list-dir=false
```

Đây là test trên **permission sets** để giải thích ý nghĩa r/w/x. Nó **không kiểm tra** một tài khoản Unix cụ thể có thể đi xuyên directory thực tế hay không.

## 11. Owner, group và API cập nhật danh tính

Đọc POSIX attributes:

```java
PosixFileAttributes attrs =
        Files.readAttributes(
            path, PosixFileAttributes.class,
            LinkOption.NOFOLLOW_LINKS);

String ownerName = attrs.owner().getName();
String groupName = attrs.group().getName();
String mode = PosixFilePermissions.toString(
        attrs.permissions());
```

Đây là snippet. Owner và group là các principal của **file system**; `getName()` có thể phụ thuộc hệ thống, LDAP/AD/identity mapping và provider. Không hard-code tên owner/group để làm bài kiểm thử portable.

Khi cần thay đổi danh tính tệp, `PosixFileAttributeView` có các API như `setOwner(UserPrincipal)` và `setGroup(GroupPrincipal)`; Java không tự cho phép process thực hiện nếu không đủ đặc quyền. Thay group-owner là thao tác **khác hẳn** bật/tắt `GROUP_READ`.

**Không tự chọn “group đầu tiên của process” làm owning group của file** trong business logic. OS có quy tắc kế thừa owner/group và setgid directory; một số provider có ACL. Nếu ứng dụng cần group chung cho cả đội, hãy dùng cơ chế triển khai/identity được quản trị rõ, không đoán từ Java string.

## 12. POSIX view không phải mô hình ACL phổ quát

Các view thường gặp trong Java:

| Attribute view | Ý nghĩa |
| --- | --- |
| `BasicFileAttributeView` | Metadata cơ bản: size, times, loại tệp |
| `FileOwnerAttributeView` | Lấy/đặt owner theo cơ chế provider |
| `PosixFileAttributeView` | Owner, owning group và chín bit permission POSIX |
| `AclFileAttributeView` | Mô hình Access Control List có thể chứa nhiều principal/permission entries |
| `DosFileAttributeView` | Thuộc tính DOS như readonly/hidden/system/archive ở provider hỗ trợ |

Một filesystem có thể hỗ trợ **một số view và không hỗ trợ các view khác**. Đặc biệt, trên Windows/NTFS, ACL thường là mô hình bảo mật quan trọng; cố map một cách giản đơn các ACE của NTFS thành chuỗi `rwxrwxrwx` có thể làm mất semantics.

Nếu filesystem hỗ trợ cả POSIX mode và ACL, **các bit POSIX không nhất thiết đủ để diễn tả toàn bộ quyền hiệu lực**. POSIX ACL có named user/group entries và mask của nó có thể hạn chế quyền effective; Java `PosixFilePermission` chỉ biểu diễn chín quyền tiêu chuẩn. Quyền root/capabilities/mount policy cũng có thể thay đổi kết quả.

### 12.1. Ví dụ runnable: nhận diện view mà không suy sai quyền

Tạo `AttributeViewsDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;

public class AttributeViewsDemo {
    public static void main(String[] args)
            throws IOException {
        Path file = Files.createTempFile(
                "attribute-views-", ".txt");

        try {
            BasicFileAttributeView basic =
                    Files.getFileAttributeView(
                        file, BasicFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);
            PosixFileAttributeView posix =
                    Files.getFileAttributeView(
                        file, PosixFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);
            AclFileAttributeView acl =
                    Files.getFileAttributeView(
                        file, AclFileAttributeView.class,
                        LinkOption.NOFOLLOW_LINKS);

            // Chỉ nhận diện capability; không tự chuyển ACL thành POSIX.
            boolean checked = basic != null
                    && (posix == null || posix.name().equals("posix"))
                    && (acl == null || acl.name().equals("acl"));

            System.out.println(
                    "views-checked=" + checked);
            System.out.println(
                    "regular-file=" + Files.isRegularFile(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AttributeViewsDemo.java
java AttributeViewsDemo
```

```text
views-checked=true
regular-file=true
```

Chương trình **không in tên view có hay không**, vì support thay đổi giữa Linux/macOS/Windows và filesystem providers. Nó xác nhận việc tra cứu không gây lỗi và tên các view tìm được khớp hợp đồng nếu hiện diện.

Trong production, chính sách nên quyết định:

- Nếu **bắt buộc có POSIX owner/group/other bits**: chỉ chạy trên provider hỗ trợ và báo lỗi nếu không.
- Nếu hỗ trợ Windows: triển khai phần quản lý ACL phù hợp hoặc dùng quyền của thư mục riêng được OS quản lý; không giả vờ 9 bit POSIX tồn tại ở đó.
- Nếu chỉ hiển thị metadata thông tin: có thể hiện “POSIX permissions not available” thay vì gắn một mode đoán từ `Files.isReadable`.

## 13. Symlink, NOFOLLOW_LINKS và thay đổi đồng thời

**Symbolic link** làm đường dẫn có thể trỏ tới một entry khác. Với nhiều API đọc thuộc tính, nếu không truyền option thì Java **theo symlink** và đọc thuộc tính target; khi truyền `LinkOption.NOFOLLOW_LINKS`, Java yêu cầu đọc thuộc tính của **chính link** nếu provider hỗ trợ.

Ví dụ:

```java
Set<PosixFilePermission> linkedTarget =
        Files.getPosixFilePermissions(path);

Set<PosixFilePermission> linkItself =
        Files.getPosixFilePermissions(
            path, LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet trên provider phù hợp. Không có nghĩa cả hai lần đọc sẽ cho kết quả khác nhau trong mọi tình huống: phụ thuộc path có là link và provider có hỗ trợ thuộc tính link.

**Giới hạn khi sửa mode:** `Files.setPosixFilePermissions(path, perms)` không nhận `LinkOption...`. Đừng tự nhận lời gọi này có chính sách “không đi theo symlink” chỉ vì lúc trước bạn dùng `NOFOLLOW_LINKS` trong lời gọi đọc. Khi file không đáng tin hoặc có actor đồng thời, path có thể bị thay đổi giữa bước validate và bước set.

**TOCTOU (time-of-check to time-of-use):** code như sau không phải giao dịch nguyên tử:

```java
if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
    Files.setPosixFilePermissions(path, requested);
}
```

Đây là snippet. Một tác nhân khác có thể thay entry sau khi kiểm tra. Với yêu cầu bảo mật cao, dùng root tin cậy, quyền hệ điều hành tối thiểu, tránh nhận đường dẫn tùy ý từ client và cân nhắc primitive handle-relative như `SecureDirectoryStream` khi provider hỗ trợ.

Không bao giờ dùng phép `Path.normalize().startsWith(root)` đơn lẻ như bảo đảm toàn diện khi filesystem có symlinks, mount points, junctions hoặc thay đổi đồng thời. Phép đó chỉ là kiểm tra cú pháp.

## 14. Quyền POSIX và khả năng đọc/ghi thực tế không phải một

Có thể gọi:

```java
boolean readable = Files.isReadable(path);
boolean writable = Files.isWritable(path);
boolean executable = Files.isExecutable(path);
```

Đây là snippet. Các method đó **không trả về chín bit POSIX**; chúng chỉ là các phép thử khả năng truy cập theo provider/process tại thời điểm gọi, và `false` cũng có thể do không xác định được. Chúng không bảo đảm thao tác I/O ngay sau đó sẽ thành công.

Ngược lại, dù `PosixFilePermissions.toString(perms)` cho `rw-------`, chưa đủ để khẳng định mọi thao tác sẽ thành công với owner:

- Process có thể không phải owner.
- Thư mục cha có thể thiếu quyền search `x`.
- ACL hoặc mount read-only/noexec có thể ảnh hưởng.
- File có thể đã bị xóa/thay đổi, handle bị khóa hoặc quota hết.
- Quyền superuser/capabilities có thể vượt qua một số kiểm tra thông thường.
- Storage/network filesystem có policy truy cập bổ sung.

**Cách thực tế:** chọn permission mode làm một lớp bảo vệ, thực hiện I/O bằng API đúng (ví dụ `Files.newInputStream`/`writeString`) và xử lý `IOException`/các lỗi đặc thù. Không dùng `isReadable` như “đã chứng minh quyền đọc vĩnh viễn”.

## 15. Các tình huống triển khai thực tế

### 15.1. Lưu tệp bí mật hoặc khóa riêng

Một cấu hình điển hình trên filesystem POSIX:

```text
Thư mục bí mật:   rwx------  (700)
Tệp chứa secret:  rw-------  (600)
```

Khi tạo, ưu tiên `Files.createFile(..., PosixFilePermissions.asFileAttribute(...))` hoặc API tạo tương đương có attribute bảo mật ban đầu. **Kiểm tra lại** mode/owner theo chính sách. Nếu provider không hỗ trợ POSIX, cần cơ chế bảo vệ tương ứng của provider hoặc fail closed.

Không ghi secret vào log. Khi ghi dữ liệu, chọn charset rõ ràng nếu là text, và cân nhắc đồng bộ hóa/durability nếu yêu cầu; permission mode không thay thế cơ chế mã hóa, secret manager hay audit.

### 15.2. Thư mục nhóm dùng chung

Có thể muốn một directory với owner r/w/x và group r/x (`rwxr-x---`, 750), nhưng nếu **group cũng cần tạo/sửa tên entry**, cần cân nhắc `rwxrwx---` (770), cùng group ownership, setgid inheritance, ACL, sticky bit và quyền tại từng entry.

**Không bật group write chỉ vì muốn đọc thư mục.** Khi group write + x trên directory, các thành viên có thể tác động đến directory entries theo các quy tắc và bảo vệ bổ sung; đây là quyền nhạy cảm.

### 15.3. Báo cáo public cho nhiều người dùng cục bộ

File mode `rw-r--r--` (644) cho phép lớp others có read bit. Điều này **chỉ hợp lý** nếu nội dung thật sự không nhạy cảm và truy cập qua directory cha cũng cho phép. Trong môi trường multi-tenant, mode này có thể không phù hợp; “public” ở một dịch vụ web là khái niệm quyền ứng dụng, không nên map trực tiếp thành `OTHERS_READ` trên ổ đĩa.

### 15.4. Triển khai binary hoặc script

Một file thực thi thường cần `x` cho lớp chủ thể tương ứng, nhưng bit này không tự biến file văn bản thành chương trình chạy được. Với shell script, đường dẫn interpreter, nội dung, shebang và mount policy cũng có thể cần đúng. Cấp `OTHERS_EXECUTE` không có nghĩa users phải được đọc script theo cùng cách trong mọi môi trường.

### 15.5. Container và volume gắn ngoài

Container chạy dưới UID/GID khác với host có thể đọc file mode 600 không thành công dù source code Java đúng. Vấn đề nằm ở **identity mapping, group membership, ACL, volume mount**. Khi debug, cần kiểm tra effective UID/GID, owner/group thực của entry, quyền search trên parent directories và runtime mount options, thay vì bật `chmod 777` làm cách “sửa nhanh”.

## 16. Lỗi API và chiến lược xử lý

Khi thao tác với POSIX attributes, phân biệt các lỗi:

| Tình huống | Exception hoặc hành vi |
| --- | --- |
| Chuỗi mode sai cấu trúc | `IllegalArgumentException` từ `PosixFilePermissions.fromString` |
| Filesystem không hỗ trợ POSIX view | `UnsupportedOperationException` từ một số methods; `getFileAttributeView` có thể trả `null` |
| File không tồn tại | `NoSuchFileException` (một `IOException`) khi đọc/ghi attributes |
| Không đủ quyền | `AccessDeniedException` hoặc `FileSystemException`/`IOException` khác, phụ thuộc provider |
| Tạo file đã tồn tại | `FileAlreadyExistsException` khi `Files.createFile` |
| Không có quyền đặt owner/group | `IOException`/provider-specific error |
| Input Path sai | `InvalidPathException` (runtime) khi tạo Path |
| ACL/provider khác nhau | Không nên suy một exception duy nhất cho mọi OS; kiểm tra tính năng trước |

**Không nuốt `UnsupportedOperationException` vô điều kiện** khi ứng dụng bắt buộc bảo đảm mode bảo mật. Có thể chuyển nó thành lỗi cấu hình triển khai “POSIX attributes required”, còn UI hiển thị chỉ thông báo “not supported” theo policy.

Nếu thao tác `Files.setPosixFilePermissions` thất bại, đừng xử lý bằng cách mặc định mở `rwxrwxrwx` rồi tiếp tục. Hãy giữ hành vi fail-safe, log ngữ cảnh phù hợp và tránh lộ metadata nhạy cảm.

## 17. Testing đa nền tảng

**Nên chia test thành hai cấp:**

1. **Pure unit tests:** chạy mọi nơi với `PosixFilePermissions.fromString`, `toString`, `Set<PosixFilePermission>`; kiểm tra chuỗi và bit policy không cần filesystem POSIX. Ví dụ `PosixModeBasicsDemo`, `PosixOctalDemo`, `PosixClassPolicyDemo`, `PosixDirectoryModeDemo`.
2. **Integration tests có điều kiện:** tạo file tạm, kiểm tra provider support rồi đọc/đặt permissions và xác minh kết quả. Trên provider không hỗ trợ, **skip có nhãn** hoặc yêu cầu CI chạy trên Linux nếu đây là tính năng bắt buộc. Ví dụ `PosixAttributeProbeDemo`, `PosixSetModeDemo`, `PosixCreateModeDemo`.

Một bài test chỉ gọi `fromString("rw-------")` không chứng minh OS thực sự áp dụng mode đó cho file. Ngược lại, một test Windows không hỗ trợ POSIX view **không chứng minh API bị lỗi thời**: nó chỉ phản ánh **khả năng của filesystem/provider đang dùng**.

**Các ca nên kiểm thử:**

- Mode `600`, `640`, `700`, `750` và `000` được phân tích đúng.
- Mode sai độ dài/ký tự báo lỗi rõ.
- File và directory phân biệt ý nghĩa `x`.
- Đọc owner/group/permissions khi provider hỗ trợ.
- Tạo file với attribute và kiểm tra actual permissions là tập con của requested.
- Tạo directory với mode `700` khi provider hỗ trợ, xác minh traversability cần thiết.
- Set permissions trên existing file rồi đọc lại, khôi phục hoặc cleanup sau test.
- Thiếu quyền đặt mode: xử lý lỗi thay vì báo thành công.
- Symbolic link và `NOFOLLOW_LINKS` có hành vi theo policy trên filesystem mục tiêu.
- ACL và group membership không bị lược giản thành biểu thức OR chín bit.
- Path bị thay đổi đồng thời, quyền thư mục cha, umask, volume mount, readonly provider.
- Runtime chỉ có ACL/DOS view: bỏ qua test POSIX hoặc fail-closed nếu security bắt buộc.
- Không in owner/group thật trong stdout cố định hay log công khai.

### 17.1. Ví dụ test thuần bộ nhớ cho mode không hợp lệ

Tạo `PosixModeValidationDemo.java`:

```java
import java.nio.file.attribute.PosixFilePermissions;

public class PosixModeValidationDemo {
    public static void main(String[] args) {
        String valid = "rw-r-----";
        String invalid = "rw-r--";

        System.out.println(
                "valid="
                + PosixFilePermissions.toString(
                    PosixFilePermissions.fromString(valid)));

        try {
            PosixFilePermissions.fromString(invalid);
            System.out.println("unexpected-valid");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid-rejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PosixModeValidationDemo.java
java PosixModeValidationDemo
```

```text
valid=rw-r-----
invalid-rejected=true
```

Ví dụ này cho thấy một lỗi đầu vào có thể được kiểm tra **trước khi đụng tới filesystem**. Tuy nhiên, parser mode thành công chưa có nghĩa quá trình ghi file được cho phép.

## 18. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Nhầm `owner/group/others` là ba user cụ thể | Chúng là ba **lớp** quyền | Hiểu identity owner, owning group và các chủ thể còn lại |
| Nghĩ file owner và process hiện tại luôn giống nhau | Account chạy service có thể khác | Đọc owner/group và kiểm tra runtime identity |
| Dùng phép OR mọi bit read để kết luận user có thể đọc | Quyền xét theo lớp và có ACL/OS rules | Không tự thay thế OS access checks |
| Đọc `rwxr-x---` thành mode 755 | Others không có quyền | Mode này là **750** |
| Dùng chuỗi `"750"` với `fromString` | Parser đòi 9 ký tự r/w/x/- | Dùng `"rwxr-x---"` |
| Truyền `"-rw-r-----"` cho parser | Có ký tự loại file ở đầu | Bỏ prefix loại file khi input được xác thực |
| Coi `644` là mode an toàn cho mọi file | Others có read bit | Chọn theo tính nhạy cảm nội dung |
| Coi `600` là mode directory hợp lý cho mọi trường hợp | Thiếu `x` để traverse | Private directory thường cần `700` |
| Hiểu directory `w` giống file `w` | Directory write ảnh hưởng tên entry | Xét cả `x`, sticky bit và ACL |
| Dùng `File.canRead()` để suy toàn bộ POSIX bits | Chỉ là kiểm tra truy cập có giới hạn | Dùng `PosixFileAttributeView` nếu có |
| Bắt `UnsupportedOperationException` rồi khẳng định đã set 600 | Provider có thể không hỗ trợ | Fail closed hoặc policy provider-specific |
| Tạo file rồi mới hạ quyền với dữ liệu nhạy cảm | Có thể có race window | Dùng `asFileAttribute` khi tạo, verify |
| Tin actual mode luôn y hệt requested | Umask/default ACL có thể thu hẹp | Đọc lại actual; bảo đảm không rộng hơn |
| Nghĩ `setPosixFilePermissions` đổi owner/group | Nó chỉ đổi chín quyền | Quản lý owner/group riêng khi cần và có quyền |
| Nghĩ ACL và POSIX mode là một | ACL có named principals, masks/entries | Đánh giá đúng attribute view và provider |
| Bật `rwxrwxrwx` để “fix permission denied” | Mở rộng quyền quá mức | Debug owner, group, parent dir, ACL, mount |
| Bỏ qua symlink/TOCTOU khi thao tác path | Có thể đụng nhầm file | Root tin cậy, policy link, handle-relative nếu hỗ trợ |
| Gọi `getPosixFilePermissions` trên Windows rồi coi exception là lỗi Java | Windows filesystem có thể thiếu POSIX view | Feature-detect và có fallback phù hợp |

## 19. Checklist code review

1. File được truy cập là **file thường hay directory**? Ý nghĩa `x` đã được hiểu đúng chưa?
2. File có nhạy cảm không? Có vô tình bật `GROUP_READ`/`OTHERS_READ` không?
3. Process chạy dưới UID/GID/identity nào? Owner/group của entry thật sự là ai?
4. Có hiểu thứ tự owner → group → others và không OR các lớp một cách sai lầm không?
5. Có biết nhóm bổ sung, POSIX ACL và ACL mask ảnh hưởng quyền hiệu lực không?
6. Có dùng `PosixFilePermissions.fromString` với đúng 9 ký tự không?
7. Có dùng `Set<PosixFilePermission>` thay vì nhầm `java.io.FilePermission` không?
8. Có kiểm tra `PosixFileAttributeView` theo provider/path không, thay vì dựa vào tên OS?
9. Nếu view thiếu, hệ thống **skip có chủ đích** hay **fail closed** theo yêu cầu bảo mật?
10. Nếu tạo file chứa secret, có đặt initial permissions ngay tại create không?
11. Có đọc lại mode thực tế và nhớ `umask` có thể tắt thêm bit không?
12. Có phân biệt đổi chín bit quyền với đổi owner/group không?
13. Có cần mô hình ACL thay vì 9 bit POSIX trên Windows/NTFS không?
14. Khi đọc attributes, có quyết định có follow symlink không?
15. Khi **ghi** permissions, có xử lý rủi ro thay đổi path/symlink/TOCTOU không?
16. Đường dẫn cha có đủ traverse/search quyền không?
17. Có tin sai `Files.isReadable`/`isWritable` là bảo đảm I/O tuyệt đối không?
18. Có test trên filesystem mục tiêu và pipeline CI với POSIX view thật khi tính năng bắt buộc không?
19. Có tránh hard-code tên owner/group và số mode giả định trên mọi OS không?
20. Có log lỗi phù hợp và không làm lộ đường dẫn hoặc thông tin danh tính nhạy cảm không?

## 20. Bài tập

**Bài 1 — Giải mã mode.** Chạy `PosixModeBasicsDemo` và giải thích mỗi ký tự trong `rwxr-x---`. Thay thành `rw-r--r--` và dự đoán số bit bật.

**Bài 2 — Octal.** Chạy `PosixOctalDemo`, thêm `"rwxrwx---"` và `"rw-r--r--"`, tính octal bằng tay. Vì sao `777` khác `750` ở quyền cấp cho group/others?

**Bài 3 — Phân lớp.** Chạy `PosixClassPolicyDemo`. Viết thêm câu hỏi “group có quyền execute không?” cho mode `rw-r-----`. Giải thích vì sao việc bật bit không đủ làm OS cho phép một process bất kỳ truy cập.

**Bài 4 — File và directory.** Chạy `PosixDirectoryModeDemo`. Thiết kế mode cho một directory private owner và một directory cho group đọc/traverse. Có cần group write hay không, vì sao?

**Bài 5 — View.** Chạy `PosixAttributeProbeDemo` trên Windows và Linux (nếu có). So sánh kết quả capability detection; nếu POSIX view không tồn tại, giải thích tại sao không nên gọi `getPosixFilePermissions` một cách mù quáng.

**Bài 6 — Thay quyền.** Chạy `PosixSetModeDemo` trên filesystem POSIX. Đổi desired thành `"rw-r-----"` rồi xác minh readback; bảo đảm khôi phục mode cũ và xóa file tạm ngay cả khi test thất bại.

**Bài 7 — Initial attributes.** Chạy `PosixCreateModeDemo`; so sánh requested và actual mode trong một test POSIX. Thay requested thành `"rwx------"` cho một directory và kiểm tra kết quả trong chính sách `umask` thực tế.

**Bài 8 — ACL.** Chạy `AttributeViewsDemo` trên các filesystem khác nhau; tìm hiểu vì sao ACL không thể tự động coi bằng chín bit POSIX. Đừng sửa ACL tài nguyên thật chỉ để hoàn thành bài tập.

**Bài 9 — Validation.** Chạy `PosixModeValidationDemo` với chuỗi `"rwxr-x"`, `"rwxr-x---"` và `"rwxr-xr-z"`; xác định những input cần báo `IllegalArgumentException`.

**Bài 10 — Thiết kế API.** Viết service `createPrivateFile(Path target)` yêu cầu POSIX mode 600. Quy định rõ behavior trên filesystem non-POSIX, xử lý file đã tồn tại, giới hạn root, symlink, thông báo lỗi và readback permission.

**Bài 11 — Multi-tenant.** Một process lưu data của nhiều tenant dưới cùng UID. Giải thích vì sao chỉ dùng `rw-------` không đủ tách các tenant nếu application permission checks sai.

**Bài 12 — Diagnose.** Một directory có mode `rw-r-----`, một file bên trong có mode `rw-r-----`. Vì sao group có thể không đọc được file theo pathname dù trên file có `GROUP_READ`? Đề xuất mode directory hợp lý mà không cấp quyền quá rộng.

## 21. Tóm tắt nhanh

- **Chín quyền POSIX** gồm `OWNER_READ/WRITE/EXECUTE`, `GROUP_READ/WRITE/EXECUTE` và `OTHERS_READ/WRITE/EXECUTE`.
- **`rwxr-x--- = 750`**, **`rw-r----- = 640`**, **`rw------- = 600`**, **`rwx------ = 700`**; `PosixFilePermissions` dùng chuỗi **9 ký tự**, không nhận trực tiếp mode octal.
- Trên **file**, `x` là execute; trên **directory**, `x` chủ yếu là **search/traverse**. Directory write thường cần `w+x` để thao tác entry.
- Quyền xét theo **owner/group/others**, không OR tất cả lớp; identity, ACL, umask, parent directories và mount policy vẫn quan trọng.
- `Files.getPosixFilePermissions` và `Files.setPosixFilePermissions` **chỉ áp dụng trên filesystem hỗ trợ POSIX view**. Kiểm tra `PosixFileAttributeView` trước.
- `PosixFileAttributes` cho biết `owner()`, `group()` và `permissions()`; chúng không mặc nhiên nói process hiện tại có quyền gì.
- Khi **tạo file bí mật**, ưu tiên `PosixFilePermissions.asFileAttribute(...)` để đặt initial mode. **Umask có thể làm mode hẹp hơn**, nên đọc lại nếu policy yêu cầu.
- Windows/ACL không nhất thiết ánh xạ được sang chín bit POSIX; thiếu view cần fallback rõ hoặc **fail closed**, không giả vờ đã bảo vệ.
- `NOFOLLOW_LINKS` điều chỉnh đọc thuộc tính link, không tự bảo đảm ghi permissions không dính symlink/TOCTOU.
- Code Java 17+ nên sử dụng NIO.2 và những kiểm tra provider/permission phù hợp, không dựa vào mẹo chmod 777 hoặc giả định mọi filesystem có cùng semantics.

## Tài liệu tham khảo chính thức

- [PosixFilePermission — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFilePermission.html): chín hằng enum quyền.
- [PosixFilePermissions — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): `fromString`, `toString`, `asFileAttribute`.
- [PosixFileAttributes — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributes.html): owner, group và permission set.
- [PosixFileAttributeView — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): đọc/đặt POSIX attributes, khả năng đặt mode lúc tạo và umask.
- [Files — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `getPosixFilePermissions`, `setPosixFilePermissions`, `createFile` và `readAttributes`.
- [FileStore — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView`.
- [AclFileAttributeView — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): quản lý ACL khác với POSIX mode.
