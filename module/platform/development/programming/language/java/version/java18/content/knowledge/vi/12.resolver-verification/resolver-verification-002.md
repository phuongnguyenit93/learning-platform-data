# Kiểm thử trực tiếp resolver và kiểm thử tích hợp qua InetAddress: hai phạm vi cần tách biệt

## 1. Mục tiêu và vấn đề cần phân biệt

Kể từ Java 18, **JEP 418 – Internet-Address Resolution SPI** bổ sung `java.net.spi.InetAddressResolver` và `InetAddressResolverProvider`. Cơ chế này vẫn phù hợp trên JDK hiện đại để kiểm thử phân giải hostname mà không phụ thuộc DNS công cộng.

Giả sử bảng dữ liệu fixture xác định như sau:

| Tên máy | IPv4 | IPv6 |
| --- | --- | --- |
| `api.qa.invalid` | `192.0.2.10` | `2001:db8::10` |
| `db.qa.invalid` | `192.0.2.20` | Không có |
| `missing.qa.invalid` | Không có | Không có |

`.invalid` là miền dành riêng; `192.0.2.0/24` và `2001:db8::/32` là các dải IP dành cho tài liệu. Các IP ở đây phục vụ kiểm thử ánh xạ, **không dùng để chứng minh kết nối TCP hoặc HTTP thành công**.

Ta cần trả lời **hai câu hỏi riêng**:

1. **Bản thân resolver đã đúng hợp đồng?** Khi được truyền `LookupPolicy.IPV6`, nó lọc IPv4; khi yêu cầu `IPV6_FIRST`, nó ưu tiên IPv6; khi không có tên/IP, nó ném `UnknownHostException`; tra cứu ngược trả đúng hostname.
2. **JVM đã sử dụng resolver đó từ `InetAddress`?** `ServiceLoader` có tìm thấy provider, `get(Configuration)` có được gọi, `InetAddress.getAllByName` có nhận đúng kết quả không?

Nếu chỉ kiểm tra (1), sai đường dẫn `META-INF/services` vẫn có thể lọt qua. Nếu chỉ kiểm tra (2), ta không chủ động ép `LookupPolicy` hoặc thử riêng `lookupByAddress(byte[])`.

### Sơ đồ hai đường kiểm thử

```text
KIỂM THỬ TRỰC TIẾP (contract)
Test -> FixedProvider.newResolverForTest()
     -> resolver.lookupByName(hostname, policy)
     -> resolver.lookupByAddress(ipBytes)
     -> assert dữ liệu, thứ tự, ngoại lệ

KIỂM THỬ TÍCH HỢP (SPI)
Test -> InetAddress.getAllByName(hostname)
     -> cache/đường phân giải của InetAddress
     -> ServiceLoader -> FixedProvider.get(configuration)
     -> resolver.lookupByName(hostname, policy do JVM chọn)
     -> assert kết quả và dấu hiệu provider được cài
```

Bộ nhớ đệm có thể khiến một lời gọi `InetAddress` được phục vụ mà không gọi lại resolver. Resolver cấp JVM được lựa chọn khi xảy ra lần phân giải tên đầu tiên sau khi VM hoàn tất khởi động; nhiều lời gọi sau đó không tạo provider mới.

## 2. Bảng so sánh phạm vi

| Câu hỏi cần kiểm tra | Gọi trực tiếp `InetAddressResolver` | Gọi qua `InetAddress` |
| --- | --- | --- |
| Mapping hostname → IP có đúng? | Có | Có |
| Truyền chính xác `LookupPolicy.IPV4`, `IPV6` và thứ tự? | **Có** | **Không**, JVM tự quyết |
| Test trực tiếp `lookupByAddress(byte[])`? | **Có** | Không trực tiếp |
| Kiểm tra ngoại lệ `UnknownHostException`? | Có | Có |
| Phát hiện thiếu/sai `META-INF/services`? | Không | **Có** |
| Chứng minh JVM đã chọn custom provider? | Không | **Có** |
| Bị ảnh hưởng bởi `InetAddress` cache? | Không trong test trực tiếp | Có thể |
| Cần tiến trình JVM mới khi đổi provider? | Không | **Có** |
| Mục đích | Contract/unit test | SPI integration/smoke test |

**Nguyên tắc:** Kiểm thử trực tiếp dùng để phát hiện lỗi trong thuật toán/contract của resolver. Kiểm thử tích hợp dùng để phát hiện lỗi wiring, classpath/module-path, vòng đời và đường gọi `InetAddress`. Cần cả hai khi triển khai resolver thật.

## 3. Provider fixture: một nguồn dữ liệu, hai cách kiểm tra

Các tệp ví dụ dành cho **JDK 18 trở lên**, không cần thư viện ngoài:

```text
resolver-demo/
  src/demo/resolver/
    FixedProvider.java
    ResolverUnitCheck.java
    ResolverIntegrationCheck.java
  resources/META-INF/services/
    java.net.spi.InetAddressResolverProvider
```

Tạo `src/demo/resolver/FixedProvider.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class FixedProvider extends InetAddressResolverProvider {
    private static final String API = "api.qa.invalid";
    private static final String DB = "db.qa.invalid";

    private static final byte[] API_V4 = {(byte) 192, 0, 2, 10};
    private static final byte[] DB_V4 = {(byte) 192, 0, 2, 20};
    private static final byte[] API_V6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0x10
    };

    private static final AtomicInteger INSTALLATIONS = new AtomicInteger();

    // Constructor công khai, không tham số, theo quy tắc ServiceLoader.
    public FixedProvider() {}

    @Override
    public String name() {
        return "fixed-test-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        INSTALLATIONS.incrementAndGet();
        return newResolverForTest();
    }

    // Unit test có thể lấy một resolver mới mà không dùng ServiceLoader.
    public static InetAddressResolver newResolverForTest() {
        return new FixedResolver();
    }

    // Dấu hiệu phục vụ bài tích hợp: JVM đã gọi get(Configuration).
    public static int installations() {
        return INSTALLATIONS.get();
    }

    private static final class FixedResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
                throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            int flags = policy.characteristics();
            List<InetAddress> found = new ArrayList<>(2);

            if (API.equalsIgnoreCase(host)) {
                if ((flags & LookupPolicy.IPV4) != 0) {
                    found.add(InetAddress.getByAddress(API, API_V4));
                }
                if ((flags & LookupPolicy.IPV6) != 0) {
                    found.add(InetAddress.getByAddress(API, API_V6));
                }
            } else if (DB.equalsIgnoreCase(host)) {
                if ((flags & LookupPolicy.IPV4) != 0) {
                    found.add(InetAddress.getByAddress(DB, DB_V4));
                }
            }

            if (found.isEmpty()) {
                throw new UnknownHostException(host);
            }
            // Dữ liệu được thêm IPv4 trước; đảo nếu muốn IPv6 trước.
            if ((flags & LookupPolicy.IPV6_FIRST) != 0) {
                Collections.reverse(found);
            }
            return found.stream();
        }

        @Override
        public String lookupByAddress(byte[] address)
                throws UnknownHostException {
            Objects.requireNonNull(address, "address");
            if (address.length != 4 && address.length != 16) {
                throw new IllegalArgumentException(
                        "IP phải gồm 4 byte (IPv4) hoặc 16 byte (IPv6)");
            }
            if (Arrays.equals(address, API_V4)
                    || Arrays.equals(address, API_V6)) {
                return API;
            }
            if (Arrays.equals(address, DB_V4)) {
                return DB;
            }
            throw new UnknownHostException("IP không có trong fixture");
        }
    }
}
```

Những chi tiết cốt lõi:

- `newResolverForTest()` giúp test trực tiếp một instance mới mà không cài nó làm resolver cấp JVM.
- `get(Configuration)` là điểm tích hợp mà `InetAddress` sẽ gọi sau khi tìm thấy provider. Biến `INSTALLATIONS` là bằng chứng có thể quan sát được.
- `InetAddress.getByAddress(host, bytes)` tạo giá trị IP từ byte, **không hỏi DNS**, vì vậy không gây phân giải tên lồng nhau trong resolver.
- Không chuyển tiếp hostname không có trong fixture tới `configuration.builtinResolver()`: nếu fallback, test có thể phụ thuộc mạng thật.
- Khi policy không chấp nhận họ địa chỉ nào hiện có, `lookupByName` ném `UnknownHostException`; `lookupByAddress` từ chối byte sai độ dài bằng `IllegalArgumentException`.

## 4. Test trực tiếp hợp đồng resolver

Tạo `src/demo/resolver/ResolverUnitCheck.java`:

```java
package demo.resolver;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;

public final class ResolverUnitCheck {
    @FunctionalInterface
    interface CheckedCall {
        void run() throws UnknownHostException;
    }

    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    private static void expectUnknown(CheckedCall operation) {
        try {
            operation.run();
            throw new AssertionError("Phải ném UnknownHostException");
        } catch (UnknownHostException expected) {
            // Đúng kỳ vọng.
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddressResolver resolver = FixedProvider.newResolverForTest();

        // Nhánh 1: chỉ IPv4, đồng thời thử hostname viết hoa.
        var onlyV4 = resolver.lookupByName(
                "API.QA.INVALID", LookupPolicy.of(LookupPolicy.IPV4)).toList();
        require(onlyV4.size() == 1, "Cần đúng một IP");
        require(onlyV4.get(0) instanceof Inet4Address, "Sai họ IP");
        require("192.0.2.10".equals(onlyV4.get(0).getHostAddress()),
                "Sai dữ liệu IPv4");

        // Nhánh 2: yêu cầu cả IPv4/IPv6 nhưng ưu tiên IPv6.
        var both = resolver.lookupByName("api.qa.invalid", LookupPolicy.of(
                LookupPolicy.IPV4 | LookupPolicy.IPV6
                | LookupPolicy.IPV6_FIRST)).toList();
        require(both.size() == 2, "Cần đúng hai địa chỉ");
        require(both.get(0) instanceof Inet6Address, "IPv6 phải đứng trước");
        require(both.get(1) instanceof Inet4Address, "IPv4 phải đứng sau");

        // Nhánh 3: reverse lookup trực tiếp trên byte IP.
        require("api.qa.invalid".equals(
                resolver.lookupByAddress(new byte[] {(byte) 192, 0, 2, 10})),
                "Sai kết quả tra cứu ngược");

        // Nhánh 4: hostname không có trong fixture.
        var ipv4 = LookupPolicy.of(LookupPolicy.IPV4);
        expectUnknown(() -> resolver.lookupByName(
                "missing.qa.invalid", ipv4).toList());

        // Nhánh 5: hostname chỉ có IPv4 nhưng yêu cầu duy nhất IPv6.
        var ipv6 = LookupPolicy.of(LookupPolicy.IPV6);
        expectUnknown(() -> resolver.lookupByName(
                "db.qa.invalid", ipv6).toList());

        // Nhánh 6: không có bản ghi reverse.
        expectUnknown(() -> resolver.lookupByAddress(
                new byte[] {(byte) 192, 0, 2, 99}));

        // Nhánh 7: độ dài byte không hợp lệ.
        try {
            resolver.lookupByAddress(new byte[] {1, 2, 3});
            throw new AssertionError("Phải ném IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Đúng kỳ vọng.
        }

        require(FixedProvider.installations() == 0,
                "Unit test không được kích hoạt đăng ký SPI");
        System.out.println("PASS: direct resolver contract");
    }
}
```

Bài này kiểm tra đầy đủ cả `lookupByName(String, LookupPolicy)` lẫn `lookupByAddress(byte[])`. Ta cấp trực tiếp cờ `IPV4`, `IPV6`, `IPV6_FIRST`, nên không cần đoán chính sách địa chỉ mà JVM sẽ sử dụng.

Trường hợp `LookupPolicy.of` nhận bộ cờ không hợp lệ (không có `IPV4`/`IPV6` hoặc đặt đồng thời `IPV4_FIRST` và `IPV6_FIRST`) phải ném `IllegalArgumentException`. Tuy nhiên, đó là **hợp đồng của lớp JDK `LookupPolicy`**, nên test nó chỉ khi muốn khảo sát API hoặc kiểm tra logic xây policy của ứng dụng; không cần lặp lại trong mọi unit test của resolver.

**Điều chưa được chứng minh:** JVM có thể không biết provider này tồn tại nếu thiếu tệp đăng ký dịch vụ. Một unit test PASS chưa chứng minh ứng dụng thật đã sử dụng SPI.

## 5. Test tích hợp qua InetAddress

### 5.1. Khai báo provider

Trong dự án dùng classpath, tạo tệp:

```text
resources/META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung tệp chính xác:

```text
demo.resolver.FixedProvider
```

Đây là tên lớp được `ServiceLoader` tải. Provider phải là lớp concrete, public, có constructor không tham số. Nếu đóng gói theo **named module**, có thể đăng ký bằng khai báo `provides java.net.spi.InetAddressResolverProvider with demo.resolver.FixedProvider;` trong `module-info.java`.

JVM chọn một `InetAddressResolver` cấp hệ thống khi bắt đầu phân giải tên sau khi khởi động xong. Nếu không có provider phù hợp, JVM dùng resolver tích hợp; nếu có nhiều provider, thứ tự tìm thấy là đặc thù triển khai. Nên cho suite tích hợp một provider duy nhất.

### 5.2. Chạy API ở bề mặt thật của ứng dụng

Tạo `src/demo/resolver/ResolverIntegrationCheck.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;

public final class ResolverIntegrationCheck {
    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) throws Exception {
        // Đường gọi do JDK chủ động chọn resolver qua SPI.
        InetAddress[] actual = InetAddress.getAllByName("api.qa.invalid");

        // Xác nhận JVM đã cài đúng custom provider.
        require(FixedProvider.installations() == 1,
                "FixedProvider không được InetAddress cài đặt");

        // Không giả định JDK/máy test nhất thiết bật cả hai họ IP.
        require(actual.length >= 1 && actual.length <= 2,
                "Số địa chỉ ngoài dự kiến: " + actual.length);

        InetAddress expectedV4 = InetAddress.getByAddress(
                new byte[] {(byte) 192, 0, 2, 10});
        InetAddress expectedV6 = InetAddress.getByAddress(new byte[] {
                0x20, 0x01, 0x0d, (byte) 0xb8, 0, 0, 0, 0,
                0, 0, 0, 0, 0, 0, 0, 0x10
        });

        for (InetAddress ip : actual) {
            require(ip.equals(expectedV4) || ip.equals(expectedV6),
                    "IP nằm ngoài fixture: " + ip.getHostAddress());
        }

        try {
            InetAddress.getAllByName("missing.qa.invalid");
            throw new AssertionError("Hostname không có phải thất bại");
        } catch (UnknownHostException expected) {
            // Đúng kỳ vọng.
        }

        require(FixedProvider.installations() == 1,
                "Provider được cài lại ngoài dự kiến");
        System.out.println("PASS: InetAddress -> ServiceLoader -> provider");
        System.out.println("Resolved: " + Arrays.toString(actual));
    }
}
```

Hai điểm quan trọng:

- `InetAddress.getAllByName` là **đường truy cập thực** của ứng dụng. Kết quả dương tính lấy từ tên `api.qa.invalid` và xác nhận `installations() == 1` giúp phát hiện thiếu service descriptor, provider sai hoặc JVM đang sử dụng resolver khác.
- `InetAddress` tự quyết định chính sách IPv4/IPv6 theo môi trường và system properties. Do đó bài tích hợp xác nhận các IP thuộc fixture, còn bài trực tiếp ở phần 4 kiểm tra chính xác thứ tự `IPV6_FIRST`.

Không dùng một ca âm tính duy nhất làm bằng chứng SPI: `missing.qa.invalid` có thể cũng thất bại trên resolver mặc định. Phải có ca **dương tính** mà chỉ fixture mới cung cấp kết quả mong đợi.

### 5.3. Chạy bằng PowerShell trên Windows

Từ thư mục `resolver-demo`, chạy trong hai tiến trình Java riêng. Thư mục `out/unit` **không có** service descriptor; `out/it` **có** descriptor.

```powershell
$javaFiles = @(
  "src/demo/resolver/FixedProvider.java",
  "src/demo/resolver/ResolverUnitCheck.java",
  "src/demo/resolver/ResolverIntegrationCheck.java"
)

New-Item -ItemType Directory -Force out/unit | Out-Null
javac --release 18 -d out/unit $javaFiles
java -cp out/unit demo.resolver.ResolverUnitCheck

New-Item -ItemType Directory -Force out/it/META-INF/services | Out-Null
javac --release 18 -d out/it $javaFiles
Copy-Item "resources/META-INF/services/java.net.spi.InetAddressResolverProvider" "out/it/META-INF/services/"
java -cp out/it demo.resolver.ResolverIntegrationCheck
```

Hai thông báo cần thấy:

```text
PASS: direct resolver contract
PASS: InetAddress -> ServiceLoader -> provider
```

Bài tích hợp còn in mảng `Resolved: [...]`; số lượng IPv4/IPv6 có thể khác nhau theo policy của JVM. Lệnh `--release 18` giới hạn API cho Java 18 để mã vẫn biên dịch và chạy trên JDK 18 trở lên. Trên Linux/macOS, dùng các lệnh tương đương `mkdir -p`, `cp` và `java -cp`.

Nếu đang dùng Maven/Gradle, cấu hình tương đương hai suite với classpath/tài nguyên tách biệt và JVM fork cho ca SPI. **Không chạy test tích hợp cùng JVM đã cài một provider khác** hoặc với tham số `-Djdk.net.hosts.file` vì sẽ làm khó xác định đường phân giải mà bài đang đo.

## 6. Đọc kết quả và phát hiện lỗi bằng ma trận

| Lỗi cần tìm | Unit/contract | Integration |
| --- | :---: | :---: |
| `IPV6_FIRST` không đảo thứ tự | ✅ | Không bảo đảm |
| Truy vấn chỉ IPv6 vẫn trả IPv4 | ✅ | Không bảo đảm |
| `lookupByAddress` trả tên sai | ✅ | Không kiểm trực tiếp |
| Tên ngoài fixture bị trả nhầm IP | ✅ | ✅ |
| Thiếu `META-INF/services` | ❌ | ✅ |
| Tên class provider trong service file viết sai | ❌ | ✅ |
| JVM chọn resolver tích hợp hoặc provider khác | ❌ | ✅ |
| Cache `InetAddress` che một lần tra cứu mới | Không | Có thể |
| Kết nối TCP/HTTP thật đến máy đích thành công | ❌ | ❌ |

Hãy chạy thêm một **ca thử nghiệm phát hiện lỗi wiring**: chạy `java -cp out/unit demo.resolver.ResolverIntegrationCheck`. Không có service descriptor thì ca tích hợp sẽ thất bại, nhờ vậy biết chắc assertion có khả năng phát hiện một provider chưa được đăng ký. Tên `.invalid` cùng địa chỉ tài liệu giúp bài kiểm thử không phụ thuộc DNS công cộng.

## 7. Những sai lầm quan trọng

### 7.1. Cho rằng newResolverForTest() có hiệu lực toàn JVM

```java
var resolver = FixedProvider.newResolverForTest();
var result = resolver.lookupByName("api.qa.invalid",
        InetAddressResolver.LookupPolicy.of(
                InetAddressResolver.LookupPolicy.IPV4));
```

Đây là **unit test**, không có thao tác cài provider. `InetAddress.getAllByName` vẫn dùng resolver cấp JVM theo cấu hình chạy ứng dụng.

### 7.2. Dùng địa chỉ IP dạng chuỗi để kiểm chứng SPI

```java
InetAddress.getByName("192.0.2.10");
```

Với địa chỉ literal, `InetAddress` có thể phân tích IP ngay mà không chạy lookup hostname. Hãy dùng tên fixture `api.qa.invalid` cho ca SPI. `InetAddress.getByAddress(host, bytes)` cũng chỉ tạo đối tượng từ byte đã có mà không xác thực ánh xạ bằng resolver.

### 7.3. Nhầm getHostName() với reverse lookup thực tế

Một `InetAddress` tạo qua `getByAddress("api.qa.invalid", bytes)` có sẵn hostname. `getHostName()` có thể trả giá trị này mà không gọi `lookupByAddress`. `getCanonicalHostName()` có ngữ nghĩa riêng, có thể thêm bước xác nhận và chịu cache; không nên lấy đó làm phép thay thế cho kiểm thử trực tiếp `lookupByAddress(byte[])`.

Nếu muốn kiểm tra reverse **tích hợp**, hãy thiết kế bài riêng với địa chỉ không mang tên sẵn, biết rõ hành vi kiểm tra thuận/ngược của `InetAddress` và cache, rồi mới xác nhận đường đi.

### 7.4. Mong có thể đổi provider ngay trong cùng JVM

Sau khi `InetAddress` đã cài resolver cấp JVM, sửa tệp service, thay class loader hoặc thay map cấu hình không buộc nó chọn provider mới. Nên chạy mỗi biến thể SPI trong JVM riêng biệt; không dựa vào thứ tự giữa các test trong cùng bộ máy JUnit.

### 7.5. Gắn số lần lookup với số lần gọi getAllByName()

`InetAddress` cache cả kết quả dương tính và âm tính; TTL tùy cấu hình JDK. Hai lần `getAllByName` liên tiếp có thể chỉ dẫn tới một lần `lookupByName`. Bộ đếm `INSTALLATIONS` trong ví dụ đo **số lần cài provider**, không phải số lần tra cứu hostname. Kiểm thử cache cần một suite riêng với điều kiện TTL xác định ngay từ đầu JVM.

### 7.6. Fallback về DNS công cộng mà không biết

`InetAddressResolverProvider.Configuration.builtinResolver()` cho phép ủy quyền truy vấn sang resolver mặc định. Đây là API hợp lệ cho ứng dụng thực, nhưng với fixture kiểm thử độc lập DNS, cách này tạo phụ thuộc ngoài ý muốn. Ví dụ cố tình từ chối hostname ngoài bảng bằng `UnknownHostException`.

## 8. Chiến lược áp dụng vào CI

Một dự án có thành phần gọi `InetAddress.getAllByName` nên duy trì hai nhóm:

1. **Contract tests:** tạo resolver mới cho mỗi case; dùng bảng hostname/IP cố định; bao phủ IPv4, IPv6, thứ tự, ngoại lệ, reverse lookup và null/byte sai độ dài nếu đó là một phần contract cần bảo đảm.
2. **SPI integration tests:** chạy một JVM mới với service descriptor đã đóng gói; có đúng một provider; xác nhận ít nhất một ca dương tính, một ca âm tính, một giá trị IP nằm trong fixture và dấu hiệu `provider.get` đã được gọi.

Các ca này xác minh **đúng hành vi phân giải tên**. Nếu muốn kiểm thử kết nối TCP, HTTPS, TLS hoặc routing, cần máy chủ test hoạt động trên loopback hay mạng kiểm thử riêng; việc resolver trả đúng địa chỉ chưa đủ chứng minh các giao thức đó hoạt động.

### Câu hỏi tự kiểm tra

- Tại sao xóa `META-INF/services` không làm `ResolverUnitCheck` thất bại?
- Điều gì khiến `ResolverIntegrationCheck` phát hiện thiếu provider dù truy vấn `missing.qa.invalid` vẫn ném `UnknownHostException`?
- Vì sao phép kiểm `IPV6_FIRST` nên nằm trong contract test?
- Vì sao một lần gọi `getCanonicalHostName()` không tự động chứng minh `lookupByAddress` đã được gọi?
- Khi cache đang bật, điều gì xảy ra nếu một test giả định `lookupByName` chạy đúng hai lần?

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418) – giới thiệu SPI trong Java 18.
- [Javadoc InetAddressResolver (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html) – `lookupByName`, `lookupByAddress` và ngoại lệ.
- [Javadoc LookupPolicy (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html) – cờ họ địa chỉ, thứ tự và kiểm tra policy hợp lệ.
- [Javadoc InetAddressResolverProvider (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html) – `ServiceLoader`, constructor, một resolver cấp JVM.
- [Javadoc InetAddress (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html) – phân giải tên, địa chỉ literal, cache và reverse lookup.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606), [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737), [RFC 3849](https://www.rfc-editor.org/rfc/rfc3849) – dữ liệu tên miền/IP dùng cho kiểm thử và tài liệu.
