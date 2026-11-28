# Xây dựng công cụ dòng lệnh với tệp nguồn gọn, IO và instance main

## 1. Mục tiêu bài thực hành

Một công cụ dòng lệnh nhỏ thường cần nhận tham số từ shell, hỏi dữ liệu người dùng, hiển thị kết quả và lưu trạng thái vào file. Trước Java 25, ngay cả chương trình một file cũng thường bắt đầu bằng khai báo class và phương thức `public static void main(String[] args)`. Cách viết đó vẫn đúng, nhưng với một tiện ích nhỏ, phần khung có thể che khuất luồng xử lý chính.

Java 25 hoàn thiện **Compact Source Files and Instance Main Methods** qua **JEP 512**. Tính năng này cho phép viết các field và method ở cấp cao nhất của file mà không cần tự khai báo class. Launcher cũng có thể gọi một phương thức `main` dạng instance, không bắt buộc `public static` và có thể bỏ `String[]` nếu chương trình không cần đối số.

Bài thực hành xây dựng một tiện ích quản lý việc cần làm tên **TaskCli**. Chương trình có thể:

- Thêm một việc mới.
- Liệt kê các việc đã lưu và trạng thái hoàn thành.
- Đánh dấu một việc hoàn thành.
- Xóa một việc theo số thứ tự.
- Chạy ở chế độ tương tác bằng `java.lang.IO`.
- Lưu dữ liệu trong file UTF-8 bằng `Path` và `Files`.

Qua bài này, người học thực hành kết hợp ba phần của Java 25:

1. **Compact source file:** viết field, record và method mà không bao một class tường minh.
2. **Instance main:** dùng trạng thái instance và method instance ngay trong chương trình entry point.
3. **Console và file I/O:** dùng `IO.readln`/`IO.println` cho terminal và `Files`/`Path` cho dữ liệu lưu trữ.

## 2. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Nhận biết compact source file và lớp được khai báo ngầm.
- Giải thích cách launcher tìm và gọi instance `main`.
- Dùng `String[] args` để xây CLI có subcommand.
- Dùng `java.lang.IO` để đọc từng dòng và hiển thị prompt.
- Phân biệt console I/O với file I/O.
- Đọc/ghi file có chỉ định UTF-8 rõ ràng.
- Thiết kế định dạng lưu dữ liệu nhiều dòng và xử lý dữ liệu lỗi.
- Chạy source file trực tiếp hoặc biên dịch trước bằng `javac`.
- Nhận biết khi nào tiện ích đã lớn đến mức nên chuyển sang class/package thông thường.

## 3. JEP 512 là tính năng final trong Java 25

**Compact Source Files and Instance Main Methods** đã trải qua các vòng preview trước khi trở thành tính năng chính thức:

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| JDK 21 | JEP 445 | Preview lần đầu |
| JDK 22 | JEP 463 | Preview lần hai |
| JDK 23 | JEP 477 | Preview lần ba |
| JDK 24 | JEP 495 | Preview lần bốn |
| **JDK 25** | **JEP 512** | **Final, không còn preview** |

Vì vậy, ví dụ trong bài chạy trên JDK 25 mà không cần `--enable-preview`. Đây là điểm khác với các hướng dẫn Java 21–24 cũ: những ví dụ đó có thể dùng tên hoặc cú pháp của vòng preview trước và không nên lấy làm mẫu cho Java 25.

## 4. Compact source file là gì?

Một compact source file là file Java có các khai báo như field, method hoặc member type không nằm bên trong một khai báo class tường minh. Compiler hiểu các khai báo này là thành viên của một **implicitly declared class** (lớp được khai báo ngầm).

Ví dụ chương trình tối giản:

~~~java
void main() {
    IO.println("Xin chào Java 25!");
}
~~~

Lưu nội dung trên trong file `Hello.java` rồi chạy:

~~~bash
java Hello.java
~~~

Không có khai báo `class`, không có từ khóa `static`, không cần `public` và không cần `String[] args`. Compiler vẫn tạo một class để JVM thực thi; cú pháp gọn chỉ giúp người viết không phải khai báo class đó bằng tay.

### Những đặc điểm của lớp được khai báo ngầm

Theo quy tắc Java 25, lớp này:

- Là top-level class `final`.
- Nằm trong unnamed package và unnamed module.
- Kế thừa `java.lang.Object`, không triển khai interface nào.
- Có default constructor không tham số.
- Có các field, method và member type được khai báo trong compact source file.
- Phải có ít nhất một launchable `main` method.
- Không thể được tham chiếu bằng tên class từ source code; tên class file do compiler chọn là chi tiết triển khai.

Compact source file không phải một ngôn ngữ Java riêng. Các quy tắc về kiểu dữ liệu, biểu thức, vòng lặp, exception, record, collection và method vẫn là Java.

## 5. Field và method ở cấp cao nhất được hiểu như thế nào?

Trong compact source file, field và method không có class bao quanh vẫn là thành viên của lớp ngầm:

~~~java
String greeting = "Chào bạn";

String message(String name) {
    return greeting + ", " + name + "!";
}

void main(String[] args) {
    IO.println(message(args.length == 0 ? "Java" : args[0]));
}
~~~

Field `greeting` là instance field theo mặc định. Method `message` là instance method theo mặc định. Phương thức `main` có thể gọi trực tiếp `message` và đọc `greeting` trên cùng object.

Bạn vẫn có thể khai báo `static` khi có lý do, nhưng không cần biến mọi method thành static chỉ vì điểm vào chương trình trước đây phải là static.

### Giới hạn cần nhớ

Compact source file không cho phép khai báo tường minh:

- `package`.
- Class bao ngoài.
- Constructor của lớp ngầm.
- Instance initializer hoặc static initializer của lớp ngầm.

Lớp ngầm chỉ có default constructor không tham số. Các field có thể có initializer; điều này khác với việc tự khai báo một initializer block.

Do lớp ngầm nằm trong unnamed package và không thể tham chiếu bằng tên từ source code, compact source file phù hợp với chương trình độc lập, tiện ích nhỏ hoặc bài thực hành. Nó không phải cách tạo một API thư viện để các package khác import và sử dụng.

## 6. Instance main method hoạt động ra sao?

Trong Java 25, launcher nhận diện một `main` method có:

- Tên `main`.
- Kiểu trả về `void`.
- Một trong hai dạng tham số: không có tham số hoặc một tham số `String[]`.
- Mức truy cập cho phép launcher gọi: `public`, `protected` hoặc package access.
- Có thể là instance method hoặc static method.

Các ví dụ hợp lệ:

~~~java
void main() {
    IO.println("Không nhận command-line arguments");
}
~~~

~~~java
void main(String[] args) {
    IO.println("Có " + args.length + " đối số");
}
~~~

~~~java
public static void main(String[] args) {
    IO.println("Dạng static truyền thống vẫn hợp lệ");
}
~~~

Với instance `main`, launcher tạo instance của lớp entry point bằng default constructor rồi gọi method đó. Trong compact source file, compiler cung cấp default constructor cho lớp ngầm.

Nếu file có nhiều candidate `main`, launcher ưu tiên dạng có `String[]` trước dạng không tham số. Với chương trình CLI, dùng `void main(String[] args)` để nhận subcommand và đối số từ shell.

**Instance main không chỉ dành cho compact source file.** Một class được khai báo bình thường cũng có thể có instance `main`, miễn thỏa quy tắc launchable main và có constructor không tham số phù hợp để launcher tạo instance.

## 7. `java.lang.IO` dùng cho console I/O

Java 25 bổ sung `java.lang.IO` để thực hiện các thao tác console theo dòng:

| Method | Công dụng |
| --- | --- |
| `IO.print(Object)` | In giá trị, không tự xuống dòng. |
| `IO.println(Object)` | In giá trị và xuống dòng. |
| `IO.println()` | In dòng trống. |
| `IO.readln()` | Đọc một dòng từ standard input. |
| `IO.readln(String prompt)` | In prompt rồi đọc một dòng. |

Ví dụ:

~~~java
void main() {
    String name = IO.readln("Tên của bạn: ");
    if (name == null) {
        IO.println("Không có dữ liệu đầu vào.");
        return;
    }
    IO.println("Xin chào, " + name + "!");
}
~~~

`readln` trả về `null` khi gặp end-of-stream mà không còn ký tự nào để trả về. Vì vậy, chương trình tương tác nên kiểm tra `null` thay vì mặc định luôn có input.

### IO không phải là file API

`java.lang.IO` đọc từ standard input và ghi ra standard output. Nó không mở file, không tạo thư mục và không lưu dữ liệu lâu dài.

Không trộn `IO.readln()` với các cách đọc khác từ `System.in` trong cùng chương trình. API có thể buffer thêm byte sau phần văn bản đã trả về; tài liệu Java 25 nêu việc dùng tiếp `System.in` sau khi đã gọi `IO.readln` có hành vi không được xác định.

Trong bài này, console chỉ dùng `IO.readln` và `IO.println`; file dùng `Files`.

## 8. `java.base` được import tự động trong compact source file

Compact source file tự động import on-demand các public top-level class và interface trong những package được export bởi module `java.base`. Có thể hiểu như thể file có:

~~~java
import module java.base;
~~~

được thêm ngầm.

Vì vậy, compact source file có thể dùng trực tiếp các kiểu phổ biến như:

- `String`, `Integer`, `System`.
- `List`, `ArrayList`, `Map`.
- `Path`, `Files`, `StandardCharsets`.
- `IOException`, `Base64`.

Trong TaskCli bên dưới, các kiểu trên được dùng mà không cần import từng package.

Giới hạn: tự động import chỉ áp dụng cho module `java.base`, không phải mọi module của JDK. Ví dụ `java.sql` hoặc module thư viện ngoài không tự động có mặt. Khi dùng package ngoài `java.base`, cần import type/package hoặc dùng module import declaration phù hợp và bảo đảm module đó có trong runtime.

`IO` nằm trong `java.lang`, nên tên class có thể được tham chiếu trực tiếp. Tuy nhiên, các method static của `IO` **không được static-import tự động**; gọi `IO.println(...)` và `IO.readln(...)`, không gọi trần `println(...)` hay `readln(...)`.

## 9. Thiết kế công cụ TaskCli

Ta xây một danh sách việc cần làm đơn giản. Mỗi task có hai thuộc tính:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `done` | `boolean` | Task đã hoàn thành hay chưa. |
| `description` | `String` | Nội dung công việc. |

Dữ liệu được lưu trong file `.java25-tasks.txt` ở thư mục home của người dùng. Mỗi task chiếm một dòng theo cấu trúc:

~~~text
0:<Base64 URL-safe của description UTF-8>
1:<Base64 URL-safe của description UTF-8>
~~~

`0` là chưa hoàn thành, `1` là đã hoàn thành. Phần mô tả được mã hóa Base64 URL-safe để nội dung có dấu tiếng Việt, dấu hai chấm hoặc ký tự xuống dòng không làm hỏng cấu trúc một task mỗi dòng.

Đây là định dạng lưu trữ nhỏ phục vụ bài tập. Nó không mã hóa bí mật và không thay thế database. Người dùng có quyền đọc file vẫn có thể Base64 decode nội dung.

## 10. Hoàn thiện chương trình TaskCli.java

Tạo file `TaskCli.java` với toàn bộ nội dung sau. Đây là **compact source file**: không có `package`, không có class bao ngoài và không có import declaration. Các method/field nằm ở cấp cao nhất sẽ trở thành thành viên của lớp được khai báo ngầm.

~~~java
record Task(boolean done, String description) {}

private final Path dataFile =
        Path.of(System.getProperty("user.home"), ".java25-tasks.txt");

void main(String[] args) {
    try {
        run(args);
    } catch (IOException | IllegalArgumentException e) {
        IO.println("Lỗi: " + e.getMessage());
        showHelp();
    }
}

void run(String[] args) throws IOException {
    if (args.length == 0) {
        interactive();
        return;
    }

    switch (args[0]) {
        case "add" -> {
            requireArgCount(args, 2);
            addTask(args[1]);
        }
        case "list" -> {
            requireArgCount(args, 1);
            listTasks();
        }
        case "done" -> {
            requireArgCount(args, 2);
            markDone(parseIndex(args[1]));
        }
        case "remove" -> {
            requireArgCount(args, 2);
            removeTask(parseIndex(args[1]));
        }
        case "path" -> {
            requireArgCount(args, 1);
            IO.println(dataFile.toAbsolutePath());
        }
        case "help" -> showHelp();
        default -> throw new IllegalArgumentException(
                "Lệnh không hợp lệ: " + args[0]);
    }
}

void interactive() throws IOException {
    IO.println("TaskCli - gõ help để xem lệnh, quit để thoát.");

    while (true) {
        String line = IO.readln("tasks> ");
        if (line == null) {
            IO.println();
            return;
        }

        String trimmed = line.strip();
        if (trimmed.isEmpty()) {
            continue;
        }

        String[] parts = trimmed.split("\\s+", 2);
        String command = parts[0].toLowerCase(Locale.ROOT);

        try {
            switch (command) {
                case "add" -> {
                    requirePartCount(parts, 2);
                    addTask(parts[1]);
                }
                case "list" -> {
                    requirePartCount(parts, 1);
                    listTasks();
                }
                case "done" -> {
                    requirePartCount(parts, 2);
                    markDone(parseIndex(parts[1]));
                }
                case "remove" -> {
                    requirePartCount(parts, 2);
                    removeTask(parseIndex(parts[1]));
                }
                case "path" -> IO.println(dataFile.toAbsolutePath());
                case "help" -> showHelp();
                case "quit", "exit" -> {
                    return;
                }
                default -> IO.println("Không hiểu lệnh. Gõ help để xem trợ giúp.");
            }
        } catch (IllegalArgumentException e) {
            IO.println("Lỗi: " + e.getMessage());
        }
    }
}

void addTask(String description) throws IOException {
    String text = description.strip();
    if (text.isEmpty()) {
        throw new IllegalArgumentException("Nội dung task không được để trống.");
    }

    List<Task> tasks = loadTasks();
    tasks.add(new Task(false, text));
    saveTasks(tasks);
    IO.println("Đã thêm: " + text);
}

void listTasks() throws IOException {
    List<Task> tasks = loadTasks();
    if (tasks.isEmpty()) {
        IO.println("Danh sách đang trống.");
        return;
    }

    for (int i = 0; i < tasks.size(); i++) {
        Task task = tasks.get(i);
        String mark = task.done() ? "[x]" : "[ ]";
        IO.println((i + 1) + ". " + mark + " " + task.description());
    }
}

void markDone(int oneBasedIndex) throws IOException {
    List<Task> tasks = loadTasks();
    int index = checkedIndex(oneBasedIndex, tasks);
    Task current = tasks.get(index);

    if (current.done()) {
        IO.println("Task đã được đánh dấu hoàn thành.");
        return;
    }

    tasks.set(index, new Task(true, current.description()));
    saveTasks(tasks);
    IO.println("Đã hoàn thành task " + oneBasedIndex + ".");
}

void removeTask(int oneBasedIndex) throws IOException {
    List<Task> tasks = loadTasks();
    int index = checkedIndex(oneBasedIndex, tasks);
    Task removed = tasks.remove(index);
    saveTasks(tasks);
    IO.println("Đã xóa: " + removed.description());
}

List<Task> loadTasks() throws IOException {
    if (Files.notExists(dataFile)) {
        return new ArrayList<>();
    }

    List<Task> tasks = new ArrayList<>();
    for (String line : Files.readAllLines(dataFile, StandardCharsets.UTF_8)) {
        tasks.add(decodeTask(line));
    }
    return tasks;
}

void saveTasks(List<Task> tasks) throws IOException {
    List<String> lines = new ArrayList<>();
    for (Task task : tasks) {
        lines.add(encodeTask(task));
    }

    Files.write(
            dataFile,
            lines,
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
            StandardOpenOption.WRITE);
}

String encodeTask(Task task) {
    String encoded = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(task.description().getBytes(StandardCharsets.UTF_8));
    return (task.done() ? "1:" : "0:") + encoded;
}

Task decodeTask(String line) throws IOException {
    if (line.length() < 2
            || line.charAt(1) != ':'
            || (line.charAt(0) != '0' && line.charAt(0) != '1')) {
        throw new IOException("Dòng dữ liệu task không đúng định dạng.");
    }

    byte[] bytes;
    try {
        bytes = Base64.getUrlDecoder().decode(line.substring(2));
    } catch (IllegalArgumentException e) {
        throw new IOException("Task có Base64 không hợp lệ.", e);
    }

    String description = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();

    if (description.isBlank()) {
        throw new IOException("Task có nội dung rỗng.");
    }

    return new Task(line.charAt(0) == '1', description);
}

int parseIndex(String value) {
    try {
        int index = Integer.parseInt(value);
        if (index < 1) {
            throw new IllegalArgumentException("Số thứ tự phải bắt đầu từ 1.");
        }
        return index;
    } catch (NumberFormatException e) {
        throw new IllegalArgumentException("Số thứ tự phải là số nguyên.", e);
    }
}

int checkedIndex(int oneBasedIndex, List<Task> tasks) {
    if (oneBasedIndex < 1 || oneBasedIndex > tasks.size()) {
        throw new IllegalArgumentException("Không có task số " + oneBasedIndex + ".");
    }
    return oneBasedIndex - 1;
}

void requireArgCount(String[] args, int expected) {
    if (args.length != expected) {
        throw new IllegalArgumentException("Số lượng đối số không đúng.");
    }
}

void requirePartCount(String[] parts, int expected) {
    if (parts.length != expected) {
        throw new IllegalArgumentException("Thiếu hoặc thừa tham số cho lệnh.");
    }
}

void showHelp() {
    IO.println("Cách dùng:");
    IO.println("  java TaskCli.java add \"Nội dung công việc\"");
    IO.println("  java TaskCli.java list");
    IO.println("  java TaskCli.java done <số-thứ-tự>");
    IO.println("  java TaskCli.java remove <số-thứ-tự>");
    IO.println("  java TaskCli.java path");
    IO.println("  java TaskCli.java");
}
~~~

### Đọc cấu trúc của chương trình

| Thành phần | Vai trò |
| --- | --- |
| `record Task(...)` | Kiểu dữ liệu lưu trạng thái và nội dung task. |
| `dataFile` | Instance field giữ vị trí file dữ liệu. |
| `void main(String[] args)` | Instance main nhận subcommand từ launcher. |
| `run(...)` | Điều phối lệnh chạy từ command line. |
| `interactive()` | Vòng lặp console dùng `IO.readln`. |
| `loadTasks()` / `saveTasks()` | Đọc/ghi file bằng `Files`. |
| `encodeTask()` / `decodeTask()` | Chuyển task giữa object và định dạng một dòng. |
| `parseIndex()` / `checkedIndex()` | Kiểm tra đầu vào và số thứ tự. |

### Vì sao `record Task` có thể đặt ở đây?

Compact source file cho phép khai báo member type ở cấp cao nhất. `Task` trở thành member type của lớp ngầm, không phải một top-level class độc lập trong package. Record tự sinh constructor và accessor; giới hạn không khai báo constructor áp dụng cho lớp ngầm, không cấm constructor do compiler tạo cho record member.

## 11. Chạy chương trình trực tiếp bằng source-file mode

Đặt terminal tại thư mục chứa `TaskCli.java`, sau đó chạy:

~~~bash
# Thêm task
java --source 25 TaskCli.java add "Ôn tập compact source files"

# Thêm task có dấu tiếng Việt
java --source 25 TaskCli.java add "Thực hành đọc ghi file UTF-8"

# Xem danh sách
java --source 25 TaskCli.java list

# Đánh dấu task số 1 hoàn thành
java --source 25 TaskCli.java done 1

# Xóa task số 2
java --source 25 TaskCli.java remove 2

# Xem vị trí file dữ liệu
java --source 25 TaskCli.java path
~~~

Nếu không truyền command-line arguments, chương trình vào chế độ tương tác:

~~~bash
java --source 25 TaskCli.java
~~~

Sau đó nhập:

~~~text
tasks> add Chuẩn bị bài thuyết trình
tasks> add Kiểm tra ví dụ Java 25
tasks> list
tasks> done 1
tasks> list
tasks> quit
~~~

Trong source-file mode, launcher biên dịch source rồi chạy chương trình. Các đối số xuất hiện sau tên file được chuyển vào `main(String[] args)`. Tùy chọn `--source 25` khóa source/API level của chương trình ở Java 25; khi chạy trên JDK 25, có thể bỏ tùy chọn này nếu file `.java` đã đủ để launcher chọn source-file mode.

Không cần `--enable-preview`, vì JEP 512 đã final trong Java 25.

### Source-file mode không đồng nghĩa với compact source file

- Source-file mode là cách launcher \`java\` biên dịch và chạy một file source trực tiếp; file đó có thể chứa class thông thường.
- Compact source file là cú pháp ngôn ngữ cho phép khai báo thành viên mà không viết class bao ngoài.

Một file class truyền thống cũng chạy được bằng \`java SomeClass.java\`. Ngược lại, compact source file có thể được biên dịch trước bằng \`javac\` rồi chạy class file được tạo ra.

## 12. Chạy với javac sau khi biên dịch

Compact source file cũng có thể biên dịch trước như file Java thông thường:

~~~bash
javac --release 25 -d out TaskCli.java
~~~

Sau đó chạy class do compiler tạo:

~~~bash
java -cp out TaskCli add "Viết báo cáo"
java -cp out TaskCli list
~~~

Trong cách này, compiler thường dùng basename của file làm tên class entry point. Tên class đó là chi tiết triển khai của lớp ngầm; không dùng tên đó để tham chiếu class trong source code khác.

Khi cần đóng gói ứng dụng thành JAR, hãy cân nhắc chuyển sang class tường minh có package và entry point ổn định. Điều này giúp manifest, API, test và công cụ build có tên class rõ ràng.

## 13. Phân tích luồng command-line arguments

Launcher chuyển mọi đối số sau source file hoặc tên class thành phần tử của `String[] args`.

Ví dụ:

~~~bash
java TaskCli.java add "Hoàn thiện bài tập Java"
~~~

Mảng `args` có nội dung:

| Index | Giá trị |
| ---: | --- |
| `args[0]` | `add` |
| `args[1]` | `Hoàn thiện bài tập Java` |

Shell xử lý dấu nháy trước khi chuyển đối số cho JVM. Nếu bỏ dấu nháy, cụm từ có dấu cách có thể bị tách thành nhiều đối số. Bởi vậy TaskCli yêu cầu mô tả task nằm trong một đối số được quote.

`String[] args` là input từ người gọi, không phải nơi lưu trạng thái ứng dụng. Mỗi lần chạy command mới, JVM khởi tạo chương trình mới; dữ liệu giữa các lần chạy được giữ trong file.

## 14. Phân biệt console I/O và file I/O

Hai loại I/O trong bài có trách nhiệm riêng:

| Nhu cầu | API | Nguồn/đích |
| --- | --- | --- |
| Hiển thị prompt | `IO.readln(String)` | Standard output và standard input |
| Đọc lệnh tương tác | `IO.readln()` | Standard input |
| Hiển thị danh sách | `IO.println(...)` | Standard output |
| Tạo đường dẫn file | `Path.of(...)` | Mô tả vị trí file |
| Kiểm tra file | `Files.notExists(...)` | File system |
| Đọc dữ liệu task | `Files.readAllLines(...)` | File system |
| Ghi dữ liệu task | `Files.write(...)` | File system |

Không dùng `IO.readln()` để đọc file và không dùng `Files.readAllLines()` để đọc bàn phím. Chọn API đúng theo nguồn/đích dữ liệu giúp code rõ ràng và dễ kiểm thử.

## 15. Vì sao chỉ định UTF-8 cho file?

Task có thể chứa tiếng Việt, emoji hoặc ký tự ngoài ASCII. Vì vậy, khi đổi String thành byte và ngược lại, chương trình phải dùng cùng charset.

Trong code:

~~~java
task.description().getBytes(StandardCharsets.UTF_8);
Files.readAllLines(dataFile, StandardCharsets.UTF_8);
Files.write(dataFile, lines, StandardCharsets.UTF_8, options);
~~~

JDK 18 trở lên đã dùng UTF-8 làm default charset trên mọi nền tảng, nhưng chỉ định charset tường minh vẫn là thói quen tốt cho định dạng file và giao thức. Nó ghi rõ hợp đồng dữ liệu, không phụ thuộc môi trường chạy hoặc thay đổi cấu hình.

Với console, `IO.readln` sử dụng charset theo system property `stdin.encoding`; nếu property không có hoặc không nạp được charset, UTF-8 được dùng. Điều này tách biệt với charset mà TaskCli chọn cho file.

## 16. Vì sao dùng Base64 URL-safe cho nội dung task?

Nếu lưu trực tiếp mỗi task trên một dòng:

~~~text
Học Java
Đọc tài liệu
Hoàn thành bài tập
~~~

thì nội dung có ký tự xuống dòng sẽ phá cấu trúc. Nếu thêm trạng thái vào đầu dòng như `[x]`, nội dung task có thể gây nhầm lẫn khi parse.

TaskCli mã hóa UTF-8 bytes bằng Base64 URL-safe và thêm một byte trạng thái dạng ký tự:

~~~text
0:SG9jIEphdmE
1:SG9hbiB0aGFuaCBiYWk
~~~

Ưu điểm:

- Mỗi task luôn nằm trên một dòng.
- Nội dung tiếng Việt được giữ nguyên qua UTF-8.
- Dấu phân cách `:` chỉ xuất hiện ở vị trí trạng thái.
- Base64 URL-safe không dùng ký tự xuống dòng hoặc dấu phân cách của file.

Base64 chỉ là encoding, không phải encryption. Không dùng file này để lưu mật khẩu, token hoặc private key.

## 17. Kiểm tra dữ liệu và xử lý lỗi

Một CLI tốt cần xử lý các đầu vào không hợp lệ:

| Tình huống | Kiểm tra trong TaskCli |
| --- | --- |
| Không truyền nội dung task | `description.isBlank()` |
| Nhập số thứ tự không phải số nguyên | `Integer.parseInt` và bắt `NumberFormatException` |
| Nhập số thứ tự nhỏ hơn 1 | `parseIndex` |
| Nhập số task không tồn tại | `checkedIndex` |
| File chưa tồn tại | `Files.notExists` trả về true, dùng danh sách rỗng |
| File có status hoặc delimiter sai | `decodeTask` ném `IOException` |
| Base64 bị hỏng | `Base64.getUrlDecoder()` ném `IllegalArgumentException` và được chuyển thành `IOException` |
| Byte UTF-8 lỗi | `CharsetDecoder` dùng `CodingErrorAction.REPORT` |

Không nên âm thầm bỏ qua dòng dữ liệu hỏng. Nếu ứng dụng bỏ qua dữ liệu sai mà vẫn ghi lại file, người dùng có thể mất dữ liệu mà không biết. TaskCli dừng với lỗi để người dùng kiểm tra file.

### Vì sao decode UTF-8 có `REPORT`?

`new String(bytes, UTF_8)` có thể thay thế byte UTF-8 sai bằng ký tự replacement. Với file dữ liệu có định dạng, điều đó có thể che giấu lỗi hỏng dữ liệu. `CharsetDecoder` kết hợp `CodingErrorAction.REPORT` khiến lỗi được thể hiện thành `CharacterCodingException`, sau đó được xử lý như một lỗi I/O.

## 18. Các giới hạn của phiên bản TaskCli

Đây là công cụ thực hành nhỏ, có một số giới hạn có chủ đích:

- `Files.readAllLines` nạp toàn bộ file vào bộ nhớ; phù hợp với danh sách nhỏ, không phù hợp hàng triệu bản ghi.
- Mỗi thay đổi ghi lại toàn bộ file; phù hợp dữ liệu ít, không phù hợp cập nhật đồng thời từ nhiều tiến trình.
- Chưa dùng file lock hoặc atomic replacement; hai lệnh chạy cùng lúc có thể ghi đè thay đổi của nhau.
- File lưu trong home directory và không được mã hóa.
- Chương trình không có database, transaction hoặc backup.
- Compact source file nằm trong unnamed package, không phải cấu trúc lý tưởng cho ứng dụng nhiều module hoặc API tái sử dụng.

Khi mở rộng, có thể chuyển phần lưu trữ sang SQLite/JDBC, thêm file lock hoặc ghi qua temporary file rồi atomic move. Khi ứng dụng có nhiều domain type, package và module, hãy chuyển sang class tường minh và tách trách nhiệm thành các lớp service/repository.

## 19. Khi nào nên chuyển compact source file thành class thông thường?

Compact source file hữu ích khi chương trình nhỏ, độc lập và chưa cần API công khai. Khi chương trình phát triển, một số dấu hiệu cho thấy nên chuyển:

- Cần nhiều file source và package có tên.
- Cần expose type để module khác sử dụng.
- Cần dependency injection, plugin hoặc service provider.
- Cần nhiều constructor hoặc quản lý vòng đời object rõ ràng.
- Cần public API và Javadoc ổn định.
- Cần chia trách nhiệm CLI, domain, persistence và configuration.

Việc chuyển đổi rất trực tiếp: giữ các import, bọc các member còn lại trong class tường minh và đổi tên class theo API dự án. Ví dụ cấu trúc class thông thường:

~~~java
package com.example.tasks;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TaskCli {
    public static void main(String[] args) throws IOException {
        // Gọi application service.
    }
}
~~~

Khi chuyển sang class thông thường, không còn tự động import toàn bộ `java.base` như compact source file; hãy thêm import cần thiết. Có thể giữ instance main nếu muốn, nhưng class tường minh thường dùng `public static void main(String[] args)` cho entry point của ứng dụng đóng gói và tương thích rộng với tooling.

## 20. Bài tập mở rộng

### Bài A — Thêm lệnh `clear`

Bổ sung command `clear` để xóa toàn bộ task. Yêu cầu xác nhận trước khi ghi file rỗng.

**Đạt:** dùng `IO.readln` nhận xác nhận, xử lý EOF và chỉ gọi `saveTasks` sau khi người dùng đồng ý.

### Bài B — Thêm lệnh `find`

Thêm `find <keyword>` để lọc task theo từ khóa không phân biệt hoa thường.

**Đạt:** dùng `String.contains` sau khi chuẩn hóa bằng `toLowerCase(Locale.ROOT)`, giữ nguyên nội dung gốc khi hiển thị.

### Bài C — Thêm ngày tạo

Mở rộng record thành `Task(boolean done, String description, Instant createdAt)`. Cập nhật định dạng lưu file và kiểm tra dữ liệu cũ.

**Đạt:** dùng `Instant` cho thời điểm tuyệt đối, không parse chuỗi ngày theo locale máy.

### Bài D — Thêm bộ lọc hoàn thành

Bổ sung `list --done` và `list --open`.

**Đạt:** tách parse command-line arguments khỏi logic hiển thị để tránh lặp code.

### Bài E — Chuyển sang class tường minh

Tạo class `TaskCli` trong package có tên. Di chuyển record và persistence code thành các type phù hợp.

**Đạt:** giải thích được điểm khác nhau giữa unnamed package và named package, implicit class và explicit class, implicit `java.base` import và import thông thường.

### Bài F — Kiểm thử file bị hỏng

Sửa thủ công một dòng trong file dữ liệu để tạo status sai, Base64 sai hoặc UTF-8 sai. Chạy `list` và quan sát lỗi.

**Đạt:** chương trình không âm thầm bỏ dữ liệu hỏng hoặc ghi đè file khi chưa xử lý.

## 21. Checklist tự đánh giá

- [ ] File `TaskCli.java` không có khai báo package hoặc class bao ngoài.
- [ ] Có instance `void main(String[] args)` và launcher gọi được.
- [ ] Chương trình dùng `IO.readln`/`IO.println` cho terminal.
- [ ] Không trộn `IO.readln` với một reader khác trên `System.in`.
- [ ] Dùng `Path` và `Files` cho file I/O.
- [ ] Chỉ định UTF-8 khi đọc và ghi file.
- [ ] Có thể thêm, liệt kê, hoàn thành và xóa task.
- [ ] Dữ liệu còn sau khi JVM kết thúc và chạy lại.
- [ ] Đầu vào sai và file dữ liệu lỗi được báo rõ.
- [ ] Hiểu giới hạn của compact source file và biết khi nào chuyển sang class/package thông thường.

## 22. Tài liệu tham khảo chính thức

- [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): đặc tả và mục tiêu của tính năng final trong Java 25.
- [Compact Source Files and Instance Main Methods — Java SE 25 Language Guide](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): lớp được khai báo ngầm, `main`, IO, tự động import `java.base` và cách phát triển chương trình.
- [The java Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): source-file mode, `--source` và cách truyền đối số.
- [Class IO — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IO.html): `readln`, `print` và `println`.
- [Files — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): đọc/ghi file, `readAllLines` và `write`.
- [Path — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html): tạo và thao tác đường dẫn.
- [StandardCharsets — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset UTF-8 chuẩn.
- [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): module import declarations cũng được hoàn thiện trong Java 25; compact source files tự động import các kiểu public từ `java.base`.

**Ghi chú tính hiện hành:** Compact source files và instance main methods là tính năng final từ Java 25 theo JEP 512, không cần preview flag. `java.lang.IO`, `Path` và `Files` là API Java SE hiện hành. Bài dùng UTF-8 tường minh cho dữ liệu file và giới hạn compact source file ở một tiện ích độc lập; khi cần package, API tái sử dụng hoặc module hóa, hãy chuyển sang class thông thường.

**Kết quả cần nộp:** file `TaskCli.java` chạy được trên JDK 25, ảnh hoặc log các lệnh add/list/done/remove, file dữ liệu UTF-8 sau khi chạy, cùng phần giải thích cách launcher tạo instance cho `main` và cách file I/O giữ dữ liệu giữa các lần chạy.
