# MulticastSocket và tham gia nhóm bằng địa chỉ cùng NetworkInterface

**Chủ đề:** Java Advance - networking  
**Nhóm kiến thức:** Multicast

Trong Java networking, **multicast** là cách một tiến trình gửi **một UDP datagram** tới **địa chỉ nhóm multicast** để các tiến trình đã đăng ký nhận nhóm đó, trên các giao diện mạng thích hợp, *có thể* nhận được bản sao. Người gửi không cần mở riêng một kết nối tới từng người nhận. Tuy nhiên, multicast **không phải TCP**, không bảo đảm datagram đến nơi, đúng thứ tự hay chỉ đến một lần, và chỉ hoạt động trong phạm vi mạng cho phép multicast.

Với **java.net.MulticastSocket**, một bên nhận không chỉ cần biết **địa chỉ nhóm** mà còn phải chọn đúng **NetworkInterface** để tham gia nhóm. Cách gọi nên dùng trên Java 17+ là:

~~~java
socket.joinGroup(new InetSocketAddress(groupAddress, 0), networkInterface);
~~~

**groupAddress** là IP multicast, còn **networkInterface** là **giao diện mạng cục bộ** mà socket tham gia nhóm. Bên nhận còn phải **bind UDP socket vào cổng nhận thực tế**. Nhầm lẫn ba giá trị **group IP**, **giao diện nhận**, **UDP port** là nguyên nhân phổ biến khiến chương trình chạy không có exception nhưng không nhận được dữ liệu.

## 1. Mô hình multicast: một nhóm, nhiều giao diện, một cổng UDP

~~~text
MÁY GỬI                                             MÁY NHẬN A
MulticastSocket / DatagramSocket                     MulticastSocket
  ├─ gửi UDP tới 239.255.42.99:50000                 ├─ bind UDP port 50000
  ├─ chọn interface để gửi                           ├─ join group 239.255.42.99
  └─ đặt TTL/scope phù hợp                           └─ trên NetworkInterface A
                  │                                           ▲
                  ▼                                           │
               MẠNG CÓ ROUTING/SWITCHING MULTICAST ───────────┤
                  │                                           │
                  └─────────────────────► MÁY NHẬN B          │
                                           ├─ bind port 50000
                                           └─ join cùng group
                                              trên interface B
~~~

**Địa chỉ nhóm** là đích logic của datagram, ví dụ **239.255.42.99** (IPv4 multicast administratively scoped dùng để minh họa). Nó **không** phải IP của một máy hay tên của **NetworkInterface**. Giao diện nhận có thể là Ethernet, Wi-Fi hoặc một interface khác được OS quản lý. Cổng UDP **50000** là cổng mà mỗi ứng dụng nhận đang **bind**; nếu nhiều máy muốn trao đổi theo cùng protocol, họ thường thống nhất **cùng group IP và UDP port**, đồng thời mỗi máy phải chọn giao diện mạng phù hợp với mình.

Mô hình nhóm multicast thường được gọi là **any-source multicast (ASM)**: thành viên có thể nhận datagram tới nhóm từ các nguồn được mạng chuyển tới. Nếu cần lọc theo nguồn cụ thể (**source-specific multicast**, SSM), xem **DatagramChannel.join(InetAddress group, NetworkInterface interf, InetAddress source)** và API **MembershipKey** tương ứng; **MulticastSocket.joinGroup(group, interface)** không tự động lọc một người gửi duy nhất.

### Phân biệt địa chỉ và vai trò

| Thành phần | Ví dụ | Được dùng ở đâu? |
| --- | --- | --- |
| **Group IP** | **239.255.42.99** | Trong **joinGroup(...)** và làm đích của **DatagramPacket** |
| **Group/UDP port** | **50000** | Trong **receiver.bind(..., 50000)** và **sender.send(packet tới group:50000)** |
| **NetworkInterface** | **NetworkInterface.getByName("eth0")**, nếu máy có | Chỉ định **giao diện cục bộ** dùng để join/leave và chọn hướng gửi |
| **IP của interface** | **192.168.1.15** | Một địa chỉ unicast gán cho NIC; **không** thay thế group IP |
| **Sender source port** | Cổng động do OS cấp | Xuất hiện trong địa chỉ nguồn UDP; **không bắt buộc** trùng port của receiver |
| **TTL/hop limit** | **1** | Giới hạn phạm vi router mà multicast IPv4 có thể đi qua; không phải timeout |

**Một datagram gửi tới group IP và port không tự tạo membership ở bên nhận.** Bên nhận cần **bind socket**, rồi **joinGroup** trên interface phù hợp; mạng/OS có thể vẫn lọc hoặc không route datagram. Ngược lại, **joinGroup** không hề tạo một kết nối TCP hoặc làm tất cả mạng ngoài Internet nhận được datagram.

## 2. MulticastSocket là UDP socket có khả năng quản lý nhóm

**MulticastSocket** kế thừa **DatagramSocket**: làm việc với **datagram**, không có byte stream, handshake TCP, **accept()**, **connect()** theo nghĩa thiết lập kết nối TCP hay đảm bảo độ tin cậy. Các lệnh chính:

- **new MulticastSocket(port)**: tạo/bind một UDP socket vào **port** được chọn, phù hợp khi muốn nhận datagram ở cổng thống nhất.
- **new MulticastSocket(null)**: tạo socket **chưa bind**; thuận tiện để gọi **setReuseAddress(true)** và các option khác trước **bind(...)**.
- **bind(SocketAddress)**: đặt local address và UDP port để socket nhận datagram.
- **joinGroup(SocketAddress group, NetworkInterface netIf)**: đăng ký nhận **nhóm trên interface** cụ thể.
- **receive(DatagramPacket)**: đợi một UDP datagram, copy dữ liệu vào buffer, cập nhật độ dài và địa chỉ nguồn.
- **send(DatagramPacket)**: gửi datagram tới group/port đã đặt trong packet.
- **leaveGroup(SocketAddress group, NetworkInterface netIf)**: rời đúng nhóm/interface đã tham gia.
- **setNetworkInterface(NetworkInterface)**: chọn **interface cho các multicast packet GỬI RA** từ socket.
- **setTimeToLive(int)**: đặt TTL multicast (0–255) cho các packet **gửi đi**.
- **setSoTimeout(int)**: đặt timeout cho **receive()**, không biến UDP thành giao thức tin cậy.

API **joinGroup(InetAddress)** và **leaveGroup(InetAddress)** đã được đánh dấu **deprecated** từ Java 14 vì không chỉ rõ interface; không nên dựa vào interface mà OS tự chọn khi có nhiều card mạng, VPN hoặc container. Hãy ưu tiên overload **(SocketAddress, NetworkInterface)**.

### Tại sao joinGroup nhận SocketAddress chứ không chỉ InetAddress?

Theo Javadoc **MulticastSocket.joinGroup(SocketAddress, NetworkInterface)**, đối số thứ nhất chỉ **địa chỉ IP nhóm**; cách dùng SocketAddress mang tính lịch sử, và implementation mặc định chỉ hỗ trợ **InetSocketAddress**. **Giá trị port trong đối số joinGroup được bỏ qua**. Ví dụ:

~~~java
InetAddress group = InetAddress.getByName("239.255.42.99");
InetSocketAddress membership = new InetSocketAddress(group, 0);
receiver.joinGroup(membership, networkInterface);
~~~

Cổng **0** trong **membership** ở đây không bảo receiver bind cổng 0 và cũng **không** định nghĩa cổng nhận. Nó chỉ là cách tạo **SocketAddress** chứa địa chỉ nhóm cho lệnh join. **Cổng nhận thật** được xác định bởi **receiver.bind(..., port)** hoặc constructor **new MulticastSocket(port)**.

Đây là khác biệt rất quan trọng:

~~~text
new MulticastSocket(50000)
   └─ bind UDP local port 50000

joinGroup(new InetSocketAddress(group, 0), netIf)
   └─ join group IP trên netIf; port 0 ở đây bị bỏ qua

sender.send(DatagramPacket(..., group, 50000))
   └─ gửi UDP datagram tới group IP, UDP destination port 50000
~~~

Hai nơi xuất hiện số cổng có vai trò khác nhau; người nhận cần bind đúng cổng datagram thực sự đến.

## 3. Chọn NetworkInterface chính xác

**java.net.NetworkInterface** đại diện cho một giao diện mạng do OS quản lý. Một interface có thể có nhiều địa chỉ IP, kể cả cả IPv4 và IPv6. Không nên nhầm **NetworkInterface** với **InetAddress**:

- **InetAddress** là địa chỉ IP, ví dụ **192.168.1.15** hoặc **fe80::...**.
- **NetworkInterface** là đối tượng đại diện interface như **eth0**, **en0**, adapter Wi-Fi hoặc virtual NIC; được nhận diện qua tên/index tùy hệ điều hành.
- **InetAddress của nhóm** (ví dụ **239.255.42.99**) không phải IP gán cho interface, nên không thể dùng **NetworkInterface.getByInetAddress(group)** để tìm interface nhận. Hàm đó tìm interface cục bộ được **gán** đúng địa chỉ IP truyền vào, thường dùng với IP unicast.

### Có biết sẵn tên interface

~~~java
NetworkInterface netIf = NetworkInterface.getByName("eth0");
if (netIf == null || !netIf.isUp() || !netIf.supportsMulticast()) {
    throw new IllegalStateException("Interface không khả dụng cho multicast");
}
~~~

Đây là **snippet**, cần import **java.net.NetworkInterface** và xử lý **SocketException**. Tên **eth0** chỉ là ví dụ Linux; trên Windows/macOS hoặc container tên có thể khác. Cần kiểm tra interface có **địa chỉ đúng họ IP** của nhóm: chọn IPv4 interface cho group IPv4, IPv6 interface cho group IPv6. **supportsMulticast()** cho biết khả năng mà OS báo, nhưng không bảo đảm mọi router, switch, firewall hoặc ứng dụng bên kia sẽ truyền datagram.

### Không biết trước tên interface

Có thể liệt kê interface rồi chọn interface đang hoạt động, hỗ trợ multicast, có một **IPv4 unicast** phù hợp với nơi cần gửi/nhận. Ví dụ Java 17+ sau (được tích hợp trong chương trình hoàn chỉnh bên dưới):

~~~java
static NetworkInterface findInterface() throws SocketException {
    Enumeration<NetworkInterface> en = NetworkInterface.getNetworkInterfaces();
    while (en.hasMoreElements()) {
        NetworkInterface ni = en.nextElement();
        if (!ni.isUp() || !ni.supportsMulticast() || ni.isLoopback()) {
            continue;
        }
        Enumeration<InetAddress> addrs = ni.getInetAddresses();
        while (addrs.hasMoreElements()) {
            InetAddress a = addrs.nextElement();
            if (a instanceof Inet4Address && !a.isLoopbackAddress()) {
                return ni;
            }
        }
    }
    return null;
}
~~~

Đây là **phương thức được tách từ chương trình đầy đủ**, không phải một file Java chạy độc lập. Nó chọn **interface đầu tiên phù hợp với tiêu chí kỹ thuật**, không biết trước interface nào sẽ kết nối đến những host mục tiêu. Trên máy có Ethernet, Wi-Fi, VPN, Docker adapter hoặc nhiều subnet, **chọn interface đầu tiên có thể sai**. Trong production, nên cho cấu hình chọn interface theo tên/index hoặc IP cục bộ, và kiểm tra đường mạng/thử nhận thực tế. Nếu có nhiều interface cùng gán một IP, **getByInetAddress(...)** không bảo đảm chọn một interface cụ thể; chọn bằng cấu hình/index rõ ràng an toàn hơn.

**Loopback interface** cũng có thể hỗ trợ multicast trên một số hệ điều hành, nhưng không phải mọi nơi. Demo bên dưới ưu tiên **non-loopback IPv4 interface** để giảm phụ thuộc vào khả năng multicast của adapter loopback. Điều đó không có nghĩa packet sẽ rời host: sender bật cơ chế multicast loopback để bản sao có thể được đưa về local receiver.

## 4. Join nhóm để NHẬN: bind socket và chỉ rõ interface

Quy trình bên nhận chuẩn:

1. Chọn **group IP** thuộc dải multicast hợp lệ cho ứng dụng.
2. Chọn **UDP port** của protocol, thống nhất với sender.
3. Chọn **NetworkInterface** cục bộ thực sự dùng để nhận trên mạng tương ứng.
4. Tạo **MulticastSocket**, cấu hình **SO_REUSEADDR** trước bind nếu cần nhiều receiver cùng cổng và OS hỗ trợ.
5. **bind** vào local UDP port; thường bind wildcard thay vì bind trực tiếp vào group IP.
6. **joinGroup(new InetSocketAddress(group, 0), netIf)**.
7. **receive(DatagramPacket)** trong loop và xử lý từng datagram; khi dừng, **leaveGroup** rồi **close**.

~~~java
// Snippet minh họa: group, netIf đã được chọn/kiểm tra; imports và xử lý lỗi cần có.
int port = 50000;
try (MulticastSocket receiver = new MulticastSocket(null)) {
    receiver.setReuseAddress(true); // Đặt trước bind nếu cần dùng chung cổng.
    receiver.bind(new InetSocketAddress(
            InetAddress.getByName("0.0.0.0"), port));
    receiver.setSoTimeout(3_000);

    InetSocketAddress membership = new InetSocketAddress(group, 0);
    receiver.joinGroup(membership, netIf);
    try {
        byte[] buffer = new byte[2048];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        receiver.receive(packet);
        System.out.println("payloadLength=" + packet.getLength());
    } finally {
        receiver.leaveGroup(membership, netIf);
    }
}
~~~

**Đây là snippet**, không có định nghĩa **group/netIf** và không bảo đảm có sender. Với UDP, **receive()** chỉ đọc **một datagram tại một lần gọi**; nếu datagram lớn hơn buffer nhận, dữ liệu có thể bị cắt. Cần dùng **packet.getLength()** và **packet.getOffset()** thay vì đọc toàn bộ **buffer.length** như payload.

**SO_REUSEADDR** có thể hữu ích khi nhiều receiver cùng bind một port và join cùng nhóm, nhưng điều kiện bind/deliver giữa các socket vẫn **phụ thuộc OS**. Không suy ra rằng hai process luôn được nhận bản sao giống nhau trong mọi cấu hình. Java **MulticastSocket** constructor đã bật reuse address mặc định; minh họa trên gọi setter một lần nữa để làm rõ **thời điểm trước bind**, thay vì phụ thuộc vào việc setter chạy sau bind.

### Vì sao không bind trực tiếp vào group IP?

Group IP là đích multicast, không phải địa chỉ unicast được gán cho interface như một IP máy thông thường. Một số môi trường có cách bind group-specific được hỗ trợ, nhưng **bind wildcard vào UDP port rồi join group/interface** là mẫu dễ dùng và dễ di động hơn. Ví dụ dùng **0.0.0.0** cho một socket IPv4 để nhận trên các local interface thích hợp, còn lệnh **joinGroup(...)** xác định **nhóm cụ thể và interface cụ thể** cần đăng ký.

### Khi join không chỉ rõ interface

Truyền **null** làm **netIf** sẽ khiến Java dựa vào interface đã đặt cho hướng gửi hoặc vào behavior của OS. Nếu chưa có interface được đặt, Javadoc nói interface được chọn có thể **không xác định**, thậm chí thao tác thất bại. Trên host có nhiều NIC, nên truyền **NetworkInterface** rõ ràng khi join và leave; không dùng các overload deprecated để “cho hệ thống chọn đại”.

**joinGroup không phải hàm idempotent:** thử join lại cùng group/interface trên cùng socket có thể ném **IOException**. Tương tự, **leaveGroup** với membership chưa join cũng có thể ném lỗi. Tổ chức một vòng đời join/leave rõ ràng và chỉ leave sau khi join thành công.

## 5. GỬI multicast: chọn interface, TTL và loopback

Bên gửi chỉ cần tạo UDP datagram có **destination group IP + destination UDP port**. **Sender không nhất thiết phải là thành viên nhóm**. Nếu máy có nhiều interface, đặt interface gửi một cách tường minh:

~~~java
// Snippet: netIf, group và port đã được định nghĩa.
try (MulticastSocket sender = new MulticastSocket()) {
    sender.setNetworkInterface(netIf); // Chọn đường gửi multicast.
    sender.setTimeToLive(1);           // TTL IPv4: giới hạn số hop router.
    sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

    byte[] message = "hello multicast".getBytes(StandardCharsets.UTF_8);
    DatagramPacket packet =
            new DatagramPacket(message, message.length, group, port);
    sender.send(packet);
}
~~~

Đây là **snippet**, cần import **java.net.\*** và **java.nio.charset.StandardCharsets**, cùng xử lý ngoại lệ. **setNetworkInterface(netIf)** tác động đến **multicast gửi ra**; nó **không** thay cho **receiver.joinGroup(membership, netIf)** để đăng ký nhận. Bên gửi và bên nhận nằm trên cùng một host có thể cần cùng interface và cho phép multicast loopback, nhưng **không có bảo đảm** rằng mọi OS/network driver sẽ chuyển datagram về chính host đó.

**TTL không phải timeout:** **setTimeToLive(1)** đặt giá trị IPv4 TTL trên packet gửi, thường chỉ cho phép lan truyền trong mạng cục bộ và không được router chuyển tiếp xa. Giá trị lớn hơn chỉ tăng *khả năng* đi xa; router vẫn cần được cấu hình multicast routing, policy cho phép và phạm vi group phù hợp. Với IPv6, tham số tương ứng thường được diễn giải dưới dạng **hop limit** và có thêm vấn đề scope/interface.

**IP_MULTICAST_LOOP** là cờ điều khiển việc vòng lại các multicast packet **gửi đi** để các receiver cùng host có thể nhận chúng. Giá trị **true** cho phép loopback, nhưng không bảo đảm local delivery khi OS hoặc chính sách network chặn. API cũ **MulticastSocket.setLoopbackMode(boolean disable)** đã deprecated và tham số có **nghĩa đảo** (true = disable); hãy ưu tiên **setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true/false)**.

### Hai câu hỏi khác nhau

| Câu hỏi | Tùy chọn/cách làm |
| --- | --- |
| Tôi muốn **nhận** group G trên interface I? | **receiver.joinGroup(new InetSocketAddress(G, 0), I)** |
| Tôi muốn **gửi ra** qua interface I? | **sender.setNetworkInterface(I)** hoặc **IP_MULTICAST_IF** |
| Tôi muốn nhận UDP trên port P? | **receiver.bind(new InetSocketAddress(..., P))** |
| Tôi muốn gửi tới port P? | **DatagramPacket(..., G, P)** |
| Tôi muốn tránh chờ mãi khi không có datagram? | **receiver.setSoTimeout(ms)** rồi xử lý **SocketTimeoutException** |
| Tôi muốn local receiver cùng host nhận packet do local sender gửi? | Kiểm tra **IP_MULTICAST_LOOP**, interface, firewall và OS support |

## 6. Chương trình Java 17+ hoàn chỉnh: join, send, receive, leave

Chương trình này là **một demo tự chạy trên cùng máy**. Nó tìm interface IPv4 đang hoạt động có hỗ trợ multicast, tạo receiver chưa bind, bind vào port **0** để OS cấp một UDP port còn trống, join group **239.255.42.99** trên interface ấy, rồi tạo sender gửi tới **group:actualPort**. Receiver thử đọc trong **1,5 giây** và cuối cùng leave đúng membership.

**Vì sao dùng port 0 ở demo?** Sender và receiver nằm trong cùng JVM nên có thể dùng trực tiếp **receiver.getLocalPort()**, không cần trao đổi cổng ngoài chương trình. Khi chạy **hai process hoặc hai host riêng**, họ **phải thống nhất port nhận trước** (ví dụ 50000); không thể để mỗi receiver chọn port ngẫu nhiên mà sender không biết. Địa chỉ nhóm và interface vẫn cần phù hợp với chính sách mạng.

Tạo file **MulticastJoinDemo.java**:

~~~java
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

public class MulticastJoinDemo {
    static NetworkInterface findInterface() throws SocketException {
        Enumeration<NetworkInterface> en = NetworkInterface.getNetworkInterfaces();
        while (en.hasMoreElements()) {
            NetworkInterface ni = en.nextElement();
            if (!ni.isUp() || !ni.supportsMulticast() || ni.isLoopback()) continue;
            Enumeration<InetAddress> addrs = ni.getInetAddresses();
            while (addrs.hasMoreElements()) {
                InetAddress a = addrs.nextElement();
                if (a instanceof Inet4Address && !a.isLoopbackAddress()) return ni;
            }
        }
        return null;
    }

    public static void main(String[] args) throws Exception {
        NetworkInterface ni = findInterface();
        if (ni == null) {
            System.out.println("No IPv4 multicast-capable interface");
            return;
        }
        System.out.println("selectedInterface=" + ni.getName());
        InetAddress group = InetAddress.getByName("239.255.42.99");
        InetSocketAddress membership = new InetSocketAddress(group, 0);

        try (MulticastSocket receiver = new MulticastSocket(null);
             MulticastSocket sender = new MulticastSocket()) {
            receiver.setReuseAddress(true);
            receiver.bind(new InetSocketAddress(
                    InetAddress.getByName("0.0.0.0"), 0));
            receiver.setSoTimeout(1500);
            receiver.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            sender.setNetworkInterface(ni);
            sender.setTimeToLive(1);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

            receiver.joinGroup(membership, ni);
            try {
                System.out.println("joined=true");
                int port = receiver.getLocalPort();
                System.out.println("assignedPortValid=" + (port > 0));
                byte[] payload = "hello multicast".getBytes(StandardCharsets.UTF_8);
                sender.send(new DatagramPacket(payload, payload.length, group, port));

                DatagramPacket packet = new DatagramPacket(new byte[2048], 2048);
                try {
                    receiver.receive(packet);
                    System.out.println("received=" + new String(
                            packet.getData(), packet.getOffset(), packet.getLength(),
                            StandardCharsets.UTF_8));
                } catch (SocketTimeoutException e) {
                    System.out.println("receiveTimedOut=true");
                }
            } finally {
                receiver.leaveGroup(membership, ni);
                System.out.println("left=true");
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 MulticastJoinDemo.java
java MulticastJoinDemo
~~~

**Một stdout thực tế đã kiểm chứng trên JDK 24 (biên dịch với --release 17):**

~~~text
selectedInterface=ethernet_32769
joined=true
assignedPortValid=true
received=hello multicast
left=true
~~~

Tên interface là **phụ thuộc máy** và không phải giá trị cố định. Trên máy khác, một trong các tình huống có thể xảy ra:

- Không tìm được interface IPv4 thích hợp: chương trình in **No IPv4 multicast-capable interface** và kết thúc.
- Join/send thành công nhưng packet không được local network stack chuyển về receiver: in **receiveTimedOut=true** thay cho dòng **received=...**, rồi **left=true**.
- OS/firewall/policy từ chối thao tác network: có thể ném **IOException** hoặc **SocketException**; đây là dấu hiệu hạn chế môi trường chứ không chứng minh cú pháp API sai.

### Đọc code theo từng bước

1. **findInterface()** kiểm tra **isUp()**, **supportsMulticast()**, **isLoopback()** và sự tồn tại của IPv4 unicast trên interface. Logic này phù hợp để thử demo, chưa đủ để quyết định tuyến mạng production.
2. **new MulticastSocket(null)** tạo receiver **chưa bind**, cho phép cấu hình trước bind. **new MulticastSocket()** ở sender có thể bind một local port bất kỳ để gửi.
3. **receiver.bind(0.0.0.0:0)** yêu cầu OS cấp một **UDP port** cho receiver. Receiver chỉ nhận datagram gửi tới đúng port này (theo socket/IP routing rules), không phải mọi port của group.
4. **membership = new InetSocketAddress(group, 0)** đại diện nhóm để join; **port 0 tại membership bị API bỏ qua**, khác với cổng đã cấp tại receiver.
5. **receiver.joinGroup(membership, ni)** đăng ký nhóm trên interface đã chọn; **sender.setNetworkInterface(ni)** chọn interface phát multicast.
6. **sender.setTimeToLive(1)** hạn chế phạm vi multicast. **IP_MULTICAST_LOOP=true** cho phép test sender/receiver cùng host trong hệ thống hỗ trợ.
7. **sender.send(...)** gửi UDP datagram chứa byte UTF-8 của **hello multicast** tới **group + receiver.getLocalPort()**.
8. **receiver.receive(packet)** đợi một datagram; khi nhận, dùng **getOffset()/getLength()** để tránh biến byte thừa trong buffer thành nội dung. Nếu quá 1,5 giây không có packet, **SocketTimeoutException** được xử lý như timeout bình thường.
9. **finally** gọi **receiver.leaveGroup(membership, ni)** đúng group/interface đã join, sau đó **try-with-resources** đóng các socket.

**Điểm cần kiểm chứng:** test thành công cùng host chưa chứng minh multicast đi được sang một host khác hay VLAN khác. Cần test tiếp với máy gửi/máy nhận ở mạng thực và kiểm tra switch/router/firewall.

## 7. Khi chạy sender và receiver ở hai tiến trình hoặc hai máy

Với hai tiến trình độc lập, hãy thống nhất cấu hình **group IP = 239.255.42.99** và **UDP port = 50000** (chỉ là cấu hình ví dụ), rồi thay **receiver.bind(..., 0)** bằng bind **50000**. Sender gửi packet tới group **239.255.42.99:50000**. Mỗi process chọn **NetworkInterface của chính máy đó**, không dùng tên interface của máy còn lại.

~~~text
Receiver trên Host A: 0.0.0.0:50000 + join 239.255.42.99 trên NIC_A
Receiver trên Host B: 0.0.0.0:50000 + join 239.255.42.99 trên NIC_B
Sender   trên Host C: UDP → 239.255.42.99:50000 qua NIC_C

Điều kiện mạng: NIC_A/B/C ở nơi multicast có thể tới;
                 firewall, switch, route và group scope phù hợp.
~~~

**Địa chỉ nhóm** không thay thế địa chỉ IP cục bộ. Không yêu cầu hai máy có cùng tên NIC; chỉ cần mỗi máy chọn interface nằm trên mạng multicast phù hợp. Nếu cả hai receiver ở **cùng máy** và muốn cùng bind port 50000, thường cần **SO_REUSEADDR trước bind**, nhưng liệu cả hai nhận datagram hay không phụ thuộc OS và chính sách UDP socket. Không dùng các kết quả trên một hệ điều hành để khẳng định cho mọi hệ.

### Gợi ý cấu hình rõ ràng

Đối với ứng dụng production, đừng cố chọn “interface đầu tiên”. Có thể cho các tham số:

~~~properties
multicast.group=239.255.42.99
multicast.port=50000
multicast.interface=eth0
multicast.ttl=1
multicast.receiveTimeoutMs=3000
~~~

Đây là **mẫu cấu hình**, không phải file Java bắt buộc. Khi chạy, cần xác minh interface **eth0** thực sự tồn tại, đang up, hỗ trợ multicast và có IP phù hợp. **Port** phải nằm trong dải 1..65535 khi cả hai tiến trình cần biết trước. Chọn group/port tránh xung đột ứng dụng khác và tuân thủ chính sách mạng của tổ chức.

Nếu không biết IP cục bộ, có thể dùng **NetworkInterface.getByName(...)** hoặc **getByIndex(...)** khi cấu hình rõ. Với IPv6, địa chỉ nhóm IPv6 phải gắn với scope phù hợp và có thể cần interface index; không thể chỉ thay group IPv4 thành một chuỗi IPv6 mà giữ nguyên toàn bộ assumptions về IPv4 wildcard, route và TTL.

## 8. TTL, phạm vi địa chỉ nhóm, IGMP/MLD và network infrastructure

### Địa chỉ multicast hợp lệ

- **IPv4 multicast** thuộc **224.0.0.0/4**. Đây là các địa chỉ **nhóm** chứ không phải IP unicast. Có thể dùng **InetAddress.isMulticastAddress()** để kiểm tra loại địa chỉ.
- Khối **224.0.0.0/24** có nhiều địa chỉ điều khiển cục bộ của giao thức mạng; không chọn bừa một địa chỉ trong đó cho ứng dụng thông thường.
- **239.0.0.0/8** là **administratively scoped multicast** dùng trong các miền quản trị. Group **239.255.42.99** trong ví dụ chỉ là lựa chọn minh họa, cần phối hợp để tránh trùng group và port trong tổ chức.
- **IPv6 multicast** có prefix **ff00::/8**, kèm scope. Cần chú ý khác biệt với IPv4, nhất là link-local interface và scope ID.

Một địa chỉ hợp lệ về cú pháp **chưa bảo đảm** switch/router sẽ gửi packet tới các receiver. OS thường dùng **IGMP** (IPv4) hoặc **MLD** (IPv6) để quản lý membership trên mạng. Switch có thể bật **IGMP snooping**, router có thể không bật multicast routing, Wi-Fi access point hoặc VPN có thể lọc multicast. Nhiều môi trường cloud/container không hỗ trợ multicast như một LAN truyền thống.

### TTL/hop limit không thay thế routing

**TTL=1** thường dùng cho bài thực hành trong một local subnet; packet đi qua router tiêu thụ TTL và bị chặn nếu không đủ. Nhưng **tăng TTL** không tự kích hoạt multicast routing và không bỏ qua firewall. Đối với multicast xuyên subnet cần sự hỗ trợ cấu hình của các thiết bị trung gian và chính sách địa chỉ nhóm.

### Multicast loopback không phải loopback interface

Hai khái niệm độc lập:

- **Loopback network interface** (**lo**, **127.0.0.1**, **::1**) là interface nội bộ của host; nó có thể hoặc không thể hỗ trợ multicast tùy OS.
- **IP_MULTICAST_LOOP** cho phép OS cấp bản sao của packet multicast **do host tự gửi** về các listener cùng host khi điều kiện phù hợp; sender vẫn có thể chọn interface Ethernet/Wi-Fi.

Nhầm hai khái niệm này thường khiến người học bind vào **127.0.0.1** rồi mong nhận mọi packet multicast đi vào NIC vật lý.

## 9. Chẩn đoán sự cố join/send/receive

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| **joinGroup** ném lỗi vì địa chỉ | Group không thuộc multicast range hoặc họ IP không phù hợp | Kiểm tra **group.isMulticastAddress()**, IPv4/IPv6 và interface |
| **NetworkInterface.getByName(...) == null** | Tên interface không tồn tại trên host | Liệt kê **NetworkInterface.getNetworkInterfaces()**, cấu hình đúng tên/index |
| **supportsMulticast() == false** | Driver/OS/interface không hỗ trợ multicast | Chọn interface khác, xem chính sách môi trường |
| **joinGroup** thất bại dù interface up | OS/network stack không hỗ trợ hoặc policy từ chối | Log exception, interface, group family và quyền |
| Sender gửi không lỗi nhưng receiver timeout | Sai **port**, group, interface, TTL, firewall, IGMP, loopback hoặc mạng không deliver | Log 5 yếu tố **group, port, bind, join interface, send interface** |
| Hai process dùng port 0 riêng | Sender không biết port receiver | Dùng UDP port cố định hoặc service discovery trao đổi port thật |
| Một receiver đọc được, receiver khác không | Khác interface/subnet/OS bind semantics hoặc group registration | Kiểm tra join trên từng host và SO_REUSEADDR trước bind |
| Nhận datagram nhưng text có ký tự rác | Decode cả buffer thay vì phần packet | Dùng **getOffset()** và **getLength()** khi tạo String |
| Gửi packet lớn nhưng nhận thiếu | Buffer quá nhỏ hoặc IP fragmentation/loss | Tăng buffer nhận phù hợp, tránh datagram quá lớn, thêm framing/checksum ứng dụng |
| Chạy Docker/VM không nhận multicast | Bridge/virtual NIC/filtering không chuyển multicast | Kiểm tra network mode, switch ảo, VLAN và policy |
| Hoạt động cùng host nhưng không qua router | Router chưa cấu hình multicast hoặc TTL/scope không đúng | Đo packet capture và xác minh multicast routing |

**Quy trình debug ngắn:**

1. Log **group IP**, **destination UDP port**, **receiver local bind**, **receiver NetworkInterface name/index/IP**, **sender outbound interface** và **TTL**; bảo đảm hai bên nhất quán.
2. Kiểm tra **group.isMulticastAddress()**, interface **isUp()/supportsMulticast()**, họ IPv4/IPv6 và địa chỉ cục bộ thực tế. Tránh lấy **NetworkInterface.getByInetAddress(group)** vì group không phải IP của NIC.
3. Trên cùng host, thử **IP_MULTICAST_LOOP=true**, cùng interface, và **setSoTimeout** để tránh treo vô hạn. Nếu môi trường không hỗ trợ multicast, chuyển sang một LAN kiểm thử có cấu hình phù hợp.
4. Với hai host, quan sát packet ở sender và receiver bằng công cụ capture phù hợp; kiểm tra firewall, switch snooping, IGMP/MLD, wireless multicast suppression và router.
5. Nếu cần nhiều process cùng nhận một group: kiểm tra **SO_REUSEADDR** trước bind, nhưng không giả định OS sẽ deliver giống nhau trên mọi nền tảng.
6. Kiểm tra packet length/truncation và protocol payload; một packet đến đúng port chưa chắc thuộc message hợp lệ của ứng dụng.
7. Thêm application-level sequence number, source ID, timestamp và metrics drop/duplicate/out-of-order khi cần đánh giá độ tin cậy.

Với môi trường test tự động, việc yêu cầu **receive() luôn thành công** làm test dễ flaky. Có thể tách test thành: (a) Java API compile + cấu hình group/interface, (b) integration test multicast trên môi trường network được kiểm soát, và (c) protocol parser test bằng dữ liệu giả lập. Đừng “sửa” test bằng cách bỏ qua lỗi network không rõ nguyên nhân; cần log đầy đủ điều kiện môi trường.

## 10. Độ tin cậy, an toàn và trách nhiệm của ứng dụng

Multicast qua UDP có các giới hạn nền tảng:

- **Không bảo đảm delivery, ordering, uniqueness**: packet có thể bị mất, lặp hoặc đến không theo thứ tự. **joinGroup** là đăng ký nhận, không phải một lời hứa hệ thống sẽ phát lại packet đã gửi trước đó.
- **Không có flow control theo từng receiver** như TCP: người gửi có thể vượt khả năng xử lý của một số receiver; datagram có thể bị drop mà không thông báo riêng.
- **Không có bảo mật tự động**: ai có khả năng tham gia network/group có thể gửi datagram; ứng dụng cần kiểm tra nguồn theo threat model, xác thực integrity/message và mã hóa nếu dữ liệu nhạy cảm.
- **Không phải kênh phát ra Internet toàn cầu**: multicast routing, admin scope và firewall quyết định phạm vi thực.
- **Datagram size** bị giới hạn bởi UDP/IP và MTU; packet lớn có thể cần fragmentation và dễ mất hơn khi một mảnh bị drop. Tránh dùng multicast UDP để gửi payload khổng lồ mà không có thiết kế giao thức và phục hồi thích hợp.
- **Tính ngắn hạn của membership**: khi socket đóng hoặc mạng/interface đổi trạng thái, cần tái lập membership khi app phục hồi; không mặc định trạng thái cũ còn hiệu lực.

Một bản tin ứng dụng nên có **version, message type, sender ID, sequence number, payload length và checksum/authentication** nếu điều kiện sử dụng yêu cầu. Mọi decoder phải giới hạn input và xử lý byte thiếu/hỏng. Nếu hệ thống đòi hỏi bảo đảm giao tận nơi và retransmission, cân nhắc unicast/TCP hoặc protocol reliable multicast chuyên dụng thay vì giả định multicast UDP làm được sẵn.

## 11. Tránh các lỗi API phổ biến

| Cách nghĩ sai | Thực tế cần nhớ |
| --- | --- |
| Truyền **InetAddress.getLocalHost()** làm group để join | Địa chỉ local host thường là **unicast**, không phải multicast group |
| Dùng **NetworkInterface.getByInetAddress(group)** để tìm NIC | Group IP không phải IP gán cho card mạng; chọn NIC theo địa chỉ unicast/name/index |
| **joinGroup(new InetSocketAddress(group, 50000), ni)** tự bind UDP port 50000 | Port trong tham số join **bị bỏ qua**; phải bind receiver riêng |
| **setNetworkInterface(ni)** đủ để nhận multicast | Setter chọn interface gửi; receiver vẫn cần **joinGroup(...)** |
| MulticastSocket tự join mọi group | Không; phải join từng group/interface mong muốn |
| **setTimeToLive(1)** bảo đảm gửi đến mọi host trong LAN | Không; còn interface, switch, IGMP, firewall, Wi-Fi policy |
| **receive()** luôn trả một chuỗi hoàn chỉnh | UDP nhận một datagram nhưng buffer có thể cắt, payload có thể là binary; cần length/protocol |
| **setSoTimeout(...)** bảo đảm packet đến đúng giờ | Chỉ giới hạn thời gian chờ receive và ném timeout |
| Sender phải join group mới gửi được | Không; sender không nhất thiết là thành viên |
| Multicast luôn có thể dùng trong Docker/cloud | Không; nhiều mạng ảo lọc/chặn multicast |
| Đóng socket mà không leave là “tương đương về mặt chương trình” | OS thường giải phóng membership khi đóng, nhưng **leaveGroup trong finally** thể hiện đúng vòng đời khi còn dùng socket |
| Multicast an toàn vì chỉ vài người biết group | Group/port không phải bảo mật hay cơ chế xác thực |

## 12. Checklist và bài tập tự kiểm tra

**Checklist bên nhận:**

1. Chọn **group IP** hợp lệ và không xung đột phạm vi sử dụng; kiểm tra **isMulticastAddress()**.
2. Thống nhất **destination UDP port**; receiver phải **bind** đúng port.
3. Chọn **NetworkInterface** thực sự có đường đến mạng multicast, đang up, hỗ trợ multicast, cùng họ IP với group.
4. Dùng **joinGroup(new InetSocketAddress(group, 0), ni)** (không dùng overload deprecated khi cần chọn interface).
5. Cấu hình **receive timeout** hoặc cơ chế shutdown để thread không treo; dùng đủ bộ đệm và đọc **getLength()**.
6. **leaveGroup(membership, ni)** trong **finally**, rồi đóng socket bằng try-with-resources.
7. Đo delivery thực tế; nếu mạng không hỗ trợ, đừng kết luận chỉ từ việc setter/join không ném lỗi.

**Checklist bên gửi:**

1. Dùng đúng **group IP + destination port** mà receiver đang lắng nghe.
2. Chọn outbound interface bằng **setNetworkInterface(ni)** hoặc socket option tương ứng.
3. Đặt TTL/hop scope phù hợp, dùng **IP_MULTICAST_LOOP** nếu thử cùng host.
4. Đóng gói message với version/length/sequence và các kiểm tra cần thiết; xử lý lỗi gửi mà không coi **send()** là acknowledgment của người nhận.

**Bài tập:**

1. Vì sao cùng một **239.255.42.99:50000** vẫn cần chọn **NetworkInterface khác nhau** trên hai host?
2. Trong **joinGroup(new InetSocketAddress(group, 0), ni)**, port 0 có nghĩa gì? Nó có làm sender phải gửi tới port 0 không?
3. Server receiver bind **UDP 50000** và join **239.255.42.99** trên Wi-Fi. Sender gửi group đúng nhưng qua Ethernet, receiver không nhận. Hãy nêu những khác biệt mạng có thể liên quan và thứ tự kiểm tra.
4. Nếu máy có ba interface đều hỗ trợ multicast, tại sao chọn “interface đầu tiên” không phải lựa chọn production tốt?
5. Tại sao **setNetworkInterface(ni)** ở sender không thay được **joinGroup(membership, ni)** ở receiver?
6. Viết biến thể dùng **new MulticastSocket(50000)** và **joinGroup(...)**; thử hai receiver trên cùng host và ghi nhận kết quả phụ thuộc OS của bạn.
7. Nếu một datagram 3 KiB tới receiver đang dùng buffer 2 KiB, điều gì có thể xảy ra? Nên thiết kế protocol thế nào để phát hiện message thiếu?
8. Một hệ thống yêu cầu mọi node đều nhận **chắc chắn một lần** và xác nhận xử lý. Vì sao không thể giải quyết yêu cầu đó chỉ bằng **MulticastSocket**?
9. Thử bật và tắt **IP_MULTICAST_LOOP** cho sender, giữ nguyên group/interface/port, sau đó so sánh kết quả trên máy của bạn và giải thích khác biệt với loopback NIC.

**Tóm tắt:** **Group IP** xác định đối tượng logic cần nhận, **UDP port** xác định cổng ứng dụng đang lắng nghe, **NetworkInterface** xác định đường mạng nơi thực hiện membership. **joinGroup(group, netIf)** là hành động của **receiver**; **setNetworkInterface(netIf)** là lựa chọn **đường gửi**; hai vai trò khác nhau. Phải đồng bộ group và port, kiểm tra interface và giới hạn mạng, dùng **leaveGroup** đúng vòng đời, và nhớ rằng multicast UDP là **best effort**.

**Tài liệu gốc:** [MulticastSocket — Java SE 21 Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/MulticastSocket.html), [NetworkInterface — Java SE 21 Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/NetworkInterface.html), [DatagramPacket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramPacket.html), [StandardSocketOptions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardSocketOptions.html) và [DatagramChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/DatagramChannel.html).