# Multicast Java: chọn card mạng khi máy có nhiều giao diện

## 1. Bối cảnh và mục tiêu

Một máy tính có thể sở hữu đồng thời nhiều **network interface (NIC/card mạng)**: Ethernet, Wi-Fi, VPN, adapter ảo cho Docker/VM, loopback hoặc nhiều cổng mạng vật lý. Với ứng dụng **multicast**, chỉ biết địa chỉ nhóm như `239.255.42.99` là chưa đủ: ứng dụng phải xác định **gửi gói qua interface nào** và **tham gia nhóm multicast trên interface nào**.

Hãy hình dung một máy đa giao diện:

~~~text
                         Java application
                         MulticastSocket
                               |
          +--------------------+---------------------+
          |                    |                     |
 Ethernet: eth0          Wi-Fi: wlan0             VPN: tun0
 192.168.10.20           192.168.1.20             10.8.0.2
          |                    |                     |
    LAN 192.168.10/24    LAN 192.168.1/24       VPN riêng

Nhóm multicast: 239.255.42.99, UDP port 50000
Câu hỏi: gói multicast phải đi qua LAN nào?
~~~

*Địa chỉ và tên NIC trong sơ đồ chỉ để minh họa.* Tên thật phụ thuộc hệ điều hành, driver, môi trường container và cấu hình mạng.

**Điểm cốt lõi:** trong Java, chọn NIC không phải chọn một “tên card Wi-Fi” ngẫu nhiên, cũng không phải chỉ gọi `InetAddress.getLocalHost()`. Bạn phải:

1. **Liệt kê** các `java.net.NetworkInterface` khả dụng và địa chỉ IP được gắn với chúng.
2. **Kiểm tra** NIC có hoạt động, có hỗ trợ multicast và có địa chỉ cùng họ với nhóm hay không.
3. **Chọn tường minh** interface bằng tên hệ thống, địa chỉ local hoặc cấu hình vận hành.
4. **Receiver:** gọi `MulticastSocket.joinGroup(SocketAddress, NetworkInterface)` với NIC đã chọn.
5. **Sender:** gọi `MulticastSocket.setNetworkInterface(NetworkInterface)` trước khi gửi datagram.
6. **Kiểm chứng** bằng log interface, bắt gói, cấu hình firewall/router và thử trên đúng VLAN/mạng.

Bài này tập trung vào multicast trong Java 17+, với `MulticastSocket`/`NetworkInterface`; phần cuối giới thiệu API `DatagramChannel` tương ứng và các tình huống IPv6.

## 2. Vì sao chọn sai card mạng lại làm multicast không hoạt động?

### 2.1. Multicast truyền UDP, không phải luồng TCP

Multicast IP cho phép một sender truyền datagram đến một **địa chỉ nhóm**, để những receiver đã tham gia nhóm trên interface/mạng phù hợp có thể nhận. Trong Java, ví dụ thường sử dụng **UDP multicast** bằng `MulticastSocket`; khác với máy chủ TCP dùng `ServerSocket.accept()` và kết nối hai chiều.

~~~text
Sender:  UDP datagram -> 239.255.42.99:50000
                               |
                         multicast LAN
                          /         \
                     Receiver A   Receiver B
                     join(group)  join(group)
~~~

Multicast UDP **không bảo đảm** gói sẽ đến, đến đúng một lần hay đến đúng thứ tự. Bản thân việc `send()` trả về không xác nhận receiver đã nhận. Nếu ứng dụng yêu cầu độ tin cậy, ACK/retry/deduplication phải do giao thức ứng dụng xử lý.

### 2.2. Một group có thể xuất hiện trên nhiều mạng

Một host có thể nối vào hai LAN khác nhau. Cùng địa chỉ `239.255.42.99` trên hai LAN **không có nghĩa** có một nhóm thống nhất trên Internet. Gói được phát qua interface/mạng nào sẽ phụ thuộc lựa chọn mạng đầu ra và chính sách định tuyến multicast; phía nhận phải tham gia nhóm trên interface tương ứng.

Ví dụ:

| Chương trình | Interface chọn | Khả năng nhận gói |
| --- | --- | --- |
| Sender tại PC A | Ethernet đi vào LAN 10 | Gói được phát trên LAN 10 theo đường đi multicast được OS hỗ trợ |
| Receiver tại PC B | Ethernet cùng LAN 10 | Có thể nhận nếu đã join đúng group/port và mạng cho phép |
| Receiver tại PC B | Wi-Fi ở LAN 20 khác | Không thể mặc định sẽ nhận từ LAN 10; cần hạ tầng multicast routing |
| Receiver tại chính PC A | Loopback | Không tự thay thế việc join trên Ethernet; loopback multicast tùy OS |
| Receiver trong VPN | VPN interface | Chỉ hoạt động nếu VPN hỗ trợ và chuyển tiếp multicast phù hợp |

**Không phải mọi switch/router/AP/VPN đều forward multicast**. Một NIC báo `supportsMulticast() == true` chỉ nói về khả năng được hệ điều hành/driver báo cho Java, **không** chứng minh đường truyền UDP multicast giữa hai máy hoạt động.

### 2.3. Chọn default interface tự động dễ sai

Nếu không chọn NIC rõ ràng, socket/OS có thể sử dụng interface theo định tuyến hiện tại, multicast policy hoặc lựa chọn mặc định. Điều này có thể thay đổi khi:

- Máy đổi từ Ethernet sang Wi-Fi hoặc VPN vừa kết nối.
- Docker/VM sinh thêm adapter ảo.
- Một interface bị down rồi up lại.
- Quy tắc routing, metric hoặc chính sách quản trị mạng thay đổi.
- Cùng chương trình chạy trên Windows, macOS, Linux hoặc container khác nhau.

Do đó **không dựa vào việc “máy này hiện chỉ dùng một card”**, không lấy phần tử đầu tiên của danh sách NIC và coi là đúng. Cần xem hoạt động mạng cụ thể thuộc interface nào rồi cấu hình tường minh.

## 3. NetworkInterface là gì? Các API thiết yếu

`java.net.NetworkInterface` là đối tượng mô tả interface mạng mà hệ điều hành cung cấp cho Java. Một interface có thể gắn **nhiều địa chỉ IP**; ngược lại, một tên hiển thị dễ đọc chưa chắc là tên định danh mà API `getByName` chấp nhận.

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| `NetworkInterface.getNetworkInterfaces()` | Liệt kê các NIC | Trả `Enumeration<NetworkInterface>`, có thể trả `null` trong trường hợp hiếm |
| `NetworkInterface.networkInterfaces()` | Duyệt dạng Stream (Java 9+) | Thuận tiện để lọc, vẫn cần xử lý `SocketException` |
| `NetworkInterface.getByName(name)` | Lấy NIC theo tên hệ thống | Ví dụ `eth0` hoặc tên có khoảng trắng; có thể trả `null` |
| `NetworkInterface.getByInetAddress(addr)` | Tìm NIC sở hữu một địa chỉ local | Thích hợp khi cấu hình chọn IP nguồn tường minh |
| `NetworkInterface.getByIndex(index)` | Tìm NIC theo index hệ thống | Index có thể khác giữa máy/lần triển khai |
| `nic.getName()` | Tên hệ thống dùng để nhận diện | Dùng cho tham số CLI hoặc cấu hình |
| `nic.getDisplayName()` | Tên thân thiện người dùng | Không dùng thay thế `getName()` một cách mặc định |
| `nic.getInetAddresses()` | Các địa chỉ IP gắn với NIC | Có thể gồm IPv4, IPv6, link-local |
| `nic.isUp()` | NIC đang hoạt động theo OS | Không bảo đảm thông suốt giữa hai host |
| `nic.supportsMulticast()` | OS/driver báo có hỗ trợ multicast | Không bảo đảm switch/AP/VPN sẽ chuyển gói |
| `nic.isLoopback()` | Interface loopback | Không mặc định dùng cho trao đổi giữa máy |
| `nic.isPointToPoint()` | Interface liên kết điểm-điểm | Cần kiểm tra môi trường, VPN thường có đặc thù |
| `nic.isVirtual()` | Interface ảo/subinterface theo định nghĩa API | Không bao quát mọi loại adapter ảo của hệ điều hành |

Các phép truy vấn trạng thái có thể ném `SocketException`. Nếu chương trình chạy trong container, không được giả định NIC của máy host xuất hiện nguyên vẹn trong namespace của container.

### 3.1. Liệt kê NIC và địa chỉ IP trước khi chọn

Mẫu Java có thể đặt trong một phương thức ném `SocketException`:

~~~java
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Collections;
import java.util.Enumeration;

static void printInterfaces() throws SocketException {
    Enumeration<NetworkInterface> all =
            NetworkInterface.getNetworkInterfaces();
    if (all == null) return;

    while (all.hasMoreElements()) {
        NetworkInterface nic = all.nextElement();
        System.out.printf(
                "%s | up=%s | multicast=%s | loopback=%s | ip=%s%n",
                nic.getName(), nic.isUp(), nic.supportsMulticast(),
                nic.isLoopback(),
                Collections.list(nic.getInetAddresses()));
    }
}
~~~

Đây là **phương thức minh họa**; chương trình đầy đủ ở phần 7 cũng có lệnh `list` tương đương. Danh sách in ra và thứ tự xuất hiện khác nhau theo máy. Không đưa một dòng như `eth0` làm “kết quả chắc chắn” ở mọi hệ điều hành.

### 3.2. Định danh theo tên khác định danh theo IP

Có thể chọn một NIC theo tên:

~~~java
// Minh họa, biến name đến từ cấu hình thực tế.
NetworkInterface nic = NetworkInterface.getByName(name);
if (nic == null) {
    throw new IllegalArgumentException("Unknown NIC: " + name);
}
~~~

Hoặc theo địa chỉ local đã biết:

~~~java
// Minh họa; localIp phải là địa chỉ GẮN VỚI MÁY, không phải IP group.
InetAddress localIp = InetAddress.getByName("192.168.10.20");
NetworkInterface nic = NetworkInterface.getByInetAddress(localIp);
~~~

Với cách chọn theo IP, cần kiểm tra `nic != null` và địa chỉ đó thật sự thuộc interface mà ứng dụng được phép dùng. Địa chỉ local trong ví dụ chỉ là minh họa; không sao chép nguyên sang máy khác.

**Không truyền địa chỉ multicast `239.255.42.99` vào `getByInetAddress()` để tìm NIC**: group là địa chỉ đích của datagram, không phải địa chỉ unicast local gắn với card.

## 4. Quy trình chọn NIC đúng trên máy multi-homed

### Bước 1: Xác định phạm vi nhận/gửi

Hãy trả lời các câu hỏi vận hành:

- Sender và receiver ở **cùng subnet/VLAN** hay phải đi qua router?
- Đang dùng **IPv4** multicast (`224.0.0.0/4`) hay **IPv6** multicast (`ff00::/8`)?
- Gói cần đi qua **Ethernet**, **Wi-Fi** hay một **VPN có hỗ trợ multicast**?
- Ứng dụng chỉ cần chạy trên một mạng, hay phải gửi/nhận qua **nhiều interface** đồng thời?
- Group/port/TTL được cấp bởi protocol hoặc người quản trị nào?

Ví dụ, một receiver trên LAN Ethernet 192.168.10/24 phải join trên NIC nối vào LAN đó thay vì mặc định join trên một adapter VPN đang được OS ưu tiên.

### Bước 2: Kiểm tra khả năng và họ địa chỉ

Ví dụ dùng group IPv4 `239.255.42.99`: nên chọn NIC **đang up**, **có hỗ trợ multicast** và **có địa chỉ IPv4**. Nếu group là IPv6 multicast, cần NIC có địa chỉ và phạm vi IPv6 phù hợp.

Không chỉ kiểm tra tên `"eth0"`: NIC có thể vẫn tồn tại nhưng `isUp() == false`, không có IPv4 hoặc driver không hỗ trợ multicast.

### Bước 3: Chỉ rõ NIC qua cấu hình

Thay vì hard-code NIC trong mã, có thể dùng CLI `--interface=...`, biến môi trường hoặc tệp cấu hình. Tên NIC có thể đổi giữa máy; một tùy chọn bằng **local IP** có thể giúp cấu hình dễ quản lý khi ứng dụng phải chọn đường đi theo địa chỉ.

Ví dụ lệnh giả định tên NIC thực tế là `eth0`:

~~~bash
java MulticastNicDemo recv eth0
java MulticastNicDemo send eth0 "xin chao"
~~~

Thay `eth0` bằng **tên trả về từ lệnh `list` trên chính máy**, không phải tên hiển thị tùy tiện. Nếu tên có khoảng trắng, đặt trong dấu nháy kép ở shell.

### Bước 4: Áp dụng NIC đúng API

Receiver chọn NIC **khi join** nhóm; sender chọn NIC **khi gửi**:

~~~java
// Receiver (các biến socket, group, port, nic được tạo/kiểm tra trước).
socket.joinGroup(new InetSocketAddress(group, port), nic);

// Sender (socket dùng để gửi; chọn interface trước khi send).
socket.setNetworkInterface(nic);
socket.send(new DatagramPacket(bytes, bytes.length, group, port));
~~~

Đây là **mã minh họa trong ngữ cảnh chương trình**, không phải file độc lập. Hai thao tác trên thực hiện hai nhiệm vụ khác nhau: `joinGroup` đăng ký membership trên interface của receiver, `setNetworkInterface` điều khiển interface đầu ra của sender.

### Bước 5: Quan sát thực tế

Với sender, ghi log `nic.getName()`, group, port và họ IP. Với receiver, ghi log cùng thông tin tại thời điểm `joinGroup` và tại lúc nhận. Nếu không nhận gói, dùng công cụ bắt gói trên NIC liên quan để phân biệt **không phát**, **không đến interface**, **bị firewall chặn** và **ứng dụng không join đúng**.

## 5. Receiver: joinGroup phải gắn với đúng NetworkInterface

### 5.1. Mẫu nhận multicast IPv4

~~~java
// Minh họa; các biến group, port và nic đã được khởi tạo.
InetSocketAddress groupAddress = new InetSocketAddress(group, port);

try (MulticastSocket socket = new MulticastSocket(port)) {
    socket.setSoTimeout(15_000);
    socket.joinGroup(groupAddress, nic);
    try {
        byte[] buf = new byte[1500];
        DatagramPacket packet = new DatagramPacket(buf, buf.length);
        socket.receive(packet);
        String message = new String(packet.getData(),
                packet.getOffset(), packet.getLength(),
                StandardCharsets.UTF_8);
        System.out.println("Received: " + message);
    } finally {
        socket.leaveGroup(groupAddress, nic);
    }
}
~~~

Đây là **đoạn minh họa**, chưa có import/`main` và yêu cầu group multicast hợp lệ. Chương trình hoàn chỉnh ở phần 7 dùng đúng các lời gọi này.

Cần lưu ý:

- `new MulticastSocket(port)` bind socket nhận tới cổng UDP cục bộ và thường sử dụng **wildcard bind address**, không khóa socket vào một IP unicast của NIC.
- `joinGroup(groupAddress, nic)` mới chọn **NIC nhận membership**. Binding với `0.0.0.0:port` không phải “join mọi NIC”.
- `receive(DatagramPacket)` trả về một datagram và sửa `length` thành **số byte thực nhận**. Khi decode text phải sử dụng `packet.getOffset()` và `packet.getLength()`, không giải mã cả mảng dự trữ 1.500 byte.
- `setSoTimeout(15_000)` giúp `receive()` ném `SocketTimeoutException` nếu không nhận được datagram trong khoảng chờ; timeout **không chứng minh sender chết**.
- `leaveGroup(groupAddress, nic)` rời membership đã tham gia; `finally` và `try-with-resources` bảo đảm dọn tài nguyên ngay cả khi có lỗi. Đóng socket cũng giải phóng membership trong quá trình OS cleanup.
- Nhiều ứng dụng bind cùng một multicast UDP port có hành vi chia sẻ/nhận gói tùy OS và socket options. Nếu cần nhiều receiver trên cùng máy, kiểm tra `SO_REUSEADDR` và các quy tắc bind cụ thể; không mặc định mọi OS đều cho kết quả giống nhau.

### 5.2. Tại sao không dùng overload joinGroup cũ?

API cũ:

~~~java
socket.joinGroup(group); // Không chọn NetworkInterface tường minh.
~~~

Overload `joinGroup(InetAddress)` đã bị deprecated; khi máy có nhiều NIC, nó không diễn đạt interface cụ thể mà ứng dụng muốn đăng ký membership. Dùng overload:

~~~java
socket.joinGroup(new InetSocketAddress(group, port), nic);
~~~

Tương tự, với gửi multicast, `setInterface(InetAddress)` là API cũ và kém rõ khi phải làm việc với nhiều địa chỉ/họ địa chỉ trên một NIC. Hãy ưu tiên `setNetworkInterface(NetworkInterface)` và ghi rõ cả group lẫn port.

### 5.3. Join nhiều NIC có được không?

Được, nếu yêu cầu ứng dụng là **nghe cùng nhóm trên nhiều mạng** và môi trường hỗ trợ. Bạn có thể join group trên từng `NetworkInterface` mong muốn, rồi leave tương ứng khi kết thúc. Nhưng:

- Chỉ join các interface đã được phê duyệt; không tự join toàn bộ NIC gồm VPN, bridge, loopback vì “cho chắc”.
- Một datagram có thể đi vào nhiều interface hoặc đi qua topology phức tạp; **ứng dụng nên có cơ chế deduplicate** nếu việc xử lý lặp gây hại.
- Nếu cần phân biệt datagram **đến từ interface nào**, `DatagramPacket.getAddress()` chỉ cho biết **địa chỉ IP người gửi**, không phải trực tiếp NIC nhận. Cơ chế nhận metadata interface có thể phụ thuộc API/hệ điều hành, hoặc dùng socket riêng gắn với từng NIC theo thiết kế và kiểm chứng.
- Cần quản lý chính xác mọi membership; nếu cấu hình hot-reload, rời NIC cũ trước khi hoặc trong lúc chuyển sang NIC mới có kiểm soát.

## 6. Sender: chọn NIC đầu ra bằng setNetworkInterface

### 6.1. Mẫu gửi multicast

~~~java
// Minh họa; group là InetAddress multicast,
// nic là NetworkInterface hợp lệ, bytes là UTF-8 payload.
try (MulticastSocket socket = new MulticastSocket()) {
    socket.setNetworkInterface(nic);
    socket.setTimeToLive(1);
    socket.send(new DatagramPacket(
            bytes, bytes.length, group, port));
}
~~~

`setNetworkInterface(nic)` chọn interface multicast đầu ra. Nó **không** tự tham gia nhóm nhận, không thay thế `joinGroup` cho receiver và không bảo đảm datagram sẽ được router/switch/OS chuyển tiếp tới mọi người nhận.

`setTimeToLive(1)` giới hạn hop count của multicast IPv4 trong ví dụ, thông thường giữ gói trong mạng cục bộ/không đi qua router; **TTL không phải cơ chế xác thực hoặc ranh giới bảo mật**. Với IPv6, cần xem hop limit và scope của địa chỉ multicast; một group link-local không thể biến thành group global chỉ bằng cách tăng TTL/hop limit.

### 6.2. NIC nhiều IP và outgoing source address

Một `NetworkInterface` có thể có cả IPv4 và IPv6 hoặc nhiều IP cùng họ. Việc chọn NIC cho multicast quyết định interface phát; **địa chỉ IP nguồn cụ thể** được OS chọn theo routing/source-address selection và socket configuration. Đừng đồng nhất `nic.getInetAddresses().nextElement()` với “IP nguồn luôn được sử dụng”.

Nếu protocol yêu cầu source address cụ thể, bạn phải thiết kế và kiểm thử việc bind local address/interface và các socket options trên OS đích. Khi làm multicast sender, **chọn bằng `setNetworkInterface`** là bước rõ ràng để tránh OS mặc định chọn VPN hoặc Wi-Fi khác.

### 6.3. Phát cùng dữ liệu trên hai LAN

Nếu yêu cầu truyền tới hai mạng độc lập, bạn có thể chọn NIC A rồi gửi, chọn NIC B rồi gửi (hoặc quản lý socket riêng theo từng NIC), **nhưng phải chủ động phát hai lần**. Việc phát multicast một lần trên Ethernet không chứng minh gói đã tới Wi-Fi subnet khác. Cần xử lý gói trùng, cấu hình multi-homed, router support và quy tắc quyền truy cập.

## 7. Ví dụ Java 17+ hoàn chỉnh: liệt kê NIC, chọn NIC, gửi/nhận UDP multicast

Demo dùng **một file Java** và ba chế độ:

- `list` — in các NIC và khả năng multicast do OS báo.
- `recv <interface>` — join group `239.255.42.99` trên NIC đã chọn, chờ một datagram tại UDP port `50000`, in payload UTF-8 rồi rời group.
- `send <interface> <message>` — chọn NIC phát, giới hạn TTL=1, gửi một datagram UDP tới cùng group/port.

Không có tên NIC nào hard-code. Chương trình kiểm tra NIC **tồn tại**, **đang up**, **supportsMulticast()`** và **có IPv4** trước khi dùng group IPv4. Nó kiểm tra kích thước thông điệp gửi (tối đa 1.400 byte trong demo), đóng socket sau mỗi hành động và có timeout chờ nhận.

**Lưu ý:** Đây là chương trình chạy được khi OS/mạng cho phép multicast. Việc gửi và nhận thực tế phải kiểm tra trên NIC, LAN, firewall và cấu hình thích hợp; stdout của `list` phụ thuộc máy. Lệnh không truyền tham số luôn có stdout xác định để kiểm tra biên dịch và CLI, nhưng không thể từ đó suy ra hạ tầng multicast đã hoạt động.

Lưu mã sau vào file **MulticastNicDemo.java**:

~~~java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;

public class MulticastNicDemo {
    private static final String GROUP = "239.255.42.99";
    private static final int PORT = 50000;

    private static NetworkInterface requireNic(String name)
            throws SocketException {
        NetworkInterface nic = NetworkInterface.getByName(name);
        if (nic == null) {
            throw new IllegalArgumentException("Unknown NIC: " + name);
        }

        if (!nic.isUp() || !nic.supportsMulticast()) {
            throw new IllegalArgumentException(
                    "NIC not up/multicast capable: " + name);
        }

        boolean hasV4 = false;
        for (Enumeration<InetAddress> addresses = nic.getInetAddresses();
             addresses.hasMoreElements();) {
            if (addresses.nextElement() instanceof Inet4Address) {
                hasV4 = true;
            }
        }
        if (!hasV4) {
            throw new IllegalArgumentException(
                    "NIC has no IPv4 address: " + name);
        }
        return nic;
    }

    private static void list() throws SocketException {
        Enumeration<NetworkInterface> all =
                NetworkInterface.getNetworkInterfaces();
        if (all == null) {
            return;
        }

        while (all.hasMoreElements()) {
            NetworkInterface nic = all.nextElement();
            System.out.printf(
                    "%s | up=%s | multicast=%s | loopback=%s"
                    + " | addresses=%s%n",
                    nic.getName(), nic.isUp(), nic.supportsMulticast(),
                    nic.isLoopback(),
                    Collections.list(nic.getInetAddresses()));
        }
    }

    private static void receive(NetworkInterface nic)
            throws IOException {
        InetAddress group = InetAddress.getByName(GROUP);
        InetSocketAddress membership =
                new InetSocketAddress(group, PORT);

        try (MulticastSocket socket = new MulticastSocket(PORT)) {
            socket.setSoTimeout(15_000);
            socket.joinGroup(membership, nic);
            try {
                byte[] data = new byte[1500];
                DatagramPacket packet =
                        new DatagramPacket(data, data.length);
                socket.receive(packet);

                String text = new String(
                        packet.getData(), packet.getOffset(),
                        packet.getLength(), StandardCharsets.UTF_8);
                System.out.println("Received: " + text);
            } finally {
                socket.leaveGroup(membership, nic);
            }
        }
    }

    private static void send(NetworkInterface nic, String message)
            throws IOException {
        byte[] data = message.getBytes(StandardCharsets.UTF_8);
        if (data.length > 1400) {
            throw new IllegalArgumentException("Message too large");
        }

        InetAddress group = InetAddress.getByName(GROUP);
        try (MulticastSocket socket = new MulticastSocket()) {
            socket.setNetworkInterface(nic);
            socket.setTimeToLive(1);
            socket.send(new DatagramPacket(
                    data, data.length, group, PORT));
            System.out.println("Sent: " + message);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println("Usage: java MulticastNicDemo list");
            System.out.println(
                    "       java MulticastNicDemo recv <interface>");
            System.out.println(
                    "       java MulticastNicDemo send <interface> <message>");
            return;
        }

        switch (args[0]) {
            case "list":
                if (args.length != 1) {
                    throw new IllegalArgumentException(
                            "list takes no arguments");
                }
                list();
                break;
            case "recv":
                if (args.length != 2) {
                    throw new IllegalArgumentException(
                            "recv needs interface");
                }
                receive(requireNic(args[1]));
                break;
            case "send":
                if (args.length != 3) {
                    throw new IllegalArgumentException(
                            "send needs interface and message");
                }
                send(requireNic(args[1]), args[2]);
                break;
            default:
                throw new IllegalArgumentException("Unknown mode");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 MulticastNicDemo.java
java MulticastNicDemo
~~~

Stdout **chính xác khi không truyền tham số**:

~~~text
Usage: java MulticastNicDemo list
       java MulticastNicDemo recv <interface>
       java MulticastNicDemo send <interface> <message>
~~~

Tiếp tục khám phá NIC:

~~~bash
java MulticastNicDemo list
~~~

Lệnh này in các NIC **thực tế** với trạng thái `up`, `multicast`, `loopback` và danh sách IP; không có stdout cố định trên mọi máy.

### 7.1. Thử trên hai terminal

Sau khi chọn tên interface có multicast + IPv4 phù hợp (ví dụ `eth0` **nếu đúng là tên từ lệnh list**), mở hai terminal. Trên máy cùng LAN hoặc hai máy trong cùng mạng hỗ trợ multicast:

**Terminal A — receiver trước:**

~~~bash
java MulticastNicDemo recv eth0
~~~

**Terminal B — sender sau khi receiver đã join group:**

~~~bash
java MulticastNicDemo send eth0 "hello multicast"
~~~

Nếu datagram đi qua được mạng và đến đúng NIC/port, sender in:

~~~text
Sent: hello multicast
~~~

Receiver in:

~~~text
Received: hello multicast
~~~

Đây là **kết quả kỳ vọng có điều kiện**, không phải bảo đảm mọi máy đều nhận. Hãy thay `eth0` bằng tên NIC đúng ở từng host. Sender và receiver có thể dùng **tên NIC khác nhau** trên hai máy miễn là NIC thực sự nối vào miền multicast phù hợp. Chương trình nhận có timeout 15 giây; nếu không có datagram nó có thể ném `SocketTimeoutException` — xem phần chẩn đoán bên dưới.

### 7.2. Giải thích luồng của demo

1. `list` cho phép kiểm tra các adapter, nhưng người vận hành vẫn phải quyết định adapter nào nối đúng LAN.
2. `requireNic` lấy NIC theo **tên hệ thống**, kiểm tra `isUp`, `supportsMulticast` và có địa chỉ IPv4; không cố đoán NIC “tốt nhất”.
3. Receiver bind vào **UDP port 50000** rồi `joinGroup(membership, nic)`. Đây là bước xác định membership trên NIC nhận.
4. Sender chọn NIC phát bằng `socket.setNetworkInterface(nic)`, dùng `TTL=1` và gửi đúng một datagram UTF-8.
5. Receiver dùng `DatagramPacket.getLength()` để decode đúng số byte nhận được; không đọc phần dư của mảng.
6. Receiver rời group trong `finally`; cả sender lẫn receiver đóng socket bằng try-with-resources.
7. `send()` thành công chỉ có nghĩa ứng dụng đưa datagram cho network stack. Không có ACK trong multicast UDP demo; receiver phải tự xác nhận bằng log của chính nó.

### 7.3. Những gì demo chưa làm

- Không thực hiện discovery, xác thực, mã hóa, đảm bảo thứ tự hay truyền tin cậy.
- Không cố đảm bảo giao thức chạy qua router/VPN hoặc multicast loopback trên mọi OS.
- Không hỗ trợ packet lớn hơn 1.400 byte; đây là giới hạn **demo**, không phải thông số MTU mạng phổ quát.
- Không phân biệt nhiều nguồn cùng gửi vào group và không có replay protection hoặc message ID.
- Không tự chọn cả IPv4 và IPv6 hoặc liên tục lắng nghe nhiều packet.

Các giới hạn này là chủ ý để tập trung vào bài học **chọn network interface chính xác**.

## 8. Khi máy có IPv4 và IPv6, cần chọn theo họ địa chỉ

### 8.1. IPv4 multicast

IPv4 multicast dùng dải `224.0.0.0/4`. Ví dụ của bài dùng group `239.255.42.99` thuộc dải multicast quản trị cục bộ; khi triển khai thực tế, hãy **phối hợp chọn địa chỉ nhóm** để tránh xung đột với ứng dụng khác trong tổ chức.

Khi dùng IPv4 group:

- Chọn NIC có địa chỉ `Inet4Address` và khả năng multicast.
- Đừng đưa địa chỉ IPv6 vào chỗ tham số local IPv4 rồi kỳ vọng OS tự chuyển giao thức.
- Nếu cấu hình IP nguồn cụ thể, hãy dùng địa chỉ **local unicast** thuộc NIC, không dùng group address.
- Đảm bảo firewall cho phép **UDP port** tương ứng và mạng chuyển multicast traffic.

### 8.2. IPv6 multicast và scope

IPv6 multicast dùng dải `ff00::/8`. Các scope được mã hóa trong địa chỉ; chẳng hạn nhóm `ff02::...` thuộc phạm vi **link-local**. Chọn một NIC có IPv6 không đủ: phải cân nhắc scope và mạng trực tiếp tương ứng. IPv6 link-local và multicast scoped address thường cần **interface/scope ID** được chỉ định đúng để routing không mơ hồ.

API `NetworkInterface` vẫn được dùng để chọn NIC; nhưng:

- Group phải là địa chỉ multicast IPv6 hợp lệ, không dùng group IPv4 `239.255.42.99`.
- NIC phải có IPv6, scope tương thích và network stack hỗ trợ IPv6 multicast.
- `MulticastSocket`/`DatagramChannel` phải sử dụng protocol family phù hợp; nếu dùng `DatagramChannel` có thể mở tường minh bằng `StandardProtocolFamily.INET6`.
- Địa chỉ IPv6 scoped và NIC/scope ID cần được xử lý tường minh theo API; đừng chỉ lấy chuỗi địa chỉ rồi bỏ zone ID.

Ví dụ lựa chọn IPv6 theo tên interface (minh họa, chưa phải sender/receiver):

~~~java
NetworkInterface nic = NetworkInterface.getByName(interfaceName);
if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
    throw new IllegalArgumentException("Invalid multicast NIC");
}
// Tiếp theo, kiểm tra NIC có địa chỉ Inet6Address và
// chọn địa chỉ IPv6 multicast với scope đúng nhu cầu.
~~~

Đoạn trên nằm trong phương thức có thể ném `SocketException`. Một nhóm IPv6 scope link-local **không thể** truyền qua các router chỉ vì tăng hop limit. Phần chọn nhóm và scope phải theo chính sách mạng IPv6 của ứng dụng.

## 9. Lựa chọn tương đương với NIO DatagramChannel

Nếu ứng dụng dùng NIO thay vì `MulticastSocket`, `java.nio.channels.DatagramChannel` hỗ trợ các thao tác multicast trên interface qua các API có ý nghĩa tương tự:

- `DatagramChannel.open(StandardProtocolFamily.INET)` mở channel kiểu IPv4 khi nền tảng hỗ trợ.
- `channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic)` chọn **NIC phát** multicast.
- `channel.join(group, nic)` tham gia nhóm trên NIC nhận; trả `MembershipKey`.
- `MembershipKey.drop()` hủy đăng ký membership.
- `channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1)` đặt TTL multicast IPv4.

Ví dụ **đoạn code minh họa**:

~~~java
// Cần import java.net.*, java.nio.channels.*;
// group là InetAddress IPv4 multicast, nic là NetworkInterface.
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.setOption(
            StandardSocketOptions.IP_MULTICAST_IF, nic);
    channel.setOption(
            StandardSocketOptions.IP_MULTICAST_TTL, 1);

    // Khi cần nhận: bind cổng và join(group, nic).
    // MembershipKey key = channel.join(group, nic);
    // ... receive và kiểm tra gói ...
    // key.drop();
}
~~~

Đoạn trên không phải chương trình độc lập, và chỉ minh họa API; để nhận datagram phải bind channel vào port và đọc gói đúng cách. Trong code thật, khi `join` thành công, giữ `MembershipKey` và gọi `drop()` trong cleanup (đóng channel cũng giải phóng resources).

**Không dùng `MulticastSocket.setNetworkInterface` cho một `DatagramChannel`**: hai loại đối tượng có API riêng. Cũng không coi `SO_REUSEADDR`, `IP_MULTICAST_IF` và membership key là một thứ: chúng giải quyết các vấn đề khác nhau.

## 10. Những lỗi thường gặp khi máy có nhiều NIC

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/cách sửa |
| --- | --- | --- |
| Máy có Ethernet + Wi-Fi, receiver không nhận | Join group trên NIC khác với LAN nơi gói đến | In `getName()` và địa chỉ NIC; truyền đúng NIC vào `joinGroup(..., nic)` |
| Sender `send()` không lỗi nhưng phía kia im lặng | Gói UDP bị chặn, phát sai interface hoặc receiver chưa join | Kiểm tra NIC phát bằng `setNetworkInterface`, firewall, VLAN, capture packet |
| Java chọn VPN thay Ethernet | Routing/default interface thay đổi | Không dựa vào mặc định; cấu hình NIC tường minh |
| `getByName("Ethernet")` trả `null` | Dùng display name thay vì system name trên OS cụ thể | Chạy `list` và dùng đúng `getName()` |
| NIC có tên nhưng không chạy | `isUp() == false` | Kiểm tra link trạng thái và xử lý NIC bị mất/hot-plug |
| `supportsMulticast() == false` | Driver/OS không báo hỗ trợ | Chọn NIC khác hoặc kiểm tra adapter/network stack |
| IPv4 group nhưng NIC chỉ có IPv6 | Khác họ địa chỉ | Chọn NIC có IPv4 hoặc thiết kế group IPv6 đúng scope |
| Dùng `getByInetAddress(multicastGroup)` để tìm NIC | Group không phải IP local | Truyền địa chỉ local unicast đã gắn NIC |
| `joinGroup(InetAddress)` hoạt động lúc được lúc không | Không chọn NIC tường minh trên máy multi-homed | Dùng `joinGroup(SocketAddress, NetworkInterface)` |
| Bind socket vào IP local nhưng vẫn không nhận | Bind không đồng nghĩa với join multicast membership | Bind đúng port/wildcard khi thích hợp, rồi join NIC được chọn |
| Sender phát ở interface A, receiver join ở B | Hai mạng/VLAN không có multicast routing | Chọn đúng NIC hoặc cấu hình định tuyến multicast trên hạ tầng |
| Chạy trên Docker/VM mà NIC khác host | Network namespace/bridge cách ly multicast | Liệt kê NIC từ **bên trong môi trường chạy**, kiểm tra mode mạng |
| Gói từ PC khác không đến qua Wi-Fi | AP client isolation, IGMP snooping, multicast filtering, firewall | Đối chiếu gói đến NIC bằng capture, kiểm tra cấu hình AP/switch |
| Receiver không nhận dù đã chọn NIC | Join sau khi sender gửi; UDP không có replay | Mở receiver trước khi gửi; thêm retry/application protocol nếu cần |
| `SocketTimeoutException` sau 15 giây | Chưa có datagram trong khoảng chờ | Xác minh sender phát, receiver đã join, NIC/group/port phù hợp |
| Nhận dữ liệu rác ở cuối String | Decode cả buffer thay vì số byte thực nhận | Dùng `packet.getOffset()` và `packet.getLength()` |
| Sender gửi nhiều UDP packet nhưng mất một số | Multicast UDP không bảo đảm delivery | Thiết kế sequence number, ACK/repair, FEC tùy nhu cầu |
| Gửi 2 NIC nhưng receiver xử lý sự kiện hai lần | Trùng packet do topology/app logic | Đưa message ID và deduplicate tại application layer |

**Quan sát lỗi một cách hệ thống:** đầu tiên xác minh Java thực sự chọn NIC nào; tiếp theo kiểm tra sender có phát datagram trên NIC đó; sau đó kiểm tra datagram có xuất hiện trên NIC receiver; cuối cùng kiểm tra receiver đã join đúng group/port và giải mã packet đúng. Đừng bắt đầu bằng cách thay ngẫu nhiên nhiều socket options cùng lúc.

## 11. Trường hợp firewall, switch và router

### 11.1. Group membership và IGMP/MLD

Đối với IPv4, hệ điều hành và thiết bị mạng thường sử dụng cơ chế **IGMP** để quản lý việc host tham gia multicast group trên một link; IPv6 sử dụng **MLD**. Các switch có IGMP snooping có thể chỉ chuyển gói đến các cổng được ghi nhận có người nhận, nhưng chính sách phụ thuộc hạ tầng.

Việc `joinGroup` trả về thành công **không chứng minh** switch đã cấu hình xong đường chuyển tiếp hoặc firewall đã cho phép gói đến ứng dụng. Khi nghi ngờ, phối hợp với đội vận hành mạng để xem IGMP querier/snooping, multicast filtering và ACL.

### 11.2. TTL không tạo đường multicast giữa các subnet

`socket.setTimeToLive(1)` thường ngăn gói multicast đi qua router. Tăng TTL không đủ nếu router **không chạy multicast routing**, group bị lọc hoặc địa chỉ thuộc scope bị giới hạn. Trong IPv6, scope cũng xác định phạm vi hợp lệ của group. Quyết định triển khai qua VLAN/subnet cần thiết kế hạ tầng; Java sender không thể ép toàn bộ mạng forward multicast chỉ bằng API.

### 11.3. Firewall và an toàn dữ liệu

Datagram gửi đến nhóm multicast có thể được nhiều receiver cùng mạng nghe, nên **không gửi bí mật dưới dạng plaintext** chỉ vì bạn “biết group” hoặc TTL nhỏ. Multicast không phải kênh bảo mật; nếu ứng dụng có thông tin nhạy cảm, cần xác thực payload, integrity và mã hóa phù hợp. Đồng thời giới hạn kích thước datagram, tốc độ nhận và xử lý dữ liệu không đáng tin để tránh lạm dụng.

## 12. Tình huống thực hành

### Tình huống A — Ethernet và VPN cùng bật

Máy có Ethernet nối LAN văn phòng và VPN. Receiver cần nhận sự kiện chỉ trong LAN văn phòng. Nên làm gì?

**Đáp án:** dùng `list` tìm tên NIC Ethernet thật, kiểm tra đang up, có IPv4 và hỗ trợ multicast, rồi `joinGroup(groupSocketAddress, ethernetNic)`. Không dựa vào default route sau khi VPN bật. Kiểm chứng bằng packet capture trên Ethernet.

### Tình huống B — Cùng group, hai VLAN tách biệt

Sender trên VLAN A, receiver join group trên VLAN B; cả hai dùng `239.255.42.99:50000` nhưng không nhận.

**Đáp án:** địa chỉ group giống nhau không tự tạo đường chuyển tiếp giữa VLAN. Muốn multicast qua router phải có multicast routing/scope/policy tương ứng; nếu nghiệp vụ chỉ cần nội bộ VLAN, hãy chọn NIC cùng VLAN hoặc thiết kế gateway ứng dụng.

### Tình huống C — Chọn đúng NIC nhưng receiver chỉ nhận khi sender chạy sau

Receiver khởi động muộn hơn sender và bỏ lỡ một datagram. Đây có phải lỗi chọn card mạng?

**Đáp án:** không nhất thiết. UDP multicast không lưu trữ gói cho receiver tương lai. Phải join trước lúc phát, hoặc có cơ chế replay/retry/application state synchronization.

### Tình huống D — Một NIC có hai địa chỉ IPv4

NIC `eth0` gắn hai IP local; `NetworkInterface.getByName("eth0")` chỉ trả một đối tượng NIC. Có cần join hai lần chỉ vì có hai IP?

**Đáp án:** không nhất thiết. Membership của `joinGroup(..., nic)` được chỉ định theo **interface**, không yêu cầu lặp mỗi địa chỉ của NIC. Nếu cần chọn **source IP cụ thể**, phải xét hành vi bind/source address riêng; đừng tự hiểu mỗi IP là một NIC.

### Tình huống E — Interface có chữ “virtual” trong tên

Một adapter VPN hoặc bridge là đường multicast chủ đích cho ứng dụng. Có nên tự bỏ mọi NIC có `isVirtual() == true` không?

**Đáp án:** không. “Ảo” không đồng nghĩa “không dùng được” hay “không được phép dùng”. Dùng chính sách cấu hình rõ, hỗ trợ multicast của OS và phép thử mạng thực. Đừng chọn NIC chỉ theo nhãn vật lý/ảo.

### Tình huống F — Chỉ có IPv6 link-local

Receiver cần join group IPv6 link-local trên máy nhiều interface. Chọn tên NIC hay chỉ truyền chuỗi `ff02::...`?

**Đáp án:** phải xác định **đúng interface/scope** và sử dụng họ địa chỉ IPv6 phù hợp. Chỉ có chuỗi group chưa đủ để loại bỏ mơ hồ phạm vi link-local trên máy nhiều NIC. Trong NIO có thể dùng `channel.join(group, nic)` với `StandardProtocolFamily.INET6` và cấu hình thích hợp.

## 13. Checklist trước khi triển khai

- [ ] Đã xác định group, UDP port, IPv4/IPv6, multicast scope và mục tiêu LAN/VLAN?
- [ ] Đã gọi `getNetworkInterfaces()`/`getByName()` để nhìn **NIC thật** của tiến trình đang chạy?
- [ ] NIC được chọn có `isUp()==true`, `supportsMulticast()==true` và họ địa chỉ phù hợp?
- [ ] Cấu hình NIC được khai báo rõ, không lấy NIC đầu tiên/default route một cách mù quáng?
- [ ] Receiver sử dụng `joinGroup(SocketAddress, NetworkInterface)` trên đúng NIC?
- [ ] Sender sử dụng `setNetworkInterface(NetworkInterface)` trước khi phát?
- [ ] Bind UDP port hợp lệ, dùng đúng group/port, xử lý receive timeout và leaveGroup khi đóng?
- [ ] Nếu cần nhận trên nhiều NIC, đã join/leave từng interface và có chính sách deduplication?
- [ ] Đã kiểm tra sự khác biệt giữa host network, container namespace, VM bridge và VPN?
- [ ] Đã xác minh IGMP/MLD, switch/AP, firewall, router, TTL/hop limit theo đường truyền thực?
- [ ] Datagram được decode theo **độ dài thực nhận**, giới hạn payload và xác thực nguồn/dữ liệu?
- [ ] Có log group/port/NIC, metrics gói, test packet capture và khả năng phục hồi khi NIC down/up?
- [ ] Không coi multicast UDP là có bảo đảm tin cậy hay bảo mật mặc định?

**Kết luận:** Với máy có nhiều card mạng, chọn đúng NIC là một phần của thiết kế **UDP multicast**, không phải chi tiết tự động được Java quyết định đúng cho mọi môi trường. `NetworkInterface` giúp định danh và kiểm tra NIC; `joinGroup(..., nic)` quyết định membership của receiver; `setNetworkInterface(nic)` quyết định interface gửi của sender. Kết quả cuối cùng vẫn phụ thuộc group scope, hệ điều hành, topology, firewall và cấu hình multicast của mạng thực tế.