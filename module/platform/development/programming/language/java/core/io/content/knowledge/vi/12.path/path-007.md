# Path.startsWith, endsWith, equals và so sánh theo thành phần trong Java

`java.nio.file.Path` biểu diễn một **đường dẫn** dưới dạng các thành phần tên (name elements) và, nếu có, một thành phần gốc (root). Khi kiểm tra một đường dẫn thuộc thư mục nào, có đuôi tên nào hoặc có bằng đường dẫn khác không, ba phương thức quan trọng là `startsWith(...)`, `endsWith(...)` và `equals(...)`.

Điểm cốt lõi: **đây là các phép so sánh trên cấu trúc `Path`, không phải phép kiểm tra tiền tố/hậu tố của chuỗi tùy ý**. Chẳng hạn, đường dẫn `docs/api/readme.md` bắt đầu bằng `docs/api`, nhưng không bắt đầu bằng `docs/ap`; tên `readme.md` không kết thúc bằng `me.md` theo nghĩa `Path.endsWith(...)`, dù `String.endsWith("me.md")` là `true`.

Bài học dùng Java 17+ và ưu tiên ví dụ đường dẫn tương đối, ghép bằng `Path.of("a", "b")` để tránh phụ thuộc dấu `/` hay `\` của hệ điều hành. Những khác biệt về root, phân biệt chữ hoa/chữ thường và provider sẽ được trình bày riêng.

## 1. Path là chuỗi có cấu trúc, không chỉ là String

Một đường dẫn như:

~~~text
docs / api / guide.md
  0     1      2
~~~

gồm ba thành phần tên: `docs`, `api`, `guide.md`. Với `Path path = Path.of("docs", "api", "guide.md")`:

| API | Ý nghĩa | Kết quả trong ví dụ |
|---|---|---|
| `path.getNameCount()` | Số phần tử tên | `3` |
| `path.getName(0)` | Phần tử tên đầu tiên | `docs` |
| `path.getName(1)` | Phần tử thứ hai | `api` |
| `path.getFileName()` | Phần tử tên cuối | `guide.md` |
| `path.getParent()` | Đường dẫn cha | `docs/api` trên Unix; dấu phân cách có thể khác trên Windows |
| `path.subpath(0, 2)` | Hai phần tử ở chỉ số 0 và 1 | `docs/api` theo cú pháp file system |
| `path.getRoot()` | Phần gốc nếu có | `null` đối với đường dẫn tương đối này |
| `path.isAbsolute()` | Có phải đường dẫn tuyệt đối theo file system hay không | `false` |

`Path` còn triển khai `Iterable<Path>`; vòng lặp `for (Path part : path)` duyệt **từng name element**, không bao gồm root như một phần tử tên. Chỉ số của `getName(...)` và `subpath(...)` bắt đầu từ **0**.

Cách biểu diễn chuỗi bằng `path.toString()` phụ thuộc hệ thống tệp: cùng cấu trúc có thể hiển thị `docs/api/guide.md` trên Unix và `docs\api\guide.md` trên Windows. Không nên viết kiểm thử Java portable bằng cách so sánh với một dấu phân cách cố định khi ý định thật là so sánh `Path`.

## 2. startsWith: so sánh các phần tử đầu đường dẫn

`boolean startsWith(Path other)` kiểm tra đường dẫn hiện tại có bắt đầu bằng những **phần tử tên** của `other` hay không, đồng thời áp dụng quy tắc tương thích root của hệ thống tệp.

~~~java
// Mảnh mã minh họa; cần import java.nio.file.Path.
Path path = Path.of("docs", "api", "guide.md");

boolean a = path.startsWith(Path.of("docs"));          // true
boolean b = path.startsWith(Path.of("docs", "api"));   // true
boolean c = path.startsWith(Path.of("docs", "ap"));    // false
boolean d = path.startsWith(Path.of("doc"));          // false
~~~

Mặc dù chuỗi `"docs/api/guide.md"` bắt đầu với các ký tự `"doc"` và `"docs/ap"`, `Path.startsWith` yêu cầu **mỗi name element tương ứng phải bằng nhau theo quy tắc của file system**. Nó không kiểm tra tiền tố ký tự bên trong tên thư mục.

Các điểm cần nhớ:

1. Nếu `other` có nhiều phần tử tên hơn đường dẫn hiện tại, kết quả là `false`.
2. `path.startsWith(path)` là `true`.
3. Root phải tương thích. Đường dẫn tương đối không thể bắt đầu bằng một `other` tuyệt đối có root; giữa các đường dẫn có root, quy tắc so khớp root do file system quy định.
4. Nếu hai `Path` thuộc hai `FileSystem` khác nhau, `startsWith(Path)` trả `false`.
5. `startsWith(String other)` là overload tiện lợi: chuỗi được chuyển thành `Path` **bằng file system của đường dẫn hiện tại** trước khi so sánh. Vì vậy nó vẫn là so sánh theo thành phần, không phải `toString().startsWith(...)`.

Ví dụ trên Unix, `/data/reports/a.txt` bắt đầu bằng `/data`, nhưng `/database/a.txt` không bắt đầu bằng `/data`. Để tránh phụ thuộc root Unix trong mã chạy trên Windows, hãy tạo đường dẫn bằng API `Path` rồi kiểm tra bằng cùng provider.

## 3. endsWith: so sánh các phần tử cuối đường dẫn

`boolean endsWith(Path other)` so sánh **phần đuôi theo name element**, không phải các ký tự cuối của `toString()`.

~~~java
// Mảnh mã minh họa; cần import java.nio.file.Path.
Path path = Path.of("docs", "api", "guide.md");

boolean a = path.endsWith(Path.of("guide.md"));         // true
boolean b = path.endsWith(Path.of("api", "guide.md"));  // true
boolean c = path.endsWith(Path.of("ide.md"));           // false
boolean d = path.endsWith(Path.of("docs", "api"));      // false
~~~

Điều này dẫn tới khác biệt quan trọng:

~~~java
Path path = Path.of("notes.txt");

// So sánh hậu tố thành phần đường dẫn:
boolean pathSuffix = path.endsWith(Path.of(".txt")); // false

// So sánh hậu tố ký tự trong tên file:
boolean extension = path.getFileName().toString()
        .endsWith(".txt");                           // true
~~~

Đây là **mảnh mã minh họa**. `Path.endsWith(".txt")` không phải hàm kiểm tra phần mở rộng file. Nó hỏi liệu thành phần tên cuối có đúng là `.txt` hay không. Muốn kiểm tra phần mở rộng, cần lấy tên file rồi áp dụng quy tắc chuỗi phù hợp nghiệp vụ.

Đối với `endsWith(Path other)`, nếu `other` không có root, nó có thể khớp với các phần tử tên cuối của một `Path` dài hơn. Nhưng nếu `other` **có root**, nó chỉ có thể khớp khi phần root và phần tên tương ứng phù hợp; trong trường hợp điển hình, không thể dùng một đường dẫn tuyệt đối để hỏi hậu tố một đường dẫn khác bằng cách bỏ qua root.

`endsWith(String other)` cũng chuyển chuỗi thành `Path` trong cùng `FileSystem` rồi so sánh cấu trúc. Đường dẫn ở những provider khác nhau không được coi là có hậu tố bằng nhau chỉ vì cách in chuỗi trùng nhau.

## 4. equals: bằng nhau theo Path, không phải “cùng một file”

`path.equals(other)` kiểm tra **sự bằng nhau của hai đối tượng đường dẫn theo quy tắc của file system**. Đây là so sánh từ góc nhìn `Path`, không tự tra cứu trên đĩa để hỏi hai đường dẫn có trỏ tới cùng một đối tượng file hay không.

~~~java
// Mảnh mã minh họa.
Path a = Path.of("docs", "api", "guide.md");
Path b = Path.of("docs", "api", "guide.md");
Path c = Path.of("docs", "api", ".", "guide.md");

boolean sameLexicalPath = a.equals(b); // true
boolean containsDot = a.equals(c);    // false trên default providers thông thường
~~~

`a` và `b` gồm các phần tử tương ứng; `c` có thêm phần tử `"."` trong biểu diễn lexical. `equals` không tự gọi `normalize()` để loại bỏ phần tử `"."`. Đối với các provider lạ, chi tiết so sánh có thể phụ thuộc triển khai; đừng dựa vào giả định mọi `FileSystem` xử lý dấu chấm và chữ hoa/chữ thường hệt nhau.

Một số trường hợp **không được suy ra từ `equals`**:

- `docs/../docs/a.txt` có thể trỏ cùng nơi với `docs/a.txt` trong hoàn cảnh thích hợp, nhưng không nên coi hai đối tượng `Path` bằng nhau trước khi chuẩn hóa.
- Một đường dẫn tuyệt đối và một đường dẫn tương đối có thể chỉ tới cùng tệp sau khi được diễn giải theo thư mục làm việc; `equals` không chuyển tương đối thành tuyệt đối.
- Hai symbolic link hoặc hard link khác tên có thể định vị cùng file vật lý, nhưng `equals` vẫn có thể trả `false`.
- Hai `Path` có cách hiển thị giống nhau nhưng thuộc hai provider/`FileSystem` khác nhau không mặc nhiên bằng nhau.
- Trên file system phân biệt chữ hoa/chữ thường, tên `Report.txt` và `report.txt` có thể khác nhau; trên một số file system khác chúng có thể được coi tương đương. **Không hard-code** chính sách phân biệt hoa/thường cho mọi hệ thống.

Để kiểm tra **hai đường dẫn có xác định cùng tệp thật không**, dùng `Files.isSameFile(path1, path2)` khi thích hợp; phương thức này có thể truy cập hệ thống tệp và ném `IOException`. Chi tiết được trình bày ở phần sau.

## 5. Chương trình Java 17+ kiểm tra ba phép so sánh

Tạo tệp **`PathComparisonDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathComparisonDemo {
    public static void main(String[] args) {
        Path path = Path.of("docs", "api", "guide.md");
        Path prefix = Path.of("docs", "api");
        Path lookAlike = Path.of("docs", "apix");

        System.out.println("startsWith(prefix)="
                + path.startsWith(prefix));
        System.out.println("startsWith(lookAlike)="
                + path.startsWith(lookAlike));
        System.out.println("endsWith(suffix)="
                + path.endsWith(Path.of("api", "guide.md")));
        System.out.println("endsWith(partialName)="
                + path.endsWith(Path.of("ide.md")));
        System.out.println("equals(same)="
                + path.equals(Path.of("docs", "api", "guide.md")));
        System.out.println("equals(extraDot)="
                + path.equals(Path.of("docs", "api", ".", "guide.md")));
        System.out.println("nameCount=" + path.getNameCount());
        System.out.println("subpathEqualsPrefix="
                + path.subpath(0, 2).equals(prefix));

        for (Path name : path) {
            System.out.println("part=" + name);
        }
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac -encoding UTF-8 PathComparisonDemo.java
java PathComparisonDemo
~~~

Stdout trên default file system Java thường gặp:

~~~text
startsWith(prefix)=true
startsWith(lookAlike)=false
endsWith(suffix)=true
endsWith(partialName)=false
equals(same)=true
equals(extraDot)=false
nameCount=3
subpathEqualsPrefix=true
part=docs
part=api
part=guide.md
~~~

Vì các thành phần tên trong chương trình đều đơn giản, các kết quả không cần in dấu phân cách thư mục của hệ điều hành. Đối với Unix/Windows default provider, phép so sánh giữ phần tử `"."` riêng cho đến khi gọi `normalize()`, nên `equals(extraDot)` là `false`.

Lưu ý vòng lặp duyệt từng thành phần tên đúng thứ tự. `subpath(0, 2)` lấy phần tử tên 0 và 1, không chứa phần tử tên 2; chỉ số cuối là **exclusive**.

## 6. Root, đường dẫn tuyệt đối và tương đối

Các đường dẫn không chỉ khác ở tên thư mục mà còn có thể khác **root**:

- **Tương đối:** `Path.of("work", "notes.txt")` không có root và được diễn giải dựa vào ngữ cảnh của file system.
- **Tuyệt đối:** `Path.of("work").toAbsolutePath()` gắn với đường dẫn tuyệt đối theo file system mặc định.
- **Root:** `getRoot()` trả thành phần gốc nếu có; `null` ở đường dẫn tương đối không có root.

Trên Unix, root thường là `/`. Trên Windows, root và cú pháp đường dẫn có thể liên quan ổ đĩa hoặc UNC. Vì vậy không nên dùng `Path.of("/data")` như ví dụ portable tuyệt đối trên mọi nền tảng; hãy dùng `toAbsolutePath()` hoặc nguồn đường dẫn đã được xác định đúng cho hệ thống chạy.

Những cặp sau **không được đồng nhất**:

~~~java
// Mảnh mã minh họa: không thực hiện I/O.
Path relative = Path.of("docs", "api");
Path absolute = relative.toAbsolutePath();

boolean same = relative.equals(absolute); // false trên default FS thông thường
~~~

Tại sao có thể cùng chỉ tới một thư mục nhưng `equals` khác nhau? Vì một bên có root và phần tên của đường dẫn tuyệt đối, một bên chỉ có phần tên tương đối; `equals` so sánh cách biểu diễn `Path` theo file system, không phải phép xác nhận file vật lý.

Nếu ứng dụng muốn so sánh các đường dẫn cùng ngữ cảnh, phải định nghĩa rõ chính sách quy đổi **cả hai**: chẳng hạn `toAbsolutePath().normalize()` cho so sánh lexical, hoặc `toRealPath()` khi cần xác minh đối tượng trên hệ thống tệp thực và có quyền truy cập phù hợp.

## 7. normalize(): bỏ các phần tử “.” và xử lý “..” ở mức lexical

`Path.normalize()` tạo ra một `Path` mới đã loại các phần tử dư thừa như `"."` và cặp tên thư mục/`".."` có thể khử về mặt cú pháp. Nó **không phải lệnh truy cập đĩa** và không tự xác minh tệp có tồn tại.

Ví dụ:

~~~text
docs / api / . / guide.md
             |
             +---- normalize() ----> docs / api / guide.md

docs / api / .. / notes.txt
                   |
                   +---- normalize() ----> docs / notes.txt
~~~

Điều quan trọng là `normalize()` không luôn giữ nguyên đường dẫn **vật lý** nếu đường đi chứa symbolic link. Ví dụ `link/../target` có thể không tương đương vật lý với `target` khi `link` là symbolic link trỏ tới vị trí khác; vì thế chỉ dùng normalize cho công việc lexical đã hiểu ngữ cảnh.

Để kiểm tra cấu trúc đường dẫn, kết hợp hợp lý với `resolve(...)`, `toAbsolutePath()` và `startsWith(...)` khi cả hai đối tượng đã được đưa về cùng hệ quy chiếu:

~~~java
// Mảnh mã minh họa: xác định base ở một vị trí tin cậy.
Path base = Path.of("workspace").toAbsolutePath().normalize();

Path candidate = base.resolve(Path.of("reports", "..", "notes.txt"))
        .normalize();

boolean lexicalInside = candidate.startsWith(base);
~~~

`resolve` ghép các thành phần đường dẫn; nếu đối số đã **tuyệt đối**, kết quả thường chính là đường dẫn tuyệt đối đó theo hợp đồng provider. Vì vậy phải chuẩn hóa và kiểm tra sau khi resolve, đồng thời quyết định có chấp nhận đường dẫn tuyệt đối từ nguồn không tin cậy hay không.

## 8. Ví dụ Java 17+: so sánh trước và sau normalize

Tạo tệp **`PathNormalizationDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathNormalizationDemo {
    public static void main(String[] args) {
        Path clean = Path.of("root", "docs", "note.txt");
        Path raw = Path.of("root", "docs", ".", "note.txt");

        System.out.println("rawEqualsClean=" + raw.equals(clean));
        System.out.println("normalizedEqualsClean="
                + raw.normalize().equals(clean));

        Path base = Path.of("sandbox", "home")
                .toAbsolutePath().normalize();
        Path good = base.resolve(
                Path.of("reports", "..", "summary.txt")).normalize();
        Path escape = base.resolve(
                Path.of("..", "outside.txt")).normalize();

        System.out.println("goodUnderBase=" + good.startsWith(base));
        System.out.println("escapeUnderBase=" + escape.startsWith(base));
    }
}
~~~

~~~bash
javac -encoding UTF-8 PathNormalizationDemo.java
java PathNormalizationDemo
~~~

Stdout trên default file system Unix/Windows:

~~~text
rawEqualsClean=false
normalizedEqualsClean=true
goodUnderBase=true
escapeUnderBase=false
~~~

Giải thích:

1. `raw` có phần tử `"."` nên chưa bằng `clean` theo phép so sánh lexical của default provider; `normalize()` loại phần tử đó.
2. `base` được biến thành đường dẫn tuyệt đối, chuẩn hóa, rồi các candidate đều được xử lý theo cùng cách.
3. `good` sau khi rút gọn `reports/..` trở thành `base/summary.txt`, vì vậy bắt đầu bằng `base`.
4. `escape` chứa `..` làm đường dẫn trượt lên thư mục cha của `base`; sau normalize, `startsWith(base)` là `false`.

Ví dụ kiểm tra **cấu trúc đường dẫn**. Nó **không tạo thư mục** và không đảm bảo rằng một ứng dụng đọc file qua symbolic link sẽ không thoát ra ngoài thư mục tin cậy.

## 9. equals() khác Files.isSameFile() và toRealPath()

Ba thao tác này trả lời ba câu hỏi khác nhau:

| Thao tác | Câu hỏi | Có truy cập file system không? |
|---|---|---|
| `a.equals(b)` | Hai đối tượng `Path` có được xem là bằng nhau theo provider hay không? | Thông thường không cần |
| `a.toAbsolutePath().normalize().equals(b.toAbsolutePath().normalize())` | Hai đường dẫn có cùng biểu diễn tuyệt đối đã chuẩn hóa về mặt cú pháp không? | Không xác minh đối tượng trên đĩa |
| `Files.isSameFile(a, b)` | Hai đường dẫn có định vị **cùng đối tượng tệp** hay không? | Có thể cần truy cập đĩa và có thể ném `IOException` |
| `a.toRealPath()` | Đường dẫn thực của một đối tượng có tồn tại theo quy tắc của file system là gì? | Có; mặc định giải quyết symbolic link và kiểm tra tồn tại |

`Files.isSameFile(a, b)` có một ngoại lệ hợp đồng đáng chú ý: **nếu hai đối tượng `Path` đã `equals`, phương thức có thể trả `true` ngay mà không kiểm tra file thực sự có tồn tại**. Vì vậy không dùng `Files.isSameFile(path, path)` làm phép kiểm tra tồn tại.

### Ví dụ Java 17+: hai đường dẫn lexical khác nhau nhưng cùng một file

Tạo tệp **`PathSameFileDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathSameFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("path-demo-", ".txt");

        try {
            Path alias = file.getParent()
                    .resolve(".")
                    .resolve(file.getFileName());

            System.out.println("equals=" + file.equals(alias));
            System.out.println("normalizedEquals="
                    + file.normalize().equals(alias.normalize()));
            System.out.println("isSameFile="
                    + Files.isSameFile(file, alias));
            System.out.println("realPathEquals="
                    + file.toRealPath().equals(alias.toRealPath()));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PathSameFileDemo.java
java PathSameFileDemo
~~~

Stdout trên default file system Unix/Windows:

~~~text
equals=false
normalizedEquals=true
isSameFile=true
realPathEquals=true
~~~

Chương trình tạo tệp tạm duy nhất, rồi tạo đường dẫn `alias` bằng cách chèn phần tử `"."` vào giữa thư mục cha và tên tệp. Hai biểu diễn lexical chưa bằng nhau, nhưng sau `normalize()` chúng bằng nhau; hệ thống tệp xác nhận cả hai định vị cùng tệp. Khối `finally` xóa tệp tạm, không sửa file có sẵn do người dùng cung cấp.

Trong chương trình thực tế, `toRealPath()` hoặc `isSameFile(...)` có thể thất bại khi thiếu quyền, tệp bị xóa trong lúc kiểm tra, symbolic link lỗi hoặc provider không hỗ trợ đặc điểm nhất định. Không lấy output của ví dụ trên làm cam kết cho mọi virtual file system.

## 10. startsWith/endsWith và String.startsWith/endsWith: dùng đúng cấp độ

Cùng tên phương thức nhưng hai bộ API có mục tiêu khác hẳn nhau.

| Nhu cầu | API thích hợp |
|---|---|
| Đường dẫn nằm trong cây thư mục `docs` theo phần tử tên | `path.startsWith(Path.of("docs"))` |
| Đường dẫn có hai phần tử cuối `images/icon.png` | `path.endsWith(Path.of("images", "icon.png"))` |
| Tên tệp có đuôi chuỗi `.png` | `path.getFileName().toString().endsWith(".png")` |
| Tên file bắt đầu bằng chuỗi `report-` | `path.getFileName().toString().startsWith("report-")` |
| Hai đường dẫn có cùng biểu diễn lexical không? | `path1.equals(path2)`, sau bước chuẩn hóa nếu yêu cầu |
| Hai đường dẫn có trỏ đến cùng file thật không? | `Files.isSameFile(path1, path2)` |
| Một đường dẫn có phần tên ở chỉ số cụ thể không? | `getName(i)`, `subpath(from, to)` |

**Lưu ý với tên tệp**: `getFileName()` có thể trả `null` nếu đường dẫn chỉ chứa root. Khi muốn kiểm tra extension an toàn, cần xử lý trường hợp này:

~~~java
// Mảnh mã minh họa: path là một Path bất kỳ.
Path fileName = path.getFileName();
boolean isJavaFile = fileName != null
        && fileName.toString().endsWith(".java");
~~~

Đây là kiểm tra hậu tố ký tự, không phải xác thực loại nội dung. Một tệp `malware.java` không chắc là mã nguồn Java hợp lệ chỉ vì tên có đuôi như vậy, và chính sách so sánh phân biệt hoa/thường phải do ứng dụng quyết định.

## 11. Vì sao startsWith(String) vẫn không phải kiểm tra chuỗi?

`Path.startsWith(String other)` về cơ bản chuyển `other` thành `Path` bằng `getFileSystem().getPath(other)` rồi gọi `startsWith(Path)`. Ví dụ:

~~~java
Path p = Path.of("alpha", "beta");

boolean a = p.startsWith("alpha");          // true
boolean b = p.startsWith("alp");            // false
boolean c = p.toString().startsWith("alp"); // true
~~~

Đây là **mảnh mã minh họa**. Bên trái vẫn là `Path`, nên overload `startsWith(String)` phân tích `"alpha"` thành phần tử tên. Lời gọi `toString().startsWith("alp")` thì chỉ kiểm tra ba ký tự đầu, không biết `alpha` là một tên thư mục hoàn chỉnh.

Tương tự, `Path.endsWith("txt")` chỉ kiểm tra thành phần tên cuối là `txt`, còn `path.toString().endsWith("txt")` có thể trả `true` cho `notes.txt`. Với code theo cấu trúc thư mục, dùng `Path`; với quy tắc tên file/đuôi extension, hãy **lấy file name rõ ràng** rồi dùng thao tác chuỗi.

Cũng cần lưu ý: chuỗi chuyển thành `Path` phải hợp lệ với provider đó; overload nhận `String` có thể ném `InvalidPathException` nếu chuỗi không tạo được đường dẫn hợp lệ. Không truyền chuỗi đường dẫn của một hệ thống khác rồi tự giả định rằng Java sẽ phân tích giống nhau.

## 12. So sánh phân biệt hoa/thường và provider

`Path` có thể được cung cấp bởi default file system, ZIP file system hoặc các provider khác. Hợp đồng về **cách so sánh tên**, phân biệt hoa/thường và root là đặc thù của hệ thống tệp. Ví dụ:

- Một số hệ thống phân biệt `data` và `Data`.
- Một số hệ thống dùng cách so sánh không phân biệt hoa/thường.
- Cách diễn giải root và dấu phân cách cũng khác nhau giữa Unix, Windows và các provider đặc biệt.
- `Path.equals`, `startsWith` và `endsWith` không tự tạo cơ chế so sánh Unicode/chuỗi **độc lập môi trường**.

Đừng sửa bằng cách gọi `path.toString().toLowerCase()` rồi so sánh một cách tùy tiện: thao tác hạ chữ không tái tạo quy tắc tên của file system, có thể phá ý nghĩa của các ký tự đặc biệt và dễ gây lỗi bảo mật ở biên đường dẫn.

Nếu ứng dụng đòi một quy tắc không phụ thuộc hệ thống, hãy định nghĩa cấu trúc đường dẫn logic riêng, chuẩn hóa dữ liệu đầu vào theo giao thức rồi đối chiếu với file system thật tại ranh giới truy cập. Đừng dùng so sánh tên file như phép xác minh tuyệt đối danh tính tài nguyên.

### compareTo và thứ tự sắp xếp

`Path` triển khai `Comparable<Path>`, và `compareTo(...)` phục vụ việc **sắp thứ tự đường dẫn theo provider**, không phải phép so sánh trùng file. Một kết quả âm/dương không cho biết hai file có liên quan cha–con hay không. Nếu cần kiểm tra tiền tố theo thành phần, `startsWith(...)` diễn đạt đúng ý định hơn.

Phép so sánh giữa `Path` thuộc các provider khác nhau có thể không được hỗ trợ hoặc ném ngoại lệ với `compareTo`; không sử dụng nó làm bộ so sánh universal cho mọi nguồn file system.

## 13. Kiểm tra đường dẫn con: cần hiểu giới hạn bảo mật

Một bài toán thường gặp: cho phép người dùng truy cập một file bên trong thư mục gốc `base`.

**Sai:** dùng `inputString.startsWith(baseString)`. Chuỗi `/srv/app-data-secret` cũng bắt đầu bằng ký tự `/srv/app-data` nhưng không nằm bên trong thư mục đó.

Một phép kiểm tra **lexical** tốt hơn:

~~~java
// Mảnh mã minh họa, không đủ làm biện pháp chống symlink/TOCTOU.
Path base = Path.of("safe-root").toAbsolutePath().normalize();
Path userPath = Path.of(userInput);
Path candidate = base.resolve(userPath).normalize();

if (!candidate.startsWith(base)) {
    throw new SecurityException("Path escapes allowed directory");
}
~~~

Cơ chế trên giải quyết lỗi **tiền tố chuỗi** và nhiều trường hợp `..` về mặt cú pháp. Nhưng nó **chưa đủ để bảo vệ trước symbolic link, junction, mount, thay đổi file system đồng thời hoặc thao tác follow link**. Ví dụ, nếu bên trong `safe-root` có một symbolic link dẫn ra ngoài, candidate có thể `startsWith(base)` theo cú pháp nhưng truy cập file thực lại đi ra ngoài cây mong muốn.

Với đầu vào không tin cậy, còn phải xác định rõ chính sách **đường dẫn tuyệt đối, link, sự tồn tại của path, quyền truy cập và thao tác mở**; trong những trường hợp cần chống race kiểu time-of-check/time-of-use, xem `SecureDirectoryStream` hoặc cơ chế mở tương đương của hệ thống tệp khi khả dụng. Không nên làm bảo mật filesystem chỉ bằng một lệnh `normalize().startsWith(...)` rồi kết luận an toàn hoàn toàn.

Nếu yêu cầu đơn thuần là tổ chức đường dẫn logic, `toAbsolutePath().normalize()` và `startsWith` là công cụ đúng; nếu yêu cầu là **phân quyền file thực**, cần thêm chiến lược mạnh hơn.

## 14. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| `Path.of("docs2", "a").startsWith(Path.of("docs"))` được kỳ vọng `true` | `docs2` không phải thành phần `docs` | So sánh theo name element |
| `path.endsWith(".java")` để kiểm tra extension | `endsWith` so phần tử tên, không so ký tự cuối | `getFileName().toString().endsWith(".java")` |
| `path.equals(other)` để kết luận hai file chắc chắn khác nhau | Hai alias/link có thể trỏ cùng file | Dùng `Files.isSameFile` nếu cần đối chiếu file thực |
| `path.normalize()` được kỳ vọng xác minh symlink | Normalize là lexical, không truy cập file system | Dùng cơ chế real-path/file access phù hợp |
| So `relative.equals(absolute)` rồi cho rằng hai đích vật lý khác nhau | Hai biểu diễn khác hệ quy chiếu | Đưa về một chuẩn đường dẫn phù hợp hoặc `isSameFile` |
| Dùng `toString().startsWith(...)` để chặn traversal | Tiền tố ký tự không biết ranh giới thành phần | So sánh `Path` đã xử lý phù hợp, cộng bảo vệ link/race |
| Cho rằng `equals` luôn case-sensitive | Provider quy định so sánh | Kiểm tra hành vi mục tiêu, tránh phụ thuộc platform |
| Cho rằng `startsWith` tự chuẩn hóa `.` hoặc `..` | Không có bảo đảm tự normalize | Chủ động `normalize()` theo mục đích |
| Dùng `compareTo` thay `startsWith` | So thứ tự không phải quan hệ cha–con | Dùng API thể hiện đúng điều cần hỏi |
| Tự nối đường dẫn bằng dấu `"/"` hoặc `"\\"` | Có thể không portable | Dùng `Path.of(...)`, `resolve(...)` |
| Giả định `getFileName()` không bao giờ null | Đường dẫn root có thể không có phần tử tên cuối | Kiểm tra `null` trước khi dùng |
| Coi lexical containment là bảo đảm chống link độc hại | Link có thể dẫn ra ngoài; file có thể đổi giữa check và open | Thiết kế bảo vệ ở thao tác file thực |

## 15. Checklist áp dụng nhanh

1. Xác định yêu cầu là **tiền tố/hậu tố thành phần**, **hậu tố chuỗi tên file**, **bằng nhau của Path** hay **cùng file thực**.
2. Dùng `startsWith(Path)` cho tiền tố thành phần và `endsWith(Path)` cho hậu tố thành phần.
3. Dùng `getFileName()` + thao tác `String` nếu muốn kiểm tra đuôi `.txt` hoặc tiền tố `report-` của **tên file**.
4. Dùng `equals` để so sánh lexical theo provider; không dùng nó để kết luận hai đường dẫn khác nhau không thể trỏ cùng file.
5. Cân nhắc `toAbsolutePath()`, `normalize()` và `toRealPath()` theo từng mục tiêu; mỗi API giải quyết một vấn đề khác nhau.
6. Đối với dữ liệu đầu vào không tin cậy, coi phép kiểm tra `startsWith(base)` chỉ là một lớp trong bảo vệ path traversal, không phải giải pháp chống symlink/race hoàn chỉnh.
7. Viết test có cả đường dẫn giống **tiền tố ký tự nhưng khác thành phần**, đường dẫn có `. / ..`, đường dẫn tương đối/tuyệt đối và khác biệt file system khi triển khai trên nhiều môi trường.

## 16. Tóm tắt

**`Path.startsWith` và `Path.endsWith` làm việc với các name element của đường dẫn, không cắt chuỗi ký tự tùy ý. `Path.equals` so sánh đường dẫn theo quy tắc provider, không tự xác minh đó là cùng file vật lý.** Để xử lý `. / ..`, sử dụng `normalize()` khi có ý nghĩa; để xác định cùng tài nguyên thật, xem `Files.isSameFile(...)` hoặc `toRealPath()`, đồng thời xử lý lỗi I/O. Với các bài toán kiểm soát truy cập, đừng coi so sánh lexical là kiểm tra bảo mật hoàn chỉnh.

### Tham khảo chính thức

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Java SE 17 — Files.isSameFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path))
- [Oracle Java Tutorials — Path Operations](https://docs.oracle.com/javase/tutorial/essential/io/pathOps.html)
