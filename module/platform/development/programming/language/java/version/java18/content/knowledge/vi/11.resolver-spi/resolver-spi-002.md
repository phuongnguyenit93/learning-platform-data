# `lookupByName(host, policy)`: hợp đồng trả `Stream` địa chỉ và báo `UnknownHostException`

> **Phạm vi:** Bài thuộc chương **Resolver SPI** của Java 18 (JEP 418). API `java.net.spi.InetAddressResolver` vẫn hữu ích trên JDK hiện đại để ứng dụng tùy biến cách phân giải hostname thành IP. Trọng tâm là hợp đồng **forward lookup** của `lookupByName(String, LookupPolicy)`, cách lọc/sắp xếp địa chỉ, và cách báo lỗi chính xác. Ví dụ chỉ dùng API đã có từ JDK 18, tránh cơ chế nội bộ hoặc lỗi thời.

## 1. `lookupByName` nằm ở đâu trong quá trình phân giải tên?

Khi mã ứng dụng gọi `InetAddress.getByName("api.example.com")` hoặc `InetAddress.getAllByName("api.example.com")`, JDK có thể sử dụng resolver cấp JVM để tìm các địa chỉ IP phù hợp. JEP 418 mở rộng `InetAddress` bằng service-provider interface (SPI), cho phép đăng ký `InetAddressResolverProvider` để cung cấp một triển khai `InetAddressResolver` riêng.

Trong interface `java.net.spi.InetAddressResolver`, phương thức phân giải thuận có chữ ký:

~~~java
Stream<InetAddress> lookupByName(
        String host,
        InetAddressResolver.LookupPolicy lookupPolicy)
        throws UnknownHostException;
~~~

Ví dụ tình huống: một hệ thống chạy thử cần ánh xạ hostname `api.lab.invalid` đến địa chỉ IP kiểm thử do ứng dụng kiểm soát. Resolver có thể trả về bản ghi IPv4/IPv6 từ dữ liệu nội bộ, nhưng phải tuân thủ đúng hợp đồng mà `InetAddress` mong đợi.

~~~text
Mã ứng dụng
    │ InetAddress.getAllByName("api.lab.invalid")
    ▼
InetAddress (cache và cơ chế phân giải của JDK)
    │
    ▼
InetAddressResolver.lookupByName(host, policy)
    │
    ├── Có IP phù hợp → Stream<InetAddress> theo policy
    └── Không có IP phù hợp → UnknownHostException
~~~

**Phân biệt:** `lookupByName` là phương thức của SPI, không phải phương thức public trên `InetAddress` cho ứng dụng gọi hàng ngày. Muốn `InetAddress` sử dụng resolver riêng, cần đăng ký provider phù hợp. Bài này minh họa trực tiếp hợp đồng của resolver để dễ kiểm thử; cách đăng ký provider là một bước tích hợp riêng.

## 2. Hợp đồng đầu vào và đầu ra

| Phần | Yêu cầu của API | Cách hiện thực an toàn |
|---|---|---|
| `host` | Tên máy cần tra cứu; không được `null`. | Kiểm tra `Objects.requireNonNull(host)`; dùng quy tắc so khớp hostname thống nhất. |
| `lookupPolicy` | Chính sách họ IP và thứ tự kết quả; không được `null`. | Đọc `lookupPolicy.characteristics()`, rồi áp dụng các bit cờ liên quan. |
| Kết quả | `Stream<InetAddress>` chứa IP của hostname thuộc các họ IP được yêu cầu, theo thứ tự thích hợp. | Trả stream các `InetAddress` hợp lệ; tránh phần tử `null`, sai họ IP hoặc thứ tự. |
| Không có địa chỉ | Ném `UnknownHostException`. | Kiểm tra kết quả sau lọc; nếu không có IP phù hợp thì ném exception. |
| Đối số `null` | Ném `NullPointerException` nếu một trong hai đối số là `null`. | Kiểm tra sớm cả hai đối số, trước khi tra cứu hay mở tài nguyên. |

### `host` là tên máy, không phải chuỗi IP

Javadoc yêu cầu `host` là hostname như `"www.example.com"`, không phải biểu diễn văn bản của một địa chỉ IP. API **không tự kiểm tra tên được truyền vào**; nếu nhận chuỗi như `"192.0.2.10"`, resolver có thể không tìm thấy mapping và ném `UnknownHostException`. Điều này khác với `InetAddress.getByName("192.0.2.10")`: API cấp cao có khả năng nhận IP literal và xử lý mà không cần phân giải tên qua SPI.

Một điểm dễ nhầm khác: `InetAddress.getByName(null)` có hợp đồng riêng, có thể trả địa chỉ loopback; còn gọi **trực tiếp** `InetAddressResolver.lookupByName(null, policy)` vi phạm hợp đồng SPI và phải ném `NullPointerException`.

### Vì sao trả `Stream` nhưng vẫn phải kiểm tra kết quả?

`Stream<InetAddress>` cho phép biểu diễn danh sách địa chỉ IP theo thứ tự và chỉ tiêu thụ một lần, chẳng hạn khi hostname có cả A (IPv4) và AAAA (IPv6). Một resolver có thể thu thập các địa chỉ trong danh sách rồi trả `list.stream()`. Đây là cách dễ bảo đảm điều kiện lỗi và thứ tự.

**Không dùng `Stream.empty()` như tín hiệu “không tìm thấy hostname”.** Hợp đồng phương thức quy định ném `UnknownHostException` khi không tìm thấy IP. Việc trả stream rỗng có thể khiến lỗi xuất hiện muộn hơn ở lớp gọi, mất thông tin nguyên nhân. Tương tự, không trả `null` hoặc một stream chứa phần tử `null`.

Nên xác định lỗi **trước khi trả stream** thay vì thiết kế một pipeline lazy sẽ đợi đến lúc tiêu thụ mới phát hiện lỗi. `UnknownHostException` là checked exception; xử lý muộn trong các phép toán trên stream dễ dẫn đến việc gói lỗi thành unchecked exception khó theo dõi.

## 3. Hiểu và áp dụng `LookupPolicy`

`InetAddressResolver.LookupPolicy` là đối tượng mô tả họ IP cần truy vấn và ưu tiên thứ tự. Gọi `characteristics()` để lấy tập cờ bitmask.

| Cờ | Ý nghĩa |
|---|---|
| `LookupPolicy.IPV4` | Yêu cầu địa chỉ IPv4. |
| `LookupPolicy.IPV6` | Yêu cầu địa chỉ IPv6. |
| `LookupPolicy.IPV4_FIRST` | Khi trả cả hai họ IP, đưa IPv4 lên trước IPv6. |
| `LookupPolicy.IPV6_FIRST` | Khi trả cả hai họ IP, đưa IPv6 lên trước IPv4. |

Ví dụ:

~~~java
import java.net.spi.InetAddressResolver.LookupPolicy;

// Chỉ lấy IPv4
LookupPolicy ipv4Only = LookupPolicy.of(LookupPolicy.IPV4);

// Cho phép cả IPv4/IPv6, ưu tiên IPv6
LookupPolicy dualStackV6First = LookupPolicy.of(
        LookupPolicy.IPV4 | LookupPolicy.IPV6 | LookupPolicy.IPV6_FIRST);
~~~

`LookupPolicy.of(int)` từ chối cấu hình không hợp lệ bằng `IllegalArgumentException`:

- Phải chọn ít nhất một trong hai cờ `IPV4` hoặc `IPV6`.
- Không được chọn đồng thời `IPV4_FIRST` và `IPV6_FIRST`.
- Các bit cờ khác ngoài những cờ hợp lệ cũng không được chấp nhận.

Nếu không có cờ `_FIRST`, chính sách yêu cầu giữ thứ tự “system”; nguồn dữ liệu hoặc resolver nền tảng quyết định thứ tự thích hợp, không nên tự khẳng định mọi máy đều ưu tiên cùng một họ IP. Trong ví dụ dữ liệu tĩnh ở phần sau, trường hợp này giữ thứ tự bản ghi đầu vào.

Một số tình huống cần phân biệt:

| Dữ liệu hostname | Chính sách | Kết quả hợp lệ |
|---|---|---|
| Có IPv4 và IPv6 | `IPV4` | Chỉ các `Inet4Address`. |
| Có IPv4 và IPv6 | `IPV6` | Chỉ các `Inet6Address`. |
| Có IPv4 và IPv6 | `IPV4 | IPV6 | IPV6_FIRST` | Các địa chỉ IPv6 đứng trước IPv4. |
| Chỉ có IPv4 | `IPV6` | Ném `UnknownHostException` do không có IP thuộc họ được yêu cầu. |
| Không tồn tại hostname | Bất kỳ policy hợp lệ nào | Ném `UnknownHostException`. |

**Không suy luận họ IP bằng độ dài của chuỗi** (dấu `:` hay dấu `.`), vì dữ liệu từ resolver nên là `InetAddress`. Có thể dùng `instanceof Inet4Address` và `instanceof Inet6Address` để lọc chính xác.

## 4. Ví dụ Java 18+: một resolver có thể kiểm thử độc lập

Đoạn mã dưới tạo resolver có hai hostname giả lập:

- `dual.lab.invalid` có IPv4 `192.0.2.10` và IPv6 `2001:db8::10`.
- `v4only.lab.invalid` chỉ có IPv4 `192.0.2.20`.

Các địa chỉ thuộc dải dành cho tài liệu. Chương trình không truy vấn DNS bên ngoài: `InetAddress.getByAddress(host, byte[])` **tạo đối tượng địa chỉ từ byte đã biết**, không xác minh bằng lookup. Điều này giúp việc kiểm tra hợp đồng có kết quả xác định.

Lưu vào `ResolverLookupExample.java`:

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public final class ResolverLookupExample {
    private static final String DUAL_HOST = "dual.lab.invalid";
    private static final String V4_HOST = "v4only.lab.invalid";

    private static InetAddress address(String host, byte[] raw) {
        try {
            // Không gọi DNS: chỉ tạo InetAddress từ byte.
            return InetAddress.getByAddress(host, raw);
        } catch (UnknownHostException e) {
            throw new AssertionError("Invalid test IP bytes", e);
        }
    }

    private static final InetAddress DUAL_V4 = address(
            DUAL_HOST, new byte[] {(byte) 192, 0, 2, 10});

    private static final InetAddress DUAL_V6 = address(
            DUAL_HOST, new byte[] {
                    0x20, 0x01, 0x0d, (byte) 0xb8,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10
            });

    private static final InetAddress ONLY_V4 = address(
            V4_HOST, new byte[] {(byte) 192, 0, 2, 20});

    static final class DemoResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(
                String host, LookupPolicy policy) throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            // 1. Lấy các địa chỉ đã biết cho hostname.
            List<InetAddress> candidates;
            if (DUAL_HOST.equalsIgnoreCase(host)) {
                candidates = List.of(DUAL_V4, DUAL_V6);
            } else if (V4_HOST.equalsIgnoreCase(host)) {
                candidates = List.of(ONLY_V4);
            } else {
                throw new UnknownHostException("Unknown host: " + host);
            }

            // 2. Lọc theo họ IP do caller yêu cầu.
            int flags = policy.characteristics();
            List<InetAddress> matches = new ArrayList<>();
            for (InetAddress candidate : candidates) {
                boolean allowV4 = candidate instanceof Inet4Address
                        && (flags & LookupPolicy.IPV4) != 0;
                boolean allowV6 = candidate instanceof Inet6Address
                        && (flags & LookupPolicy.IPV6) != 0;
                if (allowV4 || allowV6) {
                    matches.add(candidate);
                }
            }

            // 3. Hết địa chỉ sau lọc cũng là lỗi lookup.
            if (matches.isEmpty()) {
                throw new UnknownHostException(
                        "No address of requested family for " + host);
            }

            // 4. Tôn trọng ưu tiên họ IP; sort ổn định trong mỗi họ.
            if ((flags & LookupPolicy.IPV4_FIRST) != 0) {
                matches.sort(Comparator.comparingInt(
                        a -> a instanceof Inet4Address ? 0 : 1));
            } else if ((flags & LookupPolicy.IPV6_FIRST) != 0) {
                matches.sort(Comparator.comparingInt(
                        a -> a instanceof Inet6Address ? 0 : 1));
            }

            // 5. Trả stream không rỗng, chứa các địa chỉ đã lọc.
            return matches.stream();
        }

        @Override
        public String lookupByAddress(byte[] addr)
                throws UnknownHostException {
            Objects.requireNonNull(addr, "addr");
            if (addr.length != 4 && addr.length != 16) {
                throw new IllegalArgumentException("Invalid IP length");
            }
            // Ví dụ chỉ triển khai lookup thuận.
            throw new UnknownHostException("Reverse lookup not configured");
        }
    }

    private static void show(
            DemoResolver resolver, String host, LookupPolicy policy) {
        try (Stream<InetAddress> addresses =
                     resolver.lookupByName(host, policy)) {
            System.out.println(host + " -> "
                    + addresses.map(InetAddress::getHostAddress).toList());
        } catch (UnknownHostException e) {
            System.out.println(host + " -> UnknownHostException: "
                    + e.getMessage());
        }
    }

    public static void main(String[] args) {
        DemoResolver resolver = new DemoResolver();
        show(resolver, DUAL_HOST,
                LookupPolicy.of(LookupPolicy.IPV4));
        show(resolver, DUAL_HOST,
                LookupPolicy.of(LookupPolicy.IPV6));
        show(resolver, DUAL_HOST,
                LookupPolicy.of(LookupPolicy.IPV4 | LookupPolicy.IPV6
                        | LookupPolicy.IPV6_FIRST));
        show(resolver, V4_HOST,
                LookupPolicy.of(LookupPolicy.IPV6));
        show(resolver, "missing.lab.invalid",
                LookupPolicy.of(LookupPolicy.IPV4));
    }
}
~~~

Biên dịch và chạy với JDK 18 hoặc mới hơn:

~~~shell
javac ResolverLookupExample.java
java ResolverLookupExample
~~~

Các nhận xét cần thấy trong kết quả:

1. Với `IPV4`, hostname dual chỉ trả `192.0.2.10`.
2. Với `IPV6`, hostname dual chỉ trả địa chỉ bắt đầu bằng `2001:db8:`.
3. Với `IPV6_FIRST` và hai họ IP được yêu cầu, địa chỉ IPv6 phải xuất hiện trước IPv4.
4. Với hostname chỉ có IPv4 nhưng yêu cầu `IPV6`, chương trình bắt `UnknownHostException`.
5. Với hostname không có mapping, chương trình cũng bắt `UnknownHostException`.

Định dạng văn bản IPv6 do `getHostAddress()` tạo có thể khác cách viết rút gọn ban đầu; hãy xác minh bằng đối tượng/byte địa chỉ nếu cần kiểm thử chặt chẽ.

Ví dụ gọi **trực tiếp** `DemoResolver.lookupByName(...)`. Nó chứng minh cách viết và thử hợp đồng SPI, không tự cài resolver vào `InetAddress` của JVM. Muốn dùng toàn JVM, hãy đặt implementation sau một `InetAddressResolverProvider` và đăng ký qua JPMS `provides ... with ...` hoặc service configuration của `ServiceLoader`.

## 5. Xử lý lỗi đúng: khi nào ném `UnknownHostException`?

`UnknownHostException` là checked exception thông báo không thể tìm được địa chỉ IP cho hostname theo chính sách yêu cầu. Đây là hành vi bình thường của một bộ phân giải tên, không tự động đồng nghĩa DNS hoặc mạng đã hỏng.

| Trường hợp | Cách xử lý |
|---|---|
| Tên không tồn tại trong dữ liệu resolver | `throw new UnknownHostException(host)` hoặc thêm thông tin phù hợp. |
| Có bản ghi nhưng không có họ IP mà policy yêu cầu | `UnknownHostException`; không trả sai họ IP. |
| Cả hệ thống nguồn dữ liệu không cung cấp IP hợp lệ | `UnknownHostException` với nguyên nhân ngắn gọn; cân nhắc gắn cause nếu có lỗi bên dưới. |
| `host == null` hoặc `policy == null` | `NullPointerException` theo hợp đồng API. |
| `LookupPolicy.of(...)` nhận cờ không hợp lệ | `IllegalArgumentException` ngay khi tạo policy. |
| Tìm được IP phù hợp | Stream có phần tử, đúng họ IP và thứ tự; không ném exception. |

Ví dụ sai:

~~~java
// Sai hợp đồng: không có địa chỉ nhưng trả stream rỗng.
return Stream.empty();

// Sai hợp đồng: bỏ qua yêu cầu chỉ IPv6.
return Stream.of(ipv4Address);

// Sai cách báo lỗi: biến "không tìm thấy" thành null.
return null;
~~~

Ví dụ đúng:

~~~java
if (matchingAddresses.isEmpty()) {
    throw new UnknownHostException(
            "No address matching lookup policy for " + host);
}
return matchingAddresses.stream();
~~~

Lưu ý: một lỗi hạ tầng như timeout hoặc không truy cập được nguồn dữ liệu cũng có thể làm việc phân giải thất bại. Resolver nên cung cấp ngữ cảnh đủ để chẩn đoán, tránh ghi trực tiếp bí mật cấu hình hoặc dữ liệu nhạy cảm vào thông báo exception.

## 6. Tích hợp với provider, fallback và cache

Nếu một resolver tùy biến chỉ quản lý một tập hostname nội bộ, có thể **ủy quyền tên còn lại** cho resolver tích hợp mà JDK cung cấp qua `InetAddressResolverProvider.Configuration.builtinResolver()`:

~~~java
// Trong implementation của InetAddressResolverProvider.get(configuration):
InetAddressResolver builtin = configuration.builtinResolver();

// Trong implementation InetAddressResolver.lookupByName(...):
if (isManagedHost(host)) {
    return customResolver.lookupByName(host, policy);
}
return builtin.lookupByName(host, policy);
~~~

Đây là **đoạn minh họa**, giả định đã có `isManagedHost` và `customResolver`; đoạn hoàn chỉnh có thể chạy độc lập nằm ở phần 4.

Không dùng `InetAddress.getAllByName(host)` từ bên trong `lookupByName(...)` để làm fallback. Khi provider tùy chỉnh đang hoạt động, lệnh ấy có thể quay lại chính resolver hiện tại, gây đệ quy và có thể lặp vô hạn.

Cơ chế cache của `InetAddress` có thể giữ kết quả tra cứu thành công hoặc thất bại trong một khoảng thời gian. Do đó sửa dữ liệu của custom resolver không bảo đảm kết quả của các lời gọi `InetAddress.getByName(...)` thay đổi ngay. Kiểm thử trực tiếp `lookupByName(...)` xác minh hợp đồng của implementation; kiểm thử qua `InetAddress` xác minh cả tích hợp provider và hành vi cache. Nên tách hai mục tiêu này.

Việc lựa chọn provider áp dụng ở cấp JVM; không nên giả định mỗi lệnh `getByName` sẽ chọn lại một provider. Nếu chạy nhiều provider, thứ tự chọn không phải cơ chế fallback đáng tin cậy.

## 7. Checklist kiểm thử hợp đồng

| Ca kiểm thử | Điều cần xác minh |
|---|---|
| Có cả IPv4 và IPv6; policy chỉ IPv4 | Không có `Inet6Address` trong stream. |
| Có cả IPv4 và IPv6; policy chỉ IPv6 | Không có `Inet4Address` trong stream. |
| Cả hai họ; `IPV4_FIRST` | Mọi IPv4 xuất hiện trước IPv6. |
| Cả hai họ; `IPV6_FIRST` | Mọi IPv6 xuất hiện trước IPv4. |
| Hostname không tồn tại | Ném `UnknownHostException`. |
| Chỉ có IPv4; yêu cầu chỉ IPv6 | Ném `UnknownHostException`. |
| `host == null` | Ném `NullPointerException`. |
| `policy == null` | Ném `NullPointerException`. |
| Không có policy ưu tiên | Không áp đặt quy tắc IPv4-first hoặc IPv6-first vô điều kiện. |
| Tích hợp qua provider | Kiểm tra trong JVM mới để tránh provider/cache đã khởi tạo từ lần trước. |

Có thể kiểm tra thứ tự bằng `toList()` và kiểm tra kiểu bằng `instanceof`. Không nên so sánh chuỗi IPv6 nguyên văn vì nhiều dạng viết biểu diễn cùng một địa chỉ.

## 8. Câu hỏi tự đánh giá

1. Vì sao `lookupByName` trả `Stream<InetAddress>` thay vì một `InetAddress` duy nhất?
2. Một hostname có bản ghi A nhưng không có AAAA. Với policy `IPV6`, trả `Stream.empty()` hay ném `UnknownHostException`? Vì sao?
3. `LookupPolicy.IPV6_FIRST` có làm thay đổi kết quả khi caller chỉ yêu cầu IPv4 hay không?
4. Tại sao dùng `InetAddress.getByName(...)` làm fallback bên trong resolver tùy biến dễ tạo vòng đệ quy?
5. Vì sao kiểm thử gọi trực tiếp custom resolver và kiểm thử `InetAddress.getAllByName(...)` có thể quan sát kết quả khác nhau khi cache được bật?

**Ghi nhớ:** triển khai `lookupByName(host, policy)` đúng nghĩa là: **nhận hostname hợp lệ về mặt đối số; phân giải địa chỉ theo nguồn dữ liệu; lọc họ IP; tôn trọng thứ tự; trả một stream có kết quả; hoặc ném `UnknownHostException` khi không tìm thấy IP thích hợp**. Các điều kiện này vẫn là nền tảng khi sử dụng Resolver SPI trên các JDK hiện đại.

## Tài liệu chính thức

- [OpenJDK JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 25: `InetAddressResolver` — hợp đồng `lookupByName`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 25: `InetAddressResolver.LookupPolicy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE 25: `InetAddressResolverProvider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 25: `InetAddress` — getByName/getAllByName, cache](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html).
