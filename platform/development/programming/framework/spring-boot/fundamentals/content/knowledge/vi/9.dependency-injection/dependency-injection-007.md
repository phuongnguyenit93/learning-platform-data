# `Optional`, `@Nullable` và dependency không bắt buộc

> **Spring Boot Fundamentals · Tiêm phụ thuộc**  
> Constructor injection giúp một class khai báo rõ những dependency cần có để hoạt động. Nhưng đôi khi một tích hợp chỉ được bật ở một số môi trường, một extension do module khác cung cấp, hoặc một dịch vụ phụ trợ có thể vắng mặt. Spring hỗ trợ nhiều cách biểu diễn dependency không bắt buộc, nổi bật là **`Optional<T>`**, **`@Nullable`** và **`ObjectProvider<T>`**. Chọn đúng cách giúp ứng dụng khởi động ổn định, đồng thời làm rõ hành vi khi bean không tồn tại.

## 1. Dependency bắt buộc và dependency tùy chọn

Giả sử một dịch vụ xử lý đơn hàng cần repository để lưu đơn:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

`OrderRepository` là dependency bắt buộc. Nếu Spring không tìm thấy bean phù hợp, ứng dụng thường không thể tạo `OrderService` và quá trình khởi động context thất bại. Đây là hành vi tốt: hệ thống không nên âm thầm chạy khi thiếu thành phần thiết yếu.

Ngược lại, giả sử ứng dụng có một tích hợp gửi thông báo audit. Ở một số môi trường, audit được bật; trong một môi trường chạy demo hoặc test, tích hợp đó có thể không được cài đặt. Nếu nghiệp vụ chính vẫn hợp lệ khi không có audit sink, ta có thể mô tả dependency này là **không bắt buộc**.

| Loại dependency | Khi bean không tồn tại | Hành vi mong muốn |
| --- | --- | --- |
| Bắt buộc | Không thể tạo bean consumer; context thường khởi động lỗi | Fail fast để phát hiện cấu hình thiếu |
| Tùy chọn | Consumer vẫn có thể được tạo | Dùng fallback, bỏ qua tính năng phụ hoặc xử lý theo chính sách rõ ràng |
| Nhiều bean cùng loại | Có thể không xác định được ứng viên | Dùng qualifier/primary hoặc xử lý danh sách |
| Bean chỉ cần tại một thời điểm sau startup | Không nhất thiết cần tra cứu ngay lúc tạo consumer | Dùng provider/lazy lookup khi phù hợp |

**Tùy chọn là một quyết định nghiệp vụ và kiến trúc, không chỉ là cách tránh lỗi khởi động.** Trước khi biến dependency thành optional, hãy xác định ứng dụng được phép làm gì khi bean đó vắng mặt.

### 1.1. Spring xử lý dependency bắt buộc ra sao?

Với constructor:

```java
@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
```

Spring cần giải quyết một bean `ReportRepository` phù hợp. Nếu không có ứng viên, thường sẽ phát sinh lỗi như `NoSuchBeanDefinitionException` hoặc một lỗi tạo bean được bọc trong `UnsatisfiedDependencyException`.

Đó không phải lỗi cần che giấu bằng cách thêm `null` tùy tiện. Nếu service không thể hoạt động khi thiếu repository, để Spring báo lỗi ngay khi startup là lựa chọn đúng.

### 1.2. Khi nào dependency thực sự là tùy chọn?

Một dependency có thể là tùy chọn khi:

- Nó cung cấp tính năng bổ sung, không quyết định tính đúng đắn của nghiệp vụ chính.
- Có fallback hợp lệ khi bean không tồn tại.
- Việc bật/tắt tích hợp được chủ đích theo môi trường hoặc module.
- Consumer có thể hoạt động an toàn khi thiếu bean.
- Trạng thái thiếu bean được quan sát hoặc ghi nhận nếu điều đó quan trọng.

Không nên làm optional một dependency cốt lõi chỉ để ứng dụng “khởi động cho qua”. Ví dụ, nếu dịch vụ thanh toán cần gateway để hoàn thành giao dịch, thiếu gateway phải được thể hiện thành lỗi cấu hình hoặc trạng thái không sẵn sàng, chứ không nên âm thầm bỏ qua thanh toán.

## 2. `Optional<T>` trong constructor injection

`java.util.Optional<T>` biểu diễn một giá trị có thể có hoặc không có. Spring hỗ trợ dùng `Optional<T>` làm kiểu tham số injection: nếu có bean phù hợp, consumer nhận `Optional.of(bean)`; nếu không có, consumer nhận `Optional.empty()`.

Ví dụ:

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final Optional<AuditSink> auditSink;

    public OrderService(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    public void placeOrder(Order order) {
        // Xử lý và lưu đơn hàng ở đây.

        auditSink.ifPresent(sink ->
                sink.publish(new OrderPlacedEvent(order.id())));
    }
}
```

Giả sử `AuditSink` là interface của ứng dụng:

```java
package com.example.orders;

public interface AuditSink {
    void publish(OrderPlacedEvent event);
}
```

Nếu một implementation `AuditSink` được đăng ký, Spring inject nó vào `Optional`. Nếu không có bean phù hợp, `auditSink` là `Optional.empty()` và service vẫn được tạo.

Ví dụ này giả định audit là tính năng phụ. Nếu audit là yêu cầu bắt buộc về tuân thủ, không nên bỏ qua như vậy; cần cấu hình để ứng dụng không khởi động hoặc không nhận traffic khi audit infrastructure chưa sẵn sàng.

### 2.1. Sử dụng Optional đúng cách

Một số cách xử lý:

```java
auditSink.ifPresent(sink -> sink.publish(event));
```

Chỉ thực hiện khi bean tồn tại.

```java
String channel = auditSink
        .map(AuditSink::channelName)
        .orElse("audit-disabled");
```

Tạo giá trị thay thế khi bean không tồn tại.

```java
AuditSink sink = auditSink.orElseThrow(
        () -> new IllegalStateException("Audit is required here"));
```

Chuyển trường hợp thiếu bean thành lỗi tại điểm mà tính năng thật sự cần nó. Nếu thiếu audit là lỗi cấu hình, thường nên phát hiện sớm hơn trong startup thay vì đợi đến một request hiếm gặp.

Tránh gọi `get()` mà không kiểm tra:

```java
AuditSink sink = auditSink.get(); // Có thể ném NoSuchElementException.
```

Nếu đã biết chắc bean phải tồn tại, hãy cân nhắc khai báo dependency bắt buộc trực tiếp trong constructor. Dùng `Optional` rồi luôn gọi `get()` thường chỉ làm code phức tạp hơn mà không mang lại lợi ích.

### 2.2. Optional không có nghĩa là Spring inject null

Với kiểu `Optional<AuditSink>`, kết quả biểu diễn hai trạng thái bằng chính API Optional:

- Có bean: `Optional.of(auditSinkBean)`.
- Không có bean: `Optional.empty()`.

Consumer không phải tự kiểm tra `null` trên đối tượng Optional. Spring cung cấp wrapper hợp lệ trong cả hai trường hợp.

### 2.3. Điều gì xảy ra khi có nhiều bean cùng kiểu?

`Optional<T>` giải quyết tình huống **không có bean**; nó không tự giải quyết sự mơ hồ khi có nhiều ứng viên.

Giả sử có hai bean `AuditSink` mà không có quy tắc chọn rõ ràng:

```java
@Bean
AuditSink fileAuditSink() {
    return new FileAuditSink();
}

@Bean
AuditSink remoteAuditSink() {
    return new RemoteAuditSink();
}
```

Khi inject `Optional<AuditSink>`, Spring vẫn phải xác định bean nào phù hợp. Nếu có nhiều ứng viên ngang nhau, việc resolve có thể thất bại với lỗi không có bean duy nhất, ví dụ `NoUniqueBeanDefinitionException`.

Dùng `@Qualifier`:

```java
public OrderService(
        @Qualifier("remoteAuditSink") Optional<AuditSink> auditSink) {
    this.auditSink = auditSink;
}
```

Hoặc dùng `@Primary` trên bean được chọn làm ứng viên mặc định. Nếu muốn dùng tất cả implementation, inject `List<AuditSink>` hoặc `Map<String, AuditSink>` thay vì Optional đơn.

## 3. `@Nullable`: tham số có thể nhận null

Một cách khác để mô tả dependency không bắt buộc là đánh dấu tham số injection bằng `@Nullable`. Khi không có bean phù hợp, Spring có thể truyền `null` cho tham số đó thay vì yêu cầu một bean bắt buộc.

Ví dụ dùng annotation của Spring Framework 6 (thường đi cùng Spring Boot 3):

```java
package com.example.orders;

import org.springframework.lang.Nullable;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final NotificationSender sender;

    public OrderNotificationService(
            @Nullable NotificationSender sender) {
        this.sender = sender;
    }

    public void notifyOrder(Order order) {
        if (sender != null) {
            sender.sendOrderPlaced(order);
        }
    }
}
```

Nếu có bean `NotificationSender` phù hợp, Spring truyền bean đó. Nếu không có, Spring có thể truyền `null` do tham số được đánh dấu nullable.

`@Nullable` đồng thời diễn đạt **hợp đồng nullability**: consumer phải chấp nhận khả năng giá trị không có. Nó không phải một annotation để đánh dấu bean là optional trong mọi tình huống bất kỳ; hiệu quả injection phụ thuộc vị trí và cơ chế Spring hỗ trợ.

### 3.1. Chọn đúng annotation `@Nullable`

Có một số annotation mang tên `Nullable` trong hệ sinh thái Java. Với ứng dụng Spring Boot 3.x dùng Spring Framework 6, ví dụ thường gặp là:

```java
import org.springframework.lang.Nullable;
```

Hãy dùng annotation được framework và công cụ phân tích nullability của dự án hỗ trợ. Trong Spring Framework 7 và các hệ sinh thái mới hơn, Spring chuyển sang hướng null-safety dựa trên JSpecify; các annotation Spring cũ có thể bị đánh dấu deprecated theo phiên bản. Nếu dự án dùng phiên bản mới, theo tài liệu của đúng version và dùng `org.jspecify.annotations.Nullable` khi phù hợp.

Không nên trộn tùy tiện các annotation cùng tên từ thư viện khác nhau mà không biết Spring, IDE và compiler plugin nhận diện chúng thế nào.

### 3.2. Luôn kiểm tra null ở consumer

Vì Spring có thể truyền `null`, code phải xử lý rõ:

```java
if (sender != null) {
    sender.sendOrderPlaced(order);
}
```

Nếu quên kiểm tra, lỗi `NullPointerException` chỉ xuất hiện khi môi trường không cung cấp bean. Đây là lý do Optional thường dễ đọc hơn: compiler và API buộc người viết biểu diễn hai trạng thái.

### 3.3. `@Nullable` không giải quyết bean ambiguity

Nếu có hai `NotificationSender` cùng phù hợp, tham số nullable không nói Spring nên chọn bean nào. `@Nullable` chỉ làm cho **sự vắng mặt** được chấp nhận; nếu có nhiều ứng viên không phân biệt được, cần `@Qualifier`, `@Primary` hoặc một kiểu injection khác.

Ví dụ:

```java
public OrderNotificationService(
        @Nullable @Qualifier("emailSender") NotificationSender sender) {
    this.sender = sender;
}
```

Ở đây qualifier chọn vai trò bean; nullable cho phép bean mang qualifier đó vắng mặt.

## 4. So sánh `Optional<T>` và `@Nullable`

Cả hai đều có thể biểu diễn dependency không bắt buộc trong injection point mà Spring hỗ trợ, nhưng chúng truyền đạt ý định khác nhau.

| Tiêu chí | `Optional<T>` | `@Nullable T` |
| --- | --- | --- |
| Biểu diễn khi không có bean | `Optional.empty()` | `null` |
| Biểu diễn khi có bean | `Optional.of(bean)` | Bean trực tiếp |
| Consumer phải xử lý | Kiểm tra Optional hoặc dùng API của nó | Kiểm tra null |
| Mức độ tường minh ở kiểu dữ liệu | Cao: kiểu nói rõ có thể không có | Dựa vào annotation |
| Hợp đồng nullability | Giá trị Optional không null; phần tử có thể vắng mặt | Giá trị tham số có thể null |
| Phong cách sử dụng | `ifPresent`, `map`, `orElse`, `orElseThrow` | `if (value != null)` |
| Phù hợp khi | Muốn thể hiện rõ dependency tùy chọn bằng Java type | Codebase đã dùng nullability annotation nhất quán hoặc cần kiểu trực tiếp |
| Hạn chế | Có thể thêm wrapper và phải tránh lạm dụng | Dễ quên null check; annotation phải được tool/framework nhận diện |

### 4.1. Chọn một cách cho mỗi dependency

Tránh viết cả hai dạng cho cùng một tham số, chẳng hạn `@Nullable Optional<AuditSink>`. Điều đó tạo ra hai lớp “có thể không có”:

- Tham số Optional có thể rỗng.
- Bản thân tham số Optional lại có thể null.

Trong thiết kế thông thường, Spring inject Optional không null, nên đánh dấu nullable cho chính wrapper không có ích và dễ làm API khó hiểu.

Chọn `Optional<T>` **hoặc** `@Nullable T` dựa trên quy ước dự án và cách consumer xử lý.

### 4.2. Optional injection khác Optional trong dữ liệu nghiệp vụ

Đây là hai ngữ cảnh khác nhau:

- `Optional<AuditSink>` trong constructor: biểu diễn **có hay không có một bean** trong ApplicationContext.
- `Optional<PromotionCode>` trong method nghiệp vụ: biểu diễn **dữ liệu của một lần xử lý** có hay không.

Không nên biến mọi field có thể vắng mặt thành một Spring bean optional. Ví dụ, địa chỉ giao hàng thứ hai, mã khuyến mãi hoặc số điện thoại phụ thường là dữ liệu nghiệp vụ, không phải dependency injection.

## 5. `ObjectProvider<T>` khi cần tra cứu linh hoạt hoặc trì hoãn

`Optional<T>` và `@Nullable T` thường được giải quyết khi Spring tạo bean consumer. Nếu cần **lấy bean tại thời điểm sử dụng**, hỗ trợ lazy lookup hoặc làm việc với nhiều ứng viên, Spring có `ObjectProvider<T>`.

Ví dụ:

```java
package com.example.orders;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ObjectProvider<AuditSink> auditSinkProvider;

    public OrderService(ObjectProvider<AuditSink> auditSinkProvider) {
        this.auditSinkProvider = auditSinkProvider;
    }

    public void placeOrder(Order order) {
        // Xử lý đơn hàng...

        auditSinkProvider.ifAvailable(
                sink -> sink.publish(new OrderPlacedEvent(order.id())));
    }
}
```

Spring có thể inject provider ngay cả khi không có `AuditSink`. Khi gọi `ifAvailable`, provider mới tra cứu bean phù hợp trong context.

Các phương thức thường dùng:

| Phương thức | Hành vi |
| --- | --- |
| `getIfAvailable()` | Trả bean nếu tìm được; trả `null` nếu không có; có thể báo lỗi nếu nhiều ứng viên không xác định được |
| `getIfUnique()` | Trả bean nếu có ứng viên duy nhất hoặc primary; trả `null` nếu không có hoặc không xác định được duy nhất |
| `ifAvailable(Consumer<T>)` | Gọi consumer khi có bean phù hợp |
| `ifUnique(Consumer<T>)` | Gọi consumer khi tìm được bean duy nhất |
| `getObject()` | Lấy bean bắt buộc; báo lỗi nếu không có ứng viên phù hợp |
| `stream()` | Duyệt các bean theo kiểu được cung cấp |
| `orderedStream()` | Duyệt các bean theo thứ tự được Spring xác định khi có ordering metadata |

Cách hoạt động chi tiết còn tùy scope và cách bean được tạo. Provider không tự biến một prototype thành singleton hoặc bảo đảm một bean có thể khởi tạo thành công; nó chỉ cung cấp cơ chế tra cứu.

### 5.1. Optional và Provider khác nhau ở thời điểm tra cứu

| | `Optional<T>` | `ObjectProvider<T>` |
| --- | --- | --- |
| Giá trị inject vào consumer | Wrapper chứa bean hoặc rỗng | Một đối tượng provider |
| Thời điểm tra cứu | Khi giải quyết dependency lúc tạo consumer | Khi gọi provider |
| Dùng bean nhiều lần | Giữ tham chiếu Optional đã inject | Có thể tra cứu theo từng lần gọi |
| Lấy tất cả bean cùng kiểu | Không phải mục tiêu chính | Có `stream()`/`orderedStream()` |
| Hữu ích cho | Một dependency tùy chọn ổn định | Lookup lazy, nhiều bean, bean có scope động hoặc provider/factory |
| Độ phức tạp | Đơn giản | Linh hoạt hơn, nhưng thêm một lớp gián tiếp |

Nếu chỉ cần một bean optional tại startup, `Optional<T>` thường đủ. Đừng chọn `ObjectProvider` chỉ vì thấy nó mạnh hơn; dùng nó khi cần khả năng tra cứu động hoặc lazy thực sự.

### 5.2. Trường hợp có nhiều implementation

Một ứng dụng plugin có thể có nhiều `PaymentNotifier` hoặc `AuditSink`. Khi muốn gọi tất cả:

```java
@Service
public class EventPublisher {

    private final List<AuditSink> sinks;

    public EventPublisher(List<AuditSink> sinks) {
        this.sinks = sinks;
    }

    public void publish(OrderPlacedEvent event) {
        sinks.forEach(sink -> sink.publish(event));
    }
}
```

Spring thường inject collection rỗng nếu không có bean phù hợp, do đó consumer có thể xử lý danh sách mà không cần `Optional<List<AuditSink>>` trong tình huống thông thường.

Nếu cần tra cứu danh sách bean tại thời điểm sử dụng, `ObjectProvider<AuditSink>` với `orderedStream()` là một lựa chọn.

## 6. Optional setter injection và `@Autowired(required = false)`

Spring cũng hỗ trợ dependency không bắt buộc thông qua một số kiểu method injection. Ví dụ setter:

```java
@Component
public class LegacyReportService {

    private MetricsRecorder metricsRecorder;

    @Autowired(required = false)
    public void setMetricsRecorder(MetricsRecorder metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }
}
```

Với `required = false`, Spring không yêu cầu phải tìm thấy bean cho điểm injection này. Nếu dependency không có, phương thức injection có thể không được gọi.

Có thể kết hợp annotation nullable trên setter parameter trong các trường hợp phù hợp, nhưng cần chọn một cách thể hiện nhất quán.

### 6.1. Vì sao constructor injection thường vẫn tốt hơn?

Setter injection làm dependency có thể được gắn sau khi object đã được tạo. Điều này có thể tạo trạng thái tạm thời thiếu dependency, và field thường không thể `final`.

Constructor injection biểu diễn dependency ngay khi tạo object:

```java
@Service
public class ReportService {

    private final Optional<MetricsRecorder> metricsRecorder;

    public ReportService(Optional<MetricsRecorder> metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }
}
```

Với dependency thực sự tùy chọn và cần dùng xuyên suốt vòng đời service, cách này thường dễ đọc, dễ test và tránh trạng thái object chưa được cấu hình đầy đủ.

### 6.2. `@Autowired(required = false)` trên constructor cần thận trọng

Constructor quyết định object có được tạo hay không, nên làm cả constructor optional có thể khiến Spring phải chọn constructor khác hoặc đường tạo instance khác. Khi cần biểu diễn một dependency không bắt buộc, **đặt `Optional<T>` hoặc `@Nullable` trên tham số của constructor bắt buộc** thường rõ ràng hơn.

Dùng `required = false` chủ yếu trong các trường hợp method/field injection có chủ đích hoặc code legacy, không phải cách mặc định cho constructor injection mới.

## 7. Dependency optional và fallback behavior

Chỉ nhận diện bean vắng mặt là chưa đủ. Consumer cần có **hành vi xác định** cho trường hợp không có bean.

Giả sử hệ thống có `MetricsRecorder`:

```java
public interface MetricsRecorder {
    void recordOrderPlaced();
}
```

Nếu metrics chỉ là tiện ích quan sát, có thể bỏ qua khi không được cài:

```java
@Service
public class OrderMetricsService {

    private final Optional<MetricsRecorder> recorder;

    public OrderMetricsService(Optional<MetricsRecorder> recorder) {
        this.recorder = recorder;
    }

    public void recordPlaced() {
        recorder.ifPresent(MetricsRecorder::recordOrderPlaced);
    }
}
```

Nhưng nếu muốn các consumer không cần biết metrics có được bật hay không, có thể dùng **Null Object pattern**: luôn cung cấp một implementation làm no-op.

Ví dụ:

```java
@Component
@ConditionalOnProperty(
        prefix = "features.metrics",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true
)
public class NoOpMetricsRecorder implements MetricsRecorder {

    @Override
    public void recordOrderPlaced() {
        // Cố ý không thực hiện thao tác.
    }
}
```

Implementation thật có thể được đăng ký khi property bật:

```java
@Component
@ConditionalOnProperty(
        prefix = "features.metrics",
        name = "enabled",
        havingValue = "true"
)
public class PrometheusMetricsRecorder implements MetricsRecorder {

    @Override
    public void recordOrderPlaced() {
        // Ghi metric theo tích hợp thực tế.
    }
}
```

Với cấu hình này, consumer có thể inject `MetricsRecorder` **bắt buộc**, vì luôn có một implementation phù hợp nếu điều kiện và component scan được thiết lập như dự kiến. Cần bảo đảm hai điều kiện không tạo ra hai bean cùng lúc và thư viện metrics thật đã có khi bật tính năng.

### 7.1. Optional bean hay Null Object?

| Cách | Consumer phải làm gì? | Phù hợp khi |
| --- | --- | --- |
| `Optional<T>` | Kiểm tra bean có tồn tại trước khi gọi | Consumer cần phản ứng khác nhau khi tích hợp không được cấu hình |
| `@Nullable T` | Kiểm tra null | Codebase dùng nullability annotation và giá trị null là hợp đồng rõ ràng |
| No-op implementation | Luôn gọi interface như bình thường | Thiếu tích hợp có cùng ý nghĩa “không làm gì” với consumer |
| `ObjectProvider<T>` | Tra cứu khi cần | Bean có thể được tạo trễ, theo scope hoặc có nhiều ứng viên |

No-op không phải lúc nào cũng đúng. Nếu thiếu implementation cần phát cảnh báo, trả lỗi hoặc từ chối thao tác, no-op có thể che giấu vấn đề. Chọn fallback dựa trên ý nghĩa nghiệp vụ.

### 7.2. Optional dependency không đồng nghĩa optional feature flag

Hai cơ chế có thể phối hợp nhưng khác nhau:

- `@ConditionalOnProperty` quyết định **có đăng ký bean hay không** theo property.
- `Optional<T>` hoặc `@Nullable` quyết định **consumer tiếp nhận sự vắng mặt của bean như thế nào**.

Ví dụ `features.metrics.enabled=false` có thể khiến metrics bean không được đăng ký; `Optional<MetricsRecorder>` cho phép service vẫn được tạo khi bean không có. Nếu dùng No-op implementation, consumer không cần optional injection vì một bean thay thế luôn tồn tại.

## 8. Optional bean khác optional configuration property

Không nên nhầm dependency tùy chọn với property tùy chọn.

Ví dụ một property:

```yaml
partner:
  endpoint: https://partner.example
```

Nếu property có thể không tồn tại, ta có thể dùng:

```java
@Value("DOLLAR{partner.endpoint:}")
private String endpoint;
```

hoặc dùng `@ConfigurationProperties` với giá trị/default và validation phù hợp. Nhưng việc property vắng mặt **không tự nói lên** rằng một bean `PartnerClient` có hay không.

Ví dụ factory method:

```java
@Bean
@ConditionalOnProperty(prefix = "partner", name = "endpoint")
PartnerClient partnerClient(PartnerProperties properties) {
    return new PartnerClient(properties.endpoint());
}
```

Ở đây property quyết định bean có được tạo; một consumer inject `Optional<PartnerClient>` có thể xử lý khi bean không có. Hai tầng phối hợp với nhau nhưng giải quyết hai câu hỏi riêng.

### 8.1. Đừng dùng empty string thay cho optional mà không định nghĩa ý nghĩa

`partner.endpoint: ""` vẫn là một giá trị chuỗi có mặt. Nếu dùng empty string làm dấu hiệu “tắt”, hãy quy định rõ và kiểm tra nó. Thường property boolean `partner.enabled` hoặc conditional property rõ ràng dễ hiểu hơn.

### 8.2. Validate cấu hình khi tính năng được bật

Nếu `partner.enabled=true` thì endpoint, timeout và credential cần hợp lệ. Có thể dùng `@ConfigurationProperties` kết hợp validation để ứng dụng fail fast khi tính năng đã bật nhưng cấu hình thiếu. Khi tính năng tắt, bean client không được tạo và consumer xử lý theo fallback đã chọn.

Đừng để optional injection che đi cấu hình sai của một tính năng mà người vận hành đã chủ động bật.

## 9. Bean có nhiều candidate: optional không thay cho qualifier

Giả sử có hai implementation:

```java
@Component("emailNotificationSender")
class EmailNotificationSender implements NotificationSender {
    // ...
}

@Component("smsNotificationSender")
class SmsNotificationSender implements NotificationSender {
    // ...
}
```

Inject:

```java
public NotificationService(Optional<NotificationSender> sender) {
    this.sender = sender;
}
```

vẫn có thể bị mơ hồ vì Spring phải quyết định candidate nào đại diện cho `NotificationSender`. Có ba hướng:

1. Dùng `@Qualifier` để chọn đúng implementation.
2. Dùng `@Primary` nếu có một implementation mặc định.
3. Inject `List<NotificationSender>`/`Map<String, NotificationSender>` nếu muốn dùng tất cả.

Ví dụ qualifier:

```java
public NotificationService(
        @Qualifier("emailNotificationSender")
        Optional<NotificationSender> sender) {
    this.sender = sender;
}
```

Trong ví dụ này, dependency chỉ optional nếu bean mang qualifier đó có thể vắng mặt; nếu có nhiều bean cùng qualifier hoặc cấu hình không đúng, cần điều tra resolution thực tế.

**Optional xử lý zero candidate; qualifier/primary xử lý việc chọn candidate.** Đây là hai chiều khác nhau của quá trình autowiring.

## 10. Optional injection và vòng đời bean

Một số khác biệt về thời điểm tra cứu có thể ảnh hưởng đến ứng dụng.

### 10.1. `Optional<T>` được giải quyết khi tạo consumer

Ví dụ:

```java
@Service
class NotificationFacade {

    private final Optional<NotificationSender> sender;

    NotificationFacade(Optional<NotificationSender> sender) {
        this.sender = sender;
    }
}
```

Spring giải quyết Optional khi tạo `NotificationFacade`. Consumer giữ kết quả đã inject. Nếu context không có sender lúc đó, Optional vẫn rỗng trong suốt vòng đời instance này.

Đây là lựa chọn phù hợp khi tập bean ổn định sau startup.

### 10.2. `ObjectProvider<T>` cho phép tra cứu lúc gọi

```java
@Service
class NotificationFacade {

    private final ObjectProvider<NotificationSender> senderProvider;

    NotificationFacade(ObjectProvider<NotificationSender> senderProvider) {
        this.senderProvider = senderProvider;
    }

    void notify(Notification event) {
        senderProvider.ifAvailable(sender -> sender.send(event));
    }
}
```

Provider được inject ngay, còn bean được tra cứu khi `ifAvailable` được gọi. Điều này hữu ích với một số scope và khi muốn trì hoãn việc lấy bean. Tuy nhiên, Spring singleton bean graph thường không tự thay đổi tùy tiện khi ứng dụng đang chạy; provider không phải cơ chế hot-plug plugin tự động.

### 10.3. Bean prototype và lookup nhiều lần

Nếu bean có prototype scope, inject trực tiếp prototype vào singleton constructor thường chỉ lấy một instance tại thời điểm tạo singleton. Khi muốn lấy instance mới theo mỗi thao tác, `ObjectProvider<T>` hoặc factory abstraction có thể phù hợp hơn.

Không dùng `Optional<T>` như một factory tạo instance mới. Optional chỉ bao bọc một giá trị đã được resolve.

## 11. Testing cho dependency tùy chọn

Optional dependency nên được test ở cả hai trạng thái: **có bean** và **không có bean**.

### 11.1. Unit test với `Optional.empty()`

Với `OrderService` có constructor nhận Optional:

```java
class OrderServiceTest {

    @Test
    void placesOrderWhenAuditIsAbsent() {
        OrderService service = new OrderService(Optional.empty());

        Order order = new Order("O-100");

        service.placeOrder(order);

        // Assert kết quả nghiệp vụ chính vẫn đúng.
    }
}
```

`Order` và phần lưu đơn trong ví dụ cần được triển khai theo ứng dụng. Mục đích là chứng minh có thể test consumer mà không cần tạo Spring context hoặc đăng ký bean audit.

### 11.2. Unit test với bean hiện diện

```java
@Test
void publishesAuditWhenSinkIsPresent() {
    AuditSink sink = mock(AuditSink.class);
    OrderService service = new OrderService(Optional.of(sink));

    Order order = new Order("O-101");
    service.placeOrder(order);

    verify(sink).publish(new OrderPlacedEvent(order.id()));
}
```

Ví dụ dùng Mockito và cần import/static setup tương ứng. Nó kiểm tra hành vi khi dependency có mặt.

### 11.3. Test `@Nullable`

```java
@Test
void serviceWorksWithoutOptionalSender() {
    OrderNotificationService service =
            new OrderNotificationService(null);

    assertDoesNotThrow(() -> service.notifyOrder(new Order("O-102")));
}
```

Vì `@Nullable` chỉ là annotation hợp đồng, khi gọi constructor trực tiếp trong unit test, chính test phải truyền `null` để mô phỏng trường hợp bean không tồn tại. Không có Spring container nào tự động thay tham số khi test gọi `new`.

### 11.4. Test wiring thật với Spring context

Khi muốn xác nhận Spring thật sự inject `Optional.empty()` hoặc nullable parameter, có thể dùng `@SpringBootTest`, `@ContextConfiguration` hoặc `@SpringJUnitConfig` với cấu hình test tối giản.

Một lớp test có thể định nghĩa `@TestConfiguration` chỉ cung cấp một số bean, sau đó xác nhận consumer được tạo khi bean optional bị thiếu. Đối với cấu hình nhiều profile/conditional, integration test context hữu ích hơn unit test thuần.

Tránh khởi động cả ứng dụng và database thật nếu mục tiêu chỉ là xác nhận constructor nhận Optional; giữ test nhỏ để dễ xác định lỗi.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` dù dependency được xem là optional | Tham số vẫn khai báo kiểu bắt buộc, annotation nullable không được nhận diện, hoặc cấu hình chưa đúng | Dùng `Optional<T>`, `@Nullable` được hỗ trợ hoặc provider; kiểm tra import/version |
| `NoUniqueBeanDefinitionException` với `Optional<T>` | Có nhiều bean cùng kiểu và không có candidate duy nhất | Dùng `@Qualifier`/`@Primary` hoặc collection |
| `NullPointerException` | Dùng nullable dependency mà không kiểm tra null | Kiểm tra null hoặc chuyển sang Optional |
| `NoSuchElementException` | Gọi `Optional.get()` khi Optional rỗng | Dùng `ifPresent`, `orElse` hoặc `orElseThrow` với lỗi có ý nghĩa |
| Tính năng bị bỏ qua dù đã bật | Bean không được đăng ký do profile/conditional/property hoặc package scan | Kiểm tra property, active profile, condition report và component scan |
| Bean được inject nhưng khởi tạo lỗi | Factory method hoặc dependency của bean ném exception | Đọc root cause; optional không che lỗi tạo bean khi bean đã được chọn |
| Provider lookup vẫn báo lỗi | Nhiều candidate hoặc bean khởi tạo thất bại | Dùng qualifier/primary, kiểm tra candidate và lỗi startup |
| Setter optional không được gọi | `@Autowired(required=false)` và dependency không tồn tại | Đây là hành vi dự kiến; xử lý trạng thái không được inject |
| Dùng Optional nhưng consumer luôn yêu cầu bean | Thiết kế optional không phù hợp với hành vi thật | Khai báo dependency bắt buộc hoặc fail fast rõ ràng |
| Test trực tiếp constructor không có Spring nhưng mong tự inject | Unit test tự gọi `new`, container không tham gia | Truyền `Optional.empty()` hoặc `null` có chủ đích |

### 12.1. Phân biệt bean không có với bean tạo thất bại

Optional injection thường xử lý trường hợp **không tìm thấy candidate phù hợp**. Nó không phải cơ chế nuốt mọi exception trong lúc tạo bean.

Ví dụ một bean `AuditSink` tồn tại nhưng factory method ném exception do thiếu credential hoặc không kết nối được dịch vụ ngoài. Spring vẫn có thể thất bại khi tạo bean/context. Đừng kỳ vọng `Optional<AuditSink>` sẽ tự biến lỗi cấu hình hoặc lỗi kết nối thành `Optional.empty()`.

Đây là phân biệt quan trọng:

- Không có bean: optional resolution có thể trả empty/null theo kiểu khai báo.
- Có bean nhưng khởi tạo thất bại: lỗi tạo bean có thể làm context thất bại.
- Có bean nhưng thao tác runtime thất bại: consumer cần xử lý lỗi nghiệp vụ/network riêng.

### 12.2. Kiểm tra condition và cấu hình đăng ký bean

Nếu bean tùy chọn không xuất hiện, xem:

- Class chứa `@Bean` có được import/scan không?
- Bean có `@Profile` hoặc `@ConditionalOnProperty` không?
- Property và profile thực tế có đúng không?
- Dependency cần thiết có trên classpath không?
- Auto-configuration có back off vì bean khác không?
- Có lỗi khởi tạo bean nào trước đó không?

Với auto-configuration, chạy ứng dụng cùng `--debug` để xem Condition Evaluation Report khi cần.

## 13. Quy tắc thiết kế: đừng biến mọi dependency thành optional

Optional injection có ích, nhưng dùng quá nhiều sẽ khiến service có nhiều nhánh xử lý và trạng thái khó dự đoán.

Một số nguyên tắc:

1. **Mặc định giữ dependency bắt buộc.** Nếu class không thể làm đúng công việc khi thiếu dependency, khai báo trực tiếp trong constructor.
2. **Chỉ optional khi có hành vi fallback hợp lệ.** Ghi rõ điều gì xảy ra khi bean vắng mặt.
3. **Ưu tiên kiểu dữ liệu thể hiện ý định.** `Optional<T>` thường dễ đọc hơn null nếu consumer phải xử lý hai trạng thái.
4. **Dùng qualifier cho lựa chọn bean.** Optional không thay thế cơ chế giải quyết nhiều candidate.
5. **Cân nhắc No-op implementation.** Khi việc “không làm gì” là hành vi mặc định hợp lệ, Null Object có thể giảm nhánh trong consumer.
6. **Dùng provider khi cần lookup trễ.** Đừng biến provider thành service locator tổng quát để mọi class tự tìm bean.
7. **Không che lỗi khởi tạo.** Optional không phải cơ chế catch exception hoặc bỏ qua dependency hỏng.
8. **Giữ cấu hình rõ ràng.** Nếu tính năng bật thì bean và property bắt buộc phải hợp lệ; nếu tắt thì fallback cần có ý nghĩa.
9. **Test cả hai trạng thái.** Một bài test chỉ có bean hiện diện không chứng minh consumer xử lý đúng khi bean bị thiếu.
10. **Theo quy ước nullability của dự án.** Chọn đúng annotation tương thích với Spring/Java version và công cụ static analysis.

## 14. Bài thực hành: tích hợp audit có thể bật hoặc tắt

Bài thực hành giả định một dịch vụ đơn hàng có thể ghi audit event. Audit là tính năng phụ trong môi trường demo, nhưng có thể được bật ở môi trường cần quan sát.

### Bước 1 — Tạo interface

```java
package com.example.orders;

public interface AuditSink {
    void publish(String event);
}
```

### Bước 2 — Tạo implementation tùy điều kiện

Ví dụ một implementation ghi log khi property bật:

```java
package com.example.orders;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "features.audit",
        name = "enabled",
        havingValue = "true"
)
public class LoggingAuditSink implements AuditSink {

    @Override
    public void publish(String event) {
        System.out.println("AUDIT: " + event);
    }
}
```

Đây là implementation minh họa; ứng dụng thực tế có thể ghi vào hệ thống audit chuyên dụng.

### Bước 3 — Inject Optional vào service

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final Optional<AuditSink> auditSink;

    public OrderService(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    public void placeOrder(String orderId) {
        // Thực hiện nghiệp vụ đặt hàng.

        auditSink.ifPresent(sink ->
                sink.publish("Order placed: " + orderId));
    }
}
```

### Bước 4 — Bật/tắt property

Mặc định có thể để audit tắt:

```yaml
features:
  audit:
    enabled: false
```

Khi bật:

```yaml
features:
  audit:
    enabled: true
```

Trong thực tế, có thể đặt property ở profile hoặc nguồn cấu hình bên ngoài. Khi tắt, không có `AuditSink` và Optional rỗng. Khi bật, Spring đăng ký `LoggingAuditSink` và Optional chứa bean.

### Bước 5 — Viết unit test cho hai trường hợp

- Khởi tạo service với `Optional.empty()` và xác nhận nghiệp vụ chính vẫn chạy.
- Khởi tạo service với mock `AuditSink` và xác nhận `publish` được gọi.
- Nếu muốn xác nhận `@ConditionalOnProperty`, viết context test cho hai giá trị property và kiểm tra bean có/không.

### Câu hỏi tự kiểm tra

1. Dependency bắt buộc và optional khác nhau thế nào khi bean không tồn tại?
2. Spring inject gì cho `Optional<AuditSink>` khi không có bean?
3. `@Nullable` khác Optional ở cách biểu diễn trạng thái thiếu như thế nào?
4. Vì sao Optional không tự giải quyết trường hợp có hai bean cùng kiểu?
5. Khi nào nên dùng `ObjectProvider<T>` thay cho Optional?
6. `@Autowired(required=false)` trên setter có ý nghĩa gì?
7. Optional injection có nuốt exception nếu bean tồn tại nhưng khởi tạo thất bại không?
8. Khi nào Null Object tốt hơn việc kiểm tra Optional trong mỗi consumer?
9. Optional dependency có phải optional property không?
10. Nếu tính năng đã được bật nhưng bean không được đăng ký, nên kiểm tra những gì?

## 15. Bảng chọn nhanh

| Nhu cầu | Cách phù hợp để cân nhắc |
| --- | --- |
| Bean phải tồn tại để service hoạt động | Constructor injection bắt buộc `T` |
| Bean có thể không có, consumer muốn thể hiện rõ bằng Java type | Constructor `Optional<T>` |
| Codebase dùng nullability annotation và chấp nhận giá trị null | Constructor parameter `@Nullable T` |
| Cần tra cứu bean trễ hoặc nhiều lần | `ObjectProvider<T>` |
| Cần tất cả implementation | `List<T>`, `Map<String, T>` hoặc provider stream |
| Tích hợp phụ có thể tắt, không làm gì là hợp lệ | No-op implementation hoặc Optional tùy thiết kế |
| Chỉ một bean được bật theo môi trường | `@Profile` hoặc `@ConditionalOnProperty`, kết hợp injection phù hợp |
| Có nhiều bean cùng kiểu | `@Qualifier` hoặc `@Primary` |
| Dependency thiếu là lỗi cấu hình nghiêm trọng | Giữ injection bắt buộc và fail fast |

Dependency injection optional giúp ứng dụng linh hoạt khi tích hợp không luôn hiện diện. Nhưng sự linh hoạt chỉ có ích khi hành vi lúc thiếu dependency được thiết kế rõ. Dùng `Optional<T>` để biểu diễn hai trạng thái một cách tường minh, `@Nullable` khi nullability là hợp đồng đã thống nhất, và `ObjectProvider<T>` khi thật sự cần tra cứu trễ. Với những dependency cốt lõi, hãy giữ chúng bắt buộc để Spring phát hiện cấu hình sai ngay từ đầu.
