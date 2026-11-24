# Bootstrap ứng dụng Java và công bố health endpoint

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Khởi tạo một ứng dụng Java chạy bằng Spring Boot và đóng gói thành JAR.
- Tạo endpoint nghiệp vụ đơn giản để xác nhận ứng dụng có thể nhận request.
- Tích hợp Spring Boot Actuator và công bố health endpoint qua HTTP.
- Phân biệt trạng thái liveness, readiness và startup để cấu hình kiểm tra phù hợp.
- Đóng gói ứng dụng thành container, cấu hình cổng và biến môi trường.
- Kết nối health endpoint với Kubernetes probe hoặc health check của nền tảng container.
- Kiểm chứng hành vi khi ứng dụng khởi động, sẵn sàng, gặp lỗi và dừng.

## 1. Bootstrap ứng dụng Java trong môi trường cloud

Bootstrap là bước tạo cấu trúc ứng dụng, chọn runtime và dependency, thiết lập cấu hình khởi động, sau đó xác nhận ứng dụng có thể chạy trong môi trường mục tiêu. Với workload cloud, ứng dụng cần khởi động nhất quán, nhận cấu hình từ môi trường triển khai, ghi log ra stdout/stderr và cung cấp tín hiệu sức khỏe để nền tảng điều phối biết khi nào có thể gửi traffic.

Bài thực hành dùng Java 21 và Spring Boot. Spring Boot tự cấu hình phần lớn thành phần web, quản lý dependency và cung cấp cơ chế Actuator cho health endpoint. Có thể dùng Spring Boot phiên bản còn được hỗ trợ và tương thích với JDK của tổ chức; hãy để Spring Initializr hoặc parent/BOM của dự án quản lý phiên bản dependency đồng bộ.

Một ứng dụng nhỏ có thể được tạo bằng Spring Initializr với các lựa chọn:

| Thuộc tính | Giá trị gợi ý |
|---|---|
| Project | Maven |
| Language | Java |
| Java | 21 |
| Packaging | Jar |
| Dependencies | Spring Web, Spring Boot Actuator |
| Group | **com.example** |
| Artifact | **cloud-api** |
| Package | **com.example.cloudapi** |

Nếu tổ chức có project template hoặc dependency catalog, ưu tiên cấu hình chuẩn đó để thống nhất phiên bản Java, Spring Boot, plugin và quy tắc bảo mật.

### 1.1. Cấu trúc thư mục

Một cấu trúc Maven tối thiểu:

    cloud-api/
    ├── mvnw
    ├── mvnw.cmd
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/com/example/cloudapi/
        │   │   ├── CloudApiApplication.java
        │   │   └── HealthDemoController.java
        │   └── resources/
        │       └── application.yml
        └── test/
            └── java/com/example/cloudapi/

Maven Wrapper (mvnw hoặc mvnw.cmd) giúp nhóm phát triển và pipeline sử dụng cùng phiên bản Maven mà không phụ thuộc Maven cài sẵn trên máy. Commit wrapper và các file cấu hình dự án theo quy ước repository.

### 1.2. Dependency cần thiết

Trong **pom.xml**, ứng dụng cần Spring Boot web starter và Actuator. Ví dụ phần dependencies:

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
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
      </dependency>
    </dependencies>

Phần parent hoặc dependency management phải dùng Spring Boot BOM tương thích với Java đã chọn. Spring Initializr tạo sẵn cấu hình đó. Không tự đặt phiên bản riêng cho từng starter khi chúng thuộc cùng một Spring Boot release train, vì có thể gây lệch dependency.

## 2. Tạo điểm khởi động và endpoint nghiệp vụ

Lớp khởi động đánh dấu package gốc để Spring quét component, cấu hình và controller.

    package com.example.cloudapi;

    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;

    @SpringBootApplication
    public class CloudApiApplication {
        public static void main(String[] args) {
            SpringApplication.run(CloudApiApplication.class, args);
        }
    }

**@SpringBootApplication** kết hợp cấu hình tự động, component scanning và cấu hình bean. Nên đặt lớp này ở package gốc để controller, service và cấu hình con nằm trong phạm vi quét.

Tạo một endpoint nghiệp vụ đơn giản để phân biệt ứng dụng đã nhận request với health endpoint:

    package com.example.cloudapi;

    import java.util.Map;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    public class HealthDemoController {
        @GetMapping("/api/hello")
        public Map<String, String> hello() {
            return Map.of(
                "service", "cloud-api",
                "message", "Application is running"
            );
        }
    }

Endpoint **/api/hello** xác nhận luồng HTTP và controller hoạt động. Nó không thay thế health endpoint: một request nghiệp vụ có thể thất bại do dữ liệu hoặc quyền trong khi tiến trình vẫn sống; ngược lại, một endpoint trả lời được chưa chắc mọi dependency quan trọng đều sẵn sàng.

## 3. Cấu hình ứng dụng và cổng HTTP

Tạo **src/main/resources/application.yml**:

    spring:
      application:
        name: cloud-api
      lifecycle:
        timeout-per-shutdown-phase: 20s

    server:
      port: 8080
      shutdown: graceful

    management:
      endpoints:
        web:
          exposure:
            include: health
      endpoint:
        health:
          show-details: never
          probes:
            enabled: true

Các cấu hình chính:

- **spring.application.name** đặt tên service để log, metric và hệ thống quan sát nhận diện ứng dụng.
- **server.port** đặt cổng mặc định 8080. Spring Boot có thể nhận giá trị ghi đè từ biến môi trường **SERVER_PORT**.
- **server.shutdown: graceful** cho phép Spring Boot ngừng nhận request mới và chờ request đang xử lý trong thời gian cấu hình.
- **timeout-per-shutdown-phase** đặt giới hạn cho giai đoạn dừng.
- **management.endpoints.web.exposure.include: health** chỉ công bố health endpoint qua web.
- **management.endpoint.health.show-details: never** tránh trả chi tiết nội bộ cho request không được phép.
- **management.endpoint.health.probes.enabled: true** bật các health group dành cho liveness và readiness.

Chỉ expose endpoint thực sự cần thiết. Không dùng **include: "*"** trong production nếu chưa đánh giá quyền truy cập, vì Actuator có thể cung cấp thông tin môi trường và khả năng thao tác quản trị. Không đưa secret, token, connection string hoặc thông tin cá nhân vào health response.

Có thể cấu hình cổng quản trị riêng bằng **management.server.port**, nhưng cần cân nhắc đường mạng và probe. Nếu health endpoint ở cổng riêng, probe có thể vẫn thành công trong khi cổng ứng dụng chính không nhận được traffic. Với workload container đơn giản, dùng cùng cổng thường giúp kiểm tra đúng khả năng phục vụ của ứng dụng.

## 4. Công bố health endpoint bằng Spring Boot Actuator

Spring Boot Actuator cung cấp endpoint **/actuator/health**. Khi ứng dụng khởi động, Actuator tổng hợp các health contributor được cấu hình và trả trạng thái tổng thể.

Sau khi chạy ứng dụng, gọi:

    curl -i http://localhost:8080/actuator/health

Một response thành công thường có dạng:

    HTTP/1.1 200
    Content-Type: application/vnd.spring-boot.actuator.v3+json

    {
      "status": "UP"
    }

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| **UP** | Thành phần được kiểm tra đang hoạt động |
| **DOWN** | Thành phần không hoạt động hoặc không đạt điều kiện |
| **OUT_OF_SERVICE** | Thành phần tạm thời không phục vụ |
| **UNKNOWN** | Chưa xác định được trạng thái |

Thông thường, **UP** trả HTTP 200; **DOWN** hoặc **OUT_OF_SERVICE** trả HTTP 503. Client và nền tảng điều phối nên dựa trên mã HTTP cùng nội dung trạng thái, không chỉ kiểm tra rằng server có trả về JSON.

Health endpoint là tín hiệu vận hành, không phải endpoint nghiệp vụ. Nó nên nhanh, có giới hạn thời gian và tránh thực hiện truy vấn nặng mỗi lần được gọi. Một health check chậm có thể làm nền tảng kết luận nhầm rằng ứng dụng không khỏe.

## 5. Phân biệt liveness, readiness và startup

Ba loại kiểm tra trả lời ba câu hỏi khác nhau:

| Loại | Câu hỏi | Khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất quá trình khởi động chưa? | Nền tảng tiếp tục chờ trong giới hạn; quá giới hạn thì khởi động lại |
| Liveness | Tiến trình còn hoạt động và có thể tiếp tục chạy không? | Nền tảng có thể restart instance/container |
| Readiness | Instance đã sẵn sàng nhận traffic chưa? | Nền tảng ngừng gửi traffic đến instance đó |

### 5.1. Liveness

Liveness cho biết tiến trình có còn khả năng hoạt động hay đã rơi vào trạng thái không thể tự phục hồi, ví dụ deadlock hoặc vòng lặp làm ứng dụng ngừng tiến triển. Nếu liveness thất bại liên tục, Kubernetes có thể restart container.

Không đưa database, message broker hoặc API bên ngoài vào liveness check. Khi database tạm ngừng, restart hàng loạt Pod không khắc phục được database; nó có thể làm hệ thống quá tải hơn khi các Pod cùng khởi động và mở kết nối lại. Liveness nên tập trung vào trạng thái nội tại của ứng dụng.

Spring Boot cung cấp **/actuator/health/liveness** khi bật probes. Endpoint này thường phản ánh **livenessState**.

### 5.2. Readiness

Readiness cho biết instance có thể nhận request mới hay không. Ứng dụng có thể đang chạy nhưng chưa sẵn sàng vì đang khởi tạo cache, nạp cấu hình, hoàn tất migration cần thiết hoặc mất một dependency bắt buộc.

Spring Boot cung cấp **/actuator/health/readiness**. Endpoint này phản ánh **readinessState** và có thể được mở rộng bằng health contributor phù hợp.

Chỉ thêm dependency vào readiness khi dependency đó thực sự cần cho chức năng cốt lõi. Nếu mọi dependency phụ như email hoặc analytics đều nằm trong readiness, một sự cố phụ có thể làm toàn bộ API ngừng nhận traffic dù nghiệp vụ chính vẫn phục vụ được.

### 5.3. Startup probe

Startup probe hữu ích với ứng dụng khởi động chậm. Trong thời gian startup probe chưa thành công, Kubernetes chưa thực hiện liveness và readiness probe. Điều này tránh restart ứng dụng chỉ vì thời gian khởi động dài hơn **initialDelaySeconds** của liveness.

Startup probe nên có ngưỡng đủ cho thời gian khởi động p95/p99 cộng khoảng dự phòng. Không đặt ngưỡng quá lớn vì một ứng dụng thực sự treo sẽ mất nhiều thời gian mới được phát hiện.

### 5.4. Health group và đường dẫn probe

Với cấu hình **management.endpoint.health.probes.enabled=true**, Spring Boot công bố:

- **/actuator/health/liveness**
- **/actuator/health/readiness**

Các endpoint này giúp nền tảng kiểm tra từng mục đích. Không dùng **/actuator/health** tổng thể cho cả liveness và readiness nếu nhóm health có các dependency khác nhau; một lỗi dependency có thể gây restart không cần thiết.

Nếu muốn probe đi qua cổng ứng dụng chính khi management port riêng, có thể cân nhắc **management.endpoint.health.probes.add-additional-paths=true** trên phiên bản Spring Boot hỗ trợ. Kiểm tra đúng phiên bản và xác minh endpoint thực tế trước khi cấu hình probe.

## 6. Thêm health indicator cho dependency quan trọng

Actuator có thể tổng hợp health contributor từ các integration được hỗ trợ. Với dependency riêng, có thể tạo **HealthIndicator**. Chỉ đưa dependency vào readiness nếu dịch vụ không thể thực hiện chức năng cốt lõi khi dependency đó không sẵn sàng.

Ví dụ minh họa:

    package com.example.cloudapi;

    import org.springframework.boot.actuate.health.Health;
    import org.springframework.boot.actuate.health.HealthIndicator;
    import org.springframework.stereotype.Component;

    @Component("storage")
    public class StorageHealthIndicator implements HealthIndicator {
        private final StorageClient storageClient;

        public StorageHealthIndicator(StorageClient storageClient) {
            this.storageClient = storageClient;
        }

        @Override
        public Health health() {
            try {
                storageClient.pingWithTimeout();
                return Health.up().build();
            } catch (Exception ex) {
                return Health.down()
                    .withDetail("dependency", "storage_unavailable")
                    .build();
            }
        }
    }

**StorageClient** là client do ứng dụng cung cấp; phương thức ping cần timeout ngắn, giới hạn retry và không tải dữ liệu lớn. Không đưa exception message, hostname nội bộ, credential hoặc chi tiết cấu hình vào response công khai.

Có thể thêm contributor **storage** vào readiness group:

    management:
      endpoint:
        health:
          group:
            readiness:
              include: readinessState,storage

Tên contributor phụ thuộc tên bean và cấu hình Actuator. Hãy kiểm tra response thực tế sau khi khởi động. Nếu storage chỉ phục vụ một tính năng tùy chọn, không đưa nó vào readiness chung; thay vào đó theo dõi riêng và suy giảm chức năng liên quan.

## 7. Bảo vệ health endpoint

Health endpoint có thể được gọi bởi load balancer hoặc kubelet, nhưng không nên vô tình trở thành kênh công bố thông tin nội bộ.

Các nguyên tắc:

- Chỉ expose **health** qua web khi chưa có nhu cầu rõ ràng cho endpoint khác.
- Đặt **show-details** và **show-components** ở mức không công khai; chỉ hiển thị cho người có quyền nếu thực sự cần.
- Không trả secret, tên host nội bộ, connection string, exception stack hoặc dữ liệu khách hàng.
- Dùng network policy, firewall hoặc management network để giới hạn nguồn truy cập nếu nền tảng hỗ trợ.
- Nếu dùng Spring Security, cấu hình quyền cho health endpoint theo mô hình triển khai: probe nội bộ được phép truy cập, còn chi tiết chỉ dành cho operator được xác thực.
- Không dùng health endpoint thay cho authentication hoặc authorization của API nghiệp vụ.

Một cấu hình security cần giữ quyền truy cập đúng với nền tảng probe. Nếu endpoint yêu cầu đăng nhập nhưng kubelet hoặc load balancer không có credential, mọi probe sẽ thất bại dù ứng dụng đang khỏe. Có thể cho phép truy cập nội bộ vào path health nhưng giới hạn mạng và không trả chi tiết.

## 8. Đóng gói ứng dụng thành container

Sau khi kiểm tra JAR chạy được, tạo Dockerfile nhiều giai đoạn hoặc build JAR trong pipeline. Ví dụ runtime image:

    FROM eclipse-temurin:21-jre
    WORKDIR /app
    COPY target/cloud-api-*.jar app.jar
    USER 10001:10001
    EXPOSE 8080
    ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/app.jar"]

Các điểm cần chú ý:

- Dùng JRE runtime nếu không cần compiler trong image cuối.
- Pin image theo tag/version hoặc digest theo chính sách supply chain của tổ chức.
- Chạy dưới UID không phải root.
- Không copy file cấu hình chứa secret vào image.
- Dùng **.dockerignore** để loại **target** cũ, **.git**, IDE metadata và file không cần thiết khỏi build context.
- Ghi log ra stdout/stderr để nền tảng thu thập.
- Đặt memory request/limit phù hợp với heap và overhead của JVM.

Ví dụ **.dockerignore**:

    .git
    .idea
    .vscode
    *.iml
    .env
    logs/
    target/

Nếu pipeline build JAR trước, bảo đảm **target/cloud-api-*.jar** chỉ khớp một artifact đúng phiên bản. Với dự án nhiều module, dùng đường dẫn và tên artifact rõ ràng thay vì wildcard có thể chọn nhầm JAR.

Build và chạy:

    ./mvnw clean verify
    docker build -t cloud-api:local .
    docker run --rm -p 8080:8080 cloud-api:local

Trên Windows PowerShell, dùng **.\mvnw.cmd clean verify** nếu Maven Wrapper được cung cấp. Sau khi container chạy, gọi **http://localhost:8080/actuator/health** và **/api/hello** từ máy host.

## 9. Cấu hình Kubernetes probe

Kubernetes dùng probe để quyết định khi nào gửi traffic, khi nào restart container và có nên chờ startup hay không. Ví dụ Deployment:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: cloud-api
    spec:
      replicas: 2
      selector:
        matchLabels:
          app: cloud-api
      template:
        metadata:
          labels:
            app: cloud-api
        spec:
          terminationGracePeriodSeconds: 30
          containers:
            - name: cloud-api
              image: registry.example.com/cloud-api:1.0.0
              ports:
                - name: http
                  containerPort: 8080
              env:
                - name: SERVER_PORT
                  value: "8080"
              resources:
                requests:
                  cpu: 250m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              startupProbe:
                httpGet:
                  path: /actuator/health/liveness
                  port: http
                periodSeconds: 10
                timeoutSeconds: 2
                failureThreshold: 30
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

Trong ví dụ:

- Startup probe cho tối đa khoảng 300 giây để ứng dụng khởi động, tính theo chu kỳ và ngưỡng thất bại.
- Liveness probe kiểm tra tiến trình sau khi startup probe thành công.
- Readiness probe kiểm tra khả năng nhận traffic thường xuyên hơn.
- **timeoutSeconds** cần đủ cho health handler phản hồi bình thường nhưng không quá dài.
- **terminationGracePeriodSeconds** cần tương thích với graceful shutdown và thời gian drain request.

Các con số chỉ là điểm khởi đầu. Đo thời gian khởi động và độ trễ health endpoint trong môi trường thực tế. Nếu probe quá nhạy, một đợt GC pause hoặc tải CPU cao có thể làm Pod bị loại khỏi Service hoặc restart liên tục.

Kubernetes không tự động tạo endpoint health cho ứng dụng. Container phải thực sự phục vụ path đã cấu hình, cổng phải khớp và NetworkPolicy không được chặn lưu lượng probe.

## 10. Kiểm chứng từ local đến cluster

### 10.1. Kiểm tra build và khởi động local

Chạy:

    ./mvnw clean verify
    java -jar target/cloud-api-*.jar

Chờ log cho biết ứng dụng đã khởi động và web server đang lắng nghe. Sau đó gọi:

    curl -i http://localhost:8080/api/hello
    curl -i http://localhost:8080/actuator/health
    curl -i http://localhost:8080/actuator/health/liveness
    curl -i http://localhost:8080/actuator/health/readiness

Trên Windows, dùng **curl.exe** để tránh alias PowerShell. Xác nhận endpoint trả HTTP 200 khi ứng dụng khỏe và nội dung health không chứa thông tin nhạy cảm.

### 10.2. Kiểm tra trạng thái không sẵn sàng

Nếu có readiness contributor cho dependency, mô phỏng dependency mất kết nối trong môi trường thử nghiệm. Xác nhận readiness trả trạng thái không khỏe và nền tảng ngừng gửi traffic đến instance đó. Đồng thời xác nhận liveness vẫn khỏe nếu tiến trình còn hoạt động và có thể phục hồi.

Không mô phỏng lỗi bằng cách làm liveness phụ thuộc vào database; điều đó sẽ khiến lỗi database kích hoạt restart loop.

### 10.3. Kiểm tra Kubernetes

Sau khi apply manifest:

    kubectl apply -f deployment.yaml
    kubectl rollout status deployment/cloud-api
    kubectl get pods -l app=cloud-api
    kubectl describe pod <pod-name>
    kubectl logs <pod-name>

Có thể port-forward Service để kiểm tra từ máy quản trị:

    kubectl port-forward service/cloud-api 8080:80
    curl -i http://localhost:8080/actuator/health
    curl -i http://localhost:8080/actuator/health/readiness

Quan sát Pod conditions, restart count và Events. Khi readiness thất bại, Pod có thể vẫn Running nhưng không được đưa vào endpoint phục vụ của Service. Khi liveness thất bại đủ ngưỡng, kubelet restart container. Startup probe bảo vệ giai đoạn khởi động ban đầu.

### 10.4. Kiểm tra shutdown

Gửi SIGTERM hoặc thực hiện rollout trong staging. Xác nhận ứng dụng ngừng nhận request mới, hoàn tất request đang xử lý trong thời gian grace period và container thoát sạch. Nếu ứng dụng bị kill trước khi hoàn tất, kiểm tra sự tương thích giữa:

- **spring.lifecycle.timeout-per-shutdown-phase**
- **terminationGracePeriodSeconds**
- **preStop** hook nếu có
- thời gian drain của load balancer hoặc ingress
- thời gian xử lý request tối đa

## 11. Kiểm thử tự động cho health endpoint

Có thể dùng Spring Boot Test và MockMvc để xác nhận endpoint tồn tại và trả trạng thái hợp lệ.

Ví dụ:

    package com.example.cloudapi;

    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

    import org.junit.jupiter.api.Test;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.test.web.servlet.MockMvc;

    @SpringBootTest
    @AutoConfigureMockMvc
    class HealthEndpointTest {
        @Autowired
        private MockMvc mockMvc;

        @Test
        void healthEndpointReportsUp() throws Exception {
            mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
        }
    }

Nếu test dùng profile hoặc dependency giả lập, điều chỉnh kỳ vọng theo trạng thái tương ứng. Không để test phụ thuộc vào database hoặc dịch vụ cloud thật nếu mục tiêu chỉ là xác nhận endpoint và cấu hình Actuator. Dùng test riêng cho custom HealthIndicator để kiểm tra cả trạng thái UP và DOWN, timeout và dữ liệu trả về.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| **/actuator/health** trả 404 | Thiếu Actuator dependency hoặc endpoint không được expose | Kiểm tra starter, exposure include và path |
| Health trả 503 ngay khi startup | Dependency contributor chưa sẵn sàng hoặc cấu hình readiness quá chặt | Kiểm tra component status và startup sequence |
| Kubernetes báo probe failed | Sai port/path, ứng dụng chưa bind hoặc probe timeout quá ngắn | Kiểm tra kubectl describe pod, log và gọi endpoint trong container |
| Pod liên tục restart | Liveness check thất bại, startup probe thiếu thời gian hoặc JVM OOM | Kiểm tra restart reason, exit code, memory và probe events |
| Pod Running nhưng không nhận traffic | Readiness thất bại hoặc Service selector/port không khớp | Kiểm tra Pod conditions, EndpointSlice và Service |
| Lỗi dependency làm toàn bộ Pod restart | Dependency bị đưa vào liveness | Chuyển dependency phù hợp sang readiness hoặc theo dõi riêng |
| Health endpoint lộ thông tin nội bộ | Bật show-details hoặc expose quá nhiều Actuator endpoint | Giới hạn exposure, details và network access |
| Local chạy được nhưng container không truy cập được | Cổng, bind address, environment hoặc image khác biệt | Kiểm tra SERVER_PORT, log, container port và cấu hình runtime |
| Shutdown bị kill cưỡng bức | Grace period ngắn hơn thời gian drain | Đồng bộ thời gian Spring, Kubernetes và load balancer |

## 13. Checklist trước khi triển khai

- [ ] Chọn JDK và Spring Boot version còn được hỗ trợ, tương thích với dependency của dự án.
- [ ] Có Maven/Gradle wrapper và build tái lập được trong CI.
- [ ] Ứng dụng có lớp main và endpoint nghiệp vụ tối thiểu.
- [ ] Thêm Spring Boot Actuator và chỉ expose endpoint health cần thiết.
- [ ] Cấu hình cổng bằng biến môi trường và có giá trị mặc định phù hợp.
- [ ] Bật liveness/readiness probe; thiết kế startup probe cho ứng dụng khởi động chậm.
- [ ] Liveness chỉ kiểm tra khả năng sống của tiến trình; readiness phản ánh khả năng nhận traffic.
- [ ] Health check có timeout ngắn và không thực hiện truy vấn nặng.
- [ ] Không trả secret hoặc chi tiết nội bộ trong health response.
- [ ] Chạy container bằng user không phải root và không đóng gói secret vào image.
- [ ] Cấu hình Kubernetes probe khớp path, port và thời gian thực tế.
- [ ] Đồng bộ graceful shutdown, load balancer drain và termination grace period.
- [ ] Kiểm thử HTTP 200/503, dependency failure, startup, restart và shutdown.
- [ ] Có log, metric và cảnh báo cho probe failure, restart count và readiness duration.

## Kết luận

Bootstrap ứng dụng Java cho cloud cần tạo được artifact chạy ổn định, nhận cấu hình từ môi trường và công bố tín hiệu sức khỏe có ý nghĩa. Spring Boot Actuator cung cấp health endpoint; liveness cho biết tiến trình có thể tiếp tục chạy, readiness cho biết instance có thể nhận traffic, còn startup probe bảo vệ giai đoạn khởi động. Cấu hình probe đúng, giới hạn thông tin health response và kiểm chứng cả tình huống lỗi lẫn shutdown giúp nền tảng điều phối ứng dụng an toàn trong production.
