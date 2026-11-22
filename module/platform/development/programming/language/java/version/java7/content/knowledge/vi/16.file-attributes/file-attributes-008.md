# Danh sách kiểm soát truy cập với `AclFileAttributeView` trong Java

## 1. ACL dùng để làm gì?

File và thư mục có **chủ sở hữu** (*owner*), nhưng việc xác định **ai có quyền đọc, ghi, xóa, thay thuộc tính hoặc quản lý quyền truy cập** còn phụ thuộc vào cơ chế kiểm soát truy cập của hệ điều hành/file system. Một mô hình thường gặp là *Access Control List* (**ACL**), gồm một **danh sách có thứ tự** các *Access Control Entry* (**ACE**). Mỗi ACE liên kết một danh tính (principal) với loại quy tắc, những quyền liên quan và cờ kế thừa.

Ví dụ trong một hệ thống quản lý tài liệu:

- Tài khoản dịch vụ đọc các file nhưng không được đổi ACL.
- Người phụ trách được chỉnh sửa nội dung trong thư mục dự án.
- Nhóm khác chỉ được xem metadata.
- Một số quy tắc quyền có thể được thư mục cha truyền xuống các mục con.

Java NIO.2 có interface `java.nio.file.attribute.AclFileAttributeView` để **đọc hoặc yêu cầu thay thế** ACL của tệp, trên filesystem hỗ trợ view này. API có từ Java 7 và vẫn hoạt động trên Java 21 và các JDK hiện đại; bài này không dùng API legacy.

~~~java
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);

if (view != null) {
    List<AclEntry> current = view.getAcl();
    // Chỉ đang đọc; file chưa bị sửa quyền.
}
~~~

Đoạn trên là **minh họa** với `Path path` có trước; cần import `Files`, `AclFileAttributeView`, `AclEntry`, `List` và xử lý `IOException`. `view` có thể là `null` nếu provider không cung cấp ACL view, không có nghĩa file không có một cơ chế phân quyền nào khác.

**Mục tiêu học tập:** nắm `AclFileAttributeView`, cấu trúc `AclEntry`, `AclEntryType` / `AclEntryPermission` / `AclEntryFlag`, đọc và xây ACL có thứ tự, hiểu `setAcl()` thay toàn bộ danh sách, lookup đúng `UserPrincipal`, kiểm soát quyền khi ghi, xử lý provider khác nhau, inheritance, symlinks và các lỗi quyền truy cập.

**Nguyên tắc xuyên suốt:** đọc ACL để hiểu metadata là an toàn hơn thử thay quyền tùy tiện. `setAcl(...)` là hành động bảo mật có thể làm mất quyền truy cập; chỉ gọi khi được ủy quyền và đã kiểm tra đầy đủ chính sách.

## 2. Các thành phần của một ACE

`AclEntry` là một đối tượng immutable gồm bốn thành phần:

| Thành phần | Cách đọc | Ý nghĩa |
| --- | --- | --- |
| `type` | `entry.type()` | Loại quy tắc ALLOW, DENY, AUDIT, ALARM |
| `principal` | `entry.principal()` | Danh tính `UserPrincipal` mà entry áp dụng |
| `permissions` | `entry.permissions()` | Tập các `AclEntryPermission` |
| `flags` | `entry.flags()` | Tập các `AclEntryFlag` phục vụ kế thừa/propagation |

ACL là một **`List<AclEntry>` có thứ tự**, không phải `Set`. Đừng tự ý sắp xếp các ACE theo tên account, loại quy tắc hoặc quyền. Trong những mô hình ACL có luật đánh giá theo thứ tự, thay vị trí ALLOW/DENY có thể làm thay đổi ý nghĩa. Provider có thể dịch mô hình NFSv4 của Java sang mô hình bản địa khác nên hiệu lực cụ thể phải kiểm tra theo file system đích.

### 2.1. `AclEntryType`

| Hằng số | Vai trò | Cảnh báo |
| --- | --- | --- |
| `AclEntryType.ALLOW` | Mô tả quyền cho phép | Có entry ALLOW không bảo đảm truy cập được nếu các chính sách khác chặn |
| `AclEntryType.DENY` | Mô tả quyền từ chối | Không xem mọi ACL như một boolean AND/OR không có thứ tự |
| `AclEntryType.AUDIT` | Mô tả nhu cầu audit theo mô hình ACL | Nhà cung cấp có thể không ánh xạ xuống auditing của OS |
| `AclEntryType.ALARM` | Mô tả alarm theo mô hình ACL | Không bảo đảm chức năng cảnh báo của hệ điều hành |

Theo Javadoc `AclFileAttributeView`, khi provider không có ánh xạ cho `AUDIT` hoặc `ALARM`, `setAcl` **có thể bỏ qua** các entry này. Đừng suy ra rằng tạo `AUDIT` trong Java là đã bật log bảo mật.

### 2.2. Các `AclEntryPermission` thường gặp

| Hằng số | Mục đích khái quát |
| --- | --- |
| `READ_DATA` | Đọc nội dung file |
| `WRITE_DATA` | Ghi nội dung file |
| `APPEND_DATA` | Thêm dữ liệu vào cuối file |
| `READ_ATTRIBUTES` | Đọc metadata cơ bản |
| `WRITE_ATTRIBUTES` | Thay metadata cơ bản |
| `READ_NAMED_ATTRS` | Đọc named attributes nếu có |
| `WRITE_NAMED_ATTRS` | Ghi named attributes nếu có |
| `READ_ACL` | Đọc danh sách ACL |
| `WRITE_ACL` | Thay ACL |
| `WRITE_OWNER` | Yêu cầu thay chủ sở hữu |
| `DELETE` | Xóa đối tượng theo quyền tương ứng |
| `DELETE_CHILD` | Xóa mục con theo ngữ nghĩa directory |
| `EXECUTE` | Thực thi hoặc traverse tùy loại đối tượng |
| `SYNCHRONIZE` | Đồng bộ truy cập theo mô hình ACL |

Một `AclEntryPermission` là **điều kiện trong ACE**, không phải giấy chứng nhận cuối cùng rằng tài khoản đã có quyền hiệu lực. Để đọc file, ngoài `READ_DATA` còn có thể cần quyền traverse thư mục cha, account membership phù hợp, không bị quy tắc DENY hoặc OS policy chặn, và file còn tồn tại khi mở.

**Nguyên tắc quyền tối thiểu:** chỉ cho những permission thực sự cần. Đặc biệt tránh thêm `WRITE_ACL`, `WRITE_OWNER`, `DELETE` hoặc `DELETE_CHILD` chỉ vì muốn cho người dùng đọc một tài liệu.

### 2.3. `AclEntryFlag` và kế thừa

| Cờ | Ý nghĩa khái quát |
| --- | --- |
| `AclEntryFlag.FILE_INHERIT` | File được tạo bên trong thư mục có thể kế thừa ACE |
| `AclEntryFlag.DIRECTORY_INHERIT` | Directory con có thể kế thừa ACE |
| `AclEntryFlag.NO_PROPAGATE_INHERIT` | Hạn chế truyền tiếp xuống các mức sâu hơn |
| `AclEntryFlag.INHERIT_ONLY` | Entry hướng tới inheritance, không nhất thiết áp dụng trực tiếp cho thư mục hiện tại |

Các cờ này **không làm một entry tự động được ghi vào file con ngay khi xây ACE trong bộ nhớ**. Kế thừa thực tế phụ thuộc provider, native ACL và cách tạo file. Với ứng dụng yêu cầu chắc chắn một file con đã được cấp quyền, phải đọc lại **ACL của chính file con** và kiểm tra quyền hiệu lực trong môi trường đích.

## 3. `AclFileAttributeView` là attribute view gì?

`AclFileAttributeView` mở rộng `FileOwnerAttributeView`:

~~~text
FileAttributeView
     ↑
FileOwnerAttributeView
     ↑
AclFileAttributeView
~~~

Các phương thức chính:

- `getAcl()`: đọc **danh sách có thứ tự** các ACE.
- `setAcl(List<AclEntry>)`: **thay thế ACL hiện tại** bằng danh sách được cung cấp.
- `getOwner()`: đọc `UserPrincipal` của chủ file.
- `setOwner(UserPrincipal)`: cập nhật owner nếu filesystem và quyền cho phép.
- `name()`: tên view là `"acl"`.

**Owner và ACL là hai khái niệm khác nhau.** Owner xác định chủ sở hữu file; ACL mô tả nhiều rule về principal và access. Việc có quyền sửa nội dung file không đồng nghĩa có quyền `setAcl()`; việc thay owner cũng không tự động tạo đúng ACL mà bạn mong muốn.

### 3.1. Lấy view và xử lý thiếu hỗ trợ

~~~java
AclFileAttributeView view = Files.getFileAttributeView(
        file, AclFileAttributeView.class);

if (view == null) {
    throw new UnsupportedOperationException("ACL view unavailable");
}
List<AclEntry> entries = view.getAcl();
~~~

Đây là đoạn minh họa cần `Path file` và xử lý `IOException`. `getFileAttributeView` trả `null` nếu loại attribute view không được hỗ trợ. Kể cả khi `view != null`, `getAcl` vẫn có thể thất bại do file bị xóa, quyền truy cập bị từ chối, I/O hoặc provider lỗi.

Có thể hỏi khả năng của `FileStore` qua `supportsFileAttributeView(...)`, nhưng một kiểm tra hỗ trợ không thay cho việc **bắt lỗi ở chính thao tác đọc/ghi**. File system có thể thay đổi và quyền access thực phụ thuộc ngữ cảnh.

### 3.2. `getAcl()` trả List có thể sửa — nhưng chưa đổi quyền thật

Javadoc mô tả `getAcl()` trả danh sách **modifiable** để thuận tiện xây bản ACL đề xuất:

~~~java
List<AclEntry> current = view.getAcl();
List<AclEntry> proposed = new ArrayList<>(current);
proposed.add(0, newRule);
~~~

Đây là đoạn minh họa cần `AclEntry newRule` và import `ArrayList`. Ba dòng chỉ biến đổi **dữ liệu trong bộ nhớ**. Không có thay đổi ACL trên filesystem cho đến khi gọi `view.setAcl(proposed)`.

Sao chép sang `ArrayList` giúp bảo toàn snapshot ban đầu phục vụ so sánh. Tuy nhiên nó **không khóa ACL**; actor khác có thể chỉnh file giữa lần `getAcl` và lần `setAcl`, tạo race *read-modify-write*.

### 3.3. Đọc ACL qua dynamic attribute

Tên view chuẩn là `"acl"`. Các thuộc tính dynamic được hỗ trợ:

| Thuộc tính | Kiểu thực tế | Phương thức type-safe tương đương |
| --- | --- | --- |
| `"acl:acl"` | `List<AclEntry>` | `getAcl()` |
| `"acl:owner"` | `UserPrincipal` | `getOwner()` |

~~~java
Object raw = Files.getAttribute(path, "acl:acl");
if (raw instanceof List<?>) {
    // Đã nhận một danh sách; hãy xác minh phần tử nếu cần.
}
~~~

Đây là đoạn minh họa trong phương thức xử lý `IOException`. `Files.getAttribute` trả `Object` nên phải kiểm tra/ép kiểu đúng. Với bài toán ACL rõ ràng, `AclFileAttributeView.getAcl()` thường dễ hiểu và được compiler kiểm tra kiểu tốt hơn.

`Files.setAttribute(path, "acl:acl", newList)` cũng là một đường để yêu cầu thay ACL bằng tên thuộc tính; **không an toàn hơn** `setAcl(newList)`, và vẫn cần phân quyền, xử lý lỗi cùng kiểm soát danh sách đầy đủ.

## 4. Tạo `AclEntry` bằng Builder, không sửa đối tượng đã build

Tạo một ACE chỉ cho đọc dữ liệu và thuộc tính:

~~~java
AclEntry readRule = AclEntry.newBuilder()
        .setType(AclEntryType.ALLOW)
        .setPrincipal(principal)
        .setPermissions(
                AclEntryPermission.READ_DATA,
                AclEntryPermission.READ_ATTRIBUTES)
        .build();
~~~

Đây là **đoạn minh họa**; `UserPrincipal principal` phải được lấy hoặc phân giải từ provider phù hợp. Cần xác định rõ danh tính nào được phép nhận quyền. Không dùng một principal không được ủy quyền do client tùy ý cung cấp.

`AclEntry` là immutable. Muốn xây một bản khác có inheritance flags, dùng builder sao chép:

~~~java
AclEntry inheritable = AclEntry.newBuilder(readRule)
        .setFlags(
                AclEntryFlag.FILE_INHERIT,
                AclEntryFlag.DIRECTORY_INHERIT)
        .build();
~~~

`AclEntry.newBuilder(readRule)` sao chép bốn thành phần hiện tại vào builder mới. `setFlags` thay phần flags; `build()` trả entry khác. `readRule` không thay đổi.

Có thể kiểm tra các thành phần:

~~~java
boolean allows = readRule.type() == AclEntryType.ALLOW;
boolean hasReadData = readRule.permissions()
        .contains(AclEntryPermission.READ_DATA);
boolean hasNoFlags = readRule.flags().isEmpty();
~~~

Ba giá trị nói về **entry Java trong bộ nhớ**, không phải “đã cấp quyền đọc thật”. Chỉ những thao tác được ủy quyền và được provider thực hiện mới có thể cập nhật ACL của file.

## 5. Chương trình Java 21 đầy đủ: đọc ACL và dựng ACE mẫu, không thay quyền

Để ví dụ chạy trên các hệ điều hành khác nhau, ta **không cố gán ACL** trên file thật. Chương trình tự tạo file tạm, lấy ACL view, đọc owner và ACL, tạo vài ACE trong bộ nhớ, kiểm tra các thuộc tính qua boolean, rồi xóa tài nguyên do chính nó tạo.

Các điểm kiểm thử:

1. `view.name()`.
2. `view.getAcl()` trả List gồm các `AclEntry`.
3. `Files.getAttribute(file, "acl:acl")` trả danh sách.
4. Đọc owner qua `view.getOwner()` và `Files.getOwner`.
5. Tạo ACE `ALLOW` có `READ_DATA`/`READ_ATTRIBUTES`.
6. `AclEntry.newBuilder(existing).build()` cho entry tương đương.
7. Thêm `FILE_INHERIT`/`DIRECTORY_INHERIT` vào ACE mới **mà không cập nhật filesystem**.

Tạo file `src/main/java/demo/AclAttributeViewExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclEntryFlag;
import java.nio.file.attribute.AclEntryPermission;
import java.nio.file.attribute.AclEntryType;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.UserPrincipal;
import java.util.List;

public final class AclAttributeViewExample {
    private AclAttributeViewExample() {}

    static void replaceAclIfAuthorized(Path path, List<AclEntry> desired)
            throws IOException {
        AclFileAttributeView view = Files.getFileAttributeView(
                path, AclFileAttributeView.class);
        if (view == null) {
            throw new UnsupportedOperationException("ACL view unavailable");
        }
        view.setAcl(desired);
    }

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("acl-learning-");
        Path file = folder.resolve("sample.txt");
        try {
            Files.writeString(file, "hello ACL", StandardCharsets.UTF_8);
            AclFileAttributeView view = Files.getFileAttributeView(
                    file, AclFileAttributeView.class);

            if (view == null) {
                System.out.println("acl-view=unsupported");
                return;
            }

            List<AclEntry> entries = view.getAcl();
            UserPrincipal owner = view.getOwner();
            Object dynamicAcl = Files.getAttribute(file, "acl:acl");

            System.out.println("acl-view=" + view.name());
            System.out.println("acl-snapshot-readable=" + (entries != null));
            System.out.println("acl-entries-valid=" + entries.stream().allMatch(
                    entry -> entry.principal() != null
                            && entry.type() != null
                            && entry.permissions() != null
                            && entry.flags() != null));
            System.out.println("owner-name-present=" + !owner.getName().isBlank());
            System.out.println("owner-matches-files="
                    + owner.equals(Files.getOwner(file)));
            System.out.println("dynamic-is-list=" + (dynamicAcl instanceof List<?>));

            AclEntry sample = AclEntry.newBuilder()
                    .setType(AclEntryType.ALLOW)
                    .setPrincipal(owner)
                    .setPermissions(AclEntryPermission.READ_DATA,
                            AclEntryPermission.READ_ATTRIBUTES)
                    .build();
            System.out.println("sample-type=" + sample.type());
            System.out.println("sample-has-read="
                    + sample.permissions().contains(AclEntryPermission.READ_DATA));
            System.out.println("sample-flags-empty=" + sample.flags().isEmpty());
            System.out.println("copy-identical="
                    + AclEntry.newBuilder(sample).build().equals(sample));

            AclEntry inherited = AclEntry.newBuilder(sample)
                    .setFlags(AclEntryFlag.FILE_INHERIT,
                            AclEntryFlag.DIRECTORY_INHERIT)
                    .build();
            System.out.println("inherit-rule-has-directory-flag="
                    + inherited.flags().contains(AclEntryFlag.DIRECTORY_INHERIT));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Lệnh Java 21 từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/AclAttributeViewExample.java
java -cp out demo.AclAttributeViewExample
~~~

**Stdout chính xác trên Windows default file system đã kiểm thử:**

~~~text
acl-view=acl
acl-snapshot-readable=true
acl-entries-valid=true
owner-name-present=true
owner-matches-files=true
dynamic-is-list=true
sample-type=ALLOW
sample-has-read=true
sample-flags-empty=true
copy-identical=true
inherit-rule-has-directory-flag=true
~~~

**Trường hợp filesystem không cung cấp ACL view**, chương trình có thể in:

~~~text
acl-view=unsupported
~~~

Nhánh `unsupported` được viết để code chạy theo khả năng filesystem; **không** tuyên bố nó đã xảy ra trên máy thử Windows. Nếu quyền bị từ chối hoặc I/O lỗi, chương trình có thể ném `IOException`; đó không phải cùng tình huống thiếu hỗ trợ view.

### 5.1. Giải thích kết quả

- `acl-view=acl`: tên view chính thức là `"acl"`.
- `acl-snapshot-readable=true`: `getAcl()` trả List; không in số ACE vì các filesystem có policy khác nhau.
- `acl-entries-valid=true`: các entry trong List có thành phần type/principal/permissions/flags. Nếu List rỗng, `allMatch` vẫn là true; nó không chứng minh hệ thống có một ACE nhất định.
- `owner-name-present=true`: owner của file tạm trên môi trường thử có tên không rỗng. Code không tiết lộ tên account thật trong stdout.
- `owner-matches-files=true`: `view.getOwner` và `Files.getOwner` phù hợp trong tình huống file không thay đổi giữa hai lần đọc.
- `dynamic-is-list=true`: `Files.getAttribute(..., "acl:acl")` expose ACL dưới dạng List.
- `sample-type=ALLOW`: entry được tạo bằng Builder với type ALLOW.
- `sample-has-read=true`: permissions của sample chứa `READ_DATA`.
- `sample-flags-empty=true`: rule mẫu chưa đặt inheritance flag.
- `copy-identical=true`: builder sao chép tạo entry bằng bản gốc.
- `inherit-rule-has-directory-flag=true`: bản mới có `DIRECTORY_INHERIT`.

Helper `replaceAclIfAuthorized` được **compiler kiểm tra cú pháp** nhưng **không gọi trong main**. Vì vậy không có `setAcl` nào thực thi trong bài test, không sửa ACL của file tạm hoặc file người học.

## 6. `setAcl`: thay thế danh sách, không phải “thêm một entry”

Một nguy cơ thường gặp là thấy `getAcl()` trả List rồi nghĩ `setAcl` hoạt động như `addPermission`. Trên thực tế:

~~~java
view.setAcl(proposed);
~~~

Phương thức này **cập nhật/thay thế danh sách ACL của file** theo hợp đồng API. Nếu chỉ gửi `List.of(newRule)`, các rule cũ có thể bị thay mất. Điều này có thể làm người sử dụng mất quyền, cấp quyền ngoài ý muốn hoặc làm hỏng chính sách bảo mật.

**Không chạy thao tác cập nhật thật chỉ để thử cú pháp.** Một đoạn minh họa đầy đủ về luồng quản trị:

~~~java
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);
if (view == null) {
    throw new UnsupportedOperationException("ACL unsupported");
}

List<AclEntry> previous = view.getAcl();
List<AclEntry> proposed = new ArrayList<>(previous);
proposed.add(0, approvedReadRule); // Vị trí chỉ là ví dụ, phải review.
view.setAcl(proposed);             // Cập nhật TOÀN BỘ ACL.
~~~

Đây là **mẫu minh họa có tác động bảo mật**, giả sử code đã xác thực caller, file target và `approvedReadRule`. Không dùng như một API public cho phép người dùng không được tin cậy tự thêm rule; vị trí `0` cũng không phải đúng cho mọi ACL.

### 6.1. Quy trình kiểm soát khi bắt buộc cập nhật

Trước khi gọi `setAcl` trong hệ thống thực tế:

1. Kiểm tra người yêu cầu **được ủy quyền** sửa ACL của file/thư mục nào, mức quyền tối đa được cấp.
2. Xác định file target, provider và chính sách symbolic link; không đơn thuần nhận một path từ client rồi dùng quyền cao ghi.
3. Lookup principal từ filesystem đích, không tự tạo một account bằng chuỗi tùy ý.
4. Đọc ACL hiện tại và chụp snapshot để review/rollback khi chính sách cho phép.
5. Định nghĩa điều muốn thêm/bớt với *least privilege*: ví dụ không thêm `WRITE_ACL` hoặc `WRITE_OWNER` nếu chỉ cần đọc.
6. Giữ thứ tự ACE có chủ đích; xem xét rule DENY, cờ inheritance và các mục đang có.
7. Xem toàn bộ danh sách đề xuất trước khi set; **không chỉ review entry mới**.
8. Gọi `setAcl` và xử lý lỗi I/O/provider/quyền một cách tường minh.
9. Đọc lại ACL bằng `getAcl` để kiểm tra provider đã lưu/ánh xạ những gì.
10. Test access hiệu lực bằng tài khoản thử hợp lệ nếu nghiệp vụ yêu cầu, và ghi audit log theo chính sách.

### 6.2. Không có compare-and-swap ACL phổ quát

Nếu hai tiến trình cùng làm:

~~~text
T1: đọc ACL [A]
T2: đọc ACL [A]
T1: thêm B -> setAcl([A,B])
T2: thêm C -> setAcl([A,C])
Kết quả sau cùng có thể không còn B.
~~~

Đây là sơ đồ race. `getAcl` → sửa List → `setAcl` không phải một giao dịch nguyên tử có kiểm tra phiên bản. Không nên giải quyết bằng việc retry trên ACL cũ; có thể ghi đè thay đổi mới của quản trị viên. Cần phối hợp writer, xác định phiên bản/snapshot và review lại trước khi ghi tùy cơ chế ngoài API này.

### 6.3. Không giả định `setAcl` chính là transaction

Java không hứa `setAcl` có thể tự rollback mọi trạng thái nếu gặp lỗi giữa chừng. Việc cập nhật ACL còn có thể làm thay đổi những thuộc tính bảo mật liên quan theo file system. Khi rất quan trọng về độ an toàn, cần thử trên provider/OS đích và có kế hoạch khôi phục, không tự hứa rằng có thể ghi lại snapshot với kết quả giống nguyên xi trong mọi môi trường.

## 7. Phân giải principal cho đúng filesystem

Nếu nghiệp vụ yêu cầu thêm quyền cho account được xác thực, dùng `UserPrincipalLookupService`:

~~~java
UserPrincipalLookupService lookup =
        path.getFileSystem().getUserPrincipalLookupService();

UserPrincipal user = lookup.lookupPrincipalByName(accountName);
~~~

Đoạn này là minh họa với `Path path` và `String accountName`. Lấy lookup service từ **`path.getFileSystem()`**, vì account của provider A có thể không sử dụng được trên provider B.

- `UserPrincipalNotFoundException` nếu không có principal theo tên.
- `IOException` khác khi hệ thống danh tính/I/O lỗi.
- `UnsupportedOperationException` nếu provider không triển khai lookup.
- `ProviderMismatchException` khi ACE chứa principal không thuộc cùng provider như ACL view cần ghi.

`GroupPrincipal` kế thừa `UserPrincipal`, biểu diễn **nhóm** và có `lookupPrincipalByGroupName(...)`. Không thể cho rằng mọi OS/provider dùng cùng định dạng tên group hoặc phân giải được cùng account. `UserPrincipal.getName()` là tên do implementation cung cấp, **không phải ID phổ quát** dùng cho authorization cross-platform.

### 7.1. Vì sao không in danh sách ACL thật ra stdout?

ACL có thể chứa tên user, nhóm doanh nghiệp hoặc danh tính dịch vụ. Trong môi trường thật, in toàn bộ principal và permissions vào log công khai có thể tiết lộ thông tin quản trị. Ví dụ ở phần 5 chỉ kiểm tra boolean và không đưa tên account thật vào tài liệu.

Khi cần audit, phải log actor/đối tượng/thay đổi theo chính sách bảo mật và dữ liệu cá nhân của hệ thống, không dùng cách in console tùy tiện.

## 8. Tính phụ thuộc provider và mapping từ NFSv4 ACL

Mô hình `AclEntry` dựa trên ACL NFSv4, nhưng Windows, POSIX hoặc filesystem khác có thể dùng biểu diễn riêng. `AclFileAttributeView` chỉ áp dụng khi file system hỗ trợ NFSv4 ACL hoặc có ánh xạ hợp lý.

| Trường hợp | Cần nhớ |
| --- | --- |
| Windows provider hỗ trợ ACL view | Có thể đọc ACL, nhưng các entry được dịch từ native security model |
| Filesystem chỉ hỗ trợ POSIX owner/group/mode | Không tự suy ra nó hỗ trợ `AclFileAttributeView` |
| ZIP hoặc provider chuyên dụng | `getFileAttributeView` có thể trả null |
| Native ACL có rule không ánh xạ hoàn toàn | `getAcl` / `setAcl` phụ thuộc provider; có thể từ chối cập nhật |
| `AUDIT` hoặc `ALARM` không có ánh xạ | `setAcl` có thể bỏ qua entry đó |
| ACL mới ảnh hưởng metadata quyền khác | Quyền hoặc thuộc tính liên quan có thể thay đổi |

Javadoc nêu rằng khi không thể dịch một ACL theo cách bảo đảm mức độ an toàn được yêu cầu, provider nên từ chối bằng `IOException`. Vì thế **đừng nghĩ một danh sách Java đã tạo đúng cú pháp chắc chắn được filesystem lưu y nguyên**.

### 8.1. POSIX permissions không phải ACL đầy đủ

`PosixFileAttributeView` cung cấp owner, group và mode permissions theo mô hình POSIX. Nó khác với `AclFileAttributeView`. Chẳng hạn:

~~~java
PosixFileAttributeView posix = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);
if (posix != null) {
    PosixFileAttributes attrs = posix.readAttributes();
    // attrs.owner(), attrs.group(), attrs.permissions()
}
~~~

Đây là đoạn minh họa, cần import `PosixFileAttributeView` / `PosixFileAttributes`, xử lý `IOException`. Nếu `posix == null`, không được cho là máy không có bất kỳ kiểm soát quyền nào; có thể provider hỗ trợ ACL theo mô hình khác.

Không cố chuyển tất cả ACL thành một con số mode như `0644` rồi nghĩ không mất ý nghĩa — các entry allow/deny, inheritance và principal cụ thể thường phức tạp hơn.

## 9. Symbolic link và `LinkOption.NOFOLLOW_LINKS`

Mặc định, `Files.getFileAttributeView(path, AclFileAttributeView.class)` theo symbolic link khi path là link tới target. Nếu muốn yêu cầu view liên quan đến bản thân link:

~~~java
AclFileAttributeView linkView = Files.getFileAttributeView(
        linkPath,
        AclFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
~~~

Đây là đoạn minh họa; filesystem có thể không cho truy cập ACL riêng của symlink hoặc không hỗ trợ một số thao tác theo link option này.

Không suy luận rằng `NOFOLLOW_LINKS` tạo sandbox tuyệt đối. Khi file/link/directory có thể thay đổi giữa lúc kiểm tra và lúc thao tác, vẫn tồn tại **TOCTOU** (*time-of-check to time-of-use*). `getAcl` chỉ là metadata đọc ở thời điểm đó; `setAcl` sau đó có thể chạm vào đối tượng khác nếu path bị thay.

Trong công cụ quản trị nhạy cảm, phải phối hợp OS permissions, xác minh đối tượng file, xử lý symlink và cơ chế truy cập phù hợp với filesystem. Đừng xây một hệ thống phân quyền chỉ bằng `Path.normalize()` hoặc `startsWith(root)` trên chuỗi tên rồi tin rằng không thể thoát root.

## 10. Quyền hiệu lực không thể suy ra từ một ACE

Một tình huống dễ hiểu sai:

~~~text
ACE: ALLOW READ_DATA for user A
Thực tế: user A vẫn không đọc được file.
~~~

Điều đó không tự mâu thuẫn. Có thể có:

- Entry DENY hoặc rule khác theo mô hình native.
- Không có quyền duyệt parent directory.
- User process không thuộc đúng group/principal được nghĩ tới.
- Chính sách OS, mức đặc quyền hoặc security context ngăn truy cập.
- File/symlink bị thay đổi trước khi mở.
- Mapping provider không diễn giải được entry như dự kiến.

`Files.isReadable(file)` là kiểm tra best-effort dưới danh tính hiện tại, cũng **không** tính một cách đầy đủ quyền hiệu lực của một principal khác. Để xác nhận chính sách bảo mật, cần dùng tài khoản thử có quyền hợp lệ, kiểm tra việc mở file/ghi file thật trong môi trường test và xử lý lỗi của thao tác đó.

ACL view còn có `getOwner()` vì kế thừa `FileOwnerAttributeView`, nhưng owner không đồng nghĩa ACL và `view.setOwner(...)` cũng khác `view.setAcl(...)`.

## 11. Những lỗi và ngoại lệ quan trọng

| Tình huống | Biểu hiện | Xử lý phù hợp |
| --- | --- | --- |
| Không hỗ trợ ACL view | `getFileAttributeView(...) == null` | Dừng ACL workflow hoặc dùng mô hình hỗ trợ khác theo đặc tả |
| File bị xóa / đường dẫn thay đổi | `NoSuchFileException` hoặc `IOException` | Không tin vào kết quả kiểm tra trước |
| Không đủ quyền đọc/ghi ACL | `AccessDeniedException` hoặc `IOException` | Báo lỗi và không leo thang quyền tùy tiện |
| Principal không tồn tại | `UserPrincipalNotFoundException` | Kiểm tra account/domain/lookup |
| Principal thuộc provider khác | `ProviderMismatchException` | Lookup ở filesystem đích |
| ACL không hợp lệ, mapping không bảo đảm đúng | `IOException` khi `setAcl` | Không ghi đè mù; kiểm tra policy/native ACL |
| Lookup không hỗ trợ | `UnsupportedOperationException` | Xử lý giới hạn provider |
| Writer khác thay ACL sau khi đọc | Xung đột logic hoặc mất cập nhật | Phối hợp concurrency, không chỉ retry ACL cũ |
| Không hỗ trợ flags/loại ACE cụ thể | Ánh xạ hoặc bỏ qua tùy contract | Kiểm tra lại ACL và quyền thật trên OS |

Lưu ý lỗi có thể xuất hiện tại **thời điểm gọi API**, không phải chỉ ở bước lấy view. Ví dụ `view != null` nhưng `getAcl()` ném `IOException` vì thiếu quyền, filesystem vừa thay đổi hoặc I/O lỗi.

Bắt `Exception` rồi trả danh sách trống là một anti-pattern nguy hiểm: một ACL thật không đọc được do lỗi quyền không đồng nghĩa file **không có ACE**. Cần thông báo đầy đủ để quyết định nghiệp vụ không bị xây trên một trạng thái giả.

## 12. Các sai lầm thường gặp

**Sai lầm 1: “Sửa List trả từ getAcl sẽ tự thay file.”**  
Không; List là dữ liệu trong bộ nhớ. Chỉ khi được ủy quyền và gọi `setAcl` thành công mới yêu cầu ghi ACL thật.

**Sai lầm 2: “`setAcl(List.of(newRule))` thêm quyền mà giữ nguyên rule cũ.”**  
Không. `setAcl` thay thế ACL, có thể xóa entry cũ; rất nguy hiểm khi quản trị file dùng chung.

**Sai lầm 3: “ACL có thể sort theo account để dễ nhìn.”**  
Không tự sort danh sách sẽ ghi lại. ACL là ordered list và thứ tự có thể ảnh hưởng quyền hiệu lực.

**Sai lầm 4: “ALLOW READ_DATA nghĩa là chắc chắn đọc file được.”**  
Không. Quyền parent directory, DENY, account và OS policy có thể ngăn.

**Sai lầm 5: “Có FileOwnerAttributeView là chắc chắn có AclFileAttributeView.”**  
Không. ACL view mở rộng owner view, nhưng provider chỉ có owner không nhất thiết hỗ trợ ACL.

**Sai lầm 6: “Tất cả Linux/Windows/ZIP providers đều triển khai ACL giống nhau.”**  
Không. Phải kiểm tra view, ánh xạ native và policy mỗi filesystem.

**Sai lầm 7: “AclEntry.Builder tạo rule là đã cấp quyền.”**  
Không. Builder chỉ tạo đối tượng Java. Chưa có write operation trên file.

**Sai lầm 8: “Inheritance flags chắc chắn áp dụng ngay cho mọi file con đã tồn tại.”**  
Không. Inheritance phụ thuộc việc tạo/nhận ACL ở filesystem và policy của OS.

**Sai lầm 9: “AUDIT/ALARM chắc chắn ghi log bảo mật.”**  
Không. Provider có thể bỏ qua khi không có mapping.

**Sai lầm 10: “Nhận một account name string là đủ để set ACL.”**  
Không. Cần lookup principal đúng provider và ủy quyền người yêu cầu.

**Sai lầm 11: “Nếu đọc ACL được thì set ACL chắc chắn được.”**  
Không. Đọc metadata và thay quyền là hai mức đặc quyền khác nhau.

**Sai lầm 12: “`NOFOLLOW_LINKS` loại hết mọi rủi ro security.”**  
Không. Nó chỉ thay cách xử lý link trong một API; TOCTOU và quyền hệ điều hành cần giải quyết riêng.

## 13. Bài tập thực hành có đáp án

**Câu 1.** `AclFileAttributeView` có những phương thức chính nào?

**Đáp án:** `getAcl()` và `setAcl(List<AclEntry>)`; vì mở rộng `FileOwnerAttributeView` nên có cả `getOwner()` và `setOwner()`.

**Câu 2.** `AclEntry` gồm bốn thành phần gì?

**Đáp án:** `type`, `principal`, `permissions`, `flags`.

**Câu 3.** Có thể gọi `new AclEntry()` để tạo entry không?

**Đáp án:** Không. Dùng `AclEntry.newBuilder()`, cấu hình các thành phần rồi `build()`. Entry được tạo là immutable.

**Câu 4.** Một ACE `AclEntryType.ALLOW` chứa `READ_DATA`; có bảo đảm tất cả các chương trình của user đó đọc được file không?

**Đáp án:** Không; policy và những rule khác, quyền parent directory, security context và trạng thái filesystem có thể ảnh hưởng.

**Câu 5.** Khi gọi `Files.getAttribute(file, "acl:acl")`, kiểu trả về ở compile time là gì?

**Đáp án:** `Object`. `getAcl()` có kiểu `List<AclEntry>` nên rõ ràng hơn khi làm việc trực tiếp với ACL.

**Câu 6.** `getAcl()` trả List có thể sửa. `entries.add(rule)` đã đổi quyền file chưa?

**Đáp án:** Chưa. Cần `setAcl(entries)` thành công nếu thực sự có quyền và yêu cầu thay ACL.

**Câu 7.** Vì sao không nên gọi `view.setAcl(List.of(rule))` để “chỉ thêm quyền đọc”?

**Đáp án:** Vì API **thay toàn bộ ACL** bằng danh sách cung cấp. Việc này có thể làm mất những entry quan trọng đang có.

**Câu 8.** Vì sao cần `UserPrincipalLookupService` từ `path.getFileSystem()`?

**Đáp án:** Principal và cách phân giải tên phụ thuộc provider; một principal của provider khác có thể dẫn đến `ProviderMismatchException` khi ghi.

**Câu 9.** Trong ví dụ, vì sao không gọi helper `replaceAclIfAuthorized`?

**Đáp án:** Để không thay quyền truy cập thật trong một bài học, nhất là khi chưa được cấp quyền thay đổi ACL. Code đã được compiler xác nhận, còn thực thi cần quy trình quản trị được phép.

**Câu 10.** `AclEntryFlag.FILE_INHERIT` bảo đảm mọi file con hiện tại đều đã nhận rule đó chưa?

**Đáp án:** Chưa. Inheritance là ngữ nghĩa filesystem, có thể chỉ áp dụng khi tạo đối tượng mới và phụ thuộc provider. Phải đọc ACL thực của file con khi cần xác minh.

**Câu 11.** Một filesystem chỉ có POSIX mode bits nhưng không có ACL view. Có nghĩa nó không thể chặn truy cập không?

**Đáp án:** Không. POSIX permissions là một mô hình kiểm soát quyền khác. Không hỗ trợ `AclFileAttributeView` không có nghĩa thiếu mọi cơ chế access control.

**Câu 12.** Hai writer đọc ACL cùng lúc rồi mỗi bên thêm một entry và gọi `setAcl`. Có thể mất cập nhật không?

**Đáp án:** Có. API không cung cấp compare-and-swap cho cả quy trình read-modify-write; writer sau có thể thay toàn bộ danh sách bằng snapshot cũ đã sửa.

## 14. Checklist và nguồn chính thức

- [ ] Xác định ACL view có được provider hỗ trợ và kiểm tra `view != null`.
- [ ] Nhớ ACL là **danh sách `List<AclEntry>` có thứ tự**, không phải set không thứ tự.
- [ ] Phân biệt `AclEntryType.ALLOW`, `AclEntryType.DENY`, `AUDIT` và `ALARM`.
- [ ] Kiểm tra `AclEntryPermission` theo nguyên tắc **least privilege**.
- [ ] Hiểu `AclEntryFlag` là cờ inheritance và propagation phụ thuộc provider.
- [ ] Dùng `AclEntry.newBuilder()` hoặc `newBuilder(existing)` để tạo immutable ACE.
- [ ] `getAcl()` chỉ đọc; `setAcl(list)` **thay toàn bộ** ACL thực.
- [ ] Không dùng `getAcl()` + `setAcl()` như một transaction có CAS.
- [ ] Lookup principal từ đúng filesystem, không tự đoán account OS.
- [ ] Khi phải ghi, có authorization, backup/snapshot, review thứ tự, xác nhận hiệu lực và audit.
- [ ] Đọc lại ACL để kiểm tra mapping, nhưng không cho rằng quyền thật chỉ phụ thuộc vào metadata đọc được.
- [ ] Với symlink, đặt chính sách `NOFOLLOW_LINKS` và xét race/TOCTOU.
- [ ] Nếu ACL view không hỗ trợ, không tự coi mọi file đều không có security.
- [ ] Không dùng ví dụ học Java để thay ACL file người dùng hoặc file hệ thống.
- [ ] Chỉ sử dụng API hiện vẫn được hỗ trợ trên JDK hiện đại, tránh kiến thức legacy.

**Javadoc Java SE 21:**

- [AclFileAttributeView](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): đọc/thay ACL, kế thừa owner view, mapping và dynamic attributes.
- [AclEntry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclEntry.html): bốn thành phần của ACE, builder, tính immutable.
- [AclEntryType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclEntryType.html): ALLOW, DENY, AUDIT, ALARM.
- [AclEntryPermission](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclEntryPermission.html): các quyền có thể mô tả trong entry.
- [AclEntryFlag](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclEntryFlag.html): inheritance flags.
- [UserPrincipalLookupService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/UserPrincipalLookupService.html): lookup user/group theo provider.
- [Files.getFileAttributeView](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#getFileAttributeView(java.nio.file.Path,java.lang.Class,java.nio.file.LinkOption...)): lấy view và tùy chọn symlink.
- [PosixFileAttributeView](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): mô hình POSIX liên quan.
- [LinkOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html): chính sách `NOFOLLOW_LINKS`.

**Kết luận:** `AclFileAttributeView` giúp chương trình Java đọc và quản lý danh sách **ACE có thứ tự** khi filesystem hỗ trợ. Muốn làm đúng, không chỉ biết cú pháp `getAcl` / `setAcl` mà còn phải hiểu danh tính principal, quyền, thứ tự, inheritance, provider mapping và quyền quản trị. Bài học nên bắt đầu bằng đọc ACL và tạo rule trong bộ nhớ; mọi thao tác ghi ACL thật phải đi qua chính sách an toàn được ủy quyền.
