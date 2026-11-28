# `InetSocketAddress`: chọn loopback tường minh và tránh vô tình bind mọi giao diện

> **Chương:** API SimpleFileServer  
> **Module học:** `JAVA_VERSION_JAVA18` — `SimpleFileServer` được bổ sung từ Java 18 và nhận `InetSocketAddress`; bản thân `InetSocketAddress`/`InetAddress` là các API nền tảng có từ những JDK trước đó, vẫn còn áp dụng trên JDK hiện đại.  
> **Mục tiêu:** Biết chọn địa chỉ bind cho `SimpleFileServer.createFileServer(...)`, phân biệt loopback với wildcard address, hiểu hệ quả của IPv4/IPv6 và xác minh địa chỉ/cổng mà server thực sự lắng nghe.

## 1. Địa chỉ bind quyết định phạm vi truy cập

Khi tạo HTTP server, ngoài việc chọn cổng, ứng dụng cần chọn **địa chỉ IP cục bộ** mà server sẽ lắng nghe. Hai server cùng dùng cổng `8080` nhưng bind vào địa chỉ khác nhau có thể có phạm vi truy cập rất khác:

- Bind vào **loopback**: client trên chính máy (cùng network namespace) có thể kết nối qua giao diện loopback. Máy khác trong mạng không kết nối trực tiếp tới địa chỉ loopback của máy này.
- Bind vào **wildcard/any-local**: server lắng nghe trên mọi địa chỉ giao diện mạng phù hợp của máy, thay vì giới hạn vào một địa chỉ cụ thể.

Điểm này đặc biệt quan trọng khi dùng `SimpleFileServer`: Javadoc xác định công cụ này dành cho **testing, development và debugging**. Nếu chỉ muốn xem tệp trên máy đang phát triển, hãy chọn loopback tường minh để tránh vô tình mở thư mục ra mạng.

`InetSocketAddress` biểu diễn một cặp **địa chỉ IP (hoặc hostname) + cổng**. Đối tượng này được truyền vào `SimpleFileServer.createFileServer(addr, rootDirectory, outputLevel)`; server được bind theo địa chỉ đó.

## 2. Cách tạo địa chỉ: loopback và wildcard

### 2.1. Constructor dễ gây bất ngờ: `new InetSocketAddress(port)`

Đoạn code rất ngắn sau thường xuất hiện trong ví dụ:

```java
InetSocketAddress address = new InetSocketAddress(8080);
```

Constructor này tạo địa chỉ với **wildcard address**. Nó không có nghĩa là chỉ lắng nghe ở `localhost`. Khi dùng làm địa chỉ bind, wildcard cho phép server nhận kết nối trên mọi giao diện mạng cục bộ phù hợp.

Tương tự, overload nhận `InetAddress` mà truyền `null` cũng chọn wildcard:

```java
InetSocketAddress address =
        new InetSocketAddress((InetAddress) null, 8080);
```

Phép ép kiểu `(InetAddress)` cần thiết nếu viết `null`, vì constructor có overload nhận `String` và overload nhận `InetAddress`. Cả hai ví dụ trên **không phải lựa chọn phù hợp** nếu yêu cầu chỉ truy cập từ máy hiện tại.

### 2.2. Chọn loopback tường minh

API `InetAddress.getLoopbackAddress()` trả về một địa chỉ loopback. Theo Javadoc, địa chỉ này có thể là IPv4 `127.0.0.1` hoặc IPv6 `::1`, tùy môi trường:

```java
InetAddress loopback = InetAddress.getLoopbackAddress();
InetSocketAddress address = new InetSocketAddress(loopback, 8080);
```

Đây là lựa chọn gọn và không phụ thuộc vào việc hostname `localhost` được phân giải theo thứ tự IPv4/IPv6 nào. Nếu ứng dụng cần cố định một họ địa chỉ:

```java
// Cố định IPv4 loopback:
InetAddress ipv4Loopback = InetAddress.getByName("127.0.0.1");
InetSocketAddress ipv4Address =
        new InetSocketAddress(ipv4Loopback, 8080);

// Cố định IPv6 loopback:
InetAddress ipv6Loopback = InetAddress.getByName("::1");
InetSocketAddress ipv6Address =
        new InetSocketAddress(ipv6Loopback, 8080);
```

`getByName` khai báo `UnknownHostException`; trong ví dụ trên, chuỗi là IP literal nên không cần truy vấn DNS. Cách dùng `InetAddress.getLoopbackAddress()` phù hợp khi không cần ép ứng dụng sang riêng IPv4 hoặc IPv6.

### 2.3. So sánh nhanh

| Cách tạo | Ý nghĩa địa chỉ | Phạm vi dự kiến khi bind server |
| --- | --- | --- |
| `new InetSocketAddress(8080)` | Wildcard/any-local | Mọi giao diện mạng cục bộ phù hợp; không giới hạn ở localhost. |
| `new InetSocketAddress((InetAddress) null, 8080)` | Wildcard/any-local | Tương tự constructor chỉ có cổng. |
| `new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080)` | Loopback IPv4 hoặc IPv6 | Chỉ client trên cùng máy có thể kết nối trực tiếp qua loopback. |
| `new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 8080)` | IPv4 loopback | Chỉ lắng nghe tại địa chỉ loopback IPv4. |
| `new InetSocketAddress(InetAddress.getByName("::1"), 8080)` | IPv6 loopback | Chỉ lắng nghe tại địa chỉ loopback IPv6. |
| `new InetSocketAddress("localhost", 8080)` | Hostname cần phân giải | Thường là loopback theo cấu hình máy, nhưng phụ thuộc kết quả phân giải hostname. |
| `new InetSocketAddress(InetAddress.getLocalHost(), 8080)` | Địa chỉ của máy theo cấu hình hostname | Có thể là IP LAN; không đồng nghĩa loopback. |

**Quy tắc thực hành:** nếu muốn giới hạn server vào máy phát triển, dùng `InetAddress.getLoopbackAddress()` hoặc một loopback literal đã chọn rõ. Đừng mặc định constructor chỉ nhận port là an toàn cho local-only.

## 3. Wildcard address và loopback khác nhau như thế nào?

### Wildcard / any-local

Wildcard là địa chỉ đặc biệt thể hiện **không chỉ định một địa chỉ giao diện cụ thể**. Khi dùng làm đích bind, nó yêu cầu hệ điều hành nhận kết nối đến server qua các giao diện cục bộ phù hợp. Biểu diễn thường gặp là:

- IPv4: `0.0.0.0`.
- IPv6: `::` (địa chỉ unspecified).

Không nên hiểu wildcard như một địa chỉ mà client có thể truy cập trực tiếp từ xa. Client thường phải kết nối tới một IP cụ thể của máy server, ví dụ IP LAN; wildcard là chỉ thị cho thao tác bind.

### Loopback

Loopback là giao diện mạng nội bộ của chính host:

- IPv4 loopback: `127.0.0.1` (thuộc dải `127.0.0.0/8`).
- IPv6 loopback: `::1`.

Gói tin gửi đến loopback quay trở lại ngăn xếp mạng của máy cục bộ. Máy khác không thể dùng `127.0.0.1` hoặc `::1` để truy cập server trên máy của bạn; các địa chỉ này luôn chỉ chính máy đang gửi request.

```text
Chỉ máy hiện tại:

Client local ───────► 127.0.0.1:8080 / [::1]:8080
                           │
                           ▼
                    HTTP server

Bind wildcard:

Client local ───────► IP loopback ───────┐
Client trong LAN ───► IP LAN ────────────┼──► HTTP server :8080
Client qua mạng ────► IP phù hợp ────────┘    (nếu định tuyến/firewall cho phép)
```

Sơ đồ chỉ minh họa phạm vi bind. Khả năng kết nối thực tế còn phụ thuộc cấu hình interface, định tuyến, firewall, chính sách mạng và cấu hình socket của hệ điều hành.

## 4. Ví dụ Java: SimpleFileServer chỉ lắng nghe loopback

Ví dụ này dùng `InetAddress.getLoopbackAddress()` để không vô tình bind wildcard. Cổng `0` cho phép hệ điều hành chọn cổng khả dụng; sau khi factory tạo server, `getAddress()` cho biết địa chỉ bind và cổng thực tế. Server vẫn cần gọi `start()` tường minh.

Tạo thư mục `public` và đặt một tệp `hello.txt` vào đó trước khi chạy. Lưu chương trình dưới tên `LoopbackFileServer.java`:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;

import java.io.IOException;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class LoopbackFileServer {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException(
                    "Thư mục public không tồn tại hoặc không đọc được: " + root);
        }

        // Chọn rõ loopback, không dùng new InetSocketAddress(port).
        InetAddress loopback = InetAddress.getLoopbackAddress();
        InetSocketAddress address = new InetSocketAddress(loopback, 0);

        HttpServer server = SimpleFileServer.createFileServer(
                address, root, OutputLevel.INFO);

        // Xác minh địa chỉ/cổng thực tế mà server đã bind.
        InetSocketAddress bound = server.getAddress();
        InetAddress boundIp = bound.getAddress();
        if (boundIp == null || !boundIp.isLoopbackAddress()
                || boundIp.isAnyLocalAddress()) {
            throw new IllegalStateException(
                    "Server không bind vào loopback: " + bound);
        }

        server.start();

        // In URL đúng cú pháp cho IPv4 hoặc IPv6 loopback.
        String host = boundIp.getHostAddress();
        if (boundIp instanceof Inet6Address) {
            host = "[" + host + "]";
        }
        System.out.println("Đang phục vụ thư mục: " + root);
        System.out.println("URL: http://" + host + ":" + bound.getPort() + "/");
        System.out.println("Nhấn Enter để dừng...");

        try {
            System.in.read();
        } finally {
            server.stop(1);
        }
    }
}
```

Biên dịch và chạy trên JDK 18 trở lên:

```bash
javac LoopbackFileServer.java
java LoopbackFileServer
```

Chương trình sẽ in một URL, ví dụ:

```text
URL: http://127.0.0.1:54321/
```

Hoặc nếu JDK chọn IPv6:

```text
URL: http://[0:0:0:0:0:0:0:1]:54321/
```

Dùng đúng URL được in ra để thử:

```bash
curl -i http://127.0.0.1:54321/hello.txt
curl -I http://127.0.0.1:54321/hello.txt
```

Thay địa chỉ và cổng trong lệnh bằng giá trị chương trình in ra. Với IPv6, giữ dấu ngoặc vuông quanh địa chỉ, ví dụ `curl -i "http://[::1]:54321/hello.txt"`. Nhấn Enter ở terminal Java để gọi `server.stop(1)`.

**Vì sao cần in địa chỉ đã bind?** `InetAddress.getLoopbackAddress()` có thể chọn IPv4 hoặc IPv6. Một client cố kết nối tới `127.0.0.1` sẽ không truy cập được socket chỉ bind vào `::1` trong môi trường không ánh xạ hai họ địa chỉ. Dùng literal mà server báo ra giúp tránh nhầm lẫn giữa hai họ.

## 5. Cấu hình địa chỉ theo nhu cầu

### 5.1. Chỉ cho phép máy hiện tại

Đây là lựa chọn nên dùng cho demo, kiểm thử giao diện hoặc chia sẻ tạm thời một thư mục phát triển:

```java
InetSocketAddress address = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 8080);
HttpServer server = SimpleFileServer.createFileServer(
        address, root, OutputLevel.INFO);
server.start();
```

Nếu muốn kết quả nhất quán là IPv4, dùng:

```java
InetSocketAddress address = new InetSocketAddress(
        InetAddress.getByName("127.0.0.1"), 8080);
```

Nếu muốn chỉ IPv6 loopback, thay bằng `InetAddress.getByName("::1")`. Khi cố định một họ địa chỉ, client phải kết nối bằng cùng họ và hệ điều hành cần hỗ trợ loopback tương ứng.

### 5.2. Cho phép thiết bị trong mạng LAN truy cập

Nếu thật sự cần một thiết bị khác trong mạng nội bộ truy cập, hãy bind vào **địa chỉ LAN cụ thể** của máy chủ thay vì mặc định wildcard:

```java
InetAddress lanAddress = InetAddress.getByName("192.168.1.20"); // Ví dụ; thay bằng IP thật
InetSocketAddress address = new InetSocketAddress(lanAddress, 8080);
HttpServer server = SimpleFileServer.createFileServer(
        address, root, OutputLevel.INFO);
server.start();
```

Địa chỉ `192.168.1.20` chỉ là ví dụ. Hãy xác định địa chỉ IPv4/IPv6 đang được gán cho interface cần phục vụ trên máy chủ; nếu địa chỉ thay đổi theo DHCP, cấu hình cần được cập nhật. Firewall cũng cần cho phép kết nối vào cổng đã chọn.

Bind vào IP LAN giới hạn server ở interface/address đó, nhưng **mọi thiết bị có đường mạng tới IP ấy** có thể thử kết nối nếu firewall và chính sách mạng cho phép. Điều này không tự tạo xác thực hoặc phân quyền cho file server.

### 5.3. Khi nào mới dùng wildcard?

Chỉ dùng wildcard khi yêu cầu thực sự là lắng nghe trên mọi interface phù hợp:

```java
// Tương đương ý nghĩa wildcard của constructor chỉ có port:
InetSocketAddress address = new InetSocketAddress(8080);
```

Ví dụ tài liệu JDK về `SimpleFileServer` có thể dùng `new InetSocketAddress(8080)` để rút gọn minh họa. Đó là lựa chọn phù hợp cho ví dụ cần bind mặc định, nhưng người học phải hiểu đây là **wildcard**, không phải loopback. Khi copy vào công cụ phát triển cục bộ, hãy thay bằng địa chỉ loopback nếu không có nhu cầu chia sẻ qua mạng.

## 6. Các nhầm lẫn thường gặp

| Cách viết / giả định | Vấn đề | Cách chọn đúng |
| --- | --- | --- |
| `new InetSocketAddress(8080)` được hiểu là localhost | Constructor chỉ có port dùng wildcard address. | Truyền `InetAddress.getLoopbackAddress()` khi chỉ truy cập cục bộ. |
| `new InetSocketAddress((InetAddress) null, 8080)` | `null` cũng được diễn giải là wildcard. | Không truyền null nếu cần giới hạn interface. |
| `InetAddress.getLocalHost()` được xem là loopback | Địa chỉ local host thường là IP của interface LAN hoặc hostname đã phân giải. | Dùng `getLoopbackAddress()` để lấy loopback. |
| `localhost` luôn là IPv4 | Hostname có thể phân giải sang IPv4 hoặc IPv6 theo resolver/cấu hình máy. | Dùng `InetAddress.getLoopbackAddress()` hoặc literal cụ thể; in địa chỉ server thực tế. |
| Bind `0.0.0.0` rồi dùng URL `http://0.0.0.0:8080` từ client | Wildcard là chỉ thị bind, không phải địa chỉ đích thông thường để client truy cập. | Dùng loopback hoặc IP cụ thể của interface làm URL đích. |
| Firewall đang bật nên wildcard không sao | Firewall có thể chặn một số kết nối, nhưng không đổi phạm vi địa chỉ mà socket bind. | Chọn bind address phù hợp trước, sau đó cấu hình firewall theo nhu cầu. |
| Bind loopback nghĩa là không ai truy cập được | Các tiến trình/người dùng khác trên cùng host vẫn có thể kết nối đến loopback service. | Giới hạn dữ liệu phục vụ; thêm xác thực nếu ứng dụng cần bảo vệ ngay cả truy cập local. |

### Kiểm tra địa chỉ trước khi start

`InetAddress` cung cấp các phương thức kiểm tra hữu ích:

```java
InetAddress ip = address.getAddress();
System.out.println("Address = " + ip.getHostAddress());
System.out.println("Loopback = " + ip.isLoopbackAddress());
System.out.println("Wildcard = " + ip.isAnyLocalAddress());
```

Với cấu hình local-only, kỳ vọng `isLoopbackAddress()` là `true` và `isAnyLocalAddress()` là `false`. Có thể kiểm tra lại sau khi factory bind:

```java
InetSocketAddress bound = server.getAddress();
InetAddress actual = bound.getAddress();
if (actual == null || !actual.isLoopbackAddress()
        || actual.isAnyLocalAddress()) {
    throw new IllegalStateException("Unexpected bind address: " + bound);
}
```

Kiểm tra này giúp phát hiện cấu hình sai sớm. Nó không thay thế việc chọn đúng địa chỉ ngay từ đầu, cũng không thay thế kiểm tra firewall hoặc quyền truy cập nội dung.

## 7. Môi trường container và máy ảo

Khái niệm loopback luôn gắn với **network namespace/host đang chạy tiến trình**:

- Nếu Java chạy trực tiếp trên laptop, `127.0.0.1` là loopback của laptop.
- Nếu Java chạy trong Docker container với network namespace riêng, `127.0.0.1` là loopback của **container**, không phải địa chỉ loopback của host.
- Nếu Java chạy trong máy ảo, loopback là loopback bên trong máy ảo.

Vì vậy, ứng dụng bind loopback trong container có thể không được truy cập từ host qua cơ chế publish port thông thường, tùy cấu hình container/network. Nếu cần host hoặc container khác truy cập, phải thiết kế bind address và port mapping rõ ràng. Đừng đổi sang wildcard một cách máy móc khi gặp lỗi kết nối; hãy xác định client nằm trong network namespace nào và địa chỉ cần phục vụ.

## 8. Bài tập tự kiểm tra

1. `new InetSocketAddress(8080)` tạo wildcard hay loopback? Javadoc mô tả constructor này thế nào?
2. Vì sao `new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080)` phù hợp cho file server chỉ phục vụ trên máy cá nhân?
3. `InetAddress.getLoopbackAddress()` có luôn trả `127.0.0.1` không? Khi nào client cần dùng URL IPv6 có dấu ngoặc vuông?
4. Khác biệt giữa `InetAddress.getLocalHost()` và `InetAddress.getLoopbackAddress()` là gì?
5. Tại sao bật firewall không thay thế việc bind đúng địa chỉ?
6. Nếu muốn một điện thoại trong LAN truy cập máy chủ, nên bind loopback, wildcard hay IP LAN cụ thể? Cần kiểm tra thêm điều gì?
7. `InetSocketAddress((InetAddress) null, port)` có ý nghĩa gì?
8. Vì sao loopback không đồng nghĩa với xác thực người dùng trên cùng máy?

**Bài thực hành:** chạy ví dụ `LoopbackFileServer` với cổng `0`; dùng URL in ra để truy cập `hello.txt`. Sau đó thay địa chỉ bằng `new InetSocketAddress(8080)`, in `server.getAddress()`, quan sát `isAnyLocalAddress()` và so sánh phạm vi bind. Khôi phục loopback sau khi thử. Nếu muốn kiểm tra từ thiết bị LAN, chỉ thực hiện trong mạng thử nghiệm được kiểm soát và dùng IP LAN cụ thể.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `InetSocketAddress`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetSocketAddress.html): các constructor, wildcard address, port `0`, hostname resolution và `getAddress()`.
- [Oracle JDK 27 — `InetAddress`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): wildcard/any-local, loopback, `getLoopbackAddress()`, `isAnyLocalAddress()` và `isLoopbackAddress()`.
- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): server được bind vào địa chỉ truyền vào, factory method và phạm vi sử dụng testing/development/debugging.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): địa chỉ bind, `getAddress()`, `start()` và `stop(delay)`.
