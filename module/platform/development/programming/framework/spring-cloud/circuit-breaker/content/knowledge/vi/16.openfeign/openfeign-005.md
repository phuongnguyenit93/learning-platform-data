# Khai báo fallback và fallbackFactory để đọc nguyên nhân lỗi

Spring Cloud OpenFeign cho phép khai báo fallback cho một Feign client khi lời gọi từ xa thất bại hoặc Circuit Breaker từ chối lời gọi vì đang ở trạng thái OPEN. Có hai cách phổ biến: thuộc tính **fallback** trỏ đến một lớp triển khai thay thế, còn **fallbackFactory** trỏ đến một factory nhận nguyên nhân lỗi và tạo ra đối tượng fallback.

Nếu chỉ cần trả về kết quả suy giảm cố định, fallback là cách đơn giản. Nếu cần phân biệt timeout, lỗi HTTP, lỗi kết nối hoặc lời gọi bị Circuit Breaker từ chối, fallbackFactory hữu ích hơn vì phương thức create nhận được Throwable. Dù dùng cách nào, fallback phải phản ánh đúng ý nghĩa nghiệp vụ, không che giấu sự cố dependency và không tạo thêm lời gọi đến chính dependency đang lỗi.

## 1. Fallback trong Spring Cloud OpenFeign hoạt động khi nào?

Feign client là một interface mô tả lời gọi HTTP đến dịch vụ khác. Khi bật Circuit Breaker support của Spring Cloud OpenFeign, lời gọi được bảo vệ bởi Circuit Breaker. Nếu lời gọi phát sinh lỗi hoặc bị từ chối do Circuit Breaker OPEN, framework có thể gọi fallback đã khai báo cho client.

Các tình huống thường dẫn đến fallback:

- Dịch vụ đích không phản hồi hoặc lỗi kết nối.
- HTTP client phát sinh timeout.
- Response HTTP được chuyển thành exception theo cấu hình Feign ErrorDecoder.
- Circuit Breaker đang OPEN và từ chối lời gọi mới.
- Một lỗi khác được truyền ra khỏi lời gọi được Circuit Breaker bảo vệ.

Fallback không chạy cho mọi response có nội dung nghiệp vụ không mong muốn. Nếu Feign giải mã response thành công và trả về một đối tượng bình thường, framework thường xem lời gọi đã hoàn tất bình thường. Muốn một response cụ thể được xem là lỗi, cần chuyển nó thành exception bằng ErrorDecoder hoặc xử lý kết quả theo chính sách phù hợp.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[Service gọi Feign client] --> B[Circuit Breaker]
    B --> C{Cho phép gọi?}
    C -- Không --> D[Fallback hoặc fallbackFactory]
    C -- Có --> E[Feign gửi HTTP request]
    E --> F{Kết quả}
    F -- Thành công --> G[Trả response đã giải mã]
    F -- Exception --> D
    D --> H[Trả kết quả suy giảm hoặc lỗi]
~~~

Fallback là phần xử lý thay thế ở phía caller. Nó không khôi phục dịch vụ đích, không tự retry và không rollback một thao tác mà server có thể đã thực hiện.

## 2. Điều kiện để bật Circuit Breaker cho OpenFeign

Cần có Spring Cloud OpenFeign và implementation Circuit Breaker tương ứng. Nếu sử dụng Resilience4j, có thể thêm các dependency qua Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Bật tích hợp Circuit Breaker trong application.yml:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Ứng dụng cần bật quét Feign client, thường bằng @EnableFeignClients trên lớp cấu hình hoặc lớp khởi động:

~~~java
@SpringBootApplication
@EnableFeignClients
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Nếu chưa bật Circuit Breaker support, thuộc tính fallback hoặc fallbackFactory không được áp dụng theo luồng bảo vệ của Spring Cloud OpenFeign như mong đợi. Hãy xác nhận property đã được nạp đúng profile và starter implementation đã có trên classpath.

## 3. Khai báo Feign client

Giả sử dịch vụ đơn hàng cần gọi dịch vụ tồn kho. Interface định nghĩa thao tác lấy tồn kho:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryClient",
        fallback = InventoryFallback.class
)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    Inventory getInventory(@PathVariable("sku") String sku);
}
~~~

Ở đây:

- name là tên dịch vụ đích hoặc tên định danh client.
- contextId phân biệt cấu hình của client khi ứng dụng có nhiều Feign client cùng gọi một dịch vụ.
- fallback trỏ đến lớp triển khai thay thế của chính interface InventoryClient.
- getInventory là phương thức nghiệp vụ được gọi qua HTTP.

Nếu dùng service discovery và load balancing, ứng dụng cần dependency load balancer tương ứng. Nếu client khai báo URL trực tiếp trong cấu hình, cách định tuyến sẽ khác. Dù chọn cách nào, Circuit Breaker và fallback vẫn được cấu hình trên Feign client theo ID mà Spring Cloud OpenFeign tạo ra.

## 4. Dùng fallback khi không cần biết nguyên nhân

Lớp fallback phải triển khai cùng interface với Feign client và được Spring quản lý như một bean:

~~~java
import org.springframework.stereotype.Component;

@Component
public class InventoryFallback implements InventoryClient {

    @Override
    public Inventory getInventory(String sku) {
        return Inventory.unavailable(sku);
    }
}
~~~

Trong ví dụ, Inventory.unavailable là một kết quả suy giảm được mô hình nghiệp vụ định nghĩa. Có thể thay bằng dữ liệu cache, trạng thái chưa xác định hoặc lỗi nghiệp vụ có kiểm soát.

Ưu điểm của fallback:

- Ít code và dễ đọc.
- Phù hợp khi mọi nguyên nhân lỗi đều dùng cùng một phản hồi thay thế.
- Không cần xử lý Throwable trong lớp fallback.

Hạn chế là phương thức fallback không nhận trực tiếp nguyên nhân lỗi. Nếu cần ghi nhận hoặc phân biệt timeout với Circuit Breaker OPEN, lớp fallback đơn giản không cung cấp đủ thông tin để đưa ra quyết định theo nguyên nhân.

Không nên dùng fallback để trả về một giá trị có vẻ thành công nhưng không đúng thực tế. Ví dụ, tồn kho không xác định không đồng nghĩa tồn kho bằng 0. Hãy thể hiện trạng thái suy giảm rõ ràng để tầng nghiệp vụ không đưa ra quyết định sai.

## 5. Dùng fallbackFactory để nhận nguyên nhân lỗi

Khi cần biết vì sao lời gọi thất bại, khai báo fallbackFactory trên Feign client:

~~~java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryClient",
        fallbackFactory = InventoryFallbackFactory.class
)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    Inventory getInventory(@PathVariable("sku") String sku);
}
~~~

Factory triển khai FallbackFactory<T> với T là interface Feign client. Phương thức create nhận Throwable và trả về một đối tượng triển khai interface đó.

~~~java
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryFallbackFactory
        implements FallbackFactory<InventoryClient> {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryFallbackFactory.class);

    @Override
    public InventoryClient create(Throwable cause) {
        Throwable reason = cause != null
                ? cause
                : new IllegalStateException("Fallback cause is unavailable");

        return sku -> {
            log.warn(
                    "Inventory fallback activated for sku={}, causeType={}",
                    sku,
                    reason.getClass().getSimpleName()
            );

            return Inventory.unavailable(sku);
        };
    }
}
~~~

Factory nhận nguyên nhân khi tạo fallback implementation. Đối tượng được trả về thực hiện các phương thức thay thế khi Feign client cần fallback. Trong ví dụ, nguyên nhân được giữ lại để ghi log cùng SKU khi phương thức được gọi.

Cần dùng đúng kiểu dữ liệu trả về của interface. Nếu phương thức Feign trả Inventory, fallback cũng trả Inventory. Nếu interface có nhiều phương thức, đối tượng fallback phải triển khai đầy đủ các phương thức đó.

## 6. Phân loại nguyên nhân trong fallbackFactory

Throwable có thể là exception trực tiếp hoặc một exception được bọc trong nguyên nhân khác. Do đó, chỉ kiểm tra lớp ngoài cùng đôi khi không tìm được loại lỗi gốc. Có thể duyệt chuỗi cause để tìm loại exception cần quan tâm.

Ví dụ:

~~~java
import java.util.concurrent.TimeoutException;

import feign.FeignException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

private static <T extends Throwable> T findCause(
        Throwable error,
        Class<T> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return expectedType.cast(current);
        }

        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    return null;
}
~~~

Có thể sử dụng helper này trong factory:

~~~java
@Override
public InventoryClient create(Throwable cause) {
    CallNotPermittedException rejected =
            findCause(cause, CallNotPermittedException.class);

    TimeoutException timeout =
            findCause(cause, TimeoutException.class);

    FeignException httpFailure =
            findCause(cause, FeignException.class);

    if (rejected != null) {
        log.warn("Inventory call rejected because circuit breaker is OPEN");
    } else if (timeout != null) {
        log.warn("Inventory call timed out");
    } else if (httpFailure != null) {
        log.warn("Inventory HTTP call failed with status={}",
                httpFailure.status());
    } else {
        log.warn("Inventory call failed; causeType={}",
                cause == null ? "unknown" : cause.getClass().getName());
    }

    return sku -> Inventory.unavailable(sku);
}
~~~

Các loại exception trên là ví dụ thường gặp. Exception thực tế phụ thuộc HTTP client, ErrorDecoder, adapter Circuit Breaker và phiên bản thư viện. Timeout có thể được biểu diễn bằng một loại exception khác hoặc nằm trong cause chain. Cần kiểm tra log thực tế trước khi viết quy tắc phân loại.

Không nên chỉ dựa vào message để nhận diện lỗi. Message có thể thay đổi theo phiên bản, ngôn ngữ hoặc implementation. Ưu tiên loại exception, HTTP status và mã lỗi ổn định.

## 7. So sánh fallback và fallbackFactory

| Tiêu chí | fallback | fallbackFactory |
|---|---|---|
| Giá trị cấu hình | Lớp triển khai interface Feign | Lớp triển khai FallbackFactory |
| Nhận Throwable | Không | Có trong create(Throwable) |
| Cách tạo hành vi thay thế | Một bean fallback | Factory tạo đối tượng fallback |
| Phù hợp khi | Phản hồi thay thế giống nhau cho mọi lỗi | Cần phân loại lỗi hoặc ghi log theo nguyên nhân |
| Độ phức tạp | Thấp | Cao hơn |
| Ví dụ | Trả trạng thái unavailable chung | Timeout dùng cache, Circuit Breaker OPEN trả trạng thái tạm thời |

Với một Feign client, chọn cách khai báo phù hợp với yêu cầu. Không khai báo đồng thời fallback và fallbackFactory cho cùng một client. Cả hai đều phải tạo ra hành vi thay thế tương thích với interface.

Nếu fallbackFactory chỉ trả cùng một kết quả cho mọi lỗi và không ghi nhận nguyên nhân, lợi ích của factory không đáng kể. Ngược lại, nếu cần quan sát nguyên nhân hoặc phân biệt chính sách suy giảm, factory là lựa chọn rõ ràng hơn.

## 8. Thiết kế fallback theo loại lỗi

Không phải mọi lỗi đều nên có cùng một phản hồi. Ví dụ với dịch vụ tồn kho:

| Nguyên nhân | Cách xử lý có thể phù hợp |
|---|---|
| Circuit Breaker OPEN | Trả trạng thái tạm thời không khả dụng hoặc dữ liệu cache |
| Timeout | Dùng cache nếu dữ liệu còn trong giới hạn freshness |
| Lỗi kết nối | Trả trạng thái suy giảm và ghi nhận lỗi kết nối |
| HTTP 503 | Có thể dùng cache hoặc thông báo dịch vụ đang bận |
| HTTP 404 | Kiểm tra ý nghĩa nghiệp vụ; sản phẩm không tồn tại có thể là kết quả hợp lệ |
| Lỗi xác thực 401/403 | Báo lỗi cấu hình hoặc quyền truy cập; không giả vờ là dữ liệu không có |
| Lỗi dữ liệu hoặc mapping | Ghi nhận lỗi tích hợp và chuyển xử lý theo chính sách nghiệp vụ |

FallbackFactory có thể phân nhánh theo nguyên nhân:

~~~java
@Override
public InventoryClient create(Throwable cause) {
    boolean circuitOpen =
            findCause(cause, CallNotPermittedException.class) != null;

    boolean timedOut =
            findCause(cause, TimeoutException.class) != null;

    return sku -> {
        if (circuitOpen || timedOut) {
            return inventoryCache.findFresh(sku)
                    .orElseGet(() -> Inventory.unavailable(sku));
        }

        return Inventory.unavailable(sku);
    };
}
~~~

Đoạn code giả định inventoryCache là thành phần cache do ứng dụng cung cấp. Cần đặt giới hạn freshness cho dữ liệu cache và thể hiện rõ nguồn dữ liệu trong kết quả nếu nghiệp vụ cần biết đó là dữ liệu cũ.

Không nên gọi lại chính InventoryClient bên trong fallback. Làm vậy có thể tạo vòng lặp gọi lại cùng dependency đang lỗi, làm tăng tải và khiến fallback không còn là đường xử lý dự phòng.

## 9. Fallback không thay thế ErrorDecoder

Feign ErrorDecoder chuyển response HTTP không thành công thành exception. Fallback hoặc fallbackFactory xử lý khi exception đi ra khỏi lời gọi được bảo vệ.

Hai thành phần có trách nhiệm khác nhau:

- ErrorDecoder quyết định response HTTP nào được biểu diễn thành exception và loại exception nào được tạo ra.
- FallbackFactory nhận nguyên nhân thất bại đã đi qua lớp gọi và tạo đối tượng phản hồi thay thế.
- Circuit Breaker ghi nhận kết quả của lời gọi theo chính sách và thứ tự tích hợp.
- Tầng nghiệp vụ quyết định có chấp nhận dữ liệu suy giảm hay phải trả lỗi cho người dùng.

Ví dụ ErrorDecoder tùy chỉnh có thể giữ thông tin status:

~~~java
import feign.Response;
import feign.codec.ErrorDecoder;

public class PartnerErrorDecoder implements ErrorDecoder {

    @Override
    public Exception decode(String methodKey, Response response) {
        return new PartnerServiceException(
                methodKey,
                response.status(),
                "Partner service returned an unsuccessful response"
        );
    }
}
~~~

Sau đó, fallbackFactory có thể tìm PartnerServiceException trong cause chain để đọc status và chọn phản hồi phù hợp. Cấu hình ErrorDecoder cần được gắn với đúng Feign client theo cơ chế cấu hình Spring Cloud OpenFeign.

Không nên chuyển mọi HTTP status thành cùng một exception không có ngữ cảnh. Giữ status hoặc mã lỗi có cấu trúc giúp fallback và monitoring phân biệt được lỗi nghiệp vụ với lỗi hạ tầng.

## 10. Fallback và Circuit Breaker metric

Fallback có thể giúp caller nhận phản hồi có kiểm soát, nhưng không nên làm dashboard che khuất sự cố dependency. Cần phân biệt:

- Lời gọi remote thành công.
- Lời gọi remote thất bại và fallback được sử dụng.
- Lời gọi bị từ chối vì Circuit Breaker đang OPEN.
- Fallback tự phát sinh lỗi.

Theo dõi riêng số lần fallback và nguyên nhân giúp nhóm vận hành biết tỷ lệ request được phục vụ bằng dữ liệu suy giảm. Một API có thể vẫn trả HTTP 200 cho caller nhờ cache, trong khi dependency phía sau đã lỗi trong thời gian dài.

Fallback cũng cần có giới hạn thời gian và tài nguyên. Nếu fallback truy vấn một cache hoặc cơ sở dữ liệu khác, đường dự phòng đó có thể trở thành một dependency mới. Nên ưu tiên dữ liệu đã có sẵn, thao tác nhẹ và có chính sách bảo vệ phù hợp.

Không nên ghi toàn bộ response body, token hoặc thông tin cá nhân vào log khi lưu nguyên nhân. Ghi loại exception, status, client ID, operation ID và correlation ID thường đủ để điều tra mà không làm lộ dữ liệu không cần thiết.

## 11. Những lỗi thường gặp khi khai báo fallback

- **Quên bật Circuit Breaker support**: fallback không được kích hoạt theo tích hợp OpenFeign nếu property chưa bật hoặc starter không có.
- **Fallback class không triển khai đúng interface**: kiểu trả về và chữ ký phương thức phải khớp Feign client.
- **Fallback bean không nằm trong phạm vi Spring scan**: framework không thể tạo bean fallback.
- **FallbackFactory không triển khai đúng generic**: generic phải là interface Feign client tương ứng.
- **Cho rằng Throwable luôn là exception gốc**: nguyên nhân có thể được bọc nhiều lớp; cần duyệt cause chain.
- **Dựa vào message để phân loại**: message không ổn định bằng loại exception hoặc mã lỗi.
- **Gọi lại Feign client trong fallback**: có thể tạo vòng lặp và tiếp tục gây tải lên dependency lỗi.
- **Trả dữ liệu giả như dữ liệu mới**: tầng nghiệp vụ có thể đưa ra quyết định sai.
- **Không phân biệt HTTP 404 với lỗi hạ tầng**: response có thể biểu diễn kết quả nghiệp vụ bình thường.
- **Fallback làm che giấu metric lỗi**: cần theo dõi riêng fallback và trạng thái Circuit Breaker.
- **Khai báo cả fallback và fallbackFactory cho cùng client**: chọn một cơ chế thay thế phù hợp.
- **Dùng fallback như cơ chế retry**: fallback không tự thử lại thao tác chính.

## 12. Quy trình triển khai và kiểm chứng

Khi tích hợp fallback hoặc fallbackFactory cho một Feign client, có thể thực hiện theo trình tự:

1. Thêm Spring Cloud OpenFeign và Circuit Breaker implementation tương thích với phiên bản Spring Boot.
2. Bật spring.cloud.openfeign.circuitbreaker.enabled.
3. Khai báo Feign interface với fallback hoặc fallbackFactory.
4. Đảm bảo lớp fallback hoặc factory là bean Spring và triển khai đúng interface.
5. Nếu cần phân loại lỗi, triển khai fallbackFactory và duyệt cause chain an toàn.
6. Cấu hình ErrorDecoder nếu cần chuyển response HTTP cụ thể thành exception có cấu trúc.
7. Xây dựng fallback có ý nghĩa nghiệp vụ, không gọi lại dependency đang lỗi và không trả dữ liệu giả.
8. Kiểm thử các trường hợp thành công, timeout, lỗi HTTP, lỗi kết nối và Circuit Breaker OPEN.
9. Xác minh caller nhận đúng kiểu dữ liệu hoặc lỗi, đồng thời metric ghi nhận đúng số lần fallback.
10. Theo dõi nguyên nhân lỗi và tỷ lệ fallback trong môi trường chạy thực tế.

fallback phù hợp khi cần một triển khai thay thế đơn giản. fallbackFactory phù hợp khi cần đọc Throwable để phân loại nguyên nhân, ghi log có ngữ cảnh hoặc chọn dữ liệu suy giảm theo loại lỗi. Khi bật Circuit Breaker cho OpenFeign, khai báo đúng bean và kiểm thử từng tình huống, ứng dụng có thể duy trì phản hồi có kiểm soát mà vẫn giữ được khả năng quan sát sự cố của dịch vụ phụ thuộc.
