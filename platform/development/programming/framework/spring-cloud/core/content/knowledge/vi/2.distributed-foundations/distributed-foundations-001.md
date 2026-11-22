# Dịch vụ, instance và ranh giới triển khai độc lập

> **Chương:** Nền tảng phân tán  
> **Module:** SPRING_CLOUD_CORE

Trong hệ thống phân tán, một *dịch vụ* không đồng nghĩa với một tiến trình đang chạy, và hai tiến trình giống nhau không nhất thiết là hai dịch vụ khác nhau. Phân biệt rõ **service**, **service instance** và **ranh giới triển khai** là điều kiện để thiết kế discovery, cân bằng tải, mở rộng quy mô, cập nhật phiên bản và xử lý lỗi đúng cách.

Spring Cloud Core cung cấp nền tảng để các ứng dụng Spring Boot trao đổi với nhau qua những abstraction chung của **Spring Cloud Commons**, kết hợp **Spring Cloud Context**, cấu hình bên ngoài và các implementation hạ tầng tương ứng. Bài này xây dựng mô hình tư duy trước khi đi sâu vào từng cơ chế.

## 1. Ba khái niệm cần phân biệt

### 1.1. Dịch vụ (service): đơn vị năng lực và hợp đồng

**Dịch vụ** là một thành phần có trách nhiệm nghiệp vụ hoặc kỹ thuật rõ ràng, cung cấp một **hợp đồng tương tác** cho các thành phần khác. Hợp đồng đó có thể là REST API, gRPC API, sự kiện trên message broker hoặc một giao diện nội bộ khác.

Ví dụ hệ thống bán hàng:

- `catalog-service` cung cấp thông tin sản phẩm và hợp đồng như `GET /products/{id}`.
- `order-service` tiếp nhận và quản lý vòng đời đơn hàng.
- `payment-service` xử lý yêu cầu thanh toán và thông báo kết quả.

Tên như `catalog-service` là **định danh logic** của dịch vụ, thường được gọi là *service ID*. Định danh này phải ổn định hơn địa chỉ mạng của một tiến trình cụ thể. Một dịch vụ có thể có một hoặc nhiều instance cùng lúc.

Một dịch vụ có trách nhiệm rõ ràng thường sở hữu API và quy tắc dữ liệu của mình. Tuy nhiên, chỉ có tên riêng hoặc controller riêng **chưa đủ** để khẳng định thành phần có thể triển khai độc lập.

### 1.2. Instance: một bản chạy cụ thể của dịch vụ

**Service instance** là một tiến trình, container hoặc đơn vị chạy cụ thể đang thực thi một dịch vụ. Nhiều instance có thể được tạo từ cùng một bản build:

| Thuộc tính | Instance A | Instance B |
| --- | --- | --- |
| Service ID | `catalog-service` | `catalog-service` |
| Instance ID | `catalog-a` | `catalog-b` |
| Địa chỉ ví dụ | `10.0.2.11:8080` | `10.0.2.12:8080` |
| Phiên bản đang chạy | `v1.8.0` | `v1.8.0` |
| Trạng thái | Ready | Ready |

Các instance chia sẻ **hợp đồng dịch vụ**, nhưng có địa chỉ, vòng đời, lượng request và trạng thái bộ nhớ riêng. Instance A có thể bị dừng rồi được tạo lại ở địa chỉ khác, trong khi service ID vẫn là `catalog-service`.

Những điểm quan trọng:

- **Instance không mặc nhiên đồng bộ bộ nhớ.** Cache nội bộ hoặc biến Java của một instance không tự xuất hiện ở instance khác.
- **Instance ID** là định danh của bản chạy; cách sinh, tính duy nhất và vòng đời của nó phụ thuộc runtime hoặc discovery provider.
- **Replica** thường chỉ một bản chạy bổ sung của cùng workload để tăng khả năng phục vụ; trong ngữ cảnh này, replica là một instance.
- **Địa chỉ instance** có thể là host/port, URI hoặc vị trí được hệ thống định tuyến ánh xạ. Không nên xem IP hiện tại là danh tính lâu dài của dịch vụ.
- Hai instance của một dịch vụ có thể tạm chạy **khác phiên bản** trong quá trình rolling deployment; API cần hỗ trợ giai đoạn này.

### 1.3. Triển khai (deployment): vòng đời của một đơn vị phát hành

Một **đơn vị triển khai** là phần có thể được build, cấu hình, phát hành, mở rộng hoặc quay lui trong môi trường chạy: chẳng hạn một ứng dụng Spring Boot đóng gói thành JAR/container image và một workload quản lý các replica của nó.

Cần phân biệt:

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ |
| --- | --- | --- |
| **Service** | Thành phần cung cấp năng lực và hợp đồng gì? | `catalog-service` |
| **Service ID** | Thành phần khác gọi dịch vụ bằng tên logic nào? | `catalog-service` |
| **Instance** | Bản chạy cụ thể nào đang phục vụ request? | Container `catalog-a` ở `10.0.2.11` |
| **Deployment/release** | Phiên bản nào được đưa lên môi trường, với bao nhiêu bản chạy? | Release `v1.8.0`, 3 replica |
| **Node/host** | Bản chạy đang sử dụng tài nguyên tính toán ở đâu? | Máy ảo, worker node, máy vật lý |
| **Environment** | Cấu hình và điều kiện vận hành thuộc ngữ cảnh nào? | Local, staging, production |

Một deployment có thể quản lý nhiều instance; một service có thể xuất hiện trong nhiều môi trường hoặc nhiều nhóm deployment theo vùng. **Ranh giới dịch vụ, ranh giới mã nguồn và ranh giới hạ tầng không luôn trùng nhau.** Một repository có thể chứa nhiều service; một service có thể được xây dựng từ nhiều module trong cùng repository.

## 2. Từ tên dịch vụ đến địa chỉ instance

Giả sử `order-service` cần lấy giá sản phẩm. Nó nên biểu đạt phụ thuộc vào **dịch vụ danh mục**, thay vì lưu trong nghiệp vụ một IP cố định:

~~~text
Định danh logic: catalog-service
Đường dẫn API:  /products/42

Các instance tại một thời điểm:
  catalog-a -> http://10.0.2.11:8080
  catalog-b -> http://10.0.2.12:8080
  catalog-c -> http://10.0.2.13:8080
~~~

Luồng khái niệm:

~~~mermaid
flowchart LR
    O["order-service\n(consumer)"]
    D["Discovery\nservice ID → instances"]
    L["Load balancer\nchọn instance"]
    A["catalog-a\n10.0.2.11:8080"]
    B["catalog-b\n10.0.2.12:8080"]
    C["catalog-c\n10.0.2.13:8080"]
    O -->|"catalog-service"| L
    L <--> D
    L --> A
    L --> B
    L --> C
~~~

Sơ đồ biểu diễn vai trò logic, **không bắt buộc có một proxy load balancer nằm trên mạng**: với Spring Cloud LoadBalancer, việc chọn instance có thể diễn ra ở phía client. Nếu hạ tầng cung cấp DNS hoặc một virtual IP, cách giải quyết địa chỉ sẽ khác.

Ba việc thường bị nhầm lẫn:

1. **Service registration:** một instance được công bố với cơ chế đăng ký phù hợp, có thông tin nhận diện và định tuyến.
2. **Service discovery:** phía gọi tìm các instance đang được nguồn discovery công bố cho một service ID.
3. **Load balancing:** phía gọi hoặc hạ tầng chọn một instance để phục vụ một request.

Spring Cloud Commons cung cấp các abstraction phổ biến tương ứng:

| Abstraction | Vai trò |
| --- | --- |
| `ServiceInstance` | Mô tả một bản chạy: service ID, host, port, URI, metadata |
| `DiscoveryClient` | Lấy danh sách instance theo service ID qua API đồng bộ |
| `ReactiveDiscoveryClient` | Truy xuất discovery theo mô hình reactive |
| `Registration` và `ServiceRegistry` | Biểu diễn dữ liệu instance và thao tác tích hợp đăng ký dịch vụ |
| `LoadBalancerClient` | Hợp đồng chung cho một số thao tác chọn instance ở luồng đồng bộ |
| Spring Cloud LoadBalancer | Implementation/cơ chế tích hợp cân bằng tải cho các HTTP client phù hợp |

**Commons không tự đóng vai trò registry server.** Các triển khai như Eureka, Consul hoặc tích hợp Kubernetes cung cấp cách lấy thông tin instance theo môi trường cụ thể. `SimpleDiscoveryClient` có thể dùng danh sách tĩnh để phát triển hoặc kiểm thử.

Cần tính đến **độ trễ hội tụ**: instance mới khởi động có thể chưa hiện trong danh sách; instance vừa chết có thể vẫn còn trong cache. Kết quả từ discovery vì vậy là *ảnh chụp tình trạng tại một thời điểm*, không phải cam kết instance chắc chắn xử lý thành công request tiếp theo.

## 3. Thế nào là ranh giới triển khai độc lập?

Một dịch vụ có **ranh giới triển khai độc lập** khi đội ngũ có thể phát hành thay đổi của dịch vụ đó mà không cần bắt buộc build, triển khai hoặc dừng đồng thời mọi dịch vụ liên quan, **với điều kiện hợp đồng và các phụ thuộc còn tương thích**.

Ví dụ `catalog-service` thêm trường thông tin tùy chọn `brand` vào phản hồi. Nếu các consumer chấp nhận trường mới và dữ liệu cũ vẫn hợp lệ, catalog có thể phát hành mà `order-service` không cần phát hành theo. Ngược lại, nếu catalog xóa ngay trường `price` mà order đang đọc, hai đội phải phối hợp thay đổi; ranh giới triển khai chưa bảo đảm được tính độc lập mong muốn.

Các đặc điểm làm nên khả năng triển khai độc lập:

- **Hợp đồng ổn định:** thay đổi API và event theo quy tắc tương thích ngược; consumer và provider có thể chạy khác phiên bản.
- **Quyền sở hữu dữ liệu rõ ràng:** dịch vụ quản lý các bất biến nghiệp vụ và giao diện truy cập dữ liệu của mình; dịch vụ khác không ghi thẳng vào bảng nội bộ của nó.
- **Vòng đời phát hành riêng:** build, kiểm thử, triển khai, mở rộng và rollback từng dịch vụ khi điều kiện cho phép.
- **Cấu hình và tài nguyên rõ ràng:** các giá trị môi trường, quyền truy cập, connection pool và tài nguyên của từng dịch vụ được quản lý minh bạch.
- **Khả năng kiểm soát lỗi:** timeout, giới hạn concurrency, retry có kiểm soát và xử lý mất kết nối không làm lỗi lan rộng vô hạn.
- **Quan sát được:** logs, metrics và traces giúp xác định phiên bản và instance nào gây lỗi.

Độc lập triển khai **không** đồng nghĩa không có phụ thuộc. `order-service` vẫn có thể cần giá từ catalog để tính tiền; điều cần giữ độc lập là **quyết định thay phiên bản, vận hành và triển khai** trong phạm vi hợp đồng đã cam kết.

### 3.1. Một ứng dụng chung và nhiều dịch vụ khác nhau

~~~mermaid
flowchart TB
    subgraph M["Một đơn vị triển khai"]
      MC["catalog module"]
      MO["order module"]
      MP["payment module"]
    end
    subgraph S["Ba đơn vị triển khai"]
      SC["catalog-service"]
      SO["order-service"]
      SP["payment-service"]
    end
    MC --- MO
    MO --- MP
    SO -->|"API/event"| SC
    SO -->|"API/event"| SP
~~~

Ở vế trái, ba module có thể được tách lớp rõ trong mã nhưng cùng vòng đời phát hành. Ở vế phải, mỗi dịch vụ có thể có pipeline, instance và phiên bản riêng. Cách tổ chức thứ hai giúp mở rộng và phát hành riêng từng phần, đổi lại phải xử lý network, dữ liệu phân tán, quan sát và tương thích giữa các phiên bản.

**Tách nhỏ mọi module thành service không tự làm hệ thống tốt hơn.** Khi hai thành phần luôn phải cập nhật đồng thời hoặc cần một transaction nội bộ xuyên suốt, cần xem lại ranh giới nghiệp vụ trước khi quyết định phân tán chúng.

### 3.2. Ranh giới dữ liệu quyết định nhiều đến khả năng tự chủ

Thiết kế dễ gây phụ thuộc chặt:

~~~text
order-service ─┐
               ├── đọc/ghi trực tiếp cùng bảng inventory
stock-service ─┘
~~~

Nếu `order-service` thay trực tiếp bảng của `stock-service`, việc đổi schema hoặc quy tắc giữ hàng có thể làm dịch vụ còn lại hỏng. Chúng có hai tiến trình nhưng chưa có quyền sở hữu dữ liệu độc lập.

Thiết kế với hợp đồng rõ hơn:

~~~text
order-service ── ReserveStock API / event ──> stock-service
                                              |
                                              v
                                       dữ liệu stock do
                                       stock-service quản lý
~~~

Trong mô hình thứ hai, `stock-service` kiểm soát tính hợp lệ của thao tác trừ/giữ tồn kho. `order-service` chỉ biết giao diện công bố, không biết bảng hoặc transaction nội bộ. Trường hợp có nhiều dịch vụ tham gia một quy trình, cần thiết kế trạng thái trung gian, idempotency và cơ chế bù trừ hoặc nhất quán cuối cùng khi phù hợp; **không thể giả định một transaction ACID duy nhất bao trùm mọi request mạng**.

Không nhất thiết mỗi dịch vụ phải có một máy chủ cơ sở dữ liệu vật lý riêng. Điều quan trọng là **quyền sở hữu schema/dữ liệu và đường truy cập** đủ rõ để một dịch vụ không tự ý phá hợp đồng của dịch vụ khác.

## 4. Một dịch vụ có nhiều instance thì hệ thống thay đổi ra sao?

Giả sử `catalog-service` đang có một instance. Khi lượng truy cập tăng, hệ thống tăng lên ba instance từ cùng một image:

| Trạng thái | Số instance | Ý nghĩa |
| --- | ---: | --- |
| Trước khi scale | 1 | Một bản chạy phục vụ yêu cầu |
| Sau khi scale ngang | 3 | Nhiều bản chạy có thể chia sẻ tải |
| Một instance bị lỗi | 2 còn sẵn sàng | Có thể tiếp tục nếu định tuyến phát hiện và bỏ qua instance lỗi |
| Release phiên bản mới | Tạm có cả v1 và v2 | Consumer có thể gặp hai phiên bản trong lúc rolling deployment |

**Scale ngang** tăng số instance. **Scale dọc** tăng tài nguyên CPU/RAM cho một instance. Cả hai không làm thay đổi hợp đồng logic của service, nhưng ảnh hưởng tới hiệu năng, chi phí và vận hành.

Nhiều instance đặt ra các câu hỏi mà ứng dụng một tiến trình ít gặp:

- Nếu session hoặc giỏ hàng chỉ nằm trong RAM của instance A, request tiếp theo chuyển sang B sẽ ra sao? Cần lưu trạng thái ở nơi dùng chung, thiết kế stateless hoặc có chiến lược phù hợp.
- Nếu hai instance cùng xử lý một lệnh, hệ thống chống cập nhật trùng thế nào? Cần khóa, ràng buộc dữ liệu, idempotency hoặc điều phối tùy bài toán.
- Nếu một instance treo nhưng cổng vẫn mở, bộ định tuyến xác định nó đã hết sẵn sàng bằng cách nào? Cần health/readiness phù hợp.
- Nếu các instance khác vùng mạng, độ trễ và chi phí truy cập dữ liệu có thể khác nhau; thuật toán chọn instance cần tính đến yêu cầu triển khai thực tế.

Để đạt khả năng chịu lỗi, replica còn phải tránh chung một điểm lỗi ở nơi có thể: cùng node, cùng vùng hoặc cùng dependency hạ tầng. Ba container trên một máy chủ vẫn có thể cùng bị ảnh hưởng khi máy đó dừng.

## 5. Ví dụ Spring Boot: cùng một service ID, hai instance

Mục tiêu ví dụ: chạy hai instance `inventory-service` và để `order-service` gọi chúng qua **service ID**. Ví dụ dùng địa chỉ tĩnh nhằm làm rõ khái niệm, không cần cài registry server.

### 5.1. Hai bản chạy của `inventory-service`

Ứng dụng inventory có cấu hình:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

Một endpoint minh họa ở inventory:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/stock")
public class StockController {

    @GetMapping("/{sku}")
    public StockResponse getStock(@PathVariable String sku) {
        return new StockResponse(sku, 12); // Dữ liệu giả cho ví dụ
    }

    public record StockResponse(String sku, int available) {}
}
~~~

Nếu ứng dụng có dependency Web phù hợp, sau khi build thành `inventory-service.jar`, có thể khởi chạy **hai tiến trình riêng** trên cùng máy ở hai cổng:

~~~bash
java -jar inventory-service.jar --server.port=8081
java -jar inventory-service.jar --server.port=8082
~~~

Cả hai cùng có `spring.application.name=inventory-service`. Tên này xác định ứng dụng ở phía Spring Boot nhưng **không tự biến nó thành dịch vụ có discovery động**: phía gọi vẫn cần nguồn danh sách instance hoặc cơ chế định tuyến phù hợp.

### 5.2. Định nghĩa nguồn instance cho `order-service`

Đặt cấu hình dưới đây trong ứng dụng order:

~~~yaml
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
~~~

`SimpleDiscoveryClient` đọc danh sách tĩnh từ cấu hình. Trong môi trường thực, `localhost` của một container chỉ trỏ về **chính container đó**; nếu các dịch vụ chạy ở container/node khác nhau, phải dùng địa chỉ có thể truy cập từ phía order.

Ứng dụng order cần HTTP client phù hợp và Spring Cloud LoadBalancer, ví dụ `spring-boot-starter-webflux` (để dùng `WebClient`) cùng `spring-cloud-starter-loadbalancer`. Sử dụng **Spring Cloud BOM/release train tương thích với Spring Boot** để quản lý phiên bản dependency. Với registry thật, bổ sung integration tương ứng.

### 5.3. Gọi theo service ID qua `@LoadBalanced`

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryHttpClientConfig {
    @Bean
    @LoadBalanced
    WebClient.Builder inventoryWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryGateway {
    private final WebClient client;

    public InventoryGateway(@LoadBalanced WebClient.Builder builder) {
        this.client = builder.build();
    }

    public Mono<StockResponse> stockOf(String sku) {
        return client.get()
                .uri("http://inventory-service/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }

    public record StockResponse(String sku, int available) {}
}
~~~

Khi gọi `stockOf("SKU-42")`, địa chỉ `inventory-service` là **service ID**, được cơ chế load balancing giải quyết thành một trong những instance đã cấu hình. Request thực tế tới `localhost:8081` hoặc `localhost:8082`; không cần sửa `InventoryGateway` khi thay nguồn instance.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant Order as order-service
    participant LB as Spring Cloud LoadBalancer
    participant Discovery as DiscoveryClient
    participant Inventory as inventory-service instance
    Order->>LB: GET http://inventory-service/stock/SKU-42
    LB->>Discovery: Tìm instance inventory-service
    Discovery-->>LB: 8081, 8082
    LB->>Inventory: Chọn instance, gửi GET /stock/SKU-42
    Inventory-->>Order: StockResponse (qua HTTP client)
~~~

**Giới hạn ví dụ:** Hai bản chạy cùng trả dữ liệu giả `available=12`. Nếu dữ liệu thật chỉ lưu trong RAM riêng, các instance có thể trả kết quả khác nhau. Danh sách static không tự cập nhật khi instance bị hủy hoặc scale; không nên dùng ví dụ này để suy ra discovery động hoặc khả năng chịu lỗi của production.

## 6. Vòng đời instance và trạng thái sẵn sàng

Một instance có thể **đang chạy** nhưng chưa **sẵn sàng nhận lưu lượng**. Ví dụ: JVM đã mở cổng HTTP nhưng ứng dụng còn khởi tạo cache, migration hoặc kết nối cần thiết.

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: Khởi tạo xong
    Ready --> Draining: Bắt đầu dừng/rolling update
    Draining --> Stopped: Kết thúc request còn lại
    Ready --> Unhealthy: Phát sinh lỗi
    Unhealthy --> Ready: Phục hồi
    Unhealthy --> Stopped: Bị dừng/thay thế
    Stopped --> [*]
~~~

Cần phân biệt hai loại kiểm tra phổ biến:

| Kiểm tra | Trả lời câu hỏi | Hành động thường gặp |
| --- | --- | --- |
| **Liveness** | Tiến trình còn hoạt động theo tiêu chí cần thiết không? | Runtime có thể khởi động lại khi tiến trình bị kẹt |
| **Readiness** | Instance đã sẵn sàng xử lý request mới chưa? | Ngừng đưa lưu lượng mới tới instance chưa sẵn sàng |

Với Spring Boot Actuator ở phiên bản hỗ trợ health probes, có thể cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các endpoint thường dùng gồm `/actuator/health/liveness` và `/actuator/health/readiness` khi đã có Actuator và cấu hình thích hợp. Chính sách định tuyến phụ thuộc runtime, integration và probe thực tế. **Không nên đặt mọi lỗi dependency từ xa vào liveness**: một database tạm lỗi có thể khiến toàn bộ replica bị khởi động lại đồng loạt, làm sự cố nặng hơn.

Khi ngừng instance, quy trình an toàn thường là chuyển khỏi trạng thái nhận request mới, giảm/thoát lưu lượng đang xử lý, hoàn tất hoặc hủy có kiểm soát công việc còn lại, rồi dừng tiến trình. Thời điểm hủy đăng ký, cập nhật readiness, chờ drain và thời gian hội tụ discovery khác nhau theo môi trường; không thể mặc định mọi request sẽ ngừng tới instance ngay lập tức.

## 7. Hợp đồng tương thích cho phép triển khai độc lập

Trong rolling deployment, instance cũ và mới có thể cùng tồn tại. Thậm chí, consumer và provider có thể được phát hành bởi hai nhóm ở hai thời điểm khác nhau. Vì vậy, ranh giới triển khai độc lập luôn gắn với **tương thích giữa các phiên bản**.

Giả sử ban đầu `catalog-service` trả:

~~~json
{
  "id": "P-42",
  "name": "Bàn phím",
  "price": 350000
}
~~~

Phiên bản mới bổ sung trường:

~~~json
{
  "id": "P-42",
  "name": "Bàn phím",
  "price": 350000,
  "brand": "Example"
}
~~~

Đây **có thể** là thay đổi tương thích nếu consumer cũ bỏ qua thuộc tính không biết và semantic cũ vẫn giữ nguyên. Ngược lại, đổi `price` từ số sang chuỗi hoặc xóa `id` có thể làm client cũ hỏng.

| Thay đổi dự kiến | Rủi ro tương thích | Cách triển khai gợi ý |
| --- | --- | --- |
| Thêm trường tùy chọn ở response | Thường thấp khi client bỏ qua unknown fields | Kiểm thử consumer cũ; giữ semantics đã công bố |
| Đổi tên/xóa trường đang dùng | Cao | Giữ trường cũ giai đoạn chuyển tiếp hoặc tạo API version mới |
| Đổi ý nghĩa của `price` | Cao dù schema không đổi | Định nghĩa lại hợp đồng và phiên bản hóa khi cần |
| Thêm cột nullable vào DB do service sở hữu | Thường có thể triển khai dần | Mở rộng schema trước rồi triển khai code sử dụng |
| Đổi tên/xóa cột mà bản chạy cũ còn đọc | Cao trong rolling deploy | Mẫu *expand → migrate → contract* |
| Thay cấu trúc event đang có consumer | Có thể ảnh hưởng nhiều dịch vụ | Quản lý schema/version và kiểm thử khả năng đọc |
| Tăng số replica mà không đổi API | Thường ít ảnh hưởng hợp đồng | Xem xét trạng thái chia sẻ, concurrency và capacity của dependency |

Đối với database, **expand → migrate → contract** nghĩa là: thêm cấu trúc mới theo cách bản cũ vẫn hoạt động, chuyển đổi dữ liệu và ứng dụng theo giai đoạn, chỉ xóa cấu trúc cũ sau khi chắc chắn không còn consumer. Đối với API, nên áp dụng contract tests và kiểm thử liên phiên bản, đặc biệt khi deployment không diễn ra đồng thời.

Một số trường hợp thật sự đòi hỏi phối hợp phát hành, ví dụ thay đổi bảo mật buộc mọi client cập nhật. Khi đó cần nêu rõ giai đoạn chuyển tiếp và quyền rollback; không nên tuyên bố độc lập triển khai tuyệt đối.

## 8. Lỗi phân tán và ranh giới chịu lỗi

Khi `order-service` gọi `inventory-service` qua HTTP, xuất hiện những trạng thái mà lời gọi trong cùng process không có:

1. Request có thể **không tới** instance đích.
2. Instance có thể xử lý thành công nhưng **response mất trên đường về**.
3. Instance có thể trả lỗi có chủ đích, hết thời gian chờ hoặc bị hủy trong lúc triển khai.
4. Discovery có thể trả địa chỉ đã cũ; danh sách instance rỗng cũng có thể chỉ là trạng thái tạm thời.

Điều này ảnh hưởng trực tiếp đến nghiệp vụ. Giả sử order gọi API **giữ tồn kho** và timeout: không thể suy ra chắc chắn tồn kho đã được giữ hay chưa. Retry mù quáng có thể giữ hàng hai lần. Một giải pháp thường dùng là **idempotency key** cho thao tác có tác động, đồng thời đặt timeout và retry có giới hạn theo nghiệp vụ.

| Cơ chế | Giải quyết vấn đề | Lưu ý |
| --- | --- | --- |
| Timeout | Tránh chờ vô hạn khi dependency không đáp ứng | Chọn ngưỡng theo SLO và tổng ngân sách thời gian |
| Retry/backoff | Thử lại lỗi tạm thời | Chỉ retry khi an toàn; hạn chế số lần để tránh khuếch đại tải |
| Circuit breaker | Ngừng gửi nhiều request tới dependency đang lỗi | Cần chính sách trạng thái và phục hồi phù hợp |
| Bulkhead/giới hạn concurrency | Giảm khả năng một phụ thuộc dùng hết tài nguyên | Không thay thế kiểm soát capacity |
| Readiness/health | Tránh gửi lưu lượng tới bản chạy chưa sẵn sàng | Độ chính xác tùy probe và cập nhật của hệ thống điều phối |
| Tracing/metrics | Nhìn thấy lỗi giữa các service và instance | Gắn service ID, instance, phiên bản, trace ID |

Spring Cloud Commons giúp mã ứng dụng dùng các hợp đồng chung liên quan đến instance, discovery và load balancing; **nó không tự cung cấp toàn bộ chính sách timeout, retry, circuit breaker hoặc nhất quán dữ liệu**. Các tính năng này cần công cụ và cấu hình phù hợp ở tầng HTTP, resilience, message broker và lưu trữ.

## 9. Vai trò của cấu hình bên ngoài, Context và tương thích phiên bản

Trong module SPRING_CLOUD_CORE, ranh giới service/instance liên hệ trực tiếp tới ba nhóm nền tảng khác:

### 9.1. Externalized configuration của Spring Boot

Giữa staging và production, **cùng một artifact** có thể dùng URL, secret, timeout, cổng, giới hạn pool hoặc tên namespace khác nhau. Các giá trị này nên nằm trong nguồn cấu hình phù hợp thay vì hard-code theo địa chỉ từng instance.

`spring.application.name` biểu đạt tên ứng dụng; service ID mà hệ thống discovery sử dụng có thể được suy ra từ tên này hoặc do integration cấu hình riêng. Khi sử dụng một registry, kiểm tra tài liệu của implementation để biết cách đặt tên, đăng ký và định danh instance.

### 9.2. Spring Cloud Context và refresh

`@RefreshScope` và cơ chế refresh thuộc Spring Cloud Context có thể giúp cập nhật một số bean/cấu hình khi ứng dụng đang chạy, tùy cách kích hoạt và nguồn cấu hình. **Refresh cấu hình không tương đương triển khai phiên bản mã mới.** Thay JAR/image vẫn cần phát hành và quản lý vòng đời instance.

Thêm hoặc xóa instance là thay đổi **topology của runtime**; người gọi thường quan sát thông qua discovery/load balancer. Thay một tham số `timeout` là thay đổi **cấu hình client** và còn phụ thuộc bean/client có được cập nhật đúng cách không.

### 9.3. Spring Cloud và Spring Boot phải tương thích

Khi xây dựng mỗi dịch vụ, cần chọn **Spring Cloud release train/BOM** tương thích với Spring Boot trong chính dịch vụ đó. Việc hai service chạy khác phiên bản Boot hoặc Cloud là có thể nếu chúng tương tác qua hợp đồng mạng tương thích; tuy nhiên, **trong từng service**, dependency và auto-configuration vẫn phải là tổ hợp được hỗ trợ.

Không tự sao chép giả định về API hoặc starter từ một release train cũ sang bản mới. Cần kiểm tra bản tương thích chính thức khi nâng cấp và thử lại đường đi của discovery, HTTP client, load balancing, refresh và health.

## 10. Kiểm thử và vận hành theo ba tầng

### 10.1. Kiểm thử tầng dịch vụ

Kiểm tra hợp đồng API/event, quy tắc nghiệp vụ và quyền sở hữu dữ liệu. Với interface `DiscoveryClient`, có thể mock danh sách `ServiceInstance` để xác minh logic tiêu thụ mà không dựng registry thật.

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class InventoryDiscoveryTest {

    @Test
    void findsTwoInstancesOfTheSameService() {
        DiscoveryClient client = mock(DiscoveryClient.class);
        when(client.getInstances("inventory-service")).thenReturn(List.of(
            new DefaultServiceInstance("inv-1", "inventory-service", "localhost", 8081, false),
            new DefaultServiceInstance("inv-2", "inventory-service", "localhost", 8082, false)
        ));

        assertThat(client.getInstances("inventory-service"))
                .extracting(instance -> instance.getServiceId())
                .containsExactly("inventory-service", "inventory-service");
    }
}
~~~

Ví dụ giả định có JUnit 5, Mockito và AssertJ trong dependency kiểm thử. Bài kiểm tra này chỉ xác nhận **hai bản chạy cùng service ID** được mô phỏng ở tầng discovery, không xác nhận request đã được phân tải. Kiểm thử load balancing cần chạy cả tầng HTTP hoặc kiểm tra cơ chế chọn instance tương ứng.

### 10.2. Kiểm thử tầng instance

Khởi chạy ít nhất hai instance ở hai cổng hoặc container khác nhau, sau đó dừng một bản chạy và quan sát. Kỳ vọng phải được xác định rõ: hệ thống có tiếp tục đáp ứng, mất bao lâu để tránh instance lỗi, bao nhiêu request bị lỗi trong thời gian chuyển tiếp và cơ chế retry có hoạt động an toàn không.

Ngoài trạng thái success, cần thử trường hợp **instance xử lý xong nhưng client timeout** để phát hiện lặp thao tác có tác động.

### 10.3. Kiểm thử ranh giới triển khai

Trong môi trường gần production:

1. Giữ `order-service` ở phiên bản cũ, triển khai `catalog-service` phiên bản mới và chạy contract tests.
2. Tạo thời gian có cả instance catalog cũ và mới, xem response/schema có tương thích không.
3. Thử rollback catalog khi order đang chạy; kiểm tra schema DB có còn tương thích.
4. Tăng/giảm replica và xem health, metrics, latency, khả năng xử lý lưu lượng.
5. Gây lỗi cho một instance hoặc một dependency; kiểm tra mức lan truyền và khả năng phục hồi.

Khi điều tra lỗi, nên ghi nhận **service ID, instance ID, phiên bản ứng dụng, environment, trace/correlation ID** và URI đích ở mức log phù hợp. Chỉ nhìn tên service thường không đủ để biết lỗi đến từ replica nào.

## 11. Các câu hỏi thiết kế thường gặp

**Một service có thể chỉ có một instance không?** Có. Service là đơn vị logic; việc có bao nhiêu instance là quyết định triển khai. Một instance có thể đủ ở môi trường local hoặc tải thấp, nhưng là một điểm lỗi đơn lẻ ở production nếu không có phương án phục hồi.

**Hai instance chạy khác phiên bản có còn cùng một service không?** Có thể, nếu chúng cùng phục vụ một hợp đồng logic tương thích trong thời gian chuyển tiếp. Nếu semantics hoặc dữ liệu không tương thích, cần thiết kế versioning hoặc phân luồng phù hợp.

**Có phải cứ dùng container hoặc Kubernetes là có microservices?** Không. Container là cơ chế đóng gói/chạy; microservices phụ thuộc ranh giới nghiệp vụ, hợp đồng và quyền tự chủ phát hành. Một hệ thống nhiều container vẫn có thể phải triển khai đồng loạt vì phụ thuộc chặt.

**Spring Cloud có tạo ranh giới nghiệp vụ thay mình không?** Không. Spring Cloud giúp triển khai discovery, cấu hình, kết nối và các abstraction cần thiết. Việc tách service, sở hữu dữ liệu và thiết kế tương thích thuộc quyết định kiến trúc.

**Khi nào không nên tách thành dịch vụ riêng?** Khi chi phí mạng, kiểm thử tích hợp, nhất quán dữ liệu và vận hành lớn hơn lợi ích của phát hành/mở rộng riêng; đặc biệt khi hai thành phần luôn thay đổi cùng nhau và chưa xác định được hợp đồng ổn định.

## 12. Bài tập vận dụng

Một hệ thống có `checkout-service`, `inventory-service` và `payment-service`. Inventory đang có hai instance; checkout chỉ biết URI của instance đầu tiên. Đội inventory muốn tăng lên bốn replica và phát hành API trả thêm trường `warehouseId`.

Hãy trả lời:

1. Trong mô hình này, có **bao nhiêu service** và **bao nhiêu instance inventory** trước và sau khi scale?
2. Checkout cần thay đổi gì để gọi theo **service ID** và không phụ thuộc một IP cố định?
3. Điều kiện nào khiến việc thêm `warehouseId` là thay đổi tương thích ngược?
4. Nếu checkout timeout khi gọi API giữ hàng, vì sao không thể retry vô điều kiện?
5. Những bằng chứng kiểm thử và quan sát nào cho phép inventory phát hành độc lập mà checkout vẫn chạy?

**Gợi ý tự kiểm tra:** số instance không làm tăng số service logic; discovery đưa ra danh sách, load balancer chọn một instance; hợp đồng cần hỗ trợ consumer cũ; thao tác có tác động cần idempotency; và rolling deployment phải hoạt động được trong giai đoạn đồng thời tồn tại hai phiên bản.

**Điểm ghi nhớ:** **Service** thể hiện trách nhiệm và hợp đồng; **instance** là một bản chạy có địa chỉ và vòng đời riêng; **ranh giới triển khai độc lập** là khả năng phát hành, mở rộng và phục hồi từng service trong điều kiện các hợp đồng vẫn tương thích. Spring Cloud Commons và các integration của Spring Cloud giúp nối định danh logic với instance thực tế, còn sự độc lập vận hành phụ thuộc vào cách thiết kế API, dữ liệu và quy trình triển khai.
