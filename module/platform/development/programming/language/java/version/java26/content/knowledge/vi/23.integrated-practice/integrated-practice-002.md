# Khởi tạo thành phần đắt bằng LazyConstant preview Java 27

## 1. Bài thực hành và kết quả cần đạt

Một ứng dụng có thể chứa nhiều thành phần chỉ được một số request sử dụng: bộ phân tích quy tắc, catalog kiểm tra dữ liệu, schema compiler, expression engine hoặc bảng tra cứu lớn. Nếu tạo tất cả ngay khi ứng dụng khởi động, startup phải trả chi phí cho cả thành phần không được dùng.

Nếu tự viết lazy initialization bằng field mutable, synchronized hoặc double-checked locking, code phải tự quản lý race condition, publication và đường đọc sau lần khởi tạo đầu tiên.

Bài thực hành này xây dựng một RuleCatalog đắt bằng java.lang.LazyConstant trên JDK 27. Catalog được tạo khi request đầu tiên cần kiểm tra quy tắc; những request tiếp theo dùng lại cùng một instance.

Sau bài này, người học có thể:

1. Phân biệt eager initialization, initialization-on-demand holder và LazyConstant.
2. Tạo lazy constant bằng LazyConstant.of(Supplier) và lấy giá trị bằng get().
3. Kiểm tra khởi tạo at-most-once khi nhiều thread gọi đồng thời.
4. Hiểu cách JDK 27 công bố kết quả an toàn cho các thread.
5. Xử lý null, exception, dependency cycle và thành phần giữ tài nguyên.
6. Compile/run preview bằng đúng JDK 27.
7. Quyết định trường hợp nào phù hợp với LazyConstant và trường hợp nào cần cơ chế retry/lifecycle khác.

## 2. Trạng thái API: JDK 27 là preview lần thứ ba

LazyConstant là preview API, được giới thiệu trong JDK 25 dưới thiết kế ban đầu khác và tiếp tục thay đổi qua JDK 26 và JDK 27.

| JDK | JEP | Trạng thái | Điểm cần biết |
|---|---|---|---|
| JDK 25 | JEP 502 | Preview lần đầu | Thiết kế ban đầu của lazy constants |
| JDK 26 | JEP 526 | Preview lần thứ hai | API LazyConstant được preview lại |
| JDK 27 | JEP 531 | Preview lần thứ ba | Thay đổi API và semantics lỗi; dùng đúng API của JDK 27 |

JDK 27 phát hành ngày 15/09/2026. LazyConstant vẫn là preview API, không phải API Java SE ổn định. Khi compile và run phải bật preview. Preview có thể thay đổi hoặc bị loại bỏ trong release tương lai.

### 2.1. API dùng trong bài trên JDK 27

Phần API cốt lõi của JDK 27:

Đặt đoạn code này bên trong class `LazyRuleCatalogDemo`; method `loadCatalog()` được khai báo trong class thực hành ở phần sau.

~~~java
LazyConstant<RuleCatalog> catalog =
        LazyConstant.of(LazyRuleCatalogDemo::loadCatalog);

RuleCatalog value = catalog.get();
~~~

LazyConstant<T> là sealed interface mở rộng Supplier<T>. Factory of(Supplier<? extends T>) tạo holder chưa có nội dung. Lần đầu gọi get(), computing function được thực thi và kết quả trở thành nội dung bất biến của lazy constant. Những lần get() tiếp theo trả lại cùng nội dung.

### 2.2. Không dùng lại các method đã bỏ trong JDK 27

JDK 26 preview lần thứ hai từng có isInitialized() và orElse(T). Hai method này không còn trong API JDK 27 preview lần thứ ba.

| Method | JDK 26 preview | JDK 27 preview |
|---|---|---|
| LazyConstant.of(Supplier) | Có | Có |
| get() | Có | Có |
| isInitialized() | Có | Đã bỏ |
| orElse(T) | Có | Đã bỏ |

Bài thực hành chỉ dùng of() và get(). Không copy code từ preview JDK 26 có isInitialized() hoặc orElse() rồi kỳ vọng compile trên JDK 27.

## 3. Hiểu mô hình khởi tạo

### 3.1. Eager initialization

Đây là field đặt bên trong cùng class chứa method `loadCatalog()`:

~~~java
static final RuleCatalog CATALOG = loadCatalog();
~~~

Khi class được khởi tạo, loadCatalog() chạy ngay. Cách này đơn giản và phù hợp với thành phần chắc chắn được dùng trong mọi lần chạy, nhưng startup phải trả toàn bộ chi phí.

### 3.2. Initialization-on-demand holder

~~~java
private static class CatalogHolder {
    private static class Holder {
        static final RuleCatalog INSTANCE = loadCatalog();
    }

    static RuleCatalog get() {
        return Holder.INSTANCE;
    }
}
~~~

Class Holder chỉ được khởi tạo khi get() lần đầu được gọi. Java class initialization bảo đảm đồng bộ và safe publication cho static field. Đây là lựa chọn ổn định, không cần preview, phù hợp với singleton tĩnh đơn giản.

### 3.3. LazyConstant

Đây cũng là field bên trong class `LazyRuleCatalogDemo`:

~~~java
static final LazyConstant<RuleCatalog> CATALOG =
        LazyConstant.of(LazyRuleCatalogDemo::loadCatalog);

static RuleCatalog catalog() {
    return CATALOG.get();
}
~~~

Holder LazyConstant được tạo khi class khởi tạo, nhưng nội dung RuleCatalog chỉ được tính khi get() đầu tiên chạy. Sau khi đã có nội dung, JVM có thể xem lazy constant như một constant để áp dụng tối ưu tương tự final field.

LazyConstant hữu ích khi muốn giữ một tham chiếu ổn định, khởi tạo theo nhu cầu và cho JVM cơ hội tối ưu đường đọc sau khởi tạo. Nó không thay thế cache có eviction, resource pool hoặc service cần reload.

### 3.4. So sánh lựa chọn

| Cách làm | Khởi tạo | Thread safety | Tính constant sau khởi tạo | Phù hợp |
|---|---|---|---|---|
| Eager static final | Khi class được khởi tạo | Theo class initialization | Có | Thành phần luôn cần |
| Holder idiom | Khi gọi accessor lần đầu | Theo class initialization | final field | Singleton tĩnh, API stable |
| synchronized getter | Khi gọi getter lần đầu | Do monitor bảo vệ | Field thường không phải final | Logic tùy biến |
| Double-checked locking | Khi getter lần đầu | Cần volatile và đúng memory ordering | Field mutable | Chỉ khi có lý do cụ thể |
| LazyConstant | Khi gọi get() lần đầu | At-most-once, safe publication | JVM có thể constant-fold | Giá trị ổn định, tạo đắt, chỉ cần một lần |

Nếu chỉ cần một singleton tĩnh và không muốn phụ thuộc preview, holder idiom vẫn là lựa chọn tốt. Chỉ chọn LazyConstant khi lợi ích của deferred constant phù hợp với vòng đời và ràng buộc của thành phần.

## 4. Bài toán: RuleCatalog được tạo theo nhu cầu

Giả sử dịch vụ kiểm tra dữ liệu có một catalog gồm nhiều rule. Mỗi rule chứa một Pattern đã compile. Việc đọc định nghĩa, phân tích cấu hình và compile pattern tốn CPU và allocation.

Yêu cầu:

- Ứng dụng có thể khởi động mà chưa tạo catalog.
- Request đầu tiên cần kiểm tra sẽ tạo catalog.
- Các request sau dùng cùng catalog.
- Nhiều request đầu tiên chạy đồng thời vẫn chỉ tạo một catalog.
- Catalog sau khi tạo không bị thay đổi.
- Có thể đo số lần computing function chạy.

Ta dùng static final LazyConstant<RuleCatalog> và Map.copyOf() để công bố map không thể sửa qua reference trả về.

## 5. Cài đặt hoàn chỉnh

Tạo file LazyRuleCatalogDemo.java:

~~~java
import java.lang.LazyConstant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

public class LazyRuleCatalogDemo {

    private static final AtomicInteger LOAD_COUNT = new AtomicInteger();

    // Chỉ tạo holder; chưa chạy loadCatalog().
    private static final LazyConstant<RuleCatalog> RULES =
            LazyConstant.of(LazyRuleCatalogDemo::loadCatalog);

    private record RuleSpec(String name, String expression) {}

    private record Rule(String name, Pattern pattern) {}

    private record RuleCatalog(Map<String, Rule> rules) {

        RuleCatalog {
            rules = Map.copyOf(rules);
        }

        boolean matches(String ruleName, String input) {
            Rule rule = rules.get(ruleName);

            if (rule == null) {
                throw new IllegalArgumentException(
                        "Unknown rule: " + ruleName
                );
            }

            return rule.pattern().matcher(input).matches();
        }

        int size() {
            return rules.size();
        }
    }

    private static RuleCatalog loadCatalog() {
        LOAD_COUNT.incrementAndGet();

        List<RuleSpec> specs = List.of(
                new RuleSpec("invoice", "^INV-[0-9]{8}$"),
                new RuleSpec("customer", "^CUS-[A-Z0-9]{6}$"),
                new RuleSpec("postal", "^[0-9]{5}(-[0-9]{4})?$")
        );

        Map<String, Rule> rules = new HashMap<>();

        for (RuleSpec spec : specs) {
            Pattern compiled = Pattern.compile(spec.expression());
            rules.put(spec.name(), new Rule(spec.name(), compiled));
        }

        return new RuleCatalog(rules);
    }

    static boolean validateInvoice(String value) {
        return RULES.get().matches("invoice", value);
    }

    static int catalogLoadCount() {
        return LOAD_COUNT.get();
    }

    private static void verifyConcurrentInitialization() throws Exception {
        AtomicInteger concurrentLoadCount = new AtomicInteger();

        LazyConstant<RuleCatalog> concurrentRules =
                LazyConstant.of(() -> {
                    concurrentLoadCount.incrementAndGet();
                    return loadCatalog();
                });

        int threadCount = 16;
        ExecutorService executor =
                Executors.newFixedThreadPool(threadCount);

        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<RuleCatalog>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < threadCount; i++) {
                Future<RuleCatalog> future = executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return concurrentRules.get();
                });

                futures.add(future);
            }

            // Chờ các worker sẵn sàng trước khi cùng gọi get().
            ready.await();
            start.countDown();

            RuleCatalog first = futures.get(0).get();

            for (Future<RuleCatalog> future : futures) {
                RuleCatalog value = future.get();

                if (value != first) {
                    throw new AssertionError(
                            "Các thread nhận những instance khác nhau"
                    );
                }
            }

            if (concurrentLoadCount.get() != 1) {
                throw new AssertionError(
                        "Expected one computation, got "
                                + concurrentLoadCount.get()
                );
            }

            System.out.println(
                    "Concurrent computation count: "
                            + concurrentLoadCount.get()
            );
        } finally {
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(
                "Before first access: " + catalogLoadCount()
        );

        boolean valid = validateInvoice("INV-20260001");

        System.out.println("Invoice valid: " + valid);
        System.out.println(
                "After first access: " + catalogLoadCount()
        );

        validateInvoice("INV-20260002");

        System.out.println(
                "After second access: " + catalogLoadCount()
        );

        System.out.println(
                "Rule count: " + RULES.get().size()
        );

        verifyConcurrentInitialization();
    }
}
~~~

### 5.1. Kết quả mong đợi

Output có dạng:

~~~text
Before first access: 0
Invoice valid: true
After first access: 1
After second access: 1
Rule count: 3
Concurrent computation count: 1
~~~

Số lượng rule và kết quả validation được xác định bởi dữ liệu ví dụ. Điểm quan trọng là loadCatalog() chỉ chạy khi có get() đầu tiên và mỗi lazy constant chỉ chạy computing function tối đa một lần.

### 5.2. Điều gì xảy ra khi nhiều thread cùng gọi get()?

JDK chọn một thread làm computing thread. Thread đó chạy computing function trên chính thread gọi get(). Những thread cạnh tranh còn lại chờ đến khi computation hoàn tất hoặc chuyển sang error state.

Sau khi thành công:

- Mọi thread nhận cùng nội dung.
- Không có thread thứ hai chạy lại computing function.
- Kết quả được safe publication.
- Các field final bên trong object mới tạo cũng được công bố an toàn theo memory model.

Không cần tự viết synchronized, volatile hoặc double-checked locking quanh get().

## 6. Compile và run trên JDK 27

Đặt JDK 27 làm compiler và runtime. Kiểm tra phiên bản:

~~~bash
javac -version
java -version
~~~

Compile:

~~~bash
javac --release 27 --enable-preview -Xlint:preview -d out LazyRuleCatalogDemo.java
~~~

Run:

~~~bash
java --enable-preview -cp out LazyRuleCatalogDemo
~~~

Phải bật preview ở cả compile time và run time.

Không compile bằng JDK 27 rồi chạy class preview bằng JDK 26. Preview class file gắn với release đã tạo ra nó. Khi chuyển sang một JDK feature release khác, cần compile lại bằng đúng compiler và preview API của release đó.

Nếu chạy bằng JDK không hỗ trợ preview hoặc không bật --enable-preview, ứng dụng sẽ không thể dùng preview API theo yêu cầu.

## 7. Kiểm tra failure semantics của JDK 27

Đây là khác biệt quan trọng so với preview JDK 26.

### 7.1. JDK 27 chuyển sang error state khi computation thất bại

Trong JDK 27, nếu computing function:

- Ném unchecked exception hoặc Error.
- Trả về null.
- Gọi đệ quy chính lazy constant trong lúc đang tính.

thì lazy constant chuyển sang error state.

Với unchecked exception:

- Lần get() gặp lỗi ném NoSuchElementException có cause là exception ban đầu.
- Những lần get() tiếp theo cũng ném NoSuchElementException, nhưng không còn cause ban đầu.
- Computing function không được chạy lại.

Với kết quả null, JDK 27 ném NoSuchElementException có cause là NullPointerException. Lazy constant không thể chứa null.

### 7.2. Ví dụ lỗi chỉ chạy computing function một lần

~~~java
import java.lang.LazyConstant;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyFailureDemo {

    public static void main(String[] args) {
        AtomicInteger attempts = new AtomicInteger();

        LazyConstant<String> config = LazyConstant.of(() -> {
            attempts.incrementAndGet();
            throw new IllegalStateException("Invalid configuration");
        });

        for (int i = 1; i <= 2; i++) {
            try {
                config.get();
            } catch (NoSuchElementException ex) {
                System.out.println(
                        "Call " + i
                                + ", cause = "
                                + (ex.getCause() == null
                                    ? "none"
                                    : ex.getCause().getClass().getSimpleName())
                );
            }
        }

        System.out.println("Supplier attempts: " + attempts.get());
    }
}
~~~

Output kỳ vọng:

~~~text
Call 1, cause = IllegalStateException
Call 2, cause = none
Supplier attempts: 1
~~~

### 7.3. Khác biệt với JDK 26 preview

JDK 26 preview lần thứ hai có semantics khác: nếu computing function ném exception, throwable được chuyển cho caller và lazy constant vẫn chưa initialized; lần get() tiếp theo có thể thử tính lại.

JDK 27 preview lần thứ ba đổi sang error state và không retry. Không bê giả định retry từ JDK 26 sang JDK 27.

| Tình huống | JDK 26 preview | JDK 27 preview |
|---|---|---|
| Supplier ném unchecked exception | Throwable được chuyển cho caller; chưa initialized | Chuyển sang error state; get() ném NoSuchElementException |
| Lần gọi tiếp theo | Có thể thử lại computation | Không chạy supplier lại; tiếp tục ném NoSuchElementException |
| Supplier trả null | Ném NullPointerException | Ném NoSuchElementException có NullPointerException làm cause |
| Supplier gọi đệ quy | Ném IllegalStateException, không initialized | Chuyển error state; NoSuchElementException có IllegalStateException làm cause |

Vì vậy, chỉ dùng JDK 27 LazyConstant cho computation có kết quả ổn định và failure được xem là lỗi cố định của cấu hình/dữ liệu. Không dùng nó làm cơ chế retry cho network, database hoặc credential service có thể tạm thời lỗi.

### 7.4. Nếu cần giá trị nullable

Bọc nội dung bằng Optional:

~~~java
LazyConstant<Optional<RuleCatalog>> optionalCatalog =
        LazyConstant.of(() -> Optional.ofNullable(loadOptionalCatalog()));
~~~

Như vậy supplier luôn trả một object Optional không null. Giá trị nghiệp vụ có thể là Optional.empty().

## 8. Thiết kế computing function phù hợp

### 8.1. Ưu tiên computation xác định và có thể hoàn tất

Các trường hợp phù hợp:

- Compile một bộ regex hoặc parser từ cấu hình bất biến.
- Phân tích một schema nội bộ đã đóng gói cùng ứng dụng.
- Tạo bảng tra cứu immutable.
- Tạo object mô tả rule engine.
- Tính metadata đắt nhưng kết quả không thay đổi trong vòng đời ứng dụng.

Các trường hợp không phù hợp:

- Mở kết nối database hoặc HTTP cần reconnect.
- Lấy token có thể hết hạn.
- Đọc cấu hình có thể thay đổi trong runtime.
- Tạo pool cần shutdown/reinitialize.
- Load dữ liệu phụ thuộc tenant/request.
- Tác vụ cần timeout, cancellation hoặc retry.

### 8.2. Computing function chạy trên caller thread

Thread đầu tiên gọi get() sẽ chạy supplier. Vì thế request đầu tiên có thể chịu toàn bộ chi phí khởi tạo.

Nếu supplier mất 500 ms, request đầu tiên có thể tăng latency tương ứng. Những request đồng thời gọi cùng lazy constant sẽ chờ computation hoàn tất.

Nếu muốn chủ động warm up trước khi mở cổng nhận traffic, gọi get() trong startup phase. Khi đó vẫn dùng LazyConstant, nhưng chi phí được chuyển sang startup có kiểm soát.

### 8.3. Không có timeout hoặc cancellation tích hợp

Thread interruption không hủy việc khởi tạo lazy constant. get() không xóa interrupt status và không tự ném InterruptedException.

Nếu supplier block vô hạn, các thread khác gọi cùng lazy constant cũng có thể block vô hạn. LazyConstant không có timeout/cancellation API.

Do đó, không đặt một HTTP request ra ngoài hoặc chờ một service không có deadline bên trong computing function. Nếu tác vụ cần timeout, retry hoặc cancellation, hãy dùng service lifecycle/async abstraction phù hợp rồi publish một giá trị ổn định sau khi hoàn tất.

### 8.4. Checked exception cần được chuyển thành unchecked

Supplier.get() không khai báo checked exception. Nếu computation đọc file và có thể ném IOException, phải chuyển exception:

~~~java
static RuleCatalog loadCatalogFromFile(Path path) {
    try {
        return RuleCatalogParser.parse(path);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
}
~~~

Trên JDK 27, UncheckedIOException cũng khiến lazy constant đi vào error state. Nếu file có thể tạm thời không đọc được rồi phục hồi, LazyConstant không phù hợp vì không có retry sau lần thất bại.

Implementation được phép synchronize trên chính đối tượng LazyConstant. Không dùng lazy constant làm monitor hoặc khóa ứng dụng; việc đồng bộ trực tiếp hay gián tiếp trên nó có thể gây tương tác khó đoán với cơ chế nội bộ.

## 9. Dependency graph và vòng phụ thuộc

Lazy constants có thể phụ thuộc lẫn nhau:

~~~java
static final LazyConstant<RuleCatalog> RULES =
        LazyConstant.of(LazyRuleCatalogDemo::loadCatalog);

static final LazyConstant<RuleEngine> ENGINE =
        LazyConstant.of(() -> new RuleEngine(RULES.get()));
~~~

Khi gọi ENGINE.get(), RULES.get() được gọi trước để tạo dependency. Nếu chưa có catalog, catalog được tạo trước, rồi engine mới được tạo.

Tuy nhiên, dependency graph phải có hướng rõ ràng. Tránh vòng:

~~~text
A.get()
  -> tạo A
  -> B.get()
  -> tạo B
  -> A.get()
  -> quay lại A khi A chưa hoàn tất
~~~

Recursive invocation có thể đưa lazy constant vào error state. Với các static initializer phụ thuộc nhau, vòng class initialization cũng có thể dẫn đến initialization error theo JLS.

Cách xử lý:

- Vẽ dependency graph trước khi tạo lazy constants.
- Đảm bảo dependency đi theo một chiều.
- Tách interface/configuration chung khỏi implementation phụ thuộc.
- Không gọi ngược vào lazy constant đang được khởi tạo từ constructor hoặc static initializer của dependency.
- Kiểm thử cold-start theo từng entry point, không chỉ đường đi đã warm-up.

## 10. LazyConstant và constant folding

Một lazy constant sau khi khởi tạo không thể thay đổi nội dung. Vì thế JVM có thể tối ưu bằng cách loại bỏ các lần đọc nội dung sau đó và sử dụng giá trị đã quan sát; đây là constant folding.

Để lazy constant đủ điều kiện cho tối ưu này, JDK 27 mô tả đường tham chiếu từ một static final field trực tiếp tới lazy constant, hoặc một chuỗi qua các trusted fields như:

- static final fields.
- Record fields.
- Final instance fields trong hidden classes.

Ví dụ:

~~~java
static final LazyConstant<RuleCatalog> RULES =
        LazyConstant.of(LazyRuleCatalogDemo::loadCatalog);
~~~

JVM có thể tối ưu đường đọc RULES.get() sau khi nội dung đã được khởi tạo và code trở nên nóng. Đây là khả năng tối ưu, không phải cam kết rằng mọi lần gọi sẽ được constant-fold ngay lập tức.

Không thay static final bằng field mutable nếu mục tiêu là cho JVM nhận diện lazy constant như một giá trị ổn định.

## 11. Nội dung không tự động immutable

LazyConstant không thay đổi sau khi khởi tạo, nhưng object bên trong có thể mutable.

Ví dụ không nên:

~~~java
static final LazyConstant<List<String>> NAMES =
        LazyConstant.of(ArrayList::new);
~~~

Mặc dù reference trong lazy constant không đổi, ArrayList vẫn có thể bị sửa sau khi lấy ra. Điều này làm mất giả định về nội dung constant.

Nên tạo snapshot bất biến:

~~~java
static final LazyConstant<List<String>> NAMES =
        LazyConstant.of(() -> List.copyOf(loadNames()));
~~~

Tương tự với map:

~~~java
static final LazyConstant<Map<String, Rule>> RULES =
        LazyConstant.of(() -> Map.copyOf(loadRules()));
~~~

Nếu giá trị cần cập nhật theo thời gian, dùng cấu trúc quản lý state/version riêng. Không sửa object bên trong lazy constant rồi kỳ vọng JVM quan sát được một constant mới.

## 12. Quản lý bộ nhớ và vòng đời

Sau khi khởi tạo, lazy constant giữ strong reference tới nội dung. Nếu lazy constant là static final, nội dung có thể sống cùng classloader hoặc lâu hơn dự kiến.

Không dùng một lazy constant toàn cục để giữ:

- Dữ liệu riêng từng user.
- Cache không giới hạn key.
- Kết quả truy vấn theo request.
- Buffer lớn có thể giải phóng sau khi hoàn tất.
- Resource có vòng đời cần close/reload.

LazyConstant không phải Serializable. Nó cũng không có cơ chế reset hoặc remove content sau khi khởi tạo.

Đối với file handle, socket, database connection hoặc executor, cần một lifecycle owner biết khi nào đóng resource. Không dùng lazy constant như một resource pool.

## 13. Kiểm thử tích hợp

### 13.1. Test khởi tạo đúng một lần

- Tạo một lazy constant với AtomicInteger đếm số lần supplier chạy.
- Gọi get() nhiều lần tuần tự.
- Xác nhận counter bằng 1.
- Xác nhận các lần trả về là cùng instance nếu object được thiết kế singleton.

### 13.2. Test cạnh tranh đồng thời

- Tạo lazy constant mới chưa initialized.
- Dùng CountDownLatch để cho nhiều thread gọi get() gần như đồng thời.
- Thu thập tất cả kết quả.
- Xác nhận supplier chạy một lần.
- Xác nhận mọi thread nhận cùng instance.
- Xác nhận object đã công bố có các field final đúng giá trị.

Không dùng lại lazy constant đã được khởi tạo từ test tuần tự; phải tạo một lazy constant mới cho test race.

### 13.3. Test error state

- Supplier ném IllegalStateException.
- Lần get() đầu nhận NoSuchElementException có cause.
- Lần get() tiếp theo nhận NoSuchElementException không có cause.
- Counter vẫn bằng 1.
- Supplier trả null thì cause là NullPointerException.
- Supplier gọi đệ quy thì xác nhận lỗi recursive được báo và không có retry.

### 13.4. Test dependency cycle

Tạo hai component A và B phụ thuộc ngược nhau trong test riêng. Xác nhận cycle được phát hiện, test không treo vô hạn và lỗi được ghi nhận rõ. Không để class có static initialization cycle trong production chỉ để kiểm tra tình huống này.

### 13.5. Test startup và cold path

Đo:

- Thời gian tạo holder LazyConstant.
- Thời gian gọi get() lần đầu.
- Thời gian gọi get() sau khi đã khởi tạo.
- Thời gian startup khi chưa truy cập component.
- Latency request đầu tiên cần component.
- Throughput/latency khi nhiều thread đồng thời gọi lần đầu.

Đảm bảo benchmark tách cold access và warm access. Không cộng lẫn thời gian compile/JIT warmup vào chi phí khởi tạo object.

## 14. Đo hiệu năng và so sánh phương án

Một benchmark tối thiểu cần có ba biến thể:

| Biến thể | Mục tiêu đo |
|---|---|
| Eager static final | Chi phí startup khi tạo object ngay |
| Holder idiom | Chi phí lần đầu truy cập và warm access |
| LazyConstant | Chi phí lần get() đầu, warm get() và contention |

Đo trên cùng JDK 27 build, CPU, heap, workload và dữ liệu. Dùng nhiều lần chạy/fork; báo cáo median và phân vị, không chỉ một con số.

Các chỉ số nên thu thập:

- Startup/readiness time.
- First access latency.
- Warm access throughput.
- p50/p95/p99 latency khi nhiều thread tranh chấp.
- CPU time của supplier.
- Allocation rate và retained heap.
- Số lần supplier được gọi.
- Time spent waiting của các thread cạnh tranh.

Nếu ứng dụng chỉ truy cập component ngay trong startup ở mọi lần chạy, lazy initialization có thể chỉ chuyển chi phí từ startup sang request đầu tiên mà không giảm tổng CPU. Nếu nhiều lần chạy không cần component, lợi ích có thể đến từ việc tránh tạo object hoàn toàn.

Không mặc định LazyConstant nhanh hơn holder idiom ở mọi workload. Cần đo cả first access lẫn warm access, vì hai phương án có chi phí khác nhau.

## 15. Khi nào không nên dùng LazyConstant?

| Nhu cầu | Vì sao không phù hợp | Cách tiếp cận |
|---|---|---|
| Token hoặc credential có thể hết hạn | Nội dung constant không thể thay thế | Credential provider có refresh |
| Database connection cần reconnect | Lỗi đầu tiên thành error state, không retry | Connection pool/lifecycle manager |
| HTTP request có timeout | get() không có timeout/cancel | Async client và deadline |
| Cache theo key có eviction | Một lazy constant chỉ chứa một nội dung | Cache chuyên dụng |
| Cấu hình thay đổi khi runtime | Nội dung không thể thay đổi | Versioned immutable snapshot |
| Giá trị có thể null | Lazy constant không chứa null | Bọc bằng Optional |
| Thành phần cần shutdown | Không có close/reset lifecycle | Resource manager |
| Cần thử lại khi file tạm thời chưa sẵn sàng | JDK 27 không retry sau error state | Startup orchestration/retry service |

## 16. Bài tập thực hành

### Bài 1 — Đo lazy initialization

Thêm counter vào supplier và ghi thời điểm:

- Khi class được nạp.
- Khi LazyConstant holder được tạo.
- Khi get() lần đầu bắt đầu/kết thúc.
- Khi get() lần thứ hai bắt đầu/kết thúc.

Giải thích phần nào là class initialization, phần nào là computing function và phần nào là warm access.

### Bài 2 — Tăng concurrency

Thay 16 worker bằng 64 hoặc 128 worker. Giữ LazyConstant chưa initialized trước khi mở latch. Xác nhận:

- Supplier vẫn chạy một lần.
- Mọi worker nhận cùng object.
- Worker không tính lại khi chờ.
- Latency của worker đầu và worker chờ khác nhau ra sao.

### Bài 3 — Failure không retry

Tạo supplier đọc file cấu hình nhưng file chưa tồn tại. Lần get() đầu thất bại. Sau đó tạo file rồi gọi lại get().

Quan sát rằng JDK 27 lazy constant đã vào error state và supplier không chạy lại. Viết kết luận vì sao đây không phải cơ chế phù hợp cho nguồn dữ liệu có thể phục hồi.

### Bài 4 — Chuyển thành startup warmup

Tạo một method warmUp() gọi RULES.get() trong giai đoạn startup. So sánh:

- Không warmup: startup nhanh hơn nhưng request đầu tiên trả latency cao hơn.
- Warmup: startup chậm hơn nhưng request đầu tiên không phải tạo catalog.

Chọn cách phù hợp với startup SLO và request latency SLO của dịch vụ.

### Bài 5 — So sánh với holder idiom

Viết thêm implementation holder idiom cho cùng RuleCatalog. Chạy cùng test chức năng và benchmark. Nêu ưu/nhược của preview API so với stable Java class initialization.

## 17. Checklist nghiệm thu

- [ ] Đang dùng JDK 27 compiler và runtime.
- [ ] Compile/run có --enable-preview.
- [ ] Source chỉ dùng LazyConstant.of() và get() theo API JDK 27.
- [ ] Không dùng isInitialized() hoặc orElse() đã bị bỏ sau preview JDK 26.
- [ ] Computing function không chạy trước lần get() đầu.
- [ ] Nhiều thread đồng thời chỉ kích hoạt một computation.
- [ ] Kết quả được safe publication.
- [ ] Nội dung trả về không null.
- [ ] Nội dung là immutable hoặc được công bố qua immutable snapshot.
- [ ] Không có dependency cycle.
- [ ] Failure được xử lý theo error-state semantics của JDK 27.
- [ ] Không dựa vào retry sau supplier failure.
- [ ] Không đặt blocking operation không có timeout trong supplier.
- [ ] Không dùng lazy constant cho resource cần close/reload.
- [ ] Đã đo cold access, warm access và startup.
- [ ] Đã đánh giá rủi ro preview trước khi dùng trong production.

## 18. Kết luận

LazyConstant cho phép giữ một giá trị được tính khi cần, chỉ khởi tạo tối đa một lần và trở thành immutable sau khi có kết quả. JDK có thể xem nội dung đã khởi tạo như constant để áp dụng các tối ưu tương tự final field.

Trên JDK 27, cần nhớ:

- LazyConstant là preview lần thứ ba theo JEP 531.
- API dùng trong bài là LazyConstant.of(Supplier) và get().
- isInitialized() và orElse() của preview JDK 26 đã bị bỏ.
- Một thread chạy computing function; các thread cạnh tranh chờ kết quả.
- Kết quả được safe publication.
- Supplier ném unchecked exception hoặc trả null khiến lazy constant chuyển sang error state; không có retry.
- Supplier chạy trên caller thread; không có timeout hoặc cancellation tích hợp.
- Nội dung được giữ bằng strong reference và không thể reset.
- Dùng immutable object và tránh dependency cycle.
- Chỉ chấp nhận preview khi đã khóa JDK release, kiểm thử tương thích và có phương án thay thế.

Với một catalog/parser đắt, bất biến và có thể tạo an toàn một lần, LazyConstant giúp tránh chi phí startup cho thành phần chưa dùng và cho JVM cơ hội tối ưu đường truy cập sau khi khởi tạo. Với dữ liệu cần retry, reload, timeout hoặc quản lý resource, hãy dùng abstraction có lifecycle phù hợp.

## Tài liệu tham khảo chính thức

- [JDK 27 Release Notes — Lazy Constants (Third Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531)
- [LazyConstant — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [Lazy Constants — Java SE 27 Core Libraries Developer Guide](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html)
- [LazyConstant — Java SE 26 API (Second Preview, for migration comparison)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [JEP 526 — Lazy Constants (Second Preview, JDK 26)](https://openjdk.org/jeps/526)
- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Preview Features — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-and-vm-features.html)
- [JLS `12 — Initialization of Classes and Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-12.html)
- [JLS `17.4.5 — Happens-before Order](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-17.html)

