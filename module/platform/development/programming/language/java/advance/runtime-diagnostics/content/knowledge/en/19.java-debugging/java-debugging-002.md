# 19.2. Vai trò của JDWP, JDI và jdb trong kiến trúc debugging Java

Khi đặt breakpoint trong IntelliJ IDEA, Eclipse hoặc gõ lệnh bằng `jdb`, chúng ta đang điều khiển **một JVM khác** để dừng luồng, xem call stack, đọc biến và tiếp tục chạy chương trình. Phần giao diện debugger nhìn thấy chỉ là lớp trên cùng. Bên dưới là Java Platform Debugger Architecture (**JPDA**) — kiến trúc chia trách nhiệm thành giao diện lập trình, giao thức truyền thông và dịch vụ của JVM.

Ba tên rất dễ nhầm:

- **JDWP — Java Debug Wire Protocol:** giao thức trao đổi yêu cầu và sự kiện giữa debugger và JVM được debug.
- **JDI — Java Debug Interface:** API Java cấp cao để *viết debugger* hoặc công cụ điều tra từ phía debugger.
- **jdb — Java Debugger:** chương trình dòng lệnh đi kèm JDK, **sử dụng JDI**, để debug ứng dụng Java.

Một thành phần liên quan cần biết là **JVM TI — Java Virtual Machine Tool Interface**. Đây là giao diện native ở phía JVM cho công cụ chẩn đoán/debugging. Trong triển khai JPDA tham chiếu của HotSpot, **JDWP agent** dùng JVM TI để thực hiện các yêu cầu được chuyển từ debugger. Nhờ phân lớp, người dùng `jdb` không phải tự đóng gói packet JDWP, còn người viết công cụ JDI không phải gọi trực tiếp API native JVM TI.

Mục tiêu bài: giải thích được sơ đồ và luồng yêu cầu/sự kiện JPDA, phân biệt giao thức với API và công cụ CLI, tự mở một phiên `jdb` trên Java 17+, biết nơi đặt `-agentlib:jdwp`, thực hiện breakpoint/step/inspect, nhận diện lỗi kết nối và bảo vệ cổng debug.

## 1. Sơ đồ kiến trúc JPDA từ debugger đến JVM

~~~text
   MÁY / TIẾN TRÌNH DEBUGGER                      MÁY / TIẾN TRÌNH DEBUGGEE
   (front-end)                                    (back-end + ứng dụng)

  +----------------------------+                 +----------------------------+
  | jdb / IDE / custom tool    |                 | Ứng dụng Java              |
  | Giao diện, breakpoint UI   |                 | Thread, object, stack      |
  +-------------+--------------+                 +--------------+-------------+
                |                                                 ^
                | Gọi JDI API                                     | dịch vụ debug
                v                                                 | từ JVM TI
  +----------------------------+                 +--------------+-------------+
  | JDI implementation         |                 | JVM + JVM TI               |
  | com.sun.jdi.*              |                 | Debuggee runtime           |
  | Connectors, mirrors,       |                 +--------------+-------------+
  | event requests/queues      |                                ^
  +-------------+--------------+                                |
                |                                                | JVM TI calls / events
                v                                                |
  +----------------------------+                 +--------------+-------------+
  | JDWP front-end             | <-- JDWP -->    | JDWP agent / back-end      |
  | Serialize / decode packet  |   over socket   | Decode packet, query VM    |
  +----------------------------+                 +----------------------------+
             <---------------------- transport -------------------->
                      dt_socket (TCP) hoặc transport được hỗ trợ
~~~

Sơ đồ là mô hình **triển khai tham chiếu điển hình**: thành phần cụ thể có thể khác ở các JVM/IDE. Điều ổn định để hiểu là **debugger đặt câu hỏi và điều khiển trạng thái**, còn JVM đích cung cấp thông tin/thi hành điều khiển. JDWP quy định dữ liệu trao đổi qua kênh truyền; `dt_socket` là **transport TCP**, không phải tên gọi khác của JDWP.

Trong JPDA:

1. **Debugger front-end** nhận thao tác của người dùng: đặt breakpoint, xem giá trị biến, bước qua dòng lệnh.
2. **JDI** cho phép mã Java ở debugger biểu diễn JVM, thread, stack frame, class, field và event như những object/mirror.
3. **JDWP** biểu diễn các yêu cầu, phản hồi và thông báo sự kiện thành message truyền qua kết nối.
4. **JDWP back-end/agent** chạy trong tiến trình debuggee nhận message, phối hợp với JVM TI để truy xuất hoặc thay đổi trạng thái thực thi.
5. JVM có thể phát sinh sự kiện breakpoint/exception/thread-start; agent chuyển chúng ngược qua JDWP, JDI đưa về debugger qua `EventQueue`.

**JPDA không phải một chương trình riêng**, còn `jdb` không phải một tầng của đặc tả protocol. `jdb` là **một ứng dụng debugger cụ thể** được xây trên API JDI.

## 2. Bảng phân biệt JDWP, JDI, jdb và JVM TI

| Thành phần | Bản chất | Ở phía nào? | Ai dùng? | Nó giải quyết vấn đề gì? |
| --- | --- | --- | --- | --- |
| **JDWP** | Đặc tả *wire protocol*, gồm các command/reply/event packet | Giữa debugger và JVM đích | Implementations của debugger và agent | Hai tiến trình nói chuyện debug với nhau theo định dạng thống nhất |
| **JDI** | API Java cấp cao trong module `jdk.jdi`, packages `com.sun.jdi.*` | Chủ yếu ở debugger/front-end | `jdb`, IDE hoặc custom debugger Java | Viết code attach/launch, đọc state, đặt event request, nhận event mà không viết packet tay |
| **jdb** | Công cụ dòng lệnh trong JDK | Tiến trình debugger | Lập trình viên, vận hành, người học | Debug trực tiếp bằng lệnh: attach, breakpoint, step, print, where |
| **JVM TI** | Native tool interface (C/C++) | Trong/tiếp xúc JVM đích | Native agents, JDWP back-end của HotSpot | Lấy trạng thái VM, hook vào runtime, nhận sự kiện ở mức VM |

Vì vậy:

- Gõ `jdb -attach 5005` là **khởi chạy một debugger CLI**, dùng **JDI connector** để kết nối và dùng **JDWP** truyền lệnh tới **agent**.
- Viết `VirtualMachine vm = connector.attach(...)` trong Java là **sử dụng JDI**, nhưng vẫn có thể nói chuyện với agent qua JDWP.
- Cấu hình `-agentlib:jdwp=...` là **bật debug agent phía debuggee**, không phải “bật JDI trên server”.
- `dt_socket` hoặc `dt_shmem` là **phương thức vận chuyển**, không phải một lớp debugger hay câu lệnh của Java.
- `JMX`, `jcmd` và **JFR** là các cơ chế quản lý/chẩn đoán khác; chúng không đồng nghĩa với phiên debug JPDA. Một tiến trình có JMX hoặc JFR không có nghĩa tự nhiên đã mở JDWP.

## 3. JDWP: hợp đồng trao đổi trên đường truyền

JDWP định nghĩa định dạng packet mang:

- **Command** từ debugger, ví dụ yêu cầu lấy giá trị biến cục bộ, danh sách thread, thiết lập breakpoint.
- **Reply** từ JVM, gồm dữ liệu hoặc mã lỗi phản hồi yêu cầu.
- **Event** gửi từ JVM về debugger, ví dụ breakpoint hit, exception, VM start/death và thread events khi được đăng ký.

JDWP **không quy định debugger phải vẽ giao diện thế nào**. IDE có thể tạo cửa sổ Variables/Threads, còn `jdb` in text; cả hai vẫn có thể nói chuyện với cùng kiểu JDWP agent. Tương tự, JDWP **không buộc chỉ được dùng TCP**: vận chuyển trong reference implementation có `dt_socket`; `dt_shmem` là shared-memory transport trên Windows, và cấu trúc JPDA cho phép những transport khác.

Ví dụ luồng khi người dùng muốn xem giá trị `int a` trong một stack frame đã bị dừng:

~~~text
Người dùng chọn biến a
  -> jdb / IDE gọi JDI: StackFrame.getValue(LocalVariable)
  -> JDI front-end mã hóa JDWP request GetValues
  -> TCP socket (dt_socket) chuyển request
  -> JDWP back-end trong JVM đích giải mã
  -> JVM TI / JVM cung cấp giá trị của slot ở frame
  -> JDWP reply mang kết quả về debugger
  -> JDI tạo Value mirror
  -> UI/jdb hiển thị số nguyên
~~~

**Breakpoint đi chiều ngược lại khi đã được thiết lập:** VM chạy tới vị trí có breakpoint, JVM TI báo cho back-end, JDWP agent gửi event về, JDI chuyển thành `BreakpointEvent` cho event queue, và công cụ debugger xử lý event, hiển thị call stack rồi chờ người dùng.

JDWP là giao thức *debugging có quyền cao*: sau khi kết nối thành công, debugger có thể quan sát và tác động mạnh tới trạng thái JVM, bao gồm pause/resume, field/method operations nếu VM hỗ trợ. **Không coi JDWP socket là endpoint HTTP/REST, kênh log hoặc service công khai**. Trong cấu hình socket thông dụng không có cơ chế đăng nhập ứng dụng như một API nghiệp vụ; không mở port ra mạng không tin cậy.

## 4. JDI: API cho người xây debugger, không phải công cụ CLI

**Java Debug Interface (JDI)** là tập interface Java trong module `jdk.jdi`, package chính `com.sun.jdi` cùng `com.sun.jdi.connect`, `com.sun.jdi.request`, `com.sun.jdi.event`. Ví dụ các loại API:

| Nhóm API | Vai trò |
| --- | --- |
| `Bootstrap.virtualMachineManager()` | Điểm khởi đầu lấy `VirtualMachineManager` |
| `AttachingConnector` / `LaunchingConnector` / `ListeningConnector` | Kết nối JVM đang chạy, khởi tạo JVM mới, hoặc chờ JVM kết nối |
| `VirtualMachine` | “Mirror” JVM đích, truy vấn class, threads, capabilities, resume/dispose |
| `ReferenceType` / `Method` / `Field` / `Location` | Mô tả loại/class, phương thức, field, vị trí bytecode/source |
| `ThreadReference` / `StackFrame` / `LocalVariable` / `Value` | Truy cập luồng, stack frame và giá trị tại điểm suspend thích hợp |
| `EventRequestManager` / `BreakpointRequest` / `ExceptionRequest` | Đăng ký điều kiện cần JVM thông báo |
| `EventQueue` / `EventSet` / `BreakpointEvent` | Nhận các event và quản lý suspend/resume sau khi xử lý |

Một debugger Java điển hình:

1. Tìm JDI connector phù hợp, ví dụ `com.sun.jdi.SocketAttach`.
2. Cung cấp `hostname`, `port`, timeout theo yêu cầu connector, rồi `attach` tới JVM đích.
3. Tìm các `ReferenceType` đã nạp hoặc đợi class-prepare event, xác định `Location` cần đặt breakpoint.
4. Tạo `BreakpointRequest` từ `EventRequestManager`, cấu hình suspend policy/filter, rồi `enable()`.
5. Tiếp tục VM, chờ `EventQueue.remove()`. Khi nhận `BreakpointEvent`, xem `ThreadReference`, `StackFrame`, locals rồi xử lý event set.
6. Resume event/VM đúng lúc và `dispose()` khi hoàn tất.

Đây là **luồng triển khai** chứ không phải ví dụ chạy độc lập; ở phần 8 có một chương trình JDI thực tế để kiểm tra kết nối và truy vấn JVM. Một debugger production còn phải xử lý `VMDisconnectEvent`, `VMDeathEvent`, class loading, timeout, nhiều thread, disconnect bất ngờ và quyền truy cập. Không được giữ toàn bộ VM suspended vô hạn vì có thể gây treo dịch vụ.

### JDI “mirror” là gì?

`VirtualMachine`, `ObjectReference` hoặc `ThreadReference` ở debugger **không phải bản sao đầy đủ mọi Java object từ heap**. Chúng là đối tượng đại diện cho thực thể trong JVM đích, cho phép truy vấn/thao tác qua backend. Nhiều thao tác có chi phí trao đổi thông tin và có thể thất bại khi VM disconnect hoặc object không còn hợp lệ. Đọc hàng triệu object qua JDI không phải cách thay thế heap dump để đo retained size.

## 5. jdb: công cụ kiểm chứng và học kiến trúc nhanh nhất

`jdb` là debugger dòng lệnh do JDK cung cấp, dựa trên JDI. Bạn không cần tự viết một frontend để thử:

- Launch hoặc attach tới một JVM.
- Đặt breakpoint ở phương thức/dòng.
- Tiến từng bước `step` hoặc `next`.
- Xem stack, locals và biểu thức đơn giản.
- Theo dõi exception và tiếp tục chạy.

Các nhóm lệnh cơ bản (cú pháp cụ thể kiểm tra bằng `help` trên bản `jdb` đang sử dụng):

| Lệnh `jdb` | Tác dụng |
| --- | --- |
| `jdb MainClass` | jdb **tạo một JVM mới** để chạy class cần debug |
| `jdb -attach 127.0.0.1:5005` | Attach qua socket tới JVM đang chạy **có JDWP agent phù hợp** |
| `jdb -listconnectors` | Liệt kê các cách kết nối JDI được cung cấp |
| `stop in MyClass.method` | Đặt breakpoint đầu phương thức |
| `stop at MyClass:42` | Đặt breakpoint ở dòng 42, khi source mapping khả dụng |
| `stop` / `clear` | Xem, dỡ hoặc quản lý breakpoint theo cú pháp lệnh |
| `cont` | Tiếp tục chạy sau khi bị dừng |
| `step` | Đi tới dòng tiếp theo, có thể bước vào lời gọi |
| `next` | Đi tới dòng tiếp theo trong frame hiện tại, thường bỏ qua chi tiết bên trong lời gọi |
| `where` | Hiển thị call stack của thread đang chọn |
| `locals` | Hiển thị local variables nếu class có debug metadata |
| `print variable` | Xem giá trị biến/biểu thức jdb hỗ trợ |
| `threads` | Xem thread đang được debugger theo dõi |
| `catch ExceptionClass` | Yêu cầu dừng khi exception thuộc class chỉ định được ném |

Lưu ý: `jdb -attach 5005` dùng **socket port**, không phải PID. Cần phân biệt `jcmd <PID> ...` dùng PID JVM với `jdb -attach <address>` dùng địa chỉ debugger. Việc `jdb` có thể attach qua socket **không** có nghĩa mọi tiến trình Java bất kỳ sẽ chấp nhận attach khi chưa cấu hình agent hoặc phương án connector tương ứng.

## 6. Bật JDWP trên JVM cần debug

Cách điển hình với **HotSpot JDK 17+/21**, chỉ bind localhost để luyện tập:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebugArchitectureDemo
~~~

Giải thích từng phần:

| Option | Ý nghĩa | Điểm dễ nhầm |
| --- | --- | --- |
| `-agentlib:jdwp` | Nạp JDWP agent trong **JVM đích** | Không phải nạp JDI vào ứng dụng |
| `transport=dt_socket` | Kết nối TCP/IP | JDWP vẫn là protocol bên trên transport |
| `server=y` | JVM đích **listen** để debugger connect vào | “Server” là **vai trò kết nối**, không phải HTTP server |
| `suspend=y` | JVM dừng trước khi main chạy, chờ debugger kết nối/resume | Với dịch vụ, có thể trông như khởi động treo |
| `suspend=n` | JVM chạy ngay, debugger có thể attach sau | Có thể bỏ lỡ lỗi diễn ra rất sớm |
| `address=127.0.0.1:5005` | Bind port 5005 trên loopback | `address=*:5005` nghe mọi interface, có rủi ro bảo mật lớn |

`server=n` có nghĩa **JVM chủ động kết nối tới debugger đang listen**. Đó là một chế độ kết nối hợp lệ của JPDA, nhưng không dùng trong lab ở đây. Trên Windows, HotSpot còn có `dt_shmem` cho debugging cùng máy; ví dụ xuyên nền tảng trong bài ưu tiên `dt_socket`.

Để attach vào JVM trên máy khác, đừng mở bừa debug port ra Internet. Ưu tiên cơ chế truy cập được kiểm soát, ví dụ SSH tunnel tới **loopback trên host đích**:

~~~bash
ssh -L 5005:127.0.0.1:5005 user@debug-host
~~~

Sau khi kênh an toàn đã thiết lập và chính sách truy cập cho phép, debugger phía local kết nối `127.0.0.1:5005`. Nếu JVM chạy trong container/Kubernetes, loopback của host và loopback của container **khác namespace mạng**; cần bố trí tunnel/forward theo đúng topology, không đổi sang `*:5005` chỉ vì kết nối chưa tới được.

**Không bật JDWP trong production theo mặc định.** Debugging có thể làm dừng application threads, lộ secrets trong biến và tạo quyền điều khiển sâu với JVM. Phải có phê duyệt, giới hạn thời gian, cổng chỉ reachable từ nơi đáng tin, và đóng/debug agent theo quy trình vận hành.

## 7. Lab Java 17+: quan sát JDWP → JDI → jdb thật

### Bước 1 — chương trình đích độc lập

Tạo file **`DebugArchitectureDemo.java`**:

~~~java
public final class DebugArchitectureDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Press Enter to compute");
        System.in.read(); // Giữ JVM sống để chủ động chọn thời điểm breakpoint.

        int result = multiply(6, 7);
        System.out.println("Result=" + result);
    }

    private static int multiply(int a, int b) {
        int product = a * b;
        return product;
    }
}
~~~

Biên dịch với **debug information đầy đủ**:

~~~bash
javac -g DebugArchitectureDemo.java
~~~

`-g` yêu cầu javac ghi line numbers, source information và local-variable table cần cho các thao tác `locals`/`stop at`. Không cần JDI import trong **ứng dụng đích**; chương trình chỉ chạy Java bình thường và **JDWP agent** được nạp bởi tùy chọn khởi động JVM.

### Bước 2 — khởi động JVM ở terminal A

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebugArchitectureDemo
~~~

Khi `suspend=y`, JVM đợi debugger trước khi vào `main`. Agent có thể in thông báo dạng “Listening for transport dt_socket at address: 5005”; đó là **thông báo runtime/agent** chứ không phải stdout của class. Chương trình **chưa in** dòng `Press Enter to compute`.

### Bước 3 — attach bằng `jdb` ở terminal B

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Ở prompt của `jdb`:

~~~text
stop in DebugArchitectureDemo.multiply
cont
~~~

Breakpoint có thể hiển thị trạng thái **deferred** nếu class `DebugArchitectureDemo` chưa được load; debugger sẽ xử lý khi class chuẩn bị được nạp. `cont` cho chương trình tiếp tục.

Ở terminal A, ứng dụng in:

~~~text
PID=<số PID thực tế>
Press Enter to compute
~~~

Nhấn **Enter trong terminal A** để `main` gọi `multiply(6,7)`. Vì breakpoint đã đặt trước lời gọi, JVM dừng tại đầu phương thức. Quay lại terminal B dùng:

~~~text
where
locals
print a
print b
next
locals
cont
~~~

Kỳ vọng `print a` và `print b` phản ánh giá trị **6** và **7** khi debugger đang đứng trong frame `multiply`. Sau `next`, debugger có thể tới dòng `return`; `locals` có thể thấy `product=42` khi đã chạy phép nhân. Đầu ra chính xác của prompt, vị trí dòng, thread ID và trạng thái breakpoint là **động theo JDK và thời điểm**, không được xem là chuỗi cố định.

Khi `cont` thực thi nốt chương trình, terminal A in:

~~~text
Result=42
~~~

Đây là **stdout xác định** của chương trình nếu không có ai chỉnh sửa trạng thái biến và tiến trình hoàn tất bình thường.

### Điều bạn vừa quan sát

- `jdb` = giao diện CLI và logic debugger.
- Lệnh `stop in` / `print` được công cụ chuyển thành thao tác **JDI**.
- **JDI implementation** chuyển yêu cầu qua các message **JDWP** tới debug agent.
- Agent trong JVM đích phản hồi thông tin stack/biến và thông báo breakpoint.
- `-agentlib:jdwp` làm JVM đích có khả năng kết nối với debugger ngay từ khởi động.

Nếu chưa có metadata local-variable table hoặc chạy nhầm build class, `locals` có thể thiếu thông tin; soát `javac -g` và classpath trước khi nghi kết nối sai.

## 8. Lab thứ hai: viết JDI client tối thiểu bằng Java 17+

`jdb` phù hợp để học thao tác bằng tay; còn **JDI API** cho phép viết debugger hoặc công cụ quan sát chuyên biệt. Đoạn này xây **chương trình độc lập** chỉ attach rồi đọc metadata JVM và số thread, sau đó disconnect. Nó **không** đặt breakpoint hay thay thế một debugger hoàn chỉnh.

Tạo file **`JdiProbe.java`**:

~~~java
import com.sun.jdi.Bootstrap;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.AttachingConnector;
import com.sun.jdi.connect.Connector;
import java.util.Map;

public final class JdiProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java JdiProbe <host> <port>");
            return;
        }

        AttachingConnector socket = Bootstrap.virtualMachineManager()
                .attachingConnectors()
                .stream()
                .filter(c -> c.name().equals("com.sun.jdi.SocketAttach"))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("SocketAttach unavailable"));

        Map<String, Connector.Argument> options = socket.defaultArguments();
        options.get("hostname").setValue(args[0]);
        options.get("port").setValue(args[1]);

        VirtualMachine target = socket.attach(options);
        try {
            System.out.println("Target VM=" + target.name());
            System.out.println("Target version=" + target.version());
            System.out.println("Threads visible=" + target.allThreads().size());
        } finally {
            // Chỉ ngắt phiên debugger này; không phải lệnh tắt JVM đích.
            target.dispose();
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --add-modules jdk.jdi JdiProbe.java
~~~

**Dừng phiên `jdb` trước đó** rồi khởi chạy lại chương trình đích trong terminal A với `suspend=n` (để main chạy và chờ bạn nhấn Enter):

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DebugArchitectureDemo
~~~

Đừng nhấn Enter khi mới thấy `Press Enter to compute`. Trong terminal B:

~~~bash
java --add-modules jdk.jdi JdiProbe 127.0.0.1 5005
~~~

Ví dụ dạng kết quả (giá trị **phụ thuộc phiên bản và JVM đích**):

~~~text
Target VM=<tên JVM đích>
Target version=<chuỗi phiên bản JVM đích>
Threads visible=<số nguyên hiện tại>
~~~

Ba giá trị trên không được giả định là cố định. Sau khi `JdiProbe` kết thúc và đã gọi `dispose()`, JVM đích vẫn chờ bạn nhấn Enter. Khi nhấn Enter ở terminal A, nó in `Result=42` rồi kết thúc. Đây là minh chứng rằng một **JDI client do bạn viết** và `jdb` có thể dùng cùng một kiểu **JDWP socket endpoint**, dù UI và chức năng của hai chương trình khác nhau.

### Vì sao ví dụ dùng `jdk.jdi`?

Từ hệ module Java, các package `com.sun.jdi.*` nằm trong **module `jdk.jdi`**. Tên package có tiền tố `com.sun` không đồng nghĩa code bạn tự viết đang nạp một native agent vào JVM đích; đây là API **phía debugger**, được JDK cung cấp. Các JDI connector có thể thay đổi theo runtime/vendor; chương trình kiểm tra `SocketAttach` tồn tại rồi mới dùng, thay vì giả định luôn có trên mọi JVM.

Trong code thật, cũng nên kiểm tra `options.get("hostname")`/`get("port")` không null, đặt timeout và xử lý `VMDisconnectedException`, `IOException`/`IllegalConnectorArgumentsException` phù hợp. Demo sử dụng reference connector chuẩn để tập trung vào vai trò JDI.

## 9. Các phương thức kết nối: launch, attach, listen

| Tình huống | JVM đích | Debugger/JDI | Đặc điểm |
| --- | --- | --- | --- |
| **Launch từ debugger** | Do debugger khởi động | `LaunchingConnector`; `jdb MainClass` | Thuận tiện debug từ đầu chương trình; debugger kiểm soát launch/options |
| **Attach tới JVM có debug agent** | `server=y`, listen trên `dt_socket` | `AttachingConnector`; `jdb -attach host:port` | Dùng khi tiến trình được khởi động với cấu hình debug |
| **JVM chủ động connect tới debugger** | `server=n`, biết debugger address | `ListeningConnector`; `jdb -listen` hoặc cấu hình connector | Hữu ích trong một số topology nhưng cần bố trí mạng và quyền phù hợp |

Những chế độ này là **cách thiết lập kết nối**. Sau khi kết nối ổn định, JDWP requests/replies và cách debugger dùng JDI vẫn cùng bản chất. Đặc biệt:

- `server=y` trong agent nghĩa **JVM chờ debugger**, không liên quan “ứng dụng của bạn là web server hay command-line program”.
- `suspend=y` nghĩa JVM **chờ resume**, không phải “đặt breakpoint ở mọi dòng”.
- `jdb -attach` không nhận PID thông thường trong ví dụ socket, mà nhận địa chỉ kết nối.
- Cổng debug có thể đang **được sử dụng bởi một debugger khác** hoặc bị firewall ngăn; không kết luận do code Java sai nếu chưa kiểm tra socket.

## 10. Request và event: hai chiều không thể thiếu

Chỉ hiểu “debugger gửi lệnh” là chưa đủ. JPDA còn yêu cầu JVM chủ động báo sự kiện:

**Request flow (debugger → JVM):**

~~~text
User: "Đặt breakpoint tại multiply"
  -> jdb gọi API JDI/EventRequestManager
  -> JDI chuyển thành JDWP command
  -> JDWP agent trao đổi với JVM TI
  -> JVM ghi nhận breakpoint request
  -> Reply thành công/lỗi quay về debugger
~~~

**Event flow (JVM → debugger):**

~~~text
Thread của JVM thực thi vào multiply
  -> JVM/JVM TI phát sinh sự kiện breakpoint
  -> JDWP agent tạo event packet
  -> JDI EventQueue nhận BreakpointEvent trong EventSet
  -> jdb hiển thị prompt + stack
  -> Người dùng xem biến/step/continue
  -> Debugger resume theo suspend policy
~~~

**Sự khác biệt cần nhớ:** request thiết lập một điều kiện, còn event được phát **khi điều kiện xảy ra**. Nếu method chưa chạy, breakpoint đã đặt có thể chưa phát event. Nếu class chưa load, debugger có thể phải đợi class-prepare event mới đặt được location. Nếu method đã chạy qua trước khi attach với `suspend=n`, không thể quay ngược thời gian để bắt breakpoint đã bỏ lỡ.

JDI có nhiều lựa chọn về **suspend policy** (dừng cả VM, dừng thread báo event hoặc không dừng). Đặt suspend policy sai có thể khiến ứng dụng dừng nhiều hơn dự kiến hoặc không có stack frame ở trạng thái thích hợp để đọc. Đừng dùng thuật toán tự resume mọi thread nếu chưa hiểu `EventSet` và quy tắc cân bằng suspend count.

## 11. Debug information, class loading và giới hạn khả năng quan sát

Breakpoint và việc hiển thị locals phụ thuộc vào class file và trạng thái JVM:

- **`javac -g`:** sinh metadata đầy đủ cho local variables, line numbers và source files. Nếu không có local variable table, debugger có thể xem stack/method nhưng không hiện được tên biến local hoặc báo `AbsentInformationException` trong JDI.
- **Line breakpoint:** gắn với source mapping; biên dịch tối ưu, source không trùng bytecode, hoặc jar khác phiên bản có thể làm lệch vị trí. Đặt breakpoint theo method đôi khi ổn định hơn trong lab.
- **Lớp chưa được load:** `stop in` hoặc JDI breakpoint request có thể bị hoãn cho đến khi class xuất hiện. Không đồng nhất “deferred” với “failed”.
- **Inlining/optimization/JIT:** trạng thái thực thi, stepping và giá trị local có thể khác trực giác từ source; debugger có thể yêu cầu runtime deoptimization hoặc các cơ chế hỗ trợ tương tự. Không giả định lúc nào dòng source cũng ánh xạ 1–1 với bytecode/CPU instruction.
- **Thread state:** đọc frame/local variables thường đòi hỏi thread đang bị suspend đúng cách; nếu không, JDI có thể ném ngoại lệ.
- **Phiên bản JDK/VM:** bản ghi wire-level và API có quy tắc tương thích, nhưng vendor, module, transport và khả năng hỗ trợ các event đặc biệt có thể khác. Kiểm tra `jdb -help`/`jdb -listconnectors` cùng tài liệu JDK đích.
- **Nhiều thread/virtual threads:** debug trên JDK mới có thể có nhiều virtual threads. Không bật tracking tất cả thread chỉ để “xem hết” nếu số lượng quá lớn; chi phí và hành vi cần được cân nhắc theo phiên bản.

Đọc `StackFrame.getValue` hay dừng tại breakpoint là **quan sát tức thời** trong runtime đang sống, không phải timeline quá khứ. Khi cần phân tích những sự kiện xảy ra trước đó hoặc phân phối hiệu năng theo thời gian, hãy kết hợp logging, JFR hoặc metrics thay vì giữ tiến trình suspended lâu.

## 12. JDWP và vấn đề bảo mật, hiệu năng

Một cổng debug không phải cổng monitoring chỉ đọc. Khi debugger có quyền truy cập, nó có thể xem object, biến, call stack và có thể thực hiện thao tác điều khiển JVM. Rủi ro:

1. **Lộ dữ liệu nhạy cảm:** token, cấu hình, dữ liệu khách hàng có thể nằm trong heap/local variables.
2. **Thay đổi thực thi:** suspend/step/mutate state hoặc invoke methods có thể ảnh hưởng nghiệp vụ.
3. **Gián đoạn dịch vụ:** breakpoint với suspend-all có thể dừng tất cả application threads, gây timeout và ảnh hưởng heartbeat/health check.
4. **Tăng overhead:** bước từng dòng, theo dõi field/exception, nhiều thread hoặc frequent event callbacks có thể làm runtime chậm đi.
5. **Truy cập trái phép:** mở `address=*:5005` không có bảo vệ mạng thích hợp có thể cho người không được phép kết nối và kiểm soát JVM.

Vì vậy, trong môi trường thật:

- Chỉ bật khi có nhu cầu được phép; ưu tiên staging hoặc instance tách khỏi tải chính.
- Bind loopback (`127.0.0.1`/`::1`) hoặc dùng tunnel an toàn qua mạng quản trị được kiểm soát; không công khai port.
- Chọn `suspend=n` nếu không chủ đích dừng startup. `suspend=y` phù hợp lab/lỗi khởi động sớm khi có operator sẵn sàng.
- Đặt breakpoint có thời hạn, tránh suspend-all trên luồng xử lý request đang phục vụ production.
- Kết thúc kết nối, kiểm tra trạng thái dịch vụ, không để agent mở vô thời hạn nếu không còn cần.
- Đảm bảo bản build, symbols/source và version debugger phù hợp.

Tách bạch **“có JDK tools trên máy”** khỏi **“được phép debug process này”**. `jdb` có sẵn không cấp quyền tự động vượt cơ chế mạng/OS/JVM.

## 13. Lỗi thường gặp: xác định đúng tầng trước khi xử lý

| Hiện tượng | Tầng cần xem | Nguyên nhân/cách kiểm tra |
| --- | --- | --- |
| `jdb -attach` báo connection refused | Transport/JDWP agent | JVM chưa bật `-agentlib:jdwp`, sai port/host, server chưa listen, JVM đã thoát |
| Connect timeout | Mạng/firewall/namespace | DNS, firewall, container port forwarding, SSH tunnel sai; không vội mở bind all interfaces |
| `suspend=y` làm ứng dụng không in gì | Cấu hình debuggee | Đây là cơ chế chờ debugger trước main; attach rồi `cont`/resume |
| “Not connected to VM” | Session JDI | Chưa attach thành công hoặc disconnect; kiểm tra trạng thái agent |
| “Deferring breakpoint” | Class loading | Class chưa load; đợi class prepare, đừng sửa source vô cớ |
| Breakpoint không hit | Request/location/luồng thực thi | Code path chưa chạy, class khác build, đã chạy trước khi attach, breakpoint đặt sai overload |
| `locals` không có tên biến | Class debug metadata | Biên dịch `javac -g`, đúng file class/jar, kiểm tra source maps |
| Method breakpoint hit nhưng giá trị lạ | Runtime/frame state | Thread/frame không đúng, method overload, JIT, biến đã bị sửa |
| Chương trình dừng mọi request | Suspend policy | Có thể dừng toàn VM; giảm phạm vi, dùng logpoint/telemetry khi phù hợp |
| `jdb -attach 12345` không đúng JVM | Nhầm port và PID | `jdb` cần socket address; `jcmd` thường dùng PID |
| IDE debug được nhưng `jdb` không | Tool/config | IDE có thể dùng connector, port, tunnel hoặc launch config khác; so thông số |
| Debug port trong container không kết nối | Network namespace | Port bind trong container localhost không tự thành localhost host; kiểm tra forwarding |
| Port đã chiếm | Transport | Chọn port khác hoặc dừng phiên cũ, tránh nhiều JDWP agent cùng listen một address |
| Mã custom JDI lỗi `VMDisconnectedException` | JDI lifecycle | JVM đích thoát/disconnect trong khi đang query; xử lý event và dọn tài nguyên |
| JVM chạy bình thường nhưng không có log debug | Hiểu nhầm cơ chế | JDWP chỉ kênh debug; nó không tạo JFR/log/HPROF tự động |

**Checklist theo thứ tự:** đúng PID ứng dụng → đúng JVM đã bật agent → đúng địa chỉ/port/namespace → đúng debugger/connector → đúng breakpoint location và class metadata → đúng thread/suspend state → đúng source/bytecode. Điều tra tầng thấp trước giúp tránh sửa sai ứng dụng.

## 14. Ba câu hỏi kiểm tra hiểu biết

**Câu 1.** Một IDE cho bạn bấm vào `int product` và đọc `42`. Thành phần nào biến yêu cầu cấp cao thành lệnh gửi sang JVM?

*Đáp án:* Giao diện IDE sử dụng **JDI** để thao tác trên mirror `StackFrame`/`LocalVariable`; implementation của JDI mã hóa yêu cầu theo **JDWP**. JDWP agent phía debuggee có thể dùng **JVM TI** để lấy giá trị. `jdb` chỉ là một frontend khác, không cần có mặt trong trường hợp này.

**Câu 2.** Bạn chạy `jdb -attach 5005` nhưng JVM không có `-agentlib:jdwp` và chỉ đang bật JFR. Vì sao không attach được?

*Đáp án:* Vì ví dụ `jdb -attach` cần một endpoint debug JDWP tương thích, trong khi **JFR không phải JDWP agent**. Cần khởi chạy/thiết lập đúng debugging agent và quyền truy cập, không thể dùng cổng JFR như cổng JDWP.

**Câu 3.** Trong kiến trúc JPDA, việc dùng `dt_socket` có biến JDWP thành một API TCP của riêng ứng dụng không?

*Đáp án:* Không. **JDWP** mô tả ngữ nghĩa và wire format debug. **`dt_socket`** chỉ là transport truyền các message đó qua TCP; ứng dụng nghiệp vụ không tự định nghĩa protocol hoặc xác thực người dùng cho JDWP.

**Tóm tắt cuối:** Hãy nhớ theo thứ tự **công cụ → API → giao thức → JVM**:

~~~text
jdb (CLI) hoặc IDE
    -> JDI (API / debugger front-end)
    -> JDWP (wire protocol trên dt_socket, ...)
    -> JDWP agent (debuggee back-end)
    -> JVM TI (VM service interface)
    -> Java VM chạy ứng dụng
~~~

Bạn chỉ cần **`jdb`** để thao tác debug từ terminal; dùng **JDI** khi viết debugger/tool; dùng tài liệu **JDWP** khi cần hiểu hoặc triển khai truyền thông debugger; cần hiểu **JVM TI** khi nghiên cứu back-end/native agent. Với ứng dụng thật, **bảo mật debug port và kiểm soát tác động suspend** quan trọng không kém việc đặt đúng breakpoint.

## Tài liệu tham khảo chính thức

- Oracle Java SE 21 — *Java Platform Debugger Architecture* (JVM TI, JDWP, JDI, front-end/back-end): https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/jpda.html
- Oracle Java SE 21 — *Connection and Invocation Details* (connectors, dt_socket, `-agentlib:jdwp`, `server`/`suspend`/`address`): https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html
- Oracle Java SE 21 — *The jdb Command* (launch/attach, `stop`, `step`, `next`, `-listconnectors`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html
- Java SE 21 API — module `jdk.jdi`, `com.sun.jdi` và `com.sun.jdi.connect`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/module-summary.html
- Java SE 21 API — `AttachingConnector` và `VirtualMachineManager`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/connect/AttachingConnector.html
- Oracle — *JPDA Frequently Asked Questions* (khi nào dùng JDI/JDWP/JVM TI, debug metadata): https://www.oracle.com/java/technologies/javase/java-platform-debugger-architecture.html
