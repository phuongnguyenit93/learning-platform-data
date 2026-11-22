# Sử dụng Java Debugger (`jdb`) để gỡ lỗi JVM

`jdb` là trình gỡ lỗi dòng lệnh đi kèm JDK. Công cụ này cho phép dừng chương trình tại breakpoint, chạy từng dòng hoặc từng lệnh bytecode, xem call stack, đọc local variables, đánh giá biểu thức, theo dõi thread và bắt exception. `jdb` phù hợp với môi trường terminal, máy chủ không có giao diện đồ họa và các phiên debug từ xa.

`jdb` sử dụng Java Debug Interface (JDI) để điều khiển JVM đích thông qua Java Debug Wire Protocol (JDWP). Khi chạy chương trình trực tiếp bằng `jdb`, debugger khởi chạy JVM với cơ chế debug tương ứng. Khi attach vào một process đang chạy, JVM đích phải cho phép debugger kết nối qua connector phù hợp.

Bài học này dùng Zulu/OpenJDK 24.0.2 để kiểm tra cú pháp và thực hành, đồng thời dùng mã Java 17+ để ví dụ có thể biên dịch trên các JDK hiện đại.

## 1. Khi nào dùng `jdb`?

Một số tình huống phù hợp:

- Chương trình lỗi trên máy chủ chỉ có SSH hoặc terminal.
- Cần xác định chính xác dòng code làm sai giá trị.
- Muốn xem biến và call stack mà không sửa code bằng log.
- Cần dừng tại một method hoặc source line cụ thể.
- Cần kiểm tra thread đang chạy, đang chờ hoặc đang giữ lock.
- Cần bắt exception ngay tại thời điểm được throw.
- Muốn attach vào một JVM đang chạy có bật JDWP.
- Cần debug ứng dụng trong container hoặc môi trường staging không có IDE.

`jdb` không thay thế log, metrics, tracing hoặc JFR. Debugger thường tạm dừng thread hoặc toàn JVM tại breakpoint, vì vậy không nên đặt breakpoint tương tác tùy tiện trên production traffic. Với sự cố production, ưu tiên telemetry và recording ít xâm lấn; chỉ bật debugger từ xa theo quy trình vận hành có kiểm soát.

## 2. JDI, JDWP và JPDA

Các thành phần liên quan:

- **JPDA (Java Platform Debugger Architecture):** kiến trúc tổng thể cho Java debugging.
- **JDI (Java Debug Interface):** API phía debugger để đặt breakpoint, đọc frame, điều khiển thread và lấy thông tin object.
- **JDWP (Java Debug Wire Protocol):** giao thức truyền thông giữa debugger và JVM đích.
- **JVM TI:** giao diện native mà VM dùng để hỗ trợ các công cụ runtime, bao gồm debug agent.

Luồng cơ bản:

~~~text
jdb (debugger)
     |
     | JDI
     v
JDWP transport / connector
     |
     | JDWP protocol
     v
JVM debug agent
     |
     v
Java application
~~~

Khi debug local bằng lệnh `jdb <class>`, JDB khởi chạy ứng dụng và thiết lập kết nối. Khi debug remote, ứng dụng phải được khởi chạy với JDWP agent hoặc được cấu hình để chấp nhận debugger attach.

## 3. Chuẩn bị source code và debug symbols

Để xem source line và tên local variable, biên dịch với debug information:

~~~text
javac -g -d out src/JdbDemo.java
~~~

`-g` yêu cầu compiler tạo đầy đủ thông tin debug như source, line number và local variable table. Có thể chỉ định từng loại:

~~~text
javac -g:source,lines,vars -d out src/JdbDemo.java
~~~

Nếu thiếu line number information, breakpoint theo source line và source listing có thể không hoạt động như mong đợi. Nếu thiếu local variable information, lệnh `locals` có thể không hiển thị tên/giá trị biến cục bộ.

Trong dự án Maven hoặc Gradle, kiểm tra cấu hình compiler và artifact thực sự được deploy. Đừng giả định file `.class` trên server giống source code đang mở trên máy phát triển. Nếu code được obfuscate, instrument, shade hoặc tối ưu trong pipeline, breakpoint và line mapping có thể lệch.

## 4. Cú pháp và trợ giúp của `jdb`

Hiển thị trợ giúp command line:

~~~text
jdb -help
jdb -listconnectors
~~~

Khởi chạy debugger cho một class:

~~~text
jdb -classpath out -sourcepath src JdbDemo
~~~

Các option quan trọng:

| Option | Ý nghĩa |
|---|---|
| `-classpath` | Classpath của JVM đích khi JDB khởi chạy chương trình |
| `-sourcepath` | Thư mục tìm source file để hiển thị code |
| `-attach address` | Attach tới JVM đang lắng nghe JDWP qua standard socket connector |
| `-connect name:arguments` | Chọn connector JDI và truyền các argument |
| `-listen address` | Chờ JVM đích kết nối tới debugger |
| `-listenany` | Chờ kết nối trên một địa chỉ khả dụng |
| `-launch` | Khởi chạy JVM ngay, không chờ lệnh `run` |
| `-trackallthreads` | Theo dõi cả virtual threads và platform threads |
| `-R<option>` | Chuyển một JVM option cho debuggee được JDB khởi chạy |

Ví dụ truyền system property và heap size cho JVM đích:

~~~text
jdb -Dapp.mode=debug -R-Xmx512m -classpath out JdbDemo
~~~

Tùy chọn và connector khả dụng phụ thuộc JDK. Dùng `jdb -listconnectors` trên chính JDK đang chạy ứng dụng để xem tên connector, transport và argument bắt buộc.

## 5. Khởi chạy chương trình dưới debugger

Ví dụ:

~~~text
jdb -classpath out -sourcepath src JdbDemo
~~~

JDB hiển thị prompt:

~~~text
Initializing jdb ...
>
~~~

Đặt breakpoint trước khi chương trình chạy:

~~~text
stop in JdbDemo.calculate
run
~~~

`stop in` đặt breakpoint tại method. Nếu class chưa được load, JDB báo deferred breakpoint và sẽ gắn breakpoint khi class được load.

Có thể dùng `-launch` để khởi chạy JVM ngay khi JDB mở:

~~~text
jdb -launch -classpath out -sourcepath src JdbDemo
~~~

Nếu không dùng `-launch`, nhập `run` để bắt đầu main class. Khi chương trình dừng tại breakpoint, prompt thường có dạng `main[1]`.

## 6. Đặt, liệt kê và xóa breakpoint

Hai dạng breakpoint phổ biến:

**Theo method:**

~~~text
stop in com.example.OrderService.reserve
~~~

**Theo source line:**

~~~text
stop at com.example.OrderService:84
~~~

Có thể chỉ định method overload bằng danh sách kiểu tham số:

~~~text
stop in com.example.OrderService.reserve(java.lang.String,int)
~~~

Liệt kê breakpoint hiện tại:

~~~text
stop
~~~

Xóa breakpoint theo method hoặc dòng:

~~~text
clear com.example.OrderService.reserve
clear com.example.OrderService:84
~~~

Breakpoint theo dòng cần line number information trong class file và dòng đó phải có bytecode tương ứng. Nếu đặt tại dòng trống, comment hoặc dòng chỉ chứa dấu ngoặc, JDB có thể từ chối hoặc chuyển đến vị trí executable gần nhất.

JDB hỗ trợ deferred breakpoint khi class chưa được load. Nếu breakpoint không bao giờ kích hoạt, kiểm tra class name đầy đủ, classloader, source line và code path thực tế.

## 7. Chạy từng bước: `step`, `next`, `step up`, `stepi`

Khi chương trình đang dừng:

| Lệnh | Hành vi |
|---|---|
| `step` | Thực thi một source line và đi vào method được gọi nếu có |
| `next` | Thực thi một source line nhưng đi qua lời gọi method (step over) |
| `step up` | Chạy đến khi method hiện tại trả về caller |
| `stepi` | Thực thi một bytecode instruction |
| `cont` | Tiếp tục chạy đến breakpoint hoặc sự kiện dừng tiếp theo |

Ví dụ:

~~~text
step
next
step up
stepi
cont
~~~

Dùng `step` khi cần xem bên trong method. Dùng `next` khi đã biết method được gọi hoạt động đúng và muốn tiếp tục trong method hiện tại. `stepi` hữu ích khi phân tích bytecode hoặc khi source mapping không đủ rõ, nhưng thường không cần trong debug nghiệp vụ thông thường.

Compiler có thể inline hoặc biến đổi code; lambda, bridge method và synthetic method cũng làm stack trace phức tạp hơn. Hãy đối chiếu bytecode, source và line number thay vì giả định mỗi source line luôn tương ứng một instruction.

## 8. Xem call stack và chọn stack frame

Các lệnh chính:

~~~text
where
where all
where 2
up
up 2
down
down 2
~~~

- `where`: hiển thị call stack của thread hiện tại.
- `where all`: hiển thị stack của mọi thread.
- `where <thread-id>`: hiển thị stack của một thread cụ thể.
- `up` và `down`: di chuyển giữa các frame trong stack hiện tại.

Khi chọn frame khác, `locals`, `print` và `dump` sẽ được đánh giá trong phạm vi frame đó. Nếu biến không được tìm thấy, hãy xác nhận bạn đang đứng đúng frame và biến đã được khởi tạo ở vị trí hiện tại.

JDB còn có `pop` để loại bỏ frame hiện tại và các frame phía trên khỏi stack, và `reenter` để thực hiện lại frame. Đây là thao tác thay đổi luồng thực thi; chỉ dùng khi hiểu rõ tác động và trong phiên debug có thể khởi động lại.

## 9. Đọc và thay đổi biến

Các lệnh biểu thức:

~~~text
locals
print quantity
dump customer
eval order.getTotal()
set quantity = 5
~~~

- `locals`: liệt kê tham số và local variables trong frame hiện tại.
- `print`: đánh giá biểu thức và in giá trị.
- `dump`: hiển thị thông tin object.
- `eval`: đánh giá biểu thức, tương đương `print`.
- `set`: gán giá trị mới cho biến, field hoặc phần tử array có thể gán.

Ví dụ xem field:

~~~text
print order.status
print order.items.length
dump order
~~~

Biểu thức của JDB hỗ trợ cú pháp Java phổ biến, nhưng không phải toàn bộ môi trường compiler/IDE. Biểu thức gọi method có thể thực thi code trong debuggee, thay đổi state, thực hiện I/O hoặc block thread. Hãy ưu tiên đọc field/biến đơn giản; tránh gọi method có side effect trong ứng dụng đang xử lý dữ liệu thật.

Không phải mọi biến đều có thể xem ở mọi thời điểm. Biến có thể chưa được khởi tạo, đã ra khỏi scope, bị tối ưu hoặc thiếu local variable table. `locals` và `print` chỉ có ý nghĩa trong frame và thread đang được chọn.

## 10. Xem source và thông tin class

Một số lệnh hữu ích:

~~~text
list
list 84
list com.example.OrderService.reserve
use src
sourcepath
classpath
classes
class com.example.OrderService
methods com.example.OrderService
fields com.example.OrderService
~~~

- `list`: hiển thị source quanh vị trí hiện tại.
- `list <line>` hoặc `list <method>`: hiển thị source tại vị trí cụ thể.
- `use` hoặc `sourcepath`: xem/đổi đường dẫn source.
- `classpath`: in classpath của target VM.
- `classes`: liệt kê các class đã biết.
- `class`, `methods`, `fields`: xem chi tiết class, method và field.

Nếu JDB không tìm được source, dùng `-sourcepath` lúc khởi chạy hoặc `use` tại prompt. Đảm bảo source tương ứng đúng build đang chạy; source khác phiên bản có thể khiến việc đối chiếu line number gây hiểu nhầm.

## 11. Debug nhiều thread

JDB cung cấp các lệnh:

~~~text
threads
threadgroups
thread 2
where 2
suspend 2
resume 2
interrupt 2
threadlocks 2
lock order
~~~

- `threads`: liệt kê thread trong thread group hiện tại.
- `thread <id>`: chọn thread mặc định để debug.
- `suspend` và `resume`: tạm dừng hoặc tiếp tục thread; nếu bỏ ID, mặc định áp dụng cho tất cả thread.
- `interrupt`: gửi interrupt cho thread.
- `threadlocks`: hiển thị thông tin lock của thread.
- `lock <expr>`: xem thông tin lock của object.

Khi breakpoint được kích hoạt, mặc định JDB có thể suspend toàn bộ thread để giữ trạng thái nhất quán cho việc kiểm tra. Điều này có thể làm request khác bị chậm hoặc timeout. JDB có cú pháp `stop thread ...` để chỉ dừng thread được chỉ định trong một số tình huống; đọc `help` của phiên bản đang dùng trước khi áp dụng.

JDK 24 có option `-trackallthreads` để theo dõi cả virtual threads và platform threads. Nếu ứng dụng dùng virtual threads, bật option này khi cần liệt kê và theo dõi toàn bộ thread. Khả năng hiển thị và điều khiển chi tiết còn phụ thuộc JDK, connector và trạng thái thread.

## 12. Bắt exception và theo dõi field

### 12.1. Exception catchpoints

Dừng khi exception chưa được xử lý:

~~~text
catch uncaught java.lang.NullPointerException
run
~~~

Dừng khi exception được throw dù sau đó có thể được catch:

~~~text
catch all java.lang.IllegalArgumentException
~~~

Bỏ catchpoint:

~~~text
ignore uncaught java.lang.NullPointerException
~~~

Có thể dùng `catch caught` hoặc `catch all` tùy phạm vi cần theo dõi. Catchpoint ở các exception phổ biến có thể khiến debugger dừng rất nhiều lần; chọn loại exception cụ thể và xóa catchpoint sau khi hoàn thành.

### 12.2. Field watchpoint

Theo dõi việc truy cập hoặc thay đổi field:

~~~text
watch access com.example.Account.balance
watch all com.example.Account.balance
unwatch all com.example.Account.balance
~~~

`watch access` theo dõi access; `watch all` theo dõi các thao tác access/modification theo hỗ trợ của JDB. Watchpoint có thể tạo nhiều lần dừng trong code tần suất cao, nên chỉ bật cho field đang điều tra.

## 13. Breakpoint có điều kiện và tự động hóa command

Cú pháp `stop` tiêu chuẩn của JDB đặt breakpoint theo class/method hoặc class/line; command list của JDK 24 không cung cấp mệnh đề condition giống một số IDE.

Cách làm việc khi cần điều kiện:

1. Đặt breakpoint ở method hoặc dòng gần vị trí cần kiểm tra.
2. Khi dừng, dùng `print` để xem giá trị.
3. Nếu điều kiện chưa đúng, dùng `cont` để tiếp tục.
4. Nếu có thể, thêm guard có chủ đích vào debug build hoặc viết test tái hiện điều kiện.

Có thể tự chạy một command mỗi khi chương trình dừng:

~~~text
monitor where
monitor locals
monitor print orderId
~~~

Liệt kê monitor command:

~~~text
monitor
~~~

Xóa monitor theo số thứ tự:

~~~text
unmonitor 1
~~~

Có thể lưu chuỗi lệnh vào file và chạy lại:

~~~text
read debug-commands.txt
~~~

File command hữu ích cho quy trình tái hiện lặp lại, nhưng cần bảo đảm thứ tự lệnh phù hợp với trạng thái của JVM. Một lệnh `print` trước khi thread dừng hoặc biến vào scope có thể báo lỗi.

## 14. Kết nối vào JVM local đang chạy

Có hai cách attach thường dùng.

### 14.1. Attach theo PID

Xem connector khả dụng:

~~~text
jdb -listconnectors
~~~

Nếu JDK cung cấp connector `com.sun.jdi.ProcessAttach`, attach bằng PID:

~~~text
jdb -connect com.sun.jdi.ProcessAttach:pid=18240
~~~

Connector này attach tới process cục bộ và cần quyền attach của hệ điều hành, cùng user hoặc quyền tương đương theo nền tảng. Nó không biến một JVM bất kỳ thành remote-debuggable; target phải hỗ trợ attach và attach mechanism không bị tắt.

### 14.2. Attach qua socket

Nếu target đã bật JDWP socket listener ở `localhost:5005`:

~~~text
jdb -attach localhost:5005
~~~

Hoặc dùng connector tường minh:

~~~text
jdb -connect com.sun.jdi.SocketAttach:hostname=localhost,port=5005
~~~

`-attach` nhận địa chỉ socket; không truyền PID vào đây. Nếu cần attach theo PID, dùng connector ProcessAttach.

## 15. Bật JDWP cho JVM đích

Khởi chạy ứng dụng với JDWP agent:

~~~text
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar application.jar
~~~

Ý nghĩa:

- `transport=dt_socket`: dùng TCP socket transport.
- `server=y`: JVM đích mở socket để debugger kết nối.
- `suspend=n`: ứng dụng không chờ debugger mới bắt đầu chạy.
- `address=127.0.0.1:5005`: bind endpoint vào loopback trên máy đích.

Nếu muốn debugger kết nối trước khi `main` chạy:

~~~text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005
~~~

Với `suspend=y`, JVM dừng lúc khởi động cho đến khi debugger kết nối. Nếu debugger không kết nối, service có thể không bắt đầu xử lý request.

Để debug ứng dụng chạy trên máy khác, nên tạo SSH tunnel tới endpoint loopback:

~~~sh
ssh -L 5005:127.0.0.1:5005 ops@jvm-host.example.internal
~~~

Giữ tunnel mở, sau đó trên máy quản trị:

~~~text
jdb -attach localhost:5005
~~~

Cách này giữ JDWP listener trên loopback của máy đích và chuyển tiếp kết nối qua SSH. Nếu cần bind vào interface quản trị thay vì loopback, hãy giới hạn firewall/security group chỉ cho IP quản trị và dùng mạng tin cậy.

## 16. Bảo mật khi debug remote

JDWP là giao thức điều khiển debugger, không phải dịch vụ quản trị có authentication/authorization tích hợp như một API ứng dụng. Người kết nối được có thể đọc trạng thái, dừng thread, thay đổi biến và đánh giá biểu thức trong JVM. Vì vậy, mở JDWP port ra mạng công cộng có thể tương đương trao quyền điều khiển process.

Quy tắc vận hành:

- Không public JDWP port ra Internet.
- Ưu tiên bind `127.0.0.1` và dùng SSH tunnel.
- Nếu buộc phải bind interface mạng, chỉ cho phép IP quản trị cụ thể qua firewall.
- Không bật JDWP thường trực trên production nếu không có yêu cầu được phê duyệt.
- Dùng `suspend=n` nếu không muốn JVM chờ debugger khi khởi động.
- Chỉ mở debug trong cửa sổ incident và đóng listener/tunnel sau khi hoàn tất.
- Ghi lại PID, host, port, thời gian, người vận hành và mục đích.
- Không để phiên debugger bỏ quên khi service đang nhận traffic.

Breakpoint toàn JVM có thể làm tất cả request chờ. Một phiên debugger cần được xem như thao tác vận hành có khả năng ảnh hưởng trực tiếp tới availability.

## 17. Ví dụ Java 17+: đặt breakpoint, xem biến và tiếp tục

Tạo file `JdbDemo.java`:

~~~java
public final class JdbDemo {
    private JdbDemo() {
    }

    public static void main(String[] args) {
        int quantity = 3;
        int unitPrice = 120;
        int amount = calculate(quantity, unitPrice);
        System.out.println("AMOUNT=" + amount);
    }

    static int calculate(int quantity, int unitPrice) {
        int subtotal = quantity * unitPrice;
        int discount = 60;
        int result = subtotal - discount;
        return result;
    }
}
~~~

Biên dịch với debug symbols:

~~~text
javac --release 17 -g -d out JdbDemo.java
~~~

Khởi chạy JDB:

~~~text
jdb -classpath out JdbDemo
~~~

Tại prompt:

~~~text
stop in JdbDemo.calculate
run
~~~

JDB đặt deferred breakpoint rồi dừng khi `calculate` được gọi. Thực hiện:

~~~text
where
locals
print quantity
print unitPrice
next
locals
print subtotal
cont
~~~

Kết quả quan trọng cần quan sát:

- `where` cho thấy `JdbDemo.calculate` được gọi từ `JdbDemo.main`.
- `locals` tại đầu method cho thấy `quantity = 3` và `unitPrice = 120`.
- `next` thực thi dòng tính subtotal và dừng ở dòng tiếp theo.
- `locals` lúc này có `subtotal = 360`.
- `print subtotal` trả về `360`.
- `cont` cho phép chương trình hoàn tất.

Stdout của ứng dụng:

~~~text
AMOUNT=300
~~~

Kết thúc debugger bằng:

~~~text
exit
~~~

Số dòng và phần prompt phụ thuộc cách format output của JDK, nhưng giá trị biến và stdout của chương trình trên là xác định.

## 18. Troubleshooting thường gặp

### `No source found`

**Nguyên nhân:** JDB không tìm thấy source hoặc source path không khớp package.

**Cách xử lý:** truyền `-sourcepath`, dùng `use <path>` và kiểm tra source tương ứng đúng build đang chạy.

### Breakpoint bị deferred nhưng không bao giờ hit

**Nguyên nhân:** class chưa được load, method không được gọi, class name sai hoặc breakpoint đặt vào dòng không có bytecode.

**Cách xử lý:** kiểm tra `classes`, `methods`, call path, package đầy đủ và dùng breakpoint theo method để khoanh vùng.

### `locals` không hiển thị biến

**Nguyên nhân:** class file thiếu local variable debug information, biến chưa vào scope hoặc frame đang chọn không đúng.

**Cách xử lý:** biên dịch với `javac -g`, chọn đúng thread/frame bằng `thread`, `where`, `up` và `down`.

### `Name unknown` khi `print`

**Nguyên nhân:** biến không tồn tại trong frame hiện tại, chưa được khởi tạo, đã ra khỏi scope hoặc tên field cần qualifier.

**Cách xử lý:** xem `where`, `locals`, chọn đúng frame rồi dùng biểu thức có tên object/class phù hợp.

### Không attach được bằng socket

**Nguyên nhân:** target chưa bật JDWP, sai host/port, sai transport, firewall chặn hoặc JVM đã thoát.

**Cách xử lý:** xác nhận startup option `-agentlib:jdwp`, listener đang chạy, địa chỉ bind, port và đường mạng từ máy debugger.

### Attach PID thất bại

**Nguyên nhân:** target không hỗ trợ attach, chạy bằng user khác, attach mechanism bị tắt hoặc process nằm trong PID namespace khác.

**Cách xử lý:** chạy debugger với quyền phù hợp trên đúng host/container, kiểm tra `-XX:+DisableAttachMechanism` và dùng connector có trong `jdb -listconnectors`.

### JVM bị treo sau khi bật JDWP

**Nguyên nhân:** `suspend=y` làm JVM chờ debugger trước khi tiếp tục.

**Cách xử lý:** kết nối debugger vào đúng endpoint hoặc khởi động lại với `suspend=n` nếu không cần dừng trước `main`.

### Breakpoint làm request production timeout

**Nguyên nhân:** debugger suspend thread hoặc toàn VM tại breakpoint.

**Cách xử lý:** gỡ breakpoint, `cont`/`resume` các thread và kết thúc phiên debug. Dùng staging hoặc recording như JFR cho điều tra kéo dài.

### Không thấy virtual threads

**Nguyên nhân:** phiên JDB chưa bật theo dõi toàn bộ thread hoặc JDK/connector có giới hạn.

**Cách xử lý:** dùng `jdb -trackallthreads`, xem `threads` và kiểm tra hỗ trợ của JDK đích.

### Bước nhảy source line không như mong đợi

**Nguyên nhân:** compiler tối ưu, code đã instrument/obfuscate, lambda/synthetic method hoặc source không trùng bytecode.

**Cách xử lý:** xác minh artifact và source version, biên dịch lại với debug symbols và dùng `stepi` khi cần kiểm tra bytecode-level.

## 19. Quy trình debug JVM có kiểm soát

1. Xác định triệu chứng, service, host/container và đúng build đang chạy.
2. Ưu tiên tái hiện trên local hoặc staging.
3. Biên dịch với debug symbols nếu tự build được.
4. Chọn launch mode hoặc attach connector phù hợp.
5. Đặt breakpoint hẹp tại method/dòng nghi vấn.
6. Dùng `where`, `locals`, `print` và `next` để tìm giá trị sai.
7. Kiểm tra các thread liên quan nếu lỗi có tính đồng thời.
8. Bắt exception cụ thể nếu lỗi chỉ xuất hiện theo nhánh hiếm.
9. Ghi lại kết quả, stack frame, giá trị và bước tái hiện.
10. Xóa breakpoint, tiếp tục/resume thread và đóng debugger.
11. Tắt JDWP listener hoặc SSH tunnel sau khi điều tra.
12. Chuyển kết quả thành test hồi quy hoặc log/metric phù hợp.

Không để lại breakpoint, JDWP port hoặc listener sau khi kết thúc. Nếu thay đổi state bằng lệnh `set` hoặc `eval`, ghi lại chính xác thay đổi đó vì phiên debug có thể làm hành vi ứng dụng khác với lần chạy bình thường.

## 20. Checklist trước khi dùng `jdb`

- [ ] Đã xác nhận đúng JDK và đúng JVM đích.
- [ ] Đã xác định source code khớp với artifact đang chạy.
- [ ] Đã biên dịch với `-g` nếu cần xem local variables.
- [ ] Đã cấu hình đúng classpath và sourcepath.
- [ ] Đã chọn launch, ProcessAttach hay SocketAttach đúng tình huống.
- [ ] Đã đặt breakpoint vào method/dòng có thể thực thi.
- [ ] Đã biết cách dùng `where`, `locals`, `print`, `next` và `cont`.
- [ ] Đã chọn đúng thread và stack frame.
- [ ] Catchpoint/watchpoint được giới hạn đúng mục tiêu.
- [ ] Đã đánh giá ảnh hưởng của việc suspend thread/JVM.
- [ ] JDWP chỉ mở trên loopback hoặc mạng quản trị được giới hạn.
- [ ] Không public JDWP port ra Internet.
- [ ] Đã đóng tunnel, listener và debugger sau khi hoàn tất.
- [ ] Đã chuyển phát hiện thành test hoặc bằng chứng vận hành có thể lặp lại.

## 21. Tài liệu tham khảo

- Oracle JDK 24 — `jdb` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html
- Oracle JDK 24 — JPDA Connection and Invocation: https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html
- Oracle JDK 24 — Java Debug Wire Protocol: https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jdwp-spec.html
- Java SE 24 — Java Debug Interface: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/module-summary.html
- Oracle JDK 24 — `javac` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html

`jdb` giúp dừng và kiểm tra JVM ngay tại vị trí code đang chạy. Bắt đầu với debug symbols, breakpoint hẹp, `where` và `locals`; dùng stepping để theo dõi luồng dữ liệu, rồi tiếp tục chương trình bằng `cont`. Khi attach từ xa, bảo vệ JDWP bằng loopback/SSH tunnel và đóng endpoint ngay sau phiên điều tra.