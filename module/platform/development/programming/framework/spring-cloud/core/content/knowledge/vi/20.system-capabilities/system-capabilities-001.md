# Endpoint features và thông tin khả năng đang hoạt động

> **Chương:** Khả năng hệ thống  
> **Module:** SPRING_CLOUD_CORE

Khi vận hành một ứng dụng Spring Cloud, đội phát triển thường cần biết những capability nào thực sự được cấu hình trong ApplicationContext: ứng dụng có DiscoveryClient hay không, có LoadBalancer hay không, module tích hợp nào đã được bật và phiên bản implementation đang chạy là gì. Kiểm tra riêng dependency trong build file chưa đủ, vì auto-configuration có thể bị điều kiện hóa, bean có thể không được tạo hoặc một provider có thể bị thay thế bởi implementation khác.

Spring Cloud Commons cung cấp **Features Actuator Endpoint** để công bố inventory về các tính năng được khai báo và trạng thái enabled/disabled của chúng. Endpoint thường được truy cập qua `/actuator/features` khi Actuator dùng base path mặc định. Nó cung cấp thông tin loại feature, tên, phiên bản và vendor cho feature đang bật; feature abstract không có bean tương ứng được báo trong danh sách disabled.

Bài này trình bày cấu trúc dữ liệu của endpoint, cách Spring Cloud phát hiện abstract feature, cách khai báo named feature qua `HasFeatures`, cấu hình expose và bảo vệ endpoint, cùng cách kiểm thử và diễn giải kết quả trong module **SPRING_CLOUD_CORE**.

## 1. Features Endpoint giải quyết nhu cầu gì?

Một ứng dụng có thể khai báo nhiều starter và thư viện Spring Cloud. Nhưng sự có mặt của một dependency không đồng nghĩa capability tương ứng đang hoạt động:

- Dependency có thể không được auto-configuration kích hoạt do thiếu điều kiện.
- Một bean có thể bị loại khỏi context bởi profile hoặc property.
- Ứng dụng có thể dùng implementation discovery khác với dự kiến.
- Một capability có thể được khai báo bằng một feature provider riêng.
- Version trong dependency tree có thể khác với version package metadata của implementation được endpoint báo cáo.

Features Endpoint cung cấp một góc nhìn ở cấp ApplicationContext. Nó tập hợp các feature được đăng ký qua những bean `HasFeatures` và xác định trạng thái cho từng loại feature.

Ví dụ câu hỏi có thể trả lời:

- Context hiện có bean triển khai `DiscoveryClient` không?
- `LoadBalancerClient` có được tạo trong context không?
- Module tích hợp có khai báo capability tên “Partner API” không?
- Implementation được báo cáo có package version và vendor nào?
- Một abstract feature được khai báo nhưng chưa có bean thì có xuất hiện trong danh sách disabled không?

Endpoint giúp chẩn đoán cấu hình và xác nhận auto-configuration. Nó không thay thế health check, readiness probe, kiểm tra kết nối mạng hay kiểm tra nghiệp vụ.

## 2. Endpoint và dữ liệu trả về

Spring Cloud Commons cung cấp Actuator endpoint có ID `features`. Với cấu hình web management mặc định của Spring Boot, URL thường là:

~~~http
GET /actuator/features
~~~

Nếu ứng dụng đổi `management.endpoints.web.base-path` hoặc chạy management server trên cổng riêng, địa chỉ thực tế cũng thay đổi. Endpoint cần Spring Boot Actuator và phần auto-configuration của Spring Cloud Commons tương ứng.

Dữ liệu trả về có hai nhóm chính:

| Trường | Nội dung |
| --- | --- |
| `enabled` | Các feature được xác định là đang bật; mỗi phần tử chứa metadata của feature |
| `disabled` | Tên các abstract feature đã khai báo nhưng không tìm thấy bean tương ứng |

Một phần tử trong `enabled` có các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `type` | Tên đầy đủ của class implementation (hoặc class được khai báo cho named feature) |
| `name` | Tên contract đối với abstract feature; tên được khai báo đối với named feature |
| `version` | Version lấy từ package implementation metadata |
| `vendor` | Vendor lấy từ package implementation metadata |

Ví dụ JSON minh họa:

~~~json
{
  "enabled": [
    {
      "type": "com.example.catalog.CatalogDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "2.4.1",
      "vendor": "Example Platform"
    },
    {
      "type": "com.example.partner.PartnerApiClient",
      "name": "Partner API",
      "version": "1.8.0",
      "vendor": "Example Platform"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
~~~

Các giá trị version/vendor trong ví dụ chỉ nhằm minh họa định dạng. Version và vendor có thể là null nếu package không cung cấp metadata tương ứng. Không nên coi các con số trong JSON ví dụ là phiên bản Spring Cloud thực tế của ứng dụng.

### 2.1. Endpoint không quét toàn bộ classpath

Features Endpoint không tự động liệt kê mọi class hoặc mọi dependency trong JAR. Các module tích hợp và ứng dụng khai báo feature qua bean `HasFeatures`. Endpoint tổng hợp những khai báo đó rồi kiểm tra theo quy tắc của từng loại feature.

Vì vậy, nếu một thư viện có mặt trên classpath nhưng không đăng ký feature tương ứng, endpoint có thể không hiển thị thư viện đó. Ngược lại, việc khai báo named feature cần được đặt trong cấu hình có điều kiện phù hợp để tránh báo capability là enabled khi thành phần thật sự chưa được tạo.

## 3. Hai loại feature: abstract và named

Spring Cloud Commons phân biệt hai loại feature.

### 3.1. Abstract feature

Abstract feature đại diện cho một contract có kiểu rõ ràng, thường là interface hoặc abstract class mà implementation được đăng ký thành bean. Ví dụ:

- `DiscoveryClient`
- `LoadBalancerClient`
- `LockService`

Khi abstract feature được khai báo, endpoint tìm bean theo kiểu contract trong ApplicationContext:

- Nếu tìm được bean tương ứng, feature được đưa vào `enabled`.
- Nếu không tìm được bean, tên đơn giản của kiểu contract được đưa vào `disabled`.

Điều này giúp phát hiện trường hợp ứng dụng khai báo muốn có một capability nhưng auto-configuration không tạo bean tương ứng.

Ví dụ: ứng dụng khai báo `DiscoveryClient.class` là feature cần có. Nếu không có discovery provider hoặc không có bean triển khai, endpoint có thể báo `DiscoveryClient` trong danh sách disabled.

### 3.2. Named feature

Named feature dùng cho capability không có một abstraction interface/abstract class chung để endpoint tra cứu. Ví dụ có thể là API Gateway, Spring Cloud Bus, Circuit Breaker hoặc một tích hợp nội bộ.

Một named feature cần:

- Tên hiển thị.
- Class đại diện cho implementation hoặc thành phần cung cấp feature.

`NamedFeature` giữ tên và kiểu class dùng để lấy metadata type/version/vendor. Endpoint đưa named feature đã được khai báo vào `enabled`.

Điểm quan trọng: named feature được ghi nhận dựa trên bean `HasFeatures` khai báo nó; endpoint không tự kiểm tra một bean instance có đúng kiểu named feature hay không. Vì vậy, nên tạo bean khai báo named feature trong cùng cấu hình có điều kiện với capability thật hoặc yêu cầu bean triển khai trong method khai báo.

### 3.3. So sánh hai loại

| Tiêu chí | Abstract feature | Named feature |
| --- | --- | --- |
| Đại diện | Interface hoặc abstract class | Capability có tên riêng |
| Khai báo | Class contract | Tên và class implementation |
| Cách xác định enabled | Tìm bean theo kiểu contract trong ApplicationContext | Được khai báo trong HasFeatures |
| Cách xác định disabled | Không tìm thấy bean tương ứng | Không tự suy ra disabled nếu không có khai báo |
| Ví dụ | DiscoveryClient, LoadBalancerClient | API Gateway, Partner API |

Không dùng named feature thay cho abstract feature khi đã có một contract phù hợp. Abstract feature giúp endpoint kiểm tra bean thực sự tồn tại; named feature phù hợp với capability không có abstraction chung.

## 4. HasFeatures và NamedFeature

Spring Cloud Commons dùng bean `HasFeatures` để khai báo các feature mà module muốn endpoint quan sát. Có thể khai báo abstract feature hoặc named feature.

Ví dụ một module khai báo các abstraction mà nó phụ thuộc:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DiscoveryCapabilityConfiguration {

    @Bean
    HasFeatures discoveryFeatures() {
        return HasFeatures.abstractFeatures(
                DiscoveryClient.class,
                LoadBalancerClient.class);
    }
}
~~~

Endpoint sẽ kiểm tra các bean `DiscoveryClient` và `LoadBalancerClient` trong ApplicationContext. Nếu một kiểu không có bean, tên kiểu đó xuất hiện trong danh sách disabled.

Trong ứng dụng thực tế, Spring Cloud Commons hoặc discovery/load-balancer integration có thể đã khai báo các feature chuẩn. Không đăng ký lặp lại feature framework chỉ để làm endpoint có nhiều dòng hơn. Ví dụ trên minh họa cơ chế khai báo; hãy kiểm tra feature provider có sẵn trong phiên bản đang dùng trước khi bổ sung.

### 4.1. Khai báo named feature

Giả sử ứng dụng có một client tích hợp với hệ thống đối tác nhưng không có interface Spring Cloud Commons tương ứng. Có thể khai báo:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerCapabilityConfiguration {

    @Bean
    HasFeatures partnerApiFeature(PartnerApiClient partnerApiClient) {
        return HasFeatures.namedFeatures(
                new NamedFeature("Partner API", PartnerApiClient.class));
    }
}
~~~

Tham số `partnerApiClient` bảo đảm bean client tồn tại trước khi bean feature được tạo. Trong ví dụ, đối tượng client được inject để ràng buộc khai báo feature với cấu hình có client đó. Nếu capability chỉ được bật theo profile hoặc property, hãy đặt cấu hình này trong cùng điều kiện với bean client.

Không khai báo named feature ở một cấu hình luôn hoạt động nếu implementation thật có thể bị tắt. Nếu không, endpoint có thể báo “Partner API” trong enabled dù ứng dụng không có khả năng gọi hệ thống đối tác.

### 4.2. Đặt cấu hình feature theo điều kiện

Ví dụ capability chỉ tồn tại khi property được bật:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "partner.api",
        name = "enabled",
        havingValue = "true")
public class PartnerApiConfiguration {
    // Khai báo PartnerApiClient và HasFeatures tại đây.
}
~~~

Khi `partner.api.enabled=false`, cả client và bean khai báo named feature có thể không được tạo nếu chúng nằm trong cấu hình này. Điều đó giúp endpoint không báo nhầm capability là enabled.

Nếu một module dùng nhiều cấu hình điều kiện, hãy đảm bảo bean `HasFeatures` được bật/tắt cùng logic với capability mà nó mô tả.

## 5. Version và vendor được lấy từ đâu?

Features Endpoint hiển thị version và vendor dựa trên metadata của Java Package:

- `Package.getImplementationVersion()`
- `Package.getImplementationVendor()`

Đối với abstract feature, endpoint lấy implementation bean tìm được trong ApplicationContext rồi đọc package metadata của class thực tế. Đối với named feature, metadata được lấy từ class được truyền vào `NamedFeature`.

Điều này có một số hệ quả:

1. Nếu JAR được đóng gói với manifest có Implementation-Version và Implementation-Vendor, endpoint có thể hiển thị các giá trị đó.
2. Nếu metadata không có trong manifest hoặc class được chạy từ thư mục/classes không có metadata, giá trị có thể null.
3. Version hiển thị là metadata package của implementation, không phải bản tổng hợp dependency tree.
4. Version của feature không chứng minh phiên bản Spring Boot/Spring Cloud release train tương thích.

Ví dụ, endpoint báo version của một discovery client không có nghĩa toàn bộ hệ thống đã được kiểm tra tương thích. Muốn xác minh compatibility, vẫn cần dùng dependency management/BOM và cơ chế kiểm tra tương thích của Spring Cloud.

Không dùng trường version của Features Endpoint như nguồn duy nhất để lập inventory license, SBOM hoặc kiểm tra lỗ hổng. Các nhiệm vụ đó cần công cụ phân tích artifact và dependency chuyên biệt.

## 6. Bật và expose endpoint qua Actuator

Để truy cập endpoint qua HTTP, ứng dụng cần Actuator và web exposure tương ứng.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Cloud Commons cung cấp endpoint khi có Actuator endpoint API và điều kiện auto-configuration phù hợp. Thuộc tính `spring.cloud.features.enabled` mặc định là true trong cấu hình Spring Cloud Commons hiện hành; đặt false để tắt việc tạo Features Endpoint.

Ví dụ cấu hình expose:

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
          - info
          - features
~~~

Hai cấu hình có ý nghĩa khác nhau:

- `spring.cloud.features.enabled` điều khiển việc Spring Cloud tạo endpoint features.
- `management.endpoints.web.exposure.include` điều khiển endpoint nào được expose qua HTTP.

Nếu endpoint không xuất hiện, hãy kiểm tra dependency Actuator, property bật endpoint, web exposure, management base path và management port. Không nhầm việc endpoint chưa expose qua HTTP với việc capability bên trong ứng dụng bị disabled.

### 6.1. Truy cập endpoint

Với base path mặc định:

~~~bash
curl http://localhost:8080/actuator/features
~~~

Nếu ứng dụng cấu hình `management.endpoints.web.base-path` khác hoặc management server dùng port riêng, hãy điều chỉnh URL theo cấu hình đó.

Một số ứng dụng chỉ expose `health` mặc định. Vì vậy, có Actuator dependency chưa chắc đã làm `/actuator/features` truy cập được qua web. Hãy khai báo rõ endpoint cần expose trong từng môi trường.

### 6.2. Tắt endpoint khi không cần

Có thể tắt tính năng này:

~~~yaml
spring:
  cloud:
    features:
      enabled: false
~~~

Khi endpoint bị tắt, HTTP request tới path tương ứng thường không tìm thấy endpoint đã được đăng ký. Đây là quyết định về khả năng quan sát, không có nghĩa DiscoveryClient, LoadBalancer hay capability nghiệp vụ khác bị tắt.

## 7. Đọc kết quả để chẩn đoán cấu hình

Khi kiểm tra `/actuator/features`, nên đọc cả enabled và disabled.

### 7.1. Feature abstract xuất hiện trong enabled

Nếu `DiscoveryClient` có implementation bean, endpoint ghi nhận implementation class, tên, version và vendor. Có thể dùng thông tin này để xác nhận provider thực tế được tạo trong context.

Ví dụ, ứng dụng dự kiến dùng Consul nhưng endpoint cho thấy implementation khác. Khi đó cần kiểm tra dependency, auto-configuration conditions, profile và các bean do ứng dụng tự khai báo.

### 7.2. Feature abstract xuất hiện trong disabled

Nếu một abstract feature đã được khai báo nhưng không có bean tương ứng, tên contract sẽ xuất hiện trong disabled. Hãy kiểm tra:

- Starter/provider cần thiết có trong dependency graph không?
- Auto-configuration có bị exclude không?
- Property hoặc profile có vô tình tắt capability không?
- Bean có được tạo trong ApplicationContext đang quan sát không?
- Có điều kiện classpath hoặc bean khiến configuration back off không?

Một feature disabled không tự cho biết nguyên nhân cụ thể. Endpoint cho biết bean contract không được tìm thấy; cần kết hợp Condition Evaluation Report, log khởi động và các endpoint chẩn đoán khác để tìm lý do.

### 7.3. Named feature xuất hiện trong enabled

Với named feature, endpoint phản ánh bean `HasFeatures` đã khai báo capability. Nó không thực hiện health check tới dịch vụ đối tác hoặc xác nhận API từ xa đang trả lời.

Nếu named feature xuất hiện nhưng request tới hệ thống ngoài thất bại, hãy kiểm tra riêng health indicator, connectivity, credential, DNS, TLS và log client. Không diễn giải enabled thành “dịch vụ đích đang khỏe”.

## 8. Features Endpoint khác Health và Readiness như thế nào?

Các endpoint Actuator có mục đích khác nhau:

| Endpoint | Câu hỏi chính | Phạm vi |
| --- | --- | --- |
| `/actuator/features` | Capability nào được khai báo và đang được nhận diện là enabled? | Feature inventory trong ApplicationContext |
| `/actuator/health` | Ứng dụng và các health contributor có khỏe không? | Trạng thái health |
| `/actuator/info` | Ứng dụng công bố metadata thông tin nào? | Thông tin build/deployment tùy cấu hình |
| `/actuator/conditions` | Auto-configuration condition nào match hoặc không match? | Chẩn đoán điều kiện cấu hình |
| `/actuator/beans` | Những bean nào được đăng ký trong context? | Inventory bean |

Một DiscoveryClient có thể được báo enabled nhưng registry không truy cập được. Tương tự, named feature có thể được khai báo enabled trong khi endpoint đối tác đang lỗi. Health indicator và readiness probe mới phù hợp để trả lời câu hỏi về tình trạng phục vụ tại thời điểm kiểm tra.

Với Kubernetes, không dùng Features Endpoint làm readiness probe duy nhất. Readiness cần phản ánh ứng dụng có thể nhận traffic hay không theo chính sách hệ thống; inventory feature không cung cấp kết luận đó.

## 9. Bảo mật thông tin capability

Features Endpoint có thể tiết lộ:

- Các thư viện hoặc integration đang sử dụng.
- Tên class implementation.
- Version và vendor metadata.
- Sự hiện diện hoặc vắng mặt của một số capability nội bộ.

Những thông tin này có thể hữu ích cho vận hành nhưng cũng giúp người ngoài suy đoán công nghệ và bề mặt tấn công. Do đó:

- Chỉ expose endpoint trên mạng quản trị hoặc qua lớp xác thực phù hợp.
- Không mở toàn bộ Actuator endpoints ra Internet.
- Áp dụng role/authorization cho người cần xem thông tin capability.
- Giới hạn log và lưu trữ response theo chính sách bảo mật.
- Không đưa secret, token hoặc cấu hình nhạy cảm vào tên feature hay metadata.
- Cân nhắc tắt endpoint ở môi trường không cần quan sát capability.

Không nhúng thông tin credential vào `NamedFeature`. Endpoint chỉ cần tên capability và class metadata; secret phải được quản lý ở secret store phù hợp.

## 10. Kiểm thử Features Endpoint

Có thể dùng Spring Boot integration test để xác nhận endpoint được expose và named feature đã khai báo xuất hiện trong kết quả.

Giả sử ứng dụng có class `PartnerApiClient` và cấu hình sau:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureInventoryConfiguration {

    @Bean
    PartnerApiClient partnerApiClient() {
        return new PartnerApiClient();
    }

    @Bean
    HasFeatures partnerApiFeature(PartnerApiClient client) {
        return HasFeatures.namedFeatures(
                new NamedFeature("Partner API", PartnerApiClient.class));
    }

    @Bean
    HasFeatures inventoryFeature() {
        return HasFeatures.abstractFeatures(InventoryClient.class);
    }
}
~~~

Trong ví dụ này, `InventoryClient` là interface do ứng dụng định nghĩa và chưa có implementation bean trong test context. Vì thế endpoint có thể đưa tên `InventoryClient` vào danh sách disabled. `PartnerApiClient` được tạo và named feature được khai báo cùng context.

Test HTTP:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,features"
})
@AutoConfigureMockMvc
@Import(FeatureInventoryConfiguration.class)
class FeaturesEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesDeclaredCapabilities() throws Exception {
        mockMvc.perform(get("/actuator/features"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled[*].name",
                        hasItem("Partner API")))
                .andExpect(jsonPath("$.disabled",
                        hasItem("InventoryClient")));
    }
}
~~~

Test giả định ứng dụng có Spring MVC test support, Spring Boot Actuator, Spring Cloud Commons và endpoint features được auto-configure. Nếu ứng dụng dùng WebFlux, dùng WebTestClient hoặc test client phù hợp. Nếu management base path đã đổi, điều chỉnh URL test.

### 10.1. Kiểm thử trường hợp endpoint bị tắt

Có thể tạo một test context riêng với:

~~~properties
spring.cloud.features.enabled=false
~~~

Sau đó xác nhận endpoint không được tạo/expose. Tách test context giúp tránh dùng chung ApplicationContext có endpoint đã được khởi tạo từ test khác.

### 10.2. Kiểm thử feature thực sự được kích hoạt

Đối với abstract feature, test nên xác nhận cả hai trường hợp:

- Có bean triển khai contract: tên feature xuất hiện trong enabled.
- Không có bean triển khai contract: tên feature xuất hiện trong disabled.

Đối với named feature, kiểm tra bean `HasFeatures` chỉ được tạo khi capability thực sự được bật. Đây là cách tránh báo cáo sai trạng thái do cấu hình khai báo không cùng điều kiện với implementation.

## 11. Lỗi thường gặp và cách tránh

1. **Có Actuator nhưng không truy cập được endpoint:** kiểm tra web exposure, base path và management port.
2. **Tưởng endpoint tự quét mọi dependency:** chỉ các feature được khai báo qua HasFeatures mới được tổng hợp.
3. **Nhầm named feature với bean được health-check:** named feature phản ánh khai báo; kiểm tra sức khỏe cần cơ chế riêng.
4. **Abstract feature nằm trong disabled:** kiểm tra bean contract, dependency, profile và auto-configuration conditions.
5. **Version hoặc vendor là null:** kiểm tra package manifest; không suy ra ứng dụng không có version.
6. **Đăng ký trùng feature framework:** kiểm tra HasFeatures bean đã có từ Spring Cloud integration trước khi khai báo thêm.
7. **Khai báo named feature luôn bật:** đặt HasFeatures bean trong cấu hình có điều kiện hoặc phụ thuộc bean implementation.
8. **Dùng endpoint làm readiness probe:** dùng health/readiness contributor phù hợp.
9. **Coi version feature là báo cáo dependency đầy đủ:** dùng dependency tree/SBOM cho inventory và compatibility.
10. **Expose endpoint công khai:** giới hạn mạng và bảo vệ bằng authentication/authorization.
11. **Tắt endpoint rồi nghĩ capability bị tắt:** `spring.cloud.features.enabled` chỉ điều khiển endpoint inventory.
12. **Không kiểm thử trạng thái disabled:** thêm test cho trường hợp contract bean không tồn tại.

## 12. Quy trình áp dụng trong dự án Spring Cloud

Khi muốn quan sát capability của một ứng dụng:

1. Thêm Spring Boot Actuator và xác nhận Spring Cloud Commons có mặt.
2. Xác định endpoint features được bật bằng `spring.cloud.features.enabled`.
3. Expose `features` qua management HTTP trong môi trường cần chẩn đoán.
4. Kiểm tra feature framework đã được các module tích hợp khai báo.
5. Dùng abstract feature cho contract có interface/abstract class.
6. Dùng named feature cho capability không có abstraction chung.
7. Đặt bean HasFeatures trong cấu hình có điều kiện phù hợp với implementation.
8. Đọc enabled/disabled và đối chiếu version/vendor metadata.
9. Kết hợp Conditions, Beans, Health và log để điều tra nguyên nhân.
10. Bảo vệ endpoint và không dùng nó thay thế readiness/health check.

## 13. Điểm cần ghi nhớ

Features Endpoint của Spring Cloud Commons cung cấp inventory về capability được khai báo trong ApplicationContext. Abstract feature được kiểm tra bằng cách tìm bean theo contract; named feature được đưa vào enabled khi được khai báo qua `HasFeatures`. Kết quả enabled có thể kèm type, name, version và vendor lấy từ package metadata; disabled liệt kê tên abstract feature không có bean tương ứng.

Endpoint này giúp xác minh cấu hình và chẩn đoán auto-configuration, nhưng không chứng minh dependency đang khỏe, endpoint từ xa truy cập được hay ứng dụng sẵn sàng nhận traffic. Hãy kết hợp nó với health/readiness, conditions và log, đồng thời bảo vệ thông tin capability trong môi trường triển khai của **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions, Enabled Features](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Boot Actuator — Endpoint Exposure](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
