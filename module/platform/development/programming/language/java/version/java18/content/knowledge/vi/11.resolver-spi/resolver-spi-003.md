# `lookupByAddress(byte[])`: tra cứu ngược với độ dài 4 hoặc 16 byte và network byte order

> **Phạm vi:** Chương **Resolver SPI** trong `JAVA_VERSION_JAVA18`, xuất phát từ **JEP 418 – Internet-Address Resolution SPI** (Java 18). Bài giải thích hợp đồng tra cứu ngược của `java.net.spi.InetAddressResolver` theo API vẫn được hỗ trợ trên JDK hiện đại: nhận địa chỉ IP dạng byte, trả tên máy, phân biệt chính xác lỗi dữ liệu và lỗi không tìm thấy. Để kiểm chứng hành vi trên JDK đang dùng, ví dụ chỉ sử dụng API công khai đã có từ Java 18.

## 1. Tra cứu ngược là gì?

Tra cứu thuận (**forward lookup**) chuyển **tên máy → địa chỉ IP**:

~~~text
api.lab.invalid ──lookupByName──▶ 192.0.2.42
~~~

Tra cứu ngược (**reverse lookup**) chuyển **địa chỉ IP → tên máy**:

~~~text
192.0.2.42 ──lookupByAddress──▶ api.lab.invalid
~~~

Trong DNS truyền thống, reverse lookup thường dựa trên bản ghi **PTR**. Với Resolver SPI, nguồn ánh xạ có thể là DNS, dữ liệu cấu hình nội bộ, một service discovery system hoặc bảng cố định cho kiểm thử. API không bắt buộc phải liên hệ DNS.

JEP 418 cho phép triển khai `InetAddressResolver` thông qua `InetAddressResolverProvider` để `InetAddress` sử dụng resolver của ứng dụng trên phạm vi JVM. Interface có hai hướng tra cứu:

~~~java
// Trích chữ ký hai phương thức của java.net.spi.InetAddressResolver:
Stream<InetAddress> lookupByName(
        String host, InetAddressResolver.LookupPolicy policy)
        throws UnknownHostException;

String lookupByAddress(byte[] addr)
        throws UnknownHostException;
~~~

Đây là **chữ ký minh họa** hai phương thức (interface thực tế đã nằm trong `java.base`; không cần khai báo lại). Bài tập trung vào phương thức thứ hai:

~~~java
String lookupByAddress(byte[] addr) throws UnknownHostException;
~~~

Lời gọi điển hình khi resolver được tích hợp:

~~~text
InetAddress (cần tên máy của một IP)
           │
           ▼
InetAddressResolver.lookupByAddress(byte[] addr)
           │
           ├── Thành công: String tên máy
           └── Thất bại:
                 ├── NullPointerException  (addr == null)
                 ├── IllegalArgumentException (độ dài khác 4/16)
                 └── UnknownHostException  (IP hợp lệ nhưng không có tên)
~~~

## 2. Hợp đồng đầu vào, kết quả và ba loại lỗi

Javadoc của `InetAddressResolver.lookupByAddress` quy định:

| Tình huống | Kết quả đúng |
|---|---|
| `addr` chứa **4 byte**, ánh xạ được thành hostname | Trả `String` tên máy tương ứng với IPv4. |
| `addr` chứa **16 byte**, ánh xạ được thành hostname | Trả `String` tên máy tương ứng với IPv6. |
| Độ dài hợp lệ nhưng không tìm được tên máy | Ném `UnknownHostException`. |
| Mảng dài 0, 3, 5, 15, 17 byte… | Ném `IllegalArgumentException`. |
| `addr == null` | Ném `NullPointerException`. |

**Hai điều cần nhớ:**

1. **Độ dài IP hợp lệ và khả năng tìm thấy hostname là hai vấn đề khác nhau.** Một địa chỉ 4 byte bất kỳ có cấu trúc IPv4 hợp lệ, nhưng có thể không có bản ghi tra cứu ngược. Khi ấy lỗi đúng là `UnknownHostException`.
2. **Không trộn lỗi dữ liệu đầu vào với lỗi phân giải tên.** `IllegalArgumentException` báo rằng mảng không phải một địa chỉ IP 4/16 byte. `UnknownHostException` báo rằng mảng là IP hợp lệ về độ dài nhưng resolver không tìm thấy tên máy tương ứng.

Kiểm tra đầu vào nên nằm ở **đầu phương thức**, trước khi gọi nguồn dữ liệu:

~~~java
Objects.requireNonNull(addr, "addr");
if (addr.length != 4 && addr.length != 16) {
    throw new IllegalArgumentException(
            "IP address must contain 4 or 16 bytes");
}
~~~

Không nên trả `null`, chuỗi rỗng hoặc địa chỉ IP dạng văn bản như `"192.0.2.42"` để giả vờ phân giải ngược thành công khi **không** có hostname. Nếu không tìm được ánh xạ, ném `UnknownHostException`; lớp gọi sẽ quyết định hiển thị IP hay thông báo phù hợp.

## 3. Network byte order: giải mã đúng từng byte

### 3.1. IPv4 luôn là 4 byte

Network byte order đặt byte có trọng số cao nhất trước: `addr[0]` là octet đầu tiên trong địa chỉ IPv4. Ví dụ:

| Thứ tự | `addr[0]` | `addr[1]` | `addr[2]` | `addr[3]` |
|---|---:|---:|---:|---:|
| Decimal không dấu | 192 | 0 | 2 | 42 |
| Hex | `C0` | `00` | `02` | `2A` |

Tập byte này biểu diễn IPv4 **`192.0.2.42`**, thuộc dải IP dành cho tài liệu.

Trong Java, kiểu `byte` có dấu, miền giá trị từ `-128` đến `127`. Vì thế byte `0xC0` (192 không dấu) có giá trị biểu diễn Java là `(byte) 192`, tức `-64` khi in theo số nguyên có dấu:

~~~java
byte[] ipv4 = {(byte) 192, 0, 2, 42};

// Khi cần hiển thị như octet không dấu:
for (byte part : ipv4) {
    System.out.println(Byte.toUnsignedInt(part));
}
// 192, 0, 2, 42
~~~

Điều này **không** thay đổi các bit của địa chỉ. Khi so sánh mảng raw IP, dùng `Arrays.equals` hoặc khóa có so sánh theo **nội dung**; `byteArray1 == byteArray2` chỉ so sánh tham chiếu hai mảng.

Nếu cần dựng giá trị 32 bit để xử lý riêng, phải xử lý từng byte không dấu và đúng vị trí:

~~~java
long unsignedIpv4 =
        ((long) (ipv4[0] & 0xff) << 24)
        | ((long) (ipv4[1] & 0xff) << 16)
        | ((long) (ipv4[2] & 0xff) << 8)
        | (ipv4[3] & 0xffL);
~~~

Ở đây toán tử `& 0xff` tránh việc **sign extension** làm hỏng kết quả. Tuy nhiên, với reverse lookup đơn thuần, thường không cần chuyển mảng thành số nguyên: giữ nguyên `byte[]` sẽ dễ tránh lỗi endianness hơn.

### 3.2. IPv6 luôn là 16 byte

Một IPv6 có 128 bit = 16 byte, chia thành tám nhóm 16 bit khi hiển thị dạng văn bản. Ví dụ **`2001:db8::2a`**:

~~~text
IPv6 hiển thị: 2001:0db8:0000:0000:0000:0000:0000:002a

16 byte (hex):
20 01  0d b8  00 00  00 00  00 00  00 00  00 00  00 2a
│             │                                        │
└── 2001      └── 0000                    ... ────────┘
~~~

Dùng mảng Java:

~~~java
byte[] ipv6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0x2a
};
~~~

Hai cách viết văn bản `2001:db8::2a` và `2001:0db8:0:0:0:0:0:002a` chỉ khác hình thức; chúng cùng 16 byte. API `lookupByAddress` nhận **raw bytes**, vì vậy không phải tự xử lý dấu hai chấm hay quy tắc rút gọn `::`.

**Cẩn thận:** Mỗi nhóm hai byte luôn theo network byte order. Không đảo thứ tự byte vì máy đang chạy trên kiến trúc little-endian. Chẳng hạn `20 01` biểu diễn nhóm đầu `2001`, không phải `0120`.

### 3.3. Khác biệt với `InetAddress.getByAddress(byte[])`

Cùng từ “ByAddress” nhưng **khác hợp đồng**:

| Phương thức | Mục đích | Với mảng sai độ dài |
|---|---|---|
| `InetAddressResolver.lookupByAddress(byte[])` | Tra cứu hostname từ IP; có thể dùng resolver tùy biến. | `IllegalArgumentException`. |
| `InetAddress.getByAddress(byte[])` | Tạo đối tượng `InetAddress` từ raw IP; **không tra cứu ngược**. | `UnknownHostException` theo hợp đồng factory này. |

Với dữ liệu có độ dài hợp lệ:

~~~java
byte[] raw = {(byte) 192, 0, 2, 42};
InetAddress ip = InetAddress.getByAddress(raw);

System.out.println(ip.getHostAddress()); // 192.0.2.42
~~~

Đoạn trên chỉ dựng và hiển thị địa chỉ. Nó **không chứng minh** `lookupByAddress` hay DNS reverse lookup đã chạy. `getHostName()` có thể thực hiện tra cứu ngược nếu đối tượng chưa được gán hostname; `getCanonicalHostName()` cố xác định tên đầy đủ qua resolver. Nhưng các API cấp cao có logic bổ sung và có thể trả về chính IP dạng văn bản nếu không xác định được tên.

## 4. Ví dụ chạy độc lập trên Java 18+: reverse mapping cả IPv4 và IPv6

Ví dụ sau triển khai trực tiếp `InetAddressResolver` để kiểm tra hợp đồng với dữ liệu xác định. Hai hostname giả lập dùng miền `.invalid` và địa chỉ tài liệu:

- IPv4 `192.0.2.42` ↔ `service4.lab.invalid`.
- IPv6 `2001:db8::2a` ↔ `service6.lab.invalid`.

Lưu thành `ReverseLookupDemo.java`:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;
import java.util.stream.Stream;

public class ReverseLookupDemo {
    private static final String HOST4 = "service4.lab.invalid";
    private static final String HOST6 = "service6.lab.invalid";

    private static final byte[] IP4 = {(byte) 192, 0, 2, 42};
    private static final byte[] IP6 = {
            0x20, 0x01, 0x0d, (byte) 0xb8,
            0, 0, 0, 0,
            0, 0, 0, 0,
            0, 0, 0, 0x2a
    };

    static final class DemoResolver implements InetAddressResolver {
        @Override
        public String lookupByAddress(byte[] addr)
                throws UnknownHostException {
            // Kiểm tra null trước khi đọc độ dài mảng.
            Objects.requireNonNull(addr, "addr");
            if (addr.length != 4 && addr.length != 16) {
                throw new IllegalArgumentException(
                        "IP address must be 4 or 16 bytes");
            }

            // Arrays.equals so sánh giá trị từng byte.
            if (Arrays.equals(addr, IP4)) {
                return HOST4;
            }
            if (Arrays.equals(addr, IP6)) {
                return HOST6;
            }

            // Địa chỉ có độ dài hợp lệ nhưng không có ánh xạ.
            throw new UnknownHostException(
                    "No hostname for raw IP "
                            + HexFormat.of().formatHex(addr));
        }

        @Override
        public Stream<InetAddress> lookupByName(
                String host, LookupPolicy policy)
                throws UnknownHostException {
            // Cung cấp hướng thuận tối thiểu để ví dụ tự chứa.
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            int flags = policy.characteristics();
            if (HOST4.equalsIgnoreCase(host)
                    && (flags & LookupPolicy.IPV4) != 0) {
                return Stream.of(InetAddress.getByAddress(HOST4, IP4));
            }
            if (HOST6.equalsIgnoreCase(host)
                    && (flags & LookupPolicy.IPV6) != 0) {
                return Stream.of(InetAddress.getByAddress(HOST6, IP6));
            }
            throw new UnknownHostException(
                    "No suitable address for " + host);
        }
    }

    private static void show(DemoResolver resolver, byte[] raw) {
        String input = raw == null
                ? "null"
                : HexFormat.of().formatHex(raw);
        try {
            System.out.println(input + " -> "
                    + resolver.lookupByAddress(raw));
        } catch (UnknownHostException
                | IllegalArgumentException
                | NullPointerException e) {
            System.out.println(input + " -> "
                    + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        DemoResolver resolver = new DemoResolver();

        show(resolver, IP4); // IPv4 tìm thấy hostname
        show(resolver, IP6); // IPv6 tìm thấy hostname

        // Dữ liệu hợp lệ về độ dài nhưng không có hostname.
        show(resolver, new byte[] {(byte) 192, 0, 2, 43});

        // Dữ liệu không phải IPv4 hay IPv6.
        show(resolver, new byte[] {1, 2, 3});

        // Đối số null.
        show(resolver, null);
    }
}
~~~

Biên dịch và chạy bằng **JDK 18 trở lên**:

~~~shell
javac ReverseLookupDemo.java
java ReverseLookupDemo
~~~

Kết quả minh họa:

~~~text
c000022a -> service4.lab.invalid
20010db800000000000000000000002a -> service6.lab.invalid
c000022b -> UnknownHostException: No hostname for raw IP c000022b
010203 -> IllegalArgumentException: IP address must be 4 or 16 bytes
null -> NullPointerException: addr
~~~

Giải thích:

- `c000022a` là bốn byte `C0 00 02 2A`, tương đương `192.0.2.42`.
- Chuỗi hex thứ hai có **32 chữ số** = 16 byte, tương đương `2001:db8::2a`.
- `c000022b` vẫn đủ 4 byte nhưng không có ánh xạ; phải trả lỗi **không tìm thấy tên máy**, thay vì lỗi độ dài.
- Mảng `01 02 03` chỉ có 3 byte; báo `IllegalArgumentException` ngay trước khi truy vấn.
- `null` phải được xử lý riêng bằng `NullPointerException`.

Đoạn mã gọi **trực tiếp** `DemoResolver.lookupByAddress`, nên không phải đăng ký provider, không phụ thuộc DNS và không phụ thuộc cache `InetAddress`. Việc hiện thực `lookupByName` ở ví dụ là do `InetAddressResolver` yêu cầu cả hai phương thức, đồng thời tạo ánh xạ hai chiều thống nhất cho dữ liệu demo.

## 5. Đưa reverse lookup vào resolver thực tế: fallback đúng cách

Nếu custom resolver chỉ sở hữu một số địa chỉ nội bộ, cách phù hợp là xử lý chúng trước, rồi **ủy quyền** địa chỉ còn lại cho resolver tích hợp lấy từ `InetAddressResolverProvider.Configuration`.

Cấu trúc minh họa:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    InetAddressResolver builtIn = configuration.builtinResolver();

    return new InetAddressResolver() {
        @Override
        public String lookupByAddress(byte[] addr)
                throws UnknownHostException {
            Objects.requireNonNull(addr, "addr");
            if (addr.length != 4 && addr.length != 16) {
                throw new IllegalArgumentException("Invalid IP length");
            }

            if (Arrays.equals(addr, INTERNAL_IP)) {
                return INTERNAL_HOST;
            }
            return builtIn.lookupByAddress(addr);
        }

        @Override
        public Stream<InetAddress> lookupByName(
                String host, LookupPolicy policy)
                throws UnknownHostException {
            if (isInternalHost(host)) {
                return lookupInternalAddresses(host, policy);
            }
            return builtIn.lookupByName(host, policy);
        }
    };
}
~~~

Đây là **mẫu thiết kế**, không phải chương trình độc lập: `INTERNAL_IP`, `INTERNAL_HOST`, `isInternalHost` và `lookupInternalAddresses` cần được định nghĩa bởi ứng dụng. Mã hiện thực đầy đủ có thể chạy độc lập nằm ở phần 4.

Không dùng cách sau làm fallback bên trong `lookupByAddress`:

~~~java
// Không dùng làm fallback trong chính resolver đang hoạt động:
return InetAddress.getByAddress(addr).getCanonicalHostName();
~~~

`InetAddress.getByAddress(addr)` tự nó **không tra cứu ngược**, nhưng `getCanonicalHostName()` có thể đi qua resolver toàn JVM, quay lại chính `lookupByAddress` đang chạy và tạo **đệ quy**. Thay vì gọi qua `InetAddress`, dùng trực tiếp `configuration.builtinResolver().lookupByAddress(addr)`.

Tương tự, tên trả về từ reverse lookup không bảo đảm có thể tra cứu thuận về đúng IP ban đầu. Nếu ứng dụng cần xác nhận hai chiều, hãy thực hiện kiểm chứng có chủ đích và xử lý sai khác. Cần nhớ một IP có thể có nhiều hostname, trong khi `lookupByAddress` chỉ trả về **một String**.

### Không đồng nhất reverse lookup với xác thực danh tính

Tên do resolver trả về có thể bị ảnh hưởng bởi cấu hình DNS hoặc dữ liệu nội bộ. Vì thế không nên dùng kết quả reverse lookup làm bằng chứng duy nhất cho danh tính của máy chủ, quyền truy cập hay tính đáng tin của kết nối. Với giao thức bảo mật, vẫn phải xác thực bằng cơ chế phù hợp, chẳng hạn kiểm tra danh tính được chứng thực trong TLS.

## 6. Những lỗi dễ mắc

| Cách làm sai | Hệ quả | Cách đúng |
|---|---|---|
| Dùng `addr.length == 4` nhưng bỏ quên IPv6 | Địa chỉ IPv6 16 byte bị từ chối. | Chấp nhận **4 hoặc 16 byte**. |
| Coi `byte` âm là dữ liệu hỏng | Địa chỉ chứa octet từ 128 đến 255 bị đọc sai. | Giữ bit nguyên vẹn; khi cần số không dấu dùng `Byte.toUnsignedInt`. |
| Đảo byte theo kiến trúc CPU | Tra cứu nhầm địa chỉ. | Dữ liệu IP đầu vào đã ở **network byte order**. |
| So sánh `addr == KNOWN_IP` | Hai mảng bằng nhau về nội dung vẫn bị coi là khác. | Dùng `Arrays.equals(addr, KNOWN_IP)`. |
| Trả `null` hoặc tên giả khi không có mapping | Khó chẩn đoán, làm sai hợp đồng phân giải tên. | Ném `UnknownHostException`. |
| Ném `UnknownHostException` cho mảng dài 3 byte | Che giấu dữ liệu đầu vào sai. | Ném `IllegalArgumentException`. |
| Gọi `getCanonicalHostName()` để fallback trong resolver | Có thể tạo vòng đệ quy. | Gọi resolver tích hợp qua `Configuration.builtinResolver()`. |
| Giả định `getByAddress(byte[])` đã tra cứu ngược | Kiểm thử thành công giả. | Gọi trực tiếp `lookupByAddress` hoặc kiểm thử tầng tích hợp rõ ràng. |

**Chú ý về kiểm thử tích hợp:** `InetAddress` dùng resolver ở phạm vi JVM và có các cơ chế riêng khi phân giải tên. Khi thay đổi cách đăng ký provider hoặc dữ liệu cache, hãy kiểm thử trong tiến trình JVM mới để tránh suy luận sai từ trạng thái đã khởi tạo.

## 7. Checklist kiểm chứng hợp đồng

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Mảng IPv4 4 byte, có mapping | Trả đúng hostname. |
| Mảng IPv6 16 byte, có mapping | Trả đúng hostname. |
| Mảng 4 byte không có mapping | `UnknownHostException`. |
| Mảng 16 byte không có mapping | `UnknownHostException`. |
| Mảng 0, 3, 5, 15, 17 byte | `IllegalArgumentException`. |
| `null` | `NullPointerException`. |
| Mảng có byte Java mang giá trị âm | Vẫn so sánh đúng bit của IP. |
| Hai mảng khác tham chiếu nhưng cùng byte | Nhận cùng kết quả mapping. |
| Hostname trả về tra cứu thuận không được | Có quy tắc xử lý khi cần xác nhận hai chiều. |
| Địa chỉ ngoài tập custom | Fallback đúng resolver tích hợp nếu thiết kế yêu cầu. |

Có thể bổ sung kiểm tra **không sửa mảng đầu vào** vì caller có thể tái sử dụng nó. Nếu lưu `byte[]` làm dữ liệu trong bộ nhớ hay cache, cân nhắc sao chép phòng ngừa và dùng key so sánh theo nội dung để tránh lỗi khi mảng thay đổi sau khi đưa vào cấu trúc dữ liệu.

## 8. Câu hỏi tự đánh giá

1. Với raw IP `{(byte) 192, 0, 2, 42}`, tại sao phần tử đầu in ra `-64` nhưng IP thực tế vẫn là `192.0.2.42`?
2. `new byte[] {1, 2, 3}` và `new byte[] {(byte) 192, 0, 2, 43}` phải dẫn đến hai loại exception nào khác nhau?
3. Vì sao không được đảo thứ tự byte khi nhận địa chỉ IP trên máy tính dùng little-endian?
4. Khi nào `InetAddress.getByAddress(byte[])` có thể chạy thành công mà `lookupByAddress(byte[])` vẫn ném `UnknownHostException`?
5. Tại sao không nên gọi `getCanonicalHostName()` từ bên trong triển khai `lookupByAddress` để xử lý fallback?
6. Reverse lookup trả về một hostname có đủ chứng minh máy chủ đang dùng IP đó là đáng tin cậy không? Nếu không, cần xác thực bằng cách nào?

**Điểm cần nhớ:** `lookupByAddress(byte[])` nhận **4 byte IPv4 hoặc 16 byte IPv6 theo network byte order**, trả về một `String` hostname nếu tìm được, ném `UnknownHostException` nếu không có ánh xạ, `IllegalArgumentException` nếu độ dài sai và `NullPointerException` nếu mảng là `null`. Đây là hợp đồng công khai của Resolver SPI từ Java 18 vẫn phù hợp trên JDK hiện đại.

## Tài liệu tham khảo

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 25: `InetAddressResolver` – `lookupByAddress(byte[])`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 25: `InetAddressResolverProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 25: `InetAddress` – `getByAddress`, `getHostName`, `getCanonicalHostName`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html).
