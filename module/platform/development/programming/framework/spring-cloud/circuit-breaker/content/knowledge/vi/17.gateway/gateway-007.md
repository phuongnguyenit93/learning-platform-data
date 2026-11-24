# Ranh giới phối hợp với Retry filter, timeout và LoadBalancer

Spring Cloud Gateway là điểm tiếp nhận request từ client và định tuyến đến các dịch vụ phía sau. Tại gateway, một request có thể đi qua nhiều filter: xác thực, định tuyến, cân bằng tải, retry, circuit breaker và các bộ giới hạn thời gian. Cách phối hợp các filter quyết định request được thử lại bao nhiêu lần, lỗi nào được ghi nhận, thời gian client phải chờ và liệu một lần thử mới có thể được gửi đến instance khác hay không.

Gateway cần bảo vệ hệ thống ở ranh giới vào, nhưng các dịch vụ phía sau vẫn cần bảo vệ riêng cho những lời gọi mà chúng thực hiện. Vì vậy, cần phân biệt chính sách retry của Gateway với retry của Spring Cloud LoadBalancer và retry trong service; đồng thời đặt timeout sao cho tổng thời gian xử lý không vượt quá ngân sách phản hồi của client.

Bài học tập trung vào ranh giới phối hợp giữa Gateway Retry filter, CircuitBreaker filter, timeout của HTTP client và LoadBalancer. Các ví dụ dùng Spring Cloud Gateway reactive và Resilience4j làm provider Circuit Breaker.

## 1. Gateway filter chain là nơi các chính sách gặp nhau

Một request đi qua Gateway thường có luồng tổng quát như sau:

~~~text
Client
  |
  v
Spring Cloud Gateway
  |
  +--> Global filters
  |
  +--> Route filters
  |      |
  |      +--> Authentication / authorization
  |      +--> CircuitBreaker
  |      +--> Retry
  |      +--> HTTP routing
  |
  v
LoadBalancer: chọn service instance
  |
  v
HTTP client: connect timeout / response timeout
  |
  v
Service instance
~~~

Gateway kết hợp GlobalFilter và GatewayFilter của route thành một chuỗi thực thi. Filter ở phía trước có thể xử lý request trước khi gọi filter tiếp theo; sau khi filter phía sau hoàn tất, luồng xử lý quay ngược lại để xử lý response hoặc exception.

Thứ tự thực tế phụ thuộc vào thứ tự filter sau khi được sắp xếp. Route filter thường được khai báo theo danh sách trong route, nhưng GlobalFilter và filter có thứ tự riêng cũng tham gia chuỗi. Khi thay đổi thứ tự Retry và CircuitBreaker, cần kiểm tra effective filter order của phiên bản Gateway đang chạy thay vì chỉ dựa vào cách đọc YAML.

Mỗi chính sách nên có một trách nhiệm rõ ràng:

- Retry quyết định có gửi lại một request khi gặp lỗi có thể phục hồi hay không.
- Circuit Breaker quyết định có tiếp tục cho request đi đến dependency khi dependency có dấu hiệu không khỏe hay không.
- Timeout giới hạn thời gian một lần kết nối hoặc chờ phản hồi.
- LoadBalancer chọn service instance đích và có thể áp dụng chính sách retry riêng ở cấp instance.

## 2. Retry filter của Spring Cloud Gateway

Retry GatewayFilter cho phép Gateway thực hiện lại request khi response có status hoặc exception thuộc nhóm được cấu hình. Filter hỗ trợ giới hạn số lần retry, HTTP method, status code, status series, exception và backoff.

Ví dụ route chỉ retry request GET khi dịch vụ trả lỗi server:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          filters:
            - name: Retry
              args:
                retries: 2
                methods:
                  - GET
                series:
                  - SERVER_ERROR
                statuses:
                  - BAD_GATEWAY
                  - SERVICE_UNAVAILABLE
                  - GATEWAY_TIMEOUT
                exceptions:
                  - java.io.IOException
                  - java.util.concurrent.TimeoutException
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

Trong ví dụ, retries bằng 2 nghĩa là tối đa hai lần retry sau lần gọi ban đầu, tức tối đa ba lần thử. Backoff bắt đầu ở 100 ms và tăng theo hệ số 2, nhưng không vượt quá 500 ms. Các giá trị chỉ là ví dụ để thực hành; cần chọn theo latency budget và khả năng chịu tải của dịch vụ.

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| retries | Số lần retry sau lần gọi ban đầu |
| methods | Các HTTP method được phép retry |
| series | Nhóm status series được retry, ví dụ SERVER_ERROR |
| statuses | Các HTTP status cụ thể được retry |
| exceptions | Các exception được retry |
| backoff.firstBackoff | Thời gian chờ trước lần retry đầu |
| backoff.maxBackoff | Giới hạn thời gian backoff |
| backoff.factor | Hệ số tăng thời gian chờ |
| backoff.basedOnPreviousValue | Cách tính backoff tiếp theo dựa trên giá trị trước đó |

Gateway Retry thường phù hợp với GET hoặc các thao tác đã có cơ chế idempotency. Không nên retry POST, PATCH hoặc request ghi dữ liệu chỉ vì thấy lỗi 5xx. Server có thể đã thực hiện thao tác nhưng response bị mất trên đường về; gửi lại có thể tạo đơn hàng hoặc giao dịch trùng lặp.

Nếu cần retry request có body, phải xem xét cách Gateway lưu và phát lại body. Việc giữ body có thể tiêu thụ bộ nhớ, đặc biệt với request lớn hoặc lưu lượng cao. Hãy giới hạn kích thước request, số lần retry và chỉ bật cho API có quy tắc idempotency rõ ràng.

## 3. CircuitBreaker filter ở Gateway

Spring Cloud Gateway cung cấp CircuitBreaker GatewayFilter để bọc lời gọi đến route bằng abstraction Spring Cloud CircuitBreaker. Với Resilience4j provider, tên trong filter được liên kết với cấu hình Circuit Breaker tương ứng.

Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
                statusCodes:
                  - 500
                  - 502
                  - 503
                  - 504
~~~

Tên inventory là tên Circuit Breaker instance. Có thể cấu hình ngưỡng trong application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Danh sách statusCodes cho Gateway CircuitBreaker filter chỉ định các HTTP status cần được xem là lỗi. Nếu không cấu hình các status phù hợp, một response HTTP 5xx có thể được xem là một response hoàn tất bình thường ở tầng reactive, tùy đường xử lý và provider. Hãy cấu hình rõ các status nghiệp vụ cần tính vào failure rate.

Fallback URI dạng forward:/... chuyển request nội bộ đến handler trong chính ứng dụng Gateway. Ví dụ controller fallback:

~~~java
package com.example.gateway.fallback;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
public class InventoryFallbackController {

    @GetMapping("/fallback/inventory")
    public Mono<ResponseEntity<Map<String, String>>> inventoryFallback() {
        return Mono.just(
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                    "service", "inventory",
                    "status", "temporarily_unavailable"
                ))
        );
    }
}
~~~

Fallback nên trả thông tin có ý nghĩa cho client và không tiết lộ stack trace, hostname nội bộ hoặc thông tin nhạy cảm. Nếu nghiệp vụ cho phép, fallback có thể trả dữ liệu cache hoặc một response suy giảm. Nếu không thể đưa ra kết quả an toàn, hãy trả lỗi có kiểm soát.

## 4. Thứ tự Retry và CircuitBreaker làm thay đổi mẫu thống kê

Retry và CircuitBreaker có thể được lồng theo hai hướng. Filter order quyết định Circuit Breaker ghi nhận từng attempt hay kết quả cuối cùng của cả chuỗi retry.

### 4.1. Retry ở ngoài, CircuitBreaker ở trong

~~~text
Request
  |
  v
Retry filter
  |
  +--> attempt 1 --> CircuitBreaker --> service
  |
  +--> attempt 2 --> CircuitBreaker --> service
  |
  +--> attempt 3 --> CircuitBreaker --> service
~~~

Khi Retry filter nằm trước CircuitBreaker filter trong effective chain, Retry bao phần xử lý phía sau và có thể chạy lại chuỗi đó. Mỗi attempt đi qua Circuit Breaker, nên mỗi kết quả attempt có thể trở thành một mẫu trong sliding window.

Cách này phản ánh sức khỏe dependency theo từng lần thử. Một request logic có ba attempt thất bại có thể tạo ba mẫu failure. Circuit Breaker có thể đạt minimumNumberOfCalls nhanh hơn, nhưng failure rate không còn tương đương với tỷ lệ request người dùng thất bại.

Cần chú ý đến CallNotPermittedException. Khi Circuit Breaker đã OPEN, attempt tiếp theo có thể bị từ chối ngay. Không nên cấu hình Retry bắt mọi exception và tiếp tục thử CallNotPermittedException, vì request đã bị cơ chế bảo vệ từ chối và không có ích khi gửi lại ngay.

### 4.2. CircuitBreaker ở ngoài, Retry ở trong

~~~text
Request
  |
  v
CircuitBreaker filter
  |
  v
Retry filter
  |
  +--> attempt 1 --> service
  |
  +--> attempt 2 --> service
  |
  +--> attempt 3 --> service
  |
  v
Kết quả cuối cùng
~~~

Khi CircuitBreaker filter nằm trước Retry filter trong effective chain, Circuit Breaker bao toàn bộ chuỗi retry. Nó ghi nhận một kết quả sau khi Retry kết thúc.

Nếu attempt đầu thất bại nhưng attempt thứ hai thành công, Circuit Breaker nhận một kết quả thành công. Nếu tất cả attempt thất bại, Circuit Breaker ghi một failure. Cách này gần với tỷ lệ request logic thất bại cuối cùng.

Cách này cũng khiến Circuit Breaker đo tổng thời gian của các attempt và backoff. Một request có thể bị xem là slow call dù từng attempt riêng lẻ đều nhanh.

### 4.3. Chọn thứ tự theo mục tiêu

| Mục tiêu | Thứ tự nên cân nhắc |
| --- | --- |
| Thống kê lỗi theo từng lần gọi đến service | Retry ngoài, CircuitBreaker trong |
| Thống kê kết quả cuối cùng của request logic | CircuitBreaker ngoài, Retry trong |
| Đo latency người dùng phải chờ gồm cả backoff | CircuitBreaker ngoài, Retry trong |
| Phản ứng nhanh khi các attempt liên tục thất bại | Retry ngoài, CircuitBreaker trong |

Khi có fallback, cần tính đến vị trí của fallback trong chuỗi. Nếu CircuitBreaker ở trong Retry và fallback biến lỗi thành response thành công, Retry có thể xem attempt đó là hoàn tất và không thử lại. Nếu muốn Retry xử lý lỗi trước rồi mới trả fallback, hãy đặt fallback ở ranh giới bên ngoài chuỗi retry hoặc thiết kế status/exception để Retry nhận biết đúng lỗi.

## 5. Timeout của Gateway HTTP client

Timeout giới hạn thời gian Gateway chờ kết nối và phản hồi từ dịch vụ phía sau. Nó là cơ chế trực tiếp giải phóng request đang chờ khi dependency bị treo hoặc phản hồi quá chậm.

Có hai loại timeout thường cần cấu hình:

- **Connect timeout:** thời gian tối đa để thiết lập kết nối đến service instance.
- **Response timeout:** thời gian tối đa chờ response từ kết nối đã thiết lập.

Cấu hình toàn cục:

~~~yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 1000
        response-timeout: 2s
~~~

Connect timeout ở ví dụ là 1000 ms. Response timeout là 2 giây.

Có thể đặt timeout riêng cho route bằng metadata:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          metadata:
            connect-timeout: 300
            response-timeout: 800
~~~

Các giá trị metadata connect-timeout và response-timeout ở ví dụ được tính bằng millisecond. Hãy kiểm tra quy tắc cấu hình theo phiên bản Spring Cloud Gateway đang sử dụng.

Timeout của HTTP client giới hạn một lần trao đổi với service. Nếu Retry chạy nhiều lần, tổng thời gian xử lý request có thể dài hơn response-timeout vì mỗi attempt có thể tiêu thụ một khoảng timeout riêng và còn có backoff giữa các lần thử.

Ví dụ với hai lần retry, mỗi attempt có thể chờ tối đa 800 ms, backoff 100 ms và 200 ms:

\[
3 \times 800\text{ ms} + 100\text{ ms} + 200\text{ ms}
= 2{,}700\text{ ms}
\]

Tổng thời gian thực tế còn có thể bao gồm thời gian chọn instance, xử lý filter, serialization và các chi phí khác. Do đó, cần đặt deadline tổng thể ở client hoặc ingress phù hợp với latency budget của API.

## 6. Phân biệt timeout với slow-call threshold

Timeout và slow-call threshold có quan hệ nhưng không thay thế nhau.

| Cơ chế | Vai trò |
| --- | --- |
| HTTP connect timeout | Dừng chờ khi không thể thiết lập kết nối trong thời gian cho phép |
| HTTP response timeout | Giới hạn thời gian chờ phản hồi ở HTTP client |
| Circuit Breaker slowCallDurationThreshold | Đánh dấu lời gọi hoàn tất nhưng mất quá nhiều thời gian |
| Circuit Breaker failureRateThreshold | Mở mạch khi tỷ lệ lỗi đạt ngưỡng |
| Retry backoff | Chờ giữa các lần thử lại |

Slow-call threshold chỉ dùng để phân loại lời gọi khi Circuit Breaker đánh giá kết quả. Nó không tự hủy HTTP request hoặc thay thế response timeout. Nếu HTTP client không có timeout phù hợp, lời gọi có thể giữ tài nguyên quá lâu trước khi Circuit Breaker nhận được kết quả để ghi nhận.

Khi timeout xảy ra, exception từ HTTP client có thể được Circuit Breaker ghi nhận là failure. Cần kiểm tra exception thực tế và cấu hình record/ignore exception để phân loại lỗi đúng. Timeout ở gateway cũng không đảm bảo service phía sau đã hủy công việc; server có thể vẫn đang xử lý nếu cancellation không được truyền hoặc không được hỗ trợ.

## 7. LoadBalancer và URI lb://

Gateway có thể định tuyến đến một service logical name thay vì hostname cố định:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
~~~

URI lb://inventory-service yêu cầu Spring Cloud LoadBalancer tìm các instance đăng ký dưới service ID inventory-service. Việc chọn instance diễn ra ở runtime dựa trên danh sách instance và chiến lược LoadBalancer được cấu hình.

Ứng dụng thường cần Spring Cloud LoadBalancer starter và một nguồn cung cấp service instance, ví dụ DiscoveryClient hoặc cấu hình instance tĩnh cho môi trường thử nghiệm. Nếu không tìm thấy instance phù hợp, Gateway có thể trả lỗi định tuyến thay vì gọi một host cụ thể.

LoadBalancer và Gateway Retry có ranh giới khác nhau:

- Gateway Retry lặp lại request/filter chain khi response hoặc exception khớp điều kiện retry.
- LoadBalancer Retry tập trung vào việc thử lại khi chọn hoặc gọi service instance, có thể theo chính sách thử lại cùng instance hay instance khác.
- Retry trong service áp dụng cho lời gọi do chính service thực hiện đến dependency tiếp theo.

Không nên giả định rằng mỗi lần Gateway Retry chắc chắn chọn một instance mới. Việc filter LoadBalancer có được chạy lại và cách chọn instance phụ thuộc effective filter order cùng cơ chế tích hợp. Nếu yêu cầu là thử một instance khác sau khi instance hiện tại lỗi, hãy cấu hình và kiểm thử chính sách retry của Spring Cloud LoadBalancer thay vì dựa vào Gateway Retry.

## 8. Tránh nhân số lần retry giữa Gateway và LoadBalancer

Nếu cả Gateway và LoadBalancer đều retry, số lần gọi thực tế có thể lớn hơn số lần được khai báo ở một lớp.

Ví dụ Gateway cho phép hai lần retry sau lần đầu, tức tối đa ba lượt thực thi downstream. Nếu trong mỗi lượt LoadBalancer có thể thực hiện thêm ba lần thử instance, tổng số lần gửi request có thể tăng theo tích số của hai giới hạn:

\[
3 \times 3 = 9 \text{ lần thử tối đa}
\]

Đây là ước lượng cho trường hợp cả hai tầng đều thực hiện đủ số lần thử; hành vi thực tế phụ thuộc điều kiện lỗi, filter order và retry policy.

Để tránh khuếch đại tải:

1. Chọn một tầng chính chịu trách nhiệm retry cho mỗi loại lỗi.
2. Dùng Gateway Retry cho các response/exception mà gateway có thể đánh giá và xử lý an toàn.
3. Dùng LoadBalancer Retry khi mục tiêu cụ thể là thử lại service instance theo chính sách cùng instance hoặc instance kế tiếp.
4. Giới hạn số lần thử ở tất cả các tầng.
5. Đặt backoff và jitter nếu nhiều client có thể retry đồng thời.
6. Tính tổng số attempt và thời gian chờ tối đa trong latency budget.
7. Theo dõi số request logic, số attempt HTTP và số lần đổi service instance riêng biệt.

## 9. Ví dụ phối hợp CircuitBreaker, Retry, timeout và LoadBalancer

Một route Inventory có thể dùng CircuitBreaker bao ngoài Retry để Circuit Breaker thống kê kết quả cuối cùng của request logic. Gateway HTTP client giới hạn thời gian kết nối và chờ phản hồi. URI lb:// cho phép LoadBalancer chọn instance.

~~~yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 500
        response-timeout: 800ms
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
                statusCodes:
                  - 500
                  - 502
                  - 503
                  - 504

            - name: Retry
              args:
                retries: 2
                methods:
                  - GET
                series:
                  - SERVER_ERROR
                statuses:
                  - BAD_GATEWAY
                  - SERVICE_UNAVAILABLE
                  - GATEWAY_TIMEOUT
                exceptions:
                  - java.io.IOException
                  - java.util.concurrent.TimeoutException
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 300ms
                  factor: 2
                  basedOnPreviousValue: false

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Đây là cấu hình minh họa thứ tự CircuitBreaker trước Retry trong danh sách route filter. Hãy xác nhận effective order của filter chain trong phiên bản đang dùng. Với thứ tự này, Circuit Breaker dự kiến bao phần xử lý Retry và nhận kết quả cuối cùng của chuỗi retry. Nếu muốn Circuit Breaker ghi nhận từng attempt, hãy thay đổi thứ tự filter có chủ đích và kiểm tra lại hành vi fallback.

Cấu hình response-timeout 800 ms giới hạn thời gian chờ mỗi lần trao đổi HTTP theo cấu hình Gateway. Hai lần retry và backoff có thể khiến tổng thời gian vượt quá 800 ms. Vì vậy, client gọi Gateway cần có deadline phù hợp với tổng ngân sách, không chỉ sao chép response-timeout của một attempt.

Fallback URI chuyển request nội bộ đến endpoint /fallback/inventory. Nếu Retry không thể khắc phục lỗi, Circuit Breaker nhận kết quả cuối cùng và có thể chuyển sang fallback. Khi Circuit Breaker đang OPEN, request mới có thể được chuyển fallback ngay mà không gọi service instance.

## 10. Fallback và status code cần thống nhất

Fallback ở Gateway là một hợp đồng với client. Hãy quyết định response nào thể hiện dữ liệu suy giảm, response nào báo dependency tạm thời không khả dụng và response nào cần client thử lại sau.

Một số nguyên tắc:

- Không trả HTTP 200 cho dữ liệu không đầy đủ nếu client có thể hiểu nhầm là kết quả chính xác.
- Có thể trả HTTP 503 khi chức năng không thể phục vụ và client có thể thử lại sau.
- Nếu trả dữ liệu cache, cần đánh dấu rõ dữ liệu cũ hoặc trạng thái degraded.
- Không đưa exception message, stack trace hoặc địa chỉ service nội bộ vào response.
- Cấu hình statusCodes của CircuitBreaker filter phù hợp với những status cần tính vào failure rate.
- Không để fallback che mất lỗi trước khi Retry có cơ hội xử lý, nếu mục tiêu là retry trước rồi mới fallback.

Nếu fallback được thực hiện ở một filter nằm bên trong Retry, Retry có thể nhận response fallback như kết quả hoàn tất và không tiếp tục thử. Nếu muốn Retry xử lý các lỗi trước, hãy đặt fallback sau ranh giới retry hoặc đảm bảo response fallback vẫn được Retry nhận diện là điều kiện cần thử lại.

## 11. Bảo vệ request ghi dữ liệu và request có body

Gateway Retry dễ áp dụng hơn cho GET vì thao tác đọc thường có thể lặp lại mà không tạo tác dụng phụ. Với POST hoặc PATCH, không nên retry chỉ dựa trên status 5xx.

Trước khi retry một request ghi dữ liệu, cần có:

- Idempotency key duy nhất cho thao tác nghiệp vụ.
- Cơ chế lưu kết quả xử lý theo idempotency key ở service đích.
- Quy tắc xử lý khi cùng một key được gửi nhiều lần.
- Giới hạn kích thước body và bộ nhớ dùng để replay request.
- Kiểm tra request đã được service đích xử lý trước khi gửi lại.

Nếu không có cơ chế idempotency, một timeout có thể xảy ra sau khi service đã commit giao dịch. Gateway không biết thao tác đã thành công ở server hay chưa. Retry có thể tạo bản ghi hoặc giao dịch thứ hai.

## 12. Theo dõi và chẩn đoán tại ranh giới Gateway

Cần quan sát cả request logic lẫn các attempt bên dưới. Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Request count theo route | Số request client gửi đến Gateway |
| Retry attempts | Số lần Gateway gửi lại request |
| Retry exhaustion | Số request đã hết số lần retry |
| Circuit Breaker state | Tỷ lệ thời gian ở CLOSED, OPEN và HALF_OPEN |
| Circuit Breaker failure/slow-call rate | Chất lượng của supplier được Circuit Breaker bao quanh |
| Timeout count | Số lần connect hoặc response timeout |
| LoadBalancer selected instance | Instance được chọn cho từng attempt |
| Fallback count | Số request được xử lý bằng fallback |
| End-to-end latency | Thời gian client thực sự chờ |

Log nên có route ID, correlation ID, trace ID, service ID và attempt number nếu có. Không ghi Authorization header hoặc access token. Với distributed tracing, dùng HTTP client được instrument để truyền trace context đến service phía sau.

Khi điều tra một request chậm, hãy xác định thời gian bị tiêu thụ ở đâu: chờ chọn instance, connect, response, backoff hay fallback. Một request có tổng latency cao không nhất thiết là do service xử lý chậm; có thể nó đã trải qua nhiều attempt và nhiều khoảng backoff.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request bị gửi quá nhiều lần | Retry được bật ở Gateway, LoadBalancer và service cùng lúc | Chọn tầng retry chính và tính tổng attempt |
| Circuit Breaker mở quá chậm | Circuit Breaker nằm ngoài Retry và chỉ nhận một mẫu sau khi chuỗi retry hoàn tất | Điều chỉnh minimumNumberOfCalls hoặc chọn ranh giới thống kê phù hợp |
| Circuit Breaker mở quá nhanh | Circuit Breaker nằm trong Retry và ghi từng attempt vào sliding window | Đánh giá failure rate ở cấp attempt và điều chỉnh ngưỡng |
| Retry không chạy | Status hoặc exception không khớp cấu hình | Kiểm tra response thực tế, series, statuses, exceptions và methods |
| Fallback chạy trước khi Retry hoàn tất | Fallback nằm bên trong ranh giới Retry | Điều chỉnh filter order hoặc vị trí fallback |
| Request vượt deadline client | Mỗi attempt có timeout riêng và còn backoff | Tính tổng latency budget và đặt deadline tổng thể |
| Không tìm thấy service instance | Sai service ID hoặc discovery chưa cung cấp instance | Kiểm tra URI lb:// và nguồn service instance |
| Retry luôn gọi lại cùng instance | Gateway Retry không có cam kết chọn instance khác | Cấu hình LoadBalancer retry policy và quan sát instance được chọn |
| POST bị tạo giao dịch trùng | Retry request ghi không có idempotency | Dùng idempotency key hoặc không retry thao tác đó |
| HTTP 5xx không làm Circuit Breaker tăng failure rate | Chưa khai báo statusCodes phù hợp trong Gateway CircuitBreaker filter | Thêm các status cần được tính là lỗi |

## 14. Quy trình thiết kế chính sách cho một route

Khi thêm một route mới, có thể thực hiện theo trình tự:

1. Xác định service ID và nguồn discovery mà LoadBalancer sẽ sử dụng.
2. Đặt connect timeout và response timeout theo latency budget của route.
3. Xác định request method nào an toàn để retry.
4. Chọn status và exception có thể phục hồi; giới hạn số retry.
5. Quyết định Circuit Breaker thống kê từng attempt hay kết quả cuối cùng của request.
6. Đặt filter order và fallback phù hợp với mục tiêu đó.
7. Xác định LoadBalancer có cần thử instance khác hay không và tránh nhân retry ngoài ý muốn.
8. Kiểm thử service chậm, service trả 5xx, không có instance, Circuit Breaker OPEN và fallback.
9. Đo request count, attempt count, timeout, fallback và end-to-end latency trước khi triển khai.

Gateway là ranh giới điều phối request giữa client và dịch vụ phía sau. Retry filter xử lý việc thử lại request, timeout giới hạn thời gian chờ, CircuitBreaker filter ngắt request khi dependency không khỏe và LoadBalancer chọn instance đích. Khi xác định rõ trách nhiệm, thứ tự filter, số lần thử và latency budget, Spring Cloud Gateway có thể phục hồi lỗi transient mà không khuếch đại tải hoặc khiến client phải chờ vượt quá thời gian cho phép.

## Tài liệu tham khảo

- [Spring Cloud Gateway reference](https://docs.spring.io/spring-cloud-gateway/reference/)
- [Spring Cloud Gateway Retry GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html)
- [Spring Cloud Gateway CircuitBreaker GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/circuitbreaker-filter.html)
- [Spring Cloud Gateway HTTP timeouts](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/http-timeouts-configuration.html)
- [Spring Cloud LoadBalancer reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)

