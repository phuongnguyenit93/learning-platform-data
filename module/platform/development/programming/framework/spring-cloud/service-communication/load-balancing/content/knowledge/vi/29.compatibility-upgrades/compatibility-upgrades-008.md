# Kiểm thử hồi quy cấu hình, lỗi, metrics và phân phối tải

Một lần nâng cấp Spring Boot hoặc Spring Cloud có thể biên dịch thành công nhưng làm thay đổi hành vi của **Spring Cloud LoadBalancer**: cấu hình không còn được bind, supplier chain bị thay thế, exception mapping đổi, retry bật/tắt khác trước, metrics không còn xuất hiện hoặc request dồn vào một vài **ServiceInstance**. Những thay đổi này thường không được phát hiện bởi một bài test “ứng dụng khởi động được” hay một request HTTP đơn lẻ.

Bài thuộc chương **Tương thích và nâng cấp** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là xây dựng **bộ kiểm thử hồi quy trước và sau nâng cấp** cho cấu hình, lỗi, Micrometer metrics và phân phối tải; áp dụng với RestClient, WebClient và OpenFeign. Ta sẽ khóa dependency bằng Spring Cloud BOM, kiểm tra compatibility matrix, tạo hai backend có bộ đếm, xác minh lỗi/retry, kiểm tra meter và so sánh phân phối request theo baseline.

> **Nguyên tắc:** một nâng cấp chỉ được chấp nhận khi các contract quan trọng vẫn đúng: ứng dụng dùng đúng bộ version tương thích, LoadBalancer đọc đúng cấu hình, lỗi được phân loại đúng, metrics vẫn phản ánh hành vi mong muốn và lưu lượng được phân phối trong ngưỡng đã định. So sánh **baseline và target bằng cùng kịch bản** để phát hiện thay đổi hành vi.

## 1. Phạm vi hồi quy cần bảo vệ

| Nhóm | Câu hỏi phải trả lời | Bằng chứng cần có |
|---|---|---|
| Version compatibility | Spring Boot và Spring Cloud release train có tương thích không? | BOM, dependency graph, startup/compatibility verifier |
| Configuration binding | Retry, cache, health, zone, metrics properties còn được nhận không? | Context startup và assertion effective configuration |
| Supplier/selection | Cùng service ID có cùng tập ứng viên/chính sách chọn không? | Test hai instance, selected instance và handler counts |
| HTTP errors | 400/404/503, connect failure, timeout có giữ contract không? | Status, exception type/cause và error response |
| Retry | Retry có đúng điều kiện, budget và method không? | Request count tại backend, attempt count |
| Metrics | Meter names, tags và counts còn đúng không? | MeterRegistry assertions và scrape output |
| Distribution | Request còn phân phối theo thuật toán/weight mong muốn không? | Counter từng backend và tỷ lệ theo ngưỡng |
| Performance/freshness | Cache, discovery, timeout và latency có hồi quy không? | p95/p99, source reads, stale window |
| Runtime compatibility | RestClient, WebClient, Feign integration còn hoạt động không? | Integration tests theo từng HTTP client |

Ưu tiên **contract mà ứng dụng phụ thuộc**: service ID, tập đích được phép, số request, response/error semantics, metric vận hành và ngưỡng phân phối. Không cần assert mọi chi tiết nội bộ của Spring Cloud nếu chi tiết đó không phải contract của ứng dụng.

## 2. Chốt version baseline trước khi nâng cấp

Spring Cloud phát hành theo **release train BOM**, mỗi train quản lý một tập version project đã được tuyển chọn. Không nên nâng riêng **spring-cloud-loadbalancer** hoặc **spring-cloud-commons** lên version mới trong khi giữ các module Spring Cloud còn lại ở train cũ.

Bảng compatibility chính thức hiện liệt kê các mapping tiêu biểu:

| Spring Cloud release train | Spring Boot generation tương thích | Ghi chú |
|---|---|---|
| **2025.1.x (Oakwood)** | Boot 4.0.x; Boot 4.1.x từ 2025.1.2 | Train mới trên trang Spring Cloud |
| **2025.0.x (Northfields)** | Boot 3.5.x | Kiểm tra support policy trước khi chọn |
| **2024.0.x (Moorgate)** | Boot 3.4.x | Kiểm tra support policy trước khi chọn |
| **2023.0.x (Leyton)** | Boot 3.2.x; Boot 3.3.x từ 2023.0.2 | Train cũ; xem trạng thái EOL |
| **2022.0.x (Kilburn)** | Boot 3.0.x; Boot 3.1.x từ 2022.0.3 | Train cũ |
| **2021.0.x (Jubilee)** | Boot 2.6.x, 2.7.x | Train cũ |
| Các train cũ hơn | Theo mapping của release tương ứng | Phần lớn đã hết vòng đời hỗ trợ |

Bảng này **không thay thế trang hỗ trợ tại thời điểm nâng cấp**. Trang Spring Cloud hiện hiển thị 2025.1.4 là stable train mới nhất; các train có dấu sao trong bảng tương thích đã được đánh dấu EOL. Một release train có thể tương thích về kỹ thuật nhưng đã hết hỗ trợ OSS. Luôn chọn service release mới nhất trong train còn được hỗ trợ, đọc release notes và kiểm tra mapping chính thức trước khi sửa build.

Nguồn: https://spring.io/projects/spring-cloud/

### Ví dụ Gradle dùng BOM

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

ext {
    springCloudVersion = '2025.1.4'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là ví dụ minh họa cho Spring Boot 4.1.x với Spring Cloud 2025.1.x; train này hỗ trợ Boot 4.1.x từ 2025.1.2. Không coi các version ví dụ là yêu cầu cho mọi dự án. Hãy chọn **cặp version phù hợp với baseline/target** và dùng latest patch được hỗ trợ trong release train đã chọn.

### Những điều không nên làm trong một lần nâng cấp

- Override version riêng của **spring-cloud-commons**, **spring-cloud-loadbalancer**, **spring-cloud-openfeign** mà không có lý do tương thích được xác minh.
- Trộn starter từ nhiều release train.
- Đưa version Spring Framework hoặc Reactor riêng lẻ để “sửa nhanh” lỗi dependency convergence.
- Tắt compatibility verifier chỉ để ứng dụng khởi động.
- Chỉ xem build file mà không xem **dependency graph thực tế**.

## 3. Lập baseline và target có thể tái lập

Trước khi thay version, lưu lại kết quả baseline:

~~~text
baseline/
  boot-version.txt
  spring-cloud-train.txt
  dependencies.txt
  startup.log
  configuration-report.txt
  error-contract.json
  metrics-snapshot.txt
  distribution.csv
  latency.csv
~~~

Sau khi nâng cấp, tạo cùng bộ dữ liệu cho target. Mỗi lần chạy cần ghi Git commit/build identifier, JDK/runtime, Boot và Cloud versions, HTTP connector, discovery implementation, số instance, cache/health/retry configuration, test seed/concurrency/request count và kết quả logs/traces.

**Không so sánh hai lần chạy với điều kiện khác nhau.** Nếu baseline có hai instance healthy, target có một instance hoặc concurrency khác, chênh lệch phân phối không thể quy trực tiếp cho nâng cấp.

| Thuộc tính | Baseline | Target | Tiêu chí |
|---|---|---|---|
| Boot / Cloud BOM | Version đang chạy | Version đề xuất | Tương thích theo matrix |
| Dependency tree | Đã lưu | Đã lưu | Không có version drift ngoài dự kiến |
| Retry | Số retry/status/method | Cấu hình target | Cùng contract |
| Cache | TTL/implementation | Cấu hình target | Stale window trong SLO |
| Errors | Mapping status/cause | Mapping target | Không đổi ngoài chủ đích |
| Metrics | Meter names/counts/tags | Metrics target | Không mất tín hiệu |
| Distribution | A/B counters | A/B counters | Nằm trong ngưỡng |
| Latency | p50/p95/p99 | p50/p95/p99 | Không vượt regression budget |

## 4. Dependency convergence và startup compatibility

Một dependency graph lệch có thể khiến API compile được nhưng runtime nạp class không tương thích. Trong CI, xuất dependency report trước và sau nâng cấp:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-loadbalancer --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn help:effective-pom
~~~

Kiểm tra:

- Chỉ một Spring Cloud release train BOM đang quản lý các module Cloud.
- Không có module Spring Cloud bị override ngoài BOM mà không có quyết định được ghi nhận.
- Spring Boot, Spring Framework, Reactor, Micrometer và HTTP client được quản lý theo bộ version tương thích.
- Các dependency optional (Caffeine, Actuator, OpenFeign, discovery client) không vô tình biến mất khỏi target.
- Không có dependency cũ kéo theo Spring Cloud Commons version khác.

Spring Cloud có compatibility verifier để phát hiện một số cặp version không tương thích. Khi startup báo mismatch, sửa cặp version theo release train. **Không tắt verifier chỉ để bỏ qua lỗi.** Chỉ override verifier khi đã có lý do kỹ thuật, mapping được kiểm chứng và policy quản trị chấp thuận.

## 5. Khóa configuration contract trước khi nâng cấp

Các property ảnh hưởng trực tiếp đến hành vi LoadBalancer:

~~~yaml
spring:
  cloud:
    loadbalancer:
      enabled: true
      cache:
        enabled: true
        ttl: 20s
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
        retry-on-all-operations: false
      stats:
        micrometer:
          enabled: true
        include-path: false
~~~

Đây là cấu hình minh họa, cần đối chiếu effective properties với version đang dùng. **retry.enabled**, **cache.enabled** và **stats.micrometer.enabled** là các property global; không giả định mọi property đều override per-client theo cùng cách. Tài liệu LoadBalancer phân biệt property global và prefix per-client **spring.cloud.loadbalancer.clients.<clientId>.***.

Nguồn: https://docs.spring.io/spring-cloud-commons/reference/configprops.html

### Ma trận cấu hình và hành vi cần test

| Cấu hình | Hành vi kỳ vọng | Phép kiểm thử |
|---|---|---|
| loadbalancer.enabled | Client dùng LB hoặc không dùng LB | Gọi service ID và kiểm tra destination |
| cache.ttl | Danh sách instance có tuổi cache theo TTL | Warm cache, đổi nguồn, đo hội tụ |
| retry.enabled | Có/không retry theo tích hợp | Backend request counter |
| max-retries-on-next-service-instance | Giới hạn retry sang instance khác | A/B fail/success và đếm |
| retryable-status-codes | Chỉ status được phép mới retry | 503 retry, 400 không retry |
| retry-on-all-operations | Cho phép/không cho retry method ngoài GET | Test POST và idempotency |
| health-check.interval | Chu kỳ probe | Backend probe counter và thời gian loại |
| zone / hint | Tập ứng viên theo chính sách | Assert candidate/selected instance |
| stats.micrometer.enabled | Đăng ký meter LB | MeterRegistry assertion |
| stats.include-path | Kiểm soát cardinality tag URI | Kiểm tra meter tags |

**Không chỉ assert property file có chứa giá trị.** Cần chứng minh application context đã bind và hành vi runtime phản ánh cấu hình đó.

### Kiểm tra property bằng Environment

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class LoadBalancerConfigurationRegressionTest {

    @Autowired
    Environment environment;

    @Test
    void criticalLoadBalancerPropertiesRemainConfigured() {
        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.enabled", Boolean.class))
            .isTrue();

        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.retry.enabled", Boolean.class))
            .isTrue();

        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.stats.micrometer.enabled",
            Boolean.class))
            .isTrue();

        assertThat(environment.getProperty(
            "spring.cloud.loadbalancer.retry.max-retries-on-next-service-instance",
            Integer.class))
            .isEqualTo(1);
    }
}
~~~

Test này xác nhận property có trong Environment, **không tự chứng minh từng bean đã dùng nó**. Phải kết hợp integration test hành vi ở những phần sau.

## 6. Tạo fixture hai backend có thể điều khiển

Để kiểm tra lỗi và phân phối tải, cần hai instance có định danh riêng và bộ đếm nhận request. Dùng JDK HttpServer, WireMock hoặc MockWebServer. Mỗi handler nên ghi instanceId, số request đã nhận, HTTP method/path, status trả về, thời gian xử lý và correlation ID nếu cần.

~~~text
catalog-a: http://127.0.0.1:<portA>
catalog-b: http://127.0.0.1:<portB>

catalog-service:
  instance A -> portA
  instance B -> portB
~~~

Các trạng thái fault injection nên điều khiển được:

| Backend mode | Hành vi |
|---|---|
| HEALTHY | HTTP 200, body chứa instanceId |
| UNAVAILABLE | HTTP 503 |
| BAD_REQUEST | HTTP 400 |
| SLOW | Trễ có kiểm soát vượt read timeout |
| CLOSE | Đóng kết nối hoặc reset nếu test server hỗ trợ |
| MALFORMED_BODY | HTTP 200 nhưng body không decode được |

**Đặt counter tại handler**, không chỉ ở mock client. Nếu connect refused hoặc không có instance, handler count của backend không tăng. Nếu server trả 503, handler đã nhận request và count tăng.

## 7. Integration test xác nhận service ID và LoadBalancer còn hoạt động

Với RestClient, tạo builder có **@LoadBalanced**:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("loadBalancedRestClientBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Cấu hình discovery trong test bằng **SimpleDiscoveryClient** và hai URI động. Ví dụ properties khi đã biết cổng:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:18081
              - uri: http://127.0.0.1:18082
~~~

Trong CI nên dùng cổng động qua **@DynamicPropertySource** thay vì cố định cổng để tránh collision. Gửi nhiều request:

~~~java
@Test
void loadBalancedClientCanReachBothHealthyInstances() {
    for (int i = 0; i < 100; i++) {
        catalogRestClient.get()
            .uri("/api/whoami")
            .retrieve()
            .toBodilessEntity();
    }

    assertThat(receivedA.get() + receivedB.get()).isEqualTo(100);
    assertThat(receivedA.get()).isPositive();
    assertThat(receivedB.get()).isPositive();
}
~~~

Đây là assertion tối thiểu: **cả hai instance đều được sử dụng**. Phần phân phối tải sẽ đặt ngưỡng định lượng riêng; không dùng test này làm bằng chứng tỷ lệ chính xác.

Sau nâng cấp, nếu tất cả request chỉ tới A, kiểm tra supplier còn trả A/B không, service ID có đổi không, health/zone/hint filter có loại B không, cache có giữ snapshot cũ không, @LoadBalanced có còn áp dụng đúng bean không, hoặc HTTP client có chuyển sang URL cố định và bypass LB không.

## 8. Regression test cho HTTP errors

Cần khóa cả **status trả về** lẫn **exception/error mapping** của client. Ví dụ với RestClient và backend chủ động trả 503. Test này chạy trong context có retry disabled, chẳng hạn cấu hình test `spring.cloud.loadbalancer.retry.enabled=false`, để chỉ đo một response:

~~~java
@Test
void mapsServiceUnavailableFromBackend() {
    backendA.setMode(BackendMode.UNAVAILABLE);
    backendB.setMode(BackendMode.UNAVAILABLE);

    assertThatThrownBy(() ->
        catalogRestClient.get()
            .uri("/api/items/42")
            .retrieve()
            .body(String.class)
    ).isInstanceOf(HttpServerErrorException.ServiceUnavailable.class);

    // Test context này tắt LoadBalancer retry để chỉ đo một HTTP response.
    assertThat(receivedA.get() + receivedB.get()).isEqualTo(1);
}
~~~

Với ứng dụng thực, exception có thể được adapter chuyển thành `DownstreamCallException` hoặc lỗi nghiệp vụ. Khi nâng cấp, hãy assert **exception ứng dụng mà business layer cam kết**, không phụ thuộc quá sâu vào class exception nội bộ nếu adapter được thiết kế để che chi tiết HTTP client.

### Ma trận lỗi tối thiểu

| Fault | Backend received | Kỳ vọng caller | Retry |
|---|---:|---|---|
| HTTP 400 | 1 | Validation/rejected | Không retry |
| HTTP 401/403 | 1 | Auth/authorization failure | Không retry cùng credential |
| HTTP 404 theo contract | 1 | Resource not found hoặc Optional.empty | Không retry |
| HTTP 409 | 1 | Conflict | Theo contract |
| HTTP 429 | 1 mỗi attempt | Rate limited | Có điều kiện theo Retry-After/budget |
| HTTP 503 | 1 mỗi attempt | Downstream unavailable | Chỉ khi policy cho phép |
| Connect refused | 0 ở handler đích | Transport failure | Có điều kiện |
| Read timeout sau nhận request | ≥1 | Timeout, outcome có thể UNKNOWN | Thận trọng với POST |
| Không có ServiceInstance | 0 | No-instance/LB failure | Theo discovery policy |
| 2xx body sai schema | 1 | Decode/contract failure | Thường không retry mù |

Một response 503 từ backend và tình huống không tìm được instance có thể cùng kết thúc bằng lỗi phía caller nhưng khác nguồn. Hãy kiểm tra handler count và LoadBalancer discard metric để phân biệt.

Để so sánh giữa các client, lưu ý các exception ở transport khác nhau:

| Client | HTTP response lỗi | Lỗi trước/ngoài HTTP response |
|---|---|---|
| RestClient | RestClientResponseException và subclass | ResourceAccessException hoặc cause I/O |
| WebClient | WebClientResponseException và subclass | WebClientRequestException, timeout/cancel signal |
| OpenFeign | FeignException và subclass | RetryableException hoặc exception do ErrorDecoder/transport phát ra |

Không bắt buộc các class này giống nhau. Nếu ứng dụng có adapter chung, test application error model sau adapter; đồng thời giữ một số integration tests để phát hiện thay đổi exception mapping của từng client.

## 9. Regression test retry và idempotency

Chỉ bật một tầng retry trong mỗi test để đo kết quả rõ ràng. Ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 503
        retry-on-all-operations: false
~~~

Các test cần có:

1. A trả 503, B trả 200: pin lần chọn đầu vào A (hoặc dùng supplier test có thứ tự xác định), sau đó xác minh caller retry sang B và handler counters ghi nhận cả hai request.
2. A/B đều 503: caller dừng trong budget, không retry vô hạn.
3. 400: không retry.
4. GET: retry theo policy được phép.
5. POST: không retry khi `retry-on-all-operations=false`, trừ khi có contract/idempotency được thiết kế rõ.
6. Timeout sau khi server commit: outcome phải được xem xét là UNKNOWN; không tạo operation key mới cho retry cùng business intent.

**Đừng giả định max-retries-on-next-service-instance bằng một thì tổng số HTTP requests luôn bằng hai.** Lỗi có thể xảy ra trước backend; retry có thể không đủ điều kiện; transport/gateway có thể thêm retry. Đếm ở handler từng instance.

### Assertion cho budget

~~~java
@Test
void retryBudgetDoesNotCreateUnexpectedBackendRequests() {
    backendA.setMode(BackendMode.UNAVAILABLE);
    backendB.setMode(BackendMode.UNAVAILABLE);

    callThroughApplicationPort();

    assertThat(receivedA.get() + receivedB.get())
        .isLessThanOrEqualTo(EXPECTED_MAX_BACKEND_RECEIPTS);
}
~~~

`EXPECTED_MAX_BACKEND_RECEIPTS` phải được xác định theo policy/HTTP integration đang kiểm tra, không copy một con số cố định nếu còn tầng retry khác.

Đối với POST, cần đo thêm số side effects đã commit. Hai HTTP requests có thể chỉ tạo một giao dịch nếu idempotency được bảo đảm bằng shared store/unique key; ngược lại một timeout sau commit có thể làm retry tạo dữ liệu trùng.

## 10. Kiểm tra Micrometer LoadBalancer metrics

Spring Cloud LoadBalancer cung cấp `MicrometerStatsLoadBalancerLifecycle`. Để kích hoạt, cần có `MeterRegistry` và bật:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false
~~~

Với Actuator/Micrometer được cấu hình phù hợp, các meter hiện hành gồm:

| Meter | Loại | Ý nghĩa |
|---|---|---|
| `loadbalancer.requests.active` | Gauge | Số request đang active theo service/instance tags khi có |
| `loadbalancer.requests.success` | Timer | Request kết thúc bằng việc chuyển response cho HTTP client |
| `loadbalancer.requests.failed` | Timer | Request kết thúc bằng exception |
| `loadbalancer.requests.discard` | Counter | Request bị discard vì không lấy được instance để chạy |

**Lưu ý semantics quan trọng:** `loadbalancer.requests.success` không đồng nghĩa HTTP status nghiệp vụ là 2xx. Nếu LoadBalancer chọn instance và HTTP client nhận được response HTTP 503, LoadBalancer lifecycle vẫn có thể coi việc chuyển response xuống client là thành công. Hãy dùng metrics HTTP/server riêng để theo dõi status 4xx/5xx.

Metrics có thể được đăng ký **sau khi có record đầu tiên**; test không nên đòi meter tồn tại trước khi phát sinh request.

### Test MeterRegistry

~~~java
@Autowired
MeterRegistry meterRegistry;

@Test
void recordsLoadBalancerMetricsAfterRequest() {
    Timer successBefore = meterRegistry.find(
        "loadbalancer.requests.success").timer();

    long before = successBefore == null ? 0 : successBefore.count();

    callThroughApplicationPort();

    Timer successAfter = meterRegistry.find(
        "loadbalancer.requests.success").timer();

    assertThat(successAfter).isNotNull();
    assertThat(successAfter.count()).isGreaterThan(before);
}
~~~

Đây là mẫu minh họa; cần có Actuator/Micrometer và stats được bật. Với `MeterRegistry` được chia sẻ trong Spring context, không nên `clear()` tùy tiện nếu test khác dùng chung registry. Lấy snapshot count trước request rồi assert count tăng, hoặc tạo context/registry riêng cho từng test.

Với no-instance scenario, kiểm tra `loadbalancer.requests.discard` tăng nếu integration phát meter tương ứng. Với connect/timeout, kiểm tra failed timer và exception trace. Không giả định mọi client implementation cung cấp đầy đủ cùng một tag set; một số blocking integrations có thể không có request/response data.

### Tránh cardinality cao

`uri` tag có thể chứa path. Với path động như `/orders/12345`, metrics có thể tạo vô số series. Property `spring.cloud.loadbalancer.stats.include-path=false` giúp không đưa path vào URI tag theo cấu hình hỗ trợ. **Không thêm instance ID, request ID, user ID hoặc raw URL có query token vào metric tags.**

## 11. Kiểm tra phân phối tải trên hai instance

Đối với Round Robin với hai instance healthy và sequential requests, kỳ vọng tỷ lệ gần cân bằng. Với `N` request:

~~~text
total = countA + countB
ratioA = countA / total
ratioB = countB / total
imbalance = abs(countA - countB) / total
~~~

Ví dụ test 1.000 request:

~~~java
@Test
void distributesSequentialRequestsAcrossTwoInstances() {
    int total = 1000;

    for (int i = 0; i < total; i++) {
        callThroughApplicationPort();
    }

    int a = receivedA.get();
    int b = receivedB.get();

    assertThat(a + b).isEqualTo(total);

    double ratioA = (double) a / total;
    double ratioB = (double) b / total;

    assertThat(ratioA).isBetween(0.45, 0.55);
    assertThat(ratioB).isBetween(0.45, 0.55);
}
~~~

Ngưỡng 45–55% là **ví dụ cho test sequential với Round Robin**, không phải SLO mặc định. Nếu dùng RandomLoadBalancer, Weighted supplier, zone preference, sticky session, subset, retry hoặc concurrent calls, hãy thiết kế ngưỡng theo thuật toán và workload thực tế.

### Test weighted routing

Nếu cấu hình weighted và metadata A:B là 80:20, không nên assert đúng từng request theo chu kỳ 4:1 nếu thuật toán/implementation không cam kết chu kỳ cố định. Với số mẫu đủ lớn, assert trong khoảng thống kê có biên an toàn:

~~~text
expected A share ≈ 0.80
expected B share ≈ 0.20
~~~

Ngưỡng phải tính theo số mẫu, chính sách random/weighted và mức false-failure chấp nhận được. Với deterministic weighted algorithm, có thể assert kết quả chính xác hơn nếu contract của phiên bản đã được kiểm tra.

### Khi phân phối tải thay đổi sau upgrade

Kiểm tra theo thứ tự:

1. Candidate list trước và sau có cùng A/B không?
2. Có thay đổi metadata weight hoặc zone không?
3. Thuật toán có còn Round Robin hay custom LoadBalancer đã bị mất?
4. Sticky session/hint/header có thay đổi không?
5. Retry có làm một số instance nhận nhiều request hơn không?
6. Có backend response chậm khiến concurrency hoặc timeout khác nhau không?
7. Counter có tính health probes và requests ngoài test không?

Không vội kết luận thuật toán bị regression chỉ từ một lần test ít request. Lặp nhiều run với cùng điều kiện và ghi phân phối.

## 12. Regression test cache và health check

Cache và health check có thể làm thay đổi tập ứng viên dù config không đổi. Bộ test nên kiểm tra:

- TTL và cache enabled/disabled theo đúng service client.
- Source update có được phản ánh sau TTL/refresh như baseline không.
- Không có double caching không mong muốn.
- Instance unhealthy có bị loại trong thời gian SLO không.
- Khi không có healthy instance, fallback behavior có giữ contract không.
- Cache/health supplier chain không bị thay thế khi custom configuration được nạp.

Ví dụ kịch bản:

~~~text
t0: source = [A, B], warm cache
t1: B bị deregister hoặc health=DOWN
t2: caller vẫn có thể thấy stale [A, B]
t3: sau expiry/refetch/health refresh, candidate list = [A]
~~~

Test không nên assert đúng một mốc mili giây trên CI. Hãy dùng deadline hữu hạn, poll candidate list và đo detection delay. Nếu release mới thay đổi default TTL/health behavior, explicit configuration và test sẽ giúp phát hiện sớm.

## 13. So sánh RestClient, WebClient và OpenFeign

Cả ba có thể đi qua Spring Cloud LoadBalancer nhưng integration và lỗi có khác biệt:

| Client | Tích hợp LB thường dùng | Regression cần kiểm tra |
|---|---|---|
| RestClient | `@LoadBalanced RestClient.Builder` | Request factory, URI rewrite, exception, lifecycle metrics |
| WebClient | `@LoadBalanced WebClient.Builder` hoặc LoadBalancer exchange filter | Subscription/retry, Reactor errors, timeout, cancellation |
| OpenFeign | `@FeignClient(name = "...")` cùng Spring Cloud LoadBalancer | Client bean, Retryer/ErrorDecoder, transport, URL override |

Một client có URL cố định hoặc được tạo không qua integration có thể bypass service ID/LB. Sau nâng cấp hãy kiểm tra request thực đến A/B, không chỉ kiểm tra annotation còn tồn tại.

### Một contract chung cho ba client

Cùng một test fixture nên xác minh:

- Cùng service ID logic.
- Cùng tập instance được phép.
- Cùng HTTP status/error semantics theo adapter contract.
- Retry policy không bị bật khác nhau ngoài chủ đích.
- Metrics/trace được phát sinh hoặc có giải pháp quan sát tương đương.
- Tổng backend requests và phân phối không vượt regression budget.

Không ép exception class của ba client phải giống nhau nếu adapter chưa chuẩn hóa; thay vào đó assert **application error model** ở tầng business.

## 14. Regression test cho configuration theo từng service ID

Spring Cloud LoadBalancer tạo child context riêng cho mỗi service ID. Một custom config bị component-scan nhầm có thể ảnh hưởng nhiều client.

Kiểm tra:

- `@LoadBalancerClient(name = "catalog-service", ...)` chỉ tác động đúng service ID.
- Configuration class không bị scan như bean global ngoài ý muốn.
- Supplier/custom algorithm còn tồn tại sau upgrade.
- Prefix `spring.cloud.loadbalancer.clients.<clientId>.*` override đúng property.
- Property global không bị hiểu nhầm là property per-client.

Tài liệu LoadBalancer ghi rõ một số property như `enabled`, `retry.enabled`, `cache.enabled` và `stats.micrometer.enabled` là global; cách override theo client không giống tất cả property khác.

Nguồn: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html

## 15. Kiểm thử metrics và distribution trên cùng workload

Một workload kiểm thử có thể gửi 1.000 GET request tới service ID. Thu thập đồng thời:

| Signal | Nguồn |
|---|---|
| Logical calls | Test driver |
| Backend received A/B | Handler counters |
| HTTP 2xx/4xx/5xx | Client/server metrics |
| LB success/failed/discard | Micrometer LoadBalancer lifecycle |
| Selected instance | Trace/log hoặc request transformer |
| p50/p95/p99 | Timer/histogram |
| Retry count | Retry instrumentation |
| Candidate list | Discovery/supplier observation |

**Không cộng các meter khác bản chất vào một “request total” duy nhất.** `loadbalancer.requests.success` là timer, `loadbalancer.requests.discard` là counter; backend handler count là số request thực nhận; client attempts là số lần thử. Hãy đối chiếu các tín hiệu bằng correlation/trace ID hoặc cùng test window.

Ví dụ kết quả baseline/target:

| Chỉ số | Baseline | Target | Đánh giá |
|---|---:|---:|---|
| Backend A received | 502 | 498 | Trong ngưỡng |
| Backend B received | 498 | 502 | Trong ngưỡng |
| Total backend received | 1.000 | 1.000 | Giữ nguyên |
| HTTP 5xx | 0 | 0 | Không tăng |
| LB discard | 0 | 0 | Không mất instance |
| p95 latency | 42 ms | 46 ms | Tăng 9,5%, so với budget |
| Retry count | 0 | 0 | Không đổi |

Các số trong bảng là **dữ liệu giả lập để minh họa cách báo cáo**, không phải benchmark của Spring Cloud.

## 16. Pipeline CI trước và sau nâng cấp

Một pipeline hợp lý có các stage:

~~~mermaid
flowchart TD
    A["Resolve BOM and dependency graph"] --> B["Compatibility verifier + application startup"]
    B --> C["Configuration binding regression"]
    C --> D["HTTP error and retry contracts"]
    D --> E["Metrics assertions"]
    E --> F["Two-instance distribution test"]
    F --> G["Cache/health/failure injection"]
    G --> H["Performance smoke and report"]
    H --> I{"All regression budgets pass?"}
    I -->|Yes| J["Canary / staged rollout"]
    I -->|No| K["Block upgrade; inspect diff"]
~~~

### Bộ test theo tầng

| Stage | Loại test | Mục tiêu |
|---|---|---|
| Compile | Compile/test compile | Phát hiện API/binary break |
| Dependency | Dependency tree/convergence | Phát hiện version drift |
| Context | Startup/compatibility verifier | Phát hiện mismatch và bean wiring |
| Configuration | Effective properties | Phát hiện property không bind |
| Unit | Error mapper/retry decision | Khóa business semantics |
| Integration | Hai backend + LoadBalancer | Xác minh service ID và instance selection |
| Observability | MeterRegistry/scrape | Giữ metric contracts |
| Distribution | 500–1.000+ requests | Phát hiện skew |
| Fault injection | 503/timeout/no-instance | Kiểm tra lỗi và recovery |
| Performance smoke | p95/p99 | Phát hiện latency regression |

Không chạy test phân phối tải trong một environment nhiễu rồi dùng kết quả đơn lẻ để chặn mọi nâng cấp. Tách smoke test deterministic và performance test có kiểm soát.

## 17. Quy trình nâng cấp có kiểm soát

1. **Chọn release train tương thích** theo Spring Boot version và support policy.
2. **Lưu baseline** dependency graph, properties, metrics, error matrix và distribution.
3. **Nâng BOM trong branch riêng**, không đổi từng Spring Cloud module độc lập.
4. **Chạy compile và startup** để phát hiện API/compatibility issues.
5. **Chạy configuration + integration regression** với cùng test fixture.
6. **So sánh metrics và distribution** với baseline, áp dụng regression budget.
7. **Đọc release notes** của train và project liên quan (Commons, LoadBalancer, OpenFeign, discovery client).
8. **Canary một nhóm caller** và quan sát discard/failed/latency/retry/instance distribution.
9. **Tăng dần traffic** khi metrics ổn định; giữ rollback artifact/BOM.
10. **Ghi lại các thay đổi có chủ đích** (ví dụ default property thay đổi) cùng quyết định chấp nhận.

### Rollback trigger ví dụ

- Compatibility verifier fail hoặc context không khởi động.
- Candidate list rỗng bất thường.
- LB discard tăng vượt baseline.
- Tỷ lệ 5xx/timeout vượt SLO.
- Một instance nhận tỷ lệ traffic vượt ngưỡng đã đặt.
- Retry count tăng mạnh hoặc vượt budget.
- p95/p99 latency vượt regression budget.
- Metrics thiết yếu biến mất hoặc tag cardinality tăng bất thường.

Rollback cần dựa trên metric và thời gian quan sát đã thống nhất, không chỉ một log lẻ.

## 18. Các lỗi nâng cấp thường gặp

1. Nâng Boot nhưng giữ Spring Cloud train không tương thích.
2. Nâng riêng `spring-cloud-loadbalancer` và để Commons/OpenFeign ở version khác.
3. Không dùng BOM hoặc override dependency version không có kiểm soát.
4. Tắt compatibility verifier thay vì sửa version mapping.
5. Property cũ vẫn còn trong YAML nhưng không còn được bind như mong đợi.
6. Property global/per-client bị nhầm prefix.
7. Custom `@LoadBalancerClient` config bị component scan nhầm.
8. Supplier chain thay đổi thứ tự cache/health/filter.
9. Retry default hoặc retry exception whitelist thay đổi.
10. Feign Retryer/ErrorDecoder khác sau nâng cấp.
11. RestClient/WebClient builder mất `@LoadBalanced`.
12. Client có URL cố định và bypass LoadBalancer.
13. Micrometer LoadBalancer stats bị tắt hoặc thiếu MeterRegistry.
14. Metric `success` bị hiểu nhầm là HTTP 2xx.
15. Metric URI chứa path động làm tăng cardinality.
16. Round Robin/weighted/zone policy không còn đúng.
17. Instance metadata weight/zone bị thiếu hoặc đổi key.
18. Cache TTL/default implementation thay đổi.
19. Discovery client có cache riêng dẫn tới double caching.
20. Test chỉ đếm mock invocation mà không đếm backend received.
21. Test phân phối tải assert đúng 50/50 trong mọi thuật toán/concurrency.
22. Không tách lỗi connect, no-instance và backend HTTP 503.
23. Timeout sau side effect bị coi như chắc chắn thất bại rồi retry tạo dữ liệu trùng.
24. Không có baseline để phân biệt regression với biến động tải tự nhiên.
25. Canary quá ngắn hoặc không đủ traffic để phát hiện skew.

## 19. Checklist nghiệm thu

### Version và build

- [ ] Spring Boot/Spring Cloud nằm trong compatibility matrix.
- [ ] Train còn được hỗ trợ và service release có release notes.
- [ ] Spring Cloud BOM quản lý các module cùng train.
- [ ] Dependency tree không có override ngoài dự kiến.
- [ ] Compatibility verifier được giữ hoạt động.

### Cấu hình và supplier

- [ ] Critical properties được bind đúng.
- [ ] Retry/cache/stats global và per-client được phân biệt.
- [ ] Custom LoadBalancer config gắn đúng service ID.
- [ ] Supplier/health/cache/zone/weight chain giữ contract.
- [ ] RestClient/WebClient/Feign thực sự đi qua LoadBalancer.

### Errors và retries

- [ ] 400/401/403/404/409/429/503 có mapping đúng.
- [ ] No-instance khác backend 503.
- [ ] Connect failure khác read timeout.
- [ ] Retry chỉ chạy cho lỗi/method được cho phép.
- [ ] Backend handler count nằm trong retry budget.
- [ ] POST có idempotency nếu được retry.

### Metrics và distribution

- [ ] LoadBalancer Micrometer stats được bật và có MeterRegistry.
- [ ] success/failed/discard/active được hiểu đúng semantics.
- [ ] HTTP status metrics được đo riêng.
- [ ] URI/tag cardinality được kiểm soát.
- [ ] Request counters được đo ở mọi backend instance.
- [ ] Tỷ lệ phân phối nằm trong ngưỡng của thuật toán.
- [ ] p95/p99 và retry rate không vượt budget.

### Release

- [ ] Baseline/target chạy cùng fixture và workload.
- [ ] Regression report được lưu.
- [ ] Canary có rollback triggers.
- [ ] Thay đổi có chủ đích được ghi rõ.

## 20. Kết luận

**Kiểm thử hồi quy nâng cấp Spring Cloud LoadBalancer cần xác minh cả cấu hình lẫn hành vi thực tế.** Compatibility matrix và BOM giúp chọn đúng bộ version; context/property tests phát hiện cấu hình không còn được bind; hai backend có bộ đếm giúp kiểm tra lỗi, retry và phân phối tải; Micrometer giúp phát hiện discard, failed request và latency. Không một kiểm tra đơn lẻ nào thay thế được toàn bộ bằng chứng đó.

Khi nâng cấp RestClient, WebClient hoặc OpenFeign integration, hãy so sánh **cùng service ID, cùng topology, cùng fault injection và cùng workload** giữa baseline và target. Đặc biệt, phân biệt metric LoadBalancer với HTTP status, backend received với client attempts, và phân phối Round Robin với weighted/zone policy. Một upgrade an toàn là upgrade mà các contract đã định vẫn được giữ, mọi khác biệt mới đều có lý do, và canary có đủ tín hiệu để dừng hoặc rollback trước khi lỗi lan rộng.

## Tài liệu tham khảo

- Spring Cloud – Release train / Spring Boot compatibility and BOM: https://spring.io/projects/spring-cloud/
- Spring Cloud Commons – LoadBalancer, supplier configuration, Micrometer statistics and per-client properties: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons – Configuration properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Cloud – Supported versions and support policy: https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions
- Spring Boot – Supported versions and dependency management: https://spring.io/projects/spring-boot




