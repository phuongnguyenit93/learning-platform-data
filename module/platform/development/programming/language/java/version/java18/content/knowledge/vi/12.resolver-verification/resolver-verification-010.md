# Đo số lần provider được gọi khi cache thành công hoặc cache thất bại đang có hiệu lực

## 1. Câu hỏi cần trả lời khi đo cache

Java 18 đưa vào **Internet-Address Resolution SPI** theo JEP 418. Trên JDK hiện đại, `InetAddress` có thể dùng implementation do `InetAddressResolverProvider` đăng ký để thực hiện phân giải tên và địa chỉ.

Khi kiểm tra cache, phải tách ba sự kiện:

1. **Provider được discovery và cài resolver:** `InetAddress` tìm provider, tạo instance và gọi `get(Configuration)` để nhận resolver.
2. **Resolver thực hiện lookup:** `InetAddress` gọi `lookupByName(host, policy)` khi cần phân giải hostname.
3. **Cache trả kết quả:** `InetAddress` trả kết quả thành công hoặc phát lại lỗi đã lưu mà không gọi resolver thêm lần nữa.

`provider.get(Configuration)` không phải bộ đếm số lần tra cứu hostname. Trong một JVM, provider được dùng để cài resolver hệ thống; các lần lookup tiếp theo đi vào resolver đã cài. Khi cache đang có hiệu lực, cùng một hostname được hỏi lại có thể không gọi `lookupByName` lần nữa.

Bài này đo hai trường hợp riêng:

- **Positive cache:** resolver trả địa chỉ thành công ở lần đầu; những lần gọi tiếp theo nhận lại địa chỉ từ cache.
- **Negative cache:** resolver ném `UnknownHostException` ở lần đầu; những lần gọi tiếp theo nhận lại lỗi đã cache mà không gọi resolver lại.

Ta cũng chạy một cấu hình TTL bằng 0 làm đối chứng. Khi cache bị tắt, cùng hostname được hỏi nhiều lần sẽ đi vào resolver nhiều lần.

## 2. Ba security properties liên quan đến address cache

`InetAddress` có cache cho kết quả phân giải tên thành công và thất bại. Cache phục vụ hiệu năng và an toàn; các lần phân giải lặp lại không nhất thiết truy cập naming service hoặc resolver provider.

| Security property | Áp dụng cho | Giá trị |
| --- | --- | --- |
| `networkaddress.cache.ttl` | Kết quả thành công | Số giây giữ kết quả positive; `0` là không cache, giá trị âm là cache vô hạn |
| `networkaddress.cache.negative.ttl` | Kết quả thất bại | Số giây giữ lỗi negative; `0` là không cache, giá trị âm là cache vô hạn |
| `networkaddress.cache.stale.ttl` | Kết quả positive đã hết TTL nhưng có thể tiếp tục dùng khi refresh thất bại | `0` hoặc không đặt nghĩa là không dùng stale entry |

TTL positive mặc định có thể phụ thuộc implementation và cấu hình JDK; negative cache mặc định của tài liệu Java SE 25 là 10 giây. Bài kiểm thử không dựa vào mặc định. Ta đặt rõ 60 giây cho cache-on và 0 giây cho cache-off để kết quả dễ lặp lại.

**Đây là Java security properties, không phải system properties.** Không cấu hình chúng bằng:

- `-Dnetworkaddress.cache.ttl=60`
- `-Dnetworkaddress.cache.negative.ttl=60`
- `System.setProperty("networkaddress.cache.ttl", "60")`

Các cách trên không thiết lập security properties tương ứng. Hãy dùng file security properties bổ sung hoặc `Security.setProperty(...)` trước khi chính sách cache được đọc. Trong bài này, file cấu hình riêng cho mỗi lần chạy giúp tránh phụ thuộc thứ tự khởi tạo class và tránh sửa file `java.security` của JDK.

### 2.1. Hai file cấu hình dành riêng cho bài test

Tạo `cache-on.security`:

```properties
networkaddress.cache.ttl=60
networkaddress.cache.negative.ttl=60
networkaddress.cache.stale.ttl=0
```

Tạo `cache-off.security`:

```properties
networkaddress.cache.ttl=0
networkaddress.cache.negative.ttl=0
networkaddress.cache.stale.ttl=0
```

JVM nạp file bổ sung bằng system property `java.security.properties=<URL>`. File này được **append** vào security properties mặc định; giá trị trùng tên trong file bổ sung sẽ ghi đè giá trị trước đó. Không dùng cú pháp hai dấu bằng `java.security.properties==...` trong bài này, vì cú pháp đó thay thế toàn bộ master security properties file của JDK.

Mỗi lần chạy dùng một file cấu hình và một JVM mới. `InetAddress` giữ cache trong tiến trình; đổi security property sau khi cache policy đã được đọc không làm cache hiện tại tự đổi TTL.

## 3. Dữ liệu fixture và cấu trúc dự án

Dùng hai hostname cố định:

| Hostname | Hành vi resolver | Kết quả |
| --- | --- | --- |
| `cache-positive.qa.invalid` | Thành công | `192.0.2.150` |
| `cache-negative.qa.invalid` | Thất bại | `UnknownHostException` |

`.invalid` là miền dành riêng cho mục đích đặc biệt; `192.0.2.0/24` là dải TEST-NET dành cho tài liệu. Resolver không gọi DNS công cộng và không gửi traffic tới địa chỉ fixture.

Cấu trúc thư mục:

```text
inetaddress-cache-counter/
  src/demo/cache/
    CacheProbeProvider.java
    CacheProbeResolver.java
    CacheProbeCheck.java
  out/
    META-INF/services/
      java.net.spi.InetAddressResolverProvider
  cache-on.security
  cache-off.security
```

Service descriptor `META-INF/services/java.net.spi.InetAddressResolverProvider` có đúng một dòng:

```text
demo.cache.CacheProbeProvider
```

Test gọi `InetAddress.getAllByName` với hostname giống hệt nhau trong cùng JVM. Không thêm dấu chấm cuối, không đổi chữ hoa/thường giữa các lần gọi và không thay đổi lookup policy trong cùng một phép đo. Nhờ vậy, mọi lần gọi đều có cùng khóa tra cứu về mặt ứng dụng.

## 4. Provider và resolver có counter riêng

Tạo `src/demo/cache/CacheProbeProvider.java`:

```java
package demo.cache;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class CacheProbeProvider extends InetAddressResolverProvider {
    private static final String PREFIX = "demo.cacheprobe.";
    private static final AtomicInteger CONSTRUCTOR_COUNT = new AtomicInteger();
    private static final AtomicInteger GET_COUNT = new AtomicInteger();

    public CacheProbeProvider() {
        System.setProperty(PREFIX + "provider.construct.count",
                Integer.toString(CONSTRUCTOR_COUNT.incrementAndGet()));
    }

    @Override
    public String name() {
        return "positive-negative-cache-probe";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        System.setProperty(PREFIX + "provider.get.count",
                Integer.toString(GET_COUNT.incrementAndGet()));
        return new CacheProbeResolver();
    }
}
```

Tạo `src/demo/cache/CacheProbeResolver.java`:

```java
package demo.cache;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class CacheProbeResolver implements InetAddressResolver {
    private static final String PREFIX = "demo.cacheprobe.";
    private static final String POSITIVE_HOST = "cache-positive.qa.invalid";
    private static final String NEGATIVE_HOST = "cache-negative.qa.invalid";
    private static final byte[] POSITIVE_ADDRESS =
            {(byte) 192, 0, 2, (byte) 150};

    private final AtomicInteger positiveCount = new AtomicInteger();
    private final AtomicInteger negativeCount = new AtomicInteger();

    private static void publish(String key, int count) {
        System.setProperty(PREFIX + key, Integer.toString(count));
    }

    @Override
    public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
            throws UnknownHostException {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(policy, "policy");

        if (POSITIVE_HOST.equals(host)) {
            publish("resolver.positive.count",
                    positiveCount.incrementAndGet());

            if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                throw new UnknownHostException(
                        "Fixture cần policy cho phép IPv4");
            }

            // Tạo địa chỉ từ byte, không tạo lookup lồng nhau.
            return Stream.of(InetAddress.getByAddress(host, POSITIVE_ADDRESS));
        }

        if (NEGATIVE_HOST.equals(host)) {
            publish("resolver.negative.count",
                    negativeCount.incrementAndGet());
            throw new UnknownHostException(
                    "Fixture không có địa chỉ cho " + host);
        }

        throw new UnknownHostException("Host ngoài fixture: " + host);
    }

    @Override
    public String lookupByAddress(byte[] addr) throws UnknownHostException {
        Objects.requireNonNull(addr, "addr");
        throw new UnknownHostException(
                "Bài kiểm tra chỉ đo forward lookup");
    }
}
```

Provider có hai bộ đếm độc lập:
- `provider.construct.count`: số instance provider được tạo.
- `provider.get.count`: số lần JDK gọi `get(Configuration)` để lấy resolver.

Resolver có hai bộ đếm khác:

- `resolver.positive.count`: số lần lookup hostname positive đi vào resolver.
- `resolver.negative.count`: số lần lookup hostname negative đi vào resolver.

Không dùng bộ đếm `provider.get.count` để kết luận số lần resolver chạy. Cache hit có thể làm hai bộ đếm lookup đứng yên trong khi provider vẫn đã được cài đặt bình thường.

## 5. Chương trình đo positive cache và negative cache

Tạo `src/demo/cache/CacheProbeCheck.java`:

```java
package demo.cache;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.security.Security;
import java.util.Arrays;

public final class CacheProbeCheck {
    private static final String PREFIX = "demo.cacheprobe.";
    private static final String POSITIVE_HOST = "cache-positive.qa.invalid";
    private static final String NEGATIVE_HOST = "cache-negative.qa.invalid";
    private static final String EXPECTED_ADDRESS = "192.0.2.150";
    private static final int ATTEMPTS = 5;

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static int count(String key) {
        String value = System.getProperty(PREFIX + key);
        return value == null ? 0 : Integer.parseInt(value);
    }

    private static void assertCount(String key, int expected) {
        int actual = count(key);
        require(actual == expected,
                key + ": expected " + expected + ", actual " + actual);
    }

    private static void verifyPositiveCache(boolean cacheEnabled)
            throws Exception {
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            InetAddress[] addresses = InetAddress.getAllByName(POSITIVE_HOST);
            require(addresses.length == 1,
                    "Fixture positive phải trả đúng một IPv4");
            require(EXPECTED_ADDRESS.equals(addresses[0].getHostAddress()),
                    "Sai IP fixture: " + Arrays.toString(addresses));

            int expectedResolverCalls =
                    cacheEnabled ? 1 : attempt;
            assertCount("resolver.positive.count", expectedResolverCalls);
            assertCount("provider.get.count", 1);
            assertCount("provider.construct.count", 1);
        }
    }

    private static void verifyNegativeCache(boolean cacheEnabled)
            throws Exception {
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            try {
                InetAddress.getAllByName(NEGATIVE_HOST);
                throw new AssertionError(
                        "Negative fixture phải ném UnknownHostException");
            } catch (UnknownHostException expected) {
                // Cả lỗi mới từ resolver và lỗi được phát lại từ cache đều hợp lệ.
            }

            int expectedResolverCalls =
                    cacheEnabled ? 1 : attempt;
            assertCount("resolver.negative.count", expectedResolverCalls);
            assertCount("provider.get.count", 1);
            assertCount("provider.construct.count", 1);
        }
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 1,
                "Cách dùng: CacheProbeCheck <cached|uncached>");

        boolean cacheEnabled;
        if ("cached".equals(args[0])) {
            cacheEnabled = true;
        } else if ("uncached".equals(args[0])) {
            cacheEnabled = false;
        } else {
            throw new IllegalArgumentException(
                    "Mode phải là cached hoặc uncached");
        }

        // Xác nhận security properties trước lần gọi InetAddress đầu tiên.
        String expectedTtl = cacheEnabled ? "60" : "0";
        require(expectedTtl.equals(
                        Security.getProperty("networkaddress.cache.ttl")),
                "Positive TTL chưa được nạp đúng");
        require(expectedTtl.equals(
                        Security.getProperty("networkaddress.cache.negative.ttl")),
                "Negative TTL chưa được nạp đúng");
        require("0".equals(
                        Security.getProperty("networkaddress.cache.stale.ttl")),
                "Stale TTL phải bằng 0 trong bài test");

        assertCount("provider.construct.count", 0);
        assertCount("provider.get.count", 0);
        assertCount("resolver.positive.count", 0);
        assertCount("resolver.negative.count", 0);

        verifyPositiveCache(cacheEnabled);
        verifyNegativeCache(cacheEnabled);

        int expectedCalls = cacheEnabled ? 1 : ATTEMPTS;
        assertCount("resolver.positive.count", expectedCalls);
        assertCount("resolver.negative.count", expectedCalls);
        assertCount("provider.get.count", 1);
        assertCount("provider.construct.count", 1);

        System.out.println("Mode: " + args[0]);
        System.out.println("Positive resolver calls: "
                + count("resolver.positive.count"));
        System.out.println("Negative resolver calls: "
                + count("resolver.negative.count"));
        System.out.println("Provider constructor calls: "
                + count("provider.construct.count"));
        System.out.println("Provider get(Configuration) calls: "
                + count("provider.get.count"));
        System.out.println("PASS: positive and negative cache counters");
    }
}
```

Chương trình chạy năm lần cùng hostname trong mỗi nhóm. Với cache-on, lần đầu gọi resolver; bốn lần sau phải là cache hit. Với cache-off, cả năm lần đều gọi resolver. Bộ đếm `provider.get.count` phải là 1 trong cả hai mode, vì resolver hệ thống đã được cài một lần và được tái sử dụng.

## 6. Biên dịch và chạy hai mode trong hai JVM mới

Từ thư mục `inetaddress-cache-counter`, biên dịch ba class và tạo service descriptor.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path "out/META-INF/services" | Out-Null
javac --release 18 -d out src/demo/cache/CacheProbeResolver.java src/demo/cache/CacheProbeProvider.java src/demo/cache/CacheProbeCheck.java

$descriptor = "out/META-INF/services/java.net.spi.InetAddressResolverProvider"
[System.IO.File]::WriteAllText($descriptor, "demo.cache.CacheProbeProvider" + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

@("networkaddress.cache.ttl=60", "networkaddress.cache.negative.ttl=60", "networkaddress.cache.stale.ttl=0") | Set-Content -Encoding Ascii -Path cache-on.security
@("networkaddress.cache.ttl=0", "networkaddress.cache.negative.ttl=0", "networkaddress.cache.stale.ttl=0") | Set-Content -Encoding Ascii -Path cache-off.security

$cacheOnPath = (Resolve-Path .\cache-on.security).Path
$cacheOnUrl = ([System.Uri]$cacheOnPath).AbsoluteUri
java "-Djava.security.properties=$cacheOnUrl" -Djava.net.preferIPv4Stack=true -cp out demo.cache.CacheProbeCheck cached

$cacheOffPath = (Resolve-Path .\cache-off.security).Path
$cacheOffUrl = ([System.Uri]$cacheOffPath).AbsoluteUri
java "-Djava.security.properties=$cacheOffUrl" -Djava.net.preferIPv4Stack=true -cp out demo.cache.CacheProbeCheck uncached
```

### Bash/Linux/macOS

```bash
mkdir -p out/META-INF/services
javac --release 18 -d out src/demo/cache/CacheProbeResolver.java src/demo/cache/CacheProbeProvider.java src/demo/cache/CacheProbeCheck.java
printf '%s\n' 'demo.cache.CacheProbeProvider' > out/META-INF/services/java.net.spi.InetAddressResolverProvider

printf '%s\n' 'networkaddress.cache.ttl=60' 'networkaddress.cache.negative.ttl=60' 'networkaddress.cache.stale.ttl=0' > cache-on.security
printf '%s\n' 'networkaddress.cache.ttl=0' 'networkaddress.cache.negative.ttl=0' 'networkaddress.cache.stale.ttl=0' > cache-off.security

java -Djava.security.properties="file:$PWD/cache-on.security" -Djava.net.preferIPv4Stack=true -cp out demo.cache.CacheProbeCheck cached
java -Djava.security.properties="file:$PWD/cache-off.security" -Djava.net.preferIPv4Stack=true -cp out demo.cache.CacheProbeCheck uncached
```

Mỗi lệnh Java khởi chạy một tiến trình riêng. Không gộp hai mode vào cùng JVM, vì cache của `InetAddress` và chính sách TTL được giữ trong tiến trình. Tùy chọn `-Djava.security.properties` nạp file bổ sung; tùy chọn `-Djava.net.preferIPv4Stack=true` giữ fixture ở IPv4 để kết quả có một địa chỉ cố định.

## 7. Kết quả dự kiến và cách đọc counter

Với năm lần gọi cùng một hostname trong từng nhóm, kết quả dự kiến:

| Counter | Cache-on: TTL 60 | Cache-off: TTL 0 |
| --- | ---: | ---: |
| `resolver.positive.count` | 1 | 5 |
| `resolver.negative.count` | 1 | 5 |
| `provider.construct.count` | 1 | 1 |
| `provider.get.count` | 1 | 1 |

Mode cache-on có kết quả console:

```text
Mode: cached
Positive resolver calls: 1
Negative resolver calls: 1
Provider constructor calls: 1
Provider get(Configuration) calls: 1
PASS: positive and negative cache counters
```

Mode cache-off có kết quả console:

```text
Mode: uncached
Positive resolver calls: 5
Negative resolver calls: 5
Provider constructor calls: 1
Provider get(Configuration) calls: 1
PASS: positive and negative cache counters
```

Cách diễn giải:

- Lần đầu hỏi `cache-positive.qa.invalid`, resolver trả `192.0.2.150`. Với TTL 60, bốn lần tiếp theo nhận kết quả positive từ cache; `resolver.positive.count` vẫn là 1.
- Lần đầu hỏi `cache-negative.qa.invalid`, resolver ném `UnknownHostException`. Với negative TTL 60, bốn lần tiếp theo nhận lỗi đã cache; `resolver.negative.count` vẫn là 1.
- `provider.get.count` vẫn là 1 trong cả hai mode. JDK đã cài resolver một lần; việc cache có hit hay không không làm provider được cài lại.
- Với TTL 0, mỗi lần gọi đi vào resolver. Vì vậy hai counter lookup tăng tới 5, còn hai counter provider vẫn bằng 1.

Đây là phép đo số lần **resolver nhận lookup qua InetAddress**, không phải số packet DNS, số lần truy cập mạng hay số lần hệ điều hành tra cứu DNS.

## 8. Điều kiện để phép đo có ý nghĩa

### 8.1. Cùng hostname và cùng JVM

Positive và negative cache được tra theo hostname. Trong mỗi nhóm, dùng chính xác cùng một hostname và chạy các lần gọi tuần tự. Nếu mỗi lần tạo một hostname khác, mỗi lần có thể là cache miss và bộ đếm tăng dù cache đang bật.

### 8.2. Một JVM cho mỗi cấu hình TTL

Không chạy cache-on rồi đổi sang cache-off trong cùng tiến trình. `InetAddress` giữ cache và cache policy được đọc khi khởi tạo. Dùng hai tiến trình độc lập như phần 6 để mỗi mode có trạng thái ban đầu sạch.

`InetAddress` không cung cấp API công khai để xóa tùy ý cache positive/negative. Để làm test tái lập, hãy dùng JVM mới và hostname fixture mới nếu cần kiểm tra lại trạng thái ban đầu.

### 8.3. Không gọi resolver trực tiếp

Đoạn sau bỏ qua cache của `InetAddress`:

```java
CacheProbeResolver resolver = new CacheProbeResolver();
resolver.lookupByName(
        "cache-positive.qa.invalid",
        InetAddressResolver.LookupPolicy.of(
                InetAddressResolver.LookupPolicy.IPV4));
```

Đây là unit test cho resolver, không phải cache test. Muốn đo cache của JDK, mọi lần gọi phải đi qua `InetAddress.getByName` hoặc `InetAddress.getAllByName`.

### 8.4. Không chạy song song khi muốn đếm chính xác

Một số lời gọi đồng thời cho cùng hostname có thể gặp nhau trong quá trình cache entry đang được tạo. Điều đó làm phép đo số lần resolver thực sự được gọi phụ thuộc timing và cách phối hợp luồng. Ví dụ dùng vòng lặp tuần tự để mỗi lần gọi sau quan sát kết quả đã được lưu từ lần trước.

### 8.5. Không nhầm cache Java với cache của DNS/OS

Trong ví dụ, custom provider trả kết quả fixture hoặc ném lỗi trực tiếp; không gọi built-in resolver. Do đó counter trong Java đo đúng số lần SPI nhận request. Nếu dùng resolver tích hợp hoặc resolver gọi tiếp DNS, cache của OS, DNS forwarder và naming service có thể tạo thêm lớp cache bên dưới.

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `resolver.positive.count` tăng ở mọi lần dù TTL 60 | File security properties chưa được nạp, TTL bị ghi đè, stale policy hoặc hostname thay đổi |
| `resolver.negative.count` tăng ở mọi lần dù negative TTL 60 | Negative TTL không được nạp hoặc hostname/lookup context không giống nhau |
| `provider.get.count` bằng 1 nhưng resolver count bằng 0 | Chưa có lookup đi vào resolver, hoặc đang đo API parse literal/đối tượng IP |
| `provider.get.count` bằng 0 | Service descriptor sai vị trí/nội dung, provider không được discovery, hoặc chưa có hostname lookup |
| `provider.get.count` lớn hơn 1 trong một JVM test | Kiểm tra nhiều provider instance/đường khởi tạo hoặc test đã dùng class loader/runtime khác; không mặc định đó là số lookup |
| Cache-on không thấy lỗi được phát lại | Kiểm tra resolver có thực sự ném `UnknownHostException`, negative TTL và việc gọi cùng hostname |
| Cache-off vẫn chỉ có một lookup | TTL thực tế chưa bằng 0 hoặc lời gọi thứ hai không đi qua cùng đường API |
| Lệnh Java chạy được nhưng counter không có | Kiểm tra service descriptor nằm ở `out/META-INF/services`, class provider có trên system classpath và đúng tên provider |
| TTL không thay đổi dù đã thêm `-Dnetworkaddress.cache.ttl=0` | Đây là security property; `-D` không đặt giá trị security property |

### Xác minh security properties thực tế

Chương trình kiểm tra `Security.getProperty(...)` trước lần gọi `InetAddress` đầu tiên. Nếu giá trị không phải 60 hoặc 0 như mode yêu cầu, chương trình dừng bằng `AssertionError` thay vì tạo kết quả đo sai.

Có thể yêu cầu JVM in security properties trong lúc khởi động để chẩn đoán:

```powershell
java -Djava.security.debug=properties "-Djava.security.properties=$cacheOnUrl" -Djava.net.preferIPv4Stack=true -cp out demo.cache.CacheProbeCheck cached
```

Tùy chọn debug này chỉ dùng khi điều tra cấu hình; log có thể chứa nhiều security properties khác của JDK.

## 10. Checklist và bài tập mở rộng

- [ ] Provider constructor được gọi đúng một lần trong mỗi JVM.
- [ ] `provider.get(Configuration)` được gọi đúng một lần để cài resolver.
- [ ] Positive hostname trả đúng IP ở cả năm lần gọi.
- [ ] Với positive TTL 60, `lookupByName` chỉ chạy một lần cho hostname đó.
- [ ] Negative hostname ném `UnknownHostException` ở cả năm lần gọi.
- [ ] Với negative TTL 60, `lookupByName` chỉ chạy một lần cho hostname đó.
- [ ] Với cả hai TTL bằng 0, resolver được gọi năm lần cho mỗi hostname.
- [ ] Hai mode chạy trong hai JVM riêng.
- [ ] Cache properties được xác nhận qua `Security.getProperty`.
- [ ] Test không gọi resolver trực tiếp và không dùng hostname khác nhau giữa các lần.
- [ ] Service descriptor được discovery qua system class loader.
- [ ] Fixture không phụ thuộc DNS công cộng.

**Bài tập:** Đổi cả hai TTL từ 60 thành 2 giây, thêm một phép gọi sau khi chờ ít nhất 3 giây trong cùng JVM. Quan sát positive và negative resolver counters tăng thêm sau khi entry hết hạn. Sau đó thử đặt `networkaddress.cache.stale.ttl` lớn hơn positive TTL và làm resolver thất bại ở lần refresh; mô tả khác biệt giữa cache hit còn hiệu lực và việc dùng stale result sau khi refresh thất bại.

**Tiêu chí hoàn thành:** Có thể chứng minh bằng counter rằng positive cache và negative cache chặn các lần lookup lặp lại trước khi TTL hết hạn; phân biệt số lần provider được cài với số lần resolver nhận request; cấu hình TTL bằng security properties đúng cách; và giải thích vì sao hai mode cần JVM độc lập.

## Tài liệu tham khảo

- [Javadoc InetAddress – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): cache kết quả phân giải tên thành công và thất bại, cùng các security properties điều khiển TTL.
- [Networking Properties – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html): address cache positive, negative và stale; xác nhận các giá trị là security properties.
- [The Security Properties File – Java SE 25](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html): nạp file security properties bổ sung bằng `java.security.properties`, cách append/override và cách đặt property trong ứng dụng.
- [Javadoc InetAddressResolver – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng các phương thức lookup của resolver.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): provider SPI và `get(Configuration)`.
- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): giới thiệu resolver SPI trong Java 18.
