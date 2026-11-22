# Quan sát tính năng qua features và trạng thái qua serviceregistry

> **Chương:** Quan sát  
> **Module:** SPRING_CLOUD_CORE

Một ứng dụng Spring Cloud có thể có nhiều capability được nạp từ các module khác nhau: service discovery, load balancing, circuit breaker, service registry hoặc các tích hợp riêng. Khi vận hành, chỉ biết dependency có trong build file chưa đủ để xác nhận capability đã được tạo trong ApplicationContext. Đồng thời, biết ứng dụng có bean discovery cũng chưa cho biết instance hiện tại đang được registry xem là UP hay OUT_OF_SERVICE.

Spring Cloud Commons cung cấp hai Actuator endpoint bổ trợ nhau:

- **`/actuator/features`** cho biết những feature được các module khai báo và feature nào đang được nhận diện là enabled.
- **`/actuator/serviceregistry`** đọc trạng thái của Registration hiện tại và cho phép yêu cầu provider cập nhật trạng thái đó.

Endpoint thứ nhất giúp quan sát capability của ứng dụng; endpoint thứ hai giúp quan sát và điều khiển trạng thái đăng ký instance của chính ứng dụng. Hai endpoint không thay thế health/readiness, cũng không cung cấp danh sách đầy đủ mọi service trong registry. Bài này trình bày cách đọc, kết hợp và bảo vệ hai góc quan sát đó trong **SPRING_CLOUD_CORE**.

## 1. Hai câu hỏi vận hành khác nhau

Khi một dịch vụ không được client gọi tới hoặc một tính năng không hoạt động, cần tách hai câu hỏi:

1. Ứng dụng đã tạo capability cần thiết trong ApplicationContext chưa?
2. Instance hiện tại đang có trạng thái gì trong service registry?

Ví dụ, một ứng dụng có thể đã tạo bean `DiscoveryClient` và `LoadBalancerClient`, nhưng instance của nó lại được đánh dấu `OUT_OF_SERVICE` trong Eureka. Ngược lại, ứng dụng có thể đang được registry xem là `UP` nhưng không có bean LoadBalancer vì dependency hoặc auto-configuration chưa được kích hoạt.

| Tình huống | Endpoint hữu ích | Điều cần xác minh |
| --- | --- | --- |
| Không rõ discovery client nào được tạo | `features` | Abstract feature DiscoveryClient và implementation class |
| Muốn xác nhận LoadBalancer có trong context | `features` | Feature LoadBalancerClient có được nhận diện là enabled không |
| Instance đã đăng ký nhưng không nhận traffic | `serviceregistry` | Trạng thái registration hiện tại và semantics của provider |
| Muốn tạm đưa instance ra khỏi traffic | `serviceregistry` | Provider có hỗ trợ trạng thái như OUT_OF_SERVICE không |
| Không rõ ứng dụng có sẵn sàng nhận request không | `health` hoặc readiness | Health contributor và readiness state |

Features cho biết capability đã được khai báo và nhận diện trong context. ServiceRegistry cho biết trạng thái của registration cụ thể. Health/readiness phản ánh trạng thái phục vụ theo các health contributor và chính sách triển khai.

## 2. Features Actuator Endpoint

Spring Cloud Commons cung cấp endpoint có ID `features`. Với Actuator dùng base path mặc định, URL HTTP là:

~~~http
GET /actuator/features
~~~

Endpoint trả về hai nhóm chính:

- `enabled`: các feature được khai báo và nhận diện là đang bật.
- `disabled`: tên các abstract feature đã khai báo nhưng không tìm thấy bean tương ứng trong ApplicationContext.

Một feature trong `enabled` có metadata như:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên feature; với abstract feature là tên contract, với named feature là tên được khai báo |
| `type` | Tên đầy đủ của class implementation hoặc class đại diện |
| `version` | Package implementation version nếu metadata có sẵn |
| `vendor` | Package implementation vendor nếu metadata có sẵn |

Ví dụ response minh họa:

~~~json
{
  "enabled": [
    {
      "name": "DiscoveryClient",
      "type": "com.example.discovery.ConsulDiscoveryClient",
      "version": "4.2.0",
      "vendor": "Example"
    },
    {
      "name": "Partner API",
      "type": "com.example.partner.PartnerApiClient",
      "version": "1.3.0",
      "vendor": "Example"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
~~~

Các giá trị version và vendor chỉ là dữ liệu minh họa. Nếu package không cung cấp Implementation-Version hoặc Implementation-Vendor trong manifest, các trường tương ứng có thể là null.

### 2.1. Abstract feature

Abstract feature đại diện cho một contract có kiểu, thường là interface hoặc abstract class. Ví dụ Spring Cloud Commons có thể khai báo:

- `DiscoveryClient`
- `LoadBalancerClient`
- `LockService`

Feature provider khai báo contract qua bean `HasFeatures`. Features Endpoint tìm bean theo kiểu contract trong ApplicationContext:

- Nếu có bean, endpoint đưa feature vào `enabled` và lấy class thực tế của bean để tạo metadata.
- Nếu không có bean, endpoint đưa tên đơn giản của contract vào `disabled`.

Ví dụ module khai báo hai contract:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DiscoveryFeatureConfiguration {

    @Bean
    HasFeatures discoveryFeatures() {
        return HasFeatures.abstractFeatures(
                DiscoveryClient.class,
                LoadBalancerClient.class);
    }
}
~~~

Nếu context có DiscoveryClient nhưng không có LoadBalancerClient, endpoint có thể báo DiscoveryClient trong enabled và LoadBalancerClient trong disabled. Điều đó giúp nhận ra capability nào chưa được tạo.

### 2.2. Named feature

Named feature dành cho capability không có một interface/abstract class chung để kiểm tra bean theo contract. Ví dụ có thể là API Gateway, Circuit Breaker, Spring Cloud Bus hoặc một client nội bộ.

Một named feature được khai báo với tên và class đại diện:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerFeatureConfiguration {

    @Bean
    HasFeatures partnerFeature(PartnerApiClient client) {
        return HasFeatures.namedFeatures(
                new NamedFeature("Partner API", PartnerApiClient.class));
    }
}
~~~

Named feature được ghi nhận dựa trên khai báo trong `HasFeatures`. Endpoint không tự kiểm tra health của API đối tác và cũng không tự ping hệ thống từ xa. Vì vậy, hãy đặt bean khai báo feature trong cùng cấu hình có điều kiện với capability thật, hoặc phụ thuộc bean implementation như ví dụ trên.

### 2.3. Features không phải dependency tree

Endpoint không quét mọi JAR để tạo một danh sách đầy đủ tất cả thư viện trong classpath. Các module hoặc ứng dụng cần khai báo feature bằng `HasFeatures`. Do đó:

- Một dependency có thể nằm trong classpath nhưng không xuất hiện nếu không khai báo feature.
- Một abstract feature có thể xuất hiện trong disabled nếu contract được khai báo nhưng bean implementation không tồn tại.
- Một named feature xuất hiện trong enabled vì đã được khai báo, không có nghĩa hệ thống từ xa đang khỏe.
- Version/vendor phản ánh package metadata của class feature, không phải báo cáo BOM hoặc SBOM của toàn ứng dụng.

Không dùng Features Endpoint làm công cụ duy nhất để kiểm tra license, CVE, dependency convergence hoặc tính tương thích Spring Boot/Spring Cloud.

## 3. Service Registry Actuator Endpoint

Spring Cloud Commons cung cấp endpoint có ID `serviceregistry`. Với base path mặc định:

~~~http
GET /actuator/serviceregistry
~~~

Endpoint này dựa vào bean `Registration` trong Spring ApplicationContext. Khi có registration hiện tại, GET trả về trạng thái mà implementation `ServiceRegistry` cung cấp cho registration đó.

Ví dụ response minh họa với một provider có trạng thái dạng chuỗi:

~~~json
"UP"
~~~

Nếu endpoint không có Registration để truy vấn, implementation endpoint có thể trả HTTP 404 cùng thông báo `no registration found`. Đây là dấu hiệu cần kiểm tra registration bean và discovery provider, không phải bằng chứng rằng mọi dịch vụ trong registry đều không tồn tại.

### 3.1. Registration và ServiceRegistry

`Registration` là marker interface biểu diễn metadata của một instance. Một registration thường chứa thông tin như service ID, host, port, secure flag, instance ID và metadata tùy provider.

`ServiceRegistry` là abstraction thực hiện thao tác với registration. Các thao tác cốt lõi gồm:

~~~java
public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    void close();

    void setStatus(R registration, String status);

    <T> T getStatus(R registration);
}
~~~

Đây là hình dạng khái quát của contract; chữ ký generic và nullability cụ thể có thể khác theo release. Các implementation như Eureka, Consul hoặc Zookeeper cung cấp kiểu Registration và ServiceRegistry riêng.

ServiceRegistry Endpoint không truy vấn toàn bộ danh sách instance của mọi service. Nó nhận registration hiện tại được tích hợp với ứng dụng rồi gọi `getStatus(registration)` để đọc trạng thái.

### 3.2. GET: đọc trạng thái registration

Ví dụ:

~~~bash
curl http://localhost:8080/actuator/serviceregistry
~~~

Kết quả phụ thuộc provider. Một số implementation trả về trạng thái dạng chuỗi, implementation khác có thể trả về một cấu trúc hoặc giá trị khác. Hãy xem tài liệu của provider đang dùng để diễn giải chính xác.

GET chỉ đọc trạng thái của registration hiện tại. Nó không chứng minh:

- Tất cả instance của service đều khỏe.
- Client ở mọi network đều truy cập được instance.
- Instance đã vượt qua readiness probe.
- Các dependency nghiệp vụ như database hoặc message broker đang hoạt động.
- Registry đã phân phối trạng thái mới tới tất cả client.

### 3.3. POST: yêu cầu thay đổi trạng thái

Endpoint hỗ trợ POST tới cùng URL với JSON body có field `status`:

~~~bash
curl -X POST   -H "Content-Type: application/json"   -d '{"status":"OUT_OF_SERVICE"}'   http://localhost:8080/actuator/serviceregistry
~~~

POST gọi `ServiceRegistry.setStatus(registration, status)` cho registration hiện tại. Giá trị hợp lệ và ý nghĩa của nó do provider quyết định.

Ví dụ, Eureka hỗ trợ các trạng thái thường gặp:

- `UP`
- `DOWN`
- `OUT_OF_SERVICE`
- `UNKNOWN`

Không mặc định các trạng thái này được mọi provider hỗ trợ hoặc có cùng tác dụng. Trước khi tự động hóa thao tác POST, hãy đọc tài liệu implementation cụ thể và kiểm thử trên môi trường không ảnh hưởng traffic production.

### 3.4. POST không phải register hoặc deregister

Thay đổi status và thay đổi vòng đời registration là các thao tác khác nhau:

| Thao tác | API khái niệm | Ý nghĩa |
| --- | --- | --- |
| Đăng ký instance | `ServiceRegistry.register(registration)` | Công bố registration với registry |
| Hủy đăng ký | `ServiceRegistry.deregister(registration)` | Gỡ registration khỏi registry |
| Đọc trạng thái | `ServiceRegistry.getStatus(registration)` | Lấy trạng thái hiện tại |
| Đổi trạng thái | `ServiceRegistry.setStatus(registration, status)` | Yêu cầu provider cập nhật trạng thái |

POST tới `/actuator/serviceregistry` thực hiện thao tác đổi trạng thái. Nó không tự tạo registration mới và không tương đương với deregister. Nếu mục tiêu là gỡ hẳn instance, hãy dùng lifecycle hoặc API deregistration phù hợp của provider.

## 4. Hai endpoint bổ trợ nhau như thế nào?

Có thể xem chúng như hai lớp quan sát khác nhau:

~~~mermaid
flowchart TB
    A["Spring ApplicationContext"]
    A --> B["HasFeatures beans"]
    B --> C["/actuator/features"]
    C --> D["Capability enabled / disabled"]
    A --> E["Registration bean"]
    E --> F["ServiceRegistry implementation"]
    F --> G["/actuator/serviceregistry"]
    G --> H["Status của registration hiện tại"]
    D --> I["Đối chiếu cấu hình và capability"]
    H --> J["Đối chiếu trạng thái instance trong registry"]
~~~

Ví dụ ứng dụng `order-service`:

- Features báo `DiscoveryClient` enabled: ứng dụng có bean discovery.
- Features báo `LoadBalancerClient` disabled: context chưa có bean load-balancer contract được khai báo.
- ServiceRegistry báo `OUT_OF_SERVICE`: provider đang xem registration của instance hiện tại là ngoài phục vụ.
- Health báo DOWN: một hoặc nhiều health contributor không đạt điều kiện.

Bốn kết quả nói về bốn khía cạnh khác nhau. Không thể suy luận rằng LoadBalancer disabled là nguyên nhân duy nhất khiến instance OUT_OF_SERVICE; trạng thái registry có thể được cập nhật từ provider, thao tác quản trị hoặc quy trình vận hành khác.

## 5. Cấu hình expose hai endpoint qua Actuator

Ứng dụng cần Spring Boot Actuator và Spring Cloud Commons cùng các integration phù hợp.

Dependency Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Expose hai endpoint qua HTTP:

~~~yaml
spring:
  cloud:
    features:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - serviceregistry
~~~

Hai cấu hình có mục đích khác nhau:

- `spring.cloud.features.enabled` điều khiển việc tạo Features Endpoint; nó không bật/tắt các capability như DiscoveryClient hay LoadBalancer.
- `management.endpoints.web.exposure.include` điều khiển endpoint nào được truy cập qua HTTP.
- `serviceregistry` cần integration service registry và Registration bean phù hợp để đọc trạng thái.

Trong Spring Boot, chỉ `health` được expose qua HTTP theo mặc định. Có dependency Actuator không đồng nghĩa các endpoint khác tự động được mở. Nếu ứng dụng thay đổi `management.endpoints.web.base-path` hoặc dùng management port riêng, URL thực tế cũng thay đổi.

Ví dụ đổi base path:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Khi đó endpoint sẽ nằm dưới `/manage/features` và `/manage/serviceregistry`. Có thể xem trang discovery của Actuator hoặc cấu hình management để xác định URL thật.

### 5.1. Khi endpoint không xuất hiện

Nếu GET trả 404, hãy kiểm tra theo thứ tự:

1. Spring Boot Actuator có trong runtime classpath không?
2. Spring Cloud Commons và discovery/registry provider có đúng dependency không?
3. Endpoint có được tạo và được phép truy cập không?
4. `management.endpoints.web.exposure.include` có chứa endpoint cần dùng không?
5. Base path và management port có đúng không?
6. Với `serviceregistry`, context có Registration bean phù hợp không?
7. Provider có tạo ServiceRegistry implementation và gắn với Registration hiện tại không?

Không kết luận một capability bị tắt chỉ vì endpoint chưa expose qua HTTP. Exposure là lớp truy cập quản trị; feature bean có thể vẫn tồn tại bên trong context.

## 6. Registration tự động và trạng thái qua serviceregistry

Theo mặc định, nhiều ServiceRegistry integration tự đăng ký instance đang chạy. Có thể điều khiển auto-registration bằng thuộc tính chung:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true
~~~

Có thể tắt auto-registration bằng:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Hoặc dùng `@EnableDiscoveryClient(autoRegister = false)` trong cấu hình ứng dụng nếu phiên bản và provider hỗ trợ cách này.

Cần phân biệt ba khái niệm:

- Auto-registration điều khiển việc tích hợp tự đăng ký instance theo lifecycle.
- Registration bean là metadata instance mà provider dùng.
- ServiceRegistry Endpoint đọc hoặc cập nhật status của registration hiện tại.

Không suy luận rằng tắt auto-registration luôn làm mất Registration bean hoặc luôn khiến endpoint trả 404. Điều đó phụ thuộc provider và cấu hình. Hãy kiểm tra bean, hành vi thực tế và tài liệu release đang dùng.

### 6.1. Sự kiện trước và sau registration

Spring Cloud Commons định nghĩa các event liên quan tới auto-registration, thường gồm:

- `InstancePreRegisteredEvent`: phát trước khi đăng ký instance.
- `InstanceRegisteredEvent`: phát sau khi registration được thực hiện.

Ứng dụng có thể dùng listener để ghi log, bổ sung quan sát hoặc phối hợp quy trình khởi động. Các event auto-registration này không được phát khi thuộc tính `spring.cloud.service-registry.auto-registration.enabled` được đặt thành `false`.

Không dùng listener registration event thay cho GET status endpoint: event mô tả một thời điểm trong lifecycle, còn endpoint đọc trạng thái mà provider trả về tại thời điểm truy vấn.

## 7. Diễn giải trạng thái theo provider

`ServiceRegistry` cố ý để trạng thái là chuỗi hoặc kiểu do implementation quyết định. Điều này giúp abstraction dùng được với nhiều registry, nhưng cũng có nghĩa status không có semantics thống nhất hoàn toàn.

### 7.1. Eureka

Eureka thường dùng các trạng thái như:

| Trạng thái | Ý nghĩa khái quát |
| --- | --- |
| `UP` | Instance được đánh dấu hoạt động |
| `DOWN` | Instance được đánh dấu không hoạt động |
| `OUT_OF_SERVICE` | Instance được đánh dấu không phục vụ traffic |
| `UNKNOWN` | Trạng thái chưa xác định |

Ví dụ đưa instance ra khỏi phục vụ:

~~~bash
curl -X POST   -H "Content-Type: application/json"   -d '{"status":"OUT_OF_SERVICE"}'   http://localhost:8080/actuator/serviceregistry
~~~

Việc client ngừng chọn instance còn phụ thuộc cách Eureka server, discovery client và load-balancing integration xử lý trạng thái. Hãy kiểm tra danh sách instance thực tế từ một client sau khi thay đổi.

### 7.2. Zookeeper

Spring Cloud Zookeeper có implementation ServiceRegistry riêng. Tài liệu Zookeeper mô tả trạng thái `OUT_OF_SERVICE` được biểu diễn qua metadata và được service-instance supplier của Zookeeper LoadBalancer lọc khỏi danh sách instance. Chi tiết này thuộc integration Zookeeper; không áp dụng tự động cho registry khác.

### 7.3. Consul và các provider khác

Mỗi provider có cách biểu diễn health/status, đăng ký, lease, heartbeat và lọc instance riêng. Không gửi một chuỗi trạng thái chỉ vì nó hợp lệ ở Eureka rồi kỳ vọng Consul hoặc Zookeeper hiểu cùng ý nghĩa.

Trước khi thay đổi status, hãy kiểm tra:

- Provider có hỗ trợ status đó không?
- Status được lưu ở registry hay chỉ trong client cục bộ?
- Discovery client có lọc instance theo status không?
- Thay đổi có được đồng bộ tới client khác không và mất bao lâu?
- Status có bị health check hoặc heartbeat tiếp theo ghi đè không?
- Cách khôi phục trạng thái UP là gì?

## 8. Tình huống vận hành: đưa instance ra khỏi traffic

Giả sử một instance `catalog-service` cần bảo trì:

1. Xem `/actuator/features` để xác nhận capability liên quan vẫn được tạo.
2. Xem `/actuator/serviceregistry` để ghi nhận status hiện tại.
3. Kiểm tra provider hỗ trợ `OUT_OF_SERVICE` và status có được load balancer lọc không.
4. Gửi POST đổi status theo contract provider.
5. Đọc lại GET để xác nhận trạng thái mà provider trả về.
6. Từ một client khác, kiểm tra instance có còn nằm trong danh sách được chọn hay không.
7. Chờ request đang chạy kết thúc theo chính sách drain của ứng dụng.
8. Thực hiện bảo trì.
9. Gửi status phục hồi nếu provider yêu cầu, rồi xác minh lại từ registry và client.

Ví dụ lệnh cập nhật:

~~~bash
curl -X POST   -H "Content-Type: application/json"   -d '{"status":"OUT_OF_SERVICE"}'   http://localhost:8080/actuator/serviceregistry
~~~

Sau đó đọc lại:

~~~bash
curl http://localhost:8080/actuator/serviceregistry
~~~

Không chỉ dựa vào response thành công của POST. Hãy xác nhận GET, trạng thái ở registry và hành vi từ phía client. Provider có thể chấp nhận yêu cầu nhưng có độ trễ trước khi các client quan sát được thay đổi.

## 9. Kết hợp với health và readiness

Features và ServiceRegistry không thay thế health endpoint:

| Endpoint | Trả lời câu hỏi | Không chứng minh |
| --- | --- | --- |
| `/actuator/features` | Capability nào được khai báo và enabled? | Dịch vụ từ xa đang khỏe hoặc bean xử lý request thành công |
| `/actuator/serviceregistry` | Registration hiện tại có status gì? | Toàn bộ dependency của ứng dụng khỏe |
| `/actuator/health` | Health contributor báo trạng thái nào? | Instance đã được registry phân phối đúng cho mọi client |
| `/actuator/health/readiness` (khi readiness group được bật) | Ứng dụng có sẵn sàng nhận traffic theo readiness group không? | Mọi service khác đều hoạt động |

Một ứng dụng có thể có feature enabled nhưng health DOWN. Registration có thể UP trong khi readiness chưa đạt. Ngược lại, readiness nội bộ có thể đạt nhưng registry vẫn chưa cập nhật status do độ trễ hoặc lỗi kết nối.

Với Kubernetes hoặc nền tảng điều phối, tiếp tục dùng liveness/readiness probe theo chính sách triển khai. Không dùng một status chuỗi từ registry làm probe duy nhất.

## 10. Bảo mật endpoint và kiểm soát thao tác POST

`features` và `serviceregistry` tiết lộ thông tin nội bộ. Đặc biệt, `serviceregistry` có write operation có thể thay đổi trạng thái instance và ảnh hưởng việc client chọn endpoint.

Khuyến nghị:

- Chỉ expose hai endpoint trên management network hoặc cổng quản trị riêng.
- Dùng Spring Security hoặc cơ chế xác thực tương đương.
- Cấp quyền GET cho nhóm vận hành cần quan sát.
- Giới hạn POST `serviceregistry` cho nhóm có trách nhiệm điều khiển traffic.
- Không expose toàn bộ Actuator bằng wildcard nếu không có kiểm soát mạng và quyền phù hợp.
- Ghi audit log cho người gửi POST, status cũ/mới và thời điểm thay đổi.
- Không để credential trong script hoặc command history được chia sẻ.
- Kiểm thử quy trình khôi phục status để tránh instance bị giữ OUT_OF_SERVICE ngoài dự kiến.

Ví dụ cấu hình chỉ expose hai endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,features,serviceregistry
~~~

Exposure chỉ làm endpoint có thể được truy cập qua HTTP; nó không tự thay thế authentication và authorization. Nếu ứng dụng có custom SecurityFilterChain, hãy cấu hình rõ quyền đọc và quyền ghi cho từng endpoint.

## 11. Kiểm thử hai endpoint

Nên kiểm thử riêng feature inventory và registration status vì chúng có dependency và semantics khác nhau.

### 11.1. Kiểm thử Features Endpoint

Với Spring MVC test support, có thể kiểm tra endpoint được expose và response có cấu trúc mong đợi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,features,serviceregistry"
})
@AutoConfigureMockMvc
class FeaturesEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsFeatureInventory() throws Exception {
        mockMvc.perform(get("/actuator/features"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").isArray())
                .andExpect(jsonPath("$.disabled").isArray());
    }
}
~~~

Test này kiểm tra cấu trúc endpoint. Có thể bổ sung assertion cho feature cụ thể nếu test context đã khai báo bean `HasFeatures` và implementation tương ứng. Không phụ thuộc thứ tự phần tử trong danh sách.

### 11.2. Kiểm thử ServiceRegistry Endpoint

Test này cần một provider test hoặc registration fixture phù hợp. Khi context có Registration bean:

~~~java
@Test
void readsCurrentRegistrationStatus() throws Exception {
    mockMvc.perform(get("/actuator/serviceregistry"))
            .andExpect(status().isOk());
}
~~~

Nếu context không có Registration bean, endpoint có thể trả 404 `no registration found`. Đây là nhánh cần được test nếu ứng dụng có thể chạy ở chế độ không đăng ký.

### 11.3. Kiểm thử POST theo provider

Một integration test có thể gửi status được provider hỗ trợ:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void updatesRegistrationStatus() throws Exception {
    mockMvc.perform(post("/actuator/serviceregistry")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"status\":\"OUT_OF_SERVICE\"}"))
            .andExpect(status().is2xxSuccessful());

    mockMvc.perform(get("/actuator/serviceregistry"))
            .andExpect(status().isOk());
}
~~~

Đây là khung test, không phải cam kết mọi provider chấp nhận `OUT_OF_SERVICE`. Test thực tế phải dùng giá trị status hợp lệ của provider, sau đó xác nhận trạng thái qua API provider hoặc hành vi discovery/load-balancing. Nếu cần kiểm tra lỗi provider, thêm test status không hợp lệ và xác nhận cách exception được chuyển thành HTTP response theo phiên bản đang dùng.

### 11.4. Kiểm thử quyền truy cập

Bổ sung test bảo mật để xác nhận:

- Người không có quyền không đọc được thông tin endpoint theo policy.
- Người chỉ có quyền quan sát không thể POST đổi status.
- Người có quyền vận hành được phép thực hiện POST.
- Audit log ghi nhận thao tác thay đổi status.

Không dùng test status thành công làm bằng chứng cho policy bảo mật.

## 12. Lỗi thường gặp và cách tránh

1. **Nhầm features với health:** feature enabled chỉ xác nhận capability được nhận diện trong context.
2. **Nhầm serviceregistry với danh sách service:** endpoint đọc registration hiện tại, không liệt kê mọi service trong registry.
3. **GET serviceregistry trả 404:** kiểm tra Registration bean và provider integration.
4. **features có disabled:** kiểm tra HasFeatures declaration và bean contract tương ứng.
5. **Named feature luôn hiện enabled:** đặt HasFeatures bean trong cấu hình có điều kiện cùng capability thật.
6. **POST status không được hỗ trợ:** kiểm tra danh sách status của provider.
7. **POST thành công nhưng client vẫn gọi instance:** kiểm tra semantics lọc status, propagation delay và cache của discovery client/load balancer.
8. **Dùng POST để deregister:** POST chỉ gọi setStatus; dùng lifecycle hoặc deregister API khi cần gỡ registration.
9. **Tắt auto-registration rồi cho rằng endpoint chắc chắn biến mất:** kiểm tra Registration bean thực tế.
10. **Expose endpoint công khai:** giới hạn management network và quyền truy cập.
11. **Dùng status làm readiness:** kiểm tra readiness group và health contributor riêng.
12. **Không có quy trình phục hồi:** xác định status khôi phục và xác minh sau khi bảo trì.

## 13. Quy trình quan sát và xử lý sự cố

Khi một service không được gọi như mong đợi, thực hiện theo trình tự:

1. Gọi `/actuator/features` để xem các capability được khai báo và trạng thái enabled/disabled.
2. Nếu feature abstract nằm trong disabled, kiểm tra dependency, auto-configuration, profile và bean contract.
3. Gọi `/actuator/serviceregistry` để đọc status của registration hiện tại.
4. Nếu endpoint trả 404, kiểm tra Registration bean và integration provider.
5. Đối chiếu status với danh sách trạng thái được provider hỗ trợ.
6. Kiểm tra health/readiness và log của ứng dụng.
7. Nếu cần thay status, dùng POST với JSON body và quyền vận hành phù hợp.
8. Đọc lại GET để xác nhận provider trả status mới.
9. Kiểm tra từ client để xác nhận discovery/load balancing đã phản ánh thay đổi.
10. Ghi nhận status khôi phục và quy trình hoàn nguyên.

Không dừng điều tra ở một endpoint. Kết hợp feature inventory, registration status, health/readiness, log và quan sát từ phía client để có bức tranh đầy đủ.

## 14. Điểm cần ghi nhớ

`/actuator/features` trả lời capability nào được các module khai báo và nhận diện là enabled trong ApplicationContext. `/actuator/serviceregistry` đọc status của Registration hiện tại và cho phép yêu cầu provider cập nhật status qua POST với JSON field `status`. Status hợp lệ và ảnh hưởng tới discovery phụ thuộc implementation ServiceRegistry đang dùng.

Features không chứng minh dịch vụ từ xa đang khỏe; ServiceRegistry không liệt kê toàn bộ registry và POST status không phải register/deregister. Hãy kết hợp hai endpoint với health/readiness, kiểm tra hành vi từ client và bảo vệ chặt quyền ghi để quan sát và vận hành các dịch vụ trong **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions, Enabled Features và Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Zookeeper — Service Registry and Instance Status](https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html)
- [Spring Boot Actuator — Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
