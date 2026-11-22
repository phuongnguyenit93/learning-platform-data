# Bật tắt đăng ký tự động bằng thuộc tính hoặc annotation

> **Chương:** ServiceRegistry  
> **Module:** SPRING_CLOUD_CORE

Trong hệ thống Spring Cloud, một ứng dụng có thể cần tra cứu các dịch vụ khác nhưng không muốn tự đăng ký instance của chính nó vào service registry. Ví dụ, một batch worker chỉ gọi các dịch vụ nội bộ, một ứng dụng chạy trong integration test, hoặc một instance tạm thời không được phép xuất hiện trong danh sách endpoint phục vụ traffic.

Spring Cloud Commons cung cấp cơ chế điều khiển **auto-registration** ở cấp ứng dụng. Có thể tắt bằng thuộc tính `spring.cloud.service-registry.auto-registration.enabled=false` hoặc đặt `@EnableDiscoveryClient(autoRegister = false)` trên cấu hình ứng dụng. Hai cách này tác động đến quy trình tự đăng ký do Spring Cloud tích hợp; chúng cần được phân biệt với khả năng tra cứu registry và thao tác đăng ký thủ công.

Bài này giải thích cách chọn cách cấu hình, cách xác minh hành vi lúc khởi động và shutdown, cùng các trường hợp cần kiểm soát registration trong module **SPRING_CLOUD_CORE**.

## 1. Discovery và registration là hai chiều khác nhau

Service discovery thường bao gồm hai nhu cầu:

- **Discovery:** ứng dụng tìm các instance của dịch vụ khác theo service ID.
- **Registration:** ứng dụng công bố instance của chính nó để client khác có thể tìm thấy.

Một ứng dụng có thể cần discovery mà không cần registration. Ví dụ, `report-worker` có thể tra cứu `catalog-service` và `pricing-service` nhưng không cung cấp HTTP endpoint cho service khác gọi. Khi đó, tắt auto-registration không đồng nghĩa tắt discovery.

| Khả năng | Ý nghĩa | Có bị tắt bởi auto-registration=false? |
| --- | --- | --- |
| Tự đăng ký instance của ứng dụng | Gửi thông tin host, port, metadata tới registry khi startup | Có, đối với luồng auto-registration được Spring Cloud quản lý |
| Tra cứu service khác | Lấy instance theo service ID qua DiscoveryClient | Không |
| Chọn instance cho request | Load balancing trên danh sách instance | Không |
| Đăng ký thủ công qua ServiceRegistry | Code chủ động gọi API registration | Không mặc nhiên |
| Health check và trạng thái instance | Provider hoặc nền tảng cập nhật trạng thái | Không tự động bị tắt chỉ bởi thuộc tính này |

Vì vậy, trước khi tắt registration, hãy xác định ứng dụng có cần được service khác tìm thấy hay chỉ đóng vai trò client.

## 2. Auto-registration trong Spring Cloud hoạt động như thế nào?

Spring Cloud Commons định nghĩa các abstraction chung như `ServiceRegistry`, `Registration` và `AutoServiceRegistration`. Discovery provider như Eureka hoặc Consul cung cấp implementation phù hợp với registry của nó.

Ở mức khái niệm, quy trình tự đăng ký có các bước:

1. Ứng dụng khởi tạo ApplicationContext.
2. Discovery provider tạo thông tin registration cho instance hiện tại, chẳng hạn service ID, host, port và metadata.
3. Cơ chế auto-registration của provider thực hiện đăng ký theo lifecycle của ứng dụng.
4. Registry lưu instance để các client khác có thể discovery.
5. Khi ứng dụng dừng, provider có thể deregister instance hoặc cập nhật trạng thái theo lifecycle được tích hợp.

~~~mermaid
flowchart TB
    A["Ứng dụng Spring Boot khởi động"]
    A --> B["Discovery provider được cấu hình"]
    B --> C{"Auto-registration được bật?"}
    C -->|Có| D["Tạo Registration cho instance"]
    D --> E["ServiceRegistry.register()"]
    E --> F["Instance xuất hiện trong registry"]
    C -->|Không| G["Bỏ qua bước tự đăng ký"]
    G --> H["Ứng dụng vẫn có thể dùng DiscoveryClient"]
    F --> I["Ứng dụng hoạt động"]
    H --> I
    I --> J["Shutdown"]
    J --> K["Provider xử lý lifecycle/deregister nếu có registration"]
~~~

Sơ đồ mô tả luồng chung. Chi tiết tạo registration, health check, heartbeat, deregistration và trạng thái phụ thuộc discovery provider cùng phiên bản đang dùng.

### 2.1. ServiceRegistry không đồng nghĩa AutoServiceRegistration

`ServiceRegistry` là abstraction cho thao tác với registry, thường gồm đăng ký, hủy đăng ký và đọc/cập nhật trạng thái registration. `AutoServiceRegistration` là cơ chế tích hợp để provider tự thực hiện registration theo lifecycle ứng dụng.

Tách hai khái niệm này giúp hiểu đúng tác động của cờ tắt:

- Tắt auto-registration ngăn luồng tự đăng ký của Spring Cloud.
- Bean hoặc API `ServiceRegistry` có thể vẫn tồn tại.
- Code chủ động gọi registration API vẫn có thể đăng ký instance nếu provider cho phép.
- DiscoveryClient có thể vẫn hoạt động để đọc instance của dịch vụ khác.

Không xem thuộc tính tắt auto-registration như một cơ chế phân quyền hoặc bảo vệ registry. Nếu ứng dụng không được phép đăng ký trong mọi trường hợp, cần kiểm soát quyền ở registry và không cung cấp đường code registration thủ công ngoài chủ đích.

## 3. Cách 1: tắt bằng thuộc tính cấu hình

Cách phổ biến nhất là khai báo thuộc tính chung của Spring Cloud Commons trong `application.yml`:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Thuộc tính đầy đủ:

~~~text
spring.cloud.service-registry.auto-registration.enabled
~~~

Khi giá trị là `false`, Spring Cloud không thực hiện luồng tự đăng ký được điều khiển bởi auto-registration configuration. Ứng dụng vẫn có thể khởi tạo discovery client và truy vấn registry nếu provider được cấu hình cho discovery.

### 3.1. Cấu hình theo profile

Có thể tắt registration ở local và test nhưng giữ hành vi production theo yêu cầu:

`application.yml`:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true
~~~

`application-test.yml`:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Khi profile `test`, thuộc tính profile-specific có thể ghi đè giá trị chung theo quy tắc cấu hình Spring Boot. Hãy kiểm tra profile active và giá trị hiệu lực trong Environment để tránh test vô tình đăng ký instance vào registry dùng chung.

Một ứng dụng batch hoặc worker có thể đặt thuộc tính false trong profile triển khai riêng nếu nó không cần công bố endpoint cho client khác.

### 3.2. Cấu hình bằng biến môi trường hoặc JVM argument

Thuộc tính có thể được truyền từ môi trường triển khai:

~~~bash
SPRING_CLOUD_SERVICE_REGISTRY_AUTO_REGISTRATION_ENABLED=false
~~~

Hoặc qua JVM system property:

~~~bash
-Dspring.cloud.service-registry.auto-registration.enabled=false
~~~

Cách này hữu ích khi cùng một artifact được triển khai ở nhiều môi trường nhưng chính sách registration khác nhau. Không nên khai báo các giá trị mâu thuẫn trong YAML, biến môi trường và JVM argument mà không xác định nguồn có ưu tiên cao hơn.

### 3.3. Vì sao thuộc tính là lựa chọn tốt cho triển khai?

Thuộc tính phù hợp khi muốn điều khiển registration theo môi trường mà không phải thay đổi mã nguồn:

- Có thể đặt trong Config Data hoặc nguồn cấu hình được quản lý.
- Có thể override bằng profile, environment variable hoặc JVM argument.
- Dễ kiểm tra trong cấu hình triển khai.
- Không buộc ứng dụng phải thêm annotation chỉ để điều chỉnh một cờ vận hành.

Đối với policy áp dụng cho toàn bộ deployment, cấu hình ngoài thường dễ quản lý hơn. Cần bảo đảm giá trị được cung cấp trước khi auto-configuration tạo cơ chế registration; không giả định thay đổi thuộc tính trong file sau khi ứng dụng chạy sẽ tự động bật/tắt lifecycle registration.

## 4. Cách 2: tắt bằng annotation

Nếu muốn thể hiện chính sách ngay trong cấu hình ứng dụng, có thể dùng thuộc tính `autoRegister` của `@EnableDiscoveryClient`:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient(autoRegister = false)
public class ReportWorkerApplication {
}
~~~

`autoRegister = false` chỉ định ứng dụng không tự đăng ký instance thông qua cơ chế auto-registration được kích hoạt bởi annotation này.

Cách này hữu ích khi quyết định là một phần cố định của cấu trúc ứng dụng, ví dụ một worker luôn là client-only và không bao giờ được quảng bá như một service endpoint.

### 4.1. Annotation có cần thiết để bật discovery không?

Trong nhiều cấu hình Spring Cloud hiện đại, discovery client được auto-configure khi dependency provider phù hợp có mặt; ứng dụng không nhất thiết phải thêm `@EnableDiscoveryClient` chỉ để bật discovery.

Tuy nhiên, annotation vẫn có thuộc tính `autoRegister` để thể hiện lựa chọn registration trong những cấu hình hỗ trợ nó. Nếu dự án đã dùng annotation, có thể đặt `autoRegister = false`. Nếu chỉ cần điều khiển theo môi trường, thuộc tính cấu hình chung thường rõ ràng hơn.

Không thêm annotation vào mọi ứng dụng theo thói quen mà không kiểm tra cách auto-configuration của release train đang dùng.

### 4.2. Không nhầm annotation này với tắt discovery

Ví dụ `@EnableDiscoveryClient(autoRegister = false)` vẫn thể hiện ý định sử dụng discovery client nhưng không tự đăng ký ứng dụng. Nó khác với việc tắt discovery client hoặc loại bỏ dependency provider.

Nếu ứng dụng cần tra cứu `catalog-service`, hãy kiểm tra `DiscoveryClient` vẫn được tạo và có thể lấy danh sách instance sau khi tắt auto-registration.

## 5. Chọn giữa thuộc tính và annotation

Hai cách biểu đạt cùng mục tiêu nhưng phù hợp với các tình huống quản lý khác nhau.

| Tiêu chí | Thuộc tính `enabled: false` | Annotation `autoRegister = false` |
| --- | --- | --- |
| Phạm vi điều khiển | Cấu hình ứng dụng/deployment | Cấu hình Java có annotation |
| Thay đổi theo profile | Thuận tiện | Cần thay đổi cấu hình mã hoặc cấu trúc import |
| Thay đổi theo môi trường | Có thể dùng env/JVM/config server | Không thuận tiện nếu policy thay đổi theo môi trường |
| Thể hiện ý định trong source | Thấp hơn | Rõ tại class cấu hình |
| Phù hợp với | Chính sách vận hành theo môi trường | Ứng dụng luôn không tự đăng ký |
| Cần kiểm tra phiên bản | Có | Có, đặc biệt khi dùng annotation |

Có thể dùng thuộc tính chung như lựa chọn mặc định cho deployment. Dùng annotation khi muốn chính sách gắn với loại ứng dụng và ổn định giữa các môi trường.

Nếu dùng cả hai, hãy giữ giá trị nhất quán và xác minh hành vi bằng integration test. Tránh đặt thuộc tính bật registration trong khi annotation lại yêu cầu không auto-register, vì kết quả có thể phụ thuộc phiên bản và cách auto-configuration được import.

## 6. Tắt auto-registration không tắt việc tra cứu registry

Đây là điểm cần kiểm tra kỹ nhất sau khi thay đổi.

Một ứng dụng client-only có thể vẫn cần:

- `DiscoveryClient.getInstances(serviceId)` để tìm instance.
- `DiscoveryClient.getServices()` để xem service ID được biết.
- Spring Cloud LoadBalancer để chọn instance.
- HTTP client có `@LoadBalanced` để gọi bằng service ID.

Ví dụ, một worker tra cứu catalog:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogLookup {

    private final DiscoveryClient discoveryClient;

    public CatalogLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
~~~

Khi auto-registration bị tắt, code tra cứu trên vẫn có thể hoạt động nếu discovery provider và registry connection được cấu hình đúng. Không cần đăng ký chính `report-worker` thì worker mới có thể truy vấn `catalog-service`.

### 6.1. Không dùng nhầm thuộc tính tắt discovery

Một số thuộc tính khác có thể ảnh hưởng discovery client hoặc provider. Ví dụ, tắt discovery hoàn toàn có thể khiến ứng dụng không còn tra cứu được registry; đó là mục tiêu khác với việc chỉ không công bố instance của chính nó.

Với Eureka, thuộc tính riêng `eureka.client.register-with-eureka=false` điều khiển việc Eureka client đăng ký chính nó. Nếu vẫn cần lấy danh sách registry, cần xem xét riêng `eureka.client.fetch-registry` và các thiết lập liên quan. Đây là cấu hình provider-specific, không thay thế hoàn toàn thuộc tính chung của Spring Cloud Commons cho mọi registry.

Không sao chép thuộc tính của Eureka sang Consul hoặc provider khác. Mỗi implementation có namespace và semantics riêng.

## 7. Registration thủ công vẫn là một đường riêng

Tắt auto-registration không phải lệnh “cấm đăng ký” ở cấp bảo mật. Ứng dụng có thể vẫn truy cập bean `ServiceRegistry` và chủ động gọi thao tác register nếu code được viết như vậy.

Một số trường hợp cần registration thủ công:

- Một ứng dụng quản lý nhiều logical instance.
- Chỉ đăng ký sau khi hoàn tất bước khởi tạo đặc biệt.
- Chỉ đăng ký một endpoint phụ khi một feature được bật.
- Tự điều khiển thời điểm deregister trong quy trình bảo trì.

Khi tự quản lý registration, ứng dụng phải chịu trách nhiệm cho toàn bộ lifecycle: tạo dữ liệu registration đúng, xử lý lỗi, tránh đăng ký trùng, deregister khi dừng và cập nhật trạng thái khi cần.

Không dùng registration thủ công chỉ để né thuộc tính auto-registration. Nếu mục tiêu là ứng dụng không xuất hiện trong registry, hãy kiểm tra cả code nội bộ, listener và integration khác có thể thực hiện đăng ký.

## 8. Điều gì xảy ra với instance đã đăng ký trước đó?

Thuộc tính `spring.cloud.service-registry.auto-registration.enabled=false` chủ yếu điều khiển hành vi auto-registration trong quá trình khởi tạo cấu hình ứng dụng. Không nên xem việc thay đổi giá trị thành false khi JVM đang chạy là lệnh deregister instance đã được đăng ký trước đó.

Nếu instance đã tồn tại trong registry, cần xác định cách gỡ bỏ:

- Dùng lifecycle/deregister API được provider hỗ trợ.
- Dùng thao tác quản trị của registry.
- Dừng instance theo quy trình graceful shutdown để provider xử lý deregistration nếu integration hỗ trợ.
- Kiểm tra lease/TTL/heartbeat để biết khi nào registry tự loại instance mất kết nối.

Không giả định mọi provider đều deregister ngay lập tức hoặc có cùng semantics khi ứng dụng dừng. Một số registry dùng lease/TTL, một số có trạng thái health, và thời gian instance biến mất khỏi kết quả discovery có thể phụ thuộc cấu hình.

### 8.1. Khi chuyển một service thành client-only

Nếu một ứng dụng trước đây đã tự đăng ký nhưng nay không cần được tìm thấy:

1. Xác định instance hiện có trong registry.
2. Chọn cách deregister hoặc chờ lifecycle/lease của provider theo chính sách.
3. Tắt auto-registration cho lần khởi động tiếp theo.
4. Kiểm tra không còn code hoặc listener đăng ký thủ công.
5. Xác nhận discovery client vẫn hoạt động nếu ứng dụng còn gọi service khác.
6. Kiểm tra client khác không còn phụ thuộc vào endpoint của ứng dụng này.

Chỉ tắt cờ và để một registration cũ tồn tại có thể khiến client khác tiếp tục gửi traffic tới endpoint không còn phục vụ.

## 9. Tác động tới startup, shutdown và health

Không tự đăng ký giúp tránh công bố một instance không cần thiết, nhưng không thay thế các bước vận hành khác.

### 9.1. Startup

Khi auto-registration được bật, provider thường đăng ký instance theo lifecycle tích hợp. Khi tắt, bước đó được bỏ qua. Các bước khởi tạo ứng dụng khác như tạo bean, mở HTTP server hoặc kết nối registry để discovery vẫn có thể diễn ra.

Nếu ứng dụng mở HTTP server nhưng không đăng ký, endpoint vẫn có thể truy cập qua địa chỉ trực tiếp hoặc load balancer bên ngoài. Tắt registration chỉ ảnh hưởng registry được tích hợp, không tự tắt network listener.

### 9.2. Shutdown

Nếu không có registration do auto-registration tạo ra, provider không có instance tương ứng để deregister theo luồng đó. Nhưng các bean khác vẫn cần được dừng và tài nguyên phải được đóng đúng vòng đời.

Nếu ứng dụng còn đăng ký thủ công, shutdown cần deregister registration đó. Không dựa vào auto-registration lifecycle để dọn một registration do code riêng tạo ra nếu code không nối vào cùng lifecycle.

### 9.3. Health và readiness

Tắt auto-registration không đồng nghĩa tắt health endpoint hoặc readiness state. Health indicator của registry, nếu có, vẫn có thể kiểm tra khả năng kết nối tới registry hoặc các dependency. Readiness của ứng dụng vẫn cần phản ánh khả năng nhận công việc theo yêu cầu triển khai.

Một worker không đăng ký service vẫn có thể cần health/readiness probe của Kubernetes. Đây là cơ chế quản lý workload, độc lập với service registry của Spring Cloud.

## 10. Kiểm thử việc tắt auto-registration

Kiểm thử tốt cần xác nhận hai điều cùng lúc:

1. Ứng dụng không gửi lệnh đăng ký instance khi khởi động.
2. Discovery client vẫn tra cứu được service khác nếu đó là yêu cầu của ứng dụng.

### 10.1. Kiểm thử cấu hình

Với integration test, truyền thuộc tính tắt trong test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.cloud.service-registry.auto-registration.enabled=false"
})
class AutoRegistrationPropertyTest {

    @Autowired
    Environment environment;

    @Test
    void autoRegistrationIsDisabled() {
        assertThat(environment.getProperty(
                "spring.cloud.service-registry.auto-registration.enabled",
                Boolean.class,
                true)).isFalse();
    }
}
~~~

Đây chỉ xác nhận cấu hình được nạp. Nó chưa chứng minh provider không gửi request registration; cần kiểm thử hành vi tích hợp.

### 10.2. Kiểm thử hành vi với registry giả

Có thể dùng mock server hoặc fake provider để ghi nhận request. Khi context khởi động:

- Xác nhận không có request register từ instance của ứng dụng.
- Xác nhận không có request heartbeat/renew lease cho registration do ứng dụng này tạo.
- Nếu discovery vẫn cần thiết, gọi API lấy instance và xác nhận request fetch/query vẫn được gửi.
- Đóng context và kiểm tra không có deregister cho một registration không được tạo.

Cách quan sát request cụ thể phụ thuộc protocol của Eureka, Consul hoặc registry đang dùng. Không nên kiểm tra một endpoint HTTP cố định khi test dùng provider khác.

### 10.3. Ma trận kiểm thử

| Auto-registration | Discovery query | Kết quả mong đợi |
| --- | --- | --- |
| Bật | Bật | Instance ứng dụng được đăng ký; có thể tra cứu service khác |
| Tắt | Bật | Không tự đăng ký instance; vẫn tra cứu service khác |
| Bật | Tắt hoặc không cấu hình | Registration phụ thuộc provider; không nên suy ra query hoạt động |
| Tắt | Tắt | Không tự đăng ký và không sử dụng discovery query |
| Tắt | Bật, có manual register | Luồng tự động bị tắt nhưng code thủ công vẫn có thể đăng ký |

Ma trận giúp phát hiện nhầm lẫn giữa hai chiều registration và discovery, cũng như giữa auto-registration và manual registration.

## 11. Lỗi thường gặp và cách tránh

1. **Tắt auto-registration rồi nghĩ discovery cũng bị tắt:** kiểm tra riêng bean DiscoveryClient và khả năng query registry.
2. **Dùng thuộc tính provider-specific cho mọi registry:** thuộc tính chung và thuộc tính riêng có phạm vi khác nhau.
3. **Cho rằng cờ false tự deregister instance cũ:** kiểm tra registry và thực hiện deregister theo lifecycle/provider.
4. **Đặt annotation nhưng vẫn có code register thủ công:** tìm các đường registration khác trong ứng dụng.
5. **Dùng annotation khi policy cần thay đổi theo profile:** cân nhắc thuộc tính cấu hình để quản lý theo môi trường.
6. **Cấu hình mâu thuẫn giữa annotation và property:** giữ một chính sách nhất quán và kiểm tra hành vi của release train.
7. **Không kiểm tra auto-configuration:** xác nhận provider và bean auto-registration thực sự được tạo hoặc bị loại bỏ như dự kiến.
8. **Cho rằng HTTP server tự tắt khi không đăng ký:** listener vẫn có thể chạy và truy cập trực tiếp.
9. **Quên readiness của worker:** workload vẫn cần health/readiness probe dù không xuất hiện trong registry.
10. **Chỉ kiểm tra Environment property:** bổ sung test quan sát request register/query ở phía provider.

## 12. Quy trình lựa chọn và triển khai

Khi muốn tắt tự đăng ký trong ứng dụng Spring Cloud:

1. Xác định ứng dụng có cần được các service khác tìm thấy hay chỉ cần gọi dịch vụ khác.
2. Kiểm tra discovery provider và cơ chế auto-registration đang hoạt động.
3. Chọn thuộc tính `spring.cloud.service-registry.auto-registration.enabled=false` nếu policy phụ thuộc môi trường.
4. Chọn `@EnableDiscoveryClient(autoRegister = false)` nếu policy là quyết định cố định của ứng dụng và phiên bản hỗ trợ.
5. Tránh cấu hình annotation và property theo hai hướng mâu thuẫn.
6. Kiểm tra provider-specific setting nếu ứng dụng dùng Eureka, Consul hoặc registry khác.
7. Tìm các thao tác registration thủ công và listener có thể đăng ký instance.
8. Nếu instance đã đăng ký, thực hiện deregistration hoặc xử lý lease theo provider.
9. Kiểm thử không có request register nhưng discovery query vẫn hoạt động nếu cần.
10. Xác minh health, readiness, HTTP listener và shutdown vẫn phù hợp với vai trò của ứng dụng.

**Điểm ghi nhớ:** Thuộc tính `spring.cloud.service-registry.auto-registration.enabled=false` và annotation `@EnableDiscoveryClient(autoRegister = false)` điều khiển luồng tự đăng ký instance của ứng dụng. Chúng không mặc nhiên tắt DiscoveryClient, LoadBalancer hoặc mọi thao tác registration thủ công. Hãy xác định riêng nhu cầu công bố instance, tra cứu service và quản lý vòng đời registration để cấu hình ServiceRegistry an toàn trong **SPRING_CLOUD_CORE**.
