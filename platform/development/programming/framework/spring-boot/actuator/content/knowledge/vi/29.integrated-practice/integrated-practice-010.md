# Hoàn thiện cấu hình vận hành cùng hướng dẫn đọc tín hiệu và xử lý sự cố

## 1. Cấu hình vận hành phải giúp đưa ra quyết định

Một dịch vụ khởi động thành công chưa đồng nghĩa với việc người dùng đang được phục vụ tốt. Tiến trình có thể còn sống nhưng không truy cập được hệ thống kho; health có thể báo UP trong khi phần lớn yêu cầu chậm; cổng quản trị có thể phản hồi dù cổng nghiệp vụ đang gặp vấn đề.

Mục tiêu của bài thực hành là ghép các khả năng của Spring Boot Actuator thành một cấu hình có thể giải thích, kiểm chứng và bàn giao cho người vận hành. Sau bài này, cần trả lời được bốn câu hỏi:

1. Tiến trình có cần khởi động lại không?
2. Thể hiện ứng dụng này có nên nhận yêu cầu mới không?
3. Người dùng đang gặp lỗi hay chậm ở mức nào?
4. Cần thu thập bằng chứng và giảm ảnh hưởng theo thứ tự nào?

Ba lớp tín hiệu bổ sung cho nhau:

| Lớp | Câu hỏi chính | Giới hạn |
| --- | --- | --- |
| Health và probe | Có sống, có sẵn sàng, thành phần nào báo lỗi? | Một ảnh chụp trạng thái không mô tả toàn bộ trải nghiệm người dùng |
| Số đo vận hành (metrics) | Lỗi, độ trễ, tải và tài nguyên thay đổi ra sao theo thời gian? | Dữ liệu tổng hợp thường không chỉ ra yêu cầu cụ thể gây vấn đề |
| Nhật ký (log), và trace nếu đã cấu hình | Điều gì xảy ra với một lần xử lý cụ thể? | Thiếu ngữ cảnh thời gian hoặc thiếu lấy mẫu phù hợp có thể gây kết luận sai |

Actuator cung cấp điểm đọc trạng thái và số đo. Việc lưu lịch sử, đánh giá cảnh báo và xử lý sự cố còn cần hệ thống giám sát và quy trình vận hành bên ngoài ứng dụng.

## 2. Phạm vi và sơ đồ truy cập

Ví dụ dưới đây là một ứng dụng Servlet độc lập dùng Java 21, Spring Boot 3.3.0 để cố định hành vi trong bài học. Mã dùng Maven và Spring Security. Không dùng cấu hình của Spring Boot 4.x để thay trực tiếp cho ví dụ này. Khi áp dụng vào dự án thật, dùng bản vá đã được tổ chức kiểm định, rà lại thay đổi phiên bản và chạy lại các kiểm tra bên dưới.

Ứng dụng có một API GET mô phỏng nghiệp vụ, một health indicator mô phỏng hệ thống kho, hai probe trên cổng nghiệp vụ và một cổng quản trị riêng.

~~~text
Người gọi / bộ cân bằng tải
        |
        v
8080: /api/demo, /livez, /readyz
        |
        +-- chỉ GET các đường dẫn đã cho phép

Người vận hành trên cùng máy hoặc cùng không gian mạng
        |
        v
127.0.0.1:9091/actuator
        +-- health: chỉ trạng thái, cho phép thăm dò
        +-- metrics: HTTP Basic + vai trò OPS
~~~

Trong mô hình này, cổng 9091 chỉ nghe trên loopback. Công cụ ở máy khác hoặc Pod khác không thể truy cập bằng địa chỉ mạng của máy chủ. Nếu cần bộ thu số đo từ xa, phải chủ động đổi địa chỉ bind, cấu hình mạng riêng/tường lửa, xác thực và TLS ở lớp phù hợp; chỉ tách số cổng không tạo ra một ranh giới bảo mật.

Hai đường dẫn /livez và /readyz giúp probe đi qua cổng 8080 đang phục vụ nghiệp vụ. Một lần probe thành công vẫn không chứng minh mọi API, kết nối phụ thuộc và chất lượng phục vụ đều tốt.

API /api/demo là API công khai có chủ đích của phòng thực hành. Chính sách xác thực nghiệp vụ của dịch vụ thật cần được thiết kế riêng.

## 3. Tạo ứng dụng có thể chạy độc lập

Cấu trúc thư mục:

~~~text
actuator-operations/
├── pom.xml
└── src/main/
    ├── java/example/ops/
    │   ├── OperationsApplication.java
    │   └── OperationsSecurity.java
    └── resources/application.yml
~~~

### 3.1. Khai báo thư viện

Nội dung pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>actuator-operations</artifactId>
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
~~~

Actuator starter cung cấp endpoint và tích hợp số đo. Nó không tự bổ sung mọi hệ thống xuất số đo, chẳng hạn Prometheus, chỉ vì ta đưa tên endpoint vào danh sách exposure.

### 3.2. Tạo nghiệp vụ và phụ thuộc mô phỏng

Nội dung OperationsApplication.java:

~~~java
package example.ops;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class OperationsApplication {

    private final boolean inventoryUp;
    private final long delayMillis;

    public OperationsApplication(
            @Value("${demo.dependency-up:true}") boolean inventoryUp,
            @Value("${demo.delay-ms:0}") long delayMillis) {
        if (delayMillis < 0 || delayMillis > 2000) {
            throw new IllegalArgumentException("demo.delay-ms must be 0..2000");
        }
        this.inventoryUp = inventoryUp;
        this.delayMillis = delayMillis;
    }

    public static void main(String[] args) {
        SpringApplication.run(OperationsApplication.class, args);
    }

    @Bean(name = "inventory")
    HealthIndicator inventory() {
        return () -> inventoryUp
                ? Health.up().build()
                : Health.down().build();
    }

    @GetMapping("/api/demo")
    ResponseEntity<Map<String, String>> demo() throws InterruptedException {
        Thread.sleep(delayMillis);
        if (!inventoryUp) {
            return ResponseEntity.status(503)
                    .body(Map.of("result", "inventory-unavailable"));
        }
        return ResponseEntity.ok(Map.of("result", "ok"));
    }
}
~~~

Hai giá trị mô phỏng được đọc lúc khởi động. Muốn đổi tình huống, dừng rồi chạy lại tiến trình với biến môi trường khác. Không có API công khai để thay đổi health.

Indicator inventory chỉ trả về cờ mô phỏng; nó không thực sự kiểm tra máy chủ kho. Trong dịch vụ thật, thay bằng phép kiểm tra có thời hạn chờ, chi phí phù hợp và ý nghĩa rõ ràng. Không thực hiện thao tác ghi nghiệp vụ trong health check.

Thread.sleep ở đây cố ý tạo độ trễ có giới hạn để quan sát. Đây không phải cách gọi dịch vụ từ xa trong mã nghiệp vụ thật.

### 3.3. Giới hạn truy cập bằng hai chuỗi bộ lọc

Nội dung OperationsSecurity.java:

~~~java
package example.ops;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class OperationsSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService operationsUsers(
            PasswordEncoder encoder,
            @Value("${ops.user:ops}") String username,
            @Value("${ops.password}") String password) {
        if (password.isBlank()) {
            throw new IllegalArgumentException("OPS_PASSWORD must not be blank");
        }
        return new InMemoryUserDetailsManager(
                User.withUsername(username)
                        .password(encoder.encode(password))
                        .roles("OPS")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                            .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET,
                                "/livez", "/readyz", "/api/demo").permitAll()
                        .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Chuỗi thứ nhất chỉ áp dụng cho các endpoint Actuator. Health được phép thăm dò; endpoint quản trị khác yêu cầu vai trò OPS. Chuỗi thứ hai cho phép đúng các đường dẫn GET của bài thực hành và từ chối các đường dẫn còn lại.

Khi tự khai báo SecurityFilterChain, phải tự chịu trách nhiệm về chính sách truy cập; không tiếp tục giả định cấu hình bảo vệ Actuator mặc định của Boot vẫn áp dụng như khi chưa có cấu hình tùy chỉnh.

Tài khoản trong bộ nhớ giúp ví dụ chạy độc lập. Hệ thống thật cần quản lý danh tính và cấp quyền theo chính sách vận hành, có quy trình thay/thu hồi thông tin xác thực. HTTP Basic không mã hóa thông tin xác thực; nếu đi qua mạng, cần TLS. Không đưa mật khẩu vào Git, nhãn số đo, URL hay log.

## 4. Chốt application.yml và giải thích từng quyết định

Nội dung application.yml:

~~~yaml
spring:
  application:
    name: actuator-operations
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  port: 8080
  shutdown: graceful

ops:
  user: ${OPS_USER:ops}
  password: ${OPS_PASSWORD}

demo:
  dependency-up: ${DEMO_DEPENDENCY_UP:true}
  delay-ms: ${DEMO_DELAY_MS:0}

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - metrics
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include:
            - livenessState
        readiness:
          include:
            - readinessState
            - inventory
  metrics:
    tags:
      application: ${spring.application.name}

logging:
  level:
    root: INFO
~~~

Những điểm cần hiểu trước khi dùng:

| Quyết định | Ý nghĩa vận hành |
| --- | --- |
| Chỉ expose health và metrics | Danh sách cho phép nhỏ, phù hợp mục tiêu bài học |
| Không dùng exposure.include=* | Không vô tình mở rộng bề mặt quản trị khi thêm thư viện hoặc endpoint mới |
| show-details/show-components=never | Người thăm dò nhận trạng thái, không nhận cấu trúc và chi tiết phụ thuộc |
| Bật probes rõ ràng | Có liveness/readiness cả khi chạy ngoài Kubernetes |
| add-additional-paths=true | Có /livez và /readyz trên cổng chính, kể cả khi management dùng cổng khác |
| Liveness chỉ gồm livenessState | Lỗi hệ thống kho không tự biến thành lý do khởi động lại tiến trình |
| Readiness gồm readinessState và inventory | Trong ví dụ, không có kho thì thể hiện ứng dụng không phục vụ được nghiệp vụ |
| Nhãn application cố định | Phân biệt dịch vụ với số lượng giá trị hữu hạn |
| Graceful shutdown và thời gian chờ 30s | Cho phép giai đoạn dừng xử lý yêu cầu đang chạy trong giới hạn cấu hình |

Readiness có chứa phụ thuộc ngoài hay không là một quyết định kiến trúc. Nếu một phụ thuộc dùng chung hỏng khiến mọi thể hiện đồng thời không sẵn sàng, toàn bộ dịch vụ có thể bị rút khỏi cân bằng tải. Chỉ đưa phụ thuộc vào readiness khi cách rút lưu lượng đó có ý nghĩa; đánh giá khả năng trả kết quả dự phòng, phục vụ một phần và chính sách của bộ cân bằng tải.

Thời hạn graceful shutdown không tự cấu hình khoảng chờ của Kubernetes hay bộ cân bằng tải. Cần phối hợp thời gian phát hiện không sẵn sàng, rút lưu lượng, xử lý yêu cầu đang chạy và thời gian trước khi hệ điều hành cưỡng chế dừng.

Đừng nhầm ba điều kiện: endpoint có được tạo/bật, có được expose qua HTTP, và người gọi có được cấp quyền hay không. Thêm một tên vào exposure không tạo ra endpoint còn thiếu thư viện.

## 5. Khởi động và kiểm chứng đường đi bình thường

Các lệnh sau dùng Bash, Maven có trên PATH và JDK 21. Lần build đầu cần tải thư viện từ kho Maven.

Tại thư mục actuator-operations, nhập mật khẩu cho phòng thực hành mà không ghi giá trị thật vào ví dụ:

~~~bash
read -r -s -p "OPS password: " OPS_PASSWORD
printf '\n'
export OPS_PASSWORD

mvn clean package
java -jar target/actuator-operations-1.0.0.jar
~~~

Giữ terminal này chạy; mở terminal khác để thực hiện các lệnh curl. Đợi log xác nhận ứng dụng khởi động hoàn tất trước khi đánh giá readiness. Dùng curl.exe nếu chạy các lệnh tương đương trong PowerShell để tránh nhầm với bí danh của công cụ khác.

~~~bash
curl -i http://localhost:8080/api/demo
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://127.0.0.1:9091/actuator/health
curl -i http://127.0.0.1:9091/actuator/health/liveness
curl -i http://127.0.0.1:9091/actuator/health/readiness
~~~

Sau khi sẵn sàng, với giá trị mặc định của phần mô phỏng:

| Yêu cầu | HTTP kỳ vọng | Nội dung cần kiểm tra |
| --- | --- | --- |
| GET /api/demo trên 8080 | 200 | result là ok |
| GET /livez trên 8080 | 200 | status là UP |
| GET /readyz trên 8080 | 200 | status là UP |
| GET /actuator/health trên 9091 | 200 nếu các contributor khác cũng tốt | status là UP, không lộ chi tiết |
| GET /actuator/health/liveness trên 9091 | 200 | status là UP |
| GET /actuator/health/readiness trên 9091 | 200 | status là UP |

Với cài đặt tối giản và máy còn dung lượng đĩa, health tổng thường UP. Nếu diskSpace hay một contributor được thư viện bổ sung báo DOWN, health tổng có thể khác hai nhóm đã chọn. Không sửa kỳ vọng bằng cách bỏ qua lỗi thực tế.

Kiểm tra xác thực số đo:

~~~bash
curl -i http://127.0.0.1:9091/actuator/metrics
curl -i -u ops http://127.0.0.1:9091/actuator/metrics
~~~

Lệnh thứ nhất phải bị yêu cầu xác thực, thông thường trả 401 trong cấu hình này. Với lệnh thứ hai, curl hỏi mật khẩu tương tác; nhập cùng mật khẩu đã dùng để chạy ứng dụng. Kỳ vọng 200 cùng danh sách names. Nếu đã đặt OPS_USER khác ops, thay tên người dùng trong lệnh.

Kiểm tra thêm một yêu cầu không nằm trong danh sách, chẳng hạn GET /private trên 8080. Kết quả phải bị chính sách từ chối, không xuất hiện một API công khai ngoài dự kiến. Không dùng riêng kiểm tra âm tính này để chứng minh toàn bộ cấu hình bảo mật là đúng.

Các bảng trên mô tả điều kiện kiểm chứng; không nên kỳ vọng header HTTP, thứ tự thuộc tính JSON, thời điểm khởi động hay số lượng meter giống hệt giữa các máy.

## 6. Đọc số đo theo câu hỏi, không theo một con số rời rạc

Tạo một ít lưu lượng trước khi tìm meter HTTP:

~~~bash
for i in $(seq 1 10); do
  curl -sS -o /dev/null http://localhost:8080/api/demo
done

curl -sS -u ops \
  http://127.0.0.1:9091/actuator/metrics/http.server.requests
~~~

Meter có thể chỉ xuất hiện sau khi có yêu cầu phù hợp. Đọc availableTags để biết tên và giá trị nhãn thực tế, sau đó lọc đúng nhóm:

~~~bash
curl -sS -u ops --get \
  http://127.0.0.1:9091/actuator/metrics/http.server.requests \
  --data-urlencode 'tag=uri:/api/demo' \
  --data-urlencode 'tag=method:GET'
~~~

Một timer HTTP thường cung cấp COUNT, TOTAL_TIME, MAX; đọc baseUnit thay vì tự giả định đơn vị. Với timer được trình bày bằng giây, TOTAL_TIME/COUNT là thời gian trung bình của tập đang được tổng hợp, không phải p95/p99.

Ví dụ tính toán bằng số liệu giả định, trên cùng một thể hiện ứng dụng chưa khởi động lại:

~~~text
Tại t0: COUNT = 100, TOTAL_TIME = 12 giây
Tại t1: COUNT = 160, TOTAL_TIME = 30 giây
Khoảng đo: 60 giây

Lưu lượng trung bình = (160 - 100) / 60 = 1 yêu cầu/giây
Thời gian trung bình = (30 - 12) / (160 - 100) = 0,3 giây
~~~

Nếu có 6 phản hồi 5xx trong 60 yêu cầu mới cùng phạm vi lọc, tỷ lệ 5xx là 10%. Cần đo cùng cửa sổ và cùng tập nhãn; không chia số lỗi của một route cho tổng yêu cầu của route khác.

Chú ý khi diễn giải:

- COUNT và TOTAL_TIME là số tích lũy; không lấy tốc độ bằng cách đọc một lần. Khởi động lại làm mất liên tục của chuỗi số tích lũy trong tiến trình.
- MAX có thể là giá trị theo cửa sổ thời gian của registry; không mặc định đó là cực đại kể từ khi tiến trình khởi động.
- Trung bình thấp có thể che giấu một nhóm nhỏ yêu cầu rất chậm. Muốn đánh giá phân vị, cần cấu hình phân phối phù hợp và dùng hệ thống lưu/đọc hỗ trợ.
- availableTags giúp xác nhận nhãn đang tồn tại, không phải nơi để suy ra mọi giá trị có thể có.
- API đang trả 503 không nhất thiết ném exception. Ví dụ này chủ động trả ResponseEntity 503, nên cần quan sát status, không chỉ nhãn exception.
- Không dùng ID đơn hàng, ID người dùng, token, URL đầy đủ có tham số biến thiên hoặc thông báo lỗi làm nhãn. Số lượng tổ hợp nhãn tăng mạnh sẽ làm hệ thống số đo tốn tài nguyên.

Những meter nên đối chiếu, nếu chúng có mặt trong danh sách names:

| Meter | Dùng để kiểm tra | Cách đọc cần thận trọng |
| --- | --- | --- |
| http.server.requests | Lưu lượng, mã trạng thái, thời gian xử lý | Phân loại theo route/method/status; loại lưu lượng probe khỏi chỉ số nghiệp vụ khi thích hợp |
| process.uptime | Tiến trình đã chạy bao lâu | Giá trị thấp bất thường có thể gợi ý vừa khởi động lại; đối chiếu sự kiện triển khai |
| process.cpu.usage | Tỷ phần CPU của tiến trình | Đọc theo khả năng môi trường/JVM; không tự đồng nhất với phần trăm CPU hiển thị của mọi công cụ hệ điều hành |
| jvm.memory.used, jvm.memory.max | Bộ nhớ theo vùng/pool | So sánh cùng pool và tính hợp lệ của max; không cộng hoặc chia tùy tiện các vùng khác nhau |
| jvm.gc.pause | Các lần dừng do GC | So khớp thời gian và tần suất với độ trễ; một lần GC không đủ kết luận rò rỉ bộ nhớ |
| jvm.threads.live | Số luồng JVM còn sống | Không phải số luồng HTTP đang bận hay số yêu cầu đang chờ |

Actuator /metrics là công cụ chẩn đoán tại thời điểm đọc, không phải kho lịch sử. Muốn biểu đồ và cảnh báo bền vững, cần registry/exporter, bộ thu và nơi lưu thích hợp.

Nếu chọn Prometheus, bổ sung dependency io.micrometer:micrometer-registry-prometheus, expose thêm prometheus và cấu hình bộ thu truy cập có xác thực. Tên meter trong /metrics như http.server.requests khác cách biểu diễn trong exposition Prometheus; đừng sao chép nguyên tên đó vào truy vấn mà chưa kiểm tra dữ liệu xuất thực tế.

## 7. Thực hành phụ thuộc hỏng: còn sống nhưng không sẵn sàng

Dừng ứng dụng bằng Ctrl+C. Trong terminal khởi chạy vẫn có OPS_PASSWORD, chạy lại:

~~~bash
DEMO_DEPENDENCY_UP=false \
java -jar target/actuator-operations-1.0.0.jar
~~~

Sau khi quá trình khởi động hoàn tất, đọc lại:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/api/demo
curl -i http://127.0.0.1:9091/actuator/health
~~~

Kỳ vọng trong cấu hình bài học:

| Tín hiệu | Kết quả | Diễn giải |
| --- | --- | --- |
| /livez | 200, UP | Tiến trình vẫn có khả năng sống; lỗi kho không nằm trong liveness |
| /readyz | 503, DOWN | Nhóm readiness có inventory nên không sẵn sàng nhận yêu cầu |
| /api/demo | 503, result là inventory-unavailable | Người gọi trực tiếp vẫn tới ứng dụng và nhận lỗi nghiệp vụ mô phỏng |
| /actuator/health | 503, DOWN | Health tổng có contributor inventory báo DOWN |

Readiness không tự chặn controller. Nó cung cấp tín hiệu để nền tảng/bộ cân bằng tải quyết định có chuyển yêu cầu đến thể hiện này hay không. Gọi thẳng vào cổng ứng dụng vẫn có thể vào API như bảng trên.

Bài học về xử lý: nếu hệ thống kho thật bị lỗi, khởi động lại mọi thể hiện thường không sửa được kho, còn có thể gây bão kết nối và làm chậm phục hồi. Trước hết kiểm tra tình trạng phụ thuộc, đường mạng, thời hạn chờ, cơ chế trả kết quả dự phòng và ảnh hưởng đến người dùng.

Trong mô phỏng, phục hồi bằng cách dừng ứng dụng rồi chạy lại không có DEMO_DEPENDENCY_UP=false. Đây là cách đổi cờ của phòng thực hành, không phải khuyến nghị khởi động lại ứng dụng để chữa mọi lỗi phụ thuộc ngoài.

## 8. Thực hành phản hồi chậm: health vẫn UP

Dừng tiến trình mô phỏng lỗi. Chạy lại với phụ thuộc tốt và độ trễ 400 ms:

~~~bash
DEMO_DEPENDENCY_UP=true DEMO_DELAY_MS=400 \
java -jar target/actuator-operations-1.0.0.jar
~~~

Đợi sẵn sàng, sau đó:

~~~bash
curl -i http://localhost:8080/readyz
curl -sS -o /dev/null -w 'HTTP=%{http_code} seconds=%{time_total}\n' \
  http://localhost:8080/api/demo
~~~

Readiness kỳ vọng UP và API trả 200, nhưng thời gian phản hồi sẽ xấp xỉ 0,4 giây cộng thêm chi phí xử lý/mạng/lập lịch. Không coi 0,400000 giây là stdout cố định.

Đọc timer HTTP có lọc uri sau một số yêu cầu. Đối chiếu độ trễ quan sát từ bên ngoài với thời gian phía server. Hai phép đo có phạm vi khác nhau: phía người gọi còn có DNS, thiết lập kết nối, proxy và thời gian truyền mạng.

Khi áp dụng vào sự cố thật, cần phân biệt:

1. Chậm do lưu lượng vượt khả năng phục vụ: hàng đợi, pool luồng hoặc kết nối đạt giới hạn.
2. Chậm do phụ thuộc: DB, dịch vụ từ xa, DNS hoặc mạng phản hồi lâu.
3. Chậm do tài nguyên: CPU, GC, bộ nhớ, đĩa.
4. Chậm do bản phát hành: truy vấn mới, thay đổi thuật toán, timeout hay cấu hình.

Không tăng pool hay tăng timeout chỉ vì thấy độ trễ cao. Nếu DB đã quá tải, tăng kết nối có thể làm tình hình nặng hơn; tăng timeout có thể giữ thêm luồng và kết nối trong trạng thái chờ.

## 9. Đặt cảnh báo theo tác động và thời gian

Một cảnh báo cần có phạm vi, thời gian đánh giá, điều kiện dữ liệu và hành động tiếp theo. Các giá trị sau chỉ là ví dụ để tập thiết kế, không phải ngưỡng chuẩn cho mọi hệ thống:

| Điều kiện giả định | Cửa sổ | Cách xác nhận trước khi hành động |
| --- | --- | --- |
| Tỷ lệ 5xx > 5% trên API nghiệp vụ, đủ ít nhất 100 yêu cầu | 5 phút | Xác nhận tập route, tổng lưu lượng và mã lỗi; xem có triển khai mới không |
| p95 > 800 ms | 10 phút | Chỉ dùng khi dữ liệu phân vị/histogram đã được cấu hình đúng; đối chiếu mục tiêu dịch vụ |
| Readiness lỗi liên tiếp | Theo probe và chính sách nền tảng | Xác định một thể hiện hay toàn bộ dịch vụ; kiểm tra phụ thuộc dùng chung |
| Số lần khởi động lại tăng | Khoảng thời gian đã quy định | Đọc lý do thoát, sự kiện OOM, probe và lịch triển khai |

Khi lưu lượng rất ít, một yêu cầu lỗi có thể làm tỷ lệ lỗi tăng mạnh. Khi mất dữ liệu, không mặc định là không có lỗi. Hệ thống giám sát cần phân biệt lỗi dịch vụ, lỗi bộ thu và dữ liệu không còn cập nhật.

Chỉ thêm cảnh báo khi có người chịu trách nhiệm và một hành động xác minh cụ thể. Tránh tạo nhiều cảnh báo khác nhau cho cùng một nguyên nhân mà không có cơ chế gom nhóm.

## 10. Quy trình xử lý sự cố từ triệu chứng đến phục hồi

### Bước 1: Xác định tác động và mốc thời gian

Ghi lại thời điểm bắt đầu, múi giờ, môi trường, tên dịch vụ, bản phát hành, thể hiện bị ảnh hưởng, route lỗi và số người/yêu cầu chịu ảnh hưởng nếu đo được. Kiểm tra sự cố có trùng triển khai hoặc đổi cấu hình không.

So sánh đồng hồ và cửa sổ đo trước khi ghép biểu đồ với log. Không kết luận “sau triển khai nên do triển khai” nếu chưa có bằng chứng.

### Bước 2: Kiểm tra khả năng truy cập trước khi đọc nội dung

Xác định URL, cổng, đường dẫn và vị trí máy đang gọi. Phân biệt:

- Connection refused: không có listener phù hợp hoặc kết nối bị từ chối; kiểm tra tiến trình, bind và cổng.
- Timeout: có thể do mạng, hàng đợi, ứng dụng quá tải hoặc thời hạn chờ ở lớp trung gian.
- Lỗi TLS: kiểm tra tên máy, chứng chỉ, CA và nơi kết thúc TLS.
- HTTP đã trả về: chuyển sang phân tích mã trạng thái và quyền truy cập.

Không dùng curl -k để che lỗi chứng chỉ rồi coi kiểm tra TLS đã đạt.

### Bước 3: Ghép trạng thái với tín hiệu người dùng

Đọc liveness, readiness, health tổng và thử một nghiệp vụ nhỏ an toàn. Tiếp đó xem lưu lượng, 5xx và độ trễ theo thời gian. Cùng một UP có thể đi kèm tình trạng người dùng rất khác nhau.

Nếu readiness hỏng trên một thể hiện nhưng thể hiện khác phục vụ tốt, ưu tiên rút lưu lượng khỏi thể hiện đó theo quy trình. Nếu toàn bộ cùng hỏng, kiểm tra thay đổi chung và phụ thuộc dùng chung trước.

### Bước 4: Thu thập bằng chứng vừa đủ

Đọc log quanh mốc lỗi, tìm exception gốc, timeout, lỗi kết nối hoặc pool cạn. Nếu đã có trace/correlation ID, dùng nó để đối chiếu một lần xử lý; việc thêm Actuator starter không tự bảo đảm hệ thống đã xuất trace đầy đủ.

Khi CPU, luồng hoặc GC bất thường, dùng chẩn đoán phù hợp theo quyền vận hành. Thread dump/heap dump có thể tốn tài nguyên và chứa dữ liệu nhạy cảm; chỉ thu khi có mục đích, vị trí lưu và người được phép truy cập rõ ràng. Không mở công khai heapdump để tiện tải.

### Bước 5: Giảm ảnh hưởng bằng thay đổi có thể kiểm chứng

Chọn một hành động có giả thuyết: quay lui bản phát hành, giảm tải, giới hạn tính năng bị lỗi, phục hồi phụ thuộc, hoặc khởi động lại một thể hiện khi có cơ sở. Ghi lại thời điểm, người thực hiện, phạm vi, kỳ vọng và cách quay lui.

Ưu tiên một thay đổi mỗi lần khi tình huống cho phép. Thay pool, timeout và số thể hiện cùng lúc sẽ khó xác định điều gì thực sự cải thiện.

### Bước 6: Xác nhận phục hồi bằng cả kỹ thuật và nghiệp vụ

Không đóng sự cố chỉ vì /health trở lại UP. Kiểm tra lưu lượng thực đã trở lại, lỗi/độ trễ ổn định trong cửa sổ hợp lý, hàng đợi giảm và nghiệp vụ quan trọng hoạt động. Kiểm tra các thể hiện vừa phục hồi có nhận lại lưu lượng đúng cách.

Khôi phục mức log đã tăng tạm thời, thu hồi quyền chẩn đoán tạm và ghi lại nguyên nhân đã biết/chưa biết. Nếu mới chỉ giảm ảnh hưởng, nói rõ điều đó trong bàn giao.

## 11. Bảng tra nhanh khi endpoint không như kỳ vọng

| Hiện tượng | Kiểm tra trước | Hành động phù hợp |
| --- | --- | --- |
| /metrics trả 401 | Đã gửi Basic đúng tài khoản/mật khẩu chưa? | Sửa thông tin xác thực của công cụ; không mở permitAll cho metrics để né lỗi |
| Trả 403 | Quyền OPS, chuỗi bộ lọc được chọn, phương thức HTTP; với thao tác thay đổi còn có CSRF | Sửa chính sách đúng phạm vi; không tắt bảo vệ toàn ứng dụng |
| Trả 404 | Đúng cổng/base-path chưa; endpoint có được tạo và expose không; có bị proxy hoặc chuỗi bảo mật che khuất không? | Đối chiếu cấu hình hiệu lực và mapping, không chỉ nhìn file YAML gốc |
| Không có /prometheus | Đã có registry Prometheus và đã expose prometheus chưa? | Bổ sung đúng thư viện/cấu hình rồi kiểm chứng quyền truy cập |
| Meter HTTP chưa tồn tại | Đã có request hoàn tất chưa; đã đọc names/availableTags chưa? | Tạo lưu lượng mẫu, dùng đúng tên meter và tag thực tế |
| Readiness DOWN, liveness UP | Nhóm readiness gồm gì; một hay mọi thể hiện bị ảnh hưởng? | Kiểm tra khả năng phục vụ và phụ thuộc, tránh khởi động lại hàng loạt |
| Cổng quản trị tốt, API chậm | Hai cổng có thể phục vụ độc lập ở một số lớp; API có chờ pool/DB không? | Kiểm tra probe trên cổng chính và tín hiệu nghiệp vụ |
| Restart liên tục nhưng lỗi gốc là DB | Đã đưa DB vào liveness hoặc timeout probe quá gắt chưa? | Sửa thiết kế probe; dùng log/sự kiện để xác nhận nguyên nhân restart |
| Health trả UP nhưng khách hàng lỗi | Health có bao phủ đúng điều kiện phục vụ không; có lỗi ở ingress/proxy không? | Đối chiếu 5xx, độ trễ và giao dịch kiểm thử từ bên ngoài |
| Giá trị số đo “giảm đột ngột” | Tiến trình vừa restart, tag/pool đổi, hay đang xem MAX theo cửa sổ? | Xác định lại chuỗi thời gian trước khi tính chênh lệch |

HTTP 503 từ một endpoint health là kết quả đánh giá trạng thái, không phải lỗi xác thực. Ngược lại, 401/403 không chứng minh contributor bên trong đang DOWN.

## 12. Chẩn đoán tạm thời phải có điểm kết thúc

Cấu hình cơ sở chỉ expose health và metrics. Các endpoint như loggers, threaddump, heapdump, env hoặc configprops cần được đánh giá riêng; không thêm hàng loạt chỉ để tiện xử lý một sự cố.

Nếu cần đọc/thay đổi mức log qua loggers:

1. Xác định chính xác package cần quan sát, khoảng thời gian và người thực hiện.
2. Chỉ expose endpoint trong phạm vi quản trị đã bảo vệ; xác minh lại quyền.
3. Ghi mức cấu hình và mức hiệu lực ban đầu.
4. Khi dùng thao tác POST, xử lý yêu cầu CSRF theo chính sách bảo mật đã chọn; cấu hình của bài không vô hiệu hóa CSRF.
5. Tăng mức log cho đúng package; theo dõi dung lượng và nguy cơ lộ dữ liệu.
6. Trả về cấu hình ban đầu, kể cả trạng thái kế thừa mức log nếu trước đó chưa đặt mức riêng.
7. Gỡ exposure/quyền tạm theo quy trình và kiểm chứng.

Thay đổi logger trong tiến trình không mặc nhiên sửa file cấu hình hoặc áp dụng cho mọi thể hiện. Một lần khởi động lại cũng có thể làm mất thay đổi tạm thời. Tương tự, che giá trị trong env/configprops không phải lý do để mở các endpoint đó cho mọi người.

## 13. Hồ sơ bàn giao vận hành

Hoàn thiện một bản hướng dẫn ngắn đi kèm bản phát hành. Nội dung cần đủ để người trực chưa viết ứng dụng vẫn biết đọc tín hiệu và hành động:

- Sơ đồ cổng/đường dẫn: API, probe và quản trị; vị trí nào được gọi từ đâu.
- Danh sách endpoint expose, cơ chế xác thực, vai trò, nơi quản lý bí mật và cách thu hồi.
- Thành phần của liveness/readiness, ý nghĩa từng phép kiểm tra và hành động của nền tảng khi probe hỏng.
- Cấu hình hiệu lực theo môi trường, nguồn ghi đè cấu hình và định danh bản phát hành; không chép giá trị bí mật vào hồ sơ.
- Các biểu đồ/cảnh báo chính, phạm vi route, đơn vị, cửa sổ, ngưỡng và cách xử lý mất dữ liệu.
- Nơi xem log/trace, thời gian lưu, múi giờ, cách tìm bằng ID đối chiếu nếu có.
- Hướng dẫn lỗi phụ thuộc, phản hồi chậm, lỗi truy cập endpoint, khởi động lại liên tục và quay lui.
- Người chịu trách nhiệm, tiêu chí phục hồi, vị trí lưu bằng chứng và cách bàn giao sự cố chưa giải quyết tận gốc.

Không cần ghi mọi thuộc tính Spring vào tài liệu bàn giao. Cần ghi những quyết định ảnh hưởng trực tiếp đến truy cập, chẩn đoán và phục hồi.

## 14. Tự kiểm tra trước khi coi cấu hình đã hoàn thiện

Thực hiện lại trên môi trường dự kiến, không chỉ trên máy cá nhân:

1. Khởi động với cấu hình hợp lệ; thiếu bí mật bắt buộc hoặc giá trị mô phỏng sai phải được phát hiện rõ.
2. Kiểm tra đúng cổng và phạm vi bind; từ vị trí không được phép phải không truy cập được cổng quản trị.
3. Xác nhận health/probe chỉ lộ lượng thông tin đã chọn; metrics yêu cầu đúng danh tính và quyền.
4. Tạo request nghiệp vụ, kiểm tra meter xuất hiện, tag/đơn vị đúng và có thể đối chiếu với log.
5. Mô phỏng phụ thuộc hỏng: liveness giữ UP, readiness đổi DOWN theo thiết kế, nền tảng thực hiện rút lưu lượng đúng.
6. Mô phỏng chậm: health có thể UP nhưng số đo bên ngoài và timer phải phản ánh tình huống.
7. Thử dừng có kiểm soát; kiểm tra yêu cầu đang chạy, thời gian rút lưu lượng và thời hạn cưỡng chế dừng của môi trường.
8. Sau phục hồi, kiểm tra nghiệp vụ, lỗi/độ trễ và dữ liệu giám sát; dọn mọi cấu hình chẩn đoán tạm.
9. Để một người khác thực hiện theo hồ sơ bàn giao và ghi lại chỗ chưa rõ.

Hai câu hỏi cuối để tự đánh giá: nếu readiness DOWN nhưng liveness UP, bạn dự định làm gì và dựa trên bằng chứng nào? Nếu mọi health đều UP nhưng p95 tăng gấp ba, bạn sẽ kiểm tra thêm tín hiệu nào trước khi thay đổi cấu hình?
