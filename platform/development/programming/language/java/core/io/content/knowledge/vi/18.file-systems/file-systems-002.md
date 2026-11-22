# Default file system và các provider được cài đặt trong Java NIO.2

## 1. Vì sao Java có `FileSystem` và `FileSystemProvider`?

Khi làm việc với tệp bằng `java.nio.file`, ứng dụng thường bắt đầu từ hệ thống tệp sẵn có của máy: ổ đĩa Windows hoặc các thư mục trong hệ thống Unix/Linux/macOS. Java gọi đó là **default file system** (hệ thống tệp mặc định). Tuy nhiên, NIO.2 không giới hạn đường dẫn vào hệ thống tệp của hệ điều hành: một tệp ZIP có thể được mở thành hệ thống tệp riêng, hoặc một thư viện có thể cung cấp hệ thống tệp ảo.

Ba khái niệm liên kết với nhau:

- **`FileSystemProvider`** (`java.nio.file.spi.FileSystemProvider`): nhà cung cấp triển khai các thao tác với hệ thống tệp, đường dẫn, kênh tệp, thuộc tính, v.v. Mỗi provider có một scheme URI, ví dụ `file` hoặc `jar`.
- **`FileSystem`** (`java.nio.file.FileSystem`): một thể hiện hệ thống tệp được provider cung cấp. Một provider có thể quản lý nhiều thể hiện `FileSystem`.
- **`Path`** (`java.nio.file.Path`): một đường dẫn gắn với chính `FileSystem` đã tạo ra nó. Gọi `path.getFileSystem()` để kiểm tra nơi đường dẫn thuộc về.

~~~text
FileSystemProvider có scheme "file" (default provider)
          └── default FileSystem
                  ├── Path "data/input.txt"
                  └── Path "logs/app.log"

FileSystemProvider có scheme "jar" (ZIP FS provider, khi có)
          ├── FileSystem cho archive-a.zip
          │       └── Path "/docs/a.txt"
          └── FileSystem cho archive-b.zip
                  └── Path "/docs/b.txt"
~~~

Sơ đồ là minh họa quan hệ, không cam kết máy nào cũng có ZIP provider. **Provider được cài đặt không đồng nghĩa với một `FileSystem` cụ thể đã được mở**. Ví dụ provider `jar` có mặt nhưng ứng dụng chưa mở ZIP nào.

## 2. Default file system: cách lấy và các bảo đảm cơ bản

Các API trung tâm:

~~~java
FileSystem defaultFs = FileSystems.getDefault();
FileSystemProvider provider = defaultFs.provider();

Path file = Path.of("data", "input.txt");
Path another = Paths.get("data", "input.txt");
~~~

Đây là **các đoạn lệnh minh họa**, cần đặt trong lớp/phương thức Java và import `java.nio.file.*`, `java.nio.file.spi.FileSystemProvider` khi sử dụng.

`FileSystems.getDefault()` trả về hệ thống tệp mặc định của JVM. Trên JDK chạy thông thường, nó đại diện cho môi trường hệ thống tệp máy đang chạy. `Path.of(String, String...)` và `Paths.get(String, String...)` tạo đường dẫn trên hệ thống tệp mặc định; `Paths.get` là API cũ hơn và thường có thể thay bằng `Path.of` từ Java 11.

Các đặc điểm cần nhớ:

1. `FileSystems.getDefault()` trả về cùng hệ thống tệp mặc định cho tiến trình; dùng phép đồng nhất `==` khi kiểm tra hai biến có trỏ tới cùng đối tượng.
2. Provider của default filesystem sử dụng scheme **`file`**. Vì vậy `defaultFs.provider().getScheme()` trả `"file"`.
3. `Path.of("relative.txt")` chỉ tạo đối tượng đường dẫn tương đối. Nó **không** kiểm tra tệp tồn tại và **không** ghi tệp.
4. Hệ thống tệp mặc định không được quản lý theo vòng đời giống hệ thống tệp mở thêm. Không tự đóng `FileSystems.getDefault()`. Trong triển khai mặc định, `close()` không được hỗ trợ.
5. `defaultFs.getSeparator()`, `defaultFs.getRootDirectories()` và quy tắc tên có thể khác giữa các hệ điều hành hoặc provider. Đừng giả định `/`, ký tự ổ đĩa hay tính phân biệt chữ hoa/chữ thường giống nhau ở mọi máy.

**Lưu ý cấu hình nâng cao:** JDK hỗ trợ property khởi động `java.nio.file.spi.DefaultFileSystemProvider` để yêu cầu provider tùy chỉnh bọc (wrap) default provider. Đây là lựa chọn cấu hình trước khi khởi tạo default filesystem, không phải thao tác thay đổi tùy ý trong lúc ứng dụng đang dùng các `Path`. Vì vậy, đừng giả định class thực tế của default provider luôn cố định trên mọi runtime; hãy truy vấn qua API.

## 3. Các provider được cài đặt: `installedProviders()`

Danh sách provider nhìn thấy trong môi trường chạy hiện tại được lấy qua:

~~~java
List<FileSystemProvider> providers =
        FileSystemProvider.installedProviders();
~~~

`installedProviders()` trả một danh sách provider đã được cài đặt/khám phá trong runtime. **Phần tử đầu tiên là default provider**; các provider khác phụ thuộc JDK, module runtime và thư viện bổ sung. Danh sách này được nạp và lưu để sử dụng lại, nên không nên hiểu lời gọi như thao tác quét lại mọi JAR tùy ý trong mỗi lần chạy.

Một vài scheme thường gặp:

| Scheme | Ví dụ ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `file` | Hệ thống tệp mặc định của hệ điều hành | Có trong danh sách, đứng đầu |
| `jar` | ZIP/JAR filesystem (thường do module `jdk.zipfs` cung cấp) | Có thể thiếu trong runtime được cắt gọn |
| `jrt` | Hệ thống tệp ảnh module runtime của Java | Tùy khả năng của runtime/JDK, không phải ổ đĩa thông thường |
| Scheme tùy chỉnh | Provider do thư viện/ứng dụng triển khai | Chỉ dùng được khi provider hiện diện và được cơ chế nạp phù hợp tìm thấy |

Tên scheme có thể được in bằng `provider.getScheme()`. **Scheme là loại địa chỉ tài nguyên, không phải đường dẫn hay instance filesystem**. Ví dụ hai ZIP có thể dùng chung provider có scheme `jar` nhưng vẫn là hai `FileSystem` khác nhau.

Không giả định rằng mọi máy đều có đúng ba scheme `file`, `jar`, `jrt`; chương trình chỉ nên dựa trên những provider đã tìm thấy trong runtime đang chạy.

### Ví dụ Java 17+ chạy độc lập: khám phá provider

Lưu vào tệp `InstalledProvidersDemo.java`:

~~~java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.spi.FileSystemProvider;
import java.util.List;

public class InstalledProvidersDemo {
    public static void main(String[] args) {
        FileSystem defaultFs = FileSystems.getDefault();
        List<FileSystemProvider> providers =
                FileSystemProvider.installedProviders();

        System.out.println("Default scheme: "
                + defaultFs.provider().getScheme());
        System.out.println("Path.of uses default: "
                + (Path.of("sample.txt").getFileSystem() == defaultFs));
        System.out.println("Default provider is first: "
                + (providers.get(0) == defaultFs.provider()));
        System.out.println("Provider count >= 1: "
                + (providers.size() >= 1));

        System.out.println("Installed schemes:");
        for (FileSystemProvider provider : providers) {
            System.out.println("  " + provider.getScheme());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InstalledProvidersDemo.java
java InstalledProvidersDemo
~~~

Phần đầu của stdout ổn định trên JDK tuân theo hợp đồng API:

~~~text
Default scheme: file
Path.of uses default: true
Default provider is first: true
Provider count >= 1: true
Installed schemes:
~~~

**Sau dòng `Installed schemes:`, số dòng và tên scheme phụ thuộc runtime.** Scheme `file` đứng đầu danh sách; một JDK đầy đủ thường có thêm `jar` hoặc `jrt`. Vì danh sách biến thiên, không có một stdout đầy đủ cố định đúng cho mọi môi trường.

Phân tích kết quả:

- `Path.of("sample.txt")` lấy provider từ default filesystem, nên phép so sánh đối tượng `FileSystem` in `true`; tệp `sample.txt` không cần tồn tại.
- `installedProviders().get(0)` là default provider theo hợp đồng API; điều này **không** chứng minh chỉ có một provider.
- Vòng lặp in các scheme đang có thật; không nên viết logic kiểm tra bằng cách so với một danh sách cố định.

## 4. Provider được nạp như thế nào?

NIO.2 dùng cơ chế **service provider** để cho phép triển khai bổ sung. Một provider tuân theo hợp đồng `java.nio.file.spi.FileSystemProvider`; môi trường Java có thể khám phá những triển khai đã được đóng gói/khai báo hợp lệ khi provider được cài đặt.

Ở mức ứng dụng, luồng ý tưởng là:

1. Provider mặc định phục vụ hệ thống tệp của tiến trình.
2. Runtime khám phá các provider được cài đặt bổ sung bằng cơ chế nạp dịch vụ của Java và các provider có sẵn trong JDK.
3. `FileSystemProvider.installedProviders()` cho phép liệt kê các provider đó.
4. Khi yêu cầu tạo/mở `FileSystem` theo URI hay theo tài nguyên, API chọn provider có khả năng xử lý.
5. Provider tạo/trả về `FileSystem`; từ hệ thống tệp này mới tạo ra các `Path`.

Điều kiện **có class provider trong một JAR** chưa đủ để khẳng định `installedProviders()` nhìn thấy nó: còn phụ thuộc khai báo dịch vụ, module, class loader và cách khởi động runtime. Với thư viện dùng Java Platform Module System, provider có thể được khai báo bằng `provides ... with ...`; với JAR theo cơ chế dịch vụ truyền thống, thông tin provider nằm trong `META-INF/services/java.nio.file.spi.FileSystemProvider`. Nếu module runtime được dựng bằng `jlink`, danh sách provider có thể khác JDK phát triển.

Ngoài các provider được cài đặt mà danh sách chung nhìn thấy, một số overload của `FileSystems.newFileSystem` hỗ trợ lựa chọn provider thông qua class loader truyền vào. Vì vậy, danh sách cài đặt chung không phải bằng chứng rằng **mọi** triển khai provider có thể nạp theo mọi class loader đều đã được liệt kê.

### Có thể gọi thẳng `newFileSystem` của provider không?

Có, đối tượng `FileSystemProvider` có các phương thức SPI như `newFileSystem(URI, Map<String, ?>)`, `getFileSystem(URI)` và `getPath(URI)`. Tuy nhiên, code ứng dụng thông thường nên ưu tiên lớp facade `FileSystems`/`Path`/`Files` vì chúng tập trung việc lựa chọn provider và thao tác với đường dẫn.

Không nên tự khởi tạo `FileSystemProvider` bằng reflection chỉ vì thấy class trên classpath: hành vi và cấu hình phụ thuộc triển khai, không phải mọi provider được thiết kế để tạo trực tiếp như object ứng dụng.

## 5. Khi nào Java chọn default provider, khi nào chọn provider khác?

| Biểu thức | Cách chọn hệ thống tệp/provider | Mục đích |
| --- | --- | --- |
| `FileSystems.getDefault()` | Default filesystem của JVM | Lấy hệ thống tệp mặc định |
| `Path.of("folder/file.txt")` | Default filesystem | Tạo đường dẫn từ chuỗi trong hệ thống tệp mặc định |
| `FileSystems.getDefault().getPath("x.txt")` | Chính default filesystem | Tạo đường dẫn thuộc `FileSystem` đã biết |
| `Path.of(uri)` | Provider hỗ trợ scheme của URI | Lấy đường dẫn qua URI; provider có thể yêu cầu `FileSystem` đã được mở |
| `FileSystems.getFileSystem(uri)` | Provider theo scheme URI | Truy xuất một filesystem đã tồn tại/được đăng ký; **không** dùng để tạo mới |
| `FileSystems.newFileSystem(uri, env)` | Provider thích hợp theo scheme URI | Tạo/mở filesystem mới theo hợp đồng provider |
| `existingFs.getPath("entry")` | Chính `existingFs` | Tạo đường dẫn trong hệ thống tệp đã có |

Một scheme được cài đặt **không bảo đảm** gọi `getFileSystem(uri)` thành công. Ví dụ với filesystem ZIP, trước tiên bạn có thể phải tạo/mở instance bằng `newFileSystem`. `getFileSystem` có thể ném `FileSystemNotFoundException` nếu chưa tồn tại filesystem tương ứng; `newFileSystem` có thể ném `ProviderNotFoundException` khi không có provider xử lý loại URI được yêu cầu.

`Path.of(uri)` cũng có thể thất bại nếu provider thích hợp chưa có filesystem sẵn sàng; đó là lý do khi đã có `FileSystem`, dùng `fs.getPath(...)` là cách trực tiếp và rõ ràng nhất.

**Không đổi `Path` sang chuỗi rồi gọi `Path.of(String)` nếu muốn giữ provider gốc.** Cách này luôn định tuyến tên mới vào default filesystem và có thể làm mất ý nghĩa khi nguồn thuộc ZIP/JAR hoặc filesystem ảo.

## 6. Thực hành với `jar` provider: cài đặt và mở một filesystem là hai bước khác nhau

Trên JDK đầy đủ có `jdk.zipfs`, provider có scheme `jar` giúp mở tệp ZIP/JAR như một filesystem. Đoạn chương trình dưới đây tự kiểm tra provider `jar` trước khi tạo ZIP, vì runtime Java thu gọn có thể không cung cấp provider này.

Lưu thành `ZipProviderDemo.java`:

~~~java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.spi.FileSystemProvider;
import java.util.Map;

public class ZipProviderDemo {
    public static void main(String[] args) throws Exception {
        boolean jarInstalled = FileSystemProvider.installedProviders()
                .stream()
                .anyMatch(provider ->
                        provider.getScheme().equalsIgnoreCase("jar"));

        if (!jarInstalled) {
            System.out.println("ZIP provider unavailable");
            return;
        }

        Path zipFile = Files.createTempFile("nio2-demo-", ".zip");
        Files.delete(zipFile); // Để provider tạo ZIP hợp lệ từ đầu.

        try {
            URI zipUri = URI.create("jar:" + zipFile.toUri());

            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                Path entry = zipFs.getPath("/hello.txt");
                Files.writeString(entry, "Hello ZIP");

                System.out.println("ZIP scheme: "
                        + zipFs.provider().getScheme());
                System.out.println("Same as default: "
                        + (zipFs == FileSystems.getDefault()));
                System.out.println("Content: " + Files.readString(entry));
            }
        } finally {
            Files.deleteIfExists(zipFile);
        }
    }
}
~~~

Chạy:

~~~bash
javac ZipProviderDemo.java
java ZipProviderDemo
~~~

Nếu `jar` provider phù hợp đã được cài đặt và môi trường cho phép tạo/xóa tệp tạm, stdout là:

~~~text
ZIP scheme: jar
Same as default: false
Content: Hello ZIP
~~~

Nếu không có `jar` provider, stdout là:

~~~text
ZIP provider unavailable
~~~

Đọc kỹ cơ chế:

1. `installedProviders()` kiểm tra provider *đã cài đặt*. Kiểm tra này không mở ZIP.
2. `Files.createTempFile` rồi `Files.delete` bảo đảm ta có một vị trí tạm chưa chứa ZIP, trong khi `"create" = "true"` bảo ZIP provider tạo lưu trữ mới.
3. `FileSystems.newFileSystem(zipUri, Map.of("create", "true"))` giao URI scheme `jar` cho ZIP filesystem provider; đây là lúc instance `FileSystem` được mở.
4. `zipFs.getPath("/hello.txt")` tạo `Path` bên trong ZIP, không phải tệp `/hello.txt` trên filesystem mặc định.
5. `Files.writeString` và `Files.readString` định tuyến I/O qua provider của `Path`.
6. `try-with-resources` đóng ZIP filesystem và ghi hoàn tất nội dung lưu trữ; `finally` xóa ZIP tạm kể cả khi có lỗi.

Tệp ZIP bên ngoài (`zipFile`) là `Path` thuộc default filesystem, trong khi entry (`entry`) là `Path` thuộc ZIP filesystem. Cả hai cùng tham gia một ví dụ nhưng **không** thuộc cùng filesystem.

Nếu trình chạy bị hạn chế quyền ghi tệp tạm, thiếu ZIP module, hoặc provider hoạt động không như JDK ZIP thông thường, chương trình có thể ném ngoại lệ. Xử lý ngoại lệ thực tế cần tùy môi trường.

## 7. Quan hệ giữa URI scheme, provider và filesystem

URI có thể mang dấu hiệu chọn provider:

~~~text
file:///home/user/data.txt
jar:file:///home/user/archive.zip!/docs/readme.txt
jrt:/java.base/java/lang/String.class
~~~

Đây là các **ví dụ hình dạng URI**, không phải những đường dẫn chắc chắn tồn tại trên máy đang chạy.

- `file:` thường dùng default provider, nhưng URI phải hợp lệ theo quy tắc đường dẫn hệ điều hành.
- `jar:` mô tả tài nguyên liên quan đến archive ZIP/JAR, thường dùng ZIP provider. Phần trước `!` xác định archive; phần sau xác định entry.
- `jrt:` biểu diễn tài nguyên của Java runtime image qua JRT filesystem khi provider được cung cấp.

Scheme trả lời **provider nào có khả năng xử lý**, còn `FileSystem` trả lời **instance nào đang chứa đường dẫn**. Cần phân biệt:

~~~text
Scheme "jar"
    │
    ▼
ZIP FileSystemProvider
    ├── opened archive A → FileSystem A → Path "/docs/readme.txt"
    └── opened archive B → FileSystem B → Path "/docs/readme.txt"
~~~

Hai `Path` có cùng cách in chuỗi nhưng khác đối tượng `FileSystem` và có thể chứa dữ liệu hoàn toàn khác nhau. Vì vậy, kiểm tra `path.getFileSystem()` và `path.getFileSystem().provider()` để hiểu nguồn gốc.

**Không nối chuỗi `"jar:"` hay đường dẫn filesystem theo quy tắc chung một cách tùy tiện.** Việc xây URI cần chú ý encode ký tự đặc biệt, separator và cú pháp provider; `zipFile.toUri()` trong ví dụ cung cấp URI đã escape hợp lệ của archive trên hệ thống tệp mặc định.

## 8. Những lỗi phổ biến và cách xử lý

### Giả định provider có mặt trên mọi JDK

**Sai:** mặc định cho rằng `jar`, `jrt` hoặc một provider bên thứ ba luôn được cài đặt.

**Đúng:** kiểm tra `FileSystemProvider.installedProviders()` hoặc xử lý ngoại lệ `ProviderNotFoundException` khi tạo filesystem, đồng thời làm rõ yêu cầu runtime/module của ứng dụng.

### Nhầm cài đặt provider với mở filesystem

**Sai:** thấy `jar` trong danh sách và lập tức gọi `FileSystems.getFileSystem(uri)` để lấy archive chưa mở.

**Đúng:** dùng `FileSystems.newFileSystem(...)` theo hợp đồng provider khi cần mở mới. `getFileSystem(uri)` chỉ thích hợp khi filesystem tương ứng đã có; trường hợp đã được tạo có thể cần đóng đúng lúc và tránh mở trùng.

### Dùng `Path.of(String)` cho đường dẫn trong ZIP

**Sai:**

~~~java
Path entry = Path.of("/docs/hello.txt");
~~~

Đây là đường dẫn trên default filesystem, bất kể ứng dụng đang có một `zipFs`.

**Đúng** (khi `zipFs` đã được mở):

~~~java
Path entry = zipFs.getPath("/docs/hello.txt");
~~~

Hai đoạn chỉ minh họa dòng lệnh, không phải chương trình độc lập.

### Quên vòng đời hệ thống tệp mở thêm

Đường dẫn `Path` vẫn có thể tồn tại như object sau khi `FileSystem` bị đóng, nhưng thao tác I/O trên nó có thể ném `ClosedFileSystemException`. Với filesystem mở mới, dùng `try-with-resources` và bảo đảm sử dụng `Path` khi filesystem còn mở. Ngược lại, không đóng default filesystem như tài nguyên tạm.

### Trộn `Path` thuộc provider khác trong phép xử lý tên

`resolve(Path)` hoặc `relativize(Path)` không phải API chuyển file giữa filesystem. Một số triển khai ném `ProviderMismatchException` nếu kết hợp đối số từ provider không tương thích. Khi cần truyền dữ liệu, cân nhắc `Files.copy(source, target)` với hai đường dẫn đã tạo đúng filesystem đích/nguồn, và xử lý `IOException`, khả năng/provider hỗ trợ.

### Tưởng `installedProviders()` là bản đồ tất cả ổ đĩa và archive

API trả **các loại provider**, không liệt kê ổ đĩa, mount point, ZIP đang mở, file tồn tại hay tài nguyên trong mỗi hệ thống tệp. Để khảo sát thư mục root của filesystem cụ thể, dùng `fileSystem.getRootDirectories()`; để kiểm tra file, dùng các API `Files.*` trên `Path`.

## 9. Bài tập áp dụng

1. Chạy `InstalledProvidersDemo` trong hai môi trường Java khác nhau (ví dụ JDK đầy đủ và runtime được đóng gói). So sánh các scheme ở cuối stdout; giải thích tại sao số lượng provider có thể thay đổi.
2. Thay `Path.of("sample.txt")` bằng `FileSystems.getDefault().getPath("sample.txt")` và kiểm tra quan hệ `getFileSystem() == FileSystems.getDefault()`.
3. Trong `ZipProviderDemo`, in `zipFile.getFileSystem().provider().getScheme()` và `entry.getFileSystem().provider().getScheme()` trước khi đóng ZIP. Dự đoán kết quả (`file` và `jar` nếu provider có mặt).
4. Thử dùng `zipFs.getPath("another.txt")` để tạo entry thứ hai, rồi đọc lại bằng `Files.readString`. Kiểm tra khi nào cần tạo thư mục cha nếu entry nằm trong thư mục con.
5. Giải thích vì sao `installedProviders()` trả về `jar` vẫn không đủ để kết luận `FileSystems.getFileSystem(uri)` sẽ trả filesystem của ZIP chưa từng được mở.

## 10. Ghi nhớ

- `FileSystems.getDefault()` cung cấp **một hệ thống tệp mặc định**; các `Path` tạo từ chuỗi bằng `Path.of` thuộc hệ thống đó.
- `FileSystemProvider.installedProviders()` liệt kê **các provider được cài đặt** trong runtime; default provider xuất hiện đầu danh sách, các provider khác có thể khác nhau giữa môi trường.
- **Provider → FileSystem → Path** là quan hệ gốc. Scheme nhận diện loại provider, `FileSystem` là instance, còn `Path` thuộc một instance cụ thể.
- `FileSystems.newFileSystem(...)` dùng để mở/tạo filesystem khi được provider hỗ trợ; `getFileSystem(...)` dùng để tìm filesystem đã có.
- Đừng mặc định mọi đường dẫn là đường dẫn ổ đĩa; giữ nguyên `Path` cùng `FileSystem` của nó, kiểm tra provider khi cần và đóng filesystem mở thêm đúng vòng đời.
