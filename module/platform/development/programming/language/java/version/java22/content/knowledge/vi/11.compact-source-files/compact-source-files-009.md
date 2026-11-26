# Chuyển chương trình sang lớp có tên cùng cấu trúc dự án khi quy mô tăng

## 1. Mục tiêu và phạm vi phiên bản

Một tệp nguồn gọn phù hợp để bắt đầu một chương trình nhỏ. Khi chương trình có dữ liệu dùng chung, nhiều quy tắc nghiệp vụ hoặc nhiều người cùng sửa, bạn cần những tên lớp và ranh giới trách nhiệm rõ ràng hơn.

Bài này thuộc chương **Tệp nguồn gọn** của module Java 22, tập trung vào kiến thức tiếp tục hữu ích trong Java hiện đại. Java 22 có một bản preview của tính năng; **compact source files và instance `main` đã trở thành tính năng chính thức ở Java 25**. Các ví dụ dưới đây dùng JDK 25 hoặc mới hơn và không cần `--enable-preview`. Đây là mốc tối thiểu cho bài thực hành, không phải khẳng định Java 25 là phiên bản mới nhất. Xem [thay đổi ngôn ngữ ở Java SE 25](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html).

Sau bài học, bạn có thể:

- Đưa thành viên của một tệp nguồn gọn vào lớp có tên mà giữ được hành vi.
- Chọn giữa instance `main` và `public static void main(String[] args)`.
- Tách dữ liệu, nghiệp vụ và điểm khởi chạy thành các tệp có trách nhiệm rõ ràng.
- Đặt package và tổ chức cây thư mục; biên dịch, chạy và đóng gói chương trình bằng công cụ JDK.

Bạn cần biết phương thức, đối tượng, `List`, `record` và thao tác cơ bản với terminal. Các lệnh minh họa sử dụng PowerShell trên Windows.

## 2. Khi nào nên chuyển sang lớp có tên?

Số dòng chỉ là một dấu hiệu tham khảo. Hãy nhìn vào cách chương trình thay đổi và được sử dụng:

| Dấu hiệu trong chương trình | Bước tổ chức có ích |
| --- | --- |
| Một thao tác ngắn, dữ liệu nằm ngay trong tệp | Giữ tệp nguồn gọn nếu vẫn dễ đọc |
| Cần tạo đối tượng với dữ liệu khác nhau | Dùng lớp có tên và constructor |
| Cần gọi nghiệp vụ từ chương trình khác hoặc kiểm thử | Tách nghiệp vụ thành lớp có tên |
| Xử lý đầu vào, tính toán và in kết quả thường thay đổi riêng | Tách các trách nhiệm |
| Nhiều kiểu dữ liệu và tính năng bắt đầu trùng tên | Đưa mã vào package có tên |
| Thường xuyên cần biên dịch, kiểm thử và đóng gói lặp lại | Dùng cấu trúc dự án và cấu hình build thống nhất |

Lớp được khai báo ngầm của tệp gọn không phải một kiểu để mã nguồn khác gọi bằng tên hoặc tạo trực tiếp bằng `new`. Khi cần một kiểu có API, constructor hay khả năng triển khai interface, lớp có tên là bước phát triển phù hợp. Quy tắc về lớp ngầm được mô tả tại [JLS 8.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8).

Một lộ trình thực tế:

```text
Tệp nguồn gọn
    -> Lớp có tên trong một tệp
    -> Các lớp dữ liệu và nghiệp vụ riêng
    -> Package và cây thư mục dự án
    -> Quy trình build, kiểm thử, đóng gói
```

Mỗi bước giải quyết một nhu cầu cụ thể. Một tiện ích nhỏ vẫn có thể dừng ở bước đầu.

## 3. Điểm xuất phát: một CLI trong tệp nguồn gọn

Giả sử `TaskApp.java` hiển thị những công việc chưa hoàn thành:

```java
List<Task> tasks = List.of(
        new Task("Đọc record", true),
        new Task("Tách lớp", false),
        new Task("Viết kiểm thử", false)
);

void main() {
    showOpenTasks();
}

void showOpenTasks() {
    long remaining = tasks.stream()
            .filter(task -> !task.done())
            .count();

    IO.println("Còn lại: " + remaining);

    for (Task task : tasks) {
        if (!task.done()) {
            IO.println("- " + task.title());
        }
    }
}

record Task(String title, boolean done) {}
```

Chạy trong thư mục chứa tệp, với JDK 25 hoặc mới hơn:

```powershell
java TaskApp.java
```

Kết quả dự kiến:

```text
Còn lại: 2
- Tách lớp
- Viết kiểm thử
```

Ở bước này, một nơi chứa cả dữ liệu mẫu, cách chọn công việc và cách in ra terminal. Cách tổ chức đó đủ cho việc thử ý tưởng. Nếu sau này có thêm đầu vào từ tệp hoặc giao diện khác, phần lọc công việc sẽ cần được dùng độc lập với phần in.

`List` dùng được trong tệp gọn nhờ cơ chế tự nhập các kiểu công khai từ những package được `java.base` xuất ra. `IO` thuộc `java.lang`; gọi `IO.println(...)` là cách dùng ổn định trong bài. Xem [hướng dẫn compact source files của Java 25](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html).

## 4. Bước đầu tiên: khai báo lớp bao ngoài

Thay nội dung `TaskApp.java` bằng:

```java
import java.util.List;

public class TaskApp {
    private final List<Task> tasks = List.of(
            new Task("Đọc record", true),
            new Task("Tách lớp", false),
            new Task("Viết kiểm thử", false)
    );

    void main() {
        showOpenTasks();
    }

    private void showOpenTasks() {
        long remaining = tasks.stream()
                .filter(task -> !task.done())
                .count();

        IO.println("Còn lại: " + remaining);

        for (Task task : tasks) {
            if (!task.done()) {
                IO.println("- " + task.title());
            }
        }
    }

    record Task(String title, boolean done) {}
}
```

Ba thay đổi cần chú ý:

1. Bao các khai báo dữ liệu, phương thức và `record` trong `public class TaskApp`.
2. Đặt `import java.util.List;` trước khai báo lớp.
3. Giới hạn những thành viên nội bộ bằng `private` và giữ `tasks` gắn với từng đối tượng.

Khi chuyển sang đơn vị biên dịch thông thường, cơ chế tự nhập toàn bộ các kiểu nói trên của `java.base` không còn tự đi kèm. Bài này dùng import tường minh cho những kiểu cần thiết. `IO` vẫn dùng được qua `java.lang`. Quy tắc import được quy định trong [JLS 7.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3).

Có thể tiếp tục chạy:

```powershell
java TaskApp.java
```

Hoặc biên dịch rồi chạy:

```powershell
javac --release 25 -encoding UTF-8 TaskApp.java
java TaskApp
```

Trong biến thể này, `Task` vẫn là kiểu lồng trong `TaskApp`. Việc đưa nó thành kiểu cấp cao nhất sẽ là một thay đổi riêng ở bước tiếp theo.

### Lớp có tên vẫn có thể giữ instance main

`void main()` tiếp tục hợp lệ trong lớp có tên trên Java 25+. Với dạng instance này, quá trình khởi chạy cần tạo một đối tượng của lớp ban đầu bằng constructor không tham số. Lớp `TaskApp` ở trên chưa khai báo constructor nên có constructor mặc định phù hợp. Xem [JLS 12.1.4 về gọi main](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4).

Nếu sau đó thêm `TaskApp(TaskService service)`, constructor mặc định không còn được tạo tự động. Bạn cần thiết kế lại điểm khởi chạy cho phù hợp; phần 6 minh họa một `static main` làm nhiệm vụ tạo và nối các đối tượng.

### Không đổi hàng loạt thành static

Đổi riêng `void main()` thành `public static void main(String[] args)` trong ví dụ vừa rồi sẽ khiến lời gọi trực tiếp `showOpenTasks()` không còn phù hợp: `main` lúc này ở ngữ cảnh tĩnh, còn phương thức đó thuộc đối tượng.

Một cầu nối tạm thời có thể là:

```java
public static void main(String[] args) {
    new TaskApp().showOpenTasks();
}
```

Đoạn này thay thế `void main()` trong lớp ở trên. Dữ liệu và phương thức nghiệp vụ vẫn là thành viên đối tượng. Cách tách hoàn chỉnh dưới đây làm cho quan hệ giữa các đối tượng rõ hơn.

## 5. Chọn trách nhiệm trước khi chia tệp

Với ví dụ CLI, ta có ba trách nhiệm:

| Kiểu | Trách nhiệm | Lý do có thể thay đổi |
| --- | --- | --- |
| `Task` | Biểu diễn một công việc | Dữ liệu công việc thay đổi |
| `TaskService` | Chọn và đếm công việc chưa hoàn thành | Quy tắc nghiệp vụ thay đổi |
| `TaskApp` | Tạo dữ liệu, nối các đối tượng, hiển thị kết quả | Cách khởi chạy hoặc giao diện CLI thay đổi |

`TaskService` trả dữ liệu cho bên gọi. Nó không cần biết đầu ra là terminal, trang web hay kiểm thử. Khi muốn kiểm tra quy tắc “công việc nào còn mở”, bạn có thể gọi service với một danh sách do mình chuẩn bị.

Ở quy mô này, đặt cả ba kiểu trong cùng package `vn.example.tasks` giúp giữ các thành phần nội bộ trong phạm vi nhỏ. Tên package này chỉ dùng cho ví dụ; dự án thực tế nên chọn tên theo tổ chức hoặc sản phẩm.

Sơ đồ phụ thuộc dự kiến:

```text
TaskApp -> TaskService -> Task
    \--------------------> Task
```

Mũi tên nghĩa là “sử dụng”. `Task` không cần biết lớp nào sẽ khởi chạy chương trình.

## 6. Phiên bản hoàn chỉnh sau khi tách lớp

Ba tệp dưới đây thay thế hoàn toàn phiên bản một tệp ở các phần trước.

### Task.java: dữ liệu công việc

Đường dẫn từ thư mục gốc dự án: `src/main/java/vn/example/tasks/Task.java`.

```java
package vn.example.tasks;

record Task(String title, boolean done) {}
```

Trong ví dụ này, `Task` chỉ cần được dùng bởi các lớp cùng package, nên chưa cần khai báo `public`.

### TaskService.java: quy tắc chọn công việc

Đường dẫn: `src/main/java/vn/example/tasks/TaskService.java`.

```java
package vn.example.tasks;

import java.util.List;

final class TaskService {
    private final List<Task> tasks;

    TaskService(List<Task> tasks) {
        this.tasks = List.copyOf(tasks);
    }

    List<Task> openTasks() {
        return tasks.stream()
                .filter(task -> !task.done())
                .toList();
    }

    long countOpen() {
        return openTasks().size();
    }
}
```

Thiết kế này có vài chủ đích:

- Dữ liệu đầu vào được truyền qua constructor, nên có thể tạo nhiều service với các danh sách khác nhau.
- Service giữ một bản chụp danh sách bằng `List.copyOf`.
- Quy tắc `!task.done()` tập trung trong `openTasks()`.
- `countOpen()` dùng lại kết quả của quy tắc đó.
- Không có lệnh in trong service.

`countOpen()` ở đây tạo danh sách kết quả rồi lấy kích thước. Với ví dụ nhỏ, cách viết này làm rõ việc dùng chung quy tắc. Nếu khối lượng dữ liệu tăng, có thể cân nhắc một phép `count()` trực tiếp và đưa điều kiện chọn vào phương thức dùng chung.

### TaskApp.java: điểm khởi chạy

Đường dẫn: `src/main/java/vn/example/tasks/TaskApp.java`.

```java
package vn.example.tasks;

import java.util.List;

public final class TaskApp {
    public static void main(String[] args) {
        var service = new TaskService(List.of(
                new Task("Đọc record", true),
                new Task("Tách lớp", false),
                new Task("Viết kiểm thử", false)
        ));

        IO.println("Còn lại: " + service.countOpen());

        for (Task task : service.openTasks()) {
            IO.println("- " + task.title());
        }
    }
}
```

`main` tạo dữ liệu mẫu, tạo service và hiển thị kết quả. Nghiệp vụ có thể được gọi trực tiếp qua service mà không phải chạy CLI.

Dạng `public static void main(String[] args)` vẫn là một điểm vào hợp lệ của Java hiện đại. Bài này chọn nó làm điểm khởi chạy rõ ràng cho ví dụ đóng gói. Bạn vẫn có thể chọn instance `main` khi cách khởi tạo đối tượng phù hợp.

Cả `main()` và `main(String[] args)` có thể là ứng viên trên Java 25+. Nếu một lớp có cả hai dạng hợp lệ, dạng nhận `String[]` được ưu tiên khi khởi chạy. Trong dự án, nên giữ một điểm vào chủ đích để người đọc dễ theo dõi. Xem [quy tắc chọn main trong JLS 12.1.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4).

## 7. Đưa các tệp vào cấu trúc dự án

Cây thư mục cho ví dụ:

```text
task-cli/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── vn/example/tasks/
│   │   │       ├── TaskApp.java
│   │   │       ├── Task.java
│   │   │       └── TaskService.java
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── out/                         # kết quả biên dịch bằng lệnh trong bài
```

Ở đây, các thư mục `resources` và `test` mới chỉ dự phòng cho những bước phát triển tiếp theo. Ba tệp Java ở phần 6 là toàn bộ mã nguồn cần để chạy ví dụ.

Bố trí `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources` theo [quy ước thư mục của Maven](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html). Bạn có thể dùng bố trí đó ngay cả khi đang biên dịch trực tiếp bằng JDK.

| Thành phần | Vai trò |
| --- | --- |
| `src/main/java` | Gốc mã nguồn ứng dụng |
| `vn/example/tasks` | Đường dẫn tương ứng với package `vn.example.tasks` |
| `src/main/resources` | Tài nguyên ứng dụng khi có nhu cầu |
| `src/test/java` | Mã kiểm thử, tách khỏi mã ứng dụng |
| `src/test/resources` | Dữ liệu và tài nguyên dành cho kiểm thử |
| `out` | Thư mục đầu ra được chọn cho các lệnh `javac` trong bài |

**Source root** của ví dụ là `src/main/java`. Phần đường dẫn bên dưới nó tương ứng với tên package. Vì vậy, cùng một khai báo `package vn.example.tasks;` xuất hiện trong cả ba tệp.

`src/main/java` là một quy ước của công cụ build, không phải từ khóa của Java. Còn package là một phần của định danh kiểu, chẳng hạn `vn.example.tasks.TaskApp`.

Chuyển sang package có tên cần thực hiện sau khi đã có khai báo lớp tường minh. Bạn không thể chỉ chèn `package vn.example.tasks;` lên đầu tệp gọn rồi giữ nguyên các phương thức nằm ngoài lớp. Xem [JLS 7.3–7.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3).

### Giữ phạm vi truy cập vừa đủ

Trong ví dụ, `Task` và `TaskService` có package access; những lớp cùng `vn.example.tasks` có thể dùng chúng. Nếu chuyển CLI sang `vn.example.tasks.cli`, đó là package khác. Khi ấy cần thiết kế API với phạm vi truy cập thích hợp cho kiểu, constructor và phương thức được gọi. Thêm `import` không mở rộng quyền truy cập. Xem [JLS 6.6.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.6.1).

Chưa có lý do để chia ví dụ nhỏ thành nhiều package. Có thể tổ chức theo tính năng trước, rồi tách thêm khi từng phần có trách nhiệm và vòng đời thay đổi rõ ràng.

Một package có tên cũng chưa đòi hỏi bạn phải tạo `module-info.java`. Ví dụ này chạy trên classpath, không cấu hình module JPMS riêng.

## 8. Biên dịch và chạy từ thư mục gốc

Mọi lệnh trong phần này được chạy tại thư mục `task-cli` chứa `src`. Nếu đường dẫn có dấu cách, PowerShell có thể chuyển thư mục như sau; hãy thay bằng vị trí dự án của bạn:

```powershell
Set-Location -LiteralPath 'H:\Hoc Java\task-cli'
```

Kiểm tra hai công cụ thuộc JDK dùng cho bài:

```powershell
java --version
javac --version
```

Cả hai cần hỗ trợ Java 25. Sử dụng cùng một bộ JDK giúp tránh tình trạng biên dịch bằng một phiên bản và chạy bằng phiên bản khác ngoài dự kiến.

### Biên dịch cả ba tệp

```powershell
New-Item -ItemType Directory -Path 'out' -Force | Out-Null

$taskSources = @(
    'src/main/java/vn/example/tasks/Task.java'
    'src/main/java/vn/example/tasks/TaskService.java'
    'src/main/java/vn/example/tasks/TaskApp.java'
)

javac --release 25 -encoding UTF-8 -d out $taskSources

if ($LASTEXITCODE -ne 0) {
    throw 'Bien dich that bai. Hay sua loi truoc khi chay.'
}

java -cp out vn.example.tasks.TaskApp
```

`--release 25` đặt mức ngôn ngữ, API nền tảng và đích bytecode cho Java 25. `-encoding UTF-8` tương ứng với cách lưu các tệp ví dụ có chuỗi tiếng Việt. `-d out` chọn thư mục đầu ra; compiler đặt lớp vào cây package bên dưới nó. Xem [tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

Đầu ra có cấu trúc:

```text
out/
└── vn/example/tasks/
    ├── TaskApp.class
    ├── Task.class
    └── TaskService.class
```

Lệnh chạy dùng `out` làm gốc classpath và dùng **tên lớp đầy đủ**:

```powershell
java -cp out vn.example.tasks.TaskApp
```

`out/vn/example/tasks` là nơi chứa tệp `TaskApp.class`, nhưng gốc classpath phải là `out`. Tên lớp trong lệnh chạy đã bao gồm `vn.example.tasks`.

### Vẫn có thể chạy trực tiếp từ mã nguồn

Đặt các tệp đúng cây thư mục rồi chạy:

```powershell
java --source 25 src/main/java/vn/example/tasks/TaskApp.java
```

Source-file mode của Java hiện đại có thể tìm các tệp nguồn cần thiết trong cùng cây nguồn. Vì vậy, việc tách lớp và thêm package không bắt buộc bạn phải dùng công cụ build ngay lập tức. Cơ chế chạy và xác định source root được mô tả trong [tài liệu java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#using-source-file-mode-to-launch-source-code-programs).

Hai cách chạy phục vụ những nhu cầu khác nhau: chạy mã nguồn thuận tiện khi thử chương trình; bước `javac` tạo đầu ra rõ ràng để dùng tiếp khi đóng gói.

## 9. Đóng gói thành JAR và chuẩn bị cho build tool

Sau khi biên dịch thành công, chạy tại thư mục gốc dự án:

```powershell
jar --create --file task-cli.jar --main-class vn.example.tasks.TaskApp -C out .

if ($LASTEXITCODE -ne 0) {
    throw 'Dong goi that bai.'
}

java -jar task-cli.jar
```

`--main-class` ghi lớp khởi chạy vào manifest. `-C out .` lấy nội dung bên trong `out`, nên đường dẫn lớp trong JAR bắt đầu bằng `vn/example/tasks`. Xem [tài liệu jar](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html).

Đối với ví dụ chỉ dùng API của JDK, JAR này chứa đủ các lớp ứng dụng. Khi thêm thư viện ngoài, quy trình build cần quản lý cả dependency và cách đưa chúng vào môi trường chạy.

Khi dự án có nhiều tệp hoặc cần quy trình tự động, hãy đưa các quyết định sau vào cấu hình build:

- Mức Java mục tiêu và JDK dùng để build.
- Gốc mã nguồn, mã kiểm thử và tài nguyên.
- Dependency cùng phiên bản tương ứng.
- Điểm khởi chạy và quy tắc đóng gói.
- Lệnh thống nhất để nhóm phát triển và CI cùng sử dụng.

Nếu chọn Maven, cần có `pom.xml` với cấu hình compiler và đóng gói phù hợp. Cây thư mục ở phần 7 là phần chuẩn bị cho cấu hình đó; các lệnh JDK trong bài đủ để chạy ví dụ độc lập.

## 10. Những lỗi dễ gặp trong quá trình chuyển đổi

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `List` sau khi thêm lớp bao ngoài | Tệp thông thường thiếu import | Thêm `import java.util.List;` trước lớp |
| Compiler báo lỗi với `package` trong tệp gọn | Chưa đưa thành viên vào lớp tường minh | Tạo lớp có tên trước, sau đó khai báo package |
| Báo lỗi gọi thành viên instance từ `static main` | Chỉ đổi chữ ký `main`, chưa tạo đối tượng | Tạo đối tượng hoặc chuyển việc gọi sang service như phần 6 |
| Instance `main` không khởi chạy sau khi thêm constructor có tham số | Không còn cách tạo đối tượng bằng constructor không tham số | Thiết kế constructor phù hợp hoặc dùng `static main` để nối dependency |
| `Could not find or load main class` | Classpath hoặc tên lớp chạy chưa đúng | Dùng `java -cp out vn.example.tasks.TaskApp` |
| Không truy cập được `TaskService` từ package mới | Kiểu hoặc thành viên vẫn có package access | Xác định API cần mở và sửa phạm vi truy cập liên quan |
| Báo `UnsupportedClassVersionError` | Runtime cũ hơn mức bytecode đã build | Dùng runtime hỗ trợ mức `--release` đã chọn |
| Kết quả vẫn giống mã cũ sau một lần build lỗi | Đang chạy các tệp `.class` còn từ lần trước | Chỉ chạy sau khi compiler thành công; đóng gói từ đầu ra build sạch |

Một điểm cần lưu ý riêng là **định danh kiểu thay đổi khi tách kiểu lồng**. Trong phiên bản lớp bao ngoài, kiểu là `TaskApp.Task`; trong dự án cuối cùng, kiểu là `vn.example.tasks.Task`. Nếu có mã khác đang tham chiếu kiểu cũ, cần cập nhật các tham chiếu đó. Đừng giữ đồng thời hai định nghĩa rồi trộn chúng trong cùng luồng dữ liệu.

Để việc chuyển đổi dễ theo dõi, có thể tiến hành theo thứ tự:

1. Ghi nhận đầu ra của ví dụ ban đầu.
2. Tạo lớp bao ngoài và bổ sung import.
3. Tách `Task` thành một kiểu riêng.
4. Đưa quy tắc lọc vào `TaskService`.
5. Đưa các tệp vào cùng package và đúng cây thư mục.
6. Cập nhật lệnh chạy, sau đó đóng gói từ kết quả biên dịch thành công.

## 11. Bài tập vận dụng

### Bài tập 1: thay dữ liệu mà giữ nguyên nghiệp vụ

Thay danh sách dữ liệu mẫu trong `TaskApp.main` và dự đoán kết quả:

| Đầu vào | Số công việc còn lại dự kiến |
| --- | --- |
| Danh sách rỗng | `0` |
| Hai công việc đều `done = true` | `0` |
| Hai công việc đều `done = false` | `2` |
| Một công việc hoàn thành, hai công việc chưa hoàn thành | `2` |

Những trường hợp này có thể trở thành kiểm thử cho `TaskService` trong `src/test/java/vn/example/tasks`. Kiểm thử cùng package có thể dùng trực tiếp các thành phần package access trong ví dụ.

### Bài tập 2: thêm cách hiển thị khác

Viết một lớp có tên `TaskSummary` trong cùng package, nhận kết quả từ `TaskService` và tạo chuỗi dạng `"2 công việc đang mở"`. Giữ quy tắc chọn công việc trong service.

Mục tiêu là có thêm một cách biểu diễn kết quả mà không sao chép điều kiện `!task.done()` vào nhiều nơi.

### Bài tập 3: chọn điểm vào phù hợp

So sánh hai phương án cho cùng chương trình:

- Một instance `main` trong lớp có constructor không tham số.
- Một `static main` tạo `TaskService` rồi chuyển nó cho lớp xử lý CLI qua constructor.

Giải thích đối tượng nào được tạo ở đâu và vì sao. Tiêu chí hoàn thành là bạn chỉ rõ được đường đi từ điểm khởi chạy đến nghiệp vụ, đồng thời có thể sử dụng service với dữ liệu riêng mà không cần chạy toàn bộ CLI.
