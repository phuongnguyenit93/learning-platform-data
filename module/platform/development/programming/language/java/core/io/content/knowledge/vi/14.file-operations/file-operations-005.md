# Files.delete khác Files.deleteIfExists trong Java

`Files.delete(Path)` và `Files.deleteIfExists(Path)` đều dùng để **xóa một entry của hệ thống tệp**: tệp thông thường, symbolic link hoặc thư mục rỗng. Khác biệt quan trọng nhất không phải ở cách xóa, mà ở **cách báo cáo trường hợp đường dẫn không tồn tại**:

- **`Files.delete(path)`:** không trả giá trị; xóa thành công thì đi tiếp. Nếu không có entry cần xóa, thông thường ném **`NoSuchFileException`**.
- **`Files.deleteIfExists(path)`:** trả **`true`** nếu xóa được một entry, **`false`** nếu không có entry để xóa. Những lỗi xóa thật sự khác **vẫn có thể ném `IOException`**.

Khi chọn API, câu hỏi nên là: **"Việc không có tệp là lỗi nghiệp vụ, hay là trạng thái đã đạt mục tiêu?"** Không có phương thức nào tự động xóa cả cây thư mục hoặc bảo đảm việc xóa sẽ luôn thành công.

## 1. Đặt hai phương thức cạnh nhau

Cả hai thuộc `java.nio.file.Files`, dùng `Path` thuộc `java.nio.file.Path` và có thể ném `IOException`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn minh họa: đặt trong phương thức khai báo throws IOException.
Path file = Path.of("data", "report.txt");

Files.delete(file);                   // void, thiếu file -> ngoại lệ
boolean removed = Files.deleteIfExists(file); // true hoặc false
```

Cú pháp chính:

```java
public static void delete(Path path) throws IOException

public static boolean deleteIfExists(Path path) throws IOException
```

Đây là **mô tả chữ ký API**, không phải hai lệnh khai báo có thể dán tự do vào phương thức. `delete` có kiểu trả về `void`; `deleteIfExists` trả về `boolean`.

| Tình huống | `Files.delete(path)` | `Files.deleteIfExists(path)` |
| --- | --- | --- |
| Entry tồn tại và xóa thành công | Hoàn tất, không có giá trị trả về | Trả `true` |
| Entry không tồn tại | Ném `NoSuchFileException` trong trường hợp thông thường | Trả `false` |
| Không có quyền xóa, lỗi hệ thống tệp | Ném `IOException` hoặc ngoại lệ phù hợp | **Vẫn có thể ném ngoại lệ** |
| Thư mục còn chứa entry | Thường ném `DirectoryNotEmptyException` | Tương tự; **không** trả `false` để thay lỗi |
| Symbolic link tồn tại | Xóa **liên kết**, không xóa đích | Xóa **liên kết**, trả `true` nếu thành công |
| Có cần kiểm tra `Files.exists` trước không? | Không; gọi trực tiếp và xử lý kết quả/lỗi | Không; gọi trực tiếp và xử lý `boolean`/lỗi |
| Có xóa đệ quy không? | Không | Không |

**Cảnh báo:** `false` của `deleteIfExists` **không phải** cách báo “không có quyền”, “thư mục không rỗng” hay “I/O hỏng”. Những tình huống đó không được đánh đồng với “đường dẫn không tồn tại”.

## 2. `Files.delete(path)`: vắng mặt là lỗi

Nếu chương trình cần xóa **một đối tượng mà nghiệp vụ yêu cầu phải tồn tại**, `delete` giúp phát hiện trường hợp bất thường:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void removeExpectedFile(Path path) throws IOException {
    Files.delete(path);
}
```

Đoạn mã là **phương thức minh họa** cần đặt trong class. Nếu `path` không có entry tương ứng, `Files.delete(path)` sẽ báo lỗi khi file được coi là không tồn tại, thay vì giả vờ “xóa thành công”.

Có thể xử lý riêng trường hợp vắng mặt:

```java
import java.nio.file.NoSuchFileException;

try {
    Files.delete(path);
} catch (NoSuchFileException e) {
    System.err.println("Không có đường dẫn cần xóa: " + path);
}
```

Đoạn mã minh họa giả định đã có `Path path`, các import `Files` và được đặt trong phương thức xử lý/khai báo các `IOException` khác. Không nên bắt `IOException` rộng rồi coi tất cả là “không tìm thấy file”, vì việc xóa có thể thất bại do nguyên nhân nghiêm trọng hơn.

**Ví dụ phù hợp:** quá trình di chuyển file tạm sang nơi lưu chính đã ghi nhận rằng một file nhất định phải tồn tại, và bước dọn dẹp yêu cầu xác minh giả định này. Nếu file đã mất ngoài ý muốn, việc ném `NoSuchFileException` có thể giúp phát hiện lỗi quy trình.

## 3. `Files.deleteIfExists(path)`: vắng mặt là một kết quả hợp lệ

Nếu mục tiêu chỉ là **“sau bước dọn dẹp không còn entry ở đường dẫn này”**, thì không có entry ngay từ đầu thường không phải lỗi:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static boolean removeOptionalFile(Path path) throws IOException {
    return Files.deleteIfExists(path);
}
```

Phương thức minh họa trả:

- `true` nếu lời gọi **thực sự xóa được entry**;
- `false` nếu entry **không tồn tại**, nên không có gì để xóa;
- Ngoại lệ nếu xảy ra lỗi truy cập hoặc lỗi I/O phù hợp, chẳng hạn thư mục không rỗng.

Điều quan trọng là **“xóa nếu tồn tại” không đồng nghĩa “bỏ qua mọi lỗi”**. Chẳng hạn:

```java
boolean deleted = Files.deleteIfExists(path);

if (deleted) {
    System.out.println("Đã xóa một entry");
} else {
    System.out.println("Entry đã không tồn tại");
}
```

Đây là mã minh họa với `path` đã khai báo và `IOException` đã được xử lý/khai báo ở phương thức bao quanh. Nếu lời gọi ném lỗi thì chương trình **không** đi tiếp vào nhánh `if` như thể `deleted=false`.

### Có thể gọi nhiều lần không?

Nếu không có tác nhân khác thay đổi đường dẫn, cùng một file:

```text
Lần 1: deleteIfExists(path) -> true  (file đã bị xóa)
Lần 2: deleteIfExists(path) -> false (không có entry để xóa)
```

Đây là hành vi thuận tiện cho các thao tác dọn file tạm, nhưng chỉ là tính **idempotent đối với trạng thái vắng mặt trong điều kiện phù hợp**. Nếu một tiến trình khác tạo lại file giữa các lần gọi, lần sau có thể xóa một file **mới** tại cùng tên; vì vậy không nên xem lời gọi lặp là an toàn tuyệt đối trong môi trường cạnh tranh.

## 4. Chương trình Java 17+ độc lập, kiểm thử cả hai phương thức

Ví dụ tạo một thư mục tạm riêng, tạo hai file nhỏ, rồi kiểm chứng hành vi xóa khi entry có mặt và khi vắng mặt. Ví dụ **không đụng vào file do người dùng chỉ định** và dọn thư mục đã tạo trong khối `finally`.

Lưu nguyên mã vào file **`DeleteVsDeleteIfExistsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class DeleteVsDeleteIfExistsDemo {

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("java-delete-demo-");
        Path optional = directory.resolve("optional.txt");
        Path required = directory.resolve("required.txt");

        try {
            Files.writeString(optional, "one", StandardCharsets.UTF_8);

            System.out.println("Optional first removal: " +
                    Files.deleteIfExists(optional));
            System.out.println("Optional second removal: " +
                    Files.deleteIfExists(optional));

            Files.writeString(required, "two", StandardCharsets.UTF_8);
            Files.delete(required);
            System.out.println("Required removal: done");

            try {
                Files.delete(required);
            } catch (NoSuchFileException expected) {
                System.out.println(
                        "Required missing: NoSuchFileException");
            }

            System.out.println("Directory still exists: " +
                    Files.isDirectory(directory));
        } finally {
            // Dọn duy nhất những entry do ví dụ vừa tạo.
            Files.deleteIfExists(optional);
            Files.deleteIfExists(required);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 DeleteVsDeleteIfExistsDemo.java
java DeleteVsDeleteIfExistsDemo
```

**Stdout khi hệ thống tệp tạm hoạt động bình thường:**

```text
Optional first removal: true
Optional second removal: false
Required removal: done
Required missing: NoSuchFileException
Directory still exists: true
```

Giải thích theo thứ tự:

1. `Files.createTempDirectory` tạo thư mục riêng để bài thử không xóa file có sẵn. Hai lời gọi `resolve` tạo **đường dẫn**, chưa tạo nội dung file.
2. `Files.writeString(optional, ...)` tạo file tạm thứ nhất. Lần gọi `deleteIfExists` đầu trả `true`.
3. Vì file đã không còn, lần gọi `deleteIfExists` tiếp theo trả `false`, không ném `NoSuchFileException`.
4. `Files.writeString(required, ...)` tạo file thứ hai. `Files.delete(required)` xóa thành công nên không có giá trị trả về.
5. `Files.delete(required)` lần hai ném `NoSuchFileException` và được `catch` xử lý riêng để in dòng dự kiến.
6. Thư mục tạm vẫn tồn tại: **xóa hai file bên trong không đồng nghĩa xóa thư mục cha**. Khối `finally` sau đó thử dọn file và thư mục do chính ví dụ tạo.

Các điều kiện quyền hạn, lỗi filesystem hoặc tiến trình ngoài can thiệp có thể làm bài thử ném `IOException`, vì vậy stdout được mô tả cho **điều kiện I/O bình thường**. Ví dụ không giả định đường dẫn tạm có tên cố định.

## 5. Xóa thư mục: chỉ xóa khi phù hợp, không đệ quy

Cả hai API đều có thể xóa **thư mục rỗng**. Nếu thư mục còn chứa các entry, việc xóa thường thất bại với `DirectoryNotEmptyException` (ngoại lệ cụ thể này không được mọi provider/hệ điều hành bảo đảm trong mọi trường hợp).

Ví dụ minh họa:

```java
import java.io.IOException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.Path;

static void deleteEmptyDirectory(Path directory)
        throws IOException {
    try {
        Files.delete(directory);
    } catch (DirectoryNotEmptyException e) {
        System.err.println("Thư mục còn chứa entry: " + directory);
        throw e;
    }
}
```

Đây là **phương thức minh họa** cần đặt trong class. Nếu dùng `Files.deleteIfExists(directory)`, phương thức **không** tự dọn tất cả file con để sau đó trả `true`; khi thư mục còn nội dung, nó vẫn có thể ném ngoại lệ I/O.

### Có thể xóa cả cây thư mục không?

Không có tham số `recursive=true` cho hai phương thức này. Để dọn cây thư mục do ứng dụng tạo, có thể dùng `Files.walkFileTree` với `FileVisitor`, xóa file trước, rồi xóa thư mục trong `postVisitDirectory`. Với dữ liệu không tin cậy hoặc folder người dùng, đây là thao tác **nguy hiểm nếu thiếu giới hạn đường dẫn, quyền và chính sách symlink**; không nên chạy mã xóa đệ quy chỉ để xử lý một `DirectoryNotEmptyException`.

Nếu mục tiêu chỉ là xóa một file, **đừng** triển khai xóa đệ quy. Việc khác biệt giữa file và thư mục nằm ở hệ thống tệp thực tế, không nằm ở phần mở rộng như `.txt`.

## 6. Symbolic link: xóa liên kết, không xóa file đích

Nếu `path` là **symbolic link**, cả `Files.delete(path)` và `Files.deleteIfExists(path)` đều xóa **bản thân entry liên kết**, không tự đi theo link để xóa file mục tiêu.

```text
link.txt  --symbolic link--> target.txt

Files.deleteIfExists(link.txt)
    -> xóa link.txt
    -> target.txt vẫn còn (nếu không bị tác động theo cách khác)
```

Điều này vẫn quan trọng với **dangling symbolic link** — liên kết còn tồn tại nhưng mục tiêu đã mất. Kiểm tra `Files.exists(link)` theo mặc định **đi theo symbolic link**, nên có thể trả `false` dù entry link vẫn hiện hữu.

Trong trường hợp muốn kiểm tra **chính entry liên kết**:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

boolean entryPresent = Files.exists(
        path, LinkOption.NOFOLLOW_LINKS);
```

Đoạn này cần `path` là `Path` có sẵn. Tuy vậy, **không bắt buộc** kiểm tra trước khi xóa: `deleteIfExists` đã diễn đạt rõ ý định “xóa entry nếu có” và tránh một bước kiểm tra riêng dễ sinh race.

Không dùng `Files.isRegularFile(path)` như điều kiện duy nhất để quyết định xóa symbolic link, vì tùy tùy chọn, phép kiểm tra có thể theo link tới đích hoặc trả kết quả khác với việc tồn tại entry link.

## 7. Vì sao không dùng `Files.exists` rồi mới `delete`?

Cách thường thấy:

```java
if (Files.exists(path)) {
    Files.delete(path);
}
```

Nhìn hợp lý nhưng có **time-of-check to time-of-use (TOCTOU)**:

```text
Luồng A: Files.exists(path) -> true
Luồng B: xóa path
Luồng A: Files.delete(path) -> NoSuchFileException
```

Giữa lúc kiểm tra và lúc dùng, trạng thái hệ thống tệp đã thay đổi. Hai lời gọi không ghép thành một giao dịch nguyên tử.

Nếu “không tồn tại” **là trạng thái chấp nhận được**, sử dụng trực tiếp:

```java
Files.deleteIfExists(path);
```

Nếu “không tồn tại” **là lỗi**, sử dụng trực tiếp:

```java
Files.delete(path);
```

**Đừng đánh đồng điều này với bảo đảm atomicity.** Tài liệu Java cũng cảnh báo `deleteIfExists` có thể **không nguyên tử** đối với các hoạt động file system khác. Một tiến trình khác có thể tạo, xóa hoặc thay entry đồng thời. Với dữ liệu quan trọng, phải thiết kế đồng bộ/ownership và phạm vi xóa phù hợp, không chỉ dựa vào một tên API.

## 8. Lỗi truy cập và ngoại lệ: `false` không có nghĩa “mọi lỗi đều bỏ qua”

Những ngoại lệ hữu ích khi xử lý API NIO:

| Ngoại lệ | Ý nghĩa điển hình | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Entry không tồn tại khi thao tác cần xóa | Nếu vắng mặt hợp lệ, dùng `deleteIfExists`; nếu không, báo lỗi |
| `DirectoryNotEmptyException` | Thư mục còn entry, không xóa được bằng thao tác đơn lẻ | Xác định đúng mục tiêu; không tự động dọn đệ quy |
| `AccessDeniedException` | Quyền truy cập/chính sách hệ thống từ chối | Kiểm tra quyền và ownership |
| `FileSystemException` | Lỗi file system chi tiết, có thể kèm lý do | Ghi thông tin phù hợp và xử lý theo nghiệp vụ |
| `IOException` | Lỗi I/O tổng quát hoặc được provider báo | Không gộp thành “entry không tồn tại” |
| `SecurityException` | Môi trường có cơ chế kiểm tra quyền tương ứng có thể từ chối | Xử lý theo chính sách bảo mật |

Các subclass cụ thể như `AccessDeniedException` và `DirectoryNotEmptyException` phụ thuộc provider/OS; không phải mọi hệ thống báo đúng cùng một loại lỗi cho cùng hiện tượng.

**Phân biệt trả giá trị và ném lỗi:**

```java
try {
    boolean removed = Files.deleteIfExists(path);
    System.out.println(removed ? "Đã xóa" : "Đã không tồn tại");
} catch (IOException e) {
    System.err.println("Không thể hoàn thành thao tác xóa: "
            + e.getMessage());
    throw e;
}
```

Đoạn minh họa cần `path` có sẵn và đặt trong phương thức `throws IOException`. Nếu lỗi thực sự, không trả về `false`: ngoại lệ đi ra ngoài để tầng gọi xử lý.

### Xóa file đang mở

Trên một số hệ điều hành, ứng dụng có thể xóa entry của file đang mở; trên môi trường khác, file đang được tiến trình khác giữ có thể không xóa được. Đừng viết logic giả định hành vi giống nhau trên Windows, Linux và mọi filesystem. Với file do mình mở, hãy **đóng stream/reader/writer** đúng lúc bằng `try-with-resources` trước khi thực hiện dọn dẹp.

## 9. So với `java.io.File.delete()` truyền thống

Tên gần giống nhưng API khác:

```java
import java.io.File;

File legacy = new File("old.txt");
boolean removed = legacy.delete();
```

`File.delete()` trả về `boolean` và có cơ chế báo lỗi kém chi tiết hơn: `false` có thể do đường dẫn không tồn tại **hoặc** xóa thất bại. Trong khi đó:

- `Files.delete(path)`: báo tình huống không tồn tại và nhiều lỗi I/O bằng ngoại lệ.
- `Files.deleteIfExists(path)`: `false` dành cho tình huống vắng mặt; các lỗi I/O **khác vẫn được báo bằng ngoại lệ**.

Với code Java hiện đại, `Path` + `Files` thường cung cấp thông tin thất bại rõ hơn. Nếu đã có `File`, có thể chuyển đổi mà không tác động tới nội dung tệp:

```java
File file = new File("report.txt");
Path path = file.toPath();
Files.deleteIfExists(path);
```

Đây là đoạn minh họa cần import `Path`, `Files` và xử lý `IOException`. `file.toPath()` chỉ chuyển biểu diễn đường dẫn; `Files.deleteIfExists` mới là lời gọi có tác dụng xóa.

Không nên nhầm `Files.deleteIfExists` với `File.delete()`: tuy cùng trả về `boolean`, cách chúng biểu đạt **lỗi thật** không giống nhau.

## 10. Tình huống nên chọn API nào?

| Nhu cầu | Gợi ý | Vì sao |
| --- | --- | --- |
| Xóa file tạm nếu nó còn sau xử lý | `Files.deleteIfExists` | File đã biến mất không phải lỗi |
| Dọn kết quả trung gian trong `finally` | `Files.deleteIfExists`, vẫn xử lý `IOException` | Dọn được cả khi chưa kịp tạo file |
| Một workflow yêu cầu đối tượng phải tồn tại | `Files.delete` | Phát hiện trạng thái bất thường |
| Gỡ bỏ một file đã được xác định chắc chắn theo nghiệp vụ | `Files.delete` nếu thiếu file cần báo lỗi | Đưa ra tín hiệu bằng exception |
| Xóa thư mục rỗng | Cả hai, tùy ngữ nghĩa vắng mặt | Cả hai đều không đệ quy |
| Xóa cả cây thư mục | Cơ chế duyệt file tree phù hợp, kiểm soát phạm vi | Không API nào trong hai API xóa đệ quy |
| Xóa symbolic link | Cả hai xóa entry link | Không xóa mục tiêu của link |
| Xóa file do người dùng chỉ định | Kiểm soát đường dẫn/quyền/symlink rồi chọn API | Tên phương thức không bảo vệ khỏi xóa nhầm |
| Xóa nhiều entry có trạng thái cạnh tranh | Thiết kế ownership/đồng bộ và xử lý lỗi | Không thể loại bỏ race chỉ bằng `deleteIfExists` |

### Ví dụ `finally` khi file tạm có thể chưa được tạo

Nếu xử lý lỗi xảy ra trước khi tạo xong file, việc dọn có thể diễn ra khi file chưa tồn tại:

```java
Path temp = Path.of("work", "temporary-result.bin");

try {
    // Tác vụ có thể thành công hoặc thất bại trước khi tạo temp.
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là đoạn minh họa về **ý tưởng dọn dẹp**; cần đặt trong phương thức khai báo/xử lý `IOException` và chỉ xóa file **do tác vụ sở hữu**. Không được tự xóa tên file dùng chung của hệ thống nếu không có bảo đảm ownership; đoạn mã trên không tự tạo file.

Nếu ngoại lệ từ `deleteIfExists` xảy ra trong `finally`, nó có thể ảnh hưởng tới ngoại lệ đang được truyền ra từ thân `try`. Với ứng dụng cần bảo toàn **nguyên nhân thất bại chính**, hãy thiết kế chiến lược xử lý riêng cho lỗi dọn dẹp (ví dụ ghi log, suppressed exception hoặc `try-with-resources` với đối tượng tài nguyên phù hợp).

## 11. Xóa đường dẫn trong ứng dụng có bảo mật và đồng thời

Xóa file là thao tác **không thể thu hồi đơn giản** chỉ bằng gọi API. Trước khi xóa, cần chắc chắn đường dẫn thuộc phạm vi mà chương trình có quyền quản lý.

- **Không ghép tên đường dẫn tùy ý do người dùng cung cấp** rồi xóa ngay, ví dụ `base.resolve(userInput)`, vì `..`, đường dẫn tuyệt đối, symlink hoặc race có thể làm mục tiêu khác dự tính.
- `Path.normalize()` và `startsWith(root)` giúp kiểm tra phạm vi **theo cú pháp**, nhưng chưa đủ để chống symbolic link và thay đổi hệ thống tệp đồng thời.
- Giữ quyền truy cập tối thiểu và cơ chế ownership của thư mục riêng, nhất là với file tạm.
- Đối với thư mục nhiều người/tiến trình cùng ghi, cần cơ chế an toàn hơn như thao tác dựa trên directory handle/provider hỗ trợ, chứ không dựa duy nhất vào `Files.exists` rồi `Files.delete`.
- Đối với dữ liệu giá trị cao, xác định chính sách lưu trữ, backup, recycle bin hoặc xóa mềm (*soft delete*) theo nghiệp vụ thay vì để một lệnh xóa vĩnh viễn không thể đảo ngược.

### Có nên gọi `Files.exists` để "kiểm tra trước" không?

Có thể kiểm tra để **hiển thị thông tin cho người dùng**. Nhưng khi thực hiện hành động xóa thật, **phải xử lý kết quả/ngoại lệ của chính thao tác xóa**. `exists` không thể bảo đảm file vẫn còn ở thời điểm `delete` hoặc `deleteIfExists` chạy.

Một lưu ý với symbolic link: `Files.exists` mặc định đi theo link, vì vậy file đích không còn có thể dẫn tới kết luận sai rằng **entry link** không tồn tại. Lời gọi `deleteIfExists` trực tiếp thường đơn giản và đúng hơn khi ý định là xóa entry đang được trỏ tới.

## 12. Các lỗi học viên thường mắc

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`deleteIfExists` không bao giờ ném lỗi” | Chỉ bỏ qua sự vắng mặt, vẫn có lỗi xóa thật | Khai báo/xử lý `IOException` |
| “`deleteIfExists=false` nghĩa là không có quyền” | `false` báo không có entry để xóa | Phân biệt kết quả và ngoại lệ |
| “`delete` trả `boolean` như `File.delete`” | `Files.delete` trả `void` | Chọn API theo hợp đồng |
| “`Files.deleteIfExists` xóa cả cây” | Chỉ nhắm một entry, thư mục thường phải rỗng | Không dùng như lệnh recursive |
| “Trước khi xóa phải gọi `Files.exists`” | Có race giữa check/use | Gọi thao tác xóa trực tiếp và xử lý kết quả |
| “Nếu symbolic link hỏng, không thể xóa nó” | Link là entry riêng, có thể xóa link | Xóa `Path` tới link; không suy ra từ `Files.exists` mặc định |
| “Thất bại xóa đều là `NoSuchFileException`” | Có thể là quyền, file bị giữ, thư mục không rỗng | Xử lý ngoại lệ tương ứng và lỗi chung |
| “`Files.delete(path)` đổi tên file” | Nó xóa entry, không rename | `Files.move` nếu muốn di chuyển/đổi tên |
| “`Files.deleteIfExists` bảo đảm không có cạnh tranh” | Không phải giao dịch nguyên tử chống mọi thay đổi | Thiết kế ownership và đồng bộ |
| “Xóa tệp cha cũng xóa nội dung thư mục” | Thư mục có entry thường không xóa được | Xác định rõ nhu cầu, tránh đệ quy ngoài ý muốn |
| “File đang mở xóa được giống nhau mọi OS” | Provider/OS có quy tắc khác nhau | Đóng tài nguyên và xử lý lỗi thực |
| “Có thể bỏ qua lỗi cleanup” | Lỗi dọn có thể lấp hoặc che nguyên nhân chính | Quản lý ngoại lệ cleanup cẩn thận |

## 13. Câu hỏi tự kiểm tra

1. **`Files.delete(path)` trả về `true` hay `false`?** Không; kiểu trả về là **`void`**.
2. **`Files.delete(path)` với file không tồn tại thường gây gì?** **`NoSuchFileException`**.
3. **`Files.deleteIfExists(path)` với file không tồn tại trả gì?** **`false`**.
4. **`Files.deleteIfExists(path)` có trả `false` khi thư mục không rỗng không?** Không nên kỳ vọng; nó **có thể ném ngoại lệ I/O**, thường là `DirectoryNotEmptyException`.
5. **Dùng `deleteIfExists` trong `finally` có xóa được lỗi quyền không?** Không; lỗi quyền vẫn có thể ném ngoại lệ.
6. **Gọi `deleteIfExists` hai lần liên tiếp luôn trả `true` rồi `false`?** Chỉ trong điều kiện file có ở lần đầu và không có tác nhân khác tạo lại hoặc thay đường dẫn.
7. **Xóa symbolic link có xóa file đích không?** **Không**, nó xóa entry liên kết.
8. **Vì sao `if (Files.exists(p)) Files.delete(p);` không tránh được `NoSuchFileException`?** Vì file có thể biến mất giữa kiểm tra và xóa.
9. **`File.delete()` và `Files.deleteIfExists()` đều trả boolean thì có giống nhau?** Không; `File.delete` thường không phân biệt chi tiết các lỗi, còn `Files.deleteIfExists` báo các lỗi I/O khác bằng ngoại lệ.
10. **Muốn xóa toàn bộ folder chứa file có thể chỉ gọi `deleteIfExists(folder)` không?** **Không**, thư mục không rỗng thường khiến thao tác thất bại; phải dùng một quy trình xóa cây được kiểm soát khi thật sự cần.
11. **Khi thiếu file là trạng thái bình thường, API nào thể hiện rõ ý định hơn?** **`Files.deleteIfExists`**.
12. **Khi thiếu file cần được phát hiện là lỗi, API nào phù hợp hơn?** **`Files.delete`**.

**Ghi nhớ:** `Files.delete` coi **“không tồn tại” là lỗi** và trả `void`; `Files.deleteIfExists` coi **“không tồn tại” là trường hợp bình thường** và trả `false`. Cả hai đều có thể thất bại bởi các lỗi thật, không xóa đệ quy và cần dùng trên những đường dẫn mà ứng dụng thực sự được phép quản lý.