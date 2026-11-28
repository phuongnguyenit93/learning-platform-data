# Kiểm chứng lỗi trong constructor hoặc get(Configuration) được truyền tới bên kích hoạt tra cứu

> **Phạm vi học tập:** Bài thuộc chương **Kiểm chứng resolver** của `JAVA_VERSION_JAVA18`, trong mạch kiến thức Java 18 còn hữu ích trên JDK hiện đại. Trọng tâm là chứng minh bằng thử nghiệm rằng lỗi khi khởi tạo `InetAddressResolverProvider` — ở constructor hoặc `get(Configuration)` — **không bị âm thầm bỏ qua**: thao tác `InetAddress` đầu tiên kích hoạt thiết lập resolver sẽ quan sát được thất bại. Bài dùng API công khai từ JEP 418 và `ServiceLoader`, tránh kỹ thuật nội bộ hoặc legacy.

## 1. Phát biểu chính xác hợp đồng cần kiểm chứng

JEP 418 giới thiệu Internet-Address Resolution SPI từ Java 18:

- `InetAddressResolverProvider` là service provider được JDK tìm thấy và dùng để tạo một resolver.
- `InetAddressResolver` là đối tượng thực sự thực hiện `lookupByName` và `lookupByAddress`.
- `InetAddressResolverProvider.Configuration` cung cấp resolver tích hợp qua `builtinResolver()` và tên máy local qua `lookupLocalHostName()`.

Theo Javadoc hiện hành của `InetAddressResolverProvider`:

1. Sau khi VM khởi động xong, một lời gọi `InetAddress` **cần tra cứu tên** có thể kích hoạt việc cài đặt resolver cho toàn JVM.
2. JDK dùng `ServiceLoader` với **system class loader** để phát hiện provider. Provider đầu tiên được tìm thấy theo thứ tự phụ thuộc implementation sẽ được chọn.
3. JDK tạo provider rồi gọi `get(Configuration)` để nhận `InetAddressResolver`. Resolver trả về sẽ trở thành resolver dùng chung trong JVM.
4. **Nếu không tìm thấy provider**, JDK dùng resolver tích hợp.
5. **Nếu đã tìm thấy provider nhưng việc khởi tạo resolver ném error hoặc exception**, resolver toàn JVM **không được thiết lập ở lần thử đó**, và lỗi được truyền tới caller của thao tác kích hoạt tra cứu.

Điểm (4) và (5) **khác nhau**. Không được coi lỗi constructor hoặc lỗi `get` là một tín hiệu “hãy chọn built-in resolver”.

Sơ đồ:

~~~text
Lần đầu InetAddress cần lookup sau khi JVM khởi động
                       │
                       ▼
          ServiceLoader tìm provider
                │              │
                │ Có           └── Không tìm thấy
                ▼                       │
       Khởi tạo provider                ▼
                │                 Dùng built-in
                ▼
       provider.get(Configuration)
                │
          ┌─────┴─────────┐
          │               │
        Thành công      Ném lỗi
          │               │
          ▼               ▼
  Cài resolver         Không cài resolver
  toàn JVM             ở lần thử đó
          │               │
          ▼               ▼
     Tiếp tục         Lỗi truyền tới caller
    lookup tên         kích hoạt lookup
~~~

**Phạm vi kết luận:** Đây là hành vi khi **cài đặt resolver**, không phải hợp đồng của một truy vấn đã đi vào `lookupByName` hoặc `lookupByAddress`. `UnknownHostException` khi tra cứu hostname không tồn tại là lỗi ở giai đoạn **lookup**, khác với lỗi khởi tạo provider.

## 2. Phân biệt ba điểm phát sinh lỗi

| Nguồn lỗi | Giai đoạn | Biểu hiện bên kích hoạt tra cứu |
|---|---|---|
| Không có provider | Discovery | JDK dùng resolver tích hợp; không phải lỗi khởi tạo custom resolver. |
| Constructor provider ném lỗi | Khởi tạo instance provider qua `ServiceLoader` | Lời gọi kích hoạt lookup thất bại; có thể quan sát `ServiceConfigurationError` bọc nguyên nhân. |
| `get(Configuration)` ném lỗi | Tạo resolver từ provider đã được khởi tạo | Lời gọi kích hoạt lookup nhận lỗi; không có fallback ngầm theo hợp đồng. |
| `lookupByName` ném `UnknownHostException` | Phân giải hostname sau khi resolver đã được cài | Đây là thất bại lookup thông thường, không phải bằng chứng constructor/get lỗi. |
| `lookupByAddress` ném `UnknownHostException` | Phân giải ngược IP sau khi resolver đã được cài | Đây là thất bại lookup ngược, không phải lỗi tạo provider. |

### Vì sao loại exception quan sát được có thể khác nhau?

Constructor của provider được `ServiceLoader` gọi qua cơ chế nạp service. Nếu constructor ném `IllegalStateException`, lớp bao ngoài có thể là `ServiceConfigurationError` hoặc một lỗi khác liên quan đến việc nạp provider. Ngược lại, `get(Configuration)` có thể truyền trực tiếp lỗi do nó ném.

Vì vậy, để kiểm chứng **nguyên nhân**, không nên chỉ viết:

~~~java
catch (IllegalStateException expected) {
    // Không đủ cho cả lỗi constructor và get.
}
~~~

Nên kiểm tra cả **chuỗi nguyên nhân** (`getCause()`) và một thông điệp marker cố định do bài test cố ý tạo ra. Không giả định stack trace và lớp exception ngoài cùng sẽ giống nhau trên mọi JDK.

## 3. Thiết kế thử nghiệm không phụ thuộc DNS ngoài

Ta sử dụng một provider có ba chế độ, chọn qua system property `demo.fail`:

| Giá trị `demo.fail` | Hành vi cố ý | Kỳ vọng |
|---|---|---|
| `none` | Constructor/get thành công, resolver trả địa chỉ cho tên thử nghiệm. | Lookup trả `192.0.2.45`. |
| `constructor` | Constructor provider ném `IllegalStateException` chứa marker `DEMO_CONSTRUCTOR_FAILED`. | Lời gọi `InetAddress.getByName` quan sát lỗi; marker có trong chuỗi nguyên nhân. |
| `get` | Constructor thành công, `get(Configuration)` ném `IllegalStateException` chứa marker `DEMO_GET_FAILED`. | Lời gọi `InetAddress.getByName` quan sát lỗi; marker có trong chuỗi nguyên nhân. |

Hostname test là `probe.lab.invalid` và địa chỉ `192.0.2.45` (dải dành cho tài liệu). Provider tự trả dữ liệu này trong chế độ `none`, nên không cần mạng hoặc DNS thật.

**Quy tắc quan trọng:** Mỗi chế độ chạy trong **một tiến trình JVM mới**. Resolver toàn JVM chỉ được thiết lập khi một lookup cần sử dụng nó; đổi `System.setProperty` trong cùng JVM sau lần đầu lookup không phải cách đáng tin cậy để tạo lại hành vi khởi tạo.

## 4. Cấu trúc dự án thử nghiệm trên classpath

Ví dụ dùng JDK 18 trở lên với resource `META-INF/services` chuẩn:

~~~text
resolver-init-verification/
├── src/
│   ├── verify/
│   │   └── resolver/
│   │       └── ProbeProvider.java
│   └── ProbeMain.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── java.net.spi.InetAddressResolverProvider
└── build/
    ├── classes/
    ├── app/
    └── probe-provider.jar
~~~

Nội dung chính xác của tệp `resources/META-INF/services/java.net.spi.InetAddressResolverProvider`:

~~~text
verify.resolver.ProbeProvider
~~~

Tệp này là UTF-8; một dòng chứa **tên lớp triển khai đầy đủ**. Tên **tệp** phải là tên đầy đủ của **service** (`java.net.spi.InetAddressResolverProvider`), không phải tên lớp `ProbeProvider`.

Có thể đặt provider và ứng dụng trong cùng classpath, nhưng tách JAR giúp minh họa chính xác bước service discovery. Bài dùng classpath chứ không dùng `module-info.java`; với named module, đăng ký bằng `provides ... with ...`.

## 5. Lớp provider có thể gây lỗi có kiểm soát

Tệp `src/verify/resolver/ProbeProvider.java`:

~~~java
package verify.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Stream;

public final class ProbeProvider extends InetAddressResolverProvider {
    private static final String HOST = "probe.lab.invalid";
    private static final byte[] IP = {(byte) 192, 0, 2, 45};

    // Public, không tham số: tương thích ServiceLoader trên classpath.
    public ProbeProvider() {
        if ("constructor".equals(System.getProperty("demo.fail", "none"))) {
            throw new IllegalStateException("DEMO_CONSTRUCTOR_FAILED");
        }
    }

    @Override
    public String name() {
        return "probe-provider";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        if ("get".equals(System.getProperty("demo.fail", "none"))) {
            throw new IllegalStateException("DEMO_GET_FAILED");
        }

        Objects.requireNonNull(configuration, "configuration");
        InetAddressResolver builtIn = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                Objects.requireNonNull(host, "host");
                Objects.requireNonNull(policy, "policy");

                if (!HOST.equalsIgnoreCase(host)) {
                    return builtIn.lookupByName(host, policy);
                }

                if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            "No requested IPv4 address for " + host);
                }

                // Tạo địa chỉ từ byte, không kích hoạt DNS.
                return Stream.of(InetAddress.getByAddress(HOST, IP));
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr, "addr");
                if (addr.length != 4 && addr.length != 16) {
                    throw new IllegalArgumentException(
                            "IP address must contain 4 or 16 bytes");
                }

                if (Arrays.equals(addr, IP)) {
                    return HOST;
                }

                return builtIn.lookupByAddress(addr);
            }
        };
    }
}
~~~

**Giải thích ba nhánh:**

- `demo.fail=constructor`: JDK không thể tạo `ProbeProvider`; việc khởi tạo resolver không hoàn tất.
- `demo.fail=get`: provider đã được tạo nhưng không thể trả resolver; việc cài resolver không hoàn tất.
- `demo.fail=none`: provider trả về resolver thật, xử lý tên `probe.lab.invalid` và ủy quyền những tên khác qua `Configuration.builtinResolver()`.

Các lệnh `System.getProperty` và phép so sánh chuỗi chỉ nhằm chọn lỗi trong bài test. Trong sản phẩm, constructor và `get` nên nhẹ và không cố ý ném lỗi; không chạy lookup mạng hoặc chờ thread trong quá trình khởi tạo provider.

## 6. Chương trình kiểm chứng lỗi đã tới caller

Tệp `src/ProbeMain.java`:

~~~java
import java.net.InetAddress;

public final class ProbeMain {
    private static final String HOST = "probe.lab.invalid";
    private static final String EXPECTED_IP = "192.0.2.45";

    private static String expectedMarker(String mode) {
        return switch (mode) {
            case "constructor" -> "DEMO_CONSTRUCTOR_FAILED";
            case "get" -> "DEMO_GET_FAILED";
            default -> null;
        };
    }

    private static boolean printAndFindMarker(
            Throwable failure, String marker) {
        boolean found = false;
        int depth = 0;

        // Chỉ test harness bắt Throwable để quan sát cả Error và Exception.
        // Production code không nên bắt Throwable tùy tiện.
        for (Throwable current = failure;
                current != null && depth < 16;
                current = current.getCause(), depth++) {
            System.out.println(
                    "CAUSE[" + depth + "] "
                    + current.getClass().getName()
                    + ": " + current.getMessage());

            if (current.getMessage() != null
                    && current.getMessage().contains(marker)) {
                found = true;
            }
        }
        return found;
    }

    public static void main(String[] args) {
        String mode = System.getProperty("demo.fail", "none");
        String marker = expectedMarker(mode);

        if (!mode.equals("none")
                && !mode.equals("constructor")
                && !mode.equals("get")) {
            throw new IllegalArgumentException(
                    "Unsupported demo.fail value: " + mode);
        }

        try {
            // Đây là lời gọi có thể kích hoạt lần cài resolver toàn JVM.
            InetAddress resolved = InetAddress.getByName(HOST);

            if (marker != null) {
                throw new AssertionError(
                        "Expected provider initialization to fail: " + mode);
            }

            if (!EXPECTED_IP.equals(resolved.getHostAddress())) {
                throw new AssertionError(
                        "Unexpected resolution: " + resolved);
            }

            System.out.println("PASS: lookup succeeded -> "
                    + resolved.getHostAddress());
        } catch (Throwable failure) {
            if (marker == null) {
                throw new AssertionError(
                        "Lookup unexpectedly failed", failure);
            }

            boolean found = printAndFindMarker(failure, marker);
            if (!found) {
                throw new AssertionError(
                        "Failure did not contain expected marker: "
                        + marker, failure);
            }

            System.out.println(
                    "PASS: caller observed provider failure (" + mode + ")");
        }
    }
}
~~~

Vì sao harness **không** chỉ bắt `UnknownHostException`?

- Lỗi ở constructor hoặc `get` là lỗi **khởi tạo resolver**, không nhất thiết là lỗi phân giải hostname.
- Provider có thể ném unchecked exception; `ServiceLoader` có thể bọc lỗi constructor trong `ServiceConfigurationError`.
- Trong mã kiểm chứng, `catch (Throwable)` giúp in được cả `Error` và `Exception`. Đây là lựa chọn giới hạn cho **test harness**, không phải cách xử lý lỗi khuyến nghị trong ứng dụng.

Harness coi lần chạy là **PASS** khi:
- Chế độ `none` trả đúng `192.0.2.45`, hoặc
- Chế độ lỗi có marker tương ứng trong chuỗi throwable/cause mà **caller** nhận được.

Nếu không tìm thấy marker, harness ném `AssertionError`, giúp tránh báo thành công giả khi provider không được nạp, có provider khác được chọn, hoặc lỗi xảy ra vì nguyên nhân khác.

## 7. Biên dịch, đóng gói và chạy ba JVM riêng

Các lệnh sau dành cho **Windows PowerShell**, chạy tại thư mục `resolver-init-verification`.

### 7.1. Biên dịch ứng dụng và provider

~~~powershell
New-Item -ItemType Directory -Force -Path build/classes, build/app |
    Out-Null

javac -d build/classes src/verify/resolver/ProbeProvider.java
javac -d build/app src/ProbeMain.java
~~~

### 7.2. Đóng gói provider kèm service descriptor

~~~powershell
jar --create --file build/probe-provider.jar -C build/classes . -C resources .
jar --list --file build/probe-provider.jar
~~~

Tối thiểu cần thấy:

~~~text
verify/resolver/ProbeProvider.class
META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Nếu trong JAR chỉ có `ProbeProvider.class` nhưng thiếu resource `META-INF/services`, `ServiceLoader` sẽ không phát hiện provider. Nếu tên lớp bên trong resource không đúng package, bước khởi tạo sẽ không đạt điều kiện test.

### 7.3. Chạy thử thành công (đối chứng)

~~~powershell
java -Ddemo.fail=none -cp "build/app;build/probe-provider.jar" ProbeMain
~~~

Kỳ vọng:

~~~text
PASS: lookup succeeded -> 192.0.2.45
~~~

Đây là bước xác nhận cơ chế đăng ký hoạt động. Nếu không có đối chứng thành công, không thể kết luận một lần lookup thất bại là do lỗi cố ý trong constructor hay `get`.

### 7.4. Gây lỗi constructor

~~~powershell
java -Ddemo.fail=constructor -cp "build/app;build/probe-provider.jar" ProbeMain
~~~

Kết quả có dạng:

~~~text
CAUSE[0] java.util.ServiceConfigurationError: ...
CAUSE[1] java.lang.IllegalStateException: DEMO_CONSTRUCTOR_FAILED
PASS: caller observed provider failure (constructor)
~~~

**Lưu ý:** Hai dòng `CAUSE` ở trên chỉ minh họa trường hợp lỗi constructor được bọc bởi `ServiceConfigurationError`. Chuỗi ngoại lệ/stack trace thực tế có thể khác; điều kiện kiểm chứng ổn định hơn là **caller thấy lỗi** và có marker `DEMO_CONSTRUCTOR_FAILED` trong chuỗi nguyên nhân.

### 7.5. Gây lỗi get(Configuration)

~~~powershell
java -Ddemo.fail=get -cp "build/app;build/probe-provider.jar" ProbeMain
~~~

Kết quả có dạng:

~~~text
CAUSE[0] java.lang.IllegalStateException: DEMO_GET_FAILED
PASS: caller observed provider failure (get)
~~~

Ở trường hợp này constructor thành công, nhưng `get(Configuration)` ném lỗi trước khi trả `InetAddressResolver`. Lần lookup kích hoạt cài resolver phải nhận được lỗi, không được im lặng chuyển sang resolver tích hợp.

### 7.6. Lệnh tương đương trên Linux/macOS

Dấu phân cách classpath trên Linux/macOS là `:` thay vì `;`:

~~~shell
java -Ddemo.fail=none -cp "build/app:build/probe-provider.jar" ProbeMain
java -Ddemo.fail=constructor -cp "build/app:build/probe-provider.jar" ProbeMain
java -Ddemo.fail=get -cp "build/app:build/probe-provider.jar" ProbeMain
~~~

Mỗi lệnh `java` tạo một JVM mới. **Không** thay property giữa các lookup trong cùng tiến trình với kỳ vọng JDK nạp lại provider.

## 8. Diễn giải kết quả đúng: quan sát propagation, không đoán cơ chế fallback

Các điều kiện cần đồng thời được xác minh:

| Ca | Dấu hiệu xác minh | Điều có thể kết luận |
|---|---|---|
| `demo.fail=none` | Địa chỉ `192.0.2.45` được trả về. | Provider tùy biến đã được dùng trong JVM đối chứng. |
| `demo.fail=constructor` | Caller nhận throwable/cause chứa `DEMO_CONSTRUCTOR_FAILED`. | Lỗi constructor không bị nuốt; cài resolver thất bại ở lần thử đó. |
| `demo.fail=get` | Caller nhận throwable/cause chứa `DEMO_GET_FAILED`. | Lỗi `get` không bị nuốt; cài resolver thất bại ở lần thử đó. |
| Thiếu service descriptor | Tên `probe.lab.invalid` không được ánh xạ bởi provider demo. | Provider có thể chưa được phát hiện; **không** dùng kết quả này làm test propagation. |
| Có provider khác trên classpath | Marker của provider demo có thể không xuất hiện. | Cần kiểm soát classpath, không suy luận provider demo đã được chọn. |

**Không suy ra quá mức:** Hợp đồng xác nhận resolver toàn JVM chưa được set khi bước tạo custom resolver thất bại và lỗi được đưa tới caller. Nó **không hứa** về số lần retry, thứ tự lỗi khi nhiều luồng cùng khởi tạo, hay lớp wrapper chính xác của `ServiceLoader` trên mọi JDK. Không viết test phụ thuộc vào hành vi khởi tạo lại trong **cùng JVM**.

Sự khác biệt giữa hai tình huống:

~~~text
Không có provider        -> chọn built-in resolver
Provider lỗi khi tạo     -> không cài resolver; caller nhận lỗi
~~~

Vì thế một provider muốn “fallback về mặc định” phải **trả resolver thành công**, rồi ủy quyền bên trong resolver:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    return configuration.builtinResolver();
}
~~~

Đoạn này là cấu hình hợp lệ nếu chủ đích là dùng built-in; nhưng nó không chứng minh propagation vì `get` không ném lỗi.

## 9. Các vấn đề thường làm kiểm chứng sai

| Lỗi trong thử nghiệm | Vì sao làm sai kết luận | Cách khắc phục |
|---|---|---|
| Không đóng gói `META-INF/services` | JDK không tìm thấy provider thử nghiệm. | Kiểm tra `jar --list` và resource chính xác. |
| Ghi tên lớp ngắn thay vì fully qualified name | `ServiceLoader` không tạo được provider đúng. | Ghi `verify.resolver.ProbeProvider`. |
| Chạy nhiều chế độ trong cùng JVM | Resolver có thể đã được cài từ lần đầu. | Mỗi chế độ là một lệnh `java` riêng. |
| Dùng IP literal thay vì hostname | JDK có thể xử lý literal mà không đi qua resolver tùy biến. | Dùng `probe.lab.invalid`. |
| Dùng `localhost` làm hostname duy nhất | Một số đường phân giải có xử lý đặc biệt/định tuyến local. | Dùng hostname giả do provider tự nhận diện. |
| Chỉ bắt `UnknownHostException` | Bỏ lọt lỗi ở giai đoạn khởi tạo provider. | Harness quan sát `Throwable` và nguyên nhân. |
| Chỉ khớp lớp throwable ngoài cùng | Constructor có thể bị `ServiceLoader` bọc. | Tìm marker trong chuỗi `getCause()`. |
| Có nhiều provider | Provider đầu tiên theo thứ tự discovery có thể không phải test provider. | Kiểm soát classpath; ưu tiên chỉ một provider. |
| Ném lỗi trong `lookupByName` thay vì constructor/get | Đang kiểm chứng thất bại lookup, không phải thất bại khởi tạo. | Cố ý ném lỗi ngay trong constructor hoặc `get`. |
| Cho rằng lỗi provider sẽ tự chuyển built-in | Trái hợp đồng Javadoc. | Phân biệt provider không có và provider tạo lỗi. |
| Chạy test trước khi VM khởi động đầy đủ | JDK có thể dùng resolver tích hợp cho lookup trong giai đoạn bootstrap. | Kích hoạt lookup từ `main` của JVM mới. |

## 10. Tư duy thiết kế thực tế: tránh tạo lỗi từ đầu

Bài kiểm chứng cố ý ném lỗi; code sản phẩm cần giảm rủi ro:

- **Constructor public không tham số, đơn giản:** tránh DNS, socket, HTTP, database, khởi tạo framework lớn.
- **Static initializer nhẹ:** tránh dependency có thể gọi lại `InetAddress` trong quá trình nạp provider.
- **`get(Configuration)` gọn:** lấy `builtinResolver()` và tạo resolver với dữ liệu bất biến; không gọi `InetAddress.getByName()` để “thử kết nối” ở đây.
- **Ủy quyền đúng tầng:** với hostname ngoài vùng quản lý, gọi `builtIn.lookupByName(host, policy)`; với IP ngoài vùng quản lý, gọi `builtIn.lookupByAddress(addr)`.
- **Không làm giả trạng thái thành công:** tránh bắt tất cả exception rồi trả `null`, `Stream.empty()` hoặc địa chỉ tùy ý.
- **Logging an toàn:** có thể log tên provider và giai đoạn xảy ra lỗi, nhưng không đưa thông tin nhạy cảm vào marker hoặc stack trace.
- **Khởi tạo tài nguyên nặng có kiểm soát:** thực hiện ở giai đoạn phù hợp với timeout và đồng bộ rõ ràng, thay vì khóa đường cài resolver.

Javadoc khuyến nghị việc khởi tạo provider càng đơn giản càng tốt để hạn chế deadlock và chu trình nạp lớp. Đây vẫn là lời khuyên hiện hành cho các JDK sau Java 18.

## 11. Checklist kiểm chứng và câu hỏi tự đánh giá

### Checklist

- [ ] JDK dùng cho test hỗ trợ JEP 418 (Java 18+).
- [ ] Provider là lớp `public`, không abstract, có constructor `public` không tham số.
- [ ] File service tồn tại tại `META-INF/services/java.net.spi.InetAddressResolverProvider`.
- [ ] Nội dung file service là `verify.resolver.ProbeProvider`, khớp package và tên lớp.
- [ ] Provider JAR nằm trên application classpath.
- [ ] Test `none` giải ra `192.0.2.45`.
- [ ] Test `constructor` làm caller nhận failure marker từ constructor.
- [ ] Test `get` làm caller nhận failure marker từ `get(Configuration)`.
- [ ] Test harness đọc chuỗi nguyên nhân thay vì chỉ đòi một lớp exception cố định.
- [ ] Ba chế độ được chạy trong **ba JVM mới**.
- [ ] Không coi `UnknownHostException` từ hostname không tồn tại là bằng chứng constructor/get lỗi.
- [ ] Không coi lỗi tạo provider là tín hiệu để tự động dùng built-in resolver.

### Câu hỏi tự đánh giá

1. Phân biệt tình huống `ServiceLoader` **không tìm thấy provider** với tình huống đã tìm thấy provider nhưng constructor ném lỗi.
2. Vì sao `InetAddress.getByName("probe.lab.invalid")` phù hợp hơn IP literal để kích hoạt kiểm chứng?
3. Lỗi constructor có thể xuất hiện dưới dạng `ServiceConfigurationError` vì sao?
4. Vì sao nên tìm marker trong chuỗi `getCause()` thay vì chỉ bắt `IllegalStateException`?
5. Nếu `get(Configuration)` ném exception, JDK có cam kết tự cài resolver tích hợp không?
6. Nếu chạy `demo.fail=none` rồi đổi property thành `get` trong cùng JVM, tại sao kết quả không đáng tin để kiểm chứng khởi tạo?
7. Làm thế nào thiết kế provider “chỉ xử lý hostname nội bộ, những tên khác theo mặc định” mà không ném exception trong `get`?
8. Vì sao một `UnknownHostException` phát sinh từ `lookupByName` không chứng minh lỗi khởi tạo provider?

**Kết luận:** Với Resolver SPI từ Java 18, lỗi trong constructor của provider hoặc trong `get(Configuration)` là **lỗi khởi tạo resolver** và có thể quan sát từ caller đã kích hoạt `InetAddress` lookup. Nếu provider không tồn tại, JDK dùng built-in; nếu provider đã được tìm thấy nhưng tạo resolver thất bại, **không có fallback ngầm được bảo đảm**. Dùng một provider có chế độ thất bại có chủ đích, chạy các chế độ trên JVM mới và kiểm tra throwable/cause để chứng minh đúng hợp đồng.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 25: `InetAddressResolverProvider` – vòng đời, constructor, `get(Configuration)` và truyền lỗi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 26: `InetAddressResolverProvider` – hợp đồng vẫn duy trì trên JDK hiện đại](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 25: `InetAddressResolver` – forward/reverse lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 25: `ServiceLoader` – service provider configuration và lỗi nạp](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html).
