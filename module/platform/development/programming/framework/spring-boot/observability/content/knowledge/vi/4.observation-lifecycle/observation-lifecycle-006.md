# Ghi low-cardinality key value trong vòng đời Observation

> **Chương:** Vòng đời observation  
> **Bài:** Ghi low-cardinality key value  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Mục tiêu: gắn ngữ cảnh có thể tổng hợp vào một Observation

Một ứng dụng Spring Boot có thể theo dõi thao tác đặt hàng bằng Micrometer Observation. Đo thời lượng trung bình của tất cả đơn hàng giúp ta biết dịch vụ đang nhanh hay chậm, nhưng câu hỏi vận hành thường cụ thể hơn:

- Có bao nhiêu lần giữ hàng thành công và bao nhiêu lần thất bại?
- Độ trễ của kênh `web` có khác kênh `mobile` không?
- Sau một đợt triển khai, tỉ lệ lỗi của từng **loại thao tác** thay đổi thế nào?

Để trả lời, ta bổ sung cặp **key–value có cardinality thấp** vào observation. Ví dụ `channel=web`, `outcome=success`, `operation=reserve`. Các giá trị này thuộc tập nhỏ và có giới hạn, nên thích hợp làm chiều phân nhóm của metric.

Trong Micrometer Observation, API tiện dụng là:

~~~java
observation.lowCardinalityKeyValue("channel", "web");
~~~

Lệnh này ghi metadata vào context của observation. Khi hệ thống có handler metrics, các key–value phù hợp có thể trở thành tags/labels của phép đo; nếu có tracing handler, chúng cũng có thể được đưa vào span dưới dạng attributes. **Bản thân thao tác thêm key–value không tự tạo Timer, log, span hay gửi dữ liệu tới backend.** Những hành động đó phụ thuộc handler, registry và exporter được cấu hình.

### Phân biệt hai câu hỏi

| Câu hỏi | Cần gì? | Ví dụ |
| --- | --- | --- |
| “Tỉ lệ lỗi của mỗi kênh là bao nhiêu?” | Low-cardinality key–value | `outcome=error`, `channel=mobile` |
| “Đơn hàng số 8f7… bị chậm ở bước nào?” | Trace/log có định danh riêng | `orderId` trong span/log có chính sách kiểm soát |
| “Mỗi phút có bao nhiêu lần giữ hàng?” | Counter hoặc số đếm của Timer | Truy vấn `rate()` trên metric đã export |
| “Bước nào của request bị timeout?” | Span và logs được liên kết | Trace ID, span của DB/downstream |

Bài này tập trung vào **cách ghi và quản lý low-cardinality key–value trong vòng đời Observation**, chứ không thay thế các bài về cấu hình toàn bộ hệ thống metrics/traces.

## 2. Cardinality là số lượng giá trị có thể phân biệt

**Cardinality của một key** là số giá trị khác nhau của key đó. Với metrics, chi phí thực tế phụ thuộc số **tổ hợp labels** phát sinh, số phép đo, số instance, số histogram bucket và thời gian lưu.

Ví dụ cùng một metric có:

| Key | Tập giá trị | Số giá trị |
| --- | --- | ---: |
| `channel` | `web`, `mobile`, `partner` | 3 |
| `outcome` | `success`, `rejected`, `error` | 3 |
| `region` | `north`, `central`, `south` | 3 |

Nếu tất cả tổ hợp xuất hiện, riêng ba chiều này đã cho **3 × 3 × 3 = 27** tổ hợp. Với 8 instance và giả sử mỗi instance mang một label định danh riêng, backend có thể lưu tối đa **216 chuỗi** cho mỗi dạng metric có cùng tập nhãn. Một Timer xuất cả `_count`, `_sum` và nhiều `_bucket` sẽ còn nhân thêm số series.

Ngược lại, `order.id`, `request.id`, email hay session ID có thể tạo ra giá trị gần như duy nhất mỗi lần xử lý. Nếu đưa chúng vào metric tags, số chuỗi tăng theo số yêu cầu, gây hao RAM, tăng dữ liệu lưu trữ, làm truy vấn chậm và khiến hệ thống giám sát quá tải.

**Low cardinality không có nghĩa là “chuỗi ngắn”.** Giá trị `abcdef` có thể rất ngắn nhưng vẫn có vô số biến thể; tên kênh `mobile` có thể dài hơn mà vẫn chỉ nằm trong tập ba giá trị. Phải đánh giá **số giá trị có thể xuất hiện**, không dựa vào độ dài chuỗi.

## 3. Low-cardinality key–value nằm ở đâu trong Observation?

Trong Micrometer, `Observation` là đối tượng theo dõi một đơn vị công việc. Nó có `Observation.Context` chứa trạng thái và các key–value được bổ sung theo thời gian. `ObservationRegistry` điều phối những handler phản ứng với vòng đời này.

~~~mermaid
flowchart TD
    A["Tạo Observation: orders.reserve"] --> B["Thêm channel=web trước start"]
    B --> C["start() → onStart"]
    C --> D["openScope() → thao tác nghiệp vụ"]
    D --> E{"Kết quả"}
    E -->|Thành công| F["Thêm outcome=success"]
    E -->|Bị từ chối| G["Thêm outcome=rejected"]
    E -->|Lỗi kỹ thuật| H["Thêm outcome=error; error(ex)"]
    F --> I["Đóng scope và stop()"]
    G --> I
    H --> I
    I --> J["Handler metrics ghi mẫu với tags thích hợp"]
    I --> K["Handler tracing cập nhật span/attributes"]
~~~

Các mốc quan trọng:

1. **`createNotStarted`:** khởi tạo observation, chưa bắt đầu đo. Ta có thể gắn metadata đã biết như `channel` hoặc `operation`.
2. **`start()`:** kích hoạt `onStart` của các handler phù hợp. Một số handler cần metadata ngay lúc này để tạo resource, ví dụ LongTaskTimer.
3. **Thực thi nghiệp vụ:** có thể bổ sung tag phụ thuộc kết quả, như `outcome=success/error`. Trong luồng đồng bộ, mở scope khi cần current observation/trace context.
4. **`error(ex)`:** thông báo lỗi cho Observation để các handler nhận biết, ngoài việc tự ghi tag `outcome` theo định nghĩa nghiệp vụ.
5. **`stop()`:** hoàn tất phép đo. Meter handler thường tổng hợp duration và các low-cardinality keys sẵn có ở thời điểm kết thúc.

**Không nên thêm tag sau `stop()` và kỳ vọng dữ liệu lịch sử thay đổi.** Giá trị cần được cung cấp trước khi handler tiêu thụ nó. Đặc biệt, một handler xử lý metadata tại `onStart` có thể không thấy tag chỉ được thêm ở cuối; không phải mọi handler đều chờ đến `onStop`.

## 4. Cách ghi bằng API: một key hoặc nhiều key–value

### 4.1. Gắn từng cặp bằng `lowCardinalityKeyValue`

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

// observationRegistry do Spring Boot cung cấp qua dependency injection.
Observation observation = Observation.createNotStarted(
        "orders.reserve", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .lowCardinalityKeyValue("operation", "reserve")
    .start();

try {
    observation.lowCardinalityKeyValue("outcome", "success");
} finally {
    observation.stop();
}
~~~

Mỗi cặp có dạng **key → value**, chẳng hạn `channel → web`. Tên key nên có quy ước nhất quán qua các lần quan sát và không thay đổi tùy ý giữa những instance.

Trong ví dụ, `outcome` được thêm vào sau `start` chỉ để minh họa API. Khi triển khai, hãy đặt nó **sau khi biết kết quả thực tế**. Nếu thêm `success` trước khi nghiệp vụ chạy rồi thao tác thất bại, metric có thể mang kết quả sai.

### 4.2. Gắn nhiều cặp bằng `lowCardinalityKeyValues`

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;

Observation observation = Observation.createNotStarted(
        "orders.reserve", observationRegistry)
    .lowCardinalityKeyValues(
        KeyValues.of(
            "channel", "web",
            "operation", "reserve"
        )
    )
    .start();
~~~

`KeyValues` là cấu trúc của Micrometer Common để biểu diễn nhiều `KeyValue`. Có thể chọn kiểu API phù hợp với dữ liệu đã chuẩn bị. Với các key có khả năng trùng, hãy **thống nhất một nơi chịu trách nhiệm gán giá trị**, tránh trộn convention, filter và mã nghiệp vụ cùng đặt những giá trị mâu thuẫn.

### 4.3. Ghi trực tiếp vào `Observation.Context`

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;

Observation.Context context = observation.getContext();
context.addLowCardinalityKeyValue(
        KeyValue.of("outcome", "success")
);
~~~

Cách này hữu ích trong `ObservationFilter`, convention hoặc code cần thao tác với context. Khi đang ở service nghiệp vụ, API `observation.lowCardinalityKeyValue(...)` thường dễ đọc hơn.

Để xem các giá trị đã gắn trong context, có thể dùng `context.getLowCardinalityKeyValues()` khi cần chẩn đoán. Cần nhớ rằng đây là **metadata của observation**; backend có nhận được chúng hay không còn phụ thuộc handler và cấu hình.

## 5. Ví dụ Spring Boot đầy đủ: ghi channel và outcome đúng thời điểm

Tình huống: dịch vụ giữ hàng trước khi hoàn tất đơn. Ta muốn theo dõi `orders.reserve` theo kênh phát sinh (`web`, `mobile`, `partner`) và kết quả (`success`, `rejected`, `error`).

### 5.1. Service instrument công việc đồng bộ

~~~java
package example.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {
    private final ObservationRegistry observationRegistry;

    public ReservationService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public <T> T reserve(String incomingChannel, Supplier<T> operation) {
        String channel = normalizeChannel(incomingChannel);

        Observation observation = Observation.createNotStarted(
                "orders.reserve", observationRegistry)
            // Giá trị biết trước khi bắt đầu.
            .lowCardinalityKeyValue("channel", channel)
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = operation.get();

            // Chỉ đánh dấu success khi operation hoàn tất.
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (ReservationRejectedException ex) {
            observation.lowCardinalityKeyValue("outcome", "rejected");
            observation.error(ex);
            throw ex;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        if ("partner".equals(value)) return "partner";
        return "other";
    }

    // Ngoại lệ ví dụ; trong ứng dụng thật có thể đặt ở file riêng.
    public static final class ReservationRejectedException
            extends RuntimeException {
        public ReservationRejectedException(String reason) {
            super(reason);
        }
    }
}
~~~

**Ý nghĩa của từng điểm:**

- `channel` được chuẩn hóa **trước `start()`**; do đó tập giá trị là bốn lựa chọn định trước (`web`, `mobile`, `partner`, `other`). Nếu lấy nguyên chuỗi người dùng gửi lên, client có thể đưa hàng triệu giá trị khác nhau vào label.
- `outcome` được thêm **trước `stop()`**, sau khi xác định thành công hoặc thất bại. Hai nhánh lỗi và nhánh thành công có cùng **key**, khác giá trị; đây là yêu cầu tốt khi muốn so sánh rate giữa các kết quả.
- `observation.error(ex)` giúp các handler biết có exception; tự đặt `outcome=error` **không thay thế** việc báo lỗi này.
- `try-with-resources` đóng scope, còn `finally` dừng observation. Scope được dùng để các thành phần hỗ trợ context có thể nhận biết current observation và trace.
- Ví dụ bắt hai nhóm `RuntimeException`. Nếu code sử dụng cancellation, checked exception hoặc async, cần mở rộng chính sách kết quả để phù hợp. Đừng mặc định mọi lần không đi qua `catch` đều đã hoàn tất thành công.

Một lời gọi mẫu:

~~~java
String reservationId = reservationService.reserve(
    "web",
    () -> inventory.reserve(productId, requestedQuantity)
);
~~~

Trong ứng dụng thực, `inventory.reserve(...)` là lời gọi tới thành phần nghiệp vụ và cần được hiện thực riêng. ID trả về dùng để xử lý giao dịch, **không đưa vào low-cardinality key-value**.

### 5.2. Tại sao không đặt tag `orderId`?

Giả sử có 300.000 đơn hàng mỗi ngày. Với `orderId` là metric label, mỗi ngày có thể xuất hiện hàng trăm nghìn tập nhãn mới, ngay cả khi mọi request cùng một operation và outcome. Khi có nhiều instance, histogram buckets và chính sách giữ dữ liệu dài ngày, chi phí có thể tăng mạnh.

Nếu cần điều tra một đơn riêng lẻ, nên đưa ID vào log có kiểm soát hoặc trace attribute **theo chính sách quyền truy cập, bảo mật và sampling**. Dashboard metric chỉ cần phân nhóm như `channel`, `outcome`, `region` hoặc `operation` với số giá trị giới hạn.

## 6. Cấu hình Spring Boot để thấy tags trên metrics

### 6.1. Dependency và endpoint

Ví dụ dùng Spring Boot 3.x cùng Micrometer Observation. Trong Maven khi project dùng Spring Boot BOM/parent:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình minh họa trong `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Actuator cung cấp `ObservationRegistry`/tích hợp Micrometer theo auto-configuration. Khi registry và các handler phù hợp được đăng ký, một observation đã instrument có thể tạo metric. `micrometer-registry-prometheus` cung cấp registry và endpoint xuất Prometheus. Không cần tạo một `ObservationRegistry.create()` mới trong service, vì registry mới có thể bị tách khỏi cấu hình của Spring.

Trong môi trường production, giới hạn truy cập vào endpoint quản trị và thiết lập auth/network phù hợp; endpoint scrape chỉ nên truy cập được từ hệ thống giám sát.

### 6.2. Quan sát kết quả

Sau khi có các lần giữ hàng thành công và lỗi, thử:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/orders.reserve
curl "http://localhost:8080/actuator/metrics/orders.reserve?tag=outcome:success"
curl http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics/orders.reserve` có thể hiển thị `availableTags` như `channel`, `outcome`, tùy handler và instrumentation. Trong đầu ra Prometheus, Timer `orders.reserve` thường tương ứng với series như `orders_reserve_seconds_count` và `orders_reserve_seconds_sum`. Tên được đổi theo convention, vì vậy **xem exporter thực tế** trước khi viết quy tắc cảnh báo.

Khi không thấy tên metric, kiểm tra observation đã được **thực thi và stop**, handler meter có được cấu hình, hay instrumentation bị chặn bởi predicate. Mỗi observation chỉ được tạo ở runtime khi đường code tương ứng được gọi; việc có dependency không tự sinh metric nghiệp vụ `orders.reserve`.

## 7. Low cardinality, high cardinality và dữ liệu chỉ nằm trong context

Ba loại dữ liệu dưới đây có vai trò khác nhau, dù cùng được đính kèm trong quá trình quan sát.

| Dữ liệu | API hoặc vị trí | Phù hợp với | Ví dụ |
| --- | --- | --- | --- |
| **Low-cardinality key–value** | `observation.lowCardinalityKeyValue(k, v)` | Metrics tags và trace attributes | `outcome=success`, `channel=web` |
| **High-cardinality key–value** | `observation.highCardinalityKeyValue(k, v)` | Dữ liệu chi tiết trên span khi cần; không dùng làm metric label | Định danh yêu cầu, ID nghiệp vụ sau khi xem xét chính sách |
| **State riêng của context** | `Observation.Context.put/get` hoặc field của context chuyên biệt | Truyền thông tin giữa callback/handler | Đối tượng trạng thái nội bộ cho phép đo |

Ví dụ:

~~~java
observation.lowCardinalityKeyValue("outcome", "success");
observation.highCardinalityKeyValue("order.id", orderId);
observation.getContext().put("internal.phase", "saved");
~~~

Đây là ba hành vi khác nhau:

1. `outcome` có tập giá trị nhỏ, hỗ trợ phép tính tỉ lệ thành công hoặc lỗi.
2. `order.id` có tính phân biệt rất cao, do đó **không chuyển thành label metrics**. Việc đưa ID vào trace phải cân nhắc dữ liệu nhạy cảm; không mặc nhiên coi mọi identifier đều được phép xuất.
3. `internal.phase` trong context không tự động thành metric tag hoặc span attribute. Context có thể lưu dữ liệu phục vụ logic instrument/handler.

Low-cardinality tags được metrics handler sử dụng theo cấu hình; high-cardinality tags thường phù hợp với tracing handler. **Sampling tracing không đồng nghĩa sampling metrics**: nhiều request vẫn có thể góp vào Timer, dù chỉ một phần request được lưu thành trace. Vì thế không suy thông lượng hệ thống từ số trace được xuất.

## 8. Thiết kế key và giá trị ổn định

Khi một metric có nhiều instance và tồn tại lâu dài, tag là một phần của **hợp đồng dữ liệu** giữa ứng dụng với dashboard, alert và SLO.

### 8.1. Quy ước đề xuất

- Dùng key diễn tả một chiều nghiệp vụ/kỹ thuật cụ thể, chẳng hạn `channel`, `outcome`, `operation`, `region`.
- Định nghĩa danh sách giá trị cho từng key và ánh xạ giá trị lạ về `other` hoặc `unknown` khi phù hợp.
- Giữ semantics nhất quán: `outcome=error` biểu thị lỗi kỹ thuật, `outcome=rejected` biểu thị từ chối hợp lệ theo quy tắc nghiệp vụ. Nếu không phân biệt, báo cáo có thể đánh đồng hai loại.
- Đảm bảo mọi lần ghi của cùng metric có **bộ key cần thiết ổn định**. Một số kết quả không có `outcome` sẽ khiến truy vấn lọc theo outcome bị thiếu mẫu.
- Không đưa URL thực chứa ID, SQL tự do, stack trace, exception message, email, token, hostname tạo tự do hoặc HTTP query string vào low-cardinality value.

### 8.2. Chọn dimensions có ích

| Nhu cầu | Key thích hợp | Tránh dùng |
| --- | --- | --- |
| So sánh kênh vào | `channel=web/mobile/partner/other` | `userAgent` nguyên chuỗi tùy ý |
| So sánh kết quả nghiệp vụ | `outcome=success/rejected/error` | `exception.message` |
| So sánh loại thao tác | `operation=reserve/release/commit` | `orderId` |
| Phân tích API | `uri=/api/orders/{id}` (route template) | `uri=/api/orders/123456` |
| So sánh môi trường | `deployment.environment=dev/staging/prod` | Chuỗi tự do chứa request ID hoặc build timestamp ở mỗi lời gọi |

Không phải key nào cũng cần thêm vào mọi observation. Mỗi chiều tạo thêm khả năng phân tích nhưng cũng tạo chi phí. Chỉ giữ những chiều hỗ trợ quyết định vận hành cụ thể.

### 8.3. Khi nào cần key `unknown`?

Khi giá trị chưa có sẵn hoặc đường code có nhiều nhánh lỗi, `unknown` là fallback rõ ràng hơn việc lặng lẽ bỏ tag. Tuy nhiên không nên gán mặc định `success` trước khi biết kết quả. Với luồng có ngoại lệ ngoài `RuntimeException` hoặc bị hủy, hãy định nghĩa trạng thái `cancelled`/`unknown` và áp dụng nhất quán theo semantics thực tế.

## 9. Ghi tag tại service, convention hay filter?

Có nhiều cách đưa low-cardinality metadata vào một observation. Vị trí đặt phụ thuộc **nguồn gốc** của dữ liệu.

| Cách | Dùng khi nào? | Lưu ý |
| --- | --- | --- |
| API `observation.lowCardinalityKeyValue` | Service biết trực tiếp `channel` hoặc `outcome` | Minh bạch, ngay sát thao tác |
| `ObservationConvention` | Nhiều observation cần chung quy ước tên và tags dựa trên kiểu context | Giảm lặp lại và chuẩn hóa semantics |
| `ObservationFilter` | Muốn bổ sung/điều chỉnh metadata có thể lấy từ context trước khi hoàn tất | Đảm bảo filter được đăng ký vào đúng registry |
| Custom `ObservationHandler` | Muốn **phản ứng** với vòng đời, đọc tags để cập nhật metrics/traces/logs | Không phải lựa chọn mặc định chỉ để đặt tên một tag |
| Common tags tại meter registry | Muốn gắn nhãn cho các metrics xuất ra | Phạm vi là meter/metrics, không thay thế metadata của observation hoặc span |

Ví dụ trực tiếp của `ObservationFilter` (đăng ký trong bước cấu hình `ObservationRegistry`):

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationRegistry;

void configureFilter(ObservationRegistry registry) {
    registry.observationConfig().observationFilter(context -> {
        if ("orders.reserve".equals(context.getName())) {
            context.addLowCardinalityKeyValue(
                    KeyValue.of("component", "inventory")
            );
        }
        return context;
    });
}
~~~

Đây là một **đoạn cấu hình**, không phải lệnh gọi trong mỗi request. Thực hiện đăng ký một lần khi ứng dụng khởi tạo và dùng registry đã được Spring Boot cấu hình. Tránh gán cùng key tại nhiều nơi với các giá trị khác nhau. ObservationFilter bổ sung context khi lifecycle đi đến giai đoạn hoàn tất; handler cần tag ở `onStart` có thể không nhìn thấy giá trị thêm muộn.

Với `ObservationConvention`, ta thường định nghĩa **tên observation, contextual name và tập key–value có cardinality thấp/cao** dựa trên context nghiệp vụ. Nên dùng convention khi nhiều lớp cùng cần một chuẩn đo lường, thay vì copy-paste các chuỗi key/value ở nhiều service.

## 10. Dùng low-cardinality tags trong PromQL

Giả sử đã có Timer `orders.reserve` xuất ra `orders_reserve_seconds_count`. Các ví dụ dưới đây chỉ đúng khi exporter thực tế có tên series và labels phù hợp.

**Số lần thử giữ hàng mỗi giây, chia theo kết quả:**

~~~promql
sum by (outcome) (
  rate(orders_reserve_seconds_count[5m])
)
~~~

**Tỉ lệ lỗi kỹ thuật trong toàn bộ các lần thử:**

~~~promql
sum(rate(orders_reserve_seconds_count{outcome="error"}[5m]))
/
sum(rate(orders_reserve_seconds_count[5m]))
~~~

Kết quả là tỉ lệ 0–1. Nếu không có traffic trong cửa sổ truy vấn, mẫu số có thể bằng 0; dashboard và alert cần định nghĩa riêng cách thể hiện trường hợp thiếu dữ liệu.

**Tốc độ thất bại theo kênh:**

~~~promql
sum by (channel) (
  rate(orders_reserve_seconds_count{outcome="error"}[5m])
)
~~~

Nếu `outcome=rejected` nghĩa là yêu cầu bị từ chối hợp lệ, thường **không nên** gộp ngay vào lỗi hệ thống. Cách chọn numerator/denominator của SLI/SLO phải phản ánh hợp đồng nghiệp vụ.

**Độ trễ trung bình của thao tác theo kênh (giây):**

~~~promql
sum by (channel) (
  rate(orders_reserve_seconds_sum[5m])
)
/
sum by (channel) (
  rate(orders_reserve_seconds_count[5m])
)
~~~

Đây là **trung bình**, không phải p95. Để tính p95 phân phối bằng `histogram_quantile()` cần histogram đã được cấu hình và có các series `_bucket`; khi đó phải cộng theo `le` và những dimensions cần giữ lại. Tags giúp phân nhóm, nhưng bản thân việc thêm key–value **không bật histogram**.

## 11. Liên kết tags với logs và distributed tracing

Trong hệ thống nhiều dịch vụ, một request có thể tạo cả metrics, logs và traces:

~~~mermaid
flowchart LR
    A["Order API"] --> B["Observation với channel, outcome"]
    B --> C["Metrics handler"]
    B --> D["Tracing handler"]
    B --> E["Log enrichment / MDC"]
    C --> F["RPS, error rate, latency theo channel"]
    D --> G["Span có attributes + trace context"]
    E --> H["Log có traceId/spanId khi được cấu hình"]
    F --> I["Phát hiện bất thường"]
    I --> G
    G --> H
~~~

Low-cardinality tags như `channel`, `outcome` giúp khoanh vùng trên dashboard; trace/span ID giúp chuyển sang điều tra một request cụ thể. Trong Spring Boot, khả năng liên kết log với trace phụ thuộc cấu hình tracing, logging pattern và context propagation.

**Ba điểm dễ hiểu sai:**

- Thêm `orderId` thành low-cardinality tag để “tìm nhanh log của đơn đó” là thiết kế sai cho metrics. Nếu cần định danh, dùng log/trace theo chính sách truy cập và bảo mật.
- Có observation không có nghĩa mọi request đều xuất thành trace. Sampler có thể chỉ giữ một phần dấu vết; metrics và tracing được quản lý riêng.
- Việc gọi `observation.lowCardinalityKeyValue(...)` trong thread A không đảm bảo current observation/trace context tự đi sang thread B. Executor, Reactor hoặc lời gọi HTTP xuyên dịch vụ cần cơ chế propagation thích hợp.

### Khi công việc là bất đồng bộ

Mẫu `try/finally` đồng bộ ở phần 5 **không được sao chép nguyên** cho tác vụ có kết quả trả về sau này, ví dụ một `CompletableFuture` đang chạy. Nếu gọi `stop()` ngay sau khi submit công việc, duration chỉ đo thời gian khởi tạo, còn `outcome` chưa phản ánh kết quả thật.

Với async, cần xác định **lúc hoàn tất thực tế** để đặt `outcome` và `stop()`, đồng thời truyền scope/context an toàn theo cơ chế framework. Không giữ scope của một thread mở vô hạn để chờ callback trên thread khác; quản lý vòng đời của scope theo từng luồng thực thi.

## 12. Các lỗi phổ biến khi ghi low-cardinality key value

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Dashboard không có tag `outcome` | Không gắn tag trên mọi nhánh, gắn sau `stop` hoặc không có handler metrics | Bổ sung tag trước stop; kiểm tra callback/registry |
| Lỗi vẫn hiển thị `outcome=success` | Đặt success trước thao tác rồi không sửa đúng | Gán theo kết quả thực tế, cân nhắc case bị hủy |
| Series tăng mạnh sau deploy | Thêm tag có giá trị không giới hạn như `userId` | Thay bằng danh mục hữu hạn; rà soát labels thực tế |
| Có low-cardinality key nhưng không thấy metric | Chưa có Meter ObservationHandler hoặc instrumentation chưa chạy | Kiểm tra Actuator/registry, số lần stop và exporter |
| Có metric nhưng không thấy span tương ứng | Tracing chưa bật, thiếu exporter, sampler loại trace hoặc context chưa propagate | Kiểm tra riêng tracing pipeline |
| Dữ liệu theo kênh bị tách rời | Cùng ý nghĩa nhưng dùng `mobile-app`, `MOBILE`, `mobile` lẫn lộn | Chuẩn hóa giá trị trước khi thêm tag |
| Phép đo cùng tên có bộ labels không nhất quán | Các nhánh code gắn tag khác nhau | Thiết lập contract cho bộ keys bắt buộc |
| Tag thêm ở cuối không xuất hiện trong LongTaskTimer | Handler cần dữ liệu từ `onStart` | Ghi key cần thiết trước `start()` |
| Kết quả metric không khớp số lượng trace | Trace có sampling | So sánh theo metric đã tổng hợp, không suy số request bằng số trace |

Khi chẩn đoán, nên bắt đầu từ `/actuator/metrics` để biết meter có tồn tại, rồi kiểm tra labels ở `/actuator/prometheus`. Nếu tên metric thay đổi, hãy xác minh convention của registry và handler đang chạy; tránh đoán theo tên observation.

## 13. Bài thực hành theo bước

Một ứng dụng cung cấp `POST /api/checkout`, nhận yêu cầu từ `web`, `mobile` hoặc `partner`. Giả sử mã nghiệp vụ có thể thành công, bị từ chối do thiếu hàng hoặc thất bại vì timeout.

**Nhiệm vụ 1: Thiết kế labels**

Đề xuất ba key:

- `channel`: `web`, `mobile`, `partner`, `other`.
- `outcome`: `success`, `rejected`, `error`.
- `operation`: `checkout`.

Tính số tổ hợp labels tối đa cho 3 key trên, chưa tính instance hoặc histogram. Kết quả: **4 × 3 × 1 = 12**. Giải thích vì sao việc thêm `orderId` không phù hợp.

**Nhiệm vụ 2: Instrument vòng đời**

Viết một phương thức dùng `ObservationRegistry` và `Observation.createNotStarted(...)`. Đặt `channel` trước `start()`, đặt `outcome` sau khi biết kết quả, báo lỗi qua `error(ex)` và luôn `stop()` trong `finally`. Kiểm tra scope được đóng kể cả khi có exception.

**Nhiệm vụ 3: Xác nhận dữ liệu**

Thực hiện ít nhất một lời gọi của mỗi outcome. Kiểm tra `/actuator/metrics` và `/actuator/prometheus` có tags mong đợi; viết PromQL tính:

- RPS mỗi outcome trong cửa sổ 5 phút.
- Tỉ lệ `outcome=error` trên tất cả các lần thử.
- Thời gian trung bình theo `channel`.

**Nhiệm vụ 4: Xử lý tình huống khó**

Xem xét trường hợp thao tác trả về `CompletableFuture`. Hãy xác định lúc nào mới đủ thông tin để gắn `outcome` và gọi `stop()`; nêu cách quản lý propagation khi callback thực thi trên thread khác.

### Câu hỏi tự kiểm tra

1. Low-cardinality khác high-cardinality ở khía cạnh nào? Vì sao một chuỗi ID rất ngắn vẫn có thể không phù hợp làm metric label?
2. Nếu thêm `outcome` sau `stop()`, điều gì có thể xảy ra với Timer đã được ghi?
3. Vì sao low-cardinality key–value gắn trên Observation không tự xuất hiện ở Prometheus?
4. Khi nào nên gắn key ở đầu observation, khi nào nên chờ kết quả xử lý?
5. Vì sao `observation.error(ex)` và `outcome=error` không hoàn toàn thay thế cho nhau?
6. Một custom handler xử lý `onStart` có bắt buộc thấy tag do `ObservationFilter` thêm gần `onStop` không?
7. Nếu chỉ thấy 10 trace nhưng Timer ghi 1.000 request, có thể kết luận metrics sai không? Vì sao?

**Tiêu chí hoàn thành:** ghi được low-cardinality tags đúng vòng đời; phân biệt low/high/context; kiểm soát tập giá trị và sự nhất quán nhãn; đọc được dữ liệu trên Actuator/Prometheus; kết hợp kết quả với logs/traces mà không làm tăng cardinality của metrics.

## Ghi nhớ

- `lowCardinalityKeyValue(key, value)` bổ sung cặp metadata hữu hạn cho Observation; **handler và exporter** mới quyết định tín hiệu nào được tạo và đi đâu.
- Gắn metadata biết trước **trước `start()`** khi cần; gắn metadata kết quả **trước `stop()`** sau khi nghiệp vụ hoàn tất.
- Chọn bộ key và giá trị có giới hạn, chuẩn hóa giữa các instance, và đảm bảo cùng một metric có contract labels ổn định.
- Không đưa định danh từng request/đơn hàng hoặc dữ liệu nhạy cảm vào metric labels. Khi cần điều tra cá thể, dùng logs/traces và context propagation thích hợp.
- Đọc số liệu bằng cách kiểm tra Actuator, series Prometheus thực tế và truy vấn theo key; nhớ rằng sampling traces không làm số đếm metric mặc nhiên giảm theo.

## Tài liệu tham khảo

- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Reference — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

