# Đo số lần gọi, thời gian và tỷ lệ lỗi bằng Aspect-Oriented Programming (AOP)

## 1. Vì sao cần đo ở điểm cắt ngang?

Khi quan sát một chương trình, ba câu hỏi căn bản là:

1. **Một thao tác đã được gọi bao nhiêu lần?** Trả lời bằng bộ đếm (`call count`) và tốc độ gọi (`calls per second`).
2. **Mỗi thao tác mất bao lâu?** Trả lời bằng độ trễ (`latency`), tổng thời gian và phân phối thời gian; khi phù hợp còn phân biệt thời gian thực (`wall-clock elapsed time`) với thời gian CPU.
3. **Có bao nhiêu thao tác thất bại?** Trả lời bằng bộ đếm lỗi và tỷ lệ lỗi với một mẫu số được định nghĩa rõ.

Các phép đo này thường áp dụng cho nhiều phương thức hoặc thao tác, vì thế rất phù hợp với **Aspect-Oriented Programming (AOP)**. Một aspect gom logic quan sát vào một nơi và áp dụng nó tại nhiều điểm nối (`join point`), thay vì rải lệnh tăng counter và xem đồng hồ vào mọi thân phương thức nghiệp vụ. Những khái niệm quan trọng gồm:

- **Join point:** thời điểm/điểm thực thi có thể được can thiệp, ví dụ gọi phương thức hoặc thực thi phương thức; tập join point khả dụng tùy cơ chế AOP.
- **Pointcut:** điều kiện chọn join point nào cần đo.
- **Advice:** hành vi chạy trước, sau, khi trả kết quả, khi ném lỗi, hoặc bao quanh join point.
- **Around advice:** có thể bắt đầu phép đo, cho thao tác gốc thực thi, ghi nhận kết quả rồi trả nguyên giá trị hoặc ném lại lỗi. Nó thích hợp để quan sát kết quả thành công và thất bại trên cùng một đường code.
- **Weaving / proxy / instrumentation:** các cơ chế gắn advice vào luồng thực thi. Phạm vi chặn được lời gọi có thể khác nhau; cần xác minh điểm nào thực tế đã được instrument.

Mục tiêu không phải chỉ “in ra đã gọi”, mà là tạo **số đo có nghĩa, có thể so sánh và không làm đổi hợp đồng nghiệp vụ**.

## 2. Định nghĩa số đo trước khi viết advice

### 2.1 Số lần gọi khác số lần hoàn tất

Giả sử một request bắt đầu nhưng phải chờ I/O trong 10 giây. Trong khoảng chờ, hệ thống đã nhận một lần gọi, nhưng chưa có kết quả cuối. Do đó nên tách:

- `started_total`: số thao tác bắt đầu đi qua điểm đo.
- `completed_total`: số thao tác kết thúc và đã được ghi nhận.
- `failed_total`: số thao tác kết thúc theo định nghĩa lỗi.
- `in_flight`: số thao tác đang thực hiện. Trong cùng tập đối tượng đo và cùng cửa sổ tích lũy, về mặt khái niệm `in_flight ≈ started_total − completed_total`; cần tính đến snapshot không nguyên tử và chính sách hủy.
- `duration_seconds` hoặc `duration_nanos`: thời gian từng thao tác đã hoàn tất; dùng histogram hoặc cấu trúc tổng hợp để xem phân phối.

Nếu nói “số lần gọi” nhưng thực chất tăng counter ở `finally`, counter đó đếm **lần hoàn tất**, không phải số lần bắt đầu. Cả hai đều hữu ích, nhưng không được đặt nhầm tên.

### 2.2 Công thức tỷ lệ lỗi và mẫu số

Trong một khoảng thời gian được xác định trước:

`error_rate = failed / completed × 100%`

Ví dụ, có 240 thao tác kết thúc và 12 thao tác được phân loại lỗi: tỷ lệ lỗi là `12 / 240 × 100% = 5%`. Nếu không có thao tác hoàn tất (`completed = 0`), tỷ lệ lỗi **không xác định**; hiển thị “N/A”/không xuất rate sẽ trung thực hơn là giả vờ có 0% lỗi.

Mẫu số phải phù hợp mục tiêu:

| Chỉ số | Mẫu số / đơn vị | Phản ánh điều gì |
| --- | --- | --- |
| Tỷ lệ lỗi theo lần thực hiện (`attempt error rate`) | Mọi attempt đã hoàn tất | Xác suất một attempt thất bại, kể cả các lần retry |
| Tỷ lệ lỗi theo tác vụ logic (`operation error rate`) | Các yêu cầu logic đã kết thúc | Xác suất người dùng cuối nhận kết quả lỗi sau chính sách retry |
| Tỷ lệ lỗi theo request đến (`request failure rate`) | Số request có trạng thái cuối trong cửa sổ | Chất lượng phục vụ request; cần quy tắc trạng thái và timeout |
| Tốc độ lỗi (`error throughput`) | Số lỗi / giây | Tải lỗi tuyệt đối; **khác** tỷ lệ lỗi phần trăm |
| Tỷ lệ theo một phương thức | Lần hoàn tất của riêng phương thức đó | Chất lượng của từng điểm cắt ngang |

Nếu 1 request được thử tối đa ba lần, hai lần đầu lỗi và lần thứ ba thành công, ta có ba attempt, hai attempt lỗi, nhưng một tác vụ logic cuối cùng thành công. Trộn các cấp đo này sẽ làm dashboard hoặc cảnh báo sai lệch.

**Định nghĩa “lỗi” phải công khai:** exception thoát khỏi phương thức, một kết quả mang trạng thái thất bại, timeout, cancellation, mã trạng thái giao thức, hay một điều kiện domain cụ thể? Ví dụ mã nghiệp vụ “không tìm thấy” có thể là phản hồi hợp lệ thay vì lỗi hệ thống; ngược lại, phương thức trả về một đối tượng `Result.failure(...)` vẫn là lỗi dù không hề ném exception.

### 2.3 Đo thời gian với đồng hồ phù hợp

Khi tính **độ dài một khoảng** trong một JVM, dùng `System.nanoTime()`:

~~~java
long startedAt = System.nanoTime();
try {
    return operation.run();
} finally {
    long elapsedNanos = System.nanoTime() - startedAt;
    recordDuration(elapsedNanos);
}
~~~

Đây là **đoạn mã minh họa**: `operation` và `recordDuration` phải được cung cấp ở nơi sử dụng. `nanoTime()` dùng để đo khoảng thời gian tương đối, không phải dấu thời gian tuyệt đối. `System.currentTimeMillis()` dành cho thời điểm lịch và có thể bị điều chỉnh theo đồng hồ hệ thống; không nên lấy hai mốc thời gian lịch để thay phép đo elapsed khi cần độ ổn định.

Khoảng `elapsed` ở ví dụ là **wall-clock elapsed time**: nó tính cả lúc thread chờ lock, chờ I/O, bị scheduler tạm ngừng hoặc bị chặn. Không được gọi nó là “CPU time”. Thời lượng đo chính xác phụ thuộc điểm bắt đầu/kết thúc: chỉ thân phương thức, cả proxy/advice, hay toàn vòng đời tác vụ bất đồng bộ.

## 3. Vị trí đặt advice và những gì được đếm

Với một thao tác đồng bộ, mẫu đo quanh phương thức là:

~~~text
caller
  -> [điểm AOP: bắt đầu]
       -> tăng started
       -> lấy mốc nanoTime
       -> thực thi thao tác gốc đúng một lần
          -> thành công HOẶC ném exception
       -> ghi duration và kết quả
       -> tăng completed
     [kết thúc advice]
  -> caller nhận nguyên kết quả hoặc lỗi
~~~

Advice trước (`before`) có thể đếm lời gọi nhưng không trực tiếp biết kết quả. Advice sau khi trả (`after returning`) chỉ bao phủ lần trả thành công, trong khi advice khi ném (`after throwing`) cho thấy exception. **Around advice kết hợp cả hai nhánh** và hữu ích khi cần đo một khoảng thời gian duy nhất cho tất cả đường kết thúc.

Những quy tắc nền tảng:

- Thực thi logic gốc đúng **một lần** nếu phép đo là quan sát thuần túy. Gọi lại vì telemetry có thể nhân đôi side effect.
- Trả đúng giá trị, đúng kiểu và giữ exception gốc, không biến exception nghiệp vụ thành giá trị thành công hoặc ngoại lệ phản chiếu (`InvocationTargetException`).
- Ghi nhận cả đường thoát bất thường; `finally` giúp không bỏ sót duration khi thao tác ném lỗi.
- Tránh đo lặp ở các lớp lồng nhau nếu mục tiêu là đếm request logic một lần. Một lời gọi ngoài có thể đi qua nhiều join point; mỗi join point được đo sẽ tạo bộ đếm riêng.
- Quy định có đo lời gọi `Object.toString()`, `equals()`, getter, phương thức nội bộ, hay chỉ public API. Một số cơ chế proxy chỉ chặn được các lời gọi đi qua proxy; lời gọi nội bộ gọi trực tiếp trên đối tượng có thể không đi qua nó.
- Nếu aspect gọi thư viện metrics nhưng chính thư viện ấy lại bị cùng pointcut bắt, có thể xuất hiện đệ quy vô hạn. Loại trừ code instrumentation hoặc dùng guard tái nhập khi cần.

## 4. Ví dụ Java 17+: advice đo cuộc gọi, thời lượng và tỷ lệ lỗi

Ví dụ này dùng **JDK dynamic proxy** để biểu diễn around advice đối với phương thức của interface. Không cần thư viện AOP ngoài JDK. Kết quả được lưu bằng `ConcurrentHashMap` và `LongAdder` để hỗ trợ nhiều thread cập nhật. Chương trình gọi một thao tác thành công hai lần và cố ý tạo một lỗi một lần.

**Tệp `AopMetricsDemo.java`:**

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class AopMetricsDemo {
    public interface Catalog {
        String lookup(String code);
    }

    public static final class CatalogImpl implements Catalog {
        @Override
        public String lookup(String code) {
            if ("missing".equals(code)) {
                throw new IllegalArgumentException("not found");
            }
            return code.toUpperCase(Locale.ROOT);
        }
    }

    public static final class Stats {
        private final LongAdder completed = new LongAdder();
        private final LongAdder errors = new LongAdder();
        private final LongAdder durationNanos = new LongAdder();

        void record(long duration, boolean failed) {
            durationNanos.add(Math.max(0L, duration));
            if (failed) {
                errors.increment();
            }
            completed.increment();
        }

        long completed() {
            return completed.sum();
        }

        long errors() {
            return errors.sum();
        }

        double errorRatePercent() {
            long count = completed();
            return count == 0 ? Double.NaN : errors() * 100.0 / count;
        }

        double averageMillis() {
            long count = completed();
            return count == 0 ? Double.NaN
                : durationNanos.sum() / 1_000_000.0 / count;
        }
    }

    public static final class MetricsAdvice implements InvocationHandler {
        private final Object target;
        private final ConcurrentHashMap<String, Stats> registry;

        MetricsAdvice(Object target, ConcurrentHashMap<String, Stats> registry) {
            this.target = target;
            this.registry = registry;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            // Không tính các phương thức Object vào nghiệp vụ.
            if (method.getDeclaringClass() == Object.class) {
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException ex) {
                    throw ex.getCause();
                }
            }

            String key = method.toGenericString();
            Stats stats = registry.computeIfAbsent(key, ignored -> new Stats());

            long startedAt = System.nanoTime();
            boolean failed = true;
            try {
                Object result = method.invoke(target, args);
                failed = false;
                return result;
            } catch (InvocationTargetException ex) {
                // Phản chiếu bọc lỗi; đưa lại đúng lỗi gốc cho caller.
                throw ex.getCause();
            } finally {
                stats.record(System.nanoTime() - startedAt, failed);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Stats> registry = new ConcurrentHashMap<>();

        Catalog service = (Catalog) Proxy.newProxyInstance(
            Catalog.class.getClassLoader(),
            new Class<?>[] { Catalog.class },
            new MetricsAdvice(new CatalogImpl(), registry)
        );

        System.out.println(service.lookup("a1"));
        try {
            service.lookup("missing");
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
        System.out.println(service.lookup("b2"));

        String key = Catalog.class
            .getMethod("lookup", String.class)
            .toGenericString();
        Stats snapshot = registry.get(key);

        System.out.printf(
            Locale.ROOT,
            "completed=%d errors=%d errorRate=%.1f%%%n",
            snapshot.completed(),
            snapshot.errors(),
            snapshot.errorRatePercent()
        );
        // Có thể lấy snapshot.averageMillis() để xem độ trễ trung bình.
    }
}
~~~

Chạy với JDK 17 hoặc mới hơn:

~~~bash
javac AopMetricsDemo.java
java AopMetricsDemo
~~~

**Stdout xác định trong ví dụ đơn luồng:**

~~~text
A1
error=not found
B2
completed=3 errors=1 errorRate=33.3%
~~~

Tại sao các số đúng?

- Ba lần gọi `lookup` đi qua proxy đều chạy `method.invoke(target, args)` đúng một lần.
- Một lần thao tác gốc ném `IllegalArgumentException`; `InvocationTargetException` chỉ là lớp bọc của Java Reflection và được mở ra bằng `getCause()` để caller nhận lại lỗi gốc.
- `finally` ghi duration và trạng thái ở cả nhánh bình thường lẫn nhánh lỗi. `completed = 3`, `errors = 1`, nên `errorRate = 1/3 × 100 ≈ 33,3%`.
- `durationNanos` có được đo, nhưng kết quả thời gian phụ thuộc CPU, scheduler và tải máy; **không có giá trị millisecond cố định** để đưa vào stdout. `averageMillis()` tính trung bình của các lần hoàn tất.
- `method.toGenericString()` được dùng làm khóa cho riêng chữ ký phương thức; cách này tránh gộp nhầm các overload cùng tên trong ví dụ.

**Giới hạn của ví dụ:** Đây là một kỹ thuật gắn advice bằng dynamic proxy trên interface; nó chỉ đo lời gọi **đi qua proxy**. Nó không tự chặn lời gọi trực tiếp trên `CatalogImpl` hoặc lời gọi nội bộ không đi qua proxy. Nó đo **thời gian gọi đồng bộ**; nếu phương thức chỉ trả về `Future`/`CompletionStage` hoặc một nguồn sự kiện, duration trên chỉ là thời gian tạo và trả đối tượng bất đồng bộ. Ở ứng dụng lớn, cần thêm chính sách telemetry failure, tagging, histogram và cấu hình điểm cắt ngang.

### Lưu ý về bộ đếm nhiều thread

`LongAdder` thích hợp khi có nhiều thread đồng thời tăng counter, nhưng `sum()` **không là ảnh chụp nguyên tử** của toàn bộ các counter. Một bộ đọc có thể thấy `errors` và `completed` ở các thời điểm sát nhau; giá trị tỷ lệ trong lúc có lưu lượng là gần đúng tại một thời điểm. Không dùng sự chênh nhất thời giữa các counter để kết luận hệ thống đã vi phạm logic. Nếu cần tổng kết giao dịch tài chính chính xác, dùng nguồn sự kiện/ghi nhận nhất quán hơn, thay vì lấy một metrics scrape làm dữ liệu kế toán.

Tương tự, ba lần gọi trực tiếp trong demo không định nghĩa tốc độ gọi. Để tính `calls/second`, cần thêm khoảng thời gian đo hoặc tính `rate` từ chênh lệch bộ đếm giữa các mẫu liên tiếp.

## 5. Khi số liệu được đo trên tác vụ bất đồng bộ

Một around advice ngay tại phương thức không nhất thiết quan sát được lúc thao tác thực sự hoàn tất.

### 5.1 Với CompletionStage / CompletableFuture

Giả sử phương thức `fetch()` trả về `CompletionStage<Result>`. Lời gọi có thể chỉ tạo stage rồi trả ngay. Đếm “success” tại lúc trả stage sẽ sai nếu stage hoàn tất thất bại sau đó.

Một thiết kế quan sát hợp lý:

1. Khi lời gọi tạo tác vụ, ghi `started` và mốc thời gian.
2. Khi stage hoàn tất, ghi kết quả, độ trễ end-to-end và `completed` **một lần**.
3. Nếu stage hoàn tất exceptional, phân loại lỗi theo **nguyên nhân gốc và chính sách nghiệp vụ**, tránh đếm `CompletionException` chỉ như một mã lỗi chung.
4. Nếu stage bị hủy, định nghĩa riêng trạng thái `cancelled` và quyết định rõ nó có được tính vào `failed` hay không.
5. Tránh để callback telemetry ném exception ảnh hưởng kết quả mà caller quan sát.

**Mã khái niệm**, minh họa một biến thể của advice dành cho stage (không phải chương trình độc lập):

~~~java
long startedAt = System.nanoTime();
CompletionStage<Result> stage = proceedAndGetStage();

stage.whenComplete((result, error) -> {
    long elapsed = System.nanoTime() - startedAt;
    try {
        telemetry.recordCompletion(elapsed, error);
    } catch (RuntimeException telemetryError) {
        // Ghi nhận ở kênh dự phòng phù hợp; không thay kết quả gốc.
    }
});
return stage;
~~~

`proceedAndGetStage()`, `Result` và `telemetry` là thành phần giả định của ứng dụng. Việc bỏ qua stage phụ thuộc được trả về từ `whenComplete` giúp caller nhận **chính stage gốc**, nhưng callback vẫn được đăng ký để quan sát. Cách xử lý lỗi telemetry cụ thể phải phù hợp chính sách: không nên để lỗi instrumentation lan tới thread xử lý hoàn tất hoặc làm thay đổi trạng thái nghiệp vụ.

Điểm tinh tế: `whenComplete` có thể chạy trên thread hoàn tất stage và đôi khi chạy ngay nếu stage đã xong. Không thực hiện I/O chặn nặng, ghi log khối lượng lớn hoặc xử lý histogram tốn kém trong callback này.

### 5.2 Với luồng sự kiện nhiều phần tử

Một publisher có thể đăng ký nhiều subscriber, phát nhiều `onNext`, gặp `onError` hoặc `onComplete` và nhận `cancel`. Cần chọn **đơn vị đo**:

| Đơn vị | Bắt đầu | Kết thúc | Có thể đo |
| --- | --- | --- | --- |
| Tạo đối tượng nguồn sự kiện | Lời gọi phương thức trả publisher | Phương thức trả về | Chi phí tạo nguồn, không phải thời gian chạy stream |
| Một subscription | `subscribe` / `onSubscribe` theo hợp đồng đo | `onComplete`, `onError` hoặc cancellation theo chính sách | Thời gian vòng đời subscription; số terminal/error/cancel |
| Một sự kiện | Sự kiện được phát hoặc callback `onNext` bắt đầu | Callback xử lý xong, hoặc ack nghiệp vụ | Tốc độ giao/nhận và thời gian xử lý mỗi phần tử |
| Một request logic đi qua nhiều nguồn | ID request bắt đầu | Có kết quả cuối cho request | Độ trễ end-to-end và trạng thái cuối người dùng nhận |

Phải giữ nguyên cơ chế **backpressure**: advice theo dõi không được tự tăng `request(n)`, tạo subscriber phụ chỉ để đếm, hoặc giữ bộ đệm vô hạn. Số sự kiện nhận được sau một subscription không tương đương số lời gọi API ban đầu. Với một nguồn được đăng ký ba lần, số kết quả có thể khác nhau tùy nguồn là nóng/lạnh và side effect của lần subscribe.

### 5.3 Đồng bộ và bất đồng bộ dùng hai “thời gian” khác nhau

Một API async có thể cần hai histogram: `submit_latency` (thời gian tạo/trả stage hoặc publisher) và `completion_latency` (thời gian đến kết quả cuối). Nếu đặt cùng tên mà không phân biệt, dashboard sẽ trộn những đại lượng không cùng nghĩa. Với thao tác timeout, độ trễ nên được gắn trạng thái timeout và xét rõ thời gian từ mốc nào đến mốc nào.

## 6. Average, percentiles và histogram: đọc độ trễ đúng cách

Từ các lần hoàn tất có thời gian `d1, d2, ..., dn`:

- **Tổng thời gian:** `sum(d_i)`, hữu ích để tính trung bình trên đúng tập.
- **Mean (trung bình):** `sum(d_i) / n` nếu `n > 0`. Nó dễ bị kéo lên bởi vài lần rất chậm.
- **Min/max:** giúp biết biên nhưng không cho thấy toàn bộ phân phối.
- **p50:** khoảng phân vị 50%; một nửa quan sát có độ trễ không vượt giá trị này theo quy ước ước lượng đã chọn.
- **p95/p99:** khoảng phân vị cao; thể hiện trải nghiệm của những lần chậm hơn. Kết quả là **ước lượng** nếu dùng histogram/xấp xỉ.

Ví dụ có mười lần đo (ms): `1, 1, 2, 2, 2, 3, 3, 4, 5, 100`. Trung bình là `12,3 ms` dù chín lần đầu đều tối đa 5 ms. Vì vậy “trung bình 12,3 ms” che khuất phần đuôi 100 ms. Nên theo dõi histogram và phân vị phù hợp mục tiêu chất lượng phục vụ.

Trong hệ thống tải cao, không giữ mọi sample vô hạn. Có thể dùng histogram với các bucket đã được chọn theo SLO hoặc một bộ phác họa phân phối có giới hạn bộ nhớ. Nếu thống kê cho nhiều instance:

- Tổng `calls`, `errors` và tổng duration có thể cộng sau khi đã chuẩn hóa đơn vị, nhãn và cửa sổ.
- **Không lấy trung bình đơn giản của trung bình từng instance** nếu lưu lượng khác nhau; hãy dùng trung bình có trọng số theo số lần hoàn tất.
- **Không tính p99 toàn hệ thống bằng trung bình cộng p99 của các instance**. Cần gộp histogram hoặc bản tóm lược phân phối có thuật toán hỗ trợ merge và cùng định nghĩa bucket.
- Mọi so sánh trước/sau cần cùng loại operation, tập trạng thái, định nghĩa lỗi, đơn vị thời gian và độ dài cửa sổ.

## 7. Thiết kế khóa metrics, nhãn và cửa sổ thời gian

Một metric thường gồm: **tên + bộ nhãn cố định + giá trị**. Ví dụ khái niệm:

~~~text
operation_completed_total{operation="catalog.lookup",outcome="success"} 920
operation_completed_total{operation="catalog.lookup",outcome="error"} 30
operation_duration_seconds_count{operation="catalog.lookup"} 950
operation_duration_seconds_sum{operation="catalog.lookup"} 12.4
~~~

Đây là **ví dụ cấu trúc dữ liệu metrics**, không phải stdout từ chương trình `AopMetricsDemo`. Tổng 950 lần hoàn tất, 30 lỗi cho tỷ lệ khoảng `3,16%` trên tập dữ liệu này. Tổng duration 12,4 giây trên 950 lần cho trung bình khoảng `13,05 ms`; nếu tổng duration chỉ tính lần thành công, mẫu số cũng phải đổi để nhất quán.

### Các nhãn nên và không nên gắn

**Nên:** tên thao tác cố định, nhóm endpoint đã chuẩn hóa, loại lỗi theo danh mục hữu hạn, môi trường chạy, trạng thái thành công/thất bại.

**Cẩn thận hoặc tránh:** ID request, email, user ID, URL có token, chuỗi SQL động, giá trị đầu vào tự do, stack trace đầy đủ, tên tệp ngẫu nhiên. Mỗi giá trị nhãn khác nhau tạo thêm series và có thể gây **cardinality explosion**, tăng bộ nhớ và chi phí lưu trữ. Thông tin định danh và dữ liệu nhạy cảm còn gây rủi ro bảo mật. Dùng log/traces có phân quyền thích hợp cho chi tiết từng yêu cầu, còn metrics nên tổng hợp theo danh mục thấp cardinality.

### Counter tích lũy và số liệu trong một khoảng

Một counter thường chỉ tăng từ lúc process khởi động. **Số gọi trong 5 phút** là chênh lệch counter trong cửa sổ 5 phút, có xử lý reset do khởi động lại; **tỷ lệ lỗi 5 phút** được tính từ chênh lệch `failed_total` chia chênh lệch `completed_total` cùng cửa sổ và cùng tập nhãn.

Không lấy `failed_total / completed_total` từ khi ứng dụng chạy để đại diện cho “tình trạng 5 phút vừa qua”: lỗi lịch sử có thể che khuất sự cố mới. Cửa sổ quá ngắn tạo nhiễu với lưu lượng ít; cửa sổ quá dài phản ứng chậm. Cảnh báo thường cần cả **tỷ lệ lỗi và số mẫu tối thiểu** để tránh diễn giải quá mức khi chỉ có một request thất bại.

## 8. Các bẫy AOP nâng cao làm sai số liệu

| Bẫy | Ví dụ | Khắc phục |
| --- | --- | --- |
| Chọn pointcut quá rộng | Instrument cả collector làm collector tự gọi chính nó | Loại trừ mã instrumentation và giới hạn API cần đo |
| Chặn nhiều tầng | Một request đi qua API, service, repository, tạo ba count | Đặt metric theo tên tầng; định nghĩa request-level riêng |
| Gọi gốc hai lần | Advice vô ý `proceed()` lần thứ hai | Chỉ thực thi một lần cho advice đo thuần túy |
| Bỏ nhánh lỗi | Chỉ cập nhật metric khi nhận `return` bình thường | Bắt cả trả thành công và ném lỗi; ghi ở `finally` |
| Bọc exception mới | Caller nhận loại exception lạ | Bảo toàn lỗi gốc và stack/causal chain |
| Telemetry có lỗi | Registry báo lỗi, ném exception ngay trong `finally` | Có fallback rõ ràng; cô lập lỗi quan sát theo chính sách |
| Giá trị trả async | Tăng success ngay khi nhận một future chưa xong | Gắn callback vòng đời và định nghĩa terminal |
| Nhiều thread | `count++` chạy song song gây mất cập nhật | Dùng atomic/adder, snapshot nhất quán theo nhu cầu |
| Đồng hồ không phù hợp | Dùng thời gian lịch giữa hai mốc elapsed | Dùng `nanoTime()` để lấy chênh lệch thời gian |
| Trộn các đơn vị | Nơi ghi nano giây, nơi ghi mili giây vào một metric | Chuẩn hóa tên và đơn vị (ví dụ giây cho exported duration) |
| Nhãn quá chi tiết | Một metric theo user ID hoặc URL đầy đủ | Dùng nhãn nhóm có cardinality thấp |
| Retry và cache | Retry làm tăng attempts; cache tránh gọi DB | Phân tầng logical operations, attempts, cache hits |
| Sampling thiếu cân nhắc | Chỉ lấy 1/100 mẫu nhưng trình bày như tổng số thực | Đếm counter chính xác khi có thể; ghi rõ xác suất mẫu và sai số |
| Nguồn đo tác động tải | Log từng lời gọi bằng I/O đồng bộ | Batch/aggregate telemetry có giới hạn, đo overhead thực tế |

### Mức overhead và hiện tượng observer effect

AOP không miễn phí: lựa chọn điểm cắt, proxy, đo `nanoTime`, ghi bảng metrics, tạo nhãn, lấy stack trace hay gửi dữ liệu ra ngoài đều tốn CPU và bộ nhớ. Nếu thao tác gốc chỉ vài microsecond, chi phí advice có thể chiếm phần lớn kết quả. Khi đo, nên:

1. Tránh cấp phát object hoặc format chuỗi trên mỗi lần gọi nếu chỉ cần đếm.
2. Lấy `nanoTime()` tối thiểu hai lần; không ghi log đồng bộ dưới lock nóng.
3. Tránh vừa ghi duration, vừa thực hiện telemetry nặng **bên trong khoảng thời gian đang đo** nếu mục tiêu là thời gian nghiệp vụ. Trong ví dụ, `Stats` được lấy trước mốc bắt đầu, rồi ghi sau mốc kết thúc.
4. Cân nhắc số phương thức bị đo, chi phí khởi tạo proxy và độ chính xác cần thiết. Với thao tác cực ngắn, benchmark phương thức có/không advice để biết overhead.
5. Với yêu cầu độ tin cậy cao, xác định telemetry gặp lỗi thì fail-open hay fail-closed; thường giám sát không nên làm thay đổi kết quả nghiệp vụ, nhưng quyết định cần theo chính sách cụ thể.

Các số đo latency của proxy cũng có thể bị ảnh hưởng bởi JIT warm-up, GC, contention, CPU throttling và tình trạng tải. Một số lần chạy demo không chứng minh được đặc tính hiệu năng của production.

## 9. Kiểm thử độ đúng của advice và metric

### Kiểm thử đơn vị

Tạo một thao tác trả kết quả cố định, một thao tác ném exception xác định, rồi xác minh:

- Mỗi thao tác gốc được gọi đúng một lần, return value và exception gốc được giữ nguyên.
- Số completed tăng một lần cho mỗi kết thúc; số failed tăng đúng những kết thúc được định nghĩa là lỗi.
- Không có lần gọi: tỷ lệ lỗi là không xác định (`NaN` hoặc N/A), không chia cho 0.
- Duration không âm theo biểu diễn lưu trữ, đơn vị nhất quán; với clock có thể thay thế trong thiết kế test, kiểm tra chính xác duration thay vì dựa vào `Thread.sleep`.
- Lời gọi không qua proxy không vô tình được tính vào metric; các method `Object` được xử lý theo chủ đích.
- Khi có hai overload/operation, khóa metric không vô tình gộp hai tập số đo khác nhau.

### Kiểm thử cạnh tranh và tải

Dùng nhiều thread đồng thời gọi cùng một điểm cắt để tìm mất cập nhật, tranh chấp trên registry và ảnh hưởng overhead. Nếu mỗi thread chạy `m` thao tác và có `t` thread, sau khi **tất cả thread đã kết thúc và mọi ghi metrics hoàn tất**, tổng completed dự kiến là `m × t` (trừ những lần bị loại trừ theo cấu hình). Trong lúc luồng đang chạy, snapshot của nhiều counter có thể lệch ngắn hạn; test chỉ nên kiểm tra invariant cuối sau khi tất cả cập nhật đã hoàn tất.

### Kiểm thử vòng đời bất đồng bộ

Xác minh kết quả hoàn tất thành công, exceptional completion, cancel, timeout, task chưa hoàn tất, completion ngay lập tức và race giữa callback. Mục tiêu là một logical operation có đúng một terminal outcome, không tăng success ngay tại lúc trả stage, và không bỏ sót duration của lần đã được tính là completed. Với streaming, kiểm tra hủy và error theo từng subscription, không giả định một lời gọi tạo publisher tương ứng duy nhất một subscriber.

### Kiểm thử chất lượng số đo sau triển khai

So sánh counter AOP với số giao dịch/trace ở tầng biên phù hợp, phân tích sai lệch do sampling, retry, cache và pointcut. Kiểm tra dashboard theo khoảng thời gian: tỷ lệ lỗi gần 0% ở tải lớn có đúng không, tình trạng ít request có bị gây hiểu lầm không, p95/p99 có bị trộn loại thao tác, histogram có đủ độ phân giải tại ngưỡng chất lượng không. Đặt cảnh báo dựa trên số đo đồng nhất, có chú thích đơn vị và ý nghĩa mẫu số.

## 10. Tổng kết kiến thức cần nhớ

- **Số lần bắt đầu**, **số lần hoàn tất**, **số lần lỗi** là ba counter khác nhau; chỉ tính tỷ lệ lỗi khi mẫu số, thời gian và quy tắc phân loại được nêu rõ.
- **Around advice** đo thao tác đồng bộ bằng `nanoTime()` trước/sau, chuyển tiếp kết quả và lỗi gốc. `finally` giúp ghi nhận cả trường hợp ném exception.
- Với **bất đồng bộ**, việc trả stage/publisher chưa phải kết thúc; gắn đo đạc với vòng đời hoàn tất, subscription hoặc event tùy đối tượng cần đo.
- **Độ trễ trung bình** không đủ phản ánh đuôi phân phối; dùng histogram và p95/p99 khi bài toán cần phân tích các lần chậm.
- **Quan sát phải có chi phí và phạm vi được kiểm soát:** tránh pointcut quá rộng, đếm kép, counter không an toàn đa luồng, nhãn vô hạn và telemetry làm thay đổi hành vi nghiệp vụ.

Một aspect đo lường đúng là aspect có **định nghĩa số liệu rõ ràng**, **đặt tại điểm thực thi phù hợp** và **giữ nguyên ngữ nghĩa của chương trình được quan sát**.