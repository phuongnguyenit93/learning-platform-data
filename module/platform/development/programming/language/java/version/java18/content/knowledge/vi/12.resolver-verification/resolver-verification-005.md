# Kiểm tra file service thực sự có trong JAR và provider được nhìn thấy qua system class loader

## 1. Ba điều phải xác minh

Java 18 giới thiệu **Internet-Address Resolution SPI** theo JEP 418. Trên các JDK hiện đại, `InetAddress` vẫn có thể dùng custom resolver do một lớp kế thừa `InetAddressResolverProvider` cung cấp.

Để `InetAddress` sử dụng provider, chỉ biên dịch được class là chưa đủ. Với JAR trên classpath, phải xác minh:

1. JAR chứa đúng provider class và service descriptor.
2. Descriptor có tên chính xác, nội dung UTF-8 hợp lệ và nằm ở `META-INF/services` tại gốc JAR.
3. Descriptor và provider class nhìn thấy qua **system class loader**, vì `InetAddress` dùng loader này để tìm `InetAddressResolverProvider`.
4. Sau discovery, `InetAddress` thực sự gọi `get(Configuration)` để cài resolver và chuyển truy vấn vào resolver.

```text
Mã nguồn provider + service descriptor
               |
               v
       javac + đóng gói JAR
               |
               v
     jar --list --file provider.jar
       |                       |
       v                       v
Có service entry?        Có provider.class?
       |                       |
       +-----------+-----------+
                   |
                   v
  SystemClassLoader.getResources(serviceName)
                   |
                   v
 Đọc descriptor từ URL trong JAR
                   |
                   v
 ServiceLoader.load(service, systemLoader).stream()
                   |
                   v
  Provider.type() / Class.forName(..., false, loader)
                   |
                   v
        InetAddress.getAllByName(host)
                   |
                   v
   provider.get(Configuration) đã được gọi?
```

Các bước tạo bằng chứng khác nhau. `jar --list` xác nhận tên entry; `getResources` xác nhận resource nhìn thấy qua system class loader; `ServiceLoader.Provider.type()` xác nhận provider type có thể discovery mà chưa tạo instance; dấu hiệu từ `get(Configuration)` mới xác nhận `InetAddress` thực sự cài resolver do provider trả về.

## 2. Cấu trúc JAR classpath đúng chuẩn

Ví dụ dùng một provider JAR độc lập và một chương trình kiểm tra nằm ngoài JAR:

```text
resolver-jar-check/
  src/
    provider/demo/resolver/JarResolverProvider.java
    check/demo/check/ProviderVisibilityCheck.java
  build/
    provider-classes/
      demo/resolver/JarResolverProvider.class
      META-INF/services/
        java.net.spi.InetAddressResolverProvider
    resolver-provider.jar
    check-classes/
      demo/check/ProviderVisibilityCheck.class
```

Trong JAR cần có tối thiểu hai entry:

```text
demo/resolver/JarResolverProvider.class
META-INF/services/java.net.spi.InetAddressResolverProvider
```

Tên descriptor được ghép từ tiền tố cố định `META-INF/services/` và tên đầy đủ của service: `java.net.spi.InetAddressResolverProvider`. Nội dung descriptor là tên nhị phân đầy đủ của provider class, mỗi provider một dòng:

```text
demo.resolver.JarResolverProvider
```

Không thêm đuôi `.txt`. Không đặt descriptor trong thư mục nguồn rồi quên copy vào output trước khi đóng gói. JAR có bytecode provider nhưng thiếu entry service descriptor thì `ServiceLoader` không thể tìm provider theo cơ chế classpath.

### Quy tắc nội dung descriptor

Theo Javadoc `ServiceLoader`:

- Tệp provider configuration trên classpath được mã hóa **UTF-8**.
- Mỗi dòng là tên nhị phân đầy đủ của một provider.
- Khoảng trắng và tab ở đầu/cuối tên, dòng trống được bỏ qua.
- Ký tự `#` mở đầu comment; phần còn lại của dòng là comment.
- Tên provider trùng lặp được bỏ qua.
- Provider class có thể ở cùng JAR với descriptor hoặc JAR khác, nhưng phải nhìn thấy từ class loader ban đầu được dùng để tìm descriptor.

Ví dụ hợp lệ:

```text
# Resolver dùng trong integration test
demo.resolver.JarResolverProvider
```

Trong bài kiểm tra này chỉ đăng ký một provider để tránh `InetAddress` chọn provider khác. Khi nhiều provider xuất hiện, thứ tự discovery phụ thuộc triển khai; không dựa vào thứ tự JAR trong classpath như một hợp đồng portable.

## 3. Provider tối giản có dấu hiệu được cài đặt

Tạo `src/provider/demo/resolver/JarResolverProvider.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class JarResolverProvider extends InetAddressResolverProvider {
    private static final String PREFIX = "demo.jarresolver.";
    private static final String HOST = "jar.qa.invalid";
    private static final byte[] ADDRESS = {(byte) 192, 0, 2, 55};

    private static final AtomicInteger GET_COUNT = new AtomicInteger();
    private static final AtomicInteger LOOKUP_COUNT = new AtomicInteger();

    static {
        System.setProperty(PREFIX + "initialized", "true");
    }

    public JarResolverProvider() {
        System.setProperty(PREFIX + "constructor", "true");
    }

    @Override
    public String name() {
        return "jar-classpath-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        System.setProperty(PREFIX + "get.count",
                Integer.toString(GET_COUNT.incrementAndGet()));
        return new JarResolver();
    }

    private static final class JarResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
                throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            System.setProperty(PREFIX + "lookup.count",
                    Integer.toString(LOOKUP_COUNT.incrementAndGet()));

            boolean ipv4Allowed =
                    (policy.characteristics() & LookupPolicy.IPV4) != 0;
            if (!HOST.equalsIgnoreCase(host) || !ipv4Allowed) {
                throw new UnknownHostException(host);
            }

            return Stream.of(InetAddress.getByAddress(HOST, ADDRESS));
        }

        @Override
        public String lookupByAddress(byte[] address)
                throws UnknownHostException {
            Objects.requireNonNull(address, "address");
            if (address.length != 4 && address.length != 16) {
                throw new IllegalArgumentException("IP cần 4 hoặc 16 byte");
            }
            if (Arrays.equals(address, ADDRESS)) {
                return HOST;
            }
            throw new UnknownHostException("IP không có trong fixture");
        }
    }
}
```

Hostname `jar.qa.invalid` và IP `192.0.2.55` là fixture dành cho tài liệu/kiểm thử. Không dùng địa chỉ TEST-NET để kiểm chứng TCP, HTTP hoặc khả năng truy cập máy chủ thật.

Các dấu hiệu trong provider:

- `initialized=true` chỉ chứng minh class đã initialize.
- `constructor=true` chứng minh provider đã được tạo instance.
- `get.count=1` chứng minh `InetAddress` đã gọi `get(Configuration)` và nhận resolver.
- `lookup.count=1` chứng minh resolver đã nhận truy vấn hostname.

Các property là kênh quan sát test-only trong một JVM riêng. Không dùng system property làm metrics sản xuất. Provider cố ý không fallback sang `configuration.builtinResolver()` để hostname ngoài fixture không đi ra DNS công cộng.
## 4. Đóng gói provider JAR trên Windows PowerShell

Đứng tại thư mục `resolver-jar-check`. Tạo các thư mục build và biên dịch provider:

```powershell
New-Item -ItemType Directory -Force -Path `
  "build/provider-classes", `
  "build/check-classes" | Out-Null

javac --release 18 -d build/provider-classes `
  src/provider/demo/resolver/JarResolverProvider.java

New-Item -ItemType Directory -Force -Path `
  "build/provider-classes/META-INF/services" | Out-Null
```

Tạo service descriptor bằng UTF-8 **không BOM**. Đây là điểm cần chú ý với Windows PowerShell 5.1, vì `Set-Content -Encoding UTF8` có thể ghi BOM:

```powershell
$serviceFile = "build/provider-classes/META-INF/services/java.net.spi.InetAddressResolverProvider"
$serviceText = "demo.resolver.JarResolverProvider" + [Environment]::NewLine
[System.IO.File]::WriteAllText(
  $serviceFile,
  $serviceText,
  [System.Text.UTF8Encoding]::new($false)
)
```

Tạo JAR từ thư mục output:

```powershell
jar --create --file build/resolver-provider.jar -C build/provider-classes .
```

`-C build/provider-classes .` thêm nội dung thư mục build vào **gốc JAR**. Nếu đặt thêm một cấp thư mục ngoài ý muốn, entry có thể thành `build/provider-classes/META-INF/services/...` và `ServiceLoader` sẽ không tìm thấy.

## 5. Kiểm tra nội dung JAR trước khi chạy

Liệt kê entry:

```powershell
$entries = jar --list --file build/resolver-provider.jar
$entries
```

Kiểm tra chính xác hai entry cần thiết:

```powershell
$serviceEntry = "META-INF/services/java.net.spi.InetAddressResolverProvider"
$providerEntry = "demo/resolver/JarResolverProvider.class"

if ($entries -notcontains $serviceEntry) {
  throw "JAR thiếu service descriptor: $serviceEntry"
}

if ($entries -notcontains $providerEntry) {
  throw "JAR thiếu provider class: $providerEntry"
}

Write-Output "PASS: JAR có descriptor và provider class"
```

Trên Bash:

```bash
jar --list --file build/resolver-provider.jar
jar --list --file build/resolver-provider.jar | grep -F 'META-INF/services/java.net.spi.InetAddressResolverProvider'
jar --list --file build/resolver-provider.jar | grep -F 'demo/resolver/JarResolverProvider.class'
```

`jar --list` chỉ xác nhận tên entry. Nó chưa chứng minh descriptor có nội dung đúng, class có thể load hoặc system class loader nhìn thấy JAR. Vì vậy cần kiểm tra tiếp từ chương trình Java chạy với classpath thật.

## 6. Phân biệt system class loader với thread context class loader

Đối với resolver của `InetAddress`, Javadoc `InetAddressResolverProvider` quy định provider được tìm bằng `ServiceLoader` với **system class loader**. Khi xác minh khả năng nhìn thấy của provider, hãy chỉ rõ loader:

```java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();

ServiceLoader<InetAddressResolverProvider> services =
        ServiceLoader.load(InetAddressResolverProvider.class, systemLoader);
```

Không dùng mặc định `ServiceLoader.load(InetAddressResolverProvider.class)` để thay cho phép kiểm tra này. Overload không truyền loader sử dụng thread context class loader (TCCL); TCCL có thể là loader con do application server, plugin framework hoặc test runner đặt vào thread. Provider nhìn thấy từ TCCL chưa chắc nhìn thấy từ system class loader.

| Thành phần | Ý nghĩa |
| --- | --- |
| System class loader | Loader mà `InetAddress` dùng để discovery resolver provider |
| Thread context class loader | Loader theo ngữ cảnh thread; thường được dùng bởi `ServiceLoader.load(service)` |
| Custom/child class loader | Loader riêng của plugin hoặc framework; không tự động trở thành loader của `InetAddress` |

Một JAR có trong child loader nhưng không có trong system classpath có thể được ứng dụng plugin nhìn thấy mà `InetAddress` không nhìn thấy. Để resolver provider được tìm trong mô hình classpath tiêu chuẩn, thêm JAR vào classpath lúc khởi chạy JVM.
## 7. Kiểm tra resource và provider type bằng system class loader

Tạo `src/check/demo/check/ProviderVisibilityCheck.java`. Chương trình thực hiện ba bước trước khi gọi `InetAddress`:

1. Dùng `systemLoader.getResources(...)` để liệt kê **tất cả** service descriptor mà system class loader nhìn thấy.
2. Đọc nội dung từng descriptor bằng UTF-8 và xác nhận có tên provider cần kiểm tra; URL có protocol `jar` chứng minh resource đến từ JAR.
3. Dùng `ServiceLoader.Provider.type()` và `Class.forName(name, false, systemLoader)` để xác nhận provider class nhìn thấy được mà chưa initialize provider.

```java
package demo.check;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.URL;
import java.net.spi.InetAddressResolverProvider;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.ServiceLoader;

public final class ProviderVisibilityCheck {
    private static final String PREFIX = "demo.jarresolver.";
    private static final String PROVIDER =
            "demo.resolver.JarResolverProvider";
    private static final String HOST = "jar.qa.invalid";
    private static final String SERVICE_RESOURCE =
            "META-INF/services/" + InetAddressResolverProvider.class.getName();

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static boolean descriptorDeclares(URL resource)
            throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(resource.openStream(),
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

    public static void main(String[] args) throws Exception {
        ClassLoader systemLoader = ClassLoader.getSystemClassLoader();

        // 1. Tìm resource bằng chính system class loader.
        Enumeration<URL> foundResources =
                systemLoader.getResources(SERVICE_RESOURCE);
        List<URL> resources = Collections.list(foundResources);
        require(!resources.isEmpty(),
                "System class loader không thấy service descriptor");

        boolean providerDeclaredInJar = false;
        for (URL resource : resources) {
            System.out.println("Service resource: " + resource);
            if (descriptorDeclares(resource)
                    && "jar".equals(resource.getProtocol())) {
                providerDeclaredInJar = true;
            }
        }
        require(providerDeclaredInJar,
                "Không thấy provider declaration trong URL JAR");

        // 2. Discovery bằng system class loader, chỉ lấy type.
        List<String> providerTypes = ServiceLoader
                .load(InetAddressResolverProvider.class, systemLoader)
                .stream()
                .map(provider -> provider.type().getName())
                .toList();

        require(providerTypes.contains(PROVIDER),
                "ServiceLoader không nhìn thấy provider: " + providerTypes);

        // 3. Load class nhưng không initialize.
        Class<?> providerClass =
                Class.forName(PROVIDER, false, systemLoader);
        require(InetAddressResolverProvider.class.isAssignableFrom(providerClass),
                "Class không kế thừa InetAddressResolverProvider");

        // type() và Class.forName(..., false, ...) không tạo provider instance.
        require(System.getProperty(PREFIX + "initialized") == null,
                "Provider đã initialize trước khi InetAddress được gọi");

        System.out.println("System loader: " + systemLoader);
        System.out.println("Provider class loader: "
                + providerClass.getClassLoader());
        System.out.println("Visible provider types: " + providerTypes);

        // 4. Chỉ lúc này mới kích hoạt resolver cấp JVM của InetAddress.
        InetAddress[] addresses = InetAddress.getAllByName(HOST);
        require(addresses.length == 1, "Cần đúng một IP");
        require("192.0.2.55".equals(addresses[0].getHostAddress()),
                "Sai IP từ provider JAR: " + addresses[0].getHostAddress());

        require("true".equals(System.getProperty(PREFIX + "initialized")),
                "Provider chưa được initialize");
        require("true".equals(System.getProperty(PREFIX + "constructor")),
                "Provider constructor chưa chạy");
        require("1".equals(System.getProperty(PREFIX + "get.count")),
                "InetAddress chưa gọi provider.get(Configuration)");
        require("1".equals(System.getProperty(PREFIX + "lookup.count")),
                "Resolver chưa nhận forward lookup");

        System.out.println("PASS: descriptor nằm trong JAR và system loader nhìn thấy");
        System.out.println("PASS: InetAddress đã cài provider từ JAR");
    }
}
```

`ServiceLoader.stream()` trả về các `ServiceLoader.Provider`. Gọi `Provider.type()` lấy class provider mà không yêu cầu tạo instance; `Provider.get()` mới lấy instance. Bài này không gọi `get()` trước `InetAddress`.

`Class.forName(PROVIDER, false, systemLoader)` yêu cầu system loader load class nhưng không initialize class. Sau hai bước này, marker static vẫn phải chưa tồn tại. Khi `InetAddress.getAllByName` được gọi, marker, constructor, `get.count` và `lookup.count` phải xuất hiện.

Phép kiểm tra `ServiceLoader` là discovery độc lập; nó **chưa chứng minh** `InetAddress` đã chọn provider. Bằng chứng lựa chọn nằm ở marker từ `get(Configuration)` trong lời gọi thật của `InetAddress`.

## 8. Chạy chương trình với provider JAR trên system classpath

Biên dịch chương trình kiểm tra:

```powershell
javac --release 18 -d build/check-classes `
  src/check/demo/check/ProviderVisibilityCheck.java
```

Chạy với provider JAR trên classpath của JVM:

```powershell
java -Djava.net.preferIPv4Stack=true `
  -cp "build/check-classes;build/resolver-provider.jar" `
  demo.check.ProviderVisibilityCheck
```

Trên Bash:

```bash
javac --release 18 -d build/check-classes src/check/demo/check/ProviderVisibilityCheck.java
java -Djava.net.preferIPv4Stack=true -cp "build/check-classes:build/resolver-provider.jar" demo.check.ProviderVisibilityCheck
```

Kết quả dự kiến:

```text
Service resource: jar:file:/.../resolver-provider.jar!/META-INF/services/java.net.spi.InetAddressResolverProvider
System loader: ...
Provider class loader: ...
Visible provider types: [demo.resolver.JarResolverProvider]
PASS: descriptor nằm trong JAR và system loader nhìn thấy
PASS: InetAddress đã cài provider từ JAR
```

Đường dẫn JAR và thông tin loader phụ thuộc hệ điều hành/JDK. Cần xác nhận:

- Resource URL có protocol `jar` và trỏ tới đúng service descriptor.
- Danh sách provider type có `demo.resolver.JarResolverProvider`.
- Marker initialize chưa xuất hiện trước lookup.
- Sau lookup, `get.count=1` và `lookup.count=1`.
- IP trả về đúng fixture.

`-Djava.net.preferIPv4Stack=true` được truyền trước tên lớp main để ví dụ chỉ dùng IPv4. Nếu chạy trên môi trường chỉ có IPv6, cần đổi fixture và policy phù hợp.
## 9. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `jar --list` không có `META-INF/services/...` | Resource chưa được copy vào output hoặc lệnh đóng gói đặt sai gốc |
| Descriptor có trong JAR nhưng `getResources` trả danh sách rỗng | Provider JAR không nằm trên system classpath của tiến trình |
| Resource URL là `file:` thay vì `jar:` | Đang đọc descriptor từ thư mục classes, chưa xác minh descriptor trong JAR |
| Đọc descriptor không thấy tên provider | Sai tên package/class, encoding/BOM, dòng comment hoặc nội dung chưa được đóng gói |
| `Class.forName` thất bại | Thiếu provider class, sai package path hoặc thiếu dependency của provider |
| `ServiceLoader` ném `ServiceConfigurationError` | Provider không đúng kiểu service, tên sai, constructor không hợp lệ hoặc file descriptor lỗi |
| `ServiceLoader` nhìn thấy type nhưng marker không xuất hiện sau lookup | `InetAddress` chưa chọn provider này; có thể có provider khác được tìm thấy trước hoặc resolver đã được khởi tạo từ trước |
| Marker initialize có nhưng `get.count` không có | Class đã initialize do tác động khác; chưa có bằng chứng `InetAddress` cài resolver |
| `get.count=1` nhưng hostname vẫn thất bại | Kiểm tra logic resolver, `LookupPolicy` và hostname fixture |
| Hostname trả IP mặc định của máy | Có thể provider không được chọn hoặc tên đã bị cache; dùng JVM mới và hostname fixture chưa dùng |
| Chạy bằng `java -jar` thì provider JAR biến mất | `-jar` không dùng classpath truyền bằng `-cp` như cách chạy classpath; cần manifest `Class-Path` hoặc chạy với `-cp` |

### Đừng chỉ gọi getResource một lần

`systemLoader.getResource(SERVICE_RESOURCE)` trả về một resource đầu tiên tìm được. Nếu nhiều JAR có cùng service descriptor, phép gọi đó không cho biết các descriptor còn lại. Dùng `getResources` để liệt kê tất cả resource cùng tên và đọc nội dung từng resource.

### Đừng nhầm TCCL với system class loader

Một framework có thể đặt TCCL thành loader plugin để `ServiceLoader.load(service)` tìm thấy provider. Điều đó không thay đổi system class loader mà `InetAddress` dùng. Có thể in cả hai để chẩn đoán:

```java
System.out.println("TCCL: " + Thread.currentThread().getContextClassLoader());
System.out.println("System: " + ClassLoader.getSystemClassLoader());
```

Không cần hai loader là cùng một object. Điều cần thiết là provider class và descriptor nhìn thấy qua **system class loader**.

## 10. Classpath JAR và named module

Bài này kiểm tra cách triển khai provider dạng JAR **trên classpath**, dùng tệp `META-INF/services`. Nếu ứng dụng đóng gói provider thành **named module** trên module path, cách đăng ký tiêu chuẩn là khai báo trong `module-info.java`:

```java
module demo.resolver.provider {
    provides java.net.spi.InetAddressResolverProvider
        with demo.resolver.JarResolverProvider;
}
```

Với named module, provider được mô tả bằng directive `provides` trong module descriptor. Không dùng việc có tệp service ở classpath làm bằng chứng thay thế cho việc module đã được resolve và provider được khai báo đúng trên module path. Nếu chương trình kiểm tra tự gọi `ServiceLoader.load` từ named module, module consumer còn cần khai báo `uses` cho service tương ứng.

| Kiểu triển khai | Nơi đăng ký | Cách khởi chạy |
| --- | --- | --- |
| JAR classpath (bài này) | `META-INF/services/java.net.spi.InetAddressResolverProvider` | `java -cp app-classes;provider.jar Main` |
| Named module | `provides ... with ...` trong `module-info.java` | `java --module-path ... -m module/main` |

### Lưu ý về lệnh java -jar

Nếu khởi chạy ứng dụng bằng `java -jar application.jar`, tùy chọn classpath `-cp` không được dùng như trong chế độ chạy classpath. Để provider JAR được tìm thấy, có thể chạy main class với `-cp` chứa cả ứng dụng và provider JAR, hoặc khai báo provider JAR trong manifest `Class-Path` của application JAR theo quy tắc đường dẫn manifest.

Trong kiểm thử này, dùng `-cp` tường minh giúp xác định rõ JAR nào thuộc system classpath.

## 11. Checklist trước khi kết luận provider được nạp từ JAR

- [ ] `jar --list --file` hiển thị `META-INF/services/java.net.spi.InetAddressResolverProvider` ở gốc JAR.
- [ ] JAR có class entry `demo/resolver/JarResolverProvider.class`.
- [ ] Descriptor được mã hóa UTF-8 và chứa tên provider đầy đủ.
- [ ] `ClassLoader.getSystemClassLoader().getResources(...)` tìm được descriptor.
- [ ] Đọc descriptor qua URL `jar:` thấy đúng provider class.
- [ ] `ServiceLoader.load(service, systemLoader).stream()` có provider type mong đợi.
- [ ] `Class.forName(name, false, systemLoader)` thành công.
- [ ] Static marker chưa xuất hiện trước lần lookup của `InetAddress`.
- [ ] Sau `InetAddress.getAllByName`, marker và `get.count` xuất hiện.
- [ ] Kết quả IP và lookup counter phù hợp fixture.
- [ ] Chỉ có một resolver provider trong classpath kiểm thử để tránh thứ tự discovery không xác định.

**Tiêu chí hoàn thành:** Có thể chỉ ra chính xác service descriptor nằm trong JAR, đọc được nó bằng system class loader, load được provider class mà chưa initialize, rồi chứng minh `InetAddress` thực sự gọi provider để cài resolver. Các bước chạy lặp lại được trên JDK 18 trở lên mà không phụ thuộc DNS công cộng.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): API resolver SPI được đưa vào Java 18.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): `InetAddress` tìm provider bằng `ServiceLoader` và system class loader.
- [Javadoc ServiceLoader – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider configuration file trên classpath, UTF-8, discovery và `Provider.type()`.
- [Javadoc ServiceLoader.Provider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.Provider.html): lấy provider type mà không tạo instance.
- [JDK 25 jar Tool Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): tạo JAR và liệt kê nội dung archive.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) và [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737): miền và dải IPv4 dành cho tài liệu/kiểm thử.
