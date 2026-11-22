# Multicast khác với unicast và broadcast về cách chọn bên nhận

## 1. Cùng là gửi dữ liệu mạng, nhưng “gửi cho ai?” là ba bài toán khác nhau

Giả sử một ứng dụng Java có **một nguồn phát** muốn đưa bản tin tới nhiều máy. Có ít nhất ba cách xác định đối tượng nhận ở lớp địa chỉ mạng:

- **Unicast:** gửi tới **một địa chỉ đích unicast**. Ví dụ client gửi yêu cầu cho một server. Muốn gửi cùng một nội dung cho nhiều đích, ứng dụng thường phải gửi nhiều lần, hoặc sử dụng một dịch vụ trung gian để phân phối.
- **Broadcast:** gửi tới **miền broadcast** được xác định bởi địa chỉ/đường truyền. Trong IPv4, bản tin broadcast có thể được các thiết bị thuộc miền đó tiếp nhận mà **không cần đăng ký một nhóm ứng dụng cụ thể**. Broadcast không có nghĩa “mọi máy trên Internet”.
- **Multicast:** gửi tới **địa chỉ nhóm (group address)**. Các máy muốn tham gia sẽ đăng ký nhận lưu lượng của nhóm trên giao diện mạng thích hợp; mạng có thể phân phối và nhân bản gói ở những nơi cần thiết để tiếp cận các thành viên.

Khác biệt cốt lõi không chỉ là **một–một**, **một–nhiều** hay **một–tất cả** theo cách gọi tắt, mà là **người gửi chọn đích bằng loại địa chỉ nào, máy nhận được xác định như thế nào và phạm vi lan truyền ra sao**.

Ví dụ một ứng dụng phát trạng thái tới bốn máy A, B, C, D:

- Muốn gửi riêng cho B: dùng **unicast** tới địa chỉ IP của B.
- Muốn gửi tới miền mạng cục bộ của A, B, C: có thể dùng **IPv4 broadcast** theo phạm vi và cấu hình mạng phù hợp; D ở mạng khác không mặc nhiên nhận.
- Muốn gửi tới những máy **đã tham gia nhóm G**: dùng **multicast** tới địa chỉ nhóm G. Nếu A và C tham gia G còn B không tham gia, thì A/C là các đích thuộc nhóm; B không tự động được chọn chỉ vì ở cùng mạng.

Bài học tập trung vào **cơ chế chọn bên nhận**, đồng thời liên hệ cách gửi qua UDP/IP và API Java 17+ để tránh đánh đồng địa chỉ đích với kết quả ứng dụng nhận được.

## 2. So sánh unicast, broadcast, multicast

| Tiêu chí | Unicast | Broadcast | Multicast |
|---|---|---|---|
| Ý nghĩa địa chỉ đích | Một địa chỉ unicast cụ thể | Một địa chỉ/phạm vi broadcast | Một **địa chỉ nhóm multicast** |
| Bên được chọn theo logic | Một đích mạng cho mỗi gói | Các host trong broadcast domain/scope tương ứng | Các host/giao diện là **thành viên nhóm** trong phạm vi được định tuyến |
| Phía nhận có cần tham gia nhóm multicast? | Không | Không | **Có**, thường thông qua join group ở tầng host/network |
| Một nguồn gửi cho nhiều bên | Gửi riêng cho mỗi đích (hoặc dùng dịch vụ phân phối) | Một datagram broadcast trong phạm vi của nó | Một datagram gửi tới group; mạng có thể nhân bản khi cần |
| IPv4 | Có | **Có**, limited/directed broadcast theo cấu hình | Có, dải **224.0.0.0/4** |
| IPv6 | Có | **Không có cơ chế IP broadcast** | Có, địa chỉ multicast **ff00::/8** |
| Vượt qua router | Theo định tuyến unicast | Broadcast thường bị giới hạn và/hoặc bị chặn | Chỉ khi mạng có cấu hình/hỗ trợ định tuyến multicast phù hợp |
| Tình huống quen thuộc | HTTP/TCP request tới một dịch vụ | Một số cơ chế khám phá cục bộ dựa vào IPv4 broadcast | Phát luồng, thông báo nhóm, discovery/protocol nội bộ tùy mạng |
| Điều không được bảo đảm | Ứng dụng đích phải chấp nhận hoặc xử lý | Mọi ứng dụng/máy đều nhận | Mọi thành viên đều nhận và xử lý đầy đủ |

**Điểm dễ nhầm:** một gói unicast đôi khi sử dụng địa chỉ có nhiều instance dịch vụ đứng sau anycast hoặc load balancer; điều này không biến gói thành multicast. Ở cấp IP, đích gói vẫn là địa chỉ unicast. Ngược lại, multicast không phải “server mở nhiều kết nối TCP rồi gửi cùng dữ liệu”.

### Hình dung phạm vi người nhận

```text
Một nguồn phát S; máy A, B, C cùng LAN-1; máy D thuộc LAN-2.

                  +------- LAN-1 -------+
S ---- unicast -->| B                   |  Chỉ chọn đích B
                  | A    B    C         |
                  +---------------------+
                                  +--- LAN-2 ---+
                                  | D           |
                                  +-------------+

S --- IPv4 broadcast LAN-1 ---> A, B, C (các host trong miền broadcast)
                                 D: không tự nhận do khác miền

Nhóm G:
  A: tham gia G     B: không tham gia G
  C: tham gia G     D: tham gia G nhưng thuộc LAN-2

S --- multicast G, hop limit/TTL 1 ---> A, C
D chỉ có thể nhận nếu phạm vi và định tuyến multicast cho phép đến LAN-2.
```

Sơ đồ **minh họa lựa chọn các ứng viên đích**, không phải bảo đảm delivery. Firewall, NIC, kernel, membership, UDP port, binding, routing và ứng dụng có thể tiếp tục lọc gói. Một máy trong LAN broadcast không có nghĩa mọi process trên máy đó thấy datagram.

## 3. Unicast: chọn một địa chỉ đích cho một gói

**Unicast** dùng địa chỉ IP đích thuộc loại unicast, ví dụ `192.0.2.20` hoặc `2001:db8::20` (hai dải dành cho tài liệu). Với socket UDP, một datagram thường được gửi tới cặp **địa chỉ IP + cổng**; với TCP, client kết nối tới một endpoint unicast theo IP/port, rồi trao đổi qua connection tương ứng.

Ví dụ một máy S gửi tới ba máy A, B, C:

```text
S -- datagram #1 --> A
S -- datagram #2 --> B
S -- datagram #3 --> C
```

Ứng dụng nguồn chịu trách nhiệm phát tới ba đích, trừ khi có hệ thống trung gian như broker hoặc CDN đảm nhận phân phối. Một gói unicast không tự trở thành nhóm chỉ vì payload giống nhau.

**Ưu điểm:** xác định đích cụ thể, dễ thiết lập request–response, có thể áp dụng TLS/TCP, quyền truy cập và phiên làm việc theo từng peer. **Đánh đổi:** muốn phân phối nội dung lớn tới N đích riêng, nguồn hoặc dịch vụ phân phối có thể phải phát lại dữ liệu nhiều lần. Tuy vậy multicast không tự động là phương án tối ưu: các hạn chế mạng, bảo mật và hỗ trợ client có thể làm unicast phù hợp hơn.

Cần phân biệt **địa chỉ IP** và **ứng dụng**: gói tới một IP không bảo đảm đúng một process nhận được dữ liệu. Với UDP, cổng đích phải được ứng dụng mở/bind; với TCP, máy chủ phải có listener và giao thức hợp lệ.

## 4. Broadcast: chọn một miền mạng, không chọn nhóm đã đăng ký

### 4.1. Broadcast ở lớp liên kết và IPv4

Ở Ethernet, frame **broadcast** dùng địa chỉ MAC đích `ff:ff:ff:ff:ff:ff`; switch thường phát tán frame trong miền broadcast/VLAN tương ứng. Đây là **lớp 2**. Ở **IPv4**, hai dạng broadcast thường được nhắc tới:

- **Limited broadcast:** `255.255.255.255`, chỉ có phạm vi cục bộ; router không chuyển tiếp như một gói broadcast Internet thông thường.
- **Directed broadcast:** địa chỉ broadcast của một subnet IPv4, ví dụ với subnet giả định `192.0.2.0/24` thì `192.0.2.255`. Router và chính sách mạng thường **không cho chuyển tiếp directed broadcast** vì lý do bảo mật/lạm dụng.

Subnet `192.0.2.0/24` chỉ là ví dụ tài liệu; địa chỉ broadcast thực tế phải tính từ **network prefix/mask**. Không phải mọi mạng đều là /24; đừng kết luận “địa chỉ cuối luôn .255” nếu chưa biết subnet.

**Không có IPv6 broadcast** tương đương IPv4 broadcast. IPv6 dùng các địa chỉ **multicast** được định nghĩa cho các chức năng như all-nodes trên liên kết; đây vẫn là multicast, không phải IP broadcast theo cú pháp IPv4.

### 4.2. “Tất cả” ở đây nghĩa là tất cả ai?

Broadcast đưa gói đến một phạm vi mạng rộng, nhưng không có nghĩa mọi chương trình ứng dụng trên mọi host nhận hoặc xử lý nó:

1. Switch/router quyết định phạm vi gói có thể lan tới.
2. NIC, host firewall và IP/UDP stack có thể chặn hoặc lọc.
3. UDP application phải bind tới cổng tương ứng và có cấu hình cho phép nhận.
4. Chính sách môi trường (Wi-Fi AP isolation, VLAN, VPN, cloud network) có thể chặn broadcast.

Một host ở LAN khác thường **không** nhận broadcast của LAN-1. Nhiều hệ thống cloud/VPC cũng không hỗ trợ mô hình broadcast như một LAN Ethernet truyền thống.

**Trường hợp dùng:** một số giao thức khám phá máy hoặc thiết bị theo vùng cục bộ. Không nên mặc định phát dữ liệu business lớn/lặp liên tục bằng broadcast: nó có thể gây lưu lượng không cần thiết tới những thiết bị không quan tâm.

## 5. Multicast: chọn người nhận theo địa chỉ nhóm và membership

Với multicast, người gửi **không chọn từng IP của từng client**. Nó chọn **địa chỉ multicast G**. Các bên muốn nhận lưu lượng sẽ tham gia group G trên giao diện mạng liên quan.

- **IPv4 multicast:** `224.0.0.0/4`, tức địa chỉ `224.0.0.0` đến `239.255.255.255`. Trong dải này có những khối dành cho mục đích hoặc scope đặc biệt; **không chọn bừa** một group đã được dành riêng.
- **IPv6 multicast:** `ff00::/8`, có trường scope trong địa chỉ. Ví dụ `ff02::1` là all-nodes multicast phạm vi **link-local**; nó không phải “địa chỉ broadcast IPv6”.
- **Ví dụ group ứng dụng theo mạng quản trị phù hợp:** `239.10.10.10` (thuộc vùng administratively scoped multicast `239.0.0.0/8`). Group thực tế cần phù hợp với chính sách địa chỉ của tổ chức và tránh trùng với hệ thống khác.

Một IP multicast là **định danh nhóm**, không phải địa chỉ unicast của một máy chủ. **Một nguồn phát không cần tham gia group chỉ để gửi**; join chủ yếu dành cho phía **nhận**. Một host có thể tham gia nhiều nhóm và có thể rời nhóm bất kỳ lúc nào.

### 5.1. Membership và vai trò của switch/router

Quá trình ở mức khái niệm:

1. Ứng dụng mở socket UDP trên cổng cần nhận và yêu cầu hệ điều hành **join group G** trên network interface thích hợp.
2. IP stack ghi nhận membership; trong mạng IPv4 có cơ chế **IGMP** trao đổi thông tin thành viên, còn IPv6 dùng **MLD**.
3. Switch có tính năng **IGMP/MLD snooping** có thể học cổng nào thực sự có bên nhận để giảm phát tán multicast trong LAN.
4. Nếu lưu lượng cần vượt qua router, hạ tầng phải hỗ trợ định tuyến multicast theo scope/policy tương ứng. **Multicast routing không mặc định tồn tại trên Internet hoặc mọi VPN/cloud network.**
5. Khi ứng dụng leave group hoặc hết hiệu lực membership theo cơ chế mạng, lưu lượng nhóm có thể không còn được phân phối tới giao diện đó.

**Phân biệt:** IGMP/MLD là cơ chế **quản lý thành viên** giữa host và mạng lân cận; chúng **không phải** giao thức mang payload ứng dụng. Định tuyến multicast là một bài toán riêng; không nên suy luận chỉ cần gọi Java `joinGroup` là router sẽ đưa gói qua mọi subnet.

### 5.2. Người nhận được chọn qua những lớp lọc

Để một **Java application** thực sự nhận được datagram multicast, thường cần đồng thời:

- Địa chỉ đích là **group** mà interface đã tham gia, ở scope mạng phù hợp.
- Đường mạng cung cấp gói tới host/interface (switching, routing, firewall, TTL/hop limit).
- UDP **destination port** phù hợp với socket đang bind, ví dụ `5001`.
- Socket/OS và API nhận hỗ trợ membership/interface như cấu hình.
- Ứng dụng gọi `receive`, parse payload thành công và xử lý.

Vì vậy câu “multicast chỉ gửi đến các máy đăng ký” là **mô hình lựa chọn đích**, không phải lời hứa tuyệt đối rằng mạng sẽ không phát frame tới cổng nào khác, hoặc mọi thành viên sẽ đọc được message. Switch không có snooping có thể flood multicast trong một VLAN; host không tham gia group có thể vẫn thấy frame ở tầng thấp nhưng không giao cho socket ứng dụng thông thường.

### 5.3. Group, port, TTL và phạm vi

Ví dụ gửi UDP tới `239.10.10.10:5001`:

- `239.10.10.10` là **group IP**.
- `5001` là **UDP port của giao thức ứng dụng**.
- Hai ứng dụng cùng tham gia group G nhưng chỉ một ứng dụng bind đúng port chưa chắc đều được phát cùng datagram.
- **TTL/hop limit** quyết định số hop tối đa qua router; giá trị `1` thường dùng để giới hạn gói multicast trong liên kết cục bộ, không tự đồng nghĩa mọi gói đều được giao.
- Phạm vi địa chỉ multicast và chính sách router cũng giới hạn nơi gói có thể đi.

Với multicast, mạng có thể **nhân bản gói ở nhánh phân phối** thay vì sender phải gửi N bản sao tới N IP riêng. Tuy nhiên, giảm lưu lượng nguồn không bảo đảm giảm tải ở mọi liên kết hoặc luôn đạt hiệu năng tốt hơn unicast.

## 6. Một phép so sánh có địa chỉ và kết quả rõ ràng

Giả sử có các máy:

| Máy | Địa chỉ minh họa | Mạng | Tham gia nhóm G = `239.10.10.10`? |
|---|---|---|---|
| A | `192.0.2.10` | LAN-1 | Có |
| B | `192.0.2.11` | LAN-1 | Không |
| C | `192.0.2.12` | LAN-1 | Có |
| D | `198.51.100.10` | LAN-2 | Có |

Nguồn S ở LAN-1:

1. **Unicast tới B:** người gửi định danh trực tiếp địa chỉ `192.0.2.11` → B là ứng viên đích.
2. **IPv4 broadcast trong LAN-1:** chọn phạm vi LAN-1 → A, B, C là các host thuộc miền; D ở LAN-2 không được chọn.
3. **Multicast G, giới hạn TTL=1:** chọn group G và phạm vi LAN-1 → A, C là các thành viên phù hợp. B không thuộc group; D có thuộc group nhưng ở LAN-2 nên không nằm trong phạm vi này.
4. **Multicast G qua nhiều LAN (nếu hạ tầng hỗ trợ):** khi có định tuyến multicast hợp lệ và TTL/scope cho phép, D có thể được nhận thêm. Không được khẳng định điều đó chỉ từ việc D đã join.

Từ ví dụ, ta thấy multicast **không phải broadcast**: B ở chung LAN nhưng không muốn nhận G, nên không thuộc nhóm đích của ứng dụng. Multicast cũng **không phải unicast lặp**: người gửi biểu diễn đích bằng G thay vì danh sách riêng A, C, D.

## 7. Java 17+: mô phỏng chính xác việc chọn bên nhận

Để học **quy tắc chọn người nhận** mà không phụ thuộc router, Wi-Fi hoặc hệ điều hành có bật multicast hay không, chương trình dưới đây **mô phỏng** bảng host/subnet/membership. Nó không gửi datagram thật. Các địa chỉ trong bảng chỉ minh họa.

Tạo file **`RecipientSelectionDemo.java`**:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class RecipientSelectionDemo {
    record Host(
            String name,
            String ip,
            String network,
            Set<String> groups) {
    }

    static List<String> choose(
            List<Host> hosts, Predicate<Host> rule) {
        return hosts.stream()
                .filter(rule)
                .map(Host::name)
                .toList();
    }

    public static void main(String[] args) {
        String group = "239.10.10.10";
        String localNetwork = "LAN-1";

        List<Host> hosts = List.of(
                new Host("A", "192.0.2.10", "LAN-1",
                        Set.of(group)),
                new Host("B", "192.0.2.11", "LAN-1",
                        Set.of()),
                new Host("C", "192.0.2.12", "LAN-1",
                        Set.of(group)),
                new Host("D", "198.51.100.10", "LAN-2",
                        Set.of(group))
        );

        List<String> unicast = choose(
                hosts, h -> h.ip().equals("192.0.2.11"));

        List<String> broadcast = choose(
                hosts, h -> h.network().equals(localNetwork));

        List<String> multicastLocal = choose(
                hosts, h -> h.network().equals(localNetwork)
                        && h.groups().contains(group));

        List<String> remoteMembers = choose(
                hosts, h -> !h.network().equals(localNetwork)
                        && h.groups().contains(group));

        System.out.println("Unicast to B: " + unicast);
        System.out.println("Broadcast LAN-1: " + broadcast);
        System.out.println("Multicast G, TTL=1: " + multicastLocal);
        System.out.println("Members on other LANs: " + remoteMembers);
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 RecipientSelectionDemo.java
java RecipientSelectionDemo
```

**Đầu ra chính xác:**

```text
Unicast to B: [B]
Broadcast LAN-1: [A, B, C]
Multicast G, TTL=1: [A, C]
Members on other LANs: [D]
```

**Giải thích:**

- `unicast` kiểm tra **đúng địa chỉ đích** `192.0.2.11`: chỉ B thỏa mãn.
- `broadcast` chỉ kiểm tra cùng **miền LAN-1** trong mô hình: A/B/C là ứng viên, không phụ thuộc `groups()`.
- `multicastLocal` đồng thời kiểm tra thành viên **group G** và cùng **LAN-1** với nguồn khi scope/TTL mô phỏng bị giới hạn: chỉ A/C.
- `remoteMembers` cho thấy D có join G nhưng **không thể tự suy ra** nó nhận datagram khi nguồn phát trong LAN-1 với TTL=1.

Đây là mô hình **logic** để so sánh ý nghĩa địa chỉ; Java `Predicate` không thay thế cơ chế routing, IGMP/MLD, firewall hay UDP port của mạng thật. Một network packet có thể bị drop, duplicate hoặc xử lý khác mô hình ngay cả khi một host là ứng viên nhận.

## 8. Java thực tế: `DatagramSocket` và `MulticastSocket`

Trong Java, kiểu API cần chọn phản ánh cách gửi:

| Nhiệm vụ | API tiêu biểu | Địa chỉ đích |
|---|---|---|
| UDP unicast | `DatagramSocket.send(DatagramPacket)` | IP unicast + UDP port |
| IPv4 UDP broadcast | `DatagramSocket`, đôi khi cần `setBroadcast(true)` tùy cấu hình | Limited/directed broadcast IPv4 + UDP port |
| UDP multicast | `MulticastSocket` hoặc `DatagramChannel` hỗ trợ multicast | **Multicast group IP** + UDP port |
| Tham gia/rời group | `MulticastSocket.joinGroup(...)` / `leaveGroup(...)`; hoặc `DatagramChannel.join(...)` | Group và **network interface** |

### 8.1. UDP unicast

Ví dụ **mã minh họa**, đặt trong một phương thức có thể ném `IOException`:

```java
byte[] payload = "STATUS".getBytes(StandardCharsets.UTF_8);
InetAddress destination = InetAddress.getByName("192.0.2.11");
DatagramPacket packet = new DatagramPacket(
        payload, payload.length, destination, 5001);

try (DatagramSocket socket = new DatagramSocket()) {
    socket.send(packet);
}
```

Gói được gửi hướng tới **một đích** IP:port. Vì `192.0.2.11` là địa chỉ tài liệu, đoạn này chỉ minh họa cấu trúc API, **không có server thực tế nhận**. Lời gọi `send` không ném exception cũng **không chứng minh receiver đã xử lý payload**.

### 8.2. IPv4 UDP broadcast

Ví dụ **mã minh họa** dùng broadcast IPv4 giới hạn ở môi trường cho phép:

```java
byte[] payload = "DISCOVER".getBytes(StandardCharsets.UTF_8);
InetAddress destination = InetAddress.getByName("255.255.255.255");
DatagramPacket packet = new DatagramPacket(
        payload, payload.length, destination, 5001);

try (DatagramSocket socket = new DatagramSocket()) {
    socket.setBroadcast(true);
    socket.send(packet);
}
```

Tùy hệ điều hành, interface, firewall và mạng, broadcast có thể bị giới hạn/chặn. Nó không gửi đến toàn Internet; đừng sử dụng broadcast vô hạn hoặc mặc định mọi máy sẽ trả lời. `setBroadcast(true)` cho phép chế độ phát broadcast ở socket khi hệ thống hỗ trợ, nhưng **không tạo định tuyến vượt router**.

### 8.3. UDP multicast: gửi và tham gia nhóm

Để nhận multicast thật, ứng dụng phải chọn **network interface phù hợp**, bind đúng port rồi join group. Ví dụ helper dưới đây là **mã minh họa để tích hợp**, không phải class độc lập: nó giả định caller truyền `NetworkInterface nic` đã chọn hợp lệ và chính sách mạng cho phép IPv4 multicast.

```java
// Đoạn mã đặt trong một class có các import java.net.*,
// java.nio.charset.StandardCharsets và java.io.IOException.
static void receiveOneMulticast(NetworkInterface nic)
        throws IOException {
    InetAddress group = InetAddress.getByName("239.10.10.10");
    int port = 5001;
    InetSocketAddress membership = new InetSocketAddress(group, port);

    try (MulticastSocket receiver = new MulticastSocket(port)) {
        receiver.setNetworkInterface(nic);
        receiver.setSoTimeout(2_000); // tránh đợi receive() vô hạn
        receiver.joinGroup(membership, nic);
        try {
            byte[] buffer = new byte[2048];
            DatagramPacket packet =
                    new DatagramPacket(buffer, buffer.length);
            receiver.receive(packet);

            String message = new String(
                    packet.getData(), packet.getOffset(),
                    packet.getLength(), StandardCharsets.UTF_8);
            System.out.println(message);
        } finally {
            receiver.leaveGroup(membership, nic);
        }
    }
}

static void sendOneMulticast(NetworkInterface nic)
        throws IOException {
    InetAddress group = InetAddress.getByName("239.10.10.10");
    byte[] payload = "HELLO GROUP".getBytes(StandardCharsets.UTF_8);
    DatagramPacket packet =
            new DatagramPacket(payload, payload.length, group, 5001);

    try (MulticastSocket sender = new MulticastSocket()) {
        sender.setNetworkInterface(nic);
        sender.setTimeToLive(1);
        sender.send(packet);
    }
}
```

**Giải thích API, không nhầm với điều kiện giao nhận:**

1. `group` là địa chỉ **nhóm multicast** chứ không phải địa chỉ máy đích.
2. `receiver.joinGroup(new InetSocketAddress(group, port), nic)` đăng ký nhận group trên interface `nic`. Biến `port` phù hợp với UDP port đã bind của receiver; việc truyền `InetSocketAddress` ở overload này **không tự tạo TCP connection**.
3. `receiver.receive(packet)` chỉ trả về nếu có datagram phù hợp đến socket; `setSoTimeout` giới hạn thời gian chờ đọc. **Không có bảo đảm** datagram sẽ đến trong 2 giây nếu hạ tầng không hỗ trợ multicast.
4. `leaveGroup` rời membership; `close` đóng socket. Code cleanup trong `finally` nhằm cố gắng rời nhóm ngay cả khi đọc gặp exception.
5. **Sender không phải `joinGroup` chỉ để gửi.** Nó chọn group IP:port, interface và `setTimeToLive(1)` để giới hạn phạm vi.
6. Trên máy có nhiều NIC, việc chọn sai interface là nguyên nhân rất phổ biến khiến app “join thành công nhưng không nhận gói”. Interface cần hoạt động và hỗ trợ multicast (`NetworkInterface.supportsMulticast()` nếu API/hệ thống cung cấp thông tin).
7. `MulticastSocket.joinGroup(InetAddress)` là kiểu API cũ; với JDK hiện đại nên dùng overload có **`SocketAddress` và `NetworkInterface`** hoặc API `DatagramChannel` để làm rõ interface.

**Không dự đoán stdout** cho ví dụ mạng thật này: thành công phụ thuộc routing, group, interface, firewall, cổng và tiến trình sender/receiver; lớp demo hoàn chỉnh ở mục 7 mới là ví dụ kiểm tra deterministic và chạy offline.

### 8.4. DatagramChannel và IPv6

API NIO có thể dùng `DatagramChannel`, ví dụ mở theo `StandardProtocolFamily.INET` hoặc `INET6`, cấu hình `StandardSocketOptions.IP_MULTICAST_IF`, rồi `join(group, networkInterface)`. Đây là lựa chọn linh hoạt hơn khi dự án đã dùng NIO và selector; vẫn phụ thuộc scope, nhóm multicast đúng family và khả năng mạng.

Với IPv6, không cố gắng mô phỏng broadcast `255.255.255.255`: đó là địa chỉ **IPv4**. Ứng dụng IPv6 phải dùng multicast phù hợp với scope và interface.

## 9. UDP multicast không cung cấp bảo đảm kiểu TCP

Multicast phổ biến qua **UDP datagrams/IP multicast**, không phải một kết nối TCP “có nhiều người nhận”. So sánh:

- **TCP** có stream được đánh số thứ tự, retransmission, flow control và kết nối riêng giữa hai endpoint ở tầng transport. TCP là lựa chọn phổ biến cho unicast có yêu cầu thứ tự.
- **UDP** giữ ranh giới từng datagram nhưng không hứa delivery, không tự retransmit, không bắt buộc theo thứ tự và không ngăn duplicate ở mức ứng dụng.
- **IP multicast** chọn nhóm nhận datagram; nó **không tự làm UDP đáng tin cậy**. Thành viên có thể join sau thời điểm gói được phát, mất packet vì congestion hoặc không nhận do router/firewall.
- Một nguồn phát multicast không biết chính xác mỗi thành viên đã đọc/xử lý payload hay chưa. Nếu ứng dụng cần điều này, phải có giao thức ACK, sequence number, replay, FEC hoặc các cơ chế phù hợp; việc nhận nhiều ACK cùng lúc còn có thể tạo **ACK implosion**.

Multicast có thể hiệu quả khi một nguồn phân phối cùng một nội dung tới nhiều người trong mạng hỗ trợ, nhưng không phù hợp với mọi API request–response, giao dịch có xác nhận riêng hoặc dịch vụ triển khai ở môi trường không hỗ trợ multicast routing.

## 10. Thực hành lựa chọn cơ chế

| Bài toán | Lựa chọn thường cân nhắc | Vì sao |
|---|---|---|
| Client gọi API thanh toán của một service | **Unicast** qua TCP/TLS/HTTP | Một endpoint logic, yêu cầu xác thực/phản hồi rõ ràng |
| Gửi một bản tin riêng tới máy B | **Unicast** | Chọn chính xác địa chỉ đích B |
| Khám phá dịch vụ trên LAN IPv4 cũ | **Broadcast** hoặc giao thức discovery khác | Có thể muốn thông báo cho host trong một phạm vi cục bộ, không cần membership ứng dụng |
| Nhiều thiết bị trong cùng mạng đăng ký một luồng sự kiện | **Multicast** nếu mạng hỗ trợ | Chỉ các thành viên nhóm là đích logic, nguồn gửi một luồng cho group |
| Ứng dụng trên Internet/cloud/mobile phân phối sự kiện | Thường **unicast qua broker/CDN/pub-sub service** | IP multicast thường không được định tuyến xuyên Internet và cloud network |
| Chức năng khám phá trên mạng IPv6 | Cơ chế **IPv6 multicast** hoặc giao thức discovery phù hợp | IPv6 không có IP broadcast |

**Không đồng nhất multicast với pub/sub ở tầng ứng dụng.** Một message broker (Kafka, RabbitMQ, Redis Pub/Sub…) có thể chọn subscribers theo topic, nhưng vẫn phân phối qua các kết nối **unicast**. “Topic” và “multicast IP group” đều có khái niệm nhóm nhận, song thuộc **những tầng khác nhau** và có bảo đảm hoàn toàn khác nhau.

## 11. Các nhầm lẫn và lỗi thường gặp

| Nhầm lẫn | Sự thật |
|---|---|
| “Broadcast gửi đến mọi máy trên Internet.” | Broadcast IPv4 thường bị giới hạn trong phạm vi mạng; router có thể chặn directed broadcast. |
| “IPv6 có broadcast giống IPv4.” | IPv6 **không có IP broadcast**; dùng multicast theo scope. |
| “Multicast = gửi unicast N lần.” | Multicast dùng một **địa chỉ nhóm**; mạng có thể nhân bản lưu lượng ở nhánh cần thiết. |
| “Tất cả máy cùng LAN đều nhận multicast.” | Không. Nhóm đích ở mức ứng dụng dựa trên membership; host không join thường không được chuyển datagram lên socket của ứng dụng. |
| “Chỉ cần joinGroup là nhận được datagram từ mọi subnet.” | Không. Scope, TTL, interface, router, switch và firewall đều có thể giới hạn. |
| “Sender phải join group trước khi gửi multicast.” | Thường không. **Receiver** tham gia nhóm để nhận; sender có thể phát tới group. |
| “Join group = mở kết nối TCP tới các thành viên.” | Không. Group membership là thao tác multicast của IP/UDP; không tạo một kết nối TCP nhiều phía. |
| “Multicast đảm bảo mọi người nhận đúng một lần.” | Không. UDP/IP multicast không có delivery/exactly-once guarantee. |
| “Cùng group là cùng ứng dụng nhận, bất kể port.” | UDP destination port và socket binding vẫn quan trọng. |
| “Multicast không đến host B thì B không thể nhìn thấy frame ở mọi lớp.” | Host có thể thấy lưu lượng ở tầng thấp do flooding/snooping policy, nhưng ứng dụng không join không mặc nhiên được giao packet. |
| “`255.255.255.255` là multicast group.” | Đây là địa chỉ **limited IPv4 broadcast**, không phải multicast. |
| “`setBroadcast(true)` cho phép IPv4 broadcast vượt mọi router.” | Chỉ bật tính năng socket nếu OS cho phép; không thay đổi định tuyến mạng. |
| “Multicast luôn tốt hơn unicast cho nhiều người xem.” | Lợi ích phụ thuộc hạ tầng hỗ trợ, băng thông, kiểm soát lỗi và security; unicast qua CDN/broker có thể phù hợp hơn. |

## 12. Bài tập tự kiểm tra

**Câu 1.** A/B/C chung LAN, chỉ A và C join group `239.10.10.10`. Nguồn gửi UDP tới group này với TTL=1; ai là **ứng viên thành viên nhóm** ở LAN?

**Trả lời:** A và C. B không join group, không được chọn theo membership. Đây không phải bảo đảm chắc chắn A/C nhận datagram, vì còn phụ thuộc network/socket.

**Câu 2.** Cùng ba máy A/B/C, người gửi dùng IPv4 broadcast của LAN. Có cần A/B/C join multicast group trước?

**Trả lời:** Không. Broadcast hướng tới miền broadcast, không dùng membership group; tuy nhiên OS, firewall và UDP port vẫn có thể lọc.

**Câu 3.** D ở LAN khác có join cùng group G. D chắc chắn nhận khi nguồn phát TTL=1?

**Trả lời:** Không. TTL=1 giới hạn phạm vi multicast và không mặc nhiên đi qua router. Muốn qua subnet cần routing/scope và hạ tầng phù hợp.

**Câu 4.** IPv6 dùng `255.255.255.255` được không?

**Trả lời:** Không. Đó là địa chỉ IPv4 limited broadcast. IPv6 không có IP broadcast, thay vào đó dùng multicast với địa chỉ thuộc `ff00::/8` và scope tương ứng.

**Câu 5.** Khi gửi UDP multicast tới `239.10.10.10:5001`, host đã join `239.10.10.10` nhưng chỉ có process bind port `5002`. Có chắc process nhận payload không?

**Trả lời:** Không. Datagram có UDP destination port `5001`, nên process ở `5002` không tự nhận được nó. Membership group là điều kiện cần về đích multicast, chưa đủ về socket ứng dụng.

**Câu 6.** Nếu muốn mỗi máy xác nhận đã xử lý một lệnh nghiệp vụ, dùng multicast UDP đơn thuần có đủ không?

**Trả lời:** Không. Multicast chọn nhóm nhận, UDP không bảo đảm delivery/processing. Cần protocol xác nhận, nhận diện message, retry/idempotency và chiến lược chống ACK implosion nếu thực sự cần.

**Câu 7.** Một broker phát message qua TCP unicast tới 100 subscriber có phải IP multicast không?

**Trả lời:** Không. Đó là fan-out/pub-sub **ở tầng ứng dụng** bằng nhiều luồng unicast. IP multicast đòi hỏi địa chỉ multicast và cơ chế mạng tương ứng.

**Câu 8.** Trong cùng LAN, multicast luôn chỉ được phát đến port Ethernet có thành viên nhóm?

**Trả lời:** Không chắc. Switch có thể flood multicast khi không biết membership hoặc không bật snooping. Việc host/app nhận được datagram còn phải qua kiểm tra ở stack và socket.

## 13. Ghi nhớ

- **Unicast chọn một địa chỉ đích cụ thể.**
- **IPv4 broadcast chọn một miền broadcast**, không chọn nhóm những người đã đăng ký; thường chỉ có tác dụng trong phạm vi cục bộ, và **IPv6 không có IP broadcast**.
- **Multicast chọn một địa chỉ nhóm**; receiver tham gia nhóm trên interface thích hợp. Cùng LAN mà không join thì không thuộc tập người nhận logic của nhóm.
- **Nhóm khác mạng không tự nhận**: scope, TTL, multicast routing, IGMP/MLD, switch/firewall và UDP port quyết định đường đi và việc phân phối thực tế.
- **Chọn đúng người nhận không đồng nghĩa đảm bảo delivery.** UDP/IP multicast không thay thế acknowledgment, idempotency hoặc business-level processing confirmation.
- Trong Java, `DatagramSocket` phục vụ UDP; `MulticastSocket.joinGroup`/`leaveGroup` và `NetworkInterface` giúp điều khiển membership, nhưng vẫn cần hạ tầng hỗ trợ. Với TCP client–server thông thường, unicast là mô hình kết nối nền tảng.

Tài liệu tham khảo: Java SE 17 API `java.net.DatagramSocket`, `java.net.DatagramPacket`, `java.net.MulticastSocket`, `java.net.NetworkInterface`; các chuẩn IP multicast/IGMP/MLD và IPv6 addressing (RFC 1112, RFC 4291, RFC 3810).