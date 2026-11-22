# Chọn điểm đo theo câu hỏi cần trả lời thay vì chèn vào mọi phương thức

> **Nguyên tắc thiết kế:** Điểm đo (*instrumentation point*) không được lựa chọn bằng câu hỏi "Có bao nhiêu method có thể chèn bytecode?" mà bằng câu hỏi **"Khi số liệu xuất hiện, ta sẽ trả lời câu hỏi vận hành nào và đưa ra quyết định gì?"**. Đo đúng ranh giới nghiệp vụ, dependency hoặc hàng đợi thường hữu ích hơn chèn timer/log vào mọi phương thức. Instrumentation tràn lan có thể tạo chi phí CPU, allocation, I/O, kích thước trace và dữ liệu nhãn khổng lồ nhưng vẫn không giải thích được trải nghiệm đầu cuối.

Bài học nằm trong chủ đề **Thiết kế điểm đo** của Java Advance – instrumentation. Nội dung trình bày cách chuyển một giả thuyết thành danh sách điểm đo tối thiểu, xác định tín hiệu phù hợp, thiết kế bộ lọc cho `ClassFileTransformer`, kiểm soát overhead và kiểm nghiệm bằng một startup Java agent có thể chạy trên JDK 17+.

## 1. Bắt đầu bằng câu hỏi, không bắt đầu bằng danh sách method

Giả sử API thanh toán có triệu chứng: "Gần đây checkout chậm, nhưng máy chủ không quá tải". Một phương án thiếu trọng tâm là đo mọi method trong package `com.shop`: `toString()`, getter, `validate()`, `price()`, `charge()`, serializer, repository, helper và hàng nghìn lời gọi framework. Dữ liệu thu về nhiều nhưng câu hỏi **"Checkout chậm ở đâu?"** vẫn chưa chắc được trả lời.

Thay vào đó, đặt ba câu hỏi theo trình tự:

1. **Cái gì bị ảnh hưởng?** Độ trễ đầu cuối, tỷ lệ lỗi, số lượng đơn hàng, độ trễ của một dependency hay thời gian chờ trong queue?
2. **Ranh giới nào tạo ra kết quả quan sát?** Khi request đi vào và gửi response; khi một lệnh checkout bắt đầu/kết thúc; khi gọi payment gateway và nhận kết quả; khi enqueue/dequeue; khi lấy một connection từ pool?
3. **Quyết định nào được đưa ra sau khi đo?** Mở rộng service, tối ưu query, giảm timeout, xử lý queue backlog, điều chỉnh connection pool, rollback một release hay chỉ cần thêm một span để khoanh vùng sâu hơn?

Nếu không thể giải thích vì sao một dữ liệu sẽ thay đổi hành động của đội vận hành, điểm đo đó chưa có lý do đủ mạnh để bật mặc định ở production.

### Cây câu hỏi ví dụ

~~~text
Triệu chứng: p95 checkout tăng
    |
    +-- p95 ở HTTP ingress có tăng không?
    |       |
    |       +-- Có: đo request boundary (route, status, duration)
    |       |
    |       +-- Không: kiểm tra client, proxy, network ngoài service
    |
    +-- Checkout span/operation có chậm không?
            |
            +-- Có: chia có chọn lọc thành payment call, database wait, queue wait
            |
            +-- Không: xem chi phí trước/sau checkout, serialization hoặc HTTP transport
~~~

Đây là **sơ đồ phân tích**, không phải giả định mọi hệ thống đều có đúng các tầng này. Một phép đo ở `CheckoutService.checkout()` chỉ bao phủ code chạy bên trong method; nó **không mặc nhiên đo** thời gian request chờ ở load balancer, queue servlet, HTTP parsing hoặc thời gian ghi response ra mạng.

## 2. Dịch câu hỏi thành tín hiệu và điểm đo có ý nghĩa

Một bảng chọn nhanh:

| Câu hỏi cần trả lời | Tín hiệu nên có | Điểm đo ưu tiên | Tránh trước khi có bằng chứng |
| --- | --- | --- | --- |
| "Khách hàng thấy API chậm ở route nào?" | Histogram độ trễ, request count, error rate | HTTP server boundary, sử dụng route template | Timer ở mọi getter, entity, serializer |
| "Checkout tốn thời gian ở bước nào?" | Span tổng checkout + các span con cho dependency nghi ngờ | `checkout()`, `PaymentGateway.charge()`, điểm chờ DB nếu có | Tạo span cho từng helper tính toán nhỏ |
| "Lỗi giao dịch đến từ đâu?" | Số lỗi theo loại kết quả, exception class được chuẩn hóa | Ranh giới nơi lỗi được xác định/catch và dependency trả kết quả | Ghi cùng exception tại mọi frame của stack |
| "Hàng đợi tăng vì producer hay consumer?" | Queue depth, enqueue/dequeue times, processing time, retry count | Gửi message, bắt đầu xử lý, kết thúc/ack | Đo mọi method bên trong worker |
| "Connection pool gây nghẽn?" | Thời gian chờ acquire, tỷ lệ timeout, pool utilization | `DataSource.getConnection()` hoặc pool hook | Đo mọi DAO mà không biết wait time |
| "Độ trễ tăng do cấp phát/JIT/GC?" | Allocation/CPU profile, GC metrics, JFR events | Profiler/JFR, JVM metrics | Thay mọi method bằng timer nặng |
| "Một remote call hay timeout?" | Duration, attempt count, outcome, retry/backoff | Ranh giới client RPC/HTTP gọi ra ngoài | Chèn log vào mọi lớp HTTP nội bộ |

**Bắt đầu với tín hiệu rẻ, ổn định và trực tiếp trả lời câu hỏi.** Ví dụ p95 cần phân bố (histogram hoặc một nguồn đủ dữ liệu để tính quantile), không thể suy ra từ `sum(duration)/count`. Khi đã thấy checkout chậm trong một phân đoạn, mới thêm điểm đo bên trong phân đoạn đó.

Một điểm đo tốt phải có đủ: **operation name**, **điểm bắt đầu**, **điểm kết thúc**, **outcome**, **các thuộc tính cần thiết** và **chủ sở hữu**. Thiếu ranh giới kết thúc thì thường không đo được duration; thiếu outcome thì độ trễ cao do timeout và độ trễ cao do xử lý thành công có thể bị trộn.

## 3. Xác định ranh giới đo theo semantics, không theo số method

### 3.1. Ranh giới nghiệp vụ và dependency

Ví dụ một transaction gọi:

~~~text
HTTP POST /checkouts/{id}
   |
   v
CheckoutController
   |
   v
CheckoutService.checkout(sku)     <-- operation/business boundary
   +--> Catalog.price(sku)        <-- helper nội bộ
   +--> PaymentGateway.charge(x)  <-- dependency boundary
   +--> AuditEvent.write(...)     <-- tùy cấu hình
   |
   v
HTTP response                      <-- request boundary
~~~

Ở vòng đầu, có thể đặt **một HTTP-server metric/span** và **một điểm đo checkout**. Nếu checkout là nguồn tăng độ trễ, đặt thêm điểm đo cho `PaymentGateway.charge(...)`. Chỉ thêm `Catalog.price(...)` nếu nó có nguy cơ thực tế (ví dụ gọi dịch vụ giá qua mạng, cache miss, I/O), không phải vì nó cũng là method.

Có sự khác biệt:

- **HTTP boundary** cho phép đánh giá trải nghiệm request **trong phạm vi server**.
- **Checkout boundary** cho phép đánh giá hoạt động nghiệp vụ; nó có thể được gọi từ HTTP, batch job hay message consumer.
- **Dependency boundary** cho phép xác định latency/error do một dịch vụ hoặc database khác gây ra.
- **Lời gọi helper thuần CPU** thường có thể đo bằng profiler lấy mẫu khi cần, thay vì tạo hàng triệu span.

### 3.2. Entry/exit phải đúng một đơn vị công việc

Để đo thời lượng đồng bộ trong JVM, bắt đầu ngay trước operation và kết thúc ở mọi đường thoát:

~~~java
long started = System.nanoTime();
try {
    return operation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // Ghi một observation cho operation này.
}
~~~

Đây là **mảnh code minh họa**, không phải chương trình độc lập. `System.nanoTime()` là đồng hồ phù hợp để đo **khoảng thời gian tương đối trong cùng JVM**, không phải wall-clock timestamp; không dùng `System.currentTimeMillis()` để thay thế tùy tiện khi đo elapsed time.

Cần chọn chính xác thời điểm bắt đầu/kết thúc:

- Đo `PaymentGateway.charge(...)` bao gồm thời gian code caller thực sự nằm trong phương thức call đó, nhưng **không** tự bao gồm mọi retry nằm bên ngoài hoặc queue wait trước đó.
- Nếu một operation trả `CompletableFuture` ngay lập tức, timer quanh **lời gọi tạo future** chỉ đo thời gian *lập lịch*, không đo cho đến khi công việc async hoàn thành. Muốn đo end-to-end asynchronous operation phải đóng span/ghi observation khi future kết thúc (và xử lý hoàn tất exceptional/cancellation).
- Với stream, consumer hay message processing, xác định "completed" là nhận xong message, xử lý business logic, hay **acknowledge thành công**. Nếu không thống nhất, hai nhóm có thể đo cùng một operation nhưng được hai ý nghĩa khác nhau.
- Đối với exception, `finally` giúp ghi một lần quan sát khi operation thoát vì lỗi. Trạng thái `success` phải dựa trên ngữ nghĩa nghiệp vụ, không tự động coi mọi exception là HTTP 500.

### 3.3. Đừng tự gây đếm trùng

Nếu một request gọi `CheckoutService.checkout` rồi bên trong gọi `PaymentGateway.charge`, duration của cả hai **lồng nhau**. Không cộng hai duration thành "tổng thời gian request" vì sẽ **đếm trùng khoảng thời gian**. Tracing thể hiện quan hệ cha/con; metric riêng của từng operation phải được phân tích theo tên operation và boundary.

Tương tự, ghi cùng exception ở HTTP filter, controller, service, repository và interceptor có thể tạo nhiều log cho **một lỗi duy nhất**. Cần xác định tầng chịu trách nhiệm ghi log cuối cùng, và dùng trace correlation khi cần tìm đường đi thay vì sao chép stack trace khắp nơi.

## 4. Chọn signal đúng mục tiêu: metrics, traces, logs hay profiler?

| Tín hiệu | Trả lời tốt | Giá trị/giới hạn |
| --- | --- | --- |
| **Metrics** (counter, histogram, gauge) | Xu hướng, SLI/SLO, tỷ lệ lỗi, p95/p99 theo route/operation | Chi phí thường thấp nếu nhãn được giới hạn; không chỉ rõ từng lời gọi trong một request |
| **Traces** (root span + span con) | Lời gọi nào chậm, thứ tự dependency, các retry | Phải truyền context đúng qua thread/async; quá nhiều span làm tăng chi phí |
| **Structured logs** | Ngữ cảnh một sự kiện bất thường, loại lỗi, quyết định fallback | Tránh log mỗi method và log dữ liệu nhạy cảm; có thể gắn trace ID |
| **Profiler/JFR** | Hot method, allocation, lock contention, CPU/GC | Hợp với khám phá bottleneck không biết trước; không phải lúc nào có semantics nghiệp vụ |

Một câu hỏi cụ thể có thể cần **kết hợp tín hiệu**:

- SLI "p95 checkout" → metric histogram theo route hoặc operation.
- Biết p95 tăng nhưng không biết vì sao → trace ở checkout và dependency nghi ngờ.
- Biết payment timeout → một log đủ bối cảnh tại điểm xử lý lỗi, liên kết trace.
- Biết CPU tăng trong request → CPU allocation profile/JFR để tìm hot path trước khi thêm thêm instrumentation.

**Lấy mẫu có mục đích:** metric dùng cho rate/error SLI thường cần đếm đủ hoặc có cơ chế hiệu chỉnh thống kê rõ ràng. Trace chi tiết có thể lấy mẫu, đôi khi ưu tiên giữ trace lỗi/chậm theo chính sách phù hợp. Không dùng một tập trace được sampling tùy ý để tuyên bố là tỷ lệ lỗi chính xác của toàn bộ traffic.

**Nhãn/attributes có cardinality thấp:** nhóm theo `http.route="/orders/{id}"` hoặc `operation="checkout"`; không tạo series cho mỗi `orderId`, `userId`, request ID hay raw URL. Lỗi nên phân nhóm thành `timeout`, `rejected`, `invalid_input` hoặc exception class đã kiểm soát, không lấy toàn bộ message chứa thông tin tùy biến. Thư viện monitoring có thể có **giới hạn cardinality**, nhưng giới hạn đó không làm nhãn không phù hợp trở nên hữu ích.

## 5. Chọn một tập điểm đo tối thiểu và mở rộng theo bằng chứng

Một quy trình có thể áp dụng cho mỗi yêu cầu observability:

1. **Viết câu hỏi vận hành** và mức độ chính xác cần thiết: "p95 ở route checkout tăng do payment hay do tính toán nội bộ?" chứ không phải "ghi thời gian mọi method".
2. **Vẽ đường thực thi tối giản** của công việc: entry, operation, những dependency có tác động lớn, queue boundaries, exit. Chỉ cần bản đồ trách nhiệm, chưa cần call graph đầy đủ.
3. **Chọn 1–3 điểm đo ưu tiên** cho giả thuyết đầu: HTTP request boundary, checkout operation và dependency thanh toán. Cố ý ghi những điểm **không** instrument ở vòng này.
4. **Định nghĩa tên signal, nhãn, outcome và thời điểm ghi**: `checkout.duration`, `checkout.result`, `payment.attempts`; nhãn theo mã nghiệp vụ giới hạn thay vì ID người dùng.
5. **Ước tính overhead/cardinality**: số invocation/s, clock reads, đối tượng tạo thêm, bytes xuất, retry export, số series/span và khả năng backpressure. Gắn ngưỡng quan sát và phương án tắt.
6. **Kiểm chứng semantics với test**: một operation thành công, một exception, retry, concurrency và asynchronous completion nếu có. Xác nhận đúng số observation, không đổi kết quả nghiệp vụ và không rò dữ liệu.
7. **Đưa lên canary** rồi so sánh độ trễ, CPU, allocation, memory, export queue và lượng telemetry. Chỉ mở rộng phạm vi khi dữ liệu mới tạo thêm khả năng chẩn đoán có thể hành động.
8. **Dừng khi câu hỏi được trả lời**: không thêm instrument cho `equals`/getter chỉ vì có thể.

Ví dụ, nếu checkout span tăng nhưng payment span không tăng, giả thuyết "gateway chậm" yếu đi. Sau đó có thể đo chỗ chờ pool, transaction lock hoặc allocation trong checkout. Cách làm này tiết kiệm và chống nhiễu hơn việc biến mọi method thành một span.

## 6. Ví dụ Java 17+ chạy được: instrument đúng một operation

Ví dụ sau dùng **startup Java agent có `ClassFileTransformer` thật**. Để không phụ thuộc Byte Buddy/ASM trong bài học, ta chuẩn bị **hai phiên bản có cùng cấu trúc** của `CheckoutService.class` bằng `javac`:

- Bản gốc: thực hiện logic checkout, **không ghi metrics**.
- Bản được instrument: có **thêm một phép đo bao quanh `checkout()`**; không sửa `Catalog.price()` hay `PaymentGateway.charge()`.

Transformer chỉ thay bytes khi JVM định nghĩa class tên `CheckoutService`. Đây là cách thử **chọn điểm đo** trên một class cụ thể; trong agent production, transformer thường tạo bytecode hợp lệ bằng thư viện bytecode và lọc **đúng method + descriptor** trong class, thay vì nạp cả một class file thay thế có sẵn.

Thí nghiệm có thể chạy bằng JDK 17+ và **không cần dependency ngoài JDK**.

### 6.1. Tạo logic nghiệp vụ gốc

**`Catalog.java`**

~~~java
public final class Catalog {
    public int price(String sku) {
        return switch (sku) {
            case "book" -> 1200;
            case "desk" -> 3500;
            default -> throw new IllegalArgumentException("unknown sku");
        };
    }
}
~~~

**`PaymentGateway.java`**

~~~java
public final class PaymentGateway {
    public void charge(int cents) {
        if (cents <= 0) throw new IllegalArgumentException("invalid amount");
    }
}
~~~

Hai lớp này chỉ giả lập dependency đồng bộ. Không có mạng, database hoặc thanh toán thật; thời lượng đo nếu hiển thị sẽ phản ánh code của thí nghiệm, **không được dùng như benchmark độ trễ thanh toán**.

**`CheckoutService.java`** đặt trong thư mục gốc:

~~~java
public final class CheckoutService {
    private final Catalog catalog = new Catalog();
    private final PaymentGateway payment = new PaymentGateway();

    public void checkout(String sku) {
        int cents = catalog.price(sku);
        payment.charge(cents);
    }
}
~~~

Ở giai đoạn đầu, **không instrument `price` hoặc `charge`**. Câu hỏi ban đầu là "bao nhiêu checkout thành công/thất bại trong boundary nghiệp vụ?" — đo một lần ở `checkout` là đủ.

### 6.2. Xây một bộ tổng hợp phép đo đơn giản

**`Measurements.java`**

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public final class Measurements {
    private static final AtomicInteger successes = new AtomicInteger();
    private static final AtomicInteger failures = new AtomicInteger();
    private static final LongAdder durationNanos = new LongAdder();

    private Measurements() {}

    public static void record(String operation, boolean success, long elapsedNanos) {
        if (!"checkout".equals(operation)) return;
        if (success) successes.incrementAndGet();
        else failures.incrementAndGet();
        durationNanos.add(elapsedNanos);
    }

    public static int successCount() { return successes.get(); }
    public static int failureCount() { return failures.get(); }
    public static long totalDurationNanos() { return durationNanos.sum(); }
}
~~~

`AtomicInteger` và `LongAdder` phục vụ thí nghiệm thread-safe đơn giản; `durationNanos` chỉ lưu **tổng thời lượng**, nên **không thể tính p95** từ đây. Trong ứng dụng thực, dùng histogram có giới hạn cardinality và exporter/sampling phù hợp. Bộ đếm trong demo không có nhãn user ID hoặc SKU để tránh các series quá nhiều chiều.

**`instrumented/CheckoutService.java`** đặt trong thư mục con `instrumented`:

~~~java
public final class CheckoutService {
    private final Catalog catalog = new Catalog();
    private final PaymentGateway payment = new PaymentGateway();

    public void checkout(String sku) {
        long started = System.nanoTime();
        boolean success = false;
        try {
            int cents = catalog.price(sku);
            payment.charge(cents);
            success = true;
        } finally {
            Measurements.record("checkout", success, System.nanoTime() - started);
        }
    }
}
~~~

Đây là phiên bản **class file thay thế**, không được khai báo thêm vào cùng thư mục classpath của ứng dụng. Vì `record` nằm trong `finally`, cả nhánh thành công lẫn exception từ `Catalog.price` đều tạo **một observation**. Exception nghiệp vụ không bị `catch` và vẫn được truyền ra caller.

Trong production, telemetry hook cũng cần có cơ chế để lỗi từ exporter hoặc thư viện observability **không vô tình che exception nghiệp vụ**, và nên tránh I/O đồng bộ trong hot path. Bài thực hành dùng atomic counter trong cùng JVM nên không phát sinh export network.

### 6.3. Viết transformer chỉ chọn một class mục tiêu

**`SelectiveTransformer.java`**

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class SelectiveTransformer implements ClassFileTransformer {
    private final byte[] checkoutBytes;

    public SelectiveTransformer(byte[] checkoutBytes) {
        this.checkoutBytes = checkoutBytes.clone();
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
                            Class<?> beingRedefined, ProtectionDomain domain,
                            byte[] classfileBuffer) {
        if (!"CheckoutService".equals(className)) return null;
        System.out.println("instrumented=CheckoutService");
        return checkoutBytes.clone();
    }
}
~~~

Bộ lọc **chỉ** khớp tên JVM internal name `CheckoutService`; các class khác đi qua `return null`. Đối với class trong package `com.shop.service`, tên callback thường là `com/shop/service/CheckoutService`, không phải `com.shop.service.CheckoutService`.

**Quan trọng:** ví dụ chỉ có một class loader mặc định và hai bản class cùng tên/cùng member layout. Trong app nhiều class loader/module, không nên trả một class file thay thế cho bất kỳ loader nào có cùng tên; cần lọc class loader/module/phiên bản class và method descriptor khi cần. Một transformer cũng không nên tự instrument class helper của nó, để tránh class-loading recursion.

**`SelectionAgent.java`**

~~~java
import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SelectionAgent {
    public static void premain(String args, Instrumentation inst) throws IOException {
        byte[] checkoutBytes = Files.readAllBytes(Path.of("instrumented/CheckoutService.class"));
        inst.addTransformer(new SelectiveTransformer(checkoutBytes));
    }
}
~~~

Agent đọc bytes **trước khi đăng ký**, để callback chỉ kiểm tra tên class và trả byte array. Không cần `Can-Retransform-Classes` cho ví dụ vì lớp checkout được nạp **sau `premain`**, ở lần định nghĩa đầu tiên. Đường dẫn `instrumented/CheckoutService.class` là đường dẫn tương đối từ **working directory khi chạy `java`**.

**`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: SelectionAgent
~~~

Manifest cần có dấu xuống dòng cuối, nên lưu đúng định dạng văn bản JAR manifest.

### 6.4. Chương trình kiểm chứng số observation

**`App.java`**

~~~java
public final class App {
    public static void main(String[] args) {
        CheckoutService checkout = new CheckoutService();
        checkout.checkout("book");
        checkout.checkout("desk");
        try {
            checkout.checkout("missing");
        } catch (IllegalArgumentException expected) {
            System.out.println("business_error=" + expected.getMessage());
        }
        System.out.println("success_count=" + Measurements.successCount());
        System.out.println("failure_count=" + Measurements.failureCount());
    }
}
~~~

Ta có **hai giao dịch hợp lệ** và **một giao dịch lỗi**. Nếu điểm đo được đặt đúng, kết quả phải là **2 successes, 1 failure** — dù `Catalog.price()` và `PaymentGateway.charge()` được gọi nhiều lần. Đây là kiểm thử quan trọng: tổng observation tương ứng **operation**, không phải tổng số method invocation.

### 6.5. Biên dịch và chạy có/không có agent

Từ thư mục gốc chứa `Catalog.java`, `PaymentGateway.java`, `CheckoutService.java`, `Measurements.java`, `App.java`, `SelectiveTransformer.java`, `SelectionAgent.java`, `agent.mf`, và thư mục `instrumented/CheckoutService.java`:

~~~bash
javac --release 17 Catalog.java PaymentGateway.java CheckoutService.java Measurements.java App.java SelectiveTransformer.java SelectionAgent.java

javac --release 17 -classpath . -d instrumented instrumented/CheckoutService.java

jar --create --file selection-agent.jar --manifest agent.mf SelectionAgent.class SelectiveTransformer.class

java App
java -javaagent:selection-agent.jar App
~~~

Lệnh `javac --release 17` đảm bảo dùng cú pháp và classfile tương thích Java 17. Chỉ sử dụng **`CheckoutService.class` bản gốc** ở classpath ứng dụng; bản thay thế ở `instrumented/` được agent đọc như dữ liệu. JAR agent phải chứa **`SelectionAgent.class`** và **`SelectiveTransformer.class`**.

**Chạy không có agent**, stdout:

~~~text
business_error=unknown sku
success_count=0
failure_count=0
~~~

Đây là baseline: ứng dụng vẫn thực thi checkout và bắt đúng lỗi nghiệp vụ, nhưng lớp `CheckoutService` gốc **không ghi telemetry**.

**Chạy với agent**, stdout:

~~~text
instrumented=CheckoutService
business_error=unknown sku
success_count=2
failure_count=1
~~~

Cặp kết quả này được biên dịch với `javac --release 17` và chạy trên OpenJDK 21. Nếu bạn chạy với JDK/JVM khác, đường dẫn làm việc sai hoặc class đã được nạp trước agent, kết quả có thể khác; kiểm tra chính xác bytecode và command line trước khi kết luận.

### 6.6. Vì sao ví dụ chứng minh chọn điểm đo theo câu hỏi?

| Điều đã kiểm chứng | Ý nghĩa đối với thiết kế |
| --- | --- |
| Chỉ thấy `instrumented=CheckoutService` | Transformer tập trung vào **một class**, không cố biến đổi mọi class trong JVM |
| Đếm được `success_count=2` và `failure_count=1` | Điểm đo ở boundary checkout phù hợp câu hỏi "bao nhiêu operation thành công/thất bại?" |
| Lỗi `unknown sku` xuất hiện trong cả hai chế độ | Thêm đo đạc không tự thay đổi semantics exception trong bài thực hành |
| Không có log `instrumented=Catalog` hoặc `instrumented=PaymentGateway` | Không phải chèn vào helper mới trả lời được câu hỏi ban đầu |
| Chỉ lưu tổng nanos trong demo | Cần chuyển sang histogram nếu câu hỏi thực là **p95 latency**, thay vì tuyên bố tính p95 từ một tổng số |

Ví dụ dùng **class file biến thể đã biên dịch** để dễ kiểm chứng cơ chế, không minh họa đầy đủ một pipeline ASM/Byte Buddy. Trong agent thực, ưu tiên patch đúng method trên class bytes đầu vào thay vì thay cả class bằng file có sẵn.

## 7. Chọn lớp và phương thức an toàn khi dùng `ClassFileTransformer`

### 7.1. Hai tầng lọc

Để giảm chi phí và tránh instrument nhầm:

**Tầng 1 — trong callback class**: kiểm tra module, loader, `className`, namespace và danh sách class loại trừ. Với lớp không liên quan, `return null` ngay. Đừng parse bytecode của mọi class nếu chỉ theo dõi một operation.

**Tầng 2 — sau khi chọn class**: thư viện bytecode chỉ chọn đúng **method name + descriptor** và ràng buộc cần thiết (ví dụ `checkout(Ljava/lang/String;)V`), tránh match toàn bộ overload cùng tên. Kiểm tra method đã được instrument chưa, tránh chèn hai lần ở các lượt retransform/redefine.

~~~text
ClassFileTransformer.transform(...)
    |
    +-- className không thuộc allowlist --> return null
    |
    +-- agent/library/framework helper --> return null
    |
    +-- loader/module không đúng --> return null
    |
    +-- parse đúng class được chọn
            |
            +-- method name + descriptor cần đo?
            |       |
            |       +-- Không --> giữ method nguyên
            |       +-- Có --> chèn start/end/outcome hook hợp lệ
            |
            +-- trả bytes mới nếu class thực sự đổi
~~~

Java Instrumentation không tự cung cấp matcher method-level trong `transform`; callback nhận **class-file bytes**. Muốn can thiệp method, transformer phải phân tích/sinh classfile hợp lệ hoặc dùng thư viện hỗ trợ tương thích JDK.

### 7.2. Lọc đúng ngữ cảnh

- **Class loader:** cùng internal class name có thể được định nghĩa bởi nhiều loader; một chính sách cho service A không tự động hợp lệ cho service B.
- **Module:** trong ứng dụng JPMS, kiểm tra module và khả năng đọc/truy cập class helper khi bytecode mới gọi chúng; việc loader nhìn thấy class chưa bảo đảm module access đúng.
- **Lifecycle:** startup agent có thể bắt lớp ngay khi định nghĩa; dynamic attach có thể đến sau khi class đã load. Đối với lớp đã load, cần khả năng retransformation/redefinition tương ứng, kiểm tra `isModifiableClass` và giới hạn thay đổi cấu trúc.
- **Canary/filter:** allowlist theo service/route/operation hay tỷ lệ sampling phải độc lập với business input nhạy cảm. Nên có khả năng tắt riêng một loại hook để giảm overhead khi sự cố.
- **Lỗi callback:** transformer tạo classfile không hợp lệ có thể làm lớp không nạp được; thử với đủ JDK và bytecode patterns thực tế. Không chỉ test giá trị counter mà bỏ qua startup/class loading.

## 8. Chi phí, cardinality và những điểm đo cần tránh

Mỗi điểm đo đều có giá: đọc đồng hồ, nhánh điều kiện, context propagation, cấp phát đối tượng, cập nhật atomic, lưu trace, flush exporter và truy vấn backend. Đặc biệt, **chi phí trên một invocation nhỏ** có thể trở thành đáng kể khi method nằm trong hot loop; số lượng method được instrument **không phản ánh trực tiếp** tổng overhead bằng tần suất gọi.

Các tín hiệu cảnh báo:

- Instrument mọi getter/constructor tạo ra hàng chục triệu events dù câu hỏi chỉ liên quan một HTTP request.
- Ghi span cho một phép toán thuần CPU rất ngắn dẫn tới nhiều span không mang ý nghĩa nghiệp vụ.
- Gắn metric labels bằng `orderId`, raw URL, token, email hoặc request ID tạo nhiều time series và nguy cơ lộ thông tin.
- Xuất telemetry đồng bộ trên request thread làm ảnh hưởng chính latency đang cần đo; exporter bị chậm có thể tạo feedback loop.
- Ghi exception ở mọi tầng vừa tốn tài nguyên vừa khiến một lỗi trông như nhiều sự cố.
- Dùng timer quanh `CompletableFuture.supplyAsync(...)` rồi kết luận đó là thời gian xử lý async thực tế.
- Đo nhiều khoảng thời gian lồng nhau rồi cộng trực tiếp thành end-to-end latency.

**Phương án an toàn:** ưu tiên counters/histograms ít nhãn, tracing theo các span có ngữ nghĩa, queue/exporter có giới hạn, sampling có chủ đích và profiling khi cần khám phá CPU path. Nếu vẫn chưa có câu hỏi đủ rõ, đo ở một số boundary ổn định rồi khai thác profiler/JFR để tạo giả thuyết trước khi chèn thêm.

**Đo overhead thực tế:** so sánh canary bật/tắt instrumentation ở cùng traffic và cùng JVM, kiểm tra p50/p95/p99, CPU, allocation, GC, memory, số span/metric series, queue lag và drop rate. Đừng lấy `elapsedNanos` của chính hot hook làm toàn bộ bằng chứng về overhead hệ thống: bật agent có thể làm thay đổi JIT, allocation và backpressure.

## 9. Kiểm tra tính đúng đắn trước khi triển khai

| Khía cạnh | Bài test tối thiểu | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| **Semantics** | Success và exception đều giữ nguyên business behavior | Hook che lỗi gốc hoặc thay giá trị trả về |
| **Counting** | Một checkout tạo đúng một observation; retry được xác định rõ | Số metric không tương ứng số operation |
| **Boundary** | Phân biệt HTTP end-to-end, checkout, payment call, queue wait | Đổ sai trách nhiệm khi latency tăng |
| **Async** | Kiểm thử thành công, thất bại và cancel future | Span đóng quá sớm hoặc rò span/context |
| **Concurrency** | Nhiều thread tăng counter đúng; không dùng state request toàn cục | Đếm sai hoặc lẫn dữ liệu giữa requests |
| **Labels** | Allowlist giá trị route/outcome; không có ID/PII | High cardinality và rủi ro quyền riêng tư |
| **Lọc class** | Đúng internal class name, loader, module, method descriptor | Instrument nhầm lớp hoặc lỗi linkage |
| **Startup/lifecycle** | Agent load được, helper class sẵn, rollback/toggle hoạt động | JVM không khởi động hoặc khó tắt hook |
| **Cost** | A/B canary trên workload và JDK đích | Đo đạc làm latency xấu đi |
| **Quan sát tín hiệu** | Có dashboard truy vấn được theo operation và outcome | Có events nhưng vẫn không trả lời được câu hỏi |

Cần nhớ **không phải metric, span hay log nào cũng do một `ClassFileTransformer` chèn vào**. Java agent có thể instrument framework boundary, dùng JFR/JMX, đăng ký listener hay dùng API telemetry của ứng dụng. Cách chọn điểm đo luôn xuất phát từ câu hỏi và semantics; công nghệ cài điểm đo đến sau.

## 10. Bài tập suy luận và quyết định

**Tình huống A — "p95 request tăng":** Bạn có 300 method và được phép thêm đúng ba điểm đo ban đầu. Chọn gì?

Một hướng hợp lý: HTTP server duration theo route, operation nghiệp vụ chính, dependency nghi ngờ nhất. Nếu request có queue trước khi đến handler thì queue wait là một ứng viên mạnh. Không khẳng định mọi hệ thống đều có đúng ba boundary này; điểm đo cuối cùng dựa vào sơ đồ thực tế.

**Tình huống B — "một giao dịch có sáu helper method":** Nếu một checkout gọi sáu helper đồng bộ, bạn có cần sáu metric observations cho "số checkout thành công" không?

Không. Ghi **một outcome ở boundary checkout**. Đếm helper invocation trả lời một câu hỏi khác và có thể làm phóng đại kết quả nếu được hiểu thành số giao dịch.

**Tình huống C — "đã biết checkout chậm nhưng không rõ thành phần":** Nên thêm mọi method hay một span có chọn lọc cho `PaymentGateway.charge` và điểm chờ DB?

Thêm các boundary có giả thuyết và có khả năng thay đổi quyết định vận hành. Nếu kết quả vẫn chưa đủ, tiếp tục thu hẹp bằng profiler hoặc các điểm đo bổ sung.

**Tình huống D — "API dùng async":** Timer bao quanh call tạo future ghi 2 ms; future hoàn tất sau 700 ms. Có thể báo latency nghiệp vụ 2 ms không?

Không, nếu câu hỏi là thời gian đến lúc operation hoàn tất. Phải đo đến completion/cancellation và truyền context qua async boundary.

**Tình huống E — "metric quá nhiều series":** Một metric chứa `http.route` và `userId`, với userId khác nhau liên tục. Nên thêm logging ở mọi method để debug?

Không. Loại nhãn high-cardinality khỏi metric, dùng route template và outcome ổn định, rồi dùng trace theo sampling và log có trace ID khi điều tra một request cụ thể; tuyệt đối không xuất thông tin bí mật chỉ vì muốn tăng tính chi tiết.

## 11. Checklist chọn điểm đo trong Java agent

- [ ] Câu hỏi có thể viết thành **một câu ngắn**, có hành động nếu câu trả lời là A/B?
- [ ] Chỉ ra đúng **đơn vị đo**: request, checkout, dependency call, queue wait hay message processing?
- [ ] Biết chính xác **khi nào operation bắt đầu và kết thúc**, gồm exception, retry và async?
- [ ] Biết tín hiệu nào phù hợp: metric, trace, log, JFR/profiler; không bắt mọi tín hiệu phát sinh từ một timer?
- [ ] Chọn tập điểm đo ít nhất để phân biệt các giả thuyết có ý nghĩa?
- [ ] Nhãn/attributes có giới hạn, không chứa ID hoặc dữ liệu nhạy cảm?
- [ ] Có filter class/module/loader và method descriptor khi áp dụng `ClassFileTransformer`?
- [ ] Có test startup, classfile hợp lệ, code equivalence, concurrency, rollback?
- [ ] Có kế hoạch đo overhead và tắt hook trong production?
- [ ] Mỗi chỉ số và span đều gắn với **một câu hỏi vận hành cụ thể**?

**Kết luận:** Instrumentation chất lượng không phải là "nhiều method được biến đổi" mà là **ít điểm đo nhất vẫn cho đủ thông tin để ra quyết định đúng**. Bắt đầu từ câu hỏi, chọn boundary, xác định semantics, kiểm chứng qua output và mở rộng khi có bằng chứng cần thêm dữ liệu.

### Tài liệu tham khảo

- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hợp đồng callback và classfile bytes.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký/gỡ transformer và khả năng redefine/retransform.
- [OpenTelemetry — HTTP span semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/): naming theo route template và boundary HTTP.
- [OpenTelemetry — Metrics overview](https://opentelemetry.io/docs/concepts/signals/metrics/): giá thành metric, cardinality và các cơ chế giảm cardinality.
- [OpenTelemetry — Metrics SDK specification](https://opentelemetry.io/docs/specs/otel/metrics/sdk/): attribute filtering và giới hạn số metric data point.
