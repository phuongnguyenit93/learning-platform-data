# Đọc root, tên tệp, thư mục cha và từng đoạn tên với `Path` (Java 7+)

> **Chủ đề:** `java.nio.file.Path` mô tả một đường dẫn trong hệ thống tệp. Bài học tập trung vào năm thao tác quan sát cấu trúc: `getRoot()`, `getFileName()`, `getParent()`, `getNameCount()` và `getName(int)`, kèm việc duyệt các thành phần bằng vòng lặp `for-each`. Các API thành phần của `Path` xuất hiện từ Java 7 và vẫn sử dụng trong Java 17+. Ví dụ chạy với JDK 17 nên có thể dùng `Path.of(...)` (được bổ sung từ Java 11); khi cần tương thích mã nguồn Java 7, dùng `Paths.get(...)` cho phần tạo đường dẫn.

## 1. Cần biết gì trước khi bóc tách một đường dẫn?

Một đường dẫn có thể chứa:

- **Root (gốc):** điểm bắt đầu của một đường dẫn có gốc, chẳng hạn `/` trên hệ thống kiểu Unix hoặc ổ đĩa/thư mục chia sẻ trên Windows.
- **Các name elements (đoạn tên):** những thành phần nằm sau gốc, thường ứng với tên thư mục hay tên cuối cùng.
- **File name (tên cuối):** phần tên nằm ở cuối đường dẫn, nếu có; tên cuối **có thể là tên thư mục**, không bắt buộc là tệp thông thường.
- **Parent (đường dẫn cha):** đường dẫn trước phần tên cuối cùng, nếu có; `getParent()` không tự đi đọc metadata của hệ thống tệp.

Ví dụ mô hình:

```text
Đường dẫn tuyệt đối kiểu Unix:

/home/lan/projects/report.txt
^-------------------------- toàn bộ Path
^                              root: /
 ^-- home    (name[0])
      ^-- lan        (name[1])
          ^-- projects      (name[2])
                   ^-- report.txt     (name[3])

fileName = report.txt
parent   = /home/lan/projects
root     = /
nameCount = 4
```

Đây là **sơ đồ theo cú pháp đường dẫn Unix**, không phải lời khẳng định rằng tệp thật tồn tại. Trên Windows, root có thể là tên ổ đĩa hoặc điểm chia sẻ mạng, và ký hiệu phân cách đường dẫn thường là dấu `\`. Giá trị chính xác của các thành phần phụ thuộc **file-system provider** mà `Path` thuộc về.

### 1.1. `Path` không phải bản thân tệp

`Path` là một đối tượng **biểu diễn đường dẫn**. Việc gọi `getFileName()` hay `getParent()` chỉ đọc các thành phần của biểu diễn đó; **không yêu cầu file hiện hữu**, không mở file, không đọc dữ liệu, không truy cập metadata và không kiểm tra quyền truy cập.

Ví dụ:

```java
Path path = Path.of("project", "missing-folder", "missing.txt");
System.out.println(path.getFileName()); // missing.txt
```

Đây là snippet với import `java.nio.file.Path`. Kể cả khi `missing.txt` chưa tồn tại, lệnh vẫn có thể trả tên cuối; nó đang phân tích **tên trong đường dẫn**, không hỏi filesystem xem đó là file hay không.

Nếu cần xác minh thực tế, hãy dùng API thuộc `java.nio.file.Files` như `exists`, `isRegularFile`, `isDirectory` hoặc `readAttributes` theo mục tiêu. `Files.exists` trả false không phải lúc nào cũng chứng minh “chắc chắn không tồn tại”, vì việc truy cập có thể bị giới hạn; không dùng những phương thức này thay một chiến lược quản lý lỗi I/O đúng.

## 2. Bảng API thành phần cần ghi nhớ

| Method | Giá trị trả về | Ý nghĩa | Tình huống đặc biệt |
| --- | --- | --- | --- |
| `getRoot()` | `Path` hoặc `null` | Thành phần root nếu đường dẫn có root | Đường dẫn tương đối đơn giản thường trả `null` |
| `getFileName()` | `Path` hoặc `null` | **Đoạn tên cuối cùng**, không tính root | Path chỉ gồm root có thể trả `null` |
| `getParent()` | `Path` hoặc `null` | Phần đường dẫn trước đoạn tên cuối, nếu có | Một tên đơn lẻ thường có parent là `null` |
| `getNameCount()` | `int` | Số name elements, **không tính root** | Path chỉ gồm root thường cho 0 |
| `getName(i)` | `Path` | Đoạn tên ở chỉ số `i` từ 0 | `i` ngoài `0..nameCount-1` gây lỗi |
| `iterator()` | `Iterator<Path>` | Duyệt lần lượt các name elements | Root không xuất hiện như một name element |
| `subpath(begin,end)` | `Path` | Nhiều name elements liên tiếp, không gồm root | `end` là chỉ số **exclusive** |
| `isAbsolute()` | `boolean` | Path có phải dạng absolute theo provider không | Khác với việc file có tồn tại hay không |

Lưu ý: `getFileName()`, `getParent()` và `getRoot()` trả về **`Path`**, không phải `String`. Nếu muốn hiển thị, dùng `toString()`; nếu muốn nối đường dẫn, ưu tiên các method kiểu `Path` như `resolve` thay vì ghép chuỗi bằng dấu phân cách.

### 2.1. Không suy ra root từ tên đầu tiên

Với `Path.of("data", "reports", "q4.txt")`:

- `getRoot() == null`.
- `getName(0).toString().equals("data")`.
- `getFileName().toString().equals("q4.txt")`.
- `getParent()` là `data/reports` (hiển thị bằng dấu phân cách native).
- `getNameCount() == 3`.

`"data"` là **name element đầu tiên**, **không phải root**. Một đường dẫn tương đối có thể có nhiều tên nhưng không có root.

### 2.2. Không có dấu phân cách ở tên riêng lẻ

`getName(i)` trả về một Path tương đối đại diện cho **một name element**. Ví dụ `path.getName(1)` trả `reports`, không trả `data/reports`. Nếu cần nhiều đoạn tên, dùng `subpath` hoặc `getParent` theo mục tiêu.

## 3. Ví dụ Java 17 đầy đủ: phân rã một đường dẫn tương đối

Lưu thành `PathComponentsDemo.java`:

```java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class PathComponentsDemo {
    static String slash(Path path) {
        return path == null ? "null" : path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path path = Path.of("projects", "reports", "q4.txt");

        System.out.println("relative=" + !path.isAbsolute());
        System.out.println("root=" + slash(path.getRoot()));
        System.out.println("fileName=" + path.getFileName());
        System.out.println("parent=" + slash(path.getParent()));
        System.out.println("nameCount=" + path.getNameCount());

        List<String> names = new ArrayList<>();
        for (int i = 0; i < path.getNameCount(); i++) {
            System.out.println("name[" + i + "]=" + path.getName(i));
            names.add(path.getName(i).toString());
        }
        System.out.println("iteration=" + String.join(" | ", names));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 PathComponentsDemo.java
java PathComponentsDemo
```

Stdout đã kiểm tra với JDK 17:

```text
relative=true
root=null
fileName=q4.txt
parent=projects/reports
nameCount=3
name[0]=projects
name[1]=reports
name[2]=q4.txt
iteration=projects | reports | q4.txt
```

### 3.1. Đọc đầu ra theo đúng cấu trúc

`relative=true` cho biết `path.isAbsolute() == false`, không phải kết quả kiểm tra sự tồn tại của tệp.

`root=null` là kết quả đúng vì đường dẫn được xây bằng các tên tương đối, không có root. `fileName=q4.txt` là phần tên cuối cùng. `parent=projects/reports` là đường dẫn dẫn đến đoạn tên trước đó.

`nameCount=3` bao gồm `projects`, `reports`, `q4.txt`. Vòng lặp dùng chỉ số `0 <= i < path.getNameCount()` để không truy cập ngoài phạm vi. `iteration` chỉ là một cách biểu diễn nối ba tên cho mục đích quan sát, **không thay đổi Path**.

### 3.2. Tại sao có hàm `slash(Path)`?

Trên Windows, `Path.toString()` thường dùng `\` làm dấu phân cách; trên Unix, dấu `/` thường được dùng. Hàm `slash` chỉ **chuẩn hóa cách hiển thị trong ví dụ** để stdout nhất quán. Nó không phải giải pháp chuyển file path giữa các hệ điều hành và **không nên dùng kết quả replace như đường dẫn filesystem chung**. Trong logic thực tế, giữ object `Path` và dùng `resolve`, `getParent`, `getName`…

### 3.3. Cách duyệt name elements bằng `for-each`

`Path` triển khai `Iterable<Path>`, nên đoạn duyệt có thể viết ngắn hơn:

```java
for (Path name : path) {
    System.out.println(name);
}
```

Đây là snippet, `path` đã được khai báo. Nó duyệt từng name element theo thứ tự, không có root trong dãy. Với `projects/reports/q4.txt`, các dòng lần lượt là `projects`, `reports` và `q4.txt`.

Không dùng `String.split("/")` để làm thay nhiệm vụ này. Dấu phân cách native có thể khác, và `Path` có quy tắc parsing theo file-system provider (bao gồm drive root/UNC trên Windows). Duyệt qua `Path` an toàn hơn cho cấu trúc Path thực tế.

## 4. `getRoot()`: thành phần gốc khác gì đường dẫn cha?

**Root** mô tả phần bắt đầu đặc biệt của đường dẫn theo filesystem. **Parent** mô tả đường dẫn đứng trước đoạn tên cuối. Hai khái niệm không đồng nghĩa.

Với một đường dẫn tuyệt đối kiểu Unix:

```text
Path:      /home/lan/docs/report.pdf
root:      /
parent:    /home/lan/docs
fileName:  report.pdf
names:     home, lan, docs, report.pdf
```

Với một đường dẫn tuyệt đối kiểu Windows (minh họa cú pháp Windows, **không phải code chạy đa nền tảng**):

```text
Path:      C:\work\docs\report.pdf
root:      C:\
parent:    C:\work\docs
fileName:  report.pdf
names:     work, docs, report.pdf
```

Các dòng trên chỉ diễn giải **cấu trúc**, không khẳng định file tồn tại. Với UNC path trên Windows, root có thể liên quan đến tên máy chủ/chia sẻ. Một số dạng đường dẫn như **drive-relative** trên Windows có quy tắc root và absolute riêng; vì vậy không suy ra toàn bộ hành vi chỉ từ việc chuỗi có ký tự `:`.

### 4.1. Điều gì xảy ra với Path không có root?

`Path.of("reports", "2026.txt")` là một ví dụ tương đối. Trong provider mặc định thông thường:

```java
Path relative = Path.of("reports", "2026.txt");
System.out.println(relative.getRoot()); // null
```

Không có root **không phải lỗi**. Nó có nghĩa đường dẫn cần được diễn giải tương đối với một ngữ cảnh (thường là thư mục làm việc hoặc một base Path được cung cấp) khi thực hiện I/O.

### 4.2. Kiểm chứng root mà không phụ thuộc tên ổ đĩa/thư mục làm việc

```java
Path absolute = Path.of(".").toAbsolutePath();
Path root = absolute.getRoot();
System.out.println(root != null);
```

Đây là snippet với `java.nio.file.Path`. Trên provider mặc định thông thường, kết quả là `true`. **Không in nguyên absolute path làm stdout cố định** khi muốn ví dụ tái lập, vì thư mục làm việc và tên ổ đĩa phụ thuộc máy.

`Path.toAbsolutePath()` có thể dựa vào thư mục hiện tại của tiến trình, nhưng **không tự kiểm tra file tồn tại**; nó chuyển sang biểu diễn tuyệt đối theo provider. Nếu trong path có đoạn `.` hoặc `..`, cần hiểu `normalize()` là thao tác khác.

### 4.3. Path chỉ gồm root có fileName/parent không?

Đối với một Path chỉ chứa root, root chính là toàn bộ Path; không có **name element** đứng sau nó. Vì vậy:

- `getNameCount() == 0`.
- `getFileName() == null`.
- `getParent() == null`.
- `getRoot() != null`.

Đây là tình huống quan trọng khi viết code gọi `getFileName().toString()`: nếu đầu vào có thể là root, cần kiểm tra null trước khi dereference.

## 5. `getFileName()`: tên cuối cùng, không phải chứng nhận là tệp

Tên method là “file name”, nhưng nó **không xác định loại đối tượng trên đĩa**.

Ví dụ:

```java
Path folder = Path.of("data", "archive");
System.out.println(folder.getFileName()); // archive
```

Nếu trên filesystem `archive` là thư mục, `getFileName()` vẫn trả `archive`. Nếu chưa có đường dẫn đó, kết quả cũng tương tự. Method chỉ xem **phần tử tên cuối**.

### 5.1. File name có bao gồm extension không?

Có. Với `Path.of("report.tar.gz")`, `getFileName()` trả một `Path` có biểu diễn `report.tar.gz`. Nó **không tự tách** thành stem, extension hay MIME type.

Nếu ứng dụng cần phân tích extension, đó là một quy tắc riêng. Một tên như `.gitignore`, `report.` hoặc `archive.tar.gz` có nhiều trường hợp cạnh; không nên cho rằng `getFileName()` đã biết “phần mở rộng” của file.

### 5.2. Đường dẫn kết thúc bằng dấu phân cách

Trong nhiều provider mặc định, `Path.of("projects/reports/")` được chuẩn hóa về mặt cú pháp đầu vào để đoạn tên cuối vẫn là `reports`, chứ không tạo thêm một name element rỗng như khi tự tách chuỗi.

Tuy vậy, **đừng dùng dấu / cuối để xác định “đây chắc chắn là thư mục”**. Loại file/thư mục thật cần API `Files` và quyết định theo metadata.

### 5.3. Null cần xử lý ở đâu?

Khi dữ liệu Path đến từ API bên ngoài, `getFileName()` có thể trả null trong những trường hợp như Path chỉ chứa root. Vì vậy nếu chuẩn bị tên để hiển thị:

```java
Path name = path.getFileName();
String displayName = name == null ? "(root)" : name.toString();
```

Đây là snippet có `Path path` đã tồn tại. Không ghi thẳng `path.getFileName().toString()` khi đầu vào chưa bảo đảm có name element.

## 6. `getParent()`: cha về mặt cú pháp, không phải tra filesystem

`getParent()` lấy **đường dẫn đứng trước name element cuối**, nếu có.

Với:

```java
Path path = Path.of("a", "b", "c.txt");
System.out.println(path.getParent()); // a/b hoặc a\b tùy hệ điều hành
```

Nó trả `a/b` về cấu trúc. Không có thao tác xác minh thư mục `a` hoặc `b` đã tồn tại. Ngay cả một đường dẫn có nội dung `..` cũng được xem theo những đoạn tên hiện tại.

### 6.1. Chỉ một name element thì parent là null

`Path.of("report.txt")` có một đoạn tên; nó không có parent được biểu diễn **ngay trong Path tương đối đó**. Vì vậy `getParent()==null`.

Điều này không có nghĩa `report.txt` “không nằm trong thư mục nào”. Khi thực hiện I/O, Path tương đối có thể được hiểu theo thư mục làm việc hiện tại. `getParent` chỉ trả lời **đường dẫn đã viết có bao nhiêu đoạn trước file name**, không tự bổ sung current working directory.

Nếu cần biểu diễn tuyệt đối theo provider, có thể dùng:

```java
Path absolute = Path.of("report.txt").toAbsolutePath();
Path parent = absolute.getParent();
```

Đây là snippet. `parent` lúc này thường là thư mục hiện tại được suy ra khi tạo absolute Path. Việc này vẫn không tự bảo đảm file có tồn tại; muốn tra cứu file thật thì phải dùng `Files` thích hợp.

### 6.2. Parent có thể chứa `.` và `..`

Xét `work/./drafts/../note.txt`. `getParent()` ban đầu sẽ diễn giải là `work/./drafts/..`, **không tự rút gọn** thành `work`. Muốn xử lý thành phần `.`/`..` về mặt cú pháp thì gọi `normalize()` rồi đọc parent của Path mới. Chú ý phần 8 về sự khác biệt giữa lexical normalization và đường đi thật qua symbolic links.

## 7. Các trường hợp ranh giới: tên đơn, đường dẫn rỗng, dấu chấm và root

Những giá trị đầu vào khác nhau có thể nhìn giống nhau nếu chỉ in string, nhưng method thành phần trả kết quả khác.

Lưu thành `PathBoundaryDemo.java`:

```java
import java.nio.file.Path;

public class PathBoundaryDemo {
    public static void main(String[] args) {
        Path single = Path.of("report.txt");
        Path empty = Path.of("");
        Path dot = Path.of(".");
        Path root = Path.of(".").toAbsolutePath().getRoot();

        System.out.println("single.root=" + single.getRoot());
        System.out.println("single.parent=" + single.getParent());
        System.out.println("single.fileName=" + single.getFileName());
        System.out.println("single.count=" + single.getNameCount());

        System.out.println("empty.root=" + empty.getRoot());
        System.out.println("empty.parent=" + empty.getParent());
        System.out.println("empty.fileName='" + empty.getFileName() + "'");
        System.out.println("empty.count=" + empty.getNameCount());

        System.out.println("dot.fileName=" + dot.getFileName());
        System.out.println("dot.count=" + dot.getNameCount());

        System.out.println("root.present=" + (root != null));
        if (root != null) {
            System.out.println("root.isAbsolute=" + root.isAbsolute());
            System.out.println("root.parent=" + root.getParent());
            System.out.println("root.fileName=" + root.getFileName());
            System.out.println("root.count=" + root.getNameCount());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PathBoundaryDemo.java
java PathBoundaryDemo
```

Stdout **đã được kiểm chứng trên provider hệ thống mặc định của JDK 17**:

```text
single.root=null
single.parent=null
single.fileName=report.txt
single.count=1
empty.root=null
empty.parent=null
empty.fileName=''
empty.count=1
dot.fileName=.
dot.count=1
root.present=true
root.isAbsolute=true
root.parent=null
root.fileName=null
root.count=0
```

### 7.1. Điểm bất ngờ: empty Path có một tên rỗng

`Path.of("")` đại diện cho một **empty path**. Ở provider thông thường được kiểm thử, `getNameCount()==1` và `getFileName()` là một Path rỗng có `toString().equals("")`. Điều này **khác** Path chỉ gồm root: root-only path có **0 name elements** và `getFileName()==null`.

Vì vậy:

- `Path.of("")` không có root, nhưng có name element rỗng theo biểu diễn API.
- `Path.of(".")` có tên `"."`, là một name element có nội dung dấu chấm.
- `Path.of("report.txt")` có một name element thông thường.
- `root` có root, nhưng không có name element.

Trường hợp này cần được test khi xử lý đường dẫn được lấy từ input của người dùng. **Không đoán empty Path bằng `getNameCount()==0`.** Dùng ràng buộc đầu vào rõ ràng khi ứng dụng không cho phép path rỗng.

### 7.2. `null` không giống Path rỗng

`Path.of((String) null)` sẽ không tạo một Path rỗng hợp lệ; API yêu cầu đầu vào không null. Còn `Path.of("")` là biểu diễn path rỗng. Khi một method nhận `Path`, không nên coi `null`, `Path.of("")`, `Path.of(".")` và Path chỉ gồm root là cùng một trạng thái.

### 7.3. Tại sao in root thực tế bằng phép kiểm tra boolean?

Tên root có thể khác giữa máy chạy Linux, macOS và Windows, hoặc giữa ổ đĩa của các môi trường Windows. Ví dụ chỉ in `root.present`, `root.isAbsolute`, `root.parent`, `root.fileName` và `root.count` để tập trung vào **tính chất API**, không trói test vào một tên ổ đĩa cố định.

## 8. Dấu `.`, `..` và `normalize()` ảnh hưởng đến thành phần nào?

Trong một Path, `.` và `..` có thể xuất hiện như các name elements:

- `.` thường biểu thị vị trí hiện tại.
- `..` thường biểu thị cấp cha theo quy tắc giải quyết đường dẫn.
- `getNameCount()` và `getName(i)` có thể **đếm và trả lại chúng** trước khi chuẩn hóa.
- `getParent()` ban đầu trả phần đường dẫn trước tên cuối **theo biểu diễn hiện tại**.
- `normalize()` tạo Path mới bằng cách loại các đoạn thừa về mặt cú pháp, khi có thể; nó không truy cập filesystem.

Lưu thành `PathLexicalDemo.java`:

```java
import java.nio.file.Path;

public class PathLexicalDemo {
    static String slash(Path p) {
        return p == null ? "null" : p.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path raw = Path.of("work", ".", "drafts", "..", "note.txt");
        Path clean = raw.normalize();

        System.out.println("raw=" + slash(raw));
        System.out.println("raw.parent=" + slash(raw.getParent()));
        System.out.println("raw.fileName=" + raw.getFileName());
        System.out.println("raw.count=" + raw.getNameCount());
        System.out.println("raw.name1=" + raw.getName(1));
        System.out.println("raw.name3=" + raw.getName(3));
        System.out.println("normalized=" + slash(clean));
        System.out.println("normalized.parent=" + slash(clean.getParent()));
        System.out.println("normalized.count=" + clean.getNameCount());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PathLexicalDemo.java
java PathLexicalDemo
```

Stdout đã kiểm chứng:

```text
raw=work/./drafts/../note.txt
raw.parent=work/./drafts/..
raw.fileName=note.txt
raw.count=5
raw.name1=.
raw.name3=..
normalized=work/note.txt
normalized.parent=work
normalized.count=2
```

### 8.1. Phân tích trước và sau chuẩn hóa

Trước `normalize()` có **năm** name elements: `work`, `.`, `drafts`, `..`, `note.txt`. Vì vậy:

- `getNameCount() == 5`.
- `getName(1)` trả `.`.
- `getName(3)` trả `..`.
- `getParent()` giữ `work/./drafts/..`.

Sau `normalize()`, các đoạn `.` và `drafts/..` được rút gọn về mặt cú pháp, để lại `work/note.txt`. Khi ấy `getNameCount() == 2` và `getParent()` là `work`.

**Quan trọng:** `normalize()` không tự xác minh rằng `work/drafts` có tồn tại. Với symbolic links, việc rút gọn `name/..` có thể **không tương đương** với cách filesystem thật giải quyết liên kết. Khi cần xác định đường dẫn thực của đối tượng hiện hữu, `toRealPath()` là một thao tác khác, có I/O và có thể ném `IOException`.

### 8.2. Có nên normalize mọi Path ngay khi nhận?

Không phải lúc nào cũng thế. Nếu ứng dụng cần lưu **biểu diễn nguyên văn** để hiển thị hoặc audit, normalize có thể làm mất dấu vết input ban đầu. Nếu ứng dụng cần so sánh/kiểm tra một cấu trúc đường dẫn dạng lexical, normalize có thể hữu ích.

Hãy xác định mục tiêu trước: hiển thị input, ghép đường dẫn, phân tích cú pháp, hay truy cập đối tượng thật. Đừng normalize chỉ vì muốn in tên tệp.

## 9. `getNameCount()` và `getName(i)`: chỉ số bắt đầu từ 0

Với ba name elements `data`, `reports`, `2026.txt`:

```java
Path report = Path.of("data", "reports", "2026.txt");
int count = report.getNameCount(); // 3

Path a = report.getName(0); // data
Path b = report.getName(1); // reports
Path c = report.getName(2); // 2026.txt
```

Đây là snippet. Mỗi lần `getName(i)` trả một Path có **một đoạn tên**. Phần root không được đếm; nếu đầu vào là tuyệt đối, các đoạn tên vẫn đánh chỉ số bắt đầu từ 0 **sau root**.

Nếu `i < 0` hoặc `i >= getNameCount()`, `getName(i)` báo lỗi chỉ số. Vì vậy luôn duyệt bằng:

```java
for (int i = 0; i < path.getNameCount(); i++) {
    Path segment = path.getName(i);
    // Sử dụng segment theo đúng hợp đồng.
}
```

Đây là snippet với `Path path` đã khai báo. Không dùng `<= path.getNameCount()`; giới hạn trên là **exclusive**.

### 9.1. `subpath` khác `getName` như thế nào?

`getName(i)` lấy **một đoạn**, còn `subpath(beginIndex, endIndex)` lấy **một dãy** đoạn liên tiếp. `endIndex` là chỉ số **không bao gồm**.

Với `Path.of("data","reports","2026.txt")`:

- `subpath(0, 2)` cho `data/reports`.
- `subpath(1, 3)` cho `reports/2026.txt`.
- `getName(2)` cho `2026.txt`.
- `subpath(0, getNameCount())` lấy toàn bộ name elements **không kèm root** nếu Path có root.

`subpath` cũng trả `Path` tương đối, không phải String đã join và không tự điều chỉnh bằng filesystem. Chỉ số phải thỏa ràng buộc của API; `beginIndex == endIndex` không có nghĩa tạo subpath rỗng hợp lệ.

### 9.2. Duyệt bằng iterator

`Path` có thể xuất hiện trực tiếp trong `for (Path segment : path)` vì là `Iterable<Path>`. Nó giúp code dễ đọc khi không cần index. Nếu phải kèm số thứ tự cho UI hoặc breadcrumb, vòng lặp `for (int i=0; ...)` phù hợp hơn.

## 10. `resolve` và `resolveSibling` giúp ghép thay vì nối String

Đọc tên/cha/root thường đi cùng việc xây đường dẫn mới. Dùng `Path.resolve` khi ghép một đoạn tương đối vào base:

```java
Path base = Path.of("data", "reports");
Path file = base.resolve("2026.txt");
```

`file` có name elements `data`, `reports`, `2026.txt`. Không cần viết `base + "/" + "2026.txt"`, vì đường dẫn cần tuân theo filesystem provider và tránh lỗi dấu phân cách.

`resolveSibling` thay đoạn tên cuối bằng một sibling relative name theo parent của path hiện tại:

```java
Path next = file.resolveSibling("2027.txt");
```

Nếu `file` là `data/reports/2026.txt`, `next` có cấu trúc `data/reports/2027.txt`.

### 10.1. Ví dụ runnable: resolve, relativize, sibling và subpath

Lưu thành `PathResolveDemo.java`:

```java
import java.nio.file.Path;

public class PathResolveDemo {
    static String slash(Path p) {
        return p == null ? "null" : p.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path base = Path.of("data", "reports");
        Path report = base.resolve("2026.txt");

        System.out.println("base=" + slash(base));
        System.out.println("report=" + slash(report));
        System.out.println("fileName=" + report.getFileName());
        System.out.println("parent=" + slash(report.getParent()));
        System.out.println("root=" + report.getRoot());
        System.out.println("relativeToBase=" + slash(base.relativize(report)));
        System.out.println("sibling=" + slash(report.resolveSibling("2027.txt")));
        System.out.println("firstTwoNames=" + slash(report.subpath(0, 2)));
        System.out.println("report.count=" + report.getNameCount());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PathResolveDemo.java
java PathResolveDemo
```

Stdout đã kiểm chứng:

```text
base=data/reports
report=data/reports/2026.txt
fileName=2026.txt
parent=data/reports
root=null
relativeToBase=2026.txt
sibling=data/reports/2027.txt
firstTwoNames=data/reports
report.count=3
```

**Giải thích quan hệ giữa các method:**

- `base` chỉ chứa hai name elements, `report` chứa ba.
- `resolve("2026.txt")` thêm đoạn tên cuối vào base; `getFileName()` đọc đoạn mới thêm.
- `getParent()` lấy hai đoạn trước tên cuối, nên khớp `base`.
- `base.relativize(report)` tạo đường dẫn `2026.txt` tương đối từ base đến report (hai Path phải tương thích theo provider/loại root). Với các root khác nhau hoặc absolute/relative không tương thích, phép relativize có thể không hợp lệ.
- `report.resolveSibling("2027.txt")` tạo một Path cùng cha nhưng có tên cuối khác.
- `report.subpath(0,2)` lấy hai name elements đầu; khác `getParent()` ở chỗ kết quả của `subpath` là **đường dẫn tương đối theo tên**, không giữ root của Path gốc nếu có.

### 10.2. Không gọi `relativize` giữa hai Path tùy tiện

`relativize` được thiết kế tính Path tương đối giữa hai Path tương thích. Trên Unix, một absolute Path và một relative Path không thể luôn relativize trực tiếp. Trên Windows, các root khác ổ đĩa cũng có những hạn chế riêng. Hãy thiết lập cùng loại/path provider/root thích hợp trước khi dùng.

Nếu chỉ cần đọc file name hoặc parent, không cần gọi `relativize`.

## 11. Đường dẫn tương đối và tuyệt đối: cái nào có root?

### 11.1. Relative Path

`Path.of("assets", "icons", "logo.png")` có thể được đánh giá tương đối với thư mục làm việc. Nó không chứa root trong biểu diễn. `getFileName()` là `logo.png`; `getParent()` là `assets/icons`; `getNameCount()` là 3.

### 11.2. Absolute Path

`Path.of("assets", "icons", "logo.png").toAbsolutePath()` có thể được đưa về dạng absolute dựa trên quy tắc provider và current working directory của tiến trình. Trên provider mặc định, absolute path thường có root.

**Không hard-code output đầy đủ của `toAbsolutePath()` trong unit test portable**, vì giá trị cụ thể phụ thuộc máy, project working directory, ổ đĩa, thư mục chạy build tool và người dùng.

### 11.3. Windows có cú pháp root phức tạp hơn

Trên Windows, ngoài ví dụ có ổ đĩa như `C:\work\report.txt` còn có dạng UNC trỏ đến chia sẻ mạng. Dạng như `C:report.txt` **khác** `C:\report.txt` về ý nghĩa đường dẫn liên quan đến ổ đĩa; đừng suy đoán absolute chỉ dựa vào ký tự `C:`.

Trên Unix, ký tự backslash `\` có thể là một ký tự bình thường trong tên file thay vì dấu phân cách. Vì thế `Path.of("a\\b")` không phải mẫu portable để tạo hai name elements. Ưu tiên `Path.of("a", "b")` khi biết các thành phần riêng lẻ.

### 11.4. File-system provider khác nhau

`Path` có thể đến từ default filesystem, một hệ thống tệp ảo hoặc một provider khác như ZIP filesystem tùy cấu hình ứng dụng. Phân tích root và tên cần tôn trọng semantics của provider đó. Không giả định mọi Path đều có root giống Windows/Unix và không trộn Path từ provider khác nhau trong `resolve`/`relativize` mà không kiểm tra ràng buộc.

## 12. Path và filesystem thật: kiểm tra bằng `Files` khi cần

Khi chỉ cần **đọc tên** thì dùng các method trên `Path`. Khi cần **tạo file, đọc file, kiểm tra loại đối tượng**, sử dụng `Files`. Hai cấp API có trách nhiệm tách biệt.

Lưu thành `PathFilesystemDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathFilesystemDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("path-demo-");
        Path file = directory.resolve("notes.txt");

        try {
            Files.writeString(file, "ok", StandardCharsets.UTF_8);

            System.out.println("fileName=" + file.getFileName());
            System.out.println("parentMatches=" + file.getParent().equals(directory));
            System.out.println("absolute=" + file.isAbsolute());
            System.out.println("rootPresent=" + (file.getRoot() != null));
            System.out.println("exists=" + Files.isRegularFile(file));
            System.out.println("content=" +
                    Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PathFilesystemDemo.java
java PathFilesystemDemo
```

Stdout ở môi trường kiểm thử cho phép tạo tệp tạm:

```text
fileName=notes.txt
parentMatches=true
absolute=true
rootPresent=true
exists=true
content=ok
```

**Phân biệt các bước:**

1. `Files.createTempDirectory` **thực sự tạo** một thư mục tạm. Tên thư mục có hậu tố ngẫu nhiên nên ví dụ không in tên cụ thể.
2. `directory.resolve("notes.txt")` mới **xây Path**, **chưa tạo file**.
3. `Files.writeString` tạo/ghi nội dung file bằng UTF-8. Method này được thêm từ **Java 11**.
4. `file.getFileName()`, `getParent()`, `getRoot()` và `isAbsolute()` mô tả cấu trúc Path; không cần đọc file để trả kết quả.
5. `Files.isRegularFile(file)` thực hiện một phép kiểm tra về filesystem thật, còn `Files.readString` đọc nội dung.
6. `finally` dọn file và thư mục **do chương trình tự tạo**, tránh để lại dữ liệu tạm sau khi demo.

**Không áp dụng đoạn xóa file tạm này cho đường dẫn do người dùng chọn.** Chỉ xóa những resource mà code chủ động tạo và sở hữu.

### 12.1. `Path.of` và `Paths.get` khác nhau thế nào về phiên bản?

`Path` và `Paths.get(...)` đã có từ Java 7, thuộc NIO.2. `Path.of(...)` được bổ sung từ **Java 11**, tiện hơn về cách viết trong code hiện đại. Hai dòng sau có mục tiêu tương đương trên provider mặc định:

```java
Path modern = Path.of("data", "reports", "2026.txt"); // Java 11+.
Path older = java.nio.file.Paths.get("data", "reports", "2026.txt"); // Java 7+.
```

Đây là snippet, không phải hai hệ thống Path khác nhau. Với dự án dùng Java 17+, ưu tiên API phù hợp và thống nhất theo conventions dự án; **không cần quay về `java.io.File` chỉ để đọc tên/path**. `java.io.File` vẫn có khả năng chuyển đổi với `Path` bằng `File.toPath()` khi tích hợp API cũ, nhưng trong code NIO hiện đại `Path` là kiểu biểu đạt rõ hơn.

## 13. `getParent()`, `normalize()` và symbolic links không thay thế `toRealPath()`

Một lỗi tư duy thường thấy: “Có parent là `a/b`, vậy thư mục thật trên đĩa chắc chắn là `a/b`”. Thực tế `getParent()` chỉ trả về **cú pháp path**. Nếu một phần path là symbolic link, cách hệ thống resolve đến đối tượng vật lý có thể khác cấu trúc tên.

Ba thao tác có bản chất riêng:

| Thao tác | Có I/O tra cứu hệ thống tệp? | Mục đích |
| --- | --- | --- |
| `getParent()` | Không | Lấy phần tên đứng trước tên cuối |
| `normalize()` | Không | Rút gọn các đoạn `.` và `..` theo quy tắc lexical |
| `toAbsolutePath()` | Không tra cứu sự tồn tại của file | Đưa path về biểu diễn tuyệt đối theo provider |
| `toRealPath()` | Có | Phân giải thành đường dẫn thật theo file system; có thể ném `IOException` |

`toRealPath()` theo mặc định có thể theo symbolic links theo hợp đồng và cần đối tượng thật tồn tại. Nếu cần không theo links, xem `LinkOption.NOFOLLOW_LINKS` và hành vi cụ thể trong tài liệu API. Đừng dùng nó cho mọi trường hợp chỉ cần tên cuối vì nó thay đổi chi phí và điều kiện lỗi.

### 13.1. Kiểm tra đường dẫn người dùng và nguy cơ path traversal

Nếu ứng dụng nhận một đường dẫn do người dùng cung cấp rồi kết hợp với thư mục gốc được phép, đừng chỉ dùng `getFileName()` hoặc `normalize()` rồi tuyên bố an toàn. Một chuỗi chứa `..`, absolute path hoặc đường dẫn qua symbolic link có thể thoát khỏi phạm vi dự kiến nếu xử lý sai.

Một phép kiểm tra lexical có thể là **bước đầu** khi validate input đã được chuẩn hóa, nhưng không bảo đảm chống mọi thay đổi filesystem đồng thời hoặc symbolic links. Với thao tác nhạy cảm, cần chính sách quyền truy cập, loại bỏ/giới hạn root không mong muốn, xử lý symlinks và cơ chế mở file an toàn theo môi trường.

Bài này dạy **đọc cấu trúc Path**, không phải một quy trình đầy đủ để bảo vệ file upload/download khỏi directory traversal. Không tự biến tên cuối của đường dẫn thành một “đường dẫn an toàn” nếu chưa có thiết kế quyền và isolation.

## 14. Tình huống thường gặp và API nên dùng

| Mục tiêu | API | Ghi chú |
| --- | --- | --- |
| Lấy root/ổ đĩa/shares phần gốc | `path.getRoot()` | Có thể `null` nếu Path không có root |
| Lấy tên cuối để hiển thị | `path.getFileName()` | Có thể `null`; không cam kết là file thường |
| Lấy đường dẫn cha | `path.getParent()` | Có thể `null` với một tên đơn lẻ hoặc root |
| Đếm số name elements | `path.getNameCount()` | Không tính root |
| Lấy tên thứ `i` | `path.getName(i)` | Index bắt đầu từ 0 |
| Duyệt toàn bộ các tên | `for (Path name : path)` | Trả từng `Path` thành phần |
| Lấy dãy tên đầu hoặc giữa | `path.subpath(begin,end)` | End-exclusive, không giữ root |
| Kết hợp base và tên con | `base.resolve(name)` | Giữ ở dạng Path, không tự nối dấu phân cách |
| Thay tên cuối bằng sibling | `path.resolveSibling(name)` | Hữu ích cho đổi tên có cùng parent về cấu trúc |
| Biến thành absolute | `path.toAbsolutePath()` | Không chứng minh file tồn tại |
| Rút gọn `.`/`..` | `path.normalize()` | Chỉ lexical |
| Lấy path thật | `path.toRealPath()` | Có I/O và lỗi theo filesystem |
| Kiểm tra file/thư mục tồn tại | `Files.exists`/`Files.isDirectory` | Câu hỏi về filesystem thực |

### 14.1. Dùng API nào khi làm breadcrumb?

Muốn hiển thị từng đoạn thư mục theo trình tự, dùng `getNameCount` và `getName(i)`. Nếu cần breadcrumb đầy đủ từ root, **xử lý root riêng** bằng `getRoot()`, sau đó duyệt các name elements. Nếu không có root, biểu diễn như một chuỗi đường dẫn tương đối theo sản phẩm.

Mẫu ý tưởng:

```java
Path root = path.getRoot();
if (root != null) {
    // Hiển thị root nếu UI cần.
}
for (Path name : path) {
    // Hiển thị từng name element theo thứ tự.
}
```

Đây là snippet với `path` đã có. Trong UI thật, mỗi breadcrumb cũng cần xác định Path tích lũy tương ứng với link, không chỉ nối chuỗi hiển thị.

### 14.2. Tên cuối của thư mục cũng là `getFileName()`

Nếu người dùng chọn `/home/lan/photos` là **thư mục**, `getFileName()` trả `photos`. Tên method chỉ kế thừa thuật ngữ filesystem, không áp đặt loại đối tượng. Để hiển thị “file” hay “folder” khác nhau, ứng dụng cần metadata hoặc thông tin có sẵn từ UI/file chooser.

## 15. Những lỗi phổ biến nên tránh

| Lỗi | Vì sao sai | Cách tiếp cận đúng |
| --- | --- | --- |
| Nghĩ `getRoot()` chính là đoạn tên đầu tiên | Root và name element là hai thành phần khác nhau | Đọc root riêng; tên bắt đầu từ `getName(0)` |
| Nghĩ `getFileName()` luôn là file trên đĩa | Nó chỉ là đoạn cuối, có thể là thư mục hoặc chưa tồn tại | Dùng `Files` khi cần loại đối tượng |
| Gọi `getFileName().toString()` với path root-only | `getFileName()` có thể null | Kiểm tra null |
| Nghĩ `getParent()==null` tức path không có thư mục vật lý | Một tên tương đối chưa ghi current working directory | Dùng base/`toAbsolutePath` khi cần |
| Nghĩ `getParent()` tự normalize dấu `..` | Nó trả cấu trúc tên hiện tại | Gọi `normalize()` có chủ đích |
| Dùng `getName(0)` trên root-only path | Root không phải name element, `nameCount=0` | Kiểm tra `getNameCount()` trước |
| Dùng vòng lặp `i <= getNameCount()` | Vượt chỉ số cuối | Dùng `i < getNameCount()` |
| Dùng `subpath(0,0)` để lấy empty Path | Chỉ số không hợp lệ theo hợp đồng subpath | Đọc điều kiện end-exclusive |
| Cho rằng `Path.of("")` có `nameCount()==0` | Empty Path thường có một name element rỗng | Phân biệt empty Path với root-only Path |
| Tự tách chuỗi theo `"/"` | Dấu phân cách/provider khác nhau | Dùng `Path` và các method của nó |
| In absolute path và khẳng định stdout giống nhau trên mọi máy | Working directory/root khác nhau | Kiểm tra thuộc tính thay vì tên tuyệt đối cố định |
| Nhầm `Path.of` đã có từ Java 7 | `Path.of` từ Java 11 | Java 7 dùng `Paths.get` |
| Nhầm `toAbsolutePath` với `toRealPath` | Một cái đổi dạng, một cái tra filesystem | Chọn theo mục tiêu |
| Xem lexical normalize như biện pháp bảo mật hoàn chỉnh | Symlink/TOCTOU và provider vẫn có tác động | Bổ sung kiểm tra quyền và thiết kế mở file an toàn |
| Dùng `File.toString()`/Path string ghép tay để tạo path con | Dễ lỗi separator hoặc absolute override | Dùng `resolve`, `getParent`, `getName` |
| Bỏ qua các trường hợp null trong UI | Root, một tên đơn có thể không có fileName/parent | Thiết kế trạng thái không có component rõ |

## 16. Checklist khi review code dùng `Path`

1. Đầu vào có thể là **relative**, **absolute**, **empty Path**, **root-only** hay một tên đơn lẻ không?
2. Khi gọi `getRoot()`, đã xử lý trường hợp `null` mà không đoán sai root chưa?
3. Khi gọi `getFileName()`, đã xét path chỉ gồm root chưa?
4. Khi gọi `getParent()`, có nhầm parent lexical với thư mục hiện hữu không?
5. Khi duyệt `getName(i)`, có dùng phạm vi `0 <= i < getNameCount()` không?
6. Nếu cần root trong danh sách breadcrumb, có xử lý root **riêng** thay vì coi là name index 0 không?
7. Nếu dùng `subpath`, đã nhớ end index là exclusive và root không nằm trong kết quả chưa?
8. Nếu path có `.` hoặc `..`, có quyết định có cần `normalize()` trước khi trình bày không?
9. Nếu cần truy cập file thật, đã sử dụng `Files` hoặc `toRealPath()` theo đúng nhu cầu chưa?
10. Có đang ghép bằng string separator thủ công không? Có thể thay bằng `resolve`?
11. Có hard-code đường dẫn Windows trong code phải chạy Unix hoặc ngược lại không?
12. Nếu nhận path từ người dùng, có giới hạn root/permissions/symlink theo chính sách bảo mật phù hợp không?
13. Nếu code đích là Java 7–10, có tránh `Path.of` và dùng `Paths.get` không?
14. Nếu hiển thị đường dẫn, có phân biệt tên cuối với loại file/thư mục thật không?
15. Các test có bao gồm các ranh giới 0, 1, nhiều name elements và root-only không?

## 17. Bài tập có đáp án để tự kiểm tra

**Câu 1.** `Path.of("a", "b", "c.txt")` có root, parent, fileName và nameCount gì?  
**Đáp án:** Root `null`; parent `a/b`; fileName `c.txt`; nameCount `3`.

**Câu 2.** `getName(0)` của `Path.of("projects", "logs", "app.log")` là gì?  
**Đáp án:** `projects`, tức đoạn tên đầu tiên; không phải root.

**Câu 3.** `getName(2)` trong ví dụ trên trả một String hay Path?  
**Đáp án:** Trả một `Path` tương đối biểu diễn `app.log`. Dùng `toString()` nếu cần chuỗi để hiển thị.

**Câu 4.** Vì sao `getParent()` của `Path.of("report.txt")` là null?  
**Đáp án:** Path hiện tại chỉ gồm một name element và không biểu diễn đoạn cha phía trước. Điều này không chứng minh tệp không nằm trong thư mục làm việc khi chạy I/O.

**Câu 5.** Path chỉ gồm root có `getNameCount()` bao nhiêu?  
**Đáp án:** Thường là `0` vì root không được đếm như name element; `getFileName()` và `getParent()` là null.

**Câu 6.** `Path.of("")` khác Path chỉ gồm root ở điểm nào?  
**Đáp án:** Empty Path thường có một name element rỗng (`nameCount=1`), không có root; root-only Path có root nhưng không có name element.

**Câu 7.** `Path.of(".")` có tên cuối là gì?  
**Đáp án:** `"."`, một đoạn tên dấu chấm; có thể được xử lý khi normalize tùy ngữ cảnh.

**Câu 8.** `getParent()` có tự kiểm tra thư mục trên đĩa không?  
**Đáp án:** Không. Nó là thao tác cấu trúc trên Path, không phải tra metadata.

**Câu 9.** Đối với `work/./drafts/../note.txt`, trước normalize có bao nhiêu name elements và parent là gì?  
**Đáp án:** Năm name elements; parent là `work/./drafts/..`. Sau normalize, Path thành `work/note.txt`, có hai name elements và parent `work`.

**Câu 10.** `subpath(0,2)` trên `data/reports/2026.txt` trả gì?  
**Đáp án:** `data/reports`, gồm name index 0 và 1; end index 2 không được bao gồm.

**Câu 11.** `base.resolve("2026.txt")` có mở hay tạo file không?  
**Đáp án:** Không. Nó chỉ tạo Path mới. Phải dùng `Files` hoặc API I/O khác để làm việc với file thực.

**Câu 12.** `resolveSibling("2027.txt")` trên `data/reports/2026.txt` cho cấu trúc gì?  
**Đáp án:** `data/reports/2027.txt`, một Path ở cùng vị trí cha với tên cuối thay đổi.

**Câu 13.** `Path.of("foo").toAbsolutePath().getParent()` có thể khác `Path.of("foo").getParent()` không?  
**Đáp án:** Có. Absolute Path có thể bổ sung prefix từ thư mục làm việc theo provider; parent của Path chỉ có một tên tương đối ban đầu là null.

**Câu 14.** Nếu trên filesystem có thư mục tên `photos`, `getFileName()` của đường dẫn đến nó có trả `photos` không?  
**Đáp án:** Có. Method đọc tên cuối bất kể nó là file hay directory thật.

**Câu 15.** Trong Java 7, nên viết `Path.of(...)` hay `Paths.get(...)`?  
**Đáp án:** `Paths.get(...)`. `Path.of` là tiện ích được thêm ở Java 11, dù các method như `getRoot/getParent/getName` có từ Java 7.

**Câu 16.** Gọi `normalize()` có chứng minh đường dẫn an toàn khi người dùng cung cấp input không?  
**Đáp án:** Không. Normalize lexical không xử lý toàn bộ symlinks, quyền truy cập và các thay đổi filesystem đồng thời.

### Thực hành A — Năm thành phần

Thay `PathComponentsDemo` bằng `Path.of("src", "main", "java", "App.java")`. Dự đoán `root`, `parent`, `fileName`, `nameCount` và `getName(2)` rồi kiểm chứng bằng chương trình.

### Thực hành B — Root-only và empty Path

Chạy `PathBoundaryDemo`, bổ sung kiểm tra `getFileName()==null` cho root-only, `getFileName().toString().isEmpty()` cho empty Path và số name elements của mỗi trường hợp.

### Thực hành C — Chỉ số vượt phạm vi

Dùng `Path.of("a","b").getName(2)` trong một đoạn `try/catch` dành cho lỗi chỉ số, quan sát exception, rồi sửa vòng lặp thành `i < getNameCount()`. Không gọi method này với chỉ số cuối bằng count trong code production.

### Thực hành D — Normalize trước hay sau lấy parent?

Tạo `Path.of("a", ".", "b", "..", "c.txt")`. So sánh `raw.getParent()`, `raw.normalize().getParent()` và toàn bộ name elements trước/sau. Giải thích tại sao `getParent()` không tự xóa `..`.

### Thực hành E — Tách tên bằng Path thay vì String

Viết hàm nhận `Path` và trả `List<String>` chứa mỗi `getName(i).toString()`. Thử với đường dẫn tương đối, empty Path và root-only; không dùng `String.split`.

### Thực hành F — Breadcrumb

Viết hàm duyệt root riêng rồi duyệt tên, tạo các Path tích lũy bằng `resolve` để ứng dụng UI có thể hiển thị từng cấp đường dẫn. Kiểm thử trên provider mặc định của hệ điều hành hiện tại mà không hard-code ký tự phân cách.

### Thực hành G — File I/O thật

Chạy `PathFilesystemDemo`, sau đó thử đổi `notes.txt` thành tên khác; xác nhận `getFileName()` đổi theo, `getParent()` vẫn khớp thư mục tạm, và `Files.readString` đọc nội dung đúng. Dọn thư mục tạm sau test.

### Thực hành H — Dữ liệu người dùng

Giả lập người dùng gửi `../secret.txt` rồi phân tích bằng `Path.of(input).getNameCount()` và `getName(i)`. Giải thích vì sao biết có `..` chỉ là một bước kiểm tra, chưa đủ để bảo vệ một thư mục file upload khỏi symlink/path traversal.

## 18. Tài liệu chính thức

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `getRoot`, `getFileName`, `getParent`, `getNameCount`, `getName`, `subpath`, `iterator`, `resolve`, `relativize`, `normalize` và `toAbsolutePath`.
- [Java SE 17 — Paths](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Paths.html): `Paths.get` từ Java 7.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): thao tác thật trên filesystem, kiểm tra/đọc/ghi tạo file.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): cú pháp/path provider và dấu phân cách.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): tùy chọn xử lý symbolic links khi truy cập metadata/real path.
- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): lấy default filesystem và các provider khác.

**Ghi nhớ:** `getRoot()` hỏi “đường dẫn có phần gốc nào?”, `getFileName()` hỏi “tên cuối là gì?”, `getParent()` hỏi “phần trước tên cuối là gì?”, còn `getNameCount()` và `getName(i)` giúp truy cập từng name element sau root. Các method này phân tích **cấu trúc Path**, không xác nhận filesystem thật. Kiểm tra null cho root/fileName/parent, nhớ root không tính vào số tên, và dùng `Files` khi bài toán chuyển từ “xem tên” sang “thao tác với file”.
