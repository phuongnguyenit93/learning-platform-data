# JEP 418 và ba thành phần `InetAddressResolver`, `InetAddressResolverProvider`, `Configuration`

> **Phạm vi:** Java 18 giới thiệu **Internet-Address Resolution SPI** (JEP 418). Đây là API chuẩn vẫn có trong JDK hiện đại để thay đổi cách `java.net.InetAddress` phân giải tên máy và địa chỉ IP. Bài tập trung vào `InetAddressResolver`, `InetAddressResolverProvider`, `InetAddressResolverProvider.Configuration` và hợp đồng cần giữ khi triển khai.

## 1. Vấn đề JEP 418 giải quyết

Khi ứng dụng gọi `InetAddress.getByName("example.com")` hoặc `InetAddress.getAllByName("example.com")`, JDK phải tìm địa chỉ IP cho tên máy (**forward lookup**). Ngược lại, khi tìm tên máy từ địa chỉ IP, đó là **reverse lookup**. Resolver mặc định dựa trên cấu hình hệ điều hành và các dịch vụ đặt tên mà môi trường cung cấp; ứng dụng thông thường không cần biết chi tiết này.

Một số hệ thống lại cần chính sách riêng, chẳng hạn:

- Đọc ánh xạ tên nội bộ từ kho cấu hình của ứng dụng.
- Dùng resolver của môi trường kiểm thử để không phụ thuộc DNS công cộng.
- Chuyển tiếp phần lớn truy vấn cho resolver có sẵn, nhưng xử lý riêng một miền nội bộ.
- Cung cấp cách phân giải tên chuyên biệt mà vẫn để các đoạn mã hiện có tiếp tục dùng `InetAddress`.

**JEP 418** đưa ra điểm mở rộng công khai trong `java.net.spi`. Thay vì phụ thuộc vào lớp nội bộ của JDK, ứng dụng đăng ký một **provider** tạo ra **resolver** để `InetAddress` sử dụng.

Điểm then chốt: SPI này định nghĩa cách phân giải **tên ↔ địa chỉ IP trong JVM**, không tạo ra máy chủ DNS và cũng không thay thế các phần khác như xác thực TLS, định tuyến hay kết nối TCP.

## 2. Ba thành phần và trách nhiệm

| Thành phần | Loại và vị trí | Trách nhiệm |
|---|---|---|
| `InetAddressResolver` | Interface `java.net.spi.InetAddressResolver` | Thực hiện forward lookup qua `lookupByName` và reverse lookup qua `lookupByAddress`. |
| `InetAddressResolverProvider` | Abstract class `java.net.spi.InetAddressResolverProvider` | Là service provider/factory. JDK phát hiện provider bằng `ServiceLoader` rồi gọi `get(Configuration)` để nhận resolver. |
| `InetAddressResolverProvider.Configuration` | Interface lồng bên trong provider | Đưa cấu hình nền tảng vào `get`; cho phép lấy resolver mặc định bằng `builtinResolver()` và tên máy cục bộ bằng `lookupLocalHostName()`. |

Mối liên hệ:

~~~text
Ứng dụng → InetAddress.getAllByName("service.demo.invalid")
                      │
                      ▼
             Resolver toàn JVM
                      ▲
                      │ tạo ra một lần khi khởi tạo resolver
    ServiceLoader → InetAddressResolverProvider.get(Configuration)
                      │
                      ├── Configuration.builtinResolver()
                      └── Configuration.lookupLocalHostName()
~~~

### `InetAddressResolver`: thực hiện tra cứu

Hợp đồng có đúng hai phương thức chính:

~~~java
Stream<InetAddress> lookupByName(
        String host,
        InetAddressResolver.LookupPolicy lookupPolicy)
        throws UnknownHostException;

String lookupByAddress(byte[] addr)
        throws UnknownHostException;
~~~

- **`lookupByName`:** nhận **hostname** và chính sách tra cứu; trả `Stream<InetAddress>` chứa các địa chỉ phù hợp. Nếu không tìm thấy IP, ném `UnknownHostException`. Không nên giả định tham số `host` luôn là tên miền hợp lệ; API không tự xác thực tên. Địa chỉ IP viết dạng chuỗi thường được `InetAddress` xử lý riêng trước khi cần tra cứu tên.
- **`lookupByAddress`:** nhận địa chỉ IP dạng byte theo **network byte order** (4 byte với IPv4, 16 byte với IPv6), trả tên máy tương ứng; ném `UnknownHostException` nếu không có ánh xạ. Độ dài không hợp lệ cần được xử lý theo hợp đồng `IllegalArgumentException`, còn đối số `null` dẫn đến `NullPointerException`.
- **Tách biệt hai chiều:** hỗ trợ forward lookup không đồng nghĩa reverse lookup tự có. Nhà triển khai phải quyết định cách xử lý cả hai phương thức.
- **Giữ hợp đồng lỗi:** không trả về tên máy giả khi không phân giải được; dùng `UnknownHostException` đúng trường hợp. Bỏ qua các tình huống thiếu dữ liệu dễ tạo hành vi khác với resolver mặc định.

### `LookupPolicy`: bộ lọc loại IP và thứ tự

`InetAddressResolver.LookupPolicy.characteristics()` trả về bitmask diễn tả yêu cầu:

| Bitmask | Ý nghĩa |
|---|---|
| `LookupPolicy.IPV4` | Cần tra cứu và trả địa chỉ IPv4. |
| `LookupPolicy.IPV6` | Cần tra cứu và trả địa chỉ IPv6. |
| `LookupPolicy.IPV4_FIRST` | Nếu có cả hai họ IP, ưu tiên IPv4 trong thứ tự kết quả. |
| `LookupPolicy.IPV6_FIRST` | Nếu có cả hai họ IP, ưu tiên IPv6 trong thứ tự kết quả. |

Ví dụ tạo một policy hợp lệ trong mã sử dụng API:

~~~java
import java.net.spi.InetAddressResolver.LookupPolicy;

LookupPolicy policy = LookupPolicy.of(
        LookupPolicy.IPV4 | LookupPolicy.IPV6 | LookupPolicy.IPV6_FIRST);
~~~

`LookupPolicy.of(...)` yêu cầu ít nhất một trong hai bit `IPV4` hoặc `IPV6`, và không cho phép bật đồng thời `IPV4_FIRST` và `IPV6_FIRST`. Nếu không chọn thứ tự ưu tiên, kết quả theo thứ tự hệ thống. Khi hiện thực resolver, phải lọc họ IP và sắp xếp theo policy khi có nhiều địa chỉ; không nên trả IPv4 khi request chỉ cho phép IPv6.

### `InetAddressResolverProvider`: chọn và tạo resolver

Provider là lớp cụ thể kế thừa `InetAddressResolverProvider`, có constructor **không tham số** và triển khai:

~~~java
public abstract InetAddressResolver get(Configuration configuration);
public abstract String name();
~~~

- `get(Configuration)` tạo/trả resolver được dùng bởi `InetAddress`. Lỗi hoặc exception trong quá trình tạo resolver **được chuyển cho lời gọi kích hoạt tra cứu**, không tự động được coi là yêu cầu dùng resolver mặc định.
- `name()` cung cấp tên nhận diện provider (API cũng cho phép trả `null`). Tên dễ hiểu giúp chẩn đoán.
- Khi JVM đã khởi tạo đầy đủ và lần tra cứu phù hợp đầu tiên cần resolver, JDK dùng `ServiceLoader` để tìm provider bằng **system class loader**. **Provider đầu tiên tìm thấy** được chọn; thứ tự tìm thấy nhiều provider là chi tiết triển khai, không nên dựa vào đó.
- Nếu không tìm thấy provider, JDK dùng resolver tích hợp. Việc lựa chọn ở phạm vi **toàn JVM**, không phải một resolver riêng cho từng lệnh tra cứu.
- Các lookup trước khi JVM hoàn tất khởi động dùng resolver tích hợp. Hạn chế thực hiện tra cứu mạng hoặc khởi tạo phức tạp ngay trong constructor/provider `get` vì có thể dẫn đến chu trình khởi tạo và deadlock.

### `Configuration`: điểm tựa cho việc ủy quyền

`Configuration` được JDK truyền trực tiếp vào `get(Configuration)`, không phải lớp cấu hình do ứng dụng tự tạo.

- `configuration.builtinResolver()` trả `InetAddressResolver` tích hợp của JDK. Đây là cách **đúng** để xử lý các tên mà custom resolver không quản lý.
- `configuration.lookupLocalHostName()` đọc tên localhost từ cấu hình hệ thống; hữu ích khi resolver cần nhận biết tên máy cục bộ. Giá trị này là **tên**, không phải địa chỉ IP.
- Không gọi ngược `InetAddress.getByName(...)` từ chính `lookupByName(...)` để “fallback”: thao tác ấy có thể quay lại custom resolver và gây đệ quy vô hạn. Hãy gọi phương thức trên resolver lấy từ `builtinResolver()`.

## 3. Ví dụ chạy được: ánh xạ một hostname và ủy quyền phần còn lại

Ví dụ sau gán `service.demo.invalid` cho `203.0.113.9`, là địa chỉ trong dải dành cho tài liệu; không yêu cầu liên hệ dịch vụ thật. Mọi hostname khác được chuyển cho resolver mặc định. Với hostname được quản lý, ví dụ chỉ hỗ trợ IPv4 và trả lỗi rõ ràng nếu policy yêu cầu riêng IPv6.

Cấu trúc mã minh họa (có thể tạo một project nhỏ độc lập):

~~~text
src/
├── demo.resolver/
│   ├── module-info.java
│   └── demo/resolver/MappingResolverProvider.java
└── Demo.java
~~~

**`src/demo.resolver/module-info.java`**

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
            with demo.resolver.MappingResolverProvider;
}
~~~

Từ khóa `provides ... with ...` đăng ký implementation qua **JPMS** để `ServiceLoader` có thể phát hiện. Gói chứa provider không cần `exports` chỉ để sử dụng cơ chế provider.

**`src/demo.resolver/demo/resolver/MappingResolverProvider.java`**

~~~java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.stream.Stream;

public final class MappingResolverProvider extends InetAddressResolverProvider {
    private static final String DEMO_HOST = "service.demo.invalid";
    private static final byte[] DEMO_IP = {(byte) 203, 0, 113, 9};

    // ServiceLoader cần constructor không tham số.
    public MappingResolverProvider() {}

    @Override
    public String name() {
        return "demo-mapping-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                if (!DEMO_HOST.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }

                // Host demo chỉ có bản ghi IPv4.
                if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            host + " does not have an IPv6 address");
                }

                // getByAddress(host, bytes) chỉ tạo đối tượng; không tra DNS.
                return Stream.of(InetAddress.getByAddress(host, DEMO_IP));
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                if (Arrays.equals(addr, DEMO_IP)) {
                    return DEMO_HOST;
                }
                return builtin.lookupByAddress(addr);
            }
        };
    }
}
~~~

Trong ví dụ, `DEMO_IP` là IPv4; việc chỉ trả một địa chỉ đồng nghĩa không cần sắp xếp nhiều kết quả. Với resolver thực tế chứa cả IPv4 và IPv6, hãy triển khai lọc/sắp xếp theo toàn bộ `LookupPolicy`. Đối số `null` hay địa chỉ byte không hợp lệ được chuyển cho resolver tích hợp ở các nhánh không khớp, giữ cách xử lý theo hợp đồng của API.

**`src/Demo.java`**

~~~java
import java.net.InetAddress;

public class Demo {
    public static void main(String[] args) throws Exception {
        InetAddress service = InetAddress.getByName("service.demo.invalid");
        System.out.println("Forward: " + service.getHostAddress());

        byte[] rawIp = {(byte) 203, 0, 113, 9};
        InetAddress ip = InetAddress.getByAddress(rawIp);
        System.out.println("Reverse: " + ip.getCanonicalHostName());
    }
}
~~~

Biên dịch và chạy bằng **JDK 18 trở lên** (ví dụ dưới dùng PowerShell):

~~~powershell
New-Item -ItemType Directory -Force -Path mods/demo.resolver, out | Out-Null
javac -d mods/demo.resolver src/demo.resolver/module-info.java src/demo.resolver/demo/resolver/MappingResolverProvider.java
javac -d out src/Demo.java
java --module-path mods --add-modules demo.resolver -cp out Demo
~~~

Kết quả kỳ vọng khi provider được nạp:

~~~text
Forward: 203.0.113.9
Reverse: service.demo.invalid
~~~

`--add-modules demo.resolver` bảo đảm module chứa provider nằm trong đồ thị module khi chạy ứng dụng classpath. Nếu bỏ cấu hình đăng ký hoặc không resolve module provider, lời gọi tới hostname `.invalid` sẽ không tìm được ánh xạ ví dụ. `InetAddress.getByAddress(byte[])` tự tạo đối tượng IP; thao tác `getCanonicalHostName()` sau đó mới minh họa phân giải tên ngược.

Với ứng dụng dùng **classpath** hoàn toàn, có thể đăng ký provider bằng tập tin `META-INF/services/java.net.spi.InetAddressResolverProvider` chứa đúng tên lớp implementation. Đây là hai cơ chế đăng ký service tiêu chuẩn; ví dụ sử dụng JPMS để tránh phải sao chép tài nguyên dịch vụ thủ công.

## 4. Hành vi cần hiểu trước khi đưa vào hệ thống thật

**Phạm vi kích hoạt.** Provider được chọn khi cơ chế tra cứu tên của `InetAddress` khởi tạo resolver toàn JVM. Chạy code tải provider *sau* khi resolver đã được chọn không phải là cách đổi resolver đang hoạt động. Hãy đóng gói provider và đăng ký trước khi khởi động ứng dụng, đồng thời kiểm tra xem có provider khác trên đường tải class/module hay không.

**Không bảo đảm thứ tự giữa các provider.** Vì chỉ provider đầu tiên được chọn và thứ tự do triển khai quyết định, không đăng ký nhiều provider với giả định “provider A chạy trước, B là fallback”. Nếu muốn fallback theo tên miền, xây một resolver và gọi `configuration.builtinResolver()` cho phần còn lại, như ví dụ.

**Cache.** `InetAddress` lưu cache cho cả thành công và thất bại. Do đó sửa ánh xạ bên trong custom resolver không có nghĩa mọi lần gọi `getByName` lập tức thấy IP mới. Các security properties `networkaddress.cache.ttl`, `networkaddress.cache.stale.ttl` và `networkaddress.cache.negative.ttl` điều chỉnh chính sách cache. Đây là **security properties**, không phải property có thể tùy ý đặt bằng `-Dnetworkaddress.cache.ttl=...` hay `System.setProperty(...)`.

**Độ ổn định và bảo mật.** Resolver tùy biến ảnh hưởng mọi thành phần trong JVM đi qua `InetAddress`. Khi dùng nguồn dữ liệu bên ngoài, cần giới hạn thời gian chờ, định nghĩa lỗi rõ ràng, tránh vòng lặp fallback và không ghi thông tin nhạy cảm vào log. Ánh xạ tên → IP do resolver cung cấp không tự chứng minh danh tính của máy chủ; giao thức bảo mật vẫn phải xác minh danh tính máy chủ bằng cơ chế phù hợp.

**Kiểm thử.** Nên kiểm tra forward/reverse lookup; hostname được quản lý/không quản lý; IPv4/IPv6 và thứ tự; tên không tồn tại; đầu vào không hợp lệ; khi không có provider; và khi có nhiều provider trên runtime. Tạo JVM mới cho những lần kiểm tra thay đổi provider hoặc trạng thái cache, vì chúng có vòng đời ở cấp tiến trình.

## 5. Tự kiểm tra hiểu biết

1. Tại sao không nên gọi `InetAddress.getAllByName(host)` để làm fallback ngay bên trong `lookupByName`? Phương án thay thế là gì?
2. Khi `LookupPolicy` chỉ chứa `IPV6`, resolver đang chỉ có bản ghi IPv4 cho một hostname phải làm gì?
3. Nếu không có provider đăng ký, `InetAddress` sẽ dùng resolver nào? Nếu `get(Configuration)` ném exception thì chuyện gì xảy ra?
4. Tại sao thêm module provider vào đường dẫn module nhưng không resolve module ấy có thể khiến ví dụ không có tác dụng?
5. Cache có thể khiến thay đổi mapping bị quan sát chậm hơn như thế nào?

**Điều cần ghi nhớ:** `InetAddressResolver` thực hiện lookup, `InetAddressResolverProvider` tạo resolver và được tìm qua `ServiceLoader`, còn `Configuration` cung cấp điểm ủy quyền an toàn về resolver tích hợp. Đó là hợp đồng API vẫn hữu ích trên JDK mới cho nhu cầu kiểm thử và kiểm soát phân giải tên.

## Tài liệu tham khảo

- [OpenJDK JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [JDK 25: `InetAddressResolver`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [JDK 25: `InetAddressResolverProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [JDK 25: `InetAddressResolverProvider.Configuration`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [JDK 25: `InetAddressResolver.LookupPolicy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [JDK 25: `InetAddress` và chính sách cache](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html).
