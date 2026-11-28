# Kiểm thử tra cứu ngược thành công, không có hostname và địa chỉ byte sai độ dài

## 1. Mục tiêu và hợp đồng cần kiểm tra

Java 18 đưa vào **Internet-Address Resolution SPI** theo JEP 418. Trên JDK hiện đại, `InetAddress` chuyển việc phân giải tên và địa chỉ cho resolver hệ thống; ứng dụng có thể thay resolver tích hợp bằng một implementation của `InetAddressResolverProvider`.

Bài này tập trung vào phương thức:

```java
String lookupByAddress(byte[] addr) throws UnknownHostException;
```

Đây là phép tra cứu ngược: nhận byte IP thô và trả về hostname tương ứng. Hợp đồng của JDK 25 quy định:

- `addr` dùng **network byte order**: byte có trọng số cao nhất ở vị trí `addr[0]`.
- IPv4 phải có đúng 4 byte.
- IPv6 phải có đúng 16 byte.
- Không tìm được hostname cho một địa chỉ hợp lệ thì ném `UnknownHostException`.
- Độ dài không phải 4 hoặc 16 thì ném `IllegalArgumentException`.
- `addr == null` thì ném `NullPointerException`.

Cần kiểm tra riêng ba nhóm kết quả: tìm được tên, địa chỉ hợp lệ nhưng không có tên, và đầu vào sai cấu trúc. Không gộp chúng thành một lỗi chung vì mỗi trường hợp có ý nghĩa khác nhau đối với caller.

## 2. Bộ dữ liệu kiểm thử cố định

Dùng các địa chỉ dành riêng cho tài liệu:

| Trường hợp | Byte IP | Kết quả mong đợi |
| --- | --- | --- |
| IPv4 có hostname | `192.0.2.42` | `api.reverse.qa.invalid` |
| IPv6 có hostname | `2001:db8::42` | `db.reverse.qa.invalid` |
| IPv4 hợp lệ, không có hostname | `192.0.2.99` | `UnknownHostException` |
| IPv6 hợp lệ, không có hostname | `2001:db8::99` | `UnknownHostException` |
| Byte array sai độ dài | 0, 3, 5, 15 hoặc 17 byte | `IllegalArgumentException` |
| Tham số null | `null` | `NullPointerException` |

Miền `.invalid` được dành riêng; `192.0.2.0/24` và `2001:db8::/32` là các dải địa chỉ dùng trong tài liệu. Bài kiểm thử không cần DNS công cộng hoặc kết nối tới endpoint thật.

Một IP hợp lệ về cấu trúc chưa chắc có hostname. Độ dài 4/16 byte chỉ xác định đây là một địa chỉ IPv4/IPv6 hợp lệ về mặt biểu diễn; resolver vẫn phải tìm được bản ghi tương ứng mới trả về tên.

## 3. Resolver tra cứu ngược và forward xác nhận

Cấu trúc dự án:

```text
reverse-lookup-contract/
  src/demo/resolver/
    ReverseFixtureResolver.java
    ReverseFixtureProvider.java
    ReverseLookupCheck.java
  resources/META-INF/services/
    java.net.spi.InetAddressResolverProvider
```

Tạo `src/demo/resolver/ReverseFixtureResolver.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class ReverseFixtureResolver implements InetAddressResolver {
    private static final String PREFIX = "demo.reverse.fixture.";
    private static final String IPV4_HOST = "api.reverse.qa.invalid";
    private static final String IPV6_HOST = "db.reverse.qa.invalid";

    private static final byte[] IPV4 = {(byte) 192, 0, 2, 42};
    private static final byte[] IPV6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x42
    };

    private final boolean publishMetrics;
    private final AtomicInteger reverseCount = new AtomicInteger();
    private final AtomicInteger forwardCount = new AtomicInteger();

    public ReverseFixtureResolver() {
        this(false);
    }

    ReverseFixtureResolver(boolean publishMetrics) {
        this.publishMetrics = publishMetrics;
    }

    private void publish(String key, int value) {
        if (publishMetrics) {
            System.setProperty(PREFIX + key, Integer.toString(value));
        }
    }

    @Override
    public String lookupByAddress(byte[] addr) throws UnknownHostException {
        Objects.requireNonNull(addr, "addr");

        // Kiểm tra độ dài trước khi so sánh dữ liệu.
        if (addr.length != 4 && addr.length != 16) {
            throw new IllegalArgumentException(
                    "Địa chỉ IP phải có 4 hoặc 16 byte");
        }

        publish("reverse.count", reverseCount.incrementAndGet());

        if (Arrays.equals(addr, IPV4)) {
            return IPV4_HOST;
        }
        if (Arrays.equals(addr, IPV6)) {
            return IPV6_HOST;
        }

        throw new UnknownHostException(
                "Không có hostname cho địa chỉ " + Arrays.toString(addr));
    }

    @Override
    public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
            throws UnknownHostException {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(policy, "policy");
        publish("forward.count", forwardCount.incrementAndGet());

        String normalized = host.toLowerCase(Locale.ROOT);
        byte[] address;

        if (IPV4_HOST.equals(normalized)) {
            if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                throw new UnknownHostException(host);
            }
            address = IPV4;
        } else if (IPV6_HOST.equals(normalized)) {
            if ((policy.characteristics() & LookupPolicy.IPV6) == 0) {
                throw new UnknownHostException(host);
            }
            address = IPV6;
        } else {
            throw new UnknownHostException(host);
        }

        // Không gọi resolver lần nữa: tạo đối tượng trực tiếp từ byte fixture.
        return Stream.of(InetAddress.getByAddress(host, address));
    }
}
```

Resolver kiểm tra độ dài trước, rồi mới tìm mapping. Nhờ thứ tự này, một mảng 3 byte luôn tạo `IllegalArgumentException`; nó không bị hiểu nhầm thành một địa chỉ hợp lệ nhưng không có hostname.

`lookupByName` cũng được cài đặt vì `InetAddress.getCanonicalHostName()` có bước xác minh ngược: sau khi resolver trả hostname từ IP, `InetAddress` phân giải hostname đó theo chiều thuận và kiểm tra có nhận lại đúng địa chỉ ban đầu hay không. Bước này giúp hạn chế kết quả reverse mapping không nhất quán.
## 4. Đăng ký resolver để kiểm tra qua InetAddress

Tạo `src/demo/resolver/ReverseFixtureProvider.java`:

```java
package demo.resolver;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Objects;

public final class ReverseFixtureProvider extends InetAddressResolverProvider {
    private static final String PREFIX = "demo.reverse.fixture.";

    public ReverseFixtureProvider() {
        System.setProperty(PREFIX + "provider.constructed", "true");
    }

    @Override
    public String name() {
        return "reverse-lookup-fixture";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        System.setProperty(PREFIX + "provider.get.count", "1");
        return new ReverseFixtureResolver(true);
    }
}
```

Tạo service descriptor không có đuôi mở rộng:

```text
resources/META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung tệp:

```text
demo.resolver.ReverseFixtureProvider
```

Descriptor phải nằm ở gốc classpath output dưới `META-INF/services`. Trong JAR, đường dẫn này cũng phải nằm ở gốc archive. Bài dùng classpath directory để tập trung vào hợp đồng reverse lookup; cách đóng gói JAR dùng cùng một service descriptor.

## 5. Kiểm thử trực tiếp hợp đồng lookupByAddress

Tạo `src/demo/resolver/ReverseLookupCheck.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;

public final class ReverseLookupCheck {
    private static final String PREFIX = "demo.reverse.fixture.";

    private static final byte[] IPV4 = {(byte) 192, 0, 2, 42};
    private static final byte[] IPV6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x42
    };
    private static final byte[] UNKNOWN_IPV4 = {
        (byte) 192, 0, 2, 99
    };
    private static final byte[] UNKNOWN_IPV6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x63
    };

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectUnknown(
            ReverseFixtureResolver resolver, byte[] address) {
        try {
            resolver.lookupByAddress(address);
            throw new AssertionError(
                    "Phải ném UnknownHostException cho địa chỉ không có hostname");
        } catch (UnknownHostException expected) {
            // Kết quả mong đợi.
        }
    }

    private static void expectIllegalLength(
            ReverseFixtureResolver resolver, byte[] address, int length) {
        try {
            resolver.lookupByAddress(address);
            throw new AssertionError(
                    "Phải ném IllegalArgumentException cho length=" + length);
        } catch (IllegalArgumentException expected) {
            // Kết quả mong đợi.
        } catch (UnknownHostException unexpected) {
            throw new AssertionError(
                    "Độ dài sai phải được phát hiện trước bước tra cứu", unexpected);
        }
    }

    private static void expectNull(ReverseFixtureResolver resolver) {
        try {
            resolver.lookupByAddress(null);
            throw new AssertionError("addr=null phải ném NullPointerException");
        } catch (NullPointerException expected) {
            // Kết quả mong đợi.
        } catch (UnknownHostException unexpected) {
            throw new AssertionError(
                    "NullPointerException phải được phát hiện trước tra cứu",
                    unexpected);
        }
    }

    private static void expectUnknownFacade(
            InetAddress address, String expectedLiteral) {
        String actual = address.getCanonicalHostName();
        require(expectedLiteral.equals(actual),
                "Khi reverse lookup thất bại, facade phải trả IP literal; actual="
                        + actual);
    }

    public static void main(String[] args) throws Exception {
        ReverseFixtureResolver resolver = new ReverseFixtureResolver();

        // A. Reverse lookup thành công với IPv4 và IPv6.
        require("api.reverse.qa.invalid".equals(
                        resolver.lookupByAddress(IPV4)),
                "Sai hostname IPv4");
        require("db.reverse.qa.invalid".equals(
                        resolver.lookupByAddress(IPV6)),
                "Sai hostname IPv6");

        // B. Địa chỉ đúng độ dài nhưng không có hostname.
        expectUnknown(resolver, UNKNOWN_IPV4);
        expectUnknown(resolver, UNKNOWN_IPV6);

        // C. Độ dài không phải 4 hoặc 16 byte.
        for (int length : new int[] {0, 3, 5, 15, 17}) {
            expectIllegalLength(resolver, new byte[length], length);
        }

        // D. Tham số null.
        expectNull(resolver);

        // E. InetAddress.getByAddress có hợp đồng riêng: length sai là UnknownHostException.
        try {
            InetAddress.getByAddress(new byte[3]);
            throw new AssertionError(
                    "InetAddress.getByAddress phải từ chối byte array sai độ dài");
        } catch (UnknownHostException expected) {
            // Khác với IllegalArgumentException của resolver SPI.
        }

        System.out.println("PASS: IPv4 reverse mapping");
        System.out.println("PASS: IPv6 reverse mapping");
        System.out.println("PASS: valid address without hostname");
        System.out.println("PASS: invalid address lengths");
        System.out.println("PASS: null address");
        System.out.println("PASS: InetAddress.getByAddress invalid length contract");

        // E. Kiểm tra facade InetAddress với resolver đã đăng ký.
        // getByAddress(byte[]) tạo đối tượng từ byte thô, không làm reverse lookup.
        InetAddress known = InetAddress.getByAddress(IPV4);
        String canonical = known.getCanonicalHostName();
        require("api.reverse.qa.invalid".equals(canonical),
                "getCanonicalHostName phải trả hostname đã xác minh: "
                        + canonical);

        // F. Facade không ném UnknownHostException ra caller.
        // Khi resolver không tìm được tên, getCanonicalHostName trả IP literal.
        InetAddress unknown = InetAddress.getByAddress(UNKNOWN_IPV4);
        expectUnknownFacade(unknown, unknown.getHostAddress());

        require("true".equals(
                        System.getProperty(PREFIX + "provider.constructed")),
                "InetAddress chưa tạo provider");
        require("1".equals(
                        System.getProperty(PREFIX + "provider.get.count")),
                "InetAddress chưa cài resolver từ provider");
        require("2".equals(
                        System.getProperty(PREFIX + "reverse.count")),
                "Facade phải thực hiện hai reverse lookup");
        require("1".equals(
                        System.getProperty(PREFIX + "forward.count")),
                "Reverse thành công phải có forward confirmation");

        System.out.println("PASS: InetAddress.getCanonicalHostName reverse success");
        System.out.println("PASS: InetAddress fallback to textual IP");
        System.out.println("PASS: provider installed and forward-confirmed");
    }
}
```

Các test trực tiếp gọi `ReverseFixtureResolver.lookupByAddress` để xác nhận đúng ngoại lệ theo hợp đồng. Các test facade dùng `InetAddress.getByAddress(byte[])` để tạo đối tượng IP chưa có hostname, sau đó gọi `getCanonicalHostName()` để kích hoạt resolver hệ thống.
## 6. Biên dịch và chạy trên JDK 18+

Mỗi lần chạy cần một JVM mới để provider được discovery từ đầu và các counter bắt đầu ở trạng thái rỗng. Từ thư mục `reverse-lookup-contract`, chạy trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "out","out/META-INF/services" | Out-Null
javac --release 18 -d out src/demo/resolver/ReverseFixtureResolver.java src/demo/resolver/ReverseFixtureProvider.java src/demo/resolver/ReverseLookupCheck.java

$descriptor = "out/META-INF/services/java.net.spi.InetAddressResolverProvider"
$contents = "demo.resolver.ReverseFixtureProvider" + [Environment]::NewLine
[System.IO.File]::WriteAllText($descriptor, $contents, [System.Text.UTF8Encoding]::new($false))

java -Djava.net.preferIPv4Stack=true -cp out demo.resolver.ReverseLookupCheck
```

Tạo descriptor bằng UTF-8 không BOM. Cách này tương thích với Windows PowerShell 5.1; `Set-Content -Encoding UTF8` trên phiên bản này có thể ghi BOM.

Trên Bash/Linux/macOS:

```bash
mkdir -p out/META-INF/services
javac --release 18 -d out src/demo/resolver/ReverseFixtureResolver.java src/demo/resolver/ReverseFixtureProvider.java src/demo/resolver/ReverseLookupCheck.java
printf '%s\n' 'demo.resolver.ReverseFixtureProvider' > out/META-INF/services/java.net.spi.InetAddressResolverProvider
java -Djava.net.preferIPv4Stack=true -cp out demo.resolver.ReverseLookupCheck
```

Kết quả dự kiến:

```text
PASS: IPv4 reverse mapping
PASS: IPv6 reverse mapping
PASS: valid address without hostname
PASS: invalid address lengths
PASS: null address
PASS: InetAddress.getCanonicalHostName reverse success
PASS: InetAddress fallback to textual IP
PASS: provider installed and forward-confirmed
```

Tùy chọn, đóng gói output thành JAR để xác minh cùng service descriptor khi triển khai:

```powershell
jar --create --file reverse-fixture.jar -C out .
java -Djava.net.preferIPv4Stack=true -cp reverse-fixture.jar demo.resolver.ReverseLookupCheck
```

Trên Bash dùng cùng hai lệnh `jar` và `java`. Vì output đã chứa `META-INF/services` và các class, JAR giữ nguyên đăng ký provider ở gốc archive.
## 7. Phân biệt lỗi của resolver với kết quả của InetAddress

Hai API có hợp đồng khác nhau ở điểm quan trọng:

| Lời gọi | Đầu vào sai/không có mapping | Kết quả |
| --- | --- | --- |
| `resolver.lookupByAddress(validButUnmappedBytes)` | IP có 4 hoặc 16 byte nhưng không có hostname | `UnknownHostException` |
| `resolver.lookupByAddress(wrongLengthBytes)` | Độ dài không phải 4 hoặc 16 | `IllegalArgumentException` |
| `resolver.lookupByAddress(null)` | Tham số null | `NullPointerException` |
| `InetAddress.getByAddress(wrongLengthBytes)` | Byte array không phải 4 hoặc 16 byte | `UnknownHostException` theo hợp đồng riêng của `InetAddress.getByAddress` |
| `InetAddress.getCanonicalHostName()` | Reverse lookup không tìm được hostname | Trả về chuỗi IP, không ném `UnknownHostException` cho caller |

Do đó, test byte array sai độ dài của SPI phải gọi trực tiếp `lookupByAddress`. Không dùng `InetAddress.getByAddress` để thay thế rồi kỳ vọng cùng loại exception: đó là một API khác, với hợp đồng khác.

### `getByAddress` không tự làm reverse lookup

`InetAddress.getByAddress(byte[])` tạo đối tượng `InetAddress` từ byte IP và không thực hiện reverse lookup. Lời gọi `getCanonicalHostName()` mới yêu cầu system-wide resolver tìm hostname đầy đủ.

`getHostName()` có thêm một điểm dễ gây nhầm: nếu đối tượng `InetAddress` được tạo với hostname, hostname đó có thể được ghi nhớ và trả lại mà không cần tra cứu ngược. Muốn kiểm tra reverse lookup thật, tạo đối tượng từ byte thuần bằng `getByAddress(byte[])` rồi gọi `getCanonicalHostName()`.

### Vì sao `getCanonicalHostName` còn gọi lookupByName?

Sau khi resolver trả hostname từ địa chỉ, `InetAddress` phân giải hostname đó theo chiều thuận và kiểm tra có nhận lại địa chỉ ban đầu hay không. Nếu hostname trả về không ánh xạ ngược về IP gốc, `InetAddress` không tin kết quả reverse mapping và trả về chuỗi IP.

Đó là lý do resolver fixture phải triển khai cả `lookupByAddress` và `lookupByName`. Nếu chỉ viết reverse mapping mà bỏ forward mapping, bài test facade có thể trả IP literal dù lời gọi trực tiếp `lookupByAddress` đã trả hostname.

## 8. Cache và tính ổn định của phép thử

`InetAddress` cache kết quả phân giải hostname thành công và thất bại. Một đối tượng `InetAddress` cũng giữ lại kết quả canonical hostname sau khi đã tra cứu. Vì vậy:

- Test trực tiếp `ReverseFixtureResolver.lookupByAddress` là phép kiểm tra hợp đồng thuần, không đi qua cache của `InetAddress`.
- Test facade dùng đối tượng `InetAddress` mới cho mỗi địa chỉ cần reverse lookup.
- Chạy integration test trong JVM mới để provider và resolver được khởi tạo từ đầu.
- Không gọi trước `InetAddress.getAllByName` với cùng hostname fixture; forward confirmation trong `getCanonicalHostName` cần đi qua resolver của test.
- Không suy ra số lần resolver chạy từ số lần gọi API nếu cache có thể trả kết quả cũ.

Các counter trong ví dụ chỉ là tín hiệu quan sát trong một JVM test. Chúng không phải API giám sát sản xuất và không nên được dùng làm system properties của ứng dụng thật.

## 9. Những nhầm lẫn thường gặp

### 9.1. IP có độ dài hợp lệ nhưng không có hostname

Đây là trường hợp `UnknownHostException`. Ví dụ địa chỉ `192.0.2.99` có đúng 4 byte nhưng fixture không có mapping. Không được ném `IllegalArgumentException` chỉ vì không tìm thấy bản ghi.

### 9.2. Địa chỉ byte sai độ dài

Đây là lỗi cấu trúc đầu vào và phải ném `IllegalArgumentException`. Kiểm tra độ dài trước khi tìm trong bảng mapping để không trả nhầm `UnknownHostException`.

### 9.3. Nhầm lỗi của SPI với lỗi của InetAddress.getByAddress

`InetAddress.getByAddress(byte[])` cũng nhận byte IP thô, nhưng nó tạo đối tượng `InetAddress` chứ không phải reverse lookup. Nếu byte array sai độ dài, API này ném `UnknownHostException` theo hợp đồng riêng của nó. Điều đó không thay đổi hợp đồng `InetAddressResolver.lookupByAddress`.

### 9.4. Dùng hostname đã được ghi nhớ để kiểm tra reverse

`InetAddress.getByAddress(host, addr)` tạo đối tượng có hostname được gắn sẵn. `getHostName()` có thể trả tên đã ghi nhớ mà không cần gọi resolver. Dùng `InetAddress.getByAddress(addr)` với byte thuần và gọi `getCanonicalHostName()` để kiểm tra đường reverse thực sự.

### 9.5. Chỉ viết reverse mapping mà không viết forward mapping

`InetAddress.getCanonicalHostName()` xác minh hostname trả về bằng một lookup forward. Nếu tên không ánh xạ lại về IP ban đầu, facade trả IP literal. Một resolver có reverse map đúng nhưng forward map thiếu hoặc sai vẫn có thể không cho kết quả như mong đợi qua `InetAddress`.

### 9.6. Xem reverse lookup như một cam kết DNS PTR

`lookupByAddress` là hợp đồng của resolver, không bắt buộc implementation phải truy vấn DNS PTR. Resolver có thể dùng hosts file, cơ sở dữ liệu nội bộ, service discovery hoặc nguồn dữ liệu khác. Điều cần bảo đảm là mapping trả về đúng theo chính sách và nguồn dữ liệu của resolver.

## 10. Checklist và bài tập mở rộng

- [ ] IPv4 4 byte có mapping trả đúng hostname.
- [ ] IPv6 16 byte có mapping trả đúng hostname.
- [ ] Địa chỉ IPv4 hợp lệ nhưng không có mapping ném `UnknownHostException`.
- [ ] Địa chỉ IPv6 hợp lệ nhưng không có mapping ném `UnknownHostException`.
- [ ] Độ dài 0, 3, 5, 15 và 17 byte ném `IllegalArgumentException`.
- [ ] `addr == null` ném `NullPointerException`.
- [ ] Byte array được diễn giải theo network byte order.
- [ ] `InetAddress.getByAddress(byte[])` không kích hoạt reverse lookup.
- [ ] `getCanonicalHostName()` dùng resolver hệ thống và trả hostname khi forward confirmation khớp.
- [ ] Khi reverse lookup không có tên, `getCanonicalHostName()` trả chuỗi IP.
- [ ] Test integration chạy trong JVM mới với service descriptor provider.

**Bài tập:** Thêm một địa chỉ hợp lệ thứ ba vào reverse map nhưng cố ý trả về hostname mà `lookupByName` ánh xạ sang một IP khác. Gọi `getCanonicalHostName()` trên địa chỉ ban đầu và quan sát facade trả về IP literal. Sau đó sửa forward mapping để khớp IP và chạy lại. Giải thích vai trò của bước xác minh forward trong việc ngăn kết quả reverse mapping không nhất quán.

**Tiêu chí hoàn thành:** Có thể phân biệt chính xác `UnknownHostException`, `IllegalArgumentException` và `NullPointerException` của `lookupByAddress`; chứng minh reverse lookup thành công cho IPv4/IPv6; hiểu khác biệt giữa lời gọi resolver trực tiếp và `InetAddress.getCanonicalHostName()`; chạy fixture không phụ thuộc DNS công cộng.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): giới thiệu API resolver SPI trong Java 18.
- [Javadoc InetAddressResolver – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng `lookupByAddress`, byte order, độ dài IPv4/IPv6 và các ngoại lệ.
- [Javadoc InetAddress – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): `getByAddress`, `getHostName`, `getCanonicalHostName`, reverse lookup và cache.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): đăng ký resolver hệ thống bằng provider SPI.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606), [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737), [RFC 3849](https://www.rfc-editor.org/rfc/rfc3849): miền và dải IP dành riêng cho tài liệu/kiểm thử.
