# InetAddressResolverProvider và cơ chế thay thế bộ phân giải theo phiên bản Java hỗ trợ

`InetAddressResolverProvider` là **SPI (Service Provider Interface) chuẩn từ Java 18, theo JEP 418**, cho phép ứng dụng cung cấp bộ phân giải tên máy và địa chỉ IP để `java.net.InetAddress` sử dụng ở **phạm vi toàn JVM**. Trước Java 18 không có SPI công khai tương đương để thay thế resolver toàn cục của `InetAddress`. Trên Java 9–17 có thể cấu hình một tệp `hosts` riêng qua `jdk.net.hosts.file` khi cần ánh xạ tên tĩnh; trên Java 8 thường dựa vào cấu hình hệ điều hành hoặc xử lý ánh xạ trong chính ứng dụng.

**Ý chính cần nắm:** đây là cách thay thế *name/address resolution* của `InetAddress`, không phải một API để đặt DNS server cho từng HTTP request; cũng không có nghĩa mọi thư viện networking hay DNS client sẽ tự động dùng provider này.

## 1. Đang thay thế khâu nào?

Một ứng dụng gọi `InetAddress.getByName("service.example.test")` hoặc `getAllByName(...)` để chuyển **hostname → một hoặc nhiều địa chỉ IPv4/IPv6** (forward lookup). Chiều **IP → hostname** là reverse lookup, ví dụ khi hỏi `getCanonicalHostName()`.

~~~text
Ứng dụng → InetAddress → cache tra cứu → resolver được chọn
                                      ├─ built-in resolver → cấu hình hệ điều hành, hosts, DNS, ...
                                      └─ custom InetAddressResolver → quy tắc ứng dụng / dịch vụ riêng
~~~

`InetAddress` không chỉ là một DNS client thuần túy: resolver mặc định có thể phối hợp `hosts`, cấu hình name-service của hệ điều hành và DNS hoặc các cơ chế tên khác. Ngay cả khi DNS trả được địa chỉ thì kết nối TCP, HTTPS, xác thực chứng chỉ TLS và chính sách proxy vẫn là các bước riêng.

Hai lời gọi cần phân biệt:

- `InetAddress.getByName(host)`: yêu cầu phân giải tên; có thể đi qua resolver và bộ nhớ đệm.
- `InetAddress.getByAddress(host, bytes)`: **tạo đối tượng InetAddress từ byte IP đã biết**, không hỏi DNS để tìm IP. Đây là cách an toàn để tạo kết quả ngay trong một custom resolver, tránh tự gọi ngược vào `getByName`.

## 2. Ma trận hỗ trợ theo phiên bản

| Dòng Java | Thay thế resolver của `InetAddress` bằng SPI chuẩn? | Cơ chế được hỗ trợ nên cân nhắc |
|---|---|---|
| **Java 8 và cũ hơn** | **Không** có `InetAddressResolverProvider` công khai | Cấu hình `hosts`/DNS ở hệ điều hành; ánh xạ tên trong logic hoặc thư viện của ứng dụng nếu cần |
| **Java 9–17**, bao gồm Java 11/17 LTS | **Không** có SPI này | Mặc định dùng resolver hệ thống; có thể đặt `-Djdk.net.hosts.file=...` để dùng tệp hosts riêng cho `InetAddress` |
| **Java 18 trở lên**, bao gồm Java 21/25 LTS | **Có**: `java.net.spi.InetAddressResolverProvider` và `InetAddressResolver` | Đăng ký provider qua `ServiceLoader` để thay thế resolver toàn JVM; hoặc dùng built-in/`jdk.net.hosts.file` cho bài toán đơn giản |

**Mốc dễ nhớ: Java 9 thêm `jdk.net.hosts.file`; Java 18 thêm SPI (JEP 418).** Java 9 cũng loại bỏ cơ chế name-service provider nội bộ cũ đã từng được tài liệu hóa ở các bản JDK trước đó. Đừng lấy ví dụ dùng `sun.net.spi.nameservice.*` hay `sun.net.spi.nameservice.provider.*` trên một JDK cũ làm giải pháp API ổn định cho Java 17 hoặc 21; đó không phải API Java SE công khai được bảo đảm hỗ trợ.

Nếu dự án biên dịch với `--release 17` hoặc chạy JDK 17, mã import `java.net.spi.InetAddressResolverProvider` sẽ **không biên dịch/chạy được**. Phần ví dụ SPI dưới đây yêu cầu **JDK 18+ cả lúc biên dịch lẫn lúc chạy**.

## 3. Cơ chế của SPI từ Java 18

Bộ SPI nằm trong module `java.base`, package `java.net.spi`, với bốn kiểu chính:

| Kiểu | Trách nhiệm |
|---|---|
| `InetAddressResolverProvider` | **Factory** cho custom resolver; là lớp abstract, yêu cầu provider triển khai cụ thể, có constructor không tham số |
| `InetAddressResolver` | Interface định nghĩa `lookupByName` và `lookupByAddress` |
| `InetAddressResolver.LookupPolicy` | Mô tả họ địa chỉ được yêu cầu (IPv4/IPv6) và thứ tự ưu tiên |
| `InetAddressResolverProvider.Configuration` | Cung cấp `builtinResolver()` để ủy quyền xử lý thông thường, và `lookupLocalHostName()` khi cần tên máy cục bộ |

### Khởi tạo và lựa chọn provider

1. Khi JVM đã khởi tạo đầy đủ và một lời gọi `InetAddress` cần phân giải lần đầu, JDK tìm implementation `InetAddressResolverProvider` qua `ServiceLoader` **bằng system class loader**.
2. Nếu thấy nhiều provider, **provider đầu tiên tìm được** sẽ được dùng; **thứ tự là implementation-specific**, không nên dựa vào tên provider hay thứ tự JAR.
3. JDK gọi `provider.get(configuration)`; đối tượng `InetAddressResolver` trả về trở thành **resolver chung của JVM** cho các lookup tiếp theo.
4. Nếu **không tìm thấy provider**, JDK dùng **built-in resolver**.
5. Nếu **tìm thấy provider nhưng việc khởi tạo ném lỗi/exception**, lỗi được truyền cho lời gọi khởi phát lookup; **đừng kỳ vọng tự động chuyển sang built-in**. Nếu một hostname riêng không được custom resolver xử lý, chính code của bạn cần tự delegate qua `configuration.builtinResolver()`.
6. Những lookup phát sinh **trước khi VM khởi động đầy đủ** có thể vẫn dùng built-in resolver theo ghi chú triển khai của JDK.

Provider thường được chọn **một lần theo vòng đời JVM**, không phải chọn lại sau mỗi request. Vì vậy đổi classpath, thêm service file hay sửa provider sau một lookup đã diễn ra sẽ không “hot swap” resolver của tiến trình hiện tại; dùng một JVM mới để kiểm tra.

### Hai hàm bắt buộc và lookup policy

~~~java
Stream<InetAddress> lookupByName(
    String host,
    InetAddressResolver.LookupPolicy policy
) throws UnknownHostException;

String lookupByAddress(byte[] addr) throws UnknownHostException;
~~~

- `lookupByName` nhận một **hostname** (không mặc định là địa chỉ IP dạng chuỗi) và trả về một `Stream<InetAddress>`. Nếu không có địa chỉ phù hợp, ném `UnknownHostException`.
- `lookupByAddress` nhận **4 byte IPv4 hoặc 16 byte IPv6** theo network byte order; trả lại tên host hoặc ném `UnknownHostException`.
- `LookupPolicy.characteristics()` là bit mask: `IPV4`, `IPV6` biểu thị họ địa chỉ cần tra; `IPV4_FIRST` và `IPV6_FIRST` biểu thị thứ tự khi có cả hai. Chẳng hạn policy chỉ cho IPv6 thì một resolver chỉ lưu bản ghi IPv4 **không được tự trả IPv4**.
- Với nhiều địa chỉ, custom resolver cần lọc và sắp thứ tự phù hợp policy. `IPV4_FIRST`/`IPV6_FIRST` có ý nghĩa khi đồng thời có cả hai họ; không có cờ ưu tiên thì tuân theo thứ tự hệ thống.

## 4. Ví dụ chạy được: thay thế một tên nội bộ, tên khác dùng resolver mặc định

Mục tiêu: trong JVM sử dụng provider, `service.example.test` trả về **192.0.2.44** và reverse lookup trả lại tên này. `192.0.2.0/24` là dải địa chỉ dành cho tài liệu, **không phải máy chủ Internet thực**. Các tên khác được chuyển cho built-in resolver; ví dụ không tự tạo DNS traffic và không cần Internet.

Cấu trúc dự án khi chạy theo **classpath**:

~~~text
resolver-demo/
├── src/
│   └── demo/
│       ├── StaticResolverProvider.java
│       └── ResolverDemo.java
└── resources/
    └── META-INF/
        └── services/
            └── java.net.spi.InetAddressResolverProvider
~~~

### 4.1. Triển khai provider

Tạo `src/demo/StaticResolverProvider.java`:

~~~java
package demo;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.stream.Stream;

public final class StaticResolverProvider extends InetAddressResolverProvider {
    private static final String HOST = "service.example.test";
    private static final byte[] IPV4 = {(byte) 192, 0, 2, 44};

    public StaticResolverProvider() {}

    @Override
    public String name() { return "static-demo"; }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, InetAddressResolver.LookupPolicy policy)
                    throws UnknownHostException {

                if (!HOST.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }
                if ((policy.characteristics()
                        & InetAddressResolver.LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException("No IPv4 requested: " + host);
                }
                return Stream.of(InetAddress.getByAddress(HOST, IPV4.clone()));
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                if (Arrays.equals(address, IPV4)) {
                    return HOST;
                }
                return builtin.lookupByAddress(address);
            }
        };
    }
}
~~~

**Giải thích các quyết định trong code:**

- `get(Configuration)` nhận sẵn `builtinResolver()` và giữ lại để fallback. Không gọi `InetAddress.getByName(...)` từ `lookupByName`, vì lời gọi đó thường quay vào chính resolver vừa cài, tạo **đệ quy vô hạn**.
- `InetAddress.getByAddress(HOST, IPV4.clone())` dựng địa chỉ từ byte có sẵn, **không thực hiện lookup forward**. Hàm có thể ném `UnknownHostException` nếu byte địa chỉ không hợp lệ.
- Với hostname khác tên demo, ví dụ chủ động gọi `builtin.lookupByName`. Không có fallback này thì một custom resolver chỉ biết một tên có thể làm hỏng rất nhiều lookup còn lại.
- Với host demo, chỉ hỗ trợ IPv4; nếu policy không yêu cầu IPv4 thì báo không tìm thấy thay vì trả về sai họ. Vì chỉ có đúng một IP nên ví dụ không cần xử lý sắp xếp danh sách IPv4/IPv6.
- `lookupByAddress` hỗ trợ reverse mapping của IP đã gán và ủy quyền cho built-in đối với địa chỉ khác. Reverse mapping không tự động chứng minh danh tính hoặc bảo mật.
- Provider có constructor `public` không tham số; việc khởi tạo nên rất nhẹ, không thực hiện network lookup trong constructor, static initializer hoặc `get` để tránh vòng lặp class loading/deadlock.

### 4.2. Đăng ký `ServiceLoader`

Nội dung tệp **`resources/META-INF/services/java.net.spi.InetAddressResolverProvider`** chỉ có một dòng:

~~~text
demo.StaticResolverProvider
~~~

Tên **tệp** là tên đầy đủ của SPI; **nội dung** là tên class provider đầy đủ theo package. Không thêm `.java`, `.class`, dấu ngoặc hoặc tên `InetAddressResolver` thay cho provider. Tệp cần có mặt trong **runtime classpath** (thường nằm trong JAR tại `META-INF/services/...`), không chỉ trong thư mục source.

### 4.3. Chương trình gọi `InetAddress`

Tạo `src/demo/ResolverDemo.java`:

~~~java
package demo;
import java.net.InetAddress;

public class ResolverDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("forward=" + InetAddress.getByName("service.example.test")
                .getHostAddress());
        byte[] ip = {(byte) 192, 0, 2, 44};
        System.out.println("reverse=" + InetAddress.getByAddress(ip)
                .getCanonicalHostName());
    }
}
~~~

Từ thư mục `resolver-demo` chạy trên macOS/Linux với **JDK 18+**:

~~~bash
javac --release 18 -d out src/demo/StaticResolverProvider.java src/demo/ResolverDemo.java
mkdir -p out/META-INF/services
cp resources/META-INF/services/java.net.spi.InetAddressResolverProvider out/META-INF/services/
java -cp out demo.ResolverDemo
~~~

Kết quả kiểm chứng được:

~~~text
forward=192.0.2.44
reverse=service.example.test
~~~

Mã trên đã được biên dịch bằng `javac --release 18` và chạy thử với **OpenJDK 24**. Bài thử reverse dùng `getCanonicalHostName()`, có thể yêu cầu đối chiếu ngược tên/IP: vì ví dụ cung cấp **cả forward lẫn reverse mapping nhất quán** nên trả được tên đã định nghĩa. Nếu chỉ dựng `InetAddress.getByAddress(HOST, IP)` rồi gọi `getHostName()`, bạn có thể chỉ nhận tên lưu sẵn mà chưa kiểm tra thật sự reverse resolver.

**Trên Windows PowerShell**, thay hai lệnh tạo/sao chép thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services
Copy-Item resources/META-INF/services/java.net.spi.InetAddressResolverProvider out/META-INF/services/
~~~

Hai lệnh `javac` và `java` vẫn giữ nguyên; chú ý chạy từ thư mục gốc của ví dụ. Dùng JAR thì cần đóng gói file service vào JAR và đặt JAR đó trên system classpath.

### 4.4. Dự án dùng Java Platform Module System (JPMS)

Nếu triển khai provider dưới dạng **named module**, dùng chỉ thị `provides` trong `module-info.java` thay cho cách mô tả classpath ở trên:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with demo.StaticResolverProvider;
}
~~~

Đây là **trích đoạn khai báo module**, không phải chương trình độc lập. Khi chạy, cần giải quyết module vào module graph (chẳng hạn qua cấu hình `--module-path` và `--add-modules demo.resolver` phù hợp bản đóng gói). Đừng giả định chỉ đặt một JAR trên module path là luôn đủ để provider được khám phá. Không phụ thuộc một provider khác đứng trước theo thứ tự tùy ý.

## 5. Khi chưa có SPI: giải pháp cho Java 9–17

Từ **JDK 9**, thuộc tính hệ thống `jdk.net.hosts.file` chỉ định một tệp hosts riêng cho việc ánh xạ host/IP của `InetAddress`. Cơ chế này phù hợp **test hoặc ánh xạ tĩnh hữu hạn**, không thay thế một resolver DNS động, không đưa ra chính sách theo request và không yêu cầu viết provider Java.

Ví dụ file `hosts-demo.txt`:

~~~text
192.0.2.44 service.example.test
~~~

Ví dụ Java 9+ `ResolveHost.java`:

~~~java
import java.net.InetAddress;

public class ResolveHost {
    public static void main(String[] args) throws Exception {
        System.out.println(
            InetAddress.getByName("service.example.test").getHostAddress()
        );
    }
}
~~~

Biên dịch/chạy với **JDK 9 trở lên**, kể cả Java 11/17:

~~~bash
javac ResolveHost.java
java -Djdk.net.hosts.file=hosts-demo.txt ResolveHost
~~~

Kết quả với file ở trên:

~~~text
192.0.2.44
~~~

**Cần hiểu giới hạn của tệp hosts riêng:**

- Thuộc tính này được giới thiệu ở **JDK 9**; không đưa nó thành giải pháp hỗ trợ chuẩn cho Java 8.
- Trong cấu hình dựa trên built-in, khi đã chỉ định tệp riêng, những lookup thông thường lấy ánh xạ từ **tệp đó**; không coi đây là bảng “chỉ override vài tên rồi tự động hỏi DNS cho mọi tên còn lại”. Nếu file thiếu tên cần dùng, có thể nhận `UnknownHostException`.
- Nếu đường dẫn trỏ đến tệp **không tồn tại**, JDK coi như tệp rỗng và lookup không thành công, chứ không tự bỏ qua cấu hình để dùng DNS mặc định.
- Phải đặt `-D...` **trước tên class chính** (hoặc trong cấu hình khởi động JVM); dùng đường dẫn tuyệt đối khi chạy từ CI/container để tránh phụ thuộc working directory.
- Không thay toàn bộ DNS của hệ điều hành và không bắt buộc các công cụ như `nslookup`/`dig` hay những DNS client chuyên biệt phải dùng file của JVM.
- Khi kiểm thử độc lập, không đồng thời cài một provider SPI khác rồi suy diễn kết quả thành hiệu quả riêng của `jdk.net.hosts.file`: chính provider mới quyết định khi nào gọi `builtinResolver()`.

**Java 8:** bạn có thể cấu hình máy chạy/container để resolver mặc định nhận mapping từ tệp hosts hệ thống (đường dẫn khác nhau theo OS), cấu hình DNS hệ thống hoặc cung cấp sẵn IP trong tầng ứng dụng. Không có một công tắc Java SE 8 chuẩn tương đương `InetAddressResolverProvider` để chèn một provider toàn JVM. Các API nội bộ `sun.*` và thủ thuật sửa bootclasspath dễ hỏng khi nâng cấp JDK.

## 6. Cache, vòng đời và giới hạn phạm vi

### Cache của `InetAddress`

`InetAddress` lưu cache lookup thành công lẫn thất bại. Java có hai **security property** liên quan:

- `networkaddress.cache.ttl`: TTL (giây) cho kết quả thành công; `-1` biểu thị giữ vô hạn.
- `networkaddress.cache.negative.ttl`: TTL cho kết quả thất bại; `0` là không cache, `-1` là cache vô hạn.

Giá trị mặc định và điều kiện bảo mật có thể khác theo JDK/cấu hình; không nên khẳng định một TTL dương cố định cho mọi phiên bản. Đây là **Java security properties**, không mặc nhiên tương đương với mọi `-Dnetworkaddress.cache.ttl=...` trên dòng lệnh. Hãy cấu hình bằng cơ chế Java security properties được JDK của bạn hỗ trợ và kiểm chứng trên runtime đang dùng.

Một mapping vừa đổi có thể chưa xuất hiện do **cache**, dù provider đã được cài đúng. Với test đơn giản, khởi động JVM mới, dùng hostname mới và tránh lẫn kết quả cũ/negative cache. Nếu resolver tự lưu cache riêng, còn phải xét cache của chính nó.

### Tác động toàn JVM, nhưng không toàn bộ mạng

- Provider phục vụ luồng phân giải được gọi qua `java.net.InetAddress`; nó **không sửa cấu hình DNS của hệ điều hành**.
- Không suy ra tất cả thư viện HTTP, database driver hay client DNS đều chắc chắn đi qua SPI: code nào sử dụng resolver riêng, địa chỉ IP có sẵn, proxy hay API native có thể đi theo đường khác.
- Provider **không** thay đổi quy tắc phân giải CNAME/A/AAAA của DNS một cách tự động; nếu muốn truy vấn bản ghi DNS cụ thể, phải tự triển khai hoặc gọi thư viện phù hợp trong resolver.
- Giả mạo hostname → IP có thể khiến ứng dụng kết nối sai endpoint. HTTPS vẫn có xác thực danh tính và SNI theo quy tắc riêng; thay IP trong resolver không tự vô hiệu hóa kiểm tra chứng chỉ.
- Lookup có thể đến từ nhiều thread; implementation cần **thread-safe**, có timeout hợp lý và tránh I/O chặn không giới hạn. Nếu provider đóng gói trong thư viện chung, phải cân nhắc ảnh hưởng tới toàn bộ tiến trình.
- Provider có thể không được gọi cho IP literal như `192.0.2.44` hoặc `::1`: đây là dữ liệu địa chỉ đã biết, không nhất thiết là hostname cần phân giải.

## 7. Chẩn đoán tình huống thường gặp

| Triệu chứng | Kiểm tra | Hướng xử lý |
|---|---|---|
| `javac` báo không thấy `InetAddressResolverProvider` | `java -version` / `javac -version` có phải JDK 18+? Có đang dùng `--release 17`? | Chọn JDK 18+ để dùng SPI; trên 17 dùng cách phù hợp phiên bản |
| Demo chạy nhưng host không nhận IP custom | Kiểm tra chính xác path `META-INF/services/java.net.spi.InetAddressResolverProvider`, class name, constructor, runtime classpath | Đóng gói lại service file; chạy JVM mới |
| Có nhiều provider trong runtime | Thứ tự lựa chọn không được bảo đảm | Chỉ triển khai provider chủ đích; quản lý dependency/JAR chứa SPI |
| Lookup bỗng gây `StackOverflowError` | Provider có gọi `InetAddress.getByName` từ `lookupByName`? | Trả `getByAddress` cho IP tĩnh; dùng `builtinResolver()` cho fallback |
| Chỉ truy vấn IPv6 mà nhận IPv4 | Resolver bỏ qua `LookupPolicy` | Lọc theo `IPV4`/`IPV6` và bảo đảm thứ tự |
| Reverse lookup không ra hostname mong muốn | Có cài `lookupByAddress`? Forward mapping có khớp? | Trả về hostname nhất quán và kiểm tra cả hai chiều |
| Host khác tên custom bị lỗi | Code không delegate khi không nhận ra host | Dùng `configuration.builtinResolver()` |
| Sửa hosts/resolver mà ứng dụng vẫn thấy IP cũ | Cache `InetAddress`, resolver riêng hoặc JVM đã chọn provider trước đó | Kiểm tra TTL, tái khởi động JVM thử nghiệm |
| Cài `jdk.net.hosts.file` nhưng tên khác đều thất bại | Tệp không chứa đủ tên hoặc path sai | Bổ sung mapping hoặc bỏ cờ để dùng resolver hệ thống |
| `nslookup`/`dig` khác kết quả `InetAddress` | Hai công cụ dùng cơ chế khác, hoặc khác cache/cấu hình | Test chính bằng chương trình Java trên đúng JVM |

### Thứ tự debug tối thiểu

1. In version JDK được dùng **lúc chạy**, không chỉ compiler hoặc biến môi trường của IDE.
2. Xác minh file service có **nằm trong artifact thực thi** và loader hệ thống nhìn thấy provider.
3. Test hostname riêng, ví dụ `service.example.test`, bằng `InetAddress.getByName` trong **JVM mới**.
4. Nếu có reverse mapping, test riêng chiều IP → hostname; để ý việc xác minh forward trong `getCanonicalHostName`.
5. Test một host không custom để xác nhận `builtinResolver()` làm fallback theo đúng chủ đích.
6. Xem cache, policy IPv4/IPv6 và resolver riêng của framework nếu kết quả vẫn khác mong đợi.

## 8. Chọn giải pháp cho đúng bài toán

| Nhu cầu | Cách phù hợp |
|---|---|
| Kiểm thử một vài hostname tĩnh, dự án Java 9–17 | `jdk.net.hosts.file`; chạy JVM mới cho từng case |
| Kiểm thử một vài hostname tĩnh, Java 8 | Tệp hosts/configuration hệ điều hành hoặc ánh xạ ở tầng ứng dụng |
| Thay toàn bộ resolver phía `InetAddress` bằng quy tắc nội bộ khi dùng Java 18+ | `InetAddressResolverProvider` và service registration, đồng thời định nghĩa fallback |
| Chỉ một HTTP client cần DNS tùy biến, các client khác không đổi | Xem API và resolver riêng của HTTP client/thư viện đó; SPI toàn JVM có thể quá rộng |
| Ứng dụng cần truy vấn trực tiếp bản ghi DNS (MX, TXT, SRV...) | Dùng thư viện DNS hoặc API chuyên biệt; `InetAddressResolver` chủ yếu phục vụ hostname/IP và reverse |
| Muốn đổi resolver khi chương trình đang chạy | SPI không cung cấp public hot-swap; thiết kế một resolver cố định có thể đọc cấu hình động nội bộ, chú ý cache và đồng bộ |

**Ghi nhớ:** `InetAddressResolverProvider` là cơ chế **thay resolver của `InetAddress` bằng ServiceLoader từ Java 18**, không phải tính năng sẵn có trong Java 17. Trong provider, `lookupByName` và `lookupByAddress` xử lý hai chiều; `LookupPolicy` ràng buộc họ địa chỉ; `Configuration.builtinResolver()` cho phép fallback an toàn; kiểm tra cache và khởi động JVM mới khi thử nghiệm.

## Tài liệu chính thức

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 18 – InetAddressResolverProvider](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 18 – InetAddressResolver](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolver.html).
- [Java SE 18 – InetAddressResolver.LookupPolicy](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html).
- [Java SE 18 – InetAddressResolverProvider.Configuration](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html).
- [Java SE 18 – Networking properties và hosts file](https://docs.oracle.com/en/java/javase/18/core/java-networking.html).
- [JDK 9 Release Notes – giới thiệu jdk.net.hosts.file](https://www.oracle.com/java/technologies/javase/9-relnotes.html).
- [Java SE 17 – InetAddress và cache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html).
