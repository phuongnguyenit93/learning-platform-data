# Tìm tệp hoặc socket còn mở từ thông báo lỗi

Khi tạo checkpoint CRaC, ứng dụng có thể gặp lỗi liên quan tới file descriptor, file đang mở, socket, pipe hoặc một tài nguyên native do thư viện quản lý. Thông báo lỗi đôi khi chỉ nêu số descriptor, inode, đường dẫn hoặc một mã lỗi của hệ điều hành. Để tìm đúng tài nguyên, cần đối chiếu thông báo đó với danh sách handle mà tiến trình đang giữ, sau đó lần ngược về thành phần Java hoặc thư viện đã mở nó.

Trên Linux, các công cụ hữu ích nhất thường là /proc/PID/fd, lsof, ss và fuser. Với socket, cần kết hợp thông tin inode trong /proc hoặc lsof với trạng thái kết nối từ ss. Trên Windows có thể dùng Sysinternals Handle, Process Explorer và các lệnh PowerShell về TCP/UDP endpoint.

Mục tiêu không chỉ là tìm ra file hay socket nào đang mở. Cần xác định ai sở hữu nó, vì sao nó còn mở tại thời điểm checkpoint, tài nguyên đó có được engine hỗ trợ hay cần đóng, và cách khôi phục nó sau restore.

## 1. Đọc thông báo lỗi trước khi chạy công cụ

Trước tiên, giữ lại toàn bộ log của lần checkpoint thất bại. Đừng chỉ lấy dòng cuối cùng: dòng lỗi có thể chỉ ra file descriptor, còn các dòng trước đó mới cho biết Resource hoặc bước native nào đang xử lý tài nguyên.

Thông tin cần trích xuất:

- Thời điểm và PID của tiến trình bị checkpoint.
- Giai đoạn xảy ra lỗi: callback beforeCheckpoint, bước dump của engine hay bước restore.
- Số file descriptor nếu log có nêu, ví dụ FD 17.
- Đường dẫn, inode, loại handle hoặc địa chỉ socket nếu có.
- Mã lỗi hệ điều hành như EBADF, EMFILE, ENFILE, EADDRINUSE hoặc EOPNOTSUPP.
- Tên Resource, class Java, thư viện hoặc native component xuất hiện trong stack trace.
- Tên checkpoint engine và phiên bản nếu log cung cấp.

Một log minh họa có thể có dạng:

~~~text
Checkpoint failed while saving process 2481
Unsupported file descriptor: fd=17
Target: socket:[73192]
Native checkpoint operation returned EOPNOTSUPP
~~~

Đây chỉ là ví dụ định dạng, không phải thông báo chuẩn của mọi CRaC runtime. Nếu log có số FD 17 và socket inode 73192, có thể dùng hai giá trị đó để tìm socket tương ứng trong tiến trình. Nếu log nêu đường dẫn file, tìm đường dẫn trong danh sách FD và xác định process đang giữ nó.

### Phân biệt lỗi Java callback và lỗi checkpoint engine

Lỗi có thể phát sinh ở hai tầng:

| Nơi phát sinh | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|
| Resource.beforeCheckpoint | Stack trace Java, tên class Resource, lỗi flush/close hoặc timeout | Tìm thành phần sở hữu tài nguyên và logic callback |
| JDK/CRaC runtime | Log runtime, cảnh báo về trạng thái JVM hoặc native handle | Đối chiếu phiên bản JDK/CRaC và cấu hình runtime |
| Checkpoint engine | Lỗi dump native, FD, socket, namespace hoặc mã lỗi kernel | Đối chiếu FD với /proc, lsof, ss và log engine |
| Restore | Lỗi mở lại file, kết nối, credential hoặc callback afterRestore | Kiểm tra tài nguyên đã thay đổi trong thời gian checkpoint và logic phục hồi |

Không nên kết luận rằng mọi file descriptor được engine báo đều là lỗi của ứng dụng. Một số descriptor thuộc JVM, agent hoặc runtime. Ngược lại, một callback Java hoàn tất không chứng minh mọi handle native đều có thể được checkpoint.

## 2. Tìm PID của tiến trình Java

Trên Linux, có thể tìm process bằng ps:

~~~shell
ps -eo pid,ppid,user,comm,args | grep '[j]ava'
~~~

Nếu biết một phần tên ứng dụng:

~~~shell
pgrep -af 'order-service'
~~~

Chọn đúng PID của process đang tạo checkpoint. Tránh nhầm PID của Gradle, shell launcher, sidecar hoặc một Java process khác.

Trong container, PID nhìn thấy từ bên trong container có thể khác PID trên host. Nếu đang chạy lệnh bên trong container, dùng PID trong PID namespace đó khi truy cập /proc bên trong. Nếu điều tra từ host, cần xác định host PID tương ứng và namespace mà process đang sử dụng.

Có thể xem thông tin process:

~~~shell
ps -p 2481 -o pid,ppid,user,lstart,stat,cmd
cat /proc/2481/status
~~~

Thay 2481 bằng PID thực tế. Không sao chép PID từ một lần chạy cũ vì PID có thể được tái sử dụng sau khi process kết thúc.

## 3. Liệt kê file descriptor bằng /proc

Trên Linux, mỗi process có thư mục /proc/PID/fd. Mỗi entry là một symbolic link tới đối tượng mà file descriptor đang tham chiếu.

Ví dụ:

~~~shell
ls -l /proc/2481/fd
~~~

Kết quả minh họa:

~~~text
0 -> /dev/null
1 -> /var/log/order-service/stdout.log
2 -> /var/log/order-service/stderr.log
3 -> /opt/app/config/application.yml
7 -> socket:[73192]
9 -> pipe:[82014]
12 -> anon_inode:[eventpoll]
17 -> socket:[84501]
~~~

Ý nghĩa thường gặp:

- Số bên trái là file descriptor trong process.
- Đường dẫn thông thường có thể là file, device hoặc file trong filesystem.
- socket:[inode] là socket được kernel biểu diễn bằng inode.
- pipe:[inode] là một đầu pipe.
- anon_inode:[...] thường là tài nguyên kernel như eventpoll hoặc eventfd.
- memfd: có thể là file-backed memory object nằm trong RAM.

Không phải entry nào cũng là file thông thường. Nếu engine báo unsupported descriptor, loại đối tượng như pipe, eventpoll, socket hoặc device có thể quan trọng hơn tên đường dẫn.

### Tìm một FD cụ thể

Nếu thông báo lỗi nêu FD 17:

~~~shell
readlink /proc/2481/fd/17
cat /proc/2481/fdinfo/17
~~~

readlink cho biết descriptor đang trỏ tới đối tượng nào. fdinfo có thể cung cấp flags, position, mount ID hoặc thông tin phụ thuộc loại descriptor và kernel.

Ví dụ fdinfo của một file:

~~~text
pos:    4096
flags:  0100002
mnt_id: 32
ino:    912345
~~~

pos là vị trí file hiện tại của descriptor. Với stream có buffer, vị trí file vật lý có thể khác vị trí logic mà ứng dụng đã xử lý. Không dùng pos làm offset nghiệp vụ nếu có BufferedInputStream hoặc lớp đọc trước dữ liệu.

### Liệt kê tất cả FD cùng đích

Có thể dùng shell loop để in số FD và đích:

~~~shell
for fd in /proc/2481/fd/*; do
    name=$(basename "$fd")
    printf '%s -> ' "$name"
    readlink "$fd"
done
~~~

Nếu shell hoặc quyền truy cập không cho đọc một entry, ghi nhận lỗi và tiếp tục điều tra bằng lsof. Danh sách FD có thể thay đổi trong lúc process đang chạy; kết quả là ảnh chụp tại thời điểm lệnh đọc, không phải snapshot nguyên tử của toàn bộ ứng dụng.

## 4. Dùng lsof để tìm file đang mở

lsof (list open files) liệt kê các file và handle mà process đang giữ. Trên Linux, socket, pipe và nhiều đối tượng kernel cũng được hiển thị như open file.

Liệt kê mọi tài nguyên của một PID:

~~~shell
lsof -nP -p 2481
~~~

Các tùy chọn:

- -p 2481: chỉ xem process có PID 2481.
- -n: không phân giải địa chỉ mạng thành hostname.
- -P: không đổi port number thành tên service.

Một dòng kết quả thường có các cột COMMAND, PID, USER, FD, TYPE, DEVICE, SIZE/OFF, NODE và NAME. Cột FD chứa số descriptor và có thể có hậu tố như r, w, u biểu thị quyền mở. Cột NODE thường chứa inode; NAME có thể chứa đường dẫn hoặc thông tin socket.

### Tìm file theo đường dẫn

Nếu log nêu một file cụ thể:

~~~shell
lsof -nP -- /var/data/orders/current.log
~~~

Hoặc tìm trong một process:

~~~shell
lsof -nP -p 2481 | grep '/var/data/orders'
~~~

Nếu nhiều process cùng mở file, cần xác định descriptor nào thuộc process đang checkpoint. Không đóng file từ process khác chỉ vì đường dẫn giống nhau.

### Tìm file đã bị xóa nhưng vẫn mở

Một tình huống dễ bỏ sót là file đã bị xóa khỏi directory nhưng process vẫn giữ descriptor. Linux cho phép process tiếp tục truy cập inode đó cho tới khi descriptor cuối cùng được đóng.

Tìm file đã unlink nhưng còn mở:

~~~shell
lsof -nP -p 2481 +L1
~~~

Hoặc tìm chuỗi deleted:

~~~shell
lsof -nP -p 2481 | grep '(deleted)'
~~~

Ví dụ:

~~~text
java 2481 app  15w REG  8,1  1048576 912345 /var/log/app.log (deleted)
~~~

Điều này thường xảy ra khi logrotate xóa hoặc đổi tên file trong khi logger vẫn giữ handle cũ. Ứng dụng tiếp tục ghi vào inode cũ, dù đường dẫn đã bị xóa. Nếu checkpoint cần đường dẫn hoặc file descriptor có thể phục hồi, tình huống này có thể gây lỗi hoặc làm mất khả năng tìm lại file theo tên.

Giải pháp thường là yêu cầu logger đóng file cũ và mở lại file theo cơ chế của logging framework. Không tự xóa thêm file hoặc đóng descriptor từ bên ngoài khi ứng dụng vẫn đang ghi.

## 5. Tìm socket còn mở

Socket cũng xuất hiện trong /proc/PID/fd dưới dạng socket:[inode]. Có thể dùng lsof để lọc socket của process:

~~~shell
lsof -nP -a -p 2481 -i
~~~

Lệnh trên hiển thị socket Internet mà process đang sở hữu. Với Unix domain socket:

~~~shell
lsof -nP -U -p 2481
~~~

Các cột NAME thường thể hiện giao thức, địa chỉ local/remote và port. Ví dụ:

~~~text
java 2481 app  17u IPv4 84501 0t0 TCP 10.0.0.12:43120->10.0.0.20:5432 (ESTABLISHED)
java 2481 app  21u IPv6 84502 0t0 TCP *:8080 (LISTEN)
~~~

Đây chỉ là ví dụ. Tên host/port có thể được phân giải nếu không dùng -nP.

### Dùng ss để xem trạng thái kết nối

ss hiển thị socket của kernel, trạng thái TCP và thông tin process khi quyền truy cập cho phép:

~~~shell
ss -tanp
ss -uanp
ss -xap
~~~

Ý nghĩa:

- -t: TCP.
- -u: UDP.
- -a: cả socket đang listen và socket không listen.
- -n: hiển thị địa chỉ và port dạng số.
- -p: hiển thị process nếu có quyền.
- -x: Unix domain socket.

Lọc theo port:

~~~shell
ss -tanp '( sport = :8080 or dport = :8080 )'
~~~

Lọc theo PID trong output có thể thực hiện bằng cách đọc cột process, nhưng định dạng phụ thuộc phiên bản iproute2. lsof -p PID -i thường tiện hơn khi đã biết PID.

### Đối chiếu socket inode với FD

Giả sử:

- /proc/2481/fd/17 trỏ tới socket:[84501].
- lsof -nP -p 2481 -i hiển thị FD 17, NODE 84501.
- ss -tanp hiển thị kết nối TCP tương ứng.

Ba nguồn này giúp xác định FD 17 là socket nào, local/remote endpoint và trạng thái hiện tại.

Nếu ss -p không hiện process, có thể do thiếu quyền hoặc socket thuộc network namespace khác. Kiểm tra từ đúng namespace và với quyền đủ để đọc thông tin process. Trên Linux, /proc/PID/net phản ánh network namespace của process; nó không phải danh sách socket riêng của process đó.

Trong container, có thể cần chạy lệnh trong network namespace của process từ host:

~~~shell
nsenter -t 2481 -n ss -tanp
~~~

Lệnh này cần quyền phù hợp và chỉ nên dùng trong môi trường vận hành được phép. Thay 2481 bằng host PID đúng của process. Nếu đã ở trong container, dùng PID và namespace hiện tại thay vì nhầm sang PID host.

### Phân biệt trạng thái socket

Một số trạng thái TCP thường gặp:

| Trạng thái | Ý nghĩa tổng quát | Điều cần kiểm tra |
|---|---|---|
| LISTEN | Socket chờ kết nối đến | Server listener có cần đóng trước checkpoint và mở lại sau restore không? |
| ESTABLISHED | Kết nối đang hoạt động | Peer có giữ session hay sẽ timeout khi process tạm dừng? |
| CLOSE-WAIT | Peer đã đóng, ứng dụng chưa đóng socket cục bộ | Có thể ứng dụng chưa xử lý EOF hoặc chưa giải phóng connection |
| FIN-WAIT / LAST-ACK | Kết nối đang trong quá trình đóng | Kiểm tra thread và logic đóng socket |
| TIME-WAIT | Kernel giữ trạng thái TCP sau khi đóng kết nối | Thường không có file descriptor ứng dụng đang mở tương ứng |

Không kết luận mọi TIME-WAIT là socket còn mở của Java process. TIME-WAIT thường là trạng thái TCP ở kernel sau khi socket đã đóng; nó có thể ảnh hưởng việc bind lại địa chỉ/port nhưng không nhất thiết là FD còn được process giữ.

## 6. Tìm process đang giữ một file hoặc port

Khi chỉ biết đường dẫn file:

~~~shell
fuser -v /var/data/orders/current.log
~~~

Khi chỉ biết TCP port:

~~~shell
ss -ltnp 'sport = :8080'
~~~

Hoặc:

~~~shell
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Khi chỉ biết Unix socket path:

~~~shell
lsof -nP -U | grep '/run/service.sock'
~~~

Các lệnh này giúp xác định process sở hữu tài nguyên. Trước khi xử lý, xác nhận PID có đúng là ứng dụng đang checkpoint hay không. Không dùng fuser -k hoặc lệnh kill để xử lý tự động nếu chưa hiểu tác động; chúng có thể dừng process đang phục vụ traffic hoặc ghi dữ liệu.

## 7. Những mã lỗi thường gặp và cách diễn giải

Thông báo native có thể chứa mã lỗi POSIX. Ý nghĩa chính xác phụ thuộc system call và engine, nhưng các mã sau thường gợi ý hướng điều tra:

| Mã lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| EMFILE | Process đã đạt giới hạn file descriptor | Đếm FD, tìm leak, kiểm tra ulimit và vòng đời handle |
| ENFILE | File table toàn hệ thống đã đạt giới hạn | Kiểm tra tải trên host và các process khác |
| EBADF | Descriptor không hợp lệ hoặc đã đóng | Tìm race giữa close/use, FD bị tái sử dụng hoặc lỗi quản lý handle |
| EADDRINUSE | Địa chỉ/port đang được sử dụng | Tìm listener hoặc process giữ port; xem xét socket lifecycle và TIME-WAIT |
| EOPNOTSUPP | Thao tác hoặc loại tài nguyên không được hỗ trợ | Xác định loại FD và giới hạn của checkpoint engine |
| ENOENT | Đường dẫn hoặc đối tượng không tồn tại | Kiểm tra file đã bị xóa/đổi tên, mount và working directory |
| EACCES / EPERM | Không đủ quyền | Kiểm tra user, capabilities, namespace và permission |

Không phải mọi log dùng tên errno; có thể chỉ in số hoặc chuỗi riêng của runtime. Tra cứu theo đúng engine và system call trong log. Một mã lỗi đơn lẻ không đủ để xác định nguyên nhân nếu chưa biết thao tác nào thất bại.

### EMFILE và ENFILE

Đếm số FD đang mở:

~~~shell
ls -1 /proc/2481/fd | wc -l
ulimit -n
cat /proc/2481/limits
~~~

ulimit -n trong shell hiện tại không nhất thiết là giới hạn của process đã chạy từ một service manager khác. /proc/PID/limits phản ánh giới hạn của process mục tiêu.

Trong Java, có thể đọc số lượng descriptor hiện tại trên nền tảng Unix thông qua MXBean của JDK:

~~~java
import java.lang.management.ManagementFactory;

import com.sun.management.UnixOperatingSystemMXBean;

public final class FileDescriptorMetrics {
    public static void print() {
        var bean = ManagementFactory.getOperatingSystemMXBean();
        if (bean instanceof UnixOperatingSystemMXBean unix) {
            System.out.println("openFD="
                    + unix.getOpenFileDescriptorCount());
            System.out.println("maxFD="
                    + unix.getMaxFileDescriptorCount());
        }
    }
}
~~~

MXBean chỉ cung cấp số lượng FD hiện tại và giới hạn trên nền tảng hỗ trợ. Nó không liệt kê đường dẫn, socket hay object Java đang sở hữu từng descriptor. Dùng /proc hoặc lsof để tìm từng tài nguyên.

Nếu số FD tăng liên tục theo thời gian, hãy kiểm tra các đường tạo stream, channel, socket, executor, HTTP client, JDBC pool và native library. Tăng ulimit có thể giảm triệu chứng nhưng không sửa được leak.

## 8. Từ FD quay lại thành phần Java sở hữu

Hệ điều hành biết process và descriptor, nhưng không luôn biết object Java nào đã mở descriptor đó. Một FD có thể được tạo bởi:

- FileInputStream, FileOutputStream hoặc FileChannel.
- Socket, ServerSocket hoặc DatagramSocket.
- HTTP client, JDBC driver hoặc connection pool.
- Logging framework và appender.
- Native library qua JNI/JNA.
- JVM, JFR, agent hoặc framework.
- Pipe, process builder hoặc thư viện IPC.

### Dùng thông tin từ lsof

Nếu FD 17 trỏ tới /var/data/orders/current.log, tìm code sở hữu writer tới file đó. Nếu FD 17 là TCP connection tới database port 5432, tìm connection pool/driver tương ứng. Nếu đó là Unix socket tới agent, tìm thư viện hoặc process IPC đã tạo socket.

Tên file hoặc endpoint chỉ là manh mối; nhiều thành phần có thể cùng mở một đường dẫn hoặc kết nối tới cùng endpoint.

### Dùng thread dump

Thread dump giúp tìm thread đang thực hiện I/O hoặc giữ lock liên quan:

~~~shell
jcmd 2481 Thread.print
~~~

Hoặc:

~~~shell
jstack 2481
~~~

Thread dump không ánh xạ trực tiếp mọi FD sang object Java. Tuy nhiên, stack trace có thể cho biết thread đang ở trong SocketInputStream, FileChannel, JDBC driver, HTTP client hoặc thư viện cụ thể. Kết hợp thời điểm log, thread dump và FD inventory để lần ra chủ sở hữu.

Một số JVM yêu cầu quyền attach hoặc cấu hình cho phép attach. Nếu lệnh không hoạt động, dùng log ứng dụng, JFR hoặc công cụ quan sát đã được bật sẵn. Không khởi động lại process chỉ để lấy thread dump nếu điều đó làm mất trạng thái đang cần điều tra.

### Thêm log ở nơi tạo và đóng tài nguyên

Với tài nguyên do ứng dụng sở hữu, nên log:

- Tên component hoặc Resource.
- Loại tài nguyên: file, socket, channel hay client.
- Đường dẫn hoặc endpoint đã được làm sạch thông tin nhạy cảm.
- Thời điểm mở, đóng và mở lại.
- Trạng thái lifecycle hiện tại.
- Lỗi close/reopen nếu có.

Không log token, password, query có dữ liệu nhạy cảm hoặc payload. Với socket, chỉ log host/port đã được phép ghi nhận; với file, tránh ghi nội dung file hoặc thông tin nhạy cảm trong path.

## 9. Tài nguyên đặc biệt trong /proc

Không phải descriptor nào cũng tương ứng với một file hoặc socket mà ứng dụng có thể đóng trực tiếp.

| Đích trong /proc/PID/fd | Ý nghĩa có thể gặp | Hướng xử lý |
|---|---|---|
| pipe:[inode] | Pipe giữa thread/process hoặc subprocess | Xác định producer/consumer và vòng đời pipe |
| anon_inode:[eventpoll] | epoll instance | Tìm selector/event loop sở hữu nó |
| anon_inode:[eventfd] | Event notification descriptor | Tìm thư viện/runtime tạo eventfd |
| anon_inode:[timerfd] | Timer descriptor | Kiểm tra scheduler/native timer integration |
| memfd:name | File trong bộ nhớ | Xác định thư viện tạo memfd và engine support |
| /dev/* | Device handle | Kiểm tra driver và quyền truy cập |
| socket:[inode] | Socket kernel | Đối chiếu lsof và ss |

Ví dụ, Java NIO Selector trên Linux có thể sử dụng epoll bên dưới. Nếu engine báo một anon_inode eventpoll, đừng cố xóa descriptor bằng tay. Tìm Selector hoặc event loop sở hữu nó và xem JDK/CRaC runtime có hướng dẫn xử lý loại tài nguyên đó hay không.

Tương tự, descriptor do JNI/native library tạo cần được đóng bằng API của thư viện. Đóng FD trực tiếp từ shell trong khi JVM vẫn giữ object Java tương ứng có thể khiến FD number được kernel tái sử dụng cho tài nguyên khác; object cũ sau đó có thể thao tác nhầm descriptor mới.

## 10. Điều tra trong container và Kubernetes

Container thường có PID namespace và network namespace riêng. Vì vậy:

- PID bên trong container có thể khác host PID.
- /proc/PID/fd phải được đọc trong PID namespace nhìn thấy process.
- ss phải chạy trong network namespace tương ứng để thấy đúng socket.
- Quyền đọc /proc có thể bị giới hạn bởi user, mount option, ptrace policy hoặc container security context.

Nếu đang ở trong container:

~~~shell
ps -ef
ls -l /proc/1/fd
ss -tanp
~~~

Nếu đang điều tra từ host, xác định host PID trước. Có thể dùng docker top với container Docker hoặc công cụ runtime tương ứng để tìm PID. Trong Kubernetes, thông tin process có thể cần được lấy từ trong container hoặc qua node-level diagnostic theo quyền của đội vận hành.

Nếu dùng host PID và cần xem network namespace của process:

~~~shell
nsenter -t HOST_PID -n ss -tanp
~~~

Thay HOST_PID bằng PID thực tế. Không chạy nsenter hoặc công cụ host-level nếu không có quyền vận hành phù hợp. Nếu container bị giới hạn capability, việc không đọc được socket không chứng minh socket không tồn tại.

### Lưu ý về sidecar và process khác

Một Pod có thể chứa nhiều container, mỗi container có process và network namespace tùy cấu hình. Socket được mở bởi sidecar không nhất thiết thuộc JVM. Nếu log engine nêu PID của JVM, chỉ điều tra FD của PID đó trước; sau đó mới kiểm tra process khác nếu lỗi cho thấy tài nguyên được chia sẻ.

Không dừng sidecar hoặc xóa socket path để giải quyết một lỗi FD của JVM nếu chưa xác định quan hệ phụ thuộc. Điều đó có thể làm hỏng health check, service mesh hoặc kết nối IPC của workload.

## 11. Công cụ tương đương trên Windows

CRaC và checkpoint engine thường được sử dụng trên Linux, nhưng nếu cần điều tra một ứng dụng Java trên Windows hoặc một runtime/vendor có công cụ riêng, có thể dùng các công cụ sau.

### Sysinternals Handle

Handle của Microsoft Sysinternals liệt kê các handle đang mở của process:

~~~powershell
handle.exe -p 2481
~~~

Thay 2481 bằng PID thực tế. Có thể tìm theo tên file hoặc chuỗi handle bằng tùy chọn lọc của phiên bản Handle đang dùng. Đọc help của đúng bản công cụ trước khi chạy. Không dùng tùy chọn đóng handle cưỡng bức trong bước chẩn đoán; việc đó có thể làm ứng dụng hỏng trạng thái.

Process Explorer cũng cho phép chọn process, xem danh sách handle và tìm process đang giữ một file hoặc object. Đây là lựa chọn trực quan khi cần đối chiếu handle với process.

### Tìm TCP và UDP endpoint bằng PowerShell

Liệt kê TCP connection của PID:

~~~powershell
Get-NetTCPConnection -OwningProcess 2481 |
    Select-Object LocalAddress, LocalPort, RemoteAddress,
                  RemotePort, State, OwningProcess
~~~

Liệt kê UDP endpoint:

~~~powershell
Get-NetUDPEndpoint -OwningProcess 2481 |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Hoặc dùng netstat:

~~~powershell
netstat -ano
netstat -ano | findstr ":8080"
~~~

PID ở cột cuối của netstat có thể được đối chiếu với process:

~~~powershell
Get-Process -Id 2481
~~~

PowerShell cmdlet và output có thể khác giữa phiên bản Windows. Nếu cần tìm file handle, dùng Handle hoặc Process Explorer; Get-NetTCPConnection chỉ liệt kê endpoint mạng, không liệt kê file handle.

## 12. Ví dụ quy trình tìm socket từ lỗi FD

Giả sử log checkpoint nêu:

~~~text
checkpoint error: unsupported fd 17
~~~

Có thể điều tra theo trình tự:

**Bước 1: Xác nhận process và FD.**

~~~shell
ps -p 2481 -o pid,user,cmd
readlink /proc/2481/fd/17
cat /proc/2481/fdinfo/17
~~~

Nếu kết quả là socket:[84501], ghi lại inode 84501.

**Bước 2: Tìm thông tin socket của process.**

~~~shell
lsof -nP -a -p 2481 -i
~~~

Tìm dòng có FD 17 hoặc NODE 84501. Ghi nhận TCP/UDP, local endpoint, remote endpoint và trạng thái.

**Bước 3: Đối chiếu trạng thái từ kernel.**

~~~shell
ss -tanp
~~~

Nếu process ở network namespace riêng, chạy ss trong namespace tương ứng. Nếu lsof và ss không hiện cùng kết quả, kiểm tra quyền truy cập, thời điểm đọc và việc socket đã đóng trong lúc điều tra.

**Bước 4: Lần về chủ sở hữu Java.**

Kiểm tra thread dump và log kết nối để xác định client hoặc thư viện tạo socket. Nếu endpoint là database, kiểm tra JDBC pool. Nếu là HTTP endpoint, kiểm tra HTTP client hoặc connection pool. Nếu là Unix socket, xác định agent hoặc IPC library.

**Bước 5: Chọn chính sách lifecycle.**

Nếu socket không thể được engine hỗ trợ, dừng nhận request, drain các thao tác đang dùng socket, đóng client/connection trước checkpoint và tạo kết nối mới sau restore. Nếu thư viện đã có CRaC integration, dùng integration đó theo tài liệu của nó.

**Bước 6: Kiểm thử lại.**

Tạo checkpoint sau khi tài nguyên đã được xử lý. Sau restore, xác minh client mới kết nối được, không có FD cũ bị dùng lại và readiness chỉ mở khi dependency sẵn sàng.

## 13. Từ kết quả điều tra tới cách sửa lifecycle

Tìm thấy FD chỉ là bước đầu. Cần xử lý tại đúng owner:

| Tài nguyên tìm thấy | Chủ sở hữu thường gặp | Cách xử lý quanh checkpoint |
|---|---|---|
| InputStream/FileChannel | File reader hoặc repository | Dừng reader, lưu offset logic, đóng channel, mở lại sau restore |
| OutputStream/log file | Writer hoặc logging appender | Drain writer, flush, đóng và reopen qua API của framework |
| JDBC socket | Driver/connection pool | Drain transaction, đóng hoặc làm mới connection theo CRaC integration của pool/driver |
| HTTP socket | HTTP client/connection pool | Dừng request, đóng client hoặc connection theo hợp đồng, tạo lại sau restore |
| Server listener | Web server hoặc embedded server | Dùng integration CRaC của framework/server để đóng và bind lại đúng thứ tự |
| Unix domain socket | IPC client/server hoặc agent | Kiểm tra hỗ trợ của engine và tạo lại socket theo giao thức |
| Pipe/subprocess FD | ProcessBuilder hoặc thư viện native | Kết thúc hoặc quản lý subprocess, đóng stream và xác nhận engine support |
| epoll/eventfd | Selector hoặc event loop | Dùng lifecycle của JDK/framework; không đóng descriptor trực tiếp từ ngoài |
| Native handle | JNI/JNA hoặc SDK | Dùng API close/reopen chính thức của thư viện |

### Ví dụ Resource quản lý file channel

Ví dụ sau minh họa một Resource sở hữu FileChannel. Nó lưu vị trí đọc/ghi, đóng channel trước checkpoint và mở channel mới sau restore:

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ManagedFile implements Resource {
    private final Path path;
    private FileChannel channel;
    private long savedPosition;

    public ManagedFile(Path path) throws IOException {
        this.path = path;
        open();
        Core.getGlobalContext().register(this);
    }

    public synchronized FileChannel channel() {
        if (channel == null || !channel.isOpen()) {
            throw new IllegalStateException("File is not ready");
        }
        return channel;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (channel != null && channel.isOpen()) {
            savedPosition = channel.position();
            channel.force(true);
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        open();
        channel.position(savedPosition);
    }

    private void open() throws IOException {
        channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE);
    }
}
~~~

Đây là ví dụ quản lý một file do ứng dụng sở hữu. Trong ứng dụng thật, phải drain thread đang dùng channel trước callback. Nếu có buffer, vị trí channel có thể khác offset logic đã xử lý; hãy lưu offset nghiệp vụ phù hợp. force(true) có chi phí I/O và chỉ nên dùng khi yêu cầu độ bền dữ liệu cần thiết. Nếu checkpoint bị hủy sau khi channel đã đóng, bộ điều phối cần có đường mở lại tài nguyên cho process hiện tại trước khi nhận công việc.

Không dùng mẫu này để tự quản lý file descriptor của HTTP client, JDBC driver hoặc logging framework. Các thư viện đó có thể có pool, thread và native state riêng; hãy dùng API lifecycle mà chúng cung cấp.

## 14. Không đóng descriptor bằng tay từ bên ngoài process

Khi đã tìm ra FD 17, có thể muốn đóng nó ngay từ shell hoặc native debugger. Đây thường không phải cách sửa đúng cho một ứng dụng Java đang chạy.

Rủi ro gồm:

- Object Java vẫn giữ tham chiếu tới descriptor đã bị đóng.
- Kernel có thể tái sử dụng cùng số FD cho một tài nguyên khác.
- Lần đọc/ghi tiếp theo từ object cũ có thể nhận EBADF hoặc tác động nhầm tài nguyên.
- Thread khác có thể đang sử dụng descriptor tại thời điểm đóng.
- Connection pool có thể vẫn đánh dấu connection là hợp lệ.
- Callback afterRestore có thể mở thêm một handle trong khi handle cũ chưa được giải phóng đúng cách.

Hãy đóng tài nguyên qua object hoặc API sở hữu nó. Chỉ sử dụng công cụ đóng handle cưỡng bức khi tài liệu vận hành của hệ thống yêu cầu rõ ràng và đã đánh giá tác động.

Tương tự, không xóa file socket path đang được server sử dụng để cố làm hết lỗi. Xóa pathname không nhất thiết đóng socket đã bind; nó có thể khiến client mới không kết nối được hoặc tạo ra hai endpoint không nhất quán.

## 15. Quy trình điều tra ngắn gọn

Khi nhận được thông báo lỗi về file hoặc socket còn mở, có thể làm theo trình tự:

1. Lưu toàn bộ log của checkpoint và xác định PID, FD, path, inode hoặc errno.
2. Xác nhận đúng process và namespace.
3. Dùng /proc/PID/fd để xác định loại tài nguyên và inode.
4. Dùng lsof -p PID để tìm file, socket, pipe và tài nguyên đã bị xóa nhưng còn mở.
5. Nếu là socket, dùng lsof -i, lsof -U và ss để tìm endpoint/trạng thái.
6. Dùng thread dump, log ứng dụng và dependency graph để tìm owner Java/native.
7. Đọc hướng dẫn của CRaC runtime, checkpoint engine và thư viện sở hữu tài nguyên.
8. Đóng, flush, drain hoặc mở lại tài nguyên tại đúng lifecycle owner.
9. Kiểm tra đường phục hồi nếu checkpoint bị hủy sau khi beforeCheckpoint đã đóng tài nguyên.
10. Tạo checkpoint và restore thử trên môi trường tương thích; xác nhận FD, socket và readiness sau restore.

Trong lúc điều tra, chỉ dùng các lệnh đọc thông tin trước. Tránh kill process, đóng FD, xóa socket hoặc thay đổi giới hạn hệ thống khi chưa xác định nguyên nhân. Nếu cần chia sẻ output, loại bỏ token, username nhạy cảm, đường dẫn chứa bí mật và thông tin nội bộ không cần thiết.

## 16. Những hiểu nhầm thường gặp

**“Mỗi entry trong /proc/PID/fd là một file thông thường.”**

Không đúng. Entry có thể là socket, pipe, eventfd, epoll, memfd hoặc device. Cần đọc symbolic link và đối chiếu loại tài nguyên.

**“Socket TIME-WAIT là một FD còn mở của Java.”**

Không nhất thiết. TIME-WAIT thường là trạng thái TCP của kernel sau khi ứng dụng đã đóng socket. Hãy xác minh process ownership bằng lsof hoặc ss.

**“Đường dẫn file không còn tồn tại thì process không thể đang mở nó.”**

Không đúng trên Linux. File đã unlink vẫn có thể được giữ mở qua FD; dùng lsof +L1 để tìm.

**“Java MXBean cho biết chính xác file nào đang mở.”**

MXBean Unix chỉ cung cấp số lượng FD và giới hạn. Cần /proc hoặc lsof để liệt kê từng tài nguyên.

**“Có thể đóng FD bị lỗi bằng số FD từ shell.”**

Không nên. Đóng ngoài process có thể làm object Java mất đồng bộ và FD number được tái sử dụng. Đóng qua owner API.

**“Checkpoint báo lỗi socket thì chỉ cần tăng ulimit.”**

Tăng giới hạn FD chỉ hữu ích với lỗi giới hạn EMFILE/ENFILE. Nó không làm một socket hoặc loại FD không được engine hỗ trợ trở nên tương thích.

**“Lsof không hiển thị nghĩa là không có tài nguyên.”**

Có thể thiếu quyền, process nằm trong namespace khác, lsof chưa cài hoặc tài nguyên đã thay đổi trong lúc đọc. Đối chiếu /proc, ss và quyền truy cập.

## 17. Kết luận

Để tìm file hoặc socket còn mở từ thông báo lỗi, hãy bắt đầu từ PID, FD, inode, path và errno trong log. Trên Linux, /proc/PID/fd cho biết descriptor trỏ tới đâu; lsof giúp liệt kê file/socket và phát hiện file đã bị xóa nhưng còn mở; ss cung cấp trạng thái kết nối và endpoint. Trong container, cần điều tra đúng PID và network namespace. Trên Windows, dùng Sysinternals Handle/Process Explorer và các lệnh PowerShell về TCP/UDP.

Sau khi tìm thấy tài nguyên, lần ngược về thành phần Java hoặc native sở hữu nó rồi xử lý bằng lifecycle API của thành phần đó. Đừng đóng descriptor bằng tay chỉ dựa trên số FD. Với CRaC, cần phối hợp drain công việc, đóng hoặc chuẩn bị tài nguyên trước checkpoint, mở lại sau restore và chỉ nhận traffic khi dependency đã sẵn sàng.
