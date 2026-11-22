# Owner, UserPrincipal và AclFileAttributeView trong Java NIO.2

## 1. Mục tiêu bài học

Khi đọc/ghi tệp, ngoài nội dung byte và đường dẫn, hệ thống tệp còn lưu **thuộc tính** như chủ sở hữu (owner) và quy tắc truy cập. Java NIO.2 cung cấp các API để tra cứu người dùng/nhóm và, trên các hệ thống hỗ trợ, đọc hoặc cập nhật danh sách kiểm soát truy cập **ACL (Access Control List)**.

Ba khái niệm trọng tâm:

- **Owner**: một danh tính được hệ thống tệp ghi nhận là chủ sở hữu của tệp/thư mục. Trong Java, owner được biểu diễn qua `UserPrincipal`.
- **`UserPrincipal`**: giao diện mô tả danh tính người dùng, có phương thức `getName()`. `GroupPrincipal` mở rộng `UserPrincipal` cho danh tính nhóm; danh tính thực được quản lý bởi filesystem/provider/hệ điều hành.
- **`AclFileAttributeView`**: giao diện NIO.2 dùng để lấy/chỉnh ACL dạng có thứ tự và làm việc với chủ sở hữu khi filesystem hỗ trợ mô hình quyền tương ứng.

Sau bài này, bạn sẽ biết:

1. Đọc owner bằng `Files.getOwner(path)`, phân biệt thao tác đọc và thay đổi owner.
2. Tra cứu danh tính bằng `UserPrincipalLookupService` và hiểu vì sao tên hiển thị không đủ để khẳng định cùng một tài khoản.
3. Kiểm tra khả năng hỗ trợ ACL trước khi gọi `getAcl()`/`setAcl()`.
4. Phân tích `AclEntry`: principal, kiểu entry, quyền, cờ kế thừa, thứ tự.
5. Phân biệt ACL với quyền POSIX (`rwx`), DOS attributes và quyền truy cập hiệu lực của một tiến trình.
6. Xử lý `IOException`, `UnsupportedOperationException`, `SecurityException`, khác biệt provider, symbolic link và race condition.
7. Viết Java 17+ đọc metadata an toàn, đồng thời tránh vô tình thay đổi quyền của tệp thật.

> **Tư duy quan trọng:** đọc được owner **không chứng minh** người đang chạy có thể đọc/ghi tệp; đọc được ACL **không có nghĩa** bạn đã tính được đầy đủ quyền hiệu lực; còn `setAcl()`/`setOwner()` là thao tác thay đổi quyền có rủi ro, cần chính sách rõ ràng.

## 2. Chủ sở hữu (owner) là gì?

Owner thường là danh tính mà filesystem gắn với một đối tượng tệp. Trên hệ Unix/POSIX, tệp có user owner và group owner; trên Windows, owner và DACL là các khái niệm trong security descriptor. Java cung cấp lớp trừu tượng chung, nhưng **quy tắc quản trị và quyền hiệu lực do hệ điều hành và filesystem quyết định**.

Lưu ý:

- Owner không đồng nghĩa tác giả ban đầu hoặc người tạo file mãi mãi; quyền sở hữu có thể được thay đổi theo chính sách của hệ thống.
- Một người là owner không có nghĩa mặc định có mọi quyền đọc/ghi/xóa.
- `UserPrincipal.getName()` là **tên danh tính theo provider**, không phải khóa toàn cục dùng được giữa Windows, Linux và mọi miền tài khoản.
- ACL có thể cấp/khước từ quyền cho các principal khác ngoài owner; nhóm và đặc quyền quản trị có thể tham gia đánh giá quyền.
- File có thể là symlink, và thuộc tính owner của **link** có thể khác owner của **đích**, tùy khả năng hỗ trợ và lựa chọn follow link.

### 2.1. Các API chính

| Mục tiêu | API | Kết quả / giới hạn |
| --- | --- | --- |
| Đọc owner | `Files.getOwner(path)` | `UserPrincipal`; mặc định theo liên kết tượng trưng |
| Đọc owner của link (khi hỗ trợ) | `Files.getOwner(path, NOFOLLOW_LINKS)` | Phụ thuộc provider/link semantics |
| Đặt owner | `Files.setOwner(path, principal)` | Thay metadata; yêu cầu quyền thích hợp |
| Lấy view owner | `Files.getFileAttributeView(path, FileOwnerAttributeView.class)` | Có thể nhận `null` nếu view không được hỗ trợ |
| Lấy ACL view | `Files.getFileAttributeView(path, AclFileAttributeView.class)` | Có thể nhận `null` |
| Đọc ACL | `view.getAcl()` | `List<AclEntry>` có thứ tự |
| Ghi ACL | `view.setAcl(entries)` | Thay thế danh sách ACL; nguy cơ mất quyền nếu làm sai |
| Đọc owner từ ACL view | `view.getOwner()` | `AclFileAttributeView` kế thừa `FileOwnerAttributeView` |
| Tra cứu tài khoản | `FileSystem.getUserPrincipalLookupService()` | `lookupPrincipalByName` hoặc `lookupPrincipalByGroupName` |
| POSIX owner/group/mode | `PosixFileAttributeView` và `Files.readAttributes(..., PosixFileAttributes.class)` | Chỉ với filesystem hỗ trợ POSIX |

`Files.getOwner` và `Files.setOwner` có thể sử dụng cơ chế `FileOwnerAttributeView` theo provider. Khi một tính năng không được hỗ trợ, không ép provider tạo thông tin giả; hãy phát hiện và xử lý đúng.

## 3. `UserPrincipal` và `GroupPrincipal`

`java.nio.file.attribute.UserPrincipal` là một giao diện mở rộng `java.security.Principal`. Phương thức quan trọng là:

```java
String displayName = principal.getName();
```

Danh tính có thể đến từ một hệ thống user/group riêng: tài khoản cục bộ, domain, một filesystem từ xa hoặc mô hình do provider triển khai. **Không tự suy luận** danh tính thật bằng cách so sánh chuỗi tên hiển thị với tên nhập tự do của người dùng.

`GroupPrincipal` là kiểu con của `UserPrincipal` dùng cho **nhóm**. Một entry ACL có thể trỏ tới principal của một user hay một group tùy filesystem.

### 3.1. Tra cứu principal bằng `UserPrincipalLookupService`

Với hệ thống có dịch vụ tra cứu thích hợp:

```java
// Minh họa API; tên tài khoản phải được lấy từ cấu hình tin cậy.
UserPrincipalLookupService lookup =
        path.getFileSystem().getUserPrincipalLookupService();

UserPrincipal user = lookup.lookupPrincipalByName("example-user");
GroupPrincipal group = lookup.lookupPrincipalByGroupName("example-group");
```

**Đoạn này không phải chương trình độc lập**: cần `import java.nio.file.Path;`, `java.nio.file.attribute.*;`, biến `path` hợp lệ và các tài khoản **thực sự tồn tại trong provider**.

Điểm phải nhớ:

- `lookupPrincipalByName` và `lookupPrincipalByGroupName` có thể ném `UserPrincipalNotFoundException` nếu không thấy danh tính.
- Có thể phát sinh `IOException` khi gặp lỗi tra cứu hoặc `SecurityException` nếu môi trường áp chính sách bảo mật tương ứng.
- Tên tài khoản được diễn giải theo hệ thống/provider; `"admin"` hay `"Everyone"` không có nghĩa phổ quát.
- **Không dùng `() -> "somebody"` làm đối tượng principal để gọi `Files.setOwner` trên filesystem thật.** Provider có thể yêu cầu principal do chính nó tạo/tra cứu, hoặc không cho gán.
- `getName()` chỉ cung cấp biểu diễn tên; tính đúng của phép gán quyền cần dựa trên principal mà provider chấp nhận.

### 3.2. Phân biệt “biết tên”, “biết danh tính” và “có quyền”

| Nhận định | Có thể kết luận chỉ từ `getName()`? |
| --- | --- |
| Provider trả một tên danh tính | Có |
| Principal này là cùng tài khoản trên hai máy khác nhau | Không |
| Principal chắc chắn có quyền đọc file | Không |
| Quy tắc ACL đã được thực thi trên filesystem hiện tại | Không |
| Chính ứng dụng có quyền thay owner/ACL | Không |
| User và group với tên tương tự là cùng một loại principal | Không |

Tránh lưu duy nhất một chuỗi tên để dùng lại trên nhiều hệ thống khi chương trình cần độ chính xác về danh tính.

## 4. Đọc owner bằng `Files.getOwner`

Ví dụ API:

```java
Path file = Path.of("data", "report.txt");
UserPrincipal owner = Files.getOwner(file);
System.out.println(owner.getName());
```

Đây là **đoạn minh họa**, không phải chương trình độc lập vì cần import và file có thể chưa tồn tại. Kết quả là tên principal theo provider, **không có stdout cố định**.

Đọc owner có thể gặp:

1. `NoSuchFileException` nếu đường dẫn không tồn tại.
2. `AccessDeniedException` hoặc `IOException` khi filesystem không cho đọc thuộc tính.
3. `UnsupportedOperationException` khi provider không hỗ trợ thuộc tính owner theo cách gọi đó.
4. `SecurityException` nếu có chính sách kiểm soát bảo mật tương ứng.
5. Thay đổi ngoài dự kiến nếu một tiến trình khác sửa/đổi tên tệp giữa lúc kiểm tra và đọc.

### 4.1. Symlink: theo đích hay đọc thuộc tính link?

Thông thường `Files.getOwner(path)` theo symbolic link. Nếu muốn làm việc với chính đối tượng link:

```java
UserPrincipal linkOwner = Files.getOwner(
        path, LinkOption.NOFOLLOW_LINKS);
```

Tuy nhiên, **không phải mọi provider đều hỗ trợ cùng semantics** cho owner của symlink. Có thể không hỗ trợ thao tác; cần thử nghiệm trên môi trường sẽ triển khai. `NOFOLLOW_LINKS` không tự khóa symlink để tránh thay đổi đồng thời (TOCTOU).

### 4.2. Đọc owner từ `FileOwnerAttributeView`

`FileOwnerAttributeView` cho phép lấy/đặt owner qua thuộc tính view:

```java
FileOwnerAttributeView view = Files.getFileAttributeView(
        path, FileOwnerAttributeView.class);

if (view == null) {
    throw new UnsupportedOperationException(
            "Owner view unavailable");
}
UserPrincipal owner = view.getOwner();
```

Đây là đoạn minh họa. Ưu điểm của `view` là bạn có thể làm việc với thuộc tính của filesystem qua một interface xác định. Nếu view là `null`, không được gọi `getOwner()` trên nó.

## 5. ACL là gì? Vì sao khác quyền `rwx`?

**ACL (Access Control List)** là danh sách các quy tắc truy cập gắn với một đối tượng. Mỗi quy tắc thường chỉ rõ:

- **Principal**: ai được nhắc đến (user hoặc group).
- **Type**: cho phép, từ chối hoặc loại thông tin kiểm toán theo mô hình ACL.
- **Permissions**: các hành động như đọc dữ liệu, ghi dữ liệu, đọc ACL, đổi owner.
- **Flags**: một số quy tắc kế thừa hoặc phạm vi áp dụng.

Ví dụ **minh họa**, không khẳng định là ACL thật trên một hệ thống cụ thể:

```text
Entry 1: ALLOW team-editors → READ_DATA, WRITE_DATA
Entry 2: DENY  guest        → WRITE_DATA
Entry 3: ALLOW owner        → READ_DATA, READ_ACL
```

Không coi ACL là một tập quyền không có thứ tự. **Danh sách có thứ tự** và thứ tự entry có thể ảnh hưởng đến cách hệ thống áp dụng chúng. Việc đánh giá quyền hiệu lực còn liên quan token nhóm, inheritance, đặc quyền, policy và filesystem.

### 5.1. POSIX mode và ACL view không đồng nhất

Trên Unix/POSIX, quyền cơ bản thường được thể hiện qua ba nhóm `owner/group/others` và các bit `rwx`. Java cung cấp:

```java
PosixFileAttributes attributes = Files.readAttributes(
        path, PosixFileAttributes.class);
Set<PosixFilePermission> mode = attributes.permissions();
```

Đây là đoạn minh họa cần filesystem hỗ trợ POSIX; không chạy trên mọi Windows filesystem.

`AclFileAttributeView` dành cho mô hình ACL phong phú hơn, thường gắn với các filesystem có ACL kiểu tương thích NFSv4/Windows. **Không giả định** mọi filesystem POSIX đều có `AclFileAttributeView`, cũng không cho rằng ACL kiểu POSIX mặc định được biểu diễn đầy đủ bằng Java `AclFileAttributeView`. Một filesystem có thể cung cấp owner/POSIX view nhưng **không** cung cấp ACL view.

### 5.2. Khác thuộc tính DOS

`DosFileAttributeView` có các cờ như read-only, hidden, system, archive, không phải danh sách user/group ACE. Cờ read-only không thay thế phân tích quyền ACL hoặc POSIX, và `Files.isReadable`/`isWritable` chỉ là kiểm tra khả năng truy cập tại một thời điểm.

## 6. `AclFileAttributeView`: khả năng hỗ trợ và API

Lấy view bằng:

```java
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);
```

Nếu provider không hỗ trợ ACL cho đường dẫn, `view` có thể là **`null`**. Đây là kiểm tra cần thiết trước khi gọi `view.getAcl()`. Nếu view có nhưng thao tác thất bại vì quyền hoặc lỗi I/O, vẫn có thể ném ngoại lệ.

Các thành phần chính:

| API | Vai trò |
| --- | --- |
| `AclFileAttributeView` | View thuộc tính ACL và owner |
| `AclFileAttributeView.getAcl()` | Đọc danh sách `List<AclEntry>` theo thứ tự |
| `AclFileAttributeView.setAcl(List<AclEntry>)` | Đặt **toàn bộ danh sách** ACL theo yêu cầu |
| `AclFileAttributeView.getOwner()` | Đọc owner |
| `AclFileAttributeView.setOwner(UserPrincipal)` | Thay owner theo quyền/provider |
| `AclEntry` | Một quy tắc ACL, thường có principal, type, permissions, flags |
| `AclEntryType` | `ALLOW`, `DENY`, `AUDIT`, `ALARM` |
| `AclEntryPermission` | Các hành động như `READ_DATA`, `WRITE_DATA`, `READ_ACL`, `WRITE_ACL`, `WRITE_OWNER` |
| `AclEntryFlag` | Cờ về cách kế thừa ACE ở thư mục/con |
| `UserPrincipalLookupService` | Tìm danh tính do provider hiểu |

`getAcl()` trả danh sách biểu diễn ACL, có thể rỗng trên một số file/provider. **Đừng sắp xếp lại theo tên user**; entry order có thể có ý nghĩa khi đánh giá quyền.

### 6.1. Đọc danh sách ACL

Đoạn code minh họa:

```java
AclFileAttributeView view =
        Files.getFileAttributeView(path, AclFileAttributeView.class);

if (view != null) {
    List<AclEntry> entries = view.getAcl();
    for (int i = 0; i < entries.size(); i++) {
        AclEntry entry = entries.get(i);
        System.out.println(i + " " + entry.type()
                + " principal=" + entry.principal().getName()
                + " permissions=" + entry.permissions()
                + " flags=" + entry.flags());
    }
}
```

Đây **không phải class chạy độc lập** vì chưa khai báo import và `path`. Kết quả phụ thuộc ACL thực và không có stdout chung.

Không log danh sách ACL nhạy cảm ra nơi công khai. Trong chương trình thật, phân quyền cho chức năng xem ACL và xử lý lỗi riêng theo từng tệp.

### 6.2. Kiểm tra khả năng hỗ trợ qua `FileStore`

`FileStore.supportsFileAttributeView(AclFileAttributeView.class)` là tín hiệu về khả năng hỗ trợ của file store, ví dụ:

```java
boolean storeSaysAcl = Files.getFileStore(path)
        .supportsFileAttributeView(AclFileAttributeView.class);
```

Đây là đoạn minh họa (cần import và `path`). Nó không phải sự đảm bảo rằng **mọi đường dẫn/thao tác** đều cấp quyền đọc hoặc chỉnh ACL; kiểm tra view cụ thể rồi gọi thao tác thật và bắt ngoại lệ vẫn là bắt buộc. `getFileStore` bản thân cũng có thể ném `IOException`.

## 7. `AclEntry` gồm những gì?

Một entry có các thuộc tính bất biến:

- `entry.principal()` — danh tính bị ảnh hưởng.
- `entry.type()` — loại (allow/deny/audit/alarm).
- `entry.permissions()` — tập các `AclEntryPermission`.
- `entry.flags()` — các `AclEntryFlag`.

### 7.1. Các kiểu ACL entry

| `AclEntryType` | Ý nghĩa khái quát |
| --- | --- |
| `ALLOW` | Quy tắc cấp các quyền chỉ định |
| `DENY` | Quy tắc phủ nhận các quyền chỉ định |
| `AUDIT` | Quy tắc liên quan ghi nhận các truy cập theo policy |
| `ALARM` | Quy tắc liên quan báo hiệu truy cập theo policy |

Cách thực thi audit/alarm và hỗ trợ từng entry type phụ thuộc nền tảng/provider. Không coi việc tạo được một đối tượng `AclEntry` trong bộ nhớ là bằng chứng filesystem sẽ chấp nhận `setAcl` với entry đó.

### 7.2. Các quyền thường gặp

| Quyền | Đối tượng thao tác theo ngữ cảnh |
| --- | --- |
| `READ_DATA` / `LIST_DIRECTORY` | Đọc dữ liệu file hoặc liệt kê nội dung thư mục |
| `WRITE_DATA` / `ADD_FILE` | Ghi dữ liệu file hoặc thêm file trong directory |
| `APPEND_DATA` / `ADD_SUBDIRECTORY` | Nối dữ liệu file hoặc thêm directory con |
| `READ_NAMED_ATTRS` | Đọc các thuộc tính được đặt tên |
| `WRITE_NAMED_ATTRS` | Ghi các thuộc tính được đặt tên |
| `EXECUTE` | Chạy file hoặc đi qua thư mục theo semantics filesystem |
| `DELETE` | Xóa đối tượng |
| `DELETE_CHILD` | Xóa mục con trong thư mục |
| `READ_ATTRIBUTES` / `WRITE_ATTRIBUTES` | Đọc/ghi thuộc tính cơ bản |
| `READ_ACL` / `WRITE_ACL` | Đọc/ghi danh sách ACL |
| `WRITE_OWNER` | Thay đổi thông tin owner |
| `SYNCHRONIZE` | Khả năng đồng bộ truy cập theo mô hình ACL |

Một vài cặp tên quyền là **alias/cách dùng theo kiểu đối tượng** trong Java; ví dụ `READ_DATA` và `LIST_DIRECTORY` mô tả cùng bit tương ứng nhưng mang ý nghĩa file hoặc directory khác nhau. Không tự dựng mô hình “mỗi tên là một bit độc lập” nếu API khai báo tương đương.

### 7.3. Các cờ kế thừa

| Cờ | Vai trò khái quát |
| --- | --- |
| `FILE_INHERIT` | Quy tắc có thể được kế thừa bởi file con |
| `DIRECTORY_INHERIT` | Quy tắc có thể được kế thừa bởi thư mục con |
| `NO_PROPAGATE_INHERIT` | Hạn chế phạm vi lan truyền kế thừa |
| `INHERIT_ONLY` | Entry dành cho kế thừa, không áp trực tiếp ở đối tượng hiện tại theo semantics thích hợp |

Không suy từ các tên cờ rằng mọi filesystem đều triển khai kế thừa như nhau. Đặc biệt, **ACL kế thừa** từ thư mục cha có thể dẫn tới những ACE mới khi file được tạo, tùy chính sách hệ thống.

## 8. Java 17+ hoàn chỉnh: tạo một `AclEntry` minh họa trong bộ nhớ

Ví dụ này **không sửa ACL thật**. Nó sử dụng một `UserPrincipal` giả lập chỉ để học về object model. Bản thân `AclEntry` được tạo qua builder; không mở filesystem.

Lưu vào tệp **`AclEntryModelDemo.java`**:

```java
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclEntryPermission;
import java.nio.file.attribute.AclEntryType;
import java.nio.file.attribute.UserPrincipal;

public class AclEntryModelDemo {
    public static void main(String[] args) {
        // Demo principal only; never pass it to Files.setOwner.
        UserPrincipal demo = () -> "demo-user";

        AclEntry entry = AclEntry.newBuilder()
                .setType(AclEntryType.ALLOW)
                .setPrincipal(demo)
                .setPermissions(
                        AclEntryPermission.READ_DATA,
                        AclEntryPermission.READ_ACL)
                .build();

        System.out.println("Type: " + entry.type());
        System.out.println("Principal: "
                + entry.principal().getName());
        System.out.println("Can read data: "
                + entry.permissions().contains(
                        AclEntryPermission.READ_DATA));
        System.out.println("Can write ACL: "
                + entry.permissions().contains(
                        AclEntryPermission.WRITE_ACL));
        System.out.println("Has inheritance flags: "
                + !entry.flags().isEmpty());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 AclEntryModelDemo.java
java AclEntryModelDemo
```

**Stdout chính xác:**

```text
Type: ALLOW
Principal: demo-user
Can read data: true
Can write ACL: false
Has inheritance flags: false
```

**Giải thích:**

1. `demo` là `UserPrincipal` tự cài đặt với tên cố định; nó chỉ dùng để minh họa mô hình dữ liệu trong RAM.
2. Builder gán kiểu `ALLOW` và các quyền `READ_DATA`, `READ_ACL`.
3. Không thêm `WRITE_ACL`, nên kiểm tra membership cho quyền đó trả `false`.
4. Không gọi `setFlags`; tập flags rỗng.
5. **Không có file nào bị cấp quyền**. Entry này chỉ là object Java; để áp dụng ACL thực cần view hỗ trợ, principal hợp lệ do provider chấp nhận và quyền sửa ACL của người gọi.

Không diễn giải dòng `Can read data: true` là “tiến trình hiện tại có quyền đọc một tệp”: nó chỉ nói rằng **entry giả lập chứa bit `READ_DATA`**.

## 9. Java 17+ hoàn chỉnh: kiểm tra owner và ACL thực ở chế độ chỉ đọc

Ví dụ dưới đây **không thay owner/ACL**. Chương trình chỉ quan sát một đường dẫn do người dùng chỉ định. Nếu không cung cấp đường dẫn, nó thông báo cách dùng, tránh tự quét thư mục.

Lưu thành **`OwnerAclInspect.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.FileOwnerAttributeView;
import java.nio.file.attribute.UserPrincipal;
import java.util.List;

public class OwnerAclInspect {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("Usage: java OwnerAclInspect <path>");
            return;
        }

        Path path = Path.of(args[0]);
        try {
            FileOwnerAttributeView ownerView =
                    Files.getFileAttributeView(
                            path, FileOwnerAttributeView.class);

            if (ownerView == null) {
                System.out.println("Owner view: unsupported");
            } else {
                UserPrincipal owner = ownerView.getOwner();
                System.out.println("Owner: " + owner.getName());
            }

            AclFileAttributeView aclView =
                    Files.getFileAttributeView(
                            path, AclFileAttributeView.class);

            if (aclView == null) {
                System.out.println("ACL view: unsupported");
                return;
            }

            List<AclEntry> entries = aclView.getAcl();
            System.out.println("ACL entries: " + entries.size());

            for (int index = 0; index < entries.size(); index++) {
                AclEntry entry = entries.get(index);
                System.out.println(index + ": "
                        + entry.type()
                        + " principal=" + entry.principal().getName()
                        + " permissions=" + entry.permissions()
                        + " flags=" + entry.flags());
            }
        } catch (IOException failure) {
            System.err.println("I/O error: "
                    + failure.getClass().getSimpleName());
        } catch (UnsupportedOperationException failure) {
            System.err.println("Unsupported view operation");
        } catch (SecurityException failure) {
            System.err.println("Security policy denied operation");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OwnerAclInspect.java
java OwnerAclInspect
java OwnerAclInspect my-file.txt
```

Với lệnh **không có đối số**, stdout xác định là:

```text
Usage: java OwnerAclInspect <path>
```

Với `java OwnerAclInspect my-file.txt`, **không có một stdout cố định chung**: đường dẫn có thể không tồn tại, owner khác nhau, view ACL có thể không được hỗ trợ, số lượng/quy tắc entry khác nhau hoặc có lỗi quyền. Điều này là hành vi đúng với API phụ thuộc filesystem.

**Điểm học tập:**

- Kiểm tra `ownerView == null` và `aclView == null` trước khi gọi phương thức.
- Đọc `getAcl()` chỉ khi ACL view hiện diện.
- In `entry.type()`, principal, quyền và flags đúng theo thứ tự từ `List`; code **không sort hoặc đổi ACL**.
- Phân biệt lỗi I/O, view không hỗ trợ và chính sách bảo mật.
- Không gọi `Files.setOwner`, `view.setOwner` hay `view.setAcl`; đây là ví dụ có thể dùng để nghiên cứu metadata an toàn ở chế độ **chỉ đọc**.
- Với path là symlink, mặc định các lời gọi attribute view thường theo link. Nếu muốn xem chính link, cân nhắc overload với `LinkOption.NOFOLLOW_LINKS` và khả năng hỗ trợ thực tế.

## 10. Thay owner bằng `Files.setOwner` — khi nào nên làm?

API:

```java
Files.setOwner(path, principal);
```

Đây là thao tác **thay đổi metadata bảo mật**, không phải lệnh “đặt tên hiển thị cho file”. Khi provider cho phép, caller phải có quyền cần thiết. Người được gán owner nên là `UserPrincipal` phù hợp với filesystem/provider của đường dẫn.

Quy trình có kiểm soát:

1. Chọn một tệp thử trong vùng **do bạn sở hữu**, không dùng tệp cấu hình hệ thống hoặc dữ liệu quan trọng.
2. Xác định provider/owner view có hỗ trợ không.
3. Tra cứu danh tính đích qua `UserPrincipalLookupService` của cùng filesystem (nếu cần).
4. Xác minh tài khoản đích theo chính sách tổ chức; không chấp nhận một tên tùy ý từ request để cấp quyền.
5. Thực hiện `Files.setOwner` với handling `IOException`, `UnsupportedOperationException` và `SecurityException`.
6. Đọc lại `Files.getOwner` và đánh giá theo identity/provider, không chỉ hiển thị tên.
7. Ghi audit về việc ai yêu cầu, tệp nào và kết quả thay đổi quyền.

**Chỉ dùng đoạn sau như cấu trúc API, không thực thi trên file thật nếu không có quyền và quy trình kiểm soát:**

```java
// Minh họa: path và trustedUserName do ứng dụng xác thực cung cấp.
var lookup = path.getFileSystem().getUserPrincipalLookupService();
var newOwner = lookup.lookupPrincipalByName(trustedUserName);
Files.setOwner(path, newOwner);
```

Đây là **đoạn minh họa không độc lập**; không tự suy luận tên người dùng cần gán từ dữ liệu bên ngoài. Không tạo user mới: principal lookup là tra cứu, không phải provisioning tài khoản.

### 10.1. Thay owner không phải tự động cấp quyền đọc/ghi

Sau khi đổi owner, ACL có thể vẫn giữ các entry hiện có; POSIX modes/nhóm và chính sách hệ thống còn ảnh hưởng. Đừng cho rằng `setOwner` thay thế được `setAcl` hoặc ngược lại. Nếu cần “user X có quyền Y”, hãy xây chính sách quyền cụ thể và kiểm chứng phù hợp với provider, thay vì chỉ đổi owner.

## 11. Thay ACL bằng `setAcl`: rủi ro và quy trình an toàn

API:

```java
view.setAcl(entries);
```

Đây **không phải thao tác cộng thêm một dòng ACL đơn giản**. Nó yêu cầu provider áp dụng **danh sách entry mới** theo hợp đồng view. Nếu xây danh sách chỉ gồm một ACE rồi gọi `setAcl`, bạn có thể vô tình xóa các quyền hiện có hoặc khóa chính mình khỏi tài nguyên.

### 11.1. Quy trình có kiểm soát (không tự chạy trên tệp thật)

1. Kiểm tra `AclFileAttributeView` hỗ trợ và caller có quyền thay ACL.
2. Đọc **toàn bộ** danh sách hiện có qua `getAcl()`; ghi nhận thứ tự, principal, flags và quyền.
3. Xác định thay đổi đúng theo yêu cầu nghiệp vụ; tránh tự “sort” danh sách hoặc bỏ các ACE chưa hiểu.
4. Tra cứu đúng `UserPrincipal` hoặc `GroupPrincipal` qua provider, không gán principal giả từ `UserPrincipal` lambda của demo.
5. Xây danh sách mới với `AclEntry.newBuilder()`, giữ những entry cần bảo toàn và xác định thứ tự theo mô hình filesystem.
6. Kiểm thử trên tệp thử riêng, kiểm tra quyền trước/sau; chuẩn bị kế hoạch phục hồi nếu khóa quyền quản trị.
7. Gọi `setAcl` và đọc lại `getAcl` để kiểm tra kết quả, xử lý thay đổi ngoài dự kiến; lưu audit.
8. Nhớ rằng giữa đọc và ghi ACL, tiến trình khác có thể thay đổi ACL: đây là **time-of-check-to-time-of-use**. Nếu cần đồng bộ nghiêm ngặt, dùng cơ chế quản trị phù hợp, không giả định view có compare-and-swap.
9. Chuẩn bị cho trường hợp `setAcl` thất bại và trạng thái sau lỗi cần được xác minh lại; không hứa sẽ có rollback nguyên tử trên mọi provider.

### 11.2. Vì sao không nên chuyển ACL thành `Set`?

`AclFileAttributeView.getAcl()` trả **`List<AclEntry>`**, tức có thứ tự. Chuyển thành `HashSet` rồi ghi ngược làm mất thứ tự, có thể thay đổi cách diễn giải. Không “chuẩn hóa” thứ tự tùy ý theo tên user hoặc enum type trừ khi thực sự hiểu quy tắc của filesystem.

### 11.3. ACL không phải công cụ thay thế nguyên tắc phân quyền

Đừng cấp quyền `WRITE_ACL` hoặc `WRITE_OWNER` khi yêu cầu chỉ là đọc nội dung; đó là quyền quản trị rất mạnh. Tuân theo nguyên tắc **least privilege**, tách quyền đọc dữ liệu khỏi quyền sửa bảo mật, và kiểm tra các ACE được kế thừa có phù hợp không.

## 12. Tính quyền hiệu lực: nhiều yếu tố hơn một ACE

Khi `getAcl()` cho biết một ACE `ALLOW user → READ_DATA`, ta **chưa** biết người dùng có thể đọc dữ liệu trong mọi trường hợp:

- Có thể tồn tại ACE khác với kiểu `DENY` hoặc thứ tự/di sản ACL ảnh hưởng.
- User có thể thuộc nhiều nhóm với các entry khác nhau.
- File có thể nằm dưới các thư mục cha không cho traverse.
- Hệ thống còn áp dụng share permissions, sandbox, mount flags, lock/policy, filesystem restrictions.
- Người đang chạy có thể là một principal khác với principal được hiển thị.
- ACL có thể thay đổi ngay sau khi bạn đọc.

`Files.isReadable(path)`/`isWritable(path)` là **kiểm tra tại thời điểm gọi**, không phải quyết định bảo mật bất biến. Khi thực sự mở/đọc/ghi, phải xử lý lỗi của thao tác đó; đừng sử dụng kiểm tra metadata làm bước phê duyệt quyền duy nhất.

### 12.1. Owner, ACL và POSIX trong một hệ thống hỗn hợp

Đối với ứng dụng Java chạy trên Linux lẫn Windows:

- Kiểm tra các view có sẵn (`basic`, `posix`, `acl`, `owner` tùy provider).
- Không tự chuyển ACL Windows 1:1 thành `rwx` POSIX.
- Nếu chỉ muốn cho user hiện tại tạo/đọc file theo chính sách ứng dụng, đôi khi **đặt permission khi tạo file** thích hợp hơn là sửa ACL hậu kỳ.
- Với yêu cầu kiểm toán quyền có tính pháp lý/vận hành, dùng API/công cụ quản trị chuyên biệt của platform; Java view không trình bày toàn bộ lớp chính sách bảo mật của hệ thống.

## 13. Symbolic link, chủ sở hữu và race condition

### 13.1. Đọc attribute của link hay đích?

Các API NIO.2 thường theo symbolic link theo mặc định. Overload nhận `LinkOption.NOFOLLOW_LINKS` giúp bày tỏ ý định thao tác trên link thay vì đích, **khi provider hỗ trợ**:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path, AclFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là đoạn minh họa. Nó không đảm bảo mọi provider cung cấp ACL của symlink hay cho phép sửa nó.

### 13.2. Thay đổi giữa lúc kiểm tra và sử dụng

Giả sử ứng dụng:

1. Kiểm tra `Files.getOwner(path)`.
2. Đọc `view.getAcl()`.
3. Sau đó mới mở file bằng `Files.newOutputStream(path)`.

Nếu path/symlink bị tiến trình khác thay đổi giữa các bước, file được mở có thể khác file đã kiểm tra. Đây là vấn đề **TOCTOU**. Không xem `getOwner`, `getAcl` hoặc `Path.normalize()` là khóa tài nguyên.

Khi thiết kế thao tác cần an toàn cao với path không tin cậy, cân nhắc mô hình mở bằng handle/directory stream và các API an toàn hơn nếu provider hỗ trợ; luôn giới hạn quyền trên filesystem, phân quyền tiến trình và quản lý quyền ghi vào thư mục cha.

## 14. Xử lý lỗi thực tế

| Tình huống | Hành vi/ngoại lệ có thể gặp | Cách phản ứng |
| --- | --- | --- |
| File không tồn tại | `NoSuchFileException` | Kiểm tra nguồn/đường dẫn, không giả định metadata có |
| Không có quyền đọc thuộc tính | `AccessDeniedException`, `IOException` | Báo quyền; không “fallback” sang cấp quyền rộng |
| ACL view không có | `null` từ `getFileAttributeView` | Thông báo không hỗ trợ, không gọi view |
| View được tạo nhưng method không hỗ trợ | `UnsupportedOperationException` | Phân biệt với dữ liệu rỗng |
| Principal không tìm thấy | `UserPrincipalNotFoundException` | Kiểm tra tên/miền tài khoản |
| Principal không phù hợp provider | Lỗi provider / ngoại lệ từ thao tác set | Không dùng principal tự tạo để set owner/ACL |
| Đổi owner/ACL bị từ chối | `IOException` hoặc `SecurityException` | Báo lỗi; giữ audit, không retry mù |
| Symlink/target bị thay đổi | Metadata không còn đúng tại lúc dùng | Áp dụng chính sách tài nguyên/TOCTOU |
| `getAcl()` chứa principal lạ | Entry hợp lệ ở mô hình provider nhưng người đọc không hiểu | Giữ nguyên; không xóa hoặc sắp xếp lại tùy tiện |
| ACL ghi thành công nhưng truy cập vẫn bị từ chối | Có thể do các lớp quyền khác | Kiểm tra toàn bộ chính sách thay vì cấp thêm `WRITE_ACL` |

Không nuốt mọi ngoại lệ bằng `catch (Exception ignored)`. Nếu chức năng chỉ để báo cáo quyền, hãy cho thấy **view không hỗ trợ**, **không có quyền** và **không thấy file** là ba trạng thái khác nhau.

## 15. Sai lầm thường gặp

1. Nhầm **owner** với “tài khoản có toàn quyền”.
2. Nhầm `UserPrincipal.getName()` với danh tính có thể so sánh toàn cầu.
3. Nghĩ rằng mọi hệ thống tệp hỗ trợ `AclFileAttributeView`.
4. Gọi `view.getAcl()` ngay khi `view == null`.
5. Cho rằng `getAcl()` trả đủ thông tin để tính chính xác quyền hiệu lực của một user bất kỳ.
6. Nhầm `PosixFilePermissions` (`rwx`) với ACL phong phú kiểu Windows.
7. Không phân biệt `FileOwnerAttributeView` và `AclFileAttributeView`.
8. Dùng principal giả bằng lambda của ví dụ để `Files.setOwner` trên máy thật.
9. Dùng `setAcl` với danh sách chỉ chứa một ACE mà không bảo toàn ACL cũ.
10. Chuyển `List<AclEntry>` sang `Set`, làm mất thứ tự.
11. Cấp `WRITE_ACL` hoặc `WRITE_OWNER` khi chỉ muốn cho phép đọc dữ liệu.
12. Bỏ qua các flags kế thừa và đánh giá ACL của thư mục cha.
13. Cho rằng `NOFOLLOW_LINKS` có semantics giống nhau trên mọi provider.
14. Đọc ACL rồi mở file, tin rằng pathname không thể đổi.
15. Ghi cứng tên user như `"Administrator"`/`"root"` và áp dụng cho mọi nền tảng.
16. Gọi `Files.isReadable` rồi tin thao tác đọc tiếp theo chắc chắn thành công.
17. Không xử lý `IOException` khi đổi owner/ACL, không có kế hoạch khôi phục quyền.
18. Log ACL/tên tài khoản ra kênh công khai mà không kiểm soát dữ liệu nhạy cảm.

## 16. Bài tập thực hành và tự kiểm tra

1. **Mô hình:** `AclEntryModelDemo` thêm `WRITE_DATA` vào builder, dự đoán sự thay đổi của kết quả kiểm tra membership.
2. **Quan sát:** chạy `OwnerAclInspect` với file do bạn sở hữu, ghi nhận owner và ACL view có hỗ trợ không. Tại sao bạn không thể dự đoán một danh sách ACL chung cho mọi máy?
3. **View:** kiểm tra `Files.getFileAttributeView(path, FileOwnerAttributeView.class)` khác gì với `AclFileAttributeView.class`. Trên filesystem chỉ hỗ trợ owner, chương trình nên làm gì?
4. **Tra cứu:** viết mã dùng `UserPrincipalLookupService` cho một tài khoản tồn tại thật trên filesystem. Bắt riêng `UserPrincipalNotFoundException`.
5. **Thứ tự ACL:** tại sao việc sort `getAcl()` theo tên principal rồi gọi `setAcl()` có thể làm thay đổi semantics?
6. **Least privilege:** nếu yêu cầu là user chỉ được xem nội dung và thông tin ACL, vì sao không cấp luôn `WRITE_ACL`/`WRITE_OWNER`?
7. **Symlink:** nếu `link` trỏ đến `target`, so sánh ý nghĩa của `Files.getOwner(link)` và `Files.getOwner(link, NOFOLLOW_LINKS)` trên hệ thống hỗ trợ.
8. **POSIX:** thử đọc `PosixFileAttributes.permissions()` trên môi trường hỗ trợ, đối chiếu với ACL view. Vì sao không thể khẳng định hai mô hình tương đương?
9. **Lỗi:** thiết kế đầu ra rõ ràng cho file thiếu, ACL view không hỗ trợ và bị từ chối quyền đọc thuộc tính.
10. **Quy trình sửa ACL:** lập checklist sao lưu, bảo toàn entry cũ, kiểm thử ở file thử, tra cứu principal, ghi audit và xác minh readback trước khi cho phép `setAcl`.
11. **Race:** mô tả vì sao kiểm tra owner/ACL xong vẫn không đảm bảo file mở sau đó là cùng đối tượng.
12. **Đúng phạm vi:** giải thích tại sao việc đọc ACL không tự chứng minh một tiến trình có thể xóa file: quyền xóa có thể liên quan permission trên directory cha và các policy khác.

## 17. Tổng kết

- `Files.getOwner()` trả **`UserPrincipal`** mô tả owner của đường dẫn theo provider; `Files.setOwner()` thay đổi metadata bảo mật và đòi quyền phù hợp.
- `UserPrincipalLookupService` dùng để tìm danh tính hợp lệ; `GroupPrincipal` mô tả nhóm. Tên hiển thị không phải định danh phổ quát cho mọi hệ thống.
- `AclFileAttributeView` cho phép đọc danh sách **`List<AclEntry>` có thứ tự** và, khi được phép, đặt lại ACL. View có thể **không được hỗ trợ**; kiểm tra `null`, xử lý ngoại lệ.
- Mỗi `AclEntry` chứa loại, principal, tập quyền và flags; hỗ trợ/diễn giải ACE phụ thuộc provider và hệ điều hành.
- ACL, POSIX `rwx`, thuộc tính DOS và **quyền hiệu lực** là các lớp khái niệm liên quan nhưng không đồng nhất.
- Đọc owner/ACL có thể hữu ích cho báo cáo, nhưng không phải bảo đảm về file identity hoặc khả năng truy cập ở thời điểm sau đó.
- Khi cần thay ACL/owner, dùng principal được tra cứu qua provider, bảo toàn quy tắc cần thiết, kiểm thử trên tài nguyên riêng, xác minh sau khi ghi và có kế hoạch phục hồi.

**Nguyên tắc cuối cùng:** quản lý owner/ACL là quản lý **quyền truy cập thực tế** của tài nguyên. Hãy kiểm tra tính hỗ trợ và hiểu đầy đủ chính sách quyền của filesystem trước khi thay đổi, thay vì suy ra quyền từ một tên user hay một entry ACL riêng lẻ.