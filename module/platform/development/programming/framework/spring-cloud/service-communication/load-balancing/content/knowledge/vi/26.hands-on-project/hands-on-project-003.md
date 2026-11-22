# Đối chiếu round-robin và random qua tập yêu cầu đủ lớn

Trong Spring Cloud LoadBalancer, **RoundRobinLoadBalancer** và **RandomLoadBalancer** đều chọn một **ServiceInstance** từ danh sách bản sao đã được cung cấp. Điểm khác biệt không nằm ở HTTP request được tạo ra như thế nào, mà nằm ở **quy luật chọn bản sao**. Với ít request, người quan sát có thể thấy random “thiên vị” hoặc round-robin “không đều” nếu vô tình đếm response theo thứ tự hoàn tất, bật retry, thay đổi danh sách instance hoặc dùng nhiều caller. Bởi vậy, cần một bài thực hành có **tập yêu cầu đủ lớn, điều kiện kiểm soát rõ và phương pháp thống kê phù hợp**.

Bài thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Ta sẽ dựng **ba Inventory Service instances**, một **Order Caller** dùng **@LoadBalanced RestClient**, lấy danh sách instance bằng **SimpleDiscoveryClient**, lần lượt chạy round-robin và random, gửi **6.000–30.000 HTTP requests**, thu phân phối, đo độ lệch và latency, kiểm tra các tình huống khi concurrency/retry/health thay đổi.

Điểm cần đạt được sau thực hành:

1. Tự cấu hình **RoundRobinLoadBalancer** và **RandomLoadBalancer** cho cùng service ID.
2. Phân biệt **lựa chọn ServiceInstance**, **HTTP attempt**, **response thành công** và **thứ tự response hoàn tất**.
3. Dùng bảng đếm, tỷ lệ, độ lệch tương đối, **chỉ số công bằng Jain** và **chi-square** để đọc dữ liệu.
4. Biết tại sao N lớn giúp quan sát random đáng tin hơn, nhưng **không buộc random chia chính xác đều**.
5. Hiểu ảnh hưởng của **discovery, health, cache, zone, retry, timeout, connection pool** và concurrency tới kết quả.
6. Có khả năng lặp lại phép đo và viết kết luận **có điều kiện**, không tuyên bố thuật toán nào “luôn nhanh hơn” chỉ từ một lần chạy.

> **Giới hạn của bài:** Các đoạn Java/Gradle/YAML là mẫu lab để người học triển khai trong repository thực hành riêng. Worker Knowledge chỉ ghi tài liệu Markdown này, không tạo source files và không chạy Gradle/test. Chọn Spring Boot và Spring Cloud release train tương thích theo BOM của môi trường; đừng trộn tùy ý phiên bản Spring Boot 3.x/4.x với Spring Cloud.

## 1. Vấn đề nghiên cứu và giả thuyết

Giả sử **inventory-service** có ba bản sao giống nhau:

| Instance | Host:port | API | Công suất giả định |
| --- | --- | --- | --- |
| inventory-a | 127.0.0.1:8091 | GET /whoami | Bằng nhau |
| inventory-b | 127.0.0.1:8092 | GET /whoami | Bằng nhau |
| inventory-c | 127.0.0.1:8093 | GET /whoami | Bằng nhau |

Caller gọi:

~~~http
GET http://inventory-service/whoami
~~~

Ba bản sao đều trả JSON có **instanceId** để ta biết ai **thực sự nhận request**:

~~~json
{"instanceId":"inventory-b"}
~~~

Ta đặt hai giả thuyết cần quan sát:

| Thuật toán | Giả thuyết khi N lớn, danh sách cố định, không retry |
| --- | --- |
| **Round Robin** | Luân phiên vị trí trong danh sách, số lượt **chọn** mỗi instance gần bằng nhau (chênh tối đa 1 với một chuỗi chọn tuần tự, danh sách không đổi) |
| **Random** | Mỗi lượt chọn độc lập gần đều trên cùng danh sách; số lượt mỗi instance **dao động ngẫu nhiên**, tỷ lệ tiến gần 1/3 khi N tăng |

Không nên thay giả thuyết bằng “round-robin luôn có latency thấp hơn”. Khi backend có hiệu năng khác nhau, network/HTTP pool tác động khác nhau và môi trường có tải, latency phụ thuộc nhiều yếu tố ngoài thuật toán lựa chọn.

### 1.1. “Đều” có hai nghĩa

**Đều theo số lượt**: A/B/C được chọn gần 1/3 số lần.

**Đều theo tải thực tế**: CPU, thời gian xử lý, số request đang chạy, bytes truyền, database queries và queue của A/B/C gần bằng nhau.

Round-robin có thể đạt **đều theo số lượt** nhưng chưa chắc **đều theo tải**. Nếu A mất 200 ms còn B chỉ 20 ms, số request đang chạy đồng thời ở A có thể lớn hơn dù lượt nhận bằng nhau. Bài đầu tiên chỉ so sánh **phân phối theo lượt request**, sau đó mới xem xét latency và các yếu tố nhiễu.

## 2. Kiến trúc lab

~~~mermaid
flowchart LR
    T["Người chạy lab"] --> O["Order Caller :8080"]
    O --> LB["Spring Cloud LoadBalancer"]
    D["SimpleDiscoveryClient\ninventory-service → A,B,C"] --> LB
    LB --> A["Inventory A :8091"]
    LB --> B["Inventory B :8092"]
    LB --> C["Inventory C :8093"]
    A --> M["JSON instanceId"]
    B --> M
    C --> M
    M --> O
    O --> R["Tổng hợp counts, tỷ lệ,\nlatency, lỗi"]
~~~

Ta chạy hai chế độ **trên cùng một topology**:

~~~text
Thí nghiệm 1:
  algorithm = round-robin
  fixed service instance list = [A, B, C]
  N = 6000

Thí nghiệm 2:
  algorithm = random
  fixed service instance list = [A, B, C]
  N = 6000
~~~

### 2.1. Những biến phải cố định

| Biến kiểm soát | Cấu hình |
| --- | --- |
| Service ID | inventory-service |
| Danh sách instance | A/B/C, giữ nguyên trong một lần chạy |
| API và response | GET /whoami, JSON cùng schema |
| Thuật toán | Chỉ thay **round-robin** ↔ **random** |
| HTTP client | Cùng RestClient/request factory |
| Retry | Tắt để **mỗi logical request = một HTTP attempt** |
| Health filter/zone/hint | Không thêm chính sách thay danh sách A/B/C trong pha cơ bản |
| N | Bằng nhau ở hai chế độ, ví dụ 6.000 |
| Concurrency | Ban đầu **tuần tự, chỉ một caller** |
| Warm-up | Có số lần cố định và không tính vào N |
| Lỗi backend | Pha cơ bản kỳ vọng 0 |
| Timeout | Cùng cấu hình đủ để tránh treo vô hạn |

**Vì sao quan trọng?** Nếu Round Robin chạy với hai instances còn Random chạy với ba, phép so sánh không còn nói về thuật toán. Nếu bật retry cho một bên, bạn đang so **hai chính sách retry + LoadBalancer**, không phải chỉ hai lựa chọn.

### 2.2. Phạm vi một LoadBalancer

Spring Cloud LoadBalancer tạo **child ApplicationContext theo service ID**. Một RoundRobinLoadBalancer cho inventory-service có trạng thái chọn riêng trong **caller process/context đó**. Khi chạy **nhiều caller pods**, mỗi pod có bộ đếm/vòng riêng; chúng **không tự đồng bộ chỉ số chọn toàn cụm**.

Vì vậy, phát biểu “6.000 request được chia 2.000–2.000–2.000” chỉ chắc chắn theo mô hình **một bộ chọn round-robin đang hoạt động, danh sách cố định ba phần tử, không retry và đếm các lần chọn tuần tự**. Không suy rộng cho mọi mô hình distributed traffic.

## 3. Mô hình xác suất và kỳ vọng

Gọi:

- \(N\): tổng số lượt chọn hoặc attempts **hợp lệ** cần phân tích.
- \(k\): số ServiceInstance có cơ hội chọn như nhau.
- \(n_i\): số lượt được gán cho instance \(i\), với \(\sum_{i=1}^{k}n_i=N\).
- \(p_i=n_i/N\): tỷ lệ quan sát của instance \(i\).
- \(E=N/k\): số lượt kỳ vọng trên mỗi instance khi policy lựa chọn đều.

### 3.1. Round-robin lý tưởng

Với một chuỗi lựa chọn theo vòng trên tập **k instance không đổi**, số lượt của mỗi instance sau N lần chọn chỉ có thể là:

\[
n_i\in\left\{\left\lfloor\frac{N}{k}\right\rfloor,\left\lceil\frac{N}{k}\right\rceil\right\}
\]

Nếu **N chia hết cho k**, tất cả instances có đúng \(N/k\) lượt chọn. Nếu không chia hết, chênh lệch count tối đa **1 lượt**, nhưng instance nào được thêm lượt phụ thuộc vị trí bắt đầu của bộ đếm.

Ví dụ với 3 instances:

~~~text
N = 12
A B C | A B C | A B C | A B C
=> A=4, B=4, C=4

N = 11
A B C | A B C | A B C | A B
=> A=4, B=4, C=3
~~~

Spring có thể bắt đầu ở vị trí khác so với A do seed/start state và những request trước đó; ta so **counts**, không khẳng định “request đầu luôn A”.

### 3.2. Random chọn đều

Khi mỗi lựa chọn ngẫu nhiên có xác suất \(1/k\) cho mỗi instance, số lượt của một instance là biến ngẫu nhiên dạng nhị thức (biên của phân phối đa thức):

\[
\operatorname{E}[n_i]=\frac{N}{k},\qquad
\operatorname{Var}(n_i)=N\frac{1}{k}\left(1-\frac{1}{k}\right)
\]

\[
\sigma_i=\sqrt{N\frac{1}{k}\left(1-\frac{1}{k}\right)}
\]

Với \(N=6000,k=3\):

~~~text
Kỳ vọng mỗi instance: 6000 / 3 = 2000
Độ lệch chuẩn:        sqrt(6000*(1/3)*(2/3)) ≈ 36.5 lượt
Khoảng gần ±2σ:       2000 ± 73 lượt (xấp xỉ)
~~~

Đây là khoảng tham khảo theo phân phối gần chuẩn cho **một count**, không phải bảo đảm mọi instance cùng nằm trong khoảng. Random có thể cho count lệch lớn hơn, và một sự lệch đơn lẻ **không chứng minh thuật toán sai**.

### 3.3. Vì sao cần N đủ lớn?

Độ lệch tuyệt đối điển hình của random tăng khoảng \(\sqrt{N}\), còn độ lệch **tương đối** giảm khoảng \(1/\sqrt{N}\).

| N | E cho k=3 | Độ lệch chuẩn xấp xỉ | Tỷ lệ một σ so với E |
| ---: | ---: | ---: | ---: |
| 30 | 10 | 2,58 | 25,8% |
| 300 | 100 | 8,16 | 8,16% |
| 3.000 | 1.000 | 25,82 | 2,58% |
| 6.000 | 2.000 | 36,51 | 1,83% |
| 30.000 | 10.000 | 81,65 | 0,82% |

Vì thế một screenshot với **9 request** và tỷ lệ A/B/C = 5/2/2 không đánh giá được fairness của random. Với hàng nghìn requests, ta đọc **phân phối** và lặp nhiều runs, không đòi “ngẫu nhiên phải chia đều tuyệt đối”.

## 4. Các chỉ số sẽ ghi lại

Không chỉ dừng ở biểu đồ số request, hãy tính:

| Metric | Công thức/định nghĩa | Diễn giải |
| --- | --- | --- |
| Count | \(n_i\) | Số response thành công do instance i trả trong pha cơ bản |
| Share | \(100n_i/N\) (%) | Tỷ lệ nhận request |
| Max-min gap | \(\max(n_i)-\min(n_i)\) | Khoảng cách counts |
| Relative gap | \((\max n_i-\min n_i)/(N/k)\) | Độ lệch tính theo kỳ vọng |
| Jain fairness | \((\sum n_i)^2/(k\sum n_i^2)\) | Gần 1 khi counts cân bằng |
| Pearson chi-square | \(\sum(n_i-E)^2/E\) | Độ lệch so với phân phối kỳ vọng |
| Error rate | số lỗi / tổng request | Có lỗi làm méo counts nhận được không? |
| P50/P95/P99 | Phân vị thời gian phản hồi | Hiệu năng tổng thể, không thuần thuật toán |
| Throughput | Số request thành công / elapsed seconds | Kết quả kết hợp client, network và backend |

**Lưu ý:** Chỉ số Jain, chi-square và tỷ lệ trên cùng một run không phải ba kiểm định độc lập. Chúng đều tóm tắt một vector counts. Chi-square chỉ là **thước đo thống kê** dưới mô hình chọn ngẫu nhiên độc lập và phân phối đều; không dùng nó để “chấm điểm đúng/sai” của round-robin vốn là thuật toán xác định.

### 4.1. Định nghĩa N nhất quán

Trong **pha baseline** mọi request trả thành công và retry tắt, nên:

~~~text
N logical calls = N selections = N HTTP attempts = N responses thành công
~~~

Khi có timeout/503, phương trình này **không còn đúng**:

~~~text
N logical calls
    <= N HTTP attempts (nếu retry)
    != N backend successes (nếu lỗi)
    có thể != N observed responses (nếu client mất response)
~~~

Đừng lấy **counts từ những response thành công** làm bằng chứng mọi lượt chọn đã chia đều khi một instance chết. Để đo **selection fairness thật** dưới lỗi, cần instrumentation tại LoadBalancer lifecycle hoặc HTTP attempt, không chỉ dựa vào JSON backend trả về.

## 5. Cấu trúc dự án lab và dependencies

Gợi ý hai ứng dụng Spring Boot:

~~~text
loadbalancer-lab/
├─ settings.gradle
├─ inventory/
│  └─ src/main/java/lab/inventory/InventoryApplication.java
└─ caller/
   ├─ src/main/java/lab/caller/CallerApplication.java
   ├─ src/main/java/lab/caller/ExperimentController.java
   ├─ src/main/java/lab/caller/InstanceResponse.java
   ├─ src/main/java/lab/lb/InventoryLoadBalancerConfiguration.java
   └─ src/main/resources/application.yml
~~~

**Đây là sơ đồ bài tập, không phải các file được tạo bởi tài liệu này.** Chia package để **InventoryLoadBalancerConfiguration nằm ngoài component scan của CallerApplication** (mục 8 giải thích lý do).

Ví dụ dependencies (bỏ version riêng vì quản lý qua Spring Boot và Spring Cloud BOM tương thích):

~~~gradle
// inventory/build.gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}

// caller/build.gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Spring Boot 3.2+ có **RestClient**. Không thêm Eureka/Consul trong pha này: **SimpleDiscoveryClient** đọc danh sách instance cố định từ property, nhờ vậy giảm nhiễu do registry cập nhật. Nếu đang dùng Spring Boot 4.x, kiểm tra tên artifact web starter theo BOM và Spring Boot migration notes.

### 5.1. Vì sao không chạy test trực tiếp trong production?

6.000–30.000 requests liên tục có thể:

- Bão connection pool hoặc tăng CPU/network.
- Làm méo metrics và error budget của dịch vụ thật.
- Tăng chi phí registry/gateway/cloud egress.
- Tác động các endpoint có side effect.

Hãy chạy trong **local hoặc môi trường test cô lập** với GET không ghi dữ liệu. Không dùng endpoint đặt hàng/thanh toán như một phép thử phân phối.

## 6. Tạo Inventory Service trả về định danh bản sao

Mỗi Inventory instance dùng **cùng một ứng dụng** nhưng nhận **server.port** và **lab.instance-id** khác nhau. Ví dụ:

~~~java
package lab.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class InventoryApplication {

    private final String instanceId;

    public InventoryApplication(Environment environment) {
        this.instanceId = environment.getRequiredProperty("lab.instance-id");
    }

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }

    @GetMapping(
            path = "/whoami",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public InstanceReply whoAmI() {
        return new InstanceReply(instanceId);
    }

    public record InstanceReply(String instanceId) {}
}
~~~

Response từ A:

~~~json
{"instanceId":"inventory-a"}
~~~

Response từ B:

~~~json
{"instanceId":"inventory-b"}
~~~

### 6.1. Tại sao ID phải đến từ backend?

Trong pha cơ bản, Caller nhận response từ **instance thực sự xử lý HTTP request**, chứ không tự giả định instance được chọn theo vị trí trong mảng [A, B, C]. Nếu request tới A nhưng body tự ghi nhãn B, phép đo sẽ sai; vì vậy mỗi backend được khởi động với instance ID cố định và kiểm tra trực tiếp qua port vật lý.

Không nên dùng một header tự tạo từ **client** làm bằng chứng duy nhất về backend đã nhận request. Có thể bổ sung **X-Instance-Id từ chính server** để đối soát, nhưng response body trong lab đã đủ khi server giả lập đáng tin cậy.

### 6.2. Không tạo side effect trên /whoami

Endpoint GET không ghi database, gửi message hoặc thay đổi inventory. Nhờ vậy, khi người học chạy 30.000 calls, thí nghiệm không làm thay đổi dữ liệu và không phải giải quyết idempotency.

## 7. Cấu hình Caller và SimpleDiscoveryClient

Định nghĩa **caller/src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-caller
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://127.0.0.1:8091
              - uri: http://127.0.0.1:8092
              - uri: http://127.0.0.1:8093
    loadbalancer:
      retry:
        enabled: false

lab:
  algorithm: round-robin
~~~

Điều kiện:

- Caller có **spring-cloud-starter-loadbalancer**.
- Không có registry-backed DiscoveryClient khác trong classpath làm thay đổi nguồn instance.
- Cả ba Inventory processes đang nghe đúng port.
- URI backend cố định để loại bỏ tác động của discovery registration/TTL trong pha so sánh.
- HTTP scheme giống nhau; bài này dùng **HTTP trên máy local** chỉ để đo thuật toán, không phải cấu hình bảo mật cho production.

**Cần phân biệt:** host **inventory-service** trong URL logic là **service ID**, không phải DNS host phải được phân giải bởi operating system. Spring Cloud LoadBalancer sẽ chọn ServiceInstance và tạo URI vật lý đến 127.0.0.1:8091/8092/8093.

### 7.1. Kiểm tra trực tiếp ba backend trước khi dùng LoadBalancer

Trên Windows PowerShell:

~~~powershell
(Invoke-RestMethod http://127.0.0.1:8091/whoami).instanceId
(Invoke-RestMethod http://127.0.0.1:8092/whoami).instanceId
(Invoke-RestMethod http://127.0.0.1:8093/whoami).instanceId
~~~

Kỳ vọng:

~~~text
inventory-a
inventory-b
inventory-c
~~~

Nếu A/B/C trả sai ID, **dừng thí nghiệm tại đây**. Không phân tích fairness từ các nhãn backend chưa đáng tin cậy.

## 8. Chuyển RoundRobinLoadBalancer và RandomLoadBalancer bằng property

Spring Cloud mặc định sử dụng **RoundRobinLoadBalancer**; ta vẫn khai báo cả hai thuật toán rõ ràng để thí nghiệm có thể đổi bằng **lab.algorithm**.

Định nghĩa class **lab.lb.InventoryLoadBalancerConfiguration**:

~~~java
package lab.lb;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.RoundRobinLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

// Không đặt @Configuration trong package được CallerApplication scan.
// Class được đăng ký như cấu hình riêng của @LoadBalancerClient.
public class InventoryLoadBalancerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "lab",
            name = "algorithm",
            havingValue = "round-robin",
            matchIfMissing = true)
    ReactorLoadBalancer<ServiceInstance> roundRobinLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);
        return new RoundRobinLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab",
            name = "algorithm",
            havingValue = "random")
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);
        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

### 8.1. Tại sao lấy PROPERTY_NAME từ child context?

Spring Cloud LoadBalancer tạo **child ApplicationContext riêng cho service ID**. Giá trị **LoadBalancerClientFactory.PROPERTY_NAME** cho biết context hiện tại đang phục vụ service nào. Lời gọi **factory.getLazyProvider(serviceId, ServiceInstanceListSupplier.class)** lấy supplier tương ứng service ID đó, không tự ghép danh sách từ nhiều service.

**RandomLoadBalancer** và **RoundRobinLoadBalancer** thực hiện cùng contract chọn **ServiceInstance**, nên ta chỉ thay đúng thuật toán. Đây là điểm mở rộng được tài liệu Spring Cloud giới thiệu.

### 8.2. Không component-scan cấu hình con như cấu hình toàn cục

Tài liệu Spring Cloud cảnh báo class dùng qua **@LoadBalancerClient(configuration=...)** nên **không gắn @Configuration**, hoặc phải đặt ngoài phạm vi component scan của ứng dụng chính. Ví dụ cố ý đặt class trong **lab.lb**, ngoài package **lab.caller** của CallerApplication.

Nếu class cấu hình LoadBalancer cho Inventory vô tình được scan vào **parent ApplicationContext**, bean tùy chỉnh có thể tác động ngoài phạm vi mong muốn, gây nhiễu cả kết quả thí nghiệm lẫn những service khác.

### 8.3. Property không hợp lệ

Giá trị chỉ nên là:

~~~text
lab.algorithm=round-robin
lab.algorithm=random
~~~

Nếu nhập sai **lab.algorithm=randam**, các @ConditionalOnProperty không match, và có thể có một bean mặc định khác được auto-configured. **Không coi tên property trong response là chứng cứ thuật toán đã được chọn**; dùng test/log bean type và số liệu phân phối để xác nhận.

## 9. Khởi tạo CallerApplication với @LoadBalanced RestClient

~~~java
package lab.caller;

import lab.lb.InventoryLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

**Khi áp dụng trong dự án thật:** Nếu Spring Boot đã có RestClient.Builder được cấu hình thêm observations, TLS, interceptors và codecs, nên dùng **RestClientBuilderConfigurer** phù hợp để không đánh mất cấu hình đó. Cần xác định **connect/read timeout** của transport; đoạn trên giữ ví dụ tối giản để người học thấy đường đi của LoadBalancer.

Với RestClient, **@LoadBalanced** đánh dấu builder để Spring Cloud thêm tích hợp chọn ServiceInstance. Chỉ dùng RestClient.builder().baseUrl("http://inventory-service").build() trong một ứng dụng không có interceptor LoadBalancer thì **không tự** hiểu inventory-service là service ID.

### 9.1. Kiểm tra đường đi của một request

~~~text
Controller -> RestClient GET /whoami
    |
    v
Logical URI: http://inventory-service/whoami
    |
    v
BlockingLoadBalancerClient dùng ReactorServiceInstanceLoadBalancer
    |
    v
Lấy [A,B,C] từ SimpleDiscoveryClient
    |
    v
RoundRobin hoặc Random chọn instance
    |
    v
HTTP request tới IP:port vật lý
    |
    v
Backend trả JSON instanceId
~~~

**Tên “Reactor” trong ReactorLoadBalancer không có nghĩa RestClient chuyển thành reactive HTTP client.** Spring Cloud có thể sử dụng abstraction chọn instance trong đường HTTP **blocking**. HTTP transport do RestClient/request factory thực thi vẫn là synchronous.

## 10. Viết endpoint chạy N request và thống kê phân phối

Ta tạo endpoint nội bộ **GET /lab/run?n=6000&warmup=30**. Nó:

1. Gửi số lượng warm-up calls cố định để tránh so sánh cold connection khác nhau.
2. Gửi N HTTP calls **tuần tự** bằng chính RestClient đã @LoadBalanced.
3. Đọc **instanceId trong response** để tăng bộ đếm.
4. Đếm lỗi riêng, không âm thầm bỏ qua.
5. Đo elapsed time bằng **System.nanoTime()** và tính các phân vị.
6. Tính Jain fairness và chi-square trên **responses thành công**, kèm cảnh báo nếu có lỗi.

Ví dụ **lab.caller.ExperimentController** (Java 17+):

~~~java
package lab.caller;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestClient;

@RestController
@RequestMapping("/lab")
public class ExperimentController {

    private static final Set<String> KNOWN = Set.of(
            "inventory-a", "inventory-b", "inventory-c");

    private final RestClient inventory;
    private final String algorithm;

    public ExperimentController(
            RestClient inventoryRestClient,
            Environment environment) {
        this.inventory = inventoryRestClient;
        this.algorithm = environment.getProperty(
                "lab.algorithm", "round-robin");
    }

    @GetMapping("/run")
    public RunReport run(
            @RequestParam(defaultValue = "6000") int n,
            @RequestParam(defaultValue = "30") int warmup) {

        if (n < 300 || n > 30_000 || warmup < 0 || warmup > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "n must be 300..30000 and warmup 0..100");
        }

        // Warm-up không được tính vào N. Nếu backend chưa sẵn sàng,
        // báo lỗi trước khi bắt đầu đo.
        for (int i = 0; i < warmup; i++) {
            InstanceReply reply = callInventory();
            requireKnownInstance(reply);
        }

        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("inventory-a", 0);
        counts.put("inventory-b", 0);
        counts.put("inventory-c", 0);

        Map<String, Integer> errorsByType = new TreeMap<>();
        List<Long> successLatenciesNanos = new ArrayList<>(n);
        int failed = 0;
        long wallStart = System.nanoTime();

        for (int i = 0; i < n; i++) {
            long oneStart = System.nanoTime();
            try {
                InstanceReply reply = callInventory();
                requireKnownInstance(reply);

                counts.merge(reply.instanceId(), 1, Integer::sum);
                successLatenciesNanos.add(
                        System.nanoTime() - oneStart);
            } catch (RuntimeException exception) {
                failed++;
                errorsByType.merge(
                        exception.getClass().getSimpleName(),
                        1, Integer::sum);
            }
        }

        double elapsedSeconds =
                (System.nanoTime() - wallStart) / 1_000_000_000.0;
        int succeeded = n - failed;
        double sumSquares = 0;
        int minimum = Integer.MAX_VALUE;
        int maximum = 0;

        for (int count : counts.values()) {
            sumSquares += (double) count * count;
            minimum = Math.min(minimum, count);
            maximum = Math.max(maximum, count);
        }

        double expected = succeeded / (double) counts.size();
        double chiSquare = 0;
        if (expected > 0) {
            for (int count : counts.values()) {
                double deviation = count - expected;
                chiSquare += deviation * deviation / expected;
            }
        }

        double jain = sumSquares > 0
                ? (double) succeeded * succeeded /
                        (counts.size() * sumSquares)
                : 0.0;
        double relativeGapPercent = expected > 0
                ? (maximum - minimum) / expected * 100.0
                : 0.0;

        successLatenciesNanos.sort(Long::compareTo);

        return new RunReport(
                algorithm, n, warmup, succeeded, failed,
                counts, errorsByType,
                jain, chiSquare, relativeGapPercent,
                percentileMs(successLatenciesNanos, 0.50),
                percentileMs(successLatenciesNanos, 0.95),
                percentileMs(successLatenciesNanos, 0.99),
                elapsedSeconds,
                elapsedSeconds > 0
                        ? succeeded / elapsedSeconds : 0.0);
    }

    private InstanceReply callInventory() {
        return inventory.get()
                .uri("/whoami")
                .retrieve()
                .body(InstanceReply.class);
    }

    private static void requireKnownInstance(InstanceReply reply) {
        if (reply == null ||
                !KNOWN.contains(reply.instanceId())) {
            throw new IllegalStateException(
                    "Missing or unknown backend instance");
        }
    }

    private static double percentileMs(
            List<Long> sortedNanos, double fraction) {
        if (sortedNanos.isEmpty()) {
            return 0.0;
        }
        int index = (int) Math.ceil(
                sortedNanos.size() * fraction) - 1;
        index = Math.max(0, Math.min(
                index, sortedNanos.size() - 1));
        return sortedNanos.get(index) / 1_000_000.0;
    }

    public record InstanceReply(String instanceId) {}

    public record RunReport(
            String algorithm,
            int requested,
            int warmup,
            int succeeded,
            int failed,
            Map<String, Integer> counts,
            Map<String, Integer> errorsByType,
            double jainFairness,
            double chiSquare,
            double relativeGapPercent,
            double p50Ms,
            double p95Ms,
            double p99Ms,
            double elapsedSeconds,
            double throughputPerSecond) {}
}
~~~

### 10.1. Những điểm bắt buộc hiểu trước khi dùng kết quả

- **RunReport.counts** đếm backend trong **response thành công**, chưa phải trực tiếp bộ đếm choose() của LoadBalancer. Chỉ khi failed=0, không retry và mọi body hợp lệ, mới suy ra một request thành công tương ứng một lần chọn.
- **p50/p95/p99** chỉ đo những request **thành công**, không kể latency của failed attempts. Phải đọc **failed/errorsByType** trước khi so độ trễ.
- **relativeGapPercent** dùng mẫu số \(N_{\text{success}}/3\); khi có lỗi, thước đo này phản ánh **phân phối successes**, không phản ánh xác suất chọn instance thật.
- Warm-up requests có tác động tới vị trí bộ đếm Round Robin, connection pool và JIT; **không được cộng vào N** nhưng cần ghi số lượng warm-up của mỗi run.
- **elapsedSeconds** là tổng thời gian gửi N requests **tuần tự**. Throughput của run này bị giới hạn bởi network + backend + JSON decode + thread của caller, không phải năng lực tối đa của LoadBalancer.
- Chỉ số **jainFairness=1** phản ánh counts bằng nhau; nó không bảo đảm latency, CPU hoặc availability đều.

### 10.2. Đây là endpoint phục vụ thí nghiệm, không phải public API

Một request đến **/lab/run?n=30000** có thể giữ một thread server lâu và bắn nhiều outbound HTTP requests. **Chỉ bật trong môi trường cô lập**; nếu phải giữ ở test cluster, đặt authentication, timeout, rate limit và không cho người dùng cuối gọi tùy ý.

Với Spring MVC, một method synchronous chạy N requests lớn sẽ giữ request thread. Có thể dùng CLI runner riêng ở dự án thật, nhưng phần này cố tình dùng HTTP endpoint để dễ thao tác và thấy kết quả JSON ngay.

## 11. Chạy thí nghiệm A/B theo cùng quy trình

Trước tiên hoàn thiện **settings.gradle** để khai báo hai subprojects:

~~~gradle
rootProject.name = "loadbalancer-lab"
include("inventory", "caller")
~~~

Plugin versions và Spring Cloud BOM phải được cấu hình trong **build.gradle** của dự án theo cặp phiên bản đã chọn. Các snippets ở mục 5 chỉ minh họa dependencies; không phải toàn bộ build script có thể chạy trực tiếp khi chưa khai báo plugins/repositories/BOM.

### 11.1. Khởi động ba backend ở ba terminal khác nhau

Trên Windows PowerShell, trong folder root của dự án lab:

~~~powershell
# Terminal 1
.\gradlew.bat :inventory:bootRun --args="--server.port=8091 --lab.instance-id=inventory-a"

# Terminal 2
.\gradlew.bat :inventory:bootRun --args="--server.port=8092 --lab.instance-id=inventory-b"

# Terminal 3
.\gradlew.bat :inventory:bootRun --args="--server.port=8093 --lab.instance-id=inventory-c"
~~~

Mỗi command là một **tiến trình đang chạy**; không nhập cả ba nối tiếp trong một terminal rồi mong chúng đồng thời hoạt động. Sau khi cả ba ready, kiểm tra /whoami ở từng port như mục 7.1.

### 11.2. Chạy caller theo round-robin

Terminal 4:

~~~powershell
.\gradlew.bat :caller:bootRun --args="--lab.algorithm=round-robin"
~~~

Terminal 5:

~~~powershell
$rr = Invoke-RestMethod "http://127.0.0.1:8080/lab/run?n=6000&warmup=30"
$rr | ConvertTo-Json -Depth 5
~~~

Lưu response JSON vào báo cáo thí nghiệm. Kiểm tra **failed=0**, mỗi instance có count dương và tổng counts bằng 6000.

### 11.3. Chạy caller theo random

**Dừng caller round-robin** trước. Giữ nguyên ba Inventory backends và dataset, rồi khởi động caller mới:

~~~powershell
.\gradlew.bat :caller:bootRun --args="--lab.algorithm=random"
~~~

Thực hiện:

~~~powershell
$random = Invoke-RestMethod "http://127.0.0.1:8080/lab/run?n=6000&warmup=30"
$random | ConvertTo-Json -Depth 5
~~~

Không thay danh sách instance, server response logic hoặc HTTP engine giữa hai lần. **Restart Caller** để chắc chắn thuật toán và child ApplicationContext được tạo lại theo property mới; không chỉ sửa application.yml khi process vẫn đang chạy.

### 11.4. Các phép kiểm tra trước khi ghi kết luận

~~~text
[ ] Cả ba backend trả đúng ID và HTTP 200.
[ ] Caller đã restart với thuật toán dự định.
[ ] Tổng requested = 6000, failed = 0.
[ ] Tổng counts A+B+C = succeeded.
[ ] Warmup tương đương giữa hai chế độ.
[ ] Không có request khác sử dụng inventory-service trong lúc đo.
[ ] Không bật LB retry/Feign retry/gateway retry.
[ ] Không có zone/health/hint/weighted filter làm đổi tập ứng viên.
[ ] Không so response completion order với selection order.
~~~

Nếu có **failed > 0**, đừng sửa counts bằng cách “gán đều lỗi” cho các instance; phải điều tra lỗi trước hoặc chạy lại khi tất cả backend ổn định.

## 12. Đọc kết quả: round-robin gần như đều tuyệt đối, random dao động

Một **ví dụ giả định** cho N=6000, k=3, không lỗi:

| Thuật toán | inventory-a | inventory-b | inventory-c | Tổng |
| --- | ---: | ---: | ---: | ---: |
| Round Robin | 2.000 | 2.000 | 2.000 | 6.000 |
| Random, run 1 | 1.987 | 2.050 | 1.963 | 6.000 |
| Random, run 2 | 2.034 | 1.981 | 1.985 | 6.000 |

Các hàng random ở đây là **số liệu minh họa**, không phải output đã chạy trong dự án. Khi thực hành, người học cần dùng counts từ endpoint thực tế; không ép kết quả phải trùng bảng.

### 12.1. Chuyển counts sang tỷ lệ

Với Random run 1:

| Instance | Count | Share |
| --- | ---: | ---: |
| A | 1.987 | 33,12% |
| B | 2.050 | 34,17% |
| C | 1.963 | 32,72% |
| **Tổng** | **6.000** | **100%** |

Tỷ lệ lý tưởng là **33,33%**, nhưng random được phép dao động quanh mức đó. Đây là biến động thống kê tự nhiên của các lựa chọn ngẫu nhiên, không phải dấu hiệu bắt buộc một instance đang có lỗi.

### 12.2. Tính max-min gap và relative gap

Ví dụ Random run 1:

\[
\operatorname{gap}=2050-1963=87
\]

\[
\operatorname{relativeGap}=\frac{87}{2000}\times100\%=4{,}35\%
\]

Round Robin có **gap=0** khi N=6000 chia hết 3 và tập instance ổn định. Với N không chia hết 3, gap tối đa 1 lần chọn trong chuỗi round-robin đơn giản.

### 12.3. Chỉ số công bằng Jain

\[
J=\frac{(\sum_{i=1}^{k}n_i)^2}
{k\sum_{i=1}^{k}n_i^2}
\]

Trong giả định counts không âm và có ít nhất một lượt:

- \(J=1\) nếu mọi count bằng nhau.
- \(J\) nhỏ hơn 1 khi phân phối lệch.
- Với k instance và toàn bộ lượt vào một instance, \(J=1/k\).

Áp dụng cho Random run 1:

\[
J=
\frac{6000^2}{3(1987^2+2050^2+1963^2)}
\approx0{,}99966
\]

Giá trị gần 1 cho thấy **số lượt request gần cân bằng**. Nó không nói gì trực tiếp về CPU/backend latency, vì một request có thể tiêu tốn ít hoặc rất nhiều tài nguyên.

### 12.4. Pearson chi-square

Với giả thuyết phân phối đều, \(E=6000/3=2000\):

\[
\chi^2=\sum_{i=1}^{3}\frac{(n_i-E)^2}{E}
=\frac{(-13)^2+50^2+(-37)^2}{2000}=2{,}019
\]

Với k=3 và mô hình chọn độc lập ngẫu nhiên, bậc tự do \(k-1=2\), ngưỡng chi-square 95% thường dùng là **xấp xỉ 5,991**. Kết quả 2,019 **không cho thấy bằng chứng mạnh chống lại phân phối đều** ở mức ý nghĩa 5% trong mô hình đó.

Nhưng:

1. Nếu một run random có chi-square > 5,991, điều đó **có thể xảy ra do may rủi** với xác suất khoảng 5% dưới giả thuyết đúng; không kết luận thuật toán bị hỏng sau một lần chạy.
2. Nếu Round Robin có chi-square=0 khi N chia hết k, đó là hệ quả **của thuật toán xác định**, không phải “randomness tốt hơn”.
3. Chi-square chỉ có ý nghĩa suy luận khi mô hình thử nghiệm phù hợp: cùng xác suất, danh sách instance cố định, events đủ độc lập và expected counts đủ lớn.
4. Nếu một instance lỗi nên không trả JSON, counts thành công bị **selection bias**. Khi đó phải đo **số lần chọn** hoặc HTTP attempts riêng.

## 13. Lặp nhiều runs thay vì dựa vào một ảnh chụp

Để so sánh ổn định, hãy chạy **ít nhất 10 runs** cho mỗi thuật toán, cùng N và điều kiện; có thể tăng lên 30 runs để thấy biến động giữa các lần.

Ví dụ PowerShell gọi endpoint đã chạy:

~~~powershell
$rows = @()
1..10 | ForEach-Object {
    $r = Invoke-RestMethod "http://127.0.0.1:8080/lab/run?n=6000&warmup=30"
    $rows += [PSCustomObject]@{
        run       = $_
        algorithm = $r.algorithm
        a         = $r.counts.'inventory-a'
        b         = $r.counts.'inventory-b'
        c         = $r.counts.'inventory-c'
        errors    = $r.failed
        jain      = $r.jainFairness
        chiSquare = $r.chiSquare
        p95Ms     = $r.p95Ms
    }
}
$rows | Format-Table -AutoSize
~~~

Nếu cần lưu kết quả **trong dự án thực hành riêng**, có thể dùng Export-Csv ở máy người học; **worker ở bước viết tài liệu không tạo CSV hay file thực nghiệm**.

### 13.1. Cách đọc nhiều runs

| Điều mong đợi | Round Robin | Random |
| --- | --- | --- |
| Count mỗi instance trong 6.000 requests | Gần 2.000 nếu pool/list cố định và các call thành công | Dao động quanh 2.000 |
| Độ lệch giữa runs | Rất nhỏ về counts (không tính thay đổi topology/lỗi) | Thay đổi tự nhiên |
| Chi-square khi danh sách cố định và N chia k | Có thể bằng 0 | Thường >0, dao động |
| Mean share qua nhiều runs | Gần 33,33% | Tiến gần 33,33% |
| P95/P99 latency | Phụ thuộc backend/network/pool | Phụ thuộc backend/network/pool |

**Không nên chọn một run random trùng 2000–2000–2000 rồi coi random tương đương Round Robin về quy luật.** Một kết quả nhất thời gần đều không làm một thuật toán ngẫu nhiên trở thành thuật toán luân phiên.

### 13.2. Cần restart Caller mỗi lần không?

**Để đổi thuật toán:** có, trong quy trình lab này để property và child context áp dụng chắc chắn.

**Để lặp cùng thuật toán:** có thể gọi /lab/run nhiều lần trong cùng process, nhưng các runs sau dùng connection pool/JIT/context đã ấm; điều đó tốt để so **steady-state**, không tốt nếu bạn đang đo **first-call cold start**.

Nếu nghiên cứu cold-start latency, mỗi run nên bắt đầu bằng một JVM/process mới và ghi startup riêng. Nếu nghiên cứu fairness chọn instance, không nhất thiết restart giữa mọi run.

## 14. So sánh theo các cỡ N khác nhau

Một bảng thực nghiệm nên có:

| N | Số instance k | Round Robin kỳ vọng | Random kỳ vọng |
| ---: | ---: | --- | --- |
| 30 | 3 | 10/10/10 (nếu ổn định) | Có thể lệch khá lớn |
| 300 | 3 | 100/100/100 | Dao động rõ |
| 3.000 | 3 | 1000/1000/1000 | Tỷ lệ thường gần 1/3 hơn |
| 6.000 | 3 | 2000/2000/2000 | Counts còn lệch vài chục |
| 30.000 | 3 | 10000/10000/10000 | Relative deviation thường thấp hơn |

Chạy mỗi giá trị N cho cả hai thuật toán. Ghi:

- counts và từng share;
- gap, relative gap, Jain, chi-square;
- error rate;
- P50/P95/P99;
- tổng elapsed time.

### 14.1. Đường hội tụ được giải thích như thế nào?

Nếu vẽ:

~~~text
Trục X: N = 30, 300, 3000, 6000, 30000
Trục Y: relative gap (%) hoặc |share_i - 1/k|
Mỗi màu: một thuật toán
~~~

thì đường random thường có xu hướng **giảm độ lệch tỷ lệ** khi N lớn, nhưng không nhất thiết giảm ở **mọi bước liên tiếp**. Một run N=6.000 vẫn có thể có relative gap lớn hơn run N=3.000 do biến động ngẫu nhiên.

Với Round Robin, khi N chia hết k, đường gap theo counts có thể bằng 0. Nếu vẫn cao, cần kiểm tra **failures, retry, changing list, shared caller traffic** trước khi đánh giá code chọn instance.

## 15. Concurrency: lượt chọn có thể đều nhưng thứ tự phản hồi không luân phiên

Trong pha cơ bản, ta gọi **tuần tự**. Tiếp theo, tạo **16 hoặc 64 concurrent workers** để xem khác biệt giữa **selection order** và **completion order**.

~~~text
Thời điểm chọn (Round Robin):
  request-1  -> A
  request-2  -> B
  request-3  -> C
  request-4  -> A
  request-5  -> B
  request-6  -> C

Thời điểm hoàn tất (do latency khác nhau):
  request-3  <- C
  request-2  <- B
  request-6  <- C
  request-1  <- A
  request-5  <- B
  request-4  <- A
~~~

**Round Robin bảo đảm quy luật về thứ tự chọn theo state của selector**, không bảo đảm **response về theo vòng A→B→C**. Concurrency, HTTP connection pool, TCP scheduling, backend latency và thread scheduling làm phản hồi đảo thứ tự.

### 15.1. Thiết kế concurrent test có thể tái lập

Thay vì gửi một loạt HTTP calls từ bên ngoài rồi đoán chúng đến theo thứ tự, trong project test hãy dùng:

- ExecutorService có fixed thread pool được cấu hình.
- CountDownLatch hoặc CyclicBarrier để cho worker bắt đầu gần đồng thời.
- ConcurrentHashMap/LongAdder để đếm responses theo instance.
- AtomicInteger để đếm failed attempts.
- **CompletionService hoặc CompletableFuture.allOf** để đợi đủ tất cả tasks.
- Timeout tổng để tránh test bị treo khi một backend chết.

Sau khi chạy, kiểm tra **tổng counts + errors = N logical calls**. Không ghi vào HashMap thường từ nhiều threads mà không đồng bộ. Nếu chỉ dùng endpoint /lab/run như mục 10 thì **một lần gọi endpoint vẫn chạy tuần tự**; gửi đồng thời nhiều request đến chính endpoint đó sẽ tạo **nhiều vòng run giao thoa**, không phải một run được định nghĩa rõ.

### 15.2. Vì sao vẫn có thể lệch khi concurrent?

Nếu cùng một RoundRobinLoadBalancer dùng atomic position và cả 3 instances ổn định, **tổng lựa chọn cuối cùng** vẫn gần đều. Nhưng:

- Một request timeout và không có response để count.
- Retry thêm attempts làm số lần chọn khác số logical calls.
- Nhiều callers có bộ đếm riêng.
- Các supplier có thể trả danh sách theo thứ tự/nội dung khác nhau.
- Request được hủy giữa choose và gửi HTTP.
- Một server chậm làm **in-flight concurrency** dồn nhiều hơn dù counts gán gần đều.

Vì vậy, với concurrency nên xem **LoadBalancer selection metrics + HTTP attempt metrics + backend success counts**, không chỉ một danh sách response JSON.

## 16. Thử nghiệm lỗi: tắt một Inventory instance giữa chừng

Sau khi baseline thành công, giữ cấu hình discovery tĩnh vẫn chứa A/B/C nhưng **dừng tiến trình inventory-b trên port 8092**.

~~~text
SimpleDiscoveryClient: [A, B, C]
A: UP
B: DOWN, port 8092 không còn listener
C: UP
~~~

### 16.1. Khi retry đã tắt

Trong pha này:

- Round Robin vẫn có thể **chọn B** sau mỗi vài lượt vì danh sách supplier vẫn chứa B.
- Lời gọi tới B có thể trả **connection refused**, không có JSON instanceId.
- Caller đếm B vào **errors**, không vào counts của response thành công.
- Các responses còn lại có thể đến A/C.

Ví dụ phân phối **giả định**, N=6000:

| Chỉ số | A | B | C | Tổng |
| --- | ---: | ---: | ---: | ---: |
| Lượt được chọn (nếu quan sát tại LB) | 2000 | 2000 | 2000 | 6000 |
| Success responses có instanceId | 2000 | 0 | 2000 | 4000 |
| Failed attempts do connect B | 0 | 2000 | 0 | 2000 |

Nếu chỉ xem count JSON của các responses thành công, bạn sẽ thấy **A/C cân bằng 50/50** và B=0. Kết quả đó không chứng minh LoadBalancer đã nhận biết B chết, bởi **selection vẫn có thể đều giữa ba instance**.

### 16.2. Thêm HealthCheckServiceInstanceListSupplier thì sao?

Nếu thiết kế supplier có health check và B bị loại khỏi tập ứng viên sau khi poll, danh sách có thể trở thành:

~~~text
[A, C]
~~~

Lúc ấy Round Robin sẽ luân phiên giữa A/C thay vì A/B/C. Nhưng quá trình loại bỏ phụ thuộc **poll interval, initial delay, health endpoint, cache, tính nhất quán discovery và supplier ordering**. Đừng giả định chỉ vì HTTP connection refused một lần mà Spring Cloud LoadBalancer ngay lập tức tự loại instance.

Khi danh sách chỉ còn A/C, kỳ vọng cho một run mới N=6000 (sau khi snapshot đã ổn định) là xấp xỉ:

~~~text
Round Robin: A=3000, C=3000
Random:      A≈3000, C≈3000, có dao động
~~~

**Đây là một thí nghiệm khác**: k thay từ 3 thành 2. Không so chi-square của run k=2 với bảng kỳ vọng k=3 mà không điều chỉnh.

### 16.3. Không dùng round-robin để thay health check

Round Robin đơn thuần **không phải công cụ phát hiện backend chết**. Nó chỉ chọn từ **danh sách được cấp**. Nếu danh sách vẫn có B, thuật toán vẫn có thể chọn B; cách loại B đúng là discovery/health supplier hoặc retry/failure policy được thiết kế phù hợp.

## 17. Bật retry: đếm logical calls, attempts và backend successes riêng

Sau khi hiểu failure case, thử một cấu hình retry **có giới hạn** (chỉ trong môi trường test) để thấy tác động của retry lên phân phối.

Ví dụ chính sách minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
~~~

**Không suy diễn** đoạn YAML này đủ bật retry cho mọi client/release train: blocking RestTemplate có thể cần Spring Retry trên classpath; RestClient, WebClient và Feign có những đường tích hợp riêng. Phải xác minh retry thật bằng backend request count và logs.

### 17.1. Ví dụ retry làm phép đếm trở nên khác

~~~text
Logical request #42:

Attempt 1: LB chọn B -> connection refused
Attempt 2: LB chọn C -> HTTP 200

Logical calls         = 1
LoadBalancer attempts = 2 (nếu mỗi retry chọn lại)
Backend HTTP receives = 1 ở C (B có thể không nhận HTTP request vì connect fail)
Success responses     = 1 ở C
~~~

Do đó:

~~~text
Một logical call có thể dẫn đến nhiều LB selections.
Một selection có thể không dẫn đến một HTTP request được backend nhận.
Một backend có thể xử lý request nhưng caller timeout trước khi nhận response.
~~~

Nếu đem N=6000 logical calls sau retry đối chiếu trực tiếp với kỳ vọng **2000/instance cho selections**, phép đo sai mẫu số. Cần:

1. Đếm **logical calls** tại caller.
2. Đếm **HTTP attempts** tại client/transport.
3. Ghi **selected instance** của mỗi attempt qua LoadBalancer lifecycle hoặc instrumentation tương ứng.
4. Đếm **requests server thực nhận** và **success responses**.
5. So tỷ lệ đúng loại dữ liệu với mẫu số tương ứng.

### 17.2. Retry có thể không chọn instance khác

Ngay cả khi policy là retry-on-next-service-instance:

- Nếu chỉ có một instance, không còn lựa chọn thay thế.
- Supplier có thể trả danh sách thay đổi giữa attempts.
- Retry context có thể không được truyền đúng cho một HTTP integration.
- Một fallback/zone preference có thể chỉ giữ ứng viên cũ.

Vì vậy, bài test phải ghi **instance được chọn trên attempt 1 và attempt 2**, thay vì tuyên bố “retry chắc chắn là failover”.

### 17.3. Lỗi có side effect

Pha baseline sử dụng GET an toàn. Nếu mở rộng sang POST /reservations, **client timeout không chứng minh backend chưa commit**; retry có thể nhân đôi giao dịch. Cần **idempotency key** và cơ chế deduplicate phía server. Đừng dùng POST nghiệp vụ làm dữ liệu đầu vào cho benchmark phân phối đơn giản.

## 18. Danh sách instance thay đổi: không còn giả định vòng trên tập cố định

Trong môi trường thật, ServiceInstanceListSupplier có thể cập nhật danh sách sau:

- Scale-out hoặc scale-in.
- Registry đánh dấu instance DOWN/UP.
- Health check đánh giá lại.
- Zone/hint filter tạo tập con khác.
- Cache TTL hết và lấy discovery snapshot mới.
- Cấu hình canary/metadata/weight được rollout.

Ví dụ:

~~~text
Request 1..3000: supplier = [A, B, C]
Request 3001..6000: supplier = [A, C, D, E]
~~~

Ta không thể chia N=6000 cho một k cố định để dự đoán counts toàn run. Một cách phân tích đúng hơn:

1. **Gắn mốc thời gian của mỗi discovery/supplier snapshot**.
2. Chia run thành các **epochs** mà danh sách ứng viên tương đối ổn định.
3. Tính kỳ vọng riêng cho từng epoch.
4. Tổng hợp số lượt kỳ vọng của từng instance theo thời gian nó thực sự eligible.

Ví dụ A/C xuất hiện trong cả hai epochs, B chỉ epoch 1 và D/E chỉ epoch 2. A/C có thể có counts nhiều hơn B/D/E **không phải do thuật toán thiên vị**, mà vì **thời gian đủ điều kiện khác nhau**.

### 18.1. Zone preference có thể làm k khác dự kiến

Giả sử Caller ở zone-a, supplier ưu tiên [A, B] và chỉ fallback ra [C] khi không còn instance same-zone. Khi đó dù registry có 3 bản sao, tập **eligible** của mỗi lựa chọn có thể chỉ là 2.

Không được kết luận Random có vấn đề vì C nhận 0 request. Trước tiên kiểm tra:

~~~text
Discovery list      = [A, B, C]
Filtered list       = [A, B]
Selected instances  = A hoặc B
~~~

Mọi công thức fairness trong bài phải tính **trên tập ứng viên của policy thực**, không phải mọi process đang chạy.

### 18.2. Weighted selection là một bài toán khác

Nếu weight của A/B/C lần lượt là 5/3/2, kỳ vọng đúng không còn là 1/3 mỗi instance. Khi đó dùng:

\[
p_A=0{,}5,\quad p_B=0{,}3,\quad p_C=0{,}2
\]

và expected counts là \(N p_i\). Đừng áp bài kiểm tra chia đều Round Robin/Random lên một pipeline có **WeightedServiceInstanceListSupplier** hoặc policy cân trọng số khác mà không điều chỉnh kỳ vọng.

Mục tiêu bài lab hiện tại là **phân biệt thuật toán chọn từ danh sách equal-weight**, không phải đo weighted load balancing.

## 19. Fairness theo lượt không bảo đảm latency tốt hơn

Giả sử ba backend cùng nhận khoảng 2000 requests:

| Instance | Thời gian xử lý trung bình giả định |
| --- | ---: |
| A | 15 ms |
| B | 150 ms |
| C | 20 ms |

Round Robin vẫn phân phối gần 1/3 số lượt, nhưng B xử lý chậm hơn nhiều; P95 của toàn hệ thống có thể chịu ảnh hưởng lớn vì khoảng 1/3 requests phải qua B.

Random cũng chọn B khoảng 1/3 theo kỳ vọng, nhưng sẽ có các cụm request ngẫu nhiên đến B. Một thuật toán có hiểu biết về **latency, outstanding requests, CPU, weight hoặc health** có thể mang lại phân phối tải phù hợp hơn. Tuy nhiên, đó là **chính sách tùy chỉnh khác**, không phải bằng chứng Round Robin/Random luôn tệ.

### 19.1. Không đánh giá chỉ bằng total elapsed của sequential test

Với N calls tuần tự:

\[
T_{\text{total}} \approx \sum_{i=1}^{N}T_i
\]

Throughput gần \(N/T_{\text{total}}\) phụ thuộc rất lớn vào **network RTT và backend response time**. Chênh lệch vài microseconds trong thuật toán chọn có thể bị che hoàn toàn bởi HTTP.

Muốn đo **chi phí riêng của thuật toán**, phải benchmark phần choose() với cùng ServiceInstanceListSupplier, không tạo HTTP socket, và cân nhắc JVM warm-up/JMH. Nhưng mục tiêu bài này là **phân phối HTTP thực**, không phải microbenchmark choose().

### 19.2. P95/P99 có thể bị ảnh hưởng bởi connection pool

Ngay cả khi API /whoami rất nhẹ:

- Cold connection tạo DNS/TCP/TLS overhead.
- Keep-alive reuse giảm latency cho các request sau.
- Pool acquire queue có thể dài khi concurrency tăng.
- HTTP/2 multiplex thay đổi quan hệ giữa connection và request.
- GC, JIT, OS scheduling và server-side thread pool tác động elapsed time.

Vì vậy, khi report rằng Random có P95 cao hơn Round Robin trong một run, cần ghi rõ **HTTP engine, pool config, concurrent load, warm-up và error rate**. Không biến chênh lệch một lần thành kết luận tổng quát về thuật toán.

## 20. Kiểm thử tự động: kiểm chứng chức năng và thống kê là hai việc khác nhau

Một test có thể kiểm tra **code hoạt động đúng** mà không cần ép Random cho counts chính xác 1/3. Nên chia thành ba cấp:

| Cấp | Mục tiêu | Cách xác minh |
| --- | --- | --- |
| Unit test thuật toán/supplier | Round Robin và Random chọn trong tập ứng viên hợp lệ | Fixed ServiceInstanceListSupplier, gọi choose() |
| Integration test HTTP | URI service ID được rewrite đến instance thật | MockWebServer/WireMock, recorded requests |
| Performance/statistical experiment | Phân phối ở N lớn, P95/P99 và biến động | Chạy lặp nhiều lần, báo counts/CI/metrics |

**Không dùng một statistical threshold ngẫu nhiên làm assertion cứng duy nhất trong CI.** Nếu random thật sự được triển khai đúng, một mẫu ngắn vẫn có thể lệch đáng kể theo xác suất và làm test flaky.

### 20.1. Một bộ acceptance tests cho baseline

| Test | Chuẩn bị | Assertion |
| --- | --- | --- |
| Service ID lookup | Cả A/B/C đang hoạt động | Không DNS lookup inventory-service như host vật lý; backend nhận request |
| Round Robin 600 lần | 3 fixed instances, retry off | Counts thành công bằng 200/200/200 nếu không có traffic khác |
| Round Robin 601 lần | Cùng list/context điều khiển | Counts có dạng 201/200/200, không yêu cầu instance nào được thêm |
| Random 600 lần | 3 fixed instances, retry off | Tổng counts=600, mọi instanceId thuộc tập hợp hợp lệ |
| Random N lớn | 6.000+ requests, chạy lặp | Báo distribution, không assert cứng luôn bằng nhau |
| No instance | Supplier rỗng | Không có HTTP backend requests; caller nhận no-instance error |
| One instance down | B dừng nhưng vẫn trong list | Failures được ghi nhận, không gộp mất |
| Retry enabled | Giới hạn attempts rõ | Backend attempt count và logical success được đo riêng |
| Concurrency | Worker count cố định | Tổng successes+errors=N, counts thread-safe |
| Zone/hint filter | Tập ứng viên chỉ còn A/B | Không kỳ vọng C nhận 1/3 |

### 20.2. Vì sao test 600 lần với Round Robin có thể kiểm tra đúng?

Với **một selector state**, supplier luôn trả [A,B,C] theo cùng thứ tự, retry tắt, không có external requests và cả 600 responses thành công, vòng chọn sẽ hoàn tất đúng 200 chu kỳ. **Điều kiện quan trọng là số lần chọn bằng 600**.

Nếu có thêm warm-up 30 lần trước test, vì 30 chia hết 3, counts trong pha đo vẫn cân. Nếu warm-up 1 lần hoặc bộ đếm bắt đầu ở vị trí khác, **counts vẫn bằng nhau** khi N chia hết 3. Nhưng thứ tự **A/B/C của ba requests đầu** có thể khác.

### 20.3. Không dùng một random test kiểm định sai giả thuyết

Ví dụ assertion dễ flaky:

~~~java
assertEquals(200, counts.get("inventory-a")); // Sai cho Random.
assertEquals(200, counts.get("inventory-b"));
assertEquals(200, counts.get("inventory-c"));
~~~

Một random implementation đúng có xác suất rất thấp tạo **đúng số tuyệt đối** sau N requests. Cách kiểm chứng:

~~~java
// controller được inject trong integration test có ba backend đang chạy.
ExperimentController.RunReport report = controller.run(600, 30);

assertEquals(0, report.failed());
assertEquals(600, report.succeeded());
assertEquals(600, report.counts().values()
        .stream().mapToInt(Integer::intValue).sum());
~~~

Các assertions này **chưa chứng minh thuật toán đã chọn đều**. Vì vậy, cần thêm nhiều runs và thống kê riêng ngoài CI cứng; hoặc test RandomLoadBalancer bằng cách inject/khoanh vùng nguồn ngẫu nhiên **khi API của implementation cho phép**, không sửa code production chỉ để đạt một phân phối cố định.

### 20.4. Unit test không thay integration test

Mock trực tiếp **ReactorLoadBalancer.choose()** có thể chứng minh thuật toán chọn đúng một instance, nhưng chưa kiểm tra **RestClient có @LoadBalanced**, Request URL được rewrite hay backend nhận request thật. Ngược lại, một integration test HTTP thành công chỉ cho biết request đến backend, chưa chắc policy đang là Random chứ không phải Round Robin.

Một bộ test tốt có cả:

~~~text
Algorithm config test
  -> Bean type là RoundRobinLoadBalancer hoặc RandomLoadBalancer

HTTP integration test
  -> GET /whoami qua service ID
  -> selected backend/URI vật lý có thật

Statistical experiment
  -> phân phối qua N lớn
  -> báo số liệu và mô hình xác suất
~~~

## 21. Observability: đo điều gì khi kết quả không như mong đợi?

Spring Cloud LoadBalancer có hỗ trợ **MicrometerStatsLoadBalancerLifecycle**; có thể bật:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

Khi có Micrometer **MeterRegistry** (ví dụ qua Spring Boot Actuator) và tích hợp phù hợp, tài liệu Spring Cloud liệt kê các meters:

| Meter | Nội dung |
| --- | --- |
| loadbalancer.requests.active | Gauge số request đang active theo thông tin instance |
| loadbalancer.requests.success | Timer requests load-balanced kết thúc thành công theo lifecycle |
| loadbalancer.requests.failed | Timer requests kết thúc bằng exception |
| loadbalancer.requests.discard | Counter request bị bỏ vì không chọn được ServiceInstance |

**Chúng không mặc định cho bạn chính xác một histogram “choose count” độc lập khỏi HTTP response.** Trước khi dựa vào meter, cần xác minh semantics của phiên bản đang dùng, tags khả dụng và request đã qua instrumentation.

### 21.1. Tránh cardinality quá cao

Không gắn vào metrics:

- SKU thực, order ID, customer ID.
- Full URL chứa query parameters động.
- Trace ID, request ID.
- Instance ID thay đổi quá nhanh hoặc host/port vô hạn.

Tài liệu Spring Cloud LoadBalancer có cảnh báo về tag **uri** ở RestTemplate và hướng dẫn **spring.cloud.loadbalancer.stats.include-path=false** để giảm high-cardinality path khi cần. Dùng **URI template**, service ID và operation name ổn định để đo tổng.

Nếu muốn xem instance ID cụ thể, dùng **sampled tracing/logs** có quyền truy cập hạn chế, tránh biến hàng chục nghìn instances thành metric tags không kiểm soát.

### 21.2. Một event trace minh họa

~~~text
trace=trace-091, logicalService=inventory-service
algorithm=round-robin, attempt=1
selected=inventory-b, physicalHost=127.0.0.1:8092
httpStatus=200, backendInstanceId=inventory-b
elapsedMs=24.8
~~~

Khi có timeout:

~~~text
trace=trace-092, logicalService=inventory-service
algorithm=random, attempt=1
selected=inventory-c, error=read_timeout
backendResponseObserved=false
elapsedMs=1000
~~~

Đây là **mẫu log do ứng dụng tự thiết kế**, không phải output mặc định của Spring Cloud. Thông tin **selected** phải lấy từ đúng request context hoặc lifecycle, không lấy instance được chọn ở một request trước đó.

## 22. Troubleshooting: vì sao số liệu không như dự đoán?

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| Cả hai mode đều giống Round Robin | @ConditionalOnProperty không áp dụng trong child context hoặc Random bean không được tạo | Xác minh bean type trong LB context, property lúc startup |
| Chỉ gọi được một server | SimpleDiscoveryClient sai YAML hoặc filter chỉ giữ một instance | Kiểm tra danh sách supplier |
| UnknownHostException inventory-service | Client không có @LoadBalanced integration | Dùng builder bean đã @LoadBalanced |
| RR count không cân | Có lỗi/timeout, retries, traffic từ request khác, danh sách đổi | Tách choose attempts và successes |
| Request đầu luôn B thay vì A | State/seed hoặc warm-up đã chạy trước | Không assert lượt đầu phải A |
| Random ra 60/20/20 sau 10 request | Mẫu quá nhỏ | Chạy 6.000+ và nhiều runs |
| Random lệch sau 6.000 requests | Biến động tự nhiên hoặc list/policy không đều | Chi-square qua nhiều runs, xem instance list |
| Chi-square rất cao liên tục | Weighted/zone/hint, bug config hoặc lỗi tập trung | Kiểm tra eligible set và response failures |
| Random count chính xác 2.000/2.000/2.000 một lần | Có thể xảy ra do may rủi hoặc đang dùng RR | Xác minh bean type, lặp runs |
| RR đều nhưng CPU B cao | B xử lý chậm/hardware khác | Đo CPU, in-flight, backend latency |
| P99 biến động lớn | JIT/GC, cold sockets, pool, scheduling | Warm-up, metrics và lặp thí nghiệm |
| Lỗi 503 từ caller, backend không thấy request | No instances hoặc gateway | Kiểm tra discovery và lifecycle |
| Backend A nhận requests nhưng caller count A=0 | Response body lỗi, client timeout, parser mismatch | So HTTP recorded requests với successes |
| Retry làm tổng attempts > N | Policy gửi nhiều lần | Tắt retry ở baseline, đo attempts riêng |
| Thứ tự responses không A→B→C | Concurrency hoặc latency không đồng nhất | So selection events thay vì completion order |
| Khác biệt giữa hai callers | RoundRobin state per caller/context | Tách kết quả theo caller instance |
| Kết quả khác khi đổi N | N không chia hết k hoặc random noise | Dùng công thức floor/ceil, kỳ vọng xác suất |
| Sau scale-out fairness “lệch” | Instances mới chỉ eligible một phần run | Chia epochs theo snapshot |

### 22.1. Hướng debug có thứ tự

~~~text
1. Cả ba Inventory ports còn nghe HTTP không?
2. Mỗi port có đúng instanceId không?
3. Caller có đúng @LoadBalanced RestClient.Builder không?
4. SimpleDiscoveryClient đang trả đúng [A,B,C] không?
5. Child context của inventory-service dùng đúng algorithm bean không?
6. Có zone/health/hint/weight supplier thay đổi tập ứng viên không?
7. N logical requests có bằng số selections và HTTP attempts không?
8. failed/errorsByType có bằng 0 không?
9. Có caller khác cùng service ID chen vào run không?
10. Dữ liệu đang đo selections, backend receives hay successful responses?
~~~

Chỉ sau khi trả lời đủ mới so sánh **chi-square hoặc Jain index**. Một biểu đồ đẹp dựa trên mẫu số sai sẽ tạo ra kết luận sai.

## 23. Viết báo cáo kết quả thay vì chỉ chụp màn hình

Một báo cáo kỹ thuật cho thí nghiệm nên có ít nhất:

**A. Điều kiện chạy**

~~~text
Spring Boot / Spring Cloud release train:
Java version:
HTTP client / request factory:
Service ID:
Số instance và port:
Danh sách ServiceInstanceListSupplier:
LB algorithm thực sự được tạo:
N (measured):
Warm-up requests:
Concurrency:
Retry policy:
Timeout:
Zone/hint/health filters:
Số lần lặp:
~~~

**B. Dữ liệu quan sát**

| Run | Thuật toán | N | Success | Failed | A | B | C | Jain | Chi-square | P95 (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Round Robin | 6000 | 6000 | 0 | 2000 | 2000 | 2000 | 1,0000 | 0,000 | ... |
| 2 | Random | 6000 | 6000 | 0 | 1987 | 2050 | 1963 | 0,9997 | 2,019 | ... |
| 3 | Random | 6000 | 6000 | 0 | ... | ... | ... | ... | ... | ... |

**Các số liệu trên chỉ là minh họa**, không phải kết quả đã chạy. P95 để trống vì không có đo thực; không tự tạo latency cho báo cáo.

**C. Diễn giải**

Ví dụ diễn giải phù hợp:

> Trong điều kiện một caller, ba instances giống nhau, không retry và không thay đổi danh sách, Round Robin chia đều gần tuyệt đối số lượt theo vòng. Random tạo dao động quanh xác suất 1/3; khi tăng N, độ lệch tương đối thường giảm. Vì cả hai cùng dùng RestClient và ba backend, thí nghiệm này **chưa đủ bằng chứng** để kết luận thuật toán nào có P99 latency thấp hơn trong production.

**D. Giới hạn và bước tiếp theo**

Nêu rõ các giới hạn: local loopback, one caller, no real registry, HTTP không TLS, backend đồng nhất, request nhỏ, không có traffic production, thiếu thay đổi topology. Đề xuất thí nghiệm concurrent/failure/health/weight riêng, tránh trộn dữ liệu của nhiều cấu hình vào một kết luận.

### 23.1. Một bản báo cáo tốt không “sửa” số liệu random

Không:

~~~text
Random A=1987, B=2050, C=1963
=> Chỉnh bảng thành 2000/2000/2000 để biểu đồ đẹp.
~~~

Có:

~~~text
Random observed counts: 1987/2050/1963
Expected counts:        2000/2000/2000
Absolute deviations:    -13/+50/-37
Chi-square:             2.019
Relative gap:           4.35%
~~~

Sự chênh lệch chính là **thông tin khoa học** của thuật toán ngẫu nhiên; xóa nó là xóa mục tiêu thí nghiệm.

## 24. Bài tập mở rộng có gợi ý

### 24.1. N không chia hết cho số instance

**Đề:** Chạy 6.001 requests bằng Round Robin với ba instances cố định, không retry, không lỗi. Kỳ vọng counts như thế nào?

**Gợi ý:** \(\lfloor6001/3\rfloor=2000\), \(\lceil6001/3\rceil=2001\). Do đó một instance có 2.001 lượt, hai instances còn lại có 2.000; **không yêu cầu A nhất định có 2.001**.

### 24.2. Phân phối random sau 300 requests

**Đề:** Random cho counts A=115, B=88, C=97. Có nên kết luận implementation sai?

**Gợi ý:** Tổng=300 và expected mỗi instance=100, nhưng mẫu còn nhỏ. Tính chi-square:

\[
\chi^2=\frac{(115-100)^2+(88-100)^2+(97-100)^2}{100}
=3{,}78
\]

Với bậc tự do 2, giá trị này nhỏ hơn ngưỡng 5,991 ở mức 5%. Chưa đủ bằng chứng để bác bỏ phân phối đều ở mức đó. Dù vậy, đây chỉ là **một phép kiểm tra của một run**; cần lặp lại và bảo đảm tập instance không đổi.

### 24.3. Một instance chậm hơn 10 lần

**Đề:** A/B/C đều nhận 2.000 requests, nhưng B xử lý trung bình 200 ms còn A/C là 20 ms.

**Gợi ý:** Jain theo **số lượt** vẫn là 1, nhưng Jain theo **tài nguyên** (nếu đo đúng) có thể khác. Round Robin không đo outstanding requests/latency để tránh B. Cần benchmark theo tải và xem xét weighted/adaptive policy phù hợp.

### 24.4. Hai caller pods

**Đề:** Caller-1 gửi 3.001 requests; Caller-2 gửi 2.999 requests. Hai pods có RoundRobinLoadBalancer state riêng. Có thể dự đoán chính xác toàn cụm 2.000 lượt mỗi instance không?

**Gợi ý:** Mỗi pod phân phối gần đều, nhưng **vị trí bắt đầu không được đồng bộ**. Tổng count toàn cụm có thể chênh một vài lượt, không có chuỗi toàn cục A→B→C. Đừng kỳ vọng một counter chung giữa hai JVMs.

### 24.5. Dừng inventory-b nhưng không refresh discovery

**Đề:** Round Robin có còn chọn B không?

**Gợi ý:** Có thể có nếu SimpleDiscoveryClient vẫn chứa B. Thuật toán chọn không tự loại instance theo một connection error; cần health/discovery/retry chính sách riêng. Phân tích **selection count** và **success count** tách biệt.

### 24.6. Random và ngưỡng chi-square

**Đề:** Trong 20 runs random độc lập, một run có chi-square >5,991. Có nhất thiết là bug?

**Gợi ý:** Không. Với kiểm định mức 5%, khả năng có ít nhất một báo động giả trên 20 runs độc lập vào khoảng:

\[
1-(1-0{,}05)^{20}\approx64\%
\]

Nếu liên tục thấy độ lệch lớn, phải kiểm tra list/weight/filter và lỗi, đồng thời xem xét kiểm định thống kê có điều chỉnh **multiple testing**. Không dùng một threshold như nút báo động production duy nhất.

### 24.7. Chạy WebClient thay RestClient

**Đề:** Viết một phiên bản reactive của /lab/run với WebClient.

**Gợi ý:** Dùng **@LoadBalanced WebClient.Builder** và một pipeline có độ đồng thời kiểm soát:

~~~java
Flux.range(0, n)
        .flatMap(i -> webClient.get()
                .uri("http://inventory-service/whoami")
                .retrieve()
                .bodyToMono(InstanceReply.class),
                16);
~~~

Nếu cần tất cả N responses, nên thu **counts bằng collector thread-safe** hoặc dùng collectList()/groupBy() phù hợp với bộ nhớ; đặt timeout và xử lý errors để không dừng cả run không rõ lý do.

**Khác biệt quan trọng:** flatMap concurrency 16 thay đổi tính chất workload so với RestClient tuần tự. Đừng dùng P95/throughput của hai run để quy toàn bộ chênh lệch cho Round Robin/Random.

### 24.8. Cần chứng minh thuật toán thật chứ không chỉ label

**Đề:** Người học đổi lab.algorithm=random nhưng counts vẫn chính xác 2000/2000/2000 ở cả mười runs.

**Gợi ý:** Điều đó đáng kiểm tra nhưng chưa tự chứng minh bug. Hãy xem **bean implementation** của child LoadBalancer context, logs/config và cách @ConditionalOnProperty được xử lý; đảm bảo không có một fixed supplier/selector khác override. Không dùng tên trả về trong RunReport như bằng chứng đủ mạnh.

## 25. Checklist nghiệm thu bài thực hành

- [ ] Hai subprojects Inventory và Caller dùng BOM Spring Boot–Spring Cloud tương thích.
- [ ] Đã xác nhận ba backend 8091/8092/8093 trả đúng instanceId.
- [ ] Chỉ có một SimpleDiscoveryClient source cho inventory-service trong baseline.
- [ ] Caller dùng **@LoadBalanced RestClient.Builder**, URI là service ID.
- [ ] Random và Round Robin được đăng ký ở **child LoadBalancer context**, không vào parent scan ngoài ý muốn.
- [ ] Đã xác minh implementation bean thực sự khớp property, không chỉ đọc nhãn algorithm.
- [ ] Không bật health/zone/hint/weighted filters ở pha baseline.
- [ ] Tắt retry, giữ HTTP client/transport tương đương giữa hai arms.
- [ ] N được cố định, ví dụ 6.000; các runs đều có warm-up bằng nhau.
- [ ] Đã kiểm tra **requested = successes + failed**.
- [ ] Với failed=0, tổng counts A/B/C đúng N.
- [ ] Đo Round Robin counts, share, max-min gap và relative gap.
- [ ] Đo Random counts, Jain fairness, chi-square và biến động nhiều runs.
- [ ] Không assert Random phải chia chính xác bằng nhau.
- [ ] Không assert response completion order phải A→B→C.
- [ ] Không kết luận thuật toán nhanh hơn chỉ từ một P95 của một run.
- [ ] Đã ghi HTTP engine, timeout, pool, concurrency và môi trường chạy.
- [ ] Có thí nghiệm khác với N nhỏ/vừa/lớn.
- [ ] Có kiểm thử một backend chết, phân biệt selection và success counts.
- [ ] Có kiểm thử retry chọn lại instance, đếm attempts riêng.
- [ ] Có kiểm thử changing list/health/zone và điều chỉnh k theo tập eligible.
- [ ] Có unit test cho cấu hình thuật toán và integration test HTTP thật.
- [ ] Không tạo side effect hay bắn hàng nghìn requests vào production.
- [ ] Có báo cáo bảng dữ liệu thật, công thức, diễn giải và giới hạn.
- [ ] Không dùng metric tags chứa SKU/customer ID hoặc trace ID cardinality cao.

## 26. Kết luận

Trong điều kiện **cùng tập ServiceInstance ổn định, một caller, không retry, không lỗi**, hai thuật toán có đặc tính rõ ràng:

- **Round Robin** đi theo vị trí vòng, cho counts gần như bằng nhau; nếu N chia hết k, số lượt chọn từng instance bằng nhau trong mô hình chọn tuần tự.
- **Random** chọn ngẫu nhiên theo xác suất, counts dao động quanh \(N/k\). N càng lớn, **độ lệch tỷ lệ thường càng nhỏ**, nhưng không buộc counts bằng nhau.

Tuy nhiên, thuật toán chỉ là **một phần** của giao tiếp client-side load balancing. Khi có retry, health check, zone preference, cache/discovery thay đổi, concurrency, nhiều caller pods, timeout và connection pool, cần tách:

~~~text
logical calls
    -> ServiceInstance selections
    -> HTTP transport attempts
    -> backend received requests
    -> completed successful responses
~~~

Chỉ khi chọn đúng **mẫu số**, cố định biến nhiễu và có nhiều lần đo, so sánh Round Robin với Random mới có ý nghĩa. Kết quả bài lab giúp người học hiểu tính chất thuật toán; lựa chọn tối ưu production còn cần **SLO latency, capacity, reliability, routing policy và observability**.

## 27. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): thuật toán Round Robin mặc định, Random, custom configuration và ServiceInstanceListSupplier.
- [Spring Cloud LoadBalancer – Switching between the load-balancing algorithms](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#switching-between-the-load-balancing-algorithms): ví dụ cấu hình RandomLoadBalancer qua @LoadBalancerClient.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): SimpleDiscoveryClient và @LoadBalanced RestClient.Builder.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): retry, cache, health, stats và property theo client.
- [Spring Cloud LoadBalancer – Statistics](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#spring-cloud-loadbalancer-statistics): MicrometerStatsLoadBalancerLifecycle và request meters.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, exception handling và ClientHttpRequestFactory.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient và cách thực thi reactive requests.
- [Spring Boot – REST Clients](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClient.Builder và cấu hình HTTP transport trong Boot.
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): SpringBootTest và test configuration.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, Publisher subscription và kiểm thử reactive.
- [NIST Engineering Statistics Handbook – Chi-Square Goodness-of-Fit](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35f.htm): cơ sở và giới hạn kiểm định chi-square.
- [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): timer/counter, histogram và percentile metrics.

