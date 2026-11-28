# Phần thực hành dùng hợp đồng LazyConstant preview Java 27 hiện hành

> **Mốc nội dung: 27-11-2026.** Java 27 đã phát hành chính thức ngày 15-09-2026. Lazy Constants tiếp tục ở trạng thái **Preview lần thứ ba** theo JEP 531; đây chưa phải API ổn định của Java SE. Bài này dùng đúng hợp đồng API trong JDK 27, không dùng các method chỉ có ở preview JDK 26.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

- Khởi tạo một giá trị chỉ khi lần đầu cần dùng bằng `java.lang.LazyConstant<T>`.
- Kiểm chứng supplier chỉ chạy một lần khi nhiều thread cùng gọi `get()`.
- Hiểu trạng thái lỗi khi supplier ném exception, trả về `null` hoặc gọi đệ quy.
- Chọn đúng giữa `LazyConstant`, `List.ofLazy`, `Map.ofLazy` và `Set.ofLazy`.
- Biên dịch và chạy preview code bằng JDK 27.
- Đánh giá lợi ích startup và constant folding mà không giả định JVM luôn tạo ra một mức tăng tốc cố định.

Lazy Constants nằm trong phạm vi cải tiến Java 26 về tối ưu JVM, nhưng trạng thái hiện hành đã được tiếp tục và điều chỉnh trong Java 27. Oracle phân loại JEP 531 là preview API; vì vậy phải khóa phiên bản JDK khi thử nghiệm và chuẩn bị cập nhật mã khi preview thay đổi.

## 2. Xác định đúng API Java 27

Kiểu hiện hành là:

```java
java.lang.LazyConstant<T>
```

`LazyConstant<T>` là một sealed interface mở rộng `Supplier<T>`. Một lazy constant giữ một giá trị được tính khi cần và chỉ được khởi tạo tối đa một lần. Factory hiện hành là:

```java
LazyConstant<T> value = LazyConstant.of(computingFunction);
T result = value.get();
```

Ở JDK 27, các method API cần dùng trong thực hành là:

| API | Công dụng |
|---|---|
| `LazyConstant.of(Supplier<? extends T>)` | Tạo lazy constant mới, chưa tính giá trị. |
| `get()` | Tính giá trị ở lần gọi đầu tiên và trả về cùng giá trị ở các lần gọi sau. |
| `equals(Object)`, `hashCode()` | Dựa trên identity của chính lazy constant; không kích hoạt khởi tạo. |
| `toString()` | Chuỗi phục vụ debug; không kích hoạt khởi tạo và nội dung chuỗi phụ thuộc implementation. |

**Không dùng `isInitialized()` hoặc `orElse(...)` trong code Java 27.** Hai method này xuất hiện trong preview lần hai ở JDK 26 nhưng đã bị loại khỏi hợp đồng API ở preview lần ba của JDK 27. Không viết logic ứng dụng phụ thuộc vào việc dò trạng thái khởi tạo. Hãy gọi `get()` tại nơi thực sự cần giá trị.

| Phiên bản | Tình trạng |
|---|---|
| JDK 26 | `LazyConstant` ở preview lần hai, JEP 526; API có `isInitialized()` và `orElse(...)`. |
| JDK 27 | `LazyConstant` ở preview lần ba, JEP 531; bỏ hai method trên và bổ sung `Set.ofLazy(...)` trong Collections Framework. |

Hãy đọc Javadoc đúng phiên bản JDK đang biên dịch. Ví dụ hoặc bài viết dùng `isInitialized()` hay `orElse(...)` có thể đúng với JDK 26 preview nhưng không biên dịch với API JDK 27.

## 3. Bài tập 1 — Khởi tạo cấu hình khi được truy cập lần đầu

Giả sử ứng dụng có một cấu hình kết nối tốn thời gian để nạp. Không phải mọi luồng xử lý đều sử dụng cấu hình này. Nếu khởi tạo nó ngay khi tạo component, ứng dụng phải trả chi phí đó dù component không bao giờ được dùng.

Dùng lazy constant để trì hoãn việc nạp cấu hình:

```java
import java.lang.LazyConstant;
import java.time.Duration;

public final class AppConfig {
    private AppConfig() {}

    public record ConnectionSettings(
            String endpoint,
            Duration connectTimeout
    ) {}

    private static ConnectionSettings loadSettings() {
        System.out.println("Loading connection settings...");
        return new ConnectionSettings(
                "https://api.example.test",
                Duration.ofSeconds(3)
        );
    }

    private static final LazyConstant<ConnectionSettings> SETTINGS =
            LazyConstant.of(AppConfig::loadSettings);

    public static ConnectionSettings connectionSettings() {
        return SETTINGS.get();
    }

    public static void main(String[] args) {
        System.out.println("Application started");

        // Giá trị chỉ được nạp khi dòng này được thực thi.
        ConnectionSettings settings = connectionSettings();
        System.out.println(settings.endpoint());

        // Lần gọi tiếp theo lấy lại cùng giá trị đã khởi tạo.
        System.out.println(connectionSettings() == settings);
    }
}
```

Kết quả minh họa:

```text
Application started
Loading connection settings...
https://api.example.test
true
```

Hãy quan sát thứ tự output:

1. Khai báo `SETTINGS` tạo holder và lưu supplier, chưa gọi `loadSettings()`.
2. `connectionSettings()` gọi `SETTINGS.get()`.
3. Lần gọi đầu tiên thực thi supplier và lưu kết quả.
4. Những lần gọi sau nhận lại cùng object; supplier không chạy lại.

`static final` giúp giữ tham chiếu tới lazy constant ổn định trong suốt vòng đời class. Nó cũng là dạng tham chiếu phù hợp để JVM xem xét constant folding sau khi giá trị đã được khởi tạo.

## 4. Bài tập 2 — Nhiều thread cùng truy cập

Một yêu cầu quan trọng của LazyConstant là khởi tạo an toàn khi nhiều thread tranh nhau gọi `get()`. Trong một cuộc đua khởi tạo, chỉ một thread chạy computing function; các thread còn lại chờ cho đến khi giá trị được khởi tạo hoặc phép tính thất bại.

Ví dụ sau dùng virtual threads để tạo nhiều lời gọi gần như đồng thời. Virtual threads đã là tính năng ổn định từ JDK 21; phần preview trong ví dụ là `LazyConstant`.

```java
import java.lang.LazyConstant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyConstantConcurrencyDemo {
    private record ServiceClient(String endpoint) {}

    private static final AtomicInteger COMPUTE_COUNT =
            new AtomicInteger();

    private static final LazyConstant<ServiceClient> CLIENT =
            LazyConstant.of(() -> {
                COMPUTE_COUNT.incrementAndGet();
                System.out.println("Creating service client");
                return new ServiceClient("https://service.example.test");
            });

    public static void main(String[] args) throws Exception {
        int workers = 32;
        var ready = new CountDownLatch(workers);
        var start = new CountDownLatch(1);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<ServiceClient>> results =
                    new ArrayList<>(workers);

            for (int i = 0; i < workers; i++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return CLIENT.get();
                }));
            }

            // Đợi tất cả worker sẵn sàng rồi mới thả cùng lúc.
            ready.await();
            start.countDown();

            ServiceClient first = results.getFirst().get();

            for (Future<ServiceClient> result : results) {
                if (result.get() != first) {
                    throw new AssertionError(
                            "Different instances were returned"
                    );
                }
            }
        }

        System.out.println("Computations: " + COMPUTE_COUNT.get());
        System.out.println("All workers received the same instance");
    }
}
```

Kết quả mong đợi:

```text
Creating service client
Computations: 1
All workers received the same instance
```

Một dòng `Creating service client` cho thấy chỉ một lần thực thi supplier. Tất cả worker nhận cùng một tham chiếu. Số thread tham gia không làm supplier chạy nhiều lần.

**Điểm cần hiểu về thread safety:**

- Thread thắng cuộc thực hiện supplier trên chính thread gọi `get()`.
- Các thread khác có thể bị block trong lúc giá trị đang được tính.
- Việc tính giá trị và khởi tạo có quan hệ happens-before với lần đọc giá trị đã khởi tạo; object được safe publication.
- `get()` không cung cấp timeout hay cơ chế cancellation cho supplier.
- Interrupt không hủy quá trình khởi tạo; `get()` không xóa interrupt status và không ném `InterruptedException` chỉ vì thread bị interrupt.
- Nếu supplier chờ I/O vô thời hạn, các thread khác chờ cùng lazy constant cũng có thể bị block vô thời hạn.

Vì vậy, supplier nên hoàn thành hữu hạn và tránh công việc I/O không có timeout. Nếu cần thao tác mạng, hãy đặt timeout ở API mạng bên trong supplier và xác định rõ cách xử lý lỗi.

## 5. Bài tập 3 — Kiểm tra trạng thái lỗi

LazyConstant không phải cache tự thử lại. Nếu computing function thất bại bằng unchecked exception, lazy constant chuyển sang error state. Supplier không được gọi lại ở lần `get()` tiếp theo.

Ví dụ:

```java
import java.lang.LazyConstant;
import java.util.NoSuchElementException;

public class LazyConstantFailureDemo {
    public static void main(String[] args) {
        LazyConstant<String> failed = LazyConstant.of(() -> {
            System.out.println("Computing value");
            throw new IllegalStateException("Configuration is invalid");
        });

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                failed.get();
            } catch (NoSuchElementException error) {
                Throwable cause = error.getCause();
                System.out.printf(
                        "Attempt %d: %s, cause=%s%n",
                        attempt,
                        error.getClass().getSimpleName(),
                        cause == null ? "none"
                                : cause.getClass().getSimpleName()
                );
            }
        }
    }
}
```

Kết quả theo hợp đồng Java 27:

```text
Computing value
Attempt 1: NoSuchElementException, cause=IllegalStateException
Attempt 2: NoSuchElementException, cause=none
```

Lần gọi đầu tiên nhận `NoSuchElementException` với unchecked exception gốc làm cause. Các lần gọi sau tiếp tục nhận `NoSuchElementException`, không có cause; message có tên class của exception ban đầu. Supplier chỉ được thực thi một lần, kể cả khi nó thất bại.

Ba trường hợp đặc biệt:

| Trường hợp | Hành vi |
|---|---|
| Supplier ném `RuntimeException` hoặc `Error` | Chuyển sang error state; `get()` ném `NoSuchElementException` với exception gốc làm cause. |
| Supplier trả về `null` | Không được chấp nhận; `get()` ném `NoSuchElementException` với `NullPointerException` làm cause. |
| Supplier gọi đệ quy chính lazy constant đó | Không thể khởi tạo đệ quy; `get()` ném `NoSuchElementException` với `IllegalStateException` làm cause. |

Nếu nghiệp vụ cần lưu kết quả có thể không tồn tại, hãy bọc giá trị bằng `Optional` để supplier luôn trả về một object không null:

```java
LazyConstant<Optional<User>> USER =
        LazyConstant.of(() -> Optional.ofNullable(loadUser()));
```

Nếu cần retry sau lỗi tạm thời, phải thiết kế một cơ chế retry hoặc một vòng đời holder mới ở tầng ứng dụng. Không thể reset một LazyConstant đã chuyển sang error state.

## 6. Bài tập 4 — Ghép nhiều lazy constant thành đồ thị phụ thuộc

Một component có thể phụ thuộc vào component khác. Hãy biểu diễn mỗi giá trị ổn định bằng một lazy constant riêng:

```java
import java.lang.LazyConstant;

record DatabaseSettings(String jdbcUrl) {}
record DatabaseClient(DatabaseSettings settings) {}
record OrderRepository(DatabaseClient client) {}

final class ApplicationComponents {
    private ApplicationComponents() {}

    private static final LazyConstant<DatabaseSettings> SETTINGS =
            LazyConstant.of(() ->
                    new DatabaseSettings("jdbc:example://db/orders")
            );

    private static final LazyConstant<DatabaseClient> DATABASE =
            LazyConstant.of(() ->
                    new DatabaseClient(SETTINGS.get())
            );

    private static final LazyConstant<OrderRepository> ORDERS =
            LazyConstant.of(() ->
                    new OrderRepository(DATABASE.get())
            );

    static OrderRepository orderRepository() {
        return ORDERS.get();
    }
}
```

Khi gọi `orderRepository()`, đồ thị được tính theo thứ tự phụ thuộc: `ORDERS` yêu cầu `DATABASE`, còn `DATABASE` yêu cầu `SETTINGS`. Mỗi node chỉ được tính tối đa một lần. Nếu một component không được sử dụng, supplier tương ứng không cần chạy.

Hãy giữ đồ thị phụ thuộc một chiều, rõ ràng. Nếu A cần B trong lúc B lại cần A, có thể xảy ra gọi đệ quy và lazy constant chuyển sang error state. Phụ thuộc vòng trong static initializer cũng có thể tương tác với quy tắc khởi tạo class của Java và dẫn đến lỗi khởi tạo class.

## 7. Bài tập 5 — Lazy collections trong Java 27

JDK 27 mở rộng cách dùng lazy values cho những trường hợp cần nhiều giá trị. `List.ofLazy`, `Map.ofLazy` và `Set.ofLazy` đều là preview API; `Set.ofLazy` là phần bổ sung mới trong JDK 27.

| Factory | Khi nào tính | Miền dữ liệu |
|---|---|---|
| `List.ofLazy(size, IntFunction)` | Khi một index được truy cập lần đầu. | Số lượng phần tử và index xác định trước. |
| `Map.ofLazy(keys, Function)` | Khi value của một key được truy cập lần đầu. | Tập key xác định trước. |
| `Set.ofLazy(candidates, Predicate)` | Khi cần xác định candidate có thuộc set hay không. | Tập candidate xác định trước. |

### 7.1. Lazy List — tạo phần tử theo index

```java
import java.util.List;

record Report(int id, String title) {}

final class Reports {
    private static final int SIZE = 100;

    static final List<Report> REPORTS =
            List.ofLazy(SIZE, index ->
                    new Report(index, "Report " + index)
            );

    static Report reportAt(int index) {
        return REPORTS.get(index);
    }
}
```

Chỉ phần tử tại index được truy cập mới cần được tính. Mỗi index được tính tối đa một lần, kể cả khi nhiều thread cùng truy cập index đó. List không cho phép thêm, xóa hoặc thay thế phần tử; phần tử null cũng không hợp lệ.

### 7.2. Lazy Map — tính value cho tập key cố định

```java
import java.util.Map;
import java.util.Set;

record Route(String target) {}

final class RouteRegistry {
    private static final Set<String> ROUTE_NAMES =
            Set.of("profile", "orders", "billing");

    static final Map<String, Route> ROUTES =
            Map.ofLazy(ROUTE_NAMES, RouteRegistry::loadRoute);

    private static Route loadRoute(String name) {
        System.out.println("Loading route " + name);
        return new Route("/api/" + name);
    }
}
```

Map biết trước tập key. Khi lấy value của một key, computing function chỉ chạy tối đa một lần cho key đó. Map là unmodifiable và không chấp nhận key/value null. Đây không phải map động để thêm key trong runtime.

### 7.3. Lazy Set — tính membership theo candidate

```java
import java.util.EnumSet;
import java.util.Set;

enum Feature {
    AUDIT, EXPORT, EXPERIMENTAL
}

final class FeatureRegistry {
    static final Set<Feature> ENABLED =
            Set.ofLazy(
                    EnumSet.allOf(Feature.class),
                    FeatureRegistry::isEnabled
            );

    private static boolean isEnabled(Feature feature) {
        System.out.println("Checking " + feature);
        return switch (feature) {
            case AUDIT, EXPORT -> true;
            case EXPERIMENTAL -> false;
        };
    }
}
```

Tập candidate được cố định khi tạo set. Predicate chỉ được gọi khi cần kiểm tra membership của candidate. Kết quả membership được tính tối đa một lần cho mỗi candidate. Set trả về không cho phép thay đổi.

**Chọn đúng cấu trúc:**

- Một object dùng chung, tạo đúng một lần: `LazyConstant<T>`.
- Một dãy có index xác định trước: `List.ofLazy(...)`.
- Một tập key biết trước, mỗi key có value tính trễ: `Map.ofLazy(...)`.
- Một tập candidate biết trước, membership tính trễ: `Set.ofLazy(...)`.

Không dùng lazy collection nếu tập phần tử hoặc key cần thêm/xóa liên tục. Các factory này tạo collection unmodifiable.

## 8. Preview API và cách biên dịch Java 27

LazyConstant và các lazy collection là preview API. Chúng không được bật mặc định. Dùng chính JDK 27 để biên dịch và chạy:

```text
javac --enable-preview --release 27 LazyConstantDemo.java
java --enable-preview LazyConstantDemo
```

Có thể bật cảnh báo chi tiết về preview khi biên dịch:

```text
javac --enable-preview --release 27 -Xlint:preview LazyConstantDemo.java
```

Một số nguyên tắc khi dùng preview:

1. `javac` và `java` phải thuộc cùng feature release 27.
2. Bật `--enable-preview` ở bước compile và runtime.
3. `--release 27` giúp biên dịch theo API của Java 27; không dùng API của JDK mới hơn hoặc nội bộ JDK.
4. Class file dùng preview của một release không mặc nhiên chạy được trên release khác.
5. Khi chuyển sang JDK 28 hoặc release tiếp theo, phải đọc lại Preview API List và biên dịch lại. Không giả định hợp đồng JDK 27 được giữ nguyên.

Ví dụ với source-file mode:

```text
java --enable-preview LazyConstantDemo.java
```

Cách chạy này dùng runtime JDK 27 và cơ chế biên dịch source-file mode của launcher. Với dự án nhiều file hoặc build tool, cấu hình preview đồng bộ cho compiler và test/runtime task.

## 9. Hiểu đúng lợi ích hiệu năng

Lazy constant kết hợp hai đặc tính:

- **Lazy initialization:** giá trị chỉ được tính khi có lần truy cập đầu tiên.
- **Immutability sau khởi tạo:** giá trị được giữ nguyên sau khi đã khởi tạo.

JVM có thể xem lazy constant đã khởi tạo như một constant và thực hiện constant folding tương tự field `final`. Điều này có thể loại bỏ một số lần đọc giá trị từ bộ nhớ trong mã máy được JIT biên dịch.

Tuy nhiên, constant folding không phải cam kết cho mọi cách sử dụng. Javadoc mô tả điều kiện thuận lợi là tham chiếu trực tiếp từ `static final` field đến LazyConstant, hoặc đường dẫn từ `static final` field qua các trusted fields như `static final`, record fields và final instance fields trong hidden classes. JVM vẫn quyết định có thực hiện tối ưu hóa hay không dựa trên implementation và trạng thái biên dịch.

### 9.1. Khi nào có thể hữu ích?

- Component khởi tạo tốn chi phí nhưng chỉ một số luồng nghiệp vụ cần đến.
- Parser, metadata hoặc bảng tra cứu bất biến được dùng chung sau khi khởi tạo.
- Cấu hình bất biến được nạp khi chức năng tương ứng được gọi.
- Đồ thị component có nhiều nhánh hiếm khi được truy cập.

### 9.2. Khi nào không phù hợp?

- Giá trị cần thay đổi khi reload cấu hình.
- Cache có TTL, eviction hoặc cần xóa giá trị.
- Giá trị phụ thuộc vào tham số của từng request.
- Supplier thực hiện I/O có thể block lâu, cần timeout hoặc cancellation.
- Giá trị cần thử lại sau lỗi tạm thời.
- Holder có thể sống lâu hơn dự kiến và giữ một object lớn trong bộ nhớ.

LazyConstant giữ tham chiếu mạnh tới content; content vẫn reachable chừng nào holder còn reachable. Đây có thể là nguồn giữ bộ nhớ ngoài dự kiến. Ngoài ra, bản thân LazyConstant không phải Serializable.

### 9.3. Lazy holder không làm object trở thành immutable sâu

LazyConstant không thay thế object immutability. Nó bảo đảm content reference được gắn một lần; object mà reference trỏ tới vẫn có thể mutable.

Ví dụ:

```java
static final LazyConstant<List<String>> TAGS =
        LazyConstant.of(ArrayList::new);
```

Sau khi khởi tạo, code vẫn có thể gọi `TAGS.get().add("new-tag")`. Nếu cần dữ liệu bất biến, hãy tạo giá trị immutable, ví dụ `List.copyOf(...)`, hoặc dùng record với các thành phần immutable phù hợp.

Không đồng bộ trực tiếp trên LazyConstant. Javadoc ghi rõ implementation được phép synchronize trên chính lazy constant; đồng bộ ứng dụng trên object này có thể tạo tương tác khó dự đoán.

## 10. Đo kiểm và bài tập tổng hợp

Thực hiện các bài sau trên JDK 27 có bật preview:

1. **Kiểm tra trì hoãn:** thêm log trong supplier. Khởi tạo class nhưng không gọi `get()`; xác nhận supplier chưa chạy.
2. **Kiểm tra khởi tạo một lần:** gọi `get()` 100 lần. Dùng `AtomicInteger` đếm số lần supplier chạy; kết quả mong đợi là 1.
3. **Kiểm tra đồng thời:** dùng 32 hoặc 64 virtual threads cùng gọi `get()`; xác nhận mọi thread nhận cùng một object và supplier chỉ chạy một lần.
4. **Kiểm tra lỗi:** thử supplier ném `IllegalArgumentException`, supplier trả về null và supplier gọi đệ quy. Kiểm tra exception ở lần gọi đầu và lần gọi sau.
5. **Kiểm tra lazy collections:** truy cập một index của List, một key của Map và một candidate của Set. Quan sát computing function chỉ chạy cho phần tử được yêu cầu.
6. **Kiểm tra giới hạn preview:** thử compile không có `--enable-preview`, sau đó compile/run với JDK 27 đúng cờ. Ghi lại khác biệt.
7. **Kiểm tra constant folding:** đặt LazyConstant trong `static final` field, đo đường đọc sau khởi tạo bằng JMH. So sánh với field `final` được khởi tạo sớm và holder lazy truyền thống.

Bảng ghi kết quả:

| Thử nghiệm | Kết quả cần ghi | Tiêu chí |
|---|---|---|
| Khởi tạo trễ | Số lần supplier chạy trước/sau `get()` | Trước lần đầu: 0; sau các lần truy cập thành công: 1. |
| Truy cập đồng thời | Số lần tính và số identity khác nhau | Supplier chạy 1 lần; mọi kết quả cùng identity. |
| Supplier ném exception | Loại exception và cause ở lần 1/lần 2 | Error state không tự retry. |
| Supplier trả null | Exception và cause | Không có giá trị null được khởi tạo. |
| Lazy List/Map/Set | Số lần tính theo index/key/candidate | Mỗi phần tử được yêu cầu tối đa một lần. |
| Preview flags | Kết quả compile/run | JDK 27 yêu cầu bật preview ở cả compile và runtime. |
| Hiệu năng | Startup, thời gian truy cập đầu, thời gian truy cập sau warm-up | Chỉ kết luận từ benchmark lặp lại, có warm-up và nhiều fork. |

Khi đo hiệu năng, dùng JMH hoặc một harness benchmark phù hợp. Không dùng một vòng lặp `System.nanoTime()` đơn giản để kết luận về constant folding: JIT warm-up, dead-code elimination, escape analysis và môi trường chạy có thể làm sai lệch kết quả. Hãy giữ kết quả được sử dụng trong benchmark (Blackhole hoặc assertion phù hợp), tách startup khỏi steady-state và đo nhiều fork.

## 11. Checklist trước khi dùng trong dự án

- [ ] Runtime và compiler đều là JDK 27 nếu dùng preview lần ba.
- [ ] Build, test, IDE và production command line đều cấu hình `--enable-preview` nhất quán.
- [ ] Không còn gọi `LazyConstant.isInitialized()` hoặc `LazyConstant.orElse(...)`.
- [ ] Supplier trả về giá trị không null; dùng `Optional` nếu miền dữ liệu cần biểu diễn vắng mặt.
- [ ] Supplier không phụ thuộc vòng và không block vô thời hạn.
- [ ] Có chính sách rõ ràng cho error state vì supplier không tự chạy lại.
- [ ] Content không bị mutable ngoài ý muốn; holder không giữ object lớn lâu hơn cần thiết.
- [ ] Đã đo startup và steady-state trên workload thật trước khi kết luận có lợi ích hiệu năng.
- [ ] Có kế hoạch rà soát lại API khi nâng cấp JDK tiếp theo.

## Tài liệu tham khảo chính thức

- [JEP 531: Lazy Constants (Third Preview)](https://openjdk.org/jeps/531)
- [JDK 27 Release Notes — Lazy Constants (Third Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Lazy Constants — Java Platform, Standard Edition 27](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html)
- [LazyConstant API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [List API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html)
- [Map API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html)
- [Set API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html)
- [Preview Features — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)

