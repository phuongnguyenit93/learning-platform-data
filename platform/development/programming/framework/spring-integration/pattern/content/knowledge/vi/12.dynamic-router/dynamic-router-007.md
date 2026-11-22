# Kiểm soát quyền thay đổi route

## 1. Bài toán: ai được phép đổi đường đi của message?

Một hệ thống tích hợp xử lý đơn hàng qua các luồng **Domestic**, **Export** và **Manual Review**. Bình thường, đơn thị trường Việt Nam đến nhóm nội địa, đơn quốc tế được chuyển cho nhóm xuất khẩu và đơn cần kiểm tra rủi ro phải qua bước duyệt. Khi có thay đổi vận hành, quản trị viên muốn chuyển tạm đơn của một thị trường sang nhánh xử lý khác **mà không triển khai lại ứng dụng**.

Đó là một nhu cầu của **Dynamic Router** trong Enterprise Integration Patterns (EIP): quy tắc xác định điểm đến có thể được cập nhật khi hệ thống đang chạy. Sự linh hoạt này tạo ra một câu hỏi nghiêm trọng hơn việc viết biểu thức định tuyến:

> Nếu một người dùng, một producer hoặc một service bất kỳ có thể đổi route, họ có thể khiến message đi qua nhánh không được kiểm soát, bỏ qua kiểm tra hoặc làm ngừng xử lý nghiệp vụ không?

**Kiểm soát quyền thay đổi route** nghĩa là chỉ các chủ thể được ủy quyền, trong phạm vi được phép, mới có thể tạo/sửa/kích hoạt hoặc khôi phục một phiên bản chính sách định tuyến. Việc cập nhật phải được **kiểm tra, ghi nhận, có phiên bản, có thể quan sát và có đường phục hồi**.

Bài này nằm trong chương **Dynamic router** của module **SPRING_INTEGRATION_PATTERN**, phục vụ mục tiêu học triển khai Enterprise Integration Patterns với Spring Integration: xây dựng message flow ít phụ thuộc, dễ mở rộng với **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và theo dõi các nhánh xử lý. Ở đây, quyền sửa route là trọng tâm; chúng ta không coi một header do bên ngoài gửi là quyền thay đổi topology.

Sau bài học, bạn có thể phân biệt **data plane** và **control plane**, thiết kế RBAC/ABAC cho thay đổi route, giới hạn đích bằng allowlist, cập nhật chính sách có kiểm soát phiên bản, phân biệt lỗi quyền với lỗi routing và kiểm thử các trường hợp bị tấn công hoặc tranh chấp cập nhật.

## 2. Dynamic Router thực sự thay đổi điều gì?

Một Router thông thường đọc dữ liệu message và tính một **routing key**. Trong Dynamic Router, quy tắc tạo key, bảng ánh xạ hoặc danh sách người nhận có thể thay đổi theo thời gian.

Ví dụ:

| Thời điểm | Chính sách đang hoạt động | Kết quả cho `market="SG"` |
|---|---|---|
| 09:00 | Chỉ hỗ trợ VN/US | `UNSUPPORTED → orders.unmapped` |
| 09:10 | Đã duyệt chính sách thêm SG | `EXPORT → orders.export` |
| 09:30 | Nhánh export sự cố, kích hoạt phương án dự phòng | `REVIEW → orders.review` |
| 10:00 | Khôi phục chính sách đã kiểm thử | `EXPORT → orders.export` |

Lưu ý, thay đổi route không nhất thiết phải tạo channel/bean mới lúc runtime. Cách **an toàn và đơn giản hơn** là để topology và các destination channel ổn định, chỉ thay đổi **quy tắc chọn một trong các route đã cho phép**.

| Kiểu thay đổi | Tác động | Rủi ro |
|---|---|---|
| Thay đổi predicate/ngưỡng | Một nhóm message có thể đi nhánh khác | Bỏ qua kiểm duyệt do logic sai |
| Thay đổi bảng routing key → channel | Đích của một key thay đổi | Trỏ vào channel sai hoặc thiếu consumer |
| Thêm/xóa recipient của một Recipient List Router | Số người nhận của message thay đổi | Mất nhánh bắt buộc hoặc rò dữ liệu |
| Tạo/xóa endpoint, flow, channel động | Topology và vòng đời bean thay đổi | Lỗi cấu hình, quyền điều khiển hệ thống quá rộng |

**Nguyên tắc ưu tiên:** quyền thay đổi rule không đồng nghĩa với quyền tạo đích tùy ý hoặc bỏ các bước kiểm tra bắt buộc. Chỉ cấp quyền tối thiểu cho đúng loại thay đổi mà nghiệp vụ cần.

## 3. Tách data plane và control plane

**Data plane** nhận và định tuyến message nghiệp vụ. **Control plane** nhận yêu cầu sửa chính sách, xác thực/ủy quyền, phê duyệt và triển khai phiên bản route mới.

~~~mermaid
flowchart TB
    subgraph CONTROL["CONTROL PLANE — thay đổi chính sách"]
        USER["Route operator / admin"] --> API["Admin API / workflow"]
        API --> AUTH{"Authentication + authorization"}
        AUTH -->|"Từ chối"| DENY["403 / audit denied"]
        AUTH -->|"Cho phép"| VAL["Validate + approve"]
        VAL --> STORE["Versioned policy store"]
        STORE --> PUB["Publish approved revision"]
    end
    subgraph DATA["DATA PLANE — xử lý sự kiện"]
        IN["Gateway / broker adapter"] --> FILTER["Contract validation"]
        FILTER --> ROUTER{"Dynamic Router<br/>read active snapshot"}
        ROUTER --> DOM["orders.domestic"]
        ROUTER --> EXP["orders.export"]
        ROUTER --> REV["orders.review"]
        ROUTER --> UNK["orders.unmapped"]
    end
    PUB -.->|"Chỉ bản đã duyệt"| ROUTER
~~~

Hai loại message không được đánh đồng:

- `OrderCreated` là **dữ liệu** để Router quyết định theo quy tắc hiện hành.
- `RoutePolicyChange` là **lệnh quản trị** thay đổi quy tắc; chỉ một dịch vụ quản trị đáng tin cậy được áp dụng nó.

Producer gửi `headers['routeKey'] = 'orders.review'` hoặc `headers['isAdmin'] = true` **không trở thành quản trị viên**. Những giá trị ấy chỉ là dữ liệu do producer cung cấp, không thể thay thế principal đã xác thực và quyết định authorization phía server.

Đừng để route change đi chung một channel đầu vào công khai với sự kiện nghiệp vụ nếu chưa có ranh giới xác thực/phân quyền riêng. Việc tách control plane cũng giúp ghi nhận và khôi phục cấu hình độc lập với lưu lượng xử lý đơn hàng.

## 4. Những quyền cần phân biệt

Không nên chỉ có một role `ADMIN` toàn năng. Một hệ thống có thể phân chia quyền theo chức năng:

| Hành động | Reader | Operator | Approver | Route Administrator |
|---|---:|---:|---:|---:|
| Xem phiên bản đang chạy, lịch sử thay đổi | Có (trong phạm vi) | Có | Có | Có |
| Xem trước ảnh hưởng của một thay đổi | Có | Có | Có | Có |
| Tạo đề xuất thay đổi | Không | Có | Có | Có |
| Phê duyệt đề xuất | Không | Không | Có | Theo chính sách |
| Kích hoạt phiên bản đã duyệt | Không | Tùy quy trình | Tùy quy trình | Có |
| Rollback một phiên bản | Không | Đề xuất | Phê duyệt | Có, có audit |
| Đổi topology hoặc channel nhạy cảm | Không | Không | Không mặc định | Chỉ sau kiểm soát đặc biệt |

Đây là **ma trận mẫu**, không phải một role model có sẵn của Spring Integration. Doanh nghiệp có thể yêu cầu **separation of duties**: người đề xuất không phải người phê duyệt, đặc biệt đối với route thanh toán, danh tính hoặc dữ liệu cá nhân.

Ngoài role, cần chính sách theo **thuộc tính** (ABAC):

- Người dùng chỉ được sửa chính sách của tenant/đơn vị mà họ quản lý.
- Một số destination chỉ được sử dụng trong môi trường thử nghiệm.
- Rule của giao dịch rủi ro cao đòi duyệt thêm, dù người sửa có role phù hợp.
- Có thể giới hạn thời gian hiệu lực, quy mô rollout và số lượng thị trường bị ảnh hưởng.
- Quyền thực hiện lệnh phải dựa trên identity đáng tin, không chỉ dựa vào `tenantId` trong request body.

## 5. Threat model: nếu ai cũng đổi được route thì sao?

| Kịch bản | Hậu quả | Biện pháp |
|---|---|---|
| Producer giả mạo header quản trị | Thay đổi nhánh xử lý không được phép | Không cấp mutation từ data headers; identity tại control plane |
| API cho gửi tên channel tùy ý | Bypass validation, gửi message sang handler nhạy cảm | Allowlist routing key và destination cố định |
| Control Bus lộ ra ngoài | Gọi method/đổi cấu hình bean bằng biểu thức ngoài ý muốn | Không expose tùy ý; giới hạn quyền vận hành |
| Operator của tenant A sửa policy tenant B | Trộn dữ liệu hoặc vi phạm cách ly | Resource-level authorization/tenant isolation |
| Hai admin sửa đồng thời | Bản cập nhật sau ghi đè bản trước | Version/ETag, optimistic concurrency |
| Lệnh quản trị bị phát lại | Rule cũ quay lại hoặc lặp thay đổi | Command ID, version, audit, thời hạn |
| Bản cấu hình mới không có consumer | Message mắc kẹt/lỗi gửi | Validate topology + test canary trước activation |
| Một node dùng revision khác node khác | Cùng event đi route khác nhau | Versioned snapshots, đồng bộ và theo dõi rollout |

Rủi ro đáng chú ý nhất không chỉ là **không gửi được message**, mà còn là **gửi thành công đến nhánh không được phép**. Vì thế một dự án cần review các bất biến an toàn, ví dụ “mọi lệnh thanh toán phải được kiểm tra rủi ro” và “không tenant nào được route sang kho dữ liệu tenant khác”.

## 6. Định nghĩa hợp đồng thay đổi trước khi viết API

Hãy cho phép operator gửi **ý định nghiệp vụ** thay vì lệnh điều khiển bean:

~~~json
{
  "policyId": "order-market-routing",
  "expectedVersion": 12,
  "changeId": "CHG-2026-0102",
  "reason": "Temporary export maintenance",
  "rules": {
    "VN": "DOMESTIC",
    "US": "EXPORT",
    "SG": "REVIEW"
  }
}
~~~

**Không nhận** dữ liệu kiểu:

~~~json
{
  "expression": "T(java.lang.Runtime).getRuntime()...",
  "targetBeanName": "anySpringBean",
  "method": "invokeArbitraryOperation"
}
~~~

Đoạn thứ hai chỉ là **ví dụ hình dạng request phải bị từ chối**, không phải cú pháp để thực thi. Một API thay đổi route nên nhận **mã định danh policy, revision mong đợi, tập key/value có cấu trúc, lý do và command ID**. Không cho client tải lên SpEL tùy ý, tên bean tự do, mã Java hoặc câu lệnh Control Bus.

Ngay cả khi operator được phép sửa cấu hình, **tập destination** có thể vẫn bị giới hạn vào `DOMESTIC`, `EXPORT`, `REVIEW`. Việc thêm route đến endpoint mới yêu cầu một quy trình riêng đã kiểm thử handler, quyền và hợp đồng dữ liệu.

## 7. Allowlists và bất biến nghiệp vụ

Một chính sách tốt kiểm tra **cả cú pháp lẫn ngữ nghĩa**. Ví dụ:

- Key thị trường phải được chuẩn hóa (uppercase), có độ dài tối đa và không trống.
- Route key chỉ thuộc tập được công bố: `DOMESTIC`, `EXPORT`, `REVIEW`.
- Không cho phép trỏ sang channel tùy ý bằng chuỗi từ request.
- Không cho xóa mọi destination hoặc vô hiệu hóa nhánh an toàn cuối cùng.
- Những event nhạy cảm phải qua kiểm tra bắt buộc **ngoài vùng có thể cấu hình tùy ý**.
- Bản cấu hình phải có consumer đích, metric và error handling đã sẵn sàng.

Ví dụ validator thuần Java:

~~~java
public final class RouteRuleValidator {

    private static final Set<String> ALLOWED_ROUTES =
        Set.of("DOMESTIC", "EXPORT", "REVIEW");

    public void validate(Map<String, String> proposed) {
        if (proposed == null || proposed.isEmpty()
                || proposed.size() > 32) {
            throw new IllegalArgumentException("Invalid policy size");
        }
        for (var entry : proposed.entrySet()) {
            String market = entry.getKey();
            String route = entry.getValue();
            if (market == null
                    || !market.matches("[A-Z]{2}")
                    || !ALLOWED_ROUTES.contains(route)) {
                throw new IllegalArgumentException(
                    "Invalid market or route key");
            }
        }
    }
}
~~~

**Validate không thay authorization.** Một rule `SG → REVIEW` có thể hợp lệ về schema nhưng operator hiện tại không có quyền sửa thị trường SG. Ngược lại, một Route Administrator có toàn quyền vẫn không được đưa tên channel bất kỳ vào rule nếu điều đó vi phạm bất biến kỹ thuật.

**Bảo vệ đường xử lý rủi ro:** nếu mọi đơn giá trị lớn bắt buộc qua Manual Review, hãy đặt Filter/Router kiểm tra rủi ro hoặc một policy bắt buộc **trước** khu vực operator có thể sửa mapping. Không nên cho phép một thay đổi thị trường bỏ qua kiểm tra này.

## 8. Mô hình phiên bản bất biến cho runtime policy

Một lựa chọn đơn giản trong **một JVM** là giữ snapshot bất biến và thay thế bằng một thao tác nguyên tử. Đây là một dạng dynamic routing **thay đổi dữ liệu policy**, không cần tạo/xóa bean Spring khi đang chạy.

~~~java
public record RouteSnapshot(
    long version,
    Map<String, String> marketToRoute
) {
    public RouteSnapshot {
        marketToRoute = Map.copyOf(marketToRoute);
    }
}

public record OrderCreated(
    String eventId,
    String market,
    long amount
) {}

public final class VersionedRoutePolicy {
    private final AtomicReference<RouteSnapshot> active =
        new AtomicReference<>(new RouteSnapshot(
            1L, Map.of(
                "VN", "DOMESTIC",
                "US", "EXPORT"
            )));

    public RouteSnapshot snapshot() {
        return active.get();
    }

    public String resolve(OrderCreated event) {
        if (event.market() == null || event.market().isBlank()) {
            return "INVALID";
        }
        String market =
            event.market().trim().toUpperCase(Locale.ROOT);
        RouteSnapshot snapshot = active.get();
        return snapshot.marketToRoute()
            .getOrDefault(market, "UNSUPPORTED");
    }

    // Chỉ gọi sau khi đã xác thực, phân quyền, validate,
    // phê duyệt và phối hợp với nơi lưu cấu hình bền vững.
    public boolean replaceExpectedVersion(
            long expectedVersion,
            Map<String, String> newRules) {
        RouteSnapshot old = active.get();
        if (old.version() != expectedVersion) {
            return false;
        }
        RouteSnapshot updated =
            new RouteSnapshot(old.version() + 1, newRules);
        return active.compareAndSet(old, updated);
    }
}
~~~

**Các thuộc tính quan trọng:**

1. `Map.copyOf` ngăn người gọi chỉnh lại map đã dùng làm snapshot (nhưng không tự kiểm tra quyền hoặc tính hợp lệ của key).
2. `AtomicReference` giúp một lần resolve nhìn thấy một phiên bản nhất quán trong cùng tiến trình.
3. `compareAndSet` ngăn hai cập nhật đồng thời cùng ghi đè âm thầm trên **cùng instance**; caller phải xử lý kết quả false như một conflict.
4. `resolve()` chỉ đọc; không tạo side effect và không gọi mạng.
5. `replaceExpectedVersion()` là thao tác **nội bộ**, không phải API được mở trực tiếp cho người dùng.

Đây là **mô hình minh họa in-memory**, không phải hệ quản trị policy hoàn chỉnh. Nó **không** cung cấp persistence, authorization, audit log, phê duyệt, transaction với database hay đồng bộ giữa các instance. Trong production, cần một control plane đảm nhận các bước ấy.

## 9. Dùng policy động bên trong Spring Integration Java DSL

Giữ channel mapping **cố định** trong ứng dụng, còn hàm tính key có thể đọc phiên bản policy đang chạy:

~~~java
@Configuration
@EnableIntegration
class DynamicOrderRoutingFlow {

    @Bean
    VersionedRoutePolicy versionedRoutePolicy() {
        return new VersionedRoutePolicy();
    }

    @Bean
    IntegrationFlow routeOrders(VersionedRoutePolicy policy) {
        return IntegrationFlow.from("orders.in")
            .filter(OrderCreated.class,
                event -> event.eventId() != null
                    && !event.eventId().isBlank(),
                f -> f.discardChannel("orders.invalid"))
            .route(OrderCreated.class, policy::resolve,
                r -> r.channelMapping("DOMESTIC", "orders.domestic")
                      .channelMapping("EXPORT", "orders.export")
                      .channelMapping("REVIEW", "orders.review")
                      .channelMapping("INVALID", "orders.invalid")
                      .channelMapping("UNSUPPORTED", "orders.unmapped")
                      .defaultOutputChannel("orders.unclassified"))
            .get();
    }
}
~~~

Ví dụ dùng Java 17+ và Java DSL; các import được lược bỏ. Cần có handler/consumer thật cho từng channel đích. **Một lần cập nhật `marketToRoute` có thể thay đổi nhánh của message kế tiếp**, nhưng chỉ trong số các key mà Java DSL đã map. Nếu policy trả key không có mapping, message đi default theo cấu hình phù hợp; phải kiểm thử hành vi fallback trên phiên bản Spring Integration sử dụng.

Đây là lựa chọn thực tế khi yêu cầu là “đổi quy tắc chọn nhánh” chứ không phải “nạp bean mới qua runtime”. Với cùng event nhưng các lần xử lý ở hai thời điểm khác nhau, route có thể khác do phiên bản policy đã thay đổi; cần quyết định liệu replay dùng **revision lịch sử** hay policy hiện tại.

## 10. Quy trình thay đổi: từ đề xuất tới kích hoạt

Một API có role kiểm tra ở đầu vào vẫn chưa đủ. Quy trình thay đổi nên được mô hình hóa:

~~~mermaid
flowchart TD
    REQ["Đề xuất route change"] --> ID["Xác thực actor + phạm vi tenant"]
    ID -->|"Không có quyền"| NO["Reject + audit denied"]
    ID -->|"Được phép"| VA["Validate schema + allowlist + invariant"]
    VA -->|"Sai"| ERR["Reject + reason code"]
    VA -->|"Đúng"| PRE["Preview / impact analysis"]
    PRE --> APPROVE{"Có cần phê duyệt?"}
    APPROVE -->|"Có"| PENDING["Chờ người duyệt độc lập"]
    PENDING --> ACT["Activate approved revision"]
    APPROVE -->|"Không"| ACT
    ACT --> CAS{"expectedVersion còn đúng?"}
    CAS -->|"Không"| CONFLICT["409 conflict, đọc lại revision"]
    CAS -->|"Có"| SAVE["Persist revision + immutable audit"]
    SAVE --> DEPLOY["Distribute approved snapshot"]
    DEPLOY --> OBS["Canary + metrics + rollback trigger"]
~~~

Trong production, **thứ tự persist/activate và tính nguyên tử** phải được xác định rõ. Nếu DB đã commit nhưng node chưa cập nhật cache, hoặc cache đã thay đổi nhưng audit chưa ghi, các bản sao có thể lệch nhau. Có thể dùng database transaction cho trạng thái nguồn, event/outbox để phát revision, và cơ chế reconcile nhằm đạt đồng bộ từng bước. Một thao tác `AtomicReference.compareAndSet` **không giải quyết** các vấn đề phân tán ấy.

Mỗi request cần:

- `policyId` và phạm vi nguồn lực cụ thể.
- `expectedVersion` để từ chối cập nhật dựa trên trạng thái đã cũ.
- `changeId` để chống xử lý cùng lệnh nhiều lần.
- Actor identity do hệ thống xác thực; không tin `updatedBy` do client tự khai.
- Reason, ticket/approval và các thay đổi trước/sau.
- Tùy yêu cầu: thời điểm kích hoạt, rollout percentage và TTL của route tạm.

Việc đưa policy vào trạng thái **PENDING/APPROVED/ACTIVE/REVERTED** nên nằm ở control plane, không biến thành header có thể chỉnh bởi message thường.

## 11. Spring Security: role là điều kiện cần, không phải đủ

Ứng dụng Spring Boot có thể kiểm soát hành động đổi route bằng bảo vệ endpoint và **method security**. Ví dụ minh họa:

~~~java
@Configuration
@EnableMethodSecurity
class RouteMethodSecurityConfiguration {
}

@Service
class RouteAdminService {
    private final RouteAuthorization authorization;
    private final RoutePolicyRepository repository;

    RouteAdminService(RouteAuthorization authorization,
                      RoutePolicyRepository repository) {
        this.authorization = authorization;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('ROUTE_POLICY_WRITE')")
    public void propose(RouteChangeRequest change,
                        Authentication actor) {
        if (!authorization.canEdit(
                actor, change.policyId(), change.tenantId())) {
            throw new AccessDeniedException(
                "No permission for requested policy scope");
        }
        // Validator và approval workflow chạy trước activation.
        repository.saveProposal(change, actor.getName());
    }
}
~~~

Các interface `RouteAuthorization`, `RoutePolicyRepository` và record `RouteChangeRequest` ở ví dụ là **abstractions do ứng dụng định nghĩa**, không phải API có sẵn của Spring Integration. Khi hiện thực, cần validate đầy đủ trước khi lưu proposal và bảo đảm thông tin actor đến từ **security context đã xác thực**. Không cho client truyền đối tượng `Authentication` tùy ý vào API từ xa.

**Đặc biệt chú ý Spring proxy:** `@PreAuthorize` chỉ có hiệu lực khi method security đã bật và lời gọi đi qua proxy được Spring quản lý; gọi nội bộ `this.propose(...)` có thể bỏ qua interception. Vì thế không dựa duy nhất vào annotation cho invariant quan trọng: authorization theo resource và validation phải được kiểm soát tại **đúng boundary** của lệnh quản trị.

Nếu có HTTP admin API, bảo vệ bằng cơ chế xác thực mạnh và giới hạn mạng; dùng CSRF protection khi áp dụng cookie/session, TLS, giới hạn tốc độ, log audit, kiểm soát idempotency và không cho request body chứa các chỉ thị thực thi tùy ý.

## 12. Control Bus rất mạnh: không biến thành cổng sửa route công khai

Spring Integration có **Control Bus** để gửi lệnh điều khiển tới các thành phần tích hợp, thường dựa trên expression/message. Đây là công cụ vận hành có quyền rộng vì có thể thao tác endpoint/bean nếu được cho phép bởi cấu hình.

**Không nối Control Bus trực tiếp với HTTP/Kafka input của người dùng** và không coi một header `role=admin` là authorization. Nếu client có thể gửi expression tới Control Bus, một lỗi phân quyền có thể mở đường thao tác nhiều thành phần khác ngoài Router.

Nếu cần chức năng quản trị runtime:

1. Dùng **Admin API chuyên biệt** với command schema cố định, không chấp nhận SpEL tự do.
2. Dùng backend service đã xác thực để quyết định những thay đổi được cho phép.
3. Hạn chế mutator và bean được tiếp cận; ưu tiên policy data thay vì thao tác Spring context tùy ý.
4. Tách đường quản trị khỏi đường xử lý sự kiện; có mạng/identity riêng khi cần.
5. Audit mọi thay đổi, kể cả bị từ chối; giám sát thay đổi bất thường.

Quyền **điều khiển một endpoint** không đồng nghĩa với quyền **chỉ sửa một rule nghiệp vụ**. Cấp quyền cho Control Bus cần thận trọng hơn cấp quyền cập nhật bảng market-to-route trong ví dụ.

## 13. Đừng cho message nghiệp vụ mang quyền cập nhật policy

Ví dụ một producer gửi:

~~~text
payload: OrderCreated(eventId="E-10", market="VN", amount=100)
headers:
  tenantId: tenant-B
  routeKey: orders.privileged
  changePolicy: true
  routeVersion: 9999
~~~

Các header ấy **không chứng minh** producer có quyền quản trị, được chọn đích, được thay đổi tenant scope hay được cập nhật revision. Data plane cần xem chúng như input không tin cậy, trừ những metadata đã được xác minh tại adapter hoặc suy ra từ identity đáng tin.

Để bảo vệ:

- Hạn chế inbound header mapper chỉ mang metadata cần thiết.
- Không cho producer ghi đè các header điều khiển quan trọng hoặc tên channel nội bộ.
- Định nghĩa `tenantId` từ claim đã được xác minh hay mối liên kết xác thực với message, không từ header trần.
- Router chỉ dùng `RouteSnapshot` đã được control plane phê duyệt.
- Nếu cần dynamic routing theo tenant, ánh xạ theo tổ hợp `tenant + policyId` đã được kiểm tra quyền và tách dữ liệu.

**Một route key hợp lệ vẫn có thể là route không được phép đối với tenant cụ thể.** Whitelist destination ngăn route injection, nhưng không thay thế authorization theo nguồn lực.

## 14. Multi-tenant: thay đổi route phải gắn với phạm vi

Giả sử tenant A muốn cho traffic VN đi nhánh REVIEW trong một giờ. Một bản policy toàn cục `Map<market, route>` sẽ ảnh hưởng tất cả tenant, kể cả B. Nếu sản phẩm yêu cầu cô lập tenant, phải dùng khóa policy **có phạm vi**, ví dụ:

~~~text
policyKey = tenantId + ":" + policyId

tenant-A:order-market-routing → revision 24
tenant-B:order-market-routing → revision 9
~~~

Thêm các kiểm soát:

| Ranh giới | Quy định |
|---|---|
| Định danh tenant | Lấy từ nguồn xác thực hoặc dữ liệu đã xác minh |
| Quyền sửa | Actor phải quản trị đúng tenant và policy |
| Quyền xem | History và preview cũng cần kiểm soát dữ liệu nhạy cảm |
| Cấu hình mặc định | Xác định rõ global fallback có được áp dụng không |
| Phạm vi activation | Chỉ tác động đúng tenant; có thể canary theo tập nhỏ |
| Audit | Ghi tenant, policy ID, revision trước/sau, principal và lý do |

Đừng lấy `tenantId` trong URL/body làm bằng chứng rằng actor được phép sửa tenant đó. Phải so nó với quyền được máy chủ xác minh. Trong sơ đồ nhiều cluster, revision cũng phải gắn scope để tránh “tenant A version 24” bị hiểu thành revision của B.

## 15. Tranh chấp cập nhật và nhất quán khi chạy nhiều node

Giả sử hai operator đọc policy version 12:

~~~text
Operator A: thêm SG → EXPORT, expectedVersion=12
Operator B: đổi US → REVIEW, expectedVersion=12

A ghi thành version 13: thành công
B ghi với expectedVersion=12: phải nhận CONFLICT
~~~

Nếu cả hai lệnh cùng được chấp nhận mà không so version, bản ghi sau có thể làm mất thay đổi của bản trước (**lost update**). Optimistic concurrency buộc B đọc lại version 13, xem diff rồi đề xuất version 14.

Đối với nhiều instance:

~~~mermaid
flowchart LR
    STORE["Policy store v13"] --> EVT["Revision event"]
    EVT --> A["Instance A active v13"]
    EVT --> B["Instance B active v12"]
    EVT --> C["Instance C active v13"]
    B --> RECON["Reconcile / catch up"]
    RECON --> B2["Instance B active v13"]
~~~

**AtomicReference chỉ bảo đảm thao tác trong một JVM**. Nó không làm tất cả instance chuyển version đồng thời. Cần quy tắc nhất quán phù hợp: lưu canonical revision ở DB, phát update có số phiên bản, bỏ qua event cũ, lấy lại full snapshot khi bị mất event, và giám sát instance còn dùng version trước.

Có hai mô hình thường gặp:

1. **Snapshot cache từng instance:** hiệu năng cao; chấp nhận một khoảng chuyển tiếp nhiều version và phải đo được độ lệch.
2. **Routing decision tập trung:** các node gọi một decision service/policy store chung để đọc revision; nhất quán dễ quản lý hơn nhưng thêm latency và phụ thuộc availability.

Không tuyên bố “route đổi ngay trên mọi node” nếu cơ chế cập nhật thực tế là bất đồng bộ. Khi có yêu cầu cutover chính xác, cần thiết kế barrier, draining hoặc version pinning cho các message được phát trong cửa sổ chuyển đổi.

## 16. Message đang xử lý dở phải theo version nào?

Một order có thể đã qua **Filter → Transformer → Router**, nhưng còn các bước **Splitter → Aggregator → Gateway reply**. Nếu revision đổi trong lúc message đang đi:

- **Route at decision time:** mỗi lần đi qua Router đọc snapshot hiện tại; retry của cùng event có thể chọn nhánh khác.
- **Pinned policy version:** ghi revision vào context đáng tin hoặc lưu ở process state; retry/replay dùng đúng quy tắc lịch sử.
- **Migration policy:** những message còn dở được chuyển theo quy tắc migrate có kiểm soát, thay vì âm thầm áp dụng policy mới.

Ví dụ một hóa đơn đã bắt đầu kiểm tra ở revision 12, sau đó revision 13 đổi nhánh. Nếu retry từ đầu làm nó đi một nhánh khác, có thể tạo side effect không nhất quán. Cần xác định **semantics của replay/retry** và giữ event ID/correlation theo hợp đồng.

**Cẩn thận với header phiên bản:** producer có thể giả mạo `policyVersion`. Nếu cần pin, giá trị phải do hệ thống điều phối đặt hoặc xác thực tại ingress; nơi áp dụng route phải xác minh version có còn hợp lệ và có quyền truy cập trong phạm vi tenant.

## 17. Audit, approval và rollback

Một lịch sử thay đổi có thể cần các trường:

~~~json
{
  "changeId": "CHG-2026-0102",
  "policyId": "order-market-routing",
  "tenantId": "tenant-A",
  "oldVersion": 12,
  "newVersion": 13,
  "actorId": "authenticated-principal",
  "approvalId": "APR-204",
  "reason": "Maintenance window",
  "before": {"SG": "UNSUPPORTED"},
  "after": {"SG": "REVIEW"},
  "outcome": "ACTIVATED"
}
~~~

Trong production, `actorId` phải lấy từ phiên đăng nhập/token đã xác minh, còn `approvalId` phải trỏ tới quyết định duyệt thật. Tránh log payload chứa thông tin khách hàng hoặc token. Audit cần chống sửa trái phép, có retention và khả năng tra cứu theo policy/revision/time window.

**Rollback là một thay đổi mới được ghi nhận**, không nên âm thầm xóa lịch sử. Ví dụ:

~~~text
version 12: SG → UNSUPPORTED
version 13: SG → REVIEW        (thay đổi tạm)
version 14: SG → UNSUPPORTED  (rollback có lý do + audit)
~~~

Rollback không thể “đưa về trạng thái cũ” cho những message đã xử lý hoặc tác dụng phụ đã commit dưới revision 13. Nếu route sai gây thay đổi dữ liệu, cần quy trình khắc phục/compensation riêng.

Với rule tác động lớn, có thể áp dụng **two-person approval, canary rollout, TTL tự hết hạn và điều kiện rollback tự động** dựa trên lỗi hoặc tỷ lệ routing bất thường.

## 18. Khi thay đổi route gây lỗi: fail-safe và recovery

Một cập nhật có thể vượt qua schema validation nhưng vẫn gây lỗi tại runtime: channel đích không có consumer, handler quá tải, dependency mất kết nối hoặc phiên bản rule không tương thích payload mới.

| Loại lỗi | Điều cần làm |
|---|---|
| Actor không có quyền | Từ chối 403; audit denied; không thay active revision |
| Request schema/rule sai | Trả lỗi validation; giữ revision cũ |
| Expected version cũ | Trả conflict; không tự ghi đè |
| Channel đích chưa sẵn sàng | Không activate hoặc rollback sau canary |
| Consumer chậm/quá tải | Backpressure, queue/circuit breaker phù hợp |
| Router runtime exception | Error channel/exception path phù hợp từng kiểu channel |
| Cập nhật đa node một phần | Reconcile; theo dõi version skew |
| Revision gây lệch nghiệp vụ | Rollback có audit và xem lại side effect đã phát sinh |

**Default output channel** có thể giúp xử lý routing key không có mapping, nhưng **không phải cơ chế phân quyền và không tự bắt mọi exception**. Một rule không hợp lệ phải bị từ chối **trước activation**, thay vì cho phép rồi tin rằng default sẽ xử lý an toàn.

Lỗi cấu hình thường không nên được retry vô hạn trên mọi event. Nếu một số message đã đi nhầm route, cần giữ thông tin `eventId`, `policyVersion` và quyết định thực tế để có thể đối chiếu, phát lại có chủ đích hoặc thực hiện bù trừ.

## 19. Kiểm thử quyền, concurrency và routing

Nên kiểm thử theo ba lớp, không chỉ gửi một message rồi kiểm tra handler cuối:

### Unit test cho validator và snapshot

~~~java
@Test
void disallowsUnknownChannelKeys() {
    RouteRuleValidator validator = new RouteRuleValidator();

    assertThrows(IllegalArgumentException.class,
        () -> validator.validate(Map.of(
            "VN", "orders.privileged")));
}

@Test
void preventsStaleVersionOverwrite() {
    VersionedRoutePolicy policy = new VersionedRoutePolicy();

    assertTrue(policy.replaceExpectedVersion(
        1L, Map.of("VN", "REVIEW", "US", "EXPORT")));
    assertFalse(policy.replaceExpectedVersion(
        1L, Map.of("VN", "DOMESTIC", "US", "REVIEW")));
    assertEquals(2L, policy.snapshot().version());
}
~~~

Test thứ hai chỉ xác minh hành vi CAS tại một instance; để thử concurrency thực sự, khởi động hai tác vụ cập nhật đồng thời với cùng expectedVersion và xác minh **chỉ một cập nhật thành công**, không có snapshot bị chỉnh một phần. Đừng dùng `Thread.sleep` để giả định các task sẽ đụng nhau; dùng latch/barrier trong test.

### Security test cho control plane

| Trường hợp | Kỳ vọng |
|---|---|
| Không đăng nhập gọi admin API | Bị từ chối; không thay đổi revision |
| Role đọc thử sửa route | 403 hoặc access denied tương ứng |
| Operator tenant A sửa policy tenant B | Bị từ chối ở resource scope |
| Client gửi tên bean/channel tùy ý | Validation reject |
| Client tự khai `isAdmin=true` trong header | Không ảnh hưởng authorization |
| Caller gửi SpEL/Control Bus command | Không có endpoint cho phép thực thi tùy ý |
| Người đề xuất tự duyệt khi yêu cầu tách nhiệm vụ | Bị từ chối |
| Gửi lại cùng `changeId` | Không kích hoạt trùng; trả kết quả idempotent |
| Dùng `expectedVersion` cũ | Conflict, không lost update |
| Rollback không có quyền | Bị từ chối và có audit |

Để chứng minh `@PreAuthorize` hoạt động, test phải gọi service **qua Spring proxy** trong test context đã bật method security. Unit test trực tiếp `new RouteAdminService(...)` không kiểm chứng interception của annotation.

### Integration test cho route sau khi activation

Trong Spring Integration test, thay các consumer production ở `orders.domestic`, `orders.export`, `orders.review` bằng `QueueChannel` tương ứng. Gửi message vào `orders.in` và xác nhận channel được chọn:

| Input | Revision | Kết quả mong đợi |
|---|---|---|
| Market VN | v1 | `orders.domestic` |
| Market SG | v1 | `orders.unmapped` |
| Market SG | v2: SG → EXPORT | `orders.export` |
| Market VN | v3: VN → REVIEW | `orders.review` |
| Market rỗng | Bất kỳ | `orders.invalid` |
| Event ID thiếu | Bất kỳ | Filter loại, không route nghiệp vụ |
| Hai request song song | Cùng expectedVersion | Một activation thành công, một conflict |
| Message đang xử lý khi đổi revision | Trước/sau activation | Kết quả đúng theo semantics đã công bố |
| Một node chưa cập nhật revision | vN/vN+1 | Có metric version skew và cơ chế reconcile |

Khi nhánh có retry, thêm test dùng cùng `eventId` nhiều lần để bảo đảm handler không tạo side effect trùng. Khi có Splitter/Aggregator, kiểm tra `correlationId` và version policy được bảo toàn đúng theo hợp đồng; đừng dùng retry để che lỗi cấu hình route.

## 20. Observability và phát hiện thay đổi bất thường

Một thay đổi route nên tạo được chuỗi truy vết:

~~~text
Admin principal → changeId → approvalId → newVersion
     → instance activation → routing decision → handler outcome
~~~

Nên theo dõi:

| Metric / log | Ý nghĩa |
|---|---|
| Số change requests theo outcome | Có nhiều thay đổi bị từ chối hoặc lỗi validation không? |
| Active revision trên từng instance | Các node đã hội tụ về cùng version chưa? |
| Route key và destination được chọn | Traffic có dịch chuyển như dự kiến không? |
| Tỷ lệ `UNSUPPORTED` và default route | Có input chưa được policy hỗ trợ không? |
| Lỗi và latency theo destination | Revision mới có gây quá tải hay thất bại không? |
| Số lần rollback / canary abort | Policy thay đổi có thường xuyên gây sự cố không? |
| Retry, error channel, DLQ | Có message bị xử lý lại hay bị giữ trong failure queue không? |
| Correlation/event ID trong trace | Có thể nối quyết định route với kết quả nghiệp vụ không? |

Không dùng `eventId`, `tenantId` động hoặc nguyên raw channel name làm metric tag không giới hạn vì gây **high cardinality** và có thể lộ thông tin. Dùng nhãn hữu hạn; chi tiết theo thực thể nên để trong trace/log có kiểm soát quyền truy cập.

Khi điều tra sự cố, hãy lấy **revision đã được áp dụng cho từng message**, không chỉ revision đang hoạt động ở thời điểm kiểm tra. Một message có thể đã đi qua Router trước khi bản rollback được kích hoạt.

## 21. Bài thực hành: thay đổi route có kiểm soát

Xây dựng một **DynamicOrderRouter** với Spring Integration:

1. **Data plane:** `OrderCreated → Filter → Dynamic Router → Domestic/Export/Review/Unmapped`.
2. **Policy:** `VersionedRoutePolicy` với snapshot bất biến, `expectedVersion` và allowlist key.
3. **Control plane:** Admin API chỉ nhận policy ID, scope, revision, map key→route, lý do và change ID; không nhận tên bean hay SpEL.
4. **Security:** reader không được sửa, operator chỉ được đề xuất, approver phê duyệt; tenant A không sửa được tenant B.
5. **Preview:** mô phỏng ít nhất 10 sự kiện mẫu trước/sau revision; xác nhận không bỏ qua kiểm tra bắt buộc.
6. **Activation:** cập nhật version theo CAS/optimistic concurrency; lưu audit và hỗ trợ rollback thành revision mới.
7. **Capacity:** đưa phần trăm traffic sang REVIEW, đo queue/latency và thử tự rollback khi error rate vượt ngưỡng đã định.
8. **Multi-instance:** mô phỏng một node nhận update chậm; kiểm tra version skew, reconcile và semantics cho message giữa hai revision.
9. **Test:** unit test validator/CAS, security test, integration test routing, retry/idempotency và correlation với Gateway/Splitter/Aggregator khi cần.

**Tiêu chí hoàn thành:** một operator trái quyền không thể thay active policy; chỉ route keys được phép mới có thể xuất hiện; hai cập nhật đồng thời không ghi đè âm thầm; mọi revision có audit trail; cùng message được giải thích bằng policy version phù hợp; rollout và rollback có số liệu quan sát được.

## 22. Những sai lầm thường gặp

**“Có role ADMIN là đủ.”** Không. Cần quyền theo resource/tenant, tách nhiệm vụ, validate rule và theo dõi phiên bản.

**“Header của producer chứa `changePolicy=true` nên cho phép cập nhật.”** Sai. Header nghiệp vụ không thay identity hoặc quyền ở control plane.

**“Dynamic Router phải nhận tên channel tùy ý mới linh hoạt.”** Không. Thay đổi bảng key→route có giới hạn thường đáp ứng yêu cầu với rủi ro thấp hơn.

**“Map bất biến đồng nghĩa cấu hình đã bền vững.”** Sai. `Map.copyOf` và `AtomicReference` không lưu database, không audit và không đồng bộ đa node.

**“Một lần cập nhật thành công nghĩa là mọi node dùng ngay revision mới.”** Sai khi phân phối bất đồng bộ. Cần observability cho version skew và cơ chế hội tụ.

**“Rollback đưa mọi message trở về trạng thái cũ.”** Sai. Các message đã đi qua route mới và side effect đã commit cần phục hồi nghiệp vụ riêng.

**“Default channel có thể thay authorization.”** Sai. Fallback chỉ giúp xử lý key không có route phù hợp; một rule sai quyền phải bị từ chối trước khi activation.

**“Chỉ test happy path là đủ.”** Sai. Các kiểm thử quan trọng nhất nằm ở thay đổi trái quyền, tenant isolation, race condition, replay, stale revision và tác động đến consumer.

## 23. Ghi nhớ

**Kiểm soát quyền thay đổi route** là kiểm soát **control plane** của Dynamic Router. Một thiết kế an toàn cần *authentication, authorization theo scope, allowlist destination, validation bất biến, phê duyệt khi cần, version/CAS, audit, rollback và giám sát phân phối revision*. Message nghiệp vụ chỉ được **đọc** một policy đã được kích hoạt hợp lệ; producer không được biến header thành lệnh quản trị.

Trong Spring Integration, có thể giữ Router và các channel cố định, rồi thay đổi **snapshot routing policy** thông qua dịch vụ quản trị có kiểm soát. Khi kết hợp với **Filter, Transformer, Gateway, Splitter, Aggregator, retry, error channel và correlation**, cách làm này giúp thay đổi flow linh hoạt mà không đánh đổi khả năng bảo mật, tính nhất quán và kiểm thử trong hệ thống tích hợp phân tán.
