# Convention cho custom observation trong Spring Boot

Trong chương **Custom observation** của module **SPRING_BOOT_OBSERVABILITY**, ta đã biết rằng Micrometer Observation cho phép đo một thao tác nghiệp vụ bằng một API chung, sau đó chuyển thành **metrics**, **distributed traces** và các tín hiệu liên quan nếu registry có handler thích hợp. Nhưng khi nhiều lập trình viên tự instrument các thao tác, tên observation và key-value dễ bị đặt tùy ý: có nơi dùng `reserve.stock`, nơi khác dùng `inventory.reservation`; có nơi ghi `result=ok`, nơi khác ghi `status=success`. Dữ liệu vẫn được thu thập nhưng khó so sánh, tổng hợp và dùng để điều tra.

**Observation convention** giải quyết vấn đề đó bằng cách định nghĩa một **hợp đồng đặt tên và nhãn** dùng chung cho một loại observation. Convention quy định tên ổn định của thao tác, tên dễ đọc trong trace và cách chuyển dữ liệu trong context thành các low/high-cardinality key-value.

Bài này tập trung vào cách thiết kế convention cho **custom observation** trong Spring Boot, cách gắn với `ObservationRegistry`, tác động tới metrics/traces/log correlation và các lỗi dễ gặp trong môi trường thực.

## 1. Vì sao cần convention khi đã có Observation API?

Với một thao tác giữ tồn kho, cách instrument trực tiếp có thể như sau:

```java
Observation.createNotStarted("inventory.reserve", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .lowCardinalityKeyValue("warehouse.tier", "primary")
        .observe(() -> reserveInWarehouse());
```

Cách viết này phù hợp với ví dụ nhỏ. Khi nghiệp vụ được gọi từ HTTP, job scheduler và message consumer, nếu mỗi nơi tự tạo tên/tag, ta có thể nhận ba cấu trúc telemetry khác nhau cho cùng một hành vi.

Convention gom quy tắc chung vào một lớp có thể tái sử dụng:

| Không thống nhất | Quy ước chung |
| --- | --- |
| `stock.lock`, `reserveInventory`, `inventory.reservation` | `inventory.reserve` |
| `channel=online` ở service A, `channel=web` ở service B | Một tập giá trị hữu hạn như `web/pos/partner` |
| Nhãn `warehouseId` sinh giá trị theo từng kho tự do | Nhãn `warehouse.tier=primary/secondary` |
| Span có tên chứa mã đơn, khó tổng hợp | Tên span ngắn, ổn định; tham chiếu cụ thể chỉ dùng ở ngữ cảnh được phép |

Convention giúp quản lý **cardinality**, giữ khả năng so sánh số liệu qua nhiều instance và giảm nguy cơ làm hỏng dashboard/alert khi code được đổi cấu trúc.

## 2. Các thành phần của một custom observation

Micrometer tách **dữ liệu của từng lần chạy** khỏi **quy tắc diễn giải dữ liệu**:

```text
Business code
    |
    +--> Observation.Context
    |      Thông tin của lần thực hiện: channel, loại kho, ...
    |
    +--> ObservationConvention<Context>
    |      getName()
    |      getContextualName(context)
    |      getLowCardinalityKeyValues(context)
    |      getHighCardinalityKeyValues(context)
    |      supportsContext(context)
    |
    +--> Observation + ObservationRegistry
              |
              +--> ObservationHandler cho metrics (nếu cấu hình)
              +--> ObservationHandler cho tracing (nếu cấu hình)
              +--> exporter/backend tương ứng
```

Vai trò cụ thể:

| Thành phần | Chức năng |
| --- | --- |
| `Observation.Context` | Giữ dữ liệu của một instance observation và trạng thái trong vòng đời đo |
| `ObservationConvention<T>` | Chuẩn hóa tên và các key-value cho context loại `T` |
| `ObservationRegistry` | Quản lý observation configuration, conventions, predicates, filters và handlers |
| `ObservationHandler` | Nhận callback của observation; tùy handler tạo metric, span hoặc xử lý khác |
| Exporter/scraper | Đưa tín hiệu ra hệ thống thu thập, ví dụ Prometheus cho metrics hay tracing backend |

Convention **không tự tạo metric hoặc span**. Nó cung cấp metadata để các handler xử lý. Vì vậy, thấy code convention được gọi không có nghĩa dữ liệu chắc chắn đã đến backend; còn phải kiểm tra registry, tracing bridge, exporter, sampling và đường thu thập.

### Năm phương thức quan trọng

Với `ObservationConvention<T extends Observation.Context>`:

- `getName()` trả về **tên observation ổn định** để framework và meter handler sử dụng. Không đưa order ID, URL động hoặc tên người dùng vào đây.
- `getContextualName(T context)` cung cấp **tên dễ đọc trong tracing**, thường ngắn gọn theo hành động. Không dùng dữ liệu nhạy cảm.
- `getLowCardinalityKeyValues(T context)` trả về các nhãn có **số giá trị hữu hạn** để có thể dùng cho metrics và trace attributes.
- `getHighCardinalityKeyValues(T context)` dành cho ngữ cảnh nhiều giá trị khác nhau, chủ yếu có ích trong traces; việc xuất thực tế phụ thuộc handler và chính sách dữ liệu.
- `supportsContext(Observation.Context context)` cho biết convention có hỗ trợ loại context được truyền vào hay không, đặc biệt quan trọng khi đăng ký convention ở phạm vi toàn registry.

Các tên API ở đây thuộc Micrometer Observation; vị trí dependency, hỗ trợ instrumentation mặc định và cách khởi tạo registry phụ thuộc phiên bản Spring Boot.

## 3. Ví dụ đầy đủ: Convention cho thao tác giữ tồn kho

Giả sử hệ thống đặt hàng có một nghiệp vụ `reserveInventory()`. Ta muốn trả lời hai câu hỏi: **thời gian giữ hàng có tăng không** và **độ trễ thay đổi theo kênh đặt hàng/loại kho nào**. Để kiểm soát cardinality, chỉ sử dụng enum cho những nhãn làm chiều phân tích.

### Bước 1: Định nghĩa context có kiểu rõ ràng

```java
import io.micrometer.observation.Observation;
import java.util.Objects;

enum OrderChannel {
    WEB, POS, PARTNER
}

enum WarehouseTier {
    PRIMARY, SECONDARY
}

final class InventoryReserveContext extends Observation.Context {
    private final OrderChannel channel;
    private final WarehouseTier warehouseTier;

    InventoryReserveContext(OrderChannel channel, WarehouseTier warehouseTier) {
        this.channel = Objects.requireNonNull(channel);
        this.warehouseTier = Objects.requireNonNull(warehouseTier);
    }

    OrderChannel channel() {
        return channel;
    }

    WarehouseTier warehouseTier() {
        return warehouseTier;
    }
}
```

`InventoryReserveContext` kế thừa `Observation.Context`, nhưng chỉ bổ sung hai thuộc tính liên quan đến phép đo. Không cần đặt toàn bộ `Order`, request body, token hay thông tin cá nhân vào context nếu convention không sử dụng chúng.

### Bước 2: Viết convention

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import java.util.Locale;

public class InventoryReserveConvention
        implements ObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of(
                        "order.channel",
                        context.channel().name().toLowerCase(Locale.ROOT)),
                KeyValue.of(
                        "warehouse.tier",
                        context.warehouseTier().name().toLowerCase(Locale.ROOT))
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            InventoryReserveContext context) {
        // Bài toán này không cần identifier động trong trace.
        return KeyValues.empty();
    }
}
```

Kết quả mong đợi:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Observation name | `inventory.reserve` | Tên logic của thao tác, giữ ổn định qua lần chạy |
| Contextual name | `reserve inventory` | Tên span dễ đọc nếu tracing handler dùng contextual name |
| `order.channel` | `web` | Nhãn hữu hạn để so sánh kênh |
| `warehouse.tier` | `primary` | Nhãn hữu hạn để so sánh nhóm kho |
| High-cardinality keys | Rỗng | Không xuất ID động khi không có nhu cầu điều tra |

Số tổ hợp của hai nhãn trong ví dụ nhiều nhất là **3 × 2 = 6** (chưa tính nhãn chung như instance, service, exception hay các nhãn do handler thêm). Đây là mức dễ dự toán hơn so với gắn một `orderId` khác nhau vào mỗi observation.

### Bước 3: Dùng convention trong service

Ví dụ dưới đây minh họa API Observation cùng các kiểu domain giả định `ReserveCommand`, `ReservationResult` và `StockGateway`. Những kiểu domain này do ứng dụng định nghĩa; chúng không thuộc Micrometer.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {
    private final ObservationRegistry observationRegistry;
    private final InventoryReserveConvention convention;
    private final StockGateway gateway;

    public InventoryReservationService(
            ObservationRegistry observationRegistry,
            InventoryReserveConvention convention,
            StockGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.convention = convention;
        this.gateway = gateway;
    }

    public ReservationResult reserve(ReserveCommand command) {
        InventoryReserveContext context = new InventoryReserveContext(
                command.channel(),
                command.warehouseTier());

        Observation observation = Observation.createNotStarted(
                convention,
                () -> context,
                observationRegistry);

        observation.start();
        try (Observation.Scope ignored = observation.openScope()) {
            ReservationResult result = gateway.reserve(command);
            observation.lowCardinalityKeyValue(
                    "outcome",
                    result.reserved() ? "reserved" : "out_of_stock");
            return result;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }
}
```

Service tạo context trước, truyền một convention rõ ràng vào observation rồi quản lý vòng đời `start → scope → stop`. Scope giúp các lời gọi con lấy observation hiện tại trên **cùng execution context**. Trên đường lỗi, `observation.error(ex)` ghi nhận exception cho handler có hỗ trợ; mã vẫn ném exception lên caller. `finally` bảo đảm đóng phép đo.

Tag `outcome` phụ thuộc kết quả nên được thêm từ business code, còn convention giữ hai nhãn cấu trúc ổn định. Cách kết hợp này giúp tránh đưa kết quả nghiệp vụ chưa biết vào context ngay lúc khởi tạo. **Thời điểm handler đọc tag có thể khác nhau**, vì vậy khi cần thấy `outcome` trong cả metric lẫn span, hãy kiểm tra kết quả thực tế của handler/version đang dùng.

Để Spring có thể inject convention vào service trong ví dụ, đăng ký nó thành bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryObservationConfiguration {
    @Bean
    InventoryReserveConvention inventoryReserveConvention() {
        return new InventoryReserveConvention();
    }
}
```

Một cách khác cho thao tác đơn giản, không cần outcome tùy biến, là gọi `observe(...)` để Observation tự quản lý start, scope, error và stop:

```java
Observation.createNotStarted(
        convention,
        () -> new InventoryReserveContext(channel, warehouseTier),
        observationRegistry)
    .observe(() -> gateway.reserve(command));
```

Chọn cách thủ công khi cần ghi chính xác kết quả trả về, event hoặc ngữ cảnh khác trong vòng đời observation.

## 4. Convention cục bộ và global convention

**Convention cục bộ** (truyền trực tiếp khi tạo Observation) thích hợp với code do nhóm mình sở hữu: tại điểm tạo observation, người đọc nhìn ra ngay convention áp dụng cho thao tác nào.

**Global observation convention** hữu ích khi nhiều nguồn instrumentation cùng tạo một loại context và bạn muốn áp dụng một hợp đồng chung trên toàn registry. Micrometer có giao diện `GlobalObservationConvention<T>` mở rộng từ convention thông thường, được registry lựa chọn khi `supportsContext(...)` khớp. Một implementation có thể tái sử dụng logic của `InventoryReserveConvention`:

```java
import io.micrometer.observation.GlobalObservationConvention;

final class GlobalInventoryReserveConvention
        extends InventoryReserveConvention
        implements GlobalObservationConvention<InventoryReserveContext> {
    // Kế thừa tên, contextual name, key-values và supportsContext.
}
```

Spring Boot cho phép thêm global convention qua `ObservationRegistryCustomizer`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class GlobalInventoryObservationConfiguration {
    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> inventoryGlobalConvention() {
        return registry -> registry.observationConfig()
                .observationConvention(new GlobalInventoryReserveConvention());
    }
}
```

**Chọn một chiến lược rõ ràng** cho từng loại observation: hoặc truyền convention cục bộ ở nơi tạo, hoặc để registry chọn global convention khi phù hợp. Không cần đăng ký cả hai trong một ví dụ tối giản. Nếu muốn áp dụng global cho custom context, instrumentation vẫn phải tạo **đúng context subtype** và có tên/đặc điểm tương ứng để convention được chọn.

Khi có convention được chỉ định trực tiếp, global convention và convention mặc định cùng tồn tại, thứ tự chọn thông thường ưu tiên quy tắc cụ thể rồi đến global và mặc định. Chi tiết có thể phụ thuộc implementation và phiên bản Micrometer/Spring Boot; khi tùy biến instrumentation framework, cần kiểm tra xem nguồn đó có dùng convention được registry cung cấp hay có custom convention riêng.

Đừng viết một global convention với `supportsContext(...)` luôn trả về `true` nếu mục đích chỉ xử lý inventory: nó có thể áp quy ước sai cho HTTP, messaging hoặc tracing observations khác.

## 5. Convention khác ObservationFilter, ObservationPredicate và MeterFilter thế nào?

Các cơ chế sau hoạt động ở phạm vi khác nhau, dù đều nằm quanh observability:

| Cơ chế | Công việc | Ví dụ |
| --- | --- | --- |
| **`ObservationConvention`** | Xác định tên, contextual name và key-values của một loại observation | Chuẩn hóa `inventory.reserve`, `order.channel` |
| **`ObservationFilter`** | Bổ sung/chỉnh context và key-value trong pipeline observation | Thêm nhãn chung khi phù hợp; không dùng để định nghĩa hợp đồng chính cho mọi loại |
| **`ObservationPredicate`** | Cho phép hoặc từ chối **cả observation** trước khi nó hoạt động | Bỏ observation heartbeat không cần thiết |
| **`MeterFilter`** | Quản lý meter và tags trong metric registry | Giới hạn một metric tag hoặc từ chối meter không phù hợp |
| **Tracing sampler** | Kiểm soát việc ghi nhận/xuất trace | Lấy mẫu một phần các request để giảm volume |

Ví dụ: muốn chuẩn hóa nhãn `order.channel` thì thiết kế trong convention; muốn sửa một tag chung cho nhiều observation thì cân nhắc filter; muốn bỏ hoàn toàn loại observation không còn cần thiết thì predicate; muốn giảm trace volume nhưng vẫn giữ metrics thì dùng sampler. Dùng predicate để “sửa nhãn” có thể làm mất cả span và metric của thao tác cần theo dõi.

## 6. Đặt tên và kiểm soát cardinality

Convention là nơi thích hợp để thực thi quy tắc tên và key-value:

| Quy tắc | Nên | Tránh |
| --- | --- | --- |
| Tên observation | `inventory.reserve`, `payment.authorize` | `inventory.reserve.ORDER-12345` |
| Contextual name | `reserve inventory`, `authorize payment` | Nối tên người dùng, raw URL hoặc token |
| Low-cardinality values | `outcome=reserved/out_of_stock/error` | `exception.message=<nội dung tự do>` |
| Loại nguồn | `order.channel=web/pos/partner` | Header tùy ý do client gửi |
| Mã giao dịch | Chỉ cân nhắc trong trace/log có kiểm soát và chính sách bảo mật phù hợp | ID đơn hàng làm nhãn metric |
| Nhãn kỹ thuật | `provider=internal/partner_a/partner_b` | Hostname hoặc query string không chuẩn hóa |

Số tổ hợp time series có thể gần bằng tích số giá trị của từng nhãn, nhân tiếp với các chiều khác như instance, URI mẫu và trạng thái. Thêm một nhãn 50.000 giá trị vào metric vốn có 12 tổ hợp có thể tạo đến **600.000 tổ hợp** trước khi tính các nhãn bổ sung. Điều này ảnh hưởng bộ nhớ, chi phí lưu trữ, truy vấn và độ hữu ích của dashboard.

**Low cardinality** không có nghĩa “số giá trị nhỏ hiện tại” mà phải là **số giá trị bị giới hạn về mặt thiết kế**. Ví dụ `warehouse.tier=primary/secondary` đáng tin hơn `warehouse.id=...` khi số kho có thể tăng không giới hạn.

**High cardinality** không phải quyền tự do ghi mọi dữ liệu vào trace. Hạn chế thông tin cá nhân, token, session ID, email, số thẻ và nội dung nhạy cảm. Handler/collector có thể lọc hoặc biến đổi dữ liệu theo cấu hình; đừng giả định key được xử lý giống nhau ở mọi exporter.

## 7. Convention và ba tín hiệu metrics, traces, logs

Một convention tốt giúp kết hợp các tín hiệu mà không khiến chúng trở thành bản sao của nhau.

### Metrics

Khi có metric observation handler, tên ổn định và low-cardinality tags hỗ trợ tổng hợp số lần chạy, thời lượng và lỗi theo các chiều hữu hạn. Các tên metric thực tế trên backend có thể được chuẩn hóa hoặc thêm hậu tố bởi registry/exporter. Không viết truy vấn dashboard dựa trên một tên chưa được xác nhận bằng dữ liệu xuất thực tế.

Muốn alert `p95 inventory.reserve tăng`, cần xác minh histogram/percentiles và aggregation của backend: không phải chỉ tạo observation là tự có truy vấn p95 gộp đúng qua nhiều instance.

### Distributed tracing

Khi tracing bridge, handler và exporter được cấu hình, một custom observation có thể tạo span nghiệp vụ, nằm giữa HTTP server span và các span của HTTP client hoặc database:

```text
HTTP POST /checkout
    └─ inventory.reserve       (custom observation)
         └─ database/client   (instrumentation của thư viện, nếu có)
```

Contextual name phải giúp con người đọc trace dễ dàng, trong khi `getName()` giữ danh tính logic để hệ thống tổng hợp. Nếu một lời gọi HTTP đã có client observation, không nên tạo một observation khác đo lại chính xác cùng ranh giới trừ khi custom observation thể hiện **bước nghiệp vụ riêng**.

### Logs và tương quan tín hiệu

Convention **không tự cấu hình logging/MDC**. Nếu Spring Boot được cấu hình tracing và log correlation phù hợp, log trong scope của observation có thể mang `traceId`/`spanId` để đối chiếu với span. Với tác vụ chạy qua `@Async`, executor, queue hoặc service khác, cần cơ chế **context propagation** phù hợp; mở scope trên một thread không bảo đảm context tự chuyển sang thread khác.

Sampling chỉ quyết định trace nào được ghi nhận/xuất theo tracing setup. Một trace không xuất hiện có thể do sampling, exporter, context propagation hoặc predicate, không nhất thiết là lỗi convention. Metrics từ cùng observation có thể vẫn tồn tại khi trace không được lấy mẫu, nếu metric handler hoạt động độc lập.

## 8. Những lỗi thường gặp khi tạo convention

**1. Tên chứa biến động.** Tạo `getName()` bằng `"inventory.reserve." + orderId` khiến tên metric/span tăng vô hạn. Tên nên mô tả *loại công việc*, không mô tả *một lần chạy*.

**2. Context chứa dữ liệu không cần thiết.** Đưa nguyên request hoặc domain entity vào context để tiện lấy tag có thể kéo theo dữ liệu nhạy cảm, tăng phụ thuộc và rủi ro khi log hoặc xuất trace. Chỉ giữ những trường đã được chấp thuận cho telemetry.

**3. Dùng high-cardinality key cho metrics.** Trong các handler phổ biến, high-cardinality key-value thường phục vụ trace và không được dùng làm metric tags mặc định; nhưng custom handler có thể xử lý khác. Phải kiểm tra đường xuất thay vì dựa vào tên phương thức để bảo đảm an toàn.

**4. `supportsContext` quá rộng.** Một global convention áp lên nhầm HTTP observation có thể làm mất nhãn chuẩn và phá dashboard của framework.

**5. Nhầm outcome nghiệp vụ với exception.** `out_of_stock` có thể là kết quả hợp lệ, còn timeout database là lỗi kỹ thuật. Đưa cả hai vào `outcome=error` làm méo chỉ số lỗi. Phân biệt ngay trong cấu trúc nhãn.

**6. Thêm nhãn vào sai thời điểm.** Một tag chỉ được biết sau khi thao tác kết thúc sẽ không thể xuất hiện trong các xử lý diễn ra ngay lúc start. Kiểm thử metric handler và tracing handler của phiên bản đang chạy, nhất là khi cần tag outcome đồng nhất.

**7. Thay convention khi chưa kiểm tra consumers.** Đổi từ `outcome` sang `result` hoặc từ `inventory.reserve` sang `stock.reserve` có thể làm đứt truy vấn PromQL, alert và dashboard lịch sử. Xem tên/key như một API telemetry cần quản lý thay đổi.

## 9. Quy trình thiết kế và kiểm chứng

Hãy bắt đầu bằng một câu hỏi vận hành cụ thể: “Khi tồn kho chậm, chúng ta có phân biệt được kênh web và POS, nhóm kho chính và dự phòng, và lỗi kỹ thuật so với hết hàng hay không?” Từ đó mới chọn context, convention và ranh giới observation.

Một quy trình có thể áp dụng trong nhóm:

1. **Chọn ranh giới nghiệp vụ:** xác định thao tác chưa được instrument bằng tín hiệu có sẵn; tránh đo chồng lên HTTP server/client observation.
2. **Đặt tên ổn định:** thống nhất một tên logic như `inventory.reserve` và contextual name dễ đọc.
3. **Thiết kế context nhỏ:** dùng enum hoặc giá trị đã chuẩn hóa cho những chiều cần phân tích. Liệt kê dữ liệu tuyệt đối không xuất.
4. **Viết convention:** định nghĩa `getName()`, `getContextualName()`, low/high key-values và `supportsContext()`; chọn cục bộ hoặc global.
5. **Tích hợp vào service:** khởi tạo observation, mở scope đúng, ghi outcome/error và luôn đóng phép đo.
6. **Kiểm tra trên đường xuất dữ liệu:** metric registry, tracing handler, exporter/scrape, sampling, logs correlation và dashboard.
7. **Đánh giá vận hành:** số lượng time series, span volume, latency overhead và khả năng điều tra lỗi thực tế.

Ví dụ bảng xác nhận cho `inventory.reserve`:

| Kịch bản | Metrics | Tracing/logs | Hành vi ứng dụng |
| --- | --- | --- | --- |
| WEB + PRIMARY, giữ hàng thành công | Có nhãn `order.channel=web`, `warehouse.tier=primary`, `outcome=reserved` khi handler hỗ trợ | Span nghiệp vụ nằm đúng trace cha khi được lấy mẫu | Đặt giữ hàng thành công |
| POS + SECONDARY, hết hàng hợp lệ | `outcome=out_of_stock`; không tự gán là lỗi kỹ thuật | Trace/log giúp tìm bước từ chối | Trả kết quả nghiệp vụ hợp lệ |
| Gateway ném exception | `outcome=error`; duration vẫn kết thúc | Observation ghi nhận exception qua handler có hỗ trợ | Exception vẫn ném lên caller |
| Gọi từ executor khác | Metric vẫn phản ánh đúng thao tác | Parent-child/spanId đúng khi propagation đã cấu hình | Job vẫn chạy |
| Sampler không lấy trace | Metric có thể vẫn được ghi | Không có span xuất ra là hành vi sampling bình thường | Nghiệp vụ không thay đổi |
| Đổi hoặc thêm kênh đặt hàng | Số tổ hợp metric tăng trong giới hạn có dự toán | Convention vẫn đặt tên thống nhất | Không ảnh hưởng logic domain |

Khi xác minh, đọc **tín hiệu xuất thật**, không chỉ đọc mã: một `ObservationConvention` đúng cú pháp vẫn có thể cho ra dữ liệu không mong muốn nếu handler, naming convention, registry hoặc exporter chưa được cấu hình đúng.

## 10. Khi nào nên dùng convention riêng?

Convention riêng đặc biệt hữu ích khi một **loại hành vi nghiệp vụ** xuất hiện nhiều lần hoặc ở nhiều adapter (HTTP, message consumer, scheduled job), khi doanh nghiệp cần dashboard/SLI ổn định, hoặc khi nhóm muốn kiểm soát cardinality và tiêu chuẩn key-value tập trung.

Nếu chỉ có một đoạn instrumentation ngắn với một tên và vài nhãn bất biến, gắn chúng trực tiếp vào `Observation` vẫn có thể đủ. Khi số nguồn tạo observation tăng, convention giúp tránh phân mảnh ngữ nghĩa. Nó là **hợp đồng metadata**, còn chất lượng observability vẫn phụ thuộc ranh giới đo đúng, instrumentation có handler/exporter và context được truyền chính xác.

**Điểm cần nhớ:** Dùng `Observation.Context` để giữ dữ liệu đã biết về một lần thực hiện; dùng `ObservationConvention` để thống nhất cách đặt tên và phân loại dữ liệu; dùng `ObservationRegistry` cùng các handler để biến observation thành các tín hiệu có thể điều tra. Giữ tên ổn định, nhãn có cardinality hữu hạn, kết quả nghiệp vụ rõ ràng và kiểm tra tương quan metrics–logs–traces trên môi trường thực.
