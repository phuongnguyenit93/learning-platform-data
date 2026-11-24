# Cấu hình theo profile và xác minh giá trị đang được áp dụng

Trong ứng dụng Spring Cloud Circuit Breaker, cùng một bộ ngắt có thể cần ngưỡng lỗi, thời gian chờ và timeout khác nhau ở môi trường phát triển, kiểm thử và production. Spring Boot hỗ trợ tách cấu hình theo profile để mỗi môi trường nạp bộ giá trị phù hợp. Tuy nhiên, cấu hình viết trong file chưa chắc là cấu hình đang có hiệu lực: biến môi trường, tham số dòng lệnh, file bên ngoài hoặc cấu hình theo ID có thể ghi đè giá trị đó.

Bài học này trình bày cách quản lý profile cho Resilience4j, giữ ID cấu hình đồng nhất với factory, và xác minh giá trị cuối cùng mà ứng dụng đã nạp. Việc xác minh rất quan trọng vì một Circuit Breaker cấu hình sai có thể mở quá sớm, phục hồi quá chậm hoặc không bảo vệ đúng lời gọi tới dịch vụ phụ thuộc.

## 1. Profile trong Spring Boot

Profile là tên một nhóm cấu hình được kích hoạt theo môi trường hoặc mục đích chạy ứng dụng. Ví dụ, `dev` dành cho phát triển cục bộ, `test` dành cho kiểm thử tích hợp và `prod` dành cho production. Spring Boot nạp cấu hình chung rồi áp dụng phần cấu hình dành cho các profile đang hoạt động.

Có hai cách phổ biến để tách cấu hình:

- Dùng file riêng như `application-dev.yml`, `application-test.yml` và `application-prod.yml`. File có hậu tố profile chỉ được nạp khi profile tương ứng đang hoạt động.
- Dùng nhiều YAML document trong cùng `application.yml`, phân tách bằng `---` và chỉ định điều kiện nạp qua `spring.config.activate.on-profile`.

Với ứng dụng chạy ở production, nên chọn profile từ môi trường triển khai hoặc tham số khởi động thay vì cố định profile production trong file cấu hình được đóng gói cùng ứng dụng.

## 2. Kích hoạt profile

Có thể kích hoạt profile bằng biến môi trường:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
```

Hoặc truyền tham số khi khởi động:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Trong môi trường container, orchestrator hoặc pipeline triển khai, có thể đặt `SPRING_PROFILES_ACTIVE=prod` trong cấu hình workload. Nếu có nhiều profile, phân tách bằng dấu phẩy, ví dụ `dev,metrics`.

`spring.profiles.active` và `spring.profiles.default` là thuộc tính dùng để chọn profile, vì vậy phải được đặt trong nguồn cấu hình không phụ thuộc profile, chẳng hạn biến môi trường, tham số dòng lệnh hoặc document chung. Không đặt `spring.profiles.active` bên trong document chỉ được kích hoạt bởi một profile khác. Nếu không có profile nào được kích hoạt, Spring Boot dùng profile mặc định `default`.

## 3. Tách cấu hình Circuit Breaker theo file profile

Ví dụ cấu hình chung trong `application.yml` khai báo tên ứng dụng và các thiết lập quan sát cơ bản:

```yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

Trong `application-dev.yml`, có thể dùng ngưỡng dễ quan sát hơn và thời gian chờ ngắn để kiểm thử nhanh:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallRateThreshold: 80
        slowCallDurationThreshold: 1s
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 2

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
```

Trong `application-prod.yml`, chọn ngưỡng phù hợp với lưu lượng thật và SLA của dịch vụ tồn kho:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 50
        failureRateThreshold: 40
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 1200ms
```

Đây là các giá trị minh họa, không phải khuyến nghị mặc định cho mọi hệ thống. `TIME_BASED` với `slidingWindowSize: 30` nghĩa là cửa sổ quan sát 30 giây; `COUNT_BASED` với `slidingWindowSize: 10` nghĩa là cửa sổ gồm tối đa 10 lời gọi gần nhất. `minimumNumberOfCalls` ngăn bộ ngắt đánh giá tỷ lệ lỗi khi chưa có đủ mẫu. Hãy chọn giá trị dựa trên lưu lượng, độ trễ bình thường, thời gian phục hồi và mức độ chấp nhận fallback của nghiệp vụ.

Trong cả hai file, ID `inventory` phải trùng với ID mà mã ứng dụng dùng khi tạo breaker, ví dụ `circuitBreakerFactory.create("inventory")` hoặc `reactiveCircuitBreakerFactory.create("inventory")`. Cấu hình một ID khác sẽ không thay đổi bộ ngắt đang bảo vệ lời gọi.

## 4. Dùng nhiều YAML document trong cùng application.yml

Nếu muốn giữ cấu hình ở một file, có thể phân tách các document bằng `---`. Document đầu tiên chứa cấu hình chung; document tiếp theo chỉ được nạp khi điều kiện profile phù hợp:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true

---
spring:
  config:
    activate:
      on-profile: dev

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 5s

---
spring:
  config:
    activate:
      on-profile: prod

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 50
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
```

`spring.config.activate.on-profile` xác định document được đưa vào Environment khi profile phù hợp đang hoạt động. Khi dùng file riêng `application-dev.yml`, không cần khai báo điều kiện này trong file vì chính tên file đã gắn nó với profile `dev`.

Không nên khai báo cùng một thuộc tính ở nhiều nơi mà không có chủ đích. Khi nhiều nguồn cùng cung cấp một giá trị, nguồn có độ ưu tiên cao hơn sẽ thắng; người đọc file có thể tưởng giá trị trong YAML đang dùng trong khi runtime thực tế nhận giá trị từ môi trường hoặc tham số khởi động.

## 5. Hiểu thứ tự ưu tiên cấu hình

Spring Boot hợp nhất thuộc tính từ nhiều nguồn. Có thể nhớ các quy tắc vận hành quan trọng sau:

- Giá trị mặc định trong ứng dụng có độ ưu tiên thấp.
- Trong nhóm Config Data, file cấu hình bên ngoài artifact thường được ưu tiên hơn file được đóng gói cùng artifact; file dành cho profile đang hoạt động ghi đè file chung tại cùng vị trí cấu hình.
- Biến môi trường và thuộc tính hệ thống JVM có thể ghi đè các giá trị trong file cấu hình.
- `SPRING_APPLICATION_JSON` có thể cung cấp giá trị ghi đè; tham số dòng lệnh của ứng dụng thường có độ ưu tiên cao hơn các nguồn trên.

Đây là quy tắc tổng quát để định hướng điều tra, không phải danh sách đầy đủ mọi property source. Thứ tự chính xác phụ thuộc loại nguồn cấu hình, vị trí file, profile và cách khởi chạy ứng dụng. Khi điều tra một giá trị bất ngờ, hãy xem danh sách property source và nguồn gốc (origin) của thuộc tính thay vì chỉ tìm kiếm trong `application.yml`.

Ví dụ, file `application-prod.yml` đặt `failureRateThreshold: 40`, nhưng lệnh chạy lại có `--resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold=25`. Khi đó giá trị 25 từ tham số dòng lệnh có độ ưu tiên cao hơn và được sử dụng. Đây có thể là chủ ý của một đợt triển khai, nhưng cũng có thể là biến môi trường cũ còn sót lại.

Quy tắc đặt tên biến môi trường của Spring Boot chuyển tên thuộc tính thành chữ hoa, thay dấu chấm bằng dấu gạch dưới và loại bỏ dấu gạch nối. Ví dụ thuộc tính:

```text
resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold
```

có thể được đặt qua biến môi trường:

```text
RESILIENCE4J_CIRCUITBREAKER_INSTANCES_INVENTORY_FAILURERATETHRESHOLD
```

Với các tên phức tạp, nên kiểm tra cách relaxed binding của phiên bản Spring Boot đang dùng và xác minh giá trị sau khi ứng dụng khởi động. Không đoán tên biến môi trường rồi kết luận nó đã được binding.

## 6. Cấu hình Spring Cloud CircuitBreaker theo ID

Spring Cloud CircuitBreaker dùng ID truyền vào factory để chọn cấu hình của bộ ngắt. Ví dụ với reactive:

```java
ReactiveCircuitBreaker inventoryBreaker =
        reactiveCircuitBreakerFactory.create("inventory");

return inventoryBreaker.run(
        inventoryClient.getStock(sku),
        error -> Mono.just(Stock.unavailable(sku))
);
```

Với lời gọi đồng bộ, API tương ứng là `circuitBreakerFactory.create("inventory")`. Tên `inventory` cần khớp với khóa trong `resilience4j.circuitbreaker.instances` và `resilience4j.timelimiter.instances`.

Spring Cloud CircuitBreaker cho phép cấu hình mặc định, theo group và theo ID. Khi dùng properties, cấu hình theo instance cụ thể có thể ghi đè cấu hình group hoặc mặc định. Cấu hình properties có độ ưu tiên cao hơn Java `Customizer`. Do đó, nếu một bean `Customizer` đặt `failureRateThreshold` là 50 nhưng file profile hoặc biến môi trường đặt 30, giá trị từ properties sẽ được ưu tiên.

Để tránh nhầm lẫn, chọn một nguồn cấu hình chính cho từng môi trường. Dùng `Customizer` cho những thiết lập cần tạo bằng code hoặc logic có điều kiện; dùng properties cho giá trị vận hành cần thay đổi theo profile hoặc deployment mà không biên dịch lại ứng dụng.

## 7. Xác minh profile đang hoạt động

Trước tiên, xác nhận ứng dụng thực sự chạy với profile mong đợi. Có thể kiểm tra lúc khởi động qua log Spring Boot hoặc đọc `Environment`:

```java
@Component
public class ActiveProfileLogger implements ApplicationRunner {
    private static final Logger log =
            LoggerFactory.getLogger(ActiveProfileLogger.class);

    private final Environment environment;

    public ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles()));
    }
}
```

Ví dụ cần các import `ApplicationArguments`, `ApplicationRunner`, `Component`, `Environment`, `Logger`, `LoggerFactory` và `Arrays`. Trong ứng dụng thực tế, chỉ ghi log những thông tin cấu hình không nhạy cảm. Không in toàn bộ Environment vì có thể chứa token, mật khẩu hoặc thông tin kết nối.

Nếu kết quả là mảng rỗng, kiểm tra `SPRING_PROFILES_ACTIVE`, tham số `--spring.profiles.active`, cấu hình triển khai và profile mặc định. Nếu có nhiều profile, kiểm tra thứ tự của chúng vì profile được kích hoạt sau có thể ghi đè giá trị từ profile trước.

## 8. Xác minh giá trị thuộc tính thực tế

Spring Boot Actuator có endpoint `env` để xem các property source và endpoint `configprops` để xem các bean được binding từ cấu hình. Trong môi trường kiểm thử, có thể expose có kiểm soát:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,metrics
```

Ví dụ kiểm tra một thuộc tính cụ thể qua endpoint:

```text
GET /actuator/env/resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold
```

Kết quả có thể cho biết giá trị được resolve và nguồn property source đã cung cấp nó. `configprops` hữu ích khi cần kiểm tra đối tượng cấu hình đã binding. Tên endpoint, cấu trúc kết quả và chính sách hiển thị giá trị có thể thay đổi theo phiên bản Spring Boot.

Chỉ expose `env` và `configprops` trong môi trường được kiểm soát và bảo vệ bằng xác thực, phân quyền. Các endpoint này có thể tiết lộ thông tin nội bộ; Spring Boot cũng có cơ chế che giá trị nhạy cảm, nhưng không nên dựa vào việc che tự động để mở chúng công khai. Production thường chỉ expose endpoint thật sự cần thiết cho giám sát.

Đối với thuộc tính không nhạy cảm, có thể kiểm tra trực tiếp qua `Environment`:

```java
String threshold = environment.getProperty(
        "resilience4j.circuitbreaker.instances.inventory.failure-rate-threshold");
log.info("Inventory failure threshold: {}", threshold);
```

Đoạn kiểm tra này cho biết giá trị đã resolve từ Environment. Nó không chứng minh mọi bean đã được tạo theo giá trị đó nếu cấu hình bị đọc thủ công hoặc một `Customizer` thay đổi builder sau đó. Khi cần xác minh cuối cùng, hãy kiểm tra bean/registry hoặc hành vi thực tế của breaker.

## 9. Xác minh cấu hình Resilience4j và hành vi breaker

Nếu ứng dụng sử dụng trực tiếp `CircuitBreakerRegistry`, có thể đọc cấu hình của instance sau khi registry đã tạo breaker:

```java
CircuitBreaker breaker = circuitBreakerRegistry.circuitBreaker("inventory");
CircuitBreakerConfig config = breaker.getCircuitBreakerConfig();

log.info("Inventory failure threshold: {}",
        config.getFailureRateThreshold());
log.info("Inventory sliding window size: {}",
        config.getSlidingWindowSize());
log.info("Inventory minimum calls: {}",
        config.getMinimumNumberOfCalls());
log.info("Inventory slow-call threshold: {}",
        config.getSlowCallRateThreshold());
```

Cách đọc registry này áp dụng khi ứng dụng có quyền truy cập `CircuitBreakerRegistry` của Resilience4j. Với Spring Cloud CircuitBreaker, factory quản lý việc tạo breaker và không phải lúc nào cũng expose registry trực tiếp cho mã ứng dụng; khi đó dùng property origin, metrics và kiểm thử hành vi thay vì giả định có thể inject registry.

Để kiểm tra hành vi, dùng dịch vụ giả lập và thực hiện các bước:

1. Khởi động ứng dụng với profile `dev`; xác nhận active profile và giá trị ngưỡng/thời gian chờ resolve đúng với `application-dev.yml`.
2. Cho dependency trả lỗi có kiểm soát, gửi đủ số lời gọi tối thiểu và xác nhận breaker `inventory` chuyển sang `OPEN` theo ngưỡng của profile.
3. Gửi thêm request khi mạch đang `OPEN`; xác nhận request tới dependency bị chặn và fallback trả kết quả đúng.
4. Khởi động lại với profile `prod`; xác nhận giá trị từ file production đã được nạp và các tham số của deployment không vô tình ghi đè.
5. Chờ hết `waitDurationInOpenState`, cho dependency phục hồi và xác nhận các lời gọi thăm dò trong `HALF_OPEN` đưa breaker trở lại `CLOSED`.
6. Đối chiếu property origin, metrics, log và số request thực tế ở mock server để tìm sai lệch giữa cấu hình mong muốn và cấu hình đang chạy.

Không chỉ nhìn vào một giá trị trong `/actuator/env`. Một kiểm tra đáng tin cậy cần kết hợp profile đang hoạt động, nguồn property đã resolve, cấu hình instance và hành vi của Circuit Breaker.

## 10. Quy trình điều tra khi cấu hình không có hiệu lực

Khi giá trị đang chạy khác với file cấu hình, hãy kiểm tra theo thứ tự:

- Xác nhận đúng artifact và đúng môi trường triển khai đang chạy.
- Xác nhận profile đang hoạt động và các profile bổ sung.
- Kiểm tra file profile có nằm đúng vị trí mà Spring Boot tìm kiếm và có tên chính xác `application-{profile}.yml` hay không.
- Kiểm tra biến môi trường, JVM system property, `SPRING_APPLICATION_JSON` và tham số dòng lệnh có ghi đè thuộc tính hay không.
- Kiểm tra ID trong lời gọi `create(...)` có khớp với ID trong cấu hình Resilience4j hay không.
- Kiểm tra cấu hình theo instance, group và mặc định của Spring Cloud CircuitBreaker; kiểm tra `Customizer` nếu dự án có dùng.
- Dùng Actuator hoặc log có chọn lọc để xác định property source và giá trị đã binding.
- Chạy kịch bản lỗi có kiểm soát để xác nhận breaker mở, từ chối request và phục hồi đúng thời gian.

Không sửa ngưỡng chỉ để làm cho dashboard trông ổn định. Hãy tìm nguồn ghi đè trước, sau đó điều chỉnh đúng nguồn cấu hình được nhóm vận hành quản lý.

## 11. Lỗi thường gặp

- Đặt `spring.profiles.active` trong document chỉ được kích hoạt bởi profile khác, khiến cấu hình profile không hợp lệ hoặc không được nạp như mong muốn.
- Nghĩ rằng file `application-prod.yml` luôn được dùng dù profile `prod` chưa được kích hoạt.
- Để biến môi trường hoặc tham số dòng lệnh ghi đè file YAML mà không biết.
- Dùng ID khác nhau giữa factory, Circuit Breaker instance và TimeLimiter instance.
- Đặt cùng một giá trị trong YAML, `Customizer` và biến môi trường nhưng không xác định nguồn nào là chủ đạo.
- Chỉ xem file cấu hình mà không kiểm tra profile, property source và giá trị runtime.
- Expose `/actuator/env` hoặc `/actuator/configprops` công khai, làm lộ thông tin nội bộ.
- Dùng cùng ngưỡng dev và production dù lưu lượng, SLA và thời gian phục hồi của hai môi trường khác nhau.

## Tài liệu tham khảo

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profile, file cấu hình, property source, thứ tự ưu tiên và biến môi trường.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profile và điều kiện profile trong YAML document.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): cấu hình mặc định, group, instance, properties và Customizer.
- [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint `env`, `configprops`, `metrics` và kiểm soát exposure.
