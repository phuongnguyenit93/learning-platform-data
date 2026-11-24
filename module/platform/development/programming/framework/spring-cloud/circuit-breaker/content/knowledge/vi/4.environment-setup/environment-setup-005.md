# Chuẩn bị ứng dụng gọi và dịch vụ có thể chủ động gây lỗi

Để quan sát Circuit Breaker hoạt động, cần có một dịch vụ gọi (caller) và một dịch vụ phụ thuộc (provider). Caller gửi yêu cầu HTTP đến provider. Provider có các chế độ phản hồi bình thường, phản hồi chậm hoặc trả lỗi theo tham số của yêu cầu. Nhờ chủ động điều khiển được tình huống lỗi, ta có thể quan sát cách Spring Cloud CircuitBreaker kết hợp Resilience4j ghi nhận kết quả, mở mạch, trả fallback và cho phép lời gọi thăm dò khi dịch vụ phục hồi.

Bài học dựng một môi trường thực hành nhỏ gồm hai ứng dụng Spring Boot chạy độc lập:

- **inventory-service:** dịch vụ cung cấp thông tin tồn kho, chạy ở cổng 8081. Dịch vụ có thể trả dữ liệu bình thường, trì hoãn phản hồi hoặc trả HTTP 503.
- **circuit-breaker-client:** ứng dụng gọi inventory-service, chạy ở cổng 8080. Ứng dụng dùng Spring Cloud CircuitBreaker với Resilience4j để bảo vệ lời gọi đến Inventory.

Môi trường này tập trung vào lời gọi HTTP đồng bộ để người học dễ theo dõi request và response. Các ví dụ reactive, timeout và bulkhead có thể được bổ sung sau khi đã hiểu luồng cơ bản.

## 1. Chuẩn bị công cụ và phiên bản

Cài đặt các công cụ sau trên máy phát triển:

- JDK tương thích với phiên bản Spring Boot được chọn.
- Maven hoặc Maven Wrapper do Spring Initializr tạo.
- IDE hỗ trợ Java như IntelliJ IDEA, Eclipse hoặc Visual Studio Code.
- Công cụ gửi HTTP request như curl, Postman hoặc HTTP Client tích hợp trong IDE.

Hai ứng dụng cần chạy đồng thời, vì vậy hãy kiểm tra cổng 8080 và 8081 chưa bị chương trình khác sử dụng.

Khi tạo dự án, chọn phiên bản Spring Boot và Spring Cloud tương thích theo bảng tương thích chính thức của Spring Cloud. Không nên chọn hai phiên bản độc lập theo cảm tính: Spring Cloud release train được thiết kế để hoạt động với một số dòng Spring Boot nhất định. Nếu dự án đã có parent POM hoặc dependency management do tổ chức cung cấp, hãy dùng đúng phiên bản đã được chuẩn hóa trong dự án.

Có thể tạo hai dự án Maven độc lập bằng Spring Initializr:

| Thuộc tính | inventory-service | circuit-breaker-client |
| --- | --- | --- |
| Project | Maven | Maven |
| Language | Java | Java |
| Packaging | Jar | Jar |
| Dependency chính | Spring Web | Spring Web, Spring Boot Actuator |
| Dependency bổ sung | Không bắt buộc | Spring Cloud CircuitBreaker Resilience4j |
| Port thực hành | 8081 | 8080 |

Đặt tên package rõ ràng, ví dụ `com.example.inventory` cho provider và `com.example.client` cho caller. Hai ứng dụng là hai tiến trình riêng, không dùng chung bộ nhớ hoặc cổng HTTP.

## 2. Cấu trúc thư mục thực hành

Sau khi tạo hai dự án, cấu trúc tối thiểu có thể như sau:

~~~text
circuit-breaker-lab/
├── inventory-service/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/inventory/
│       │   ├── InventoryApplication.java
│       │   ├── InventoryController.java
│       │   └── InventoryResponse.java
│       └── resources/application.yml
└── circuit-breaker-client/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/client/
        │   ├── ClientApplication.java
        │   ├── InventoryResponse.java
        │   ├── InventoryClientConfiguration.java
        │   ├── InventoryGateway.java
        │   └── InventoryController.java
        └── resources/application.yml
~~~

Spring Initializr tạo sẵn lớp application có annotation `@SpringBootApplication`. Nếu package của bạn khác ví dụ, hãy điều chỉnh khai báo package và import cho nhất quán. DTO `InventoryResponse` được khai báo ở cả hai ứng dụng vì chúng chạy độc lập; trong dự án thực tế có thể dùng một hợp đồng API hoặc thư viện mô hình dùng chung nếu phù hợp.

## 3. Tạo dịch vụ Inventory có thể chủ động gây lỗi

Provider cần có một endpoint ổn định để trả dữ liệu tồn kho, cùng hai tham số thử nghiệm:

- `fail=true`: trả HTTP 503 để mô phỏng dịch vụ phụ thuộc gặp lỗi.
- `delayMs=3000`: trì hoãn phản hồi 3 giây để mô phỏng lời gọi chậm.

Không truyền tham số hoặc dùng `fail=false&delayMs=0` sẽ tạo phản hồi bình thường. Giới hạn độ trễ tối đa trong ví dụ giúp tránh vô tình treo tiến trình quá lâu.

### 3.1. DTO phản hồi

Tạo file `InventoryResponse.java` trong package `com.example.inventory`:

~~~java
package com.example.inventory;

public record InventoryResponse(
    String sku,
    int available,
    String status
) {
}
~~~

DTO có mã SKU, số lượng tồn kho và trạng thái. Provider trả `OK` khi xử lý thành công.

### 3.2. Controller mô phỏng lỗi và độ trễ

Tạo file `InventoryController.java`:

~~~java
package com.example.inventory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/inventory")
public class InventoryController {

    private static final Logger log = LoggerFactory.getLogger(InventoryController.class);

    @GetMapping("/{sku}")
    public InventoryResponse getInventory(
            @PathVariable String sku,
            @RequestParam(defaultValue = "false") boolean fail,
            @RequestParam(defaultValue = "0") long delayMs) {

        long safeDelay = Math.min(Math.max(delayMs, 0), 15_000);
        log.info("Inventory request sku={} fail={} delayMs={}", sku, fail, safeDelay);

        if (safeDelay > 0) {
            try {
                Thread.sleep(safeDelay);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Inventory request interrupted",
                    exception
                );
            }
        }

        if (fail) {
            throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Simulated inventory failure"
            );
        }

        return new InventoryResponse(sku, 25, "OK");
    }
}
~~~

Tham số `fail` chỉ mô phỏng lỗi sau khi đã chờ độ trễ được yêu cầu. Nhờ đó có thể thử riêng lỗi HTTP, lời gọi chậm hoặc kết hợp cả hai. Trong ứng dụng thật, không nên để endpoint điều khiển lỗi như thế này được công khai; đây chỉ là công cụ thử nghiệm ở môi trường local.

### 3.3. Cấu hình cổng provider

Trong `inventory-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8081
~~~

Lớp khởi động có thể được tạo bởi Spring Initializr:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Đến đây, inventory-service có thể chạy độc lập và nhận request từ công cụ HTTP.

## 4. Tạo ứng dụng caller và thêm Resilience4j

Caller là ứng dụng Spring Boot gửi request đến Inventory. Nó cần Spring Web để cung cấp endpoint cho người thử nghiệm, Spring Boot Actuator để quan sát ứng dụng và Spring Cloud CircuitBreaker Resilience4j để bọc lời gọi từ xa.

### 4.1. Khai báo dependency Maven

Trong `circuit-breaker-client/pom.xml`, dự án cần có Spring Boot parent phù hợp với môi trường và Spring Cloud BOM tương thích. Ví dụ phần quản lý phiên bản Spring Cloud:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>SPRING_CLOUD_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Thay `SPRING_CLOUD_COMPATIBLE_RELEASE_TRAIN` bằng release train tương thích với Spring Boot của dự án. Trong POM thực tế, `properties` và `dependencyManagement` được đặt bên trong phần tử `project`.

Khai báo các dependency của caller:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>
</dependencies>
~~~

Với provider, dependency tối thiểu là `spring-boot-starter-web`. Không cần thêm Resilience4j vào provider vì trong bài thực hành, Circuit Breaker nằm ở phía ứng dụng gọi.

Spring Cloud CircuitBreaker cung cấp abstraction để mã caller không phải thao tác trực tiếp với API của từng provider. Resilience4j là provider được dùng trong bài học này. BOM giúp Maven chọn các phiên bản Spring Cloud đồng bộ thay vì khai báo phiên bản riêng cho từng starter.

### 4.2. Cấu hình địa chỉ Inventory và Circuit Breaker

Trong `circuit-breaker-client/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

inventory:
  base-url: http://localhost:8081

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Cấu hình này dùng cửa sổ 10 lời gọi gần nhất và cần tối thiểu 5 mẫu trước khi tính tỷ lệ. Khi tỷ lệ lỗi đạt 50% hoặc tỷ lệ lời gọi chậm đạt 50%, Circuit Breaker có thể chuyển sang OPEN. Lời gọi kéo dài từ 2 giây được tính là chậm. Sau 10 giây ở OPEN, mạch tự chuyển sang HALF_OPEN và cho phép tối đa hai lời gọi thăm dò.

Các con số chỉ phục vụ môi trường lab. Trong production, cần chọn ngưỡng dựa trên lưu lượng và độ trễ bình thường của dependency. `slowCallDurationThreshold` chỉ đánh dấu một lời gọi là chậm để tính tỷ lệ; nó không tự hủy lời gọi hoặc thay thế cấu hình timeout. Cần cấu hình timeout ở HTTP client hoặc TimeLimiter khi muốn giới hạn thời gian chờ thực tế.

### 4.3. Khởi tạo HTTP client

Ví dụ dùng `RestClient`, API đồng bộ có trong Spring Framework 6.1 trở lên. Spring Boot cung cấp `RestClient.Builder` để tạo client:

~~~java
package com.example.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        return builder
            .baseUrl(baseUrl)
            .build();
    }
}
~~~

Nếu dự án dùng Spring Framework cũ chưa có `RestClient`, có thể thay bằng `RestTemplate` hoặc nâng cấp lên phiên bản tương thích. Hãy bảo đảm phiên bản Spring Boot và Spring Cloud được chọn theo cùng một ma trận tương thích.

### 4.4. Khai báo DTO ở caller

Tạo `InventoryResponse.java` trong package `com.example.client`:

~~~java
package com.example.client;

public record InventoryResponse(
    String sku,
    int available,
    String status
) {
    public static InventoryResponse unavailable(String sku) {
        return new InventoryResponse(sku, 0, "UNAVAILABLE");
    }
}
~~~

Fallback trả về trạng thái `UNAVAILABLE` để caller có thể phân biệt kết quả dự phòng với dữ liệu tồn kho thật. Trong ứng dụng nghiệp vụ, cần xác định rõ API contract: kết quả dự phòng có thể là response suy giảm, dữ liệu cache hoặc một lỗi HTTP có kiểm soát, tùy yêu cầu của chức năng.

### 4.5. Bọc lời gọi bằng Circuit Breaker

Tạo `InventoryGateway.java`:

~~~java
package com.example.client;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RestClient inventoryRestClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RestClient inventoryRestClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryRestClient = inventoryRestClient;
    }

    public InventoryResponse getInventory(
            String sku,
            boolean fail,
            long delayMs) {

        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryRestClient.get()
                .uri(uriBuilder -> uriBuilder
                    .path("/inventory/{sku}")
                    .queryParam("fail", fail)
                    .queryParam("delayMs", delayMs)
                    .build(sku))
                .retrieve()
                .body(InventoryResponse.class),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

Tên `inventory` trong `create("inventory")` phải trùng tên instance trong application.yml. Khi provider trả HTTP 503, `RestClient` ném exception và Circuit Breaker ghi nhận kết quả thất bại. Khi mạch OPEN hoặc lời gọi gặp lỗi, hàm fallback trả về DTO có trạng thái `UNAVAILABLE`.

Trong ví dụ này fallback trả một DTO bình thường nên endpoint caller vẫn có thể trả HTTP 200. Đây là lựa chọn đơn giản để quan sát kết quả. Với API thực tế, hãy thiết kế response và HTTP status phù hợp với hợp đồng nghiệp vụ, tránh để client hiểu nhầm dữ liệu dự phòng là dữ liệu tồn kho đã được xác nhận.

### 4.6. Mở endpoint để gọi thử

Tạo `InventoryController.java` trong caller:

~~~java
package com.example.client;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryController {

    private final InventoryGateway inventoryGateway;

    public InventoryController(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    @GetMapping("/check/{sku}")
    public InventoryResponse check(
            @PathVariable String sku,
            @RequestParam(defaultValue = "false") boolean fail,
            @RequestParam(defaultValue = "0") long delayMs) {
        return inventoryGateway.getInventory(sku, fail, delayMs);
    }
}
~~~

Lớp khởi động `ClientApplication` được tạo tương tự như `InventoryApplication`, với package `com.example.client`.

Luồng request lúc này là:

~~~text
HTTP client
    |
    v
circuit-breaker-client :8080
    |
    v
CircuitBreaker "inventory"
    |
    +---- CLOSED / HALF_OPEN: cho phép lời gọi
    |             |
    |             v
    |       RestClient
    |             |
    |             v
    |       inventory-service :8081
    |
    +---- OPEN: từ chối lời gọi
                  |
                  v
               fallback
~~~

## 5. Khởi chạy hai ứng dụng

Mở hai terminal riêng trong thư mục dự án.

Terminal thứ nhất chạy provider:

~~~powershell
cd inventory-service
.\mvnw.cmd spring-boot:run
~~~

Terminal thứ hai chạy caller:

~~~powershell
cd circuit-breaker-client
.\mvnw.cmd spring-boot:run
~~~

Nếu dùng Maven cài sẵn thay vì Maven Wrapper, có thể chạy `mvn spring-boot:run`. Khởi động provider trước để caller có thể kết nối ngay khi nhận request. Khi cả hai ứng dụng đã sẵn sàng, kiểm tra endpoint health nếu Actuator đã được bật hoặc gửi một request thử trực tiếp đến Inventory.

Nếu chạy từ IDE, hãy tạo hai Run Configuration riêng và bảo đảm mỗi ứng dụng dùng đúng working directory. Không khởi chạy hai ứng dụng trên cùng một cổng.

## 6. Kiểm tra provider độc lập trước

Trước khi kiểm tra Circuit Breaker, hãy gọi trực tiếp provider để xác nhận endpoint mô phỏng hoạt động đúng.

Phản hồi bình thường:

~~~bash
curl "http://localhost:8081/inventory/ABC-001"
~~~

Provider trả dữ liệu tương tự:

~~~json
{
  "sku": "ABC-001",
  "available": 25,
  "status": "OK"
}
~~~

Mô phỏng lỗi HTTP 503:

~~~bash
curl -i "http://localhost:8081/inventory/ABC-001?fail=true"
~~~

Mô phỏng phản hồi chậm 3 giây:

~~~bash
curl -i "http://localhost:8081/inventory/ABC-001?delayMs=3000"
~~~

Nếu các request trực tiếp không cho kết quả như mong đợi, hãy xử lý vấn đề ở provider trước. Khi provider chưa chạy hoặc URL sai, caller cũng có thể nhận lỗi kết nối; lỗi kết nối vẫn là tình huống có thể dùng để quan sát Circuit Breaker, nhưng sẽ khó phân biệt với lỗi do endpoint mô phỏng.

## 7. Gửi request qua caller

Khi cả hai ứng dụng đã chạy, gửi request đến caller:

~~~bash
curl "http://localhost:8080/check/ABC-001"
~~~

Caller gọi Inventory và trả về dữ liệu thành công.

Mô phỏng lỗi:

~~~bash
curl "http://localhost:8080/check/ABC-001?fail=true"
~~~

Caller nhận lỗi HTTP 503 từ provider. Fallback trả về kết quả có trạng thái `UNAVAILABLE`. Nếu mới chỉ có một request thất bại, Circuit Breaker thường vẫn ở CLOSED vì chưa đủ `minimumNumberOfCalls` để đánh giá tỷ lệ.

Mô phỏng lời gọi chậm:

~~~bash
curl "http://localhost:8080/check/ABC-001?delayMs=3000"
~~~

Request mất khoảng 3 giây ở provider. Với cấu hình lab, thời lượng này vượt `slowCallDurationThreshold: 2s` và được ghi nhận là lời gọi chậm. Một lời gọi chậm đơn lẻ chưa đủ để mở mạch nếu chưa đạt số mẫu tối thiểu và tỷ lệ chậm cần thiết.

## 8. Tạo đủ mẫu để quan sát Circuit Breaker mở mạch

Cấu hình lab cần tối thiểu 5 lời gọi và ngưỡng lỗi 50%. Để tạo tình huống rõ ràng, gửi ít nhất 5 request thất bại qua caller. Trong PowerShell:

~~~powershell
1..5 | ForEach-Object {
    curl.exe -s "http://localhost:8080/check/ABC-001?fail=true"
}
~~~

Hoặc chạy lặp lại request trong Postman. Sau khi có đủ mẫu, tỷ lệ lỗi đạt 100%, vượt ngưỡng 50% và Circuit Breaker chuyển sang OPEN.

Gửi thêm request lỗi hoặc request bình thường qua caller khi Circuit Breaker đang OPEN. Caller tiếp tục trả fallback `UNAVAILABLE`, nhưng provider không nhận request mới từ Circuit Breaker trong thời gian mạch mở. Có thể kiểm tra log của inventory-service để thấy các request bị ngắt mạch không tiếp tục đi đến controller provider.

Sau khi hết `waitDurationInOpenState: 10s`, Circuit Breaker chuyển sang HALF_OPEN do cấu hình tự động chuyển trạng thái. Gửi hai request thành công:

~~~powershell
1..2 | ForEach-Object {
    curl.exe -s "http://localhost:8080/check/ABC-001?fail=false"
}
~~~

Hai lời gọi thăm dò thành công sẽ cho phép Circuit Breaker trở về CLOSED. Nếu lời gọi thăm dò tiếp tục thất bại hoặc chậm theo ngưỡng, mạch có thể quay lại OPEN.

Để thử điều kiện slow call, hãy gửi nhiều request có `delayMs=3000`. Khi số mẫu tối thiểu đã đạt và tỷ lệ lời gọi chậm vượt ngưỡng, Circuit Breaker cũng có thể mở mạch dù các request cuối cùng trả về thành công. Hãy đợi trạng thái trở lại CLOSED trước khi thực hiện một kịch bản thử nghiệm độc lập khác, hoặc khởi động lại caller để đưa instance về trạng thái ban đầu trong môi trường lab.

## 9. Quan sát trạng thái và metrics

Caller đã thêm Spring Boot Actuator và mở các endpoint health, info, metrics. Có thể kiểm tra health:

~~~bash
curl "http://localhost:8080/actuator/health"
~~~

Tùy cấu hình provider và phiên bản tích hợp, Resilience4j có thể cung cấp metrics như số lời gọi thành công, thất bại, bị từ chối, tỷ lệ lỗi và tỷ lệ lời gọi chậm. Hãy xem các metrics được ứng dụng công bố:

~~~bash
curl "http://localhost:8080/actuator/metrics"
~~~

Endpoint `/actuator/metrics` trả danh sách tên metric đang có. Có thể truy vấn một metric cụ thể bằng cách thay `{metric-name}` bằng tên được trả về:

~~~bash
curl "http://localhost:8080/actuator/metrics/{metric-name}"
~~~

Tên và tag của metric phụ thuộc phiên bản Resilience4j, Micrometer và cấu hình Actuator. Nếu không thấy metric mong đợi, kiểm tra dependency, endpoint exposure, cấu hình tag và phần tích hợp metrics của provider. Không nên mặc định rằng chỉ cần thêm Actuator là mọi metric của Circuit Breaker đều tự động xuất hiện trong mọi phiên bản.

Trong môi trường chia sẻ, chỉ expose các endpoint quản trị và metrics cần thiết. Không mở rộng Actuator ra mạng công khai nếu chưa có xác thực và kiểm soát truy cập phù hợp.

## 10. Các lỗi thường gặp khi chuẩn bị môi trường

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Caller không khởi động được | Spring Boot và Spring Cloud không tương thích hoặc Maven không phân giải được dependency | Kiểm tra BOM, release train và log Maven |
| Caller báo connection refused | Provider chưa chạy, sai port hoặc sai `inventory.base-url` | Gọi trực tiếp cổng 8081 và kiểm tra application.yml |
| Request trả 404 | Sai mapping hoặc sai đường dẫn | Kiểm tra `/inventory/{sku}` ở provider và `/check/{sku}` ở caller |
| Gửi `fail=true` nhưng Circuit Breaker chưa OPEN | Chưa đủ mẫu, lỗi chưa được ghi nhận hoặc chưa vượt ngưỡng | Kiểm tra `minimumNumberOfCalls`, exception và số request |
| Gửi request chậm nhưng không mở mạch | Chưa đủ số mẫu hoặc tỷ lệ slow call chưa đạt ngưỡng | Kiểm tra `slowCallDurationThreshold`, `slowCallRateThreshold` và thời lượng thực tế |
| Fallback không chạy như mong đợi | Chữ ký hoặc kiểu dữ liệu fallback không tương thích, hoặc request chưa đi qua đúng Circuit Breaker | Kiểm tra đoạn `run`, tên instance và log exception |
| Không thấy metrics | Chưa bật Actuator, endpoint chưa expose hoặc thiếu tích hợp Micrometer | Kiểm tra dependency và danh sách metric |
| Port đã được sử dụng | Ứng dụng khác chiếm 8080 hoặc 8081 | Dừng tiến trình cũ hoặc đổi port đồng bộ với base URL |

Một lỗi cấu hình phổ biến là dùng tên instance khác nhau giữa mã Java và application.yml. Ví dụ mã gọi `create("inventory")` nhưng YAML lại khai báo `instances.inventoryService`. Khi đó cấu hình mong đợi có thể không áp dụng cho instance thực tế. Hãy giữ tên thống nhất từ đầu đến cuối.

Một vấn đề khác là nhầm lẫn giữa lời gọi chậm và timeout. Slow call threshold chỉ đánh dấu lời gọi đã mất nhiều thời gian để hoàn thành. Nếu cần dừng request sau một giới hạn cụ thể, hãy cấu hình timeout cho HTTP client hoặc TimeLimiter. Hai cơ chế có thể phối hợp nhưng giải quyết hai mục tiêu khác nhau.

## 11. Chuẩn bị cho các bài thực hành tiếp theo

Khi môi trường đã hoạt động, có thể dùng hai ứng dụng này để thực hành các nội dung tiếp theo:

- Điều chỉnh `slidingWindowSize`, `minimumNumberOfCalls` và `failureRateThreshold`, sau đó quan sát thời điểm Circuit Breaker mở mạch.
- So sánh COUNT_BASED và TIME_BASED bằng cách thay đổi nhịp gửi request.
- Thử CLOSED, OPEN và HALF_OPEN bằng các chuỗi lỗi và thành công có chủ đích.
- Thay đổi fallback để phân biệt dữ liệu cache, kết quả suy giảm và lỗi nghiệp vụ.
- Bổ sung timeout và bulkhead để quan sát cách giới hạn thời gian chờ và số lời gọi đồng thời.
- Tạo phiên bản WebFlux với WebClient và ReactiveCircuitBreakerFactory để thực hành luồng reactive.

Trước khi chuyển sang bài tiếp theo, cần xác nhận provider chạy ở cổng 8081, caller chạy ở cổng 8080, request bình thường trả dữ liệu tồn kho, request `fail=true` tạo lỗi 503 và request có `delayMs` tạo độ trễ có thể quan sát. Khi đã tái tạo được các tình huống này, người học có một môi trường ổn định để quan sát Circuit Breaker bảo vệ ứng dụng gọi khi dependency chậm hoặc không khả dụng.

## Tài liệu tham khảo

- [Spring Initializr](https://start.spring.io/)
- [Spring Cloud release train documentation](https://spring.io/projects/spring-cloud)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Resilience4j CircuitBreaker documentation](https://resilience4j.readme.io/docs/circuitbreaker)
- [Spring Framework REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)

