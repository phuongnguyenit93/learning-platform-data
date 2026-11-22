# Nhận diện UnknownHostException, BindException, ConnectException và SocketTimeoutException trong Java 17

Trong chủ đề **Cấu hình và quan sát** của Java Advance — networking, một lập trình viên cần xác định được lỗi xảy ra **ở giai đoạn nào** trước khi quyết định retry hoặc thông báo sự cố. Cùng là lỗi kết nối, nhưng **hostname không resolve được**, **cổng cục bộ không bind được**, **remote TCP port từ chối kết nối** và **socket chờ quá thời hạn** là bốn tình huống rất khác nhau.

Bốn exception trọng tâm:

- **UnknownHostException:** Java không thể xác định IP address của hostname tại một lần phân giải tên.
- **BindException:** thao tác bind socket vào **địa chỉ/cổng cục bộ** thất bại.
- **ConnectException:** thao tác connect tới **remote address/port** gặp lỗi, điển hình là connection refused.
- **SocketTimeoutException:** một blocking operation trên socket quá thời hạn đã đặt; có thể xảy ra ở **connect**, **accept** hoặc **read** tùy API.

**Không có quy tắc ngoại lệ nào chứng minh chỉ bằng class rằng remote server đã ngừng chạy.** Cần xem **class, operation phase, endpoint, timeout policy, OS/network state và root cause**. Một read timeout có thể xảy ra sau khi server đã commit nghiệp vụ; một BindException có thể hoàn toàn là lỗi triển khai trên máy bạn.

Bài này dùng **Java SE 17**, có hai chương trình hoàn chỉnh đã được biên dịch với **javac --release 17** và chạy thành công trên loopback. Phần lý thuyết bổ sung cây kế thừa, cách catch, quan hệ với HttpClient/CompletableFuture, quan sát/metrics, chiến lược retry và bài tập.

## 1. Đặt exception đúng giai đoạn

~~~text
CLIENT
  |
  +-- resolve hostname -> IP
  |       +-- UnknownHostException
  |
  +-- bind local IP:port (nếu yêu cầu)
  |       +-- BindException
  |
  +-- connect remote IP:port
  |       +-- ConnectException (thường refused)
  |       +-- SocketTimeoutException (khi connect deadline hết hạn)
  |       +-- NoRouteToHostException / IOException khác
  |
  +-- đọc từ connection đã mở
          +-- SocketTimeoutException (read chờ quá hạn)
          +-- -1 từ InputStream.read(): EOF, KHÔNG phải timeout
          +-- SocketException/IOException khác: reset/I/O failure

SERVER
  |
  +-- ServerSocket.bind(local IP:port)
  |       +-- BindException
  |
  +-- ServerSocket.accept()
  |       +-- SocketTimeoutException (accept timeout)
  |
  +-- acceptedSocket.getInputStream().read()
          +-- SocketTimeoutException (read timeout)
~~~

**Một API có thể gộp nhiều bước**: constructor Socket(host, port) có thể resolve và connect trong một lời gọi. Các API Java NIO/async còn có exception và trạng thái riêng. Không được dùng sơ đồ như một khẳng định mọi chương trình luôn gọi từng thao tác tường minh.

| Exception | Bước điển hình | Kiểm tra trước |
|---|---|---|
| UnknownHostException | DNS/hostname resolution | Hostname, DNS server, hosts file, search domains, container namespace |
| BindException | Local bind | Port đã được sử dụng? Local IP có tồn tại? Listener khác? |
| ConnectException | Remote connect | IP/port đúng chưa? Có listener? Firewall active reject? |
| SocketTimeoutException | Connect/accept/read quá hạn | Chính xác method nào, timeout nào, socket còn open không? |

## 2. Cây kế thừa và thứ tự catch

~~~text
java.lang.Exception
  |
  +-- java.io.IOException
  |      |
  |      +-- java.net.UnknownHostException
  |      |
  |      +-- java.net.SocketException
  |      |      +-- java.net.BindException
  |      |      +-- java.net.ConnectException
  |      |      +-- java.net.NoRouteToHostException
  |      |
  |      +-- java.io.InterruptedIOException
  |      |      +-- java.net.SocketTimeoutException
  |      |
  |      +-- java.net.http.HttpTimeoutException
  |             +-- java.net.http.HttpConnectTimeoutException
  |
  +-- java.util.concurrent.TimeoutException
~~~

**BindException và ConnectException là con của SocketException. SocketTimeoutException KHÔNG là con của SocketException:** nó kế thừa **InterruptedIOException**. **UnknownHostException** là một IOException, không nằm dưới SocketException.

Nếu bạn cần phân loại riêng:

~~~java
try {
    networkOperation();
} catch (UnknownHostException ex) {
    // DNS/hostname lookup.
} catch (BindException ex) {
    // Bind vào local port.
} catch (ConnectException ex) {
    // Connect tới remote port.
} catch (SocketTimeoutException ex) {
    // Connect/accept/read timeout: còn phải biết phase.
} catch (SocketException ex) {
    // Socket errors còn lại.
} catch (IOException ex) {
    // IOException khác.
}
~~~

**Đoạn trên chỉ minh họa thứ tự**, networkOperation là tên giả định và Java compiler có thể coi nhánh cụ thể unreachable nếu phần try chỉ có kiểu exception hẹp. Trong catch chain thực, **không đặt IOException trước các subclasses**, cũng không đặt SocketException trước BindException/ConnectException. Với classifier dùng instanceof, áp thứ tự kiểm tra tương tự.

## 3. UnknownHostException: không xác định được IP của hostname

Javadoc Java 17 định nghĩa **UnknownHostException** khi không thể xác định IP address của host.

~~~java
InetAddress result = InetAddress.getByName("service.example.invalid");
~~~

Đây là snippet về API, không phải chương trình có stdout cố định. Tên miền .invalid dành cho tài liệu, nhưng DNS resolver, VPN, proxy, hosts file, DNS wildcard và cache có thể khác nhau theo môi trường. Không thiết kế một unit test yêu cầu lookup Internet luôn thất bại sau chính xác 100 ms.

**Những nguyên nhân cần kiểm tra:** hostname sai chính tả, service discovery chưa có record, DNS outage, search suffix sai, container/pod có cấu hình resolver khác máy host, hostname vô tình chứa cả port, IPv4/IPv6 lookup preference hoặc internal DNS không sẵn. UnknownHostException **không nói chắc host ở xa có chạy hay không** vì TCP connect có thể chưa được thử.

Để điều tra, ghi lại **hostname đã lọc secrets**, môi trường chạy, resolver, DNS records, thời điểm và resolved IPs (nếu có). Kiểm tra từ **cùng network namespace/container**, không chỉ từ laptop. Dùng InetAddress.getAllByName(host) để quan sát addresses khi thành công; công cụ nslookup/dig của OS có thể bổ sung thông tin nhưng cache/lookup path khác Java.

**Không ép mọi API NIO trả UnknownHostException**. Java NIO channel có thể dùng **UnresolvedAddressException** đối với InetSocketAddress chưa resolve. Đọc Javadoc của SocketChannel/AsynchronousSocketChannel đang dùng.

Trong chương trình thực hành bên dưới, UnknownHostException được **khởi tạo synthetic** chỉ để minh họa phân loại type, không làm DNS query. Kiểm thử DNS end-to-end nên dùng DNS test server được kiểm soát.

## 4. BindException: local address hoặc port không bind được

**BindException extends SocketException** thường xảy ra khi **ServerSocket.bind(...)** hoặc **Socket.bind(...)** không thể giữ local IP:port.

~~~java
try (ServerSocket listener = new ServerSocket()) {
    listener.bind(new InetSocketAddress("127.0.0.1", 8080));
}
~~~

Đoạn trên là snippet với imports ngầm định. Nếu process khác đã chiếm local port 8080 hoặc IP bind không hợp lệ trong môi trường, lệnh có thể ném BindException. Thông báo lỗi như **Address already in use** phụ thuộc OS; không nên phân loại bằng substring của exception.getMessage().

**Nguyên nhân chính:** listener khác giữ port, nhiều replicas cùng bind, quá trình restart/shutdown chưa giải phóng tài nguyên, bind IP không tồn tại trên interface, IPv4/IPv6 wildcard conflicts hoặc socket options/policies của OS. **Socket phía client** cũng có thể gặp BindException nếu ứng dụng bind source port tường minh đã bị chiếm.

**Cách xử lý:** kiểm tra local address/port, process và network namespace đang giữ port; xác minh replicas, startup/shutdown. Với test dùng **new ServerSocket(0, backlog, address)** để OS cấp port động và đọc **getLocalPort()**. **SO_REUSEADDR không bảo đảm chiếm được mọi port đang có listener**, dù nó có thể hữu ích với một số chính sách reuse/TIME_WAIT theo OS. BindException do cấu hình cố định thường nên fail-fast và sửa config, không retry mãi cùng cổng.

**Đừng báo BindException là remote server offline**: lỗi xảy ra khi giữ tài nguyên **cục bộ**.

## 5. ConnectException: không connect được remote address/port

**ConnectException extends SocketException**. Theo Javadoc, thường gặp khi một host/port remote **từ chối connection**, ví dụ không có process listen tại cổng ấy.

~~~java
try (Socket client = new Socket()) {
    client.connect(new InetSocketAddress(
            "127.0.0.1", 50000), 500);
}
~~~

Đây là snippet. Không có bảo đảm port 50000 đang trống trên mọi máy; nếu có listener sẽ thành công. Nếu port không listen và OS active refuse, có thể ném **ConnectException** rất nhanh.

**Nguyên nhân thường gặp:** sai remote port, server chưa start hoặc đang restart, server chỉ bind loopback, firewall/NAT/LB active reject, service discovery trỏ cổng cũ, kết nối tới IPv4/IPv6 interface sai hoặc các giới hạn tài nguyên. ConnectException không phải một lỗi DNS: hostname có thể resolve thành IP bình thường nhưng **remote port không accept**.

Phân biệt với timeout:

- **Refused nhanh**: có tín hiệu từ chối, thường ConnectException.
- **Network drop/no response**: có thể chờ tới connect timeout, hoặc OS trả lỗi khác.
- **No route**: có thể NoRouteToHostException/IOException khác.
- **DNS thất bại**: có thể UnknownHostException hoặc lỗi unresolved của API.

**TCP connect thành công không phải HTTP success**. Remote có thể nhận connection rồi không gửi bytes, trả 500/503, reset hoặc trả protocol sai. Nếu connect thành công nhưng read timeout, class và cách xử lý khác.

## 6. SocketTimeoutException: cần biết operation nào timeout

**SocketTimeoutException extends InterruptedIOException**, và có thể xuất hiện ở nhiều blocking operations:

| Operation | Thiết lập thời hạn | Khi hết thời gian |
|---|---|---|
| Socket.connect(remote, timeoutMs) | Tham số thứ hai của connect | Có thể ném SocketTimeoutException khi TCP connect chưa hoàn thành |
| ServerSocket.accept() | ServerSocket.setSoTimeout(ms) | Timeout nếu chưa có incoming connection |
| Socket.getInputStream().read() | Socket.setSoTimeout(ms) | Timeout nếu chưa đọc được dữ liệu |
| DatagramSocket.receive() | DatagramSocket.setSoTimeout(ms) | Timeout khi chưa có datagram |

**Socket.setSoTimeout không phải connect timeout**:

~~~java
socket.connect(remoteEndpoint, 2000); // Connect budget.
socket.setSoTimeout(1000);            // Blocking read budget.
int firstByte = socket.getInputStream().read();
~~~

Đây là snippet, socket và remoteEndpoint được định nghĩa tại caller. **ServerSocket.setSoTimeout** kiểm soát **accept**, không mặc định áp cho read của Socket mới accept. Trên accepted socket muốn giới hạn read thì phải cấu hình SO_TIMEOUT cho **socket ấy**.

**Giá trị 0** ở các timeout API này có nghĩa không có giới hạn thời gian tường minh tại API tương ứng; OS vẫn có thể phát hiện lỗi và kết thúc thao tác. Tránh chờ vô hạn nếu nghiệp vụ cần deadline.

### Timeout accept/read không tự đóng socket

- Sau **ServerSocket.accept()** ném SocketTimeoutException vì SO_TIMEOUT, Javadoc cho biết ServerSocket vẫn hợp lệ.
- Sau **Socket InputStream.read()** timeout, Socket cũng có thể còn open; server có thể gửi byte muộn hơn.
- **Socket.connect(endpoint, timeout)** là giai đoạn khác; khi connect thất bại không nên giả định có thể sử dụng socket ấy như một connection thành công.

**Read timeout khác EOF:** read trả **-1** là end-of-stream. Read ném SocketTimeoutException nghĩa thao tác chờ quá hạn, không chứng minh peer đã shutdown. Lỗi reset có thể là SocketException khác.

**Read SO_TIMEOUT không tạo overall deadline cho toàn response**. Nếu peer nhỏ giọt một byte trước mỗi lần read timeout, vòng đọc có thể kéo dài lâu. Cần giới hạn tổng bytes, global deadline và protocol validation riêng.

**Đừng tự bật interrupt flag khi bắt SocketTimeoutException** chỉ vì class cha mang tên InterruptedIOException: timeout không chứng minh Thread.interrupt đã xảy ra.

## 7. Chương trình Java 17: mô phỏng và tạo các lỗi Socket thật

**SocketFailureLab.java** dùng loopback, port động, try-with-resources để:

1. Tạo một **UnknownHostException synthetic**; không phụ thuộc DNS ngoài.
2. Giữ một local port bằng listener đầu, thử bind listener thứ hai → **BindException**.
3. Đóng listener ở một port động, rồi connect vào port ấy → thông thường **ConnectException**. Có **race rất nhỏ** nếu process khác chiếm đúng port trong khoảng trống.
4. Đặt ServerSocket SO_TIMEOUT = 150 ms và không cho client connect → **SocketTimeoutException ở accept**.
5. Tạo TCP connection thành công, không gửi byte, đặt read SO_TIMEOUT = 150 ms → **SocketTimeoutException ở read**.
6. Kiểm tra listener và accepted socket vẫn open sau timeout.

Tạo tệp **SocketFailureLab.java**:

~~~java
import java.io.IOException;
import java.net.BindException;
import java.net.ConnectException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

public class SocketFailureLab {
    private static final InetAddress LOOPBACK = InetAddress.getLoopbackAddress();

    private static void bindCollision() throws Exception {
        try (ServerSocket first = new ServerSocket(0, 10, LOOPBACK);
             ServerSocket second = new ServerSocket()) {
            second.setReuseAddress(false);
            try {
                second.bind(new InetSocketAddress(
                        LOOPBACK, first.getLocalPort()));
                throw new AssertionError("Second bind unexpectedly succeeded");
            } catch (BindException expected) {
                System.out.println("Bind: BindException");
            }
        }
    }

    private static void connectRefused() throws Exception {
        int unusedPort;
        try (ServerSocket temporary = new ServerSocket(0, 10, LOOPBACK)) {
            unusedPort = temporary.getLocalPort();
        }
        try (Socket client = new Socket()) {
            try {
                client.connect(new InetSocketAddress(LOOPBACK, unusedPort), 500);
                throw new AssertionError("Unexpected TCP listener on test port");
            } catch (ConnectException expected) {
                System.out.println("Connect: ConnectException");
            }
        }
    }

    private static void acceptTimeout() throws Exception {
        try (ServerSocket server = new ServerSocket(0, 10, LOOPBACK)) {
            server.setSoTimeout(150);
            try {
                server.accept();
                throw new AssertionError("Unexpected incoming connection");
            } catch (SocketTimeoutException expected) {
                System.out.println("Accept: SocketTimeoutException");
                System.out.println("Accept socket still open: " + !server.isClosed());
            }
        }
    }

    private static void readTimeout() throws Exception {
        try (ServerSocket server = new ServerSocket(0, 10, LOOPBACK);
             Socket client = new Socket()) {
            client.connect(new InetSocketAddress(
                    LOOPBACK, server.getLocalPort()), 500);
            try (Socket accepted = server.accept()) {
                accepted.setSoTimeout(150);
                try {
                    accepted.getInputStream().read();
                    throw new AssertionError("Unexpected application bytes or EOF");
                } catch (SocketTimeoutException expected) {
                    System.out.println("Read: SocketTimeoutException");
                    System.out.println("Read socket still open: " + !accepted.isClosed());
                }
            }
        }
    }

    private static void simulatedDnsFailure() {
        // Constructed exception only; no DNS/network request performed.
        IOException failure = new UnknownHostException("synthetic DNS failure");
        if (!(failure instanceof UnknownHostException)) {
            throw new AssertionError("Wrong exception class");
        }
        System.out.println("DNS example (synthetic): UnknownHostException");
    }

    public static void main(String[] args) throws Exception {
        simulatedDnsFailure();
        bindCollision();
        connectRefused();
        acceptTimeout();
        readTimeout();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SocketFailureLab.java
java SocketFailureLab
~~~

Stdout từ lần chạy thành công:

~~~text
DNS example (synthetic): UnknownHostException
Bind: BindException
Connect: ConnectException
Accept: SocketTimeoutException
Accept socket still open: true
Read: SocketTimeoutException
Read socket still open: true
~~~

**Đã biên dịch bằng javac --release 17 và chạy thành công trên JDK trong môi trường loopback**, đầu ra khớp bảy dòng. Không dùng mạng ngoài. Ngoại lệ DNS ở đây được **new trực tiếp**, không phải lỗi DNS thật. Test refused phụ thuộc OS không có listener đồng thời ở port ấy.

**BindException** được kiểm thử khi socket đầu vẫn listen; **accept timeout** không đóng ServerSocket; **read timeout** không tự đóng accepted socket. Tuy nhiên trong code thật có thể **chủ động đóng** socket sau timeout nếu đã hết business deadline hoặc protocol state không an toàn để đọc tiếp.

## 8. Chương trình Java 17: phân loại exception và unwrap asynchronous failure

Chương trình thứ hai tập trung vào **cây kế thừa và cách phân loại**, không tạo network requests. Tất cả exceptions ở đây là **synthetic**. Nó phân biệt bốn nhóm đề bài với HttpClient timeouts và **Future.get(timeout)**.

**NetworkExceptionClassifier.java**:

~~~java
import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.BindException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;

public class NetworkExceptionClassifier {
    private static Throwable unwrap(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    private static String category(Throwable failure) {
        Throwable cause = unwrap(failure);
        if (cause instanceof UnknownHostException) return "DNS";
        if (cause instanceof BindException) return "LOCAL_BIND";
        if (cause instanceof ConnectException) return "REMOTE_CONNECT";
        if (cause instanceof SocketTimeoutException) return "SOCKET_TIMEOUT";
        if (cause instanceof HttpConnectTimeoutException) return "HTTP_CONNECT_TIMEOUT";
        if (cause instanceof HttpTimeoutException) return "HTTP_RESPONSE_TIMEOUT";
        if (cause instanceof TimeoutException) return "CALLER_WAIT_TIMEOUT";
        if (cause instanceof IOException) return "OTHER_IO";
        return "OTHER";
    }

    public static void main(String[] args) {
        Throwable[] examples = {
                new UnknownHostException("synthetic"),
                new BindException("synthetic"),
                new ConnectException("synthetic"),
                new SocketTimeoutException("synthetic"),
                new HttpConnectTimeoutException("synthetic"),
                new HttpTimeoutException("synthetic"),
                new TimeoutException("synthetic"),
                new CompletionException(new ConnectException("synthetic"))
        };
        for (Throwable example : examples) {
            System.out.println(example.getClass().getSimpleName()
                    + " -> " + category(example));
        }
        System.out.println("Bind is SocketException: "
                + (new BindException() instanceof SocketException));
        System.out.println("Connect is SocketException: "
                + (new ConnectException() instanceof SocketException));
        System.out.println("Socket timeout is InterruptedIOException: "
                + (new SocketTimeoutException() instanceof InterruptedIOException));
        System.out.println("HTTP connect timeout is HttpTimeoutException: "
                + (new HttpConnectTimeoutException("synthetic")
                instanceof HttpTimeoutException));
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 NetworkExceptionClassifier.java
java NetworkExceptionClassifier
~~~

Stdout đã kiểm thử:

~~~text
UnknownHostException -> DNS
BindException -> LOCAL_BIND
ConnectException -> REMOTE_CONNECT
SocketTimeoutException -> SOCKET_TIMEOUT
HttpConnectTimeoutException -> HTTP_CONNECT_TIMEOUT
HttpTimeoutException -> HTTP_RESPONSE_TIMEOUT
TimeoutException -> CALLER_WAIT_TIMEOUT
CompletionException -> REMOTE_CONNECT
Bind is SocketException: true
Connect is SocketException: true
Socket timeout is InterruptedIOException: true
HTTP connect timeout is HttpTimeoutException: true
~~~

**Đã biên dịch bằng javac --release 17 và chạy thành công**, khớp đủ 12 dòng. Hàm unwrap lấy cause từ **CompletionException/ExecutionException**, không cố bóc mọi loại wrapper; trong logs sản phẩm thật hãy giữ original stack trace và các lớp ngữ cảnh.

**Đặt instanceof IOException ở đầu category là sai** nếu muốn phân biệt subclasses: tất cả lỗi socket cụ thể sẽ bị phân loại OTHER_IO. Đặt các lớp cụ thể trước, fallback chung sau.

## 9. Phân biệt với java.net.http.HttpClient

**HttpClient.Builder.connectTimeout(Duration)** giới hạn thiết lập connection **mới**; **HttpRequest.Builder.timeout(Duration)** giới hạn thời gian chờ response của **một request**. Đây là API khác raw Socket.

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

Đây là snippet, giả định uri hợp lệ và imports đã có. Nếu cần mở connection mới nhưng không xong đúng hạn, lỗi phù hợp là **HttpConnectTimeoutException**; nếu response request không nhận đúng hạn, **HttpTimeoutException**. **HttpConnectTimeoutException extends HttpTimeoutException**, không extends SocketTimeoutException.

**HTTP status 408 hoặc 504** là phản hồi từ server/gateway, không tự tương đương client-side Java timeout exception. Nếu có HttpResponse, kiểm tra statusCode; nếu exchange thất bại, xem IOException class/cause.

Với **sendAsync**, future có thể complete exceptionally; **join** đưa lỗi trong CompletionException, **get** thường đưa trong ExecutionException. Còn **future.get(timeout, unit)** có thể ném **java.util.concurrent.TimeoutException** chỉ vì caller chờ quá lâu; không chứng minh HTTP operation đã bị hủy hoặc server chưa xử lý.

### NIO và async sockets

Không ép **SocketChannel** hay **AsynchronousSocketChannel** báo y hệt các lỗi của blocking Socket: có thể gặp **UnresolvedAddressException, NotYetConnectedException, AlreadyBoundException, ClosedChannelException**, hoặc exceptions khác theo state. Khi debug, ghi **exact method và channel state**, không tạo một exception mới rồi che nguyên nhân gốc.

## 10. Logs, metrics và quyết định recovery

Một log tốt mang **phase**, **exception class**, endpoint alias và timeout:

~~~text
event=network_failure
phase=connect
target_alias=inventory-service
remote_port=8443
timeout_ms=2000
elapsed_ms=2007
exception_class=java.net.SocketTimeoutException
attempt=2
request_id=redacted
~~~

Dòng trên là **minh họa**, không phải một phép đo thật. Timeout scheduling có thể vượt con số cấu hình một chút.

Nên ghi thêm local IP/port khi bind, DNS lookup result khi được phép, root cause chain, số bytes đã gửi/nhận, socket lifecycle và JDK/OS/container khi điều tra. Dùng **System.nanoTime()** đo elapsed. Đừng ghi token, password, Authorization headers, private query string hoặc toàn response body. Metrics nên gắn low-cardinality labels như exception class, phase, endpoint alias thay vì raw URL.

### Policy xử lý

| Lỗi | Hướng xử lý |
|---|---|
| **UnknownHostException** | Kiểm tra DNS/host; retry bounded khi DNS tạm lỗi; typo cố định thì fail-fast |
| **BindException** | Kiểm tra local IP/port, process giữ cổng, replicas; không retry vô hạn cùng config |
| **ConnectException** | Kiểm tra listener/remote port/proxy/firewall; retry khi transient và trong deadline |
| **SocketTimeoutException tại accept** | Thường có thể tiếp tục accept hoặc kiểm tra shutdown flag |
| **SocketTimeoutException tại read** | Kiểm tra protocol partial state, overall deadline, app outcome |
| **SocketTimeoutException tại connect** | Kiểm tra route/drop, retry có backoff nếu được phép |
| **HttpTimeoutException** | Kiểm tra request timeout và idempotency |
| **Future TimeoutException** | Caller ngừng đợi; quyết định cancellation/cleanup riêng |

Một nghiệp vụ có tổng deadline 5 giây không nên cho attempt đầu 5 giây rồi retry thêm 5 giây ngoài ngân sách. Tính **remaining deadline** từ một mốc System.nanoTime, thêm retry cap, exponential backoff và jitter. Nếu lệnh POST có side effects, timeout **không chứng minh server chưa commit**; dùng idempotency key hoặc reconciliation thay vì retry mù.

## 11. Lỗi phổ biến cần tránh

1. Gộp mọi IOException thành "server remote down"; BindException có thể hoàn toàn là local error.
2. Catch SocketException rồi nghĩ đã bắt SocketTimeoutException; cây kế thừa không như vậy.
3. Catch IOException/SocketException trước các subclasses cụ thể.
4. Coi UnknownHostException luôn là DNS NXDOMAIN; còn lookup configuration/cache/transient errors.
5. Coi ConnectException là lỗi phân giải tên; remote port có thể bị refused sau DNS thành công.
6. Coi Socket.setSoTimeout là timeout của Socket.connect; dùng tham số timeout của connect.
7. Coi accept timeout tự đóng listener hoặc read timeout tự đóng connected socket.
8. Coi read() trả -1 là SocketTimeoutException; -1 nghĩa EOF.
9. Bật SO_REUSEADDR rồi cho rằng không còn BindException.
10. Dùng public IP bất kỳ để "bảo đảm" ConnectException hoặc connect timeout trong test.
11. So sánh exception.getMessage() với chữ English để xác định loại lỗi.
12. Retry vô hạn sau network failure, gây retry storm hoặc duplicate side effects.
13. Đồng nhất HttpConnectTimeoutException, SocketTimeoutException và Future TimeoutException.
14. Dùng Future.get(timeout) rồi giả định underlying network request tự ngừng.
15. Log URL kèm secrets hoặc dùng endpoint raw/user IDs làm metric labels.

## 12. Bài tập thực hành

**Bài A — Catch order:** trong NetworkExceptionClassifier, đặt IOException check lên trước UnknownHostException và quan sát tất cả subclasses bị gộp vào OTHER_IO; sửa đúng thứ tự.

**Bài B — Bind conflict:** giữ listener ở port do OS cấp, thử bind listener khác vào cùng IP:port. So sánh BindException với ConnectException; điều gì là local, điều gì là remote?

**Bài C — Accept timeout:** đổi 150 ms thành 300 ms, đo elapsed bằng System.nanoTime và kiểm tra listener vẫn open. Không assert chính xác từng millisecond.

**Bài D — Read timeout vs EOF:** tạo connection, trước hết không gửi byte để read timeout; sau đó thử client.shutdownOutput() để read() có thể trả -1. Giải thích khác biệt.

**Bài E — Connect refused:** đổi remote port tới port không có listener. Ghi class và phase; thử case có listener để xem connect thành công nhưng read vẫn có thể timeout.

**Bài F — DNS lab:** dùng một DNS test server do bạn kiểm soát với tên tồn tại và không tồn tại; quan sát InetAddress.getAllByName và cache, không dùng DNS Internet làm unit-test oracle.

**Bài G — Future wrappers:** tạo CompletableFuture.failedFuture(new ConnectException("synthetic")), gọi join rồi dùng getCause từ CompletionException để phân loại đúng.

**Bài H — HTTP request timeout:** tạo HTTP server localhost trả response chậm, gọi HttpClient với HttpRequest.timeout ngắn, phân biệt HttpTimeoutException với raw SocketTimeoutException.

**Bài I — Overall deadline:** giới hạn 3 giây cho tất cả attempts/connect/read/backoff bằng monotonic clock, không reset deadline sau mỗi retry.

**Bài J — Idempotency:** mô phỏng server tạo đơn hàng rồi response đến muộn, client timeout; thiết kế idempotency key/reconciliation trước khi retry.

**Bài K — Logging:** tạo record chỉ có phase, class, endpoint alias, timeout, duration, attempt và correlation ID; kiểm tra không lộ credentials/PII.

## 13. Câu hỏi ôn tập

**1. UnknownHostException cho biết gì?** Không xác định được IP của host trong operation lookup.

**2. BindException thuộc local hay remote?** Local bind.

**3. ConnectException thường gặp khi nào?** Remote connection bị refused hoặc lỗi khi mở TCP.

**4. SocketTimeoutException có thể xuất hiện ở connect không?** Có, với Socket.connect(endpoint, timeout).

**5. ServerSocket.setSoTimeout điều khiển gì?** accept().

**6. Socket.setSoTimeout điều khiển gì?** Blocking InputStream.read() của Socket.

**7. Timeout bằng 0 có ý nghĩa gì?** Không có deadline tường minh ở API đó; OS vẫn có thể trả lỗi.

**8. Accept timeout có tự đóng listener không?** Không theo contract.

**9. Read timeout khác EOF ra sao?** Timeout ném exception, EOF là read() trả -1.

**10. SocketTimeoutException extends SocketException không?** Không; extends InterruptedIOException.

**11. BindException và ConnectException extends gì?** SocketException.

**12. UnknownHostException có chứng minh remote server chết không?** Không.

**13. ConnectException có chứng minh DNS sai không?** Không.

**14. Vì sao phải biết phase khi gặp SocketTimeoutException?** Cùng class có thể thuộc connect, accept hoặc read.

**15. Retry sau read timeout có an toàn cho POST không?** Không mặc định; server có thể đã commit.

**16. HttpConnectTimeoutException extends gì?** HttpTimeoutException.

**17. CompletableFuture.get(timeout) ném exception loại gì khi hết thời gian chờ?** java.util.concurrent.TimeoutException.

**18. Future wait timeout có hủy request không?** Không bảo đảm.

**19. Vì sao không parse exception message để retry?** Message phụ thuộc OS/locale/provider.

**20. Port 0 giúp gì trong test?** Nhờ OS chọn port động, giảm xung đột.

**21. Muốn test DNS deterministic nên làm gì?** Synthetic unit test hoặc DNS test environment.

**22. SO_REUSEADDR có sửa mọi BindException không?** Không.

**23. Log nên chứa gì?** Class, phase, endpoint alias, timeout, elapsed, attempt và request ID.

**24. Mốc thời gian để đo elapsed nên dùng gì?** System.nanoTime().

**25. Vì sao retry cần overall deadline?** Để nhiều attempts không vượt quá ngân sách nghiệp vụ.

## 14. Tài liệu Java SE 17 chính thức

- UnknownHostException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnknownHostException.html
- BindException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/BindException.html
- ConnectException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ConnectException.html
- SocketTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html
- SocketException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketException.html
- Socket: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- ServerSocket: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- InetAddress: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- InterruptedIOException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InterruptedIOException.html
- HttpTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- HttpConnectTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html
- CompletableFuture: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

**Ghi nhớ:** **UnknownHostException** thuộc giai đoạn phân giải IP, **BindException** thuộc local bind, **ConnectException** thuộc remote connect, còn **SocketTimeoutException** phụ thuộc giai đoạn connect/accept/read và timeout policy. Luôn xem **exception class + phase + root cause**; không đồng nhất SocketTimeoutException với HttpTimeoutException hay Future TimeoutException. Trước khi retry, kiểm tra deadline, side effects và idempotency; bảo vệ tài nguyên socket và không tiết lộ dữ liệu nhạy cảm trong logs.