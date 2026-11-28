# Dựng bảng ánh xạ hostname và IP xác định để kiểm thử không phụ thuộc DNS công cộng

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao kết quả phân giải hostname từ DNS thật làm bài kiểm thử thiếu ổn định.
2. Tạo bảng ánh xạ hostname → IP có dữ liệu đầu vào và kết quả kỳ vọng cố định.
3. Dùng `jdk.net.hosts.file` cho kiểm thử đơn giản; dùng `InetAddressResolverProvider` (JEP 418, từ Java 18) khi cần điều khiển chính xác hành vi resolver.
4. Kiểm tra tra cứu thuận, tra cứu ngược, IPv4/IPv6, trường hợp không tồn tại và ranh giới giữa phân giải tên với kết nối mạng.
5. Tổ chức mỗi bài kiểm thử trong môi trường biệt lập để tránh tác động của resolver toàn JVM và bộ nhớ đệm.

## 1. Vì sao cần một bảng phân giải xác định?

`InetAddress.getByName(host)` và `InetAddress.getAllByName(host)` chuyển tên máy thành địa chỉ IP. Với resolver mặc định, kết quả có thể phụ thuộc cấu hình máy, tệp hosts của hệ điều hành, DNS nội bộ, DNS công cộng, thay đổi bản ghi, trạng thái mạng và cache. Cùng một bài kiểm thử vì thế có thể đạt trên máy phát triển nhưng thất bại trong CI hoặc khi mất mạng.

Từ **Java 18**, [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418) cung cấp cơ chế mở rộng chuẩn trong `java.net.spi`: `InetAddressResolverProvider` tạo `InetAddressResolver` để JVM sử dụng thay cho resolver tích hợp. API này vẫn được hỗ trợ trên các JDK hiện đại. Đối với bài kiểm thử chỉ cần bảng hostname/IP, JDK cũng hỗ trợ thuộc tính `jdk.net.hosts.file` để chỉ định tệp hosts riêng cho tiến trình Java.

Mục tiêu là kiểm thử **hành vi phân giải tên**, không phải gửi lưu lượng đến một máy thật. Dùng tên `*.invalid` (miền dành riêng) và các dải IP dành cho tài liệu giúp tránh nhầm ví dụ với hệ thống đang hoạt động.

### Bộ dữ liệu cố định dùng xuyên suốt

| Hostname | IPv4 kỳ vọng | IPv6 kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- |
| `api.qa.invalid` | `192.0.2.10` | `2001:db8::10` | Có hai họ địa chỉ; dùng kiểm tra `LookupPolicy` |
| `db.qa.invalid` | `192.0.2.20` | Không có | Chỉ có IPv4 |
| `missing.qa.invalid` | Không có | Không có | Phải nhận `UnknownHostException` |

`192.0.2.0/24` là TEST-NET-1; `2001:db8::/32` là tiền tố IPv6 dùng cho tài liệu. **Không dùng các địa chỉ này để kiểm thử kết nối TCP/HTTP thành công.** Kiểm thử kết nối cần máy chủ test đang chạy, thường trên loopback hoặc môi trường mạng riêng.

Luồng cần kiểm soát:

```text
Mã kiểm thử
  |
  +--> InetAddress.getAllByName("api.qa.invalid")
          |
          +--> resolver của JVM
                  |
                  +--> bảng fixture -> [192.0.2.10, 2001:db8::10]
                  +--> không có tên -> UnknownHostException
```

## 2. Phương án A: sử dụng tệp hosts riêng cho JVM

Khi chỉ cần mô phỏng các ánh xạ tĩnh, thuộc tính `jdk.net.hosts.file` là cách triển khai gọn nhất. Nó dùng tệp do bài kiểm thử quản lý, không cần sửa `/etc/hosts` hoặc tệp hosts của Windows và không cần cài DNS server.

Tạo tệp `fixture.hosts`:

```text
# Cú pháp: IPAddress hostname [alias ...]
192.0.2.10 api.qa.invalid
192.0.2.20 db.qa.invalid
```

Ví dụ trên cố ý chỉ chứa IPv4 để kết quả kiểm thử tương đương trên nhiều môi trường. Có thể bổ sung dòng `2001:db8::10 api.qa.invalid` khi bài kiểm thử cần IPv6 và môi trường được cấu hình hỗ trợ.

Tạo `CheckHostsFile.java`:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;

public class CheckHostsFile {
    public static void main(String[] args) throws Exception {
        InetAddress[] found = InetAddress.getAllByName("api.qa.invalid");
        if (found.length != 1
                || !"192.0.2.10".equals(found[0].getHostAddress())) {
            throw new AssertionError("Sai IP cho api.qa.invalid");
        }

        try {
            InetAddress.getAllByName("missing.qa.invalid");
            throw new AssertionError("Hostname chưa khai báo phải thất bại");
        } catch (UnknownHostException expected) {
            System.out.println("PASS: không tìm thấy hostname ngoài fixture");
        }

        System.out.println("PASS: ánh xạ IPv4 xác định");
    }
}
```

Biên dịch bằng JDK 18 trở lên và chạy trong **tiến trình JVM mới**, với đường dẫn tuyệt đối đến tệp fixture:

```bash
javac CheckHostsFile.java
java -Djdk.net.hosts.file=/absolute/path/to/fixture.hosts CheckHostsFile
```

Trên PowerShell/Windows, thay tham số bằng đường dẫn thực tế, ví dụ: `"-Djdk.net.hosts.file=C:\test-data\fixture.hosts"`. Nếu đường dẫn có khoảng trắng, đặt toàn bộ tham số `-D...` trong dấu ngoặc kép.

Khi `jdk.net.hosts.file` được đặt, việc tìm tên của resolver tích hợp dùng nội dung tệp đã chỉ định; hostname không có trong tệp sẽ thất bại thay vì tự hỏi DNS công cộng. Nếu chỉ định tệp không tồn tại, JDK xem như tệp rỗng và việc tra cứu thất bại. Điều này rất hữu ích để xác minh các trường hợp âm tính có chủ đích.

**Giới hạn:** Một tệp hosts không thể tự lập trình quy tắc kiểm thử phức tạp, như giả lập riêng từng nhánh `LookupPolicy` hoặc ghi nhận số lần resolver được gọi. Khi cần mức điều khiển đó, dùng SPI ở phần tiếp theo.

## 3. Phương án B: xây resolver fixture bằng Java 18 SPI

### 3.1. Hợp đồng API cần nhớ

| API | Vai trò |
| --- | --- |
| `InetAddressResolverProvider` | Service provider có constructor không tham số; triển khai `name()` và `get(Configuration)`. |
| `InetAddressResolver.lookupByName(host, policy)` | Trả về `Stream<InetAddress>` của những địa chỉ khớp tên và chính sách họ địa chỉ/thứ tự, hoặc ném `UnknownHostException` nếu không có. |
| `InetAddressResolver.lookupByAddress(byte[])` | Tra cứu IP → hostname; xử lý mảng IPv4 (4 byte), IPv6 (16 byte) và tên không tìm thấy. |
| `InetAddressResolver.LookupPolicy` | Có cờ `IPV4`, `IPV6`, `IPV4_FIRST`, `IPV6_FIRST`, truy xuất qua `characteristics()`. |
| `InetAddress.getByAddress(host, bytes)` | Tạo đối tượng địa chỉ từ byte sẵn có **mà không xác minh bằng DNS**; thích hợp cho fixture. |
| `ServiceLoader` | Nạp provider được khai báo trong `META-INF/services` hoặc `module-info.java`. |

Đối với bài này, resolver **không chuyển tiếp tên chưa biết** đến `Configuration.builtinResolver()`. Việc chuyển tiếp như vậy sẽ khiến bài kiểm thử tiếp tục phụ thuộc cấu hình DNS của máy chạy.

### 3.2. Cấu trúc ví dụ

```text
src/
  main/
    java/
      demo/net/FixedResolverProvider.java
      demo/net/ResolverCheck.java
    resources/
      META-INF/services/java.net.spi.InetAddressResolverProvider
```

Tệp `src/main/java/demo/net/FixedResolverProvider.java`:

```java
package demo.net;

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

public final class FixedResolverProvider extends InetAddressResolverProvider {
    private static final String API = "api.qa.invalid";
    private static final String DB = "db.qa.invalid";

    private static final byte[] API_V4 = {(byte) 192, 0, 2, 10};
    private static final byte[] DB_V4 = {(byte) 192, 0, 2, 20};
    private static final byte[] API_V6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0x10
    };

    // ServiceLoader cần lớp provider công khai và constructor không tham số.
    public FixedResolverProvider() {}

    @Override
    public String name() {
        return "fixed-qa-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        // Cố ý không fallback về DNS thật.
        return fixture();
    }

    // Điểm vào để kiểm thử trực tiếp các trường hợp LookupPolicy.
    public static InetAddressResolver fixture() {
        return new FixedResolver();
    }

    private static final class FixedResolver implements InetAddressResolver {
        @Override
        public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
                throws UnknownHostException {
            Objects.requireNonNull(host, "host");
            Objects.requireNonNull(policy, "policy");

            int flags = policy.characteristics();
            List<InetAddress> addresses = new ArrayList<>(2);

            if (API.equalsIgnoreCase(host)) {
                if ((flags & LookupPolicy.IPV4) != 0) {
                    addresses.add(InetAddress.getByAddress(API, API_V4));
                }
                if ((flags & LookupPolicy.IPV6) != 0) {
                    addresses.add(InetAddress.getByAddress(API, API_V6));
                }
            } else if (DB.equalsIgnoreCase(host)) {
                if ((flags & LookupPolicy.IPV4) != 0) {
                    addresses.add(InetAddress.getByAddress(DB, DB_V4));
                }
            }

            // Không trả về Stream.empty() cho hostname không phân giải được.
            if (addresses.isEmpty()) {
                throw new UnknownHostException(host);
            }

            if ((flags & LookupPolicy.IPV6_FIRST) != 0) {
                addresses.sort((a, b) -> Integer.compare(
                        a.getAddress().length == 16 ? 0 : 1,
                        b.getAddress().length == 16 ? 0 : 1));
            }
            // Nếu IPV4_FIRST hoặc không quy định thứ tự:
            // fixture đang trả IPv4 trước, rồi IPv6.
            return addresses.stream();
        }

        @Override
        public String lookupByAddress(byte[] address)
                throws UnknownHostException {
            Objects.requireNonNull(address, "address");
            if (address.length != 4 && address.length != 16) {
                throw new IllegalArgumentException(
                        "Địa chỉ IP phải dài 4 hoặc 16 byte");
            }

            if (Arrays.equals(address, API_V4)
                    || Arrays.equals(address, API_V6)) {
                return API;
            }
            if (Arrays.equals(address, DB_V4)) {
                return DB;
            }
            throw new UnknownHostException(Arrays.toString(address));
        }
    }
}
```

Các lựa chọn trong mã có chủ đích:

- `API_V4`, `DB_V4`, `API_V6` chứa byte IP trực tiếp; không có lời gọi phân giải tên bên trong quá trình khởi tạo provider.
- Khi hostname khớp nhưng không có IP thuộc họ được yêu cầu (ví dụ `db.qa.invalid` với `IPV6`), resolver ném `UnknownHostException`.
- `IPV6_FIRST` đưa IPv6 lên đầu. Với `IPV4_FIRST`, thứ tự đã là IPv4 trước. Khi không có cờ thứ tự, hợp đồng cho phép thứ tự hệ thống; ví dụ chọn cố định IPv4 trước.
- `lookupByAddress` trả về hostname đã định nghĩa và từ chối địa chỉ không nằm trong bảng.
- `get(Configuration)` tạo resolver không dùng `builtinResolver()`, tránh việc hostname ngoài bảng vô tình ra DNS công cộng.

### 3.3. Đăng ký provider với ServiceLoader

Tạo tệp **không có đuôi mở rộng** `src/main/resources/META-INF/services/java.net.spi.InetAddressResolverProvider`, với đúng một dòng:

```text
demo.net.FixedResolverProvider
```

Tên tệp dịch vụ phải là tên đầy đủ của lớp SPI; nội dung phải là tên đầy đủ của lớp provider. Khi đóng gói thành JAR dùng classpath, tài nguyên này phải có trong JAR ở đường dẫn `META-INF/services/java.net.spi.InetAddressResolverProvider`. Nếu dùng module đặt tên, có thể đăng ký qua `provides java.net.spi.InetAddressResolverProvider with demo.net.FixedResolverProvider;` trong `module-info.java`.

### 3.4. Chương trình xác minh đầu cuối và chính sách IPv4/IPv6

Tệp `src/main/java/demo/net/ResolverCheck.java`:

```java
package demo.net;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.util.Arrays;

public final class ResolverCheck {
    public static void main(String[] args) throws Exception {
        // Kiểm thử đường đi thực: InetAddress -> provider qua ServiceLoader.
        InetAddress[] db = InetAddress.getAllByName("db.qa.invalid");
        if (db.length != 1
                || !"192.0.2.20".equals(db[0].getHostAddress())) {
            throw new AssertionError("Sai ánh xạ: " + Arrays.toString(db));
        }

        // Kiểm thử trực tiếp hợp đồng API để chủ động cấp LookupPolicy.
        InetAddressResolver resolver = FixedResolverProvider.fixture();
        var policy = InetAddressResolver.LookupPolicy.of(
                InetAddressResolver.LookupPolicy.IPV4
                | InetAddressResolver.LookupPolicy.IPV6
                | InetAddressResolver.LookupPolicy.IPV6_FIRST);
        var addresses = resolver.lookupByName("api.qa.invalid", policy).toList();
        if (addresses.size() != 2
                || !(addresses.get(0) instanceof Inet6Address)
                || !(addresses.get(1) instanceof Inet4Address)) {
            throw new AssertionError("Sai lọc/thứ tự IPv4 và IPv6");
        }

        // Reverse lookup: so sánh byte IP, không phụ thuộc cách viết IPv6.
        String reverse = resolver.lookupByAddress(
                new byte[] {(byte) 192, 0, 2, 10});
        if (!"api.qa.invalid".equals(reverse)) {
            throw new AssertionError("Sai hostname tra cứu ngược");
        }

        // Unknown hostname: phải từ chối, không chuyển sang DNS công cộng.
        try {
            InetAddress.getAllByName("missing.qa.invalid");
            throw new AssertionError("Thiếu UnknownHostException");
        } catch (UnknownHostException expected) {
            // Kết quả mong đợi.
        }

        System.out.println("PASS: provider, IPv4/IPv6, reverse, unknown host");
    }
}
```

Ví dụ lệnh chạy trên PowerShell từ thư mục dự án (có JDK 18 trở lên):

```powershell
javac --release 18 -d out src/main/java/demo/net/FixedResolverProvider.java src/main/java/demo/net/ResolverCheck.java
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
Copy-Item src/main/resources/META-INF/services/java.net.spi.InetAddressResolverProvider out/META-INF/services/
java -cp out demo.net.ResolverCheck
```

Với Bash/Linux/macOS, thay bước tạo thư mục/sao chép bằng `mkdir -p out/META-INF/services` và `cp src/main/resources/META-INF/services/java.net.spi.InetAddressResolverProvider out/META-INF/services/`. Khi dùng Maven/Gradle, tài nguyên `src/main/resources` được đóng gói vào classpath theo cấu hình build thông thường; vẫn phải kiểm tra service file có mặt trong đầu ra.

Kết quả mong đợi:

```text
PASS: provider, IPv4/IPv6, reverse, unknown host
```

Chạy lại trong JVM mới khi cần thay bảng fixture hoặc đổi provider. Không kết hợp đồng thời ví dụ `jdk.net.hosts.file` với custom provider trong cùng ca kiểm thử để tránh nhầm cơ chế đang được kiểm chứng.

## 4. Ma trận kiểm thử nên có

| Tình huống | Đầu vào | Kết quả phải kiểm tra |
| --- | --- | --- |
| Tra cứu thuận IPv4 | `db.qa.invalid`, cho phép `IPV4` | Chỉ có `192.0.2.20` |
| Tra cứu thuận hai họ | `api.qa.invalid`, `IPV4 \| IPV6` | Đúng hai địa chỉ, không thừa |
| Ưu tiên IPv6 | `api.qa.invalid`, `IPV4 \| IPV6 \| IPV6_FIRST` | IPv6 ở trước IPv4 |
| Chỉ IPv6 | `db.qa.invalid`, `IPV6` | `UnknownHostException` |
| Tra cứu ngược hợp lệ | Byte của `192.0.2.10` | `api.qa.invalid` |
| Tra cứu ngược không có | Byte của `192.0.2.99` | `UnknownHostException` |
| Byte IP sai độ dài | Mảng 3 byte | `IllegalArgumentException` |
| Hostname ngoài bảng | `missing.qa.invalid` | `UnknownHostException`, không fallback |
| Viết hoa/viết thường | `API.QA.INVALID` | Cùng ánh xạ với `api.qa.invalid` |
| Kiểm tra tích hợp SPI | `InetAddress.getAllByName("db.qa.invalid")` | Provider được nạp từ `ServiceLoader` |

Phân biệt hai kiểu kiểm thử: gọi thẳng `FixedResolverProvider.fixture().lookupByName(...)` kiểm tra thuật toán của resolver; gọi `InetAddress.getAllByName(...)` kiểm tra thêm việc JVM đã nạp đúng provider. Có thể kiểm thử chính sách IPv4/IPv6 trực tiếp vì API `InetAddress.getAllByName` tự dùng chính sách của JVM và không nhận `LookupPolicy` làm tham số.

## 5. Giữ bài kiểm thử ổn định trong CI

**Bộ nhớ đệm:** `InetAddress` có bộ nhớ đệm cho cả tra cứu thành công và thất bại. Kết quả cũ có thể tồn tại một thời gian tùy cấu hình JDK. Hãy dùng mỗi kịch bản cấu hình resolver trong một JVM độc lập và giữ bảng fixture bất biến trong suốt ca chạy; không dựa vào việc đổi file hosts hay thay map rồi tra cứu lại trong cùng tiến trình.

**Phạm vi JVM:** SPI chọn một resolver cấp toàn JVM khi phát sinh tra cứu đầu tiên sau giai đoạn khởi động. Việc thay `ClassLoader` ở giữa bài kiểm thử không bảo đảm thay resolver đang hoạt động. Nếu có nhiều provider, thứ tự provider được tìm thấy không được bảo đảm; môi trường test nên triển khai **một provider duy nhất**.

**Khởi tạo an toàn:** Constructor và phương thức `get` của provider cần đơn giản. Tránh gọi `InetAddress.getByName(...)` khi tạo provider vì có thể kích hoạt vòng tra cứu hoặc chu trình khởi tạo. `InetAddress.getByAddress(host, bytes)` tạo giá trị từ byte đã biết mà không cần DNS.

**Đúng lớp cần kiểm chứng:** `InetAddress.getByName("192.0.2.10")` nhận IP literal và không thực hiện hostname lookup như `InetAddress.getByName("api.qa.invalid")`. Khi mục tiêu là kiểm thử resolver, dùng hostname fixture. Lệnh `ping`/`nslookup` và trình duyệt riêng không nhất thiết dùng resolver SPI của JVM.

**Phân giải tên ≠ mở kết nối:** Kết quả `InetAddress` hợp lệ chỉ nói rằng map đã trả IP. Nó không chứng minh máy đích lắng nghe cổng, có TLS hợp lệ hay HTTP trả 200. Đối với bài kiểm thử kết nối, chạy server kiểm thử thực trên loopback hoặc môi trường biệt lập; đừng kết nối vào địa chỉ TEST-NET dùng trong tài liệu.

**Không rò rỉ ra môi trường ngoài:** Đừng sửa hosts của hệ điều hành hay dùng tên miền công khai có thể trỏ đến dịch vụ của người khác. Dùng `.invalid`, IP tài liệu, bảng fixture do test sở hữu và tiến trình JVM riêng; trường hợp không có trong bảng phải ném lỗi ngay.

## 6. Bài thực hành mở rộng

Bổ sung hostname `cache.qa.invalid` → `192.0.2.30` vào cả bảng dữ liệu và resolver. Sau đó:

1. Viết ca kiểm thử thuận cho `cache.qa.invalid`; đảo chữ hoa để kiểm tra quy tắc khớp không phân biệt hoa thường.
2. Viết ca kiểm thử ngược cho byte `{(byte) 192, 0, 2, 30}`.
3. Đảm bảo truy vấn `IPV6` cho hostname chỉ có IPv4 ném `UnknownHostException`.
4. Chạy toàn bộ test trên máy không có Internet hoặc CI bị chặn truy cập DNS công cộng; kết quả phân giải phải giống như khi có mạng.
5. Thử bỏ tệp `META-INF/services` khỏi classpath trong một tiến trình mới: ca kiểm thử tích hợp tra cứu `db.qa.invalid` sẽ không còn được provider fixture phục vụ. Từ đó phân biệt lỗi đăng ký SPI với lỗi logic của resolver.

**Tiêu chí hoàn thành:** Kết quả ánh xạ thuận/ngược và lỗi hostname không tồn tại là cố định; kiểm thử không truy cập DNS công cộng cho những tên đã khai báo; có ít nhất một ca xác nhận đường đi tích hợp qua `InetAddress`; và mọi kịch bản chạy được trên JDK 18 hoặc JDK mới hơn.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): thiết kế SPI được đưa vào Java 18.
- [Javadoc `InetAddressResolverProvider`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): nạp và chọn provider, vòng đời resolver.
- [Javadoc `InetAddressResolver` và `LookupPolicy`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng tra cứu thuận/ngược; [chi tiết `LookupPolicy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE Core Libraries – Java Networking](https://docs.oracle.com/en/java/javase/25/core/java-networking.html): `jdk.net.hosts.file` và cú pháp tệp hosts dùng trong kiểm thử.
- [Javadoc `InetAddress`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): phân giải tên và caching.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606), [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737), [RFC 3849](https://www.rfc-editor.org/rfc/rfc3849): tên miền và các dải IP dành cho kiểm thử, ví dụ, tài liệu.
