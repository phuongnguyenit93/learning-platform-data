# DatagramSocket.joinGroup, leaveGroup và NetworkInterface trong Java 17

UDP multicast cho phép một nguồn gửi datagram đến một địa chỉ nhóm; các máy hoặc tiến trình đã tham gia nhóm trên mạng tương ứng có thể nhận những datagram đó. Đây là mô hình gửi một-nhiều hữu ích cho discovery trong mạng nội bộ, truyền dữ liệu trạng thái, thông báo hoặc một số hệ thống phân phối dữ liệu thời gian thực.

Java 17 bổ sung trực tiếp hai phương thức multicast vào `DatagramSocket`:

- `joinGroup(SocketAddress mcastaddr, NetworkInterface netIf)`: tham gia một nhóm multicast trên interface mạng cục bộ được chỉ định.
- `leaveGroup(SocketAddress mcastaddr, NetworkInterface netIf)`: rời nhóm multicast trên interface đó.

Hai phương thức này có từ Java 17. Vì vậy, trong Java 17 có thể dùng `DatagramSocket` trực tiếp cho multicast, không bắt buộc phải tạo `MulticastSocket` chỉ để gọi API tham gia nhóm. `NetworkInterface` xác định **card/interface mạng cục bộ** mà socket dùng để nhận multicast; nó không phải địa chỉ nhóm và cũng không phải cổng UDP. [Java 17 DatagramSocket API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html) và [NetworkInterface API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html) mô tả các hợp đồng này.

Để sử dụng đúng, cần hiểu đồng thời ba thành phần:

1. **Multicast group address**: địa chỉ IP đại diện cho nhóm người nhận.
2. **DatagramSocket**: socket UDP được bind vào cổng cục bộ để gửi hoặc nhận datagram.
3. **NetworkInterface**: interface trên máy cục bộ dùng để tham gia nhóm hoặc gửi datagram multicast ra mạng.

`joinGroup` chỉ tạo membership trên mạng tương ứng. Nó không tự bảo đảm router, switch, firewall hoặc hệ điều hành sẽ chuyển datagram đến ứng dụng. Mạng bên dưới phải hỗ trợ multicast và được cấu hình phù hợp.

## 1. Phân biệt unicast, broadcast và multicast

UDP gửi từng datagram độc lập. Địa chỉ đích xác định cách gói tin được phân phối:

| Kiểu gửi | Ý nghĩa | Địa chỉ đích |
| --- | --- | --- |
| Unicast | Một nguồn gửi đến một địa chỉ nhận cụ thể | Địa chỉ IP của một host/interface |
| Broadcast | Một nguồn gửi đến các host trong phạm vi broadcast của mạng | Địa chỉ broadcast IPv4 |
| Multicast | Một nguồn gửi đến một nhóm nhận đã tham gia | Địa chỉ multicast group |

Với multicast, ứng dụng gửi một datagram đến group address. Mạng có thể nhân bản và chuyển gói đến các nhánh có thành viên nhóm. Ứng dụng nhận cần tham gia group trên interface phù hợp trước khi nhận dữ liệu.

### Phạm vi địa chỉ multicast

Các dải địa chỉ thường gặp:

- **IPv4 multicast**: `224.0.0.0/4`, tức từ `224.0.0.0` đến `239.255.255.255`.
- **IPv6 multicast**: các địa chỉ bắt đầu bằng `ff00::/8`.

Ví dụ `239.1.2.3` là một địa chỉ IPv4 multicast trong dải administratively scoped. Ví dụ này chỉ dùng minh họa; khi triển khai, chọn group address theo quy hoạch địa chỉ của mạng và tránh các dải được dành riêng cho giao thức hoặc mục đích đặc biệt.

Có thể kiểm tra một địa chỉ có phải multicast hay không bằng `InetAddress.isMulticastAddress()`:

~~~java
InetAddress address = InetAddress.getByName("239.1.2.3");

if (!address.isMulticastAddress()) {
    throw new IllegalArgumentException("Address is not multicast");
}
~~~

Không dùng địa chỉ IP của máy nhận làm group address. Group address là địa chỉ nhóm; `NetworkInterface` là interface cục bộ mà máy dùng để tham gia nhóm đó.

### Multicast vẫn là UDP

Multicast datagram có các đặc tính của UDP:

- Không có kết nối đầu cuối như TCP.
- Không bảo đảm datagram sẽ đến nơi.
- Không bảo đảm thứ tự nhận.
- Không tự truyền lại gói bị mất.
- Không tự loại bỏ bản sao trùng lặp ở tầng ứng dụng.
- Datagram quá lớn có thể bị phân mảnh ở IP hoặc bị mất do giới hạn MTU/mạng.

Nếu ứng dụng cần thứ tự, phát hiện mất gói, retry, xác thực nguồn hoặc đồng bộ trạng thái, phải thiết kế các cơ chế đó ở tầng ứng dụng hoặc dùng giao thức khác phù hợp.

## 2. DatagramSocket multicast API có từ Java 17

Trước Java 17, các API multicast quen thuộc chủ yếu được gọi qua `MulticastSocket`, một lớp con của `DatagramSocket`. Từ Java 17, `DatagramSocket` có trực tiếp các phương thức:

~~~java
public void joinGroup(
        SocketAddress mcastaddr,
        NetworkInterface netIf) throws IOException;

public void leaveGroup(
        SocketAddress mcastaddr,
        NetworkInterface netIf) throws IOException;
~~~

Hai tham số có ý nghĩa:

| Tham số | Vai trò |
| --- | --- |
| `mcastaddr` | Địa chỉ multicast group. API nhận `SocketAddress`; implementation mặc định hỗ trợ `InetSocketAddress`. Phần port của địa chỉ này bị bỏ qua khi tham gia nhóm. |
| `netIf` | Interface mạng cục bộ nhận multicast. Có thể truyền `null` để dùng interface được cấu hình cho multicast outgoing; nếu không có interface đó, hành vi không được xác định và thao tác có thể thất bại. |

Với implementation mặc định, `mcastaddr` phải là `InetSocketAddress`; port trong đối tượng này không quyết định cổng nhận. **Cổng nhận là cổng mà DatagramSocket đã bind**. Vì vậy, thường tạo địa chỉ nhóm với port `0` để thể hiện rằng chỉ địa chỉ IP nhóm có ý nghĩa cho thao tác join/leave.

Ví dụ:

~~~java
InetAddress groupAddress = InetAddress.getByName("239.1.2.3");
InetSocketAddress group = new InetSocketAddress(groupAddress, 0);
NetworkInterface networkInterface =
        NetworkInterface.getByName("eth0");

socket.joinGroup(group, networkInterface);
// ...
socket.leaveGroup(group, networkInterface);
~~~

Tên `eth0` chỉ là ví dụ trên một số hệ Linux. Tên interface thực tế khác nhau giữa Windows, Linux, macOS, máy ảo và container. Không hard-code một tên interface rồi giả định nó có trên mọi máy.

### Có thể tham gia nhiều nhóm hoặc nhiều interface

Một DatagramSocket có thể gọi `joinGroup` nhiều lần để tham gia nhiều multicast group khác nhau, hoặc tham gia cùng group trên nhiều mạng/interface. Khi rời nhóm, truyền lại đúng group và interface tương ứng đã dùng lúc join.

Nếu socket đã là thành viên của group trên interface đó, lời gọi join lặp có thể ném `IOException`. Nếu socket không phải thành viên của group/interface được yêu cầu, `leaveGroup` có thể ném `IOException`. Vì vậy, ứng dụng nên quản lý rõ các membership đã tạo thay vì gọi join/leave tùy tiện.

## 3. NetworkInterface đại diện cho điều gì?

`java.net.NetworkInterface` mô tả một interface mạng của máy cục bộ, thường là Ethernet, Wi-Fi, loopback, interface ảo hoặc interface con. Một interface có thể có nhiều địa chỉ IP được gán.

Các thông tin thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên hệ thống của interface, ví dụ `eth0`, `en0` hoặc tên do hệ điều hành đặt |
| `getDisplayName()` | Tên hiển thị dễ đọc |
| `getIndex()` | Chỉ số interface do hệ thống cấp |
| `getInetAddresses()` | Các địa chỉ IP được gán cho interface |
| `inetAddresses()` | Stream các địa chỉ IP của interface |
| `isUp()` | Interface có đang hoạt động hay không |
| `isLoopback()` | Có phải loopback interface hay không |
| `isVirtual()` | Có phải interface ảo/subinterface hay không |
| `supportsMulticast()` | Interface có hỗ trợ multicast hay không |
| `getByName(name)` | Tìm interface theo tên hệ thống |
| `getByIndex(index)` | Tìm interface theo index |
| `getByInetAddress(address)` | Tìm interface chứa địa chỉ IP được chỉ định |
| `getNetworkInterfaces()` | Liệt kê các interface trên máy |

`isUp()` và `supportsMulticast()` có thể ném `SocketException`. Việc interface tồn tại không đồng nghĩa interface đang hoạt động hoặc có hỗ trợ multicast.

### Liệt kê interface trên máy

~~~java
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Collections;

public class ListNetworkInterfaces {
    public static void main(String[] args) throws SocketException {
        for (NetworkInterface networkInterface
                : Collections.list(NetworkInterface.getNetworkInterfaces())) {

            System.out.println("Name: " + networkInterface.getName());
            System.out.println("Display: " + networkInterface.getDisplayName());
            System.out.println("Up: " + networkInterface.isUp());
            System.out.println("Loopback: " + networkInterface.isLoopback());
            System.out.println("Multicast: "
                    + networkInterface.supportsMulticast());

            System.out.println("Addresses:");
            for (var address
                    : Collections.list(networkInterface.getInetAddresses())) {
                System.out.println("  " + address.getHostAddress());
            }
            System.out.println();
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 ListNetworkInterfaces.java
java ListNetworkInterfaces
~~~

Kết quả phụ thuộc máy chạy. Một máy có thể hiển thị Ethernet, Wi-Fi, VPN, loopback, adapter ảo của hypervisor hoặc interface của container. Interface loopback thường chỉ liên lạc nội bộ host; nó không chứng minh multicast có thể đi qua mạng vật lý.

### Chọn interface có thể dùng multicast

Một hàm tiện ích có thể kiểm tra tên và capability:

~~~java
import java.net.NetworkInterface;
import java.net.SocketException;

static NetworkInterface requireMulticastInterface(String name)
        throws SocketException {

    NetworkInterface networkInterface =
            NetworkInterface.getByName(name);

    if (networkInterface == null) {
        throw new IllegalArgumentException(
                "No network interface named " + name);
    }
    if (!networkInterface.isUp()) {
        throw new IllegalStateException(
                "Network interface is down: " + name);
    }
    if (!networkInterface.supportsMulticast()) {
        throw new IllegalStateException(
                "Network interface does not support multicast: " + name);
    }

    return networkInterface;
}
~~~

Đây là kiểm tra ban đầu ở phía Java. `supportsMulticast()` trả lời capability của interface theo hệ điều hành; nó không bảo đảm switch, router, firewall hoặc mạng thực tế đang chuyển tiếp group traffic.

### Chọn interface theo địa chỉ IP

Nếu cấu hình ứng dụng biết địa chỉ IP cục bộ cần dùng, có thể tìm interface:

~~~java
InetAddress localAddress = InetAddress.getByName("192.168.1.20");
NetworkInterface networkInterface =
        NetworkInterface.getByInetAddress(localAddress);

if (networkInterface == null) {
    throw new IllegalArgumentException(
            "No interface owns " + localAddress);
}
~~~

Nếu một địa chỉ được gán trên nhiều interface, API không xác định interface nào sẽ được trả về. Khi cần chọn chính xác, ưu tiên tên hoặc index được cấu hình rõ ràng và kiểm tra lại trạng thái.

## 4. Chuẩn bị DatagramSocket để nhận multicast

Để nhận multicast, socket cần được bind vào cổng UDP cục bộ trước khi tham gia group. Java 17 API note khuyến nghị:

1. Tạo DatagramSocket ở trạng thái **unbound**.
2. Bật `SO_REUSEADDR` trước khi bind nếu muốn hỗ trợ nhiều socket bind cùng địa chỉ/cổng để nhận multicast.
3. Bind vào wildcard address trên cổng nhận.
4. Gọi `joinGroup(group, networkInterface)`.

Ví dụ:

~~~java
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;

int port = 5000;
NetworkInterface networkInterface =
        NetworkInterface.getByName("eth0");

DatagramSocket socket = new DatagramSocket(null);
socket.setReuseAddress(true);
socket.bind(new InetSocketAddress(port));

socket.joinGroup(
        new InetSocketAddress(
                InetAddress.getByName("239.1.2.3"), 0),
        networkInterface);
~~~

`new DatagramSocket(null)` tạo socket chưa bind. `setReuseAddress(true)` phải được gọi **trước bind** nếu cần bật `SO_REUSEADDR` cho mục tiêu này. `new InetSocketAddress(port)` bind vào wildcard local address, giúp socket nhận datagram trên các interface phù hợp theo cấu hình multicast.

### Vì sao cần bật SO_REUSEADDR trước bind?

Một số ứng dụng có nhiều listener cùng tham gia một group và cùng bind một UDP port. `SO_REUSEADDR` cho phép hệ điều hành hỗ trợ bind trùng địa chỉ socket trong những trường hợp nền tảng cho phép.

Đối với `DatagramSocket`, `SO_REUSEADDR` mặc định không bật. Nếu socket được tạo và bind ngay bằng `new DatagramSocket(port)`, lúc đó đã quá muộn để thiết lập tùy chọn trước bind theo yêu cầu. Vì vậy, tạo socket chưa bind rồi bật reuse trước.

Hỗ trợ và hành vi cụ thể của `SO_REUSEADDR` phụ thuộc nền tảng. Không nên giả định mọi hệ điều hành sẽ phân phối multicast giữa các socket trùng port giống nhau. Hãy kiểm tra trên môi trường triển khai.

### Vì sao nên bind wildcard?

Java 17 API note khuyến nghị bind socket multicast receiver vào wildcard address trước khi join. Nếu bind socket vào một địa chỉ cụ thể của một interface, khả năng nhận multicast có thể phụ thuộc implementation. Khi mục tiêu là chọn interface nhận, truyền `NetworkInterface` vào `joinGroup` để biểu đạt ý định đó.

## 5. Tham gia nhóm bằng joinGroup

Một receiver cần group address và interface phù hợp:

~~~java
InetAddress groupAddress = InetAddress.getByName("239.1.2.3");
if (!groupAddress.isMulticastAddress()) {
    throw new IllegalArgumentException("Not a multicast address");
}

InetSocketAddress group =
        new InetSocketAddress(groupAddress, 0);

NetworkInterface networkInterface =
        requireMulticastInterface("eth0");

socket.joinGroup(group, networkInterface);
~~~

Khi join thành công, socket đã đăng ký nhận datagram thuộc group trên interface được chỉ định, theo khả năng và chính sách của nền tảng.

### Truyền null cho NetworkInterface có được không?

Có thể truyền `null`. Theo API, `null` yêu cầu trì hoãn việc chọn interface tới interface được cấu hình cho multicast outgoing trên socket. Nếu chưa đặt interface outgoing, hành vi không xác định: hệ thống có thể tự chọn một interface hoặc ném `SocketException`.

Với ứng dụng cần hoạt động ổn định trên máy có nhiều NIC, VPN hoặc Wi-Fi/Ethernet cùng lúc, nên chọn `NetworkInterface` tường minh. Điều này giúp tránh phụ thuộc vào route mặc định của hệ điều hành.

### Join nhiều nhóm

Ví dụ socket tham gia hai group trên cùng interface:

~~~java
InetSocketAddress groupA =
        new InetSocketAddress(
                InetAddress.getByName("239.1.2.3"), 0);
InetSocketAddress groupB =
        new InetSocketAddress(
                InetAddress.getByName("239.1.2.4"), 0);

socket.joinGroup(groupA, networkInterface);
socket.joinGroup(groupB, networkInterface);
~~~

Nếu cần cùng group trên hai interface khác nhau, có thể gọi `joinGroup` với cùng group address nhưng interface khác. Khi rời nhóm, phải dùng đúng cặp group/interface tương ứng.

## 6. Nhận DatagramPacket sau khi join

Sau khi join group, dùng `receive(DatagramPacket)` như socket UDP thông thường:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

byte[] buffer = new byte[2048];
DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

socket.setSoTimeout(2000);

try {
    socket.receive(packet);
    String message = new String(
            packet.getData(),
            packet.getOffset(),
            packet.getLength(),
            StandardCharsets.UTF_8);

    System.out.println("From: " + packet.getAddress()
            + ":" + packet.getPort());
    System.out.println("Message: " + message);
} catch (SocketTimeoutException ex) {
    System.out.println("No packet received before timeout");
}
~~~

`receive()` là thao tác blocking: thread gọi chờ cho tới khi có datagram hoặc timeout. `setSoTimeout()` đặt thời gian chờ nhận tính bằng milliseconds; giá trị `0` có nghĩa chờ vô hạn.

### Dùng lại DatagramPacket trong vòng lặp

Khi tái sử dụng packet, nhớ khôi phục độ dài buffer trước lần nhận kế tiếp:

~~~java
byte[] buffer = new byte[2048];
DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

while (!Thread.currentThread().isInterrupted()) {
    packet.setLength(buffer.length);
    socket.receive(packet);

    String message = new String(
            packet.getData(),
            packet.getOffset(),
            packet.getLength(),
            StandardCharsets.UTF_8);

    handleMessage(message);
}
~~~

Sau một lần receive, `packet.getLength()` là độ dài datagram thực nhận. Nếu không gọi `setLength(buffer.length)` trước lần tiếp theo, packet có thể giữ giới hạn ngắn hơn và các datagram sau bị cắt theo giới hạn đó.

### Kích thước buffer và datagram bị cắt

Nếu datagram lớn hơn vùng buffer có thể chứa, dữ liệu dư bị cắt. `getLength()` cho biết số byte thực tế được đặt trong packet sau nhận; nó không thể khôi phục phần đã bị cắt.

Không nên gửi payload lớn tùy tiện qua UDP. Kích thước datagram an toàn phụ thuộc MTU, header IP/UDP, mạng và đường đi. Nếu cần truyền dữ liệu lớn, hãy phân mảnh ở tầng ứng dụng có sequence number/reassembly, hoặc cân nhắc TCP/HTTP hay giao thức truyền tải phù hợp hơn.

## 7. Rời nhóm bằng leaveGroup

Khi không còn cần nhận multicast, gọi:

~~~java
socket.leaveGroup(group, networkInterface);
~~~

`group` nên chứa cùng địa chỉ multicast đã dùng khi join và `networkInterface` phải là interface tương ứng. Port trong `InetSocketAddress` bị bỏ qua bởi implementation mặc định, nhưng nên dùng lại cùng đối tượng/giá trị group để tránh nhầm lẫn.

Nếu socket không phải thành viên của group trên interface được chỉ định, `leaveGroup` có thể ném `IOException`. Vì vậy, giữ thông tin membership đã đăng ký và chỉ leave các membership thực sự đã join thành công.

### Quản lý lifecycle bằng try/finally

Một receiver có thể có cấu trúc:

~~~java
InetSocketAddress group =
        new InetSocketAddress(
                InetAddress.getByName("239.1.2.3"), 0);

try (DatagramSocket socket = new DatagramSocket(null)) {
    socket.setReuseAddress(true);
    socket.bind(new InetSocketAddress(5000));
    socket.joinGroup(group, networkInterface);

    try {
        receiveMessages(socket);
    } finally {
        socket.leaveGroup(group, networkInterface);
    }
}
~~~

try-with-resources bảo đảm socket được đóng. finally bảo đảm ứng dụng chủ động rời membership khi luồng xử lý kết thúc bình thường hoặc do exception. Đóng socket cũng giải phóng tài nguyên và membership gắn với socket; leaveGroup tường minh giúp vòng đời group được thể hiện rõ.

Nếu receiver chạy lâu dài trong một service, cần có cơ chế dừng: đặt cờ shutdown, dùng timeout để vòng lặp kiểm tra cờ hoặc đóng socket để giải phóng thread đang chờ receive. Đừng giữ một thread chờ vô hạn mà không có đường dừng ứng dụng.

## 8. Ví dụ hoàn chỉnh: receiver multicast

Chương trình sau liệt kê interface, chọn interface theo tên cấu hình, kiểm tra capability, bind socket, join group, nhận một số datagram và rời group.

Lưu thành `MulticastReceiver.java`:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class MulticastReceiver {

    private static NetworkInterface findInterface(String name)
            throws SocketException {
        NetworkInterface networkInterface =
                NetworkInterface.getByName(name);

        if (networkInterface == null) {
            throw new IllegalArgumentException(
                    "Unknown network interface: " + name);
        }
        if (!networkInterface.isUp()) {
            throw new IllegalStateException(
                    "Interface is down: " + name);
        }
        if (!networkInterface.supportsMulticast()) {
            throw new IllegalStateException(
                    "Interface does not support multicast: " + name);
        }
        return networkInterface;
    }

    public static void main(String[] args) throws Exception {
        String interfaceName =
                args.length > 0 ? args[0] : "eth0";
        int port = 5000;
        int maxPackets = 5;

        InetAddress groupAddress =
                InetAddress.getByName("239.1.2.3");
        if (!groupAddress.isMulticastAddress()) {
            throw new IllegalArgumentException(
                    "Invalid multicast group: " + groupAddress);
        }

        NetworkInterface networkInterface =
                findInterface(interfaceName);
        InetSocketAddress group =
                new InetSocketAddress(groupAddress, 0);

        try (DatagramSocket socket = new DatagramSocket(null)) {
            // Với receiver multicast, bật reuse trước khi bind.
            socket.setReuseAddress(true);
            socket.bind(new InetSocketAddress(port));
            socket.setSoTimeout(5000);

            socket.joinGroup(group, networkInterface);
            System.out.println("Joined " + groupAddress
                    + " on " + networkInterface.getName()
                    + ", UDP port " + port);

            try {
                byte[] buffer = new byte[2048];
                DatagramPacket packet =
                        new DatagramPacket(buffer, buffer.length);

                for (int i = 0; i < maxPackets; i++) {
                    packet.setLength(buffer.length);
                    try {
                        socket.receive(packet);
                    } catch (SocketTimeoutException ex) {
                        System.out.println("Receive timed out");
                        break;
                    }

                    String message = new String(
                            packet.getData(),
                            packet.getOffset(),
                            packet.getLength(),
                            StandardCharsets.UTF_8);

                    System.out.println("Received from "
                            + packet.getAddress() + ":"
                            + packet.getPort() + " -> " + message);
                }
            } finally {
                socket.leaveGroup(group, networkInterface);
                System.out.println("Left multicast group");
            }
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 MulticastReceiver.java
~~~

Chạy với tên interface thật trên máy:

~~~bash
java MulticastReceiver eth0
~~~

Thay `eth0` bằng tên được liệt kê từ `NetworkInterface.getNetworkInterfaces()`. Nếu máy dùng Wi-Fi hoặc Windows, tên interface có thể khác hoàn toàn.

Receiver này đợi tối đa năm packet hoặc timeout sau năm giây. Trong ứng dụng thật, vòng lặp thường chạy cho tới khi service dừng và cần cơ chế shutdown rõ ràng.

## 9. Gửi multicast và chọn interface outgoing

Không cần join group để gửi multicast. Sender chỉ cần tạo DatagramPacket có đích là multicast group. Tuy nhiên, nếu máy có nhiều interface, cần xác định interface gửi.

`DatagramSocket` hỗ trợ socket option:

- `StandardSocketOptions.IP_MULTICAST_IF`: interface dùng cho datagram multicast outgoing.
- `StandardSocketOptions.IP_MULTICAST_TTL`: time-to-live của multicast datagram IPv4.
- `StandardSocketOptions.IP_MULTICAST_LOOP`: bật/tắt multicast loopback theo hỗ trợ của nền tảng.

Ví dụ sender:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.StandardSocketOptions;
import java.nio.charset.StandardCharsets;

public class MulticastSender {
    public static void main(String[] args) throws Exception {
        NetworkInterface networkInterface =
                NetworkInterface.getByName("eth0");
        if (networkInterface == null
                || !networkInterface.isUp()
                || !networkInterface.supportsMulticast()) {
            throw new IllegalStateException(
                    "Multicast interface is unavailable");
        }

        InetAddress group =
                InetAddress.getByName("239.1.2.3");
        int port = 5000;

        byte[] payload =
                "Hello multicast".getBytes(StandardCharsets.UTF_8);
        InetSocketAddress destination =
                new InetSocketAddress(group, port);

        try (DatagramSocket socket =
                     new DatagramSocket(new InetSocketAddress(0))) {
            socket.setOption(
                    StandardSocketOptions.IP_MULTICAST_IF,
                    networkInterface);
            socket.setOption(
                    StandardSocketOptions.IP_MULTICAST_TTL,
                    1);

            DatagramPacket packet =
                    new DatagramPacket(
                            payload, payload.length, destination);
            socket.send(packet);
        }
    }
}
~~~

`IP_MULTICAST_IF` xác định interface gửi ra. TTL giới hạn phạm vi chuyển tiếp của gói multicast IPv4; ví dụ TTL 1 thường giới hạn trong link cục bộ vì router không chuyển tiếp gói có TTL đã hết. Đây không phải cơ chế xác thực hoặc mã hóa.

### IP_MULTICAST_LOOP

Tùy chọn loopback điều khiển việc multicast datagram gửi ra có được loop back để các socket trên cùng host nhận hay không, theo hỗ trợ của hệ điều hành:

~~~java
socket.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
~~~

Không nên dựa vào loopback để chứng minh mạng vật lý hoạt động. Kiểm thử sender/receiver trên cùng máy chỉ kiểm tra một phần đường đi; vẫn cần thử giữa các máy trên interface và mạng mục tiêu.

## 10. Phân biệt interface nhận và interface gửi

Hai thao tác liên quan nhưng không nên nhầm:

| Nhu cầu | API |
| --- | --- |
| Chọn interface cục bộ để tham gia nhóm và nhận multicast | `socket.joinGroup(group, networkInterface)` |
| Chọn interface cục bộ để gửi multicast | `socket.setOption(StandardSocketOptions.IP_MULTICAST_IF, networkInterface)` |

`joinGroup` nhận interface trực tiếp làm tham số. Với sender, cấu hình socket option `IP_MULTICAST_IF`. Một socket có thể vừa gửi vừa nhận, nhưng thường nên thiết kế vai trò và lifecycle rõ ràng để dễ quản lý.

Nếu truyền `null` cho tham số `netIf` của joinGroup, API trì hoãn chọn interface tới interface outgoing đã cấu hình; nếu chưa cấu hình, hệ thống có thể tự chọn hoặc thất bại. Chọn tường minh là cách dễ dự đoán hơn trên máy nhiều interface.

## 11. Ví dụ sender và receiver chạy cùng một mạng

Quy trình thử nghiệm:

1. Trên máy nhận, liệt kê interface và chọn interface đang kết nối mạng LAN, có `isUp()` và `supportsMulticast()` đều true.
2. Chạy receiver để bind UDP port 5000 và join group `239.1.2.3`.
3. Trên máy gửi, chọn interface nối vào cùng mạng multicast.
4. Gửi datagram đến group `239.1.2.3:5000`.
5. Quan sát log receiver.
6. Dừng receiver và xác nhận nó leave group/close socket.

Sơ đồ:

~~~text
                 Multicast group 239.1.2.3:5000
                              ^
                              |
                    LAN / multicast network
                       /             \
                      /               \
             Sender host             Receiver host
             interface A             interface B
                 |                       |
        DatagramSocket.send()    DatagramSocket.joinGroup()
                 |                       |
                 +---- UDP datagram -----+
~~~

Nếu sender và receiver ở các VLAN/subnet khác nhau, mạng phải có cấu hình multicast routing tương ứng. IGMP (IPv4) hoặc MLD (IPv6), switch snooping và router policy có thể ảnh hưởng việc chuyển tiếp. Java API chỉ yêu cầu hệ điều hành tham gia group; nó không tự cấu hình hạ tầng mạng.

## 12. Lỗi và ngoại lệ cần xử lý

| Trường hợp | Có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Group address không phải multicast | `IOException` khi join/leave hoặc validation thất bại | Kiểm tra `InetAddress.isMulticastAddress()` trước |
| `mcastaddr` null hoặc kiểu SocketAddress không hỗ trợ | `IllegalArgumentException` | Dùng `InetSocketAddress` có địa chỉ multicast |
| Interface name không tồn tại | `NetworkInterface.getByName()` trả null | Liệt kê interface và lấy tên cấu hình đúng |
| Interface không up hoặc không hỗ trợ multicast | Join có thể thất bại hoặc không nhận được packet | Kiểm tra `isUp()` và `supportsMulticast()` |
| Join cùng group/interface lặp lại | `IOException` | Quản lý membership và tránh join trùng |
| Leave group chưa join | `IOException` | Chỉ leave membership đã đăng ký |
| Port đã được tiến trình khác bind | `BindException`/`SocketException` | Kiểm tra port và SO_REUSEADDR trước bind |
| Firewall chặn UDP hoặc multicast | Không nhận được packet dù join thành công | Kiểm tra firewall, policy và network path |
| Chọn nhầm interface | Join/send thành công nhưng không thấy dữ liệu | Kiểm tra địa chỉ IP và route của interface |
| Datagram lớn hơn buffer | Packet bị cắt | Tăng buffer hợp lý hoặc thiết kế payload/chunk |
| Receive chờ vô hạn | Thread khó dừng | Dùng `setSoTimeout` hoặc đóng socket khi shutdown |
| Mạng không hỗ trợ multicast | Không nhận được traffic giữa các host | Dùng mạng có multicast hoặc chọn giao thức khác |

### Join thành công không có nghĩa đã nhận được dữ liệu

`joinGroup` có thể thành công ở tầng socket nhưng ứng dụng vẫn không nhận packet vì:

- Sender gửi sang interface khác.
- Sender dùng group hoặc port khác.
- Firewall chặn UDP multicast.
- Switch không chuyển tiếp multicast đến cổng receiver.
- Router không có cấu hình multicast routing giữa các subnet.
- Sender chưa thực sự gửi datagram hoặc datagram bị mất.
- Receiver bind sai port hoặc buffer/packet handling sai.

Khi debug, xác minh theo từng tầng: group IP, port, interface, bind, join, send, firewall và hạ tầng mạng. Đừng coi việc join không ném exception là bằng chứng end-to-end.

## 13. So sánh DatagramSocket và MulticastSocket

`MulticastSocket` vẫn tồn tại trong Java 17 và là subclass của `DatagramSocket`. Trước Java 17, nó là API quen thuộc để join/leave multicast. Từ Java 17, `DatagramSocket` có trực tiếp `joinGroup(SocketAddress, NetworkInterface)` và `leaveGroup(...)`.

Một khác biệt cấu hình cần nhớ:

- Khi tạo `DatagramSocket`, `SO_REUSEADDR` mặc định tắt.
- `MulticastSocket` có hành vi constructor riêng và thường bật reuse address mặc định.
- Với `DatagramSocket` được dùng làm receiver multicast, API note khuyến nghị cân nhắc bật `setReuseAddress(true)` trước khi bind.

Không cần chuyển một ứng dụng đang dùng `MulticastSocket` ổn định chỉ vì có API mới. Nhưng với code Java 17 mới, có thể dùng trực tiếp `DatagramSocket` và cấu hình socket options một cách tường minh.

Không nhầm các API multicast hiện hành với những accessor cũ của `MulticastSocket` dựa trên `InetAddress` đơn lẻ. Ví dụ `getInterface()` và `setInterface(InetAddress)` đã deprecated từ Java 14 vì địa chỉ IP không nhận diện duy nhất một network interface. Khi cần chọn interface, dùng `NetworkInterface` và socket option/API tương ứng.

## 14. Khi nào nên dùng DatagramChannel thay cho DatagramSocket?

Java NIO có `DatagramChannel`, triển khai `MulticastChannel`. API này phù hợp khi ứng dụng cần:

- Non-blocking I/O.
- Tích hợp với `Selector`.
- Source-specific multicast.
- Quản lý membership bằng `MembershipKey`.

Ví dụ API ở mức khái quát:

~~~java
DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET);
channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
channel.bind(new InetSocketAddress(5000));

MembershipKey membership =
        channel.join(groupAddress, networkInterface);

// Khi không còn cần membership:
membership.drop();
~~~

Đây là API khác với `DatagramSocket.joinGroup`. `MembershipKey.drop()` rời membership đã tạo. Với ứng dụng cần selector/non-blocking hoặc source-specific multicast, DatagramChannel có thể phù hợp hơn. Với ứng dụng UDP đơn giản dùng receive/send blocking, DatagramSocket có API trực tiếp và dễ hiểu.

Không dùng DatagramChannel chỉ vì nó mới hơn nếu ứng dụng không cần các đặc tính NIO. Hãy chọn theo mô hình I/O, khả năng kiểm soát và yêu cầu thực tế.

## 15. Kiểm thử và triển khai

### Unit test

Các phần có thể kiểm thử không cần mạng multicast thật:

- Kiểm tra địa chỉ bằng `isMulticastAddress()`.
- Kiểm tra cấu hình group và port.
- Kiểm tra việc xử lý payload, sender address, packet length.
- Kiểm tra lifecycle logic qua một lớp adapter/interface được mock.
- Kiểm tra xử lý timeout và lỗi theo hợp đồng.

Không nên viết unit test phụ thuộc một tên interface như `eth0`, vì môi trường CI có thể không có interface đó.

### Integration test

Multicast cần kiểm thử trên mạng có cấu hình thực:

- Chọn interface đang up và hỗ trợ multicast.
- Chạy sender/receiver trên cùng host hoặc hai host trong LAN.
- Xác minh group, port, interface và firewall.
- Kiểm tra trường hợp join/leave, timeout, packet loss và datagram bị cắt.
- Thử trên các hệ điều hành và network adapter mà ứng dụng hỗ trợ.

Một test chạy trên loopback không chứng minh multicast hoạt động trên Wi-Fi, Ethernet hoặc qua router. Hạ tầng mạng là một phần của điều kiện kiểm thử.

### Triển khai trong container hoặc cloud

Container, VM, VPN và cloud network có thể giới hạn multicast hoặc không hỗ trợ chuyển tiếp multicast giữa các instance. Interface mà Java nhìn thấy có thể là interface ảo, bridge hoặc tunnel. Cần xác minh chính sách của nền tảng trước khi chọn multicast làm cơ chế discovery/phân phối dữ liệu.

Nếu môi trường triển khai không hỗ trợ multicast, cân nhắc cơ chế thay thế như service discovery, message broker, HTTP polling, WebSocket hoặc một giao thức truyền tải được nền tảng hỗ trợ.

## 16. Các nguyên tắc sử dụng an toàn

Khi dùng `DatagramSocket.joinGroup`, `leaveGroup` và `NetworkInterface` trong Java 17:

1. Chọn một địa chỉ multicast hợp lệ và kiểm tra bằng `isMulticastAddress()`.
2. Chọn `NetworkInterface` cục bộ rõ ràng; kiểm tra interface tồn tại, đang up và hỗ trợ multicast.
3. Với receiver, tạo `DatagramSocket` unbound, bật `SO_REUSEADDR` trước bind khi cần, rồi bind wildcard address vào UDP port.
4. Gọi `joinGroup(group, networkInterface)` sau khi bind.
5. Nhận packet bằng `receive()` và xử lý đúng `offset`/`length`; reset packet length nếu tái sử dụng.
6. Khi kết thúc, gọi `leaveGroup` với đúng group/interface đã join rồi đóng socket.
7. Với sender, cấu hình `IP_MULTICAST_IF` để chọn interface outgoing; không cần join group chỉ để gửi.
8. Quản lý TTL, loopback, buffer và timeout theo yêu cầu mạng.
9. Không giả định multicast bảo đảm giao hàng, thứ tự hoặc chống trùng; UDP cần cơ chế ứng dụng nếu các thuộc tính đó quan trọng.
10. Kiểm thử trên hạ tầng thật, vì join thành công không bảo đảm switch/router/firewall chuyển tiếp packet.

`DatagramSocket.joinGroup` và `leaveGroup` từ Java 17 cung cấp cách trực tiếp để quản lý multicast membership. `NetworkInterface` cho phép chọn chính xác đường mạng cục bộ. Khi kết hợp đúng thứ tự bind, cấu hình reuse, join, receive, leave và close, ứng dụng có thể tham gia nhóm multicast một cách rõ ràng và kiểm soát được vòng đời socket.

## Tài liệu API Java 17

- [DatagramSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html)
- [NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html)
- [InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html)
- [DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [MulticastChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html)
