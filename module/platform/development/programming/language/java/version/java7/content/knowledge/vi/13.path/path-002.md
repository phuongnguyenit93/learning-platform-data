# Tạo đường dẫn từ các thành phần hoặc URI với java.nio.file.Path

**Chủ đề:** Java 7 — Path  
**Bài học:** Tạo đường dẫn từ các thành phần hoặc URI  
**Phiên bản thực hành:** Java 17+; dùng API NIO.2 hiện hành. `Path` và `Paths.get(...)` có từ Java 7; `Path.of(...)` là factory hiện đại từ Java 11. Các ví dụ độc lập bên dưới dùng `Path.of` để nhất quán với Java 17+.

Một đường dẫn file không chỉ là một chuỗi có dấu gạch chéo. Nó biểu diễn một vị trí trong **file system cụ thể**, có quy tắc về root, dấu phân tách, tên thành phần, cách biểu diễn đường dẫn tương đối/tuyệt đối và cách chuyển đổi thành URI.

Bài này tập trung vào hai nguồn tạo `Path`:

1. **Các thành phần đường dẫn** (*path components*): khi bạn có tên thư mục, tên tệp hoặc một đường dẫn dưới thư mục gốc.
2. **URI**: khi dữ liệu đã được biểu diễn theo cú pháp URI, ví dụ `file:///...` hoặc URI của một file system provider.

**Quy tắc quan trọng:** `Path.of("...")` **không phải** phép phân tích URI. `Path.of(URI)` **không phải** cách tải một URL bất kỳ. Chọn đúng overload theo nguồn đầu vào và file system đang sử dụng.

## 1. Path là gì?

`java.nio.file.Path` là interface mô hình hóa một đường dẫn trong file system. `Path` có thể **tương đối** hoặc **tuyệt đối**, có thể chứa các thành phần `.` và `..`, và có thể thuộc **default file system** hoặc một provider khác (ví dụ ZIP/JAR file system).

Một `Path` mới được tạo **không chứng minh file hay thư mục đã tồn tại**. Phân tích tên đường dẫn và thực hiện I/O là hai thao tác khác nhau.

Ví dụ:

```java
Path report = Path.of("reports", "2026", "summary.csv");
```

Đây là một đoạn mã trong phương thức với `import java.nio.file.Path;`. Nó chỉ tạo một object đường dẫn tương đối. Chưa có thư mục `reports`, chưa có tệp `summary.csv` và cũng chưa gọi `Files.createDirectories` hay `Files.writeString`.

**Khi cần kiểm tra/tạo dữ liệu thật**, dùng các API như `Files.isRegularFile`, `Files.createDirectories`, `Files.readString`, `Files.writeString` theo contract và quyền truy cập. Đừng hiểu nhầm việc tạo `Path` với việc mở file.

### 1.1. Vì sao không nên tự nối String?

Một cách dễ sai:

```java
// Không nên tự ghép dấu phân tách khi đang mô hình hóa đường dẫn:
String file = base + "/" + folder + "/" + name;
```

Đây là code minh họa. Ngay cả khi dấu `/` có thể được default provider chấp nhận trên nhiều nền tảng, phép nối String có thể gây lỗi khi `base` đã có dấu phân tách cuối, `folder` rỗng hoặc một thành phần là đường dẫn tuyệt đối.

Nên viết:

```java
Path file = base.resolve(folder).resolve(name);
```

hoặc:

```java
Path file = Path.of(baseText, folder, name);
```

Các đoạn này yêu cầu biến và import hợp lệ trong ứng dụng. `Path` biết cách xử lý cú pháp theo **file system provider**, không buộc mã nguồn phải tự chèn `"/"` hoặc `"\\"` cho mọi máy.

**Không đồng nhất “nối đúng cú pháp” với “an toàn trước dữ liệu không tin cậy”**. Nếu tên file đến từ client, `Path.resolve` không tự chặn `..`, đường dẫn tuyệt đối hoặc symbolic link. Phần 10 giải thích rõ hơn.

## 2. Tạo Path từ các thành phần

Hai factory liên quan:

```java
// Từ Java 11:
Path a = Path.of("data", "reports", "summary.csv");

// API có từ Java 7, vẫn sử dụng được:
Path b = Paths.get("data", "reports", "summary.csv");
```

Đây là đoạn minh họa, cần import `Path` và `Paths`. Với default file system, hai cách tạo có ý nghĩa tương đương. `Paths.get(...)` **không phải API bị loại bỏ**; `Path.of(...)` thường ngắn và trực tiếp hơn trên Java 11+.

Chữ ký cần nhớ:

```java
static Path Path.of(String first, String... more);
static Path Path.of(URI uri);

static Path Paths.get(String first, String... more);
static Path Paths.get(URI uri);
```

Đây là **chữ ký rút gọn để học**; các overload thực sự do JavaDoc định nghĩa. Chữ ký nhận `String...` diễn giải theo **cú pháp đường dẫn** của default file system; chữ ký nhận `URI` diễn giải theo **scheme/provider** của URI.

### 2.1. Đường dẫn tương đối có nhiều thành phần

```java
Path relative = Path.of("project", "images", "logo.png");
```

- `project` là thành phần đầu.
- `images` là thư mục dưới `project`.
- `logo.png` là thành phần cuối.
- Không có root tường minh, nên đây là **đường dẫn tương đối** trong default file system.

Trên Unix, cách hiển thị thường là `project/images/logo.png`; trên Windows, thường là `project\images\logo.png`. **Đừng lấy `toString()` làm một wire format cố định** nếu dữ liệu cần được truyền giữa các nền tảng khác nhau.

Nếu dữ liệu đến từ cấu hình, có thể lưu các thành phần riêng hoặc dùng định dạng đã thống nhất. Không suy từ một chuỗi `"/"` hay `"\\"` rằng ứng dụng đang chạy trên hệ điều hành tương ứng.

### 2.2. Ví dụ chạy độc lập: các thành phần, resolve và Paths.get

Tạo `PathComponentsDemo.java`:

```java
import java.nio.file.Path;
import java.nio.file.Paths;

public class PathComponentsDemo {
    static String display(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path parts = Path.of(
                "data", "reports", "2026", "summary.csv");
        Path resolved = Path.of("data")
                .resolve("reports")
                .resolve("2026")
                .resolve("summary.csv");
        Path otherFactory = Paths.get(
                "data", "reports", "2026", "summary.csv");

        System.out.println("path=" + display(parts));
        System.out.println(
                "same-resolve=" + parts.equals(resolved));
        System.out.println(
                "same-paths-get="
                + parts.equals(otherFactory));
        System.out.println(
                "relative=" + !parts.isAbsolute());
        System.out.println(
                "parent=" + display(parts.getParent()));
        System.out.println(
                "filename=" + parts.getFileName());
        System.out.println(
                "names=" + parts.getNameCount());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PathComponentsDemo.java
java PathComponentsDemo
```

**stdout chính xác:**

```text
path=data/reports/2026/summary.csv
same-resolve=true
same-paths-get=true
relative=true
parent=data/reports/2026
filename=summary.csv
names=4
```

Hàm `display` chỉ chuẩn hóa dấu phân tách **khi in kết quả minh họa** để stdout giống nhau trên Windows và Unix. Nó **không** thay đổi object `Path`. Đừng làm `path.toString().replace(...)` để sửa quyền truy cập, làm rõ nghĩa URI hoặc tự xây dựng đường dẫn bảo mật.

Với các thành phần do chương trình kiểm soát, `Path.of(first, more)` thường dễ đọc hơn nối String. Khi đã có `Path base`, `base.resolve(other)` đặc biệt hữu ích.

### 2.3. Tên file và các thành phần có dấu cách/Unicode

Các chuỗi như `"báo cáo 2026.txt"` hoặc `"ảnh đại diện.png"` là tên thành phần đường dẫn, **không phải URI**. Bạn có thể viết:

```java
Path document = Path.of(
        "documents", "báo cáo 2026.txt");
```

`Path.of(String...)` không yêu cầu tự mã hóa khoảng trắng thành `%20`. Percent-encoding thuộc **cú pháp URI**, không phải cú pháp đường dẫn thông thường.

Không mặc định tất cả ký tự Unicode đều được chấp nhận trên mọi file system: provider và hệ điều hành có thể hạn chế tên, dấu phân tách, ký tự điều khiển hoặc tên dành riêng. `Path.of(...)` có thể ném `InvalidPathException` khi tên không hợp lệ; tạo tệp vẫn có thể thất bại vì quyền truy cập, giới hạn file system hoặc file đã tồn tại.

## 3. resolve, resolveSibling, getParent và relativize

Khi đã có `Path`, các method thường gặp:

| Method | Mục đích | Điểm cần hiểu |
| --- | --- | --- |
| `base.resolve(other)` | Tạo đường dẫn bằng cách kết hợp base và other | Với đường dẫn tuyệt đối, quy tắc resolve có thể khiến đường dẫn đầu vào thay thế base; đừng dùng như kiểm tra an toàn |
| `path.resolveSibling(other)` | Thay thành phần cuối bằng đường dẫn tương ứng dưới parent | Hữu ích khi tạo tên file ngang cấp |
| `path.getParent()` | Lấy parent theo cú pháp | Có thể là `null` với path chỉ có một tên hoặc root |
| `path.getFileName()` | Lấy thành phần tên cuối | Có thể `null` với root |
| `a.relativize(b)` | Tìm đường dẫn từ `a` đến `b` theo quan hệ đường dẫn | Cần hai path tương thích, thường cùng loại absolute/relative và cùng provider |
| `path.startsWith(base)` | Kiểm tra prefix theo **thành phần Path** | Không phải so sánh prefix String; chưa chứng minh file thật không thoát qua symlink |

**Không dùng `String.startsWith` để kiểm tra root.** Ví dụ `"/data/safe-extra"` bắt đầu bằng chuỗi `"/data/safe"` nhưng không thuộc thư mục `"/data/safe"`. `Path.startsWith` xét thành phần đường dẫn theo quy tắc provider, tránh nhầm lẫn kiểu prefix chữ cái này; dù vậy, `Path.startsWith` **vẫn chưa giải quyết symbolic link và race**.

### 3.1. Ví dụ chạy độc lập: quan hệ giữa các Path

Tạo `PathLexicalDemo.java`:

```java
import java.nio.file.Path;

public class PathLexicalDemo {
    static String show(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path messy = Path.of(
                "reports", "draft", "..", "final",
                ".", "summary.txt");
        Path normalized = messy.normalize();

        System.out.println(
                "normalized=" + show(normalized));
        System.out.println(
                "file-name=" + normalized.getFileName());
        System.out.println(
                "name-count=" + normalized.getNameCount());

        Path incoming = Path.of("reports", "incoming");
        System.out.println(
                "sibling="
                + show(incoming.resolveSibling("processed")));

        Path base = Path.of("reports");
        Path target = Path.of(
                "reports", "final", "summary.txt");
        System.out.println(
                "relative="
                + show(base.relativize(target)));
        System.out.println(
                "starts-with-reports="
                + normalized.startsWith(base));
        System.out.println(
                "absolute="
                + normalized.toAbsolutePath().isAbsolute());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PathLexicalDemo.java
java PathLexicalDemo
```

```text
normalized=reports/final/summary.txt
file-name=summary.txt
name-count=3
sibling=reports/processed
relative=final/summary.txt
starts-with-reports=true
absolute=true
```

`normalize()` loại bỏ những phần tử `.` và xử lý `..` khi có thể theo **cú pháp**, không phải thao tác kiểm tra tệp thật. `toAbsolutePath()` đưa đường dẫn về dạng tuyệt đối theo file system và thư mục làm việc, nhưng không đồng nghĩa với `toRealPath()`.

Ví dụ không cần có thư mục `reports` thật để tính `normalize()`, `getFileName()` hay `relativize()`. Việc tạo object/path không thực hiện I/O chỉ để tính những kết quả đó.

## 4. Tương đối, tuyệt đối và vị trí làm việc của chương trình

Đường dẫn tương đối như:

```java
Path file = Path.of("data", "notes.txt");
```

được giải quyết theo **working directory** của ứng dụng khi các API I/O cần vị trí thực tế. Nó **không nhất thiết** là thư mục chứa file `.java`, thư mục lưu `.class` hoặc đường dẫn repo mà bạn nhìn thấy trên IDE.

Ví dụ một process được khởi chạy từ thư mục khác sẽ có thể nhìn vào tệp khác khi dùng cùng đường dẫn tương đối.

Các method cần phân biệt:

- `isAbsolute()`: hỏi path có root theo provider hay không.
- `toAbsolutePath()`: tạo đường dẫn tuyệt đối theo working directory và quy tắc provider; không tự chứng minh tệp tồn tại.
- `normalize()`: xử lý `.`/`..` theo cú pháp; không truy cập file system.
- `toRealPath()`: truy cập file system để lấy đường dẫn thực theo option, mặc định thường cần mục tiêu tồn tại và xử lý symbolic links theo contract.
- `Files.exists(path)`: kiểm tra sự tồn tại theo file system, nhưng `false` cũng có thể xuất hiện khi không xác định được trạng thái do hạn chế truy cập; không dùng riêng nó để xác minh an toàn hay thiết kế lock.

Một đường dẫn có thể **tồn tại hợp lệ về cú pháp** nhưng tệp chưa tồn tại. Điều này hoàn toàn bình thường khi bạn muốn tạo file mới:

```java
Path output = Path.of("exports", "new.csv");
Files.createDirectories(output.getParent());
Files.writeString(output, "id,name\n",
                  StandardCharsets.UTF_8);
```

Đây là **mã minh họa**, cần import `Files`, `Path`, `StandardCharsets`, xử lý `IOException` và phải chọn root thuộc quyền sở hữu ứng dụng. `Files.createDirectories` tạo các thư mục cha theo yêu cầu; bản thân `Path.of` không làm công việc đó.

### 4.1. Đường dẫn absolute làm thay đổi ngữ nghĩa resolve

Khi `other` là đường dẫn **tuyệt đối**, `base.resolve(other)` có thể trả về `other` thay vì đặt nó dưới `base`. Vì vậy không đủ an toàn nếu đơn thuần viết:

```java
Path destination = uploadRoot.resolve(userSuppliedPath);
```

để cho phép người dùng chọn vị trí ghi. Cần kiểm tra path do người dùng gửi có tuyệt đối không, chuẩn hóa theo root và xác minh các điều kiện boundary; tham khảo phần bảo mật.

**Windows cần chú ý thêm:** `C:\files`, `C:files`, `\files` và UNC `\\server\share` không có cùng ngữ nghĩa. Đặc biệt, dạng `C:files` có thể liên quan thư mục hiện tại của drive, không đồng nghĩa với đường dẫn tuyệt đối `C:\files`. Không hard-code các dạng Windows vào code chạy đa nền tảng mà chưa hiểu provider.

## 5. URI là gì và khác đường dẫn String thế nào?

`java.net.URI` chứa các phần theo cú pháp URI: **scheme**, authority, path, query và fragment (tùy loại URI). Nó không đơn thuần là một đường dẫn file.

Ví dụ:

```text
file:///home/app/reports/annual%20summary.txt
https://example.org/files/report%20final.csv?version=2#details
jar:file:///home/app/lib/resources.zip!/docs/readme.txt
```

- `file:`: thường chỉ tài nguyên trong file system.
- `https:`: một URL trên mạng; **không trở thành Path file địa phương** chỉ vì có phần path.
- `jar:`: có thể chỉ tài nguyên trong archive khi có **file system provider** phù hợp.
- `%20` là cách percent-encode một dấu cách trong URI; nó không phải một đoạn tên tệp nguyên nghĩa chứa các ký tự `%`, `2`, `0`.

**Không nhầm hai factory:**

```java
Path filePath = Path.of("reports", "annual summary.txt");
URI fileUri = filePath.toAbsolutePath().toUri();
Path restored = Path.of(fileUri);
```

Đây là **mã minh họa** (cần import) theo default file system. `Path.of(String...)` nhận thành phần đường dẫn; `Path.of(URI)` nhận một URI đã phân tích và định tuyến theo scheme/provider.

### 5.1. URI string có khoảng trắng và ký tự đặc biệt

Một string như `"file:///tmp/annual summary.txt"` có khoảng trắng thô, không phải biểu diễn URI percent-encoded hợp lệ theo cú pháp URI chuẩn. `URI.create` có thể ném `IllegalArgumentException` nếu đưa vào một chuỗi không hợp lệ.

**Đừng tự nối `"file://" + pathString`** để tạo URI. Nó dễ sai với dấu cách, ký tự Unicode, ổ đĩa Windows, UNC và cách escaping. Với tệp trong Java:

```java
URI uri = localPath.toUri();
```

`Path.toUri()` tự tạo URI theo provider. Nếu cần truyền URI dưới dạng ASCII thuần, `uri.toASCIIString()` percent-encode các ký tự không thuộc ASCII theo quy tắc URI.

Cũng đừng lấy `uri.getPath()` rồi tự đặt vào `Path.of(...)` như phép biến đổi chung cho mọi URI. Cách này làm mất **scheme/authority**, không hiểu provider khác và có thể làm sai các trường hợp có encoding hoặc file system không mặc định.

## 6. Tạo Path từ file: URI

Với một file URI hợp lệ và provider hỗ trợ, có thể dùng:

```java
Path fromUri = Path.of(uri);        // Java 11+
Path fromUri7 = Paths.get(uri);    // Java 7+, vẫn hợp lệ
```

Đây là snippet với biến `uri` kiểu `java.net.URI`. `Path.of(URI)` dùng **file system provider** ứng với scheme để chuyển URI thành `Path`. Provider mặc định hỗ trợ scheme `file` với các giới hạn cú pháp/authority của hệ điều hành.

Thường **đáng tin nhất** là URI được tạo từ `path.toUri()` trên cùng hệ thống/provider, rồi chuyển lại thành `Path`.

**Lưu ý thực tế:**

- URI cho `Path.of(URI)` phải là URI thích hợp với provider; một URI tương đối không có scheme không tự trở thành đường dẫn tương đối.
- Không phải URI scheme nào cũng có provider. `https://...` không phải lời gọi mở file hệ thống qua `Path.of`.
- Một số provider cần file system tương ứng được mở trước khi có thể resolve URI nội bộ.
- Với file URI có authority, query hoặc fragment, **quy tắc hợp lệ tùy provider**; không nghĩ mọi trường URI đều được phép trong file path.
- Chuyển `Path` sang URI **không tự upload file hoặc gửi dữ liệu**. Nó chỉ biểu diễn vị trí theo dạng URI.

### 6.1. Ví dụ runnable: URI round-trip có khoảng trắng và tiếng Việt

Tạo `PathUriRoundTripDemo.java`:

```java
import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;

public class PathUriRoundTripDemo {
    public static void main(String[] args) {
        Path relative = Path.of(
                "data", "báo cáo 2026.txt");
        Path absolute =
                relative.toAbsolutePath().normalize();
        URI uri = absolute.toUri();

        Path again = Path.of(uri);
        Path legacyFactory = Paths.get(uri);

        System.out.println("scheme=" + uri.getScheme());
        System.out.println(
                "recreated-absolute=" + again.isAbsolute());
        System.out.println(
                "roundtrip=" + again.equals(absolute));
        System.out.println(
                "paths-get=" + again.equals(legacyFactory));
        System.out.println(
                "has-escaped-space="
                + uri.toASCIIString().contains("%20"));
        System.out.println(
                "has-escaped-unicode="
                + uri.toASCIIString().contains("%C3%A1"));
        System.out.println(
                "filename-ok="
                + again.getFileName().toString()
                    .equals("báo cáo 2026.txt"));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PathUriRoundTripDemo.java
java PathUriRoundTripDemo
```

```text
scheme=file
recreated-absolute=true
roundtrip=true
paths-get=true
has-escaped-space=true
has-escaped-unicode=true
filename-ok=true
```

Bài kiểm tra này dùng `toASCIIString` thay vì in trọn URI do URI có thể chứa đường dẫn working directory khác nhau trên mỗi máy.

**Phân tích:** `Path` gốc là tương đối, `toAbsolutePath()` giải quyết theo working directory, `toUri()` chuyển sang `file:` URI. Khi chuyển URI trở lại, kết quả là một `Path` **tuyệt đối**. File có thể **chưa tồn tại** mà việc tạo, chuyển URI và round-trip vẫn hợp lệ.

Việc có `%20` và `%C3%A1` chỉ chứng minh URI mang dấu cách và Unicode dưới biểu diễn ASCII đúng quy tắc, không tạo file và không bảo đảm quyền đọc tệp.

## 7. Phân tích một URI web mà không biến nó thành Path

Một URL `https:` có phần path như `/files/report%20final.csv`, nhưng **path component của URI web không phải đường dẫn trên ổ đĩa cục bộ**.

Tạo `UriPartsDemo.java`:

```java
import java.net.URI;

public class UriPartsDemo {
    public static void main(String[] args) {
        URI web = URI.create(
                "https://example.org/files/report%20final.csv"
                + "?version=2#download");

        System.out.println(
                "scheme=" + web.getScheme());
        System.out.println(
                "host=" + web.getHost());
        System.out.println(
                "raw-path=" + web.getRawPath());
        System.out.println(
                "decoded-path=" + web.getPath());
        System.out.println(
                "query=" + web.getQuery());
        System.out.println(
                "fragment=" + web.getFragment());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all UriPartsDemo.java
java UriPartsDemo
```

```text
scheme=https
host=example.org
raw-path=/files/report%20final.csv
decoded-path=/files/report final.csv
query=version=2
fragment=download
```

`getRawPath()` giữ escape sequence `%20`, còn `getPath()` trả nội dung path đã được giải mã percent-encoding thành dấu cách. Nhưng nếu lấy `getPath()` rồi gọi `Path.of(...)`, bạn sẽ chỉ tạo một **đường dẫn trong default file system**, không tự tải nội dung từ server.

Nếu mục tiêu thật là tải nội dung HTTP, dùng thư viện HTTP phù hợp, ví dụ `java.net.http.HttpClient` trên Java 17+, xác minh URI và xử lý response; **đừng** dùng `Files.readString(Path.of(httpUri))` để thay thế một HTTP client.

### 7.1. URI và URL không phải từ đồng nghĩa với local file path

`URI` mô tả tên/địa chỉ tài nguyên theo cú pháp URI. `URL` biểu diễn locator có thể dùng để truy cập các tài nguyên tương ứng theo protocol. `Path` mô hình hóa đường dẫn trong một `FileSystem` có provider tương thích.

Không nên cố dùng một API thay cho cả ba:

- Đã có một `Path` địa phương, muốn đưa vào file URI → `path.toUri()`.
- Đã có `file:` URI của file system tương thích → `Path.of(uri)` hoặc `Paths.get(uri)`.
- Đã có `https:` URI cần lấy dữ liệu → dùng HTTP client, không ép vào default file system.
- Đã có URI thuộc provider khác như `jar:` → xử lý theo provider và lifecycle của file system đó.

## 8. Làm việc thực tế với Path và Files

`Path` chỉ biểu diễn vị trí. `Files` mới làm việc với nội dung và metadata. Một workflow thường là:

1. Xác định root bằng `Path`.
2. Kết hợp tên tương đối qua `resolve`.
3. Tạo thư mục cha nếu cần.
4. Đọc/ghi bằng API có charset tường minh.
5. Nếu phải chia sẻ URI của file, gọi `toUri` trên path thực tế.
6. Đóng resources hoặc xóa file tạm theo lifecycle.

### 8.1. Ví dụ runnable: tạo file tạm, ghi, chuyển URI và đọc lại

Tạo `PathFileIoDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathFileIoDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("path-lesson-");
        Path file = dir.resolve("báo cáo.txt");

        try {
            Files.writeString(
                    file, "Xin chào",
                    StandardCharsets.UTF_8);
            URI uri = file.toUri();
            Path fromUri = Path.of(uri);

            System.out.println(
                    "scheme=" + uri.getScheme());
            System.out.println(
                    "same-path=" + fromUri.equals(file));
            System.out.println(
                    "is-file=" + Files.isRegularFile(fromUri));
            System.out.println(
                    "text-ok="
                    + Files.readString(
                        fromUri, StandardCharsets.UTF_8)
                        .equals("Xin chào"));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PathFileIoDemo.java
java PathFileIoDemo
```

```text
scheme=file
same-path=true
is-file=true
text-ok=true
```

**Chỉ ở `Files.writeString` mới có file thật được tạo**. `Path.of(URI)` không ghi hay tải bất kỳ dữ liệu nào. Tệp và thư mục được dọn trong `finally`, không để lại dữ liệu trong thư mục dự án. Các lời gọi I/O vẫn có thể ném `IOException` (ví dụ thiếu quyền hoặc hết dung lượng), vì vậy code dùng file cần xử lý lỗi.

`Files.readString`/`writeString` ở đây chỉ rõ UTF-8 để tránh đoán default charset. Nếu giao thức/tệp quy định encoding khác, hãy dùng charset theo hợp đồng đó.

### 8.2. Làm việc với thư mục con

Ví dụ dịch vụ nhận tên báo cáo do hệ thống tự tạo:

```java
Path root = Path.of("storage", "reports")
                .toAbsolutePath().normalize();
Path output = root.resolve("monthly")
                  .resolve("result.csv");

Files.createDirectories(output.getParent());
Files.writeString(
        output, "month,total\n",
        StandardCharsets.UTF_8);
```

Đây là **đoạn mã minh họa**, cần các import và xử lý `IOException`. Nếu `monthly` hay `result.csv` được cung cấp từ người dùng không đáng tin, cần kiểm tra boundary trước khi ghi file. Một thao tác `resolve` đơn giản **không đủ để ngăn path traversal**.

## 9. URI trong ZIP/JAR: phụ thuộc FileSystem provider

Không phải `Path` nào cũng thuộc ổ đĩa mặc định. NIO.2 cho phép các provider biểu diễn tài nguyên trong ZIP/JAR như một `FileSystem`.

Ví dụ URI có dạng:

```text
jar:file:///.../archive.zip!/docs/guide.txt
```

Phần trước dấu `!` chỉ archive, phần sau là path bên trong. Khi sử dụng API file system provider, những URI này có thể trở thành `Path` để đọc/ghi nội dung ZIP.

Tuy nhiên, **đừng giả định `Path.of(jarUri)` luôn mở archive tự động**. Với ZIP/JAR provider, có thể cần mở `FileSystem` tương ứng trước, dùng `FileSystems.newFileSystem(...)` và **đóng FileSystem** khi xong.

### 9.1. Ví dụ runnable: tạo ZIP FileSystem rồi chuyển path thành URI

Tạo `ZipPathDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipPathDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-path-");
        Path archive = dir.resolve("archive.zip");

        try {
            URI zipUri = URI.create(
                    "jar:" + archive.toUri());

            try (FileSystem zipFs =
                    FileSystems.newFileSystem(
                        zipUri, Map.of("create", "true"))) {
                Path inside = zipFs.getPath(
                        "/docs", "guide.txt");
                Files.createDirectories(inside.getParent());
                Files.writeString(
                        inside, "inside-zip",
                        StandardCharsets.UTF_8);

                Path restored = Path.of(inside.toUri());

                System.out.println(
                        "scheme=" + inside.toUri().getScheme());
                System.out.println(
                        "same-entry=" + restored.equals(inside));
                System.out.println(
                        "read-ok="
                        + Files.readString(
                            restored, StandardCharsets.UTF_8)
                            .equals("inside-zip"));
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipPathDemo.java
java ZipPathDemo
```

```text
scheme=jar
same-entry=true
read-ok=true
```

Ở đây `Map.of("create","true")` yêu cầu ZIP provider tạo archive nếu chưa tồn tại. `FileSystems.newFileSystem` khởi tạo một `FileSystem` từ URI archive, sau đó `zipFs.getPath("/docs", "guide.txt")` tạo path **bên trong ZIP**. Khi file system đang mở, `inside.toUri()` có scheme `jar` và `Path.of(uri)` có thể phân giải thông qua provider đã mở.

Cơ chế này phụ thuộc việc JDK/runtime có **ZIP file system provider** phù hợp (có trong các JDK đầy đủ phổ biến). Trên một runtime image tùy biến thiếu module/provider, việc mở ZIP có thể thất bại. Đây là lý do không nên viết business logic giả định mọi môi trường đều mở được mọi URI scheme.

**Ownership:** `FileSystem` được dùng trong `try-with-resources` và đóng khi hoàn thành. Không trả `Path` nội bộ cho caller rồi đóng `FileSystem` và mong caller vẫn dùng được như khi archive còn mở. Hãy quản lý rõ lifecycle của provider khi có code ở nhiều tầng.

## 10. Bảo mật: tạo Path từ đầu vào không đáng tin

Giả sử ứng dụng có thư mục gốc cho người dùng upload file:

```text
/app/uploads/
```

Một người dùng nhập `"photos/avatar.png"`, người khác gửi `"../secret.txt"` hoặc đường dẫn tuyệt đối. Nếu chỉ viết `root.resolve(input)`, ứng dụng có nguy cơ ghi/đọc ngoài thư mục gốc.

Một **kiểm tra ở mức cú pháp** (lexical check) có thể bắt đầu bằng:

1. Đổi root sang đường dẫn tuyệt đối và chuẩn hóa.
2. Tạo path từ input, **từ chối absolute path** nếu API chỉ chấp nhận relative.
3. Kết hợp root với input và `normalize()`.
4. Dùng `candidate.startsWith(root)` ở **mức Path component**, không dùng String prefix.

### 10.1. Ví dụ runnable: kiểm tra lexical boundary

Tạo `PathBoundaryDemo.java`:

```java
import java.nio.file.Path;

public class PathBoundaryDemo {
    static Path resolveLexically(Path root, String input) {
        Path relative = Path.of(input);
        if (relative.isAbsolute()) {
            throw new IllegalArgumentException(
                    "absolute path rejected");
        }

        Path normalizedRoot =
                root.toAbsolutePath().normalize();
        Path candidate = normalizedRoot
                .resolve(relative).normalize();

        if (!candidate.startsWith(normalizedRoot)) {
            throw new IllegalArgumentException(
                    "outside root");
        }
        return candidate;
    }

    public static void main(String[] args) {
        Path root = Path.of("storage", "uploads");

        Path safe = resolveLexically(
                root, "photos/avatar.png");
        System.out.println(
                "safe-absolute=" + safe.isAbsolute());

        Path normalized = resolveLexically(
                root, "temp/../photos/avatar.png");
        System.out.println(
                "normalized-same=" + safe.equals(normalized));

        try {
            resolveLexically(root, "../secret.txt");
            System.out.println("unexpected-accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "traversal-rejected="
                    + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PathBoundaryDemo.java
java PathBoundaryDemo
```

```text
safe-absolute=true
normalized-same=true
traversal-rejected=outside root
```

**Giới hạn cực kỳ quan trọng:** đây chỉ là **lexical validation**. Nó **không** bảo đảm an toàn khi file system có symbolic links, junctions/reparse points, mount points hoặc directory entries bị thay đổi giữa lúc kiểm tra và lúc mở file. Ví dụ `storage/uploads/photos` có thể là symbolic link trỏ ra ngoài root, dù path đã qua `startsWith`.

**Đối với thao tác file thực sự nhạy cảm**, cần thiết kế thêm kiểm soát từ filesystem: giới hạn thư mục có quyền ghi, từ chối/kiểm soát symlinks, xác minh parent directories và thao tác theo descriptor tương ứng (ví dụ `SecureDirectoryStream` khi provider hỗ trợ), xét nguy cơ TOCTOU và permissions. `toRealPath` giúp giải quyết trạng thái thực tại thời điểm gọi nhưng **một phép kiểm tra đơn lẻ không loại bỏ race condition** khi dữ liệu có thể bị thay đổi đồng thời.

Một hướng thường an toàn hơn cho upload là **không cho client tự chọn đường dẫn file tùy ý**: ứng dụng tạo tên lưu trữ bằng ID do server quản lý, kiểm soát phần mở rộng/loại file và giữ folder root trong cấu hình tin cậy.

### 10.2. Ký tự phân tách trên những hệ điều hành khác nhau

`Path.of("dir", "name")` dùng file system hiện tại. Một ký tự `"\\"` có thể được diễn giải là dấu phân tách trên Windows, nhưng có thể là ký tự bình thường trong tên trên Unix. Vì vậy bộ lọc chỉ thay `"../"` hoặc chỉ thay `"..\\"` theo một giả định hệ điều hành là **không đủ**.

Đừng tự sáng tạo “sanitizer” bằng một vài `String.replace` rồi tuyên bố mọi tên an toàn. Tạo `Path` bằng provider đúng và validate theo **cấu trúc, policy, symlink và quyền truy cập**. Khi nhận URI, hãy hiểu thêm percent-encoding và scheme, không tự decode vài lần tùy ý.

## 11. Các lỗi thường gặp

| Lỗi | Vì sao sai | Giải pháp |
| --- | --- | --- |
| Viết `Path.of("file:///tmp/a.txt")` để đọc file URI | Overload `String` xử lý như *file path string*, không parse URI | Tạo `URI` rồi `Path.of(uri)` nếu provider hỗ trợ |
| Viết `URI.create("file://" + path)` | Dấu cách, Unicode, Windows drive và authority dễ sai | Dùng `path.toUri()` |
| Viết `Path.of(httpUri)` để “tải URL” | HTTP không phải local filesystem scheme | Dùng HTTP client |
| Dùng `Path.of("a/b")` rồi giả định dấu phân tách giống nhau mọi OS | Cú pháp tùy provider | Truyền các thành phần `Path.of("a","b")` khi xây dựng portable path |
| Tạo `Path` rồi nghĩ file đã tồn tại | Path là object mô tả vị trí | Dùng `Files` và xử lý I/O |
| Lấy `toAbsolutePath()` làm đường dẫn đã xác minh | Chỉ chuyển đổi theo working directory | Nếu cần file thực, dùng API như `toRealPath` với contract rõ |
| Gọi `normalize()` rồi tin path an toàn tuyệt đối | Không xử lý symlink/race | Cần boundary và filesystem-level protections |
| Dùng `String.startsWith` để kiểm tra root | Prefix ký tự không phải prefix theo thành phần | Dùng `Path.startsWith` cùng chính sách bảo mật bổ sung |
| Bỏ qua `..` hoặc absolute input của người dùng | Có thể thoát khỏi root cho phép | Validate trước khi resolve và mở file |
| Dùng `getParent()` không kiểm tra null | Path chỉ có một tên hoặc root có thể không có parent | Xử lý trường hợp null |
| Dùng URI dạng `jar:` khi chưa mở provider filesystem | Có thể nhận `FileSystemNotFoundException` | Mở `FileSystem` trước và quản lý lifecycle |
| Lấy `getPath()` của URI bất kỳ rồi dùng làm local Path | Mất scheme/authority và ý nghĩa provider | Dùng URI đúng nguồn; chỉ chuyển qua provider phù hợp |
| So sánh `toString()` với đường dẫn ghi cứng của OS khác | Ký tự phân tách và root khác nhau | So `Path`/name components thay vì text khi phù hợp |
| Dùng `Files.exists` như kiểm tra quyền/bảo mật duy nhất | Kết quả không chứng minh an toàn với thay đổi đồng thời | Chọn thao tác I/O đúng chính sách, xử lý exception |
| Trả `Path` của ZIP rồi đóng FileSystem ngay | Path có thể không còn dùng được để truy cập | Trả nội dung đã đọc hoặc chuyển lifecycle sở hữu |

### 11.1. InvalidPathException, IOException và lỗi provider

Đừng trộn ba tầng lỗi:

- **Lỗi tên đường dẫn:** `Path.of(String...)` có thể ném `InvalidPathException` khi cú pháp bị từ chối.
- **Lỗi filesystem I/O:** `Files.readString`, `Files.writeString`, `Files.createDirectories` có thể ném `IOException` vì quyền truy cập, tệp không có, ổ đĩa, ... .
- **Lỗi URI/provider:** `Path.of(URI)` có thể ném `IllegalArgumentException`, `FileSystemNotFoundException`, `FileSystemNotFoundException`/`ProviderNotFoundException` tùy scheme và provider, hoặc lỗi riêng của provider.

Mỗi tầng cần thông báo lỗi phù hợp. Không biến mọi exception thành “file not found” khi nguyên nhân thật sự là URI không hợp lệ, thiếu provider, path traversal bị chặn hoặc thiếu quyền ghi.

## 12. Checklist code review

1. **Nguồn là tên đường dẫn hay URI?** Nếu đã parse thành `URI`, dùng overload URI; nếu là tên thành phần, dùng overload String.
2. **Có dùng Java 17+ không?** `Path.of` hợp lệ từ Java 11; nếu phải hỗ trợ mã nguồn Java 7 thì dùng `Paths.get` tương đương.
3. **Có hard-code separator hoặc root theo OS?** Cân nhắc `Path.of(first,more)`, `resolve` và cấu hình root.
4. **Có chuyển URI bằng `toUri()`?** Tránh tự lắp `file://` với String.
5. **Đã xử lý space, Unicode và percent-encoding chưa?** Không giải mã URI như path String một cách mơ hồ.
6. **Scheme có provider không?** `file:` thường được hỗ trợ, `https:` là HTTP, `jar:` cần provider/lifecycle thích hợp.
7. **Có đang dùng relative path mà không kiểm soát working directory?** Cần root tin cậy hoặc document rõ nơi chạy.
8. **Có gọi `normalize()` đúng mục đích?** Lexical cleanup khác `toRealPath` và không tạo file.
9. **Đầu vào có đáng tin không?** Từ chối absolute/path traversal theo policy, validate sau resolve và kiểm soát symlink/race.
10. **Đã tách path construction khỏi file I/O chưa?** `Path.of` không mở/tạo file; `Files` mới làm việc với dữ liệu.
11. **Đã xử lý `getParent() == null` chưa?** Tạo thư mục cha cần parent tồn tại về mặt cú pháp.
12. **Có đóng FileSystem do mình sở hữu không?** Nhất là ZIP/JAR provider.
13. **Đã test trên OS/provider mục tiêu chưa?** Windows path root/UNC và Unix separator có thể có ý nghĩa khác.
14. **Đã kiểm tra hành vi khi path chưa tồn tại, sai URI và thiếu quyền?** Test đường lỗi riêng, không chỉ đường thành công.

## 13. Bài tập

**Bài 1 — Từ nhiều thành phần.** Chạy `PathComponentsDemo`, đổi thành phần cuối thành tên có dấu cách. Dự đoán `getNameCount()`, `getParent()` và `getFileName()` rồi xác minh bằng code.

**Bài 2 — Lexical operations.** Chạy `PathLexicalDemo`, đổi `"draft", ".."` thành `"draft", ".", ".."` và xem `normalize()`. Phân biệt `toAbsolutePath` với `toRealPath` khi file chưa tồn tại.

**Bài 3 — URI tròn vòng.** Chạy `PathUriRoundTripDemo`, thay tên thành `"tài liệu #1.txt"` và quan sát `toASCIIString()`. Giải thích vì sao `#` được percent-encode ở path thay vì trở thành fragment.

**Bài 4 — Web URI.** Chạy `UriPartsDemo`; đổi query và fragment. Giải thích vì sao `getRawPath()` không giống `getPath()`, và vì sao không thể dùng `Path.of` để tải HTTP.

**Bài 5 — File thật.** Chạy `PathFileIoDemo`, tạo thư mục con trước khi ghi file. Thử dùng `Files.readString` trên file chưa tồn tại và xử lý `NoSuchFileException` theo contract.

**Bài 6 — ZIP FileSystem.** Chạy `ZipPathDemo`, tạo thêm file `/docs/second.txt` trong archive. Đặt mọi thao tác bên trong scope `try (FileSystem zipFs = ...)`, không để path nội bộ thoát ra rồi mới đọc.

**Bài 7 — Path traversal.** Chạy `PathBoundaryDemo`, thử `"../../private.txt"` và một input tuyệt đối. Giải thích vì sao lexical check không chứng minh an toàn nếu `uploads/photos` là symlink trỏ ra ngoài root.

**Bài 8 — Thiết kế API.** Viết hai phương thức tách bạch: `Path targetFor(String[] components)` nhận các thành phần tin cậy; `Path localFileFromUri(URI uri)` chỉ chấp nhận scheme `file` theo contract. Test với file URI và https URI.

**Bài 9 — So sánh lựa chọn.** Một hệ thống nhận hai chuỗi `"reports/2026.csv"` và `"file:///tmp/reports/2026.csv"`. Chỉ ra cách xử lý đúng mỗi chuỗi và tại sao không thể dùng một lời gọi `Path.of(String)` cho cả hai.

## 14. Ghi nhớ

- **Đầu vào là các thành phần đường dẫn:** dùng `Path.of(first, more)` trên Java 11+ hoặc `Paths.get(first,more)` khi cần API Java 7.
- **Đầu vào là URI:** dùng `Path.of(uri)`/`Paths.get(uri)` khi file system provider tương ứng hỗ trợ; `file:` khác `https:`.
- **Không tự xây file URI bằng nối String:** dùng `path.toUri()` để xử lý space, Unicode, Windows roots và escaping theo provider.
- **`resolve` ghép path, `resolveSibling` tạo path ngang cấp, `normalize` dọn `.`/`..` theo cú pháp.** Không phương thức nào tự tạo file.
- **Relative path phụ thuộc working directory**; `toAbsolutePath` không bảo đảm file tồn tại, còn `toRealPath` liên quan file system thật.
- **ZIP/JAR path cần provider và lifecycle FileSystem**; không dùng một đường dẫn của FileSystem đã đóng.
- **Boundary security không chỉ là `normalize + startsWith`.** Với input không đáng tin cần chống symlink/race, kiểm soát quyền và scope thực hiện I/O.
- **Java 17+ ưu tiên API NIO.2 hiện đại** nhưng không gọi `Paths.get` là legacy hay loại bỏ. Những kỹ thuật này vẫn được áp dụng rộng rãi.

## Tài liệu chính thức

- [Path — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `of`, `resolve`, `normalize`, `toAbsolutePath`, `toUri`, `startsWith`.
- [Paths — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Paths.html): `get(String...)` và `get(URI)`.
- [URI — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): scheme, path, raw path, percent-encoding.
- [Files — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): các thao tác I/O, giải quyết file và thư mục.
- [FileSystems — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): mở và quản lý file systems theo provider.
- [JDK ZIP File System Provider](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): ZIP/JAR là container có cấu trúc riêng; với NIO.2, dùng provider ZIP file system trong JDK nếu có.
