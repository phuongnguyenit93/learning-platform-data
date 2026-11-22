# Giới hạn của `getLocalHost()` và `isReachable()` khi đánh giá khả năng kết nối

## Mục tiêu học tập

Trong Java, hai phương thức `java.net.InetAddress.getLocalHost()` và `InetAddress.isReachable(...)` thường bị dùng như câu trả lời nhanh cho những câu hỏi rất khác nhau: "Máy đang dùng IP nào?", "Máy có mạng không?", "Server có sống không?", hoặc "Ứng dụng của tôi gọi được API chứ?". **Không phương thức nào tự xác nhận rằng một dịch vụ ở host và port cụ thể đang dùng được.**

Sau bài này, bạn sẽ hiểu chính xác thông tin mà mỗi API trả về; vì sao kết quả có thể gây nhầm lẫn trên máy nhiều card mạng, container, VPN hoặc hệ thống bị firewall chặn; cách kiểm tra DNS, TCP, TLS và HTTP ở đúng tầng; và cách viết phép thử Java 17+ có timeout cùng khả năng giải thích kết quả.

## 1. Phân biệt những câu hỏi trước khi chọn API

| Câu hỏi cần trả lời | Công cụ phù hợp | Điều **chưa** được chứng minh |
|---|---|---|
| Hệ thống đặt tên máy hiện tại là gì và tên đó phân giải thành IP nào? | `InetAddress.getLocalHost()` | IP đó là IP public, IP gửi ra mạng, hay IP mà máy khác truy cập được |
| Những địa chỉ IP nào gắn với các giao diện mạng? | `NetworkInterface.getNetworkInterfaces()` | Địa chỉ nào sẽ được chọn làm nguồn khi kết nối đến một đích cụ thể |
| Tên `api.example.com` phân giải thành những IP nào? | `InetAddress.getAllByName("api.example.com")` | Bất kỳ IP nào thực sự nhận kết nối |
| Một địa chỉ IP có phản hồi phép dò reachability của JDK không? | `address.isReachable(timeout)` | Port dịch vụ `443`/`8080` mở, TLS hợp lệ, HTTP hoạt động |
| Client có hoàn thành kết nối TCP tới host:port không? | `Socket.connect(endpoint, timeout)` | Server hiểu HTTP, TLS handshake thành công hay nghiệp vụ khỏe mạnh |
| Endpoint HTTP(S) trả về phản hồi như kỳ vọng không? | `HttpClient.send(...)` + kiểm tra status/body | Mọi phụ thuộc hoặc toàn hệ thống luôn khỏe mạnh |

Nguyên tắc quan trọng: **không dùng phép đo ở tầng thấp hơn để tự động kết luận tầng cao hơn hoạt động**. DNS thành công không chứng minh TCP; TCP thành công không chứng minh TLS/HTTP; HTTP trả lời không chứng minh dữ liệu hoặc nghiệp vụ đúng.

```text
Tên host / cấu hình máy
         │
         ▼
Name service (DNS, hosts file, cache...) ─► địa chỉ IP
         │
         ▼
Route, interface, firewall, NAT ──────────► đường truyền tới IP
         │
         ▼
TCP host:port ────────────────────────────► kết nối dịch vụ
         │
         ▼
TLS (nếu dùng HTTPS) ────────────────────► phiên bảo mật
         │
         ▼
HTTP request + status + payload ─────────► hành vi của API
```

`getLocalHost()` liên quan **tên/địa chỉ máy hiện tại**, còn `isReachable()` là phép dò **tới một địa chỉ IP**. Chúng nằm ở hai vị trí khác nhau trong sơ đồ và không thay cho kiểm tra dịch vụ.

## 2. `InetAddress.getLocalHost()` thực sự làm gì?

Theo hợp đồng API của Java 17, phương thức tĩnh:

```java
InetAddress local = InetAddress.getLocalHost();
String ipText = local.getHostAddress();
```

lấy **hostname được hệ thống cung cấp cho máy hiện tại**, rồi dùng cơ chế phân giải tên của môi trường để tìm một `InetAddress`. Cơ chế này có thể chịu ảnh hưởng của file `hosts`, DNS, cấu hình name service hoặc cache; API có thể cache kết quả trong thời gian ngắn.

Đây là **phép phân giải tên**, không phải lệnh "kiểm tra kết nối Internet", không phải truy vấn "IP public của tôi" và cũng không phải lựa chọn giao diện phù hợp với một server từ xa.

### 2.1. Những kết luận có thể và không thể rút ra

Giả sử `getLocalHost().getHostAddress()` trả về `192.168.1.12`. Ta chỉ biết tên máy hiện tại đã được phân giải tới địa chỉ đó trong môi trường đang chạy. Không thể kết luận từ một kết quả này rằng:

- `192.168.1.12` là địa chỉ được dùng khi Java mở socket tới `203.0.113.10`. Hệ điều hành chọn đường đi/địa chỉ nguồn theo route, binding và chính sách mạng.
- Máy khác trên Internet truy cập trực tiếp được `192.168.1.12`. Đây là dạng địa chỉ private; firewall, NAT, port mapping và đường truyền còn phải phù hợp.
- Địa chỉ đó đã được gắn vào interface đang hoạt động hoặc cổng ứng dụng đang lắng nghe.
- `getLocalHost()` luôn trả về địa chỉ IPv4. Kết quả có thể là IPv4 hoặc IPv6, tùy môi trường.
- Kết quả ổn định mãi mãi. DHCP, VPN, container, DNS/hosts và cache có thể thay đổi theo thời gian.

### 2.2. Vì sao kết quả dễ gây ngộ nhận?

**Máy nhiều card mạng.** Laptop có Wi-Fi, Ethernet, VPN, loopback hoặc các interface ảo. Hostname thường chỉ phân giải ra một địa chỉ, trong khi các đích khác nhau có thể dùng route và địa chỉ nguồn khác nhau.

**Container, VM, Kubernetes.** Code chạy trong network namespace của container có thể thấy IP nội bộ của container/pod, không phải IP của host vật lý hay địa chỉ public của dịch vụ. Pod được tái tạo thì IP có thể đổi; client từ ngoài thường truy cập qua Service, ingress hoặc proxy thay vì địa chỉ mà `getLocalHost()` quan sát.

**File hosts hoặc DNS không nhất quán.** Hostname có thể được ánh xạ tới loopback, IP cũ hoặc IP không còn gắn lên máy. Khi hostname không phân giải được, `getLocalHost()` có thể ném `UnknownHostException` **dù TCP tới một IP khác vẫn hoạt động**. Ngược lại, `getLocalHost()` có thể trả về thành công ngay khi adapter mạng đang ngắt kết nối, do thông tin tên được cấu hình sẵn hoặc cache.

**Cơ chế bảo mật cũ của Java 17.** Nếu có `SecurityManager` và kiểm tra quyền không cho phép phân giải tên local, đặc tả Java 17 cho phép trả về địa chỉ loopback. Đây là một trường hợp trong API lịch sử, không phải bằng chứng rằng máy chỉ có loopback.

### 2.3. Các API khác phục vụ mục đích khác

- `InetAddress.getLoopbackAddress()`: lấy địa chỉ loopback (`127.0.0.1` hoặc `::1`), thích hợp cho server/client thử nghiệm **trên cùng máy**. Không thay cho địa chỉ có thể truy cập từ bên ngoài.
- `NetworkInterface.getNetworkInterfaces()`: liệt kê các giao diện và địa chỉ mà môi trường Java nhìn thấy. Cần phân biệt interface ảo, loopback, trạng thái up/down, IPv4 và IPv6; việc interface đang up **không bảo đảm** Internet hoạt động.
- `socket.getLocalAddress()` sau `Socket.connect(...)`: cho biết IP local mà socket **đã chọn cho kết nối TCP cụ thể**. Đây thường là dữ kiện tốt hơn `getLocalHost()` nếu bạn muốn biết **đường ra tới một remote endpoint cụ thể**, nhưng vẫn là quan sát bên trong máy/container, không tự tiết lộ IP public sau NAT.
- `socket.getLocalSocketAddress()`: cung cấp cả địa chỉ local **và cổng local** cho kết nối đó.
- Một web service "what is my IP" có thể trả về IP mà service đó **nhìn thấy** (có thể là proxy/NAT), nhưng không chứng minh inbound connectivity; nó còn phụ thuộc vào chính service bên ngoài.

**Tránh một lỗi thiết kế thường gặp:** bind server bằng `getLocalHost()` chỉ vì nghĩ nó là địa chỉ "chính". Nếu muốn chỉ cho phép kết nối nội bộ, bind loopback rõ ràng. Nếu cần nghe trên các địa chỉ phù hợp của máy, dùng wildcard bind (`0.0.0.0` hoặc `::` tùy family/cấu hình) và quản lý firewall. **Địa chỉ bind wildcard không phải địa chỉ mà client bên ngoài nên dùng làm đích.**

## 3. `InetAddress.isReachable()` thực sự kiểm tra điều gì?

Hai overload chính:

```java
boolean reachable = address.isReachable(1500);
boolean reachableViaInterface =
        address.isReachable(networkInterface, 0, 1500);
```

Tham số `timeout` tính bằng **mili giây**; `ttl` là giới hạn số hop hoặc `0` để dùng mặc định, còn `networkInterface` chỉ định interface thử nghiệm hoặc `null` cho phép tùy chọn mặc định. Giá trị âm ở `timeout` (hoặc `ttl`) gây `IllegalArgumentException`. Phép thử có thể ném `IOException` khi gặp lỗi mạng, không nhất thiết chỉ trả về `false`.

**Điểm quan trọng nhất:** JDK mô tả đây là phép thử *best effort*. Một cách triển khai điển hình dùng **ICMP Echo Request** nếu có đủ đặc quyền; nếu không, có thể thử **TCP Echo ở port 7**, tùy hệ điều hành và JDK. Vì thế `isReachable()` không có API tham số để thử **port 443, 5432 hoặc 8080** của ứng dụng.

### 3.1. `false` không có nghĩa "dịch vụ không truy cập được"

`isReachable()` có thể trả `false` vì:

- Thiết bị hoặc firewall chặn ICMP, hoặc không bật dịch vụ TCP Echo port 7.
- Quyền truy cập socket/raw ICMP, chính sách hệ điều hành, namespace/container hoặc cấu hình mạng không cho phép phép dò.
- Đường đi ICMP bị lọc/rate limit khác với TCP traffic tới port ứng dụng.
- Timeout quá ngắn so với độ trễ hoặc thiết bị xử lý chậm.
- Các gói phản hồi đi đường khác, bị chặn hoặc không nhận được trong điều kiện thử nghiệm.

Trong những trường hợp trên, TCP tới `host:443` hoặc `host:8080` **vẫn có thể thành công**. Bởi vậy không được viết:

```java
// Sai về mặt suy luận: ICMP/Echo thất bại không phủ định TCP :443.
if (!remoteIp.isReachable(1000)) {
    throw new IllegalStateException("HTTPS service is offline");
}
```

### 3.2. `true` không có nghĩa "API đang khỏe"

Ngay cả khi `isReachable()` trả về `true`:

- Port TCP đích có thể **đóng** hoặc ứng dụng chưa khởi động.
- TCP server có thể chấp nhận connection nhưng không đọc request hoặc không phản hồi.
- TLS có thể thất bại vì certificate, hostname, phiên bản giao thức hoặc yêu cầu xác thực.
- HTTP có thể trả `401`, `403`, `404`, `429`, `500` hoặc response không đúng schema.
- DB, message broker hay upstream nghiệp vụ có thể lỗi dù host phản hồi phép dò mạng.

`isReachable()` không thể xác minh method/path HTTP, TLS, auth hay dữ liệu nghiệp vụ. `true` chỉ là **một tín hiệu cho loại phép dò mà JDK đã thực hiện** trong thời điểm đó.

### 3.3. Các giới hạn còn lại

- `isReachable()` không giống hoàn toàn lệnh `ping` của mọi hệ điều hành. Cách cài đặt, quyền, tham số và kết quả có thể khác.
- Đổi overload sang `isReachable(netif, ttl, timeout)` giúp định hướng giao diện/hop kiểm tra; **không bổ sung tham số port** và không biến nó thành health check ứng dụng.
- `getByName("host")` hoặc `getAllByName("host")` chỉ phân giải tên, không bảo đảm phản hồi ICMP hay dịch vụ TCP.
- `IOException` của phép dò phải được báo riêng nếu cần chẩn đoán; không nên gộp mọi lỗi thành "server chết".
- Kết quả là **ảnh chụp tại một thời điểm**. Việc test thành công rồi mới gửi request vẫn có rủi ro mạng/dịch vụ thay đổi ở giữa (time-of-check vs. time-of-use).

## 4. Phân tích từng kịch bản thực tế

| Quan sát | Kết luận đáng tin | Điều không được suy ra |
|---|---|---|
| `getLocalHost()` ném `UnknownHostException` | Không phân giải được hostname local bằng cơ chế hiện tại | Máy mất Internet hoặc không kết nối được service bằng IP |
| `getLocalHost()` trả `127.0.0.1` | Hostname local đang ánh xạ tới loopback | Tất cả endpoint chỉ có thể truy cập nội bộ |
| `getLocalHost()` trả IP private | Name service hiện trả IP private | Máy không có đường ra Internet hoặc IP đó là IP public |
| `isReachable(ip, 1000) == false` | Phép dò của JDK không xác nhận reachability trong điều kiện đó | TCP port 443/8080 chắc chắn đóng |
| `isReachable(ip, 1000) == true` | Đích phản hồi phép dò theo logic triển khai | HTTP/TLS hoặc business transaction sẽ thành công |
| `Socket.connect(host:port)` thành công | TCP handshake đến endpoint đó đã hoàn tất | Server trả dữ liệu đúng hay TLS/HTTP thành công |
| HTTPS trả `200` từ `/health` | Request tới endpoint đó được xử lý và trả `200` | Toàn bộ dependency đều khỏe, trừ khi endpoint có hợp đồng kiểm tra chúng |

Hai hệ thống có thể cùng cho kết quả `isReachable() == false` nhưng rất khác nhau: một hệ thống chặn ICMP và vẫn phục vụ HTTPS tốt; hệ thống kia mất route hoàn toàn. Cần **kiểm tra chính cổng và giao thức ứng dụng** để phân biệt.

## 5. Java 17+: khảo sát địa chỉ local mà không tự suy luận khả năng kết nối

Tạo file `HostIdentityInspect.java`:

```java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.UnknownHostException;
import java.util.Enumeration;

public class HostIdentityInspect {
    public static void main(String[] args) throws SocketException {
        try {
            InetAddress local = InetAddress.getLocalHost();
            System.out.println("getLocalHost IP: " + local.getHostAddress());
        } catch (UnknownHostException e) {
            System.out.println("getLocalHost: hostname not resolved");
        }

        System.out.println("loopback IP: "
                + InetAddress.getLoopbackAddress().getHostAddress());

        Enumeration<NetworkInterface> interfaces =
                NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) {
            return;
        }

        while (interfaces.hasMoreElements()) {
            NetworkInterface networkInterface = interfaces.nextElement();
            if (!networkInterface.isUp()) {
                continue;
            }

            Enumeration<InetAddress> addresses =
                    networkInterface.getInetAddresses();
            while (addresses.hasMoreElements()) {
                InetAddress ip = addresses.nextElement();
                System.out.println(networkInterface.getName() + " -> "
                        + ip.getHostAddress());
            }
        }
    }
}
```

Biên dịch và chạy từ terminal có JDK 17+:

```bash
javac -encoding UTF-8 HostIdentityInspect.java
java HostIdentityInspect
```

**Output thay đổi theo môi trường.** Chẳng hạn các dòng có thể trông như sau (chỉ minh họa, không phải kết quả bắt buộc):

```text
getLocalHost IP: 192.168.1.12
loopback IP: 127.0.0.1
eth0 -> 192.168.1.12
lo -> 127.0.0.1
```

Trên máy khác, `getLocalHost` có thể thất bại, loopback có thể là IPv6 `::1`, interface mang tên khác, và số lượng IP có thể nhiều hơn. Danh sách trên giúp **kiểm kê địa chỉ** mà môi trường đang thấy, chưa xác nhận kết nối ra ngoài. Nếu muốn biết IP nguồn của một kết nối thực, hãy quan sát `Socket.getLocalAddress()` **sau khi kết nối tới đúng đích**.

## 6. Java 17+: đặt `isReachable()` cạnh một kết nối TCP thật

Ví dụ sau dùng loopback để tránh phụ thuộc DNS và Internet. Nó in kết quả reachability theo cơ chế của JDK, sau đó tạo một TCP listener trên **port tạm thời** và kết nối tới listener đó. Không hề có điều kiện `if (isReachable)` quyết định có thử TCP hay không.

Tạo file `ReachabilityLayersDemo.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class ReachabilityLayersDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try {
            System.out.println("isReachable(loopback): "
                    + loopback.isReachable(1000));
        } catch (IOException e) {
            System.out.println("isReachable(loopback): error "
                    + e.getClass().getSimpleName());
        }

        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(2000);
            int port = server.getLocalPort();

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, port), 2000);

                try (Socket accepted = server.accept()) {
                    System.out.println("TCP connect to listener: OK");
                    System.out.println("Client local IP: "
                            + client.getLocalAddress().getHostAddress());
                    System.out.println("Listener port: " + port);
                }
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 ReachabilityLayersDemo.java
java ReachabilityLayersDemo
```

Trên máy cho phép dùng TCP loopback, kết quả có cấu trúc như sau; boolean, IP format và port không cố định:

```text
isReachable(loopback): true
TCP connect to listener: OK
Client local IP: 127.0.0.1
Listener port: 53241
```

Dòng đầu cũng có thể in `false` hoặc báo lỗi `IOException`; dòng `Client local IP` có thể hiển thị IPv6; port 53241 chỉ là ví dụ do hệ điều hành lựa chọn. Nếu môi trường cấm mở loopback socket, phần TCP có thể ném `IOException`.

**Điều thí nghiệm minh họa:** bạn đang đo hai thứ riêng biệt. `isReachable` không biết port vừa được server bind; trong khi `Socket.connect` thử chính endpoint `(loopback, port)` mà Java server đang lắng nghe. **Kể cả TCP connect thành công cũng mới xác nhận handshake**, vì chương trình này không gửi một thông điệp ứng dụng nào.

Không biến kiểm tra này thành khẳng định rằng mọi máy sẽ có `isReachable(loopback) == true`; đặc tính đó không được chuẩn hóa thành kết quả cố định trong môi trường bị hạn chế.

## 7. Java 17+: kiểm tra đúng host và TCP port thay vì dựa vào `isReachable()`

Đối với đích thực tế, bạn thường có **hostname và port cụ thể** như `db.internal:5432` hoặc `api.example.com:443`. Mã sau phân giải tất cả địa chỉ trả về của hostname, ghi nhận kết quả `isReachable` để so sánh, rồi **vẫn thử TCP** với từng địa chỉ. Kết quả của `isReachable` không dùng làm điều kiện bỏ qua phép thử TCP.

Tạo file `TcpPortProbe.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.UnknownHostException;

public class TcpPortProbe {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println("Usage: java TcpPortProbe <host> <port>");
            return;
        }

        String host = args[0];
        int port;
        try {
            port = Integer.parseInt(args[1]);
            if (port < 1 || port > 65535) {
                throw new NumberFormatException("port out of range");
            }
        } catch (NumberFormatException e) {
            System.out.println("Port must be 1..65535");
            return;
        }

        InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(host);
        } catch (UnknownHostException e) {
            System.out.println("Name resolution failed: " + host);
            return;
        }

        for (InetAddress address : addresses) {
            String ip = address.getHostAddress();

            try {
                System.out.println(ip + " isReachable: "
                        + address.isReachable(800));
            } catch (IOException e) {
                System.out.println(ip + " isReachable error: "
                        + e.getClass().getSimpleName());
            }

            try (Socket socket = new Socket()) {
                socket.connect(new InetSocketAddress(address, port), 2000);
                System.out.println(ip + ":" + port + " TCP CONNECT OK");
                System.out.println("Actual local endpoint: "
                        + socket.getLocalSocketAddress());
                return;
            } catch (IOException e) {
                System.out.println(ip + ":" + port + " TCP failed: "
                        + e.getClass().getSimpleName());
            }
        }

        System.out.println("No resolved address accepted TCP connection.");
    }
}
```

```bash
javac -encoding UTF-8 TcpPortProbe.java
java TcpPortProbe localhost 8080
```

**Output phụ thuộc listener, DNS/hosts, địa chỉ IPv4/IPv6, firewall và hệ điều hành**. Ví dụ khi một địa chỉ loopback có dịch vụ TCP ở port 8080, có thể thấy:

```text
127.0.0.1 isReachable: true
127.0.0.1:8080 TCP CONNECT OK
Actual local endpoint: /127.0.0.1:54213
```

Đây là output minh họa, không phải lời hứa rằng `localhost` chỉ có IPv4 hay port `8080` đã mở. Khi không có listener, chương trình có thể báo `ConnectException`, `SocketTimeoutException` hoặc ngoại lệ I/O khác. Nếu hostname trả về cả IPv6 và IPv4, chương trình sẽ thử theo thứ tự mà môi trường trả về cho đến khi thành công hoặc hết các địa chỉ.

**Ý nghĩa của từng bước:**

1. `getAllByName(host)` kiểm tra việc phân giải **tên đích** và trả về các `InetAddress`. Nó không kiểm tra một port.
2. `isReachable(800)` thêm tín hiệu chẩn đoán, nhưng không kết luận trước khả năng kết nối TCP.
3. `new InetSocketAddress(address, port)` chỉ rõ IP **và TCP port đích**.
4. `socket.connect(..., 2000)` thử TCP handshake với timeout cho giai đoạn kết nối; **không** giới hạn mọi bước ứng dụng sau đó.
5. `socket.getLocalSocketAddress()` quan sát local IP và ephemeral port **của chính kết nối đã thành công**. Nó không xác nhận IP public bên ngoài NAT.
6. `TCP CONNECT OK` chưa có nghĩa TLS handshake, xác thực, HTTP request hay truy vấn DB đã thành công.

Chương trình này là **TCP connectivity diagnostic**, không phải công cụ kiểm thử UDP hoặc khả năng khỏe của một ứng dụng. Nó có thể không phản ánh đầy đủ thuật toán chọn địa chỉ, retry, DNS cache, proxy hoặc connection pool của thư viện ứng dụng thật. Khi kiểm tra một lỗi chỉ xảy ra trong chính client, hãy cấu hình phép thử gần giống client nhất có thể.

## 8. Kiểm tra đúng tầng ứng dụng: ví dụ HTTP(S)

Nếu câu hỏi thực tế là "`https://api.example.com/health` có trả kết quả hợp lệ không?", hãy gửi **HTTP request thật** bằng `HttpClient` (có trong JDK 17), thay vì dùng `getLocalHost` hoặc `isReachable`.

Tạo file `HttpHealthProbe.java`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpHealthProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java HttpHealthProbe <http(s)-url>");
            return;
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

```bash
javac -encoding UTF-8 HttpHealthProbe.java
java HttpHealthProbe https://api.example.com/health
```

URL trên là **địa chỉ minh họa**, không bảo đảm có endpoint thật để thử. Với URL hợp lệ và máy chủ trả `200`, output là:

```text
HTTP status: 200
```

Trong trường hợp khác, kết quả là status thực tế hoặc exception (DNS, TCP, timeout, TLS, proxy...). `connectTimeout` áp dụng khi cần mở connection mới; `HttpRequest.timeout` đặt giới hạn thời gian cho request. Với HTTPS, HTTP client tiêu chuẩn còn kiểm tra kết nối TLS/chứng chỉ theo cấu hình mặc định. `200` chỉ chứng minh **endpoint đã trả HTTP 200 trong lần gọi ấy**; trạng thái "healthy" phải dựa trên hợp đồng cụ thể của endpoint, kiểm tra nội dung cần thiết và các phụ thuộc mà endpoint được thiết kế để xác nhận.

Nếu dùng kiểm tra tự động, hãy định nghĩa rõ **tiêu chí thành công**: ví dụ status mong đợi, JSON schema, mã lỗi nghiệp vụ, độ trễ tối đa và credential phù hợp. `401` chứng minh một service HTTP có trả lời nhưng không chứng minh request hợp lệ; `500` cho thấy ứng dụng đã nhận được request ở một tầng nhưng xử lý phía server gặp lỗi.

## 9. Quy trình debug khi "server không kết nối được"

Đừng mở đầu bằng việc gọi `getLocalHost()` rồi lấy đó làm kết luận. Hãy xác định **đích thật** (hostname, port, giao thức, đường dẫn) và **nơi chạy phép thử** (máy vật lý, container, pod, VPN, mạng office hay máy ngoài Internet).

| Bước | Kiểm tra | Câu hỏi phân biệt |
|---|---|---|
| 1. Input/config | URL, scheme, hostname, port, proxy, service discovery | Client có đang gọi đúng môi trường và đúng endpoint không? |
| 2. Name resolution | `getAllByName(remoteHost)`; đối chiếu bản ghi/hosts | Tên đích có ra IP như mong đợi trong môi trường **client** không? |
| 3. IP/route | Route, VPN, firewall, namespace, NAT; ICMP khi phù hợp | Có dấu hiệu lỗi đường đi? Kết quả ICMP có bị lọc riêng không? |
| 4. Transport | TCP `Socket.connect(remoteIP:port, timeout)`, hoặc client UDP tương ứng | **Đúng cổng/giao thức** có tiếp nhận lưu lượng không? |
| 5. Security/protocol | TLS handshake, SNI, chứng chỉ, ALPN, giao thức DB/HTTP | Hai bên có nói đúng giao thức và xác thực được không? |
| 6. Application | HTTP method/path/status/body hoặc lệnh ping chính thức của service | Dịch vụ có xử lý yêu cầu như contract không? |
| 7. Dependencies | DB, queue, upstream API, auth, quota, thời gian đáp ứng | Từng phụ thuộc quan trọng có hoạt động không? |

Phân biệt các hiện tượng hay gặp:

- **`UnknownHostException`** từ `getLocalHost()`: hostname **local** không phân giải được; không trực tiếp nói gì về hostname server. `UnknownHostException` từ `getAllByName(remoteHost)` lại liên quan **tên đích**.
- **`ConnectException: Connection refused`** khi thử TCP: thường chỉ ra không có listener phù hợp hoặc mạng chủ động từ chối; **không** phải kết quả của HTTP status.
- **TCP connect timeout**: có thể do gói bị lọc, route/đích không phản hồi hoặc tình trạng mạng khác; không đủ để khẳng định server không tồn tại.
- **TCP connect thành công nhưng đọc response timeout**: kết nối đã tới tầng TCP, nhưng ứng dụng/giao thức hoặc quá trình xử lý/đọc tiếp có vấn đề. `Socket.setSoTimeout(...)` mới liên quan timeout cho các thao tác `read` trên socket truyền thống; connect timeout riêng không thay thế nó.
- **`isReachable() == false` cùng lúc `Socket.connect()` thành công**: hoàn toàn có thể. Phép dò ICMP/TCP Echo bị chặn còn port dịch vụ đang mở.
- **HTTP status 5xx**: HTTP endpoint có phản hồi, nhưng phía server xử lý thất bại; kiểm tra log ứng dụng/downstream thay vì dùng mỗi `ping`.

### Nhớ góc quan sát của phép thử

Kết quả `Socket.connect` từ laptop **khác** kết quả từ container chạy production nếu chúng nằm sau các route, firewall hoặc proxy khác nhau. `getLocalHost` trong container cũng mô tả môi trường container, không phải đường nhìn từ Internet. Với dịch vụ inbound, một kết nối tới `localhost` trên server chỉ chứng minh **local listener**, không đảm bảo client bên ngoài truy cập được service qua load balancer, firewall và DNS public.

Đối với server ứng dụng, phân biệt ít nhất ba phép kiểm tra:

- **Liveness**: process còn chạy/đáp ứng tối thiểu hay không.
- **Readiness**: instance đủ điều kiện nhận traffic mới hay chưa.
- **End-to-end health**: luồng nghiệp vụ có thực sự chạy qua các dependency quan trọng hay không.

Chúng là các hợp đồng vận hành khác nhau. Không nên dùng `isReachable()` như một tiêu chí thay thế toàn bộ ba phép kiểm tra.

## 10. Những lỗi thiết kế thường gặp và cách sửa

### Lỗi 1: "Địa chỉ của server chính là `getLocalHost()`"

```java
// Dễ sai trong máy nhiều NIC/container: đây chỉ là hostname local được phân giải.
String advertisedHost = InetAddress.getLocalHost().getHostAddress();
```

**Cách sửa:** địa chỉ mà client phải gọi nên lấy từ cấu hình service discovery, DNS, ingress/load balancer hoặc cấu hình endpoint được quản lý. Nếu phải đo IP local của kết nối outbound cụ thể, đọc `Socket.getLocalAddress()` sau khi kết nối tới đích.

### Lỗi 2: "`isReachable()` là TCP port health check"

```java
// Sai: boolean này không kiểm tra TCP port 443.
boolean httpsUp = InetAddress.getByName("api.example.com")
        .isReachable(1000);
```

**Cách sửa:** kiểm tra `Socket.connect(..., 443)` nếu chỉ cần biết có TCP handshake. Nếu cần HTTPS thực sự hoạt động, gửi HTTPS request bằng `HttpClient` và đánh giá status/response.

### Lỗi 3: "`false` đồng nghĩa mất mạng; `true` đồng nghĩa API tốt"

Cả hai suy luận đều vượt quá chứng cứ. Firewall có thể chặn ICMP; server có thể trả lời ICMP nhưng port ứng dụng đóng. Log phải thể hiện rõ **"probe không nhận được phản hồi"**, **"TCP connect thất bại"** hay **"HTTP health check không đạt"**, tránh gộp thành nhãn `NetworkDown` không có cơ sở.

### Lỗi 4: "Một lần kiểm tra thành công đủ đảm bảo request sau đó"

Mạng, route, DNS, process và policy có thể thay đổi ngay sau phép thử. Đừng tạo quy trình bắt buộc `isReachable()` trước mỗi HTTP request: nó có thể từ chối giả, thêm độ trễ và không bảo đảm request tiếp theo. Thiết kế client cần **timeout phù hợp, xử lý lỗi đúng chỗ, retry có kiểm soát khi an toàn, và quan sát thống kê lỗi theo thời gian**.

### Lỗi 5: "Không có timeout nghĩa là sẽ xong nhanh"

Không nên để probe chạy vô hạn. Với TCP, `connect(endpoint, timeoutMillis)` giới hạn giai đoạn connect theo API, nhưng thời gian phân giải tên, TLS và đọc response cần có chính sách timeout riêng. Với HTTP, dùng cả `HttpClient.connectTimeout(...)` khi thích hợp và `HttpRequest.timeout(...)`. Với `isReachable`, timeout chỉ dành cho phép dò best-effort, không tạo một kiểm tra toàn bộ stack dịch vụ.

## 11. Tự kiểm tra

**Câu 1.** Ứng dụng Java trong Docker in `getLocalHost() = 172.18.0.4`. Người dùng ngoài Internet phải gọi IP này?  
**Trả lời:** Không thể suy ra. Đây có thể là IP private trong network namespace. Đích public thường được cấp qua hostname/ingress/load balancer/NAT và chính sách mạng.

**Câu 2.** `remoteIp.isReachable(1000)` trả `false`, nhưng `Socket.connect(remoteIp:443)` thành công. Có mâu thuẫn không?  
**Trả lời:** Không. Probe reachability của JDK có thể dùng ICMP hoặc TCP Echo port 7, khác TCP port 443. Khi ICMP bị chặn, HTTPS vẫn có thể hoạt động.

**Câu 3.** `isReachable(1000)` trả `true`. HTTP POST `/payments` có chắc hoạt động?  
**Trả lời:** Không. Cần TCP/TLS, HTTP protocol, authentication, request validation và logic nghiệp vụ. Chỉ request thực tế hoặc health contract phù hợp mới kiểm tra các tầng liên quan.

**Câu 4.** `getLocalHost()` ném `UnknownHostException`. Bạn có nên thông báo "server database down"?  
**Trả lời:** Không. Đây là vấn đề phân giải hostname local. Hãy kiểm tra tên đích DB và phép kết nối tới DB bằng host:port riêng.

**Câu 5.** Client muốn biết local IP đã được chọn khi gọi `198.51.100.10:8443` thì nên dùng phương thức nào?  
**Trả lời:** Sau kết nối TCP thành công, xem `socket.getLocalAddress()` hoặc `socket.getLocalSocketAddress()` của **đúng socket**. Kết quả đó chưa nhất thiết là IP public sau NAT.

**Câu 6.** Vì sao kiểm tra `localhost:8080` thành công mà user ở mạng khác vẫn không vào được ứng dụng?  
**Trả lời:** Listener có thể chỉ bind loopback; hoặc firewall, NAT, ingress, DNS, VPN, route hay TLS/proxy phía ngoài đang cản trở. Local TCP success không chứng minh đường truy cập inbound từ nơi khác.

## 12. Tóm tắt vận dụng

- `getLocalHost()` = **hostname của máy hiện tại → phân giải ra một địa chỉ**. Không dùng nó làm bằng chứng IP public, egress IP hay khả năng truy cập service.
- `isReachable()` = **best-effort probe tới một địa chỉ**, có thể dựa vào ICMP hoặc TCP Echo port 7, chịu ảnh hưởng quyền và firewall. `true`/`false` không nói chắc gì về port ứng dụng.
- `getAllByName(remoteHost)` = phân giải **tên đích**; `Socket.connect(remoteIP:port, timeout)` = kiểm tra TCP **đúng port**; `HttpClient` = thử HTTP(S) ở tầng ứng dụng.
- Dùng **phép kiểm tra cùng tầng với yêu cầu**, chạy từ **đúng nơi client hoạt động**, với timeout và phân loại lỗi phù hợp. Mọi phép kiểm tra là quan sát tại một thời điểm, không phải bảo đảm cho lần gọi kế tiếp.

### Tài liệu gốc của Java 17

- [`InetAddress` — `getLocalHost`, `isReachable`, `getLoopbackAddress`, `getAllByName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html)
- [`NetworkInterface` — giao diện và địa chỉ mạng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [`Socket` — `connect` và local/remote socket address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`HttpClient` — HTTP request/response và timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
