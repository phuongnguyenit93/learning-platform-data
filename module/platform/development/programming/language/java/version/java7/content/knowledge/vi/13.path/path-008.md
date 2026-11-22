# Kiểm tra tiền tố, hậu tố và quan hệ đường dẫn với `Path` trong Java

## 1. Mục tiêu: so sánh đường dẫn theo thành phần, không theo chuỗi

Khi thao tác với tệp và thư mục, chúng ta thường hỏi:

- Một đường dẫn có bắt đầu từ một thư mục gốc nhất định không?
- Một đường dẫn có kết thúc bằng tên tệp hoặc chuỗi **thành phần tên** nào không?
- Hai đường dẫn có biểu diễn cùng một **giá trị đường dẫn** không?
- Có thể tính đường tương đối từ thư mục này đến tệp kia không?
- Hai tên đường dẫn khác nhau có thực sự chỉ tới cùng một tệp hay không?

Java NIO.2 cung cấp interface `java.nio.file.Path`, có từ **Java 7** và vẫn được sử dụng trong Java hiện đại. Hai phương thức trọng tâm là:

```java
boolean prefix = path.startsWith(other);
boolean suffix = path.endsWith(other);
```

Các biểu thức này là **đoạn minh họa trong phương thức**; `path` và `other` cần là biến kiểu `Path` đã khai báo. `startsWith` và `endsWith` kiểm tra **cấu trúc đường dẫn**, **không phải** tiền tố/hậu tố ký tự của `String`.

Ví dụ:

```java
import java.nio.file.Path;

Path base = Path.of("workspace", "reports");
Path report = Path.of("workspace", "reports", "2026", "summary.txt");

boolean insideByNames = report.startsWith(base);          // true
boolean endsWithFile = report.endsWith("summary.txt");     // true
boolean endsWithExtension = report.endsWith(".txt");       // false
```

`Path.of` xuất hiện từ **Java 11**; với Java 7/8 có thể dùng `java.nio.file.Paths.get(...)`. Các khái niệm `Path`, `startsWith`, `endsWith`, `resolve`, `relativize` và `normalize` vẫn áp dụng từ Java 7 tới Java 17+.

**Quy tắc tổng quát:** Một đường dẫn là **giá trị thuộc một `FileSystem`**, không phải chính tệp trên ổ đĩa. Kiểm tra quan hệ theo thành phần đường dẫn thông thường **không đòi tệp tồn tại**. Khi cần nhận dạng tệp thực hoặc kiểm soát truy cập, phải dùng thêm API hệ thống tệp và cơ chế bảo vệ phù hợp.

## 2. Các thành phần tên, root và đường dẫn tương đối/tuyệt đối

Để hiểu tiền tố/hậu tố, hãy tách đường dẫn thành các **thành phần tên**:

```text
workspace / reports / 2026 / summary.txt
    0          1       2         3
```

Đây là **cách biểu diễn minh họa**, không phải định dạng đường dẫn duy nhất của mọi hệ điều hành. Trên Windows, `Path.toString()` thông thường dùng separator `\`; trên Unix thường là `/`. Quan hệ `Path` do **file-system provider** quyết định.

Xét các câu lệnh:

```java
Path report = Path.of("workspace", "reports", "2026", "summary.txt");

Path name = report.getFileName(); // summary.txt
Path parent = report.getParent(); // workspace/reports/2026 (minh họa dấu /)
Path first = report.getName(0);  // workspace

boolean absolute = report.isAbsolute(); // false
Path root = report.getRoot();            // null
```

Đây là các câu lệnh minh họa trong phương thức có `import java.nio.file.Path;`.

- `getFileName()` chỉ lấy thành phần tên cuối. Nó **không kiểm tra** rằng tệp `summary.txt` tồn tại hoặc là tệp thông thường.
- `getParent()` lấy phần giá trị đường dẫn đứng trước thành phần cuối, **không tự mở thư mục cha**.
- `getRoot()` có thể là `null` nếu `Path` là đường dẫn tương đối.
- `Path.of("summary.txt").getParent()` có thể trả `null`. Không gọi `getParent().resolve(...)` nếu chưa kiểm tra.
- `getNameCount()` cho biết số thành phần tên, nhưng không phải độ sâu vật lý đã xác minh trên hệ thống tệp.

**Tương đối và tuyệt đối:** Đường dẫn tương đối như `workspace/reports/summary.txt` không có root; đường dẫn tuyệt đối gắn với root và ngữ cảnh provider. Trên Windows root có thể liên quan tới ổ đĩa hoặc UNC; trên Unix thường là `/`. `startsWith`/`endsWith` cần được hiểu trong **ngữ cảnh dạng đường dẫn và hệ thống tệp**, không chỉ so chuỗi hiển thị.

## 3. `Path.startsWith`: kiểm tra tiền tố theo thành phần

### 3.1. Mẫu cơ bản

```java
Path directory = Path.of("workspace", "reports");
Path file = Path.of("workspace", "reports", "2026", "summary.txt");

System.out.println(file.startsWith(directory)); // true
```

Ở ví dụ này, hai thành phần đầu của `file` là `workspace` và `reports`, trùng với toàn bộ `directory`. Cú pháp hỗ trợ cả overload nhận `Path` và overload nhận `String`:

```java
boolean a = file.startsWith(Path.of("workspace", "reports"));
boolean b = file.startsWith("workspace"); // String được diễn giải là Path.
```

Với `startsWith(String)`, chuỗi được diễn giải **thành một giá trị đường dẫn theo file system tương ứng**. Nó **không** tương đương với `file.toString().startsWith(text)`.

### 3.2. Vì sao tiền tố chuỗi dễ sai?

Giả sử có hai thư mục gần giống tên:

```java
Path allowed = Path.of("workspace", "reports");
Path lookalike = Path.of("workspace", "reports-old", "draft.txt");

boolean stringCheck =
        lookalike.toString().startsWith(allowed.toString()); // true
boolean pathCheck = lookalike.startsWith(allowed);           // false
```

Cả hai biểu thức chạy trên đường dẫn tương đối trong hệ thống tệp mặc định thông thường:

- `"workspace/reports-old/draft.txt"` **bắt đầu về ký tự** bằng `"workspace/reports"`.
- Nhưng thành phần tên thứ hai là `reports-old`, **không bằng** `reports`. Do vậy `Path.startsWith` trả `false`.

Đây là lý do cần chọn phép so sánh theo thành phần khi muốn xác định vị trí logic thuộc nhánh nào.

**Cảnh báo bảo mật:** `Path.startsWith` đúng về cấu trúc tên **chưa đủ** để chứng minh tệp thực nằm trong thư mục được phép: các thành phần `..`, symbolic link và race condition phải được xem xét riêng ở mục 11.

### 3.3. Những quan hệ tiền tố khác

| Đường dẫn đang kiểm tra | Tiền tố đưa vào | Kết quả minh họa |
| --- | --- | --- |
| `workspace/reports/2026/summary.txt` | `workspace` | `true` |
| `workspace/reports/2026/summary.txt` | `workspace/reports` | `true` |
| `workspace/reports/2026/summary.txt` | `workspace/reports/2026` | `true` |
| `workspace/reports/2026/summary.txt` | `workspace/images` | `false` |
| `workspace/reports-old/draft.txt` | `workspace/reports` | `false` |
| `workspace/reports/2026/summary.txt` | Chính đường dẫn đó | `true` |

Ví dụ áp dụng cho các `Path` tương đối có cùng provider. Khi **đối số có root** hoặc thuộc file system khác, quy tắc matching phụ thuộc hợp đồng `Path`/provider và tính tương thích; không tự trộn đường dẫn Windows, Unix hoặc ZIP file system rồi mong kết quả giống nhau.

## 4. `Path.endsWith`: kiểm tra hậu tố theo thành phần

### 4.1. Hậu tố có thể gồm một hoặc nhiều thành phần

```java
Path report = Path.of("workspace", "reports", "2026", "summary.txt");

boolean endByName = report.endsWith("summary.txt"); // true
boolean endByPath =
        report.endsWith(Path.of("2026", "summary.txt")); // true
```

Khác với việc hỏi “tên file có mấy ký tự cuối”, `Path.endsWith` xem phần cuối của đường dẫn có **các thành phần tên khớp** hay không.

Ví dụ:

```text
workspace / reports / 2026 / summary.txt
                      \________________/
                         hậu tố Path
```

`Path.of("2026", "summary.txt")` khớp vì nó bao gồm hai thành phần cuối. `Path.of("reports", "2026", "summary.txt")` cũng khớp với ba thành phần cuối.

### 4.2. `endsWith(".txt")` không phải kiểm tra phần mở rộng tệp

```java
Path report = Path.of("workspace", "reports", "2026", "summary.txt");

System.out.println(report.endsWith("summary.txt")); // true
System.out.println(report.endsWith(".txt"));        // false
```

Hậu tố `Path` `".txt"` được hiểu là **một thành phần tên nguyên vẹn** có giá trị `.txt`. Nó không khớp với thành phần `summary.txt`.

Khi thật sự cần hỏi **chuỗi tên tệp** kết thúc bằng `.txt`, có thể dùng:

```java
Path fileName = report.getFileName();

boolean hasTxtSuffix = fileName != null
        && fileName.toString().endsWith(".txt");
```

Đây là **kiểm tra hậu tố chuỗi của tên cuối**, không phải `Path.endsWith`. Nó không chứng minh đường dẫn dẫn tới tệp thường và không xử lý mọi quy ước đuôi tệp đa nền tảng; ví dụ `SUMMARY.TXT` có thể cần chính sách chữ hoa/thường riêng theo nghiệp vụ. Java `Path` không định nghĩa một “file extension” bắt buộc cho mọi file system.

### 4.3. Hậu tố tuyệt đối: đừng giả định root không quan trọng

Khi đối số `endsWith` có **root**, việc so sánh phải xét quy tắc root và các thành phần thích hợp của provider. Không coi một `Path` tuyệt đối là hậu tố tương đương với một `Path` tương đối có cùng tên cuối.

Nếu chỉ cần hậu tố gồm một hay nhiều **tên**, hãy truyền một `Path` tương đối như `Path.of("2026", "summary.txt")`. Nếu cần so sánh **toàn bộ** đường dẫn tuyệt đối, hãy xem xét `equals` sau khi đã xác định rõ dạng/cách chuẩn hóa. Không thay `endsWith` bằng so chuỗi `toString().endsWith(...)` vì có thể trùng những đoạn ký tự không nằm trên ranh giới thành phần tên.

## 5. `startsWith` và `endsWith` không tự sửa `.`, `..`

Một điểm dễ sai là tưởng `Path.startsWith` tự động hiểu rằng `..` quay lại thư mục cha. Thực tế, các phép prefix/suffix xử lý **giá trị đường dẫn đang có**; muốn làm gọn cú pháp phải gọi `normalize()` theo chủ đích.

```java
Path raw = Path.of(
        "workspace", "reports", "old", "..", "2026", "summary.txt");
Path normalized = raw.normalize();

Path target = Path.of("workspace", "reports", "2026", "summary.txt");

System.out.println(raw.equals(target));           // false
System.out.println(normalized.equals(target));    // true
```

Minh họa phép kiểm tra tiền tố:

```java
Path desiredPrefix = Path.of("workspace", "reports", "2026");

System.out.println(raw.startsWith(desiredPrefix));        // false
System.out.println(normalized.startsWith(desiredPrefix)); // true
```

Hai câu lệnh trên khác nhau vì giá trị `raw` chứa thành phần `old` ở vị trí mà `desiredPrefix` mong đợi `2026`. Sau `normalize()`, cặp `old/..` được loại bỏ **về mặt cú pháp**.

**Giới hạn:** `normalize` không truy cập file system để biết `old` có tồn tại hoặc là symbolic link hay không. Trong một số cấu trúc symbolic link, rút gọn `link/..` theo cú pháp có thể **khác cách hệ thống tệp xử lý đối tượng thật**. Vì vậy chuẩn hóa lexical hữu ích cho việc so sánh tên, nhưng không phải bằng chứng tuyệt đối về vị trí vật lý hoặc quyền truy cập.

## 6. Root và absolute/relative quyết định quan hệ đường dẫn

### 6.1. Đừng trộn tiền tố relative với đường dẫn absolute

```java
Path relativeBase = Path.of("workspace", "reports");
Path relativeFile = relativeBase.resolve("2026").resolve("summary.txt");

Path absoluteBase = relativeBase.toAbsolutePath();
Path absoluteFile = relativeFile.toAbsolutePath();

boolean mismatched = absoluteFile.startsWith(relativeBase); // false
boolean matched = absoluteFile.startsWith(absoluteBase);    // true
```

Đây là đoạn minh họa trong chương trình có cùng môi trường làm việc và file system. Những giá trị absolute được tạo từ cùng ngữ cảnh nên chia sẻ root và các tên tương ứng.

Hãy **thống nhất dạng đường dẫn** trước khi so sánh. Nếu một bên là absolute và bên kia là relative, tiền tố không khớp theo cách bạn kỳ vọng dù khi đọc tên thấy giống nhau. `toAbsolutePath` có thể phụ thuộc **thư mục làm việc hiện tại**; không in ra một absolute path cố định rồi giả định kết quả ấy chạy giống mọi máy.

### 6.2. Absolute không có nghĩa tồn tại

```java
Path path = Path.of("not-created", "file.txt").toAbsolutePath();
```

Câu lệnh không tạo tệp hoặc kiểm tra sự tồn tại. `isAbsolute()` là thuộc tính của **giá trị đường dẫn**, không phải chỉ báo tình trạng file.

### 6.3. Các provider có thể khác nhau

Một chương trình có thể làm việc với `Path` từ file system mặc định, ZIP/JAR provider hoặc các provider được cài đặt. Không nên áp dụng quy tắc so sánh bằng cách tự ép tất cả sang `String`.

- `startsWith`/`endsWith` dùng semantics đường dẫn của provider.
- `equals`, `hashCode` và `compareTo` cũng gắn với cách biểu diễn và quy tắc của implementation.
- `relativize` cần các đường dẫn tương thích về file system/root.
- Một chuỗi hợp lệ trên Unix có thể không hợp lệ trên Windows; phân biệt hoa/thường và ký tự tên cũng có thể khác.

Ưu tiên **các giá trị `Path` sinh từ cùng file system** khi cần xét quan hệ thành phần. Nếu khác provider, hãy chuyển đổi ở **ranh giới giao thức** một cách có chủ đích, không dựa vào `toString()` như định dạng trao đổi phổ quát.

## 7. `getParent`, `resolveSibling`, `resolve` và `relativize` để diễn đạt quan hệ

Một đường dẫn có thể được liên hệ tới một đường dẫn khác bằng nhiều phép biến đổi, không phải lúc nào cũng cần bắt đầu bằng `startsWith`.

### 7.1. Đường dẫn cha: `getParent()`

```java
Path report = Path.of("workspace", "reports", "2026", "summary.txt");

Path parent = report.getParent();
// workspace/reports/2026
```

`getParent()` biểu diễn **phần cha của giá trị đường dẫn**, không kiểm tra thư mục cha có thật. Nó có thể trả `null` khi đường dẫn không có parent theo cách biểu diễn.

**Cảnh báo:** tên cuối của một `Path` có thể là thư mục, file hoặc không tồn tại. `getParent` không suy ra “loại file” của đối tượng tại đường dẫn.

### 7.2. Đường dẫn cùng cấp: `resolveSibling()`

```java
Path report = Path.of("workspace", "reports", "2026", "summary.txt");
Path sibling = report.resolveSibling("overview.md");
// workspace/reports/2026/overview.md
```

Đây là thao tác **thay thành phần tên cuối bằng tên khác ở cùng mức cha**. Nó không tạo file `overview.md` và không đổi tên tệp `summary.txt` trên đĩa. Nếu muốn đổi tên thực, cần API I/O tương ứng như `Files.move` và xử lý lỗi.

### 7.3. Ghép từ base: `resolve()`

```java
Path base = Path.of("workspace", "reports");
Path target = base.resolve(Path.of("2026", "summary.txt"));
```

Với phần ghép **relative**, kết quả là giá trị biểu diễn `workspace/reports/2026/summary.txt`. Nếu đối số là **absolute**, `resolve` có các quy tắc khác, thường giữ đường dẫn absolute của đối số; không dựa vào `resolve` làm phép bảo vệ tự động giữ mọi đầu vào dưới base.

### 7.4. Đường đi tương đối: `relativize()`

```java
Path base = Path.of("workspace", "reports");
Path target = Path.of("workspace", "reports", "2026", "summary.txt");

Path relative = base.relativize(target);
// 2026/summary.txt

Path rebuilt = base.resolve(relative);
// workspace/reports/2026/summary.txt
```

Với các giá trị tương thích trên, `rebuilt.equals(target)` là `true`. Đây là cách hữu ích khi cấu hình một thư mục làm việc cố định nhưng cần lưu **đường đi tương đối** cho từng mục.

**Lưu ý:** `relativize` không yêu cầu tệp tồn tại. Nếu so giữa absolute và relative không tương thích, có thể ném `IllegalArgumentException`. Không coi `relativize` là kiểm tra “có quyền truy cập” hoặc “đường dẫn chắc chắn nằm dưới thư mục”.

### 7.5. Có nên dùng `relativize` sau `startsWith`?

Khi đã bảo đảm hai đường dẫn có cùng cách biểu diễn và muốn lấy hậu tố tương đối, có thể làm:

```java
Path base = Path.of("workspace", "reports");
Path target = Path.of("workspace", "reports", "2026", "summary.txt");

if (target.startsWith(base)) {
    Path within = base.relativize(target);
    System.out.println(within); // 2026/summary.txt (minh họa)
}
```

Bước `startsWith` xác nhận **tiền tố tên**; `relativize` lấy các bước còn lại. Mẫu này hữu ích cho **logic xử lý đường dẫn đáng tin**, như tạo tên hiển thị tương đối trong một workspace đã kiểm soát. **Không dùng riêng mẫu này làm sandbox bảo mật cho đầu vào đối kháng**, vì các mục `..`, symbolic link và điều kiện thay đổi file system cần được xử lý ở mức phù hợp.

## 8. `equals`, `hashCode` và `Files.isSameFile`: quan hệ tên khác quan hệ file

Cần phân biệt hai câu hỏi:

1. **Hai giá trị `Path` bằng nhau không?** → `a.equals(b)`, dựa trên semantics của provider.
2. **Hai đường dẫn thực đang nói tới cùng một đối tượng tệp không?** → `Files.isSameFile(a,b)`, có thể cần truy cập file system và ném `IOException`.

```java
Path file = Path.of("workspace", "reports", "summary.txt");
Path withDot = Path.of("workspace", ".", "reports", "summary.txt");

boolean sameValue = file.equals(withDot); // Có thể khác vì chứa thành phần ".".
```

Đoạn trên **không kiểm tra** rằng tệp thực tồn tại. Những implementation file system thông thường phân biệt hai giá trị ở dạng chưa `normalize`, dù chúng có thể trỏ tới cùng tệp nếu file system giải quyết `.` theo cách kỳ vọng.

Khi **có file thật**, có thể dùng:

```java
import java.nio.file.Files;

// file và withDot là các Path hợp lệ; đoạn đặt trong phương thức
// có khai báo throws java.io.IOException.
boolean sameFile = Files.isSameFile(file, withDot);
```

`Files.isSameFile` có thể kiểm tra danh tính tệp theo file system. Nó có ích khi đường dẫn khác tên do `.`, symbolic link hoặc hard link, nhưng điều kiện hoạt động/khả năng so sánh phụ thuộc provider và trạng thái file system. Không thay thế nó bằng `equals` nếu yêu cầu nghiệp vụ thực sự là **cùng đối tượng tệp**.

### Không kiểm tra danh tính vật lý bằng `toString()`

Cách sau không đủ:

```java
file.toString().equals(withDot.toString())
```

Hai chuỗi khác nhau vẫn có thể dẫn đến một tệp, và trên một file system cụ thể các kiểu chữ hoa/thường/root có thể được diễn giải khác. Khi cần so giá trị `Path`, dùng `Path.equals`; khi cần danh tính file đang tồn tại, dùng `Files.isSameFile`.

### Lưu ý thời điểm và quyền

Ngay cả khi `Files.isSameFile` trả `true`, tệp vẫn có thể bị xóa hoặc thay thế sau đó. Đây là một quan sát trong hệ thống tệp có thể thay đổi, **không phải cam kết trạng thái tương lai**. Tương tự, `Files.exists` không phải kiểm tra quyền vĩnh viễn và cũng không thay việc xử lý ngoại lệ I/O lúc mở file.

## 9. `Path.endsWith` không phải glob, regex hoặc kiểm tra nội dung

Một số nhu cầu thường bị nhầm:

| Nhu cầu thật | Cách phù hợp | Không nên nhầm với |
| --- | --- | --- |
| Kiểm tra đường dẫn nằm sau một số thành phần nhất định | `path.endsWith(Path.of("reports", "summary.txt"))` | So ký tự cuối của một chuỗi |
| Kiểm tra tên cuối có hậu tố `.csv` | `path.getFileName().toString().endsWith(".csv")` sau khi kiểm tra `null` | `path.endsWith(".csv")` |
| Kiểm tra tên phù hợp mẫu `*.csv` | API pattern/glob phù hợp, ví dụ `PathMatcher`, hoặc xử lý tên theo yêu cầu | `path.endsWith("*.csv")` |
| Tìm file thật trong cây thư mục | `Files.walk`, `Files.find` hay API duyệt thư mục thích hợp | Chỉ gọi `startsWith`/`endsWith` |
| Kiểm tra hai tên cùng trỏ tới tệp | `Files.isSameFile` khi cần danh tính | `path.endsWith(filename)` |
| Xác thực quyền truy cập thư mục | Cơ chế kiểm soát quyền và I/O an toàn theo môi trường | Kiểm tra chuỗi bằng `startsWith` |

`startsWith` và `endsWith` không đọc file, không tìm trong thư mục và không sử dụng wildcard. Ví dụ `path.endsWith("*.txt")` không có nghĩa “mọi tệp .txt”; dấu sao là một phần tên theo cách phân tích của provider, hoặc có thể bị coi là không hợp lệ trên một số hệ thống.

Khi đọc đường dẫn không tin cậy, không nên cố diễn giải tên tệp bằng thủ thuật chuỗi đơn giản nếu cần đảm bảo an toàn. Việc phân tích tên, xác minh quyền và mở file nên được thiết kế nhất quán.

## 10. Ví dụ Java 17+ độc lập: toàn bộ phép kiểm tra tiền tố, hậu tố và quan hệ

Chương trình sau minh họa:

- So sánh **tiền tố ký tự** với **tiền tố thành phần đường dẫn**.
- `endsWith` trên tên tệp và trên hai thành phần cuối.
- Tính **đường tương đối**, **đường cùng cấp**, và chuẩn hóa `..`.
- Phân biệt đường dẫn **absolute** với **relative**.
- Tạo file tạm để chứng minh hai giá trị `Path` khác nhau có thể trỏ đến cùng một **tệp thật**.

Mã được kiểm thử bằng Java 17, không phụ thuộc thư mục làm việc cụ thể và không in tên thư mục tạm ngẫu nhiên.

Tạo tệp **`PathRelationsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PathRelationsDemo {
    private static String show(Path path) {
        return path.toString().replace('\\', '/');
    }

    private static void verify(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws IOException {
        Path base = Path.of("workspace", "reports");
        Path report = base.resolve(Path.of("2026", "summary.txt"));
        Path lookalike = Path.of("workspace", "reports-old", "draft.txt");
        Path suffix = Path.of("2026", "summary.txt");
        Path raw = Path.of("workspace", "reports", "old", "..",
                "2026", "summary.txt");
        Path normalized = raw.normalize();

        verify(report.startsWith(base), "prefix");
        verify(!lookalike.startsWith(base), "lookalike");
        verify(report.endsWith(suffix), "suffix");
        verify(report.endsWith("summary.txt"), "file name suffix");
        verify(!report.endsWith(".txt"), "not extension");
        verify(base.resolve(base.relativize(report)).equals(report),
                "round trip");
        verify(normalized.equals(report), "normalize");
        verify(!raw.equals(report), "not normalized");
        verify(!raw.startsWith(Path.of("workspace", "reports", "2026")),
                "prefix before normalize");
        verify(normalized.startsWith(
                Path.of("workspace", "reports", "2026")),
                "prefix after normalize");

        System.out.println("report = " + show(report));
        System.out.println("startsWith base = "
                + report.startsWith(base));
        System.out.println("similar text prefix = "
                + lookalike.toString().startsWith(base.toString()));
        System.out.println("similar path prefix = "
                + lookalike.startsWith(base));
        System.out.println("endsWith filename = "
                + report.endsWith("summary.txt"));
        System.out.println("endsWith two components = "
                + report.endsWith(suffix));
        System.out.println("endsWith extension = "
                + report.endsWith(".txt"));
        System.out.println("relative suffix = "
                + show(base.relativize(report)));
        System.out.println("resolved back = "
                + base.resolve(base.relativize(report)).equals(report));
        System.out.println("sibling = "
                + show(report.resolveSibling("overview.md")));
        System.out.println("raw equals normalized = "
                + raw.equals(normalized));
        System.out.println("normalize equals report = "
                + normalized.equals(report));
        System.out.println("abs startsWith relative = "
                + report.toAbsolutePath().startsWith(base));
        System.out.println("abs startsWith abs = "
                + report.toAbsolutePath().startsWith(base.toAbsolutePath()));

        Path directory = Files.createTempDirectory("path-relations-");
        Path file = directory.resolve("entry.txt");
        try {
            Files.writeString(file, "ok", StandardCharsets.UTF_8);
            Path withDot = directory.resolve(".").resolve("entry.txt");
            System.out.println("path values equal = "
                    + file.equals(withDot));
            System.out.println("same filesystem file = "
                    + Files.isSameFile(file, withDot));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
        System.out.println("checks = PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 PathRelationsDemo.java
java PathRelationsDemo
```

**Stdout chính xác trong môi trường kiểm thử với hệ thống tệp mặc định thông thường:**

```text
report = workspace/reports/2026/summary.txt
startsWith base = true
similar text prefix = true
similar path prefix = false
endsWith filename = true
endsWith two components = true
endsWith extension = false
relative suffix = 2026/summary.txt
resolved back = true
sibling = workspace/reports/2026/overview.md
raw equals normalized = false
normalize equals report = true
abs startsWith relative = false
abs startsWith abs = true
path values equal = false
same filesystem file = true
checks = PASS
```

### 10.1. Vì sao ví dụ in `show(path)` thay vì `toString()` trực tiếp?

`show` chỉ đổi dấu `\` trong **chuỗi để in kết quả** thành `/`, giúp phần hiển thị dễ đọc trên Windows và Unix. Không dùng kết quả này để xử lý file thật. Mọi phép so sánh `startsWith`/`endsWith`, `resolve`/`relativize` đều thao tác trên **đối tượng `Path`** nguyên gốc.

### 10.2. Vì sao `similar text prefix = true` nhưng `similar path prefix = false`?

`reports-old` có chung những ký tự đầu với `reports`, nhưng **không phải cùng thành phần tên**. Đây là một trong những khác biệt thiết thực nhất giữa `String.startsWith` và `Path.startsWith`.

### 10.3. Hậu tố `summary.txt` và `.txt`

`report.endsWith("summary.txt")` là `true` vì thành phần cuối trùng tên. `report.endsWith(".txt")` là `false` vì không có thành phần cuối nào tên đúng `.txt`. Nếu đang kiểm tra extension, phải lấy tên cuối rồi xét chuỗi theo hợp đồng file name của ứng dụng.

### 10.4. Vì sao file tạm có `equals == false` nhưng `isSameFile == true`?

`file` và `withDot` chứa các giá trị tên khác nhau vì `withDot` thêm thành phần `.`. Khi đã tạo file thật, provider giải quyết `.` và xác nhận hai đường dẫn truy tới **cùng đối tượng file**. Đây là ví dụ cụ thể rằng **bằng nhau theo giá trị đường dẫn** không nhất thiết tương đương **cùng một file vật lý**.

Phần file tạm yêu cầu quyền I/O; trên môi trường không cho phép tạo/ghi/xóa file tạm, lệnh có thể ném `IOException`. Phần tính toán tên đường dẫn trước đó không phụ thuộc vào việc tệp `workspace/...` có tồn tại hay không.

## 11. Bảo mật: tiền tố đúng về cú pháp chưa đảm bảo nằm trong thư mục cho phép

Đối với đường dẫn do người dùng cung cấp, lỗi thường gặp là dùng kiểm tra chuỗi đơn giản:

```java
// KHÔNG đủ để xác minh quyền truy cập.
boolean allowed = candidate.toString().startsWith(root.toString());
```

Nó có thể nhận nhầm `uploads-old` là bên trong `uploads`.

`Path.startsWith` theo thành phần **giải quyết được lỗi tiền tố ký tự**, nhưng không tự loại bỏ các đường dẫn `..` và không chống symbolic link hoặc việc đối tượng file system thay đổi giữa các thao tác.

Ví dụ một bước kiểm tra lexical:

```java
Path root = Path.of("uploads").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();

boolean lexicallyInside = candidate.startsWith(root);
```

Đây chỉ là **đoạn minh họa**, với `userSuppliedName` đến từ nguồn chưa tin cậy. Nó giúp kiểm tra rằng biểu thức tên đã normalize có tiền tố phù hợp, nhưng **không đủ để kết luận tệp thật an toàn**:

1. `userSuppliedName` có thể chứa `..`, đường dẫn tuyệt đối hoặc cú pháp đặc biệt.
2. Một symbolic link bên trong `root` có thể dẫn ra ngoài, dù biểu thức đường dẫn vẫn có tiền tố `root`.
3. Một tiến trình khác có thể đổi liên kết, thư mục hoặc tệp giữa bước kiểm tra và bước mở (**TOCTOU**, time-of-check/time-of-use).
4. Trên những provider khác nhau, quy tắc root, case sensitivity và quyền truy cập có thể khác.

Để bảo vệ tài nguyên thật, cần **mô hình sở hữu thư mục**, kiểm soát quyền, kiểm tra chính sách symbolic link và cách mở file an toàn. Trên provider hỗ trợ, các API như `SecureDirectoryStream` có thể giúp một số thao tác theo directory handle giảm rủi ro race; không được coi đó là giải pháp mặc định chạy ở mọi nơi. Cần kiểm soát cả đường dẫn lẫn quyền I/O thực tế, không dựa vào một boolean từ `startsWith`.

### `toRealPath` có giải quyết mọi việc không?

`Path.toRealPath()` có thể giải quyết symbolic link theo tùy chọn và lấy đường dẫn thực của đối tượng đang tồn tại, nhưng nó có I/O, có thể ném `IOException` và **không tự loại bỏ toàn bộ race condition sau bước kiểm tra**.

Ví dụ khi mục tiêu là phân tích một đối tượng đã tồn tại:

```java
Path realRoot = root.toRealPath();
Path realCandidate = candidate.toRealPath();

boolean realPrefix = realCandidate.startsWith(realRoot);
```

Đây là phần minh họa trong phương thức khai báo `throws IOException`. Nó kiểm tra quan hệ trên **đường dẫn thực tại thời điểm truy vấn**, nhưng các đối tượng có thể bị thay đổi sau đó. Với tệp chưa tồn tại, `toRealPath()` không phải phép thay thế trực tiếp cho bước tạo file an toàn.

## 12. Phân biệt những quan hệ đường dẫn hay bị lẫn

| Câu hỏi | API đúng trọng tâm | Có cần tệp tồn tại? |
| --- | --- | --- |
| Đường dẫn có những thành phần đầu giống một đường dẫn khác không? | `path.startsWith(prefix)` | Không |
| Đường dẫn có những thành phần cuối giống một đường dẫn khác không? | `path.endsWith(suffix)` | Không |
| Hai giá trị `Path` có bằng nhau theo provider không? | `a.equals(b)` | Không |
| Cần lấy tên thành phần cuối? | `getFileName()` | Không |
| Cần lấy phần cha của giá trị đường dẫn? | `getParent()` | Không |
| Cần tạo đường dẫn cùng cấp? | `resolveSibling(...)` | Không |
| Cần ghép đường con vào một base? | `resolve(...)` | Không |
| Cần lấy đường đi tương đối giữa hai giá trị? | `base.relativize(target)` | Không, nhưng phải tương thích |
| Cần bỏ các thành phần dư như `.`, `..` theo cú pháp? | `normalize()` | Không |
| Cần absolute path theo ngữ cảnh hiện tại? | `toAbsolutePath()` | Không nhất thiết |
| Cần đường dẫn thực, có thể giải quyết symbolic link? | `toRealPath()` | Thông thường có, có I/O |
| Cần biết hai tên đang chỉ cùng file? | `Files.isSameFile(a,b)` | Có thể I/O, có thể ném lỗi |
| Cần kiểm tra đuôi tên file `.txt`? | `getFileName().toString().endsWith(".txt")` với kiểm tra `null` | Không, chỉ là kiểm tra tên |

**Đọc bảng đúng cách:** phép so sánh tên đường dẫn và phép nhận diện đối tượng file system không thay thế cho nhau. Dùng phép phù hợp với câu hỏi nghiệp vụ và xử lý lỗi, quyền, symbolic link nếu đã vượt từ tầng tên sang tầng file thật.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Tại sao sai? | Hướng xử lý |
| --- | --- | --- |
| Dùng `String.startsWith` để kiểm tra đường dẫn nằm dưới base | Nhận nhầm `reports-old` là `reports` | Dùng `Path.startsWith` theo thành phần |
| Dùng `path.endsWith(".txt")` để kiểm tra đuôi file | `endsWith` kiểm tra thành phần tên, không kiểm tra hậu tố ký tự | Dùng `getFileName()` rồi kiểm tra chuỗi tên |
| Dùng `path.endsWith("*.txt")` như wildcard | `endsWith` không phải matcher | Dùng API matching/phân tích tên phù hợp |
| Cho rằng `startsWith`/`endsWith` tự normalize `..` | Hai phép không tự rút gọn thành phần tên | Dùng `normalize` có chủ đích khi cần lexical comparison |
| Dùng `normalize` để kết luận hai tên trỏ tới cùng file thật | Symlink và trạng thái hệ thống tệp có thể làm khác | Xem xét `toRealPath` / `Files.isSameFile` |
| Trộn absolute với relative trong `startsWith` | Root không khớp | Thống nhất dạng đường dẫn |
| Gọi `getParent().resolve(...)` khi parent là `null` | Có thể ném `NullPointerException` | Kiểm tra kết quả trước |
| Cho rằng `relativize` sẽ làm việc với mọi cặp `Path` | File system và root có thể không tương thích | Chọn các giá trị tương thích |
| Tưởng `resolveSibling` di chuyển file | Nó chỉ tạo giá trị đường dẫn | Dùng `Files.move` cho I/O thật |
| Coi `Path.equals` là cùng một tệp vật lý | Symlink/hard link cho phép nhiều tên cùng trỏ một tệp | Dùng `Files.isSameFile` khi cần |
| Coi `Files.isSameFile` bảo đảm tệp sẽ không đổi | Hệ thống tệp có thể thay đổi sau khi kiểm tra | Thiết kế thao tác I/O an toàn và xử lý lỗi |
| Thay toàn bộ `Path` bằng chuỗi để so sánh | Mất semantics root/provider, dễ sai separator/casing | Dùng các phương thức `Path` |
| Coi kiểm tra tiền tố lexical là sandbox bảo mật hoàn chỉnh | Có `..`, symlink, race và quyền truy cập | Xác định threat model, xử lý ở tầng file system |
| Mặc định file name có hậu tố là tệp thật | Tên có thể không tồn tại hoặc là thư mục | Dùng `Files` khi cần xác thực tệp |

## 14. Bài tập và đáp án

### Bài 1 — Phân biệt tiền tố ký tự với tiền tố `Path`

```java
Path root = Path.of("data", "images");
Path other = Path.of("data", "images-old", "cover.png");
```

**Câu hỏi:** `other.toString().startsWith(root.toString())` và `other.startsWith(root)` cho kết quả gì trên hệ thống tệp mặc định thông thường?

**Đáp án:** Phép chuỗi cho `true` do `images-old` bắt đầu bằng `images`; phép `Path` cho `false` vì thành phần `images-old` khác `images`.

### Bài 2 — Kiểm tra tên file hay phần mở rộng?

```java
Path p = Path.of("data", "notes.txt");
```

**Câu hỏi:** `p.endsWith("notes.txt")` và `p.endsWith(".txt")` có cùng kết quả không?

**Đáp án:** Không. Lệnh đầu là `true` vì tên cuối bằng `notes.txt`; lệnh sau là `false` vì thành phần cuối không tên `.txt`. Muốn kiểm tra đuôi ký tự, lấy `p.getFileName().toString().endsWith(".txt")` sau khi đảm bảo tên cuối tồn tại.

### Bài 3 — Hậu tố nhiều thành phần

Cho `p = Path.of("a","b","c","file.csv")`. Hai biểu thức `p.endsWith(Path.of("c","file.csv"))` và `p.endsWith(Path.of("b","file.csv"))` trả gì?

**Đáp án:** `true` và `false`. Hai thành phần cuối là `c` và `file.csv`, không phải `b` và `file.csv`.

### Bài 4 — Liên hệ `resolve` với `relativize`

```java
Path base = Path.of("a", "reports");
Path file = Path.of("a", "reports", "q1", "total.csv");
```

**Câu hỏi:** `base.relativize(file)` trả gì? `base.resolve(base.relativize(file)).equals(file)` có đúng không?

**Đáp án:** Kết quả tương ứng `q1/total.csv` và biểu thức kiểm tra bằng nhau là `true` trong trường hợp này. Đây là hai giá trị tương đối tương thích, không yêu cầu tệp thật tồn tại.

### Bài 5 — Chuẩn hóa trước hay sau?

```java
Path raw = Path.of("a", "old", "..", "reports", "item.txt");
Path prefix = Path.of("a", "reports");
```

**Câu hỏi:** Vì sao `raw.startsWith(prefix)` có thể `false` nhưng `raw.normalize().startsWith(prefix)` là `true`?

**Đáp án:** `raw` chứa thành phần `old` ở vị trí thứ hai, không khớp `reports`. `normalize` loại cặp `old/..` về mặt cú pháp, làm kết quả tương ứng `a/reports/item.txt`. Không được coi điều này là bằng chứng file thật nằm dưới root an toàn trong mọi cấu trúc symbolic link.

### Bài 6 — Absolute và relative

Một ứng dụng dùng `Path.of("data","report.txt")` và `toAbsolutePath()` của nó. Có nên kiểm tra tiền tố absolute bằng một `Path` relative không?

**Đáp án:** Không nên trộn hai dạng. Nếu cần so theo tiền tố, hãy thống nhất cùng file system, root và ngữ cảnh. Kết quả absolute phụ thuộc môi trường khởi chạy, không phải tên cố định cho mọi máy.

### Bài 7 — Hai tên nhưng cùng tệp

Hai `Path` khác nhau có thể cùng trỏ đến một tệp nhờ symbolic link. Phương thức nào thích hợp hơn để kiểm tra danh tính tệp thực: `equals` hay `Files.isSameFile`?

**Đáp án:** `Files.isSameFile(a,b)` khi cần kiểm tra **cùng đối tượng tệp đang tồn tại**. Nó có thể truy cập hệ thống tệp, ném `IOException` và kết quả là quan sát tại thời điểm gọi. `Path.equals` chỉ so sánh **giá trị đường dẫn theo provider**.

### Bài 8 — Vì sao `Path.startsWith` không đủ để kiểm soát path traversal?

**Đáp án:** Vì nó chỉ đánh giá cấu trúc **giá trị tên đường dẫn**. Nếu đầu vào có `..`, đường dẫn absolute, symbolic link hoặc hệ thống có kẻ khác thay đổi thư mục/link giữa bước kiểm tra và bước mở, phép so sánh này chưa xác minh được vị trí tệp và quyền truy cập. Cần phối hợp chuẩn hóa theo mục đích, root kiểm soát, xử lý symlink, thao tác I/O an toàn và mô hình đe dọa.

### Bài 9 — Quan hệ cùng cấp

`Path.of("a","b","old.txt").resolveSibling("new.txt")` biểu diễn gì? Có tạo file `new.txt` không?

**Đáp án:** Tạo **giá trị** `a/b/new.txt`; không tự tạo tệp trên đĩa. Muốn ghi, đổi tên hoặc tạo tệp thật cần `Files` và xử lý I/O thích hợp.

### Bài 10 — Test nhiều môi trường

Bạn viết test so sánh một đường dẫn tuyệt đối với chuỗi `"/home/user/data/file.txt"`. Có phù hợp cho CI đa hệ điều hành không?

**Đáp án:** Không. Root, separator, thư mục làm việc và provider khác nhau. Nên tạo `Path` bằng các thành phần, kiểm tra quan hệ có ý nghĩa thay vì hardcode chuỗi absolute. Nếu mục đích thật sự cần kiểm tra trên một hệ thống cụ thể, hãy tách test theo platform và ghi rõ precondition.

## 15. Checklist khi viết mã kiểm tra quan hệ đường dẫn

- [ ] Đang so sánh **thành phần đường dẫn** hay **ký tự của tên file**? Chọn `Path.startsWith/endsWith` hoặc phép chuỗi đúng mục đích.
- [ ] Hai đường dẫn có cùng `FileSystem`, root và dạng absolute/relative tương thích không?
- [ ] Đã phân biệt `getParent`, `getFileName` và `getRoot` với việc kiểm tra file thật chưa?
- [ ] Nếu có `.`/`..`, đã quyết định có cần `normalize` theo cú pháp không?
- [ ] Không nhầm `normalize` với `toRealPath` hoặc nhận dạng đối tượng file system.
- [ ] Dùng `resolve` và `relativize` theo hợp đồng của các giá trị tương thích, không ghép chuỗi thủ công.
- [ ] Có test tên tiền tố gần giống (`reports`/`reports-old`), hậu tố nhiều thành phần và phần mở rộng file.
- [ ] Có test root/absolute vs relative và những trường hợp `getParent() == null`.
- [ ] Khi cần cùng file vật lý, đã cân nhắc `Files.isSameFile` cùng xử lý `IOException`?
- [ ] Không dùng riêng một phép `startsWith` làm cơ chế bảo mật với đầu vào không tin cậy, symlink hoặc race.
- [ ] Đã ghi rõ baseline Java của dự án: `Path` từ Java 7, `Path.of` từ Java 11, `Files.writeString` từ Java 11.
- [ ] Không suy diễn từ một phép quan hệ `Path` rằng tệp tồn tại, có quyền đọc hoặc sẽ không thay đổi.

## 16. Tổng kết

Để **kiểm tra tiền tố/hậu tố**, hãy ưu tiên `Path.startsWith` và `Path.endsWith` thay vì `String.startsWith`/`endsWith` trên toàn bộ đường dẫn. Hai phương thức này làm việc theo **thành phần tên**, nhờ vậy tránh các nhầm lẫn như `reports` với `reports-old` hoặc `endsWith(".txt")` với kiểm tra phần mở rộng. Khi cần diễn đạt **quan hệ đường dẫn**, kết hợp `getParent`, `resolveSibling`, `resolve`, `relativize` và `normalize` theo đúng mục tiêu.

Phải phân biệt **đường dẫn như một giá trị** với **tệp vật lý đang tồn tại**. `Path.equals` so sánh giá trị theo provider; `Files.isSameFile` kiểm tra danh tính tệp thực khi phù hợp và có thể phát sinh I/O. Kiểm tra prefix/suffix không tự động đảm bảo an toàn thư mục, loại trừ symbolic link hoặc xử lý thay đổi trạng thái. Những nguyên tắc này vẫn là kiến thức nền tảng của Java NIO.2 từ Java 7 đến Java hiện đại.