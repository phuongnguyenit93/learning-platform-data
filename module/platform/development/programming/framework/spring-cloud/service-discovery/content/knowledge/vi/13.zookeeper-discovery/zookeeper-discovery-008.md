# Theo dõi thay đổi, lưu đệm và tái kết nối với Curator

Khi dùng ZooKeeper làm service registry, mỗi service instance thường được biểu diễn bằng một znode dưới cây `/services`. Consumer cần biết khi instance được thêm, thay đổi hoặc bị xóa để cập nhật danh sách endpoint đang dùng. ZooKeeper cung cấp watch để thông báo thay đổi; Apache Curator bổ sung các recipe giúp đăng ký watcher, duy trì cache cục bộ và xử lý kết nối lại dễ hơn.

Trong thực tế, consumer không nên gửi truy vấn ZooKeeper cho mọi request nghiệp vụ. Một cache cục bộ như Curator `ServiceCache` hoặc `CuratorCache` giữ danh sách instance gần nhất và cập nhật khi có thay đổi. Tuy nhiên, cache chỉ là góc nhìn cục bộ có thể cũ trong thời gian mất kết nối. Ứng dụng vẫn cần xử lý trạng thái kết nối, session expiration, đăng ký ephemeral và đối soát dữ liệu sau khi reconnect.

## 1. Cấu trúc service registry trong ZooKeeper

Một mô hình đơn giản tổ chức service theo tên và mỗi instance thành một znode riêng:

```text
/services
  /inventory-service
    /instance-a
    /instance-b
  /payment-service
    /instance-c
```

Mỗi znode instance lưu payload mô tả địa chỉ kết nối và metadata, ví dụ:

```json
{
  "name": "inventory-service",
  "id": "instance-a",
  "address": "10.20.1.15",
  "port": 8081,
  "metadata": {
    "zone": "ap-southeast-1a",
    "version": "2.4.1"
  }
}
```

Trong mô hình phổ biến, instance đăng ký bằng ephemeral znode. Znode này gắn với ZooKeeper session của tiến trình đăng ký; khi session hết hạn, ZooKeeper tự xóa ephemeral node. Điều đó giúp registry dọn những instance của client đã mất session, nhưng cũng có nghĩa ứng dụng phải đăng ký lại sau khi session mới được tạo.

ZooKeeper không tự kiểm tra HTTP health endpoint của service. Ephemeral node phản ánh trạng thái session của client đăng ký, không phải bảo đảm rằng ứng dụng vẫn xử lý request tốt. Nếu cần health check nghiệp vụ, phải bổ sung cơ chế kiểm tra riêng hoặc tích hợp với nền tảng health monitoring.

## 2. Watch của ZooKeeper hoạt động như thế nào?

Watch là cơ chế để client nhận thông báo khi một znode hoặc danh sách con thay đổi. Ví dụ, consumer có thể theo dõi children của `/services/inventory-service` để biết instance nào đang được đăng ký.

Watch cơ bản của ZooKeeper có một số đặc điểm quan trọng:

- Watch truyền thống là one-shot: sau khi nhận sự kiện, client cần đăng ký watch mới nếu muốn tiếp tục theo dõi.
- Sự kiện watch là tín hiệu báo dữ liệu đã thay đổi, không phải một bản ghi sự kiện đầy đủ có thể phát lại.
- Nhiều thay đổi xảy ra giữa hai lần đọc có thể được quan sát như một trạng thái mới nhất; watch không phải event log bảo đảm nhận đủ từng thay đổi trung gian.
- Khi kết nối hoặc session bị gián đoạn, watcher cần được thiết lập lại theo trạng thái kết nối và phiên làm việc.
- Khi nhận sự kiện, cách an toàn thường là đọc lại trạng thái hiện tại thay vì suy luận toàn bộ registry chỉ từ một event.

Ví dụ, nếu một instance được tạo rồi xóa rất nhanh trước khi consumer đọc lại children, consumer có thể chỉ thấy danh sách cuối cùng mà không quan sát được đầy đủ cả hai thao tác. Vì vậy, watch phù hợp để duy trì một bản nhìn hiện tại của registry; nếu cần audit mọi thay đổi, cần một event log hoặc hệ thống messaging riêng.

## 3. Curator giúp quản lý watch và cache

Apache Curator cung cấp các abstraction cao hơn API ZooKeeper thuần:

| Thành phần | Mục đích | Khi nên dùng |
| --- | --- | --- |
| `CuratorFramework` | Quản lý kết nối, retry và thao tác ZooKeeper | Hầu hết ứng dụng dùng Curator |
| `ServiceDiscovery` | Đăng ký và tra cứu service instance theo recipe của Curator | Ứng dụng cần service registry dựa trên ZooKeeper |
| `ServiceCache` | Cache danh sách instance của một service và thông báo khi danh sách thay đổi | Consumer thường xuyên tra cứu cùng một service |
| `CuratorCache` | Cache một znode hoặc cây znodes tổng quát, nhận sự kiện create/change/delete | Theo dõi metadata hoặc cấu trúc registry tự thiết kế |
| `ConnectionStateListener` | Nhận trạng thái kết nối `SUSPENDED`, `RECONNECTED`, `LOST`... | Phục hồi cache và registration khi mạng/session thay đổi |

Với service discovery theo recipe chuẩn, ưu tiên `ServiceDiscovery` và `ServiceCache` vì chúng hiểu cấu trúc service instance của Curator. Dùng `CuratorCache` khi cần theo dõi cây znode tùy chỉnh hoặc muốn kiểm soát cách ánh xạ dữ liệu.

Ở các phiên bản Curator hiện đại, `CuratorCache` là API cache tổng quát được ưu tiên thay cho các recipe cũ như `NodeCache`, `PathChildrenCache` hoặc `TreeCache`. Dự án dùng Curator phiên bản cũ có thể còn các API này; cần kiểm tra version và tài liệu tương ứng trước khi nâng cấp.

## 4. Tạo CuratorFramework và kết nối đến ZooKeeper

CuratorFramework quản lý session với ensemble ZooKeeper, retry thao tác theo chính sách đã cấu hình và phát trạng thái kết nối cho listener.

```java
import org.apache.curator.RetryPolicy;
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.retry.ExponentialBackoffRetry;

public final class ZooKeeperClientFactory {

    private ZooKeeperClientFactory() {}

    public static CuratorFramework create(String connectString) {
        RetryPolicy retryPolicy = new ExponentialBackoffRetry(1_000, 5);

        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(connectString)
                .sessionTimeoutMs(60_000)
                .connectionTimeoutMs(15_000)
                .retryPolicy(retryPolicy)
                .build();

        client.start();
        return client;
    }
}
```

Khởi tạo client với danh sách server trong ensemble, ví dụ `zk-1:2181,zk-2:2181,zk-3:2181`. `start()` khởi động kết nối bất đồng bộ; nó không đồng nghĩa client đã kết nối thành công. Nếu ứng dụng cần chờ kết nối ban đầu, có thể gọi:

```java
boolean connected = client.blockUntilConnected(15, TimeUnit.SECONDS);
if (!connected) {
    throw new IllegalStateException("Cannot connect to ZooKeeper ensemble");
}
```

Không nên tạo một CuratorFramework mới cho từng request. Thông thường một client được quản lý theo vòng đời ứng dụng và được đóng khi ứng dụng shutdown.

## 5. Theo dõi service bằng ServiceCache

`ServiceCache` là lựa chọn phù hợp khi ứng dụng sử dụng Curator Service Discovery. Nó giữ danh sách instance của một service trong bộ nhớ và thông báo khi cache thay đổi.

Ví dụ khởi tạo ServiceDiscovery và ServiceCache:

```java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.x.discovery.ServiceCache;
import org.apache.curator.x.discovery.ServiceDiscovery;
import org.apache.curator.x.discovery.ServiceDiscoveryBuilder;
import org.apache.curator.x.discovery.ServiceInstance;
import org.apache.curator.x.discovery.details.JsonInstanceSerializer;

public class InventoryRegistry {

    private static final String BASE_PATH = "/services";

    private final CuratorFramework client;
    private final ServiceDiscovery<InstancePayload> discovery;
    private final ServiceCache<InstancePayload> inventoryCache;

    public InventoryRegistry(CuratorFramework client) throws Exception {
        this.client = client;

        JsonInstanceSerializer<InstancePayload> serializer =
                new JsonInstanceSerializer<>(InstancePayload.class);

        this.discovery = ServiceDiscoveryBuilder
                .builder(InstancePayload.class)
                .client(client)
                .basePath(BASE_PATH)
                .serializer(serializer)
                .build();

        discovery.start();

        this.inventoryCache = discovery.serviceCacheBuilder()
                .name("inventory-service")
                .build();

        inventoryCache.start();
    }

    public List<ServiceInstance<InstancePayload>> getInstances() {
        return inventoryCache.getInstances();
    }

    public void close() throws IOException {
        inventoryCache.close();
        discovery.close();
    }
}
```

`InstancePayload` là lớp payload do ứng dụng định nghĩa và cần có cấu trúc tương thích với serializer đã chọn. Ví dụ này tập trung vào vòng đời cache; trong ứng dụng thật cần quản lý `CuratorFramework`, `ServiceDiscovery` và `ServiceCache` bằng Spring bean hoặc một lifecycle component để chúng được đóng đúng thứ tự.

Đăng ký một instance bằng `ServiceDiscovery`:

```java
ServiceInstance<InstancePayload> instance = ServiceInstance
        .<InstancePayload>builder()
        .name("inventory-service")
        .id("inventory-10-20-1-15-8081")
        .address("10.20.1.15")
        .port(8081)
        .payload(new InstancePayload("2.4.1", "ap-southeast-1a"))
        .build();

discovery.registerService(instance);
```

Với loại registration động mặc định của Curator Service Discovery, instance thường được lưu dưới dạng ephemeral znode. Nếu ứng dụng tự thiết kế persistent node hoặc loại registration khác, phải hiểu rõ ai chịu trách nhiệm dọn dữ liệu cũ.

## 6. Nhận thông báo khi ServiceCache thay đổi

Consumer có thể đăng ký `ServiceCacheListener` để phản ứng khi danh sách instance được cập nhật hoặc trạng thái kết nối thay đổi:

```java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.x.discovery.ServiceCacheListener;

inventoryCache.addListener(new ServiceCacheListener() {

    @Override
    public void cacheChanged() {
        List<ServiceInstance<InstancePayload>> instances =
                inventoryCache.getInstances();

        // Rebuild an immutable local snapshot for request handling.
        updateRoutingSnapshot(instances);
    }

    @Override
    public void stateChanged(
            CuratorFramework client,
            ConnectionState newState) {
        handleConnectionState(newState);
    }
});
```

Listener nên làm việc ngắn gọn: đọc snapshot hiện tại, cập nhật cấu trúc dữ liệu bất biến hoặc phát tín hiệu cho thành phần khác. Tránh thực hiện request mạng dài, thao tác blocking hoặc logic nghiệp vụ nặng ngay trong callback vì có thể làm chậm luồng xử lý event.

Sau `inventoryCache.start()`, ứng dụng có thể đọc `getInstances()` để lấy snapshot hiện tại. Nếu cần biết cache đã hoàn tất giai đoạn khởi tạo trước khi nhận traffic, hãy xây dựng readiness barrier theo cơ chế của version Curator đang dùng và chỉ đánh dấu consumer sẵn sàng sau khi có tín hiệu initialization phù hợp. Không coi việc gọi `start()` là bằng chứng cache đã đầy đủ.

## 7. Dùng CuratorCache cho cây znode tùy chỉnh

Nếu registry có schema riêng, `CuratorCache` cho phép theo dõi các znode create, change và delete dưới một path. Ví dụ theo dõi `/services/inventory-service`:

```java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.recipes.cache.CuratorCache;
import org.apache.curator.framework.recipes.cache.CuratorCacheListener;

CuratorCache cache = CuratorCache.builder(
        curatorFramework,
        "/services/inventory-service"
).build();

CuratorCacheListener listener = CuratorCacheListener.builder()
        .forCreates(node -> onInstanceCreated(node))
        .forChanges((oldNode, newNode) -> onInstanceChanged(oldNode, newNode))
        .forDeletes(node -> onInstanceDeleted(node))
        .forInitialized(() -> markCacheInitialized())
        .build();

cache.listenable().addListener(listener);
cache.start();
```

Khi cache được khởi tạo, có thể đọc snapshot các node mà Curator đang giữ:

```java
cache.stream().forEach(this::loadInitialNode);
```

`forInitialized` hữu ích để phân biệt giai đoạn dựng cache ban đầu với các thay đổi tiếp theo. Tên API và overload có thể khác giữa các bản Curator; hãy dùng API đúng với dependency trong dự án. Nếu cần một snapshot nhất quán ở tầng ứng dụng, cần đồng bộ thao tác dựng snapshot với callback cập nhật để tránh ghi đè thay đổi mới bằng dữ liệu khởi tạo cũ.

`CuratorCache` là cache tổng quát cho znode. Nó không tự hiểu service name, địa chỉ, port, metadata hoặc chính sách chọn instance. Ứng dụng phải deserialize payload, kiểm tra dữ liệu và tự ánh xạ sang mô hình instance.

## 8. Vì sao cache cục bộ hữu ích?

Không có cache, mỗi request có thể phải truy vấn ZooKeeper để lấy danh sách service instance. Điều này làm tăng độ trễ, tải lên ensemble và khiến request nghiệp vụ phụ thuộc trực tiếp vào khả năng phản hồi của ZooKeeper.

Cache giúp:

- Đọc danh sách instance từ bộ nhớ cục bộ với độ trễ thấp.
- Tái sử dụng snapshot cho nhiều request.
- Cập nhật danh sách khi nhận watch/event thay vì polling liên tục.
- Giảm số lần đọc ZooKeeper trong đường xử lý request.
- Tiếp tục có dữ liệu gần nhất trong một khoảng gián đoạn ngắn, nếu chính sách ứng dụng cho phép.

Nhưng cache cũng tạo ra rủi ro stale data. Khi consumer mất kết nối, nó có thể vẫn giữ instance đã chết hoặc không biết instance mới vừa đăng ký. Vì thế, cache cần có trạng thái freshness/connection đi kèm; không nên chỉ lưu danh sách endpoint mà bỏ qua trạng thái của nguồn dữ liệu.

Một snapshot routing có thể bao gồm thời điểm cập nhật, trạng thái kết nối và danh sách instance:

```java
public record RegistrySnapshot<T>(
        Instant updatedAt,
        boolean connected,
        List<ServiceInstance<T>> instances
) {}
```

Khi callback nhận thay đổi, tạo snapshot mới bất biến rồi thay thế snapshot hiện tại bằng một thao tác atomic. Request thread chỉ đọc snapshot, không sửa collection đang được listener cập nhật.

## 9. Trạng thái kết nối của Curator

Curator cung cấp `ConnectionStateListener` để ứng dụng nhận biết tình trạng kết nối ZooKeeper. Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Hành động gợi ý |
| --- | --- | --- |
| `CONNECTED` | Kết nối ban đầu đã được thiết lập | Bắt đầu sử dụng cache sau khi initialization hoàn tất |
| `SUSPENDED` | Kết nối tạm thời bị gián đoạn; session chưa được xác nhận là mất | Đánh dấu dữ liệu có thể stale, hạn chế quyết định phụ thuộc registry mới nhất |
| `RECONNECTED` | Kết nối được khôi phục với session còn hiệu lực | Xác nhận cache/watch tiếp tục hoạt động và làm mới snapshot khi cần |
| `LOST` | Session đã hết hạn | Coi ephemeral registration gắn với session cũ đã mất; đăng ký lại sau khi có session mới |
| `READ_ONLY` | Client kết nối ở chế độ chỉ đọc nếu ensemble cho phép | Không thực hiện thao tác ghi/đăng ký; chỉ đọc khi chính sách cho phép |

Ví dụ listener:

```java
curatorFramework.getConnectionStateListenable().addListener(
        (client, state) -> {
            switch (state) {
                case CONNECTED -> onConnected();
                case SUSPENDED -> markRegistryStale();
                case RECONNECTED -> reconcileAfterReconnect();
                case LOST -> handleExpiredSession();
                case READ_ONLY -> markReadOnly();
            }
        }
);
```

Các trạng thái phản ánh kết nối/session của Curator, không phải health của từng service instance. Không được dùng `CONNECTED` để kết luận mọi provider đều khỏe hoặc dùng `SUSPENDED` để kết luận mọi instance đã chết.

## 10. Phân biệt SUSPENDED, RECONNECTED và LOST

Đây là phần quan trọng nhất khi xử lý reconnect:

### SUSPENDED: tạm thời mất kết nối

Client chưa thể trao đổi với ZooKeeper. Session có thể vẫn còn hiệu lực, nhưng ứng dụng chưa biết chắc các thay đổi registry mới nhất. Cache vẫn chứa dữ liệu trước đó, vì vậy nên đánh dấu snapshot là stale hoặc degraded.

Trong giai đoạn này:

- Không xóa toàn bộ instance chỉ vì mất kết nối ZooKeeper.
- Không xem cache cũ là dữ liệu chắc chắn còn đúng.
- Có thể tiếp tục phục vụ theo chính sách stale-read nếu nghiệp vụ chấp nhận.
- Giới hạn thời gian dùng cache cũ và phát cảnh báo nếu mất kết nối kéo dài.

### RECONNECTED: kết nối được khôi phục

Curator đã kết nối lại. Nếu session còn hiệu lực, ephemeral nodes của client có thể vẫn tồn tại. Recipe của Curator có thể khôi phục việc theo dõi; ứng dụng cần chờ cache được cập nhật và đối soát snapshot trước khi đánh dấu registry fresh.

Không nên tự suy ra rằng mọi event xảy ra trong thời gian mất kết nối đã được giao lần lượt. Watch truyền thống không phải event log. Hãy đọc lại trạng thái hiện tại hoặc dùng cache recipe đã quản lý việc đồng bộ lại.

### LOST: session hết hạn

`LOST` nghĩa là ZooKeeper session đã hết hạn. Ephemeral znodes gắn với session cũ bị xóa bởi ZooKeeper. Curator có thể thiết lập session mới khi kết nối lại, nhưng những ephemeral registrations của ứng dụng phải được tạo lại bằng session mới.

Ứng dụng cần:

1. Đánh dấu registration cũ không còn hiệu lực.
2. Chờ Curator có session/kết nối mới.
3. Đăng ký lại service instance bằng `ServiceDiscovery.registerService()` hoặc cơ chế registration tương ứng.
4. Xác nhận znode instance xuất hiện trong registry.
5. Chờ cache consumer được khởi tạo/cập nhật trước khi đánh dấu dữ liệu fresh.

Curator recipes có thể tự quản lý một phần watcher và lifecycle nội bộ, nhưng không nên giả định mọi znode do ứng dụng tự tạo đều được phục hồi tự động. Cần xác định rõ thành phần nào chịu trách nhiệm re-register ephemeral service.

## 11. Retry policy không thay thế session recovery

`RetryPolicy` của Curator xử lý việc thử lại các thao tác khi gặp lỗi tạm thời. Ví dụ `ExponentialBackoffRetry` tăng thời gian chờ giữa các lần retry. Retry hữu ích với timeout hoặc mất kết nối ngắn, nhưng không thể làm session đã hết hạn trở lại hợp lệ.

Phân biệt:

- **Retry thao tác:** thử lại một lệnh đọc/ghi khi lỗi tạm thời.
- **Reconnect:** thiết lập lại kết nối đến ZooKeeper ensemble.
- **Session recovery:** xử lý khi session cũ hết hạn và client có session mới.
- **Registration recovery:** tạo lại ephemeral znodes đã bị xóa do session expiration.
- **Cache reconciliation:** đồng bộ lại snapshot từ trạng thái ZooKeeper hiện tại.

Các bước này liên quan nhưng không đồng nhất. Chỉ cấu hình retry policy không đủ để bảo đảm service instance tự xuất hiện lại sau `LOST`.

## 12. Mẫu phục hồi registration sau LOST

Một thành phần quản lý service registration có thể phản ứng với `LOST` và `RECONNECTED`. Mã dưới đây là phác thảo lifecycle; cần điều chỉnh theo cách ứng dụng tạo `ServiceDiscovery` và theo phiên bản Curator:

```java
public class RegistrationLifecycle implements ConnectionStateListener {

    private final ServiceDiscovery<InstancePayload> discovery;
    private final ServiceInstance<InstancePayload> localInstance;
    private final AtomicBoolean registered = new AtomicBoolean(false);

    public RegistrationLifecycle(
            ServiceDiscovery<InstancePayload> discovery,
            ServiceInstance<InstancePayload> localInstance) {
        this.discovery = discovery;
        this.localInstance = localInstance;
    }

    @Override
    public void stateChanged(CuratorFramework client, ConnectionState state) {
        if (state == ConnectionState.SUSPENDED) {
            markRegistrationUncertain();
            return;
        }

        if (state == ConnectionState.LOST) {
            registered.set(false);
            markRegistrationLost();
            return;
        }

        if (state == ConnectionState.RECONNECTED && !registered.get()) {
            registerAgain();
        }
    }

    private void registerAgain() {
        try {
            discovery.registerService(localInstance);
            registered.set(true);
            markRegistrationRestored();
        } catch (Exception e) {
            registered.set(false);
            scheduleRegistrationRetry(e);
        }
    }
}
```

Đây là ví dụ minh họa ý tưởng, không phải một implementation retry hoàn chỉnh. Trong hệ thống thật, cần tránh đăng ký trùng khi Curator recipe đã tự phục hồi registration, xử lý race giữa nhiều callback, retry có giới hạn/backoff, và xác minh registration tồn tại trước khi cập nhật trạng thái thành công. Có thể dùng một registration manager idempotent để gom trách nhiệm này.

Không gọi thao tác blocking dài trực tiếp trong `ConnectionStateListener`. Nên đẩy công việc phục hồi sang executor có quản lý, tránh chặn luồng event của Curator.

## 13. Dùng cache để chọn instance và gọi service

Consumer đọc snapshot từ `ServiceCache`, sau đó áp dụng chính sách chọn instance. Ví dụ đơn giản chọn một instance trong danh sách:

```java
public Optional<ServiceInstance<InstancePayload>> chooseInstance(
        List<ServiceInstance<InstancePayload>> instances) {

    if (instances == null || instances.isEmpty()) {
        return Optional.empty();
    }

    int index = ThreadLocalRandom.current().nextInt(instances.size());
    return Optional.of(instances.get(index));
}
```

Ví dụ này chỉ minh họa bước chọn. Trong production cần loại bỏ instance không hợp lệ, kiểm tra metadata/zone nếu có policy, áp dụng timeout và xử lý lỗi kết nối. Nếu request thất bại vì instance vừa bị xóa, consumer có thể làm mới snapshot và thử instance khác khi thao tác an toàn để retry.

Không nên giữ một `ServiceInstance` đã chọn quá lâu rồi dùng cho nhiều request như địa chỉ bất biến. Hãy lấy snapshot mới nhất theo chính sách cache và xử lý lỗi khi instance không còn tồn tại.

## 14. Tránh race condition khi cập nhật cache

Một consumer có thể nhận nhiều callback gần nhau. Nếu callback sửa trực tiếp một `ArrayList` mà request thread cũng đang đọc, ứng dụng có thể gặp lỗi đồng thời hoặc thấy trạng thái nửa cũ nửa mới.

Một cách đơn giản là tạo snapshot bất biến rồi thay thế tham chiếu bằng `AtomicReference`:

```java
public class InstanceSnapshotStore<T> {

    private final AtomicReference<List<ServiceInstance<T>>> current =
            new AtomicReference<>(List.of());

    public void replace(List<ServiceInstance<T>> instances) {
        current.set(List.copyOf(instances));
    }

    public List<ServiceInstance<T>> get() {
        return current.get();
    }
}
```

Callback cache lấy danh sách mới, kiểm tra dữ liệu rồi gọi `replace()`. Request thread chỉ đọc list bất biến. Nếu cần lưu thêm `connected`, `updatedAt` hoặc `initialized`, nên đặt tất cả vào một object snapshot và thay thế nguyên object trong một thao tác atomic để các trường luôn nhất quán với nhau.

## 15. Xử lý stale cache và chính sách khi ZooKeeper gián đoạn

Không có một chính sách đúng cho mọi hệ thống. Hãy quyết định rõ consumer có được tiếp tục dùng cache cũ hay phải ngừng gọi service khi ZooKeeper mất kết nối.

| Tình huống | Hướng xử lý thường dùng |
| --- | --- |
| Mất kết nối ngắn, cache gần đây | Có thể tiếp tục dùng snapshot cũ trong giới hạn thời gian cho phép |
| Mất kết nối kéo dài | Đánh dấu degraded, phát cảnh báo và giới hạn stale-read |
| Session `LOST` ở provider | Đăng ký lại ephemeral node và xác nhận registration mới |
| Session `LOST` ở consumer | Chờ cache/watch đồng bộ lại, không dùng trạng thái initialized cũ làm bằng chứng freshness |
| Cache chưa khởi tạo xong | Chưa đánh dấu readiness cho luồng phụ thuộc registry |
| Danh sách instance rỗng | Trả lỗi phù hợp, fallback theo kiến trúc hoặc chờ registry; không tự tạo endpoint giả |
| Instance vừa bị xóa nhưng cache chưa nhận event | Request timeout/failure cần kích hoạt refresh/retry có giới hạn |

Nếu nghiệp vụ yêu cầu định tuyến chính xác đến instance hiện đang khỏe, cache cũ có thể không đủ. Cần health check, timeout, circuit breaker hoặc một nguồn kiểm tra bổ sung. ZooKeeper session health không tương đương application health.

## 16. Cấu hình timeout, session và retry

Ba tham số thường cần xem xét:

- `sessionTimeoutMs`: thời gian ZooKeeper cho phép session không liên lạc trước khi xem là hết hạn. Giá trị quá thấp làm client dễ mất session khi mạng chập chờn; quá cao làm ephemeral node tồn tại lâu hơn khi client thực sự chết.
- `connectionTimeoutMs`: thời gian chờ thiết lập kết nối ban đầu hoặc một thao tác kết nối theo API Curator.
- `RetryPolicy`: số lần và khoảng thời gian thử lại thao tác khi lỗi.

Ví dụ cấu hình:

```java
RetryPolicy retryPolicy = new ExponentialBackoffRetry(
        1_000,  // base sleep time
        5,      // max retries
        10_000  // max sleep time
);

CuratorFramework client = CuratorFrameworkFactory.builder()
        .connectString("zk-1:2181,zk-2:2181,zk-3:2181")
        .sessionTimeoutMs(60_000)
        .connectionTimeoutMs(15_000)
        .retryPolicy(retryPolicy)
        .build();
```

Overload của `ExponentialBackoffRetry` phụ thuộc version Curator; nếu version đang dùng không có overload ba tham số, sử dụng constructor được hỗ trợ. Thời gian cần được chọn dựa trên latency mạng, thời gian failover và yêu cầu phát hiện instance lỗi, không sao chép máy móc giá trị ví dụ.

## 17. Kiểm thử watch, cache và reconnect

Một bài kiểm thử tốt cần mô phỏng cả thay đổi registry bình thường và lỗi kết nối/session:

1. Khởi động ZooKeeper ensemble và CuratorFramework.
2. Khởi động `ServiceDiscovery` và `ServiceCache`; chờ cache initialization.
3. Đăng ký instance A; xác nhận listener nhận thay đổi và snapshot có A.
4. Đăng ký instance B; xác nhận cache có A và B.
5. Hủy đăng ký A; xác nhận cache loại A sau khi cập nhật.
6. Ngắt mạng đến ensemble trong thời gian ngắn; xác nhận trạng thái `SUSPENDED` và snapshot được đánh dấu stale.
7. Khôi phục mạng trước session timeout; xác nhận `RECONNECTED`, cache tiếp tục theo dõi và snapshot được đối soát.
8. Tạo tình huống session hết hạn; xác nhận `LOST`, ephemeral registration biến mất và provider đăng ký lại bằng session mới.
9. Xác nhận consumer nhận lại instance sau khi registration và cache hội tụ.
10. Dừng ứng dụng bình thường; xác nhận cache, discovery và CuratorFramework được đóng đúng thứ tự.

Không chỉ kiểm tra callback đã chạy. Hãy kiểm tra nội dung cache sau mỗi giai đoạn, số lượng registration trong ZooKeeper, trạng thái session và khả năng gọi đến endpoint. Test reconnect cần có timeout đủ rộng để không phụ thuộc vào lịch chạy thread hoặc thời điểm mạng được phục hồi.

## 18. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không nhận event khi znode thay đổi | Watch chưa được đăng ký, cache chưa `start()` hoặc path sai | Kiểm tra base path, listener registration và log Curator |
| Chỉ nhận một lần thay đổi | Dùng watch one-shot trực tiếp nhưng không đăng ký lại | Dùng Curator recipe hoặc đọc lại và cài watch mới |
| Cache rỗng ngay sau `start()` | Cache đang khởi tạo bất đồng bộ hoặc registry chưa có instance | Chờ initialization signal và kiểm tra znode trực tiếp |
| Cache còn instance đã bị xóa | Mất kết nối, event chưa đến hoặc snapshot không được refresh | Kiểm tra ConnectionState, watch và đối soát children hiện tại |
| Instance biến mất sau reconnect | Session đã `LOST`, ephemeral node bị xóa | Kiểm tra listener state và đăng ký lại instance |
| Instance không xuất hiện lại sau `LOST` | Chưa có registration recovery hoặc retry chưa thành công | Kiểm tra registration manager và znode sau khi session mới hoạt động |
| Callback làm ứng dụng chậm | Listener thực hiện công việc blocking hoặc gọi mạng | Chuyển xử lý sang executor và giữ callback ngắn |
| Request dùng địa chỉ cũ | Consumer giữ instance URI quá lâu hoặc stale cache không có giới hạn | Dùng snapshot có timestamp, refresh và retry có giới hạn |
| Có nhiều instance trùng | Instance ID không duy nhất hoặc registration không idempotent | Kiểm tra path/ID và quy trình re-register |
| ZooKeeper báo session expired liên tục | Session timeout quá thấp, mạng không ổn định hoặc ensemble quá tải | Kiểm tra latency, timeout, GC pause và trạng thái quorum |

## 19. Đóng tài nguyên đúng vòng đời

CuratorFramework, ServiceDiscovery, ServiceCache và CuratorCache đều có lifecycle. Ứng dụng cần đóng cache/listener trước, sau đó đóng ServiceDiscovery và cuối cùng đóng CuratorFramework nếu ứng dụng sở hữu client đó.

Với Spring Boot, có thể quản lý bằng bean và `@PreDestroy` hoặc `SmartLifecycle`. Tránh tạo cache trong mỗi request rồi quên đóng; điều đó có thể làm tăng watcher, listener và tài nguyên bộ nhớ.

Nếu nhiều service cache dùng chung một `ServiceDiscovery`, cần xác định rõ component nào sở hữu và đóng `ServiceDiscovery`. Không để hai bean cùng đóng một tài nguyên mà không có quy ước ownership.

## 20. Checklist triển khai

- [ ] Chọn `ServiceCache` cho service discovery theo recipe hoặc `CuratorCache` cho cây znode tùy chỉnh.
- [ ] Hiểu watch ZooKeeper truyền thống là one-shot và không phải event log.
- [ ] Chờ cache initialization trước khi đánh dấu consumer readiness.
- [ ] Đọc instance từ snapshot cục bộ thay vì truy vấn ZooKeeper cho mỗi request.
- [ ] Cập nhật snapshot bất biến để tránh race giữa listener và request thread.
- [ ] Theo dõi `SUSPENDED`, `RECONNECTED`, `LOST` và `READ_ONLY`.
- [ ] Đánh dấu cache stale khi mất kết nối và đặt giới hạn stale-read.
- [ ] Đăng ký lại ephemeral service sau session expiration khi recipe không tự đảm nhiệm.
- [ ] Dùng retry policy cho lỗi tạm thời, đồng thời có logic session/registration recovery riêng.
- [ ] Kiểm thử instance create/change/delete, reconnect ngắn và session `LOST`.
- [ ] Đóng cache, discovery và CuratorFramework đúng thứ tự.

Curator giúp giảm độ phức tạp khi theo dõi thay đổi và duy trì cache từ ZooKeeper. `ServiceCache` phù hợp với danh sách instance của một service; `CuratorCache` phù hợp với cây znode tùy chỉnh. Cả hai giúp consumer có snapshot cục bộ nhanh, nhưng ứng dụng vẫn phải nhận biết dữ liệu stale, phân biệt reconnect với session expiration và phục hồi ephemeral registration sau `LOST`. Đó là điều kiện để service discovery tiếp tục đáng tin cậy khi mạng hoặc ZooKeeper ensemble gặp gián đoạn.
