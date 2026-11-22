# Tiến trình hiện tại, tìm theo PID và liệt kê tiến trình

Từ Java 9, API **ProcessHandle** cung cấp cách làm việc với tiến trình của hệ điều hành ngay trong Java. Có thể lấy tiến trình đang chạy JVM, đọc PID, tìm một tiến trình theo PID và duyệt các tiến trình mà chương trình hiện tại được phép nhìn thấy.

API này cũng cung cấp thông tin mô tả tiến trình như lệnh khởi chạy, thời điểm bắt đầu, thời lượng CPU và người dùng. Một số thông tin phụ thuộc hệ điều hành và quyền truy cập nên được biểu diễn bằng Optional.

## 1. ProcessHandle và PID

**ProcessHandle** là một handle đại diện cho một tiến trình của hệ điều hành. Nó cho phép truy vấn trạng thái, thông tin và quan hệ giữa các tiến trình.

PID (process identifier) là mã số hệ điều hành dùng để nhận diện một tiến trình tại một thời điểm. PID thường được dùng khi cần tìm tiến trình cụ thể hoặc đối chiếu với thông tin từ công cụ quản lý tiến trình của hệ điều hành.

Các phương thức nền tảng:

| Phương thức | Công dụng |
|---|---|
| ProcessHandle.current() | Lấy handle của tiến trình đang chạy JVM |
| pid() | Lấy PID của tiến trình |
| isAlive() | Kiểm tra tiến trình còn hoạt động hay không |
| info() | Lấy thông tin mô tả tiến trình |
| ProcessHandle.of(pid) | Tìm handle theo PID, trả về Optional |
| ProcessHandle.allProcesses() | Tạo Stream chứa các tiến trình nhìn thấy được |
| parent() | Lấy tiến trình cha nếu có thể xác định |
| children() | Liệt kê các tiến trình con trực tiếp |
| descendants() | Liệt kê các tiến trình con ở mọi cấp |

ProcessHandle và các phương thức trên có từ Java 9, vì vậy có thể dùng trong ứng dụng chạy Java 9 trở lên.

## 2. Lấy tiến trình hiện tại và PID

Dùng ProcessHandle.current() để lấy handle của tiến trình đang chạy chương trình Java. Gọi pid() trên handle đó để lấy PID:

~~~java
ProcessHandle current = ProcessHandle.current();

long currentPid = current.pid();
boolean alive = current.isAlive();

System.out.println("PID: " + currentPid);
System.out.println("Alive: " + alive);
~~~

current() đại diện cho tiến trình đang chạy JVM. pid() trả về mã định danh native mà hệ điều hành cấp cho tiến trình. isAlive() cho biết tiến trình còn hoạt động tại thời điểm kiểm tra.

PID có thể được hệ điều hành tái sử dụng sau khi một tiến trình kết thúc. Vì vậy, nếu lưu PID để dùng về sau, không nên mặc định rằng cùng một số PID luôn chỉ cùng một tiến trình trong suốt thời gian chạy ứng dụng.

## 3. Tìm tiến trình theo PID bằng ProcessHandle.of()

Dùng ProcessHandle.of(long pid) để tra cứu một tiến trình:

~~~java
long pid = 12345;

Optional<ProcessHandle> process = ProcessHandle.of(pid);

if (process.isPresent()) {
    ProcessHandle handle = process.get();
    System.out.println("Found PID: " + handle.pid());
    System.out.println("Alive: " + handle.isAlive());
} else {
    System.out.println("Process not found");
}
~~~

Phương thức trả về Optional<ProcessHandle>:

- Optional có giá trị khi có thể lấy được handle cho PID được yêu cầu.
- Optional rỗng khi không tồn tại tiến trình tương ứng với PID tại thời điểm tra cứu.
- PID không hợp lệ, chẳng hạn số âm hoặc 0, có thể gây IllegalArgumentException.
- Tùy môi trường và quyền truy cập, thao tác truy vấn có thể bị từ chối bằng SecurityException.

Có thể viết gọn bằng ifPresentOrElse():

~~~java
ProcessHandle.of(pid).ifPresentOrElse(
        handle -> System.out.println("Found: " + handle.pid()),
        () -> System.out.println("Process not found")
);
~~~

Nếu PID được nhập từ tham số dòng lệnh, cần kiểm tra dữ liệu trước khi chuyển bằng Long.parseLong(). Chuỗi không phải số hợp lệ sẽ gây NumberFormatException.

Sau khi lấy được handle, nên kiểm tra isAlive() trước khi thực hiện các thao tác cần tiến trình còn hoạt động. Tiến trình có thể kết thúc ngay sau lúc tra cứu, nên kết quả kiểm tra chỉ phản ánh trạng thái tại thời điểm gọi.

## 4. Liệt kê tiến trình bằng ProcessHandle.allProcesses()

ProcessHandle.allProcesses() trả về Stream<ProcessHandle> chứa các tiến trình mà tiến trình hiện tại có thể nhìn thấy:

~~~java
ProcessHandle.allProcesses()
        .forEach(handle ->
                System.out.println("PID: " + handle.pid()));
~~~

Có thể kết hợp Stream để lọc tiến trình còn sống và chỉ hiển thị một số kết quả:

~~~java
ProcessHandle.allProcesses()
        .filter(ProcessHandle::isAlive)
        .limit(10)
        .forEach(handle ->
                System.out.println("PID: " + handle.pid()));
~~~

Một số điểm cần lưu ý:

- allProcesses() trả về Stream, nên có thể dùng filter(), map(), limit(), count() và các thao tác Stream khác.
- Stream không cam kết thứ tự tiến trình. Không nên dựa vào thứ tự nhận được để suy ra tiến trình nào được tạo trước.
- Danh sách không phải snapshot cố định. Tiến trình có thể được tạo hoặc kết thúc trong khi chương trình đang duyệt.
- Một handle lấy được vẫn có thể đại diện cho tiến trình đã kết thúc khi chương trình kiểm tra nó. Dùng isAlive() nếu cần biết trạng thái tại thời điểm xử lý.
- Kết quả chỉ bao gồm các tiến trình nhìn thấy được từ môi trường hiện tại; không nên giả định rằng mọi tiến trình trên hệ điều hành đều có thể truy cập.
- Việc liệt kê có thể bị hạn chế bởi quyền của hệ điều hành hoặc môi trường chạy và có thể phát sinh SecurityException.

Nếu cần hiển thị toàn bộ danh sách, bỏ limit(). Với hệ thống có nhiều tiến trình, nên cân nhắc lọc trước khi in hoặc lưu kết quả để tránh tạo lượng đầu ra quá lớn.

## 5. Đọc thông tin mô tả bằng ProcessHandle.Info

Gọi info() trên một ProcessHandle để lấy đối tượng ProcessHandle.Info:

~~~java
ProcessHandle handle = ProcessHandle.current();
ProcessHandle.Info info = handle.info();

info.command().ifPresent(command ->
        System.out.println("Command: " + command));

info.user().ifPresent(user ->
        System.out.println("User: " + user));

info.startInstant().ifPresent(start ->
        System.out.println("Started: " + start));

info.totalCpuDuration().ifPresent(duration ->
        System.out.println("CPU time: " + duration));
~~~

Một số thông tin có thể truy vấn:

| Phương thức | Thông tin |
|---|---|
| command() | Đường dẫn hoặc tên lệnh khởi chạy |
| commandLine() | Dòng lệnh dùng để khởi chạy |
| arguments() | Các tham số dòng lệnh |
| startInstant() | Thời điểm tiến trình bắt đầu |
| totalCpuDuration() | Tổng thời lượng CPU đã sử dụng |
| user() | Người dùng sở hữu tiến trình |

Các phương thức này trả về Optional vì hệ điều hành có thể không cung cấp đầy đủ mọi trường thông tin. Hãy dùng ifPresent(), orElse() hoặc cách xử lý Optional phù hợp; không giả định command() hay user() luôn có giá trị.

Thông tin dòng lệnh và arguments có thể chứa đường dẫn hoặc dữ liệu nhạy cảm do ứng dụng truyền vào. Chỉ hiển thị hoặc ghi log những trường thực sự cần thiết.

## 6. Quan hệ giữa tiến trình cha và tiến trình con

ProcessHandle cũng hỗ trợ duyệt cây tiến trình:

~~~java
ProcessHandle current = ProcessHandle.current();

current.parent().ifPresent(parent ->
        System.out.println("Parent PID: " + parent.pid()));

current.children().forEach(child ->
        System.out.println("Child PID: " + child.pid()));

current.descendants().forEach(descendant ->
        System.out.println("Descendant PID: " + descendant.pid()));
~~~

- parent() trả về Optional chứa tiến trình cha nếu có thể xác định.
- children() trả về Stream các tiến trình con trực tiếp.
- descendants() trả về Stream các tiến trình con ở mọi cấp bên dưới.

Các tiến trình con có thể kết thúc hoặc thay đổi trong lúc duyệt. Nếu cần xử lý ổn định hơn, hãy kiểm tra isAlive() tại thời điểm thao tác và xử lý trường hợp tiến trình đã kết thúc.

## 7. Ví dụ hoàn chỉnh: lấy PID, tìm tiến trình và liệt kê

Lưu chương trình dưới tên **ProcessHandleDemo.java**. Ví dụ dùng API Java 9, chỉ truy vấn thông tin và không gửi lệnh dừng hay thay đổi tiến trình khác.

~~~java
import java.util.Optional;
import java.util.stream.Stream;

public class ProcessHandleDemo {

    private static void printProcess(ProcessHandle process) {
        ProcessHandle.Info info = process.info();
        String command = info.command().orElse("<not exposed>");
        System.out.println("pid=" + process.pid()
                + " alive=" + process.isAlive()
                + " command=" + command);
    }

    public static void main(String[] args) {
        ProcessHandle current = ProcessHandle.current();
        long currentPid = current.pid();

        long pidToFind = args.length == 0
                ? currentPid
                : Long.parseLong(args[0]);

        System.out.println("current pid available: " + (currentPid > 0));
        System.out.println("current process alive: " + current.isAlive());

        try {
            Optional<ProcessHandle> found = ProcessHandle.of(pidToFind);
            System.out.println("lookup pid " + pidToFind + ": "
                    + (found.isPresent() ? "found" : "not found"));
            found.ifPresent(ProcessHandleDemo::printProcess);
        } catch (SecurityException exception) {
            System.out.println("lookup pid " + pidToFind + ": access denied");
        }

        try {
            long visibleCount = ProcessHandle.allProcesses()
                    .filter(ProcessHandle::isAlive)
                    .count();
            System.out.println("visible live process count: " + visibleCount);
            System.out.println("sample visible live processes:");

            try (Stream<ProcessHandle> processes = ProcessHandle.allProcesses()) {
                processes.filter(ProcessHandle::isAlive)
                        .limit(5)
                        .forEach(ProcessHandleDemo::printProcess);
            }
        } catch (SecurityException exception) {
            System.out.println("process listing: access denied");
        }
    }
}
~~~

Biên dịch và chạy với PID mặc định là tiến trình hiện tại:

~~~bash
javac --release 9 ProcessHandleDemo.java
java ProcessHandleDemo
~~~

Có thể truyền PID cần tìm làm tham số:

~~~bash
java ProcessHandleDemo 12345
~~~

Dạng kết quả khi chạy:

~~~text
current pid available: true
current process alive: true
lookup pid <current-pid>: found
pid=<current-pid> alive=true command=<command-or-not-exposed>
visible live process count: <count>
sample visible live processes:
pid=<pid> alive=true command=<command-or-not-exposed>
pid=<pid> alive=true command=<command-or-not-exposed>
...
~~~

PID, số lượng tiến trình, đường dẫn lệnh và các dòng trong danh sách phụ thuộc hệ điều hành cũng như môi trường đang chạy. Nếu metadata không được cung cấp, chương trình hiển thị chuỗi not exposed.

## 8. Lỗi thường gặp và lưu ý khi sử dụng

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm PID với chỉ số cố định của ứng dụng | Tra cứu nhầm tiến trình sau khi PID được tái sử dụng | Kiểm tra trạng thái và metadata tại thời điểm tra cứu |
| Giả định ProcessHandle.of(pid) luôn trả về handle | Có thể không tìm thấy tiến trình hoặc không có quyền truy cập | Xử lý cả hai trường hợp bằng Optional và bắt SecurityException khi cần |
| Nghĩ allProcesses() luôn liệt kê mọi tiến trình của hệ điều hành | Bỏ qua giới hạn quyền và khả năng quan sát của môi trường | Chỉ coi kết quả là các tiến trình hiện có thể nhìn thấy |
| Dựa vào thứ tự của allProcesses() | Kết quả không ổn định giữa các lần chạy | Tự sắp xếp theo PID nếu cần thứ tự hiển thị |
| Giả định tiến trình vẫn sống sau khi lấy handle | Có thể thao tác trên tiến trình đã kết thúc | Kiểm tra isAlive() và xử lý race condition |
| Giả định mọi trường ProcessHandle.Info đều có giá trị | Có thể bỏ sót metadata không được hệ điều hành cung cấp | Xử lý các trường Optional riêng biệt |
| In toàn bộ command line và arguments vào log | Có thể làm lộ thông tin nhạy cảm | Chỉ ghi các trường cần thiết và kiểm soát quyền truy cập log |
| Dùng Long.parseLong() mà không kiểm tra đầu vào | Có thể phát sinh NumberFormatException | Xác thực PID trước khi tra cứu |

## 9. Ghi nhớ

- ProcessHandle được bổ sung từ Java 9 để truy vấn tiến trình của hệ điều hành.
- ProcessHandle.current() lấy tiến trình đang chạy JVM; pid() lấy PID và isAlive() kiểm tra trạng thái.
- ProcessHandle.of(pid) tìm tiến trình theo PID và trả về Optional.
- ProcessHandle.allProcesses() trả về Stream các tiến trình nhìn thấy được; thứ tự không được bảo đảm và danh sách có thể thay đổi trong lúc duyệt.
- ProcessHandle.Info cung cấp metadata dưới dạng Optional vì không phải hệ điều hành nào cũng cung cấp đủ thông tin.
- parent(), children() và descendants() hỗ trợ quan sát quan hệ giữa các tiến trình.
- PID có thể được tái sử dụng; handle có thể trở nên không còn sống khi tiến trình kết thúc.
- Khi làm việc với process, cần tính đến quyền truy cập, trạng thái thay đổi đồng thời và dữ liệu metadata có thể không đầy đủ.
