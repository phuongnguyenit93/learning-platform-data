# @Fallback trong các phiên bản Spring Framework hỗ trợ

Trong một ứng dụng Spring Boot, nhiều bean có thể cùng triển khai một interface. Ví dụ, ứng dụng cần một `MetricsPublisher` để ghi nhận số liệu. Khi chạy độc lập hoặc trong môi trường phát triển, một implementation đơn giản có thể không làm gì; khi triển khai thật, ứng dụng có thể cung cấp implementation ghi số liệu vào hệ thống quan sát.

Nếu cả hai bean cùng được đăng ký, một constructor chỉ yêu cầu `MetricsPublisher` có thể gặp nhiều candidate. Spring cung cấp một số cơ chế lựa chọn như `@Primary` và `@Qualifier`. Từ **Spring Framework 6.2**, có thêm annotation `@Fallback` để đánh dấu bean là lựa chọn dự phòng: khi có một bean thông thường phù hợp và các bean còn lại được đánh dấu fallback, Spring ưu tiên bean thông thường cho injection một giá trị.

`@Fallback` hữu ích khi một thư viện hoặc cấu hình muốn cung cấp implementation mặc định, đồng thời cho phép ứng dụng đăng ký implementation riêng mà không cần đánh dấu bean của ứng dụng bằng `@Primary`.

Bài học giải thích phiên bản hỗ trợ, cách sử dụng trên class và phương thức `@Bean`, quan hệ với `@Primary` và `@Qualifier`, hành vi với collection, cũng như khác biệt giữa `@Fallback` và `@ConditionalOnMissingBean`.

## 1. Bài toán: nhiều bean cùng đáp ứng một kiểu

Giả sử ứng dụng có contract:

~~~java
package com.example.metrics;

public interface MetricsPublisher {
    void publish(String name, long value);
}
~~~

Một implementation dự phòng có thể không gửi số liệu đi đâu:

~~~java
package com.example.metrics;

public class NoOpMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        // Cố ý không thực hiện thao tác bên ngoài.
    }
}
~~~

Một implementation khác ghi số liệu ra log:

~~~java
package com.example.metrics;

public class LoggingMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        System.out.println("[METRIC] " + name + "=" + value);
    }
}
~~~

Service chỉ cần contract:

~~~java
package com.example.metrics;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final MetricsPublisher metricsPublisher;

    public CheckoutService(MetricsPublisher metricsPublisher) {
        this.metricsPublisher = metricsPublisher;
    }

    public void checkout() {
        // Xử lý nghiệp vụ checkout...
        metricsPublisher.publish("checkout.completed", 1);
    }
}
~~~

Nếu cả `NoOpMetricsPublisher` và `LoggingMetricsPublisher` đều là bean, Spring nhìn thấy hai ứng viên có kiểu `MetricsPublisher`. Với injection một giá trị, container cần biết bean nào nên được đưa vào constructor.

Một cách cũ là đánh dấu một bean là `@Primary`. Nhưng nếu implementation NoOp chỉ là lựa chọn mặc định khi ứng dụng chưa cung cấp implementation thật, ta có thể đánh dấu NoOp là `@Fallback`. Khi đó bean ứng dụng thông thường sẽ được ưu tiên.

## 2. @Fallback là gì?

`@Fallback` là annotation của Spring Framework, nằm trong package:

~~~java
import org.springframework.context.annotation.Fallback;
~~~

Nó đánh dấu một bean là **fallback autowire candidate** — ứng viên dự phòng khi Spring giải quyết dependency theo kiểu.

Annotation này:

- Có từ **Spring Framework 6.2**.
- Có thể đặt trên class bean hoặc method được đánh dấu `@Bean`.
- Có runtime retention và được Spring đọc trong quá trình xử lý bean.
- Là một cơ chế bổ sung và thay thế cách dùng `@Primary` trong những tình huống muốn đánh dấu các bean dự phòng.
- Chỉ ảnh hưởng việc chọn bean cho injection một giá trị khi có nhiều candidate cùng kiểu.
- Không loại bỏ bean khỏi container.

Javadoc chính thức mô tả quy tắc: nếu trong nhiều candidate phù hợp, tất cả trừ một bean được đánh dấu fallback, bean còn lại sẽ được chọn. Các bean phù hợp kiểu vẫn được đưa vào khi inject array, collection, map hoặc stream từ `ObjectProvider`.

Điểm cần nhớ: **fallback là metadata về độ ưu tiên khi chọn bean**, không phải cơ chế tự tạo bean bị thiếu, không phải xử lý lỗi runtime và cũng không phải circuit breaker.

## 3. Phiên bản nào hỗ trợ @Fallback?

`@Fallback` được giới thiệu trong Spring Framework 6.2. Do đó, cần kiểm tra phiên bản Spring Framework thực tế mà ứng dụng sử dụng, không chỉ nhìn phiên bản Java.

| Dòng Spring | Phiên bản Framework nền | Có `@Fallback`? |
| --- | --- | --- |
| Spring Framework 6.0 / 6.1 | Trước 6.2 | Không |
| Spring Framework 6.2.x | 6.2 trở lên | Có |
| Spring Framework 7.x | 7.x | Có |

Với Spring Boot, quan hệ phiên bản thông dụng:

| Dòng Spring Boot | Spring Framework nền | Có thể dùng `@Fallback`? |
| --- | --- | --- |
| Spring Boot 3.3.x | 6.1.x | Không |
| Spring Boot 3.4.x | 6.2.x | Có |
| Spring Boot 3.5.x | 6.2.x | Có |
| Spring Boot 4.x | 7.x | Có |

Bảng này mô tả các dòng phát hành tương ứng; bản vá cụ thể và yêu cầu tương thích phải được kiểm tra theo tài liệu của bản Boot đang dùng.

### 3.1. Vì sao cần chú ý phiên bản?

Nếu dự án đang dùng Spring Boot 3.3.x, import:

~~~java
import org.springframework.context.annotation.Fallback;
~~~

có thể khiến compiler báo không tìm thấy class, vì Spring Framework 6.1.x chưa cung cấp annotation này.

Không nên giải quyết bằng cách thêm riêng một JAR `spring-context` 6.2 vào ứng dụng Boot 3.3 đang quản lý Spring Framework 6.1. Các module Spring Framework cần được nâng đồng bộ theo tổ hợp được Boot hỗ trợ. Nếu muốn sử dụng `@Fallback`, hãy cân nhắc nâng Spring Boot lên dòng tương thích, chẳng hạn 3.4 trở lên trong hệ Boot 3.x, rồi kiểm tra yêu cầu JDK, Gradle/Maven và các dependency khác.

Nếu ứng dụng dùng Spring Framework độc lập, cần có `spring-context` 6.2 trở lên và các module Spring liên quan tương thích cùng dòng.

### 3.2. Kiểm tra version Framework đang chạy

Trong Maven, có thể xem dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-context
~~~

Trong Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
~~~

Đây là cách xác nhận phiên bản đã resolve thay vì đoán từ một dòng cấu hình. Với ứng dụng Boot, nên để BOM của Boot quản lý các module Spring Framework, trừ khi có lý do nâng cấp được kiểm chứng rõ ràng.

## 4. Dùng @Fallback trên class component

Có thể đánh dấu trực tiếp implementation:

~~~java
package com.example.metrics;

import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Fallback;

@Component
@Fallback
public class NoOpMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        // Không gửi số liệu.
    }
}
~~~

Một implementation thông thường khác:

~~~java
package com.example.metrics;

import org.springframework.stereotype.Component;

@Component
public class LoggingMetricsPublisher implements MetricsPublisher {
    @Override
    public void publish(String name, long value) {
        System.out.println("[METRIC] " + name + "=" + value);
    }
}
~~~

Khi cả hai bean được đăng ký, constructor:

~~~java
public CheckoutService(MetricsPublisher metricsPublisher) {
    this.metricsPublisher = metricsPublisher;
}
~~~

sẽ nhận `LoggingMetricsPublisher` vì đó là candidate thông thường duy nhất; `NoOpMetricsPublisher` được đánh dấu fallback.

Luồng lựa chọn:

~~~text
Dependency cần: MetricsPublisher
             │
             ▼
Tìm các bean phù hợp kiểu
             │
       ┌─────┴─────┐
       ▼           ▼
NoOpMetrics     LoggingMetrics
 @Fallback       regular bean
       │           │
       └─────┬─────┘
             ▼
    Chọn regular bean
             │
             ▼
      CheckoutService
~~~

Nếu bỏ bean `LoggingMetricsPublisher` khỏi context, `NoOpMetricsPublisher` là candidate duy nhất và vẫn có thể được inject. Đây là ý nghĩa của implementation dự phòng.

## 5. Dùng @Fallback trên phương thức @Bean

Không nhất thiết phải đánh dấu class bằng `@Component`. Khi tự tạo object qua factory method, có thể đặt `@Fallback` trên method `@Bean`.

~~~java
package com.example.metrics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;

@Configuration
public class DefaultMetricsConfiguration {

    @Bean
    @Fallback
    public MetricsPublisher defaultMetricsPublisher() {
        return new NoOpMetricsPublisher();
    }
}
~~~

Ứng dụng có thể cung cấp bean thông thường riêng:

~~~java
package com.example.metrics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApplicationMetricsConfiguration {

    @Bean
    public MetricsPublisher applicationMetricsPublisher() {
        return new LoggingMetricsPublisher();
    }
}
~~~

Với hai bean trên, một service inject `MetricsPublisher` sẽ nhận bean ứng dụng thông thường. Bean mặc định vẫn được đăng ký và container vẫn quản lý nó, nhưng nó được đánh dấu là lựa chọn dự phòng.

Cách này phù hợp khi viết thư viện hoặc module cấu hình muốn cung cấp một implementation mặc định mà ứng dụng sử dụng có thể thay thế bằng bean riêng.

### 5.1. Kiểu trả về của @Bean vẫn quan trọng

Nên khai báo kiểu trả về phản ánh contract:

~~~java
@Bean
@Fallback
public MetricsPublisher defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Nếu khai báo quá chung:

~~~java
@Bean
@Fallback
public Object defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Spring có thể thiếu thông tin kiểu để dự đoán bean là một `MetricsPublisher` khi xử lý dependency trước khi gọi factory method. Hãy công bố kiểu interface hoặc kiểu cụ thể phù hợp với nhu cầu autowiring.

Nếu consumer chỉ cần contract, `MetricsPublisher` là kiểu trả về phù hợp. Object runtime vẫn là `NoOpMetricsPublisher`.

## 6. @Fallback hoạt động khi nào?

`@Fallback` có tác dụng trong việc chọn bean cho **single-valued dependency** — một injection point chỉ cần một object.

Ví dụ:

~~~java
@Service
public class CheckoutService {
    private final MetricsPublisher publisher;

    public CheckoutService(MetricsPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

Nếu có nhiều bean phù hợp và chỉ còn một candidate thông thường sau khi loại các lựa chọn fallback khỏi vị trí ưu tiên, Spring chọn candidate thông thường đó.

Các trường hợp cơ bản:

| Candidate phù hợp | Kết quả mong đợi |
| --- | --- |
| Chỉ có một bean thông thường | Bean thông thường được inject |
| Một bean thông thường và một hoặc nhiều bean fallback | Bean thông thường được ưu tiên |
| Chỉ có một bean fallback | Bean fallback vẫn được inject |
| Nhiều bean thông thường cùng phù hợp | `@Fallback` không giải quyết sự nhập nhằng giữa các bean thông thường |
| Nhiều bean fallback cùng phù hợp mà không có quy tắc lựa chọn khác | Cần chỉ định rõ hơn, ví dụ bằng `@Qualifier` |
| Không có bean phù hợp | Vẫn thiếu dependency; `@Fallback` không tự tạo bean |

Khi còn nhiều candidate chưa được phân giải, hãy dùng qualifier hoặc một quy tắc lựa chọn thích hợp thay vì dựa vào thứ tự đăng ký.

## 7. @Fallback không loại bean khỏi collection

Một điểm rất quan trọng là `@Fallback` chỉ tác động lựa chọn cho injection một giá trị. Khi inject collection hoặc map, tất cả bean phù hợp kiểu vẫn được đưa vào.

Ví dụ:

~~~java
@Service
public class MetricsCoordinator {
    private final List<MetricsPublisher> publishers;

    public MetricsCoordinator(List<MetricsPublisher> publishers) {
        this.publishers = publishers;
    }

    public void publishAll(String name, long value) {
        for (MetricsPublisher publisher : publishers) {
            publisher.publish(name, value);
        }
    }
}
~~~

Nếu context có `NoOpMetricsPublisher` được đánh dấu fallback và `LoggingMetricsPublisher` thông thường, danh sách vẫn có cả hai bean.

Tương tự, quy tắc này áp dụng cho:

- Array, ví dụ `MetricsPublisher[]`.
- `List<MetricsPublisher>` hoặc `Set<MetricsPublisher>`.
- `Map<String, MetricsPublisher>`.
- Stream candidate từ `ObjectProvider<MetricsPublisher>`.

Vì vậy, không nên hiểu `@Fallback` là “bean này bị ẩn khỏi mọi nơi”. Nó vẫn là bean được đăng ký và có thể được truy cập theo tên hoặc xuất hiện trong các cấu trúc tập hợp.

Nếu nghiệp vụ muốn chỉ chạy implementation thông thường, hãy thiết kế collection filtering hoặc qualifier phù hợp; đừng trông đợi `@Fallback` tự loại bean khỏi collection.

## 8. So sánh @Fallback, @Primary và @Qualifier

Ba annotation giải quyết các khía cạnh khác nhau của việc chọn bean.

### 8.1. @Primary: chỉ định lựa chọn ưu tiên

`@Primary` đánh dấu một bean được ưu tiên khi có nhiều candidate cho injection một giá trị.

~~~java
@Bean
@Primary
public MetricsPublisher loggingMetricsPublisher() {
    return new LoggingMetricsPublisher();
}

@Bean
public MetricsPublisher noOpMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Nếu có đúng một bean primary phù hợp, Spring chọn bean đó.

Dùng `@Primary` khi bạn muốn nói: **“Trong các lựa chọn hợp lệ, đây là bean mặc định nên được ưu tiên.”**

### 8.2. @Fallback: đánh dấu lựa chọn dự phòng

~~~java
@Bean
public MetricsPublisher loggingMetricsPublisher() {
    return new LoggingMetricsPublisher();
}

@Bean
@Fallback
public MetricsPublisher noOpMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Dùng `@Fallback` khi muốn nói: **“Bean này có thể đáp ứng contract, nhưng hãy ưu tiên implementation thông thường nếu có.”**

Khác biệt về ý định:

| Annotation | Ý nghĩa |
| --- | --- |
| `@Primary` | Đánh dấu bean nên được ưu tiên |
| `@Fallback` | Đánh dấu bean có mức ưu tiên dự phòng |
| Không đánh dấu | Candidate thông thường |
| `@Qualifier` | Thu hẹp candidate theo một đặc tính hoặc qualifier cụ thể |

`@Primary` và `@Fallback` đều chỉ có ý nghĩa khi Spring đang giải quyết một injection point cần một giá trị. Nếu có nhiều bean primary hoặc nhiều candidate thông thường không thể phân giải, cần xem các quy tắc lựa chọn khác.

### 8.3. @Qualifier: chọn theo yêu cầu cụ thể của consumer

Nếu một service cần chính xác bean có qualifier `remote`:

~~~java
@Bean
@Qualifier("local")
public MetricsPublisher localPublisher() {
    return new NoOpMetricsPublisher();
}

@Bean
@Qualifier("remote")
public MetricsPublisher remotePublisher() {
    return new LoggingMetricsPublisher();
}
~~~

Constructor:

~~~java
public CheckoutService(
        @Qualifier("remote") MetricsPublisher publisher) {
    this.publisher = publisher;
}
~~~

`@Qualifier` lọc các candidate theo qualifier. Đây là lựa chọn phù hợp khi consumer có yêu cầu cụ thể, chẳng hạn cần local, remote, persistent hoặc một nhóm chức năng nhất định.

Đừng dùng `@Fallback` để thay thế `@Qualifier` khi service thực sự cần một implementation cụ thể.

### 8.4. Có thể kết hợp các cơ chế không?

Có thể dùng qualifier cùng metadata ưu tiên khi cần, nhưng nên tránh tạo một cấu hình khó hiểu với nhiều quy tắc chồng chéo.

Một cách thiết kế dễ đọc:

- `@Fallback` cho implementation mặc định của thư viện.
- Bean thông thường cho implementation do ứng dụng cung cấp.
- `@Qualifier` khi từng consumer phải chọn một loại rõ ràng.
- `@Primary` khi ứng dụng có một lựa chọn mặc định ưu tiên giữa nhiều bean thông thường.

`@Order` hoặc `Ordered` thường được dùng để sắp xếp thứ tự trong collection hoặc một số cơ chế có thứ tự; không nên nhầm nó với `@Fallback` khi chọn một bean duy nhất.

## 9. @Fallback khác @ConditionalOnMissingBean như thế nào?

Đây là hai cơ chế thường được nhắc đến khi viết Spring Boot starter hoặc auto-configuration, nhưng chúng không tương đương.

### 9.1. @ConditionalOnMissingBean quyết định có đăng ký bean hay không

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean(MetricsPublisher.class)
public MetricsPublisher defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Nếu đã có bean phù hợp được đăng ký và điều kiện được đánh giá trong ngữ cảnh tương ứng, factory method mặc định có thể không được đăng ký thành bean definition.

Nói cách khác, condition quyết định **có tạo định nghĩa bean này trong context hay không**.

### 9.2. @Fallback đánh dấu bean vẫn được đăng ký nhưng có vai trò dự phòng

~~~java
@Bean
@Fallback
public MetricsPublisher defaultMetricsPublisher() {
    return new NoOpMetricsPublisher();
}
~~~

Trong trường hợp này, bean mặc định vẫn được đăng ký. Nếu ứng dụng có một bean thông thường cùng kiểu, bean thông thường được ưu tiên cho injection một giá trị. Bean fallback vẫn tồn tại trong context và có thể xuất hiện khi inject collection.

### 9.3. Bảng so sánh

| Tiêu chí | `@ConditionalOnMissingBean` | `@Fallback` |
| --- | --- | --- |
| Nguồn | Spring Boot autoconfigure | Spring Framework 6.2+ |
| Vai trò | Điều kiện đăng ký bean definition | Đánh dấu mức ưu tiên khi autowiring |
| Bean mặc định khi ứng dụng có bean riêng | Có thể không được đăng ký | Vẫn được đăng ký |
| Ảnh hưởng collection injection | Chỉ các bean thực sự được đăng ký mới xuất hiện | Bean fallback vẫn xuất hiện nếu phù hợp kiểu |
| Dùng khi | Chỉ muốn tạo bean mặc định nếu chưa có bean khác | Muốn giữ default bean nhưng ưu tiên bean thông thường khi inject một giá trị |

Hai cơ chế có thể phục vụ các mục tiêu thiết kế khác nhau. Trong auto-configuration của Spring Boot, `@ConditionalOnMissingBean` vẫn là công cụ phổ biến để cho phép người dùng thay thế hoàn toàn một cấu hình mặc định. `@Fallback` hữu ích khi muốn nhiều implementation cùng tồn tại nhưng một implementation đóng vai trò dự phòng.

Không nên thêm cả hai annotation vào một method mà không xác định rõ ý định. Nếu condition không cho phép bean được đăng ký, metadata fallback trên bean ấy không còn tác dụng trong context đó.

## 10. Ví dụ ứng dụng: cung cấp implementation mặc định cho starter

Giả sử bạn đang viết một module dùng chung cung cấp khả năng ghi audit. Ứng dụng tiêu thụ module cần một bean `AuditWriter`.

Contract:

~~~java
public interface AuditWriter {
    void write(String event);
}
~~~

Implementation dự phòng:

~~~java
public class NoOpAuditWriter implements AuditWriter {
    @Override
    public void write(String event) {
        // Không ghi audit trong cấu hình mặc định.
    }
}
~~~

Cấu hình mặc định:

~~~java
@Configuration
public class AuditDefaultConfiguration {

    @Bean
    @Fallback
    public AuditWriter defaultAuditWriter() {
        return new NoOpAuditWriter();
    }
}
~~~

Trong ứng dụng thực tế, nhóm phát triển cung cấp implementation:

~~~java
@Component
public class DatabaseAuditWriter implements AuditWriter {
    @Override
    public void write(String event) {
        // Ghi event vào database.
    }
}
~~~

Service tiêu thụ contract:

~~~java
@Service
public class AccountService {
    private final AuditWriter auditWriter;

    public AccountService(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    public void changeEmail(String email) {
        // Thực hiện thay đổi email...
        auditWriter.write("Account email changed");
    }
}
~~~

Hai tình huống:

**Ứng dụng không cung cấp implementation riêng:** `defaultAuditWriter` là candidate duy nhất, nên được inject. Ứng dụng vẫn khởi động và có một hành vi mặc định có chủ đích.

**Ứng dụng cung cấp `DatabaseAuditWriter`:** bean này là candidate thông thường; `NoOpAuditWriter` vẫn có mặt nhưng được đánh dấu fallback. `AccountService` nhận `DatabaseAuditWriter`.

Nhờ vậy, service không cần biết ứng dụng có cấu hình audit thật hay đang dùng fallback. Nó chỉ phụ thuộc `AuditWriter`.

Lưu ý về ví dụ: `NoOpAuditWriter` chỉ phù hợp khi bỏ qua audit là hành vi được chấp nhận cho trường hợp sử dụng đó. Với audit bắt buộc về pháp lý hoặc bảo mật, một implementation no-op có thể nguy hiểm; khi đó nên buộc cấu hình audit thật hoặc làm ứng dụng thất bại khi thiếu cấu hình.

## 11. Kiểm thử hành vi chọn bean

Một kiểm thử context có thể xác nhận Spring chọn implementation thông thường khi có bean fallback.

Ví dụ các bean trong cấu hình:

~~~java
@Configuration
public class AuditTestConfiguration {

    @Bean
    @Fallback
    AuditWriter fallbackAuditWriter() {
        return new NoOpAuditWriter();
    }

    @Bean
    AuditWriter customAuditWriter() {
        return new RecordingAuditWriter();
    }
}
~~~

`RecordingAuditWriter` là implementation test ghi nhận event. Service:

~~~java
@Service
public class AccountService {
    private final AuditWriter auditWriter;

    public AccountService(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    public void changeEmail(String email) {
        auditWriter.write("Changed: " + email);
    }
}
~~~

Test Spring Boot:

~~~java
@SpringBootTest(classes = {
        AuditTestConfiguration.class,
        AccountService.class
})
class AuditFallbackSelectionTest {

    @Autowired
    private AuditWriter auditWriter;

    @Test
    void selectsRegularBeanOverFallbackBean() {
        assertInstanceOf(RecordingAuditWriter.class, auditWriter);
    }
}
~~~

Test cần import JUnit, Spring Boot Test và các kiểu Spring tương ứng; các implementation `NoOpAuditWriter`, `RecordingAuditWriter` phải được định nghĩa trong test source hoặc source phù hợp.

Có thể kiểm tra thêm collection:

~~~java
@Autowired
private List<AuditWriter> writers;

@Test
void includesFallbackBeanInCollection() {
    assertEquals(2, writers.size());
}
~~~

Điều này minh họa rằng bean fallback vẫn được đăng ký và vẫn xuất hiện trong collection injection.

### 11.1. Kiểm tra khi chỉ có fallback bean

Tạo một context chỉ đăng ký `fallbackAuditWriter`, sau đó inject `AuditWriter`. Bean fallback vẫn là lựa chọn duy nhất và được cung cấp.

### 11.2. Kiểm tra khi có hai bean thông thường

Nếu cấu hình thêm hai bean `AuditWriter` không đánh dấu fallback và injection point yêu cầu một giá trị, `@Fallback` trên bean thứ ba không quyết định giữa hai bean thông thường. Test nên xác nhận context báo lỗi nhập nhằng nếu không có qualifier, primary hoặc quy tắc chọn khác.

Không nên chỉ kiểm tra rằng ứng dụng khởi động với một implementation; hãy kiểm tra đúng tình huống cấu hình mà module muốn hỗ trợ.

## 12. Những hiểu nhầm thường gặp

### 12.1. “@Fallback có nghĩa là chỉ tạo bean khi không có bean khác”

Không chính xác. `@Fallback` không phải condition ngăn đăng ký. Bean được đăng ký bình thường; annotation chỉ đánh dấu vai trò trong lựa chọn autowire candidate. Nếu muốn không đăng ký bean khi đã có implementation khác, cân nhắc `@ConditionalOnMissingBean`.

### 12.2. “@Fallback loại bean khỏi List hoặc Map”

Không. Các bean phù hợp kiểu vẫn được đưa vào array, collection, map và stream của `ObjectProvider`. Fallback chỉ ảnh hưởng lựa chọn single-valued dependency.

### 12.3. “@Fallback là cách xử lý lỗi khi service chính thất bại”

Không. Annotation không tự phát hiện exception, timeout, lỗi kết nối hoặc trạng thái unhealthy. Nó không tự chuyển sang implementation khác sau khi method của bean chính ném lỗi.

Nếu cần failover khi runtime, phải thiết kế cơ chế resilience riêng như retry, circuit breaker, routing hoặc xử lý exception theo nghiệp vụ.

### 12.4. “@Fallback thay thế @Qualifier”

Không. Nếu một consumer cần chính xác implementation có đặc tính cụ thể, qualifier là cách diễn đạt phù hợp. Fallback chỉ phân biệt bean dự phòng với candidate thông thường khi autowiring một giá trị.

### 12.5. “Chỉ cần thêm @Fallback là hết lỗi NoUniqueBeanDefinitionException”

Không. Nếu vẫn còn nhiều candidate thông thường cùng phù hợp, hoặc nhiều fallback candidate mà không có quy tắc lựa chọn rõ ràng, sự nhập nhằng vẫn có thể tồn tại. Cần xem danh sách bean, qualifier và primary metadata.

### 12.6. “@Fallback dùng được trên mọi Spring Boot 3.x”

Không. Spring Boot 3.3.x dùng Spring Framework 6.1.x nên không có annotation này. Cần Framework 6.2 trở lên; trong hệ Boot 3.x, điều đó tương ứng với Boot 3.4 trở lên.

### 12.7. “Đánh dấu class fallback là đủ dù class chưa được đăng ký”

Không. `@Fallback` không thay thế `@Component`, `@Bean` hoặc cơ chế đăng ký bean khác. Nếu class không được container phát hiện hay đăng ký, annotation không thể tự tạo bean definition.

## 13. Quy trình chẩn đoán khi bean fallback không được chọn

Khi kết quả injection không như mong đợi, hãy kiểm tra theo thứ tự:

1. **Phiên bản Framework:** ứng dụng có Spring Framework 6.2+ không?
2. **Bean có được đăng ký?** Component scan, `@Bean` method, profile và condition có cho phép bean xuất hiện không?
3. **Kiểu có phù hợp?** Bean có thực sự implements interface hoặc kế thừa kiểu mà injection point yêu cầu không?
4. **Fallback metadata có được đặt đúng?** Annotation trên class component hoặc factory method có nằm trên bean definition thực sự không?
5. **Có nhiều bean thông thường?** `@Fallback` không chọn thay giữa các candidate thông thường còn lại.
6. **Có qualifier hoặc primary?** Các metadata khác có thể ảnh hưởng candidate selection.
7. **Injection là single-valued hay collection?** Collection vẫn nhận mọi bean phù hợp kiểu, bao gồm fallback.
8. **Có đang dùng một bean từ context khác?** Parent/child context hoặc cấu hình test có thể khiến tập candidate khác với dự đoán.

Một số exception thường gặp:

| Exception | Ý nghĩa có thể liên quan |
| --- | --- |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp được đăng ký/nhìn thấy |
| `NoUniqueBeanDefinitionException` | Có nhiều candidate nhưng không chọn được một bean duy nhất |
| `UnsatisfiedDependencyException` | Một dependency trong quá trình tạo bean không được giải quyết |

Hãy đọc cause và bean name trong stack trace. Không nên sửa bằng cách thêm `@Primary` hoặc đổi scope một cách ngẫu nhiên trước khi hiểu tập candidate.

## 14. Khi nào nên sử dụng @Fallback?

`@Fallback` phù hợp trong những tình huống:

- Một thư viện muốn cung cấp implementation mặc định để ứng dụng có thể chạy ngay.
- Ứng dụng có implementation no-op hoặc đơn giản cho môi trường không cần tích hợp bên ngoài.
- Một module cung cấp bean dự phòng nhưng vẫn cho phép ứng dụng tiêu thụ đăng ký bean thông thường.
- Bạn muốn giữ nhiều bean trong container nhưng để một bean đóng vai trò dự phòng cho injection một giá trị.

Không nên dùng `@Fallback` khi:

- Chỉ có một bean và không có candidate cạnh tranh; annotation thường không mang thêm giá trị lựa chọn.
- Consumer cần một implementation cụ thể; dùng `@Qualifier`.
- Cần ưu tiên rõ một implementation giữa nhiều candidate thông thường; cân nhắc `@Primary`.
- Muốn không đăng ký bean mặc định khi người dùng đã cung cấp bean khác; cân nhắc `@ConditionalOnMissingBean`.
- Cần chuyển sang implementation khác sau lỗi runtime; dùng cơ chế resilience phù hợp.

Hãy chọn annotation theo ý nghĩa cấu hình mà bạn muốn biểu đạt, không chỉ để làm context khởi động thành công.

## 15. Bài thực hành

### Bài A: Chọn bean mặc định

Tạo interface:

~~~java
public interface GreetingProvider {
    String greeting(String name);
}
~~~

Tạo hai implementation:

- `DefaultGreetingProvider` trả lời lời chào đơn giản và được đánh dấu `@Fallback`.
- `VietnameseGreetingProvider` trả lời theo quy tắc riêng và là bean thông thường.

Tạo service inject `GreetingProvider`. Khi cả hai bean được đăng ký, hãy xác nhận implementation tiếng Việt được chọn.

### Bài B: Chỉ có fallback bean

Tạm thời loại `VietnameseGreetingProvider` khỏi context. Chạy lại test và xác nhận `DefaultGreetingProvider` vẫn được inject.

Giải thích vì sao fallback bean không bị bỏ qua chỉ vì nó mang annotation `@Fallback`.

### Bài C: Nhiều bean thông thường

Thêm `EnglishGreetingProvider` không đánh dấu fallback. Bây giờ có hai bean thông thường cùng kiểu và một bean fallback.

Quan sát lỗi khi inject một `GreetingProvider` duy nhất. Sửa bằng `@Qualifier` hoặc `@Primary` và giải thích vai trò riêng của từng annotation.

### Bài D: Collection injection

Inject `List<GreetingProvider>`. Xác nhận danh sách vẫn chứa cả bean fallback và các bean thông thường.

Giải thích vì sao kết quả này khác với constructor chỉ nhận một `GreetingProvider`.

### Bài E: So sánh với @ConditionalOnMissingBean

Viết hai cấu hình riêng:

1. Một cấu hình dùng `@Fallback` trên bean mặc định.
2. Một cấu hình dùng `@ConditionalOnMissingBean(GreetingProvider.class)`.

Khi ứng dụng có implementation riêng, quan sát sự khác biệt về số bean được đăng ký và kết quả collection injection.

### Bài F: Kiểm tra tương thích phiên bản

Trong một dự án Spring Boot 3.3.x, thử import `org.springframework.context.annotation.Fallback` và ghi nhận lỗi biên dịch. Sau đó xem dependency tree của `spring-context`, nâng dự án lên dòng Boot tương thích Spring Framework 6.2 và xác nhận import được giải quyết.

Bài thực hành này giúp hiểu annotation thuộc Framework và được cung cấp theo version quản lý của Boot.

## 16. Câu hỏi tự kiểm tra

**1. @Fallback được giới thiệu từ Spring Framework phiên bản nào?**

Từ Spring Framework 6.2. Các ứng dụng dùng Framework 6.1 trở xuống không có annotation này.

**2. Spring Boot 3.3.x có dùng trực tiếp @Fallback không?**

Không theo tổ hợp mặc định, vì Boot 3.3.x dùng Framework 6.1.x. Spring Boot 3.4.x chuyển sang Framework 6.2.x và hỗ trợ annotation.

**3. Nếu có một bean thường và một bean fallback cùng kiểu, bean nào được inject vào constructor?**

Bean thông thường được ưu tiên, nếu không có một quy tắc lựa chọn cụ thể khác làm thay đổi candidate.

**4. Nếu chỉ có một bean fallback, Spring có inject được không?**

Có. Khi đó nó là candidate phù hợp duy nhất.

**5. @Fallback có loại bean khỏi List không?**

Không. Tất cả bean phù hợp kiểu vẫn được đưa vào array, collection, map và stream của `ObjectProvider`.

**6. @Fallback khác @Primary thế nào?**

`@Primary` đánh dấu bean được ưu tiên; `@Fallback` đánh dấu bean dự phòng để bean thông thường được chọn khi có thể.

**7. @Fallback có thay thế @ConditionalOnMissingBean không?**

Không. `@ConditionalOnMissingBean` điều khiển việc đăng ký bean definition; `@Fallback` điều khiển mức ưu tiên khi chọn bean cho autowiring.

**8. @Fallback có tự xử lý lỗi runtime của implementation chính không?**

Không. Đây là cơ chế lựa chọn bean trong quá trình dependency resolution, không phải cơ chế failover khi gọi method thất bại.

## 17. Kết luận

`@Fallback` giúp Spring Framework biểu đạt rõ một implementation là **lựa chọn dự phòng** khi có nhiều bean cùng đáp ứng một kiểu. Annotation được giới thiệu từ Spring Framework 6.2, có thể đặt trên class bean hoặc phương thức `@Bean`. Trong hệ Spring Boot 3.x, cần dùng Boot 3.4 trở lên để có Framework 6.2 theo cấu hình nền; Boot 3.3.x và các dòng Framework 6.1 không hỗ trợ.

Khi inject một giá trị, nếu có một bean thông thường duy nhất bên cạnh các bean fallback, Spring chọn bean thông thường. Nếu chỉ có fallback bean, nó vẫn được sử dụng. Khi inject collection, các bean fallback vẫn được bao gồm. Hãy dùng `@Primary` cho lựa chọn ưu tiên, `@Qualifier` cho lựa chọn cụ thể, và `@ConditionalOnMissingBean` khi muốn điều khiển việc đăng ký bean mặc định.

Giá trị của `@Fallback` nằm ở việc một thư viện hoặc cấu hình có thể cung cấp implementation mặc định mà ứng dụng tiêu thụ dễ dàng thay bằng bean riêng. Hiểu đúng phạm vi và giới hạn của annotation giúp thiết kế cấu hình IoC rõ ràng, tránh nhầm lẫn giữa lựa chọn bean lúc khởi tạo và failover khi ứng dụng đang chạy.

## Tài liệu tham khảo

- [Spring Framework 6.2 — @Fallback Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Fallback.html)
- [Spring Framework Reference — Fine-tuning Autowiring with @Primary or @Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework 6.2 Release Notes — Support for fallback beans](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes)
- [Spring Boot 3.3 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.4 System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html)

