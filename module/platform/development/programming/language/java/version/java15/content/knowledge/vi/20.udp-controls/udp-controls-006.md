# MembershipKey và vòng đời tham gia nhóm multicast UDP trong Java

> **Phạm vi:** Nội dung thuộc nhóm **Điều khiển UDP** của module Java 15. Bài tập trung vào **`java.nio.channels.MembershipKey`**: nhận key từ `DatagramChannel.join(...)`, kiểm tra `isValid()`, rời nhóm bằng `drop()`, tham gia lại, đóng channel, và quản lý nhận dữ liệu từ mọi nguồn hoặc nguồn cụ thể bằng `block()/unblock()`. Đây là các API Java NIO **ổn định từ Java 7** và vẫn được hỗ trợ trên JDK 17, 21, 25 trở lên. Ví dụ thực hành dùng **Java 17+**, không dùng các overload đa hướng đã bị deprecate hoặc cấu trúc mạng lỗi thời.

## 1. Vì sao ứng dụng UDP cần “tham gia nhóm”?

UDP thường được dùng theo mô hình **unicast**: một datagram được gửi đến **một địa chỉ IP đích và một cổng**. IP **multicast** lại cho phép một nguồn gửi datagram đến **địa chỉ nhóm**, còn những máy/ứng dụng đã tham gia nhóm trên interface phù hợp có thể nhận các datagram được phân phối đến nhóm đó.

Ví dụ:

```text
                      Sender
                    192.0.2.10
                         |
                         |  UDP datagram
                         |  destination = 239.192.0.77:51000
                         v
                IP multicast network
                   /           \
                  /             \
             Receiver A       Receiver B
             đã join          đã join
             group G          group G
             trên NIC A       trên NIC B

         Receiver C chưa join: không có membership
         do chương trình yêu cầu cho group G.
```

Đây là **sơ đồ ý tưởng**, không phải bảo đảm mọi mạng đều chuyển multicast. Hệ điều hành, router, IGMP (IPv4)/MLD (IPv6), firewall, VLAN và cấu hình của network interface quyết định datagram có được phân phối thật hay không.

Trong Java NIO, câu lệnh trọng tâm là:

```java
MembershipKey key = channel.join(group, networkInterface);
```

- `channel` là `DatagramChannel` hỗ trợ multicast.
- `group` là **địa chỉ IP multicast**, không phải một cổng, ví dụ `239.192.0.77`.
- `networkInterface` là giao diện mạng **cục bộ** muốn tham gia nhóm.
- `key` là đối tượng **đại diện quyền thành viên** của channel trong group trên interface đó.

**Không phải** gọi `join` cho từng datagram. Một membership thường tồn tại qua nhiều lần nhận cho đến khi ứng dụng gọi `drop()` hoặc đóng channel.

### “Group” khác “port”

Một multicast group được xác định bằng **multicast IP address**; còn UDP port chỉ định **ứng dụng/endpoint nhận**:

```text
group = 239.192.0.77        // địa chỉ nhóm multicast
port  = 51000               // cổng UDP mà receiver bind
NIC   = Ethernet/Wi-Fi/...  // interface cục bộ tham gia nhóm
```

`MembershipKey` lưu thông tin **group + interface + channel + source tùy chọn**, **không có thuộc tính port**. Cổng được gắn vào **socket/channel thông qua bind**, chứ không phải do `MembershipKey` cấp.

## 2. Những kiểu/API Java cần nhớ

| API | Vai trò chính | Ghi nhớ |
| --- | --- | --- |
| `DatagramChannel` | Channel UDP NIO để gửi, nhận và join multicast | Hiện thực `MulticastChannel` |
| `MulticastChannel.join(group, interf)` | Tham gia nhóm nhận từ **mọi nguồn** | Trả `MembershipKey` |
| `MulticastChannel.join(group, interf, source)` | Tham gia nhóm chỉ từ **một nguồn** | Trả `MembershipKey` loại source-specific |
| `MembershipKey` | Token đại diện một membership | Giữ key để quản lý vòng đời |
| `MembershipKey.isValid()` | Kiểm tra membership còn hiệu lực không | Không đảm bảo mạng đang chuyển gói |
| `MembershipKey.drop()` | Bỏ membership do key đại diện | Key trở thành invalid vĩnh viễn |
| `MembershipKey.block(source)` | Chặn nguồn trên **any-source membership** | Phụ thuộc hệ điều hành hỗ trợ source filtering |
| `MembershipKey.unblock(source)` | Bỏ chặn nguồn đã bị block | Không hoạt động với source chưa từng được block |
| `MembershipKey.sourceAddress()` | Trả nguồn nếu membership source-specific, ngược lại `null` | Phân biệt hai kiểu membership |
| `NetworkInterface` | Đại diện interface mạng cục bộ | Chọn interface phù hợp protocol family |
| `StandardSocketOptions.SO_REUSEADDR` | Tùy chọn reuse địa chỉ trước bind | Quan trọng khi nhiều receiver cùng dùng cổng |
| `StandardSocketOptions.IP_MULTICAST_IF` | Chọn interface **gửi multicast đi** | Không thay cho tham số interface của `join` |
| `StandardProtocolFamily.INET` | Tạo IPv4 DatagramChannel | Chọn family tương ứng multicast group IPv4 |

**Đừng nhầm** `MembershipKey` với `SelectionKey` của `Selector` hoặc `KeyPair` của crypto: chúng là các loại “key” cho các mục đích hoàn toàn khác nhau.

## 3. Tạo channel và gọi join đúng trình tự

Một khuôn mẫu chuẩn cho multicast IPv4:

```java
import java.net.*;
import java.nio.channels.*;

InetAddress group = InetAddress.getByName("239.192.0.77");
NetworkInterface ni = NetworkInterface.getByName("eth0");

try (DatagramChannel dc =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    dc.bind(new InetSocketAddress(51000)); // wildcard:port
    MembershipKey key = dc.join(group, ni);

    // Tại đây có thể receive datagram từ nhóm.
    // Sau đó rời nhóm có chủ đích.
    key.drop();
}
```

**Đây là snippet**, không phải chương trình độc lập. Tên `"eth0"` chỉ minh họa: Windows, Linux, macOS hoặc container có tên interface khác; nếu `getByName(...)` trả `null` phải xử lý, không tự truyền `null` vào `join`. Ví dụ runnable có chọn interface ở phần 7.

Thứ tự cần chú ý:

1. **Chọn protocol family**: `INET` cho nhóm IPv4, `INET6` cho nhóm IPv6. Không dựa vào việc IPv6 socket tình cờ hỗ trợ nhóm IPv4 trên một hệ điều hành nhất định.
2. **Tạo DatagramChannel**: `DatagramChannel.open(StandardProtocolFamily.INET)`.
3. **Cấu hình `SO_REUSEADDR` trước bind** nếu nhận multicast trên port chia sẻ. Điều này là khuyến nghị của Javadoc `MulticastChannel`.
4. **Bind socket vào wildcard address và cổng UDP** theo chính sách ứng dụng, ví dụ `new InetSocketAddress(51000)`.
5. **Join địa chỉ nhóm** trên một `NetworkInterface` có thể dùng multicast.
6. **Giữ `MembershipKey`** để quản lý membership: kiểm tra, block/unblock nếu cần, drop khi dừng.
7. **Đóng channel bằng try-with-resources** khi toàn bộ endpoint dừng; close tự làm invalid mọi membership còn tồn tại.

### Vì sao bind wildcard?

Theo Java SE, với multicast receiver nên **bind vào wildcard** (ví dụ IPv4 `0.0.0.0:port`), không nhất thiết vào chính IP nhóm hoặc một local IP cụ thể. Nếu bind channel vào một địa chỉ riêng, việc nhận multicast trên mọi nền tảng là **implementation-specific**.

Cổng trong `bind` phải khớp với **cổng đích datagram** mà bạn muốn nhận. Bind cổng `0` phù hợp thử nghiệm API/vòng đời membership vì OS tự chọn port, nhưng để **nhận từ sender biết trước port cố định**, receiver thường phải bind đúng port của giao thức.

### `SO_REUSEADDR` không phải giấy phép bind mọi cổng

Nếu nhiều chương trình cùng tham gia một group và cùng cổng, khuyến nghị bật `SO_REUSEADDR` **trước bind**. Tuy nhiên hành vi cụ thể còn phụ thuộc hệ điều hành và chính sách cổng; không khẳng định mọi socket luôn chia sẻ port thành công. Không dùng cơ chế này để thay cho cấu hình firewall hoặc phân phối multicast ở hạ tầng.

## 4. MembershipKey lưu những thông tin nào?

Các phương thức hiện hành của `MembershipKey`:

```java
boolean isValid()
void drop()
MulticastChannel channel()
InetAddress group()
NetworkInterface networkInterface()
InetAddress sourceAddress()
MembershipKey block(InetAddress source) throws java.io.IOException
MembershipKey unblock(InetAddress source)
```

Với key nhận được từ `dc.join(group, ni)`:

```java
boolean valid = key.isValid();
boolean sameGroup = key.group().equals(group);
boolean sameInterface = key.networkInterface().equals(ni);
boolean sameChannel = key.channel() == dc;
boolean anySource = key.sourceAddress() == null;
```

Đây là **snippet** giả định có `key`, `group`, `ni` và `dc` hợp lệ từ lần join. Kết quả thông thường sau khi join thành công:

- `valid == true`.
- `sameGroup == true`.
- `sameInterface == true`.
- `sameChannel == true`.
- `anySource == true` vì overload hai tham số tạo membership **không source-specific**.

Với overload ba tham số `dc.join(group, ni, source)`, `sourceAddress()` trả `InetAddress` của nguồn được chọn, không còn `null`.

### Thông tin metadata vẫn đọc được sau khi key invalid

Sau `drop()` hoặc sau khi channel bị đóng, Javadoc vẫn cho phép đọc:

- `key.channel()`: vẫn trả channel tương ứng.
- `key.group()`: vẫn trả group.
- `key.networkInterface()`: vẫn trả interface.
- `key.sourceAddress()`: vẫn trả source hoặc `null`.

Nhưng những giá trị metadata ấy chỉ mô tả **membership cũ**, không chứng minh membership vẫn hoạt động. Muốn biết hiệu lực hiện tại hãy dùng `key.isValid()`.

**Một `MembershipKey` không phải socket:** không có `close()` riêng; `drop()` rời membership, còn `DatagramChannel.close()` giải phóng endpoint UDP.

## 5. Vòng đời chính xác: join → valid → drop/close → invalid

Sơ đồ trạng thái:

```text
DatagramChannel.open(...)
             |
             v
    Channel OPEN / chưa join
             |
             | dc.join(group, ni)
             v
       MembershipKey A
       A.isValid() = true
             |
      +------+----------------------+
      |                             |
      | A.drop()                    | dc.close()
      v                             v
 A.isValid() = false          A.isValid() = false
      |                             |
      | channel có thể vẫn OPEN     | channel CLOSED
      v                             v
 dc.join(group, ni)            không thể join lại
      |                        trên cùng channel
      v
   MembershipKey B
   B.isValid() = true
   A.isValid() = false mãi mãi
```

Các quy tắc:

1. **Ngay sau join thành công**, key là `valid`.
2. **`drop()`** bỏ membership được đại diện bởi key. Khi trở về, key đó **invalid**.
3. **`drop()` trên key đã invalid** không có thêm tác dụng (theo Javadoc); thao tác được thiết kế để có thể gọi trong cleanup.
4. **Key invalid vĩnh viễn**: không có `revalidate()` hoặc `join()` trên chính key cũ. Sau `drop()`, nếu muốn tham gia lại group, gọi `dc.join(...)` và **giữ key mới**.
5. **Đóng channel** làm invalid **mọi membership key** liên kết với channel ấy.
6. **`drop()` không đóng channel**: channel có thể còn hoạt động, gửi/nhận unicast hoặc tham gia group khác.
7. **Đóng channel không tạo ra membership mới**: muốn hoạt động lại sau close, tạo `DatagramChannel` mới rồi bind/join lại.

### Bảng trạng thái

| Thời điểm | `channel.isOpen()` | `key.isValid()` | Có thể dùng key làm membership? |
| --- | --- | --- | --- |
| Trước join | `true` | Chưa có key | Chưa |
| Vừa join thành công | `true` | `true` | Có |
| Đã `key.drop()` | `true` | `false` | Không |
| Join lại, có `newKey` | `true` | Old `false`; new `true` | Chỉ dùng new key |
| Channel bị `close()` | `false` | Mọi key `false` | Không |
| Cố `join` trên channel đã đóng | `false` | Không có key mới | `ClosedChannelException` |

**Đừng suy diễn:** `key.isValid() == true` chỉ nói key chưa bị drop và channel chưa đóng. Nó **không bảo đảm** packet chắc chắn được nhận: multicast có thể bị mạng, firewall hoặc router chặn.

## 6. `drop()` có ngay lập tức ngăn mọi datagram đã gửi không?

Không nhất thiết. Java SE nói rõ: **sau khi drop**, chương trình **vẫn có thể nhận datagram của group** nếu chúng **đã nằm trong receive buffer** của socket. Tương tự, sau khi gọi `block(source)`, một số datagram từ nguồn đó đã vào buffer có thể vẫn được trả về bởi `receive()`.

Hệ quả quan trọng:

- `drop()` thay đổi **quyền tham gia group** cho luồng dữ liệu tiếp theo, không phải lệnh **xóa toàn bộ receive queue**.
- `key.isValid()==false` không có nghĩa buffer đã rỗng.
- Với ứng dụng nhạy cảm, luôn kiểm tra payload/nguồn/phiên/nghiệp vụ của datagram **sau khi nhận**.
- Nếu phải thay profile phân phối dữ liệu ngay lập tức, có thể cân nhắc **đóng channel cũ và tạo channel mới**, đồng thời kiểm soát các hàng đợi ứng dụng, nhưng vẫn cần quy tắc chuyển tiếp và đồng bộ rõ ràng.
- Đừng viết test bắt buộc `receive()` timeout ngay sau `drop()` trong mọi điều kiện mạng. Packet đã queue có thể làm test thất bại dù API chạy đúng.

### `isValid()` có phải công cụ đồng bộ?

Không. Khi nhiều thread cùng giữ key, một thread có thể kiểm tra `isValid()==true` nhưng thread khác gọi `drop()` hoặc `close()` ngay sau đó. Với công cụ xử lý song song, quản lý vòng đời tại một chủ sở hữu hoặc dùng cơ chế đồng bộ phù hợp để tránh *time-of-check/time-of-use race*.

`MembershipKey` không thay thế bộ điều phối lifecycle của dịch vụ hoặc kiểm tra authorization của các gói nhận.

## 7. Chương trình hoàn chỉnh: join, drop, join lại, close

Ví dụ sau **thực sự gọi `DatagramChannel.join`**, đọc metadata, thử drop và join lại, rồi đóng channel. Nó không cần sender hoặc nhận multicast qua mạng; vì thế thử nghiệm tập trung vào **vòng đời `MembershipKey`** chứ không phụ thuộc thời điểm packet đến.

Chương trình cần một interface IPv4 đang **UP** và **quảng bá hỗ trợ multicast**; một số máy ảo, container hoặc mạng doanh nghiệp có thể cấm membership dù interface có vẻ phù hợp. Đó là hạn chế môi trường phải xử lý rõ, không giả định mọi máy đều hỗ trợ.

### 7.1. File `MembershipLifecycleDemo.java`

```java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.util.Collections;

public class MembershipLifecycleDemo {
    static NetworkInterface findIPv4MulticastInterface()
            throws IOException {
        var interfaces = NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) {
            return null;
        }
        for (NetworkInterface ni : Collections.list(interfaces)) {
            if (!ni.isUp() || !ni.supportsMulticast()) {
                continue;
            }
            boolean hasIPv4 = Collections.list(ni.getInetAddresses())
                    .stream()
                    .anyMatch(addr -> addr instanceof Inet4Address);
            if (hasIPv4) {
                return ni;
            }
        }
        return null;
    }

    public static void main(String[] args) throws Exception {
        NetworkInterface ni = findIPv4MulticastInterface();
        if (ni == null) {
            System.out.println("multicast.interfaceAvailable=false");
            return;
        }

        InetAddress group = InetAddress.getByName("239.192.0.77");
        MembershipKey keyOnClose;

        try (DatagramChannel dc =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            // Chọn reuse trước bind; port 0 phù hợp test vòng đời.
            dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            dc.bind(new InetSocketAddress(0));

            MembershipKey first = dc.join(group, ni);
            System.out.println("joined.valid=" + first.isValid());
            System.out.println("joined.group="
                    + first.group().equals(group));
            System.out.println("joined.interface="
                    + first.networkInterface().equals(ni));
            System.out.println("joined.channel="
                    + (first.channel() == dc));
            System.out.println("joined.anySource="
                    + (first.sourceAddress() == null));

            // Cùng group + interface: membership đang có được dùng lại.
            MembershipKey same = dc.join(group, ni);
            System.out.println("duplicate.valid=" + same.isValid());

            // Chỉ rời group; DatagramChannel vẫn mở.
            first.drop();
            System.out.println("afterDrop.valid=" + first.isValid());
            System.out.println("afterDrop.channelOpen=" + dc.isOpen());

            // Join lần nữa sau khi đã drop: tạo membership mới.
            MembershipKey renewed = dc.join(group, ni);
            System.out.println("rejoined.valid=" + renewed.isValid());
            System.out.println("old.staysInvalid=" + !first.isValid());

            // Không drop renewed; để close() tự kết thúc membership.
            keyOnClose = renewed;
        } catch (IOException | UnsupportedOperationException ex) {
            // Multicast phụ thuộc OS/NIC; không thử "vá" bằng API cũ.
            System.out.println("multicast.environmentUnsupported=true");
            return;
        }

        // try-with-resources đã đóng dc.
        System.out.println("afterClose.keyValid="
                + keyOnClose.isValid());
        System.out.println("afterClose.channelOpen="
                + keyOnClose.channel().isOpen());
    }
}
```

### 7.2. Biên dịch và chạy

Đặt đúng tên file `MembershipLifecycleDemo.java`. Dùng JDK 17+:

```bash
javac -encoding UTF-8 MembershipLifecycleDemo.java
java MembershipLifecycleDemo
```

**Stdout khi máy có IPv4 multicast phù hợp và tất cả lần join thành công:**

```text
joined.valid=true
joined.group=true
joined.interface=true
joined.channel=true
joined.anySource=true
duplicate.valid=true
afterDrop.valid=false
afterDrop.channelOpen=true
rejoined.valid=true
old.staysInvalid=true
afterClose.keyValid=false
afterClose.channelOpen=false
```

Chương trình in boolean, **không hard-code tên interface hoặc số cổng OS cấp**, giúp đầu ra thành công tái lập được trên nhiều máy.

**Nhánh môi trường không có interface phù hợp:**

```text
multicast.interfaceAvailable=false
```

Nếu OS/NIC bị từ chối khi mở/bind/join, chương trình có thể in:

```text
multicast.environmentUnsupported=true
```

Tùy thời điểm lỗi, có thể đã có một số dòng thành công trước dòng này; đây là lý do nên phân biệt **lỗi môi trường** và **lỗi logic vòng đời**. Nếu cần chẩn đoán, thay nhánh catch bằng log tên exception và OS/network configuration; không biến mọi lỗi mạng thành báo cáo “đã join thành công”.

### 7.3. Giải thích kết quả

- `joined.valid=true`: token được tạo bởi lần join đầu và vẫn còn hợp lệ.
- `joined.group=true`: key gắn đúng group multicast IPv4 đã chọn.
- `joined.interface=true`: key gắn đúng interface cục bộ dùng để tham gia.
- `joined.channel=true`: key thuộc về đúng `DatagramChannel`.
- `joined.anySource=true`: overload hai tham số nhận datagram từ mọi nguồn trong phạm vi OS filtering.
- `duplicate.valid=true`: gọi `join(group, ni)` lần nữa khi membership còn tồn tại trả lại membership đã có. **Không phải mỗi lời gọi đều tạo một lần gia nhập OS độc lập**.
- `afterDrop.valid=false` nhưng `afterDrop.channelOpen=true`: rời group không đồng nghĩa đóng endpoint.
- `rejoined.valid=true`: gọi `join` lại sau drop được key đang hoạt động.
- `old.staysInvalid=true`: key đã drop không tự “sống lại” dù cùng group/interface được tham gia lần nữa.
- `afterClose.keyValid=false` và `afterClose.channelOpen=false`: đóng channel làm vô hiệu hóa những membership chưa drop.

**Điểm thực hành:** trong một service, giữ cả `DatagramChannel` và các `MembershipKey` hiện hành theo group/interface/source. Khi có nhu cầu đổi nhóm, drop **đúng key** rồi cập nhật registry; không cất key invalid để dùng lại.

## 8. Tham gia từ mọi nguồn (ASM) và tham gia từ một nguồn (SSM)

Java NIO phân biệt hai kiểu membership:

| Kiểu | Lời gọi | `sourceAddress()` | Ý nghĩa |
| --- | --- | --- | --- |
| Any-Source Multicast (**ASM**) | `dc.join(group, ni)` | `null` | Nhận datagram gửi tới group từ **mọi địa chỉ nguồn** được mạng chuyển đến |
| Source-Specific Multicast (**SSM**) | `dc.join(group, ni, source)` | `source` đã cho | Chỉ tham gia nhận datagram từ **một địa chỉ nguồn unicast** |
| ASM + block nguồn | `asmKey.block(source)` | Vẫn `null` | Chặn một nguồn cụ thể, nếu OS hỗ trợ source filtering |

**ASM không bắt buộc bật block/unblock.** Chỉ `join(group, ni)` là đủ để tạo membership không source-specific; việc có nhận được gói hay không phụ thuộc mạng.

**SSM không có nghĩa tự xác thực nguồn bằng mật mã.** Source IP ở tầng mạng có thể bị giả mạo trong một số môi trường, và membership không xác minh danh tính ứng dụng hoặc chữ ký dữ liệu. Nếu giao thức cần bảo đảm nguồn, phải dùng kiểm tra ứng dụng/mật mã phù hợp.

### 8.1. SSM: `join(group, ni, source)`

Khai báo một source IPv4 unicast rõ ràng:

```java
InetAddress group = InetAddress.getByName("239.192.0.77");
InetAddress source = InetAddress.getByName("192.0.2.10");
MembershipKey sourceKey = dc.join(group, ni, source);

boolean onlyOneSource = sourceKey.sourceAddress().equals(source);
```

Đây là snippet: `dc` và `ni` phải đã được tạo đúng kiểu, và OS phải **hỗ trợ source-specific multicast**. `192.0.2.10` là địa chỉ tài liệu TEST-NET, dùng để minh họa API, **không phải một nguồn hoạt động công khai mà chương trình sẽ nhận packet**. Khi triển khai thật, thay bằng IP unicast của sender thực tế.

Javadoc quy định:

- Source phải là **unicast address**, không được là multicast group address.
- Source và group phải cùng address family (IPv4 với IPv4, IPv6 với IPv6).
- Nếu đã có source-specific membership cho đúng group/interface/source, join tương ứng có thể trả key của membership đó.
- Có thể thêm **các source khác** trên cùng group/interface bằng những lần `join(group, ni, anotherSource)`; membership có tính **cộng dồn** cho các nguồn được chọn.
- `drop()` của một key source-specific chỉ bỏ membership cho **nguồn đó**.
- Nếu hệ điều hành không hỗ trợ source filtering, lời gọi SSM có thể ném `UnsupportedOperationException`.

### 8.2. Không trộn ASM và SSM trên cùng group/interface của một channel

Javadoc `MulticastChannel` không cho phép dùng cả hai kiểu membership **đồng thời trên cùng group và interface** của một channel.

- Đã có `dc.join(group, ni)` → gọi `dc.join(group, ni, source)` sẽ gặp `IllegalStateException`.
- Đã có SSM cho cùng group/interface → gọi `dc.join(group, ni)` sẽ gặp `IllegalStateException`.
- Nếu muốn chuyển chế độ, hãy **drop các membership xung đột** trước rồi join theo chế độ mới; không giả định chỉ gọi overload khác là tự chuyển mode.

**Không suy rộng** rằng group khác hoặc interface khác trên cùng channel luôn bị cấm. Channel có thể tham gia **nhiều group** và thậm chí cùng group trên **nhiều interface** nếu hệ thống hỗ trợ.

## 9. `block(source)` và `unblock(source)`: lọc nguồn trên ASM

Với key từ `join(group, ni)`, nếu OS có source filtering:

```java
InetAddress source = InetAddress.getByName("192.0.2.10");
asmKey.block(source);
asmKey.unblock(source);
```

Đây là snippet, với `asmKey` là key ASM còn valid. Khi muốn lọc nguồn không nên giả định mọi platform hỗ trợ.

**`block(source)`:**

- Trả lại chính `MembershipKey` nếu thành công.
- Chặn datagram từ nguồn IPv4/IPv6 phù hợp với family của group.
- Nếu nguồn **đã block**, gọi lại không có thêm tác dụng.
- Nếu key là **source-specific** hoặc đã invalid, ném `IllegalStateException`.
- Nếu OS không hỗ trợ source filtering, ném `UnsupportedOperationException`.
- Nếu source không phải unicast hoặc khác family, ném `IllegalArgumentException`.
- Có thể ném `IOException` vì lỗi hệ thống; **không** kết luận chặn đã thành công khi exception xảy ra.

**`unblock(source)`:**

- Chỉ sử dụng cho nguồn **đã bị block** trên membership đó.
- Nếu nguồn chưa bị block, hoặc key đã invalid, ném `IllegalStateException`.
- Trả chính key khi thành công.
- Không đồng nghĩa “cho phép toàn bộ nguồn mọi nơi”: nó chỉ hủy một quy tắc block cụ thể của membership.

### Lọc nguồn không xóa datagram đã nằm trong buffer

Sau `block(source)`, OS có thể vẫn cung cấp một số datagram **đã xếp hàng trước thao tác**. Vì vậy đừng sử dụng `block` làm thay thế cho cơ chế xác thực dữ liệu hoặc xóa trạng thái nhận của ứng dụng.

### Khác nhau về khả năng xử lý

| Tình huống | API phù hợp | Lưu ý |
| --- | --- | --- |
| Chấp nhận tất cả nguồn | `join(group, ni)` | ASM |
| Chỉ chấp nhận một nguồn | `join(group, ni, source)` | SSM, cần OS hỗ trợ |
| ASM nhưng muốn loại một nguồn | `asmKey.block(source)` | Cần source filtering |
| Bỏ loại một nguồn đã block | `asmKey.unblock(source)` | Không dùng khi chưa từng block |
| Rời group hoàn toàn ở key ASM | `asmKey.drop()` | Không đóng channel |
| Rời membership của một source SSM | `sourceKey.drop()` | Không nhất thiết drop các source SSM khác |
| Dừng mọi membership của channel | `channel.close()` | Mọi key tương ứng invalid |

## 10. Ví dụ source filtering với xử lý điều kiện nền tảng

Ví dụ sau minh họa **thao tác ASM block/unblock** và **thử tham gia SSM** trên một channel **khác** để không xung đột kiểu membership. Nó có các nhánh báo rằng tính năng phụ thuộc OS, thay vì hứa hẹn mọi máy sẽ cho kết quả giống nhau.

Tệp `MembershipFilteringDemo.java`:

```java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.util.Collections;

public class MembershipFilteringDemo {
    static NetworkInterface findInterface() throws IOException {
        var interfaces = NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) {
            return null;
        }
        for (NetworkInterface ni : Collections.list(interfaces)) {
            if (ni.isUp() && ni.supportsMulticast()
                    && Collections.list(ni.getInetAddresses()).stream()
                        .anyMatch(ip -> ip instanceof Inet4Address)) {
                return ni;
            }
        }
        return null;
    }

    static DatagramChannel newReceiver() throws IOException {
        DatagramChannel dc =
                DatagramChannel.open(StandardProtocolFamily.INET);
        try {
            dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            dc.bind(new InetSocketAddress(0));
            return dc;
        } catch (IOException | RuntimeException ex) {
            dc.close();
            throw ex;
        }
    }

    public static void main(String[] args) throws Exception {
        NetworkInterface ni = findInterface();
        if (ni == null) {
            System.out.println("multicast.interfaceAvailable=false");
            return;
        }

        InetAddress group = InetAddress.getByName("239.192.0.77");
        // TEST-NET chỉ minh họa cú pháp source; không phải sender thật.
        InetAddress source = InetAddress.getByName("192.0.2.10");

        try (DatagramChannel asm = newReceiver()) {
            MembershipKey allSources = asm.join(group, ni);
            System.out.println("asm.sourceIsNull="
                    + (allSources.sourceAddress() == null));

            try {
                allSources.block(source);
                allSources.unblock(source);
                System.out.println("asm.blockRoundTrip=true");
            } catch (UnsupportedOperationException ex) {
                System.out.println("asm.filterSupported=false");
            } finally {
                allSources.drop();
            }
        } catch (IOException | UnsupportedOperationException ex) {
            System.out.println("asm.joinUnavailable=true");
        }

        // Channel khác: không trộn kiểu membership ASM/SSM
        // trên cùng group+interface của cùng channel.
        try (DatagramChannel ssm = newReceiver()) {
            MembershipKey oneSource = ssm.join(group, ni, source);
            try {
                System.out.println("ssm.sourceMatches="
                        + source.equals(oneSource.sourceAddress()));
            } finally {
                oneSource.drop();
            }
        } catch (IOException | UnsupportedOperationException ex) {
            System.out.println("ssm.unavailable=true");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MembershipFilteringDemo.java
java MembershipFilteringDemo
```

Nếu OS/NIC hỗ trợ multicast và source filtering cho cả hai kiểu, stdout mong đợi:

```text
asm.sourceIsNull=true
asm.blockRoundTrip=true
ssm.sourceMatches=true
```

Nếu source filtering không được hỗ trợ, một output hợp lệ có thể là:

```text
asm.sourceIsNull=true
asm.filterSupported=false
ssm.unavailable=true
```

Đây là **hai tình huống điều kiện**, không phải hai bộ output cam kết cho mọi OS. Một hệ thống có thể hỗ trợ block ASM nhưng không hỗ trợ SSM hoặc ngược lại; có thể lỗi join ban đầu và đi theo nhánh `asm.joinUnavailable`; có thể không có interface phù hợp.

**Về xử lý lỗi:** Chương trình bắt các ngoại lệ **phụ thuộc nền tảng** mà mục tiêu học tập cần minh họa. Nếu `block` hoặc `unblock` gặp `IOException`, ngoại lệ sẽ đi ra ngoài `main` (vẫn được cleanup), giúp phân biệt **lỗi I/O** với tính năng **không hỗ trợ**. Trong sản phẩm thật, ghi log chi tiết và kiểm soát retry/backoff theo chính sách.

## 11. Chọn NetworkInterface đúng cách

`NetworkInterface` không chỉ là một chuỗi tên. Nó đại diện cho một card mạng/virtual interface cụ thể của hệ điều hành.

Các cách tìm:

```java
NetworkInterface ni = NetworkInterface.getByName("eth0");
```

Hoặc khi biết địa chỉ local:

```java
NetworkInterface ni = NetworkInterface.getByInetAddress(
        InetAddress.getByName("192.168.1.20"));
```

Hai snippet giả định tên/IP thực sự tồn tại trên máy. Các lời gọi có thể trả `null`; không viết chương trình sản xuất chỉ dùng tên `"eth0"` vì Windows hoặc container thường có tên khác.

Các kiểm tra hữu ích:

```java
boolean up = ni.isUp();
boolean supports = ni.supportsMulticast();
boolean hasIpv4 = Collections.list(ni.getInetAddresses()).stream()
        .anyMatch(a -> a instanceof Inet4Address);
```

Đây là snippet với `ni` đã kiểm tra khác null và các import `java.net.*`, `java.util.Collections`. `isUp()`/`supportsMulticast()` có thể cần xử lý `SocketException` (subtype `IOException`).

**Không đánh đồng:**

- Interface tồn tại ≠ interface đang UP.
- `supportsMulticast() == true` ≠ router, firewall hay OS chắc chắn cho join hoặc phân phối gói.
- Interface dùng `join` để **nhận** ≠ interface do `IP_MULTICAST_IF` chọn để **gửi**.
- Loopback IPv4 có tồn tại ≠ mọi hệ điều hành cho nhận multicast trên loopback.
- Chọn một interface ở máy có nhiều card mạng ≠ mọi receiver tự động tham gia tất cả card mạng.

Nếu dịch vụ chạy nhiều NIC, nên có cấu hình rõ và giữ các `MembershipKey` tương ứng theo từng `NetworkInterface`. Một số nơi cần join cùng group nhiều lần trên các interface khác nhau. Đó là các membership phân biệt, và phải drop đúng key của từng interface.

## 12. `IP_MULTICAST_IF`, TTL và multicast loopback

Ba option quan trọng trong `StandardSocketOptions`:

| Option | Ý nghĩa | Liên quan membership thế nào? |
| --- | --- | --- |
| `IP_MULTICAST_IF` | Chọn interface dùng khi **gửi multicast đi** | Không tự join group nhận |
| `IP_MULTICAST_TTL` | Giới hạn số hop multicast IPv4; phụ thuộc ngữ cảnh IPv6 | Không quyết định key valid hay invalid |
| `IP_MULTICAST_LOOP` | Điều khiển multicast loopback về các listener trên máy gửi nếu platform hỗ trợ | Ảnh hưởng test gửi/nhận nội bộ, không thay `join` |

Ví dụ channel gửi đến group:

```java
DatagramChannel sender =
        DatagramChannel.open(StandardProtocolFamily.INET);

try (sender) {
    sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
    sender.send(ByteBuffer.wrap(bytes),
            new InetSocketAddress(group, 51000));
}
```

Đây là snippet cần `ni`/`group` và import `java.net.*`, `java.nio.ByteBuffer`, `java.nio.charset.StandardCharsets` cùng `java.nio.channels.DatagramChannel`. Nó minh họa **gửi multicast**. Sender **không cần join group** chỉ để gửi. Không được suy ra từ việc `send` trả về rằng một receiver đã nhận; UDP vẫn không bảo đảm delivery.

Đối với receiver thực tế:

```java
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    receiver.bind(new InetSocketAddress(51000));
    MembershipKey key = receiver.join(group, ni);
    // receive(ByteBuffer) sẽ block nếu không cấu hình nonblocking.
    // Đọc packet và xử lý theo giao thức.
    key.drop();
}
```

Đây là snippet, không phải chương trình hoàn chỉnh. `DatagramChannel.receive(...)` dùng `ByteBuffer` và có cách điều khiển blocking/nonblocking khác với `DatagramSocket.receive(DatagramPacket)`. Không dùng cách nhận của một API vào API khác mà chưa chuyển đổi đúng.

### Chọn TTL có chủ đích

TTL nhỏ có thể giới hạn phạm vi multicast, nhưng không thay ranh giới tin cậy. Router/network policies có thể cấm forwarding multicast dù TTL cho phép. Trong test cùng máy, `IP_MULTICAST_LOOP` cũng có thể phụ thuộc OS, nên tránh coi việc loopback xảy ra là một phần được cam kết của ví dụ lifecycle.

## 13. Vòng đời trong ứng dụng có nhiều nhóm/nguồn

Một dịch vụ có thể tham gia:

```text
DatagramChannel dc
   |
   +-- MembershipKey K1: group G1, NIC A, any-source
   |
   +-- MembershipKey K2: group G2, NIC A, source S1
   |
   +-- MembershipKey K3: group G2, NIC A, source S2
   |
   +-- MembershipKey K4: group G1, NIC B, any-source
```

Sơ đồ là trường hợp hợp lệ về **mô hình membership** nếu hệ thống hỗ trợ những group/interface/source đó.

- Drop `K1` không tự drop `K2`, `K3` hoặc `K4`.
- Drop `K2` không ngắt membership source `S2` của `K3`.
- Cùng group nhưng **khác interface** là các membership riêng.
- `close()` trên `dc` làm invalid toàn bộ `K1..K4`.
- Một key invalid không thể được dùng như key hiện tại dù registry còn giữ object.
- Tham gia lại cùng group sau drop trả một **membership key mới**; cập nhật registry cho đúng.

### Gợi ý thiết kế registry

Một ứng dụng nhiều nhóm có thể giữ một map theo bộ khóa logic:

```text
MembershipId = (group IP, interface identity, source IP hoặc ANY)
MembershipEntry = (DatagramChannel, MembershipKey, policy/profile)
```

Khi nhận lệnh thay đổi cấu hình:

1. Xác định group/interface/source đích.
2. Nếu có key hợp lệ tương ứng, áp dụng chính sách idempotent của ứng dụng.
3. Nếu cần thay chế độ ASM ↔ SSM, drop các membership xung đột **trước** khi join chế độ mới.
4. Gọi `join` và chỉ lưu key mới nếu lời gọi thành công.
5. Khi dừng service, drop những key còn valid nếu cần cleanup theo từng group rồi đóng channel bằng try-with-resources/lifecycle manager.
6. Ngăn các thread khác gọi lại `block`/`unblock`/`join` vào channel đang đóng; dùng cơ chế điều phối/synchronization phù hợp.

**Lưu ý hiệu lực ở mức OS:** có thể nhiều socket khác của cùng host cũng đăng ký group đó. Drop một key chỉ quản lý membership của channel tương ứng; không coi đó là lệnh xóa group khỏi toàn mạng hay ngắt ứng dụng khác.

## 14. Cách dừng receiver và tài nguyên an toàn

`MembershipKey.drop()` và `DatagramChannel.close()` giải quyết hai mức khác nhau:

- **Drop một membership:** bỏ tham gia một nhóm/nguồn trên một channel còn sống.
- **Close channel:** đóng endpoint UDP, làm mất hiệu lực mọi membership trên channel và kết thúc khả năng I/O của channel đó.

Với lifecycle server:

```text
SERVICE START
  |
  v
open DatagramChannel
  |
  v
configure options -> bind
  |
  v
join required groups -> save MembershipKeys
  |
  v
RECEIVE / PROCESS (theo policy ứng dụng)
  |
  +-- reconfigure one group --> drop key cũ --> join key mới
  |
  v
SERVICE STOP
  |
  +-- stop/coordinate workers
  +-- optionally drop memberships còn valid
  +-- close DatagramChannel
  |
  v
ALL KEYS INVALID, ENDPOINT CLOSED
```

Không phụ thuộc garbage collector để giải phóng socket. Dùng **try-with-resources**, `close()` hoặc lifecycle manager rõ ràng.

### Nếu thread đang chờ `receive()`

Đóng channel có thể khiến hoạt động I/O đang bị chặn kết thúc bằng ngoại lệ liên quan channel close, ví dụ `AsynchronousCloseException` tùy thời điểm. Đừng dựa vào `drop()` như một công cụ chắc chắn đánh thức một thread đang block trong `receive`; membership đã drop nhưng channel vẫn mở và có thể không còn datagram mới tới.

Nếu cần dừng receive loop có kiểm soát, có thể dùng:

- `DatagramChannel.configureBlocking(false)` kết hợp `Selector`.
- Đóng channel từ thread điều phối.
- Cơ chế “wakeup”/control channel hoặc cờ dừng theo kiến trúc.

Nếu đang dùng `Selector`, nhớ rằng `SelectionKey` phục vụ **đăng ký sự kiện I/O**, **khác hoàn toàn `MembershipKey`**. Hủy `SelectionKey` không tương đương rời multicast group; đóng channel mới làm key membership mất hiệu lực.

### Sau drop, có cần đóng channel ngay?

Không bắt buộc. Có thể dùng channel cho group khác, nhận datagram unicast hoặc gửi datagram. Tuy nhiên, nếu service đã thực sự kết thúc, đóng channel để giải phóng OS resources. **Không giữ channel mở vô hạn chỉ vì key đã invalid.**

## 15. Ngoại lệ thường gặp và cách chẩn đoán

| Thao tác | Lỗi/tình huống | Kết quả thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| `join(nonMulticastAddress, ni)` | `group` không phải multicast | `IllegalArgumentException` | Kiểm tra `group.isMulticastAddress()` |
| `join(groupIPv6, ni)` trên IPv4 channel | Sai protocol family | `IllegalArgumentException` hoặc giới hạn platform phù hợp | Mở `DatagramChannel.open(INET6)` cho nhóm IPv6 |
| `join(group, ni)` trên channel đã close | Channel đóng | `ClosedChannelException` | Tạo channel mới, bind/join lại |
| `join(group, ni)` khi platform không hỗ trợ multicast | Socket/OS không hỗ trợ | `UnsupportedOperationException` | Kiểm tra NIC, OS và chính sách triển khai |
| `join(group, ni)` và xảy ra lỗi OS | Không join được nhóm/giao diện | `IOException` | Log nguyên nhân, interface, group và runtime |
| `join(group, ni, source)` khi không hỗ trợ source filtering | SSM không có trong OS | `UnsupportedOperationException` | Không tự coi là SSM; xem xét chính sách fallback |
| `join(group, ni, source)` với source multicast hoặc khác family | Source không hợp lệ | `IllegalArgumentException` | Source phải là unicast, cùng IPv4/IPv6 family |
| Trộn ASM/SSM trên cùng group/interface | Hai chế độ membership xung đột | `IllegalStateException` | Drop key xung đột trước, chuyển mode có chủ đích |
| `block(source)` trên SSM key | `block` không dùng cho key source-specific | `IllegalStateException` | Dùng đúng overload join hoặc key ASM |
| `block(source)` khi key invalid | Key đã drop/channel close | `IllegalStateException` | Không tái sử dụng key cũ |
| `block(source)` và OS không có source filtering | Thiếu hỗ trợ filter | `UnsupportedOperationException` | Đổi cấu hình/policy; không âm thầm bỏ filter |
| `unblock(source)` khi chưa block | Source không nằm trong tập bị chặn | `IllegalStateException` | Chỉ unblock nguồn đã block thành công |
| `unblock(source)` trên key invalid | Key không còn hiệu lực | `IllegalStateException` | Rejoin và tạo key mới |
| `drop()` khi key đã invalid | Membership đã rời nhóm | Không có tác dụng bổ sung | An toàn cho cleanup idempotent |
| `receive` vẫn thấy gói sau `drop` | Datagram đã nằm trong receive buffer | Có thể xảy ra | Kiểm tra tầng ứng dụng, không đòi queue rỗng tức thì |
| `SO_REUSEADDR` bật nhưng không bind được | Chính sách OS/port conflict | `IOException` | Kiểm tra bind address/port, các socket khác |
| Không thấy gói dù `isValid()==true` | Firewall, router, IGMP/MLD, NIC, TTL, source filter | Không nhất thiết có exception | Chẩn đoán mạng thực tế, đừng đồng nhất với key invalid |

**Chẩn đoán lỗi:** nên ghi group IP, interface name/ID, local UDP port, membership mode, source nếu có, trạng thái channel/key và loại exception. Không log payload nhạy cảm hoặc bí mật nghiệp vụ chỉ để xác định lý do join thất bại.

### Không dùng source filtering như authentication

SSM/ASM source filtering dựa vào thông tin **địa chỉ nguồn ở tầng mạng**. Đây không phải kiểm chứng danh tính mật mã; không dùng `sourceAddress()`, `block` hoặc `unblock` thay chữ ký số, token, mã xác thực hay kiểm tra quyền nghiệp vụ.

## 16. Kiểm thử: điều gì nên và không nên hard-code?

### Những kiểm tra có ý nghĩa ổn định

Sau khi **join thành công**:

```java
assert key.isValid();
assert key.group().equals(group);
assert key.networkInterface().equals(ni);
assert key.channel() == dc;
assert key.sourceAddress() == null; // ASM
```

Đây là các **assert statements** minh họa với biến đã tạo trong test và cơ chế bật assertion (`-ea`) nếu chạy bằng chương trình `java`.

Sau `drop`:

```java
key.drop();
assert !key.isValid();
assert dc.isOpen();
```

Sau `close`:

```java
dc.close();
assert !newestKey.isValid();
assert !dc.isOpen();
```

Đây là snippet với `newestKey` hiện vẫn valid trước khi channel close.

### Những điều không ổn định

**Không** viết test phụ thuộc vào:

- Tên network interface như `eth0`, `Ethernet 2`, `en0`.
- Cổng ephemeral mà OS chọn ở `bind(0)`.
- Thời điểm multicast datagram được nhận sau join.
- Việc OS/router luôn cho phép multicast trên loopback.
- Khả năng source filtering của mọi kernel/network stack.
- Packet queue chắc chắn rỗng ngay sau drop/block.
- Mọi môi trường container/CI đều có route multicast.
- TTL/loopback khiến datagram chắc chắn đến mọi receiver trong hệ thống.

### Cách kiểm thử đề nghị

1. **Test logic thuần:** kiểm tra chính sách group/interface/source, registry, trạng thái ứng dụng mà không giả lập OS multicast quá mức.
2. **Integration test có điều kiện:** chạy `MembershipLifecycleDemo` trên máy hỗ trợ IPv4 multicast và xem các trạng thái valid/invalid.
3. **Integration test source-filtering riêng:** chạy `MembershipFilteringDemo` nếu OS có IGMPv3/MLDv2 support và mạng phù hợp.
4. **E2E network test:** cấu hình sender/receiver thực, giám sát route/firewall/port/TTL, xác thực datagram thực nhận, ghi điều kiện test.
5. **Cleanup test:** drop và close, xác nhận key invalid và channel closed, không phụ thuộc thời gian GC.

## 17. Bài tập có đáp án

**Bài 1.** `MembershipKey` được tạo từ đâu?

**Đáp án:** Từ `MulticastChannel.join(...)`, được `DatagramChannel` triển khai. Không gọi `new MembershipKey()` trong code ứng dụng thông thường.

**Bài 2.** Một key ASM vừa được tạo; `isValid()` bằng gì?

**Đáp án:** `true` sau khi join thành công, cho đến khi drop hoặc channel đóng.

**Bài 3.** `key.drop()` có đóng `DatagramChannel` không?

**Đáp án:** Không. Nó chỉ bỏ membership đại diện bởi key. `dc.isOpen()` vẫn là `true` nếu channel chưa bị đóng vì lý do khác.

**Bài 4.** Sau `drop()` rồi `join` lại cùng group/interface, key cũ có trở thành valid?

**Đáp án:** Không. Key cũ invalid vĩnh viễn; lần join sau tạo một membership key mới.

**Bài 5.** `channel.close()` ảnh hưởng gì đến các membership keys của channel?

**Đáp án:** Tất cả key còn thuộc channel sẽ invalid. Không thể dùng channel đã đóng để join lại.

**Bài 6.** `key.sourceAddress()==null` biểu diễn điều gì?

**Đáp án:** Membership là **any-source** (nhận từ mọi nguồn theo điều kiện mạng), không phải source-specific.

**Bài 7.** Muốn nhận chỉ từ IP `192.0.2.10`, nên dùng overload nào?

**Đáp án:** `dc.join(group, ni, source)` với `source` là địa chỉ **unicast** cùng IPv4/IPv6 family, khi OS hỗ trợ source filtering. Địa chỉ TEST-NET trong bài chỉ minh họa, không phải sender thật.

**Bài 8.** Đã tham gia SSM cho group/interface, có được join ASM cùng group/interface ngay không?

**Đáp án:** Không. `join(group, ni)` sẽ ném `IllegalStateException` khi vẫn có source-specific membership xung đột; muốn đổi phải drop membership cũ rồi join lại theo mode mới.

**Bài 9.** `block(source)` có dùng trên key SSM được không?

**Đáp án:** Không. `block` chỉ dùng cho ASM key hợp lệ khi OS hỗ trợ source filtering; với SSM key ném `IllegalStateException`.

**Bài 10.** `unblock(source)` cho nguồn chưa từng bị block sẽ ra sao?

**Đáp án:** Ném `IllegalStateException`. Chỉ dùng sau khi `block(source)` thành công.

**Bài 11.** `key.isValid()==true` có đảm bảo một datagram từ sender sẽ được nhận không?

**Đáp án:** Không. Nó chỉ nói membership chưa bị drop/close; việc phân phối datagram phụ thuộc network, OS, IGMP/MLD, firewall và routing.

**Bài 12.** Vì sao đôi khi vẫn nhận datagram sau `drop`?

**Đáp án:** Vì một số datagram có thể đã được đưa vào receive buffer trước khi thao tác drop, nên vẫn được đọc ra.

**Bài 13.** Một channel đã join hai group khác nhau; drop key của group A có tự rời group B không?

**Đáp án:** Không. Các membership độc lập; key tương ứng group B vẫn valid nếu channel còn mở và chưa drop B.

**Bài 14.** `IP_MULTICAST_IF` có tự tạo membership để nhận group không?

**Đáp án:** Không. Nó chọn interface gửi multicast. Muốn nhận phải `join(group, ni)` và bind endpoint phù hợp.

**Bài 15.** Khi muốn receiver trên nhiều NIC cùng nhận một group, cần làm gì?

**Đáp án:** Tham gia group trên từng `NetworkInterface` phù hợp bằng các lần `join`, giữ key riêng và quản lý drop/close theo thiết kế. Không thể coi một lần join trên NIC A là tự động join tất cả NIC khác.

**Bài 16.** Có thể dùng key để nhận biết cả UDP port hay không?

**Đáp án:** Không trực tiếp. `MembershipKey` lưu group, interface, channel và source (nếu có); UDP port là trạng thái bind của channel/socket.

**Bài 17.** Mỗi lần gọi `join(group, ni)` khi membership đã có sẽ tạo thêm một membership độc lập?

**Đáp án:** Không. Theo Javadoc, join lại cùng group/interface khi any-source membership đang tồn tại sẽ trả key đại diện membership hiện có.

**Bài 18.** Vì sao key valid nhưng không nên tin packet đến từ một danh tính đã xác thực?

**Đáp án:** Membership/filter dựa trên tầng IP, không tạo bằng chứng danh tính ứng dụng hay chữ ký dữ liệu. Phải áp dụng kiểm tra bảo mật tầng ứng dụng riêng.

### Checklist trước khi dùng trong sản phẩm

- [ ] Tôi biết `MembershipKey` được trả bởi `DatagramChannel.join`.
- [ ] Tôi biết `isValid`, `drop` và `close` ảnh hưởng membership khác nhau thế nào.
- [ ] Tôi không tái sử dụng key đã invalid sau rejoin.
- [ ] Tôi hiểu group IP, interface và local UDP port là các thành phần độc lập.
- [ ] Tôi chọn đúng `StandardProtocolFamily.INET`/`INET6`.
- [ ] Tôi bật `SO_REUSEADDR` trước bind khi có nhu cầu chia sẻ port.
- [ ] Tôi phân biệt key ASM/SSM qua `sourceAddress()`.
- [ ] Tôi không trộn ASM và SSM trên cùng group/interface của một channel.
- [ ] Tôi chỉ gọi `block`/`unblock` cho key ASM còn valid, với nguồn hợp lệ và OS hỗ trợ.
- [ ] Tôi biết drop/block không đảm bảo xóa ngay datagram đã queued.
- [ ] Tôi không nhầm `IP_MULTICAST_IF` với tham số interface của join.
- [ ] Tôi không dùng multicast membership như cơ chế xác thực người gửi.
- [ ] Tôi có lifecycle manager để drop key khi cấu hình đổi và close channel khi service dừng.
- [ ] Tôi không hard-code tên interface hoặc nhận định OS luôn hỗ trợ multicast.
- [ ] Tôi chạy ví dụ trên JDK 17+ và giải thích các nhánh phụ thuộc platform.

## 18. Tài liệu chính thức, còn được hỗ trợ

1. [Oracle Java SE 25 — `MembershipKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/MembershipKey.html): `isValid`, `drop`, `block`, `unblock`, `channel`, `group`, `networkInterface`, `sourceAddress`.
2. [Oracle Java SE 25 — `MulticastChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/MulticastChannel.html): hai overload `join`, ASM/SSM, giới hạn tương thích, tùy chọn `SO_REUSEADDR` và tác dụng `close`.
3. [Oracle Java SE 25 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): `open`, `bind`, `receive`, `send`, `close`, socket options.
4. [Oracle Java SE 25 — `NetworkInterface`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/NetworkInterface.html): `getNetworkInterfaces`, `isUp`, `supportsMulticast`, `getInetAddresses`.
5. [Oracle Java SE 25 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_REUSEADDR`, `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`.
6. [RFC 1112 — Host Extensions for IP Multicasting](https://www.rfc-editor.org/rfc/rfc1112): mô hình IP multicast cơ bản.
7. [RFC 3376 — IGMPv3](https://www.rfc-editor.org/rfc/rfc3376) và [RFC 3810 — MLDv2](https://www.rfc-editor.org/rfc/rfc3810): cơ chế membership/source filtering ở các hạ tầng tương ứng.

**Tổng kết:** `MembershipKey` là **token cho membership multicast của một channel trên một group/interface**, có thể gắn thêm source. `join(...)` tạo hoặc trả membership đang có; `isValid()` cho biết key còn hiệu lực; `drop()` chỉ rời membership đó, còn `DatagramChannel.close()` làm invalid mọi membership của channel. Muốn tham gia lại sau drop phải `join` lấy key mới. Với nguồn cụ thể, dùng overload SSM hoặc `block/unblock` trên key ASM khi OS hỗ trợ; không coi trạng thái key là bảo đảm datagram đến nơi hoặc được xác thực.