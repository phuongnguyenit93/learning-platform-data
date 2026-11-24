# Xung đột nhiều DiscoveryClient hoặc không tương thích phiên bản

Một ứng dụng Spring Cloud có thể đưa nhiều thư viện discovery vào classpath, ví dụ Eureka, Consul, ZooKeeper và Kubernetes. Khi nhiều starter cùng được kích hoạt, ứng dụng có thể tạo nhiều bean `DiscoveryClient`, nhiều cơ chế đăng ký service hoặc nhiều nguồn instance cho cùng một service ID. Nếu cấu hình không chủ ý, consumer có thể tra cứu nhầm registry, provider đăng ký trùng hoặc health state giữa các registry không nhất quán.

Một nhóm lỗi khác xuất hiện khi phiên bản Spring Boot, Spring Cloud release train và các starter không tương thích. Ứng dụng có thể không khởi động vì dependency thiếu, lỗi tạo bean, `NoSuchMethodError` hoặc hành vi discovery bất thường sau khi nâng cấp.

Bài này giúp phân biệt xung đột do nhiều provider với lỗi tương thích dependency, xác định bean và auto-configuration thực sự được kích hoạt, chọn một provider rõ ràng hoặc cấu hình nhiều provider có chủ đích, rồi xử lý lỗi phiên bản theo thứ tự có thể kiểm chứng.

## 1. Phân biệt DiscoveryClient, ServiceRegistry và auto-registration

Ba khái niệm thường bị gộp làm một:

- **`DiscoveryClient`**: abstraction để consumer truy vấn service instance theo service ID qua `getInstances(serviceId)` và liệt kê service qua `getServices()`.
- **`ServiceRegistry`**: abstraction để đăng ký, hủy đăng ký hoặc cập nhật trạng thái instance ở registry.
- **Auto-registration**: lifecycle integration của provider tự đăng ký instance khi ứng dụng khởi động và deregister khi shutdown.

Một provider thường cung cấp cả DiscoveryClient lẫn ServiceRegistry, nhưng chúng là hai vai trò khác nhau. Consumer chỉ cần tra cứu có thể tắt registration của chính nó. Provider cần được service khác tìm thấy thì cần registration và health/lease phù hợp.

Spring Cloud Commons cung cấp abstraction chung; Eureka, Consul, ZooKeeper và Kubernetes cung cấp implementation riêng. Thêm một starter vào classpath có thể kích hoạt auto-configuration của provider đó nếu các điều kiện cấu hình thỏa mãn.

## 2. Nhiều DiscoveryClient không đồng nghĩa với một registry dự phòng

Khi nhiều discovery provider cùng được kích hoạt, ứng dụng có thể có nhiều bean implementation. Spring Cloud Commons có thể tạo `CompositeDiscoveryClient` để điều phối các delegate. Cách composite chọn delegate, thứ tự gọi và xử lý kết quả phụ thuộc implementation/version; không nên mặc định rằng nó luôn hợp nhất tất cả instance từ mọi registry thành một danh sách duy nhất.

Ví dụ classpath có cả Eureka và Consul:

```text
ApplicationContext
  EurekaDiscoveryClient
  ConsulDiscoveryClient
  CompositeDiscoveryClient (nếu auto-configuration tạo)
```

Composite discovery giải quyết việc truy vấn qua nhiều delegate theo cơ chế của nó. Nó không tự động:

- Đồng bộ service registration giữa Eureka và Consul.
- Chọn registry chính/phụ theo health hoặc ưu tiên nghiệp vụ.
- Bảo đảm hai registry có cùng service ID, metadata và health status.
- Hủy đăng ký instance khỏi tất cả registry khi ứng dụng shutdown.
- Cung cấp failover nhất quán cho mọi `ServiceRegistry`.

Đặc biệt, không nhầm `CompositeDiscoveryClient` với một bộ điều phối registration đa registry. Auto-registration của từng provider có lifecycle riêng; hãy kiểm tra các bean `AutoServiceRegistration`, `ServiceRegistry` và log đăng ký thực tế.

## 3. Những dạng xung đột thường gặp

| Dạng xung đột | Triệu chứng | Nguyên nhân thường gặp |
| --- | --- | --- |
| Nhiều discovery starter ngoài ý muốn | Consumer tìm thấy service từ registry không mong đợi | Dependency transitively kéo thêm provider starter |
| Nhiều `DiscoveryClient` bean | Composite được tạo hoặc injection không rõ delegate | Nhiều provider auto-configuration cùng thỏa điều kiện |
| Nhiều registrar | Instance xuất hiện ở nhiều registry | Auto-registration của nhiều provider cùng bật |
| Nhiều `ServiceRegistry` bean | Injection mơ hồ hoặc registrar chọn sai bean | Code tự tạo bean hoặc nhiều provider cùng được bật |
| Service ID không thống nhất | Registry có instance nhưng consumer nhận danh sách rỗng | Khác chữ hoa/thường, prefix, namespace hoặc application name |
| Discovery và registration dùng provider khác nhau | Provider đăng ký ở registry A nhưng consumer tra cứu registry B | Cấu hình provider không nhất quán giữa service |
| Starter không tương thích | Lỗi tạo bean, `NoSuchMethodError`, `ClassNotFoundException` | Spring Boot/Cloud/library version lệch nhau |
| Dependency bị kéo hai phiên bản | Hành vi thay đổi theo classpath hoặc môi trường chạy | Không dùng BOM thống nhất hoặc override version thủ công |

## 4. Chọn kiến trúc discovery trước khi chỉnh dependency

Trước khi loại bỏ hoặc thêm starter, xác định ứng dụng thuộc trường hợp nào:

| Nhu cầu | Thiết kế phù hợp |
| --- | --- |
| Chỉ dùng một registry | Chỉ thêm starter của provider đó và tắt các provider khác |
| Consumer chỉ tra cứu, không cần được đăng ký | Bật DiscoveryClient, tắt auto-registration của ứng dụng |
| Ứng dụng vừa cung cấp service vừa gọi service khác | Bật discovery và registration của cùng provider |
| Di chuyển từ registry cũ sang registry mới | Chọn một giai đoạn migration rõ ràng, kiểm tra dữ liệu và traffic trước khi loại registry cũ |
| Cần tra cứu nhiều registry có chủ đích | Thiết kế thứ tự/fallback/merge rõ ràng, kiểm thử composite và registration riêng |
| Cần active-active nhiều registry | Xác định cách đồng bộ registration, health, deregistration và xử lý split-brain; không dựa riêng vào CompositeDiscoveryClient |

Trong phần lớn ứng dụng, một provider chính giúp cấu hình, health check, quyền truy cập và vận hành dễ dự đoán hơn. Chỉ giữ nhiều provider khi có yêu cầu kiến trúc rõ ràng và có test cho từng luồng.

## 5. Kiểm tra dependency nào đã đưa provider vào ứng dụng

Không chỉ nhìn `pom.xml` hoặc `build.gradle` trực tiếp. Starter có thể được kéo vào transitively bởi một thư viện khác.

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud
```

Để kiểm tra cụ thể nhóm Spring Framework/Spring Boot:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-context,org.springframework.boot
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xem vì sao một dependency xuất hiện:

```bash
./gradlew dependencyInsight \
  --dependency spring-cloud-starter-consul-discovery \
  --configuration runtimeClasspath
```

Hãy tìm các starter như:

- `spring-cloud-starter-netflix-eureka-client`
- `spring-cloud-starter-consul-discovery`
- `spring-cloud-starter-zookeeper-discovery`
- `spring-cloud-starter-kubernetes-client` hoặc starter Kubernetes discovery tương ứng phiên bản
- `spring-cloud-starter-loadbalancer`

Tên artifact Kubernetes và cách chia starter có thể thay đổi theo release. Kiểm tra dependency tree thay vì suy luận chỉ từ tên module.

Nếu ứng dụng chỉ cần Consul nhưng Eureka starter được kéo vào từ một module nội bộ, hãy xác định dependency nào đưa nó vào rồi loại bỏ ở đúng nơi. Không thêm exclusion hàng loạt trước khi hiểu dependency path vì có thể loại nhầm thư viện mà provider đang cần.

## 6. Kiểm tra bean DiscoveryClient thực tế

Khi ứng dụng khởi động được, hãy xem ApplicationContext đang có những bean nào. Có thể dùng một `ApplicationRunner` tạm thời trong profile debug:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@Configuration
class DiscoveryClientDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryClientDiagnostics.class);

    @Bean
    ApplicationRunner logDiscoveryClients(ApplicationContext context) {
        return args -> context.getBeansOfType(DiscoveryClient.class)
                .forEach((beanName, client) -> log.info(
                        "Discovery client bean: name={}, type={}, description={}",
                        beanName,
                        client.getClass().getName(),
                        client.description()));
    }
}
```

Đoạn code chỉ log tên bean, class và description; không dump toàn bộ ApplicationContext hoặc cấu hình có thể chứa credential. Có thể kiểm tra thêm `ReactiveDiscoveryClient` nếu ứng dụng dùng reactive discovery.

Đừng vội thêm `@Primary` khi thấy nhiều bean. `@Primary` chỉ giúp Spring chọn bean khi injection theo type bị mơ hồ; nó không tắt auto-configuration provider khác, không ngăn registrar khác chạy và không bảo đảm composite lookup chỉ dùng provider được chọn.

Nếu cần inject một implementation cụ thể, dùng `@Qualifier` với bean name đã xác minh. Chỉ làm vậy khi code thực sự cần provider-specific API; code nghiệp vụ thông thường nên phụ thuộc abstraction chung.

## 7. Kiểm tra auto-configuration đã bật vì điều kiện nào

Chạy ứng dụng với debug condition report:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc truyền `--debug` khi khởi động artifact đã build. Spring Boot sẽ in condition evaluation report, cho biết auto-configuration nào match và điều kiện nào không match.

Nếu Actuator được bật, endpoint `/actuator/conditions` có thể hiển thị condition report. Chỉ expose endpoint này trong môi trường debug được bảo vệ; không công khai thông tin cấu hình nội bộ ra Internet.

Tìm các cấu hình liên quan đến:

- Eureka client auto-configuration.
- Consul discovery auto-configuration.
- ZooKeeper discovery auto-configuration.
- Kubernetes discovery auto-configuration.
- Composite DiscoveryClient.
- SimpleDiscoveryClient.
- ServiceRegistry và auto-registration.

Condition report hữu ích hơn việc đoán từ tên dependency vì một starter có thể có mặt nhưng bị tắt bởi property, thiếu class hoặc điều kiện môi trường.

## 8. Tắt provider không cần thiết

Nếu chỉ dùng một provider, hãy tắt provider khác bằng property được hỗ trợ trong phiên bản đang dùng và loại dependency không cần thiết nếu có thể.

Ví dụ cấu hình minh họa khi ứng dụng chỉ dùng Consul:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
    consul:
      discovery:
        enabled: true
    zookeeper:
      discovery:
        enabled: false
    kubernetes:
      discovery:
        enabled: false

eureka:
  client:
    enabled: false
```

Property chính xác phụ thuộc provider và release train. Ví dụ thường gặp gồm `spring.cloud.consul.discovery.enabled`, `eureka.client.enabled`, `spring.cloud.zookeeper.discovery.enabled`, `spring.cloud.kubernetes.discovery.enabled` và công tắc chung `spring.cloud.discovery.enabled`. Kiểm tra configuration metadata/reference của đúng starter đang dùng trước khi áp dụng.

Nếu muốn giữ DiscoveryClient nhưng không tự đăng ký ứng dụng:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

Property này tắt auto-registration chung khi provider tích hợp với cơ chế Spring Cloud Commons tương ứng; nó không có nghĩa mọi provider-specific registration path đều bị tắt trong mọi version. Hãy kiểm tra log và registry để xác nhận instance không còn được đăng ký.

Không dùng `spring.cloud.discovery.enabled=false` nếu ứng dụng vẫn cần discovery lookup. Đây là công tắc phạm vi rộng, có thể tắt cả client discovery mà consumer đang cần.

## 9. Phân biệt CompositeDiscoveryClient với lựa chọn provider tường minh

Nếu nhiều provider là chủ ý, hãy xác định composite có đúng semantics mong muốn không. Các câu hỏi cần trả lời:

- Khi service ID tồn tại ở cả hai registry, delegate nào được hỏi trước?
- Kết quả trả về là danh sách từ delegate đầu tiên có kết quả, hay hợp nhất nhiều danh sách?
- Nếu delegate đầu tiên lỗi, composite có tiếp tục thử delegate sau không?
- Nếu delegate đầu tiên trả danh sách rỗng, có thử delegate tiếp theo không?
- `getServices()` có thể liệt kê tên từ nhiều registry trong khi `getInstances()` lấy từ một registry khác không?
- LoadBalancer cache danh sách kết quả trong bao lâu?
- Metadata/health có cùng semantics giữa hai provider không?

Không trả lời các câu hỏi này bằng giả định. Hãy đọc API/version đang dùng, xem bean thực tế và viết integration test với hai registry có dữ liệu khác nhau để quan sát hành vi.

Nếu nghiệp vụ yêu cầu ưu tiên registry A rồi fallback B, có thể tạo một adapter/strategy tường minh thay vì dựa vào thứ tự bean ngầm định. Adapter phải định nghĩa rõ lỗi nào được fallback, xử lý empty result ra sao và cách tránh trả instance trùng.

## 10. Tắt registration nhưng vẫn tra cứu service

Một consumer chỉ gọi downstream có thể không cần đăng ký chính nó vào registry. Ví dụ:

```yaml
spring:
  application:
    name: report-worker
  cloud:
    consul:
      discovery:
        enabled: true
        register: false
```

Với Eureka, cấu hình thường là:

```yaml
eureka:
  client:
    enabled: true
    register-with-eureka: false
    fetch-registry: true
```

`register-with-eureka=false` tắt đăng ký client lên Eureka nhưng vẫn fetch registry. Đây là khác biệt quan trọng với `fetch-registry=false`, vốn có thể làm consumer không lấy được danh sách service.

Tên property và default có thể thay đổi theo provider/version. Sau khi cấu hình, xác minh cả hai mặt: ứng dụng vẫn tra cứu được service cần gọi và không tạo registration ngoài ý muốn.

## 11. Quản lý nhiều ServiceRegistry khi thực sự cần đăng ký đa nơi

Một số kiến trúc migration hoặc hybrid có nhu cầu đăng ký cùng instance vào hai registry. Khi đó, không được coi việc có hai `DiscoveryClient` là đủ.

Cần định nghĩa một registration coordinator có trách nhiệm:

1. Tạo một service identity nhất quán hoặc mapping ID rõ ràng cho từng registry.
2. Đăng ký vào registry A và B theo trình tự/parallel policy được xác định.
3. Ghi nhận kết quả từng registry độc lập.
4. Xử lý trường hợp A thành công nhưng B thất bại.
5. Retry phần chưa thành công mà không tạo registration trùng.
6. Deregister khỏi tất cả registry mà coordinator đã đăng ký.
7. Đồng bộ health/status và metadata theo semantics của từng provider.

Đây là bài toán distributed workflow: không có transaction ACID chung giữa hai registry. Có thể cần compensation nếu một bước thành công và bước khác thất bại. Log/metric cần tách kết quả theo provider để nhìn thấy trạng thái partial success.

Nếu không có nhu cầu migration hoặc hybrid rõ ràng, tránh đăng ký đa registry chỉ để “dự phòng”. Một registry chính cộng với backup/replication ở tầng hạ tầng thường đơn giản hơn nhiều so với đồng bộ hai registration plane từ mọi ứng dụng.

## 12. Spring Boot và Spring Cloud phải dùng phiên bản tương thích

Spring Boot và Spring Cloud được phát hành theo các dòng phiên bản có ma trận tương thích. Một release train Spring Cloud chỉ hỗ trợ một số dòng Spring Boot nhất định. Không nên chọn phiên bản mới nhất riêng lẻ cho từng starter.

Quy tắc quản lý dependency:

- Chọn phiên bản Spring Boot trước.
- Chọn Spring Cloud release train được công bố tương thích với dòng Boot đó.
- Import `spring-cloud-dependencies` BOM của release train.
- Không tự đặt version riêng cho từng Spring Cloud starter nếu BOM đã quản lý.
- Giữ các module Spring Cloud Commons, LoadBalancer và provider starter trong cùng release train.
- Chỉ override dependency version khi có lý do rõ ràng và đã kiểm tra compatibility.

### Maven: import Spring Cloud BOM

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-consul-discovery</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
```

`YOUR_COMPATIBLE_RELEASE_TRAIN` là placeholder; thay bằng release train đã được kiểm tra trong compatibility matrix chính thức. Spring Boot parent/BOM cũng phải được chọn đồng bộ. Không copy một version cụ thể từ dự án khác mà không xác nhận dòng Boot và Java đang dùng.

### Gradle: import BOM

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation "org.springframework.cloud:spring-cloud-starter-consul-discovery"
    implementation "org.springframework.cloud:spring-cloud-starter-loadbalancer"
}
```

Nếu dùng Kotlin DSL, cú pháp tương ứng là `implementation(platform("..."))`. Không khai báo version riêng cho từng starter khi BOM đã quản lý version đó.

## 13. Nhận diện lỗi binary incompatibility

Một số exception thường gợi ý lệch version:

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `NoSuchMethodError` | Code đã compile mong đợi method nhưng runtime load class version không có method đó | Dependency tree, classpath thực tế, BOM alignment |
| `AbstractMethodError` | Implementation không cung cấp method tương thích với interface/abstract class runtime | Spring Cloud module hoặc provider implementation lệch version |
| `NoClassDefFoundError` | Class cần thiết không có khi runtime hoặc khởi tạo class thất bại | Dependency bị thiếu/exclude hoặc lỗi static initialization trước đó |
| `ClassNotFoundException` | Classloader không tìm thấy class được yêu cầu | Artifact/version/classpath và optional dependency |
| `IncompatibleClassChangeError` | Kiểu class/interface hoặc binary signature không tương thích | Dependency trùng phiên bản hoặc API bị đổi |
| `BeanCreationException` | Bean lỗi khi khởi tạo; nguyên nhân gốc có thể nằm sâu trong cause chain | Đọc root cause, condition report và provider configuration |
| `NoSuchBeanDefinitionException` | Auto-configuration không tạo bean hoặc dependency chưa có | Starter, property enablement và condition report |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type mà injection không xác định được | Qualifier/Primary hoặc tắt provider dư sau khi xác minh |

Đừng sửa `NoSuchMethodError` bằng cách thêm `@Primary`; đó là lỗi binary dependency, không phải lỗi chọn bean. Tương tự, `NoUniqueBeanDefinitionException` không tự chứng minh các thư viện không tương thích; có thể chỉ là nhiều provider được bật đúng như classpath yêu cầu.

## 14. Khác biệt javax/jakarta và nền tảng Java

Khi nâng từ Spring Boot 2 lên Spring Boot 3, nhiều API chuyển từ namespace `javax.*` sang `jakarta.*`. Một thư viện discovery cũ biên dịch dựa trên `javax` có thể không tương thích với ứng dụng Spring Boot 3 sử dụng `jakarta`.

Khi gặp lỗi class hoặc method liên quan servlet, validation, annotation hoặc persistence:

- Kiểm tra provider starter có release hỗ trợ Spring Boot major đang dùng không.
- Kiểm tra Java runtime phù hợp với yêu cầu của Spring Boot.
- Không thêm đồng thời cả hai API `javax` và `jakarta` chỉ để làm compile pass nếu thư viện không hỗ trợ cả hai.
- Nâng cấp provider integration cùng release train, không chỉ nâng Spring Cloud Commons riêng lẻ.
- Kiểm tra thư viện nội bộ có kéo transitive dependency cũ vào không.

Không có một thay đổi version đơn lẻ bảo đảm giải quyết toàn bộ lỗi namespace; cần xác định class cụ thể trong stack trace và dependency sở hữu class đó.

## 15. Dùng compatibility verifier đúng cách

Spring Cloud có compatibility verifier để phát hiện một số tổ hợp Spring Boot/Spring Cloud không được hỗ trợ. Khi ứng dụng báo phiên bản không tương thích, hãy xem đây là tín hiệu cần xử lý.

Không nên tắt verifier chỉ để ứng dụng khởi động:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: false
```

Property này có thể bỏ qua bước kiểm tra sớm trong các phiên bản hỗ trợ, nhưng không sửa được API binary mismatch, lỗi auto-configuration hoặc hành vi không được kiểm thử. Chỉ tắt tạm thời khi đã có đánh giá kỹ thuật, biết chính xác tổ hợp dependency và có kiểm thử hồi quy; không dùng làm cấu hình mặc định.

## 16. Quy trình xử lý khi có nhiều DiscoveryClient

Thực hiện theo thứ tự sau:

1. Ghi lại provider mà kiến trúc yêu cầu cho môi trường hiện tại.
2. Xem dependency tree để tìm starter trực tiếp và transitive.
3. Bật condition report để biết auto-configuration nào match.
4. Liệt kê bean `DiscoveryClient`, `ReactiveDiscoveryClient`, `ServiceRegistry` và auto-registration thực tế.
5. Kiểm tra property enablement theo provider.
6. Tắt provider ngoài ý muốn và loại dependency không cần thiết.
7. Xác minh consumer vẫn lấy được instance từ registry mong muốn.
8. Xác minh provider chỉ đăng ký ở registry dự định.
9. Kiểm tra health, deregistration và shutdown lifecycle.
10. Chạy integration test với registry thật hoặc container để xác nhận không còn instance/lookup ngoài ý muốn.

Nếu nhiều provider là chủ ý, viết test xác nhận rõ thứ tự delegate, kết quả khi service ID tồn tại ở nhiều registry, behavior khi một registry lỗi và registration/deregistration partial failure.

## 17. Quy trình xử lý khi phiên bản không tương thích

1. Ghi lại phiên bản Java, Spring Boot, Spring Cloud release train và provider starter.
2. Lấy root cause đầy đủ, không chỉ dòng `BeanCreationException` ngoài cùng.
3. Chạy Maven/Gradle dependency tree cho `org.springframework.cloud`, `org.springframework.boot` và `org.springframework`.
4. Tìm dependency bị override, duplicate hoặc kéo transitive version khác.
5. Chọn đúng Spring Cloud BOM theo compatibility matrix của Spring Boot.
6. Xóa version override không cần thiết và để BOM quản lý các module cùng release train.
7. Kiểm tra artifact provider có hỗ trợ Boot major/Java/namespace hiện tại.
8. Clean build và chạy test context startup.
9. Chạy integration test registration, discovery lookup, health update và deregistration.
10. Chỉ sau khi xác minh mới cân nhắc exclusion hoặc override có phạm vi hẹp.

Không nâng đồng thời Boot, Cloud, provider, logging và HTTP client trong một bước nếu không cần. Chia thay đổi thành các nhóm có thể xác định nguyên nhân khi có regression.

## 18. Test xác nhận chỉ có provider mong muốn

Có thể viết test kiểm tra bean thực tế trong context:

```java
@SpringBootTest
class DiscoveryProviderConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void exposesExpectedDiscoveryClient() {
        Map<String, DiscoveryClient> clients =
                context.getBeansOfType(DiscoveryClient.class);

        assertThat(clients.values())
                .anyMatch(client -> client.description().contains("Consul"));

        assertThat(clients.values())
                .noneMatch(client -> client.description().contains("Eureka"));
    }
}
```

Đây là ví dụ minh họa; `description()` là chuỗi mô tả, có thể thay đổi giữa phiên bản. Trong test của dự án, nên kiểm tra bean type/qualifier hoặc hành vi thực tế thay vì phụ thuộc quá chặt vào nội dung chuỗi.

Kiểm tra bean chưa đủ. Integration test nên:

- Đăng ký một provider instance có service ID duy nhất.
- Xác nhận `DiscoveryClient` trả đúng instance.
- Xác nhận registry ngoài ý muốn không nhận registration.
- Tắt hoặc làm registry chính mất kết nối và quan sát hành vi theo policy.
- Đóng context và xác nhận deregistration.

## 19. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Service xuất hiện ở cả Eureka và Consul | Hai provider auto-registration cùng bật | Tắt registrar không dùng hoặc thiết kế coordinator đa registry rõ ràng |
| Consumer trả instance từ registry không mong muốn | Nhiều DiscoveryClient/composite đang hoạt động | Kiểm tra delegate/order, disable provider dư và test lookup |
| `NoUniqueBeanDefinitionException` cho `ServiceRegistry` | Nhiều implementation được đăng ký | Dùng qualifier nếu có chủ đích hoặc tắt provider không dùng |
| `NoSuchMethodError` trong Spring Cloud | Module Cloud lệch release train | Import BOM đồng bộ và bỏ version override |
| `NoClassDefFoundError` khi startup | Dependency thiếu/exclude hoặc namespace không tương thích | Dependency tree và kiểm tra provider support matrix |
| `BeanCreationException` ở provider config | Property sai, endpoint không hợp lệ hoặc auto-config mismatch | Đọc root cause và condition report |
| Eureka client không fetch registry | `fetch-registry=false` hoặc client bị disable | Kiểm tra `eureka.client.enabled` và `fetch-registry` |
| Consumer không đăng ký nhưng lookup vẫn hoạt động | Auto-registration đã tắt có chủ đích | Xác nhận đây là vai trò consumer-only |
| `@Primary` không ngăn service đăng ký ở registry khác | Registrar khác vẫn chạy | Tắt auto-registration/provider, không chỉ chọn bean injection |
| Chạy local được nhưng CI lỗi | Runtime classpath/profile khác hoặc env property khác | So sánh dependency tree, active profile và condition report |
| Compatibility verifier báo unsupported | Boot/Cloud release train không khớp | Chọn release train tương thích; không tắt verifier để che lỗi |

## 20. Checklist trước khi kết luận đã xử lý

- [ ] Đã phân biệt `DiscoveryClient`, `ServiceRegistry` và auto-registration.
- [ ] Đã xác định số lượng và class thực tế của discovery bean trong context.
- [ ] Đã kiểm tra `CompositeDiscoveryClient` semantics theo version đang dùng.
- [ ] Đã kiểm tra tất cả starter trực tiếp và transitive trong runtime classpath.
- [ ] Provider ngoài ý muốn đã được disable hoặc dependency đã được loại đúng chỗ.
- [ ] Consumer lookup và provider registration được kiểm tra riêng.
- [ ] `@Primary`/`@Qualifier` chỉ dùng để giải quyết injection, không thay thế provider configuration.
- [ ] Spring Boot và Spring Cloud release train tương thích theo compatibility matrix.
- [ ] Các Spring Cloud module được quản lý bằng một BOM thống nhất.
- [ ] Không còn version override gây lệch Commons/LoadBalancer/provider starter.
- [ ] Đã kiểm tra Java baseline và khác biệt `javax`/`jakarta` khi nâng major.
- [ ] Compatibility verifier không bị tắt chỉ để bỏ qua cảnh báo.
- [ ] Integration test xác nhận registration, lookup, health và deregistration đúng registry.
- [ ] Log và condition report không làm lộ token hoặc credential.

Khi nhiều DiscoveryClient cùng xuất hiện, cần xác định đó là cấu hình nhiều registry có chủ ý hay starter bị kéo vào ngoài ý muốn. `CompositeDiscoveryClient` chỉ giải quyết lookup theo semantics của implementation; nó không đồng bộ registration hoặc thay thế một chiến lược multi-registry. Khi lỗi xuất phát từ version, hãy căn chỉnh Spring Boot, Spring Cloud release train và provider starter bằng BOM tương thích, rồi xác minh lại bean, registration và lookup bằng integration test. Cách xử lý theo từng lớp giúp tránh dùng `@Primary`, exclusion hoặc tắt compatibility verifier để che một nguyên nhân thực sự chưa được giải quyết.
