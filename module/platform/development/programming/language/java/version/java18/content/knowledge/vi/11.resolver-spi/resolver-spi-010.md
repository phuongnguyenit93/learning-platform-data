# `Configuration.lookupLocalHostName()`: đọc hostname cục bộ và xác định khi nào cần dùng

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). Bài giải thích `InetAddressResolverProvider.Configuration.lookupLocalHostName()`, API công khai vẫn được hỗ trợ trên JDK hiện đại. Phương thức đọc hostname cục bộ từ cấu hình hệ thống và trả về `String`; nó hữu ích khi custom resolver cần nhận diện hoặc xử lý riêng tên máy local. Bài cũng phân biệt phương thức này với `builtinResolver()`, `InetAddress.getLocalHost()` và địa chỉ loopback.

## 1. Hostname cục bộ là gì?

Một máy tính có thể có nhiều khái niệm tên và địa chỉ khác nhau:

- **Hostname của máy:** tên hệ điều hành hoặc cấu hình mạng gán cho máy, ví dụ `dev-box` hoặc `dev-box.example.test`.
- **Tên loopback:** tên quy ước `localhost` thường được ánh xạ đến địa chỉ loopback.
- **Địa chỉ IP cục bộ:** địa chỉ IPv4/IPv6 được gán cho một hay nhiều giao diện mạng.
- **Địa chỉ loopback:** địa chỉ nội bộ của ngăn xếp mạng, thường là `127.0.0.1` hoặc `::1`.

Các giá trị trên liên quan với nhau nhưng không đồng nghĩa. Hostname máy có thể là tên ngắn, tên đầy đủ hoặc tên được cấu hình riêng; nó không phải một địa chỉ IP.

JEP 418 bổ sung Internet-Address Resolution SPI để `InetAddress` sử dụng resolver tùy biến. Khi JDK gọi `InetAddressResolverProvider.get(Configuration)`, provider nhận một đối tượng cấu hình có hai phương thức:

~~~java
InetAddressResolver builtinResolver();
String lookupLocalHostName();
~~~

- `builtinResolver()` trả về resolver tích hợp của JDK.
- `lookupLocalHostName()` đọc hostname cục bộ từ cấu hình hệ thống và trả về `String`.

Bài này tập trung vào phương thức thứ hai. Nó cung cấp **tên máy local**, không cung cấp danh sách địa chỉ IP, không trả về `InetAddress` và không tự thực hiện forward lookup cho tên đó.

## 2. Hợp đồng của lookupLocalHostName()

Chữ ký:

~~~java
String lookupLocalHostName();
~~~

Javadoc mô tả phương thức là đọc tên localhost từ cấu hình hệ thống. Phương thức không nhận tham số và không khai báo checked exception.

| Thuộc tính | Ý nghĩa |
|---|---|
| Kiểu trả về | `String` hostname cục bộ. |
| Nguồn | Cấu hình hệ thống/nền tảng. |
| Tra cứu IP? | Không. Phương thức chỉ trả về tên. |
| Trả về resolver? | Không. Resolver được lấy qua `builtinResolver()`. |
| Dùng ở đâu? | Trong provider, thường là lúc triển khai `get(Configuration)`. |
| Phiên bản | Có từ Java 18, tiếp tục có trong JDK hiện đại. |

Không nên tự giả định giá trị trả về luôn là một FQDN có dấu chấm, luôn là `localhost`, hoặc luôn trùng với tên reverse DNS của một địa chỉ. API chỉ cam kết trả về hostname local theo cấu hình hệ thống. Cách đặt tên phụ thuộc môi trường chạy.

Ví dụ:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    String localHostName = configuration.lookupLocalHostName();

    // Có thể dùng localHostName để nhận diện tên máy local
    // trong chính sách phân giải của ứng dụng.
    ...
}
~~~

Nếu custom resolver không cần xử lý hostname local theo cách riêng, không cần gọi phương thức này. Có thể chỉ dùng `configuration.builtinResolver()` để ủy quyền lookup.

## 3. Phân biệt ba API thường bị nhầm

### 3.1. lookupLocalHostName(): lấy tên máy

~~~java
String localName = configuration.lookupLocalHostName();
~~~

Kết quả là một chuỗi hostname từ cấu hình hệ thống. Ví dụ, giá trị có thể là `build-agent-07`. Từ chuỗi đó, resolver có thể quyết định dùng nguồn dữ liệu nào hoặc có ánh xạ đặc biệt nào.

### 3.2. InetAddress.getLocalHost(): lấy địa chỉ của máy local

~~~java
InetAddress localAddress = InetAddress.getLocalHost();
System.out.println(localAddress.getHostAddress());
~~~

Đây là API cấp cao trả về một đối tượng `InetAddress` đại diện cho máy cục bộ. Việc lấy địa chỉ liên quan đến phân giải tên máy; nếu hostname local không phân giải được thành địa chỉ, lời gọi có thể ném `UnknownHostException`.

Nó không phải API thay thế cho `lookupLocalHostName()`: một bên trả về tên, bên kia trả về đối tượng địa chỉ.

### 3.3. InetAddress.getLoopbackAddress(): lấy địa chỉ loopback

~~~java
InetAddress loopback = InetAddress.getLoopbackAddress();
System.out.println(loopback.getHostAddress());
~~~

Phương thức này trả về địa chỉ loopback, không phải địa chỉ LAN hoặc địa chỉ có thể truy cập từ máy khác. Nó không đọc hostname của hệ điều hành.

Bảng so sánh:

| API | Kết quả | Dùng khi |
|---|---|---|
| `Configuration.lookupLocalHostName()` | `String` hostname | Cần biết tên máy local từ cấu hình hệ thống. |
| `InetAddress.getLocalHost()` | `InetAddress` | Cần địa chỉ được phân giải cho máy local. |
| `InetAddress.getLoopbackAddress()` | `InetAddress` loopback | Cần địa chỉ loopback để giao tiếp nội bộ trong máy. |
| `Configuration.builtinResolver()` | `InetAddressResolver` | Cần ủy quyền lookup cho resolver tích hợp. |

Đừng coi `localhost`, hostname local và địa chỉ loopback là cùng một giá trị. Chúng có thể cùng trỏ về một máy trong một cấu hình, nhưng vai trò API khác nhau.

## 4. Khi nào custom resolver cần hostname cục bộ?

`lookupLocalHostName()` hữu ích khi custom resolver cần biết tên mà nền tảng đang dùng để gọi chính máy đó. Một số tình huống:

1. **Ánh xạ local theo cấu hình ứng dụng:** resolver có danh mục địa chỉ riêng và cần gắn hostname local với địa chỉ do ứng dụng quản lý.
2. **Chính sách cho hostname local:** tên local được xử lý theo một nguồn dữ liệu hoặc quy tắc khác với hostname bên ngoài.
3. **Kiểm thử môi trường:** bài test muốn nhận diện hostname hiện tại mà không hard-code tên máy của người chạy.
4. **Tích hợp service discovery:** resolver cần đánh dấu một node local trong danh mục node, sau đó dùng địa chỉ từ inventory hoặc registry của ứng dụng.

Ví dụ, một ứng dụng có bảng dữ liệu:

~~~text
hostname hệ thống: build-agent-07
địa chỉ ứng dụng quản lý:
  IPv4: 192.0.2.70
  IPv6: 2001:db8::70
~~~

Resolver có thể dùng hostname được đọc từ hệ thống để tìm bản ghi tương ứng trong bảng cấu hình của ứng dụng.

**Phương thức này không tự tìm ra địa chỉ IP của máy.** Nếu resolver cần trả IP, nó vẫn phải lấy địa chỉ từ nguồn phù hợp hoặc ủy quyền cho resolver tích hợp. Không được tự tạo một địa chỉ tùy ý chỉ vì đã biết hostname.

Nếu ứng dụng không có quy tắc riêng cho hostname local, hãy để resolver tích hợp xử lý tên đó như các hostname khác.

## 5. Đọc hostname một lần trong get(Configuration)

Provider nhận cấu hình khi JDK cài đặt resolver toàn JVM. Cách làm thông thường là đọc hostname trong `get(Configuration)`, sau đó lưu chuỗi vào biến bất biến mà resolver sử dụng:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    Objects.requireNonNull(configuration, "configuration");

    String localHostName = configuration.lookupLocalHostName();
    InetAddressResolver builtin = configuration.builtinResolver();

    return new LocalAwareResolver(localHostName, builtin);
}
~~~

Lợi ích:

- Resolver có sẵn tên local khi xử lý lookup.
- Không cần gọi lại cấu hình ở mỗi truy vấn.
- Không phụ thuộc hostname hard-code trong source.
- Dễ kiểm thử bằng cách truyền một giá trị hostname vào constructor của resolver.

Nên giữ khởi tạo provider đơn giản. Không gọi các API phân giải tên như `InetAddress.getByName()` hoặc `InetAddress.getLocalHost()` trong constructor/provider initialization chỉ để tìm hostname; `Configuration` đã cung cấp phương thức dành riêng cho thông tin này. Việc khởi tạo phức tạp có thể làm tăng nguy cơ vòng lặp nạp lớp hoặc deadlock khi JDK đang cài đặt resolver.

### Xử lý hostname rỗng hoặc không dùng được

Javadoc mô tả giá trị trả về là hostname local nhưng không đưa ra quy tắc để ứng dụng suy ra một tên cố định. Nếu resolver có nhánh xử lý riêng cho local name, nên kiểm tra giá trị trước khi dùng:

~~~java
boolean hasLocalHostName =
        localHostName != null && !localHostName.isBlank();
~~~

Nếu không có giá trị phù hợp để nhận diện local name, có thể bỏ qua nhánh đặc biệt và ủy quyền cho resolver tích hợp. Không tự gán hostname giả cho máy.

## 6. Ví dụ Java 18+: resolver nhận diện hostname local

Ví dụ sau minh họa một resolver có ánh xạ riêng cho hostname do hệ điều hành cung cấp. Địa chỉ `192.0.2.70` và `2001:db8::70` thuộc dải dành cho tài liệu, chỉ dùng làm dữ liệu minh họa; thay chúng bằng địa chỉ từ inventory hoặc cấu hình thực tế của ứng dụng.

Provider lấy hostname local qua `lookupLocalHostName()` và resolver tích hợp qua `builtinResolver()`:

~~~java
package demo.resolver;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public final class LocalHostAwareProvider
        extends InetAddressResolverProvider {

    private static final byte[] LOCAL_IPV4 = {
            (byte) 192, 0, 2, 70
    };

    private static final byte[] LOCAL_IPV6 = {
            0x20, 0x01, 0x0d, (byte) 0xb8,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x70
    };

    public LocalHostAwareProvider() {
    }

    @Override
    public String name() {
        return "local-host-aware-demo";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");

        // Đọc hostname local từ cấu hình hệ thống.
        String localHostName = configuration.lookupLocalHostName();

        // Giữ resolver tích hợp để xử lý các tên/địa chỉ còn lại.
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                Objects.requireNonNull(host, "host");
                Objects.requireNonNull(policy, "policy");

                // Không có local name hoặc hostname không khớp:
                // ủy quyền trực tiếp cho resolver tích hợp.
                if (localHostName == null
                        || localHostName.isBlank()
                        || !localHostName.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }

                int flags = policy.characteristics();
                boolean wantsIpv4 =
                        (flags & LookupPolicy.IPV4) != 0;
                boolean wantsIpv6 =
                        (flags & LookupPolicy.IPV6) != 0;
                boolean ipv4First =
                        (flags & LookupPolicy.IPV4_FIRST) != 0;
                boolean ipv6First =
                        (flags & LookupPolicy.IPV6_FIRST) != 0;

                List<InetAddress> ipv4 = new ArrayList<>();
                List<InetAddress> ipv6 = new ArrayList<>();

                if (wantsIpv4) {
                    ipv4.add(InetAddress.getByAddress(
                            localHostName, LOCAL_IPV4));
                }
                if (wantsIpv6) {
                    ipv6.add(InetAddress.getByAddress(
                            localHostName, LOCAL_IPV6));
                }

                List<InetAddress> result = new ArrayList<>();

                if (ipv4First) {
                    result.addAll(ipv4);
                    result.addAll(ipv6);
                } else if (ipv6First) {
                    result.addAll(ipv6);
                    result.addAll(ipv4);
                } else {
                    // Thứ tự nguồn mặc định của dữ liệu demo: IPv4 rồi IPv6.
                    result.addAll(ipv4);
                    result.addAll(ipv6);
                }

                if (result.isEmpty()) {
                    throw new UnknownHostException(
                            "No address for local hostname: " + host);
                }

                return result.stream();
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr, "addr");

                if (addr.length != 4 && addr.length != 16) {
                    throw new IllegalArgumentException(
                            "IP address must contain 4 or 16 bytes");
                }

                if (localHostName != null
                        && Arrays.equals(addr, LOCAL_IPV4)) {
                    return localHostName;
                }
                if (localHostName != null
                        && Arrays.equals(addr, LOCAL_IPV6)) {
                    return localHostName;
                }

                return builtin.lookupByAddress(addr);
            }
        };
    }
}
~~~

Các điểm cần quan sát:

- `lookupLocalHostName()` được gọi trong `get(Configuration)`, không gọi trong từng lần lookup.
- Resolver dùng tên này để nhận diện hostname local.
- Khi hostname trùng, resolver dùng dữ liệu riêng và vẫn lọc theo `LookupPolicy`.
- Với hostname khác, resolver chuyển nguyên hostname và policy cho resolver tích hợp.
- Reverse lookup của hai địa chỉ demo trả lại local hostname.
- Địa chỉ không thuộc dữ liệu riêng được chuyển cho resolver tích hợp.
- `InetAddress.getByAddress(host, bytes)` tạo đối tượng từ byte đã biết; nó không thực hiện DNS lookup.

Ví dụ chỉ mô tả cách nối hostname hệ thống với dữ liệu ứng dụng. Hai địa chỉ tài liệu không phải địa chỉ thật của máy đang chạy. Trong triển khai thực tế, phải thay chúng bằng địa chỉ do hệ thống quản lý và xác minh rằng chúng thực sự thuộc hostname local.

## 7. Phân biệt với việc gọi getLocalHost() trong provider

`InetAddress.getLocalHost()` là API cấp cao để lấy địa chỉ của máy cục bộ. Nó không chỉ trả về chuỗi hostname. Để có một `InetAddress`, JVM cần xác định tên máy và phân giải tên đó thành địa chỉ.

Trong quá trình khởi tạo custom resolver, gọi thêm các API phân giải của `InetAddress` có thể kích hoạt cơ chế resolver toàn JVM trong lúc resolver đang được cài đặt. Đây là một thời điểm nhạy cảm về khởi tạo. Provider nên dùng thông tin trực tiếp được `Configuration` cung cấp khi chỉ cần hostname local.

Phân biệt cách dùng:

~~~java
// Lấy tên máy từ cấu hình được JDK cung cấp:
String hostName = configuration.lookupLocalHostName();

// Lấy resolver tích hợp để thực hiện lookup:
InetAddressResolver builtin = configuration.builtinResolver();

// Không dùng API phân giải cấp cao để tự tìm tên trong lúc cài provider:
InetAddress local = InetAddress.getLocalHost();
~~~

Nếu cần địa chỉ local thật, hãy thiết kế nguồn dữ liệu và luồng phân giải riêng phù hợp; đừng nhầm rằng `lookupLocalHostName()` đã trả về địa chỉ đó. Trong resolver, khi cần fallback cho hostname hoặc địa chỉ không quản lý, gọi trực tiếp `builtinResolver()` thay vì gọi vòng lại `InetAddress.getByName()` hay `getCanonicalHostName()`.

## 8. Các giới hạn và lưu ý vận hành

| Điều cần lưu ý | Cách xử lý |
|---|---|
| Hostname local có thể không phải FQDN | Không tự nối domain hoặc giả định có dấu chấm. |
| `localhost` không nhất thiết là hostname hệ thống | So sánh với giá trị đọc từ cấu hình; xử lý alias riêng nếu ứng dụng cần. |
| Hostname không phải địa chỉ IP | Cần nguồn ánh xạ hoặc resolver để lấy IP. |
| Một máy có thể có nhiều địa chỉ/giao diện | Dùng inventory hoặc cấu hình đáng tin cậy để cung cấp danh sách IP. |
| Hostname có thể thay đổi theo môi trường | Đọc từ Configuration khi tạo resolver; kiểm thử trên từng môi trường. |
| Reverse DNS không nhất thiết trả cùng hostname | Không coi reverse lookup là xác thực danh tính. |
| Local hostname không chứng minh máy chủ đáng tin | Vẫn xác thực kết nối bằng cơ chế bảo mật phù hợp. |
| Provider được khởi tạo ở cấp JVM | Không giả định thay hostname giữa tiến trình sẽ tự cập nhật resolver đang chạy. |

Đặc biệt, tên local lấy từ cấu hình hệ thống chỉ là dữ liệu nhận diện. Nó không phải bằng chứng mật mã về danh tính máy, không xác nhận địa chỉ IP đang được dùng bởi tiến trình và không thay thế kiểm tra chứng thư TLS.

## 9. Checklist kiểm chứng

| Ca kiểm thử | Điều cần xác minh |
|---|---|
| Configuration trả hostname local hợp lệ | Provider giữ đúng giá trị để resolver sử dụng. |
| Hostname truy vấn trùng local name | Nhánh xử lý local được chọn. |
| Hostname khác local name | Gọi resolver tích hợp với nguyên policy. |
| Local name null hoặc blank | Không dùng nhánh local đặc biệt; fallback theo thiết kế. |
| Policy chỉ IPv4 | Chỉ trả địa chỉ IPv4 local. |
| Policy chỉ IPv6 | Chỉ trả địa chỉ IPv6 local. |
| Policy có FIRST | Thứ tự nhóm địa chỉ tuân theo cờ. |
| Reverse lookup địa chỉ local | Trả hostname local theo mapping. |
| Reverse lookup địa chỉ ngoài phạm vi | Ủy quyền cho resolver tích hợp. |
| `InetAddress.getLocalHost()` | Kiểm thử riêng kết quả phân giải hostname local thành địa chỉ. |
| JVM mới | Kiểm thử lại sau khi thay đổi provider hoặc cấu hình hostname. |

Khi unit test, nên tách phần logic resolver ra một lớp nhận `localHostName` và `builtinResolver` qua constructor. Nhờ vậy có thể kiểm thử hostname cố định mà không phụ thuộc hostname của máy chạy test. Bài kiểm thử tích hợp provider cần chạy trong JVM mới vì resolver được cài ở phạm vi toàn tiến trình.

## 10. Câu hỏi tự đánh giá

1. `lookupLocalHostName()` trả về hostname hay địa chỉ IP?
2. `lookupLocalHostName()` khác `builtinResolver()` ở điểm nào?
3. Vì sao không thể dùng `localhost` làm giá trị thay thế cho mọi hostname local?
4. Khi nào custom resolver nên đọc hostname local từ Configuration?
5. Nếu biết hostname local nhưng chưa có IP, resolver cần lấy địa chỉ từ đâu?
6. Vì sao `InetAddress.getLocalHost()` không phải API thay thế cho `lookupLocalHostName()`?
7. Vì sao không nên gọi các API phân giải cấp cao trong quá trình provider đang được khởi tạo?
8. Hostname local có đủ chứng minh danh tính của một máy chủ khi kết nối TLS không?

**Ghi nhớ:** `Configuration.lookupLocalHostName()` đọc hostname cục bộ từ cấu hình hệ thống và trả về `String`. Dùng nó khi custom resolver cần nhận diện hoặc xử lý riêng tên máy local. Phương thức không trả IP, không thay thế `builtinResolver()` và không tương đương `InetAddress.getLocalHost()`. Nếu cần địa chỉ, resolver phải dùng dữ liệu ứng dụng hoặc ủy quyền lookup phù hợp; luôn tránh gọi vòng lại API phân giải `InetAddress` trong lúc cài resolver.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolverProvider.Configuration` – `lookupLocalHostName()` và `builtinResolver()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [Java SE 26: `InetAddressResolverProvider` – khởi tạo resolver toàn JVM](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 26: `InetAddress` – `getLocalHost()` và các API địa chỉ local](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html).
