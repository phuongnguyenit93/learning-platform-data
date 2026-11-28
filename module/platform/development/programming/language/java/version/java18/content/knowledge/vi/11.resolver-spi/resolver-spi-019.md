# Phạm vi SPI đồng bộ: trách nhiệm timeout của provider và giới hạn đối với thư viện có resolver riêng

> **Chương:** Resolver SPI  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Hiểu giới hạn đồng bộ của `InetAddressResolver` từ JEP 418; xác định bên nào chịu trách nhiệm giới hạn thời gian DNS lookup, retry và hủy yêu cầu; phân biệt ứng dụng dùng `InetAddress` với thư viện tự thực hiện phân giải tên. Thiết kế kiểm thử và vận hành resolver có kiểm soát trên JDK hiện đại.

## 1. Vấn đề thực tế: ứng dụng gọi DNS nhưng bị chờ quá lâu

Một ứng dụng thường chuyển hostname như `api.example.test` thành địa chỉ IP trước khi mở kết nối TCP hoặc gửi request. DNS có thể phản hồi chậm, không phản hồi hoặc bị ảnh hưởng bởi cấu hình mạng, nameserver, bộ nhớ đệm và cơ chế retry.

Từ Java 18, JEP 418 bổ sung SPI công khai trong `java.net.spi`, giúp ứng dụng có thể cung cấp một resolver thay cho resolver có sẵn mà `java.net.InetAddress` sử dụng. Đây vẫn là API có ích trên JDK hiện đại.

Tuy nhiên, cần phân biệt ba nhu cầu:

- **Định tuyến phân giải tên:** `InetAddress` nên hỏi nguồn dữ liệu/resolver nào?
- **Giới hạn thời gian:** mỗi lần tìm địa chỉ được phép chiếm bao nhiêu thời gian?
- **Độ bao phủ:** mọi thư viện trong cùng JVM có thực sự đi qua `InetAddress` hay không?

SPI giải quyết nhu cầu lựa chọn resolver cho đường đi qua `InetAddress`. Nó không tự tạo một hệ thống DNS bất đồng bộ có deadline chung cho mọi thư viện.

Bài tập trung vào hợp đồng còn áp dụng; không dùng các hook DNS nội bộ `sun.*`, package `jdk.internal.*` hoặc workaround legacy như một phương án thiết kế.

## 2. Các thành phần Java SE của JEP 418

Những API sau thuộc module `java.base` và có từ Java 18:

| Thành phần | Vai trò |
|---|---|
| `java.net.spi.InetAddressResolverProvider` | Service provider tạo resolver tùy biến |
| `java.net.spi.InetAddressResolver` | Giao diện tra cứu hostname ↔ IP |
| `InetAddressResolver.LookupPolicy` | Yêu cầu họ địa chỉ IPv4/IPv6 và thứ tự |
| `InetAddressResolverProvider.Configuration` | Cung cấp resolver tích hợp và tên máy cục bộ |
| `java.net.InetAddress` | API ứng dụng thường gọi để phân giải tên |

Provider là một factory; resolver là đối tượng thực thi lookup. JVM duy trì một resolver toàn hệ thống cho các thao tác `InetAddress` sau khi môi trường được khởi tạo đầy đủ.

Cơ chế discovery là `ServiceLoader` dùng system class loader. Nếu có nhiều provider, thứ tự provider được tìm thấy là chi tiết phụ thuộc implementation; provider đầu tiên được chọn. Nếu không tìm thấy provider, resolver tích hợp được dùng. Nếu khởi tạo provider đã được chọn ném lỗi, lỗi được truyền ra từ lookup kích hoạt quá trình khởi tạo; không mặc nhiên chuyển sang provider khác.

**Hệ quả:** đây không phải cơ chế để mỗi lời gọi `InetAddress.getByName()` tự chọn provider khác nhau theo request. Nếu cần quyết định riêng cho từng client/request, thiết kế thêm lớp abstraction ở ứng dụng hoặc sử dụng API của client tương ứng.

### 2.1. Provider chỉ được chọn khi có lookup thực sự

Tài liệu API mô tả resolver hệ thống được cài đặt khi JVM đã khởi tạo đầy đủ và một lời gọi `InetAddress` kích hoạt lần tra cứu tên đầu tiên. Việc provider được load muộn có nghĩa:

- Một lời gọi quá sớm trong quá trình bootstrap có thể dùng resolver tích hợp.
- Provider được chọn cho JVM không tự thay đổi khi cấu hình mạng/JAR đổi giữa lúc tiến trình đang chạy.
- Để kiểm tra hai cấu hình provider độc lập, nên khởi chạy **hai JVM riêng**.
- Quá trình khởi tạo provider nên đơn giản; tránh lookup vòng tròn và thao tác gây deadlock.

## 3. Hợp đồng InetAddressResolver là giao diện đồng bộ

Hai phương thức trung tâm:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.util.stream.Stream;

interface ResolverShape extends InetAddressResolver {
    @Override
    Stream<InetAddress> lookupByName(
            String host,
            InetAddressResolver.LookupPolicy lookupPolicy)
            throws UnknownHostException;

    @Override
    String lookupByAddress(byte[] addr)
            throws UnknownHostException;
}
~~~

`ResolverShape` chỉ minh họa chữ ký để tiện đọc; trong dự án thật bạn triển khai trực tiếp `InetAddressResolver`.

Cần quan sát:

1. Cả hai phương thức trả kết quả trực tiếp hoặc ném lỗi; không trả `CompletableFuture` hay `CompletionStage`.
2. Chữ ký **không có** tham số `Duration`, `timeoutMillis` hoặc `deadline`.
3. `lookupByName` nhận hostname và chính sách IPv4/IPv6, trả `Stream<InetAddress>`.
4. `lookupByAddress` nhận mảng byte IP, trả tên hostname cho reverse lookup.
5. `UnknownHostException` là lỗi checked được khai báo khi không tìm được ánh xạ.

`Stream<InetAddress>` không làm API này trở thành giao diện DNS async. Stream là cách biểu diễn tập kết quả; nó có thể được tạo/tiêu thụ theo cách lazy. Provider không nên giấu network I/O chưa kiểm soát bên trong các thao tác stream khiến nơi tiêu thụ kết quả bị block khó dự đoán.

Trong lối dùng thông thường `InetAddress.getAllByName(host)`, caller gọi một API đồng bộ và có thể phải chờ lookup kết thúc. Nếu resolver bị block, thread gọi có thể bị giữ trong suốt thời gian đó.

## 4. Đường đi của một yêu cầu tra cứu tên

Sơ đồ khái quát:

~~~text
Code ứng dụng
    |
    +-- InetAddress.getByName(host)
    |       InetAddress.getAllByName(host)
    |               |
    |          Kiểm tra cache/đường tắt hợp lệ
    |               |
    |          Resolver hệ thống của InetAddress
    |               |
    |       +-------+--------+
    |       |                |
    |  Custom provider   Built-in resolver
    |       |                |
    |   Network/hosts/   OS/network naming
    |   backend riêng    configuration
    |       |                |
    |       +-------+--------+
    |               |
    |       IP hoặc UnknownHostException
    |
    +-- Thư viện tự gửi DNS packet/DoH
            |
          Resolver riêng của thư viện
            |
          Không nhất thiết đi qua InetAddress SPI
~~~

Sơ đồ mang tính kiến trúc. Các chi tiết cache, chuẩn hóa tên, xử lý literal IP hoặc bootstrap có thể khiến một lời gọi ứng dụng **không** tạo một lời gọi `lookupByName` mới. Không viết assertion yêu cầu provider được gọi đúng một lần mỗi khi ứng dụng gọi `InetAddress.getByName`.

### 4.1. Phạm vi các lời gọi InetAddress

Những API đáng kiểm tra:

~~~java
InetAddress.getByName("fixture.test");
InetAddress.getAllByName("fixture.test");
address.getCanonicalHostName();
~~~

Hai lệnh đầu có thể kích hoạt forward lookup. `getCanonicalHostName()` có thể kích hoạt reverse lookup, kèm kiểm tra lại ánh xạ tùy tình huống. Không giả định chỉ có đúng một lời gọi reverse hoặc forward phía dưới.

Một object `InetAddress` được tạo trực tiếp từ IP literal/binary address có thể không cần DNS. Chẳng hạn:

~~~java
InetAddress address = InetAddress.getByAddress(
        new byte[] {(byte) 127, 0, 0, 1});
~~~

Lệnh này tạo đối tượng từ byte địa chỉ và không phân giải hostname bằng resolver. Dùng nó khi cần fixture IP cố định mà không muốn bài kiểm thử phụ thuộc DNS thật.

## 5. Không có timeout API-level trong SPI

Chữ ký `lookupByName(host, lookupPolicy)` và `lookupByAddress(addr)` không mang một timeout do caller truyền vào. `LookupPolicy` nói về **loại địa chỉ và thứ tự**, không phải độ dài tối đa của network request.

Do đó, một provider sử dụng network backend cần tự có chính sách riêng, ví dụ:

- Timeout cho mỗi network attempt.
- Tổng ngân sách thời gian (overall deadline) cho cả lần lookup.
- Số lần retry tối đa.
- Backoff có giới hạn.
- Nhiều DNS server và chiến lược chuyển server.
- Cách xử lý khi bị interrupt/cancel.
- Quy tắc map kết quả không thành công thành `UnknownHostException`.
- Theo dõi latency và trạng thái lỗi để điều tra.

Điều này là **trách nhiệm thiết kế và vận hành của provider**, không phải một đảm bảo tự động mà `InetAddressResolverProvider` áp đặt.

Nếu provider dùng `configuration.builtinResolver()` để delegate, thời gian hoàn thành phụ thuộc resolver tích hợp và cấu hình tên của OS/JDK. Chỉ bọc một resolver không có deadline trong một lớp Java không biến lookup bên dưới thành thao tác có timeout cưỡng bức.

### 5.1. Các loại timeout dễ nhầm

| Loại timeout | Bảo vệ việc gì? | Có phải chính sách tự động của SPI? |
|---|---|---|
| DNS query/response timeout | Chờ phản hồi resolver backend | Không |
| DNS total deadline | Tổng thời gian cho retry và fallback | Không |
| TCP connect timeout | Chờ thiết lập kết nối tới IP | Không |
| Socket read timeout | Chờ dữ liệu sau khi kết nối | Không |
| HTTP request timeout | Toàn bộ hoặc một phần request theo client API | Không |
| Future `get(timeout)` | Thời gian thread caller chờ một task | Không; không bảo đảm dừng lookup bên trong |
| Cache TTL | Thời gian một kết quả được dùng lại | Không phải timeout của lần lookup |

Các tầng này độc lập. Ví dụ đặt connect timeout 500 ms không bảo đảm phân giải hostname xong trong 500 ms nếu quá trình resolve diễn ra trước khi bắt đầu TCP connect. Kiểm tra hợp đồng cụ thể của HTTP/TCP client trước khi tuyên bố một option giới hạn end-to-end latency.

## 6. Phân bổ ngân sách thời gian cho provider

Khi provider cần truy vấn DNS trực tiếp, nên tính một deadline cho toàn lookup thay vì chỉ đặt read timeout lặp lại ở mỗi attempt.

Ví dụ chính sách thiết kế:

~~~text
Overall lookup budget:       800 ms
Max attempts:                2
Max one-attempt budget:      350 ms
Maximum retry/backoff:       phần thời gian còn lại
On timeout:                  dừng retry, trả lỗi lookup
On cancellation:             cố gắng hủy I/O theo client backend
~~~

Đây là **số minh họa**, không phải giá trị mặc định của `InetAddress` hay JDK. Ứng dụng thật cần chọn ngân sách theo latency objective, tính chất mạng và nguồn DNS.

### 6.1. Thuật toán deadline gợi ý

~~~text
start = monotonicClock()
overallBudget = 800 ms

for each attempt while attempt < maxAttempts:
    remaining = overallBudget - elapsedSince(start)
    if remaining <= 0:
        fail lookup

    perAttemptBudget = min(remaining, configuredPerAttemptBudget)
    query DNS with real I/O timeout <= perAttemptBudget
    if successful:
        return addresses
    if timeout/transient failure:
        retry only while time remains

fail lookup with meaningful diagnostic
~~~

Đây là thuật toán ở mức thiết kế, **không phải API Java SE có sẵn**. Thành phần `query DNS` phải dùng network client hỗ trợ connect/read/deadline/cancellation phù hợp. Việc kiểm tra đồng hồ *trước* một network call không giới hạn thời gian network call nếu network layer không áp dụng timeout.

Nên dùng nguồn thời gian monotonic như `System.nanoTime()` để đo elapsed duration. `System.currentTimeMillis()` là wall-clock có thể thay đổi khi đồng hồ máy được điều chỉnh; không phù hợp để tính deadline ngắn của request.

### 6.2. Tại sao timeout chỉ ở tầng chờ là chưa đủ?

Giả sử ứng dụng làm:

~~~java
Future<InetAddress[]> task =
        executor.submit(() -> InetAddress.getAllByName(host));

try {
    return task.get(300, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    task.cancel(true);
    throw timeout;
}
~~~

Đây là **đoạn trích phương án thường gặp**, giả định `executor`, `host` và context trả về được định nghĩa trong ứng dụng; không phải phương thức SPI hoàn chỉnh.

`Future.get(300, ...)` giới hạn **thời gian caller chờ kết quả**. `task.cancel(true)` chỉ yêu cầu interrupt; nếu resolver hoặc I/O bên dưới không hỗ trợ hủy kịp thời, worker vẫn có thể bị block. Khi nhiều lookup timeout cùng lúc, pool thread có thể cạn dù caller đã nhận TimeoutException.

Vì vậy, dùng future timeout như **lớp bảo vệ bên ngoài** là hợp lý khi đã hiểu giới hạn, nhưng không dùng nó thay cho network timeout thực sự ở resolver backend. Với provider phát sinh I/O, cần thiết kế hủy, retry và deadline tại tầng có quyền điều khiển network operation.

## 7. Timeout và ý nghĩa UnknownHostException

`InetAddressResolver` khai báo `UnknownHostException` khi lookup không tìm được hostname hoặc địa chỉ tương ứng. Một thất bại có thể bắt nguồn từ:

- Host không tồn tại hoặc không có record phù hợp.
- Mạng hoặc nameserver không truy cập được.
- Backend hết hạn chờ sau số lần retry đã cấu hình.
- Cấu hình name service không hợp lệ hoặc lỗi môi trường.
- Truy vấn reverse không có tên tương ứng.

Tùy provider và layer bên dưới, các nguyên nhân có thể được biểu diễn bằng `UnknownHostException` cùng thông điệp hoặc cause khác nhau. **Không có hợp đồng chung rằng mọi timeout DNS sẽ thành một subtype exception riêng** từ `InetAddress.getAllByName`.

Một provider có thể gói nguyên nhân để hỗ trợ chẩn đoán:

~~~java
UnknownHostException problem =
        new UnknownHostException("DNS lookup failed for " + host);
problem.initCause(originalFailure);
throw problem;
~~~

Trong ví dụ, `originalFailure` là exception do backend DNS cung cấp. Không giả định mọi provider bảo toàn cause hoặc thông điệp theo cùng cấu trúc. Khi kiểm thử public contract, chỉ assert những exception/type/condition thực sự được tài liệu hóa; phần cause và message có thể là diagnostic phụ thuộc implementation.

Tránh log credential, token, toàn bộ URL hoặc dữ liệu người dùng vào thông điệp lỗi hostname. Giới hạn độ dài, phân loại và sanitize input từ nguồn không tin cậy.

## 8. Ví dụ provider fixture đồng bộ, không phát DNS thật

Để minh họa việc `InetAddress` có thể đi qua provider mà không cần DNS ngoài mạng, ta dùng một hostname fixture ổn định và delegate các tên khác cho resolver tích hợp.

Đây là ví dụ **định tuyến lookup**, không phải implementation DNS có timeout. Nó cố ý không mở socket để tránh nhầm phần test SPI với phần xử lý latency production.

### 8.1. TestResolverProvider.java

~~~java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Stream;

public final class TestResolverProvider extends InetAddressResolverProvider {

    @Override
    public String name() {
        return "fixture-provider";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        // Resolver tích hợp được lấy trước, không gọi InetAddress để
        // tự phân giải tên trong lúc tạo provider.
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            private final byte[] fixtureIp =
                    new byte[] {127, 0, 0, 42};

            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {

                Objects.requireNonNull(host);
                Objects.requireNonNull(policy);

                if ("fixture.test".equalsIgnoreCase(host)) {
                    if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                        throw new UnknownHostException(
                                "No requested IP family for " + host);
                    }
                    // Tạo InetAddress từ byte, không gọi resolver lần nữa.
                    InetAddress fixed =
                            InetAddress.getByAddress("fixture.test", fixtureIp);
                    return Stream.of(fixed);
                }

                // Các hostname không thuộc fixture đi qua resolver tích hợp.
                // Demo này KHÔNG áp đặt deadline cho built-in lookup.
                return builtin.lookupByName(host, policy);
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr);

                if (Arrays.equals(addr, fixtureIp)) {
                    return "fixture.test";
                }
                return builtin.lookupByAddress(addr);
            }
        };
    }
}
~~~

Ví dụ dùng `LookupPolicy.IPV4` để không trả IPv4 khi caller chỉ yêu cầu IPv6. Dự án thật cần tôn trọng cả lựa chọn IPv4/IPv6 và thứ tự kết quả của `LookupPolicy`, đặc biệt nếu provider có cả record A và AAAA.

`InetAddress.getByAddress("fixture.test", fixtureIp)` **không gọi DNS để xác minh hostname**; nó tạo object chứa địa chỉ được truyền vào. Đây là cách tránh đệ quy vô hạn khi triển khai provider.

### 8.2. Đăng ký bằng ServiceLoader

Với JAR classpath, đặt entry sau trong JAR provider:

~~~text
META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Nội dung file chỉ gồm tên lớp provider:

~~~text
demo.resolver.TestResolverProvider
~~~

Với ứng dụng JPMS, có thể đăng ký bằng module descriptor:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with demo.resolver.TestResolverProvider;
}
~~~

Provider cần nằm trong runtime và được ServiceLoader khám phá theo cấu hình module/classpath. Để thử trên module path, cần đảm bảo module chứa provider được resolve; dùng `--add-modules demo.resolver` khi cần với phương thức chạy phù hợp.

### 8.3. Probe.java

~~~java
import java.net.InetAddress;

public class Probe {
    public static void main(String[] args) throws Exception {
        for (InetAddress address :
                InetAddress.getAllByName("fixture.test")) {
            System.out.println(address.getHostAddress());
        }
    }
}
~~~

Trong **JVM mới** có đăng ký provider đúng và đã resolve, ví dụ này dự kiến in:

~~~text
127.0.0.42
~~~

Nếu không thấy kết quả, kiểm tra service registration, module graph, classpath và provider đã được chọn. Do cache và lựa chọn resolver ở cấp JVM, không dùng cùng một JVM đang chạy để bật/tắt provider rồi mong định tuyến thay đổi tức thì.

Không dùng test này để suy ra timeout của provider đã được bảo đảm: nó không gửi network request thật và nhánh delegate cho built-in chưa có deadline do provider kiểm soát.

## 9. Tránh vòng lặp khi provider tự gọi lại InetAddress

Một lỗi thiết kế thường gặp:

~~~java
// Sai trong custom lookupByName:
return Arrays.stream(InetAddress.getAllByName(host));
~~~

Khi `InetAddress.getAllByName(host)` đã ủy quyền cho chính provider, lệnh trên có thể dẫn đến recursion hoặc chờ lẫn nhau; hành vi còn chịu ảnh hưởng cache/khóa nội bộ.

Các phương án đúng:

- Dùng `configuration.builtinResolver()` để delegate rõ ràng cho resolver tích hợp.
- Nếu có DNS client riêng, gọi trực tiếp client đó, không đi vòng qua `InetAddress` của chính JVM.
- Với fixture IP cố định, dùng `InetAddress.getByAddress(...)` từ byte IP.
- Trong hàm `get(Configuration)`, hạn chế tối đa thao tác có thể gây lookup hoặc class-loading cycle.

Không nên dùng lại một phương thức `InetAddress` phụ thuộc resolver đang được khởi tạo để khởi tạo provider đó. Javadoc khuyến nghị provider initialization càng đơn giản càng tốt.

## 10. Ranh giới với thư viện có resolver riêng

**SPI này điều chỉnh đường đi qua `InetAddress`, không tự động chặn toàn bộ DNS traffic của JVM.**

Một thư viện có thể:

1. Gọi `InetAddress.getByName` hoặc `getAllByName` và nhận kết quả từ resolver hệ thống của Java.
2. Có một DNS abstraction nhưng implementation mặc định vẫn delegate sang `InetAddress`.
3. Gửi DNS packets bằng UDP/TCP riêng hoặc dùng DNS-over-HTTPS qua HTTP client khác.
4. Dùng native library hoặc API tên riêng không đi qua `InetAddress`.
5. Nhận sẵn IP từ cấu hình hoặc cache nên không thực hiện DNS lookup.
6. Dùng hostname resolution của proxy hoặc lớp mạng ngoài tiến trình ứng dụng.

Chỉ trường hợp thực sự gọi `InetAddress` cho lookup tương ứng mới nằm trong phạm vi của resolver SPI.

### 10.1. Ma trận mức độ bao phủ

| Đường đi của ứng dụng/thư viện | Provider InetAddress có thể ảnh hưởng? | Lưu ý |
|---|---|---|
| `InetAddress.getAllByName(host)` | Có, khi cần system-wide lookup | Cache/literal có thể tránh gọi provider |
| `InetAddress.getByName(host)` | Có, khi cần system-wide lookup | Cùng giới hạn cache/khởi tạo |
| `getCanonicalHostName()` | Có, với reverse lookup | Có thể kèm forward check/fallback |
| Thư viện `DNS resolver` delegate sang `InetAddress` | Có, tại nhánh delegate | Cần kiểm tra implementation cụ thể |
| Client DNS tự gửi UDP/TCP query | Không tự động | Cần cấu hình client đó |
| Client dùng DoH riêng | Không tự động | Cần cấu hình endpoint/timeout của DoH client |
| Gọi API từ IP đã có, không tra tên | Không cần resolver | Đừng assert provider được gọi |
| Proxy giải DNS từ phía server | Không theo đường đi JVM local | Policy nằm ở proxy/server |
| Thư viện có cache của riêng mình | Có thể không lookup lại | Cần phân biệt cache của thư viện và JVM |

Ví dụ thực tế có thể có thư viện networking với DNS resolver tùy biến hoặc lựa chọn DoH. Không được khẳng định một thư viện cụ thể chắc chắn dùng/bỏ qua SPI chỉ từ tên sản phẩm; phiên bản, adapter và configuration quyết định đường đi.

### 10.2. Vì sao điều này quan trọng cho timeout?

Nếu hệ thống gắn provider custom với budget 500 ms, còn thư viện HTTP sử dụng một DNS client riêng có retry 5 giây, request từ thư viện đó vẫn có thể chờ quá 500 ms.

Ngược lại, một HTTP client có request timeout 2 giây không tự chứng minh custom provider của `InetAddress` sẽ dừng network request sau 2 giây nếu provider không hỗ trợ hủy.

**Kết luận kiến trúc:** DNS timeout và observability phải được cấu hình, kiểm thử tại **mọi đường phân giải tên thật sự được sử dụng**; không chỉ tại provider được đăng ký.

## 11. Kiểm tra thực nghiệm thư viện có đi qua SPI hay không

Đừng suy ra từ một class name hoặc từ việc ứng dụng chạy thành công. Đề xuất quy trình:

1. Liệt kê HTTP/database/message clients và SDK networking của ứng dụng.
2. Tìm cấu hình như `DnsResolver`, `NameResolver`, `ResolverGroup` hoặc adapter tương tự trong tài liệu của **đúng phiên bản** thư viện.
3. Xác định implementation đang sử dụng có gọi `InetAddress` hay gửi network query riêng.
4. Đăng ký một provider fixture như phần 8 trong JVM thử nghiệm mới.
5. Dùng một hostname fixture được kiểm soát, tránh public DNS.
6. Quan sát kết quả/marker phía provider nếu có. Không yêu cầu đúng một call vì cache và điều kiện runtime.
7. Chạy cùng request qua từng client/transport của ứng dụng.
8. So sánh client nào nhận IP fixture, client nào dùng resolver khác.
9. Ghi kết quả theo client version, JDK vendor/version, OS và configuration.

Tách test `InetAddress` trực tiếp với test integration của thư viện. Một test `InetAddress.getByName("fixture.test")` thành công chỉ xác nhận provider được gọi trong đường đi đó; nó **không** chứng minh tất cả client trong JVM đều sử dụng provider.

Khi muốn chắc chắn một client đi qua provider, nên có instrumentation/metric ở nhánh provider, không chỉ suy luận từ địa chỉ IP cuối cùng vì có thể tồn tại cache hoặc cấu hình trùng kết quả.

## 12. Cache không phải timeout

`InetAddress` có cache cho lookup thành công và thất bại. Các security properties liên quan gồm:

- `networkaddress.cache.ttl`: tuổi thọ positive cache.
- `networkaddress.cache.negative.ttl`: tuổi thọ negative cache.
- `networkaddress.cache.stale.ttl`: chính sách giữ kết quả stale trong các JDK hỗ trợ.

Đây là **cache TTL**, khác với network timeout. Cấu hình positive cache TTL 30 giây không có nghĩa một DNS lookup mới sẽ timeout sau 30 giây.

Hệ quả khi kiểm thử:

- Lookup đầu có thể gọi provider, lookup kế tiếp nhận kết quả từ cache.
- Một thất bại có thể được negative-cache tạm thời và không lặp lại network ngay.
- Cache của thư viện bên ngoài là một lớp nữa, có TTL độc lập.
- Không mặc định cache sẽ có TTL giống nhau trên mọi JDK/vendor/configuration.

Khi đo latency của provider, cần phân biệt cache hit, cache miss, lookup network mới và retry. Không dựa vào việc gọi cùng hostname hai lần rồi đo thời gian để suy ra timeout thật.

### 12.1. Kiểm chứng với JVM mới

Vì resolver toàn hệ thống và cache nằm trong phạm vi JVM, bài kiểm thử khởi chạy JVM riêng cho mỗi cấu hình sẽ dễ tái hiện hơn việc cố sửa property hoặc provider trong cùng một process.

Không khuyến nghị ứng dụng production thay đổi security property cache trong lúc chạy để buộc DNS call mới; hãy dùng cấu hình startup rõ ràng, fixture và instrumentation phù hợp.

## 13. LookupPolicy không phải thời gian chờ

`InetAddressResolver.LookupPolicy` chứa các đặc tính về IP family và ordering:

- `LookupPolicy.IPV4`
- `LookupPolicy.IPV6`
- `LookupPolicy.IPV4_FIRST`
- `LookupPolicy.IPV6_FIRST`

Dùng `lookupPolicy.characteristics()` để đọc bitmask. Một provider cần trả kết quả phù hợp family được yêu cầu, đồng thời bảo toàn ordering khi có cả IPv4 và IPv6.

Không nhầm:

- IPv4/IPv6 preference: chính sách **nên trả loại địa chỉ nào và thứ tự nào**.
- Timeout/retry: chính sách **được phép chờ bao lâu và thử mấy lần**.

Một provider có thể thực hiện tra cứu A/AAAA tuần tự hoặc song song tùy thiết kế. Vì API public không truyền deadline, nếu muốn overall budget, provider phải tính ngân sách cho cả hai loại truy vấn và các lần retry.

### 13.1. Forward và reverse là hai hoạt động khác nhau

`lookupByName` chuyển hostname thành địa chỉ IP. `lookupByAddress` nhận byte IP dài 4 (IPv4) hoặc 16 (IPv6) và tìm hostname tương ứng.

Một reverse lookup cũng có thể chậm hoặc thất bại. Nếu provider chỉ áp đặt timeout cho forward lookup, ứng dụng gọi `getCanonicalHostName()` vẫn có nguy cơ block lâu. Chính sách timeout cần bao phủ **cả hai hướng** nếu kiến trúc sử dụng chúng.

## 14. Cách xử lý cancellation và thread resource

Một resolver đồng bộ có thể chiếm thread trong khi chờ backend trả kết quả. Đây là vấn đề latency và capacity, đặc biệt khi ứng dụng có nhiều request đồng thời.

Các nguyên tắc:

1. Hạn chế số lookup network đồng thời nếu backend không chịu tải lớn.
2. Dùng timeout ở tầng I/O thực sự có thể kết thúc thao tác.
3. Có overall deadline để tránh retry vô hạn.
4. Giải phóng socket/resource trong `finally` hoặc try-with-resources.
5. Không giả định `Thread.interrupt()` có thể dừng mọi native DNS call ngay lập tức.
6. Không tạo vô hạn worker thread chỉ vì caller đã timeout.
7. Ghi metric latency của **lookup thật**, không chỉ thời gian chờ kết quả ở request thread.
8. Theo dõi active lookups, queue depth, timeout count, failure count và fallback count.

Virtual threads có thể giúp đơn giản hóa cấu trúc đồng thời trong các tình huống phù hợp, nhưng chúng không thay thế việc quản lý deadline của DNS backend hoặc làm một SPI đồng bộ tự động có tham số timeout. Cần kiểm tra implementation thực tế và khả năng hủy của I/O đang dùng.

Không dùng `Thread.stop()` hay các thủ thuật dừng thread cưỡng bức đã lỗi thời để xử lý lookup chậm.

## 15. Chẩn đoán timeout end-to-end

Giả sử một API HTTP thỉnh thoảng chậm 8 giây dù được cấu hình connect timeout 1 giây. Không vội kết luận timeout của HTTP client bị bỏ qua.

Cần ghi các mốc:

~~~text
T0: request bắt đầu
T1: bắt đầu resolve hostname
T2: hoàn tất resolve / lấy từ cache
T3: bắt đầu TCP connect
T4: kết nối thành công hoặc thất bại
T5: gửi request
T6: đọc response
T7: request hoàn thành
~~~

Đo từng pha khi thư viện cho phép instrumentation:

| Khoảng thời gian | Ý nghĩa | Thành phần cần kiểm tra |
|---|---|---|
| T1 → T2 | DNS resolution | InetAddress provider hoặc resolver riêng của client |
| T3 → T4 | TCP connect | Connect timeout, mạng, proxy |
| T5 → T6 | Response latency | Server, HTTP request/read timeout |
| T0 → T7 | End-to-end latency | Deadline toàn request và các bước chờ |

Không phải thư viện nào cũng có callback cho từng mốc. Nếu không đo được chính xác, hãy dùng fixture/instrumentation ở lớp kiểm soát được và ghi rõ giới hạn kết luận.

Với sự cố thực tế, ghi JDK version, client/library version, hostname đã sanitize, provider được chọn nếu đo được, trạng thái cache, timeout/retry config và môi trường OS. Tránh log dữ liệu nhạy cảm hoặc hostname không đáng tin cậy một cách thiếu giới hạn.

## 16. Kiểm thử hành vi timeout có kiểm soát

### 16.1. Unit test cho thuật toán budget

Không cần DNS internet. Dùng fake clock/fake DNS transport để trả các trường hợp:

- Kết quả trước deadline.
- Một attempt timeout nhưng lần sau thành công.
- Hết overall deadline trước attempt tiếp theo.
- Backend trả lỗi không retry được.
- Cancellation trong lúc chờ.
- IPv4 và IPv6 dùng chung ngân sách.

Assert các invariants:

- Không khởi chạy attempt mới khi ngân sách đã hết.
- Không retry vượt số lần cho phép.
- Không bỏ qua cancellation nếu transport hỗ trợ.
- Không coi `UnknownHostException` là bằng chứng duy nhất của NXDOMAIN.
- Không gọi hệ thống mạng thật trong unit test.

### 16.2. Integration test cho provider SPI

Dùng provider fixture ở phần 8, JVM mới và `InetAddress.getAllByName("fixture.test")`.

Kiểm tra:

- Provider được phát hiện qua ServiceLoader.
- Tên fixture nhận IP cố định từ provider.
- Hostname không thuộc fixture delegate đúng nhánh đã thiết kế, nhưng không bắt buộc gọi DNS ngoài mạng trong CI.
- Reverse lookup và LookupPolicy được kiểm tra bằng fixture thích hợp.
- Cache/khởi tạo khiến số lượt gọi provider có thể khác số lượt gọi API.

### 16.3. Integration test cho thư viện có resolver riêng

Mỗi client có thể có đường resolution khác nhau. Kiểm tra trên đúng phiên bản/configuration mà sản phẩm sử dụng:

- Nhánh dùng `InetAddress` có nhận fixture provider không?
- Nhánh dùng resolver riêng có bỏ qua fixture không?
- Timeout của client áp dụng vào DNS, connect hay request?
- Sau timeout, còn I/O/worker nào tiếp tục chạy không?
- Retry có làm tổng request vượt budget không?
- Hai kiểu client có khác nhau khi cache hit/miss không?

Không cần làm chậm public DNS hoặc đánh vào nameserver production để kiểm thử. Dùng fake transport, local stub DNS server hoặc môi trường kiểm soát có timeout ngắn.

## 17. Những hiểu lầm cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| JEP 418 làm DNS lookup thành API bất đồng bộ | SPI có hai phương thức lookup đồng bộ |
| `Stream<InetAddress>` nghĩa là async | Stream là tập kết quả, không phải CompletionStage |
| SPI truyền timeout vào `LookupPolicy` | LookupPolicy chỉ mang family/order, không mang deadline |
| Đã đặt TCP connect timeout nên DNS chắc chắn hết hạn cùng lúc | DNS có thể chạy trước TCP connect và dùng timeout riêng |
| `Future.get(timeout)` chấm dứt chắc chắn DNS đang block | Caller hết thời gian chờ; underlying task có thể vẫn chạy |
| Provider có timeout nên mọi thư viện trong JVM đều được bảo vệ | Chỉ đường đi qua InetAddress SPI mới chịu ảnh hưởng |
| Mọi lần gọi `InetAddress.getByName` đều gọi provider | Cache, literal và đường xử lý khác có thể tránh lookup |
| `networkaddress.cache.ttl` là DNS timeout | TTL là vòng đời cache, không phải latency budget |
| Resolver custom có thể gọi lại `InetAddress.getByName` để delegate | Có thể gây recursion; dùng `builtinResolver()` hoặc DNS client riêng |
| `UnknownHostException` luôn có nghĩa domain không tồn tại | Có nhiều nguyên nhân, bao gồm lỗi mạng/timeout tùy provider |
| Virtual threads tự giải quyết DNS timeout | Cần timeout và cancellation thật ở network backend |
| Có hai provider thì có thể dựa vào thứ tự ưu tiên ổn định | Discovery order implementation-specific; tránh cấu hình mơ hồ |

## 18. Bài tập thực hành

### Bài 1 — Đọc hợp đồng SPI

Đọc Javadoc của `InetAddressResolver` và `LookupPolicy` trên JDK mục tiêu.

**Tiêu chí đạt:** Chỉ ra được hai phương thức lookup, kiểu trả về, exception được khai báo và việc không có tham số timeout.

### Bài 2 — Đăng ký fixture provider

Sử dụng ví dụ `TestResolverProvider`, đóng gói service registration và chạy `Probe` trong JVM mới.

**Tiêu chí đạt:** `fixture.test` được resolve thành địa chỉ fixture, không cần public DNS; biết vì sao có thể phải kiểm tra module graph.

### Bài 3 — Thiết kế ngân sách DNS

Đề xuất chính sách overall 800 ms, tối đa hai attempt và per-attempt cap 350 ms.

**Tiêu chí đạt:** Có xét thời gian còn lại trước mỗi attempt; biết rằng transport phải enforce timeout, không chỉ kiểm tra đồng hồ ở caller.

### Bài 4 — Phân biệt timeout ở các tầng

Cho một tình huống DNS 3 giây, TCP connect 100 ms, HTTP response 200 ms. Client chỉ có connect timeout 500 ms.

**Tiêu chí đạt:** Giải thích được vì sao không thể kết luận end-to-end request luôn dưới 500 ms.

### Bài 5 — Kiểm tra thư viện có resolver riêng

Chọn hai client networking mà dự án thực sự dùng, xác định đường đi DNS của từng client qua cấu hình/tài liệu hoặc fixture provider.

**Tiêu chí đạt:** Không suy luận rằng mọi client tự động dùng `InetAddressResolverProvider`; ghi bằng chứng cho từng implementation.

### Bài 6 — Reverse lookup và cache

Dùng fixture IP và `getCanonicalHostName()` để khảo sát reverse; chạy test trong JVM mới và quan sát cache có thể ảnh hưởng số lượt gọi.

**Tiêu chí đạt:** Phân biệt forward, reverse, cache hit và invocation của provider; không assert chính xác số request mạng khi contract không bảo đảm.

## 19. Checklist áp dụng vào dự án

- [ ] Xác định phiên bản JDK có `InetAddressResolverProvider` (Java 18+).
- [ ] Xác định hostname resolution thực sự đi qua `InetAddress` hay resolver riêng.
- [ ] Không coi SPI là API async hoặc có built-in request deadline.
- [ ] Có overall budget và per-attempt timeout cho DNS backend do mình kiểm soát.
- [ ] Có chính sách retry/backoff hữu hạn.
- [ ] Có cách giải phóng resource và xử lý cancellation hợp lý.
- [ ] Không nhầm connect/read/request timeout với DNS lookup timeout.
- [ ] Không nhầm cache TTL với latency deadline.
- [ ] Có test timeout với fake transport, không phụ thuộc DNS internet.
- [ ] Có integration test provider registration ở JVM riêng.
- [ ] Đã kiểm tra LookupPolicy và reverse lookup khi cần.
- [ ] Không gọi lại `InetAddress.getByName` từ chính provider custom.
- [ ] Đã kiểm tra đường DNS và timeout của từng thư viện networking.
- [ ] Không phụ thuộc thứ tự ServiceLoader khi có nhiều provider.
- [ ] Không sử dụng API nội bộ/legacy để thay thế SPI công khai.
- [ ] Có metric latency, timeout, retry, cache hit/miss để chẩn đoán production.

## 20. Tài liệu chính thức

1. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): mục tiêu và phạm vi thay đổi từ Java 18.
2. [InetAddressResolver — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolver.html): chữ ký lookup đồng bộ, LookupPolicy, UnknownHostException.
3. [InetAddressResolverProvider — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): cơ chế chọn một resolver toàn JVM và ServiceLoader.
4. [InetAddressResolverProvider.Configuration — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.Configuration.html): `builtinResolver()` và `lookupLocalHostName()`.
5. [InetAddressResolver.LookupPolicy — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html): lựa chọn IPv4/IPv6 và ordering.
6. [InetAddress — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): system-wide resolver, lookup APIs, caching và reverse lookup.
7. [Future — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): ý nghĩa `get(timeout)` và `cancel(boolean)`.
8. [System — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html): `nanoTime()` để đo elapsed time.
9. [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): bối cảnh concurrency hiện đại, không thay thế deadline của DNS backend.

**Kết quả cần đạt:** Bạn phân biệt được phạm vi `InetAddressResolverProvider` với các thư viện DNS riêng, hiểu vì sao SPI đồng bộ không tự mang timeout và biết đặt giới hạn thời gian tại backend/provider hoặc client thích hợp. Khi kiểm tra hệ thống, hãy phân tách DNS latency, TCP connect, response time và cache, đồng thời dùng fixture/JVM riêng để xác nhận đường đi resolver trên JDK hiện đại.
