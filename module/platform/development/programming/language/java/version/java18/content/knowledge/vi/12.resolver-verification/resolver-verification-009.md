# Kiểm chứng IP literal và getByAddress() để tránh kết luận sai rằng provider bị bỏ qua

## 1. Vấn đề: một đối tượng InetAddress chưa chắc đã có lần phân giải tên

Java 18 đưa vào **Internet-Address Resolution SPI** theo JEP 418. Trên JDK hiện đại, các thao tác phân giải hostname và địa chỉ thông qua `InetAddress` có thể được chuyển tới implementation của `InetAddressResolverProvider`.

Khi viết test cho SPI, cần phân biệt hai việc:

- **Tạo đối tượng địa chỉ:** chương trình đã có một `InetAddress` biểu diễn một IP cụ thể.
- **Phân giải tên hoặc địa chỉ:** `InetAddress` gọi system-wide resolver để chuyển hostname thành IP hoặc IP thành hostname.

Không phải API nào trả về `InetAddress` cũng cần gọi resolver. Nếu test dùng IP literal hoặc `getByAddress(...)`, việc bộ đếm `lookupByName` không tăng là hành vi đúng. Không thể từ đó kết luận provider chưa được cài hoặc JDK đã bỏ qua provider.

Bài này dùng provider thử nghiệm có bộ đếm forward/reverse, rồi so sánh các đường gọi sau:

1. Hostname thật trong fixture qua `InetAddress.getByName`/`getAllByName`.
2. IPv4 và IPv6 literal qua `getByName`/`getAllByName`.
3. Byte IP thô qua `getByAddress(byte[])`.
4. Hostname được gắn sẵn qua `getByAddress(String, byte[])`.
5. Reverse lookup tường minh qua `getCanonicalHostName()`.

## 2. Ma trận API và hành vi resolver

| API | Đầu vào | Có gọi `lookupByName`? | Có gọi `lookupByAddress`? |
| --- | --- | --- | --- |
| `InetAddress.getByName("node.qa.invalid")` | Hostname | Có, nếu cần phân giải và chưa có kết quả cache | Không |
| `InetAddress.getAllByName("node.qa.invalid")` | Hostname | Có, nếu cần phân giải và chưa có kết quả cache | Không |
| `InetAddress.getByName("192.0.2.42")` | IPv4 literal hợp lệ | Không | Không |
| `InetAddress.getAllByName("2001:db8::42")` | IPv6 literal hợp lệ | Không | Không |
| `InetAddress.getByAddress(byte[])` | Byte IP thô 4/16 byte | Không | Không; API không thực hiện reverse lookup |
| `InetAddress.getByAddress(host, byte[])` | Hostname do caller cung cấp và byte IP | Không; không xác minh hostname | Không |
| `address.getHostAddress()` | Đối tượng đã có IP | Không | Không |
| `address.getCanonicalHostName()` | Đối tượng đã có IP | Không trực tiếp như một forward request ban đầu; resolver thực hiện reverse lookup | Có |
| `address.getHostName()` | Đối tượng có hostname đã gắn | Không nếu hostname đã được ghi nhớ; nếu chưa có, thực hiện reverse lookup | Có khi cần reverse lookup |

Bảng trên mô tả đường đi khi cache không cung cấp sẵn kết quả. Với hostname thông thường, cache thành công/thất bại của `InetAddress` có thể khiến một lần gọi API không tạo thêm lần gọi resolver. Vì vậy, test đếm resolver phải chạy trong JVM mới và dùng hostname fixture chưa được tra cứu.

### Hai chi tiết dễ nhầm

- `getByName` và `getAllByName` vẫn là API phân giải tên, nhưng khi đối số là **IP literal hợp lệ**, JDK chỉ kiểm tra cú pháp địa chỉ và tạo đối tượng từ literal. `InetAddressResolver.lookupByName` được định nghĩa để nhận hostname, không phải textual IP.
- `getByAddress(byte[])` tạo đối tượng từ byte thô và không thực hiện reverse lookup. Muốn yêu cầu tìm hostname của IP đó, gọi `getCanonicalHostName()` hoặc `getHostName()` trên đối tượng không có hostname được gắn sẵn.

## 3. Fixture và provider có bộ đếm

Dữ liệu kiểm thử:

| Mục đích | Giá trị |
| --- | --- |
| Hostname kích hoạt forward lookup | `node.qa.invalid` |
| Hostname được reverse resolver trả về | `reverse-node.qa.invalid` |
| IPv4 | `192.0.2.42` |
| IPv6 | `2001:db8::42` |
| IP hợp lệ nhưng không có reverse mapping | `192.0.2.99` |

`.invalid`, `192.0.2.0/24` và `2001:db8::/32` dành cho tài liệu/kiểm thử. Bài không gửi gói tin đến các địa chỉ này và không phụ thuộc DNS công cộng.

Cấu trúc thư mục:

```text
inetaddress-literal-probe/
  src/demo/literal/
    LiteralProbeProvider.java
    LiteralProbeResolver.java
    LiteralPathCheck.java
  resources/META-INF/services/
    java.net.spi.InetAddressResolverProvider
```

### 3.1. Resolver

Tạo `src/demo/literal/LiteralProbeResolver.java`:

```java
package demo.literal;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class LiteralProbeResolver implements InetAddressResolver {
    private static final String PREFIX = "demo.literalprobe.";

    private static final String NODE = "node.qa.invalid";
    private static final String REVERSE_NODE = "reverse-node.qa.invalid";

    private static final byte[] IPV4 = {(byte) 192, 0, 2, 42};
    private static final byte[] IPV6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x42
    };
    private final AtomicInteger nameCount = new AtomicInteger();
    private final AtomicInteger addressCount = new AtomicInteger();

    private static void publish(String key, int value) {
        System.setProperty(PREFIX + key, Integer.toString(value));
    }

    @Override
    public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
            throws UnknownHostException {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(policy, "policy");

        publish("lookup.name.count", nameCount.incrementAndGet());

        if (!NODE.equalsIgnoreCase(host)
                && !REVERSE_NODE.equalsIgnoreCase(host)) {
            throw new UnknownHostException(host);
        }

        int flags = policy.characteristics();
        InetAddress ipv4 = null;
        InetAddress ipv6 = null;

        if ((flags & LookupPolicy.IPV4) != 0) {
            ipv4 = InetAddress.getByAddress(host, IPV4);
        }
        if ((flags & LookupPolicy.IPV6) != 0) {
            ipv6 = InetAddress.getByAddress(host, IPV6);
        }

        List<InetAddress> result = new ArrayList<>(2);
        if ((flags & LookupPolicy.IPV4_FIRST) != 0) {
            if (ipv4 != null) result.add(ipv4);
            if (ipv6 != null) result.add(ipv6);
        } else if ((flags & LookupPolicy.IPV6_FIRST) != 0) {
            if (ipv6 != null) result.add(ipv6);
            if (ipv4 != null) result.add(ipv4);
        } else {
            // Fixture giữ thứ tự nguồn IPv4 rồi IPv6 khi không ép ưu tiên.
            if (ipv4 != null) result.add(ipv4);
            if (ipv6 != null) result.add(ipv6);
        }

        if (result.isEmpty()) {
            throw new UnknownHostException(
                    "Policy không yêu cầu họ địa chỉ có trong fixture");
        }

        return result.stream();
    }

    @Override
    public String lookupByAddress(byte[] addr) throws UnknownHostException {
        Objects.requireNonNull(addr, "addr");
        if (addr.length != 4 && addr.length != 16) {
            throw new IllegalArgumentException(
                    "Địa chỉ IP phải có 4 hoặc 16 byte");
        }

        publish("lookup.address.count", addressCount.incrementAndGet());

        if (Arrays.equals(addr, IPV4) || Arrays.equals(addr, IPV6)) {
            return REVERSE_NODE;
        }

        throw new UnknownHostException(
                "Không có hostname cho IP " + Arrays.toString(addr));
    }
}
```

Resolver chỉ tăng `lookup.name.count` khi `lookupByName` thực sự được gọi và chỉ tăng `lookup.address.count` khi `lookupByAddress` thực sự được gọi. Khi trả địa chỉ cho forward lookup, resolver dùng `InetAddress.getByAddress(host, bytes)` để tạo kết quả trực tiếp, tránh gọi phân giải lồng nhau.
## 4. Đăng ký provider để quan sát lookup thật

Tạo `src/demo/literal/LiteralProbeProvider.java`:

```java
package demo.literal;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Objects;

public final class LiteralProbeProvider extends InetAddressResolverProvider {
    private static final String PREFIX = "demo.literalprobe.";

    public LiteralProbeProvider() {
        System.setProperty(PREFIX + "provider.constructed", "true");
    }

    @Override
    public String name() {
        return "literal-path-probe";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        System.setProperty(PREFIX + "provider.get.count", "1");
        return new LiteralProbeResolver();
    }
}
```

Tạo service descriptor không có đuôi mở rộng:

```text
META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung:

```text
demo.literal.LiteralProbeProvider
```

Trong test, không tham chiếu `LiteralProbeProvider` trực tiếp. Provider được discovery qua descriptor khi `InetAddress` cần resolver hệ thống. Test chỉ đọc system properties bằng tên chuỗi, tránh tự khởi tạo provider trước lần lookup cần quan sát.

## 5. Chương trình kiểm tra các đường gọi

Tạo `src/demo/literal/LiteralPathCheck.java`:

```java
package demo.literal;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;

public final class LiteralPathCheck {
    private static final String PREFIX = "demo.literalprobe.";
    private static final String NODE = "node.qa.invalid";
    private static final String REVERSE_NODE = "reverse-node.qa.invalid";
    private static final String UNVERIFIED = "unverified.qa.invalid";

    private static final byte[] IPV4 = {(byte) 192, 0, 2, 42};
    private static final byte[] IPV6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x42
    };
    private static final byte[] UNKNOWN_IPV4 = {
        (byte) 192, 0, 2, 99
    };

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static String property(String key) {
        return System.getProperty(PREFIX + key);
    }

    private static int count(String key) {
        String value = property(key);
        return value == null ? 0 : Integer.parseInt(value);
    }

    private static void assertAddress(
            InetAddress address, Class<?> family, byte[] expected) {
        require(family.isInstance(address),
                "Sai họ địa chỉ: " + address.getClass().getName());
        require(Arrays.equals(expected, address.getAddress()),
                "Sai byte IP: " + address.getHostAddress());
    }

    public static void main(String[] args) throws Exception {
        // Bắt đầu trong JVM mới: chưa có provider hoặc lookup nào chạy.
        require(property("provider.get.count") == null,
                "Resolver đã được khởi tạo trước test");
        require(count("lookup.name.count") == 0,
                "Forward lookup đã chạy trước test");
        require(count("lookup.address.count") == 0,
                "Reverse lookup đã chạy trước test");

        // A. Hostname fixture phải đi qua system-wide resolver.
        InetAddress[] byName = InetAddress.getAllByName(NODE);
        require(byName.length > 0, "Hostname fixture phải có địa chỉ");
        require("true".equals(property("provider.constructed")),
                "Provider constructor chưa chạy");
        require("1".equals(property("provider.get.count")),
                "InetAddress chưa yêu cầu provider tạo resolver");

        int nameCountAfterHostname = count("lookup.name.count");
        require(nameCountAfterHostname >= 1,
                "Hostname fixture chưa đi vào lookupByName");

        // B. IPv4/IPv6 literal được parse trực tiếp, không gọi lookupByName.
        InetAddress ipv4Literal = InetAddress.getByName("192.0.2.42");
        assertAddress(ipv4Literal, Inet4Address.class, IPV4);

        InetAddress[] ipv4Literals = InetAddress.getAllByName("192.0.2.42");
        require(ipv4Literals.length == 1, "IPv4 literal phải có một kết quả");
        assertAddress(ipv4Literals[0], Inet4Address.class, IPV4);

        InetAddress[] ipv6Literals = InetAddress.getAllByName("2001:db8::42");
        require(ipv6Literals.length == 1, "IPv6 literal phải có một kết quả");
        assertAddress(ipv6Literals[0], Inet6Address.class, IPV6);

        require(count("lookup.name.count") == nameCountAfterHostname,
                "IP literal đã làm tăng forward lookup");
        require(count("lookup.address.count") == 0,
                "IP literal không được tạo reverse lookup");

        // C. Byte IP thô tạo InetAddress, không gọi reverse lookup.
        InetAddress raw4 = InetAddress.getByAddress(IPV4);
        InetAddress raw6 = InetAddress.getByAddress(IPV6);
        assertAddress(raw4, Inet4Address.class, IPV4);
        assertAddress(raw6, Inet6Address.class, IPV6);
        require(count("lookup.name.count") == nameCountAfterHostname,
                "getByAddress(byte[]) đã gọi forward lookup");
        require(count("lookup.address.count") == 0,
                "getByAddress(byte[]) đã gọi reverse lookup");

        // D. Overload có host gắn hostname do caller cung cấp, không xác minh nó.
        InetAddress suppliedHost = InetAddress.getByAddress(UNVERIFIED, IPV4);
        require(UNVERIFIED.equals(suppliedHost.getHostName()),
                "Hostname caller cung cấp phải được ghi nhớ");
        require(count("lookup.name.count") == nameCountAfterHostname,
                "getByAddress(host, bytes) đã phân giải hostname");
        require(count("lookup.address.count") == 0,
                "getHostName trên đối tượng có tên gắn sẵn đã reverse lookup");

        // E. Byte array sai độ dài bị getByAddress từ chối trực tiếp.
        try {
            InetAddress.getByAddress(new byte[3]);
            throw new AssertionError("Byte array 3 phần tử phải bị từ chối");
        } catch (UnknownHostException expected) {
            // Hợp đồng của InetAddress.getByAddress.
        }
        require(count("lookup.name.count") == nameCountAfterHostname,
                "getByAddress byte sai độ dài đã gọi resolver");
        require(count("lookup.address.count") == 0,
                "getByAddress byte sai độ dài đã gọi resolver");

        // F. Chỉ getCanonicalHostName mới yêu cầu reverse lookup cho raw IP.
        require(REVERSE_NODE.equals(raw4.getCanonicalHostName()),
                "Sai reverse hostname IPv4");
        require(count("lookup.address.count") >= 1,
                "Canonical lookup chưa đi qua lookupByAddress");

        // G. IP hợp lệ nhưng không có hostname: facade trả lại IP literal.
        InetAddress unknown = InetAddress.getByAddress(UNKNOWN_IPV4);
        String canonicalUnknown = unknown.getCanonicalHostName();
        require(unknown.getHostAddress().equals(canonicalUnknown),
                "Reverse lookup thất bại phải trả textual IP");
        require(count("lookup.address.count") >= 2,
                "Địa chỉ không có hostname chưa đi qua reverse resolver");

        System.out.println("PASS: hostname uses lookupByName");
        System.out.println("PASS: IPv4 and IPv6 literals bypass lookupByName");
        System.out.println("PASS: getByAddress(byte[]) does not reverse lookup");
        System.out.println("PASS: getByAddress(host, bytes) trusts supplied host");
        System.out.println("PASS: invalid raw length is rejected without resolver");
        System.out.println("PASS: getCanonicalHostName uses lookupByAddress");
        System.out.println("PASS: unknown reverse mapping returns textual IP");
        System.out.println("Provider get count: " + property("provider.get.count"));
        System.out.println("Forward lookup count: " + count("lookup.name.count"));
        System.out.println("Reverse lookup count: " + count("lookup.address.count"));
    }
}
```

Chương trình cố ý kích hoạt hostname fixture đầu tiên để xác nhận provider đã được cài. Sau đó nó mới đo các đường literal và byte thô. Nhờ vậy, bộ đếm không bị hiểu sai nếu provider chưa từng được khởi tạo.
## 6. Biên dịch và chạy trên JDK 18+

Mỗi lần chạy phải dùng một JVM mới để provider được discovery từ đầu và bộ đếm bắt đầu ở trạng thái rỗng.

### Windows PowerShell

Từ thư mục `inetaddress-literal-probe`:

```powershell
New-Item -ItemType Directory -Force -Path "out/META-INF/services" | Out-Null
javac --release 18 -d out src/demo/literal/LiteralProbeResolver.java src/demo/literal/LiteralProbeProvider.java src/demo/literal/LiteralPathCheck.java

$descriptor = "out/META-INF/services/java.net.spi.InetAddressResolverProvider"
$contents = "demo.literal.LiteralProbeProvider" + [Environment]::NewLine
[System.IO.File]::WriteAllText($descriptor, $contents, [System.Text.UTF8Encoding]::new($false))

java -cp out demo.literal.LiteralPathCheck
```

### Bash/Linux/macOS

```bash
mkdir -p out/META-INF/services
javac --release 18 -d out src/demo/literal/LiteralProbeResolver.java src/demo/literal/LiteralProbeProvider.java src/demo/literal/LiteralPathCheck.java
printf '%s\n' 'demo.literal.LiteralProbeProvider' > out/META-INF/services/java.net.spi.InetAddressResolverProvider
java -cp out demo.literal.LiteralPathCheck
```

Tệp descriptor được ghi UTF-8 không BOM. Tránh dùng cách ghi file có thể thêm BOM ngoài ý muốn; service configuration file được `ServiceLoader` đọc theo UTF-8.

Kết quả dự kiến:

```text
PASS: hostname uses lookupByName
PASS: IPv4 and IPv6 literals bypass lookupByName
PASS: getByAddress(byte[]) does not reverse lookup
PASS: getByAddress(host, bytes) trusts supplied host
PASS: invalid raw length is rejected without resolver
PASS: getCanonicalHostName uses lookupByAddress
PASS: unknown reverse mapping returns textual IP
Provider get count: 1
Forward lookup count: implementation-dependent, at least 1
Reverse lookup count: at least 2
```

Số forward lookup cuối cùng có thể lớn hơn một vì implementation có thể xác minh hostname reverse bằng một lần phân giải chiều thuận. Điều quan trọng của bài là các assertion chụp bộ đếm **trước reverse lookup**: IP literal và `getByAddress` không làm tăng `lookup.name.count` hoặc `lookup.address.count`.
## 7. Đọc bộ đếm theo từng giai đoạn

| Giai đoạn | `provider.get.count` | `lookup.name.count` | `lookup.address.count` |
| --- | ---: | ---: | ---: |
| JVM mới, chưa dùng `InetAddress` | Chưa có | 0 | 0 |
| Gọi `getAllByName("node.qa.invalid")` | 1 | Tăng | 0 |
| Gọi `getByName("192.0.2.42")` | 1 | Không đổi | 0 |
| Gọi `getAllByName("2001:db8::42")` | 1 | Không đổi | 0 |
| Gọi `getByAddress(byte[])` | 1 | Không đổi | 0 |
| Gọi `getByAddress(host, bytes)` rồi `getHostName()` | 1 | Không đổi | 0 |
| Gọi `getCanonicalHostName()` trên raw IP có mapping | 1 | Có thể tăng do xác minh forward | Tăng |
| Gọi `getCanonicalHostName()` trên raw IP không có mapping | 1 | Thường không tăng nếu reverse thất bại ngay | Tăng |

`provider.get.count` là dấu hiệu resolver đã được `InetAddress` yêu cầu từ provider. Nó không phải số lần lookup. `lookup.name.count` và `lookup.address.count` mới cho biết từng phương thức resolver có thực sự chạy.

Một provider có thể đã được cài đặt từ lần hostname đầu tiên, sau đó các API tạo IP literal hoặc đối tượng từ byte thô không gọi resolver. Đây là kết quả mong đợi của API.

## 8. Các trường hợp dễ tạo kết luận sai

### 8.1. Dùng IP literal để kiểm tra forward resolver

Sai mục tiêu:

```java
// Đây là IP literal hợp lệ, không phải hostname fixture.
InetAddress address = InetAddress.getByName("192.0.2.42");
```

Lời gọi trên chỉ kiểm tra parser IP literal và tạo đối tượng. Muốn xác nhận `lookupByName` chạy, dùng hostname không phải IP literal, chẳng hạn `node.qa.invalid`, và kiểm tra counter.

### 8.2. Dùng getByAddress rồi chờ reverse counter tăng

`InetAddress.getByAddress(byte[])` chỉ tạo đối tượng từ byte IP. Javadoc ghi rõ phương thức này không thực hiện reverse lookup. Sau khi tạo đối tượng, `getHostAddress()` cũng chỉ định dạng byte IP thành chuỗi.

Muốn kiểm tra `lookupByAddress`, gọi `getCanonicalHostName()` hoặc `getHostName()` trên đối tượng được tạo từ byte thô và chưa có hostname được gắn sẵn.

### 8.3. Gắn hostname vào đối tượng rồi gọi getHostName

`InetAddress.getByAddress(host, bytes)` nhận hostname do caller cung cấp. API này không dùng system-wide resolver để kiểm tra địa chỉ và cũng không xác minh hostname. Vì vậy:

```java
InetAddress address = InetAddress.getByAddress(
        "unverified.qa.invalid",
        new byte[] {(byte) 192, 0, 2, 42});

System.out.println(address.getHostName());
// unverified.qa.invalid: tên caller đã cung cấp và được ghi nhớ.
```

Kết quả trên không chứng minh hostname tồn tại trong DNS hoặc provider đã phân giải tên. Muốn reverse lookup thật, dùng đối tượng được tạo bằng `getByAddress(byte[])` và gọi `getCanonicalHostName()`.

### 8.4. Nhầm getHostAddress với getHostName

- `getHostAddress()` trả chuỗi IP từ byte đã có; không cần tra cứu hostname.
- `getHostName()` trả hostname đã gắn sẵn nếu đối tượng được tạo với hostname; nếu chưa có, nó có thể thực hiện reverse lookup.
- `getCanonicalHostName()` yêu cầu system-wide resolver thực hiện reverse lookup và trả về IP dạng text nếu không tìm được tên.

Vì vậy, khi kiểm tra reverse resolver, `getCanonicalHostName()` thể hiện ý định rõ ràng hơn.

### 8.5. Dùng hostname null hoặc chuỗi rỗng

Theo hợp đồng `InetAddress`, `getByName(null)` và `getByName("")` trả về địa chỉ loopback. Đây là trường hợp đặc biệt, không phải hostname để kiểm tra provider. Hãy dùng một hostname fixture riêng.

### 8.6. Dùng chuỗi IP sai định dạng làm ca hostname

Chỉ IP literal **hợp lệ** mới được parser nhận diện và xử lý trực tiếp. Chuỗi giống IP nhưng sai cú pháp không phải fixture tốt để kiểm tra provider. Dùng hostname `.invalid` để tạo ca forward có chủ đích; dùng literal hợp lệ để kiểm tra đường parser.

## 9. Phạm vi từng API và điều không thể suy ra

| Quan sát | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| `getByName` trả IPv4 literal | Parser chấp nhận literal và tạo địa chỉ | Provider `lookupByName` đã chạy |
| `getAllByName` trả IPv6 literal | Parser chấp nhận IPv6 literal | Resolver đã tìm IPv6 qua DNS |
| `getByAddress(byte[])` trả đối tượng | Byte IP có độ dài hợp lệ và đối tượng được tạo | Có reverse hostname hoặc resolver đã chạy |
| `getByAddress(host, bytes)` trả đối tượng | Đối tượng được tạo từ byte và hostname caller cung cấp | Hostname đã tồn tại hoặc ánh xạ tới byte IP |
| `getCanonicalHostName()` trả hostname fixture | Reverse resolver đã cung cấp hostname có thể dùng được | Một DNS PTR record công cộng tồn tại |
| `getCanonicalHostName()` trả IP literal | Resolver không cung cấp được hostname phù hợp | Provider chưa được cài đặt |

`lookupByAddress` là hợp đồng của resolver, không bắt buộc implementation phải truy vấn DNS PTR. Resolver có thể lấy hostname từ hosts file, cơ sở dữ liệu nội bộ hoặc service discovery. API `InetAddress` chỉ cung cấp facade cho thao tác reverse lookup.

## 10. Checklist và bài tập mở rộng

- [ ] Hostname fixture đi qua `lookupByName` và làm counter tăng.
- [ ] IPv4 literal hợp lệ không làm forward hoặc reverse counter tăng.
- [ ] IPv6 literal hợp lệ không làm forward hoặc reverse counter tăng.
- [ ] `getByAddress(byte[])` tạo đối tượng nhưng không gọi reverse resolver.
- [ ] `getByAddress(host, bytes)` không xác minh hostname do caller cung cấp.
- [ ] `getHostAddress()` chỉ trả textual IP.
- [ ] `getHostName()` trên đối tượng có hostname gắn sẵn trả tên đã ghi nhớ.
- [ ] `getCanonicalHostName()` trên đối tượng raw IP gọi reverse resolver.
- [ ] IP không có reverse mapping làm facade trả textual IP.
- [ ] Byte array sai độ dài bị `InetAddress.getByAddress` từ chối mà không gọi resolver.
- [ ] Test chạy trong JVM mới và không dựa vào DNS công cộng.

**Bài tập:** Thêm một hostname fixture `alias.qa.invalid` ánh xạ tới cùng IP với `node.qa.invalid`. So sánh `InetAddress.getByName("alias.qa.invalid")`, `InetAddress.getByAddress("alias.qa.invalid", bytes)` và `InetAddress.getByAddress(bytes)`. Ghi lại forward/reverse counter và giải thích vì sao ba cách tạo đối tượng có nguồn hostname khác nhau.

**Tiêu chí hoàn thành:** Có thể phân biệt parser IP literal, tạo đối tượng từ byte thô, hostname được gắn sẵn và lookup thực sự qua system-wide resolver. Khi provider counter không tăng, có thể chỉ ra API nào đã tạo đối tượng mà không cần resolver và thiết kế lại test đúng mục tiêu.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): giới thiệu resolver SPI trong Java 18.
- [Javadoc InetAddress – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): hợp đồng `getByName`, `getAllByName`, `getByAddress`, `getHostName`, `getCanonicalHostName` và IP literal.
- [Javadoc InetAddressResolver – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng `lookupByName` nhận hostname và `lookupByAddress` nhận byte IP.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): cơ chế cài resolver cấp JVM.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606), [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737), [RFC 3849](https://www.rfc-editor.org/rfc/rfc3849): miền và dải IP dành riêng cho tài liệu/kiểm thử.
