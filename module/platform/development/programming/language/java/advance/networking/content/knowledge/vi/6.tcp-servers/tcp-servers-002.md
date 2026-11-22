# Cổng 0, địa chỉ bind và cách công bố địa chỉ đã được cấp

**Chủ đề:** Java Advance - networking  
**Nhóm kiến thức:** Máy chủ TCP

Khi một máy chủ TCP chạy thử nghiệm, mở nhiều instance song song hoặc được một tiến trình khác khởi động, việc cố định một cổng như 8080 rất dễ gây xung đột. Trong Java, **bind vào cổng 0** cho phép hệ điều hành chọn một cổng TCP đang khả dụng. Sau khi **bind thành công**, máy chủ lấy **cổng thực tế** từ **ServerSocket.getLocalPort()** hoặc **getLocalSocketAddress()**, rồi công bố endpoint đúng cho client.

Tuy nhiên, **cổng đã cấp** chỉ là một phần của endpoint. **Địa chỉ bind** quy định các địa chỉ mạng cục bộ mà listener nhận kết nối; **địa chỉ công bố (advertised address)** là host/IP và port **mà client có thể thực sự dùng để truy cập**. Hai địa chỉ này có thể khác nhau khi server bind wildcard, chạy trong container, đứng sau NAT/load balancer hoặc phục vụ client ở mạng khác.

Bài học đi theo đúng chuỗi: **chọn địa chỉ bind → yêu cầu port 0 → OS cấp cổng → đọc endpoint thật → chọn địa chỉ client truy cập được → công bố sau khi server sẵn sàng → client kết nối → thu hồi thông tin khi dừng**.

## 1. Cổng 0 nghĩa là gì?

Một địa chỉ TCP listener có hai thành phần quan trọng:

~~~text
Địa chỉ IP cục bộ + cổng TCP cục bộ

Ví dụ bind cụ thể: 127.0.0.1:53217
Ví dụ bind wildcard: 0.0.0.0:53217
Ví dụ IPv6 loopback: [::1]:53217
~~~

**Port 0 trong lời gọi bind** là yêu cầu đặc biệt: **hãy để hệ điều hành chọn một cổng còn khả dụng**. Cổng được chọn thường thuộc dải cổng động (ephemeral) theo cấu hình hệ điều hành. Số chính xác không cố định và có thể khác sau mỗi lần chạy. **Port 0 không phải cổng dịch vụ mà client được yêu cầu kết nối tới**; sau bind, listener có một cổng **khác 0**.

Trên Java:

~~~java
// Snippet: cần import java.net.* và đóng socket sau khi dùng.
ServerSocket listener = new ServerSocket(); // Chưa bind.
int before = listener.getLocalPort();       // -1.

listener.bind(new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 0)); // OS chọn port thật.

int assignedPort = listener.getLocalPort();   // Thường 1..65535.
SocketAddress bound = listener.getLocalSocketAddress();
~~~

**getLocalPort() == -1** nghĩa là ServerSocket **chưa từng bind thành công**. Sau bind, giá trị này là cổng thực tế; việc socket về sau bị đóng **không có nghĩa** getter sẽ quay lại -1. **ServerSocket.isBound()** cho biết socket đã được bind, nhưng có thể vẫn trả true sau **close()**; dùng thêm **isClosed()**, trạng thái service và health check khi cần xác định listener còn hoạt động.

Có hai cách thường gặp:

- **new ServerSocket(0)**: constructor bind ngay vào một địa chỉ wildcard thích hợp và yêu cầu OS cấp port. Dùng nhanh cho demo/test khi không cần chọn interface.
- **new ServerSocket()**, sau đó **bind(new InetSocketAddress(address, 0), backlog)**: tách bước tạo với bước bind, cho phép chọn địa chỉ và cấu hình cần thiết trước bind. Đây là cách rõ ràng khi dạy về địa chỉ bind và port động.

Một **Socket client** cũng có thể được OS cấp cổng nguồn động khi kết nối; cổng nguồn đó **không phải** cổng listening của ServerSocket. **ServerSocket.accept()** trả về **Socket mới** cho từng connection, không đổi cổng listener.

## 2. Bind là hành động ở hệ điều hành, không phải biến Java

**ServerSocket.bind(...)** yêu cầu TCP/IP stack của OS đăng ký một local endpoint để lắng nghe connection. OS kiểm tra địa chỉ có thuộc ngữ cảnh network interface/namespace phù hợp, cổng có thể sử dụng hay không, quyền và policy liên quan, rồi tạo listener. Sau khi bind thành công:

1. Listener có **địa chỉ cục bộ** và **port cục bộ**.
2. Kernel có thể xử lý bước kết nối TCP ban đầu và xếp những connection chờ **accept()** vào hàng đợi phù hợp.
3. **accept()** trả socket của từng connection đã được chấp nhận.
4. Java application tiếp tục đọc/ghi byte và thực hiện protocol trên socket đó.

**bind thành công không chứng minh mọi client trên Internet đều kết nối được**. Firewall, route, interface, container port mapping, ACL, NAT, proxy và application readiness vẫn có thể ngăn kết nối.

Tham số **backlog** trong **ServerSocket.bind(endpoint, backlog)** là yêu cầu về hàng đợi connection đang chờ chấp nhận; OS có thể điều chỉnh hoặc giới hạn. Nó không phải số lượng client tối đa mà toàn bộ ứng dụng có thể phục vụ đồng thời, không phải request timeout.

### Vì sao không nên tự tìm một cổng “đang trống” rồi đóng lại?

Một anti-pattern thường gặp:

~~~java
// Minh họa cách KHÔNG NÊN dùng để dành cổng.
int port;
try (ServerSocket probe = new ServerSocket(0)) {
    port = probe.getLocalPort();
}
// probe đã đóng, cổng không còn do tiến trình này giữ.
ServerSocket server = new ServerSocket(port); // Có thể thất bại do race.
~~~

Giữa lúc **probe.close()** và lần bind thứ hai, một tiến trình khác có thể chiếm cổng đó: đây là lỗi **time-of-check to time-of-use (TOCTOU)**. Cách đúng là **giữ nguyên ServerSocket đã bind thành công**, lấy **getLocalPort()** từ chính socket đang mở rồi dùng socket đó làm listener. Không cần “kiểm tra cổng trống” trước khi yêu cầu bind port 0.

## 3. Địa chỉ bind: loopback, wildcard hay một IP cụ thể?

Cùng yêu cầu port 0, nhưng địa chỉ bind làm thay đổi phạm vi kết nối được nhận.

| Địa chỉ bind | Ý nghĩa và ví dụ sử dụng | Điều cần nhớ khi công bố |
| --- | --- | --- |
| **127.0.0.1** | IPv4 loopback; client trên chính host | Không công bố 127.0.0.1 cho client ở máy khác |
| **::1** | IPv6 loopback; client trên chính host | Khi hiển thị với port, dùng dạng **[::1]:port** |
| **0.0.0.0** | IPv4 wildcard; lắng nghe trên các địa chỉ IPv4 cục bộ thích hợp | **0.0.0.0** là địa chỉ bind, không phải host đích dùng cho client bên ngoài |
| **::** | IPv6 wildcard; hành vi dual-stack/IPv4-mapped tùy OS và cấu hình | Không mặc định nó chấp nhận IPv4; cần xác minh trên hệ thống thực |
| **192.0.2.10** | Minh họa bind một IPv4 cụ thể đã được gán cho interface | Chỉ bind thành công khi IP hợp lệ ở môi trường; client phải có route và quyền truy cập |
| **Địa chỉ của một interface thật** | Dùng trong host có nhiều NIC, network namespace hoặc nhiều service | Không tự suy ra đây là địa chỉ public; phụ thuộc routing, NAT và firewall |

**192.0.2.10** là địa chỉ ví dụ thuộc dải dành cho tài liệu; nó không phải IP cần dùng trên máy của bạn.

### Loopback phù hợp cho test

~~~java
InetAddress localOnly = InetAddress.getLoopbackAddress();
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress(localOnly, 0));
~~~

**InetAddress.getLoopbackAddress()** trả về địa chỉ loopback của hệ thống, có thể là IPv4 hoặc IPv6. Một test client nên dùng **chính đối tượng địa chỉ** đã chọn để kết nối, nhờ vậy tránh tình huống server bind **127.0.0.1** nhưng **localhost** trên client lại resolve thành **::1** hoặc ngược lại.

### Wildcard phù hợp khi cần nhận từ nhiều interface

~~~java
// Snippet: yêu cầu bind IPv4 wildcard; xử lý IOException khi dùng thực tế.
InetAddress allIPv4 = InetAddress.getByName("0.0.0.0");
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress(allIPv4, 0));
int assignedPort = listener.getLocalPort();
~~~

Đây là ví dụ **bind IPv4 wildcard**. Nó không tạo ra một “IP public” để trả về client. Cần **chọn riêng** một hostname/IP phù hợp với **vị trí của client**; trong một container hoặc phía sau NAT, cổng ở ngoài host cũng có thể khác với cổng đã bind bên trong.

**Rủi ro mở truy cập:** bind wildcard có thể làm dịch vụ nhận kết nối trên nhiều interface hơn dự kiến. Dùng cấu hình network ACL/firewall, TLS/xác thực và địa chỉ bind phù hợp với nhu cầu thực tế.

### Bind vào IP cụ thể

Nếu máy có nhiều NIC, bind vào một IP cụ thể giới hạn local endpoint mà socket lắng nghe. IP đó phải có thể dùng ở network namespace của tiến trình. **InetAddress.getLocalHost()** không phải công thức đáng tin để chọn địa chỉ cần công bố: tên máy có thể resolve về loopback, IP nội bộ, một trong nhiều NIC hoặc địa chỉ khác client không truy cập được.

## 4. Đọc đúng địa chỉ và cổng đã được OS cấp

Với **ServerSocket** đã bind:

~~~java
int port = listener.getLocalPort();
InetAddress bindAddress = listener.getInetAddress();
InetSocketAddress actual = (InetSocketAddress) listener.getLocalSocketAddress();

System.out.println(actual.getPort() == port);   // true nếu bind hợp lệ.
~~~

Đây là snippet cần được đặt trong ngữ cảnh có biến **listener** đã bind; stdout trong comment chỉ đúng khi listener như mô tả.

- **getLocalPort()** trả cổng TCP đã cấp, là giá trị quan trọng nhất khi bind port 0.
- **getInetAddress()** trả local address dùng cho bind. Nếu bind wildcard, đây vẫn là **wildcard address**, không phải địa chỉ client ngoài host sẽ truy cập.
- **getLocalSocketAddress()** trả một **SocketAddress** (trên TCP Internet socket là **InetSocketAddress**) gồm address và cổng. Nó trả null nếu ServerSocket chưa từng bind.
- **getLocalSocketAddress()** có thể tiếp tục phản ánh endpoint từng bind dù socket đã đóng; không dùng getter như health check.

**Đừng đọc port trước bind rồi công bố -1 hoặc 0.** Ngoài ra, **đừng công bố cổng của Socket vừa accept()** vì socket đó biểu diễn một connection, không phải listener đăng ký dịch vụ. Lấy thông tin từ **ServerSocket** còn mở.

Với Java NIO, cùng nguyên tắc áp dụng cho **ServerSocketChannel**:

~~~java
// Snippet: cần import java.net.* và java.nio.channels.ServerSocketChannel.
try (ServerSocketChannel channel = ServerSocketChannel.open()) {
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
    InetSocketAddress actual =
            (InetSocketAddress) channel.getLocalAddress();
    System.out.println(actual.getPort() > 0); // true khi bind thành công.
}
~~~

**ServerSocketChannel.getLocalAddress()** phản ánh local address sau bind; vẫn cần chọn địa chỉ công bố phù hợp với client. Với protocol HTTP, WebSocket hoặc TLS chạy trên TCP, port 0 và địa chỉ bind có cùng nguyên tắc, nhưng **scheme và cách truy cập** phải được xác định theo protocol thực tế.

## 5. Quy trình đăng ký endpoint sau bind

Một thứ tự triển khai đáng tin là:

~~~text
CHUẨN BỊ
  ├─ chọn bind host/interface và quyền truy cập
  ├─ chọn port = 0 khi cần OS tự cấp
  └─ cấu hình các socket option cần đặt trước bind
          ↓
BIND THÀNH CÔNG
  ├─ OS đăng ký listener và cấp cổng thực
  └─ đọc listener.getLocalPort() / getLocalSocketAddress()
          ↓
CHUẨN BỊ SERVE TRAFFIC
  ├─ accept loop / worker / dependencies đã sẵn sàng
  └─ xác định reachable host và exposed port cho client
          ↓
CÔNG BỐ (READY)
  ├─ in metadata có cấu trúc / IPC / registry / service discovery
  └─ client lấy endpoint từ nguồn công bố, không đoán cổng
          ↓
SHUTDOWN
  ├─ dừng nhận kết nối mới, thu hồi đăng ký/đánh dấu not-ready
  └─ đóng listener, xử lý các connection còn lại theo policy
~~~

Hai khái niệm cần tách:

- **Bound address**: địa chỉ mà OS chấp nhận cho listener. Ví dụ **0.0.0.0:52741** trong container.
- **Advertised endpoint**: địa chỉ/port thực sự dùng bởi một nhóm client cụ thể. Ví dụ **tcp-service.internal.example:52741**, hoặc **gateway.example.org:443** nếu bên ngoài kết nối qua proxy. Phải lấy **cổng đã cấp** cho listener bên trong, sau đó tính tới port mapping/proxy nếu có.

**Chỉ công bố sau khi bind thành công và ứng dụng đủ sẵn sàng phục vụ.** Nếu đăng ký trước rồi bind thất bại, client sẽ thấy một endpoint không hoạt động. Ngược lại, nếu listener đã bind nhưng service chưa thể xử lý request, việc công bố quá sớm có thể khiến health check hoặc request đầu tiên thất bại. Quy trình readiness của hệ thống phải phản ánh trạng thái thực, không chỉ **isBound()**.

## 6. Ví dụ Java 17+ hoàn chỉnh: port 0 và công bố qua directory trong bộ nhớ

Ví dụ dùng **một tiến trình** để tập trung vào cơ chế. Listener bind vào **loopback:0**; OS cấp cổng thực; chương trình đặt **Endpoint(address, actualPort)** vào một directory theo tên dịch vụ **echo**. Client đọc directory và kết nối bằng chính endpoint đã được công bố. Đây là cách truyền thông tin **trong cùng tiến trình** để minh họa discovery. Trong ứng dụng nhiều tiến trình/máy, directory phải được thay bằng kênh công bố chung phù hợp.

Tạo tệp **PortZeroServerDemo.java**:

~~~java
import java.io.DataInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PortZeroServerDemo {
    record Endpoint(InetAddress address, int port) {
        InetSocketAddress socketAddress() {
            return new InetSocketAddress(address, port);
        }
    }

    public static void main(String[] args) throws Exception {
        Map<String, Endpoint> directory = new HashMap<>();
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket()) {
            System.out.println("beforeBindPort=" + listener.getLocalPort());
            listener.bind(new InetSocketAddress(loopback, 0), 16);
            listener.setSoTimeout(3_000);

            Endpoint endpoint = new Endpoint(loopback, listener.getLocalPort());
            directory.put("echo", endpoint);
            System.out.println("bound=" + listener.isBound());
            System.out.println("assignedPortValid=" + (endpoint.port() > 0));
            System.out.println("publishedMatchesBind=" +
                    (endpoint.port() == listener.getLocalPort()
                     && endpoint.address().equals(listener.getInetAddress())));

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverResult = executor.submit(() -> {
                    try (Socket accepted = listener.accept()) {
                        accepted.setSoTimeout(3_000);
                        byte[] request = new byte[4];
                        new DataInputStream(accepted.getInputStream())
                                .readFully(request);
                        accepted.getOutputStream().write(
                                "PONG".getBytes(StandardCharsets.US_ASCII));
                        return new String(request, StandardCharsets.US_ASCII);
                    }
                });

                Endpoint discovered = directory.get("echo");
                try (Socket client = new Socket()) {
                    client.connect(discovered.socketAddress(), 3_000);
                    client.setSoTimeout(3_000);
                    client.getOutputStream().write(
                            "PING".getBytes(StandardCharsets.US_ASCII));
                    byte[] response = new byte[4];
                    new DataInputStream(client.getInputStream())
                            .readFully(response);
                    System.out.println("clientResponse=" +
                            new String(response, StandardCharsets.US_ASCII));
                }
                System.out.println("serverRequest=" +
                        serverResult.get(3, TimeUnit.SECONDS));
            } finally {
                directory.remove("echo", endpoint);
                executor.shutdownNow();
            }
            System.out.println("directoryCleaned=" +
                    !directory.containsKey("echo"));
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 PortZeroServerDemo.java
java PortZeroServerDemo
~~~

**Stdout trong lần chạy thành công** (đã biên dịch với **--release 17** và chạy kiểm chứng trên JDK 24):

~~~text
beforeBindPort=-1
bound=true
assignedPortValid=true
publishedMatchesBind=true
clientResponse=PONG
serverRequest=PING
directoryCleaned=true
~~~

Từng dòng nói lên điều gì?

1. **beforeBindPort=-1**: constructor **new ServerSocket()** chưa đăng ký listener.
2. **listener.bind(loopback:0, 16)**: OS chọn port còn khả dụng; không được chọn trước bằng “thử rồi đóng”. **16** là backlog yêu cầu, có thể bị OS điều chỉnh.
3. **assignedPortValid=true**: sau bind, **getLocalPort() > 0**. Chương trình cố ý không in một port cố định vì số được cấp thay đổi theo lần chạy.
4. **Endpoint** chứa **InetAddress** và số port thực rồi được đăng ký bằng **directory.put("echo", endpoint)**. Dòng **publishedMatchesBind=true** xác nhận bản ghi directory dùng đúng endpoint bind trong demo.
5. Client gọi **directory.get("echo")** rồi **connect(discovered.socketAddress(), 3000)**. Nó không biết cổng từ trước và không cần quét cổng.
6. Server thread gọi **accept()**, đọc **4 byte** bằng **DataInputStream.readFully(...)**, sau đó trả **PONG**. Client cũng đọc đủ 4 byte; không giả định một read luôn lấy đủ byte.
7. **directory.remove(...)** xóa thông tin công bố khi hoàn tất demo. Đây là một bước lifecycle quan trọng để client không dùng endpoint đã ngừng hoạt động.

**Giới hạn cố ý của demo:** Directory chỉ là **HashMap trong cùng một tiến trình**, không phải mạng service discovery. Cặp PING/PONG là protocol 4-byte tối giản; ứng dụng thực phải có framing, timeout và giới hạn payload rõ ràng. Loopback cho phép tự kiểm chứng mà không cần mở cổng ra mạng ngoài. Thứ tự output ổn định trong lần chạy thành công vì main thread in kết quả sau khi đã nhận response và chờ **Future** của server.

## 7. Công bố địa chỉ thật cho client như thế nào?

**Không có API Java tự động công bố port đã cấp tới mọi client.** Server phải lựa chọn một **kênh trao đổi thông tin ngoài băng (out-of-band)** phù hợp. Điều cần gửi thường là **protocol + advertised host + advertised port + trạng thái sẵn sàng**, và khi cần thêm service ID/instance ID, TLS identity, thời hạn đăng ký.

| Ngữ cảnh | Cách công bố phổ biến | Lưu ý |
| --- | --- | --- |
| Test tự động cùng JVM | Trả **server.getLocalPort()** cho test hoặc lưu **Endpoint** trong biến dùng chung | Dùng lại listener đang mở; test client kết nối đúng IP/port vừa cấp |
| Parent process khởi chạy child server | Child ghi một bản ghi **READY** có cấu trúc ra stdout/pipe/IPC sau bind; parent parse và dùng | Đồng bộ tới lúc READY, tách log thường khỏi bản ghi máy đọc |
| Hai tiến trình cùng host | File cấu hình runtime, UNIX-domain/named pipe phụ trợ hoặc kênh IPC | Cần quyền đọc phù hợp, ghi atomic, dọn file cũ và phát hiện process chết |
| Nhiều instance trên mạng | Service registry/discovery (có heartbeat, lease hoặc health check) | Công bố hostname/IP reachable, port thực, thu hồi khi dừng |
| Service nằm sau gateway/proxy | Công bố địa chỉ gateway/service ổn định | Địa chỉ public có thể có port khác listener nội bộ |
| Hệ thống test phân tán | Controller/runner nhận metadata sau bind và cấp cho test client | Không đọc một giá trị port cố định từ config khi server đang bind port 0 |

Ví dụ **bản ghi discovery** minh họa sau khi OS cấp cổng **52741**:

~~~json
{
  "service": "catalog-tcp",
  "protocol": "tcp",
  "host": "service.internal.example",
  "port": 52741,
  "ready": true
}
~~~

Đây là **mẫu bản ghi**, không phải dữ liệu từ demo; lần chạy khác có thể được cấp port khác. Trường **host** phải được chọn theo mạng của client; nếu server bind wildcard, **đừng** lấy literal **0.0.0.0** hoặc **::** làm hostname đăng ký. Nếu client cần TLS, metadata có thể cần scheme/định danh máy chủ tương thích chứng chỉ. Không dùng JSON này làm giao thức gửi byte qua TCP nếu ứng dụng chưa định nghĩa quy tắc đọc/ghi JSON.

### Công bố trong cùng process

Sau khi bind:

~~~java
// Snippet: server đã bind thành công vào địa chỉ cần thiết.
InetSocketAddress actual =
        (InetSocketAddress) listener.getLocalSocketAddress();
int port = actual.getPort();
endpointDirectory.put("catalog-tcp", new Endpoint(advertisedAddress, port));
~~~

Đây là **pseudo-snippet gợi ý thiết kế**, không phải chương trình độc lập: **endpointDirectory**, **Endpoint** và **advertisedAddress** là các đối tượng mà ứng dụng phải tự định nghĩa. Với một JVM, có thể dùng dependency injection, object trả về từ hàm start, future/Promise hoặc một map thread-safe. Nếu nhiều thread truy cập directory, **HashMap** thường không đủ bảo đảm đồng bộ; cân nhắc **ConcurrentHashMap** hoặc cơ chế đồng bộ tương ứng. Demo ở trên đăng ký và đọc map trên cùng main thread nên không có truy cập map đồng thời.

### Công bố giữa process hoặc qua network

Một parent process có thể đợi dòng thông báo có cấu trúc sau khi child bind. Một registry mạng có thể chứa **(service name, reachable host, port, instance ID)** và trạng thái health/lease. Trước khi trả endpoint cho client, cần kiểm tra service còn ready. Khi server dừng, xóa/expire bản ghi; khi restart, đăng ký lại port mới vì port 0 có thể đổi.

**Công bố bằng cách ghi log mà không có consumer có thể đọc đáng tin chưa phải service discovery.** Nếu log bị trộn với stdout bình thường, parser dễ nhầm hoặc bỏ lỡ trạng thái READY. Kênh metadata nên có định dạng rõ, cơ chế đồng bộ và xử lý lỗi.

### Host, port và IPv6

Nếu xuất endpoint dưới dạng chuỗi **host:port**, IPv6 có dấu hai chấm bên trong địa chỉ; dạng **[::1]:52741** giúp tránh nhầm tách port. Đơn giản hơn, giữ **host** và **port** thành **hai trường dữ liệu** rồi dùng **new InetSocketAddress(host, port)** hoặc constructor **InetSocketAddress(InetAddress, int)** cho client.

Đối với HTTP/HTTPS thực sự, có thể dùng **java.net.URI** với scheme **http/https** và các thành phần host/port phù hợp; **đừng** tự gắn **http://** vào dịch vụ TCP dùng protocol tùy biến như PING/PONG trong demo. Một endpoint là khả năng truy cập mạng; cú pháp địa chỉ phải khớp với protocol mà server thực sự cung cấp.

## 8. Trong container, NAT, proxy và nhiều interface: bind khác advertise

### Docker/container

Một process trong container có thể bind **0.0.0.0:52741**. Client ngoài container không thể mặc định truy cập IP container hay cổng đó. Khi dùng Docker port publishing, host port được ánh xạ tới **container port** đã được cấu hình. Ví dụ nếu **container listener thực sự là port 52741**, ánh xạ host port 18080 sang 52741 cần cấu hình tương ứng. Nếu container lại bind port 0 và chọn port khác mỗi lần, ánh xạ tĩnh tới 52741 sẽ sai.

**Port 0 trong ứng dụng** khác với yêu cầu Docker **tự chọn host port** khi publish một **container port cố định**. Hai lớp cấp port xảy ra ở hai network namespace/điểm ánh xạ khác nhau, cần được quản lý riêng.

### Kubernetes/service mesh/load balancer

Một Kubernetes Service thường dùng địa chỉ/port dịch vụ ổn định, trỏ tới targetPort của workload. Nếu chính ứng dụng trong Pod bind port 0 rồi chọn port ngẫu nhiên, hệ thống routing/service discovery tiêu chuẩn **không tự biết** port mới đó nếu không có cơ chế cập nhật tương ứng. Với production service thông thường, **port bind cố định bên trong workload** và **địa chỉ Service ổn định** thường đơn giản hơn. Port 0 đặc biệt hữu ích ở **test, local multi-instance, embedded servers**, hoặc khi controller có quy trình registration động thực sự.

Khi có reverse proxy hoặc TLS termination, endpoint client thấy có thể là **https://gateway.example.org:443**, trong khi backend bind TCP ở **10.0.2.15:52741**. Client không cần biết cổng nội bộ nếu proxy xử lý tuyến đúng. Công bố endpoint theo góc nhìn của **đối tượng dùng nó**, không phải chỉ copy các trường của ServerSocket.

### Host có nhiều NIC

Một server có thể có IPv4 nội bộ, IPv6, VPN và mạng quản trị. Bind wildcard cho phép listener có mặt ở các interface thích hợp, nhưng chọn IP nào để công bố phụ thuộc mạng của client. Việc tự dùng **InetAddress.getLocalHost()**, hostname của máy hoặc IP đầu tiên tìm thấy có thể chọn sai đường đi. Cấu hình advertised address rõ ràng hoặc nhận từ cơ chế triển khai/discovery đáng tin giúp tránh lỗi.

### Kiểm soát truy cập

Port 0 chỉ giảm khả năng đụng cổng; **không phải cơ chế bảo mật bằng cách giấu số port**. Listener bind wildcard có thể mở rộng bề mặt truy cập. Client phải đáp ứng xác thực, phân quyền, mã hóa khi cần; firewall và network policy phải cho phép đường đi thật. Nếu một endpoint nội bộ được công bố ra bên ngoài mà không có chủ đích, đây là lỗi cấu hình dù bind thành công.

## 9. Vòng đời, khởi động đồng thời và các lỗi khó thấy

### Không công bố trước khi bind

Giả sử hai server đều yêu cầu cổng 0 cùng lúc. OS có thể cấp hai cổng khác nhau để tránh xung đột listener. Nhưng nếu chương trình ghi registry **port = 0** trước bind, cả hai bản ghi đều vô dụng. Luồng đúng là **bind → kiểm tra port thực → hoàn thành readiness → đăng ký**.

### Không giữ bản ghi cũ sau khi đóng

Sau **close()**, **ServerSocket.getLocalPort()** có thể vẫn báo port trước đây, và **isBound()** có thể vẫn true. Các getter này không chứng minh endpoint còn được phục vụ. Khi shutdown/restart cần **unregister/expire** bản ghi; client đã cache endpoint cũ cần retry và refresh discovery theo protocol.

### Không coi listener đã bind là request đã sẵn sàng

OS có thể nhận TCP handshake khi connection đang chờ trong backlog; application thread có thể chưa kịp gọi **accept()**, chưa khởi tạo dependencies, hoặc chưa sẵn sàng xử lý byte. Readiness nên bao gồm việc server có thể phục vụ request theo contract, có thể xác minh bằng health check thích hợp, không chỉ **listener.isBound()**.

### Đừng dùng cổng được cấp làm danh tính bền vững

Port 0 có thể trả **52741** ở một lần chạy và **54632** ở lần tiếp theo. Định danh service nên là **service name/instance ID**, còn endpoint là trạng thái runtime cập nhật được. Cũng không nên lưu một port ngẫu nhiên vào cấu hình triển khai rồi giả định nó vẫn sẵn có trong lần chạy sau.

### Đừng bỏ qua lỗi bind

**BindException: Address already in use** có thể xuất hiện khi bind cổng cố định hoặc khi có cấu hình/port reservation đặc thù. **BindException: Cannot assign requested address** thường gợi ý IP không khả dụng tại host/namespace, dù thông báo cụ thể phụ thuộc OS. Nếu bind thất bại, **không công bố endpoint**. Bắt exception kèm thông tin cấu hình bind và nguyên nhân; không tự đổi sang wildcard hoặc interface khác nếu không có yêu cầu rõ.

### Lưu ý ngoại lệ khi dùng port 0

OS vẫn có thể không cấp được cổng nếu dải cổng khả dụng cạn, policy hạn chế hoặc gặp lỗi tài nguyên. Port 0 giúp giảm xung đột nhưng không bảo đảm bind luôn thành công. Mỗi listener vẫn tiêu thụ tài nguyên OS và cần được đóng đúng vòng đời.

## 10. Chẩn đoán vì sao client không kết nối được

| Hiện tượng | Điểm cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| **getLocalPort() == -1** | ServerSocket chưa bind | Gọi bind trước, kiểm tra exception và trạng thái |
| Registry đang lưu **port 0** | Công bố trước khi bind hoặc lưu config gốc | Lấy port từ **getLocalPort()** sau bind |
| Client ở máy khác gọi **127.0.0.1** | Loopback là “máy của chính client” | Chọn địa chỉ reachable từ máy client; bind đúng interface |
| Client gọi **0.0.0.0:port** | Wildcard dùng để bind | Công bố IP/hostname định tuyến được |
| Chạy trong container, host không truy cập | Port mapping sai hoặc container chỉ bind loopback | Kiểm tra internal listener port, host publish port và network |
| Client chỉ truy cập được IPv4, server chỉ bind IPv6 | Địa chỉ/dual stack không tương thích | Xác minh bind family, DNS A/AAAA và route |
| Sau restart client dùng port cũ | Port động đã đổi | Đăng ký lại, expire cache hoặc dùng route ổn định |
| TCP connect thành công nhưng request timeout | Listener/accept loop/handler chưa sẵn sàng | Kiểm tra readiness, backlog, thread pool, protocol và timeout |
| Server có port nhưng bị **Connection refused** | Không còn listener, sai IP:port hoặc bị từ chối | Kiểm tra PID/service, interface, endpoint công bố và policy |
| Đôi khi port “bị chiếm” dù đã probe trống | Race giữa probe và bind | Giữ nguyên listener bind port 0; không đóng rồi bind lại |

Dùng **netstat -ano** trên Windows, hoặc **ss -ltnp** trên Linux (nếu có quyền) để xem local listener thực tế. So sánh với cổng mà **ServerSocket.getLocalPort()** báo sau bind, interface, network namespace và địa chỉ công bố. Trong container, xem cả listener **bên trong** và port mapping **bên ngoài**.

Khi debug, nên log các thông tin phân biệt được:

~~~text
service=catalog-tcp
bindHost=127.0.0.1
bindRequestedPort=0
assignedListenPort=52741
advertisedHost=127.0.0.1
advertisedPort=52741
ready=true
~~~

Đây là **một bản ghi minh họa**; nếu server dùng port 0, lần chạy thật có thể được cấp số khác. Đặt **bindRequestedPort**, **assignedListenPort** và **advertisedPort** thành các trường khác nhau sẽ giúp nhận diện lỗi khi dùng proxy/NAT hoặc khi người quản trị nhầm địa chỉ bind với địa chỉ truy cập.

## 11. Checklist thiết kế và bài tập tự kiểm tra

**Trước khi đưa listener vào sử dụng:**

1. Chọn **bind IP** theo nhu cầu: loopback cho test nội bộ, interface cụ thể hoặc wildcard có kiểm soát nếu cần truy cập xa.
2. Nếu yêu cầu port 0, gọi **bind(..., 0)** một lần và giữ nguyên socket đang mở; không dùng port 0 như port đích của client.
3. Lấy **getLocalPort()** hoặc **getLocalSocketAddress()** **sau bind** và xác nhận port hợp lệ.
4. Chọn **advertised host/port** theo mạng của client; cân nhắc NAT/proxy/container, IPv4/IPv6 và tên DNS.
5. Đảm bảo accept loop và xử lý protocol đủ sẵn sàng, rồi mới công bố trạng thái READY và endpoint qua kênh client đọc được.
6. Khi dừng/restart, thu hồi hoặc expire đăng ký, đóng socket, cập nhật port mới nếu có.
7. Dùng kết nối và response theo protocol để xác minh dịch vụ hoạt động; không lấy **isBound()** hoặc **getLocalPort()** làm health check duy nhất.

**Bài tập:**

1. Vì sao **new ServerSocket(0)** ít xảy ra xung đột hơn **new ServerSocket(8080)** khi nhiều test chạy song song? Cổng được OS chọn có cố định sau khi process restart không?
2. Một server bind **0.0.0.0:0** và được cấp **51423**. Vì sao client ở máy khác không nên dùng **0.0.0.0:51423**? Khi nào client cần địa chỉ public thay vì IP nội bộ?
3. Tại sao quy trình “bind 0 để tìm port → close → bind lại port đó” vẫn có race? Làm cách nào giữ quyền sử dụng cổng?
4. Một service chạy trong container ở cổng **51423**, nhưng bên ngoài publish trên **443** qua reverse proxy. Cần công bố endpoint nào cho client công cộng và endpoint nào cho peer nội bộ?
5. **isBound() == true** sau close có chứng minh listener còn hoạt động không? Registry phải xử lý tình huống shutdown và restart như thế nào?
6. Với test Java, hãy sửa ví dụ để chạy ba listener đồng thời trên loopback:0. Mỗi listener phải trả port khác nhau khi cùng bind thành công; client phải dùng đúng port được từng listener công bố.
7. Khi thử với IPv6 loopback, vì sao nên dùng **InetAddress.getLoopbackAddress()** và cấu trúc **InetSocketAddress**, thay vì tự ghép chuỗi IPv6 với dấu **:**?

**Điểm cần ghi nhớ:** **Port 0 được dùng lúc bind**, OS mới là bên cấp cổng, và chỉ **getLocalPort()/getLocalSocketAddress() sau bind** mới cho biết endpoint thực. **Bind address** xác định nơi listener nhận kết nối; **advertised address** phải phản ánh đường đi mà client sử dụng. Một giải pháp đúng cần giữ listener đang mở, công bố port thật sau readiness, và dọn registration khi server dừng.

**Tham khảo API:** [ServerSocket (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html), [InetSocketAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html), [Socket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html), [ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).