# `java.nio.file.Path` — Đường dẫn như một giá trị thuộc hệ thống tệp trong Java

## 1. Tư duy cốt lõi: `Path` là giá trị mô tả vị trí, không phải chính tệp

Trong Java, khi muốn diễn đạt vị trí một tệp hoặc thư mục, ta nên dùng **`java.nio.file.Path`** thay vì ghép các đoạn chuỗi tùy ý. `Path` là một interface trong Java NIO.2, được giới thiệu từ **Java 7**, dùng để biểu diễn một đường dẫn theo quy tắc của **một hệ thống tệp (`FileSystem`)**.

Ví dụ:

```java
import java.nio.file.Path;

Path document = Path.of("projects", "docs", "notes.txt");
```

Đây là các câu lệnh **minh họa bên trong phương thức**. `Path.of(...)` có từ **Java 11** và được dùng trong Java 17+; nếu cần tương thích với Java 7/8, dùng `Paths.get("projects", "docs", "notes.txt")`. Cả hai cách đều tạo đối tượng `Path` theo hệ thống tệp mặc định.

**Điểm then chốt:** Câu lệnh tạo `Path` bên trên **không tự tạo tệp `notes.txt`**, không mở tệp, không ghi dữ liệu và không xác nhận tệp có tồn tại.

Phân biệt ba lớp ý nghĩa:

| Khái niệm | Ví dụ | Điều nó đại diện |
| --- | --- | --- |
| Giá trị đường dẫn | `Path.of("projects", "docs", "notes.txt")` | Vị trí mang tên theo quy tắc `FileSystem` |
| Đối tượng của hệ thống tệp | Tệp hoặc thư mục thực sự tại vị trí đó | Có thể tồn tại, bị xóa, thay thế, đổi tên hoặc không truy cập được |
| Thao tác I/O | `Files.readString(path)`, `Files.writeString(path, text)` | Truy cập trạng thái thực tế của hệ thống tệp |

`Path` được thiết kế như một **đối tượng giá trị bất biến**: các phép như `resolve` hoặc `normalize` trả về giá trị đường dẫn, không sửa đối tượng ban đầu. Tuy nhiên, *giá trị đường dẫn bất biến* **không đồng nghĩa** với tệp mà nó tham chiếu cũng bất biến: nội dung tệp, quyền truy cập hoặc liên kết có thể thay đổi ngoài chương trình.

Mục tiêu của bài này là hiểu cách xây dựng, diễn giải, so sánh và biến đổi đường dẫn; biết khi nào thao tác chỉ là **xử lý tên đường dẫn** và khi nào đã thực sự truy cập hệ thống tệp.

## 2. `Path`, `FileSystem` và `Files` khác nhau như thế nào?

Java NIO.2 tổ chức các trách nhiệm tương đối rõ:

- **`Path`**: biểu diễn đường dẫn trong một `FileSystem`. Cung cấp các phép như `getFileName`, `getParent`, `resolve`, `relativize`, `normalize`, `toAbsolutePath` và `toRealPath`.
- **`FileSystem`**: xác định hệ thống tệp và các quy tắc về separator, root, provider, biểu diễn và so sánh đường dẫn. Một JVM có thể làm việc với hệ thống tệp mặc định và các provider khác.
- **`Files`**: các phương thức `static` để đọc/ghi, tạo/xóa, sao chép/di chuyển, lấy thuộc tính, kiểm tra trạng thái và mở stream của tệp.

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("data", "report.txt"); // Xây dựng giá trị đường dẫn.
boolean exists = Files.exists(file);       // Hỏi trạng thái tệp tại thời điểm gọi.
```

Đoạn này là **mã minh họa trong phương thức**; không có bảo đảm `data/report.txt` tồn tại. `Files.exists(file)` có thể trả `false` nếu tệp không tồn tại **hoặc nếu không thể xác định chắc trạng thái trong một số tình huống**. Đừng suy diễn `false` là bằng chứng tuyệt đối rằng tệp không tồn tại hay có thể tạo mới an toàn.

Cùng một `Path` có thể được dùng để mở tệp nhiều lần vào các thời điểm khác nhau. Giữa hai lần gọi, tệp có thể đã bị xóa hoặc nội dung bị sửa. Vì vậy không nên coi `Path` là “ảnh chụp” nội dung tệp, một file handle đang mở hoặc một lời cam kết tệp vẫn tồn tại.

### `Path` là interface, không phải loại tệp

Các đối tượng `Path` được trả về bởi một **file-system provider**. Khi tạo:

```java
Path value = Path.of("archive", "2026", "index.txt");
```

ta nhận một implementation phù hợp với `FileSystem` mặc định. Không nên viết logic dựa vào tên lớp nội bộ của implementation (có thể khác trên Windows/Linux hoặc provider khác). Cứ lập trình theo interface `Path` và các API `Files` được công khai.

**Lưu ý:** `java.io.File` vẫn còn là API Java được hỗ trợ, không phải cứ gặp `File` là mã hỏng. Với code mới cần NIO.2, `Path` thường là lựa chọn rõ ràng hơn. Các phương thức `File.toPath()` và `Path.toFile()` có thể hỗ trợ tương tác với mã dùng `java.io.File`; riêng `Path.toFile()` không phải chuyển đổi hợp lệ cho mọi `Path` từ provider phi mặc định.

## 3. Tạo `Path` đúng cách và lưu ý phiên bản Java

### 3.1. Java 11+ — `Path.of(...)`

```java
Path relative = Path.of("workspace", "docs", "readme.md");
Path absoluteOrRelative = Path.of("settings.json");
```

Các đoạn đường dẫn được truyền **theo thành phần**. Provider sẽ sử dụng quy tắc separator của hệ thống tệp tương ứng. Trên Unix, separator mặc định thường là `/`; trên Windows thường là `\`.

`Path.of` **không phải** API của Java 7 nguyên thủy, dù interface `Path` có từ Java 7. Trong tài liệu ứng dụng chạy Java 17+, `Path.of` là lựa chọn gọn gàng và hợp lệ.

### 3.2. Java 7+ — `Paths.get(...)`

```java
import java.nio.file.Path;
import java.nio.file.Paths;

Path report = Paths.get("workspace", "docs", "readme.md");
```

`Paths.get` đã có từ Java 7 và vẫn hoạt động. Đây là dạng thích hợp khi dự án thực sự còn hỗ trợ baseline Java 7/8. Không có lý do phải dùng `Path.of` trong một dự án biên dịch theo Java 7 nếu compiler không hỗ trợ.

### 3.3. Tạo từ URI khi có yêu cầu giao tiếp hệ thống khác

```java
import java.net.URI;
import java.nio.file.Path;

URI uri = URI.create("file:///tmp/example.txt");
Path path = Path.of(uri);
```

Đây là đoạn minh họa **URI kiểu `file:` trên một hệ thống phù hợp**, không nên xem `/tmp` là vị trí khả dụng trên Windows. `Path.of(URI)` có từ Java 11; `Paths.get(URI)` là dạng đã có từ Java 7. Việc hỗ trợ scheme do các **provider đã được cài đặt** quyết định: không phải mọi chuỗi URI đều có thể đổi thành đường dẫn trên mọi hệ thống tệp.

Đừng dùng `URI.create` để thay thế một cách tùy tiện cho `Path.of(String)` khi đầu vào chỉ là **tên đường dẫn của hệ thống tệp hiện tại**. URI và tên đường dẫn thuần có các quy tắc escaping/separator khác nhau.

### 3.4. Đường dẫn có thể không hợp lệ trên môi trường khác

`Path.of(...)` có thể ném `InvalidPathException` nếu chuỗi không thể biểu diễn một đường dẫn theo quy tắc của provider. Ký tự được phép, tên dành riêng, giới hạn độ dài, dạng root và phân biệt chữ hoa/chữ thường đều có thể khác giữa các hệ điều hành.

**Thực hành tốt:** tạo đường dẫn từ các thành phần `Path`, không giả định một tên mà Linux chấp nhận sẽ hợp lệ trên Windows, và không dùng các chuỗi kết hợp separator tự tạo cho mọi môi trường.

## 4. Phân tích các thành phần của một giá trị `Path`

Xét:

```java
Path p = Path.of("workspace", "assets", "logo.png");
```

Đây là **đường dẫn tương đối** có ba thành phần tên. Một số phương thức chỉ phân tích giá trị:

| API | Ý nghĩa | Giá trị với ví dụ |
| --- | --- | --- |
| `p.getFileName()` | Thành phần tên cuối | `logo.png` |
| `p.getParent()` | Phần đường dẫn cha (nếu có) | `workspace/assets` theo cách hiển thị thống nhất |
| `p.getRoot()` | Thành phần root, nếu có | `null` với đường dẫn tương đối này |
| `p.getNameCount()` | Số thành phần tên | `3` |
| `p.getName(0)` | Thành phần tên ở chỉ số 0 | `workspace` |
| `p.subpath(0, 2)` | Các tên trong khoảng chỉ số `[0,2)` | `workspace/assets` |
| `p.isAbsolute()` | Có phải đường dẫn tuyệt đối? | `false` |

Ở đây `workspace/assets` là cách mô tả với separator `/` để dễ đọc; `p.getParent().toString()` trên Windows thường dùng `\`. Các phép `getName` và `subpath` làm việc trên **thành phần tên**, không đọc nội dung tệp.

**Bẫy null:**

- `Path.of("logo.png").getParent()` có thể trả `null` vì giá trị tương đối chỉ có một tên.
- `getRoot()` trả `null` với đường dẫn không có root.
- `getFileName()` có thể trả `null` với một đường dẫn chỉ gồm root.

Đừng tự động gọi `p.getParent().resolve(...)` hoặc `p.getRoot().toString()` khi chưa biết kết quả không phải `null`.

### Tên cuối không cho biết loại tệp thực tế

`getFileName()` chỉ đọc **tên cuối trong đường dẫn**. Nó không kiểm tra đây là tệp, thư mục, symbolic link hay một tên không tồn tại. Một đường dẫn kết thúc bằng `.txt` vẫn có thể trỏ tới một thư mục hoặc không có đối tượng nào.

Muốn hỏi hệ thống tệp, dùng các API như `Files.isRegularFile`, `Files.isDirectory` hoặc `Files.readAttributes` khi phù hợp; mỗi phép quan sát vẫn có thể bị thay đổi bởi thao tác từ tiến trình khác.

## 5. `resolve`: ghép đường dẫn theo ngữ nghĩa của `FileSystem`

Đây là thao tác thường dùng để xây dựng đường dẫn con:

```java
Path base = Path.of("workspace", "assets");
Path logo = base.resolve("logo.png");
```

Giá trị `logo` tương ứng với `workspace/assets/logo.png` trên hệ thống dùng dấu `/`. Hai lệnh trên **chưa tạo thư mục hay tệp**.

### 5.1. `resolve` khác phép cộng chuỗi

Không nên ghép:

```java
String file = directory + "/" + name;
```

trong mã mà `directory` và `name` vốn là khái niệm đường dẫn: việc tự ghép separator khó kiểm soát hệ điều hành, phần tử đường dẫn tuyệt đối và cấu trúc tên. Thay vào đó, chuyển sang kiểu `Path` sớm và dùng `resolve`:

```java
Path directory = Path.of("workspace", "assets");
Path file = directory.resolve("logo.png");
```

Trong ví dụ này `resolve` nhận một **tên tương đối**. Nếu đối số là một `Path` **tuyệt đối**, quy tắc thường gặp là kết quả giải quyết theo đối số tuyệt đối thay vì bắt buộc nằm dưới `directory`. Vì vậy, không được dựa vào `base.resolve(userInput)` như một biện pháp tự động nhốt đường dẫn đầu vào bên trong thư mục cho phép.

### 5.2. `resolveSibling`: đường dẫn cùng cấp

```java
Path logo = Path.of("workspace", "assets", "logo.png");
Path readme = logo.resolveSibling("readme.md");
```

`readme` tương ứng với `workspace/assets/readme.md`. Đó là thao tác dựa trên **phần cha** của `logo`. Nếu đường dẫn hiện tại không có phần cha, `resolveSibling` có hành vi tương ứng với đối số được cung cấp, nên đừng mặc định có cấu trúc thư mục cha ở mọi trường hợp.

### 5.3. Dùng `resolve` với cấu trúc đầu ra

```java
Path outputDirectory = Path.of("exports", "daily");
Path destination = outputDirectory.resolve("summary.csv");
```

Đây là cách tổ chức đường dẫn trước khi ghi tệp. Để thực sự tạo thư mục cha hoặc ghi nội dung, cần các lệnh như `Files.createDirectories(outputDirectory)` và `Files.writeString(destination,...)`, với xử lý lỗi I/O thích hợp.

## 6. `relativize`: mô tả đường đi từ một `Path` sang `Path` khác

`relativize` trả một **đường dẫn tương đối** giữa hai giá trị đường dẫn tương thích:

```java
Path base = Path.of("workspace", "assets");
Path logo = Path.of("workspace", "assets", "logo.png");

Path relative = base.relativize(logo);
// relative tương ứng với "logo.png".
```

Trong ví dụ trên, có thể kiểm tra:

```java
Path roundTrip = base.resolve(relative);
boolean same = roundTrip.equals(logo); // true với các giá trị này.
```

Để biểu diễn “từ thư mục con đi lên rồi sang thư mục khác”:

```java
Path from = Path.of("workspace", "assets");
Path to = Path.of("workspace", "docs", "readme.md");

Path steps = from.relativize(to);
// steps gồm: .. / docs / readme.md
```

Phần `..` ở đây là thành phần **tên đường dẫn**, không có nghĩa chương trình đã di chuyển tệp hoặc duyệt thư mục trên đĩa.

**Giới hạn cần nhớ:**

- Thường không được relativize giữa một `Path` tuyệt đối và một `Path` tương đối; việc đó có thể gây `IllegalArgumentException`.
- Hai `Path` thuộc hệ thống tệp/provider không tương thích cũng không có phép tính tương đối hợp lệ.
- `relativize` tính toán dựa trên cách hiểu tên đường dẫn của provider; không thay thế việc kiểm tra đối tượng thật khi có symbolic link.
- `from.relativize(to)` **không** đồng nghĩa với `to.relativize(from)`.

Nếu đầu vào của ứng dụng có thể mang các dạng khác nhau, hãy thống nhất cách biểu diễn (ví dụ cùng là relative theo một base đã biết, hoặc cùng absolute trên một file system) trước khi gọi `relativize`.

## 7. `normalize`: chuẩn hóa cú pháp, không xác minh tệp tồn tại

`normalize()` loại bỏ các thành phần tên dư thừa như `.` và xử lý các cặp thành phần `name/..` theo **quy tắc đường dẫn từ góc nhìn cú pháp**.

```java
Path raw = Path.of("workspace", "docs", "..", "assets", "logo.png");
Path normalized = raw.normalize();
```

Có thể hình dung:

```text
raw        = workspace/docs/../assets/logo.png
normalized = workspace/assets/logo.png
```

Phương thức không cần mở tệp, không đọc directory entries và không kiểm tra `workspace/docs` có thực sự tồn tại.

**Điểm quan trọng:** `normalize` **không đảm bảo** đường dẫn chuẩn hóa tham chiếu tới cùng đối tượng tệp trong mọi trường hợp, đặc biệt nếu một thành phần trung gian là **symbolic link**. Ví dụ `link/../file` có thể được hệ thống tệp diễn giải khác với kết quả xóa cặp `link/..` theo cú pháp.

Do đó:

- Dùng `normalize` để **làm gọn/đồng nhất biểu thức tên đường dẫn** khi điều đó có ý nghĩa.
- Không gọi nó là cơ chế xác minh đường dẫn thực hay biện pháp bảo mật đủ dùng.
- Không kết luận từ `raw.normalize().equals(other)` rằng hai giá trị chắc chắn trỏ đến cùng tệp trên đĩa.

### `normalize` khác `toAbsolutePath`

`toAbsolutePath()` trả một đường dẫn tuyệt đối dựa trên ngữ cảnh và quy tắc file system. Nếu đầu vào là relative, nó thường được giải quyết dựa trên **thư mục làm việc hiện tại** của chương trình hoặc ngữ cảnh file system tương ứng. Nó **không cần kiểm tra tệp có tồn tại** và không phải bảo đảm đã giải quyết symbolic link.

```java
Path relative = Path.of("docs", "readme.md");
Path absolute = relative.toAbsolutePath();
```

Giá trị in ra của `absolute` phụ thuộc máy, ổ đĩa, đường dẫn khởi chạy và provider; **không có stdout cố định đa nền tảng** cho ví dụ này.

Cũng không nên mặc định `toAbsolutePath()` sẽ tự loại hết `.` và `..`. Nếu cần biểu thức cú pháp gọn hơn, có thể dùng `toAbsolutePath().normalize()` nhưng vẫn hiểu đây chưa phải xác minh đối tượng thật.

## 8. `toRealPath`: đường dẫn thực và tác động của symbolic link

Khi cần biết đường dẫn thực của **một đối tượng hệ thống tệp đang tồn tại**, `toRealPath(...)` có thể chuẩn hóa, chuyển thành absolute và giải quyết symbolic link theo những quy tắc của provider.

```java
import java.io.IOException;
import java.nio.file.Path;

static Path existingRealPath(Path input) throws IOException {
    return input.toRealPath();
}
```

Đây là **phương thức minh họa** đặt trong một lớp Java. Khác `normalize`, `toRealPath` thực hiện tương tác với hệ thống tệp và có thể ném `IOException`, ví dụ nếu tệp không tồn tại hoặc không thể truy cập.

Mặc định, `toRealPath()` **theo các symbolic link**. Khi hợp đồng yêu cầu không theo link, có thể cân nhắc:

```java
import java.nio.file.LinkOption;
import java.nio.file.Path;

Path path = Path.of("some", "entry");
Path realWithoutFollowingLinks =
        path.toRealPath(LinkOption.NOFOLLOW_LINKS);
```

Đây là **mã minh họa trong phương thức có thể ném `IOException`**. Không thể suy ra đường dẫn hoặc trạng thái kết quả nếu không biết hệ thống tệp thật. `NOFOLLOW_LINKS` làm thay đổi chính sách xử lý symbolic link theo hợp đồng API; cách hoạt động chi tiết có thể tùy provider.

| Thao tác | Chủ yếu xử lý tên? | Có thể yêu cầu đối tượng thật? | Symbolic link |
| --- | --- | --- | --- |
| `getFileName` / `getParent` | Có | Không | Không giải quyết |
| `resolve` / `relativize` | Có | Không | Không giải quyết |
| `normalize` | Có | Không | Không giải quyết thực tế |
| `toAbsolutePath` | Chuyển sang absolute theo ngữ cảnh | Không nhất thiết | Không thay thế `toRealPath` |
| `toRealPath` | Không chỉ tên: có I/O | Có, theo hợp đồng | Mặc định đi theo link; có tùy chọn |
| `Files.isSameFile(a,b)` | Kiểm tra danh tính tệp | Có thể I/O và ném lỗi | Có thể kiểm tra hai tên cùng một đối tượng tệp |

**Không đồng nhất `normalize` với `toRealPath`**: kết quả trông giống nhau trên một ví dụ đơn giản không bảo đảm chúng có cùng ngữ nghĩa trong thư mục chứa symlink, tên ảo hoặc provider khác.

## 9. `equals` và `hashCode` của `Path`: so sánh giá trị đường dẫn

Vì `Path` là đối tượng giá trị, có thể dùng nó làm khóa trong map/set hoặc so sánh các đường dẫn:

```java
Path first = Path.of("workspace", "assets", "logo.png");
Path second = Path.of("workspace", "assets").resolve("logo.png");

boolean equal = first.equals(second); // true trong ví dụ này.
```

Các giá trị `Path` cần được so sánh theo **quy tắc `equals`/`hashCode` của chính implementation và file system**. Không thay chúng bằng `toString().equals(...)` để tự tạo một hợp đồng so sánh có thể sai separator, casing hoặc provider.

### So sánh `Path` có phải so sánh “cùng tệp thực” không?

**Không nhất thiết.** Hai giá trị đường dẫn khác nhau có thể tham chiếu tới cùng một đối tượng tệp nhờ symbolic link hoặc hard link. Ngược lại, ngay cả một giá trị `Path` cố định có thể trỏ tới các đối tượng tệp khác nhau theo thời gian nếu tệp bị thay thế.

Đối với hai đối tượng đang tồn tại, `Files.isSameFile(a,b)` là API thích hợp khi muốn hỏi **cùng một tệp** theo hệ thống tệp:

```java
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn minh họa; a và b cần được khai báo là Path.
boolean sameFile = Files.isSameFile(a, b);
```

Phương thức này có thể thực hiện I/O và ném `IOException`, không phải lúc nào cũng cần hoặc nên gọi. Nó khác việc hỏi hai **giá trị đường dẫn** có `equals` hay không.

### `normalize` trước khi so sánh có ý nghĩa gì?

```java
Path raw = Path.of("workspace", "docs", "..", "assets", "logo.png");
Path normalized = raw.normalize();

boolean sameValue = raw.equals(normalized); // false trong ví dụ này.
```

Đường dẫn thô có các thành phần `docs/..` mà giá trị chuẩn hóa không còn. Kết quả so sánh trong ví dụ minh họa trên provider mặc định thông thường là `false`. Không suy rộng giá trị này thành bảo đảm mọi provider đều phân biệt mọi cách viết của một đường dẫn như nhau: các quy tắc `equals`, phân biệt chữ hoa và quản lý root có thể phụ thuộc `FileSystem`.

Nếu cần dùng `Path` làm khóa trong cache, hãy quyết định trước **hợp đồng khóa**: dạng relative hay absolute, có normalize theo cú pháp không, có yêu cầu real path không, file system nào, và cache có phụ thuộc trạng thái tệp đang tồn tại hay không.

## 10. Code hoàn chỉnh Java 17+: kiểm tra giá trị đường dẫn và thao tác tệp riêng biệt

Ví dụ chạy độc lập dưới đây cố ý tách **phần thao tác giá trị thuần `Path`** khỏi **phần I/O qua `Files`**. Chương trình chỉ tạo một tệp mẫu trong thư mục tạm do hệ thống cấp, sau đó xóa tệp và thư mục tạm. Mọi thông điệp stdout có thể kiểm tra mà không phụ thuộc tên thư mục hiện tại.

Tạo tệp **`PathValueDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PathValueDemo {
    private static String display(Path path) {
        return path.toString().replace('\\', '/');
    }

    private static void check(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }

    public static void main(String[] args) throws IOException {
        Path raw = Path.of("workspace", "docs", "..", "assets", "logo.png");
        Path normalized = raw.normalize();
        Path base = Path.of("workspace", "assets");
        Path target = base.resolve("logo.png");

        check(normalized.equals(target), "normalized equality");
        check(normalized.startsWith(base), "component prefix");
        check(!Path.of("workspace", "assets-old", "x").startsWith(base),
                "prefix is not string prefix");
        check(!raw.equals(normalized), "lexical equality differs");
        check(normalized.getRoot() == null, "relative has no root");

        System.out.println("raw = " + display(raw));
        System.out.println("normalized = " + display(normalized));
        System.out.println("normalized equals target = " + normalized.equals(target));
        System.out.println("raw equals normalized = " + raw.equals(normalized));
        System.out.println("parent = " + display(normalized.getParent()));
        System.out.println("file name = " + normalized.getFileName());
        System.out.println("relative has no root = " + (normalized.getRoot() == null));
        System.out.println("relative to base = " + display(base.relativize(target)));
        System.out.println("sibling = " + display(target.resolveSibling("readme.md")));
        System.out.println("component prefix = " + target.startsWith(base));
        System.out.println("false string prefix = "
                + Path.of("workspace", "assets-old", "x").startsWith(base));

        Path directory = Files.createTempDirectory("path-value-demo-");
        Path file = directory.resolve("sample.txt");
        try {
            System.out.println("exists before = " + Files.exists(file));
            Files.writeString(file, "Hello Path", StandardCharsets.UTF_8);
            System.out.println("regular file after = " + Files.isRegularFile(file));
            System.out.println("content = "
                    + Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("real path exists = " + Files.exists(file.toRealPath()));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
        System.out.println("cleanup complete");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 PathValueDemo.java
java PathValueDemo
```

**Stdout đã kiểm chứng:**

```text
raw = workspace/docs/../assets/logo.png
normalized = workspace/assets/logo.png
normalized equals target = true
raw equals normalized = false
parent = workspace/assets
file name = logo.png
relative has no root = true
relative to base = logo.png
sibling = workspace/assets/readme.md
component prefix = true
false string prefix = false
exists before = false
regular file after = true
content = Hello Path
real path exists = true
cleanup complete
```

### 10.1. Vì sao dùng `display`?

`display` chuyển ký tự `\` trong kết quả `toString()` thành `/` **chỉ để in ra màn hình cùng một dạng trình bày** trên Windows và Unix. Đây **không phải** cách xử lý đường dẫn để mở tệp. Toàn bộ phép `resolve`, `normalize`, `relativize` và `Files` vẫn nhận **`Path` gốc**. Không dùng `display` làm phương thức normalize thay cho API của `Path`.

### 10.2. Hai phần kiểm chứng khác nhau

Phần đầu chỉ xử lý tên đường dẫn `workspace/...`:

- `normalize` biến `workspace/docs/../assets/logo.png` thành `workspace/assets/logo.png`.
- `resolve("logo.png")` xây dựng đường dẫn con của `base`.
- `relativize` trả `logo.png` khi tính từ `base` tới `target`.
- `resolveSibling` thay thành phần tên cuối thành `readme.md`.
- `startsWith` nhận biết các thành phần đường dẫn, không chỉ tiền tố chuỗi; `assets-old` không thuộc nhánh `assets`.
- Không tạo hay cần tồn tại bất kỳ tệp `workspace/...` nào.

Phần thứ hai **có I/O thật** trong thư mục tạm:

- `Files.createTempDirectory` tạo thư mục thực tế.
- `directory.resolve("sample.txt")` mới tạo **giá trị đường dẫn**, nên `exists before` là `false`.
- `Files.writeString` tạo/ghi nội dung tệp, rồi `Files.isRegularFile` xác nhận thuộc tính quan sát tại thời điểm gọi.
- `Files.readString` đọc đúng nội dung `Hello Path`.
- `file.toRealPath()` thành công vì tệp thực tế đang tồn tại.
- `finally` cố gắng xóa tài nguyên mẫu để tránh để lại tệp tạm.

`Files.createTempDirectory` có thể chọn một thư mục tạm với tên khác nhau ở mỗi lượt; ví dụ **không in đường dẫn tuyệt đối** nên stdout không phụ thuộc chuỗi tên ngẫu nhiên. Nếu hệ thống từ chối tạo/ghi/xóa tệp tạm vì quyền hoặc không còn dung lượng, chương trình có thể ném `IOException`; đó là điều kiện môi trường I/O, không phải sự bất ổn của các phép biến đổi giá trị `Path`.

## 11. Tính đa nền tảng: tên đường dẫn phải theo quy tắc file system

### 11.1. Separator phụ thuộc môi trường

`Path.of("a", "b", "c.txt")` là dạng dễ mang qua các hệ điều hành hơn việc ghép một chuỗi có dấu `/` hoặc `\` cứng nhắc cho mọi provider. Kết quả `Path.toString()` không có nghĩa là định dạng trao đổi chung giữa hệ thống.

- Trên Linux/macOS, separator mặc định thường là `/` và root là `/`.
- Trên Windows, tồn tại các dạng drive, UNC và quy tắc root khác; separator mặc định thường là `\`.
- Một provider cho file system chuyên biệt có thể có cách biểu diễn khác nữa.

Nếu ứng dụng cần dữ liệu chuyển giữa hệ thống, hãy chọn **định dạng giao thức rõ ràng**, chẳng hạn URI đúng chuẩn cho tài nguyên phù hợp hoặc lưu **các thành phần tên logic**, thay vì trao đổi tùy tiện chuỗi `Path.toString()` rồi mong mọi máy hiểu giống nhau.

### 11.2. Không tự đổi chữ hoa/chữ thường

Một số hệ thống tệp mặc định không phân biệt chữ hoa/chữ thường khi tra cứu tên, một số hệ thống thì phân biệt. Không nên viết:

```java
String key = path.toString().toLowerCase();
```

rồi coi đó là cách chuẩn hóa `Path` phổ quát. Cách làm này có thể đồng nhất sai hai tên thực sự khác nhau hoặc không tương thích locale và provider. Sử dụng quy tắc so sánh `Path` của provider; nếu cần chính sách riêng, định nghĩa rõ trên miền dữ liệu logic của ứng dụng.

### 11.3. Đừng nhầm `URI` với chuỗi đường dẫn

`Path.toUri()` cung cấp một `URI` đại diện theo hợp đồng provider, thường có biểu diễn dựa trên đường dẫn tuyệt đối đối với `Path` của file system mặc định. Nó khác phép ép chuỗi thuần và có quy tắc encoding khác.

Dữ liệu như `file:///...`, `C:\...` và `docs/notes.txt` không phải ba cách viết hoán đổi tự do. Nếu thao tác với URI nhận từ network, phải kiểm tra **scheme/provider** và chính sách được phép; tránh tự thay dấu slash rồi coi đó là parser an toàn.

## 12. `Path`, bảo mật đường dẫn và đầu vào không tin cậy

Giả sử server nhận một tên tệp từ người dùng:

```java
Path root = Path.of("uploads").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();
```

Đây là **mã minh họa**, biến `userSuppliedName` là dữ liệu chưa tin cậy. Hai lệnh có thể tạo một giá trị đường dẫn, nhưng **không tự chặn tấn công path traversal**:

- Giá trị như `../outside.txt` có thể đi ra khỏi thư mục dự kiến.
- Giá trị tuyệt đối có thể khiến `resolve` không còn nằm dưới `root` như người lập trình tưởng.
- Symbolic link nằm trong `root` có thể dẫn đến vị trí bên ngoài khi truy cập thật.
- Giữa bước kiểm tra và bước mở tệp, thành phần đường dẫn có thể bị tiến trình khác đổi (**TOCTOU**, time-of-check vs time-of-use).

### Kiểm tra cú pháp chỉ là một lớp bảo vệ

Một bước kiểm tra thành phần có thể dùng:

```java
Path candidate = root.resolve(userSuppliedName).normalize();
boolean lexicallyInside = candidate.startsWith(root);
```

`startsWith` xem xét **thành phần đường dẫn**, tốt hơn kiểm tra `candidate.toString().startsWith(root.toString())` vốn dễ nhầm `uploads` với `uploads-old`. Tuy vậy, kiểm tra **lexicallyInside** không phải một hàng rào bảo mật hoàn chỉnh và **không xác thực** quyền truy cập thực tế.

Khi đường dẫn không tin cậy và hệ thống có đối thủ có thể sửa thư mục/link, cần thiết kế theo mô hình đe dọa: root do hệ thống kiểm soát, kiểm tra quyền, cách xử lý symbolic link, hạn chế thao tác theo directory handle hoặc API như `SecureDirectoryStream` nếu provider hỗ trợ, và tránh giả định rằng `toRealPath` một lần loại bỏ mọi race condition.

**Không tự giải quyết vấn đề bằng “cứ gọi `normalize` là an toàn”**. `normalize` xử lý tên, không giải quyết filesystem security.

### Vì sao `Files.exists` trước khi mở chưa đủ?

```java
if (Files.exists(candidate)) {
    // Trạng thái có thể thay đổi trước thao tác đọc/ghi thật.
}
```

Trong hệ thống có nhiều tiến trình, kết quả `exists` chỉ là quan sát ở một thời điểm. Một tệp có thể bị xóa hoặc thay thế ngay sau đó. Hãy để thao tác I/O thực tế báo lỗi và xử lý `IOException`; khi cần tránh ghi đè, dùng các tùy chọn tạo tệp thích hợp như `StandardOpenOption.CREATE_NEW` theo hợp đồng, thay vì chỉ kiểm tra `exists` rồi tạo tệp theo hai bước không nguyên tử.

## 13. Các lỗi thường gặp

| Nhầm lẫn | Vì sao sai hoặc nguy hiểm | Cách hiểu đúng |
| --- | --- | --- |
| “Tạo `Path` là tạo tệp.” | `Path.of`/`Paths.get` chỉ tạo giá trị tên đường dẫn | Dùng `Files` cho I/O thật |
| Dùng `Path.of` trong dự án biên dịch Java 7 | `Path.of` có từ Java 11 | Dùng `Paths.get` nếu baseline Java 7 |
| Coi `getFileName()` là xác nhận “đó là tệp” | Nó chỉ lấy tên cuối | Dùng `Files` để hỏi loại đối tượng thật |
| Gọi `getParent().resolve(...)` trên tên đơn | `getParent()` có thể `null` | Kiểm tra `null` |
| Nhầm `normalize` với `toRealPath` | Một bên chủ yếu lexical, bên kia có I/O và xử lý link | Dùng đúng theo mục tiêu |
| Cho rằng `toAbsolutePath` bảo đảm file có thật | Chỉ chuyển thành đường dẫn absolute theo ngữ cảnh | Gọi I/O và xử lý lỗi nếu cần |
| So sánh hai `Path` bằng chuỗi đã lower-case | Không phù hợp mọi provider/case rule | Dựa vào hợp đồng `Path` |
| Kết luận `p.equals(q)` nghĩa là cùng file vật lý | Có thể có symlink/hard link hoặc file bị thay đổi | Dùng `Files.isSameFile` khi cần và có điều kiện |
| Xem `resolve(base, userInput)` là sandbox | Đầu vào absolute/`..`/symlink có thể phá phạm vi | Kiểm tra đa lớp và mô hình đe dọa |
| Cho rằng `relativize` luôn chạy giữa absolute và relative | Có thể ném `IllegalArgumentException` | Dùng đường dẫn tương thích |
| Lưu `Path.toString()` như format chung mọi OS | Separator/root/provider có thể khác | Định nghĩa format trao đổi rõ |
| Giả định tên tệp có đuôi `.txt` là file thường | Có thể là thư mục, symlink hoặc không tồn tại | Đọc thuộc tính thực tế |
| Dùng `Files.exists` như đảm bảo lâu dài | Quan sát có thể bị race | Xử lý I/O thực và lỗi |
| Dựa vào `normalize` để xử lý mọi symlink | Không truy filesystem | Cân nhắc `toRealPath` và API bảo mật |
| Tự sửa dấu slash trên đường dẫn để thao tác | Không giải quyết provider semantics | Dùng `Path.resolve` và các API tên đường dẫn |

## 14. Bài tập tự luyện và đáp án

### Bài 1 — Tạo đường dẫn có tạo tệp không?

```java
Path p = Path.of("data", "archive.zip");
```

**Câu hỏi:** Sau lệnh trên, `archive.zip` chắc chắn tồn tại chưa?

**Đáp án:** Chưa. Lệnh chỉ tạo một **giá trị `Path`**. Muốn biết trạng thái tại một thời điểm có thể gọi `Files.exists(p)`, nhưng việc kiểm tra vẫn chịu giới hạn quyền và trạng thái có thể thay đổi. Muốn tạo tệp cần lệnh I/O thích hợp.

### Bài 2 — Chuẩn hóa

```java
Path p = Path.of("a", "b", "..", "c", "file.txt");
```

**Câu hỏi:** `p.normalize()` có các thành phần tên nào?

**Đáp án:** `a/c/file.txt` theo biểu diễn dấu slash minh họa. Việc loại `b/..` là xử lý lexical, **không phải** kiểm tra hệ thống tệp có thư mục `b`.

### Bài 3 — Đường dẫn tương đối

Với `base = Path.of("a","reports")` và `target = Path.of("a","reports","2026.csv")`, `base.relativize(target)` trả gì?

**Đáp án:** `2026.csv`. Phép `base.resolve(base.relativize(target))` tái tạo giá trị `target` trong trường hợp này.

### Bài 4 — `resolveSibling`

`Path.of("a","b","old.txt").resolveSibling("new.txt")` biểu diễn vị trí nào?

**Đáp án:** `a/b/new.txt`. Nó thay tên cuối trong cùng thư mục cha; chưa đổi tên tệp thật.

### Bài 5 — Hai loại so sánh

Hai đường dẫn khác tên nhưng cùng tham chiếu một file nhờ symbolic link có nhất thiết `equals` là `true` không?

**Đáp án:** Không. `equals` so sánh **giá trị `Path`** theo hợp đồng provider. Muốn kiểm tra hai đường dẫn đang tham chiếu tới cùng file thực, dùng API như `Files.isSameFile` khi phù hợp, chấp nhận khả năng I/O và ngoại lệ.

### Bài 6 — Đường dẫn tuyệt đối

`Path.of("docs","a.txt").toAbsolutePath()` có thể in ra giống nhau trên mọi máy không? Tệp cần tồn tại để dùng phép này không?

**Đáp án:** Không: đường dẫn absolute phụ thuộc thư mục làm việc, OS và provider. `toAbsolutePath` không đòi tệp tồn tại. Không viết unit test kiểm tra một chuỗi absolute cố định khi chạy trên nhiều môi trường.

### Bài 7 — Biên của `getParent`

`Path.of("notes.txt").getParent()` có thể là gì?

**Đáp án:** Có thể là `null`, vì đường dẫn tương đối chỉ có một thành phần tên. Cần kiểm tra trước khi gọi phương thức trên kết quả.

### Bài 8 — Kiểm tra tiền tố

Tại sao `Path.of("root","uploads-old","x").startsWith(Path.of("root","uploads"))` là `false`?

**Đáp án:** `startsWith` của `Path` so sánh **các thành phần tên**, không phải kiểm tra tiền tố của một chuỗi ký tự. `uploads-old` không phải cùng thành phần `uploads`. Tuy nhiên, phép kiểm tra lexical này **không đủ làm sandbox bảo mật** khi có symlink hoặc race condition.

### Bài 9 — Khi nào dùng `toRealPath`?

Trong một quy trình cần xác định vị trí thật của tệp đang tồn tại, vì sao `toRealPath` phù hợp hơn `normalize`?

**Đáp án:** `toRealPath` tương tác với hệ thống tệp và có thể giải quyết symbolic link theo tùy chọn, đồng thời ném `IOException` khi không truy cập được. `normalize` chỉ loại thành phần dư về mặt tên. Dù vậy, kết quả `toRealPath` không phải bảo đảm trạng thái sẽ không thay đổi trong tương lai.

### Bài 10 — Java 7 và Java 17

Hãy chọn cách tạo `Path` tương thích Java 7 và cách viết gọn trên Java 17.

**Đáp án:**

```java
Path compatibleWithJava7 =
        java.nio.file.Paths.get("a", "b", "c.txt");

Path java17Style =
        Path.of("a", "b", "c.txt");
```

Cả hai biểu diễn đường dẫn theo hệ thống tệp mặc định tương ứng; `Path.of` chỉ có từ Java 11, còn `Paths.get` dùng được từ Java 7.

## 15. Checklist khi dùng `Path` trong ứng dụng thật

- [ ] Đã xác định **`FileSystem`/provider** và định dạng đường dẫn đầu vào.
- [ ] Hiểu rằng **tạo `Path` không tạo file** và không bảo đảm file đang tồn tại.
- [ ] Chọn `Path.of` (Java 11+) hoặc `Paths.get` (Java 7+) theo baseline được hỗ trợ.
- [ ] Dùng `resolve`, `relativize`, `resolveSibling` thay cho thao tác ghép chuỗi thủ công khi biểu diễn đường dẫn.
- [ ] Kiểm tra khả năng `null` của `getParent` và `getRoot` trước khi truy cập tiếp.
- [ ] Phân biệt **relative, absolute, normalized và real path**.
- [ ] Không nhầm so sánh giá trị `Path.equals` với nhận dạng **cùng file vật lý**.
- [ ] Khi làm I/O, xử lý `IOException` và race condition; không phụ thuộc `Files.exists` như bảo đảm vĩnh viễn.
- [ ] Đường dẫn nhận từ người dùng phải có chính sách **path traversal, symbolic link, quyền truy cập và root** thích hợp.
- [ ] Không mặc định chuỗi `Path.toString()` có cùng ý nghĩa trên mọi OS/provider.
- [ ] Test chương trình trên môi trường được hỗ trợ, nhất là separator, absolute/relative, tên có dấu Unicode và tệp/đường dẫn không tồn tại.

## 16. Tổng kết

`java.nio.file.Path` biểu diễn **một giá trị đường dẫn thuộc một hệ thống tệp**, không phải đối tượng tệp vật lý hay thao tác I/O. Cấu trúc này giúp xử lý đường dẫn bằng những API có ngữ nghĩa: `resolve` để ghép, `relativize` để tính đường tương đối, `getFileName`/`getParent` để phân tích, `normalize` để làm gọn cú pháp và `toAbsolutePath` để chuyển sang đường dẫn tuyệt đối.

Khi cần xác minh trạng thái thật, phải chuyển sang các thao tác **`Files`** hoặc `toRealPath` và chấp nhận lỗi I/O. Hãy nhớ sự khác nhau giữa **giá trị `Path`**, **đối tượng file đang tồn tại**, **đường dẫn thực có symbolic link** và **đầu vào không tin cậy**. Interface `Path` từ Java 7 đến Java hiện đại vẫn là một phần nền tảng của Java NIO.2; dùng đúng nó giúp mã đọc/ghi file dễ hiểu, dễ kiểm thử và ít phụ thuộc phép ghép chuỗi theo hệ điều hành.