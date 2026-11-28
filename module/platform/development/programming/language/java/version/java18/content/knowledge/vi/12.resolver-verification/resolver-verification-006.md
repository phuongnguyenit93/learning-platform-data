# Kiểm chứng đường triển khai classpath và named module bằng cùng bộ dữ liệu địa chỉ

## 1. Mục tiêu: cùng một resolver, hai cách đóng gói

Java 18 giới thiệu **Internet-Address Resolution SPI** theo JEP 418. Trên JDK hiện đại, `InetAddress` vẫn có thể dùng resolver do ứng dụng cung cấp qua `InetAddressResolverProvider`.

Một provider có thể được triển khai theo hai cách phổ biến:

- **Classpath JAR:** đăng ký provider bằng tệp `META-INF/services/java.net.spi.InetAddressResolverProvider`.
- **Named module:** đăng ký provider bằng directive `provides ... with ...` trong `module-info.java`.

Bài này dùng **cùng một mã nguồn provider và cùng một bảng hostname/IP** cho cả hai kiểu đóng gói. Ta sẽ kiểm tra resource hoặc module descriptor, discovery qua system class loader, sau đó gọi `InetAddress` để chứng minh resolver thật sự được cài đặt.

Dữ liệu fixture:

| Hostname | Địa chỉ IP cố định |
| --- | --- |
| `api.qa.invalid` | `192.0.2.10` |
| `db.qa.invalid` | `192.0.2.20` |
| `missing.qa.invalid` | Không có; phải ném `UnknownHostException` |

`.invalid` là miền dành riêng; `192.0.2.0/24` là dải IPv4 dành cho tài liệu. Các địa chỉ chỉ dùng để kiểm thử phân giải tên, không dùng để khẳng định máy chủ TCP/HTTP thật đang hoạt động.

**Kết quả mong muốn:** cùng một hostname phải cho cùng một IP trong cả classpath và named module. Sự khác nhau nằm ở cách provider được đóng gói và khai báo, không nằm ở logic resolver hay dữ liệu.

## 2. Khác biệt giữa classpath và named module

| Thành phần | Classpath JAR | Named module |
| --- | --- | --- |
| Cách khai báo provider | Tệp service descriptor | Directive `provides` trong module descriptor |
| Vị trí đăng ký | `META-INF/services/java.net.spi.InetAddressResolverProvider` ở gốc JAR | `module-info.java` |
| Nội dung | Tên đầy đủ của provider class, một dòng mỗi provider | `provides java.net.spi.InetAddressResolverProvider with ...;` |
| Discovery | `ServiceLoader` đọc provider configuration file | `ServiceLoader` đọc module descriptor của module đã được resolve |
| Điều kiện visibility | JAR nằm trong system classpath, provider class nhìn thấy từ system class loader | Module provider được resolve vào layer, provider class được định nghĩa bởi loader của module |
| Consumer gọi `ServiceLoader` trực tiếp | Không cần module descriptor | Module consumer phải khai báo `uses` |
| Consumer chỉ gọi `InetAddress` | Không cần thêm module metadata | `java.base` là module dùng SPI; consumer không cần `uses` chỉ vì gọi `InetAddress` |

Đối với resolver của `InetAddress`, JDK sử dụng `ServiceLoader` với **system class loader**. Vì vậy, việc một plugin loader hoặc thread context class loader nhìn thấy provider chưa đủ chứng minh `InetAddress` có thể tìm thấy provider đó.

Named module cần phân biệt hai directive:

- `provides` thuộc module chứa provider, khai báo module cung cấp implementation nào.
- `uses` thuộc module trực tiếp gọi `ServiceLoader.load(...)`, khai báo module đó sử dụng service nào.

Trong bài này, chương trình kiểm tra tự gọi `ServiceLoader.load` để quan sát provider trước khi kích hoạt resolver, nên module ứng dụng khai báo `uses`. Nếu một ứng dụng named module chỉ gọi `InetAddress.getAllByName` mà không tự gọi `ServiceLoader`, nó không cần thêm `uses` chỉ vì sử dụng `InetAddress`; module `java.base` đã sử dụng SPI này.

## 3. Một mã nguồn provider và một bộ dữ liệu chung

Cấu trúc tổng thể:

```text
resolver-dual-deployment/
  src/
    provider/
      demo/resolver/FixtureProvider.java
    classpath/
      (service descriptor được tạo khi build)
    module-provider/
      module-info.java
    app/
      demo/check/ResolverCheck.java
    module-app/
      module-info.java
  build/
    classpath/
    mods/
    jars/
```

Mã nguồn `FixtureProvider.java` được biên dịch hai lần:

1. Không có `module-info.java` để tạo classpath JAR.
2. Có `module-info.java` để tạo explicit named module.

Không fork hai bản logic resolver. Cách này giúp so sánh công bằng: nếu kết quả khác nhau, nguyên nhân nhiều khả năng nằm ở packaging, descriptor, module resolution hoặc class loader.

### 3.1. Provider dùng chung

Tạo `src/provider/demo/resolver/FixtureProvider.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class FixtureProvider extends InetAddressResolverProvider {
    private static final String PREFIX = "demo.fixture.resolver.";
    private static final Map<String, byte[]> ADDRESSES = Map.of(
            "api.qa.invalid", new byte[] {(byte) 192, 0, 2, 10},
            "db.qa.invalid",  new byte[] {(byte) 192, 0, 2, 20}
    );

    private static final AtomicInteger GET_COUNT = new AtomicInteger();
    private static final AtomicInteger LOOKUP_COUNT = new AtomicInteger();

    static {
        System.setProperty(PREFIX + "initialized", "true");
    }

    public FixtureProvider() {
        System.setProperty(PREFIX + "constructed", "true");
    }

    @Override
    public String name() {
        return "dual-deployment-fixture";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        System.setProperty(PREFIX + "get.count",
                Integer.toString(GET_COUNT.incrementAndGet()));
        return new FixtureResolver();
    }

    private static final class FixtureResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
                throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            System.setProperty(PREFIX + "lookup.count",
                    Integer.toString(LOOKUP_COUNT.incrementAndGet()));

            byte[] address = ADDRESSES.get(host.toLowerCase(Locale.ROOT));
            boolean ipv4Allowed =
                    (policy.characteristics() & LookupPolicy.IPV4) != 0;

            if (address == null || !ipv4Allowed) {
                throw new UnknownHostException(host);
            }

            // Tạo InetAddress từ byte fixture, không gọi DNS lồng nhau.
            return Stream.of(InetAddress.getByAddress(host, address));
        }

        @Override
        public String lookupByAddress(byte[] address)
                throws UnknownHostException {
            Objects.requireNonNull(address, "address");
            if (address.length != 4 && address.length != 16) {
                throw new IllegalArgumentException("IP cần 4 hoặc 16 byte");
            }

            for (var entry : ADDRESSES.entrySet()) {
                if (Arrays.equals(address, entry.getValue())) {
                    return entry.getKey();
                }
            }
            throw new UnknownHostException("IP không có trong fixture");
        }
    }
}
```

Bộ dữ liệu là một map không sửa đổi về cấu trúc; các mảng byte được giữ nội bộ và không trả ra ngoài. Resolver chỉ trả IPv4 khi `LookupPolicy` cho phép `IPV4`. Lệnh chạy sẽ đặt `-Djava.net.preferIPv4Stack=true` trước main class để ví dụ dùng chính sách IPv4 nhất quán.

Các marker giúp quan sát:

- `initialized=true`: class provider đã được initialize.
- `constructed=true`: constructor provider đã chạy.
- `get.count=1`: `InetAddress` đã gọi `get(Configuration)`.
- `lookup.count`: số truy vấn thực sự đi vào resolver, không phải số lần ứng dụng gọi API.

Các marker chỉ phục vụ test trong JVM mới; không dùng system property làm metrics sản xuất.

### 3.2. Module descriptor của provider

Tạo `src/module-provider/module-info.java`:

```java
module demo.resolver.provider {
    provides java.net.spi.InetAddressResolverProvider
        with demo.resolver.FixtureProvider;
}
```

Directive `provides` đăng ký provider cho service của JDK. Module provider không cần `exports demo.resolver` chỉ để `ServiceLoader` phát hiện implementation; lớp provider vẫn là lớp `public` có constructor công khai không tham số.

Khi biên dịch trên module path, descriptor này trở thành metadata của explicit named module. Bản đóng gói named module **không cần** service configuration file trên classpath.

### 3.3. Module descriptor của ứng dụng kiểm tra

Tạo `src/module-app/module-info.java`:

```java
module demo.resolver.app {
    uses java.net.spi.InetAddressResolverProvider;
}
```

`uses` cần thiết vì `ResolverCheck` gọi `ServiceLoader.load(...)` trực tiếp để kiểm tra discovery. Nếu bỏ đoạn kiểm tra `ServiceLoader` và chỉ gọi `InetAddress`, directive `uses` này không cần thiết cho riêng lời gọi `InetAddress`.
## 4. Chương trình kiểm tra chung cho cả hai cách đóng gói

Tạo `src/app/demo/check/ResolverCheck.java`. Mã này được biên dịch hai lần: một lần trên classpath, một lần trong named module `demo.resolver.app`.

Trước khi gọi `InetAddress`, chương trình xác minh descriptor theo đúng kiểu triển khai:

- Với `classpath`, đọc resource qua `systemLoader.getResources` và xác nhận URL có protocol `jar`, đồng thời nội dung có tên provider.
- Với `module`, tìm module `demo.resolver.provider` trong boot layer và kiểm tra module descriptor có directive `provides` đúng service/provider.

Sau đó chương trình dùng `ServiceLoader.Provider.type()` để xem provider class mà chưa tạo instance, và `Class.forName(..., false, systemLoader)` để load class nhưng chưa initialize. Cuối cùng, gọi `InetAddress` với hai hostname dương tính và một hostname âm tính.

```java
package demo.check;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.lang.module.ModuleDescriptor;
import java.net.InetAddress;
import java.net.URL;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolverProvider;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.ServiceLoader;

public final class ResolverCheck {
    private static final String SERVICE =
            InetAddressResolverProvider.class.getName();
    private static final String RESOURCE =
            "META-INF/services/" + SERVICE;
    private static final String PROVIDER =
            "demo.resolver.FixtureProvider";
    private static final String PROVIDER_MODULE =
            "demo.resolver.provider";
    private static final String PREFIX = "demo.fixture.resolver.";

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static boolean descriptorDeclares(URL url)
            throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(url.openStream(),
                        StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                int comment = line.indexOf('#');
                if (comment >= 0) {
                    line = line.substring(0, comment);
                }
                if (PROVIDER.equals(line.trim())) {
                    return true;
                }
            }
        }
        return false;
    }

    private static void verifyClasspathDescriptor(ClassLoader loader)
            throws IOException {
        Enumeration<URL> enumeration = loader.getResources(RESOURCE);
        List<URL> resources = Collections.list(enumeration);
        require(!resources.isEmpty(),
                "System class loader không thấy service descriptor");

        boolean foundInJar = false;
        for (URL url : resources) {
            System.out.println("Service resource: " + url);
            if ("jar".equals(url.getProtocol())
                    && descriptorDeclares(url)) {
                foundInJar = true;
            }
        }
        require(foundInJar,
                "Không tìm thấy provider declaration trong JAR");
    }

    private static void verifyModuleDescriptor() {
        Module providerModule = ModuleLayer.boot()
                .findModule(PROVIDER_MODULE)
                .orElseThrow(() -> new AssertionError(
                        "Provider module chưa được resolve vào boot layer"));

        ModuleDescriptor descriptor = providerModule.getDescriptor();
        boolean providesService = descriptor.provides().stream()
                .anyMatch(entry ->
                        SERVICE.equals(entry.service())
                        && entry.providers().contains(PROVIDER));

        require(!descriptor.isAutomatic(),
                "Provider phải là explicit named module");
        require(providesService,
                "module-info không khai báo provides đúng provider");

        System.out.println("Provider module: " + providerModule.getName());
        System.out.println("Module descriptor: " + descriptor);
    }

    private static void verifyAddress(String host, String expected)
            throws UnknownHostException {
        InetAddress[] addresses = InetAddress.getAllByName(host);
        require(addresses.length == 1,
                host + " phải trả đúng một địa chỉ");
        require(expected.equals(addresses[0].getHostAddress()),
                host + " expected " + expected
                        + " but got " + addresses[0].getHostAddress());
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 1,
                "Cách dùng: ResolverCheck <classpath|module>");
        String mode = args[0];
        require("classpath".equals(mode) || "module".equals(mode),
                "Mode phải là classpath hoặc module");

        ClassLoader systemLoader = ClassLoader.getSystemClassLoader();

        // 1. Xác minh metadata trước khi InetAddress kích hoạt provider.
        if ("classpath".equals(mode)) {
            verifyClasspathDescriptor(systemLoader);
        } else {
            verifyModuleDescriptor();
        }

        // 2. Discovery qua đúng system class loader.
        List<String> providerTypes = ServiceLoader
                .load(InetAddressResolverProvider.class, systemLoader)
                .stream()
                .map(provider -> provider.type().getName())
                .toList();

        require(providerTypes.contains(PROVIDER),
                "System loader không discovery được provider: " + providerTypes);

        // Load class mà không initialize, rồi kiểm tra module sở hữu class.
        Class<?> providerClass =
                Class.forName(PROVIDER, false, systemLoader);
        require(InetAddressResolverProvider.class.isAssignableFrom(providerClass),
                "Provider class không triển khai đúng SPI");

        if ("classpath".equals(mode)) {
            require(!providerClass.getModule().isNamed(),
                    "Classpath provider phải thuộc unnamed module");
        } else {
            require(providerClass.getModule().isNamed()
                            && PROVIDER_MODULE.equals(
                                    providerClass.getModule().getName()),
                    "Provider class không thuộc named module dự kiến");
        }

        // type() và Class.forName(..., false, ...) không tạo instance/init.
        require(System.getProperty(PREFIX + "initialized") == null,
                "Provider đã initialize trước lần gọi InetAddress");

        // 3. Cùng bộ dữ liệu phải trả cùng kết quả ở cả hai mode.
        verifyAddress("api.qa.invalid", "192.0.2.10");
        verifyAddress("db.qa.invalid", "192.0.2.20");

        require("true".equals(
                        System.getProperty(PREFIX + "initialized")),
                "Provider chưa initialize");
        require("true".equals(
                        System.getProperty(PREFIX + "constructed")),
                "Provider constructor chưa chạy");
        require("1".equals(System.getProperty(PREFIX + "get.count")),
                "InetAddress chưa gọi provider.get(Configuration)");
        require("2".equals(System.getProperty(PREFIX + "lookup.count")),
                "Resolver phải nhận đúng hai forward lookup");

        // 4. Hostname ngoài fixture phải bị từ chối, không fallback DNS.
        try {
            InetAddress.getAllByName("missing.qa.invalid");
            throw new AssertionError(
                    "Hostname không có trong fixture phải thất bại");
        } catch (UnknownHostException expected) {
            // Kết quả mong đợi.
        }

        require("3".equals(System.getProperty(PREFIX + "lookup.count")),
                "Truy vấn âm tính không đi vào resolver");

        System.out.println("Mode: " + mode);
        System.out.println("Provider type: " + providerClass.getName());
        System.out.println("Provider module: "
                + providerClass.getModule().getName());
        System.out.println("PASS: api.qa.invalid -> 192.0.2.10");
        System.out.println("PASS: db.qa.invalid -> 192.0.2.20");
        System.out.println("PASS: missing.qa.invalid -> UnknownHostException");
        System.out.println("PASS: InetAddress installed FixtureProvider");
    }
}
```

### Các assertion chứng minh điều gì?

- `verifyClasspathDescriptor` kiểm tra nội dung thực của service resource được system class loader nhìn thấy từ JAR.
- `verifyModuleDescriptor` kiểm tra module đã được resolve vào boot layer và module descriptor khai báo đúng provider.
- `ServiceLoader.load(service, systemLoader).stream().map(Provider::type)` chứng minh provider type được discovery mà không tạo instance.
- `Class.forName(PROVIDER, false, systemLoader)` load class nhưng không initialize class.
- Marker `initialized` phải vắng mặt trước khi gọi `InetAddress`.
- `get.count=1` chứng minh `InetAddress` đã gọi provider để cài resolver; `lookup.count` xác nhận hai hostname dương tính và một hostname âm tính đã đi vào resolver.

Test chạy trong một JVM mới cho từng mode. Không chạy cả hai mode trong cùng một JVM vì resolver cấp JVM và cache của `InetAddress` không được thiết kế để thay provider sau khi đã khởi tạo.
## 5. Build và chạy biến thể classpath JAR

Từ thư mục `resolver-dual-deployment`, tạo thư mục output và biên dịch provider **không có module descriptor**:

```powershell
New-Item -ItemType Directory -Force -Path "build/classpath/provider-classes","build/classpath/app-classes" | Out-Null
javac --release 18 -d build/classpath/provider-classes src/provider/demo/resolver/FixtureProvider.java
New-Item -ItemType Directory -Force -Path "build/classpath/provider-classes/META-INF/services" | Out-Null
```

Tạo service descriptor UTF-8 không BOM. Cách ghi dưới đây tương thích Windows PowerShell 5.1:

```powershell
$serviceFile = "build/classpath/provider-classes/META-INF/services/java.net.spi.InetAddressResolverProvider"
$serviceText = "demo.resolver.FixtureProvider" + [Environment]::NewLine
[System.IO.File]::WriteAllText($serviceFile, $serviceText, [System.Text.UTF8Encoding]::new($false))
```

Đóng gói provider JAR và biên dịch chương trình kiểm tra trên classpath:

```powershell
jar --create --file build/classpath/resolver-provider.jar -C build/classpath/provider-classes .
javac --release 18 -d build/classpath/app-classes src/app/demo/check/ResolverCheck.java
```

Kiểm tra nội dung archive:

```powershell
$entries = jar --list --file build/classpath/resolver-provider.jar
$entries
if ($entries -notcontains "META-INF/services/java.net.spi.InetAddressResolverProvider") { throw "JAR thiếu service descriptor" }
if ($entries -notcontains "demo/resolver/FixtureProvider.class") { throw "JAR thiếu provider class" }
Write-Output "PASS: JAR có descriptor và provider class"
```

Chạy với provider JAR trên system classpath:

```powershell
java -Djava.net.preferIPv4Stack=true -cp "build/classpath/app-classes;build/classpath/resolver-provider.jar" demo.check.ResolverCheck classpath
```

Trên Bash/Linux/macOS:

```bash
mkdir -p build/classpath/provider-classes build/classpath/app-classes
javac --release 18 -d build/classpath/provider-classes src/provider/demo/resolver/FixtureProvider.java
mkdir -p build/classpath/provider-classes/META-INF/services
printf '%s\n' 'demo.resolver.FixtureProvider' > build/classpath/provider-classes/META-INF/services/java.net.spi.InetAddressResolverProvider
jar --create --file build/classpath/resolver-provider.jar -C build/classpath/provider-classes .
javac --release 18 -d build/classpath/app-classes src/app/demo/check/ResolverCheck.java
java -Djava.net.preferIPv4Stack=true -cp "build/classpath/app-classes:build/classpath/resolver-provider.jar" demo.check.ResolverCheck classpath
```

Ở biến thể này, `ResolverCheck` thuộc unnamed module; provider JAR cũng được nạp từ classpath. `ServiceLoader` đọc tệp provider configuration trong JAR. Không có `module-info.java` trong provider artifact.

## 6. Build và chạy biến thể explicit named module

Biến thể module sử dụng **cùng `FixtureProvider.java` và `ResolverCheck.java`**, chỉ bổ sung hai module descriptor ở phần 3.

### 6.1. Biên dịch provider module

```powershell
New-Item -ItemType Directory -Force -Path "build/mods/demo.resolver.provider","build/mods/demo.resolver.app","build/jars" | Out-Null
javac --release 18 -d build/mods/demo.resolver.provider src/module-provider/module-info.java src/provider/demo/resolver/FixtureProvider.java
```

Output provider có cấu trúc:

```text
build/mods/demo.resolver.provider/
  module-info.class
  demo/resolver/FixtureProvider.class
```

### 6.2. Biên dịch consumer module

Biên dịch ứng dụng với module path có provider module:

```powershell
javac --release 18 --module-path build/mods -d build/mods/demo.resolver.app src/module-app/module-info.java src/app/demo/check/ResolverCheck.java
```

Consumer module khai báo `uses java.net.spi.InetAddressResolverProvider;` vì source `ResolverCheck` trực tiếp gọi `ServiceLoader.load`. Nó **không** cần `requires demo.resolver.provider`; liên kết provider được xử lý qua service binding khi module graph được resolve.

### 6.3. Đóng gói hai named module thành JAR

```powershell
jar --create --file build/jars/demo.resolver.provider.jar -C build/mods/demo.resolver.provider .
jar --create --file build/jars/demo.resolver.app.jar -C build/mods/demo.resolver.app .
```

Xem module descriptor trong provider JAR:

```powershell
jar --describe-module --file build/jars/demo.resolver.provider.jar
```

Kết quả phải hiển thị module `demo.resolver.provider` và phần cung cấp service:

```text
demo.resolver.provider
requires java.base mandated
provides java.net.spi.InetAddressResolverProvider with demo.resolver.FixtureProvider
contains demo.resolver
```

Named module đăng ký provider qua `provides` trong `module-info.class`. Bản JAR này không cần tệp `META-INF/services`.

### 6.4. Chạy named module

```powershell
java -Djava.net.preferIPv4Stack=true --show-module-resolution --module-path build/jars -m demo.resolver.app/demo.check.ResolverCheck module
```

Trên Bash:

```bash
java -Djava.net.preferIPv4Stack=true --show-module-resolution --module-path build/jars -m demo.resolver.app/demo.check.ResolverCheck module
```

`--show-module-resolution` hiển thị quá trình resolve module, hữu ích để xác nhận provider module được đưa vào boot layer nhờ service binding. Chương trình còn kiểm tra trực tiếp `ModuleLayer.boot()` và `ModuleDescriptor.provides()`, do đó không phụ thuộc riêng vào log.

## 7. Kết quả mong đợi khi so sánh

Cả hai lệnh chạy phải có cùng các kết quả địa chỉ:

```text
PASS: api.qa.invalid -> 192.0.2.10
PASS: db.qa.invalid -> 192.0.2.20
PASS: missing.qa.invalid -> UnknownHostException
PASS: InetAddress installed FixtureProvider
```

Phần thông tin packaging sẽ khác nhau:

| Assertion | Classpath | Named module |
| --- | --- | --- |
| Resource service descriptor | Có, URL dạng `jar:` | Không dùng descriptor này |
| Provider class | Thuộc unnamed module | Thuộc `demo.resolver.provider` |
| Metadata đăng ký | Tệp `META-INF/services` | `ModuleDescriptor.provides()` |
| Discovery qua system loader | Có provider type | Có provider type |
| `get.count` sau lookup | `1` | `1` |
| Bộ dữ liệu hostname/IP | Cùng map | Cùng map |

## 8. Vì sao hai cách discovery khác nhau?

### 8.1. Classpath: ServiceLoader đọc provider configuration file

Với classpath JAR, `ServiceLoader` tìm resource có tên:

```text
META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung là tên đầy đủ của provider class. Tệp được mã hóa UTF-8; có thể có comment bắt đầu bằng `#` và dòng trống. Nên ghi UTF-8 không BOM để tránh lỗi với công cụ build hoặc runtime đọc descriptor.

Một số lỗi phổ biến:

- Tên tệp sai một ký tự hoặc thêm đuôi `.txt`.
- Descriptor bị đặt dưới một thư mục gốc thừa trong JAR.
- Provider class không có trong JAR hoặc thiếu dependency.
- Provider JAR có trên TCCL nhưng không nằm trong system classpath.
- Descriptor có BOM hoặc nội dung không phải tên nhị phân đầy đủ.

### 8.2. Named module: ServiceLoader đọc module descriptor

Với explicit named module, `provides` nằm trong `module-info.class`. Khi một module đã được resolve khai báo `uses` cho service, quá trình module resolution có thể liên kết các module provider có directive `provides` tương ứng. Provider module phải nằm trên module path và được đưa vào module graph; chỉ chép JAR vào thư mục không có nghĩa nó đã được resolve.

Module provider không cần export package implementation chỉ để đăng ký service. Javadoc `ServiceLoader` khuyến nghị **không export package chứa provider**, nhằm giữ implementation được đóng gói. Provider class vẫn cần đáp ứng quy tắc public provider class và public constructor không tham số khi dùng provider constructor.

### 8.3. Provider discovery không đồng nghĩa provider đã được cài

`ServiceLoader.load(...).stream().map(Provider::type)` kiểm tra discovery và type. Nó không tự chứng minh `InetAddress` đã cài resolver. Chương trình trong bài cố ý không gọi `Provider.get()` trước lookup, để không tự tạo provider instance.

Bằng chứng tích hợp nằm ở:

- `initialized=true` sau lookup.
- `constructed=true` sau khi provider được tạo.
- `get.count=1` sau khi `InetAddress` gọi `get(Configuration)`.
- `lookup.count=3` sau hai truy vấn dương tính và một truy vấn âm tính.

Nếu provider type được discovery nhưng `get.count` không xuất hiện sau lời gọi `InetAddress`, hãy kiểm tra provider nào thực sự được chọn, resolver có được khởi tạo trước đó hay chưa và môi trường runtime có provider khác đứng trước hay không.

## 9. Chẩn đoán lỗi theo từng kiểu triển khai

| Triệu chứng | Classpath cần kiểm tra | Named module cần kiểm tra |
| --- | --- | --- |
| Provider type không xuất hiện | Descriptor, UTF-8, tên provider, JAR trong system classpath | `provides`, module path, module provider đã resolve |
| Resource descriptor không tìm thấy | `META-INF/services` ở gốc JAR | Bình thường: explicit module dùng `module-info`, không dựa vào resource này |
| Provider class không load được | Entry `demo/resolver/FixtureProvider.class` và dependencies | Class nằm trong module provider đã resolve |
| `ServiceConfigurationError` | Sai format descriptor, provider class không assignable hoặc thiếu public no-arg constructor | Sai provider type, thiếu provider constructor, lỗi module descriptor hoặc service use |
| `ServiceLoader` báo caller không khai báo service use | Chỉ xảy ra nếu caller là explicit module | Thêm `uses java.net.spi.InetAddressResolverProvider;` vào module gọi `ServiceLoader` |
| Provider class nằm trong unnamed module | Bình thường cho classpath | Không đúng với mode explicit named module |
| Provider module không có trong boot layer | Không áp dụng | Kiểm tra service binding, `uses` và module path |
| `get.count` không bằng 1 | Kiểm tra provider có bị chọn nhầm hoặc resolver đã khởi tạo trước | Kiểm tra provider module nào được resolve/chọn |
| IP không khớp fixture | Kiểm tra map, `LookupPolicy`, cache và fallback | Kiểm tra cùng các yếu tố; module descriptor không thay đổi logic mapping |

### Phân biệt lỗi service descriptor và lỗi provider class

- `jar --list` có descriptor nhưng `getResources` không tìm thấy: JAR không ở system classpath đang chạy hoặc resource đặt sai đường dẫn.
- `getResources` thấy descriptor nhưng `ServiceLoader` không có provider: đọc nội dung file, tên class, class visibility và lỗi cấu hình.
- `ServiceLoader` thấy provider type nhưng class không assignable: kiểm tra provider có thực sự kế thừa `InetAddressResolverProvider` và có dùng đúng class service từ `java.base`.
- `ServiceLoader` discovery thành công nhưng `InetAddress` không dùng provider mong đợi: kiểm tra thứ tự discovery và resolver cấp JVM đã được khởi tạo trước chưa.

### Không trộn hai kiểu đóng gói

Một explicit named module dùng `provides`; một JAR classpath dùng provider configuration file. Không lấy việc resource `META-INF/services` có trong một JAR bất kỳ làm bằng chứng cho module provider đã được resolve. Cũng không đặt cùng một provider đồng thời theo hai cách rồi dựa vào kết quả discovery như thể thứ tự chọn luôn xác định.

## 10. Những lưu ý về class loader, module layer và cache

**System class loader và TCCL:** `InetAddress` dùng system class loader để tìm resolver provider. `ServiceLoader.load(service)` không truyền loader sử dụng TCCL; kết quả có thể khác khi ứng dụng chạy trong plugin framework hoặc application server. Bài dùng overload `ServiceLoader.load(service, systemLoader)` để khớp với đường discovery cần kiểm tra.

**Module layer:** Ví dụ named module chạy qua boot layer và xác minh bằng `ModuleLayer.boot().findModule(...)`. Nếu ứng dụng tự tạo module layer bằng `ModuleLayer.defineModules...` sau khi JVM khởi động, việc provider ở layer riêng có được `InetAddress` dùng hay không phụ thuộc class loader và cách provider được cung cấp cho system-wide discovery. Không giả định mọi module layer tùy biến tự động trở thành nguồn provider của `InetAddress`.

**Cache:** `InetAddress` cache kết quả thành công và thất bại. Chương trình dùng hostname riêng cho từng lần gọi và mỗi mode chạy trong một JVM mới để tránh kết quả cũ. Không suy ra số lần resolver chạy chỉ từ số lần ứng dụng gọi `getAllByName`.

**Không fallback ra DNS thật:** Fixture ném `UnknownHostException` với hostname ngoài map. Điều này làm bài kiểm thử tái lập được mà không cần DNS công cộng. Nếu ứng dụng thực sự cần fallback tới resolver tích hợp, đó là một chính sách khác và nên có bài test riêng.

**Lệnh `java -jar`:** Chế độ `-jar` không dùng classpath truyền bằng `-cp` như cách chạy main class trên classpath. Để provider JAR được tìm thấy, chạy main class bằng `-cp` tường minh hoặc khai báo dependency trong manifest `Class-Path` của application JAR. Named module thì dùng `--module-path` và `-m`.

**Phạm vi kiểm chứng:** Bài này xác minh cách đóng gói, discovery và phân giải hostname. Nó không xác nhận địa chỉ IP có thể kết nối TCP, TLS hay HTTP; muốn kiểm thử kết nối cần server và mạng test riêng.

## 11. Checklist so sánh hai cách triển khai

- [ ] Cùng một `FixtureProvider.java` được biên dịch cho cả hai mode.
- [ ] Cùng map `api.qa.invalid` và `db.qa.invalid` được dùng trong cả hai mode.
- [ ] Classpath JAR có `META-INF/services/java.net.spi.InetAddressResolverProvider` ở gốc archive.
- [ ] Named provider JAR có `module-info.class` khai báo `provides`.
- [ ] Named app khai báo `uses` vì chương trình kiểm tra trực tiếp gọi `ServiceLoader`.
- [ ] Provider class được discovery qua system class loader trong cả hai mode.
- [ ] `Class.forName(..., false, systemLoader)` load class mà không initialize.
- [ ] Trước lookup, marker initialize chưa xuất hiện.
- [ ] Sau lookup, `get.count=1` và IP đúng theo cùng fixture.
- [ ] `missing.qa.invalid` ném `UnknownHostException` trong cả hai mode.
- [ ] Mỗi mode chạy trong một JVM mới.

**Bài tập mở rộng:** Thêm `cache.qa.invalid` → `192.0.2.30` vào cùng map. Không sửa logic provider theo mode. Chạy lại classpath và named module; cả hai phải trả đúng IP mới. Tiếp theo, cố tình xóa service descriptor khỏi JAR classpath và xóa directive `provides` khỏi module descriptor. Quan sát hai kiểu triển khai thất bại ở những bước khác nhau và giải thích dấu hiệu phát hiện tương ứng.

**Tiêu chí hoàn thành:** Hai cách đóng gói dùng chung một provider và một bảng dữ liệu; classpath được xác minh bằng service resource trong JAR; named module được xác minh bằng module descriptor và module resolution; system class loader nhìn thấy provider; `InetAddress` thực sự cài resolver và trả cùng kết quả trên JDK 18 trở lên.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): giới thiệu resolver SPI trong Java 18.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): provider discovery cho resolver cấp JVM.
- [Javadoc ServiceLoader – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider configuration file, UTF-8, `uses`, `provides` và discovery trong named module.
- [Javadoc ServiceLoader.Provider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.Provider.html): xem provider type mà không tạo instance.
- [Javadoc ModuleLayer – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): module layer và module đã được resolve.
- [JLS 25, §7.7 – Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html): hợp đồng ngôn ngữ cho `uses` và `provides`.
- [JDK 25 jar Tool Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): tạo JAR, mô tả module và liệt kê archive.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) và [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737): tên miền và dải IPv4 dành cho tài liệu/kiểm thử.
