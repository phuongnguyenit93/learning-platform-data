# Chứng minh provider đã được nạp bằng dấu hiệu khởi tạo và bộ đếm lời gọi

## 1. Điều cần chứng minh

Java 18 đưa vào **Internet-Address Resolution SPI** theo JEP 418. Trên JDK hiện đại, ứng dụng vẫn có thể cung cấp `InetAddressResolverProvider` để tạo một `InetAddressResolver` dùng bởi `InetAddress`.

Khi kiểm thử custom resolver, một kết quả IP đúng chưa đủ chứng minh provider đã được nạp. Ta cần phân biệt bốn mốc:

1. **Class được load:** JVM đã tìm và nạp bytecode của provider.
2. **Class được initialize:** static initializer (`<clinit>`) đã chạy.
3. **Provider được tạo và được chọn:** `ServiceLoader` tạo instance; `InetAddress` gọi `get(Configuration)` để lấy resolver.
4. **Resolver nhận truy vấn:** `lookupByName` hoặc `lookupByAddress` thực sự được gọi.

Static initializer chứng minh class đã được khởi tạo; constructor chứng minh có instance được tạo; `get(Configuration)` là dấu hiệu mạnh cho thấy provider được `InetAddress` dùng để cài resolver toàn JVM; bộ đếm lookup chứng minh truy vấn đã đi vào resolver.

### Vòng đời rút gọn của provider

```text
Lần phân giải hostname đầu tiên sau khi JVM boot
        |
        v
InetAddress cần system-wide resolver
        |
        v
ServiceLoader tìm provider bằng system class loader
        |
        v
Khởi tạo class -> static initializer
        |
        v
Tạo provider -> constructor
        |
        v
InetAddress gọi provider.get(Configuration)
        |
        v
Cài resolver dùng cho toàn JVM
        |
        v
lookupByName(host, policy) / lookupByAddress(bytes)
```

Theo Javadoc Java SE 25, một lần chạy JVM duy trì một resolver hệ thống. Provider được tìm bằng `ServiceLoader` và system class loader; thứ tự tìm thấy phụ thuộc triển khai, provider đầu tiên được dùng. Nếu không tìm thấy provider, resolver tích hợp được chọn. Nếu khởi tạo resolver tùy biến thất bại, lỗi được truyền về lời gọi đã kích hoạt việc khởi tạo. Lookup trước khi JVM boot hoàn tất có thể dùng resolver tích hợp.

## 2. Chọn tín hiệu quan sát đúng

| Tín hiệu | Chứng minh điều gì? | Đủ để chứng minh provider được chọn? |
| --- | --- | --- |
| `-Xlog:class+load=info` | Class bytecode đã được load | Không |
| Static initializer | Class đã được initialize | Chưa |
| Constructor counter | Instance provider đã được tạo | Chưa chắc |
| `get(Configuration)` counter | `InetAddress` yêu cầu provider tạo resolver | **Có** |
| `lookupByName` counter | Truy vấn hostname đã vào resolver | **Có, cho truy vấn đó** |
| `lookupByAddress` counter | Truy vấn reverse đã vào resolver | **Có, cho truy vấn đó** |
| IP trả về đúng | Kết quả phân giải phù hợp | Một mình nó không đủ |

Không dùng riêng `name()` làm bằng chứng: API yêu cầu provider trả tên hoặc `null`, nhưng việc gọi phương thức này không thể thay thế dấu hiệu từ `get(Configuration)` và lookup.

**Bẫy lớn nhất:** Nếu test gọi `new ProbeProvider()`, `Class.forName("...", true, ...)` hoặc một static method của provider trước khi gọi `InetAddress`, test có thể tự khởi tạo provider. Khi đó static initializer chạy dù `InetAddress` chưa hề chọn provider. `ProbeProvider.class` có thể làm class được load/resolve, nhưng class literal tự nó không chạy static initializer. Bài này quan sát bằng system property có tiền tố riêng và không tham chiếu class provider trong mã test.

## 3. Provider có marker và bộ đếm

Ví dụ dùng hostname `probe.qa.invalid` và IP tài liệu `192.0.2.42`. Miền `.invalid` và dải `192.0.2.0/24` dành riêng cho ví dụ/kiểm thử; không dùng IP này để kiểm tra kết nối mạng thật.

Cấu trúc:

```text
resolver-probe/
  src/demo/resolver/
    ProbeProvider.java
    ProviderProbe.java
  out/
    META-INF/services/
      java.net.spi.InetAddressResolverProvider
```
Tệp `src/demo/resolver/ProbeProvider.java`:

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

public final class ProbeProvider extends InetAddressResolverProvider {
    private static final String PREFIX = "demo.resolver.probe.";

    private static final AtomicInteger CONSTRUCTOR_COUNT =
            new AtomicInteger();
    private static final AtomicInteger GET_COUNT =
            new AtomicInteger();
    private static final AtomicInteger FORWARD_COUNT =
            new AtomicInteger();
    private static final AtomicInteger REVERSE_COUNT =
            new AtomicInteger();

    private static final String HOST = "probe.qa.invalid";
    private static final byte[] ADDRESS = {(byte) 192, 0, 2, 42};

    static {
        // Chỉ chứng minh class đã được initialize.
        System.setProperty(PREFIX + "initialized", "true");
    }

    public ProbeProvider() {
        publish("constructor.count", CONSTRUCTOR_COUNT.incrementAndGet());
    }

    @Override
    public String name() {
        return "resolver-probe";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");
        publish("get.count", GET_COUNT.incrementAndGet());
        return new ProbeResolver();
    }

    private static void publish(String key, int value) {
        // Kênh quan sát test-only trong cùng JVM.
        System.setProperty(PREFIX + key, Integer.toString(value));
    }

    private static final class ProbeResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
                throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            publish("lookup.forward.count",
                    FORWARD_COUNT.incrementAndGet());

            boolean ipv4Allowed =
                    (policy.characteristics() & LookupPolicy.IPV4) != 0;
            if (!HOST.equalsIgnoreCase(host) || !ipv4Allowed) {
                throw new UnknownHostException(host);
            }

            // Tạo từ byte đã biết, không gọi DNS lồng nhau.
            return Stream.of(InetAddress.getByAddress(HOST, ADDRESS));
        }

        @Override
        public String lookupByAddress(byte[] address)
                throws UnknownHostException {
            Objects.requireNonNull(address, "address");
            publish("lookup.reverse.count",
                    REVERSE_COUNT.incrementAndGet());
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

Bốn bộ đếm có vai trò khác nhau:

- `CONSTRUCTOR_COUNT` tăng khi một instance provider được tạo. Với đúng một provider trên classpath, kỳ vọng là 1.
- `GET_COUNT` tăng trong `get(Configuration)`. Đây là dấu hiệu trực tiếp `InetAddress` đã gọi provider để cài resolver hệ thống.
- `FORWARD_COUNT` tăng mỗi khi `lookupByName` thực sự chạy. Ca dương tính và âm tính đều được đếm.
- `REVERSE_COUNT` tăng mỗi khi `lookupByAddress` chạy. Phần kiểm thử sẽ kích hoạt reverse lookup qua `InetAddress.getCanonicalHostName()`.

Static initializer ghi marker `initialized=true`. Nó chứng minh class đã được initialize, **không tự nó chứng minh** resolver được chọn. Bộ đếm `get.count` và kết quả lookup bổ sung bằng chứng còn thiếu.

Các property dùng tiền tố `demo.resolver.probe.` để tránh đụng tên property ứng dụng. Đây là kênh quan sát test-only cho kiểm thử tuần tự trong JVM biệt lập; không dùng các system property này làm metrics sản xuất.
## 4. Đăng ký provider bằng ServiceLoader

Tệp service descriptor **không có đuôi mở rộng**:

```text
META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung:

```text
demo.resolver.ProbeProvider
```

Tệp phải nằm trên classpath của JVM kiểm thử. Nếu ứng dụng dùng named module, có thể đăng ký provider bằng khai báo `provides java.net.spi.InetAddressResolverProvider with demo.resolver.ProbeProvider;` trong `module-info.java`, theo cấu trúc module phù hợp.

Provider là lớp concrete có constructor không tham số. Trong bài này chỉ đăng ký **một provider** để tránh phụ thuộc thứ tự tìm thấy khi nhiều provider cùng hiện diện. Không kết hợp `-Djdk.net.hosts.file` với ca kiểm tra SPI này vì một resolver dựa trên tệp hosts có thể làm thay đổi đường phân giải đang được kiểm chứng.

## 5. Test quan sát mà không tự khởi tạo provider

Mã test chỉ dùng `System.getProperty` để đọc marker/counter; nó không import provider, gọi static method hoặc khởi tạo provider. Điều này quan trọng vì class initialization trong Java có thể xảy ra do thao tác của chính test, tạo bằng chứng giả.

Thứ tự test có chủ đích:

1. Đọc marker trước lookup và xác nhận nó chưa tồn tại trong JVM mới.
2. Gọi `InetAddress.getAllByName("probe.qa.invalid")` để kích hoạt cơ chế phân giải hostname.
3. Kiểm tra marker static, constructor counter và `get.count`.
4. Gọi `InetAddress.getCanonicalHostName()` trên địa chỉ được tạo từ byte để kiểm tra reverse lookup.
5. Gọi hostname âm tính riêng biệt để xác nhận resolver được gọi và ném `UnknownHostException`.

Không dùng IP literal làm đầu vào forward test: `InetAddress` có thể phân tích địa chỉ ngay mà không gọi `lookupByName`. Với reverse test, `InetAddress.getByAddress(byte[])` tạo đối tượng IP mà không cần phân giải tên; `getCanonicalHostName()` là API dùng system-wide resolver để thực hiện reverse lookup.
## 6. Chương trình kiểm thử trong JVM mới

Tệp `src/demo/resolver/ProviderProbe.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.Arrays;

public final class ProviderProbe {
    private static final String PREFIX = "demo.resolver.probe.";

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static String property(String name) {
        return System.getProperty(PREFIX + name);
    }

    private static void expectCount(String name, int expected) {
        String actual = property(name);
        require(Integer.toString(expected).equals(actual),
                name + ": expected " + expected + ", actual " + actual);
    }

    private static int count(String name) {
        String value = property(name);
        require(value != null, "Chưa có counter " + name);
        return Integer.parseInt(value);
    }

    public static void main(String[] args) throws Exception {
        // Test không tham chiếu ProbeProvider trước lookup đầu tiên.
        require(property("initialized") == null,
                "Provider đã initialize trước phép thử");
        require(property("constructor.count") == null,
                "Provider đã được tạo trước phép thử");

        // 1. Tra cứu hostname dương tính qua API thật của InetAddress.
        InetAddress[] found =
                InetAddress.getAllByName("probe.qa.invalid");

        require(found.length == 1, "Cần đúng một địa chỉ");
        require("192.0.2.42".equals(found[0].getHostAddress()),
                "Sai địa chỉ: " + Arrays.toString(found));

        // 2. Xác minh các mốc vòng đời provider.
        require("true".equals(property("initialized")),
                "Static initializer chưa chạy");
        expectCount("constructor.count", 1);
        expectCount("get.count", 1);
        expectCount("lookup.forward.count", 1);

        // 3. Reverse lookup qua API dùng system-wide resolver.
        InetAddress raw = InetAddress.getByAddress(
                new byte[] {(byte) 192, 0, 2, 42});
        String reverse = raw.getCanonicalHostName();
        require("probe.qa.invalid".equals(reverse),
                "Sai reverse lookup: " + reverse);
        expectCount("lookup.reverse.count", 1);

        // 4. Hostname chưa có trong bảng phải đi vào resolver và thất bại.
        int beforeMissing = count("lookup.forward.count");
        try {
            InetAddress.getAllByName("missing.qa.invalid");
            throw new AssertionError("Phải ném UnknownHostException");
        } catch (UnknownHostException expected) {
            // Kết quả mong đợi.
        }
        expectCount("lookup.forward.count", beforeMissing + 1);
        expectCount("get.count", 1);

        System.out.println("PASS provider.initialized=true");
        System.out.println("PASS provider.constructor.count=1");
        System.out.println("PASS provider.get.count=1");
        System.out.println("PASS resolver.forward.count >= 2");
        System.out.println("PASS resolver.reverse.count=1");
    }
}
```

**Điểm quan trọng:** test không import, gọi static method hay khởi tạo `ProbeProvider`. Nó chỉ đọc system property bằng `System.getProperty`. Descriptor là nơi duy nhất khai báo tên provider; `InetAddress` tự tìm và khởi tạo provider khi test thực hiện tra cứu hostname đầu tiên.

Nếu test tham chiếu provider trước, điều kiện marker ban đầu sẽ thất bại. Điều này giúp phát hiện false positive do chính mã test kích hoạt static initializer.
## 7. Biên dịch và chạy test

Từ thư mục `resolver-probe`, tạo hai tệp Java theo nội dung ở trên và service descriptor ở phần 4.

### PowerShell trên Windows

```powershell
New-Item -ItemType Directory -Force -Path "out/META-INF/services" | Out-Null
javac --release 18 -d out src/demo/resolver/ProbeProvider.java src/demo/resolver/ProviderProbe.java
Set-Content -Encoding Ascii -Path "out/META-INF/services/java.net.spi.InetAddressResolverProvider" -Value "demo.resolver.ProbeProvider"
java -Djava.net.preferIPv4Stack=true -cp out demo.resolver.ProviderProbe
```

### Bash trên Linux/macOS

```bash
mkdir -p out/META-INF/services
javac --release 18 -d out src/demo/resolver/ProbeProvider.java src/demo/resolver/ProviderProbe.java
printf '%s\n' 'demo.resolver.ProbeProvider' > out/META-INF/services/java.net.spi.InetAddressResolverProvider
java -Djava.net.preferIPv4Stack=true -cp out demo.resolver.ProviderProbe
```

`--release 18` giới hạn API biên dịch ở Java 18; mã có thể chạy trên JDK 18 trở lên. `-Djava.net.preferIPv4Stack=true` được truyền trước class main để fixture IPv4 phù hợp chính sách phân giải của tiến trình. Mỗi lệnh `java` mở một JVM mới, nên marker và bộ đếm bắt đầu từ trạng thái rỗng.

Kết quả dự kiến:

```text
PASS provider.initialized=true
PASS provider.constructor.count=1
PASS provider.get.count=1
PASS resolver.forward.count >= 2
PASS resolver.reverse.count=1
```

Nếu `get.count` không xuất hiện, hãy kiểm tra service descriptor, classpath/module-path, tên lớp đầy đủ và lỗi trong quá trình khởi tạo. Nếu marker khởi tạo có nhưng `get.count` không có, class provider đã được initialize nhưng chưa có bằng chứng `InetAddress` đã gọi provider để cài resolver.

## 8. Quan sát class loading bằng unified logging

Static marker cho biết class đã được **initialize**. Nếu cần bằng chứng riêng về giai đoạn **load class**, unified logging của HotSpot có thể hiển thị cả sự kiện tải lớp lẫn khởi tạo:

```powershell
java -Xlog:class+load=info,class+init=info -Djava.net.preferIPv4Stack=true -cp out demo.resolver.ProviderProbe 2>&1 | Select-String -Pattern "ProbeProvider|ProbeResolver"
```

Trên Bash:

```bash
java -Xlog:class+load=info,class+init=info -Djava.net.preferIPv4Stack=true -cp out demo.resolver.ProviderProbe 2>&1 | grep -E 'ProbeProvider|ProbeResolver'
```

Log có thể chứa nhiều dòng từ thư viện JDK. Lọc theo tên class giúp xem đúng sự kiện cần kiểm chứng. Cú pháp `-Xlog` là unified logging hiện hành trên JDK hiện đại.

**Diễn giải đúng:**

- Dòng `class,load` chứng minh JVM đã nạp bytecode của class.
- Dòng `class,init` và marker system property chứng minh class đã được khởi tạo.
- Constructor counter chứng minh instance provider được tạo.
- `get.count=1` chứng minh `InetAddress` đã yêu cầu provider trả resolver để cài toàn JVM.
- `lookup.forward.count`/`lookup.reverse.count` chứng minh từng loại truy vấn đã thực sự tới resolver.

Log tải lớp không thay thế counter của `get(Configuration)`. Một class có thể được load hoặc initialize bởi code khác mà không được chọn làm resolver hệ thống.

## 9. Hiểu counter, cache và các trường hợp dễ gây kết luận sai

### 9.1. Số lần gọi API không bằng số lần resolver chạy

`InetAddress` cache kết quả phân giải tên thành công và thất bại. Nếu gọi cùng hostname hai lần khi cache còn hiệu lực, lần thứ hai có thể được trả từ cache mà không gọi lại `lookupByName`.

Vì vậy:

- `get.count` đếm việc provider tạo resolver; trong JVM cô lập của ví dụ kỳ vọng là 1.
- `lookup.forward.count` đếm lần resolver thực sự nhận truy vấn; nó không nhất thiết bằng số lần ứng dụng gọi `getAllByName`.
- `lookup.reverse.count` cũng có thể bị cache reverse che ở những lần gọi sau.
- Test dùng JVM mới, hostname dương tính mới và hostname âm tính mới để đo lần đầu, tránh dựa vào TTL của lần chạy trước.

Nếu cần kiểm tra cache, hãy tạo suite riêng và cấu hình security properties trước khi JVM khởi chạy. `networkaddress.cache.ttl`, `networkaddress.cache.negative.ttl` và `networkaddress.cache.stale.ttl` là **security properties**; không đặt chúng bằng `-D...` hoặc `System.setProperty` rồi kỳ vọng JDK áp dụng. Giá trị mặc định và thời gian lưu có thể phụ thuộc triển khai/JDK.

### 9.2. Không tự khởi tạo provider trong test

Những thao tác sau có thể làm static initializer chạy trước lần lookup muốn quan sát:

```java
// Các thao tác này làm sai điều kiện kiểm thử:
new ProbeProvider();
Class.forName("demo.resolver.ProbeProvider", true,
        ClassLoader.getSystemClassLoader());
ProbeProvider.someStaticMethod();
```

Không dùng chúng trước khi gọi `InetAddress.getAllByName`. Test trong bài chỉ đọc property bằng tên chuỗi; nó không có tham chiếu class-level tới provider. Descriptor cung cấp tên lớp để `ServiceLoader` tìm thấy.

Lưu ý: `ProbeProvider.class` có thể khiến JVM nạp/resolve metadata của class, nhưng bản thân class literal **không chạy static initializer**. Nếu đang đo riêng giai đoạn load class, tránh cả thao tác này trước khi ghi nhận baseline; nếu đo initialization, hãy quan sát marker static.

### 9.3. Phân biệt load, initialize, instantiate và install

| Mốc | Dấu hiệu | Cách diễn giải |
| --- | --- | --- |
| Load | Unified log `class+load` | Bytecode được nạp vào JVM |
| Initialize | `static` marker | Khối static đã chạy |
| Instantiate | Constructor counter | Instance provider được tạo |
| Install | Counter trong `get(Configuration)` | `InetAddress` nhận resolver từ provider |
| Use | Counter trong `lookupByName`/`lookupByAddress` | Một truy vấn thực sự đi vào resolver |

Một constructor counter riêng chưa đủ chứng minh provider được chọn vì code khác có thể tạo instance thủ công. Một static marker riêng cũng chưa đủ vì class có thể được initialize bởi test. Kết hợp marker, constructor, `get` và lookup counter trong một tiến trình sạch tạo bằng chứng rõ ràng hơn.

### 9.4. Đọc lỗi khởi tạo

Nếu `get(Configuration)` ném exception hoặc error, `InetAddress` không cài resolver tùy biến và lỗi được truyền về caller đã kích hoạt lookup. Không được xem fallback về resolver tích hợp là kết quả thành công sau lỗi `get`. Khi test thất bại, hãy giữ stack trace và các marker trước khi kết luận provider không được nạp.

### 9.5. Giữ marker đơn giản

`System.setProperty` chỉ là kênh chẩn đoán trong ví dụ. Nó thay đổi trạng thái global của JVM, có thể gây xung đột với test khác và không phù hợp cho metrics ứng dụng. Dùng prefix riêng, chạy test tuần tự trong JVM mới và không tái sử dụng các key này ngoài suite.

Với kiểm thử đồng thời hoặc ứng dụng thực, hãy dùng logging/metrics có scope rõ ràng. `AtomicInteger` đảm bảo phép tăng an toàn giữa nhiều thread, nhưng việc ghi snapshot ra system property không phải một giao thức telemetry hoàn chỉnh.

## 10. Checklist và câu hỏi tự kiểm tra

- [ ] Provider chỉ được đăng ký một lần trong service descriptor hoặc module descriptor.
- [ ] Test chạy trong JVM mới, trước lookup marker khởi tạo và constructor chưa tồn tại.
- [ ] Test không gọi `new ProbeProvider()` hoặc static method của provider trước lookup.
- [ ] Hostname được dùng là tên, không phải IP literal.
- [ ] IP trả về khớp fixture.
- [ ] Static marker và constructor counter xuất hiện sau lookup đầu tiên.
- [ ] `get.count` xác nhận `InetAddress` đã cài resolver từ provider.
- [ ] Counter forward/reverse xác nhận các phương thức resolver đã được gọi.
- [ ] Test âm tính dùng hostname riêng và xác nhận `UnknownHostException`.
- [ ] Không suy ra số lần lookup từ số lần gọi API vì `InetAddress` có cache.

**Bài tập:** Tạo một provider thứ hai có marker riêng. Đưa cả hai descriptor vào cùng classpath, chạy test và quan sát provider nào được chọn. Lặp lại trên JDK/triển khai khác nhau; giải thích vì sao không nên dựa vào thứ tự tìm thấy provider. Sau đó bỏ descriptor và chạy lại: marker, constructor và `get.count` phải không xuất hiện, đồng thời hostname fixture không được phân giải thành công.

**Tiêu chí hoàn thành:** Có thể chứng minh riêng class đã initialize, provider đã được tạo, `InetAddress` đã gọi `get(Configuration)` và resolver đã nhận forward/reverse lookup. Bài kiểm thử phân biệt được lỗi đăng ký SPI với lỗi logic resolver và không bị kết quả cache làm sai kết luận.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): API resolver SPI được đưa vào Java 18.
- [Javadoc InetAddressResolverProvider – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): vòng đời resolver toàn JVM, tìm provider qua system class loader và thời điểm gọi `get(Configuration)`.
- [Javadoc InetAddressResolver – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng forward và reverse lookup.
- [Javadoc InetAddress – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): `getAllByName`, `getCanonicalHostName` và cache.
- [Java Networking Properties – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html): các security properties điều khiển cache hostname.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) và [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737): miền và IPv4 dành riêng cho tài liệu/kiểm thử.
