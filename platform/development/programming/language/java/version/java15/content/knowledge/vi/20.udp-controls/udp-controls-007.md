# Giới hạn UDP payload, MTU và phân mảnh IP trong Java

> **Phạm vi:** Bài học thuộc chủ đề **Điều khiển UDP** của Java 15. Tập trung vào cách chọn kích thước một UDP datagram, phân biệt **giới hạn lý thuyết của giao thức UDP** với **Maximum Transmission Unit (MTU)** thực tế, cách IP fragmentation ảnh hưởng đến độ tin cậy và cách xử lý payload trong `DatagramSocket`/`DatagramChannel`. Các API và khuyến nghị dưới đây vẫn áp dụng trên JDK 17+ và môi trường Java hiện đại. Không dùng kỹ thuật lỗi thời, không giả định một Ethernet MTU là giới hạn chung của Internet.

## 1. Vấn đề: gửi được 60 KiB không có nghĩa gửi tốt

Ví dụ một chương trình Java muốn gửi một mảng:

~~~java
// Mảnh mã minh họa: socket, address và port đã hợp lệ.
byte[] data = new byte[60_000];
DatagramPacket packet =
        new DatagramPacket(data, data.length, address, port);
socket.send(packet);
~~~

Đoạn này có thể **gửi được** trên một số hệ điều hành và đường đi, nhưng không chứng minh rằng:

- Gói này không cần **phân mảnh IP**;
- Tất cả các mảnh đã đi qua router/NAT/firewall;
- Bên nhận đã có đủ bộ đệm ở OS và Java;
- Dữ liệu đến **đúng một lần, đúng thứ tự**, hoặc đến nơi;
- Đường đi tới một host khác cũng có MTU giống loopback;
- Lời gọi `send()` thành công là một xác nhận bên nhận đã xử lý.

UDP là giao thức **datagram-oriented**: mỗi lần gửi là một thông điệp UDP độc lập. Tuy nhiên, thông điệp đó vẫn phải được đóng trong IP và đi qua một đường truyền có MTU hữu hạn. Khi datagram quá lớn so với path MTU, hệ thống có thể phân mảnh, báo lỗi, bỏ gói hoặc không chuyển đến đích.

**Kết luận ban đầu:** chọn kích thước payload theo **path MTU và giao thức ứng dụng**, không theo “mảng `byte[]` trong Java chứa được bao nhiêu phần tử”.

## 2. Ba kích thước cần phân biệt

### 2.1. Application payload

Là các bytes mà ứng dụng Java đưa vào `DatagramPacket` hoặc `DatagramChannel.send`, ví dụ một message JSON mã hóa UTF-8 hay một frame âm thanh.

~~~text
UDP application payload: bytes do ứng dụng muốn gửi
~~~

### 2.2. UDP datagram

UDP thêm một **header 8 byte** gồm source port, destination port, length và checksum. Vì thế:

~~~text
UDP datagram size = 8-byte UDP header + application payload size
~~~

Không có khái niệm “UDP tự chia một datagram thành nhiều datagram nhỏ rồi tự ghép ở receiver”. Việc chia gói ở IP (nếu được thực hiện) là một cơ chế khác.

### 2.3. IP packet và MTU

IP thêm header bao quanh UDP datagram:

~~~text
IPv4 không options:
[20-byte IPv4 header][8-byte UDP header][application payload]

IPv6 không extension headers:
[40-byte IPv6 header][8-byte UDP header][application payload]
~~~

**MTU** thường nói tới kích thước tối đa của **IP packet** mà một link có thể mang **không cần IP fragmentation**. Trên Ethernet phổ biến, IP MTU thường là **1500 byte**, không bao gồm Ethernet MAC header/trailer trong cách tính IP MTU. MTU thực tế có thể khác: VPN, tunnels, PPPoE, overlay networks, jumbo frames, radio links và chính sách đường đi.

**Path MTU (PMTU)** là MTU hiệu dụng theo đường từ sender đến receiver; nhìn vào MTU của NIC bên gửi **không đủ** để biết PMTU xuyên qua tất cả hops.

## 3. Giới hạn lý thuyết của một UDP payload

### 3.1. IPv4: 65.507 byte là trần lý thuyết phổ biến

Trong IPv4 thông thường:

- Trường `Total Length` của IPv4 dài 16 bit, nên IP datagram tối đa **65.535 byte**.
- IPv4 header tối thiểu **20 byte**.
- UDP header dài **8 byte**.

Vậy:

~~~text
IPv4 max UDP application payload (không IP options)
= 65,535 - 20 - 8
= 65,507 bytes
~~~

Nếu IPv4 packet có **IP options** làm header lớn hơn 20 byte, trần payload thực tế giảm tương ứng.

Lưu ý rằng UDP còn có trường `Length` 16 bit, nhưng trong IPv4 thông thường chính giới hạn **IP Total Length** (bao gồm cả IPv4 header) khiến payload tối đa là **65.507**, không phải 65.527 byte.

### 3.2. IPv6: 65.527 byte trong trường hợp thông thường

Trong IPv6 thông thường:

- Trường `Payload Length` dài 16 bit, tối đa **65.535 byte**, **không tính IPv6 base header 40 byte**.
- UDP header dài **8 byte**.
- Nếu không có IPv6 extension header bổ sung:

~~~text
IPv6 max UDP application payload (không extension headers)
= 65,535 - 8
= 65,527 bytes
~~~

Các **extension headers** làm giảm chỗ còn lại cho UDP trong giới hạn này. IPv6 có cơ chế đặc biệt **jumbogram** (RFC 2675), nhưng đó là ngoại lệ có điều kiện, **không phải khả năng thường trực mà ứng dụng Java portable được quyền giả định**.

### 3.3. Hai giới hạn này không phải kích thước nên gửi

| Khái niệm | IPv4 | IPv6 |
| --- | ---: | ---: |
| UDP header | 8 byte | 8 byte |
| IP base header | Tối thiểu 20 byte | 40 byte |
| Max application UDP payload thông thường, không options/extensions | 65.507 byte | 65.527 byte |
| Có bảo đảm datagram tối đa đi qua mọi mạng không? | **Không** | **Không** |
| Có bảo đảm datagram tối đa đi một IP packet không phân mảnh không? | **Không** | **Không** |

**65.507/65.527 là giới hạn biểu diễn của giao thức**, không phải một khuyến nghị “cứ gửi bằng đúng kích thước này”.

## 4. Từ path MTU tính UDP payload không cần fragmentation

Công thức thông thường:

~~~text
maxUdpApplicationPayloadWithoutIpFragmentation =
    pathMtu
    - IP header size (kể cả options/extensions nếu có)
    - 8 bytes UDP header
~~~

Ví dụ tính với **MTU=1500**, IP không có headers bổ sung:

| Giao thức | PMTU | IP header | UDP header | UDP app payload tối đa |
| --- | ---: | ---: | ---: | ---: |
| IPv4 | 1500 | 20 | 8 | **1472 byte** |
| IPv6 | 1500 | 40 | 8 | **1452 byte** |
| IPv4 | 1400 | 20 | 8 | **1372 byte** |
| IPv6 | 1400 | 40 | 8 | **1352 byte** |
| IPv6 | 1280 | 40 | 8 | **1232 byte** |
| IPv4, giả định MTU 576 | 576 | 20 | 8 | **548 byte** |

Những con số này là **phép tính có điều kiện**, không phải constants toàn cầu:

- IPv4 options và IPv6 extension headers có thể làm header lớn hơn.
- Tunnel/overlay/VPN có thể làm **effective path MTU nhỏ hơn**.
- MTU của link đầu tiên không chứng minh PMTU của toàn đường đi.
- Nếu ứng dụng có header **riêng trong UDP payload** (message ID, sequence, checksum, encryption tag…), dung lượng data nghiệp vụ phải **trừ tiếp overhead của giao thức ứng dụng**.
- Con số 576 với IPv4 là một mốc trong hướng dẫn xử lý PMTU chưa biết; nó **không phải bảo đảm mọi link IPv4 hiện đại luôn có MTU 576**.

### Ví dụ về overhead tầng ứng dụng

Giả sử tính được một UDP payload budget là **1200 byte**. Protocol của bạn thêm:

- 4 byte message ID;
- 2 byte sequence;
- 2 byte total fragments;
- 8 byte timestamp;
- 16 byte authentication tag (nếu dùng một cơ chế xác thực phù hợp).

Tổng overhead **32 byte**, nên data thật mỗi application datagram chỉ nên tối đa:

~~~text
1200 - (4+2+2+8+16) = 1168 bytes
~~~

Đây là **ví dụ budgeting**, không phải một protocol bảo mật sẵn dùng. Authentication tag phải được tạo bằng một thiết kế mật mã đúng, và sender/receiver phải nhất quán về format.

## 5. 1200 byte, 1232 byte và “an toàn trên Internet”

Nhiều giao thức datagram hiện đại chọn kích thước ban đầu tương đối nhỏ, chẳng hạn **khoảng 1200 byte UDP payload**, để hạn chế rủi ro fragmentation trên các đường thông thường. Tuy nhiên:

- **1200 không phải mức UDP bảo đảm** chạy không fragmentation trên mọi IPv4/IPv6 path.
- **1232** là phép tính `1280 - 40 - 8` cho IPv6 với PMTU 1280 và **không có extension headers**; nếu có overhead bổ sung, payload budget giảm.
- Với IPv4, những đường có PMTU thấp hơn 1228 byte vẫn có thể không mang được payload UDP 1200 mà không phân mảnh.
- Một số giao thức, chẳng hạn QUIC, có **quy định riêng** về minimum datagram size/initial packet và PMTU discovery; không lấy một con số riêng của QUIC làm giới hạn của Java UDP nói chung.
- Để đạt throughput tốt trên path có MTU lớn, một protocol có thể **khám phá PMTU rồi tăng kích thước có kiểm soát**.

**Lựa chọn thực tiễn:** dùng budget ban đầu theo threat model, môi trường và yêu cầu tương thích; nếu đi qua Internet chưa biết PMTU, **đừng gửi gần 65 KB** chỉ vì OS cho phép. Khi cần gói lớn hơn, cân nhắc **DPLPMTUD theo RFC 8899** hoặc cơ chế PMTU phù hợp với giao thức.

## 6. IP fragmentation: một UDP datagram có thể thành nhiều IP packets

Giả sử IPv4 header 20 byte, UDP header 8 byte, MTU=1500; ứng dụng gửi **1600 byte UDP payload**.

~~~text
Application data = 1600 bytes
UDP datagram     = 8 + 1600 = 1608 bytes
IPv4 packet gốc  = 20 + 1608 = 1628 bytes
PMTU             = 1500 bytes
~~~

Nếu IPv4 fragmentation được cho phép và path thực hiện phân mảnh, một ví dụ đơn giản (không IPv4 options) có thể là:

~~~text
Fragment IP #1: IPv4 header 20 + IP payload 1480
               IP payload chứa UDP header 8 + app data 1472

Fragment IP #2: IPv4 header 20 + IP payload 128
               chứa 128 byte app data còn lại

Bên nhận:
  IP reassembly đủ các fragments
      -> UDP nhận lại một datagram có payload 1600 byte
      -> Java receive() nhận một datagram, KHÔNG phải 2 messages
~~~

Fragment offset trong IPv4 được đo theo đơn vị **8 byte**; ví dụ chia 1480 byte IP payload của fragment đầu là bội số 8 nên hợp lệ trong mô hình đơn giản.

**Quan trọng:** đây chỉ là sơ đồ khi **fragmentation được phép và xảy ra**. Nếu IPv4 DF (Don't Fragment) được đặt hoặc thiết bị/mạng không cho fragmentation, IP packet quá PMTU có thể **bị loại và phát tín hiệu lỗi**. Không đảm bảo Java `send()` luôn trả đúng một exception tên cố định: báo lỗi qua OS/socket/ICMP phụ thuộc cấu hình và hệ điều hành.

### IPv4 và IPv6 khác nhau

- **IPv4:** sender và một số router trung gian có thể phân mảnh IP packet khi được phép; DF khiến router không phân mảnh packet đó.
- **IPv6:** router **không phân mảnh** packet khi chuyển tiếp. Router không thể chuyển một packet quá MTU sẽ loại và có thể gửi **ICMPv6 Packet Too Big** để sender điều chỉnh. IPv6 **source** có thể tạo fragments bằng Fragment extension header trong những trường hợp phù hợp.
- Cả hai phiên bản đều có rủi ro lớn khi fragmented traffic đi qua NAT/firewall hoặc mất fragment.

Nếu một UDP datagram phải đi qua **N IP fragments**, chỉ cần **một fragment không đến hoặc bị loại** là IP thường không thể reassemble đầy đủ datagram. Bên nhận UDP do đó **không nhận được message hoàn chỉnh**. IP reassembly timeout hoặc giới hạn tài nguyên cũng có thể làm datagram mất.

## 7. Vì sao nên tránh phân mảnh IP?

Các lý do vẫn đúng theo **RFC 8085 — UDP Usage Guidelines** và **RFC 8900 — IP Fragmentation Considered Fragile**:

1. **Độ tin cậy:** mất một mảnh làm mất toàn datagram.
2. **Độ phức tạp reassembly:** receiver phải giữ fragments, quản lý identifiers, offsets và timeout.
3. **NAT/firewall:** nhiều thiết bị chặn hoặc xử lý fragmented traffic khác thường.
4. **Băng thông:** mỗi fragment thường mang thêm IP header; có thể tăng overhead.
5. **Hiệu năng và DoS:** fragment buffers tiêu tốn tài nguyên, có rủi ro tấn công bộ nhớ/reassembly.
6. **Quan sát lỗi khó:** ứng dụng chỉ thấy timeout/mất datagram, trong khi lỗi thật xảy ra ở IP path.
7. **Đường đi thay đổi:** một PMTU đúng trước đó có thể giảm khi routing/tunnel thay đổi.

Hệ quả: **không thiết kế protocol dựa vào việc IP luôn phân mảnh và tự ghép thành công**. Đó là cơ chế mạng có thể tồn tại, nhưng tính mong manh khiến UDP application phải chọn kích thước hợp lý.

### Phân biệt IP fragmentation với application chunking

| Đặc tính | IP fragmentation | Chia message thành nhiều UDP datagrams ở tầng ứng dụng |
| --- | --- | --- |
| Ai thực hiện? | IP stack/đường mạng, theo phiên bản IP và chính sách | Chính giao thức ứng dụng |
| Java có nhìn thấy từng phần? | Thông thường **không**; IP reassembles trước khi giao UDP | **Có**, mỗi datagram là một message UDP |
| Nếu mất một phần? | Toàn datagram IP gốc không được chuyển lên UDP | Ứng dụng có thể phát hiện phần thiếu và **chọn retransmit riêng**, nếu thiết kế |
| Có sẵn sequence và reassembly logic nghiệp vụ? | IP có cơ chế riêng nhưng không bảo đảm giao cho app | **Phải tự thiết kế** IDs, ordering, timeout, limits, validation |
| Có reliability mặc định? | **Không** | **Không**, trừ khi ứng dụng tự bổ sung |
| Khuyến nghị khi message lớn? | Tránh phụ thuộc fragmentation | Thiết kế protocol chunking/reassembly hoặc dùng giao thức khác |

Chia message ở tầng ứng dụng không tự giải quyết mọi vấn đề: nếu gửi quá nhiều UDP datagrams lớn không kiểm soát, bạn còn có rủi ro congestion, packet loss, reordering và DoS. Cần **flow/congestion control, bounds, retransmission và xác thực** tương ứng.

## 8. PMTU và Path MTU Discovery: vì sao con số có thể đổi?

**PMTU** là cỡ IP packet lớn nhất có thể đi qua đường tới đích mà không cần fragmentation (theo định nghĩa và điều kiện mạng). Mỗi hop có thể có MTU khác; tunnel cũng làm giảm dung lượng hiệu dụng.

~~~text
Sender --(MTU 1500)--> Router --(MTU 1400)--> VPN --(effective MTU 1360)--> Receiver
                                          |
                                      Path MTU ≈ 1360
~~~

Đây là ví dụ giả định, không phải số đo thực của một tuyến mạng. Nếu chỉ nhìn MTU 1500 của sender rồi gửi IPv4 UDP payload 1472, đường đi có thể không chấp nhận gói không phân mảnh ở đoạn 1360.

### 8.1. Classical PMTUD

- IPv4 có **ICMP Fragmentation Needed** trong trường hợp DF và gói lớn hơn next-hop MTU (RFC 1191).
- IPv6 có **ICMPv6 Packet Too Big** theo RFC 8200/8201.
- Sender hoặc IP stack điều chỉnh kích thước dựa trên thông tin nhận được.

Nhưng **ICMP có thể bị lọc** bởi firewall/middlebox, dẫn tới PMTU black hole: packet nhỏ thành công nhưng packet lớn biến mất hoặc bị timeout, và ứng dụng không thấy thông báo hữu ích.

### 8.2. Datagram Packetization Layer PMTU Discovery (DPLPMTUD)

**RFC 8899** xác định cách một datagram transport/protocol dùng **probe packets** và phản hồi ở tầng packetization để khám phá kích thước phù hợp, không bắt buộc phụ thuộc hoàn toàn vào ICMP.

Mô hình ý tưởng:

~~~text
1. Bắt đầu với datagram size bảo thủ.
2. Gửi probe có kích thước xác định và ID/ack theo protocol.
3. Nhận xác nhận đúng probe từ peer.
4. Chỉ tăng kích thước nếu có bằng chứng đường đi hỗ trợ.
5. Khi nghi ngờ black hole, giảm kích thước và thăm dò lại.
6. Theo dõi thay đổi đường đi và giữ chính sách congestion control.
~~~

**Không** chỉ thử gửi datagram 1472 byte và coi `DatagramSocket.send()` không ném exception là probe thành công. `send()` có thể chỉ chứng minh kernel chấp nhận input, không chứng minh peer đã nhận.

Một probe cần **phản hồi tầng ứng dụng**, ràng buộc ID/kích thước, timeout và chính sách an toàn/chống lạm dụng. Một ứng dụng không nhất thiết phải tự viết toàn bộ DPLPMTUD nếu protocol/library đã làm đúng; hãy tận dụng implementation tiêu chuẩn phù hợp.

## 9. Java DatagramSocket: kích thước packet gửi/nhận

### 9.1. Gửi datagram với DatagramPacket

~~~java
// Mảnh minh họa: socket, destination hợp lệ.
byte[] message = "hello".getBytes(StandardCharsets.UTF_8);
DatagramPacket packet = new DatagramPacket(
        message,
        message.length,
        destinationAddress,
        destinationPort
);
socket.send(packet);
~~~

`DatagramPacket.getLength()` là **số bytes payload UDP** được yêu cầu gửi, không bao gồm UDP header hoặc IP header. Nếu đặt offset/length, socket gửi đúng phần của array tương ứng.

Một `DatagramSocket.send()` có thể ném `IOException`/`SocketException` tùy vấn đề OS/network, nhưng thành công **không bảo đảm delivery, timing, order hoặc no-fragmentation**.

### 9.2. Bên nhận: receive buffer có thể cắt cụt message

~~~java
byte[] buffer = new byte[1024];
DatagramPacket incoming =
        new DatagramPacket(buffer, buffer.length);
socket.receive(incoming);

int actualLength = incoming.getLength();
~~~

Javadoc của `DatagramSocket.receive(DatagramPacket)` quy định: nếu message dài hơn **packet length/buffer được cung cấp**, message **bị cắt cụt**.

**Điều này hoàn toàn khác với IP fragmentation:**

- IP fragmentation: nhiều IP packets, khi ghép đầy đủ mới chuyển một UDP datagram lên socket.
- Java truncation: UDP datagram đã đến socket, nhưng **ứng dụng cung cấp bộ đệm quá nhỏ**, nên chỉ nhận được phần đầu, phần dư không thể lấy bằng lần `receive` kế tiếp.

Đừng nghĩ rằng đọc 1024 bytes đầu rồi gọi `receive` lần nữa sẽ nhận 200 bytes còn lại của cùng UDP message. UDP **giữ ranh giới datagram**, không hoạt động như TCP byte stream.

### 9.3. Tái sử dụng DatagramPacket phải reset length

Sau khi `receive(packet)` thành công, `packet.getLength()` phản ánh kích thước **message vừa nhận**. Khi dùng lại cùng packet, nên đặt lại chiều dài tối đa cho lần receive tiếp theo:

~~~java
// Mảnh minh họa:
DatagramPacket packet =
        new DatagramPacket(new byte[2048], 2048);

socket.receive(packet);
int firstLength = packet.getLength();

// Dùng lại packet để nhận tối đa 2048 bytes.
packet.setLength(packet.getData().length);
socket.receive(packet);
int secondLength = packet.getLength();
~~~

Nếu không reset, Java có thể tiếp tục coi giới hạn `length` là giá trị sau lần receive trước; một datagram lớn hơn lần trước có thể bị cắt cụt dù mảng còn chỗ.

**Lưu ý thêm:** `DatagramPacket.getOffset()` và `getLength()` mô tả vùng dữ liệu hợp lệ; không tự coi toàn bộ buffer là dữ liệu vừa nhận.

### 9.4. SO_SNDBUF/SO_RCVBUF không phải PMTU

Hai API:

~~~java
socket.setSendBufferSize(256 * 1024);
socket.setReceiveBufferSize(256 * 1024);
~~~

chỉ gửi **hint** về kích thước OS socket buffers (`SO_SNDBUF`, `SO_RCVBUF`). Theo Javadoc, kích thước thực được OS quyết định; việc gửi/nhận datagram lớn hơn SO_SNDBUF/SO_RCVBUF có thể phụ thuộc implementation.

**Tăng hai buffer này không làm tăng MTU của link/PMTU của đường đi.** Cũng không tự làm `DatagramPacket` chứa nhiều bytes hơn: receiver vẫn cần cấp phát `byte[]` đủ dài và truyền length thích hợp.

Trong hệ thống tốc độ cao, socket receive buffer quá nhỏ có thể gây **drop do hàng đợi đầy**; đó là một nguyên nhân mất datagram khác với packet quá PMTU.

## 10. Chương trình Java 17+ chạy được: giới hạn tính toán, UDP loopback và truncation

Chương trình sau cố ý **không đo fragmentation**: địa chỉ loopback có MTU và network behavior phụ thuộc hệ điều hành, nên gửi UDP trên loopback không chứng minh PMTU của Internet. Ví dụ chỉ xác nhận **cách tính budget** và **hành vi API Java khi receiver quá nhỏ**.

Lưu file **`UdpMtuDemo.java`**:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.util.Arrays;

public final class UdpMtuDemo {
    private static int budget(int pathMtu, int ipHeaderBytes) {
        return pathMtu - ipHeaderBytes - 8;
    }

    private static void send(
            DatagramSocket sender,
            InetSocketAddress destination,
            byte[] bytes) throws Exception {
        DatagramPacket packet =
                new DatagramPacket(bytes, bytes.length, destination);
        sender.send(packet);
    }

    public static void main(String[] args) throws Exception {
        System.out.println("IPv4 at MTU 1500: " + budget(1500, 20));
        System.out.println("IPv6 at MTU 1500: " + budget(1500, 40));
        System.out.println("IPv6 at MTU 1280: " + budget(1280, 40));

        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (DatagramSocket receiver =
                     new DatagramSocket(new InetSocketAddress(
                             loopback, 0));
             DatagramSocket sender =
                     new DatagramSocket(new InetSocketAddress(
                             loopback, 0))) {

            receiver.setSoTimeout(3000);
            InetSocketAddress destination =
                    new InetSocketAddress(loopback,
                            receiver.getLocalPort());

            byte[] original = new byte[1200];
            for (int i = 0; i < original.length; i++) {
                original[i] = (byte) (i % 251);
            }

            // Gửi 1200 bytes, nhận bằng mảng đủ dài.
            send(sender, destination, original);
            DatagramPacket full =
                    new DatagramPacket(new byte[1500], 1500);
            receiver.receive(full);

            byte[] received = Arrays.copyOfRange(
                    full.getData(),
                    full.getOffset(),
                    full.getOffset() + full.getLength());

            System.out.println(
                    "loopback received length: " + full.getLength());
            System.out.println(
                    "loopback bytes match: "
                            + Arrays.equals(original, received));

            // Gửi 64 bytes, nhưng caller chỉ cấp 32 bytes.
            send(sender, destination, new byte[64]);
            DatagramPacket tooSmall =
                    new DatagramPacket(new byte[32], 32);
            receiver.receive(tooSmall);
            System.out.println(
                    "truncated receive length: "
                            + tooSmall.getLength());

            // Reuse: lần đầu 5 bytes, lần sau 64 bytes.
            DatagramPacket reused =
                    new DatagramPacket(new byte[128], 128);
            send(sender, destination, new byte[5]);
            receiver.receive(reused);
            System.out.println(
                    "reuse first length: " + reused.getLength());

            reused.setLength(reused.getData().length);
            send(sender, destination, new byte[64]);
            receiver.receive(reused);
            System.out.println(
                    "reuse second length: " + reused.getLength());
        }
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 17+:

~~~bash
javac UdpMtuDemo.java
java UdpMtuDemo
~~~

**Stdout kỳ vọng trên môi trường loopback IPv4 hoạt động bình thường:**

~~~text
IPv4 at MTU 1500: 1472
IPv6 at MTU 1500: 1452
IPv6 at MTU 1280: 1232
loopback received length: 1200
loopback bytes match: true
truncated receive length: 32
reuse first length: 5
reuse second length: 64
~~~

Giải thích kết quả:

1. `budget(1500,20)` trả **1472** và `budget(1500,40)` trả **1452**; đây là **phép tính giả định headers**, không đo route.
2. `127.0.0.1` buộc demo dùng IPv4 loopback; socket receiver bind vào port do OS chọn (`0`).
3. Datagram đầu tiên gửi **1200 bytes**, receiver có buffer dài **1500**, nên `getLength()` là 1200 và bytes khớp.
4. Datagram thứ hai chứa **64 bytes**, nhưng `DatagramPacket` phía nhận chỉ cho tối đa **32 bytes**, nên message bị cắt cụt tại receiver. Đây là lỗi ứng dụng, không phải quan sát IP fragmentation.
5. `reused` nhận lần đầu 5 bytes; trước lần nhận thứ hai, `setLength(128)` đặt lại chiều dài tối đa. Vì vậy datagram 64 bytes tiếp theo được nhận đầy đủ.

Chương trình dùng `setSoTimeout(3000)` để tránh chờ vô hạn khi môi trường không cho loopback UDP. Nếu có firewall/sandbox chặn local UDP hoặc scheduler trì hoãn quá lâu, demo có thể ném `SocketTimeoutException` — đó là điều kiện vận hành, không phải thay đổi về công thức MTU.

**Không** thay địa chỉ sang host Internet rồi kỳ vọng luôn có stdout trên: UDP không đảm bảo delivery, và path MTU/firewall/port reachability sẽ khác.

Nếu compiler đang dùng hỗ trợ target Java 15, có thể biên dịch với:

~~~bash
javac --release 15 UdpMtuDemo.java
~~~

Các API sử dụng là API Java còn được hỗ trợ, không cần tính năng preview.

## 11. DatagramChannel và ByteBuffer: phần thừa cũng có thể bị loại

Java NIO cung cấp `java.nio.channels.DatagramChannel`. Ví dụ:

~~~java
// Mảnh minh họa: channel đã bind và ở blocking mode.
ByteBuffer dst = ByteBuffer.allocate(1200);
SocketAddress peer = channel.receive(dst);

if (peer != null) {
    dst.flip();
    int receivedBytes = dst.remaining();
    // Đọc đúng receivedBytes bytes từ dst.
}
~~~

Ở chế độ **non-blocking**, `receive(dst)` có thể trả `null` nếu chưa có datagram. Khi có datagram, nó ghi vào buffer bắt đầu tại `position` hiện tại.

Theo Javadoc, nếu datagram dài hơn `dst.remaining()`, **phần dư bị loại bỏ**. Do đó:

- `ByteBuffer.capacity()` lớn không có ích nếu `position/limit` khiến `remaining()` nhỏ.
- `flip()` được gọi **sau receive** để chuyển sang đọc những bytes vừa nhận, không phải trước khi receive vào buffer mới.
- **Read-only ByteBuffer** không phải vùng nhận hợp lệ cho `receive(dst)`.
- `DatagramChannel.receive` không tự làm PMTU discovery hay tự chia message lớn thành những message nhỏ.

### Hành vi đích của ByteBuffer

~~~text
Trước receive:
  capacity=1500, position=0, limit=1500 -> remaining=1500

Giả sử datagram 1200 bytes đến:
  position=1200, limit=1500

Sau flip():
  position=0, limit=1200 -> đọc đúng 1200 bytes
~~~

Nếu bạn quên `clear()`/`compact()` và tái dùng buffer có `remaining()` quá nhỏ cho lần receive kế tiếp, ứng dụng có thể vô tình cắt cụt message. **Kích thước ByteBuffer và MTU là hai vấn đề khác nhau.**

## 12. Nếu message nghiệp vụ lớn hơn UDP payload budget

Giả sử cần gửi một tài liệu 80 KiB nhưng muốn UDP payload mỗi datagram không vượt quá một budget bảo thủ, ví dụ 1200 byte. Không thể gửi 80 KiB dưới dạng **một UDP datagram thông thường** (vượt trần protocol và thường vượt MTU). Có các lựa chọn kiến trúc.

### 12.1. Chọn giao thức reliable nếu yêu cầu bài toán

Nếu dữ liệu phải đến **đầy đủ, đúng thứ tự và đáng tin cậy** (file transfer, cập nhật cấu hình quan trọng), thường nên cân nhắc giao thức có sẵn như TCP hoặc một implementation QUIC phù hợp, thay vì tự làm lại reliability/congestion control trên UDP.

Không mặc định UDP “nhanh hơn” TCP trong mọi trường hợp. Rủi ro loss, retransmission và flow control mới quyết định kết quả thực tế.

### 12.2. Application-layer chunking nếu thật sự cần UDP

Nếu vẫn dùng UDP, có thể tách message thành **nhiều datagrams độc lập** với header của ứng dụng:

~~~text
messageId | chunkIndex | totalChunks | payloadLength | chunkBytes
~~~

Bên nhận cần:

1. Xác định các datagrams cùng một message bằng **messageId**.
2. Kiểm tra `chunkIndex` trong phạm vi và `totalChunks` không vượt giới hạn.
3. Xử lý datagrams **đến sai thứ tự**.
4. Chống bản sao trùng, kiểm tra chunk bị thiếu.
5. Giới hạn **tổng bytes và số messages đang chờ ghép** để tránh DoS.
6. Hủy trạng thái sau timeout và có cơ chế GC.
7. Kiểm tra integrity/authenticity của message/chunks nếu threat model yêu cầu.
8. Có ACK/NACK, retransmission, flow/congestion control nếu cần reliability.
9. Chỉ giao message hoàn chỉnh cho nghiệp vụ khi đủ các điều kiện.

RFC 8085 khuyến nghị nếu ứng dụng chia message thành nhiều UDP datagrams, thiết kế để mỗi datagram có thể được **nhận độc lập** và, nếu triển khai reliability, **retransmit độc lập**.

**Cần trừ application header khỏi budget**. Nếu 1200 byte là UDP payload budget và header riêng dài 20 bytes, chunk data tối đa là 1180 byte, không phải 1200.

### 12.3. Không nhầm chunking với IP fragmentation

Mỗi chunk ứng dụng là **một UDP datagram mới**, có UDP header riêng và có thể nhận/ACK riêng. Ngược lại, IP fragments là các mảnh của **một IP packet nguyên thủy**; Java UDP thường chỉ nhận datagram sau khi IP reassembly hoàn tất.

Ứng dụng chunking không tự bảo đảm không IP fragmentation: **mỗi UDP datagram chunk vẫn phải đủ nhỏ so với PMTU**.

## 13. Congestion control và tốc độ gửi

UDP bản thân không có congestion control/retransmission/flow control theo kiểu TCP. Một ứng dụng không thể chỉ tăng tốc gửi tối đa vì packet nhỏ hơn MTU.

Rủi ro:

- Burst datagrams làm đầy OS send/receive queues;
- Router/link drop vì congestion;
- Receiver xử lý không kịp;
- Retry quá nhanh làm tình hình tệ hơn;
- Amplification khi server phản hồi dữ liệu lớn cho địa chỉ nguồn chưa xác minh.

Hướng xử lý:

- Rate limit theo peer hoặc session;
- Pacing thay vì burst không kiểm soát;
- Giới hạn outstanding messages và reassembly buffers;
- Backpressure/ACK phù hợp;
- Retransmission với timeout/backoff và trần số lần thử;
- Congestion control thân thiện với luồng khác;
- Xác thực peer và chống reflection/amplification nếu protocol tiếp xúc Internet.

**Chọn datagram nhỏ giảm nguy cơ IP fragmentation, nhưng không biến UDP thành giao thức reliable.**

## 14. Chẩn đoán: phân biệt các kiểu mất/truncated datagram

| Hiện tượng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| `send()` thành công nhưng bên nhận không thấy | UDP loss, firewall, ICMP filtered, path MTU, sai port/IP | Packet capture, reachability, PMTU, server logs, ACK ở application |
| Packet nhỏ qua, packet lớn timeout | PMTU black hole, fragments bị drop | Probe sizes, ICMP Packet Too Big, firewall/VPN/tunnel |
| Bên nhận chỉ có đúng 512 bytes dù sender gửi 1000 | `DatagramPacket` length 512 hoặc `ByteBuffer.remaining()==512` | User-space receive buffer/truncation |
| Bên nhận có nhiều packets mỗi cái 1000 bytes | Sender chia ứng dụng thành nhiều UDP datagrams | Message IDs, ordering, reassembly protocol |
| Receiver hoàn toàn không thấy IP fragments | Driver, OS, capture location/offload, middlebox | Capture đúng interface, phân biệt reassembly và capture |
| Receiver queue mất datagrams khi burst | SO_RCVBUF không đủ, CPU/app xử lý chậm | OS drops, receive queue, rate/pacing |
| Datagram lớn báo exception trên sender | OS/protocol limit, PMTU/socket buffers | Exception thực, kích thước bytes, IP family, options |
| Tăng `SO_SNDBUF` không giải quyết | PMTU độc lập socket queue | Kích thước IP headers, route, transport |
| Loopback gửi 60 KiB thành công nhưng Internet mất | Loopback MTU/path khác | Không suy ra khả năng qua WAN từ loopback |
| IPv4 chạy, IPv6 lỗi | IPv6 headers/PMTU/ICMPv6 behavior khác | Address family, extension headers, PMTU, firewall |
| Chỉ một datagram rất lớn bị mất | Mất một IP fragment hoặc policy chặn fragments | Giảm kích thước; DPLPMTUD; capture |
| App nghĩ có thêm “phần còn lại” ở receive lần hai | Nhầm UDP với TCP stream | Truncation làm phần dư của datagram bị loại |

### Vì sao packet capture phải được diễn giải cẩn thận?

Một công cụ như Wireshark/tcpdump có thể thấy:

- Nhiều IPv4 fragments trên một đoạn path;
- Một UDP datagram sau khi OS đã reassemble;
- Những gói lớn do tính năng offload của NIC/OS khiến capture không giống wire size;
- UDP datagrams độc lập do ứng dụng tự chunk.

Vì vậy, cần **xác định capture point** (sender host, NIC, router, receiver) và hiểu checksum/segmentation offload, thay vì kết luận chỉ từ một ảnh chụp màn hình rằng packet chắc chắn đi trên wire như vậy.

### Gợi ý phép đo có căn cứ

- Ghi rõ kích thước **application bytes** và loại IP (IPv4/IPv6).
- Ghi path/network interface, VPN/tunnel và PMTU nếu biết.
- Theo dõi tỷ lệ delivered/acked theo datagram size, không chỉ `send()` success.
- Quan sát ICMP Fragmentation Needed / ICMPv6 Packet Too Big khi có.
- Thử nhiều sizes có kiểm soát; không flood/DoS.
- Quan sát OS socket drops và số bytes nhận được bằng `getLength()`/`ByteBuffer.position()`.
- Test trên **cùng loại đường đi thực tế**; localhost không thay thế WAN.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Vì sao sai | Cách nghĩ đúng |
| --- | --- | --- |
| “UDP payload tối đa luôn 65.535 bytes” | 16-bit length còn gồm headers và IP giới hạn | IPv4 thông thường tối đa 65.507, IPv6 65.527 nếu không ext |
| “MTU là giới hạn byte[] của Java” | MTU thuộc IP path, không thuộc mảng Java | Tính từ path MTU và header overhead |
| “Ethernet MTU 1500 nghĩa UDP payload 1500” | Cần trừ IP và UDP headers | IPv4 1472, IPv6 1452 trong giả định thường |
| “IPv4 và IPv6 có cùng kích thước header” | Base headers 20 vs 40 | Tính theo đúng IP version |
| “IPv4 payload 1472 luôn không fragment” | Path MTU có thể nhỏ hơn 1500 | PMTU hoặc conservative budget + probing |
| “IPv6 routers tự fragmentation” | IPv6 routers không fragment | Sender xử lý PMTU; IPv6 source có thể fragment |
| “Phân mảnh IP tạo nhiều UDP receive events” | Reassembly thuộc IP layer | Một datagram hoặc mất toàn bộ |
| “Mất một fragment vẫn nhận phần còn lại” | UDP datagram không hoàn chỉnh | Không có message để giao lên UDP |
| “Đủ kích thước socket buffer thì vượt được MTU” | SO_SNDBUF/SO_RCVBUF khác PMTU | Queue buffers và path constraints độc lập |
| “`receive` trả 512 bytes thì sender chỉ gửi 512” | Có thể app truncation | Kiểm tra received DatagramPacket length/capacity |
| “Gọi `receive` lần hai lấy tiếp datagram trước” | UDP không phải byte stream | Phần dư của datagram đã bị loại |
| “Tăng timeout giúp gói quá PMTU đến nơi” | Không sửa khả năng truyền qua path | Sửa packet size và PMTU handling |
| “Gửi loopback thành công chứng minh Internet tốt” | Loopback và WAN path khác | Test trên đường đi thực tế |
| “1200 bytes an toàn tuyệt đối mọi mạng” | Vẫn có overhead/path đặc biệt | Là một baseline có điều kiện, không guarantee |
| “`send()` success bảo đảm bên nhận đã nhận” | UDP không có delivery acknowledgment | ACK/probe tầng ứng dụng nếu cần |
| “Application chunking là luôn reliable” | Thiếu ACK/retransmit/order/congestion | Thiết kế đầy đủ protocol nếu cần |

## 16. Bài tập thực hành và đáp án

**Bài 1.** Với IPv4 header 20 bytes, UDP header 8 bytes và PMTU 1500, app có thể đặt bao nhiêu bytes trong UDP payload để không vượt MTU?

**Đáp án:** `1500 - 20 - 8 = 1472 bytes`, giả sử không có IP options/tunnel overhead khác.

**Bài 2.** Với IPv6 base header 40 bytes, UDP header 8 bytes và PMTU 1280, payload budget là bao nhiêu?

**Đáp án:** `1280 - 40 - 8 = 1232 bytes` nếu không có IPv6 extension headers hay overhead khác.

**Bài 3.** Vì sao “65.535 bytes” không phải max UDP payload của IPv4?

**Đáp án:** IPv4 Total Length giới hạn cả IP packet ở 65.535; trừ tối thiểu 20-byte IPv4 header và 8-byte UDP header còn **65.507 bytes**.

**Bài 4.** Một UDP payload 1600 bytes cần đi qua IPv4 PMTU 1500. Nếu IP fragmentation được phép, có thể xảy ra điều gì?

**Đáp án:** IP có thể tách thành nhiều fragments, receiver reassembles trước khi giao **một UDP datagram** cho ứng dụng; nếu thiếu fragment, datagram thường bị mất. Nếu DF hoặc policy không cho fragmentation, gói có thể bị bỏ và báo lỗi PMTU.

**Bài 5.** Receiver Java cấp `DatagramPacket(new byte[512],512)`, sender gửi 900 bytes. Có thể gọi receive lần tiếp theo để lấy 388 bytes còn lại không?

**Đáp án:** Không. Datagram sẽ bị **truncated** ở receiver, phần dư không trở thành datagram tiếp theo.

**Bài 6.** Tại sao `DatagramPacket.setLength(buffer.length)` có ích khi tái dùng packet?

**Đáp án:** Sau receive, `getLength()` phản ánh kích thước datagram vừa nhận. Reset đảm bảo lần sau có đủ length allowance để nhận datagram lớn hơn, nếu backing array đủ chỗ.

**Bài 7.** `socket.setSendBufferSize(1_000_000)` có đảm bảo gửi một UDP datagram 65 KB qua đường PMTU 1400 không phân mảnh không?

**Đáp án:** Không. SO_SNDBUF là hint cho OS socket queue, không phải cấu hình path MTU. Datagram lớn có thể fragment hoặc không đến.

**Bài 8.** IPv6 router gặp packet lớn hơn outgoing link MTU có được chia IP fragments và forward không?

**Đáp án:** Không. IPv6 router không thực hiện fragmentation; nó phải bỏ packet không thể chuyển và có thể gửi ICMPv6 Packet Too Big. Source có thể điều chỉnh/fragment trong điều kiện IPv6 cho phép.

**Bài 9.** Application chunking khác IP fragmentation thế nào khi mất một phần?

**Đáp án:** IP fragments thuộc **một** UDP datagram gốc; thiếu mảnh làm mất datagram. Các application chunks là những UDP datagrams độc lập, vì vậy app có thể nhận các phần còn lại và tự yêu cầu retransmit phần thiếu nếu protocol hỗ trợ.

**Bài 10.** Một file 100 KiB phải truyền chính xác, đúng thứ tự và có congestion control. Có nên tự dùng một UDP datagram 100 KiB không?

**Đáp án:** Không thể trong giới hạn UDP thông thường, và cũng không hợp lý với PMTU. Cân nhắc TCP/QUIC được triển khai đúng hoặc một protocol chunking + reliability/congestion control được thiết kế rõ ràng.

**Bài 11.** Một ứng dụng gửi UDP payload 1200 bytes. Có bảo đảm nó không bị fragmentation trên mọi IPv4 path không?

**Đáp án:** Không. Nếu PMTU dưới 1228 bytes (20-byte IPv4 + 8-byte UDP + 1200 bytes) hoặc có IP options/extra overhead, datagram vẫn có thể vượt PMTU.

**Bài 12.** Vì sao `DatagramChannel.receive(buffer)` có thể cắt cụt datagram dù `buffer.capacity()==4096`?

**Đáp án:** API sử dụng **`buffer.remaining()`**. Nếu `position/limit` chỉ còn 100 bytes, phần dư của datagram bị loại. Hãy quản lý buffer state đúng.

**Bài 13.** Khi chỉ có `send()` không ném exception, liệu đủ kết luận PMTU probe thành công?

**Đáp án:** Không. Phải có phản hồi/ACK tầng ứng dụng chứng minh peer nhận được probe tương ứng, theo một cơ chế thăm dò đáng tin cậy.

**Bài 14.** Vì sao packet loss tăng khi gửi datagrams bị chia nhiều IP fragments?

**Đáp án:** Bất kỳ fragment nào mất cũng có thể khiến toàn datagram không được reassemble. NAT/firewall/reassembly timeout làm rủi ro thêm cao.

## 17. Checklist thiết kế UDP để đưa vào sản phẩm

1. Xác định **số bytes của application payload**, không nhầm byte count với số ký tự Java `String`.
2. Biết dùng **IPv4, IPv6 hay dual-stack** và tính đúng IP/UDP headers.
3. Xem MTU/PMTU của **path thực tế**, không chỉ local NIC.
4. Trừ IP options/IPv6 extensions, tunnel overhead và application framing.
5. Chọn một **baseline datagram size** bảo thủ; không coi 1200 hoặc 1472 là giới hạn chung.
6. Nếu cần tối ưu kích thước, cân nhắc **DPLPMTUD (RFC 8899)** với probe/ACK thích hợp.
7. Tránh thiết kế phụ thuộc IP fragmentation, nhất là qua Internet/NAT/firewall.
8. Đảm bảo receive `DatagramPacket`/`ByteBuffer` đủ lớn cho message tối đa dự kiến.
9. Khi tái dùng `DatagramPacket`, reset `setLength` trước lần receive tiếp theo.
10. Không dùng `SO_SNDBUF/SO_RCVBUF` như nút tăng MTU.
11. Nếu app tự chunk, có message ID, sequence, length, dedup, reassembly bounds/timeout.
12. Nếu cần reliable delivery/order, thiết kế ACK/retransmit/congestion control hoặc chọn TCP/QUIC.
13. Giới hạn số messages/chunks chờ ghép để chống DoS và memory exhaustion.
14. Xem xét xác thực/integrity phù hợp; UDP checksum không đủ xác thực nguồn nghiệp vụ.
15. Kiểm thử timeout, packet loss, reordering, duplicates, IPv4/IPv6 và network tunnel.
16. Đo send/receive, packet capture và OS drops thay vì suy luận từ `send()` success.
17. Đừng dùng localhost để khẳng định MTU Internet hoặc độ tin cậy WAN.
18. Quan sát PMTU khi routing/network thay đổi và có chiến lược giảm kích thước an toàn.

## 18. Nguồn chính thức và kiến thức còn áp dụng

- **RFC 768 — User Datagram Protocol:** https://www.rfc-editor.org/rfc/rfc768
- **RFC 8085 — UDP Usage Guidelines (Best Current Practice):** https://www.rfc-editor.org/rfc/rfc8085
- **RFC 8899 — Datagram Packetization Layer Path MTU Discovery (DPLPMTUD):** https://www.rfc-editor.org/rfc/rfc8899
- **RFC 8900 — IP Fragmentation Considered Fragile:** https://www.rfc-editor.org/rfc/rfc8900
- **RFC 8200 — Internet Protocol, Version 6 (IPv6):** https://www.rfc-editor.org/rfc/rfc8200
- **RFC 8201 — Path MTU Discovery for IPv6:** https://www.rfc-editor.org/rfc/rfc8201
- **RFC 1191 — IPv4 Path MTU Discovery:** https://www.rfc-editor.org/rfc/rfc1191
- **Oracle Java SE 17 — `DatagramSocket`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html
- **Oracle Java SE 17 — `DatagramPacket`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html
- **Oracle Java SE 17 — `DatagramChannel`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html

**Kết luận:** UDP payload có **trần protocol** (IPv4 thông thường **65.507 bytes**, IPv6 **65.527 bytes**), nhưng kích thước nên gửi phải dựa vào **PMTU và tổng overhead** của IP, UDP, extensions/tunnels và application framing. Một đường có MTU 1500 thường cho phép **1472-byte IPv4 payload** hoặc **1452-byte IPv6 payload** nếu không có headers bổ sung. Gói quá PMTU dễ gặp **IP fragmentation**, vốn mong manh và gây mất toàn datagram khi thiếu một mảnh. Trong Java, phải phân biệt fragmentation ở IP với **truncation** do `DatagramPacket`/`ByteBuffer` phía nhận quá nhỏ. Thiết kế datagram có giới hạn hợp lý, thăm dò PMTU khi cần, không phụ thuộc IP fragmentation, và bổ sung reliability/congestion control khi yêu cầu nghiệp vụ đòi hỏi.
