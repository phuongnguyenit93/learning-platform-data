# Triển khai provider với constructor không tham số, get(Configuration) và name()

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). Bài hướng dẫn triển khai `java.net.spi.InetAddressResolverProvider` trên JDK hiện đại, tập trung vào constructor không tham số, phương thức `get(Configuration)`, `name()` và cách đăng ký provider để JDK phát hiện. Các API này vẫn được hỗ trợ; ví dụ dùng JPMS và `ServiceLoader`, không phụ thuộc lớp nội bộ hoặc cơ chế legacy.

## 1. Provider là điểm vào để JDK nhận resolver tùy biến

JEP 418 bổ sung Internet-Address Resolution SPI để thay đổi cách `InetAddress` phân giải hostname và địa chỉ IP. SPI có hai vai trò:

- **Provider** (`InetAddressResolverProvider`): được JDK phát hiện như một service provider và tạo resolver.
- **Resolver** (`InetAddressResolver`): thực hiện forward lookup và reverse lookup.

Luồng khái quát:

~~~text
Ứng dụng gọi InetAddress.getByName(host)
                 │
                 ▼
       Cơ chế phân giải của InetAddress
                 │
                 ▼
       Phát hiện provider qua ServiceLoader
                 │
                 ▼
       Tạo provider bằng constructor không tham số
                 │
                 ▼
       provider.get(Configuration)
                 │
                 ▼
       InetAddressResolver được trả về
                 │
                 ▼
       lookupByName(...) / lookupByAddress(...)
~~~

Provider không trực tiếp xử lý từng truy vấn bằng phương thức `get(...)`. `get(Configuration)` là điểm tạo resolver; các lookup về sau được gọi trên resolver mà provider trả về.

Nếu không có provider phù hợp, JDK sử dụng resolver tích hợp. Khi có provider tùy biến, việc chọn provider thuộc cơ chế khởi tạo resolver của `InetAddress`; ứng dụng thông thường tiếp tục gọi các API quen thuộc như `InetAddress.getByName(...)`.

## 2. Ba thành phần bắt buộc của provider

Một provider cụ thể kế thừa `InetAddressResolverProvider` và triển khai hai phương thức trừu tượng:

~~~java
public abstract class InetAddressResolverProvider {
    public InetAddressResolverProvider() {
        // Constructor không tham số.
    }

    public abstract InetAddressResolver get(Configuration configuration);

    public abstract String name();
}
~~~

Đoạn trên chỉ minh họa chữ ký API. Trong ứng dụng, ta tạo lớp con:

~~~java
public final class DemoResolverProvider
        extends InetAddressResolverProvider {

    public DemoResolverProvider() {
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        // Tạo và trả về resolver.
    }

    @Override
    public String name() {
        return "demo-resolver";
    }
}
~~~

| Thành phần | Hợp đồng và trách nhiệm |
|---|---|
| Constructor không tham số | Cho phép cơ chế service loading khởi tạo provider. |
| `get(Configuration)` | Nhận cấu hình do JDK cung cấp và trả về một `InetAddressResolver`. |
| `name()` | Trả tên provider để hỗ trợ chẩn đoán. Tên này không phải cơ chế chọn thứ tự hay fallback. |

Provider nên được thiết kế nhẹ, không yêu cầu tham số constructor riêng. Những phụ thuộc cần cho resolver có thể được đọc từ cấu hình ứng dụng phù hợp hoặc được khởi tạo bên trong `get(...)`; không giả định `ServiceLoader` sẽ tự thực hiện dependency injection.

## 3. Constructor không tham số và quy tắc service loading

`ServiceLoader` cần một cách chuẩn để tạo provider mà không biết trước cấu trúc constructor của ứng dụng. Với `InetAddressResolverProvider`, hãy cung cấp constructor public không tham số:

~~~java
public final class DemoResolverProvider
        extends InetAddressResolverProvider {

    public DemoResolverProvider() {
        // Có thể để trống.
    }

    // get(...) và name() được triển khai bên dưới.
}
~~~

Một số lưu ý:

- Constructor phải truy cập được với cơ chế nạp service và không nhận tham số.
- Không đặt logic khởi tạo mạng, truy vấn DNS hoặc chờ dịch vụ bên ngoài trong constructor.
- Không dựa vào thứ tự khởi tạo provider để phối hợp nhiều resolver.
- Không tự gọi `InetAddress.getByName(...)` trong constructor; việc đó có thể kích hoạt cơ chế phân giải trong lúc provider đang được khởi tạo.
- Provider nên giữ trạng thái tối thiểu. Nếu có trạng thái dùng chung, cần bảo đảm an toàn khi resolver được nhiều luồng sử dụng.

Không có constructor không tham số phù hợp là lỗi cấu hình provider; JDK không thể khởi tạo implementation theo hợp đồng service loading.

## 4. get(Configuration): tạo resolver và nhận cấu hình nền tảng

`get(Configuration)` là phương thức chính của provider:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    // Dùng configuration để lấy resolver tích hợp hoặc thông tin local host.
    // Trả về một InetAddressResolver.
}
~~~

Đối số `configuration` là interface lồng trong `InetAddressResolverProvider`, do JDK truyền vào. Hai phương thức hữu ích:

| Phương thức | Công dụng |
|---|---|
| `configuration.builtinResolver()` | Lấy resolver tích hợp của JDK để ủy quyền các hostname/địa chỉ mà provider tùy biến không quản lý. |
| `configuration.lookupLocalHostName()` | Lấy tên máy cục bộ theo cấu hình của hệ thống; hữu ích khi resolver cần nhận diện tên local. |

### Dùng builtinResolver làm fallback

Nếu custom resolver chỉ quản lý một số hostname nội bộ, nên giữ resolver tích hợp và gọi trực tiếp khi hostname không thuộc phạm vi quản lý:

~~~java
InetAddressResolver builtin = configuration.builtinResolver();

// Bên trong resolver:
if (isManagedHost(host)) {
    return lookupManagedHost(host, policy);
}
return builtin.lookupByName(host, policy);
~~~

Đây là cách ủy quyền theo hợp đồng SPI. Không dùng `InetAddress.getAllByName(host)` từ bên trong `lookupByName(...)` để làm fallback. Lời gọi đó có thể quay lại resolver tùy biến đang chạy và gây đệ quy.

Tương tự, trong `lookupByAddress(...)`, hãy gọi `builtin.lookupByAddress(addr)` để ủy quyền reverse lookup. Không gọi `InetAddress.getByAddress(addr).getCanonicalHostName()` làm fallback; phần `getCanonicalHostName()` có thể kích hoạt lại cơ chế reverse lookup toàn JVM.

### Dùng lookupLocalHostName khi cần

`configuration.lookupLocalHostName()` trả về tên máy local theo cấu hình hệ thống. Provider có thể dùng thông tin này nếu chính sách phân giải cần đối xử đặc biệt với hostname cục bộ. Không phải provider nào cũng cần gọi phương thức này; không nên giả định giá trị đó là địa chỉ IP hoặc dùng nó thay cho kiểm tra danh tính bảo mật.

## 5. name(): định danh phục vụ chẩn đoán

Provider phải triển khai:

~~~java
@Override
public String name() {
    return "demo-resolver";
}
~~~

Tên provider có mục đích chẩn đoán, giúp người vận hành nhận biết implementation đang được sử dụng khi phân tích cấu hình và log. Hãy chọn tên:

- Ổn định giữa các lần khởi động.
- Ngắn, mô tả nguồn hoặc mục đích của resolver.
- Không chứa mật khẩu, token, hostname nội bộ nhạy cảm hoặc thông tin bí mật.
- Không phụ thuộc vào thứ tự provider được phát hiện.

Không xem `name()` như một khóa định tuyến. JDK không dùng tên này để quyết định hostname nào do provider xử lý, cũng không dùng nó làm thứ tự ưu tiên giữa nhiều provider. Quy tắc chọn provider thuộc service loading.

## 6. Ví dụ hoàn chỉnh: provider xử lý một hostname và ủy quyền phần còn lại

Ví dụ sau ánh xạ `service.lab.invalid` thành IPv4 `203.0.113.9`, một địa chỉ thuộc dải dành cho tài liệu. Các hostname khác được chuyển cho resolver tích hợp. Ví dụ minh họa cả forward và reverse lookup, đồng thời áp dụng policy IPv4.

Cấu trúc module:

~~~text
src/
├── demo.resolver/
│   ├── module-info.java
│   └── demo/resolver/DemoResolverProvider.java
└── Demo.java
~~~

### 6.1. Đăng ký provider trong module-info.java

Tệp `src/demo.resolver/module-info.java`:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
            with demo.resolver.DemoResolverProvider;
}
~~~

`provides ... with ...` khai báo rằng module `demo.resolver` cung cấp implementation cho service `InetAddressResolverProvider`. Gói chứa provider không cần `exports` chỉ để service loading phát hiện provider.

### 6.2. Cài đặt provider

Tệp `src/demo.resolver/demo/resolver/DemoResolverProvider.java`:

~~~java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Stream;

public final class DemoResolverProvider
        extends InetAddressResolverProvider {

    private static final String DEMO_HOST = "service.lab.invalid";
    private static final byte[] DEMO_IP = {
            (byte) 203, 0, 113, 9
    };

    // ServiceLoader cần constructor public không tham số.
    public DemoResolverProvider() {
    }

    @Override
    public String name() {
        return "demo-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");

        // Giữ resolver tích hợp để xử lý các truy vấn ngoài phạm vi demo.
        InetAddressResolver builtin = configuration.builtinResolver();

        // Trả về implementation thực hiện lookup.
        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                Objects.requireNonNull(host, "host");
                Objects.requireNonNull(policy, "policy");

                if (!DEMO_HOST.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }

                int flags = policy.characteristics();
                if ((flags & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            host + " has no IPv4 address for this policy");
                }

                // Tạo InetAddress từ byte, không thực hiện DNS lookup.
                return Stream.of(
                        InetAddress.getByAddress(host, DEMO_IP));
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr, "addr");

                if (addr.length != 4 && addr.length != 16) {
                    throw new IllegalArgumentException(
                            "IP address must contain 4 or 16 bytes");
                }

                if (Arrays.equals(addr, DEMO_IP)) {
                    return DEMO_HOST;
                }

                return builtin.lookupByAddress(addr);
            }
        };
    }
}
~~~

Những điểm cần chú ý:

- Constructor không tham số cho phép service loader tạo provider.
- `get(Configuration)` lấy resolver tích hợp trước khi tạo resolver tùy biến.
- Hostname thuộc phạm vi demo được xử lý cục bộ.
- Hostname khác được ủy quyền cho `builtinResolver`.
- `lookupByAddress` trả tên demo cho IP được quản lý và ủy quyền các IP khác.
- Mảng sai độ dài và đối số null được xử lý theo hợp đồng API.
- Không gọi ngược `InetAddress.getByName(...)` hoặc `getCanonicalHostName()` để fallback.

### 6.3. Ứng dụng sử dụng InetAddress bình thường

Tệp `src/Demo.java`:

~~~java
import java.net.InetAddress;

public class Demo {
    public static void main(String[] args) throws Exception {
        InetAddress service =
                InetAddress.getByName("service.lab.invalid");

        System.out.println("Forward: " + service.getHostAddress());

        byte[] rawIp = {(byte) 203, 0, 113, 9};
        InetAddress ip = InetAddress.getByAddress(rawIp);

        System.out.println("Reverse: " + ip.getCanonicalHostName());
    }
}
~~~

Ứng dụng không cần tự tạo provider hoặc gọi `ServiceLoader` trực tiếp. Khi service được đăng ký và module provider được resolve lúc chạy, `InetAddress` sẽ dùng resolver do provider cung cấp.

### 6.4. Biên dịch và chạy với JPMS

Ví dụ PowerShell, chạy tại thư mục chứa `src`:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/demo.resolver, out | Out-Null
javac -d mods/demo.resolver src/demo.resolver/module-info.java src/demo.resolver/demo/resolver/DemoResolverProvider.java
javac -d out src/Demo.java
java --module-path mods --add-modules demo.resolver -cp out Demo
~~~

Kết quả mong đợi khi provider được nạp:

~~~text
Forward: 203.0.113.9
Reverse: service.lab.invalid
~~~

`--add-modules demo.resolver` đưa module provider vào đồ thị module khi ứng dụng chạy trên classpath. Nếu module provider không được resolve hoặc thiếu khai báo `provides`, JDK không phát hiện provider theo cấu hình này; hostname `.invalid` của ví dụ sẽ không được ánh xạ.

## 7. Đăng ký provider khi dùng classpath

Nếu ứng dụng không dùng JPMS module descriptor, có thể đăng ký service bằng tệp cấu hình:

~~~text
META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Nội dung tệp là tên lớp đầy đủ (fully qualified class name), mỗi provider một dòng:

~~~text
demo.resolver.DemoResolverProvider
~~~

Đặt tệp này trong classpath runtime, thường được đóng gói thành:

~~~text
META-INF/
└── services/
    └── java.net.spi.InetAddressResolverProvider
~~~

Các điều kiện cần giữ:

- Lớp provider có mặt trên classpath được dùng để phát hiện service.
- Lớp triển khai service có constructor public không tham số theo cơ chế `ServiceLoader` classpath.
- Nội dung service file phải đúng tên package và class, phân biệt chữ hoa/chữ thường.
- Không để provider trùng hoặc provider ngoài ý muốn cùng xuất hiện trên classpath.

Chọn một cách đăng ký phù hợp với cách đóng gói ứng dụng. Với module có tên, dùng `provides ... with ...`; với classpath, dùng `META-INF/services/...`. Tránh vô tình đưa nhiều provider vào runtime nếu chưa xác định rõ quy tắc chọn provider.

## 8. Nhiều provider, vòng đời và tính an toàn luồng

`InetAddress` sử dụng resolver ở phạm vi JVM. Provider được tìm qua cơ chế service loading; nếu có nhiều provider, provider đầu tiên được phát hiện theo thứ tự của `ServiceLoader` được chọn. Không nên dựa vào thứ tự không được đảm bảo để thiết kế fallback giữa các provider.

Nếu cần xử lý nhiều nguồn dữ liệu, hãy tạo **một provider** và kết hợp nhiều nguồn bên trong resolver mà nó trả về. Ví dụ: tra cứu hostname nội bộ trước, sau đó ủy quyền resolver tích hợp. Điều này giúp quy tắc ưu tiên được định nghĩa trong chính implementation.

Resolver có thể được nhiều luồng trong JVM gọi. Vì vậy:

- Ưu tiên resolver không trạng thái hoặc dữ liệu bất biến.
- Nếu dùng cache hoặc cấu trúc dữ liệu có thể thay đổi, phải đồng bộ hoặc dùng cấu trúc an toàn luồng.
- Không giữ `Stream` đã tiêu thụ để tái sử dụng cho truy vấn tiếp theo.
- Không thực hiện công việc mạng chặn lâu trong constructor hoặc trong quá trình tạo provider.
- Giữ fallback trực tiếp qua `builtinResolver()` để tránh đệ quy.

Việc thay đổi classpath/module path sau khi resolver đã được khởi tạo không phải cách thay provider đang hoạt động. Khi kiểm thử thay đổi đăng ký service hoặc cache, dùng tiến trình JVM mới để kết quả không bị ảnh hưởng bởi trạng thái đã khởi tạo trước đó.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách đúng |
|---|---|---|
| Không có constructor public không tham số | `ServiceLoader` không thể khởi tạo provider theo cấu hình classpath. | Cung cấp constructor không tham số. |
| Đặt logic mạng trong constructor | Tăng rủi ro lỗi khởi tạo và vòng lặp phân giải. | Giữ constructor nhẹ; tạo resolver trong `get`. |
| `get(Configuration)` trả `null` | JDK không có resolver hợp lệ để sử dụng. | Trả về một implementation `InetAddressResolver`. |
| Bỏ qua `builtinResolver()` khi cần fallback | Hostname ngoài phạm vi custom có thể không được phân giải. | Ủy quyền trực tiếp resolver tích hợp. |
| Gọi `InetAddress.getByName()` trong resolver để fallback | Có thể gọi ngược chính resolver, gây đệ quy. | Dùng `builtinResolver().lookupByName(...)`. |
| Xem `name()` là thứ tự ưu tiên | Tên provider không điều khiển việc chọn service. | Đăng ký một provider và kết hợp nguồn bên trong. |
| Module có `provides` nhưng không được resolve lúc chạy | Service provider không được phát hiện trong module graph. | Đưa module vào module path và resolve nó. |
| Service file sai tên lớp | Classpath service loader không thể nạp provider. | Dùng fully qualified class name chính xác. |
| Dùng trạng thái mutable không an toàn luồng | Các lookup đồng thời có thể gây race condition. | Dùng dữ liệu bất biến hoặc cơ chế đồng bộ phù hợp. |

## 10. Checklist kiểm chứng provider

| Hạng mục | Điều cần xác minh |
|---|---|
| Constructor | Public, không tham số và không làm công việc mạng. |
| Kế thừa | Lớp provider extends `InetAddressResolverProvider`. |
| `get(Configuration)` | Trả một `InetAddressResolver` hợp lệ. |
| `Configuration` | Lấy `builtinResolver()` để fallback khi cần. |
| `name()` | Trả tên ổn định, hữu ích cho chẩn đoán. |
| JPMS | Có `provides ... with ...` và module được resolve. |
| Classpath | Có service descriptor đúng đường dẫn và tên lớp. |
| Forward lookup | Hostname custom được ánh xạ; hostname ngoài phạm vi được fallback. |
| Reverse lookup | IP custom được ánh xạ; IP ngoài phạm vi được fallback. |
| Lỗi | Null, độ dài IP sai và không tìm thấy được xử lý đúng exception. |
| Runtime | Kiểm thử trong JVM mới khi thay đổi provider. |

## 11. Câu hỏi tự đánh giá

1. Vì sao provider cần constructor không tham số?
2. `get(Configuration)` khác gì `lookupByName(...)`?
3. Khi nào nên dùng `configuration.builtinResolver()`?
4. `lookupLocalHostName()` cung cấp loại thông tin gì?
5. `name()` có điều khiển thứ tự hoặc lựa chọn provider không?
6. Vì sao gọi `InetAddress.getAllByName(...)` từ bên trong resolver để fallback có thể gây đệ quy?
7. Module descriptor và service descriptor trên classpath khác nhau ở đâu?
8. Tại sao nên dùng một provider điều phối nhiều nguồn thay vì phụ thuộc vào thứ tự của nhiều provider?

**Ghi nhớ:** Provider là điểm vào service loading; constructor không tham số cho phép JDK tạo provider; `get(Configuration)` tạo resolver và cung cấp đường fallback an toàn qua `builtinResolver()`; `name()` phục vụ chẩn đoán. Đăng ký provider bằng JPMS `provides ... with ...` hoặc classpath `META-INF/services/java.net.spi.InetAddressResolverProvider`, rồi để ứng dụng tiếp tục sử dụng `InetAddress`.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolverProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 26: `InetAddressResolverProvider.Configuration`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [Java SE 26: `InetAddressResolver`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 26: `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html).
