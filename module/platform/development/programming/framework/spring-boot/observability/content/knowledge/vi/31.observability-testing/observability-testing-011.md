# Test Actuator endpoint trong Spring Boot

Spring Boot Actuator cung cấp endpoint vận hành như health, info, metrics và prometheus. Các endpoint này là giao diện mà Kubernetes, load balancer, monitoring platform và đội vận hành dùng để quan sát trạng thái ứng dụng. Một endpoint xuất hiện trong application không có nghĩa nó đã được expose, được bảo vệ đúng hoặc trả status code đúng trong mọi tình huống. **Test Actuator endpoint** xác minh cả nội dung response, HTTP semantics, exposure, security, health contributors và khả năng tương thích với môi trường triển khai.

Trong module SPRING_BOOT_OBSERVABILITY, testing Actuator là một phần của kiểm thử observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Bài thuộc chương Testing observability, tập trung vào cách kiểm thử Actuator endpoints: test slice và full application context, MockMvc/WebTestClient, health groups, custom indicators, status aggregation, security, metrics/Prometheus, endpoint exposure và production-like smoke tests.

## Mục tiêu học tập

1. Phân biệt endpoint được enable, expose và được phép truy cập.
2. Chọn Spring Boot test slice hoặc full context phù hợp.
3. Kiểm thử health status, contributors, groups và HTTP status mapping.
4. Kiểm thử security, component details và endpoint exposure.
5. Kiểm thử metrics và Prometheus scrape output.
6. Dùng mock/fake dependencies để tạo trạng thái health xác định.
7. Kiểm tra management port, base path và cấu hình theo profile.
8. Thiết kế smoke tests trong container/Kubernetes.
9. Tránh các test flaky do dependency thật, thời gian và môi trường.

## 1. Những gì cần kiểm thử ở Actuator

Một Actuator endpoint có nhiều lớp behavior:

- Endpoint implementation: dữ liệu hoặc thao tác endpoint trả về.
- Enablement: endpoint có được bật trong application context không.
- Exposure: endpoint có được mở qua HTTP/JMX không.
- Security: caller nào được truy cập và xem details.
- HTTP semantics: status code, content type và response body.
- Runtime integration: contributor, registry, exporter và management server.
- Deployment integration: port, base path, network policy và probe configuration.

Một test chỉ kiểm tra JSON body có thể bỏ sót endpoint bị expose sai hoặc security chain cho phép truy cập trái phép.

### 1.1. Enable, expose và authorize

| Khái niệm | Câu hỏi | Cấu hình/kiểm tra |
| --- | --- | --- |
| Enable | Endpoint có được tạo không? | Endpoint availability/configuration |
| Expose | Endpoint có truy cập qua HTTP/JMX không? | management.endpoints.*.exposure |
| Authorize | Caller nào được phép truy cập? | Spring Security |
| Details | Caller có được xem component details? | show-details/show-components |
| Network | Kubelet/monitoring có tới được port không? | Service, port, NetworkPolicy |

Ví dụ endpoint health có thể được enable mặc định và expose qua HTTP, trong khi metrics hoặc env không được expose. Không suy luận exposure từ việc endpoint class có trong classpath.

## 2. Test dependencies và cấu hình cơ bản

Thêm các test dependencies theo Spring Boot BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Với ứng dụng reactive, dùng WebTestClient và các test dependencies tương ứng. Không tự đặt version riêng khi BOM đã quản lý.

Cấu hình production có thể expose health, info và prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never
~~~

Test nên dùng cấu hình rõ ràng và độc lập với production secrets. Không mở rộng exposure trong test rồi mặc định rằng production cũng an toàn.

### 2.1. Test profile

Có thể tạo test properties cho management endpoint:

~~~java
@SpringBootTest(properties = {
    "management.endpoints.web.exposure.include=health,metrics,prometheus",
    "management.endpoint.health.show-details=always"
})
~~~

Chỉ dùng show-details=always trong test context với fixture không nhạy cảm. Test security riêng phải xác minh production policy không để anonymous caller xem details.

## 3. Chọn test style: slice hay full context

| Kiểu test | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| Unit test | Một HealthIndicator/logic riêng | Kiểm tra status mapping, timeout/error |
| @WebMvcTest | MVC/security slice | Test controller/security behavior khi Actuator endpoint được import phù hợp |
| @SpringBootTest + MockMvc | Full application context, mock servlet requests | Kiểm tra Actuator auto-configuration và endpoint exposure |
| @SpringBootTest + RANDOM_PORT | Embedded server thực | Test HTTP server, management port và filters |
| WebTestClient | Reactive hoặc HTTP client test | WebFlux và end-to-end HTTP checks |
| Container/Kubernetes smoke test | Runtime image/cluster | Kiểm tra port, path, network và probes |

Với Actuator auto-configuration, full context thường là lựa chọn rõ ràng nhất cho integration test. Slice test có thể không load endpoint infrastructure hoặc auto-configuration cần thiết nếu cấu hình bị giới hạn.

## 4. Kiểm thử health endpoint bằng MockMvc

Ví dụ integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health",
        "management.endpoint.health.show-details=never"
})
@AutoConfigureMockMvc
class ActuatorHealthEndpointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsUpStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

Test này xác minh endpoint được expose và trả status UP trong test context. Nếu context có database hoặc dependency thật, kết quả có thể phụ thuộc môi trường. Dùng test database hoặc thay dependency bằng fake để có kết quả xác định.

### 4.1. Kiểm tra content type và response contract

Khi client/monitoring phụ thuộc response shape, kiểm tra content type và những field contract cần thiết. Tránh assert toàn bộ JSON nếu response chứa contributors thay đổi theo classpath. Assert các field ổn định như status và component bắt buộc.

### 4.2. Test khi health DOWN

Không ép toàn bộ application context xuống trạng thái lỗi để test một contributor. Thay dependency bằng fake trả failure, sau đó gọi endpoint và xác minh body/status code theo aggregation policy. Health DOWN thường ánh xạ sang HTTP 503, nhưng custom status mapping có thể thay đổi.

## 5. Kiểm thử custom HealthIndicator

Unit test kiểm tra contributor độc lập:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;

import static org.assertj.core.api.Assertions.assertThat;

class SearchHealthIndicatorTest {

    @Test
    void reportsDownWhenSearchIsUnavailable() {
        SearchClient client = () -> false;
        SearchHealthIndicator indicator = new SearchHealthIndicator(client);

        assertThat(indicator.health().getStatus()).isEqualTo(Status.DOWN);
    }
}
~~~

Ví dụ giả định SearchClient có phương thức ping trả boolean. Unit test nên bao phủ:
- dependency trả success;
- dependency trả failure;
- timeout;
- exception;
- response malformed nếu có thể;
- details không chứa secret.

### 5.1. Dùng fake thay vì dependency thật

Fake cho phép test điều khiển trạng thái mà không cần database/broker/search cluster. Ví dụ một fake client có thể chuyển từ available sang unavailable. Tránh gọi dịch vụ bên ngoài trong unit test vì network và trạng thái môi trường làm test không ổn định.

### 5.2. Kiểm tra timeout

HealthIndicator cần timeout hữu hạn. Dùng fake client có delay hoặc test clock để xác minh timeout mapping. Không dùng Thread.sleep dài tùy tiện; nếu không có clock abstraction, dùng timeout ngắn với upper bound hợp lý và cleanup executor.

## 6. Health groups: liveness và readiness

Khi Kubernetes probes được bật, Spring Boot có thể expose:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Test riêng từng group. Một database failure có thể làm readiness DOWN nếu database là dependency bắt buộc, nhưng liveness nên vẫn UP nếu process có thể tiếp tục hoạt động.

~~~java
@SpringBootTest(properties = {
    "management.endpoint.health.probes.enabled=true",
    "management.endpoints.web.exposure.include=health"
})
@AutoConfigureMockMvc
class ActuatorProbeGroupsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void livenessEndpointIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void readinessEndpointIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
    }
}
~~~

Nếu ứng dụng có startup coordinator giữ readiness REFUSING_TRAFFIC, test cần trigger hoặc chờ warm-up completion theo contract. Không giả định readiness luôn UP ngay khi test context được tạo.

### 6.1. Kiểm tra group membership

Tạo một custom indicator chỉ nằm trong readiness group. Cho indicator trả DOWN và xác minh readiness bị ảnh hưởng trong khi liveness vẫn UP. Test này phát hiện cấu hình liveness vô tình phụ thuộc external services.

### 6.2. Kiểm tra status mapping

Xác minh:
- UP trả HTTP success;
- DOWN trả HTTP failure theo mapping;
- OUT_OF_SERVICE được xử lý theo policy;
- custom status có mapping được cấu hình;
- caller đọc status không cần component details nếu đó là probe contract.

## 7. Kiểm thử security và component details

Actuator endpoints có thể tiết lộ database names, internal hosts, disk paths hoặc exception details. Test security cần kiểm tra cả quyền truy cập và dữ liệu trả về.

Ví dụ security filter chain định hướng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ActuatorSecurityConfiguration {
    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/actuator/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic()
                .and()
                .build();
    }
}
~~~

Cú pháp Security DSL có thể khác giữa Spring Security versions; dùng API phù hợp dependency version. Ứng dụng có nhiều filter chains cần đặt @Order để management chain không bắt nhầm business routes.

### 7.1. Anonymous caller

Test caller không xác thực:
- health status tối thiểu được truy cập nếu probe policy cho phép;
- metrics/prometheus và management endpoints khác bị từ chối nếu policy yêu cầu;
- component details không xuất hiện.

### 7.2. Authorized caller

Dùng Spring Security test support để đăng nhập user có role OPS và xác minh endpoint/details theo policy. Cũng test user authenticated nhưng thiếu role để tránh nhầm authenticated với authorized.

### 7.3. Details policy

Cấu hình show-details=when-authorized và show-components=when-authorized nếu muốn chỉ người có quyền xem chi tiết. Test response anonymous không chứa components/details và response authorized chỉ có các fields được duyệt.

Không chỉ kiểm tra HTTP 200/403; kiểm tra JSON body không rò rỉ host, URL, credentials hoặc exception message.

## 8. Kiểm thử endpoint exposure

Expose endpoint qua HTTP được cấu hình riêng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Test endpoint được expose trả response mong đợi, endpoint không expose trả 404 theo behavior/version của framework. Test cả cấu hình profile nếu production dùng profile-specific exposure.

### 8.1. Negative exposure tests

Ví dụ env endpoint không nằm trong include list. Gửi request tới /actuator/env và xác minh không thể truy cập qua web. Nếu endpoint bị security chặn thay vì không expose, status code có thể khác; mục tiêu là chứng minh caller không lấy được dữ liệu.

### 8.2. JMX và HTTP

HTTP exposure không đồng nghĩa JMX exposure. Nếu hệ thống dùng JMX, test riêng JMX endpoint exposure và authentication/network policy. Không bỏ qua JMX chỉ vì HTTP endpoint được bảo vệ.

## 9. Kiểm thử metrics và Prometheus endpoint

Metrics endpoint có thể liệt kê meter names và đọc một meter cụ thể. Prometheus endpoint xuất scrape format.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Integration test có thể kiểm tra:
- /actuator/metrics trả danh sách meter;
- meter cần thiết có trong registry;
- /actuator/metrics/{name} trả measurement;
- /actuator/prometheus trả content type/format phù hợp;
- metric name và tags không chứa IDs động.

### 9.1. Test meter được đăng ký

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MetricsRegistryTest {
    @Autowired
    MeterRegistry registry;

    @Test
    void registersJvmMemoryMetric() {
        assertThat(registry.find("jvm.memory.used").meter()).isNotNull();
    }
}
~~~

Meter name phụ thuộc registry và binders. Dùng tên đã xác minh trong application thực tế; test không nên phụ thuộc meter không có trong dependency set.

### 9.2. Test Prometheus scrape

Dùng MockMvc hoặc HTTP client gọi /actuator/prometheus, kiểm tra response chứa một metric ổn định đã được đăng ký. Tránh assert toàn bộ output vì JVM/process metrics thay đổi giữa môi trường và version.

### 9.3. Cardinality regression test

Có thể thực hiện nhiều requests với user/order IDs khác nhau rồi xác minh số lượng meter time series không tăng theo các IDs đó. Metric tag names/values cần được allowlist và review.

## 10. Management port và real HTTP tests

MockMvc không kiểm tra network listener hoặc management server port riêng. Nếu cấu hình management.server.port khác application port, dùng RANDOM_PORT hoặc container smoke test để xác minh management endpoint thật sự listen trên port mong muốn.

Ví dụ test server:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "management.server.port=0"
)
class ManagementPortTest {
    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void healthIsServedOnManagementPort() {
        ResponseEntity<String> response = restTemplate.getForEntity(
                "http://localhost:" + managementPort + "/actuator/health",
                String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
    }
}
~~~

Các test annotations/management port support phụ thuộc Spring Boot version. Nếu không dùng separate management port, test có thể dùng local server port và đúng base path.

### 10.1. Test base path

Nếu management.endpoints.web.base-path đổi từ /actuator sang /manage, xác minh path cũ không còn được expose và path mới trả response. Điều này tránh manifest/probe trỏ tới endpoint cũ.

## 11. WebTestClient cho reactive application

Với WebFlux, WebTestClient có thể kiểm tra endpoint HTTP và reactive response. Khi test application context không mở server, bind WebTestClient theo cách Spring Boot test support cho version đang dùng. Với RANDOM_PORT, client gửi request qua embedded server để kiểm tra filters và networking.

Test reactive HealthIndicator cần xác minh publisher complete/error trong timeout. Không block event loop trong indicator hoặc test path.

## 12. Test health endpoint ổn định và không phụ thuộc môi trường

Một nguyên nhân phổ biến của flaky tests là auto-configured indicator gọi database/broker thật. Khi developer local có service chạy nhưng CI không có, test behavior khác nhau.

Chiến lược:
- dùng test database/container khi cần xác minh integration;
- fake dependency cho status aggregation tests;
- disable contributor không liên quan trong test profile khi hợp lý;
- không phụ thuộc external public endpoint;
- cố định clock/configuration khi test cache/TTL;
- đặt timeout và cleanup rõ;
- tránh assert exact latency milliseconds.

Nếu test cần chứng minh DataSource health, dùng Testcontainers hoặc database test service được quản lý. Nếu chỉ cần chứng minh endpoint aggregation, fake contributor là đủ.

## 13. Troubleshooting Actuator endpoint tests

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Endpoint trả 404 | Chưa expose hoặc sai base path | Kiểm tra exposure/path |
| Endpoint trả 401/403 | Security chain chặn | Kiểm tra matcher, role và test user |
| Health trả DOWN trong CI | Contributor phụ thuộc external service | Fake dependency hoặc test container |
| MockMvc không tìm thấy endpoint | Slice test thiếu Actuator auto-config | Dùng full context hoặc import đúng config |
| Health body UP nhưng HTTP 503 | Status mapping/customizer | Kiểm tra HTTP mapping và contributors |
| Readiness DOWN trong test | Warm-up chưa hoàn tất | Trigger/await readiness transition |
| Details lộ cho anonymous | show-details/security policy sai | Test body và authorization |
| Prometheus endpoint rỗng | Registry/exporter chưa có meter | Kiểm tra dependency/binder/registry |
| Meter name khác kỳ vọng | Registry/version khác | Inspect registry trong runtime |
| Management port test fail | Port/path/context setup sai | Dùng LocalManagementPort và RANDOM_PORT |
| Test timeout | Health indicator block hoặc retry | Dependency timeout và bounded test |
| Test chạy local nhưng fail CI | Phụ thuộc môi trường | Fake/container và deterministic fixtures |

### 13.1. Quy trình điều tra

1. Xác định test slice hay full application context.
2. Kiểm tra Actuator dependency, endpoint enablement và HTTP exposure.
3. Xác minh base path, management port và active profile.
4. Đọc response status/body để phân biệt health failure với security failure.
5. Kiểm tra health contributors và external dependencies.
6. Kiểm tra security chain order, matcher và test principal.
7. Xác minh MeterRegistry/exporter và meter names thực tế.
8. Chạy container/cluster smoke test nếu lỗi chỉ xảy ra sau deploy.

## 14. Production-like smoke tests và CI

Unit/integration tests không chứng minh deployment manifest, container port hoặc NetworkPolicy hoạt động. CI/CD nên có các tầng:

1. Unit tests cho custom indicators và health logic.
2. Application integration tests cho Actuator configuration.
3. Security tests cho anonymous/authorized callers.
4. Container smoke tests cho image và management port.
5. Manifest validation cho probe paths/ports.
6. Staging smoke tests từ góc nhìn network tương tự kubelet/monitoring.
7. Post-deploy verification cho health, metrics scrape và alert pipeline.

Không chạy smoke test destructive trên production. Dùng endpoint read-only và synthetic fixtures có cleanup.

### 14.1. Kiểm tra readiness sau deploy

Sau rollout, xác minh:
- replicas mong đợi đều Ready;
- readiness path trả status phù hợp;
- liveness path không phụ thuộc database outage;
- Prometheus target được scrape;
- management endpoints không bị public ngoài ý muốn;
- logs/alerts không báo endpoint failures bất thường.

### 14.2. Contract tests

Nếu monitoring platform phụ thuộc metric names hoặc health response fields, giữ contract tests cho những phần ổn định. Khi nâng Spring Boot/Micrometer, chạy contract tests để phát hiện thay đổi naming, content type hoặc endpoint behavior.

## 15. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| Endpoint enable/exposure rõ | Test positive và negative exposure |
| Health status contract | UP/DOWN và HTTP mapping |
| Health groups | Liveness/readiness membership |
| Custom indicators | Success/failure/timeout/exception |
| Security | Anonymous, authorized và unauthorized tests |
| Details privacy | Không leak internal data |
| Metrics registry | Meter names/tags đã xác minh |
| Prometheus scrape | Format/content type và metric presence |
| Cardinality | IDs không tạo time series mới |
| Management port/base path | Real HTTP test |
| Runtime image | Container smoke test |
| Kubernetes manifest | Probe path/port validation |
| CI determinism | Không phụ thuộc external services ngoài test |
| Upgrade safety | Contract tests qua version change |

## 16. Bài thực hành: xây bộ test Actuator cho order-service

**Bối cảnh:** order-service expose health, readiness/liveness, metrics và Prometheus. CI thỉnh thoảng fail vì database test không sẵn sàng; endpoint health details từng vô tình lộ hostname trong môi trường staging.

**Nhiệm vụ:**

1. Tạo full-context integration test cho /actuator/health.
2. Dùng fake database/search indicators để test UP/DOWN aggregation.
3. Test readiness và liveness groups độc lập.
4. Test status-to-HTTP mapping cho DOWN và OUT_OF_SERVICE.
5. Test anonymous caller chỉ xem status tối thiểu.
6. Test OPS role xem details đã được duyệt.
7. Test endpoint không expose như env/configprops không truy cập được.
8. Test MeterRegistry có meter cần thiết và tags không chứa order/customer IDs.
9. Test Prometheus scrape output bằng metric ổn định.
10. Test management port riêng và base path.
11. Build container và chạy smoke test từ network context tương tự deployment.
12. Viết CI stages và runbook cho 404, 503, 401/403, missing metrics và probe failures.

**Kết quả mong đợi:** test suite bao phủ endpoint, security, health groups, metrics, management port, container smoke tests và contract verification.

## 17. Ghi nhớ

Test Actuator endpoint phải xác minh enablement, HTTP exposure, authorization, response contract và runtime connectivity. Unit test custom HealthIndicator chưa chứng minh endpoint được expose; MockMvc chưa chứng minh management port hoặc NetworkPolicy hoạt động; container smoke test bổ sung bằng chứng từ runtime gần production.

Dùng fake contributors cho aggregation tests và test containers khi cần xác minh dependency thật. Kiểm thử riêng liveness/readiness, status mapping, security/details, metrics registry và Prometheus output. Giữ tests deterministic, tránh phụ thuộc external services và không assert toàn bộ response có fields thay đổi theo classpath. Khi deploy, xác minh probe paths/ports và monitoring scrape. Metrics, logs và traces hỗ trợ chẩn đoán; endpoint tests bảo đảm các giao diện vận hành đó hoạt động đúng và không lộ dữ liệu.

**Tài liệu tham khảo:**
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Health Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/)
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Testcontainers — Spring Boot](https://java.testcontainers.org/modules/databases/)

