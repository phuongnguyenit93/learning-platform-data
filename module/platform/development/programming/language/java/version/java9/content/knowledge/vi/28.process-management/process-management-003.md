# Quan hệ cha, con và cây tiến trình trong Java

Java 9 bổ sung Process API để quan sát và điều khiển tiến trình ở cấp hệ điều hành. Trung tâm của API mới là `ProcessHandle`: một đối tượng đại diện cho một process đang chạy, có thể cung cấp PID, thông tin tiến trình, quan hệ với tiến trình cha/con, trạng thái sống, sự kiện kết thúc và các thao tác yêu cầu dừng.

Một chương trình Java có thể tạo process bằng `ProcessBuilder`, lấy handle của process đó qua `Process.toHandle()`, rồi quan sát cây tiến trình bằng `parent()`, `children()` và `descendants()`. Những API này hữu ích khi chạy công cụ bên ngoài, quản lý worker process, giám sát tiến trình con hoặc chẩn đoán ứng dụng khởi chạy nhiều process.

## 1. Phân biệt Process và ProcessHandle

Hai kiểu này liên quan với nhau nhưng phục vụ hai mục đích khác nhau:

- `Process` đại diện cho một process được chương trình Java khởi chạy. Nó hỗ trợ tương tác với luồng vào/ra của process, chờ kết thúc, lấy exit code và yêu cầu dừng.
- `ProcessHandle` đại diện cho một process ở cấp hệ điều hành. Nó cung cấp PID, thông tin tiến trình, quan hệ cha/con và các thao tác giám sát hoặc điều khiển.

Ví dụ tạo process và lấy handle:

~~~java
Process process = new ProcessBuilder("java", "-version").start();
ProcessHandle handle = process.toHandle();

System.out.println("pid=" + handle.pid());
System.out.println("alive=" + handle.isAlive());
~~~

`Process.toHandle()` và phần lớn API `ProcessHandle` được bổ sung từ Java 9. Handle giúp quan sát process ngay cả khi nó không được tạo bởi đối tượng `Process` hiện tại, miễn là process đó tồn tại và có thể truy cập theo quyền của hệ điều hành.

Không nên xem PID là định danh vĩnh viễn. Hệ điều hành có thể tái sử dụng PID sau khi process kết thúc. Một handle gắn với process cụ thể; còn việc tra cứu lại bằng PID ở thời điểm khác có thể dẫn tới process khác nếu PID đã được tái sử dụng.

## 2. Lấy ProcessHandle và PID

Có một số cách phổ biến để lấy handle:

### Handle của JVM hiện tại

~~~java
ProcessHandle current = ProcessHandle.current();

long pid = current.pid();
boolean alive = current.isAlive();
~~~

`current()` trả về handle của tiến trình đang chạy JVM. `pid()` trả về PID do hệ điều hành cấp; kiểu trả về là `long`, không phải `int`.

### Tra cứu theo PID

~~~java
Optional<ProcessHandle> found = ProcessHandle.of(pid);

found.ifPresent(handle ->
    System.out.println("alive=" + handle.isAlive())
);
~~~

`of(pid)` trả về Optional. Nếu không tìm thấy process tương ứng hoặc process không thể được truy cập, kết quả có thể là Optional rỗng. Việc tra cứu cũng có thể bị từ chối bởi quyền truy cập hoặc chính sách của hệ điều hành.

Không nên chỉ kiểm tra PID rồi giả định process vẫn là process cũ ở lần thao tác sau. Process có thể kết thúc giữa hai lần kiểm tra; đây là một race condition bình thường khi giám sát process.

### Lấy handle từ Process

~~~java
Process process = new ProcessBuilder("some-command").start();
ProcessHandle handle = process.toHandle();
~~~

Đây là cách phù hợp khi chương trình tự tạo process bằng `ProcessBuilder` và muốn dùng thêm API ProcessHandle.

## 3. Quan hệ cha và con

Một process được tạo bởi process khác thường có quan hệ cha/con ở cấp hệ điều hành. ProcessHandle cung cấp ba phương thức để quan sát quan hệ này:

| Phương thức | Kết quả | Ý nghĩa |
|---|---|---|
| `parent()` | `Optional<ProcessHandle>` | Process cha nếu có thể xác định |
| `children()` | `Stream<ProcessHandle>` | Các process con trực tiếp |
| `descendants()` | `Stream<ProcessHandle>` | Tất cả process hậu duệ ở các cấp bên dưới |

### parent(): tìm process cha

~~~java
ProcessHandle.current().parent().ifPresent(parent -> {
    System.out.println("parent pid=" + parent.pid());
});
~~~

Kết quả là Optional vì không phải lúc nào process cha cũng có thể xác định hoặc truy cập. Process cha có thể đã kết thúc, process có thể được khởi chạy bởi một cơ chế hệ điều hành đặc biệt, hoặc quyền truy cập có thể hạn chế thông tin.

Không nên giả định `parent()` luôn có giá trị. Luôn xử lý trường hợp Optional rỗng.

### children(): các process con trực tiếp

~~~java
ProcessHandle current = ProcessHandle.current();

current.children().forEach(child ->
    System.out.println("child pid=" + child.pid())
);
~~~

`children()` chỉ trả về process con trực tiếp của process hiện tại. Nếu process A tạo B và B tạo C, thì B là child của A; C là descendant của A nhưng không phải child trực tiếp của A.

### descendants(): toàn bộ hậu duệ

~~~java
ProcessHandle.current().descendants().forEach(descendant ->
    System.out.println("descendant pid=" + descendant.pid())
);
~~~

`descendants()` bao gồm các process con, cháu và những cấp sâu hơn trong cây process. Stream này không bao gồm chính process gốc.

Ví dụ cấu trúc:

~~~text
JVM A
└── Process B
    ├── Process C
    │   └── Process E
    └── Process D
~~~

Với JVM A:

- `children()` có B.
- `descendants()` có B, C, D và E.

Thứ tự phần tử trong Stream không phải một cam kết về thứ tự duyệt cây. Nếu cần sắp xếp theo PID, thời gian bắt đầu hoặc tiêu chí riêng, hãy thu thập rồi sắp xếp theo tiêu chí đó.

## 4. Snapshot và sự thay đổi của cây tiến trình

`children()` và `descendants()` cung cấp snapshot quan hệ process tại thời điểm truy vấn. Đây không phải một subscription liên tục theo dõi mọi thay đổi của cây.

Điều này dẫn tới một số hệ quả:

- Process mới được tạo sau khi lấy snapshot có thể không xuất hiện trong Stream đã nhận.
- Process có thể kết thúc trước khi chương trình xử lý xong handle của nó.
- Quan hệ cha/con có thể thay đổi khi process kết thúc hoặc hệ điều hành tái gán process mồ côi.
- Việc lấy danh sách process và hành động lên từng process không phải một giao dịch nguyên tử.

Ví dụ, process có thể còn sống khi lấy danh sách nhưng kết thúc ngay trước khi gọi `info()` hoặc `destroy()`. Vì vậy, mã giám sát phải chấp nhận trạng thái thay đổi và xử lý kết quả/ngoại lệ ở từng thao tác.

Không nên giữ một danh sách ProcessHandle trong bộ nhớ rồi giả định danh sách đó luôn phản ánh cây process hiện tại. Khi cần ảnh chụp mới, gọi lại `children()` hoặc `descendants()`.

## 5. Lấy thông tin bằng ProcessHandle.Info

`ProcessHandle.info()` trả về đối tượng `ProcessHandle.Info` chứa thông tin có thể truy cập về process:

~~~java
ProcessHandle.Info info = handle.info();

Optional<String> command = info.command();
Optional<String> commandLine = info.commandLine();
Optional<String[]> arguments = info.arguments();
Optional<Instant> start = info.startInstant();
Optional<Duration> cpu = info.totalCpuDuration();
Optional<String> user = info.user();
~~~

Các trường thông tin chính:

| Phương thức | Thông tin |
|---|---|
| `command()` | Đường dẫn hoặc tên chương trình thực thi |
| `commandLine()` | Dòng lệnh đã dùng để khởi chạy process |
| `arguments()` | Các đối số truyền cho chương trình |
| `startInstant()` | Thời điểm process bắt đầu |
| `totalCpuDuration()` | Tổng thời gian CPU đã sử dụng |
| `user()` | Người dùng sở hữu process |

Mỗi giá trị được trả về dưới dạng Optional. Hệ điều hành, quyền truy cập, cách khởi chạy process và khả năng cung cấp thông tin có thể khiến một số trường không có giá trị. Không được gọi `get()` một cách mù quáng.

Ví dụ xử lý an toàn:

~~~java
ProcessHandle.Info info = handle.info();

String command = info.command().orElse("<không có thông tin>");
String user = info.user().orElse("<không xác định>");

System.out.println("command=" + command);
System.out.println("user=" + user);
~~~

Thông tin dòng lệnh và đối số có thể chứa dữ liệu nhạy cảm do ứng dụng truyền vào, chẳng hạn token hoặc mật khẩu. Tránh ghi toàn bộ command line/arguments vào log công khai; chỉ thu thập trường thực sự cần thiết và che dữ liệu bí mật.

## 6. Liệt kê process nhìn thấy được

`ProcessHandle.allProcesses()` trả về Stream các process mà tiến trình hiện tại có thể nhìn thấy:

~~~java
ProcessHandle.allProcesses()
    .forEach(handle ->
        System.out.println(handle.pid())
    );
~~~

Đây là cách hữu ích để xây dựng công cụ quan sát process. Tuy nhiên, không nên coi kết quả là danh sách tuyệt đối mọi process trên máy:

- Quyền hệ điều hành có thể giới hạn process được nhìn thấy.
- Process có thể kết thúc trong lúc chương trình đang duyệt.
- Process mới có thể xuất hiện sau khi snapshot được tạo.
- Thông tin chi tiết của một số process có thể không truy cập được.

Khi chỉ cần lọc process theo thuộc tính có sẵn:

~~~java
List<ProcessHandle> javaProcesses = ProcessHandle.allProcesses()
    .filter(handle -> handle.info().command()
        .map(command -> command.toLowerCase().contains("java"))
        .orElse(false))
    .collect(Collectors.toList());
~~~

Đoạn mã này chỉ là bộ lọc theo chuỗi command có thể truy cập được. Tên command có thể khác nhau theo hệ điều hành hoặc cách cài đặt JDK, nên không nên dùng kiểm tra chuỗi đơn giản làm cơ chế nhận dạng bảo mật.

Với máy có nhiều process, hãy giới hạn thông tin thu thập và tránh giữ các snapshot lớn lâu hơn cần thiết.

## 7. Theo dõi vòng đời process bằng onExit()

`ProcessHandle.onExit()` trả về `CompletableFuture<ProcessHandle>`. Future hoàn tất khi process kết thúc:

~~~java
ProcessHandle handle = process.toHandle();

handle.onExit().thenAccept(exited ->
    System.out.println("process ended: " + exited.pid())
);
~~~

Cách này hữu ích khi muốn thực hiện callback sau khi process kết thúc mà không phải chặn luồng hiện tại bằng `waitFor()`.

Có thể chờ hoàn tất bằng:

~~~java
ProcessHandle exited = handle.onExit().get();
~~~

Trong ứng dụng thực tế nên đặt timeout nếu không thể chờ vô hạn:

~~~java
handle.onExit().get(10, TimeUnit.SECONDS);
~~~

`onExit()` là tín hiệu hoàn tất của process cụ thể. Nếu process cha kết thúc, không có cam kết rằng mọi process con cũng đã kết thúc. Muốn theo dõi từng process con, cần giữ handle và theo dõi từng future tương ứng.

Với đối tượng `Process`, `waitFor()` vẫn hữu ích khi cần exit code. Có thể kết hợp:

~~~java
Process process = new ProcessBuilder("some-command").start();
ProcessHandle handle = process.toHandle();

handle.onExit().get();
int exitCode = process.exitValue();
~~~

## 8. Yêu cầu dừng process

ProcessHandle cung cấp:

- `destroy()`: yêu cầu process kết thúc theo cơ chế mà nền tảng hỗ trợ.
- `destroyForcibly()`: yêu cầu kết thúc cưỡng bức.
- `supportsNormalTermination()`: cho biết `destroy()` có hỗ trợ kết thúc bình thường trên nền tảng hiện tại hay không.
- `isAlive()`: kiểm tra process còn sống tại thời điểm gọi.

Ví dụ:

~~~java
if (handle.isAlive()) {
    boolean normalSupported = handle.supportsNormalTermination();
    boolean requested = handle.destroy();

    System.out.println("normal termination supported="
        + normalSupported);
    System.out.println("termination requested=" + requested);
}
~~~

Kết quả boolean của `destroy()` hoặc `destroyForcibly()` không có nghĩa process đã chắc chắn kết thúc ngay lập tức. Đây là yêu cầu gửi tới hệ điều hành; cần theo dõi `onExit()` hoặc kiểm tra `isAlive()` để biết trạng thái sau đó.

Không nên dùng `destroyForcibly()` ngay khi có lỗi nhỏ. Ưu tiên gửi yêu cầu kết thúc bình thường, chờ trong một khoảng thời gian hợp lý, sau đó mới cân nhắc kết thúc cưỡng bức theo chính sách của ứng dụng.

### Dừng một process không đồng nghĩa dừng cả cây

Gọi `destroy()` trên process cha không tạo ra cam kết portable rằng toàn bộ descendants sẽ kết thúc. Hành vi khi process cha dừng và cách hệ điều hành xử lý process con khác nhau theo nền tảng.

Nếu ứng dụng cần dừng cả cây process do mình quản lý, cần lưu lại các handle của process con, xác định danh sách descendants tại thời điểm dừng, gửi yêu cầu kết thúc cho từng process và chờ từng process hoàn tất. Danh sách này vẫn là snapshot nên có thể bỏ sót process mới được tạo đồng thời; thiết kế ứng dụng nên kiểm soát việc tạo process mới trước khi bắt đầu shutdown.

Khi dừng theo cây, thường cần xử lý process ở tầng sâu trước rồi mới tới process cha để giảm khả năng process cha tạo thêm con trong lúc dọn dẹp. Đây là chiến lược quản lý ứng dụng, không phải bảo đảm thứ tự của Stream descendants.

## 9. Tạo process con bằng ProcessBuilder và quan sát quan hệ

`ProcessBuilder` vẫn là API chính để khởi chạy chương trình bên ngoài:

~~~java
Process process = new ProcessBuilder(
    "java", "-version"
).start();

ProcessHandle child = process.toHandle();
~~~

Từ handle này có thể:

- Lấy PID bằng `pid()`.
- Kiểm tra trạng thái bằng `isAlive()`.
- Xem process cha bằng `parent()`.
- Quan sát các process con của nó bằng `children()`.
- Theo dõi descendants bằng `descendants()`.
- Lấy thông tin qua `info()`.
- Đợi kết thúc qua `onExit()`.

Cần phân biệt process con của JVM với process con do process con đó tạo ra. Ví dụ JVM A tạo process B; nếu B khởi chạy C thì C là descendant của A nhưng parent trực tiếp của C là B.

Nếu chương trình cần quản lý một nhóm process, hãy thiết kế một lớp quản lý vòng đời riêng: lưu handle đã tạo, ghi nhận trạng thái, xử lý timeout và dừng theo chính sách. Không nên dựa hoàn toàn vào việc quét `allProcesses()` để tìm process do ứng dụng tạo, vì các process khác trên máy có thể có cùng tên chương trình.

## 10. Ví dụ Java chạy được: tạo child và kiểm tra cây process

Ví dụ sau tự khởi chạy một bản sao của chính chương trình ở chế độ child. JVM cha kiểm tra parent, children, descendants và đợi child kết thúc bằng `onExit()`.

~~~java
import java.io.File;
import java.util.concurrent.TimeUnit;

public class ProcessTreeExample {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--child".equals(args[0])) {
            Thread.sleep(3000);
            return;
        }

        ProcessHandle current = ProcessHandle.current();
        System.out.println("current alive=" + current.isAlive());
        System.out.println("current pid positive=" + (current.pid() > 0));

        boolean windows = System.getProperty("os.name")
            .toLowerCase().contains("win");
        String javaExecutable = System.getProperty("java.home")
            + File.separator + "bin" + File.separator
            + (windows ? "java.exe" : "java");

        Process child = new ProcessBuilder(
            javaExecutable,
            "-cp",
            System.getProperty("java.class.path"),
            ProcessTreeExample.class.getName(),
            "--child"
        ).start();

        ProcessHandle childHandle = child.toHandle();

        boolean parentMatches = childHandle.parent()
            .map(parent -> parent.pid() == current.pid())
            .orElse(false);
        System.out.println("child parent is current=" + parentMatches);

        boolean directChildListed = current.children()
            .anyMatch(handle -> handle.pid() == childHandle.pid());
        System.out.println("direct child listed=" + directChildListed);

        boolean descendantListed = current.descendants()
            .anyMatch(handle -> handle.pid() == childHandle.pid());
        System.out.println("descendant listed=" + descendantListed);

        childHandle.onExit().get(10, TimeUnit.SECONDS);
        System.out.println("child exited=" + !childHandle.isAlive());
        System.out.println("child exit code=" + child.exitValue());
    }
}
~~~

Lưu trong tệp `ProcessTreeExample.java`, biên dịch và chạy với Java 17 trở lên:

~~~shell
javac --release 9 -Xlint:all ProcessTreeExample.java
java ProcessTreeExample
~~~

Kết quả stdout trên hệ thống cho phép quan sát process con:

~~~text
current alive=true
current pid positive=true
child parent is current=true
direct child listed=true
descendant listed=true
child exited=true
child exit code=0
~~~

Giải thích:

1. JVM hiện tại lấy handle bằng `ProcessHandle.current()`.
2. `ProcessBuilder` tạo một JVM con chạy cùng class ở chế độ `--child`.
3. `Process.toHandle()` lấy handle của child process.
4. `childHandle.parent()` xác nhận process cha của child là JVM hiện tại.
5. `current.children()` tìm child trực tiếp.
6. `current.descendants()` cũng chứa child đó vì child là hậu duệ của JVM hiện tại.
7. `onExit()` hoàn tất khi child kết thúc; sau đó `isAlive()` trả false và `exitValue()` trả mã thoát 0.

Trong môi trường bị giới hạn quyền hoặc không cho phép quan sát process, các kết quả kiểm tra quan hệ có thể khác. Chương trình production cần xử lý trường hợp không có thông tin thay vì giả định mọi hệ điều hành đều cung cấp đầy đủ.

## 11. Race condition và giới hạn cần hiểu

Quản lý process luôn tương tác với trạng thái thay đổi bên ngoài JVM. Một số tình huống thường gặp:

- Process kết thúc ngay sau khi `isAlive()` trả true.
- Process cha kết thúc trước khi gọi `parent()`.
- Process con mới xuất hiện sau khi gọi `children()`.
- Process bị quyền hệ điều hành hạn chế nên `info()` chỉ cung cấp một phần dữ liệu.
- PID được tái sử dụng sau khi process cũ kết thúc.
- Yêu cầu `destroy()` đã gửi nhưng process vẫn còn chạy trong một khoảng thời gian.
- Process con tạo ra descendants mới trong lúc ứng dụng đang shutdown.

Do đó:

1. Dùng Optional cho dữ liệu có thể không có.
2. Xử lý `IOException`, `SecurityException`, timeout và trạng thái process thay đổi.
3. Dùng `onExit()` để chờ hoàn tất thay vì chỉ dựa vào một lần kiểm tra `isAlive()`.
4. Không giả định snapshot process tree là danh sách live.
5. Không dùng PID làm khóa định danh lâu dài.
6. Thiết kế shutdown có giới hạn thời gian và có chính sách xử lý process còn sống.

## 12. Những lỗi thường gặp

- **Nhầm children với descendants:** children chỉ là con trực tiếp; descendants gồm mọi cấp bên dưới.
- **Giả định parent luôn có giá trị:** parent trả Optional và có thể rỗng.
- **Coi descendants là cây live:** đây là snapshot tại thời điểm gọi, không tự cập nhật khi process thay đổi.
- **Giả định allProcesses nhìn thấy mọi process:** quyền hệ điều hành và khả năng truy cập có thể giới hạn kết quả.
- **Gọi Optional.get() không kiểm tra:** command, user, parent và các trường Info có thể không có dữ liệu.
- **Xem PID là định danh vĩnh viễn:** PID có thể được tái sử dụng sau khi process kết thúc.
- **Cho rằng destroy cha tự dừng mọi process con:** API không bảo đảm hành vi portable đó.
- **Coi destroy() trả true là process đã dừng:** cần chờ onExit hoặc xác minh trạng thái sau đó.
- **Đọc toàn bộ command line vào log:** đối số có thể chứa bí mật; chỉ ghi trường cần thiết và che dữ liệu nhạy cảm.
- **Dùng quét allProcesses để quản lý process của ứng dụng:** hãy giữ handle của process do chính ứng dụng tạo và quản lý vòng đời rõ ràng.

## 13. Tài liệu tham khảo chính thức

- [ProcessHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessHandle.html): PID, parent, children, descendants, allProcesses, Info, onExit và thao tác dừng.
- [Process — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): quan hệ giữa Process và ProcessHandle, waitFor, exitValue, toHandle và vòng đời process.
- [ProcessBuilder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): khởi chạy process và cấu hình command/environment/IO.
- [JEP 102: Process API Updates](https://openjdk.org/jeps/102): thiết kế Process API được bổ sung trong Java 9.