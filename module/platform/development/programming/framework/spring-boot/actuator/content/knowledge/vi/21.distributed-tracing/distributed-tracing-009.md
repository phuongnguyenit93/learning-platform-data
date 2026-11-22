# Tạo span tùy chỉnh và ghi nhận lỗi theo phạm vi thao tác

## 1. Span cần phản ánh một thao tác có ý nghĩa

Một yêu cầu đặt hàng có thể mất nhiều thời gian vì kiểm tra tồn kho, tính phí giao hàng hoặc gọi cổng thanh toán. Span HTTP cho biết tổng thời gian xử lý; các span nghiệp vụ giúp xác định bước nào chậm và bước nào thất bại.

**Span tùy chỉnh (custom span)** là đơn vị truy vết do ứng dụng chủ động tạo cho một thao tác cần quan sát. Ranh giới của nó nên trùng với việc mà người vận hành muốn hỏi: “giữ hàng mất bao lâu?”, “lần gọi kho này có thất bại không?”. Không cần tạo span cho từng getter, setter hoặc từng dòng lệnh.

Các thuật ngữ cần phân biệt:

| Thuật ngữ | Vai trò trong bài |
| --- | --- |
| Trace | Tập hợp các span có quan hệ, mô tả đường đi của một lần xử lý |
| Span | Một thao tác có tên, thời điểm bắt đầu/kết thúc và dữ liệu truy vết |
| Span cha/con | Quan hệ giữa thao tác bao ngoài và một thao tác thành phần |
| Phạm vi hiện hành (scope) | Khoảng mà một span được đặt làm span hiện tại của ngữ cảnh thực thi |
| Thuộc tính (tag) | Cặp khóa–giá trị mô tả thao tác |
| Sự kiện (event) | Mốc xảy ra trong thời gian sống của span |
| Ghi nhận lỗi | Gắn thông tin thất bại vào đúng thao tác được quan sát |

Ví dụ cây thao tác do ứng dụng thiết kế:

```text
HTTP xử lý đặt hàng
└── checkout
    ├── inventory.reserve
    └── shipping.quote
```

Một lỗi của `inventory.reserve` chưa đủ để kết luận `checkout` thất bại. Nếu hợp đồng nghiệp vụ cho phép tiếp nhận đơn ở trạng thái chờ giữ hàng, thao tác cha có thể hoàn tất hợp lệ. Vì vậy, trước khi viết mã, cần xác định **mỗi span đang mô tả việc gì và kết quả nào được coi là thất bại của chính việc đó**.

## 2. Chọn Observation hay Tracer

Trong Spring Boot 3.3.x, có hai cách thường dùng:

| Nhu cầu | API phù hợp |
| --- | --- |
| Quan sát một thao tác để các bộ xử lý tạo metric và span theo cấu hình | `Observation` và `ObservationRegistry` |
| Tạo và điều khiển span trực tiếp, không tự tạo thêm metric của thao tác | `io.micrometer.tracing.Tracer` |
| Thêm dữ liệu cho span đã có | Truy cập span hiện tại, kiểm tra khả năng không có span và tuân thủ quyền sở hữu |

Spring Boot tích hợp Micrometer Observation với Micrometer Tracing khi có cấu hình và thư viện tracing phù hợp. Chỉ tạo một `ObservationRegistry` rỗng hoặc chỉ thêm Actuator không bảo đảm đã có span được gửi tới hệ thống thu thập. Xem [Spring Boot 3.3: tạo custom span và tích hợp Observation](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.creating-spans).

Các ví dụ service phía dưới là **mã tích hợp vào ứng dụng Spring Boot đã cấu hình tracing**, không phải chương trình chỉ chạy bằng `javac InventoryService.java`. Một lựa chọn thư viện cho ứng dụng là:

- `org.springframework.boot:spring-boot-starter-actuator`.
- `io.micrometer:micrometer-tracing-bridge-otel`.
- `io.opentelemetry:opentelemetry-exporter-zipkin` nếu gửi tới Zipkin.

Dùng bộ quản lý phiên bản của Spring Boot cho các phụ thuộc này và chọn bridge/exporter phù hợp với hệ thống hiện có. Phần thực hành độc lập ở mục 7 dùng Observation và bộ xử lý in ra màn hình, giúp kiểm tra vòng đời mà chưa cần hệ thống thu thập trace.

## 3. Tạo span trực tiếp và quản lý đúng vòng đời

### 3.1. Tạo, bắt đầu, mở scope và kết thúc là các thao tác khác nhau

Với API `Tracer`, mẫu sử dụng gồm:

1. Tạo span cho thao tác và đặt tên ổn định.
2. Bắt đầu span.
3. Đưa span vào scope trong lúc thực thi mã cần quan sát.
4. Ghi tag, event hoặc lỗi vào đúng đối tượng span.
5. Đóng scope để khôi phục ngữ cảnh trước đó.
6. Kết thúc span bằng `end()` trong `finally`.

`nextSpan()` tạo span con nếu có span hiện tại; nếu không có cha, nó tạo span thuộc trace mới. `withSpan(...)` trả về `Tracer.SpanInScope`, nên sử dụng với `try-with-resources`. **Đóng scope không thay cho kết thúc span.** Đây là hai trách nhiệm riêng trong [Micrometer Tracing: sử dụng Tracer trực tiếp](https://docs.micrometer.io/tracing/reference/api.html).

### 3.2. Ví dụ service giữ hàng

Tệp `InventoryService.java`:

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final Tracer tracer;

    public InventoryService(Tracer tracer) {
        this.tracer = tracer;
    }

    public String reserve(boolean fail) {
        Span span = tracer.nextSpan()
                .name("inventory.reserve")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            span.tag("inventory.source", "primary");
            span.event("inventory.reserve.started");

            if (fail) {
                throw new IllegalStateException("primary unavailable");
            }

            span.tag("inventory.result", "reserved");
            span.event("inventory.reserve.completed");
            return "RESERVED";
        } catch (RuntimeException | Error error) {
            span.error(error);
            throw error;
        } finally {
            span.end();
        }
    }
}
```

`fail` là đầu vào mô phỏng để chủ động đi vào hai nhánh của ví dụ. Trong ứng dụng thực, thay phần mô phỏng bằng thao tác giữ hàng thực sự; không thêm độ trễ giả vào mã nghiệp vụ để “làm rõ” trace.

Những điểm cần đọc từ đoạn mã:

- `inventory.reserve` là tên của **loại thao tác**, không chứa mã đơn hàng.
- `tag` mô tả kết quả; `event` đánh dấu một thời điểm. Hai loại dữ liệu này không thay thế `error(Throwable)`.
- Nếu thao tác thất bại, mã ghi nhận lỗi rồi **ném lại cùng đối tượng lỗi**, bảo toàn hành vi cho bên gọi.
- `finally` chạy cả khi `return` và khi có ngoại lệ, nên nhánh thành công lẫn thất bại đều kết thúc span.
- Bắt `Error` ở đây chỉ để ghi nhận rồi ném lại ngay; đây không phải cơ chế phục hồi khỏi lỗi nghiêm trọng của JVM.

Ví dụ chỉ có ngoại lệ không kiểm tra. Nếu thao tác thực tế khai báo ngoại lệ có kiểm tra như `IOException`, hãy ghi nhận và ném lại ngoại lệ đó theo chữ ký phương thức; không bỏ sót nó hoặc chuyển thành kết quả thành công chỉ để đơn giản hóa tracing.

Theo hợp đồng [Micrometer Span](https://raw.githubusercontent.com/micrometer-metrics/tracing/v1.3.6/micrometer-tracing/src/main/java/io/micrometer/tracing/Span.java), `error(Throwable)` ghi nhận ngoại lệ còn `end()` kết thúc span. Việc gửi dữ liệu còn phụ thuộc lấy mẫu, bridge, exporter và hệ thống thu thập; `end()` không phải xác nhận máy chủ đã lưu span.

### 3.3. Bẫy ghi lỗi vào span cha sau khi scope đã đóng

Với cấu trúc `try-with-resources` ở trên, scope được đóng **trước khi vào khối catch**. Lúc đó span hiện tại có thể đã trở lại span cha.

Đoạn sau là một phản ví dụ, không dùng để ghi lỗi cho span con:

```java
// Sai mục tiêu: currentSpan có thể là span cha hoặc null.
catch (RuntimeException error) {
    tracer.currentSpan().error(error);
    throw error;
}
```

Giữ tham chiếu `span` đã tạo và gọi `span.error(error)` giúp xác định rõ thao tác bị lỗi, không phụ thuộc span nào đang hiện hành trong khối catch.

Tương tự, không gọi `end()` trên span lấy từ `tracer.currentSpan()` nếu span đó do HTTP instrumentation hoặc thành phần khác tạo. Thành phần tạo span chịu trách nhiệm kết thúc span; thành phần sử dụng ngữ cảnh không được tự đóng vòng đời của người khác.

## 4. Ghi nhận lỗi theo hợp đồng của từng thao tác

### 4.1. Phân biệt lỗi con và kết quả cha

Giả sử `checkout` được định nghĩa là “tiếp nhận đơn, cho phép chờ giữ hàng khi kho chính tạm thời không sẵn sàng”. Khi đó:

| Tình huống | `inventory.reserve` | `checkout` |
| --- | --- | --- |
| Giữ hàng thành công | Không ghi lỗi | Hoàn tất với đơn đã giữ hàng |
| Kho thất bại, cha chấp nhận trạng thái chờ hợp lệ | Ghi lỗi của lần giữ hàng | Ghi kết quả chờ và event xử lý thay thế |
| Kho thất bại, cha bắt buộc phải giữ hàng ngay | Ghi lỗi của lần giữ hàng | Cũng thất bại theo hợp đồng của thao tác cha |
| Không đủ hàng là kết quả nghiệp vụ bình thường của thao tác kiểm tra | Ghi trạng thái nghiệp vụ phù hợp | Quyết định theo hợp đồng, không mặc định đánh dấu lỗi kỹ thuật |

Đây là cách thiết kế ranh giới quan sát cho ví dụ. Việc phân loại phải dựa vào ý nghĩa thao tác thực tế, không chỉ dựa vào tên lớp ngoại lệ hay mã HTTP trả về. [Hướng dẫn ghi lỗi của OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/) cũng phân biệt lỗi của một thao tác với lỗi đã được xử lý để thao tác đó hoàn tất hợp lệ.

### 4.2. Ví dụ cha chấp nhận phương án xử lý thay thế

Tệp `CheckoutService.java`, dùng cùng `InventoryService` ở mục 3:

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final Tracer tracer;
    private final InventoryService inventoryService;

    public CheckoutService(
            Tracer tracer, InventoryService inventoryService) {
        this.tracer = tracer;
        this.inventoryService = inventoryService;
    }

    public String checkout(boolean failInventory) {
        Span span = tracer.nextSpan().name("checkout").start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            try {
                String result = inventoryService.reserve(failInventory);
                span.tag("checkout.result", "reserved");
                return result;
            } catch (IllegalStateException error) {
                span.tag("checkout.result", "deferred");
                span.event("inventory.fallback.accepted");
                return "ACCEPTED_PENDING_STOCK";
            }
        } catch (RuntimeException | Error error) {
            span.error(error);
            throw error;
        } finally {
            span.end();
        }
    }
}
```

Trong ví dụ, `IllegalStateException` chỉ đại diện cho sự cố kho đã mô phỏng. Ứng dụng thực nên bắt kiểu ngoại lệ đặc thù của thao tác có thể phục hồi; không dùng một khối bắt quá rộng để che cả lỗi lập trình.

Khi gọi `checkout(true)`:

1. `checkout` vào scope.
2. `inventory.reserve` trở thành span con.
3. Lỗi được ghi vào span con và ném lại; span con kết thúc.
4. Scope của con đóng, ngữ cảnh cha được khôi phục.
5. Cha chấp nhận trạng thái chờ, thêm tag/event và hoàn tất.

Cha không gọi `error(error)` cho lỗi đã được xử lý hợp lệ trong phạm vi của mình. Ngược lại, nếu việc giữ hàng là điều kiện bắt buộc, hãy để lỗi truyền ra khỏi thao tác cha; khi đó khối catch ngoài của cha ghi nhận thất bại của `checkout`.

**Không suy luận rằng mọi span trong một trace phải cùng trạng thái lỗi.** Cũng không cần sao chép toàn bộ stack trace vào từng tầng. Nếu các tầng đều có thao tác thực sự thất bại, cần diễn đạt đúng thất bại ở từng ranh giới và tránh thêm bản ghi ngoại lệ trùng lặp không cần thiết.

### 4.3. Log lỗi, tag lỗi và trạng thái lỗi không đồng nhất

`logger.error(...)` tạo bản ghi log. `span.tag("result", "failed")` thêm một thuộc tính. Cả hai không tự bảo đảm span đã được đánh dấu lỗi.

Với bridge OpenTelemetry trong Micrometer Tracing 1.3.6, `Span.error(Throwable)` vừa ghi exception vừa đặt trạng thái span thành `ERROR`; xem [mã triển khai OtelSpan](https://raw.githubusercontent.com/micrometer-metrics/tracing/v1.3.6/micrometer-tracing-bridges/micrometer-tracing-bridge-otel/src/main/java/io/micrometer/tracing/otel/bridge/OtelSpan.java). Cách hiển thị chi tiết lỗi có thể khác giữa các bridge và giao diện thu thập trace.

Tương tự, ghi lỗi lên span không tự làm HTTP response thành 500, không rollback giao dịch và không thực hiện retry. Những hành vi đó vẫn do mã ứng dụng và framework tương ứng quyết định.

## 5. Dùng Observation để quản lý thao tác

Với thao tác cần được quan sát qua cả metric và trace, có thể dùng một lớp thay thế `InventoryService` theo hướng sau. Đây là **lựa chọn thay thế cho việc tự tạo span của cùng thao tác**, không cần bọc chồng cả hai cách chỉ để đo đúng một công việc.

Tệp `ObservedInventoryService.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedInventoryService {
    private final ObservationRegistry registry;

    public ObservedInventoryService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String reserve(boolean fail) {
        Observation observation = Observation
                .createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("inventory.source", "primary");

        return observation.observe(() -> {
            if (fail) {
                throw new IllegalStateException("primary unavailable");
            }
            observation.lowCardinalityKeyValue(
                    "inventory.result", "reserved");
            return "RESERVED";
        });
    }
}
```

`observe(...)` bao trọn việc bắt đầu observation, mở scope, thực thi lambda, ghi nhận lỗi thoát khỏi lambda, đóng scope và dừng observation. Khi dùng mẫu này, không tự gọi thêm `start()` trước hoặc `stop()` lần nữa sau đó. Hành vi ghi lỗi rồi ném lại và dừng trong `finally` có thể đối chiếu tại [Observation 1.13.6](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.6/micrometer-observation/src/main/java/io/micrometer/observation/Observation.java).

Một điểm quan trọng về vị trí khối catch:

- Nếu ngoại lệ **thoát khỏi lambda** của `inventory.reserve`, observation của thao tác này nhận lỗi.
- Nếu lambda tự bắt ngoại lệ và trả về phương án thay thế hợp lệ, `observe` nhìn thấy lần thực thi hoàn tất bình thường.
- Nếu mã trả về một đối tượng kết quả thất bại mà không ném ngoại lệ, `observe` không tự hiểu ý nghĩa nghiệp vụ của đối tượng đó. Cần phân loại kết quả và chủ động bổ sung dữ liệu quan sát phù hợp.
- Nếu đang quan sát một thao tác thực sự thất bại nhưng phải chuyển ngoại lệ thành kết quả trả về, có thể gọi `observation.error(error)` trước khi trả về. Chỉ làm vậy khi thất bại đúng với hợp đồng của chính observation đó.

Nếu dùng API thủ công `Observation.start(...)` và `openScope()`, phải tự quản lý `error(...)`, đóng scope và `stop()`. Đừng lấy việc đóng `Observation.Scope` làm dấu hiệu observation đã dừng.

## 6. Chọn tên, thuộc tính và ranh giới hợp lý

Tên span nên ổn định theo loại thao tác, ví dụ `inventory.reserve`, `shipping.quote`, `checkout`. Không ghép mã đơn hàng thành tên như `checkout-ORDER-938172`, vì sẽ tạo rất nhiều tên khó tổng hợp.

Với Observation, **low cardinality** nghĩa là tập giá trị có giới hạn hợp lý; ví dụ `inventory.source=primary|backup` hoặc `checkout.result=reserved|deferred`. Mã yêu cầu có rất nhiều giá trị khác nhau không phù hợp làm nhãn metric. Phân biệt này được giải thích trong [Micrometer Observation 1.13: thuộc tính và cardinality](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

Một cách chọn dữ liệu cho bài toán:

| Dữ liệu | Cách dùng |
| --- | --- |
| Nguồn kho primary/backup | Tag để lọc theo một tập giá trị nhỏ |
| Kết quả reserved/deferred | Tag thể hiện kết quả nghiệp vụ |
| Đã bắt đầu giữ hàng | Event nếu mốc thời gian này giúp chẩn đoán |
| Ngoại lệ làm thao tác thất bại | `error(Throwable)` hoặc lỗi của Observation |
| Mật khẩu, token, số thẻ, toàn bộ payload | Không đưa vào tag, event hoặc thông điệp ngoại lệ được xuất ra |

High cardinality không đồng nghĩa với được phép ghi dữ liệu nhạy cảm. Thông điệp và stack trace của ngoại lệ cũng có thể chứa dữ liệu đầu vào; cần kiểm soát thông tin tại nơi tạo lỗi và tại tuyến thu thập theo yêu cầu của hệ thống.

Một lần retry thất bại rồi thành công cần được mô tả theo ranh giới đã chọn: span cho từng lần thử có thể ghi lỗi của lần thử đó, còn span bao toàn bộ chuỗi retry phản ánh kết quả cuối cùng. Không đánh dấu thất bại cho thao tác tổng thể chỉ vì một lần thử bên trong đã lỗi nhưng được phục hồi đúng hợp đồng.

## 7. Thực hành Java độc lập: thấy rõ lỗi con và scope

Chương trình sau chạy với Java 17+ và Micrometer Observation 1.13.0. Nó đăng ký một `ObservationHandler` chỉ in vòng đời ra stdout. **Chương trình này không cài tracing handler, không tạo dữ liệu gửi tới Zipkin và không chứng minh đường xuất span đã hoạt động.** Mục tiêu là kiểm chứng vị trí ghi lỗi, thứ tự kết thúc và việc khôi phục scope.

Lưu thành `ObservationScopeDemo.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationScopeDemo {
    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(new ConsoleHandler());

        System.out.println("RESULT " + checkout(registry, false));
        System.out.println("AFTER_SCOPE_EMPTY "
                + (registry.getCurrentObservation() == null));
        System.out.println("RESULT " + checkout(registry, true));
        System.out.println("AFTER_SCOPE_EMPTY "
                + (registry.getCurrentObservation() == null));
    }

    private static String checkout(
            ObservationRegistry registry, boolean failInventory) {
        Observation observation =
                Observation.createNotStarted("checkout", registry);
        return observation.observe(() -> {
            try {
                return reserve(registry, failInventory);
            } catch (IllegalStateException error) {
                observation.lowCardinalityKeyValue("result", "deferred");
                observation.event(
                        Observation.Event.of("inventory.fallback.accepted"));
                return "ACCEPTED_PENDING_STOCK";
            }
        });
    }

    private static String reserve(
            ObservationRegistry registry, boolean fail) {
        Observation observation =
                Observation.createNotStarted("inventory.reserve", registry);
        return observation.observe(() -> {
            System.out.println("IN_SCOPE inventory.reserve="
                    + (registry.getCurrentObservation() == observation));
            if (fail) {
                throw new IllegalStateException("primary unavailable");
            }
            return "RESERVED";
        });
    }

    private static final class ConsoleHandler
            implements ObservationHandler<Observation.Context> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            System.out.println("START " + context.getName());
        }

        @Override
        public void onError(Observation.Context context) {
            System.out.println("ERROR " + context.getName() + " "
                    + context.getError().getClass().getSimpleName());
        }

        @Override
        public void onStop(Observation.Context context) {
            Throwable error = context.getError();
            System.out.println("STOP " + context.getName() + " error="
                    + (error == null ? "none"
                            : error.getClass().getSimpleName()));
        }
    }
}
```

Đặt hai JAR `micrometer-observation-1.13.0.jar` và `micrometer-commons-1.13.0.jar` cùng thư mục với tệp Java, hoặc điều chỉnh classpath tới vị trí đã tải. Trong PowerShell:

```powershell
$cp = ".;micrometer-observation-1.13.0.jar;micrometer-commons-1.13.0.jar"
javac --release 17 -encoding UTF-8 -cp $cp ObservationScopeDemo.java
java -cp $cp ObservationScopeDemo
```

Trên Linux/macOS, dấu ngăn cách các mục classpath là `:` thay cho `;`.

Stdout của chương trình:

```text
START checkout
START inventory.reserve
IN_SCOPE inventory.reserve=true
STOP inventory.reserve error=none
STOP checkout error=none
RESULT RESERVED
AFTER_SCOPE_EMPTY true
START checkout
START inventory.reserve
IN_SCOPE inventory.reserve=true
ERROR inventory.reserve IllegalStateException
STOP inventory.reserve error=IllegalStateException
STOP checkout error=none
RESULT ACCEPTED_PENDING_STOCK
AFTER_SCOPE_EMPTY true
```

Ở lần thứ hai, lỗi thoát khỏi lambda của `reserve`, nên handler thấy `ERROR inventory.reserve`. Nó được bắt trong lambda của `checkout`, nên handler kết thúc `checkout` với `error=none`. Cả hai lần đều có `AFTER_SCOPE_EMPTY true`, chứng minh trong chương trình này không còn observation hiện hành sau thao tác bao ngoài.

Bộ xử lý in ra màn hình không có phương thức in event nên dòng `inventory.fallback.accepted` không xuất hiện trong stdout. Điều đó không làm mất việc gọi event trong mã; đơn giản là handler này chỉ in `onStart`, `onError` và `onStop`.

## 8. Kiểm chứng trong ứng dụng Spring Boot có tracing

Sau khi áp dụng **một** trong hai cách tạo span vào ứng dụng đã cấu hình tracing:

1. Chạy trường hợp thành công và trường hợp kho bị lỗi có thể phục hồi.
2. Trong trace đã được thu thập, tìm các thao tác theo tên, kiểm tra quan hệ cha/con, thời gian và tag/event.
3. Xác nhận span giữ hàng ghi lỗi ở trường hợp thất bại; không bắt buộc span tiếp nhận đơn bị đánh dấu lỗi nếu hợp đồng cho phép trạng thái chờ.
4. Bỏ phương án xử lý thay thế và để lỗi truyền ra thao tác cha; xác nhận kết quả quan sát thay đổi phù hợp.
5. Kiểm tra một yêu cầu tiếp theo để phát hiện việc rò rỉ ngữ cảnh từ lần xử lý trước.

Khi không thấy span, kiểm tra theo tuyến: tracing đã được cấu hình chưa, thao tác có chạy không, span đã kết thúc chưa, chính sách lấy mẫu có giữ trace không, exporter có gửi được không và bộ lọc giao diện có đang loại dữ liệu không. Có trace ID trong log không tự chứng minh span đã tới hệ thống lưu trữ.

Các ví dụ scope trong bài là mã **đồng bộ**. Một `try-with-resources` bao quanh lệnh tạo `CompletableFuture` hoặc `Mono` có thể kết thúc trước khi công việc thực sự chạy xong. Khi chuyển luồng hoặc dùng xử lý phản ứng, phải gắn vòng đời với lúc công việc hoàn tất và truyền ngữ cảnh bằng cơ chế thích hợp; không giữ scope của luồng gọi rồi dùng tùy ý trên luồng khác.

## 9. Lỗi thường gặp và bài tập tự kiểm tra

| Lỗi thường gặp | Hệ quả | Cách sửa |
| --- | --- | --- |
| Quên `end()` hoặc `stop()` | Thao tác chưa được kết thúc đúng vòng đời | Dùng `finally` hoặc `observe(...)` |
| Chỉ đóng scope | Khôi phục ngữ cảnh nhưng chưa hoàn tất thao tác | Phân biệt scope với span/observation |
| Gọi `currentSpan().error(...)` sau khi scope con đóng | Có thể gắn lỗi vào cha hoặc gặp null | Giữ tham chiếu tới span cần ghi lỗi |
| Chỉ thêm tag `error=true` | Có dữ liệu tùy ý nhưng chưa chắc có trạng thái lỗi | Dùng API ghi lỗi đúng của loại quan sát |
| Nuốt mọi ngoại lệ và trả thành công | Sai cả hành vi ứng dụng lẫn dữ liệu quan sát | Giữ hợp đồng lỗi và chỉ phục hồi khi hợp lệ |
| Tự kết thúc span HTTP đang hiện hành | Can thiệp vòng đời do framework sở hữu | Chỉ kết thúc span do mình tạo |
| Tạo hai lớp đo cho cùng một thao tác không có lý do | Trace dư span và metric dễ trùng | Chọn Observation hoặc Tracer theo nhu cầu |

Bài tập:

1. Trong `ObservationScopeDemo`, bỏ khối catch xử lý thay thế của `checkout`, rồi bắt ngoại lệ ở `main` để chương trình tiếp tục. Dự đoán observation nào nhận lỗi trước khi chạy.
2. Đổi tình huống thành “không còn hàng” là kết quả hợp lệ, trả về `OUT_OF_STOCK` thay vì ném lỗi kỹ thuật. Chọn tag kết quả và giải thích vì sao có hoặc không ghi lỗi.
3. Với service tạo span thủ công, đánh dấu vị trí scope đóng và vị trí `end()` chạy cho cả nhánh `return` và nhánh ném ngoại lệ.
4. Thiết kế một span bao toàn bộ quá trình thử lại và các span con theo từng lần thử; giải thích trường hợp lần đầu lỗi nhưng lần sau thành công.

Một lời giải tốt xác định rõ thao tác được đo, chủ sở hữu vòng đời, nơi khôi phục ngữ cảnh và ý nghĩa của thất bại tại từng ranh giới.
