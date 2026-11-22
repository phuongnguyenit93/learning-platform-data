# Rời nhóm, đóng socket và quản lý nhiều nhóm Multicast trong Java

Trong UDP multicast, một ứng dụng có thể đăng ký nhận datagram từ nhiều địa chỉ nhóm, ví dụ một nhóm cho thông báo trạng thái và một nhóm cho dữ liệu cập nhật. Đăng ký thành công chỉ là **bắt đầu vòng đời membership**: ứng dụng còn phải biết lúc nào nên rời từng nhóm, làm gì khi một nhóm lỗi, cách giữ các nhóm còn lại, và cách đóng socket/channel để giải phóng tài nguyên.

Java 17+ có hai cách quản lý vòng đời chính:

- **`java.net.MulticastSocket`**: gọi `joinGroup(SocketAddress, NetworkInterface)` để gia nhập và `leaveGroup(SocketAddress, NetworkInterface)` để rời **chính nhóm và network interface đã tham gia**. `close()` kết thúc socket.
- **`java.nio.channels.DatagramChannel`** thông qua `MulticastChannel`: `join(group, interface)` trả một **`MembershipKey`**; gọi `key.drop()` để rời membership đó, `key.isValid()` để kiểm tra token còn hiệu lực; `channel.close()` làm các membership của channel không còn hợp lệ.

Bài học tập trung vào **leave / close / nhiều group**, bao gồm trường hợp có nhiều interface, tránh join lặp, tránh leave nhầm, cleanup sau lỗi và kiểm thử hành vi. Ví dụ dùng **IPv4 administratively scoped multicast** như `239.255.42.10` và `239.255.42.11`; đây chỉ là địa chỉ minh họa trong phạm vi phù hợp với môi trường được phép, không phải dịch vụ công khai.

## 1. Một socket có thể ở nhiều nhóm, nhưng membership không đồng nghĩa với socket

Mô hình:

~~~text
                          UDP receiver socket (local port 5000)
                                         |
                          +--------------+--------------+
                          |                             |
                    network-if A                  network-if B
                          |                             |
                  +-------+-------+                     |
                  |               |                     |
              group G1         group G2               group G1
                  |               |                     |
             membership 1    membership 2          membership 3
~~~

Có ba membership riêng: `(socket, G1, ifA)`, `(socket, G2, ifA)`, `(socket, G1, ifB)`. Đó là các đăng ký **nhận** multicast. Một ứng dụng có thể rời `G1` trên `ifA` mà vẫn giữ `G2` trên `ifA` và `G1` trên `ifB` nếu nền tảng hỗ trợ cách sử dụng này.

Phân biệt rõ:

| Thao tác | Ảnh hưởng đến membership | Ảnh hưởng đến socket/channel |
| --- | --- | --- |
| `joinGroup(G, ifA)` / `join(G, ifA)` | Thêm đăng ký nhận `G` trên interface `ifA` | Socket vẫn mở và bind vào local port hiện tại |
| `leaveGroup(G, ifA)` / `key.drop()` | Rời **membership được chỉ định** | Socket/channel vẫn có thể hoạt động với nhóm khác hoặc unicast |
| `close()` | Các đăng ký gắn với socket/channel không còn hoạt động; với NIO các key trở thành invalid | Giải phóng tài nguyên socket/channel và kết thúc khả năng nhận/gửi của đối tượng |
| Mở socket/channel mới | **Không tự phục hồi** các đăng ký của đối tượng cũ | Phải bind và join lại theo cấu hình hiện tại |

Multicast không có phiên kết nối TCP và `joinGroup` không đồng nghĩa `connect`. Thành viên chỉ đăng ký cơ chế lọc nhận packet ở host/OS; join thành công không bảo đảm gói multicast thực tế sẽ tới được (router, firewall, VLAN, IGMP/MLD, OS, interface và policy mạng vẫn quyết định).

**Không nhầm việc rời một nhóm với việc đóng socket**. Một listener chung cho ba nhóm có thể tắt riêng nhóm thứ nhất mà không làm gián đoạn tất cả gói của hai nhóm còn lại. Ngược lại, `close` là hành động đóng tài nguyên tổng thể, không có ý nghĩa “tạm ngừng đúng một nhóm”.

## 2. Nhóm, cổng nhận và interface là ba phần thông tin khác nhau

Multicast receiver thường cần:

1. **Multicast group address:** IPv4 thuộc dải `224.0.0.0/4` (không tùy tiện chọn các địa chỉ dành riêng); hoặc địa chỉ multicast IPv6 theo scope.
2. **Local UDP port:** socket phải **bind** vào cổng mà sender gửi datagram đến. Một socket bind vào cổng `5000` không tự nhận toàn bộ multicast gửi tới cổng `6000` chỉ vì cùng group.
3. **Local network interface:** xác định interface mong muốn dùng để nhận group. Máy có Ethernet, Wi-Fi, VPN hoặc nhiều card mạng có thể cần chọn interface thật chính xác.

Ví dụ:

~~~java
// Đoạn minh họa nằm trong phương thức throws IOException.
// Đã có NetworkInterface netIf được xác định hợp lệ.
InetAddress group = InetAddress.getByName("239.255.42.10");
InetSocketAddress membershipAddress =
        new InetSocketAddress(group, 0);

try (MulticastSocket socket = new MulticastSocket(5000)) {
    socket.joinGroup(membershipAddress, netIf);
    try {
        // Nhận datagram gửi đến group:5000 trên interface được chọn.
    } finally {
        socket.leaveGroup(membershipAddress, netIf);
    }
}
~~~

Đây là **đoạn mô tả vòng đời, không phải chương trình nhận độc lập**: nhận thực tế yêu cầu gọi `receive` cùng buffer và timeout. Trong API `MulticastSocket.joinGroup(SocketAddress, NetworkInterface)`, tham số `SocketAddress` biểu diễn **địa chỉ nhóm**; với implementation mặc định `InetSocketAddress`, **port trong đối số join bị bỏ qua vì lý do lịch sử**. Port nhận thật là port đã **bind** của socket (ở đây `5000`). Đừng tự kết luận `joinGroup(group:6000)` sẽ đổi cổng listener đang bind ở `5000`.

`netIf` nên khác `null`: Javadoc Java 17 nói nếu `null` mà chưa cấu hình interface outgoing, việc chọn interface có thể không xác định hoặc thất bại. Khi leave phải chỉ đúng **group + interface đã join**. Ví dụ join trên Wi-Fi nhưng leave trên VPN không phải cùng một membership.

Để lấy interface có tên đã biết:

~~~java
NetworkInterface netIf = NetworkInterface.getByName("interface-name");
if (netIf == null || !netIf.isUp() || !netIf.supportsMulticast()) {
    throw new IllegalStateException(
            "Network interface unavailable for multicast");
}
~~~

Đoạn này thuộc phương thức có `throws SocketException` (hoặc xử lý lỗi), cần `import java.net.NetworkInterface;` và `import java.net.SocketException;`. `getName()`/`getByName` dùng tên hệ điều hành, không bảo đảm Linux/Windows/macOS có cùng tên. Kiểm tra `supportsMulticast()` là **điều kiện sàng lọc**, không chứng minh mọi group và policy sẽ join thành công. Ngoài ra cần kiểm tra interface có địa chỉ tương thích IPv4/IPv6.

## 3. `MulticastSocket.joinGroup` / `leaveGroup`: giữ đúng cặp group–interface

API nên dùng trên Java 17:

~~~java
socket.joinGroup(new InetSocketAddress(group, 0), netIf);
socket.leaveGroup(new InetSocketAddress(group, 0), netIf);
~~~

Từ Java 14, các overload cũ `joinGroup(InetAddress)` và `leaveGroup(InetAddress)` được đánh dấu **deprecated** vì **không chỉ rõ network interface**. Với máy nhiều interface, dùng overload hai tham số để hành vi rõ ràng.

### 3.1. Join nhiều nhóm với cùng một receiver socket

~~~java
// Đoạn minh họa; socket đã bind, ni là interface hợp lệ.
InetSocketAddress groupA = new InetSocketAddress(
        InetAddress.getByName("239.255.42.10"), 0);
InetSocketAddress groupB = new InetSocketAddress(
        InetAddress.getByName("239.255.42.11"), 0);

socket.joinGroup(groupA, ni);
socket.joinGroup(groupB, ni);
// Lúc này socket đăng ký nhận cả A và B trên ni.
~~~

Rời từng nhóm:

~~~java
socket.leaveGroup(groupA, ni);
// B vẫn là membership của socket nếu không có lỗi/đổi trạng thái.
socket.leaveGroup(groupB, ni);
~~~

Javadoc `MulticastSocket` cho phép tham gia nhiều nhóm hoặc cùng nhóm trên nhiều mạng/interface. Song **join trùng một membership đã tham gia** có thể ném `IOException`; và **leave một group/interface không phải thành viên** cũng có thể ném `IOException`. Do đó, không viết code “cứ gọi join mỗi lần nhận cấu hình” hoặc “cứ gọi leave trong mọi nhánh finally” mà không theo dõi trạng thái thực.

### 3.2. Quản lý membership bằng registry

Với một socket dùng **một interface duy nhất**, có thể lưu `Set<InetSocketAddress>` của những nhóm **đã join thành công**. Cấu trúc này giúp:

- Bỏ qua yêu cầu join trùng do UI hoặc cấu hình được cập nhật lại.
- Chỉ gọi leave cho những nhóm đã gia nhập.
- Cập nhật registry **sau** khi lời gọi OS thành công; nếu `joinGroup` ném exception, không thêm group.
- Nếu `leaveGroup` ném exception, không tự xóa mục khỏi registry rồi khẳng định nó đã được rời.

Nếu **cùng socket** tham gia nhiều interface, phải định danh membership bằng **`(groupAddress, NetworkInterface)`**, không chỉ group. Ví dụ khóa:

~~~java
// Java 17 record minh họa, khai báo trong class hoặc ngoài class.
record GroupInterface(InetAddress group, NetworkInterface netIf) {}
~~~

Một khóa chỉ theo IP group sẽ mất khả năng phân biệt `G1@ifA` và `G1@ifB`, dẫn tới leave sai hoặc cập nhật trạng thái nhầm. Nếu có **nhiều socket/channel** được quản lý chung, còn phải ghi nhận owner socket/channel của từng membership.

### 3.3. Đặt `SO_REUSEADDR` trước bind khi nhiều listener chung port

Khi nhiều receiver cần bind cùng UDP port, thường phải cấu hình `SO_REUSEADDR` trước bind và kiểm tra chính sách OS. Không có bảo đảm rằng mọi kernel chia gói giống nhau cho nhiều socket trùng port. Với `MulticastSocket`, có thể chủ động tạo socket chưa bind:

~~~java
MulticastSocket socket =
        new MulticastSocket((SocketAddress) null);
try (socket) {
    socket.setReuseAddress(true);              // trước bind
    socket.bind(new InetSocketAddress(5000));   // wildcard local address
    // joinGroup(...) sau bind.
}
~~~

Đoạn này nằm trong phương thức xử lý `IOException` và cần import `SocketAddress`. Giá trị `5000` chỉ minh họa; có thể thất bại nếu cổng đang được sử dụng hoặc policy không cho bind. Với ví dụ học tập về **lifecycle membership**, dùng port `0` để OS chọn port động sẽ giảm xung đột; còn ứng dụng muốn nhận từ sender thật phải bind đúng port đã thỏa thuận.

## 4. Ví dụ hoàn chỉnh Java 17+: quản lý hai nhóm với `MulticastSocket`

Ví dụ dưới đây minh họa **join hai group → leave group A → giữ group B → cleanup B → close socket**. Không cần gửi datagram. Nó nhận **tên network interface** từ tham số chương trình để tránh chọn mặc định một interface sai. Có kiểm tra IPv4 và `supportsMulticast`, bỏ qua join trùng bằng registry, chỉ ghi nhận trạng thái sau thao tác thành công.

Tạo file **`MulticastSocketGroups.java`**:

~~~java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.net.SocketAddress;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

public final class MulticastSocketGroups {
    private static boolean hasIPv4(NetworkInterface iface) {
        return Collections.list(iface.getInetAddresses()).stream()
                .anyMatch(Inet4Address.class::isInstance);
    }

    private static void joinOnce(
            MulticastSocket socket,
            InetSocketAddress group,
            NetworkInterface iface,
            Set<InetSocketAddress> joined) throws IOException {
        if (joined.contains(group)) {
            return;
        }
        socket.joinGroup(group, iface);
        joined.add(group); // chỉ sau khi join thành công
    }

    private static void leaveIfJoined(
            MulticastSocket socket,
            InetSocketAddress group,
            NetworkInterface iface,
            Set<InetSocketAddress> joined) throws IOException {
        if (!joined.contains(group)) {
            return;
        }
        socket.leaveGroup(group, iface);
        joined.remove(group); // chỉ sau khi leave thành công
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java MulticastSocketGroups <interface-name>");
            return;
        }

        NetworkInterface iface = NetworkInterface.getByName(args[0]);
        if (iface == null || !iface.isUp()
                || !iface.supportsMulticast() || !hasIPv4(iface)) {
            System.out.println(
                    "SKIPPED: no IPv4 multicast on interface");
            return;
        }

        InetSocketAddress a = new InetSocketAddress(
                InetAddress.getByName("239.255.42.10"), 0);
        InetSocketAddress b = new InetSocketAddress(
                InetAddress.getByName("239.255.42.11"), 0);

        MulticastSocket socket =
                new MulticastSocket((SocketAddress) null);
        try (socket) {
            socket.setReuseAddress(true);
            socket.bind(new InetSocketAddress(0));

            Set<InetSocketAddress> joined = new LinkedHashSet<>();
            try {
                joinOnce(socket, a, iface, joined);
                joinOnce(socket, b, iface, joined);
                System.out.println("joined: " + joined.size());

                leaveIfJoined(socket, a, iface, joined);
                System.out.println(
                        "after leaving A: " + joined.size());
            } finally {
                for (InetSocketAddress group :
                        new ArrayList<>(joined)) {
                    try {
                        leaveIfJoined(
                                socket, group, iface, joined);
                    } catch (IOException ex) {
                        System.err.println(
                                "Cleanup error: "
                                + ex.getClass().getSimpleName());
                    }
                }
                // try-with-resources vẫn close socket nếu leave lỗi.
            }
            System.out.println(
                    "tracked after cleanup: " + joined.size());
        }
        System.out.println("closed: " + socket.isClosed());
    }
}
~~~

Biên dịch bằng JDK 17+ (tên interface **thực tế** khác nhau theo OS):

~~~bash
javac --release 17 MulticastSocketGroups.java
java MulticastSocketGroups "YOUR_INTERFACE_NAME"
~~~

Với interface IPv4 multicast hợp lệ và các thao tác join/leave thành công, stdout là:

~~~text
joined: 2
after leaving A: 1
tracked after cleanup: 0
closed: true
~~~

Nếu interface không tồn tại, đang down hoặc không công bố hỗ trợ multicast/IPv4, chương trình chỉ in:

~~~text
SKIPPED: no IPv4 multicast on interface
~~~

Nếu OS từ chối join/leave hoặc bind, có thể có `IOException`, cùng dòng lỗi cleanup trên stderr tùy nhánh. **Không được diễn giải SKIPPED hoặc IOException là “mã Java không compile”.** Đây là bài học về phụ thuộc môi trường multicast. Trên máy không có quyền multicast, cần chạy trong môi trường test phù hợp thay vì đổi cứng tên interface/địa chỉ tùy tiện.

**Điểm đáng học từ ví dụ:**

1. `joinOnce` không gọi join trùng trên cùng interface. Khi bài toán nhiều interface, mở rộng `Set` thành khóa `GroupInterface`.
2. `joinOnce` thêm vào registry **sau** `joinGroup`, nên lỗi ở group B không biến registry thành “đã tham gia B”.
3. Nếu group B join thất bại sau khi A đã join, nhánh `finally` cố gắng leave A; nếu leave thất bại, `try-with-resources` vẫn đóng socket.
4. Rời group A không đóng socket và không tự rời group B. Sau cleanup B, socket mới bị đóng khi ra khỏi khối `try`.
5. `tracked after cleanup: 0` chỉ phản ánh các lời gọi leave **đã thành công** được theo dõi; nó không phải bằng chứng kernel không còn datagram nào đang chờ, cũng không xác nhận mọi router đã cập nhật trạng thái membership ngay.
6. Ví dụ dùng port động vì **chỉ kiểm tra lifecycle**; để nhận dữ liệu thực, phải bind port của protocol và cấu hình source/target đúng.
7. Dòng `closed: true` xác nhận đối tượng socket đã đóng sau `try-with-resources`; không được gọi lại `joinGroup` trên cùng đối tượng đã đóng.

Chương trình xử lý lỗi trong `finally` theo hướng best effort để các membership khác vẫn có cơ hội leave; trong service thực tế cần ghi log có group/interface, và có thể báo tổng hợp cleanup failure qua exception/suppressed exception theo chính sách ứng dụng. Không nên che khuất lỗi join ban đầu bằng một cleanup exception phụ.

## 5. NIO `DatagramChannel`: membership là một `MembershipKey`

`DatagramChannel` triển khai `MulticastChannel`. Java 17 dùng:

~~~java
MembershipKey key = channel.join(group, netIf);
key.drop();
boolean stillJoined = key.isValid();
~~~

`MembershipKey` gắn với **channel, group, network interface và (nếu có) source filter**. Các phương thức chính:

| API | Ý nghĩa |
| --- | --- |
| `key.group()` | Trả địa chỉ group mà key đại diện |
| `key.networkInterface()` | Trả interface nơi group được join |
| `key.channel()` | Trả channel sở hữu membership |
| `key.sourceAddress()` | Địa chỉ source được lọc, hoặc `null` nếu any-source multicast |
| `key.isValid()` | `true` cho đến khi drop hoặc channel đóng |
| `key.drop()` | Rời membership, làm key invalid; gọi lại trên key đã invalid là no-op |
| `channel.close()` | Đóng channel và **làm invalid toàn bộ membership keys** còn gắn với channel |

### 5.1. `drop` chỉ ảnh hưởng đúng key

Giả sử:

~~~java
MembershipKey a = channel.join(groupA, ni);
MembershipKey b = channel.join(groupB, ni);
a.drop();
~~~

Sau `a.drop()`, `a.isValid() == false` nhưng `b.isValid()` **vẫn true** nếu channel vẫn mở và B chưa drop. Thực hiện `a.drop()` lần nữa không tạo thêm leave operation có ý nghĩa; key đã invalid không thể được hồi sinh. Muốn tham gia lại group A, gọi **`channel.join(groupA, ni)`** và lưu **key mới**.

Nếu đã join **cùng group + interface** với any-source membership, gọi `channel.join(group, ni)` lần nữa theo Javadoc sẽ **trả lại key cho membership hiện tại**, khác với `MulticastSocket.joinGroup` có thể ném lỗi khi join trùng. Tuy nhiên registry vẫn hữu ích vì nó lưu ý định của ứng dụng, trách nhiệm sở hữu và trạng thái từng nhóm.

### 5.2. `drop` không nhất thiết làm receiver ngừng nhận tức thì

Javadoc `MembershipKey.drop` lưu ý: sau khi rời membership vẫn **có thể nhận datagram đã nằm trong receive buffer**. Vì vậy:

- Không viết unit test “drop xong, mọi lần receive tiếp theo phải không có gói của group đó”.
- Nếu cần ngừng xử lý nghiệp vụ ngay, cập nhật **tập group đang được ứng dụng cho phép** và xác thực message/metadata theo protocol, không chỉ trông vào cơ chế OS filter.
- Phân biệt **đăng ký nhận** đã hủy với **dữ liệu đã được nhận và xếp hàng** trước đó.
- Trong trường hợp multicast trên một socket có nhiều group, API receive thường trả địa chỉ nguồn của sender; nó **không cung cấp một trường phổ quát chứng minh packet đến từ group đích nào**. Nếu cần phân luồng chắc chắn, thiết kế message type/group identifier có xác thực phù hợp, hoặc dùng kiến trúc socket/channel riêng trong giới hạn hệ thống.

### 5.3. `close` tự invalid mọi key còn lại

`MulticastChannel.close()` theo contract: đóng channel khi vẫn là thành viên của group sẽ drop membership; khi hàm trả về, membership key phải invalid. `MembershipKey.isValid()` cho phép kiểm chứng rõ điều này, khác API `MulticastSocket` không cung cấp token membership tương đương.

Điều này giúp viết shutdown idempotent:

~~~java
// Đoạn minh họa: key và channel tồn tại.
if (key.isValid()) {
    key.drop();
}
channel.close();
// key.isValid() -> false
~~~

Trong hệ thống đa nhóm, có thể `drop` tất cả key để thể hiện ý định shutdown và cập nhật registry, sau đó **luôn đóng channel** trong `finally`. Nếu cần đóng ngay vì thread đang blocked ở `receive`, `close` cũng chấm dứt hoạt động chờ theo contract channel và thread đang chạy cần xử lý ngoại lệ đóng phù hợp. Không giữ vòng lặp retry vô hạn sau khi channel đã đóng.

## 6. Ví dụ Java 17+ hoàn chỉnh: hai nhóm và `MembershipKey`

Tạo file **`MulticastChannelKeys.java`**:

~~~java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.util.Collections;

public final class MulticastChannelKeys {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java MulticastChannelKeys <interface-name>");
            return;
        }

        NetworkInterface iface = NetworkInterface.getByName(args[0]);
        if (iface == null || !iface.isUp()
                || !iface.supportsMulticast()
                || Collections.list(iface.getInetAddresses()).stream()
                        .noneMatch(Inet4Address.class::isInstance)) {
            System.out.println(
                    "SKIPPED: no IPv4 multicast on interface");
            return;
        }

        InetAddress a = InetAddress.getByName("239.255.42.10");
        InetAddress b = InetAddress.getByName("239.255.42.11");

        MembershipKey second;
        try (DatagramChannel channel = DatagramChannel.open(
                StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0)); // wildcard, port OS chọn

            MembershipKey first = channel.join(a, iface);
            second = channel.join(b, iface);

            System.out.println("both valid: "
                    + (first.isValid() && second.isValid()));

            first.drop();
            System.out.println("first dropped: " + !first.isValid());
            System.out.println("second remains: " + second.isValid());
        }

        System.out.println(
                "second invalid after close: " + !second.isValid());
    }
}
~~~

~~~bash
javac --release 17 MulticastChannelKeys.java
java MulticastChannelKeys "YOUR_INTERFACE_NAME"
~~~

Nếu OS, protocol family, interface và quyền cho phép cả hai join, stdout chính xác:

~~~text
both valid: true
first dropped: true
second remains: true
second invalid after close: true
~~~

Nếu interface không thích hợp, stdout chỉ có:

~~~text
SKIPPED: no IPv4 multicast on interface
~~~

Nếu OS không hỗ trợ join hoặc gặp lỗi socket, chương trình có thể ném `IOException` hoặc `UnsupportedOperationException`; đó là điều kiện môi trường. Trong ví dụ, `try-with-resources` luôn đóng channel khi ra khỏi khối; nếu join A thành công mà join B thất bại, việc đóng channel dọn membership A. Do đó không cần `catch` chỉ để “giả vờ join thành công”.

**Giải thích từng bước:**

1. `DatagramChannel.open(StandardProtocolFamily.INET)` tạo channel IPv4 tương thích với hai IPv4 multicast group. Không tùy tiện dùng `INET6` rồi giả định IPv4 group vẫn hoạt động trên mọi OS.
2. `SO_REUSEADDR` đặt **trước** `bind`; NIO multicast Javadoc khuyến nghị bind wildcard và reuse address để nhiều subscriber có thể cùng dùng port trong môi trường hỗ trợ.
3. `join` trả hai key độc lập vì hai group khác nhau. Chúng còn valid khi channel mở.
4. `first.drop()` chỉ rời A; B tiếp tục valid cho đến khi channel đóng.
5. Hết `try` gọi `channel.close()`. Sau khi close, `second.isValid()` trở thành `false` theo contract.
6. Không có multicast sender trong ví dụ; nó kiểm tra **lifecycle membership**, không phải delivery. Port động chỉ phù hợp cho thí nghiệm này.

## 7. Quản lý nhiều group với một registry NIO

Với NIO, nên lưu key tương ứng từng đăng ký thay vì chỉ một biến `lastKey`:

~~~java
// Pseudocode có khai báo record/class phù hợp bên ngoài.
record GroupInterface(InetAddress group, NetworkInterface iface) {}

Map<GroupInterface, MembershipKey> active = new HashMap<>();

void joinIfNeeded(
        DatagramChannel channel,
        InetAddress group,
        NetworkInterface iface) throws IOException {
    GroupInterface id = new GroupInterface(group, iface);
    MembershipKey old = active.get(id);
    if (old != null && old.isValid()) {
        return;
    }
    MembershipKey key = channel.join(group, iface);
    active.put(id, key);
}

void leaveIfPresent(InetAddress group, NetworkInterface iface) {
    MembershipKey key =
            active.remove(new GroupInterface(group, iface));
    if (key != null) {
        key.drop();
    }
}
~~~

Đây là **pseudocode thiết kế**, không phải Java class độc lập: `active` là field của manager, các method ở trong class và cần import các kiểu liên quan. Nó cho thấy **chỉ giữ key sau join thành công** và **chỉ drop đúng key**. Khi channel đóng, phải xóa/đánh dấu registry tương ứng để tránh những key invalid còn sót; `key.isValid()` giúp phát hiện tình trạng đó.

Nếu app chạy đa luồng, tránh để hai thread đồng thời gọi join/leave và sửa `HashMap` không đồng bộ. Có thể chuyển tất cả thay đổi membership vào **một event loop/worker quản lý channel**, hoặc đồng bộ registry thích hợp. Đừng giữ một lock quản lý membership trong lời gọi `receive` blocking kéo dài.

Một shutdown manager nên thực hiện:

1. Ngừng nhận yêu cầu subscribe mới và báo consumer không xử lý thêm dữ liệu của group bị gỡ.
2. Lấy snapshot các key còn valid.
3. `drop` từng key (mỗi key có thể đã invalid vì lỗi/close trước đó).
4. Luôn `close` channel trong `finally`; việc này xử lý cả những membership chưa drop được.
5. Xóa registry, giải phóng executor/selector và cập nhật trạng thái service khi tài nguyên thật sự đóng.

Trong nhiều lớp dịch vụ, nên phân biệt **desired subscriptions** (những nhóm cấu hình muốn tham gia) với **active memberships** (những key hiện đang valid). Khi interface down, socket được mở lại hoặc config thay đổi, service có thể reconcile hai tập để join lại các mục còn mong muốn. Một key invalid không thể phục hồi chỉ bằng cách đổi `isValid`.

## 8. Những trường hợp khác biệt dễ gây lỗi

### 8.1. Cùng một group trên hai interface

Ví dụ `group = 239.255.42.10` trên Wi-Fi và Ethernet:

~~~text
(group, Wi-Fi)      -> membership 1
(group, Ethernet)   -> membership 2
~~~

`leaveGroup(group, ethernet)` không có nghĩa rời group trên Wi-Fi. Với NIO, `keyForEthernet.drop()` không làm `keyForWifi` invalid. Vì vậy registry chỉ dùng `InetAddress` làm khóa là không đủ. **Cùng group nhưng khác interface là hai đăng ký khác nhau** khi platform hỗ trợ.

Interface có thể đổi trạng thái trong lúc chương trình chạy. Không dựa vào `NetworkInterface.getIndex()` hoặc tên interface như một định danh bền vững qua mọi lần restart/hot-plug; sau khi phát hiện thay đổi, truy vấn lại interface phù hợp và kiểm tra trạng thái thực trước khi join.

### 8.2. Một interface, nhiều group nhưng chỉ một port

Một `MulticastSocket(5000)` có thể subscribe nhiều group cùng nhận datagram gửi tới port `5000`. Việc chọn group A/B không cho phép cùng socket nhận gói gửi tới nhiều port khác nhau một cách tự động.

Nếu ứng dụng cần phân chia group ở các port khác nhau, có thể cần **nhiều socket/channel**, mỗi cái bind port thích hợp. Cũng cần hiểu hành vi phân phối datagram khi nhiều socket bind cùng port có thể khác theo OS.

### 8.3. `leaveGroup` không tự xóa các packet đã nhận

Sau leave, những datagram đã nằm trong socket receive buffer có thể vẫn được đọc. Với NIO, đây là ghi chú trong `MembershipKey.drop`. Đừng lấy một gói “còn nhận được sau leave” làm bằng chứng đơn giản rằng lời gọi leave đã thất bại; kiểm tra thời điểm packet được kernel nhận, registry và traffic test có kiểm soát.

Khi ứng dụng yêu cầu “ngừng xử lý từ group X ngay”, cần chuyển **logic phân loại/cho phép nhận** sang tầng ứng dụng. Đặc biệt, `DatagramPacket.getAddress()` cho **IP nguồn** của sender, **không** cho địa chỉ multicast đích của gói. Nếu phân loại theo group là yêu cầu chức năng, dùng cơ chế nhận metadata đích phù hợp với nền tảng (khi có) hoặc cấu trúc ứng dụng/message riêng; không nhầm IP source là multicast group.

### 8.4. Một socket đã close không thể “join lại”

~~~java
socket.close();
socket.joinGroup(groupAddress, netIf); // không hợp lệ
~~~

Đây là minh họa **sai**. Cần tạo socket/channel **mới**, bind port cần thiết, cấu hình interface rồi join lại các group còn mong muốn. Với `DatagramChannel`, membership key cũ đã invalid vĩnh viễn; dù mở channel mới với cùng địa chỉ và port cũng phải dùng **key mới**.

### 8.5. Source-specific multicast và bộ lọc nguồn

`MulticastChannel.join(group, iface, source)` có thể đăng ký chỉ nhận từ một **source IP** cụ thể (SSM) khi OS hỗ trợ. Mỗi `MembershipKey` biểu diễn group/interface/source; gọi `drop()` trên key đó dừng membership nguồn tương ứng, không nhất thiết rời toàn bộ group theo mô hình any-source.

Các lời gọi `block(source)` và `unblock(source)` trên key any-source cần hỗ trợ source filtering của OS; không phải mọi nền tảng đều có. Không trộn tùy tiện any-source membership và source-specific memberships cho **cùng group/interface**: Javadoc có thể ném `IllegalStateException` khi yêu cầu mâu thuẫn với trạng thái đã có. Với scope bài này, chỉ cần nhớ **registry key của SSM phải bao gồm source** và `drop` tác động đúng key.

## 9. Chọn giữa explicit leave và close

| Tình huống | Nên làm gì? | Vì sao? |
| --- | --- | --- |
| Người dùng bỏ theo dõi group A, vẫn cần B | `leaveGroup(A, ifA)` hoặc `keyA.drop()` | Chỉ thay membership A, không dừng listener chung |
| Ứng dụng đổi A từ interface 1 sang interface 2 | Join mới trên interface 2 và rời cũ theo thứ tự phù hợp yêu cầu liên tục; xử lý rollback | Không mất dữ liệu tùy tiện khi chuyển interface |
| Một lần join nhiều nhóm, join ở giữa thất bại | Cleanup mọi membership đã join thành công; luôn close socket/channel nếu không tiếp tục hoạt động | Tránh rò tài nguyên và trạng thái nửa chừng |
| Shutdown toàn bộ receiver | Ngừng subscription, drop/leave best effort rồi close trong `finally` | Đảm bảo OS handle được giải phóng dù cleanup lỗi |
| Channel đã đóng bất ngờ | Xóa/sync lại registry, tạo channel mới rồi join các desired group | Key cũ invalid, không thể dùng lại |
| Chỉ muốn gửi multicast, không muốn nhận | Không cần join chỉ để gửi | Sender multicast không bắt buộc phải là receiver |
| Đổi port lắng nghe | Tạo/bind socket với port mới, join lại các group tương ứng | Membership không tự làm socket đổi local port |

**Explicit leave** có lợi khi muốn giữ socket sống và quản lý từng nhóm chính xác. **Close** là ranh giới tài nguyên cuối cùng; phải có kể cả khi không có yêu cầu leave từng nhóm từ UI. Đừng lấy việc bỏ tham chiếu Java để thay cho `close`: GC không phải cơ chế shutdown mạng có thời điểm xác định.

## 10. Lỗi, cleanup và logging khi quản lý group

| Trạng thái/lỗi | Nguyên nhân có thể | Phản ứng phù hợp |
| --- | --- | --- |
| `joinGroup` ném `IOException` | Group không hợp lệ, OS không hỗ trợ, interface sai/down, đã là member | Không thêm vào registry; log group/interface và nguyên nhân |
| `leaveGroup` ném `IOException` | Chưa join group/interface tương ứng, socket lỗi/đã đóng | Không đánh dấu đã leave thành công; tiếp tục cleanup các membership khác khi cần |
| `NetworkInterface.supportsMulticast() == false` | Interface không quảng bá hỗ trợ multicast | Không thử join mù; chọn interface phù hợp được phép |
| `join` của channel ném `IllegalArgumentException` | Group không phải multicast hoặc address family không phù hợp | Kiểm tra tham số và protocol family |
| `join` hoặc filtering ném `UnsupportedOperationException` | Platform thiếu multicast/source filtering theo yêu cầu | Fallback khi chức năng optional hoặc fail fast nếu bắt buộc |
| `MembershipKey.isValid() == false` | Key đã `drop` hoặc channel đã đóng | Không dùng key cũ; join lại khi channel phù hợp đang mở |
| `ClosedChannelException` / `AsynchronousCloseException` | Channel đóng khi thao tác I/O đang/chưa chạy | Dừng I/O, kiểm tra shutdown hoặc race, không tự retry vô hạn |
| `SocketException` khi đang `receive` | Socket có thể bị `close` từ thread khác hoặc có lỗi OS | Phân biệt shutdown chủ động với lỗi mạng cần báo cáo |
| Không nhận multicast dù join thành công | Firewall, router TTL/scope, IGMP/MLD, OS interface, sender dùng sai group/port | Kiểm tra bind, membership, interface, packet capture hoặc thử nghiệm trên mạng được kiểm soát |
| Vẫn thấy packet sau drop/leave | Packet được xếp hàng trước khi rời hoặc nhận từ membership khác | Không khẳng định leave thất bại chỉ từ một packet |

Với đa nhóm, log tối thiểu nên chứa `group IP`, `interface name/index`, `local bind port`, `action=JOIN/LEAVE/DROP/CLOSE`, kết quả và exception type. Đừng ghi payload nhạy cảm hay thông tin cá nhân không cần cho chẩn đoán. Đừng log “left all groups” khi chỉ mới gọi `close` sau khi leave một nhóm bị lỗi mà chưa xác minh state mong muốn; thay vào đó ghi socket đã đóng và membership keys đã invalid theo contract.

### 10.1. Cleanup khi một trong nhiều group join thất bại

Sai:

~~~java
socket.joinGroup(groupA, ni);
socket.joinGroup(groupB, ni); // lỗi ở đây
socket.leaveGroup(groupA, ni); // sẽ không chạy
~~~

Đây là **mã cố ý sai**, thiếu `finally`. Nếu join B thất bại, A vẫn được join và socket có thể còn mở nếu caller không đóng. Mẫu tốt hơn: dùng `try-with-resources` ở vòng đời socket và `finally` dựa trên tập membership **đã join thành công**, như `MulticastSocketGroups` phía trên.

Trong NIO, `try (DatagramChannel channel = ...)` đảm bảo `close()` kể cả khi join một group ở giữa gặp exception. Nếu cần tiếp tục dùng channel sau lỗi một group, phải xử lý lỗi ở mức membership và quyết định **desired set** nào vẫn được giữ; không mặc nhiên hủy toàn bộ nếu chính sách sản phẩm cho phép tiếp tục.

### 10.2. Cleanup khi nhận dữ liệu ở thread khác

Một thread có thể đang blocked trong `receive` trong khi thread điều khiển yêu cầu shutdown. Các bước thực tế:

1. Chuyển trạng thái service sang stopping, không nhận lệnh join mới.
2. Dừng logic tiêu thụ message của các group đã bị disable.
3. Nếu cần dừng ngay một blocking receive, đóng socket/channel sẽ làm thao tác đang chờ kết thúc bằng ngoại lệ phù hợp; thread xử lý nhánh shutdown dự kiến.
4. Chờ loop nhận kết thúc theo cơ chế quản lý thread/executor của ứng dụng.
5. Đảm bảo không thread nào truy cập registry/socket sau khi chúng đã bị đóng.

Nếu chỉ rời một group nhưng vẫn nhận B, **không close** socket dùng chung chỉ để hủy blocking receive của A: như vậy sẽ làm rơi cả B. Hãy thiết kế receive loop để định kỳ xét desired subscriptions hoặc có đường điều khiển riêng.

## 11. Tình huống thực tế: cấu hình danh sách group thay đổi

Giả sử receiver ban đầu muốn:

~~~text
desired = { G1@ifA, G2@ifA }
active  = { G1@ifA, G2@ifA }
~~~

Sau cập nhật:

~~~text
desired = { G2@ifA, G3@ifA }
active  = { G1@ifA, G2@ifA }
~~~

Bộ quản lý cần thực hiện một **reconcile**:

- Tính `toJoin = desired − active`: thêm `G3@ifA`.
- Tính `toLeave = active − desired`: rời `G1@ifA`.
- `G2@ifA` được giữ nguyên, không join lại.
- Chỉ cập nhật `active` cho những lời gọi join/leave đã thành công; lỗi cần ghi nhận để retry có kiểm soát hoặc giữ báo động cấu hình.
- Sau khi thay đổi interface hoặc socket, đánh giá lại tất cả membership và tránh dùng key đã invalid.

Tùy mục tiêu có thể **join G3 trước rồi leave G1** để giảm khoảng mất dữ liệu, hoặc leave cũ trước khi join mới nếu có ràng buộc tài nguyên/độc quyền. Không có một thứ tự mặc định đúng cho mọi hệ thống. Với NIO và `MembershipKey`, nên duy trì registry `Map<GroupInterface, MembershipKey>`; với classic socket, giữ `Set<GroupInterface>` đồng bộ với các join/leave thành công.

Nếu nhiều event cấu hình đến nhanh, serialize chúng qua một owner thread để không xảy ra race “join A” trong lúc một luồng khác vừa “leave A”. Retry cần backoff và nguyên nhân rõ ràng; không lặp nhanh không giới hạn khi OS đang từ chối multicast.

## 12. Kiểm thử vòng đời và giới hạn của kiểm thử multicast

### 12.1. Unit test logic membership

Không cần tạo traffic thật để kiểm tra:

- Quy tắc tính `toJoin` / `toLeave` của desired-vs-active.
- Tránh join trùng đối với same group/interface.
- Giữ đúng registry khi một join thất bại.
- Rời group A không xóa group B khỏi trạng thái ứng dụng.
- Close sau cleanup, kể cả khi một thao tác leave thất bại.
- Phân biệt group giống nhau trên hai interface.

Nên đưa thao tác OS thực vào một abstraction nhỏ khi cần giả lập lỗi, ví dụ interface với `join`, `leave`, `close`. Đừng viết unit test dựa vào port multicast cố định hoặc tên card mạng của người phát triển.

### 12.2. Integration test trên OS/JDK mục tiêu

Một bài kiểm thử có mạng thật cần tối thiểu:

1. Chọn interface đang up, supports multicast và có address family phù hợp.
2. Bind receiver vào **port do test kiểm soát**, bật reuse address đúng thời điểm.
3. Join G1 và G2 trên interface ấy.
4. Sender gửi datagram tới `G1:port` và `G2:port` với TTL/scope phù hợp; receiver kiểm tra payload/protocol ID.
5. Leave G1, tiếp tục xác nhận G2 vẫn nhận được.
6. Không khẳng định “không có gói G1 nào nữa” ngay tức thì vì kernel receive buffer có thể chứa packet cũ; dùng message IDs, quãng thời gian drain thích hợp và nhận định đúng giới hạn.
7. Close receiver và kiểm tra key invalid nếu dùng NIO; thử mở receiver mới/bind lại chỉ khi môi trường cho phép.
8. Lặp trên các JDK/OS/containers mà ứng dụng hỗ trợ.

Cần nhớ: **multicast loopback trên cùng một máy có thể bị cấu hình khác với mạng LAN thật**. NIC, firewall, router và kernel khác nhau làm kết quả khác nhau. Giữ timeout hữu hạn và cho phép báo `SKIPPED/UNSUPPORTED` khi môi trường CI hoàn toàn không hỗ trợ multicast, nhưng không “pass” giả để che thiếu coverage của môi trường production mục tiêu.

### 12.3. Phân biệt ba bằng chứng

| Bằng chứng | Xác nhận được gì? | Chưa xác nhận được gì? |
| --- | --- | --- |
| `joinGroup`/`join` thành công | OS/JDK chấp nhận membership tại thời điểm đó | Có packet nào được gửi hoặc giao thành công |
| `leaveGroup` trả về / `key.isValid()==false` | Membership đã được rời về mặt API/token | Mọi packet đợi trong buffer đã biến mất |
| `close` thành công / `channel.isOpen()==false` | Socket/channel không còn mở | Những client khác tự biết nên chuyển group/port, hay mạng đã đồng bộ ngay |

Không biến “membership registered” thành “service healthy”. Nếu dịch vụ cần phát hiện mất nguồn dữ liệu multicast, hãy theo dõi heartbeat, sequence number hoặc timestamp ở protocol tầng ứng dụng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một `MulticastSocket` đã join A và B trên cùng interface. Gọi `leaveGroup(A, ni)` có buộc đóng socket không?  
**Đáp án:** Không. Socket còn mở và membership B vẫn được giữ nếu không có lỗi hoặc thay đổi khác.

**Câu 2.** Join `G1` trên Wi-Fi, sau đó dùng `leaveGroup(G1, ethernet)` để rời. Có tương đương?  
**Đáp án:** Không. Membership phải được nhận diện theo group và interface đã join; lời gọi leave sai interface có thể ném `IOException`.

**Câu 3.** Gọi `MulticastSocket.joinGroup(G1, ni)` lần hai khi đã là thành viên thì sao?  
**Đáp án:** Theo hợp đồng `MulticastSocket`, có thể ném `IOException`. Hãy theo dõi registry và tránh join trùng.

**Câu 4.** NIO `DatagramChannel.join(G1, ni)` lần hai có giống trên không?  
**Đáp án:** Không hoàn toàn. Với any-source membership đang tồn tại cho cùng group/interface, Javadoc quy định trả key của membership hiện có.

**Câu 5.** Sau `keyA.drop()`, key A có thể tự trở lại valid không?  
**Đáp án:** Không. Key invalid vĩnh viễn; muốn join lại phải gọi `channel.join` và lấy key mới.

**Câu 6.** Sau `channel.close()`, key B chưa drop thủ công còn valid không?  
**Đáp án:** Không. Đóng channel làm membership bị drop và key invalid theo hợp đồng `MulticastChannel`.

**Câu 7.** Vì sao có thể còn đọc packet từ A ngay sau `keyA.drop()`?  
**Đáp án:** Packet đã được kernel nhận và đặt trong receive buffer trước khi membership được hủy.

**Câu 8.** `joinGroup(new InetSocketAddress(G1, 9000), ni)` có đổi local port mà socket đang bind là `5000` thành `9000` không?  
**Đáp án:** Không. Port trong `InetSocketAddress` của lời gọi join bị bỏ qua theo implementation mặc định; local bind port không bị thay đổi.

**Câu 9.** Nếu join A thành công, join B lỗi, phải xử lý A ra sao?  
**Đáp án:** Cleanup A theo registry nếu tiếp tục giữ socket; luôn đóng tài nguyên nếu huỷ toàn bộ quá trình. Không thêm B vào registry khi join chưa thành công.

**Câu 10.** Một socket thuộc nhiều group nhận packet có source IP `192.0.2.40`. Có thể suy ra packet gửi vào group nào từ `DatagramPacket.getAddress()` không?  
**Đáp án:** Không. Phương thức đó là **địa chỉ nguồn**, không phải group multicast đích. Thiết kế protocol/architecture riêng nếu cần phân luồng group.

**Câu 11.** Có cần join group mới gửi multicast tới group đó không?  
**Đáp án:** Không. Sender không bắt buộc phải đăng ký nhận multicast để gửi.

**Câu 12.** Khi cấu hình bỏ G1 và thêm G3, có nên leave/join lại G2 vốn vẫn đang active?  
**Đáp án:** Thông thường không. Tính phần chênh lệch desired/active và chỉ thay các membership thực sự cần; giữ G2 khi vẫn hợp lệ.

## 14. Checklist triển khai

1. **Chọn đúng interface** và IP family; kiểm tra trạng thái, multicast capability và quyền OS.
2. **Bind đúng port** nhận của protocol; dùng wildcard cho multicast khi thích hợp; `SO_REUSEADDR` trước bind nếu có nhiều listener.
3. **Dùng API có interface tường minh**: `joinGroup(SocketAddress, NetworkInterface)` / `leaveGroup(SocketAddress, NetworkInterface)` hoặc `DatagramChannel.join(group, iface)`.
4. **Định danh membership** theo group + interface (và source với SSM); thêm owner socket/channel khi có nhiều resource.
5. **Tránh join trùng** và chỉ ghi registry sau khi OS thao tác thành công.
6. **Rời riêng từng nhóm** khi ứng dụng còn muốn nhận nhóm khác; không close socket dùng chung vì yêu cầu leave một nhóm.
7. **NIO: giữ `MembershipKey`**, dùng `drop/isValid`, không tái sử dụng key invalid, hiểu queued datagrams sau drop.
8. **Shutdown luôn close** bằng `try-with-resources` hoặc `finally`, kể cả khi explicit leave lỗi.
9. **Reconcile desired-vs-active** sau thay đổi cấu hình, interface hoặc reconnect/recreate channel; serialize cập nhật membership.
10. **Test traffic thực trên môi trường đích**, không nhầm join/leave thành công với delivery hoặc xác thực nguồn dữ liệu.

## Tài liệu chính thức

- [Java SE 17 — `MulticastSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/MulticastSocket.html): nhiều membership, join/leave theo interface, duplicate join/leave và các overload deprecated.
- [Java SE 17 — `MulticastChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): joining nhiều nhóm, platform dependencies, channel close làm drop memberships.
- [Java SE 17 — `MembershipKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): `drop`, `isValid`, `group`, `networkInterface`, `sourceAddress`, queued datagrams sau drop.
- [Java SE 17 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): protocol family, send/receive, channel lifecycle.
- [Java SE 17 — `NetworkInterface`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): `getByName`, `isUp`, `supportsMulticast` và địa chỉ trên NIC.
- [Java SE 17 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_REUSEADDR`, `IP_MULTICAST_IF`, `IP_MULTICAST_LOOP`, `IP_MULTICAST_TTL`.

**Điều cần nhớ:** membership là một đăng ký nhận gắn với **group + interface + socket/channel**, còn `close` là điểm kết thúc vòng đời tài nguyên. Dùng **explicit leave/drop** để quản lý từng nhóm, và dùng **close** để bảo đảm giải phóng tất cả resource khi receiver kết thúc.
