# Snapshot, tiến trình kết thúc và khả năng tái sử dụng PID

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt \`ProcessHandle\` với snapshot thông tin \`ProcessHandle.Info\`.
- Hiểu thời điểm mà \`info()\` thu thập dữ liệu và vì sao các trường metadata có thể không có.
- Theo dõi tiến trình kết thúc bằng \`onExit()\` thay vì chỉ dựa vào một lần kiểm tra \`isAlive()\`.
- Giải thích vì sao PID có thể được hệ điều hành tái sử dụng sau khi tiến trình cũ kết thúc.
- Tránh nhầm một tiến trình mới có cùng PID với tiến trình đã quan sát trước đó.

## 1. ProcessHandle và ProcessHandle.Info là hai thứ khác nhau

Java 9 bổ sung Process API trong \`java.lang.ProcessHandle\`. API này cho phép lấy PID, kiểm tra trạng thái, đọc một số thông tin và theo dõi thời điểm tiến trình kết thúc.

Cần phân biệt hai khái niệm:

- **\`ProcessHandle\`** đại diện cho một tiến trình cụ thể mà chương trình đang quan sát. Các thao tác như \`pid()\`, \`isAlive()\` và \`onExit()\` cung cấp thông tin về định danh số và vòng đời của tiến trình.
- **\`ProcessHandle.Info\`** là snapshot metadata thu được khi gọi \`handle.info()\`. Nó mô tả những thông tin mà runtime có thể lấy được tại thời điểm truy vấn.

Ví dụ:

~~~java
ProcessHandle handle = ProcessHandle.current();
long pid = handle.pid();

ProcessHandle.Info snapshot = handle.info();
~~~

Biến \`snapshot\` không phải một cửa sổ dữ liệu trực tiếp luôn cập nhật. Nếu tiến trình đổi trạng thái hoặc kết thúc sau đó, object \`Info\` đã lấy trước đó vẫn biểu diễn lần quan sát ban đầu. Muốn quan sát lại, gọi \`info()\` lần nữa; lần gọi mới có thể trả về các giá trị khác hoặc ít thông tin hơn nếu tiến trình đã kết thúc.

Giữ một snapshot không giữ tiến trình sống, không ngăn hệ điều hành tái sử dụng PID và không làm cho thông tin trở thành dữ liệu hiện thời.

## 2. Metadata trong Info là Optional

\`ProcessHandle.Info\` cung cấp một số trường metadata:

| Method | Thông tin |
|---|---|
| \`command()\` | Đường dẫn hoặc tên executable |
| \`commandLine()\` | Lệnh thực thi cùng các tham số dưới dạng chuỗi |
| \`arguments()\` | Các đối số truyền cho executable |
| \`startInstant()\` | Thời điểm tiến trình bắt đầu |
| \`totalCpuDuration()\` | Thời gian CPU đã sử dụng |
| \`user()\` | Người dùng sở hữu tiến trình |

Các method này trả về \`Optional\`, ví dụ:

~~~java
ProcessHandle.Info info = handle.info();

Optional<String> command = info.command();
Optional<String> commandLine = info.commandLine();
Optional<String[]> arguments = info.arguments();
Optional<Instant> start = info.startInstant();
Optional<Duration> cpu = info.totalCpuDuration();
Optional<String> user = info.user();
~~~

Một trường có thể là \`Optional.empty()\` vì hệ điều hành không cung cấp thông tin đó, runtime không truy cập được, tiến trình đã kết thúc hoặc implementation không hỗ trợ trường tương ứng. Không được giả định tất cả trường đều có giá trị.

Hãy kiểm tra Optional trước khi dùng:

~~~java
String executable = info.command().orElse("<unavailable>");

info.startInstant().ifPresent(
        instant -> System.out.println("Started at: " + instant));
~~~

Không gọi \`get()\` một cách mù quáng. Cũng không nên dùng một trường metadata tùy chọn làm bằng chứng duy nhất rằng một PID vẫn đại diện cho cùng tiến trình.

Thông tin command line và arguments có thể chứa đường dẫn, tên tài khoản hoặc dữ liệu nhạy cảm do ứng dụng truyền vào. Chỉ ghi log những trường cần thiết; tránh vô tình ghi token, mật khẩu hoặc bí mật nằm trong tham số dòng lệnh.

## 3. Snapshot có thể tồn tại sau khi tiến trình kết thúc

Có thể lấy thông tin trước khi tiến trình kết thúc rồi tiếp tục dùng snapshot sau khi nhận thông báo kết thúc:

~~~java
ProcessHandle handle = process.toHandle();

ProcessHandle.Info beforeExit = handle.info();
Optional<String> commandAtCapture = beforeExit.command();
Optional<Instant> startAtCapture = beforeExit.startInstant();

handle.onExit().join();

// Hai Optional trên vẫn là các giá trị đã chụp trước đó.
System.out.println(commandAtCapture.orElse("<unavailable>"));
System.out.println(startAtCapture.orElse(null));
~~~

Các giá trị đã chụp không tự thay đổi thành trạng thái sau khi kết thúc. Đây là điều hữu ích khi cần lưu metadata để ghi log hoặc điều tra sau này.

Tuy nhiên, snapshot chỉ chứa các trường runtime đã cung cấp tại thời điểm truy vấn. Nếu một trường đang là empty, việc giữ object lâu hơn không làm trường đó xuất hiện. Nếu cần lưu lịch sử, hãy chủ động sao chép các giá trị cần thiết vào cấu trúc dữ liệu của ứng dụng.

## 4. Theo dõi kết thúc bằng onExit

\`ProcessHandle.onExit()\` trả về \`CompletableFuture<ProcessHandle>\`. Future hoàn tất khi tiến trình được đại diện kết thúc:

~~~java
CompletableFuture<ProcessHandle> exitFuture = handle.onExit();

exitFuture.thenAccept(exited -> {
    System.out.println("Process ended: " + exited.pid());
});
~~~

Có thể dùng \`join()\` để đợi trong ví dụ đồng bộ hoặc kết hợp với callback để tiếp tục xử lý bất đồng bộ.

So sánh với \`isAlive()\`:

~~~java
if (handle.isAlive()) {
    // Tiến trình đang sống tại thời điểm kiểm tra.
}
~~~

\`isAlive()\` chỉ là một quan sát tại một thời điểm. Tiến trình có thể kết thúc ngay sau khi method trả về \`true\`. Vì vậy, đoạn code kiểm tra rồi hành động có thể gặp race condition:

1. Thread A kiểm tra \`isAlive()\` và nhận \`true\`.
2. Tiến trình kết thúc.
3. Thread A tiếp tục thực hiện hành động dựa trên giả định cũ.

\`onExit()\` phù hợp khi cần biết tiến trình đã kết thúc. Nó không biến các thao tác kiểm tra và hành động khác thành một giao dịch nguyên tử, cũng không bảo đảm tiến trình tiếp tục sống sau khi callback chạy.

## 5. PID có thể được tái sử dụng

PID là một số do hệ điều hành cấp cho tiến trình. PID thường duy nhất trong thời gian một tiến trình tồn tại, nhưng sau khi tiến trình kết thúc, hệ điều hành có thể cấp lại cùng số đó cho một tiến trình khác.

Ví dụ về trình tự có thể xảy ra:

| Thời điểm | Sự kiện |
|---|---|
| T1 | Tiến trình A chạy với PID 4200 |
| T2 | A kết thúc |
| T3 | Hệ điều hành tái sử dụng PID 4200 cho tiến trình B |
| T4 | Ứng dụng gọi \`ProcessHandle.of(4200)\` |

Ở T4, \`ProcessHandle.of(4200)\` có thể trả về handle của B. Việc PID giống nhau không chứng minh đó vẫn là A.

~~~java
long oldPid = oldHandle.pid();

// Sau khi oldHandle đã kết thúc, PID có thể được tái sử dụng.
Optional<ProcessHandle> currentOwner = ProcessHandle.of(oldPid);
~~~

\`ProcessHandle.of(pid)\` chỉ tra cứu tiến trình đang mang PID đó tại thời điểm gọi. Nếu Optional có giá trị, điều đó không chứng minh tiến trình được tìm thấy chính là tiến trình từng được quan sát trước đây.

Không dùng PID như một định danh lâu dài trong database, hàng đợi công việc hoặc cache để nhận diện tiến trình qua nhiều thời điểm. Không nên trì hoãn một hành động nguy hiểm rồi chỉ tra cứu lại bằng PID cũ.

## 6. Kết hợp PID với thông tin khác như thế nào?

Nếu cần đối chiếu tiến trình trong log hoặc hệ thống giám sát, có thể lưu thêm metadata:

- PID để hỗ trợ tra cứu và đọc log.
- \`startInstant()\` nếu runtime cung cấp, giúp phân biệt hai lần sử dụng cùng PID ở những thời điểm khác nhau.
- Command hoặc command line nếu được phép lưu và thực sự cần thiết.
- Một mã định danh do chính ứng dụng tạo nếu ứng dụng kiểm soát tiến trình con.

PID kết hợp với thời điểm bắt đầu là tín hiệu đối chiếu hữu ích, nhưng không nên coi là một định danh toàn cục được bảo đảm duy nhất. \`startInstant()\` là Optional và độ chính xác phụ thuộc hệ điều hành/implementation. Nếu cần nhận diện bền vững, hãy dùng một application-level ID hoặc token ngẫu nhiên do tiến trình con nhận qua tham số hay kênh IPC.

Nếu ứng dụng tự khởi chạy tiến trình bằng \`ProcessBuilder\`, hãy giữ \`Process\` hoặc \`ProcessHandle\` nhận được từ chính lần khởi chạy đó và theo dõi \`onExit()\`. Đừng tái tạo mối liên hệ với tiến trình cũ chỉ bằng cách gọi \`ProcessHandle.of(pid)\` sau khi nó đã kết thúc.

## 7. Ví dụ hoàn chỉnh: chụp snapshot rồi đợi tiến trình con kết thúc

Tạo file **ProcessSnapshotDemo.java**:

~~~java
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.Locale;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

public class ProcessSnapshotDemo {

    private static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win");

        Path executable = Paths.get(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java");

        return executable.toString();
    }

    public static void main(String[] args) throws Exception {
        Process child = new ProcessBuilder(javaExecutable(), "-version")
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start();

        ProcessHandle handle = child.toHandle();
        long pidAtStart = handle.pid();

        // Chụp metadata trước khi tiến trình kết thúc.
        ProcessHandle.Info snapshot = handle.info();
        Optional<String> commandAtStart = snapshot.command();
        Optional<Instant> startAtStart = snapshot.startInstant();

        // Đăng ký theo dõi kết thúc.
        CompletableFuture<ProcessHandle> exitFuture = handle.onExit();
        ProcessHandle exitedHandle = exitFuture.join();

        System.out.println("snapshot captured = " + (snapshot != null));
        System.out.println("pid positive = " + (pidAtStart > 0));
        System.out.println("command metadata available = "
                + commandAtStart.isPresent());
        System.out.println("start instant available = "
                + startAtStart.isPresent());
        System.out.println("child exit code = " + child.exitValue());
        System.out.println("alive after onExit = " + handle.isAlive());
        System.out.println("onExit handle has original pid = "
                + (exitedHandle.pid() == pidAtStart));

        // Snapshot và các Optional đã chụp vẫn có thể được đọc.
        System.out.println("captured command Optional retained = "
                + (commandAtStart != null));
        System.out.println("captured start Optional retained = "
                + (startAtStart != null));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out ProcessSnapshotDemo.java
java -cp out ProcessSnapshotDemo
~~~

Trên một môi trường Java thông thường, output có dạng:

~~~text
snapshot captured = true
pid positive = true
command metadata available = true
start instant available = true
child exit code = 0
alive after onExit = false
onExit handle has original pid = true
captured command Optional retained = true
captured start Optional retained = true
~~~

Hai dòng \`command metadata available\` và \`start instant available\` phụ thuộc hệ điều hành, quyền truy cập và implementation; chúng có thể là \`false\`. Các dòng còn lại xác nhận snapshot đã được lấy trước khi đợi, tiến trình con đã kết thúc và future trả về handle của tiến trình vừa được theo dõi.

Ví dụ chạy \`java -version\` bằng executable trong \`java.home\`, nên không phụ thuộc shell cụ thể. Output của tiến trình con được chuyển hướng để không làm lẫn với output kiểm thử.

## 8. Quy tắc thực hành an toàn

- Lấy snapshot sớm nếu cần lưu metadata của tiến trình ngắn hạn.
- Luôn kiểm tra \`Optional\`; không giả định command, arguments, start time, CPU duration hoặc user luôn sẵn có.
- Dùng \`onExit()\` khi cần phản ứng với sự kiện kết thúc; tránh vòng lặp polling liên tục.
- Xem \`isAlive()\` là một quan sát có thể cũ ngay sau khi trả về.
- Không dùng PID như định danh lâu dài sau khi tiến trình kết thúc.
- Dùng application-level ID khi cần đối chiếu bền vững giữa log, database và nhiều lần khởi chạy.
- Cân nhắc dữ liệu nhạy cảm trước khi lưu command line hoặc arguments.
- Không giả định giữ \`ProcessHandle.Info\` sẽ giữ tiến trình sống hoặc ngăn PID được cấp lại.

## 9. Lỗi thường gặp

### Nghĩ Info là dữ liệu live

\`Info\` là snapshot. Muốn có quan sát mới, gọi \`handle.info()\` lại và vẫn phải chấp nhận các trường Optional có thể empty.

### Gọi Optional.get() mà không kiểm tra

Thông tin tiến trình có thể bị giới hạn bởi hệ điều hành hoặc quyền truy cập. Dùng \`orElse\`, \`ifPresent\` hoặc kiểm tra \`isPresent()\`.

### Dùng PID cũ sau khi tiến trình kết thúc

PID có thể được cấp cho tiến trình khác. Một lần gọi \`ProcessHandle.of(pid)\` sau đó có thể tìm thấy tiến trình mới.

### Cho rằng isAlive() bảo đảm tiến trình còn sống ở bước tiếp theo

Trạng thái có thể đổi ngay sau khi kiểm tra. Thiết kế xử lý lỗi và race condition quanh hành động thực tế.

### Coi startInstant là định danh tuyệt đối

Trường này có thể không có và độ chính xác tùy môi trường. Dùng nó để hỗ trợ đối chiếu, không thay thế mã định danh ứng dụng.

### Giả định onExit() giữ tiến trình sống

Future chỉ thông báo tiến trình kết thúc. Nó không kéo dài vòng đời tiến trình và không biến PID thành định danh có thể tái sử dụng an toàn.

## 10. Checklist

- [ ] Đã phân biệt \`ProcessHandle\` với \`ProcessHandle.Info\`.
- [ ] Đã hiểu \`Info\` là snapshot tại thời điểm gọi \`info()\`.
- [ ] Đã kiểm tra Optional trước khi đọc metadata.
- [ ] Đã lưu các trường cần thiết trước khi tiến trình ngắn hạn kết thúc.
- [ ] Đã dùng \`onExit()\` để theo dõi kết thúc khi phù hợp.
- [ ] Đã xem \`isAlive()\` là quan sát tức thời, có thể gặp race.
- [ ] Đã hiểu PID có thể được tái sử dụng sau khi tiến trình kết thúc.
- [ ] Không dùng PID đơn lẻ làm định danh lâu dài.
- [ ] Đã cân nhắc application-level ID và dữ liệu nhạy cảm trong command line.
- [ ] Đã biên dịch và chạy ví dụ với Java 9+.

