# Root, parent, file name và các thành phần đường dẫn trong Java Path

## 1. Path mô tả vị trí bằng các thành phần, không chỉ là một chuỗi

Trong Java NIO.2, **java.nio.file.Path** biểu diễn một đường dẫn trong một file system. Đường dẫn có thể trỏ tới file, thư mục, symbolic link, vị trí chưa tồn tại hoặc một root. Đối tượng Path gồm các **name element** (thành phần tên), có thể có **root component** và được giải thích theo quy tắc của file-system provider.

Ví dụ minh họa theo kiểu đường dẫn Unix:

~~~text
/home/learner/docs/lesson.md
|---|---------------------|
root        name elements

root       = /
name[0]    = home
name[1]    = learner
name[2]    = docs
name[3]    = lesson.md
parent     = /home/learner/docs
fileName   = lesson.md
nameCount  = 4
~~~

Ba khái niệm dễ nhầm nhất:

- **Root:** thành phần gốc của hệ thống đường dẫn, ví dụ dấu / trên Unix, ổ đĩa hoặc share root trên Windows. Lấy bằng **getRoot()**.
- **Parent:** đường dẫn cha về mặt **cú pháp**, bỏ thành phần tên cuối cùng. Lấy bằng **getParent()**.
- **File name:** thành phần tên cuối, không nhất thiết là một file thường hay đã tồn tại. Lấy bằng **getFileName()**.

Những phương thức này chủ yếu phân tích **cấu trúc đường dẫn**, không mở file, không kiểm tra quyền truy cập và không xác minh vị trí có tồn tại.

**Điểm quan trọng:** Path là đối tượng bất biến (immutable). Các phép như normalize(), resolve() hoặc subpath() trả về Path kết quả; chúng không sửa đối tượng gốc.

## 2. Các API cần nhớ

| API | Kết quả | Lưu ý |
| --- | --- | --- |
| **getRoot()** | Root dưới dạng Path; có thể null | Root không được tính là name element |
| **getParent()** | Path cha; có thể null | Chỉ tính theo cấu trúc đường dẫn; không tự loại . hoặc .. |
| **getFileName()** | Thành phần tên cuối dưới dạng Path; có thể null | Không xác minh đó là file hay thư mục |
| **getNameCount()** | Số name element | Đường dẫn chỉ gồm root có count = 0 |
| **getName(index)** | Thành phần tên tại vị trí index | Bắt đầu từ 0; root không có chỉ số |
| **subpath(begin, end)** | Dãy name element con dưới dạng Path tương đối | begin bao gồm, end không bao gồm |
| **iterator()** | Duyệt lần lượt các name element | Không trả root |
| **isAbsolute()** | Đường dẫn có phải absolute theo provider? | Không phải phép kiểm tra file có thật |
| **normalize()** | Bỏ những name element dư thừa về mặt cú pháp | Không truy vấn file system |
| **resolve(other)** | Ghép đường dẫn bên dưới path hiện tại | Nếu other là absolute thì thường trả other |
| **resolveSibling(other)** | Thay phần tử cuối bằng một path cùng cấp | Dựa trên parent của path hiện tại |
| **relativize(other)** | Đường dẫn tương đối từ path hiện tại đến other | Phải dùng các path tương thích |
| **toAbsolutePath()** | Biểu diễn absolute của đường dẫn | Không tương đương xác minh file thực |
| **toRealPath()** | Đường dẫn thực của file đã tồn tại | Truy cập file system; có thể ném IOException |

Hầu hết phép phân tách Path không cần đến Files.exists(): một Path chỉ là mô tả địa chỉ và vẫn có thể được phân tích dù đường dẫn chưa tồn tại.

## 3. Đường dẫn relative và absolute ảnh hưởng root thế nào?

**Relative path (đường dẫn tương đối)** cần ngữ cảnh thư mục làm việc hoặc base path để định vị file. Ví dụ:

~~~text
courses/io/README.md
~~~

Với default file system thông thường, đường dẫn đó có:

~~~text
root     = null
parent   = courses/io
fileName = README.md
names    = [courses, io, README.md]
~~~

**Absolute path (đường dẫn tuyệt đối)** có đủ thông tin theo quy tắc file system để xác định vị trí mà không cần ghép thêm thư mục cơ sở. Ví dụ:

~~~text
Unix:      /var/log/app.log
Windows:   C:\work\logs\app.log
Windows:   \\server\share\reports\2026.txt
~~~

Các ví dụ trên minh họa **cú pháp của từng hệ điều hành**, không có nghĩa Java trên Linux sẽ hiểu mọi đường dẫn Windows đúng như Java trên Windows. Trong một môi trường Linux, chuỗi bắt đầu bằng C: có thể chỉ là tên tương đối; trong Windows, root/drive/share có cách phân tích riêng.

Đừng tự xây đường dẫn dùng chung bằng cách nối chuỗi với / hoặc \. Ưu tiên:

~~~java
Path file = Path.of("courses", "io", "README.md");
~~~

Khi dùng default provider, Path.of(...) ghép các phần theo quy tắc platform. **toString()** có thể hiển thị dấu phân cách khác nhau giữa Windows và Unix. Khi viết ví dụ và test chạy đa hệ điều hành, nên kiểm tra từng **name element** hoặc tính chất đường dẫn, thay vì cố định toàn bộ chuỗi kết quả với một dấu phân cách duy nhất.

**Root không đồng nghĩa thư mục home hoặc thư mục làm việc**. Chẳng hạn trên Unix root có thể là /, còn thư mục làm việc là /home/learner/project. Trên Windows đường dẫn tuyệt đối có thể thuộc ổ đĩa hoặc share riêng.

## 4. Chương trình Java 17+ đọc các thành phần đường dẫn

Tạo file **PathComponentsDemo.java**, lưu mã nguồn UTF-8:

~~~java
import java.nio.file.Path;

public class PathComponentsDemo {
    public static void main(String[] args) {
        Path path = Path.of("courses", "io", "README.md");

        System.out.println("absolute=" + path.isAbsolute());
        System.out.println("root=" + path.getRoot());
        System.out.println("parentLast="
                + path.getParent().getFileName());
        System.out.println("fileName=" + path.getFileName());
        System.out.println("count=" + path.getNameCount());

        for (int i = 0; i < path.getNameCount(); i++) {
            System.out.println("name[" + i + "]=" + path.getName(i));
        }

        Path single = Path.of("README.md");
        System.out.println("singleParent=" + single.getParent());

        Path systemRoot = Path.of("").toAbsolutePath().getRoot();
        System.out.println("rootParent=" + systemRoot.getParent());
        System.out.println("rootFileName=" + systemRoot.getFileName());
        System.out.println("rootNameCount=" + systemRoot.getNameCount());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PathComponentsDemo.java
java PathComponentsDemo
~~~

Stdout trên các default file system Windows/Unix thông dụng:

~~~text
absolute=false
root=null
parentLast=io
fileName=README.md
count=3
name[0]=courses
name[1]=io
name[2]=README.md
singleParent=null
rootParent=null
rootFileName=null
rootNameCount=0
~~~

**Vì sao kết quả đúng?**

1. Path tương đối courses/io/README.md có ba thành phần tên, không có root.
2. getParent() là courses/io; lấy fileName() của parent được io.
3. getFileName() của path ban đầu là README.md; fileName là thành phần cuối, kể cả nếu đây là một **thư mục** chứ không phải file thường.
4. Một Path tương đối chỉ có một thành phần README.md **không có parent**, nên getParent() là null. Thư mục làm việc hiện tại không tự được gắn vào path.
5. Khi lấy root của một absolute path thuộc default file system, bản thân root không có parent, không có fileName và có **0 name element**.

**Không nhầm Path.of("") với đường dẫn chỉ gồm root:** Path rỗng theo hợp đồng Path có một name element rỗng, trong khi Path biểu diễn root đơn độc có nameCount() = 0. Tạo Path rỗng không phải cách trực tiếp lấy root; đoạn code lấy root từ absolute path của thư mục làm việc.

## 5. getRoot(): thành phần gốc, không phải element đầu tiên

Đối với /home/learner/docs theo cú pháp Unix:

~~~text
getRoot()     -> /
getName(0)    -> home
getName(1)    -> learner
getName(2)    -> docs
getNameCount()-> 3
~~~

Root đứng **ngoài** danh sách name element. Vì vậy gọi getName(0) trên Path chỉ chứa / không hợp lệ; path đó có getNameCount() bằng 0.

Với Path tương đối trong môi trường thông thường, getRoot() trả null. Tuy nhiên **cách định nghĩa root và absolute là phụ thuộc provider**. Ví dụ Windows có thể phân biệt ổ đĩa và đường dẫn liên quan đến ổ đĩa hoặc root tương đối; không dùng quy tắc văn bản đơn giản kiểu “có dấu / đầu chuỗi là absolute” hoặc “có dấu hai chấm là root” cho mọi hệ điều hành.

Khi cần biết tính absolute, gọi **isAbsolute()** thay vì so sánh chuỗi. Khi cần root, gọi **getRoot()** và xử lý khả năng null:

~~~java
Path root = path.getRoot();
if (root == null) {
    System.out.println("No root component");
} else {
    System.out.println("Has a root component");
}
~~~

Đây là mảnh code dùng trong phương thức đã có biến path kiểu Path.

## 6. getParent(): đường dẫn cha theo cú pháp

getParent() trả một Path mới gồm root (nếu có) và toàn bộ name element **trừ tên cuối**:

~~~text
courses/io/README.md  -> courses/io
courses/io            -> courses
courses               -> null

Trên Unix:
/home/learner/file    -> /home/learner
/home                 -> /
/                     -> null
~~~

Một path một tên **không có root** như report.txt không có parent được biểu diễn bên trong path, nên:

~~~java
Path name = Path.of("report.txt");
System.out.println(name.getParent() == null); // true
~~~

Nếu cần xác định thư mục chứa file tương đối dựa trên thư mục làm việc, có thể chuyển sang absolute trước:

~~~java
Path absolute = name.toAbsolutePath();
Path parent = absolute.getParent();
~~~

Nhưng không được coi parent đã tồn tại hay file đã được tạo. **getParent() không gọi hệ thống file**, không xử lý symbolic link và không kiểm tra quyền truy cập.

### Dấu . và .. không tự được getParent loại bỏ

~~~text
Đường dẫn tương đối:  a/../b
getParent():          a/..
normalize():          b
normalize().getParent(): null
~~~

Vì vậy, nếu muốn parent của **đường dẫn đã giản lược về mặt cú pháp**, hãy chủ động normalize trước:

~~~java
Path parent = path.normalize().getParent();
~~~

Ngay cả vậy, normalize cũng **không chứng minh nơi lưu trữ thực sự**: một đoạn đường dẫn có symbolic link có thể thay đổi ý nghĩa khi xử lý .. ở tầng file system. Nếu cần vị trí thực của một đường dẫn đã tồn tại, xem toRealPath() và các quy tắc về symlink.

**Tránh NullPointerException:** getParent() có thể null khi path không có parent; không gọi getParent().getFileName() khi chưa chắc parent tồn tại.

## 7. getFileName(): tên cuối có thể là file hoặc thư mục

getFileName() chỉ phân tích thành phần tên cuối:

~~~text
courses/io/README.md -> README.md
courses/io           -> io
README.md            -> README.md

Trên Unix:
/home/learner         -> learner
/                     -> null
~~~

Tên phương thức **không đảm bảo** phần tử cuối là regular file. Một đường dẫn tên photos có thể trỏ tới thư mục, symlink hoặc chưa tồn tại. Nếu cần loại thực tế, dùng API Files như **Files.isRegularFile**, **Files.isDirectory**, **Files.isSymbolicLink**, tùy ngữ nghĩa và chính sách theo symbolic link.

Ví dụ:

~~~java
Path filename = Path.of("data", "reports");
System.out.println(filename.getFileName()); // reports
~~~

Đây vẫn là kết quả hợp lệ nếu data/reports là thư mục hoặc chưa có trên đĩa.

**Extension không phải thành phần riêng của Path.** getFileName() cho README.md, không tự trả md. Nếu ứng dụng cần phân tích extension, phải quy định rõ cách xử lý tên bắt đầu bằng dấu chấm, nhiều dấu chấm, tên không có extension và quy ước hệ điều hành. Path không có getExtension() chuẩn.

## 8. getNameCount(), getName(index), subpath() và Iterator

Các phần tử tên được đánh chỉ số từ **0**, không gồm root:

~~~text
Path:  courses/java/io/lesson.md

index     0        1    2       3
name      courses  java io      lesson.md
count     4
~~~

- **getName(0)** trả courses.
- **getName(3)** trả lesson.md.
- **subpath(1, 3)** trả phần gồm name[1] và name[2], tức java/io.
- **subpath(0, getNameCount())** chứa tất cả name element nhưng là **relative Path**, không mang root gốc.
- **iterator()** duyệt lần lượt các phần tử tên; không bao gồm root.

Khi lấy chỉ số ngoài phạm vi 0 đến nameCount-1, getName(index) ném **IllegalArgumentException** theo đặc tả Path Java SE 17. Với subpath(begin,end), begin phải hợp lệ, end lớn hơn begin và không vượt nameCount. Không được gọi subpath(0,0) để kỳ vọng một dãy tên rỗng bình thường.

Ví dụ duyệt không quan tâm dấu phân cách:

~~~java
Path path = Path.of("courses", "java", "io", "lesson.md");
for (Path element : path) {
    System.out.println(element);
}
~~~

Kết quả:

~~~text
courses
java
io
lesson.md
~~~

Điều này phù hợp khi viết chương trình đa nền tảng, vì việc iterate từng name element không phụ thuộc toàn bộ path in ra dùng / hay dấu gạch chéo ngược.

### Trường hợp đặc biệt: path chỉ gồm root và path rỗng

- Path chỉ gồm root, ví dụ / trên Unix, có **0 name element**, getFileName() trả null.
- Path rỗng tạo từ Path.of("") là một **empty Path** có một name element rỗng theo đặc tả Java Path.
- Không đồng nhất **empty Path**, **root Path** và **relative Path một tên**; chúng có cấu trúc và ngữ nghĩa khác nhau.

## 9. Ghép đường dẫn: resolve và resolveSibling

Khi đã có base directory, dùng **resolve()** thay vì nối chuỗi:

~~~java
Path base = Path.of("courses", "java");
Path file = base.resolve("io").resolve("lesson.md");
~~~

Ở đây file tương ứng các name element [courses, java, io, lesson.md]. **resolve(relative)** thường ghép các tên bên phải vào base; nếu đối số **absolute**, kết quả là chính absolute path đó theo hợp đồng thông thường.

Nếu muốn đổi tên cùng cấp, dùng **resolveSibling()**:

~~~java
Path oldFile = Path.of("courses", "io", "lesson.md");
Path renamed = oldFile.resolveSibling("summary.md");
~~~

renamed có parent courses/io và fileName summary.md. Khi path gốc không có parent, resolveSibling() có quy tắc riêng: thường trả other; không tự lấy thư mục làm việc làm parent.

**relativize()** tìm đường dẫn tương đối từ một Path tới Path khác:

~~~text
base:   courses/java
target: courses/java/io/lesson.md
relative = base.relativize(target)
         = io/lesson.md
~~~

Không tự áp dụng relativize giữa một absolute và một relative path. Các path cần cùng ngữ cảnh/provider và root phù hợp, nếu không có thể ném IllegalArgumentException. Nếu hai path bằng nhau, kết quả là empty Path.

## 10. Chương trình Java 17+: normalize, resolve, relativize

Tạo file **PathCompositionDemo.java**:

~~~java
import java.nio.file.Path;

public class PathCompositionDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "guides");
        Path target = Path.of(
                "workspace", "guides", "io", "lesson.md");

        Path relative = base.relativize(target);
        Path rebuilt = base.resolve(relative);

        System.out.println("relativeCount=" + relative.getNameCount());
        System.out.println("relativeFirst=" + relative.getName(0));
        System.out.println("relativeFileName="
                + relative.getFileName());
        System.out.println("roundTrip=" + rebuilt.equals(target));

        Path raw = Path.of(
                "workspace", "guides", "..", "assets", "icon.png");
        Path normalized = raw.normalize();

        System.out.println("beforeCount=" + raw.getNameCount());
        System.out.println("afterCount=" + normalized.getNameCount());
        System.out.println("afterParentLast="
                + normalized.getParent().getFileName());

        Path odd = Path.of("a", "..", "b");
        System.out.println("parentBefore="
                + odd.getParent().getFileName());
        System.out.println("parentAfter=" + odd.normalize().getParent());

        System.out.println("siblingName="
                + target.resolveSibling("index.md").getFileName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PathCompositionDemo.java
java PathCompositionDemo
~~~

Stdout mong đợi:

~~~text
relativeCount=2
relativeFirst=io
relativeFileName=lesson.md
roundTrip=true
beforeCount=5
afterCount=3
afterParentLast=assets
parentBefore=..
parentAfter=null
siblingName=index.md
~~~

Lý do:

1. base và target đều relative, có cùng prefix, nên relativize trả hai thành phần io và lesson.md.
2. resolve các thành phần tương đối trở lại base tái tạo đúng target.
3. raw gồm năm thành phần workspace, guides, .., assets, icon.png; normalize loại cặp guides/.. để còn workspace, assets, icon.png.
4. getParent() của a/../b trả a/.., tên cuối của parent là ..; còn normalize(a/../b) tạo path b chỉ một thành phần nên không có parent.
5. resolveSibling("index.md") thay tên cuối lesson.md bằng index.md.

Các thao tác trong chương trình đều **có thể thực hiện dù không có file hoặc thư mục tương ứng**; đây là phân tích/ghép đường dẫn thuần túy.

## 11. Cú pháp đường dẫn so với trạng thái thật trên đĩa

Dễ nhầm ba phép sau:

| Phép | Mục đích | Có kiểm tra file thực tế? |
| --- | --- | --- |
| **getParent/getFileName/getRoot** | Tách các thành phần của đường dẫn | Không |
| **normalize()** | Rút gọn dấu . và cặp tên/.. theo cú pháp | Không |
| **toAbsolutePath()** | Tạo biểu diễn absolute, thường dựa vào thư mục làm việc | Không bảo đảm đối tượng tồn tại |
| **toRealPath()** | Phân giải đường dẫn thực tới đối tượng đã tồn tại | Có; có thể ném IOException |

**toAbsolutePath() không tương đương toRealPath().** Ví dụ một path tương đối không tồn tại vẫn có thể được chuyển thành absolute path. Muốn tìm path thực sự của một file đã có, toRealPath() có thể cần truy cập filesystem, kiểm tra quyền và xử lý symbolic link theo tùy chọn.

Ngay cả khi dùng Files.exists(path) hay Files.isDirectory(path), trạng thái file có thể thay đổi giữa thời điểm kiểm tra và thời điểm mở file. Với I/O thực tế, cần xử lý IOException ở thao tác đọc/ghi thay vì xem kiểm tra trước đó là bảo đảm tuyệt đối.

### Symbolic link và ..

Giả sử thư mục link là symbolic link trỏ đến vị trí ở nơi khác. Biến đổi lexical như:

~~~text
link/../file.txt
        |
   normalize()
        v
file.txt
~~~

có thể **khác đường đi thực** nếu hệ thống giải quyết link trước thành phần .., tùy provider và cách truy cập. Vì vậy normalize() chỉ đơn giản hóa cú pháp, không thay thế toRealPath() hay kiểm tra ranh giới an toàn với symbolic link.

## 12. Không so sánh bằng phép nối chuỗi

Ví dụ có hai đường dẫn:

~~~text
data
database
~~~

Dùng **String.startsWith("data")** sẽ cho true ở cả hai chuỗi, dù database **không nằm trong** thư mục data. Dùng **Path.startsWith(Path)** kiểm tra theo thành phần đường dẫn theo ngữ nghĩa của provider:

~~~java
Path a = Path.of("data", "file.txt");
Path b = Path.of("database", "file.txt");

System.out.println(a.startsWith(Path.of("data"))); // true
System.out.println(b.startsWith(Path.of("data"))); // false
~~~

Path.equals và Path.startsWith đều xét các đường dẫn theo quy tắc file-system provider; không tự khẳng định hai tên khác nhau trỏ đến cùng một inode/file thật. Nếu cần kiểm tra hai đường dẫn hiện có trỏ đến cùng một file, có thể dùng **Files.isSameFile(...)**, vốn có thể cần I/O và ném IOException.

Một điểm an toàn: khi ghép tên file từ input người dùng, kiểm tra một đường dẫn sau resolve().normalize().startsWith(base) chỉ phát hiện một số trường hợp **thoát khỏi base theo cú pháp**. Nó **không đủ làm hàng rào bảo mật** khi có symbolic link, race condition hoặc file system không tin cậy. Với yêu cầu bảo mật thực sự, cần kiểm tra/kiểm soát việc mở file và xử lý link ở tầng filesystem thích hợp.

## 13. Tình huống sử dụng thực tế

### 13.1. Hiển thị tên file cho người dùng

~~~java
Path selected = Path.of("reports", "summary.csv");
Path fileName = selected.getFileName();
System.out.println(fileName); // summary.csv
~~~

Nên kiểm tra fileName != null nếu path có thể là root. Cũng đừng dùng tên này làm định danh duy nhất: hai file ở thư mục khác nhau có thể cùng tên summary.csv.

### 13.2. Tạo đường dẫn đến một file cùng thư mục

~~~java
Path source = Path.of("reports", "summary.csv");
Path backup = source.resolveSibling("summary.bak");
~~~

backup sẽ có parent giống source. Nếu thực sự muốn sao chép file, cần gọi Files.copy(...) hoặc API khác; resolveSibling() tự nó **không tạo file**.

### 13.3. Duyệt từng thư mục để hiển thị breadcrumb

~~~java
Path path = Path.of("school", "courses", "java", "notes.txt");
for (Path element : path) {
    System.out.println(element);
}
~~~

Iterator chỉ trả các name element. Nếu cần hiển thị root trong breadcrumb absolute, phải lấy riêng getRoot() và xử lý null.

### 13.4. Kiểm tra phần cuối đường dẫn

~~~java
Path path = Path.of("backup", "archive.zip");
System.out.println(path.endsWith(Path.of("archive.zip"))); // true
~~~

endsWith là so sánh theo thành phần; **không phải phép khẳng định file có tồn tại**. Nếu cần mở ZIP, dùng thư viện thích hợp sau khi xác minh đường dẫn.

## 14. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Coi getFileName() luôn là file vật lý | Nó chỉ trả tên cuối của Path | Dùng Files API để kiểm tra thực tế khi cần |
| Coi getParent() luôn có giá trị | Path relative một tên hoặc root có thể không có parent | Kiểm tra null |
| Coi getRoot() là getName(0) | Root không tính trong name element | Gọi getRoot() riêng |
| Gọi getName(getNameCount()) | Index cuối hợp lệ là count-1 | Kiểm tra index 0..count-1 |
| Gọi subpath(0,0) | Khoảng tên phải không rỗng | end > begin |
| In Path thành chuỗi rồi tự cắt tại / | Separator phụ thuộc OS/provider | Dùng Path.getName/getParent/getFileName |
| Coi relative path có parent là current directory | Path relative một tên có parent null | Dùng toAbsolutePath() nếu thật sự cần ngữ cảnh cwd |
| Coi normalize() là xác thực đường dẫn vật lý | Chỉ xử lý . và .. về mặt cú pháp | Dùng Files/toRealPath khi cần quan sát thực |
| Dùng String.startsWith để kiểm tra thư mục cha | Dễ nhầm data và database | Dùng Path.startsWith, kèm kiểm soát symbolic link khi cần bảo mật |
| Gọi relativize với hai path không tương thích | Có thể ném IllegalArgumentException | Đưa về cùng provider và kiểu root phù hợp |
| Nghĩ resolveSibling tạo file | Nó chỉ tạo Path mới | Gọi Files API mới tạo file |
| Dựa vào đuôi .txt để xác nhận regular file | Đuôi tên không phải loại file thực tế | Files.isRegularFile và xử lý lỗi mở file |

## 15. Tự kiểm tra kiến thức

**Câu 1.** Với Path.of("a","b","c.txt"), getRoot(), getParent(), getFileName() trả gì?  
**Đáp án:** getRoot() = null; getParent() là a/b (dấu phân cách theo hệ điều hành); getFileName() = c.txt.

**Câu 2.** Với Path biểu diễn / trên Unix, getFileName() và getNameCount() bằng bao nhiêu?  
**Đáp án:** getFileName() = null; getNameCount() = 0. Root không phải một name element.

**Câu 3.** Vì sao Path.of("report.txt").getParent() là null dù chương trình đang chạy trong một thư mục?  
**Đáp án:** Vì bản thân Path tương đối chỉ chứa một tên; nó chưa được chuyển sang ngữ cảnh absolute của thư mục làm việc.

**Câu 4.** Với path a/../b, getParent() và normalize().getParent() có giống nhau không?  
**Đáp án:** Không. getParent() của path gốc là a/..; normalize() thành b, một Path tương đối một tên nên parent null.

**Câu 5.** Trên Unix, /a/b/c.txt có getNameCount() bằng 3 hay 4?  
**Đáp án:** 3: a, b, c.txt. Dấu / là root và không được tính là một name element.

**Câu 6.** Vì sao không dùng split("/") để lấy fileName?  
**Đáp án:** Cú pháp dấu phân cách phụ thuộc file-system provider, và Path API đã có getFileName() xử lý đúng cấu trúc.

**Câu 7.** Tạo Path bằng resolve() có tự tạo file không?  
**Đáp án:** Không. resolve chỉ ghép các thành phần; muốn tạo file phải gọi Files API.

**Câu 8.** Nếu muốn duyệt mọi name element của một Path absolute, iterator có trả root không?  
**Đáp án:** Không. Lấy root riêng qua getRoot() nếu cần hiển thị nó.

**Câu 9.** normalize() đã bảo đảm đường dẫn cuối không đi ra ngoài thư mục cho phép khi có symbolic link chưa?  
**Đáp án:** Chưa. Normalize là lexical; phải có cơ chế kiểm soát file system và symbolic link phù hợp nếu đây là ranh giới bảo mật.

**Câu 10.** getFileName() trả về Path hay String?  
**Đáp án:** Path. Có thể gọi toString() nếu muốn hiển thị tên như văn bản, nhưng không được thay thế mọi thao tác đường dẫn bằng xử lý String.

## 16. Tài liệu Java SE 17

- [Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): getRoot, getParent, getFileName, getNameCount, getName, subpath, iterator, resolve, relativize, normalize.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): thao tác thật với file và thư mục, kiểm tra loại và quyền truy cập.
- [FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): provider, root directories và dấu phân cách tên.

**Ghi nhớ:** **Root** xác định gốc của cấu trúc đường dẫn, **parent** là path cha về mặt cú pháp, **file name** là thành phần cuối, còn **name element** là những tên có thể truy cập bằng getName(index) hoặc iterator. Java Path giúp phân tích và ghép đường dẫn mà không phụ thuộc cách viết dấu phân cách, nhưng **không tự xác nhận file tồn tại hay đường dẫn an toàn với symbolic link**.
