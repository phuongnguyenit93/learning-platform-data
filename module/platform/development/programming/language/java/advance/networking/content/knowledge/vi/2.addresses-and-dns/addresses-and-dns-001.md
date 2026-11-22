# IPv4, IPv6 và cách biểu diễn địa chỉ bằng InetAddress

Khi lập trình mạng bằng Java, cần phân biệt **địa chỉ IP** (định danh ở tầng mạng), **tên máy chủ** (tên cần được phân giải) và **cổng** (xác định dịch vụ trên máy). Bài này tập trung vào cách đọc, biểu diễn, phân loại địa chỉ IPv4/IPv6 và thao tác với các lớp `java.net.InetAddress`, `Inet4Address`, `Inet6Address` trên Java 17+.

Sau bài học, bạn có thể: nhận biết địa chỉ IPv4/IPv6 và phạm vi sử dụng; giải thích vì sao chúng dài 4/16 byte; tạo `InetAddress` từ literal, tên host hoặc byte; nhận diện khác biệt giữa phân giải DNS và chuyển đổi địa chỉ; xử lý các trường hợp link-local, CIDR và socket endpoint.

## 1. Địa chỉ IP và tên host là hai khái niệm khác nhau

- **Địa chỉ IP** là giá trị nhị phân được giao thức Internet dùng để định tuyến gói tin. IPv4 có 32 bit; IPv6 có 128 bit.
- **Literal IP** là cách con người viết địa chỉ IP dưới dạng chuỗi, chẳng hạn `192.0.2.10` hoặc `2001:db8::1`.
- **Hostname** là tên như `example.com`. Một tên có thể được phân giải thành không, một hoặc nhiều địa chỉ IPv4/IPv6. Phân giải không nhất thiết luôn truy vấn DNS từ xa: hệ điều hành, tệp hosts, bộ nhớ đệm và resolver cấu hình sẵn cũng có thể tham gia.
- **Port** là số 0–65535 dùng trong endpoint TCP/UDP, ví dụ máy chủ `192.0.2.10` tại cổng `443`. `InetAddress` chỉ mang thông tin địa chỉ IP (và có thể gắn thông tin hostname); muốn ghép địa chỉ với cổng, dùng `InetSocketAddress`.

Luồng khái niệm:

~~~text
"example.com" (hostname)
        |
        v
bộ phân giải tên / DNS / hosts / cache
        |
        +----> địa chỉ IPv4 (A) ----> Inet4Address
        |
        +----> địa chỉ IPv6 (AAAA) --> Inet6Address
                                      |
                                      v
                             IP + cổng => endpoint
~~~

Không được xem IP là danh tính bất biến của một website: một hostname có thể trả nhiều IP, IP có thể thay đổi theo thời gian và một IP có thể phục vụ nhiều hostname.

## 2. IPv4: 32 bit, bốn octet

IPv4 thường viết dưới dạng **dotted decimal** gồm bốn số thập phân 0–255, cách nhau bằng dấu chấm:

~~~text
192.0.2.10
192 | 0 | 2 | 10
 8    8   8   8 bit = 32 bit = 4 byte
~~~

Mỗi octet là một byte không dấu về mặt giao thức. Trong Java, `byte` có dấu (−128 đến 127), vì vậy octet `192` phải được đặt trong byte bằng `(byte) 192` và đọc lại bằng `Byte.toUnsignedInt(value)` hoặc `value & 0xff`.

**Địa chỉ và tiền tố mạng:** `192.0.2.10/24` có 24 bit tiền tố mạng, tương đương subnet mask `255.255.255.0`. Phần `/24` là ký hiệu CIDR dùng khi nói về mạng/subnet; nó **không phải** một phần của literal IP mà `InetAddress.getByName(...)` tự hiểu. Phải lưu, phân tích tiền tố riêng nếu đang xây công cụ quản lý subnet.

Các nhóm thường gặp:

| Dải/ví dụ IPv4 | Ý nghĩa cần nhớ |
| --- | --- |
| `127.0.0.0/8`, thường `127.0.0.1` | Loopback, trao đổi ngay trên chính máy |
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | Địa chỉ private, không được định tuyến trực tiếp trên Internet công cộng |
| `169.254.0.0/16` | Link-local IPv4, thường do máy tự cấu hình trên liên kết cục bộ |
| `0.0.0.0` | Địa chỉ unspecified; khi bind server thường biểu thị tất cả giao diện IPv4 phù hợp |
| `224.0.0.0/4` | Multicast IPv4 |
| `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` | Dải dành cho tài liệu/ví dụ; không dùng làm đích máy chủ thật |

Không đồng nhất `0.0.0.0` với địa chỉ một server có thể kết nối, và không coi mọi địa chỉ không-public đều là loopback. Broadcast IPv4 còn phụ thuộc subnet; ví dụ broadcast truyền thống của `192.0.2.0/24` là `192.0.2.255`, không có quy tắc “mọi địa chỉ kết thúc bằng .255 đều là broadcast”.

## 3. IPv6: 128 bit, tám nhóm hextet

IPv6 gồm tám nhóm 16 bit biểu diễn bằng hệ 16, ngăn bằng dấu hai chấm. Mỗi nhóm có từ một đến bốn chữ số hex:

~~~text
2001:0db8:0000:0000:0000:0000:0000:0001
   = 2001:db8:0:0:0:0:0:1
   = 2001:db8::1
~~~

Quy tắc rút gọn:

1. Có thể bỏ các số `0` ở đầu mỗi nhóm (`0db8` thành `db8`; nhóm toàn 0 thành `0`).
2. Một chuỗi liên tiếp các nhóm bằng 0 có thể thay bằng `::`, **tối đa một lần trong một địa chỉ** để còn suy ra đủ tám nhóm.
3. Chuẩn trình bày RFC 5952 ưu tiên dạng ngắn, chữ hex thường và quy tắc thống nhất khi chọn chuỗi 0; Java có thể trả về chuỗi trình bày khác nhưng vẫn cùng địa chỉ nhị phân.

Ví dụ `::1` là loopback IPv6, `::` là unspecified IPv6. `2001:db8::/32` dành cho tài liệu; ví dụ `2001:db8:abcd::/48` biểu diễn tiền tố 48 bit. Cũng như IPv4, prefix `/48` hoặc `/64` **không** nằm trong nội dung của một đối tượng `InetAddress`.

Các phạm vi IPv6 thiết yếu:

| Dải/ví dụ IPv6 | Vai trò |
| --- | --- |
| `::1/128` | Loopback |
| `::/128` | Unspecified |
| `fe80::/10` | Link-local, lưu thông trong liên kết cục bộ |
| `fc00::/7` | Unique Local Address (ULA), thường dùng nội bộ |
| `ff00::/8` | Multicast |
| `2001:db8::/32` | Dải ví dụ/tài liệu |

IPv6 **không sử dụng broadcast** như IPv4; nhiều chức năng tương ứng dùng multicast (chẳng hạn Neighbor Discovery). Đừng mặc định IPv6 luôn có kết nối Internet: khả năng kết nối còn tùy cấu hình, định tuyến, firewall và mạng đang dùng.

### Scope/zone ID trên IPv6 link-local

Hai giao diện mạng khác nhau có thể cùng nhìn thấy một địa chỉ dạng `fe80::1`. Khi cần chọn đúng giao diện liên kết, chuỗi biểu diễn có thể kèm **zone identifier**, ví dụ `fe80::1%eth0` hoặc `fe80::1%3`. Tên giao diện và scope ID thay đổi giữa máy/OS; mã hard-code `eth0` không portable.

`Inet6Address` cung cấp `getScopeId()`, `getScopedInterface()` và các phương thức tạo địa chỉ có scope. Không nhầm dấu `%` mô tả zone với một phần của 128 bit địa chỉ. Với URI chứa literal IPv6 cần dấu ngoặc vuông và chú ý encode ký tự `%` khi có zone ID.

## 4. Java lưu địa chỉ IP như thế nào?

Sơ đồ lớp thực dụng:

~~~text
java.net.InetAddress
    +-- java.net.Inet4Address  (4 byte / IPv4)
    +-- java.net.Inet6Address  (16 byte / IPv6)
~~~

`InetAddress` là kiểu dùng chung khi bạn chưa biết một hostname sẽ trả IPv4 hay IPv6. Bạn có thể nhận biết family qua `instanceof Inet4Address` hoặc `instanceof Inet6Address`; `getAddress()` trả mảng byte theo **network byte order** (byte đầu là phần có trọng số cao nhất); `getHostAddress()` trả literal IP dưới dạng chuỗi.

| API | Chức năng | Điểm cần để ý |
| --- | --- | --- |
| `InetAddress.getByName(host)` | Trả một địa chỉ của hostname hoặc literal IP | Hostname có thể cần resolver; địa chỉ được chọn không cố định |
| `InetAddress.getAllByName(host)` | Trả các địa chỉ mà resolver cung cấp | Thứ tự, số lượng, family tùy DNS/cấu hình/cache |
| `InetAddress.getByAddress(bytes)` | Tạo IP từ 4 hoặc 16 byte | Không truy vấn DNS để kiểm tra địa chỉ; byte array dài sai ném `UnknownHostException` |
| `getAddress()` | Lấy 4/16 byte thô | Byte của Java có dấu; chuyển về unsigned nếu in octet |
| `getHostAddress()` | Lấy chuỗi IP số | Không nên dựa vào kiểu rút gọn IPv6 để so sánh địa chỉ |
| `getHostName()` | Lấy hostname liên quan hoặc tìm tên | Có thể liên quan reverse lookup; đừng gọi trong luồng nhạy độ trễ mà không cân nhắc |
| `getCanonicalHostName()` | Lấy tên chuẩn qua cơ chế phân giải | Có thể chặn/chậm, phụ thuộc resolver |
| `isLoopbackAddress()`, `isAnyLocalAddress()`, `isLinkLocalAddress()`, `isMulticastAddress()` | Kiểm tra thuộc tính địa chỉ | Phân loại địa chỉ, không kiểm chứng server đang hoạt động |
| `InetAddress.getLoopbackAddress()` | Lấy loopback của máy | Có thể trả IPv4 hoặc IPv6 tùy môi trường |
| `InetAddress.getLocalHost()` | Phân giải tên của máy cục bộ | Không đảm bảo là IP public, IP mà client ngoài Internet nhìn thấy, hay mọi IP của máy |

`UnknownHostException` xuất hiện khi không phân giải được tên hoặc đầu vào địa chỉ không hợp lệ với API tương ứng. Literal IP hợp lệ không cần DNS để chuyển thành byte; hostname có thể cần truy vấn mạng. Không sử dụng `getByName` như bộ kiểm tra cú pháp IP thuần túy cho dữ liệu không tin cậy, vì một chuỗi không phải literal có thể kích hoạt phân giải tên.

## 5. Ví dụ Java 17+: parsing, family và byte không dấu

Tạo tệp `AddressBasics.java`:

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class AddressBasics {
    public static void main(String[] args) throws UnknownHostException {
        InetAddress ipv4 = InetAddress.getByName("192.0.2.10");
        InetAddress ipv6 = InetAddress.getByName("2001:db8::1");
        InetAddress expanded =
                InetAddress.getByName("2001:0db8:0:0:0:0:0:1");

        System.out.println("IPv4 literal: " + ipv4.getHostAddress());
        System.out.println("IPv4 type: " + (ipv4 instanceof Inet4Address));
        System.out.println("IPv4 bytes: " + ipv4.getAddress().length);
        System.out.println("IPv4 first octet: "
                + Byte.toUnsignedInt(ipv4.getAddress()[0]));
        System.out.println("IPv6 type: " + (ipv6 instanceof Inet6Address));
        System.out.println("IPv6 bytes: " + ipv6.getAddress().length);
        System.out.println("IPv6 same address: " + ipv6.equals(expanded));
        System.out.println("IPv6 loopback: " + ipv6.isLoopbackAddress());
    }
}
~~~

Chạy trong thư mục chứa file:

~~~bash
javac AddressBasics.java
java AddressBasics
~~~

Kết quả xác định của chương trình:

~~~text
IPv4 literal: 192.0.2.10
IPv4 type: true
IPv4 bytes: 4
IPv4 first octet: 192
IPv6 type: true
IPv6 bytes: 16
IPv6 same address: true
IPv6 loopback: false
~~~

Diễn giải:

- `getByName("192.0.2.10")` và `getByName("2001:db8::1")` nhận **literal**, không cần tra cứu hostname. Đây là các dải tài liệu, được dùng để minh họa parsing.
- `getAddress().length` chứng minh sự khác nhau giữa 4 byte và 16 byte.
- `Byte.toUnsignedInt` biến byte có dấu của Java thành giá trị octet 0–255.
- Hai cách viết IPv6 rút gọn và đầy đủ cho cùng 128 bit nên `equals` trả `true`. Nên so sánh đối tượng/byte thay vì so sánh chuỗi dạng chữ.

## 6. Tự tạo InetAddress từ byte, không cần phân giải tên

Tạo tệp `RawAddress.java`:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

public class RawAddress {
    public static void main(String[] args) throws UnknownHostException {
        byte[] raw4 = {(byte) 192, 0, 2, 10};
        InetAddress ipv4 = InetAddress.getByAddress(raw4);

        byte[] raw6 = new byte[16];
        raw6[0] = 0x20;
        raw6[1] = 0x01;
        raw6[2] = 0x0d;
        raw6[3] = (byte) 0xb8;
        raw6[15] = 1; // 2001:db8::1
        InetAddress ipv6 = InetAddress.getByAddress(raw6);

        System.out.println("IPv4: " + ipv4.getHostAddress());
        System.out.println("First octet: "
                + Byte.toUnsignedInt(ipv4.getAddress()[0]));
        System.out.println("IPv6 class: "
                + ipv6.getClass().getSimpleName());
        System.out.println("IPv6 byte count: "
                + ipv6.getAddress().length);
        System.out.println("Same IPv6: "
                + ipv6.equals(InetAddress.getByName("2001:db8::1")));
    }
}
~~~

~~~bash
javac RawAddress.java
java RawAddress
~~~

Kết quả:

~~~text
IPv4: 192.0.2.10
First octet: 192
IPv6 class: Inet6Address
IPv6 byte count: 16
Same IPv6: true
~~~

`getByAddress(byte[])` chỉ nhận mảng đúng **4 hoặc 16 byte**. Trật tự byte là big-endian/network order; không đảo byte theo endianness của CPU. Nếu có mảng 5 byte, API sẽ ném `UnknownHostException`. Overload `getByAddress(String host, byte[] addr)` cho phép đính kèm nhãn hostname nhưng **không xác thực** rằng hostname đó thực sự trỏ tới IP; không được xem nhãn này là chứng cứ DNS.

**IPv4-mapped IPv6:** Dạng `::ffff:192.0.2.10` biểu diễn một địa chỉ IPv4 trong vùng cú pháp 128 bit. API `InetAddress`/`Inet6Address` của Java có thể nhận dạng này làm đầu vào nhưng chuyển thành đối tượng IPv4, vì vậy không nên suy ra family chỉ bằng việc chuỗi đầu vào có dấu `:`. Khi cần, kiểm tra đối tượng thực tế bằng `instanceof` và `getAddress().length`.

## 7. Phân giải một hostname: có thể có cả A và AAAA

Với hostname thực, dùng `getAllByName` nếu muốn quan sát các địa chỉ resolver cung cấp. Tạo `ResolveHost.java`:

~~~java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;

public class ResolveHost {
    public static void main(String[] args) {
        String host = args.length > 0 ? args[0] : "example.com";
        try {
            InetAddress[] addresses = InetAddress.getAllByName(host);
            for (InetAddress address : addresses) {
                String family =
                        address instanceof Inet4Address ? "IPv4" : "IPv6";
                System.out.printf("%s: %s%n",
                        family, address.getHostAddress());
            }
        } catch (UnknownHostException e) {
            System.err.println("Không phân giải được " + host
                    + ": " + e.getMessage());
        }
    }
}
~~~

~~~bash
javac ResolveHost.java
java ResolveHost example.com
~~~

**Output không cố định:** Kết quả có thể là một hoặc nhiều dòng IPv4/IPv6; IP, thứ tự, thậm chí việc phân giải thành công đều phụ thuộc DNS/resolver, bộ nhớ đệm, chính sách chọn địa chỉ và kết nối mạng. Không chép cứng một IP hiện tại của `example.com` làm kết quả mong đợi. Trong hệ thống thực, DNS có thể trả nhiều địa chỉ để phân tải hoặc dự phòng; ứng dụng kết nối phải xử lý trường hợp một đích không khả dụng.

Đường đi cần phân biệt:

1. Parse literal IP: `"192.0.2.10"` → byte địa chỉ, không cần truy vấn tên.
2. Forward resolution: `"example.com"` → tập địa chỉ từ resolver (thường qua DNS A/AAAA và cấu hình hệ thống).
3. Reverse resolution: IP → hostname qua cơ chế phân giải ngược (thường có thể dùng DNS PTR); kết quả không đảm bảo tồn tại hoặc phản ánh tên gốc. `getHostName()`/`getCanonicalHostName()` có thể phát sinh độ trễ.
4. Kết nối TCP/UDP: chọn địa chỉ + port rồi dùng socket/client phù hợp. `InetAddress` tự nó không mở kết nối.

Java và resolver có thể cache kết quả tra cứu. Không giả định DNS đổi bản ghi là các kết nối đang chạy hoặc mọi lần gọi `getByName` sẽ lập tức nhận IP mới.

## 8. Địa chỉ IP trong URL và endpoint

Một địa chỉ IP **không chứa port**. Java biểu diễn một socket endpoint qua `InetSocketAddress`:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;

InetAddress loopback = InetAddress.getLoopbackAddress();
InetSocketAddress endpoint = new InetSocketAddress(loopback, 8080);
// endpoint.getAddress(): địa chỉ IP
// endpoint.getPort(): 8080
~~~

Đoạn trên là **snippet**, không phải chương trình độc lập; đặt vào một phương thức có xử lý ngoại lệ thích hợp khi sửa để dùng hostname. `InetSocketAddress` chỉ tạo thông tin endpoint; nó không bảo đảm máy/dịch vụ đang lắng nghe.

Trong URI/URL, IPv6 literal phải được bao bởi dấu ngoặc vuông để phân biệt các dấu `:` của địa chỉ với dấu `:` trước port:

~~~text
http://192.0.2.10:8080/path
http://[2001:db8::1]:8080/path
~~~

Ví dụ `http://2001:db8::1:8080/path` không phải cách biểu diễn đúng một HTTP authority chứa địa chỉ IPv6 và port. Địa chỉ tài liệu ở ví dụ chỉ để minh họa cú pháp; không phải máy chủ có thể truy cập. Khi dùng IPv6 link-local kèm zone ID trong URI, còn có quy tắc percent-encoding riêng; đừng ghép URI bằng nối chuỗi tùy tiện.

## 9. Chọn đúng địa chỉ và nhận diện lỗi phổ biến

- **Nhầm IPv4 với IPv6 qua dấu câu:** `InetAddress` là kiểu chung, còn IPv4-mapped có thể được Java chuyển về `Inet4Address`. Kiểm tra family bằng lớp thực tế hoặc độ dài byte.
- **So sánh string IPv6:** `2001:db8::1` và `2001:0db8:0:0:0:0:0:1` là cùng địa chỉ. `getHostAddress()` không nhất thiết giữ nguyên cách viết đầu vào. Dùng `equals` cho địa chỉ, đồng thời cân nhắc scope của IPv6 khi địa chỉ cần giao diện.
- **Coi byte Java là octet không dấu:** `(byte) 192` khi in trực tiếp có thể thành `-64`; dùng `Byte.toUnsignedInt`.
- **Đưa `/24` hoặc `/64` vào literal:** CIDR là địa chỉ **kèm prefix**, còn `InetAddress` chỉ chứa địa chỉ. Parser mạng/subnet là trách nhiệm tách biệt.
- **Quên scope của link-local:** `fe80::...` có thể cần zone/interface cụ thể để định tuyến, không thể coi nó là đích global thông thường.
- **Tưởng `getLocalHost()` trả IP public:** máy có thể có nhiều NIC, loopback, NAT và container; giá trị phương thức phụ thuộc hệ thống cục bộ.
- **Tưởng `getByName` chỉ là kiểm tra định dạng:** hostname có thể kích hoạt DNS hoặc resolver và thất bại/chậm; cần kiểm soát đầu vào không tin cậy, timeout ở luồng mạng và không thực hiện tra cứu đồng bộ tùy tiện trong tác vụ nhạy độ trễ.
- **Tin `isReachable(timeout)` là bài test dịch vụ:** kết quả phụ thuộc ICMP, quyền, firewall và môi trường mạng; `true` không có nghĩa cổng ứng dụng hoạt động, `false` không kết luận host hoàn toàn chết.
- **Giả định một hostname chỉ có một địa chỉ:** `getByName` chọn một trong các kết quả; ứng dụng hỗ trợ dual-stack nên xét chính sách lựa chọn IPv4/IPv6, khả năng thất bại và cơ chế fallback của thư viện kết nối.
- **Hard-code IP của dịch vụ có DNS:** IP có thể thay đổi. Khi ứng dụng cần tính liên tục, nên dùng hostname với chính sách phân giải/kết nối phù hợp.

## 10. Tự kiểm tra

1. `192.0.2.10` cần bao nhiêu byte? Còn `2001:db8::1`? **Đáp án:** lần lượt 4 và 16 byte; cùng một phương thức `getAddress()` trả độ dài tương ứng.
2. Hai chuỗi `2001:db8::1` và `2001:0db8:0:0:0:0:0:1` có là hai địa chỉ khác nhau không? **Không.** Chúng biểu diễn cùng 128 bit, có thể kiểm chứng bằng `InetAddress.equals`.
3. Vì sao `InetAddress.getByName("example.com")` có thể chậm nhưng `getByAddress(new byte[]{127,0,0,1})` không cần DNS? **Vì** lời gọi đầu phân giải một hostname bằng resolver; lời gọi sau đã nhận sẵn địa chỉ nhị phân.
4. Muốn kết nối tới IPv6 `2001:db8::1` trên cổng `443` thì chỉ một `InetAddress` có đủ thông tin chưa? **Chưa.** Cần địa chỉ **và port** (ví dụ qua `InetSocketAddress`), rồi mới tạo kết nối. Đây là địa chỉ tài liệu, không phải server thật.
5. Vì sao truy cập `fe80::1` đôi khi phải có `%interface`? **Vì** IPv6 link-local chỉ có nghĩa trong một liên kết và máy có thể có nhiều interface; zone xác định phạm vi gửi gói.

## Tham khảo kỹ thuật

- [Java SE 21: InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html) — phương thức parsing, resolver, byte và thuộc tính địa chỉ.
- [Java SE 21: Inet4Address](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Inet4Address.html) và [Inet6Address](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Inet6Address.html) — định dạng, IPv4-mapped và IPv6 scoped.
- [RFC 4291](https://www.rfc-editor.org/rfc/rfc4291) (IPv6 Addressing Architecture), [RFC 5952](https://www.rfc-editor.org/rfc/rfc5952) (biểu diễn IPv6) và [RFC 4007](https://www.rfc-editor.org/rfc/rfc4007) (IPv6 Scoped Address Architecture).
