# Trọng số trong lựa chọn bản sao và nguồn metadata

Khi các bản sao của một service có năng lực xử lý khác nhau, chia đều request theo số lượng instance có thể không phù hợp. Một bản sao chạy trên máy cấu hình lớn có thể xử lý nhiều request hơn bản sao giới hạn CPU; một phiên bản canary chỉ nên nhận một phần traffic nhỏ trong giai đoạn thử nghiệm. **Trọng số (weight)** là cách biểu diễn mức độ ưu tiên tương đối của từng `ServiceInstance` khi chọn đích.

Bài học thuộc chương **Thuật toán chọn đích** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Module hướng tới việc hiểu cân bằng tải phía client của Spring Cloud LoadBalancer: chọn `ServiceInstance` theo service ID, discovery, health check và chính sách định tuyến; đồng thời thực hành `RestClient`, `WebClient`, OpenFeign, retry/timeout và quan sát lỗi. Ở bài này, ta tập trung vào hai câu hỏi: **trọng số ảnh hưởng thế nào tới cơ hội được chọn** và **trọng số đến từ đâu trong metadata của instance**.

Sau khi học, bạn có thể giải thích tỉ lệ phân phối traffic theo trọng số, gắn metadata `weight` cho từng replica, xây dựng supplier chain có hỗ trợ trọng số, xác minh metadata thực sự tới LoadBalancer, thiết kế phép đo phân phối và nhận diện trường hợp kết quả thực tế khác kỳ vọng.

## 1. Tại sao cần trọng số?

Giả sử `inventory-service` có ba instance:

| Instance | Địa chỉ | Khả năng xử lý tương đối | Trọng số |
|---|---|---|---:|
| `inv-a` | `localhost:8081` | Máy lớn, nhiều CPU | 5 |
| `inv-b` | `localhost:8082` | Máy cỡ vừa | 3 |
| `inv-c` | `localhost:8083` | Máy nhỏ hoặc canary | 2 |

Nếu bộ chọn chia đều ba instance, mỗi bản sao có thể nhận khoảng một phần ba số request, bất kể năng lực thực tế. Với trọng số `5:3:2`, mục tiêu phân phối tương đối sẽ gần `50%:30%:20%` khi cả ba instance cùng khả dụng và không có chính sách lọc nào khác.

Có thể biểu diễn tỉ lệ mục tiêu của một instance `i` bằng:

\[
p_i = \frac{w_i}{\sum_{j=1}^{n}w_j}
\]

Trong đó `w_i` là trọng số dương của instance `i`, còn mẫu số là tổng trọng số của **những instance vẫn nằm trong tập ứng viên** tại thời điểm lựa chọn.

Với `w_A=5`, `w_B=3`, `w_C=2`:

- Tổng trọng số: `5 + 3 + 2 = 10`.
- `A`: `5 / 10 = 50%`.
- `B`: `3 / 10 = 30%`.
- `C`: `2 / 10 = 20%`.

Đây là cách tính **tỉ lệ kỳ vọng**, không phải cam kết chính xác cho từng nhóm 10 request. Kết quả thực tế phụ thuộc thuật toán chọn, số lần gọi, biến động danh sách instance, cache, health check, retry và các lớp proxy khác.

## 2. Trọng số tác động ở vị trí nào trong Spring Cloud LoadBalancer?

Một client gọi bằng service ID, ví dụ `http://inventory-service`. Spring Cloud LoadBalancer lấy danh sách `ServiceInstance` thông qua `ServiceInstanceListSupplier`, sau đó bộ chọn như `RoundRobinLoadBalancer` sử dụng danh sách ứng viên để chọn một địa chỉ.

~~~mermaid
flowchart LR
    A["RestClient / WebClient / OpenFeign"] --> B["LoadBalancer theo service ID"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["Discovery + metadata"]
    D --> E["Danh sách instance có weight"]
    E --> F["Lớp hỗ trợ trọng số"]
    F --> G["Danh sách/cơ hội lựa chọn hiệu dụng"]
    G --> H["Bộ chọn instance"]
    H --> I["HTTP tới instance được chọn"]
~~~

Trong Spring Cloud LoadBalancer, `WeightedServiceInstanceListSupplier` là một thành phần hỗ trợ lựa chọn dựa trên trọng số. Nó có thể tham gia supplier chain để phản ánh trọng số trong tập ứng viên mà thuật toán chọn đích sử dụng.

Cần phân biệt ba vai trò:

1. **Discovery** tìm các replica theo service ID và cung cấp metadata.
2. **Supplier chain** cung cấp hoặc biến đổi danh sách ứng viên, bao gồm chính sách trọng số và các bộ lọc nếu được cấu hình.
3. **Bộ chọn instance** chọn một `ServiceInstance` để gửi request.

Việc thêm metadata `weight` vào registry **chưa đủ** để mọi cấu hình LoadBalancer tự động phân phối theo trọng số. Caller còn phải sử dụng supplier hoặc cơ chế chọn đích có hiểu trọng số. Ngược lại, việc bật weighted supplier nhưng metadata không được cung cấp đúng có thể khiến các instance mang trọng số mặc định.

## 3. Metadata của ServiceInstance là nguồn trọng số

`ServiceInstance` có thể cung cấp metadata dạng map thông qua `getMetadata()`. Metadata thường chứa các chuỗi key-value do discovery client hoặc nguồn cung cấp instance ánh xạ vào.

Ví dụ một instance được nhìn từ caller:

~~~text
serviceId = inventory-service
instanceId = inv-a
host = localhost
port = 8081
metadata = {
    "weight": "5",
    "zone": "zone-a",
    "version": "v1"
}
~~~

Trong cơ chế trọng số mặc định của Spring Cloud LoadBalancer, khóa metadata thường được dùng là `weight`. Mỗi instance không có trọng số được khai báo sẽ sử dụng **trọng số mặc định 1**. Giá trị metadata vốn là chuỗi, nên cần đặt nội dung theo định dạng mà cơ chế đọc trọng số của phiên bản đang sử dụng hỗ trợ.

Một quy ước dữ liệu tốt là:

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| `weight` | `"5"` | Mức ưu tiên tương đối khi phân phối request |
| `zone` | `"zone-a"` | Gợi ý vị trí để áp dụng zone preference |
| `version` | `"v1"` | Đánh dấu phiên bản phục vụ hoặc triển khai |
| `trafficTier` | `"stable"` | Phục vụ chính sách lọc canary/stable nếu có |

Không nên dùng các thuộc tính này thay thế lẫn nhau. `zone` xác định vị trí, `version` cho biết phiên bản, còn `weight` mô tả mức phân phối tương đối. Trọng số không tự sinh từ số CPU, mức sử dụng RAM, độ trễ HTTP hoặc health score, trừ khi ứng dụng đã chủ động viết cơ chế tính và cập nhật giá trị đó.

### Nguồn metadata phổ biến

Metadata có thể đến từ nhiều nơi:

- **Registry động**: Eureka, Consul hoặc một discovery implementation khác nhận metadata của service khi đăng ký và đưa chúng vào `ServiceInstance`.
- **Cấu hình tĩnh**: `SimpleDiscoveryClient` tạo các instance và metadata từ `application.yml` của caller.
- **Nền tảng triển khai**: discovery client tương ứng có thể ánh xạ labels/annotations/tags của hệ thống triển khai vào metadata, tùy thư viện và cấu hình.
- **Supplier tùy chỉnh**: tự xây dựng `ServiceInstance` hoặc một cơ chế cấp trọng số từ nguồn quản lý nội bộ.

Điểm quan trọng là trọng số phải hiện diện trong **metadata mà ứng dụng caller thực sự nhận được**. Một trường trong cấu hình của server, một response body hoặc một tag ở hệ thống triển khai không tự động trở thành metadata của `ServiceInstance` nếu discovery adapter không chuyển trường đó qua.

## 4. Ví dụ nguồn tĩnh với SimpleDiscoveryClient

Trong môi trường local, có thể khai báo ba bản sao của `inventory-service` bằng `SimpleDiscoveryClient`. Ví dụ cấu hình đặt trong ứng dụng **caller**:

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
                metadata:
                  weight: "5"
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  weight: "3"
                  zone: zone-a
              - uri: http://localhost:8083
                metadata:
                  weight: "2"
                  zone: zone-b
~~~

Các cổng `8081`, `8082` và `8083` là ba tiến trình riêng của service đích. Mỗi tiến trình nên có endpoint chẩn đoán `GET /internal/instance` trả định danh của chính nó để quan sát đường đi của request.

Cấu hình trên chỉ tạo danh sách discovery tĩnh. Nó không tự chạy ba server, không tự loại một server vừa ngừng hoạt động và không bảo đảm registry động được sử dụng khi ứng dụng đã cài đặt cơ chế discovery khác. Với ví dụ local, cần kiểm tra từng endpoint trực tiếp trước khi đo phân phối qua LoadBalancer.

Ưu điểm của nguồn tĩnh là dễ kiểm soát đầu vào để kiểm thử. Nhược điểm là thay đổi instance hoặc metadata thường phải cập nhật cấu hình ứng dụng, thay vì được registry đồng bộ tự động.

## 5. Đọc trọng số từ registry động

Ở môi trường có Eureka, từng replica có thể khai báo trọng số qua metadata đăng ký. Ví dụ trên instance `inventory-service`:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      weight: "5"
      zone: zone-a
~~~

Bản sao thứ hai có thể đặt `weight: "3"`, bản sao thứ ba đặt `weight: "2"`. Đây là ví dụ **dành riêng cho Eureka**; nó chỉ có tác dụng khi ứng dụng đã tích hợp Eureka Discovery Client và instance được đăng ký thành công.

Các registry khác sử dụng cấu hình metadata riêng. Chẳng hạn với Consul hoặc nền tảng Kubernetes, không nên sao chép khóa `eureka.instance.metadata-map` rồi giả định client sẽ hiểu. Hãy dùng cấu hình mà discovery implementation đó hỗ trợ và xác minh metadata sau khi được ánh xạ vào `ServiceInstance`.

Những bước quan trọng khi nguồn metadata là registry:

1. Bảo đảm các replica đăng ký dưới cùng service ID nhưng có instance ID và địa chỉ khác nhau.
2. Đặt metadata trọng số trên từng instance, theo quy tắc key-value thống nhất.
3. Xác minh registry đã lưu đúng giá trị của từng bản sao.
4. Xác minh `ServiceInstance.getMetadata()` phía caller chứa khóa `weight` cùng giá trị mong đợi.
5. Quan sát thời gian cập nhật khi đổi trọng số; việc đăng ký lại, đồng bộ discovery hoặc cache có thể khiến cập nhật không có hiệu lực ngay lập tức.

Không nên mặc định rằng chỉ cần thay file YAML trên một instance đang chạy là mọi caller lập tức thấy trọng số mới. Cần xét cơ chế refresh và đăng ký của môi trường thực tế.

## 6. Bật lựa chọn có trọng số bằng supplier builder

Cấu hình một `ServiceInstanceListSupplier` riêng cho `inventory-service`:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryWeightedLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withWeighted()
                .build(context);
    }
}
~~~

Ý nghĩa:

- `withDiscoveryClient()`: xây dựng nguồn danh sách từ discovery client.
- `withCaching()`: cache danh sách nguồn để giảm truy vấn discovery lặp lại.
- `withWeighted()`: bổ sung cơ chế xét trọng số dựa trên thông tin của instance.
- `build(context)`: hoàn thiện chain cho context đang được cấu hình.

Đăng ký cấu hình với **service ID đích**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryWeightedLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Lớp `InventoryWeightedLoadBalancerConfiguration` nên được đặt ngoài phạm vi component scan chung của ứng dụng (hoặc loại khỏi scan) để bean supplier chỉ xuất hiện trong LoadBalancer context tương ứng. Ví dụ đặt ứng dụng ở `com.example.order` và cấu hình riêng ở `com.example.loadbalancer.inventory`.

Các ví dụ code giả định một dòng Spring Boot/Spring Cloud tương thích có hỗ trợ builder và weighted supplier. Khi triển khai trên version cụ thể, xác nhận phiên bản dependency và các API builder có mặt. Không cần tự tạo nhiều supplier bean cạnh tranh cho cùng một service ID; một chain có nguồn và các bước đã được xác định là đủ.

## 7. Trọng số tương tác với Round Robin, Random và danh sách ứng viên

Trọng số không phải là một lệnh độc lập yêu cầu “cứ đúng 10 request thì A nhận 5, B nhận 3, C nhận 2”. Thay vào đó, nó làm thay đổi cơ hội lựa chọn giữa các instance theo cơ chế hỗ trợ trọng số đã cấu hình.

| Phương án | Đầu vào | Cách hiểu kết quả |
|---|---|---|
| Round Robin thông thường | Ba instance cùng mức ưu tiên | Thường hướng tới việc luân phiên các ứng viên |
| Random thông thường | Ba instance cùng mức ưu tiên | Mỗi lần chọn một ứng viên ngẫu nhiên |
| Weighted supplier kết hợp bộ chọn | Ba instance có `weight=5,3,2` | Hướng tới phân phối tương đối có trọng số khi không có yếu tố lọc hay lỗi khác |
| Filter theo zone trước bước trọng số | Chỉ còn các instance thuộc zone hợp lệ | Trọng số chỉ có ý nghĩa trong tập ứng viên còn lại |

Ví dụ zone preference chỉ giữ `inv-a` và `inv-b`, có weight lần lượt là `5` và `3`. Khi `inv-c` không nằm trong tập ứng viên, tỉ lệ mục tiêu lúc này dựa trên tổng `5+3=8`: khoảng `62,5%` cho A và `37,5%` cho B, **không còn là 50%-30%-20%**.

Nếu chỉ có một ứng viên hợp lệ, nó là lựa chọn duy nhất bất kể weight. Nếu danh sách rỗng, LoadBalancer không có đích để gọi. Nếu một instance không khỏe bị loại, trọng số của nó không còn tham gia phân phối cho tới khi instance quay lại tập ứng viên.

### Tình huống phiên bản canary

Giả sử hai replica chạy bản ổn định, một replica chạy canary:

~~~text
stable-A weight=9
stable-B weight=9
canary-C weight=2
~~~

Nếu cả ba là ứng viên, canary có mục tiêu khoảng `2/(9+9+2) = 10%`. Cách này có thể giúp thử tải với mức ảnh hưởng nhỏ. Tuy nhiên, trọng số chỉ điều chỉnh phân phối yêu cầu; nó không tự bảo đảm tách biệt dữ liệu, định tuyến theo người dùng, tính ổn định của phiên hoặc khả năng rollback. Với một canary cần ràng buộc nghiêm ngặt, cần thiết kế thêm chính sách định tuyến, quan sát và điều kiện dừng triển khai.

## 8. Khi kết hợp weighted supplier với cache, health check và zone

Trong ứng dụng thực, supplier chain có thể có nhiều bước. Thứ tự rất quan trọng vì các bước có thể biến đổi tập ứng viên:

~~~text
Discovery source
     |
     v
Caching / Health check (theo thiết kế)
     |
     v
Zone hoặc metadata filter
     |
     v
Weighted supplier
     |
     v
LoadBalancer chọn instance
~~~

Sơ đồ mô tả trách nhiệm và quan hệ dữ liệu, không khẳng định mọi phiên bản luôn tạo chain theo đúng thứ tự hiển thị. Với builder, phải kiểm tra thứ tự các decorator thực tế và khả năng tương thích của chúng.

Một số nguyên tắc thiết kế:

- **Cache gần nguồn discovery.** Cache danh sách registry giúp giảm tải tra cứu; tránh cache nhầm kết quả đã phụ thuộc request mà không có khóa cache phù hợp.
- **Health check phản ánh khả năng phục vụ.** Weight cao không khiến một instance đang chết có thể nhận request thành công. Cần dùng trạng thái discovery, health-check supplier hoặc cơ chế loại bỏ instance không khỏe.
- **Zone và metadata lọc trước khi so tỉ lệ cuối cùng.** Tổng trọng số phải dựa trên tập ứng viên hợp lệ sau chính sách lọc.
- **Không đặt weight thay cho timeout.** Instance có weight thấp vẫn có thể bị chậm hoặc timeout; phải cấu hình timeout theo giao tiếp HTTP.
- **Không dùng weight để bảo đảm độ bám phiên.** Sticky session hoặc tính nhất quán theo người dùng cần chính sách riêng.
- **Không tính weight như giới hạn concurrency tuyệt đối.** Replica có trọng số lớn có thể bị quá tải nếu công việc xử lý không đồng nhất.

Nếu ứng dụng cần health, zone và trọng số cùng lúc, đừng ghép các bước theo cảm tính. Hãy xác định supplier nào tạo danh sách nền tảng, bước nào đọc cache, bước nào lọc instance và bước nào thay đổi cơ hội lựa chọn; sau đó kiểm thử chính xác danh sách cùng phân phối đầu ra.

## 9. Gọi qua RestClient và quan sát định danh bản sao

Trên caller, cấu hình một `RestClient.Builder` được tích hợp LoadBalancer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Tạo kiểu phản hồi chẩn đoán tối giản:

~~~java
public record InstanceResponse(
        String serviceId,
        String instanceId
) {}
~~~

Ví dụ thực hiện nhiều lần gọi và tổng hợp số lượt nhận bởi từng instance:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class WeightedDistributionProbe {

    private final RestClient client;

    public WeightedDistributionProbe(
            @LoadBalanced RestClient.Builder builder) {
        this.client = builder.build();
    }

    public Map<String, Integer> collect(int requests) {
        Map<String, Integer> counts = new HashMap<>();

        for (int i = 0; i < requests; i++) {
            InstanceResponse response = client.get()
                    .uri("http://inventory-service/internal/instance")
                    .retrieve()
                    .body(InstanceResponse.class);

            if (response != null) {
                counts.merge(response.instanceId(), 1, Integer::sum);
            }
        }

        return counts;
    }
}
~~~

Mỗi replica của `inventory-service` cần trả `instanceId` riêng ở endpoint `/internal/instance`. Nhờ vậy, caller nhìn thấy instance thực sự phục vụ request thay vì chỉ biết địa chỉ logic.

Ví dụ với `1.000` request thành công trong một thử nghiệm minh họa:

~~~text
inv-a: 506
inv-b: 294
inv-c: 200
~~~

Các số này **chỉ là dữ liệu giả định** để minh họa cách đọc kết quả. Không coi chúng là kết quả chạy thực tế của code hoặc là tỉ lệ bảo đảm. Nếu chạy lại, kết quả có thể khác do cách lựa chọn và trạng thái hệ thống.

Với `WebClient` hoặc OpenFeign đã cấu hình Spring Cloud LoadBalancer, nguyên tắc quan sát tương tự: gọi hostname logic của service, đọc instance ID trong response và tổng hợp số lượt. Phần supplier có trọng số vẫn thuộc LoadBalancer context của service ID đích.

## 10. Cách đánh giá tỉ lệ phân phối đúng

Đánh giá weight bằng số request phải xét điều kiện của phép đo. Một phép thử hữu ích nên:

1. Khởi động tất cả replica và xác nhận endpoint chẩn đoán hoạt động khi gọi trực tiếp.
2. Xác nhận caller đang dùng supplier hỗ trợ trọng số cho đúng service ID.
3. Kiểm tra `ServiceInstance.getMetadata()` của từng instance có các giá trị `weight` như mong đợi.
4. Gọi một số lượng request đủ lớn qua cùng một cơ chế LoadBalancer; loại trừ những thời điểm instance khởi động hoặc danh sách còn thay đổi.
5. Ghi tổng số lượt gọi, số lượt thành công, lỗi và retry theo từng instance nếu có thể quan sát.
6. So sánh tỉ lệ trên tập request được định nghĩa rõ, rồi đối chiếu với tình trạng health, zone, cache và retry.

Công thức tỉ lệ quan sát được:

\[
\hat p_i = \frac{N_i}{\sum_j N_j}
\]

Trong đó `N_i` là số lượt của instance `i` **theo cùng một cách đếm**. Nếu chỉ đếm response thành công, tỉ lệ có thể khác với tỉ lệ các lần lựa chọn instance khi một replica thường xuyên lỗi. Khi có retry, một yêu cầu logic có thể sinh nhiều lượt thử HTTP và có thể được chuyển đến nhiều instance.

Đừng viết kiểm thử cứng rằng đúng `500/300/200` lượt sau `1.000` request là bắt buộc. Thay vào đó, kiểm thử đơn vị nên xác minh việc đọc metadata và diễn giải trọng số; kiểm thử tích hợp xác minh phân phối nằm trong khoảng chấp nhận được dưới điều kiện thử có kiểm soát. Khoảng chấp nhận phải được xác định theo nhu cầu và đặc tính thuật toán đang dùng.

## 11. Điều gì xảy ra khi trọng số thiếu, sai hoặc thay đổi?

Các tình huống này cần có chính sách nhất quán:

| Tình huống | Điều cần kiểm tra |
|---|---|
| Không có metadata `weight` | Cơ chế mặc định thường dùng trọng số 1; xác nhận phiên bản và dữ liệu được nhận. |
| Giá trị `weight` không phải số hợp lệ | Kiểm tra cách supplier xử lý; chuẩn hóa metadata và phát hiện sớm lúc triển khai. |
| Trọng số bằng 0 hoặc âm | Không tự giả định nghĩa “tắt instance”; chọn giá trị dương hợp lệ và xác minh hành vi của phiên bản sử dụng. |
| Trọng số rất lớn so với các instance khác | Instance đó có thể nhận phần lớn traffic; đánh giá sức chứa và sai số đo. |
| Registry vừa cập nhật trọng số | Có thể phải chờ registration/discovery refresh và cache TTL. |
| Một instance ngừng hoạt động | Bảo đảm discovery/health loại hoặc đánh dấu instance, tránh tiếp tục gửi request lỗi. |
| Metadata key sai chữ hoa/thường | Thống nhất chính xác tên `weight` và kiểm tra map phía caller. |
| Chỉ caller A có weighted supplier | Caller B có thể vẫn phân phối khác dù gọi cùng service ID. |

Các weight được khai báo nên là số dương đơn giản, ví dụ `1`, `2`, `5`; tránh dựa vào hành vi không được tài liệu hóa đối với giá trị rỗng, số âm hoặc số thập phân.

### Cập nhật trọng số khi đang chạy

Một kế hoạch đổi weight từ `5:3:2` sang `3:3:4` có thể phục vụ thử nghiệm tăng traffic cho bản sao thứ ba. Nhưng thứ tự cập nhật quan trọng:

- Cập nhật metadata theo cơ chế registry hỗ trợ.
- Đợi registry phản ánh dữ liệu mới và caller nhận lại danh sách sau cache/refresh.
- Kiểm tra mọi caller liên quan đã áp dụng chính sách tương ứng.
- Đọc phân phối thực tế cùng lỗi và độ trễ.
- Có phương án khôi phục trọng số cũ nếu phiên bản nhận thêm traffic không đáp ứng.

Vì mỗi caller có thể có cache và chu kỳ discovery khác nhau, quá trình chuyển đổi hiếm khi đồng bộ tuyệt đối ở mọi nơi.

## 12. Weight không phải bộ điều khiển tải tự động

Trọng số là một cấu hình **tương đối**; nó không đo trực tiếp số request đang xử lý hoặc độ trễ hiện thời. Ví dụ đặt `weight=5` cho một replica không có nghĩa replica chắc chắn phục vụ nhanh gấp năm lần replica `weight=1`. Năng lực thực tế còn phụ thuộc kích thước request, dữ liệu, CPU, IO, connection pool và dependency phía sau.

Một số nguyên tắc vận hành:

- Đo throughput, latency, tỷ lệ lỗi, saturation và giới hạn tài nguyên trước khi đặt weight.
- Tránh tăng weight đồng loạt cho nhiều instance nếu hệ thống downstream vẫn là nút thắt.
- Không coi weight là rate limiter, circuit breaker hoặc timeout.
- Với request không đồng nhất về chi phí xử lý, phân phối theo số request có thể không tương đương với phân phối theo CPU hoặc thời gian xử lý.
- Khi traffic có tính phiên, sticky routing có thể tác động lên tỉ lệ quan sát được.
- Khi có retry, phải phân biệt lần gọi ban đầu với toàn bộ attempt để đánh giá tác động của weight.
- Đối với canary rollout, kết hợp weight với metric lỗi/độ trễ, kiểm soát version và khả năng rollback.

Nếu muốn weight tự điều chỉnh từ metric tải theo thời gian thực, đó là một cơ chế điều khiển bổ sung cần thiết kế, lọc nhiễu và giới hạn dao động. Đừng giả định weighted supplier mặc định sẽ tự thay weight dựa trên CPU hoặc latency.

## 13. Sơ đồ xử lý sự cố khi phân phối không như kỳ vọng

~~~mermaid
flowchart TD
    A["Tỉ lệ instance khác tỉ lệ weight mong đợi"] --> B{"Caller dùng weighted supplier?"}
    B -- "Chưa" --> C["Kiểm tra bean và @LoadBalancerClient theo service ID"]
    B -- "Có" --> D{"Metadata weight tới caller?"}
    D -- "Không" --> E["Kiểm tra registry, key weight, refresh, cache"]
    D -- "Có" --> F{"Tập ứng viên có đủ replica?"}
    F -- "Không" --> G["Kiểm tra health, zone, hint và filter"]
    F -- "Có" --> H{"Có retry/lỗi hoặc proxy khác?"}
    H -- "Có" --> I["Đối chiếu attempt, response, lỗi và proxy"]
    H -- "Không" --> J["Tăng mẫu, kiểm tra thuật toán và cách đo"]
~~~

Ví dụ điều tra thực tế: `inv-a` đang khai báo weight 5 nhưng chỉ trả về 10% response thành công. Có thể nó bị lỗi nhiều, bị health check loại bớt, hoặc caller đang dùng dữ liệu discovery cũ. Nếu chỉ nhìn số response thành công và tăng weight ngay, tình trạng quá tải có thể nghiêm trọng hơn. Hãy kiểm tra số lượt chọn instance, số attempt, tỷ lệ lỗi và thời điểm cache được cập nhật.

Với một sự cố khó tái hiện, log nên có service ID, instance ID được chọn, phiên bản triển khai, số lượng ứng viên và trạng thái lỗi. Tránh ghi nguyên payload nhạy cảm. Với metric, cần kiểm soát cardinality của label; không tạo label biến đổi không giới hạn theo mỗi request.

## 14. Checklist hoàn thành bài thực hành

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Service discovery | `inventory-service` có ba instance hợp lệ |
| Metadata | Ba instance mang weight lần lượt `5`, `3`, `2` |
| Supplier chain | Caller có bước `withWeighted()` cho đúng service ID |
| Client | HTTP client được tích hợp LoadBalancer và gọi bằng service ID |
| Endpoint chẩn đoán | Mỗi replica trả instance ID riêng |
| Phân phối | Sau đủ request, traffic có xu hướng gần tỉ lệ mục tiêu trong điều kiện ổn định |
| Lọc instance | Instance bị loại bởi health/zone không còn tham gia tổng trọng số |
| Refresh | Trọng số thay đổi được phản ánh sau chu kỳ discovery/cache phù hợp |
| Retry/timeout | Có cấu hình xử lý lỗi; số lượt attempt được phân biệt với request logic |
| Quan sát | Có khả năng đối chiếu instance được chọn, response, lỗi và latency |

## 15. Những điểm cần nhớ

- Trọng số diễn tả **mức ưu tiên tương đối** giữa các `ServiceInstance`, thường được truyền bằng metadata `weight`.
- Tỉ lệ mục tiêu được tính từ trọng số của **tập ứng viên còn hợp lệ**, không phải mọi instance từng được đăng ký.
- `WeightedServiceInstanceListSupplier` có thể được ghép bằng `ServiceInstanceListSupplier.builder().withWeighted()`; chỉ gắn metadata mà không bật cơ chế hiểu trọng số thì chưa đủ.
- Nguồn metadata có thể là SimpleDiscoveryClient, registry động hoặc discovery adapter; điều quyết định là `ServiceInstance.getMetadata()` phía caller nhìn thấy gì.
- Cache, health check, zone, hint và retry đều có thể ảnh hưởng phân phối thực tế.
- Weight không bảo đảm tỉ lệ chính xác trên mẫu nhỏ, không thay thế health check, timeout hay tự động cân bằng theo CPU.
- Đo đầy đủ số lần chọn, lượt thử, response thành công và lỗi trước khi đánh giá một chính sách phân phối.

Hiểu trọng số cùng nguồn metadata giúp bạn quyết định replica nào nên nhận nhiều traffic hơn và kiểm chứng chính sách đó trong giao tiếp giữa các dịch vụ dùng Spring Cloud LoadBalancer.

