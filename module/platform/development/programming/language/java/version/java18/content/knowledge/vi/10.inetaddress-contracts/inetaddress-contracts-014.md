# Tên miền đổi địa chỉ, vòng đời JVM và tác động của cache đến khả năng quan sát

> **Chương:** Hợp đồng `InetAddress` — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học giải thích vì sao hostname đã đổi IP trên DNS vẫn có thể trả địa chỉ cũ hoặc tiếp tục ném `UnknownHostException` trong một JVM đang chạy. Trọng tâm là phân biệt các lớp cache, hiểu phạm vi theo vòng đời tiến trình và thiết kế phép thử có bộ đếm để biết lookup có thực sự đi tới resolver hay không. Nội dung dùng API còn được hỗ trợ trên JDK hiện đại.

Giả sử `api.example.test` ban đầu trỏ tới `192.0.2.10`. Sau một lần triển khai, bản ghi DNS được đổi thành `192.0.2.20`. Lệnh tra cứu DNS ở terminal đã thấy địa chỉ mới, nhưng ứng dụng Java vẫn kết nối tới địa chỉ cũ. Một trường hợp khác: hostname trước đó chưa tồn tại, ứng dụng nhận `UnknownHostException`; DNS sau đó đã được sửa, nhưng cùng JVM vẫn tiếp tục nhận lỗi.

Hai hiện tượng này có thể xảy ra vì kết quả phân giải tên được cache ở nhiều lớp. Cache của `InetAddress` sống trong tiến trình JVM; cache của hệ điều hành, recursive resolver, DNS server hoặc thư viện mạng có vòng đời và chính sách riêng. Muốn giải thích đúng, phải biết lần lookup hiện tại dừng ở lớp nào.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đường đi của một hostname lookup qua các lớp cache.
2. Phân biệt TTL của bản ghi DNS với positive/negative TTL của `InetAddress`.
3. Giải thích vì sao một JVM có thể giữ IP cũ hoặc lỗi `UnknownHostException` sau khi DNS thay đổi.
4. Phân biệt cache trong JVM với cache của OS, recursive resolver và resolver provider tùy biến.
5. Hiểu vai trò của lần lookup đầu tiên và vòng đời resolver instance trong JVM.
6. Dùng `InetAddressResolverProvider` để tạo fixture có thể thay đổi dữ liệu và đếm số lần resolver được gọi.
7. Thiết kế phép thử với hai JVM để phân biệt cache theo tiến trình.
8. Chẩn đoán production mà không suy luận chỉ từ timing hoặc lệnh DNS chạy ở terminal.

## 2. Một hostname đổi địa chỉ trong lúc JVM đang chạy

Xét trình tự sau:

```text
T0  DNS: api.example.test -> 192.0.2.10
T1  JVM-A gọi InetAddress.getAllByName("api.example.test")
T2  JVM-A nhận 192.0.2.10 và giữ positive cache entry
T3  DNS authoritative đổi bản ghi thành 192.0.2.20
T4  dig/nslookup ở một máy hoặc resolver đã thấy 192.0.2.20
T5  JVM-A gọi lại InetAddress.getAllByName(...)
T6  JVM-A vẫn có thể trả 192.0.2.10 từ cache trong tiến trình
T7  Khi entry JVM hết hạn, lookup mới mới có cơ hội đi tới resolver bên dưới
```

Việc DNS authoritative đã cập nhật ở T3 không đồng nghĩa mọi cache đã cập nhật đồng thời. Ở T5, Java có thể chưa gọi resolver thêm lần nào. Ở T7, JVM có thể gọi resolver, nhưng resolver hệ điều hành hoặc recursive DNS vẫn còn bản ghi cũ.

`192.0.2.0/24` là dải IPv4 dành cho tài liệu. Địa chỉ trong ví dụ chỉ minh họa quá trình thay đổi, không phải endpoint Internet có thể kết nối.

### 2.1. Hostname chưa tồn tại rồi được tạo

Negative cache tạo ra tình huống tương tự:

```text
T0  missing.example.test chưa có bản ghi phù hợp
T1  JVM gọi lookup và nhận UnknownHostException
T2  Kết quả thất bại được lưu trong negative cache
T3  Quản trị viên tạo bản ghi DNS cho hostname
T4  Một lookup lặp lại trong JVM có thể vẫn nhận UnknownHostException
T5  Sau khi negative entry hết hạn, lookup mới có cơ hội hỏi resolver lại
```

Do đó, lỗi lookup vừa xảy ra không chứng minh hostname hiện tại vẫn không tồn tại. Lỗi có thể phản ánh trạng thái ở thời điểm lần phân giải trước.

## 3. Những lớp cache cần phân biệt

Một đường phân giải tên điển hình có thể gồm nhiều lớp sau. Không phải môi trường nào cũng có đủ mọi lớp, và thứ tự cụ thể còn phụ thuộc JDK, hệ điều hành, cấu hình resolver và provider.

| Lớp | Phạm vi/vòng đời | Dữ liệu có thể được giữ |
|---|---|---|
| DNS authoritative | Theo zone và bản ghi DNS | Bản ghi A/AAAA và TTL được công bố |
| Recursive DNS resolver | Dùng chung cho nhiều client | Câu trả lời DNS đã cache theo TTL và chính sách resolver |
| OS/native resolver | Theo máy, container hoặc network namespace | Kết quả từ DNS, hosts file, local resolver hoặc dịch vụ hệ điều hành |
| `InetAddress` JVM cache | Một tiến trình JVM | Kết quả phân giải thành công và thất bại |
| Custom resolver/provider cache | Do ứng dụng/provider thiết kế | Dữ liệu riêng trong bộ nhớ, file, Redis hoặc dịch vụ ngoài |
| HTTP client/connection pool | Theo thư viện và client instance | Endpoint đã phân giải, kết nối TCP/TLS đang mở hoặc route đã chọn |

### 3.1. DNS authoritative record TTL

TTL trong resource record cho biết resolver có thể cache câu trả lời DNS trong bao lâu theo chính sách DNS. TTL này thuộc dữ liệu DNS được công bố từ zone; nó không phải TTL của cache `InetAddress`.

Khi bản ghi được thay đổi, resolver recursive có thể tiếp tục dùng câu trả lời cũ cho đến khi TTL cũ hết hạn. Chính sách serve-stale hoặc cache nội bộ của resolver cũng có thể ảnh hưởng thời điểm câu trả lời mới được nhìn thấy.

### 3.2. Recursive resolver cache

Recursive resolver thường được nhiều ứng dụng hoặc máy khách dùng chung. Một JVM mới vẫn có thể nhận IP cũ nếu recursive resolver mà nó hỏi còn cache câu trả lời cũ.

Lệnh tra cứu terminal có thể hỏi một DNS server khác, dùng resolver khác, hoặc chạy ở máy/network namespace khác. Vì vậy, kết quả mới từ terminal không chứng minh resolver mà tiến trình Java thực sự sử dụng đã thấy cùng dữ liệu.

### 3.3. OS/native resolver cache

Resolver mặc định của JDK có thể kết hợp thông tin cấu hình cục bộ với naming service của hệ điều hành, ví dụ hosts file và DNS. Cấu hình cụ thể phụ thuộc nền tảng.

Một số hệ điều hành hoặc dịch vụ local DNS có cache; một số đường phân giải không giữ cache riêng ở lớp này. Hãy kiểm tra môi trường thật thay vì giả định mọi hệ điều hành có cùng một native cache.

### 3.4. InetAddress JVM cache

`InetAddress` cache kết quả phân giải tên thành công và thất bại vì hiệu năng và chính sách bảo mật. Cache này nằm trong tiến trình JVM, nên các lời gọi lặp lại trong cùng JVM có thể không đi tới resolver nữa.

Hai security properties liên quan là:

- `networkaddress.cache.ttl`: positive cache cho lookup thành công.
- `networkaddress.cache.negative.ttl`: negative cache cho lookup thất bại.

Đây là bối cảnh cần biết để hiểu ví dụ. Quy tắc giá trị, mặc định theo JDK và cách cấu hình chi tiết đã được trình bày ở các bài về TTL và security properties; không nên nhầm các khóa này với system properties truyền trực tiếp bằng `-Dnetworkaddress.cache.*`.

### 3.5. Cache của custom resolver/provider

Từ Java 18, ứng dụng có thể cài `InetAddressResolverProvider` để thay resolver mặc định. Provider được cài làm system-wide resolver của JVM; provider có thể tự giữ cache trong bộ nhớ hoặc gọi một dịch vụ ngoài có cache riêng.

Khi đó, một lookup mới từ `InetAddress` chưa chắc tạo truy vấn DNS mới. Nó chỉ có thể gọi provider; provider vẫn có thể trả dữ liệu cũ từ cache riêng của nó. Nếu provider delegate sang resolver built-in, các lớp OS/DNS bên dưới tiếp tục có ảnh hưởng.

### 3.6. Cache trong HTTP client và kết nối đang mở

Không phải mọi request HTTP đều gọi lại `InetAddress`. Client có thể đã tạo connection pool, giữ socket TCP/TLS tới IP cũ và tái sử dụng kết nối đó. Một số thư viện hoặc service mesh cũng có cache endpoint riêng.

Vì vậy, thấy request vẫn đi tới IP cũ không nhất thiết có nghĩa `InetAddress` vừa trả lại IP cũ. Cần phân biệt một lần phân giải mới với việc tái sử dụng kết nối đã mở.

## 4. Positive cache và negative cache ảnh hưởng điều gì?

| Kết quả lần lookup trước | Thay đổi xảy ra sau đó | Quan sát có thể thấy trong cùng JVM |
|---|---|---|
| Thành công với IP cũ | DNS đổi sang IP mới | Tiếp tục nhận IP cũ cho tới khi positive entry hết hạn hoặc bị thay thế |
| Thất bại với `UnknownHostException` | Hostname được tạo hoặc DNS được sửa | Tiếp tục nhận lỗi đã cache trong thời gian negative cache |
| Thành công với IP cũ | Resolver bên dưới đã có IP mới | JVM có thể chưa hỏi resolver nên chưa thấy địa chỉ mới |
| Entry JVM hết hạn | Resolver bên dưới vẫn cache IP cũ | Lookup mới vẫn có thể trả IP cũ |
| Entry JVM hết hạn | Resolver/provider trả IP mới | JVM có thể cache kết quả mới cho những lần sau |

Hết hạn một entry ở JVM chỉ mở cơ hội thực hiện lookup mới. Nó không buộc DNS authoritative, recursive resolver, OS hoặc provider phải trả dữ liệu mới.

### 4.1. Hai TTL là hai chính sách độc lập

Positive cache giữ kết quả thành công. Negative cache giữ kết quả thất bại. Một hệ thống có thể cần positive TTL tương đối dài cho hostname ổn định nhưng negative TTL ngắn hơn để tên mới được thử lại sớm.

Không đặt TTL bằng 0 chỉ để buộc mọi request đi qua DNS. Việc đó có thể tăng số lần gọi resolver, tăng độ trễ và tạo tải đột biến. Cũng không dùng negative cache vô hạn cho hostname có thể xuất hiện sau khi service khởi động.

### 4.2. Stale result trên JDK hỗ trợ

Một số JDK hiện đại có thêm chính sách giữ stale positive result khi refresh thất bại. Đây là hành vi phụ thuộc phiên bản JDK và security property tương ứng; không giả định tính năng này thuộc baseline Java 18. Khi chẩn đoán, hãy kiểm tra tài liệu đúng JDK đang chạy để biết stale entry có thể được trả trong tình huống resolver lỗi hay không.

## 5. Vòng đời JVM và lần lookup đầu tiên

`InetAddress` cache là trạng thái trong bộ nhớ của tiến trình. Khi một JVM đã tra cứu hostname, kết quả có thể được dùng lại trong các lần gọi tiếp theo trong suốt thời gian entry còn hiệu lực.

### 5.1. Resolver provider được cài đặt khi nào?

Theo API `InetAddressResolverProvider`, mỗi lần chạy JVM duy trì một system-wide resolver instance được `InetAddress` sử dụng. Resolver instance này được thiết lập sau khi VM khởi tạo xong và khi một phương thức của `InetAddress` kích hoạt lần lookup đầu tiên.

JDK tìm provider bằng `ServiceLoader` với system class loader. Nếu không tìm thấy provider phù hợp, JDK dùng resolver built-in. Thứ tự provider được tìm thấy là implementation-specific; nếu ứng dụng đóng gói nhiều provider, hãy kiểm soát classpath/module path và xác minh provider nào thực sự được chọn.

### 5.2. Resolver instance và cache entry có vòng đời khác nhau

- Resolver provider/system-wide resolver instance tồn tại trong phạm vi một lần chạy JVM.
- Positive/negative cache entry được tạo theo từng kết quả lookup và chính sách TTL.
- Cache riêng do provider tự triển khai có vòng đời do provider quyết định.
- Connection pool hoặc socket do HTTP client quản lý có vòng đời riêng với cache của `InetAddress`.

Một lần lookup mới sau khi cache entry hết hạn có thể gọi lại resolver instance đang cài trong JVM. Điều đó không đồng nghĩa provider được tạo lại.

### 5.3. Cấu hình trước khi lookup

Các security properties điều khiển positive/negative cache cần được cấu hình trước khi cơ chế cache sử dụng chúng. Với resolver provider, việc cài đặt system-wide resolver cũng gắn với lần lookup đầu tiên sau khi VM khởi tạo.

Nếu dependency thực hiện lookup sớm trong bootstrap, đoạn cấu hình chạy muộn trong `main` có thể không tạo ra thí nghiệm như dự định. Khi cần so sánh policy, hãy cấu hình lúc khởi động và dùng JVM mới cho từng kịch bản.

## 6. Thí nghiệm có kiểm soát bằng custom resolver

Để tách cache JVM khỏi DNS/OS cache, có thể tạo một `InetAddressResolverProvider` thử nghiệm. Resolver dưới đây chỉ xử lý hostname `switch.test` bằng một file mapping, đọc file ở mỗi lần provider được gọi và ghi một dòng vào file counter. Các hostname khác được chuyển cho resolver built-in.

Cách làm này giúp quan sát chính xác provider có được gọi lại hay không. Đây là fixture dành cho môi trường học tập/test; không dùng resolver file-backed này làm resolver production.

### 6.1. Cấu trúc thư mục

```text
inetaddress-cache-lab/
  src/
    demo/
      FileBackedResolverProvider.java
      ResolveFixture.java
  out/
  mapping.txt
  calls.log
  address-cache.security
```

Tạo `mapping.txt` với nội dung ban đầu:

```text
192.0.2.10
```

Tạo `address-cache.security`:

```properties
networkaddress.cache.ttl=300
networkaddress.cache.negative.ttl=20
```

Các con số trong fixture chỉ nhằm giữ cache đủ lâu cho phép thử. Hãy dùng giá trị phù hợp trong môi trường thử nghiệm của bạn; chúng không phải khuyến nghị cấu hình production.

### 6.2. Provider đọc mapping và đếm lần lookup

Tạo `src/demo/FileBackedResolverProvider.java`:

```java
package demo;

import java.io.IOException;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public final class FileBackedResolverProvider
        extends InetAddressResolverProvider {

    @Override
    public String name() {
        return "file-backed-cache-lab";
    }

    @Override
    public InetAddressResolver get(
            InetAddressResolverProvider.Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, InetAddressResolver.LookupPolicy lookupPolicy)
                    throws UnknownHostException {

                if (!"switch.test".equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, lookupPolicy);
                }

                try {
                    recordLookup(host);

                    if ((lookupPolicy.characteristics()
                            & InetAddressResolver.LookupPolicy.IPV4) == 0) {
                        throw new UnknownHostException(
                                "Fixture supports IPv4 lookups only");
                    }

                    String value = Files.readString(
                            requiredPath("demo.mapping"),
                            StandardCharsets.UTF_8).trim();

                    if ("FAIL".equalsIgnoreCase(value)) {
                        throw new UnknownHostException(
                                "Fixture marks " + host + " as unavailable");
                    }

                    byte[] addressBytes = parseIpv4(value);
                    InetAddress address =
                            InetAddress.getByAddress(host, addressBytes);

                    return Stream.of(address);
                } catch (UnknownHostException e) {
                    throw e;
                } catch (IOException | IllegalArgumentException e) {
                    UnknownHostException failure =
                            new UnknownHostException(
                                    "Fixture resolver failed for " + host);
                    failure.initCause(e);
                    throw failure;
                }
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                return builtin.lookupByAddress(address);
            }
        };
    }

    private static Path requiredPath(String property) throws IOException {
        String value = System.getProperty(property);
        if (value == null || value.isBlank()) {
            throw new IOException("Missing system property: " + property);
        }
        return Path.of(value);
    }

    private static void recordLookup(String host) throws IOException {
        Files.writeString(
                requiredPath("demo.counter"),
                host + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND);
    }

    private static byte[] parseIpv4(String value) {
        String[] parts = value.split("\\.", -1);
        if (parts.length != 4) {
            throw new IllegalArgumentException("Expected IPv4 address");
        }

        byte[] result = new byte[4];
        for (int i = 0; i < parts.length; i++) {
            int octet = Integer.parseInt(parts[i]);
            if (octet < 0 || octet > 255) {
                throw new IllegalArgumentException("Invalid IPv4 octet");
            }
            result[i] = (byte) octet;
        }
        return result;
    }
}
```

Provider không gọi `InetAddress.getByName` để phân tích địa chỉ IPv4, vì thao tác đó sẽ quay lại resolver và làm sai thí nghiệm. `InetAddress.getByAddress` tạo đối tượng từ các byte đã biết mà không cần phân giải hostname.

### 6.3. Chương trình gọi lookup hai lần trong cùng JVM

Tạo `src/demo/ResolveFixture.java`:

```java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ResolveFixture {
    public static void main(String[] args) throws Exception {
        lookup("Lần 1");

        System.out.println(
                "Hãy đổi mapping.txt sang 192.0.2.20, "
                + "sau đó nhấn Enter tại terminal này.");
        new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8))
                .readLine();

        lookup("Lần 2 trong cùng JVM");
    }

    private static void lookup(String label) {
        try {
            InetAddress[] addresses =
                    InetAddress.getAllByName("switch.test");
            System.out.println(label + ": " + Arrays.toString(addresses));
        } catch (UnknownHostException e) {
            System.out.println(label + ": UnknownHostException");
        }
    }
}
```

### 6.4. Đăng ký service provider

Sau khi biên dịch, tạo file service descriptor:

```text
out/META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung file chỉ có tên lớp provider:

```text
demo.FileBackedResolverProvider
```

JDK dùng `ServiceLoader` để tìm provider qua system class loader. Đảm bảo file descriptor nằm đúng trong classpath output và không có provider khác đứng trước trong môi trường thử nghiệm.

### 6.5. Biên dịch và chạy

Từ thư mục `inetaddress-cache-lab`, biên dịch hai lớp:

```powershell
javac -d out src/demo/FileBackedResolverProvider.java src/demo/ResolveFixture.java
New-Item -ItemType Directory -Force out/META-INF/services
Set-Content -Encoding ascii out/META-INF/services/java.net.spi.InetAddressResolverProvider 'demo.FileBackedResolverProvider'
```

Khởi chạy bằng JDK 18 trở lên. Thay đường dẫn file security properties bằng đường dẫn tuyệt đối trên máy:

```text
java -cp out -Djava.security.properties=file:/absolute/path/address-cache.security -Ddemo.mapping=./mapping.txt -Ddemo.counter=./calls.log demo.ResolveFixture
```

Trên Windows, dùng file URI hợp lệ cho security properties, ví dụ `file:///C:/path/to/address-cache.security`. Hai thuộc tính `demo.mapping` và `demo.counter` là system properties riêng của fixture; chúng không phải cấu hình TTL của `InetAddress`.

### 6.6. Quan sát hai tiến trình

**Tiến trình JVM-A**

1. Đặt `mapping.txt` là `192.0.2.10`.
2. Xóa `calls.log` nếu file còn từ lần chạy trước.
3. Khởi chạy JVM-A.
4. Lần 1 trả về `192.0.2.10`; `calls.log` có một dòng `switch.test`.
5. Trong khi chương trình đang chờ Enter, đổi `mapping.txt` thành `192.0.2.20`.
6. Nhấn Enter để thực hiện lần 2 trong cùng JVM-A.
7. Lần 2 vẫn có thể trả `192.0.2.10` và `calls.log` vẫn chỉ có một dòng.

Trong fixture này, provider không có cache riêng và luôn đọc file khi được gọi. Counter không tăng ở lần 2 cho thấy lookup đã được trả từ cache `InetAddress` của JVM-A; provider không được gọi lại.

**Tiến trình JVM-B**

1. Để `mapping.txt` ở giá trị `192.0.2.20`.
2. Khởi chạy một JVM-B mới với cùng classpath và tham số cấu hình.
3. Lần lookup đầu của JVM-B trả về `192.0.2.20`.
4. `calls.log` tăng thêm một dòng vì JVM-B có cache `InetAddress` mới và phải gọi provider.

Kết quả mong đợi:

| Quan sát | JVM-A | JVM-B |
|---|---|---|
| Mapping lúc lookup đầu | `192.0.2.10` | `192.0.2.20` |
| Kết quả lookup lặp | Vẫn `192.0.2.10` | Theo mapping `192.0.2.20` |
| Số lần provider được gọi trong tiến trình | Một lần nếu entry còn hạn | Một lần cho lookup đầu |
| Cache `InetAddress` | Được giữ trong JVM-A | Bắt đầu rỗng trong JVM-B |

Thí nghiệm này cố ý thay mapping file trong khi tiến trình còn sống. Nó cô lập cache JVM vì custom provider đọc file cục bộ, không truy vấn DNS hoặc OS resolver cho hostname fixture.

### 6.7. Biến thể kiểm tra negative cache

Để quan sát `UnknownHostException` đã cache:

1. Ghi `FAIL` vào `mapping.txt`.
2. Khởi chạy một JVM mới với negative TTL đủ dài cho thời gian thử nghiệm.
3. Lookup đầu tiên ném `UnknownHostException` và provider counter tăng một dòng.
4. Khi chương trình đang chờ, đổi `mapping.txt` thành `192.0.2.20`.
5. Thực hiện lookup lần hai trong cùng JVM và trước khi negative TTL hết hạn.
6. Nếu JVM vẫn ném `UnknownHostException` và counter không tăng, negative cache JVM đang giữ kết quả thất bại.
7. Khởi chạy JVM mới; lookup đầu có thể trả `192.0.2.20`.

Nếu muốn thử thời điểm entry hết hạn, chờ lâu hơn TTL đã cấu hình rồi gọi lại trong cùng tiến trình. Provider counter cần tăng khi resolver được gọi lại. Dùng thời gian chờ có biên an toàn và ghi timestamp; không kết luận chỉ từ một phép đo sát ranh giới hết hạn.

## 7. Thí nghiệm với DNS thật: cần kiểm soát nhiều hơn

Custom provider fixture ở mục trước cô lập được cache JVM. Khi thử trên DNS thật, cần ghi nhận cả resolver và network namespace mà tiến trình sử dụng.

Một kịch bản DNS thật có thể làm như sau:

1. Tạo hostname thử nghiệm thuộc zone bạn quản lý.
2. Đặt A/AAAA record ban đầu và ghi TTL của bản ghi.
3. Chạy một ứng dụng Java tối giản để lookup hostname và ghi địa chỉ, thời gian, PID.
4. Đổi bản ghi DNS authoritative.
5. Kiểm tra câu trả lời từ recursive resolver mà ứng dụng sử dụng, từ OS resolver trên cùng máy/container và từ terminal.
6. Lặp `InetAddress.getAllByName` trong cùng JVM, đồng thời ghi nhận kết quả.
7. Chờ positive TTL JVM và các TTL ở lớp DNS/resolver liên quan; thực hiện lookup lại.
8. Khởi chạy JVM mới và so sánh kết quả, nhưng tiếp tục kiểm tra recursive/OS cache nếu địa chỉ vẫn cũ.

Không dùng hostname của bên thứ ba làm fixture thay đổi vì bạn không kiểm soát được TTL, DNS provider, CDN, load balancer hoặc resolver policy.

## 8. Fresh JVM reset điều gì và không reset điều gì?

Khởi động JVM mới là cách đơn giản để có trạng thái cache `InetAddress` mới, nhưng không phải lệnh xóa toàn bộ cache DNS trên máy hoặc mạng.

| Trạng thái | Khi JVM cũ kết thúc và JVM mới bắt đầu |
|---|---|
| Positive/negative cache trong `InetAddress` của JVM cũ | Được giải phóng cùng tiến trình cũ |
| System-wide resolver instance của JVM cũ | Kết thúc cùng tiến trình cũ |
| Cache provider chỉ nằm trong heap JVM cũ | Kết thúc cùng tiến trình cũ |
| Mapping file hoặc counter file bên ngoài | Vẫn còn |
| Cache OS/native resolver | Có thể vẫn còn |
| Cache recursive DNS resolver | Vẫn còn cho tới khi resolver hết hạn hoặc làm mới theo chính sách |
| DNS authoritative record | Không bị ảnh hưởng bởi restart JVM |
| Cache/connection pool ở một tiến trình khác | Không bị ảnh hưởng |
| Socket đang mở ở một tiến trình khác | Không bị ảnh hưởng |

Trong fixture file-backed ở mục 6, JVM mới thấy mapping mới vì nó khởi tạo cache `InetAddress` mới và gọi provider để đọc file. Với resolver built-in trên DNS thật, JVM mới vẫn có thể nhận IP cũ nếu OS hoặc recursive resolver chưa cập nhật.

## 9. Vì sao terminal và ứng dụng Java có thể thấy khác nhau?

Lệnh `dig`, `nslookup` hoặc công cụ tương tự thường thực hiện truy vấn qua resolver mà công cụ được cấu hình sử dụng. Chúng không đọc cache trong heap của một JVM đang chạy.

Do đó:

- Terminal thấy IP mới nhưng Java còn IP cũ: có thể là positive cache trong JVM.
- JVM mới vẫn thấy IP cũ: có thể do OS/native resolver hoặc recursive resolver.
- Provider counter tăng nhưng vẫn trả IP cũ: provider hoặc lớp resolver bên dưới vẫn đang trả dữ liệu cũ.
- Provider counter không tăng trong fixture không có cache riêng: lookup được phục vụ trước khi provider được gọi, ví dụ từ cache `InetAddress`.
- Java lookup đã có IP mới nhưng HTTP request vẫn tới server cũ: có thể client tái sử dụng socket hoặc connection pool đã kết nối tới IP cũ.

Không dùng kết quả của một lệnh terminal để khẳng định chính xác trạng thái mọi lớp cache của ứng dụng.

## 10. Chẩn đoán production

Khi ứng dụng vẫn kết nối tới IP cũ hoặc tiếp tục báo `UnknownHostException` sau một thay đổi DNS, hãy kiểm tra theo thứ tự:

1. **Xác định tiến trình:** ghi PID, JDK vendor, runtime version, container/network namespace và thời điểm process bắt đầu.
2. **Xác định địa chỉ ứng dụng thực sự dùng:** log hostname, danh sách `InetAddress` được trả về, remote address của socket và thời điểm lookup.
3. **Kiểm tra connection pool:** xác định client có tạo lookup mới hay đang tái sử dụng socket TCP/TLS đã mở.
4. **Kiểm tra JVM cache policy:** đọc security properties của đúng tiến trình và đối chiếu cấu hình positive/negative TTL đã triển khai.
5. **Kiểm tra provider:** nếu dùng `InetAddressResolverProvider`, ghi tên provider, số lần `lookupByName` được gọi và cache riêng của provider.
6. **Kiểm tra OS resolver:** chạy công cụ chẩn đoán trong cùng máy/container/network namespace với ứng dụng.
7. **Kiểm tra recursive DNS:** truy vấn đúng resolver mà môi trường ứng dụng sử dụng và ghi TTL/câu trả lời.
8. **Kiểm tra authoritative DNS:** xác nhận bản ghi đã được cập nhật ở zone có thẩm quyền.
9. **Lặp lại sau khi cache hết hạn:** phân biệt entry hết hạn ở JVM với thời điểm cache ở resolver bên dưới hết hạn.
10. **So sánh JVM mới:** chỉ xem đây là phép thử reset cache trong tiến trình; không coi đó là bằng chứng OS/DNS cache đã sạch.

### 10.1. Dấu hiệu và giả thuyết

| Dấu hiệu | Giả thuyết cần kiểm tra |
|---|---|
| Cùng JVM luôn trả IP cũ, provider counter không tăng | Positive cache JVM còn hiệu lực |
| Cùng JVM tiếp tục ném lỗi sau khi DNS được sửa | Negative cache JVM còn hiệu lực |
| Provider được gọi lại nhưng IP vẫn cũ | Provider, OS resolver hoặc recursive resolver vẫn có dữ liệu cũ |
| JVM mới vẫn trả IP cũ | Cache ngoài tiến trình hoặc dữ liệu DNS chưa hội tụ |
| `InetAddress` trả IP mới nhưng request đi IP cũ | Connection pool/socket cũ hoặc cache riêng của HTTP client |
| Terminal thấy IP mới, ứng dụng không thấy | Terminal và JVM có thể dùng đường resolver/cache khác nhau |

### 10.2. Ghi log hữu ích

Một bản ghi chẩn đoán có thể lưu:

```text
timestamp:
process_id:
java_vendor:
java_runtime_version:
hostname:
lookup_api:
resolved_addresses:
remote_socket_address:
resolver_provider:
lookup_counter:
positive_cache_policy_source:
negative_cache_policy_source:
network_namespace:
```

Không ghi mật khẩu, token hoặc thông tin nhạy cảm của ứng dụng vào log. Khi ghi nhận địa chỉ IP, lưu kèm hostname và thời gian để có thể so sánh với thay đổi DNS.

## 11. Restart, TTL và rollout khi DNS thay đổi

Restart JVM có thể làm mất cache `InetAddress` của tiến trình đó và tạo resolver instance mới. Tuy nhiên, restart cũng tạo cold start, đóng kết nối hiện tại, khởi tạo lại pool và có thể làm nhiều instance đồng thời gửi lookup/kết nối mới.

Với hệ thống production:

- Nếu cần chuyển endpoint có kế hoạch, xem xét TTL của DNS và positive cache JVM trước thời điểm chuyển đổi.
- Không giả định giảm DNS record TTL sẽ tự giảm positive TTL của `InetAddress`; đây là hai chính sách khác nhau.
- Nếu thay đổi security property, cấu hình trước khi JVM khởi động theo quy trình triển khai đã kiểm chứng.
- Nếu cần restart, dùng rolling restart, readiness/health check và giới hạn số instance khởi động lại đồng thời.
- Kiểm tra connection pool và thời gian sống của socket; DNS refresh không tự chuyển một TCP connection đã mở sang IP mới.
- Theo dõi số lượng lookup, lỗi resolver và tải DNS sau khi thay đổi TTL; TTL quá ngắn có thể làm tăng lưu lượng lookup.
- Nếu provider có cache riêng, phải có cơ chế invalidation/TTL của provider hoặc thay đổi dữ liệu nguồn; restart JVM chỉ reset phần cache nằm trong tiến trình.

Không restart toàn bộ fleet chỉ dựa trên một lần `nslookup` hoặc một quan sát timing. Trước tiên xác định lớp cache nào đang giữ kết quả cũ và phạm vi instance bị ảnh hưởng.

## 12. Các kết luận sai thường gặp

| Kết luận vội | Vì sao chưa đủ bằng chứng |
|---|---|
| “DNS đã đổi nên Java phải thấy IP mới ngay” | JVM, OS và recursive resolver có cache độc lập |
| “dig trả IP mới nên JVM không thể trả IP cũ” | dig không đọc cache trong heap JVM |
| “Restart JVM xóa toàn bộ DNS cache” | Restart chỉ reset trạng thái trong tiến trình; OS/recursive resolver vẫn có thể cache |
| “Gọi getByName nhiều lần sẽ hỏi DNS nhiều lần” | Positive/negative cache có thể trả kết quả mà không gọi resolver |
| “Lần gọi thứ hai nhanh hơn chứng minh cache JVM hit” | OS cache, recursive resolver, JIT và tải hệ thống cũng ảnh hưởng timing |
| “Provider không ghi log nghĩa là DNS server không nhận query” | Có thể lookup được phục vụ từ cache JVM hoặc provider cache trước khi gửi DNS |
| “InetAddress trả IP mới nghĩa HTTP request đã đi IP mới” | HTTP client có thể tái sử dụng socket hoặc connection pool cũ |
| “JVM mới luôn thấy DNS mới” | Resolver ngoài tiến trình có thể chưa hết hạn cache |

## 13. Bài tập tự kiểm tra

1. Vì sao JVM có thể tiếp tục trả IP cũ sau khi DNS authoritative đã thay đổi?
2. TTL của DNS record khác positive TTL của `InetAddress` như thế nào?
3. Negative cache giải thích ra sao việc một hostname vừa được tạo nhưng JVM vẫn ném `UnknownHostException`?
4. Nếu JVM cache entry hết hạn nhưng recursive resolver vẫn giữ IP cũ, kết quả tiếp theo có thể là gì?
5. Vì sao một JVM mới có resolver instance mới nhưng vẫn có thể nhận IP cũ?
6. `InetAddressResolverProvider` được cài vào JVM khi nào và có bao nhiêu system-wide resolver instance trong một lần chạy JVM?
7. Trong fixture file-backed, vì sao counter không tăng ở lần lookup thứ hai trong cùng JVM?
8. Vì sao phải dùng hai tiến trình để phân biệt cache trong JVM cũ với cache của tiến trình mới?
9. Nếu provider counter tăng nhưng IP vẫn cũ, cần kiểm tra những lớp nào?
10. Nếu `InetAddress` trả IP mới nhưng HTTP request vẫn đi IP cũ, cần kiểm tra thành phần nào?
11. Vì sao timing đơn lẻ không chứng minh cache hit?
12. Khi rollout DNS change, cần cân nhắc gì trước khi restart nhiều JVM cùng lúc?

**Tiêu chí hoàn thành:** Bạn vẽ được đường đi qua các lớp cache, giải thích được IP cũ và lỗi âm trong cùng JVM, phân biệt được reset của JVM với cache bên ngoài tiến trình, và dùng fixture có counter để chứng minh lúc nào resolver thực sự được gọi.

## 14. Tài liệu chuẩn

- [InetAddress — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): cache kết quả phân giải thành công/thất bại và vai trò của resolver.
- [Networking Properties — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html): positive/negative cache và các security properties điều khiển TTL.
- [InetAddressResolver — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng lookup hostname/IP và việc `InetAddress` ủy quyền lookup cho system-wide resolver.
- [InetAddressResolverProvider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): ServiceLoader, thời điểm cài resolver instance và phạm vi một JVM.
- [InetAddressResolverProvider.Configuration — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html): cách provider truy cập built-in resolver để delegate khi cần.
- [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): resolver SPI được bổ sung trong Java 18.
- [RFC 1035 — Domain Names: Implementation and Specification](https://www.rfc-editor.org/rfc/rfc1035): cấu trúc resource record và trường TTL của DNS.
- [RFC 2181 — Clarifications to the DNS Specification](https://www.rfc-editor.org/rfc/rfc2181): làm rõ ngữ nghĩa TTL của DNS resource records.
