# Same-instance preference và phạm vi trạng thái của bên gọi

Trong Spring Cloud LoadBalancer, một **bên gọi** (caller) có thể gửi hàng nghìn HTTP request tới cùng service ID như `inventory-service`. Với Round Robin, mỗi lần chọn đích thường chuyển sang một bản sao tiếp theo trong danh sách; với Random, bộ chọn lấy ngẫu nhiên một bản sao. Nhưng đôi khi ta muốn bên gọi **ưu tiên bản sao vừa được chọn ở lượt trước** thay vì phân phối luân phiên cho mọi lượt.

Spring Cloud hỗ trợ cơ chế này qua `SameInstancePreferenceServiceInstanceListSupplier`. Từ khóa ở đây là **preference**: supplier ưu tiên instance đã được chọn trước đó **nếu instance đó vẫn nằm trong tập ứng viên khả dụng**, không phải bảo đảm rằng mọi người dùng hoặc mọi request sẽ luôn tới cùng một máy.

Điểm quan trọng nhất của bài là **phạm vi trạng thái**. Lựa chọn gần nhất được giữ trong một đối tượng supplier của LoadBalancer ở phía caller, thường thuộc context riêng của **service ID đích** và một **tiến trình ứng dụng caller**. Nó không phải session của người dùng, không được tự đồng bộ giữa các replica caller và cũng không được lưu bền qua lần khởi động lại ứng dụng.

## 1. Vấn đề: caller muốn ưu tiên instance quen thuộc

Giả sử có hệ thống:

- `checkout-service`: dịch vụ gọi các API trong quá trình xử lý thanh toán.
- `inventory-service`: dịch vụ kiểm tra tồn kho, chạy ba bản sao A, B và C.
- `payment-service`: dịch vụ thu tiền, chạy hai bản sao D và E.

Caller dùng địa chỉ logic:

~~~text
http://inventory-service/api/stock/SKU-42
http://payment-service/api/authorize
~~~

Discovery cung cấp danh sách `ServiceInstance` cho từng service ID. Khi không bật Same-instance preference, thuật toán thường dùng là Round Robin, lần lượt chọn các bản sao ở những request kế tiếp. Khi bật ưu tiên instance trước đó **chỉ cho inventory**, các lời gọi tới inventory có xu hướng tiếp tục ở bản sao đã chọn lần gần nhất, miễn bản sao đó còn xuất hiện trong danh sách đầu vào.

~~~mermaid
flowchart LR
    U["checkout-service<br/>caller instance 1"] --> L["Spring Cloud LoadBalancer<br/>service ID: inventory-service"]
    D["Discovery / supplier<br/>A, B, C"] --> L
    L --> P["SameInstancePreference<br/>nhớ instance gần nhất"]
    P --> A["Inventory A"]
    P -.-> B["Inventory B"]
    P -.-> C["Inventory C"]
~~~

Sơ đồ chỉ diễn tả ba lựa chọn có thể; **mỗi lần chọn** đưa ra một instance được dùng làm đích. Một số mục tiêu có thể khiến cơ chế này hữu ích: tăng xác suất tái sử dụng dữ liệu đã làm nóng ở cache cục bộ của backend, giảm chuyển đổi backend liên tục hoặc tái hiện hành vi của các hệ thống từng dùng chính sách `StickyRule` trong Zookeeper.

Tuy nhiên, ưu tiên lại cùng backend có thể khiến phân phối tải **lệch mạnh**. Nếu một caller hoạt động liên tục và backend cũ luôn còn trong danh sách, nhiều request của caller đó có thể cùng đi về một bản sao. Đó là hệ quả chủ ý, không phải lỗi Round Robin.

## 2. Supplier thực hiện preference như thế nào?

`SameInstancePreferenceServiceInstanceListSupplier` là một **ServiceInstanceListSupplier decorator**, không phải một thuật toán thay thế `RoundRobinLoadBalancer` hay `RandomLoadBalancer`. Nó lấy danh sách instance từ một supplier khác, sau đó điều chỉnh danh sách được đưa cho bộ chọn.

Một vòng đời đơn giản:

1. Caller gửi request đầu tiên đến service ID `inventory-service`.
2. Supplier chưa nhớ instance nào nên trả về danh sách ứng viên như `[A, B, C]`.
3. LoadBalancer chọn một instance, chẳng hạn B.
4. Cơ chế callback lựa chọn (giao diện `SelectedInstanceCallback`) thông báo cho supplier biết B đã được chọn.
5. Ở request kế tiếp, nếu B vẫn thuộc danh sách hiện tại, preference supplier ưu tiên B; kết quả lựa chọn thường tiếp tục là B.
6. Nếu B không còn được cung cấp, supplier trả về các ứng viên còn lại để LoadBalancer chọn lại; instance mới được chọn sẽ trở thành lựa chọn ưu tiên cho các lượt sau.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant L as LoadBalancer
    participant P as SameInstancePreference supplier
    participant D as Discovery supplier
    participant B as inventory B

    C->>L: Request 1: inventory-service
    L->>P: Lấy danh sách ứng viên
    P->>D: get instances
    D-->>P: [A, B, C]
    P-->>L: [A, B, C] (chưa có lịch sử)
    L-->>P: selectedServiceInstance(B)
    L-->>C: Chọn B
    C->>B: HTTP request

    C->>L: Request 2: inventory-service
    L->>P: Lấy danh sách ứng viên
    P->>D: get instances
    D-->>P: [A, B, C]
    P-->>L: Ưu tiên B
    L-->>C: Chọn B
    C->>B: HTTP request
~~~

Sơ đồ thể hiện đường đi khái niệm, không phải các phương thức callback đồng bộ có thứ tự y hệt trong mọi transport. Điều cốt lõi: **supplier được cập nhật từ kết quả chọn instance**, không phải từ một HTTP response thành công.

Điều đó kéo theo một giới hạn dễ bỏ sót: instance B có thể trả 500 hoặc timeout nhưng vẫn nằm trong danh sách của discovery. Nếu không có health filtering hoặc retry phù hợp, cơ chế preference có thể tiếp tục ưu tiên B. **Same-instance preference không tự đánh giá sức khỏe backend**.

## 3. Phạm vi của bộ nhớ: theo service ID và theo caller

Spring Cloud LoadBalancer thường tạo một context riêng cho mỗi service ID thông qua `LoadBalancerClientFactory`. Trong context này có các bean lựa chọn và supplier tương ứng. Khi bật preference cho inventory, supplier giữ trạng thái *instance đã được chọn gần nhất* của inventory ở phía caller.

Ví dụ một tiến trình `checkout-service` gọi hai service:

~~~text
checkout-service process #1
|
+-- LoadBalancer context: inventory-service
|   +-- SameInstancePreferenceServiceInstanceListSupplier
|   +-- previously selected: inventory-B
|
+-- LoadBalancer context: payment-service
    +-- supplier riêng
    +-- chính sách riêng (ví dụ Round Robin)
~~~

Không có chuyện chọn `inventory-B` rồi tự động làm thay đổi lựa chọn cho `payment-service`: hai service ID có context và tập instance riêng.

Đồng thời, `RestClient` và `WebClient` gọi cùng **service ID** từ cùng một caller process có thể chia sẻ LoadBalancer context/supplier nếu chúng dùng cùng cấu hình và `LoadBalancerClientFactory`. Trạng thái preference vì vậy **không gắn riêng với mỗi đối tượng HTTP client**, mỗi controller hay mỗi luồng Java. Nó gắn với **instance của supplier** được quản lý trong context LoadBalancer đó.

Để hình dung ranh giới:

| Phạm vi | Có chia sẻ “instance vừa chọn” mặc định không? | Giải thích |
|---|---|---|
| Hai request tuần tự tới cùng service ID, cùng caller process/context | Có xu hướng có | Cùng supplier giữ lựa chọn gần nhất |
| Hai controller trong cùng caller gọi cùng service ID | Có thể có | Nếu đi qua cùng LoadBalancer client context |
| Một RestClient và một WebClient trong cùng caller gọi cùng service ID | Có thể có | Nếu cùng sử dụng LoadBalancer infrastructure/context |
| Hai service ID khác nhau, cùng caller process | Không | Mỗi service ID thường có context riêng |
| Hai replica của `checkout-service` | Không | Mỗi JVM/container có supplier và bộ nhớ riêng |
| Hai người dùng đi qua một caller process | Không có trạng thái riêng cho từng người dùng | Lựa chọn gần nhất thuộc caller, không thuộc session |
| Caller restart/redeploy | Không duy trì | Trạng thái trong bộ nhớ được tạo lại |
| Hai cluster hoặc hai region | Không tự đồng bộ | Không có cơ chế đồng thuận/distributed persistence cho preference này |

Đây là đặc điểm khác biệt lớn nhất so với **session affinity** theo cookie. Same-instance preference là preference dựa trên *lựa chọn gần nhất của caller*, không dựa vào danh tính người dùng.

## 4. Khi có nhiều replica caller: mỗi nơi nhớ một kết quả

Giả sử `checkout-service` được scale thành ba Pod:

~~~mermaid
flowchart LR
    G["Gateway"] --> C1["Checkout Pod 1<br/>ưu tiên inventory A"]
    G --> C2["Checkout Pod 2<br/>ưu tiên inventory C"]
    G --> C3["Checkout Pod 3<br/>ưu tiên inventory A"]

    C1 --> A["Inventory A"]
    C2 --> C["Inventory C"]
    C3 --> A
~~~

Mỗi caller Pod có context và supplier riêng. Pod 1 có thể nhớ A, Pod 2 nhớ C, Pod 3 cũng nhớ A. Không có bộ chia sẻ trạng thái cho biết Pod nào đã chọn instance nào.

Vì thế:

- Một người dùng gửi request thứ nhất qua Checkout Pod 1 có thể gián tiếp gọi Inventory A.
- Request tiếp theo của **cùng người dùng** được gateway gửi qua Checkout Pod 2 có thể gián tiếp gọi Inventory C.
- Nếu ba caller cùng vô tình ưu tiên Inventory A thì A có thể bị nóng, trong khi B hoặc C ít traffic.

Không nên diễn giải Same-instance preference thành cam kết `userId -> inventory instance`. Cũng không nên giả định số lượng caller lớn sẽ tự phân phối đều tuyệt đối; phân bố ban đầu và thời gian tồn tại của preference có thể tạo độ lệch kéo dài.

Nếu cần **affinity theo phiên người dùng**, hãy dùng cơ chế có khóa định danh rõ ràng như request-based sticky session hoặc định tuyến theo consistent hashing được thiết kế cho nghiệp vụ. Nếu cần lưu trạng thái giao dịch hoặc session bền vững, nên dùng kho dữ liệu/session dùng chung thay vì phụ thuộc máy backend luôn không thay đổi.

## 5. Khởi tạo hoặc thay đổi instance được ưu tiên

Một số thời điểm làm thay đổi trạng thái preference:

| Tình huống | Kết quả có thể quan sát |
|---|---|
| Chưa từng chọn instance | Supplier chưa có lựa chọn cũ; bộ chọn dùng tập ứng viên ban đầu |
| Instance đã chọn vẫn có trong danh sách | Supplier ưu tiên instance đó |
| Instance đã chọn bị loại khỏi tập khả dụng | Bộ chọn cần chọn lại từ tập còn lại; lựa chọn mới trở thành ưu tiên |
| Discovery hoặc cache chưa cập nhật việc instance bị mất | Instance lỗi có thể vẫn được ưu tiên |
| Caller khởi động lại | Lịch sử lựa chọn bị xóa |
| Thay đổi service ID | Chuyển sang context khác, với trạng thái của service đó |
| Có nhiều request concurrent khi chưa có lịch sử | Các request có thể lựa chọn các instance khác nhau trước khi trạng thái được cập nhật |
| Instance cũ quay trở lại sau khi caller đã chọn instance khác | Không có bảo đảm tự chuyển về instance cũ; preference hướng tới lựa chọn mới nhất |

Một lần thay đổi danh sách không nhất thiết làm supplier quên hẳn instance cũ ngay lập tức. Điều kiện có ý nghĩa thực tế là **danh sách ứng viên hiệu lực của lượt chọn** sau discovery, cache, health check, zone filtering hoặc các supplier khác.

Trong hệ thống có nhiều request đồng thời, thứ tự các callback lựa chọn có thể đan xen. Vì vậy, đây là chính sách **best-effort** chứ không phải một cơ chế khóa cứng hoặc ràng buộc tuần tự tất cả request vào một backend.

## 6. Bật bằng cấu hình có sẵn

Spring Cloud cung cấp preset `same-instance-preference`. Nếu muốn cấu hình chính sách này ở phạm vi ứng dụng, có thể dùng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: same-instance-preference
~~~

Preset này chọn cấu hình `ServiceInstanceListSupplier` hỗ trợ preference thay vì supplier mặc định cho các LoadBalancer client chịu ảnh hưởng. Vì là cấu hình ở cấp global, hãy xem xét tác động đến tất cả các service ID trong caller.

Ở các phiên bản hỗ trợ per-client override của namespace `spring.cloud.loadbalancer.clients.<serviceId>`, có thể gắn preset cho một service:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          configurations: same-instance-preference
~~~

`inventory-service` phải trùng đúng service ID caller đang dùng. Cách này phụ thuộc cơ chế binding/cấu hình theo client của phiên bản Spring Cloud; kiểm tra bảng cấu hình của release train đang sử dụng nếu thấy preset không được áp dụng. Để định nghĩa chính xác chuỗi supplier hoặc kết hợp nhiều chính sách, lựa chọn an toàn, dễ kiểm soát là `@LoadBalancerClient` kèm cấu hình Java riêng theo service ID.

Không có thuộc tính chuẩn dạng `spring.cloud.loadbalancer.same-instance-preference.enabled: true` được bảo đảm dùng để thay thế trực tiếp hai cách trên. Cần dùng đúng preset hoặc đăng ký supplier phù hợp.

## 7. Cấu hình Java theo riêng inventory-service

Giả sử application chính ở package `com.example.checkout`. Ta đặt configuration class của LoadBalancer trong package **ngoài** vùng component scan của ứng dụng chính, ví dụ `com.example.lbconfig`, nhằm tránh bean trong client context bị đăng ký nhầm vào context toàn ứng dụng.

Trong lớp khởi động:

~~~java
package com.example.checkout;

import com.example.lbconfig.InventoryPreferenceConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryPreferenceConfiguration.class
)
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Trong `com.example.lbconfig.InventoryPreferenceConfiguration`:

~~~java
package com.example.lbconfig;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryPreferenceConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withSameInstancePreference()
                .build(context);
    }
}
~~~

Giải thích:

- `withDiscoveryClient()` cung cấp nguồn danh sách instance bằng discovery được cấu hình.
- `withCaching()` là tầng cache tùy chọn, đặt ngay sau nguồn discovery. Khi sử dụng cache của chính DiscoveryClient hoặc dùng health-check supplier có cache riêng, cân nhắc bỏ tầng cache trùng lặp.
- `withSameInstancePreference()` đặt decorator preference trên danh sách nguồn để LoadBalancer dùng kết quả ưu tiên.
- `@LoadBalancerClient(name = "inventory-service")` giới hạn cấu hình này cho service ID inventory trong ứng dụng caller.

Ở các release train cụ thể, mã mẫu có thể cần import hoặc chuỗi builder phù hợp với API được hỗ trợ. Spring Cloud có ví dụ trực tiếp với `withDiscoveryClient().withSameInstancePreference().build(context)`; bổ sung `withCaching()` ở đây để minh họa đúng vị trí cache theo hướng dẫn về supplier chain.

**Đừng để class cấu hình này bị component scan làm cấu hình global.** Nếu nó được đăng ký vào context chính, chính sách có thể tác động tới service ID không mong muốn. Có thể giữ class không gắn `@Configuration` như ví dụ, hoặc để class được gắn annotation ở package ngoài vùng quét và tham chiếu chỉ qua `@LoadBalancerClient`.

Lưu ý quan trọng về thứ tự chuỗi: preference nên hoạt động trên **danh sách ứng viên đã phù hợp với ràng buộc routing**. Ví dụ, nếu muốn ưu tiên zone trước rồi mới duy trì instance, một cấu hình có thể dùng:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withSameInstancePreference()
        .build(context);
~~~

Khi đó, một instance không còn nằm trong danh sách sau bước ưu tiên zone sẽ không được tiếp tục chọn chỉ vì từng được chọn ở lần trước. Hãy kiểm tra thứ tự wrapper và quy tắc fallback của từng supplier, thay vì nghĩ rằng preference mặc nhiên hiểu zone hoặc version.

## 8. Thử nghiệm bằng SimpleDiscoveryClient và RestClient

Để học ngay trên máy local, có thể dùng ba instance inventory chạy cùng code trên ba cổng 8081, 8082 và 8083; caller chạy trên cổng 8080.

Dependency cần thiết cho caller (phiên bản do Spring Boot parent và Spring Cloud BOM tương thích quản lý):

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

Khai báo danh sách instance tĩnh ở `application.yml` của caller:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: checkout-service
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

Trong service inventory, tạo endpoint để biết instance đã xử lý request:

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

    @GetMapping("/instance")
    public Map<String, String> instance() {
        return Map.of(
                "serviceId", "inventory-service",
                "instance", "inventory:" +
                        environment.getProperty("server.port", "8081")
        );
    }
}
~~~

Khởi chạy một ứng dụng Spring Boot inventory thành ba tiến trình riêng, ghi đè `--server.port=8081`, `--server.port=8082` và `--server.port=8083` tương ứng. Endpoint `/instance` phải trả về trường instance phân biệt cho từng cổng.

Ở caller, khai báo builder đã được Spring Cloud LoadBalancer tích hợp:

~~~java
package com.example.checkout;

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

Controller tạo RestClient theo service ID:

~~~java
package com.example.checkout;

import java.util.Map;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class InventoryProxyController {

    private final RestClient restClient;

    public InventoryProxyController(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    @GetMapping("/proxy/instance")
    public Map<String, String> proxy() {
        return restClient.get()
                .uri("/instance")
                .retrieve()
                .body(new org.springframework.core.ParameterizedTypeReference<>() {});
    }
}
~~~

Đây là code minh họa hoạt động của RestClient và instance selection. Không truy cập trực tiếp `http://localhost:8081` từ caller, vì như vậy sẽ bỏ qua LoadBalancer và không kiểm chứng preference.

## 9. Quan sát nhiều request và kết quả có thể xảy ra

Chạy các ứng dụng rồi gọi caller **tuần tự**:

~~~powershell
1..12 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/instance").instance
}
~~~

Ví dụ kết quả:

~~~text
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
inventory:8082
~~~

Đây là **kết quả minh họa**, không phải cổng 8082 luôn được chọn. Lần đầu LoadBalancer có thể chọn 8081, 8082 hoặc 8083. Với supplier preference đang được kích hoạt và danh sách ứng viên ổn định, các lượt sau thường tiếp tục dùng instance đầu tiên đã chọn.

Điều cần quan sát:

- **Chưa bật preference:** nếu dùng Round Robin mặc định, các cổng thường luân phiên qua nhiều request.
- **Đã bật preference:** sau khi một instance được chọn, các lượt gọi tuần tự thường tiếp tục về cùng instance.
- **Gửi request đồng thời:** có thể thấy nhiều instance lúc khởi động hoặc khi danh sách thay đổi; preference không phải cơ chế serialize các request.
- **Restart caller:** instance ưu tiên mới được chọn lại; có thể tình cờ trùng instance trước restart.
- **Restart một instance đích khi vẫn giữ URI tĩnh:** địa chỉ không bị xóa khỏi SimpleDiscoveryClient; việc dừng process không tự động kích hoạt fallback an toàn.

Hãy đo cả service ID logic và instance ID thực tế, vì chỉ nhìn `http://inventory-service` không cho biết backend nào đã xử lý request.

## 10. Kiểm chứng phạm vi bằng hai replica caller

Ta có thể chạy hai tiến trình checkout từ cùng ứng dụng, một ở cổng 8080 và một ở 8090. Mỗi tiến trình kết nối tới cùng danh sách inventory nhưng quản lý trạng thái preference riêng.

~~~text
checkout-service :8080   -> có thể ưu tiên inventory:8081
checkout-service :8090   -> có thể ưu tiên inventory:8083
~~~

Gọi tuần tự ở hai caller:

~~~powershell
Write-Host "Caller 8080"
1..8 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/instance").instance
}

Write-Host "Caller 8090"
1..8 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8090/proxy/instance").instance
}
~~~

Nếu cả hai caller trùng chọn inventory:8081, đó vẫn là một kết quả hợp lệ; **không phải bằng chứng rằng trạng thái được chia sẻ**. Để chứng minh ranh giới, có thể khởi động lại riêng caller 8090 và quan sát việc lựa chọn gần nhất được thiết lập lại; caller 8080 vẫn có thể tiếp tục ưu tiên instance cũ.

Mỗi replica caller có một context LoadBalancer bên trong chính JVM của nó. Thêm một API gateway phía trước không làm hai context đó chia sẻ state. Vì vậy, khi một yêu cầu của cùng người dùng chuyển qua các caller replica khác nhau, backend được chọn cũng có thể khác.

## 11. Kiểm chứng failover đúng cách

Một bài thử dễ gây hiểu lầm là dừng Inventory 8082 rồi kỳ vọng mọi request lập tức chuyển sang 8081. Nhưng với danh sách tĩnh trong `SimpleDiscoveryClient`, instance 8082 **vẫn được trả về**. Supplier preference có thể tiếp tục coi nó là ứng viên và việc gọi sẽ lỗi.

Muốn kiểm chứng tình huống instance cũ không còn khả dụng, cần **nguồn danh sách có thay đổi thật**:

1. Dùng Eureka/Consul/Kubernetes discovery hoặc `ServiceInstanceListSupplier` thử nghiệm có thể loại instance.
2. Đảm bảo instance đã dừng không còn nằm trong danh sách ứng viên **mà preference thực sự thấy**; tính đến độ trễ registry và cache.
3. Khi request tiếp theo đến, supplier không còn instance ưu tiên cũ nên trả về tập còn lại.
4. LoadBalancer chọn instance mới, rồi preference cập nhật theo instance đó.
5. Khi instance cũ quay lại, không nên kỳ vọng policy tự chuyển về nó; instance mới đã trở thành lựa chọn gần nhất.

Tùy thiết kế, có thể dùng `HealthCheckServiceInstanceListSupplier` để loại các instance không khỏe trước khi đến bước preference. Cơ chế này cần được cấu hình đúng thứ tự; đặt `health-check.interval` trong YAML không tự kích hoạt health supplier. Ngoài ra, một số discovery client đã có health filtering và cache riêng, do đó tránh bọc thêm nhiều tầng cache không cần thiết.

Kết quả cần ghi log: thời điểm instance biến mất khỏi supplier, instance trước đó được ưu tiên, số lỗi trước khi chuyển hướng, instance mới được chọn và độ trễ hồi phục. Những dữ liệu này phân biệt lỗi **phát hiện tình trạng instance** với lỗi **chọn instance**.

## 12. Preference không thay thế sticky session theo request

Spring Cloud có một tính năng khác tên `RequestBasedStickySessionServiceInstanceListSupplier`. Nó ưu tiên instance ID lấy từ cookie trong request, khác với Same-instance preference dựa trên lựa chọn trước của caller.

| Thuộc tính | Same-instance preference | Request-based sticky session |
|---|---|---|
| Khóa để ưu tiên | Instance đã chọn gần nhất của supplier | Instance ID trong cookie request |
| Nơi giữ ngữ cảnh | Bộ nhớ supplier thuộc LoadBalancer context của caller | Cookie gắn với từng luồng request/client tương ứng |
| Phân biệt hai người dùng qua cùng caller | Không | Có thể, nếu cookie được truyền đúng |
| Hai replica caller | Có lịch sử lựa chọn riêng | Có thể giữ tính liên tục nếu cookie đến đúng nơi và instance vẫn khả dụng |
| Khi instance ưu tiên biến mất | Fallback theo danh sách hiện tại | Fallback theo danh sách hiện tại |
| Mục tiêu chính | Hạn chế thay đổi backend cho một caller | Hướng các request liên quan về cùng backend |

Theo tài liệu Spring Cloud Commons, request-based sticky session có thể dùng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: request-based-sticky-session
      sticky-session:
        add-service-instance-cookie: true
      instance-id-cookie-name: sc-lb-instance-id
~~~

Khả năng tự bổ sung cookie và request context phụ thuộc HTTP integration; tài liệu Spring Cloud ghi nhận hỗ trợ trực tiếp cho đường đi WebClient trong phần này. Không nên tự khẳng định RestClient hoặc mọi triển khai Feign đều có cùng hành vi xử lý cookie.

Cả hai cơ chế **không phải** lời hứa rằng request luôn về một instance không giới hạn thời gian. Nếu backend bị loại, fallback là cần thiết. Nếu ứng dụng phụ thuộc vào session/state đặt trong bộ nhớ một backend, cần thiết kế dữ liệu phiên chia sẻ hoặc phục hồi khi backend chết.

## 13. Tương tác với retry, timeout và nhiều tầng cân bằng tải

Same-instance preference thuộc lớp **chọn đích**. Nó không tự cấu hình connect timeout, read timeout, số lần retry, circuit breaker hoặc transaction idempotency.

Khi một request gặp lỗi:

- Callback chọn instance có thể đã ghi nhận instance trước khi biết request HTTP thành công hay thất bại.
- Nếu instance lỗi vẫn tồn tại trong danh sách, preference có thể tiếp tục chọn instance lỗi.
- Nếu bật retry và muốn tránh instance vừa thất bại, cần kiểm tra chính sách retry và supplier `RetryAwareServiceInstanceListSupplier` tương ứng. Chính sách tránh instance cũ có thể tương tác với preference; phải xác minh thực tế ở phiên bản đang dùng.
- HTTP client vẫn cần connect/read/response timeout để không chờ vô hạn khi đích không phản hồi.
- POST hoặc thao tác thay đổi trạng thái cần idempotency key/thiết kế chống xử lý trùng trước khi retry.

Bên cạnh đó, nếu caller chọn một địa chỉ VIP hoặc Kubernetes Service thay vì trực tiếp một Pod/instance, Same-instance preference chỉ ổn định **địa chỉ logic mà LoadBalancer nhìn thấy**. Hạ tầng phía sau VIP vẫn có thể đưa các kết nối đến các backend khác nhau. Không nên dựa vào preference để suy ra Pod cuối cùng khi hệ thống có hai lớp load balancing.

Một ví dụ:

~~~text
Caller process
  -> SameInstancePreferenceServiceInstanceListSupplier
  -> ServiceInstance = http://inventory.internal (VIP)
  -> Infrastructure load balancer
  -> Có thể chọn backend A hoặc backend B
~~~

Nếu chỉ có một VIP trong danh sách, preference không phân biệt được các backend phía sau nó. Lựa chọn có vẻ ổn định ở Spring Cloud nhưng HTTP request thực tế vẫn có thể được hạ tầng phân phối.

## 14. Rủi ro tải lệch và tiêu chí chọn giải pháp

Same-instance preference có thể có ích khi backend có cache cục bộ và caller hưởng lợi từ việc tiếp tục gọi bản sao quen thuộc. Tuy nhiên, trước khi áp dụng, cần trả lời các câu hỏi sau:

- **Số caller replica so với số backend:** một caller có thể đẩy hầu hết tải của nó vào một backend; nếu có rất ít caller nhưng nhiều backend, nhiều bản sao backend có thể gần như không nhận traffic.
- **Độ đồng nhất backend:** nếu instance có năng lực khác nhau, preference không tự tính trọng số hay CPU.
- **Tuổi thọ caller:** tiến trình sống lâu giữ preference lâu; sau rolling restart, bản đồ caller → backend có thể phân bố lại đột ngột.
- **Thay đổi backend:** health check và discovery refresh có kịp loại instance lỗi không?
- **Nhiều region/zone:** instance được ưu tiên có còn hợp lệ theo chính sách zone hiện tại không?
- **Dữ liệu phiên:** state quan trọng có đang nằm độc quyền trong RAM của backend không? Nếu có, preference không đủ để bảo đảm tính đúng đắn.

Ví dụ chọn chính sách:

| Nhu cầu | Hướng tiếp cận |
|---|---|
| Muốn các request được phân phối gần đều theo số lượt | Round Robin hoặc chính sách load balancing phù hợp |
| Muốn caller ưu tiên instance vừa chọn khi còn khả dụng | Same-instance preference |
| Muốn từng người dùng có affinity khi di chuyển giữa caller replica | Request-based sticky session hoặc định tuyến dựa trên khóa định danh |
| Muốn giảm truy cập qua zone | ZonePreference supplier, có thể kết hợp preference theo thứ tự phù hợp |
| Muốn cân bằng dựa trên năng lực backend khác nhau | Weighted hoặc chiến lược riêng có dữ liệu tải |
| Muốn session tồn tại khi backend bị thay thế | Lưu session/state ở kho dùng chung, không chỉ dựa vào routing |

Phần lớn hệ thống cần tính sẵn sàng và chia tải nên bắt đầu với Round Robin và health filtering, sau đó chỉ bật preference nếu đã có phép đo cho thấy lợi ích. Nếu mục tiêu là cache locality, nên so sánh cache hit ratio, p95/p99 latency và độ lệch tải giữa các replica trước và sau khi bật.

## 15. Quan sát và chẩn đoán

Không đủ để nhìn log của một backend và kết luận rằng preference đã hoạt động. Hãy quan sát theo ba lớp:

1. **Caller:** caller instance ID/Pod name, service ID được gọi, thời gian request, HTTP status và retry count.
2. **LoadBalancer:** danh sách ứng viên sau filtering, instance được chọn gần nhất, số lần fallback, event thay đổi instance nếu instrument được.
3. **Backend:** instance ID thực phục vụ request, số request, cache hit rate, CPU, error rate và response latency.

Các trường hợp thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Request luân phiên giữa A/B/C | Chưa kích hoạt supplier preference, hoặc cấu hình bị scope sai service ID |
| Request luôn đến A | Có thể preference đang hoạt động; cũng có thể chỉ có một ứng viên hoặc caller đang gọi thẳng A |
| Hai caller chọn hai backend khác nhau | Bình thường vì hai caller có trạng thái riêng |
| Cùng một người dùng đổi backend | Gateway có thể đổi caller Pod; preference không keyed theo user |
| A đã chết nhưng vẫn được ưu tiên | Discovery/cache/health chưa loại A khỏi danh sách |
| Sau restart caller, backend thay đổi | Lịch sử preference không bền vững |
| Bật policy nhưng thấy tải lệch quá nhiều | Đây là hệ quả có thể xảy ra; cần kiểm tra số caller, số backend và lượng request mỗi caller |
| Bật cả zone và preference nhưng chọn khác mong đợi | Kiểm tra thứ tự supplier và fallback khi không có instance trong zone |

Đối với Spring Cloud LoadBalancer, có thể bật các lifecycle/metrics của Micrometer theo phiên bản phù hợp khi `MeterRegistry` hiện diện. Tránh đưa user ID hay URL động nguyên vẹn vào label gây cardinality cao. Nếu muốn biết *instance đã chọn* ở từng request, có thể dùng log có correlation ID, custom lifecycle callback hoặc HTTP request transformer tùy loại client.

### Checklist kiểm chứng

- [ ] Service ID ở URI khớp `@LoadBalancerClient(name = "...")` hoặc nhánh cấu hình per-client.
- [ ] Caller dùng RestClient/WebClient/OpenFeign đã tích hợp Spring Cloud LoadBalancer, không gọi trực tiếp IP.
- [ ] Supplier chain thực tế chứa `SameInstancePreferenceServiceInstanceListSupplier`.
- [ ] Class cấu hình per-client không bị component scan như cấu hình global.
- [ ] Đã xác minh lần đầu chọn một instance và các lần tuần tự tiếp theo ưu tiên lại instance đó.
- [ ] Hiểu rõ trạng thái là **per service ID / per caller process**, không phải per user/session.
- [ ] Đã thử với hai caller replica, không giả định hai nơi dùng chung lịch sử.
- [ ] Đã kiểm tra độ trễ discovery/cache/health khi backend lỗi và xác định điều kiện fallback.
- [ ] Nếu có zone/hint, đã kiểm tra thứ tự các supplier.
- [ ] Đã kiểm tra retry, timeout và yêu cầu idempotency riêng.
- [ ] Đã đo số request/CPU/latency theo backend để phát hiện hotspot trước khi triển khai rộng.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): mục *Same instance preference for LoadBalancer*, `SameInstancePreferenceServiceInstanceListSupplier`, preset `same-instance-preference` và request-based sticky session.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): thuộc tính `spring.cloud.loadbalancer` và cấu hình theo service ID.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): discovery và retry trong service-to-service communication.

**Kết luận:** Same-instance preference là một chính sách **ưu tiên lựa chọn gần nhất được ghi nhớ ở bên gọi**. Nó giúp caller có xu hướng bám vào một `ServiceInstance` miễn instance đó vẫn đủ điều kiện, nhưng không có nghĩa người dùng có session affinity bền vững hoặc nhiều caller replica chia sẻ cùng lựa chọn. Để vận hành ổn định, phải kết hợp đúng discovery, health check, retry/timeout, quan sát phân phối tải và lựa chọn chính sách định tuyến dựa trên nhu cầu nghiệp vụ.
