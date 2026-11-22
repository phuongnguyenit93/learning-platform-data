# Quy trình truy vết từ yêu cầu phân giải tới đăng ký, đồ thị và vòng đời

Khi ứng dụng Java dùng **Dependency Injection (DI)** khởi động thất bại hoặc một service nhận sai cộng tác viên, thông báo lỗi đầu tiên thường chưa giải thích hết nguyên nhân. Ví dụ, màn hình có thể chỉ hiển thị “không tạo được `CheckoutHandler`”, trong khi vấn đề thực sự là một `AuditClient` chưa được đăng ký, một qualifier chọn sai implementation, hoặc một dependency có vòng đời theo request bị giữ trong singleton.

Để chẩn đoán đáng tin cậy, ta cần theo dõi **toàn bộ đường đi từ yêu cầu phân giải (*resolution request*) tới registration/binding, object graph, scope và quyền sở hữu tài nguyên**. Không nên sửa bằng cách thêm `new`, đổi annotation hoặc chuyển mọi bean thành singleton trước khi biết lỗi nằm ở đâu.

Bài thuộc chương **Chẩn đoán DI** của module Dependency Injection, tiếp nối constructor injection, Inversion of Control (IoC), composition root, scope và lifecycle. Ta sẽ học quy trình truy vết có thể áp dụng cho **DI thủ công** lẫn **DI container**, rồi thực hành bằng Java 17 thuần với một resolver nhỏ có khả năng ghi sự kiện. Ví dụ không cần framework và không thay thế container production.

> **Nguyên tắc:** một lần phân giải có nhiều quyết định độc lập: *yêu cầu kiểu gì*, *binding nào đáp ứng*, *cần xây graph nào*, *instance được chia sẻ trong scope nào*, *ai giữ và đóng resource*. Chẩn đoán phải xác định quyết định sai trước khi thay đổi cách lắp ghép.

## 1. Nhận diện triệu chứng và phân loại vị trí lỗi

Các triệu chứng DI thường có biểu hiện giống nhau nhưng nguyên nhân khác nhau:

| Triệu chứng | Câu hỏi đầu tiên | Ví dụ nguyên nhân |
|---|---|---|
| “No bean/binding for X” | X được yêu cầu từ đường nào? | Chưa đăng ký interface, registration không thuộc profile hiện tại |
| “Multiple candidates for X” | Có bao nhiêu binding, qualifier nào được chọn? | Hai implementation cùng thỏa contract, thiếu lựa chọn tường minh |
| “Circular dependency” | Chu trình nằm trên đường constructor nào? | A cần B, B lại cần A |
| “Cannot resolve scoped dependency” | Đang phân giải bên trong scope nào? | Request dependency được yêu cầu ngoài request |
| Service của request B dùng dữ liệu request A | Instance nào bị giữ lâu hơn hợp đồng? | Singleton giữ request context hoặc session |
| Đã shutdown nhưng vẫn có task gọi client | Ai dừng nhận việc và ai đóng client trước? | Consumer chưa drain đã đóng pool |
| Tạo service thành công nhưng lần gọi đầu mới lỗi | Registration được validate lúc nào? | Lazy resolution, config lỗi hoặc hạ tầng mất sẵn sàng |
| Test pass nhưng production dùng sai implementation | Graph test khác graph production ở đâu? | Qualifier, profile, override, feature flag hoặc tenant setting |

Đừng lập tức quy mọi lỗi tới framework. Nếu constructor đòi `PaymentGateway` nhưng không có binding, đây là **lỗi composition**. Nếu gateway đã được cấp nhưng network timeout, đó là **lỗi vận hành của collaborator**. Nếu gateway trả kết quả sai nghiệp vụ, đây là **lỗi hành vi hoặc hợp đồng**, không phải lỗi resolver.

Một phương pháp chẩn đoán tốt tách ba lớp:

1. **Composition:** type, registration, selection, constructor và graph.
2. **Lifetime:** scope, cache, thời gian sống, quyền đóng và dependency bị giữ lâu.
3. **Execution:** lời gọi nghiệp vụ, timeout, network, transaction và dữ liệu phản hồi.

Lớp thứ ba có thể cần fake, integration test hoặc health check; không nên cố “sửa binding” để che sự cố runtime.

## 2. Quy trình chuẩn: từ yêu cầu phân giải đến resource shutdown

Giả sử HTTP request cần một `CheckoutHandler`. Graph dự định:

```text
                  Composition root
                         │
             register / chọn factory
                         │
                         ▼
  RequestScope(REQ-1).resolve(CheckoutHandler)
                         │
                         ▼
           Binding: CheckoutHandler
                  scope=REQUEST
                         │
              ┌──────────┴─────────┐
              ▼                    ▼
     CheckoutService         RequestLedger
       scope=APP             scope=REQUEST
       /       \                  │
      ▼         ▼                 ▼
   Catalog   PricePolicy       AuditClient
   scope=APP scope=APP         scope=APP
```

Các bước cần kiểm tra theo đúng thứ tự:

1. **Yêu cầu:** thành phần nào gọi `resolve(CheckoutHandler.class)`? Có một request scope hợp lệ không?

2. **Đăng ký:** container hoặc composition root biết cách tạo `CheckoutHandler` không? Binding của nó có thuộc môi trường hiện hành không?

3. **Lựa chọn:** có nhiều implementation, qualifier, name hoặc key không? Quy tắc ưu tiên có tường minh không?

4. **Đồ thị:** từ constructor/factory của handler, những collaborator nào tiếp tục được yêu cầu? Đường nào thiếu binding hoặc tạo vòng?

5. **Scope/cache:** mỗi dependency là application-wide, request-scoped hay transient? Phân giải lần hai có được dùng lại instance đúng phạm vi không?

6. **Khởi tạo:** factory/constructor có ném lỗi, trả null, gọi network hoặc thực hiện tác dụng phụ không?

7. **Vòng đời:** request kết thúc thì resource nào đóng? Khi ứng dụng dừng, consumer nào phải ngừng trước client/pool dùng chung?

Sơ đồ chẩn đoán tổng quát:

```text
REQUEST: resolve(T)
        │
        ▼
Có binding cho T? ─── không ──► MISSING_BINDING
        │ có
        ▼
Chọn đúng key/qualifier? ─────► AMBIGUOUS / WRONG_BINDING
        │
        ▼
Scope hiện tại hợp lệ? ── không ► MISSING_SCOPE
        │
        ▼
Dependency sống lâu có giữ
request dependency? ─── có ───► CAPTIVE_DEPENDENCY
        │
        ▼
T có đang nằm trên đường xây? ─► CYCLE
        │
        ▼
Có instance cached hợp lệ?
       / \
      có  không
      │     │
      ▼     ▼
    REUSE  resolve dependencies → CREATE
      │     │
      └──┬──┘
         ▼
     Dùng đối tượng
         │
         ▼
  Stop/drain → close scope → close app resources
```

Các nhãn lỗi là **mã phân loại trong bài thực hành**, không phải mã lỗi tiêu chuẩn dùng chung của mọi DI container.

## 3. Thu thập chứng cứ trước khi thay đổi graph

Khi gặp lỗi DI, nên ghi lại một bộ dữ liệu tối thiểu:

| Chứng cứ | Ví dụ | Vì sao quan trọng |
|---|---|---|
| **Resolution target** | `CheckoutHandler` | Cho biết yêu cầu bắt đầu từ đâu |
| **Entry point** | HTTP controller, worker, CLI startup | Biết ranh giới mở scope |
| **Binding/key** | `AuditClient → RealAuditClient` | Xác định implementation thực tế |
| **Qualifier/profile** | `@Qualifier("primary")`, `prod` | Phân biệt nhiều candidate |
| **Dependency path** | `Handler → Ledger → AuditClient` | Chỉ ra nơi thiếu/sai binding |
| **Scope của từng node** | APP / REQUEST / TRANSIENT | Phát hiện lifetime mismatch |
| **Instance identity** | Cùng hay khác tham chiếu giữa hai request | Xác nhận caching và chia sẻ |
| **Thời điểm lỗi** | Compile, startup, first resolve, request, shutdown | Khoanh vùng cơ chế lỗi |
| **Ownership** | Root sở hữu pool, request sở hữu session | Khoanh vùng lỗi đóng/leak |
| **Điều kiện runtime** | Config, feature flag, tenant, phiên bản deploy | Giải thích graph khác giữa môi trường |

Một dependency path tốt hơn thông báo chung chung “không tạo được handler”:

```text
MISSING_BINDING
  target : CheckoutHandler
  path   : CheckoutHandler
           → RequestLedger
           → AuditClient
  missing: AuditClient
  scope  : REQ-1
```

Với **DI thủ công**, đường dẫn thường thấy ở các lời gọi `new` và constructor trong composition root. Với **container**, đường dẫn có thể nằm trong exception cause chain, debug log, graph report hoặc generated source. Nếu container chưa cung cấp đường dẫn, có thể bổ sung test composition hoặc diagnostics ở ranh giới ứng dụng thay vì đưa logging chi tiết vào mọi business service.

**Tránh ghi secret vào log.** Trường dùng để chẩn đoán nên là tên type, key, lifetime, mã correlation và phiên bản cấu hình; không ghi password, token, toàn bộ request DTO hay dữ liệu nhạy cảm chỉ để tìm binding.

## 4. Đọc đúng registration và quy tắc chọn implementation

Một interface có thể có nhiều implementation:

```java
interface AuditClient {
    void append(String event);
}

final class LocalAuditClient implements AuditClient { /* ... */ }
final class RemoteAuditClient implements AuditClient { /* ... */ }
```

Nếu `RequestLedger` cần `AuditClient`, hệ thống phải xác định **implementation nào đang được cấp**. Trong Java thuần:

```java
AuditClient audit = new RemoteAuditClient(settings);
RequestLedger ledger = new RequestLedger(audit);
```

Trong container, việc chọn có thể dựa vào qualifier, name, type key, profile hoặc factory. Không có một quy tắc “cứ có hai implementation thì container chọn lớp mới nhất” áp dụng cho mọi framework. Một số container báo ambiguous binding, một số dùng default/primary/registration precedence, một số yêu cầu lựa chọn rõ ràng.

Khi chẩn đoán, hãy đặt câu hỏi theo thứ tự:

1. **Registration có tồn tại không?** Có thực sự được tải trong process và profile đang chạy?
2. **Key có khớp không?** `Catalog` khác `Catalog<Product>` nếu container xét generic type; qualifier `local` khác `remote`.
3. **Có nhiều candidate không?** Nếu có, cơ chế chọn nào được cấu hình?
4. **Registration có bị override không?** Test module, profile, plugin hoặc module khác có thay binding không?
5. **Factory trả implementation nào?** Factory có đọc biến môi trường hoặc key theo tenant không?
6. **Lựa chọn được cố định lúc nào?** Startup, request hay theo mỗi lần gọi?

Nếu vấn đề là missing binding, chỉ thêm binding đúng có thể đủ. Nếu lựa chọn sai, cần sửa **chính sách selection**. Nếu scope sai, đổi qualifier không giải quyết việc resource bị giữ lâu.

## 5. Object graph: lần theo đường constructor thay vì đoán theo tên class

Một node trong graph đại diện cho **một dependency cần giải quyết**, còn cạnh `A → B` có nghĩa A phụ thuộc vào B:

```text
CheckoutHandler → CheckoutService → Catalog
                 │                  └→ PricePolicy
                 └→ RequestLedger → AuditClient
```

Nếu `AuditClient` chưa được bind, lỗi phát sinh từ một node sâu trong graph. Chỉ đọc constructor của `CheckoutHandler` có thể chưa thấy node đó.

Khi nghi có chu trình:

```text
ServiceA → ServiceB → ServiceC
   ▲                    │
   └────────────────────┘
```

Cần xác định **đường phụ thuộc đang được xây**, không chỉ thấy các class có tham chiếu tới nhau ở runtime. Constructor cycle thường khiến không thể tạo bất kỳ instance hoàn chỉnh nào, trừ khi framework có cơ chế lazy/proxy/provider và semantics tương ứng.

Inject `Provider<ServiceB>` có thể trì hoãn một cạnh nhưng không tự sửa mô hình sai. Nếu A và B thực sự cần nhau để khởi tạo, vẫn phải phân chia lại trách nhiệm, tách một collaborator thứ ba hoặc thay cách giao tiếp giữa chúng.

**Phân biệt constructor cycle với lời gọi method đệ quy:** graph constructor không có chu trình không bảo đảm các lời gọi nghiệp vụ không bao giờ gọi qua lại vô hạn; đó là một loại bug khác.

## 6. Thực hành Java 17: resolver tối giản có trace

Ta xây một container nhỏ để quan sát từng bước:

- `register(key, lifetime, factory)` đăng ký cách tạo type.
- `resolve(key)` tìm dependency cấp ứng dụng.
- `openRequest(id).resolve(key)` tìm dependency trong request scope.
- Mỗi bước tạo hoặc tái sử dụng instance được ghi vào danh sách sự kiện.
- Các lỗi thiếu binding, thiếu scope, dependency request bị singleton giữ và chu trình constructor có **mã và path**.
- Resource application/request implement `Managed` được đóng theo phạm vi do owner quản lý.

Đây là **mô hình học tập**, không phải container production: không có reflection, qualifier, generic key đầy đủ, đăng ký động đa luồng, proxy, async scope propagation hoặc cơ chế vòng đời của framework. Chúng ta dùng factory Java tường minh để tập trung vào **quy trình chẩn đoán**, không vào thuật toán quét class.

### 6.1. Mã nguồn đầy đủ: `DiDiagnosticsDemo.java`

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class DiDiagnosticsDemo {

    enum Lifetime {
        APPLICATION, REQUEST, TRANSIENT
    }

    interface Managed extends AutoCloseable {
        @Override
        void close();
    }

    @FunctionalInterface
    interface Factory<T> {
        T create(Lookup lookup);
    }

    static final class DiFailure extends IllegalStateException {
        private final String code;

        DiFailure(String code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static final class Registration<T> {
        final Lifetime lifetime;
        final Factory<T> factory;

        Registration(Lifetime lifetime, Factory<T> factory) {
            this.lifetime = lifetime;
            this.factory = factory;
        }
    }

    // Mỗi yêu cầu phân giải có path riêng, không dùng global locator.
    static final class ResolutionState {
        final TraceContainer container;
        final RequestScope request;
        final Deque<Class<?>> path = new ArrayDeque<>();
        final Deque<Lifetime> parentLifetimes = new ArrayDeque<>();

        ResolutionState(
                TraceContainer container, RequestScope request) {
            this.container = container;
            this.request = request;
        }
    }

    static final class Lookup {
        private final ResolutionState state;

        Lookup(ResolutionState state) {
            this.state = state;
        }

        <T> T get(Class<T> type) {
            return state.container.resolveInside(type, state);
        }

        String requestId() {
            if (state.request == null) {
                throw new IllegalStateException(
                    "No active request scope");
            }
            return state.request.id;
        }
    }

    static final class TraceContainer implements Managed {
        private final Map<Class<?>, Registration<?>> bindings =
            new LinkedHashMap<>();
        private final Map<Class<?>, Object> applicationCache =
            new HashMap<>();
        private final Deque<Managed> applicationOwned =
            new ArrayDeque<>();
        private final List<String> events;

        private boolean closed;
        private int activeRequests;

        TraceContainer(List<String> events) {
            this.events = Objects.requireNonNull(
                events, "events");
        }

        <T> void register(
                Class<T> type,
                Lifetime lifetime,
                Factory<T> factory) {
            ensureOpen();
            Objects.requireNonNull(type, "type");
            Objects.requireNonNull(lifetime, "lifetime");
            Objects.requireNonNull(factory, "factory");

            if (bindings.containsKey(type)) {
                String message =
                    "DUPLICATE_BINDING: " + type.getSimpleName();
                events.add("ERROR " + message);
                throw new DiFailure(
                    "DUPLICATE_BINDING", message, null);
            }

            bindings.put(type, new Registration<>(
                lifetime, factory));
            events.add("REGISTER " + type.getSimpleName()
                + " scope=" + lifetime);
        }

        <T> T resolve(Class<T> type) {
            ensureOpen();
            return resolveInside(
                type, new ResolutionState(this, null));
        }

        RequestScope openRequest(String requestId) {
            ensureOpen();
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException(
                    "requestId must not be blank");
            }

            activeRequests++;
            events.add("BEGIN " + requestId);
            return new RequestScope(this, requestId);
        }

        private <T> T resolveInside(
                Class<T> type, ResolutionState state) {
            ensureOpen();
            Objects.requireNonNull(type, "type");

            Registration<?> binding = bindings.get(type);
            events.add("LOOKUP " + pathFor(state, type)
                + " -> " + (binding == null
                    ? "ABSENT" : binding.lifetime));

            if (binding == null) {
                throw failure(
                    "MISSING_BINDING", type, state,
                    "No factory registered", null);
            }

            // Phải có request scope trước khi cấp request object.
            if (binding.lifetime == Lifetime.REQUEST
                    && state.request == null) {
                throw failure(
                    "MISSING_REQUEST_SCOPE", type, state,
                    "Request-scoped dependency outside request",
                    null);
            }

            // Một singleton được xây không được bắt giữ
            // dependency chỉ hợp lệ trong một request.
            if (binding.lifetime == Lifetime.REQUEST
                    && state.parentLifetimes.contains(
                        Lifetime.APPLICATION)) {
                throw failure(
                    "CAPTIVE_REQUEST", type, state,
                    "Application object captures request object",
                    null);
            }

            if (state.path.contains(type)) {
                throw failure(
                    "CIRCULAR_DEPENDENCY", type, state,
                    "Constructor path repeats a type", null);
            }

            Map<Class<?>, Object> cache = switch (
                    binding.lifetime) {
                case APPLICATION -> applicationCache;
                case REQUEST -> state.request.instances;
                case TRANSIENT -> null;
            };

            if (cache != null && cache.containsKey(type)) {
                events.add("REUSE " + type.getSimpleName()
                    + " scope=" + binding.lifetime);
                return type.cast(cache.get(type));
            }

            state.path.addLast(type);
            state.parentLifetimes.addLast(binding.lifetime);

            try {
                Object instance =
                    binding.factory.create(new Lookup(state));

                if (instance == null || !type.isInstance(instance)) {
                    throw failure(
                        "INVALID_FACTORY_RESULT", type, state,
                        "Factory returned null or wrong type",
                        null);
                }

                if (cache != null) {
                    cache.put(type, instance);
                }

                // Chỉ owner của APPLICATION/REQUEST quản lý
                // Managed instance. TRANSIENT phải có contract riêng.
                if (instance instanceof Managed managed) {
                    if (binding.lifetime == Lifetime.APPLICATION) {
                        applicationOwned.push(managed);
                    } else if (binding.lifetime == Lifetime.REQUEST) {
                        state.request.owned.push(managed);
                    }
                }

                events.add("CREATE " + type.getSimpleName()
                    + " scope=" + binding.lifetime);
                return type.cast(instance);

            } catch (DiFailure known) {
                throw known;
            } catch (RuntimeException cause) {
                throw failure(
                    "FACTORY_FAILED", type, state,
                    "Factory or constructor failed: "
                        + cause.getClass().getSimpleName(),
                    cause);
            } finally {
                state.path.removeLast();
                state.parentLifetimes.removeLast();
            }
        }

        private String pathFor(
                ResolutionState state, Class<?> requested) {
            StringBuilder path = new StringBuilder();

            for (Class<?> type : state.path) {
                if (path.length() > 0) {
                    path.append(" -> ");
                }
                path.append(type.getSimpleName());
            }

            if (state.path.isEmpty()
                    || state.path.peekLast() != requested) {
                if (path.length() > 0) {
                    path.append(" -> ");
                }
                path.append(requested.getSimpleName());
            }

            return path.toString();
        }

        private DiFailure failure(
                String code,
                Class<?> requested,
                ResolutionState state,
                String detail,
                Throwable cause) {
            String message = code
                + " path=" + pathFor(state, requested)
                + " detail=" + detail;
            events.add("ERROR " + message);
            return new DiFailure(code, message, cause);
        }

        private void ensureOpen() {
            if (closed) {
                throw new IllegalStateException(
                    "Application container is closed");
            }
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            if (activeRequests != 0) {
                throw new IllegalStateException(
                    "Close request scopes before application: "
                        + activeRequests);
            }

            closed = true;
            closeAll(applicationOwned);
            events.add("END APPLICATION");
        }

        private static void closeAll(Deque<Managed> owned) {
            RuntimeException primary = null;

            while (!owned.isEmpty()) {
                Managed resource = owned.pop();

                try {
                    resource.close();
                } catch (RuntimeException failure) {
                    if (primary == null) {
                        primary = failure;
                    } else if (primary != failure) {
                        primary.addSuppressed(failure);
                    }
                }
            }

            if (primary != null) {
                throw primary;
            }
        }
    }

    static final class RequestScope implements Managed {
        private final TraceContainer container;
        private final String id;
        private final Map<Class<?>, Object> instances =
            new HashMap<>();
        private final Deque<Managed> owned =
            new ArrayDeque<>();
        private boolean closed;

        RequestScope(TraceContainer container, String id) {
            this.container = container;
            this.id = id;
        }

        <T> T resolve(Class<T> type) {
            if (closed) {
                throw new IllegalStateException(
                    "Request scope is closed");
            }
            return container.resolveInside(
                type, new ResolutionState(container, this));
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            closed = true;

            try {
                TraceContainer.closeAll(owned);
            } finally {
                container.activeRequests--;
                container.events.add("END " + id);
            }
        }
    }

    record Order(String orderId, String sku, int quantity) {
        Order {
            if (orderId == null || orderId.isBlank()
                    || sku == null || sku.isBlank()
                    || quantity <= 0) {
                throw new IllegalArgumentException(
                    "Invalid order");
            }
        }
    }

    record Receipt(
        String requestId, String orderId, long totalVnd) {}

    record RequestContext(String requestId) {
        RequestContext {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException(
                    "Missing requestId");
            }
        }
    }

    interface Catalog {
        long unitPrice(String sku);
    }

    static final class InMemoryCatalog implements Catalog {
        private final Map<String, Long> prices;

        InMemoryCatalog(Map<String, Long> prices) {
            this.prices = Map.copyOf(prices);
        }

        @Override
        public long unitPrice(String sku) {
            Long price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException(
                    "Unknown SKU: " + sku);
            }
            return price;
        }
    }

    interface PricePolicy {
        long total(long unitPriceVnd, int quantity);
    }

    static final class RegularPricePolicy implements PricePolicy {
        @Override
        public long total(long price, int quantity) {
            return Math.multiplyExact(price, quantity);
        }
    }

    static final class AuditClient implements Managed {
        private final List<String> events;
        private boolean closed;

        AuditClient(List<String> events) {
            this.events = events;
        }

        void ensureOpen() {
            if (closed) {
                throw new IllegalStateException(
                    "AuditClient already closed");
            }
        }

        void append(String entry) {
            ensureOpen();
            events.add("AUDIT " + entry);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                events.add("CLOSE AuditClient");
            }
        }
    }

    static final class RequestLedger implements Managed {
        private final RequestContext context;
        private final AuditClient audit;
        private final List<String> events;
        private boolean closed;

        RequestLedger(
                RequestContext context,
                AuditClient audit,
                List<String> events) {
            this.context = Objects.requireNonNull(context);
            this.audit = Objects.requireNonNull(audit);
            this.events = Objects.requireNonNull(events);
        }

        void record(String orderId, long totalVnd) {
            if (closed) {
                throw new IllegalStateException(
                    "RequestLedger already closed");
            }
            audit.append(context.requestId()
                + ":" + orderId + ":" + totalVnd);
        }

        @Override
        public void close() {
            if (!closed) {
                // Dependency cấp ứng dụng còn sống khi scope đóng.
                audit.ensureOpen();
                closed = true;
                events.add(
                    "CLOSE RequestLedger " + context.requestId());
            }
        }
    }

    static final class CheckoutService {
        private final Catalog catalog;
        private final PricePolicy pricing;

        CheckoutService(Catalog catalog, PricePolicy pricing) {
            this.catalog = Objects.requireNonNull(catalog);
            this.pricing = Objects.requireNonNull(pricing);
        }

        long total(Order order) {
            return pricing.total(
                catalog.unitPrice(order.sku()),
                order.quantity());
        }
    }

    static final class CheckoutHandler {
        private final CheckoutService checkout;
        private final RequestContext context;
        private final RequestLedger ledger;

        CheckoutHandler(
                CheckoutService checkout,
                RequestContext context,
                RequestLedger ledger) {
            this.checkout = Objects.requireNonNull(checkout);
            this.context = Objects.requireNonNull(context);
            this.ledger = Objects.requireNonNull(ledger);
        }

        Receipt handle(Order order) {
            Objects.requireNonNull(order);
            long total = checkout.total(order);
            ledger.record(order.orderId(), total);
            return new Receipt(
                context.requestId(), order.orderId(), total);
        }
    }

    // Composition root: đăng ký đúng contract và scope.
    static TraceContainer configured(List<String> events) {
        TraceContainer app = new TraceContainer(events);

        app.register(
            Catalog.class, Lifetime.APPLICATION,
            r -> new InMemoryCatalog(
                Map.of("BOOK", 60_000L)));

        app.register(
            PricePolicy.class, Lifetime.APPLICATION,
            r -> new RegularPricePolicy());

        app.register(
            AuditClient.class, Lifetime.APPLICATION,
            r -> new AuditClient(events));

        app.register(
            CheckoutService.class, Lifetime.APPLICATION,
            r -> new CheckoutService(
                r.get(Catalog.class),
                r.get(PricePolicy.class)));

        app.register(
            RequestContext.class, Lifetime.REQUEST,
            r -> new RequestContext(r.requestId()));

        app.register(
            RequestLedger.class, Lifetime.REQUEST,
            r -> new RequestLedger(
                r.get(RequestContext.class),
                r.get(AuditClient.class),
                events));

        app.register(
            CheckoutHandler.class, Lifetime.REQUEST,
            r -> new CheckoutHandler(
                r.get(CheckoutService.class),
                r.get(RequestContext.class),
                r.get(RequestLedger.class)));

        return app;
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        try (TraceContainer app = configured(events)) {
            try (RequestScope request =
                     app.openRequest("REQ-1")) {
                Receipt receipt = request.resolve(
                    CheckoutHandler.class).handle(
                    new Order("ORDER-1", "BOOK", 2));

                System.out.println(
                    "REQ-1 total=" + receipt.totalVnd());
            }

            try (RequestScope request =
                     app.openRequest("REQ-2")) {
                Receipt receipt = request.resolve(
                    CheckoutHandler.class).handle(
                    new Order("ORDER-2", "BOOK", 1));

                System.out.println(
                    "REQ-2 total=" + receipt.totalVnd());
            }
        }

        // In các mốc chính; log LOOKUP vẫn có trong events.
        for (String event : events) {
            if (event.startsWith("CREATE ")
                    || event.startsWith("REUSE ")
                    || event.startsWith("CLOSE ")) {
                System.out.println(event);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac DiDiagnosticsDemo.java
java DiDiagnosticsDemo
```

Kết quả dự kiến (dòng sự kiện theo thứ tự thực thi):

```text
REQ-1 total=120000
REQ-2 total=60000
CREATE Catalog scope=APPLICATION
CREATE PricePolicy scope=APPLICATION
CREATE CheckoutService scope=APPLICATION
CREATE RequestContext scope=REQUEST
REUSE RequestContext scope=REQUEST
CREATE AuditClient scope=APPLICATION
CREATE RequestLedger scope=REQUEST
CREATE CheckoutHandler scope=REQUEST
CLOSE RequestLedger REQ-1
REUSE CheckoutService scope=APPLICATION
CREATE RequestContext scope=REQUEST
REUSE RequestContext scope=REQUEST
REUSE AuditClient scope=APPLICATION
CREATE RequestLedger scope=REQUEST
CREATE CheckoutHandler scope=REQUEST
CLOSE RequestLedger REQ-2
CLOSE AuditClient
```

Đường `LOOKUP` cũng được lưu trong `events` nhưng không in hết ra màn hình để tránh quá dài. Nếu cần chẩn đoán sâu, thay điều kiện in ở cuối `main` bằng `events.forEach(System.out::println)` để thấy cả registration và dependency path.

### 6.2. Đọc log từ request đầu tiên

Một phần trace `LOOKUP` của request đầu có thể trông như:

```text
LOOKUP CheckoutHandler -> REQUEST
LOOKUP CheckoutHandler -> CheckoutService -> APPLICATION
LOOKUP CheckoutHandler -> CheckoutService -> Catalog -> APPLICATION
LOOKUP CheckoutHandler -> CheckoutService -> PricePolicy -> APPLICATION
LOOKUP CheckoutHandler -> RequestContext -> REQUEST
LOOKUP CheckoutHandler -> RequestLedger -> REQUEST
LOOKUP CheckoutHandler -> RequestLedger -> RequestContext -> REQUEST
LOOKUP CheckoutHandler -> RequestLedger -> AuditClient -> APPLICATION
```

Cách đọc:

1. `CheckoutHandler` được yêu cầu từ `RequestScope`.
2. Registration của handler yêu cầu `CheckoutService`, `RequestContext` và `RequestLedger`.
3. `CheckoutService` cần `Catalog` và `PricePolicy`. Cả ba được tạo ở application scope.
4. `RequestContext` được tạo trong request scope; khi `RequestLedger` yêu cầu lại, resolver dùng instance đã cache.
5. `RequestLedger` dùng một `AuditClient` application-wide. Nó ghi audit nhưng **không đóng client**.
6. Khi request kết thúc, chỉ `RequestLedger` được đóng. `AuditClient` vẫn sống để request tiếp theo dùng.
7. Khi mọi request đã đóng, application owner mới đóng `AuditClient`.

Một **binding key** không nhất thiết trùng concrete class: trace hiển thị `Catalog`, còn object thật là `InMemoryCatalog` vì factory trả implementation đó. Production diagnostics nên ghi cả key và implementation nếu cần truy vết.

### 6.3. Các giới hạn quan trọng

Resolver này không dùng reflection, không có qualifier và chỉ hỗ trợ **một registration cho mỗi `Class<?>`**. `APPLICATION`/`REQUEST` dùng cache; `TRANSIENT` tạo mới mỗi lần resolve. Nhưng chương trình **không tự dispose transient `Managed`**: nếu muốn tạo disposable transient, cần bổ sung hợp đồng ownership riêng và test.

Ví dụ chạy **tuần tự, một thread**. `ArrayList`, `HashMap` và các biến `boolean` không phải cơ chế quản lý scope an toàn khi nhiều request đồng thời. Container thật cần đồng bộ, request-context propagation, shutdown coordination và kiểm soát các tác vụ bất đồng bộ.

Các check scope trong `resolveInside` minh họa **một quy tắc chẩn đoán có chủ ý**, không phải bảo đảm mọi container đều tự phát hiện captive dependency. Một số container có proxy/provider và validation với ngữ nghĩa khác. Không nên dùng resolver tối giản này làm dependency framework sản xuất.

## 7. Thực hành chủ động tạo các lỗi DI và kiểm tra path

Một quá trình chẩn đoán tốt phải tái hiện được lỗi có kiểm soát. Ta sẽ viết chương trình thứ hai, đăng ký graph cố ý sai và kiểm tra **mã lỗi** cùng **đường dẫn** mà resolver báo.

Các trường hợp:

| Mã trong demo | Lỗi cố ý | Dấu hiệu quan trọng |
|---|---|---|
| `MISSING_BINDING` | Factory yêu cầu type không đăng ký | Path chỉ tới type bị thiếu |
| `DUPLICATE_BINDING` | Đăng ký lại cùng key | Lỗi ngay lúc register, không ghi đè ngầm |
| `CIRCULAR_DEPENDENCY` | A → B → A | Path cho thấy vòng constructor |
| `MISSING_REQUEST_SCOPE` | Resolve request dependency tại app root | Không có request boundary hợp lệ |
| `CAPTIVE_REQUEST` | App-scoped factory giữ request dependency | Sai lifetime của parent và child |
| `FACTORY_FAILED` | Factory/constructor ném exception | Biết type đang tạo và giữ cause |
| **Lifecycle assertion** | Đóng request trước app | Resource đúng owner, đúng thứ tự |

### 7.1. Mã nguồn đầy đủ: `DiDiagnosticsCheck.java`

Lưu cùng thư mục với `DiDiagnosticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class DiDiagnosticsCheck {

    static final class UnknownDependency {}

    static final class RequiresUnknown {
        RequiresUnknown(UnknownDependency dependency) {}
    }

    static final class CycleA {
        CycleA(CycleB dependency) {}
    }

    static final class CycleB {
        CycleB(CycleA dependency) {}
    }

    static final class CaptiveSingleton {
        CaptiveSingleton(
                DiDiagnosticsDemo.RequestLedger ledger) {}
    }

    static final class ExplodingFactoryTarget {}

    private static void expectFailure(
            Runnable operation, String code, String pathPart) {
        try {
            operation.run();
        } catch (DiDiagnosticsDemo.DiFailure failure) {
            if (!code.equals(failure.code())
                    || !failure.getMessage().contains(pathPart)) {
                throw new AssertionError(
                    "Expected " + code + " and " + pathPart,
                    failure);
            }
            return;
        }
        throw new AssertionError("Expected error " + code);
    }

    public static void main(String[] args) {
        // 1. Đường thành công: app instance dùng chung,
        // request resource không dùng chung giữa hai scope.
        List<String> normalEvents = new ArrayList<>();
        DiDiagnosticsDemo.CheckoutService sharedService;
        DiDiagnosticsDemo.RequestLedger firstLedger;

        try (var app = DiDiagnosticsDemo.configured(normalEvents)) {
            try (var first = app.openRequest("REQ-A")) {
                var firstHandler = first.resolve(
                    DiDiagnosticsDemo.CheckoutHandler.class);
                var again = first.resolve(
                    DiDiagnosticsDemo.CheckoutHandler.class);

                if (firstHandler != again) {
                    throw new AssertionError(
                        "Request handler was not cached");
                }

                sharedService = first.resolve(
                    DiDiagnosticsDemo.CheckoutService.class);
                firstLedger = first.resolve(
                    DiDiagnosticsDemo.RequestLedger.class);

                var receipt = firstHandler.handle(
                    new DiDiagnosticsDemo.Order(
                        "ORDER-A", "BOOK", 2));

                if (receipt.totalVnd() != 120_000L) {
                    throw new AssertionError("Wrong first total");
                }
            }

            try (var second = app.openRequest("REQ-B")) {
                var secondService = second.resolve(
                    DiDiagnosticsDemo.CheckoutService.class);
                var secondLedger = second.resolve(
                    DiDiagnosticsDemo.RequestLedger.class);

                if (secondService != sharedService
                        || secondLedger == firstLedger) {
                    throw new AssertionError(
                        "Wrong lifetime sharing");
                }

                second.resolve(
                    DiDiagnosticsDemo.CheckoutHandler.class)
                    .handle(new DiDiagnosticsDemo.Order(
                        "ORDER-B", "BOOK", 1));
            }
        }

        int requestClose = normalEvents.indexOf(
            "CLOSE RequestLedger REQ-B");
        int appClose = normalEvents.indexOf(
            "CLOSE AuditClient");

        if (requestClose < 0 || appClose <= requestClose) {
            throw new AssertionError(
                "Application resource closed too early");
        }

        // 2. Thiếu binding: kiểm tra đường phụ thuộc.
        try (var app = new DiDiagnosticsDemo.TraceContainer(
                new ArrayList<>())) {
            app.register(
                RequiresUnknown.class,
                DiDiagnosticsDemo.Lifetime.APPLICATION,
                r -> new RequiresUnknown(
                    r.get(UnknownDependency.class)));

            expectFailure(
                () -> app.resolve(RequiresUnknown.class),
                "MISSING_BINDING",
                "RequiresUnknown -> UnknownDependency");
        }

        // 3. Hai constructor phụ thuộc vòng.
        try (var app = new DiDiagnosticsDemo.TraceContainer(
                new ArrayList<>())) {
            app.register(
                CycleA.class,
                DiDiagnosticsDemo.Lifetime.APPLICATION,
                r -> new CycleA(r.get(CycleB.class)));

            app.register(
                CycleB.class,
                DiDiagnosticsDemo.Lifetime.APPLICATION,
                r -> new CycleB(r.get(CycleA.class)));

            expectFailure(
                () -> app.resolve(CycleA.class),
                "CIRCULAR_DEPENDENCY",
                "CycleA -> CycleB -> CycleA");
        }

        // 4. Request dependency không được resolve ở app root.
        try (var app = DiDiagnosticsDemo.configured(
                new ArrayList<>())) {
            expectFailure(
                () -> app.resolve(
                    DiDiagnosticsDemo.RequestLedger.class),
                "MISSING_REQUEST_SCOPE", "RequestLedger");
        }

        // 5. Application singleton không bắt giữ request ledger.
        try (var app = DiDiagnosticsDemo.configured(
                new ArrayList<>())) {
            app.register(
                CaptiveSingleton.class,
                DiDiagnosticsDemo.Lifetime.APPLICATION,
                r -> new CaptiveSingleton(
                    r.get(DiDiagnosticsDemo.RequestLedger.class)));

            try (var request = app.openRequest("REQ-CAP")) {
                expectFailure(
                    () -> request.resolve(CaptiveSingleton.class),
                    "CAPTIVE_REQUEST",
                    "CaptiveSingleton -> RequestLedger");
            }
        }

        // 6. Đăng ký trùng key phải bị từ chối.
        try (var app = DiDiagnosticsDemo.configured(
                new ArrayList<>())) {
            expectFailure(
                () -> app.register(
                    DiDiagnosticsDemo.Catalog.class,
                    DiDiagnosticsDemo.Lifetime.APPLICATION,
                    r -> new DiDiagnosticsDemo.InMemoryCatalog(
                        Map.of("BOOK", 1L))),
                "DUPLICATE_BINDING", "Catalog");
        }

        // 7. Factory lỗi: giữ path và mã lỗi.
        try (var app = new DiDiagnosticsDemo.TraceContainer(
                new ArrayList<>())) {
            app.register(
                ExplodingFactoryTarget.class,
                DiDiagnosticsDemo.Lifetime.APPLICATION,
                r -> {
                    throw new IllegalArgumentException(
                        "bad configuration");
                });

            expectFailure(
                () -> app.resolve(ExplodingFactoryTarget.class),
                "FACTORY_FAILED", "ExplodingFactoryTarget");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac DiDiagnosticsDemo.java DiDiagnosticsCheck.java
java DiDiagnosticsCheck
```

Kết quả dự kiến:

```text
PASS
```

Kiểm thử này dùng **Java thuần**, không có DI container bên ngoài, mock framework hay kết nối mạng. Các lỗi được tạo một cách xác định; nếu mã lỗi hoặc path khác mong đợi, test báo lỗi thay vì che thông tin chẩn đoán.

### 7.2. Đọc ba lỗi điển hình

**Thiếu registration:**

```text
MISSING_BINDING path=RequiresUnknown -> UnknownDependency
detail=No factory registered
```

Không nên sửa bằng cách cho `RequiresUnknown` tự `new UnknownDependency()`. Đó là đưa quyết định composition vào consumer. Hãy đăng ký một factory/implementation phù hợp tại root và test đường phân giải.

**Vòng constructor:**

```text
CIRCULAR_DEPENDENCY path=CycleA -> CycleB -> CycleA
detail=Constructor path repeats a type
```

Đường lặp cho thấy A và B cần nhau **trước khi có instance hoàn chỉnh**. Tìm ranh giới trách nhiệm cần tách; tránh dùng proxy hoặc lazy chỉ để làm mất thông báo nếu vòng thiết kế vẫn bất hợp lý.

**Giữ nhầm request dependency:**

```text
CAPTIVE_REQUEST path=CaptiveSingleton -> RequestLedger
detail=Application object captures request object
```

Nếu một application-scoped instance nắm trực tiếp `RequestLedger` đã được tạo trong request, nó có thể giữ state request sau khi request kết thúc. Giải pháp thường là thay lifetime của consumer, truyền dữ liệu theo method, hoặc inject factory/provider có hợp đồng mở dependency trong scope hợp lệ. Không sửa bằng cách đổi `RequestLedger` thành singleton nếu nó giữ transaction hoặc dữ liệu request.

## 8. Cách đọc cache hit và identity theo scope

Một lần `resolve(X)` không nhất thiết luôn gọi constructor. Cần phân biệt:

| Lifetime | Trong demo | Điều cần xác minh |
|---|---|---|
| `APPLICATION` | Có một instance cho mỗi key trong `TraceContainer` | Hai request cùng root có dùng lại đúng instance không? |
| `REQUEST` | Có một instance cho mỗi key trong một `RequestScope` | Trong request giống nhau, khác request là khác instance không? |
| `TRANSIENT` | Factory được gọi mỗi lần resolve, không cache | Có thực sự resolve lại không, hay một singleton giữ instance đã được cấp? |

Ví dụ trace:

```text
CREATE CheckoutService scope=APPLICATION
REUSE CheckoutService scope=APPLICATION

CREATE RequestLedger scope=REQUEST
CLOSE RequestLedger REQ-1
CREATE RequestLedger scope=REQUEST
CLOSE RequestLedger REQ-2
```

Nếu cùng một request mà `RequestLedger` được tạo hai lần không có chủ ý, hãy kiểm tra liệu có **hai request scope khác nhau** đang bị mở trong cùng đường xử lý. Nếu hai request khác nhau dùng cùng `RequestLedger`, cần kiểm tra có object nào giữ instance bên ngoài scope hay không.

Không nên kết luận phạm vi chỉ bằng tên annotation. Một container có thể có nhiều context hoặc nested scope. Singleton thường là **một instance trong phạm vi container/registration**, không phải duy nhất toàn JVM.

**Transient không có nghĩa mỗi lần gọi method lại có object mới.** Nếu `ReportService` singleton nhận một transient trực tiếp trong constructor, nó có thể giữ object đó suốt đời service. Khi muốn mỗi thao tác có instance mới, hãy inject factory/provider và gọi ở ranh giới thích hợp.

## 9. Truy vết vòng đời và quyền đóng tài nguyên

Sau khi graph đã lắp thành công, chẩn đoán DI chưa kết thúc. Resource có thể bị đóng sai thứ tự, không được đóng hoặc bị đóng bởi một consumer không sở hữu nó.

Trong demo:

```text
RequestScope REQ-1
   └── RequestLedger  ──uses──► AuditClient
          close lúc                    │
          request kết thúc             │
                                      ▼
                          Application owner
                          close khi app shutdown
```

Thứ tự chính xác:

```text
Tạo AuditClient APPLICATION
  → Tạo RequestLedger REQUEST
  → Xử lý request
  → Đóng RequestLedger
  → Những request khác vẫn có thể dùng AuditClient
  → Đóng AuditClient khi app kết thúc
```

Nếu `RequestLedger.close()` còn cần `AuditClient` sống để flush, việc đóng client trước ledger sẽ gây lỗi. Trong hệ thống thật, cần dừng nhận công việc mới, đợi in-flight work hoàn thành hoặc hủy theo chính sách, đóng resource theo scope rồi mới đóng pool/client nền.

### Phân biệt ba sự cố lifecycle

| Sự cố | Dấu hiệu | Kiểm tra |
|---|---|---|
| **Đóng sớm** | “client already closed” ở request đang chạy | Resource có bị đóng bởi consumer thay vì owner? Shutdown có drain không? |
| **Không đóng** | Tăng connection/thread/file descriptor sau nhiều request | Request scope có `close()` trong `finally`/`try-with-resources` không? |
| **Đóng lặp** | Lỗi khi nhiều component cùng shutdown | Có nhiều owner cho cùng một instance không? Contract `close()` có idempotent không? |

`try-with-resources` hữu ích vì đóng resource khi thoát scope kể cả khi method ném lỗi. Tuy nhiên, **không được suy ra mọi resource đều được phép đóng bởi nơi đang sử dụng nó**. Nếu caller chỉ mượn pool, caller không nên gọi `pool.close()` sau một request.

Khi startup thất bại giữa chừng, composition root phải cleanup những resource đã tạo thành công mà chưa bàn giao; factory phải tự dọn phần cấp phát dở **trước khi trả instance**. Nếu cleanup ném exception, cần giữ lỗi chính và đưa lỗi cleanup vào suppressed exceptions theo hợp đồng Java, thay vì làm mất nguyên nhân ban đầu.

## 10. Đừng nhầm lỗi constructor với lỗi sẵn sàng của hạ tầng

Một dependency có thể hợp lệ về DI nhưng chưa sẵn sàng thực hiện I/O:

```text
Registration OK
     │
     ▼
Object graph OK
     │
     ▼
Constructor hoàn tất
     │
     ▼
Readiness probe? ── dependency chưa sẵn sàng
     │
     ▼
Chưa mở nhận việc / degraded mode theo policy
```

Ví dụ `DataSource` đã được inject vào repository nhưng database không kết nối được. Không có thiếu binding hay cycle; lỗi nằm ở readiness/transport. Đổi `@Qualifier` không chữa được database outage.

Một quy trình chẩn đoán nên hỏi:

- **Lỗi xảy ra trước khi constructor trả về hay khi use case gọi dependency?**
- **Constructor có thực hiện network I/O hoặc nạp dữ liệu tốn kém không?** Nếu có, có đang trộn tạo object và readiness không?
- **Đã validate cấu hình cục bộ chưa?** URL, mode, credential presence, key/qualifier.
- **Readiness có kiểm tra đúng dependency bắt buộc để nhận công việc không?**
- **Có phân biệt cấu hình sai cố định với dependency tạm thời unavailable/timeout không?**
- **Khi probe thành công, code xử lý request vẫn có đường phản ứng với sự cố sau đó không?**

**Constructor injection giúp kiểm thử bằng fake**: dùng fake `DataSource` hoặc `RateGateway` để tách lỗi lắp ghép khỏi lỗi network. Với DI container, eager bean initialization và readiness check có thể chạy ở các giai đoạn khác nhau; cần đọc hợp đồng framework cụ thể.

## 11. Truy vết container thực: chuyển khái niệm thành thao tác

Một DI container thông dụng có thể tạo graph bằng runtime reflection, mã sinh trước runtime, factory method hoặc kết hợp nhiều cách. Tên API khác nhau, nhưng chuỗi chẩn đoán giữ nguyên.

| Câu hỏi | Với Java thuần | Với DI container |
|---|---|---|
| Ai yêu cầu dependency? | Tìm lời gọi `new`/`factory.create` hoặc `resolve` ở root | Tìm entry point, bean creation/resolve request, stack trace |
| Binding nằm ở đâu? | Đoạn `register(...)` hoặc câu lệnh chọn implementation | Configuration, qualifier, profile, module registration |
| Node tiếp theo trong graph là gì? | Đọc constructor/factory và các tham số | Dependency graph, injection metadata, error path |
| Vì sao instance được dùng lại? | Theo map cache của application/request | Scope rule và context hiện hành |
| Vì sao lỗi chỉ xuất hiện lần đầu gọi? | Factory lazy hoặc startup không đi qua nhánh đó | Lazy bean/provider/request-specific resolution |
| Ai đóng bean/resource? | Composition root, `try-with-resources` | Container lifecycle, context shutdown, custom owner |
| Lỗi khởi tạo có cleanup không? | Code `try`/`finally` trong root | Hợp đồng khởi động thất bại của framework, test |

Một số container có tính năng validate graph tại build hoặc startup, nhưng không thể suy ra **mọi nhánh phụ thuộc đều đã được kiểm tra**. Binding động theo tenant, profile, plugin hoặc request vẫn có thể lỗi lúc runtime. Code generation/AOT có thể phát hiện một số vấn đề sớm nhưng không chứng minh network, credential hoặc tài nguyên bên ngoài luôn sẵn sàng.

### Cẩn thận với Service Locator

Khi một business service gọi:

```java
// Pseudocode phản ví dụ.
PaymentGateway gateway =
    globalContainer.resolve(PaymentGateway.class);
```

phụ thuộc thật bị ẩn khỏi constructor. Việc chẩn đoán đòi tìm các lần lookup bên trong method, có thể bị thay đổi theo nhánh runtime. Tốt hơn là inject `PaymentGateway` hoặc một `PaymentGatewaySelector` có hợp đồng hẹp từ composition root.

Việc gọi API container **tại composition root** để lấy một dependency rồi cấp nó cho service không đồng nghĩa business service dùng Service Locator. Ranh giới quyết định là **nơi lookup xảy ra** và **consumer có công khai collaborator cần thiết hay không**.

## 12. Sự khác nhau giữa lỗi đăng ký và lỗi điều phối nghiệp vụ

Một service có thể nhận đủ dependencies và vẫn chạy sai thứ tự chiến lược:

```java
List<RateStrategy> ordered = List.of(
    new StandardRate(),  // catch-all ở đầu
    new ExpressRate()
);
```

Nếu `StandardRate.supports(...)` luôn `true`, `ExpressRate` không bao giờ được thử. DI graph **hoàn toàn hợp lệ về type và scope**, nhưng lựa chọn nghiệp vụ sai.

Vì vậy, ở giai đoạn sau khi xác nhận graph đúng, còn phải kiểm tra:

1. **Thứ tự collection injection** có phải quy tắc nghiệp vụ không?
2. **Decorator chain** có đặt logging, retry, validation hoặc transaction đúng lớp ngoài/lớp trong không?
3. **Default/qualifier** có chọn đúng strategy cho từng môi trường không?
4. **Fake test** có chứng minh selected implementation và số lần gọi không?
5. **Tác dụng phụ** có xảy ra một lần hay bị retry/lặp không?

Một lỗi output sai không nhất thiết bắt nguồn từ DI. Resolver chỉ bảo đảm cung cấp một graph theo registration; nó không chứng minh công thức giá, thứ tự pipeline hoặc retry semantics đúng.

## 13. Quy trình xử lý sự cố trên môi trường chạy

Khi nhận một incident liên quan dependency, có thể làm theo runbook sau:

1. **Khoanh thời điểm:** startup, first request, request dưới tải hay shutdown? Ghi phiên bản ứng dụng và cấu hình liên quan.

2. **Xác định target:** type/service đầu tiên được yêu cầu tạo hoặc dùng, cùng request/job ID nếu có.

3. **Lấy dependency path:** đọc chuỗi nguyên nhân trong exception và trace; xác định **node đầu tiên thực sự thất bại**, không chỉ node ngoài cùng.

4. **Kiểm tra registration:** type, qualifier, profile, module, key và factory thực tế. Nếu nhiều binding, xem quy tắc chọn; nếu thiếu, xác định vì sao registration không được tải.

5. **Kiểm tra graph:** thiếu constructor argument, vòng dependency, factory null/lỗi hoặc lệch version/classpath.

6. **Kiểm tra scope:** request hiện tại có hợp lệ không; instance có được tái sử dụng đúng; singleton có giữ request state không?

7. **Kiểm tra lifecycle:** request/transaction có đóng đúng owner; client dùng chung có bị đóng sớm hay không đóng; có task chưa drain khi shutdown không?

8. **Kiểm tra readiness và I/O:** nếu graph đúng, chuyển sang xác minh client/transport/credential/deadline, đừng tiếp tục chỉnh binding để “thử vận may”.

9. **Tái hiện có kiểm soát:** dùng một composition test hoặc fake đưa ra mã lỗi/path hoặc identity mong đợi. Hạn chế lệ thuộc hạ tầng thật cho unit test.

10. **Sửa đúng ranh giới, thêm regression test:** thay registration ở root, sửa scope hoặc refactor dependency cycle; lưu lại trace trước/sau và xác nhận đường lỗi được xử lý.

Ví dụ mẫu báo cáo cho một lỗi:

```text
Incident: CheckoutHandler không khởi động trong profile prod
Resolution target: CheckoutHandler
First failing node: AuditClient
Dependency path: CheckoutHandler -> RequestLedger -> AuditClient
Finding: prod profile không đăng ký AuditClient
Scope: REQUEST -> APPLICATION hợp lệ
Action: đăng ký đúng AuditClient tại composition root
Validation: composition test cho prod profile + startup readiness
Ownership: app root vẫn chịu trách nhiệm đóng AuditClient
```

Không cần in toàn bộ request hoặc secret để chứng minh đường phụ thuộc sai.

## 14. Quan sát có cấu trúc và giới hạn logging

Với ứng dụng lớn, trace cần đủ để điều tra nhưng không làm ngập log:

| Thuộc tính event | Giá trị minh họa |
|---|---|
| `phase` | `lookup`, `select`, `create`, `reuse`, `dispose` |
| `key` | `AuditClient` |
| `implementation` | `RemoteAuditClient` |
| `scope` | `application`, `request` |
| `path` | `Handler/RequestLedger/AuditClient` |
| `correlationId` | `REQ-1` |
| `outcome` | `ok`, `missing_binding`, `scope_error` |
| `durationMs` | Chỉ ghi khi có đo thực tế |
| `configVersion` | Phiên bản cấu hình không chứa secret |

Trong production, không nhất thiết log **mọi** resolution thành công. Có thể bật debug theo môi trường, lấy mẫu, tổng hợp metric số lần tạo/reuse/dispose và lưu error path khi thất bại. Nếu một singleton được dùng hàng triệu lần, log mỗi cache hit có thể trở thành chi phí đáng kể.

**Instance identity** có thể hữu ích để phát hiện chia sẻ sai, nhưng không nên phụ thuộc vào `hashCode()` như định danh toàn cục: các object có thể override hash code, có thể trùng và không bảo đảm ổn định trên các process. Nếu cần trace chính xác, tạo ID chẩn đoán theo owner/scope và giới hạn vòng đời ID.

Quan sát lifecycle nên ghi được **bao nhiêu resource đang mở**, không chỉ số lần gọi `close()`. Một resource có thể đóng thành công nhưng còn callback đang hoạt động, hoặc `close()` chỉ trả connection về pool. Phải hiểu hợp đồng thư viện khi chọn metric.

## 15. Những lỗi chẩn đoán dễ gặp

| Phản ứng vội | Vì sao sai | Cách xử lý tốt hơn |
|---|---|---|
| Thấy missing binding thì thêm `new` trong service | Biến consumer thành nơi tạo collaborator | Sửa registration ở composition root |
| Có hai implementation thì xóa một bất kỳ | Có thể xóa lựa chọn hợp lệ ở môi trường khác | Kiểm tra qualifier, profile và selection rule |
| Có cycle thì thêm lazy/provider ở khắp nơi | Che chu trình trách nhiệm, có thể lỗi muộn | Vẽ dependency path và tách vòng nếu cần |
| Có scope mismatch thì đổi tất cả thành singleton | Rò request state, transaction hoặc dữ liệu tenant | Sửa lifetime/parameter/factory ở đúng ranh giới |
| Nhìn một lần resolve thành công rồi kết luận mọi nhánh ổn | Lazy/dynamic registration có thể chưa được dùng | Test composition cho cấu hình và entry point quan trọng |
| Lấy timeout làm bằng chứng thiếu binding | Timeout là execution/transport failure | Kiểm tra readiness, client và dependency runtime |
| Chỉ kiểm tra được giá trị trả về | Không thấy resource leak hoặc sai thứ tự chọn | Test interaction, instance identity và close |
| Dùng `System.identityHashCode` làm ID toàn hệ thống | Không phải định danh duy nhất bền vững | Dùng ID theo scope/correlation rõ |
| Log toàn bộ cấu hình và request để tìm graph | Có thể lộ secret hoặc dữ liệu nhạy cảm | Log type/key/path và thông tin tối thiểu |
| Cho rằng DI container luôn đóng mọi transient | Semantics khác nhau và có thể không có owner | Đọc hợp đồng disposal và test |
| Đóng application khi còn request mở | Consumer có thể còn dùng client | Stop/drain request trước khi dispose root |
| Nhầm factory constructor failure với lỗi nghiệp vụ | Sửa sai tầng; dễ che bug thực | Xác định thời điểm lỗi và cause chain |

## 16. Bài tập thực hành

### Bài tập 1 — Thiếu binding sâu trong graph

Từ `DiDiagnosticsDemo.configured(...)`, bỏ registration của `AuditClient` trong **bản sao thực hành**. Resolve `CheckoutHandler` trong request scope và ghi lại đường `LOOKUP` dẫn tới lỗi.

**Tiêu chí đạt:** báo `MISSING_BINDING` với path `CheckoutHandler -> RequestLedger -> AuditClient`; không sửa `RequestLedger` để tự tạo client.

### Bài tập 2 — Sai scope trong singleton

Tạo `ReportService` application-scoped nhưng constructor nhận `RequestContext`. Resolve trong request, quan sát `CAPTIVE_REQUEST`. Chọn một trong ba phương án sửa và giải thích: `ReportService` theo request, truyền context qua method, hoặc inject provider có scope hợp lệ.

**Tiêu chí đạt:** request A và B không chia sẻ instance chứa state request; không đổi `RequestContext` thành singleton chỉ để vượt validation.

### Bài tập 3 — Chu trình constructor và trách nhiệm

Tạo `ServiceA(ServiceB)` và `ServiceB(ServiceA)`. Xác nhận trace vòng, sau đó tách một collaborator độc lập như `Notifier` để loại bỏ vòng không cần thiết.

**Tiêu chí đạt:** đường xây mới không có type lặp; test không chỉ tắt cycle detection.

### Bài tập 4 — Thay binding bằng fake

Đăng ký một `Catalog` fake trả giá 123 VND, giữ `CheckoutService` và `CheckoutHandler` không đổi. Kiểm tra tổng của hai sản phẩm là 246 VND.

**Tiêu chí đạt:** quyết định implementation chỉ nằm ở registration/composition; use case không dùng `GlobalContainer.get(...)`.

### Bài tập 5 — Kiểm tra tài nguyên sau shutdown

Dùng `events` xác minh `CLOSE RequestLedger REQ-1` xuất hiện trước `CLOSE AuditClient`. Thử gọi `app.close()` khi một scope còn mở, xác nhận coordinator từ chối; đóng scope rồi đóng app.

**Tiêu chí đạt:** không để request dùng client đã đóng; báo lỗi có nguyên nhân khi thứ tự shutdown sai.

### Bài tập 6 — Thời điểm validate registration

Bổ sung một registration cho service không được `resolve` trong `main`, nhưng factory của nó yêu cầu dependency chưa đăng ký. Quan sát chương trình vẫn có thể tạo những graph khác. Thảo luận vì sao **đăng ký thành công không đồng nghĩa toàn bộ graph đã được kiểm tra**.

**Tiêu chí đạt:** nêu rõ khác biệt giữa registry validation, eager graph validation, lazy resolution và readiness.

### Bài tập 7 — Phát hiện registration trùng

Thêm một binding thứ hai cho `Catalog.class`, xác nhận `DUPLICATE_BINDING`. Sau đó thiết kế một cách chọn nhiều implementation dựa trên key như `CatalogMode` hoặc qualifier thay vì ghi đè âm thầm.

### Bài tập 8 — Tạo báo cáo chẩn đoán

Viết một báo cáo ngắn cho lỗi `RequestLedger` bị giữ trong singleton với các trường: target, path, registration, scope, symptom, root cause, fix và regression test. Không in toàn bộ dữ liệu của request vào log.

### Bài tập 9 — Phân biệt sự cố hạ tầng với sự cố DI

Cho fake `AuditClient` ném một exception biểu diễn network unavailable ngay lúc `append(...)`. So sánh với việc **không đăng ký** `AuditClient`. Khi nào lỗi xuất hiện? Vì sao cách sửa khác nhau?

## 17. Câu hỏi tự kiểm tra

1. Vì sao phải bắt đầu từ resolution target và đường phụ thuộc thay vì chỉ đọc exception ngoài cùng?
2. Binding key khác implementation cụ thể như thế nào?
3. Khi nhiều implementation cùng thỏa interface, tiêu chí chọn được xác định ở đâu?
4. Constructor cycle khác với một vòng lời gọi method ở runtime ra sao?
5. Vì sao request-scoped dependency không nên bị singleton giữ trực tiếp?
6. Hai lần `resolve` có luôn tạo hai instance không?
7. Container khởi động thành công có bảo đảm mọi lazy binding đều hợp lệ không?
8. Một dependency được tạo thành công có chứng minh database sẵn sàng không?
9. Vì sao request phải đóng trước application-scoped client?
10. Tại sao test chọn đúng policy/strategy không thể thay thế chỉ bằng kiểm tra graph có đủ kiểu?
11. Trong Java thuần, nơi nào tương ứng với registration của DI container?
12. Những trường nào nên đưa vào trace để vừa hỗ trợ chẩn đoán vừa tránh lộ dữ liệu?

**Gợi ý:** (1) path chỉ ra node gốc; (2) key là hợp đồng yêu cầu, implementation là object được factory tạo; (3) composition/qualifier/profile/factory; (4) một bên cản xây graph, bên kia là hành vi gọi; (5) lifetime và dữ liệu request bị giữ quá hạn; (6) không, phụ thuộc scope/cache; (7) không, còn nhánh lazy/dynamic; (8) không, readiness riêng; (9) tránh sử dụng resource đã đóng; (10) thứ tự nghiệp vụ nằm ngoài kiểm tra type; (11) composition root/factory map; (12) type, scope, path, mã lỗi, correlation ID an toàn.

## Ghi nhớ

- **Chẩn đoán DI theo chuỗi:** yêu cầu phân giải → registration/selection → dependency path → scope/cache → constructor/factory → vòng đời và ownership.
- **Lỗi composition khác lỗi execution:** thiếu binding, vòng constructor và scope mismatch không phải timeout/database outage.
- **Tường minh giúp truy vết:** constructor injection và composition root cho thấy collaborator thật; tránh giấu chúng sau Service Locator.
- **Scope quyết định quyền chia sẻ instance, ownership quyết định ai đóng.** Request resource đóng khi request kết thúc, còn client dùng chung đóng sau khi các consumer ngừng sử dụng.
- **Một trace tốt ghi key, path, scope, outcome và thời điểm lỗi**, không cần sao chép secret hoặc toàn bộ request.
- **Java 17 thuần đủ để luyện quy trình chẩn đoán:** registry nhỏ, fake test và danh sách sự kiện giúp quan sát missing binding, duplicate binding, cycle, captive dependency, reuse và disposal trước khi dùng công cụ chẩn đoán của DI container thực tế.
