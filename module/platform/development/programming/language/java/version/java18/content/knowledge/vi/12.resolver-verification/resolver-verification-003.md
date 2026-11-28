# Chạy JVM con riêng cho từng cấu hình provider để cô lập trạng thái resolver toàn tiến trình

## 1. Vấn đề: resolver có phạm vi toàn JVM

Java 18 giới thiệu **Internet-Address Resolution SPI (JEP 418)**. Khi ứng dụng dùng `InetAddress` để phân giải hostname, một `InetAddressResolverProvider` có thể cung cấp `InetAddressResolver` thay thế resolver tích hợp. Hợp đồng API vẫn còn áp dụng trên các JDK hiện đại.

Theo Javadoc, **mỗi JVM chỉ giữ một resolver hệ thống**: sau khi JVM hoàn tất khởi động, lần tra cứu đầu tiên qua `InetAddress` có thể kích hoạt `ServiceLoader` (bằng system class loader), chọn provider đầu tiên tìm thấy và gọi `get(Configuration)`. Thứ tự tìm provider không được bảo đảm; nếu không tìm thấy provider thì sử dụng resolver tích hợp.

Điều này có hệ quả trực tiếp cho kiểm thử. Giả sử cùng hostname `svc.qa.invalid` có hai cấu hình mong muốn:

| Cấu hình | Provider | Hostname | IP cố định |
| --- | --- | --- | --- |
| `alpha` | `AlphaProvider` | `svc.qa.invalid` | `192.0.2.10` |
| `beta` | `BetaProvider` | `svc.qa.invalid` | `192.0.2.20` |

Miền `.invalid` và dải `192.0.2.0/24` được dành riêng cho thử nghiệm/tài liệu. Địa chỉ này chỉ phục vụ **kiểm thử phân giải tên**; không được dùng làm kỳ vọng kết nối mạng thực.

Nếu chạy `alpha` trong một JVM rồi thay service descriptor, class loader hoặc system property để chạy `beta` trong **cùng JVM**, `InetAddress` không tự chọn lại resolver hệ thống. Hơn nữa, lớp này có cache cho cả kết quả phân giải thành công và thất bại, nên một lần gọi mới chưa chắc đi vào resolver.

**Cách cô lập:** Mỗi cấu hình provider được triển khai trong một **JVM con mới**, với classpath và service descriptor được quyết định ngay lúc khởi chạy.

```text
JVM cha: ForkRunner
    |
    +-- JVM con alpha:
    |     classpath = classes + provider-alpha
    |     service descriptor -> AlphaProvider
    |     InetAddress("svc.qa.invalid") -> 192.0.2.10
    |     mã thoát 0 nếu PASS
    |
    +-- JVM con beta:
          classpath = classes + provider-beta
          service descriptor -> BetaProvider
          InetAddress("svc.qa.invalid") -> 192.0.2.20
          mã thoát 0 nếu PASS
```

Mỗi JVM con có state `static`, resolver cấp JVM và cache `InetAddress` riêng. Chúng vẫn dùng chung một số tài nguyên hệ điều hành như hệ thống tệp, DNS cache ngoài JVM hoặc kết nối mạng; fixture trong bài **không tra DNS bên ngoài** để tránh phụ thuộc đó.

## 2. Điều kiện thành công

Với từng JVM con:

1. `InetAddress.getAllByName("svc.qa.invalid")` trả đúng một địa chỉ IPv4 dự kiến.
2. Provider được cài qua `ServiceLoader`, không phải được khởi tạo thủ công trong test.
3. Bộ đếm ở `provider.get(Configuration)` của biến thể được chọn bằng **1**, của biến thể còn lại bằng **0**.
4. Tên không có trong bảng trả `UnknownHostException` mà không fallback sang DNS công cộng.
5. JVM con kết thúc với mã `0` khi các assertion đạt; chương trình cha kiểm mã thoát và timeout.

Không đặt hai provider trong cùng classpath rồi trông chờ JVM lần lượt thử cả hai: **chỉ provider đầu tiên tìm được được chọn**, và thứ tự là đặc thù triển khai.

## 3. Tổ chức dự án mẫu (Java 18+)

Các ví dụ dùng Java thuần, không đòi Maven, Gradle hay JUnit:

```text
resolver-forks/
  src/demo/resolver/
    FixtureResolver.java
    AlphaProvider.java
    BetaProvider.java
    ChildProbe.java
    ForkRunner.java
  out/
    classes/
    provider-alpha/META-INF/services/java.net.spi.InetAddressResolverProvider
    provider-beta/META-INF/services/java.net.spi.InetAddressResolverProvider
```

Tất cả mã Java được biên dịch chung vào `out/classes`. Hai service descriptor được đặt trong **hai thư mục khác nhau**; mỗi lần khởi chạy child chỉ đưa một thư mục descriptor vào classpath.

### 3.1. Resolver dùng chung với bảng ánh xạ xác định

Tạo `src/demo/resolver/FixtureResolver.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Stream;

final class FixtureResolver implements InetAddressResolver {
    static final String HOST = "svc.qa.invalid";

    private final byte[] ipv4;

    FixtureResolver(int lastOctet) {
        if (lastOctet < 0 || lastOctet > 255) {
            throw new IllegalArgumentException("Octet IPv4 ngoài phạm vi");
        }
        this.ipv4 = new byte[] {(byte) 192, 0, 2, (byte) lastOctet};
    }

    @Override
    public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
            throws UnknownHostException {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(policy, "policy");

        boolean acceptsIPv4 =
                (policy.characteristics() & LookupPolicy.IPV4) != 0;

        if (!HOST.equalsIgnoreCase(host) || !acceptsIPv4) {
            throw new UnknownHostException(host);
        }

        // Tạo InetAddress trực tiếp từ byte, không hỏi DNS.
        return Stream.of(InetAddress.getByAddress(HOST, ipv4));
    }

    @Override
    public String lookupByAddress(byte[] bytes)
            throws UnknownHostException {
        Objects.requireNonNull(bytes, "bytes");
        if (bytes.length != 4 && bytes.length != 16) {
            throw new IllegalArgumentException("IP cần 4 hoặc 16 byte");
        }
        if (Arrays.equals(bytes, ipv4)) {
            return HOST;
        }
        throw new UnknownHostException("IP không có trong fixture");
    }
}
```

`FixtureResolver` tuân thủ hợp đồng của API hiện hành: `lookupByName` chỉ trả địa chỉ khi hostname và họ IP phù hợp chính sách, còn `lookupByAddress` xử lý byte IPv4/IPv6 hợp lệ và lỗi tương ứng. Bài này cố tình dùng IPv4 để tập trung vào **cô lập JVM**; kiểm chứng thứ tự IPv4/IPv6 nên có các contract test riêng với `LookupPolicy` cố định.

Quan trọng: sử dụng `InetAddress.getByAddress(HOST, ipv4)` vì hàm này **tạo địa chỉ từ dữ liệu có sẵn**, không kích hoạt một vòng phân giải hostname mới trong quá trình resolver đang phục vụ truy vấn.

### 3.2. AlphaProvider và BetaProvider

Tạo `src/demo/resolver/AlphaProvider.java`:

```java
package demo.resolver;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.concurrent.atomic.AtomicInteger;

public final class AlphaProvider extends InetAddressResolverProvider {
    private static final AtomicInteger INSTALLATIONS = new AtomicInteger();

    public AlphaProvider() {}

    @Override
    public String name() {
        return "fixture-alpha";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        INSTALLATIONS.incrementAndGet();
        return new FixtureResolver(10);
    }

    public static int installations() {
        return INSTALLATIONS.get();
    }
}
```

Tạo `src/demo/resolver/BetaProvider.java`:

```java
package demo.resolver;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.concurrent.atomic.AtomicInteger;

public final class BetaProvider extends InetAddressResolverProvider {
    private static final AtomicInteger INSTALLATIONS = new AtomicInteger();

    public BetaProvider() {}

    @Override
    public String name() {
        return "fixture-beta";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        INSTALLATIONS.incrementAndGet();
        return new FixtureResolver(20);
    }

    public static int installations() {
        return INSTALLATIONS.get();
    }
}
```

Hai class đều có constructor công khai không tham số phù hợp `ServiceLoader`. Bộ đếm `INSTALLATIONS` tăng tại `get(Configuration)` để phân biệt **provider đã được JVM chọn** với provider chỉ tồn tại trên classpath. Bộ đếm này không đo số lần thực hiện `lookupByName`, vì cache có thể phục vụ nhiều lời gọi `InetAddress` mà không gọi lại resolver.

## 4. Chương trình trong JVM con

Tệp `src/demo/resolver/ChildProbe.java` nhận biến thể `alpha` hoặc `beta` và kiểm đường đi thật từ `InetAddress` qua `ServiceLoader`.

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;

public final class ChildProbe {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 1, "Cần một biến thể alpha/beta");
        String variant = args[0];
        boolean alpha = "alpha".equals(variant);
        require(alpha || "beta".equals(variant),
                "Biến thể không hợp lệ: " + variant);

        byte[] expected = new byte[] {
            (byte) 192, 0, 2, (byte) (alpha ? 10 : 20)
        };

        // Chính InetAddress phải kích hoạt provider qua ServiceLoader.
        InetAddress[] resolved =
                InetAddress.getAllByName(FixtureResolver.HOST);

        require(resolved.length == 1, "Cần đúng một địa chỉ IPv4");
        require(Arrays.equals(resolved[0].getAddress(), expected),
                "Provider/IP không đúng: " + Arrays.toString(resolved));

        // Class provider không được chọn vẫn có thể có trên classpath;
        // get(Configuration) của nó không được gọi.
        int countA = AlphaProvider.installations();
        int countB = BetaProvider.installations();
        require(countA == (alpha ? 1 : 0),
                "Sai số lần cài AlphaProvider");
        require(countB == (alpha ? 0 : 1),
                "Sai số lần cài BetaProvider");

        try {
            InetAddress.getAllByName("missing.qa.invalid");
            throw new AssertionError("Thiếu UnknownHostException");
        } catch (UnknownHostException expectedFailure) {
            // Tên không tồn tại phải bị từ chối bởi fixture.
        }

        System.out.printf(
                "PASS child=%s pid=%d ip=%s installs=%d/%d%n",
                variant, ProcessHandle.current().pid(),
                resolved[0].getHostAddress(), countA, countB);
    }
}
```

**Vì sao cần cả IP và bộ đếm?** Nếu thiếu service descriptor, `InetAddress` có thể dùng resolver tích hợp và thất bại ở hostname fixture. Nếu JVM chọn nhầm provider, giá trị IP/bộ đếm không khớp. Ca âm tính `missing.qa.invalid` riêng lẻ không đủ chứng minh SPI đã hoạt động, vì resolver mặc định cũng có thể không tìm thấy tên này.

`ProcessHandle.current().pid()` ghi PID để chẩn đoán, không assert một giá trị PID cố định. Chương trình dùng `AssertionError` trực tiếp nên không phụ thuộc JVM có bật `-ea` cho toán tử `assert` hay chưa.

## 5. JVM cha điều phối qua ProcessBuilder

Tệp `src/demo/resolver/ForkRunner.java`:

```java
package demo.resolver;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class ForkRunner {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Cách dùng: ForkRunner <classes> <alpha-services> <beta-services>");
        }

        Path classes = Path.of(args[0]).toAbsolutePath().normalize();
        Path alphaServices = Path.of(args[1]).toAbsolutePath().normalize();
        Path betaServices = Path.of(args[2]).toAbsolutePath().normalize();

        for (Path directory :
                new Path[] {classes, alphaServices, betaServices}) {
            if (!Files.isDirectory(directory)) {
                throw new IllegalArgumentException(
                        "Thiếu thư mục: " + directory);
            }
        }

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");

        fork(javaExecutable, classes, alphaServices, "alpha");
        fork(javaExecutable, classes, betaServices, "beta");

        System.out.println("PASS: hai cấu hình trong hai JVM con");
    }

    private static void fork(Path javaExecutable, Path classes,
                             Path serviceDir, String variant)
            throws Exception {
        String childClasspath = classes + File.pathSeparator + serviceDir;

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable.toString(),
                "-Djava.net.preferIPv4Stack=true",
                "-cp", childClasspath,
                "demo.resolver.ChildProbe",
                variant
        );

        // Cho stdout/stderr đi thẳng vào console để tránh đầy pipe.
        builder.inheritIO();

        Process child = builder.start();
        if (!child.waitFor(20, TimeUnit.SECONDS)) {
            child.destroyForcibly();
            child.waitFor(5, TimeUnit.SECONDS);
            throw new AssertionError("JVM con " + variant + " bị timeout");
        }

        if (child.exitValue() != 0) {
            throw new AssertionError(
                    "JVM con " + variant + " exit=" + child.exitValue());
        }
    }
}
```

### Những quyết định quan trọng trong mã

- **Đúng JDK:** `java.home/bin/java` lấy executable từ runtime JVM cha. Trên Windows chọn `java.exe`; trên Linux/macOS chọn `java`.
- **Classpath riêng:** Mỗi JVM con có `out/classes` và đúng một thư mục service descriptor. Cả hai class provider đều tồn tại không gây xung đột, vì chỉ một được khai báo bằng `META-INF/services`.
- **Tham số riêng:** `ProcessBuilder` nhận từng argument; đường dẫn có dấu cách không làm vỡ lệnh vì không ghép lệnh shell.
- **IPv4 khi khởi động:** `-Djava.net.preferIPv4Stack=true` giúp fixture IPv4 hoạt động ổn định trên máy có hỗ trợ IPv4. Với hệ điều hành chỉ có IPv6, dùng fixture IPv6/policy phù hợp.
- **I/O:** `inheritIO()` chuyển stdout/stderr child về console cha. Nếu đổi sang pipe để thu output, phải đọc liên tục các luồng hoặc redirect vào file để tránh đầy pipe.
- **Timeout:** `waitFor(20, TimeUnit.SECONDS)` có hạn, `destroyForcibly()` khi vượt hạn, và mã thoát khác 0 được đưa thành lỗi của JVM cha.

Không dùng thread, `ThreadLocal` hoặc class loader mới thay cho JVM con khi mục tiêu là cô lập resolver toàn tiến trình: chúng vẫn cùng JVM và cùng resolver hệ thống.

## 6. Biên dịch và chạy trên Windows PowerShell

Từ thư mục `resolver-forks`, tạo đủ năm tệp Java theo nội dung ở trên, sau đó chạy:

```powershell
$javaFiles = @(
  "src/demo/resolver/FixtureResolver.java",
  "src/demo/resolver/AlphaProvider.java",
  "src/demo/resolver/BetaProvider.java",
  "src/demo/resolver/ChildProbe.java",
  "src/demo/resolver/ForkRunner.java"
)

New-Item -ItemType Directory -Force -Path `
  "out/classes", `
  "out/provider-alpha/META-INF/services", `
  "out/provider-beta/META-INF/services" | Out-Null

javac --release 18 -d out/classes $javaFiles

Set-Content -Encoding Ascii `
  -Path "out/provider-alpha/META-INF/services/java.net.spi.InetAddressResolverProvider" `
  -Value "demo.resolver.AlphaProvider"

Set-Content -Encoding Ascii `
  -Path "out/provider-beta/META-INF/services/java.net.spi.InetAddressResolverProvider" `
  -Value "demo.resolver.BetaProvider"

java -cp out/classes demo.resolver.ForkRunner `
  out/classes out/provider-alpha out/provider-beta
```

Hai service descriptor phải là tệp **không có đuôi mở rộng**, mỗi tệp chứa đúng một tên class provider. `javac --release 18` giúp tránh dùng nhầm API được đưa vào sau Java 18.

Trong Bash trên Linux/macOS, sử dụng lệnh tương đương:

```bash
mkdir -p out/classes out/provider-alpha/META-INF/services \
         out/provider-beta/META-INF/services

javac --release 18 -d out/classes src/demo/resolver/*.java

printf '%s\n' 'demo.resolver.AlphaProvider' \
  > out/provider-alpha/META-INF/services/java.net.spi.InetAddressResolverProvider

printf '%s\n' 'demo.resolver.BetaProvider' \
  > out/provider-beta/META-INF/services/java.net.spi.InetAddressResolverProvider

java -cp out/classes demo.resolver.ForkRunner \
  out/classes out/provider-alpha out/provider-beta
```

Kết quả **dự kiến**, PID thay đổi theo máy và mỗi lượt chạy:

```text
PASS child=alpha pid=1234 ip=192.0.2.10 installs=1/0
PASS child=beta pid=5678 ip=192.0.2.20 installs=0/1
PASS: hai cấu hình trong hai JVM con
```

Vì `ForkRunner` sinh hai tiến trình, hai dòng đầu có PID khác nhau. Mã thoát 0 của cả hai là điều kiện để dòng cuối được in.

Để chạy thử từng child trên Windows PowerShell:

```powershell
java -Djava.net.preferIPv4Stack=true `
  -cp "out/classes;out/provider-alpha" `
  demo.resolver.ChildProbe alpha

java -Djava.net.preferIPv4Stack=true `
  -cp "out/classes;out/provider-beta" `
  demo.resolver.ChildProbe beta
```

Trên Linux/macOS, ký tự phân tách classpath là `:` thay cho `;`. Trong mã Java, `File.pathSeparator` xử lý sự khác biệt này.

## 7. Thử lỗi có chủ đích để chứng minh độ tin cậy

| Thao tác | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- |
| `alpha` dùng descriptor `AlphaProvider` | PASS, IP `192.0.2.10`, bộ đếm `1/0` | Nạp đúng provider A |
| `beta` dùng descriptor `BetaProvider` | PASS, IP `192.0.2.20`, bộ đếm `0/1` | Nạp đúng provider B |
| JVM `beta` trỏ nhầm đến `provider-alpha` | FAIL do IP và bộ đếm sai | Phát hiện nhầm classpath |
| Bỏ descriptor khỏi JVM `alpha` | FAIL ca hostname dương tính | Phát hiện thiếu đăng ký SPI |
| Đưa cả hai descriptor vào một JVM | Không bảo đảm provider nào được chọn | Phát hiện cấu hình kiểm thử mơ hồ |
| Đổi descriptor sau lần tra cứu đầu | Không tự cài resolver mới | Chứng minh giới hạn toàn JVM |
| Dùng `InetAddress.getByName("192.0.2.10")` thay hostname | Có thể chỉ phân tích IP literal | Test chưa đo SPI |
| Child không kết thúc trong thời hạn | `ForkRunner` FAIL | Kiểm giới hạn thời gian |
| Child có assertion lỗi | `ForkRunner` FAIL vì exit code khác 0 | Truyền lỗi về test runner |

Một bài kiểm chứng tốt phải **thất bại khi wiring sai**. Bạn có thể chạy `ChildProbe beta` với classpath `provider-alpha` để xác nhận nó bắt lỗi, thay vì chỉ dựa vào hai lần PASS mặc định.

### Anti-pattern: thay property trong cùng JVM

```java
System.setProperty("resolver.demo.profile", "alpha");
InetAddress.getAllByName("svc.qa.invalid");

System.setProperty("resolver.demo.profile", "beta");
InetAddress.getAllByName("svc.qa.invalid");
```

Đổi property **không làm `InetAddress` chạy lại `ServiceLoader`**. Nếu một resolver đã cài tự đọc property mỗi lần gọi thì hành vi của chính resolver đó có thể thay đổi, nhưng điều này không tương đương việc chọn provider khác; cache cũng có thể che sự thay đổi. Tạo `URLClassLoader` mới và gọi `ServiceLoader.load(...)` thủ công cũng không làm resolver hệ thống tự được thay thế.

Trong ứng dụng sản xuất có nhiều resolver tùy biến, phải phân biệt **tạo instance mới để unit test** với **cài resolver toàn JVM cho `InetAddress`**. Chỉ cách sau mới kiểm chứng luồng tích hợp qua SPI.

## 8. Tích hợp vào JUnit và pipeline CI

Mô hình phù hợp cho dự án thật:

1. **Unit/contract test:** Tạo trực tiếp `InetAddressResolver` và thử `lookupByName`/`lookupByAddress` với `LookupPolicy` xác định. Những test này không nhất thiết cần JVM con cho từng phương thức.
2. **SPI integration test:** Mỗi cấu hình provider chạy trong một JVM fork mới với classpath riêng, service descriptor duy nhất và một hostname fixture dương tính.
3. **CI:** Thu stdout, stderr, exit code, tên profile, phiên bản JDK, PID và classpath tương ứng. Mọi mã thoát khác 0 hoặc timeout phải làm task thất bại.
4. **Chạy song song:** Có thể chạy nhiều JVM con đồng thời, nhưng các file cấu hình có thể sửa, cổng mạng và tài nguyên hệ điều hành vẫn cần tách biệt.

### Bộ nhớ đệm

`InetAddress` cache kết quả phân giải tên thành công lẫn thất bại. Các thuộc tính `networkaddress.cache.ttl`, `networkaddress.cache.negative.ttl` là **security properties**, không được cấu hình đáng tin cậy bằng `-D...` hoặc `System.setProperty`. Với mục tiêu thay **provider**, mỗi JVM con mới cho một trạng thái ban đầu riêng, rõ ràng hơn việc cố thay TTL rồi gọi lại trong cùng JVM.

Nếu mục tiêu học tập chuyển sang **thử cơ chế cache**, cần suite riêng với cấu hình security properties đúng nguồn và quy tắc đo số lần resolver được gọi.

### Đăng ký provider và khởi tạo

`InetAddress` nạp provider bằng system class loader và chọn provider đầu tiên được tìm thấy; thứ tự không ổn định nếu có nhiều provider. Provider nên có constructor và `get(Configuration)` đơn giản, tránh phân giải hostname trong static initializer hoặc trong bước cài provider để hạn chế vòng gọi/deadlock.

Javadoc cũng quy định lookup xảy ra **trước khi JVM hoàn tất boot** có thể dùng resolver tích hợp. Bài ví dụ kích hoạt hostname fixture từ `main` của từng JVM con, sau giai đoạn boot, để kiểm đúng SPI đang cần học.

Không kết hợp `-Djdk.net.hosts.file=...` với test kiểm tra SPI: trên các triển khai OpenJDK, thiết lập này có thể chọn resolver dùng tệp hosts thay cho custom provider. Mỗi suite nên chỉ xác minh một cơ chế phân giải tại một thời điểm.

### Ranh giới đảm bảo

Tách JVM giúp cô lập resolver và cache thuộc JVM; nó **không cô lập toàn bộ hệ điều hành**. Không dùng IP TEST-NET để khẳng định có HTTP, TCP, TLS hoặc server thật. Nếu cần kiểm thử giao tiếp mạng, tạo máy chủ test trên loopback hoặc mạng kiểm thử riêng với điểm cuối có thể kết nối.

## 9. Checklist thực hành và bài tập mở rộng

- [ ] Mỗi biến thể có JVM riêng và PID có thể quan sát.
- [ ] Mỗi child có đúng một descriptor `InetAddressResolverProvider` trên classpath.
- [ ] Ca dương tính thật sự gọi `InetAddress.getAllByName(hostname)`.
- [ ] Cả IP và bộ đếm `provider.get(Configuration)` đều phù hợp.
- [ ] Ca âm tính ném `UnknownHostException`, không fallback DNS.
- [ ] JVM cha kiểm timeout, mã thoát và hiển thị thông tin lỗi của child.
- [ ] Test sai descriptor thực sự FAIL.
- [ ] Không đặt kỳ vọng thay resolver cấp JVM sau khi nó đã được chọn.

**Bài tập:** Thêm `GammaProvider` ánh xạ `svc.qa.invalid` tới `192.0.2.30`, tạo descriptor `provider-gamma` và một JVM con thứ ba. Sau đó, cố tình gán JVM `gamma` sang descriptor `alpha`: hãy xác nhận child FAIL vì IP/bộ đếm không khớp.

**Tiêu chí hoàn thành:** Hai provider được kiểm thử qua SPI trong hai JVM độc lập; mỗi biến thể trả đúng IP; sai cấu hình, timeout hoặc lỗi assertion đều được JVM cha phát hiện; toàn bộ ví dụ dùng được trên JDK 18 trở lên mà không cần DNS công cộng.

## 10. Câu hỏi tự kiểm tra

1. Vì sao hai test cùng một JVM không bảo đảm chọn lần lượt AlphaProvider và BetaProvider?
2. Những trạng thái nào của `InetAddress` được khởi tạo lại khi tạo JVM con?
3. Vì sao `ChildProbe` phải kiểm cả IP lẫn bộ đếm provider?
4. Điểm khác biệt giữa `ClassLoader` riêng và tiến trình JVM riêng trong bài này là gì?
5. Nếu một test được trả từ cache, số lần `InetAddress.getAllByName` có nhất thiết bằng số lần `resolver.lookupByName` không?
6. Khi nào cần kiểm thử trực tiếp `InetAddressResolver` thay vì chạy integration suite qua `InetAddress`?

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): SPI giới thiệu từ Java 18.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): resolver toàn JVM, ServiceLoader, khởi tạo provider và lựa chọn đầu tiên.
- [Javadoc InetAddressResolver – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng `lookupByName` và `lookupByAddress`.
- [Javadoc InetAddress – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): tra cứu tên và cache.
- [Javadoc ProcessBuilder – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html): tạo JVM con, argument, I/O và quản lý tiến trình.
- [Java Networking Properties – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html): security properties của cache.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606), [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737): miền dành riêng và IPv4 dành cho tài liệu.
