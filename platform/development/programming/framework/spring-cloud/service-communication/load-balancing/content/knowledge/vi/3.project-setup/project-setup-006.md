# Cấu hình tên dịch vụ, cổng và định danh từng bản sao

Trong module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`, project cần mô tả rõ dịch vụ nào đang chạy, mỗi tiến trình lắng nghe ở đâu và từng bản sao được nhận diện như thế nào. Ba thông tin này giúp Spring Cloud LoadBalancer tìm đúng nhóm instance theo service ID, sau đó chọn một instance cụ thể để gửi request.

Bài thực hành dùng `order-service` gọi `inventory-service`. Ta chạy nhiều bản sao của `inventory-service` cùng tên dịch vụ nhưng có định danh instance riêng. Khi hoàn thành, bạn có thể cấu hình một ứng dụng chạy ở nhiều cổng trên máy phát triển hoặc nhiều container/pod trong môi trường triển khai, đồng thời xác minh registry phân biệt được từng bản sao.

## Phân biệt service name, port và instance ID

Ba giá trị này có vai trò khác nhau và không nên gộp làm một:

| Thuộc tính | Ví dụ | Ý nghĩa | Quy tắc khi chạy nhiều bản sao |
|---|---|---|---|
| `spring.application.name` | `inventory-service` | Tên logic của ứng dụng; thường được dùng làm service ID trong discovery và URI của client | Giữ giống nhau giữa các bản sao của cùng một dịch vụ |
| `server.port` | `8081`, `8082` | Cổng HTTP mà tiến trình Spring Boot lắng nghe | Trên cùng một máy, mỗi tiến trình cần một cổng chưa được sử dụng; trong các container riêng, chúng có thể cùng dùng cổng nội bộ |
| Instance ID | `inventory-8081`, `inventory-8082` | Định danh duy nhất cho một bản sao trong registry hoặc log | Mỗi bản sao phải có giá trị riêng trong phạm vi registry |
| Host hoặc địa chỉ mạng | `localhost`, IP container hoặc hostname của pod | Địa chỉ mà client thực sự kết nối sau khi LoadBalancer chọn instance | Phải truy cập được từ mạng của dịch vụ gọi |

Ví dụ, registry có thể lưu hai bản ghi cùng service ID `inventory-service`:

| Service ID | Instance ID | Địa chỉ đăng ký |
|---|---|---|
| `inventory-service` | `inventory-8081` | `http://localhost:8081` |
| `inventory-service` | `inventory-8082` | `http://localhost:8082` |

Khi `order-service` gọi `http://inventory-service/api/inventory/SKU-01`, phần `inventory-service` là tên logic. LoadBalancer lấy danh sách các instance thuộc service ID đó, chọn một bản sao, rồi gửi request đến địa chỉ đã đăng ký. Vì vậy, không đặt tên ứng dụng thành `inventory-service-1` và `inventory-service-2` nếu hai tiến trình thực chất là bản sao của cùng một dịch vụ; làm vậy sẽ tạo ra hai service ID riêng và không còn một nhóm instance để cân bằng tải.

## Chuẩn bị dependency và project

Tạo project Spring Boot cho `inventory-service` và `order-service`. Hai ứng dụng có thể nằm trong hai module Maven hoặc hai project riêng. Dùng Spring Cloud BOM tương thích với phiên bản Spring Boot của project để quản lý phiên bản thư viện.

Ví dụ khai báo release train trong `pom.xml`:

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_VERSION</spring-cloud.version>
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
```

Thay `YOUR_COMPATIBLE_SPRING_CLOUD_VERSION` bằng release train tương thích với Spring Boot đang dùng. Không sao chép một số phiên bản tùy ý từ project khác vì Spring Boot và Spring Cloud có ma trận tương thích riêng.

Trong `order-service`, thêm LoadBalancer và starter discovery tương ứng với registry bạn chọn. Ví dụ nếu dùng Eureka:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Trong `inventory-service`, thêm starter discovery client nếu dịch vụ cần tự đăng ký vào registry. Với Eureka, dùng `spring-cloud-starter-netflix-eureka-client`; nếu dùng Consul hoặc Kubernetes thì thay bằng starter tương ứng. `spring-cloud-starter-loadbalancer` là thành phần chọn instance phía client; nó không tự tạo ra registry và cũng không thay thế discovery provider.

## Đặt tên logic cho từng ứng dụng

Trong `inventory-service/src/main/resources/application.yml`, khai báo tên dịch vụ một lần:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: ${SERVER_PORT:8081}

app:
  instance-id: ${INSTANCE_ID:${spring.application.name}:${server.port}}
```

`spring.application.name` là tên logic chung cho mọi bản sao. `SERVER_PORT` là biến môi trường để thay đổi cổng khi khởi chạy. `app.instance-id` là thuộc tính ứng dụng do project định nghĩa để lưu định danh riêng; nếu không truyền `INSTANCE_ID`, ví dụ dùng tên dịch vụ ghép với cổng làm giá trị mặc định. Cách mặc định này phù hợp cho lab chạy nhiều tiến trình trên cùng máy với các cổng khác nhau.

Trong `order-service`, dùng tên riêng và cổng riêng:

```yaml
spring:
  application:
    name: order-service

server:
  port: ${SERVER_PORT:8080}
```

Tên `order-service` giúp registry và log phân biệt ứng dụng gọi với ứng dụng đích. Khi gọi inventory, client vẫn sử dụng service ID `inventory-service`, không dùng tên của instance hoặc cổng của một bản sao cụ thể.

## Cấu hình địa chỉ và định danh cho discovery

`app.instance-id` là giá trị dùng chung trong ví dụ để bạn không phải gắn logic nghiệp vụ với một discovery provider cụ thể. Khi đăng ký dịch vụ, ánh xạ nó sang thuộc tính instance ID mà provider hỗ trợ.

### Nếu sử dụng Eureka

Trong `inventory-service` và `order-service`, cấu hình địa chỉ Eureka server. Ví dụ sau giả định registry chạy trên máy phát triển tại cổng `8761`:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_URL:http://localhost:8761/eureka/}
  instance:
    instance-id: ${app.instance-id}
    prefer-ip-address: true
```

`eureka.instance.instance-id` giúp mỗi bản sao có định danh dễ đọc trong Eureka. `prefer-ip-address` yêu cầu instance quảng bá IP thay vì hostname; chỉ bật khi IP được quảng bá có thể truy cập từ các dịch vụ khác. Trong Docker hoặc Kubernetes, địa chỉ đăng ký phải có ý nghĩa trong mạng container/cluster, không được trỏ về `localhost` của một container nếu client nằm ở container khác.

Đối với lab chạy hai tiến trình trên cùng máy, có thể khởi động lần lượt với `INSTANCE_ID=inventory-8081` và `INSTANCE_ID=inventory-8082`. Cả hai tiến trình vẫn dùng `spring.application.name=inventory-service`.

### Nếu sử dụng Consul

Với Consul, ánh xạ định danh vào cấu hình discovery của Consul:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        service-name: ${spring.application.name}
        instance-id: ${app.instance-id}
```

`service-name` gom các bản sao vào cùng một dịch vụ; `instance-id` phân biệt từng bản sao trong Consul. Nếu project đang dùng một provider khác, hãy tra thuộc tính đăng ký instance của provider đó và ánh xạ cùng `app.instance-id`; không cấu hình đồng thời Eureka và Consul chỉ để thử một bài lab đơn giản.

### Nếu chỉ muốn thử với danh sách tĩnh

Để kiểm tra LoadBalancer trước khi dựng registry, có thể dùng `SimpleDiscoveryClient` với danh sách URI tĩnh trong `order-service`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082

server:
  port: 8080
```

Danh sách này giúp client có hai địa chỉ để chọn mà không cần dựng registry. Nó không tự đăng ký hoặc kiểm tra vòng đời tiến trình `inventory-service`; khi dừng một instance, bạn phải cập nhật danh sách cấu hình hoặc chuyển sang discovery provider có khả năng cập nhật instance. Dùng cách này cho bước khởi động lab, sau đó thực hành với registry để hiểu quá trình đăng ký và loại bỏ instance.

## Khởi chạy nhiều bản sao trên máy phát triển

Giả sử đã build `inventory-service.jar`. Mở hai terminal và khởi động hai tiến trình với cùng artifact, cùng tên dịch vụ nhưng khác cổng và instance ID.

Terminal thứ nhất trên Bash:

```bash
SERVER_PORT=8081 INSTANCE_ID=inventory-8081 java -jar inventory-service.jar
```

Terminal thứ hai trên Bash:

```bash
SERVER_PORT=8082 INSTANCE_ID=inventory-8082 java -jar inventory-service.jar
```

Trên PowerShell, đặt biến môi trường trong từng terminal trước khi chạy:

```powershell
$env:SERVER_PORT = "8081"
$env:INSTANCE_ID = "inventory-8081"
java -jar .\inventory-service.jar
```

Ở terminal còn lại, đổi hai giá trị thành `8082` và `inventory-8082`. Các biến môi trường chỉ áp dụng cho tiến trình được khởi chạy từ terminal tương ứng. Nếu chạy qua IDE, tạo hai Run Configuration với cùng main class và artifact nhưng giá trị environment khác nhau.

Khi chạy trong container hoặc Kubernetes, các replica thường có thể dùng cùng cổng nội bộ, ví dụ `8080`, vì mỗi container/pod có network namespace riêng. Khi đó, địa chỉ host hoặc pod IP phân biệt endpoint; hãy đặt `INSTANCE_ID` theo tên pod, UID hoặc giá trị duy nhất do nền tảng cấp. Không dùng tên dịch vụ cộng với cổng nội bộ làm instance ID nếu mọi replica đều có cùng cổng và registry yêu cầu ID duy nhất.

## Trả về instance ID để kiểm chứng

Trong lab, hãy làm cho mỗi bản sao trả về định danh của chính nó. Cách đơn giản là thêm endpoint chỉ dùng cho kiểm tra:

```java
@RestController
class InstanceInfoController {

    private final String serviceId;
    private final String instanceId;
    private final int port;

    InstanceInfoController(
            @Value("${spring.application.name}") String serviceId,
            @Value("${app.instance-id}") String instanceId,
            @Value("${server.port}") int port) {
        this.serviceId = serviceId;
        this.instanceId = instanceId;
        this.port = port;
    }

    @GetMapping("/internal/instance")
    Map<String, Object> instance() {
        return Map.of(
                "serviceId", serviceId,
                "instanceId", instanceId,
                "port", port);
    }
}
```

Khi truy cập trực tiếp `http://localhost:8081/internal/instance`, kết quả cần có `instanceId` là `inventory-8081`; cổng `8082` phải trả về `inventory-8082`. Endpoint này phục vụ lab và quan sát. Trong hệ thống thật, cân nhắc giới hạn truy cập endpoint nội bộ và tránh công khai thông tin hạ tầng không cần thiết.

## Kết nối từ order-service bằng service ID

Sau khi discovery có hai instance, cấu hình một client có LoadBalancer trong `order-service`:

```java
@Configuration
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

```java
@Service
class InventoryClient {
    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    Map<?, ?> getInstanceInfo() {
        return restClient.get()
                .uri("http://inventory-service/internal/instance")
                .retrieve()
                .body(Map.class);
    }
}
```

Điểm quan trọng là URI dùng `inventory-service`. LoadBalancer dùng service ID này để lấy các ứng viên từ discovery rồi chọn một địa chỉ. Nếu thay URI thành `http://localhost:8081`, request sẽ gọi thẳng một bản sao và không còn kiểm chứng được cơ chế cân bằng tải.

## Xác minh cấu hình theo từng bước

Thực hiện các bước sau trước khi chuyển sang bài về chính sách chọn instance:

1. Khởi động registry nếu project sử dụng Eureka, Consul hoặc provider khác.
2. Khởi động hai bản sao `inventory-service` với cùng `spring.application.name`, hai `INSTANCE_ID` khác nhau và địa chỉ truy cập hợp lệ.
3. Truy cập endpoint `/internal/instance` trực tiếp trên từng cổng để xác nhận từng tiến trình trả đúng ID.
4. Mở giao diện hoặc API của registry và kiểm tra có hai instance cùng thuộc service ID `inventory-service`.
5. Khởi động `order-service`, kiểm tra nó có thể lấy danh sách instance và gọi URI chứa service ID.
6. Gửi nhiều request đến endpoint thông qua `order-service`; ghi lại `instanceId` trong response để thấy các bản sao được chọn.
7. Dừng một bản sao, chờ registry và client cập nhật danh sách theo chu kỳ cấu hình, rồi gửi request tiếp. Xác minh request được phục vụ bởi instance còn khả dụng.

Kết quả mong đợi của bước cấu hình ban đầu:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Tên dịch vụ của hai bản sao | Đều là `inventory-service` |
| Cổng khi chạy hai tiến trình trên cùng máy | Khác nhau, ví dụ `8081` và `8082` |
| Instance ID | Duy nhất, ví dụ `inventory-8081` và `inventory-8082` |
| Registry | Hiển thị hai instance trong cùng service ID |
| URI từ order-service | Dùng `http://inventory-service/...` |
| Địa chỉ đăng ký | Có thể truy cập từ mạng của order-service |

## Lỗi cấu hình thường gặp

- **Đặt tên ứng dụng khác nhau giữa các replica:** registry tạo hai service ID khác nhau; LoadBalancer gọi một service ID sẽ không nhìn thấy nhóm bản sao còn lại.
- **Trùng instance ID:** registry có thể ghi đè, từ chối hoặc hiển thị không chính xác các bản ghi. Tạo ID duy nhất cho từng tiến trình.
- **Trùng cổng trên cùng một máy:** tiến trình thứ hai không bind được socket và thường dừng ngay khi khởi động. Đổi `SERVER_PORT` hoặc chạy trong network namespace riêng.
- **Đăng ký `localhost` trong container:** `localhost` của container là chính container đó, không phải container khác. Dùng DNS service, hostname hoặc IP có thể truy cập từ caller.
- **Nhầm instance ID với service ID:** instance ID phân biệt một bản sao; client vẫn gọi bằng service ID chung.
- **Chỉ cấu hình LoadBalancer mà thiếu discovery:** LoadBalancer không tự biết địa chỉ các bản sao. Cần discovery provider hoặc danh sách tĩnh cho lab.
- **Dùng cùng một ID mặc định cho mọi pod:** trong môi trường container, hãy cấp ID từ tên pod hoặc UID thay vì chỉ ghép service name với cổng nội bộ.
- **Thay đổi cấu hình nhưng không khởi động lại tiến trình:** biến môi trường và `application.yml` được nạp khi ứng dụng khởi động; kiểm tra lại log cấu hình và registry sau khi restart.

## Tiêu chí hoàn thành

Bạn hoàn thành bài này khi có thể chứng minh rằng hai bản sao `inventory-service` dùng cùng service ID, lắng nghe tại endpoint hợp lệ và có instance ID riêng; registry hoặc danh sách discovery hiển thị được cả hai; `order-service` gọi qua service ID thay vì địa chỉ cố định; và bạn giải thích được cách cấu hình thay đổi giữa chạy nhiều tiến trình trên một máy với triển khai nhiều container/pod.

Những cấu hình này là nền tảng cho các bài tiếp theo về chọn `ServiceInstance`, health check, retry, timeout và định tuyến. Nếu service name, địa chỉ đăng ký hoặc instance identity sai, việc phân phối request và điều tra lỗi ở các bước sau sẽ khó chính xác.
