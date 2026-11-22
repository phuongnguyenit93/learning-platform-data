# 3.2 Dùng jcmd, jps và ProcessHandle để khám phá tiến trình; hiểu giới hạn thông tin trả về

Trong chẩn đoán Java, câu hỏi đầu tiên thường là: **JVM nào thực sự đang chạy ứng dụng cần điều tra, PID của nó là gì và mình có quyền nhìn thấy những thông tin nào?** Một máy có thể đồng thời chạy nhiều dịch vụ Java, một tiến trình build, một IDE và chính các công cụ chẩn đoán. Trong container, PID nhìn từ host còn có thể khác PID nhìn từ bên trong container. Chọn sai tiến trình dẫn đến đọc sai cấu hình, kết luận sai hoặc tác động lên dịch vụ khác.

Ba công cụ giải quyết các phần khác nhau của vấn đề:

- `jps` liệt kê **JVM được instrumentation của công cụ Java nhận diện** trong phạm vi có thể truy cập.
- `jcmd` có chế độ **liệt kê JVM** và có thể **gửi diagnostic command** tới một JVM tương thích, được phép attach.
- `ProcessHandle` là **Java API để nhận diện và xem tiến trình hệ điều hành**, bao gồm cả tiến trình không chạy JVM. API không tự cung cấp heap dump, GC history hay đảm bảo đọc được đầy đủ lệnh khởi động.

Mục tiêu là biết cách dùng đúng từng công cụ, kết hợp bằng chứng và giải thích **vì sao một tiến trình có thể xuất hiện trong công cụ này nhưng vắng mặt ở công cụ khác**. Phần nội dung tập trung vào nhận diện tiến trình, giới hạn dữ liệu và độ tin cậy; các diagnostic command chuyên sâu chỉ được nhắc đến như bước tiếp theo.

## 1. Phân biệt đối tượng được khám phá

### 1.1 Native process, JVM process và Java application không đồng nghĩa

Một ứng dụng Java thông thường chạy trong **một tiến trình hệ điều hành** chứa JVM. Tiến trình có một PID trong phạm vi định danh của hệ điều hành/namespace; JVM thực thi mã Java, quản lý heap, GC, JIT và giao tiếp với OS.

Không phải mọi native process là JVM: `ps`, trình duyệt, cơ sở dữ liệu hay load generator cũng là tiến trình OS. Ngược lại, không nên mặc định mỗi ứng dụng Java là đúng một PID: một hệ thống có thể có nhiều worker JVM, launcher, supervisor hoặc tiến trình con. Một JVM nhúng bằng launcher riêng cũng có thể không trình bày tên main class như ứng dụng chạy bằng `java -jar`.

Khi điều tra, cần nhận diện ít nhất:

| Danh tính | Điều gì được xác định? | Giới hạn |
| --- | --- | --- |
| PID / native process ID | Tiến trình OS ở một thời điểm trong namespace cụ thể | PID có thể được tái sử dụng sau khi tiến trình kết thúc |
| LVMID của `jps` | Định danh JVM cục bộ do công cụ báo | Thường là PID, **không được bảo đảm luôn bằng PID OS** |
| Main class / JAR | Entry point launcher hoặc mô tả mà công cụ thu được | Có thể là tên bootstrap, launcher framework hoặc `Unknown` |
| Executable path | Lệnh thực thi, chẳng hạn đường dẫn tới `java` | Không bảo đảm chỉ ra đúng artifact nghiệp vụ hoặc đủ đường dẫn |
| Start time | Thời điểm bắt đầu khi OS/API cung cấp được | Có thể thiếu và đồng hồ/thông tin thu được có giới hạn |
| Host, container, namespace | Phạm vi PID, quyền quan sát và giới hạn tài nguyên | PID trong container không nhất thiết trùng PID trên host |

**PID là một chỉ dấu để tra cứu, không phải định danh bền vững tuyệt đối.** Với service dài hạn, nên lưu thêm mốc thời gian khởi động, tên workload, container/pod instance, build/image ID và môi trường. Một lần nhìn thấy PID 4242 hôm qua không bảo đảm hôm nay PID ấy vẫn là JVM cũ.

### 1.2 Danh sách tiến trình là ảnh chụp, không phải lịch sử

Các tiến trình có thể khởi động, kết thúc hoặc thay PID giữa hai câu lệnh liên tiếp. Do đó:

- “Không thấy trong danh sách” không chứng minh JVM chưa từng chạy.
- “Có PID trong danh sách” không đảm bảo tiến trình còn sống khi lệnh tiếp theo chạy.
- “Không hiện command line” không đồng nghĩa tiến trình không có command line.
- “PID không đổi” cũng chưa đủ chứng minh một tiến trình vẫn là phiên bản đã quan sát trước, vì PID có thể tái sử dụng.

Khám phá tiến trình chủ yếu trả lời **tình trạng hiện thấy trong phạm vi được phép**; nó không tự cung cấp lịch sử restart, nguyên nhân crash, mức CPU trong nhiều giờ hay trạng thái GC. Với dữ liệu thời gian dài, cần log, event và metrics có timestamp.

## 2. Chọn công cụ theo câu hỏi

| Câu hỏi | `jps` | `jcmd` | `ProcessHandle` |
| --- | --- | --- | --- |
| Có JVM instrumented nào công cụ nhìn thấy? | Phù hợp | `jcmd -l` cũng phù hợp, với giới hạn riêng | Không phân biệt JVM nếu chỉ dùng API |
| Liệt kê native process, kể cả không chạy Java? | Không | Không phải mục tiêu | `allProcesses()` liệt kê những process OS nhìn thấy được |
| Lấy main class/JAR và thông tin launcher? | `-l`, `-m`, `-v` ở mức mà tool báo được | `-l` hoặc `VM.command_line` nếu attach được | `Info.commandLine()`/`arguments()` có thể thiếu hoặc không đầy đủ |
| Xác minh runtime flags của JVM đích? | `-v` cho các JVM arguments mà `jps` thu được | `VM.flags` và `VM.command_line` để điều tra sâu hơn | Không có API tiêu chuẩn để lấy effective JVM flags của process khác |
| Xem parent/children và start time của OS process? | Không trực tiếp | Không phải mục tiêu chính | `parent()`, `children()`, `descendants()`, `Info.startInstant()` |
| Truy vấn trạng thái GC/thread của JVM tương thích? | Không | Có diagnostic commands nếu được hỗ trợ và có quyền | Không bằng các phương thức ProcessHandle |
| Bảo đảm thấy **mọi** process/JVM trên máy? | Không | Không | Cũng không: quyền, OS, container/namespace và thời điểm giới hạn |

Từ bảng này, một chiến lược đúng là **phát hiện ứng viên → xác minh danh tính và phạm vi PID → chọn lệnh quan sát đủ nhẹ → đối chiếu chéo**. Không cần chạy thao tác nặng nếu mới chỉ muốn tìm PID.

## 3. Dùng jps để tìm các JVM instrumented

### 3.1 Các lệnh cơ bản

`jps` là công cụ đi kèm nhiều bản phân phối JDK. Trên một máy có JDK và quyền phù hợp:

```bash
jps
jps -l
jps -lm
jps -v
jps -q
```

Ý nghĩa cần nhớ:

| Lệnh/option | Kết quả mong đợi | Lưu ý |
| --- | --- | --- |
| `jps` | LVMID và tên ngắn main class hoặc JAR của JVM nhìn thấy | Tên chưa chắc là tên dịch vụ |
| `jps -l` | Tên package đầy đủ của main class hoặc đường dẫn JAR nếu biết | Launcher tùy biến có thể làm tên không có sẵn |
| `jps -m` | Thêm những đối số được truyền vào `main` theo khả năng công cụ | Có thể hiển thị `null` hoặc `Unknown` tùy JVM/launcher |
| `jps -v` | Thêm JVM arguments mà công cụ nhận diện được | Có thể lộ tham số nhạy cảm trong stdout |
| `jps -q` | Chỉ liệt kê LVMID | Không xác minh được danh tính ứng dụng từ mỗi số |
| `jps -lm` | Kết hợp tên dài và main arguments | Chuỗi chứa khoảng trắng có thể khó phân tách bằng script |

Một đầu ra **minh họa giả định** của `jps -l`:

```text
4120 com.example.orders.OrderApplication
4367 /srv/apps/report-worker.jar
4512 jdk.jcmd/sun.tools.jps.Jps
```

Các số PID/tên trong khối trên chỉ minh họa **dạng thông tin**, không phải bằng chứng máy nào đang chạy. `jps` có thể tự xuất hiện trong danh sách vì bản thân công cụ là một chương trình Java chạy trong JVM.

### 3.2 jps thực sự nhìn thấy cái gì?

Theo tài liệu JDK, `jps` liệt kê **instrumented Java HotSpot VMs** có thể truy cập; nó không phải bộ phát hiện mọi chương trình Java, mọi JVM implementation hay mọi tiến trình OS. Danh sách bị giới hạn bởi các cơ chế khám phá và quyền truy cập của môi trường.

Một số trường hợp không thấy JVM dù process còn tồn tại:

1. **Quyền:** principal đang chạy `jps` không đủ quyền xem JVM của người dùng khác.
2. **Namespace/container:** công cụ ở host hoặc container khác không có cùng phạm vi quan sát/đường dữ liệu instrumentation.
3. **JVM/launcher không tương thích:** JVM không hỗ trợ hay không cung cấp đầy đủ cơ chế mà `jps` cần; launcher tùy biến có thể không công bố main class/JAR.
4. **Vòng đời ngắn:** process đã kết thúc trước khi `jps` quét.
5. **Môi trường chạy tối giản:** không cài `jps`, hoặc JDK tool không phù hợp với runtime/kiến trúc của đích.

Điểm khác biệt có tính nguyên tắc: **`jps` không được định nghĩa như API inventory có độ đầy đủ tuyệt đối**. Tài liệu Oracle còn đánh dấu đây là công cụ experimental/unsupported và khuyến cáo **không viết script phụ thuộc chặt vào định dạng dòng output**, vì định dạng có thể thay đổi.

LVMID **thường** bằng PID OS khi khám phá JVM trên máy cục bộ, nhưng không được mặc định như định luật khi xử lý môi trường remote, custom configuration hoặc implementation khác. Nếu cần tác động vào một PID cụ thể, kiểm tra thêm bằng công cụ OS và thời điểm khởi động.

### 3.3 Tránh rủi ro khi đọc tên và tham số

Lệnh `jps -v` hoặc `-m` có thể lộ giá trị như JVM system properties, key, token hoặc connection string nếu chúng được truyền trên command line. Không đưa raw output chưa lọc vào ticket công khai hay log chia sẻ. Với báo cáo điều tra, chỉ trích các flag cần thiết, ẩn giá trị bí mật và lưu bằng chứng theo quyền truy cập.

Nếu script cần danh sách PID đáng tin cho orchestration, nên dùng API/endpoint chuyên dụng hoặc nguồn từ platform quản lý tiến trình, kết hợp kiểm tra identity. Không parse token thứ hai của `jps` để suy ra tên dịch vụ bất biến.

## 4. Dùng jcmd: từ liệt kê đến hỏi trực tiếp JVM đích

### 4.1 Liệt kê JVM cục bộ

```bash
jcmd
jcmd -l
```

Theo tài liệu JDK, không truyền đối số tương đương `jcmd -l`: hiển thị các JVM process identifier mà cơ chế liệt kê của công cụ nhìn thấy, cùng main class và tham số launcher tương ứng nếu có.

**Lưu ý riêng rất quan trọng với Docker:** tài liệu `jcmd` ghi rõ `-l` không liệt kê JVM đang chạy trong một Docker process riêng biệt theo cách công cụ dò tìm. Khi gặp tình huống ấy, phải dùng nguồn khác, ví dụ `ps` tại đúng namespace hoặc công cụ quản lý container, để xác định PID. **`jcmd -l` không thấy không chứng minh JVM bị tắt.**

Trong môi trường nhiều JVM, cần kiểm tra cả tên class/JAR, command line, host/container, phiên bản runtime và thời gian bắt đầu. Không chọn theo số PID “gần giống” ở lần điều tra trước.

### 4.2 Truy vấn khả năng diagnostic của đúng JVM

Sau khi xác định PID, ví dụ **PID 4242 chỉ để minh họa cú pháp**:

```bash
jcmd 4242 help
jcmd 4242 VM.command_line
jcmd 4242 VM.version
jcmd 4242 VM.flags
jcmd 4242 VM.uptime
```

- `help` liệt kê các diagnostic command mà JVM đích công bố. Có thể dùng `jcmd 4242 help VM.command_line` để xem thông tin về một lệnh cụ thể.
- `VM.command_line` trả thông tin lệnh khởi chạy JVM mà implementation hỗ trợ.
- `VM.version` cho biết phiên bản VM đích; giá trị này có ý nghĩa hơn `java -version` ở một terminal khác nếu cần xác nhận service đang chạy.
- `VM.flags` cho biết những VM flags được JVM báo; cách hiển thị và độ đầy đủ phụ thuộc command/implementation.
- `VM.uptime` đưa thời gian JVM chạy theo nguồn của VM; kết hợp timestamp/identity để tránh đọc nhầm tiến trình đã restart.

Ở bước khám phá, **không cần** lập tức chạy `Thread.print` hay tạo dump. Các lệnh thông tin đơn giản thường nhẹ hơn, trong khi số lệnh khác có chi phí rất khác nhau tùy tải và số đối tượng/thread. Luôn đọc mô tả/impact của command trong `help` và chọn đúng mục tiêu.

Một số diagnostic command khác như `GC.heap_info`, `Thread.print`, `JFR.*` có thể hữu ích **sau khi đã xác định chính xác JVM** và mục đích thu thập. Chúng không thay thế kiểm tra PID, và không phải thành phần bắt buộc của bước discovery.

### 4.3 jcmd có những điều kiện tiên quyết nào?

- Công cụ thường cần chạy **trên cùng máy** với JVM đích và với effective user/group IDs tương ứng theo yêu cầu của implementation được tài liệu hóa; quyền OS và chính sách attach vẫn có hiệu lực.
- JVM cần hỗ trợ diagnostic/attach tương ứng; cấu hình như `-XX:+DisableAttachMechanism` trên HotSpot có thể làm attach không khả dụng.
- Đường nhìn PID phải đúng với môi trường thực thi. Một PID nhìn ở host không được giả định bằng PID trong namespace của container.
- Container image chỉ gồm Java runtime có thể không có `jcmd`. Việc công cụ **không có trong PATH** khác với JVM **không thể được chẩn đoán**.
- Đích có thể thoát, treo hoặc đổi trạng thái giữa lúc xác định PID và lúc attach; lệnh có thể thất bại hoặc timeout tùy công cụ.
- Một diagnostic command có thể không tồn tại ở phiên bản JVM cụ thể. `jcmd PID help` là cách xác nhận hỗ trợ trước khi dùng.

Không kết luận “JVM lỗi” chỉ từ một thông báo attach thất bại. Cần phân biệt *không tìm thấy process*, *không đủ quyền*, *không cùng namespace*, *attach bị vô hiệu*, *tool/runtime không tương thích*, *JVM không phản hồi* và *command không được hỗ trợ*.

### 4.4 Các lệnh có thể tiết lộ dữ liệu nhạy cảm hoặc làm thay đổi trạng thái

`jcmd PID VM.system_properties` có thể in system properties chứa dữ liệu nhạy cảm; `VM.command_line` cũng có thể in tham số khởi chạy có secret. Một số diagnostic command không chỉ đọc: có lệnh thay flags hoặc điều khiển recording/management agent. Vì vậy chỉ chạy **đúng lệnh đọc cần dùng**, xem mô tả trước và tránh dùng `jcmd 0 ...` hoặc nhắm theo main class khi mục tiêu chỉ là một JVM: các cách đó có thể nhắm **nhiều** JVM.

Khi đưa output vào báo cáo, luôn ghi PID, host/container, thời điểm, command đã chạy và bộ lọc/redaction áp dụng. Đừng đưa token, password hay nguyên chuỗi command line không kiểm soát vào kho lưu rộng quyền.

## 5. Dùng ProcessHandle để khám phá tiến trình từ mã Java

`ProcessHandle` (có từ Java 9) thuộc `java.lang`, cho phép thao tác với **native process** theo những khả năng hệ điều hành và quyền cung cấp. Không cần thêm dependency ngoài JDK để dùng API này. ProcessHandle có các phương thức điều khiển tiến trình như `destroy()`, nhưng bài này chỉ sử dụng API **đọc**.

### 5.1 API thường dùng

| API | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `ProcessHandle.current()` | Lấy handle của process Java đang gọi | Chỉ mô tả **tiến trình hiện tại** |
| `ProcessHandle.of(pid)` | Tìm handle theo PID, trả `Optional<ProcessHandle>` | Có thể rỗng khi PID không tồn tại; quyền/OS có thể gây exception |
| `ProcessHandle.allProcesses()` | Trả stream snapshot của những native processes nhìn thấy được | Gồm non-Java processes, không có guarantee toàn bộ host |
| `handle.pid()` | Trả native process ID | PID tái sử dụng; ngữ cảnh namespace quan trọng |
| `handle.info()` | Trả `ProcessHandle.Info` snapshot | Các trường bên trong là `Optional` |
| `handle.parent()` | Tìm parent process, nếu có thể xác định | Có thể rỗng do không có parent hoặc OS limitations |
| `handle.children()` | Snapshot các process con trực tiếp | Process có thể kết thúc/đổi quan hệ ngay sau snapshot |
| `handle.descendants()` | Snapshot con, cháu và các cấp dưới | Không phải cây ổn định qua thời gian |
| `handle.isAlive()` | Kiểm tra trạng thái sống hiện tại | Là ảnh chụp; không bảo đảm process còn sống ở thao tác tiếp theo |
| `handle.onExit()` | Future hoàn thành khi process kết thúc | Hữu ích khi theo dõi vòng đời; **không** là log lịch sử restart |

`allProcesses()` là stream tiến trình OS mà runtime có thể nhìn thấy tại thời điểm chụp; **không tự phân loại Java hay HotSpot**. Tìm tên executable chứa `java` chỉ là heuristic: có thể bỏ sót custom launcher, sai khi đường dẫn bị rút ngắn hoặc chứa tên tương tự.

### 5.2 ProcessHandle.Info cung cấp thông tin nào?

`ProcessHandle.Info` có các accessor chính:

| Trường | Kiểu trả về | Ý nghĩa và giới hạn |
| --- | --- | --- |
| `command()` | `Optional<String>` | Đường dẫn/name executable; có thể thiếu hoặc bị cắt ngắn |
| `commandLine()` | `Optional<String>` | Biểu diễn best-effort của command line; không nhất thiết khôi phục chuẩn quoting/argv |
| `arguments()` | `Optional<String[]>` | Các đối số process nếu OS cung cấp; có thể thiếu, bị đổi hoặc không đầy đủ |
| `startInstant()` | `Optional<Instant>` | Thời điểm process bắt đầu nếu có |
| `totalCpuDuration()` | `Optional<Duration>` | Thời gian CPU tích lũy nếu có; không phải CPU % tức thời |
| `user()` | `Optional<String>` | Tên user mà OS/API cho phép đọc, nếu có |

**Optional rỗng là kết quả bình thường cần xử lý.** Nó không chứng minh giá trị thực tế bằng rỗng, bằng 0 hay bằng “unknown Java”. Trên một số hệ điều hành, `commandLine()` chỉ được tạo từ `command()` và `arguments()` ghép bằng dấu cách; cách biểu diễn đó không thể tái tạo chắc chắn ranh giới argument chứa dấu cách hoặc cách shell đã quote.

Đừng dùng `arguments().get()` khi chưa kiểm tra present; đừng tin rằng tài khoản không đặc quyền có thể lấy owner/command line của mọi process. Với process đã thoát, dữ liệu từng trường có thể đã biến mất.

### 5.3 CPU time và process tree có dễ suy luận không?

`totalCpuDuration()` là **CPU time tích lũy** của process, không phải phần trăm CPU hay thời gian chạy đồng hồ. Muốn ước lượng CPU utilization cần tối thiểu hai mẫu CPU duration và elapsed wall time, định nghĩa cách chuẩn hóa theo số lõi/quota, đồng thời xử lý reset/restart. Hai process có cùng CPU duration không có nghĩa mức tải hiện tại giống nhau.

`children()` và `descendants()` biểu diễn cấu trúc parent-child **ở lúc truy vấn**, không phải tập các request worker thread. Thread của một JVM không xuất hiện như những “Java child processes” trong API này. Nếu ứng dụng gọi `ProcessBuilder` để chạy command ngoài, những command ấy **có thể** là native child processes; còn các thread trong cùng JVM vẫn thuộc một tiến trình.

## 6. Ví dụ Java 17+ chạy độc lập: kiểm tra self, parent, PID tùy chọn và phạm vi nhìn thấy

Lưu đoạn mã sau trong tệp `ProcessDiscoveryDemo.java`. Chương trình **chỉ đọc thông tin**, không kill process, không quét command line để lọc keyword và không đụng tới dữ liệu heap/JVM ngoài tiến trình.

```java
import java.util.stream.Stream;

public class ProcessDiscoveryDemo {
    private static String describe(ProcessHandle process) {
        ProcessHandle.Info info = process.info();
        String command = info.command().orElse("(unavailable)");
        String start = info.startInstant()
                .map(Object::toString)
                .orElse("(unavailable)");
        return "pid=" + process.pid()
                + " alive=" + process.isAlive()
                + " command=" + command
                + " start=" + start;
    }

    public static void main(String[] args) {
        ProcessHandle self = ProcessHandle.current();

        System.out.println("SELF " + describe(self));
        System.out.println("PARENT " + self.parent()
                .map(ProcessDiscoveryDemo::describe)
                .orElse("(unavailable)"));

        try (Stream<ProcessHandle> children = self.children()) {
            System.out.println("DIRECT_CHILDREN_SNAPSHOT=" + children.count());
        }

        try (Stream<ProcessHandle> processes = ProcessHandle.allProcesses()) {
            System.out.println("VISIBLE_OS_PROCESSES_SNAPSHOT=" + processes.count());
        }

        if (args.length > 0) {
            try {
                long requestedPid = Long.parseLong(args[0]);
                if (requestedPid <= 0) {
                    System.out.println("TARGET invalid positive PID required");
                    return;
                }
                String target = ProcessHandle.of(requestedPid)
                        .map(ProcessDiscoveryDemo::describe)
                        .orElse("(not found)");
                System.out.println("TARGET " + target);
            } catch (NumberFormatException ex) {
                System.out.println("TARGET invalid integer PID required");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ProcessDiscoveryDemo.java
java ProcessDiscoveryDemo
java ProcessDiscoveryDemo 4242
```

- Lệnh thứ hai chỉ hỏi tiến trình Java hiện tại, parent, số children tại thời điểm lấy mẫu và số process OS đang nhìn thấy.
- Lệnh cuối thêm truy vấn **PID ví dụ 4242**; số này không khẳng định đang tồn tại. Nếu không có process ấy, dòng `TARGET (not found)` là kết quả hợp lệ, không phải lỗi Java.
- Các giá trị PID, command, start time, parent và số process **phụ thuộc máy, container, thời điểm và quyền**, nên không có stdout số cụ thể cố định. Mọi dòng đều có prefix như `SELF`, `PARENT`, `DIRECT_CHILDREN_SNAPSHOT=`, `VISIBLE_OS_PROCESSES_SNAPSHOT=` và khi có đối số thì `TARGET`.
- Các phép đếm dùng `Stream.count()`; `try-with-resources` bảo đảm stream được đóng đúng cách, dù việc đóng stream ở đây không đồng nghĩa giải phóng một tài nguyên hệ thống nặng.
- `ProcessHandle.of` trả về optional; chương trình không gọi `get()` trên optional rỗng. Nó không tự nhận “mọi Java process” từ `allProcesses()`.

Nếu hệ điều hành, policy hoặc SecurityManager (trên các runtime còn hỗ trợ) cấm thao tác, có thể nhận `SecurityException` hoặc `UnsupportedOperationException`. Đây là ứng dụng đo đơn giản, không tự vượt cơ chế quyền. Nó không thay thế inventory của platform hoặc `jcmd` khi mục tiêu là JVM internals.

### 6.1 Nhìn process khác không có nghĩa đã attach JVM

Một chương trình Java chạy `ProcessHandle.of(4242)` có thể tìm thấy process Python, shell hoặc database bình thường. Điều này chỉ nói process OS có handle khả dụng. **Không thể suy ra process ấy là HotSpot, có heap hoặc nhận được `jcmd`**. Ngược lại, nếu `ProcessHandle.Info.command()` rỗng, process vẫn có thể là JVM mà công cụ jcmd nhận diện.

### 6.2 Dùng PID + startInstant để giảm nguy cơ nhận nhầm

Nếu có `startInstant()`, ghi cả PID lẫn timestamp. Trước và sau khi thu bằng chứng, xác minh cặp danh tính này vẫn phù hợp. Khi timestamp không có, cần đối chiếu thêm container instance, uptime, artifact/build identity và event từ orchestration. Đây là biện pháp giảm nhầm lẫn do PID reuse, **không phải giao thức nguyên tử đảm bảo không có race**: process vẫn có thể kết thúc giữa bước kiểm tra và bước quan sát.

## 7. Quy trình điều tra thực tế: tìm đúng JVM trước khi truy vấn

Một quy trình read-only có thể thực hiện như sau.

### Bước 1 — Xác định môi trường bạn đang đứng

Đang chạy công cụ ở host, VM, container, pod hay development terminal? Ghi namespace PID, quyền account, đường dẫn executable JDK và thời gian. Nếu dự định so nhiều lệnh, bảo đảm chúng chạy cùng phạm vi quan sát hoặc ghi rõ mapping PID.

### Bước 2 — Thu danh sách ứng viên từ nhiều nguồn

Trên môi trường có JDK:

```bash
jps -l
jcmd -l
```

Trên Linux, bổ sung nguồn native process của đúng namespace:

```bash
ps -eo pid,ppid,comm,args
```

Trên Windows, có thể dùng PowerShell `Get-Process` hoặc công cụ OS; không copy lệnh `ps` Linux sang Windows mà coi kết quả tương đương. Một Java service chạy trong container nên được đối chiếu với tên pod/container và process list tương ứng của chính container.

**Không lấy union của các kết quả rồi kết luận tất cả đều là JVM.** `ps` hiển thị process OS, `jps` và `jcmd` có phương pháp phát hiện JVM riêng. Sự khác biệt là dữ kiện về *phạm vi quan sát*, chưa phải dấu hiệu lỗi.

### Bước 3 — Khóa danh tính ứng viên trước khi đào sâu

Ghi PID ở đúng namespace, command/executable nếu có, main class/JAR, start time, service instance, runtime version và owner. Nếu có nhiều bản `report-worker.jar`, dùng instance/container/port/runtime/config để phân biệt thay vì chọn dòng đầu tiên.

### Bước 4 — Thăm dò diagnostic nhẹ, nhắm PID cụ thể

Chỉ khi chắc chắn PID và quyền:

```bash
jcmd 4242 help
jcmd 4242 VM.command_line
jcmd 4242 VM.version
jcmd 4242 VM.uptime
```

PID 4242 chỉ minh họa. Lưu timestamp, stdout/stderr và exit status; che các tham số nhạy cảm trước khi chia sẻ. Nếu không attach được, ghi lỗi thực tế và quay lại kiểm tra quyền/namespace/version/attach support, không đổi đại PID khác.

### Bước 5 — Xác minh điều bạn đã biết và điều còn chưa biết

Sau một vòng discovery, nên trả lời được:

- JVM/process ứng viên nào đang tồn tại và mình nhìn từ host/namespace nào?
- Lệnh nào chứng minh danh tính, phiên bản runtime, launcher và thời gian chạy?
- Trường nào không được cung cấp do `Optional.empty()`, quyền hoặc giới hạn tool?
- Có thể kiểm tra chéo OS process với JVM liveness và orchestration metadata chưa?
- Chỉ số runtime chuyên sâu nào cần thu **tiếp theo** cho giả thuyết điều tra?

Khi một mảnh thông tin thiếu, ghi “không quan sát được bằng phương pháp này” thay vì tự điền giá trị.

## 8. Vì sao kết quả ba công cụ khác nhau?

| Hiện tượng | Giải thích có thể xảy ra | Bước kiểm tra phù hợp |
| --- | --- | --- |
| `ps` thấy Java process, `jps` không thấy | Quyền, instrumentation, namespace, VM implementation, process quá ngắn | Xác định PID/owner/namespace, đối chiếu tool ở đúng môi trường |
| `jcmd -l` không thấy JVM trong Docker | Giới hạn liệt kê Docker process được tài liệu jcmd nêu | Dùng process list của đúng container/host và mapping PID |
| `jps` thấy app nhưng `jcmd PID ...` thất bại | Attach bị chặn, quyền khác, PID đổi, JVM không phản hồi hoặc command không được hỗ trợ | Kiểm tra effective UID/GID, PID/start time, `help`, stderr |
| `ProcessHandle.allProcesses()` thấy rất nhiều dòng hơn `jps` | API liệt kê native processes, cả non-Java | Không dùng count đó làm số JVM |
| `Info.commandLine()` rỗng, `pid()` có giá trị | OS/permission không cung cấp trường command line | Xem `Optional`, dùng nguồn process/launcher hợp lệ khác |
| `Info.command()` chỉ thấy `java` | Đây là executable, không nhất thiết là tên app | Đối chiếu JAR/main class, container metadata và jcmd |
| `jps -l` hiện `Unknown` | Custom launcher/JVM không báo được entry point | Xác minh bằng VM command line hoặc runtime metadata, nếu có |
| `ProcessHandle.of(pid)` rỗng sau khi `jps` vừa in PID | Process đã kết thúc, namespace khác hoặc lookup không thấy | Đọc mốc thời gian, kiểm tra lại danh tính/sự kiện |
| Hai lần chạy báo cùng PID nhưng runtime khác | PID đã tái sử dụng sau restart | Kèm startInstant/uptime và instance ID khi lưu bằng chứng |

Bảng là **các giả thuyết để kiểm tra**, không phải chẩn đoán chắc chắn. Một trường hợp có thể có nhiều nguyên nhân đồng thời.

## 9. Bốn giới hạn quan trọng cần hiểu sâu

### 9.1 Giới hạn quyền và phạm vi quan sát

Dù có quyền chạy một chương trình Java, người dùng hiện tại không nhất thiết có quyền đọc các tiến trình của tài khoản khác. Hệ điều hành, container runtime, namespace, sandbox, security policy và cấu hình JVM đều tham gia quyết định.

Một quy trình kiểm tra an toàn:

1. Ghi process owner và account thực thi lệnh công cụ.
2. Xác nhận cùng host/namespace và có đường đi phù hợp tới process đích.
3. Xem stderr và mã thoát thay vì chỉ đếm số dòng stdout.
4. Chỉ nâng quyền qua quy trình vận hành đã được phép; không mặc định chạy mọi công cụ bằng root.

Đặc biệt, `jcmd` không phải một giao thức giám sát từ xa tổng quát. Tài liệu của nó yêu cầu thao tác trên cùng máy và quyền tương ứng để gửi command. `jps` có thể mô tả tùy chọn host identifier trong môi trường dùng `jstatd`, nhưng điều đó **không biến mọi JVM từ xa thành mục tiêu có thể truy vấn mặc định**.

### 9.2 Giới hạn container và PID namespace

Khi một JVM là PID 1 bên trong container, trên host nó có thể có PID khác. Nếu chạy `ProcessHandle.current()` bên trong, `pid()` phản ánh view của process đó. Gửi PID bên trong vào `jcmd` đang chạy ngoài container có thể nhắm sai process hoặc thất bại. Ngoài PID, khác filesystem namespace và user mapping cũng có thể làm attach gặp vấn đề.

Tài liệu `jcmd -l` nêu hạn chế với JVM trong Docker process riêng biệt. Vì thế, một checklist thực tế là ghi **tool chạy ở đâu, target chạy ở đâu, PID lấy từ namespace nào và có mapping nào hợp lệ**. Không đổi/chỉnh namespace chỉ vì thiếu output mà chưa xác định phạm vi.

### 9.3 Giới hạn thông tin và tính nhạy cảm

`jps` có thể trả tên ngắn, tên dài hoặc `Unknown`. `ProcessHandle.Info` có thể trả Optional rỗng và command line không giữ nguyên cách trích dẫn đối số. `jcmd VM.command_line` có thể cho góc nhìn JVM rõ hơn nhưng chỉ khi attach được.

Command line và system properties có thể chứa password, API key hoặc đường dẫn nội bộ. **Đầy đủ hơn không luôn là an toàn hơn**: nội dung báo cáo chỉ cần trường phù hợp để xác định tiến trình. Không ghi raw output nhạy cảm vào bảng công khai; nếu cần dữ liệu chi tiết hãy lưu ở chỗ có quyền truy cập hạn chế và quy tắc redaction rõ ràng.

### 9.4 Giới hạn thời điểm và tính nhất quán

`jps` lúc T1, `jcmd` lúc T2 và `ProcessHandle.info()` lúc T3 không phải một snapshot nguyên tử. Giữa T1–T3 có thể có restart, PID reuse, đổi parent hoặc kết thúc process. Vì vậy, timestamp của evidence và thông tin start/uptime có giá trị kiểm chứng.

Các trường `isAlive`, `parent`, `children` hoặc `descendants` phản ánh quan sát gần thời điểm gọi; không bảo đảm tính đồng thời tuyệt đối. Không viết automation kiểu “nếu `isAlive()` đúng thì mọi command tiếp theo chắc chắn thành công”.

## 10. Những kết luận không được suy ra từ mỗi công cụ

- **Thấy PID trong `jps` ⇒ không có nghĩa JVM khỏe.** Process tồn tại có thể đang deadlock, bị nghẽn CPU hoặc không phục vụ request.
- **Không thấy PID trong `jcmd -l` ⇒ không có nghĩa JVM tắt.** Có giới hạn phát hiện, đặc biệt trong môi trường Docker riêng.
- **`jps -v` có vài flags ⇒ không có nghĩa đã biết toàn bộ effective JVM configuration.** Còn runtime ergonomics, flags tự chọn và nguồn cấu hình khác; cần kiểm tra theo JVM thực tế.
- **`ProcessHandle.Info.totalCpuDuration()` lớn ⇒ không có nghĩa CPU hiện đang cao.** Đây là tích lũy; cần hai điểm đo theo thời gian, so quota/cpu count để tính rate.
- **`ProcessHandle.allProcesses().count()` ⇒ không phải số Java process hoặc thread.** Nó đếm native processes nhìn thấy; nhiều Java threads vẫn thuộc một PID.
- **`Info.commandLine()` có chuỗi “java” ⇒ không chứng minh tiến trình đang chứa JVM tương thích `jcmd`.** Một process/script/native launcher có thể mang tên hoặc argument tương tự.
- **`Info.startInstant()` rỗng ⇒ không phải start time bằng epoch.** Đó là không có thông tin qua API.
- **PID giống nhau qua hai lần đo ⇒ không chắc là cùng instance.** Cần liên hệ start/uptime và nhận dạng workload.
- **`jcmd PID help` thành công ⇒ không bảo đảm mọi diagnostic command đều được hỗ trợ hoặc có chi phí bằng nhau.** Mỗi command có hỗ trợ và impact riêng.

## 11. Bài tập ứng dụng

### Bài tập A — Xem tiến trình của chính mình

1. Biên dịch `ProcessDiscoveryDemo.java` bằng JDK 17+.
2. Chạy `java ProcessDiscoveryDemo` và ghi PID, parent, start time, command và số process OS nhìn thấy.
3. Khi JVM demo đang chạy, dùng `jps -l` và `jcmd -l` trên cùng máy/namespace, nếu các tool tồn tại, để tìm nó. Vì demo chạy rất nhanh, có thể nó đã kết thúc trước khi bạn gõ lệnh; **đó chính là giới hạn thời điểm**, không phải bằng chứng công cụ hỏng. Muốn quan sát một JVM lâu hơn, dùng một service hợp lệ đang chạy lâu hoặc một quy trình thực nghiệm riêng có kiểm soát.
4. Ghi lại kết quả nào thực sự quan sát được và kết quả nào không thể đối chiếu vì process đã thoát.

### Bài tập B — Trường hợp production nhiều JVM

Giả định host hiển thị ba Java processes: một API service, một batch worker và một build daemon. Nhiệm vụ là định danh đúng API service mà **không** thu dump hay thay đổi trạng thái:

1. Dùng tên workload/host/container đã biết để giới hạn ứng viên.
2. Lấy danh sách `jps -l`, `jcmd -l` và native process list của phạm vi phù hợp.
3. Đối chiếu PID, entry point, command, runtime version, start/uptime và instance identity.
4. Nếu `jcmd -l` thiếu một process, ghi giới hạn quan sát rồi tiếp tục bằng nguồn OS/container, không bỏ qua process chỉ vì thiếu dòng.
5. Sau khi xác minh, mới chạy một command read-only nhẹ theo PID cụ thể và lưu thời gian cùng output đã làm sạch.

Bản ghi kết quả nên có dạng:

```text
Quan sát: service, host/container, timestamp, PID scope
Nguồn: jps / jcmd / ProcessHandle / OS tool
Đã xác minh: PID, runtime/launcher, start time hoặc uptime
Chưa xác minh: trường Optional rỗng, quyền thiếu, namespace chưa map
Giới hạn: dữ liệu chỉ là snapshot; process có thể restart
Hành động tiếp: command đọc cụ thể nếu có căn cứ
```

Đây là **cấu trúc báo cáo**, không phải output của lệnh; nó giúp phân biệt bằng chứng và suy đoán.

## 12. Checklist trước khi tuyên bố “đã tìm đúng JVM”

- [ ] Đã ghi đúng máy/VM/container, user và namespace thực thi công cụ.
- [ ] Đã biết nguồn cung cấp PID là OS, `jps` LVMID hay namespace bên trong container.
- [ ] Đã đối chiếu tên service/main class/JAR với workload thực và bản build nếu có.
- [ ] Đã kiểm tra phiên bản JVM đang chạy thay vì chỉ `java -version` của shell khác.
- [ ] Đã thu start time/uptime hoặc metadata tương đương để giảm nhầm PID reuse.
- [ ] Đã ghi rõ command nào nhìn thấy hoặc không nhìn thấy process và nguyên nhân **đã kiểm chứng**.
- [ ] Đã xử lý `Optional.empty()` và command line có thể bị rút gọn/sai quoting.
- [ ] Đã cân nhắc attach permission, container boundary và lệnh jcmd hỗ trợ.
- [ ] Chỉ dùng thao tác read-only phù hợp mục tiêu, tránh scan/heap dump không cần thiết.
- [ ] Mọi output chia sẻ đều đã rà soát dữ liệu nhạy cảm.
- [ ] Kết luận có timestamp, scope và giới hạn quan sát; không coi snapshot là lịch sử.

## Tài liệu tra cứu

- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cú pháp liệt kê, điều kiện gửi diagnostic command, các lệnh và impact.
- [Oracle JDK 21 — jps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html): JVM instrumented, các tùy chọn `-l`/`-m`/`-v`, LVMID, lưu ý định dạng output.
- [Java SE 21 API — ProcessHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html): snapshot, process identity, parent/children, liveness và quyền.
- [Java SE 21 API — ProcessHandle.Info](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html): command, arguments, start time, total CPU duration và tính tùy chọn của dữ liệu.

**Ghi nhớ:** `jps` giúp phát hiện những JVM mà cơ chế instrumentation nhìn thấy; `jcmd` cho phép hỏi một JVM cụ thể khi có quyền và attach được; `ProcessHandle` cho góc nhìn **native process** của OS từ Java. Ba nguồn có phạm vi khác nhau. Chẩn đoán đáng tin phải xác minh đúng PID/namespace/instance và hiểu rằng dữ liệu có thể thiếu, thay đổi theo thời điểm hoặc bị giới hạn bởi quyền.