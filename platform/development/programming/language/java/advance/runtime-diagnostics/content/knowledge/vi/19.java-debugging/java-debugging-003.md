# 19.3 Khởi động ứng dụng với -agentlib:jdwp và hiểu server, suspend, address

## 1. Bài toán: vì sao JVM «đang nghe ở port 5005» mà ứng dụng vẫn chưa chạy?

Khi cần debug một service Java, ta có thể khởi động với JDWP:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Nhưng ba tùy chọn tưởng đơn giản lại quyết định ba hành vi **khác nhau**:

- `server=y/n`: **bên nào mở socket chờ (listen), bên nào chủ động kết nối (connect)**? `server` nói về **vai trò mạng của target JVM**, không phải “đây có phải máy chủ ứng dụng HTTP hay không”.
- `suspend=y/n`: JVM có **tạm dừng trước khi tải main class** để debugger có cơ hội đặt breakpoint ngay từ đầu hay không? Nó không có nghĩa “debugger chỉ được phép pause khi bật y”.
- `address=...`: **điểm cuối của kết nối JDWP**, có thể là bind address/port của target khi `server=y`, hoặc host/port debugger đang nghe khi `server=n`. Sai địa chỉ có thể gây lỗi kết nối, mở port ngoài ý muốn hoặc chờ debugger mãi không thấy ứng dụng ready.

Ví dụ trong phần đầu dùng JDK 17+ và HotSpot: JVM mở một cổng TCP chỉ trên loopback, chạy `main` ngay mà không đợi debugger kết nối, nhưng vẫn cho phép một debugger kết nối sau đó. Việc ứng dụng chạy có nghĩa **`suspend=n`**, không phụ thuộc vào tên `server` của agent.

**Mục tiêu:** đọc đúng cấu trúc `-agentlib:jdwp`; chọn tổ hợp `server/suspend/address` phù hợp; kết nối bằng IDE hoặc `jdb`; tự quan sát sự khác nhau giữa chạy ngay và chờ debugger; xử lý port/bind/container; bảo vệ JDWP khỏi truy cập trái phép.

## 2. JPDA, JDWP và vị trí của debug agent

**JPDA** (Java Platform Debugger Architecture) cung cấp các lớp giao tiếp debug:

- **JDI (Java Debug Interface)**: giao diện được IDE/`jdb` dùng để điều khiển và quan sát JVM đang debug.
- **JDWP (Java Debug Wire Protocol)**: giao thức trao đổi lệnh/sự kiện giữa debugger và JVM đích.
- **JVM TI**: giao diện tooling ở phía JVM; agent JDWP của HotSpot dùng các khả năng VM để phục vụ yêu cầu debugger.
- **Transport**: cơ chế mang các gói JDWP. Thông dụng nhất là TCP socket `dt_socket`. Trên HotSpot Windows có thể có `dt_shmem` (shared memory, cùng máy), không áp dụng cho debug qua TCP/Linux.

Sơ đồ tình huống quen thuộc:

~~~text
IDE / jdb (debugger)  -- TCP JDWP -->  Java target VM
         attach                           listens at
                                          127.0.0.1:5005
                              agentlib:jdwp,server=y
~~~

Trong trường hợp **`server=n`**, mũi tên thiết lập kết nối đảo chiều: debugger **listen**, target JVM **connect** tới `address`. Sau khi kết nối được thiết lập, debugger vẫn điều khiển target theo JDWP; `server=n` không biến Java app thành debugger.

Bật JDWP khi khởi động có nghĩa **nạp agent debug vào JVM trước khi chạy mã ứng dụng**. Chỉ mở IDE hoặc chạy `jdb` không tự biến bất kỳ JVM nào thành cổng debug đang nghe; muốn attach bằng cổng TCP thì target phải có agent tương ứng, hoặc dùng một cơ chế attach/instrumentation riêng được JVM/IDE hỗ trợ. Không coi `jcmd` và JDWP là một giao thức.

## 3. Cú pháp và giá trị mặc định: đừng đoán

Cú pháp thông dụng của Java launcher:

~~~text
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out MyMain
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Tham số `-agentlib:jdwp=...` phải được truyền cho **JVM launcher**, đứng **trước tên main class hoặc `-jar`**. Các sub-options ngăn bằng dấu phẩy, **không có khoảng trắng chèn giữa**. `jdwp` là tên agent library; không phải tên ứng dụng hoặc tên biến môi trường.

| Tùy chọn | Giá trị | Ý nghĩa | Mặc định theo tài liệu JPDA/JDK 17 |
| --- | --- | --- | --- |
| `transport` | `dt_socket` (phổ biến), `dt_shmem` (HotSpot Windows) | Chọn transport cho kết nối | **Bắt buộc**, không mặc định |
| `server` | `y` / `n` | `y`: target listen. `n`: target connect đến debugger | **`n`** |
| `suspend` | `y` / `n` | `y`: VMStart có policy SUSPEND_ALL; `n`: SUSPEND_NONE | **`y`** |
| `address` | `port` / `host:port` / `*:port` trong socket transport | Với `server=y` là chỗ target bind/listen; `server=n` là nơi target connect | Bắt buộc khi `server=n`, có thể bỏ khi `server=y` |
| `timeout` | Số mili giây, tùy transport | Giới hạn thời gian đợi attach/connect ở những transport hỗ trợ | Không timeout, nhưng mức hỗ trợ cần kiểm tra |
| `allow` | IP hoặc subnet cho socket khi `server=y` | Hạn chế địa chỉ có thể kết nối (tính năng của transport) | `*` khi không chỉ rõ |

Những defaults ít được nhớ nhưng quan trọng: nếu chỉ ghi `-agentlib:jdwp=transport=dt_socket,server=y,address=5005` thì **`suspend=y` mặc định**. JVM sẽ in thông báo đang listen, nhưng **`main` vẫn chưa chạy** cho đến khi debugger kết nối và resume.

Nên **ghi rõ `server`, `suspend` và `address`** trong cấu hình vận hành, dù có thể dựa vào default. Kiểm tra cú pháp được hỗ trợ bởi JDK đang dùng:

~~~bash
java -agentlib:jdwp=help -version
~~~

Lệnh này **in trợ giúp rồi thoát**, không khởi động ứng dụng. Các lựa chọn nâng cao như `onthrow`/`onuncaught` có thể trì hoãn khởi tạo agent tới khi một exception xuất hiện; đó là cấu hình riêng cho tình huống just-in-time debugging, **không cần** để hiểu hành vi khởi động cơ bản.

## 4. `server=y` và `server=n`: ai lắng nghe ai?

### 4.1 `server=y`: target JVM nghe, IDE/jdb attach

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out MyMain
~~~

Ý nghĩa:

1. Target JVM yêu cầu OS bind/listen trên `127.0.0.1:5005`.
2. Khi debugger được mở ở chế độ **Attach to remote JVM**, debugger chủ động nối tới host `127.0.0.1` port `5005`.
3. Nếu `suspend=n`, target **vào `main` ngay** bất kể debugger đã attach hay chưa. Debugger attach trễ có thể bỏ lỡ code chạy ngay lúc startup.
4. Khi attach thành công, debugger vẫn có quyền đặt breakpoint, tạm dừng thread/VM, xem stack/biến và resume theo cơ chế debug.

Đây là hướng phổ biến nhất khi chạy app local hoặc trong một môi trường chỉ cho phép tunnel có kiểm soát.

Ví dụ `jdb` trong terminal thứ hai:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Nếu `server=y` mà debugger cũng chọn **Listen** thay vì **Attach**, cả hai bên đều chờ và sẽ không có kết nối. Debugger cần dùng đúng loại connector.

### 4.2 `server=n`: debugger nghe, target JVM chủ động nối

~~~bash
# Khởi động debugger ở chế độ listen trước (trên cùng máy).
jdb -listen 5005
# Ở terminal khác, cho target kết nối tới debugger:
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5005 -cp out MyMain
~~~

Ở đây target JVM không mở cổng đợi IDE attach. Nó **chủ động kết nối tới listener của debugger** tại `127.0.0.1:5005`. Phía debugger chọn **Listen for debug connection** hoặc connector `SocketListen`, không phải Attach.

Nếu debugger chưa mở listener, JVM có thể thất bại ngay ở bước khởi tạo JDWP với lỗi connect/refused hoặc timeout. **`suspend=n` không bảo đảm bỏ qua lỗi khởi tạo kết nối khi `server=n`**; nó chỉ quyết định chính sách suspend ban đầu sau khi đã thiết lập được việc debug. Các hệ thống yêu cầu “ứng dụng phải lên ngay cả khi debugger vắng mặt” thường nên dùng `server=y,suspend=n` ở môi trường local/dev thay vì `server=n`.

`server=n` có thể hữu ích trong một số luồng debug chủ động kết nối từ target ra debugger, nhưng **không tự biến kết nối thành an toàn**: debugger đang nghe vẫn cần quyền truy cập mạng được kiểm soát.

### Bảng bốn tổ hợp

| `server` | `suspend` | Hành vi khởi tạo và thực thi |
| --- | --- | --- |
| `y` | `y` | Target **listen**, VM tạm dừng **trước khi load main class**; debugger attach và resume thì app mới chạy |
| `y` | `n` | Target **listen**, app **chạy ngay**; debugger có thể attach sau |
| `n` | `y` | Target **connect** tới debugger đang listen, rồi tạm dừng ban đầu cho debugger kiểm soát/resume |
| `n` | `n` | Target **connect** tới debugger; không đặt initial suspend, nhưng khởi tạo JDWP có thể vẫn thất bại nếu không nối được |

**Quy tắc nhớ:** `server` là *hướng kết nối*. `suspend` là *điểm dừng ban đầu*. Hai trục độc lập.

## 5. `suspend=y`: vì sao không thấy dòng log nào từ main?

Với lệnh:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out MyMain
~~~

JVM có thể in thông báo dạng:

~~~text
Listening for transport dt_socket at address: 5005
~~~

Tại thời điểm đó **chưa có bằng chứng rằng application đã vào `main`, bind cổng HTTP, load Spring context hoặc sẵn sàng nhận traffic**. Đây chỉ là debug agent đang chờ kết nối. Theo semantics JDWP, `suspend=y` khiến sự kiện VMStart mang chính sách `SUSPEND_ALL` trước khi nạp main class; debugger phải kết nối và gửi lệnh resume. Một số IDE có thể tự resume sau khi attach; với `jdb`, sau khi đặt breakpoint có thể dùng `cont` để tiếp tục.

Điều này có ích khi muốn dừng tại `main`, static initializer, bootstrap hoặc lỗi xảy ra ngay lúc startup. Nhưng nếu lỡ để `suspend=y` trong container:

- Health/readiness probe có thể thất bại vì HTTP server chưa khởi tạo.
- Deployment có thể treo ở trạng thái Starting dù JVM process vẫn tồn tại và port JDWP đang listen.
- Startup timeout của orchestration có thể kết thúc container trước khi debugger attach.
- Metrics/JFR của application chưa xuất hiện vì code chưa chạy.

Với debug không cần bắt lỗi startup, chọn `suspend=n` để tránh sự cố trên. Với debug cần break sớm, dùng `suspend=y` **có chủ đích**, trên môi trường và khoảng thời gian kiểm soát được, không để bật âm thầm trong production.

**Quan trọng:** `suspend=n` không cấm debugger suspend code sau này. Breakpoint `SUSPEND_ALL` hoặc `SUSPEND_EVENT_THREAD` khi đã attach vẫn có thể pause ứng dụng theo chính sách breakpoint; cần cân nhắc thread và request đang phục vụ.

## 6. `address`: loopback, wildcard, port và mô hình mạng

Với `transport=dt_socket` và `server=y` trong JDK 17+:

| `address` | Target listen ở đâu? | Khi nào dùng |
| --- | --- | --- |
| `127.0.0.1:5005` | Loopback IPv4 trên **host/network namespace của target** | Mặc định tốt cho local debug hoặc SSH tunnel trên remote host |
| `5005` | **Loopback** theo cú pháp JDWP hiện đại (JDK 9+) | Local debug ngắn gọn; vẫn nên ghi host rõ để dễ đọc |
| `localhost:5005` | Hostname `localhost` được resolve tại target; tùy IPv4/IPv6 | Chỉ khi đã kiểm tra address family và resolver đúng |
| `*:5005` | **Wildcard / tất cả network interfaces** tương ứng transport | Chỉ khi cần reach qua namespace/network và đã chặn truy cập bằng lớp bảo mật phù hợp |
| `127.0.0.1:0` | Loopback với **port do OS chọn**; agent in port thật | Lab nhiều JVM, tránh xung đột port; đọc port in ra trước khi attach |
| `[::1]:5005` | Loopback IPv6 khi JVM/OS hỗ trợ | Khi debugger và target cùng dùng IPv6 |

Trong JDK 17, nếu chỉ ghi `address=5005` thì thường listen **loopback**, không phải mọi interface. Trên một số **JDK cũ trước JDK 9** hoặc VM khác, semantics khác; không sao chép cấu hình cũ mà không kiểm tra `java -version` và bind thực tế. Với `server=n`, `address=host:port` lại chỉ **nơi target phải connect**, không quyết định target listen.

### Kiểm tra port đúng theo OS

**Linux:**

~~~bash
ss -ltnp | grep ':5005'
~~~

**PowerShell/Windows:**

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005
~~~

Nếu output tương ứng là loopback, kết nối từ một máy khác **không thể trực tiếp đi vào đó** qua IP mạng ngoài; phải có tunnel hoặc cấu hình bind thích hợp. `localhost` trong **container** là loopback của container, không tự đồng nhất với `localhost` trên host hoặc máy dùng IDE.

Port **5005 chỉ là ví dụ thường dùng**, không có gì đặc biệt trong giao thức. Bị chiếm port sẽ báo lỗi như `Address already in use`/`transport error 202` hoặc thông báo bind liên quan và JVM có thể không khởi động. Chọn port chưa dùng hoặc `:0` cho lab; không cố kết nối debugger với một HTTP service tình cờ cũng mở port 5005.

## 7. Lab Java 17+: quan sát chạy ngay và dừng trước main

Lab này có chương trình Java đầy đủ, không phụ thuộc Spring/IDE. Dùng JDK 17+; có thể chạy trên Windows/Linux/macOS với `dt_socket`. Chọn port 5005 đang trống và chỉ bind loopback. **Không mở port ra Internet.**

### File `JdwpLaunchDemo.java`

~~~java
public final class JdwpLaunchDemo {
    private static int calculate(int number) {
        return number * number + 1;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("MAIN_STARTED");

        if (args.length == 1 && "--hold".equals(args[0])) {
            System.out.println("WAITING_FOR_ENTER");
            System.in.read();
        }

        for (int i = 1; i <= 3; i++) {
            System.out.println("step=" + i
                    + " value=" + calculate(i));
            Thread.sleep(200);
        }

        System.out.println("MAIN_FINISHED");
    }
}
~~~

**Giải thích:** `calculate()` tạo một vị trí breakpoint dễ quan sát; `Thread.sleep(200)` chỉ giúp có thứ tự output. Đối số `--hold` làm `main` dừng tại `System.in.read()` **sau khi đã bắt đầu** để người học kịp attach; đây là **cơ chế chờ của code ứng dụng**, không phải `suspend=y` của JDWP. `System.in.read()` cần chạy trong terminal có stdin tương tác; nếu stdin đã EOF thì có thể trả về ngay.

Biên dịch có debug symbols, rồi chạy bình thường:

~~~bash
javac -g JdwpLaunchDemo.java
java JdwpLaunchDemo
~~~

**Stdout chính xác của lần chạy không bật JDWP**:

~~~text
MAIN_STARTED
step=1 value=2
step=2 value=5
step=3 value=10
MAIN_FINISHED
~~~

### Thí nghiệm 1 — `server=y,suspend=n` (chạy ngay, attach sau)

**Terminal 1:**

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 JdwpLaunchDemo --hold
~~~

Khi không có xung đột port, target thường in theo thứ tự:

~~~text
Listening for transport dt_socket at address: 5005
MAIN_STARTED
WAITING_FOR_ENTER
~~~

Chú ý `MAIN_STARTED` đã xuất hiện **trước khi debugger attach**. Dòng `WAITING_FOR_ENTER` đến từ Java code, không phải JDWP.

**Terminal 2:**

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Trong `jdb`, dùng:

~~~text
stop in JdwpLaunchDemo.calculate
cont
~~~

Sau đó quay lại **terminal 1** và nhấn Enter để chương trình đi vào `calculate()`. Nếu debugger đang chạy và breakpoint được nhận, nó sẽ dừng tại `calculate`; dùng `where` để xem stack, `locals` để xem local variables (khi class có debug symbols) và `cont` để tiếp tục. Vì vòng lặp gọi `calculate` ba lần, có thể phải `cont` ba lần cho đến khi `MAIN_FINISHED` xuất hiện. Dừng một Java thread bằng breakpoint không phụ thuộc `suspend=n` ban đầu.

Nếu `jdb` không tạm dừng ở `calculate`, kiểm tra thứ tự thao tác, breakpoint, việc `cont` và Enter ở terminal ứng dụng. Khi dùng IDE, chọn **Remote JVM Debug → Attach**, host `127.0.0.1`, port `5005` và đặt breakpoint theo đúng source/build.

### Thí nghiệm 2 — `server=y,suspend=y` (chờ từ startup)

Dừng process của thí nghiệm 1 để giải phóng port. **Terminal 1**:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 JdwpLaunchDemo
~~~

Target in dòng JDWP listener, nhưng **chưa in `MAIN_STARTED`**. **Terminal 2**:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Đặt breakpoint trong `main` trước khi resume nếu muốn:

~~~text
stop in JdwpLaunchDemo.main
cont
~~~

Khi target đã được debugger resume và chạy tới breakpoint, `jdb` sẽ báo điểm dừng. Có thể dùng `cont` thêm để tiếp tục chương trình. Nếu bỏ qua lệnh `cont` sau khi attach hoặc debugger vẫn giữ VM suspended, **`MAIN_STARTED` chưa xuất hiện**; không phải ứng dụng bị deadlock. Tắt hoặc resume breakpoint đúng cách, rồi chạy tiếp.

### Thí nghiệm 3 — port tự chọn để tránh đụng nhau

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:0 JdwpLaunchDemo
~~~

JDWP in cổng thực sự được OS gán, chẳng hạn:

~~~text
Listening for transport dt_socket at address: <PORT_DUOC_CAP>
MAIN_STARTED
...
~~~

Đây là **mẫu định dạng**, không phải stdout cố định: port đổi giữa các lần chạy. Vì demo kết thúc nhanh, muốn kịp attach hãy thêm `--hold` và dùng port **được in ra**, không tự gõ 5005. Cách này đặc biệt phù hợp trong môi trường có nhiều bản test song song.

### Lưu ý khác biệt terminal

Trong PowerShell, nếu shell diễn giải đối số bắt đầu bằng `-` không như mong muốn, có thể bọc **toàn bộ JVM option** trong dấu nháy:

~~~powershell
java "-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005" JdwpLaunchDemo --hold
~~~

Với Maven/Gradle/IDE, thêm `-agentlib:jdwp=...` vào **JVM options của tiến trình ứng dụng thực tế**, không thêm vào program arguments hoặc vào JVM của build tool khi mục tiêu là service forked. Xác minh process đang listen và classpath tương ứng với source.

## 8. Remote, Docker và Kubernetes: điểm cuối phải được nhìn từ đúng bên

### 8.1 Debug một JVM trên remote host bằng SSH tunnel

Để tránh mở cổng debug ra mạng ngoài, target trên remote host listen **loopback**:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Trên máy chạy IDE, tạo local forward có xác thực SSH:

~~~bash
ssh -N -L 5005:127.0.0.1:5005 user@remote-host
~~~

Sau đó IDE Attach tới `127.0.0.1:5005` **trên máy local**. SSH vận chuyển kết nối tới `127.0.0.1:5005` **trên remote host**. Đường này không yêu cầu JDWP bind `*:5005`. Kiểm soát quyền SSH, key/host verification và bảo vệ local port; không mở tunnel cho những người dùng không được phép.

### 8.2 Container Docker: localhost là namespace của container

Nếu Java chạy **trong container** với `address=127.0.0.1:5005`, cổng bind ở loopback **bên trong container**; không mặc định truy cập được từ host qua `-p`. Cách thường thấy khi debug cục bộ một container là:

- Trong container, nếu buộc phải kết nối từ ngoài namespace, target nghe `address=*:5005`.
- Ở Docker host, **chỉ publish về loopback của host**: `-p 127.0.0.1:5005:5005`.
- Dùng SSH tunnel hoặc lớp cách ly mạng tương đương khi IDE ở máy khác. Kiểm tra Docker/OS firewall và mạng container thực tế; không coi publish loopback là bảo vệ đầy đủ trong mọi topology.

Ví dụ **minh họa cách map port** (image ứng dụng phải đã có và JVM bên trong được bật JDWP):

~~~bash
docker run --rm -p 127.0.0.1:5005:5005 my-debug-app
~~~

Đây **chỉ là ví dụ Docker networking**, không tự bật JDWP cho image. Không expose `5005` tới `0.0.0.0` hoặc Internet vì tiện. Trong Kubernetes, nên dùng **`kubectl port-forward` trên một pod debug có phân quyền** và kiểm soát bind/network namespace; cách bind bên trong pod phải tương thích với endpoint port-forward. Không bật JDWP công khai cho deployment production chỉ để debug một request.

### 8.3 `server=n` từ container ra debugger

Nếu target chạy với `server=n`, `address` là **IP/host và port nơi debugger đang listen nhìn từ container**. `127.0.0.1` lúc này là *chính container*, không phải laptop. Cần xác minh route, DNS, listener, firewall và quyền mạng; đừng sửa `server=n` thành `y` chỉ vì thất bại kết nối mà chưa rõ hướng cần dùng.

## 9. Bảo mật: JDWP là kênh điều khiển JVM, không phải HTTP API

**Không mở cổng JDWP ra Internet hoặc mạng không tin cậy.** Giao thức/debug agent thông dụng không có một cơ chế xác thực/ủy quyền ứng dụng để bảo vệ các thao tác debug như truy cập stack/objects, thay đổi trạng thái execution và có thể dẫn tới **thực thi code theo quyền của process**. Một kết nối JDWP trái phép có mức rủi ro rất cao.

Lựa chọn an toàn theo ưu tiên:

1. Chỉ enable JDWP trong môi trường phát triển/test hoặc phiên debug được phê duyệt, giữ thời gian bật ngắn nhất cần thiết.
2. Mặc định `server=y,address=127.0.0.1:5005`; dùng SSH tunnel/cơ chế remote access được bảo vệ khi cần kết nối từ xa.
3. Nếu bắt buộc bind wildcard `*:5005` trong container/namespace, chặn truy cập bằng network policies, firewall, port-forward có RBAC và chỉ expose ra loopback của host; cân nhắc thêm `allow` như phòng tuyến phụ, không thay cơ chế bảo mật.
4. Không copy các ví dụ `address=*:5005,allow=*` vào production; `allow=*` có nghĩa không giới hạn nguồn theo tùy chọn đó.
5. Không để secrets ở breakpoint/log; debugger có thể quan sát biến, environment và dữ liệu nhạy cảm của process. Cân nhắc quyền của người được phép attach.
6. Sau debug, **dừng process debug hoặc restart không có agent**; gỡ forwarding, cập nhật deployment config và xác minh cổng không còn listen. Đừng để cấu hình debug tồn tại trong ảnh build hoặc service launch script không kiểm soát.

Bật JDWP cũng có thể ảnh hưởng hoạt động do breakpoints, single-stepping và khả năng suspend all threads. Sử dụng trên live traffic cần kiểm soát rủi ro latency/timeouts.

## 10. Chẩn đoán lỗi trước khi sửa cấu hình

| Hiện tượng | Giải thích có thể xảy ra | Cách xác minh/khắc phục |
| --- | --- | --- |
| Có `Listening for transport dt_socket...` nhưng không có log main | `suspend=y` đang chờ debugger; hoặc code đang bị breakpoint pause | Xem launch options; attach đúng port, resume bằng IDE/`cont` |
| JVM không start, `Address already in use` hoặc bind failure | Port đã bị process khác sử dụng, địa chỉ bind không tồn tại trong namespace | Kiểm tra `ss`/`Get-NetTCPConnection`, chọn port khác/`:0`, bind interface có thật |
| `Connection refused` khi IDE attach | Không có JDWP listener ở endpoint, sai port, JVM đã exit, dùng `server=n` nhầm hoặc container loopback | Xem stdout target, PID, port/socket state, JDK và connector |
| Timeout attach từ xa nhưng local attach được | Bind loopback, firewall/NAT hoặc namespace không cho remote reach | Giữ loopback và dùng tunnel có quyền; chỉ mở bind wildcard khi đã bảo vệ |
| IDE Listen, target `server=y` | **Cả hai chờ** | Đổi IDE sang Attach hoặc target sang `server=n` tùy mô hình đã chọn |
| IDE Attach, target `server=n` | **Hai bên đều connect** | Đổi IDE sang Listen hoặc target sang `server=y` |
| Target `server=n` thất bại trước main | Debugger chưa listen hoặc sai host/port; JDWP initialization thất bại | Bật debugger listener trước, kiểm tra route và timeout |
| Attach thành công nhưng breakpoint không hit | Code đã chạy vì `suspend=n`, sai source/class/build, sai line info, breakpoint không nằm trong path | Dùng `suspend=y` cho startup, build `javac -g`, xác minh source/jar và đường gọi |
| Debugger báo VM suspended, service timeout | Suspend all threads hoặc breakpoints khiến ứng dụng ngừng tiến triển | Resume đúng VM/thread; không pause long-lived production dưới tải |
| Port mở nhưng giao thức HTTP/curl thất bại | `dt_socket` trao đổi **JDWP packets**, không phải HTTP server | Dùng `jdb` hoặc IDE có JDWP connector |
| Có thông báo đã disconnect rồi app vẫn chạy | `suspend=n` và debugger detach; VM vẫn chạy theo chính sách/hoạt động thực tế | Kiểm tra process, logs và breakpoint/suspend state; không coi detach luôn là stop |
| JDWP options hoạt động khác giữa JDKs | Defaults/bind semantics/transport khả dụng khác theo JDK hoặc vendor | Ghi `java -version`, dùng `-agentlib:jdwp=help` và thử bind trên JDK đúng |

Đối với Spring Boot, nên chèn VM option **trước** `-jar`. Nếu lệnh debug hiện trong log Gradle/Maven nhưng app không listen, rất có thể agent đang gắn vào **process build tool** chứ không phải Java process chạy service. Với IDE, thường dùng cấu hình **Remote JVM Debug** sẵn có, không cần tự chạy thêm `jdb`.

## 11. Checklist thực hành

- [ ] Đã xác định Java/JDK vendor + version (ưu tiên JDK 17+ theo lab), đúng process và đúng JVM arguments.
- [ ] Đã hiểu `server=y` là target listen / debugger attach; `server=n` là target connect / debugger listen.
- [ ] Đã ghi rõ `suspend=y` để bắt startup hoặc `suspend=n` để chạy ngay; không vô tình dùng mặc định `y`.
- [ ] Đã chọn `address` theo **network namespace**: loopback local, wildcard chỉ khi có kiểm soát; không nhầm port của ứng dụng HTTP với port JDWP.
- [ ] Khi dùng container/remote, đã kiểm tra bind, routing, firewall, SSH tunnel hoặc port-forward và phạm vi truy cập.
- [ ] Đã kiểm tra port trước/ sau chạy; không có listener trái phép trên interface công khai.
- [ ] Đã xác nhận bằng stdout rằng `MAIN_STARTED` xuất hiện trước attach khi `suspend=n`, và chưa xuất hiện trước resume khi `suspend=y`.
- [ ] Đã dùng IDE/`jdb` đúng kiểu connector và xác nhận breakpoint tại mã thật, không nhầm việc attach với việc chạy tới breakpoint.
- [ ] Đã kiểm tra behavior khi debugger vắng mặt, đặc biệt trường hợp `server=n`.
- [ ] Đã gỡ JDWP agent và port-forward khi kết thúc phiên debug; không để lộ secrets hoặc ảnh hưởng traffic thực.

### Tài liệu chính thức

- Oracle JDK 17 — JPDA, transports, connectors, các sub-options `server`/`suspend`/`address` và ví dụ: https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html
- Oracle JDK 17 — `jdb`, attach, listen và breakpoint: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdb.html
- Oracle JDK 17 — Java launcher và `-agentlib`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 21 — đặc tả JPDA cho các bản Java mới hơn: https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html

**Ghi nhớ:** `server` chọn **ai chủ động tạo kết nối**, `suspend` chọn **có dừng VM lúc startup hay không**, `address` chỉ **đúng endpoint theo vai trò đó**. Hiểu độc lập ba yếu tố này sẽ tránh đa số lỗi “debugger không attach được”, “JVM treo khi khởi động” và “vô tình mở JDWP cho người lạ”.