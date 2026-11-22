# Instance bị chia sẻ ngoài ý muốn hoặc bị tạo mới quá nhiều

## 1. Hai lỗi đối nghịch trong cùng một object graph

Trong **Dependency Injection (DI)**, một service nhận phụ thuộc từ bên ngoài, còn **composition root** hoặc DI container tạo và lắp ghép các đối tượng. Cách tổ chức này giúp giảm coupling, nhưng **không tự bảo đảm số lượng instance hoặc vòng đời instance đúng như mong đợi**.

Một object graph có thể mắc hai lỗi trái ngược:

- **Chia sẻ ngoài ý muốn (accidental sharing):** đối tượng có trạng thái chỉ dành cho một request hoặc tác vụ lại được giữ bởi singleton/app-scoped service. Request sau nhìn thấy dữ liệu của request trước, các thao tác đồng thời ghi đè nhau hoặc resource đã hết hiệu lực vẫn bị sử dụng.
- **Tạo mới quá nhiều (over-creation):** một client, connection pool, bộ máy biên dịch template hoặc cache đáng ra dùng chung lại bị tạo trong mỗi request. Hệ thống tốn thời gian khởi tạo, bộ nhớ, kết nối và chi phí đóng/mở mà không cải thiện cách ly dữ liệu.

Hai lỗi đều xuất phát từ việc **scope thực tế của instance không khớp với scope thiết kế**. Chúng có thể tồn tại ngay cả khi mọi constructor đều nhận dependency hợp lệ và toàn bộ chương trình không có một lệnh `new` nào trong lớp nghiệp vụ.

Bài thuộc chương **Chẩn đoán DI** của module **DEPENDENCY_INJECTION**. Mục tiêu là quan sát đúng *instance nào được tạo, ai sử dụng, trong bao lâu và ai đóng*, thực hành chẩn đoán bằng Java thuần rồi mới liên hệ tới cơ chế singleton, prototype, request scope, provider và lifecycle của DI container.

### Ví dụ trực giác

Một ứng dụng nhận hai request:

- Request A của `alice` cần giỏ nháp riêng với `ORDER-A1`.
- Request B của `bob` cần giỏ nháp riêng với `ORDER-B1`.
- Cả hai có thể dùng chung một gateway gửi đơn được thiết kế cho nhiều request.

**Đúng:** tạo hai trạng thái request độc lập nhưng chỉ một gateway dùng chung cho vòng đời ứng dụng.

**Sai kiểu 1:** một `List` đơn hàng nằm trong singleton handler khiến Bob nhìn thấy `ORDER-A1`.

**Sai kiểu 2:** tạo lại một gateway/pool đắt tiền cho mỗi request dù nó không giữ trạng thái request; sau hai request đã mở và đóng hai gateway.

## 2. Trước khi sửa, xác định số instance mong đợi

Không thể kết luận một đối tượng được tạo “quá nhiều” nếu chưa biết **scope và cardinality dự kiến**.

| Loại đối tượng | Phạm vi dự kiến | Số lượng dự kiến với hai request A, B | Vì sao |
| --- | --- | ---: | --- |
| `OrderService` không giữ state theo request | Ứng dụng | 1 | Cùng quy tắc và dependency dùng chung |
| `GatewayClient` đủ an toàn cho cách dùng chung | Ứng dụng | 1 | Client/pool cấu hình sẵn, tái sử dụng tài nguyên |
| `RequestSession` có danh tính và danh sách nháp | Request | 2 | Trạng thái A và B phải tách biệt |
| `Transaction` hoặc stream riêng của tác vụ | Tác vụ | 2, nếu mỗi request cần một | Phải đóng/commit/rollback khi tác vụ kết thúc |
| `OrderSummary` là kết quả nghiệp vụ | Từng lần tạo kết quả | Theo số đơn, không theo số request cố định | Value object không phải dependency dùng chung |
| Cache nghiệp vụ dùng chung | Theo ứng dụng hoặc tenant, tùy thiết kế | Theo khóa/scope đã định | Cần tính đúng của dữ liệu và an toàn đồng thời |

Trong ví dụ, “1 gateway” là **giả định thiết kế** cho một client có thể dùng lại. Với client không thread-safe, một client cho mọi request chưa chắc đúng; có thể cần một pool, factory hoặc instance theo scope. **Đừng áp đặt singleton cho mọi đối tượng đắt tiền**: phải xem hợp đồng của thư viện và mô hình concurrency thực tế.

### Sơ đồ đúng và sai

~~~mermaid
flowchart TB
    subgraph WrongShare["Sai: trạng thái ngắn hạn bị giữ chung"]
        H1["Singleton Handler"] --> C1["Một RequestCart mutable"]
        A1["Request A"] --> H1
        B1["Request B"] --> H1
    end

    subgraph WrongCreate["Sai: client dùng chung bị tạo liên tục"]
        A2["Request A"] --> G1["GatewayClient A"]
        B2["Request B"] --> G2["GatewayClient B"]
    end

    subgraph Correct["Đúng theo hợp đồng ví dụ"]
        Root["Composition root"] --> Gateway["Một GatewayClient"]
        Root --> Service["Một OrderService"]
        Service --> Gateway
        RA["Request A"] --> CA["RequestSession A"]
        RB["Request B"] --> CB["RequestSession B"]
        CA -->|"gọi tạm thời"| Service
        CB -->|"gọi tạm thời"| Service
    end
~~~

Sơ đồ diễn tả **số instance**, không chỉ type. Một type `GatewayClient` có thể có một hoặc nhiều instance tùy nơi tạo. Đọc riêng tên class hoặc annotation là chưa đủ để biết graph lúc chạy có bao nhiêu đối tượng.

## 3. Lỗi thứ nhất: instance bị chia sẻ ngoài ý muốn

Một trường hợp hay gặp là **singleton service giữ field mutable dành cho request**:

~~~java
// Phác họa lỗi, không phải chương trình độc lập.
final class WrongOrderHandler {
    private final java.util.List<String> pendingOrders =
            new java.util.ArrayList<>();

    void handle(String orderId) {
        pendingOrders.add(orderId);
        process(pendingOrders);
    }

    private void process(java.util.List<String> orders) {
        // Tất cả request nhìn thấy cùng danh sách.
    }
}
~~~

Nếu `WrongOrderHandler` được tạo một lần và phục vụ nhiều request, `pendingOrders` không tự trở thành danh sách mới cho từng request. Request B có thể nhìn thấy dữ liệu của A; trong môi trường đồng thời, hai thread còn có thể cùng sửa `ArrayList` vốn không thread-safe.

Các biến thể tương tự:

- `currentUserId` hoặc `currentTenantId` trong field của singleton.
- `EntityManager`, transaction/session hoặc connection được mượn theo request rồi giữ lại lâu dài.
- Builder, parser có buffer mutable hoặc formatter có trạng thái được dùng chung dù không an toàn luồng.
- Cache toàn cục lưu trực tiếp đối tượng chứa thông tin một request.
- Callback/lambda sống lâu bắt giữ `RequestContext` đã hết hiệu lực.

### Vì sao thêm `synchronized` chưa đủ?

Đồng bộ có thể ngăn truy cập đồng thời gây hỏng cấu trúc `List`, nhưng **không tự thay đổi ý nghĩa scope**. Sau khi xử lý request A, danh sách vẫn giữ đơn A. Request B sau đó vẫn thấy dữ liệu A dù tất cả lời gọi đều nối đuôi nhau.

Vấn đề cần sửa là **quyền sở hữu state và thời gian giữ tham chiếu**, không chỉ race condition.

## 4. Lỗi thứ hai: instance bị tạo mới quá nhiều

Một trường hợp đối nghịch:

~~~java
// Phác họa: tạo client/pool trong từng lời gọi.
void handle(String orderId) {
    try (GatewayClient gateway = new GatewayClient(config)) {
        gateway.send(orderId);
    }
}
~~~

Nếu `GatewayClient` là client/pool đắt tiền và hỗ trợ tái sử dụng nhiều request, cách này có thể gây:

- Thiết lập kết nối/TLS hoặc đọc cấu hình lặp lại, tăng độ trễ request.
- Nhiều socket, thread nền, bộ đệm hoặc pool tồn tại cùng lúc.
- Cache không được tận dụng giữa các lời gọi.
- Tăng áp lực GC và nguy cơ cạn giới hạn file descriptor/kết nối.
- Nếu quên `close()`, tài nguyên rò rỉ theo số lần request.

Mã có `try-with-resources` ở trên **không rò rỉ theo hợp đồng đóng**, nhưng vẫn có thể **không hiệu quả vì tạo quá nhiều**. Đây là hai chẩn đoán khác nhau.

Một client **không an toàn cho nhiều thread**, một transaction hoặc một request buffer lại có thể **cần tạo mới** mỗi lần: trong các tình huống ấy, tăng số instance là hành vi đúng. Chỉ kết luận “quá nhiều” sau khi đối chiếu **mục đích, scope, chi phí và khả năng chia sẻ** của đối tượng.

## 5. Những nguyên nhân làm scope thực tế lệch khỏi dự kiến

| Nguồn gốc | Biểu hiện | Cách xác minh |
| --- | --- | --- |
| `new` được đặt trong request handler | Số client tăng cùng số request | Ghi số lần constructor/factory được gọi |
| Composition root được dựng lại trong mỗi lời gọi | Mỗi request nhận cả một graph mới | Tìm nơi tạo graph và vòng đời đối tượng sở hữu |
| Container được khởi tạo nhiều lần | Mỗi application context có singleton riêng | Ghi số context và instance thuộc từng context |
| Scope `prototype`/transient được dùng cho resource đắt tiền | Mỗi lần resolve tạo một instance | Kiểm tra scope đăng ký và số lần `get()` |
| Factory/provider trả instance mới ngoài ý muốn | `get()` trong vòng lặp/request tạo nhiều đối tượng | Test identity bằng `==` và đếm số lần tạo |
| Singleton giữ instance request thật | Request sau dùng state đã hết hiệu lực | Truy đường field và vòng đời dependency |
| Cache hoặc static mutable field | Dữ liệu request A xuất hiện trong B | Test nhiều request khác nhau, kể cả tuần tự |
| Dependency được cache trong caller lâu hơn scope | Provider lấy đúng instance nhưng caller lưu sai | Kiểm tra nơi giữ tham chiếu sau lần resolve |
| Lazy provider thiếu đồng bộ | Hai thread cùng khởi tạo “một lần” | Kiểm tra race lúc khởi tạo, đo số constructor |
| Tạo hai instance độc lập nhưng tưởng dùng chung | Cache không thống nhất, pool tăng đôi | So sánh identity và vị trí tạo/đăng ký |

**Lưu ý:** một container thường có khái niệm singleton **trong phạm vi của chính container/context**, không nhất thiết là singleton duy nhất trong mọi JVM hoặc mọi tiến trình. Hai application context độc lập có thể có hai instance singleton hợp lệ, nhưng vẫn gây trùng tài nguyên nếu thiết kế vận hành chỉ dự tính một pool.

## 6. Quy trình chẩn đoán: từ triệu chứng đến object graph

Thực hiện theo trình tự, thay vì thêm annotation hoặc cache một cách thử-và-sai:

1. **Ghi triệu chứng cụ thể.** Ví dụ request B thấy giỏ A, hoặc số client được tạo tăng theo request.
2. **Viết kỳ vọng số lượng instance.** Nêu rõ một instance theo ứng dụng, một theo request, một theo job hay một cho mỗi lần gọi factory.
3. **Vẽ đường tham chiếu.** Ai tạo? Ai tiêm? Ai giữ field? Caller có lưu đối tượng trả về từ provider không?
4. **Gắn vòng đời.** Instance được tạo lúc startup, request hay task; lúc nào hết hiệu lực/được đóng?
5. **Quan sát identity và số lần tạo.** Dùng counter, instance ID hoặc tracing có kiểm soát; không chỉ nhìn type.
6. **Kiểm tra cả hai chiều.** Có đối tượng sống quá lâu do chia sẻ? Có đối tượng lẽ ra chia sẻ nhưng tạo lại?
7. **Tái hiện với ít nhất hai request.** Đổi actor/tenant và xác minh không lẫn state; đo số instance client trước và sau.
8. **Sửa ở đúng ranh giới.** Di chuyển khởi tạo về composition root, tạo state theo request hoặc dùng factory đúng scope.
9. **Kiểm tra cleanup/shutdown.** Resource đã tạo phải có owner; sửa tạo trùng không được tạo leak hoặc use-after-close.
10. **Bổ sung test hồi quy và quan sát vận hành.** Theo dõi count/latency trong môi trường đại diện.

~~~mermaid
flowchart TD
    Start["Phát hiện triệu chứng"] --> Expect["Viết scope và số instance kỳ vọng"]
    Expect --> Observe["Đếm tạo/đóng + quan sát identity"]
    Observe --> Problem{"Lệch theo hướng nào?"}
    Problem -->|"Chia sẻ quá rộng"| Isolate["Đưa mutable state vào request/job"]
    Problem -->|"Tạo quá thường xuyên"| Reuse["Chia sẻ dependency an toàn tại app root"]
    Problem -->|"Không lệch"| Else["Kiểm tra logic, transaction, thread safety"]
    Isolate --> Test["Test hai request và lifecycle"]
    Reuse --> Test
    Test --> Measure["Đo lại và xác nhận hết triệu chứng"]
~~~

### Chẩn đoán bằng identity thay vì chỉ so sánh dữ liệu

Trong Java, toán tử `a == b` kiểm tra **hai tham chiếu có trỏ đến cùng một object** hay không (với các reference thông thường). `equals()` có thể trả `true` cho hai object khác nhau có cùng dữ liệu, nên **không thích hợp để đếm identity**.

`System.identityHashCode(object)` có thể hỗ trợ log chẩn đoán, nhưng **không cam kết duy nhất tuyệt đối** giữa mọi instance, cũng không phải mã nhận diện ổn định qua các lần chạy. Để quan sát chính xác, có thể gắn **một ID tăng dần khi xây dựng** hoặc dùng công cụ tracing/profiling phù hợp.

Khi ghi log thực tế, **không log nguyên token, password, nội dung giỏ hàng hoặc dữ liệu nhạy cảm** chỉ để xác minh scope. Instance ID, scope ID, counter và request correlation ID đã được xử lý phù hợp thường đủ để chẩn đoán.

## 7. Ví dụ Java 11: mô phỏng cả hai lỗi và đồ thị đúng

Ví dụ dưới đây **không tạo kết nối mạng thật**. `TrackingGateway` đóng vai trò tài nguyên dùng chung và có counter theo dõi lần tạo/đóng/gửi. Mục tiêu là minh họa **identity, số lượng instance, request isolation và lifecycle** mà không gây I/O bên ngoài.

Lưu thành **`ScopeDiagnosisDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

public final class ScopeDiagnosisDemo {

    // Công cụ đo để minh họa, không dùng làm global registry.
    public static final class Counters {
        private final AtomicInteger created = new AtomicInteger();
        private final AtomicInteger closed = new AtomicInteger();
        private final AtomicInteger sent = new AtomicInteger();
        private final List<String> deliveries = new CopyOnWriteArrayList<>();

        private void onCreate() {
            created.incrementAndGet();
        }

        private void onClose() {
            closed.incrementAndGet();
        }

        private void onSend(String actorId, String orderId) {
            sent.incrementAndGet();
            deliveries.add(actorId + ":" + orderId);
        }

        public int created() {
            return created.get();
        }

        public int closed() {
            return closed.get();
        }

        public int sent() {
            return sent.get();
        }

        public List<String> deliveries() {
            return List.copyOf(deliveries);
        }
    }

    public interface Gateway {
        void send(String actorId, String orderId);
    }

    // Mô phỏng một client dùng chung, có vòng đời cần đóng.
    public static final class TrackingGateway
            implements Gateway, AutoCloseable {
        private final Counters counters;
        private boolean closed;

        public TrackingGateway(Counters counters) {
            this.counters = Objects.requireNonNull(counters, "counters");
            this.counters.onCreate();
        }

        @Override
        public synchronized void send(String actorId, String orderId) {
            if (closed) {
                throw new IllegalStateException("Gateway đã đóng");
            }
            counters.onSend(actorId, orderId);
        }

        @Override
        public synchronized void close() {
            if (!closed) {
                closed = true;
                counters.onClose();
            }
        }
    }

    // Một request sở hữu state riêng và giới hạn thời gian sử dụng.
    public static final class RequestSession implements AutoCloseable {
        private final String actorId;
        private final List<String> pending = new ArrayList<>();
        private boolean closed;

        public RequestSession(String actorId) {
            if (actorId == null || actorId.isBlank()) {
                throw new IllegalArgumentException("actorId không hợp lệ");
            }
            this.actorId = actorId;
        }

        private void requireOpen() {
            if (closed) {
                throw new IllegalStateException(
                        "RequestSession đã hết hiệu lực");
            }
        }

        public void addOrder(String orderId) {
            requireOpen();
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            pending.add(orderId);
        }

        public String actorId() {
            requireOpen();
            return actorId;
        }

        public List<String> orders() {
            requireOpen();
            return List.copyOf(pending);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                pending.clear();
            }
        }
    }

    // Core có thể dùng chung: không giữ RequestSession trong field.
    public static final class OrderService {
        private final Gateway gateway;

        public OrderService(Gateway gateway) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
        }

        public void submit(RequestSession request) {
            Objects.requireNonNull(request, "request");
            String actorId = request.actorId();
            List<String> orders = request.orders();

            for (String orderId : orders) {
                gateway.send(actorId, orderId);
            }
        }
    }

    // LỖI 1: handler dùng chung giữ state của mọi request.
    public static final class BadSharedCart {
        private final List<String> allPending = new ArrayList<>();

        public List<String> handle(String actorId, String orderId) {
            Objects.requireNonNull(actorId, "actorId");
            Objects.requireNonNull(orderId, "orderId");
            allPending.add(actorId + ":" + orderId);
            return List.copyOf(allPending);
        }
    }

    // LỖI 2: client dùng chung bị dựng lại ở mỗi request.
    public static void sendWithNewGatewayPerRequest(
            Counters counters, String actorId, String orderId) {
        try (TrackingGateway gateway = new TrackingGateway(counters);
             RequestSession request = new RequestSession(actorId)) {
            OrderService service = new OrderService(gateway);
            request.addOrder(orderId);
            service.submit(request);
        }
    }

    // CÁCH ĐÚNG: composition root sở hữu client dùng chung.
    public static final class ApplicationGraph implements AutoCloseable {
        private final TrackingGateway gateway;
        private final OrderService orders;
        private boolean closed;

        private ApplicationGraph(
                TrackingGateway gateway, OrderService orders) {
            this.gateway = gateway;
            this.orders = orders;
        }

        public static ApplicationGraph start(Counters counters) {
            TrackingGateway gateway = new TrackingGateway(counters);
            try {
                OrderService service = new OrderService(gateway);
                return new ApplicationGraph(gateway, service);
            } catch (RuntimeException | Error failure) {
                // Nếu graph chưa được trả về, dọn resource đã tạo.
                gateway.close();
                throw failure;
            }
        }

        public void handle(String actorId, String orderId) {
            if (closed) {
                throw new IllegalStateException("ApplicationGraph đã đóng");
            }

            // State theo request được tạo/đóng trong đúng boundary.
            try (RequestSession request = new RequestSession(actorId)) {
                request.addOrder(orderId);
                orders.submit(request);
            }
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                gateway.close();
            }
        }
    }

    public static void main(String[] args) {
        // Tình huống 1: request B nhìn thấy dữ liệu A.
        BadSharedCart wrong = new BadSharedCart();
        System.out.println("BAD shared A: "
                + wrong.handle("alice", "ORDER-A1"));
        System.out.println("BAD shared B: "
                + wrong.handle("bob", "ORDER-B1"));

        // Tình huống 2: không rò rỉ, nhưng đã tạo client hai lần.
        Counters waste = new Counters();
        sendWithNewGatewayPerRequest(waste, "alice", "ORDER-A1");
        sendWithNewGatewayPerRequest(waste, "bob", "ORDER-B1");
        System.out.println("BAD over-created: created=" + waste.created()
                + ", closed=" + waste.closed());

        // Lắp ghép đúng: một client chung, state riêng mỗi request.
        Counters healthy = new Counters();
        try (ApplicationGraph app = ApplicationGraph.start(healthy)) {
            app.handle("alice", "ORDER-A1");
            app.handle("bob", "ORDER-B1");
            System.out.println("GOOD during app: created="
                    + healthy.created() + ", closed=" + healthy.closed()
                    + ", sent=" + healthy.sent());
        }
        System.out.println("GOOD after close: created="
                + healthy.created() + ", closed=" + healthy.closed());
    }
}
~~~

### Chạy chương trình

~~~bash
javac ScopeDiagnosisDemo.java
java ScopeDiagnosisDemo
~~~

Đầu ra dự kiến:

~~~text
BAD shared A: [alice:ORDER-A1]
BAD shared B: [alice:ORDER-A1, bob:ORDER-B1]
BAD over-created: created=2, closed=2
GOOD during app: created=1, closed=0, sent=2
GOOD after close: created=1, closed=1
~~~

**Đọc số liệu cho đúng:**

- `BAD shared B` bao gồm đơn của Alice: lỗi scope xảy ra **ngay cả khi hai request chạy tuần tự**.
- `BAD over-created` có `created=2, closed=2`: không phải leak; đây là tạo dư so với thiết kế dùng chung.
- `GOOD during app` có `created=1, closed=0`: gateway đang hoạt động trong vòng đời ứng dụng.
- `GOOD after close` có `created=1, closed=1`: composition root đã đóng resource do nó sở hữu đúng một lần.
- `sent=2` chứng minh cùng gateway xử lý hai đơn mà `OrderService` không cần giữ state của request trước.

**Giới hạn:** `TrackingGateway` chỉ mô phỏng lifecycle bằng counter, không phản ánh chi phí kết nối mạng thật. `RequestSession`, `BadSharedCart` và `ApplicationGraph` ở ví dụ được dùng **tuần tự**; đồng bộ riêng `TrackingGateway.send/close` không biến toàn bộ graph thành server an toàn khi nhiều request đồng thời hoặc khi shutdown đan xen request.

## 8. Kiểm thử chẩn đoán thay vì chỉ nhìn kết quả cuối

Một lỗi scope có thể **không lộ ở request đầu tiên**. Một lỗi tạo dư có thể vẫn cho kết quả nghiệp vụ đúng. Vì vậy, test phải quan sát cả **state isolation** và **cardinality/lifecycle**.

Lưu thành **`ScopeDiagnosisDemoTest.java`** cạnh file demo:

~~~java
import java.util.List;

public final class ScopeDiagnosisDemoTest {

    private static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    private static void testBadSharingIsObservable() {
        ScopeDiagnosisDemo.BadSharedCart wrong =
                new ScopeDiagnosisDemo.BadSharedCart();

        List<String> afterA = wrong.handle("alice", "ORDER-A1");
        List<String> afterB = wrong.handle("bob", "ORDER-B1");

        check(afterA.equals(List.of("alice:ORDER-A1")),
                "Request A phải tạo một dòng");
        check(afterB.equals(List.of(
                "alice:ORDER-A1", "bob:ORDER-B1")),
                "Lỗi chia sẻ state phải được tái hiện");
    }

    private static void testNewGatewayEachTimeIsMeasurable() {
        ScopeDiagnosisDemo.Counters waste =
                new ScopeDiagnosisDemo.Counters();

        ScopeDiagnosisDemo.sendWithNewGatewayPerRequest(
                waste, "alice", "ORDER-A1");
        ScopeDiagnosisDemo.sendWithNewGatewayPerRequest(
                waste, "bob", "ORDER-B1");

        check(waste.created() == 2,
                "Đường sai tạo hai gateway");
        check(waste.closed() == 2,
                "Đường sai vẫn đóng đủ gateway");
        check(waste.sent() == 2,
                "Cả hai lời gọi vẫn gửi được");
    }

    private static void testCorrectGraphAndLifecycle() {
        ScopeDiagnosisDemo.Counters metrics =
                new ScopeDiagnosisDemo.Counters();

        ScopeDiagnosisDemo.ApplicationGraph app =
                ScopeDiagnosisDemo.ApplicationGraph.start(metrics);
        try {
            app.handle("alice", "ORDER-A1");
            app.handle("bob", "ORDER-B1");

            check(metrics.created() == 1,
                    "Phải tạo một gateway cấp ứng dụng");
            check(metrics.closed() == 0,
                    "Không được đóng gateway sau từng request");
            check(metrics.sent() == 2,
                    "Hai request phải được xử lý");
            check(metrics.deliveries().equals(List.of(
                    "alice:ORDER-A1", "bob:ORDER-B1")),
                    "Không được trộn dữ liệu hai request");
        } finally {
            app.close();
        }

        check(metrics.created() == 1 && metrics.closed() == 1,
                "Phải đóng đúng một gateway khi ứng dụng kết thúc");

        // Close idempotent, tránh double-close do nhiều đường cleanup.
        app.close();
        check(metrics.closed() == 1,
                "Đóng lần hai không được tính thêm");

        boolean refused = false;
        try {
            app.handle("charlie", "ORDER-C1");
        } catch (IllegalStateException expected) {
            refused = true;
        }
        check(refused, "Không được xử lý sau khi graph đóng");
    }

    private static void testRequestScopeExpires() {
        ScopeDiagnosisDemo.RequestSession request =
                new ScopeDiagnosisDemo.RequestSession("alice");
        request.addOrder("ORDER-A1");
        check(request.orders().size() == 1,
                "Request đang hoạt động phải giữ đơn của mình");
        request.close();

        boolean refused = false;
        try {
            request.addOrder("ORDER-A2");
        } catch (IllegalStateException expected) {
            refused = true;
        }
        check(refused, "Request đã kết thúc phải từ chối sử dụng");
    }

    private static void testConstructorInjectionIsExplicit() {
        boolean rejected = false;
        try {
            new ScopeDiagnosisDemo.OrderService(null);
        } catch (NullPointerException expected) {
            rejected = true;
        }
        check(rejected, "Gateway là dependency bắt buộc");
    }

    public static void main(String[] args) {
        testBadSharingIsObservable();
        testNewGatewayEachTimeIsMeasurable();
        testCorrectGraphAndLifecycle();
        testRequestScopeExpires();
        testConstructorInjectionIsExplicit();

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ScopeDiagnosisDemo.java ScopeDiagnosisDemoTest.java
java ScopeDiagnosisDemoTest
~~~

Kết quả mong đợi:

~~~text
Tất cả kiểm thử đều đạt.
~~~

Các test về `BadSharedCart` và `sendWithNewGatewayPerRequest` **cố ý xác nhận lỗi có thể tái hiện**, không khuyến khích giữ thiết kế sai. Test của `ApplicationGraph` xác minh cách khắc phục theo hợp đồng ví dụ: số gateway là 1, dữ liệu A/B tách biệt, không đóng resource quá sớm và đóng một lần khi kết thúc.

### Vì sao không chỉ test `equals()`?

Hai `TrackingGateway` khác nhau có thể cấu hình hệt nhau và cho kết quả gửi giống hệt nhau. Test nghiệp vụ thông thường sẽ đạt, nhưng vẫn không phát hiện **hai lần tạo**. Counter `created()` và `closed()` giúp kiểm tra điều kiện về instance/lifecycle, trong khi danh sách `deliveries()` kiểm tra hành vi.

Trong test lớn hơn, có thể dùng fake factory ghi số lần `create()`, gắn ID cho từng instance và ghi lại luồng acquire/release. Không nên đưa counter test-only vào mọi production service khi không có nhu cầu quan sát thực tế.

## 9. Cách sửa trong DI thủ công: scope phải nằm đúng ranh giới

Một **composition root** đúng không nhất thiết phải tạo tất cả mọi object ngay tại startup.

Nó cần quyết định **loại đối tượng nào được chia sẻ**, và **cách tạo đối tượng theo request/tác vụ**:

- **App-scoped:** tạo ở startup hoặc lazy một lần; giữ trong graph; đóng khi graph kết thúc.
- **Request-scoped:** tạo tại request boundary, dùng trong thời gian request, hủy/đóng ở cuối request.
- **Job-scoped:** tạo khi nhận job, đóng sau khi job hoàn thành hoặc hủy.
- **Transient value object:** tạo tự nhiên khi cần, thường không có lifecycle đặc biệt.

Trong ví dụ, `ApplicationGraph` tạo `TrackingGateway` và `OrderService` **một lần**. Mỗi `handle(...)` tạo một `RequestSession` bằng `try-with-resources`, dùng nó trong lời gọi rồi kết thúc.

Điều quan trọng không phải “mọi `new` chuyển vào một file” mà là **đặt quyết định tạo và ownership ở nơi phù hợp**:

~~~java
// Phác họa đúng trách nhiệm, dùng các kiểu của ví dụ.
try (ScopeDiagnosisDemo.ApplicationGraph app =
        ScopeDiagnosisDemo.ApplicationGraph.start(metrics)) {
    app.handle("alice", "ORDER-A1");
    app.handle("bob", "ORDER-B1");
}
~~~

Một cách thiết kế khác là dùng factory cho các đối tượng cần tạo theo request:

~~~java
// Phác họa API cho hệ thống lớn hơn.
interface RequestSessionFactory {
    ScopeDiagnosisDemo.RequestSession open(String actorId);
}
~~~

Nếu việc tạo `RequestSession` chỉ là một constructor đơn giản, factory riêng **chưa chắc cần thiết**. Factory có giá trị khi phải tạo một graph theo request, có tài nguyên, nhiều bước khởi tạo hoặc cần một seam giúp lựa chọn implementation.

### Tránh “sửa” bằng cách cache mọi object

Nếu áp dụng cache cho tất cả instance để giảm số lần `new`, bạn có thể vô tình giữ `RequestSession` của A cho B. Việc giảm allocation là mục tiêu hiệu năng, nhưng **không được phá hợp đồng scope**.

Đối với connection, có thể phải dùng **pool cấp ứng dụng** và **connection được mượn cấp tác vụ**. Pool sống lâu; connection/session được acquire rồi release theo transaction. Không nên hiểu “client dùng chung” là “một connection duy nhất dùng đồng thời cho mọi request”.

## 10. Liên hệ DI container: scope annotation không thay thế việc kiểm chứng

DI container có thể hỗ trợ singleton, prototype/transient, request scope, factory/provider, lazy initialization và lifecycle hook. Tuy nhiên, **tên scope và quy tắc chính xác khác nhau giữa Spring, CDI, Guice hoặc các công cụ khác**.

Một lỗi có thể đến từ cấu hình như:

- Bean client đắt tiền bị đăng ký dạng prototype rồi được resolve ở mỗi request.
- Bean singleton giữ tham chiếu trực tiếp đến một đối tượng chứa state theo request.
- Component được scan/đăng ký ở nhiều application context không như dự tính.
- Provider `get()` được gọi nhiều lần vì consumer tưởng rằng nó memoize.
- Lazy singleton được tự viết nhưng không bảo vệ khởi tạo đồng thời.
- Scoped proxy hoạt động đúng lúc resolve, nhưng caller lại lưu object trả về quá thời gian sống của scope.

Các đoạn sau chỉ mang tính **minh họa ý tưởng**, không phải một chương trình Spring chạy độc lập:

~~~java
// Trong Spring, ý nghĩa scope do metadata/configuration và context xác định.
// @Scope("singleton") không chứng minh nội bộ bean an toàn luồng.
// @Scope("prototype") có thể dẫn đến tạo mới nhiều lần khi được yêu cầu.
//
// Một singleton dùng provider:
// final class Handler {
//     private final ObjectProvider<RequestState> states;
//     Handler(ObjectProvider<RequestState> states) { this.states = states; }
//     void handle() { RequestState current = states.getObject(); ... }
// }
//
// Phải hiểu getObject() lấy theo scope nào, ai sở hữu và khi nào close.
~~~

Trong framework thực, cần kiểm tra **định nghĩa bean, qualifier, scope, provider, số context và shutdown** trên chính ứng dụng đó. Không suy ra vòng đời của bean từ việc có annotation `@Component` hoặc từ class name.

### Scope mismatch: chỉ thay annotation có đủ không?

Chưa chắc. Một singleton giữ field `RequestContext` thực có thể tiếp tục sai nếu context hết hạn. Scoped proxy/provider có thể giải quyết **thời điểm phân giải** nhưng không tự giải quyết **việc giữ tham chiếu quá lâu**, truyền context sang background thread hoặc truy cập sau khi request đóng.

Khi dữ liệu request chỉ cần trong một lời gọi đồng bộ, **method injection** hoặc một tham số ngữ nghĩa như `actorId` đã được xác thực thường dễ hiểu hơn dùng container để ẩn context.

## 11. Quan sát trong production: đếm đúng và tránh kết luận vội

Trong môi trường thật, dùng counter chỉ là một phần. Cần quan sát cả chi phí và tình huống sử dụng:

| Tín hiệu | Có thể gợi ý | Không đủ để kết luận |
| --- | --- | --- |
| Số lần tạo client tăng bằng số request | Client bị dựng lại trong request path | Có thể client thực sự phải sống theo request |
| Số connection mở tăng không giảm | Pool trùng, resource leak hoặc lưu lượng tăng | Cần xem số đóng/trả về pool và giới hạn tải |
| P99 latency tăng ở lần gọi đầu | Lazy initialization, kết nối/TLS hoặc cache cold | Không chắc chỉ do DI |
| GC và allocation cao | Nhiều object được tạo | Tạo value object nhiều có thể vẫn bình thường |
| Cache hit-rate thấp bất thường | Cache bị tạo lại, scope quá hẹp | Cũng có thể do đặc tính dữ liệu hoặc invalidation |
| Request B nhận dữ liệu A | State chia sẻ quá rộng hoặc khóa cache sai | Cần tìm đường dữ liệu, không mặc định chỉ DI |
| Nhiều bean cùng type trong log | Nhiều registration/context | Có thể là nhiều instance hợp lệ theo cấu hình |

**Một đo lường có ích** là số tài nguyên đang hoạt động:

`active = created - closed`

Nhưng phép tính chỉ đáng tin nếu `created`/`closed` đếm cùng loại đối tượng, trong cùng phạm vi quan sát, và mỗi lần đóng chỉ được tính một lần. Một resource của pool có thể được **mượn/trả nhiều lần** mà không được tạo/đóng vật lý; khi ấy cần chỉ số `acquire` và `release` riêng. Không lấy `active` làm số connection còn sống nếu counter đang đếm wrapper theo request.

Không log dữ liệu người dùng để chứng minh state leak. Nên dùng request ID nội bộ, instance ID, loại bean, scope và event lifecycle đủ để khoanh vùng.

## 12. Thread safety, scope và shutdown cần được kiểm tra cùng nhau

**Chia sẻ đúng số instance** chưa đủ để đúng kiến trúc:

- Một singleton với field `final` chứa `ArrayList` mutable vẫn **không tự thread-safe**.
- Một client dùng chung có thể thread-safe về mặt API nhưng không nên bị đóng khi còn request đang sử dụng.
- Một request-scoped object có thể được giữ trong lambda hoặc task chạy nền sau khi request kết thúc.
- Một provider có thể trả bean theo request, nhưng callback ở thread khác có thể không có scope hoạt động.
- Khi shutdown, cần **dừng nhận việc mới**, đợi/cancel công việc đang chạy theo chính sách, rồi đóng resource dùng chung.

Ví dụ demo đánh dấu `closed` bằng `boolean` đơn giản và xử lý tuần tự. Nó **không phải ứng dụng web đa luồng hoàn chỉnh**. Nếu dựng server thực, cần cơ chế bảo đảm lifecycle/concurrency giữa `handle` và `close`, không chỉ dựa vào một cờ không đồng bộ. Nếu tác vụ chạy sau khi graph đóng, có thể cần reference counting, graceful shutdown hoặc framework quản lý active requests.

### Chia sẻ quá ít và chia sẻ quá nhiều đôi khi xảy ra cùng lúc

Một anti-pattern kết hợp:

- Mỗi request tự tạo `OrderService` mới **và** một client mới (tạo quá nhiều).
- Nhưng các service mới lại cùng giữ `static List` lưu trạng thái user (chia sẻ quá nhiều).

Vì vậy, đừng dừng chẩn đoán ở “scope của service”. Hãy kiểm tra **từng dependency trong object graph**, kể cả static state, provider result, factory product và tài nguyên bên trong adapter.

## 13. Những cách sửa nhầm thường gặp

| Cách xử lý vội | Vì sao có thể sai? | Hướng kiểm tra và sửa |
| --- | --- | --- |
| Thêm `@Singleton` cho mọi component | Giữ cả request state và resource không an toàn luồng | Phân loại từng node theo scope thực |
| Đổi tất cả thành transient | Tạo nhiều client/pool và mất cache | Chia sẻ những thành phần thực sự an toàn |
| Bọc `List` bằng `synchronizedList` | Ngăn một số race nhưng không xóa dữ liệu A trước B | Cấp danh sách riêng theo request |
| Thêm `volatile currentUserId` | Không gắn chính xác user với từng lời gọi đồng thời | Truyền actor qua phương thức/context đúng scope |
| Cache kết quả `provider.get()` trong singleton | Giữ instance có thể thuộc request đầu tiên | Chỉ dùng kết quả trong scope hợp lệ |
| Gọi `new Client()` rồi đóng sau mỗi request | Không leak nhưng có thể tạo quá nhiều | Chia sẻ client/pool nếu hợp đồng cho phép |
| Dùng cùng một DB connection cho tất cả request | Connection/transaction có thể không an toàn đồng thời | Pool cấp app, mượn connection theo unit of work |
| Tạo một container mới ở mỗi request | Mất ý nghĩa singleton trong context cũ | Quản lý application context tại startup |
| Reset global static state giữa test | Test vẫn phụ thuộc thứ tự và có race khi chạy song song | Đưa state vào instance/scope độc lập |
| Đo `hashCode()` để nhận diện object | Hai instance có thể equals/hashCode giống nhau | Dùng identity hoặc ID do công cụ gán |
| Chỉ xem số instance lúc startup | Lazy hoặc factory có thể tạo sau đó | Đo trong đường xử lý runtime và shutdown |
| Bỏ qua close vì GC sẽ thu hồi | Socket/file/pool cần đóng đúng hợp đồng | Xác định ownership và graceful shutdown |

Không có một cấu hình singleton/prototype “chuẩn” cho mọi dependency. Mỗi lựa chọn phải giải thích được **vòng đời có nghĩa gì đối với tính đúng đắn và hiệu suất**.

## 14. Bài tập thực hành và câu hỏi tự đánh giá

**Bài 1 — Phát hiện captive state.** Viết `RequestCart` có danh sách đơn và một singleton handler giữ nó. Gọi tuần tự bằng hai actor khác nhau; xác nhận request B nhìn thấy đơn của A. Sửa bằng cách cấp cart mới tại request boundary, không sửa bằng cách chỉ thêm `synchronized`.

**Bài 2 — Đo instance theo thời gian.** Bổ sung một counter ghi số lần constructor của gateway được gọi. Chạy 1, 10 và 100 request ở hai mô hình tạo gateway mỗi request và tạo ở composition root. Ghi lại số tạo/đóng. Giải thích tại sao counter của fake không đo được latency thật của mạng.

**Bài 3 — Đổi scope có chủ đích.** Một `ReportFormatter` bất biến được tạo một lần mỗi request. Có nên dùng chung để giảm allocation không? Đưa ra điều kiện làm việc dùng chung an toàn. Sau đó xét `ReportBuilder` mutable chứa dữ liệu request, giải thích vì sao quyết định có thể ngược lại.

**Bài 4 — Provider không đồng nghĩa singleton.** Cho `Supplier<Client> supplier = Client::new`. Một service gọi `supplier.get()` hai lần. Dự đoán số instance. Thay supplier bằng một lazy memoizing provider và nêu những điều kiện thread-safety, xử lý lỗi khởi tạo và shutdown cần bổ sung.

**Bài 5 — Nhiều application context.** Một ứng dụng vô tình tạo hai DI container độc lập, mỗi container định nghĩa một `ClientPool` singleton. Có bao nhiêu pool? Nêu cách phát hiện từ log/metrics và biện pháp bảo đảm lifecycle của container được kiểm soát.

**Bài 6 — Tài nguyên theo tác vụ.** Một singleton service giữ một connection lấy từ pool khi khởi động. Đề xuất thiết kế giữ **pool cấp ứng dụng** nhưng tạo/mượn **connection theo request/transaction**. Chỉ rõ nơi commit/rollback và trả connection.

**Bài 7 — Test không chỉ kiểm kết quả.** Dùng `ScopeDiagnosisDemoTest` và bổ sung test cho `Gateway.send` sau khi đóng, test `RequestSession.orders()` sau khi đóng và test số lần tạo khi ba request sử dụng cùng `ApplicationGraph`.

**Bài 8 — Shutdown dưới tải.** Một worker đang gửi dữ liệu qua gateway, trong khi ứng dụng bắt đầu shutdown. Thiết kế thứ tự dừng nhận request mới, đợi các công việc còn chạy, đóng request resource rồi đóng gateway. Vì sao chỉ có cờ `closed` chưa đủ trong trường hợp đa luồng?

**Bài 9 — Chẩn đoán hỗn hợp.** Hệ thống có `static Map<tenantId, Session>` và tạo mới `HttpClient` cho mỗi request. Liệt kê cả hai lỗi, tác động lên dữ liệu/hiệu năng và thứ tự ưu tiên sửa. Đề xuất hai loại test riêng cho isolation và instance cardinality.

### Checklist dùng khi debug DI

- [ ] Tôi đã viết rõ số instance kỳ vọng **theo ứng dụng/request/job** chưa?
- [ ] Tôi biết chính xác **nơi tạo** từng dependency và factory/provider được gọi khi nào chưa?
- [ ] Tôi đã kiểm tra identity bằng tham chiếu hoặc instrumentation phù hợp chưa?
- [ ] Có field singleton/static/closure giữ **state ngắn hạn** quá lâu không?
- [ ] Có resource đáng chia sẻ bị tạo lại trong mỗi request không?
- [ ] Các instance dùng chung có an toàn với concurrency thật không?
- [ ] Tôi đã phân biệt **tạo dư** với **rò rỉ vì không đóng** chưa?
- [ ] Tôi biết ai đóng resource và **thứ tự shutdown** chưa?
- [ ] Có test ít nhất hai request, đo số lần tạo/đóng và kiểm tra dữ liệu không lẫn không?
- [ ] Nếu dùng container, tôi đã kiểm tra số context, scope, qualifier, provider và lazy behavior thực tế chưa?

## 15. Tổng kết

Hai triệu chứng “instance bị chia sẻ ngoài ý muốn” và “instance bị tạo mới quá nhiều” không thể giải quyết bằng việc thêm thật nhiều interface, annotation hoặc factory. Chúng cần một mô hình chính xác về **object graph, identity, scope, thời gian sử dụng và ownership**.

Trong bài thực hành, một `OrderService` không giữ trạng thái request và một `TrackingGateway` có thể được tạo một lần cho ứng dụng; `RequestSession` được tạo riêng cho từng request và đóng khi request kết thúc. Các counter giúp phát hiện **tạo dư dù không rò rỉ**, còn test qua hai actor giúp phát hiện **chia sẻ state sai ngay cả khi chạy tuần tự**.

Nguyên tắc chẩn đoán hữu ích nhất là: **“Instance này phải được dùng chung bởi ai, phải được tạo bao nhiêu lần, tồn tại đến khi nào và ai có trách nhiệm đóng?”** Khi trả lời được cả bốn câu hỏi bằng Java thuần, bạn có nền tảng để sử dụng DI container với scope và lifecycle có chủ đích, thay vì để cấu hình container che khuất lỗi thiết kế.
