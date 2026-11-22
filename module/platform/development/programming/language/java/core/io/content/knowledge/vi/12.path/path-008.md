# URI, Path.toUri() và giới hạn chuyển đổi giữa các FileSystemProvider trong Java

`java.nio.file.Path` biểu diễn một đường dẫn theo **quy tắc của một hệ thống tệp**. `java.net.URI` biểu diễn một **định danh tài nguyên có scheme** như `file:`, `jar:` hoặc `https:`. Trong Java NIO.2, `Path.toUri()` có thể biến một đường dẫn thành URI do provider của đường dẫn đó định nghĩa; `Path.of(URI)` hoặc `Paths.get(URI)` đi chiều ngược lại **chỉ khi có `FileSystemProvider` phù hợp và các điều kiện của provider được đáp ứng**.

Ba điều phải nhớ:

1. `Path.toUri()` **không tạo file**, không mở tài nguyên, cũng không hứa mọi URI đều là `file:`.
2. `Path.of(uri)` **không phải bộ tải URL hoặc phép chuyển đổi URI phổ quát**. Nó cần provider có thể diễn giải scheme và có thể cần một `FileSystem` đang mở.
3. Kết quả và khả năng chuyển đổi hai chiều **phụ thuộc provider**. URI `file:` của filesystem mặc định khác URI `jar:` của ZIP filesystem, và `https:` thông thường không thể dùng trực tiếp như một `Path` Java NIO.

Bài học dùng Java 17+, tập trung vào `Path`, `URI`, `toUri()`, `Path.of(URI)`, `FileSystems`, `FileSystemProvider`, ranh giới giữa provider và các trường hợp lỗi dễ gây nhầm lẫn.

## 1. Path và URI giải quyết hai bài toán khác nhau

| API | Mô hình | Ví dụ | Điều quan trọng |
| --- | --- | --- | --- |
| `Path` | Đường dẫn **trong một FileSystem** | `Path.of("docs", "guide.txt")` | Có provider, filesystem, root và quy tắc path riêng |
| `URI` | Định danh tài nguyên theo cú pháp chung | `URI.create("https://example.com/a")` | Có scheme và các thành phần URI; không mặc định là file cục bộ |
| `Path.toUri()` | Chuyển `Path` sang URI do provider biểu diễn | `path.toUri()` | Dạng URI và bảo đảm round-trip tùy provider |
| `Path.of(URI)` | Yêu cầu provider diễn giải URI thành `Path` | `Path.of(fileUri)` | Có thể thành công hoặc ném ngoại lệ |
| `FileSystemProvider` | Nhà cung cấp cách xử lý đường dẫn/file | Provider mặc định, ZIP/JAR provider | Quy định scheme, kiểu Path và cách truy cập |

Sơ đồ:

```text
                     +----------------------+
                     | Path                 |
                     | thuộc FileSystem A   |
                     +----------------------+
                             |
                             | path.toUri()
                             v
                    URI (scheme tùy A)
                             |
                             | Path.of(uri)
                             | chọn provider theo scheme
                             v
                FileSystemProvider tương ứng
                             |
                +------------+-------------+
                |                          |
         provider & filesystem       thiếu provider / chưa mở
         có thể giải quyết URI       filesystem / URI không hợp lệ
                |                          |
                v                          v
           Path mới              Exception / không chuyển được
```

Đối tượng `Path` có thể tồn tại ngay cả khi file chưa tồn tại, tương tự `java.io.File`. `URI` thuần túy cũng không xác nhận tài nguyên đang tồn tại. Tạo `Path`/`URI` và ghi dữ liệu xuống filesystem là những hành động khác nhau.

### Hai chiều chuyển đổi quen thuộc

```java
Path path = Path.of("docs", "hello.txt");
URI uri = path.toUri();
Path restored = Path.of(uri);
```

Đây là mảnh mã; cần import `java.nio.file.Path` và `java.net.URI`. Trong filesystem mặc định, URI tạo ra thường mang scheme `file`, ở dạng tuyệt đối. Đường dẫn nhận lại tương ứng đường dẫn **tuyệt đối**, không nhất thiết bằng chuỗi đường dẫn tương đối ban đầu.

Không viết `Path.of(uri.toString())` để thay cho `Path.of(uri)`: overload nhận `String` hiểu chuỗi đó theo **cú pháp đường dẫn của hệ điều hành**, không phân tích scheme URI; trên Windows, `file:...` có thể là đường dẫn bất hợp lệ, còn trên Unix có thể bị hiểu thành tên khác với mong muốn.

## 2. Path.toUri(): kết quả là URI tuyệt đối, không nhất thiết là file đang có

Chữ ký:

```java
URI uri = path.toUri();
```

Với provider mặc định, `toUri()` tạo một URI **tuyệt đối** có scheme `file`, biểu diễn đường dẫn tuyệt đối. Ví dụ (chỉ minh họa, phụ thuộc OS và thư mục làm việc):

```text
Path tương đối: docs/hello world.txt
Trên Unix có thể thành: file:///home/user/project/docs/hello%20world.txt
Trên Windows có thể thành: file:///C:/work/project/docs/hello%20world.txt
```

Đặc điểm:

- `path.toUri().isAbsolute()` là `true` vì kết quả có scheme.
- `path.toUri()` **không yêu cầu file vật lý đã tồn tại**. Có thể chuyển đường dẫn tới tên dự định tạo trong tương lai.
- Với default provider, đường dẫn tương đối được chuyển thành dạng tương ứng **đường dẫn tuyệt đối** khi tạo URI.
- Dấu cách, ký tự `#` và một số ký tự đặc biệt được **percent-encode** khi cần; ví dụ `hello #.txt` có phần tương ứng `hello%20%23.txt` trong dạng ASCII URI.
- Khi có thể xác định đích là thư mục, URI của đường dẫn thư mục theo provider mặc định có thể kết thúc bằng `/`. Không dựa vào dấu `/` cuối như phép xác thực duy nhất rằng tài nguyên là thư mục.
- URI này không chứng minh file có tồn tại, có quyền đọc, hay thực sự là một file thường.

`Path.toUri()` là phép tạo biểu diễn URI, không tương đương `toRealPath()`. `toRealPath()` truy vấn đường dẫn thật trên filesystem và thường yêu cầu tài nguyên tồn tại; `toUri()` không cung cấp cùng bảo đảm.

### Ví dụ chứng minh không có I/O tạo file

```java
Path missing = Path.of("never-created.txt");
URI uri = missing.toUri();
System.out.println(Files.exists(missing)); // Thường false nếu chưa được tạo
```

Đây là mảnh mã với import `java.nio.file.*` và `java.net.URI`. Kết quả `exists` phụ thuộc thư mục làm việc, vì file tên đó có thể đã tồn tại trước khi chạy. Ý chính là: bản thân `toUri()` **không gọi API tạo file**.

## 3. Quy tắc round-trip của filesystem mặc định

Trong Java SE 17, provider mặc định có bảo đảm quan trọng: khi tạo và dùng các đối tượng **trong cùng JVM**, phép chuyển `Path` → `URI` → `Path` bằng provider mặc định thỏa mãn ý tưởng:

```java
Path p = Path.of("docs", "hello.txt");
boolean same = Path.of(p.toUri()).equals(p.toAbsolutePath());
```

Đây là mảnh mã, cần import `java.nio.file.Path`. Với provider mặc định theo hợp đồng Java, kết quả là `true` trong bối cảnh áp dụng bảo đảm đó. Đối với `p` ban đầu là **tương đối**, không nên so sánh `Path.of(p.toUri())` trực tiếp với `p` rồi ngạc nhiên khi `equals` trả `false`: bên trái đã mang đường dẫn tuyệt đối.

Nhưng **bảo đảm này không được tự động áp dụng cho mọi provider khác**. Một provider có thể dùng URI riêng, yêu cầu filesystem đã mở, hoặc không cho phép tái tạo đường dẫn chỉ dựa vào một URI được lưu bên ngoài. Ngoài ra:

- `Path.equals` thường là **so sánh theo cấu trúc Path/provider**, không phải bằng chứng hai đường dẫn trỏ tới cùng một thực thể vật lý.
- `Files.isSameFile(p1, p2)` là API khác để kiểm tra hai đường dẫn có cùng file thực (có thể đụng filesystem và ném `IOException`); nó không thay thế cú pháp round-trip.
- `toAbsolutePath()` không phải `toRealPath()`. Đường dẫn tuyệt đối có thể vẫn chứa các thành phần biểu diễn chưa được giải quyết theo trạng thái thực của filesystem.
- Nếu truyền URI qua máy khác/OS khác, chuỗi URI mặc định được tạo trên Windows không được bảo đảm sẽ biến thành cùng một `Path` trên Linux, và ngược lại.

Tính round-trip nên được hiểu trong **hợp đồng của provider và môi trường cụ thể**, không phải cam kết URI có thể gắn vào bất kỳ runtime nào.

## 4. URI là đối tượng có scheme, không phải tất cả URI là file

`URI` có các thành phần cú pháp khác nhau, chẳng hạn:

```text
https://example.com/docs/guide.html?lang=vi#intro
\___/  \_________/ \______________/ \_____/ \___/
scheme  authority         path         query fragment

file:///tmp/hello%20world.txt
\__/   \_____________________/
scheme          raw path

jar:file:///tmp/sample.zip!/docs/guide.txt
\_/  \_________________________________/
scheme       scheme-specific part
```

Các phương thức hữu ích của `URI`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getScheme()` | Scheme như `file`, `jar`, `https` |
| `isAbsolute()` | URI có scheme hay không; khác `Path.isAbsolute()` |
| `isOpaque()` | URI thuộc loại opaque hay hierarchical |
| `getPath()` | Path **đã percent-decode** cho URI hierarchical, hoặc `null` nếu không có thành phần đó |
| `getRawPath()` | Path còn escape phần ký tự theo URI, hoặc `null` |
| `getSchemeSpecificPart()` | Thành phần phụ thuộc scheme (dạng đã decode) |
| `toASCIIString()` | Biểu diễn ASCII với escaping thích hợp |
| `resolve(...)` | Giải quyết URI tham chiếu theo **quy tắc URI**, không phải `Path.resolve` |

Một URI opaque như `jar:file:/...!/entry` thường có `getPath() == null`. Vì thế đừng lấy `uri.getPath()` rồi áp dụng `Path.of(...)` với mọi URI. Đừng tự cắt `jar:`/`file:` từ chuỗi theo `substring(...)` hay giải mã phần `%20` thủ công; URI có thể bao gồm các delimiter mang ý nghĩa riêng của provider.

Ví dụ đường dẫn có dấu `#`:

```java
Path p = Path.of("hello #.txt");
URI uri = p.toUri();
System.out.println(uri.getFragment()); // null với URI được tạo cho tên file đó
```

Dấu `#` **nằm trong tên file**, nên `toUri` phải escape nó thay vì diễn giải như fragment. Ngược lại, nếu người lập trình tự ghép chuỗi `"file:///.../hello #.txt"` bằng `URI.create(...)`, dấu khoảng trắng khiến URI không hợp lệ và có thể gây `IllegalArgumentException`. Hãy dùng `Path.toUri()` hoặc constructor `URI` phù hợp thay vì tự ghép URI từ path thô.

## 5. Path.of(URI) và Paths.get(URI): yêu cầu provider xử lý URI

Hai API tương ứng:

```java
Path path1 = Path.of(uri);  // Java 11+
Path path2 = Paths.get(uri); // API có từ Java 7
```

Đây là mảnh mã cần import `java.net.URI` và `java.nio.file.*`. Cả hai dựa trên hệ thống **`FileSystemProvider` được cài đặt/khám phá** để xử lý scheme. Không nên tự diễn giải rằng chúng chỉ dành cho `file:`, nhưng cũng không nghĩ chúng tự hỗ trợ mọi URI.

Quy trình logic:

1. Nhận `URI`.
2. Xem scheme, chọn provider phù hợp.
3. Yêu cầu provider tạo `Path` trỏ vào filesystem tương ứng.
4. Provider có thể trả Path hoặc báo rằng URI sai định dạng, filesystem chưa tồn tại, chưa được mở, hay provider không được cài.

Những ngoại lệ có thể gặp (tùy tình huống/provider):

- `IllegalArgumentException`: URI không đáp ứng yêu cầu cú pháp của provider hoặc đối số không hợp lệ.
- `FileSystemNotFoundException`: không tìm được filesystem phù hợp, chẳng hạn một ZIP filesystem đã đóng hoặc chưa được khởi tạo theo cách mà provider tra cứu được.
- `ProviderNotFoundException`: thao tác tạo filesystem không tìm thấy provider cho scheme theo hợp đồng của API có liên quan. Không suy diễn mọi lời gọi `Path.of(URI)` khi thiếu scheme đều nhất thiết ném đúng lớp này.
- `SecurityException` hoặc ngoại lệ truy cập có thể xuất hiện khi hệ thống bảo mật/chính sách truy cập từ chối một số thao tác.

Đừng viết:

```java
Path remote = Path.of(URI.create("https://example.com/file.txt"));
```

rồi cho rằng Java tự tải dữ liệu HTTP. Một URI `https:` là locator web; Java NIO mặc định không có filesystem provider HTTP có thể diễn giải trực tiếp như `Path`. Nếu muốn tải nội dung web, dùng `HttpClient` hoặc API mạng phù hợp, kiểm soát timeout, lỗi HTTP, kích thước, URL redirect và bảo mật. Sau khi tải, bạn có thể lưu bằng `Files.write(...)` vào một Path cục bộ **riêng biệt**.

**Một URI hợp lệ không đảm bảo chuyển được thành Path.** Đây là ranh giới thiết kế giữa định danh tài nguyên và namespace filesystem.

## 6. Ví dụ Java 17+ chạy được: file URI, ký tự escape và path chưa tồn tại

Tạo file `PathUriDefaultDemo.java`:

```java
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathUriDefaultDemo {
    public static void main(String[] args) throws Exception {
        Path relative = Path.of("folder", "hello #.txt");
        URI uri = relative.toUri();

        System.out.println("scheme: " + uri.getScheme());
        System.out.println("URI absolute: " + uri.isAbsolute());
        System.out.println("path relative: " + relative.isAbsolute());
        System.out.println("escaped name: "
                + (uri.toASCIIString().contains("%20")
                && uri.toASCIIString().contains("%23")));
        System.out.println("fragment: " + uri.getFragment());
        System.out.println("round trip: "
                + Path.of(uri).equals(relative.toAbsolutePath()));

        Path root = Files.createTempDirectory("path-uri-");
        try {
            Path missing = root.resolve("not-created.txt");
            URI missingUri = missing.toUri();
            System.out.println("exists before: " + Files.exists(missing));
            System.out.println("same path: " + Path.of(missingUri).equals(missing));
            System.out.println("exists after: " + Files.exists(missing));
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac PathUriDefaultDemo.java
java PathUriDefaultDemo
```

Stdout trên một filesystem mặc định có quyền tạo thư mục tạm, không bị tác nhân khác thay đổi dữ liệu giữa các lệnh:

```text
scheme: file
URI absolute: true
path relative: false
escaped name: true
fragment: null
round trip: true
exists before: false
same path: true
exists after: false
```

Tại sao đầu ra ổn định dù đường dẫn tuyệt đối phụ thuộc máy?

- Không in nguyên URI thực tế; chỉ kiểm tra scheme, trạng thái absolute, encoding ký tự cần escape và round-trip.
- `relative` vẫn là Path tương đối, trong khi `relative.toUri()` cho URI tuyệt đối.
- Chuỗi `hello #.txt` có dấu cách và `#`. URI có các escape `%20` và `%23`; không xuất hiện fragment.
- `Files.createTempDirectory` **thực sự tạo một thư mục tạm**; ngược lại `missing.toUri()` và `Path.of(missingUri)` không tạo `not-created.txt`.
- `Path.of(missingUri).equals(missing)` so sánh hai Path tuyệt đối cùng provider, không yêu cầu file tồn tại.
- `finally` xóa thư mục tạm đã tạo; chương trình không phụ thuộc giá trị động của tên thư mục để tạo output.

Chỉ lệnh `Files.createTempDirectory` và `Files.deleteIfExists` có tác dụng thay đổi filesystem trong ví dụ. Các phép chuyển `Path`/`URI` không tạo tài nguyên.

## 7. FileSystemProvider là gì?

`FileSystemProvider` trong `java.nio.file.spi` là điểm mở rộng cho các kiểu hệ thống tệp. Provider quyết định cách tạo filesystem, tạo Path từ URI, đọc thuộc tính, mở kênh và thực hiện thao tác file. Ví dụ:

- **Filesystem mặc định** của hệ điều hành: đường dẫn cục bộ, scheme thường là `file`.
- **JDK ZIP/JAR filesystem provider** (khi có module `jdk.zipfs`): cho phép làm việc với các mục nằm trong một ZIP/JAR như Path, scheme `jar`.
- Các provider bên thứ ba: có thể truy cập filesystem trong bộ nhớ, kho dữ liệu đặc thù, hệ thống tệp ảo hoặc đích khác tùy triển khai.

Thao tác `path.getFileSystem().provider().getScheme()` cho biết scheme của provider sở hữu `path`. Tuy nhiên, chỉ biết **tên scheme** chưa đủ để đảm bảo URI sẽ tái tạo một Path từ bất cứ tiến trình nào: có thể còn yêu cầu cài provider, cấu hình thông số, quyền truy cập, đăng ký filesystem hoặc mở kết nối.

Ví dụ:

```java
Path local = Path.of("hello.txt");
String scheme = local.getFileSystem().provider().getScheme();
// Ở filesystem mặc định phổ biến: scheme là "file".
```

Đây là mảnh mã cần `java.nio.file.Path`. Tên scheme khác nhau giữa các provider, và không thể bắt mọi provider phải dùng cú pháp `file:/...` hoặc cung cấp URL truy cập được bên ngoài JVM.

## 8. ZIP filesystem: một file vật lý có nhiều Path bên trong

Một archive `sample.zip` có thể chứa nhiều entry như `/notes/readme.txt`. Với ZIP filesystem provider, hai loại Path sau rất khác nhau:

```text
Filesystem mặc định                       ZIP filesystem
----------------------------------        --------------------------------
Path.of("/tmp/sample.zip")                 zip.getPath("/notes/readme.txt")
  -> trỏ tới archive vật lý                -> trỏ tới entry *bên trong* archive

file:///tmp/sample.zip                     jar:file:///tmp/sample.zip!/notes/readme.txt
scheme: file                               scheme: jar
```

URI `jar:` (với provider ZIP/JAR phù hợp) chứa cả **URI của archive** và **đường dẫn entry**. Ký hiệu `!` phân tách theo cú pháp ZIP/JAR provider, không phải quy tắc chung của mọi URI.

Vì vậy không thể lấy `URI.getPath()` của `jar:...` rồi giả định đó là đường dẫn filesystem mặc định. Một URI `jar:` thường opaque, nên `getPath()` là `null`. Bạn phải dùng provider tương ứng.

Quan trọng: `Path.of(jarUri)` có thể **không hoạt động ngay cả khi URI đúng định dạng**, nếu ZIP FileSystem chưa được mở/đăng ký theo cách provider có thể tra cứu. Một ZIP archive tồn tại trên đĩa không tự làm cho FileSystem của các entry bên trong tồn tại trong JVM.

### Ví dụ Java 17+ chạy được với ZIP filesystem

Tạo `ZipUriProviderDemo.java`:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipUriProviderDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("zip-uri-");
        Path archive = root.resolve("sample.zip");

        // URI của filesystem ZIP: jar:<URI của archive>
        URI zipFileSystemUri = URI.create("jar:" + archive.toUri());
        URI entryUri;

        try {
            // Mở ZIP FS bằng URI để provider đăng ký nó cho việc lookup.
            try (FileSystem zip = FileSystems.newFileSystem(
                    zipFileSystemUri, Map.of("create", "true"))) {

                Path entry = zip.getPath("/lesson.txt");
                Files.writeString(entry, "hello", StandardCharsets.UTF_8);

                entryUri = entry.toUri();

                System.out.println("entry scheme: " + entryUri.getScheme());
                System.out.println("entry opaque: " + entryUri.isOpaque());
                System.out.println("provider scheme: "
                        + entry.getFileSystem().provider().getScheme());
                System.out.println("round trip while open: "
                        + Path.of(entryUri).equals(entry));
            }

            // FileSystem đã đóng; lookup URI entry có thể thất bại.
            try {
                Path.of(entryUri);
                System.out.println("round trip after close: available");
            } catch (FileSystemNotFoundException e) {
                System.out.println("round trip after close: unavailable");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy với JDK 17+ có ZIP filesystem provider:

```bash
javac ZipUriProviderDemo.java
java ZipUriProviderDemo
```

Stdout đã kiểm tra trên JDK có `jdk.zipfs`:

```text
entry scheme: jar
entry opaque: true
provider scheme: jar
round trip while open: true
round trip after close: unavailable
```

Giải thích:

1. `archive.toUri()` là URI của file ZIP trong filesystem **mặc định** (`file:`).
2. `URI.create("jar:" + archive.toUri())` biểu diễn một ZIP filesystem để provider `jar` có thể mở.
3. `FileSystems.newFileSystem(zipFileSystemUri, Map.of("create", "true"))` tạo/mở ZIP filesystem; khi archive chưa tồn tại, tùy chọn `create` cho phép tạo archive theo cơ chế ZIP provider.
4. `zip.getPath("/lesson.txt")` là Path **thuộc ZIP filesystem**, không phải file `lesson.txt` cạnh archive ngoài đĩa.
5. `entry.toUri()` có scheme `jar`; trong trường hợp này URI là opaque.
6. Trong khi ZIP FileSystem được mở/đăng ký theo URI, `Path.of(entryUri)` có thể tìm lại entry Path.
7. Sau `close()`, không còn filesystem mở tương ứng; lookup có thể ném `FileSystemNotFoundException`. Việc file ZIP vật lý vẫn tồn tại **không có nghĩa** ZIP FileSystem vẫn được mở.

Đây là ví dụ có chủ ý phụ thuộc **ZIP FileSystemProvider có sẵn trong JDK**. Các runtime Java cắt giảm module có thể thiếu `jdk.zipfs` và không chạy được phần ZIP; điều đó chính là một minh họa cho giới hạn provider.

**Chi tiết nâng cao:** Mở ZIP FileSystem bằng overload `FileSystems.newFileSystem(Path, Map)` có thể không đăng ký thể hiện đó để `Path.of(jarUri)` tìm kiếm giống với overload nhận **URI**, tùy triển khai provider. Vì vậy không khẳng định “filesystem đang mở” là điều kiện duy nhất; cách nó được tạo và cơ chế lookup cũng quan trọng.

## 9. Các lỗi khi chuyển URI thành Path và cách xử lý

### 9.1. Không hỗ trợ scheme

`URI.create("https://example.com/a")` là URI hợp lệ, nhưng không phải URI của provider `file` hoặc `jar` mặc định. `Path.of(...)` không biến HTTP thành file cục bộ. Nếu ứng dụng có provider bên thứ ba hỗ trợ một scheme nào đó, khả năng xử lý sẽ phụ thuộc chính provider đó; đừng bắt cứng những giả định về mọi runtime.

### 9.2. Provider có nhưng FileSystem chưa mở

URI một entry ZIP như `jar:file:///tmp/a.zip!/x.txt` cần `jar` provider và filesystem thích hợp. Khi chưa mở, đã đóng, hoặc được đăng ký khác cách, `Path.of(uri)` có thể ném `FileSystemNotFoundException`. Hướng xử lý là dùng `FileSystems.newFileSystem(...)`/`getFileSystem(...)` theo hợp đồng ZIP provider, **không** đổi bừa scheme sang `file`.

### 9.3. URI sai yêu cầu của provider

Đối với default `file` provider, URI thường phải là file URI **hierarchical, tuyệt đối**, có path phù hợp và không chứa các thành phần tùy tiện như query/fragment; authority cũng phải được xử lý theo quy tắc provider/nền tảng. Ví dụ các URI dựng thủ công không đúng yêu cầu có thể làm `Path.of(uri)` ném `IllegalArgumentException`.

Đừng tự ghép:

```java
URI bad = URI.create("file:///tmp/hello world.txt");
```

Vì dấu cách không được escape trong chuỗi URI thô; `URI.create` ném `IllegalArgumentException` trước cả bước tạo Path. Một đường dẫn thật nên được tạo bằng `Path.of(...)` rồi gọi `toUri()` để Java xử lý escaping.

### 9.4. Khác máy và khác provider

Một URI `file:///C:/...` có thể là file path hợp lý trên Windows, nhưng không thể giả định nó sẽ có cùng ý nghĩa trên hệ điều hành khác. Với filesystem bên thứ ba, khả năng round-trip ở JVM khác còn phụ thuộc cài đặt provider, trạng thái filesystem và cấu hình truy cập.

Trường hợp xử lý URI từ bên ngoài hệ thống, nên kiểm tra:

- Scheme nằm trong **allowlist** mà ứng dụng thực sự hỗ trợ.
- Provider có sẵn, và filesystem/credential cần thiết đã được khởi tạo.
- Cấu trúc URI hợp lệ với provider; không tự parse cú pháp của provider khi chưa cần.
- Đường dẫn sau khi chuyển không vi phạm phạm vi cho phép, quyền truy cập hoặc chính sách bảo mật của ứng dụng.
- Nếu muốn đọc file thật, gọi `Files.newInputStream(...)`, `Files.readString(...)` hoặc API tương ứng và xử lý `IOException`; chỉ có `Path` không đồng nghĩa truy cập thành công.

### Một ví dụ bắt lỗi theo trường hợp

```java
try {
    Path result = Path.of(uri);
    // result chỉ là Path; thao tác I/O thực sự vẫn cần xử lý riêng.
} catch (FileSystemNotFoundException e) {
    // Provider có thể không tìm thấy một filesystem đã mở phù hợp.
} catch (IllegalArgumentException e) {
    // URI không đáp ứng yêu cầu của provider / đầu vào không hợp lệ.
}
```

Đây là **mảnh mã**: cần `java.net.URI`, `java.nio.file.*`; biến `uri` đã tồn tại. Nếu nghiệp vụ dùng provider tùy biến, còn phải hiểu các loại exception khác theo API/triển khai. Không nên nuốt lỗi mà giả vờ URI là một đường dẫn cục bộ.

## 10. File.toURI(), Path.toUri() và URI.toURL()

Các API thường dễ bị trộn lẫn:

| API | Input → output | Dùng khi nào |
| --- | --- | --- |
| `new File(name)` | Tên đường dẫn → `File` | Làm việc với API `java.io.File` |
| `file.toURI()` | `File` → `URI` | Cần URI cho đường dẫn thuộc mô hình File truyền thống |
| `file.toPath()` | `File` → `Path` | Chuyển sang NIO |
| `path.toUri()` | `Path` → `URI` | Provider của Path quyết định dạng URI |
| `Path.of(uri)` | `URI` → `Path` | Chỉ khi provider cho scheme và filesystem phù hợp |
| `uri.toURL()` | `URI` → `URL` | Chuyển thành đối tượng URL nếu scheme/handler hỗ trợ; không tự động đọc |
| `Path.of(uri.toString())` | Chuỗi URI → tên path thô | **Không phải** chuyển URI đúng chuẩn; tránh dùng |

Ví dụ với default filesystem:

```java
File legacy = new File("notes.txt");
URI legacyUri = legacy.toURI();

Path modern = legacy.toPath();
URI modernUri = modern.toUri();
```

Mảnh mã cần `java.io.File`, `java.net.URI`, `java.nio.file.Path`. Hai URI có thể biểu diễn cùng địa chỉ tài nguyên, nhưng không nên xem chuỗi của mọi overload/API luôn đồng nhất trong mọi hoàn cảnh. Khi bạn đang giữ `Path` của một provider phi mặc định (chẳng hạn ZIP), **`Path.toUri()`** phản ánh provider sở hữu Path; việc chuyển ép mọi thứ qua `java.io.File` không phải lúc nào cũng được hỗ trợ (ví dụ `Path.toFile()` có thể ném `UnsupportedOperationException` nếu Path không thuộc filesystem mặc định).

Nếu cần đọc nội dung từ HTTP, `URI.toURL()`/`URL.openStream()` hoặc `HttpClient` là một tầng mạng khác, không tương đương tạo `Path`. Với mã hiện đại, `HttpClient` thường cho phép quản lý timeout, phản hồi HTTP và lỗi rõ ràng hơn.

## 11. Vì sao không nên tự parse hoặc tự ghép URI file?

Giả sử tên tệp chứa khoảng trắng, `#`, `%` hay ký tự Unicode. Việc tự ghép:

```java
String text = "file://" + path.toString();
```

có thể tạo URI sai vì:

- `Path.toString()` dùng separator/syntax của provider; trên Windows có thể chứa `\`, ổ đĩa hoặc UNC, không phù hợp ghép trực tiếp như URL.
- `#` có thể bị hiểu là fragment thay vì phần tên tệp.
- `%` có thể bị hiểu là khởi đầu một escape sequence; tự encode hai lần cũng gây lỗi.
- URI opaque của provider như `jar` có cấu trúc đặc biệt; không thể áp đặt cú pháp `file:`.
- Đường dẫn tương đối không tự trở thành một URI file tuyệt đối đúng quy tắc.

Thay vào đó:

```java
Path path = Path.of("folder", "hello #.txt");
URI uri = path.toUri();
```

Đó là mảnh mã cần import `java.nio.file.Path`, `java.net.URI`. Nếu phải làm việc với thành phần URI HTTP, xây dựng URI theo cú pháp URI/URL, không dùng `Path` để tạo URL web.

### getPath() và getRawPath() không giống nhau

`uri.getPath()` trả phần đường dẫn đã decode các escape URI, còn `uri.getRawPath()` giữ các escape như `%20`. Nếu bạn gọi `URLDecoder.decode(...)` thêm một lần hoặc lấy chuỗi đã decode rồi ghi lại vào URI không đúng cách, có thể gây **double decoding** hoặc thay đổi nghĩa của ký tự đặc biệt như `+`, `%` và `#`.

Khi cần chuyển **file URI thực** sang `Path`, dùng `Path.of(uri)`. Khi chỉ hiển thị thành phần URI, hãy phân biệt raw/decoded theo nhu cầu. Với provider `jar`, `getPath()` có thể không có giá trị vì URI là opaque.

## 12. Bảo mật, dữ liệu không đáng tin và filesystem scope

Một URI hoặc đường dẫn được nhận từ API/người dùng không tự động an toàn. Một số lưu ý:

1. **Không cho phép mọi scheme** nếu ứng dụng chỉ hỗ trợ `file`. Scheme tùy ý có thể kích hoạt provider hoặc cách truy cập không mong muốn.
2. **Không coi `normalize()` là kiểm tra an toàn hoàn chỉnh**: nó chỉ xử lý thành phần cú pháp `.`/`..` và không tự xác nhận đường dẫn thực. Symbolic link có thể thay đổi đích.
3. Nếu bắt buộc giới hạn trong một thư mục gốc, kiểm tra và thao tác theo chính sách phù hợp, xét `toRealPath()`/`Files.isSameFile` khi cần và xử lý ngoại lệ. Cẩn thận race giữa thời điểm kiểm tra và mở.
4. Không dùng `Files.exists(path)` làm bảo đảm file luôn còn đó khi đọc. Filesystem có thể thay đổi tức thời.
5. Không mặc định hệ thống ngoài JVM hiểu cùng provider hoặc thông tin credential. Một Path của provider ảo không nhất thiết có biểu diễn file cục bộ.
6. Một URI có thể là **định danh**, không phải quyền được phép truy cập. Việc chuyển thành Path thành công chưa chứng minh có quyền đọc/ghi.
7. Khi tạo tài nguyên thật, chọn thao tác NIO phù hợp như `Files.createFile`, `Files.newInputStream`, `Files.writeString` với option và ngoại lệ được kiểm soát.

Ví dụ ứng dụng nhận URI bên ngoài chỉ cho phép `file`:

```java
if (!"file".equalsIgnoreCase(uri.getScheme())) {
    throw new IllegalArgumentException("Only file: URIs are supported");
}
Path path = Path.of(uri);
// Tiếp tục kiểm tra phạm vi ứng dụng/đường dẫn thật trước khi mở I/O.
```

Đây chỉ là **kiểm tra scheme**, chưa đủ là rào bảo mật đầy đủ cho mọi đường dẫn file. Muốn hạn chế truy cập trong một thư mục an toàn phải thiết kế logic cấp quyền và chống traversal/symlink/race phù hợp.

## 13. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `toUri()` tạo file | Kết luận tài nguyên đã tồn tại | `toUri()` chỉ tạo URI; dùng `Files` khi cần I/O |
| Dùng `Path.of(uri.toString())` | Chuỗi URI bị hiểu như path thô | `Path.of(uri)` |
| Giả định mọi `Path.toUri()` là `file:` | Sai với ZIP/JAR/custom provider | Hỏi scheme/provider thực |
| Giả định mọi URI hợp lệ đều chuyển thành Path | Thiếu provider/filesystem | Chỉ chuyển URI mà NIO provider hỗ trợ |
| Dùng `Path.of(httpsUri)` để tải file web | Không phải thao tác HTTP | Dùng API mạng rồi lưu xuống Path khác |
| Bỏ qua `FileSystemNotFoundException` với URI JAR | Không tìm thấy ZIP filesystem cần thiết | Mở/đăng ký provider filesystem phù hợp |
| Cho rằng ZIP archive tồn tại là ZIP FS đã mở | URI entry vẫn không round-trip được | Quản lý vòng đời `FileSystem` |
| Gọi `uri.getPath()` với `jar:` | Có thể nhận `null` | Dùng provider, xem opaque URI |
| Tự ghép `"file://" + path` | Sai escaping, slash, Windows path | `path.toUri()` |
| Coi `getPath()` và `getRawPath()` giống nhau | Sai phần percent-encoding | Phân biệt decoded/raw |
| So sánh Path sau round-trip trực tiếp với Path tương đối | Kết luận sai do absolute/relative | So sánh theo hợp đồng provider, dùng `toAbsolutePath()` |
| Nghĩ round-trip cục bộ được đảm bảo trên máy khác | Sai khác hệ điều hành/provider | Chỉ dựa vào bảo đảm trong phạm vi tài liệu xác nhận |
| Đổi Path ZIP sang `toFile()` bất cứ lúc nào | Có thể ném `UnsupportedOperationException` | Dùng Files APIs trực tiếp trên Path |
| Đã có Path là đọc được file | Có thể không tồn tại/không có quyền | Thực hiện I/O, xử lý `IOException` |
| Dùng `normalize()` làm rào chống traversal duy nhất | Bỏ qua symlink/race | Thiết kế kiểm tra bảo mật riêng |

## 14. Tự kiểm tra kiến thức

1. **`Path.toUri()` có tạo file vật lý không?** Không; nó chỉ tạo URI biểu diễn Path theo provider.
2. **URI của Path tương đối trên default provider thường là tương đối hay tuyệt đối?** URI tuyệt đối với scheme `file`, tương ứng đường dẫn tuyệt đối.
3. **`Path.of(uri)` có hỗ trợ URI `https:` mặc định như một file cục bộ?** Không. Đó là thao tác provider của NIO, không phải HTTP download.
4. **Vì sao `Path.of(path.toUri())` không nên so sánh trực tiếp với path tương đối?** Kết quả round-trip của default provider tương ứng `path.toAbsolutePath()`.
5. **Tại sao tên file `hello #.txt` chứa `%23` trong URI?** Vì `#` phải escape để không bị xem là fragment.
6. **Scheme của Path bên trong ZIP FS thường là gì?** `jar` khi dùng JDK ZIP filesystem provider.
7. **Vì sao `Path.of(jarUri)` có thể ném `FileSystemNotFoundException`?** Không tìm thấy ZIP filesystem đang mở/đăng ký tương ứng với URI.
8. **URI `jar:...` có luôn có `getPath()` không?** Không; thường opaque nên `getPath()` trả `null`.
9. **Nếu đã đóng ZIP FileSystem, file archive vật lý có còn không?** Có thể vẫn còn, nhưng Path/URI lookup cho entry cần filesystem được mở lại.
10. **`Path.toFile()` có hoạt động cho ZIP Path không?** Không được bảo đảm; Path ngoài filesystem mặc định có thể ném `UnsupportedOperationException`.
11. **Có thể dùng `Path.of(uri.toString())` thay `Path.of(uri)` không?** Không; hai overload diễn giải đầu vào theo hai mô hình khác nhau.
12. **Làm sao biết URI có thể thành Path?** Kiểm tra scheme/provider, điều kiện filesystem và xử lý lỗi từ `Path.of(URI)` theo hợp đồng provider.
13. **Round-trip có khẳng định file đang có hoặc có quyền truy cập không?** Không.
14. **Dùng API nào để đọc file thực sau khi có Path?** `Files.newInputStream`/`Files.readString` hoặc API phù hợp, với xử lý I/O.
15. **URI/Path ngoại lai có an toàn chỉ vì đã normalize?** Không; còn traversal, symlink, quyền và race.

## Tham khảo API Java 17

- [`Path` — `toUri()`, `toFile()`, `toAbsolutePath()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html).
- [`Path.of(URI)` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#of(java.net.URI)).
- [`Paths.get(URI)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html).
- [`URI` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html).
- [`FileSystemProvider` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html).
- [`FileSystems` — `newFileSystem(...)` / `getFileSystem(...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html).
- [`FileSystemNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemNotFoundException.html).
- [`Files` — thao tác I/O thực sự](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [JDK ZIP File System Provider](https://docs.oracle.com/en/java/javase/17/docs/specs/zipfs.html).

**Kết luận:** `Path.toUri()` là chiếc cầu từ một đường dẫn thuộc **một FileSystem cụ thể** sang URI do provider định nghĩa. `Path.of(URI)` là yêu cầu **provider và FileSystem tương ứng** chuyển URI trở lại thành Path, không phải công cụ chuyển mọi URI thành file. Với default `file` provider có bảo đảm round-trip trong cùng JVM; với `jar`, ZIP hoặc provider bên thứ ba, phải xét scheme, cách mở filesystem, vòng đời và hợp đồng riêng của provider.