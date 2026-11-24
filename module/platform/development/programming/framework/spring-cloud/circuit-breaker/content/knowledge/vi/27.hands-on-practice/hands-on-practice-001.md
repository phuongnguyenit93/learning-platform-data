# Dựng dịch vụ phụ thuộc có chế độ thành công, lỗi và phản hồi chậm

Khi thực hành circuit breaker, cần một dịch vụ phụ thuộc có thể điều khiển kết quả để tái hiện các tình huống mà ứng dụng gọi phải xử lý. Bài thực hành này dựng một dịch vụ tồn kho giả lập bằng Spring Boot với ba chế độ: trả dữ liệu thành công, trả lỗi HTTP 503 và phản hồi thành công sau một khoảng trễ có thể cấu hình.

Dịch vụ giả lập đóng vai trò upstream/downstream có hành vi xác định. Ứng dụng Spring Cloud CircuitBreaker có thể gọi nó để quan sát kết quả bình thường, failure rate và slow call rate, rồi thử fallback khi mạch OPEN. Ta sẽ chạy dịch vụ giả lập riêng ở cổng 8081 để không trộn trạng thái mô phỏng với ứng dụng gọi.

## Mục tiêu và sơ đồ thực hành

Sau khi hoàn thành, ta có thể:

- Khởi động một HTTP service độc lập mô phỏng dịch vụ tồn kho.
- Chọn chế độ thành công, lỗi hoặc phản hồi chậm qua query parameter.
- Điều chỉnh độ trễ để kiểm tra slow call threshold và timeout.
- Gửi request lặp lại để tạo đủ mẫu cho sliding window.
- Dùng cùng endpoint làm đích gọi của một circuit breaker trong ứng dụng khác.

~~~mermaid
flowchart LR
    A[Ứng dụng Spring Cloud] -->|HTTP request| B[Dịch vụ tồn kho giả lập :8081]
    B --> C{mode}
    C -->|success| D[HTTP 200 và dữ liệu tồn kho]
    C -->|error| E[HTTP 503 và mã lỗi]
    C -->|slow| F[Chờ có giới hạn rồi HTTP 200]
    D --> A
    E --> A
    F --> A
~~~

Trong phạm vi bài tập, dịch vụ giả lập chỉ tạo phản hồi có thể dự đoán. Nó không truy cập cơ sở dữ liệu và không đại diện cho logic tồn kho thật.

## 1. Tạo ứng dụng Spring Boot cho dịch vụ giả lập

Tạo một Spring Boot application riêng, ví dụ tên `inventory-simulator`. Dùng Java 17 trở lên và Spring Boot 3. Thêm dependency Web để tạo REST endpoint:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Nếu dự án đã dùng Spring Boot parent hoặc BOM, để dependency management quản lý phiên bản. Actuator là tùy chọn, chỉ cần khi muốn kiểm tra health endpoint của simulator.

Cấu hình ứng dụng chạy ở cổng 8081:

~~~yaml
spring:
  application:
    name: inventory-simulator

server:
  port: 8081

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Giữ cổng của simulator khác cổng ứng dụng gọi, ví dụ caller chạy ở 8080. Khi hai ứng dụng độc lập, có thể dừng hoặc khởi động lại simulator mà không làm mất cấu hình circuit breaker của caller.

## 2. Khai báo response model

Tạo hai record để biểu diễn kết quả thành công và lỗi mô phỏng:

~~~java
package com.example.inventorysimulator.api;

public record InventoryResponse(
        String sku,
        Integer available,
        String status,
        String mode,
        long delayMs,
        String message
) {
}
~~~

~~~java
package com.example.inventorysimulator.api;

public record ApiError(
        String code,
        String message,
        String mode
) {
}
~~~

Response thành công có số lượng tồn kho giả lập. Response lỗi có mã lỗi ổn định để caller hoặc test có thể nhận diện. Trường `mode` và `delayMs` giúp xác nhận simulator đã chạy đúng kịch bản.

## 3. Tạo endpoint có ba chế độ

Tạo controller sau. Endpoint mặc định dùng chế độ `success`; hai chế độ còn lại được chọn qua query parameter `mode`.

~~~java
package com.example.inventorysimulator.api;

import java.util.Locale;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/inventory")
public class InventorySimulationController {

    private static final long MAX_DELAY_MS = 10_000L;

    @GetMapping("/{sku}")
    public ResponseEntity<?> find(
            @PathVariable String sku,
            @RequestParam(defaultValue = "success") String mode,
            @RequestParam(defaultValue = "1500") long delayMs) {

        String selectedMode = mode.toLowerCase(Locale.ROOT);

        return switch (selectedMode) {
            case "success" -> ResponseEntity.ok(
                    new InventoryResponse(
                            sku, 12, "AVAILABLE", selectedMode, 0,
                            "Simulated inventory response"
                    )
            );

            case "error" -> ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(new ApiError(
                            "INVENTORY_SIMULATED_FAILURE",
                            "Inventory dependency is temporarily unavailable",
                            selectedMode
                    ));

            case "slow" -> slowResponse(sku, delayMs);

            default -> ResponseEntity.badRequest().body(
                    new ApiError(
                            "INVALID_SIMULATION_MODE",
                            "mode must be success, error or slow",
                            selectedMode
                    )
            );
        };
    }

    private ResponseEntity<?> slowResponse(String sku, long requestedDelayMs) {
        long boundedDelayMs = Math.max(
                0L,
                Math.min(requestedDelayMs, MAX_DELAY_MS)
        );

        try {
            Thread.sleep(boundedDelayMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();

            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(new ApiError(
                            "SIMULATION_INTERRUPTED",
                            "The simulated delay was interrupted",
                            "slow"
                    ));
        }

        return ResponseEntity.ok(
                new InventoryResponse(
                        sku, 12, "AVAILABLE", "slow", boundedDelayMs,
                        "Successful response after simulated delay"
                )
        );
    }
}
~~~

Các điểm cần chú ý:

- `success` trả HTTP 200 và dữ liệu tồn kho giả lập.
- `error` trả HTTP 503 cùng mã `INVENTORY_SIMULATED_FAILURE`. Đây là response HTTP hợp lệ; HTTP client như RestClient thường chuyển 5xx thành exception khi dùng `retrieve()`.
- `slow` chờ theo `delayMs`, sau đó vẫn trả HTTP 200. Vì kết quả cuối thành công, đây là cách cô lập slow call khỏi failure.
- Độ trễ được giới hạn tối đa 10 giây để tránh request vô tình giữ thread quá lâu.
- Khi thread bị interrupt, controller khôi phục cờ interrupt và trả lỗi có kiểm soát.

Việc dùng `Thread.sleep` ở đây chỉ nhằm mô phỏng dịch vụ chậm trong môi trường thực hành. Không dùng cách này để tạo độ trễ nhân tạo trong endpoint production. Dịch vụ thật nên dùng timeout ở client, giới hạn tài nguyên và quan sát nguyên nhân độ trễ thực tế.

## 4. Khởi động và gọi thử simulator

Chạy ứng dụng Spring Boot tại thư mục dự án simulator. Sau khi khởi động, gửi lần lượt các request:

**Thành công:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=success"
~~~

Kết quả mong đợi là HTTP 200 và JSON tương tự:

~~~json
{
  "sku": "SKU-100",
  "available": 12,
  "status": "AVAILABLE",
  "mode": "success",
  "delayMs": 0,
  "message": "Simulated inventory response"
}
~~~

**Lỗi phụ thuộc:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=error"
~~~

Kết quả mong đợi là HTTP 503 và body có mã `INVENTORY_SIMULATED_FAILURE`. Nếu caller dùng HTTP client chuyển 5xx thành exception, circuit breaker có thể ghi nhận kết quả này là failure theo cấu hình phân loại exception.

**Phản hồi chậm nhưng thành công:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=slow&delayMs=1800"
~~~

Kết quả mong đợi là HTTP 200 sau khoảng 1,8 giây. Nếu `slowCallDurationThreshold` của circuit breaker thấp hơn 1,8 giây và timeout của caller dài hơn độ trễ này, lời gọi được ghi nhận là slow call nhưng không phải failure.

**Chế độ không hợp lệ:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=unknown"
~~~

Kết quả mong đợi là HTTP 400. Không dùng 400 làm tín hiệu lỗi phụ thuộc trong bài thực hành; đây là lỗi tham số mô phỏng do caller gửi sai.

Trên Windows PowerShell, có thể gọi rõ `curl.exe` để tránh alias `curl` của PowerShell. Trên Linux hoặc macOS, dùng `curl` như ví dụ.

## 5. Kết nối simulator với ứng dụng CircuitBreaker

Trong ứng dụng caller, tạo HTTP client trỏ đến simulator. Ví dụ sau dùng `RestClient` của Spring Framework 6.1 trở lên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8081")
                .build();
    }
}
~~~

Tạo service gọi simulator thông qua Spring Cloud CircuitBreaker factory:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryQueryService {

    private final RestClient restClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public InventoryQueryService(
            RestClient inventoryRestClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = inventoryRestClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public InventoryResponse find(
            String sku,
            String mode,
            long delayMs) {

        return circuitBreakerFactory.create("inventoryProbe").run(
                () -> restClient.get()
                        .uri(uriBuilder -> uriBuilder
                                .path("/inventory/{sku}")
                                .queryParam("mode", mode)
                                .queryParam("delayMs", delayMs)
                                .build(sku))
                        .retrieve()
                        .body(InventoryResponse.class),
                error -> new InventoryResponse(
                        sku,
                        null,
                        "UNAVAILABLE",
                        mode,
                        0,
                        error.getClass().getSimpleName()
                )
        );
    }
}
~~~

Caller cần có dependency Spring Cloud CircuitBreaker với backend Resilience4j tương thích. Các kiểu `InventoryResponse` và `CircuitBreakerFactory` trong ví dụ thuộc ứng dụng caller; có thể dùng chung DTO qua một module hợp đồng nếu kiến trúc dự án cho phép.

Khi simulator trả 503, `RestClient.retrieve()` phát exception cho response 5xx và fallback được gọi. Khi simulator trả 200 sau độ trễ dài, supplier vẫn hoàn tất thành công nhưng circuit breaker có thể đánh dấu lời gọi là chậm. Khi mạch OPEN, lời gọi mới bị từ chối trước khi tới simulator và fallback trả kết quả suy giảm.

## 6. Cấu hình circuit breaker để quan sát cả lỗi và lời gọi chậm

Trong ứng dụng caller, khai báo instance tương ứng với tên `inventoryProbe`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryProbe:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Với cấu hình này:

- Cần tối thiểu 5 mẫu trước khi đánh giá tỷ lệ.
- Lời gọi mất hơn 800 ms được tính là slow call.
- Nếu slow call rate đạt 50%, mạch có thể mở dù các lời gọi đều trả HTTP 200.
- Nếu failure rate đạt 50%, mạch cũng có thể mở do lỗi.
- Sau 5 giây ở OPEN, mạch có thể cho phép các lời gọi thăm dò ở HALF_OPEN.

Không đặt timeout của HTTP client ngắn hơn 800 ms khi đang kiểm tra slow success. Nếu caller timeout ở 500 ms, lời gọi 1,8 giây sẽ trở thành lỗi timeout trước khi có thể hoàn tất thành công; bài kiểm thử không còn cô lập được slow call rate.

Timeout và slow call threshold có nhiệm vụ khác nhau. Timeout giới hạn thời gian chờ; slow call threshold phân loại lời gọi theo thời lượng sau khi lời gọi hoàn tất. Hãy kiểm tra riêng từng cơ chế.

## 7. Thực hành ba kịch bản circuit breaker

Mỗi kịch bản nên dùng một circuit breaker mới hoặc khởi động lại caller để sliding window và trạng thái OPEN của lần trước không ảnh hưởng kết quả.

| Kịch bản | Request đến simulator | Kết quả mong đợi ở caller |
|---|---|---|
| Bình thường | `mode=success` | HTTP 200, response có `available=12`, breaker ghi nhận thành công. |
| Lỗi nhanh | `mode=error` | Simulator trả 503, RestClient phát exception, breaker ghi nhận failure và fallback chạy. |
| Chậm nhưng thành công | `mode=slow&delayMs=1800` | Simulator trả 200 sau độ trễ, breaker ghi nhận slow call nhưng failure count không tăng. |
| Mạch OPEN | Gửi tiếp bất kỳ mode nào sau khi đủ mẫu lỗi/chậm | Caller bị từ chối nhanh, simulator không nhận request mới, fallback chạy. |
| Phục hồi | Sau thời gian OPEN, gửi `mode=success` | Breaker thử ở HALF_OPEN và có thể trở lại CLOSED nếu đủ mẫu thành công. |

**Bài tập A — xác nhận đường thành công**

1. Khởi động caller và simulator.
2. Gửi một request với `mode=success`.
3. Xác nhận response 200 và dữ liệu tồn kho.
4. Quan sát số lời gọi thành công của `inventoryProbe`.

**Bài tập B — tạo failure rate**

1. Dùng một breaker mới với cửa sổ 10 và minimumNumberOfCalls 5.
2. Gửi ít nhất 5 request với `mode=error`.
3. Xác nhận mỗi response simulator là 503.
4. Xác nhận caller kích hoạt fallback và failure rate tăng.
5. Sau khi đủ điều kiện, gửi thêm request và xác nhận mạch OPEN từ chối nhanh.

**Bài tập C — tạo slow call rate độc lập**

1. Dùng một breaker mới để tránh trạng thái từ bài tập B.
2. Đặt `slowCallDurationThreshold=800ms`, timeout caller dài hơn 1,8 giây.
3. Gửi ít nhất 5 request với `mode=slow&delayMs=1800`.
4. Xác nhận từng response là HTTP 200.
5. Xác nhận slow call rate tăng nhưng failure rate vẫn bằng 0.
6. Khi slow call rate đạt ngưỡng, xác nhận circuit breaker có thể mở.

**Bài tập D — kiểm tra trạng thái OPEN và HALF_OPEN**

1. Sau khi breaker OPEN, gửi thêm một request và quan sát thời gian phản hồi nhanh.
2. Kiểm tra log simulator để xác nhận request bị từ chối không tới dịch vụ phụ thuộc.
3. Chờ hết `waitDurationInOpenState`.
4. Gửi request success để kiểm tra lời gọi thăm dò.
5. Xác nhận mạch trở lại CLOSED sau khi các lời gọi thăm dò thành công.

## 8. Chẩn đoán khi kết quả không như mong đợi

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Chế độ error không làm failure rate tăng | HTTP client không chuyển status 503 thành exception hoặc exception bị ignore. | Kiểm tra exception tại supplier và cấu hình phân loại. |
| Chế độ slow không làm slow call rate tăng | Ngưỡng chậm cao hơn delay, hoặc caller đo thời lượng ở lớp khác. | So sánh delay thực tế với `slowCallDurationThreshold`. |
| Chế độ slow trở thành failure | Timeout của client ngắn hơn độ trễ simulator. | Tăng timeout trong bài slow-success hoặc giảm delay. |
| Mạch chưa OPEN | Chưa đủ `minimumNumberOfCalls`, tỷ lệ chưa đạt threshold hoặc breaker ID không khớp. | Kiểm tra số mẫu, metrics và tên instance. |
| Request vẫn tới simulator khi nghĩ breaker OPEN | Caller đang dùng ID khác hoặc một đường gọi khác không qua breaker. | Kiểm tra tên factory, log và call path. |
| Request bị từ chối ngay từ đầu | Breaker còn OPEN từ kịch bản trước. | Tạo instance mới hoặc khởi động lại caller. |
| Slow response không ổn định | Máy chạy test quá tải hoặc độ trễ sát ngưỡng. | Dùng khoảng cách lớn hơn giữa delay và threshold. |

Nếu dùng `RestClient`, hãy nhớ response 4xx/5xx từ `retrieve()` thường phát exception. Nếu dùng một HTTP client khác hoặc xử lý response bằng API không tự ném exception, cần chủ động chuyển status được chọn thành lỗi để circuit breaker thống kê.

## 9. Giới hạn của dịch vụ giả lập

Simulator dùng `Thread.sleep` để giữ request thread trong thời gian mô phỏng. Đây là cách đơn giản để tạo slow response trong bài tập đồng bộ, nhưng không mô phỏng chính xác mọi loại độ trễ của mạng hoặc hệ thống phân tán.

Khi thử nghiệm sâu hơn, có thể thay thế bằng WireMock, MockWebServer hoặc một service test riêng có thể điều khiển:

- Delay trước khi gửi response headers.
- Delay giữa các phần tử của response stream.
- Đóng kết nối đột ngột.
- Trả các mã HTTP khác nhau.
- Trả lỗi theo tỷ lệ xác suất.
- Giới hạn số request đồng thời.

Không expose chế độ lỗi giả lập ra môi trường production hoặc public internet. Giữ simulator trong mạng phát triển/test, giới hạn delay và không đưa thông tin nhạy cảm vào response.

## Checklist hoàn thành

- [ ] Simulator khởi động độc lập ở cổng 8081.
- [ ] `mode=success` trả HTTP 200 và dữ liệu tồn kho.
- [ ] `mode=error` trả HTTP 503 cùng mã lỗi ổn định.
- [ ] `mode=slow` trả HTTP 200 sau độ trễ được giới hạn.
- [ ] `mode` không hợp lệ trả HTTP 400.
- [ ] Caller gọi simulator qua một circuit breaker có ID ổn định.
- [ ] Lỗi 503 được ghi nhận là failure và kích hoạt fallback.
- [ ] Slow success làm tăng slow call rate mà không tăng failure rate.
- [ ] Khi breaker OPEN, request mới bị từ chối trước khi tới simulator.
- [ ] Sau thời gian OPEN, HALF_OPEN có thể thử phục hồi bằng response thành công.

Dịch vụ phụ thuộc có ba chế độ thành công, lỗi và phản hồi chậm tạo ra một môi trường kiểm thử có thể lặp lại cho Spring Cloud CircuitBreaker. Khi tách simulator khỏi caller, giới hạn độ trễ và xác nhận cả HTTP response lẫn metrics của circuit breaker, ta có thể quan sát riêng lỗi phụ thuộc, suy giảm độ trễ và quá trình phục hồi mà không cần chờ một hệ thống bên ngoài gặp sự cố thật.

