# BasicFileAttributes và BasicFileAttributeView trong Java NIO

Trong Java NIO.2, **`java.nio.file.attribute.BasicFileAttributes`** và **`java.nio.file.attribute.BasicFileAttributeView`** đều liên quan tới metadata của một file hoặc thư mục, nhưng **không có cùng vai trò**:

- **`BasicFileAttributes`** là một **giao diện dữ liệu chỉ đọc**: chứa các giá trị đã lấy về, như loại mục, kích thước, timestamp và khóa nhận diện file nếu có.
- **`BasicFileAttributeView`** là một **giao diện để truy cập nhóm thuộc tính cơ bản của một đường dẫn**: cho phép gọi `readAttributes()` để đọc bộ thuộc tính mới và `setTimes(...)` để yêu cầu thay đổi một số timestamp.

Đọc thuộc tính không đồng nghĩa mở nội dung file. Cập nhật timestamp không phải cập nhật nội dung byte. Ngoài ra, metadata của hệ thống tập tin có thể thay đổi ngay sau khi được đọc, phụ thuộc quyền, loại file, symbolic link và khả năng của file system provider.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Kể tên và sử dụng đúng các phương thức của `BasicFileAttributes`: `size`, `creationTime`, `lastModifiedTime`, `lastAccessTime`, `isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`, `fileKey`.
2. Đọc metadata theo kiểu an toàn bằng `Files.readAttributes(path, BasicFileAttributes.class)`.
3. Lấy một `BasicFileAttributeView` từ `Files.getFileAttributeView(...)` và sử dụng `view.readAttributes()` hoặc `view.setTimes(...)`.
4. Hiểu các tham số `null` của `setTimes`, độ chính xác timestamp, lỗi I/O và những hành vi phụ thuộc provider.
5. Phân biệt snapshot metadata với file thực, không suy ra việc đọc thuộc tính là một thao tác khóa/snapshot nguyên tử của toàn hệ thống.
6. Phân biệt chế độ theo symbolic link mặc định với `LinkOption.NOFOLLOW_LINKS`.
7. Nhận biết khi cần các view chuyên biệt như `PosixFileAttributeView` hoặc `DosFileAttributeView` thay vì cố dùng basic view để đổi quyền.
8. Viết chương trình Java 17+ có thể biên dịch/chạy, kiểm tra metadata trên file tạm và xử lý trường hợp file chưa tồn tại.

## 2. Hai abstraction: bộ giá trị và cửa sổ thao tác

Hình dung quan hệ:

~~~text
Path
  |
  +-- Files.readAttributes(path, BasicFileAttributes.class)
  |          |
  |          v
  |    BasicFileAttributes
  |      size, timestamps, type, fileKey...
  |      (dữ liệu vừa đọc, không có setter)
  |
  +-- Files.getFileAttributeView(
         path, BasicFileAttributeView.class
      )
             |
             v
       BasicFileAttributeView
         + readAttributes()
         |      |
         |      v
         |  BasicFileAttributes mới
         |
         + setTimes(modified, accessed, created)
                |
                v
          Yêu cầu cập nhật file system
~~~

`BasicFileAttributes` trả về kết quả quan sát ở **một lần đọc**. Nếu file được ghi thêm một phút sau, object thuộc tính bạn đang giữ không tự làm mới `size()` hoặc `lastModifiedTime()`; cần yêu cầu đọc lại.

`BasicFileAttributeView` đại diện cho API của **một nhóm thuộc tính** gắn với `Path`. View không phải file handle khóa vĩnh viễn một mục. Bạn có thể lấy view trước, rồi khi gọi `readAttributes`, đường dẫn đã thay đổi hoặc không còn tồn tại và thao tác có thể lỗi. Cần phân biệt **lấy được view** với **đọc được thuộc tính ở thời điểm sử dụng**.

Các kiểu chính:

~~~java
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.BasicFileAttributeView;

Path path = Path.of("data.txt");

BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

BasicFileAttributeView view =
        Files.getFileAttributeView(
                path, BasicFileAttributeView.class);

BasicFileAttributes refreshed = view.readAttributes();
~~~

Đây là **mảnh mã**, cần đặt trong phương thức khai báo hoặc xử lý `IOException`, và `data.txt` phải tồn tại/truy cập được để các lệnh đọc thành công. `getFileAttributeView` có thể trả `null` nếu provider không hỗ trợ kiểu view yêu cầu; khi viết API tổng quát, nên kiểm tra trước khi sử dụng.

## 3. `BasicFileAttributes` cung cấp những gì?

Đây là interface trong gói `java.nio.file.attribute`. Nó khai báo các phương thức sau:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `lastModifiedTime()` | `FileTime` | Thời điểm sửa đổi cuối được file system báo cáo |
| `lastAccessTime()` | `FileTime` | Thời điểm truy cập cuối được file system báo cáo |
| `creationTime()` | `FileTime` | Thời điểm tạo được file system báo cáo |
| `size()` | `long` | Kích thước được báo cáo, thường theo **byte** đối với file thường |
| `isRegularFile()` | `boolean` | Có phải file thường hay không |
| `isDirectory()` | `boolean` | Có phải thư mục hay không |
| `isSymbolicLink()` | `boolean` | Có phải symbolic link hay không |
| `isOther()` | `boolean` | Một loại mục khác ba loại trên hay không |
| `fileKey()` | `Object` hoặc `null` | Khóa nhận diện file nếu provider cung cấp |

### FileTime và các mốc thời gian

`FileTime` biểu diễn một mốc thời gian, có thể được chuyển sang `Instant` hoặc các đơn vị thời gian phù hợp.

~~~java
FileTime modified = attrs.lastModifiedTime();
System.out.println(modified.toInstant());
~~~

Đây là mảnh mã với `attrs` đã đọc từ một file. Không in một timestamp cố định trong bài tập trừ khi bạn đã chủ động đặt giá trị và xác định provider hỗ trợ độ chính xác đó.

Ba timestamp thường được hiểu:

- **last modified**: lần sửa nội dung/metadata theo định nghĩa của hệ thống, thông thường liên quan thay đổi nội dung file.
- **last accessed**: lần truy cập cuối; nhiều file system/mount không cập nhật thời điểm truy cập theo từng lần đọc vì lý do hiệu năng.
- **creation**: thời điểm tạo; một số hệ thống không lưu mốc này như một trường độc lập.

**Hợp đồng Java quan trọng:** nếu hệ thống không hỗ trợ một timestamp, phương thức vẫn có thể trả **giá trị mặc định do triển khai quy định**, chẳng hạn thời điểm sửa đổi cuối hoặc epoch, thay vì báo “không có” bằng `null`. Không được xem mọi `creationTime()` đều chắc chắn phản ánh ngày sinh thật của file.

### `size()` đo byte, không đo ký tự Java

Với file thường, `size()` trả kích thước theo byte được file system báo cáo, **không phải**:

- `String.length()` (đơn vị UTF-16 `char`),
- số ký tự hiển thị,
- số dòng,
- số Unicode code point.

Ví dụ chuỗi `"Xin chào"` khi ghi bằng UTF-8 có thể có số byte lớn hơn số ký tự hiển thị. Với file nén/sparse file, số byte được báo cáo có thể không trùng dung lượng vật lý thực chiếm. Với thư mục hoặc mục không phải file thường, giá trị kích thước **phụ thuộc implementation** và không có ý nghĩa “tổng dung lượng mọi file con”.

### Bốn phép phân loại loại file

~~~java
if (attrs.isRegularFile()) {
    // File thường, có nội dung dạng byte.
} else if (attrs.isDirectory()) {
    // Directory.
} else if (attrs.isSymbolicLink()) {
    // Chính symbolic link nếu đọc với NOFOLLOW_LINKS.
} else if (attrs.isOther()) {
    // Loại khác, ví dụ đối tượng đặc biệt do provider xác định.
}
~~~

Mảnh mã trên dùng `attrs` đã khai báo. Thông tin phân loại được xác định **tại thời điểm đọc**, không cấp quyền truy cập hay khóa file. Khi đọc thuộc tính mặc định (theo link), `isSymbolicLink()` có thể false ngay cả khi đường dẫn đầu vào là symbolic link, vì bạn đang nhìn thuộc tính **đích của link**.

### `fileKey()` là khóa nhận diện, không phải đường dẫn

`fileKey()` có thể trả một object dùng để nhận diện file trong phạm vi provider, ví dụ tổ hợp device ID/inode trên một số hệ thống Unix. Nhưng:

- Provider được phép trả `null` khi không có file key.
- Không coi `fileKey().toString()` là format chuẩn hay ID ổn định để lưu lâu dài.
- Tính duy nhất chỉ được bảo đảm trong điều kiện file system và file giữ nguyên; sau khi xóa có thể tái sử dụng ID.
- Không so sánh tùy tiện các file key từ hai providers khác nhau.
- Nếu cần xác định **hai Path có đang chỉ tới cùng file**, dùng `Files.isSameFile(path1, path2)` theo hợp đồng riêng, và vẫn tính tới khả năng file bị thay đổi ngay sau đó.

## 4. Chương trình Java 17+ hoàn chỉnh: đọc thuộc tính file thường

Tạo file **`BasicAttributesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.BasicFileAttributeView;

public class BasicAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("basic-attrs-");
        Path file = directory.resolve("hello.txt");

        try {
            Files.writeString(file, "Hello!", StandardCharsets.UTF_8);

            BasicFileAttributes attrs =
                    Files.readAttributes(
                            file, BasicFileAttributes.class);

            BasicFileAttributeView view =
                    Files.getFileAttributeView(
                            file, BasicFileAttributeView.class);

            if (view == null) {
                throw new IOException("Basic attribute view unavailable");
            }

            BasicFileAttributes viaView = view.readAttributes();

            System.out.println("view=" + view.name());
            System.out.println("regular=" + attrs.isRegularFile());
            System.out.println("directory=" + attrs.isDirectory());
            System.out.println("symbolicLink=" + attrs.isSymbolicLink());
            System.out.println("other=" + attrs.isOther());
            System.out.println("bytes=" + attrs.size());
            System.out.println("viaViewBytes=" + viaView.size());
            System.out.println("hasModifiedTime=" +
                    (attrs.lastModifiedTime() != null));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BasicAttributesDemo.java
java BasicAttributesDemo
~~~

**Stdout dự kiến trên file system mặc định thông thường, không có sửa file đồng thời:**

~~~text
view=basic
regular=true
directory=false
symbolicLink=false
other=false
bytes=6
viaViewBytes=6
hasModifiedTime=true
~~~

Giải thích:

1. `Files.createTempDirectory` tạo thư mục thật. Đường dẫn tới file `hello.txt` ban đầu chưa có mục đích.
2. `Files.writeString` ghi 6 byte ASCII của `Hello!` dưới UTF-8.
3. `Files.readAttributes` lấy một bộ thuộc tính theo kiểu `BasicFileAttributes`.
4. `Files.getFileAttributeView` trả view thuộc tên `"basic"`; `view.readAttributes()` đọc một bộ metadata tương ứng ở **lần gọi khác**.
5. `size() == 6` đúng vì chuỗi `Hello!` gồm sáu byte UTF-8.
6. Giá trị timestamp cụ thể không được in, vì không ổn định giữa môi trường và thời điểm chạy.
7. `finally` dọn tài nguyên tạm. Nếu cleanup thất bại thì `IOException` vẫn có thể được truyền lên.

**Không suy luận rằng hai object `attrs` và `viaView` là cùng một instance hay một snapshot nguyên tử chung.** Chúng được lấy qua hai lời gọi đọc riêng; nội dung có thể khác nhau nếu file bị tác nhân khác thay đổi ở giữa.

## 5. `BasicFileAttributeView`: cửa sổ để đọc và cập nhật timestamp

Giao diện này mở rộng `FileAttributeView` và cung cấp ba khả năng chính:

~~~java
String name();
BasicFileAttributes readAttributes() throws IOException;
void setTimes(
        FileTime lastModifiedTime,
        FileTime lastAccessTime,
        FileTime createTime
) throws IOException;
~~~

Tên của view là **`"basic"`**. `readAttributes()` lấy các thuộc tính cơ bản như một **bulk operation** (một lần gọi API). Tuy nhiên, tài liệu **không bảo đảm mọi thuộc tính được lấy nguyên tử so với các thao tác file system khác**; điều đó phụ thuộc implementation.

`setTimes(...)` yêu cầu thay đổi một hoặc nhiều timestamp. Nó **không** dùng để cập nhật size, file key, loại file, tên, ACL hay permission. Các phần đó hoặc là thông tin chỉ đọc, hoặc cần các API khác.

### Cú pháp và quy tắc tham số `null`

~~~java
view.setTimes(modifiedTime, null, null);
~~~

Nghĩa là chỉ yêu cầu cập nhật **last modified time**, còn last access và creation time được chỉ định `null` nên **không yêu cầu thay đổi**.

~~~java
view.setTimes(null, accessedTime, null);
~~~

Chỉ yêu cầu thay đổi last access time.

~~~java
view.setTimes(null, null, createdTime);
~~~

Chỉ yêu cầu thay đổi creation time, **nếu provider/file store hỗ trợ**.

~~~java
view.setTimes(null, null, null);
~~~

Không thay đổi timestamp nào theo hợp đồng.

**Cẩn trọng:** `null` ở đây có nghĩa “không thay đổi thuộc tính tương ứng”, **không phải** “đặt thời gian thành null/1970”. Java có thể phải đọc các giá trị cũ khi chỉ thay một số trường rồi ghi lại; vì vậy cập nhật không được bảo đảm atomic và đôi lúc còn mất độ chính xác của timestamp khác.

### Độ chính xác và giá trị không được hỗ trợ

`FileTime` có thể đại diện một mốc thời gian rất chính xác, nhưng file store có thể chỉ lưu timestamp ở độ phân giải giây, mili giây hoặc cấp khác. Khi cập nhật:

- Java chuyển giá trị về mốc/độ chính xác mà file store hỗ trợ.
- Chuyển từ độ chính xác cao xuống thấp có thể làm tròn hoặc mất phần lẻ.
- Với timestamp không được hỗ trợ hoặc nằm ngoài khoảng hợp lệ, hành vi **không được định nghĩa đầy đủ**: thao tác có thể báo `IOException` hoặc không.
- Vì vậy, **đọc lại để kiểm chứng** nếu timestamp là điều kiện nghiệp vụ quan trọng; không giả định `setTimes` trả về bình thường luôn tạo chính xác từng nano giây.

## 6. Chương trình Java 17+ hoàn chỉnh: cập nhật thời gian sửa đổi

Tạo file **`BasicTimesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class BasicTimesDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("basic-times-");
        Path file = folder.resolve("data.txt");

        try {
            Files.writeString(file, "data", StandardCharsets.UTF_8);

            BasicFileAttributeView view =
                    Files.getFileAttributeView(
                            file, BasicFileAttributeView.class);
            if (view == null) {
                throw new IOException("Basic view unavailable");
            }

            FileTime requested =
                    FileTime.from(Instant.parse("2020-01-02T03:04:05Z"));

            // Chỉ cập nhật last-modified-time.
            view.setTimes(requested, null, null);

            BasicFileAttributes after = view.readAttributes();

            System.out.println("view=" + view.name());
            System.out.println("regular=" + after.isRegularFile());
            System.out.println("requestedYear="
                    + requested.toInstant().atZone(
                            java.time.ZoneOffset.UTC).getYear());
            System.out.println("actualTimestamp="
                    + after.lastModifiedTime());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BasicTimesDemo.java
java BasicTimesDemo
~~~

**Ví dụ stdout trên file store hỗ trợ thời gian được yêu cầu:**

~~~text
view=basic
regular=true
requestedYear=2020
actualTimestamp=2020-01-02T03:04:05Z
~~~

Dòng `actualTimestamp` **không phải kết quả bắt buộc trên mọi nền tảng**: provider có thể thay độ chính xác, từ chối cập nhật hoặc báo một timestamp implementation-specific. Đó là lý do chương trình đọc lại thuộc tính sau khi `setTimes`, thay vì tự in giá trị đã yêu cầu như bằng chứng thành công.

Nếu ứng dụng cần độ chính xác tới đơn vị giây, nên so sánh theo chính sách ứng dụng sau readback:

~~~java
boolean sameSecond =
        after.lastModifiedTime().toInstant().getEpochSecond()
        == requested.toInstant().getEpochSecond();
~~~

Đây là mảnh mã sử dụng `after` và `requested` từ ví dụ trên. Nó so sánh tới **giây**, không đòi nano giây giống nhau, nhưng vẫn có thể trả `false` nếu file store không lưu được giá trị hoặc thao tác thực sự không đạt yêu cầu. Không bỏ qua `false` khi timestamp là ràng buộc nghiệp vụ.

## 7. Đọc một lần bằng `Files.readAttributes` hay giữ `BasicFileAttributeView`?

Có hai cách phổ biến.

### Cách A — Đọc trực tiếp

~~~java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);
~~~

Ưu điểm:

- Ngắn gọn, rõ kiểu tĩnh.
- Phù hợp khi chỉ cần **đọc một snapshot metadata**.
- Mọi trường có thể được dùng nhiều lần từ object kết quả mà không phải đọc lại file system.
- Có thể truyền `LinkOption.NOFOLLOW_LINKS` để đọc chính symbolic link.

### Cách B — Lấy view và thao tác

~~~java
BasicFileAttributeView view =
        Files.getFileAttributeView(
                path, BasicFileAttributeView.class);

BasicFileAttributes before = view.readAttributes();
view.setTimes(newTime, null, null);
BasicFileAttributes after = view.readAttributes();
~~~

Đây là mảnh mã; `path` kiểu `Path`, `newTime` kiểu `FileTime` và cần xử lý `IOException`. Nếu view có thể là `null`, phải kiểm tra trước khi gọi các phương thức.

Ưu điểm:

- Gom việc đọc và yêu cầu cập nhật timestamp qua **cùng loại attribute view**.
- Tiện khi cần đọc–đổi–đọc lại nhiều lần trong một phương thức.
- Cho phép API làm việc với các attribute view khác nhau khi thiết kế hệ thống cần mở rộng.

Cả hai đều thao tác trên file system theo thời điểm gọi; **view không đảm bảo path còn tồn tại, không giữ khóa và không tự đồng bộ hóa người sửa khác**.

| Nhu cầu | Gợi ý |
| --- | --- |
| Xem nhanh size, type, thời gian sửa | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Lấy thuộc tính với kiểm soát symlink | `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` |
| Đọc và cập nhật timestamp qua cùng abstraction | `Files.getFileAttributeView(...).setTimes(...)` rồi `readAttributes()` |
| Chỉ cần last-modified-time | `Files.getLastModifiedTime` / `Files.setLastModifiedTime` |
| Đọc thuộc tính theo tên chuỗi động | `Files.getAttribute` / `Files.readAttributes(path, "basic:*")` |
| Chỉnh permission POSIX hay ACL | Dùng attribute views/chức năng chuyên biệt tương ứng, không phải basic view |

## 8. Typed attributes so với attribute-name strings

Java còn có API thuộc tính động dựa trên tên chuỗi, ví dụ:

~~~java
Map<String, Object> values =
        Files.readAttributes(path, "basic:*");
~~~

Nó trả về `Map<String, Object>` thay vì một `BasicFileAttributes` có phương thức được kiểm tra kiểu lúc biên dịch.

Các tên của nhóm `basic` bao gồm:

- `lastModifiedTime` — `FileTime`
- `lastAccessTime` — `FileTime`
- `creationTime` — `FileTime`
- `size` — `Long`
- `isRegularFile` — `Boolean`
- `isDirectory` — `Boolean`
- `isSymbolicLink` — `Boolean`
- `isOther` — `Boolean`
- `fileKey` — `Object` (có thể `null`)

Khi muốn một thuộc tính:

~~~java
FileTime modified =
        (FileTime) Files.getAttribute(
                path, "basic:lastModifiedTime");
~~~

Khi muốn yêu cầu thay đổi:

~~~java
Files.setAttribute(
        path,
        "basic:lastModifiedTime",
        requestedTime
);
~~~

Đây đều là **mảnh mã** cần import `java.nio.file.Files`, `Path`, `Map`, `FileTime`, khai báo biến `path`/`requestedTime` và xử lý `IOException`.

**Quan trọng:** không được suy ra mọi key trong `basic:*` đều có thể `setAttribute`. Basic view chỉ cung cấp hành vi setter cho **ba trường thời gian** theo `setTimes`. Các thuộc tính như `size`, `isRegularFile`, `fileKey` không có setter tương đương trong `BasicFileAttributeView`.

Với code ứng dụng biết rõ các trường cần đọc, bản typed thường dễ bảo trì hơn vì tránh cast `Object` thủ công và lỗi đánh máy tên thuộc tính.

## 9. Symbolic link và `LinkOption.NOFOLLOW_LINKS`

Đây là một trong những lý do quan trọng nhất phải hiểu **đọc thuộc tính của đối tượng nào**.

Giả sử:

~~~text
data.txt                 (file thường)
shortcut -> data.txt     (symbolic link)
~~~

Khi đọc mặc định:

~~~java
BasicFileAttributes followed =
        Files.readAttributes(
                shortcut, BasicFileAttributes.class);
~~~

`Files.readAttributes` mặc định **theo symbolic link**. Nếu target tồn tại và là file thường, `followed.isRegularFile()` thường là `true`; `followed.isSymbolicLink()` thường là `false` vì attributes mô tả **đích sau khi theo link**.

Để đọc **chính link entry**:

~~~java
BasicFileAttributes linkAttrs =
        Files.readAttributes(
                shortcut,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);

System.out.println(linkAttrs.isSymbolicLink());
~~~

Đây là mảnh mã cần `shortcut` kiểu `Path`, các import thích hợp và xử lý `IOException`. Nếu link thực sự tồn tại, thuộc tính của chính link có `isSymbolicLink() == true`.

Tương tự với attribute view:

~~~java
BasicFileAttributeView linkView =
        Files.getFileAttributeView(
                shortcut,
                BasicFileAttributeView.class,
                LinkOption.NOFOLLOW_LINKS
        );
~~~

`linkView.readAttributes()` nhắm tới chính link theo policy của view. `setTimes` khi dùng view này cũng có thể liên quan cập nhật timestamp của **link entry**, và hỗ trợ thao tác trên link phụ thuộc file system/provider.

**Không gọi code tạo symlink mặc định trong mọi test CI:** trên một số hệ điều hành, quyền người dùng và provider có thể không cho tạo symlink. Khi cần test thật, thiết lập fixture theo khả năng môi trường hoặc skip khi không hỗ trợ.

### Dangling symbolic link

Nếu `shortcut` trỏ đến mục không tồn tại:

- Đọc thuộc tính **theo link** có thể thất bại với `NoSuchFileException`.
- Đọc thuộc tính với `NOFOLLOW_LINKS` vẫn có thể mô tả **chính link** nếu entry link còn tồn tại.

Do đó `Files.exists(shortcut)==false` mặc định không tự chứng minh link entry không có ở đường dẫn. Nếu cần kiểm tra entry link, chọn `NOFOLLOW_LINKS` và xử lý điều kiện unknown/truy cập bị từ chối.

## 10. File chưa tồn tại và view có thể được tạo trước khi file xuất hiện

`Path` là biểu diễn vị trí, không phải một file đã mở; việc lấy attribute view cũng không nên bị hiểu là đã đọc được metadata thật.

Tạo file **`MissingAttributesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;

public class MissingAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("missing-attrs-");
        Path missing = folder.resolve("absent.txt");

        try {
            BasicFileAttributeView view =
                    Files.getFileAttributeView(
                            missing, BasicFileAttributeView.class);

            System.out.println("viewAvailable=" + (view != null));

            if (view == null) {
                return;
            }

            try {
                view.readAttributes();
                System.out.println("unexpected success");
            } catch (NoSuchFileException exception) {
                System.out.println("read=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MissingAttributesDemo.java
java MissingAttributesDemo
~~~

**Stdout dự kiến trên default file system thông thường:**

~~~text
viewAvailable=true
read=NoSuchFileException
~~~

Bài học:

1. `getFileAttributeView` có thể cấp view cho **một Path chưa tồn tại**.
2. `view != null` chỉ chứng minh kiểu view được provider hỗ trợ; **không chứng minh file hiện tồn tại hoặc có quyền đọc**.
3. `readAttributes()` mới cố lấy metadata thật, nên đường dẫn bị thiếu thường dẫn tới `NoSuchFileException`.
4. Đừng dùng view như thay thế cho `Files.exists`; kể cả nếu một phép kiểm tra trước thành công, file vẫn có thể bị thay đổi ngay sau đó.

Với file system provider đặc biệt, loại ngoại lệ cụ thể có thể khác; ví dụ dùng `NoSuchFileException` để minh họa default provider, còn code sản xuất vẫn phải xử lý `IOException`.

## 11. Metadata có phải “snapshot nguyên tử” của file không?

**Không được mặc định là có.**

`BasicFileAttributeView.readAttributes()` đọc tập thuộc tính bằng bulk operation. Tuy vậy, theo tài liệu Java, **liệu tất cả các trường có được đọc nguyên tử so với thao tác file system khác hay không là implementation-specific**.

Một timeline có thể như sau:

~~~text
Thread A                         Thread B
--------                         --------
readAttributes() bắt đầu
                                 ghi thêm dữ liệu vào file
lấy attrs.size()
                                 cập nhật timestamp metadata
nhận attrs
...
sử dụng kết quả cũ
~~~

Chương trình A có thể thấy metadata của một thời điểm, và khi mở file để đọc nội dung thì kích thước/nội dung đã khác. Một `BasicFileAttributes` đã nhận vẫn giữ giá trị cũ, không theo dõi file realtime.

Ví dụ tình huống:

~~~java
BasicFileAttributes before =
        Files.readAttributes(path, BasicFileAttributes.class);

// Người dùng khác/tiến trình khác có thể sửa file ở đây.

byte[] bytes = Files.readAllBytes(path);
boolean sizeMatched = before.size() == bytes.length;
~~~

Đây là mảnh mã đặt trong phương thức xử lý `IOException` với biến `path` đã khai báo. `sizeMatched` có thể false do file thay đổi, và ngay cả nếu true thì **không bảo đảm byte là cùng một phiên bản nội dung** (file có thể được sửa mà kích thước không đổi).

Nếu cần một snapshot nhất quán thực sự, hãy xác định cơ chế của hệ thống: file bất biến/versioned, file locks trong phạm vi hỗ trợ, copy tới staging, transactional storage hoặc protocol phối hợp các bên ghi/đọc. Một object `BasicFileAttributes` không tự tạo ra điều đó.

## 12. `setTimes` không phải giao dịch nguyên tử và không thay quyền

Một câu lệnh:

~~~java
view.setTimes(newModified, null, null);
~~~

có thể cần đọc timestamp cũ rồi ghi metadata mới, tùy provider. Nó không hứa:

- Cập nhật đồng thời cả ba timestamp một cách nguyên tử.
- Giữ nguyên độ chính xác của các timestamp khác trên mọi file store.
- Chống tác nhân khác sửa file ngay sau khi set.
- Giữ một file identity cố định dưới cùng Path.
- Chỉnh `size`, `fileKey`, owner, ACL hoặc POSIX permissions.

Nếu cần thay permission, hãy dùng các API thích hợp, ví dụ:

~~~java
// Chỉ minh họa API; không chạy trên mọi file system.
Files.setPosixFilePermissions(path, permissions);
~~~

Đây là mảnh mã với `permissions` kiểu `Set<PosixFilePermission>`, phụ thuộc hỗ trợ của provider và quyền thực thi. Nó không phải phương thức của `BasicFileAttributeView`.

Với Windows/DOS-style attributes như `hidden`, `readOnly`, `system`, `archive`, cần xem `DosFileAttributeView`. Với POSIX owner/group/permissions, xem `PosixFileAttributeView`. Các view chuyên biệt có thể không được hỗ trợ ở một provider, nên `getFileAttributeView` có thể trả `null` hoặc API tương ứng có thể ném lỗi.

## 13. Phân biệt Basic, DOS và POSIX

| View | Nhóm thuộc tính chính | Hành vi bổ sung |
| --- | --- | --- |
| `BasicFileAttributeView` | Type, size, timestamps, fileKey | `readAttributes`, `setTimes` |
| `DosFileAttributeView` | Basic + hidden, read-only, archive, system | Có setter tương ứng khi hỗ trợ |
| `PosixFileAttributeView` | Basic + owner, group, permission bits POSIX | Có API đổi owner/group/permissions khi hỗ trợ |
| `AclFileAttributeView` | ACL theo mô hình hỗ trợ của provider | Đọc/ghi ACL khi hỗ trợ |
| `UserDefinedFileAttributeView` | Thuộc tính mở rộng do người dùng định nghĩa | Đọc/ghi tên/value cụ thể khi hỗ trợ |

Không phải mọi hệ thống tập tin cung cấp mọi loại view. Đừng dùng `BasicFileAttributes` để kết luận file “có quyền đọc hay không”: nó **không định nghĩa method `canRead()`**. Muốn đánh giá khả năng truy cập, dùng các API tương ứng như `Files.isReadable` (chỉ kiểm tra tại một thời điểm), hoặc thực hiện thao tác mở/đọc và xử lý lỗi thực tế.

Khi code đa nền tảng:

~~~java
if (Files.getFileAttributeView(
        path, java.nio.file.attribute.PosixFileAttributeView.class) != null) {
    // Provider cung cấp POSIX attribute view.
}
~~~

Đây là mảnh mã, không đảm bảo thao tác đổi quyền sẽ thành công — còn phụ thuộc quyền file thực tế và việc file vẫn tồn tại khi thao tác.

## 14. Những lỗi I/O và ngoại lệ cần xử lý

Các thao tác đọc thuộc tính có thể thất bại vì:

- File hoặc thư mục đã bị xóa/chưa từng tồn tại.
- Symbolic link bị hỏng hoặc không thể được giải quyết khi theo link.
- Quyền đọc metadata bị từ chối.
- File system provider/thiết bị mạng gặp lỗi.
- File bị thay thế trong lúc truy vấn.
- Provider không hỗ trợ view hoặc attribute yêu cầu.
- Timestamp mới nằm ngoài phạm vi/độ chính xác hỗ trợ.

Ví dụ code quản lý lỗi rõ ràng:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class AttributeReader {
    private AttributeReader() {}

    public static BasicFileAttributes requireMetadata(Path path)
            throws IOException {
        try {
            return Files.readAttributes(
                    path, BasicFileAttributes.class);
        } catch (NoSuchFileException exception) {
            throw new IOException("File not found: " + path,
                    exception);
        } catch (AccessDeniedException exception) {
            throw new IOException("Cannot inspect metadata: " + path,
                    exception);
        }
    }
}
~~~

Đây là **lớp tiện ích có thể biên dịch** (không có `main`). Nó giữ nguyên nguyên nhân bên trong `IOException(message, cause)` để caller/log có thêm thông tin. Provider không bắt buộc luôn dùng đúng lớp con cụ thể cho mọi tình huống, nên các `IOException` khác vẫn được lan truyền.

Với API đọc map động, tên thuộc tính không hỗ trợ có thể ném `IllegalArgumentException` hoặc `UnsupportedOperationException` theo hợp đồng từng phương thức. Không bắt mọi `RuntimeException` rồi gộp thành “file không tồn tại”.

Một số giá trị `false` từ `Files.isRegularFile(path)` / `Files.exists(path)` có thể có nghĩa không xác định được trạng thái; khi nghiệp vụ cần lý do, `Files.readAttributes` cung cấp đường báo lỗi rõ hơn.

### Bảo mật và quyền truy cập

Metadata có thể chứa đường dẫn, ID file hay timestamp nhạy cảm trong một số bối cảnh. Không ghi thông tin người dùng/path tuyệt đối vào log công khai theo thói quen. Nếu đường dẫn đến từ nguồn không tin cậy, kiểm soát path traversal/symlink và quyền thao tác thực tế. `readAttributes()` thành công không trao quyền truy cập file hay bảo vệ khỏi TOCTOU.

## 15. Khi nào dùng `Files.size` / `getLastModifiedTime` thay vì đọc nhiều trường?

Nếu chỉ cần **một trường**, API tiện ích có thể rõ nghĩa hơn:

~~~java
long bytes = Files.size(path);
FileTime modified = Files.getLastModifiedTime(path);
~~~

Nếu cần **nhiều trường** để hiển thị hoặc phân loại file:

~~~java
BasicFileAttributes attrs =
        Files.readAttributes(
                path, BasicFileAttributes.class);

long bytes = attrs.size();
boolean directory = attrs.isDirectory();
FileTime modified = attrs.lastModifiedTime();
~~~

Những lời gọi đầu là hai truy vấn riêng; lời gọi sau lấy bộ thuộc tính một lần. Không được tuyên bố rằng đọc một lần đảm bảo tất cả trường atomic, nhưng khi mục tiêu là đọc nhiều thuộc tính gần thời điểm nhau, bộ attribute typed là giải pháp tiện và có thể giảm số round trip metadata.

Nếu cần đổi timestamp, dùng `Files.setLastModifiedTime` cho trường hợp đơn giản; dùng `BasicFileAttributeView.setTimes` khi muốn đổi các mốc khác hoặc nhiều mốc trong cùng API.

**Đừng lạm dụng `Files.size` để dự đoán chắc số byte sẽ nhận trong lần đọc tiếp theo**: file có thể thay đổi. Khi đọc streaming, số byte thực đọc và EOF từ stream vẫn là sự thật cần xử lý.

## 16. Ứng dụng thực tế: thống kê file và lọc theo loại

Ví dụ ứng dụng liệt kê thư mục và chỉ xử lý file thường, với metadata lấy từ từng path:

~~~java
try (java.nio.file.DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory)) {
    for (Path child : stream) {
        BasicFileAttributes attrs =
                Files.readAttributes(
                        child, BasicFileAttributes.class,
                        java.nio.file.LinkOption.NOFOLLOW_LINKS);
        if (attrs.isRegularFile()) {
            System.out.println(child.getFileName() + ": "
                    + attrs.size() + " bytes");
        }
    }
}
~~~

Đây là **mảnh mã** nằm trong phương thức có các biến/import phù hợp và xử lý `IOException` (lỗi phát sinh trong lúc duyệt `DirectoryStream` có thể được bọc trong `DirectoryIteratorException`). `DirectoryStream` là tài nguyên phải đóng. Đọc với `NOFOLLOW_LINKS` có nghĩa một symlink tới file sẽ **không** được coi là file thường trong chính lần phân loại đó.

Nếu cần quét một cây thư mục lớn, có thể sử dụng `Files.walkFileTree` và tận dụng `BasicFileAttributes` được cung cấp trong callback của `FileVisitor`. Không nhất thiết truy vấn metadata lần hai nếu callback đã có bộ thuộc tính phù hợp.

### Callback trong `walkFileTree`

~~~java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    if (attrs.isRegularFile()) {
        totalBytes += attrs.size();
    }
    return FileVisitResult.CONTINUE;
}
~~~

Đây là **mảnh mã của một lớp kế thừa `SimpleFileVisitor<Path>`** với biến `totalBytes` khai báo trong lớp và các import `FileVisitResult`, `Path`, `BasicFileAttributes`, `IOException`. Callback nhận snapshot thuộc tính theo quy trình duyệt. Nếu file thay đổi giữa duyệt và xử lý, `attrs.size()` không nhất thiết trùng với số byte về sau được đọc.

## 17. Hiểu nhầm thường gặp

**1. “`BasicFileAttributes` là đối tượng live; file đổi thì `attrs.size()` đổi.”**  
Sai. `attrs` là dữ liệu đã đọc ở một thời điểm; muốn cập nhật phải đọc lại metadata.

**2. “`BasicFileAttributeView` chính là danh sách thuộc tính.”**  
Sai. View là API đọc và cập nhật; `view.readAttributes()` mới trả về bộ dữ liệu `BasicFileAttributes`.

**3. “`getFileAttributeView(...) != null` chứng minh file đang tồn tại.”**  
Sai. Nó chủ yếu chứng minh provider hỗ trợ view kiểu đó; `readAttributes()` mới thực hiện truy cập metadata và có thể lỗi.

**4. “`setTimes(null, null, null)` đặt timestamp về epoch.”**  
Sai. Cả ba `null` nghĩa là không thay đổi trường nào; `null` riêng lẻ là giữ nguyên timestamp tương ứng.

**5. “`setTimes` bảo đảm thay đổi đồng thời cả ba thời gian một cách nguyên tử.”**  
Sai. Nhà cung cấp file system có thể đọc/ghi trung gian và làm mất độ chính xác, nhất là khi chỉ thay một số trường.

**6. “`creationTime()` luôn là ngày tạo thực sự.”**  
Sai. Nếu file system không hỗ trợ creation time, kết quả có thể là giá trị implementation-specific như thời điểm sửa cuối/epoch.

**7. “`attrs.size()` cho biết dung lượng toàn bộ thư mục.”**  
Sai. Size của mục không phải file thường không được đặc tả phổ quát theo cách đó.

**8. “`fileKey()` luôn khác null và có thể lưu như ID vĩnh viễn.”**  
Sai. Có thể null; không được đảm bảo ổn định sau khi file bị xóa/thay thế hoặc chuyển sang file system khác.

**9. “Đọc attributes từ symlink luôn báo `isSymbolicLink()==true`.”**  
Sai. Mặc định `Files.readAttributes` theo symlink; muốn đọc chính link thì dùng `NOFOLLOW_LINKS`.

**10. “Basic view cho phép đổi owner, permission, ACL.”**  
Sai. Basic view chỉ định nghĩa `setTimes` cho timestamp; cần view chuyên biệt khi muốn cập nhật quyền/thuộc tính bảo mật.

**11. “Đọc metadata thành công đồng nghĩa mở file hoặc ghi file tiếp theo sẽ thành công.”**  
Sai. Quyền, file identity và trạng thái có thể thay đổi; cần xử lý lỗi I/O tại thao tác thật.

**12. “Tất cả provider đều báo đúng cùng một subclass `IOException`.”**  
Sai. Java cho phép khác biệt về các exception cụ thể và khả năng attribute view; code phải sẵn sàng xử lý `IOException`.

## 18. Checklist khi áp dụng trong dự án

- [ ] Đã phân biệt data object `BasicFileAttributes` và view `BasicFileAttributeView`?
- [ ] Có chọn `Files.readAttributes(..., BasicFileAttributes.class)` khi muốn đọc nhiều thuộc tính typed?
- [ ] Có đọc lại nếu cần thông tin cập nhật, thay vì giữ mãi một object attrs?
- [ ] Có hiểu `size` là byte count, không phải số ký tự hay dung lượng đệ quy của directory?
- [ ] Có xác định ý nghĩa `creationTime/lastAccessTime` trên file system thực tế, thay vì tin tuyệt đối?
- [ ] Nếu cần symlink metadata, đã dùng `NOFOLLOW_LINKS` phù hợp?
- [ ] Có kiểm tra khả năng hỗ trợ view và xử lý đường dẫn thiếu, lỗi I/O hoặc thiếu quyền?
- [ ] Khi `setTimes`, đã truyền `null` cho các timestamp không muốn đổi?
- [ ] Khi timestamp là ràng buộc nghiệp vụ, đã đọc lại và đánh giá độ chính xác?
- [ ] Có tránh dùng `fileKey` như ID vĩnh viễn hoặc kết luận identity khi file bị thay đổi?
- [ ] Có dùng POSIX/DOS/ACL view phù hợp nếu cần quyền/thuộc tính ngoài basic?
- [ ] Có xử lý TOCTOU nếu file được thay đổi bởi bên khác?
- [ ] Nếu duyệt nhiều mục, đã đóng `DirectoryStream`/`Stream<Path>` và xử lý lỗi phát sinh khi duyệt?
- [ ] Có kiểm tra kết quả trên những file systems/providers thực sự triển khai?

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `BasicFileAttributes` và `BasicFileAttributeView` khác gì?  
**Đáp án:** `BasicFileAttributes` là bộ giá trị metadata đã đọc; `BasicFileAttributeView` là API để gọi đọc lại và yêu cầu cập nhật timestamp.

**Câu 2.** Muốn biết size, loại file và timestamp bằng một truy vấn typed, dùng gì?  
**Đáp án:** `Files.readAttributes(path, BasicFileAttributes.class)`.

**Câu 3.** `view.setTimes(null, accessTime, null)` thay đổi trường nào?  
**Đáp án:** Chỉ yêu cầu đổi last-access-time; hai trường còn lại được giữ theo hợp đồng.

**Câu 4.** Một `Path` chưa có file thì `getFileAttributeView` có thể trả view không?  
**Đáp án:** Có thể. Lấy view không chứng minh file tồn tại; `view.readAttributes()` có thể ném `NoSuchFileException`.

**Câu 5.** `attrs.fileKey() == null` có nghĩa file đã bị hỏng không?  
**Đáp án:** Không. Provider có thể không cung cấp file key.

**Câu 6.** `attrs.size()` đối với directory có luôn bằng tổng số byte file con không?  
**Đáp án:** Không. Size của mục không phải file thường phụ thuộc implementation.

**Câu 7.** Muốn xem metadata của chính symbolic link chứ không phải target, cần gì?  
**Đáp án:** Đọc với `LinkOption.NOFOLLOW_LINKS`.

**Câu 8.** `setTimes` hoàn tất mà đọc lại không trùng từng nanosecond thì có chắc Java sai không?  
**Đáp án:** Không. File store có thể có độ phân giải thấp hơn, hoặc một timestamp không được hỗ trợ. Phải đánh giá theo chính sách ứng dụng/file system.

**Câu 9.** Có thể dùng basic view để chỉnh quyền POSIX không?  
**Đáp án:** Không. Dùng API thuộc tính POSIX nếu provider hỗ trợ.

**Câu 10.** `readAttributes` có bảo đảm một snapshot nguyên tử khi file bị sửa đồng thời không?  
**Đáp án:** Không. Java nêu rõ tính nguyên tử của bulk metadata read phụ thuộc implementation.

**Ghi nhớ:** **`BasicFileAttributes` cho bạn biết những gì vừa được quan sát; `BasicFileAttributeView` cho bạn cách đọc/đề nghị cập nhật những thuộc tính đó**. Đặc biệt, `readAttributes()` không khóa file và `setTimes()` không hứa atomicity hay độ chính xác tuyệt đối. Hãy chú ý symbolic link, quyền, provider và xử lý `IOException` ở từng thao tác thật.

## Tài liệu Java SE 17

- [BasicFileAttributes — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
- [BasicFileAttributeView — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html)
- [Files.readAttributes / getFileAttributeView — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileTime — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html)
- [LinkOption — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)