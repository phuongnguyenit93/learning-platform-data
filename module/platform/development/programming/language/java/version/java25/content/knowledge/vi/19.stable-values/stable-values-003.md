# Đảm bảo khởi tạo một lần và công bố an toàn với Lazy Constants

> **Chương:** Stable Values  
> **Học phần:** `JAVA_VERSION_JAVA25` — khám phá các tính năng Java hiện đại còn áp dụng, gồm khởi tạo an toàn, khả năng đồng thời, tối ưu JVM và các API preview đã tiếp tục phát triển sau Java 25.  
> **Mục tiêu:** Hiểu ý tưởng “tạo giá trị khi cần, sau đó giữ nguyên suốt vòng đời”; nắm cách `LazyConstant` bảo đảm chỉ một thread khởi tạo và công bố an toàn cho các thread khác; phân biệt tính bất biến của holder với tính bất biến của object được giữ; biết giới hạn của preview API và lựa chọn thay thế ổn định cho production.

> **Cập nhật phiên bản:** Tên “Stable Values” chỉ là tên của preview đầu tiên trong JDK 25. Từ JDK 26, tính năng được đổi tên thành **Lazy Constants** và API `StableValue` cũ không còn là API hiện hành. Bài học dùng tên và API `LazyConstant` của các JDK mới; không dùng lại các method preview cũ.

## 1. Bài toán: tạo một giá trị một lần nhưng không muốn khởi tạo quá sớm

Ứng dụng thường có các object được dùng nhiều lần và có chi phí tạo đáng kể:

- Cấu hình đã được phân tích từ file hoặc environment.
- Bộ phân tích biểu thức, schema hoặc metadata.
- Bộ định dạng, serializer hoặc mapper.
- Client kết nối tới dịch vụ bên ngoài.
- Một graph object được xây từ nhiều thành phần.
- Logger hoặc thành phần phụ trợ chỉ cần khi một chức năng được gọi.

Nếu tạo tất cả object ngay khi ứng dụng khởi động, thời gian startup và lượng bộ nhớ ban đầu có thể tăng dù một số chức năng chưa bao giờ được dùng. Nếu trì hoãn bằng một field mutable và tự viết kiểm tra `null`, cần xử lý nhiều thread cùng truy cập để tránh tạo trùng hoặc đọc một object chưa được công bố an toàn.

Ví dụ cách viết ngây thơ:

```java
final class PricingService {
    private PricingRules rules;

    PricingRules rules() {
        if (rules == null) {
            rules = loadRules();
        }
        return rules;
    }
}
```

Nếu hai thread gọi `rules()` cùng lúc, cả hai có thể thấy `rules == null` và cùng gọi `loadRules()`. Một thread có thể trả về object trong khi trạng thái khởi tạo của nó chưa được công bố an toàn cho thread khác. Field mutable cũng làm compiler khó xem giá trị là một hằng số sau khi đã khởi tạo.

Bài toán thực sự gồm ba yêu cầu:

1. **Lazy:** chỉ tạo object khi có người cần dùng.
2. **At most once:** dù nhiều thread truy cập đồng thời, chỉ một lần tính toán được chấp nhận.
3. **Safe publication và stable reference:** sau khi hoàn tất, mọi thread đọc được cùng giá trị đã khởi tạo; holder không thay nội dung bằng giá trị khác.

Lazy Constants được thiết kế cho mô hình này.

## 2. Từ Stable Values đến Lazy Constants: tên gọi và API đã thay đổi

JEP 502 giới thiệu **Stable Values** dưới dạng preview trong JDK 25. Sau vòng preview đầu tiên, API được thiết kế lại và đổi tên thành **Lazy Constants** từ JDK 26.

| JDK | JEP | Tên / trạng thái | Điều cần nhớ |
|---|---|---|---|
| JDK 25 | JEP 502 | Stable Values, preview lần đầu | API thử nghiệm ban đầu; không dùng làm API hiện hành |
| JDK 26 | JEP 526 | Lazy Constants, preview lần hai | Đổi tên type thành `LazyConstant`; dùng `of(Supplier)` và `get()` |
| JDK 27 | JEP 531 | Lazy Constants, preview lần ba | Bỏ `isInitialized()` và `orElse()`; bổ sung `Set.ofLazy(...)` trong Collections API liên quan |
| JDK 28 EA | JEP 547 | Lazy Constants, preview lần bốn | Vẫn là preview; chưa phải API final |

Tại thời điểm biên soạn, JDK 27 là bản GA mới nhất. JDK 28 đang ở Early Access và JEP 547 đưa Lazy Constants vào vòng preview thứ tư. Vì vậy, `LazyConstant` là hướng API đang được phát triển, nhưng vẫn cần bật preview khi biên dịch và chạy.

**Không sao chép code Stable Values từ JDK 25** vào dự án JDK mới. Các kiểu và method preview cũ như `StableValue`, `orElseSet`, `orElse` hoặc các cách kiểm tra trạng thái trước đây không đại diện cho API Lazy Constants hiện hành.

## 3. LazyConstant là gì?

`java.lang.LazyConstant<T>` là một holder chứa một giá trị được tính toán muộn. Tạo holder chưa làm chạy computing function. Lần đầu gọi `get()`, function được thực thi và kết quả trở thành nội dung của lazy constant. Những lần `get()` sau nhận lại cùng nội dung.

API hiện hành có hai điểm chính:

- `LazyConstant.of(Supplier<? extends T>)`: tạo holder và cung cấp function để tính nội dung.
- `get()`: lấy nội dung; nếu chưa được khởi tạo, thực hiện việc khởi tạo trước khi trả về.

Ví dụ:

```java
import java.lang.LazyConstant;

final class PricingService {
    private final LazyConstant<PricingRules> rules =
            LazyConstant.of(PricingService::loadRules);

    PricingRules rules() {
        return rules.get();
    }

    private static PricingRules loadRules() {
        return PricingRules.loadFromConfiguration();
    }
}
```

Khi tạo `PricingService`, holder `rules` được tạo nhưng `loadRules()` chưa chạy. Khi method `rules()` được gọi lần đầu, `get()` khởi tạo nội dung. Các lần gọi sau nhận cùng một giá trị đã được thiết lập.

`LazyConstant` triển khai `Supplier<T>`, nhưng có semantics mạnh hơn một `Supplier` thông thường: nội dung được khởi tạo tối đa một lần, không thể thay bằng nội dung khác và được công bố an toàn cho các thread đọc.

### 3.1. Holder được tạo trước, content được tạo sau

```text
new PricingService()
       |
       v
LazyConstant<PricingRules> được tạo
       |
       | chưa chạy loadRules()
       |
       v
Thread đầu tiên gọi rules.get()
       |
       v
Chạy computing function đúng một lần
       |
       v
Công bố nội dung đã khởi tạo
       |
       +------ Thread A: nhận PricingRules
       |
       +------ Thread B: nhận cùng PricingRules
       |
       +------ Thread C: nhận cùng PricingRules
```

Holder và nội dung là hai đối tượng khác nhau. Việc tạo holder có thể xảy ra lúc tạo service; nội dung chỉ xuất hiện khi được yêu cầu.

## 4. Khởi tạo đồng thời: nhiều thread tranh nhau nhưng chỉ một thread tính toán

Một trong những bảo đảm quan trọng của Lazy Constants là **atomic initialization at most once**.

Giả sử nhiều request cùng gọi `rules.get()` trong thời điểm đầu tiên:

1. Các thread cùng quan sát một lazy constant chưa có content.
2. JVM chọn một trong các thread gọi `get()` thực hiện computing function ngay trên thread đó; LazyConstant không tự tạo worker thread.
3. Những thread còn lại chờ kết quả khởi tạo.
4. Khi function hoàn tất thành công, content được công bố.
5. Những thread đang chờ và các thread gọi sau đó nhận cùng content.
6. Computing function không được gọi lại cho holder đó.

Ví dụ:

```java
import java.lang.LazyConstant;
import java.util.concurrent.atomic.AtomicInteger;

final class SharedSchema {
    private static final AtomicInteger COMPUTATIONS =
            new AtomicInteger();

    private static final LazyConstant<Schema> SCHEMA =
            LazyConstant.of(() -> {
                COMPUTATIONS.incrementAndGet();
                return Schema.load();
            });

    static Schema get() {
        return SCHEMA.get();
    }

    static int computationCount() {
        return COMPUTATIONS.get();
    }
}
```

Dù 100 thread đồng thời gọi `SharedSchema.get()`, computing function chỉ được thực thi một lần nếu khởi tạo thành công. `computationCount()` là công cụ minh họa/test; không cần thêm bộ đếm vào code production chỉ để kiểm tra lazy initialization.

### 4.1. At most once không phải exactly once cho mọi side effect

Bảo đảm at most once áp dụng cho computing function của **một holder trong vòng đời của holder đó**. Nó không biến mọi thao tác bên ngoài thành một giao dịch exactly-once.

Nếu function gọi API thanh toán, gửi email hoặc ghi dữ liệu từ xa, hãy nhớ rằng:

- Function có thể thất bại sau khi hệ thống bên ngoài đã thực hiện side effect.
- Lazy constant chuyển sang error state; nó không tự retry function.
- Tạo một holder mới sẽ tạo một chu kỳ khởi tạo mới.
- Exactly-once cho hệ thống ngoài cần idempotency key, transaction hoặc cơ chế xử lý riêng.

Vì vậy, computing function phù hợp nhất với việc tạo một giá trị dùng chung trong process, không phải workflow nghiệp vụ có side effect cần retry.

## 5. Công bố an toàn: happens-before và visibility

Thread-safety không chỉ là bảo đảm hai thread không cùng tạo object. Các thread đọc còn phải nhìn thấy đầy đủ trạng thái mà thread khởi tạo đã thiết lập trước khi công bố.

LazyConstant quy định rằng việc gọi computing function và hoàn tất khởi tạo xảy ra-trước (happens-before) việc đọc content đã khởi tạo. Vì vậy, các field đã được thiết lập trong object được công bố an toàn, bao gồm cả `final` fields của object vừa tạo.

Ví dụ:

```java
final class RoutingTable {
    private final Map<String, String> routes;
    private final int version;

    RoutingTable(Map<String, String> routes, int version) {
        this.routes = Map.copyOf(routes);
        this.version = version;
    }

    String destination(String key) {
        return routes.get(key);
    }

    int version() {
        return version;
    }
}

private static final LazyConstant<RoutingTable> ROUTES =
        LazyConstant.of(() -> new RoutingTable(loadRoutes(), 7));
```

Khi thread khác gọi `ROUTES.get()` và nhận object, nó nhìn thấy trạng thái đã được thiết lập trước khi initialization hoàn tất. Không cần tự thêm `volatile` cho một field nội dung nằm bên trong holder chỉ để công bố kết quả khởi tạo.

### 5.1. Happens-before không đồng nghĩa object mutable trở nên thread-safe

LazyConstant bảo đảm việc công bố ban đầu. Nó không tự đồng bộ các thay đổi được thực hiện **sau khi** object đã được trả về.

Ví dụ, nếu content là `ArrayList` và nhiều thread cùng thêm/xóa phần tử, ứng dụng vẫn cần collection concurrent, lock hoặc immutable snapshot. Holder không cho phép thay content bằng object khác; nó không tự khóa mọi thao tác trên content.

Hãy ưu tiên:

- Object bất biến, record với thành phần bất biến.
- `Map.copyOf`, `List.copyOf` hoặc collection immutable phù hợp.
- Cấu trúc concurrent khi nội dung cần cập nhật.
- Tách cấu hình immutable khỏi trạng thái runtime mutable.

Không diễn giải “LazyConstant thread-safe” thành “mọi object chứa trong LazyConstant đều thread-safe”.

## 6. Nội dung không thể là `null`

LazyConstant không cho phép computing function trả về `null`. Nếu function trả `null`, lần khởi tạo chuyển sang error state và `get()` ném `NoSuchElementException` với `NullPointerException` làm cause.

Nếu giá trị có thể không tồn tại, hãy biểu diễn trạng thái đó bằng `Optional<T>`:

```java
private static final LazyConstant<Optional<FeatureConfig>> FEATURE_CONFIG =
        LazyConstant.of(() -> findFeatureConfig());

static Optional<FeatureConfig> featureConfig() {
    return FEATURE_CONFIG.get();
}
```

Ở đây function phải trả về một `Optional` không null, có thể là `Optional.empty()`. Holder chứa một `Optional` hợp lệ, không chứa `null`.

Điều này giúp phân biệt rõ:

- Giá trị đã khởi tạo và có content.
- Giá trị đã khởi tạo nhưng biểu diễn “không có kết quả” bằng `Optional.empty()`.
- Holder đang ở error state do function thất bại.

## 7. Khi computing function thất bại: error state không tự retry

Nếu computing function ném unchecked exception (`RuntimeException` hoặc `Error`), LazyConstant chuyển sang error state. Nó không thử gọi function lại ở lần `get()` tiếp theo.

Theo API hiện hành:

- Lần truy cập gặp lỗi khởi tạo sẽ nhận `NoSuchElementException` với unchecked exception gốc làm cause.
- Các lần `get()` sau tiếp tục ném `NoSuchElementException`, không gọi lại function; cause ban đầu không được giữ như một lần retry.
- Nếu function trả `null`, error state có cause `NullPointerException`.
- Nếu function gọi đệ quy chính lazy constant đang được khởi tạo, lỗi được báo qua `NoSuchElementException` với `IllegalStateException` làm cause.

Ví dụ:

```java
private static final LazyConstant<RemoteConfig> CONFIG =
        LazyConstant.of(() -> {
            throw new IllegalStateException("Configuration source unavailable");
        });
```

Sau khi holder chuyển sang error state, gọi `CONFIG.get()` không làm function chạy lại. Đây là semantics khác với một cache có retry hoặc một `Supplier` tự viết.

### 7.1. Khi nào semantics này phù hợp?

Phù hợp khi:

- Giá trị được tính từ nguồn ổn định trong vòng đời process.
- Lỗi khởi tạo cần được coi là lỗi cấu hình hoặc lỗi triển khai.
- Ứng dụng có thể fail fast khi không tạo được giá trị bắt buộc.
- Không cần timeout hoặc retry nội bộ.

Không phù hợp khi:

- Dependency từ xa có thể tạm thời lỗi và cần retry.
- Giá trị cần refresh định kỳ.
- Kết quả phụ thuộc người dùng, tenant hoặc request.
- Có yêu cầu hủy computation khi thread bị interrupt.
- Giá trị cần được thay thế sau khi credential hoặc cấu hình rotate.

Trong các trường hợp đó, dùng abstraction có semantics retry, refresh, expiry hoặc cancellation phù hợp; đừng ép LazyConstant thành cache mutable.

## 8. Interrupt, blocking và vòng đời bộ nhớ

LazyConstant đảm bảo chỉ một thread thực hiện computing function. Những thread khác đang gọi `get()` có thể phải chờ cho tới khi khởi tạo thành công hoặc chuyển sang error state.

Có ba hệ quả vận hành quan trọng:

1. **Interrupt không hủy khởi tạo.** Nếu computing thread bị interrupt, `LazyConstant.get()` không xóa interrupt status và không ném `InterruptedException` chỉ vì bị interrupt.
2. **Không có timeout hoặc cancellation tích hợp.** Nếu computing function block vô thời hạn, các thread khác chờ cùng lazy constant cũng có thể block vô thời hạn.
3. **Content được giữ mạnh.** Sau khi khởi tạo, holder giữ tham chiếu mạnh tới content; không có API reset hoặc clear content.

Vì vậy, computing function nên ngắn gọn, có giới hạn thời gian cho I/O và tránh phụ thuộc vào một dịch vụ có thể treo vô thời hạn.

### 8.1. Không dùng LazyConstant làm connection pool hoặc cache có thể đóng/mở lại

Một database connection đơn lẻ hoặc socket được giữ trong LazyConstant có thể tồn tại lâu hơn vòng đời dự kiến và không có thao tác reset. Nếu cần quản lý resource, rotation, shutdown hoặc refresh, dùng lifecycle abstraction phù hợp như connection pool, client bean do container quản lý hoặc resource registry có close semantics.

LazyConstant phù hợp để giữ cấu hình đã parse, schema immutable hoặc một object dùng chung không cần refresh. Nó không thay thế lifecycle manager.

### 8.2. Tránh đồng bộ trực tiếp trên holder

Implementation được phép dùng chính LazyConstant làm monitor nội bộ. Không viết:

```java
synchronized (CONFIG) {
    // ...
}
```

Cũng tránh code gián tiếp khóa trên cùng object thông qua một callback hoặc utility. Việc dùng holder làm application lock có thể tạo lock contention hoặc deadlock với cơ chế đồng bộ bên trong implementation.

## 9. Nội dung có thể phụ thuộc LazyConstant khác

Một lazy constant có thể được tạo từ một lazy constant khác. Khi gọi `get()` trên constant phụ thuộc, các constant cần thiết được khởi tạo theo thứ tự dependency.

```java
import java.lang.LazyConstant;

final class ApplicationComponents {
    private static final LazyConstant<DatabaseConfig> DATABASE =
            LazyConstant.of(DatabaseConfig::load);

    private static final LazyConstant<Repository> REPOSITORY =
            LazyConstant.of(() -> new Repository(DATABASE.get()));

    private static final LazyConstant<OrderService> ORDER_SERVICE =
            LazyConstant.of(() -> new OrderService(REPOSITORY.get()));

    static OrderService orderService() {
        return ORDER_SERVICE.get();
    }
}
```

Khi gọi `orderService()` lần đầu:

1. `ORDER_SERVICE.get()` bắt đầu khởi tạo `OrderService`.
2. Computing function gọi `REPOSITORY.get()`.
3. `REPOSITORY` gọi `DATABASE.get()`.
4. Database config được tạo trước, sau đó repository, rồi service.
5. Các lần truy cập tiếp theo nhận lại cùng các instance.

Đây là dependency graph được tính lười. Hãy giữ graph một chiều, dễ hiểu và tránh chu trình.

### 9.1. Chu trình khởi tạo có thể thất bại

Nếu A cần B trong constructor và B lại gọi A.get() trong lúc A đang khởi tạo, một chu trình recursive sẽ xảy ra. LazyConstant phát hiện recursive invocation và báo lỗi thay vì tiếp tục đệ quy vô hạn.

```java
final class Components {
    static final LazyConstant<A> A_REF =
            LazyConstant.of(() -> new A(B_REF.get()));

    static final LazyConstant<B> B_REF =
            LazyConstant.of(() -> new B(A_REF.get()));
}
```

Ví dụ trên minh họa một dependency cycle. Thiết kế tốt hơn là tách phần dùng chung thành một thành phần thứ ba, hoặc trì hoãn việc kết nối dependency tới một bước cấu hình có thứ tự rõ ràng.

Static initialization cũng có thể tương tác với class initialization order. Khi kết hợp lazy constants với static initializers, cần kiểm tra chu trình giữa các class, không chỉ chu trình giữa các holder.

## 10. JVM tối ưu Lazy Constants như thế nào?

Lợi ích khác biệt so với một field mutable được đồng bộ là JVM có thể xem nội dung đã khởi tạo như một giá trị ổn định. Sau khi holder đã có content, implementation có thể loại bỏ một số lần đọc holder trong tối ưu hóa và dùng giá trị đã quan sát; kỹ thuật này thường được gọi là **constant folding**.

Tuy nhiên, khả năng tối ưu phụ thuộc vào cách holder được tham chiếu. JDK mô tả trường hợp có thể tối ưu khi:

- Có tham chiếu trực tiếp từ một `static final` field tới LazyConstant; hoặc
- Có chuỗi tham chiếu từ `static final` field, đi qua các trusted fields như `static final`, record fields hoặc final instance fields trong hidden classes, tới LazyConstant.

Ví dụ:

```java
private static final LazyConstant<RoutingTable> ROUTES =
        LazyConstant.of(RoutingTable::load);

static RoutingTable routes() {
    return ROUTES.get();
}
```

Cách khai báo này phù hợp với dạng tham chiếu trực tiếp từ `static final` field. Nếu giữ holder trong một field mutable hoặc truyền vòng quanh qua những object có cấu trúc không được JVM xem là trusted, đừng giả định compiler có thể constant-fold mọi lần đọc.

### 10.1. Không biến tối ưu hóa thành hợp đồng hiệu năng

API bảo đảm semantics khởi tạo và publication. Việc JVM có constant-fold hay không là tối ưu hóa implementation, phụ thuộc JDK, compiler, call site và cấu trúc tham chiếu.

Không viết code correctness dựa vào việc `get()` bị loại bỏ hoặc chỉ còn một phép đọc. Hãy benchmark đúng JDK và workload trước khi tuyên bố hiệu năng tăng.

### 10.2. LazyConstant giữ content suốt khi holder còn reachable

Holder giữ content bằng tham chiếu mạnh. Nếu content là một graph object lớn, class loader hoặc buffer, nó vẫn có thể giữ toàn bộ graph đó sống. Không có `clear()` để thu hồi content sau khi khởi tạo.

Nếu giá trị cần expiry hoặc eviction, dùng cache có chính sách lifetime. LazyConstant không phải cache thay thế Caffeine, cache framework hoặc dữ liệu có TTL.

## 11. LazyConstant và các lựa chọn khởi tạo an toàn khác

Lazy Constants là preview API, nên ứng dụng production cần cân nhắc các cơ chế final có sẵn trong Java.

| Cơ chế | Lazy | An toàn đa luồng | Có thể thay/refresh | Trạng thái |
|---|---|---|---|---|
| `static final` field | Không, khởi tạo khi class được initialize | Có theo quy tắc class initialization | Không | Final, ổn định |
| Initialization-on-demand holder | Có, khi nested holder được dùng lần đầu | Có theo quy tắc class initialization | Không | Final, ổn định |
| `enum` singleton | Khi enum class được initialize | Có | Không | Final, ổn định |
| `synchronized` getter | Có | Có nếu mọi truy cập tuân thủ lock | Có thể nếu thiết kế cho phép | Final, cần quản lý lock |
| `volatile` + double-checked locking | Có | Có nếu viết đúng và field là `volatile` | Có thể nếu thiết kế cho phép | Final, dễ sai nếu triển khai thiếu volatile |
| `LazyConstant` | Có | At most once và safe publication | Không | Preview qua JDK 28 EA |

### 11.1. Initialization-on-demand holder idiom

Đây là lựa chọn final, đơn giản cho singleton cần khởi tạo lười:

```java
public final class RoutingTableProvider {
    private RoutingTableProvider() {}

    private static class Holder {
        static final RoutingTable INSTANCE = RoutingTable.load();
    }

    public static RoutingTable get() {
        return Holder.INSTANCE;
    }
}
```

Nested class `Holder` chỉ được initialize khi `get()` lần đầu truy cập `Holder.INSTANCE`. Quy tắc class initialization của JVM bảo đảm việc initialize class/interface được đồng bộ và safe publication cho các thread khác.

Mẫu này phù hợp khi:

- Cần một singleton static.
- Có thể chấp nhận khởi tạo theo class initialization.
- Không cần một API lazy holder tổng quát cho nhiều instance.
- Không muốn bật preview feature.

Nếu khởi tạo thất bại trong class initializer, JVM đánh dấu class initialization thất bại; đây không phải cơ chế retry. Hãy cân nhắc semantics lỗi tương tự khi chọn holder idiom.

### 11.2. `final` field và constructor

Nếu object cần thiết cho mọi instance và có thể tạo ngay khi constructor chạy, dùng `final` field:

```java
final class OrderService {
    private final PricingRules rules;

    OrderService(PricingRules rules) {
        this.rules = Objects.requireNonNull(rules);
    }
}
```

Constructor injection làm dependency hiển thị rõ, tránh trạng thái object chưa hoàn chỉnh và tận dụng final-field semantics. Đây thường là lựa chọn tốt cho service phụ thuộc vào cấu hình đã có sẵn.

### 11.3. Double-checked locking chỉ khi thật sự cần

Nếu cần lazy initialization cho field instance có thể refresh, có thể dùng `volatile` và double-checked locking. Mẫu này cần viết đúng; bỏ `volatile` sẽ làm mất bảo đảm publication:

```java
final class InstanceConfig {
    private volatile Config config;

    Config get() {
        Config current = config;
        if (current == null) {
            synchronized (this) {
                current = config;
                if (current == null) {
                    current = Config.load();
                    config = current;
                }
            }
        }
        return current;
    }
}
```

Mẫu này vẫn là state mutable và cần thêm chính sách khi refresh, failure hoặc đóng resource. Với singleton static, initialization-on-demand holder thường ít phức tạp hơn.

## 12. Khi nào nên và không nên dùng Lazy Constants?

**Nên cân nhắc** khi một object:

- Có chi phí tạo đáng kể nhưng không phải request nào cũng cần.
- Có thể giữ nguyên nội dung trong suốt vòng đời process.
- Được nhiều thread đọc sau khi tạo.
- Không cần refresh, eviction, timeout hoặc cancellation.
- Có thể được tạo từ một computing function không có side effect nguy hiểm.

Ví dụ phù hợp: schema đã parse, metadata bất biến, cấu hình được xác thực, bảng định tuyến immutable, parser dùng chung.

**Không nên dùng** khi:

- Dữ liệu thay đổi theo request, user hoặc tenant.
- Cần refresh theo thời gian hoặc khi secret rotate.
- Cần retry khi remote service tạm thời lỗi.
- Cần timeout/cancel computation.
- Content là resource phải đóng hoặc tái tạo.
- Muốn lưu một collection mutable rồi nhiều thread sửa đồng thời.
- Không chấp nhận preview API trong production.

Đối với cache dữ liệu nghiệp vụ, dùng cache có TTL, eviction và refresh semantics. Đối với dependency injection, dùng lifecycle container như Spring. Đối với context theo request, dùng tham số tường minh hoặc `ScopedValue` tùy phạm vi.

## 13. Dùng API LazyConstant hiện hành trên JDK 27/28

`LazyConstant` là preview API từ JDK 26. Trên JDK 27 GA, JEP 531 là preview lần thứ ba. Trên JDK 28 Early Access, JEP 547 là preview lần thứ tư. Code sau dùng API shape hiện hành: `LazyConstant.of(...)` và `get()`.

```java
import java.lang.LazyConstant;
import java.util.Map;

public final class FeatureRegistry {
    private static final LazyConstant<Map<String, Boolean>> FLAGS =
            LazyConstant.of(FeatureRegistry::loadFlags);

    private FeatureRegistry() {}

    public static Map<String, Boolean> flags() {
        return FLAGS.get();
    }

    private static Map<String, Boolean> loadFlags() {
        return Map.of(
                "new-checkout", true,
                "bulk-export", false
        );
    }
}
```

Biên dịch và chạy với JDK 27:

```bash
javac --release 27 --enable-preview -d out src/FeatureRegistry.java
java --enable-preview -cp out example.Main
```

Với JDK 28 Early Access, dùng chính JDK 28 compiler/runtime và bật preview:

```bash
javac --enable-preview -d out src/FeatureRegistry.java
java --enable-preview -cp out example.Main
```

Không dùng `--release 25` cho `LazyConstant`: type này chưa tồn tại trong JDK 25. Cờ preview phải khớp với phiên bản JDK đang biên dịch và chạy. Preview API có thể tiếp tục thay đổi hoặc bị rút lại; cần đọc API docs của đúng build trước khi nâng cấp.

### 13.1. Module declaration

`LazyConstant` thuộc module `java.base`, module này được yêu cầu mặc định bởi mọi module Java. Ứng dụng named module không cần thêm `requires` riêng cho `java.base`.

### 13.2. Không dùng API cũ từ JDK 25

Khi đọc tài liệu hoặc sample code về Stable Values, kiểm tra đúng JDK và JEP. Tên `StableValue` và các method preview ban đầu không còn là cách dùng hiện hành. Mã mới cần dùng `java.lang.LazyConstant` và API của JDK đích.

## 14. Kiểm thử concurrency và safe publication

Một bài test tốt nên xác minh hành vi của API thay vì chỉ kiểm tra rằng `get()` trả về object.

Các tình huống cần kiểm tra:

| Tình huống | Kỳ vọng |
|---|---|
| Nhiều thread gọi `get()` lần đầu | Computing function chỉ chạy một lần |
| Các thread gọi sau khi khởi tạo | Nhận cùng content |
| Content có `final` fields được thiết lập trong constructor | Thread đọc sau publication thấy trạng thái đã khởi tạo |
| Function trả về `null` | Chuyển error state, không giữ null |
| Function ném unchecked exception | Chuyển error state, không retry ở lần get sau |
| Function gọi đệ quy chính nó | Báo lỗi recursive initialization |
| Computing thread bị interrupt | Initialization không bị tự động cancel |
| Function block vô hạn | Các thread chờ có thể block vô hạn |
| Content là mutable | Mutations sau publication cần đồng bộ riêng |

Ví dụ test đếm số lần function chạy:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.LazyConstant;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

class LazyConstantConcurrencyTest {
    @Test
    void initializesOnlyOnceForConcurrentCallers() throws Exception {
        AtomicInteger calls = new AtomicInteger();

        LazyConstant<Object> value = LazyConstant.of(() -> {
            calls.incrementAndGet();
            return new Object();
        });

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var tasks = java.util.stream.IntStream.range(0, 32)
                    .<Callable<Object>>mapToObj(i -> value::get)
                    .toList();

            var futures = executor.invokeAll(tasks);
            Object first = futures.getFirst().get();

            for (var future : futures) {
                assertSame(first, future.get());
            }
        }

        assertEquals(1, calls.get());
    }
}
```

Đoạn test minh họa trên dùng JDK có `LazyConstant` preview và JUnit Jupiter. `ExecutorService` hỗ trợ `AutoCloseable` trong các JDK hiện đại được dùng cho ví dụ; nếu dự án dùng JDK khác, điều chỉnh cách đóng executor theo API có sẵn. Để bảo đảm thật sự có tranh chấp ở lần truy cập đầu, có thể thêm `CountDownLatch` đồng bộ điểm bắt đầu các task.

### 14.1. Kiểm thử publication, không chỉ identity

Một test khác nên tạo content có nhiều field được thiết lập trong constructor rồi để nhiều thread đọc các field đó sau `get()`. Mục tiêu là xác minh không thread nào nhìn thấy trạng thái khởi tạo dở dang.

Tuy nhiên, không thể chứng minh memory model chỉ bằng một test stress chạy thành công. Căn cứ chính là hợp đồng happens-before của API; test chỉ giúp phát hiện lỗi trong cách ứng dụng sử dụng content sau publication.

## 15. Bài tập thực hành và tiêu chí hoàn thành

### Bài tập 1 — Nhận diện tên API theo JDK

Giải thích vì sao code dùng `StableValue` từ JDK 25 không phải API nên dùng cho JDK 27. Nêu tên API hiện hành, JEP của JDK 26/27/28 và cờ preview cần thiết.

### Bài tập 2 — Nhiều thread cùng khởi tạo

Một service có 64 request đồng thời gọi `CONFIG.get()` lần đầu. Mô tả thread nào chạy computing function, các thread còn lại làm gì và vì sao không có 64 bản config được chấp nhận.

### Bài tập 3 — Safe publication và mutable content

Một LazyConstant giữ `ArrayList`. Vì sao việc khởi tạo holder an toàn không làm các lần `add()` sau đó thread-safe? Đề xuất cách chuyển sang immutable snapshot hoặc collection concurrent.

### Bài tập 4 — Failure semantics

Computing function gọi config server và ném `IllegalStateException`. Điều gì xảy ra ở lần `get()` đầu, lần thứ hai và vì sao LazyConstant không phù hợp với retry tự động?

### Bài tập 5 — Null và Optional

Một cấu hình có thể không tồn tại. Viết computing function trả `Optional<Config>` để biểu diễn absence mà không trả `null`.

### Bài tập 6 — Dependency graph

Một `OrderService` phụ thuộc `Repository`, `Repository` phụ thuộc `DatabaseConfig`. Thiết kế ba LazyConstant và mô tả thứ tự khởi tạo khi gọi `OrderService.get()` lần đầu. Tìm một ví dụ chu trình và cách tách dependency.

### Bài tập 7 — Chọn cơ chế production

Một ứng dụng cần singleton static tạo lười, không được dùng preview API. So sánh LazyConstant với initialization-on-demand holder idiom và giải thích lựa chọn phù hợp.

### Tiêu chí đạt

Bạn hoàn thành bài học khi có thể:

1. Giải thích lịch sử Stable Values (JDK 25) và tên API hiện hành Lazy Constants từ JDK 26.
2. Dùng đúng `java.lang.LazyConstant`, `of(Supplier)` và `get()` trên JDK preview tương ứng.
3. Mô tả bảo đảm at most once khi nhiều thread gọi đồng thời.
4. Giải thích happens-before và safe publication của content đã khởi tạo.
5. Phân biệt holder không thay content với object bên trong có thể mutable.
6. Xử lý đúng `null`, unchecked exception, recursive initialization và error state.
7. Nhận diện rủi ro block, interruption, strong reference và không có timeout/cancel.
8. Biết khi nào LazyConstant phù hợp và khi nào cần cache/lifecycle manager khác.
9. Dùng initialization-on-demand holder hoặc final fields khi cần giải pháp ổn định không preview.
10. Không trộn API StableValue cũ với LazyConstant hiện hành.

### Tài liệu tham khảo

1. [JEP 502 — Stable Values](https://openjdk.org/jeps/502): preview đầu tiên của ý tưởng Stable Values trong JDK 25.
2. [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): đổi tên và điều chỉnh API trong JDK 26.
3. [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): trạng thái API trong JDK 27.
4. [JEP 547 — Lazy Constants (Fourth Preview)](https://openjdk.org/jeps/547): vòng preview được nhắm tới JDK 28.
5. [Java SE 27 API — `LazyConstant`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API, thread safety, error state, null handling và constant folding.
6. [Oracle JDK 27 — Lazy Constants Guide](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): ví dụ ứng dụng, dependency graph, lazy lists và lazy maps.
7. [Oracle JDK 26 — Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): xác nhận JEP 502 được đổi mới và re-preview dưới JEP 526.
8. [Inside Java — JEP 547 targeted to JDK 28](https://inside.java/2026/11/20/jep547-target-jdk28/): trạng thái preview thứ tư trong JDK 28.
9. [JLS §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se27/html/jls-12.html#jls-12.4): semantics class initialization dùng bởi initialization-on-demand holder idiom.
10. [JLS §17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.4.5): mô hình bộ nhớ Java và quan hệ happens-before.

11. [JDK 28 Early Access API — `LazyConstant`](https://download.java.net/java/early_access/jdk28/docs/api/java.base/java/lang/LazyConstant.html): kiểm tra trạng thái preview và API của build JDK 28 EA.

> **Ghi chú hiện hành:** Stable Values là tên của preview đầu tiên trong Java 25; API đó đã được thay thế bằng Lazy Constants từ Java 26. Tại thời điểm biên soạn, JDK 27 là bản GA mới nhất và LazyConstant vẫn là preview lần thứ ba; JDK 28 Early Access có preview lần thứ tư theo JEP 547. Bài không dùng lại API StableValue cũ. Với production không chấp nhận preview, ưu tiên `final` field, class initialization hoặc initialization-on-demand holder idiom.

