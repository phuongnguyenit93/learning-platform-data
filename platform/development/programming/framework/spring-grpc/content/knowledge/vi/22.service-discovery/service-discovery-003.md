# Resolver tùy chỉnh

DNS resolver phù hợp khi tên dịch vụ được DNS quản lý. Nhưng trong một số hệ thống, endpoint đến từ service registry nội bộ, control plane, catalog theo vùng hoặc nguồn discovery có quy tắc riêng. Khi đó có thể viết **custom name resolver** cho grpc-java và sử dụng nó qua target URI trong Spring gRPC.

Resolver tùy chỉnh nhận target, tra cứu endpoint từ nguồn discovery và cung cấp danh sách địa chỉ cho channel. Nó không xử lý message RPC, không tự chọn instance cho từng request và không thay thế load balancer. Bài này tập trung vào `NameResolverProvider`, `NameResolver`, vòng đời bất đồng bộ, đăng ký scheme và kiểm thử resolver.

## 1. Khi nào cần resolver tùy chỉnh?

Hãy cân nhắc custom resolver khi DNS không thể biểu diễn hoặc cung cấp đủ thông tin discovery:

- Endpoint được lưu trong service registry có API riêng.
- Một service có nhiều endpoint theo region, tenant hoặc môi trường.
- Control plane cần trả thêm attributes hoặc service config cho gRPC channel.
- Ứng dụng cần nhận cập nhật endpoint theo event/watch thay vì chỉ tra cứu DNS.
- Quy tắc tên dịch vụ cần được ánh xạ sang tập địa chỉ theo chính sách của nền tảng.

Nếu DNS đã đáp ứng yêu cầu, nên dùng DNS resolver tiêu chuẩn. Custom resolver bổ sung code, trạng thái, retry, cache, bảo mật và trách nhiệm vận hành; không nên tạo chỉ để thay cú pháp target.

## 2. Target URI và custom scheme

Resolver được chọn từ scheme của target URI. Ví dụ:

```text
catalog:///orders
catalog:///inventory
```

Trong ví dụ, `catalog` là scheme do ứng dụng định nghĩa; `orders` và `inventory` là service key. Resolver sẽ diễn giải path và tra cứu catalog tương ứng.

Một URI target nên có hợp đồng rõ ràng:

| Thành phần | Quy ước ví dụ | Kiểm tra |
| --- | --- | --- |
| Scheme | `catalog` | Phải khớp `getDefaultScheme()` của provider |
| Authority | Để trống trong `catalog:///orders` | Không nhận authority ngoài hợp đồng |
| Path | `/orders` | Một service key hợp lệ, giới hạn độ dài/ký tự |
| Query | Không dùng trong ví dụ cơ bản | Nếu hỗ trợ region/version, phải parse và validate rõ |

Không đưa password, API key hoặc registry token vào URI. Target có thể xuất hiện trong log, exception, diagnostic hoặc telemetry. Credentials để gọi registry phải được lấy từ cấu hình bảo mật riêng.

## 3. Hai thành phần: NameResolverProvider và NameResolver

`NameResolverProvider` đăng ký scheme và tạo resolver cho target phù hợp. `NameResolver` thực hiện discovery và gửi kết quả tới channel.

| Thành phần | Trách nhiệm |
| --- | --- |
| `NameResolverProvider` | Khai báo scheme, priority/availability và tạo resolver từ URI |
| `NameResolver` | Tra cứu service key, phát endpoint, refresh và shutdown |
| Registry client | Gọi nguồn discovery, xác thực, timeout và chuyển dữ liệu registry thành địa chỉ |
| `NameResolver.Listener2` | Nhận kết quả phân giải hoặc lỗi |
| `ResolutionResult` | Mang danh sách `EquivalentAddressGroup` và attributes/service config tùy nhu cầu |
| Load balancer | Nhận địa chỉ và quyết định subchannel/endpoint cho RPC |

Provider không nên tự thực hiện lookup mạng. Việc đó thuộc resolver, thường thông qua một registry client bất đồng bộ được inject vào provider.

## 4. Định nghĩa hợp đồng với service registry

Giả sử registry trả về các socket address cho một service key. Ta định nghĩa một interface nhỏ để resolver không phụ thuộc trực tiếp vào HTTP client hoặc SDK cụ thể:

```java
import java.net.InetSocketAddress;
import java.util.List;
import java.util.concurrent.CompletionStage;

public interface ServiceCatalog {
    CompletionStage<List<InetSocketAddress>> lookup(String serviceName);
}
```

Implementation thực tế của `ServiceCatalog` chịu trách nhiệm:

- Kết nối registry bằng TLS và credentials phù hợp.
- Đặt timeout cho request và giới hạn số lần retry.
- Parse response, kiểm tra hostname/IP và port hợp lệ.
- Loại bỏ endpoint trùng hoặc không hợp lệ theo chính sách.
- Không trả về endpoint đã hết hạn hoặc không còn được publish.
- Không ghi token hoặc response nhạy cảm vào log.

Dùng `CompletionStage` để resolver không phải chặn thread trong lúc chờ registry. Với registry hỗ trợ watch/stream, có thể mở rộng interface để phát sự kiện endpoint thay đổi; khi đó phải quản lý subscription và hủy nó trong `shutdown()`.

## 5. Cài đặt NameResolverProvider

Provider nhận URI và tạo resolver. Ví dụ dưới đây chỉ chấp nhận target dạng `catalog:///service-name`, không có authority hoặc query:

```java
import io.grpc.NameResolver;
import io.grpc.NameResolverProvider;
import java.net.URI;

public final class CatalogNameResolverProvider
        extends NameResolverProvider {

    private final ServiceCatalog catalog;
    private final String serviceAuthority;

    public CatalogNameResolverProvider(
            ServiceCatalog catalog,
            String serviceAuthority) {
        this.catalog = catalog;
        this.serviceAuthority = serviceAuthority;
    }

    @Override
    protected boolean isAvailable() {
        return true;
    }

    @Override
    protected int priority() {
        return 5;
    }

    @Override
    public String getDefaultScheme() {
        return "catalog";
    }

    @Override
    public NameResolver newNameResolver(
            URI targetUri, NameResolver.Args args) {
        if (!"catalog".equals(targetUri.getScheme())) {
            return null;
        }

        String path = targetUri.getRawPath();
        boolean validPath = path != null
            && path.matches("/[a-z0-9][a-z0-9-]{0,62}");

        if (targetUri.getRawAuthority() != null
                || targetUri.getRawQuery() != null
                || !validPath) {
            throw new IllegalArgumentException(
                "Expected target catalog:///service-name");
        }

        String serviceName = path.substring(1);
        return new CatalogNameResolver(
            serviceName,
            serviceAuthority,
            catalog,
            args.getSynchronizationContext());
    }
}
```

`isAvailable()` và `priority()` cho registry biết provider có thể được dùng và mức ưu tiên của nó. `getDefaultScheme()` trả scheme `catalog`. `newNameResolver(...)` kiểm tra URI rồi tạo resolver. Nếu target sai cấu trúc, fail sớm với lỗi rõ ràng thay vì âm thầm tra cứu nhầm service.

`serviceAuthority` là danh tính dịch vụ logic mà resolver đại diện. Nó cần được chọn phù hợp với cách cấu hình TLS/authority của channel; không tùy tiện trả về IP endpoint nếu certificate được cấp cho hostname dịch vụ.

## 6. Cài đặt NameResolver bất đồng bộ

Resolver cần giữ listener, gọi registry bất đồng bộ và chuyển kết quả về gRPC `SynchronizationContext`. Ví dụ sau dùng generation counter để bỏ qua kết quả lookup cũ nếu đã có lần refresh mới hơn hoặc resolver đã shutdown:

```java
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;
import io.grpc.Status;
import io.grpc.SynchronizationContext;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicLong;

final class CatalogNameResolver extends NameResolver {

    private final String serviceName;
    private final String serviceAuthority;
    private final ServiceCatalog catalog;
    private final SynchronizationContext syncContext;
    private final AtomicLong generation = new AtomicLong();

    private volatile Listener2 listener;
    private volatile boolean shutdown;

    CatalogNameResolver(
            String serviceName,
            String serviceAuthority,
            ServiceCatalog catalog,
            SynchronizationContext syncContext) {
        this.serviceName = serviceName;
        this.serviceAuthority = serviceAuthority;
        this.catalog = catalog;
        this.syncContext = syncContext;
    }

    @Override
    public String getServiceAuthority() {
        return serviceAuthority;
    }

    @Override
    public void start(Listener2 listener) {
        this.listener = listener;
        refresh();
    }

    @Override
    public void refresh() {
        if (shutdown || listener == null) {
            return;
        }

        long requestGeneration = generation.incrementAndGet();
        final CompletionStage<List<InetSocketAddress>> lookup;
        try {
            lookup = catalog.lookup(serviceName);
        } catch (RuntimeException ex) {
            reportError(requestGeneration, ex);
            return;
        }

        lookup.whenComplete((addresses, error) ->
            syncContext.execute(() -> {
                if (shutdown || requestGeneration != generation.get()) {
                    return;
                }

                if (error != null) {
                    listener.onError(
                        Status.UNAVAILABLE
                            .withDescription("Service catalog lookup failed")
                            .withCause(error));
                    return;
                }

                if (addresses == null || addresses.isEmpty()) {
                    listener.onError(
                        Status.UNAVAILABLE.withDescription(
                            "No endpoint found for service"));
                    return;
                }

                List<EquivalentAddressGroup> groups = new ArrayList<>();
                for (InetSocketAddress address : addresses) {
                    groups.add(new EquivalentAddressGroup(address));
                }

                ResolutionResult result = ResolutionResult.newBuilder()
                    .setAddresses(groups)
                    .build();
                listener.onResult(result);
            }));
    }

    private void reportError(long requestGeneration, Throwable cause) {
        syncContext.execute(() -> {
            if (shutdown || requestGeneration != generation.get()) {
                return;
            }
            listener.onError(
                Status.UNAVAILABLE
                    .withDescription("Service catalog lookup failed")
                    .withCause(cause));
        });
    }

    @Override
    public void shutdown() {
        shutdown = true;
        generation.incrementAndGet();
    }
}
```

Đây là khung triển khai tập trung vào vòng đời resolver. Các import/API cụ thể cần khớp phiên bản grpc-java của dự án. Trong production, bổ sung kiểm tra từng `InetSocketAddress`, xử lý exception khi đăng ký callback, timeout và cơ chế hủy lookup. `CompletionStage` trong ví dụ không cung cấp handle hủy riêng; registry client thực tế nên hỗ trợ cancellation hoặc bảo đảm tác vụ có thời hạn hữu hạn.

Không gọi listener từ nhiều thread tùy tiện. `SynchronizationContext` giúp tuần tự hóa callback theo cơ chế gRPC. Generation counter ngăn kết quả cũ ghi đè endpoint mới sau một lần refresh nhanh hơn.

## 7. ResolutionResult và endpoint attributes

Resolver trả danh sách `EquivalentAddressGroup`, mỗi group chứa một hoặc nhiều `SocketAddress` tương đương. Với resolver đơn giản, mỗi endpoint có thể là một group riêng:

```java
List<EquivalentAddressGroup> groups = new ArrayList<>();
for (InetSocketAddress endpoint : endpoints) {
    groups.add(new EquivalentAddressGroup(endpoint));
}

NameResolver.ResolutionResult result =
    NameResolver.ResolutionResult.newBuilder()
        .setAddresses(groups)
        .build();
listener.onResult(result);
```

Khi cần, resolver có thể gắn `Attributes` vào group hoặc result để chuyển thông tin như region, zone hoặc endpoint metadata cho thành phần downstream. Chỉ đưa attributes không nhạy cảm và có schema ổn định; không đưa registry token, credential hay dữ liệu cá nhân vào attributes.

Nếu registry trả service config, resolver có thể cung cấp cấu hình tương ứng theo API grpc-java và policy của channel. Cần validate config và kiểm thử tương thích; không để dữ liệu registry không tin cậy tùy ý thay đổi retry hoặc load balancing policy của client.

## 8. Đăng ký resolver trong Spring gRPC

Tạo provider thành Spring bean là chưa đủ: provider phải được đăng ký với `NameResolverRegistry` **trước khi channel phân giải target**. Ví dụ tạo provider và channel theo thứ tự phụ thuộc bean:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.NameResolverRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersGrpcConfiguration {

    @Bean
    CatalogNameResolverProvider catalogResolverProvider(
            ServiceCatalog catalog) {
        return new CatalogNameResolverProvider(
            catalog,
            "orders.internal.example");
    }

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel(
            CatalogNameResolverProvider provider) {
        NameResolverRegistry.getDefaultRegistry().register(provider);

        return ManagedChannelBuilder
            .forTarget("catalog:///orders")
            .useTransportSecurity()
            .build();
    }
}
```

Ví dụ giả định `ServiceCatalog` đã được cấu hình và provider được đăng ký trước khi channel được build. Registry mặc định là phạm vi toàn JVM; tránh đăng ký lặp cùng provider trong mỗi request hoặc mỗi lần tạo stub. Nếu ứng dụng dùng starter Spring gRPC quản lý channel, hãy đăng ký provider ở bootstrap/configuration phase trước khi starter tạo channel, theo extension point mà phiên bản starter hỗ trợ.

Có thể dùng Java Service Provider Interface nếu provider có thể được khởi tạo theo cơ chế phù hợp của ứng dụng. Với provider cần dependency injection như registry client, đăng ký tường minh qua bootstrap thường dễ kiểm soát hơn. Dù chọn cách nào, channel phải được quản lý theo lifecycle ứng dụng và đóng khi shutdown.

## 9. Resolver, load balancer và health checking

Resolver chỉ công bố endpoint; load balancer chọn subchannel và xử lý việc pick cho RPC. Health checking là một cơ chế khác, xác định service có báo trạng thái phục vụ hay không.

| Thành phần | Trách nhiệm |
| --- | --- |
| Custom resolver | Tra cứu service key và phát endpoint list |
| Load balancer | Chọn endpoint/subchannel theo policy |
| Health checking | Theo dõi trạng thái phục vụ của gRPC service nếu được cấu hình |
| Retry policy | Quyết định retry RPC theo status, method và policy |
| Channel | Quản lý kết nối, transport và call lifecycle |

Không nhúng thuật toán round-robin vào resolver. Nếu registry trả nhiều endpoint, hãy để load balancer thực hiện lựa chọn. Resolver có thể lọc endpoint đã hết hạn hoặc bị đánh dấu không được publish, nhưng không nên tự suy diễn health nếu registry không cung cấp thông tin đó.

Khi endpoint bị xóa, resolver cần phát kết quả mới. Load balancer sau đó cập nhật subchannel; connection draining và RPC đang chạy cần được xử lý theo lifecycle của channel/server. Không coi việc registry xóa endpoint là bằng chứng mọi kết nối hiện hữu đã lập tức đóng.

## 10. Lỗi, retry và tài nguyên

Custom resolver trở thành một phần của control plane phía client, vì vậy phải giới hạn tác động khi registry gặp sự cố:

- **Timeout:** lookup cần thời hạn hữu hạn; không để một lần tra cứu treo vô hạn.
- **Retry/backoff:** retry có jitter và giới hạn, tránh tạo bão request khi registry unavailable.
- **Empty result:** báo resolution error hoặc áp dụng cache policy được định nghĩa; không tự tạo địa chỉ giả.
- **Stale endpoint:** quyết định có tiếp tục dùng kết quả cũ trong một khoảng grace period hay không; đặt giới hạn tuổi rõ ràng.
- **Cancellation:** bỏ qua kết quả lookup cũ sau refresh/shutdown và hủy tác vụ nếu registry client hỗ trợ.
- **Thread lifecycle:** dừng watch, scheduler và executor do resolver sở hữu; không shutdown executor do gRPC cung cấp.
- **Security:** xác thực registry, kiểm tra dữ liệu trả về và không log credentials.

`UNAVAILABLE` có thể phù hợp khi registry tạm thời không thể cung cấp endpoint. Target sai cấu trúc nên bị từ chối sớm; không biến lỗi cấu hình thành retry liên tục. Nếu resolver đã từng có endpoint hợp lệ, chính sách giữ endpoint cũ phải được thiết kế rõ để cân bằng availability và tính mới của discovery.

## 11. Kiểm thử custom resolver

Unit test resolver nên dùng fake `ServiceCatalog` để điều khiển kết quả và lỗi:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Target `catalog:///orders` hợp lệ | Provider tạo resolver cho service `orders` |
| Sai scheme | Provider không nhận target |
| Path sai hoặc có query không hỗ trợ | Bị từ chối rõ ràng |
| Registry trả một endpoint | Listener nhận một address group |
| Registry trả nhiều endpoint | Listener nhận đủ endpoint |
| Registry trả danh sách rỗng | Listener nhận resolution error theo policy |
| Registry timeout/failure | Listener nhận `UNAVAILABLE`; không treo callback |
| Refresh trong lúc lookup cũ còn chạy | Kết quả cũ không ghi đè kết quả mới |
| Shutdown trước khi lookup hoàn tất | Callback muộn bị bỏ qua; tài nguyên được giải phóng |
| Spring context đóng | Channel shutdown và registry watcher dừng |

Một integration test hữu ích khởi động gRPC server cục bộ trên port động, cấu hình fake catalog trả `InetSocketAddress("127.0.0.1", port)`, tạo channel bằng target `catalog:///orders` rồi gọi generated stub. Test chứng minh provider đã được đăng ký, resolver trả endpoint và channel thật sự gọi được server.

Ngoài test trong tiến trình, kiểm tra TLS authority/certificate, registry authentication, timeout và cập nhật endpoint trong môi trường gần production. In-process transport không kiểm tra việc kết nối TCP tới địa chỉ mà resolver trả về.

## 12. Bài tập vận dụng

Một nền tảng có registry nội bộ trả endpoint của `PaymentService` theo service key và region. Client Spring gRPC cần gọi `catalog:///payments` và nhận endpoint mới khi instance được thay thế.

**Yêu cầu:**

1. Định nghĩa URI contract cho scheme `catalog`, service key và tùy chọn region.
2. Viết `NameResolverProvider` kiểm tra scheme/path/query và tạo resolver.
3. Viết `NameResolver` tra cứu registry bất đồng bộ, phát `ResolutionResult` và xử lý lỗi.
4. Bảo đảm `refresh()` không để kết quả cũ ghi đè kết quả mới; `shutdown()` dừng watch/executor và bỏ callback muộn.
5. Đăng ký provider trước khi Spring gRPC channel được tạo; cấu hình TLS authority đúng với danh tính dịch vụ.
6. Dùng fake registry kiểm thử empty result, nhiều endpoint, timeout, refresh, shutdown và integration call tới server cục bộ.

**Câu hỏi tự kiểm tra:**

- `NameResolverProvider` khác `NameResolver` ở trách nhiệm nào?
- Vì sao lookup registry nên bất đồng bộ?
- `ResolutionResult` cung cấp dữ liệu gì cho channel?
- Resolver có nên tự round-robin giữa các endpoint không?
- Vì sao cần generation/version để bỏ kết quả lookup cũ?
- Khi nào resolver nên phát `UNAVAILABLE` và khi nào target phải bị từ chối ngay?
- Vì sao provider phải được đăng ký trước khi channel phân giải custom scheme?
- `getServiceAuthority()` liên quan thế nào tới danh tính TLS của dịch vụ?

**Ghi nhớ:** Custom resolver mở rộng service discovery bằng cách ánh xạ target URI sang endpoint từ nguồn riêng. `NameResolverProvider` đăng ký scheme và tạo resolver; `NameResolver` tra cứu bất đồng bộ, phát `ResolutionResult`, refresh và shutdown. Trong Spring gRPC, đăng ký provider trước khi tạo channel, giữ lookup có timeout/cancellation, để load balancer chọn endpoint và kiểm thử cả kết quả phân giải lẫn RPC thực tế.
