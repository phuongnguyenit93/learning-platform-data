# Vai trò của CircuitBreaker filter trên ranh giới Gateway

## Gateway là ranh giới bảo vệ phía trước dịch vụ

Trong kiến trúc microservices, Spring Cloud Gateway tiếp nhận request từ client, chọn route và chuyển tiếp request đến dịch vụ phía sau. Nếu một dịch vụ phụ thuộc chậm hoặc không khả dụng, Gateway có thể tiếp tục nhận lượng request lớn và chuyển chúng đến một dependency đang suy giảm. Các request đó giữ connection, tăng latency và có thể làm sự cố lan rộng sang những thành phần khác.

CircuitBreaker GatewayFilter đặt một lớp bảo vệ ngay trên route. Filter dùng Spring Cloud Circuit Breaker để quan sát kết quả chuyển tiếp đến dịch vụ đích. Khi tỷ lệ lỗi đạt ngưỡng, breaker mở và Gateway từ chối các lời gọi mới đến route đó trong thời gian bảo vệ. Nếu được cấu hình, Gateway chuyển request sang một URI fallback để trả phản hồi thay thế.

Vai trò chính của filter là bảo vệ ranh giới định tuyến:

- Giảm số request tiếp tục đi vào một dịch vụ đang lỗi.
- Giảm thời gian chờ của request mới khi breaker đã `OPEN`.
- Cho phép Gateway trả phản hồi có cấu trúc hoặc chuyển sang một luồng xử lý dự phòng.
- Tạo một điểm quan sát tập trung theo route hoặc theo dependency phía sau.

Gateway filter không sửa lỗi ở dịch vụ đích và cũng không đảm bảo mọi lời gọi nội bộ trong hệ thống đều được bảo vệ. Một dịch vụ vẫn có thể cần Circuit Breaker riêng khi gọi database, message broker hoặc một microservice khác.

## Luồng xử lý của CircuitBreaker filter

Với một route được cấu hình CircuitBreaker, luồng xử lý khái quát như sau:

1. Client gửi request đến Gateway.
2. Predicate của route chọn route phù hợp, ví dụ `/catalog/**`.
3. GatewayFilterChain thực hiện lời gọi chuyển tiếp đến `catalog-service` bên trong reactive circuit breaker.
4. Filter ghi nhận kết quả thành công, exception hoặc HTTP status được cấu hình là lỗi.
5. Khi failure rate vượt ngưỡng sau khi đủ số lời gọi tối thiểu, breaker chuyển sang `OPEN`.
6. Trong trạng thái `OPEN`, lời gọi mới bị từ chối trước khi được chuyển tiếp đến dịch vụ đích; Gateway có thể chuyển request đến fallback URI.
7. Sau thời gian chờ, breaker có thể vào `HALF_OPEN` để cho phép một số lời gọi thử nghiệm và đánh giá khả năng phục hồi.

Filter thường sử dụng `ReactiveCircuitBreakerFactory`, vì Spring Cloud Gateway hoạt động trên WebFlux và Reactor. Do đó, ứng dụng cần starter Circuit Breaker reactive phù hợp với provider đã chọn. Không nên đưa một lời gọi blocking vào filter chain hoặc gọi `block()` để chờ kết quả trên event-loop.

## Dependency cần thiết

Với Gateway reactive dùng Resilience4j, ứng dụng thường cần starter Gateway và starter Circuit Breaker Reactor Resilience4j. Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
```

Quản lý phiên bản Spring Boot và Spring Cloud bằng BOM tương thích. Tên artifact và cách đóng gói Gateway có thể thay đổi giữa các release train; hãy dùng dependency management của đúng phiên bản dự án và kiểm tra runtime dependency graph. Nếu ứng dụng dùng provider khác, chọn starter reactive tương ứng thay vì thêm Resilience4j chỉ vì ví dụ này sử dụng nó.

## Khai báo CircuitBreaker filter trên route

Ví dụ route đến dịch vụ danh mục qua service discovery:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: lb://catalog-service
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogGateway
                fallbackUri: forward:/fallback/catalog
                statusCodes:
                  - "500"
                  - "502"
                  - "503"
                  - "504"
```

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò |
| --- | --- |
| `name` | Tên Circuit Breaker được tạo qua factory. Đây cũng là định danh để liên kết với cấu hình và metrics của provider. |
| `fallbackUri` | URI được dùng khi lời gọi thất bại hoặc breaker từ chối. Với Gateway filter, dạng thường dùng là `forward:/...` để chuyển nội bộ đến handler trong chính ứng dụng Gateway. |
| `statusCodes` | Danh sách HTTP status của response phía sau được xem là lỗi để Circuit Breaker ghi nhận. |

`lb://catalog-service` yêu cầu có thành phần load balancing và service discovery phù hợp. Nếu route dùng URI cố định như `http://localhost:8081`, phần cấu hình CircuitBreaker vẫn hoạt động nhưng không cần load balancer cho route đó.

Các status `500`, `502`, `503` và `504` trong ví dụ được chọn vì thường biểu thị lỗi xử lý hoặc khả năng phục vụ của dependency. Không nên tự động xem mọi mã 4xx là lỗi hạ tầng. `400` có thể là request không hợp lệ, `401` hoặc `403` có thể là vấn đề xác thực và phân quyền, còn `404` có thể là kết quả nghiệp vụ bình thường. Chỉ thêm status vào `statusCodes` khi hợp đồng API xác định nó là tín hiệu cần mở mạch.

## Cấu hình ngưỡng Resilience4j theo tên filter

Khi dùng Resilience4j provider, tên trong `name` có thể được dùng để khai báo instance Circuit Breaker:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogGateway:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Với cấu hình này, Circuit Breaker đánh giá tối đa 20 kết quả gần nhất và chỉ bắt đầu tính tỷ lệ khi đã có ít nhất 10 lời gọi được ghi nhận. Nếu failure rate đạt hoặc vượt 50%, breaker có thể chuyển sang `OPEN`. Sau 15 giây, nó có thể chuyển sang `HALF_OPEN` và cho phép tối đa ba lời gọi thử nghiệm theo chính sách của Resilience4j.

Tên instance phải khớp chính xác với `catalogGateway` trong route filter. Nếu tên không khớp, filter có thể dùng cấu hình mặc định hoặc instance khác theo cách provider tạo breaker. Khi điều tra cấu hình, hãy kiểm tra ID mà factory nhận và metrics được xuất theo ID đó.

## Tạo fallback handler trong Gateway

`fallbackUri: forward:/fallback/catalog` chuyển tiếp nội bộ đến một handler trong ứng dụng Gateway. Ví dụ controller reactive trả status 503 cùng payload có ý nghĩa:

```java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GatewayFallbackController {

    @RequestMapping("/fallback/catalog")
    public Mono<ResponseEntity<Map<String, String>>> catalogFallback() {
        Map<String, String> body = Map.of(
            "code", "CATALOG_TEMPORARILY_UNAVAILABLE",
            "message", "Dịch vụ danh mục hiện chưa thể xử lý yêu cầu."
        );

        return Mono.just(ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(body));
    }
}
```

Fallback endpoint là một phần của ứng dụng Gateway, không phải endpoint của dịch vụ danh mục. Nó cần được thiết kế để không gọi ngược lại route đang lỗi. Nếu handler gọi lại cùng dependency qua một route khác, fallback có thể tạo vòng lặp hoặc tiếp tục dồn tải vào dịch vụ đang suy giảm.

Trả HTTP 503 trong ví dụ giúp client hiểu rằng dịch vụ tạm thời không khả dụng. Không nên luôn trả HTTP 200 chỉ để tránh lỗi hiển thị; điều đó khiến client, monitoring và hệ thống retry hiểu sai kết quả. Nếu có dữ liệu cache hợp lệ hoặc một phương án thay thế nghiệp vụ, handler có thể trả kết quả tương ứng nhưng cần thể hiện rõ độ mới và trạng thái của dữ liệu.

## CircuitBreaker filter xử lý lỗi nào?

Có hai nhóm tín hiệu chính:

- **Exception từ quá trình chuyển tiếp:** lỗi kết nối, timeout hoặc exception do HTTP client phát ra có thể được đưa vào Circuit Breaker theo chính sách provider.
- **HTTP status từ response:** các status khai báo trong `statusCodes` được filter xem là lỗi để Circuit Breaker đánh giá.

Một response 500 không nhất thiết tự trở thành exception ở mọi HTTP client hoặc mọi filter chain. `statusCodes` cho Gateway biết những response status nào cần được xem là lỗi. Ngược lại, một status 404 không nằm trong danh sách thường được xem là response bình thường đối với Circuit Breaker, dù ứng dụng vẫn có thể trả 404 cho client.

Việc phân loại status phải phù hợp với nghiệp vụ. Ví dụ, nếu dịch vụ danh mục trả 404 khi sản phẩm không tồn tại, mở mạch vì 404 có thể chặn cả các request hợp lệ khác. Nếu một API trả 429 khi bị giới hạn lưu lượng, đội vận hành có thể muốn xem đó là dấu hiệu quá tải và đưa vào danh sách lỗi. Hãy thống nhất cách hiểu giữa Gateway, client và dịch vụ phía sau.

## Phạm vi của breaker: theo route và failure domain

Circuit Breaker ở Gateway thường đại diện cho một dependency hoặc một route. Tất cả request đi qua cùng breaker name chia sẻ cửa sổ thống kê và trạng thái trong cùng tiến trình Gateway. Nếu hai route có failure domain khác nhau nhưng dùng chung một tên breaker, lỗi ở route này có thể làm route kia bị mở mạch theo cùng trạng thái.

Ví dụ:

| Route | Dependency | Tên breaker gợi ý |
| --- | --- | --- |
| `/catalog/**` | `catalog-service` | `catalogGateway` |
| `/orders/**` | `order-service` | `orderGateway` |
| `/profiles/**` | `profile-service` | `profileGateway` |

Đặt tên riêng giúp cấu hình ngưỡng, theo dõi metrics và điều tra sự cố theo dependency. Chỉ chia sẻ tên khi các route thực sự nên dùng chung một chính sách và cùng failure domain.

Trạng thái Resilience4j thường nằm trong bộ nhớ của từng tiến trình Gateway. Nếu Gateway chạy nhiều replica, mỗi replica có thể có cửa sổ và trạng thái breaker riêng; không nên giả định mọi replica chuyển sang `OPEN` cùng một thời điểm. Vì vậy, metrics cần được tổng hợp theo instance và route, còn giới hạn lưu lượng toàn hệ thống cần tính đến số replica.

## Vị trí Gateway filter trong hệ thống bảo vệ nhiều lớp

Gateway Circuit Breaker bảo vệ request từ bên ngoài trước khi chúng đi vào dịch vụ. Nó không thay thế Circuit Breaker bên trong từng service. Một request có thể đi qua Gateway, vào `order-service`, rồi từ đó gọi `payment-service`. Nếu Gateway chỉ bảo vệ route đến `order-service`, lỗi ở lời gọi nội bộ từ order sang payment vẫn cần được xử lý trong `order-service`.

Có thể hình dung các lớp như sau:

```text
Client
  |
  v
Spring Cloud Gateway
  |  CircuitBreaker filter cho route
  v
Order Service
  |  CircuitBreaker cho dependency nội bộ
  v
Payment Service
```

Gateway cũng không tự giới hạn số request đồng thời như Bulkhead. Khi cần giới hạn concurrency hoặc bảo vệ connection pool, hãy cấu hình Bulkhead hoặc giới hạn tài nguyên ở lớp phù hợp. Timeout ở HTTP client hoặc TimeLimiter vẫn cần thiết để lời gọi đang chạy không giữ tài nguyên vô hạn.

## Thứ tự filter, retry và fallback

Gateway cho phép kết hợp nhiều filter trên cùng route, nhưng thứ tự và phạm vi áp dụng có thể ảnh hưởng kết quả. Nếu dùng Retry cùng CircuitBreaker, cần xác định rõ một request nghiệp vụ có thể tạo bao nhiêu lần thử đến dependency. Retry có thể làm tăng tải trong lúc dịch vụ đang suy giảm; Circuit Breaker nên quan sát đúng kết quả theo chính sách dự kiến.

Không nên thêm nhiều lớp Retry quanh một route mà không giới hạn số lần, backoff và deadline. Cần kiểm tra thứ tự filter trong đúng phiên bản Gateway, sau đó thử các trường hợp response 5xx, exception kết nối, breaker mở và fallback thất bại. Fallback nên là điểm kết thúc có kiểm soát, không phải một route khác quay lại cùng dependency.

## Quan sát CircuitBreaker filter

Theo dõi riêng trạng thái Circuit Breaker và kết quả mà client nhận được. Các chỉ số hữu ích gồm:

- Trạng thái breaker theo tên route: `CLOSED`, `OPEN` hoặc `HALF_OPEN`.
- Số lời gọi được ghi nhận, thành công, thất bại và bị từ chối khi mạch mở.
- Failure rate, slow-call rate và số lời gọi thử ở `HALF_OPEN`.
- Số lần Gateway chuyển sang fallback và số lần fallback handler tự thất bại.
- Latency của route chính và latency của fallback.
- HTTP status cuối cùng trả về client.

HTTP 503 do fallback tạo ra không cho biết chắc breaker đang mở hay supplier vừa gặp timeout. Muốn biết nguyên nhân, hãy đối chiếu event của Resilience4j, log của Gateway và trace của request. Dùng breaker name và route ID làm nhãn có giới hạn; tránh đưa URL đầy đủ, ID người dùng hoặc exception message vào metric tag.

Nếu dùng Spring Boot Actuator và Micrometer, kiểm tra endpoint metrics/health đã được bật và bảo vệ đúng cách. Không công khai endpoint quản trị chỉ để xem trạng thái Circuit Breaker. Log nên ghi nhận route, breaker name, loại lỗi và correlation ID nhưng tránh ghi token, cookie hoặc dữ liệu nhạy cảm trong request.

## Kiểm thử Gateway CircuitBreaker

Nên kiểm thử trên Gateway chạy thật với một dịch vụ đích giả lập có thể trả status hoặc trì hoãn phản hồi. Các trường hợp tối thiểu:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Dependency trả 200 | Response đi qua bình thường; breaker ghi nhận thành công. |
| Dependency trả 503 và status được khai báo | Breaker ghi nhận lỗi và fallback được gọi theo cấu hình. |
| Dependency trả 404 không nằm trong `statusCodes` | 404 được chuyển về client và không bị tính lỗi chỉ vì là 4xx. |
| Không kết nối được dependency | Exception được ghi nhận theo chính sách provider và fallback hoạt động. |
| Breaker đã `OPEN` | Request mới không được chuyển tiếp đến dependency; fallback URI được sử dụng nếu đã cấu hình. |
| Fallback handler trả 503 | Client nhận status có ý nghĩa; metric fallback response tăng. |
| Fallback handler cũng lỗi | Lỗi fallback được quan sát riêng, không tạo vòng lặp route. |
| Nhiều Gateway replica | Xác nhận trạng thái breaker có thể khác nhau giữa các tiến trình và metrics được gắn instance phù hợp. |

Khi kiểm thử, đừng chỉ kiểm tra body fallback. Hãy xác nhận số request thực sự đến dependency, trạng thái breaker, số lần bị từ chối và status cuối cùng. Điều này giúp phân biệt filter đang bảo vệ dependency với một controller fallback chỉ tình cờ trả response.

## Các lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Thiếu reactive Circuit Breaker starter hoặc provider | Gateway không tạo được reactive factory hoặc filter không hoạt động như mong đợi. | Kiểm tra starter, runtime classpath và auto-configuration. |
| `name` không khớp instance cấu hình | Breaker dùng cấu hình mặc định hoặc sai chính sách. | Đối chiếu tên filter với tên instance Resilience4j. |
| Không khai báo `statusCodes` cho status cần bảo vệ | Response lỗi có thể không được tính là lỗi theo chính sách mong muốn. | Liệt kê status dựa trên hợp đồng API. |
| Coi mọi 4xx là lỗi dependency | Request sai hoặc kết quả nghiệp vụ có thể làm mở mạch. | Chỉ ghi nhận status thực sự biểu thị sự cố dependency. |
| Fallback gọi lại route đang lỗi | Tạo vòng lặp hoặc tiếp tục tăng tải lên dependency. | Dùng handler nội bộ hoặc nguồn dự phòng độc lập. |
| Dùng chung breaker name cho các failure domain khác nhau | Lỗi một dependency ảnh hưởng route không liên quan. | Tách breaker theo dependency hoặc nhóm route có chủ đích. |
| Chỉ theo dõi status cuối cùng | Fallback có thể che mất sự cố phía sau Gateway. | Theo dõi đồng thời metrics breaker, primary route và fallback. |

CircuitBreaker GatewayFilter tạo một lớp bảo vệ hữu ích tại ranh giới vào hệ thống: nó giảm request chuyển đến dependency đang suy giảm và cho phép Gateway trả phản hồi dự phòng có kiểm soát. Để lớp bảo vệ này hoạt động đúng, cần chọn breaker name theo failure domain, phân loại status phù hợp, cấu hình fallback không tạo vòng lặp và quan sát riêng kết quả đường chính với kết quả fallback. Các service phía sau vẫn cần bảo vệ những dependency nội bộ của chính chúng.
