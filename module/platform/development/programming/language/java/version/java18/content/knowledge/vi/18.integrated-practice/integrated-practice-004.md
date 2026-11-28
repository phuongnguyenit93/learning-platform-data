# Tích hợp resolver provider ánh xạ hostname thử nghiệm đến fixture và kiểm tra trong JVM riêng

## 1. Mục tiêu thực hành

Từ **Java 18**, JDK cung cấp **Internet-Address Resolution SPI** (JEP 418), gồm `InetAddressResolverProvider` và `InetAddressResolver`. Các API này vẫn được hỗ trợ trên JDK hiện đại, cho phép tùy biến cách `java.net.InetAddress` phân giải hostname thành IP và thực hiện reverse lookup.

Bài thực hành tổng hợp này xây dựng một provider nhỏ để:

1. Ánh xạ hostname của môi trường thử nghiệm thành IP fixture cố định.
2. Không phát tán các hostname fixture chưa khai báo ra DNS bên ngoài.
3. Ủy quyền các hostname ngoài namespace fixture cho resolver tích hợp của JDK.
4. Đăng ký provider bằng `ServiceLoader`.
5. So sánh **hai tiến trình JVM riêng biệt**: JVM không nạp provider và JVM có provider.
6. Kiểm tra forward lookup, reverse lookup, lookup không tồn tại, policy địa chỉ và caching.

Đây là bài học về Java networking và khả năng kiểm chứng hợp đồng API, không phải một DNS server hay hệ thống định tuyến mạng production.

> **Yêu cầu:** JDK 18 trở lên. Chỉ sử dụng API public và cơ chế SPI hiện hành; không dùng tên lớp nội bộ `sun.net.spi.nameservice` hoặc cơ chế legacy không còn được hỗ trợ.

## 2. Fixture hostname và lựa chọn giải pháp

Giả sử ứng dụng cần hai hostname để test:

| Hostname | IPv4 fixture | Mục đích |
| --- | --- | --- |
| `alpha.fixture.test` | `127.0.0.42` | Dịch vụ giả lập A |
| `beta.fixture.test` | `127.0.0.43` | Dịch vụ giả lập B |
| `missing.fixture.test` | Không có mapping | Kiểm thử `UnknownHostException` |

Đuôi `.test` được IANA dành riêng cho kiểm thử, không phải domain dịch vụ production. Các IP trong `127.0.0.0/8` thuộc IPv4 loopback. Trong bài, ta chỉ phân giải hostname; không cần khởi động dịch vụ TCP tại các IP đó.

| Cách xử lý hostname | Phạm vi | Khi dùng |
| --- | --- | --- |
| Sửa hosts file của OS | Có thể ảnh hưởng nhiều tiến trình trên máy | Thử nghiệm thủ công trên máy riêng |
| `-Djdk.net.hosts.file=...` | Resolver built-in của JVM đọc hosts file chỉ định | Test mapping cố định, không cần SPI riêng |
| `InetAddressResolverProvider` | Resolver system-wide trong **một JVM** | Test logic phân giải riêng, fallback, SPI discovery |
| Tiêm interface resolver của ứng dụng | Theo từng component | Unit test khi code ứng dụng kiểm soát nơi gọi resolver |

Nếu chỉ cần ánh xạ vài tên vào IP, `jdk.net.hosts.file` thường đơn giản hơn. Ta cố ý viết provider để luyện SPI, ServiceLoader, fallback và cô lập theo tiến trình.

## 3. Hợp đồng InetAddressResolverProvider

Các thành phần:

- `InetAddress`: API ứng dụng gọi qua `getByName`, `getAllByName` và `getCanonicalHostName`.
- `InetAddressResolverProvider`: factory của một custom resolver.
- `InetAddressResolver`: triển khai `lookupByName` và `lookupByAddress`.
- `InetAddressResolver.LookupPolicy`: mô tả family IPv4/IPv6 và thứ tự ưu tiên.
- `InetAddressResolverProvider.Configuration`: cho phép lấy `builtinResolver()` để ủy quyền.

Luồng xử lý:

```text
InetAddress.getAllByName(host)
             |
             v
Resolver system-wide của JVM
             |
             v
FixtureResolverProvider
             |
             +-- host thuộc fixture.test?
             |          |
             |          +-- Có mapping & policy cho phép IPv4
             |          |          |
             |          |          v
             |          |    Trả 127.0.0.x
             |          |
             |          +-- Tên không có mapping
             |                     |
             |                     v
             |             UnknownHostException
             |
             +-- host ngoài namespace fixture
                        |
                        v
            configuration.builtinResolver()
```

Theo API, sau khi VM khởi tạo xong, lần lookup cần thiết đầu tiên khiến `InetAddress` dùng `ServiceLoader` để tìm provider qua **system class loader**. Provider đầu tiên tìm được sẽ tạo resolver system-wide; nếu không có provider, JDK dùng resolver built-in.

Thứ tự tìm thấy giữa nhiều provider là implementation-specific. Bài lab chỉ đóng gói một provider, tránh tình huống kết quả phụ thuộc thứ tự.

Lưu ý: những lookup rất sớm trước khi VM bootstrap xong vẫn có thể dùng built-in resolver. Không thiết kế test với kỳ vọng provider chặn cả mọi bước bootstrap của JVM.

## 4. Tổ chức project thử nghiệm

```text
resolver-lab/
├── src/
│   ├── demo/
│   │   ├── FixtureResolverProvider.java
│   │   └── ResolverProbe.java
│   └── META-INF/
│       └── services/
│           └── java.net.spi.InetAddressResolverProvider
├── lab-hosts
└── build/
    ├── classes/
    └── fixture-provider.jar
```

- `FixtureResolverProvider.java`: mã SPI.
- `ResolverProbe.java`: chương trình kiểm tra bằng assertions.
- `src/META-INF/services/...`: tệp đăng ký ServiceLoader.
- `lab-hosts`: hosts file riêng để kiểm tra nhánh fallback, không gọi DNS công cộng.
- `build/classes`: các class đã biên dịch, **không** có service descriptor.
- `build/fixture-provider.jar`: các class **và** service descriptor.

Điểm quan trọng: baseline phải chạy với `build/classes`, còn phép thử provider phải chạy với JAR. Nếu cả hai classpath đều có service descriptor, bạn không còn thử hai cấu hình resolver khác nhau.

## 5. Mã FixtureResolverProvider

Tạo `src/demo/FixtureResolverProvider.java`:

```java
package demo;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Stream;

public final class FixtureResolverProvider
        extends InetAddressResolverProvider {

    private static final byte[] ALPHA = {127, 0, 0, 42};
    private static final byte[] BETA  = {127, 0, 0, 43};

    public FixtureResolverProvider() {
        // ServiceLoader needs a public no-arg constructor.
    }

    @Override
    public String name() {
        return "fixture-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration);

        // Do not call InetAddress.getByName here:
        // installation is itself triggered by name lookup.
        InetAddressResolver builtIn = configuration.builtinResolver();
        System.err.println("[fixture-provider] installed");

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {

                Objects.requireNonNull(host);
                Objects.requireNonNull(policy);
                String key = normalize(host);

                if (key.equals("fixture.test")
                        || key.endsWith(".fixture.test")) {
                    byte[] bytes = switch (key) {
                        case "alpha.fixture.test" -> ALPHA;
                        case "beta.fixture.test" -> BETA;
                        default -> null;
                    };

                    boolean supportsIPv4 =
                        (policy.characteristics() & LookupPolicy.IPV4) != 0;

                    if (bytes == null || !supportsIPv4) {
                        throw new UnknownHostException(host);
                    }

                    System.err.println("[fixture-provider] forward " + key);

                    // Build from bytes, with no recursive DNS lookup.
                    return Stream.of(InetAddress.getByAddress(key, bytes));
                }

                return builtIn.lookupByName(host, policy);
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {

                Objects.requireNonNull(address);
                if (address.length != 4 && address.length != 16) {
                    throw new IllegalArgumentException(
                        "IP length must be 4 or 16 bytes"
                    );
                }

                if (Arrays.equals(address, ALPHA)) {
                    System.err.println("[fixture-provider] reverse alpha");
                    return "alpha.fixture.test";
                }
                if (Arrays.equals(address, BETA)) {
                    System.err.println("[fixture-provider] reverse beta");
                    return "beta.fixture.test";
                }

                return builtIn.lookupByAddress(address);
            }
        };
    }

    private static String normalize(String host) {
        String key = host.toLowerCase(Locale.ROOT);
        return key.endsWith(".")
            ? key.substring(0, key.length() - 1)
            : key;
    }
}
```

### 5.1. Không tạo recursive name lookup

Trong `lookupByName`, dùng:

```java
InetAddress.getByAddress(key, bytes)
```

Hàm này xây `InetAddress` từ byte IP, không gọi resolver để tra tên. Nếu gọi `InetAddress.getByName(host)` ở đây, bạn có thể quay lại chính resolver system-wide đang xử lý request, dẫn đến đệ quy.

Trong `get(Configuration)` cũng chỉ lấy `builtinResolver()`, không thực hiện lookup hoặc gọi API networking phức tạp. Javadoc đặc biệt khuyến nghị khởi tạo provider đơn giản để tránh deadlock và class-loading cycle.

### 5.2. Cách bảo vệ namespace fixture

Câu điều kiện chặn toàn bộ vùng `fixture.test`:

```java
if (key.equals("fixture.test") || key.endsWith(".fixture.test")) {
    // Known fixtures succeed, other names fail locally.
}
```

Nhờ vậy `missing.fixture.test` không rơi xuống resolver tích hợp hoặc DNS. Tên miền thử nghiệm không bị gửi ra ngoài do một typo.

`normalize` chuẩn hóa chữ hoa/thường bằng `Locale.ROOT` và bỏ một dấu chấm cuối nếu có. Do đó `ALPHA.FIXTURE.TEST` và `alpha.fixture.test.` được xử lý như cùng một fixture.

### 5.3. LookupPolicy và giới hạn IPv4-only

`LookupPolicy.characteristics()` cung cấp bit flags `IPV4`, `IPV6`, `IPV4_FIRST`, `IPV6_FIRST`.

Lab chỉ có IPv4 fixtures nên:

- Khi policy cho phép IPv4: trả đúng một IPv4.
- Khi policy chỉ cho IPv6: ném `UnknownHostException`.
- Không tự bịa IPv6 tương ứng.
- Không phải sắp xếp nhiều địa chỉ vì mỗi fixture hiện có một địa chỉ.

Khi mở rộng sang dual-stack, phải lọc kết quả theo family và tôn trọng thứ tự nếu có cả IPv4 và IPv6.

### 5.4. Reverse lookup và fallback

`lookupByAddress(byte[])` nhận byte của IPv4 (4 byte) hoặc IPv6 (16 byte). Từ dữ liệu raw `{127,0,0,42}` trả `alpha.fixture.test`; từ `{127,0,0,43}` trả `beta.fixture.test`.

Với IP khác hoặc hostname ngoài namespace fixture, dùng resolver built-in được cung cấp bởi `Configuration`:

```java
return builtIn.lookupByName(host, policy);
return builtIn.lookupByAddress(address);
```

Không thay các câu trên bằng `InetAddress.getAllByName` hoặc `getCanonicalHostName` ngay trong resolver: những API system-wide đó có thể gọi lại provider hiện tại.

## 6. Đăng ký provider với ServiceLoader

Tạo tệp đúng đường dẫn:

```text
src/META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung của tệp (một dòng):

```text
demo.FixtureResolverProvider
```

Tên tệp phải khớp **tên đầy đủ của service interface**; tên bên trong phải là fully qualified class name của provider.

Yêu cầu:

- Class provider phải public, có constructor public không tham số.
- Tệp descriptor cần được đóng gói vào classpath/JAR của JVM sẽ dùng provider.
- Chỉ đưa một provider vào phép thử có yêu cầu kết quả xác định.
- Nếu tên class trong descriptor sai, `ServiceLoader` có thể báo `ServiceConfigurationError`.

Đối với named module, một lựa chọn khác là khai báo trong `module-info.java`:

```java
module demo.fixture.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with demo.FixtureResolverProvider;
}
```

Bài thực hành chính dùng classpath và `META-INF/services`, không đồng thời cấu hình module path để tránh tăng độ phức tạp.


## 7. Chương trình ResolverProbe: assertions trong từng JVM

Tạo `src/demo/ResolverProbe.java`:

```java
package demo;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;

public final class ResolverProbe {
    private ResolverProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: ResolverProbe baseline|fixture"
            );
        }

        switch (args[0]) {
            case "baseline" -> baseline();
            case "fixture" -> fixture();
            default -> throw new IllegalArgumentException(
                "Unknown mode: " + args[0]
            );
        }
    }

    private static void baseline() throws Exception {
        assertAddress("delegated.example.test", "127.0.0.88");
        expectUnknown("alpha.fixture.test");
        System.out.println("PASS baseline");
    }

    private static void fixture() throws Exception {
        assertAddress("alpha.fixture.test", "127.0.0.42");
        assertAddress("beta.fixture.test", "127.0.0.43");
        assertAddress("ALPHA.FIXTURE.TEST", "127.0.0.42");

        // Fallback to the built-in resolver / hosts file.
        assertAddress("delegated.example.test", "127.0.0.88");

        // Unknown fixture names cannot be sent to DNS.
        expectUnknown("missing.fixture.test");

        // This object has no pre-supplied hostname.
        InetAddress raw = InetAddress.getByAddress(
            new byte[] {127, 0, 0, 42}
        );
        assertEquals(
            "alpha.fixture.test",
            raw.getCanonicalHostName(),
            "reverse lookup"
        );

        System.out.println("PASS fixture");
    }

    private static void assertAddress(
            String hostname, String expected) throws Exception {

        InetAddress[] addresses = InetAddress.getAllByName(hostname);
        if (addresses.length != 1) {
            throw new AssertionError(
                hostname + ": expected one address, got "
                + Arrays.toString(addresses)
            );
        }

        assertEquals(
            expected,
            addresses[0].getHostAddress(),
            hostname
        );
        System.out.println("PASS " + hostname + " -> " + expected);
    }

    private static void expectUnknown(String hostname)
            throws Exception {

        try {
            InetAddress.getAllByName(hostname);
        } catch (UnknownHostException expected) {
            System.out.println("PASS unknown: " + hostname);
            return;
        }
        throw new AssertionError(
            "Expected UnknownHostException: " + hostname
        );
    }

    private static void assertEquals(
            String expected, String actual, String label) {

        if (!expected.equals(actual)) {
            throw new AssertionError(
                label + ": expected=" + expected
                + ", actual=" + actual
            );
        }
    }
}
```

Các assertions ném `AssertionError` trực tiếp, không dùng keyword `assert`; vì thế không cần JVM flag `-ea`.

### 7.1. Phân biệt hai mode

| Mode | Classpath | Kết quả quan trọng |
| --- | --- | --- |
| `baseline` | Chỉ các class đã compile, không có service descriptor | `alpha.fixture.test` nhận `UnknownHostException`. |
| `fixture` | JAR chứa provider và descriptor | Alpha/beta trả IP fixture, unknown fixture thất bại, fallback và reverse hoạt động. |

Bài test so sánh **giá trị IP** chứ không chỉ kiểm tra rằng lookup thành công. Vì vậy, ánh xạ sai sẽ bị phát hiện.

### 7.2. Vì sao reverse dùng getCanonicalHostName?

Đối tượng:

```java
InetAddress raw = InetAddress.getByAddress(
    new byte[] {127, 0, 0, 42}
);
```

được tạo mà không kèm hostname. `getCanonicalHostName()` sử dụng resolver system-wide để thực hiện reverse lookup; JDK cũng có thể xác minh kết quả bằng lookup chiều thuận.

Nếu dùng:

```java
InetAddress known = InetAddress.getByAddress(
    "alpha.fixture.test", new byte[] {127, 0, 0, 42}
);
System.out.println(known.getHostName());
```

thì `getHostName()` có thể trả hostname đã ghi sẵn trong object mà không gọi `lookupByAddress`. Vì vậy nó không phải phép thử reverse lookup đáng tin cậy.

## 8. Hosts file riêng giúp kiểm tra fallback mà không cần DNS

Tạo `lab-hosts` ở thư mục gốc `resolver-lab`:

```text
127.0.0.88 delegated.example.test
```

Khi khởi động JVM, truyền:

```text
-Djdk.net.hosts.file=<absolute-path-to-lab-hosts>
```

Tài liệu Java Networking mô tả cách chỉ định hosts file riêng cho `InetAddress`, phù hợp với các phép thử không muốn dựa vào DNS mạng.

Nhờ đó:

- Built-in resolver biết `delegated.example.test = 127.0.0.88`.
- Built-in resolver **không** có `alpha.fixture.test`.
- JVM baseline kiểm tra kết quả không có provider.
- JVM fixture dùng provider cho `alpha.fixture.test`, và dùng `configuration.builtinResolver()` cho `delegated.example.test`.

Không cần chỉnh file hosts của OS hay dùng quyền quản trị. Giữ tệp thử nghiệm chỉ chứa hostname/IP giả lập.

## 9. Biên dịch và chạy trên Linux/macOS

Từ thư mục `resolver-lab`:

```sh
mkdir -p build/classes

javac -encoding UTF-8 -d build/classes \
    src/demo/FixtureResolverProvider.java \
    src/demo/ResolverProbe.java
```

Lệnh `javac` chỉ biên dịch classes; nó **không** tự chép service descriptor trong thư mục `src/META-INF/services` vào `build/classes`.

Đóng gói một JAR có cả class và descriptor:

```sh
jar --create --file build/fixture-provider.jar \
    -C build/classes . \
    -C src META-INF/services/java.net.spi.InetAddressResolverProvider
```

Kiểm tra:

```sh
jar --list --file build/fixture-provider.jar
```

Phải thấy ít nhất:

```text
demo/FixtureResolverProvider.class
demo/ResolverProbe.class
META-INF/services/java.net.spi.InetAddressResolverProvider
```

Anonymous class triển khai resolver có thể tạo thêm class file như `FixtureResolverProvider$1.class`; đây là kết quả biên dịch bình thường.

### 9.1. JVM A: baseline không có service descriptor

```sh
java -Djdk.net.hosts.file="$PWD/lab-hosts" \
    -cp build/classes \
    demo.ResolverProbe baseline
```

Output minh họa:

```text
PASS delegated.example.test -> 127.0.0.88
PASS unknown: alpha.fixture.test
PASS baseline
```

Trong JVM này, class provider có trên classpath nhưng không có service descriptor; ServiceLoader không tự tìm mọi class để suy ra một provider.

### 9.2. JVM B: có provider

```sh
java -Djdk.net.hosts.file="$PWD/lab-hosts" \
    -cp build/fixture-provider.jar \
    demo.ResolverProbe fixture
```

Output minh họa:

```text
[fixture-provider] installed
[fixture-provider] forward alpha.fixture.test
PASS alpha.fixture.test -> 127.0.0.42
PASS beta.fixture.test -> 127.0.0.43
PASS ALPHA.FIXTURE.TEST -> 127.0.0.42
PASS delegated.example.test -> 127.0.0.88
PASS unknown: missing.fixture.test
[fixture-provider] reverse alpha
PASS fixture
```

Những dòng `[fixture-provider]` được ghi ra stderr, còn `PASS` ghi ra stdout. Thứ tự sau khi terminal hoặc CI trộn hai stream có thể khác ví dụ; không viết test phụ thuộc thứ tự log.

Nếu assertion thất bại, exception làm main kết thúc bất thường, và Java launcher thông thường trả exit code khác 0.

## 10. Biên dịch và chạy trên Windows PowerShell

Từ thư mục `resolver-lab`, tạo build folder và biên dịch:

```powershell
New-Item -ItemType Directory -Force -Path 'build\classes' | Out-Null
javac -encoding UTF-8 -d build/classes src/demo/FixtureResolverProvider.java src/demo/ResolverProbe.java
```

Đóng gói và kiểm tra JAR:

```powershell
jar --create --file build/fixture-provider.jar -C build/classes . -C src META-INF/services/java.net.spi.InetAddressResolverProvider
jar --list --file build/fixture-provider.jar
```

Tạo biến đường dẫn tuyệt đối:

```powershell
$hosts = (Resolve-Path '.\lab-hosts').Path
```

Chạy baseline trong JVM A:

```powershell
java "-Djdk.net.hosts.file=$hosts" -cp build/classes demo.ResolverProbe baseline
if ($LASTEXITCODE -ne 0) {
    throw "Baseline JVM failed"
}
```

Chạy fixture trong JVM B:

```powershell
java "-Djdk.net.hosts.file=$hosts" -cp build/fixture-provider.jar demo.ResolverProbe fixture
if ($LASTEXITCODE -ne 0) {
    throw "Fixture JVM failed"
}
```

Mỗi lệnh `java` tạo một JVM mới. Do classpath ở mỗi lệnh chỉ có một entry, không cần xử lý ký tự phân cách classpath Windows (`;`) hay Unix (`:`).

## 11. Vì sao cần JVM riêng?

Resolver được cài theo **phạm vi toàn JVM**, không theo test method hay thread. Provider được chọn khi `InetAddress` khởi tạo system-wide resolver sau bootstrap, rồi được dùng cho các lookup tiếp theo.

Không nên viết test theo giả định:

```java
// Not a valid isolation strategy:
// 1. Resolve a name, installing a resolver.
// 2. Load a provider JAR dynamically.
// 3. Expect the existing JVM to switch resolver.
```

Thêm JAR bằng custom class loader không bảo đảm thay resolver đã cài. ServiceLoader của cơ chế này dùng **system class loader**, còn `InetAddress` cũng cache kết quả phân giải thành công/thất bại.

Sơ đồ đúng:

```text
Test runner
    |
    +-- JVM A
    |     classpath: build/classes
    |     resolver: built-in
    |     alpha.fixture.test -> UnknownHostException
    |
    +-- JVM B
          classpath: build/fixture-provider.jar
          resolver: fixture provider
          alpha.fixture.test -> 127.0.0.42
```

Trong JUnit hoặc test framework khác, nên fork subprocess cho những scenario cần lựa chọn resolver khác nhau. Không phụ thuộc thứ tự thực thi các test case trong một JVM.

### 11.1. Tùy chọn tự fork bằng ProcessBuilder

Đoạn sau có thể lưu thành `ForkedResolverTest.java` nếu muốn tự động hóa:

```java
import java.nio.file.Path;
import java.util.List;

public final class ForkedResolverTest {
    static int run(Path javaExe, Path hosts, String cp, String mode)
            throws Exception {

        List<String> command = List.of(
            javaExe.toString(),
            "-Djdk.net.hosts.file=" + hosts.toAbsolutePath(),
            "-cp",
            cp,
            "demo.ResolverProbe",
            mode
        );

        Process child = new ProcessBuilder(command)
            .inheritIO()
            .start();

        return child.waitFor();
    }

    public static void main(String[] args) throws Exception {
        boolean windows = System.getProperty("os.name")
            .startsWith("Windows");

        Path javaExe = Path.of(
            System.getProperty("java.home"),
            "bin",
            windows ? "java.exe" : "java"
        );

        Path hosts = Path.of("lab-hosts");

        int baseline = run(
            javaExe, hosts, "build/classes", "baseline"
        );
        int fixture = run(
            javaExe, hosts, "build/fixture-provider.jar", "fixture"
        );

        if (baseline != 0 || fixture != 0) {
            throw new AssertionError(
                "Child JVM failures: " + baseline + ", " + fixture
            );
        }
        System.out.println("PASS isolated JVM runs");
    }
}
```

Trong CI, cần thêm timeout và dọn child process khi quá hạn để không giữ job vô thời hạn. Với bài lab cơ bản, hai lệnh `java` ở phần 9 hoặc 10 đã đủ để kiểm tra riêng hai JVM.


## 12. Bảng test tổng hợp

| Case | JVM baseline | JVM fixture | Tiêu chí xác nhận |
| --- | --- | --- | --- |
| `alpha.fixture.test` | Không tìm thấy | `127.0.0.42` | Chỉ JVM có provider áp dụng fixture. |
| `beta.fixture.test` | Không tìm thấy | `127.0.0.43` | Provider trả đúng mapping thứ hai. |
| `ALPHA.FIXTURE.TEST` | Không có mapping | `127.0.0.42` | Không phân biệt chữ hoa/thường của hostname. |
| `missing.fixture.test` | Không có mapping | `UnknownHostException` | Không fallback ra DNS. |
| `delegated.example.test` | `127.0.0.88` | `127.0.0.88` | Fallback tới built-in resolver đã cấu hình hosts file. |
| Raw IP `127.0.0.42` reverse | Tùy mapping built-in | `alpha.fixture.test` | Hai chiều fixture nhất quán. |

Có hai mức khẳng định:

- **Về hợp đồng:** provider được ServiceLoader chọn và được cài system-wide; `lookupByName` và `lookupByAddress` phải tuân theo API.
- **Về dữ liệu fixture:** các hostname và IP cụ thể chỉ do bài lab quy định. Chúng không phải IP của một máy chủ thật và không đòi hỏi dịch vụ mạng đang lắng nghe.

Không dùng `ping` làm phép thử duy nhất cho SPI. Công cụ `ping` của hệ điều hành không chạy trong JVM chứa provider nên có thể dùng resolver khác. Kiểm chứng đúng là gọi `InetAddress` **trong cùng JVM đã nạp provider**.

## 13. Trường hợp âm tính và giới hạn lookup policy

### 13.1. Unknown fixture không được delegate

Phần quan trọng:

```java
if (bytes == null || !supportsIPv4) {
    throw new UnknownHostException(host);
}
```

Nếu không có mapping, provider ném `UnknownHostException`, kể cả khi built-in resolver có thể phân giải một hostname có hình dạng tương tự. Đây là hành vi có chủ ý để không tạo phụ thuộc bên ngoài vùng fixture.

### 13.2. Không tự tạo IPv6 khi thiếu fixture

`LookupPolicy` có thể yêu cầu IPv4, IPv6 hoặc cả hai. Provider của lab chỉ có IPv4.

Nếu policy chỉ cho phép IPv6, trả IPv4 sẽ vi phạm kỳ vọng family. Vì vậy provider từ chối lookup đó. Khi mở rộng dual-stack, cần:

1. Cấp fixture IPv6 hợp lệ (16 byte).
2. Trả đúng family được yêu cầu.
3. Xếp thứ tự IPv4/IPv6 theo flag ưu tiên nếu có.
4. Đảm bảo reverse mapping nhất quán.
5. Kiểm thử trên cả môi trường có/không có hỗ trợ IPv6 của hệ điều hành.

Không nên ép mọi test thành công bằng cách giả vờ một địa chỉ IPv4 là IPv6.

### 13.3. Không bịa kết quả reverse

`lookupByAddress` chỉ biết hai byte arrays fixture. Với địa chỉ khác, nó delegate. Điều này đúng hơn việc trả một hostname tùy ý cho mọi IP. Kết quả reverse không có mapping có thể là `UnknownHostException`, tùy hành vi resolver built-in.

## 14. Vì sao cache khiến kết quả có vẻ không thay đổi?

`InetAddress` cache kết quả cả forward/reverse lookup, bao gồm lookup thất bại. Khi bạn sửa fixture trong code hoặc sửa hosts file rồi chạy tiếp trong cùng process, việc lookup có thể dùng kết quả cũ.

Một số security properties liên quan:

| Property | Chức năng |
| --- | --- |
| `networkaddress.cache.ttl` | Thời gian lưu lookup thành công. |
| `networkaddress.cache.negative.ttl` | Thời gian lưu lookup thất bại. |
| `networkaddress.cache.stale.ttl` | Hành vi giữ kết quả stale nếu có hỗ trợ và cấu hình. |

Đây là các **security properties** của JDK, không phải các system properties thông thường. Không viết `-Dnetworkaddress.cache.ttl=0` rồi khẳng định cache đã tắt: Oracle ghi rõ những thuộc tính này không được thiết lập bằng `-D` hoặc `System.setProperty()`.

Trong bài lab, cách đơn giản và nhất quán nhất là **khởi động JVM mới cho mỗi cấu hình**. Không cần sửa policy cache toàn JDK chỉ để tạo một phép thử fixture.

Nếu cần thiết lập TTL trong hệ thống thực, hãy dùng cơ chế security property được JDK tài liệu hóa và đánh giá ảnh hưởng tới hiệu năng/độ tin cậy.

## 15. Các nguyên tắc an toàn khi triển khai SPI

Custom resolver có ảnh hưởng tới toàn bộ name resolution trong JVM, không chỉ một hàm test cụ thể. Những lỗi sau có thể ảnh hưởng rộng:

- Không resolve được hostname của dịch vụ ngoài fixture.
- Trả sai IP và kết nối nhầm đích.
- Tự gọi `InetAddress.getByName` trong provider gây vòng đệ quy.
- Chạy logic phức tạp trong constructor/get gây deadlock hoặc class-loader cycle.
- Để hostname fixture ngoài bảng rơi xuống DNS hoặc resolver thật.
- Không tôn trọng IPv4/IPv6 policy.
- Thêm provider fixture vào production JAR ngoài ý muốn.
- Coi log startup là bằng chứng duy nhất thay cho assertions.

Khuyến nghị:

1. Giữ constructor và `get(Configuration)` nhẹ, không gọi network.
2. Đặt các tên fixture trong namespace riêng dưới `.test`.
3. Không delegate hostname thuộc namespace fixture nhưng thiếu mapping.
4. Dùng `InetAddress.getByAddress` để xây địa chỉ từ byte đã biết.
5. Delegate bằng `configuration.builtinResolver()`, không bằng system-wide `InetAddress`.
6. Tuân thủ hợp đồng `LookupPolicy`, `UnknownHostException`, null và độ dài raw IP.
7. Đừng dùng nhiều provider nếu test đòi biết chắc provider nào được chọn.
8. Fork JVM khi thay cấu hình provider, tránh phụ thuộc cache.
9. Không để credentials, hostname nhạy cảm hoặc địa chỉ production trong fixtures.
10. Không nhầm hoạt động DNS với kết nối TCP/HTTP: phân giải IP thành công không đảm bảo một dịch vụ có thể truy cập.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy `[fixture-provider] installed` | Descriptor không nằm trong classpath JAR hoặc provider khác được chọn. | Xem `jar --list` và descriptor. |
| `ServiceConfigurationError` | Sai class name, thiếu public no-arg constructor hoặc dependency. | Kiểm tra package/classpath và nội dung service descriptor. |
| JVM fixture vẫn không tìm thấy alpha | Không cài provider, mapping sai, policy không cho IPv4. | Xem startup stderr, đúng JAR và policy. |
| JVM baseline lại thấy alpha fixture | Tệp service bị chép vào `build/classes` hoặc hosts file có mapping alpha. | Tách rõ classpath baseline và hosts file. |
| Fallback không phân giải delegated hostname | Sai đường dẫn hosts file, không delegate hoặc file trống. | Dùng đường dẫn tuyệt đối và đọc lại mapping. |
| Reverse trả IP dạng số | Không tìm được tên hoặc không xác minh được mapping hai chiều. | Kiểm tra `lookupByAddress` cùng forward mapping. |
| Không thấy mọi lần lookup trong log provider | Có cache, lookup đặc biệt hoặc log đã bị trộn stream. | Chạy JVM mới, dùng tên chưa tra và assertion. |
| Test lâu hoặc phụ thuộc mạng | Host ngoài namespace đang được delegate tới mạng bên ngoài. | Cấu hình `jdk.net.hosts.file` với tên thử nghiệm. |
| Test pass khi chạy đơn lẻ nhưng fail khi chạy chung | JVM chung đã chọn resolver khác hoặc cache đã có dữ liệu. | Fork mỗi cấu hình thành child JVM. |
| IPv6-only lookup trả lỗi | Lab chỉ định IPv4 fixtures. | Bổ sung family IPv6 nếu tình huống yêu cầu. |
| Có nhiều provider và kết quả không ổn định | Provider discovery order không được đặc tả. | Chỉ đóng gói một provider trong test. |
| `java.net.spi` không có API mong đợi | Dùng JDK trước 18 hoặc compiler/runtime không cùng version. | Kiểm tra `java -version`, `javac -version`. |

### 16.1. Checklist khi kiểm tra kết quả trên CI

- [ ] Hai JVM dùng cùng JDK phù hợp và đúng đường dẫn Java launcher.
- [ ] Baseline classpath không có service descriptor.
- [ ] Fixture JAR chứa class provider và service descriptor.
- [ ] Hosts file nằm tại đường dẫn được truyền ở JVM startup.
- [ ] Baseline báo `UnknownHostException` cho alpha.
- [ ] Fixture trả IP alpha/beta đúng byte.
- [ ] Unknown fixture thất bại ngay trong provider.
- [ ] Fallback của hostname ngoài fixture trả `127.0.0.88`.
- [ ] Reverse lookup của `127.0.0.42` trả alpha.
- [ ] Cả hai process có exit code 0.
- [ ] Không chạy networking bên ngoài ngoài phạm vi test.
- [ ] Không dùng cache hoặc kết quả tiến trình cũ làm bằng chứng.

## 17. Bài tập tự kiểm tra

1. Thêm `gamma.fixture.test` ánh xạ tới `127.0.0.44`, bổ sung cả reverse và assertions.
2. Thử `ALPHA.FIXTURE.TEST.` (có dấu chấm cuối) và giải thích vai trò `normalize`.
3. Xóa một entry đã biết rồi chạy JVM mới; xác nhận `UnknownHostException`.
4. Thêm entry `other.example.test` vào `lab-hosts` và kiểm chứng built-in fallback.
5. Bỏ service descriptor khỏi fixture JAR để thấy provider không được ServiceLoader tìm thấy.
6. Đổi tên class trong descriptor thành một lớp không tồn tại; ghi nhận lỗi discovery.
7. Giải thích vì sao thứ tự nhiều provider không phải cơ sở cho test deterministic.
8. Chạy lại phép thử với một JVM mới sau khi thay fixture; đối chiếu với nguy cơ cache trong một JVM dùng lâu.
9. Viết test runner fork hai JVM bằng `ProcessBuilder` và kiểm tra exit codes.
10. Mở rộng dữ liệu fixture để có IPv6, lọc theo `LookupPolicy`.
11. Chứng minh `getHostName()` trên `InetAddress` đã gắn hostname không nhất thiết tạo reverse lookup.
12. Giải thích sự khác biệt giữa phân giải hostname và việc có service TCP thực sự lắng nghe tại IP đó.
13. So sánh ưu/nhược điểm của `jdk.net.hosts.file` với custom `InetAddressResolverProvider` cho một CI test.
14. Viết báo cáo thực hành gồm JDK version, hai lệnh launch, classpath, địa chỉ trả về, các exception dự kiến, exit code.

**Tiêu chí hoàn thành:** bạn triển khai được `InetAddressResolverProvider` public, đăng ký bằng ServiceLoader, xác minh fixture hostname/IP và reverse mapping, giữ fallback tới built-in resolver, ngăn unknown fixture đi ra DNS, và chạy hai cấu hình resolver trong **hai JVM riêng** với assertions kiểm chứng.

## 18. Tài liệu tham khảo

- [OpenJDK JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): giới thiệu SPI trong Java 18 và động cơ thiết kế.
- [Oracle Java SE 26 — InetAddressResolverProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): ServiceLoader, thời điểm chọn resolver system-wide, startup và deadlock.
- [Oracle Java SE 26 — InetAddressResolver](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng forward/reverse lookup và ngoại lệ.
- [Oracle Java SE 26 — LookupPolicy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html): flags IPv4/IPv6 và thứ tự.
- [Oracle Java SE 25 — Configuration API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html): lấy built-in resolver để delegate.
- [Oracle Java SE 26 — InetAddress API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): `getAllByName`, `getByAddress` và `getCanonicalHostName`.
- [Oracle Java SE 26 — Networking Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html): TTL/cache và security properties.
- [Oracle Java Networking](https://docs.oracle.com/en/java/javase/25/core/java-networking.html): `jdk.net.hosts.file` trong thử nghiệm ánh xạ hostname.
- [IANA — .test](https://www.iana.org/domains/root/db/test): domain dành riêng cho test.
