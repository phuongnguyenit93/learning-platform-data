# SpringRetryCircuitBreakerFactory và SpringRetryConfigBuilder

## Spring Retry trong Spring Cloud Circuit Breaker

Spring Cloud Circuit Breaker cung cấp một API chung để ứng dụng tạo và gọi Circuit Breaker thông qua `CircuitBreakerFactory`. Một trong các implementation có thể được chọn là Spring Retry. Implementation này kết hợp `SpringRetryCircuitBreakerFactory` với cơ chế retry có trạng thái của Spring Retry để vừa thử lại lời gọi theo chính sách, vừa ngăn các lời gọi tiếp tục đi đến dependency khi circuit đang mở.

Hai lớp chính có vai trò khác nhau:

- **`SpringRetryCircuitBreakerFactory`** là factory do Spring tạo từ starter Spring Retry. Ứng dụng inject factory này, tạo breaker theo ID và dùng API `run` để thực thi supplier cùng fallback.
- **`SpringRetryConfigBuilder`** xây dựng cấu hình cho breaker. Builder nhận một `RetryPolicy`; factory dùng cấu hình đó để tạo `CircuitBreakerRetryPolicy` và `DefaultRetryState` tương ứng.

Spring Retry thực hiện circuit breaker bằng `CircuitBreakerRetryPolicy` kết hợp stateful retry. Chính sách retry quyết định một lời gọi được thử bao nhiêu lần và trong điều kiện nào. Phần trạng thái giữ kết quả retry giữa các lần gọi, nhờ đó factory có thể nhận biết breaker đã mở và chuyển nhanh sang fallback.

## Thêm starter và chọn đúng phiên bản

Với ứng dụng Spring Boot dùng Spring Cloud Circuit Breaker và Spring Retry, thêm starter sau:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-spring-retry</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-spring-retry'
}
```

Để Spring Cloud BOM quản lý phiên bản starter cùng các thành phần Spring Cloud khác. Chọn release train tương thích với Spring Boot đang dùng; không tự ghép một phiên bản starter riêng với Spring Cloud Commons hoặc Spring Retry ở một dòng khác. Sau khi thêm dependency, kiểm tra runtime dependency graph để xác nhận Spring Cloud Circuit Breaker Spring Retry và Spring Retry được resolve.

Spring Retry Circuit Breaker là lựa chọn cho lời gọi đồng bộ dựa trên `RetryTemplate`. Với ứng dụng WebFlux hoặc publisher `Mono`/`Flux`, hãy chọn implementation có hỗ trợ reactive, thường là Resilience4j Reactor provider. Không gọi `block()` để đưa một pipeline reactive vào `SpringRetryCircuitBreakerFactory`.

## Tạo và sử dụng Circuit Breaker từ factory

Sau khi starter được nạp, Spring cung cấp bean `CircuitBreakerFactory`. Có thể inject abstraction này vào service:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryService {
    private final RestTemplate restTemplate;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public InventoryService(
            RestTemplate restTemplate,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restTemplate = restTemplate;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Inventory find(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> restTemplate.getForObject(
                "http://inventory-service/items/" + sku,
                Inventory.class
            ),
            error -> Inventory.unavailable(sku)
        );
    }
}
```

`create("inventory")` tạo hoặc lấy breaker có ID `inventory`. Supplier chứa lời gọi đồng bộ đến dịch vụ tồn kho. Nếu supplier thất bại hoặc breaker từ chối lời gọi do đang mở, fallback nhận nguyên nhân và trả kết quả thay thế.

`Inventory` là kiểu dữ liệu do ứng dụng định nghĩa. `Inventory.unavailable` nên biểu thị rõ trạng thái chưa xác định hoặc dịch vụ tạm thời không sẵn sàng. Không trả một đối tượng có số lượng bằng 0 nếu điều đó khiến caller hiểu nhầm rằng sản phẩm chắc chắn hết hàng.

ID breaker cần ổn định theo dependency hoặc failure domain. Nếu mỗi request tạo một ID khác nhau, trạng thái retry sẽ bị chia nhỏ và Circuit Breaker không còn bảo vệ được nhóm lời gọi như dự kiến.

## SpringRetryConfigBuilder tạo cấu hình như thế nào?

`SpringRetryConfigBuilder` là builder dành riêng cho implementation Spring Retry. Điểm cấu hình quan trọng là `retryPolicy(...)`. Chính sách được truyền vào là chính sách delegate để Spring Retry quyết định số lần thử và điều kiện tiếp tục retry. Factory kết hợp nó với `CircuitBreakerRetryPolicy` và `DefaultRetryState` để tạo breaker có trạng thái.

Ví dụ đặt chính sách mặc định cho mọi breaker:

```java
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.springretry.SpringRetryCircuitBreakerFactory;
import org.springframework.cloud.circuitbreaker.springretry.SpringRetryConfigBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.policy.TimeoutRetryPolicy;

@Configuration(proxyBeanMethods = false)
public class SpringRetryCircuitBreakerConfiguration {

    @Bean
    Customizer<SpringRetryCircuitBreakerFactory> defaultRetryCustomizer() {
        return factory -> factory.configureDefault(id ->
            new SpringRetryConfigBuilder(id)
                .retryPolicy(new TimeoutRetryPolicy())
                .build()
        );
    }
}
```

`configureDefault` áp dụng cấu hình cho các ID chưa có cấu hình riêng. Trong ví dụ, `TimeoutRetryPolicy` điều khiển việc retry theo thời gian của Spring Retry. Hãy đọc tài liệu Spring Retry của phiên bản dự án để hiểu timeout và hành vi retry mặc định của policy được chọn; không đồng nhất timeout của retry policy với timeout của HTTP client.

## Chọn RetryPolicy phù hợp

`RetryPolicy` quyết định khi nào một lần gọi được thử lại. Một số policy thường gặp:

| Policy | Cách hoạt động | Trường hợp phù hợp |
| --- | --- | --- |
| `SimpleRetryPolicy` | Giới hạn số lần thử tối đa. | Muốn đặt số lần thử hữu hạn và dễ dự đoán. |
| `TimeoutRetryPolicy` | Cho phép retry trong một khoảng thời gian theo policy. | Muốn giới hạn cửa sổ retry theo thời gian. |
| Policy phân loại exception | Chỉ retry với một số loại lỗi được chỉ định. | Muốn retry lỗi kết nối tạm thời nhưng không retry lỗi validation hoặc lỗi nghiệp vụ. |

Ví dụ dùng `SimpleRetryPolicy` với tối đa ba lần thực thi cho mỗi invocation:

```java
import org.springframework.retry.policy.SimpleRetryPolicy;

new SpringRetryConfigBuilder("inventory")
    .retryPolicy(new SimpleRetryPolicy(3))
    .build();
```

`maxAttempts` tính cả lần gọi đầu tiên. Vì vậy, `new SimpleRetryPolicy(3)` cho phép tối đa ba lần thực thi tổng cộng, tức tối đa hai lần retry sau lần đầu. Policy này minh họa cách giới hạn số lần thử; trong production, nên chọn policy có phân loại exception để không lặp lại các lỗi không thể khắc phục bằng retry.

Ví dụ tạo policy phân biệt lỗi kết nối với lỗi đầu vào:

```java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import org.springframework.retry.RetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;

Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(IOException.class, true);
retryable.put(IllegalArgumentException.class, false);

RetryPolicy inventoryRetryPolicy = new SimpleRetryPolicy(
    3,
    retryable,
    true
);
```

Tham số `true` yêu cầu policy xét cả cause khi ngoại lệ bị bọc. Cần kiểm tra các kiểu exception thực tế mà HTTP client phát ra; ví dụ `IOException` chỉ đại diện một nhóm lỗi, không bao quát mọi lỗi kết nối hoặc timeout của mọi client.

## Cấu hình riêng theo ID

Không phải dependency nào cũng nên dùng cùng số lần thử. Dịch vụ danh mục có thể chịu được một vài lần retry ngắn, trong khi dịch vụ thanh toán cần chính sách thận trọng hơn để tránh lặp thao tác ghi.

Có thể cấu hình theo ID bằng `factory.configure(...)`:

```java
@Bean
Customizer<SpringRetryCircuitBreakerFactory> serviceRetryPolicies() {
    return factory -> {
        factory.configure(
            builder -> builder
                .retryPolicy(new SimpleRetryPolicy(3))
                .build(),
            "inventory"
        );

        factory.configure(
            builder -> builder
                .retryPolicy(new SimpleRetryPolicy(1))
                .build(),
            "payment"
        );
    };
}
```

Với `inventory`, policy cho phép tối đa ba lần thực thi. Với `payment`, `SimpleRetryPolicy(1)` chỉ cho phép một lần thực thi và không retry thêm. Cấu hình riêng được gắn với đúng ID truyền vào `create(...)`; tên trong cấu hình phải khớp với ID trong mã gọi.

Khi cùng một ID có cả default và cấu hình riêng, cấu hình riêng là lựa chọn dành cho ID đó. Tránh tạo nhiều customizer cùng cấu hình một ID mà không có chủ đích rõ ràng, vì thứ tự cấu hình có thể làm chính sách cuối cùng khó xác định.

## RetryTemplate và addRetryTemplateCustomizers

Spring Retry thực thi lời gọi thông qua `RetryTemplate`. `SpringRetryCircuitBreakerFactory` cho phép thêm customizer để chỉnh `RetryTemplate` sau khi cấu hình breaker được tạo nhưng trước khi nó được sử dụng. Một ứng dụng có thể đăng ký `RetryListener` để quan sát vòng đời retry.

```java
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.springretry.SpringRetryCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

@Bean
Customizer<SpringRetryCircuitBreakerFactory> retryListenerCustomizer() {
    return factory -> factory.addRetryTemplateCustomizers(retryTemplate ->
        retryTemplate.registerListener(new RetryListener() {
            @Override
            public <T, E extends Throwable> boolean open(
                    RetryContext context,
                    RetryCallback<T, E> callback) {
                return true;
            }

            @Override
            public <T, E extends Throwable> void close(
                    RetryContext context,
                    RetryCallback<T, E> callback,
                    Throwable throwable) {
                // Ghi nhận invocation đã kết thúc.
            }

            @Override
            public <T, E extends Throwable> void onError(
                    RetryContext context,
                    RetryCallback<T, E> callback,
                    Throwable throwable) {
                // Ghi nhận một lần thực thi thất bại.
            }
        })
    );
}
```

`open` được gọi khi một retry operation bắt đầu; trả về `true` để cho phép operation tiếp tục. `onError` được gọi khi một lần thực thi gặp lỗi. `close` được gọi khi operation kết thúc. Có thể dùng listener để ghi log hoặc cập nhật số liệu tổng hợp, nhưng tránh đưa ID người dùng, URL đầy đủ hoặc exception message vào metric tag có cardinality cao.

`addRetryTemplateCustomizers` tác động đến các `RetryTemplate` do factory tạo. Nếu cần hành vi khác nhau theo dependency, hãy kiểm tra khả năng cấu hình theo ID trong phiên bản đang dùng và tránh áp dụng một customizer toàn cục làm thay đổi ngoài ý muốn tất cả breaker.

## Stateful retry và trạng thái Circuit Breaker

Điểm khác biệt của Spring Retry Circuit Breaker so với một `RetryTemplate` stateless thông thường là trạng thái được giữ giữa các invocation. Spring Cloud tạo `CircuitBreakerRetryPolicy` cùng `DefaultRetryState` cho breaker. Khi policy delegate đã hết khả năng retry sau các lần thất bại, trạng thái circuit được đánh dấu mở. Những invocation tiếp theo trong thời gian mở có thể bị từ chối sớm và đi vào fallback thay vì tiếp tục gọi dependency.

Luồng khái quát:

```text
Invocation đến factory
        |
        v
Kiểm tra trạng thái retry có lưu
        |
        +---- Circuit đang mở ----> Bỏ qua supplier ----> Fallback
        |
        v
Circuit cho phép thực thi
        |
        v
RetryPolicy điều khiển các lần thử
        |
        +---- Thành công ----------> Trả kết quả
        |
        +---- Hết khả năng retry --> Ghi trạng thái mở --> Fallback
        |
        v
Sau thời gian reset, context có thể được làm mới
        |
        v
Invocation tiếp theo thử lại dependency
```

Trong Spring Retry, trạng thái circuit gắn với stateful retry context và key của breaker. Khi triển khai nhiều replica, trạng thái trong bộ nhớ của mỗi tiến trình không tự đồng bộ giữa các replica. Một instance Gateway hoặc service có thể đang mở circuit trong khi instance khác vẫn đang cho phép lời gọi. Nếu cần phối hợp trạng thái trên nhiều node, phải thiết kế cơ chế chia sẻ trạng thái riêng; không giả định factory tự tạo trạng thái phân tán.

## Không nhầm với sliding window của Resilience4j

Spring Retry Circuit Breaker và Resilience4j đều có thể ngăn lời gọi đến dependency đang lỗi, nhưng cơ chế quyết định mở circuit khác nhau.

| Khía cạnh | Spring Retry Circuit Breaker | Resilience4j Circuit Breaker |
| --- | --- | --- |
| Cơ chế cốt lõi | `CircuitBreakerRetryPolicy` kết hợp stateful retry và `DefaultRetryState`. | Máy trạng thái Circuit Breaker với metrics và sliding window. |
| Điều kiện thất bại | Policy retry delegate không còn cho phép thử tiếp. | Failure rate hoặc slow-call rate đạt ngưỡng sau khi đủ số mẫu tối thiểu. |
| Cấu hình thường dùng | `SpringRetryConfigBuilder.retryPolicy(...)`. | `CircuitBreakerConfig`, `failureRateThreshold`, `slidingWindowSize`, `minimumNumberOfCalls`. |
| Retry | Là một phần trực tiếp trong policy của Spring Retry. | Thường kết hợp decorator Retry riêng với Circuit Breaker. |
| Reactive | Tích hợp Spring Retry này dựa trên `RetryTemplate` đồng bộ. | Có provider Reactor cho `Mono` và `Flux`. |

Không chuyển nguyên các property như `failureRateThreshold`, `slidingWindowSize` hoặc `minimumNumberOfCalls` sang `SpringRetryConfigBuilder`; đó là cấu hình Resilience4j. Với Spring Retry, hãy chọn policy retry phù hợp và hiểu cách policy đó quyết định khi nào stateful circuit mở.

## Phân biệt Spring Retry và Framework Retry

Các phiên bản Spring Cloud mới có thể cung cấp thêm implementation tên Framework Retry dựa trên API retry của Spring Framework 7. Implementation đó dùng `FrameworkRetryCircuitBreakerFactory` và `FrameworkRetryConfigBuilder`. Đây là provider khác với bài học này, vốn sử dụng `SpringRetryCircuitBreakerFactory` và `SpringRetryConfigBuilder` thuộc module Spring Retry.

Khi đọc ví dụ hoặc nâng cấp dependency, hãy đối chiếu chính xác tên factory, builder và starter. Không thay `SpringRetryCircuitBreakerFactory` bằng `FrameworkRetryCircuitBreakerFactory` chỉ vì tên gần giống nhau; hai provider có dependency và cấu hình riêng.

## Retry có thể làm tăng tải: chọn policy an toàn

Retry hữu ích với lỗi tạm thời như kết nối bị reset hoặc một số lỗi gateway, nhưng mỗi lần thử bổ sung đều tạo thêm tải lên dependency. Khi dependency đang quá tải, retry không giới hạn có thể khiến sự cố nghiêm trọng hơn.

Một số nguyên tắc khi chọn policy:

- Đặt số lần thử hữu hạn và tính cả lần thực thi ban đầu.
- Chỉ retry loại exception có khả năng tự phục hồi; không retry lỗi validation, phân quyền hoặc lỗi nghiệp vụ không thể thay đổi bằng chờ đợi.
- Dùng backoff để các lần retry không dồn cùng lúc. Nếu cần cấu hình `BackOffPolicy`, thực hiện qua điểm tùy chỉnh `RetryTemplate` được phiên bản Spring Retry hỗ trợ.
- Đặt connect timeout, read timeout và deadline tổng ở HTTP client. RetryPolicy không thay thế timeout của lời gọi mạng.
- Chỉ retry thao tác ghi khi có idempotency key hoặc cơ chế chống thực hiện trùng.
- Phối hợp số lần retry với thời gian mở circuit và thời hạn nghiệp vụ để request không chờ lâu hơn mức cho phép.

Ví dụ, một lời gọi lấy thông tin sản phẩm có thể retry lỗi kết nối hai lần. Một lệnh thanh toán không nên tự động thực thi lại nếu không có idempotency key, vì lần đầu có thể đã được xử lý ở server nhưng response bị mất.

## Fallback khi retry hết hoặc circuit đang mở

Khi lời gọi đã dùng hết khả năng retry hoặc bị circuit từ chối, fallback trong `run` cung cấp kết quả thay thế:

```java
public PaymentStatus getStatus(String paymentId) {
    return circuitBreakerFactory.create("payment-status").run(
        () -> paymentClient.getStatus(paymentId),
        error -> PaymentStatus.unknown(paymentId)
    );
}
```

Fallback cần thể hiện đúng ý nghĩa. `unknown` nói rằng ứng dụng chưa xác định được trạng thái thanh toán; không được trả `FAILED` hoặc `SUCCESS` nếu dịch vụ thanh toán chưa xác nhận. Đặc biệt với thao tác ghi, fallback không có nghĩa giao dịch đã được hoàn tất.

Phân loại lỗi trong retry policy cũng ảnh hưởng fallback. Nếu policy chỉ retry một số exception, các exception khác có thể đi thẳng đến fallback sau lần thực thi đầu tiên. Hãy xác định rõ exception nào cần retry, exception nào không retry và kết quả nào fallback được phép tạo.

## Giới hạn và lựa chọn provider

Spring Retry Circuit Breaker phù hợp khi ứng dụng đồng bộ đã dùng Spring Retry và muốn tận dụng `RetryPolicy`, stateful retry cùng `RetryTemplate`. Tuy nhiên, cần cân nhắc các giới hạn sau:

- Không có mô hình cấu hình failure-rate theo sliding window như Resilience4j.
- Chính sách circuit phụ thuộc vào delegate retry policy và trạng thái retry được lưu.
- Retry có thể làm tăng latency tổng; phải tính backoff và timeout vào deadline của request.
- Trạng thái trong bộ nhớ không tự chia sẻ giữa nhiều instance.
- Tích hợp này không phải lựa chọn cho reactive pipeline `Mono`/`Flux`.
- Cần tự thiết kế quan sát retry và trạng thái circuit phù hợp; không giả định có cùng bộ metrics như Resilience4j.

Nếu cần sliding window, slow-call threshold, bulkhead, rate limiter, metrics tích hợp sâu hoặc reactive support, Resilience4j thường phù hợp hơn. Nếu ứng dụng đã chuẩn hóa Spring Retry và cần một policy retry có trạng thái theo API Spring Cloud Circuit Breaker, Spring Retry provider vẫn là một lựa chọn có thể cân nhắc.

## Kiểm tra tích hợp

Khi triển khai, hãy kiểm tra các tình huống sau bằng dependency giả lập hoặc môi trường kiểm thử:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Dependency trả thành công ngay lần đầu | Supplier chạy một lần và kết quả được trả về. |
| Lần đầu lỗi tạm thời, lần sau thành công | RetryPolicy cho phép thử lại và invocation trả kết quả thành công. |
| Tất cả lần thử đều thất bại | Policy hết khả năng retry, trạng thái circuit được cập nhật và fallback được gọi. |
| Circuit đang mở | Supplier không được thực thi lại trong thời gian mở; fallback nhận lỗi từ chối. |
| Hết thời gian reset | Invocation tiếp theo được phép thử dependency theo cơ chế stateful retry. |
| Exception không thuộc nhóm retry | Không lặp lại ngoài ý muốn; fallback hoặc caller nhận lỗi theo cấu hình. |
| Nhiều instance ứng dụng | Xác nhận mỗi tiến trình có trạng thái riêng và quan sát được sự khác biệt đó. |

Khi debug, kiểm tra factory có được inject đúng implementation hay không, ID truyền vào `create` có khớp customizer hay không và policy được áp dụng có đúng loại exception hay không. Nếu retry không xảy ra, xem lại `RetryPolicy`; nếu circuit không mở như mong đợi, kiểm tra stateful retry và cách policy delegate báo hết khả năng retry.

## Tài liệu tham khảo

- [Spring Cloud Circuit Breaker: Configuring Spring Retry Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-spring-retry.html)
- [Spring Retry: CircuitBreakerRetryPolicy](https://github.com/spring-projects/spring-retry/blob/main/src/main/java/org/springframework/retry/policy/CircuitBreakerRetryPolicy.java)

`SpringRetryCircuitBreakerFactory` kết nối API Circuit Breaker của Spring Cloud với cơ chế stateful retry của Spring Retry. `SpringRetryConfigBuilder` là điểm khai báo `RetryPolicy` để factory tạo breaker theo từng ID. Khi hiểu rõ vai trò của retry policy, trạng thái được lưu và fallback, ứng dụng có thể sử dụng provider này có kiểm soát và tránh nhầm nó với mô hình sliding window của Resilience4j.
