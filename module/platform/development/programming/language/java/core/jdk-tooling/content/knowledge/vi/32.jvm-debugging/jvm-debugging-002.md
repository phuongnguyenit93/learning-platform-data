# JDWP: Java Debug Wire Protocol

**Java Debug Wire Protocol (JDWP)** là giao thức trao đổi giữa debugger và Java Virtual Machine (JVM) đang chạy ứng dụng cần debug (debuggee). JDWP cho phép debugger yêu cầu thông tin về class, thread, stack frame, object và biến; đặt breakpoint; nhận event khi breakpoint hoặc exception xảy ra; step qua code; thay đổi một số giá trị runtime và điều khiển việc tạm dừng/tiếp tục JVM.

JDWP là một lớp trong **Java Platform Debugger Architecture (JPDA)**. Đây là nền tảng giúp JDB, IntelliJ IDEA, Eclipse và các debugger tương thích kết nối tới JVM cục bộ hoặc từ xa. Để dùng JDWP trên HotSpot, JVM cần được khởi động với debug agent, thường bằng tùy chọn `-agentlib:jdwp`.

## 1. JDWP nằm ở đâu trong kiến trúc JPDA?

JPDA có ba lớp chính:

| Lớp | Tên đầy đủ | Vai trò |
| --- | --- | --- |
| JVM TI | Java Virtual Machine Tool Interface | Giao diện native mà JVM cung cấp để đọc trạng thái và điều khiển hoạt động debug |
| JDWP | Java Debug Wire Protocol | Quy định packet, command, reply và event giữa debugger với debuggee |
| JDI | Java Debug Interface | API Java cấp cao để viết debugger và làm việc với breakpoint, thread, stack frame, object |

Trong triển khai tham chiếu của Oracle:

- JVM TI được triển khai trong VM.
- JDWP back-end chạy phía debuggee, nhận yêu cầu từ debugger và gọi các chức năng JVM TI.
- JDWP front-end chuyển các thao tác debugger thành packet JDWP.
- JDI là API mà JDB và nhiều IDE sử dụng để thao tác với front-end.

Ví dụ khi bạn chọn một biến local trong IDE:

1. IDE gọi JDI để yêu cầu giá trị biến trong stack frame.
2. Front-end chuyển yêu cầu thành JDWP command.
3. JDWP back-end nhận packet và truy vấn JVM thông qua JVM TI.
4. Kết quả được đóng gói thành JDWP reply và trả lại debugger.
5. IDE hiển thị giá trị biến.

Khi breakpoint được chạm, VM gửi một event qua back-end; debugger nhận event và hiển thị vị trí dừng.

**Phân biệt thuật ngữ:**

- JPDA là kiến trúc tổng thể.
- JDWP là giao thức truyền dữ liệu debug.
- JVM TI là giao diện native phía VM.
- JDI là API phía debugger.
- JDB là debugger dòng lệnh mẫu dùng JDI.
- JDWP agent là thành phần được nạp vào JVM đích để hỗ trợ giao tiếp debug.

JDWP là tùy chọn; một số JVM implementation có thể không cung cấp giao thức hoặc agent này.

## 2. Cơ chế kết nối và JDWP handshake

JDWP truyền các command, reply và event qua một transport. Transport xác định cách hai tiến trình trao đổi byte; JDWP xác định định dạng và ý nghĩa của dữ liệu.

Khi kết nối được thiết lập, debugger và VM thực hiện handshake:

- Debugger gửi chuỗi ASCII 14 byte `JDWP-Handshake`.
- VM trả lại chính xác cùng chuỗi.
- Sau handshake, hai phía mới trao đổi JDWP packet.

Có hai nhóm packet cơ bản:

- **Command packet:** debugger yêu cầu thông tin hoặc điều khiển VM; VM cũng có thể gửi command/event packet để thông báo sự kiện.
- **Reply packet:** trả trạng thái thành công/lỗi và dữ liệu tương ứng cho command.

Ví dụ các nhóm lệnh trong JDWP:

- VirtualMachine: liệt kê class/thread, suspend, resume, exit và truy vấn capabilities.
- ReferenceType/Method: truy vấn field, method, source line table và variable table.
- StackFrame: đọc hoặc thay đổi giá trị trong frame.
- EventRequest: đăng ký hoặc xóa breakpoint, exception event và các event khác.
- ThreadReference: xem trạng thái, stack frame, monitor và suspend/resume thread.
- ObjectReference/ClassType: đọc field, ghi field, gọi method hoặc tạo object khi VM hỗ trợ.

Giao thức có event cho breakpoint, single-step, exception, thread start/end và các thay đổi runtime khác. Không phải mọi capability đều có mặt trên mọi JVM; debugger cần kiểm tra capabilities của target VM.

## 3. Nạp JDWP agent vào JVM

Trên HotSpot JDK hiện đại, dùng:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar app.jar
```

Cấu trúc tổng quát:

```text
-agentlib:jdwp=<name1>=<value1>,<name2>=<value2>,...
```

Các thành phần:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-agentlib:jdwp` | Nạp JDWP agent vào JVM |
| `transport` | Chọn transport giữa debugger và JVM |
| `server` | Chọn bên nào lắng nghe kết nối |
| `address` | Địa chỉ transport |
| `suspend` | Quyết định JVM có dừng trước khi chạy ứng dụng hay không |
| `timeout` | Thời gian chờ kết nối, tính bằng millisecond |
| `allow` | Lọc địa chỉ client được phép kết nối với socket server |
| `onthrow` | Chỉ khởi tạo JDWP khi một exception class được chỉ định bị throw |
| `onuncaught` | Chỉ khởi tạo JDWP khi có uncaught exception |
| `launch` | Khởi chạy chương trình debugger stub sau khi JDWP khởi tạo; thường kết hợp với onthrow/onuncaught |

Kiểm tra tùy chọn thực tế của JDK đang dùng:

```bash
java -agentlib:jdwp=help
jdb -help
jdb -listconnectors
```

JDK 24 vẫn hỗ trợ giao diện cũ `-Xrunjdwp`, nhưng đã cảnh báo giao diện này sẽ bị loại bỏ trong một bản phát hành tương lai. Dùng `-agentlib:jdwp` cho cấu hình mới.

## 4. Hiểu server, transport, address và suspend

### server=y và server=n

`server=y` có nghĩa JVM đích mở endpoint và chờ debugger kết nối. Đây là cách thường dùng khi IDE attach vào một ứng dụng đã được khởi động với debug agent.

`server=n` có nghĩa JVM đích chủ động kết nối tới debugger đang lắng nghe. Cấu hình này hữu ích khi mạng hoặc firewall chỉ cho phép kết nối theo chiều từ máy chạy ứng dụng ra máy phát triển.

Lưu ý: `server=y` nói về vai trò client/server của kết nối JDWP; nó không có nghĩa ứng dụng phải là web server.

### Transport

| Transport | Cách hoạt động | Phạm vi |
| --- | --- | --- |
| `dt_socket` | TCP/IP socket | Cùng máy hoặc máy khác |
| `dt_shmem` | Windows shared memory | Hai tiến trình trên cùng máy Windows |

`dt_socket` hỗ trợ IPv4 và IPv6. Địa chỉ socket có dạng `<host>:<port>`. Nếu host rỗng, transport dùng loopback; host `*` trong chế độ server lắng nghe trên mọi network interface.

`dt_shmem` chỉ có trong triển khai tham chiếu trên Windows và không dùng để debug qua mạng.

### address

Ví dụ lắng nghe trên loopback:

```bash
-agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005
```

Ví dụ lắng nghe trên mọi interface:

```bash
-agentlib:jdwp=transport=dt_socket,server=y,address=*:5005
```

Trong JDK 24, nếu server dùng địa chỉ chỉ có port, ví dụ `address=5005`, socket transport mặc định lắng nghe loopback. Dùng địa chỉ loopback tường minh giúp cấu hình dễ đọc và giảm nhầm lẫn giữa các môi trường.

Nếu `server=y` và bỏ `address`, agent có thể chọn một địa chỉ transport khả dụng rồi in địa chỉ đó ra standard output. Cách này hữu ích khi cần port động.

### suspend

| Giá trị | Hành vi |
| --- | --- |
| `suspend=y` | Dừng VM tại VMStart event trước khi main class được nạp/chạy; tiếp tục sau khi debugger kết nối và gửi resume |
| `suspend=n` | VM chạy ngay; debugger có thể attach khi ứng dụng đang hoạt động |

Mặc định của JDWP agent là `suspend=y`.

Dùng `suspend=y` khi cần breakpoint ở startup hoặc cần debug lỗi khởi tạo. Nếu debugger không kết nối, ứng dụng có thể tiếp tục bị dừng; có thể cấu hình `timeout` để giới hạn thời gian chờ.

Dùng `suspend=n` khi không muốn ứng dụng chờ debugger. Tuy nhiên, breakpoint đặt sau khi method đã chạy sẽ không quay ngược thời gian để bắt lần gọi trước đó.

## 5. Ví dụ cấu hình thường gặp

### Debug local và dừng trước main

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out DebugTarget
```

JVM mở socket loopback và đợi debugger. Ứng dụng chưa chạy main cho đến khi debugger kết nối và resume VM.

### Debug local nhưng không dừng startup

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out DebugTarget
```

Ứng dụng bắt đầu chạy ngay. Attach debugger sau đó và đặt breakpoint cho những lần thực thi tiếp theo.

### Giới hạn thời gian chờ debugger

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005,timeout=30000 -cp out DebugTarget
```

`timeout=30000` đặt thời gian chờ 30 giây cho transport hỗ trợ tùy chọn timeout. Nếu hết thời gian mà debugger chưa attach, agent có thể kết thúc kết nối hoặc VM theo hành vi của transport.

### Giới hạn địa chỉ client được phép

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=127.0.0.1+192.168.1.0/24 -cp out DebugTarget
```

`allow` áp dụng cho `dt_socket` khi `server=y`. Danh sách IP/subnet phân tách bằng dấu `+`. Đây là bộ lọc địa chỉ nguồn, không phải xác thực danh tính debugger.

### Debugger lắng nghe, JVM chủ động kết nối

Terminal chạy debugger:

```bash
jdb -connect com.sun.jdi.SocketListen:port=5005
```

Terminal chạy ứng dụng:

```bash
java -agentlib:jdwp=transport=dt_socket,server=n,address=127.0.0.1:5005,suspend=y -cp out DebugTarget
```

Trong cấu hình này, debugger là bên lắng nghe và JVM là bên khởi tạo kết nối. Khi triển khai remote, hãy xác định rõ chiều kết nối phù hợp với firewall/network policy.

## 6. Kết nối bằng JDB

JDB là debugger dòng lệnh đi kèm JDK. Có thể dùng JDB để khởi chạy chương trình hoặc attach tới JVM đã chạy với JDWP agent.

Xem các connector được hỗ trợ:

```bash
jdb -listconnectors
```

Các connector thường gặp:

- `com.sun.jdi.SocketAttach`: attach tới JVM qua TCP socket.
- `com.sun.jdi.SocketListen`: chờ JVM kết nối qua TCP socket.
- `com.sun.jdi.SharedMemoryAttach`: attach qua Windows shared memory.
- `com.sun.jdi.SharedMemoryListen`: lắng nghe Windows shared memory.
- `com.sun.jdi.ProcessAttach`: attach tới JVM theo PID nếu target hỗ trợ.
- `com.sun.jdi.CommandLineLaunch`: JDI connector khởi chạy một JVM mới.

Ví dụ attach qua socket:

```bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

JDB cũng có cú pháp ngắn:

```bash
jdb -attach 5005
```

Tuy nhiên, connector mặc định của `jdb -attach` phụ thuộc nền tảng: triển khai tham chiếu dùng shared memory trên Windows và socket trên Linux/macOS. Nếu target đang dùng `dt_socket` trên Windows, hãy chỉ định `com.sun.jdi.SocketAttach` rõ ràng như ví dụ trên.

Để JDB khởi chạy chương trình mới:

```bash
jdb -sourcepath src -classpath out DebugTarget
```

Khi dùng cách này, JDB quản lý việc khởi chạy target và có thể dừng chương trình trước instruction đầu tiên của main class để bạn đặt breakpoint.

## 7. Các lệnh JDB thường dùng

| Lệnh | Công dụng |
| --- | --- |
| `stop at Class:line` | Đặt breakpoint tại dòng source |
| `stop in Class.method` | Đặt breakpoint khi method bắt đầu |
| `clear Class:line` | Xóa breakpoint tại dòng |
| `where` | In stack trace của thread hiện tại |
| `where all` | In stack trace của mọi thread |
| `threads` | Liệt kê thread |
| `thread <id>` | Chọn thread làm thread hiện tại |
| `locals` | In method arguments và local variables |
| `print expression` | Đánh giá và in biểu thức |
| `dump expression` | In thông tin object |
| `set variable = expression` | Thay đổi giá trị biến/field được phép |
| `step` | Đi vào lời gọi method tiếp theo |
| `next` | Chạy qua lời gọi method hiện tại, dừng ở dòng kế tiếp trong frame |
| `step up` | Chạy đến khi method hiện tại trả về caller |
| `stepi` | Bước theo bytecode instruction |
| `cont` | Tiếp tục sau breakpoint |
| `resume` | Resume thread hoặc toàn bộ VM; mặc định là tất cả thread |
| `catch ExceptionClass` | Dừng khi exception tương ứng được throw |
| `ignore ExceptionClass` | Bỏ theo dõi exception đã đăng ký |
| `watch all Class.field` | Theo dõi truy cập và thay đổi field nếu VM hỗ trợ |
| `redefine Class file.class` | Nạp lại định nghĩa class nếu VM hỗ trợ |

Khi VM vừa attach ở VMStart và chưa có stack frame, dùng `resume` để cho tất cả thread chạy. Sau khi dừng tại breakpoint, dùng `cont` để tiếp tục thực thi.

Để xem trợ giúp lệnh:

```text
help
```

Một số thao tác phụ thuộc khả năng VM, loại breakpoint và debug information có trong class file.

## 8. Ví dụ thực hành Java 17: đặt breakpoint và xem biến bằng JDWP

Ví dụ sau tính tổng hai số, nhân đôi kết quả rồi in ra màn hình.

Cấu trúc project:

```text
project/
  src/
    DebugTarget.java
  out/
```

Tệp `src/DebugTarget.java`:

```java
public final class DebugTarget {
    private DebugTarget() {
    }

    public static void main(String[] args) {
        int left = 7;
        int right = 5;
        int result = calculate(left, right);
        System.out.println("result=" + result);
    }

    static int calculate(int left, int right) {
        int sum = left + right;
        int doubled = sum * 2;
        return doubled;
    }
}
```

Biên dịch với debug information:

```bash
mkdir out
javac --release 17 -g -d out src/DebugTarget.java
```

Tùy chọn `-g` yêu cầu compiler sinh thông tin debug như source, line number và local variable table. Điều này giúp debugger ánh xạ bytecode tới source line và đọc local variables. Nếu thiếu local variable table, lệnh `locals` có thể không hiển thị các biến local.

### Terminal A: khởi chạy JVM với JDWP

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out DebugTarget
```

Output ban đầu:

```text
Listening for transport dt_socket at address: 5005
```

JVM đang chờ debugger; main chưa được thực thi.

### Terminal B: attach bằng JDB

```bash
jdb -sourcepath src -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

Tại dấu nhắc JDB, đặt breakpoint ở dòng 11, sau đó resume VM:

```text
stop at DebugTarget:11
resume
```

JVM chạy cho tới dòng:

```java
int doubled = sum * 2;
```

Khi breakpoint hit, xem stack và biến:

```text
where
locals
print sum
```

Output quan trọng:

```text
Breakpoint hit: "thread=main", DebugTarget.calculate(), line=11
11            int doubled = sum * 2;

[1] DebugTarget.calculate (DebugTarget.java:11)
[2] DebugTarget.main (DebugTarget.java:6)

Method arguments:
left = 7
right = 5

Local variables:
sum = 12

sum = 12
```

Đi qua dòng gán `doubled`:

```text
next
print doubled
```

Output:

```text
Step completed: "thread=main", DebugTarget.calculate(), line=12
12            return doubled;

doubled = 24
```

Tiếp tục cho chương trình kết thúc:

```text
cont
```

Output của ứng dụng:

```text
result=24
```

Đây là luồng debug đã được kiểm thử trên HotSpot JDK 24.0.2 với source biên dịch bằng `javac --release 17 -g`. Port và chi tiết BCI/thread có thể khác giữa các lần chạy; giá trị biến và kết quả tính toán của ví dụ là cố định.

## 9. Breakpoint, stepping và exception

### Breakpoint theo dòng

```text
stop at DebugTarget:11
```

JDB đặt breakpoint ở instruction đầu tiên tương ứng với dòng source có thể thực thi. Một dòng không có bytecode tương ứng có thể không tạo breakpoint như mong đợi.

### Breakpoint theo method

```text
stop in DebugTarget.calculate
```

Nếu method overload, chỉ rõ kiểu tham số:

```text
stop in DebugTarget.calculate(int,int)
```

### Step into và step over

- `step` đi vào method được gọi ở dòng kế tiếp.
- `next` thực thi method call mà không đi vào method đó.
- `step up` chạy đến khi method hiện tại trả về caller.
- `stepi` bước theo bytecode instruction.

Chọn lệnh theo câu hỏi: muốn kiểm tra logic trong method được gọi thì dùng `step`; muốn quan sát luồng của method hiện tại thì dùng `next`.

### Dừng khi exception xảy ra

Đăng ký exception breakpoint:

```text
catch java.lang.IllegalArgumentException
```

Khi exception được throw, JDB dừng tại vị trí phát sinh để kiểm tra stack và biến. Dùng `ignore` để bỏ đăng ký exception tương ứng.

Exception breakpoint có thể bắt exception đã được catch hoặc chỉ uncaught tùy cú pháp `catch` và cấu hình. Kiểm tra `help catch` trong JDB đang dùng.

## 10. Compile debug information và source mapping

JDWP truyền thông tin runtime từ VM; việc hiển thị source line và local variable phụ thuộc metadata có trong class file.

Nên biên dịch code cần debug với:

```bash
javac -g -d out src/DebugTarget.java
```

Các loại debug information:

- Source file attribute: tên source file.
- Line number table: ánh xạ bytecode index tới source line.
- Local variable table: tên và phạm vi sống của local variables.
- Local variable type table: generic type information nếu được sinh.

Nếu dùng Maven hoặc Gradle, kiểm tra cấu hình compiler để đảm bảo debug information được giữ lại. Một số build tối ưu hoặc obfuscation có thể xóa metadata hoặc thay đổi tên class/method.

Khi attach vào JVM từ xa, dùng source code cùng revision/build với class file đang chạy. Nếu source khác phiên bản, breakpoint line có thể lệch hoặc JDB không tìm được vị trí tương ứng.

## 11. JDWP với IDE

Các IDE Java thường tích hợp JDI và JDWP trong chức năng Debug/Remote Debug.

Quy trình tổng quát:

1. Khởi chạy ứng dụng với JDWP agent.
2. Chọn transport và host/port.
3. Tạo cấu hình Remote JVM Debug trong IDE.
4. Chọn đúng source/module tương ứng với binary đang chạy.
5. Attach debugger.
6. Đặt breakpoint và kích hoạt request hoặc luồng xử lý cần điều tra.
7. Xem Variables, Watches, Frames, Threads và Console.
8. Resume hoặc detach khi hoàn tất.

IDE thường cung cấp giao diện trực quan hơn JDB nhưng vẫn dùng cùng kiến trúc kết nối. Nếu IDE báo không kết nối được, hãy kiểm tra JDWP agent, transport, port, firewall và connector trước khi điều tra breakpoint.

## 12. Debugging virtual threads

JDK hiện đại có virtual threads. Khi ứng dụng tạo số lượng virtual thread rất lớn, debugger phải theo dõi nhiều thread/event và có thể bị quá tải.

Trong JDK 24:

- JDB mặc định không theo dõi mọi virtual thread ngay từ lúc được tạo.
- `jdb -trackallthreads` yêu cầu JDB theo dõi virtual thread khi chúng được tạo.
- JDWP agent có tùy chọn `includevirtualthreads=y` để trả virtual thread trong danh sách thread mà debugger yêu cầu.
- Virtual thread được tạo trước khi debugger attach có thể không nằm trong danh sách mà agent biết.
- Theo dõi toàn bộ virtual thread có thể tạo overhead hoặc làm debugger quá tải khi số lượng thread rất lớn.

Ví dụ:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,includevirtualthreads=y,address=127.0.0.1:5005 -cp out DebugTarget
```

Và:

```bash
jdb -trackallthreads -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

Chỉ bật theo dõi toàn bộ khi cần điều tra vấn đề liên quan virtual thread. Với ứng dụng có hàng trăm nghìn hoặc hàng triệu virtual thread, hãy cân nhắc giới hạn phạm vi quan sát.

## 13. Giới hạn của JDWP và hành vi runtime

JDWP là giao thức điều khiển debug, không phải profiler hoặc monitoring system.

Một số giới hạn quan trọng:

- Không phải mọi JVM đều hỗ trợ JDWP agent hoặc mọi JDWP capability.
- Debugger có thể đọc local variables nếu class file có local variable table.
- Breakpoint line phụ thuộc line number table và bytecode thực tế.
- JIT optimization, inlining và code generation có thể làm stepping/source mapping khác với cách đọc source tuần tự.
- Redefine class có giới hạn theo khả năng của VM; HotSwap thông thường không cho phép tùy ý thêm/xóa field, method hoặc thay đổi class hierarchy.
- JDWP tập trung vào Java-level debugging. Native code cần native debugger phù hợp.
- Suspend thread/VM làm thay đổi timing của ứng dụng; lỗi race condition hoặc timeout có thể biến mất hoặc xuất hiện khác khi debug.
- Một breakpoint dừng toàn VM có thể khiến request, lock owner, heartbeat hoặc health check chờ lâu.
- Attach vào JVM production có thể ảnh hưởng latency và độ ổn định; cần kế hoạch và phạm vi debug rõ ràng.

Nếu cần phân tích hiệu năng liên tục, allocation, lock contention hoặc GC, hãy dùng JFR/JMC và profiler. JDWP chủ yếu dùng để kiểm tra logic, trạng thái và luồng thực thi tại một vị trí cụ thể.

## 14. Bảo mật khi bật JDWP

JDWP cho phép debugger đọc trạng thái JVM và điều khiển tiến trình. Protocol có command để đọc/ghi field, đọc/ghi stack frame, gọi method, suspend/resume và terminate VM. Hãy xem cổng JDWP như một giao diện quản trị có quyền cao.

Thực hành an toàn:

- Chỉ bật JDWP khi thật sự cần debug.
- Ưu tiên bind loopback, ví dụ `address=127.0.0.1:5005`.
- Không dùng `address=*:5005` trên mạng công cộng.
- Nếu phải mở interface mạng, giới hạn nguồn bằng `allow`, firewall và network policy.
- `allow` chỉ lọc địa chỉ nguồn, không thay thế xác thực.
- Với remote debug, ưu tiên SSH tunnel hoặc VPN thay vì expose cổng trực tiếp.
- Tắt debug agent và đóng tunnel sau khi điều tra xong.
- Không ghi thông tin nhạy cảm vào command line hoặc log debug.
- Không để debugger treo ở breakpoint trong môi trường có traffic người dùng.
- Chỉ cấp quyền debug cho người được phép truy cập process và dữ liệu runtime.

Ví dụ SSH tunnel từ máy phát triển:

```bash
ssh -L 5005:127.0.0.1:5005 user@debug-host
```

Nếu JVM remote lắng nghe loopback trên host, tunnel chuyển cổng local 5005 tới loopback port 5005 của host. IDE/JDB trên máy phát triển kết nối tới `127.0.0.1:5005`.

Không coi JDWP là một giao thức có xác thực hoặc mã hóa đầu cuối. Dùng network boundary bên ngoài để bảo vệ kết nối.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Connection refused` | JVM chưa bật agent, sai port hoặc agent chưa lắng nghe | Kiểm tra command khởi chạy, PID, host và port |
| JDB attach nhưng không hit breakpoint | Breakpoint đặt sau khi method đã chạy hoặc class chưa được load | Dùng `suspend=y` khi cần bắt startup; đặt breakpoint trước lần gọi tiếp theo |
| `No source found` | Thiếu source path hoặc source không cùng revision | Dùng `-sourcepath` và đúng source revision |
| Không xem được local variable | Class file không có local variable table | Biên dịch lại với `javac -g` hoặc bật debug info trong build |
| Breakpoint line bị lệch | Source không khớp binary hoặc dòng không có executable bytecode | Xác minh commit/build và line number table |
| `Unable to attach` | Sai transport, quyền process hoặc connector không tương thích | Dùng connector đúng với `dt_socket`/`dt_shmem` |
| `jdb -attach` lỗi shared memory trên Windows | `-attach` mặc định chọn shared memory nhưng target đang dùng socket | Dùng `-connect com.sun.jdi.SocketAttach:hostname=...,port=...` |
| JVM không khởi động vì JDWP | Tùy chọn agent sai hoặc port/address không hợp lệ | Kiểm tra `java -agentlib:jdwp=help` và log khởi động |
| Ứng dụng không chạy sau khi bật debug | `suspend=y` đang đợi debugger attach | Attach debugger rồi dùng `resume`; cân nhắc timeout |
| Debugger không thấy virtual thread | Mặc định không theo dõi mọi virtual thread | Cân nhắc `-trackallthreads` và `includevirtualthreads=y` |
| Breakpoint làm request timeout | Thread/VM bị suspend trong khi request đang chạy | Chọn breakpoint có điều kiện/phạm vi thread, giảm thời gian dừng và debug trên môi trường phù hợp |
| Không thể hot-swap thay đổi cấu trúc class | VM không hỗ trợ schema change trong redefine | Restart ứng dụng hoặc dùng công cụ có khả năng reload phù hợp |

## 16. Quy trình debug JVM bằng JDWP

1. Xác định lỗi và JVM cần điều tra.
2. Xác minh JDK/JVM hỗ trợ JDWP.
3. Biên dịch với source/line/local debug information.
4. Chọn transport, server/client direction và address.
5. Chọn `suspend=y` nếu cần bắt startup hoặc `suspend=n` nếu ứng dụng phải chạy ngay.
6. Bật agent bằng `-agentlib:jdwp`.
7. Attach JDB/IDE bằng connector khớp với transport.
8. Đặt breakpoint hoặc exception breakpoint.
9. Dùng stack, locals, print, watch và stepping để kiểm tra trạng thái.
10. Resume application ngay khi hoàn tất quan sát.
11. Detach/đóng debugger và tắt JDWP agent khi không còn cần.
12. Ghi lại JDK version, build, breakpoint, dữ liệu quan sát và kết luận.

## 17. Ghi nhớ

- JDWP là giao thức command/reply/event giữa debugger và JVM đích.
- JPDA gồm JVM TI, JDWP và JDI; JDB/IDE thường dùng JDI.
- `-agentlib:jdwp` nạp debug agent vào JVM.
- `transport=dt_socket` dùng TCP; `dt_shmem` dùng Windows shared memory.
- `server=y` khiến JVM chờ debugger; `server=n` khiến JVM kết nối tới debugger listener.
- `suspend=y` dừng VM trước khi main class chạy; `suspend=n` cho phép ứng dụng chạy ngay.
- `address` xác định endpoint; `allow` lọc nguồn kết nối cho socket server.
- JDK 24 trên Windows dùng shared memory cho connector mặc định của `jdb -attach`; dùng `SocketAttach` tường minh khi target sử dụng socket.
- `stop`, `where`, `locals`, `print`, `step`, `next` và `cont` là các lệnh JDB thường dùng.
- `javac -g` giúp debugger có line table và local variable table.
- Virtual thread cần cấu hình theo dõi riêng khi cần xem toàn bộ.
- JDWP có quyền điều khiển mạnh và làm thay đổi timing; chỉ mở trong phạm vi mạng tin cậy, trong thời gian cần thiết.

Hiểu JDWP giúp bạn kết nối debugger với đúng JVM, dừng tại đúng vị trí, kiểm tra trạng thái thread/biến và lần theo luồng thực thi. Kết hợp breakpoint, stack frame, local variables và stepping sẽ giúp bạn xác định lỗi logic một cách có hệ thống.

## Tài liệu tham khảo

- [Java Platform Debugger Architecture — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html)
- [Connection and Invocation Details — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [The jdb Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [Java Debug Wire Protocol Details — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html)
