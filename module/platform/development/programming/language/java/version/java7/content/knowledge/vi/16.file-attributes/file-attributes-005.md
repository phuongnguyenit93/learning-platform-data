# Chủ sở hữu tệp và `UserPrincipal` trong Java NIO.2

## 1. Vì sao cần biết chủ sở hữu?

Một file hoặc thư mục không chỉ có tên, đường dẫn và nội dung. File system còn quản lý **thuộc tính** (*metadata*), trong đó có **chủ sở hữu** (*owner*). Chủ sở hữu thường là một danh tính người dùng hoặc tài khoản hệ thống mà hệ điều hành/file system gắn với đối tượng tệp để phục vụ quản lý và kiểm soát truy cập.

Ví dụ: trong một dịch vụ lưu file, ứng dụng có thể muốn ghi nhận ai đang sở hữu file báo cáo, xác minh metadata sau khi tạo file, hoặc quản trị việc bàn giao ownership của tài nguyên do mình quản lý. Tuy nhiên, **đọc được chủ sở hữu** và **có quyền thay đổi chủ sở hữu** là hai việc hoàn toàn khác.

Từ Java 7, Java NIO.2 cung cấp các API chuẩn hiện vẫn được hỗ trợ:

~~~java
UserPrincipal owner = Files.getOwner(path);
String ownerName = owner.getName();
~~~

Đoạn minh họa cần `Path path` và import `java.nio.file.Files`, `java.nio.file.attribute.UserPrincipal`. Hai lệnh này truy vấn danh tính chủ sở hữu của tệp tại thời điểm gọi; chúng **không tự cấp quyền** cho chương trình.

Các thành phần quan trọng:

- `java.nio.file.Files.getOwner(Path, LinkOption...)` — đọc chủ sở hữu file.
- `java.nio.file.Files.setOwner(Path, UserPrincipal)` — yêu cầu cập nhật chủ sở hữu; chỉ có thể thành công nếu file system và quyền của tiến trình cho phép.
- `java.nio.file.attribute.UserPrincipal` — đối tượng **danh tính** chủ sở hữu, không chỉ là một chuỗi.
- `java.nio.file.attribute.FileOwnerAttributeView` — một *attribute view* hỗ trợ đọc/đổi owner.
- `java.nio.file.attribute.UserPrincipalLookupService` — phân giải tên tài khoản thành đối tượng `UserPrincipal`.
- `PosixFileAttributeView` / `AclFileAttributeView` — các view liên quan đến owner nhưng có những mô hình phân quyền khác nhau.

**Mục tiêu bài học:** đọc owner, hiểu `UserPrincipal`, so sánh với group/permissions/ACL, biết cách lookup và yêu cầu đổi owner có kiểm soát, xử lý provider không hỗ trợ, sự khác biệt Windows/Linux và symbolic link, đồng thời tránh dùng metadata owner như lời bảo đảm quyền truy cập hoặc an ninh.

**Phiên bản:** các API chủ đề thuộc Java NIO.2 từ Java 7 và **vẫn áp dụng trên các JDK hiện đại**. Ví dụ đầy đủ biên dịch và chạy với **Java 21**; bài không dựa vào API lỗi thời hoặc workflow legacy.

## 2. Chủ sở hữu là thuộc tính của file, không phải nội dung file

Đặt một tình huống:

~~~text
project/
  report.txt
    nội dung: "Hello owner"
    metadata: owner = <danh tính tài khoản trong file system>
~~~

Dòng metadata chỉ mô tả ý tưởng, không phải cú pháp file hay kết quả thực tế của mọi hệ điều hành. Cùng nội dung byte `"Hello owner"` có thể có owner khác nhau sau khi copy sang filesystem khác, được tạo bởi process khác, hoặc được quản trị viên chuyển ownership.

Những điều cần phân biệt:

1. **`Path`** — đường dẫn dùng để tìm file trong filesystem. Nó không chứa một trường “owner bất biến” trong chính đối tượng `Path`.
2. **`UserPrincipal`** — danh tính do filesystem/provider biểu diễn; có thể là account trong hệ điều hành, domain hoặc hệ quản lý danh tính khác.
3. **Quyền truy cập (permissions)** — các quy tắc quyết định đọc/ghi/thực thi hoặc thao tác quản lý được phép hay không. Chủ sở hữu có thể là một yếu tố trong quy tắc đó, **không phải toàn bộ**.
4. **Principal của process hiện tại** — tài khoản mà process chạy dưới quyền; không nhất thiết bằng owner của mọi file process đọc.
5. **Tên tài khoản dạng text** — kết quả của `getName()`, hữu ích để hiển thị/log có kiểm soát, nhưng không tự thay thế đối tượng danh tính được provider phân giải.

Trên nhiều hệ thống, file mới có thể thuộc tài khoản tạo file, nhưng Java **không cam kết** mọi provider, mount và chính sách tạo file đều gán owner theo một quy tắc duy nhất. Không hard-code giả định “chủ file chính là user đang đăng nhập”.

## 3. `UserPrincipal`: đối tượng danh tính, không phải String

Interface:

~~~java
import java.nio.file.attribute.UserPrincipal;
~~~

`UserPrincipal` là interface biểu diễn một danh tính người dùng cho các hệ thống file có quản lý owner/access control. Nó có `getName()` (thông qua hợp đồng principal) để lấy **tên mà implementation cung cấp**.

Ví dụ:

~~~java
UserPrincipal owner = Files.getOwner(path);
System.out.println(owner.getName());
~~~

Đây là đoạn minh họa — output không nên bị cố định là `"alice"`, `"root"` hoặc `"DOMAIN\\Alice"`, vì tên phụ thuộc người dùng, hệ điều hành và provider.

### 3.1. Vì sao không dùng chuỗi thay `UserPrincipal`?

Chữ ký phương thức đổi owner là:

~~~java
Path updatedPath = Files.setOwner(path, desiredOwner);
~~~

Ở đây `desiredOwner` phải là **`UserPrincipal`**, không phải `String`. Điều này cho phép filesystem provider quản lý cách phân giải danh tính và kiểm tra tính hợp lệ của principal.

Không nên ép một tên từ cấu hình trực tiếp thành `UserPrincipal` bằng implementation tự viết rồi trông chờ mọi provider chấp nhận. Hãy dùng `UserPrincipalLookupService` phù hợp với **filesystem của file đích** nếu cần phân giải tên.

### 3.2. Tên tài khoản không phải ID phổ quát

`getName()` có thể trả tên theo quy tắc khác nhau:

- Linux/Unix-like: có thể hiển thị tên user của hệ thống.
- Windows: có thể hiển thị dạng có domain hoặc thành phần nhận diện khác.
- Filesystem provider chuyên dụng: có thể dùng định danh riêng.

Không giả định:

- Hai chuỗi tên giống nhau trên hai filesystem khác nhau nhất định là **cùng một danh tính**.
- `System.getProperty("user.name")` nhất định bằng `owner.getName()`.
- Thay đổi tên hiển thị đồng nghĩa thay đổi owner của file.
- Mọi owner nhất thiết là một người dùng đang đăng nhập tương tác.

Trong ứng dụng cần xác minh owner thật, dùng principal lấy trực tiếp từ provider đích và chính sách danh tính/ủy quyền phù hợp. `UserPrincipal.equals(...)` có ý nghĩa theo implementation; không biến việc so sánh tên thành một hệ thống xác thực tài khoản xuyên nền tảng.

## 4. Đọc owner nhanh bằng `Files.getOwner`

API cơ bản:

~~~java
UserPrincipal owner = Files.getOwner(file);
~~~

Với `file` trỏ tới một file hoặc thư mục thực sự và provider hỗ trợ owner, Java trả về principal của chủ sở hữu. Phương thức có thể thực hiện I/O và khai báo `throws IOException`. Nó cũng có thể ném `UnsupportedOperationException` nếu filesystem của path không hỗ trợ `FileOwnerAttributeView`; truy cập bị từ chối có thể biểu hiện bằng lỗi quyền/I/O phù hợp.

### 4.1. Chính sách symbolic link

Overload:

~~~java
UserPrincipal targetOwner = Files.getOwner(file);
UserPrincipal entryOwner = Files.getOwner(file, LinkOption.NOFOLLOW_LINKS);
~~~

Đoạn minh họa cần import `java.nio.file.LinkOption`.

- Không truyền `NOFOLLOW_LINKS`: mặc định **đi theo symbolic link** nếu `file` là symlink, đọc owner của **target**.
- Truyền `NOFOLLOW_LINKS`: yêu cầu đọc thuộc tính của **chính symlink** thay vì target (nếu provider hỗ trợ thao tác đó).
- Với file bình thường không phải symlink, hai lời gọi thường đọc cùng owner.
- Một số filesystem không hỗ trợ quản lý owner của symlink theo cách bạn mong đợi; cần xử lý ngoại lệ/provider-specific behavior.
- Kết quả chỉ là metadata tại **thời điểm đọc**, không giữ link/file bất biến cho bước tiếp theo.

**Quan trọng:** `Files.setOwner(Path, UserPrincipal)` **không có overload nhận `LinkOption`**. Đừng suy ra rằng truyền `NOFOLLOW_LINKS` vào `getOwner` rồi gọi `setOwner` sẽ cập nhật owner **của chính link**. Nếu phải thay owner của symlink, cần nghiên cứu semantics của `FileOwnerAttributeView` và provider đang dùng, thay vì giả định một hành vi thống nhất.

### 4.2. Đọc trực tiếp hay đọc qua view?

Hai cách đều sử dụng cơ chế owner attribute:

~~~java
UserPrincipal one = Files.getOwner(file);

FileOwnerAttributeView view = Files.getFileAttributeView(
        file, FileOwnerAttributeView.class);

if (view != null) {
    UserPrincipal two = view.getOwner();
}
~~~

Đây là đoạn minh họa cần các import tương ứng.

`Files.getOwner` thường ngắn gọn và dễ đọc. `FileOwnerAttributeView` thích hợp khi code quản lý nhiều thuộc tính cùng nhóm hoặc cần truy cập API `setOwner` tương ứng trên một view đã chọn.

**Phải kiểm tra null của view:** `Files.getFileAttributeView(file, FileOwnerAttributeView.class)` có thể trả `null` nếu provider không hỗ trợ loại view yêu cầu. Đừng gọi `view.getOwner()` ngay mà không kiểm tra.

## 5. Chương trình Java 21 hoàn chỉnh: đọc owner bằng ba API và không sửa quyền hệ thống

Ví dụ này **không đổi chủ sở hữu**. Nó tạo một file tạm riêng, ghi nội dung, kiểm tra support của owner view, đọc owner qua ba API và kiểm tra kết quả **mà không in thông tin tài khoản thật của máy**.

- `Files.getOwner(document)`.
- `FileOwnerAttributeView.getOwner()`.
- `Files.getAttribute(document, "owner:owner")`.
- `Files.getOwner(document, NOFOLLOW_LINKS)` trên **file thường**.
- Một helper **chỉ minh họa cách đổi owner nếu đã được cấp quyền**, được compiler kiểm tra nhưng **không gọi trong main**.

Tạo file `src/main/java/demo/OwnerPrincipalExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.FileOwnerAttributeView;
import java.nio.file.attribute.UserPrincipal;
import java.nio.file.attribute.UserPrincipalLookupService;

public final class OwnerPrincipalExample {
    private OwnerPrincipalExample() {}

    // Chỉ dùng sau khi ứng dụng đã kiểm tra quyền quản trị và chính sách.
    static void changeOwnerIfAuthorized(Path file, String accountName)
            throws IOException {
        UserPrincipalLookupService lookup =
                file.getFileSystem().getUserPrincipalLookupService();
        UserPrincipal desired = lookup.lookupPrincipalByName(accountName);
        Files.setOwner(file, desired);
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("owner-lesson-");
        Path document = directory.resolve("sample.txt");
        try {
            Files.writeString(document, "Hello owner", StandardCharsets.UTF_8);

            FileOwnerAttributeView view = Files.getFileAttributeView(
                    document, FileOwnerAttributeView.class);
            if (view == null) {
                System.out.println("owner-view=unsupported");
                return;
            }

            UserPrincipal directOwner = Files.getOwner(document);
            UserPrincipal viewOwner = view.getOwner();
            UserPrincipal namedAttribute = (UserPrincipal) Files.getAttribute(
                    document, "owner:owner");

            System.out.println("view-name=" + view.name());
            System.out.println("owner-name-nonempty=" + !directOwner.getName().isBlank());
            System.out.println("files-view-same-owner="
                    + directOwner.equals(viewOwner));
            System.out.println("attribute-same-owner="
                    + directOwner.equals(namedAttribute));
            System.out.println("owner-is-userprincipal="
                    + (directOwner instanceof UserPrincipal));

            UserPrincipal noFollowOwner = Files.getOwner(document, LinkOption.NOFOLLOW_LINKS);
            System.out.println("no-link-same-owner="
                    + directOwner.equals(noFollowOwner));
        } finally {
            Files.deleteIfExists(document);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Từ thư mục chứa `src/`, dùng JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/OwnerPrincipalExample.java
java -cp out demo.OwnerPrincipalExample
~~~

**Stdout chính xác trên default Windows file system của môi trường đã kiểm thử:**

~~~text
view-name=owner
owner-name-nonempty=true
files-view-same-owner=true
attribute-same-owner=true
owner-is-userprincipal=true
no-link-same-owner=true
~~~

Nếu provider **không hỗ trợ** `FileOwnerAttributeView`, chương trình có thể in một dòng:

~~~text
owner-view=unsupported
~~~

Đó là **nhánh tương thích**, không phải stdout được quan sát ở môi trường đã kiểm thử. Nếu tài khoản thiếu quyền đọc metadata, hoặc I/O bị lỗi, `IOException`/lỗi truy cập vẫn có thể xảy ra; không nên biến tất cả lỗi đó thành thông báo “unsupported”.

### 5.1. Diễn giải từng dòng

- **`view-name=owner`:** tên chính thức của `FileOwnerAttributeView` là `"owner"`.
- **`owner-name-nonempty=true`:** account của owner trong môi trường thử có tên không rỗng. Không in tên thật để output không phụ thuộc user/OS và không rò rỉ danh tính hệ thống trong log.
- **`files-view-same-owner=true`:** `Files.getOwner` và `view.getOwner` trả cùng danh tính trong tình huống tệp thử không đổi và cùng provider.
- **`attribute-same-owner=true`:** `Files.getAttribute(path, "owner:owner")` trả giá trị tương ứng với principal của owner. Cú pháp là **`viewName:attributeName`**.
- **`owner-is-userprincipal=true`:** principal nhận được là một `UserPrincipal`. Biến `directOwner` đã có kiểu `UserPrincipal`, nên phép kiểm tra này chủ yếu củng cố khái niệm kiểu dữ liệu, không phải xác thực tài khoản.
- **`no-link-same-owner=true`:** tài nguyên thử là **file thường**, không phải symbolic link, nên hai chế độ đọc owner cho cùng kết quả trong môi trường thử.

Điểm quan trọng nhất là **đọc metadata** khác **thay đổi metadata**. Chương trình không gọi `changeOwnerIfAuthorized` để tránh thao tác đổi owner ngoài ý muốn.

### 5.2. Tại sao code không cố thay owner của file tạm?

`Files.setOwner` là hành động thay đổi quyền sở hữu file thực. Kể cả khi muốn gán lại đúng principal hiện tại, filesystem/OS vẫn có thể từ chối do chính sách bảo mật. Một tutorial nên **không mặc nhiên yêu cầu chạy với quyền quản trị** hoặc cố chuyển file cho tài khoản khác để kiểm thử một API đọc thuộc tính.

Vì vậy chương trình:

- Tạo file tạm có tên riêng.
- Kiểm thử thao tác đọc owner thật.
- Kiểm tra biên dịch của helper lookup + setOwner.
- **Không gọi helper thay ownership**.
- Dọn file và thư mục của chính ví dụ bằng `finally`.

Đây là cách kiểm thử kiến thức về `UserPrincipal` mà không sửa quyền sở hữu của file thực ngoài phạm vi bài.

## 6. `FileOwnerAttributeView`: vì sao API dùng một view?

`FileOwnerAttributeView` là interface hỗ trợ **đọc và cập nhật owner**. Nó có:

| Thành phần | Vai trò |
| --- | --- |
| `getOwner()` | Đọc `UserPrincipal` của file |
| `setOwner(UserPrincipal)` | Yêu cầu cập nhật chủ sở hữu file |
| `name()` | Trả tên attribute view: `"owner"` |

Lấy một view:

~~~java
FileOwnerAttributeView view = Files.getFileAttributeView(
        path, FileOwnerAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view == null) {
    throw new UnsupportedOperationException("Owner view not supported");
}

UserPrincipal owner = view.getOwner();
~~~

Đây là đoạn minh họa cần import tương ứng, xử lý `IOException` và xác định `Path path`. Việc truyền `NOFOLLOW_LINKS` làm view áp dụng chính sách không đi theo symbolic link theo hỗ trợ của provider; điều đó **khác** việc gọi `Files.setOwner` trực tiếp (không có option).

### 6.1. Thuộc tính có tên `"owner:owner"`

Nếu muốn đọc bằng cú pháp attribute name:

~~~java
UserPrincipal owner = (UserPrincipal) Files.getAttribute(
        path, "owner:owner");
~~~

`"owner"` trước dấu `:` là **tên view**, `"owner"` sau dấu `:` là **tên thuộc tính**. Kết quả là `Object`, vì vậy cần ép kiểu `UserPrincipal` khi lấy thông qua `Files.getAttribute`.

Không nhầm `"owner:owner"` là một thuộc tính trả chuỗi tài khoản. Giá trị mà API cung cấp theo contract là **principal**, còn tên text lấy bằng `owner.getName()`.

Có thể đọc hàng loạt thuộc tính bằng `Files.readAttributes(path, "owner:owner")` theo contract string-based của `Files`, nhưng bài này không cần dùng map vì `Files.getOwner` và view đã rõ ràng hơn.

### 6.2. Các interface liên quan

`PosixFileAttributeView` và `AclFileAttributeView` đều mở rộng khả năng truy cập owner từ `FileOwnerAttributeView`, nhưng **chính sách phân quyền** của chúng khác nhau:

- POSIX có owner, group và bộ bit quyền đọc/ghi/thực thi.
- ACL có danh sách entry/quy tắc truy cập, thường dùng trên những filesystem tương ứng.
- Chúng không bảo đảm tồn tại trên mọi provider, và không đồng nghĩa `FileOwnerAttributeView` sẽ hỗ trợ đầy đủ cả POSIX lẫn ACL.

Do đó, nếu chỉ cần owner mà muốn code dễ di chuyển, hãy ưu tiên interface chung `FileOwnerAttributeView` hoặc `Files.getOwner`, kiểm tra hỗ trợ của provider và xử lý ngoại lệ.

## 7. `UserPrincipalLookupService`: chuyển tên tài khoản thành principal hợp lệ

Khi cần đổi owner, người quản trị có thể cung cấp **tên tài khoản** từ cấu hình hoặc workflow đã được xác thực. API phù hợp để phân giải tên đó là:

~~~java
UserPrincipalLookupService lookup =
        path.getFileSystem().getUserPrincipalLookupService();

UserPrincipal desired = lookup.lookupPrincipalByName(accountName);
~~~

Đây là hai lệnh minh họa với `Path path`, `String accountName` và import từ `java.nio.file.attribute`.

**Điểm dễ bỏ sót:** lấy lookup service từ **`path.getFileSystem()`**, không ngầm lấy default filesystem rồi dùng principal đó cho một path từ provider khác. Các hệ thống file có thể biểu diễn và chấp nhận principal theo cách khác nhau.

### 7.1. Khi lookup không thành công

- Tên account không tồn tại/không thể phân giải: có thể ném `UserPrincipalNotFoundException`, là subtype của `IOException`.
- Lỗi hệ thống danh tính hoặc I/O: có thể ném `IOException`.
- Filesystem không hỗ trợ dịch vụ lookup: có thể ném `UnsupportedOperationException`.
- Một môi trường có thể áp dụng kiểm tra quyền, security constraints hoặc quy tắc danh tính riêng.

**Không tự suy diễn** rằng `lookupPrincipalByName("alice")` chạy được trên mọi máy hoặc cùng chỉ đến một tài khoản trên các domain/provider khác nhau. Đừng đưa account cố định từ hệ điều hành này vào bài test cross-platform.

### 7.2. Nhóm là `GroupPrincipal`, không phải mọi `UserPrincipal` đều giống nhau

`GroupPrincipal` kế thừa `UserPrincipal` nhưng biểu diễn **một nhóm**. Có API:

~~~java
GroupPrincipal group = lookup.lookupPrincipalByGroupName(groupName);
~~~

Đây là đoạn minh họa, cần import `java.nio.file.attribute.GroupPrincipal` và `UserPrincipalLookupService`.

**Không dùng group principal tùy tiện để gọi `Files.setOwner`.** Javadoc `FileOwnerAttributeView` giải thích việc có thể dùng group như owner hay không là **implementation-specific**, và khuyến nghị chỉ gán file owner bằng **user principal không phải group** để có hành vi nhất quán giữa các hệ thống.

Trong môi trường POSIX, **owner** và **group-owner** là hai thuộc tính liên quan nhưng khác nhau. Đổi group nên dùng API POSIX phù hợp (`PosixFileAttributeView.setGroup`) khi provider hỗ trợ và chính sách cho phép, không dùng `setOwner` để “đổi group”.

## 8. Thay đổi chủ sở hữu: `Files.setOwner` cần quyền thực tế

Chữ ký:

~~~java
Path result = Files.setOwner(path, desiredOwner);
~~~

Khi thành công, phương thức trả lại `path` và yêu cầu cập nhật chủ sở hữu file. Tuy nhiên, đây **không phải** thao tác mà bất kỳ chương trình Java nào cũng làm được.

### 8.1. Quy trình phù hợp trong ứng dụng quản trị

1. Xác định rõ **file đích** và **filesystem provider**.
2. Kiểm tra workflow có quyền quản trị và được phép chuyển owner theo chính sách.
3. Phân giải tài khoản đích qua `UserPrincipalLookupService` của đúng filesystem.
4. Thực hiện `Files.setOwner(path, principal)` trong khối xử lý `IOException`/lỗi quyền và `UnsupportedOperationException`.
5. Nếu nghiệp vụ cần xác nhận, đọc lại owner bằng `Files.getOwner(path)`.
6. Ghi audit log không tiết lộ dữ liệu bí mật, và xử lý tình huống target bị thay thế hoặc owner lại đổi sau bước đọc.

Ví dụ minh họa **chỉ dành cho môi trường có quyền hợp lệ**:

~~~java
static void changeOwnerIfAuthorized(Path file, String accountName)
        throws IOException {
    UserPrincipalLookupService lookup =
            file.getFileSystem().getUserPrincipalLookupService();
    UserPrincipal desired = lookup.lookupPrincipalByName(accountName);
    Files.setOwner(file, desired);
}
~~~

Phương thức này nằm trong class ví dụ đã biên dịch ở phần 5 nhưng **không được gọi trong bài thử**. Nó không có bước phân quyền nghiệp vụ bên trong; tên `IfAuthorized` nhắc rằng **caller phải xác thực, phân quyền và quản lý file target trước**. Không sao chép hàm này như API public cho người dùng không được tin cậy.

### 8.2. Kết quả bị từ chối là tình huống bình thường

Tùy hệ điều hành và policy, đổi owner có thể cần quyền đặc biệt. Một tài khoản có quyền sửa nội dung file **chưa chắc** có quyền chuyển quyền sở hữu file đó cho người khác. Thậm chí chuyển từ owner hiện tại sang cùng principal vẫn có thể bị từ chối bởi provider.

Các kiểu thất bại cần xử lý:

- `AccessDeniedException` hoặc một `IOException` khác khi không có quyền.
- `UnsupportedOperationException` nếu attribute view/lookup không được provider hỗ trợ.
- `UserPrincipalNotFoundException` khi không phân giải được tên cần gán.
- File bị xóa/thay đổi giữa thời điểm lookup, xác minh và setOwner.
- Provider từ chối principal thuộc hệ thống danh tính không tương thích.

**Không dùng `Files.setOwner` như công cụ “tạo quyền đọc” chung.** Mục đích của API là thay đổi owner metadata; hệ quả về quyền tùy thuộc chính sách của hệ điều hành/file system.

### 8.3. Không cần đặc quyền để học phần đọc

Đọc owner bằng `Files.getOwner` trên file do chương trình tạo, trong môi trường cho phép, là đủ cho phần lớn bài thực hành. Đổi owner của file hệ thống hoặc file dùng chung chỉ nên thử khi có quyền admin được cấp rõ ràng và file thí nghiệm được chọn có chủ đích.

## 9. Chủ sở hữu và quyền truy cập: khác nhau thế nào?

Câu “file thuộc user X” **không tương đương** với câu “chỉ user X mới được đọc file” hay “user X được làm mọi thao tác”.

Mô hình có thể gồm:

- Owner của file.
- Nhóm sở hữu (*group owner*) trên hệ thống kiểu POSIX.
- Quyền đọc/ghi/thực thi cho owner, group và others.
- ACL entries cấp/deny quyền cho các principal cụ thể.
- Quyền quản trị, policy hệ thống, mount options, inheritance và security controls khác.

`UserPrincipal` chỉ biểu diễn danh tính. Không được biến `owner.getName()` thành một phép **authorization** duy nhất.

### 9.1. POSIX: owner, group, permissions

Trên filesystem có `PosixFileAttributeView`, có thể đọc chung:

~~~java
PosixFileAttributeView posix = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);

if (posix != null) {
    PosixFileAttributes attrs = posix.readAttributes();
    UserPrincipal owner = attrs.owner();
    GroupPrincipal group = attrs.group();
    Set<PosixFilePermission> permissions = attrs.permissions();
}
~~~

Đây là **đoạn minh họa**, cần import `PosixFileAttributeView`, `PosixFileAttributes`, `GroupPrincipal`, `PosixFilePermission`, `Set` và xử lý `IOException`.

- `attrs.owner()` là principal của owner.
- `attrs.group()` là principal của group-owner.
- `attrs.permissions()` là quyền POSIX dưới dạng tập `PosixFilePermission`.

Trên Windows default filesystem, `PosixFileAttributeView` thường không được hỗ trợ. Đừng gọi `Files.getPosixFilePermissions(...)` rồi coi một exception là lỗi Java. Dùng mô hình thuộc tính thực mà provider hỗ trợ.

### 9.2. ACL: owner và quyền chi tiết

`AclFileAttributeView` cung cấp `getAcl()` và `setAcl(...)` cho những provider hỗ trợ ACL. Nó mở rộng `FileOwnerAttributeView`, vì vậy cũng có `getOwner()` / `setOwner(...)`.

Nhưng **đổi owner** và **đổi ACL** là hai thao tác khác nhau. ACL có thể cho hoặc từ chối quyền đối với nhiều principal; đổi owner chưa chắc đặt lại toàn bộ ACL theo một chính sách bạn giả định.

Nếu bài toán là “người dùng A có quyền đọc file này không?”, chỉ biết owner chưa đủ. `Files.isReadable(path)` là một kiểm tra best-effort tại thời điểm gọi, nhưng quyết định cuối cùng vẫn là kết quả thao tác mở/đọc thật, dưới quyền process hiện tại và policy của hệ thống.

## 10. Quy tắc hỗ trợ theo filesystem provider

Đây là khác biệt rất thực tế giữa máy phát triển, máy chạy dịch vụ và một provider ảo như ZIP filesystem.

| API/view | Tính di động và lỗi cần xét |
| --- | --- |
| `Files.getOwner(path)` | Cần provider hỗ trợ owner view; có thể ném `UnsupportedOperationException` hoặc `IOException` |
| `Files.getFileAttributeView(path, FileOwnerAttributeView.class)` | Có thể trả `null` khi không hỗ trợ |
| `view.getOwner()` | Có thể ném `IOException` hoặc lỗi quyền truy cập |
| `UserPrincipalLookupService.lookupPrincipalByName(...)` | Tên/khả năng lookup phụ thuộc filesystem, có thể gặp `UserPrincipalNotFoundException` |
| `Files.setOwner(path, owner)` | Cần hỗ trợ ghi owner và đủ quyền; không bảo đảm thành công trên mọi OS/provider |
| `PosixFileAttributeView` | Chỉ phù hợp filesystem hỗ trợ mô hình POSIX |
| `AclFileAttributeView` | Chỉ phù hợp provider có ACL tương ứng |

### 10.1. Kiểm tra support rồi vẫn phải xử lý lỗi

Ví dụ:

~~~java
FileOwnerAttributeView view = Files.getFileAttributeView(
        path, FileOwnerAttributeView.class);

if (view == null) {
    // Provider không hỗ trợ kiểu view này.
} else {
    UserPrincipal owner = view.getOwner();
    // Thao tác getOwner vẫn có thể thất bại vì I/O/quyền.
}
~~~

**Kiểm tra `view != null` không phải lời bảo đảm phép đọc owner chắc chắn thành công.** File có thể bị xóa, permissions bị đổi, hoặc provider gặp lỗi giữa hai bước.

Bạn cũng có thể hỏi `Files.getFileStore(path).supportsFileAttributeView("owner")`. Nhưng filesystem metadata và trạng thái của file vẫn có thể đổi; không thay thế bắt lỗi tại thao tác thật.

### 10.2. Không in tên thật của tài khoản trong mọi log

Tên owner có thể chứa định danh cá nhân/tài khoản doanh nghiệp hoặc domain. Khi debug, có thể ghi **trạng thái success/failure**, loại exception và đường dẫn đã được kiểm soát thay vì mặc định in mọi tên principal công khai.

Nếu một nghiệp vụ cần audit chính xác ai đổi ownership, log nên tuân thủ chính sách dữ liệu/retention và xác thực actor độc lập với `owner.getName()`, không dựa vào một tên hiển thị đơn lẻ.

## 11. Symbolic link, race và đối tượng tệp thực sự

Giả sử:

~~~text
workspace/
  item.txt -> /shared/report.txt
~~~

Đây là sơ đồ symlink. Với `item.txt`:

~~~java
UserPrincipal targetOwner = Files.getOwner(linkPath);
UserPrincipal linkOwner = Files.getOwner(
        linkPath, LinkOption.NOFOLLOW_LINKS);
~~~

Đoạn minh họa cần có `Path linkPath`.

Hai principal **có thể khác** vì đối tượng link và file đích là hai đối tượng metadata khác nhau. Tuy nhiên, việc hệ thống hỗ trợ đọc owner của link hay không là do provider quyết định.

### 11.1. Quyền sở hữu tại thời điểm kiểm tra không phải bảo đảm cho lần mở tiếp theo

Một quy trình dễ mắc TOCTOU:

~~~java
UserPrincipal checked = Files.getOwner(path);
if (checked.equals(allowedOwner)) {
    String content = Files.readString(path, StandardCharsets.UTF_8);
}
~~~

Đây là **phản ví dụ** nếu code cho rằng lần kiểm tra owner bảo đảm file vẫn là cùng đối tượng cho lần đọc. Nếu một tác nhân có thể thay đường dẫn/symlink giữa `getOwner` và `readString`, nội dung mở sau đó có thể không thuộc file được kiểm tra.

**Không dùng `getOwner` + `equals` như một sandbox chống truy cập trái phép.** Nếu có yêu cầu kiểm soát an ninh mạnh, cần cơ chế quyền file system, handle-based access, kiểm tra policy và phòng TOCTOU phù hợp môi trường.

### 11.2. Owner của file có thể thay đổi khi đang chạy

`Path` object không tự chứa snapshot metadata. Lần gọi `Files.getOwner(path)` thứ hai có thể cho kết quả khác nếu file được thay bằng file mới, owner được quản trị viên đổi hoặc link đổi target.

Nếu nghiệp vụ yêu cầu audit/vận hành dựa trên owner cố định, cần xác định **thời điểm quan sát**, danh tính của đối tượng file và concurrency policy, chứ không khẳng định một lần đọc metadata mang giá trị vĩnh viễn.

## 12. Khi nào nên dùng owner, khi nào không?

| Nhu cầu | Nên dùng | Không nên suy diễn |
| --- | --- | --- |
| Hiển thị chủ sở hữu một file | `Files.getOwner(path).getName()` khi được phép | Tên có định dạng giống nhau trên mọi OS |
| Kiểm tra hai cách đọc metadata owner cho cùng file | `Files.getOwner` và `FileOwnerAttributeView.getOwner` | Kết quả sẽ giữ nguyên nếu file đổi sau đó |
| Đổi owner của file được quản lý có chủ đích | Lookup principal của đúng filesystem rồi `Files.setOwner` với quyền hợp lệ | Mọi caller đều có quyền thay |
| Đọc group và quyền POSIX | `PosixFileAttributeView` nếu provider hỗ trợ | POSIX luôn có trên Windows |
| Làm việc với ACL phức tạp | `AclFileAttributeView` nếu provider hỗ trợ | Owner và ACL là cùng một thứ |
| Hỏi quyền đọc hiện tại | Tôn trọng OS ACL/permissions, thử thao tác thật và xử lý lỗi | Owner bằng process user thì chắc chắn đọc được |
| Kiểm tra đường dẫn không thoát thư mục cho phép | Thiết kế path/handle/permissions chống TOCTOU | So owner là đủ chống traversal |
| Ghi log vận hành | Trạng thái, nguyên nhân thất bại, principal cần thiết theo policy | Tên principal luôn là thông tin có thể công khai |
| Quản lý file tạo mới | Tạo file với ownership/perms theo OS/provider | Java mặc định cho owner/perms giống nhau trên mọi filesystem |

## 13. Lỗi thường gặp và cách sửa

**Lỗi 1: Coi owner là một chuỗi account đơn giản.**  
`UserPrincipal` là đối tượng danh tính. `getName()` là tên do provider cấp, không phải ID toàn cầu để tự tạo principal mới.

**Lỗi 2: Không kiểm tra owner view có được hỗ trợ không.**  
`Files.getFileAttributeView(...)` có thể trả `null`. `Files.getOwner(...)` có thể ném `UnsupportedOperationException`; hãy xử lý theo contract.

**Lỗi 3: Nghĩ chương trình đọc được owner thì chắc chắn đổi được owner.**  
Đọc metadata và chuyển quyền sở hữu cần quyền khác nhau. `setOwner` có thể bị từ chối.

**Lỗi 4: Dùng `System.getProperty("user.name")` làm owner chắc chắn của file.**  
Process user không nhất thiết là owner. Đọc từ filesystem khi thật sự cần metadata file.

**Lỗi 5: Chuyển chuỗi từ người dùng thành principal tùy ý mà không lookup.**  
Tên phải được phân giải bởi `UserPrincipalLookupService` của filesystem liên quan.

**Lỗi 6: Giả định `Files.setOwner` có overload `NOFOLLOW_LINKS`.**  
Không có. Chính sách link của thao tác qua view/provider cần được nghiên cứu riêng.

**Lỗi 7: Dùng GroupPrincipal để đổi owner một cách mặc định.**  
Javadoc cho biết group có thể/không thể được chấp nhận tùy implementation. Hãy dùng user principal đúng mục đích.

**Lỗi 8: Coi `FileOwnerAttributeView`, `PosixFileAttributeView` và `AclFileAttributeView` là tương đương.**  
Owner view là khái niệm chung; POSIX và ACL bổ sung các mô hình quyền riêng.

**Lỗi 9: So tên principal rồi mở file, coi đó là bảo đảm security.**  
Đường dẫn/file/symlink có thể thay giữa check và use. Cần xử lý TOCTOU và bảo vệ filesystem.

**Lỗi 10: Bắt mọi `IOException` rồi coi file không có owner.**  
Có thể che lỗi quyền, lỗi thiết bị hoặc file biến mất; phân loại chính xác thay vì đánh đồng.

**Lỗi 11: Ghi đè owner của file system để test tutorial.**  
Không nên. Bài thực hành đọc metadata trên file tạm đã đủ; chỉ thử setOwner khi được cấp quyền và có mục tiêu rõ.

**Lỗi 12: Coi một owner là đồng nghĩa một ACL duy nhất.**  
ACL có thể cấp/deny quyền cho nhiều principal. Ownership chỉ là một phần mô hình access control.

## 14. Bài tập có đáp án

**Bài 1.** `Files.getOwner(path)` trả `String` hay `UserPrincipal`?

**Đáp án:** Trả `UserPrincipal`. Muốn lấy tên hiển thị, gọi `owner.getName()`.

**Bài 2.** Có thể dùng `Files.setOwner(path, "alice")` trực tiếp không?

**Đáp án:** Không. API nhận `UserPrincipal`, không phải string. Cần lookup tên qua `UserPrincipalLookupService` nếu ứng dụng được phép đổi owner.

**Bài 3.** Lấy `FileOwnerAttributeView` bằng `Files.getFileAttributeView` mà nhận `null` có nghĩa gì?

**Đáp án:** Filesystem provider không hỗ trợ attribute view yêu cầu cho path tương ứng. Không gọi `getOwner()` trên null; cần xử lý thiếu hỗ trợ.

**Bài 4.** `Files.getOwner(path, LinkOption.NOFOLLOW_LINKS)` khác gì mặc định khi `path` là symbolic link?

**Đáp án:** Mặc định theo link để đọc owner target. Với `NOFOLLOW_LINKS`, yêu cầu đọc owner chính link nếu provider hỗ trợ.

**Bài 5.** Một file thuộc tài khoản `A`. Có thể kết luận mọi tiến trình chạy dưới `A` đều có toàn quyền không?

**Đáp án:** Không. Quyền thực phụ thuộc permissions, ACL, OS security policy, privilege và thao tác cụ thể.

**Bài 6.** `GroupPrincipal` có phải `UserPrincipal` không? Có nên mặc định dùng nó làm owner?

**Đáp án:** `GroupPrincipal` mở rộng `UserPrincipal`. Nhưng sử dụng group làm owner của file là implementation-specific; không mặc định làm vậy.

**Bài 7.** Một ứng dụng chạy trên Windows không hỗ trợ `PosixFileAttributeView`. Có nhất thiết không đọc được owner không?

**Đáp án:** Không. Provider có thể hỗ trợ `FileOwnerAttributeView` hoặc `AclFileAttributeView` mà không hỗ trợ POSIX permissions. Hãy kiểm tra đúng view cần dùng.

**Bài 8.** `Files.getAttribute(file, "owner:owner")` trả kiểu gì và vì sao có dấu hai chấm?

**Đáp án:** Trả `Object` chứa `UserPrincipal` theo contract. Cú pháp `view:attribute` là `"owner:owner"`.

**Bài 9.** Vì sao không gọi `Files.setOwner` trong chương trình demo?

**Đáp án:** Đổi ownership là thao tác metadata cần quyền thực. Tùy hệ điều hành, nó có thể bị từ chối hoặc gây thay đổi không mong muốn; bài demo chỉ cần chứng minh đọc owner.

**Bài 10.** Nếu file bị thay qua symlink sau khi đọc owner, có thể dùng kết quả owner cũ để ủy quyền mở file mới không?

**Đáp án:** Không. Đây là TOCTOU; object đã mở ở thời điểm sau có thể khác object được kiểm tra. Cần thiết kế bảo mật dựa trên OS/file handles/permission policy phù hợp.

**Bài 11.** Tại sao không nên dùng tên account `"root"` hoặc `"Administrator"` làm expected output trong tutorial Java cross-platform?

**Đáp án:** Các tên đó phụ thuộc OS và cấu hình. Chương trình nên chỉ kiểm tra semantics ổn định, không giả định một account cụ thể.

## 15. Checklist và tài liệu chính thức

- [ ] Dùng `Files.getOwner(path)` khi cần đọc owner theo provider.
- [ ] Hiểu `UserPrincipal` là **danh tính**, `getName()` chỉ là tên do implementation cung cấp.
- [ ] Với view, kiểm tra `Files.getFileAttributeView(path, FileOwnerAttributeView.class) != null`.
- [ ] Phân biệt `Files.getOwner`, `view.getOwner` và `Files.getAttribute(path, "owner:owner")`.
- [ ] Nhớ chính sách mặc định theo symbolic link; dùng `LinkOption.NOFOLLOW_LINKS` nếu có chủ đích và được hỗ trợ.
- [ ] Không coi đọc owner tương đương có quyền sửa owner.
- [ ] Khi thật sự cần chuyển owner, lookup principal bằng service của đúng filesystem và yêu cầu quyền quản trị hợp lệ.
- [ ] Không gán group principal cho file owner một cách mặc định.
- [ ] Dùng `PosixFileAttributeView` cho POSIX owner/group/permissions khi hỗ trợ; dùng `AclFileAttributeView` cho ACL khi hỗ trợ.
- [ ] Xử lý `IOException`, `UnsupportedOperationException`, trường hợp thiếu principal và lỗi quyền.
- [ ] Không log tên user/domain nếu không cần hoặc không được phép theo chính sách.
- [ ] Không xem kết quả owner/permission check là snapshot bất biến trước TOCTOU.
- [ ] Không dựa vào API legacy; sử dụng các NIO.2 API còn hỗ trợ trên JDK hiện đại.
- [ ] Kiểm thử trên filesystem thực sự triển khai vì Windows/POSIX/providers khác nhau.

**Tài liệu chính thức Java SE 21:**

- [Files.getOwner / setOwner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): hai phương thức lấy/đổi chủ sở hữu và giới hạn hỗ trợ.
- [FileOwnerAttributeView](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/FileOwnerAttributeView.html): `getOwner`, `setOwner`, tên view `"owner"`.
- [UserPrincipal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/UserPrincipal.html): interface đại diện danh tính.
- [UserPrincipalLookupService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/UserPrincipalLookupService.html): phân giải tài khoản/group thành principal.
- [UserPrincipalNotFoundException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/UserPrincipalNotFoundException.html): khi không tìm được principal theo tên.
- [PosixFileAttributeView](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html) và [PosixFileAttributes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributes.html): owner, group và POSIX permissions.
- [AclFileAttributeView](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): ACL và các khả năng liên quan owner.
- [LinkOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` khi truy cập thuộc tính qua symlink.

**Kết luận:** chủ sở hữu file là **một danh tính do filesystem quản lý**, được Java biểu diễn bằng `UserPrincipal`. `Files.getOwner` và `FileOwnerAttributeView` cho phép đọc metadata đó; `UserPrincipalLookupService` hỗ trợ phân giải tên khi thực sự cần thay owner bằng `Files.setOwner`. Nhưng ownership **không phải toàn bộ quyền truy cập**, và thao tác thay owner phải được cấp quyền, kiểm tra provider, xử lý lỗi cũng như tính biến động của hệ thống tệp. Những nguyên tắc này vẫn còn nguyên giá trị trên Java hiện đại.
