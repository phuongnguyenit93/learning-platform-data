# Lan truyền thay đổi bằng Bus tới một dịch vụ hoặc một instance

Spring Cloud Bus cho phép phát một sự kiện refresh qua broker và giới hạn sự kiện tới đúng một instance hoặc một nhóm instance. Bài thực hành này dựng một Config Server và hai bản chạy của cùng ứng dụng order-service. Sau khi đổi cấu hình trong Git, ta sẽ refresh đúng instance A để chứng minh instance B chưa đổi; sau đó phát một sự kiện nhắm toàn bộ order-service để cả hai instance cùng nhận phiên bản mới.

Điểm cần quan sát là **destination của Bus**. Một lệnh refresh không có destination sẽ phát rộng tới các ứng dụng tham gia Bus. Destination chính xác có thể nhắm một Bus ID; destination dạng pattern có thể nhắm mọi instance của một service. Các instance vẫn xử lý sự kiện độc lập và bất đồng bộ.

## 1. Kết quả cần đạt

Sau bài lab, người học có thể:

- Kết nối Config Server và nhiều Config Client vào cùng một Spring Cloud Bus.
- Dùng RabbitMQ làm broker cho bài thực hành.
- Chạy hai instance có cùng application name nhưng Bus ID khác nhau.
- Thay đổi một property trong Git và xác minh Config Server đã nhìn thấy commit mới.
- Gọi endpoint Bus refresh với destination chính xác để cập nhật một instance.
- Gọi endpoint Bus refresh với wildcard để cập nhật mọi instance của một dịch vụ.
- Phân biệt refresh cục bộ, refresh có destination và broadcast toàn Bus.
- Xác minh instance nào đã áp dụng release mới và chẩn đoán lỗi định tuyến.

~~~mermaid
flowchart TD
    G[(Git config repository)] --> S[Config Server]
    S <--> B[(RabbitMQ)]
    B <--> A[order-service A<br/>port 8081]
    B <--> C[order-service B<br/>port 8082]
    S -->|Config Data request| A
    S -->|Config Data request| C
    S -->|busrefresh destination| B
~~~

Trong bài lab, Config Server là nơi phát sự kiện. Cả hai client có cùng application name là order-service, nhưng mỗi tiến trình có một Bus ID riêng.

## 2. Chuẩn bị phiên bản và dependency

Chọn một cặp Spring Boot và Spring Cloud release train tương thích theo bảng tương thích chính thức. Dùng Spring Cloud BOM để quản lý version của Config và Bus; không tự ghép các phiên bản starter khác release train.

Config Server cần các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bus-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Mỗi Config Client cần:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bus-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Import Spring Cloud BOM trong phần dependency management của cả hai project:

~~~xml
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

Giá trị spring-cloud.version phải thuộc release train tương thích với Spring Boot đang dùng. Bài lab không yêu cầu một version cố định; giữ cùng BOM ở Config Server và Config Client để tránh lệch protocol hoặc dependency.

## 3. Khởi chạy RabbitMQ

Tạo file docker-compose.yml trong thư mục lab:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:3-management
    container_name: config-bus-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: configlab
      RABBITMQ_DEFAULT_PASS: configlab-local-only
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 5s
      timeout: 5s
      retries: 12
~~~

Khởi chạy:

~~~bash
docker compose up -d
docker compose ps
~~~

RabbitMQ management UI của lab có thể truy cập tại http://localhost:15672. Tài khoản trong ví dụ chỉ dùng cho máy local; không dùng mật khẩu này ở staging hoặc production. Nếu không dùng Docker, có thể trỏ các ứng dụng tới một RabbitMQ broker đã được cấp riêng cho môi trường thử nghiệm.

## 4. Dựng Git repository cấu hình

Tạo working repository và bare repository riêng. Config Server sẽ clone/fetch từ bare repository; ta cập nhật working tree rồi push commit mới lên remote.

~~~bash
mkdir -p /tmp/spring-cloud-bus-lab/config-work
cd /tmp/spring-cloud-bus-lab/config-work
git init -b main
git config user.name "Config Bus Lab"
git config user.email "config-bus-lab@example.invalid"
~~~

Tạo file order-service.yml:

~~~yaml
demo:
  message: "Hello from configuration release v1"
  release: "v1"
~~~

Commit lần đầu và tạo bare remote:

~~~bash
git add order-service.yml
git commit -m "Add order service configuration v1"
git init --bare ../config-repo.git
git remote add origin ../config-repo.git
git push -u origin main
~~~

Kiểm tra branch và remote:

~~~bash
git log --oneline --decorate
git --git-dir=../config-repo.git show-ref
~~~

Trong bài lab, repository chỉ chứa dữ liệu không nhạy cảm. Không commit API key, password hoặc secret thật.

## 5. Cấu hình Config Server

Class khởi động Config Server:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Ví dụ application.yml:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    bus:
      id: "config-server:${server.port}:lab-origin"
    config:
      server:
        git:
          uri: "file:///tmp/spring-cloud-bus-lab/config-repo.git"
          default-label: main
          clone-on-start: true
          refresh-rate: 0
  rabbitmq:
    host: localhost
    port: 5672
    username: configlab
    password: configlab-local-only

management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Trên Windows, đổi Git URI thành dạng file:///C:/spring-cloud-bus-lab/config-repo.git. URI dùng dấu gạch chéo xuôi. Thay đường dẫn theo nơi đặt repository lab thực tế.

Các thiết lập quan trọng:

- **git.uri**: bare repository mà Config Server đọc.
- **default-label**: branch mặc định của bài lab là main.
- **clone-on-start**: clone repository khi server khởi động để phát hiện lỗi sớm.
- **refresh-rate: 0**: cho phép Git backend fetch theo từng request; phù hợp lab để quan sát commit mới ngay.
- **spring.cloud.bus.id**: định danh riêng cho Config Server; nó không trùng với ID của hai client.
- **busrefresh exposure**: mở write endpoint để Config Server phát sự kiện refresh có destination.

Sự kiện refresh từ Config Server chỉ được truyền qua Bus khi Spring Cloud Bus được kích hoạt ở cả Config Server và các client. Tất cả tiến trình trong bài lab phải kết nối cùng RabbitMQ broker và virtual host. Endpoint busrefresh là write operation có thể làm thay đổi runtime của nhiều ứng dụng; chỉ expose nó trên mạng quản trị và bảo vệ bằng authorization trong môi trường dùng chung.

Khởi động Config Server và kiểm tra:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8888/order-service/default/main
~~~

Response Environment cần có property source chứa demo.message và demo.release với giá trị v1. Nếu request không thành công, sửa Git URI hoặc branch trước khi khởi động các client.

## 6. Cấu hình hai instance của cùng một Config Client

Hai tiến trình sẽ cùng dùng application name order-service. Điểm khác nhau là port và INSTANCE_ID. Đặt Bus ID tường minh giúp ta biết chính xác destination cần gọi.

Ví dụ application.yml của order-service:

~~~yaml
server:
  port: ${SERVER_PORT:8081}

spring:
  application:
    name: order-service
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: main
    bus:
      id: "${spring.application.name}:${server.port}:${INSTANCE_ID:local}"
  rabbitmq:
    host: localhost
    port: 5672
    username: configlab
    password: configlab-local-only

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Config Data import ở trên là bắt buộc. Nếu Config Server không sẵn sàng khi client khởi động, client sẽ không khởi động thành công. Đây là lựa chọn phù hợp cho lab vì Config Server là nguồn cấu hình bắt buộc.

Không đặt demo.message hoặc demo.release trong application.yml cục bộ của client. Các key này phải đến từ Git Config Server để có thể quan sát việc refresh.

### 6.1. Đăng ký configuration properties

Tạo class ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

Tạo bean mutable để Spring Cloud Context có thể rebind sau refresh:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public class DemoProperties {

    private String message;
    private String release;

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public String getRelease() {
        return release;
    }

    public void setRelease(String release) {
        this.release = release;
    }
}
~~~

Tạo endpoint đọc một số giá trị không nhạy cảm:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoConfigController {

    private final DemoProperties properties;

    @Value("${INSTANCE_ID:unknown}")
    private String instanceId;

    @Value("${spring.cloud.bus.id}")
    private String busId;

    public DemoConfigController(DemoProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/demo/config")
    public Map<String, String> config() {
        return Map.of(
            "instanceId", instanceId,
            "busId", busId,
            "message", properties.getMessage(),
            "release", properties.getRelease()
        );
    }
}
~~~

Endpoint này chỉ trả release marker và thông điệp giả của lab. Không tạo endpoint trả toàn bộ Environment hoặc secret để debug refresh.

## 7. Chạy hai instance với Bus ID khác nhau

Mở hai terminal tại project order-service. Chạy mỗi instance với port và instance ID riêng.

Terminal A:

~~~bash
INSTANCE_ID=node-a SERVER_PORT=8081 ./mvnw spring-boot:run
~~~

Terminal B:

~~~bash
INSTANCE_ID=node-b SERVER_PORT=8082 ./mvnw spring-boot:run
~~~

Trên Windows PowerShell, đặt biến môi trường trong từng cửa sổ riêng:

~~~powershell
$env:INSTANCE_ID = "node-a"
$env:SERVER_PORT = "8081"
.\mvnw.cmd spring-boot:run
~~~

Ở cửa sổ PowerShell thứ hai, dùng node-b và 8082. Nếu dùng IDE, cấu hình hai Run Configuration với environment variables khác nhau.

Hai instance phải có:

| Thuộc tính | Instance A | Instance B |
|---|---|---|
| spring.application.name | order-service | order-service |
| server.port | 8081 | 8082 |
| INSTANCE_ID | node-a | node-b |
| spring.cloud.bus.id | order-service:8081:node-a | order-service:8082:node-b |
| Git label | main | main |

Bus ID là định danh định tuyến của một instance. Mỗi instance phải có ID duy nhất. Nếu hai tiến trình dùng cùng Bus ID, cơ chế loại sự kiện do chính instance phát có thể khiến sự kiện bị bỏ qua hoặc định tuyến sai.

## 8. Xác minh trạng thái ban đầu

Gọi endpoint đọc cấu hình của cả hai instance:

~~~bash
curl --fail --silent --show-error http://localhost:8081/demo/config
curl --fail --silent --show-error http://localhost:8082/demo/config
~~~

Kết quả mong đợi:

| Instance | Bus ID | demo.release | demo.message |
|---|---|---|---|
| A | order-service:8081:node-a | v1 | Hello from configuration release v1 |
| B | order-service:8082:node-b | v1 | Hello from configuration release v1 |

Nếu một instance không khởi động hoặc không có các key demo, kiểm tra Config Data import và Config Server trước. Chưa gửi Bus event khi trạng thái ban đầu chưa nhất quán.

## 9. Thay đổi cấu hình trong Git

Trong working tree config-work, đổi order-service.yml sang release v2:

~~~yaml
demo:
  message: "Hello from configuration release v2"
  release: "v2"
~~~

Commit và push:

~~~bash
git add order-service.yml
git commit -m "Publish order service configuration v2"
git push origin main
~~~

Kiểm tra Config Server đã nhìn thấy release mới:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8888/order-service/default/main
~~~

Trong Environment response, xác nhận property source chứa demo.release là v2 và demo.message tương ứng. Chỉ tiếp tục khi Config Server đã phục vụ đúng snapshot.

Lúc này, hai client vẫn có thể đang hiển thị v1 vì chưa có refresh event. Gọi lại:

~~~bash
curl --fail --silent --show-error http://localhost:8081/demo/config
curl --fail --silent --show-error http://localhost:8082/demo/config
~~~

Kết quả trước refresh phải vẫn là v1 ở cả A và B. Điều này giúp tách rõ thay đổi ở Git/Config Server khỏi thay đổi runtime tại client.

## 10. Refresh đúng một instance

Config Server đã có Bus starter và endpoint busrefresh được expose. Gửi POST với destination là Bus ID đầy đủ của instance A:

~~~bash
curl --include --request POST \
  http://localhost:8888/actuator/busrefresh/order-service:8081:node-a
~~~

Destination là một **path segment**, không phải query parameter. Endpoint có dạng:

~~~text
POST /actuator/busrefresh/{destination}
~~~

Với ID đã cấu hình, chỉ instance có Bus ID khớp order-service:8081:node-a xử lý refresh event. Các instance khác nhận thông điệp Bus nhưng không xử lý event dành cho node A.

Chờ event được broker phân phối rồi gọi lại hai endpoint:

~~~bash
curl --fail --silent --show-error http://localhost:8081/demo/config
curl --fail --silent --show-error http://localhost:8082/demo/config
~~~

Kết quả mong đợi:

| Instance | Release trước | Release sau | Kết quả |
|---|---|---|---|
| A: node-a | v1 | v2 | Đã refresh |
| B: node-b | v1 | v1 | Không nhận refresh dành cho A |

Muốn chỉ instance B refresh, đổi destination thành Bus ID của B:

~~~bash
curl --include --request POST --url 'http://localhost:8888/actuator/busrefresh/order-service:8082:node-b'
~~~

Sau khi event được xử lý, B chuyển từ v1 sang v2; A vẫn ở v2 vì đã được refresh ở bước trước.

Đây là nhánh kiểm thử tùy chọn để xác nhận có thể nhắm B. Nếu muốn theo đúng luồng chính của phần tiếp theo, bỏ qua lệnh này để B tiếp tục ở v1.

Đây là phép thử chính của bài lab. Nếu cả hai cùng lên v2, hãy kiểm tra destination có bị bỏ trống hoặc dùng wildcard không. Nếu không instance nào đổi, kiểm tra Bus broker, Bus ID và log nhận event.

## 11. Refresh tất cả instance của một dịch vụ

Tiếp theo, đổi Git sang release v3:

~~~yaml
demo:
  message: "Hello from configuration release v3"
  release: "v3"
~~~

Commit và push:

git add order-service.yml
git commit -m "Publish order service configuration v3"
git push origin main
~~~

Xác minh Config Server trả v3 trước khi phát sự kiện. Sau đó gửi Bus refresh tới pattern khớp mọi instance có ID bắt đầu bằng order-service:

~~~bash
curl --include --request POST \
  'http://localhost:8888/actuator/busrefresh/order-service:**'
~~~

Spring Cloud Bus dùng PathMatcher với dấu phân cách là dấu hai chấm. Pattern order-service:** nhắm mọi instance của service order-service, bất kể phần ID cụ thể phía sau.

Kết quả mong đợi sau khi event được xử lý:

| Instance | Release trước | Release sau |
|---|---|---|
| A: node-a | v2 | v3 |
| B: node-b | v1 (hoặc v2 nếu đã chạy phép thử riêng cho B) | v3 |

Có thể so sánh với broadcast không có destination:

~~~bash
curl --include --request POST \
  http://localhost:8888/actuator/busrefresh
~~~

Lệnh không có destination phát refresh tới các ứng dụng tham gia Bus, bao gồm các service khác và Config Server nếu chúng có tham gia Bus. Trong production, ưu tiên destination hẹp nhất đáp ứng mục tiêu để giảm refresh không cần thiết.

## 12. Phân biệt ba kiểu refresh

| Cách gọi | Phạm vi | Khi sử dụng |
|---|---|---|
| POST /actuator/refresh | Chỉ tiến trình nhận HTTP request | Thử refresh cục bộ hoặc vận hành một instance trực tiếp |
| POST /actuator/busrefresh/{destination} | Instance hoặc nhóm instance khớp destination | Cập nhật có chọn lọc |
| POST /actuator/busrefresh | Tất cả ứng dụng tham gia Bus | Thay đổi cấu hình dùng chung hoặc refresh toàn fleet có chủ đích |

Endpoint busrefresh thực hiện cơ chế refresh ở các node nhận sự kiện: làm mới cache RefreshScope và rebind các bean ConfigurationProperties. Bus không gửi một bản Environment snapshot cố định để mọi node áp dụng cùng lúc; từng client gọi Config Server để lấy cấu hình của mình.

## 13. Cách xác định Bus ID khi không đặt tường minh

Nếu không cấu hình spring.cloud.bus.id, Bus tạo ID từ môi trường. ID mặc định có dạng app:index:id:

- app là vcap.application.name nếu có, nếu không là spring.application.name.
- index lần lượt được lấy từ vcap.application.instance_index, spring.application.index, local.server.port, server.port hoặc 0.
- id được lấy từ vcap.application.instance_id nếu có; nếu không, Bus tạo một giá trị ngẫu nhiên.

Vì phần cuối có thể thay đổi giữa các lần chạy, không nên đoán ID từ application name và port rồi gửi destination thiếu phần còn lại nếu cần nhắm một tiến trình chính xác. Hãy đọc log startup hoặc cấu hình một spring.cloud.bus.id tường minh cho mỗi instance.

Trong môi trường container/orchestrator, có thể dùng pod name hoặc instance UID làm phần cuối của ID. Đảm bảo giá trị duy nhất trong phạm vi Bus.

## 14. Theo dõi sự kiện và xác nhận hoàn tất

Bus truyền sự kiện bất đồng bộ. HTTP response của endpoint busrefresh chỉ xác nhận request phát sự kiện đã được tiếp nhận ở phía gửi; nó không phải acknowledgement rằng mọi client đích đã refresh thành công.

Trong bài lab, dùng release marker để kiểm chứng:

1. Config Server Environment response đã là release mới.
2. Instance đích trả release mới ở endpoint demo/config.
3. Instance không thuộc destination vẫn giữ release cũ trong bài test targeted.
4. Với service-wide target, tất cả instance order-service đều trả release mới.
5. Log client thể hiện nhận và xử lý refresh event.

Trong hệ thống thật, có thể xuất metric hoặc health detail chỉ chứa config release ID, label/commit metadata và thời điểm refresh gần nhất. Không expose toàn bộ Environment hoặc secret để phục vụ quan sát.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Endpoint busrefresh trả 404 | Chưa thêm Bus starter, actuator hoặc chưa expose endpoint | Kiểm tra dependency và management exposure trên Config Server |
| Endpoint trả 401/403 | Security policy chặn write operation | Cấp quyền vận hành đúng phạm vi; không mở endpoint công khai |
| Cả A và B cùng refresh khi nhắm A | Destination bị bỏ trống, pattern quá rộng hoặc ID bị trùng | Kiểm tra path destination và Bus ID thực tế của từng node |
| Không node nào refresh | Config Server hoặc client chưa tham gia cùng broker | Kiểm tra bus starter, RabbitMQ connection và queue binding |
| A không refresh nhưng B refresh | Destination nhầm ID hoặc hai instance cấu hình ID sai | So sánh ID trong log và endpoint demo/config |
| Cả hai nhận event nhưng giá trị vẫn v1 | Config Server chưa fetch commit mới hoặc client dùng label khác | Kiểm tra Environment endpoint, Git ref và spring.cloud.config.label |
| Chỉ một phần service-wide instances lên v3 | Instance offline, broker lỗi hoặc event chưa xử lý | Kiểm tra từng node, broker và retry/restart có kiểm soát |
| Refresh thành công nhưng bean không đổi | Bean không được rebind hoặc đang giữ state đã khởi tạo | Dùng ConfigurationProperties mutable, RefreshScope khi phù hợp hoặc restart bean/tài nguyên |
| Event bị bỏ qua dù destination đúng | Bus ID trùng với ID của sender hoặc ID không duy nhất | Dùng ID riêng cho từng instance và sender |
| Local refresh hoạt động nhưng Bus refresh không hoạt động | Actuator refresh có nhưng Bus không kết nối broker | Kiểm tra Bus starter và broker ở cả server/client |

## 16. Checklist hoàn thành

- [ ] Spring Boot và Spring Cloud BOM tương thích.
- [ ] RabbitMQ đã sẵn sàng và Config Server kết nối được.
- [ ] Git bare repository có branch main và file order-service.yml.
- [ ] Config Server đọc đúng Git repository và label main.
- [ ] Config Server có Bus starter và expose busrefresh.
- [ ] Hai Config Client cùng application name order-service.
- [ ] Hai instance có Bus ID khác nhau, xác định được.
- [ ] Cả hai instance ban đầu trả release v1.
- [ ] Git commit v2 đã được Config Server nhìn thấy.
- [ ] Refresh targeted cập nhật A lên v2, B vẫn v1.
- [ ] Git commit v3 đã được Config Server nhìn thấy.
- [ ] Destination order-service:** cập nhật cả A và B lên v3.
- [ ] Đã phân biệt targeted refresh với broadcast không destination.
- [ ] Đã xác minh log và release marker thay vì chỉ dựa vào HTTP response.
- [ ] Đã dừng các tiến trình và RabbitMQ sau bài lab.

## 17. Dọn dẹp môi trường

Dừng hai Config Client và Config Server. Sau đó dừng RabbitMQ:

~~~bash
docker compose down
~~~

Chỉ xóa thư mục spring-cloud-bus-lab nếu chắc chắn đó là thư mục tạo riêng cho bài thực hành. Không chạy lệnh xóa trên repository cấu hình dùng chung hoặc thư mục làm việc khác.

## 18. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Dựng Config Server và nhiều Config Client cùng tham gia Spring Cloud Bus.
- Cấu hình broker RabbitMQ và định danh Bus ID riêng cho từng instance.
- Dùng POST /actuator/busrefresh/{destination} để nhắm một instance.
- Dùng wildcard destination để nhắm mọi instance của một service.
- Giải thích khác biệt giữa local refresh, targeted Bus refresh và broadcast refresh.
- Xác minh Config Server đã có cấu hình mới trước khi gửi sự kiện.
- Kiểm tra kết quả từng node bằng release marker và log.
- Chẩn đoán lỗi destination, Bus ID trùng, broker, security và stale configuration.

**Tự kiểm tra:** Hai instance order-service có Bus ID order-service:8081:node-a và order-service:8082:node-b. Sau khi Git chuyển từ v1 sang v2, hãy viết lệnh POST để chỉ node-b refresh và mô tả giá trị dự kiến của A/B. Tiếp theo, hãy viết destination để cả hai instance refresh nhưng không tác động service inventory-service. Giải thích vì sao HTTP response thành công từ Config Server chưa chứng minh cả hai node đã áp dụng release mới.

## Tài liệu tham khảo

- [Spring Cloud Bus — Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
- [Spring Cloud Bus — Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html)
- [Spring Cloud Config — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/server/push-notifications-and-bus.html)
- [Spring Cloud Commons — Application Context Services and Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
