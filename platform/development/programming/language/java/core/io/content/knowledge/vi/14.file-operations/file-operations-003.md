# Sao chép tệp với REPLACE_EXISTING và COPY_ATTRIBUTES trong Java NIO

Khi cần sao chép tệp trong Java 17+, API thông dụng là `java.nio.file.Files.copy(Path source, Path target, CopyOption... options)`. Hai tùy chọn thường đi cùng nhau là:

- **`StandardCopyOption.REPLACE_EXISTING`**: nếu tệp đích đã tồn tại, cho phép thay thế tệp đích trong những điều kiện API hỗ trợ.
- **`StandardCopyOption.COPY_ATTRIBUTES`**: yêu cầu thử sao chép các thuộc tính của tệp nguồn sang tệp đích, tối thiểu gồm thời điểm sửa đổi cuối nếu cả hai file store hỗ trợ.

Ví dụ điển hình:

~~~java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);
~~~

Tuy nhiên, **cho phép thay thế không có nghĩa là sao chép nguyên tử**, và **yêu cầu sao chép thuộc tính không có nghĩa mọi metadata được bảo toàn tuyệt đối**. Cần hiểu riêng từng option, cách chúng kết hợp, các trường hợp ngoại lệ và rủi ro tệp đích bị ghi chưa hoàn chỉnh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích hợp đồng của `Files.copy(Path, Path, CopyOption...)`, kiểu trả về và các ngoại lệ quan trọng.
2. Phân biệt hành vi mặc định khi tệp đích đã có với `REPLACE_EXISTING`.
3. Phân biệt sao chép **nội dung byte** với sao chép **thuộc tính tệp**, và các giới hạn của `COPY_ATTRIBUTES`.
4. Biết điều gì xảy ra khi nguồn là symbolic link hoặc thư mục, khi đích là symbolic link, hoặc khi nguồn và đích trỏ đến cùng một tệp.
5. Hiểu lý do `Files.copy` không bảo đảm atomicity, rollback hoặc bảo vệ khỏi thay đổi đồng thời.
6. Xây dựng ví dụ Java 17+ chạy được, có thư mục tạm, cleanup, kiểm tra nội dung bằng `Files.mismatch` và quan sát metadata.
7. Chọn chiến lược tệp tạm và `Files.move` khi cần một quy trình công bố kết quả có kiểm soát.
8. Tránh các lỗi thường gặp về đường dẫn, quyền, file store, thuộc tính và độ an toàn dữ liệu.

## 2. Tổng quan cú pháp và ý nghĩa

Chữ ký của overload được học:

~~~java
public static Path copy(
        Path source, Path target, CopyOption... options
) throws IOException;
~~~

Trong đó:

- `source`: `Path` của nguồn cần sao chép.
- `target`: `Path` đích cần được tạo hoặc thay thế.
- `options`: các tùy chọn điều khiển hành vi, chẳng hạn `StandardCopyOption.REPLACE_EXISTING`, `StandardCopyOption.COPY_ATTRIBUTES` hoặc `LinkOption.NOFOLLOW_LINKS`.
- Giá trị trả về: chính `Path` đích.
- `IOException`: báo các lỗi trong quá trình sao chép; có thể nhận một lớp con cụ thể như `FileAlreadyExistsException`.

Phải phân biệt rõ overload này với:

~~~java
long bytes = Files.copy(inputStream, target, copyOptions);
long bytes = Files.copy(source, outputStream);
~~~

Hai overload còn lại có kiểu trả về `long` và bộ option/hợp đồng riêng. **Không thể mặc định `COPY_ATTRIBUTES` áp dụng cho việc copy từ một `InputStream` tùy ý** vì nguồn kiểu stream không mang một bộ file attributes theo `Path` để sao chép.

### Khi không truyền option

~~~java
Path copied = Files.copy(source, target);
~~~

Mặc định, khi `target` đã tồn tại (kể cả symbolic link) thì thao tác sẽ thất bại, **trừ trường hợp nguồn và đích được xác định là cùng một tệp**: khi đó phương thức có thể hoàn tất mà không thực hiện bản sao.

Nếu là hai tệp khác nhau và đích đã tồn tại, provider thường ném `FileAlreadyExistsException`; theo tài liệu Java, đây là *optional specific exception*: code sản xuất vẫn phải xử lý `IOException` tổng quát vì không phải mọi provider bắt buộc dùng cùng loại ngoại lệ chuyên biệt.

Mặc định cũng **không yêu cầu sao chép các thuộc tính file** ngoài nội dung và thông tin mà provider cần để tạo file đích. Muốn yêu cầu giữ thuộc tính, khai báo rõ `COPY_ATTRIBUTES`.

## 3. `REPLACE_EXISTING`: thay thế tệp đích, không phải nối thêm

~~~java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

Option này yêu cầu cho phép thay thế một entry tại đường dẫn đích nếu nó đã tồn tại. Nó **không** có ý nghĩa:

- Nối dữ liệu vào cuối file cũ (*append*).
- Chỉ ghi những byte khác nhau hoặc đồng bộ tăng dần.
- Tạo mọi thư mục cha chưa tồn tại.
- Tự sao lưu nội dung cũ hoặc tự khôi phục khi lỗi.
- Thực hiện một thao tác thay thế nguyên tử.
- Cho phép xóa một **thư mục đích không rỗng** để thay thế.

Theo hợp đồng `Files.copy`, `REPLACE_EXISTING` không thể thay thế một target là **thư mục không rỗng**. Hãy xử lý `DirectoryNotEmptyException` nếu provider dùng lỗi cụ thể này; nếu không vẫn phải xử lý `IOException`.

### So sánh

| Tình huống | `Files.copy(source, target)` | Có `REPLACE_EXISTING` |
| --- | --- | --- |
| Đích chưa tồn tại | Tạo bản sao mới nếu đủ điều kiện | Cũng tạo bản sao mới |
| Đích đã là file thường khác nguồn | Thường lỗi `FileAlreadyExistsException` | Cho phép thay thế file đích |
| Đích là symbolic link | Mặc định coi là đích đã tồn tại nên thường lỗi | Thay thế **chính link**, không phải file mà link trỏ đến |
| Đích là thư mục không rỗng | Không ghi đè | Không thể thay thế thư mục không rỗng |
| Nguồn và đích là cùng một tệp | Hoàn tất không copy thực tế theo hợp đồng | Cũng không cần copy khi được nhận diện là cùng tệp |

**Rủi ro thực tế:** nếu người gọi chỉ định nhầm `target`, option này có thể khiến dữ liệu quan trọng cũ bị mất. Dùng option khi yêu cầu nghiệp vụ thật sự là thay thế. Với yêu cầu “đừng ghi đè”, hãy **bỏ `REPLACE_EXISTING`** và xử lý xung đột.

`REPLACE_EXISTING` cũng **không phải** giải pháp chống TOCTOU (*time-of-check/time-of-use*): trạng thái đích có thể thay đổi giữa kiểm tra và copy, và tài liệu nêu việc kiểm tra tồn tại/cấp tạo file mới không nhất thiết là nguyên tử đối với hoạt động file system khác.

## 4. `COPY_ATTRIBUTES`: cố gắng sao chép metadata, không phải mọi thuộc tính

~~~java
Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES);
~~~

`COPY_ATTRIBUTES` yêu cầu hệ thống cố sao chép thuộc tính đi kèm tệp nguồn sang tệp đích. Theo tài liệu Java 17:

- **Những thuộc tính được sao chép chính xác phụ thuộc nền tảng và file system**.
- Tối thiểu, `last-modified-time` được sao chép **nếu cả file store nguồn và đích cùng hỗ trợ**.
- Việc chép timestamp có thể **mất độ chính xác** do độ phân giải thời gian của file store.
- Quyền truy cập, ACL, owner, nhóm, extended attributes hoặc các metadata khác **không được bảo đảm giống nhau** trên mọi hệ thống.
- Nếu đang sao chép **symbolic link** bằng `NOFOLLOW_LINKS`, việc sao chép thuộc tính cho chính link phụ thuộc triển khai; `COPY_ATTRIBUTES` có thể bị bỏ qua cho link.

Như vậy, không nên khẳng định:

> “`COPY_ATTRIBUTES` bảo toàn 100% permission, owner, creation time và mọi ACL.”

Điều đó vượt quá hợp đồng Java. Nếu bài toán thực sự phải giữ một thuộc tính riêng, hãy dùng API thuộc tính tương ứng để **đọc, so sánh và xử lý sai khác** trong phạm vi provider hỗ trợ, ví dụ:

~~~java
FileTime sourceTime = Files.getLastModifiedTime(source);
FileTime targetTime = Files.getLastModifiedTime(target);

System.out.println("sameTimestamp=" + sourceTime.equals(targetTime));
~~~

Đây là mảnh mã cần import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.attribute.FileTime`. Giá trị so sánh có thể khác khi đích có độ phân giải timestamp thấp hơn. `false` không tự khẳng định dữ liệu byte bị copy sai; nó cho thấy timestamp chưa khớp chính xác theo phép so sánh này.

### REPLACE_EXISTING kết hợp COPY_ATTRIBUTES

~~~java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);
~~~

Nghĩa là:

1. Cho phép copy vào đường dẫn đích ngay cả khi đích là file cũ cần thay thế.
2. Đồng thời yêu cầu cố sao chép thuộc tính nguồn sang kết quả mới.

**Không có thứ tự “thay thế xong chắc chắn mọi thuộc tính đã chép” nếu phát sinh lỗi.** Tài liệu nêu nếu gặp `IOException`, tệp đích có thể chỉ được copy một phần hoặc một số thuộc tính chưa được sao chép.

## 5. Ví dụ Java 17+ chạy được: mặc định thất bại, sau đó thay thế thành công

Tạo file **`CopyOptionsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class CopyOptionsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-options-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "NEW", StandardCharsets.UTF_8);
            Files.writeString(target, "OLD", StandardCharsets.UTF_8);

            try {
                Files.copy(source, target);
                System.out.println("unexpected success");
            } catch (FileAlreadyExistsException exception) {
                System.out.println("withoutReplace=FileAlreadyExistsException");
            }

            Path returned = Files.copy(
                    source,
                    target,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES
            );

            System.out.println("returnedTarget=" + returned.equals(target));
            System.out.println("targetText=" +
                    Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("sourceText=" +
                    Files.readString(source, StandardCharsets.UTF_8));
            System.out.println("sameBytes=" +
                    (Files.mismatch(source, target) == -1L));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CopyOptionsDemo.java
java CopyOptionsDemo
~~~

**Stdout trên default file system thông thường, khi không có tiến trình khác tác động lên thư mục tạm:**

~~~text
withoutReplace=FileAlreadyExistsException
returnedTarget=true
targetText=NEW
sourceText=NEW
sameBytes=true
~~~

Giải thích:

- Cả `source.txt` và `target.txt` đều tồn tại trước khi copy.
- Lần gọi **không option** bị từ chối vì target đã tồn tại.
- Lần gọi có `REPLACE_EXISTING` sao chép nội dung của nguồn sang target.
- Thêm `COPY_ATTRIBUTES` yêu cầu sao chép metadata trong giới hạn được hỗ trợ. Ví dụ không in timestamp vì kết quả phụ thuộc file system, không nên khẳng định một chuỗi thời gian cố định.
- `Files.copy` trả `Path` đích, nên `returned.equals(target)` là `true`.
- `Files.mismatch` (Java 12+) trả `-1L` khi hai file có nội dung byte giống nhau. Đó là một phép so sánh nội dung, **không** xác nhận mọi thuộc tính đều giống.
- Việc copy không xóa nguồn; `sourceText=NEW` xác minh file nguồn còn nguyên trong ca demo.
- `finally` dọn các file và thư mục tạm để không phụ thuộc vào đường dẫn cố định của máy.

### Vì sao không cần `BufferedInputStream`?

`Files.copy(Path, Path, CopyOption...)` đã giao công việc sao chép cho file system provider/JDK. Không cần tự viết vòng `read/write` chỉ để có thể chỉ định `REPLACE_EXISTING` và `COPY_ATTRIBUTES`. Khi muốn thay đổi nội dung lúc copy, tính checksum theo luồng hoặc áp một định dạng đặc biệt, khi đó mới cân nhắc streams/channels với mô hình metadata và xử lý lỗi riêng.

## 6. Quan sát thuộc tính lastModifiedTime

Để kiểm chứng ý nghĩa `COPY_ATTRIBUTES`, có thể gán thời điểm sửa cuối cho nguồn trước khi sao chép:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

// Mảnh mã: source và target đã được khai báo và có cha thích hợp.
FileTime expectedTime = FileTime.from(
        Instant.parse("2020-02-03T04:05:06Z"));

Files.setLastModifiedTime(source, expectedTime);

Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES
);

FileTime sourceTime = Files.getLastModifiedTime(source);
FileTime targetTime = Files.getLastModifiedTime(target);

System.out.println("sourceTime=" + sourceTime);
System.out.println("targetTime=" + targetTime);
~~~

Đây là **mảnh mã minh họa**, cần đặt trong phương thức có xử lý `IOException`. Nó không có stdout bất biến theo mọi file system: provider có thể lưu thời gian theo độ phân giải khác, nên giá trị được đọc lại có thể bị làm tròn.

Phép kiểm tra đúng là đánh giá **theo yêu cầu ứng dụng**: ví dụ file store hỗ trợ độ chính xác giây thì so sánh đến giây, hoặc yêu cầu exact match trên một môi trường đã xác định. Nếu timestamp quan trọng nhưng phía đích không hỗ trợ cùng độ chính xác, đó là một giới hạn nền tảng cần được ghi nhận thay vì im lặng tuyên bố “đã copy mọi thuộc tính”.

Cũng cần phân biệt:

- `size`: kích thước nội dung byte; nếu nội dung copy thành công thì dung lượng file thường phản ánh nội dung mới, **không phải** thứ cần bật `COPY_ATTRIBUTES` mới có.
- `lastModifiedTime`: thuộc tính thời gian được yêu cầu sao chép tối thiểu khi cả hai file store hỗ trợ.
- `lastAccessTime`, `creationTime`, `owner`, `permissions`, `ACL` và extended metadata: không được suy ra chắc chắn đã giống chỉ từ một lần gọi `COPY_ATTRIBUTES`.

## 7. Nếu không thêm `COPY_ATTRIBUTES` thì sao?

~~~java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

Dữ liệu được copy theo hợp đồng của `Files.copy`, nhưng không có yêu cầu **bảo toàn metadata nguồn**. Target có thể nhận các timestamp hoặc thuộc tính mới theo quy tắc tạo tệp của hệ thống.

Ví dụ:

- Một hệ thống nhận file export cần nội dung mới, không cần giữ thời gian sửa đổi của file nguồn: có thể chỉ dùng `REPLACE_EXISTING`.
- Một quy trình sao lưu/copy dữ liệu muốn giữ `lastModifiedTime` để người dùng đối chiếu: có thể thêm `COPY_ATTRIBUTES`, sau đó xác minh các thuộc tính thực sự quan trọng.

**Không nhầm** yêu cầu “sao chép file” với yêu cầu “sao chép file kèm mọi security attributes”. Đây là hai mức hợp đồng khác nhau; mức sau phải viết rõ những thuộc tính nào phải giữ và hành vi khi hệ thống không hỗ trợ.

## 8. Tình huống nguồn hoặc đích là symbolic link

Symbolic link (*liên kết tượng trưng*) có hai khía cạnh: chính **link entry** và **đích mà nó chỉ tới**.

### Khi nguồn là symbolic link

Theo mặc định, `Files.copy(sourceLink, target)` **theo symbolic link nguồn** và sao chép **file mà link trỏ đến**, nếu có thể giải quyết link.

Nếu muốn sao chép **chính symbolic link**, dùng `LinkOption.NOFOLLOW_LINKS`:

~~~java
Files.copy(
        sourceLink,
        targetLink,
        LinkOption.NOFOLLOW_LINKS
);
~~~

Đây là mảnh mã, cần import `Files`, `LinkOption` và dùng `Path` phù hợp. Nó yêu cầu provider hỗ trợ thao tác symbolic link; có thể không chạy trên mọi hệ điều hành, file system hoặc cấu hình quyền.

| Nguồn | Option | Đối tượng được yêu cầu copy |
| --- | --- | --- |
| Symlink trỏ tới file | Mặc định | File mà link trỏ đến |
| Symlink | `NOFOLLOW_LINKS` | Chính symbolic link |
| Symlink + `COPY_ATTRIBUTES` + `NOFOLLOW_LINKS` | Hai option | Chính link; việc chép **thuộc tính của link** có thể bị bỏ qua tùy triển khai |

### Khi đích là symbolic link

Với `REPLACE_EXISTING`, nếu `target` đang là symbolic link thì **chính symbolic link đó được thay thế**, chứ không phải file mà link trỏ tới. Đây là điểm thường gây nhầm:

~~~text
targetLink --> important.txt

Files.copy(source, targetLink, REPLACE_EXISTING)

Kết quả được yêu cầu:
- entry targetLink bị thay thế bằng bản sao
- không phải ghi trực tiếp nội dung vào important.txt qua link
~~~

Tuy vậy, đừng xem điều này là giải pháp tổng quát chống mọi symlink race: cây thư mục và các thành phần cha vẫn có thể thay đổi do tác nhân khác kiểm soát. Với đường dẫn lấy từ dữ liệu không tin cậy, phải đánh giá quyền truy cập, đường dẫn cha, policy và tính nguyên tử của thao tác thực.

## 9. Copy thư mục là sao chép nông (*shallow*), không tự đệ quy

Một hiểu nhầm phổ biến là `Files.copy(sourceDirectory, targetDirectory)` sẽ tự copy toàn bộ cây file. Theo Java 17:

> Khi nguồn là thư mục, API này tạo một **thư mục rỗng** ở đích; không tự copy các mục bên trong.

Ví dụ chạy được: tạo một thư mục có file con rồi copy thư mục đó.

Tạo **`DirectoryCopyDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryCopyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-copy-");
        Path source = Files.createDirectory(root.resolve("source"));
        Path child = Files.writeString(
                source.resolve("inside.txt"), "hello",
                StandardCharsets.UTF_8
        );
        Path target = root.resolve("target");

        try {
            Files.copy(source, target);

            System.out.println("sourceChildExists=" +
                    Files.exists(child));
            System.out.println("targetIsDirectory=" +
                    Files.isDirectory(target));
            System.out.println("targetChildExists=" +
                    Files.exists(target.resolve("inside.txt")));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(child);
            Files.deleteIfExists(source);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DirectoryCopyDemo.java
java DirectoryCopyDemo
~~~

Stdout trong môi trường thông thường:

~~~text
sourceChildExists=true
targetIsDirectory=true
targetChildExists=false
~~~

Muốn copy **toàn bộ cây**, cần duyệt đệ quy, chẳng hạn `Files.walkFileTree` với `FileVisitor` và thao tác riêng cho mỗi thư mục/file. Khi làm như vậy, phải xác định rõ có theo symbolic links hay không, thứ tự tạo thư mục, giới hạn độ sâu, cách xử lý lỗi và metadata nào cần khôi phục sau khi copy con. Thêm `COPY_ATTRIBUTES` vào một lần copy thư mục **không biến nó thành copy đệ quy**.

## 10. `Files.copy` không phải thao tác nguyên tử

Tài liệu Java nêu rõ việc sao chép một file **không phải atomic operation**. Nếu `IOException` xảy ra giữa chừng:

- Đích có thể đã bị thay thế và chỉ chứa **một phần dữ liệu**.
- Một số attributes có thể đã copy, những attributes khác chưa.
- Nội dung cũ của đích có thể không còn; không có rollback tự động.
- Người đọc khác có thể quan sát trạng thái đích trong một số giai đoạn, tùy provider và cách triển khai.
- Lỗi khi copy metadata vẫn có thể làm hoạt động báo thất bại, dù nội dung đã được chuyển một phần hoặc toàn bộ.

Vì vậy đoạn sau **không nên** hiểu là một giao dịch an toàn tuyệt đối:

~~~java
Files.copy(source, target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
System.out.println("published");
~~~

Dòng `published` chỉ chứng tỏ lời gọi `copy` đã hoàn thành mà không ném exception. Nó không khẳng định checksum/metadata theo chính sách nghiệp vụ đã được xác minh, file đã được đồng bộ bền vững xuống đĩa hoặc phía đọc từ xa đã nhìn thấy nội dung.

Nếu lỗi xảy ra, code phải đánh giá trạng thái đích, chính sách cleanup và khả năng thử lại. **Không xóa target một cách mù quáng** nếu target có thể là dữ liệu dùng chung hoặc đã được một tác vụ khác thay thế trong khi đang xử lý.

## 11. Mô hình an toàn hơn khi cần công bố file

Một cách thường dùng là:

1. Tạo một **file tạm trong thư mục đích** (thường để thuận lợi cho việc move trong cùng file store).
2. Copy nguồn sang file tạm, với `COPY_ATTRIBUTES` nếu cần.
3. Nếu yêu cầu, kiểm tra byte bằng `Files.mismatch`, kích thước, checksum hay metadata.
4. Di chuyển file tạm sang tên chính thức; có thể **yêu cầu** `ATOMIC_MOVE` nếu provider hỗ trợ.
5. Xóa file tạm trong `finally` khi chưa được chuyển đi.

Ví dụ lớp tiện ích Java 17, **`StagedCopy.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class StagedCopy {
    private StagedCopy() {}

    public static void publish(Path source, Path target)
            throws IOException {
        Path parent = target.toAbsolutePath().getParent();
        if (parent == null) {
            throw new IllegalArgumentException("Target needs a parent");
        }

        // parent phải tồn tại và caller đã xác định được phép ghi.
        Path staged = Files.createTempFile(
                parent, ".staged-copy-", ".part");

        try {
            // createTempFile đã tạo staged; cần REPLACE_EXISTING
            // để copy ghi vào tên tạm đó.
            Files.copy(
                    source,
                    staged,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES
            );

            if (Files.mismatch(source, staged) != -1L) {
                throw new IOException("Content mismatch after copy");
            }

            Files.move(
                    staged,
                    target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING
            );
        } finally {
            Files.deleteIfExists(staged);
        }
    }
}
~~~

Đây là **lớp có thể biên dịch nhưng không có `main`**. Caller truyền nguồn và đích phù hợp; phương thức có thể ném `IOException` nếu không thể hoàn tất. Đoạn mã cho thấy một **chiến lược**, không phải lời hứa hỗ trợ đồng nhất trên mọi hệ thống.

Các giới hạn cần hiểu kỹ:

- `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)`: khi đã chọn `ATOMIC_MOVE`, **các options còn lại bị bỏ qua theo hợp đồng** của `Files.move`; nếu target đã tồn tại, việc **thay thế hay báo lỗi** phụ thuộc implementation. Không giả định luôn là “atomic replace existing” trên mọi provider.
- Nếu provider không hỗ trợ atomic move, `AtomicMoveNotSupportedException` có thể xảy ra. Trong ví dụ, phương thức **không âm thầm hạ cấp** sang move không nguyên tử.
- Bản thân quá trình **copy vào staged** vẫn không nguyên tử, nhưng chưa công bố bằng tên target cuối cho tới bước move nếu mọi thứ thành công.
- `Files.mismatch` xác nhận nội dung byte khi đọc ở hai thời điểm; nguồn vẫn có thể bị sửa **đồng thời** trong/giữa copy và verify. Nếu yêu cầu snapshot nhất quán, cần khóa/cơ chế version/nguồn bất biến hoặc biện pháp khác của hệ thống.
- `ATOMIC_MOVE` không đồng nghĩa mọi byte đã được `fsync`/ghi bền vững vào thiết bị khi mất điện. Nếu yêu cầu durability, phải thiết kế cơ chế đồng bộ thích hợp, trong phạm vi nền tảng hỗ trợ.
- Nếu move thành công thì `staged` không còn ở tên tạm, nên `deleteIfExists(staged)` không xóa target. Nếu move thất bại, cleanup sẽ cố xóa tệp tạm. Trạng thái ngoài ý muốn vẫn có thể cần giám sát thủ công.
- Với thư mục/đích không tin cậy, đường dẫn cha và symlink cần cơ chế bảo vệ bổ sung.

Nếu ứng dụng thực sự đòi **thay thế đích hiện hữu một cách nguyên tử**, phải xác nhận file system/provider của môi trường triển khai hỗ trợ đúng hành vi mong muốn. Không nên tự tin chỉ nhờ thấy cả hai option `ATOMIC_MOVE` và `REPLACE_EXISTING` trong lời gọi.

## 12. Exceptions: biết loại lỗi nào có thể xảy ra

`Files.copy(Path, Path, CopyOption...)` khai báo `throws IOException` và có thể phát sinh những lỗi như:

| Trường hợp | Ngoại lệ/tín hiệu điển hình |
| --- | --- |
| Đích đã tồn tại, không có `REPLACE_EXISTING` | `FileAlreadyExistsException` hoặc `IOException` |
| Đích là thư mục không rỗng không thể thay thế | `DirectoryNotEmptyException` hoặc `IOException` |
| Nguồn hoặc một thành phần thiết yếu không tồn tại | `NoSuchFileException` hoặc `IOException` |
| Không đủ quyền truy cập | `AccessDeniedException` hoặc `IOException` |
| Lỗi đọc/ghi thiết bị, file store, network filesystem | `IOException` |
| Option không được provider hỗ trợ | `UnsupportedOperationException` |
| Một số tham số bị `null` | `NullPointerException` theo hợp đồng API |

Những lớp con I/O chuyên biệt có thể là **optional specific exceptions**: không nên bỏ xử lý `IOException` tổng quát.

Mẫu xử lý tối thiểu:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class CopyWithErrors {
    private CopyWithErrors() {}

    public static Path copy(Path source, Path target)
            throws IOException {
        try {
            return Files.copy(
                    source, target,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES
            );
        } catch (AccessDeniedException exception) {
            throw new IOException(
                    "Access denied while copying to " + target,
                    exception
            );
        } catch (FileAlreadyExistsException exception) {
            // Có thể gặp ở môi trường/provider đặc thù hoặc
            // khi thao tác cạnh tranh làm trạng thái thay đổi.
            throw new IOException(
                    "Target collision while copying to " + target,
                    exception
            );
        }
    }
}
~~~

Lớp ví dụ không có `main`. Nó giữ `cause` để bên gọi có thông tin chẩn đoán. Nếu không có yêu cầu phân loại nghiệp vụ riêng, thường **lan truyền `IOException` gốc** đơn giản hơn so với bọc lại cùng một thông điệp.

Tránh log đường dẫn nhạy cảm một cách tùy tiện. Không có nghĩa mọi thất bại đều nên retry: `AccessDeniedException`, directory-not-empty hoặc đường dẫn bị cấu hình sai thường không giải quyết bằng retry liên tục.

## 13. Các yếu tố làm kết quả phụ thuộc môi trường

### File store, timestamp và permissions

Sao chép trong cùng filesystem thường có điều kiện thuận lợi hơn việc copy giữa hai provider/file store khác nhau, nhưng không thể suy ra điều này bảo đảm mọi thuộc tính giống nhau. Độ chính xác timestamp, quyền chủ sở hữu, ACL, extended attributes và implementation copy đều có thể khác giữa Windows, Linux, macOS và file system mạng.

Nếu chương trình yêu cầu một thuộc tính thiết yếu như permission POSIX hoặc ACL, hãy kiểm tra capability và dùng API `Files.readAttributes`/attribute views tương ứng để xác minh rõ, không dựa vào `COPY_ATTRIBUTES` như giấy cam kết tất cả metadata.

### Thư mục cha của target

`Files.copy` không có hợp đồng tự tạo toàn bộ directory tree. Nếu `target` là `output/reports/data.txt` mà `output/reports` chưa tồn tại, copy có thể thất bại.

Khi ứng dụng được phép tạo parent directories:

~~~java
Path parent = target.toAbsolutePath().getParent();
if (parent != null) {
    Files.createDirectories(parent);
}
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
~~~

Đây là **mảnh mã** với `source/target` kiểu `Path` và xử lý `IOException`. Tạo các thư mục cha là **thao tác riêng**, có thể thất bại và có thể tạo một phần cây trước khi lỗi.

### Nguồn và đích cùng một tệp

Theo `Files.copy`, khi nguồn và đích được xem là **cùng một file**, phương thức hoàn tất mà không tạo bản sao. Điều này không chỉ là so sánh chuỗi path: hard link hoặc hai đường dẫn khác biểu diễn cùng một file có thể cần file system để nhận diện. Khi thật sự muốn biết hai path có trỏ tới cùng file ở thời điểm hiện tại, xem `Files.isSameFile`, nhưng đây cũng không phải khóa chặn thay đổi đồng thời.

### Copy giữa nhiều providers

`Files.copy` có thể làm việc với hai `Path` thuộc providers khác nhau trong phạm vi hợp đồng Java. Khi đó khả năng hỗ trợ metadata, symlink, quyền và hiệu năng khác nhau. Không giả định mọi bản sao giữa các provider đều có thể thay thế, giữ attributes và chạy đúng tốc độ như copy nội bộ trên ổ local.

## 14. Copy file có giữ nguyên nội dung văn bản không?

`Files.copy(Path, Path, ...)` sao chép file theo cơ chế file, không gọi decoder UTF-8 rồi encoder lại theo kiểu bạn tự làm với `BufferedReader`/`BufferedWriter`. Do đó nó thích hợp cho:

- Ảnh, PDF, ZIP và các file nhị phân.
- File text mà không cần thay đổi encoding hoặc line endings.
- Dữ liệu bất kỳ cần copy nguyên nội dung byte khi thao tác thành công.

Nếu bạn cần chuyển UTF-8 sang UTF-16, thay đổi newline hoặc chỉnh nội dung, phải có bước xử lý văn bản khác; `COPY_ATTRIBUTES` không thực hiện chuyển đổi charset và `REPLACE_EXISTING` cũng không làm việc đó.

Sau copy, có thể so sánh byte bằng:

~~~java
long difference = Files.mismatch(source, target);
boolean identical = difference == -1L;
~~~

`Files.mismatch` không phải checksum mật mã; nó so sánh nội dung mà API đọc được và có thể ném `IOException`. Nó cũng không so sánh permissions, ACL hoặc timestamp.

## 15. Các lỗi phổ biến

**Lỗi 1 — Quên `REPLACE_EXISTING` rồi nghĩ copy sẽ ghi đè mặc định.**  
Mặc định target tồn tại khiến copy bị từ chối (ngoại trừ trường hợp source/target là cùng file). Hãy chọn rõ chính sách overwrite.

**Lỗi 2 — Dùng `REPLACE_EXISTING` khi nghiệp vụ thực ra cấm ghi đè.**  
Điều này có thể làm mất file đích cũ. Nếu cần “create only”, đừng truyền option và xử lý xung đột theo hợp đồng.

**Lỗi 3 — Tưởng `COPY_ATTRIBUTES` bảo toàn tất cả metadata giống hệt.**  
Không đúng. Danh sách attributes và độ chính xác phụ thuộc hệ thống; tối thiểu last-modified-time nếu hai store hỗ trợ. Kiểm tra thêm những thuộc tính thật sự cần thiết.

**Lỗi 4 — Nghĩ `Files.copy` có rollback và atomicity.**  
Không. Khi lỗi I/O, target có thể chưa hoàn chỉnh hoặc bị thay thế một phần. Với dữ liệu quan trọng, cân nhắc staging file và publish phù hợp.

**Lỗi 5 — Copy thư mục rồi mong có cả cây con.**  
`Files.copy` trên directory tạo directory đích rỗng; muốn đệ quy phải duyệt cây file riêng.

**Lỗi 6 — Nhầm hành vi symbolic link.**  
Nguồn symlink mặc định theo link; `NOFOLLOW_LINKS` copy chính link. Target symlink với `REPLACE_EXISTING` bị thay thế **link entry**, không ghi qua tới file mà link trỏ đến.

**Lỗi 7 — Dùng `COPY_ATTRIBUTES` cho overload copy từ `InputStream`.**  
Đó là overload khác; nguồn stream không có attribute set kiểu `Path` tương ứng. Hãy đọc hợp đồng từng overload.

**Lỗi 8 — Cho rằng REPLACE_EXISTING xóa được mọi loại đích.**  
Không thể thay thế một thư mục đích không rỗng bằng thao tác copy như mong muốn. Ngoài ra, quyền, file store và concurrency có thể gây lỗi.

**Lỗi 9 — Chỉ kiểm tra `Files.exists(target)` trước copy.**  
Trạng thái có thể thay đổi, và `exists==false` không luôn chứng minh file vắng mặt. Hãy để chính lệnh `copy` thực hiện rồi xử lý lỗi.

**Lỗi 10 — Đọc kết quả từ một lần test local rồi suy rộng mọi OS/provider.**  
Timestamp precision, quyền, xử lý symlink, ngoại lệ chi tiết và khả năng atomic move khác nhau. Test trên môi trường triển khai quan trọng, đặc biệt nếu nghiệp vụ yêu cầu metadata.

## 16. Quy trình chọn tùy chọn cho tình huống thực tế

| Nhu cầu | Cách dùng | Điều cần kiểm tra |
| --- | --- | --- |
| Chỉ copy nếu đích chưa có | `Files.copy(source, target)` | Xử lý đích đã tồn tại và I/O lỗi |
| Cho phép thay thế đích | `Files.copy(source, target, REPLACE_EXISTING)` | Có thực sự cho phép mất nội dung đích cũ? |
| Thay thế và giữ một số metadata nguồn | `Files.copy(source, target, REPLACE_EXISTING, COPY_ATTRIBUTES)` | Kiểm tra những metadata bắt buộc và giới hạn provider |
| Sao chép chính symbolic link | Thêm `LinkOption.NOFOLLOW_LINKS` | Provider hỗ trợ symlink và attribute của link không được bảo đảm |
| Copy cả cây thư mục | `Files.walkFileTree` + copy từng mục | Thứ tự, error recovery, symlink, độ sâu, attributes |
| Công bố file với khả năng thay thế nguyên tử | Copy sang staging rồi yêu cầu `ATOMIC_MOVE` | Không mọi provider hỗ trợ và hành vi khi đích tồn tại phụ thuộc implementation |
| Chỉ cần copy byte ra một stream | `Files.copy(source, outputStream)` | Đây là overload khác, không có `COPY_ATTRIBUTES` kiểu Path→Path |
| Sao chép từ một stream vào file | `Files.copy(inputStream, target, options)` | Option hỗ trợ hạn chế, không có metadata nguồn để copy |
| Kiểm tra nội dung giống nhau | `Files.mismatch(source, target) == -1L` | Không kiểm tra metadata, race hoặc durable persistence |

## 17. Checklist khi review code sản xuất

- [ ] Nguồn là **file thường**, thư mục hay symbolic link; chọn hành vi theo link phù hợp?
- [ ] Nếu target tồn tại, chính sách có cho phép **thay thế** không?
- [ ] Nếu cần metadata, đã thêm `COPY_ATTRIBUTES` và xác định **thuộc tính nào** bắt buộc?
- [ ] Có hiểu timestamp có thể mất độ chính xác và owner/ACL không tự đảm bảo giống?
- [ ] Đã xác định thư mục cha target tồn tại, có quyền và không bị can thiệp ngoài ý muốn?
- [ ] Có xử lý `IOException` và các trường hợp provider-specific mà không giả định một subclass luôn xuất hiện?
- [ ] Có chính sách khi bản sao thất bại để tránh công bố file chưa hoàn chỉnh?
- [ ] Có kiểm tra nguồn/đích cùng file, symlink và race nếu đường dẫn đến từ bên ngoài?
- [ ] Có tránh copy nhầm một directory và tưởng đã copy toàn bộ nội dung bên trong?
- [ ] Nếu cần atomic publish, đã xem xét `ATOMIC_MOVE`, giới hạn replace existing và không hạ cấp im lặng?
- [ ] Nếu cần bảo đảm content bytes, có xác minh bằng `Files.mismatch`/hash theo yêu cầu?
- [ ] Nếu yêu cầu file thực sự durable hoặc remote ACK, có cơ chế chuyên biệt bên ngoài `Files.copy`?
- [ ] Unit test có dùng thư mục tạm, cleanup và không phụ thuộc đường dẫn cố định?
- [ ] Không log dữ liệu/đường dẫn riêng tư vào kênh công khai khi xảy ra lỗi?

## 18. Câu hỏi tự kiểm tra

**1.** `Files.copy(source, target)` khi target đã tồn tại sẽ làm gì?  
**Đáp án:** Mặc định lỗi (trừ khi source và target là cùng file); thường có thể thấy `FileAlreadyExistsException`.

**2.** `REPLACE_EXISTING` có tự làm thao tác copy nguyên tử không?  
**Đáp án:** Không. `Files.copy` không phải atomic operation theo hợp đồng.

**3.** `COPY_ATTRIBUTES` có bảo đảm quyền POSIX/ACL/owner đều y hệt không?  
**Đáp án:** Không. Thuộc tính thực sự được copy phụ thuộc provider và file store; chỉ bảo đảm tối thiểu việc copy last-modified-time khi cả hai hỗ trợ, với khả năng mất độ chính xác.

**4.** Target là symbolic link, thêm `REPLACE_EXISTING` có nghĩa ghi đè file mà link trỏ tới không?  
**Đáp án:** Không. Nó thay thế **chính symbolic link tại đường dẫn đích**.

**5.** Source là symbolic link, không có `NOFOLLOW_LINKS` thì copy cái gì?  
**Đáp án:** Mặc định copy mục mà symlink trỏ đến; thêm `NOFOLLOW_LINKS` để copy chính link nếu provider hỗ trợ.

**6.** `Files.copy(sourceDir, targetDir, COPY_ATTRIBUTES)` có copy hết các file con không?  
**Đáp án:** Không. Một lần copy directory chỉ tạo thư mục đích rỗng; cần thuật toán duyệt cây riêng.

**7.** Nếu copy thất bại giữa chừng, có chắc target vẫn giữ nguyên byte cũ không?  
**Đáp án:** Không. Target có thể bị thay thế hoặc chưa hoàn chỉnh; phải thiết kế xử lý lỗi và công bố dữ liệu phù hợp.

**8.** `Files.mismatch(source, target) == -1L` chứng minh điều gì?  
**Đáp án:** Nội dung byte được so sánh là giống nhau theo thao tác đó; không khẳng định mọi metadata, file identity hay khả năng lưu bền vững.

**9.** Muốn buộc publish nguyên tử và provider không hỗ trợ `ATOMIC_MOVE` thì sao?  
**Đáp án:** Xử lý `AtomicMoveNotSupportedException`, báo không đáp ứng yêu cầu hoặc chọn một giải pháp đã được đánh giá riêng; không tự coi move thường là tương đương.

**Ghi nhớ:** `REPLACE_EXISTING` quyết định **có cho phép thay thế entry đích đã tồn tại hay không**. `COPY_ATTRIBUTES` yêu cầu **cố sao chép metadata trong khả năng file system hỗ trợ**. Kết hợp cả hai vẫn **không** tạo ra giao dịch nguyên tử, sao lưu tự động hay cam kết metadata giống tuyệt đối. Hãy chọn option theo hợp đồng nghiệp vụ, kiểm tra lỗi và dùng staging/verification khi dữ liệu quan trọng.

## Tài liệu API chính thức (Java SE 17)

- [`Files.copy(Path, Path, CopyOption...)` và ghi chú về atomicity, thuộc tính, symlink](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#copy(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...))
- [`StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [`LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
- [`FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html)
- [`Files.mismatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path))