# Path.normalize() chỉ xử lý cú pháp đường dẫn

## 1. Vì sao cần hiểu đúng normalize()?

Trong Java NIO.2, `java.nio.file.Path` biểu diễn **đường dẫn** đến một vị trí trong hệ thống tệp. Một đường dẫn có thể chứa các phần tên bình thường cùng những thành phần đặc biệt như `.` (thư mục hiện tại) và `..` (thư mục cha). Phương thức `Path.normalize()` giúp rút gọn các thành phần dư thừa theo **quy tắc cú pháp đường dẫn**.

Điểm quan trọng nhất:

> **`Path.normalize()` là phép biến đổi từ một đối tượng Path thành một Path khác theo cú pháp; nó không mở file, không tra cứu sự tồn tại của file, không kiểm tra quyền và không xác minh symbolic link trỏ đến đâu.**

Ví dụ đường dẫn tương đối:

```text
Đầu vào:    data/reports/../images/./logo.png
            └───────┬──────┘       │
                  reports/..        .
                    loại bỏ     loại bỏ
Kết quả:    data/images/logo.png
```

Nếu ta chỉ cần làm sạch biểu diễn đường dẫn cho mục đích thao tác cú pháp, `normalize()` rất hữu ích. Nhưng nếu muốn biết hai đường dẫn thật sự trỏ tới **cùng một file**, thư mục đích thật là đâu hoặc một đường dẫn có nằm an toàn trong thư mục được phép không, phải dùng các API và biện pháp khác.

Trong cùng module Java I/O, hãy phân biệt ba việc:

1. **Lexical normalization:** chuẩn hóa phần tên trong `Path` bằng `normalize()`.
2. **Absolute path conversion:** tạo biểu diễn tuyệt đối bằng `toAbsolutePath()`.
3. **Filesystem resolution:** truy cập hệ thống tệp để xác định đường dẫn thực, tồn tại và liên kết, ví dụ `toRealPath()` hoặc `Files.isSameFile()`.

Đây là ba ý nghĩa khác nhau dù chúng thường xuất hiện gần nhau trong code.

## 2. Path là một biểu diễn đường dẫn

`Path` là interface thuộc `java.nio.file`, được tạo thông dụng bằng `Path.of(...)`. Một `Path` có thể:

- Là **tương đối**: `docs/manual.txt`.
- Là **tuyệt đối**: ví dụ `/var/data/manual.txt` trên hệ thống Unix hoặc đường dẫn có ký hiệu ổ đĩa thích hợp trên Windows.
- Có dấu phân cách và đặc điểm được quyết định bởi **filesystem provider**.
- Chứa các name element như `docs`, `.`, `..`, `manual.txt`.

Các thao tác thuần về `Path` như `resolve()`, `getFileName()`, `getParent()`, `startsWith()`, `endsWith()`, `relativize()`, và `normalize()` có thể thực hiện trên biểu diễn đường dẫn. Không cần có tệp tương ứng đang tồn tại để gọi `normalize()`.

Ví dụ:

```java
Path path = Path.of("data", "reports", "..", "images", ".", "logo.png");
Path normalized = path.normalize();
```

Đoạn minh họa cần `import java.nio.file.Path;`. `normalized` có những name element `data`, `images`, `logo.png`. Hình thức chuỗi khi in có thể dùng `/` hoặc `\\` tùy provider và hệ điều hành, vì vậy ví dụ kiểm thử nên so sánh **`Path` với `Path`** thay vì kỳ vọng literal đường dẫn Unix trên Windows.

## 3. normalize() xử lý chính xác điều gì?

Theo hợp đồng `Path.normalize()` trong Java, kết quả loại bỏ các name element dư thừa như `.` và những cặp `name/..` có thể triệt tiêu theo cú pháp. Một số nguyên tắc:

- Một thành phần `.` thường bị loại bỏ.
- Một thành phần tên bình thường ngay trước `..` có thể bị triệt tiêu cùng `..`.
- Một `..` ở đầu một đường dẫn tương đối mà không có tên trước nó để triệt tiêu thường **được giữ lại**.
- Phần root của đường dẫn tuyệt đối được giữ theo quy tắc provider; việc gặp `..` ở sát root không thể suy ra rằng có thể đi lên vô hạn.
- Kết quả vẫn là một `Path` theo cùng filesystem provider; phương thức không bắt buộc trả đúng cùng object instance.
- Gọi `normalize()` trên kết quả một lần nữa không cần làm thay đổi biểu diễn đã được chuẩn hóa (tính idempotent về giá trị).

Một số ví dụ **cú pháp** với dấu `/` để dễ nhìn, không phải khẳng định mọi OS sẽ in cùng dấu phân cách:

| Đường dẫn đầu vào | Sau normalize | Ý nghĩa |
| --- | --- | --- |
| `a/./b` | `a/b` | Bỏ `.` |
| `a/x/../b` | `a/b` | Triệt tiêu cặp `x/..` |
| `a/b/../../c` | `c` | Triệt tiêu hai cấp tên |
| `../a/./b` | `../a/b` | Giữ `..` đầu đường dẫn tương đối |
| `a/../../b` | `../b` | Chỉ triệt tiêu được một cặp `a/..` |
| `a/b` | `a/b` | Đã gọn, không cần biến đổi |

**Không đồng nhất việc rút gọn cú pháp với đường đi thực tế trên đĩa.** Khi gặp symbolic link hoặc các đặc tính filesystem đặc biệt, loại bỏ một cặp `name/..` có thể thay đổi **tệp vật lý** mà đường dẫn sẽ phân giải đến.

### Điều normalize() không làm

`normalize()` **không**:

- Kiểm tra `Files.exists(path)`.
- Mở file hoặc đọc nội dung file.
- Kiểm tra quyền đọc/ghi.
- Theo symbolic link để biết mục tiêu thật.
- Tự biến đường dẫn tương đối thành tuyệt đối.
- Chứng minh hai `Path` khác nhau trỏ tới cùng inode/file.
- Phát hiện chắc chắn traversal attack hoặc xác nhận input người dùng an toàn.
- Đảm bảo dữ liệu đã được “canonical hóa” theo trạng thái hiện tại của filesystem.
- Tạo thư mục, xóa tệp hoặc thay đổi working directory.

Một số phương thức `Path` như `toRealPath()` mới cần truy cập hệ thống tệp và có thể ném `IOException`.

## 4. Ví dụ Java 17 chạy được: normalize thuần cú pháp

Chương trình này không tạo hoặc đọc bất kỳ file nào. Kết quả cố ý dựa vào `Path.equals` và số name element để tránh phụ thuộc dấu phân cách trên Windows/Unix.

**Tệp `NormalizeBasics.java`:**

```java
import java.nio.file.Path;

public class NormalizeBasics {
    public static void main(String[] args) {
        Path original = Path.of(
                "data", "reports", "..", "images", ".", "logo.png");
        Path expected = Path.of("data", "images", "logo.png");
        Path normalized = original.normalize();

        System.out.println("Original names: " + original.getNameCount());
        System.out.println("Normalized names: " + normalized.getNameCount());
        System.out.println("Expected path: " + normalized.equals(expected));
        System.out.println("Still relative: " + !normalized.isAbsolute());
        System.out.println("Idempotent: "
                + normalized.normalize().equals(normalized));

        Path leadingParent = Path.of("a", "..", "..", "b").normalize();
        System.out.println("Leading .. retained: "
                + leadingParent.equals(Path.of("..", "b")));
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac NormalizeBasics.java
java NormalizeBasics
```

**Stdout chính xác:**

```text
Original names: 6
Normalized names: 3
Expected path: true
Still relative: true
Idempotent: true
Leading .. retained: true
```

Đoạn code không gọi `Files.exists`, `Files.readString` hay `Files.newInputStream`. Dù đường dẫn `data/images/logo.png` không hề tồn tại, việc `normalize()` vẫn hợp lệ. Điều này chứng minh rằng **phép biến đổi chỉ dựa trên các thành phần đường dẫn**, không cần kiểm tra đích trên đĩa.

### Hai điều cần nhớ trong ví dụ

1. `original.getNameCount()` đếm các thành phần hiện hữu trong Path, gồm cả `..` và `.`, nên khác số thành phần của `normalized`.
2. `Path.equals` so sánh các biểu diễn Path theo filesystem provider và các quy tắc của nó; không đảm bảo kết luận về **hai file vật lý** khi có liên kết hoặc nhiều cách đặt tên.

## 5. Path.normalize(), toAbsolutePath() và toRealPath() khác nhau

Ba phương thức này rất dễ bị đánh đồng:

| Phương thức | Đọc thông tin filesystem? | Kết quả/ý nghĩa |
| --- | --- | --- |
| `path.normalize()` | Không cần | Rút gọn thành phần cú pháp như `.`, `name/..` |
| `path.toAbsolutePath()` | Chuyển thành biểu diễn tuyệt đối theo provider; không có nghĩa là kiểm tra file tồn tại | Một `Path` tuyệt đối, có thể vẫn có thành phần cần normalize |
| `path.toRealPath()` | Có, tra cứu theo filesystem | Đường dẫn tuyệt đối, thực tế, được xử lý theo trạng thái filesystem (mặc định theo liên kết) và có thể ném `IOException` |

Cần đọc hợp đồng của provider; trên filesystem mặc định, `toAbsolutePath()` thường dùng working directory để đổi đường dẫn tương đối. Nhưng phương thức này **không đồng nghĩa** với `toRealPath()`, và không bảo đảm file tồn tại.

Hai biểu thức thường gặp:

```java
Path absoluteAndLexical = path.toAbsolutePath().normalize();
Path real = path.toRealPath();
```

Đây là **đoạn minh họa** với `Path path` và xử lý `IOException`. Biểu thức đầu cho một đường dẫn tuyệt đối đã loại bỏ thành phần dư thừa theo cú pháp; biểu thức sau truy cập filesystem để tìm đường dẫn thực.

**Không thay `toRealPath()` bằng `toAbsolutePath().normalize()`** nếu thuật toán phụ thuộc vào symbolic link, nhận dạng file hoặc vị trí đích đã được phân giải. Hai biểu thức có thể trả Path khác nhau dù xuất phát từ cùng input.

### toRealPath và LinkOption.NOFOLLOW_LINKS

Thông thường `toRealPath()` phân giải symbolic link và yêu cầu đường dẫn thực sự tồn tại. Một biến thể:

```java
Path result = path.toRealPath(LinkOption.NOFOLLOW_LINKS);
```

Đây là đoạn minh họa cần `java.nio.file.LinkOption`, `Path` và xử lý `IOException`. Khi đưa `NOFOLLOW_LINKS`, cách xử lý symbolic link thay đổi theo hợp đồng của API, vì vậy `result` không nên được hiểu là cùng ý nghĩa với `path.toRealPath()` mặc định. Dù có tùy chọn không theo liên kết, lời gọi vẫn là **hoạt động filesystem**, khác `normalize()`.

## 6. Ví dụ thực tế: tồn tại file mới cần toRealPath

Một đoạn chương trình có thể tạo một file tạm, rồi so sánh biểu diễn cú pháp với kết quả thực tế:

**Tệp `RealPathDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RealPathDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("normalize-demo-");
        Path child = directory.resolve("child");
        Path file = directory.resolve("sample.txt");

        try {
            Files.createDirectory(child);
            Files.writeString(file, "ok", StandardCharsets.UTF_8);

            Path withDots = child.resolve("..").resolve("sample.txt");
            Path lexical = withDots.normalize();

            System.out.println("Lexical equals file path: "
                    + lexical.equals(file));
            System.out.println("Real paths equal: "
                    + withDots.toRealPath().equals(file.toRealPath()));
            System.out.println("Same file: "
                    + Files.isSameFile(withDots, file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(child);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac RealPathDemo.java
java RealPathDemo
```

**Stdout trong điều kiện file tạm được tạo/xóa thành công, không có thay đổi đồng thời:**

```text
Lexical equals file path: true
Real paths equal: true
Same file: true
```

Trong ví dụ, `child` là thư mục thật, `..` thường trỏ trở về `directory`, nên cả ba phép so sánh đều đúng. Nhưng đây là điều kiện **mà chương trình đã tạo và kiểm soát**. Với một component là symbolic link, kết quả có thể khác, và bước `normalize()` có thể không bảo toàn ý nghĩa đường dẫn đối với việc truy cập thật.

Không nên dùng `Files.exists()` rồi xem đó là bằng chứng file sẽ tiếp tục tồn tại đến khi đọc: filesystem có thể bị thay đổi giữa lúc kiểm tra và lúc sử dụng (**TOCTOU** — time of check to time of use).

## 7. Rủi ro lớn nhất: symbolic link làm lexical normalize khác thực tế

Giả sử cấu trúc file:

```text
/work/
├── data/
│   ├── notes.txt
│   └── alias  -> /shared/reports   (symbolic link)
└── ...
/shared/
├── notes.txt
└── reports/
```

Xét đường dẫn:

```text
/work/data/alias/../notes.txt
```

**Rút gọn thuần cú pháp** bằng `normalize()` loại cặp `alias/..`, tạo:

```text
/work/data/notes.txt
```

Nhưng **phân giải vật lý** khi hệ điều hành đi qua `alias` (trỏ đến `/shared/reports`) có thể khiến phần `..` đi lên thư mục cha của đích symlink và trỏ đến:

```text
/shared/notes.txt
```

Vì vậy, theo trạng thái filesystem và cách thực hiện path resolution, đường dẫn trước/sau normalize có thể **trỏ đến hai file khác nhau**.

Đây là lý do tài liệu `Path.normalize()` cảnh báo: loại bỏ `name/..` có thể đổi kết quả tìm file nếu `name` là symbolic link. **Không dùng `normalize()` như bằng chứng rằng đã truy cập đúng file mong muốn.**

### Một vấn đề nữa: symbolic link không phải dữ liệu tĩnh

Ngay cả khi vừa gọi `toRealPath()` và kiểm tra kết quả, một tác nhân khác có quyền thay đổi cây thư mục có thể **thay symbolic link** trước khi lời gọi mở file tiếp theo. Đó là tình huống race condition. Với hệ thống có yêu cầu an ninh cao, thiết kế cần ràng buộc quyền truy cập ở cấp filesystem, dùng thao tác gắn với directory handle hoặc cơ chế tương đương thay vì chỉ kiểm tra chuỗi Path rồi mở lại tên.

## 8. normalize không có nghĩa đường dẫn an toàn

Một sai lầm thường gặp trong hệ thống phục vụ file:

```java
Path candidate = base.resolve(userInput).normalize();
return Files.readAllBytes(candidate);
```

Đây là đoạn minh họa **chưa có kiểm tra an toàn**, cần `Path base`, `Path userInput`, `Files` và xử lý `IOException`. Nếu userInput chứa `..` hoặc là đường dẫn tuyệt đối, `candidate` có thể trỏ **ra ngoài thư mục được phép**. `normalize()` chỉ làm rõ biểu diễn đó chứ không chặn truy cập.

Ví dụ:

```text
base:        /srv/app/public
userInput:   ../private/secret.txt
resolve:     /srv/app/public/../private/secret.txt
normalize:   /srv/app/private/secret.txt
```

Kết quả đã loại `..`, nhưng vẫn ở **ngoài** `/srv/app/public`.

**Quan trọng:** với `Path.resolve(other)`, nếu `other` là đường dẫn tuyệt đối theo provider, kết quả có thể bỏ qua `base` và dùng `other` trực tiếp. Không thể giả định `base.resolve(userInput)` luôn nằm dưới base.

### Một kiểm tra cú pháp (chỉ dùng trong tình huống phù hợp)

```java
Path normalizedBase = base.toAbsolutePath().normalize();
Path candidate = normalizedBase.resolve(userInput).normalize();

if (!candidate.startsWith(normalizedBase)) {
    throw new SecurityException("Path escapes permitted directory");
}
```

Đây là đoạn **minh họa lexical containment**. Nó kiểm tra candidate có nằm dưới base ở cấp các thành phần Path hay không, sau khi rút gọn cú pháp. Tuy nhiên **nó chưa ngăn symbolic link ở bên trong base trỏ ra ngoài** và không chống được race khi thư mục/file bị thay đổi giữa bước kiểm tra và bước mở.

Tùy ứng dụng, cần thêm:

- Kiểm tra loại/đặc tính input hợp lệ từ người dùng.
- Xác nhận real root và real candidate qua filesystem khi target đã tồn tại.
- Cẩn trọng nếu target mới **chưa tồn tại** vì `toRealPath()` của target chưa dùng được; có thể cần kiểm tra parent thật và áp dụng cơ chế tạo file an toàn.
- Sử dụng quyền filesystem chặt chẽ, sandbox/container và directory-handle-based operations khi cần bảo vệ chống race.
- Thiết kế chính sách symbolic link rõ ràng (cho phép, cấm hay chỉ cho phép trong một cây thư mục nhất định).

**`normalize()` là bước hữu ích để xử lý cú pháp, không phải hệ thống kiểm soát truy cập.**

## 9. startsWith(Path) khác String.startsWith

Một lỗi an toàn phổ biến là dùng:

```java
candidate.toString().startsWith(base.toString())
```

Đây là phép so sánh **tiền tố ký tự**, nên `/data/public2` cũng bắt đầu bằng `/data/public` dù là thư mục khác.

`Path.startsWith(Path)` so sánh **các name element của đường dẫn** theo provider; nó tránh lỗi đồng nhất tiền tố văn bản với tổ tiên thực của Path. Tuy nhiên, như đã nói, nó vẫn chỉ xét biểu diễn Path và **không tự phân giải symbolic link**.

### Ví dụ Java 17 chạy được: tiền tố chuỗi đánh lừa

**Tệp `PathPrefixDemo.java`:**

```java
import java.nio.file.Path;

public class PathPrefixDemo {
    public static void main(String[] args) {
        Path base = Path.of("public").toAbsolutePath().normalize();
        Path sibling = base.resolveSibling("public-backup")
                .resolve("config.txt").normalize();

        System.out.println("String prefix: "
                + sibling.toString().startsWith(base.toString()));
        System.out.println("Path prefix: " + sibling.startsWith(base));

        Path escape = base.resolve("..").resolve("outside.txt").normalize();
        System.out.println("Escaping .. rejected lexically: "
                + !escape.startsWith(base));
    }
}
```

Chạy:

```bash
javac PathPrefixDemo.java
java PathPrefixDemo
```

**Stdout chính xác trên filesystem mặc định thông thường:**

```text
String prefix: true
Path prefix: false
Escaping .. rejected lexically: true
```

Mục tiêu là minh họa hai tầng so sánh: string prefix nhìn thấy cùng tiền tố `public`, còn Path prefix nhận ra `public-backup` là tên khác. Dù `Path.startsWith` đúng hơn khi nói về đường dẫn, nó không thay thế kiểm tra **real path và chính sách filesystem** trong tình huống an ninh.

## 10. So sánh đường dẫn: equals, normalize, isSameFile, toRealPath

Các API khác nhau trả lời các câu hỏi khác nhau:

| API | Trả lời câu hỏi |
| --- | --- |
| `a.equals(b)` | Hai đối tượng Path được coi là bằng nhau về biểu diễn theo provider hay không? |
| `a.normalize().equals(b.normalize())` | Hai biểu diễn sau rút gọn cú pháp có giống nhau không? |
| `a.toAbsolutePath().normalize()` | Đường dẫn tuyệt đối rút gọn cú pháp nhìn như thế nào? |
| `a.toRealPath()` | Đường dẫn thực tới entry hiện tồn tại theo filesystem là gì? |
| `Files.isSameFile(a, b)` | Hai Path có định danh cùng file ở thời điểm kiểm tra theo filesystem hay không? |

`Files.isSameFile` có thể ném `IOException`; tùy filesystem, nó có thể xử lý symbolic link, hard link và nhận dạng file theo provider. `Path.equals` đơn thuần không được dùng để khẳng định hai đường dẫn khác chữ là hai file khác nhau.

Ví dụ:

```text
/var/data/current.txt -> /var/data/releases/v2.txt  (symlink)
```

`Path.of("/var/data/current.txt")` và `Path.of("/var/data/releases/v2.txt")` rõ ràng có name element khác nhau, nên lexical equality có thể là `false`. Nhưng nếu symlink đang trỏ tới tệp đó, `Files.isSameFile` có thể là `true`. Hãy chọn API theo câu hỏi thật sự cần trả lời.

Một `Path` có thể bị thay đổi ý nghĩa vật lý theo thời gian dù chính đối tượng Java không đổi, vì filesystem là trạng thái bên ngoài. Kiểm tra hôm nay không phải một xác nhận mãi mãi.

## 11. resolve, relativize và normalize: thứ tự có ý nghĩa

Các thao tác Path có thể được kết hợp, nhưng thứ tự biến đổi cần theo mục tiêu.

### resolve: ghép đường dẫn

```java
Path base = Path.of("docs");
Path child = base.resolve("chapters").resolve("..").resolve("intro.md");
Path result = child.normalize(); // docs/intro.md theo cú pháp.
```

`resolve()` ghép đường dẫn ở cấp provider. Nó **không đọc filesystem**. Một thành phần `..` sau khi resolve vẫn cần normalize nếu muốn biểu diễn gọn.

### relativize: tìm đường đi tương đối giữa hai Path

```java
Path a = Path.of("docs", "java");
Path b = Path.of("docs", "images", "logo.png");
Path relative = a.relativize(b);
```

Đoạn này tạo một relative Path theo các phần tên. Đối với các provider phổ biến, có thể có dạng `../images/logo.png`. `relativize` thường yêu cầu các Path có hình thức tương thích (ví dụ cùng tuyệt đối hoặc cùng tương đối và cùng provider); nếu không, có thể ném `IllegalArgumentException`.

**`relativize` cũng mang ý nghĩa cú pháp**; nó không khám phá symlink hay đường đi vật lý “ngắn nhất” giữa hai vị trí thật.

### Thứ tự với toAbsolutePath

Trong các ứng dụng thông thường, `base.toAbsolutePath().normalize().resolve(relative).normalize()` giúp có một biểu diễn tuyệt đối có thể dự đoán. Nhưng nếu mục tiêu là định danh file thật, bước `toRealPath()` hoặc một chiến lược filesystem-aware mới giải quyết phần đó.

Không suy luận kết quả `resolve`, `relativize`, `normalize` từ chuỗi thô theo hệ điều hành khác mà không tính tới root, ổ đĩa, UNC paths hoặc provider.

## 12. normalize và đường dẫn tương đối có ..

Nếu một đường dẫn tương đối bắt đầu bằng `..`, `normalize()` không thể biết thư mục cha nào là “đúng” nếu không có ngữ cảnh:

```java
Path p = Path.of("..", "data", ".", "info.txt");
Path n = p.normalize();
System.out.println(n.equals(Path.of("..", "data", "info.txt")));
```

Đoạn trên minh họa giá trị `true`. `..` đầu được giữ vì không có một thành phần tên bình thường nào đứng trước nó để rút gọn. Việc cố tự xóa mọi `..` khỏi path có thể tạo ra một đường dẫn mang **ý nghĩa khác**, không phải normalize.

Đừng giải quyết traversal bằng cách xóa các đoạn `..` dưới dạng chuỗi. Cách đó dễ có lỗi khi xử lý các separator, encoding, provider và symbolic link. Cần quy ước rõ về đầu vào hợp lệ và ranh giới truy cập.

## 13. normalize không liên quan đến Unicode normalization

Tên `normalize` trong `Path.normalize()` dễ gây liên tưởng nhầm tới chuẩn hóa Unicode như NFC, NFD. Đây là hai khái niệm **hoàn toàn khác nhau**:

- `Path.normalize()`: rút gọn **cấu trúc path**, ví dụ `a/./b` thành `a/b`.
- `java.text.Normalizer.normalize(text, form)`: chuẩn hóa **biểu diễn Unicode**, ví dụ các chuỗi code point có ý nghĩa kết hợp tương đương.

`Path.normalize()` không biến tên `café.txt` ở một dạng Unicode sang dạng khác chỉ vì tên chứa dấu. Hành vi so sánh tên file với Unicode, case sensitivity và normalization vật lý còn phụ thuộc filesystem/provider.

Nếu cần quản lý tên file đa ngôn ngữ, phải hiểu đặc tính filesystem mục tiêu và quy ước ứng dụng; `Path.normalize()` không phải công cụ giải quyết mọi vấn đề Unicode của tên file.

## 14. normalize không đảm bảo an toàn khi thao tác tệp

Các tình huống thực tế cần chú ý:

### 14.1 File không tồn tại

`Path.of("missing/../a.txt").normalize()` vẫn tạo một Path rút gọn mà không ném `NoSuchFileException` chỉ vì các thư mục chưa tồn tại. Nếu sau đó `Files.newInputStream` được gọi, nó mới có thể phát sinh lỗi filesystem.

### 14.2 Quyền truy cập

`normalize()` không kiểm tra quyền. Một path trông hợp lệ có thể không đọc được vì quyền trên thư mục cha, ACL, sandbox hoặc khóa tệp.

### 14.3 Symbolic link và hard link

`normalize()` không phân giải liên kết. Hai đường dẫn có biểu diễn khác nhau có thể chỉ về cùng file; hoặc một đường dẫn thay đổi ý nghĩa sau khi symlink được cập nhật.

### 14.4 Race conditions

Ngay cả `toRealPath()`, `Files.exists()` hay `Files.isSameFile()` chỉ phản ánh trạng thái tại lúc truy vấn; filesystem có thể thay đổi sau đó. Với đầu vào không tin cậy, không nên dựa duy nhất vào mẫu “check rồi mở” để bảo vệ khỏi kẻ thay đổi cây thư mục đồng thời.

### 14.5 Khác biệt provider và nền tảng

`Path` phụ thuộc filesystem provider. Root, separator, drive letter, đường dẫn UNC, định dạng case và khả năng symbolic link khác nhau giữa các hệ. Code cần chạy trên nhiều nền tảng nên dùng API Path thay vì ghép dấu `/` hoặc `\\` thủ công. Khi kiểm thử, so sánh Path hoặc các thuộc tính thay vì mặc định mọi máy đều in đúng một đường dẫn string.

### 14.6 Di chuyển và tạo tệp mới

Nếu target chưa tồn tại, `toRealPath()` có thể thất bại. Trong quy trình upload hoặc tạo file, cần phân biệt phần thư mục đã tồn tại, quy tắc được phép ghi, và khả năng kẻ khác thay parent/symlink. Chỉ `normalize()` và `startsWith()` không đủ bảo đảm chống traversal/race trong môi trường có đối thủ.

## 15. Một cách kiểm tra vị trí file hiện hữu (và giới hạn)

Với file **đã tồn tại**, một hướng kiểm tra filesystem-aware ở mức cơ bản:

```java
static Path validateExistingFile(Path permittedRoot, Path request)
        throws IOException {
    Path realRoot = permittedRoot.toRealPath();
    Path realTarget = realRoot.resolve(request).toRealPath();

    if (!realTarget.startsWith(realRoot)) {
        throw new SecurityException("Outside permitted root");
    }
    return realTarget;
}
```

Đây là **phương thức minh họa**, cần `Path`, `IOException`; không phải giao thức an ninh hoàn chỉnh. Lời gọi `toRealPath()` phân giải vị trí thực và cần mục tiêu tồn tại. `realTarget.startsWith(realRoot)` sau đó so sánh các name element **trên đường dẫn thực đã được xác định tại thời điểm kiểm tra**.

Tuy nhiên:

- Nếu resource nằm ngoài root, phương thức từ chối; nếu không tồn tại hoặc không được phép truy cập, `toRealPath()` ném lỗi.
- Nếu một attacker có thể thay symlink giữa validate và thao tác open tiếp theo, có thể xảy ra **TOCTOU**.
- Nếu phải tạo file mới, target chưa tồn tại không thể được xử lý nguyên xi bằng cách này.
- Nếu có nhiều filesystem provider, các `Path` không tương thích có thể gây lỗi khi `resolve` hoặc so sánh.
- Chính sách có cho phép symlink, mount point, hard link hay không cần được quy định riêng theo yêu cầu ứng dụng.

Với tác vụ an ninh cao, xem xét phương pháp thao tác tương đối tới directory handle, chẳng hạn `SecureDirectoryStream` khi provider hỗ trợ, và hạn chế quyền của tiến trình. **Không một lời gọi `normalize()` đơn lẻ tạo ra biên an ninh.**

## 16. Câu hỏi tự kiểm tra

1. Vì sao `Path.of("a","..","b").normalize()` trả một Path hợp lệ ngay cả khi thư mục `a` không tồn tại?
2. Nêu khác biệt giữa `normalize()`, `toAbsolutePath()`, `toRealPath()` và `Files.isSameFile()`.
3. Chạy `NormalizeBasics` trên Java 17. Thay `"reports", ".."` bằng `"reports", "2026", "..", ".."` rồi dự đoán số name element trước/sau.
4. Viết test chứng minh `Path.of("..","a").normalize()` vẫn có `..` ở đầu.
5. Vẽ cấu trúc filesystem có symlink `alias` rồi giải thích tại sao đường dẫn `alias/../x` có thể không tương đương với việc xóa hai thành phần ấy.
6. Chạy `PathPrefixDemo`, thay `public-backup` bằng `public2`; giải thích tại sao kiểm tra chuỗi vẫn gây nhầm lẫn.
7. Với input `../private/secret.txt` và root `/srv/app/public`, hãy tính kết quả của `resolve` và `normalize`. Vì sao không thể gọi kết quả ấy là “safe path”?
8. Tạo một tệp tạm, gọi `toRealPath()`, rồi thử `toRealPath()` trên một tệp không tồn tại. Phân biệt kết quả với `normalize()`.
9. Thiết kế một hàm nhận đường dẫn do người dùng cung cấp và chỉ cho phép đọc file hiện hữu trong root. Nêu các bước kiểm tra cùng giới hạn TOCTOU.
10. Hãy giải thích vì sao `Path.normalize()` không đồng nghĩa với Unicode NFC/NFD và không sửa mọi vấn đề về tên file đa ngôn ngữ.
11. Với một Path tương đối và một Path tuyệt đối thuộc cùng filesystem, điều gì có thể xảy ra khi gọi `relativize` trực tiếp?
12. Trình bày trường hợp `Files.isSameFile(a,b)` trả true nhưng `a.normalize().equals(b.normalize())` là false.

## 17. Những lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `normalize()` rồi nghĩ file chắc chắn tồn tại | Lỗi khi mở file | Dùng Files API phù hợp và xử lý `IOException` |
| Coi `normalize()` là kiểm tra quyền | Quyền truy cập vẫn có thể bị từ chối | Kiểm tra ở lúc thao tác thật; quản lý exception |
| Coi `normalize()` là canonical path vật lý | Sai khi có symlink | Dùng `toRealPath` khi cần đường dẫn thực |
| So `Path.equals` để khẳng định là cùng file | Có thể bỏ qua symlink/hard link | Dùng `Files.isSameFile` khi cần |
| So `candidate.toString().startsWith(base.toString())` | `public2` trùng tiền tố `public` | Dùng `Path.startsWith` cho so sánh thành phần |
| Dùng `normalize().startsWith(root)` như kiểm soát truy cập tuyệt đối | Symlink/race có thể thoát root | Chính sách filesystem-aware và cơ chế chống race |
| Coi `toAbsolutePath()` là `toRealPath()` | Chưa phân giải symlink và chưa chứng minh tồn tại | Chọn đúng API theo mục tiêu |
| Xóa mọi đoạn `..` bằng xử lý string | Có thể đổi ý nghĩa path và tạo lỗi bảo mật | Làm việc với Path và chính sách input rõ ràng |
| Dùng `File.separator` ghép string khắp nơi | Dễ sai provider/platform | `Path.of`, `resolve`, `getParent` |
| Cho rằng normalize giống Unicode normalization | Không xử lý vấn đề Unicode trong tên file | Dùng API Unicode riêng khi thực sự cần |
| Kiểm tra file rồi mặc định trạng thái không thể đổi | TOCTOU | Thiết kế thao tác an toàn ở cấp filesystem |
| Normalize rồi ghi đè file được user cung cấp mà không xác minh root | Có nguy cơ truy cập ngoài phạm vi | Validation thực tế và giới hạn quyền truy cập |

## 18. Ghi nhớ

**`Path.normalize()` chỉ xử lý cấu trúc cú pháp của đường dẫn.** Nó hữu ích để loại `.`, triệt tiêu những cặp `name/..` có thể triệt tiêu và tạo Path gọn hơn cho các phép toán khác.

Nhưng normalize **không** đảm bảo tệp tồn tại, quyền truy cập hợp lệ, đường dẫn vật lý đúng theo ý muốn hoặc input người dùng không thể vượt khỏi thư mục cho phép. Khi cần nhận dạng file, dùng `Files.isSameFile` hoặc `toRealPath` theo hợp đồng; khi cần bảo vệ vùng lưu trữ, xem xét symbolic link và rủi ro thay đổi đồng thời.

**Mental model:** `normalize` trả lời “đường dẫn này rút gọn theo ký hiệu như thế nào?”, còn việc truy cập filesystem mới có thể trả lời “tệp thực tế ở đâu và có đọc/ghi được không?”.

### Tài liệu tham khảo

- [Java SE 17: `Path.normalize()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#normalize()) và [`Path.toRealPath()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#toRealPath(java.nio.file.LinkOption...)).
- [Java SE 17: `Files.isSameFile()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path)).
- [Java SE 17: `SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html) — cơ chế phù hợp cho một số thao tác directory-handle-based khi provider hỗ trợ.
