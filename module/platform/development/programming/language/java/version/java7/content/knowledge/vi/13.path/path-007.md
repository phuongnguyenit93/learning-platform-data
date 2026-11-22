# Phân biệt `Path.normalize()` với `Path.toRealPath()` trong Java

## 1. Tổng quan: rút gọn đường dẫn không có nghĩa xác minh file

Trong Java NIO.2, `java.nio.file.Path` mô tả **đường dẫn trong một file system**. Một đường dẫn có thể có các thành phần `.`, `..`, dùng tên tương đối, tên tuyệt đối hoặc đi qua symbolic link. Khi muốn chuẩn hóa một path, hai phương thức dễ nhầm lẫn là:

~~~java
Path lexical = path.normalize();
Path real = path.toRealPath();
~~~

Đây là đoạn minh họa khi đã có biến `Path path`.

**`normalize()`** rút gọn **các thành phần tên** mà không hỏi hệ thống tệp. **`toRealPath()`** xác minh đường dẫn hiện có bằng **file system**, trả kết quả **tuyệt đối** và mặc định giải symbolic link đến target thật.

Hai phương thức có từ Java 7 và **vẫn được dùng trực tiếp trên Java hiện đại**. Phần thực hành dùng Java 21, `Path.of(...)` và `Files.writeString(...)`, không yêu cầu API legacy.

**Mục tiêu học tập:** hiểu điều kiện tồn tại, kiểu đường dẫn trả về, xử lý `.`/`..` và symbolic links, tùy chọn `NOFOLLOW_LINKS`, so sánh hai file thật, những ngộ nhận bảo mật khi chỉ dùng `normalize()` và lựa chọn API phù hợp cho file đã tồn tại hoặc dự định tạo.

## 2. Bảng so sánh cốt lõi

| Tiêu chí | `normalize()` | `toRealPath()` |
| --- | --- | --- |
| Cơ chế | Phân tích **cú pháp path** (*lexical*) | Tra cứu, xác định **đường dẫn thật** qua file system |
| Truy cập file system? | **Không** | **Có**, có thể phát sinh I/O |
| File phải tồn tại? | **Không** | **Có**, theo hợp đồng API |
| Relative path có tự thành absolute? | **Không** | **Có**, kết quả luôn absolute |
| Loại dấu `.`, `..` | Theo thành phần tên, không biết link | Theo ý nghĩa file system, có xét symlink |
| Symbolic link | Không dò và không giải link | Mặc định giải link tới target cuối |
| `NOFOLLOW_LINKS` | Không có tham số | Có thể truyền `LinkOption.NOFOLLOW_LINKS` |
| Checked exception | Không khai báo `IOException` | Khai báo `throws IOException` |
| Dùng cho path chưa tạo? | Phù hợp để rút tên trước khi tạo | Không thể lấy real path của file chưa tồn tại |
| Có bảo đảm cùng file với path đầu vào? | **Không**, nếu tên trước `..` là symlink có thể đổi đích | Thiết kế để chỉ cùng file hiện có theo filesystem |
| Kết quả thể hiện | Tên path mới đã loại phần dư | Tên tuyệt đối của file thực theo filesystem |

**Nhớ ngắn gọn:** `normalize()` giải quyết *tên gọi được rút gọn ra sao?*; `toRealPath()` giải quyết *file hiện có ở đâu theo hệ thống tệp?*

Không nên gọi `normalize()` là cách tìm canonical/real path vì nó không xác minh đường dẫn trên đĩa.

## 3. `normalize()` hoạt động hoàn toàn ở mức lexical

### 3.1. Thành phần `.` và `..`

Trên file system thông thường:

- `.` biểu diễn thư mục hiện tại, thường được bỏ trong quá trình normalization.
- Một tên thư mục/file bình thường ngay trước `..` và chính `..` có thể triệt tiêu nhau.
- Quá trình loại cặp tên được lặp lại cho đến khi không còn tên thừa.
- `..` ở đầu một path tương đối có thể vẫn phải giữ lại vì không có thành phần hợp lệ đứng trước để triệt tiêu.
- Nếu các thành phần trong relative path bị triệt tiêu hết, kết quả là một **empty Path**.

Ví dụ:

~~~java
Path before = Path.of("reports", ".", "draft", "..", "result.txt");
Path after = before.normalize();
// Kết quả lexical tương ứng reports/result.txt.
// Không yêu cầu reports hay draft tồn tại.
~~~

Đây là đoạn minh họa cần import `java.nio.file.Path` và đặt trong phương thức/class phù hợp.

Với `Path.of("alpha", "..").normalize()`, mọi thành phần có thể triệt tiêu nhau, trả về empty `Path`. Empty Path là một đối tượng path hợp lệ, **không** có nghĩa nó tự động xóa file hay thư mục.

### 3.2. Relative vẫn là relative

~~~java
Path relative = Path.of("a", "..", "file.txt");
Path compact = relative.normalize();
System.out.println(compact.getFileName()); // file.txt
System.out.println(compact.isAbsolute());  // false
~~~

Đây là đoạn minh họa; chương trình đầy đủ ở phần 5 sẽ in kết quả tương tự.

`normalize()` không chuyển path thành absolute. Nếu cần tên absolute theo thư mục làm việc, có thể gọi:

~~~java
Path absoluteLexical = relative.toAbsolutePath().normalize();
~~~

Tuy nhiên, **`toAbsolutePath().normalize()` không phải `toRealPath()`**. Nó vẫn chỉ là path tuyệt đối được xây từ biểu diễn tên, chưa chứng minh file tồn tại và chưa giải symbolic link về target.

### 3.3. Không kiểm tra sự tồn tại

~~~java
Path unknown = Path.of("a-file-not-created-yet.txt");
Path shortName = unknown.normalize(); // Vẫn chạy dù file chưa tồn tại.
~~~

Đây là đoạn minh họa; Java không chạm đĩa chỉ để normalize. Vì thế `normalize()` phù hợp cho việc dựng hoặc hiển thị đường dẫn dự kiến, nhưng không thể dùng như kết quả của phép xác minh file.

## 4. `toRealPath()` truy vấn hệ thống tệp

Chữ ký theo interface `Path`:

~~~java
Path toRealPath(LinkOption... options) throws IOException
~~~

Đây là chữ ký API minh họa, không phải code cần tự định nghĩa.

Với lời gọi mặc định:

~~~java
Path realFile = path.toRealPath();
~~~

Java tìm real path của một file đang tồn tại. Đặc điểm:

1. Nếu đầu vào là relative, trước hết xác định path tuyệt đối theo file system.
2. Dựa trên thực tế thư mục/file và các quy tắc tên của provider để tạo path **absolute** và loại các thành phần dư.
3. **Mặc định theo symbolic link**, vì thế kết quả có thể có cấu trúc hoàn toàn khác chuỗi path ban đầu.
4. File phải tồn tại; nếu không tồn tại hoặc I/O xảy ra lỗi, phương thức ném `IOException`, thường là `NoSuchFileException` trong tình huống file không có của default provider.
5. Cách chuẩn hóa tên thực tế có thể phụ thuộc file system. Ví dụ trên file system không phân biệt hoa thường, ký tự trong tên path trả về có thể là cách viết thực tế của file.

**Không suy diễn:** `toRealPath()` không tạo file, không giữ file mở sẵn cho bạn, không khóa hệ thống tệp và không tự cấp quyền truy cập cho caller. Nó cho biết đường dẫn tại **thời điểm tra cứu**, còn hệ thống tệp vẫn có thể thay đổi ngay sau đó.

### 4.1. `LinkOption.NOFOLLOW_LINKS`

~~~java
Path noFollow = path.toRealPath(LinkOption.NOFOLLOW_LINKS);
~~~

Đây là đoạn minh họa, cần import `java.nio.file.LinkOption`.

- Không truyền tùy chọn: `toRealPath()` giải symbolic links đến đích.
- Truyền `NOFOLLOW_LINKS`: phương thức **không resolve symbolic links**.
- Cả hai vẫn là hoạt động lấy real path, có thể thực hiện I/O và kiểm tra đối tượng trong file system.
- Với `symlink/..`, Javadoc nêu rằng thành phần đó chỉ được triệt tiêu nếu **bảo đảm việc triệt tiêu vẫn chỉ tới cùng file**. Không nên coi `toRealPath(NOFOLLOW_LINKS)` chỉ là `toAbsolutePath().normalize()`.

Nếu một path thường không có symlink, hai chế độ có thể trả cùng đường dẫn thực; điều đó không chứng minh hai tùy chọn tương đương trong mọi trường hợp.

## 5. Chương trình Java 21 hoàn chỉnh, không phụ thuộc đường dẫn ổ đĩa cố định

Ví dụ tạo thư mục tạm và file thật, rồi kiểm tra cả đường dẫn relative, đường dẫn có `..`, mode `NOFOLLOW_LINKS` và file chưa tồn tại. Cuối cùng, chương trình dọn chính những tài nguyên đã tạo bằng `finally`. Kết quả là các giá trị ổn định, không phải tên ổ C: hoặc dấu phân cách của hệ điều hành.

Tạo file `src/main/java/demo/NormalizeVsRealPathExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public final class NormalizeVsRealPathExample {
    private NormalizeVsRealPathExample() {}

    public static void main(String[] args) throws IOException {
        Path workspace = Files.createTempDirectory("paths-learning-");
        Path folder = workspace.resolve("folder");
        Path target = workspace.resolve("report.txt");

        try {
            Files.createDirectory(folder);
            Files.writeString(target, "ready", StandardCharsets.UTF_8);

            Path relative = Path.of("draft", "..", "report.txt");
            Path cleaned = relative.normalize();
            System.out.println("normalized-name=" + cleaned.getFileName());
            System.out.println("still-relative=" + !cleaned.isAbsolute());
            System.out.println("empty-normalized="
                    + Path.of("alpha", "..").normalize().toString().isEmpty());

            Path redundant = folder.resolve("..").resolve("report.txt");
            System.out.println("lexical-equals="
                    + redundant.normalize().equals(target));
            Path real = redundant.toRealPath();
            System.out.println("real-equals="
                    + real.equals(target.toRealPath()));
            System.out.println("real-is-absolute=" + real.isAbsolute());
            System.out.println("nofollow-regular="
                    + redundant.toRealPath(LinkOption.NOFOLLOW_LINKS)
                            .equals(target.toRealPath(LinkOption.NOFOLLOW_LINKS)));
            System.out.println("same-file=" + Files.isSameFile(redundant, target));

            Path missing = workspace.resolve("missing.txt");
            System.out.println("missing-normalize-works="
                    + missing.normalize().equals(missing));
            try {
                missing.toRealPath();
            } catch (NoSuchFileException ex) {
                System.out.println("missing-real=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(workspace);
        }
    }
}
~~~

Lệnh kiểm thử trên JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/NormalizeVsRealPathExample.java
java -cp out demo.NormalizeVsRealPathExample
~~~

**Stdout chính xác** trên default file system đã thử:

~~~text
normalized-name=report.txt
still-relative=true
empty-normalized=true
lexical-equals=true
real-equals=true
real-is-absolute=true
nofollow-regular=true
same-file=true
missing-normalize-works=true
missing-real=NoSuchFileException
~~~

**Phân tích kết quả:**

- `normalized-name=report.txt`: cặp `draft/..` được xóa bằng phép biến đổi tên, không yêu cầu có thư mục `draft`.
- `still-relative=true`: `normalize()` không biến một relative `Path` thành absolute.
- `empty-normalized=true`: `alpha/..` bị triệt tiêu hoàn toàn, thành empty Path.
- `lexical-equals=true`: `folder/../report.txt` được rút về `workspace/report.txt` chỉ nhờ cấu trúc tên.
- `real-equals=true`: vì `folder` và `report.txt` có thật, real path của biểu thức có `..` và real path của file đều xác định cùng target.
- `real-is-absolute=true`: output của `toRealPath` là absolute path.
- `nofollow-regular=true`: không có symlink trong ví dụ nên tùy chọn không theo link không làm đổi kết quả.
- `same-file=true`: `Files.isSameFile` được dùng để kiểm tra danh tính file thực, khác với so hai path theo chuỗi.
- `missing-normalize-works=true`: path giả định chưa có vẫn có thể normalize.
- `missing-real=NoSuchFileException`: file giả định chưa tồn tại nên lời gọi `toRealPath` bị từ chối trên default file system.

Với provider khác, kiểu `IOException` cụ thể khi file chưa tồn tại có thể khác; xử lý API ở tầng application nên tôn trọng khai báo checked exception chung.

## 6. Symbolic link làm lộ rõ khác biệt giữa lexical path và real path

Xét một hệ thống tệp kiểu Unix với sơ đồ giả định:

~~~text
/sandbox/
  report.txt
  alias -> /data/project/deep
/data/project/
  report.txt
  deep/
~~~

Khi đi theo symlink `alias` đến thư mục `/data/project/deep`:

~~~text
Tên ban đầu: /sandbox/alias/../report.txt
normalize():   /sandbox/report.txt
toRealPath():  /data/project/report.txt
~~~

Đây là **sơ đồ minh họa phụ thuộc filesystem/provider**, không phải yêu cầu rằng mọi hệ thống đều xử lý liên kết theo một cách bất biến.

`normalize()` chỉ nhìn thấy `alias/..` nên xóa cả cặp tên. Nhưng nếu tra cứu file thật **có theo symbolic link**, `alias` có thể đưa việc duyệt vào thư mục `deep` bên ngoài `sandbox`; `..` khi đó có thể đưa về `/data/project`. Vì thế, **hai path trả về có thể chỉ tới hai file khác nhau**.

Đây là lý do trọng tâm: **`normalize()` không chứng minh rằng đường dẫn sau khi rút gọn trỏ tới cùng file ban đầu**. Javadoc `Path.normalize` cảnh báo rõ về tình huống symlink đứng trước `..`.

Với `NOFOLLOW_LINKS`, đừng áp dụng cơ học phép triệt tiêu `alias/..` trong mọi trường hợp; điều kiện là kết quả phải vẫn giữ đúng file được định danh theo chính sách không theo link.

## 7. So sánh với `toAbsolutePath()` và `Files.isSameFile()`

Bốn thao tác có mục đích khác nhau:

| Cách gọi | Trả lời câu hỏi | Kiểm tra file tồn tại? |
| --- | --- | --- |
| `path.normalize()` | Tên được rút gọn thế nào? | Không |
| `path.toAbsolutePath()` | Tên tuyệt đối theo file system hiện tại là gì? | Không bắt buộc |
| `path.toAbsolutePath().normalize()` | Tên tuyệt đối sau khi rút cú pháp là gì? | Không |
| `path.toRealPath()` | Tên thật của một file tồn tại là gì? | Có |
| `Files.isSameFile(a,b)` | Hai đường dẫn có định danh cùng file không? | Thường có tra cứu thực tế |

### 7.1. Vì sao không chỉ dùng `Path.equals`?

`Path.equals` và `normalize().equals(...)` xét các đối tượng đường dẫn theo quy tắc tương ứng, không nhất thiết xét **danh tính của file thực**. Trong khi đó, hai tên khác nhau có thể truy cập cùng file do symbolic link hoặc **hard link**.

Nếu mục tiêu là xác định liệu hai path hiện có cùng file, ưu tiên `Files.isSameFile(a, b)` và xử lý `IOException`. Không nên đồng nhất tên real path với một định danh toàn cầu duy nhất trong mọi kiểu file system.

### 7.2. `Path.startsWith` khác `String.startsWith`

Không nên bảo vệ một thư mục gốc bằng:

~~~java
// CỐ Ý KHÔNG ĐỦ AN TOÀN: so prefix ký tự
boolean inside = candidate.toString().startsWith(root.toString());
~~~

Ví dụ `/data/app` và `/data/application` có cùng tiền tố chuỗi. `Path.startsWith(Path)` so **các thành phần tên**, không phải prefix ký tự:

~~~java
boolean inside = candidate.startsWith(root);
~~~

Đây là đoạn minh họa trong một context có hai `Path`. Vẫn phải bảo đảm cả hai path được xử lý theo cùng ngữ nghĩa và hiểu symbolic link/TOCTOU nếu dùng để kiểm soát truy cập.

## 8. Bảo mật: `normalize()` không đủ ngăn path traversal

Giả sử ứng dụng chỉ cho đọc file trong thư mục `root`, còn `userRelative` đến từ người dùng. Một cách viết không đầy đủ:

~~~java
Path candidate = root.resolve(userRelative).normalize();
if (!candidate.startsWith(root)) {
    throw new SecurityException("outside root");
}
// Đến đây CHƯA chứng minh đường dẫn thực nằm trong root.
~~~

Đây là **đoạn minh họa rủi ro**, không phải công thức bảo mật hoàn chỉnh. Một thư mục con có thể là symbolic link tới nơi bên ngoài, trong khi `candidate` vẫn có prefix lexical nằm trong `root`.

### 8.1. Kiểm tra file **đang tồn tại** bằng real path

Một helper minh họa (đặt trong class có import `Path` và `IOException`):

~~~java
static Path resolveExistingWithin(Path rootDirectory, Path userRelative)
        throws IOException {
    if (userRelative.isAbsolute()) {
        throw new IllegalArgumentException("relative path required");
    }
    Path realRoot = rootDirectory.toRealPath();
    Path realCandidate = realRoot.resolve(userRelative).toRealPath();
    if (!realCandidate.startsWith(realRoot)) {
        throw new SecurityException("outside allowed directory");
    }
    return realCandidate;
}
~~~

Cách này tốt hơn chỉ kiểm tra lexical path vì so đường dẫn **đã được file system xác minh** với real root. Nhưng nó **không phải sandbox tuyệt đối**:

- Chỉ áp dụng khi candidate **đã tồn tại**; `toRealPath` không tạo file.
- Nếu attacker có quyền đổi symbolic link hoặc directory, có thể xảy ra *time-of-check to time-of-use* (**TOCTOU**) giữa bước check và bước mở file.
- `toRealPath` không giữ file handle hoặc khóa đường dẫn sau khi trả về.
- Với yêu cầu chống race mạnh, cân nhắc cơ chế thao tác trên directory handle như `SecureDirectoryStream` khi provider hỗ trợ, kiểm soát quyền cấp thư mục và giới hạn thao tác file theo môi trường hệ điều hành.

### 8.2. File sắp tạo phải có quy trình riêng

Với path chưa tồn tại, `candidate.toRealPath()` không giúp kiểm tra “file sẽ được tạo ở đâu” theo cách trực tiếp. Có thể xác minh parent đã tồn tại và chính sách tên ở bước đầu, nhưng nếu cần bảo vệ trước symlink race thì chỉ kiểm tra parent rồi gọi `Files.write` vẫn chưa đủ.

Không sử dụng `normalize()` như lớp bảo vệ duy nhất trước đường dẫn không tin cậy, cũng không đánh đồng `NOFOLLOW_LINKS` với bảo đảm an ninh toàn bộ các thành phần đường dẫn.

## 9. Các tình huống biên trong dự án

### 9.1. File thiếu, lỗi quyền hoặc file system thay đổi

Một path có thể normalize thành công dù không tồn tại. `toRealPath` có thể ném `IOException` nếu file thiếu, file system lỗi hoặc truy cập không thực hiện được. Java `Path` là đối tượng **immutable** về cách biểu diễn tên, nhưng directory/link trên đĩa là trạng thái **mutable**. Kết quả `toRealPath` ở hai thời điểm không nhất thiết giống nhau.

### 9.2. Không có symbolic link

Nếu mọi thành phần đều tồn tại và không có link, `normalize` và `toRealPath` có thể tương ứng với cùng file; nhưng một kết quả còn **relative**, kết quả kia luôn **absolute**. Không dùng một test giản đơn làm bằng chứng hai phương thức có cùng ý nghĩa.

### 9.3. Empty Path và tên `..` ở đầu

Một relative path như `Path.of("a","..")` có thể normalize thành empty Path. Giá trị này có ngữ nghĩa liên quan **thư mục mặc định** khi truy cập, không phải lúc nào cũng là lỗi. Nếu nhận đường dẫn từ người dùng, ứng dụng nên quyết định cụ thể có cho phép empty path hay không.

Path mở đầu bằng `..` không tự động bị loại; nó có thể hợp lệ về mặt cú pháp. Kiểm soát ranh giới thư mục phải dựa vào **đích được cho phép**, không chỉ phép tìm chuỗi `".."`.

### 9.4. Phụ thuộc provider và hệ điều hành

Java NIO.2 hỗ trợ các file system provider khác nhau. `normalize` và `toRealPath` có thể khác nhau về các chi tiết như case, quy tắc path và symbolic link. Tránh viết mã giả định Linux slash, Windows drive letter hoặc việc có thể tạo symlink trên mọi máy.

### 9.5. Không tự dùng `toRealPath` cho mọi thao tác nhỏ

Nếu chỉ cần rút gọn tên trước khi hiển thị và **không cần file tồn tại**, `normalize` là đủ. `toRealPath` có chi phí và khả năng thất bại do I/O; chỉ gọi khi nghiệp vụ thực sự cần thông tin file đã tồn tại.

## 10. Ma trận chọn phương thức

| Tình huống | Nên dùng | Ghi chú |
| --- | --- | --- |
| Dọn `.`/`..` ở phần hiển thị | `normalize()` | Chỉ lexical |
| Xây path cho file mới | `resolve(...)`, `normalize()` theo contract | Vẫn cần bảo vệ path không tin cậy |
| Muốn đường dẫn tuyệt đối theo working directory | `toAbsolutePath()` | Không kiểm tra file thực |
| Muốn absolute path đã rút gọn tên | `toAbsolutePath().normalize()` | Không xử lý link như `toRealPath()` |
| Muốn file hiện có và path thật | `toRealPath()` | Mặc định theo symbolic links |
| Muốn không resolve symbolic link | `toRealPath(NOFOLLOW_LINKS)` | Không tương đương normalize |
| Muốn xác định hai path tới cùng file | `Files.isSameFile(a, b)` | Cần xử lý lỗi I/O |
| Muốn giới hạn file đọc trong một root | Real path check cộng chính sách mở file | Tránh symlink và TOCTOU |
| Muốn tạo file mới dưới root có attacker | Thiết kế file access an toàn theo nền tảng | Không chỉ check path rồi open |

## 11. Những hiểu nhầm và cách sửa

**“`normalize()` luôn trỏ cùng file với input.”** Sai nếu việc loại `..` đứng sau symlink làm thay cách đi qua thư mục thật. Không dựa vào phép lexical để suy ra danh tính file.

**“`normalize()` cần path tồn tại.”** Sai; phương thức không truy cập hệ thống tệp.

**“`toRealPath()` chỉ loại các dấu `.` và `..`.”** Sai; nó trả absolute real path và mặc định resolve symlink, cần tra cứu file hiện có.

**“`toAbsolutePath().normalize()` giống `toRealPath()`.”** Sai; cả hai bước trước không xác minh file và không đi theo symbolic link để xác định target.

**“`NOFOLLOW_LINKS` là chế độ không I/O.”** Sai; nó chỉ điều chỉnh hành vi giải symbolic links của `toRealPath`.

**“Tên đường dẫn khác nhau là hai file khác nhau.”** Không nhất thiết, do symlink/hard link; dùng `Files.isSameFile` khi cần.

**“`normalize().startsWith(root)` đảm bảo path nằm trong root khi attacker điều khiển symlink.”** Sai. Cần hiểu real target và TOCTOU.

**“`String.startsWith` đủ để kiểm tra thư mục con.”** Sai do có thể trùng prefix ký tự nhưng khác name element.

**“Gọi `toRealPath()` rồi mở file thì không thể có race.”** Sai; trạng thái hệ thống tệp có thể bị đổi giữa hai thao tác.

## 12. Tự luyện và đáp án

**Câu 1.** `Path.of("a","b","..","result.txt").normalize()` có cần thư mục `a` và `b` tồn tại không? Kết quả tên là gì?

**Đáp án:** Không cần; phần `b/..` bị triệt tiêu theo cú pháp, path còn `a/result.txt` (relative).

**Câu 2.** Vì sao `Path.of("missing").normalize()` chạy được nhưng `Path.of("missing").toRealPath()` có thể ném lỗi?

**Đáp án:** `normalize` không kiểm tra file; `toRealPath` phải tìm file thực đang tồn tại.

**Câu 3.** `toRealPath()` có giữ kết quả relative nếu input relative không?

**Đáp án:** Không. Kết quả luôn absolute; input relative được diễn giải thành absolute trước khi lấy real path.

**Câu 4.** Vì sao `root/link/../target` có thể trỏ tới file khác `root/target` sau khi follow symlink?

**Đáp án:** `link` có thể dẫn tới một directory bên ngoài; `..` khi truy cập thực có thể tham chiếu parent của đích link, trong khi normalize chỉ xóa cặp tên lexical `link/..`.

**Câu 5.** `toRealPath(NOFOLLOW_LINKS)` có giống `normalize()` không?

**Đáp án:** Không. Nó vẫn cần thông tin file system, trả path absolute và có chính sách không resolve symlink.

**Câu 6.** Vì sao không nên so `candidate.toString().startsWith(root.toString())`?

**Đáp án:** Vì prefix ký tự không phản ánh ranh giới thư mục. Dùng `Path.startsWith` với path chuẩn bị phù hợp, và nếu là kiểm soát truy cập thì xử lý cả symlink/race.

**Câu 7.** Nếu hai đường dẫn là hard link tới cùng một file, cách kiểm tra phù hợp?

**Đáp án:** `Files.isSameFile(a, b)`, không đơn thuần dựa trên `Path.equals` hoặc `toRealPath().equals`.

**Câu 8.** Có thể dùng `toRealPath` cho một file sẽ tạo ngày mai không?

**Đáp án:** Không khi file còn chưa tồn tại. Dựng tên và xử lý chính sách tạo file, xác thực parent/ownership theo cách khác.

**Câu 9.** Tại sao xác minh real path trước khi mở vẫn chưa chống race tuyệt đối?

**Đáp án:** Vì symbolic link/thư mục có thể thay đổi sau lần kiểm tra, trước thao tác mở; đây là TOCTOU. Cần kiến trúc mở file theo handle/quyền an toàn nếu có yêu cầu bảo vệ mạnh.

## 13. Checklist và nguồn chính thức

- [ ] Xác định nhu cầu là **rút tên lexical** hay **tìm file thật đang tồn tại**.
- [ ] Dùng `normalize()` cho việc rút `.`/`..` và hiểu nó **không** truy cập file system.
- [ ] Dùng `toRealPath()` khi cần real path; xử lý `IOException` và thực tế tồn tại.
- [ ] Nhớ `toRealPath` cho absolute result, mặc định follow symlink.
- [ ] Chỉ truyền `NOFOLLOW_LINKS` khi có chủ đích không resolve link.
- [ ] Không coi `toAbsolutePath().normalize()` là canonical file check.
- [ ] Khi cần xác định cùng file, cân nhắc `Files.isSameFile`.
- [ ] Với directory boundary, tránh `String.startsWith`; cân nhắc real path + chống TOCTOU.
- [ ] File chưa tồn tại cần một quy trình tạo riêng, không gọi `toRealPath` trên đích mới rồi kỳ vọng thành công.
- [ ] Kiểm tra edge cases: missing path, empty path, symlink, quyền truy cập và provider thực tế.
- [ ] Kiểm thử ví dụ bằng `javac --release 21 -Xlint:all`.
- [ ] Chỉ sử dụng API và hướng dẫn đang còn áp dụng, không khuyến nghị API legacy.

**Javadoc chính thức:**

- [Java SE 21 — Path.normalize](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#normalize()): lexical rút tên, không truy cập file system, cảnh báo khác file nếu có symlink.
- [Java SE 21 — Path.toRealPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toRealPath(java.nio.file.LinkOption...)): absolute path của file hiện có, symlink và `NOFOLLOW_LINKS`.
- [Java SE 21 — Path.toAbsolutePath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toAbsolutePath()): lấy path tuyệt đối.
- [Java SE 21 — Files.isSameFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path)): kiểm tra hai path định danh cùng file.
- [Java SE 21 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): cơ chế directory-handle cho một số providers khi cần giảm race.

**Kết luận:** `normalize()` chỉ rút gọn **tên**, còn `toRealPath()` xác định **file thật** qua filesystem. Đừng dùng phép lexical như một xác minh bảo mật. File mới và file hiện có cần cách xử lý khác nhau, còn file do người dùng chỉ định cần cả chính sách symlink và phòng TOCTOU nếu quyền truy cập là vấn đề quan trọng. Các nguyên tắc này vẫn đúng trên Java hiện đại.
