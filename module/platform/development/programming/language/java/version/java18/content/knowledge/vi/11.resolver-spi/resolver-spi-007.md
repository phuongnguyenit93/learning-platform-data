# Kiểm tra null, độ dài địa chỉ không hợp lệ và trường hợp không có kết quả phân giải

> **Phạm vi:** Chương **Resolver SPI** của Java 18 (JEP 418). Bài tập trung vào hợp đồng lỗi của `java.net.spi.InetAddressResolver` trên JDK hiện đại: phân biệt đối số `null`, mảng địa chỉ IP sai độ dài và hostname/IP hợp lệ về cấu trúc nhưng không có kết quả phân giải. Ba tình huống này có loại exception khác nhau; implementation phải báo đúng lỗi để caller xử lý chính xác. Chỉ dùng API công khai còn được hỗ trợ.

## 1. Vì sao phải phân biệt ba nhóm lỗi?

Resolver SPI cho phép JDK dùng một bộ phân giải tên tùy biến. Interface `InetAddressResolver` có hai hướng tra cứu:

~~~java
Stream<InetAddress> lookupByName(
        String host,
        InetAddressResolver.LookupPolicy lookupPolicy)
        throws UnknownHostException;

String lookupByAddress(byte[] addr)
        throws UnknownHostException;
~~~

- **Forward lookup:** hostname → một hoặc nhiều địa chỉ IP.
- **Reverse lookup:** địa chỉ IP dạng byte → hostname.

Khi tra cứu thất bại, không phải mọi nguyên nhân đều giống nhau. Ví dụ:

| Tình huống | Ý nghĩa | Exception theo hợp đồng |
|---|---|---|
| Caller truyền `null` | Đối số bắt buộc không tồn tại. | `NullPointerException` |
| Mảng IP không có 4 hoặc 16 byte | Dữ liệu không phải biểu diễn IPv4/IPv6 hợp lệ theo API. | `IllegalArgumentException` |
| Host/IP hợp lệ về cấu trúc nhưng không tìm thấy tên hoặc địa chỉ phù hợp | Lookup không có kết quả. | `UnknownHostException` |

Sơ đồ phân loại:

~~~text
Lời gọi resolver
      │
      ▼
Đối số có null?
  ├── Có ──▶ NullPointerException
  └── Không
       │
       ▼
Độ dài raw IP có hợp lệ? (chỉ lookupByAddress)
  ├── Không ──▶ IllegalArgumentException
  └── Có
       │
       ▼
Có kết quả phân giải phù hợp?
  ├── Không ──▶ UnknownHostException
  └── Có ──▶ Kết quả theo hợp đồng
~~~

Điểm quan trọng là `NullPointerException` và `IllegalArgumentException` báo lỗi **đầu vào**, còn `UnknownHostException` báo rằng resolver không tìm thấy kết quả. Không đổi tất cả thành một exception chung, không trả `null` và cũng không trả stream rỗng để che giấu lookup thất bại.

## 2. Đối số null: NullPointerException

Javadoc của Resolver SPI quy định các đối số bắt buộc không được `null`:

- `lookupByName(host, lookupPolicy)`: cả `host` và `lookupPolicy` đều không được `null`.
- `lookupByAddress(addr)`: `addr` không được `null`.

Ví dụ:

~~~java
resolver.lookupByName(null, policy); // NullPointerException
resolver.lookupByName("api.example.test", null); // NullPointerException
resolver.lookupByAddress(null); // NullPointerException
~~~

Implementation nên kiểm tra null ở đầu phương thức:

~~~java
Objects.requireNonNull(host, "host");
Objects.requireNonNull(lookupPolicy, "lookupPolicy");
Objects.requireNonNull(addr, "addr");
~~~

Mỗi phương thức chỉ kiểm tra những tham số của nó. Không cần kiểm tra `addr` trong forward lookup hoặc kiểm tra `host` trong reverse lookup.

### Vì sao nên kiểm tra sớm?

1. **Lỗi có vị trí rõ ràng:** stack trace trỏ tới hợp đồng đầu vào của resolver, không phải một phép so sánh hoặc thao tác mảng sâu bên trong.
2. **Không gọi nguồn dữ liệu khi đối số đã sai:** tránh truy vấn DNS, database hoặc service discovery không cần thiết.
3. **Thông báo dễ hiểu:** có thể cung cấp tên tham số như `"host"` hoặc `"addr"` trong thông báo của exception.

`Objects.requireNonNull` thuộc `java.util.Objects`, là API Java lâu đời vẫn được hỗ trợ trên JDK hiện đại:

~~~java
import java.util.Objects;

byte[] addr = Objects.requireNonNull(input, "addr");
~~~

Không dùng cách sau:

~~~java
if (addr == null) {
    return null; // Sai hợp đồng
}
~~~

`null` không có nghĩa là “không tìm thấy hostname”. Nó là đối số không hợp lệ và phải được báo bằng `NullPointerException`.

## 3. Độ dài địa chỉ không hợp lệ: IllegalArgumentException

`lookupByAddress(byte[])` nhận địa chỉ IP dưới dạng mảng byte theo **network byte order**:

- IPv4: đúng **4 byte**.
- IPv6: đúng **16 byte**.

Các ví dụ:

| Mảng byte | Ý nghĩa | Kết quả kiểm tra độ dài |
|---|---|---|
| `{(byte) 192, 0, 2, 10}` | IPv4 | Hợp lệ |
| 16 byte của `2001:db8::10` | IPv6 | Hợp lệ |
| `{1, 2, 3}` | Chỉ 3 byte | `IllegalArgumentException` |
| `{1, 2, 3, 4, 5}` | 5 byte | `IllegalArgumentException` |
| Mảng rỗng | 0 byte | `IllegalArgumentException` |

Mảng `null` được xử lý trước bằng `NullPointerException`; mảng không null nhưng sai độ dài được xử lý bằng `IllegalArgumentException`.

Mẫu kiểm tra:

~~~java
static void validateAddress(byte[] addr) {
    Objects.requireNonNull(addr, "addr");

    if (addr.length != 4 && addr.length != 16) {
        throw new IllegalArgumentException(
                "IP address must contain exactly 4 or 16 bytes");
    }
}
~~~

Không dùng `UnknownHostException` cho mảng sai độ dài. `UnknownHostException` có nghĩa là lookup không tìm được hostname, còn mảng 3 byte chưa phải một địa chỉ IPv4/IPv6 hợp lệ để bắt đầu lookup.

### Phân biệt với InetAddress.getByAddress

Một API dễ nhầm là `InetAddress.getByAddress(byte[])`. Hai phương thức có hợp đồng khác nhau:

| API | Mục đích | Độ dài sai |
|---|---|---|
| `InetAddressResolver.lookupByAddress(byte[])` | Tra cứu ngược địa chỉ thành hostname. | `IllegalArgumentException` |
| `InetAddress.getByAddress(byte[])` | Tạo đối tượng `InetAddress` từ raw bytes, không tra cứu DNS. | `UnknownHostException` |

Ví dụ:

~~~java
byte[] invalid = {1, 2, 3};

// Factory của InetAddress có hợp đồng exception riêng:
InetAddress.getByAddress(invalid); // UnknownHostException

// Resolver SPI báo độ dài đối số không hợp lệ:
resolver.lookupByAddress(invalid); // IllegalArgumentException
~~~

Không lấy exception của factory `InetAddress` để suy luận exception của Resolver SPI. Hãy đọc đúng Javadoc của phương thức đang triển khai.

## 4. Không có kết quả phân giải: UnknownHostException

`UnknownHostException` là checked exception trong `java.net`, được dùng khi không thể tìm thấy địa chỉ hoặc hostname tương ứng.

### Với forward lookup

`lookupByName(host, policy)` ném `UnknownHostException` khi:

- Hostname không được nguồn dữ liệu của resolver biết đến.
- Hostname tồn tại nhưng không có địa chỉ thuộc họ IP mà policy yêu cầu.
- Nguồn phân giải không thể cung cấp địa chỉ phù hợp.

Ví dụ: hostname chỉ có IPv4 nhưng caller yêu cầu riêng IPv6. Địa chỉ IPv4 tồn tại không làm cho kết quả hợp lệ với policy IPv6-only.

~~~java
if (matchingAddresses.isEmpty()) {
    throw new UnknownHostException(
            "No address matching lookup policy for " + host);
}
return matchingAddresses.stream();
~~~

Không trả `Stream.empty()` để báo không tìm thấy. Hợp đồng lookup yêu cầu exception khi không tìm thấy địa chỉ. Stream rỗng khiến caller khó phân biệt “không tồn tại hostname” với một implementation đã trả kết quả rỗng sai hợp đồng.

### Với reverse lookup

`lookupByAddress(addr)` ném `UnknownHostException` khi:

- Địa chỉ có đúng 4 hoặc 16 byte nhưng không có ánh xạ hostname.
- Resolver đã tra nguồn dữ liệu nhưng không tìm được tên máy.
- Resolver không thể cung cấp tên tương ứng với địa chỉ đó.

~~~java
String host = reverseMap.get(addressKey);
if (host == null) {
    throw new UnknownHostException(
            "No hostname registered for the address");
}
return host;
~~~

Không trả `null`, chuỗi rỗng hoặc chuỗi IP để giả vờ reverse lookup thành công. Nếu ứng dụng muốn hiển thị IP khi không có hostname, caller có thể bắt `UnknownHostException` và tự quyết định cách hiển thị.

### Lỗi nguồn dữ liệu và nguyên nhân gốc

Nếu resolver dùng database hoặc service discovery, lỗi kết nối nguồn có thể khiến lookup thất bại. Implementation nên giữ thông tin nguyên nhân bằng cách gắn cause khi thích hợp:

~~~java
try {
    return directory.lookup(host);
} catch (DirectoryUnavailableException e) {
    UnknownHostException failure =
            new UnknownHostException("Unable to resolve host: " + host);
    failure.initCause(e);
    throw failure;
}
~~~

Đây là ví dụ minh họa cách giữ cause khi ánh xạ lỗi của nguồn dữ liệu sang lỗi lookup. Chỉ chuyển lỗi khi nó thực sự có nghĩa là resolver không thể cung cấp kết quả theo hợp đồng; không biến lỗi lập trình như `NullPointerException` hoặc `IllegalStateException` thành `UnknownHostException` một cách tùy tiện.

## 5. Ví dụ Java 18+: một resolver thể hiện đủ ba trường hợp

Ví dụ dùng một bảng ánh xạ tĩnh để không phụ thuộc DNS bên ngoài:

- `api.lab.invalid` ↔ IPv4 `192.0.2.10`.
- `api6.lab.invalid` ↔ IPv6 `2001:db8::10`.
- `missing.lab.invalid` không có ánh xạ.
- Một địa chỉ đúng độ dài khác hai địa chỉ trên cũng không có hostname.

Lưu thành `ResolverErrorDemo.java`:

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public final class ResolverErrorDemo {
    private static final String HOST4 = "api.lab.invalid";
    private static final String HOST6 = "api6.lab.invalid";

    private static final byte[] IP4 = {(byte) 192, 0, 2, 10};
    private static final byte[] IP6 = {
            0x20, 0x01, 0x0d, (byte) 0xb8,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10
    };

    private static InetAddress address(String host, byte[] raw) {
        try {
            // Tạo đối tượng từ byte, không thực hiện DNS lookup.
            return InetAddress.getByAddress(host, raw);
        } catch (UnknownHostException impossible) {
            throw new AssertionError(impossible);
        }
    }

    private static final InetAddress ADDR4 = address(HOST4, IP4);
    private static final InetAddress ADDR6 = address(HOST6, IP6);

    static final class DemoResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(
                String host, LookupPolicy policy)
                throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            int flags = policy.characteristics();
            List<InetAddress> candidates;

            if (HOST4.equalsIgnoreCase(host)) {
                candidates = List.of(ADDR4);
            } else if (HOST6.equalsIgnoreCase(host)) {
                candidates = List.of(ADDR6);
            } else {
                throw new UnknownHostException("Unknown host: " + host);
            }

            List<InetAddress> matching = candidates.stream()
                    .filter(ip ->
                            (ip instanceof Inet4Address
                                    && (flags & LookupPolicy.IPV4) != 0)
                            || (ip instanceof Inet6Address
                                    && (flags & LookupPolicy.IPV6) != 0))
                    .toList();

            if (matching.isEmpty()) {
                throw new UnknownHostException(
                        "No address matching policy for " + host);
            }

            return matching.stream();
        }

        @Override
        public String lookupByAddress(byte[] addr)
                throws UnknownHostException {
            Objects.requireNonNull(addr, "addr");

            if (addr.length != 4 && addr.length != 16) {
                throw new IllegalArgumentException(
                        "IP address must contain 4 or 16 bytes");
            }

            if (Arrays.equals(addr, IP4)) {
                return HOST4;
            }
            if (Arrays.equals(addr, IP6)) {
                return HOST6;
            }

            throw new UnknownHostException(
                    "No hostname for the supplied IP address");
        }
    }

    private static void testForward(
            DemoResolver resolver, String host, LookupPolicy policy) {
        try (Stream<InetAddress> result =
                     resolver.lookupByName(host, policy)) {
            System.out.println("Forward OK: "
                    + result.map(InetAddress::getHostAddress).toList());
        } catch (NullPointerException e) {
            System.out.println("Forward NPE: " + e.getMessage());
        } catch (UnknownHostException e) {
            System.out.println("Forward UnknownHostException: "
                    + e.getMessage());
        }
    }

    private static void testReverse(
            DemoResolver resolver, byte[] addr) {
        try {
            System.out.println("Reverse OK: "
                    + resolver.lookupByAddress(addr));
        } catch (NullPointerException e) {
            System.out.println("Reverse NPE: " + e.getMessage());
        } catch (IllegalArgumentException e) {
            System.out.println("Reverse IAE: " + e.getMessage());
        } catch (UnknownHostException e) {
            System.out.println("Reverse UnknownHostException: "
                    + e.getMessage());
        }
    }

    public static void main(String[] args) {
        DemoResolver resolver = new DemoResolver();
        LookupPolicy ipv4 = LookupPolicy.of(LookupPolicy.IPV4);
        LookupPolicy ipv6 = LookupPolicy.of(LookupPolicy.IPV6);

        // Forward: thành công.
        testForward(resolver, HOST4, ipv4);

        // Forward: đối số null.
        testForward(resolver, null, ipv4);

        // Forward: policy null.
        testForward(resolver, HOST4, null);

        // Forward: hostname không có trong bảng.
        testForward(resolver, "missing.lab.invalid", ipv4);

        // Forward: có hostname nhưng policy không chấp nhận họ IPv4.
        testForward(resolver, HOST4, ipv6);

        // Reverse: thành công.
        testReverse(resolver, IP4);

        // Reverse: null.
        testReverse(resolver, null);

        // Reverse: sai độ dài.
        testReverse(resolver, new byte[] {1, 2, 3});

        // Reverse: độ dài hợp lệ nhưng không có hostname.
        testReverse(resolver, new byte[] {(byte) 192, 0, 2, 99});
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~shell
javac ResolverErrorDemo.java
java ResolverErrorDemo
~~~

Kết quả có dạng:

~~~text
Forward OK: [192.0.2.10]
Forward NPE: host
Forward NPE: policy
Forward UnknownHostException: Unknown host: missing.lab.invalid
Forward UnknownHostException: No address matching policy for api.lab.invalid
Reverse OK: api.lab.invalid
Reverse NPE: addr
Reverse IAE: IP address must contain 4 or 16 bytes
Reverse UnknownHostException: No hostname for the supplied IP address
~~~

Kết quả cho thấy ba loại lỗi không thay thế cho nhau:

- `NullPointerException`: caller truyền thiếu đối số bắt buộc.
- `IllegalArgumentException`: địa chỉ raw có độ dài không phải 4 hoặc 16 byte.
- `UnknownHostException`: đầu vào có cấu trúc hợp lệ nhưng không tìm thấy kết quả phân giải.

Ví dụ gọi trực tiếp `DemoResolver`, nên kiểm chứng hợp đồng của implementation mà không phụ thuộc provider hoặc cache của `InetAddress`. Để JDK sử dụng resolver tùy biến trong toàn JVM, cần cung cấp nó qua `InetAddressResolverProvider` và đăng ký service theo JEP 418.

## 6. Bắt exception ở phía caller

Caller nên bắt đúng loại lỗi theo hành động tiếp theo:

~~~java
try {
    Stream<InetAddress> addresses =
            resolver.lookupByName(host, policy);
    // Tiêu thụ stream ở đây.
} catch (NullPointerException e) {
    // Sửa dữ liệu đầu vào hoặc lỗi gọi API.
} catch (UnknownHostException e) {
    // Báo không phân giải được; thử nguồn dự phòng nếu thiết kế cho phép.
}
~~~

Với reverse lookup:

~~~java
try {
    String host = resolver.lookupByAddress(rawAddress);
    System.out.println(host);
} catch (NullPointerException e) {
    // Đầu vào null: lỗi của caller.
} catch (IllegalArgumentException e) {
    // Độ dài raw IP sai: kiểm tra dữ liệu.
} catch (UnknownHostException e) {
    // IP hợp lệ nhưng không có hostname.
}
~~~

Trong thực tế, `NullPointerException` và `IllegalArgumentException` thường chỉ ra lỗi lập trình hoặc dữ liệu đầu vào; không nên tự động retry mạng với cùng dữ liệu. `UnknownHostException` có thể là kết quả bình thường khi tên không tồn tại, nhưng cũng có thể do nguồn phân giải tạm thời không khả dụng; chính sách retry phải dựa vào cause và loại nguồn dữ liệu, tránh retry vô hạn.

Không nên bắt `Exception` chung rồi trả `null` để caller tiếp tục. Cách đó xóa mất khác biệt giữa lỗi đầu vào, lookup không có kết quả và lỗi lập trình.

## 7. Checklist kiểm thử hợp đồng lỗi

| Phương thức | Đầu vào | Kết quả mong đợi |
|---|---|---|
| `lookupByName` | `host == null` | `NullPointerException` |
| `lookupByName` | `policy == null` | `NullPointerException` |
| `lookupByName` | Hostname không tồn tại | `UnknownHostException` |
| `lookupByName` | Hostname có IPv4 nhưng policy chỉ IPv6 | `UnknownHostException` |
| `lookupByName` | Hostname có địa chỉ phù hợp | Stream chứa địa chỉ theo policy |
| `lookupByAddress` | `addr == null` | `NullPointerException` |
| `lookupByAddress` | Mảng 0, 3, 5, 15 hoặc 17 byte | `IllegalArgumentException` |
| `lookupByAddress` | Mảng 4 byte có mapping | Trả hostname |
| `lookupByAddress` | Mảng 16 byte có mapping | Trả hostname |
| `lookupByAddress` | Mảng 4/16 byte không có mapping | `UnknownHostException` |

Nên kiểm tra cả IPv4 và IPv6, địa chỉ có mapping và không có mapping. Với mảng byte, đừng chỉ kiểm thử mảng 3 byte; hãy có cả độ dài 0, 5, 15 và 17 để chắc chắn ranh giới được kiểm tra đúng.

## 8. Những lỗi triển khai thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Trả `null` khi đối số null | Che giấu vi phạm hợp đồng. | Ném `NullPointerException`. |
| Ném `UnknownHostException` cho mảng sai độ dài | Nhầm lỗi cấu trúc với lỗi không tìm thấy hostname. | Ném `IllegalArgumentException`. |
| Trả `Stream.empty()` khi không có IP | Không báo lookup thất bại theo hợp đồng. | Ném `UnknownHostException`. |
| Trả chuỗi rỗng khi reverse lookup không có tên | Caller tưởng đã phân giải thành công. | Ném `UnknownHostException`. |
| Bắt mọi exception rồi trả giá trị mặc định | Mất nguyên nhân và khó phát hiện bug. | Giữ đúng loại exception và cause. |
| Gọi `InetAddress.getByName()` trong resolver để fallback | Có thể đệ quy về chính resolver. | Dùng `Configuration.builtinResolver()`. |
| Dùng hợp đồng `InetAddress.getByAddress` cho SPI | Hai API có exception khác nhau. | Đọc Javadoc đúng phương thức. |

## 9. Câu hỏi tự đánh giá

1. Vì sao `lookupByAddress(null)` phải ném `NullPointerException`, không phải `UnknownHostException`?
2. Mảng 3 byte và mảng 4 byte không có hostname phải tạo ra hai exception nào?
3. Nếu hostname có IPv4 nhưng policy chỉ yêu cầu IPv6, resolver nên trả stream rỗng hay ném exception?
4. Vì sao `InetAddress.getByAddress(new byte[] {1, 2, 3})` và `resolver.lookupByAddress(new byte[] {1, 2, 3})` có thể ném hai loại exception khác nhau?
5. Khi nguồn dữ liệu resolver bị lỗi kết nối, vì sao cần giữ cause trong `UnknownHostException`?
6. Khi nào caller nên retry `UnknownHostException`, và vì sao không nên retry `NullPointerException` hoặc `IllegalArgumentException`?

**Ghi nhớ:** Phân loại lỗi theo đúng hợp đồng: đối số `null` → `NullPointerException`; mảng reverse lookup không dài 4 hoặc 16 byte → `IllegalArgumentException`; không có kết quả phân giải phù hợp → `UnknownHostException`. Giữ nguyên khác biệt này giúp resolver dễ kiểm thử, caller xử lý đúng và lỗi nguồn dữ liệu có thể được chẩn đoán.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `InetAddressResolver` – hợp đồng lookup và exception](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 26: `InetAddress` – `getByAddress` và `UnknownHostException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html).
- [Java SE 26: `UnknownHostException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnknownHostException.html).
- [Java SE 26: `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html).
