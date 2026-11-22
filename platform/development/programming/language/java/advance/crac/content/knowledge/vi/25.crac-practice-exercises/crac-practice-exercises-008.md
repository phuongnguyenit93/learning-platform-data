# Làm mới định danh khi khôi phục nhiều bản sao từ một ảnh

Một checkpoint CRaC lưu trạng thái của một tiến trình Java tại thời điểm tạo ảnh. Nếu cùng checkpoint được dùng để khôi phục nhiều instance, mỗi instance bắt đầu với một bản sao của heap và các object đã tồn tại trong ảnh. Điều này có thể bao gồm `static` field, singleton, UUID đã tạo, hostname, client ID, cờ leader, counter, lease metadata và trạng thái của các thư viện client.

Nếu ứng dụng tiếp tục dùng những giá trị đó như thể chúng thuộc riêng instance hiện tại, nhiều bản sao có thể tự nhận cùng một danh tính. Hệ quả có thể là service registry ghi đè endpoint, metric bị gộp, message consumer dùng trùng client ID, nhiều replica cùng nghĩ mình là leader, hoặc các instance cùng sử dụng một lease đã hết hạn.

Khi khôi phục nhiều bản sao từ một ảnh, cần phân biệt **danh tính ổn định của service** với **danh tính riêng của từng instance và từng lần chạy**. Mỗi process được restore phải nhận một incarnation ID mới, đọc lại thông tin nền tảng hiện tại, giành lease/session riêng và đăng ký endpoint mới trước khi nhận traffic.

## 1. Vì sao các bản sao có thể trùng định danh?

Giả sử một ứng dụng tạo ID khi khởi động:

```java
public final class InstanceInfo {
    public static final String INSTANCE_ID =
            UUID.randomUUID().toString();

    private InstanceInfo() {
    }
}
```

Khi ứng dụng khởi động lần đầu, class được khởi tạo và `INSTANCE_ID` nhận một giá trị. Nếu checkpoint được tạo sau thời điểm đó, giá trị này nằm trong trạng thái heap được lưu.

Khi cùng checkpoint được restore thành ba process, cả ba bản sao có thể bắt đầu với cùng giá trị `INSTANCE_ID`. `static final` không làm giá trị tự sinh lại; constructor hoặc static initializer cũng không chạy lại chỉ vì process được restore.

```text
Checkpoint generation 42
  INSTANCE_ID = "instance-a7"
          |
          +--------------------+--------------------+
          |                    |                    |
       Restore A            Restore B            Restore C
          |                    |                    |
   INSTANCE_ID=a7       INSTANCE_ID=a7       INSTANCE_ID=a7
```

Điều tương tự có thể xảy ra với:

- Hostname, IP hoặc port được đọc trước checkpoint.
- `client.id` của message broker hoặc HTTP client.
- Cờ `isLeader`, lock token hoặc lease ID.
- Counter dùng làm sequence number hoặc ID toàn cục.
- Random generator/PRNG có trạng thái nội bộ nằm trong heap.
- Session ID, TLS/session context hoặc credential tạm.
- Registration ID và heartbeat metadata trong service registry.

Một checkpoint không biết nó sẽ được restore một lần hay được nhân bản thành hàng trăm instance. Vì vậy, mọi giá trị chỉ đúng cho một process đang chạy phải được xem xét lại sau restore.

## 2. Phân biệt service identity, instance identity và incarnation identity

Không nên gom mọi loại định danh vào một trường `id`. Mỗi loại có vòng đời và phạm vi khác nhau.

| Loại định danh | Ví dụ | Có giống nhau giữa các bản sao không? | Khi nào thay đổi? |
|---|---|---|---|
| Service identity | `orders-api`, `billing-worker` | Có | Khi đổi tên logical service |
| Release/checkpoint identity | `orders-2026.11.13`, checkpoint generation 42 | Có trong cùng release | Khi build/release/checkpoint mới |
| Instance identity | Pod UID, VM instance ID, worker ID | Không | Khi nền tảng tạo instance mới |
| Process incarnation ID | UUID cho một lần process chạy/restore | Không | Mỗi lần khởi chạy hoặc restore process |
| Lease/fencing token | Lease epoch 1087 | Không; do hệ thống phối hợp cấp | Mỗi lần giành quyền sở hữu lease |
| Request/trace identity | Request ID, trace ID | Không; theo request/trace | Mỗi request hoặc trace mới |

Ví dụ, ba replica của `orders-api` có thể dùng chung `serviceName` và `releaseId`, nhưng cần `instanceId` khác nhau. Nếu một pod restore lại process nhiều lần, `instanceId` của pod có thể giữ nguyên nhưng `incarnationId` nên đổi để phân biệt process mới với process cũ.

Một cấu trúc dữ liệu rõ ràng:

```java
import java.time.Instant;

public record RuntimeIdentity(
        String serviceName,
        String releaseId,
        String instanceId,
        String incarnationId,
        Instant createdAt) {
}
```

`serviceName` và `releaseId` có thể đến từ cấu hình bất biến của release. `instanceId` nên đến từ nền tảng đang chạy hoặc một identity provider có thẩm quyền. `incarnationId` được tạo mới cho mỗi process restore. Không lưu một `RuntimeIdentity` đầy đủ vào checkpoint rồi tái sử dụng nguyên vẹn trên mọi bản sao.

## 3. Làm mới định danh ở `afterRestore`

Mỗi process được restore cần chạy logic tạo identity mới trước khi bắt đầu nhận công việc. CRaC cung cấp callback `afterRestore(...)` cho `Resource` đã đăng ký. Đây là vị trí phù hợp để:

1. Đọc instance metadata hiện tại từ nền tảng hoặc identity provider.
2. Tạo `incarnationId` mới cho process vừa restore.
3. Cập nhật một identity snapshot nhất quán trong ứng dụng.
4. Tạo lại client/session dùng identity mới.
5. Đăng ký endpoint và heartbeat mới.
6. Giành lease hoặc tham gia leader election nếu nghiệp vụ yêu cầu.
7. Mở scheduler/consumer và readiness sau khi các bước bắt buộc hoàn tất.

Không chờ request đầu tiên mới tạo identity. Một background worker, metrics exporter hoặc scheduled task có thể chạy trước request đầu tiên và sử dụng định danh cũ. Hãy đặt gate để mọi thành phần phụ thuộc identity chỉ hoạt động sau khi identity mới đã được cài đặt.

## 4. Chọn nguồn tạo identity mới

Có nhiều nguồn có thể cấp định danh, nhưng chúng có mức bảo đảm khác nhau.

| Nguồn | Ưu điểm | Lưu ý |
|---|---|---|
| UUID ngẫu nhiên sau restore | Đơn giản, không cần round trip tới dịch vụ ngoài | Phải dùng nguồn entropy phù hợp; không tái sử dụng PRNG object đã được snapshot |
| Pod UID/container instance ID từ platform | Phản ánh identity do orchestrator cấp | Phải đọc giá trị hiện tại; environment variable có thể đã bị chụp vào process trước checkpoint |
| VM/cloud instance ID | Định danh instance do cloud/platform cấp | Cần truy cập metadata service và xác thực nguồn dữ liệu |
| Identity service | Có thể cấp ID, token hoặc certificate theo policy | Phụ thuộc mạng và availability của dịch vụ cấp identity |
| Database sequence/unique constraint | Cấp ID theo kho dữ liệu có tính nhất quán | Có chi phí truy cập database; cần xử lý retry và lỗi kết nối |
| Lease/coordination service | Cấp quyền sở hữu cùng fencing token | Dùng khi cần ownership/leader, không chỉ để tạo chuỗi ID |

Với ID chỉ cần xác suất trùng cực thấp, UUID mới tạo sau restore thường đủ. Với ID là cơ sở bảo vệ quyền ghi, leader election hoặc fencing, cần một hệ thống phối hợp có tính nhất quán; UUID ngẫu nhiên không thay thế lease.

### Cẩn thận với environment variable được checkpoint

Environment variable của process là dữ liệu process đã đọc khi khởi chạy. Nếu checkpoint được tạo trong môi trường prepare, giá trị như `HOSTNAME`, `POD_NAME` hoặc `INSTANCE_ID` có thể vẫn là giá trị của môi trường prepare sau restore. Việc deployment đặt environment variable khác cho container không tự bảo đảm vùng nhớ environment của process đã checkpoint được thay thế.

Nếu cần metadata hiện tại của Kubernetes hoặc cloud:

- Dùng một nguồn được cập nhật theo instance hiện tại, chẳng hạn metadata endpoint hoặc projected volume được nền tảng hỗ trợ.
- Nếu đọc từ file mount, mở lại file sau restore; đừng dựa vào file descriptor cũ đã nằm trong checkpoint.
- Nếu gọi Kubernetes API, làm mới token/service account credential theo cơ chế rotation của platform.
- Xác thực rằng metadata trả về thuộc đúng pod/VM đang chạy.
- Nếu không thể lấy identity đáng tin cậy, giữ readiness đóng và báo lỗi phục hồi.

Với Kubernetes Downward API, cần cân nhắc cách expose dữ liệu. Một giá trị inject qua environment có thể bị giữ trong process snapshot; một projected file có thể được cập nhật bởi kubelet nhưng ứng dụng vẫn nên mở lại file sau restore và xác minh hành vi trên cluster/runtime thật.

## 5. Thiết kế identity holder có thể thay thế atomically

Tránh giữ identity cũ trong nhiều `static final` field hoặc singleton riêng lẻ. Hãy gom định danh runtime thành một snapshot immutable, rồi thay toàn bộ snapshot bằng một thao tác atomic.

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

final class RuntimeIdentityHolder {
    private final AtomicReference<RuntimeIdentity> current =
            new AtomicReference<>();

    RuntimeIdentity current() {
        RuntimeIdentity identity = current.get();
        if (identity == null) {
            throw new IllegalStateException("Runtime identity is not ready");
        }
        return identity;
    }

    void install(RuntimeIdentity next) {
        current.set(next);
    }

    void clear() {
        current.set(null);
    }
}
```

Các service cần identity nên đọc từ holder tại thời điểm thực hiện thao tác. Không copy identity vào field bất biến của từng bean lúc constructor chạy nếu bean đó sẽ sống qua restore. Nếu một thư viện bắt buộc nhận client ID trong constructor, tạo lại client sau restore hoặc dùng factory/provider để tạo client với identity mới.

Snapshot immutable giúp request không nhìn thấy tổ hợp nửa cũ nửa mới, ví dụ `instanceId` mới nhưng `advertiseAddress` hoặc `releaseGeneration` cũ. Nếu identity gồm nhiều trường có quan hệ với nhau, hãy thay chúng cùng lúc.

## 6. Ví dụ nguồn identity và CRaC resource

Ví dụ sau minh họa một resource duy nhất điều phối refresh identity. Các interface `PlatformIdentityProvider`, `IdentityAwareComponents` và `ReadinessGate` là abstraction của ứng dụng.

```java
import java.time.Instant;
import java.util.UUID;

import org.crac.Context;
import org.crac.Resource;

final class IdentityRefreshResource implements Resource {
    private final String serviceName;
    private final String releaseId;
    private final PlatformIdentityProvider platform;
    private final RuntimeIdentityHolder identityHolder;
    private final IdentityAwareComponents components;
    private final ReadinessGate readiness;

    IdentityRefreshResource(
            String serviceName,
            String releaseId,
            PlatformIdentityProvider platform,
            RuntimeIdentityHolder identityHolder,
            IdentityAwareComponents components,
            ReadinessGate readiness) {
        this.serviceName = serviceName;
        this.releaseId = releaseId;
        this.platform = platform;
        this.identityHolder = identityHolder;
        this.components = components;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        components.stopCreatingWork();
        components.awaitInFlightWork();
        components.releaseEphemeralOwnership();
        identityHolder.clear();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();

        String instanceId = platform.currentInstanceId();
        String incarnationId = UUID.randomUUID().toString();

        RuntimeIdentity next = new RuntimeIdentity(
                serviceName,
                releaseId,
                instanceId,
                incarnationId,
                Instant.now()
        );

        identityHolder.install(next);
        components.recreateClients(next);
        components.registerInstance(next);
        components.acquireRequiredLeases(next);
        components.verifyDependencies(next);
        components.resumeWork(next);
        readiness.acceptTraffic();
    }
}
```

Đăng ký resource trong giai đoạn khởi tạo ứng dụng:

```java
import org.crac.Core;

Core.getGlobalContext().register(identityRefreshResource);
```

`UUID.randomUUID()` trong ví dụ được gọi bên trong `afterRestore`, không phải static initializer. Với yêu cầu định danh có tính bảo mật hoặc uniqueness nghiêm ngặt, nên dùng identity provider/OS entropy đã được xác minh cho runtime; không giữ một `Random` hoặc `SecureRandom` instance đã có trạng thái trong checkpoint rồi tiếp tục dùng nó cho tất cả clone. Nếu identity dùng để cấp quyền ghi, cần lease/fencing token từ hệ thống phối hợp thay vì chỉ UUID.

Trong production, các thao tác `components.*` cần timeout, retry có giới hạn và xử lý lỗi. Nếu lấy instance ID, đăng ký hoặc giành lease thất bại, callback nên báo lỗi và readiness vẫn đóng. Không bắt exception rồi tiếp tục như thể identity đã hợp lệ.

### Vì sao gom thứ tự vào một coordinator?

Một ứng dụng có thể có nhiều `Resource`: resource cho database pool, HTTP server, metrics, message consumer và identity. Nếu chúng tự chạy độc lập mà không có hợp đồng thứ tự, một component có thể mở listener trước khi identity mới được cài hoặc consumer có thể bắt đầu trước khi lease được cấp.

Một coordinator giúp định nghĩa thứ tự rõ ràng:

```text
afterRestore
    |
    v
Read current platform identity
    |
    v
Create new process incarnation
    |
    v
Install immutable identity snapshot
    |
    v
Recreate clients and sessions
    |
    v
Register endpoint / acquire lease
    |
    v
Verify dependencies
    |
    v
Start consumers and scheduled work
    |
    v
Open readiness
```

Nếu framework hoặc thư viện đã có CRaC resource riêng, coordinator cần phối hợp với integration đó theo API được hỗ trợ. Không đăng ký một resource khác để đóng/mở cùng client nếu không có ownership rõ ràng.

## 7. Làm mới service registration và network endpoint

Service registry thường ánh xạ logical service tới các instance endpoint. Nếu ba bản restore cùng đăng ký với một `instanceId`, một registration có thể ghi đè registration khác hoặc heartbeat của replica này cập nhật nhầm replica kia.

Sau restore, mỗi replica cần:

1. Xác định bind address và port hiện tại.
2. Tạo incarnation ID mới.
3. Đăng ký endpoint bằng identity mới.
4. Gắn health/heartbeat với đúng incarnation.
5. Chỉ nhận traffic sau khi listener đã bind và registration hợp lệ.
6. Hủy registration cũ nếu còn tồn tại và nếu instance có quyền thu hồi.

Không dùng hostname hoặc IP từ checkpoint như một identity bất biến. Trong môi trường container, pod IP và port có thể khác sau restore. Trong VM, địa chỉ NIC hoặc route có thể thay đổi theo network attachment. Hãy đọc thông tin hiện tại từ platform và kiểm tra listener thực tế.

### Tránh xóa nhầm registration của replica khác

Khi dọn registration cũ, thao tác nên có compare-and-delete theo `instanceId`/`incarnationId` hoặc registration version. Nếu replica A và B trùng ID, A có thể xóa registration mới do B vừa tạo. Unique identity là điều kiện để cleanup an toàn.

## 8. Lease, leader election và fencing token

Một field như `isLeader = true` trong singleton không chứng minh instance vẫn giữ quyền leader sau restore. Lease có thể đã hết hạn trong thời gian process dừng. Nếu nhiều replica cùng restore, tất cả có thể cùng mang `isLeader = true` từ snapshot.

Sau restore:

- Xóa/đánh dấu stale trạng thái leader cũ.
- Tham gia lại leader election hoặc yêu cầu lease mới.
- Chỉ chạy tác vụ độc quyền sau khi lease được cấp.
- Gia hạn lease theo clock hiện tại.
- Dùng fencing token tăng đơn điệu để hệ thống đích từ chối thao tác từ owner cũ.

Fencing token đặc biệt quan trọng khi một process cũ có thể sống tiếp trong lúc bản restore mới đã giành lease. Lease service cấp epoch mới, ví dụ 1088; database/storage nhận thao tác chỉ khi token không cũ hơn token đã chấp nhận. Nhờ vậy, owner cũ với token 1087 không thể ghi đè trạng thái do owner mới quản lý.

UUID chỉ phân biệt instance. Nó không thay thế fencing token vì UUID không cho biết owner nào mới hơn.

## 9. Message consumer, scheduler và worker identity

Nếu checkpoint chứa message consumer hoặc scheduled job, nhiều bản sao có thể cùng tiếp tục với client/member ID hoặc trạng thái scheduler giống nhau.

### Message broker

- Tạo client/session mới sau restore theo hướng dẫn của client library.
- Để broker cấp member ID mới khi join consumer group nếu protocol hỗ trợ.
- Không tái sử dụng connection/session hoặc heartbeat state từ checkpoint nếu thư viện không hỗ trợ.
- Xác nhận subscription và partition assignment trước khi xử lý message.
- Dùng idempotency key và cơ chế commit/ack phù hợp để xử lý redelivery.
- Nếu cần client ID duy nhất, tạo ID từ instance/incarnation mới.

### Scheduled job

- Không khôi phục cờ `schedulerStarted` hoặc `jobOwner` như bằng chứng quyền sở hữu hiện tại.
- Chỉ khởi động job sau khi identity và lease đã sẵn sàng.
- Dùng distributed lock/lease nếu job phải chạy duy nhất toàn cụm.
- Lưu tiến độ job dài hạn ở storage bền vững.
- Thiết kế job idempotent để retry sau restore không tạo side effect trùng.

### Worker pool

Thread name hoặc worker number cục bộ có thể giống nhau giữa các replica mà không sao nếu chúng chỉ dùng để debug. Nhưng nếu worker ID được gửi tới hệ thống ngoài, dùng làm khóa ownership hoặc ghi vào registry, cần gắn thêm instance/incarnation identity.

## 10. Counter, sequence và random state

Một counter trong heap có thể được nhân bản cùng giá trị. Nếu dùng counter đó để cấp ID toàn cục, các replica có thể tạo trùng số:

```java
static final AtomicLong NEXT_ORDER_ID = new AtomicLong(1_000_000);
```

Sau khi clone, nhiều instance có thể cùng cấp `1_000_001`. Hãy dùng database sequence, ID service, UUID/ULID phù hợp hoặc ID có cấu trúc chứa một thành phần instance duy nhất và counter cục bộ.

Random generator cũng có trạng thái. Nếu một object PRNG được checkpoint rồi nhân bản, các bản sao có thể tạo ra cùng chuỗi số tiếp theo. Không dùng `Random` đã được snapshot làm nguồn duy nhất cho ID hoặc token cần uniqueness/bảo mật.

Các lựa chọn:

- Cấp ID từ dịch vụ bên ngoài có uniqueness guarantee.
- Tạo một nguồn entropy mới sau restore từ OS/provider được hỗ trợ.
- Dùng UUID v4 hoặc ID scheme khác dựa trên nguồn entropy đáng tin cậy.
- Kết hợp instance/incarnation ID với counter cục bộ nếu cần ID có thứ tự trong một instance.
- Dùng unique constraint ở database để phát hiện và từ chối collision.

Đối với cryptographic key, nonce hoặc token bảo mật, tuân thủ hướng dẫn của `SecureRandom`, provider và runtime CRaC đang dùng. Không tự sao chép seed, không tự ghép timestamp với counter rồi coi đó là entropy an toàn.

## 11. Metrics, logging và tracing cần identity mới

Nếu nhiều replica dùng chung metric labels hoặc logger identity từ checkpoint, dữ liệu observability có thể bị nhập nhằng.

### Metrics

- Giữ `service.name`, environment và release label ổn định.
- Gắn instance label do platform cung cấp hoặc incarnation label theo policy backend.
- Tránh dùng cùng một series identity cho nhiều process độc lập.
- Rebind gauge tới pool/client mới sau restore.
- Không đưa UUID mới vào mọi metric label nếu cardinality sẽ tăng không kiểm soát.

### Logging

- Thêm instance/incarnation metadata vào log context/MDC.
- Tạo lại appender/session nếu output network cần reconnect.
- Không để nhiều clone ghi chung một file local hoặc dùng chung appender identity khi không được hỗ trợ.
- Giữ timestamp gốc của log event được tạo trước checkpoint; thêm restore marker riêng.

### Tracing

- Tạo span startup/restore mới cho mỗi incarnation.
- Không dùng trace ID cố định từ checkpoint cho mọi replica.
- Tạo lại exporter/client nếu connection cũ không còn hợp lệ.
- Với công việc được resume, tạo span mới hoặc link tới trace context bền vững thay vì tiếp tục một span cũ trong heap nếu semantics không phù hợp.

## 12. Ví dụ thực hành: ba bản sao từ cùng checkpoint

Giả sử một ứng dụng `inventory-api` được warm-up và checkpoint với metadata sau:

```text
serviceName       = inventory-api
releaseId         = release-2026.11.13.4
instanceId        = prepare-runner-01
incarnationId     = prepare-incarnation-01
leader            = true
consumerClientId  = inventory-consumer-01
```

Deployment restore cùng checkpoint thành ba instance. Mục tiêu sau restore:

| Trường | Replica A | Replica B | Replica C |
|---|---|---|---|
| serviceName | inventory-api | inventory-api | inventory-api |
| releaseId | release-2026.11.13.4 | release-2026.11.13.4 | release-2026.11.13.4 |
| instanceId | pod-uid-a | pod-uid-b | pod-uid-c |
| incarnationId | inc-a-new | inc-b-new | inc-c-new |
| leader | Được bầu lại | Được bầu lại | Được bầu lại |
| consumer session | Session mới A | Session mới B | Session mới C |
| endpoint | IP/port A | IP/port B | IP/port C |

Trình tự thực hành:

1. Tạo checkpoint từ một process prepare, không dùng identity đó làm identity production.
2. Khởi chạy ba bản restore trong môi trường kiểm thử cô lập.
3. Mỗi bản restore đọc identity từ platform hiện tại hoặc identity provider.
4. Mỗi process tạo incarnation ID mới.
5. Mỗi process cài identity snapshot vào holder.
6. Mỗi process tạo client/session mới với ID riêng.
7. Mỗi process đăng ký endpoint riêng.
8. Nếu chỉ một replica được chạy job độc quyền, chúng tham gia election và chỉ owner có lease/fencing token hợp lệ mới được chạy.
9. Xác nhận ba registration, heartbeat và metric series không ghi đè nhau.
10. Gửi traffic và kiểm tra log/tracing cho biết đúng replica xử lý request.

Điểm cần xác minh là instance identity không lấy từ `prepare-runner-01` đã nằm trong checkpoint. Nếu platform không cung cấp identity mới qua một kênh có thể đọc sau restore, ứng dụng phải gọi một identity service hoặc tạo incarnation độc lập rồi đăng ký với control plane.

## 13. Kiểm thử collision và hành vi khi identity service lỗi

Không chỉ test trường hợp bình thường. Cần kiểm tra:

- Nhiều replica restore đồng thời từ cùng checkpoint.
- Identity provider trả về cùng ID do cấu hình sai.
- Metadata endpoint timeout hoặc trả metadata của instance khác.
- Token để truy cập platform metadata đã hết hạn.
- Service registry từ chối đăng ký vì identity đã tồn tại.
- Lease service không truy cập được.
- Process cũ vẫn còn sống và giữ lease cũ.
- Một replica restore hai lần với cùng pod identity nhưng incarnation khác nhau.
- Cleanup registration cũ chạy trễ sau khi replica mới đã đăng ký.

Khi identity không thể xác minh, không nên fallback sang ID cũ trong checkpoint. Giữ readiness đóng, retry có giới hạn và phát cảnh báo. Nếu cần fallback, chỉ dùng nguồn identity có uniqueness guarantee tương đương và đã được thiết kế trước.

### Kiểm tra uniqueness trong test

Một integration test có thể thu thập identity của tất cả replica và assert uniqueness:

```java
Set<String> instanceIds = restoredInstances.stream()
        .map(instance -> instance.identity().instanceId())
        .collect(Collectors.toSet());

if (instanceIds.size() != restoredInstances.size()) {
    throw new AssertionError("Restored instances share an instance ID");
}

Set<String> incarnationIds = restoredInstances.stream()
        .map(instance -> instance.identity().incarnationId())
        .collect(Collectors.toSet());

if (incarnationIds.size() != restoredInstances.size()) {
    throw new AssertionError("Restored processes share an incarnation ID");
}
```

Đoạn test giả định `restoredInstances` là danh sách kết quả thu thập từ từng process và có các import `java.util.Set`, `java.util.stream.Collectors`. Trong test nhiều process/container, dữ liệu nên được thu qua endpoint test hoặc registry thay vì static state của test runner.

## 14. Quan sát identity trong production

Để phát hiện clone trùng identity, nên theo dõi:

| Dữ liệu | Mục đích |
|---|---|
| service name và release ID | Nhóm các replica cùng service/release |
| instance ID | Phân biệt instance do platform cấp |
| incarnation ID | Phân biệt các lần process restore/restart |
| checkpoint generation | Truy nguyên nguồn snapshot |
| identity created timestamp | Phát hiện identity cũ bất thường |
| lease/fencing epoch | Xác định owner mới nhất |
| registration version | Theo dõi service registry update/cleanup |
| restore result/readiness time | Phát hiện lỗi trong chuỗi phục hồi |

Có thể phát một log event `application.restore` sau khi identity mới được cài. Event nên chứa service, release, instance, incarnation và checkpoint generation. Không đưa secret, token hoặc toàn bộ metadata nhạy cảm vào log.

Một số metric hữu ích:

- Số instance đang hoạt động theo service/release.
- Số identity collision hoặc registration conflict.
- Số lần lease acquisition thất bại.
- Số lần fencing token cũ bị từ chối.
- Thời gian từ `afterRestore` bắt đầu tới identity ready.
- Thời gian từ identity ready tới readiness accepting.

Tránh dùng incarnation UUID làm label trên mọi metric nếu backend có cardinality limit. Có thể giữ UUID trong log/tracing resource attribute và dùng metric labels có retention/cardinality được kiểm soát.

## 15. Các lỗi thường gặp

### Tạo UUID trong static initializer

UUID được tạo trước checkpoint và được sao chép tới mọi replica. Tạo incarnation mới trong `afterRestore` hoặc lấy từ identity provider.

### Nghĩ `final` có nghĩa mỗi replica có giá trị riêng

`static final` giữ nguyên giá trị đã checkpoint. `final` chỉ ngăn gán lại reference trong process, không tự tạo identity mới.

### Dùng hostname từ process environment

Environment có thể là giá trị của prepare process được lưu trong snapshot. Đọc metadata hiện tại qua kênh được cập nhật sau restore và xác minh.

### Dùng UUID làm distributed lock

UUID phân biệt instance nhưng không chứng minh quyền sở hữu. Dùng lease/leader election và fencing token từ hệ thống phối hợp.

### Giữ cờ leader và consumer session cũ

Nhiều clone có thể cùng nghĩ mình là leader hoặc dùng trạng thái session cũ. Tạo session mới và giành quyền sở hữu lại sau restore.

### Mở listener trước khi identity mới được cài

Request đầu tiên có thể được xử lý với registration hoặc log context cũ. Cài identity, tạo client, đăng ký endpoint và kiểm tra health trước readiness.

### Xóa registration cũ bằng key không unique

Một replica có thể xóa registration của replica khác. Dùng compare-and-delete theo incarnation/registration version.

### Dùng counter/PRNG được clone để cấp ID

Các bản sao có thể tiếp tục từ cùng counter hoặc random state. Dùng identity service, OS-backed entropy mới hoặc unique constraint.

## 16. Checklist triển khai

- [ ] Đã phân biệt service identity, release/checkpoint ID, instance ID và process incarnation ID.
- [ ] Không dùng identity của prepare process làm identity production.
- [ ] Mỗi lần restore tạo incarnation ID mới.
- [ ] Instance ID được đọc từ platform hiện tại hoặc identity provider có thẩm quyền.
- [ ] Không giả định environment variable đã checkpoint tự đổi theo container mới.
- [ ] Runtime identity được cài atomically trước khi component phụ thuộc bắt đầu.
- [ ] Client/session được tạo lại với identity mới.
- [ ] Service registry và heartbeat dùng instance/incarnation ID riêng.
- [ ] Lease/leader election được thực hiện lại sau restore.
- [ ] Hệ thống ghi có fencing token để ngăn owner cũ ghi dữ liệu.
- [ ] Consumer, scheduler và worker không tái sử dụng ownership state cũ.
- [ ] Counter và PRNG đã checkpoint không được dùng làm nguồn ID toàn cục.
- [ ] Readiness chỉ mở sau khi identity, endpoint, lease và dependency bắt buộc sẵn sàng.
- [ ] Cleanup registration cũ dùng compare-and-delete an toàn.
- [ ] Đã test nhiều replica restore đồng thời và kiểm tra uniqueness.
- [ ] Đã test identity/lease provider lỗi và xác nhận instance không dùng lại ID cũ.

## 17. Kết luận

Khôi phục nhiều bản sao từ cùng một checkpoint có thể nhân bản mọi định danh đã nằm trong heap. Một `static UUID`, hostname, broker client ID, cờ leader hoặc lease token được tạo trước checkpoint không tự thay đổi khi restore. Vì vậy, ứng dụng cần tách service identity ổn định khỏi instance identity và process incarnation identity.

Hãy làm mới identity trong `afterRestore`, đọc metadata từ nguồn của instance hiện tại, tạo incarnation mới và cài một identity snapshot nhất quán trước khi khởi động client, listener, consumer hoặc scheduler. Với tài nguyên độc quyền, giành lease mới và dùng fencing token; với service registry, heartbeat và metrics, gắn định danh riêng cho từng replica. Chỉ mở readiness sau khi toàn bộ identity và dependency bắt buộc đã được xác minh. Như vậy, nhiều bản sao có thể dùng chung một checkpoint generation mà vẫn hoạt động như những instance độc lập.
