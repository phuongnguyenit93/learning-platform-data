# Tạo dự án Java 17 nhỏ, biên dịch và chạy bằng dòng lệnh

Khi học Java, bạn không cần một IDE để bắt đầu. Bộ công cụ trong JDK cho phép tạo mã nguồn, biên dịch thành bytecode, chạy chương trình, và đóng gói ứng dụng ngay trong terminal. Bài này xây dựng một ứng dụng **quản lý công việc trên dòng lệnh (Task CLI)** có thể thêm, xem và đánh dấu hoàn thành công việc, qua đó thực hành quy trình phát triển Java 17 từ đầu đến cuối.

Ứng dụng dùng **Java 17**, thư viện chuẩn của JDK và ba tệp mã nguồn. Không cần Maven, Gradle hay thư viện bên thứ ba. Quy trình sử dụng các lệnh `javac`, `java` và `jar` vẫn là nền tảng hữu ích khi làm việc với những phiên bản Java hiện đại.

## 1. Mục tiêu và điều kiện chuẩn bị

Sau khi hoàn thành, bạn có thể:

- Phân biệt **JDK**, **mã nguồn `.java`**, **bytecode `.class`** và **JVM**.
- Tạo cấu trúc dự án dùng `package` và tổ chức nhiều lớp Java.
- Biên dịch đúng phiên bản tương thích Java 17, chỉ định nơi lưu tệp `.class` và chạy lớp có `main`.
- Đọc thông báo lỗi thường gặp khi biên dịch/chạy từ terminal.
- Đóng gói các lớp đã biên dịch thành tệp JAR có điểm khởi chạy, sau đó dùng `java -jar`.

Bạn cần cài **JDK 17 hoặc JDK mới hơn có hỗ trợ tùy chọn `--release 17`**. Để thực hành sát với bài, nên dùng JDK 17. Mở terminal trong một thư mục bạn có quyền ghi và kiểm tra:

~~~text
java -version
javac -version
jar --version
~~~

Ví dụ khi dùng JDK 17, đầu ra của `java -version` và `javac -version` chứa số phiên bản `17`. Nhà phân phối JDK và số bản vá có thể khác nhau. Lệnh `java` khởi động JVM, `javac` biên dịch mã nguồn và `jar` tạo/đọc gói JAR. Nếu `java` chạy được nhưng `javac` không tồn tại, hãy kiểm tra việc cài **JDK đầy đủ** và cấu hình `PATH`.

### Chu trình từ mã nguồn đến chương trình chạy

~~~text
src/main/java/.../*.java
          |
          | javac --release 17 -d out ...
          v
out/.../*.class  (bytecode)
          |
          | java -cp out vn.example.taskcli.Main
          v
JVM chạy chương trình
          |
          | jar --create ... -C out .
          v
taskcli.jar       (gói có thể chạy bằng java -jar)
~~~

`javac` phát hiện lỗi cú pháp và kiểm tra kiểu khi biên dịch; JVM thực thi bytecode sau đó. Một ứng dụng Java không tự động biến thành tệp thực thi độc lập kiểu `.exe` chỉ vì được biên dịch; tệp `.class` và JAR vẫn cần môi trường Java tương thích để chạy.

## 2. Thiết kế dự án Task CLI

Ta tổ chức mã nguồn theo quy ước thư mục tương ứng với tên package. Dự án có cấu trúc như sau:

~~~text
task-cli/
├── src/
│   └── main/
│       └── java/
│           └── vn/
│               └── example/
│                   └── taskcli/
│                       ├── Main.java
│                       ├── Task.java
│                       └── TaskManager.java
├── out/                  (sinh ra khi biên dịch)
└── taskcli.jar           (sinh ra khi đóng gói)
~~~

Ba lớp chịu trách nhiệm rõ ràng:

| Thành phần | Vai trò |
|---|---|
| `Task` | Biểu diễn một công việc: mã số, tiêu đề, trạng thái hoàn thành. |
| `TaskManager` | Quản lý danh sách công việc trong bộ nhớ; cung cấp thao tác thêm, xem, hoàn thành. |
| `Main` | Đọc lệnh người dùng từ terminal, gọi `TaskManager` và in kết quả. |

**Lưu ý về phạm vi:** Dữ liệu của ví dụ được giữ trong bộ nhớ. Khi thoát chương trình rồi mở lại, danh sách công việc bắt đầu trống. Muốn lưu lâu dài, bạn sẽ cần bổ sung lưu trữ tệp hoặc cơ sở dữ liệu trong một bước phát triển tiếp theo.

### Tạo thư mục

Mở terminal, tạo thư mục dự án `task-cli` rồi chuyển vào thư mục đó. Tại **PowerShell trên Windows**:

~~~powershell
mkdir task-cli
cd task-cli
New-Item -ItemType Directory -Force -Path src/main/java/vn/example/taskcli | Out-Null
New-Item -ItemType Directory -Force -Path out | Out-Null
~~~

Tại **Bash/Zsh trên Linux hoặc macOS**:

~~~bash
mkdir task-cli
cd task-cli
mkdir -p src/main/java/vn/example/taskcli out
~~~

Các đường dẫn dùng dấu `/` trong ví dụ để thống nhất cách trình bày. Bạn có thể viết mã nguồn bằng bất kỳ trình soạn thảo văn bản nào, lưu thành ba tệp `.java` theo đúng vị trí bên dưới. Lưu tệp ở định dạng UTF-8.

## 3. Viết mã nguồn

### 3.1. Mô hình dữ liệu — `Task.java`

Tạo tệp `src/main/java/vn/example/taskcli/Task.java`:

~~~java
package vn.example.taskcli;

public record Task(int id, String title, boolean completed) {
    public Task {
        if (id <= 0) {
            throw new IllegalArgumentException("Task id must be positive");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Task title must not be blank");
        }
        title = title.strip();
    }

    public Task markCompleted() {
        return new Task(id, title, true);
    }
}
~~~

`record` là tính năng ổn định của Java 17, phù hợp để biểu diễn đối tượng dữ liệu đơn giản. Java tự tạo constructor chuẩn, các phương thức truy cập `id()`, `title()`, `completed()` cùng `equals()`, `hashCode()` và `toString()`. Phần `public Task { ... }` là *compact constructor*: kiểm tra dữ liệu và chuẩn hóa tiêu đề trước khi lưu.

Đối tượng `record` không thay đổi trạng thái sau khi tạo. Vì vậy, `markCompleted()` **trả về một `Task` mới** có `completed = true` thay vì sửa trực tiếp đối tượng cũ. Cách làm này giúp quản lý trạng thái có chủ đích.

### 3.2. Quản lý danh sách — `TaskManager.java`

Tạo tệp `src/main/java/vn/example/taskcli/TaskManager.java`:

~~~java
package vn.example.taskcli;

import java.util.ArrayList;
import java.util.List;

public final class TaskManager {
    private final List<Task> tasks = new ArrayList<>();
    private int nextId = 1;

    public Task add(String title) {
        Task task = new Task(nextId, title, false);
        tasks.add(task);
        nextId++;
        return task;
    }

    public List<Task> all() {
        return List.copyOf(tasks);
    }

    public boolean markCompleted(int id) {
        for (int i = 0; i < tasks.size(); i++) {
            Task current = tasks.get(i);
            if (current.id() == id) {
                tasks.set(i, current.markCompleted());
                return true;
            }
        }
        return false;
    }
}
~~~

`ArrayList` là danh sách có thể thêm và thay phần tử. `nextId` tạo mã số liên tiếp trong một lần chạy. `List.copyOf(tasks)` trả về danh sách không cho phép người gọi sửa trực tiếp, nhờ vậy mọi thay đổi đi qua các phương thức của `TaskManager`. Khi đánh dấu hoàn thành, chương trình tìm đúng mã số và thay `Task` cũ bằng một bản ghi mới.

Trong ứng dụng nhỏ này, tìm tuyến tính bằng vòng lặp là đủ dễ hiểu. Với dữ liệu lớn hoặc lưu trữ lâu dài, bạn có thể cân nhắc cấu trúc dữ liệu và cơ chế lưu trữ khác.

### 3.3. Giao diện dòng lệnh — `Main.java`

Tạo tệp `src/main/java/vn/example/taskcli/Main.java`:

~~~java
package vn.example.taskcli;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        TaskManager manager = new TaskManager();
        printHelp();

        try (Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8)) {
            boolean running = true;

            while (running) {
                System.out.print("task> ");
                System.out.flush();

                if (!scanner.hasNextLine()) {
                    break;
                }

                String line = scanner.nextLine().strip();
                if (line.isEmpty()) {
                    continue;
                }

                String[] parts = line.split("\\s+", 2);
                String command = parts[0].toLowerCase(Locale.ROOT);

                switch (command) {
                    case "add" -> {
                        if (parts.length < 2 || parts[1].isBlank()) {
                            System.out.println("Usage: add <title>");
                        } else {
                            Task task = manager.add(parts[1]);
                            System.out.printf(
                                    "Added #%d: %s%n", task.id(), task.title());
                        }
                    }
                    case "list" -> {
                        List<Task> tasks = manager.all();
                        if (tasks.isEmpty()) {
                            System.out.println("No tasks yet.");
                        } else {
                            for (Task task : tasks) {
                                String check = task.completed() ? "x" : " ";
                                System.out.printf(
                                        "[%s] #%d %s%n",
                                        check, task.id(), task.title());
                            }
                        }
                    }
                    case "done" -> {
                        if (parts.length < 2) {
                            System.out.println("Usage: done <id>");
                        } else {
                            try {
                                int id = Integer.parseInt(parts[1].strip());
                                if (manager.markCompleted(id)) {
                                    System.out.println("Completed #" + id);
                                } else {
                                    System.out.println("Task not found: #" + id);
                                }
                            } catch (NumberFormatException exception) {
                                System.out.println("Id must be an integer.");
                            }
                        }
                    }
                    case "help" -> printHelp();
                    case "exit" -> running = false;
                    default -> System.out.println(
                            "Unknown command. Type help for instructions.");
                }
            }
        }

        System.out.println("Goodbye!");
    }

    private static void printHelp() {
        System.out.println("Commands:");
        System.out.println("  add <title>  - create a task");
        System.out.println("  list         - show all tasks");
        System.out.println("  done <id>    - mark a task as completed");
        System.out.println("  help         - show commands");
        System.out.println("  exit         - quit");
    }
}
~~~

Các điểm đáng chú ý:

- `public static void main(String[] args)` là điểm bắt đầu chương trình khi chạy lớp `Main`. Tên package đầy đủ của lớp là `vn.example.taskcli.Main`.
- `Scanner` đọc các dòng từ `System.in`. `try (...)` đóng bộ đọc khi kết thúc; việc kiểm tra `hasNextLine()` cho phép thoát sạch khi người dùng gửi EOF.
- `String.strip()` loại bỏ khoảng trắng đầu/cuối. `split("\\s+", 2)` tách **tối đa hai phần**: tên lệnh và toàn bộ phần nội dung còn lại, nên tiêu đề công việc có thể chứa dấu cách.
- `switch` với nhánh `case "..." ->` là cú pháp ổn định trong Java 17. `Locale.ROOT` giúp chuẩn hóa tên lệnh nhất quán, không phụ thuộc ngôn ngữ hệ điều hành.
- `Integer.parseInt()` có thể ném `NumberFormatException` nếu người dùng nhập mã không phải số nguyên; chương trình bắt ngoại lệ và báo lỗi thay vì kết thúc đột ngột.
- `StandardCharsets.UTF_8` được chỉ định khi đọc đầu vào. Để nhập tiếng Việt trên Windows, terminal cũng cần cấu hình hỗ trợ UTF-8; lựa chọn font và mã hóa của terminal ảnh hưởng việc hiển thị ký tự.

Mã nguồn dùng chữ ASCII trong thông báo để dễ chạy giống nhau trên nhiều terminal; người dùng vẫn có thể đặt tiêu đề công việc bằng Unicode khi đầu vào terminal hỗ trợ UTF-8.

## 4. Biên dịch bằng `javac`

Đảm bảo terminal đang ở thư mục gốc `task-cli` (thư mục chứa `src` và `out`). Chạy lệnh **giống nhau trong PowerShell, Bash và Zsh**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/vn/example/taskcli/Task.java src/main/java/vn/example/taskcli/TaskManager.java src/main/java/vn/example/taskcli/Main.java
~~~

Nếu thành công, `javac` thường kết thúc mà **không in thông báo**. Kiểm tra thư mục kết quả:

~~~text
out/
└── vn/
    └── example/
        └── taskcli/
            ├── Main.class
            ├── Task.class
            └── TaskManager.class
~~~

Giải thích các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `javac` | Trình biên dịch Java được cung cấp trong JDK. |
| `--release 17` | Biên dịch cho API và phiên bản bytecode tương thích Java 17, kể cả khi dùng JDK mới hơn. |
| `-encoding UTF-8` | Đọc mã nguồn `.java` bằng UTF-8, tránh phụ thuộc mã hóa mặc định của máy. |
| `-d out` | Ghi các tệp `.class` vào thư mục `out`, tự tạo các thư mục con tương ứng với package. |
| Các đường dẫn `.java` | Liệt kê đầy đủ những tệp mã nguồn cần biên dịch. |

Danh sách tệp được ghi rõ thay vì dùng ký tự đại diện `*.java`; cách này có thể sao chép trực tiếp vào PowerShell và các shell phổ biến, vì quy tắc mở rộng wildcard cho lệnh ngoài không hoàn toàn giống nhau.

Tên thư mục sau `-d` phản ánh khai báo `package vn.example.taskcli;`. Bạn **không** cần tạo thủ công thư mục `out/vn/example/taskcli` trước khi biên dịch.

### Thử quan sát một lỗi biên dịch

Nếu cố tình đổi `task.title()` thành `task.unknownMethod()` trong `Main.java` rồi biên dịch lại, `javac` sẽ báo lỗi dạng `cannot find symbol` và chỉ vị trí dòng có phương thức không tồn tại. Trả mã nguồn về `task.title()` và biên dịch lại để tiếp tục.

Đây là lỗi ở **giai đoạn biên dịch**, chưa có lệnh nào được chạy trên JVM. Các lỗi nhập liệu như `done abc` ở phần sau lại được xử lý **khi chương trình đang chạy**.

## 5. Chạy bằng `java` và sử dụng ứng dụng

Sau khi biên dịch thành công:

~~~bash
java -cp out vn.example.taskcli.Main
~~~

Trong lệnh trên:

- `java` khởi động JVM.
- `-cp out` (viết đầy đủ là `--class-path out`) chỉ nơi JVM tìm lớp đã biên dịch. `out` chính là **class path root**, không phải thư mục `out/vn/example/taskcli`.
- `vn.example.taskcli.Main` là tên lớp đầy đủ (*fully qualified class name*). Khi chạy lớp từ classpath, không thêm đuôi `.class` và không viết thành đường dẫn tệp.

Bạn sẽ thấy danh sách lệnh và dấu nhắc `task>`. Một phiên thao tác ví dụ:

~~~text
Commands:
  add <title>  - create a task
  list         - show all tasks
  done <id>    - mark a task as completed
  help         - show commands
  exit         - quit
task> add Read chapter 1
Added #1: Read chapter 1
task> add Practice Java CLI
Added #2: Practice Java CLI
task> list
[ ] #1 Read chapter 1
[ ] #2 Practice Java CLI
task> done 1
Completed #1
task> list
[x] #1 Read chapter 1
[ ] #2 Practice Java CLI
task> done abc
Id must be an integer.
task> exit
Goodbye!
~~~

Ký hiệu `[ ]` thể hiện công việc chưa hoàn thành, còn `[x]` là đã hoàn thành. Lệnh `add` hỗ trợ tiêu đề nhiều từ. Lệnh `done` yêu cầu số nguyên; khi mã không tồn tại, chương trình in `Task not found`. Nhấn Enter ở dòng trống sẽ mở dấu nhắc kế tiếp; `exit` hoặc EOF kết thúc vòng đọc.

Khi vừa thay đổi mã nguồn `.java`, bạn cần chạy lại `javac ...` để tạo bytecode mới rồi mới chạy `java -cp ...`. Lệnh `java -cp` chạy các tệp `.class` hiện có; nó không tự biên dịch lại toàn bộ dự án nhiều lớp.

### Chạy thử với đầu vào có sẵn

Với chương trình đọc từ `System.in`, bạn có thể truyền chuỗi lệnh qua pipeline để quan sát đầu ra nhanh mà không phải gõ từng dòng.

PowerShell:

~~~powershell
@('add Read Java 17', 'add Build a CLI', 'list', 'done 1', 'list', 'exit') | java -cp out vn.example.taskcli.Main
~~~

Bash/Zsh:

~~~bash
printf 'add Read Java 17\nadd Build a CLI\nlist\ndone 1\nlist\nexit\n' | java -cp out vn.example.taskcli.Main
~~~

Hai cách trên dùng dữ liệu ASCII để tránh khác biệt cấu hình mã hóa đầu vào giữa các shell. Đây là bước chạy thử thủ công, phù hợp cho ví dụ đơn giản; khi ứng dụng mở rộng, bạn có thể viết kiểm thử tự động cho các lớp xử lý nghiệp vụ.

## 6. Đóng gói và chạy từ JAR

Khi đã có các tệp `.class` trong `out`, tạo một **JAR có khai báo lớp khởi chạy** bằng lệnh:

~~~bash
jar --create --file taskcli.jar --main-class vn.example.taskcli.Main -C out .
~~~

Ý nghĩa:

- `--create`: tạo JAR.
- `--file taskcli.jar`: ghi ra tệp có tên `taskcli.jar` tại thư mục hiện tại.
- `--main-class vn.example.taskcli.Main`: khai báo điểm bắt đầu trong manifest của JAR.
- `-C out .`: lấy nội dung **bên trong** thư mục `out` làm gốc của gói; đường dẫn các lớp trong JAR bắt đầu bằng `vn/example/taskcli/...`.

Chạy chương trình đã đóng gói:

~~~bash
java -jar taskcli.jar
~~~

Kết quả tương tự khi chạy bằng classpath. Tệp JAR này chứa bytecode của ba lớp và thông tin điểm chạy; đây **không phải** JAR bao gồm sẵn một JVM. Máy chạy vẫn cần runtime Java 17 hoặc phiên bản tương thích mới hơn. Vì dự án không dùng thư viện ngoài, JAR hiện tại đã chứa đủ lớp của chính ứng dụng; dự án có phụ thuộc bên ngoài sẽ cần chiến lược đóng gói/classpath phù hợp.

Có thể xem danh sách tệp trong gói bằng:

~~~bash
jar --list --file taskcli.jar
~~~

Bạn sẽ thấy các mục tương tự `META-INF/MANIFEST.MF` và `vn/example/taskcli/Main.class`. Nếu sửa mã nguồn, trình tự cập nhật JAR là **biên dịch lại `.class` → chạy lại lệnh `jar --create ...` → chạy `java -jar ...`**.

### Phân biệt các cách chạy phổ biến

| Cách chạy | Khi nào dùng | Điểm cần nhớ |
|---|---|---|
| `java -cp out vn.example.taskcli.Main` | Làm việc với mã đã biên dịch vào thư mục. | Chỉ định classpath root và tên lớp đầy đủ. |
| `java -jar taskcli.jar` | Chạy ứng dụng đóng gói có `Main-Class`. | JVM đọc điểm khởi chạy từ manifest của JAR. |
| `java Hello.java` | Chạy nhanh một chương trình mã nguồn đơn tệp được hỗ trợ. | Chế độ khởi chạy mã nguồn có từ Java 11; không thay thế cách tổ chức và biên dịch dự án nhiều tệp ở bài này. |

Ví dụ chế độ mã nguồn đơn tệp (độc lập với Task CLI), tạo `Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java 17!");
    }
}
~~~

Rồi chạy `java Hello.java`. Đây là tính năng hiện hành hữu ích cho ví dụ ngắn; với dự án Task CLI gồm nhiều lớp, quy trình `javac` + `java -cp` giúp bạn nắm rõ bytecode, package và classpath.

## 7. Các lỗi thường gặp khi thao tác từ terminal

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
|---|---|---|
| `javac` không được nhận diện | Chưa cài JDK hoặc thư mục `bin` của JDK chưa có trong `PATH`. | Kiểm tra `javac -version`; cấu hình JDK đầy đủ và mở terminal mới. |
| `error: file not found` | Chạy sai thư mục hoặc đường dẫn/tên tệp nguồn sai. | Vào thư mục `task-cli`, kiểm tra đúng đường dẫn `src/main/java/...`. |
| `cannot find symbol` | Sai tên lớp/phương thức, thiếu import hoặc chưa đưa tệp cần thiết vào lệnh biên dịch. | Đọc tên ký hiệu và số dòng được báo; biên dịch đủ ba tệp ở ví dụ. |
| `Could not find or load main class ...` | Classpath root hoặc tên package/lớp không đúng; thiếu tệp `.class`. | Kiểm tra `out/vn/example/taskcli/Main.class` và chạy `java -cp out vn.example.taskcli.Main`. |
| `UnsupportedClassVersionError` | Runtime quá cũ so với bytecode đã biên dịch. | Kiểm tra cả `java -version` và `javac -version`; sử dụng runtime Java 17+ và tùy chọn `--release 17` khi biên dịch. |
| `no main manifest attribute` khi chạy `java -jar` | JAR chưa khai báo `Main-Class`. | Tạo lại với `jar --create --file taskcli.jar --main-class vn.example.taskcli.Main -C out .`. |
| Tiếng Việt hiển thị sai | Mã hóa tệp nguồn, đầu vào hoặc terminal không thống nhất. | Lưu tệp UTF-8, biên dịch bằng `-encoding UTF-8` và chỉnh terminal về UTF-8. |
| Sửa mã nhưng chạy vẫn ra kết quả cũ | Đang chạy bytecode hoặc JAR tạo trước khi sửa. | Biên dịch lại, đóng gói lại nếu dùng JAR, và chạy đúng đầu ra mới. |

Đối với lỗi liên quan package, hãy nhớ ba thành phần phải khớp nhau: **khai báo `package` → đường dẫn lớp bên trong `out` → tên lớp đầy đủ khi chạy**. Chẳng hạn `package vn.example.taskcli;` dẫn đến `out/vn/example/taskcli/Main.class` và lệnh `java -cp out vn.example.taskcli.Main`.

Không cần tự thêm các API `sun.*` hoặc phụ thuộc vào cơ chế nội bộ của JDK để xử lý những lỗi trên. Ví dụ này chỉ dùng API công khai, ổn định của Java 17.

## 8. Phát triển thêm từ dự án nhỏ

Khi chương trình cơ bản đã hoạt động, bạn có thể luyện thêm theo thứ tự:

1. Thêm lệnh `remove <id>` để xóa công việc và xử lý trường hợp mã không tồn tại.
2. Thêm `list pending` / `list done` để lọc trạng thái; cân nhắc dùng `Stream` hoặc vòng lặp rõ ràng.
3. Viết kiểm thử đơn vị cho `TaskManager`: thêm công việc, mã số tăng, đánh dấu hoàn thành, không tìm thấy mã. Có thể tích hợp JUnit bằng công cụ build khi học đến quản lý dependency.
4. Lưu công việc ra tệp văn bản hoặc JSON theo một định dạng xác định, rồi đọc lại ở lần chạy sau. Hãy xử lý lỗi đọc/ghi tệp và cân nhắc mã hóa UTF-8.
5. Khi dự án có nhiều tệp và thư viện, chuyển sang Maven hoặc Gradle để tự động hóa biên dịch, kiểm thử và đóng gói. Kiến thức về `javac`, `java`, package và classpath vẫn là nền tảng để hiểu công cụ build thực hiện điều gì.

**Tự kiểm tra kiến thức:** Tại sao phải dùng `-cp out` thay vì `-cp out/vn/example/taskcli`? Nếu biên dịch bằng JDK mới hơn nhưng cần chạy trên Java 17, tùy chọn nào cần giữ? Vì sao `java -jar taskcli.jar` không cần truyền tên lớp `Main`? Khi thay đổi `TaskManager.java`, các bước nào phải chạy lại để JAR chứa mã mới?

Bạn đã đi hết một vòng phát triển thực tế: tạo dự án → viết nhiều lớp có package → biên dịch ra bytecode tương thích Java 17 → chạy bằng JVM → đóng gói và chạy JAR. Có thể áp dụng cùng quy trình cho những ứng dụng dòng lệnh nhỏ khác trước khi sử dụng IDE hay công cụ build.
