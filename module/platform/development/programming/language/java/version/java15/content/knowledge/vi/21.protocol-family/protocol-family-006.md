# UnsupportedOperationException khi nền tảng không hỗ trợ protocol family (Java 15+)

## Mục tiêu bài học

Khi tạo socket/channel trong Java NIO, lập trình viên có thể chủ động chọn **họ giao thức** (*protocol family*). Ví dụ, `StandardProtocolFamily.INET` đại diện IPv4, `INET6` đại diện IPv6. Tuy nhiên, việc một enum hay overload API tồn tại trong JDK **không bảo đảm hệ điều hành, cấu hình mạng hoặc loại channel đang sử dụng hỗ trợ họ giao thức đó**.

Trong trường hợp được quy định bởi hợp đồng, lời gọi như:

```java
DatagramChannel.open(StandardProtocolFamily.INET6);
```

có thể ném **`UnsupportedOperationException`** nếu IPv6 không được hỗ trợ/không được bật trên nền tảng. Đây là một **exception runtime** mang ý nghĩa *khả năng được yêu cầu không được cung cấp*, không phải kết quả kết nối mạng thất bại tạm thời.

Bài học thuộc nhóm **Protocol family** trong Java 15 và làm rõ:

1. Khái niệm `ProtocolFamily`, `StandardProtocolFamily.INET`, `INET6`, `UNIX` và phạm vi các API NIO.
2. Khi nào `DatagramChannel.open(ProtocolFamily)` ném `UnsupportedOperationException`; vì sao `UNIX` không áp dụng cho datagram channel dù socket Unix-domain có thể tồn tại cho stream channel.
3. Cách phân biệt `UnsupportedOperationException`, `IOException`, `UnsupportedAddressTypeException` và lỗi socket option.
4. Cách xử lý tính năng tùy chọn một cách **có kiểm soát**, chỉ fallback IPv4 khi yêu cầu nghiệp vụ thật sự cho phép.
5. Cách kiểm thử có tính di động: không hardcode kết quả “IPv6 luôn có” hoặc “IPv6 luôn lỗi”.
6. Một ví dụ Java hoàn chỉnh, chạy trên **JDK 17+**, sử dụng public API và có stdout ổn định trong môi trường cho phép UDP loopback.

**Phạm vi kiến thức hiện hành:** `DatagramChannel.open(ProtocolFamily)` là API từ Java 7; `SocketChannel.open(ProtocolFamily)` và `ServerSocketChannel.open(ProtocolFamily)` có từ **Java 15**. `StandardProtocolFamily.UNIX` được bổ sung từ **Java 16**, và được dùng trong ví dụ JDK 17+ để tạo một ca không hỗ trợ rõ ràng. Những quy tắc được mô tả vẫn có hiệu lực trên các JDK hiện đại, không dựa vào API nội bộ/legacy.

## 1. ProtocolFamily là gì?

`java.net.ProtocolFamily` là interface mô tả một họ giao thức. Java cung cấp enum chuẩn `java.net.StandardProtocolFamily`:

| Giá trị | Ý nghĩa | Phạm vi thực tế |
| --- | --- | --- |
| `INET` | Internet Protocol Version 4 (IPv4) | Datagram UDP IPv4; socket TCP IPv4 |
| `INET6` | Internet Protocol Version 6 (IPv6) | Datagram UDP IPv6; socket TCP IPv6 khi nền tảng hỗ trợ |
| `UNIX` | Unix-domain / local interprocess communication | Socket **stream** qua `SocketChannel`/`ServerSocketChannel` từ Java 16 nếu nền tảng hỗ trợ; **không** được `DatagramChannel` hỗ trợ |

**Hai câu hỏi phải tách riêng:**

- **API/class có chấp nhận loại family này không?** Chẳng hạn `DatagramChannel` chỉ hỗ trợ datagram Internet protocol; Unix-domain sockets **không được hỗ trợ** bởi `DatagramChannel`.
- **Nền tảng hiện tại có hỗ trợ family mà API cho phép không?** Một môi trường có thể không có IPv6, bị cấu hình tắt IPv6, hoặc provider không mở được channel tương ứng.

Ngay cả khi đã mở channel được, kết nối tới một endpoint cụ thể còn tùy routing, bind address, firewall và trạng thái mạng. **Có thể mở family không đồng nghĩa có thể truyền dữ liệu tới mọi địa chỉ trong family ấy.**

### 1.1. Các overload liên quan

```java
DatagramChannel.open();
DatagramChannel.open(StandardProtocolFamily.INET);
DatagramChannel.open(StandardProtocolFamily.INET6);
```

- `open()` chọn protocol family phụ thuộc nền tảng/cấu hình; tài liệu nói **không xác định trước family** của socket được mở.
- `open(INET)` chủ động yêu cầu IPv4.
- `open(INET6)` chủ động yêu cầu IPv6 và có thể ném `UnsupportedOperationException` nếu family này không khả dụng.

Với UDP multicast, nên **chọn family phù hợp với loại địa chỉ của multicast group**. Không dùng một family “bất kỳ mở được” rồi kỳ vọng nó join được mọi nhóm IPv4/IPv6.

Trong Java 15, các lựa chọn family cho stream channel cũng được mở rộng:

```java
SocketChannel.open(StandardProtocolFamily.INET);
ServerSocketChannel.open(StandardProtocolFamily.INET6);
```

Các lệnh trên cũng có thể ném `UnsupportedOperationException` nếu family được yêu cầu không được hỗ trợ. Không nhầm chúng với UDP: `SocketChannel` là channel **stream-oriented** (thường dùng cho TCP/Unix-domain), còn `DatagramChannel` là **datagram-oriented**.

## 2. Chính xác khi nào UnsupportedOperationException xuất hiện?

Tài liệu chính thức của `DatagramChannel.open(ProtocolFamily)` ghi rõ:

- Ném **`UnsupportedOperationException`** nếu *specified protocol family is not supported*.
- Ví dụ do tài liệu đưa ra là `StandardProtocolFamily.INET6` nhưng IPv6 không được bật trên nền tảng.
- Có thể ném **`IOException`** khi phát sinh lỗi I/O độc lập với khái niệm family hỗ trợ.

`UnsupportedOperationException` kế thừa `RuntimeException`, do đó là **unchecked exception**. Dù chữ ký phương thức chỉ khai báo `throws IOException`, bạn vẫn phải xử lý trường hợp không hỗ trợ nếu yêu cầu khả năng đa nền tảng.

Ví dụ:

```java
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // Ở đây chỉ biết mở được channel IPv6.
    // Còn phải bind/connect/send/receive theo yêu cầu thật.
} catch (UnsupportedOperationException unsupportedIpv6) {
    // Môi trường/provider không hỗ trợ family IPv6 được yêu cầu.
}
```

Đoạn này là **mã minh họa trong phương thức có khai báo `throws IOException` hoặc bắt IOException riêng**. Trong nhánh catch không thể tự kết luận lỗi DNS, remote server không chạy, hay người dùng đã tắt firewall.

### 2.1. Không phải mọi exception liên quan đến network đều là unsupported family

| Exception | Thường xuất hiện ở đâu | Ý nghĩa cần phân biệt |
| --- | --- | --- |
| `UnsupportedOperationException` | `open(family)` với family không hỗ trợ, hoặc `setOption` với socket option không hỗ trợ | Yêu cầu khả năng mà channel/provider không cung cấp |
| `IOException` | `open`, `bind`, `connect`, `send`, `receive` | Lỗi I/O/hệ điều hành/tài nguyên hoặc mạng; **không mặc định** là family không được hỗ trợ |
| `UnsupportedAddressTypeException` | `bind/connect/send` với kiểu `SocketAddress` không được channel chấp nhận | Sai **kiểu địa chỉ endpoint**, không phải nhất thiết lỗi family ở lúc tạo channel |
| `UnresolvedAddressException` | `connect/send` với địa chỉ Inet chưa được resolve phù hợp | Địa chỉ đích chưa có địa chỉ IP cụ thể |
| `IllegalArgumentException` | Ví dụ giá trị socket option không hợp lệ | Tham số sai, không phải tính năng family thiếu |
| `ClosedChannelException` | Gọi I/O lên channel đã đóng | Vòng đời tài nguyên sai |
| `SecurityException` | Một thao tác bị từ chối bởi cơ chế kiểm soát phù hợp nếu áp dụng | Vấn đề quyền; không tương đương unsupported family |

Không dựa vào thông báo exception (*message*) như `"IPv6 not available"` hoặc tên lớp implementation để quyết định logic. Thông báo có thể khác giữa provider/JDK/OS. Sử dụng **loại exception**, thông tin family đã yêu cầu và ngữ cảnh thao tác.

### 2.2. Vì sao không catch IOException rồi tự động chuyển IPv4?

Ví dụ sai:

```java
// Mã minh họa anti-pattern, không nên dùng làm fallback chung.
try {
    return DatagramChannel.open(StandardProtocolFamily.INET6);
} catch (Exception anyProblem) {
    return DatagramChannel.open(StandardProtocolFamily.INET);
}
```

Lỗi:

- `IOException` có thể là cạn tài nguyên, lỗi hệ điều hành, lỗi cấu hình hoặc sự cố khác; fallback có thể **che giấu lỗi thực**.
- Chuyển từ IPv6 sang IPv4 thay đổi semantics địa chỉ và chính sách bảo mật. Nếu đích chỉ có IPv6 hoặc là nhóm multicast IPv6, fallback IPv4 không đáp ứng mục tiêu.
- Catch `Exception` quá rộng có thể bắt cả lỗi tham số/programming bug rồi giả vờ đó là “nền tảng không hỗ trợ”.

Cách đúng là **chỉ bắt trường hợp không hỗ trợ mà bạn muốn xử lý**, chỉ chuyển sang phương án khác khi **nghiệp vụ cho phép**, và để các lỗi I/O bất ngờ được xử lý/ghi nhận đúng.

## 3. Trường hợp chắc chắn không phù hợp: UNIX với DatagramChannel

Từ **Java 16**, `StandardProtocolFamily.UNIX` mô tả Unix-domain socket để giao tiếp nội bộ giữa tiến trình, không qua IP. Tuy nhiên, API note của `DatagramChannel.open(ProtocolFamily)` nói rõ **Unix domain sockets are not supported**.

Vì vậy, với JDK 17+ và provider NIO chuẩn:

```java
try (DatagramChannel unused =
        DatagramChannel.open(StandardProtocolFamily.UNIX)) {
    // Không phải cách tạo Unix-domain datagram.
} catch (UnsupportedOperationException expected) {
    System.out.println("DatagramChannel khong ho tro UNIX");
}
```

Đây là một **negative test tốt**, vì không cần cố tắt IPv6 của OS để tạo lỗi. Nó kiểm tra **family không phù hợp với loại channel**, chứ không chứng minh hệ điều hành không hỗ trợ mọi loại Unix-domain socket.

### 3.1. UNIX có thể dùng cho stream socket, không phải DatagramChannel

Khi môi trường hỗ trợ và sử dụng Java 16+, các API:

```java
SocketChannel.open(StandardProtocolFamily.UNIX);
ServerSocketChannel.open(StandardProtocolFamily.UNIX);
```

có thể mở **Unix-domain stream channel**. Kết quả còn phụ thuộc vào hỗ trợ của hệ điều hành/provider, nên cần xử lý `UnsupportedOperationException` khi không được hỗ trợ.

Một class hoặc enum constant `UNIX` xuất hiện trong JDK **không có nghĩa mọi loại socket đều dùng được nó**. Không được “chữa” lỗi `DatagramChannel.open(UNIX)` bằng cách chuyển sang `DatagramChannel.open(INET)`: đó là chuyển từ **local IPC** sang mạng IP, làm thay đổi mô hình địa chỉ, quyền và truyền thông.

Cũng đừng cho rằng `SocketChannel.socket()` trên Unix-domain channel luôn trả một `java.net.Socket` kiểu IP; API này có điều kiện và có thể ném `UnsupportedOperationException` khi channel không phải Internet protocol socket. Hãy dùng chính `SocketChannel` khi đã chọn UNIX.

**Chú ý phiên bản Java:** `UNIX` là điểm bổ sung của **Java 16**, không có trong StandardProtocolFamily của Java 15. Bài minh họa dùng `javac --release 17` nên hợp lệ; muốn biên dịch phần UDP thuần cho Java 15, chỉ dùng các family/API có ở release 15.

## 4. Khả năng hỗ trợ là thuộc tính của môi trường chạy, không phải của mã nguồn

Một ứng dụng có thể:

- Biên dịch trên JDK có `StandardProtocolFamily.INET6`.
- Chạy trên máy có IPv6 hỗ trợ đầy đủ; `DatagramChannel.open(INET6)` thành công.
- Chạy ở container hoặc cấu hình OS/provider không hỗ trợ IPv6; cùng lời gọi có thể ném `UnsupportedOperationException`.

**Biên dịch thành công không chứng minh hỗ trợ lúc chạy.** Sự tồn tại của enum `INET6` cũng không phải một “feature flag” báo IPv6 bật.

Tương tự, điều kiện:

```java
InetAddress address = InetAddress.getByName("::1");
```

không phải phép thử đầy đủ cho việc socket IPv6 có thể **bind/communicate** theo yêu cầu. Chuyển chuỗi địa chỉ thành một object có thể làm được trong khi network stack/container vẫn không cho phép thao tác socket đó.

Cần kiểm thử đúng thao tác mà ứng dụng yêu cầu:

- **Chỉ cần biết mở được channel?** Thử `DatagramChannel.open(INET6)`.
- **Cần listen trên IPv6 loopback?** Thử bind đến `::1` bằng channel phù hợp.
- **Cần truy cập đích IPv6 từ xa?** Kiểm tra DNS/địa chỉ, route, firewall, send/receive hoặc giao thức ứng dụng.
- **Cần IPv6 multicast?** Kiểm tra family, địa chỉ nhóm, interface, quyền join group và hỗ trợ multicast thực tế.

Đừng gộp tất cả thành một boolean “IPv6 supported” duy nhất nếu ứng dụng cần nhiều khả năng khác nhau.

## 5. Thiết kế fallback IPv6 → IPv4 an toàn

Fallback chỉ hợp lý nếu **yêu cầu chấp nhận cả IPv6 và IPv4**. Ví dụ dịch vụ có cả A/AAAA record, cho phép truyền UDP qua cả hai; ứng dụng chọn cách khả dụng theo chính sách. Ngược lại, một multicast group IPv6 hoặc endpoint chỉ có AAAA record **không thể chuyển sang IPv4** chỉ vì channel IPv6 không mở được.

Một phương án đơn giản:

1. Xác định family mong muốn và family thay thế **được phép bởi nghiệp vụ** trước khi mở.
2. Gọi `DatagramChannel.open(preferred)`.
3. Nếu `UnsupportedOperationException` và policy có cho phép fallback: thử `DatagramChannel.open(alternative)`.
4. Nếu `IOException`, để lỗi được xử lý như I/O failure; **không coi nó là bằng chứng family không được hỗ trợ**.
5. Ghi nhớ family đã chọn theo nhánh của chính code (vì `DatagramChannel` không cung cấp một phương thức public đơn giản `getProtocolFamily()` để bạn giả định dùng).
6. Sử dụng địa chỉ đích và multicast group **tương thích với family được chọn**; không dùng IPv6-only address với channel IPv4.
7. Đóng những channel đã mở bằng `try-with-resources`.

Để thể hiện chính sách rõ ràng, một helper có thể trả cả channel và family đã được chọn:

```java
private static final class OpenedUdp implements AutoCloseable {
    final DatagramChannel channel;
    final StandardProtocolFamily chosenFamily;

    OpenedUdp(DatagramChannel channel, StandardProtocolFamily chosenFamily) {
        this.channel = channel;
        this.chosenFamily = chosenFamily;
    }

    public void close() throws IOException {
        channel.close();
    }
}
```

Đây là **trích đoạn class lồng**, cần imports và context; chương trình hoàn chỉnh phía dưới sử dụng nó trong một class có thể biên dịch trực tiếp.

### 5.1. Cẩn thận không hạ cấp giao thức một cách im lặng

Không phải mọi fallback đều là tương đương:

| Mục tiêu gốc | Fallback IPv4 có hợp lệ? | Lý do |
| --- | --- | --- |
| Dịch vụ UDP có endpoint IPv4 **và** IPv6 được phép | Có thể | Cần chọn đúng địa chỉ IPv4 và bảo toàn policy |
| IPv6 multicast group cố định | Không | Group IPv6 không phải group IPv4 |
| Endpoint chỉ hỗ trợ IPv6 | Không | Không có đích IPv4 tương đương |
| Unix-domain IPC qua filesystem path | Không | IP/UDP khác hoàn toàn local socket semantics |
| Hệ thống yêu cầu bind `::1` | Không | Loopback IPv4 `127.0.0.1` không thay thế trực tiếp `::1` |
| Hệ thống có quy tắc mã hóa/xác thực theo từng transport | Tùy chính sách | Không được fallback làm thay đổi điều kiện bảo mật |

**Một thông điệp “unsupported family” tốt hơn một fallback âm thầm trái policy.**

## 6. Phân biệt chọn protocol family và socket option

Ngoài `open(family)`, các network channel có phương thức:

```java
channel.supportedOptions();
channel.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
channel.getOption(StandardSocketOptions.SO_RCVBUF);
```

Những lời gọi trên là **mã minh họa**, giả định `channel` là một đối tượng `NetworkChannel` phù hợp và đã được mở.

Theo Java API, `setOption`/`getOption` cũng có thể ném **`UnsupportedOperationException`** khi option đó không được channel hỗ trợ. Vì vậy trong log phải xác định **thao tác nào ném lỗi**:

- `DatagramChannel.open(INET6)` không hỗ trợ: vấn đề family.
- `channel.setOption(option, value)` không hỗ trợ: vấn đề option.
- `channel.bind(address)` sai loại địa chỉ: có thể là `UnsupportedAddressTypeException`.
- `channel.setOption(option, invalidValue)`: có thể là `IllegalArgumentException`.

Không dùng một catch `UnsupportedOperationException` bao quanh toàn bộ quá trình khởi tạo rồi kết luận tất cả đều do IPv6 bị tắt. Ghi rõ pha `OPEN_FAMILY`, `SET_OPTION`, `BIND`, `CONNECT` trong xử lý lỗi/telemetry.

### 6.1. Feature detection qua supportedOptions

`supportedOptions()` công bố tập `SocketOption<?>` được channel hỗ trợ. Ví dụ:

```java
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    if (channel.supportedOptions()
            .contains(StandardSocketOptions.SO_RCVBUF)) {
        int size = channel.getOption(StandardSocketOptions.SO_RCVBUF);
        System.out.println(size > 0);
    }
}
```

Điều này không có nghĩa `supportedOptions()` là API liệt kê tất cả *protocol family* của máy. Nó liệt kê **socket option của channel đã mở**. Không giả lập “IPv6 supported” từ việc `SO_RCVBUF` có mặt.

Giá trị buffer do OS quản lý có thể khác mức yêu cầu; đừng viết test đòi kết quả chính xác 64 KiB sau khi `setOption`. Kiểm tra invariants và mức phù hợp với use case.

## 7. Ví dụ Java hoàn chỉnh: phát hiện và xử lý unsupported family

Chương trình dưới đây sử dụng các public API đang được hỗ trợ:

- Mở hai `DatagramChannel` **IPv4** trên loopback `127.0.0.1` để kiểm tra gửi/nhận.
- Kiểm tra các socket option tiêu chuẩn của UDP qua `supportedOptions`.
- Cố mở `DatagramChannel.open(UNIX)` để tạo nhánh `UnsupportedOperationException` **không phụ thuộc vào việc IPv6 hiện đang bật hay tắt**.
- Thử ưu tiên `INET6` nhưng nếu family không được hỗ trợ thì chọn `INET` **theo policy đã cho phép fallback**, ghi nhớ family đã chọn.
- Chứng minh policy không bao giờ chuyển `UNIX` sang IP một cách âm thầm.

**Giới hạn kiểm thử:** Chương trình cần môi trường cho phép UDP IPv4 loopback. Nếu sandbox/CI chặn tạo network socket, nó có thể thất bại do quyền hoặc I/O; điều đó khác với việc family không được hỗ trợ. Ở môi trường bình thường có loopback, cả chín dòng PASS đều ổn định.

### 7.1. Tệp nguồn đầy đủ

Lưu tệp **`ProtocolFamilySupportDemo.java`** bằng UTF-8:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public final class ProtocolFamilySupportDemo {
    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label + " FAILED");
        }
        System.out.println(label + "=PASS");
    }

    private static final class OpenedUdp implements AutoCloseable {
        final DatagramChannel channel;
        final StandardProtocolFamily chosenFamily;

        OpenedUdp(DatagramChannel channel,
                  StandardProtocolFamily chosenFamily) {
            this.channel = channel;
            this.chosenFamily = chosenFamily;
        }

        @Override
        public void close() throws IOException {
            channel.close();
        }
    }

    private static OpenedUdp openPreferred(
            boolean preferIpv6, boolean permitIpv4Fallback) throws IOException {
        if (!preferIpv6) {
            return new OpenedUdp(
                    DatagramChannel.open(StandardProtocolFamily.INET),
                    StandardProtocolFamily.INET);
        }
        try {
            return new OpenedUdp(
                    DatagramChannel.open(StandardProtocolFamily.INET6),
                    StandardProtocolFamily.INET6);
        } catch (UnsupportedOperationException unsupported) {
            if (!permitIpv4Fallback) {
                throw unsupported;
            }
            return new OpenedUdp(
                    DatagramChannel.open(StandardProtocolFamily.INET),
                    StandardProtocolFamily.INET);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            check("unconnectedByDefault",
                    !receiver.isConnected() && !sender.isConnected());

            receiver.bind(new InetSocketAddress(loopback, 0));
            sender.bind(new InetSocketAddress(loopback, 0));

            ByteBuffer data = StandardCharsets.UTF_8.encode("PING");
            int sent = sender.send(data, receiver.getLocalAddress());

            ByteBuffer received = ByteBuffer.allocate(32);
            SocketAddress from = receiver.receive(received);
            received.flip();

            check("inetUdpExchange",
                    sent == 4
                            && from instanceof InetSocketAddress
                            && StandardCharsets.UTF_8.decode(received)
                                    .toString().equals("PING"));

            check("standardReceiveOption",
                    receiver.supportedOptions()
                            .contains(StandardSocketOptions.SO_RCVBUF));
            check("receiveBufferPositive",
                    receiver.getOption(StandardSocketOptions.SO_RCVBUF) > 0);
        }

        boolean unixDatagramRejected = false;
        try (DatagramChannel unused =
                     DatagramChannel.open(StandardProtocolFamily.UNIX)) {
            // A DatagramChannel does not support Unix-domain datagrams.
        } catch (UnsupportedOperationException expected) {
            unixDatagramRejected = true;
        }
        check("unixDatagramRejected", unixDatagramRejected);

        try (OpenedUdp chosen = openPreferred(true, true)) {
            check("negotiatedFamilyKnown",
                    chosen.chosenFamily == StandardProtocolFamily.INET
                            || chosen.chosenFamily == StandardProtocolFamily.INET6);
            check("preferredChannelOpen", chosen.channel.isOpen());
        }

        try (OpenedUdp ipv4Only = openPreferred(false, false)) {
            check("explicitInetChoice",
                    ipv4Only.chosenFamily == StandardProtocolFamily.INET);
        }

        boolean noSilentUnixFallback = false;
        try (DatagramChannel unused =
                     DatagramChannel.open(StandardProtocolFamily.UNIX)) {
            // Do not silently substitute IP for a Unix-domain requirement.
        } catch (UnsupportedOperationException expected) {
            noSilentUnixFallback = true;
        }
        check("noSilentUnixFallback", noSilentUnixFallback);
    }
}
```

### 7.2. Biên dịch và chạy

Với **JDK 17 hoặc mới hơn**:

```bash
javac --release 17 -encoding UTF-8 ProtocolFamilySupportDemo.java
java ProtocolFamilySupportDemo
```

**Stdout chính xác trong môi trường cho phép UDP IPv4 loopback:**

```text
unconnectedByDefault=PASS
inetUdpExchange=PASS
standardReceiveOption=PASS
receiveBufferPositive=PASS
unixDatagramRejected=PASS
negotiatedFamilyKnown=PASS
preferredChannelOpen=PASS
explicitInetChoice=PASS
noSilentUnixFallback=PASS
```

Chương trình **không in** `"IPv6 supported"` hoặc `"IPv6 unsupported"` dưới dạng một expected value cố định vì thông tin đó phụ thuộc nền tảng. Nó chỉ xác nhận rằng đường chọn IPv6 hoặc IPv4 theo policy đưa đến một channel đã mở, và **family đã chọn được theo dõi rõ ràng**.

### 7.3. Giải thích 9 kết quả

| Kết quả | Ý nghĩa |
| --- | --- |
| `unconnectedByDefault=PASS` | `DatagramChannel.open(INET)` tạo channel UDP ban đầu chưa connect |
| `inetUdpExchange=PASS` | Hai channel IPv4 trao đổi một datagram `PING` qua loopback và giải mã đúng `ByteBuffer` sau `flip()` |
| `standardReceiveOption=PASS` | `SO_RCVBUF` được công bố qua public `supportedOptions` của IP datagram channel |
| `receiveBufferPositive=PASS` | `getOption(SO_RCVBUF)` trả kích thước dương, không hardcode giá trị cụ thể |
| `unixDatagramRejected=PASS` | `DatagramChannel.open(UNIX)` bị từ chối bằng `UnsupportedOperationException` đúng hợp đồng của loại channel |
| `negotiatedFamilyKnown=PASS` | Helper giữ một trong hai family được chính sách cho phép là `INET6` hoặc `INET` |
| `preferredChannelOpen=PASS` | Sau nhánh chọn family, channel được trả về đang mở |
| `explicitInetChoice=PASS` | Khi không yêu cầu IPv6, helper chọn IPv4 trực tiếp |
| `noSilentUnixFallback=PASS` | Yêu cầu Unix-domain datagram không bị tự động đổi sang giao thức IP |

Ví dụ này **không kiểm tra tốc độ, chất lượng route IPv6 hoặc khả năng multicast**. Nếu ứng dụng yêu cầu các tính năng đó, hãy bổ sung integration test ở đúng môi trường.

## 8. Tại sao không dùng open() mặc định để thay fallback?

Một anti-pattern khác:

```java
// Không đáng tin để thay yêu cầu "phải có IPv4".
DatagramChannel channel = DatagramChannel.open();
```

Tài liệu `DatagramChannel.open()` nói family của socket mới là **platform/configuration dependent and unspecified**. Do đó:

- Không bảo đảm luôn là `INET` hay `INET6` đúng như bạn mong muốn.
- Với **multicast**, nên mở channel theo family tương ứng của nhóm multicast.
- Nếu một module khác trong code giả định IPv4, hãy chọn `open(StandardProtocolFamily.INET)` và làm việc với `Inet4Address`/địa chỉ IPv4 phù hợp.
- Nếu ứng dụng cần cả hai family, thiết kế chọn family và địa chỉ đi kèm, không suy luận từ implementation hay system property.

Điều này cũng cho thấy **API công khai** phù hợp hơn cách soi `sun.nio.ch.*` để đoán OS đã chọn family nào. Hãy nắm quyền lựa chọn từ chính lời gọi khởi tạo và giữ thông tin trong cấu trúc ứng dụng.

## 9. IPv6 multicast và fallback có thể gây lỗi logic

Với UDP multicast, họ giao thức của channel phải tương thích với nhóm địa chỉ được join. Ví dụ:

- Multicast IPv4 dùng group thuộc dải IPv4 multicast và interface tương ứng.
- Multicast IPv6 dùng group thuộc IPv6 multicast và interface hỗ trợ IPv6.
- `DatagramChannel.open(INET6)` chưa đủ chứng minh máy có thể join group: còn cần interface, route, multicast capability và quyền tương ứng.

Đừng làm thế này:

```java
// Anti-pattern: giả định chấp nhận thay UDP IPv6 multicast bằng IPv4.
try {
    channel = DatagramChannel.open(StandardProtocolFamily.INET6);
} catch (UnsupportedOperationException ex) {
    channel = DatagramChannel.open(StandardProtocolFamily.INET);
}
// Sau đó vẫn cố join một IPv6 multicast group: không đúng.
```

Trích đoạn trên thiếu khai báo biến `channel` và chỉ minh họa lỗi logic. Trong code thật, nếu protocol **bắt buộc IPv6 multicast**, hãy trả lỗi cấu hình/không hỗ trợ với thông báo rõ ràng; **không fallback** thành một channel vốn không thể tham gia nhóm đó.

## 10. Không nhầm IPv6 không hỗ trợ với IPv6 không truy cập được

Một test probe `open(INET6)` có thể thành công, nhưng thao tác tiếp theo vẫn thất bại:

- `bind` đến địa chỉ không được gán cho máy có thể gây lỗi I/O.
- `connect/send` tới remote có thể lỗi route, firewall hoặc address type.
- `receive` có thể không nhận được datagram vì UDP không bảo đảm giao hàng.
- Với non-blocking channel, `receive` có thể trả `null` khi chưa có packet.
- Group multicast có thể không join được vì interface/OS không hỗ trợ multicast.

Đó là các **bước khác nhau**, không tự động trở thành `UnsupportedOperationException` khi tạo family. Nếu mở được channel rồi lại bắt mọi lỗi mạng bằng nhánh “fallback IPv4 vì IPv6 unsupported”, hệ thống có nguy cơ che mất nguyên nhân thật.

Một thiết kế tốt nên phân loại các pha:

```text
SELECT_FAMILY
    |
    v
OPEN_CHANNEL           <- UnsupportedOperationException: family không hỗ trợ
    |
    v
CONFIGURE_OPTIONS      <- UnsupportedOperationException: option không hỗ trợ
    |
    v
BIND/CONNECT           <- IOException / UnsupportedAddressTypeException / ...
    |
    v
SEND/RECEIVE           <- IOException / thời gian chờ / packet loss / ...
    |
    v
VALIDATE_APPLICATION   <- kiểm tra payload, peer, retry, authentication
```

Những gì API có thể phân biệt được thì log/telemetry cũng nên phân biệt để QA và vận hành xác định đúng lớp lỗi.

## 11. Test đa môi trường như thế nào?

Các trường hợp nên có trong CI/integration test:

| Môi trường/đầu vào | Điều kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Máy có IPv4 loopback | `DatagramChannel.open(INET)`, bind và trao đổi UDP | Thành công nếu môi trường cho phép |
| Nền tảng có IPv6 | `open(INET6)`, bind/route tới IPv6 endpoint phù hợp | Thành công khi khả năng thực sự hiện diện |
| Nền tảng không bật IPv6 | `open(INET6)` | Xử lý `UnsupportedOperationException` theo API và policy |
| `DatagramChannel.open(UNIX)` trên JDK 17+ | Family không phù hợp loại channel | `UnsupportedOperationException` |
| `SocketChannel.open(UNIX)` trên JDK 17+ | Stream Unix-domain socket | Có thể thành công nếu được hỗ trợ; không coi là UDP |
| `setOption` với option không hỗ trợ | Phân biệt lỗi option và family | `UnsupportedOperationException` đúng pha |
| `bind/connect/send` với địa chỉ sai loại | Kiểm tra address/family mismatch | Không nhầm với lỗi mở family |
| Không đủ tài nguyên OS hoặc quyền mạng | Có thể lỗi `IOException` hoặc lỗi quyền | Không fallback âm thầm, ghi đúng lỗi |
| Cấu hình bắt buộc IPv6 | `INET6` không được hỗ trợ | Fail fast, không chuyển sang `INET` |
| Cấu hình cho phép dual stack và có endpoint IPv4 | `INET6` không hỗ trợ | Cho phép fallback nếu policy và địa chỉ phù hợp |

**Không ép CI phải tạo một máy thiếu IPv6 bằng cách can thiệp system property hoặc thay đổi cấu hình hệ thống tùy tiện**. Có thể viết unit test cho helper chọn family bằng cách tách phần mở channel ra một interface/factory và giả lập nhánh `UnsupportedOperationException`, rồi dùng integration test trên môi trường thực để xác minh khả năng network.

Test không nên phụ thuộc thông báo exception hoặc tên lớp provider. Chỉ kiểm tra kiểu lỗi, yêu cầu family và các hành vi public mà Java cam kết.

## 12. Những sai lầm phổ biến

| Sai lầm | Vì sao không đúng | Cách khắc phục |
| --- | --- | --- |
| Thấy `INET6` trong enum nên nghĩ IPv6 luôn hoạt động | Compile-time khác runtime capability | Thử `open(INET6)`, rồi kiểm tra bind/route cần thiết |
| Bắt `IOException` và ghi “IPv6 not supported” | Có thể là I/O, tài nguyên hoặc OS lỗi | Phân biệt `IOException` và `UnsupportedOperationException` |
| Catch `Exception` rồi fallback IPv4 | Che lỗi và thay đổi semantics | Bắt chính xác lỗi, chỉ fallback khi policy cho phép |
| Dùng `DatagramChannel.open()` khi bắt buộc IPv4 | Family mặc định không được quy định | Dùng `open(INET)` |
| Dùng `DatagramChannel.open(UNIX)` để tạo local datagram | DatagramChannel không hỗ trợ UNIX | Chọn API/giao thức phù hợp, không giả vờ IP tương đương |
| Nghĩ `SocketChannel.open(UNIX)` có từ Java 15 | Enum `UNIX` chỉ từ Java 16 | Ghi rõ mức Java yêu cầu |
| Nghĩ unsupported option = unsupported family | Cùng exception nhưng xảy ra ở pha khác | Kiểm tra operation phát sinh lỗi |
| Gọi `setOption` mà không xem supportedOptions | Option có thể không được hỗ trợ | Dùng `supportedOptions()`, xử lý lỗi thích hợp |
| Dùng IPv4 fallback cho IPv6-only endpoint | Không thể liên lạc đúng đích | Fail fast hoặc thay protocol endpoint theo policy |
| Tìm cách bật family bằng reflection vào JDK internals | Không ổn định, không được API hỗ trợ | Dùng public API và cấu hình môi trường mạng đúng |
| Quên đóng channel sau probe | Rò socket/file descriptor | `try-with-resources` |
| Chỉ thử `open(INET6)` rồi tuyên bố IPv6 multicast hoạt động | Chưa kiểm tra interface/group/route | Thêm integration test thực |
| Hardcode “IPv6 unavailable” làm stdout trên mọi OS | Máy khác có thể mở IPv6 được | Viết test chấp nhận hai khả năng, log feature outcome riêng |
| Cho rằng UOE ở `SocketChannel.socket()` nghĩa là UNIX stream channel không mở được | Method `socket()` không áp dụng cho mọi loại channel | Sử dụng channel API, phân biệt thao tác public |

## 13. Bài tập tự kiểm tra

**Bài 1.** Tại sao `DatagramChannel.open(StandardProtocolFamily.INET6)` có thể ném `UnsupportedOperationException` dù code compile thành công?

**Đáp án:** Sự hiện diện của enum và API không bảo đảm runtime/provider/OS hỗ trợ IPv6; `open(family)` được tài liệu quy định ném exception khi family không được hỗ trợ.

**Bài 2.** `DatagramChannel.open(UNIX)` lỗi trên JDK 17. Có phải điều đó chứng minh OS không hỗ trợ **bất kỳ** Unix-domain socket nào?

**Đáp án:** Không. `DatagramChannel` không hỗ trợ Unix-domain datagram theo contract, nhưng `SocketChannel`/`ServerSocketChannel` có thể hỗ trợ UNIX stream sockets nếu platform cho phép.

**Bài 3.** Khi `open(INET6)` ném `IOException`, có thể mặc định catch và gọi `open(INET)` như một cách sửa không?

**Đáp án:** Không. `IOException` có thể là lỗi tài nguyên/hệ điều hành. Fallback chỉ nên do policy cho phép và phải phân biệt lỗi thực; `UnsupportedOperationException` mới là tín hiệu rõ cho thiếu family tại `open`.

**Bài 4.** Một ứng dụng phải join multicast group IPv6. Máy không hỗ trợ `INET6`. Có được dùng `INET` thay không?

**Đáp án:** Không. Multicast group IPv6 không tương thích với IPv4. Phải báo không hỗ trợ hoặc thay thiết kế yêu cầu mạng.

**Bài 5.** `channel.setOption(...)` ném `UnsupportedOperationException`. Có thể kết luận IPv6 không được hỗ trợ không?

**Đáp án:** Không. Đây có thể là option không được channel hỗ trợ. Kiểm tra `supportedOptions()` và pha thao tác; không gộp lỗi option thành lỗi family.

**Bài 6.** Vì sao cần giữ giá trị `chosenFamily` trong helper fallback thay vì chỉ trả về `DatagramChannel`?

**Đáp án:** Để ứng dụng biết chính sách đã chọn IPv4 hay IPv6, tạo địa chỉ đích và cấu hình multicast phù hợp, đồng thời không suy đoán implementation bên trong channel.

**Bài 7.** `DatagramChannel.open(INET6)` thành công nhưng `send` không tới được một remote IPv6. Điều này có mâu thuẫn không?

**Đáp án:** Không. Mở channel và khả năng kết nối/route tới remote cụ thể là hai tầng điều kiện khác nhau. Xử lý lỗi của từng thao tác.

## Ghi nhớ

**`UnsupportedOperationException` tại `open(ProtocolFamily)` là dấu hiệu family được yêu cầu không được channel/provider/nền tảng hỗ trợ**, không phải mọi lỗi network. Với `DatagramChannel`, `INET6` có thể không khả dụng trên một hệ thống; `UNIX` **không được hỗ trợ cho datagram** dù có hỗ trợ Unix-domain **stream** sockets từ Java 16. Hãy chọn family tường minh, kiểm tra đúng thao tác, chỉ fallback khi semantics và policy cho phép, và giữ riêng xử lý `IOException`, lỗi địa chỉ, lỗi socket option. Những nguyên tắc này tiếp tục áp dụng trên các JDK hiện đại.

### Tài liệu Java chính thức đang áp dụng

- [Java SE 17 — DatagramChannel.open(ProtocolFamily), UnsupportedOperationException và Unix-domain note](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Java SE 17 — StandardProtocolFamily: INET, INET6, UNIX](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [Java SE 17 — SocketChannel.open(ProtocolFamily)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — ServerSocketChannel.open(ProtocolFamily)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java SE 17 — NetworkChannel.supportedOptions và setOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/NetworkChannel.html)
- [OpenJDK JEP 380 — Unix-Domain Socket Channels (Java 16)](https://openjdk.org/jeps/380)
