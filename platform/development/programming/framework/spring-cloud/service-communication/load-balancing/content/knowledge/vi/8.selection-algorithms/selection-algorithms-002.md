# Random: chọn ngẫu nhiên và phân bố trong nhiều yêu cầu

Trong **Spring Cloud LoadBalancer**, client gọi một dịch vụ qua *service ID* như `inventory-service` và cần chọn một `ServiceInstance` cụ thể để gửi HTTP request. Spring Cloud cung cấp hai thuật toán lựa chọn cơ bản: **Round Robin** (mặc định) và **Random**. Random chọn một ứng viên ngẫu nhiên từ danh sách instance được cung cấp ở thời điểm chọn, nên một instance có thể được chọn nhiều lần liên tiếp; phân bố tương đối đều chỉ là kỳ vọng thống kê khi số lần chọn đủ lớn và điều kiện ổn định.

Bài học này tập trung vào ý nghĩa của `RandomLoadBalancer`, xác suất chọn từng bản sao, cách phân bố được quan sát qua nhiều request và cách bật Random riêng cho một service ID. Phần cuối trình bày một mô hình thực hành với RestClient, cách đo số lượt request, các ảnh hưởng của discovery/health check/retry và những điều cần tránh khi vận hành.

## 1. Random giải quyết điều gì?

Giả sử hệ thống có một ứng dụng `order-service` cần gọi `inventory-service`. Discovery trả về ba bản sao:

| Service ID | Instance ID | Địa chỉ |
|---|---|---|
| `inventory-service` | `inventory-1` | `http://localhost:8081` |
| `inventory-service` | `inventory-2` | `http://localhost:8082` |
| `inventory-service` | `inventory-3` | `http://localhost:8083` |

Caller không cần biết trước instance nào sẽ phục vụ request. Khi dùng HTTP client được tích hợp LoadBalancer, caller gọi URL logic:

~~~text
http://inventory-service/api/items/SKU-001
~~~

Spring Cloud LoadBalancer nhận service ID `inventory-service`, truy vấn danh sách `ServiceInstance` phù hợp, rồi chọn một ứng viên. Với Random, mỗi lần lựa chọn hợp lệ, bộ chọn ngẫu nhiên lấy một vị trí trong danh sách ứng viên.

~~~mermaid
flowchart LR
    A["Order service"] -->|"http://inventory-service"| B["Spring Cloud LoadBalancer"]
    S["Discovery / ServiceInstanceListSupplier"] -->|"[inventory-1, inventory-2, inventory-3]"| B
    B --> R["RandomLoadBalancer"]
    R -->|"chọn một instance"| C["HTTP transport"]
    C --> D["inventory-1 :8081"]
    C --> E["inventory-2 :8082"]
    C --> F["inventory-3 :8083"]
~~~

Sơ đồ thể hiện các đích có thể được chọn, không ngụ ý một HTTP request được gửi đến cả ba. Thông thường, một lần chọn trả về **một** `ServiceInstance` cho lần gửi request đó. Retry, nếu được cấu hình, có thể khiến nghiệp vụ phát sinh thêm lần chọn/gửi về sau.

## 2. Cơ chế chọn một instance ngẫu nhiên

Có thể hình dung cách chọn như sau:

~~~java
List<ServiceInstance> candidates = supplier.getInstances(serviceId);

if (candidates.isEmpty()) {
    // Không tìm được instance phù hợp: trả kết quả rỗng/lỗi phù hợp.
} else {
    int index = ThreadLocalRandom.current().nextInt(candidates.size());
    ServiceInstance selected = candidates.get(index);
    // HTTP client sẽ dùng host, port và scheme của selected.
}
~~~

Đây là **mã giả minh họa thuật toán**, không phải mã thay thế trực tiếp cho API reactive của Spring Cloud. Lớp thực tế `RandomLoadBalancer` nhận danh sách từ `ServiceInstanceListSupplier` và trả kết quả lựa chọn qua API của LoadBalancer.

Các trường hợp biên:

- **Danh sách rỗng:** không có instance để chọn. LoadBalancer trả kết quả không có server, và HTTP integration có thể báo lỗi/response như 503 tùy client, adapter và chính sách xử lý lỗi.
- **Danh sách có một instance:** Random luôn chọn instance đó; không thể tạo phân phối đa bản sao.
- **Danh sách có nhiều instance:** chọn một vị trí ngẫu nhiên trong tập ứng viên tại thời điểm đó.
- **Danh sách thay đổi:** lần chọn tiếp theo có thể dùng danh sách mới sau khi discovery và các tầng cache/supplier cập nhật.

Random không cần duy trì con trỏ vòng như Round Robin. Nó cũng không tự theo dõi số kết nối, độ trễ, CPU hay lịch sử số request của từng replica để cân bằng theo tải.

## 3. Xác suất khi danh sách ổn định

Giả sử danh sách gồm `n` instance **phân biệt, mỗi instance xuất hiện một lần** và được chọn đồng đều. Khi ấy xác suất chọn một instance ở một lần chọn là:

\[
P(\text{chọn instance } i)=\frac{1}{n}
\]

| Số instance khả dụng | Xác suất chọn từng instance trong một lượt |
|---:|---:|
| 1 | 100% |
| 2 | 50% |
| 3 | Khoảng 33,33% |
| 4 | 25% |
| 5 | 20% |

Với ba instance `A`, `B`, `C`, một chuỗi kết quả hoàn toàn hợp lệ là:

~~~text
Request:     1  2  3  4  5  6  7  8  9 10 11 12
Selected:    B  B  A  C  C  B  B  B  A  C  A  B
~~~

`B` được chọn nhiều lần liên tiếp là điều bình thường. Random **không có quy tắc** “đã chọn B thì lượt sau không được chọn B”. Nếu tập ứng viên và phân phối xác suất không đổi, xác suất lượt tiếp theo lại chọn B vẫn là `1/3`, bất kể các lượt trước đã chọn ai.

Cần phân biệt hai phát biểu:

1. **Đúng:** mỗi instance có cơ hội như nhau ở một lượt chọn khi danh sách đầu vào gồm các ứng viên phân biệt và không có trọng số.
2. **Sai:** sau ba request, ba instance chắc chắn mỗi nơi nhận đúng một request.

Thuật toán Random không cam kết một mức phân phối chính xác trong từng cửa sổ ngắn.

## 4. Phân bố trên nhiều request: kỳ vọng và dao động

Giả sử có `N` lần chọn độc lập, danh sách giữ nguyên và xác suất của một instance là `p = 1/n`. Số lượt instance đó được chọn là biến ngẫu nhiên nhị thức:

\[
X_i \sim \operatorname{Binomial}(N,p)
\]

Kỳ vọng và độ lệch chuẩn:

\[
E[X_i]=Np=\frac{N}{n}
\]

\[
\sigma_i=\sqrt{Np(1-p)}
\]

Ví dụ có ba instance, gửi 3.000 request mà **mỗi request tạo đúng một lần chọn**:

- Mỗi instance có kỳ vọng nhận 1.000 lượt.
- Độ lệch chuẩn của số lượt một instance được chọn là khoảng 25,8.
- Dưới giả định mô hình nhị thức, một khoảng xấp xỉ 95% **cho riêng một instance** là khoảng 949–1.051 lượt (kỳ vọng ±1,96 độ lệch chuẩn).

Điều đó không có nghĩa tổng số lượt cả ba instance đều nằm trong khoảng này với xác suất đúng 95%; các bộ đếm liên quan nhau vì tổng luôn bằng 3.000. Đây cũng không phải mức giới hạn mà hệ thống bảo đảm.

Khi số request tăng, **tỷ lệ** thường tiến gần `1/n`, nhưng **chênh lệch tuyệt đối** giữa các bộ đếm vẫn có thể tăng theo quy mô gần bậc căn của `N`. Ví dụ, 10.000 request không bắt buộc trả đúng 5.000/5.000 ở hệ thống hai instance.

Có thể quan sát các trường hợp:

| Số request | Hai instance, số lượt kỳ vọng mỗi bên | Điều cần hiểu |
|---:|---:|---|
| 10 | 5 | 7–3 hoặc 8–2 vẫn có thể xảy ra |
| 100 | 50 | Chênh vài đến hơn mười lượt có thể gặp |
| 1.000 | 500 | Tỷ lệ thường ổn định hơn so với mẫu 10 |
| 10.000 | 5.000 | Mức lệch theo tỷ lệ thường nhỏ, vẫn không bảo đảm chính xác |

Nếu đánh giá Random chỉ bằng 5–10 request, rất dễ nhầm sự dao động tự nhiên với cấu hình lỗi. Cần quan sát số lượt đủ lớn, đồng thời xác nhận danh sách instance ổn định.

## 5. Random và Round Robin khác nhau thế nào?

Mặc định, Spring Cloud LoadBalancer thường dùng `RoundRobinLoadBalancer`. Có thể đổi sang `RandomLoadBalancer` qua cấu hình riêng của client.

| Tiêu chí | Round Robin | Random |
|---|---|---|
| Cách chọn | Di chuyển qua danh sách theo chỉ số vòng | Chọn một chỉ số ngẫu nhiên trong danh sách |
| Trạng thái lựa chọn | Có vị trí/đếm để xác định lượt kế | Không cần con trỏ vòng giữa các lượt |
| 3 lần chọn đầu, 3 instance ổn định | Thường gặp mỗi instance một lượt nếu chuỗi bắt đầu ở vị trí tương ứng | Có thể cả ba lần đều trúng một instance |
| Cân bằng trong cửa sổ ngắn | Thường đều hơn nếu thứ tự/list ổn định | Có thể lệch đáng kể |
| Khi nhiều request | Phân phối tương đối đều theo số lượt | Phân phối đều theo kỳ vọng thống kê |
| Sự cố/tải thực tế | Không tự biết độ trễ hay CPU từ tên thuật toán | Không tự biết độ trễ hay CPU từ tên thuật toán |
| Phù hợp | Muốn luân phiên dễ dự đoán | Muốn lựa chọn đơn giản, phân tán không tuần tự |

Không nên xem một thuật toán là luôn tốt hơn. Nếu mục tiêu là phân phối gần đều **theo số request trong cửa sổ ngắn**, Round Robin thường dễ quan sát. Nếu chấp nhận dao động và muốn không phụ thuộc thứ tự vòng, Random là lựa chọn hợp lý.

Cả hai đều không đồng nghĩa với **least connections**, **least response time**, **weighted**, **consistent hashing** hay **sticky session**. Muốn tính đến năng lực khác nhau giữa replica, cần thiết kế chuỗi supplier/chiến lược phù hợp.

## 6. Random nằm ở đâu trong chuỗi supplier?

Random chỉ lựa chọn trên tập ứng viên mà `ServiceInstanceListSupplier` trả về. Trước bước Random, danh sách có thể đã chịu ảnh hưởng bởi discovery, cache, health check, zone preference hoặc hint.

~~~mermaid
flowchart LR
    D["DiscoveryClient"] --> C["Cache danh sách (nếu bật)"]
    C --> H["Health / zone / hint filtering (nếu cấu hình)"]
    H --> L["Danh sách ứng viên hiệu lực"]
    L --> R["RandomLoadBalancer"]
    R --> I["ServiceInstance được chọn"]
    I --> T["RestClient / WebClient / OpenFeign"]
~~~

Ví dụ ban đầu discovery thấy:

~~~text
[A, B, C, D]
~~~

Nếu zone preference chỉ còn `[A, C]`, Random chọn đều giữa A và C chứ không chọn cả bốn. Nếu health check loại C và danh sách còn `[A]`, mọi lượt chọn đều đi A. Nếu bộ lọc không tìm được ứng viên phù hợp rồi fallback về tập gốc, hành vi lại phụ thuộc quy tắc fallback của supplier đó.

**Không nên đồng nhất danh sách đăng ký với danh sách đủ điều kiện lựa chọn.** Khi thấy số request phân bố không đều, hãy kiểm tra tập instance mà LoadBalancer thực sự nhận, cùng các bộ lọc trước khi kết luận Random sai.

Cũng cần lưu ý: tính đồng đều `1/n` áp dụng cho **các phần tử trong danh sách đầu vào**. Nếu một supplier có chủ ý trả lại nhiều bản sao của cùng một instance hoặc áp dụng trọng số, xác suất theo *instance logic* có thể thay đổi. Đó là hiệu ứng của supplier, không phải vì Random tự đọc CPU hay metadata.

## 7. Bật Random riêng cho một service ID

Cấu hình mặc định thường là Round Robin. Không có thuộc tính chuẩn chung dạng `spring.cloud.loadbalancer.strategy=random` tự động đổi thuật toán cho mọi service. Cách được tài liệu Spring Cloud hướng dẫn là đăng ký một `ReactorLoadBalancer<ServiceInstance>` riêng qua `@LoadBalancerClient`.

Giả sử ứng dụng caller có package gốc `com.example.caller`. Đặt cấu hình Random ở package **ngoài phạm vi component scan của caller**, ví dụ `com.example.lbconfig`.

Lớp ứng dụng chính:

~~~java
package com.example.caller;

import com.example.lbconfig.InventoryRandomLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryRandomLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Cấu hình Random theo client ID:

~~~java
package com.example.lbconfig;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

public class InventoryRandomLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryRandomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory clientFactory) {

        String serviceId = environment.getRequiredProperty(
                LoadBalancerClientFactory.PROPERTY_NAME
        );

        return new RandomLoadBalancer(
                clientFactory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class
                ),
                serviceId
        );
    }
}
~~~

Giải thích các thành phần:

- `@LoadBalancerClient(name = "inventory-service")` gắn cấu hình cho đúng service ID.
- `LoadBalancerClientFactory` quản lý context và bean LoadBalancer của từng service ID.
- `LoadBalancerClientFactory.PROPERTY_NAME` cung cấp tên service ID của context đang được tạo.
- `getLazyProvider(serviceId, ServiceInstanceListSupplier.class)` cung cấp supplier tương ứng cho service đó.
- `RandomLoadBalancer` chọn instance từ danh sách supplier trả về.
- `ReactorLoadBalancer<ServiceInstance>` là giao diện chung của bộ chọn; tên `Reactor` trong interface không có nghĩa ứng dụng chỉ dùng được WebClient.

**Ranh giới component scan là quan trọng:** nếu `InventoryRandomLoadBalancerConfiguration` bị quét vào ApplicationContext chính như một `@Configuration` thông thường, bean Random có thể lan ra ngoài service ID dự định. Có thể để lớp cấu hình không gắn `@Configuration` như ví dụ, hoặc đặt lớp có `@Configuration` ngoài vùng scan và chỉ tham chiếu thông qua `@LoadBalancerClient`.

Cấu hình trên chỉ thay thuật toán **lựa chọn instance** của `inventory-service`. Nếu caller còn gọi `payment-service` nhưng không cấu hình riêng, payment tiếp tục dùng thuật toán mặc định của nó (thường là Round Robin).

## 8. Tạo danh sách instance để thử Random tại máy local

Để kiểm chứng Random, caller phải có nhiều instance cùng service ID. Có thể dùng `SimpleDiscoveryClient` để khai báo danh sách tĩnh mà không cần Eureka hoặc Consul.

Dependency của caller, quản lý phiên bản Spring Boot và Spring Cloud BOM tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

`application.yml` phía caller:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
              - uri: http://localhost:8083
~~~

Hai thông tin cần kiểm tra:

1. Khóa `inventory-service` phải trùng tên trong `@LoadBalancerClient` và hostname logic của request.
2. Cả ba URI phải thực sự có tiến trình inventory đang lắng nghe. Danh sách tĩnh không tự loại một cổng đã dừng.

Ở service đích, cung cấp endpoint nhận diện instance, ví dụ:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final Environment environment;

    public InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public Map<String, String> whoAmI() {
        return Map.of(
                "serviceId", "inventory-service",
                "instance", "inventory:" +
                        environment.getProperty("server.port", "8081")
        );
    }
}
~~~

Chạy **cùng mã nguồn inventory** thành ba tiến trình với `--server.port=8081`, `--server.port=8082` và `--server.port=8083`. Caller chạy cổng 8080. Các tiến trình cần có Spring Boot application riêng để endpoint trên hoạt động.

## 9. Gọi thử bằng load-balanced RestClient

Đặt bean `RestClient.Builder` được tích hợp LoadBalancer:

~~~java
package com.example.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Tạo endpoint chuyển tiếp một lời gọi đến inventory:

~~~java
package com.example.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class ProxyController {

    private final RestClient inventoryClient;

    public ProxyController(@LoadBalanced RestClient.Builder builder) {
        this.inventoryClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    @GetMapping("/proxy/whoami")
    public InstanceResponse whoAmI() {
        return inventoryClient.get()
                .uri("/whoami")
                .retrieve()
                .body(InstanceResponse.class);
    }

    public record InstanceResponse(
            String serviceId,
            String instance
    ) {
    }
}
~~~

Khi gọi `GET http://localhost:8080/proxy/whoami`, RestClient nhận URI logic, Spring Cloud LoadBalancer chọn một `ServiceInstance` bằng Random, rồi gửi request đến một trong các cổng 8081/8082/8083. Trường `instance` của response dùng để kiểm chứng instance thực tế.

Với WebClient đã được đánh dấu `@LoadBalanced` hoặc OpenFeign dùng service ID `inventory-service`, bộ chọn trong context riêng của service này vẫn là Random. **Thuật toán chọn đích không quyết định HTTP client hoạt động blocking hay non-blocking.** RestClient thường dùng lời gọi blocking, WebClient hỗ trợ pipeline reactive, còn OpenFeign là interface khai báo lời gọi.

## 10. Thực hành quan sát chuỗi ngẫu nhiên

Trên PowerShell, gọi 15 lần để nhìn chuỗi:

~~~powershell
1..15 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/whoami").instance
}
~~~

Ví dụ đầu ra **minh họa**, không phải thứ tự cố định:

~~~text
inventory:8082
inventory:8082
inventory:8081
inventory:8083
inventory:8083
inventory:8081
inventory:8082
inventory:8083
inventory:8081
inventory:8081
inventory:8082
inventory:8082
inventory:8083
inventory:8081
inventory:8082
~~~

Không viết test mong đợi chuỗi cố định này. Random có thể tạo nhiều chuỗi khác nhau ngay cả khi code và cấu hình không đổi.

Để quan sát phân bố trên 900 request:

~~~powershell
$selected = 1..900 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/whoami").instance
}

$selected |
    Group-Object |
    Sort-Object Name |
    Select-Object Name, Count
~~~

Một ví dụ đầu ra:

~~~text
Name             Count
----             -----
inventory:8081     309
inventory:8082     286
inventory:8083     305
~~~

Ba bộ đếm cộng lại bằng 900. Nếu các instance cùng có xác suất 1/3, kỳ vọng là 300 lượt mỗi bên, nhưng việc cả ba cùng đúng 300 không được bảo đảm. Số lần chọn của từng instance có dao động ngẫu nhiên; mẫu 900 thường đủ để nhìn xu hướng, chưa thể chứng minh cấu hình chính xác tuyệt đối.

Nếu muốn ước lượng tỷ lệ, dùng:

~~~powershell
$total = $selected.Count

$selected |
    Group-Object |
    Sort-Object Name |
    ForEach-Object {
        [pscustomobject]@{
            Instance = $_.Name
            Requests = $_.Count
            Percent  = [math]::Round(100 * $_.Count / $total, 2)
        }
    }
~~~

Với kiểm thử có ý nghĩa, hãy ghi lại số request thành công, lỗi, số lần retry và danh sách instance khả dụng trong suốt quá trình thử. Không âm thầm loại request lỗi khỏi mẫu rồi kết luận bộ chọn cân bằng đều.

## 11. Những yếu tố làm phân bố thực tế khác lý thuyết

Giả định phân bố đều chỉ gần đúng trong điều kiện danh sách ứng viên ổn định, mỗi instance xuất hiện đúng một lần và mỗi request có một lượt chọn độc lập. Các yếu tố sau có thể thay đổi cách quan sát:

| Yếu tố | Tác động |
|---|---|
| Discovery cập nhật danh sách | Số ứng viên `n` thay đổi theo thời gian |
| Cache danh sách instance | Một số thay đổi instance chưa xuất hiện ngay ở caller |
| Health check | Instance không khỏe có thể bị loại trước khi Random chọn |
| Zone/hint filtering | Chỉ các instance phù hợp tiêu chí được đưa vào tập chọn |
| Retry | Một request nghiệp vụ có thể tạo nhiều lần chọn/gửi HTTP |
| Backend khác năng lực | Random không tự điều chỉnh dựa vào CPU hoặc response time |
| Client và server timeout | Số request hoàn tất khác với số lần đã chọn |
| Nhiều caller | Mỗi caller có context/bộ chọn riêng; thống kê toàn hệ thống cần gộp nhiều nguồn |
| Sticky session hoặc routing tầng hạ tầng | Có thể thay đổi backend cuối cùng so với instance được client nghĩ là đang gọi |

Ví dụ, các instance A, B, C đều được đăng ký nhưng B đã chết mà danh sách tĩnh chưa cập nhật. Random vẫn có thể chọn B và gây lỗi kết nối. **Random không phải là health check**. Muốn lọc B, cần discovery/health-check supplier hoặc cơ chế vận hành khác để cập nhật tập ứng viên.

Mặt khác, nếu hạ tầng đã cung cấp VIP cân bằng tải phía sau một `ServiceInstance`, Random ở phía Spring Cloud chỉ thấy VIP đó. Nó không chọn trực tiếp những replica phía sau VIP. Khi thiết kế nhiều tầng load balancing, cần xác định rõ tầng nào chọn instance và tầng nào phân phối tới backend thật.

## 12. Retry, timeout và khả năng tiếp tục chọn instance lỗi

Spring Cloud LoadBalancer lựa chọn instance; HTTP client mới là nơi thực hiện kết nối và gửi request. Nếu instance được chọn trả lỗi hoặc timeout, việc thử lại phụ thuộc cấu hình retry ở Spring Cloud LoadBalancer, RestClient/WebClient, OpenFeign hoặc các thư viện resilience khác.

Đừng giả định Random tự nhớ instance vừa lỗi để tránh ở lần chọn kế tiếp. Theo thuật toán thuần túy, nếu danh sách vẫn là [A, B, C], xác suất chọn lại B ở lượt sau vẫn là 1/3.

Spring Cloud có các thành phần bổ trợ cho retry, ví dụ `RetryAwareServiceInstanceListSupplier` khi được cấu hình phù hợp, để hỗ trợ tránh instance vừa thất bại trong lần retry. Quy tắc thực tế phụ thuộc cơ chế retry, cấu hình `spring.cloud.loadbalancer.retry.avoid-previous-instance` và danh sách còn đủ instance hay không.

Ví dụ dòng chảy:

~~~mermaid
sequenceDiagram
    participant U as Client
    participant L as RandomLoadBalancer
    participant A as inventory A
    participant B as inventory B

    U->>L: Lựa chọn cho HTTP GET
    L-->>U: Chọn inventory A
    U->>A: GET /whoami
    A--xU: Lỗi kết nối / timeout
    Note over U: Retry chỉ nếu được cấu hình và đủ điều kiện
    U->>L: Lựa chọn lần retry
    L-->>U: Có thể chọn B hoặc ứng viên khác
    U->>B: GET /whoami
    B-->>U: 200 OK
~~~

Sơ đồ trên minh họa khả năng chọn B sau retry, không khẳng định mọi lỗi đều được retry hay lần retry luôn chọn instance khác. Với thao tác ghi như POST tạo thanh toán, cần kiểm soát idempotency trước khi bật retry để tránh thực hiện nghiệp vụ hai lần.

Timeout kết nối/đọc response phải được cấu hình ở HTTP transport hoặc HTTP client thích hợp. Không có một thuộc tính Random nào tự giới hạn thời gian toàn bộ request. Retry và backoff có thể làm tổng thời gian xử lý lớn hơn đáng kể; nên đặt một deadline phù hợp với yêu cầu nghiệp vụ.

## 13. Random có phù hợp khi các instance khác năng lực?

Giả sử:

- Instance A có 4 CPU.
- Instance B có 1 CPU.
- Cả hai cùng xử lý một API nhưng năng lực tối đa không bằng nhau.

Random đồng đều sẽ chọn A và B gần 50/50 theo số lượt, dù B có thể chịu ít tải hơn. Nếu request có chi phí tương tự, B có nguy cơ quá tải trước A.

Có thể dùng **weighted load balancing** khi muốn phân phối theo trọng số. Spring Cloud cung cấp `WeightedServiceInstanceListSupplier`; với metadata trọng số `weight` hoặc `WeightFunction` tùy chỉnh, supplier có thể ảnh hưởng đến danh sách ứng viên đưa vào bộ chọn.

Nếu mong muốn 80% request tới A và 20% tới B, cần chính sách có trọng số được thiết kế và đo kiểm rõ ràng. Không thể yêu cầu `RandomLoadBalancer` thuần túy tự suy ra tỷ lệ 80/20 từ CPU.

Những yêu cầu khác có thể cần chiến lược riêng:

- **Affinity/sticky session:** người dùng cần tiếp tục đến cùng backend.
- **Locality/zone preference:** ưu tiên instance trong zone gần caller.
- **Least connections hoặc latency-aware:** tránh instance đang bận.
- **Canary rollout:** chỉ một tỷ lệ request đến phiên bản mới, có thể dựa trên metadata và policy.
- **Idempotent retry:** tránh instance thất bại trước đó khi điều kiện cho phép.

Chọn Random khi các replica tương đối đồng nhất, chấp nhận dao động ngắn hạn và không có yêu cầu affinity hoặc routing đặc biệt.

## 14. Cách kiểm thử Random có ý nghĩa

Không nên viết unit test chỉ kiểm tra `RandomLoadBalancer` trả đúng một chuỗi thứ tự. Random không hứa hẹn thứ tự cố định. Thay vào đó, nên kiểm thử hai cấp:

**Cấp chức năng:** Với một danh sách chỉ gồm một instance, xác nhận lần chọn trả đúng instance đó. Với danh sách rỗng, xác nhận hệ thống trả tín hiệu không có instance và client xử lý phù hợp. Với nhiều instance, xác nhận kết quả luôn thuộc tập ứng viên.

**Cấp tích hợp:** Với nhiều instance thật, gửi đủ nhiều HTTP request và thống kê instance đã xử lý. Quan sát tỷ lệ theo khoảng thời gian dài hơn, đồng thời xác nhận không có filter/retry làm thay đổi tập lựa chọn.

Với các bài kiểm thử thống kê, dùng độ lệch cho phép đã tính trước và tránh ngưỡng quá hẹp tạo test chập chờn. Chẳng hạn, ở ba instance và 900 lần chọn độc lập, một instance có kỳ vọng 300 lượt và độ lệch chuẩn khoảng 14,1; một vài chục lượt chênh lệch chưa đủ kết luận có lỗi. Kết hợp thống kê với kiểm tra **cấu hình bộ chọn** và **danh sách ứng viên** sẽ đáng tin cậy hơn việc chỉ nhìn kết quả vài request.

Nếu kiểm thử một thuật toán tùy chỉnh cần tính tái lập tuyệt đối, nên thiết kế thuật toán có khả năng inject nguồn random hoặc tách bước chọn chỉ số để kiểm thử riêng. `RandomLoadBalancer` tiêu chuẩn được dùng cho lựa chọn vận hành, không nên giả định có thể đặt một random seed cố định qua cấu hình thông thường.

## 15. Quan sát và xử lý sự cố

Khi cần chứng minh thuật toán Random đang chạy, nên thu thập ít nhất ba nhóm dữ liệu:

1. **Tầng caller:** service ID, thời gian gọi, status, số lần retry, mã tương quan request.
2. **Tầng LoadBalancer:** tập instance khả dụng, instance được chọn nếu có logging/tracing phù hợp, metrics của lifecycle.
3. **Tầng backend:** instance ID thực nhận request, response time, CPU, số kết nối và tỷ lệ lỗi.

Spring Cloud LoadBalancer có thể tích hợp Micrometer lifecycle statistics khi có registry và bật `spring.cloud.loadbalancer.stats.micrometer.enabled`. Dùng Actuator/metrics exporter phù hợp và kiểm tra tài liệu của phiên bản Spring Cloud đang chạy.

Một bảng chẩn đoán nhanh:

| Hiện tượng | Cách kiểm tra |
|---|---|
| Luôn chọn một instance | Danh sách ứng viên có thực sự nhiều hơn một? Có filter hoặc discovery cache giữ một bản sao? |
| Kết quả luân phiên cứng nhắc | Client có thể vẫn dùng Round Robin; kiểm tra `@LoadBalancerClient` và vị trí configuration class |
| Nhiều request liên tục vào cùng một replica | Có thể chỉ là chuỗi Random hợp lệ; tăng số mẫu và đo tỷ lệ |
| Request thất bại dù còn instance khỏe | Instance lỗi có còn trong supplier? Retry/health check đã cấu hình đúng chưa? |
| Thống kê backend không trùng bộ đếm caller | Retry, gateway/VIP, sticky routing hoặc các request lỗi có thể làm bộ đếm khác nhau |
| Random áp dụng cho cả dịch vụ khác | Custom LoadBalancer configuration có bị component scan vào context chính không? |
| Tỷ lệ vẫn lệch lớn khi đo dài | Kiểm tra tập instance, trọng số, filter, năng lực backend, lỗi, retry và cách lấy mẫu |

## 16. Checklist trước khi sử dụng

- [ ] Xác định service ID được caller gọi và danh sách `ServiceInstance` mà discovery cung cấp.
- [ ] Phân biệt thuật toán chọn instance với bước lọc từ cache, health check, zone hoặc hint.
- [ ] Biết mặc định là Round Robin; nếu muốn Random, cấu hình `RandomLoadBalancer` rõ ràng.
- [ ] Đăng ký thuật toán theo service bằng `@LoadBalancerClient` và đặt configuration class ngoài phạm vi component scan chung.
- [ ] Dùng RestClient/WebClient/OpenFeign đã được tích hợp với LoadBalancer và URL service ID.
- [ ] Không kỳ vọng Random luân phiên đúng vòng hoặc bảo đảm mỗi instance nhận số request bằng nhau trong cửa sổ ngắn.
- [ ] Với `N` request và `n` ứng viên ổn định, dùng kỳ vọng `N/n` và tính đến dao động xác suất.
- [ ] Theo dõi backend thực nhận request thay vì chỉ quan sát URI logic ở caller.
- [ ] Cấu hình health check, retry, timeout và circuit breaker ở tầng phù hợp nếu cần chịu lỗi.
- [ ] Nếu replica khác năng lực hoặc cần stickiness, cân nhắc weighted/affinity strategy.
- [ ] Khi đổi cấu hình, xác minh riêng inventory mà không vô tình ảnh hưởng các service ID khác.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): hướng dẫn đổi từ Round Robin sang `RandomLoadBalancer` bằng `@LoadBalancerClient`, tích hợp HTTP client, supplier và metrics.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): tham khảo các thuộc tính cấu hình LoadBalancer, retry và quan sát theo phiên bản.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): các trừu tượng service discovery và retry.

Random trong Spring Cloud LoadBalancer chọn **ngẫu nhiên một phần tử của danh sách instance đủ điều kiện** ở mỗi lần lựa chọn. Nếu các instance có cơ hội ngang nhau và danh sách giữ nguyên, số lượt chọn sẽ có xu hướng phân bố gần đều khi quan sát dài hạn, nhưng không có cam kết về thứ tự hoặc độ đều trong từng nhóm request nhỏ. Hiểu rõ xác suất, pipeline supplier và ranh giới giữa lựa chọn, kết nối và retry giúp đánh giá Random đúng bằng hành vi thực tế, thay vì kỳ vọng nó luân phiên như Round Robin.
