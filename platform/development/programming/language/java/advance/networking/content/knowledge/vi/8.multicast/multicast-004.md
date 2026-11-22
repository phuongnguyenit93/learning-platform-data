# Phạm vi IPv4, IPv6 và số chặng bằng multicast TTL trong Java

**Multicast** cho phép một bên gửi một datagram đến *nhóm* địa chỉ IP, để những máy đã đăng ký nhận nhóm phù hợp có thể nhận bản sao trong phạm vi mạng cho phép. Từ góc nhìn ứng dụng Java, câu hỏi khó nhất thường không phải “gửi byte thế nào?”, mà là **gói được phép đi tới đâu, bị chặn ở đâu, và phải chọn interface/TTL/hop limit ra sao?**

Có hai ý tưởng rất dễ nhầm:

1. **Phạm vi địa chỉ nhóm (multicast scope):** dùng **dải địa chỉ và ranh giới quản trị** ở IPv4; dùng **trường scope được mã hóa ngay trong địa chỉ nhóm** ở IPv6. Nó nói nhóm thuộc phạm vi mạng nào về mặt ngữ nghĩa và quy tắc chuyển tiếp.
2. **Giới hạn số chặng (IPv4 TTL / IPv6 Hop Limit):** thuộc **trường header của từng gói**, cho biết gói còn được phép đi qua bao nhiêu bước chuyển tiếp IP trước khi hết hạn. Nó **không** tự cấp quyền vượt phạm vi địa chỉ, không đảm bảo có router multicast và không đo độ trễ.

Một gói có TTL rất lớn nhưng dùng địa chỉ IPv4 `224.0.0.1` vẫn không được router multicast chuyển tiếp ra ngoài link. Một gói IPv6 gửi đến nhóm link-local `ff12::1234` cũng không trở thành global chỉ vì Hop Limit lớn. Ngược lại, một nhóm được định nghĩa ở phạm vi rộng vẫn có thể chỉ đến link cục bộ khi gói mang TTL/Hop Limit = 1.

Bài này thuộc module **Java Advance - networking**, chủ đề cha **Multicast**. Mục tiêu là hiểu chính xác IPv4/IPv6 scope, cách router tiêu thụ TTL/Hop Limit và cách cấu hình trong Java 17+ với `MulticastSocket`, `DatagramChannel` và `StandardSocketOptions.IP_MULTICAST_TTL`.

## 1. Kiến thức nền: multicast vận hành qua các lớp nào?

Một kịch bản điển hình:

~~~text
Ứng dụng gửi UDP
   |
   | đích: nhóm multicast + UDP port
   v
IP multicast datagram
   |
   | family IPv4 hay IPv6, outgoing network interface
   | TTL (IPv4) hoặc Hop Limit (IPv6)
   v
LAN / router multicast / chính sách phạm vi / firewall
   |
   +-- host A đã tham gia nhóm, port phù hợp -> có thể nhận
   +-- host B đã tham gia nhóm, port phù hợp -> có thể nhận
   +-- host C không tham gia nhóm        -> thường không được giao datagram
   +-- mạng ngoài scope hoặc hết hop    -> không được chuyển tiếp
~~~

**Multicast IP không phải TCP.** Ứng dụng Java thường gửi multicast bằng **UDP datagrams**. IP multicast không tự đảm bảo datagram đến tất cả subscriber, không tự sắp thứ tự, không tự gửi lại, không tự chống trùng hoặc bảo mật nội dung. Nếu ứng dụng cần độ tin cậy hoặc xác thực, phải thiết kế thêm ở tầng ứng dụng hoặc dùng giao thức phù hợp.

Có ba quyết định riêng biệt cần đồng thời đúng:

- **Nhóm (`group address`) và UDP port:** người gửi gửi đến đúng nhóm/port, người nhận tham gia nhóm trên interface phù hợp và bind port nhận đúng.
- **Hướng giao tiếp (`NetworkInterface`):** host có nhiều NIC (LAN, Wi-Fi, VPN, container, IPv4/IPv6) phải chọn đúng nơi gửi và nhận; để OS chọn mặc định có thể đi sai đường.
- **Ràng buộc phạm vi và chặng:** nhóm thuộc scope hợp lệ, số chặng cho phép đủ nhưng không quá rộng, router/switch/firewall thực sự hỗ trợ đường truyền multicast.

Ví dụ, server và client ở cùng subnet nhưng không nhận được multicast có thể do chưa join group, chọn nhầm NIC, firewall, Wi-Fi multicast filtering, IGMP/MLD snooping hoặc socket bind port sai — không nhất thiết là TTL thấp. Chỉ tăng TTL hiếm khi giải quyết được vấn đề trên **cùng link**.

## 2. IPv4: không gian địa chỉ nhóm và scope

### 2.1. IPv4 multicast là `224.0.0.0/4`

IPv4 multicast sử dụng nhóm địa chỉ từ **`224.0.0.0` đến `239.255.255.255`**, thường gọi là class D theo cách phân loại lịch sử. Dải này dành cho **địa chỉ đích nhóm multicast**, không phải địa chỉ nguồn thông thường của host.

Không được hiểu rằng mọi địa chỉ trong `224.0.0.0/4` đều tự do cấp cho ứng dụng. Nhiều block dành cho giao thức điều khiển, được IANA phân bổ, reserved, source-specific multicast (SSM) hoặc quản trị nội bộ.

| Dải IPv4 | Ý nghĩa chính | Ghi chú thực hành |
| --- | --- | --- |
| `224.0.0.0/24` | Local Network Control Block | Dành cho điều khiển trên link; router multicast **không chuyển tiếp** các datagram tới dải này, bất kể TTL |
| `224.0.1.0/24` và các block khác đã cấp | Nhóm/giao thức được đăng ký | Không tùy tiện chọn địa chỉ đã có ứng dụng khác sở hữu |
| `232.0.0.0/8` | Source-Specific Multicast (SSM) IPv4 | Mô hình tham gia theo **nhóm và nguồn**, không đồng nghĩa ASM join group thông thường |
| `239.0.0.0/8` | Administratively Scoped IPv4 Multicast | Phạm vi nội bộ do ranh giới mạng/quản trị kiểm soát |
| `239.255.0.0/16` | IPv4 Local Scope theo RFC 2365 | Miền cục bộ được định nghĩa bởi cấu hình mạng, **không phải mặc định chỉ một host** |
| `239.192.0.0/14` | IPv4 Organization-Local Scope theo RFC 2365 | Dải cho tổ chức phân bổ nhóm theo chính sách nội bộ |

Các mạng có thể có cấu hình không thực hiện multicast routing. Vì thế bảng trên mô tả **phân loại/semantics**, không phải lời hứa gói sẽ được nhận ở mọi nơi. Xem sổ đăng ký IANA hiện hành trước khi chọn group lâu dài cho sản phẩm.

### 2.2. Điểm đặc biệt của `224.0.0.0/24`

Dải `224.0.0.0` đến `224.0.0.255` là Local Network Control Block, bao gồm ví dụ:

- `224.0.0.1` — all systems trên subnet (nhóm giao thức), **không nên dùng làm nhóm dữ liệu ứng dụng tùy ý**.
- `224.0.0.2` — all routers trên subnet (nhóm giao thức).
- Những địa chỉ khác dùng cho routing protocol/điều khiển mạng.

**Router multicast không được forward datagram có đích thuộc `224.0.0.0/24` ra khỏi local link, dù IPv4 TTL = 5, 64 hay 255.** Đây là quy tắc của dải địa chỉ, không phải hiệu quả ngẫu nhiên của TTL.

Vì vậy, thí nghiệm “tăng TTL từ 1 lên 32 mà datagram gửi `224.0.0.1` vẫn không qua router” **không chứng minh** thiết lập TTL trong Java bị bỏ qua. Đó là chọn nhóm có **scope bị giới hạn cứng ở link**.

### 2.3. Administratively scoped IPv4: `239/8`

RFC 2365 dành `239.0.0.0/8` cho multicast có ranh giới theo **chính sách quản trị**. Router quản trị một vùng có thể được cấu hình để không chuyển tiếp nhóm này qua những boundary cụ thể.

Ví dụ:

- `239.255.0.0/16` là **Local Scope** theo RFC 2365; “local” là vùng topology được quản trị, không nhất thiết chỉ host hoặc một LAN.
- `239.192.0.0/14` là **Organization-Local Scope**; tổ chức có thể quy hoạch các subrange cho multicast nội bộ.
- `239.192.10.42` là một **địa chỉ ví dụ trong dải organization-local**, chỉ nên dùng sau khi kiểm tra phân bổ nhóm của mạng thực.

**Chỉ chọn `239.x.x.x` không tự dựng router boundary.** Phạm vi hữu hiệu còn cần cấu hình của router/switch, multicast routing và firewall. Một TTL lớn không vượt qua boundary đã chặn, nhưng nếu boundary cấu hình sai thì việc “địa chỉ 239 nên chắc chắn nội bộ” là giả định an ninh nguy hiểm. Đừng dùng dải địa chỉ thay thế authentication, access control hoặc mã hóa.

### 2.4. `232/8` không đơn giản là một nhóm ASM khác

IPv4 `232.0.0.0/8` là Source-Specific Multicast (SSM). Thay vì tham gia chỉ bằng nhóm G (Any-Source Multicast), receiver SSM quan tâm đến cặp **(source S, group G)** và routing phù hợp. Trong Java, `DatagramChannel.join(group, networkInterface, source)` là API có thể biểu diễn source-specific membership khi hệ điều hành hỗ trợ.

Mục tiêu bài này không phải tự triển khai SSM, nhưng cần nhớ: **đừng chọn `232.x.x.x` làm địa chỉ thử nghiệm ASM mặc định** rồi suy ra TTL có vấn đề khi không nhận được datagram.

## 3. IPv6: scope nằm trong chính địa chỉ multicast

IPv6 multicast dùng prefix **`ff00::/8`**, nghĩa là byte đầu tiên bằng hexadecimal `FF`. Khác với IPv4, **trường scope được mã hóa trực tiếp trong địa chỉ đích IPv6 multicast**.

### 3.1. Phân tích hai byte đầu

Theo kiến trúc IPv6, phần đầu của một địa chỉ multicast có dạng:

~~~text
|   8 bit   |    4 bit     |  4 bit   | phần còn lại ... |
|  11111111 |    flags     |  scope   |      group ID   |
|     FF    |    0..F      |   0..F   |                  |

Ví dụ ở dạng ngắn:
   ff12::1234  -> FF | flags=1 | scope=2 | group ID...
   ff15::1234  -> FF | flags=1 | scope=5 | group ID...
   ff1e::1234  -> FF | flags=1 | scope=E | group ID...
~~~

Nibble cuối của **byte thứ hai** là scope code. Với một `Inet6Address` là multicast, Java có thể đọc byte bằng `address.getAddress()[1] & 0x0F`.

**Giải thích flags:** với ví dụ `ff12::1234`, nibble flags là `1`, cho biết nhóm dạng **transient/non-permanently assigned** theo cách diễn giải cơ bản. Không nên cho rằng chỉ cần biết scope là đã đủ để thiết kế ID nhóm mới: IPv6 multicast còn có các dạng cấp phát và flag mở rộng (RFC 3306, RFC 3307, RFC 4291). Với sản phẩm thực tế, tuân thủ quy hoạch group ID của mạng/tổ chức.

### 3.2. Các scope code IPv6 cần nhớ

| Scope (hex) | Tên | Ý nghĩa |
| --- | --- | --- |
| `1` | Interface-Local | Trong một interface (cấp node/interface) |
| `2` | Link-Local | Trên một link; không chuyển tiếp ra link khác |
| `3` | Realm-Local | Realm của công nghệ liên kết; cần định nghĩa tương ứng |
| `4` | Admin-Local | Vùng quản trị nhỏ nhất cần cấu hình |
| `5` | Site-Local | Trong một site được định nghĩa theo mạng |
| `8` | Organization-Local | Trong tổ chức theo quản trị |
| `E` | Global | Phạm vi global về mặt địa chỉ multicast |
| `0`, `F` | Reserved | Không dùng làm scope ứng dụng |
| `6`, `7`, `9`–`D` | Unassigned trong sổ đăng ký hiện hành | Không tự gán nghĩa tùy ý |

Ví dụ:

- `ff02::1` là một nhóm **all-nodes link-local** được định nghĩa bởi giao thức. Không dùng để phát nội dung ứng dụng tự chọn.
- `ff12::1234`: nhóm ví dụ **transient, link-local**; muốn gửi đúng link cần chọn interface thích hợp.
- `ff15::1234`: nhóm ví dụ **transient, site-local**; scope rộng hơn link nếu network topology hỗ trợ.
- `ff18::1234`: nhóm ví dụ **transient, organization-local**.
- `ff1e::1234`: nhóm ví dụ **transient, global-scope**; điều đó **không** có nghĩa Internet tự cung cấp multicast routing toàn cầu.

Ví dụ là để phân tích **cấu trúc địa chỉ**, không phải địa chỉ nhóm bảo đảm luôn được phép phân bổ và dùng cho mọi ứng dụng. Group ID và phạm vi phải được mạng/tổ chức cấp phát hợp lệ.

### 3.3. IPv6 scope không phải IPv6 Hop Limit

Hai trường độc lập:

~~~text
Datagram IPv6
    destination = ff12::1234   (scope=2: link-local)
    Hop Limit   = 200          (ngân sách hop lớn)
    => vẫn bị giới hạn trong local link bởi scope.

Datagram IPv6
    destination = ff1e::1234   (scope=E: global)
    Hop Limit   = 1            (ngân sách hop nhỏ)
    => bị giới hạn bởi hop count; không thể đến mạng xa qua router.
~~~

Với IPv6 link-local multicast, việc chỉ sửa Hop Limit không thay đổi phạm vi địa chỉ. Phải chọn đúng **group scope** trước, sau đó chọn **hop limit** phù hợp. Ngược lại, chỉ đổi địa chỉ nhóm sang global không giúp gửi tới remote site nếu hop limit quá thấp hoặc network không có multicast route.

### 3.4. Một NIC cụ thể đặc biệt quan trọng với link-local IPv6

Một máy có thể có nhiều link khác nhau: Ethernet, Wi-Fi, VLAN, VPN, container veth. Scope **link-local** chỉ có ý nghĩa khi biết gửi trên **link/interface nào**.

Trong ứng dụng Java:

- Xác định `NetworkInterface` mong muốn, kiểm tra `isUp()`, `supportsMulticast()`, các địa chỉ IPv6 của interface nếu cần.
- Khi gửi bằng `MulticastSocket`, dùng `setNetworkInterface(netIf)`; với `DatagramChannel`, dùng `setOption(StandardSocketOptions.IP_MULTICAST_IF, netIf)`.
- Khi nhận, join multicast group trên interface phù hợp; ví dụ `joinGroup(new InetSocketAddress(group, 0), netIf)` với `MulticastSocket`.
- Không suy rằng interface “mặc định” luôn là interface đúng khi máy có VPN hoặc nhiều NIC.

Trong địa chỉ IPv6, cú pháp zone identifier như `%eth0` có thể được dùng với những địa chỉ link-local cụ thể trên hệ điều hành thích hợp. Tuy nhiên, **không thay thế cách chọn `NetworkInterface` trong API multicast bằng việc tự ghép chuỗi zone tùy tiện**; việc giải quyết zone/NIC phụ thuộc môi trường.

## 4. IPv4 TTL là gì?

TTL là viết tắt **Time To Live** nhưng trong định tuyến IP hiện đại nó được dùng như **hop counter/budget**, không phải thời gian tính bằng giây hay mili giây.

- Trường TTL của IPv4 có độ dài **8 bit**, giá trị trong khoảng **0–255**.
- Ở một bước định tuyến, router giảm TTL; nếu TTL không còn cho phép chuyển tiếp, gói bị loại bỏ.
- Một gói gửi với **TTL = 1** thường có thể đi trên **link cục bộ**, nhưng không được multicast router forward sang một link khác.
- **TTL = 0**: theo hợp đồng Java multicast socket, datagram **không được truyền lên mạng**, nhưng có thể được giao cục bộ tùy hệ điều hành và cấu hình loopback.
- **TTL = 2**, **TTL = 8**, **TTL = 32**: tăng ngân sách số bước chuyển tiếp, **không** bảo đảm sẽ đi qua đúng số router hay đến một khoảng cách vật lý xác định.

Ví dụ tuyến multicast được thiết lập và không có ranh giới khác:

~~~text
Sender -- LAN A -- Router R1 -- LAN B -- Router R2 -- LAN C

TTL = 1:
  Datagram có thể truyền trên LAN A; R1 không forward tới LAN B.

TTL = 2:
  Có thể được R1 chuyển tiếp sang LAN B; không tiếp tục vượt R2.

TTL = 3:
  Có thể được R1 rồi R2 chuyển tiếp tới LAN C.

Đây là mô hình lý tưởng; thực tế còn router policy, IGMP, firewall,
multicast route, MTU, source policy và giới hạn group scope.
~~~

Đừng đổi “TTL 3” thành “gửi được đến ba máy”. Một datagram có thể được nhân bản qua nhiều nhánh multicast; TTL là giới hạn **hop IP** trên mỗi nhánh chứ không phải số máy nhận.

### TTL và subnet

- **Subnet** và **link** không hoàn toàn đồng nghĩa. Có thể một LAN chứa nhiều IP subnet, hoặc một subnet đi qua topology đặc biệt. TTL dùng hop forwarding, không phải đếm địa chỉ/subnet theo tên gọi.
- Không phải mọi router tự forward multicast chỉ vì đã bật IP forwarding thông thường. Multicast cần cơ chế routing và membership phù hợp.
- Nếu nhóm `224.0.0.0/24`, **TTL = 64 vẫn không cho phép** router forward khỏi link: scope địa chỉ chặn trước.

## 5. IPv6 Hop Limit tương đương TTL về ý tưởng nhưng không về tên header

IPv6 dùng trường **Hop Limit** (8 bit) thay cho trường IPv4 TTL. IPv6 không gọi trường đó là TTL trong IP header, nhưng ở cấp **Java socket option**, tên chuẩn chung vẫn là **`IP_MULTICAST_TTL`**.

| Câu hỏi | IPv4 | IPv6 |
| --- | --- | --- |
| Trường trong IP header | Time To Live (TTL) | Hop Limit |
| Số bit | 8 | 8 |
| Giá trị socket option Java | Integer `0..255` | Integer `0..255` |
| Tác dụng | Giới hạn việc forward theo hop | Giới hạn việc forward theo hop |
| Địa chỉ nhóm | `224.0.0.0/4` | `ff00::/8` |
| Scope địa chỉ | Khối địa chỉ + boundary quản trị | Nibble scope trong địa chỉ |
| Có thể vượt scope bằng TTL lớn? | Không | Không |

Theo JDK, `StandardSocketOptions.IP_MULTICAST_TTL` trên **IPv4 socket** điều khiển IPv4 multicast TTL; trên **IPv6 socket** điều khiển IPv6 multicast Hop Limit. Với socket IPv6 gửi đến địa chỉ IPv4, tác động phụ tới IPv4 TTL có thể **phụ thuộc hệ điều hành/implementation**. Để tránh bất ngờ, dùng socket/channel và family rõ ràng cho từng trường hợp.

Trong Java, đừng tìm một hằng số tên `IP_MULTICAST_HOP_LIMIT` thuộc `StandardSocketOptions`: API standard sử dụng cùng tên **`IP_MULTICAST_TTL`** cho cả hai family.

## 6. TTL không phải là tất cả: điều kiện để packet được nhận

Một receiver có thể **không nhận được** datagram dù TTL/hop limit > 1 vì nhiều lý do:

1. Sender dùng địa chỉ multicast không phù hợp hoặc nhóm đã được protocol khác sử dụng.
2. Receiver chưa tham gia nhóm, join sai interface hoặc join sai source-filter với SSM.
3. Sender chọn sai outgoing NIC (Wi-Fi thay vì LAN, VPN thay vì interface nội bộ).
4. Sender/receiver không thống nhất UDP port hoặc socket bind sai.
5. Không có **multicast routing** giữa các link, hoặc router policy chặn nhóm/scope.
6. Firewall máy chủ, firewall router, Wi-Fi AP multicast filtering, IGMP/MLD snooping hoặc VLAN boundary làm mất datagram.
7. IPv6 group là link-local nhưng đích nhận nằm ở link khác.
8. Quá TTL/Hop Limit trước khi đến đích, hoặc packet bị giới hạn bởi administratively scoped boundary.
9. Multicast loopback bị tắt; gói gửi cùng máy không được loop lại như mong đợi.
10. Buffer, kích thước datagram, tốc độ gửi hoặc mất UDP datagram gây drop.

**IGMP** (IPv4) và **MLD** (IPv6) giúp các thiết bị quản lý membership multicast; chúng không phải API để ứng dụng “tăng TTL”. Một socket join group đúng chưa chắc tự sinh ra multicast routing trên router; hệ thống mạng phải hỗ trợ đường truyền tương ứng.

## 7. Java API: thiết lập TTL/Hop Limit như thế nào?

### 7.1. `MulticastSocket.setTimeToLive(int)`

Với `java.net.MulticastSocket`:

~~~java
try (MulticastSocket socket = new MulticastSocket()) {
    socket.setTimeToLive(1); // TTL/Hop Limit cho các multicast datagram gửi ra
    int current = socket.getTimeToLive();
    System.out.println(current);
}
~~~

Đây là **mảnh code đặt trong method có `throws IOException`** và cần `import java.net.MulticastSocket;`. `MulticastSocket` kế thừa `DatagramSocket` nên đóng tài nguyên bằng `try-with-resources`.

Hợp đồng:

- `setTimeToLive(int ttl)` chấp nhận **`0 <= ttl <= 255`**; ra khỏi khoảng này ném `IllegalArgumentException`.
- Phương thức có thể ném `IOException` nếu OS không thiết lập được option.
- `getTimeToLive()` đọc giá trị đang được thiết lập trên socket.
- Mức mặc định thường **1**, nhưng đừng dựa vào mặc định cho giao thức quan trọng: hãy cấu hình cụ thể khi cần và có thể đọc lại.
- Cài đặt TTL cho **datagram sẽ gửi**, không làm thay đổi địa chỉ group, không join group và không đặt số lượng người nhận.

Phương thức cũ `setTTL(byte)` và `getTTL()` đã deprecated; không nên dùng trong Java 17+. Overload `send(DatagramPacket, byte ttl)` cũng deprecated; nên cấu hình option trên socket rồi dùng `send(packet)` thông thường.

### 7.2. `StandardSocketOptions.IP_MULTICAST_TTL`

API hiện đại cung cấp một socket option chuẩn:

~~~java
socket.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 8);
int configured =
        socket.getOption(StandardSocketOptions.IP_MULTICAST_TTL);
~~~

Đây là **mảnh minh họa**: `socket` có thể là `DatagramSocket`/`MulticastSocket` hỗ trợ option; cần `import java.net.StandardSocketOptions;` và xử lý `IOException`. JDK ghi rõ `MulticastSocket.setTimeToLive(8)` về mặt API tương đương thiết lập option này.

Với NIO:

~~~java
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 3);
    System.out.println(
            channel.getOption(StandardSocketOptions.IP_MULTICAST_TTL));
}
~~~

Mảnh này chạy trong method khai báo/catch `IOException`; cần `java.nio.channels.DatagramChannel` và imports `java.net.StandardProtocolFamily`, `java.net.StandardSocketOptions`. Khi tạo `DatagramChannel.open(StandardProtocolFamily.INET)`, ta yêu cầu IPv4. Tương tự, `StandardProtocolFamily.INET6` yêu cầu IPv6, **nếu nền tảng hỗ trợ**.

| Tác vụ | API Java | Cần chú ý |
| --- | --- | --- |
| Thiết lập multicast TTL | `MulticastSocket.setTimeToLive(ttl)` | Dải 0..255, checked `IOException` |
| Đọc TTL hiện tại | `MulticastSocket.getTimeToLive()` | Không phải đo gói đã đi bao xa |
| Thiết lập qua socket option | `socket.setOption(IP_MULTICAST_TTL, ttl)` | Phân biệt IPv4/IPv6 family |
| NIO DatagramChannel | `channel.setOption(IP_MULTICAST_TTL, ttl)` | IPv6 family => hop limit |
| Chọn NIC multicast | `setNetworkInterface(netIf)` hoặc `IP_MULTICAST_IF` | Tránh route qua NIC ngoài ý muốn |
| Điều khiển loopback | `IP_MULTICAST_LOOP` | Tác động cụ thể phụ thuộc platform |
| Join IPv4/IPv6 group | `joinGroup(groupSocketAddress, netIf)` hoặc `DatagramChannel.join(group, netIf)` | Receiver cần interface phù hợp |

### 7.3. TTL là state của socket gửi

Khi dùng một `MulticastSocket` để gửi nhiều datagrams:

~~~java
socket.setTimeToLive(1);
socket.send(localPacket); // phát theo cấu hình TTL=1

socket.setTimeToLive(8);
socket.send(widerPacket); // phát theo cấu hình TTL=8
~~~

Đây là **mảnh minh họa**, `socket`, `localPacket`, `widerPacket` đã được tạo và cần xử lý `IOException`. Việc đổi TTL ở socket có thể ảnh hưởng các datagram tiếp theo gửi qua cùng đối tượng, nên không nên nhiều thread tùy tiện đổi TTL của cùng một socket song song mà không đồng bộ. Tốt hơn dùng một cấu hình TTL nhất quán theo loại traffic hoặc các socket gửi riêng nếu cần policy khác nhau.

Cả hai packet vẫn phải có địa chỉ đích nhóm và outbound interface đúng. **`setTimeToLive()` không thay đổi `DatagramPacket` đang mang destination/port nào.**

## 8. Ví dụ Java 17+ chạy độc lập: nhận diện IPv4/IPv6 và cấu hình TTL

Chương trình dưới đây không gửi multicast thật, không join group và không phụ thuộc router. Nó thực hiện **parse các địa chỉ số**, đọc scope nibble IPv6, cấu hình TTL trên `MulticastSocket`, kiểm tra giá trị ngoài range và cấu hình option trên `DatagramChannel` IPv4.

Tệp: **`MulticastScopeDemo.java`**

~~~java
import java.net.*;
import java.nio.channels.DatagramChannel;

public class MulticastScopeDemo {
    static int ipv6Scope(InetAddress address) {
        if (!(address instanceof Inet6Address) || !address.isMulticastAddress()) {
            throw new IllegalArgumentException("IPv6 multicast address required");
        }
        return address.getAddress()[1] & 0x0F;
    }

    public static void main(String[] args) throws Exception {
        InetAddress ipv4Control = InetAddress.getByName("224.0.0.1");
        InetAddress ipv4Admin = InetAddress.getByName("239.192.0.42");
        InetAddress ipv6Link = InetAddress.getByName("ff12::1234");
        InetAddress ipv6Site = InetAddress.getByName("ff15::1234");
        System.out.println("IPv4 control multicast: " + ipv4Control.isMulticastAddress());
        System.out.println("IPv4 admin multicast: " + ipv4Admin.isMulticastAddress());
        System.out.println("IPv6 link scope: " + ipv6Scope(ipv6Link));
        System.out.println("IPv6 site scope: " + ipv6Scope(ipv6Site));

        try (MulticastSocket socket = new MulticastSocket((SocketAddress) null)) {
            socket.setTimeToLive(1);
            System.out.println("MulticastSocket TTL: " + socket.getTimeToLive());
            socket.setTimeToLive(8);
            System.out.println("MulticastSocket TTL changed: " + socket.getTimeToLive());
            try {
                socket.setTimeToLive(256);
            } catch (IllegalArgumentException expected) {
                System.out.println("TTL 256 rejected: true");
            }
        }
        try (DatagramChannel ch = DatagramChannel.open(StandardProtocolFamily.INET)) {
            ch.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 3);
            System.out.println("DatagramChannel TTL: " +
                    ch.getOption(StandardSocketOptions.IP_MULTICAST_TTL));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MulticastScopeDemo.java
java MulticastScopeDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK 24** (API và cú pháp sử dụng đều có trên Java 17):

~~~text
IPv4 control multicast: true
IPv4 admin multicast: true
IPv6 link scope: 2
IPv6 site scope: 5
MulticastSocket TTL: 1
MulticastSocket TTL changed: 8
TTL 256 rejected: true
DatagramChannel TTL: 3
~~~

**Điểm cần phân tích:**

1. `InetAddress.isMulticastAddress()` trả `true` cho hai địa chỉ IPv4 nhóm. Nhưng điều đó **không** nói được địa chỉ đó được router forward hay được ứng dụng phép dùng.
2. IPv6 `ff12::1234` có scope nibble 2 (link-local), `ff15::1234` có scope nibble 5 (site-local). Đây là **thuộc tính địa chỉ**, không lấy từ TTL.
3. `MulticastSocket` được tạo ở trạng thái **unbound** để cấu hình option, không cần phát datagram hay có receiver. `setTimeToLive(1)` và `setTimeToLive(8)` đọc lại đúng số đã đặt.
4. `setTimeToLive(256)` vi phạm dải 0..255 nên ném `IllegalArgumentException`; việc bắt lỗi chỉ dùng để chứng minh validation.
5. `DatagramChannel.open(INET)` tạo channel IPv4. `IP_MULTICAST_TTL` đặt 3 và đọc lại 3.
6. Mã cần OS cho phép tạo datagram socket/channel IPv4; trong sandbox nghiêm ngặt không có networking API thì có thể gặp lỗi hệ thống. Chạy ví dụ thành công **không chứng minh** multicast routing giữa hai mạng đã hoạt động, vì không gói tin nào được gửi.

**Lưu ý về ví dụ địa chỉ:** hai group IPv4 được dùng chỉ để phân loại; `224.0.0.1` là group điều khiển và **không** được chọn làm nhóm dữ liệu tùy ý. `239.192.0.42` chỉ là một địa chỉ số nằm trong dải organization-local; đừng triển khai sản phẩm mà không phối hợp quản trị địa chỉ nhóm.

## 9. Áp dụng thực tế: gửi multicast UDP có TTL hữu hạn

Giả sử ứng dụng có nhóm IPv4 được cấp phép nội bộ `239.192.10.42`, port 5001, và muốn gói chỉ nằm trong LAN. Ý tưởng:

1. Chọn đúng NIC đang dùng cho multicast.
2. Tạo `MulticastSocket` và đặt outgoing interface.
3. Đặt `setTimeToLive(1)`.
4. Tạo `DatagramPacket` với destination group/port.
5. Gửi và đóng socket khi xong.

### 9.1. Mảnh code gửi (đặt trong method)

~~~java
InetAddress group = InetAddress.getByName("239.192.10.42");
NetworkInterface nic = NetworkInterface.getByName("eth0");
if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
    throw new IllegalStateException("Multicast interface unavailable");
}
byte[] payload = "hello-group".getBytes(StandardCharsets.UTF_8);

try (MulticastSocket sender = new MulticastSocket()) {
    sender.setNetworkInterface(nic);
    sender.setTimeToLive(1);

    DatagramPacket packet = new DatagramPacket(
            payload, payload.length, group, 5001);
    sender.send(packet);
}
~~~

**Đây là đoạn mã minh họa, không phải chương trình chạy độc lập.** Nó cần các import `java.net.*`, `java.nio.charset.StandardCharsets` và một phương thức khai báo/catch `IOException`. Tên interface `eth0` chỉ là ví dụ trên một số máy Linux; Windows/macOS hoặc container có thể dùng tên khác. **Không tự gửi packet vào hệ thống không thuộc quyền kiểm soát của bạn.** Group phải được cấp phát hợp lệ cho mạng. Đoạn gửi không tạo receiver nên **không có stdout** và không bảo đảm host khác sẽ nhận.

### 9.2. Receiver phải join group — TTL không thay thao tác join

Một receiver truyền thống có thể dùng:

~~~java
InetAddress group = InetAddress.getByName("239.192.10.42");
NetworkInterface nic = NetworkInterface.getByName("eth0");

try (MulticastSocket receiver = new MulticastSocket(5001)) {
    receiver.setSoTimeout(3_000);
    receiver.joinGroup(new InetSocketAddress(group, 0), nic);
    try {
        byte[] bytes = new byte[2048];
        DatagramPacket packet = new DatagramPacket(bytes, bytes.length);
        receiver.receive(packet);
        // packet.getLength() là độ dài payload thực nhận.
    } finally {
        receiver.leaveGroup(new InetSocketAddress(group, 0), nic);
    }
}
~~~

**Đây cũng là mảnh mã minh họa**, cần chuẩn bị group/NIC, policy mạng và xử lý `IOException`/`SocketTimeoutException`; sử dụng trên interface thực hỗ trợ multicast. `MulticastSocket.joinGroup(InetAddress)` đời cũ đã deprecated vì thiếu khả năng chỉ rõ interface; ưu tiên overload nhận `SocketAddress` và `NetworkInterface`.

Trên mạng thật, nhiều hệ điều hành/switch yêu cầu receiver join đúng group/interface và bind đúng UDP port. Datagram vẫn có thể bị mất: UDP multicast **không** tạo lời hứa delivery hoặc ACK.

### 9.3. Phiên bản NIO dùng `DatagramChannel`

~~~java
NetworkInterface nic = NetworkInterface.getByName("eth0");

try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
    channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);

    ByteBuffer data = StandardCharsets.UTF_8.encode("hello-group");
    channel.send(data, new InetSocketAddress("239.192.10.42", 5001));
}
~~~

Đoạn này **không độc lập**, vì cần các imports `java.net.*`, `java.nio.channels.DatagramChannel`, `java.nio.ByteBuffer`, `java.nio.charset.StandardCharsets`, `IOException` handling và một NIC có multicast. Nó minh họa cách Java NIO tách outgoing interface và TTL qua các options. Không gọi `join()` chỉ để gửi: **sender thông thường không bắt buộc tham gia group**.

Nếu làm receiver bằng `DatagramChannel`, dùng `MembershipKey key = channel.join(group, nic)` khi channel/OS hỗ trợ; `key.drop()` hoặc đóng channel để giải phóng membership. Với SSM, overload `join(group, nic, source)` có thể cần hỗ trợ thêm từ OS.

## 10. Khi chuyển sang IPv6, phải đổi cả địa chỉ và family

Không thể chỉ thay IPv4 group `239.192.10.42` bằng một chuỗi IPv6 bất kỳ rồi cho rằng toàn bộ hạ tầng tự tương thích.

### 10.1. Các quyết định bắt buộc

- Chọn multicast group thuộc `ff00::/8` và **scope phù hợp** với mục tiêu: link, site, organization hoặc global. Không dùng nhóm điều khiển/được cấp phát sẵn cho payload ứng dụng.
- Chọn outgoing NIC có địa chỉ/stack IPv6 và hỗ trợ multicast trên link mong muốn.
- Mở socket/channel IPv6 khi cần tách family rõ ràng; với NIO: `DatagramChannel.open(StandardProtocolFamily.INET6)`.
- Đặt `StandardSocketOptions.IP_MULTICAST_IF`, `IP_MULTICAST_TTL` (= **Hop Limit** trên IPv6) và cấu hình nhận group theo interface.
- Kiểm tra firewall, MLD, multicast routing IPv6, VLAN/VRF và boundary scope. Không giả định IPv6 multicast routing hoạt động giữa các site.

### 10.2. Mảnh minh họa IPv6

~~~java
InetAddress group = InetAddress.getByName("ff12::1234"); // link-local
NetworkInterface nic = NetworkInterface.getByName("eth0");

try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET6)) {
    channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
    channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    // DatagramChannel: giá trị 1 ở đây là IPv6 Hop Limit.
    // channel.send(data, new InetSocketAddress(group, 5001));
}
~~~

Đây là **mảnh mã giải thích lựa chọn option**, không đảm bảo chạy được trên mọi hệ điều hành. `nic` phải là interface tồn tại và có IPv6 multicast; `data` trong dòng comment phải được chuẩn bị. `ff12::1234` chỉ là địa chỉ ví dụ để đọc scope. Cần theo chính sách cấp phát group IPv6 trước khi gửi ứng dụng thật.

Nếu muốn gói đi nhiều hop, **đổi Hop Limit và có thể phải đổi scope địa chỉ**. Ví dụ, tăng Hop Limit của nhóm `ff12::1234` từ 1 lên 32 **vẫn không cho phép** router đưa nó ra khỏi local link.

### 10.3. Không nhầm IPv6 link-local unicast với multicast scope

- `fe80::/10` là **IPv6 link-local unicast** (địa chỉ của một interface).
- `ff02::/16` mô tả nhóm multicast có **link-local scope** trong cấu trúc `ff0s` với flags phù hợp.
- Một NIC có địa chỉ unicast `fe80::...` không có nghĩa mọi nhóm `ff00::/8` đều là link-local.
- “`%eth0`” / scope ID thường gắn với địa chỉ có ý nghĩa theo interface; định tuyến/đăng ký group vẫn cần chọn đúng interface.

Đây là hai **loại địa chỉ khác nhau**, dù cả hai có thể gắn với phạm vi link.

## 11. Chọn phạm vi cho một yêu cầu nghiệp vụ

| Yêu cầu | Định hướng địa chỉ/scope | TTL/Hop Limit | Điều kiện còn thiếu |
| --- | --- | --- | --- |
| Phát hiện thiết bị trong một LAN IPv4 do tổ chức quản lý | Group IPv4 phù hợp trong vùng nội bộ đã cấp; không chiếm `224.0.0/24` | Thường bắt đầu từ 1 | NIC đúng, join group, UDP port, firewall, WLAN |
| Dịch vụ nội bộ qua nhiều subnet IPv4 | Dải `239/8` theo phạm vi đã quy hoạch | Chọn đủ số hop, không đặt 255 vô cớ | Multicast routing và boundary quản trị |
| Discovery IPv6 chỉ trong link | Group IPv6 có scope `2`, ví dụ dạng `ff12::...` đã quy hoạch | Thường 1 | Đúng interface/link, MLD và support của OS |
| Ứng dụng IPv6 nội bộ cả site | Group IPv6 có scope `5`, với group ID hợp lệ | Lớn hơn 1 nếu cần đi qua router | Router hỗ trợ chuyển tiếp trong site |
| Ứng dụng IPv6 toàn tổ chức | Scope `8`, group ID theo quy hoạch | Theo topology | Multicast routing/chính sách organization |
| Một ứng dụng muốn “đến tất cả Internet” | Không tự giả định multicast global hoạt động | Không có TTL nào bảo đảm | Cần mô hình phân phối đã được network hỗ trợ hoặc dùng unicast/pub-sub thay thế |

**Quy tắc thiết kế:** chọn phạm vi **hẹp nhất** đáp ứng yêu cầu, sau đó chọn TTL/Hop Limit tối thiểu phù hợp topology đã kiểm chứng. Việc dùng số 255 trên mọi socket không phải mẹo để “chắc chắn nhận”, mà có thể mở rộng lưu lượng không cần thiết nếu network cho phép.

## 12. Cách thử nghiệm phân biệt lỗi scope và lỗi hop

Hãy thử có kiểm soát trên mạng được phép sử dụng:

1. **Kiểm tra group:** IPv4 thuộc 224/4 nhưng không rơi vào dải reserved/control trái mục đích; IPv6 thuộc ff00::/8 với scope đúng. `isMulticastAddress()` chỉ xác nhận loại địa chỉ, không kiểm tra quyền dùng group.
2. **Kiểm tra NIC:** log tên/index của `NetworkInterface`, trạng thái up, multicast support, địa chỉ local và IP family.
3. **Thử một LAN:** sender và receiver cùng link, cùng group/port, join đúng NIC, cấu hình TTL/Hop Limit = 1, bật loopback nếu kiểm thử cùng host cần thiết.
4. **Thử qua router:** sử dụng một group **được phép forward** và multicast routing đã cấu hình; thử TTL/Hop Limit = 1 rồi 2/3; quan sát thay đổi tại từng link.
5. **Thử boundary:** với IPv4 admin-scoped hoặc IPv6 site/organization scope, xác minh lưu lượng **không vượt** boundary bằng packet capture ở điểm phù hợp.
6. **Tách vấn đề protocol:** khi packets đến nhưng ứng dụng không phản hồi, debug framing, port, buffer, charset và lỗi business logic thay vì tăng TTL.
7. **Quan sát bằng packet capture:** công cụ như Wireshark/tcpdump có thể cho biết địa chỉ đích, TTL/Hop Limit và interface; có quyền truy cập mạng mới thực hiện. Không hiển thị dữ liệu nhạy cảm trong log.
8. **Đọc số từ API:** `getTimeToLive()` cho biết giá trị socket cấu hình, **không** cho biết số hop gói đã đi thực tế.

Ví dụ bảng dự kiến (không phải kết quả benchmark đo trên mạng thật):

| Gói | Group | TTL / Hop Limit | Kỳ vọng có điều kiện |
| --- | --- | --- | --- |
| A | `224.0.0.1` | TTL 64 | Không được router multicast forward ra khỏi local link |
| B | `239.192.10.42` | TTL 1 | Có thể nhận trong link nguồn nếu người nhận join và network cho phép |
| C | `239.192.10.42` | TTL 3 | Có thể đi xa hơn nếu multicast routing và policy cho phép |
| D | `ff12::1234` | Hop Limit 64 | Vẫn link-local do IPv6 group scope=2 |
| E | `ff15::1234` | Hop Limit 1 | Không đi qua router dù địa chỉ site-local |
| F | `ff15::1234` | Hop Limit 4 | Có thể tới những link khác **trong site** nếu hạ tầng multicast phù hợp |

## 13. Những nhầm lẫn phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “TTL nghĩa là số giây gói còn sống” | TTL trong thực tế là **hop budget** | Đọc TTL/Hop Limit như số chặng IP |
| “TTL = 1 là chỉ cùng host” | TTL=1 có thể phát trên local link | Phân biệt local host và một-hop/link |
| “TTL = 10 gửi tới 10 client” | Một datagram có thể được nhân nhiều nhánh | TTL không liên quan số subscriber |
| “TTL = 255 chắc chắn xuyên router” | Router cần multicast routing, membership và policy | Xác minh route và boundary |
| Gửi dữ liệu ứng dụng vào `224.0.0.1` | Đây là group điều khiển all-systems | Chọn group cấp phát hợp lệ; không chiếm block control |
| Tăng TTL của `224.0.0/24` rồi chờ qua router | Block này không được forward bất kể TTL | Sửa group theo scope/mục đích |
| Xem tất cả `239/8` tự được mạng bảo vệ | Administratively scoped cần boundary được triển khai đúng | Cấu hình router/firewall và kiểm thử |
| Chọn `232/8` như nhóm ASM thông thường | Đây là dải SSM | Dùng source-specific join nếu đúng yêu cầu |
| “IPv6 ff12::... gửi toàn site nếu Hop Limit cao” | Scope=2 link-local cố định trong địa chỉ | Chọn group scope=5 nếu site-local cần thiết |
| “Java có hằng IP_MULTICAST_HOP_LIMIT riêng” | StandardSocketOptions dùng `IP_MULTICAST_TTL` cho cả 2 family | Dùng chung option, xác định socket IPv4/IPv6 |
| Dùng `setTTL(byte)`/`getTTL()` đời cũ | API deprecated và byte dễ nhầm signedness | Dùng `setTimeToLive(int)`/`getTimeToLive()` |
| Chỉ set TTL, receiver không join group | TTL không thay membership | Join group đúng NIC/port |
| Sender có nhiều NIC nhưng không chọn outbound | Gói có thể ra sai interface hoặc không route | Chọn `NetworkInterface` rõ ràng |
| “Join thành công thì packet chắc chắn đến” | UDP multicast không bảo đảm delivery | Thêm đo lường/retry/protocol phù hợp |
| Dùng network test khác family | IPv6 path khác IPv4, dual-stack khác nhau theo OS | Test riêng INET và INET6 |
| Gọi `MulticastSocket.setTimeToLive(256)` | Giá trị ngoài 0..255 | Validate đầu vào và xử lý IllegalArgumentException |
| Dựa vào loopback multicast có cùng hành vi trên mọi OS | `IP_MULTICAST_LOOP` có chi tiết platform-dependent | Test trên OS/NIC mục tiêu và không suy rộng |

## 14. Bài tập và đáp án

### Bài 1: Địa chỉ IPv4 control

Bạn gửi datagram tới `224.0.0.1` với TTL = 32. Router multicast có thể forward nó ra subnet khác không?

**Đáp án:** Không. `224.0.0.0/24` là Local Network Control Block; router multicast không forward các gói tới block này ra khỏi local link, **bất kể TTL**.

### Bài 2: Chọn IPv4 group nội bộ

Tổ chức có router multicast và muốn phát thông báo trong các mạng do mình quản lý. Nhóm nào hợp lý hơn làm **ví dụ để bắt đầu quy hoạch**: `224.0.0.1` hay một địa chỉ được cấp từ `239.192.0.0/14`?

**Đáp án:** Một nhóm **đã được quản trị cấp** từ organization-local `239.192.0.0/14` phù hợp hơn. Không chiếm `224.0.0.1` vì đó là group điều khiển. Vẫn cần boundary router, membership, TTL và security.

### Bài 3: IPv6 scope nibble

Địa chỉ `ff12::abcd` và `ff15::abcd` có scope nào? Nếu đặt Hop Limit 100 cho `ff12::abcd`, có thành site-local không?

**Đáp án:** `ff12` có scope 2 (link-local), `ff15` có scope 5 (site-local). Hop Limit 100 không làm `ff12` thành site-local.

### Bài 4: Cấu hình Java

Cho một `MulticastSocket` gửi IPv4, muốn đặt TTL = 4. Viết cách cấu hình mới và cho biết range hợp lệ.

**Đáp án:**

~~~java
socket.setTimeToLive(4);
// Tương đương về API: socket.setOption(
//     StandardSocketOptions.IP_MULTICAST_TTL, 4);
~~~

Đây là mảnh code trong phương thức có `socket` đã tồn tại; handle `IOException`. Dải hợp lệ **0..255**, ra ngoài ném `IllegalArgumentException`.

### Bài 5: Vì sao không nhận trên cùng LAN?

Sender dùng một group đúng với TTL = 1; receiver vẫn không thấy gói. Có nhất thiết tăng TTL lên 20 không?

**Đáp án:** Không. Kiểm tra receiver đã join group đúng interface/port chưa, outgoing NIC, firewall, multicast filtering, IGMP/MLD, loopback, bind và Wi-Fi AP. TTL=1 thường đã đủ để phát trên cùng link.

### Bài 6: IPv6 option

Một `DatagramChannel` mở với `StandardProtocolFamily.INET6` và được đặt `IP_MULTICAST_TTL = 7`. Giá trị này ứng với tên trường nào trong header IPv6?

**Đáp án:** **Hop Limit** = 7 cho IPv6 multicast datagram, không phải IPv4 TTL. Hành vi dùng chung socket IPv6 để gửi IPv4 phụ thuộc nền tảng, nên nên tách family khi cần chắc chắn.

### Bài 7: Dự báo đường đi

Một multicast packet IPv4 dùng nhóm hợp lệ có thể forward và TTL = 2. Giữa sender và receiver có hai router multicast. Có thể kỳ vọng chắc chắn receiver nhận không?

**Đáp án:** Không. Trong mô hình lý tưởng gói không đủ ngân sách để được forward qua cả hai router tới link thứ ba; ngoài ra route, firewall, membership và chính sách nhóm vẫn quyết định kết quả. Không được xem TTL = 2 là “hai router đều chuyển tiếp và vẫn còn gói đến bất kỳ phía sau router thứ hai”.

### Bài 8: SSM

Ứng dụng dùng nhóm IPv4 `232.x.x.x` và `DatagramChannel.join(group, nic)` theo kiểu any-source nhưng không nhận dữ liệu như mong đợi. Nên xem lại điều gì?

**Đáp án:** `232/8` là dải **SSM**, yêu cầu mô hình (source, group). Cần xác định source và khả năng `join(group, nic, source)`/mạng hỗ trợ SSM, chứ không kết luận do TTL.

## 15. Checklist đưa multicast vào hệ thống

- [ ] Tôi biết đang dùng **IPv4** hay **IPv6** và đã kiểm tra socket protocol family.
- [ ] Địa chỉ nhóm multicast được phân bổ hợp lệ, không chiếm dải control/reserved.
- [ ] Với IPv4, tôi phân biệt `224.0.0/24` link control, `232/8` SSM và `239/8` admin scoped.
- [ ] Với IPv6, tôi đọc được scope nibble của group; chọn scope hẹp nhất đúng nhu cầu.
- [ ] TTL/Hop Limit là số hop, không phải đơn vị thời gian, số người nhận hoặc công tắc mở router.
- [ ] Tôi đã đặt `0..255` qua `setTimeToLive(int)` hoặc `IP_MULTICAST_TTL` trên socket gửi.
- [ ] Tôi cấu hình outgoing `NetworkInterface` khi cần, không gửi nhầm NIC/VPN.
- [ ] Receiver tham gia group đúng interface và bind UDP port phù hợp; SSM nếu cần có source riêng.
- [ ] Firewall, IGMP/MLD, multicast routing, administrative boundary và switch/Wi-Fi đã được kiểm tra.
- [ ] Tôi dùng timeout/giới hạn buffer; không coi UDP multicast là reliable.
- [ ] Tôi test trên OS, NIC và network topology thật, không chỉ đo `getTimeToLive()`.
- [ ] Tôi không dùng TTL hoặc administratively scoped addresses làm thay thế security policy.

## 16. Nguồn tham khảo chính thức

- [Java SE 21 — MulticastSocket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/MulticastSocket.html): `setTimeToLive()`, `getTimeToLive()`, group membership và API deprecated.
- [Java SE 21 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardSocketOptions.html): `IP_MULTICAST_TTL`, `IP_MULTICAST_IF`, `IP_MULTICAST_LOOP` và khác biệt IPv4/IPv6.
- [Java SE 21 — DatagramChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/DatagramChannel.html): mở protocol family, gửi/nhận, socket options và join multicast.
- [Java SE 21 — InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html): `isMulticastAddress()`, `isMCLinkLocal()`, `isMCSiteLocal()`, `isMCOrgLocal()`.
- [IANA — IPv4 Multicast Address Space](https://www.iana.org/assignments/multicast-addresses): các dải và trạng thái đăng ký hiện hành.
- [IANA — IPv6 Multicast Address Space](https://www.iana.org/assignments/ipv6-multicast-addresses): scope registry và các địa chỉ nhóm IPv6 được quản lý.
- [RFC 5771 — IPv4 Multicast Address Assignments](https://www.rfc-editor.org/rfc/rfc5771): nguyên tắc cấp phát IPv4 multicast, đặc biệt `224.0.0/24` và `232/8`.
- [RFC 2365 — Administratively Scoped IP Multicast](https://www.rfc-editor.org/rfc/rfc2365): `239/8`, local scope và organization-local scope.
- [RFC 4291 — IP Version 6 Addressing Architecture](https://www.rfc-editor.org/rfc/rfc4291): cấu trúc địa chỉ multicast IPv6, flags và scope.
- [RFC 7346 — IPv6 Multicast Address Scopes](https://www.rfc-editor.org/rfc/rfc7346): định nghĩa scope như realm-local, admin-local, site-local và organization-local.

**Tóm tắt cuối:** IPv4 xác định multicast scope qua **khối địa chỉ và ranh giới mạng**, IPv6 mã hóa **scope trong địa chỉ đích**, còn TTL/Hop Limit xác định **ngân sách chuyển tiếp mỗi gói**. Trong Java, chọn group và interface đúng trước, dùng `MulticastSocket.setTimeToLive(int)` hoặc `StandardSocketOptions.IP_MULTICAST_TTL` để đặt số chặng, rồi kiểm thử đường truyền multicast thực tế. **Không có giá trị TTL nào có thể thay cho scope, membership, routing hoặc bảo mật.**
