# Thứ tự duyệt cây thư mục không mặc nhiên là thứ tự mong muốn

## 1. Vấn đề: “duyệt được” không có nghĩa “duyệt đúng thứ tự”

Trong Java I/O, ứng dụng có thể liệt kê file bằng **File.list()/listFiles()**, **Files.list(Path)**, **DirectoryStream**, hoặc duyệt toàn bộ cây thư mục bằng **Files.walk(Path)** và **Files.walkFileTree(...)**. Những API này giúp **tìm và duyệt các mục**, nhưng **không mặc định bảo đảm thứ tự theo tên, ngày sửa, dung lượng, loại file hay bất kỳ thứ tự nghiệp vụ nào**.

Ví dụ có cây:

~~~text
project/
├── zeta.txt
├── docs/
│   ├── chapter2.md
│   └── chapter1.md
└── alpha.txt
~~~

Một ứng dụng muốn hiện menu cho người dùng theo tên có thể mong đợi:

~~~text
alpha.txt
docs/
zeta.txt
~~~

Nhưng lệnh **Files.list(project)** chỉ lấy các mục trực tiếp dưới **project**, **không cam kết thứ tự alphabet**. Trên một máy, đầu ra có thể tình cờ trùng thứ tự mong muốn; trên máy khác, sau khi tạo/xóa file hoặc đổi filesystem, thứ tự có thể khác.

Một ứng dụng khác muốn **duyệt cây đầy đủ** theo từng nhánh, hoặc **xóa file trước khi xóa thư mục cha**. Đó lại là **bài toán thứ tự khác** so với alphabet toàn cục. Cần phân biệt **phạm vi liệt kê**, **chiến lược duyệt cây** và **thứ tự xử lý**.

> Nguyên tắc: **khi thứ tự là yêu cầu đúng-sai của chương trình, phải xác định quy tắc và áp đặt nó trong code**. Đừng phụ thuộc vào thứ tự mà filesystem trả về tình cờ.

## 2. Ba khái niệm rất dễ nhầm

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Phạm vi** | Chỉ con trực tiếp hay cả cây? | **Files.list(dir)** lấy con trực tiếp; **Files.walk(root)** đi vào các cấp con |
| **Chiến lược duyệt** | Vào nhánh nào trước, cha hay con trước? | **Files.walk** duyệt **depth-first**, mỗi thư mục trước các mục dưới nó |
| **Sắp xếp** | Giữa những mục cùng cấp, mục nào đứng trước? | Tên A–Z, thư mục trước file, thời gian tăng dần |

Dù một API có xác định **depth-first** (chiều sâu), điều đó **không đồng nghĩa** mỗi thư mục con được duyệt theo alphabet. “Depth-first” trả lời **cách đi qua cấu trúc cây**; “alphabet” trả lời **so sánh giữa các mục**.

Cũng không được suy luận theo tên file có số: **"file10.txt"** đứng **trước "file2.txt"** theo so sánh từ điển ký tự thông thường vì ký tự **'1'** đứng trước **'2'**. Nếu cần thứ tự số tự nhiên, phải có bộ so sánh chuyên biệt.

## 3. Thứ tự trả về của File.list() và File.listFiles()

API truyền thống **java.io.File**:

~~~java
File dir = new File("project");
String[] names = dir.list();
File[] entries = dir.listFiles();
~~~

Đây là **mảnh code minh họa**, cần import **java.io.File**. Các API trên chỉ liệt kê **các mục con trực tiếp**; chúng **không tự đi vào mọi cấp con**.

Hai phương thức **không bảo đảm thứ tự** của các tên hoặc đối tượng trả về. Vì vậy, không nên viết:

~~~java
File[] entries = dir.listFiles();
File first = entries[0]; // Sai nếu hiểu đây là file đầu tiên theo tên.
~~~

Ngoài chuyện chưa sắp xếp, **listFiles() có thể trả null** nếu đường dẫn không phải thư mục hoặc có lỗi I/O; đoạn code trên còn có thể lỗi null hay mảng rỗng. Cần kiểm tra:

~~~java
File[] entries = dir.listFiles();
if (entries == null) {
    throw new IOException("Không thể liệt kê thư mục: " + dir);
}
Arrays.sort(entries,
        Comparator.comparing(File::getName));
for (File entry : entries) {
    System.out.println(entry.getName());
}
~~~

Đây là **mảnh code minh họa**, cần import **java.io.File**, **java.io.IOException**, **java.util.Arrays**, **java.util.Comparator**. **Arrays.sort** áp đặt thứ tự theo **getName()** trên **mảng hiện có**, không làm thay đổi thứ tự lưu trên filesystem.

**Lưu ý:** hàm so sánh trong ví dụ phân biệt hoa/thường và theo thứ tự ký tự của Java. Nó không phải tự động là thứ tự phù hợp với ngôn ngữ tự nhiên hoặc quy tắc “folder first” của file manager.

## 4. Files.list(Path): một cấp, thứ tự không được bảo đảm

API NIO:

~~~java
try (Stream<Path> stream = Files.list(directory)) {
    stream.forEach(System.out::println);
}
~~~

Đây là **mảnh code minh họa**, giả định **directory** là Path và đã import **java.nio.file.Files**, **java.nio.file.Path**, **java.util.stream.Stream**, đồng thời xử lý IOException.

**Files.list(directory)** tạo stream lấy **các mục trực tiếp** trong directory. Javadoc nói **thứ tự phần tử không được bảo đảm**. Stream có thể được cấp dữ liệu lười (*lazy*); việc mở stream có tài nguyên gắn với thư mục, nên cần **try-with-resources**.

### 4.1. Muốn xếp tên A–Z: sorted() tường minh

~~~java
try (Stream<Path> stream = Files.list(directory)) {
    stream.sorted(
            Comparator.comparing(p -> p.getFileName().toString()))
          .forEach(System.out::println);
}
~~~

Đoạn trên cần thêm import **java.util.Comparator** và giả định thư mục hiện hữu. Kết quả sắp xếp theo **tên mục con**, không theo toàn bộ đường dẫn. Do các mục là con trực tiếp của cùng một directory, đây thường là quy tắc cần dùng cho danh sách tên đơn cấp.

Nếu chỉ cần tên:

~~~java
try (Stream<Path> stream = Files.list(directory)) {
    List<String> names = stream
            .map(p -> p.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
~~~

Đây là **mảnh code**, cần import **java.util.List**. Java 16+ có **Stream.toList()**, vì vậy Java 17 sử dụng được. Lấy danh sách rồi sort giúp kết quả không phụ thuộc vào thứ tự bất kỳ của filesystem, **với điều kiện tập mục không bị thay đổi trong lúc thu thập**.

**sorted() là thao tác có trạng thái**: để sắp xếp toàn bộ danh sách, nó phải lưu các phần tử cần so sánh. Với thư mục chứa hàng triệu file, bộ nhớ và chi phí sort có thể đáng kể.

## 5. Files.walk(Path): duyệt chiều sâu, không mặc định duyệt con theo tên

**Files.walk(root)** trả stream duyệt cây file từ root. Hợp đồng quan trọng:

- Bắt đầu ở **root**.
- Duyệt **depth-first** (theo chiều sâu) và **thư mục được phát trước các mục con** của nó (*pre-order*).
- **Không bảo đảm thứ tự các mục con/sibling** trong cùng thư mục.
- Theo mặc định **không theo symbolic link** trỏ đến thư mục khi duyệt sâu; có tùy chọn **FileVisitOption.FOLLOW_LINKS** nếu chủ động cần, kèm rủi ro vòng lặp và phạm vi truy cập.
- Stream giữ tài nguyên của các thư mục đang mở; cần **đóng stream**. Trong quá trình duyệt, lỗi I/O có thể xuất hiện dưới dạng **UncheckedIOException**.

Ví dụ:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.forEach(System.out::println);
}
~~~

Đây là mảnh code minh họa, giả định **root** đã khai báo là Path, có import cần thiết và xử lý IOException. Không được suy ra rằng thư mục con tên “a” sẽ luôn được thăm trước thư mục “z”.

### 5.1. Pre-order không đồng nghĩa alphabet toàn cục

Giả sử:

~~~text
root/
├── b.txt
└── docs/
    └── a.txt
~~~

Trong **pre-order depth-first**, khi chọn đi vào **docs**, luồng sẽ phát **docs** trước **docs/a.txt**; nhưng **b.txt** có thể xuất hiện trước hay sau nhánh **docs** do thứ tự sibling không được bảo đảm.

Nếu áp dụng:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.sorted().forEach(System.out::println);
}
~~~

thì đây là **sắp xếp toàn cục các Path sau khi duyệt**, không phải yêu cầu filesystem “đi qua các nhánh theo alphabet”. Hai cách có thể cho **thứ tự đầu ra cuối giống nhau** theo một comparator, nhưng khác **thời điểm khám phá** và không biến traversal gốc thành một hành trình DFS với lựa chọn sibling tường minh.

**Duyệt và xử lý ngay** (ví dụ in, copy hoặc xóa trong hành trình) khác với **thu thập tất cả rồi sắp xếp mới xử lý**. Khi hành động phụ thuộc thứ tự cha/con, không thể dùng một sort tùy ý thay cho thuật toán traversal phù hợp.

## 6. Files.walkFileTree và thứ tự trước/sau khi thăm thư mục

**Files.walkFileTree** gọi các callback của **FileVisitor**. Các callback có ý nghĩa cấu trúc:

- **preVisitDirectory(dir, attrs)**: xử lý thư mục **trước** khi duyệt các mục bên trong nó.
- **visitFile(file, attrs)**: xử lý file (và các mục không phải thư mục được duyệt sâu).
- **visitFileFailed(file, exc)**: xử lý trường hợp không truy cập được mục.
- **postVisitDirectory(dir, exc)**: xử lý thư mục **sau khi** đã duyệt xong các mục bên trong (hoặc sau khi duyệt bị gián đoạn theo hợp đồng).

Mặc dù callback xác định ý nghĩa **trước/sau đối với từng thư mục**, **thứ tự giữa các mục con cùng cấp vẫn không được bảo đảm theo alphabet**.

Một số bài toán yêu cầu thứ tự phụ thuộc cấu trúc:

| Tác vụ | Thứ tự cần thiết |
| --- | --- |
| Tạo cây thư mục ở nơi khác | Thường **tạo thư mục cha trước con**, tức là pre-order khi xử lý thư mục |
| Dọn một cây thư mục | **Xóa file/con trước khi xóa thư mục cha**, dùng visitFile + postVisitDirectory |
| Xuất danh sách theo tên | Có thể cần **sort sibling** hoặc sort toàn bộ tên đầu ra |
| Xuất cây đẹp, thụt lề theo cấp | **Cấu trúc DFS + thứ tự sibling tường minh**, không phải chỉ global sort |
| Chọn file “mới nhất” | Sort theo **thời gian thực** đã đọc từ attribute, không dựa vào vị trí trả về |

Nếu chỉ cần thứ tự **phục vụ xóa con trước cha**, **walkFileTree** với **postVisitDirectory** phù hợp hơn việc mong Files.walk trả danh sách mà đảo lại tùy tiện.

## 7. Ví dụ Java 17+ hoàn chỉnh: cùng cây, nhưng tự sắp xếp để ổn định

Chương trình sau tự tạo thư mục tạm để mọi lần chạy có cấu trúc dữ liệu thống nhất. Nó:

1. Tạo **a.txt**, **b.txt**, thư mục **docs** và **docs/intro.txt**, theo thứ tự tạo có chủ đích nhưng **không dựa vào thứ tự tạo khi liệt kê**.
2. Liệt kê **một cấp** bằng Files.list và sort theo tên.
3. Duyệt **cả cây** bằng Files.walk, biến các đường dẫn thành đường dẫn tương đối để output không chứa tên thư mục tạm ngẫu nhiên, rồi sort để đầu ra ổn định.
4. Dọn cây **con trước cha** bằng FileVisitor.

Lưu thành **TraversalOrderDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.List;
import java.util.stream.Stream;

public class TraversalOrderDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("traversal-order-");

        try {
            Files.writeString(root.resolve("b.txt"), "B");
            Path docs = Files.createDirectory(root.resolve("docs"));
            Files.writeString(docs.resolve("intro.txt"), "Intro");
            Files.writeString(root.resolve("a.txt"), "A");

            try (Stream<Path> stream = Files.list(root)) {
                List<String> children = stream
                        .map(path -> path.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("children=" + children);
            }

            try (Stream<Path> stream = Files.walk(root)) {
                List<String> tree = stream
                        .map(path -> {
                            String relative = root.relativize(path)
                                    .toString().replace('\\', '/');
                            return relative.isEmpty() ? "." : relative;
                        })
                        .sorted()
                        .toList();
                System.out.println("tree=" + tree);
            }
        } finally {
            // Chỉ xóa cây tạm do chương trình tạo; không follow links.
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.delete(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    Files.delete(dir); // Con đã được duyệt/xóa trước.
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }
}
~~~

Chạy với Java 17 trở lên:

~~~bash
javac TraversalOrderDemo.java
java TraversalOrderDemo
~~~

Kết quả trong trường hợp không có tiến trình ngoài can thiệp vào thư mục tạm:

~~~text
children=[a.txt, b.txt, docs]
tree=[., a.txt, b.txt, docs, docs/intro.txt]
~~~

**Vì sao kết quả ổn định?**

- **children** lấy con trực tiếp rồi sort theo String từ tên file, nên **a.txt** trước **b.txt**, rồi **docs**.
- **tree** chuyển đường dẫn tuyệt đối sang tên tương đối và thống nhất dấu phân cách thành **/** trước khi sort: đường dẫn gốc được biểu diễn bằng **"."**; thứ tự từ điển là **.**, **a.txt**, **b.txt**, **docs**, **docs/intro.txt**.
- Việc **tạo b.txt trước a.txt** không ảnh hưởng kết quả đã sort.
- Đoạn **finally** không dựa vào alphabet để xóa: FileVisitor xóa mỗi file tại **visitFile** và xóa directory trong **postVisitDirectory**, bảo đảm con được xử lý trước cha trong quá trình duyệt thành công.

**Giới hạn của ví dụ:** nếu có lỗi I/O, xung đột quyền truy cập hoặc một tiến trình khác thay đổi cây trong lúc duyệt, chương trình có thể ném IOException thay vì in đủ hai dòng; bản thân filesystem không cung cấp một snapshot bất biến tự động chỉ vì gọi Files.list/Files.walk.

## 8. Muốn duyệt từng nhánh theo tên: sắp xếp sibling trước khi đệ quy

Sort toàn bộ kết quả **Files.walk(root).sorted(...)** hữu ích khi chỉ cần **danh sách cuối cùng**. Nhưng nếu bạn phải **vừa duyệt vừa thực hiện thao tác theo đúng thứ tự từng thư mục**, hãy sắp xếp **tập con trực tiếp** trước khi gọi đệ quy vào từng nhánh.

Mẫu chức năng Java:

~~~java
static void visitByName(Path root, Path current) throws IOException {
    System.out.println(root.relativize(current));

    try (Stream<Path> entries = Files.list(current)) {
        List<Path> children = entries
                .sorted((left, right) -> left.getFileName().toString()
                        .compareTo(right.getFileName().toString()))
                .toList();

        for (Path child : children) {
            if (Files.isDirectory(child,
                    java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                visitByName(root, child);
            } else {
                System.out.println(root.relativize(child));
            }
        }
    }
}
~~~

Đây là **một phương thức minh họa**, không chạy độc lập: cần khai báo trong class, import **java.nio.file.Files**, **java.nio.file.Path**, **java.util.List**, **java.util.stream.Stream**, **java.io.IOException**. Khi gọi với root là một directory, nó duyệt depth-first với các **mục con được sắp xếp theo tên**.

Nếu muốn hiện **thư mục trước file**, hãy dùng comparator so loại trước rồi so tên:

~~~java
Comparator<Path> foldersFirst = Comparator
        .comparing((Path p) -> !Files.isDirectory(
                p, LinkOption.NOFOLLOW_LINKS))
        .thenComparing(p -> p.getFileName().toString());
~~~

Đây là **mảnh code minh họa** cần import **java.util.Comparator**, **java.nio.file.Files**, **java.nio.file.LinkOption**, **java.nio.file.Path**. Boolean **false** (thư mục) đứng trước **true** (không phải thư mục). Nếu yêu cầu group theo loại, không nên kỳ vọng **String sort** tự động làm được.

**Cảnh báo:** kiểm tra **Files.isDirectory** trong comparator có thể quan sát trạng thái khác nhau khi directory bị thay đổi đồng thời; đối với dữ liệu cần nhất quán, nên thu thập metadata thành đối tượng dữ liệu rồi sort snapshot, đồng thời xử lý lỗi truy cập rõ ràng. Trên cây có symlink, chương trình phải quy định **theo symlink** hay chỉ coi symlink là một entry. Mẫu trên không tự theo thư mục symlink vì có NOFOLLOW_LINKS.

## 9. Thứ tự theo tên, số, thời gian, kích thước: chọn comparator theo yêu cầu

| Yêu cầu | Cách làm phù hợp | Lưu ý |
| --- | --- | --- |
| Tên A–Z theo ký tự Java | **Comparator.comparing(p -> p.getFileName().toString())** | Phân biệt chữ hoa/thường, không có “natural number order” |
| Tên không phân biệt hoa/thường | **String.CASE_INSENSITIVE_ORDER**, thêm tie-breaker theo tên nguyên bản | Tránh kết quả phụ thuộc đầu vào khi hai tên chỉ khác hoa/thường |
| Giao diện theo ngôn ngữ người dùng | **Collator** với Locale xác định | Quy tắc ngôn ngữ, dấu và tương đương không giống compareTo; cần tie-breaker nếu phải tất định |
| File mới sửa gần nhất trước | Lấy **Files.getLastModifiedTime**, sắp xếp giảm dần | Có thể trùng timestamp, cần tie-breaker; metadata có thể đổi khi đọc |
| Dung lượng lớn trước | Lấy **Files.size**, sort giảm dần | Files.size có thể lỗi hoặc chưa phản ánh một snapshot đồng thời |
| Thư mục trước, file sau | Comparator theo **loại entry**, rồi tên | Dùng NOFOLLOW_LINKS nếu không muốn symlink bị coi như directory |
| Tên có số theo thứ tự “file2” trước “file10” | **Natural numeric comparator** do bạn kiểm soát | Không phải thứ tự mặc định của String.compareTo |
| Trình tự nghiệp vụ riêng | Map tên thành **ưu tiên** rồi sort, thêm thứ tự phụ | Viết rõ quy tắc cho tên chưa được liệt kê |

### 9.1. Comparator cần một quy tắc phụ để kết quả tất định

Nếu có hai mục được comparator coi là **bằng nhau** (ví dụ sort không phân biệt chữ hoa cho **a.txt** và **A.txt**), phương thức sort ổn định vẫn **giữ thứ tự tương đối ban đầu** của các phần tử bằng nhau. Nhưng thứ tự đầu vào của Files.list là không bảo đảm, nên **kết quả cuối vẫn có thể khác**. Thêm tie-breaker:

~~~java
Comparator<String> byName = String.CASE_INSENSITIVE_ORDER
        .thenComparing(Comparator.naturalOrder());
~~~

Mảnh code này cần import **java.util.Comparator**. So sánh bỏ phân biệt hoa trước, nếu bằng nhau thì so String nguyên bản. Điều đó định nghĩa thứ tự rõ ràng ngay cả khi filesystem trả các tên theo thứ tự khác nhau.

Tương tự, nếu sort theo thời gian sửa mà hai file trùng timestamp, có thể xếp tiếp theo tên để có quy tắc ổn định.

### 9.2. Sort trên metadata: nên tách pha đọc và pha so sánh

Với thời gian sửa/dung lượng, phép đọc thuộc tính file có thể ném IOException; không nên giấu IOException bằng cách trả về giá trị mặc định trong comparator. Cách dễ bảo trì hơn:

1. Liệt kê các đường dẫn cần xét.
2. Đọc thuộc tính quan tâm cho từng đường dẫn, xử lý lỗi rõ ràng.
3. Tạo các bản ghi chứa Path + thuộc tính đã đọc.
4. Sort danh sách bản ghi bằng comparator có tiêu chí chính/phụ.
5. Sử dụng thứ tự đã được quyết định.

Một metadata snapshot trong bộ nhớ vẫn không **khóa filesystem**: nếu file thay đổi sau khi đọc metadata, dữ liệu thực tế có thể khác. Khi một hành động phụ thuộc metadata hiện tại, cần xác nhận lại hoặc thiết kế xử lý cạnh tranh ở tầng phù hợp.

## 10. Liệt kê nhiều lần không phải một snapshot ổn định

Ngay cả khi **cùng máy, cùng thư mục**, bạn không được giả định hai lần **Files.list** sẽ luôn có cùng thứ tự hoặc cùng tập kết quả:

- Một chương trình khác có thể tạo/xóa/đổi tên file giữa hai lần.
- Filesystem có thể thay đổi cấu trúc lưu thư mục sau thao tác.
- Provider hệ thống file (đĩa cục bộ, mạng, archive, cloud mount) có quy tắc riêng.
- Quy tắc so sánh đường dẫn phụ thuộc hệ thống (case-sensitive/case-insensitive) trong khi sort String thường dùng thứ tự Java.
- Một số API liệt kê là **weakly consistent** và không khóa một ảnh chụp nguyên tử trước các thay đổi đồng thời.

**Sắp xếp giải quyết thứ tự**, không tự giải quyết **tính nhất quán của tập file**. Nếu cần xử lý chính xác một tập bất biến, phải xác định quy trình nghiệp vụ (ví dụ đóng băng nguồn, chụp danh sách cùng metadata rồi kiểm tra lại, khóa/cơ chế snapshot của filesystem nếu có).

Đặc biệt không dùng:

~~~java
Path first = Files.list(directory).findFirst().orElseThrow();
~~~

để chọn “file đầu tiên theo tên”. Ngoài việc **không đóng stream** trong mảnh này, không có tiêu chí tên nào được áp dụng nên file chọn được không có tính tất định nghiệp vụ. Thay vào đó, phải đặt comparator rõ ràng và dùng try-with-resources.

## 11. Hiệu năng, giới hạn bộ nhớ và độ sâu cây

**Files.list** có thể liệt kê lười một thư mục lớn; **Files.walk** có thể đi qua cả cây mà không cần xây toàn bộ danh sách trong RAM. Tuy nhiên, khi thêm **sorted()**, việc sắp xếp thường cần **gom toàn bộ phần tử** trước khi phát ra kết quả cuối. Với hàng triệu mục, số đối tượng Path, chuỗi, metadata và bộ nhớ sort có thể rất lớn.

Nếu cần **DFS theo alphabet**, có thể sort **mỗi tập sibling** của từng thư mục trước khi đệ quy, chỉ giữ danh sách một thư mục trên mỗi mức recursion. Điều đó giảm nhu cầu sort toàn bộ cây, nhưng trên một thư mục có cực nhiều con vẫn phải giữ nhiều phần tử; recursion sâu có thể gây **StackOverflowError** nếu dùng đệ quy Java không giới hạn. Với cây sâu, có thể chọn **stack tường minh** hoặc một cơ chế traversal khác.

**Files.walk(root, maxDepth)** giới hạn độ sâu cần đọc khi ứng dụng không muốn đi hết cây. **maxDepth = 0** chỉ phát root; cấp 1 bao gồm root và các mục con trực tiếp (nếu đọc được). Với **Files.walkFileTree**, có overload truyền các option và maxDepth. Giới hạn độ sâu khác với sắp xếp; cần chọn cả hai theo nghiệp vụ.

Nếu muốn vừa lọc vừa sort: áp dụng lọc đúng logic rồi sort dữ liệu cần thiết. Nhưng khi muốn “mục đầu tiên theo sort”, thao tác **sorted().findFirst()** vẫn có thể phải xem mọi phần tử đầu vào, không nhanh như “lấy phần tử đầu tiên filesystem trả về”.

## 12. Duyệt để thao tác: cần thứ tự theo phụ thuộc, không chỉ theo tên

### 12.1. Tạo hoặc copy cây: cha trước con

Khi sao chép một cây thư mục sang vị trí khác, phải đảm bảo thư mục đích cha tồn tại trước khi ghi file con. Có thể dùng **walkFileTree** với **preVisitDirectory** để tạo thư mục đích trước khi xử lý file.

**Không lấy Files.walk đã sort và giả định tự tạo mọi thư mục cha**: thứ tự Path sau sort tùy comparator; chính code cần rõ quy tắc tạo cha, hoặc chủ động dùng **Files.createDirectories(parent)** khi phù hợp.

### 12.2. Xóa cây: con trước cha

Khi muốn xóa cây **được sở hữu và đã được phép xóa**, thư mục cha không thể xóa khi còn file hoặc thư mục con. Sử dụng **visitFile** để xóa file và **postVisitDirectory** để xóa thư mục đã duyệt xong.

**Không dùng tên A–Z để suy ra thứ tự xóa an toàn**. Một danh sách file đã sắp xếp không đảm bảo ràng buộc “xóa hết con trước cha” nếu comparator được chọn sai. **Files.walkFileTree** thể hiện phụ thuộc cấu trúc rõ hơn; kể cả vậy, xóa có thể thất bại do file mới xuất hiện, thiếu quyền hoặc trạng thái đồng thời.

### 12.3. Thứ tự không thay thế xử lý lỗi

**walkFileTree** cho phép triển khai **visitFileFailed** và xử lý lỗi truyền vào **postVisitDirectory**. Với pipeline nghiêm ngặt, không được nuốt lỗi để báo "đã duyệt hết" hoặc "đã xóa sạch" khi thực tế chỉ xử lý một phần. Cần xác định chính sách dừng hay tiếp tục và ghi nhận các phần tử thất bại.

## 13. Lưu ý về symbolic link, quyền và sự thay đổi đồng thời

Duyệt cây trên filesystem không tin cậy có nhiều rủi ro hơn thứ tự:

1. **Symbolic link** có thể dẫn ra ngoài root nếu ứng dụng chọn FOLLOW_LINKS; mặc định Files.walk/walkFileTree không theo symbolic link nhưng cần hiểu provider.
2. Có thể có **vòng lặp liên kết** khi FOLLOW_LINKS. Java có cơ chế phát hiện vòng và báo lỗi như **FileSystemLoopException** trong tình huống tương ứng.
3. Người dùng khác có thể **đổi symlink hoặc đường dẫn sau khi bạn kiểm tra**. Mẫu kiểm tra Path rồi mới mở/xóa là race TOCTOU.
4. **Files.isDirectory** và **Files.exists** không phải khóa. Kết quả vừa đọc không bảo đảm giữ nguyên đến bước tiếp theo.
5. Quyền truy cập có thể khác ở từng nhánh; công cụ duyệt phải quản lý IOException và UncheckedIOException.
6. Khi duyệt **để xóa**, không thay tên root bằng input tùy ý của người dùng trong một ví dụ cleanup. Trong hệ thống đối kháng, cân nhắc cơ chế xử lý thư mục dựa trên handle hoặc **SecureDirectoryStream** nếu có hỗ trợ.

Ví dụ chỉ xóa **thư mục tạm do chính chương trình tạo**, giúp phân biệt hướng dẫn học thuật với công cụ xóa toàn bộ đường dẫn bất kỳ.

## 14. Lỗi thường gặp

1. **Cho rằng File.listFiles trả tên alphabet.** Hợp đồng không bảo đảm; sort tường minh.
2. **Dựa vào thứ tự tạo file trên đĩa.** Thứ tự tạo và thứ tự được liệt kê không phải một hợp đồng chung.
3. **Nhầm Files.list với Files.walk.** list lấy một cấp, walk có thể đi toàn bộ cây.
4. **Nghĩ Files.walk là alphabet vì dùng depth-first.** DFS xác định cách đi qua nhánh, không xác định thứ tự sibling.
5. **In Files.walk rồi mới .sorted() trong cùng stream.** Stream đã tiêu thụ không thể tái sử dụng; tạo pipeline đúng thứ tự trước terminal operation.
6. **Quên close Stream từ Files.list / Files.walk.** Tài nguyên thư mục có thể bị giữ cho đến khi đóng.
7. **Dùng sorted() mà không hiểu comparator.** String sort phân biệt hoa/thường, không tự sort số “tự nhiên” hoặc theo ngôn ngữ.
8. **Không có tie-breaker khi comparator coi hai tên bằng nhau.** Kết quả có thể kế thừa thứ tự không xác định ban đầu.
9. **Dùng Files.size hoặc getLastModifiedTime trong comparator nhưng nuốt IOException.** Có thể dẫn đến thứ tự sai và che giấu lỗi; nên lấy metadata có xử lý lỗi trước.
10. **Giả định sorted() miễn phí.** Nó cần lưu dữ liệu, tốn CPU/RAM trên thư mục cực lớn.
11. **Dùng thứ tự tên để xóa cây.** Xóa phải dựa trên quan hệ con trước cha, không chỉ alphabet.
12. **Theo symbolic links mà không giới hạn phạm vi.** Có thể đi ngoài root hoặc gặp vòng lặp.
13. **Bỏ qua việc filesystem thay đổi khi duyệt.** Sort không cung cấp snapshot nhất quán.
14. **Không giới hạn độ sâu hay dung lượng trên cây không tin cậy.** Rủi ro thời gian, RAM, số file và độ sâu recursion.
15. **Coi null từ File.listFiles như mảng rỗng.** Null có thể là đường dẫn không phải directory hoặc lỗi I/O; cần phân biệt.
16. **Không phân biệt sort để hiển thị với sort để thao tác.** Có thể cần những thuật toán khác nhau.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Files.list(dir) có bảo đảm file đầu là file tên nhỏ nhất không?  
**Đáp:** Không. Muốn sắp xếp theo tên, áp dụng **sorted(Comparator...)** hoặc thu thập và sort.

**Câu 2:** Files.walk(root) duyệt kiểu gì và có đảm bảo alphabet giữa sibling không?  
**Đáp:** Nó duyệt **depth-first**, directory trước entries bên dưới, nhưng **không bảo đảm thứ tự sibling alphabet**.

**Câu 3:** Vì sao sorted() trên Stream kết quả của Files.walk khác với “duyệt từng nhánh đã sort”?  
**Đáp:** sorted() sắp xếp **danh sách đầu ra toàn cục** sau quá trình khám phá; duyệt sibling theo tên đặt thứ tự **trước khi xuống từng nhánh**. Chúng khác về thời điểm, memory và cách thực hiện side effects.

**Câu 4:** File.listFiles() có thể trả null không?  
**Đáp:** Có, nếu File không phải directory hoặc xảy ra lỗi I/O. Không được luôn gọi Arrays.sort trực tiếp mà chưa kiểm tra.

**Câu 5:** Muốn giao diện sắp xếp tên không phân biệt hoa, làm sao giữ kết quả tất định khi "A.txt" và "a.txt" bị coi là bằng nhau?  
**Đáp:** Thêm **thenComparing(Comparator.naturalOrder())** cho tên nguyên bản làm tiêu chí phụ.

**Câu 6:** Khi xóa cả cây, nên xóa directory cha ở preVisitDirectory hay postVisitDirectory?  
**Đáp:** **postVisitDirectory**, sau khi đã xử lý hết con, kết hợp visitFile.

**Câu 7:** Sort bằng Files.getLastModifiedTime có phải tự tạo snapshot nguyên tử của toàn filesystem không?  
**Đáp:** Không. Thuộc tính có thể bị thay đổi khi đọc/duyệt; cần thiết kế theo yêu cầu nhất quán thực tế.

**Câu 8:** Files.walk(root, 0) duyệt bao nhiêu mức?  
**Đáp:** Chỉ **root**. Với maxDepth 1, gồm root và các mục con trực tiếp khi có thể đọc.

## 16. Kết luận

Thứ tự mà filesystem trả về khi liệt kê không phải thứ tự nghiệp vụ của bạn. **File.listFiles**, **Files.list**, **DirectoryStream** không hứa alphabet; **Files.walk** và **walkFileTree** cung cấp cách đi qua cây, nhưng **không quy định sibling theo tên**.

Nếu mục tiêu là **danh sách A–Z**, hãy sort với comparator rõ ràng. Nếu cần **DFS theo sibling A–Z**, hãy thu thập và sắp xếp từng cấp **trước khi đệ quy**. Nếu công việc là **tạo/xóa cây**, hãy ưu tiên **thứ tự phụ thuộc cha/con**, ví dụ preVisitDirectory hoặc postVisitDirectory. Khi kết quả phải tái lập, còn cần quy tắc phụ (tie-breaker), charset/cách so tên thống nhất và kiểm soát biến động của dữ liệu nguồn.

### Tài liệu tham khảo

- [Oracle Java SE 17 — File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): list và listFiles không bảo đảm thứ tự, giá trị null và danh sách con trực tiếp.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): list, walk, walkFileTree, xử lý symlink và tài nguyên.
- [Oracle Java SE 17 — FileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html): các callback preVisitDirectory/visitFile/postVisitDirectory.
- [Oracle Java SE 17 — Stream.sorted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): sắp xếp, thứ tự, stateful operation và chi phí.
- [Oracle Java SE 17 — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): tiêu chí chính/phụ để sắp xếp.
