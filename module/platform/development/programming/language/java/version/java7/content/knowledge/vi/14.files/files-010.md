# Java 7 — Files: Xóa tệp hoặc thư mục với `delete`, `deleteIfExists`

## Mục tiêu bài học

Trong Java NIO.2, `java.nio.file.Files` cung cấp hai phương thức để **xóa một mục trên hệ thống tệp**, đã có từ Java 7 và vẫn là API hiện hành trên JDK 17+:

- `Files.delete(Path path)`: yêu cầu **xóa mục được chỉ định**; nếu mục không tồn tại hoặc việc xóa thất bại, phương thức báo lỗi bằng exception. Phương thức trả về `void`.
- `Files.deleteIfExists(Path path)`: yêu cầu xóa **nếu mục tồn tại**; trả `true` khi phương thức đã xóa mục, `false` khi không thể xóa do mục không tồn tại. Các lỗi I/O **khác vẫn có thể ném exception**.

Cả hai dùng cho regular file, symbolic link và **thư mục rỗng**, nhưng **không tự xóa đệ quy một thư mục đang chứa các mục con**. Một khác biệt tưởng nhỏ — xử lý trường hợp path đã biến mất — ảnh hưởng cách viết cleanup, retry, logic idempotent và xử lý cạnh tranh giữa nhiều tiến trình.

Sau bài, bạn có thể:

1. Chọn đúng `delete` hay `deleteIfExists` theo hợp đồng nghiệp vụ: *bắt buộc tồn tại* hoặc *có thì xóa*.
2. Dự đoán exception và giá trị trả về khi xóa file có thật, file đã mất, directory rỗng và directory chưa rỗng.
3. Phân biệt `NoSuchFileException`, `DirectoryNotEmptyException`, `AccessDeniedException` cùng các `IOException` khác.
4. Hiểu rằng xóa một symbolic link là xóa **chính link**, không mặc nhiên xóa target.
5. Không nhầm `deleteIfExists` với một thao tác bất biến, nguyên tử hay miễn nhiễm lỗi trong mọi tình huống.
6. Tổ chức thứ tự xóa **con trước, cha sau**; biết khi nào dùng `Files.walkFileTree` với `SimpleFileVisitor`.
7. Nhận diện nguy cơ xóa nhầm dữ liệu do `..`, đường dẫn tuyệt đối, symbolic link, race condition và quyền filesystem.
8. Kiểm thử bằng temp directory do chính chương trình tạo, dọn dẹp chính xác những đối tượng thuộc phạm vi test.
9. Thiết kế cleanup không âm thầm che lỗi chính hoặc xóa dữ liệu đã thuộc về người dùng khác.
10. Phân biệt việc xóa tên file trong filesystem với bảo đảm dữ liệu đã bị tẩy khỏi thiết bị lưu trữ.

Tất cả ví dụ Java hoàn chỉnh trong bài được biên dịch/chạy với **`javac --release 17` trên OpenJDK hiện đại**. Các đoạn mã chỉ mang tính minh họa được đánh dấu rõ. Bài tập trung vào API **đang được hỗ trợ**, không dùng phương án đã lỗi thời.

## 1. Bản chất của `Path` và `Files` khi xóa

Một `Path` mô tả một vị trí trên filesystem:

```java
Path file = Paths.get("work", "notes.txt");
```

Đây là **đoạn mã minh họa** cần import `java.nio.file.Path` và `java.nio.file.Paths`. Nó **không** mở, tạo hoặc xóa `notes.txt`. Hành động I/O chỉ xảy ra khi gọi một API như:

```java
Files.delete(file);
```

Đoạn này cần import `java.nio.file.Files` và phải được đặt trong ngữ cảnh có xử lý hoặc khai báo `IOException`.

Đường dẫn có thể là **relative**, được diễn giải theo working directory của tiến trình, hoặc **absolute**, gắn với một root của filesystem. Đừng giả định `Paths.get("work", "notes.txt")` luôn chỉ vào cùng tệp khi chạy trong IDE, terminal, service hoặc container. Đây là điểm quan trọng vì **thao tác xóa có tác dụng phá hủy dữ liệu**.

### 1.1. Vì sao nên dùng `Files` thay vì `File.delete()`?

`java.io.File.delete()` vẫn có thể gặp trong code cũ, nhưng nó trả boolean và thường cung cấp ít thông tin lỗi cụ thể hơn. `Files.delete(Path)`, là API NIO.2 vẫn hiện hành, sử dụng `IOException` và các subtype chuyên biệt để caller dễ phân biệt trạng thái.

Đây là **khác biệt API**, không phải tuyên bố rằng `java.io.File` đã không còn tồn tại hoặc bị cấm sử dụng. Với code mới cần xử lý đường dẫn, thuộc tính và lỗi filesystem rõ ràng, `Path` và `Files` thường là lựa chọn dễ bảo trì.

### 1.2. Xóa file thực sự khác xóa dữ liệu hoàn toàn khỏi thiết bị

`Files.delete`/`deleteIfExists` yêu cầu filesystem xóa mục hoặc liên kết directory entry. Chúng **không cung cấp hợp đồng “secure erase”** cho dữ liệu vật lý đã lưu, bản sao backup, snapshot, cache, SSD wear-leveling hay storage từ xa.

Nếu yêu cầu nghiệp vụ là “không còn đọc được qua path này”, các API có thể đáp ứng khi I/O thành công. Nếu yêu cầu là “xóa vĩnh viễn mọi bản sao”, cần chính sách lưu trữ, khóa mã hóa, retention, backup và secure deletion riêng; không mô tả hai API Java là chức năng tẩy dữ liệu pháp chứng.

## 2. So sánh nhanh `delete` và `deleteIfExists`

| Khía cạnh | `Files.delete(path)` | `Files.deleteIfExists(path)` |
| --- | --- | --- |
| Kiểu trả về | `void` | `boolean` |
| Path là regular file có thể xóa | Xóa, hoàn tất bình thường | Xóa, trả `true` |
| Path là directory **rỗng** có thể xóa | Xóa, hoàn tất bình thường | Xóa, trả `true` |
| Path đã không tồn tại | Ném `IOException`; thường là `NoSuchFileException` | Trả `false` nếu không xóa được vì không tồn tại |
| Directory không rỗng | Thất bại, thường `DirectoryNotEmptyException` | Vẫn thất bại, thường `DirectoryNotEmptyException` |
| Thiếu quyền / file đang bị sử dụng | Có thể ném `IOException` | Có thể ném `IOException` |
| Path là symbolic link | Xóa chính link, không phải target | Xóa chính link, không phải target |
| Tự xóa toàn bộ cây | Không | Không |
| Atomic với các hoạt động filesystem khác | **Không được bảo đảm** | **Không được bảo đảm** |
| Trường hợp thường dùng | Xóa một mục được *kỳ vọng phải tồn tại* | Cleanup “nếu còn thì xóa”, retry/best-effort có kiểm soát |

**Hai điều không được suy diễn:**

- `deleteIfExists` không có nghĩa *“xóa thất bại thì trả false”*. `false` tương ứng trường hợp không xóa được **vì mục không tồn tại**; thiếu quyền, directory không rỗng hoặc lỗi I/O vẫn có thể ném exception.
- `delete` cũng không có nghĩa *“xóa luôn cả thư mục cùng mọi file con”*. Cả hai chỉ thao tác trên **mục được chỉ định**, với yêu cầu directory rỗng.

### 2.1. Khi nào nên dùng phương thức nào?

Nếu code xử lý một chuyển trạng thái nghiêm ngặt “file phải có rồi mới được xóa” và việc file mất là dấu hiệu sai logic, dùng `delete` để **phát hiện missing path** có thể phù hợp.

Nếu code dọn file tạm trong `finally` và việc file đã được dọn trước đó là trạng thái chấp nhận được, `deleteIfExists` diễn đạt chính sách ấy rõ ràng hơn. Tuy nhiên, nếu cleanup không thể hoàn tất do lỗi permission hoặc I/O, **không nên nuốt lỗi tùy tiện**.

## 3. `Files.delete`: xóa mục phải tồn tại

Chữ ký rút gọn:

```java
public static void delete(Path path) throws IOException
```

Lời gọi:

```java
Files.delete(file);
```

Đây là đoạn minh họa, cần `file` kiểu `Path` và handling `IOException`. Khi thành công, nó không trả một biến boolean để đọc `true` hay `false`: **không có return value**.

### 3.1. Xóa lần đầu khác xóa lần hai

Với một regular file tồn tại và có quyền xóa:

1. Lần thứ nhất `Files.delete(file)` có thể thành công và file biến mất khỏi path.
2. Lần thứ hai với cùng path không còn mục đó để xóa; trên default filesystem thường nhận `NoSuchFileException`.
3. Nếu muốn chấp nhận tình trạng mục đã không tồn tại, có thể dùng `Files.deleteIfExists(file)` và kiểm tra boolean.

Mức chính xác của subtype exception còn phụ thuộc filesystem provider. Hợp đồng `delete` là báo lỗi khi không thể xóa, còn `NoSuchFileException` là một **optional specific exception** theo API Java.

## 4. Chương trình A — Xóa file một lần, kiểm tra missing path

Lưu tệp hoàn chỉnh **`DeleteFileDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class DeleteFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("delete-file-demo-");
        Path file = root.resolve("notes.txt");

        try {
            Files.writeString(file, "data", StandardCharsets.UTF_8);
            System.out.println("before=" + Files.isRegularFile(file));

            Files.delete(file);
            System.out.println("after=" + Files.exists(file));

            try {
                Files.delete(file);
                System.out.println("missing=unexpected");
            } catch (NoSuchFileException ex) {
                System.out.println("missing=NoSuchFileException");
            }

            System.out.println("ifMissing=" + Files.deleteIfExists(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 DeleteFileDemo.java
java DeleteFileDemo
```

**Stdout thực tế trên Windows/JDK đã kiểm tra:**

```text
before=true
after=false
missing=NoSuchFileException
ifMissing=false
```

### 4.1. Giải thích từng kết quả

- `Files.createTempDirectory` tạo một thư mục tạm **riêng**, nên ví dụ không xóa một file bất kỳ trong project.
- `Files.writeString` tạo và ghi file trước khi thao tác delete. Phương thức này được bổ sung từ **Java 11**, vẫn được hỗ trợ trên JDK 17+. Chủ đề `Files.delete` có từ Java 7.
- `before=true`: trước khi xóa, `Files.isRegularFile(file)` cho biết mục đang là regular file trong điều kiện test.
- `Files.delete(file)` xóa file.
- `after=false`: `Files.exists(file)` thấy file không còn tại path trong phép thử.
- Lần thứ hai `Files.delete(file)` nhận `NoSuchFileException` trên provider thử.
- `Files.deleteIfExists(file)` trả `false` vì file không còn nữa.
- `finally` chủ động dọn lại nếu có, rồi xóa root tạm; `deleteIfExists` phù hợp vì file có thể đã bị xóa trong phần xử lý chính.

### 4.2. Kiểm tra `exists` chỉ để quan sát, không phải bảo đảm

Trong ví dụ, `Files.exists(file)` giúp bạn hiểu kết quả. Tuy nhiên, trong ứng dụng có concurrency, thời điểm `exists` và thời điểm `delete` là hai thời điểm khác nhau: một thread khác có thể di chuyển, xóa hoặc thay thế mục đó giữa hai thao tác.

Không lấy mẫu:

```java
if (Files.exists(file)) {
    Files.delete(file);
}
```

làm cơ chế tránh exception chắc chắn. Thay vào đó, chọn đúng `delete` hoặc `deleteIfExists` theo contract và **xử lý `IOException`**.

## 5. `Files.deleteIfExists`: “có thì xóa”, không phải “không bao giờ lỗi”

Chữ ký rút gọn:

```java
public static boolean deleteIfExists(Path path) throws IOException
```

Một quy tắc đọc kết quả:

- `true`: phương thức báo đã xóa mục.
- `false`: phương thức không thể xóa vì mục không tồn tại.
- `IOException`: có lỗi trong quá trình I/O mà API không giải quyết như trường hợp mục vắng mặt.

### 5.1. Idempotency trong cleanup nghĩa là gì?

“Chạy cleanup lặp mà kết quả cuối là mục không tồn tại” là một mục tiêu thường gặp. `deleteIfExists` hữu ích ở đó: khi file đã mất, lời gọi tiếp theo trả false thay vì ném lỗi riêng cho missing file.

Nhưng **idempotency về trạng thái mong muốn** không phải lời hứa rằng toàn bộ hệ thống file tĩnh hoặc lệnh không thể thất bại. Directory có thể không rỗng, file có thể bị process khác giữ, quyền có thể thay đổi, hoặc provider có thể gặp lỗi.

### 5.2. Chương trình B — `DeleteIfExistsDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DeleteIfExistsDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("delete-if-demo-");
        Path file = root.resolve("sample.txt");

        try {
            System.out.println("initialMissing=" + Files.deleteIfExists(file));
            Files.writeString(file, "keep", StandardCharsets.UTF_8);
            System.out.println("firstDelete=" + Files.deleteIfExists(file));
            System.out.println("secondDelete=" + Files.deleteIfExists(file));
            System.out.println("noFile=" + Files.notExists(file));

            Files.createFile(file);
            System.out.println("recreate=" + Files.isRegularFile(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DeleteIfExistsDemo.java
java DeleteIfExistsDemo
```

**Stdout chính xác:**

```text
initialMissing=false
firstDelete=true
secondDelete=false
noFile=true
recreate=true
```

### 5.3. Từng bước xảy ra gì?

1. `file` chưa tồn tại trong directory tạm vừa tạo, nên `deleteIfExists(file)` trả `false`.
2. `Files.writeString` ghi nội dung vào file mới.
3. `deleteIfExists(file)` xóa file và trả `true`.
4. Gọi lại nhận `false`; việc file vắng mặt không phải lỗi của phép “có thì xóa”.
5. `Files.notExists(file)` quan sát thấy file không còn trong thời điểm thử.
6. `Files.createFile(file)` tạo lại một file rỗng với cùng tên; vì path nay trống, thao tác tạo mới thành công.

**Quan trọng:** `deleteIfExists` không “ghi nhớ” file đã xóa. Nếu một process khác tạo file mới **cùng tên** sau đó, lời gọi `deleteIfExists` tiếp theo có thể xóa file mới ấy. Vì vậy không dùng thao tác dựa trên path như bảo đảm xóa “đúng object cũ” khi kẻ khác có quyền thay thế entry.

## 6. Directory rỗng và directory không rỗng

Trên filesystem, directory là mục có thể chứa các entry khác. `Files.delete(directory)` chỉ xóa directory theo hợp đồng **khi nó rỗng**. Nếu còn file hoặc directory con, phép xóa có thể thất bại với `DirectoryNotEmptyException`.

`Files.deleteIfExists(directory)` **không bỏ qua** quy tắc này. Nó chỉ khác ở cách xử lý mục **không tồn tại**; directory còn nội dung vẫn là một vấn đề phải xử lý.

### 6.1. “Rỗng” không có nghĩa trông rỗng trong một cửa sổ Explorer

Directory có thể chứa hidden file, metadata/entry được provider quản lý hoặc file vừa được process khác tạo. Danh sách hiển thị trong GUI có thể không phản ánh đầy đủ những entry đang có. Nếu xóa directory thất bại, đừng lập tức coi Java sai — cần xem lỗi thực tế, permission và trạng thái filesystem.

Không nhất thiết tất cả provider sẽ ném cùng subtype khi directory không rỗng. `DirectoryNotEmptyException` là subtype phù hợp, nhưng API mô tả nó như **optional specific exception** trong những trường hợp tương ứng.

## 7. Chương trình C — Hai API cùng từ chối directory chưa rỗng

Lưu thành **`DeleteDirectoryDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DeleteDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("delete-dir-demo-");
        Path childDir = root.resolve("reports");
        Path file = childDir.resolve("report.txt");

        try {
            Files.createDirectory(childDir);
            Files.createFile(file);
            try {
                Files.delete(childDir);
                System.out.println("nonempty=unexpected");
            } catch (DirectoryNotEmptyException ex) {
                System.out.println("nonempty=DirectoryNotEmptyException");
            }

            try {
                Files.deleteIfExists(childDir);
                System.out.println("ifExistsNonempty=unexpected");
            } catch (DirectoryNotEmptyException ex) {
                System.out.println("ifExistsNonempty=DirectoryNotEmptyException");
            }

            Files.delete(file);
            System.out.println("deletedFile=" + Files.notExists(file));
            Files.delete(childDir);
            System.out.println("deletedEmptyDir=" + Files.notExists(childDir));
            System.out.println("repeatDelete=" + Files.deleteIfExists(childDir));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(childDir);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DeleteDirectoryDemo.java
java DeleteDirectoryDemo
```

**Stdout đã kiểm chứng:**

```text
nonempty=DirectoryNotEmptyException
ifExistsNonempty=DirectoryNotEmptyException
deletedFile=true
deletedEmptyDir=true
repeatDelete=false
```

### 7.1. Diễn giải

- `childDir` chứa `report.txt`, nên cả `delete(childDir)` và `deleteIfExists(childDir)` không thể xóa nguyên directory theo hợp đồng trong tình huống test.
- Trước khi xóa directory, code phải **xóa file con**.
- Sau `Files.delete(file)`, directory `childDir` rỗng và có thể xóa.
- Gọi `deleteIfExists(childDir)` khi directory đã không còn trả `false`.

Nếu các tệp con không do ứng dụng sở hữu, việc “xóa cho sạch để xóa directory” có thể gây mất dữ liệu. Cần xác nhận **ownership và scope** trước khi viết thủ tục recursive delete.

### 7.2. Một directory “không rỗng” không thể sửa bằng cách đổi tên API

Phản ví dụ:

```java
try {
    Files.delete(dir);
} catch (DirectoryNotEmptyException ex) {
    Files.deleteIfExists(dir); // KHÔNG giải quyết directory còn con.
}
```

Đây là **anti-pattern**, không phải một giải pháp. Nếu lỗi do directory chưa rỗng, việc đổi sang `deleteIfExists` không làm mất nội dung con; lời gọi thứ hai có thể ném lỗi như cũ.

Phải **quyết định nghiệp vụ**: chỉ xóa nếu rỗng, từ chối nếu có dữ liệu, hay cho phép xóa đệ quy trên một cây do ứng dụng kiểm soát.

## 8. Symbolic link: xóa liên kết, không xóa target

Một symbolic link là một entry chỉ tới file/directory khác. Theo hợp đồng `Files.delete` và `Files.deleteIfExists`: nếu path cần xóa là một **symbolic link**, chính **link** được xóa, **không phải đích cuối** mà nó trỏ tới.

Ví dụ có ý nghĩa:

```text
workspace/
  original.txt       # regular file chứa dữ liệu
  shortcut.txt  -> original.txt   # symbolic link
```

Nếu gọi:

```java
Files.delete(Paths.get("workspace", "shortcut.txt"));
```

thì ý định là xóa **entry `shortcut.txt`**, không trực tiếp xóa `original.txt`. Đây là đoạn minh họa; hệ thống cần hỗ trợ symbolic link và tài nguyên thật phải tồn tại đúng như sơ đồ.

### 8.1. Đừng dựa vào `Files.exists` để quyết định xóa dangling link

`Files.exists(link)` **theo link theo mặc định** khi quan sát sự tồn tại. Nếu `link` bị đứt (target không còn), phép hỏi có thể trả `false` dù **bản thân symbolic link vẫn tồn tại**.

Vì vậy, pattern:

```java
if (Files.exists(link)) {
    Files.delete(link);
}
```

có thể không xóa một dangling link. `Files.deleteIfExists(link)` được định nghĩa để xóa **chính entry link** nếu nó tồn tại; không cần dùng `exists` như bước bắt buộc.

Khi muốn hỏi sự tồn tại của **chính entry** mà không theo symbolic link, có thể dùng:

```java
Files.exists(link, LinkOption.NOFOLLOW_LINKS);
```

Đây là mảnh minh họa, cần import `Files` và `LinkOption`. Tuy vậy, kiểm tra trước vẫn không loại bỏ race với thao tác xóa tiếp theo.

### 8.2. Symlink bên trong một cây cần xóa

Nếu một directory chứa symbolic link trỏ **ra ngoài** cây, thuật toán recursive delete phải xác định rõ có **theo link** hay không. `Files.walkFileTree(root, visitor)` khi không yêu cầu `FOLLOW_LINKS` **mặc định không đi vào target của symbolic link**; nó xử lý link như một mục được visit.

Đối với hoạt động xóa, cấu hình tự động **theo symbolic links** có thể phá hủy mục không thuộc phạm vi được phép. Trong các chương trình thông thường, **không bật `FOLLOW_LINKS` khi thực hiện recursive delete** nếu không có một thiết kế an toàn, phân quyền và kiểm thử rõ ràng.

### 8.3. Xóa symlink không làm nhiệm vụ quản lý phiên bản dữ liệu

Nếu target còn bản sao, snapshot hoặc hard link khác, xóa một symbolic link không làm dữ liệu biến mất khỏi mọi nơi. Ngược lại, xóa một regular file cũng có thể chỉ làm một directory entry biến mất trong filesystem có hard links.

Các API trả kết quả thao tác theo **filesystem entry/path**, không diễn đạt chính sách xóa bản sao nghiệp vụ hay “xóa mọi tham chiếu”.

## 9. Exception phải được xử lý theo hợp đồng nghiệp vụ

Các ngoại lệ thường gặp là:

| Loại | Khi nào có thể gặp? | Phản ứng gợi ý |
| --- | --- | --- |
| `NoSuchFileException` | Xóa một path không tồn tại bằng `delete` | Nếu missing là lỗi thì báo; nếu được phép thì cân nhắc `deleteIfExists` |
| `DirectoryNotEmptyException` | Xóa directory còn con | Quyết định xóa con hay từ chối; không cố xóa tiếp bằng `deleteIfExists` |
| `AccessDeniedException` | Không được phép hoặc provider từ chối thao tác | Báo/ghi log phù hợp; kiểm tra quyền, file in use, cấu hình |
| `FileSystemException` | Các lỗi filesystem liên quan tên/path/trạng thái | Ghi đủ thông tin chẩn đoán không nhạy cảm; không đoán nguyên nhân chỉ từ tên |
| `IOException` | Lỗi I/O không thể phân loại ở cấp ứng dụng | Propagate, translate có cause, hoặc xử lý theo policy |
| `SecurityException` | Một số runtime/provider có cơ chế kiểm tra bảo mật ở cấp Java | Phân biệt unchecked security error với checked I/O; không dựa vào cơ chế legacy này làm security boundary |

**Lưu ý:** `NoSuchFileException` và `DirectoryNotEmptyException` là **optional specific exceptions** theo đặc tả API. Những provider khác nhau có thể ném một `IOException` khác thay vì subtype bạn đang thấy trên Windows/Linux. Code cần có đường xử lý fallback hợp lý.

### 9.1. Mẫu xử lý lỗi cụ thể

```java
try {
    Files.delete(target);
} catch (NoSuchFileException ex) {
    // Xử lý thiếu mục như một lỗi logic/nghiệp vụ nếu đó là contract.
    throw ex;
} catch (DirectoryNotEmptyException ex) {
    // Không được tự động xóa toàn bộ cây nếu chưa có quyền.
    throw ex;
} catch (IOException ex) {
    // Lỗi permission/I/O/provider khác.
    throw ex;
}
```

Đây là **mảnh minh họa** với `target` kiểu `Path`, cần import các lớp exception và xử lý `IOException` ở caller. Các nhánh đang propagate để minh họa phân loại; trong ứng dụng thật có thể chuyển thành lỗi domain có `cause`, ghi log thích hợp và xử lý ở boundary đã được định nghĩa.

### 9.2. Không biến mọi IOException thành “file đã không tồn tại”

Anti-pattern:

```java
try {
    Files.delete(target);
} catch (IOException ignored) {
    // Sai: file có thể còn nguyên do thiếu quyền hoặc đang được dùng.
}
```

Bắt mọi lỗi rồi bỏ qua khiến caller tin thao tác đã hoàn thành trong khi dữ liệu vẫn còn. Với quy trình cleanup chỉ cho phép bỏ qua missing path, dùng `deleteIfExists` hoặc chỉ bỏ qua đúng lỗi đã được xác định trong contract, chứ không “nuốt” `IOException` tùy tiện.

### 9.3. `deleteIfExists` vẫn có thể ném lỗi khi tên có vẻ đang vắng mặt

Trong hệ thống thực có nhiều luồng/process, giữa việc tra cứu và việc xóa có thể có thay đổi. Chính API Java cảnh báo `deleteIfExists` **không nhất thiết atomic với các thao tác filesystem khác**. Vì vậy đừng viết assertion “với 8 thread, đúng 1 true và 7 false, không bao giờ có exception” như một yêu cầu portable.

Trong môi trường Windows/JDK được thử, các lời gọi delete đồng thời có thể xuất hiện `AccessDeniedException` hoặc số lần trả `true` không ổn định, tùy timing. Kết quả quan sát này **không thay thế hợp đồng chính thức**; nó là ví dụ lý do không được áp đặt mô hình compare-and-swap atomic lên `deleteIfExists`.

**Sự khác biệt hữu ích:** `Files.createFile` được đặc tả là thao tác check-and-create nguyên tử, nhưng `Files.delete`/`deleteIfExists` **không có bảo đảm tương tự về atomicity**. Đừng suy từ tên “IfExists” rằng nó là CAS.

## 10. Xóa file đang được sử dụng: tùy hệ điều hành và provider

Một file có thể đang được mở bởi Java, trình soạn thảo, antivirus, dịch vụ khác hoặc một process trên network filesystem.

- Trên một số hệ điều hành, việc xóa tên một file đang mở có thể bị từ chối cho đến khi handle được đóng.
- Ở những filesystem/OS khác, có thể unlink directory entry dù file còn được một process đang mở giữ handle; ngữ nghĩa tài nguyên đang mở lúc ấy khác nhau.
- Java `Files.delete` và `deleteIfExists` không hứa rằng **mọi open file đều có thể xóa ngay lập tức**.
- Race, quyền ACL, sharing modes, mount và driver có thể ảnh hưởng kết quả.

Nếu bạn tạo một `InputStream`/`OutputStream`/`FileChannel` cho file, hãy **đóng** resource khi xong, ưu tiên try-with-resources. Nhưng đóng resource của mình cũng không bảo đảm một process khác đã thôi dùng file.

### 10.1. Không retry mù quáng

Một số lỗi file-in-use có thể tạm thời, nhưng permission denied hoặc path sai có thể không hết dù retry nhiều lần. Nếu có retry:

1. Phân loại lỗi và xác định lỗi nào thật sự retryable với provider của ứng dụng.
2. Có giới hạn số lần/thời gian và cơ chế backoff.
3. Không làm mất dấu lỗi gốc khi retry thất bại.
4. Đánh giá việc mục đã được tạo lại giữa các lần thử.
5. Không tự retry việc xóa dữ liệu người dùng hoặc dữ liệu quan trọng khi ownership không chắc chắn.

## 11. Không có “recursive delete” tự động: dùng `walkFileTree` khi thật sự cần

Khi một directory chứa file, muốn xóa **cả cây** cần duyệt theo thứ tự đúng: xóa file/entry con trước, xóa directory cha **sau khi đã hết con**.

Java NIO.2 cung cấp `Files.walkFileTree` và `SimpleFileVisitor<Path>`. Mô hình thường gặp:

- `visitFile`: xóa file (và các symlink được visit như file khi không theo link).
- `postVisitDirectory`: sau khi duyệt con, kiểm tra lỗi và xóa directory.
- `visitFileFailed`: xử lý/truyền lỗi theo policy, không bỏ qua một mục rồi tuyên bố đã xóa sạch.

**Bài này chủ yếu về `delete`/`deleteIfExists`**; `walkFileTree` chỉ cho thấy cách phối hợp khi một yêu cầu **thực sự cần** xóa directory nhiều cấp. Không dùng recursive deletion như mặc định mỗi khi `DirectoryNotEmptyException` xuất hiện.

### 11.1. Chương trình D — Xóa cây tạm có cấu trúc biết trước

Tệp **`WalkDeleteDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.atomic.AtomicInteger;

public final class WalkDeleteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("walk-delete-demo-");
        Path job = root.resolve("job");
        Path work = job.resolve("work");
        Path nested = work.resolve("nested");
        AtomicInteger filesDeleted = new AtomicInteger();
        AtomicInteger directoriesDeleted = new AtomicInteger();

        try {
            Files.createDirectories(nested);
            Files.writeString(job.resolve("root.txt"), "r",
                    StandardCharsets.UTF_8);
            Files.writeString(work.resolve("input.txt"), "i",
                    StandardCharsets.UTF_8);
            Files.writeString(nested.resolve("output.txt"), "o",
                    StandardCharsets.UTF_8);

            Files.walkFileTree(job, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attributes)
                        throws IOException {
                    Files.delete(file);
                    filesDeleted.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path directory, IOException error) throws IOException {
                    if (error != null) {
                        throw error;
                    }
                    Files.delete(directory);
                    directoriesDeleted.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("filesDeleted=" + filesDeleted.get());
            System.out.println("directoriesDeleted=" +
                    directoriesDeleted.get());
            System.out.println("jobMissing=" + Files.notExists(job));
            System.out.println("rootStillExists=" + Files.isDirectory(root));
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 WalkDeleteDemo.java
java WalkDeleteDemo
```

**Stdout đã xác minh:**

```text
filesDeleted=3
directoriesDeleted=3
jobMissing=true
rootStillExists=true
```

### 11.2. Đọc theo thứ tự xóa

Trong directory root tạm, chương trình tạo:

```text
root/
  job/
    root.txt
    work/
      input.txt
      nested/
        output.txt
```

`walkFileTree(job, visitor)` duyệt cây `job` nhưng không đụng vào root tạm ngoài `job`. Có ba regular files: `root.txt`, `input.txt`, `output.txt`. Có ba directory thuộc cây được xóa: `job`, `work`, `nested`. Vì vậy counter lần lượt là 3 và 3.

- `visitFile` dùng `Files.delete(file)` để xóa từng mục đã được visit.
- `postVisitDirectory` xóa directory **sau** khi xử lý các mục con.
- Nếu có `IOException error` trong quá trình duyệt con, ví dụ rethrow thay vì giả vờ xóa xong.
- Cuối cùng `jobMissing=true` và `rootStillExists=true`: cây cần xóa mất đi, còn root tạm do test sở hữu vẫn có cho tới `finally`.
- `finally` dọn root tạm sau khi cây đã được xử lý.

### 11.3. Vì sao `visitFileFailed` không nên bị bỏ qua?

`SimpleFileVisitor` có mặc định rethrow nhiều lỗi I/O trong callback `visitFileFailed`. Ví dụ dùng mặc định ấy thay vì cố ý bỏ qua file bị từ chối rồi tuyên bố đã dọn xong.

Nếu bạn xây một công cụ cleanup có chính sách **best-effort**, có thể thu thập lỗi và tiếp tục với những file hợp lệ. Nhưng phải báo chính xác **còn những mục nào chưa xóa**, không âm thầm nuốt lỗi rồi trả “SUCCESS”.

### 11.4. Không tự động bật `FOLLOW_LINKS`

`Files.walkFileTree(job, visitor)` không truyền `FileVisitOption.FOLLOW_LINKS`; theo mặc định, nó không traversal vào target của symlink. Đây là lựa chọn quan trọng khi dọn temp tree. Nếu bật follow links, cần hiểu nguy cơ vòng lặp và đường dẫn ra ngoài scope.

Trong môi trường không tin cậy, ngay cả traversal không follow links cũng cần xét race và quyền filesystem. Một attacker có thể thay đổi directory entries giữa lúc duyệt và xóa; không coi toàn bộ thuật toán trên là sandbox/security boundary tổng quát.

## 12. An toàn khi chọn đường dẫn phải xóa

Khác với đọc file, việc xóa nhầm một file có thể làm mất dữ liệu ngay. Nếu path đến từ request người dùng, thường phải giới hạn nó trong một directory được phép quản lý.

Một kiểm tra **lexical** cơ bản:

```java
Path base = Paths.get("storage").toAbsolutePath().normalize();
Path input = Paths.get("reports", "output.txt");

if (input.isAbsolute()) {
    throw new IllegalArgumentException("Absolute input rejected");
}
Path candidate = base.resolve(input).normalize();
if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Path escapes allowed base");
}
Files.deleteIfExists(candidate);
```

Đây là **mảnh minh họa**, chưa phải giải pháp an toàn hoàn chỉnh. Cần import `Path`, `Paths`, `Files` và xử lý `IOException`.

### 12.1. Vì sao `String.startsWith` không đủ?

Chuỗi `"sandbox-evil"` có tiền tố `"sandbox"` nhưng **không phải thư mục con** của `sandbox`. `Path.startsWith` so theo **thành phần path** trong provider, thích hợp hơn cho kiểm tra lexical.

Tuy nhiên, `Path.startsWith` không giải mọi symlink, junction, mount hoặc TOCTOU. Nếu threat model có người có thể sửa file system giữa kiểm tra và delete, hãy dùng giải pháp access control, directory handles hoặc cơ chế confinement thích hợp.

### 12.2. Tại sao absolute input nguy hiểm?

Với `base.resolve(input)`, nếu `input` là absolute path thì `resolve` trên filesystem mặc định có thể trả **input absolute** thay vì buộc nó nằm dưới base. Xóa mà không kiểm tra có thể tác động ngoài phạm vi dự kiến.

### 12.3. Tại sao `..` nguy hiểm?

`base.resolve(Path.of("..", "outside.txt")).normalize()` có thể trỏ tới file **bên ngoài base**. Dùng `normalize` giúp nhìn ra kiểu traversal thuần từ vựng, nhưng không thay thế bảo vệ filesystem-level.

## 13. Chương trình E — Kiểm tra lexical scope trước khi xóa một file thử

Tệp hoàn chỉnh **`SafeDeleteDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SafeDeleteDemo {
    public static void main(String[] args) throws IOException {
        Path base = Files.createTempDirectory("safe-delete-demo-")
                .toAbsolutePath().normalize();
        Path reports = base.resolve("reports");
        Path file = reports.resolve("report.txt");

        try {
            Files.createDirectory(reports);
            Files.createFile(file);
            Path relative = Path.of("reports", "report.txt");
            Path candidate = base.resolve(relative).normalize();

            System.out.println("isRelative=" + !relative.isAbsolute());
            System.out.println("lexicallyInside=" + candidate.startsWith(base));
            System.out.println("trustedDeleted=" +
                    Files.deleteIfExists(candidate));
            System.out.println("escapeInside=" +
                    base.resolve(Path.of("..", "outside.txt"))
                            .normalize().startsWith(base));
            Path absoluteInput = base.getRoot().resolve("elsewhere.txt");
            System.out.println("absoluteInput=" + absoluteInput.isAbsolute());
            System.out.println("stringPrefixTrap=" +
                    "sandbox-evil".startsWith("sandbox"));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(reports);
            Files.deleteIfExists(base);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SafeDeleteDemo.java
java SafeDeleteDemo
```

**Stdout đúng:**

```text
isRelative=true
lexicallyInside=true
trustedDeleted=true
escapeInside=false
absoluteInput=true
stringPrefixTrap=true
```

### 13.1. Phân tích

- `isRelative=true`: `Path.of("reports","report.txt")` không phải absolute path.
- `lexicallyInside=true`: target hợp lệ được resolve dưới base.
- `trustedDeleted=true`: file do chính test tạo đã được xóa.
- `escapeInside=false`: nếu child là `../outside.txt`, việc normalize làm lộ việc nó vượt base về từ vựng.
- `absoluteInput=true`: một path bắt đầu từ root của base là absolute; contract chỉ cho relative input cần từ chối dạng này.
- `stringPrefixTrap=true`: so tiền tố chuỗi có thể chấp nhận sai tên `sandbox-evil`.

**Giới hạn cần nhớ:** Những boolean này là các kiểm tra ở mức cấu trúc; chúng **không** chứng minh symlink, reparse point hoặc race không thể làm target cuối cùng bị thay thế. Một hệ thống xóa dữ liệu không tin cậy cần thiết kế an toàn vượt ngoài ví dụ này.

### 13.2. `Path.of` là tiện ích Java 11+, không phải API Java 7

Ví dụ dùng `Path.of(...)` vì chạy trên Java 17+. Nếu codebase cần biên dịch đúng Java 7, dùng `Paths.get(...)` với cùng các thành phần. `Files.delete` và `deleteIfExists` bản thân đã được giới thiệu trong NIO.2 từ Java 7.

## 14. Filesystem security: symlink, hard link, TOCTOU và quyền

### 14.1. Path không phải file identity bất biến

Một `Path` là địa chỉ. Giữa hai lệnh Java, một process khác có thể:

- Xóa entry đang có.
- Tạo entry mới cùng tên.
- Di chuyển file sang nơi khác.
- Thay directory bằng symbolic link (trong phạm vi được hệ điều hành cho phép).
- Điều chỉnh permission hoặc ACL.

Vì thế, `Files.isRegularFile(path)` rồi `Files.delete(path)` **không bảo đảm bạn đã xóa chính object mà phép hỏi vừa quan sát**.

### 14.2. `toRealPath` có ích nhưng không giải được mọi race

`Path.toRealPath()` có thể xác định vị trí thực của path hiện hữu theo filesystem và xử lý symlink mặc định, nhưng giữa bước lấy real path và bước delete vẫn có thời gian cho directory entries bị thay đổi.

Không thiết kế xóa file nhạy cảm chỉ với chuỗi “normalize → realPath → startsWith → delete” rồi tuyên bố không còn TOCTOU. Cần cân nhắc directory-relative operations (`SecureDirectoryStream` khi provider hỗ trợ), quản lý quyền trên base và hạn chế khả năng attacker thay thế entry.

### 14.3. Không follow symlink khi không cần

Nếu nhiệm vụ là dọn một temp tree do ứng dụng tạo, thường muốn xóa chính các link và các file trong cây, **không** truy ngược target link ra ngoài. `Files.delete(link)` xóa bản thân link; `walkFileTree` không follow links theo mặc định. Không thay đổi thiết kế này chỉ để “đảm bảo xóa hết”.

### 14.4. Quyền file và directory khác nhau

Quyền xóa phụ thuộc provider, quyền trên directory chứa entry và các thuộc tính filesystem, không chỉ giá trị `Files.isWritable(file)`. Trên một số hệ thống, có thể xóa file dù file không có quyền ghi trực tiếp; ở hệ thống khác, một handle mở hoặc chính sách ACL làm xóa thất bại.

Đừng dùng một phép hỏi quyền đơn lẻ để dự đoán chắc chắn kết quả delete. Hãy thử thao tác trong phạm vi được phép và xử lý exception.

## 15. Cleanup ở `finally` và try-with-resources

Một quy trình thực tế có thể dùng file tạm:

```java
Path temp = Files.createTempFile("export-", ".tmp");
try {
    // Ghi, kiểm tra và sử dụng file tạm.
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là **mảnh minh họa**, cần import `Path` và `Files` cùng xử lý `IOException`. Chỉ dọn file mà ứng dụng **thật sự sở hữu**, không dùng một path tùy ý có thể đã bị bên khác thay thế.

### 15.1. Ngoại lệ lúc cleanup có thể che mất lỗi chính

Nếu phần `try` đã ném lỗi nghiệp vụ, rồi `deleteIfExists(temp)` trong `finally` cũng ném `IOException`, cần chú ý thứ tự exception và việc lỗi cleanup có thể **che** lỗi trước đó tùy cách viết.

Đối với các resource như stream/channel, try-with-resources giúp đóng tài nguyên và quản lý **suppressed exceptions** theo cơ chế của Java. Nhưng `Files.deleteIfExists` là một thao tác I/O riêng, **không tự động được try-with-resources gọi** trừ khi bạn thiết kế một resource wrapper có contract phù hợp.

Chọn chính sách:

- Với cleanup critical, propagate IOException phù hợp, giữ thông tin lỗi gốc.
- Với cleanup best-effort, log lỗi cleanup nhưng không tuyên bố file đã mất.
- Với hệ thống cần cleanup sau crash, cân nhắc quản lý temp directories theo session/job, retention và job quét dọn được kiểm soát.

### 15.2. Không xóa bừa thư mục ngoài phạm vi test

Trong ví dụ chạy thử, tất cả path đều nằm trong root do `Files.createTempDirectory` cấp, và chương trình chỉ xóa những mục đã tạo. Không thử recursive delete trên `home`, root drive, source repository hoặc nơi chứa tài liệu người dùng.

Nếu workflow cần dọn toàn bộ directory được một job sở hữu, hãy tạo một **directory riêng cho job** ngay từ đầu, không chia sẻ cây ấy với các workflow độc lập.

## 16. Khác biệt giữa xóa, di chuyển vào “thùng rác” và lưu trữ an toàn

`Files.delete`/`deleteIfExists` không phải API “move to Recycle Bin/Trash”. Chúng yêu cầu xóa filesystem entry theo hợp đồng và không có giao diện Undo. Nếu người dùng mong có chức năng khôi phục:

- Thiết kế **soft delete** ở tầng ứng dụng.
- Move file tới khu vực cách ly/retention trước khi purge.
- Ghi audit log, thời điểm xóa, actor/permission phù hợp.
- Hỗ trợ backup, versioning hoặc snapshot theo chính sách dữ liệu.
- Chỉ purge thực sự khi điều kiện nghiệp vụ thỏa mãn.

Đây là quyết định sản phẩm/architecture, không phải một tùy chọn tự động bật bằng cách đổi `delete` sang `deleteIfExists`.

### 16.1. Khi nào cần atomic move thay vì delete trực tiếp?

Nếu mục tiêu là thay thế một file hiện hữu mà không để dữ liệu dang dở, có thể viết file tạm rồi `Files.move` theo contract phù hợp thay vì xóa file cũ trước rồi ghi mới vào cùng tên.

Nhưng atomic move phụ thuộc filesystem/provider và quy định `ATOMIC_MOVE`; không coi nó là tính năng bảo đảm mọi nơi. Đó là bài toán **publish dữ liệu**, khác với bài xóa entry hiện tại. Không phối hợp xóa và ghi như một transaction nếu API không cung cấp transaction ấy.

## 17. Bảng những lỗi thường gặp và cách sửa

### 17.1. Gọi `delete` nhiều lần rồi không hiểu lỗi

Nếu file đã bị xóa, `delete` sẽ báo missing theo provider. Hãy xác định trạng thái thiếu file có hợp lệ không: nếu hợp lệ, `deleteIfExists` diễn đạt đúng hơn; nếu không, xử lý exception là tín hiệu của lỗi logic.

### 17.2. Nghĩ `deleteIfExists` sẽ trả false khi không có quyền

Sai. `deleteIfExists` có thể ném `AccessDeniedException` hoặc `IOException`. `false` không phải kết quả chung cho mọi thất bại.

### 17.3. Dùng `deleteIfExists` để xóa directory còn con

Không xóa tự động file con; có thể ném `DirectoryNotEmptyException` như `delete`. Muốn xóa tree, phải được phép và có thuật toán duyệt đúng.

### 17.4. Dùng `exists` trước `delete` để “loại bỏ race”

Check-then-act không nguyên tử. Nếu chấp nhận missing thì dùng `deleteIfExists`, nhưng vẫn xử lý lỗi I/O/concurrency khác.

### 17.5. Nghĩ `deleteIfExists` là atomic compare-and-delete

Không. Java API nói rõ hoạt động xóa có thể cần kiểm tra entry để biết loại, nên không nhất thiết atomic với các hoạt động filesystem khác.

### 17.6. Xóa symbolic link rồi nghĩ target bị xóa

Không. Xóa link là xóa entry link, không phải file/directory target mà nó trỏ tới.

### 17.7. Bỏ qua dangling symbolic link vì `Files.exists` trả false

Khi `exists` follow link, target không tồn tại có thể làm phép hỏi false dù bản thân link còn đó. Hãy hiểu `NOFOLLOW_LINKS` khi kiểm tra link và dùng API xóa theo contract, không phụ thuộc precheck.

### 17.8. Recursive delete dùng `FOLLOW_LINKS` không kiểm soát

Có thể xóa hoặc traversal ra ngoài cây intended. Không tự bật follow links trong công cụ dọn dẹp.

### 17.9. Xóa directory trước khi xóa file con

Directory chưa rỗng không được xóa. Khi xóa tree, xử lý file trước, directory sau bằng `postVisitDirectory`.

### 17.10. Nuốt mọi `IOException` trong finally

Có thể để lại dữ liệu rác, file nhạy cảm hoặc lock file. Xác định policy cleanup và log/propagate để không mất dấu lỗi.

### 17.11. Tưởng `Files.delete` đảm bảo secure erase

Không. API xóa entry, không bảo đảm xóa bản sao vật lý/backup.

### 17.12. Truyền absolute path do người dùng nhập vào base.resolve

Có thể vượt ra ngoài base. Kiểm tra loại path và confinement thực sự.

### 17.13. Dùng `String.startsWith` cho filesystem containment

`"sandbox-evil".startsWith("sandbox")` trả true. Dùng `Path.startsWith` cho kiểm tra lexical, nhưng không quên symlink/race.

### 17.14. Tin rằng một tệp đang mở luôn xóa được

Tùy OS/provider. Đóng handle của ứng dụng, nhận diện AccessDenied/file-in-use và không khẳng định xóa thành công trước khi API báo.

### 17.15. Xóa “tệp cũ” qua path mà không xét bị thay thế

Path có thể được gắn file khác giữa lúc kiểm tra và lúc xóa. Nếu identity quan trọng, thiết kế filesystem-level synchronization/ownership; một phép hỏi trước không khóa entry.

## 18. Ma trận kiểm thử cho hai API

| Tình huống | `delete` | `deleteIfExists` | Điểm kiểm tra |
| --- | --- | --- | --- |
| Regular file có thật | Xóa thành công | `true` nếu xóa được | File không còn tại path |
| File chưa từng tồn tại | Báo lỗi, thường `NoSuchFileException` | `false` | Missing được xử lý khác nhau |
| File đã xóa ở lần trước | Báo lỗi khi xóa lại | `false` | Cleanup lặp |
| Empty directory | Xóa được | `true` nếu xóa được | Directory rỗng |
| Non-empty directory | Lỗi, thường `DirectoryNotEmptyException` | Vẫn lỗi | Không recursive |
| Symbolic link | Xóa link | Xóa link, thường `true` | Target không bị xóa |
| Dangling symbolic link | Xóa link nếu được phép | Xóa link nếu được phép | `Files.exists` có thể false khi follow |
| File đang được process khác mở | Tùy provider | Tùy provider | `IOException` vẫn có thể xuất hiện |
| Thiếu quyền | Lỗi I/O hoặc security | Lỗi I/O hoặc security | Không trả false chung cho mọi lỗi |
| Hai thread xóa cùng path | Không có bảo đảm atomic chung | Không có bảo đảm atomic chung | Không assert một true, nhiều false bất biến |
| Permission thay đổi giữa check và delete | Có thể lỗi | Có thể lỗi | Không dùng precheck như đồng bộ |
| Path ngoài base do `..` | Có thể xóa nhầm nếu không xác minh | Có thể xóa nhầm | Security/ownership |
| Tệp nằm sau symbolic link trong cây | Phụ thuộc path thực và traversal | Tương tự | Không nhầm link với target |

### 18.1. Chọn test đúng bản chất API

Test nên chứa ít nhất:

1. File mới, gọi `delete` một lần.
2. File không còn, gọi `delete` để kiểm tra error path.
3. File vắng, `deleteIfExists` trả false.
4. File có thật, `deleteIfExists` trả true.
5. Directory rỗng, xóa thành công.
6. Directory chứa file, cả hai API phải từ chối xóa theo contract.
7. Xóa file con rồi directory cha.
8. Nếu filesystem hỗ trợ, tạo symbolic link tới target rồi xác nhận chỉ link bị xóa.
9. Lặp cleanup và bảo đảm không xóa dữ liệu ngoài phạm vi thử.
10. Test lỗi permission/file-in-use khi môi trường CI cho phép, nhưng không hardcode subtype cho mọi hệ điều hành.

### 18.2. Đừng gán stdout cố định cho concurrency test không được đặc tả

Khi nhiều thread/process gọi `deleteIfExists` cùng lúc, **đặc tả không bảo đảm atomicity**. Kết quả số lần trả true/false có thể phụ thuộc provider và lịch chạy; một số tình huống có thể ném `IOException`. Nếu viết test cạnh tranh, kiểm tra các invariant thực sự thuộc contract của ứng dụng và chấp nhận các trạng thái lỗi hợp lệ, **không yêu cầu một pattern boolean cố định trên mọi máy**.

Trong các ví dụ runnable phía trên, mọi thao tác xóa đều diễn ra có kiểm soát trong temp directory để có stdout xác định.

## 19. Quy trình triển khai an toàn

Khi một tính năng cần “xóa tài liệu đã lưu”, hãy theo quy trình:

1. **Xác định yêu cầu nghiệp vụ:** xóa bắt buộc, xóa nếu còn, move sang thùng rác ứng dụng hay soft-delete.
2. **Xác định authority:** người dùng/service có quyền xóa mục này không?
3. **Giới hạn phạm vi:** target phải được chọn từ identifier/đường dẫn đã xác thực, không tự dùng path từ raw input chưa kiểm tra.
4. **Xác định loại đối tượng:** regular file, empty directory, symbolic link hay directory tree.
5. **Nếu directory tree:** chỉ xóa đệ quy khi caller được ủy quyền rõ và tree thuộc phạm vi ứng dụng.
6. **Chọn API:** `delete` khi missing là lỗi; `deleteIfExists` khi missing là chấp nhận được.
7. **Không precheck để giả làm atomic:** tránh phụ thuộc `exists` rồi mới xóa.
8. **Xử lý lỗi:** missing, directory-not-empty, permission, file-in-use, provider I/O.
9. **Tránh TOCTOU/symlink:** bảo đảm confinement/permission bằng thiết kế filesystem phù hợp.
10. **Ghi audit nếu cần:** actor, resource ID, thời điểm, kết quả, nhưng không log nội dung bí mật.
11. **Dọn temp riêng:** theo dõi ownership và giới hạn cleanup.
12. **Kiểm thử trên file tạm và môi trường triển khai thực:** Windows/Linux/provider có thể khác nhau về loại exception và open handles.
13. **Không đồng nhất API success với secure erasure:** retention, backup và recovery cần thiết kế riêng.

### Checklist code review

- [ ] `delete` và `deleteIfExists` được phân biệt theo contract missing path.
- [ ] Không đợi `Files.delete` trả boolean; nó là `void`.
- [ ] Không coi `false` của `deleteIfExists` là “lỗi xóa bất kỳ”.
- [ ] Đã xử lý `IOException`/subtypes theo nghiệp vụ.
- [ ] Directory không rỗng không bị xóa bừa; recursive deletion có scope rõ.
- [ ] Đã hiểu symbolic link bị xóa là link, không phải target.
- [ ] Có chính sách với dangling link và `NOFOLLOW_LINKS` khi kiểm tra.
- [ ] Không dựa vào atomicity khi nhiều thread/process cùng xóa.
- [ ] Không dùng `exists`/`isRegularFile` trước delete như phép khóa.
- [ ] Không để xóa diễn ra bên ngoài base được cấp quyền.
- [ ] Đã cân nhắc symlink, TOCTOU, path traversal, mount và permission.
- [ ] Có test empty/non-empty directory và file đã bị xóa từ trước.
- [ ] Có test cleanup trong root tạm không làm thay đổi file của người dùng.
- [ ] Không nhầm xóa entry với secure erase hoặc soft delete.
- [ ] Đã ghi rõ API Java 7 và các tiện ích Java 11+ dùng trong ví dụ.

## 20. Bài tập thực hành

**Bài 1 — Nhận diện API.** Một tệp `report.txt` phải tồn tại trước khi chuyển trạng thái từ “published” sang “removed”. Hãy chọn `delete` hay `deleteIfExists` và giải thích tại sao trường hợp file vắng là lỗi hay trạng thái cho phép.

**Bài 2 — Cleanup idempotent.** Tạo file trong temp directory rồi gọi `deleteIfExists` hai lần. Dự đoán hai boolean; kiểm tra kết quả bằng `DeleteIfExistsDemo`.

**Bài 3 — Missing file.** Gọi `Files.delete` trên một path chưa tạo. Quan sát exception trên provider bạn đang dùng. Vì sao không nên bắt mọi `IOException` rồi tuyên bố “không tồn tại”?

**Bài 4 — Non-empty directory.** Tạo directory `reports`, thêm file `a.txt`, gọi hai API xóa lên directory. Tại sao cả hai đều có thể ném `DirectoryNotEmptyException`?

**Bài 5 — Thứ tự xóa.** Có cây `job/a/b/c.txt`. Hãy viết kế hoạch xóa con trước cha sau; sau đó dùng `walkFileTree` trong temp root để kiểm chứng.

**Bài 6 — Dangling link.** Trên filesystem có hỗ trợ symlink, tạo symbolic link tới target rồi xóa target. `Files.exists(link)` và `Files.exists(link, NOFOLLOW_LINKS)` có thể khác nhau ra sao? Làm thế nào để xóa chính link?

**Bài 7 — Permission.** Một process thiếu quyền xóa file. `deleteIfExists` có được phép đơn giản trả false thay vì exception không? Nêu ý nghĩa của `false` trong API.

**Bài 8 — Concurrency.** Hai thread cùng gọi `deleteIfExists`. Có thể khẳng định đúng một lời gọi trả true, lời gọi còn lại trả false, không bao giờ ném lỗi không? Tra lại Java API để giải thích.

**Bài 9 — Name reuse.** Một file bị xóa, sau đó file khác cùng tên được tạo. Điều gì có thể xảy ra nếu tác vụ cleanup cũ tiếp tục gọi `deleteIfExists` trên path ấy?

**Bài 10 — Path traversal.** Người dùng nhập `../secret.txt` trong API chỉ cho phép xóa file dưới `base`. Viết phép kiểm tra lexical và nêu vì sao nó không đủ cho symlink race.

**Bài 11 — String prefix trap.** Tại sao `"sandbox-evil".startsWith("sandbox")` trả true nhưng không chứng minh file thuộc thư mục `sandbox`? Sửa bằng `Path.startsWith` cho kiểm tra lexical.

**Bài 12 — Xóa file đang mở.** Đang có một `FileChannel` đọc file, process khác xóa nó. Vì sao hành vi phụ thuộc OS/provider? Bạn cần test/exception handling gì?

**Bài 13 — Cleanup exception.** Trong `finally`, thao tác delete lỗi trong khi `try` đã ném một exception khác. Hãy thiết kế cách báo cáo lỗi cleanup mà không vô tình mất dấu lỗi chính.

**Bài 14 — Soft delete.** Ứng dụng yêu cầu người dùng có thể khôi phục tài liệu trong 30 ngày. Vì sao gọi `Files.delete` ngay không đáp ứng hoàn toàn? Thiết kế mô hình trạng thái/retention phù hợp.

**Bài 15 — Test portable.** Chuyển bài thử đang xóa `C:\\Users\\Developer\\Desktop\\temp.txt` thành test dùng `Files.createTempDirectory`, và chứng minh cleanup không chạm ra ngoài root tạm.

**Bài 16 — Hard links và backup.** Sau `Files.delete(path)` thành công, bạn có thể kết luận mọi bản sao dữ liệu đã bị xóa vật lý chưa? Vì sao cần phân biệt delete, unlink, backup và secure erase?

### Gợi ý đáp án ngắn

- **Bài 1:** `delete` phát hiện missing path bằng exception, phù hợp khi missing là lỗi nghiệp vụ.
- **Bài 2:** Với file đã tạo và không có cạnh tranh, lần đầu true, lần sau false.
- **Bài 3:** Trên nhiều provider là `NoSuchFileException`; không nuốt mọi `IOException`.
- **Bài 4:** `deleteIfExists` chỉ khác ở trường hợp *không tồn tại*, không có recursive semantics.
- **Bài 5:** Xóa file trước rồi xóa directory theo thứ tự post-order.
- **Bài 6:** `exists` có thể false với dangling link nếu follow; xóa bằng `deleteIfExists` hoặc `delete` trên chính link.
- **Bài 7:** Không; lỗi permission thường được báo dưới dạng `IOException`.
- **Bài 8:** Không; đặc tả nói phương thức không bảo đảm atomic với filesystem operations khác.
- **Bài 9:** Cleanup theo path có thể tác động lên object mới nếu tên được tái sử dụng.
- **Bài 10:** Check relative/normalize/Path.startsWith là lớp lexical; vẫn cần confinement ở cấp filesystem.
- **Bài 11:** Path prefix xét thành phần path; String prefix chỉ xét text.
- **Bài 12:** File-in-use có policy khác giữa OS/providers; xử lý lỗi theo contract.
- **Bài 13:** Cân nhắc suppressed exception, logging hoặc cách propagate giữ cause.
- **Bài 14:** Cần soft delete/quarantine cùng retention thay vì xóa entry ngay.
- **Bài 15:** Test root tạm giúp giới hạn ownership và tránh xóa file thật của người dùng.
- **Bài 16:** Không; API không bảo đảm secure erasure hay xóa mọi bản sao.

## 21. Tài liệu chính thức và những điểm cần tra khi dùng

- [Java SE 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): hợp đồng `delete(Path)` và `deleteIfExists(Path)`, loại mục, symbolical link, directory rỗng, khả năng không atomic và ngoại lệ I/O.
- [Java SE 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `isAbsolute`, `startsWith` và đường dẫn theo filesystem provider.
- [Java SE 17 — `java.nio.file.NoSuchFileException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html): một subtype khi mục không tồn tại.
- [Java SE 17 — `java.nio.file.DirectoryNotEmptyException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryNotEmptyException.html): subtype cho tình huống directory chưa rỗng.
- [Java SE 17 — `java.nio.file.AccessDeniedException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html): thao tác bị từ chối truy cập.
- [Java SE 17 — `java.nio.file.FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` cho thao tác duyệt cây.
- [Java SE 17 — `java.nio.file.SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): mẫu callback duyệt file/directory, xử lý lỗi trong quá trình traversal.
- [Java SE 17 — `java.nio.file.LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` khi kiểm tra entry.
- [Java SE 17 — `java.nio.file.SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): API directory-relative có thể giảm một số race trên provider hỗ trợ.

**Kết luận:** `Files.delete` là lời yêu cầu xóa một mục mà việc mục vắng mặt được báo bằng lỗi; `Files.deleteIfExists` chấp nhận tình trạng mục vắng mặt qua boolean. **Cả hai không tự xóa recursive, không đảm bảo atomic với mọi hoạt động filesystem khác, vẫn có thể gặp IOException và xóa symbolic link chứ không xóa target.** Chỉ xóa đúng phạm vi có quyền, xử lý ngoại lệ theo nghiệp vụ, dùng hậu duyệt khi thật sự cần xóa cây, và không đánh đồng xóa path với tẩy hoàn toàn mọi dữ liệu trên storage.