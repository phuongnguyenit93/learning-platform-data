# Giữ constructor và get(Configuration) đơn giản để tránh vòng lặp class loading hoặc deadlock

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). Bài tập trung vào vòng đời khởi tạo `InetAddressResolverProvider` và resolver toàn JVM trên JDK hiện đại. Javadoc khuyến nghị quá trình khởi tạo provider phải đơn giản để giảm nguy cơ deadlock và chu trình nạp lớp. Nội dung giải thích vì sao constructor, static initializer và `get(Configuration)` cần nhẹ, các lời gọi dễ tái nhập cơ chế phân giải, cách dùng `Configuration` đúng chỗ và một ví dụ provider có fallback an toàn.

## 1. Vì sao khởi tạo provider là thời điểm nhạy cảm?

Resolver SPI cho phép ứng dụng thay đổi cách `InetAddress` phân giải hostname và địa chỉ IP. JDK không tạo một provider mới cho mỗi lần gọi `InetAddress.getByName`. Mỗi tiến trình JVM duy trì một resolver dùng chung ở phạm vi toàn JVM.

Theo Javadoc của `InetAddressResolverProvider`:

1. Sau khi JVM khởi động hoàn tất, lần đầu một phương thức của `InetAddress` cần lookup sẽ kích hoạt việc cài đặt resolver toàn JVM.
2. JDK dùng `ServiceLoader` với system class loader để tìm `InetAddressResolverProvider`.
3. Provider đầu tiên được tìm thấy theo thứ tự do implementation quyết định sẽ được khởi tạo và gọi `get(Configuration)`.
4. Resolver mà `get` trả về được cài đặt làm resolver toàn JVM.
5. Nếu không tìm thấy provider nào, JDK dùng resolver tích hợp.

Sơ đồ vòng đời:

~~~text
JVM hoàn tất khởi động
          │
          ▼
Lần đầu InetAddress cần phân giải tên
          │
          ▼
ServiceLoader tìm InetAddressResolverProvider
          │
          ▼
Nạp lớp + khởi tạo provider
          │
          ▼
Gọi constructor không tham số
          │
          ▼
Gọi provider.get(Configuration)
          │
          ▼
Cài đặt resolver toàn JVM
          │
          ▼
Các lần lookup tiếp theo dùng resolver đó
~~~

Trong giai đoạn này, JDK đang thiết lập chính cơ chế mà các API mạng có thể cần sử dụng. Nếu constructor, static initializer hoặc `get` lại gọi những API cần phân giải tên, khởi tạo class khác có phụ thuộc mạng, hoặc chờ một luồng đang bị giữ bởi lock liên quan, hệ thống có thể gặp chu trình khởi tạo, tái nhập hoặc deadlock.

Javadoc của constructor `InetAddressResolverProvider` nêu rõ khuyến nghị giữ việc khởi tạo service implementation đơn giản nhất có thể để tránh rủi ro deadlock hoặc class loading cycles. Đây là hướng dẫn thiết kế có chủ đích của API, không phải một tối ưu hiệu năng tùy chọn.

## 2. Constructor không tham số: chỉ làm công việc tối thiểu

Provider cụ thể là lớp con của `InetAddressResolverProvider` và có constructor không tham số để service loading khởi tạo:

~~~java
public final class LightweightResolverProvider
        extends InetAddressResolverProvider {

    public LightweightResolverProvider() {
        // Cố ý để trống.
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        // Chỉ tạo resolver đơn giản.
    }

    @Override
    public String name() {
        return "lightweight-resolver";
    }
}
~~~

Constructor nên:

- Không mở socket, kết nối database, gọi HTTP hoặc truy vấn dịch vụ từ xa.
- Không gọi `InetAddress.getByName`, `InetAddress.getAllByName`, `InetAddress.getLocalHost` hay API khác có thể kích hoạt phân giải tên.
- Không tự dùng `ServiceLoader` để tìm provider khác trong cùng SPI.
- Không khởi động thread, chờ `Future`, chờ latch hoặc đợi tài nguyên bên ngoài.
- Không khởi tạo dependency injection container hoặc thư viện lớn có static initializer phức tạp.
- Không giữ lock ứng dụng trong khi gọi mã bên ngoài có thể nạp lớp hoặc phân giải tên.

Hãy để constructor tạo một đối tượng provider nhẹ và trả về ngay. Nếu cần cấu hình, đọc hoặc chuẩn bị nó ở giai đoạn phù hợp sau khi resolver đã được cài đặt, với timeout và xử lý lỗi rõ ràng.

## 3. Static initializer cũng thuộc quá trình khởi tạo

Giữ constructor rỗng vẫn chưa đủ nếu lớp provider có static initializer nặng. JVM phải khởi tạo lớp trước khi tạo instance; các trường static và khối static có thể kích hoạt nạp lớp khác.

Ví dụ nên tránh:

~~~java
public final class RiskyProvider
        extends InetAddressResolverProvider {

    // Không nên: class initialization có thể kích hoạt lookup mạng.
    private static final InetAddress LOCAL =
            InetAddress.getLocalHost();

    // Không nên: tạo client có thể khởi tạo nhiều dependency và mở kết nối.
    private static final DirectoryClient CLIENT =
            DirectoryClient.connectFromEnvironment();

    public RiskyProvider() {
    }

    // ...
}
~~~

Các dạng khởi tạo cần xem xét kỹ:

| Dạng khởi tạo | Rủi ro |
|---|---|
| Gọi API phân giải tên trong static field initializer | Có thể tái nhập quá trình cài resolver. |
| Nạp framework hoặc dependency lớn trong static block | Có thể tạo chu trình nạp lớp gián tiếp. |
| Khởi tạo client mạng ở cấp static | Có thể chờ DNS, socket hoặc dịch vụ bên ngoài. |
| Lấy singleton từ container toàn ứng dụng | Container có thể khởi tạo các bean phụ thuộc mạng hoặc lock. |
| Chờ thread khác hoàn tất static initialization | Có thể tạo lock inversion hoặc deadlock. |

Các hằng số bất biến, chuỗi tên provider và dữ liệu nhỏ không có side effect thường phù hợp. Tuy nhiên, không nên gọi một hàm tiện ích trong static initializer nếu chưa biết hàm đó có khởi tạo thư viện, truy vấn hostname hoặc nạp service khác hay không.

## 4. get(Configuration): tạo resolver, không khởi động cả ứng dụng

Javadoc quy định `get(Configuration)` được `InetAddress` gọi khi cài đặt resolver toàn JVM. Bất kỳ error hoặc exception nào phát sinh từ phương thức này đều được xem là lỗi khởi tạo resolver và được truyền về caller đã kích hoạt lookup.

Do đó, `get` nên làm ít việc:

1. Nhận cấu hình do JDK cung cấp.
2. Lấy resolver tích hợp nếu cần fallback.
3. Đọc thông tin cấu hình trực tiếp cần thiết.
4. Tạo đối tượng resolver với trạng thái ban đầu đơn giản.
5. Trả resolver ngay.

Mẫu gọn:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    InetAddressResolver builtin = configuration.builtinResolver();
    String localName = configuration.lookupLocalHostName();

    return new CustomResolver(builtin, localName);
}
~~~

Chỉ gọi `lookupLocalHostName()` nếu resolver thực sự cần hostname local. Nếu không cần, bỏ dòng đó để quá trình cài đặt càng đơn giản.

Không nên thực hiện trong `get`:

- Gọi `InetAddress.getByName` hoặc `getAllByName` để kiểm tra hostname.
- Gọi `InetAddress.getLocalHost` để tìm tên máy.
- Gọi `getCanonicalHostName` để kiểm tra reverse lookup.
- Gọi `ServiceLoader.load(InetAddressResolverProvider.class)` để tìm provider khác.
- Khởi tạo connection pool, HTTP client hoặc database pool đồng bộ.
- Đợi một tác vụ bất đồng bộ bằng `Future.get()` hoặc chờ lock của thành phần khác.
- Đọc một kho cấu hình từ xa mà không có timeout.

`Configuration` đã cung cấp các điểm truy cập dành cho provider. Dùng `builtinResolver()` để ủy quyền lookup mặc định và `lookupLocalHostName()` khi cần tên máy local; không tìm lại những thông tin này bằng cách gọi vòng qua `InetAddress`.

## 5. Những lời gọi dễ gây tái nhập cơ chế resolver

Không phải mọi phương thức trong `InetAddress` đều thực hiện DNS lookup. Cần phân biệt phương thức có thể kích hoạt phân giải tên với factory chỉ tạo đối tượng từ byte đã biết.

| API | Có thể kích hoạt lookup? | Lưu ý khi gọi trong constructor hoặc get |
|---|---|---|
| `InetAddress.getByName(host)` | Có, nếu host cần phân giải. | Tránh gọi. |
| `InetAddress.getAllByName(host)` | Có. | Tránh gọi. |
| `InetAddress.getLocalHost()` | Có thể cần phân giải hostname local. | Tránh gọi; dùng Configuration nếu chỉ cần tên local. |
| `InetAddress.getByAddress(bytes)` | Không thực hiện DNS lookup; tạo địa chỉ từ raw bytes. | Không phải fallback resolver; vẫn nên tránh khởi tạo không cần thiết trong giai đoạn provider đang được tạo. |
| `InetAddress.getCanonicalHostName()` | Có thể thực hiện reverse lookup nếu chưa có tên canonical. | Tránh gọi trong quá trình cài provider. |
| `Configuration.builtinResolver()` | Không phải lời gọi phân giải hostname; trả resolver tích hợp. | Dùng để giữ tham chiếu fallback. |
| `Configuration.lookupLocalHostName()` | Đọc hostname local từ cấu hình nền tảng. | Dùng khi thực sự cần local name. |

Một lỗi phổ biến là gọi `InetAddress.getAllByName(host)` bên trong `get` với ý định “kiểm tra DNS trước khi tạo resolver”. Nhưng chính lời gọi này có thể là sự kiện kích hoạt quá trình cài resolver mà `get` đang thực hiện. Tùy implementation và trạng thái khởi tạo, nó có thể dẫn tới tái nhập hoặc tương tác lock không an toàn.

Tương tự, gọi `InetAddress.getLocalHost()` trong constructor chỉ để lấy hostname local là không cần thiết: `Configuration.lookupLocalHostName()` đã cung cấp thông tin đó.

## 6. Vì sao có thể xuất hiện class loading cycle hoặc deadlock?

### 6.1. Chu trình nạp lớp

Giả sử provider cần khởi tạo một thư viện cấu hình. Thư viện đó có static initializer gọi API mạng để xác định hostname. API mạng lại cần resolver, nên JDK quay lại provider trong lúc provider hoặc dependency của nó chưa khởi tạo xong.

~~~text
Nạp Provider
    │
    ▼
Provider static initializer
    │
    ▼
Nạp thư viện cấu hình
    │
    ▼
Static initializer của thư viện gọi InetAddress
    │
    ▼
InetAddress cần cài resolver
    │
    └──────────────▶ Provider đang được nạp
                         │
                         └── Chu trình khởi tạo
~~~

JVM có cơ chế đồng bộ class initialization, nhưng điều đó không làm mọi chu trình phụ thuộc trở nên an toàn. Khi các lớp nằm ở nhiều thread hoặc phụ thuộc lẫn nhau qua static initialization, việc chờ có thể tạo trạng thái không thể tiến triển.

### 6.2. Lock inversion và deadlock

Ví dụ, thread A giữ lock của ứng dụng rồi kích hoạt provider; trong lúc khởi tạo, provider gọi thư viện cần lock B. Đồng thời thread B giữ lock B và gọi API cần resolver hoặc lock A. Hai luồng chờ nhau.

~~~text
Thread A                         Thread B
--------                         --------
Giữ lock A                       Giữ lock B
Khởi tạo provider                 Gọi API mạng
Chờ lock B                       Chờ resolver/lock A
       │                               │
       └────────── chờ nhau ───────────┘
                   DEADLOCK
~~~

Đây là sơ đồ tình huống minh họa, không phải mô tả lock nội bộ cố định của mọi JDK. Điểm cần nhớ là provider được khởi tạo trong đường đi nhạy cảm của `InetAddress`; giữ lock ứng dụng, chờ thread hoặc gọi thư viện có dependency mạng có thể tạo vòng chờ.

Không nên dựa vào một chi tiết implementation cụ thể của JDK để cho rằng mọi lời gọi tái nhập đều sẽ được xử lý an toàn. Hãy tuân theo khuyến nghị của API: giữ quá trình khởi tạo service provider đơn giản.

## 7. Ví dụ tốt: provider nhẹ và resolver thực hiện lookup sau khi được cài

Ví dụ sau chỉ quản lý hostname `service.lab.invalid` với địa chỉ tài liệu `203.0.113.9`. Constructor rỗng; `get` chỉ lấy resolver tích hợp và tạo resolver mới. Các thao tác lookup diễn ra trong phương thức của resolver sau khi resolver đã được trả về và cài đặt.

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

public final class LightweightResolverProvider
        extends InetAddressResolverProvider {

    private static final String MANAGED_HOST = "service.lab.invalid";
    private static final byte[] MANAGED_IPV4 = {
            (byte) 203, 0, 113, 9
    };

    // Không mở mạng, không gọi InetAddress, không chờ dependency.
    public LightweightResolverProvider() {
    }

    @Override
    public String name() {
        return "lightweight-lab-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        // Chỉ lấy tham chiếu do JDK cung cấp và tạo resolver.
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                Objects.requireNonNull(host, "host");
                Objects.requireNonNull(policy, "policy");

                if (!MANAGED_HOST.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }

                if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            MANAGED_HOST + " has no address for this policy");
                }

                // getByAddress tạo đối tượng từ byte, không tra DNS.
                return Stream.of(
                        InetAddress.getByAddress(MANAGED_HOST, MANAGED_IPV4));
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr, "addr");

                if (addr.length != 4 && addr.length != 16) {
                    throw new IllegalArgumentException(
                            "IP address must contain 4 or 16 bytes");
                }

                if (Arrays.equals(addr, MANAGED_IPV4)) {
                    return MANAGED_HOST;
                }

                return builtin.lookupByAddress(addr);
            }
        };
    }
}
~~~

Trong ví dụ:

- Constructor chỉ tạo instance provider.
- Không có static initializer gọi API mạng.
- `get` không khởi tạo client, đọc mạng, chờ thread hoặc gọi API phân giải tên.
- Resolver tích hợp được lấy qua `Configuration.builtinResolver()`.
- Hostname ngoài phạm vi được ủy quyền trực tiếp cho resolver tích hợp.
- `InetAddress.getByAddress` chỉ dựng địa chỉ từ byte ở thời điểm lookup; không dùng `getByName` để fallback.

Ví dụ này minh họa cấu trúc khởi tạo gọn. Một resolver sản xuất có thể cần cấu hình hoặc nguồn dữ liệu lớn hơn; hãy tách việc đọc cấu hình, kết nối dịch vụ và quản lý tài nguyên khỏi constructor/provider installation, đồng thời thiết kế timeout, lỗi và đồng bộ phù hợp cho giai đoạn lookup.

## 8. Nếu cần tài nguyên nặng, hãy khởi tạo có kiểm soát

Không phải resolver nào cũng chỉ dùng dữ liệu tĩnh. Một hệ thống thực tế có thể cần:

- Client kết nối service discovery.
- Cấu hình từ file hoặc kho dữ liệu.
- Cache hostname/IP.
- Danh sách mapping có thể thay đổi.
- Metric hoặc logging backend.

Cách tổ chức nên cân nhắc:

| Việc | Giai đoạn phù hợp |
|---|---|
| Tạo provider và hằng số đơn giản | Constructor/static initialization |
| Lấy resolver tích hợp và cấu hình local name | `get(Configuration)` |
| Tạo object resolver nhỏ, không side effect | `get(Configuration)` |
| Kết nối dịch vụ từ xa | Khi lookup thực sự cần, với timeout rõ ràng; hoặc qua bước bootstrap ứng dụng riêng sau khi JVM sẵn sàng |
| Nạp mapping lớn | Sau khi khởi tạo resolver, có kiểm soát và có cơ chế lỗi |
| Làm mới cache | Cơ chế quản trị riêng, thread-safe |
| Log/metrics | Tránh backend có static initialization gọi lại resolver |

Nếu dùng lazy initialization, hãy bảo đảm:

- Chỉ một lần khởi tạo thành công hoặc có chính sách retry rõ ràng.
- Không giữ lock trong khi gọi code bên ngoài có thể phân giải tên.
- Không chờ thread khác nếu thread đó có thể cần resolver đang được khởi tạo.
- Dùng timeout cho thao tác I/O.
- Bảo đảm dữ liệu dùng chung an toàn khi nhiều lookup chạy đồng thời.
- Lỗi khởi tạo tài nguyên được chuyển thành exception lookup phù hợp, không trả kết quả giả.

Lazy initialization không tự động làm code an toàn. Nếu initializer vẫn gọi `InetAddress.getByName` hoặc chờ một dependency cần resolver, chu trình có thể chỉ bị trì hoãn đến lần lookup đầu tiên.

## 9. Điều gì xảy ra nếu constructor hoặc get thất bại?

Theo Javadoc của `InetAddressResolverProvider`:

- Nếu không tìm thấy provider nào, JDK cài resolver tích hợp.
- Nếu provider được tìm thấy nhưng khởi tạo resolver bằng constructor hoặc `get` gặp error/exception, quá trình cài resolver thất bại và lỗi được truyền về caller đã kích hoạt lookup.
- Không nên giả định JDK sẽ âm thầm bỏ qua provider lỗi rồi tự chuyển sang resolver tích hợp.

Do đó, đừng dùng exception như một cách báo “hãy dùng resolver mặc định”. Nếu custom resolver muốn fallback, hãy tạo resolver trả về thành công và bên trong nó ủy quyền phần không quản lý qua `configuration.builtinResolver()`.

Ví dụ đúng:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    InetAddressResolver builtin = configuration.builtinResolver();

    return new CustomResolver(builtin);
}
~~~

Ví dụ sai về ý định fallback:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    // Ném lỗi với hy vọng JDK tự chọn resolver tích hợp.
    throw new IllegalStateException("Use built-in resolver instead");
}
~~~

Cách thứ hai làm thất bại việc cài resolver; caller khởi tạo lookup sẽ nhận lỗi. Nếu muốn toàn bộ ứng dụng dùng resolver tích hợp, không đăng ký provider custom hoặc triển khai fallback tường minh bên trong resolver.

## 10. Checklist rà soát trước khi đóng gói provider

| Hạng mục | Câu hỏi cần kiểm tra |
|---|---|
| Constructor | Có public zero-argument constructor và chỉ làm việc tối thiểu không? |
| Static fields/blocks | Có gọi InetAddress, nạp framework, kết nối mạng hoặc chờ thread không? |
| get(Configuration) | Có chỉ lấy cấu hình cần thiết và tạo resolver nhẹ không? |
| Re-entry | Có gọi `getByName`, `getAllByName`, `getLocalHost` hoặc `getCanonicalHostName` trong giai đoạn cài resolver không? |
| Service loading | Có tự dùng ServiceLoader để tìm lại cùng provider SPI không? |
| Fallback | Có dùng `configuration.builtinResolver()` thay vì gọi vòng qua InetAddress không? |
| External dependency | Có static initializer hoặc constructor gián tiếp gọi DNS/mạng không? |
| Locking | Có giữ lock trong lúc nạp lớp, gọi mạng hoặc chờ thread khác không? |
| Failure | Có hiểu rằng exception từ constructor/get làm việc cài resolver thất bại không? |
| Concurrency | Resolver trả về có an toàn khi nhiều luồng cùng lookup không? |
| Runtime | Đã kiểm tra trong JVM mới với đúng module path/classpath chưa? |

## 11. Câu hỏi tự đánh giá

1. Vì sao Javadoc khuyến nghị provider initialization càng đơn giản càng tốt?
2. Khi nào `InetAddress` tìm và khởi tạo provider?
3. Vì sao gọi `InetAddress.getAllByName` trong `get(Configuration)` có thể tạo chu trình tái nhập?
4. Static initializer có thể gây class loading cycle ngay cả khi constructor rỗng như thế nào?
5. `Configuration.builtinResolver()` giúp fallback ra sao?
6. Nếu `get(Configuration)` ném exception, JDK có bảo đảm tự dùng built-in resolver không?
7. Vì sao lazy initialization vẫn có thể deadlock nếu initializer gọi API mạng?
8. Khi nào nên tạo connection client hoặc nạp mapping lớn?
9. Vì sao không nên giữ application lock trong lúc gọi thư viện bên ngoài ở giai đoạn provider initialization?

**Ghi nhớ:** Provider được nạp đúng lúc `InetAddress` cài resolver toàn JVM. Constructor, static initializer và `get(Configuration)` cần đơn giản, không gọi ngược API phân giải tên, không nạp framework nặng, không kết nối mạng hoặc chờ thread. Lấy resolver tích hợp qua `Configuration.builtinResolver()` để fallback. Nếu khởi tạo custom resolver thất bại, exception được truyền về caller kích hoạt lookup; JDK không bảo đảm tự chuyển sang built-in resolver trong trường hợp đó.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolverProvider` – vòng đời provider, constructor và `get(Configuration)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 26: `InetAddressResolverProvider.Configuration` – resolver tích hợp](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [Java SE 26: `InetAddressResolver` – hợp đồng forward/reverse lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 26: `ServiceLoader` – phát hiện và khởi tạo service provider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html).
