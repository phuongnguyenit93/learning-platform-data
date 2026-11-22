# Kiểm thử IPv4, IPv6 và họ giao thức không hỗ trợ trong Java

## 1. Mục tiêu của phép kiểm thử

Khi một ứng dụng Java dùng TCP/UDP, câu hỏi “máy có hỗ trợ mạng không?” chưa đủ. Một runtime có thể phân giải được chuỗi địa chỉ IPv6 nhưng không mở được socket IPv6; một máy có IPv6 nhưng service chỉ bind IPv4; hoặc một loại **protocol family** được Java biểu diễn bằng enum nhưng không được API socket đang dùng hỗ trợ.

Sau bài này, bạn cần có khả năng:

1. Phân biệt **địa chỉ IPv4**, **địa chỉ IPv6**, **họ giao thức của socket**, và **giao thức vận chuyển TCP/UDP**.
2. Thiết kế kiểm thử độc lập: **parse địa chỉ → tạo socket đúng family → bind → gửi/nhận dữ liệu → kiểm tra lỗi**.
3. Xác minh hành vi trên **JDK + hệ điều hành + cấu hình JVM thực tế**, không suy luận kết quả chỉ vì Java có lớp API tương ứng.
4. Kiểm tra đúng tình huống **family không hỗ trợ** (`UnsupportedOperationException`) và phân biệt nó với địa chỉ không phù hợp, lỗi bind hoặc timeout.
5. Ghi nhận **PASS, FAIL, SKIP có điều kiện** sao cho CI không che giấu một yêu cầu IPv6 bắt buộc.

Các API `InetAddress`, `Inet4Address`, `Inet6Address`, `StandardProtocolFamily`, `DatagramSocket`, `DatagramChannel` và cách cấu hình `java.net` dưới đây còn được hỗ trợ trong các JDK hiện đại. Ví dụ chạy bằng **Java 17+** và có thể kiểm tra trên JDK 21; nội dung không dựa vào API nội bộ của JDK.

## 2. Bốn khái niệm thường bị nhầm

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **IPv4 address** | `127.0.0.1` | Địa chỉ IP 32 bit; `InetAddress` trả về `Inet4Address` khi phân giải literal hợp lệ. |
| **IPv6 address** | `::1` | Địa chỉ IP 128 bit; tương ứng `Inet6Address`. |
| **Protocol family** | `StandardProtocolFamily.INET`, `INET6`, `UNIX` | Chọn họ địa chỉ/socket cho API có nhận `ProtocolFamily`. `INET` dành cho IPv4, `INET6` dành cho IPv6. |
| **Transport protocol** | TCP hoặc UDP | Xác định cơ chế truyền. `SocketChannel` dùng TCP, `DatagramChannel` dùng UDP; family không thay TCP thành UDP. |

Hai địa chỉ loopback dùng trong bài:

- `127.0.0.1`: IPv4 loopback, gói quay lại chính máy.
- `::1`: IPv6 loopback, cũng quay lại chính máy, **nếu hệ điều hành/JVM cho phép sử dụng socket IPv6**.

Đừng đồng nhất `localhost` với một địa chỉ duy nhất: tùy hệ điều hành, resolver, cấu hình JVM và `/etc/hosts`, `localhost` có thể ánh xạ tới IPv4, IPv6 hoặc cả hai. Muốn kiểm tra từng họ riêng biệt, dùng literal `127.0.0.1` và `::1` để loại biến số DNS.

`0.0.0.0` và `::` là **địa chỉ wildcard khi bind** (lắng nghe trên những interface phù hợp); không dùng chúng như địa chỉ máy chủ đích trong giao thức ứng dụng. Với URL/URI, IPv6 literal có cổng thường phải đặt trong dấu ngoặc vuông, ví dụ `http://[::1]:8080/`. Dấu ngoặc vuông này là cú pháp URI, không phải một phần của các byte địa chỉ IP.

**Một sự thật quan trọng:** `InetAddress.getByName("::1")` có thể tạo được `Inet6Address` ngay cả khi máy **không mở được socket IPv6**. Parse địa chỉ thành công chỉ kiểm tra cú pháp/biểu diễn; nó chưa kiểm tra năng lực của network stack.

## 3. Đặt hợp đồng kiểm thử trước khi viết code

Thay vì một phép thử chỉ kiểm tra `instanceof Inet6Address`, hãy tách các lớp bằng chứng:

| Test ID | Điều kiện | Hành động | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| T1 — IPv4 parse | JDK có Java networking API | Parse `127.0.0.1` | `Inet4Address`, không cần kết nối mạng. |
| T2 — IPv6 parse | JDK có Java networking API | Parse `::1` | `Inet6Address`; không suy ra OS hỗ trợ IPv6. |
| T3 — IPv4 bind | IPv4 loopback khả dụng | `DatagramChannel.open(INET)` và bind loopback/cổng `0` | Socket được tạo, bind thành công. |
| T4 — IPv4 UDP round trip | IPv4 loopback khả dụng | Gửi `PING` tới socket nhận trên chính máy | Nhận đúng 4 byte UTF-8 và đúng địa chỉ nguồn. |
| T5 — IPv6 bind | IPv6 là năng lực được yêu cầu **hoặc tùy chọn** | `DatagramChannel.open(INET6)` và bind `::1` | PASS khi khả dụng; phân loại lỗi theo yêu cầu môi trường. |
| T6 — IPv6 UDP round trip | T5 đã thành công | Gửi/nhận gói `PING` qua `::1` | Nhận đúng payload; nếu lỗi, không giả định chỉ vì IPv6 bind được là có giao tiếp. |
| T7 — Family không hỗ trợ | JDK 17+ | `DatagramChannel.open(UNIX)` | `UnsupportedOperationException` đối với Unix-domain datagram theo API hiện hành. |

Ở T3/T5, cổng `0` yêu cầu hệ điều hành tự chọn một **cổng tạm** đang khả dụng, giảm xung đột với tiến trình khác. Ở T4/T6, phép thử vẫn đặt **timeout**; test network không nên treo vô hạn.

T7 là một **negative test**: phép thử PASS chính khi API từ chối một family không được hỗ trợ. Khác với T5, đây không phải trường hợp “môi trường thiếu IPv6”. `UNIX` là họ địa chỉ dành cho Unix-domain sockets; Java có thể hỗ trợ loại socket này qua **stream** `SocketChannel`/`ServerSocketChannel` trên nền tảng phù hợp, nhưng `DatagramChannel` không hỗ trợ **Unix-domain datagram**. Không suy diễn “UNIX bị Java loại bỏ hoàn toàn”.

## 4. Các API và ngoại lệ cần hiểu

### 4.1. Parse và phân loại địa chỉ

```java
InetAddress v4 = InetAddress.getByName("127.0.0.1");
InetAddress v6 = InetAddress.getByName("::1");

boolean isIPv4 = v4 instanceof Inet4Address;
boolean isIPv6 = v6 instanceof Inet6Address;
```

Đoạn trên là **trích đoạn minh họa**, chưa phải file chạy độc lập; các import và chương trình hoàn chỉnh xuất hiện ở phần sau. `getByName` nhận IP literal thì không cần lấy bản ghi DNS để biết địa chỉ; trái lại, khi gọi `getByName("example.com")` hoặc `getAllByName(...)`, kết quả phụ thuộc resolver/DNS, cache và chính sách ưu tiên địa chỉ.

Không kiểm tra IPv4/IPv6 bằng độ dài của chuỗi `getHostAddress()`: IPv6 có cách viết rút gọn, có thể có phạm vi (*scope*) và có những biểu diễn tương đương. Sử dụng `Inet4Address`/`Inet6Address` hoặc độ dài `getAddress()` (4/16 byte) theo nhu cầu.

### 4.2. Tạo socket gắn với family

```java
try (DatagramChannel channel =
         DatagramChannel.open(StandardProtocolFamily.INET6)) {
    channel.bind(new InetSocketAddress(
            InetAddress.getByName("::1"), 0));
}
```

Đây cũng là **trích đoạn minh họa**. `DatagramChannel.open(ProtocolFamily)` mở UDP channel thuộc family chỉ định. API có thể ném:

- **`UnsupportedOperationException`:** family được yêu cầu không được hỗ trợ, ví dụ `INET6` khi IPv6 không khả dụng, hoặc `UNIX` với UDP datagram.
- **`IOException`:** lỗi I/O trong thao tác mở/bind, ví dụ không thể bind địa chỉ, thiếu tài nguyên hoặc cổng không khả dụng.
- **`UnsupportedAddressTypeException`:** địa chỉ dùng với channel không thuộc loại mà channel chấp nhận, chẳng hạn cố bind IPv6 vào channel chỉ có family IPv4 trên các triển khai hỗ trợ kiểm tra này.

`UnsupportedOperationException` và `UnsupportedAddressTypeException` đều là unchecked exceptions nhưng **không có cùng ý nghĩa**. `UnknownHostException` là vấn đề phân giải địa chỉ; `SocketTimeoutException` khi đợi UDP phản hồi là vấn đề thời gian chờ; cả hai không tự chứng minh family không được OS hỗ trợ.

### 4.3. Hỗ trợ của OS và khả năng kết nối là hai tầng khác nhau

Nếu `DatagramChannel.open(INET6)` thành công, ta mới biết JDK/OS chấp nhận tạo channel; sau đó vẫn cần `bind`. Nếu bind thành công, ta biết địa chỉ local hợp lệ; nhưng vẫn chưa biết firewall, network route hoặc server từ xa có cho phép kết nối hay không. Vì vậy phải tách **socket capability test**, **loopback test**, **DNS test** và **remote integration test**.

## 5. Chương trình kiểm thử chạy được bằng Java 17+

Tệp **`IpFamilyTests.java`** bên dưới kiểm tra:

- Parse literal IPv4 và IPv6.
- Mở/bind UDP channel theo `INET` và `INET6`.
- Gửi/nhận datagram UTF-8 trên loopback với timeout.
- Negative test: `UNIX` không được hỗ trợ trong `DatagramChannel`.
- In ra trạng thái rõ ràng nếu môi trường không dùng được IPv6.

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public final class IpFamilyTests {
    private static void udpLoopback(String label, InetAddress address)
            throws IOException {
        try (DatagramSocket receiver =
                     new DatagramSocket(new InetSocketAddress(address, 0));
             DatagramSocket sender =
                     new DatagramSocket(new InetSocketAddress(address, 0))) {
            receiver.setSoTimeout(1500);

            byte[] sent = "PING".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(
                    sent, sent.length, address, receiver.getLocalPort()));

            byte[] buffer = new byte[64];
            DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
            receiver.receive(packet);

            String result = new String(packet.getData(), packet.getOffset(),
                    packet.getLength(), StandardCharsets.UTF_8);
            if (!"PING".equals(result)
                    || !address.equals(packet.getAddress())) {
                throw new AssertionError(
                        label + " received unexpected datagram");
            }
            System.out.println(label + ": UDP loopback PASS");
        }
    }

    private static void verifyIp(String label,
                                 StandardProtocolFamily family,
                                 InetAddress address) throws IOException {
        try (DatagramChannel channel = DatagramChannel.open(family)) {
            channel.bind(new InetSocketAddress(address, 0));
            System.out.println(label + ": channel bind PASS");
        }
        udpLoopback(label, address);
    }

    public static void main(String[] args) throws IOException {
        InetAddress ipv4 = InetAddress.getByName("127.0.0.1");
        InetAddress ipv6 = InetAddress.getByName("::1");
        if (!(ipv4 instanceof Inet4Address)
                || !(ipv6 instanceof Inet6Address)) {
            throw new AssertionError("Unexpected address family");
        }
        System.out.println("Address classes: PASS");

        verifyIp("IPv4", StandardProtocolFamily.INET, ipv4);

        try {
            verifyIp("IPv6", StandardProtocolFamily.INET6, ipv6);
        } catch (UnsupportedOperationException | IOException ex) {
            System.out.println("IPv6: UNAVAILABLE_OR_ERROR ("
                    + ex.getClass().getSimpleName() + ")");
        }

        try (DatagramChannel unexpected =
                     DatagramChannel.open(StandardProtocolFamily.UNIX)) {
            throw new AssertionError("UNIX datagram unexpectedly supported");
        } catch (UnsupportedOperationException expected) {
            System.out.println("UNIX datagram: UNSUPPORTED (expected)");
        }
    }
}
```

**Giải thích chương trình:**

1. Hai literal `127.0.0.1` và `::1` cho phép chọn rõ họ địa chỉ mà không phụ thuộc tên `localhost`.
2. `verifyIp` thử `DatagramChannel.open(family)` và `bind`; nếu thành công mới chạy thử UDP thực.
3. `udpLoopback` tạo hai socket bind trên cùng địa chỉ local nhưng cổng tạm khác nhau; socket gửi `PING` đến đúng `receiver.getLocalPort()`.
4. `setSoTimeout(1500)` chặn việc test treo vô hạn; khi timeout, exception được chuyển tới phần xử lý ở `main`.
5. Khi nhận datagram, chương trình so sánh **đúng vùng dữ liệu** qua `getOffset()` và `getLength()`, rồi kiểm tra IP nguồn với địa chỉ loopback mong đợi.
6. `try-with-resources` đóng channel/socket kể cả khi test lỗi.
7. Với IPv4, lỗi được phép thoát khỏi `main`: bài test coi đây là lỗi môi trường/test. Với IPv6, ví dụ chỉ **ghi nhận chẩn đoán** để người chạy quyết định xem hỗ trợ IPv6 là bắt buộc hay tùy chọn.
8. Negative test `UNIX` thành công khi ném `UnsupportedOperationException`; nếu API bất ngờ chấp nhận Unix-domain datagram, chương trình ném `AssertionError` để báo giả định cần kiểm tra lại.

**Giới hạn của ví dụ:** Đây là chương trình kiểm tra khả năng theo môi trường, **chưa phải bộ test tự động chốt toàn bộ yêu cầu ứng dụng**. Nó sử dụng loopback, không chứng minh đi được tới máy bên ngoài; kiểm thử payload `PING` không thay thế kiểm thử tải, phân mảnh, mất gói, bảo mật hoặc dual-stack từ mạng thực.

## 6. Biên dịch, chạy và đọc kết quả

Dùng JDK 17 trở lên (ví dụ JDK 21). Lưu file đúng tên `IpFamilyTests.java` rồi thực hiện trong thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 IpFamilyTests.java
java IpFamilyTests
```

Trên môi trường đã kiểm thử thực tế bằng **OpenJDK 21 trên Linux với IPv4 và IPv6 loopback khả dụng**, stdout là:

```text
Address classes: PASS
IPv4: channel bind PASS
IPv4: UDP loopback PASS
IPv6: channel bind PASS
IPv6: UDP loopback PASS
UNIX datagram: UNSUPPORTED (expected)
```

**Không được xem đây là stdout bắt buộc trên mọi máy.** Nếu IPv6 không khả dụng hoặc bị JVM cấu hình tắt, kết quả có thể là:

```text
Address classes: PASS
IPv4: channel bind PASS
IPv4: UDP loopback PASS
IPv6: UNAVAILABLE_OR_ERROR (UnsupportedOperationException)
UNIX datagram: UNSUPPORTED (expected)
```

Dòng `UNAVAILABLE_OR_ERROR` là **dữ liệu chẩn đoán**, chưa phải PASS cho một yêu cầu IPv6. Nếu ứng dụng của bạn **bắt buộc hỗ trợ IPv6**, phải để CI FAIL khi gặp dòng này (ví dụ đổi `catch` để ném `AssertionError` sau khi ghi nguyên nhân). Nếu dự án **chủ động không yêu cầu IPv6 trên runner đó**, có thể phân loại SKIP cùng lý do và kiểm thử IPv6 ở một runner khác có IPv6.

### Thử cấu hình IPv4-only trong một tiến trình mới

```bash
java -Djava.net.preferIPv4Stack=true IpFamilyTests
```

Trên OpenJDK 21 Linux, lệnh này cho kết quả IPv4 PASS, IPv6 báo `UNAVAILABLE_OR_ERROR (UnsupportedOperationException)`, và negative test UNIX vẫn PASS. Thuộc tính `java.net.preferIPv4Stack` được xét tại **khởi động JVM**; không nên mong `System.setProperty(...)` sau khi socket đã hoạt động sẽ thay đổi lại network stack.

Nếu kiểm thử trong PowerShell, có thể dùng các lệnh `javac`/`java` tương tự khi JDK nằm trên `PATH`. Để so sánh nhiều JDK, chạy với đường dẫn đầy đủ đến từng executable hoặc cấu hình toolchain phù hợp, ghi lại `java --version` cho **mỗi lượt**, không chỉ kiểm tra máy developer.

## 7. JVM networking properties: kiểm tra chứ không đoán

Hai property liên quan tới IPv4/IPv6 là:

| Property | Giá trị thường gặp | Tác dụng | Điều không thể kết luận |
| --- | --- | --- | --- |
| `java.net.preferIPv4Stack` | Mặc định `false`; đặt `true` khi chủ động muốn dùng IPv4-only | Khi `true`, dùng IPv4-only sockets; không thể liên lạc trực tiếp với IPv6-only hosts bằng stack đó. | `false` **không chứng minh** OS/CI có IPv6. |
| `java.net.preferIPv6Addresses` | Mặc định `false`; có thể là `true` hoặc `system` | Ảnh hưởng thứ tự ưu tiên địa chỉ khi một hostname có IPv4 và IPv6; `system` theo thứ tự hệ thống trả về. | `true` **không bật IPv6** nếu socket IPv6 không được hỗ trợ. |

Theo tài liệu `java.net` hiện hành, cả hai property này đều được kiểm tra **một lần lúc startup**. Vì thế mỗi tổ hợp cấu hình phải chạy trong **JVM riêng**. Nếu test thay đổi property giữa các case trong cùng một JVM rồi giả định stack đổi theo, kết quả có thể sai.

Ví dụ kiểm tra các lần chạy tách biệt:

```bash
java IpFamilyTests
java -Djava.net.preferIPv4Stack=true IpFamilyTests
java -Djava.net.preferIPv6Addresses=true IpFamilyTests
java -Djava.net.preferIPv6Addresses=system IpFamilyTests
```

Chương trình này dùng IP literal nên hai biến thể `preferIPv6Addresses` **không nhất thiết tạo khác biệt** trong output. Chúng chủ yếu có giá trị khi đánh giá cách resolver trả về và lựa chọn các địa chỉ từ hostname có cả bản ghi A/AAAA. Không dùng sự thay đổi (hoặc không đổi) của output loopback làm bằng chứng về DNS.

Trong ứng dụng thực, ngoài giá trị JVM properties còn cần ghi cấu hình OS, interface IPv6, container networking, firewall, DNS và các chính sách sandbox. Kết quả trên máy local không đảm bảo giống CI và production.

## 8. Test DNS và lựa chọn địa chỉ theo đúng phạm vi

Một phép thử DNS tốt cần tách:

- **DNS resolve:** `InetAddress.getAllByName(host)` trả về những địa chỉ nào; mỗi địa chỉ là `Inet4Address` hay `Inet6Address`?
- **Address selection:** client chọn một địa chỉ, thử từng địa chỉ hay có cơ chế fallback?
- **Transport:** kết nối TCP/UDP tới địa chỉ đã chọn có thực sự thành công?
- **Service:** server có lắng nghe trên họ giao thức đó hay không?

Đoạn mã minh họa cách quan sát family của các địa chỉ đã phân giải (chạy trong chương trình có import `java.net.*` và `java.util.*`):

```java
InetAddress[] addresses = InetAddress.getAllByName("localhost");
for (InetAddress address : addresses) {
    String family = address instanceof Inet6Address ? "IPv6" : "IPv4";
    System.out.println(family + " " + address.getHostAddress());
}
```

Đoạn trên **không phải chương trình độc lập** và thứ tự/độ dài danh sách là **đầu ra phụ thuộc môi trường**. Không viết test khẳng định `localhost` luôn có đúng hai địa chỉ hoặc IPv6 phải đứng trước IPv4.

Với ứng dụng kết nối tới hostname thật, hãy kiểm thử khả năng xử lý khi chỉ có A, chỉ có AAAA, có cả hai nhưng một đường lỗi, DNS thất bại và khi kết quả DNS bị thay đổi. Tách mỗi test theo môi trường kiểm soát được, tránh phụ thuộc dịch vụ Internet công cộng không thuộc quyền kiểm soát của test suite.

**IPv4-mapped IPv6 address** và socket dual-stack có thể khiến một socket IPv6 xử lý traffic IPv4 ở một số nền tảng/cấu hình. Tuy nhiên không được suy ra việc mở `INET6` thành công có nghĩa ứng dụng chấp nhận cả IPv4 và IPv6 trên mọi OS. Nếu hệ thống yêu cầu dual-stack, phải kiểm tra **hai phía client và server thật**, port bind, wildcard, interface, firewall và cấu hình v6-only ở môi trường đích.

## 9. Kiểm thử âm tính: family hoặc address không tương thích

Có ít nhất ba trường hợp khác nhau cần gắn nhãn đúng.

### 9.1. Family không được hỗ trợ bởi API

`DatagramChannel.open(StandardProtocolFamily.UNIX)` là negative test phù hợp trên JDK 17+: Java hỗ trợ Unix-domain **stream** socket ở những cấu hình phù hợp, nhưng tài liệu `DatagramChannel.open` nói **Unix domain sockets are not supported** cho datagram channel. Ngoại lệ `UnsupportedOperationException` ở đây là kết quả mong đợi, không phải một sự cố mạng.

`StandardProtocolFamily.UNIX` được bổ sung từ JDK 16. Nếu cần chạy source trực tiếp trên JDK 15, không tham chiếu hằng enum này trong source dành riêng cho JDK 15; bài thực hành dùng `--release 17` vì muốn minh họa ranh giới Unix-domain socket theo API hiện đại.

### 9.2. Family có trong API nhưng OS/JVM không cung cấp

`DatagramChannel.open(StandardProtocolFamily.INET6)` có thể ném `UnsupportedOperationException` khi IPv6 chưa được bật hoặc không sẵn có. Điều đó không có nghĩa `INET6` là API lỗi thời. Kết luận đúng là **không khả dụng trong runtime/cấu hình đang kiểm tra**.

Kiểm tra thêm `java.net.preferIPv4Stack`, khả năng bind `::1`, cấu hình interface và container. Không thử “sửa” bằng cách đổi tùy tiện thành `INET`, vì như vậy test không còn xác minh yêu cầu IPv6.

### 9.3. Channel và địa chỉ không khớp

Ví dụ tạo channel family `INET` (IPv4) nhưng cố bind địa chỉ IPv6 `::1` là **address-family mismatch**. Một triển khai có thể báo `UnsupportedAddressTypeException`; các lỗi khác còn tùy bước và môi trường. Nếu muốn kiểm thử trường hợp này, hãy chỉ định rõ **family channel** và **loại address**, đừng suy từ thông điệp hệ điều hành.

Các exception thường gặp không đồng nghĩa nhau:

| Dấu hiệu | Cách diễn giải | Hướng kiểm tra |
| --- | --- | --- |
| `UnsupportedOperationException` từ `open(INET6)` | Family không được provider/OS hỗ trợ lúc đó. | JVM flags, IPv6 OS/container, provider. |
| `UnsupportedOperationException` từ `open(UNIX)` trên UDP | Negative test PASS cho API datagram hiện hành. | Contract của `DatagramChannel.open`. |
| `UnsupportedAddressTypeException` | Kiểu địa chỉ không phù hợp channel/socket. | Đối chiếu `INET`/`INET6` với `Inet4Address`/`Inet6Address`. |
| `BindException`/`SocketException` | Không bind được địa chỉ/cổng hoặc lỗi native socket. | Địa chỉ local, port, interface, quyền, stack. |
| `UnknownHostException` | Không parse/resolve được host. | IP literal, DNS, hosts, resolver. |
| `SocketTimeoutException` | Đợi nhận UDP quá hạn; chưa thấy datagram. | Nguồn/đích, route, firewall, server, timeout. |
| Gửi được nhưng không nhận | UDP không bảo đảm delivery; sai family/port, gói bị drop hoặc server không trả lời. | Phân biệt send, receive, app protocol; log và test theo từng lớp. |

Không viết một khối `catch (Exception)` rồi tuyên bố tất cả là “unsupported family”: làm vậy khiến CI mất khả năng chỉ ra lỗi triển khai hay cấu hình thực.

## 10. Chính sách PASS, SKIP, FAIL cho CI

Khả năng IPv6 phải được xác định theo **mục tiêu sản phẩm**, không theo việc test muốn chạy xanh.

| Tình huống | Quyết định | Vì sao |
| --- | --- | --- |
| IPv4 là yêu cầu nền tảng, T3/T4 lỗi | **FAIL** | Không thỏa yêu cầu chạy ứng dụng. |
| IPv6 bắt buộc ở production, T5/T6 lỗi | **FAIL** | Một tính năng bắt buộc không đạt; cần sửa hoặc thay runner. |
| Runner chuyên chạy IPv4-only, IPv6 sẽ được test ở runner riêng | **SKIP có lý do** trên runner đó | Test không có điều kiện tiên quyết; vẫn phải có lượt kiểm thử IPv6 thực tế ở chỗ khác. |
| `DatagramChannel.open(UNIX)` ném đúng `UnsupportedOperationException` | **PASS** negative test | API từ chối family không hỗ trợ đúng contract. |
| Negative test `UNIX` mở thành công bất ngờ | **FAIL / cần điều tra** | Contract hoặc nền tảng thay đổi so với giả định của test. |
| Parse `::1` thành `Inet6Address` nhưng bind IPv6 lỗi | **KHÔNG tự PASS** | Parse không chứng minh mở socket được; áp chính sách yêu cầu IPv6. |
| Test dùng hostname được phân giải khác trên các runner | **Ghi dữ liệu môi trường rồi điều tra** | Thứ tự A/AAAA có thể thay đổi; chưa chứng minh lỗi ứng dụng. |

Trong JUnit 5 hoặc framework kiểm thử khác, có thể dùng assumptions để **skip một test môi trường tùy chọn**. Chỉ sử dụng assumptions cho điều kiện thực sự tùy chọn và luôn ghi lý do. Test bắt buộc phải dùng assertions để FAIL nếu thiếu điều kiện tiên quyết. Ví dụ CLI phía trên in dòng chẩn đoán nhưng **chưa tự fail** khi IPv6 không khả dụng; muốn dùng làm gate bắt buộc, hãy sửa nhánh `catch` IPv6 theo policy đã duyệt.

Nên gắn nhãn riêng cho `ipv4`, `ipv6`, `dual-stack`, `unsupported-family`, chạy các case trên OS/container/JDK mục tiêu và lưu stdout/stderr cùng `java --version`. Với UDP, test round trip trên loopback nên tách khỏi integration test giữa hai host; không được xem PASS localhost là bằng chứng đường truyền production hoạt động.

## 11. Các điểm thiết kế giúp test đáng tin cậy

### Không phụ thuộc port cố định

Bind cổng `0` để lấy port hệ điều hành chọn; gửi đến `receiver.getLocalPort()`. Cách này giảm lỗi do CI chạy song song. Nếu cần kiểm tra ứng dụng có bind port cấu hình thật hay không, dùng integration test riêng và quản lý vòng đời service.

### Luôn giới hạn thời gian chờ

UDP `receive` có thể chặn vô hạn. `DatagramSocket.setSoTimeout` giới hạn thời gian chờ để test kết thúc và chẩn đoán được; timeout không chứng minh đối tác không nhận request. Với `DatagramChannel` non-blocking, cơ chế timeout phù hợp là `Selector`/deadline, không giả định timeout của `DatagramSocket` hoạt động y hệt khi truy cập qua channel.

### Kiểm tra byte hợp lệ

Một `DatagramPacket` có buffer lớn hơn dữ liệu nhận được. Dùng `getOffset()` và `getLength()`, không giải mã cả buffer. Nếu test giao thức có nhiều byte hoặc nhị phân, xác minh độ dài, schema và checksum khi có; payload `PING` chỉ kiểm tra vòng đi/đến tối thiểu.

### Không bỏ qua cấu hình bảo mật

Loopback chỉ kiểm tra kết nối nội bộ; nó không đại diện cho firewall, NAT, IPv6 link-local scope, routing, multicast hoặc khả năng một client không tin cậy làm sai giao thức. Với IPv6 link-local (`fe80::/10`), địa chỉ có thể cần **zone/scope ID** gắn interface; không coi literal link-local không scope là testcase portable. Với IP công cộng, chỉ thử trên hệ thống/dải địa chỉ được phép kiểm tra.

### Không dùng tên exception làm tiêu chí duy nhất

Một runtime bị hạn chế quyền, thiếu interface, sai bind address hoặc thiếu IPv6 có thể báo lỗi ở những bước khác nhau. Test phải ghi lại **đã đến bước nào** (parse/open/bind/send/receive), family, địa chỉ, JDK và OS. Khi xảy ra lỗi không mong đợi, giữ nguyên stack trace hoặc nguyên nhân gốc ở báo cáo CI.

### Không gắn nhãn “IPv6 unsupported” từ DNS

Không tìm thấy bản ghi AAAA cho hostname **không chứng minh** máy không có IPv6; ngược lại, có AAAA **không chứng minh** tới được địa chỉ đó. Phân loại DNS và socket capability phải độc lập.

## 12. Kịch bản mở rộng để ứng dụng thực đạt chất lượng

Sau khi chương trình ví dụ chạy thành công, có thể xây một bộ test theo các lớp sau:

1. **Unit:** parse IPv4/IPv6, kiểm tra `Inet4Address`/`Inet6Address`, format URI `[::1]`, validate input, không cần network.
2. **Local integration:** bind và gửi/nhận trên loopback IPv4/IPv6 ở những runner phù hợp, timeout hữu hạn và cleanup socket.
3. **Negative/contract:** `open(UNIX)` cho `DatagramChannel` bị từ chối; IPv6 phải không bị đánh dấu PASS khi runner không hỗ trợ; address family mismatch được ghi là lỗi cấu hình/kiểu.
4. **Dual-stack integration:** chạy service thật, thử client IPv4 lẫn IPv6 tới endpoint đã cấu hình, quan sát server bind, firewall và tính năng fallback nếu ứng dụng yêu cầu.
5. **DNS integration:** mô phỏng A-only, AAAA-only, dual A/AAAA và DNS fail bằng resolver môi trường kiểm soát được; xác định thứ tự lựa chọn mà code cam kết, không assert thứ tự resolver chung.
6. **Transport fault:** tiêm mất gói, trễ, reorder/duplicate ở lớp test phù hợp, quan sát timeout/retry/idempotency của giao thức UDP ứng dụng.
7. **Deployment:** thực hiện test trên JDK, kernel, base image và network mode tương đồng production; không chỉ dùng máy developer.

Có thể tạo một bảng kết quả cho mỗi lần chạy:

```text
JDK version/vendor: <giá trị thực của java --version>
OS/container: <nền tảng và network mode thực>
JVM flags: <cờ -D hoặc flags liên quan>
IPv4 parse / bind / UDP: PASS | FAIL
IPv6 parse / bind / UDP: PASS | FAIL | SKIP (reason)
UNIX datagram negative test: PASS | FAIL
Dual-stack application test: PASS | FAIL | NOT_RUN
Evidence: <log/test report của chính lượt chạy>
```

Đây là mẫu **biên bản**, không phải stdout của chương trình. Giá trị phải được điền từ bằng chứng, không suy đoán.

## 13. Bài tập tự kiểm tra

1. Vì sao `InetAddress.getByName("::1") instanceof Inet6Address` là `true` nhưng `DatagramChannel.open(INET6)` vẫn có thể ném `UnsupportedOperationException`?
2. Sự khác nhau giữa `StandardProtocolFamily.INET6` và giao thức TCP/UDP là gì? Vì sao `DatagramChannel.open(UNIX)` thất bại không đồng nghĩa Unix-domain stream socket không được hỗ trợ?
3. Nếu `IPv6: UNAVAILABLE_OR_ERROR` xuất hiện trên CI, trường hợp nào được SKIP, trường hợp nào phải FAIL? Ai cần xác định tiêu chí đó?
4. Điều gì chứng minh **bind thành công** nhưng vẫn chưa chứng minh client IPv6 ở máy khác truy cập được service?
5. Vì sao hai lần chạy `java -Djava.net.preferIPv4Stack=true ...` và `java ...` phải nằm trong hai tiến trình JVM riêng?
6. Vì sao test `localhost` có thể thay đổi kết quả giữa Windows, Linux và container dù ứng dụng không đổi?
7. Bạn sẽ thêm test nào để phát hiện service vô tình chỉ bind IPv4 sau khi triển khai IPv6?

## 14. Nguồn tham khảo chính thức

- [Oracle Java API — DatagramChannel (JDK 25): open(ProtocolFamily), unsupported family và Unix-domain datagram](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html).
- [Oracle Java API — StandardProtocolFamily (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardProtocolFamily.html).
- [Oracle Java API — InetAddress (JDK 21): loopback, parse, getAllByName, địa chỉ IP](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html).
- [Oracle Java API — DatagramSocket (JDK 21): bind, send, receive và SO_TIMEOUT](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html).
- [Oracle Java — Networking Properties (JDK 21): preferIPv4Stack, preferIPv6Addresses](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html).
- [Oracle Java API — UnixDomainSocketAddress (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html).

**Điểm cần nhớ:** Kiểm thử IPv4/IPv6 phải tách **loại địa chỉ**, **family được API/OS chấp nhận**, **bind**, **gửi nhận thật** và **yêu cầu sản phẩm**. Một kết quả `UnsupportedOperationException` chỉ có ý nghĩa khi biết chính xác lời gọi nào ném ra nó: có thể là negative test PASS (`UNIX` với datagram), hoặc dấu hiệu cần sửa môi trường/đánh FAIL cho yêu cầu IPv6.