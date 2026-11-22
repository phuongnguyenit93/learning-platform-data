# Giới hạn truy cập health và Prometheus theo nhu cầu hạ tầng

## 1. Bắt đầu từ người sử dụng tín hiệu vận hành

Actuator cung cấp các tín hiệu giúp hạ tầng ra quyết định. Nhưng các bên sử dụng không cần cùng một tập thông tin:

- Bộ kiểm tra của Kubernetes cần biết tiến trình còn sống và đã sẵn sàng nhận yêu cầu hay chưa.
- Bộ cân bằng tải cần một tín hiệu nhỏ để quyết định có chuyển yêu cầu đến phiên bản ứng dụng này không.
- Prometheus cần đọc số liệu định kỳ để lưu chuỗi thời gian và phục vụ cảnh báo.
- Người vận hành có thể cần đọc tình trạng tổng hợp khi điều tra sự cố.

**Giới hạn truy cập** là xác định rõ ai được kết nối, được gọi endpoint nào, bằng phương thức nào và nhận bao nhiêu thông tin. Mục tiêu là cung cấp đủ tín hiệu cho vận hành trong khi tránh mở rộng quyền vượt nhu cầu.

Ví dụ xuyên suốt bài dùng Java 21 và Spring Boot 3.3.13. Phần mã chạy được chọn Spring MVC/Servlet để minh họa một chính sách cụ thể. Với WebFlux, giữ nguyên ma trận quyền nhưng dùng hệ API Reactive tương ứng; không trộn hai loại chuỗi bảo mật.

## 2. Health và Prometheus trả lời các câu hỏi khác nhau

### 2.1. Health: một quyết định tại thời điểm kiểm tra

`/actuator/health` biểu diễn tình trạng tổng hợp. Các nhóm `liveness` và `readiness` tập trung vào hai quyết định riêng:

| Tín hiệu | Câu hỏi | Hành động điển hình của hạ tầng |
| --- | --- | --- |
| Liveness | Tiến trình có rơi vào trạng thái cần khởi động lại không? | Khởi động lại container khi kiểm tra thất bại theo ngưỡng |
| Readiness | Phiên bản ứng dụng này có sẵn sàng nhận yêu cầu không? | Ngừng chuyển lưu lượng đến phiên bản chưa sẵn sàng |
| Startup | Ứng dụng đã vượt qua giai đoạn khởi động chưa? | Trì hoãn các kiểm tra liveness/readiness cho đến khi startup thành công |

Không nên dùng một kiểm tra tổng hợp duy nhất cho mọi quyết định. Chẳng hạn, cơ sở dữ liệu chung ngừng hoạt động không nhất thiết có nghĩa là khởi động lại toàn bộ ứng dụng sẽ sửa được lỗi. Ngược lại, một phiên bản đang ngừng nhận lưu lượng để bảo trì có thể vẫn sống bình thường.

Những hành vi của probe được mô tả trong [Kubernetes: Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/). Nhóm kiểm tra mặc định và việc lựa chọn hệ thống phụ thuộc cần được thiết kế theo ứng dụng, không suy ra chỉ từ tên endpoint.

### 2.2. Prometheus: dữ liệu để quan sát theo thời gian

`/actuator/prometheus` trả số liệu theo định dạng mà Prometheus có thể thu thập. Đây thường là quá trình **kéo dữ liệu (scrape)**: Prometheus gửi GET đến ứng dụng theo chu kỳ.

Endpoint này khác `/actuator/metrics`. Endpoint metrics phục vụ việc xem các số đo qua API của Actuator; Prometheus dùng endpoint xuất dữ liệu riêng. Muốn có endpoint Prometheus cần cả thư viện registry tương ứng và cấu hình công bố qua HTTP.

Số liệu có thể chứa tên dịch vụ, cấu trúc đường dẫn, nhãn nghiệp vụ hoặc thông tin về tải và tài nguyên. Không đưa token, địa chỉ email, nội dung yêu cầu hay dữ liệu cá nhân vào nhãn số liệu rồi trông chờ cấu hình bảo mật che được tất cả.

Một lần scrape thành công cũng không chứng minh ứng dụng đã sẵn sàng nhận nghiệp vụ. Chỉ số `up` do Prometheus tạo phản ánh kết quả thu thập ở phía Prometheus; không đồng nhất nó với trạng thái readiness của Spring Boot.

Xem [Spring Boot 3.3: Metrics — Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.export.prometheus).

## 3. Thiết kế quyền theo ba lớp

Một yêu cầu chỉ nên thành công khi đáp ứng cả ba lớp:

```text
Đường mạng đến được máy chủ
            |
Endpoint đã được bật và công bố qua HTTP
            |
Chính sách ứng dụng cho phép người gửi thực hiện yêu cầu
            |
Nhận phản hồi có lượng thông tin phù hợp
```

### 3.1. Khả năng kết nối mạng

Firewall, chính sách mạng, Service, reverse proxy và Ingress quyết định nguồn nào có thể tiếp cận cổng quản trị.

Một đường dẫn được `permitAll()` không thể tự phân biệt kubelet với người dùng Internet. Nếu cả hai đều đến được cùng đường dẫn thì cả hai đều có thể gọi nó. Khi probe không cần mật khẩu, chính hạ tầng phải bảo đảm đường đi đó chỉ xuất hiện ở nơi đã chủ ý cho phép.

Không dùng `User-Agent: kube-probe` làm danh tính đáng tin: người khác có thể tự đặt header này. Không tin trực tiếp `X-Forwarded-For` do bên ngoài gửi để cấp quyền. Nếu dựa vào địa chỉ nguồn, cần xác minh chuỗi proxy tin cậy, việc viết lại header và địa chỉ thực tế mà ứng dụng nhìn thấy.

### 3.2. Bật và công bố endpoint

Trong Boot 3.3, `management.endpoints.web.exposure.include` là danh sách endpoint được công bố qua HTTP. Nó không phải danh sách người được phép truy cập.

Cấu hình `include: health,prometheus` không có nghĩa hai endpoint đều công khai. Ngược lại, khai báo một quy tắc `permitAll()` cũng không tự tạo endpoint chưa được công bố hoặc thiếu dependency.

### 3.3. Xác thực, phân quyền và lượng dữ liệu

Xác thực trả lời người gửi là ai; phân quyền quyết định người đó được đọc tài nguyên nào. Một tài khoản chuyên thu thập số liệu không cần quyền quản trị chung.

Ẩn chi tiết health là một quyết định độc lập với việc cho phép gọi endpoint. Phản hồi tối giản có thể chỉ có:

```json
{"status":"UP"}
```

Ngay cả phản hồi tối giản vẫn tiết lộ tình trạng dịch vụ. Hãy chỉ mở nó cho đúng đường kiểm tra được chọn.

## 4. Lập ma trận truy cập trước khi viết cấu hình

Ví dụ sử dụng ba nhóm người gọi:

- **Probe nội bộ:** không mang thông tin đăng nhập; chỉ đọc hai đường kiểm tra tối giản.
- **scraper:** tài khoản máy có authority `METRICS_SCRAPE`; chỉ đọc dữ liệu Prometheus.
- **operator:** tài khoản người vận hành có vai trò `OPS`; đọc health tổng hợp, không mặc nhiên có quyền scrape.

Ma trận ở tầng ứng dụng:
    
| GET đến tài nguyên | Không đăng nhập | scraper | operator |
| --- | --- | --- | --- |
| `/actuator/health/liveness` | Cho phép | Cho phép | Cho phép |
| `/actuator/health/readiness` | Cho phép | Cho phép | Cho phép |
| `/actuator/health` | 401 | 403 | Cho phép |
| `/actuator/prometheus` | 401 | Cho phép | 403 |
| `/actuator` — liên kết khám phá | 401 | 403 | 403 |
| Endpoint khác được công bố về sau | Không cấp quyền | Không cấp quyền | Không cấp quyền |

Mật khẩu ở hai cột có tài khoản được giả định là đúng. Khi chủ ý cần operator cũng đọc số liệu, hãy cấp thêm authority đó và cập nhật kiểm thử; không giả định `OPS` tự bao hàm mọi quyền.

Ma trận mạng bổ sung một điều kiện quan trọng: **người dùng Internet không được truy cập các đường Actuator qua cửa vào công khai**, kể cả hai đường probe được cho phép ở tầng ứng dụng. Việc này cần cấu hình hạ tầng riêng; mã Java bên dưới không tự tạo chính sách mạng hay cấu hình Ingress.

## 5. Dự án độc lập để kiểm chứng chính sách

Ví dụ chỉ tập trung vào endpoint vận hành, không tạo API nghiệp vụ giả. Các yêu cầu còn lại bị từ chối. Khi tích hợp vào ứng dụng có API thật, thay chính sách cuối bằng chính sách nghiệp vụ đã được thiết kế và kiểm thử.

### 5.1. Cấu trúc

```text
actuator-infrastructure-access/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── InfrastructureApplication.java
    │   │   └── AccessPolicy.java
    │   └── resources/application.yml
    └── test/java/example/
        ├── AccessPolicyTest.java
        └── ExtraEndpointTest.java
```

### 5.2. pom.xml

Dùng JDK 21 và Maven 3.6.3+. Thư viện `micrometer-registry-prometheus` bổ sung khả năng xuất số liệu Prometheus. Boot quản lý phiên bản các dependency, bao gồm Spring Security và Micrometer.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>actuator-infrastructure-access</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/resources/application.yml

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      show-components: never

demo:
  scrape-password: ${SCRAPE_PASSWORD}
  ops-password: ${OPS_PASSWORD}
```

`probes.enabled: true` bật hai nhóm kiểm tra cả khi chạy tại máy cá nhân. Trong Kubernetes, Boot có khả năng nhận diện môi trường và cấu hình probe; việc bật tường minh giúp bài thực hành không phụ thuộc quá trình nhận diện đó.

`show-details: never` và `show-components: never` giữ phản hồi health tối giản cho mọi người gọi trong mẫu. Nếu cần thông tin chi tiết cho operator, có thể thiết kế chính sách `when-authorized` và vai trò được xem chi tiết; phải kiểm thử riêng phản hồi ẩn danh và từng nhóm sức khỏe. Cho phép truy cập endpoint không tự giải quyết quyền xem chi tiết.

Hai thuộc tính `demo.*` nhận mật khẩu từ biến môi trường. Mẫu không cung cấp mật khẩu mặc định trong cấu hình ứng dụng. Các giá trị dành cho kiểm thử sẽ được truyền riêng trong lớp test.

### 5.4. src/main/java/example/InfrastructureApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfrastructureApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfrastructureApplication.class, args);
    }
}
```

Không cần tự viết controller cho health hoặc Prometheus: Actuator cung cấp các endpoint đó.

### 5.5. src/main/java/example/AccessPolicy.java

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.metrics.export.prometheus.PrometheusScrapeEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class AccessPolicy {
    @Bean
    @Order(1)
    SecurityFilterChain actuator(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(rules -> rules
                .requestMatchers(HttpMethod.GET,
                        "/actuator/health/liveness",
                        "/actuator/health/readiness").permitAll()
                .requestMatchers(EndpointRequest.to(PrometheusScrapeEndpoint.class))
                        .hasAuthority("METRICS_SCRAPE")
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                        .hasRole("OPS")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(rules -> rules.anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.scrape-password}") String scrapePassword,
            @Value("${demo.ops-password}") String opsPassword) {
        var scraper = User.withUsername("scraper")
                .password(encoder.encode(scrapePassword))
                .authorities("METRICS_SCRAPE")
                .build();
        var operator = User.withUsername("operator")
                .password(encoder.encode(opsPassword))
                .roles("OPS")
                .build();
        return new InMemoryUserDetailsManager(scraper, operator);
    }
}
```

Những điểm quyết định của cấu hình:

1. Chuỗi `@Order(1)` chỉ nhận các endpoint Actuator. Hai quy tắc GET cụ thể đứng trước quy tắc bao quát cho HealthEndpoint.
2. Chỉ hai URL probe chính xác được phép ẩn danh. Không dùng `"/actuator/health/**"` cho phép tất cả, vì sau này có thể thêm nhóm hoặc đường dẫn health khác.
3. Endpoint Prometheus yêu cầu authority riêng. `hasAuthority("METRICS_SCRAPE")` kiểm tra đúng chuỗi này, không thêm tiền tố vai trò.
4. Health tổng hợp và các đường con chưa được công khai cần vai trò OPS. `roles("OPS")` tạo authority `ROLE_OPS`, phù hợp với `hasRole("OPS")`.
5. Quy tắc cuối `denyAll()` tránh tự cấp quyền khi ai đó mở thêm endpoint vào danh sách exposure.
6. Chuỗi `@Order(2)` bao phủ phần còn lại. Không để các đường ngoài matcher Actuator rơi vào vùng không có chính sách bảo mật.

`EndpointRequest.toAnyEndpoint()` bao gồm cả endpoint liên kết tại đường dẫn gốc Actuator. Nó không có nghĩa mọi URL bắt đầu bằng `/actuator` đều chắc chắn là một endpoint hiện hữu. Xem [EndpointRequest của Servlet trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

Các mật khẩu được băm bằng PasswordEncoder khi tạo người dùng mẫu. Kho người dùng trong bộ nhớ phục vụ việc minh họa chính sách, không đại diện cho hệ thống quản lý danh tính của mọi tổ chức. Basic chỉ mã hóa Base64 thông tin đăng nhập; cần HTTPS hoặc một kênh truyền bảo mật phù hợp khi đi ra ngoài bài thực hành tại máy cá nhân.

CSRF được giữ nguyên. Các tác vụ probe và scrape chỉ dùng GET nên không cần tắt CSRF. Mở các thao tác thay đổi trạng thái khác là một quyết định riêng.

**Giới hạn về đường dẫn:** hai matcher probe viết cố định URL mặc định. Nếu đổi base-path, path-mapping hoặc thêm đường probe ở cổng chính, phải sửa đúng matcher và chạy lại kiểm thử. Các matcher theo endpoint cho health/Prometheus không làm hai chuỗi URL cụ thể này tự thay đổi.

## 6. Chạy và quan sát tại máy cá nhân

Tại thư mục chứa `pom.xml`, thiết lập hai mật khẩu thử nghiệm trong terminal chạy ứng dụng.

Bash:

```bash
export SCRAPE_PASSWORD='lab-scrape-pass'
export OPS_PASSWORD='lab-ops-pass'
mvn spring-boot:run
```

PowerShell:

```powershell
$env:SCRAPE_PASSWORD = 'lab-scrape-pass'
$env:OPS_PASSWORD = 'lab-ops-pass'
mvn spring-boot:run
```

Đây là giá trị công khai dành riêng cho thực hành tại máy cá nhân. Trong triển khai thật, cấp bí mật qua cơ chế quản lý bí mật và quy trình thay đổi mật khẩu của hệ thống; không đưa mật khẩu thật vào repository hoặc lệnh được lưu trong lịch sử shell.

Có thể đóng gói và chạy bằng Java thay cho `spring-boot:run`:

```bash
mvn package
java -jar target/actuator-infrastructure-access-1.0.0.jar
```

Giữ hai biến môi trường trong terminal chạy JAR. Vì có dependency Spring, dùng Maven để biên dịch và xây dựng classpath; không chỉ gọi `javac` trên một tệp rồi kỳ vọng dependency được tự tải.

### 6.1. Đọc probe

Khi ứng dụng đã khởi động và sẵn sàng:

```bash
curl -s http://localhost:8080/actuator/health/liveness
curl -s http://localhost:8080/actuator/health/readiness
```

Nội dung mỗi phản hồi trong trạng thái bình thường:

```json
{"status":"UP"}
```

Đây là nội dung HTTP, không phải log của phương thức main. Curl không tự thêm dòng trống giữa các phản hồi. Khi readiness bị chuyển sang từ chối lưu lượng, phản hồi mặc định của nhóm đó là 503 với trạng thái `OUT_OF_SERVICE`; kiểm thử ở mục 7 minh họa việc này.

### 6.2. Xác minh quyền

Các lệnh dưới dùng Bash; trong PowerShell dùng `curl.exe` và thay `/dev/null` bằng `NUL`. Chúng dùng đúng mật khẩu thử nghiệm ở trên:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/prometheus
curl -s -o /dev/null -w "%{http_code}\n" -u operator:lab-ops-pass http://localhost:8080/actuator/prometheus
curl -s -o /dev/null -w "%{http_code}\n" -u scraper:lab-scrape-pass http://localhost:8080/actuator/prometheus
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/health
curl -s -o /dev/null -w "%{http_code}\n" -u scraper:lab-scrape-pass http://localhost:8080/actuator/health
curl -s -o /dev/null -w "%{http_code}\n" -u operator:lab-ops-pass http://localhost:8080/actuator/health
```

Kết quả lần lượt:

```text
401
403
200
401
403
200
```

401 trong các lệnh này chỉ ra thiếu xác thực hợp lệ; 403 với tài khoản đúng cho biết thiếu quyền tương ứng. Không tổng quát hóa mọi 403 thành thiếu vai trò: CSRF và các lớp phía trước cũng có thể từ chối một yêu cầu.

Đọc dữ liệu scrape:

```bash
curl -s -u scraper:lab-scrape-pass -H "Accept: text/plain;version=0.0.4" http://localhost:8080/actuator/prometheus
```

Phản hồi chứa dữ liệu xuất Prometheus, gồm các dòng mô tả như `# HELP`, các dòng `# TYPE` và giá trị số đo. Không cố định toàn bộ stdout vì tên, giá trị, thứ tự và tập số đo phụ thuộc môi trường và thời điểm.

## 7. Kiểm thử chính sách và hành vi readiness

Bộ kiểm thử sau dùng đầy đủ ngữ cảnh Spring Boot với MockMvc. Thông tin Basic đi qua bộ lọc bảo mật thật, không thay người gọi bằng một danh tính đã được xác thực sẵn. Không mở cổng HTTP.

`@AutoConfigureObservability` cho phép cấu hình quan sát cần thiết trong kiểm thử này, để registry và endpoint Prometheus có mặt; nếu vô tình tắt registry trong môi trường test, kết quả không còn kiểm tra đúng đường scrape dự kiến.

### 7.1. src/test/java/example/AccessPolicyTest.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "demo.scrape-password=test-scrape-pass",
        "demo.ops-password=test-ops-pass"
})
@AutoConfigureMockMvc
@AutoConfigureObservability
class AccessPolicyTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Test
    void probesAreAnonymousAndMinimal() throws Exception {
        for (String group : new String[]{"liveness", "readiness"}) {
            mvc.perform(get("/actuator/health/" + group))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.status").value("UP"))
                    .andExpect(jsonPath("$.components").doesNotExist());
        }
    }

    @Test
    void aggregateHealthIsOnlyForOperator() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("scraper", "test-scrape-pass")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("operator", "test-ops-pass")))
                .andExpect(status().isOk());
    }

    @Test
    void prometheusRequiresItsOwnAuthority() throws Exception {
        mvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("operator", "test-ops-pass")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("scraper", "test-scrape-pass"))
                        .accept("text/plain;version=0.0.4"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("# HELP")));
    }

    @Test
    void wrongScrapePasswordIsRejected() throws Exception {
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("scraper", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void discoveryLinksAreNotGrantedToOperator() throws Exception {
        mvc.perform(get("/actuator")
                        .with(httpBasic("operator", "test-ops-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void healthSubtreeIsNotAllPublic() throws Exception {
        mvc.perform(get("/actuator/health/unpublished"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void otherPathsAreDenied() throws Exception {
        mvc.perform(get("/actuator/env")
                        .with(httpBasic("operator", "test-ops-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void postToProbeIsNotMadePublic() throws Exception {
        mvc.perform(post("/actuator/health/liveness")
                        .with(httpBasic("operator", "test-ops-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void refusingTrafficDoesNotMeanLivenessFailure() throws Exception {
        AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
        try {
            mvc.perform(get("/actuator/health/readiness"))
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(jsonPath("$.status").value("OUT_OF_SERVICE"));
            mvc.perform(get("/actuator/health/liveness"))
                    .andExpect(status().isOk());
        }
        finally {
            AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
```

Kiểm thử readiness phát sự kiện `REFUSING_TRAFFIC` rồi luôn khôi phục trạng thái trong `finally`. Nó chứng minh rằng ngừng nhận lưu lượng không tự làm kiểm tra liveness thất bại. Đây là thao tác mô phỏng trạng thái trong test, không phải một API công khai để thay đổi trạng thái ứng dụng.

Phép thử POST trả 403 trong cấu hình giữ CSRF. Nó không chứng minh một quyền GET tự có tác dụng đối với POST; phương thức HTTP, CSRF và handler của endpoint là các điều kiện riêng.

### 7.2. src/test/java/example/ExtraEndpointTest.java

Lớp thứ hai cố ý công bố thêm `info` nhưng không sửa chính sách quyền:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.scrape-password=test-scrape-pass",
        "demo.ops-password=test-ops-pass",
        "management.endpoints.web.exposure.include=health,prometheus,info"
})
@AutoConfigureMockMvc
@AutoConfigureObservability
class ExtraEndpointTest {
    @Autowired
    MockMvc mvc;

    @Test
    void exposingInfoDoesNotGrantAccess() throws Exception {
        mvc.perform(get("/actuator/info")
                        .with(httpBasic("operator", "test-ops-pass")))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
mvn clean test
```

Có 10 phương thức kiểm thử: 9 trong AccessPolicyTest và 1 trong ExtraEndpointTest. Điều kiện thành công là không có failure/error.

Phép thử thêm endpoint đặc biệt hữu ích: cấu hình exposure được mở rộng không đồng nghĩa tài khoản operator tự được đọc endpoint mới. Việc cấp quyền phải là một thay đổi rõ ràng.

MockMvc kiểm tra chính sách trong ứng dụng. Nó không xác nhận firewall, TLS, Ingress, nguồn truy cập từ node hay kết nối Prometheus thật. Những ranh giới đó cần kiểm tra từ đúng vị trí triển khai.

## 8. Gắn probe với Kubernetes

Đoạn YAML dưới là **phần cấu hình của một container**, không phải một Deployment hoàn chỉnh. Nó khớp cổng 8080 và đường dẫn mặc định của dự án:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

Các ngưỡng chỉ minh họa cách cấu hình; lựa chọn thật phải dựa vào thời gian khởi động và khả năng phản hồi đã đo được. Startup probe dành thời gian cho giai đoạn khởi động trước khi liveness/readiness bắt đầu hoạt động.

HTTP probe đi đến địa chỉ và cổng của Pod theo cấu hình, không cần đi vòng qua trang đăng nhập công khai. Kubernetes coi mã 200–399 là thành công cho HTTP probe; vì vậy một chuyển hướng đến trang đăng nhập có thể tạo tín hiệu sai. Mẫu dùng HTTP Basic cho tài nguyên cần xác thực và không bật form login cho probe.

Không chèn một tài khoản quản trị vào header probe chỉ để chữa lỗi 401. Trước hết kiểm tra URL, phương thức, cổng, thứ tự quy tắc và phạm vi mạng. Nếu tổ chức bắt buộc probe phải xác thực, chọn cơ chế mà hạ tầng thật sự hỗ trợ và quản lý được bí mật, thay vì ghi cứng Authorization trong manifest.

Không đưa mọi hệ thống bên ngoài vào liveness. Với readiness, chỉ thêm thành phần mà việc không sẵn sàng của nó thật sự làm phiên bản này không nên nhận lưu lượng. Tránh tạo một cơ chế khiến sự cố của một hệ thống dùng chung loại toàn bộ các phiên bản ra khỏi phục vụ mà không có phương án xử lý.

Xem [Kubernetes: cấu hình probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

## 9. Gắn Prometheus với danh tính máy riêng

Ví dụ `prometheus.yml` dưới giả định Prometheus và ứng dụng cùng chạy trực tiếp trên một máy thực hành. Tệp `secrets/scrape-password` chứa đúng mật khẩu thử nghiệm đã cấp cho ứng dụng; đường dẫn được đọc từ tiến trình Prometheus.

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 5s

scrape_configs:
  - job_name: actuator-local
    metrics_path: /actuator/prometheus
    scheme: http
    basic_auth:
      username: scraper
      password_file: secrets/scrape-password
    static_configs:
      - targets:
          - localhost:8080
```

Nếu chạy Prometheus trong container, `localhost` là chính container đó; phải đổi target sang địa chỉ ứng dụng có thể truy cập từ mạng của Prometheus. Không khắc phục sai target bằng cách mở công khai toàn bộ cổng quản trị.

Có thể kiểm tra cú pháp bằng công cụ đi kèm Prometheus:

```bash
promtool check config prometheus.yml
```

Kiểm tra cú pháp không chứng minh target kết nối được, mật khẩu đúng hay CA hợp lệ. Sau khi cấu hình được nạp, kiểm tra trạng thái target, lỗi scrape và chỉ số `up`.

### 9.1. Khi triển khai có HTTPS

Giả sử hệ thống đã có Service nội bộ `orders-management.observability.svc.cluster.local:8443` phục vụ HTTPS và chứng thư hợp lệ cho tên đó. Phần job có thể có dạng sau; đây là cấu hình cho hạ tầng đã nêu, không phải cấu hình TLS được tự tạo bởi dự án Java:

```yaml
scrape_configs:
  - job_name: orders-internal
    scheme: https
    metrics_path: /actuator/prometheus
    basic_auth:
      username: scraper
      password_file: /etc/prometheus/secrets/orders-scrape-password
    tls_config:
      ca_file: /etc/prometheus/certs/internal-ca.crt
    static_configs:
      - targets:
          - orders-management.observability.svc.cluster.local:8443
```

Các tệp bí mật và CA phải được cấp cho đúng tiến trình/container Prometheus. Không bật bỏ qua kiểm tra chứng thư để che lỗi tên máy hoặc chuỗi CA. Nếu TLS kết thúc tại proxy, xem xét cả đoạn truyền từ proxy đến ứng dụng theo ranh giới tin cậy của hệ thống.

Tài khoản scraper không cần dùng chung mật khẩu với operator. Khi thay mật khẩu, phối hợp việc cập nhật nguồn danh tính và bí mật phía Prometheus; theo dõi lỗi 401 sau thay đổi. Kiểm tra cơ chế nạp lại của các thành phần đang dùng, không giả định mọi tệp bí mật đều được đọc lại giống nhau.

Nếu dùng Prometheus Operator, cấu hình xác thực và tham chiếu Secret qua tài nguyên giám sát mà phiên bản Operator hỗ trợ; không chép nguyên cấu trúc `scrape_configs` vào mọi ServiceMonitor.

Các trường `metrics_path`, `basic_auth`, `password_file` và `tls_config` được mô tả trong [tài liệu cấu hình Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

## 10. Khi nào nên tách cổng quản trị?

Cùng cổng thuận tiện khi hạ tầng chỉ cho một cổng và có thể giới hạn chính xác đường dẫn. Tách cổng hữu ích khi muốn đặt một cổng quản trị vào mạng riêng và quản lý Service, firewall hoặc TLS độc lập.

Một thay đổi cấu hình minh họa, cần hợp nhất vào YAML hiện có:

```yaml
server:
  port: 8080

management:
  server:
    port: 9090
```

**Số cổng khác không phải một cơ chế xác thực.** Nếu cổng 9090 vẫn được mở ra Internet thì dữ liệu quản trị vẫn có thể bị tiếp cận. Ngược lại, đặt `management.server.address: 127.0.0.1` chỉ phù hợp khi bên thu thập thực sự có đường đến loopback đó; Prometheus ở Pod khác không thể truy cập loopback của ứng dụng.

Theo [Boot 3.3: Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html), cổng và TLS quản trị có thể được cấu hình riêng. Khi đổi cổng cần cập nhật target scrape và probe tương ứng.

### 10.1. Probe ở cổng chính khi quản trị dùng cổng riêng

Một cổng quản trị vẫn phản hồi không chứng minh cổng nghiệp vụ đang nhận kết nối. Boot 3.3 hỗ trợ:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

Tính năng này bổ sung `/livez` và `/readyz` ở cổng chính. Khi áp dụng, phải làm đồng thời:

1. Sửa đường probe của hạ tầng sang hai URL đó trên cổng ứng dụng.
2. Thêm quyền GET chính xác cho `/livez` và `/readyz` vào chuỗi xử lý các đường này trên cổng chính. Trong cấu hình mẫu, chuỗi bao phủ phần còn lại đang denyAll nên không thể chỉ thêm thuộc tính rồi kỳ vọng truy cập thành công.
3. Giữ chính sách riêng cho endpoint Prometheus trên cổng quản trị.
4. Kiểm thử cả hai cổng, các đường bổ sung và đường Actuator gốc.

Đây là một biến thể triển khai, không được bộ kiểm thử một cổng ở mục 7 xác nhận sẵn. Không tự mở `/actuator/**` ở cổng chính để chữa lỗi probe.

## 11. Kiểm soát mạng và cửa vào công khai

Các lớp cần được phối hợp theo đường đi thực tế:

- Cửa vào công khai chỉ chuyển tiếp các đường nghiệp vụ đã chủ ý công bố; không vô tình chuyển tiếp mọi đường Actuator qua quy tắc bắt tất cả.
- Service quản trị, nếu có, chỉ phục vụ mạng và nhóm người gọi cần thiết; không tự chọn kiểu công bố ra ngoài chỉ để tiện scrape.
- Chính sách mạng giới hạn kết nối theo nguồn và cổng phù hợp; quyền ứng dụng tiếp tục kiểm tra danh tính scraper.
- Đường probe của kubelet phải được kiểm tra trong mô hình mạng node–Pod thực tế, đặc biệt khi có chính sách mặc định từ chối.

Kubernetes NetworkPolicy tiêu chuẩn kiểm soát kết nối ở tầng mạng/vận chuyển, không lọc được riêng đường HTTP `/actuator/prometheus` trên cùng một cổng với API. Muốn phân biệt đường dẫn ở tầng mạng cần một thành phần tầng ứng dụng phù hợp hoặc tách cổng. Các chính sách mạng chỉ có hiệu lực khi giải pháp mạng của cụm hỗ trợ chúng; nhiều chính sách cho phép còn có thể cộng dồn quyền truy cập.

Địa chỉ nguồn nhìn thấy và xử lý lưu lượng từ node có thể phụ thuộc hạ tầng mạng. Không suy ra “chỉ một namespace được gọi” chỉ từ một đoạn YAML mà chưa kiểm tra từ nguồn thực tế. Xem [Kubernetes: Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Một ma trận kiểm tra triển khai nên gồm:

| Vị trí gửi yêu cầu | Điều phải xác minh |
| --- | --- |
| Máy người dùng bên ngoài | Không nhận được dữ liệu Actuator qua cửa vào công khai |
| Kubelet/node kiểm tra Pod | Hai probe đến đúng cổng và đường dẫn, nhận đúng trạng thái |
| Tiến trình Prometheus | Scrape được với danh tính máy; sai hoặc thiếu mật khẩu bị từ chối |
| Một workload không được phép | Không đến được cổng quản trị theo chính sách mạng dự kiến |
| Operator qua đường quản trị được cấp | Chỉ đọc được tài nguyên đã cấp quyền |

## 12. Chẩn đoán mà không mở rộng quyền tùy tiện

| Hiện tượng | Kiểm tra theo thứ tự |
| --- | --- |
| Probe trả 401 | Đúng cổng/URL/phương thức chưa; matcher có khớp trước quy tắc health tổng hợp không |
| Probe nhận 302 | Có proxy hoặc cơ chế đăng nhập đang chuyển hướng thay vì trả kết quả sức khỏe không |
| Prometheus nhận 401 | Username, mật khẩu, nguồn tệp bí mật và việc nạp cấu hình |
| Prometheus nhận 403 với mật khẩu đúng | Authority thực tế có đúng METRICS_SCRAPE không; có lớp proxy từ chối không |
| Scrape nhận HTML hoặc JSON health | Sai đường, sai route proxy hoặc sai target |
| Không có endpoint Prometheus | Có registry, endpoint khả dụng và exposure tương ứng chưa |
| Không kết nối được | DNS, địa chỉ bind, cổng, Service, firewall và chính sách mạng |
| Lỗi TLS | Tên máy, CA, hạn chứng thư và điểm kết thúc TLS |
| Health có chi tiết không mong đợi | show-details, show-components và cấu hình riêng của từng nhóm |
| Scrape thành công nhưng Pod chưa sẵn sàng | Đây là hai tín hiệu khác nhau; đọc readiness và trạng thái ứng dụng |

Trong mẫu, GET đến một đường không được công bố như `/actuator/env` có thể bị chuỗi cuối trả 403 cho tài khoản đã đăng nhập. Điều đó không chứng minh endpoint env đang tồn tại. Chuỗi bảo mật có thể từ chối trước khi ứng dụng tìm handler.

Đừng xử lý lỗi bằng `include: "*"`, cấp quyền quản trị cho scraper hay `permitAll()` toàn bộ Actuator. Truy vết đúng một yêu cầu qua đường mạng, khả năng tồn tại của endpoint, xác thực và quyền cần thiết rồi sửa lớp có lỗi.

## 13. Thực hành và tiêu chí hoàn thành

1. Chạy 10 kiểm thử và giải thích vì sao scraper không đọc được health tổng hợp, còn operator không đọc được Prometheus.
2. Đọc kết quả của phép thử readiness: tại sao 503 ở readiness vẫn đi cùng 200 ở liveness?
3. Thêm một nhóm sức khỏe mới trong dự án thực hành. Chứng minh nhóm đó không tự công khai chỉ vì liveness/readiness đang công khai.
4. Đổi đường dẫn gốc hoặc tách cổng quản trị, rồi cập nhật matcher, probe và target scrape. Kiểm thử lại từ đúng phía của từng kết nối.
5. Lập ma trận nguồn truy cập cho một môi trường thật: người ngoài, kubelet, Prometheus và operator. Chỉ ra lớp nào thực thi mỗi điều kiện.

Chính sách đạt yêu cầu khi bên kiểm tra nhận được tín hiệu tối giản, bộ thu thập có quyền riêng vừa đủ, người vận hành có quyền rõ ràng và đường vào công khai không vô tình trở thành cửa đọc dữ liệu quản trị.
