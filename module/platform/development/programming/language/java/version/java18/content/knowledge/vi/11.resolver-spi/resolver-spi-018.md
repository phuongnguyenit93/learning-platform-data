# Thiết kế resolver an toàn khi nhiều luồng gọi đồng thời và quản lý trạng thái dùng chung

## 1. Bối cảnh và mục tiêu

Từ Java 18, **InetAddress Resolver SPI** (JEP 418) cho phép ứng dụng cung cấp cách phân giải tên riêng qua `java.net.spi.InetAddressResolverProvider` và `java.net.spi.InetAddressResolver`. Cơ chế này vẫn có mặt trên các JDK hiện đại. Chủ đề thuộc nhóm **Resolver SPI** của module `JAVA_VERSION_JAVA18`: thiết kế một resolver hoạt động đúng khi nhiều luồng cùng tra cứu địa chỉ, trong khi cấu hình hoặc dữ liệu dùng chung có thể thay đổi.

Ví dụ, dịch vụ nội bộ muốn ánh xạ một số hostname sang IP do hệ thống điều phối cấp, còn những hostname khác tiếp tục được phân giải theo cơ chế mặc định của JDK. Các luồng HTTP client, tác vụ nền và luồng xử lý yêu cầu có thể gọi `InetAddress.getAllByName(...)` đồng thời. Nếu resolver tự lưu `HashMap` có thể sửa trực tiếp hoặc dùng chung một đối tượng `ArrayList` đang bị cập nhật, các luồng có thể nhận dữ liệu chưa hoàn chỉnh hoặc kết quả không nhất quán.

Một thiết kế an toàn cần đáp ứng những yêu cầu sau:

- Mỗi lần tra cứu nhìn thấy **một phiên bản cấu hình hoàn chỉnh**, dù phiên bản mới được công bố trong lúc tra cứu.
- Không có data race trên bảng ánh xạ, thống kê, cache hoặc trạng thái làm mới.
- Tôn trọng `LookupPolicy` về họ địa chỉ IPv4/IPv6 và thứ tự ưu tiên; truy vấn ngược cũng có quy tắc rõ ràng.
- Không gọi lại `InetAddress.getByName(...)` hoặc `InetAddress.getAllByName(...)` từ chính resolver để tránh đi vòng qua SPI, gây đệ quy hoặc phụ thuộc vào bộ nhớ đệm ngoài ý muốn.
- Khi tra cứu tên không được xử lý riêng, có thể ủy quyền cho resolver tích hợp do `Configuration.builtinResolver()` cung cấp.
- Cấu hình sai phải bị từ chối trước khi công bố; lỗi của một lần tra cứu không được làm hỏng trạng thái dùng chung.

> Phạm vi: bài học sử dụng các API công khai hiện còn được hỗ trợ, như Resolver SPI, `AtomicReference`, các collection bất biến và các công cụ đồng thời chuẩn của Java. Không phụ thuộc API DNS nội bộ của JDK.

## 2. Những thành phần nào thực sự dùng chung?

`InetAddressResolverProvider` được cơ chế SPI lựa chọn và sử dụng để tạo một `InetAddressResolver` qua phương thức `get(Configuration)`. Phần mã tra cứu cần được xem là **có thể bị nhiều luồng gọi đồng thời**. Không giả định mỗi luồng sở hữu một resolver riêng hoặc việc khởi tạo sẽ lặp lại cho mỗi truy vấn.

| Thành phần | Vòng đời/đặc điểm | Cách quản lý phù hợp |
|---|---|---|
| Resolver tích hợp (`builtinResolver`) | Được lấy từ cấu hình SPI | Giữ tham chiếu sau khi khởi tạo; dùng để ủy quyền, không tự gọi lại API phân giải tên của `InetAddress` |
| Bảng hostname → IP | Nhiều truy vấn cùng đọc, đôi khi thay đổi | Tạo bản sao bất biến rồi công bố bằng `AtomicReference` |
| Bảng IP → hostname | Cần đồng bộ logic với bảng thuận | Đặt chung trong **một snapshot** với bảng thuận |
| Cache tự xây dựng | Nhiều luồng đọc/ghi, dữ liệu có thời hạn | Cấu trúc đồng thời, TTL, giới hạn dung lượng và chính sách làm mới |
| Số liệu thống kê | Nhiều luồng tăng đếm | `LongAdder` hoặc `AtomicLong`; không dùng `long++` không đồng bộ |
| Dữ liệu tạm của một lần lookup | Chỉ phục vụ một lời gọi | Biến cục bộ; không lưu ở field có thể bị ghi đè bởi luồng khác |

Một `ConcurrentHashMap` chỉ bảo đảm an toàn cho **các thao tác riêng lẻ trên map**. Nó không tự bảo đảm một đợt cập nhật nhiều key là nguyên tử, càng không bảo đảm hai map thuận và ngược được thay đồng thời. Với dữ liệu cấu hình ít cập nhật, một snapshot bất biến thường dễ kiểm chứng hơn.

## 3. Mẫu thiết kế: immutable snapshot và atomic publication

Giả sử một bản cấu hình gồm hai bảng:

```text
Snapshot phiên bản N
 ├── forward: hostname -> danh sách InetAddress
 └── reverse: bytes địa chỉ -> hostname

Luồng cập nhật: kiểm tra dữ liệu -> tạo hai map mới -> AtomicReference.set(N+1)
Luồng tra cứu: AtomicReference.get() -> xử lý hoàn toàn trên snapshot vừa lấy
```

`AtomicReference.get()` lấy một tham chiếu đã được công bố an toàn, còn `set()` thay tham chiếu nguyên tử. Vì map và danh sách bên trong không bị sửa sau khi công bố, luồng đã giữ phiên bản N có thể tiếp tục tra cứu ngay cả khi luồng khác công bố phiên bản N+1. Điều này tránh khóa toàn cục trong đường tra cứu thường xuyên.

### Ví dụ triển khai đầy đủ

Ví dụ dưới đây áp dụng cho Java 18 trở lên. Bảng override dùng các hostname và đối tượng `InetAddress` đã được chuẩn bị từ trước; bước thay cấu hình **không cần thực hiện truy vấn DNS**. Mọi tên không có trong bảng được chuyển tới resolver tích hợp.

```java
package example.resolver;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

public final class SafeResolverProvider extends InetAddressResolverProvider {
    private record Snapshot(
            Map<String, List<InetAddress>> forward,
            Map<String, String> reverse) { }

    private static final AtomicReference<Snapshot> CURRENT =
            new AtomicReference<>(new Snapshot(Map.of(), Map.of()));

    // Nên gọi khi ứng dụng nạp cấu hình, trước các lần tra cứu đầu tiên.
    public static void replaceOverrides(Map<String, List<InetAddress>> input) {
        Objects.requireNonNull(input, "input");
        Map<String, List<InetAddress>> forward = new HashMap<>();
        Map<String, String> reverse = new HashMap<>();

        for (var entry : input.entrySet()) {
            String host = key(entry.getKey());
            List<InetAddress> addresses = List.copyOf(entry.getValue());
            if (addresses.isEmpty() || forward.putIfAbsent(host, addresses) != null) {
                throw new IllegalArgumentException("Invalid/duplicate host: " + host);
            }

            for (InetAddress address : addresses) {
                String bytes = HexFormat.of().formatHex(address.getAddress());
                String previous = reverse.putIfAbsent(bytes, host);
                if (previous != null && !previous.equals(host)) {
                    throw new IllegalArgumentException(
                            "Address is assigned to multiple hosts: " + bytes);
                }
            }
        }

        // Chỉ công bố sau khi toàn bộ dữ liệu đã hợp lệ và được sao chép.
        CURRENT.set(new Snapshot(Map.copyOf(forward), Map.copyOf(reverse)));
    }

    private static String key(String host) {
        return Objects.requireNonNull(host, "host").toLowerCase(Locale.ROOT);
    }

    @Override
    public String name() {
        return "safe-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy) throws UnknownHostException {
                Snapshot snapshot = CURRENT.get();
                List<InetAddress> configured = snapshot.forward().get(key(host));
                if (configured == null) {
                    return builtin.lookupByName(host, policy);
                }

                int flags = policy.characteristics();
                List<InetAddress> matches = new ArrayList<>();
                for (InetAddress address : configured) {
                    if (address instanceof Inet4Address
                            && (flags & LookupPolicy.IPV4) != 0) {
                        matches.add(address);
                    } else if (address instanceof Inet6Address
                            && (flags & LookupPolicy.IPV6) != 0) {
                        matches.add(address);
                    }
                }
                if (matches.isEmpty()) {
                    throw new UnknownHostException(host);
                }

                if ((flags & LookupPolicy.IPV4_FIRST) != 0) {
                    matches.sort(Comparator.comparingInt(
                            address -> address instanceof Inet4Address ? 0 : 1));
                } else if ((flags & LookupPolicy.IPV6_FIRST) != 0) {
                    matches.sort(Comparator.comparingInt(
                            address -> address instanceof Inet6Address ? 0 : 1));
                }
                return List.copyOf(matches).stream();
            }

            @Override
            public String lookupByAddress(byte[] address) throws UnknownHostException {
                Snapshot snapshot = CURRENT.get();
                String bytes = HexFormat.of().formatHex(address);
                String configured = snapshot.reverse().get(bytes);
                return configured != null
                        ? configured
                        : builtin.lookupByAddress(address);
            }
        };
    }
}
```

Điểm cần kiểm chứng trong đoạn mã:

1. `Snapshot` chứa **cả hai bảng**; một lần lookup chỉ lấy một snapshot bằng `CURRENT.get()`. Hai bảng được xây dựng rồi thay cùng lúc, tránh trạng thái “bảng thuận mới, bảng ngược cũ”.
2. `List.copyOf(...)` sao chép danh sách từ phía gọi và từ chối phần tử `null`; `Map.copyOf(...)` tạo map không sửa được. Không lưu trực tiếp collection mà bên ngoài vẫn giữ quyền sửa.
3. Mã biến byte địa chỉ thành chuỗi hex khi xây bảng ngược, không giữ lại mảng `byte[]` do phía gọi sở hữu. Dùng trực tiếp `byte[]` làm key trong `HashMap` sẽ sai vì so sánh mảng mặc định theo tham chiếu.
4. Tên trong cấu hình được so khớp không phân biệt hoa/thường bằng `Locale.ROOT`. Ví dụ cố ý **không** tự xóa dấu chấm cuối, chuyển IDN hoặc sửa dạng literal IP; với những yêu cầu đó, cần xây quy tắc canonicalization riêng và kiểm thử tương thích với hành vi JDK.
5. Khi hostname có override nhưng không có địa chỉ phù hợp với `LookupPolicy`, mã báo `UnknownHostException`. Nó không âm thầm trả về IPv4 cho yêu cầu chỉ nhận IPv6, hoặc tự chuyển sang DNS mặc định và làm mất tính nhất quán của override.
6. Đối với dữ liệu override, `lookupByAddress` dùng bảng ngược trong cùng snapshot. Khi cùng một IP được khai báo cho hai hostname khác nhau, bước kiểm tra từ chối cấu hình vì quy tắc reverse của ví dụ không có câu trả lời duy nhất. Một dịch vụ thực tế có thể chọn quy tắc khác và phải mô tả rõ quy tắc đó.

### Đăng ký provider

Nếu ứng dụng dùng **classpath**, tệp tài nguyên `META-INF/services/java.net.spi.InetAddressResolverProvider` chứa tên lớp:

```text
example.resolver.SafeResolverProvider
```

Nếu dùng **named module**, khai báo trong `module-info.java`:

```java
module example.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with example.resolver.SafeResolverProvider;
}
```

Hai cách trên là hai kiểu đóng gói thay thế nhau. Trong môi trường chạy thật, phải kiểm tra provider được JDK chọn đúng như mong muốn; không giả định việc thêm provider mới vào một JVM đang hoạt động sẽ thay thế resolver đã được chọn hoặc xóa cache tra cứu cũ.

### Nạp dữ liệu mẫu

`InetAddress.getByAddress(byte[])` tạo đối tượng từ byte IP, không thực hiện tra cứu tên qua SPI. Có thể dùng nó khi chuẩn bị cấu hình:

```java
byte[] ip = {(byte) 192, 0, 2, 10}; // TEST-NET-1: địa chỉ tài liệu
SafeResolverProvider.replaceOverrides(Map.of(
        "api.example.test", List.of(InetAddress.getByAddress(ip))));
```

Đoạn mã giả định được đặt trong phương thức có xử lý `UnknownHostException` và đã import các lớp cần thiết. Nạp cấu hình sớm, trước khi các client bắt đầu thực hiện lookup, giúp giảm tác động của những kết quả tên đã được JDK lưu trong cache.

## 4. Những giới hạn quan trọng của mẫu snapshot

**Nguyên tử khi thay cấu hình không đồng nghĩa mọi lời gọi cùng thấy một phiên bản.** Nếu luồng A lấy snapshot N và luồng B lấy N+1 sau một lần reload thì cả hai kết quả đều hợp lệ. Nếu nghiệp vụ yêu cầu mọi thao tác thuộc cùng một giao dịch nhìn thấy cùng phiên bản, cần truyền snapshot hoặc version ở cấp giao dịch; SPI không tự tạo hợp đồng nhất quán liên lời gọi.

**Một cặp lookup thuận rồi ngược cũng có thể đi qua hai phiên bản.** Ví dụ trên bảo đảm mỗi *lời gọi* dùng một snapshot, nhưng không gắn hai lời gọi độc lập vào cùng một phiên bản. Bên cạnh đó, dữ liệu reverse được cấu hình có thể khác PTR của DNS công cộng; đây là một chính sách của resolver, không phải bằng chứng cho bản ghi PTR bên ngoài.

**Cập nhật cấu hình không bắt buộc làm `InetAddress` hỏi provider ngay lần kế tiếp.** `InetAddress` có cơ chế cache kết quả thuận và lỗi tra cứu. Chính sách TTL tích cực/tiêu cực của JVM có thể giữ kết quả đã phân giải, làm cho snapshot mới chưa xuất hiện ngay qua `InetAddress.getByName(...)`. Cần thiết kế cách triển khai, thay đổi và quan sát kết quả với chính sách cache phù hợp; không hứa rằng `CURRENT.set(...)` sẽ lập tức vô hiệu hóa cache của JDK.

**Thứ tự tìm kiếm và thời gian sống của provider thuộc cơ chế SPI.** Không đặt logic khởi tạo phụ thuộc vào chính việc `InetAddress` tra cứu trong constructor hoặc `get(...)`, và không dựa vào thứ tự không được bảo đảm khi có nhiều provider cùng đăng ký. Cấu hình nào có vòng đời riêng (ví dụ dùng file watcher) cần cơ chế đóng tài nguyên rõ ràng, tránh tạo một watcher/executor mới ở mỗi lần lookup.

## 5. Khi resolver cần cache hoặc thực hiện tác vụ chậm

Không phải resolver nào cũng chỉ đọc bản đồ cấu hình bất biến. Nếu phải hỏi một dịch vụ điều phối hoặc DNS chuyên biệt, ta cần quyết định cách chia sẻ kết quả đang tính toán và cách giới hạn tài nguyên.

| Vấn đề | Cách tiếp cận | Điều cần tránh |
|---|---|---|
| Nhiều luồng hỏi cùng hostname | Đồng bộ yêu cầu cùng khóa (*single-flight*) hoặc dùng future đang chạy chung | Cho hàng trăm luồng cùng tạo một truy vấn ngoại vi cho một key |
| Kết quả có thời hạn | Lưu `expiresAt` theo `System.nanoTime()` để đo khoảng thời gian trong một tiến trình | Dùng thời gian đồng hồ hệ thống cho khoảng TTL ngắn, hoặc giữ kết quả vô hạn |
| Kết quả âm (`UnknownHostException`) | Quy định TTL âm riêng, có giới hạn; xóa trạng thái tác vụ lỗi để cho phép thử lại | Cache mọi lỗi mạng như “hostname không tồn tại” vĩnh viễn |
| Cache tăng không kiểm soát | Giới hạn số phần tử/khối lượng, TTL và chính sách loại bỏ | Dùng `ConcurrentHashMap` không giới hạn theo hostname do phía ngoài cung cấp |
| Reload khi lookup đang chạy | Lookup giữ snapshot cũ hoặc key chứa version, theo chính sách được chọn | Xóa/sửa từng key đang được đọc rồi kỳ vọng kết quả nguyên tử |
| Thống kê số lần tra cứu | `LongAdder` cho bộ đếm tần suất cao; đo latency ở rìa API | `counter++` trên field dùng chung; log đầy đủ hostname nhạy cảm vào mọi request |

Nếu dùng `ConcurrentHashMap.computeIfAbsent(...)` để ghi cache, hàm tính toán phải ngắn, không gọi đệ quy vào cùng map và tránh giữ khóa trong lúc thực hiện I/O chậm. Một phương án cho lookup tốn thời gian là lưu một `CompletableFuture` cho key, để tác vụ được khởi động một lần, các caller cùng chờ kết quả, và phần tử lỗi được loại bỏ có điều kiện sau khi hoàn thành. Phải kiểm soát timeout, hủy, số yêu cầu đang chạy và kích thước cache. Một `CompletableFuture` duy nhất bị giữ mãi sau khi lỗi sẽ biến lỗi tạm thời thành lỗi thường trực.

Chẳng hạn, nếu gọi dịch vụ ngoài để lấy IP, nên phân tách ba việc:

```text
lookup(host, policy)
    |
    +-- đọc snapshot cấu hình và chính sách hiện tại
    |
    +-- tìm cache hợp lệ theo key / version
    |       +-- hit: lọc IPv4/IPv6 rồi trả kết quả
    |
    +-- miss: gộp các lookup cùng key, có giới hạn đồng thời
            +-- thành công: chỉ cache kết quả còn hợp lệ
            +-- thất bại: áp dụng retry/negative-TTL theo loại lỗi
```

Không chặn toàn bộ resolver bằng `synchronized` bao trùm lời gọi mạng. Khóa toàn cục kiểu đó biến truy vấn chậm của một hostname thành điểm nghẽn cho mọi hostname khác. Nếu có refresh nền, quản lý vòng đời executor, giới hạn hàng đợi và ngừng nhận tác vụ khi hệ thống đóng; không để thread nền tự tích lũy không kiểm soát.

## 6. Xử lý lỗi và tính đúng đắn của hợp đồng API

Resolver triển khai cả hai phương thức `lookupByName(String, LookupPolicy)` và `lookupByAddress(byte[])`, đều có thể ném `UnknownHostException`. Cần phân biệt:

- **Không có override**: ví dụ ủy quyền trực tiếp cho `builtinResolver`; ngoại lệ và kết quả của resolver tích hợp được giữ theo hợp đồng của nó.
- **Có override nhưng không khớp policy**: báo không tìm được địa chỉ phù hợp; không trả về họ địa chỉ bị cấm.
- **Cấu hình mới không hợp lệ**: từ chối ở bước `replaceOverrides`, giữ snapshot cũ nguyên vẹn; không công bố một phần bảng.
- **Lỗi hệ thống bên ngoài**: xác định khi nào thử lại, khi nào trả `UnknownHostException`, khi nào dùng bản ghi cũ nếu chính sách cho phép. Không đánh đồng lỗi hạ tầng tạm thời với việc hostname thực sự không tồn tại.
- **Tên đầu vào và địa chỉ không đáng tin**: cần có giới hạn độ dài, miền được phép override, kiểm tra dữ liệu cấu hình và danh sách địa chỉ hợp lệ theo yêu cầu nghiệp vụ. Một bản ghi bị đưa tới IP nội bộ hoặc IP không mong đợi có thể ảnh hưởng trực tiếp đến an toàn kết nối.

Mã mẫu là cơ sở cho bảng override được quản trị tin cậy, chưa phải một resolver DNS tổng quát. Trường hợp cần biểu diễn nhiều hostname trên một IP, địa chỉ có scope IPv6, canonical name, IDN, literal address hoặc các yêu cầu chuẩn hóa tên đặc thù, hãy xác định và kiểm thử từng quy tắc trước khi dùng trong sản phẩm.

## 7. Kiểm thử đồng thời và quan sát khi chạy

Một bài kiểm thử tốt cần chứng minh **hành vi khi có đua tranh**, không chỉ thử một lookup thành công:

1. **Thay snapshot khi nhiều luồng đọc**: tạo nhiều tác vụ lookup và một luồng liên tục thay giữa hai cấu hình hợp lệ A/B. Kiểm tra mỗi kết quả thuộc trọn A hoặc trọn B; không xuất hiện danh sách IP bị trộn hoặc `ConcurrentModificationException`.
2. **Giữ bản sao độc lập**: sau `replaceOverrides(...)`, sửa `ArrayList` và `HashMap` gốc; kết quả lookup phải giữ nguyên cho tới lần thay snapshot tiếp theo.
3. **Lookup thuận và ngược**: với một snapshot cố định, mọi IP override phải tra ngược ra hostname dự kiến; thử cấu hình có hai host chung một IP để chắc chắn bước nạp từ chối nguyên tử.
4. **Chính sách IPv4/IPv6**: chuẩn bị dữ liệu có cả hai họ địa chỉ; kiểm tra lọc và ưu tiên theo `LookupPolicy`, cùng trường hợp chỉ còn địa chỉ bị cấm.
5. **Tính đúng đắn của fallback**: hostname không có override và địa chỉ không có reverse override phải được chuyển cho resolver tích hợp; không có vòng lặp gọi lại `InetAddress` từ custom resolver.
6. **Cache và lỗi**: nếu bổ sung cache, kiểm tra TTL dương/âm, lỗi tạm thời, nhiều luồng miss cùng key, timeout và giới hạn số phần tử. Kiểm tra cả việc kết quả cũ còn tồn tại qua cache của `InetAddress`.
7. **Thử nghiệm tích hợp**: chạy một JVM riêng với đăng ký SPI thật, kiểm tra provider được chọn và hành vi qua `InetAddress`. Tách bài kiểm thử thành các JVM sạch khi cần loại bỏ ảnh hưởng của provider đã được khởi tạo hoặc cache tồn tại trước đó.

Để tạo tranh chấp đồng thời có kiểm soát, dùng `ExecutorService` với `CountDownLatch` cho nhiều tác vụ bắt đầu cùng lúc; đo thành công/thất bại theo từng phiên bản. Kết quả đi qua cache JDK có thể khiến provider không được gọi với tần suất giả định, vì vậy nên có cả bài kiểm thử trực tiếp logic của resolver và bài kiểm thử tích hợp qua SPI. Khi chạy thực tế, quan sát số lần lookup, tỷ lệ hit/miss cache tự xây dựng, lỗi phân giải, số yêu cầu đồng thời, p95/p99 độ trễ và phiên bản cấu hình đang được công bố.

## 8. Checklist trước khi đưa vào môi trường thực tế

- [ ] Xác nhận ứng dụng chạy trên JDK có hỗ trợ `InetAddressResolverProvider` / `InetAddressResolver`, đăng ký provider đúng kiểu classpath hoặc module.
- [ ] Bất kỳ dữ liệu nào chia sẻ giữa các luồng đều bất biến sau khi công bố hoặc có cơ chế đồng bộ rõ ràng.
- [ ] Mỗi lookup dùng một snapshot; không sửa map hay danh sách đang được các luồng đọc.
- [ ] Xử lý đầy đủ `LookupPolicy`, lookup ngược và các trường hợp `UnknownHostException`.
- [ ] Fallback dùng `Configuration.builtinResolver()`; không tự gọi lại `InetAddress.getByName(...)` từ resolver.
- [ ] Có chính sách TTL, giới hạn tài nguyên và quản lý lỗi nếu tự thêm cache hoặc thực hiện I/O bên ngoài.
- [ ] Đã kiểm thử reload, tải đồng thời, cache JDK và vòng đời thực tế của provider.

**Điểm cốt lõi:** tính thread-safe của resolver đến từ hợp đồng dữ liệu dùng chung và cách công bố trạng thái. Một snapshot bất biến giúp truy vấn nhất quán trong từng lời gọi; các phần phát sinh như cache, I/O, cập nhật nóng và cache của JVM cần được thiết kế và kiểm thử riêng theo cùng hợp đồng đó.
