# Socket và multicast trong Java: Tra cứu khả năng hỗ trợ qua supportedOptions()

## 1. Mục tiêu và tình huống thực tế

Một dịch vụ Java cần chạy được trên Windows, Linux và nhiều môi trường container. Nó có các luồng kết nối TCP và một thành phần nhận/gửi UDP multicast. Lập trình viên muốn:

- Bật `TCP_NODELAY` cho kết nối TCP khi socket hỗ trợ.
- Cấu hình `SO_RCVBUF` để giảm nguy cơ quá tải khi có nhiều gói UDP.
- Đặt `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP` hoặc `IP_MULTICAST_IF` khi sử dụng multicast.
- Xem xét `SO_REUSEPORT` nhưng **không** mặc định mọi hệ điều hành/JDK hỗ trợ.
- Tránh dùng tùy chọn của TCP cho UDP, hoặc ngược lại.
- Không coi việc API có tên `setOption` là chứng minh mọi `SocketOption` đều hợp lệ.

Để khám phá **những tùy chọn socket mà đối tượng mạng hiện tại hỗ trợ**, Java NIO.2 cung cấp:

```java
Set<SocketOption<?>> options = channel.supportedOptions();
```

Đây là **mã minh họa**, `channel` phải là một `NetworkChannel` đã được tạo, và cần import `java.net.SocketOption`, `java.util.Set`. Trên Java 9+, các lớp `Socket`, `ServerSocket` và `DatagramSocket` thuộc `java.net` cũng có phương thức `supportedOptions()` trực tiếp.

**Ý chính:** `supportedOptions()` trả về tập **khả năng được công bố cho chính socket/channel đó**. Tập này có thể phụ thuộc kiểu socket, provider, hệ điều hành và phiên bản JDK. Nó không phải danh sách “các option Java tồn tại”, không phải kết quả kiểm tra quyền mạng thực tế, và **không** bảo đảm mọi giá trị truyền cho `setOption` sẽ được chấp nhận hoặc có hiệu ứng đo được.

Bài sẽ làm rõ cách tra cứu, mô hình kiểu của `SocketOption<T>`, phân biệt TCP/UDP/multicast, kiểm tra trước khi cấu hình, phản ứng với lỗi, và thử nghiệm Java 17 thực tế **không cần gửi gói tin ra mạng**.

Các API `NetworkChannel`, `SocketOption` và `StandardSocketOptions` có từ **Java 7** và hiện vẫn được sử dụng. Phần mở rộng cho `java.net.Socket/ServerSocket/DatagramSocket.supportedOptions()` có từ **Java 9**. Ví dụ độc lập trong bài biên dịch với `--release 17`.

## 2. `NetworkChannel` và hợp đồng `supportedOptions()`

`NetworkChannel` thuộc package `java.nio.channels`, đại diện cho channel gắn với network socket. Nó khai báo những phương thức:

| Phương thức | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `supportedOptions()` | Trả `Set<SocketOption<?>>` mà channel hỗ trợ | Tra cứu năng lực, không gửi gói hoặc bind |
| `getOption(SocketOption<T>)` | Đọc giá trị hiện tại của một option | Cần đúng option; có thể lỗi nếu không hỗ trợ hoặc channel đóng |
| `setOption(SocketOption<T>,T)` | Yêu cầu cấu hình option | Type-safe theo `T`; vẫn phải xử lý giá trị không hợp lệ/I/O |
| `bind(SocketAddress)` | Bind local address | Có thể cần đặt một số option **trước bind** |
| `getLocalAddress()` | Đọc địa chỉ đã bind | Không phải phép tra cứu option |
| `close()`, `isOpen()` | Quản lý vòng đời channel | `supportedOptions()` vẫn được quy định trả tập sau khi channel đã đóng |

Những implementation chính của `NetworkChannel`:

- `SocketChannel`: TCP client/server-side connected stream channel.
- `ServerSocketChannel`: TCP listener chấp nhận kết nối vào.
- `DatagramChannel`: UDP unicast/broadcast/multicast tùy loại và cấu hình.
- `AsynchronousSocketChannel`: socket stream với API I/O bất đồng bộ.
- `AsynchronousServerSocketChannel`: server socket bất đồng bộ.

`MulticastChannel` là subinterface của `NetworkChannel`; `DatagramChannel` triển khai `MulticastChannel` để hỗ trợ việc gia nhập nhóm multicast theo hợp đồng và khả năng nền tảng.

**Không có một danh sách option bất biến cho mọi implementation.** Ví dụ `IP_MULTICAST_TTL` có ý nghĩa với UDP multicast, không phải tùy chọn cấu hình một `SocketChannel` TCP thông thường.

### 2.1. Đọc toàn bộ danh sách được hỗ trợ

```java
try (DatagramChannel udp = DatagramChannel.open()) {
    for (SocketOption<?> option : udp.supportedOptions()) {
        System.out.println(option.name() + " : "
                + option.type().getSimpleName());
    }
}
```

Đây là **đoạn minh họa trong phương thức có xử lý `IOException`**, cần import `DatagramChannel` và `SocketOption`. Phương thức `name()` trả tên option, còn `type()` trả lớp kiểu giá trị. Đừng coi thứ tự duyệt một `Set` là ổn định; nếu cần kết quả dễ đọc và diff, **sắp xếp theo tên**.

### 2.2. Dùng `contains` thay vì so sánh chuỗi

```java
if (udp.supportedOptions().contains(
        StandardSocketOptions.IP_MULTICAST_TTL)) {
    // Có thể xem xét getOption/setOption cho TTL.
}
```

Đây là đoạn minh họa với `udp` kiểu `DatagramChannel` và import `StandardSocketOptions`. Sử dụng **đúng hằng `SocketOption`** thay vì `option.name().equals("IP_MULTICAST_TTL")`:

- Tránh lỗi chính tả/tên option không khớp.
- Giữ được thông tin kiểu `SocketOption<Integer>`.
- Không nhầm option chuẩn với một option do provider định nghĩa có tên gần giống.
- Code biên dịch bắt lỗi kiểu ở lời gọi `setOption`.

**Không tự sửa hoặc thêm option vào tập returned.** `supportedOptions` là thông tin năng lực; thêm một `SocketOption` vào một collection của riêng ứng dụng không khiến socket có thêm tính năng native.

### 2.3. `supportedOptions` vẫn tra cứu được sau khi đóng

Theo hợp đồng `NetworkChannel`, gọi `supportedOptions()` **sau khi channel đã đóng vẫn trả tập option được hỗ trợ**. Điều này khác với `getOption` hoặc `setOption`: gọi chúng trên channel đã đóng có thể ném `ClosedChannelException`.

Vì vậy:

```java
Set<SocketOption<?>> saved = channel.supportedOptions();
channel.close();
boolean same = channel.supportedOptions().equals(saved);
```

Đây là **đoạn minh họa** với `channel` được khai báo kiểu `NetworkChannel` trong một phương thức có xử lý `IOException`. Nó kiểm tra **metadata khả năng** và không nói rằng channel đã đóng vẫn dùng được để cấu hình hay truyền thông.

## 3. `SocketOption<T>` và kiểu dữ liệu của option

`SocketOption<T>` là interface đại diện cho một tùy chọn socket; `T` biểu thị **kiểu dữ liệu của giá trị option**. API có:

```java
String name();
Class<T> type();
```

Các kiểu thông dụng:

| Hằng option | Kiểu `T` | Ý nghĩa ngắn |
| --- | --- | --- |
| `StandardSocketOptions.TCP_NODELAY` | `Boolean` | Cho phép/tắt cơ chế Nagle trên TCP |
| `StandardSocketOptions.SO_KEEPALIVE` | `Boolean` | Bật/tắt TCP keep-alive của OS |
| `StandardSocketOptions.SO_REUSEADDR` | `Boolean` | Quy tắc reuse local address, tùy hệ thống |
| `StandardSocketOptions.SO_REUSEPORT` | `Boolean` | Reuse port khi được hệ thống hỗ trợ; có từ Java 9 |
| `StandardSocketOptions.SO_BROADCAST` | `Boolean` | Cho phép truyền UDP broadcast, không phải multicast |
| `StandardSocketOptions.SO_RCVBUF` | `Integer` | Gợi ý dung lượng buffer nhận theo byte |
| `StandardSocketOptions.SO_SNDBUF` | `Integer` | Gợi ý dung lượng buffer gửi theo byte |
| `StandardSocketOptions.SO_LINGER` | `Integer` | Thời gian chờ khi đóng một số socket có dữ liệu chưa gửi |
| `StandardSocketOptions.IP_TOS` | `Integer` | IP Type of Service; ý nghĩa phụ thuộc mạng/nền tảng |
| `StandardSocketOptions.IP_MULTICAST_TTL` | `Integer` | TTL cho datagram IP multicast |
| `StandardSocketOptions.IP_MULTICAST_LOOP` | `Boolean` | Cấu hình multicast loopback |
| `StandardSocketOptions.IP_MULTICAST_IF` | `NetworkInterface` | Interface để gửi datagram multicast |

Không phải mọi option trong bảng đều được hỗ trợ bởi mọi đối tượng. Bảng chỉ nêu **kiểu và ý nghĩa API của các hằng chuẩn**.

### 3.1. Compiler giúp phát hiện sai kiểu

```java
SocketOption<Boolean> delay = StandardSocketOptions.TCP_NODELAY;
SocketOption<Integer> ttl = StandardSocketOptions.IP_MULTICAST_TTL;
SocketOption<NetworkInterface> outgoing =
        StandardSocketOptions.IP_MULTICAST_IF;
```

Đây là đoạn minh họa cần import `SocketOption`, `StandardSocketOptions` và `NetworkInterface`. Một lời gọi:

```java
tcp.setOption(StandardSocketOptions.TCP_NODELAY, Boolean.TRUE);
```

đúng về **kiểu Boolean**, nhưng vẫn yêu cầu channel TCP hỗ trợ và đang ở trạng thái phù hợp. Ngược lại, việc truyền một `Integer` cho `TCP_NODELAY` không đúng generic type và bị compiler phát hiện ở code Java có kiểu rõ ràng.

### 3.2. Kiểu dữ liệu đúng chưa đủ để cấu hình hợp lệ

`SocketOption<Integer>` không có nghĩa số nguyên nào cũng hợp lệ:

- `IP_MULTICAST_TTL` có phạm vi TTL được quy định, không thể tự đặt một số âm hay rất lớn và mong được chấp nhận.
- Buffer size phải theo ràng buộc của provider/OS; giá trị thực tế có thể được điều chỉnh.
- `SO_LINGER` có ngữ nghĩa riêng cho các giá trị âm hoặc không âm.
- `IP_TOS` có giá trị hữu ích phụ thuộc giao thức và mạng.

Vì vậy kiểm tra `supportedOptions().contains(option)` chỉ trả lời **có hỗ trợ tên option không**, không phải “giá trị bạn chọn luôn đúng”.

## 4. Khác nhau giữa TCP, server TCP và UDP/multicast

| Đối tượng | Option thường liên quan | Không nên giả định |
| --- | --- | --- |
| `SocketChannel` | `TCP_NODELAY`, `SO_KEEPALIVE`, `SO_SNDBUF`, `SO_RCVBUF`, `SO_REUSEADDR` | Có mọi option của `DatagramChannel` |
| `ServerSocketChannel` | `SO_RCVBUF`, `SO_REUSEADDR` và option khác tùy implementation | Listener TCP có thể chỉnh `TCP_NODELAY` trên chính listening channel |
| `DatagramChannel` | `SO_SNDBUF`, `SO_RCVBUF`, `SO_BROADCAST`, `SO_REUSEADDR`, `IP_MULTICAST_IF/TTL/LOOP` | Hỗ trợ `TCP_NODELAY` hoặc mọi khả năng của mạng |
| `AsynchronousSocketChannel` | Các option phù hợp stream socket và provider | Set option loại multicast IP chỉ vì tên lớp có socket |
| `AsynchronousServerSocketChannel` | Các option phù hợp listener TCP và provider | Có tập option giống hệt `AsynchronousSocketChannel` |

Những tập thực tế **có thể chứa option mở rộng** ngoài `StandardSocketOptions`. Ví dụ một hệ thống có thể hiển thị những option về TCP keep-alive chi tiết hoặc xử lý socket riêng của hệ điều hành. Không hardcode số lượng và tên của tất cả phần tử mà không có kiểm chứng.

### 4.1. `SocketChannel` và `TCP_NODELAY`

`TCP_NODELAY` dùng cho TCP stream socket. Kiểm tra trước khi cấu hình:

```java
if (tcp.supportedOptions().contains(
        StandardSocketOptions.TCP_NODELAY)) {
    boolean original =
            tcp.getOption(StandardSocketOptions.TCP_NODELAY);
    tcp.setOption(StandardSocketOptions.TCP_NODELAY, true);
    boolean effective =
            tcp.getOption(StandardSocketOptions.TCP_NODELAY);
    System.out.println("TCP_NODELAY effective = " + effective);
    tcp.setOption(StandardSocketOptions.TCP_NODELAY, original);
}
```

Đây là **đoạn minh họa** với `tcp` kiểu `SocketChannel` còn mở và phương thức xử lý `IOException`. Việc đọc lại giá trị có thể hữu ích để xác nhận ý định cấu hình, nhưng **không** chứng minh một ứng dụng sẽ có latency thấp hơn. Với giao thức request/response, nên đo thêm throughput, packetization và tài nguyên CPU.

### 4.2. `ServerSocketChannel` có vai trò listener riêng

Một server socket đang lắng nghe **không giống** một socket kết nối TCP cụ thể. `TCP_NODELAY` ảnh hưởng lên TCP connection, không phải một thiết lập mặc định mà ta cứ gọi trực tiếp trên mọi server listener.

Khi cần cấu hình từng kết nối đã được chấp nhận:

```java
try (ServerSocketChannel listener = ServerSocketChannel.open()) {
    // listener.bind(...) ở ngữ cảnh có quyền và địa chỉ phù hợp.
    SocketChannel accepted = listener.accept();
    if (accepted != null) {
        try (accepted) {
            if (accepted.supportedOptions().contains(
                    StandardSocketOptions.TCP_NODELAY)) {
                accepted.setOption(
                        StandardSocketOptions.TCP_NODELAY, true);
            }
        }
    }
}
```

Đây là **mã minh họa chưa chạy độc lập**: cần bind listener trên địa chỉ thích hợp trước khi `accept` và xử lý `IOException`; nếu không có kết nối tới, `accept()` ở blocking mode có thể chờ. Không dùng đoạn này như một bài test tự động không có client.

### 4.3. `DatagramChannel` và các tùy chọn multicast

UDP multicast có các option chuyên biệt:

- `IP_MULTICAST_IF` — chọn **network interface gửi** các datagram multicast.
- `IP_MULTICAST_TTL` — điều chỉnh **TTL/hop-limit** theo hợp đồng option.
- `IP_MULTICAST_LOOP` — cho phép/điều chỉnh loopback của datagram multicast theo nền tảng.
- `SO_REUSEADDR` — thường được cân nhắc khi nhiều tiến trình muốn bind địa chỉ/port dùng cho multicast, với semantics phụ thuộc OS.
- `SO_RCVBUF` — liên quan bộ đệm nhận; không bảo đảm không mất gói nếu ứng dụng xử lý chậm.

`SO_BROADCAST` liên quan **UDP broadcast** chứ không phải việc tham gia multicast group. Dù cùng nằm trên `DatagramChannel`, không dùng `SO_BROADCAST` làm “cờ bật multicast”.

### 4.4. `SO_REUSEPORT` và tính khả dụng

`StandardSocketOptions.SO_REUSEPORT` có từ **Java 9**, không tồn tại trong Java 7/8. Không giả định option này được cung cấp trên mọi hệ điều hành hoặc mọi loại socket. Trước khi thiết kế nhiều listener cùng port, cần:

1. Kiểm tra `supportedOptions().contains(SO_REUSEPORT)` **trên đúng socket**.
2. Cấu hình ở thời điểm phù hợp, thường **trước `bind`**.
3. Xử lý `setOption`, `bind` và giới hạn quyền/OS.
4. Kiểm thử thực tế hành vi phân phối traffic và tính nhất quán ứng dụng.

**`SO_REUSEADDR` không đồng nghĩa với `SO_REUSEPORT`**; semantics của cả hai phụ thuộc nền tảng. Có tên trong `supportedOptions` chưa đủ để bảo đảm thiết kế nhiều socket bind cùng cổng hoạt động giống nhau trên mọi máy.

## 5. Kiểm tra trước khi cấu hình, nhưng không nuốt lỗi

Một helper generic hữu ích:

```java
static <T> boolean setWhenAvailable(
        NetworkChannel channel, SocketOption<T> option, T value)
        throws IOException {
    if (!channel.supportedOptions().contains(option)) {
        return false; // Không có option: caller quyết định fallback.
    }
    channel.setOption(option, value);
    return true;
}
```

Đây là phương thức minh họa để đặt vào một lớp Java, với import `NetworkChannel`, `SocketOption` và `IOException`. Trả `false` chỉ khi option **không được liệt kê**; những lỗi `setOption` vẫn được propagate, tránh tình huống báo “không hỗ trợ” để che lỗi tham số, quyền hoặc socket đã đóng.

Ví dụ dùng helper:

```java
boolean configured = setWhenAvailable(
        udp, StandardSocketOptions.IP_MULTICAST_LOOP, true);
if (!configured) {
    // Theo chính sách ứng dụng: cảnh báo hoặc từ chối tính năng multicast.
}
```

Đây là đoạn minh họa với `udp` là `DatagramChannel` còn mở, và phương thức xử lý `IOException`. Chọn `true`/`false` chỉ sau khi hiểu nghĩa loopback và nhu cầu sản phẩm; không đặt cờ tuỳ tiện chỉ vì được hỗ trợ.

### 5.1. Câu hỏi “bắt buộc hay tùy chọn?”

Trước khi viết `if (supported) set...`, hãy phân loại **đòi hỏi nghiệp vụ**:

- **Tùy chọn tối ưu hóa**: như một số tunable buffer hoặc TCP_NODELAY. Nếu không hỗ trợ, có thể bỏ qua **và ghi nhận** cho telemetry.
- **Tính năng bắt buộc**: chẳng hạn một cơ chế truyền thông yêu cầu interface multicast cụ thể. Nếu không hỗ trợ hoặc không cấu hình được, **fail fast** thay vì chạy trong trạng thái không đáp ứng hợp đồng.
- **Rủi ro bảo mật/phân phối**: như reuse port. Nếu thiếu option, không âm thầm đổi sang phương án mở cổng khác có semantics khác mà không được chấp thuận.

Cách quyết định khi không hỗ trợ có thể là fallback, disable feature hoặc báo lỗi cấu hình. **Không có chính sách chung đúng cho tất cả option**.

### 5.2. Đừng chỉ catch `UnsupportedOperationException`

Lời gọi `setOption` có thể thất bại vì những lý do khác:

```java
try {
    udp.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
} catch (UnsupportedOperationException ex) {
    // Provider/socket không hỗ trợ tùy chọn.
} catch (IllegalArgumentException ex) {
    // Giá trị không hợp lệ.
} catch (java.nio.channels.ClosedChannelException ex) {
    // Vòng đời channel sai: đã đóng.
} catch (IOException ex) {
    // Lỗi I/O khi tương tác với hệ thống.
}
```

Đây là đoạn minh họa trong một phương thức có `udp` và import tương ứng. Tùy API, một số điều kiện khác như quyền truy cập có thể gây exception phù hợp. Không gom tất cả vào “option unsupported”: lỗi quyền và lifecycle có thể là sự cố vận hành cần báo nghiêm túc.

### 5.3. `getOption` cũng không phải phép đọc không thể thất bại

`getOption` cũng có thể ném `UnsupportedOperationException`, `ClosedChannelException` hoặc `IOException`. Một lần `supportedOptions()` trả `true` không bảo đảm channel sẽ vẫn đang mở sau đó; thread khác có thể đóng channel ngay trước lệnh đọc.

**Preflight không thay thế xử lý lỗi tại thao tác thực**.

## 6. Multicast: kiểm tra option không đồng nghĩa join group thành công

Đây là điểm cần phân biệt trong chương *Socket và multicast*.

`DatagramChannel` có thể implements `MulticastChannel` và liệt kê `IP_MULTICAST_TTL`. Nhưng để **nhận datagram gửi tới group**, ứng dụng còn cần một flow khác:

1. Kiểm tra **địa chỉ group multicast hợp lệ** và protocol family (IPv4 hoặc IPv6).
2. Chọn một `NetworkInterface` đang tồn tại và thích hợp; kiểm tra trạng thái/khả năng theo OS và điều kiện mạng.
3. Tạo `DatagramChannel` cho protocol family phù hợp.
4. Cân nhắc các option bind/reuse, thường cấu hình **trước bind** khi cần.
5. Bind local address/port theo mục tiêu.
6. Gọi `channel.join(groupAddress, networkInterface)` để tham gia group; giữ `MembershipKey` và quản lý drop/đóng.
7. Gửi/nhận datagram và xử lý timeout, mất gói, network routing, firewall, TTL, loopback theo hợp đồng.
8. Đóng channel để giải phóng tài nguyên khi ngừng.

`supportedOptions()` chỉ giúp trả lời **socket có expose tùy chọn nào**, **không kiểm tra** rằng router sẽ chuyển multicast, firewall cho phép traffic, NIC hỗ trợ group, hay một lời gọi `join(...)` chắc chắn thành công.

### 6.1. Các loại option và việc tham gia group

| API/khái niệm | Nó làm gì? |
| --- | --- |
| `supportedOptions()` | Khám phá option mà chính channel công bố |
| `setOption(IP_MULTICAST_IF, iface)` | Chọn interface để gửi datagram multicast |
| `setOption(IP_MULTICAST_TTL, ttl)` | Chọn TTL cho datagram multicast |
| `setOption(IP_MULTICAST_LOOP, flag)` | Cấu hình xử lý multicast loopback |
| `channel.join(group, iface)` | Yêu cầu tham gia group trên interface và trả `MembershipKey` nếu thành công |
| `MembershipKey.drop()` | Rời một membership do key đại diện |
| `channel.send(buffer, destination)` | Gửi datagram tới địa chỉ đích |
| `channel.receive(buffer)` | Nhận datagram nếu có; có thể block theo mode |

**Gọi `setOption(IP_MULTICAST_IF,...)` không phải gọi `join`**. Một ứng dụng chỉ gửi multicast có thể cần lựa chọn outgoing interface mà không nhất thiết phải join group để nhận. Một ứng dụng nhận multicast cần mô hình membership và địa chỉ bind thích hợp.

### 6.2. IPv4/IPv6 phải được chọn đúng

`DatagramChannel.open(StandardProtocolFamily.INET)` yêu cầu IPv4 channel; `INET6` cho IPv6 tùy khả năng hệ thống. Theo hợp đồng API, nếu family không được provider/OS hỗ trợ, `open(family)` có thể ném `UnsupportedOperationException` hoặc lỗi I/O phù hợp.

Nếu muốn join group IPv6, đừng chỉ dựa vào một `DatagramChannel.open()` mặc định và tin protocol family chắc chắn phù hợp. Hãy chọn có chủ đích và xử lý lỗi. Không sử dụng địa chỉ multicast IPv4 làm một group IPv6 vì cả hai đều mang chữ “multicast”.

### 6.3. Kiểm tra `NetworkInterface` chỉ là bước chuẩn bị

Nếu ứng dụng cần interface cụ thể, có thể dùng `NetworkInterface.getByName(name)` hoặc các API khám phá interface; sau đó kiểm tra `iface != null` và `iface.supportsMulticast()` khi thích hợp, đồng thời xét trạng thái đang hoạt động và địa chỉ family tương ứng.

Nhưng **`supportsMulticast() == true` không chứng minh đường mạng tới group hoạt động**. Còn có firewall, switch/router và cấu hình membership.

### 6.4. TTL và loopback không phải thước đo thông mạng

Giá trị `TTL=1` thường được chọn để giữ phạm vi multicast cục bộ, nhưng không thay được phân tích topology. Multicast loopback ảnh hưởng cách xử lý gói gửi trong môi trường máy cục bộ, không có nghĩa mọi tiến trình có thể nhận được hoặc tất cả gói đều được giao.

Muốn chứng minh hoạt động multicast cần **test end-to-end có sender/receiver và mạng phù hợp**, không chỉ `getOption(IP_MULTICAST_TTL)==1`.

## 7. Thời điểm đặt option: trước bind, trước connect và sau khi mở

Dù option được hỗ trợ, **thời điểm cấu hình** có thể quan trọng:

- `SO_REUSEADDR` và `SO_REUSEPORT` thường cần được đặt **trước bind** để có hiệu lực như mong đợi. Đổi sau bind có thể không làm thay đổi hành vi của địa chỉ đã được cấp.
- `SO_RCVBUF`/`SO_SNDBUF` là yêu cầu điều chỉnh kích cỡ buffer; OS có thể kẹp giới hạn hoặc làm tròn. Một số implementation có ràng buộc thời điểm cấu hình.
- `TCP_NODELAY` thường có thể cấu hình trên stream socket đang mở; hiệu quả thực tế phải đo.
- `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP` và `IP_MULTICAST_IF` phục vụ datagram multicast và có các điều kiện cụ thể theo provider.

Ví dụ bind có kiểm tra capability:

```java
try (DatagramChannel udp = DatagramChannel.open()) {
    if (udp.supportedOptions().contains(
            StandardSocketOptions.SO_REUSEADDR)) {
        udp.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    }
    udp.bind(new java.net.InetSocketAddress(0));
    // Cấu hình và dùng theo hợp đồng sản phẩm.
}
```

Đây là đoạn minh họa trong phương thức xử lý `IOException`. `new InetSocketAddress(0)` yêu cầu OS chọn ephemeral port. Không gửi hay join multicast trong đoạn này; nó chỉ cho thấy một option liên quan bind được cấu hình **trước bind** khi có hỗ trợ.

### 7.1. Buffer size là yêu cầu, không phải cam kết tài nguyên

`SO_SNDBUF`/`SO_RCVBUF` trả `Integer` với số byte nhưng có thể được hệ điều hành điều chỉnh. Do đó khi tối ưu UDP throughput:

1. Đặt giá trị mong muốn (hợp lệ, theo nhu cầu).
2. Đọc lại qua `getOption`.
3. Đo dropped packets, throughput, latency, queue và memory.
4. Không coi giá trị đọc lại đơn lẻ chứng minh ứng dụng không mất gói.

Một số hệ điều hành có thể điều chỉnh kích thước lớn hơn/nhỏ hơn. `supportedOptions` không cung cấp số byte tối đa khả thi.

### 7.2. Keep-alive không phải bộ kiểm tra kết nối tức thời

Nếu `SO_KEEPALIVE` được hỗ trợ và bật, OS có thể kiểm tra peer định kỳ sau khoảng idle theo chính sách nền tảng; nó không phải cơ chế heartbeat với thời hạn cố định của sản phẩm. Đừng giả định `setOption(SO_KEEPALIVE,true)` đồng nghĩa mọi dead connection được phát hiện trong vài giây.

## 8. Java 7 và Java hiện đại: chọn đúng API, tránh nhầm legacy

### 8.1. Trên NIO channel

Từ **Java 7**, có thể dùng trực tiếp:

```java
SocketChannel tcp = SocketChannel.open();
Set<SocketOption<?>> options = tcp.supportedOptions();
```

Đây là đoạn minh họa, cần import và đóng channel. Không cần module bổ sung chỉ để gọi `supportedOptions` trên `NetworkChannel` thông thường.

### 8.2. Trên `java.net.Socket`, `ServerSocket` và `DatagramSocket`

Từ **Java 9**, các lớp socket truyền thống có API option trực tiếp theo `SocketOption<T>`:

```java
try (Socket socket = new Socket()) {
    Set<SocketOption<?>> options = socket.supportedOptions();
    if (options.contains(StandardSocketOptions.TCP_NODELAY)) {
        socket.setOption(StandardSocketOptions.TCP_NODELAY, true);
    }
}
```

Đây là đoạn minh họa trong phương thức xử lý `IOException`; chưa thực hiện kết nối TCP. `Socket.supportedOptions()` không phải API có từ Java 7. Đoạn tương tự có thể dùng trên `ServerSocket` và `DatagramSocket` theo các option tương ứng.

### 8.3. Không dùng API deprecated `jdk.net.Sockets` cho code mới

Module `jdk.net` từng cung cấp tiện ích `jdk.net.Sockets.supportedOptions(Class<?>)` cho các lớp `java.net`. Trên Java hiện đại, tiện ích này đã **deprecated**, và bản `supportedOptions(Class)` được đánh dấu có thể bị loại bỏ.

Với source Java hiện đại, hãy dùng **`socket.supportedOptions()`** trực tiếp (Java 9+) hoặc **`channel.supportedOptions()`** trên `NetworkChannel`. Không cần thiết kế mới phụ thuộc vào tiện ích deprecated của `jdk.net.Sockets` chỉ để dò option.

### 8.4. Tùy chọn mở rộng là dữ liệu phụ thuộc nền tảng

Một số JDK/OS trả thêm option không nằm trong bộ hằng `StandardSocketOptions`, ví dụ option về TCP keep-alive chi tiết. Các option mở rộng có thể thuộc `jdk.net.ExtendedSocketOptions` hoặc implementation nội bộ.

Cách tiếp cận an toàn:

- Nếu ứng dụng chỉ cần một **option chuẩn**, kiểm tra đúng hằng `StandardSocketOptions`.
- Nếu chủ động cần một **option mở rộng**, quản lý module availability, phiên bản JDK và fallback rõ ràng.
- Không parse một chuỗi tên option rồi ép kiểu tùy tiện cho tất cả.
- Không mặc định một option xuất hiện trên máy A cũng có trên máy B.
- Không cố gắng set mọi option có trong danh sách; một số có thể read-only hoặc đòi quyền/ngữ cảnh đặc biệt.

**Special Note thực hành:** các API chính trong bài đều áp dụng hiện tại. Nhắc tới tiện ích deprecated chỉ để **tránh sử dụng** trong thiết kế mới, không coi nó là giải pháp cần học theo.

## 9. Ví dụ Java 17+ độc lập — khám phá TCP/UDP/async và kiểm tra đúng option

Chương trình này không gửi gói mạng, không bind port công khai, không connect ra Internet và không tham gia multicast group. Nó chỉ:

1. Mở `SocketChannel` (TCP), `ServerSocketChannel`, `DatagramChannel` IPv4, `AsynchronousSocketChannel` và `AsynchronousServerSocketChannel`.
2. Gọi `supportedOptions()` trên từng channel, in số lượng và danh sách tên đã sort cho TCP/UDP.
3. Dùng `SocketOption.name()/type()` để chỉ ra kiểu giá trị.
4. Kiểm tra `TCP_NODELAY` trên TCP, `IP_MULTICAST_TTL` trên UDP và việc option multicast **không có** trên TCP channel ở môi trường kiểm thử.
5. Với option được hỗ trợ, gọi `setOption/getOption` theo kiểu đúng rồi khôi phục giá trị ban đầu.
6. Khi một option không được hỗ trợ, kiểm tra `getOption` ném `UnsupportedOperationException` trong trường hợp thử.
7. Đóng channel và xác nhận `supportedOptions()` vẫn trả metadata sau khi đóng.
8. Mở `Socket`, `ServerSocket` và `DatagramSocket` dạng `java.net` để minh họa API tra cứu trực tiếp từ Java 9.
9. Dùng assertion để phát hiện sai kỳ vọng; đóng mọi tài nguyên bằng `try-with-resources`.

**Không hardcode số option hoặc các tên mở rộng làm tiêu chí thành công.** Danh sách trả về khác nhau theo hệ điều hành/JDK; test chỉ cố kiểm chứng những khái niệm API và ví dụ điều kiện hỗ trợ thực tế.

Tạo file **`SupportedOptionsDemo.java`**:

```java
import java.io.IOException;
import java.net.DatagramSocket;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketOption;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.DatagramChannel;
import java.nio.channels.NetworkChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.Set;

public final class SupportedOptionsDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void display(String kind, NetworkChannel channel) {
        Set<SocketOption<?>> options = channel.supportedOptions();
        System.out.println(kind + " option count = " + options.size());
        System.out.println(kind + " options sorted = "
                + options.stream().map(SocketOption::name).sorted().toList());
    }

    private static void tryTcpOption(SocketChannel tcp) throws IOException {
        SocketOption<Boolean> option = StandardSocketOptions.TCP_NODELAY;
        if (!tcp.supportedOptions().contains(option)) {
            System.out.println("TCP_NODELAY unavailable = true");
            return;
        }
        boolean before = tcp.getOption(option);
        tcp.setOption(option, !before);
        boolean changed = tcp.getOption(option);
        check(changed != before, "TCP_NODELAY did not change");
        tcp.setOption(option, before);
        System.out.println("TCP_NODELAY changed and restored = true");
    }

    private static void tryMulticastOption(DatagramChannel udp)
            throws IOException {
        SocketOption<Integer> option = StandardSocketOptions.IP_MULTICAST_TTL;
        if (!udp.supportedOptions().contains(option)) {
            System.out.println("multicast TTL unavailable = true");
            return;
        }
        int before = udp.getOption(option);
        udp.setOption(option, 1);
        int now = udp.getOption(option);
        check(now == 1, "IP_MULTICAST_TTL not applied");
        udp.setOption(option, before);
        System.out.println("multicast TTL=1 roundtrip = true");
    }

    public static void main(String[] args) throws Exception {
        Set<SocketOption<?>> saved;
        DatagramChannel postClose;
        try (SocketChannel tcp = SocketChannel.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             DatagramChannel udp = DatagramChannel.open(StandardProtocolFamily.INET);
             AsynchronousSocketChannel asyncTcp =
                     AsynchronousSocketChannel.open();
             AsynchronousServerSocketChannel asyncServer =
                     AsynchronousServerSocketChannel.open()) {
            display("TCP", tcp);
            display("UDP", udp);
            System.out.println("TCP_NODELAY type = "
                    + StandardSocketOptions.TCP_NODELAY.type().getSimpleName());
            System.out.println("IP_MULTICAST_IF type = "
                    + StandardSocketOptions.IP_MULTICAST_IF.type().getSimpleName());
            System.out.println("TCP supports TCP_NODELAY = "
                    + tcp.supportedOptions().contains(StandardSocketOptions.TCP_NODELAY));
            System.out.println("UDP supports IP_MULTICAST_TTL = "
                    + udp.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_TTL));
            System.out.println("TCP supports IP_MULTICAST_TTL = "
                    + tcp.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_TTL));
            System.out.println("server supports SO_RCVBUF = "
                    + server.supportedOptions().contains(StandardSocketOptions.SO_RCVBUF));
            System.out.println("async TCP options available = "
                    + !asyncTcp.supportedOptions().isEmpty());
            System.out.println("async server options available = "
                    + !asyncServer.supportedOptions().isEmpty());

            tryTcpOption(tcp);
            tryMulticastOption(udp);
            if (!tcp.supportedOptions().contains(
                    StandardSocketOptions.IP_MULTICAST_TTL)) {
                try {
                    tcp.getOption(StandardSocketOptions.IP_MULTICAST_TTL);
                    throw new AssertionError(
                            "Unsupported option unexpectedly succeeded");
                } catch (UnsupportedOperationException expected) {
                    System.out.println(
                            "unsupported TCP getOption rejected = true");
                }
            }

            saved = Set.copyOf(udp.supportedOptions());
            postClose = udp;
        }
        check(postClose.supportedOptions().equals(saved),
                "closed options changed");
        System.out.println("options after channel close = true");

        try (Socket socket = new Socket();
             ServerSocket server = new ServerSocket();
             DatagramSocket datagram =
                     new DatagramSocket((java.net.SocketAddress) null)) {
            System.out.println("Socket direct options available = "
                    + !socket.supportedOptions().isEmpty());
            System.out.println("ServerSocket direct options available = "
                    + !server.supportedOptions().isEmpty());
            System.out.println("DatagramSocket direct options available = "
                    + !datagram.supportedOptions().isEmpty());
        }
        System.out.println("checks = PASS");
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 SupportedOptionsDemo.java
java SupportedOptionsDemo
```

### 9.1. Stdout chính xác của một lượt chạy đã kiểm thử

Dưới đây là kết quả từ một lần biên dịch và chạy thật trên Windows/JDK 17. **Danh sách option, số lượng và một số giá trị true/false là dữ liệu nền tảng**, không phải stdout được bảo đảm giống hệt trên mọi máy.

```text
TCP option count = 11
TCP options sorted = [IP_TOS, SO_KEEPALIVE, SO_LINGER, SO_OOBINLINE, SO_RCVBUF, SO_REUSEADDR, SO_SNDBUF, TCP_KEEPCOUNT, TCP_KEEPIDLE, TCP_KEEPINTERVAL, TCP_NODELAY]
UDP option count = 9
UDP options sorted = [IP_DONTFRAGMENT, IP_MULTICAST_IF, IP_MULTICAST_LOOP, IP_MULTICAST_TTL, IP_TOS, SO_BROADCAST, SO_RCVBUF, SO_REUSEADDR, SO_SNDBUF]
TCP_NODELAY type = Boolean
IP_MULTICAST_IF type = NetworkInterface
TCP supports TCP_NODELAY = true
UDP supports IP_MULTICAST_TTL = true
TCP supports IP_MULTICAST_TTL = false
server supports SO_RCVBUF = true
async TCP options available = true
async server options available = true
TCP_NODELAY changed and restored = true
multicast TTL=1 roundtrip = true
unsupported TCP getOption rejected = true
options after channel close = true
Socket direct options available = true
ServerSocket direct options available = true
DatagramSocket direct options available = true
checks = PASS
```

### 9.2. Tại sao tên mở rộng xuất hiện?

Ở môi trường kiểm thử, một số tên như `SO_OOBINLINE`, `TCP_KEEPIDLE`, `TCP_KEEPINTERVAL`, `TCP_KEEPCOUNT` và `IP_DONTFRAGMENT` xuất hiện trong tập option. **Không lấy số 11 và 9 làm ngưỡng assert trên máy khác.** Một implementation có thể bổ sung, bớt hoặc đưa ra tập extended option khác.

Những tên được in là **metadata runtime**. Không phải mọi tên trong đó đều nên/được phép set giá trị tùy ý; khi cần thiết kế một tính năng dựa trên option cụ thể, hãy đọc hợp đồng option đó và thử chính thao tác get/set có xử lý lỗi.

### 9.3. Vì sao thử `TCP_NODELAY` mà không connect?

Chương trình muốn kiểm chứng **cấu hình option trên socket TCP đang mở**, không đo hành vi mạng. `SocketChannel.open()` tạo một channel chưa kết nối. Provider kiểm thử cho phép get/set `TCP_NODELAY` trên channel này.

Việc setter và getter hoạt động không chứng minh kết nối tương lai có performance tốt hơn; muốn kết luận về TCP latency phải có bài đo end-to-end với giao thức và workload thật.

### 9.4. Vì sao `IP_MULTICAST_TTL` xuất hiện trên UDP?

`DatagramChannel` mở theo `INET` là channel IP datagram, phù hợp cho multicast khi môi trường hỗ trợ. Trong lần test, `IP_MULTICAST_TTL` nằm trong `supportedOptions()`; code đọc giá trị ban đầu, đặt TTL=1, xác minh qua `getOption`, sau đó khôi phục.

**Chưa có gói nào được gửi** và **chưa có group nào được join**. Đây chỉ là test khả năng và hoạt động của socket option.

### 9.5. Vì sao kiểm tra option không hỗ trợ trên TCP?

Khi `TCP` không liệt kê `IP_MULTICAST_TTL`, code chủ động thử `tcp.getOption(IP_MULTICAST_TTL)` và xác minh `UnsupportedOperationException`. Đây là ví dụ rõ ràng rằng tùy chọn hợp lệ trong `StandardSocketOptions` vẫn có thể **không được một loại channel cụ thể hỗ trợ**.

Đoạn thử được bao bởi điều kiện `!supportedOptions().contains(...)` để không ép một giả định thiếu khả chuyển. Nếu provider khác có đặc tính bất thường, test không mặc định nó phải có cùng tập option của Windows.

### 9.6. Vì sao kiểm tra sau khi đóng channel?

`supportedOptions()` là thao tác truy vấn **tập khả năng được công bố**, theo Java API nó vẫn hoạt động sau close. Test lưu một snapshot của tập UDP, đóng channel qua `try-with-resources` rồi so kết quả.

Điều này không có nghĩa `getOption` và `setOption` vẫn hoạt động. Sau close, chúng là thao tác I/O/cấu hình trên channel không còn mở và có thể bị từ chối bằng `ClosedChannelException`.

### 9.7. Vì sao còn có `Socket`, `ServerSocket` và `DatagramSocket`?

Các lớp socket trong `java.net` có `supportedOptions()` trực tiếp từ Java 9. Chương trình in tình trạng tập option của ba đối tượng này để minh họa API hiện đại, tránh phụ thuộc các tiện ích `jdk.net.Sockets` đã deprecated.

Đừng hiểu ba constructor chưa connect/bind là một chương trình mạng hoàn chỉnh; mục đích là **capability introspection**, không phải thực hiện giao tiếp.

### 9.8. Giới hạn của ví dụ

Môi trường thực thi phải cho phép tạo các channel/socket liên quan và có IPv4 cho `DatagramChannel.open(INET)`. Runtime giới hạn quyền network hoặc thiếu protocol family có thể ném lỗi khi mở. Danh sách option và hành vi một số setter còn chịu sự khác biệt provider/OS.

Chương trình sẽ fail test khi một khả năng được công bố nhưng thao tác kiểm chứng của provider không đáp ứng kỳ vọng trong fixture. Đó là **tín hiệu môi trường cần điều tra**, không phải lý do hardcode lại danh sách option.

## 10. Từ phát hiện capability đến cấu hình an toàn cho sản phẩm

Một hệ thống nên đi qua từng bước:

```text
Mục tiêu nghiệp vụ: cần cấu hình option X
        |
        v
Chọn đúng socket/channel type và protocol family
        |
        v
Mở socket/channel, xác định ownership
        |
        v
supportedOptions().contains(X) ?
        |
        +-- Không --> fallback hoặc báo thiếu tính năng bắt buộc
        |
        +-- Có --> kiểm tra giá trị, thời điểm cấu hình, quyền
                       |
                       v
                  setOption(X, value)
                       |
                       +-- Exception --> báo lỗi/rollback/fallback có điều kiện
                       |
                       +-- Thành công --> getOption(X) nếu cần xác nhận
                                            |
                                            v
                                  Kiểm thử hành vi mạng thực tế
```

Sơ đồ chỉ mô tả **luồng ra quyết định**; bước `setOption` được OS/provider chấp nhận chưa đảm bảo network hoạt động theo mong đợi.

### 10.1. Tối ưu hóa tùy chọn khác tính năng bắt buộc

Ví dụ, nếu `SO_RCVBUF` không đạt mức mong muốn, ứng dụng có thể vẫn chạy nhưng phải giám sát packet drops. Còn nếu sản phẩm bắt buộc multicast qua một interface và việc chọn `IP_MULTICAST_IF` thất bại, tiếp tục gửi trên interface mặc định có thể gửi dữ liệu sai nơi. Chỉ ứng dụng mới biết fallback nào được phép.

### 10.2. Đọc lại chỉ là một bước xác minh

Với option định lượng như buffer size, `getOption` có thể trả giá trị hiệu lực đã được điều chỉnh bởi OS. Tính đúng đắn của throughput không được suy ra chỉ từ getter; phải đo tải thật, lỗi, dropped packet, latency và tính khả dụng cuối cùng.

### 10.3. Thu thập telemetry hữu ích

Trong môi trường nhiều máy, có thể ghi một lần lúc startup:

- Java version và OS.
- Kiểu socket/channel và protocol family.
- Các option **bắt buộc** có mặt hay không.
- Các option **tối ưu** được bật hay bỏ qua.
- Giá trị được yêu cầu và giá trị đọc lại (khi có ý nghĩa).
- Lỗi cấu hình và chính sách fallback.
- Những tính năng multicast/broadcast/reuse port thật sự đã được test.

Không ghi hoặc gửi ra nơi công khai địa chỉ mạng, interface, topology hay cấu hình nhạy cảm nếu không cần. Không ghi log toàn bộ tập option cho mỗi packet — đó là metadata tương đối ổn định trong vòng đời socket và log lặp sẽ gây tốn tài nguyên.

## 11. Các giới hạn mà `supportedOptions()` không thể giải quyết

| Điều cần biết | `supportedOptions()` trả lời được? | Cần làm gì thêm? |
| --- | --- | --- |
| Đối tượng hỗ trợ tên option X? | **Có**, thông qua `contains(X)` | Kiểm tra đúng socket/channel |
| Giá trị X=Y hợp lệ? | **Không** | Theo docs option và xử lý `setOption` |
| Option có thể thay đổi sau bind? | **Không đầy đủ** | Đọc hợp đồng và cấu hình đúng thời điểm |
| OS có điều chỉnh buffer size? | **Không** | `getOption` sau setter; đo thật |
| Mạng có hỗ trợ multicast qua interface cụ thể? | **Không** | Kiểm tra NIC, join, firewall, routing, test sender/receiver |
| Hai tiến trình bind được cùng port? | **Không** | Thử cấu hình trước bind, kiểm tra `bind` và semantics OS |
| Kết nối TCP hoạt động? | **Không** | `connect`/`accept` và I/O thật |
| UDP có bị mất packet? | **Không** | Sequence numbers, counters, monitoring, đo end-to-end |
| Socket có đang mở? | **Không** | `isOpen`, đồng thời xử lý race |
| Một option có cải thiện performance? | **Không** | Benchmark đúng workload |
| Tập option cố định giữa JDK/OS? | **Không** | Runtime introspection ở môi trường đích |
| Tham gia group multicast thành công? | **Không** | `join(group, iface)` và xử lý I/O |
| Một option có yêu cầu quyền đặc biệt? | **Không** | Đọc docs/provider, kiểm tra exception và quyền |
| Mọi option trong tập đều settable? | **Không** | Có option read-only hoặc hành vi phụ thuộc runtime |

**Tập supported là điều kiện để lựa chọn một hướng cấu hình, không phải bằng chứng về mọi điều kiện vận hành**.

## 12. Lỗi và exception cần phân biệt

| Lỗi/tình huống | Khi nào có thể xảy ra? | Phản ứng gợi ý |
| --- | --- | --- |
| `UnsupportedOperationException` | Option không được socket/channel hỗ trợ; hoặc family/provider không hỗ trợ | Feature fallback hoặc từ chối theo hợp đồng |
| `IllegalArgumentException` | Value không hợp lệ theo option | Sửa cấu hình, không retry cùng value |
| `ClosedChannelException` | Channel đã đóng khi get/set/bind | Sửa quản lý vòng đời |
| `IOException` | Lỗi hệ thống I/O hoặc network | Báo nguyên nhân, retry có điều kiện |
| `SecurityException` | Quyền truy cập bị hạn chế ở môi trường phù hợp | Không tự lách quyền; báo cấu hình |
| `NullPointerException` | Option name null theo hợp đồng API; tùy trường hợp value null có thể hợp lệ | Không truyền tên null; đọc docs cho value |
| `AlreadyBoundException` | Cố bind lại khi socket/channel đã bound | Phân biệt bind lifecycle, không giải quyết bằng đổi option tùy tiện |
| `UnsupportedAddressTypeException` | Loại địa chỉ không phù hợp | Chọn protocol family/address đúng |
| `FileSystemAlreadyExistsException` | Không thuộc vấn đề socket options | Đừng nhầm lỗi tài nguyên khác với socket capability |
| `BindException`/`SocketException` | Bind hoặc thao tác mạng thực tế thất bại | Kiểm tra port, quyền, OS, interface và policy |

Không cần bắt tất cả exception trên mọi đoạn code; hãy bắt **những loại có hành động khôi phục rõ ràng**, còn lại propagate tới tầng quản lý. Tránh dùng `catch (Exception) { }` bỏ qua thất bại rồi tiếp tục như thể cấu hình đã thành công.

### 12.1. Thứ tự check và thao tác vẫn có race

Nếu thread A gọi `supportedOptions()` rồi thread B đóng channel trước khi A gọi `setOption()`, tập option vẫn có thể ghi là “supported” nhưng lời gọi cấu hình thất bại. Đừng xem preflight hỗ trợ là một transaction khóa trạng thái socket.

### 12.2. Đừng suy error là option không được hỗ trợ

Một `IOException` khi set option khác với `UnsupportedOperationException`. Ví dụ OS từ chối điều chỉnh buffer hoặc channel đã đóng cần thông tin lỗi riêng; fallback giả bằng cách coi “không hỗ trợ” có thể che bug lifecycle hoặc thiếu quyền hệ thống.

## 13. Bài tập và đáp án

### Bài 1 — Hỏi capability

Muốn biết một `DatagramChannel` có hỗ trợ TTL multicast hay không, sử dụng API nào?

**Đáp án:** `udp.supportedOptions().contains(StandardSocketOptions.IP_MULTICAST_TTL)`. Đây là check tên tùy chọn trên chính channel, không phải test multicast end-to-end.

### Bài 2 — TCP và UDP

Một `SocketChannel` TCP được tạo thành công. Có thể suy ra nó hỗ trợ `IP_MULTICAST_TTL` vì đây là hằng trong `StandardSocketOptions` không?

**Đáp án:** Không. Hằng tồn tại trong Java chỉ mô tả một loại option; mỗi channel hỗ trợ tập riêng. UDP multicast và TCP là hai loại khác nhau.

### Bài 3 — Getter và setter

Sau khi `supportedOptions` có `SO_RCVBUF`, chương trình gọi `setOption(SO_RCVBUF, 10_000_000)`. Có chắc `getOption` trả đúng 10.000.000 không?

**Đáp án:** Không. Buffer sizes có thể được OS kẹp giới hạn hoặc làm tròn. Sau khi set, đọc lại nếu cần rồi đo tải thực.

### Bài 4 — Type-safety

`StandardSocketOptions.IP_MULTICAST_LOOP` có kiểu `SocketOption<Boolean>` hay `SocketOption<Integer>`?

**Đáp án:** `SocketOption<Boolean>`. Đối với TTL là `SocketOption<Integer>`; đối với interface gửi là `SocketOption<NetworkInterface>`.

### Bài 5 — Java 7 và Java 9

Có thể gọi `SocketChannel.supportedOptions()` từ Java 7 không? Có thể dùng `new Socket().supportedOptions()` với source Java 7 không?

**Đáp án:** Cách đầu có thể vì `NetworkChannel` từ Java 7. Cách sau **không**, vì API `supportedOptions` trực tiếp trên `java.net.Socket` có từ Java 9.

### Bài 6 — Sau close

Một channel đã đóng. `supportedOptions()` có thể tiếp tục được gọi không? `getOption()` có bảo đảm hoạt động không?

**Đáp án:** Theo hợp đồng `NetworkChannel`, `supportedOptions()` vẫn trả tập sau close. `getOption`/`setOption` phụ thuộc channel còn mở và có thể ném `ClosedChannelException`.

### Bài 7 — Multicast join

`IP_MULTICAST_TTL` nằm trong supported set. Có chứng minh sender/receiver đã cùng tham gia group và gói đi qua router không?

**Đáp án:** Không. Cần cấu hình interface, `join` cho receiver, bind đúng, firewall/routing phù hợp và kiểm thử truyền nhận thật.

### Bài 8 — SO_BROADCAST

Bật `SO_BROADCAST` trên UDP có tự động làm socket trở thành thành viên một multicast group không?

**Đáp án:** Không. Broadcast và multicast khác nhau. Thành viên group được quản lý bằng `MulticastChannel.join` và `MembershipKey` khi phù hợp.

### Bài 9 — Phát hiện capability nhưng set thất bại

`supportedOptions.contains(option) == true` nhưng `setOption` ném `IllegalArgumentException`. Có nên kết luận “option unsupported” không?

**Đáp án:** Không. Option có thể hỗ trợ nhưng value không hợp lệ. Cần sửa validation; không gộp lỗi giá trị với lỗi unsupported.

### Bài 10 — SO_REUSEPORT

Có nên bật `SO_REUSEPORT` vô điều kiện trên mọi máy chạy JDK 17?

**Đáp án:** Không. Đây là option thêm từ Java 9 và khả năng/semantics còn phụ thuộc OS/provider và socket type. Kiểm tra trên instance, set trước bind khi cần, xử lý lỗi và test quy trình bind thực.

### Bài 11 — Extended options

Danh sách của chương trình trên Linux chứa một số option không thấy trên Windows. Có phải Java bị lỗi?

**Đáp án:** Không nhất thiết. `supportedOptions()` có thể trả option chuẩn và option mở rộng do implementation/platform cung cấp. Không hardcode số lượng phần tử.

### Bài 12 — Kiểu kết quả generic

Vì sao code dùng `Set<SocketOption<?>>` thay cho `Set<SocketOption<Boolean>>`?

**Đáp án:** Vì một channel có thể có option với nhiều kiểu giá trị khác nhau: Boolean, Integer, NetworkInterface. Wildcard `?` biểu diễn tập không đồng nhất, còn generic type của từng hằng giúp gọi getter/setter an toàn.

### Bài 13 — Chọn network interface

Nếu cần multicast trên NIC `eth0` nhưng không tìm thấy interface này, có nên lấy interface bất kỳ rồi tự gửi không?

**Đáp án:** Không nếu contract yêu cầu NIC cụ thể. Có thể thất bại có thông tin hoặc áp dụng fallback đã được chủ động thiết kế; không gửi dữ liệu trên một NIC bất ngờ.

### Bài 14 — Default của TTL

`getOption(IP_MULTICAST_TTL)` trả `1` trên một máy. Có thể hardcode rằng default của mọi OS/JDK đều là 1 không?

**Đáp án:** Không chỉ dựa trên một lần quan sát. Hãy đọc contract/provider và cấu hình rõ giá trị mong muốn khi phù hợp, đồng thời xử lý lỗi và giới hạn hệ thống.

### Bài 15 — Introspection và hành vi thực

Một channel trả supported `TCP_NODELAY` và `setOption` thành công. Có đủ kết luận throughput hoặc latency luôn tăng không?

**Đáp án:** Không. Tùy giao thức, packet sizes, workload và mạng. Phải benchmark end-to-end.

### Bài 16 — Không dùng deprecated utility

Với Java 17, muốn hỏi option của một `DatagramSocket`, nên dùng `jdk.net.Sockets.supportedOptions(DatagramSocket.class)` hay `datagram.supportedOptions()`?

**Đáp án:** Dùng `datagram.supportedOptions()` trực tiếp. Tiện ích `jdk.net.Sockets` đã deprecated, không phải giải pháp hiện đại cho code mới.

### Bài 17 — Cấu hình trước bind

`SO_REUSEADDR` có mặt trong set. Tại sao đặt trước `bind` thường quan trọng?

**Đáp án:** Vì semantics/hiệu lực có thể được OS áp dụng tại lúc bind; thay đổi sau bind có thể không tạo tác dụng mà ứng dụng muốn. Check supported không thay thế việc chọn đúng thời điểm.

### Bài 18 — Test an toàn

Vì sao ví dụ hoàn chỉnh chỉ thay TTL và TCP_NODELAY, không tự gửi multicast tới một địa chỉ thật?

**Đáp án:** Mục tiêu bài là **tra cứu hỗ trợ và kiểm thử option getter/setter**, không thử hạ tầng multicast. Gửi hoặc join group có thể đòi network policy và tác động mạng; integration test phải dùng môi trường được phép, có sender/receiver và cleanup rõ.

## 14. Checklist khi đưa supportedOptions vào ứng dụng

- [ ] Chọn đúng kiểu: `SocketChannel`, `ServerSocketChannel`, `DatagramChannel` hoặc async channel.
- [ ] Với Java 7 sử dụng `NetworkChannel.supportedOptions`; với `java.net.Socket` direct API từ Java 9.
- [ ] Tra cứu trên **instance thực tế**, không dùng tập option đoán từ tên class.
- [ ] Dùng `contains(StandardSocketOptions.X)` thay vì so chuỗi option name.
- [ ] Tôn trọng `SocketOption<T>` và đúng kiểu Boolean/Integer/NetworkInterface.
- [ ] Xử lý trường hợp không được hỗ trợ theo **chính sách sản phẩm**: fallback, disable hoặc fail fast.
- [ ] Không nhầm option supported với mọi value đều hợp lệ.
- [ ] Không nhầm get/set option thành xác nhận bind, connect, multicast join hoặc network reachability.
- [ ] Phân biệt TCP_NODELAY, SO_KEEPALIVE cho TCP với IP_MULTICAST_* cho UDP multicast.
- [ ] Nhớ `SO_BROADCAST` không tự tham gia multicast group.
- [ ] Đọc contract và chọn đúng thời điểm cấu hình, đặc biệt các option reuse trước bind.
- [ ] Với buffer size, đọc lại giá trị hiệu lực và đo workload, không tin setter bảo đảm đúng dung lượng.
- [ ] Với SO_REUSEPORT, kiểm tra runtime support và xử lý khác biệt Java version/OS.
- [ ] Kiểm tra IPv4/IPv6 family và network interface phù hợp trước khi join group.
- [ ] Có xử lý UnsupportedOperationException, IllegalArgumentException, ClosedChannelException, IOException đúng ngữ nghĩa.
- [ ] Không coi `supportedOptions()` sau close là dấu hiệu channel vẫn có thể dùng.
- [ ] Không hardcode số lượng/tên extended options từ stdout một máy.
- [ ] Không phụ thuộc `jdk.net.Sockets` deprecated trong code mới.
- [ ] Không log toàn bộ option cho mỗi packet; quan sát capability khi startup hoặc khi tạo socket.
- [ ] Không bao giờ tự động bật mọi option có trong set; có option đặc thù/hạn chế quyền.
- [ ] Kiểm chứng phần bắt buộc bằng integration test trên network environment thực tế.
- [ ] Quản lý tài nguyên bằng `try-with-resources`; không tạo/đóng socket không có owner rõ.
- [ ] Bài test introspection không cần gửi packet hoặc join group; khi test multicast phải có môi trường cho phép.
- [ ] Dùng JDK 17+ cho ví dụ hoàn chỉnh; API lõi `NetworkChannel` từ Java 7 và `java.net.Socket.supportedOptions` từ Java 9.

## 15. Tài liệu Java chính thức

- [Java SE 17 — NetworkChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/NetworkChannel.html): `supportedOptions`, `getOption`, `setOption`, vòng đời channel và exceptions.
- [Java SE 17 — SocketOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketOption.html): generic type và `name()/type()`.
- [Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): các option chuẩn và ý nghĩa.
- [Java SE 17 — DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): supported options và UDP/multicast.
- [Java SE 17 — MulticastChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): gia nhập nhóm và membership.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): API option trực tiếp trên `java.net.Socket` từ Java 9.
- [Java SE 17 — jdk.net.Sockets](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/Sockets.html): thông tin API deprecated để tránh dùng cho code mới.

## 16. Tổng kết

`supportedOptions()` là công cụ khám phá **khả năng socket thực sự công bố trên đối tượng đang dùng**. Nó trả `Set<SocketOption<?>>` để chương trình kiểm tra đúng hằng của `StandardSocketOptions` và tránh yêu cầu tùy chọn không hợp kiểu hoặc không hỗ trợ. Với TCP, cần quan tâm tới các option như `TCP_NODELAY`; với UDP/multicast, phải phân biệt các option `IP_MULTICAST_IF`, `IP_MULTICAST_TTL` và `IP_MULTICAST_LOOP`. Kết quả có thể thay đổi theo socket type, provider, OS và JDK; extended option không phải hợp đồng chung cho mọi máy.

**Check supported không phải kết thúc quy trình**: phải kiểm tra kiểu và giá trị, gọi `setOption` đúng thời điểm, xử lý exceptions, đọc lại khi thích hợp và đo/test hành vi networking thật. Một UDP socket hỗ trợ TTL multicast chưa chứng minh join group hay truyền gói hoạt động; một TCP socket chấp nhận TCP_NODELAY chưa chứng minh cải thiện latency.

Bằng cách tách **khám phá capability → cấu hình an toàn → xác minh tác dụng → kiểm thử end-to-end**, ứng dụng Java giữ được tính khả chuyển mà không rơi vào giả định “mọi socket đều hỗ trợ mọi option” hoặc dùng các API đã deprecated.