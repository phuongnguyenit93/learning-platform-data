# Kiểm thử snapshot cấu hình route

## 1. Vấn đề: route thay đổi trong lúc hệ thống đang xử lý

Trong **Dynamic Router**, quyết định đưa message tới channel nào có thể thay đổi khi ứng dụng đang chạy. Chẳng hạn, đơn hàng nội địa ban đầu đi vào `orders.vn.primary`, sau đó đội vận hành chuyển sang `orders.vn.canary` để thử một cách xử lý mới mà không phải sửa producer. Khả năng đổi route này hữu ích, nhưng cũng làm phát sinh câu hỏi:

- Một message đang được xử lý ở thời điểm cấu hình đổi thì dùng **phiên bản rule cũ hay mới**?
- Một lần cập nhật nhiều mapping có thể khiến người đọc thấy **nửa cấu hình cũ, nửa cấu hình mới** hay không?
- Làm sao chứng minh mọi key đang hỗ trợ vẫn có channel hợp lệ sau khi cập nhật?
- Khi rollback, xử lý các message đã đi theo phiên bản mới thế nào?
- Có cách nào kiểm thử cấu hình mới **trước khi cho traffic thực chạy qua**?

**Snapshot cấu hình route** là một ảnh chụp *logic* của toàn bộ tập quy tắc cần dùng ở một thời điểm: gồm **version**, các **routing key → destination key/channel**, điều kiện và metadata cần thiết. Snapshot lý tưởng là **bất biến**; khi thay đổi chính sách, ứng dụng chuẩn bị snapshot mới, kiểm tra hợp lệ rồi **publish cả bản mới như một đơn vị**. Một quyết định định tuyến nên tham chiếu **một snapshot nhất quán**, không ghép nhiều bản đọc cấu hình rời rạc.

~~~mermaid
flowchart LR
    A[Producer OrderCreated] --> R{Dynamic Router}
    V1["RouteSnapshot v1: VN → primary"] -. hiện hành .-> R
    V2["RouteSnapshot v2: VN → canary"] --> P[Validate & publish atomically]
    P -. thay snapshot hiện hành .-> R
    R -->|v1| C1[(orders.vn.primary)]
    R -->|v2| C2[(orders.vn.canary)]
    C1 --> H1[Primary Handler]
    C2 --> H2[Canary Handler]
~~~

Sơ đồ minh họa một thay đổi **theo thời điểm quyết định**. Nó không bảo đảm mọi message đang chạy sẽ lập tức chuyển sang v2: message đã được dispatch sang primary vẫn có thể tiếp tục xử lý ở đó. Đây thường là hành vi mong muốn để tránh thay đổi lộ trình giữa chừng.

Bài thuộc chương **Dynamic router** của module `SPRING_INTEGRATION_PATTERN`. Module tập trung triển khai các Enterprise Integration Patterns bằng Spring Integration, xây dựng luồng ít phụ thuộc và dễ mở rộng, phối hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử/quan sát từng nhánh.

**Mục tiêu:** hiểu snapshot cấu hình route là gì; phân biệt snapshot immutable với cấu hình sống có thể chỉnh từng phần; thiết kế route validation và atomic swap; viết unit/integration tests về version, rollback, concurrent updates và đường đi message; xây dựng bằng chứng vận hành khi route thay đổi.

## 2. “Snapshot” ở đây có nghĩa gì?

### 2.1. Không phải ảnh chụp giao diện

Trong bài này, **snapshot cấu hình** là một **giá trị dữ liệu bất biến đại diện cho toàn bộ cấu hình routing tại một phiên bản**. Nó không phải screenshot và cũng không chỉ là một file “golden snapshot” của test framework.

Ví dụ snapshot ở thời điểm T1:

~~~yaml
version: route-policy-v1
routes:
  VN: vnPrimary
  INTL: international
~~~

Snapshot mới chuẩn bị tại T2:

~~~yaml
version: route-policy-v2
routes:
  VN: vnCanary
  INTL: international
~~~

Hai ví dụ YAML chỉ để trình bày **dữ liệu**, không phải file cấu hình được Spring Integration tự nhận vào `DynamicRouter`. Phần Java bên dưới mới thể hiện cách ứng dụng đọc và sử dụng snapshot.

### 2.2. Phân biệt ba khái niệm

| Khái niệm | Nội dung | Điều cần kiểm thử |
|---|---|---|
| **Route configuration snapshot** | Bảng quy tắc route bất biến tại version xác định. | Key, value, rule, version, validation và không bị mutation. |
| **Snapshot/golden test** | Một expected fixture được lưu hoặc viết trong test để phát hiện thay đổi ngoài ý muốn. | So sánh cấu hình thực tế với expected theo dạng ổn định và có chủ đích. |
| **Runtime routing decision** | Kết quả chọn đích cho **một** message theo **một** snapshot. | Message đúng đích; version và key được ghi nhận, không đọc xen lẫn hai phiên bản. |

Ví dụ test chỉ assert `VN → vnPrimary` nhưng không kiểm tra `INTL` thì **không chứng minh snapshot hợp lệ toàn diện**. Ngược lại, test so sánh mọi key trên một snapshot vẫn **không chứng minh channel tồn tại và có subscriber đang chạy**; cần integration test.

### 2.3. Những gì nên nằm trong snapshot

Một snapshot route có thể chứa:

| Trường | Ví dụ | Tác dụng |
|---|---|---|
| `version` | `route-policy-v2` | Gắn audit và so sánh/rollback. |
| `routes` | `VN → vnCanary` | Quy tắc mapping dùng để quyết định. |
| `effectiveFrom` (nếu cần) | Thời điểm được phép kích hoạt. | Rollout có lịch và phân biệt staging/active. |
| `policyHash` (nếu cần) | Digest của nội dung chuẩn hóa. | Phát hiện cấu hình lệch giữa các node. |
| `schemaVersion` (nếu cần) | `1` | Kiểm soát cách parse/validate khi schema đổi. |
| `owner/approval metadata` (nếu cần) | ID thay đổi được phê duyệt. | Truy nguyên ai kích hoạt rule và vì sao. |

Không phải cứ thêm mọi metadata là tốt. Trường nào dùng cho **quyết định** phải có semantics rõ; trường vận hành không nên bí mật làm thay đổi policy. Trong ví dụ, ta chỉ dùng `version` và `routes` để tập trung vào khả năng kiểm thử.

## 3. Khi không có snapshot, dễ xảy ra lỗi gì?

### 3.1. Cập nhật từng mapping để lộ trạng thái trung gian

Giả sử cấu hình đang chạy có hai key:

~~~text
Version v1
  VN   -> vnPrimary
  INTL -> international
~~~

Đội vận hành muốn đổi sang:

~~~text
Version v2
  VN   -> vnCanary
  INTL -> internationalV2
~~~

Nếu sửa hai entry của một `Map` dùng chung lần lượt, một request đến giữa hai thao tác có thể thấy:

~~~text
VN   -> vnCanary
INTL -> international   // entry chưa cập nhật
~~~

Đây là trạng thái **lai** chưa được phê duyệt hoặc kiểm thử. Tệ hơn, nếu thay đổi bằng cách `clear()` rồi `putAll()`, một reader có thể thấy map **rỗng** giữa chừng.

### 3.2. Thay Map không atomic với version

Một lỗi tinh vi:

~~~java
// Ví dụ không khuyến nghị: hai biến mutable độc lập.
currentVersion = "v2";
currentRoutes = newRoutes;
~~~

Trong khoảng giữa hai phép gán, một request có thể log `version=v2` nhưng route theo `v1`. Thêm `volatile` riêng cho hai biến không khiến **cặp giá trị** được cập nhật như một đơn vị. Snapshot phải đặt **version và mapping trong cùng một object bất biến**, rồi thay reference nguyên khối.

### 3.3. Snapshot test chỉ kiểm tra cấu hình, chưa kiểm tra delivery

Ngay cả khi snapshot hợp lệ:

~~~text
VN -> vnCanary
~~~

channel `orders.vn.canary` có thể không tồn tại, không có consumer, bị stop hoặc đang quá tải. Do đó:

1. **Unit test snapshot** chứng minh rule và cập nhật dữ liệu nhất quán.
2. **Integration test routing** chứng minh Spring Integration dispatch vào channel đúng.
3. **Operational validation** chứng minh nhánh nhận còn hoạt động, có đủ capacity và có đường xử lý lỗi.

Ba tầng kiểm tra này bổ sung nhau; không nên đánh đồng.

## 4. Kiến trúc snapshot bất biến và atomic swap

### 4.1. Đường đi của một thay đổi cấu hình

~~~mermaid
flowchart TD
    D[Draft RouteSnapshot v2] --> S[Validate schema / required keys]
    S --> W[Validate destination allowlist]
    W --> T[Unit / integration checks]
    T --> A[Approval / rollout gate]
    A --> CAS{Atomic compare-and-set}
    CAS -->|Thành công| ACTIVE[Active RouteSnapshot v2]
    CAS -->|Version conflict| REJECT[Reject / reload / reconcile]
    ACTIVE --> R[Decide mỗi message từ 1 snapshot]
    R --> OBS[Log version + route decision]
~~~

Trong ứng dụng đơn JVM, một cách thực hiện là `AtomicReference<RouteSnapshot>`. Mỗi request **đọc reference một lần**, giữ snapshot đó trong quá trình tính đích và sinh một kết quả gồm version + route key. Khi cập nhật, tạo object mới rồi `compareAndSet` theo version/identity của bản đang active.

### 4.2. Các bất biến cần giữ

| Bất biến | Vì sao quan trọng |
|---|---|
| Snapshot **không thể bị sửa nội dung** sau khi publish. | Request đã giữ snapshot v1 không bị đổi dưới chân. |
| `version` và `routes` nằm cùng một object. | Tránh log version mới nhưng dùng mapping cũ. |
| Mọi key bắt buộc luôn có mapping. | Không xuất hiện trạng thái route thiếu đích giữa rollout. |
| Mọi destination thuộc allowlist. | Không phân giải một tên channel tùy tiện do user cấu hình. |
| Mỗi quyết định chỉ đọc một snapshot. | Không dùng v1 để chọn key và v2 để chọn channel. |
| Update có kiểm soát xung đột. | Hai operator không được âm thầm ghi đè thay đổi của nhau. |
| Rollback là một lần publish snapshot được kiểm chứng. | Không chỉnh từng entry trở lại theo cách không atomic. |

**Quan trọng:** atomic swap này chỉ có hiệu lực trong **một process/JVM**. Nếu ứng dụng chạy nhiều replica, từng node có `AtomicReference` riêng. Không có bảo đảm tất cả node chuyển v2 cùng một nano-giây; cần cơ chế phân phối cấu hình, version, canary rollout và kiểm tra drift ở cấp cluster.

## 5. Java: định nghĩa snapshot và chính sách cập nhật

Ví dụ dưới đây hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x**. Mã Java thuần ở phần 5 **không phụ thuộc framework** để dễ unit test; phần 7 sẽ đưa kết quả policy vào Spring Integration Java DSL.

### 5.1. Snapshot, decision và route state

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

record RouteSnapshot(String version, Map<String, String> routes) {
    private static final Set<String> REQUIRED_MARKETS =
            Set.of("VN", "INTL");

    private static final Map<String, Set<String>> ALLOWED =
            Map.of(
                    "VN", Set.of("vnPrimary", "vnCanary"),
                    "INTL", Set.of("international"));

    RouteSnapshot {
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version is required");
        }
        Objects.requireNonNull(routes, "routes");

        // Copy trước khi publish: caller không sửa được snapshot.
        routes = Map.copyOf(routes);

        if (!routes.keySet().equals(REQUIRED_MARKETS)) {
            throw new IllegalArgumentException(
                    "Missing or unsupported market keys");
        }
        for (var entry : routes.entrySet()) {
            if (!ALLOWED.get(entry.getKey()).contains(entry.getValue())) {
                throw new IllegalArgumentException(
                        "Destination is not allowlisted: " + entry);
            }
        }
    }
}

record RouteDecision(
        String version,
        String market,
        String channelKey) {}

final class RouteState {
    private final AtomicReference<RouteSnapshot> active;

    RouteState(RouteSnapshot initial) {
        this.active = new AtomicReference<>(
                Objects.requireNonNull(initial, "initial"));
    }

    RouteSnapshot snapshot() {
        return active.get();
    }

    RouteDecision decide(String market) {
        // Điểm tuyến tính hóa: chỉ đọc đúng một snapshot.
        RouteSnapshot selected = active.get();
        String key = selected.routes().get(market);
        if (key == null) {
            throw new IllegalArgumentException(
                    "Unsupported market: " + market);
        }
        return new RouteDecision(selected.version(), market, key);
    }

    boolean swapIfVersion(
            String expectedVersion, RouteSnapshot next) {
        Objects.requireNonNull(expectedVersion, "expectedVersion");
        Objects.requireNonNull(next, "next");

        RouteSnapshot previous = active.get();
        if (!previous.version().equals(expectedVersion)
                || previous.version().equals(next.version())) {
            return false;
        }
        return active.compareAndSet(previous, next);
    }
}
~~~

### 5.2. Giải thích cách code bảo vệ snapshot

- `Map.copyOf` tạo bản đồ bất biến (với key/value ở ví dụ đều là `String` bất biến); sửa `Map` nguồn sau khi tạo `RouteSnapshot` không làm snapshot đổi.
- `REQUIRED_MARKETS` giữ đúng hai key `VN`, `INTL` trong **bài tập**. Production phải định nghĩa tập key theo hợp đồng của module, không sao chép bừa hai thị trường.
- `ALLOWED` chống việc route từ `VN` vào một nhánh quốc tế hoặc một bean lạ. Nếu thêm channel mới, phải thay policy/allowlist và kiểm tra nó đã được đăng ký.
- `decide()` giữ một local variable `selected` để version và channelKey đi cùng nhau.
- `swapIfVersion()` tạo **compare-and-set**: chỉ publish `next` nếu bản active vẫn là object đã đọc và version của nó khớp `expectedVersion`.
- Nếu một writer khác cập nhật giữa `active.get()` và `compareAndSet(...)`, CAS trả `false`; caller cần reload/reconcile, không tự gửi lại bản thay đổi cũ bằng lệnh ghi đè.

**Giới hạn cần biết:** `RouteState` chưa triển khai lưu cấu hình bền vững, phân quyền thay đổi, audit, phân phối giữa nhiều JVM, kiểm tra rollout toàn cluster hoặc tự động rollback. Những việc này phải bổ sung ở service vận hành, không suy từ `AtomicReference` rằng ứng dụng có một config store phân tán.

### 5.3. Một thay đổi có kiểm soát

~~~java
RouteSnapshot initial = new RouteSnapshot(
        "route-policy-v1",
        Map.of("VN", "vnPrimary", "INTL", "international"));

RouteState state = new RouteState(initial);
RouteDecision before = state.decide("VN");
// before.version() == "route-policy-v1"
// before.channelKey() == "vnPrimary"

RouteSnapshot candidate = new RouteSnapshot(
        "route-policy-v2",
        Map.of("VN", "vnCanary", "INTL", "international"));

boolean published =
        state.swapIfVersion("route-policy-v1", candidate);
// published == true

RouteDecision after = state.decide("VN");
// after.version() == "route-policy-v2"
// after.channelKey() == "vnCanary"
~~~

Nếu có message đã được định tuyến tới `orders.vn.primary` trước swap, nó vẫn có thể chạy tiếp tại đó. Snapshot giúp **quyết định đã đưa ra nhất quán**, không tự hủy side effect hoặc chuyển những message đã dispatch sang canary.

## 6. Unit test: snapshot bất biến, đầy đủ và có version

### 6.1. Kiểm tra snapshot đúng cấu hình

Mọi snapshot phải qua kiểm tra **hợp lệ về mặt dữ liệu** trước khi chạy test tích hợp. Với JUnit 5:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RouteSnapshotValidationTest {

    @Test
    void validSnapshotContainsEveryRequiredRoute() {
        RouteSnapshot snapshot = new RouteSnapshot(
                "v1",
                Map.of("VN", "vnPrimary",
                        "INTL", "international"));

        assertEquals("v1", snapshot.version());
        assertEquals(Map.of(
                "VN", "vnPrimary",
                "INTL", "international"), snapshot.routes());
    }

    @Test
    void missingRequiredMarketIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("bad",
                        Map.of("VN", "vnPrimary")));
    }

    @Test
    void unexpectedMarketIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("bad", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international",
                        "UNKNOWN", "vnPrimary")));
    }

    @Test
    void destinationNotOnAllowlistIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("bad", Map.of(
                        "VN", "international",
                        "INTL", "international")));
    }

    @Test
    void blankVersionIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("   ", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international")));
    }

    @Test
    void laterChangesToInputMapCannotChangeSnapshot() {
        Map<String, String> source = new HashMap<>();
        source.put("VN", "vnPrimary");
        source.put("INTL", "international");
        RouteSnapshot snapshot = new RouteSnapshot("v1", source);

        source.put("VN", "vnCanary");

        assertEquals("vnPrimary", snapshot.routes().get("VN"));
        assertThrows(UnsupportedOperationException.class, () ->
                snapshot.routes().put("VN", "vnCanary"));
    }
}
~~~

**Giới hạn:** test trên phát hiện mapping sai, key thiếu, destination ngoài allowlist và mutation ngoài ý muốn. Nó chưa biết các bean `orders.vn.primary`, `orders.vn.canary` có được tạo, có subscriber, hay có quyền truy cập downstream; chuyện đó thuộc integration test và runtime checks.

### 6.2. Test một quyết định dùng một version

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteStateVersionTest {

    private static RouteSnapshot v1() {
        return new RouteSnapshot("v1", Map.of(
                "VN", "vnPrimary",
                "INTL", "international"));
    }

    private static RouteSnapshot v2() {
        return new RouteSnapshot("v2", Map.of(
                "VN", "vnCanary",
                "INTL", "international"));
    }

    @Test
    void aPublishedUpdateChangesNewDecisionsNotOldOnes() {
        RouteState state = new RouteState(v1());
        RouteDecision oldDecision = state.decide("VN");

        assertTrue(state.swapIfVersion("v1", v2()));
        RouteDecision newDecision = state.decide("VN");

        assertEquals(new RouteDecision("v1", "VN", "vnPrimary"),
                oldDecision);
        assertEquals(new RouteDecision("v2", "VN", "vnCanary"),
                newDecision);
    }

    @Test
    void staleWriterCannotOverwritePublishedSnapshot() {
        RouteState state = new RouteState(v1());
        assertTrue(state.swapIfVersion("v1", v2()));

        RouteSnapshot staleChange = new RouteSnapshot(
                "v3-stale", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international"));

        assertFalse(state.swapIfVersion("v1", staleChange));
        assertEquals("v2", state.snapshot().version());
        assertEquals("vnCanary", state.decide("VN").channelKey());
    }

    @Test
    void aSecondPublishWithSameVersionIsRejected() {
        RouteState state = new RouteState(v1());

        assertFalse(state.swapIfVersion("v1", v1()));
        assertEquals("v1", state.snapshot().version());
    }
}
~~~

**Điểm cần nhớ:** sau khi `swapIfVersion` thành công, một request đã có `oldDecision` vẫn có quyết định của v1, còn request tiếp theo được phép dùng v2. Đó là mục tiêu của snapshot consistency.

Không nên suy từ test một JVM rằng **hai server** đang chạy v1/v2 cùng lúc sẽ tự đồng bộ. Multi-node cần cơ chế kiểm soát riêng.

### 6.3. “Golden snapshot test” phát hiện drift như thế nào?

Một snapshot test có thể so sánh một cấu hình được chuẩn hóa với **expected fixture** đã được review:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

final class SnapshotFormat {
    static String canonical(RouteSnapshot snapshot) {
        String lines = snapshot.routes().entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .map(e -> e.getKey() + "=" + e.getValue())
                .collect(Collectors.joining("\n"));

        return snapshot.version() + "\n" + lines;
    }
}
~~~

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RouteGoldenSnapshotTest {
    @Test
    void activePolicyMatchesReviewedSnapshot() {
        RouteSnapshot snapshot = new RouteSnapshot("v1", Map.of(
                "VN", "vnPrimary",
                "INTL", "international"));

        String expected = "v1\n"
                + "INTL=international\n"
                + "VN=vnPrimary";

        assertEquals(expected, SnapshotFormat.canonical(snapshot));
    }
}
~~~

Lệnh `sorted(Map.Entry.comparingByKey())` là quan trọng: **iteration order của `Map.of`/`Map.copyOf` không phải một hợp đồng sắp xếp**. Nếu serialize trực tiếp theo thứ tự map, golden test có thể thất bại không vì rule thay đổi mà vì thứ tự output khác.

**Cách review một thay đổi có chủ đích:** trước khi sửa expected fixture cho v2, xem rõ diff như `VN=vnPrimary` → `VN=vnCanary`, xác nhận lý do rollout, đúng allowlist và các điều kiện an toàn. Không tự động “update snapshot” mỗi khi test fail — thao tác đó có thể chấp nhận một cấu hình sai mà không ai kiểm tra.

### 6.4. Snapshot test nên so sánh *ý nghĩa*, không so sánh dữ liệu nhiễu

Nếu cấu hình mang các trường như `generatedAt`, `lastPolledAt` hoặc token tạm thời, so sánh byte-to-byte toàn object sẽ gây test dễ thất bại vô ích. Nên chuẩn hóa và chỉ snapshot các trường **mang ngữ nghĩa route**:

- `version` và tập rule được phê duyệt.
- Thứ tự rule **nếu thứ tự thực sự ảnh hưởng quyết định**; không sắp xếp lại các predicate ưu tiên có ý nghĩa.
- Destination key, default/fallback policy, điều kiện chọn nhánh.
- Các giới hạn như max routes, timeout hoặc feature flag nếu chúng làm thay đổi hành vi.

Ngược lại, một map key→value **không có ngữ nghĩa thứ tự** nên có thể sort theo key để làm fixture ổn định. Đây là khác biệt giữa một **snapshot test hữu dụng** và một bản dump ngẫu nhiên.

## 7. Tích hợp snapshot với Spring Integration Dynamic Router

### 7.1. Dynamic về chính sách, tĩnh về channel registry

Spring Integration có các cách xây dựng routing động và điều chỉnh mapping ở runtime, tùy loại router và API framework. Trong ví dụ này, ta chọn cách **đơn giản và dễ kiểm thử**: những channel hợp lệ được đăng ký **tĩnh** khi application context khởi tạo, còn **chính sách chọn routing key** được cập nhật thông qua `RouteState`.

~~~mermaid
flowchart LR
    I[(orders.input)] --> R{Router + RouteState}
    S["AtomicReference<RouteSnapshot>"] -. versioned policy .-> R
    R -->|vnPrimary| A[(orders.vn.primary)]
    R -->|vnCanary| B[(orders.vn.canary)]
    R -->|international| C[(orders.international)]
    A --> HA[Primary Handler]
    B --> HB[Canary Handler]
    C --> HC[International Handler]
~~~

**Giới hạn có chủ đích:** bài này không tạo/destroy bean endpoint khi đổi snapshot. Nếu thêm một **channel mới**, phải bổ sung channel/consumer và triển khai/đăng ký theo cơ chế phù hợp trước khi cho snapshot tham chiếu nó. Atomic swap một `Map` không tự tạo destination kỹ thuật.

### 7.2. Cấu hình Java DSL hoàn chỉnh

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record OrderEvent(String eventId, String market) {}

final class RouteProbe {
    final AtomicInteger primary = new AtomicInteger();
    final AtomicInteger canary = new AtomicInteger();
    final AtomicInteger international = new AtomicInteger();
}

@Configuration
@EnableIntegration
class DynamicOrderRoutingConfiguration {

    @Bean
    RouteState routeState() {
        return new RouteState(new RouteSnapshot(
                "v1",
                Map.of("VN", "vnPrimary",
                        "INTL", "international")));
    }

    @Bean
    RouteProbe routeProbe() {
        return new RouteProbe();
    }

    @Bean(name = "orders.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.vn.primary")
    MessageChannel primary() {
        return new DirectChannel();
    }

    @Bean(name = "orders.vn.canary")
    MessageChannel canary() {
        return new DirectChannel();
    }

    @Bean(name = "orders.international")
    MessageChannel international() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow routeOrders(RouteState state) {
        return IntegrationFlow.from("orders.input")
                .route(OrderEvent.class, event -> {
                    RouteDecision decision =
                            state.decide(event.market());
                    // Điểm ghi structured log/metrics:
                    // eventId, decision.version(),
                    // decision.market(), decision.channelKey().
                    return decision.channelKey();
                }, routes -> routes
                        .channelMapping("vnPrimary", "orders.vn.primary")
                        .channelMapping("vnCanary", "orders.vn.canary")
                        .channelMapping("international",
                                "orders.international"))
                .get();
    }

    @Bean
    IntegrationFlow primaryFlow(RouteProbe probe) {
        return IntegrationFlow.from("orders.vn.primary")
                .handle(OrderEvent.class, (event, headers) -> {
                    probe.primary.incrementAndGet();
                    return null; // One-way event handler.
                })
                .get();
    }

    @Bean
    IntegrationFlow canaryFlow(RouteProbe probe) {
        return IntegrationFlow.from("orders.vn.canary")
                .handle(OrderEvent.class, (event, headers) -> {
                    probe.canary.incrementAndGet();
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow internationalFlow(RouteProbe probe) {
        return IntegrationFlow.from("orders.international")
                .handle(OrderEvent.class, (event, headers) -> {
                    probe.international.incrementAndGet();
                    return null;
                })
                .get();
    }
}
~~~

**Giải thích:**

1. `routeOrders` được wiring **một lần** trong context, nhưng mỗi message gọi `state.decide(...)` nên route thực tế có thể thay đổi sau khi publish snapshot mới.
2. Routing key `vnPrimary`/`vnCanary`/`international` được ánh xạ rõ sang channel bean, không dùng chuỗi tùy ý từ payload làm bean name.
3. `decide` đọc **một snapshot**, tạo `RouteDecision` gồm version và key. Đây là vị trí phù hợp để log/metric quyết định; không gọi `state.snapshot()` lần nữa chỉ để log vì version có thể đã đổi giữa hai lần đọc.
4. Các handler chỉ tăng counter để giúp integration test quan sát kênh nhận. Không có gateway reply hoặc side effect thật trong ví dụ.
5. Mọi channel trong ví dụ là `DirectChannel`. Khi chuyển sang `ExecutorChannel`/`QueueChannel`, cần xem lại semantics accepted/processed, backpressure, timeout và error flow.

**Không đánh đồng:** Ví dụ dùng **policy động trên một DSL Router** để dạy snapshot consistency. Nó **không khẳng định** đang sử dụng lớp `DynamicRouter` cụ thể hoặc API cập nhật runtime mapping nội bộ của Spring Integration. Khi muốn thao tác trực tiếp lên mapping của router/framework qua management API, phải xác minh **semantics đồng thời của API đó** thay vì cho rằng nhiều lệnh update entry tự động được publish như một snapshot nguyên tử.

### 7.3. Một quyết định phải được ghi cùng version đã dùng

Vì policy có thể đổi sau `decide`, cách log sau đây dễ gây nhầm:

~~~java
// Anti-pattern: đọc snapshot thêm lần nữa sau khi route.
String chosen = state.decide(event.market()).channelKey();
String loggedVersion = state.snapshot().version();
// chosen có thể thuộc v1 trong khi loggedVersion là v2.
~~~

Cách đúng:

~~~java
RouteDecision decision = state.decide(event.market());
String chosen = decision.channelKey();
String loggedVersion = decision.version();
// Cả chosen và loggedVersion thuộc cùng một snapshot.
~~~

Nếu các endpoint sau cần biết version, hãy **truyền `RouteDecision` hoặc `policyVersion` như metadata được tạo từ cùng một lần quyết định** trong một bước atomic của flow; đừng gắn header bằng cách đọc policy lần thứ hai rồi route ở bước sau bằng một lần đọc khác. Trên ranh giới broker/adapter, metadata này cần mapping và validation phù hợp.

## 8. Integration test: snapshot mới thực sự đổi channel đích

### 8.1. Đường kiểm thử

Đối với `DynamicOrderRoutingConfiguration` ở phần 7, cần kiểm thử:

~~~text
Snapshot v1
  OrderEvent(market=VN)
    -> Router -> orders.vn.primary -> primary counter +1

Publish snapshot v2
  OrderEvent(market=VN)
    -> Router -> orders.vn.canary -> canary counter +1

OrderEvent(market=INTL) ở cả v1/v2
    -> Router -> orders.international
~~~

Một unit test chỉ xác nhận `RouteState.decide("VN")` trả `vnCanary` là chưa đủ. Cần kiểm tra rằng **routing key và channel mapping của Spring Integration** nối đúng với consumer thực tế.

### 8.2. JUnit 5 + Spring Test

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(DynamicOrderRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DynamicOrderRoutingIntegrationTest {

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Autowired
    private RouteState routeState;

    @Autowired
    private RouteProbe probe;

    private void publish(String id, String market) {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        new OrderEvent(id, market)).build(),
                1_000));
    }

    @Test
    void initialSnapshotUsesPrimaryRoute() {
        assertEquals("v1", routeState.snapshot().version());
        assertEquals(Map.of(
                "VN", "vnPrimary",
                "INTL", "international"),
                routeState.snapshot().routes());

        publish("EVT-1", "VN");

        assertEquals(1, probe.primary.get());
        assertEquals(0, probe.canary.get());
        assertEquals(0, probe.international.get());
    }

    @Test
    void changingSnapshotMovesNewEventsToCanary() {
        publish("EVT-OLD", "VN");

        RouteSnapshot next = new RouteSnapshot("v2", Map.of(
                "VN", "vnCanary",
                "INTL", "international"));
        assertTrue(routeState.swapIfVersion("v1", next));

        publish("EVT-NEW", "VN");
        publish("EVT-INTL", "INTL");

        assertEquals(1, probe.primary.get());
        assertEquals(1, probe.canary.get());
        assertEquals(1, probe.international.get());
        assertEquals("v2", routeState.snapshot().version());
    }
}
~~~

**Ý nghĩa kiểm thử:**

- `@DirtiesContext` cô lập trạng thái mutable của `RouteState` và `RouteProbe` giữa các test, tránh phụ thuộc vào thứ tự chạy.
- Test v1 kiểm tra **cả snapshot và channel thực nhận message**, nên mạnh hơn unit test mapping riêng.
- Test v2 chứng minh **cùng một flow bean** vẫn chạy nhưng **message mới** đổi đích sau update.
- Số đếm chỉ chứng minh các handler mô phỏng đã nhận message qua `DirectChannel`, chưa chứng minh external side effect hoặc persistence.

Khi thay channel đích bằng `ExecutorChannel`, `QueueChannel` hoặc broker, các assertion counter ngay sau `send` không còn là hợp đồng chung. Lúc đó dùng latch/await với timeout và test riêng trạng thái **accepted**, **processed**, **committed**.

### 8.3. Test snapshot “đúng” nhưng channel không có consumer

Trong ví dụ, snapshot `VN → vnCanary` hợp lệ vì `vnCanary` nằm trong allowlist. Nhưng nếu `orders.vn.canary` không có handler đang đăng ký, điều gì xảy ra?

1. **Policy layer** vẫn trả một key hợp lệ.
2. **Spring Integration router** vẫn có thể phân giải được tên bean channel.
3. **Dispatch layer** có thể thất bại vì channel không có subscriber, hoặc consumer đang stopped.
4. **Business result** không thể coi là thành công chỉ dựa vào bước 1 và 2.

Vì vậy, cần test riêng một context thiếu consumer hoặc điều khiển lifecycle endpoint rồi xác minh lỗi/timeout theo semantics channel. Với `DirectChannel`, không có subscriber thì message **không tự được buffer để xử lý sau**.

### 8.4. Cần log version ở đâu để đối chiếu test?

Một bản ghi có cấu trúc hữu ích:

~~~text
event=ROUTE_DECIDED eventId=EVT-NEW
  routeVersion=v2 market=VN channelKey=vnCanary
  destination=orders.vn.canary

event=BRANCH_ENTERED eventId=EVT-NEW
  subscriber=canaryHandler destination=orders.vn.canary

event=BRANCH_COMPLETED eventId=EVT-NEW
  outcome=SUCCESS
~~~

Đây là **schema log ứng dụng đề xuất**, không phải log mặc định của Spring Integration. Test có thể capture các sự kiện này trong test logger/collector, nhưng tránh phụ thuộc vào thứ tự log không quan trọng hoặc message ID có thể thay đổi khi flow tạo message mới.

## 9. Kiểm thử thay đổi đồng thời và request đang chạy

### 9.1. Hai operator cùng publish từ v1

Một tình huống thực tế:

~~~text
Active = v1

Operator A:
  expected=v1, candidate=v2-canary

Operator B:
  expected=v1, candidate=v2-primary

Ai publish trước thì thắng.
Người còn lại phải nhận xung đột, tải lại trạng thái và quyết định lại.
~~~

Nếu không kiểm tra version, B có thể vô tình ghi đè ngay thay đổi của A mà không hề hay biết.

### 9.2. JUnit kiểm tra CAS chỉ chấp nhận một writer

~~~java
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConcurrentRouteUpdateTest {

    @Test
    void twoWritersFromSameVersionCannotBothWin()
            throws Exception {
        RouteState state = new RouteState(new RouteSnapshot(
                "v1", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international")));

        RouteSnapshot candidateA = new RouteSnapshot(
                "v2-canary", Map.of(
                        "VN", "vnCanary",
                        "INTL", "international"));
        RouteSnapshot candidateB = new RouteSnapshot(
                "v2-primary", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<Boolean> a = pool.submit(() -> {
                ready.countDown();
                if (!start.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Start timeout");
                }
                return state.swapIfVersion("v1", candidateA);
            });
            Future<Boolean> b = pool.submit(() -> {
                ready.countDown();
                if (!start.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Start timeout");
                }
                return state.swapIfVersion("v1", candidateB);
            });

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            int successCount = (a.get(10, TimeUnit.SECONDS) ? 1 : 0)
                    + (b.get(10, TimeUnit.SECONDS) ? 1 : 0);
            assertEquals(1, successCount);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Đây không phải kiểm thử thời gian tuyệt đối: latch giúp hai writer chuẩn bị gần nhau, còn **tính đúng** dựa trên CAS và điều kiện expected version. Ngay cả khi thread scheduling khiến chúng thực hiện lệch nhau, khi hai writer cùng dùng `expected=v1` thì **tối đa một** phép publish có thể thành công.

Trong production, nếu API cập nhật cấu hình trả conflict, người quản trị phải **review diff với snapshot mới nhất**, không tự động retry bằng cách đổi expected version rồi ghi đè policy của người khác.

### 9.3. Kiểm thử không đọc lẫn version và route key

Một bài test nhiều thread hữu ích là lặp rất nhiều quyết định trong lúc một thread đang publish v2, sau đó kiểm tra mỗi kết quả chỉ thuộc một trong hai cặp:

~~~text
Allowed decisions:
  (version=v1, channelKey=vnPrimary)
  (version=v2, channelKey=vnCanary)

Forbidden:
  (version=v1, channelKey=vnCanary)
  (version=v2, channelKey=vnPrimary)
~~~

Có thể dùng thread đọc lặp `state.decide("VN")`, trong khi thread khác đổi snapshot đúng một lần. Test **không nên** assert tỷ lệ v1/v2 cố định vì lịch chạy phụ thuộc scheduler; chỉ assert **tính nhất quán của từng cặp**. Đây là kiểm thử mô hình đọc **một reference bất biến** tốt hơn phép đo thời gian mong manh.

### 9.4. Kiểm thử in-flight event không bị “dịch chuyển”

Một test nâng cao dùng `CountDownLatch` ở Primary Handler:

1. Đặt active snapshot v1; gửi `EVT-OLD` vào một thread riêng.
2. Handler primary báo `started` rồi chờ trên latch.
3. Trong khi `EVT-OLD` đang ở handler primary, publish snapshot v2.
4. Gửi `EVT-NEW` và xác minh nó vào Canary Handler.
5. Mở latch cho primary hoàn tất; xác minh `EVT-OLD` vẫn hoàn thành ở primary, không được reroute vào canary.

**Vì sao cần thread riêng?** `DirectChannel` đồng bộ: nếu gọi `send(EVT-OLD)` trên chính test thread rồi handler chờ latch, test thread sẽ bị chặn và không thể publish v2. Đồng thời, luôn giải phóng latch trong `finally` và dùng deadline hữu hạn.

Test này xác minh **route decision tại điểm dispatch được giữ nguyên cho message đang xử lý**. Nó không chứng minh toàn bộ workflow nhiều Router sau đó dùng v1: nếu các bước sau **tự tính route bằng state mới**, chúng vẫn có thể dùng v2. Với workflow yêu cầu **pin version xuyên nhiều bước**, hãy mang decision/snapshot ID qua message và cho những bước sau tuân thủ version đã chọn, thay vì đọc mặc định “latest” một lần nữa.

## 10. Rollback và kiểm thử bản cấu hình phục hồi

### 10.1. Rollback không phải sửa từng entry về chỗ cũ

Sau khi canary gặp lỗi, đừng thực hiện:

~~~text
routeMap.put("VN", "vnPrimary")
routeMap.put("INTL", "international")
currentVersion = "v1"
~~~

Các thao tác này có thể để lộ trạng thái trung gian, gây nhầm về lịch sử thay đổi và khó audit. Thay vào đó, tạo một snapshot mới từ cấu hình tốt đã được duyệt:

~~~java
RouteSnapshot rollback = new RouteSnapshot(
        "v3-rollback",
        Map.of("VN", "vnPrimary",
                "INTL", "international"));

boolean restored =
        state.swapIfVersion("v2", rollback);
// restored == true nếu active vẫn là v2.
~~~

Version mới `v3-rollback` giúp phân biệt **một lần kích hoạt mới** với dữ liệu của v1. Rollback chỉ thay quyết định đối với **message được định tuyến sau đó**, không đảo ngược các tác động canary đã gây ra trước đó.

### 10.2. Test phải chứng minh ba giai đoạn

| Giai đoạn | Snapshot active | Route `VN` kỳ vọng |
|---|---|---|
| Trước rollout | v1 | `vnPrimary` |
| Sau rollout canary | v2 | `vnCanary` |
| Sau rollback | v3-rollback | `vnPrimary` |

Một bài test rollback nên chứng minh:

- Không có snapshot không hợp lệ được publish.
- Rollback có expected version để không ghi đè một thay đổi mới của operator khác.
- Message mới đi lại primary.
- Message **đã dispatch vào canary** không bị cho là tự biến mất hoặc tự đảo ngược side effect.
- Metric và log ghi `v3-rollback`, không ngụy trang đó là một lần chạy v1.

### 10.3. Kết quả đã xử lý dưới v2

Nếu canary đã gửi email, ghi database hoặc gọi API ngoài, rollback cấu hình route **không rollback side effect**. Để phục hồi nghiệp vụ cần idempotency, reconciliation, retry tại đúng điểm lỗi hoặc compensation theo hợp đồng.

Đặc biệt, nếu client timeout rồi retry sau rollback, hai attempt có thể được xử lý bởi **hai phiên bản route khác nhau**. Hãy thiết kế operation ID ổn định, quyết định retry phải tiếp tục hành trình cũ hay được phép dùng route mới, và log version để chẩn đoán.

## 11. Một snapshot trong JVM khác một snapshot trên toàn cluster

### 11.1. Vấn đề cấu hình lệch giữa các replica

Giả sử hệ thống có ba instance:

~~~text
app-A: route-policy-v2   VN -> vnCanary
app-B: route-policy-v1   VN -> vnPrimary
app-C: route-policy-v2   VN -> vnCanary
~~~

Tất cả có thể **đúng về mặt nhất quán trong từng process**, nhưng một request VN qua load balancer có thể đến primary hoặc canary tùy node. Điều này là lỗi nếu sản phẩm yêu cầu thay đổi đồng loạt; nhưng lại có thể là **rollout chủ đích** nếu đang canary theo node.

**Không thể giải quyết bằng một `AtomicReference` dùng chung tưởng tượng.** Mỗi JVM có reference riêng. Khi dùng central configuration store, message bus thông báo thay đổi hoặc deployment rollout, phải xác định:

| Câu hỏi | Điều cần quyết định |
|---|---|
| Ai là nguồn chân lý? | Config store/DB/versioned artifact nào được phê duyệt? |
| Node cập nhật khi nào? | Pull định kỳ, push event hoặc reload khi deploy? |
| Node bỏ lỡ event cập nhật thì sao? | Reconcile/poll lại bản active; kiểm tra version, không giả định delivery một lần duy nhất. |
| Version có thứ tự thế nào? | Không cho event v1 đến muộn ghi đè v2; có epoch/sequence nếu cần. |
| Có cho nhiều version chạy đồng thời không? | Rollout dần/canary hay bắt buộc cutover đồng loạt? |
| Node bị lệch cấu hình có nhận traffic không? | Readiness gate, alert hoặc policy canary rõ ràng. |
| Config store mất kết nối? | Tiếp tục bằng last-known-good hay fail closed theo mức quan trọng? |

Nếu update không nhất thiết đồng thời toàn cluster, log mỗi route decision cần ghi **nodeId, policyVersion và channelKey** để truy nguyên. Khi yêu cầu tất cả node đồng bộ trước khi nhận traffic, phải có deployment/activation protocol, không chỉ publish snapshot ở một node.

### 11.2. Kiểm tra hash và drift

Một kiểm tra vận hành hữu ích:

~~~text
node=A  version=v2  policyHash=sha256:abc...
node=B  version=v1  policyHash=sha256:def...
node=C  version=v2  policyHash=sha256:abc...
~~~

`policyHash` là **digest của dạng chuẩn hóa** cho các trường route có ý nghĩa. Để hash ổn định, phải sort các map không có thứ tự, chuẩn hóa encoding và tránh đưa timestamp tạm vào. Cùng version mà khác hash là một bất thường nghiêm trọng: có thể hai node đã đọc **hai nội dung khác nhau dưới cùng một nhãn version**.

Không xem hash là bằng chứng kết quả nghiệp vụ. Nó chỉ giúp phát hiện/config drift, không chứng minh handler đích khỏe.

### 11.3. Test cấp cluster

Một kế hoạch integration/system test:

1. Khởi động hai node với cùng v1; xác nhận cả hai report version/hash giống nhau.
2. Publish v2 qua cơ chế config distribution thật.
3. Chờ theo deadline hợp lệ; xác minh các node bắt buộc áp dụng v2 trước khi gửi traffic yêu cầu consistency.
4. Thử gửi message qua từng node; đối chiếu route version trong log và destination thực nhận.
5. Giả lập node tạm mất kết nối cập nhật, sau đó reconnect và reconcile.
6. Gửi một update cũ đến muộn để xác minh node không rollback âm thầm.
7. Thử chiến lược canary nếu hệ thống **chủ động cho phép** nhiều version đồng thời.

Các bước trên **không phải** unit test của `RouteState`; chúng kiểm tra phân phối cấu hình và hành vi trên nhiều replica.

## 12. Dynamic route còn có những lỗi nào?

### 12.1. Snapshot hợp lệ nhưng Router vẫn lỗi

~~~mermaid
flowchart TD
    A[Message vào] --> R[Chọn snapshot + routing key]
    R -->|Key không hợp lệ| E1[Validation / routing error]
    R -->|Key hợp lệ| M[Map tới channel]
    M -->|Channel không tồn tại| E2[Resolution error]
    M -->|Channel tồn tại| D[Dispatch]
    D -->|Không có consumer / queue đầy| E3[Delivery error]
    D -->|Consumer nhận| H[Handler]
    H -->|Lỗi downstream| E4[Processing error]
    H -->|Hoàn tất| OK[Outcome theo contract]
~~~

Phân biệt **policy failure**, **destination resolution failure**, **delivery failure** và **processing failure**. Chúng cần dashboard, retry và recovery khác nhau:

| Nguồn lỗi | Retry nguyên message ngay có ích không? | Gợi ý xử lý |
|---|---|---|
| Market/key không hợp lệ | Thường không. | Validation/business rejection; không tự map tới một tenant khác. |
| Snapshot thiếu mapping | Không nên publish snapshot lỗi. | Bắt tại preflight, rollback candidate, cảnh báo. |
| Channel bean không tồn tại | Retry không tự tạo bean. | Đảm bảo destination đã deploy/registered trước activation. |
| Consumer stopped | Có thể tạm thời. | Readiness/maintenance, buffer đúng semantics hoặc từ chối rõ. |
| Queue/executor quá tải | Có thể, nhưng cần bounded retry. | Backpressure, timeout, scale và capacity. |
| Downstream HTTP timeout | Có thể, nếu nghiệp vụ hỗ trợ. | Backoff, idempotency/reconciliation khi outcome không chắc chắn. |
| Handler ném lỗi vĩnh viễn | Thường không. | Error flow, DLQ/manual repair; không retry storm. |

### 12.2. Đồng bộ và bất đồng bộ khác nhau

Với `DirectChannel`, exception từ router/handler thường có thể truyền lại sender trong cùng call stack. Với `ExecutorChannel`, `QueueChannel` có poller hoặc broker adapter, exception có thể xảy ra **sau khi upstream đã accept**, được chuyển vào `ErrorMessage`/`errorChannel` trong những ngữ cảnh đã cấu hình.

**Đừng giả định** mọi lỗi đều tự xuất hiện trên một error channel chung. Nếu dùng một `IntegrationFlow` bất đồng bộ, hãy kiểm tra error handling của đúng adapter, poller, gateway và transport. Một lỗi vào error channel không tự đảm bảo message được retry hoặc business side effect được rollback.

### 12.3. Không tái định tuyến retry theo latest một cách vô thức

Giả sử v1 gửi `EVT-42` sang primary, handler primary timeout; ngay sau đó active snapshot đổi thành v2 và retry được đưa **ngược lại đầu vào Router**. Retry có thể đi sang canary, khiến **cùng business operation** được xử lý ở hai đường.

Các phương án cần lựa chọn rõ:

- **Sticky route per operation:** giữ `routeDecision.version` và destination đã chọn, retry tại cùng nhánh.
- **Re-evaluate latest snapshot:** retry được phép dùng policy mới, nhưng phải có chính sách idempotency và audit về chuyển tuyến.
- **Recovery routing:** lỗi được đưa sang DLQ/quarantine hoặc operator quyết định replay bằng phiên bản khác.

Không có một cách áp dụng cho mọi nghiệp vụ. Với thanh toán, xuất hóa đơn hoặc cập nhật tồn kho, sự nhất quán/idempotency thường quan trọng hơn việc “luôn chọn version mới nhất”.

### 12.4. Dynamic Router không thay thế authorization

Nếu message chứa `market=VN`, cần xác định giá trị đó đến từ đâu. Với public API, caller có thể tự gửi `market=INTL` hoặc một header `routeKey` giả mạo. `RouteSnapshot` chỉ kiểm tra **tập key và destination được cho phép**, không xác minh client có quyền chọn market đó.

Ở vùng biên tin cậy:

1. Xác thực identity và tenant.
2. Chuẩn hóa market từ dữ liệu nghiệp vụ có kiểm tra.
3. Tính routing key theo policy server-side.
4. Chỉ cho phép destination nằm trong registry được chấp thuận.
5. Ghi audit cho thay đổi cấu hình và những quyết định quan trọng.

Không expose một API cập nhật route không có phân quyền, xác thực, phê duyệt và audit. Một rule có thể chuyển dữ liệu sang kênh khác; vì vậy đây là **bề mặt điều khiển nghiệp vụ**, không phải chỉ là cấu hình vô hại.

## 13. Quy trình triển khai một snapshot mới

Một quy trình thực tế có thể chia thành sáu pha:

~~~mermaid
flowchart LR
    A[Prepare] --> B[Validate]
    B --> C[Test]
    C --> D[Approve]
    D --> E[Activate]
    E --> F[Observe / rollback]
~~~

**Prepare:** tạo `RouteSnapshot v2` với version mới và bản diff từ v1. Kiểm tra schema, số key bắt buộc, destination allowlist và metadata thay đổi.

**Validate:** xác minh destination bean/channel đã đăng ký trong release tương ứng, endpoint có readiness phù hợp, đường reject/fallback rõ và các tổ hợp rule không có lỗ hổng.

**Test:** chạy unit test `RouteSnapshotValidationTest`, `RouteStateVersionTest`, golden snapshot và integration test v1→v2. Với thay đổi lớn, test canary/staging qua transport thật.

**Approve:** người được phân quyền xác nhận diff, phạm vi rollout, version/hash và kế hoạch rollback. Tránh tự động đồng ý chỉ vì test snapshot đã cập nhật expected.

**Activate:** publish atomic bằng expected version. Nếu CAS/central config update báo conflict, **reload và review lại**, không force overwrite.

**Observe:** theo dõi route decisions, xử lý từng nhánh, lỗi/timeout/backlog, version trên từng node; nếu vượt ngưỡng lỗi thì publish snapshot rollback mới theo policy.

### 13.1. Các tín hiệu cần có ngay sau activation

| Tín hiệu | Câu hỏi |
|---|---|
| `route_policy_active_version` | Mỗi node đang dùng version nào? |
| `route_policy_hash` | Cùng version có cùng nội dung không? |
| `route_update_attempts/conflicts` | Có tranh chấp cấu hình, update thất bại? |
| `route_decisions_total{version,key}` | Traffic thực đi theo phiên bản và nhánh nào? |
| `route_resolution_errors_total` | Có key/channel chưa được phân giải? |
| `branch_received_total{destination}` | Handler đích có thực sự nhận message? |
| `branch_completed/failed_total` | Tỷ lệ kết quả nghiệp vụ theo nhánh? |
| `queue_depth` / `oldest_message_age` | Canary có bị nghẽn/đọng message? |

Đây là **tên metric minh họa do ứng dụng đề xuất**, không phải meter tự sinh mặc định của Spring Integration. Không đưa `orderId`, `eventId`, `traceId` vào label metric vì cardinality cao; hãy dùng log/tracing có quyền truy cập thích hợp.

### 13.2. Canary rollout và snapshot tests

Canary rollout có thể dùng một snapshot v2 cho một phần traffic hoặc node. Cần kiểm soát **cách phân bổ ổn định**: không dùng một hàm random không seed để quyết định đường đi rồi kỳ vọng test luôn lặp lại kết quả.

Nếu điều kiện routing dựa trên tỷ lệ, snapshot nên thể hiện rule có seed/hash ổn định, ví dụ dựa vào `customerId` hoặc `orderId` đã xác thực. Test không chỉ so sánh tỷ lệ tổng mà còn xác minh **cùng một request ID** luôn nhận kết quả nhất quán theo phiên bản rule. Khi đổi seed hoặc version, quyết định cũ có thể khác; cần policy rõ cho retry/replay.

**Không đưa tỷ lệ canary vào ví dụ `RouteState` ở phần 5** vì nó chỉ minh họa deterministic mapping `VN → primary/canary`. Muốn weighted routing phải bổ sung một rule có semantics và test riêng.

## 14. Ma trận kiểm thử snapshot cấu hình route

| Nhóm | Kịch bản | Điều phải chứng minh |
|---|---|---|
| Schema | Thiếu version hoặc blank version | Snapshot bị từ chối trước publish. |
| Schema | Thiếu key `INTL` hoặc có key ngoài tập | Snapshot bị từ chối. |
| Security | Destination ngoài allowlist | Snapshot không được active. |
| Immutability | Caller sửa `Map` nguồn | Snapshot active không đổi. |
| Immutability | Caller sửa `snapshot.routes()` | Không sửa được. |
| Determinism | Serialize expected với `Map.of` | Canonical snapshot ổn định, không phụ thuộc iteration order. |
| Functional | v1 + VN | Quyết định `vnPrimary` và handler primary nhận message. |
| Functional | v2 + VN | Quyết định `vnCanary` và handler canary nhận message. |
| Regression | v1/v2 + INTL | Vẫn đi đúng `orders.international`. |
| Version | Đổi snapshot v1→v2 | Decision cũ vẫn thuộc v1, decision mới thuộc v2. |
| Version | Hai writer từ expected v1 | Chỉ một update thành công, writer còn lại nhận conflict. |
| Version | Publish snapshot mới nhưng giữ tên version cũ | Bị từ chối ở policy cập nhật; hệ thống config ngoài cũng phải enforce uniqueness. |
| In-flight | Event ở primary khi active đổi | Event đó không tự bị chuyển sang canary. |
| Unknown input | Market không được hỗ trợ | Error/rejection rõ; không route tùy tiện. |
| Channel | Mapping hợp lệ nhưng bean thiếu | Deployment/integration test phát hiện lỗi trước rollout. |
| Subscriber | Endpoint canary stopped | Không công bố business success chỉ vì key đã phân giải. |
| Capacity | Queue canary đầy | Producer thấy overload, timeout/recovery theo contract. |
| Retry | v1 xử lý lỗi rồi v2 active | Có sticky/re-evaluate policy rõ, idempotency được test. |
| Rollback | v2 lỗi và rollback thành v3 | Message mới quay primary, event cũ vẫn truy nguyên được v2. |
| Cluster | Một replica lỡ update | Drift được phát hiện và xử lý theo rollout policy. |
| Ordering | Event cập nhật cũ đến sau mới | Node không âm thầm hồi quy xuống version cũ. |
| Observability | Log route decision | Version/key/destination cùng thuộc **một** quyết định. |

Một test suite tốt cần kết hợp **unit**, **integration**, **concurrency** và **system/cluster tests**. Không nhất thiết mọi job CI đều chạy test multi-node nặng; nhưng release pipeline phải có bằng chứng tương ứng với mức rủi ro mà thay đổi cấu hình tạo ra.

## 15. Sai lầm thường gặp

| Hiểu nhầm | Hậu quả | Cách làm đúng |
|---|---|---|
| “Snapshot là một `Map` có thể chỉnh trực tiếp.” | Reader thấy dữ liệu lai, đôi khi thiếu key. | Copy bất biến và atomic swap nguyên object. |
| “Có `volatile` cho version và map là atomic.” | Version và mapping có thể không khớp. | Gộp cả hai vào `RouteSnapshot`. |
| “Test chỉ `VN` đủ để snapshot đúng.” | Key khác lỗi nhưng không phát hiện. | Test toàn bộ required keys/fallback và allowlist. |
| “`Map.of` có thứ tự cố định.” | Golden test flaky. | Chuẩn hóa/sort trước khi so sánh. |
| “Snapshot test pass nghĩa là route đã xử lý xong.” | Channel/consumer có thể thiếu hoặc lỗi. | Integration test và quan sát completed outcome. |
| “Cập nhật policy tạo luôn channel/handler mới.” | Router trỏ đến destination không tồn tại. | Deploy/đăng ký destination trước activation. |
| “Mỗi lần log version đọc lại active state là chính xác.” | Log v2 nhưng route đã chọn v1. | Dùng `RouteDecision` từ một lần đọc. |
| “AtomicReference áp dụng chung mọi replica.” | Các node có route khác nhau không được phát hiện. | Version/hash và config distribution/rollout policy. |
| “Retry sau update luôn dùng route mới.” | Một operation xử lý ở hai đích, trùng side effect. | Sticky/re-evaluate policy và idempotency. |
| “Rollback xóa mọi ảnh hưởng canary.” | Side effect v2 vẫn còn. | Phục hồi nghiệp vụ và audit riêng. |
| “Cập nhật expected golden khi fail là xong.” | Vô tình phê duyệt rule sai. | Review diff, yêu cầu xác nhận thay đổi có chủ đích. |
| “Header market từ client đủ để chọn tenant.” | Route spoofing, sai phân vùng dữ liệu. | Xác thực, chuẩn hóa, cho phép đúng nguồn. |
| “Dynamic Router tự xử lý mọi lỗi retry/error channel.” | Lỗi bị bỏ sót, retry storm. | Phân loại failure và thiết kế recovery rõ. |

## 16. Bài tập thực hành

1. **Cấu hình v1:** tạo `RouteSnapshot` cho `VN → vnPrimary` và `INTL → international`; viết test snapshot đầy đủ và immutable.
2. **Tạo v2:** đổi `VN → vnCanary`, so sánh canonical snapshot với expected, giải thích diff và những channel nào phải tồn tại trước activation.
3. **Atomic update:** viết `swapIfVersion`, cho hai operator cùng gửi expected `v1` rồi kiểm tra chỉ một phiên bản mới thắng.
4. **In-flight:** dùng latch giữ Primary Handler của event v1, publish v2 và gửi event v2; chứng minh event cũ không tự bị reroute.
5. **Invalid mapping:** thêm `VN → orders.secret` hoặc bỏ key `INTL`; kiểm tra snapshot bị từ chối ngay khi tạo.
6. **No subscriber:** dừng endpoint canary hoặc bỏ bean handler trong test context; phân biệt lỗi snapshot, channel resolution và delivery.
7. **Async channel:** thay canary bằng `QueueChannel` có capacity nhỏ và poller; chứng minh `send` thành công không đồng nghĩa handler đã hoàn tất.
8. **Golden fixture:** tạo bản canonical v1; cố tình đổi một mapping mà không đổi expected. Review lỗi test và chỉ chấp nhận diff được phê duyệt.
9. **Rollback:** triển khai v3-rollback trở về primary, ghi đầy đủ version của quyết định trước/sau rollback.
10. **Cluster drift:** mô phỏng hai node v1/v2, đưa version/hash vào health/admin state; xác định khi nào được phép nhận traffic.
11. **Replay:** một operation thất bại ở v1 nhưng được retry khi v2 active. Lựa chọn và chứng minh sticky route hoặc policy re-evaluate an toàn.
12. **Canary rule:** thêm một điều kiện deterministic dựa trên business ID và tỷ lệ canary; test output ổn định theo snapshot version.
13. **Observability:** log `ROUTE_DECIDED` và `BRANCH_COMPLETED` có `eventId`, `policyVersion`, `destination`; tìm một event lỗi qua tracing.
14. **Security:** thử gửi header routeKey từ client để yêu cầu channel ngoài allowlist; chứng minh hệ thống không cho chọn bean tùy ý.

### Câu hỏi tự kiểm tra

**Câu 1:** Một reader đang giữ snapshot v1; writer publish v2. Reader đó có được phép tiếp tục dùng v1 không? **Có.** Đây là tính chất mong muốn của snapshot bất biến trong lúc một quyết định được thực hiện.

**Câu 2:** Nếu log version được đọc riêng với routing key, sai lệch nào có thể xảy ra? **Version v2 được ghi nhưng key được quyết định theo v1**, khiến audit không chính xác.

**Câu 3:** Vì sao `Map.copyOf` là chưa đủ nếu version và mapping vẫn nằm trong hai biến mutable độc lập? **Vì** việc thay hai biến không atomic và reader có thể thấy trạng thái lai.

**Câu 4:** Golden snapshot test chỉ kiểm tra bảng `VN → vnCanary` có chứng minh endpoint canary đang chạy không? **Không.** Cần integration/lifecycle/readiness test.

**Câu 5:** Hai writer cùng dựa trên expected v1 có được phép âm thầm ghi đè nhau không? **Không.** Dùng CAS/version conflict và review lại bản mới nhất.

**Câu 6:** Sau rollback từ v2 sang v3, event đã vào canary có tự quay lại primary không? **Không.** Rollback ảnh hưởng quyết định mới; side effect/in-flight cần recovery riêng.

**Câu 7:** `AtomicReference<RouteSnapshot>` có đồng bộ ba replica Spring Boot không? **Không.** Nó chỉ bảo đảm cập nhật/đọc nhất quán trong một JVM; cluster cần cơ chế phân phối riêng.

**Câu 8:** Khi retry một nghiệp vụ sau khi route đổi, có nên mặc nhiên tính route mới nhất? **Không.** Cần hợp đồng sticky route hay re-evaluation, idempotency và audit phiên bản.

**Câu 9:** Có nên cho HTTP client gửi nguyên tên channel `orders.admin` làm routing key không? **Không.** Cần xác thực, allowlist và tách business key khỏi destination bean.

## 17. Kết luận

**Kiểm thử snapshot cấu hình route** không chỉ là so sánh một file YAML với expected. Đó là chứng minh một chính sách định tuyến **đầy đủ, bất biến, có version, được publish nguyên tử và được áp dụng nhất quán cho từng message**. Bên cạnh unit test validation/golden snapshot, cần integration test để biết Spring Integration thực sự gửi vào channel đích, concurrency test cho atomic update, in-flight test, rollback test và kiểm tra drift khi chạy nhiều replica.

Trong `SPRING_INTEGRATION_PATTERN`, Dynamic Router giúp thay policy mà vẫn giữ flow ít phụ thuộc. Muốn an toàn, hãy tách **routing rule** khỏi **channel registry**, không cho message chọn arbitrary bean, ghi route decision cùng version từ **một lần đọc snapshot**, xử lý retry/idempotency/error channel theo từng nhánh, rồi giám sát outcome thực thay vì chỉ nhìn `send=true`. Khi đó snapshot test trở thành một hàng rào đáng tin cậy trước những thay đổi route có thể ảnh hưởng trực tiếp đến nghiệp vụ.
