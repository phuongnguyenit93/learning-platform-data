# `Configuration.builtinResolver()`: ủy quyền đến resolver tích hợp mà không gọi lặp InetAddress

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). Bài giải thích cách dùng `InetAddressResolverProvider.Configuration.builtinResolver()` trên JDK hiện đại để custom resolver ủy quyền các hostname và địa chỉ IP ngoài phạm vi quản lý cho resolver tích hợp của JDK. Trọng tâm là tránh vòng lặp khi gọi lại `InetAddress`, xử lý cả forward/reverse lookup và giữ đúng hợp đồng lỗi của API. Chỉ sử dụng Resolver SPI công khai còn được hỗ trợ.

## 1. Vì sao cần resolver tích hợp?

Một ứng dụng có thể chỉ muốn can thiệp một phần việc phân giải tên:

- Hostname nội bộ được ánh xạ từ cấu hình hoặc service discovery của ứng dụng.
- Hostname bên ngoài vẫn cần dùng cơ chế phân giải mặc định của hệ điều hành/JDK.
- Reverse lookup của một số địa chỉ nội bộ cần tên riêng, các địa chỉ khác dùng resolver tích hợp.

JEP 418 cung cấp Internet-Address Resolution SPI để tùy biến cách `InetAddress` phân giải tên. Khi viết provider, phương thức `get(Configuration)` nhận một đối tượng `Configuration`. Phương thức `builtinResolver()` của đối tượng này trả về resolver tích hợp mà JDK cung cấp.

Mối quan hệ:

~~~text
Ứng dụng
  │
  │ InetAddress.getAllByName(host)
  ▼
Custom InetAddressResolver
  │
  ├── Host/IP do ứng dụng quản lý
  │       └── Trả kết quả từ dữ liệu riêng
  │
  └── Host/IP ngoài phạm vi
          └── builtinResolver.lookupByName / lookupByAddress
                    │
                    ▼
             Resolver tích hợp của JDK
~~~

Điểm quan trọng: custom resolver và resolver tích hợp đều triển khai `InetAddressResolver`. Custom resolver có thể giữ tham chiếu đến resolver tích hợp và gọi trực tiếp các phương thức SPI của nó. Nhờ vậy, phần không được quản lý vẫn hoạt động theo cơ chế mặc định.

## 2. Lấy builtin resolver đúng cách trong get(Configuration)

Chữ ký provider:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    InetAddressResolver builtin = configuration.builtinResolver();

    return new InetAddressResolver() {
        // lookupByName và lookupByAddress
    };
}
~~~

`configuration.builtinResolver()` trả về `InetAddressResolver` tích hợp. Nên lấy tham chiếu này khi tạo custom resolver rồi đóng kín nó trong implementation được trả về.

Cách này có ba lợi ích:

1. **Ủy quyền đúng tầng:** gọi thẳng SPI của resolver tích hợp, không đi vòng qua API cấp cao `InetAddress`.
2. **Giữ hành vi nền tảng:** các hostname/địa chỉ không được custom resolver quản lý vẫn được xử lý bởi cơ chế tích hợp.
3. **Tránh đệ quy:** không kích hoạt lại resolver toàn JVM mà custom provider vừa đăng ký.

Không cần tạo một `ServiceLoader` khác để tìm resolver tích hợp. `Configuration` đã cung cấp chính resolver mà JDK muốn custom provider dùng làm nền.

## 3. Vì sao gọi lại InetAddress có thể tạo vòng lặp?

Khi custom provider đang được dùng, các API cấp cao như `InetAddress.getByName(host)` và `InetAddress.getAllByName(host)` đi qua cơ chế phân giải của `InetAddress`. Cơ chế đó lại gọi custom resolver.

Nếu trong chính `lookupByName` ta gọi `InetAddress.getAllByName(host)` để fallback, luồng có thể trở thành:

~~~text
InetAddress.getAllByName("external.example")
          │
          ▼
CustomResolver.lookupByName(...)
          │
          │ gọi lại InetAddress.getAllByName(...)
          ▼
InetAddress.getAllByName("external.example")
          │
          ▼
CustomResolver.lookupByName(...)
          │
          └── lặp lại ...
~~~

Kết quả là đệ quy không có điểm dừng, có thể gây stack overflow hoặc làm tiến trình phân giải bị kẹt.

Với reverse lookup, lỗi tương tự có thể xuất hiện khi gọi `InetAddress.getByAddress(addr).getCanonicalHostName()` từ bên trong `lookupByAddress`. Factory `getByAddress` tạo đối tượng địa chỉ từ byte, nhưng `getCanonicalHostName()` có thể cần tra cứu tên ngược và quay lại resolver đang hoạt động.

**Quy tắc:** trong custom resolver, fallback trực tiếp qua tham chiếu `builtin`:

~~~java
return builtin.lookupByName(host, policy);
~~~

hoặc:

~~~java
return builtin.lookupByAddress(addr);
~~~

Không gọi vòng lại `InetAddress` để thực hiện cùng loại lookup.

## 4. Ủy quyền forward lookup

`lookupByName(host, policy)` nhận hostname và policy. Custom resolver nên xác định rõ phạm vi tên mà nó sở hữu:

~~~java
@Override
public Stream<InetAddress> lookupByName(
        String host, LookupPolicy policy)
        throws UnknownHostException {

    Objects.requireNonNull(host, "host");
    Objects.requireNonNull(policy, "policy");

    if (isManagedHost(host)) {
        return lookupManagedHost(host, policy);
    }

    return builtin.lookupByName(host, policy);
}
~~~

Trong ví dụ này:

- `isManagedHost(host)` quyết định hostname thuộc vùng quản lý của ứng dụng hay không.
- `lookupManagedHost(host, policy)` phân giải từ dữ liệu riêng và phải tuân thủ `LookupPolicy`.
- Tên ngoài vùng quản lý được chuyển nguyên `host` và `policy` cho resolver tích hợp.

Không được bỏ qua policy khi fallback. Nếu caller yêu cầu riêng IPv6, resolver tích hợp phải nhận đúng policy đó để lọc kết quả theo hợp đồng.

### Không nuốt UnknownHostException

Nếu resolver tích hợp không tìm thấy hostname, nó ném `UnknownHostException`. Thông thường hãy để exception đó truyền về caller:

~~~java
return builtin.lookupByName(host, policy);
~~~

Không nên bắt `UnknownHostException` rồi trả `Stream.empty()`, `null` hoặc một địa chỉ giả. Điều đó biến lỗi không tìm thấy thành một kết quả không đúng hợp đồng.

Chỉ thực hiện thêm fallback khác nếu ứng dụng có một nguồn dữ liệu thứ hai được xác định rõ. Khi ấy phải quy định thứ tự nguồn, điều kiện retry và cách giữ nguyên nguyên nhân lỗi.

## 5. Ủy quyền reverse lookup

`lookupByAddress(byte[])` nhận mảng byte địa chỉ IP và trả hostname:

~~~java
@Override
public String lookupByAddress(byte[] addr)
        throws UnknownHostException {

    Objects.requireNonNull(addr, "addr");

    if (addr.length != 4 && addr.length != 16) {
        throw new IllegalArgumentException(
                "IP address must contain 4 or 16 bytes");
    }

    if (isManagedAddress(addr)) {
        return lookupManagedAddress(addr);
    }

    return builtin.lookupByAddress(addr);
}
~~~

Trình tự hợp lý:

1. Kiểm tra `null`.
2. Kiểm tra độ dài 4 byte (IPv4) hoặc 16 byte (IPv6).
3. Kiểm tra địa chỉ thuộc phạm vi custom.
4. Nếu thuộc phạm vi custom, trả tên tương ứng.
5. Nếu không, gọi `builtin.lookupByAddress(addr)`.

Không gọi `InetAddress.getByAddress(addr).getCanonicalHostName()` để thay thế bước 5. `getCanonicalHostName()` có thể quay lại cơ chế reverse lookup toàn JVM và gây đệ quy tương tự forward lookup.

Nếu resolver tích hợp không tìm thấy tên, để `UnknownHostException` được truyền về caller. Địa chỉ có độ dài sai vẫn là `IllegalArgumentException`; không chuyển lỗi cấu trúc đầu vào thành lỗi không tìm thấy.

## 6. Ví dụ hoàn chỉnh: custom hostname và fallback cho phần còn lại

Ví dụ sau quản lý hostname `service.lab.invalid` với địa chỉ IPv4 `203.0.113.9` (dải dành cho tài liệu). Mọi hostname và địa chỉ khác được ủy quyền cho resolver tích hợp.

### 6.1. Provider

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

public final class DelegatingResolverProvider
        extends InetAddressResolverProvider {

    private static final String CUSTOM_HOST = "service.lab.invalid";
    private static final byte[] CUSTOM_IP = {
            (byte) 203, 0, 113, 9
    };

    public DelegatingResolverProvider() {
    }

    @Override
    public String name() {
        return "delegating-lab-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");

        // Lấy resolver tích hợp một lần khi tạo custom resolver.
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                Objects.requireNonNull(host, "host");
                Objects.requireNonNull(policy, "policy");

                if (!CUSTOM_HOST.equalsIgnoreCase(host)) {
                    // Fallback trực tiếp, không gọi InetAddress.getAllByName.
                    return builtin.lookupByName(host, policy);
                }

                int flags = policy.characteristics();

                // Host custom chỉ có IPv4.
                if ((flags & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            CUSTOM_HOST + " has no address for this policy");
                }

                // Tạo InetAddress từ byte, không phát sinh DNS lookup.
                return Stream.of(
                        InetAddress.getByAddress(CUSTOM_HOST, CUSTOM_IP));
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr, "addr");

                if (addr.length != 4 && addr.length != 16) {
                    throw new IllegalArgumentException(
                            "IP address must contain 4 or 16 bytes");
                }

                if (Arrays.equals(addr, CUSTOM_IP)) {
                    return CUSTOM_HOST;
                }

                // Fallback trực tiếp, không gọi getCanonicalHostName.
                return builtin.lookupByAddress(addr);
            }
        };
    }
}
~~~

Các điểm cần quan sát:

- `builtin` được lấy từ `Configuration` trong `get(...)`, sau đó giữ trong anonymous resolver.
- Hostname custom được xử lý riêng.
- Hostname khác chuyển nguyên policy cho resolver tích hợp.
- Reverse lookup của IP custom trả hostname custom.
- Reverse lookup của IP khác được ủy quyền.
- Không có lời gọi ngược đến `InetAddress.getByName`, `getAllByName` hoặc `getCanonicalHostName` trong các phương thức fallback.

### 6.2. Đăng ký provider bằng JPMS

Tệp `module-info.java`:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
            with demo.resolver.DelegatingResolverProvider;
}
~~~

Ứng dụng sử dụng API thông thường:

~~~java
import java.net.InetAddress;

public class Demo {
    public static void main(String[] args) throws Exception {
        InetAddress custom =
                InetAddress.getByName("service.lab.invalid");
        System.out.println(custom.getHostAddress());

        InetAddress external =
                InetAddress.getByName("example.com");
        System.out.println(external.getHostAddress());
    }
}
~~~

Hostname `service.lab.invalid` được custom resolver xử lý. `example.com` được chuyển cho resolver tích hợp; kết quả cụ thể phụ thuộc DNS và mạng của môi trường chạy.

Khi chạy với ứng dụng trên classpath, module provider phải được resolve, ví dụ:

~~~shell
java --module-path mods --add-modules demo.resolver -cp out Demo
~~~

Có thể dùng service descriptor `META-INF/services/java.net.spi.InetAddressResolverProvider` khi triển khai provider trên classpath thay vì module descriptor.

## 7. lookupLocalHostName không phải resolver fallback

`Configuration` còn cung cấp `lookupLocalHostName()`. Phương thức này trả tên máy local theo cấu hình hệ thống; nó hữu ích khi custom resolver cần nhận diện tên máy cục bộ.

Không nhầm hai phương thức:

| Phương thức | Trả về | Mục đích |
|---|---|---|
| `builtinResolver()` | `InetAddressResolver` | Ủy quyền forward/reverse lookup. |
| `lookupLocalHostName()` | `String` hostname | Lấy tên máy cục bộ theo cấu hình hệ thống. |

`lookupLocalHostName()` không trả về một resolver và không thay thế `builtinResolver()`. Cũng không nên giả định tên local này là địa chỉ IP hoặc là bằng chứng xác thực danh tính máy chủ.

## 8. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách đúng |
|---|---|---|
| Gọi `InetAddress.getAllByName(host)` bên trong `lookupByName` | Có thể quay lại custom resolver và đệ quy. | Gọi `builtin.lookupByName(host, policy)`. |
| Gọi `getCanonicalHostName()` bên trong `lookupByAddress` | Có thể kích hoạt reverse lookup quay lại custom resolver. | Gọi `builtin.lookupByAddress(addr)`. |
| Không truyền policy khi fallback | Resolver tích hợp không nhận đúng yêu cầu IPv4/IPv6 và thứ tự. | Truyền nguyên `policy`. |
| Trả `Stream.empty()` khi builtin không tìm thấy | Che giấu `UnknownHostException`. | Để exception truyền về caller. |
| Bắt `UnknownHostException` rồi trả hostname giả | Caller nhận kết quả sai. | Giữ nguyên lỗi hoặc gắn cause khi ánh xạ lỗi có chủ đích. |
| Dùng `builtinResolver()` như một provider thứ hai | Nhầm tầng service loading và tầng resolver. | Dùng trực tiếp đối tượng `InetAddressResolver` trả về. |
| Lấy resolver tích hợp bằng cách tạo `ServiceLoader` khác | Không bảo đảm nhận được resolver tích hợp của JDK. | Dùng `Configuration.builtinResolver()`. |
| Bỏ kiểm tra null/độ dài trước fallback | Lỗi đầu vào có thể bị xử lý khác với hợp đồng custom. | Kiểm tra đầu vào theo đúng hợp đồng của phương thức. |

## 9. Checklist kiểm chứng

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Hostname custom | Trả địa chỉ từ dữ liệu custom. |
| Hostname ngoài phạm vi | Gọi `builtin.lookupByName(host, policy)`. |
| Hostname custom nhưng policy không chấp nhận IPv4 | `UnknownHostException`. |
| IP custom reverse lookup | Trả hostname custom. |
| IP ngoài phạm vi | Gọi `builtin.lookupByAddress(addr)`. |
| Mảng reverse lookup là `null` | `NullPointerException`. |
| Mảng reverse lookup không dài 4/16 byte | `IllegalArgumentException`. |
| Builtin không tìm thấy hostname/IP | Để `UnknownHostException` truyền về caller. |
| Fallback forward | Không gọi `InetAddress.getAllByName`. |
| Fallback reverse | Không gọi `getCanonicalHostName`. |
| Runtime | Kiểm thử provider trong JVM mới sau khi thay đổi đăng ký service. |

## 10. Câu hỏi tự đánh giá

1. `Configuration.builtinResolver()` trả về loại đối tượng nào?
2. Vì sao gọi `InetAddress.getAllByName(host)` từ bên trong `lookupByName` có thể đệ quy?
3. Cách fallback đúng cho reverse lookup là gì?
4. Vì sao cần truyền nguyên `LookupPolicy` khi ủy quyền forward lookup?
5. `lookupLocalHostName()` khác `builtinResolver()` như thế nào?
6. Khi resolver tích hợp ném `UnknownHostException`, custom resolver có nên đổi thành `Stream.empty()` không? Vì sao?
7. Nếu custom resolver chỉ quản lý một hostname, làm sao vẫn giữ hành vi phân giải mặc định cho phần còn lại?

**Ghi nhớ:** Lấy resolver tích hợp bằng `configuration.builtinResolver()` trong `get(Configuration)`, giữ tham chiếu đó trong custom resolver và gọi trực tiếp `builtin.lookupByName(host, policy)` hoặc `builtin.lookupByAddress(addr)` cho phần ngoài phạm vi. Không gọi ngược API `InetAddress` để fallback vì có thể quay lại custom resolver và tạo đệ quy. Giữ nguyên policy và exception của resolver tích hợp.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolverProvider.Configuration` – `builtinResolver()` và `lookupLocalHostName()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [Java SE 26: `InetAddressResolver` – `lookupByName` và `lookupByAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 26: `InetAddressResolverProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
