# Khai báo tên bộ ngắt mạch và phạm vi từng route

Trong Spring Cloud Gateway, filter **CircuitBreaker** bảo vệ lời gọi từ Gateway đến dịch vụ phía sau. Mỗi route có một **route ID** để định danh tuyến định tuyến, còn filter CircuitBreaker nhận một **name** để chọn instance Circuit Breaker sẽ thực thi. Hai tên này có mục đích khác nhau: route ID xác định cấu hình tuyến, trong khi Circuit Breaker name xác định trạng thái, chính sách và sliding window được chia sẻ bởi các lời gọi đi qua bộ ngắt đó.

Việc đặt tên đúng quyết định phạm vi bảo vệ của Gateway. Nếu nhiều route dùng cùng một Circuit Breaker name, chúng có thể chia sẻ trạng thái CLOSED, OPEN, HALF_OPEN và cùng cửa sổ thống kê. Nếu mỗi route cần chính sách hoặc phạm vi lỗi riêng, hãy đặt tên bộ ngắt riêng và cấu hình Resilience4j theo đúng tên đó. Tên cần ổn định theo dịch vụ phụ thuộc hoặc operation, không thay đổi theo từng request.

## 1. Phân biệt route ID và Circuit Breaker name

Một route trong Gateway thường có ID, URI đích, predicate và các filter. Ví dụ route **catalog-read-route** nhận request có đường dẫn /catalog/** và chuyển tiếp đến dịch vụ Catalog.

Filter CircuitBreaker bên trong route có thuộc tính **name**, ví dụ **catalogReadBreaker**. Đây là ID mà Spring Cloud CircuitBreaker dùng để lấy hoặc tạo bộ ngắt tương ứng.

| Thuộc tính | Ví dụ | Vai trò |
|---|---|---|
| Route ID | catalog-read-route | Định danh route trong cấu hình và dữ liệu quan sát của Gateway |
| Predicate | Path=/catalog/** | Xác định request nào khớp route |
| URI đích | lb://CATALOG-SERVICE | Dịch vụ hoặc URI mà Gateway chuyển request đến |
| Circuit Breaker name | catalogReadBreaker | Chọn instance Circuit Breaker và chính sách Resilience4j |
| Fallback URI | forward:/fallback/catalog | Đường dẫn nội bộ được gọi khi filter kích hoạt fallback |

Route ID không tự động trở thành Circuit Breaker name. Cần khai báo rõ **name** trong filter. Tương tự, tên của instance trong cấu hình Resilience4j phải khớp với Circuit Breaker name mà route sử dụng.

## 2. Khai báo CircuitBreaker filter cho một route

Ví dụ sau khai báo một route đọc dữ liệu Catalog:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogReadBreaker
                fallbackUri: forward:/fallback/catalog
~~~

Khi request khớp /catalog/**, Gateway chuyển request đến **CATALOG-SERVICE** qua service discovery/load balancer. Filter CircuitBreaker bảo vệ lời gọi đến dịch vụ đó bằng instance có tên **catalogReadBreaker**.

Hai điểm cần kiểm tra:

- **id: catalog-read-route** là tên route; nó không cấu hình trạng thái hoặc sliding window của Circuit Breaker.
- **args.name: catalogReadBreaker** là tên bộ ngắt; đây là tên phải dùng trong nhánh **resilience4j.circuitbreaker.instances**.

**fallbackUri** trong ví dụ dùng scheme **forward:** để chuyển tiếp nội bộ đến một handler trong chính ứng dụng Gateway. Đường dẫn fallback nên tách khỏi predicate của route nghiệp vụ để request fallback không bị chuyển ngược đến dịch vụ đang lỗi.

Cấu trúc property route có thể khác giữa các thế hệ Spring Cloud Gateway và cách đóng gói server WebFlux hoặc MVC. Hãy dùng đúng property prefix của phiên bản Gateway trong dự án; ý nghĩa của route ID, filter name và phạm vi instance vẫn cần được giữ tách biệt.

## 3. Cấu hình Resilience4j theo Circuit Breaker name

Sau khi route dùng tên **catalogReadBreaker**, khai báo instance cùng tên trong cấu hình Resilience4j:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogReadBreaker:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Các thuộc tính có ý nghĩa:

- **slidingWindowType: COUNT_BASED**: đánh giá theo số lượng kết quả lời gọi.
- **slidingWindowSize: 20**: cửa sổ lưu tối đa 20 kết quả gần nhất.
- **minimumNumberOfCalls: 10**: cần tối thiểu 10 lời gọi được ghi nhận trước khi đánh giá tỷ lệ.
- **failureRateThreshold: 50**: tỷ lệ lỗi đạt 50% có thể làm bộ ngắt chuyển OPEN sau khi đủ mẫu.
- **waitDurationInOpenState: 15s**: thời gian chờ trong OPEN trước khi cho phép kiểm tra phục hồi.
- **permittedNumberOfCallsInHalfOpenState: 3**: giới hạn số lời gọi thăm dò khi HALF_OPEN.

Nếu route khai báo **name: catalogReadBreaker** nhưng properties lại chỉ có **instances.catalog**, cấu hình riêng cho **catalogReadBreaker** sẽ không được gắn vào instance mà route đang yêu cầu. Hãy giữ tên nhất quán giữa filter và cấu hình Resilience4j, kể cả chữ hoa/chữ thường.

## 4. Mỗi route dùng một Circuit Breaker riêng

Khi các route gọi các dịch vụ khác nhau hoặc cần chính sách bảo vệ khác nhau, nên đặt tên bộ ngắt riêng cho từng phạm vi. Ví dụ Gateway có route đọc Catalog và route kiểm tra Inventory:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogReadBreaker
                fallbackUri: forward:/fallback/catalog

        - id: inventory-check-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCheckBreaker
                fallbackUri: forward:/fallback/inventory
~~~

Khai báo hai instance độc lập:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogReadBreaker:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s

      inventoryCheckBreaker:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
~~~

Với cách tổ chức này:

- Lỗi của Catalog được ghi nhận trong **catalogReadBreaker**.
- Lỗi của Inventory được ghi nhận trong **inventoryCheckBreaker**.
- Hai bộ ngắt có trạng thái và sliding window riêng.
- Có thể điều chỉnh ngưỡng và thời gian OPEN theo đặc tính của từng dependency.

Nếu Catalog chuyển OPEN, route Inventory vẫn có thể tiếp tục hoạt động theo trạng thái của **inventoryCheckBreaker**. Đây là lợi ích của việc tách phạm vi bảo vệ theo dependency hoặc operation.

## 5. Nhiều route dùng chung một Circuit Breaker name

Không bắt buộc mỗi route phải có một bộ ngắt riêng. Hai route có thể dùng chung name khi chúng thực sự cần chia sẻ chính sách và trạng thái bảo vệ.

Ví dụ, một dịch vụ Catalog được gọi qua hai đường dẫn:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-public-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/public/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog

        - id: catalog-internal-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/internal/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog
~~~

Cả hai route cùng dùng **catalogSharedBreaker**. Vì cùng tên instance, các lời gọi được bảo vệ chia sẻ trạng thái và dữ liệu đánh giá của cùng Circuit Breaker. Nếu lỗi từ một nhóm request làm bộ ngắt chuyển OPEN, lời gọi từ route còn lại cũng có thể bị từ chối.

Cách chia sẻ phù hợp khi:

- Hai route gọi cùng dependency và có đặc tính lỗi tương đương.
- Chúng cần cùng timeout, ngưỡng lỗi và thời gian OPEN.
- Muốn tổng hợp lưu lượng của cả hai route trong cùng sliding window.
- Khi dependency suy giảm, muốn ngăn cả hai đường gọi cùng tạo thêm tải.

Không nên chia sẻ name chỉ vì hai route cùng thuộc một Gateway. Nếu route public và internal có SLA, backend hoặc chính sách lỗi khác nhau, một bộ ngắt chung có thể khiến lỗi của route này làm gián đoạn route kia. Hãy chọn phạm vi dựa trên dependency và hành vi vận hành mà nhóm muốn bảo vệ.

## 6. Tác động của phạm vi dùng chung đến sliding window

Circuit Breaker đánh giá các kết quả mà instance của nó nhận được. Khi hai route dùng chung name, kết quả từ cả hai route có thể đi vào cùng sliding window.

Giả sử **catalogSharedBreaker** dùng cửa sổ COUNT_BASED 20 mẫu và tối thiểu 10 lời gọi. Trong một khoảng thời gian, route public tạo ra 6 kết quả, route internal tạo ra 4 kết quả. Nếu các kết quả được ghi nhận vào cùng instance, bộ ngắt có đủ 10 mẫu để bắt đầu đánh giá tỷ lệ lỗi.

Ngược lại, nếu tách thành **catalogPublicBreaker** và **catalogInternalBreaker**, mỗi instance có cửa sổ riêng. Điều này cho phép phát hiện sự cố riêng theo luồng, nhưng từng instance cần đủ lưu lượng để đánh giá. Nếu một route ít request, nó có thể lâu đạt số mẫu tối thiểu.

| Cách đặt tên | Phạm vi sliding window | Hệ quả |
|---|---|---|
| Cùng name cho nhiều route | Một cửa sổ chung | Tập hợp lỗi và lưu lượng; một route có thể ảnh hưởng route khác |
| Name riêng từng route | Cửa sổ độc lập | Phân biệt sự cố theo route; cần đủ mẫu riêng cho từng instance |
| Name riêng theo operation | Cửa sổ theo loại thao tác | Phù hợp khi operation có SLA hoặc semantics lỗi khác nhau |

Khi chọn phạm vi, hãy cân nhắc cả năng lực của backend và mục tiêu giám sát. Nếu một backend dùng chung nhưng các operation có đặc tính rất khác nhau, có thể tách Circuit Breaker theo operation. Nếu nhiều route chỉ là các alias của cùng một operation, dùng chung name thường dễ vận hành hơn.

## 7. Khai báo fallback riêng cho từng route

Mỗi route có thể chỉ định một **fallbackUri** phù hợp với nội dung response cần trả về. Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogReadBreaker
                fallbackUri: forward:/fallback/catalog

        - id: inventory-check-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCheckBreaker
                fallbackUri: forward:/fallback/inventory
~~~

Gateway có thể xử lý hai fallback bằng controller:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GatewayFallbackController {

    @RequestMapping("/fallback/catalog")
    ResponseEntity<Map<String, String>> catalogFallback() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", "CATALOG_UNAVAILABLE",
                "message", "Catalog hiện chưa thể phục vụ yêu cầu"
            ));
    }

    @RequestMapping("/fallback/inventory")
    ResponseEntity<Map<String, String>> inventoryFallback() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", "INVENTORY_UNAVAILABLE",
                "message", "Inventory hiện chưa thể phục vụ yêu cầu"
            ));
    }
}
~~~

Fallback URI dùng **forward:** để Gateway chuyển tiếp nội bộ đến controller. Controller trả mã HTTP và payload phù hợp với hợp đồng API. Trong thực tế, response fallback cần giữ cấu trúc lỗi nhất quán, có thể thêm correlation ID hoặc mã lỗi để client biết có thể thử lại sau.

Không cấu hình fallback trùng với predicate route đang được bảo vệ nếu điều đó khiến request quay lại chính route và tạo vòng lặp. Fallback cũng không nên gọi lại backend đang lỗi qua một đường khác mà không có cơ chế bảo vệ riêng.

## 8. Phân biệt route ID, Circuit Breaker name và fallback URI khi vận hành

Khi điều tra sự cố, cần ghi nhận đủ ba định danh:

- **Route ID:** cho biết request đã khớp tuyến Gateway nào.
- **Circuit Breaker name:** cho biết bộ ngắt nào đã cho phép hoặc từ chối lời gọi.
- **Fallback URI:** cho biết handler nào đã được dùng để tạo phản hồi dự phòng.

Ví dụ log có thể ghi route ID và tên bộ ngắt cùng trace ID:

~~~java
log.warn(
    "Gateway route={} circuitBreaker={} traceId={} chuyển sang fallback",
    routeId,
    circuitBreakerName,
    traceId
);
~~~

Không nên ghép trace ID, user ID, order ID hoặc URL có tham số động vào Circuit Breaker name. Tên bộ ngắt cần có số lượng hữu hạn và ổn định. Đưa dữ liệu thay đổi theo request vào name có thể tạo nhiều instance và nhiều nhóm metric, làm phân mảnh sliding window và tăng cardinality của hệ thống giám sát.

Với Micrometer/Actuator và registry phù hợp, metric Circuit Breaker có thể được nhóm theo tên instance. Khi dashboard hiển thị **catalogSharedBreaker** ở trạng thái OPEN, hãy đối chiếu route ID để biết các route nào đang dùng chung instance đó. Việc ghi nhận cả hai loại tên giúp xác định phạm vi ảnh hưởng nhanh hơn.

## 9. Quy tắc đặt tên cho hệ thống có nhiều route

Tên Circuit Breaker nên mô tả dependency hoặc operation được bảo vệ. Một quy ước đơn giản có thể là dependency + operation + Breaker.

Ví dụ:

| Dependency | Operation | Circuit Breaker name |
|---|---|---|
| Catalog | Đọc sản phẩm | catalogReadBreaker |
| Catalog | Tìm kiếm | catalogSearchBreaker |
| Inventory | Kiểm tra tồn kho | inventoryCheckBreaker |
| Inventory | Giữ hàng | inventoryReserveBreaker |
| Payment | Cấp phép thanh toán | paymentAuthorizeBreaker |

Khi quyết định tách hoặc dùng chung name, hãy trả lời:

1. Các route có gọi cùng backend và cùng operation không?
2. Chúng có cần cùng ngưỡng lỗi, sliding window và thời gian OPEN không?
3. Một route lỗi có nên làm các route còn lại ngừng gọi backend không?
4. Lưu lượng của từng route có đủ để đánh giá riêng không?
5. Dashboard cần theo dõi sự cố theo dependency hay theo từng route?

Nếu câu trả lời cho thấy các route nên chia sẻ trạng thái, dùng chung name. Nếu cần cô lập lỗi và chính sách riêng, đặt name khác nhau. Hãy giữ route ID riêng để vẫn quan sát được từng tuyến ngay cả khi nhiều tuyến dùng chung một bộ ngắt.

## 10. Những lỗi cấu hình thường gặp

1. **Nhầm route ID với Circuit Breaker name.** Route có ID hợp lệ nhưng filter name không khớp properties Resilience4j; hãy kiểm tra args.name và instances.<name>.
2. **Đặt tên Circuit Breaker theo từng request.** Số lượng instance tăng không kiểm soát và sliding window bị chia nhỏ; hãy dùng tên ổn định theo dependency hoặc operation.
3. **Dùng chung name cho backend khác nhau.** Lỗi của một dependency có thể làm bộ ngắt dùng chung chuyển OPEN và ảnh hưởng route còn lại.
4. **Tách name quá nhỏ.** Mỗi route có quá ít lưu lượng để đạt minimumNumberOfCalls; đánh giá tỷ lệ lỗi trở nên chậm hoặc không đủ mẫu.
5. **Quên cấu hình instance tương ứng.** Filter dùng catalogReadBreaker nhưng chỉ khai báo instances.catalog; cấu hình dự kiến không được ánh xạ vào đúng ID.
6. **Fallback URI khớp lại route nghiệp vụ.** Request fallback có thể quay lại backend đang lỗi hoặc lặp filter; dùng đường dẫn nội bộ riêng.
7. **Không theo dõi cả route ID và Circuit Breaker name.** Dashboard chỉ có một tên khiến khó xác định route nào chịu ảnh hưởng khi nhiều route chia sẻ bộ ngắt.
8. **Dùng property prefix không đúng phiên bản Gateway.** Đối chiếu tài liệu release train và server variant đang dùng trước khi triển khai route YAML.

## 11. Tình huống thực hành

Một Gateway có ba route:

- /catalog/** gọi dịch vụ Catalog để đọc thông tin sản phẩm.
- /catalog/search/** gọi cùng dịch vụ Catalog để tìm kiếm.
- /inventory/** gọi dịch vụ Inventory để kiểm tra tồn kho.

Đội phát triển quyết định hai route Catalog chia sẻ cùng một bộ ngắt vì chúng cùng backend và cần cùng chính sách bảo vệ. Inventory dùng một bộ ngắt riêng.

Cấu hình:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog

        - id: catalog-search-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/search/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog

        - id: inventory-check-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCheckBreaker
                fallbackUri: forward:/fallback/inventory
~~~

Cần lưu ý thứ tự predicate và mức độ cụ thể của path khi thiết kế route để request tìm kiếm được khớp đúng route mong muốn. Trong ví dụ, cả hai route Catalog dùng **catalogSharedBreaker**, vì vậy lỗi từ hoạt động đọc hoặc tìm kiếm có thể cùng đóng góp vào sliding window. Route Inventory dùng **inventoryCheckBreaker**, nên trạng thái của nó độc lập.

Khi Circuit Breaker Catalog chuyển OPEN, cả hai route Catalog có thể đi vào fallback. Route Inventory vẫn được đánh giá bởi bộ ngắt riêng. Nếu hoạt động tìm kiếm có độ trễ hoặc tỷ lệ lỗi khác đáng kể so với đọc sản phẩm, đội vận hành có thể tách thành **catalogSearchBreaker** và **catalogReadBreaker** sau khi cân nhắc lưu lượng cùng mục tiêu cô lập.

Sau khi triển khai, hãy kiểm tra:

1. Mỗi request khớp route ID dự kiến.
2. Filter dùng đúng Circuit Breaker name.
3. Tên instance trong Resilience4j khớp với filter name.
4. Các route dùng chung name thực sự chia sẻ trạng thái và metric.
5. Fallback URI chuyển đến handler riêng và không quay lại route nghiệp vụ.
6. Dashboard hiển thị trạng thái theo Circuit Breaker name và log vẫn nhận diện được route ID.

## Kết luận

Trong Spring Cloud Gateway, **route ID** định danh tuyến định tuyến còn **CircuitBreaker name** xác định instance và phạm vi trạng thái được bảo vệ. Nhiều route dùng chung name sẽ chia sẻ Circuit Breaker và sliding window; name riêng giúp cô lập trạng thái, chính sách và metric. Hãy đặt tên ổn định theo dependency hoặc operation, khai báo cùng tên trong Resilience4j properties, chọn fallback URI riêng và ghi nhận cả route ID lẫn Circuit Breaker name để vận hành dễ dàng.
