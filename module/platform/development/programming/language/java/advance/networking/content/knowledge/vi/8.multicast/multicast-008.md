# Kiểm chứng multicast trong mạng cục bộ và phân biệt lỗi ứng dụng với hạ tầng

## Mục tiêu

Multicast cho phép **một bên gửi** một datagram đến **địa chỉ nhóm**, và các máy đã tham gia nhóm có thể nhận bản sao trong phạm vi mạng cho phép. Khi ứng dụng Java không nhận được một bản tin multicast, không thể kết luận ngay rằng “mã Java sai” hoặc “switch chặn”: một phép kiểm chứng tốt phải tách được **ứng dụng → hệ điều hành/socket → NIC/firewall → switch/Wi-Fi/VLAN → thiết bị định tuyến**.

Sau bài này, bạn có thể:

1. Mô tả đường đi của một UDP multicast IPv4 trong LAN; phân biệt **địa chỉ nhóm**, **UDP port**, **giao diện mạng**, **IGMP membership**, **TTL** và các thiết bị trung gian.
2. Dùng Java 17+ kiểm tra interface có đang hoạt động và có báo hỗ trợ multicast; join/leave đúng nhóm bằng `MulticastSocket.joinGroup(SocketAddress, NetworkInterface)`.
3. Thực hiện một phép thử gửi–nhận có **group/port/interface/TTL cố định**, gắn `runId` và `sequence` vào payload để so sánh log hai phía.
4. Kiểm tra theo từng tầng bằng log, timeout, unicast control test, packet capture và dữ liệu từ switch/router khi được phép.
5. Phân loại dấu hiệu lỗi: **không gửi được**, **không thấy gói ở NIC gửi**, **không thấy gói ở NIC nhận**, **gói tới NIC nhưng Java không nhận**, **Java nhận nhưng parser từ chối**.
6. Hiểu giới hạn của từng bằng chứng và tránh khẳng định “mạng tốt” chỉ vì `joinGroup()` hay `send()` trả về thành công.

> Trọng tâm là **chẩn đoán multicast trong mạng cục bộ**, không phải xây hệ thống multicast routing xuyên nhiều mạng. Ví dụ dùng **IPv4**, giao thức UDP và JDK 17 trở lên.

## 1. Bản đồ vấn đề: multicast đi qua những đâu?

Xét hai máy trên cùng LAN/VLAN: máy A chạy sender và máy B chạy receiver.

```text
Máy A — sender                                Máy B — receiver
 ┌─────────────────┐                          ┌──────────────────────┐
 │ Java UDP send() │                          │ Java UDP receive()   │
 │ group:port      │                          │ joinGroup(group, NI) │
 └────────┬────────┘                          └──────────▲───────────┘
          │                                             │
     UDP/IP stack                                    UDP/IP stack
          │                                             ▲
          ▼                                             │
    NIC/interface ───► switch / Wi-Fi AP ─────────────► NIC/interface
                         │
                         ├─ VLAN / firewall / ACL?
                         ├─ IGMP snooping?
                         ├─ IGMP querier?
                         └─ AP client isolation?

Sender gửi đến 239.255.42.99:50017 (IPv4 multicast, UDP).
Receiver join group 239.255.42.99 trên đúng interface và bind UDP port 50017.
```

Một multicast **địa chỉ đích** như `239.255.42.99` không đại diện một máy đơn lẻ. Nhiều receiver có thể cùng tham gia nhóm, còn socket nhận phải lắng nghe **UDP port** mà sender sử dụng. Địa chỉ nhóm và port là **hai thành phần độc lập**: join đúng group nhưng bind sai port vẫn có thể không nhận.

### 1.1. Những thành phần phải thống nhất

| Thành phần | Ví dụ dùng trong bài | Vai trò | Sai sẽ dẫn đến |
|---|---|---|---|
| IP family | IPv4 | Giao thức địa chỉ IP dùng cho nhóm | Join IPv4 nhưng sender gửi IPv6 hoặc ngược lại |
| Multicast group | `239.255.42.99` | Địa chỉ đích nhóm | Sender và receiver khác nhóm |
| UDP destination port | `50017` | Port nhận của socket | Packet không tới đúng socket ứng dụng |
| Interface/NIC | `eth0`, `en0` hoặc tên thật khác | Cổng/adapter gửi ra và tham gia nhóm | Chọn VPN, adapter ảo, Wi-Fi khác hoặc NIC sai |
| Local bind | UDP port `50017` trên receiver | Socket nhận các datagram đúng port | Không bind được, bind sai địa chỉ/port |
| IGMP membership | Join nhóm trên interface nhận | Hệ điều hành thông báo nhu cầu nhận multicast IPv4 | Switch/router có thể không chuyển tiếp tới port máy nhận |
| TTL của sender | `1` | Giới hạn hop ở tầng IP | Không đi qua router; điều này là chủ đích của thử nghiệm LAN |
| Firewall / ACL | Quy tắc UDP inbound/outbound | Quyết định packet có được phép qua | Packet có thể bị chặn dù Java đúng |
| Chính sách Wi-Fi/switch | Isolation, IGMP snooping, querier | Quyết định cách phát multicast trên LAN | Packet không tới được receiver qua L2 |

Địa chỉ thuộc dải `239.0.0.0/8` thường dùng cho **administratively scoped IPv4 multicast** trong phạm vi được quản lý. Chọn `239.255.42.99` cho thí nghiệm **không có nghĩa địa chỉ này được dành riêng toàn cầu** cho bài học; nên kiểm tra tránh xung đột với nhóm đang được sử dụng trong mạng thật. Không chọn bừa `224.0.0.x`, vì nhiều địa chỉ trong `224.0.0.0/24` dành cho giao thức điều khiển link-local.

### 1.2. IGMP làm gì, không làm gì?

Với IPv4 multicast, **IGMP (Internet Group Management Protocol)** hỗ trợ máy nhận thông báo việc tham gia nhóm tới mạng cục bộ/thiết bị định tuyến multicast. Switch có **IGMP snooping** có thể quan sát membership để quyết định chuyển datagram multicast đến các port cần thiết, thay vì flood đến mọi port.

Điều cần phân biệt:

- `joinGroup` làm việc với **host networking stack** và membership; hệ điều hành có thể tạo IGMP report phù hợp. Nó **không tạo một kênh tin cậy như TCP**.
- IGMP membership **không** xác nhận sender đang phát đúng địa chỉ/port.
- IGMP report nhìn thấy ở đâu đó không bảo đảm payload UDP sẽ được chuyển đến từng receiver; còn phụ thuộc chính sách switch/AP, firewall, topology và thời điểm.
- Cấu hình IGMP snooping/querier trên switch có thể ảnh hưởng việc duy trì membership. Việc thiếu querier trong một số topology có thể khiến multicast hoạt động lúc đầu rồi mất sau một khoảng thời gian.
- Nếu có router giữa hai máy, cần **multicast routing** được thiết kế/cho phép; chỉ tăng TTL không tự làm thiết bị mạng chuyển tiếp multicast.

**Cần chẩn đoán IGMP và đường dữ liệu riêng.** Nhìn thấy một bản IGMP report chỉ chứng minh host/network stack có hoạt động membership signaling ở nơi capture đó, không chứng minh UDP group payload đến ứng dụng.

## 2. Ba nguyên tắc chống kết luận sai

### 2.1. `joinGroup()` thành công không bảo đảm có người gửi

`MulticastSocket.joinGroup(new InetSocketAddress(group, port), ni)` đăng ký tham gia nhóm trên interface `ni`. Javadoc Java 17 nêu rằng tham số port trong đối tượng group address **không quyết định membership ở mức group**; **port thực sự nhận** do **socket đã bind** quyết định.

Vì vậy chương trình có thể join nhóm thành công trong khi:

- Sender chưa chạy hoặc gửi tới port khác.
- Sender dùng interface/route không tới VLAN của receiver.
- Switch không chuyển tiếp gói tới port tương ứng.
- Firewall local chặn UDP inbound, hoặc AP Wi-Fi bật client isolation.
- Ứng dụng nhận đã thoát, gặp timeout, đọc sai buffer hoặc từ chối payload.

**Đừng sử dụng `joinGroup()` như một health check end-to-end.**

### 2.2. `send()` trả về không chứng minh receiver đã nhận

`MulticastSocket.send(DatagramPacket)` gửi datagram qua stack mạng. Nó không yêu cầu receiver phản hồi và không bảo đảm datagram đã đến, vì UDP không cung cấp cơ chế xác nhận ứng dụng hay truyền lại như TCP. Với multicast, điều đó càng quan trọng: có thể một receiver nhận được còn receiver khác không.

Nếu cần biết ai đã xử lý message, **thiết kế ACK hoặc phép kiểm tra riêng ở tầng ứng dụng**, có ID/nonce, deadline và xác thực theo yêu cầu. ACK vẫn có thể mất; phải phân biệt “không thấy ACK” với “không ai xử lý”.

### 2.3. Timeout không chỉ ra chính xác tầng lỗi

`MulticastSocket.receive(packet)` có thể đợi nếu không có datagram phù hợp. `setSoTimeout(6000)` khiến nó ném `SocketTimeoutException` sau khoảng thời gian chờ khi không nhận được datagram. **Đó chỉ là quan sát tại socket**, chưa tự xác định nguyên nhân. Hãy dùng thêm kết quả từ capture tại NIC và log sender để khoanh vùng.

## 3. Thiết kế một phép thử LAN có thể lặp lại

Thay vì gửi chuỗi “hello” rồi chỉ nhìn thấy/không thấy, hãy ghi chép một *test vector* rõ ràng:

| Thuộc tính | Giá trị |
|---|---|
| IP family | IPv4 |
| Group | `239.255.42.99` |
| UDP port | `50017` |
| Sender TTL | `1` (thử LAN, không qua router) |
| Sender interface | Tên interface lấy trực tiếp từ `NetworkInterface` trên **máy A** |
| Receiver interface | Tên interface lấy trực tiếp từ `NetworkInterface` trên **máy B** |
| Payload | `MC1|<runId>|<seq>` |
| Số datagram dự kiến gửi | `5` |
| Khoảng giữa lần gửi | `200 ms` |
| Timeout receiver | `6000 ms` mỗi lần chờ |
| Bằng chứng quan sát | Log sender, log receiver, capture sender/receiver, group/port/interface/TTL |

`runId` giúp phân biệt các lượt chạy; `seq` giúp đếm nhận, nhận lặp, quan sát thứ tự. Không giả định UDP luôn nhận đủ cả 5 hoặc theo thứ tự 1 đến 5. Trong thử nghiệm LAN khỏe, việc thấy đủ 5 là một **kết quả quan sát tích cực**, không phải cam kết của giao thức.

Một kết quả ví dụ:

```text
Sender: SENT run=ab12cd34 seq=1
Sender: SENT run=ab12cd34 seq=2
Sender: SENT run=ab12cd34 seq=3
Sender: SENT run=ab12cd34 seq=4
Sender: SENT run=ab12cd34 seq=5

Receiver: RECV run=ab12cd34 seq=1 ...
Receiver: RECV run=ab12cd34 seq=2 ...
Receiver: RECV run=ab12cd34 seq=3 ...
Receiver: RECV run=ab12cd34 seq=4 ...
Receiver: RECV run=ab12cd34 seq=5 ...
```

Các dòng trên chỉ là **mẫu**; ID thực, IP nguồn, số gói và thứ tự có thể khác. Nếu mất một gói, ví dụ receiver thấy 1,2,4,5, hãy ghi rõ **seq=3 không được ứng dụng quan sát**, đừng khẳng định ngay “switch làm mất” trước khi có packet capture.

## 4. Java 17+: xác định đúng network interface

Máy có thể có nhiều adapter: Ethernet, Wi-Fi, VPN, Docker bridge, WSL, interface ảo và loopback. `InetAddress.getLocalHost()` chỉ phân giải tên máy tới một địa chỉ và **không chọn thay bạn interface multicast đúng**.

Chương trình sau liệt kê các interface đang `isUp()` cùng cờ `supportsMulticast()` và các địa chỉ gắn trên interface, để chọn chính xác **tên interface** cho hai chương trình tiếp theo.

**Tệp `MulticastInterfaceAudit.java`:**

```java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Enumeration;

public class MulticastInterfaceAudit {
    public static void main(String[] args) throws Exception {
        Enumeration<NetworkInterface> all =
                NetworkInterface.getNetworkInterfaces();

        if (all == null) {
            System.out.println("No network interfaces visible");
            return;
        }

        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            System.out.println("name=" + ni.getName()
                    + " up=" + ni.isUp()
                    + " multicast=" + ni.supportsMulticast()
                    + " loopback=" + ni.isLoopback());

            Enumeration<InetAddress> addresses = ni.getInetAddresses();
            while (addresses.hasMoreElements()) {
                System.out.println("  ip="
                        + addresses.nextElement().getHostAddress());
            }
        }
    }
}
```

**Lệnh:**

```bash
javac -encoding UTF-8 MulticastInterfaceAudit.java
java MulticastInterfaceAudit
```

**Output phụ thuộc máy và hệ điều hành**, ví dụ:

```text
name=eth0 up=true multicast=true loopback=false
  ip=192.168.1.20
name=lo up=true multicast=false loopback=true
  ip=127.0.0.1
```

Không được xem ví dụ stdout là danh sách bắt buộc. Tên interface trên Windows/macOS/Linux, thứ tự địa chỉ, IPv6 và thuộc tính loopback khác nhau theo nền tảng.

**Chọn interface nào?** Hãy chọn interface có địa chỉ thuộc LAN cần kiểm thử, đang **up**, và báo **supportsMulticast=true**. Flag này là khả năng **do OS cung cấp**, **không chứng minh** switch/AP cho phép multicast hoặc host đã join đúng group. Trên máy A và B có thể dùng các tên interface khác nhau.

## 5. Java 17+: receiver join nhóm trên interface tường minh

Ví dụ `LanMulticastReceiver` lắng nghe UDP port `50017` trên local wildcard address, dùng `joinGroup(group, networkInterface)` để đăng ký nhận trên interface được chọn. Nó in `runId`, `seq`, IP/port nguồn, đồng thời đánh dấu trùng `seq` theo từng lượt chạy. Đây là một chương trình độc lập cho **Java 17+**.

**Tệp `LanMulticastReceiver.java`:**

```java
import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class LanMulticastReceiver {
    private static final int PORT = 50017;

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java LanMulticastReceiver <interface-name>");
            return;
        }

        NetworkInterface ni = NetworkInterface.getByName(args[0]);
        if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
            System.out.println("Interface missing, down or no multicast support");
            return;
        }

        InetAddress group = InetAddress.getByName("239.255.42.99");
        InetSocketAddress membership = new InetSocketAddress(group, PORT);

        try (MulticastSocket socket = new MulticastSocket(null)) {
            // Đặt reuse option trước khi bind; không phải lời hứa rằng
            // mọi OS đều cho nhiều process cùng nhận trên một port.
            socket.setReuseAddress(true);
            socket.bind(new InetSocketAddress(PORT));
            socket.setSoTimeout(6000);
            socket.joinGroup(membership, ni);

            Map<String, Set<Integer>> seen = new HashMap<>();
            System.out.println("READY group=239.255.42.99:50017"
                    + " interface=" + ni.getName());

            try {
                for (int i = 0; i < 5; i++) {
                    byte[] buffer = new byte[2048];
                    DatagramPacket packet =
                            new DatagramPacket(buffer, buffer.length);

                    try {
                        socket.receive(packet);
                    } catch (SocketTimeoutException timeout) {
                        System.out.println("TIMEOUT waiting for datagram");
                        break;
                    }

                    String payload = new String(packet.getData(),
                            packet.getOffset(), packet.getLength(),
                            StandardCharsets.UTF_8);
                    String[] parts = payload.split("\\|", -1);

                    if (parts.length != 3
                            || !"MC1".equals(parts[0])
                            || parts[1].isBlank()) {
                        System.out.println("APP_REJECT invalid format");
                        continue;
                    }

                    try {
                        int seq = Integer.parseInt(parts[2]);
                        if (seq < 1) {
                            System.out.println("APP_REJECT invalid sequence");
                            continue;
                        }
                        boolean duplicate = !seen
                                .computeIfAbsent(parts[1], k -> new HashSet<>())
                                .add(seq);

                        System.out.println("RECV run=" + parts[1]
                                + " seq=" + seq
                                + " from=" + packet.getAddress().getHostAddress()
                                + ":" + packet.getPort()
                                + " duplicate=" + duplicate);
                    } catch (NumberFormatException e) {
                        System.out.println("APP_REJECT invalid sequence");
                    }
                }
            } finally {
                socket.leaveGroup(membership, ni);
            }
        }
    }
}
```

**Biên dịch:**

```bash
javac -encoding UTF-8 LanMulticastReceiver.java
```

**Chạy trên máy nhận**, thay tên interface bằng tên thật từ chương trình kiểm kê:

```bash
java LanMulticastReceiver eth0
```

Nếu tên interface chứa khoảng trắng, hãy đặt tên đó trong dấu nháy kép trên dòng lệnh. `eth0` chỉ là ví dụ của Linux, **không phải tên interface mặc định trên mọi hệ điều hành**.

Khi join thành công, chương trình **in dòng READY trước lúc chờ UDP**:

```text
READY group=239.255.42.99:50017 interface=eth0
```

Nếu không có datagram phù hợp trong 6 giây, nó có thể in:

```text
TIMEOUT waiting for datagram
```

**READY không phải bằng chứng packet đến**, và **TIMEOUT không chỉ ra tầng gây lỗi**. Nếu nhận được packet đúng định dạng, nó in thêm `RECV run=... seq=... from=... duplicate=...`. Những giá trị động này không có stdout cố định.

### Các điểm kỹ thuật quan trọng

1. `new MulticastSocket(null)` tạo socket chưa bind để có thể cấu hình `SO_REUSEADDR` **trước** khi bind. `bind(new InetSocketAddress(PORT))` khiến socket lắng nghe UDP port `50017` trên local wildcard address.
2. `joinGroup(membership, ni)` dùng **IP của group** và **interface ni** để join. Theo Javadoc, thành phần port trong `membership` bị bỏ qua cho thao tác join; **port của socket đã bind** mới quyết định UDP traffic được nhận.
3. `setSoTimeout(6000)` chỉ giới hạn thời gian chờ cho mỗi lần `receive`. Nó không tạo một kiểm tra hoạt động toàn mạng.
4. Mỗi `DatagramPacket` nhận **một datagram**; `getLength()` là số byte nhận được. Giải mã toàn bộ buffer 2.048 byte sẽ thêm dữ liệu thừa; mã chỉ giải mã đúng vùng `offset..offset+length`.
5. `APP_REJECT` nghĩa là **ứng dụng đã nhận một datagram**, nhưng nội dung không qua được quy tắc parsing minh họa; đây là loại chứng cứ hoàn toàn khác `TIMEOUT`.
6. `duplicate=true` ở đây chỉ phát hiện `runId+seq` đã thấy **trong process này**. Nó không bảo đảm dedup bền vững hay chống giả mạo; giới hạn bộ nhớ/cửa sổ thời gian là trách nhiệm của hệ thống thật.
7. `leaveGroup` được gọi khi kết thúc vòng đọc; `try-with-resources` đóng socket sau đó. Nếu join thất bại, chương trình báo exception; thông báo lỗi thường chỉ hướng kiểm tra quyền, interface hoặc hỗ trợ stack, không kết luận switch lỗi.

**Cẩn trọng khi thử nhiều receiver cùng máy:** `setReuseAddress(true)` không bảo đảm trên mọi OS rằng hai process cùng bind một port và đều nhận tất cả datagram. Thử mỗi host một receiver trước để loại bỏ phụ thuộc hành vi sharing của OS.

## 6. Java 17+: sender gửi năm probe với TTL = 1

Chương trình sender chọn cùng group và port, chỉ định interface **đầu ra** bằng `setNetworkInterface(ni)`, đặt `setTimeToLive(1)` và gửi năm datagram với cùng `runId` nhưng `seq` tăng dần. Nó **không join group**, vì một bên chỉ gửi multicast không cần là member để gửi.

**Tệp `LanMulticastSender.java`:**

```java
import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class LanMulticastSender {
    private static final int PORT = 50017;

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java LanMulticastSender <interface-name>");
            return;
        }

        NetworkInterface ni = NetworkInterface.getByName(args[0]);
        if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
            System.out.println("Interface missing, down or no multicast support");
            return;
        }

        InetAddress group = InetAddress.getByName("239.255.42.99");
        InetSocketAddress destination = new InetSocketAddress(group, PORT);
        String runId = UUID.randomUUID().toString().substring(0, 8);

        try (MulticastSocket socket = new MulticastSocket()) {
            socket.setNetworkInterface(ni);
            socket.setTimeToLive(1);

            for (int seq = 1; seq <= 5; seq++) {
                String message = "MC1|" + runId + "|" + seq;
                byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

                socket.send(new DatagramPacket(
                        bytes, bytes.length, destination));

                System.out.println("SENT run=" + runId
                        + " seq=" + seq + " bytes=" + bytes.length);
                Thread.sleep(200);
            }
        }
    }
}
```

**Biên dịch và chạy trên máy A:**

```bash
javac -encoding UTF-8 LanMulticastSender.java
java LanMulticastSender eth0
```

Trong một lần chạy bình thường, sender in năm dòng. `runId` khác nhau mỗi lần; ví dụ:

```text
SENT run=ab12cd34 seq=1 bytes=14
SENT run=ab12cd34 seq=2 bytes=14
SENT run=ab12cd34 seq=3 bytes=14
SENT run=ab12cd34 seq=4 bytes=14
SENT run=ab12cd34 seq=5 bytes=14
```

Với cấu trúc `MC1|` (4 byte) + `runId` (8 byte) + `|` (1 byte) + số thứ tự 1 chữ số, kích thước payload là **14 byte**. `runId` trong stdout trên chỉ là giá trị ví dụ; các dòng `SENT` nói code đã hoàn tất lời gọi `send()`, **không** nói receiver đã nhận.

**Lưu ý TTL:** `setTimeToLive(1)` giới hạn multicast trong mạng có phạm vi hop thích hợp và ngăn chuyển qua router ở điều kiện thông thường. Với mục tiêu kiểm chứng **cùng LAN/VLAN**, đây là giới hạn chủ động để tránh phát packet đi xa. Nếu hai máy nằm **khác subnet/VLAN** và đi qua router, phép thử TTL=1 có thể thất bại **đúng theo cấu hình**. Đừng tự nâng TTL lên cao để “sửa” một hệ thống chưa được phép định tuyến multicast; việc định tuyến nhóm qua VLAN cần thiết kế và phê duyệt từ quản trị mạng.

### Chạy thử đúng thứ tự

1. Kiểm kê interface trên cả hai máy, xác định interface nối vào cùng LAN/VLAN.
2. Kiểm tra cả hai máy có thể giao tiếp trên subnet theo cơ chế phù hợp; nếu chỉ `ping` được, đừng suy ra UDP multicast sẽ được chuyển.
3. Trên **máy B**, chạy `LanMulticastReceiver` và thấy dòng `READY`. Tránh khởi động sender **trước** receiver: datagram UDP đã gửi không được lưu lại để ứng dụng tham gia nhóm sau này nhận.
4. Trong thời hạn receiver đang chờ, trên **máy A** chạy `LanMulticastSender`. Chọn interface chính xác ở mỗi máy, không sao chép cứng tên `eth0` nếu hệ điều hành khác.
5. So sánh cùng `runId`, các `seq` gửi/nhận và IP:port nguồn. Chỉ tính các packet có đúng group/port, đúng lượt chạy và đúng định dạng.
6. Nếu không thấy `RECV`, chuyển sang kiểm tra từng tầng thay vì thay đổi đồng thời nhiều tham số.

Một output **minh họa** khi receiver nhận đúng một datagram có thể là:

```text
RECV run=ab12cd34 seq=1 from=192.168.1.20:53741 duplicate=false
```

IP và source port được OS quyết định, không cố định. Chương trình demo chỉ nhận tối đa năm datagram/6 giây mỗi lần chờ nên không dùng như service production. Nếu nhiều sender cùng phát, năm datagram nhận đầu tiên có thể đến từ các lượt chạy khác nhau.

## 7. Baseline quan trọng: thử UDP unicast loopback để khoanh vùng

Khi multicast thất bại, một phép thử **UDP unicast trên loopback** có thể kiểm tra độc lập rằng JVM có khả năng tạo datagram, ghi/đọc buffer UTF-8 và nhận packet qua socket trong cùng máy. Điều này **không xác nhận multicast**, không xác nhận NIC vật lý, IGMP, firewall LAN hay switch.

**Tệp `UdpLoopbackControl.java`:**

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpLoopbackControl {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver = new DatagramSocket(
                     new InetSocketAddress(loopback, 0));
             DatagramSocket sender = new DatagramSocket(
                     new InetSocketAddress(loopback, 0))) {
            receiver.setSoTimeout(2000);

            byte[] payload = "MC1|selftest|1"
                    .getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(
                    payload, payload.length, receiver.getLocalSocketAddress()));

            DatagramPacket incoming = new DatagramPacket(new byte[128], 128);
            receiver.receive(incoming);
            String text = new String(incoming.getData(),
                    incoming.getOffset(), incoming.getLength(),
                    StandardCharsets.UTF_8);

            System.out.println("UDP_LOOPBACK_OK " + text);
        }
    }
}
```

**Lệnh:**

```bash
javac -encoding UTF-8 UdpLoopbackControl.java
java UdpLoopbackControl
```

**Stdout khi local UDP hoạt động bình thường:**

```text
UDP_LOOPBACK_OK MC1|selftest|1
```

Nếu chương trình thành công, có thể loại bớt một số giả thuyết về việc Java không chạy được UDP cơ bản trên máy đó. Nhưng **unicast loopback OK không đủ để khẳng định multicast loopback hay LAN multicast OK**. Nếu nó thất bại, chưa nên đi thẳng tới IGMP trên switch: kiểm tra Java runtime, quyền socket, firewall/local policy và hành vi loopback trước.

## 8. Ma trận bằng chứng: lỗi ứng dụng hay hạ tầng?

Một chương trình có thể “không nhận được” ở nhiều tầng. Ma trận sau không biến triệu chứng thành kết luận chắc chắn, mà chỉ ra **bước quan sát tiếp theo**.

| Dấu hiệu | Nhóm nguyên nhân nên ưu tiên | Bằng chứng kế tiếp |
|---|---|---|
| Java không tìm thấy interface / interface down | Sai interface, VPN/adapter ảo, cấu hình host | Chạy audit, xem địa chỉ thực và trạng thái NIC |
| `supportsMulticast()==false` | Driver/interface không báo hỗ trợ | Chọn NIC khác, kiểm tra OS/driver |
| `bind` ném `BindException` | Port bị chiếm, sharing/permission/bind address sai | Xem UDP socket đang bind, tránh hai receiver tranh port |
| `joinGroup` ném exception | Interface, địa chỉ group, OS/socket policy | Ghi loại exception, xác nhận group IPv4/NI, quyền và nền tảng |
| Receiver in `READY`, sender chưa chạy | Không có nguồn gửi | Khởi chạy sender trong cửa sổ chờ, so runId |
| Sender in `SENT`, không thấy packet ở capture NIC gửi | Có thể chọn sai interface, route/capture, policy host | Capture đúng NIC và kiểm tra interface/hệ điều hành |
| Capture NIC gửi có UDP, capture NIC nhận không có | Có thể mất trên đường L2/AP/VLAN/firewall/route, hoặc capture chưa đúng | Kiểm tra cùng VLAN, switch ports, Wi-Fi isolation, IGMP snooping/querier |
| Capture NIC nhận có UDP, Java không `RECV` | Host filter/firewall, bind/join/NI, parser/log, namespace | Kiểm tra socket bind, join, UDP port, firewall local, namespace |
| Java in `APP_REJECT` | Dữ liệu **đã tới ứng dụng**, nhưng parser từ chối | Đối chiếu payload, encoding, version, length, runId/seq |
| Java in `RECV` nhưng logic nghiệp vụ không chạy | Lỗi xử lý sau receive, validation, thread/queue | Log và test parser/handler riêng |
| Mất vài `seq`, các `seq` khác vẫn tới | Mất datagram, buffer/drop, overload, hạ tầng hoặc sender | So capture và counters, rate, receive buffer, thread |
| Cùng máy có multicast, máy khác không | Phụ thuộc đường LAN thật hoặc khác chính sách NIC | Capture hai NIC vật lý, firewall và network equipment |
| Cùng VLAN OK, khác VLAN không | TTL=1 hoặc không có multicast routing/ACL | Xác minh topology/TTL với quản trị mạng |

**Cảnh báo:** packet capture ở sender thấy một packet **không chứng minh chắc chắn packet đã phát thành công trên dây** (có thể chịu tác động của vị trí capture và offload). Capture ở receiver NIC thấy một packet nhưng Java không nhận có thể do **host firewall/stack** trước socket, không nhất thiết bug Java. Phân loại nguyên nhân phải theo **bằng chứng kết hợp**.

### Phân tầng theo từng câu hỏi

**Lớp ứng dụng:** đúng phiên bản message chưa? `MC1`, `runId`, `seq`, UTF-8, chiều dài có hợp lệ? Có exception bị nuốt hoặc parser bỏ gói không? Log sự kiện ở **trước và sau `receive()`** để biết đã vào app hay chưa.

**Lớp socket/OS:** receiver có bind đúng port `50017`? Đã join group qua **đúng interface**? Socket còn mở? Firewall local có chặn inbound UDP? Chương trình đang trong container/VM/WSL với network namespace khác host? Có process khác cũng bind port với hành vi chia sẻ không ổn định?

**Lớp NIC/LAN:** máy A và B ở cùng VLAN/SSID? Wi-Fi AP có client isolation/guest network? Port switch được cấu hình multicast thế nào? IGMP snooping có học group membership? Có querier duy trì membership nếu topology cần? ACL có drop traffic không?

**Lớp định tuyến:** nếu máy khác subnet/VLAN, router có hỗ trợ và được cấu hình **multicast forwarding** không? TTL có đủ cho các hop được phép? Đừng giả định mạng unicast bình thường kéo theo multicast qua router.

**Lớp vận hành:** packet rate quá cao, CPU/buffer receiver không theo kịp, receiver khởi động sau sender, NIC offload/filtering hoặc firewall policy thay đổi theo thời điểm. Tình huống “thỉnh thoảng nhận” có thể khác “không bao giờ nhận”.

## 9. Packet capture: nhìn gói ở đúng chỗ, đúng tầng

Nếu được phép dùng Wireshark hoặc tcpdump, hãy capture **đồng thời** trên NIC vật lý của máy A và B, hoặc trên switch port mirror đúng vị trí. Đừng chỉ capture loopback trên laptop rồi kết luận LAN đang nhận multicast.

### 9.1. Bộ lọc Wireshark

Filter hiển thị UDP đến đúng nhóm và port:

```text
ip.dst == 239.255.42.99 && udp.dstport == 50017
```

Filter xem IGMP membership signaling:

```text
igmp
```

Nếu cần quan sát cả **payload** và **membership**, dùng hai filter theo lượt hoặc các điều kiện kết hợp phù hợp. Kiểm tra packet thực sự có `ip.dst=239.255.42.99`, `udp.dstport=50017`, source IP/port mong đợi, độ dài và giá trị `MC1|runId|seq`. Đừng chỉ nhìn số “UDP packets” tổng cộng.

### 9.2. Ví dụ tcpdump (Linux/macOS, cần quyền capture)

```bash
sudo tcpdump -ni eth0 'udp and dst host 239.255.42.99 and dst port 50017'
sudo tcpdump -ni eth0 'igmp'
```

`eth0` chỉ là tên minh họa: phải thay bằng interface thật; trên macOS thường có tên khác. Trên Windows dùng công cụ capture tương đương được đơn vị cho phép. **Không cần thay đổi cấu hình firewall/switch** để thu thập bằng chứng, trừ khi bạn có thẩm quyền.

### 9.3. Quy trình đối chiếu song song

1. Trước khi gửi, mở capture phía **receiver**, thấy/ghi nhận thời điểm receiver join group (IGMP report có thể không nhìn thấy do vị trí capture, cache hoặc hành vi OS; không thấy report đơn lẻ chưa đủ để khẳng định join lỗi).
2. Mở capture phía **sender** và kiểm tra đúng **interface đầu ra**.
3. Chạy một lượt sender; ghi `runId`, thời gian, các `seq` đã log.
4. So từng `seq` giữa **sender log → capture A → capture B → receiver log**.
5. Nếu xuất hiện gói trên capture B nhưng không có log nhận, kiểm tra firewall host, local bind/join và đường tới ứng dụng; nếu log `APP_REJECT`, tập trung vào app parser thay vì nghi toàn bộ LAN.
6. Nếu không thấy trên capture B nhưng có trên A, đối chiếu VLAN, AP isolation, switch snooping, IGMP querier, ACL; tránh nhảy thẳng tới giả thuyết duy nhất.

**Giới hạn capture:** phần mềm capture nhìn thấy gói tại điểm quan sát của mình, không phải phép đo toàn tuyến. Một số môi trường offload/virtualization thay đổi cách gói xuất hiện. Muốn kết luận drop ở switch cụ thể phải có thêm counters hoặc capture ở hai phía thiết bị đó.

## 10. Những lỗi mạng cục bộ hay gặp

### 10.1. Sai NIC trên máy nhiều đường mạng

Laptop có Wi-Fi, Ethernet và VPN; container có veth/bridge; interface Java chọn tự động có thể **khác NIC đang nối LAN**. Vì vậy cần **truyền tên interface tường minh** vào chương trình, kiểm tra IP của nó trong audit và nhìn capture trên cùng NIC.

Chỉ dùng `InetAddress.getLocalHost()` không đủ để biết NIC multicast đúng. Cờ `supportsMulticast()` là điều kiện hỗ trợ do OS báo, **không bảo đảm** mạng vật lý cho phép.

### 10.2. IGMP snooping / thiếu querier

Một số switch học các port có receiver qua IGMP reports để chuyển group traffic đúng nơi. Khi **IGMP snooping bật** nhưng topology không có IGMP querier hoạt động phù hợp, membership có thể không được duy trì ổn định theo thời gian. Triệu chứng có thể là nhận được lúc mới join, sau đó mất; hoặc chỉ nhận trên một số switch ports.

Không tự ý tắt IGMP snooping toàn hệ thống để thử nếu không được phép. Thay vào đó, cung cấp **group, VLAN, port switch, thời gian và capture** cho quản trị mạng; kiểm tra IGMP groups, querier và forwarding table bằng công cụ phù hợp với model switch.

### 10.3. Wi-Fi guest / AP client isolation

Hai thiết bị cùng SSID chưa chắc giao tiếp ngang hàng được. Guest network hoặc AP client isolation có thể chặn lưu lượng trực tiếp giữa client; nhiều WLAN còn hạn chế/buffer/chuyển đổi multicast để tiết kiệm airtime. Để đối chiếu, thử **hai máy cắm Ethernet cùng VLAN** nếu có sẵn và được phép; nếu Ethernet OK nhưng Wi-Fi không, ưu tiên kiểm tra chính sách AP/SSID và wireless multicast.

Đừng suy ra lỗi “Java trên Windows” chỉ từ việc test trên Wi-Fi thất bại.

### 10.4. Firewall/endpoint security

Host firewall có thể cho phép UDP loopback/unicast nhưng chặn inbound multicast theo network profile, ứng dụng hoặc UDP port. Capture trên NIC nhận có thể thấy gói nhưng process Java không đọc được. Khi so sánh, ghi rõ **profile mạng, rule inbound/outbound, executable process và port `50017`**.

Không tắt firewall hoặc antivirus đại trà để sửa. Nếu cần kiểm chứng quy tắc, làm theo quy trình của quản trị máy và chỉ thay đổi hẹp, có thời hạn, được phép.

### 10.5. Khác VLAN/subnet, TTL và multicast routing

Test với TTL=1 **được thiết kế cho phạm vi LAN**, không dùng để xác nhận xuyên router. Nếu hai host khác VLAN, unicast ping thành công không chứng minh multicast sẽ qua. Chuyển tiếp multicast qua router cần routing/policy phù hợp và TTL/hop limit cho tuyến cho phép. Nâng TTL không thể tự tạo route, group state hoặc vượt ACL.

### 10.6. Container, VM và WSL

`joinGroup` có thể thành công trong network namespace của container nhưng không có gói đi qua bridge/NAT tới NIC host như mong muốn; multicast qua Docker/VM/WSL còn tùy driver và chế độ mạng. Kết quả trong container cần ghi rõ **interface bên trong namespace** và cách bridge/vSwitch gắn với LAN. Hãy thử một ứng dụng Java tương đương **trên host trực tiếp** (nếu được phép) để kiểm tra ranh giới virtualization.

### 10.7. Đệm nhận, packet lớn và tải cao

UDP giữ ranh giới datagram, nhưng một `DatagramPacket` có buffer quá nhỏ có thể nhận **payload bị cắt**. Trong ví dụ, buffer 2048 byte đủ cho probe 14 byte; với payload lớn hơn cần thiết kế giới hạn rõ ràng và tránh IP fragmentation nếu có thể. Nếu sender bắn dồn dập, OS socket receive buffer hoặc ứng dụng có thể làm rơi datagram; kiểm tra counters và thử giảm rate trước khi kết luận switch lỗi.

**Không biến `SO_RCVBUF` thành lời hứa “UDP không bao giờ mất”**. Kích thước buffer thực chịu OS và UDP vẫn best-effort.

## 11. Tự kiểm tra theo từng tình huống

**Tình huống A — `READY` nhưng không có `RECV`:** Receiver join đúng group và in READY. Sender chưa chạy. Có phải hạ tầng lỗi?  
**Trả lời:** Không. READY chỉ xác nhận việc setup local, không có nghĩa đã có nguồn gửi. Khởi chạy sender đúng interface và trong cửa sổ nhận.

**Tình huống B — `SENT` đủ năm dòng:** Sender log seq 1..5. Receiver log 1,2,4,5. Có thể khẳng định switch drop seq 3?  
**Trả lời:** Chưa. Sender log không đảm bảo packet lên dây; còn host stack, NIC, AP/switch, firewall, bộ đệm receiver và code. So capture theo cùng runId/seq mới khoanh vùng.

**Tình huống C — packet đến NIC B, Java in `APP_REJECT`:** Đây là lỗi ở đâu?  
**Trả lời:** Có bằng chứng **ứng dụng đã nhận datagram** và parser từ chối định dạng. Kiểm tra version, encoding, chuỗi payload, độ dài, schema; đồng thời tránh giả định mọi gói khác đều đến đủ.

**Tình huống D — sender và receiver cùng group nhưng receiver bind port `50018` thay vì `50017`:** Chỉ join group đúng IP đã đủ?  
**Trả lời:** Không. Socket phải bind UDP port tương ứng. Thành phần port trong tham số `joinGroup` không thay cho local bind.

**Tình huống E — unicast loopback OK nhưng multicast qua Wi-Fi không nhận:** Có thể loại bỏ firewall/AP/switch chưa?  
**Trả lời:** Không. Unicast loopback chỉ kiểm chứng một phần chức năng local; kiểm tra NIC, group join, Wi-Fi isolation, IGMP snooping/querier, firewall và capture.

**Tình huống F — máy A và B ở hai VLAN, TTL=1:** Vì sao unicast ping qua router OK mà multicast fail?  
**Trả lời:** TTL=1 và thiếu multicast routing/ACL/group state có thể chặn multicast qua router. Unicast connectivity không bảo đảm multicast forwarding.

**Tình huống G — IGMP report có xuất hiện trên capture:** Có đủ chứng minh UDP payload sẽ đến Java?  
**Trả lời:** Không. IGMP membership signaling khác đường đi dữ liệu UDP; còn sender, port, group, device forwarding, firewall, socket bind và parser.

**Tình huống H — hai máy cùng SSID nhưng không thấy packet:** Có nghĩa không cùng LAN?  
**Trả lời:** Không nhất thiết. AP có thể bật client isolation, chia VLAN hoặc quản lý multicast đặc biệt. Kiểm tra cấu hình SSID/VLAN và so sánh với kết nối Ethernet được cho phép.

**Tình huống I — receiver log duplicate=true cho cùng `runId+seq`:** Có chắc mạng tự nhân đôi packet?  
**Trả lời:** Không. Có thể sender gửi lại, nhiều đường/cơ chế multicast tạo bản sao hoặc app nhận trùng. Đối chiếu sender log và capture, không chỉ nhìn một log.

**Tình huống J — `joinGroup` ném `SocketException`:** Có nên sửa Java parser đầu tiên?  
**Trả lời:** Không. Chưa tới bước nhận payload. Ưu tiên xác minh interface, địa chỉ group IPv4, quyền socket, bind và hỗ trợ OS/driver; ghi nguyên loại lỗi và ngữ cảnh.

## 12. Tổng kết quy trình chẩn đoán

Một phép kiểm chứng multicast có giá trị khi nó trả lời được *packet mất ở ranh giới nào*, thay vì chỉ trả lời *có chạy hay không*:

```text
Java sender log SENT?
  │ no  -> kiểm tra mã gửi, group/port/NI, exception
  │ yes
  ▼
Capture ở NIC gửi thấy UDP multicast?
  │ no  -> kiểm tra source host / interface / route / capture location
  │ yes
  ▼
Capture ở NIC nhận thấy đúng group:port + runId?
  │ no  -> kiểm tra LAN/VLAN/AP/IGMP/switch/firewall/TTL/topology
  │ yes
  ▼
Java receiver nhận datagram?
  │ no  -> kiểm tra host firewall, bind/port, join/NI, namespace, socket
  │ yes
  ▼
Parser chấp nhận payload?
  │ no  -> kiểm tra schema, length, UTF-8, version, ID
  │ yes
  ▼
Ứng dụng xử lý đúng?
  │ no  -> kiểm tra business handler, queue/thread, trạng thái/ack
  │ yes -> đã xác nhận đường thử này ở thời điểm đo
```

Các mũi tên là **hướng ưu tiên điều tra**, không phải chứng minh nhân quả tuyệt đối. Mỗi capture/log chỉ phản ánh nơi và thời điểm quan sát.

Ghi nhớ nhanh:

- **Group + UDP port + đúng interface + local bind + membership** là nền tảng receiver.
- **Sender interface + TTL + group:port đúng** là nền tảng phép gửi.
- `joinGroup` và `send` không tạo delivery guarantee; UDP multicast có thể mất, trùng hoặc đảo thứ tự.
- **IGMP snooping, querier, AP isolation, VLAN, firewall, virtualization và routing** là các biến hạ tầng hay bị bỏ sót.
- **Quan sát theo `runId/seq` tại cả sender, capture A, capture B và receiver** giúp phân biệt lỗi trước socket, trên mạng và trong ứng dụng.
- Khi có yêu cầu nghiệp vụ quan trọng, thiết kế thêm cơ chế **ACK, timeout/retry, dedup và bảo mật**; đừng dựa vào multicast tự cung cấp tính tin cậy.

### Tài liệu tra cứu

- [Java 17 `MulticastSocket` — `joinGroup`, `leaveGroup`, `setNetworkInterface`, `setTimeToLive`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/MulticastSocket.html)
- [Java 17 `NetworkInterface` — `getNetworkInterfaces`, `isUp`, `supportsMulticast`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [Java 17 `DatagramPacket` và `DatagramSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html)
- [Cisco — Troubleshoot Multicast Networks with CLI Tools](https://www.cisco.com/c/en/us/support/docs/ip/ip-multicast/13726-57.html)
