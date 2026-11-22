# Kiến thức tiên quyết và trình tự học của module

Bài học thuộc chương **Tổng quan** của module **SPRING_CLOUD_CORE**. Mục tiêu của module là hiểu những nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán: **Spring Cloud Commons**, **Spring Cloud Context**, cấu hình bên ngoài, khả năng tương thích với **Spring Boot**, cơ chế refresh, discovery, service registry, giao tiếp giữa các dịch vụ, kiểm thử và vận hành các abstraction dùng chung.

Để học hiệu quả, cần phân biệt hai lớp: **Spring Boot** giúp xây dựng và chạy từng ứng dụng, còn **Spring Cloud** bổ sung các abstraction và khả năng tích hợp phục vụ môi trường có nhiều dịch vụ. Một số khả năng Spring Cloud chỉ xuất hiện khi thêm dependency và cấu hình tương ứng; không nên coi toàn bộ Spring Cloud là một thành phần đơn lẻ tự động bật mọi tính năng.

## 1. Sau bài này, người học cần đạt gì?

Sau khi học, bạn có thể:

1. Tự đánh giá mình đã đủ nền tảng Java, Spring Boot, HTTP và cấu hình ứng dụng để vào module hay chưa.
2. Chọn bộ **JDK – Spring Boot – Spring Cloud release train** tương thích, biết tìm nguyên nhân khi thư viện không khớp phiên bản.
3. Giải thích trách nhiệm của Spring Cloud Commons và Spring Cloud Context bằng ví dụ cụ thể.
4. Phác thảo cách một dịch vụ tìm dịch vụ khác, lựa chọn instance và thực hiện HTTP call.
5. Lập kế hoạch thực hành từ cấu hình cục bộ tới discovery, refresh, kiểm thử và quan sát khi chạy.
6. Xác định tiêu chí hoàn thành cho từng chặng học thay vì chỉ đọc xong lý thuyết.

## 2. Những kiến thức tiên quyết

| Nhóm kiến thức | Cần nắm trước khi vào module | Cách tự kiểm tra |
| --- | --- | --- |
| **Java và công cụ build** | Class, interface, dependency injection ở mức khái niệm; Maven hoặc Gradle; biến môi trường; JDK tương thích với phiên bản Spring Boot đã chọn. | Tạo và chạy ứng dụng Java; xem dependency tree; giải thích được vì sao một JAR được đưa vào classpath. |
| **Spring Framework** | `ApplicationContext`, bean, `@Configuration`, `@Bean`, `@Component`, `@Autowired` hoặc constructor injection; lifecycle và proxy ở mức cơ bản. | Giải thích được thời điểm bean được tạo và vì sao gọi qua proxy có thể khác gọi trực tiếp. |
| **Spring Boot** | Starter, auto-configuration, `application.yml`, profile, `@ConfigurationProperties`, Actuator và quy trình khởi động ứng dụng. | Chạy một API đơn giản với hai profile; thay đổi cấu hình qua biến môi trường. |
| **HTTP và mạng** | URL, hostname, port, DNS, HTTP method/status, timeout, connection error, JSON; nguyên lý client/server. | Dùng `curl` gọi endpoint, phân biệt lỗi 4xx, 5xx và lỗi kết nối. |
| **Hệ thống phân tán** | Một dịch vụ có nhiều instance; instance có thể lỗi hoặc thay địa chỉ; network call có độ trễ và có thể thất bại. | Giải thích vì sao `localhost` của mỗi container không đại diện cho cùng một máy. |
| **Kiểm thử và vận hành** | Unit/integration test, log, health check, biến cấu hình bí mật, nguyên tắc quyền truy cập tối thiểu. | Viết một test Spring Boot đơn giản và xem tình trạng ứng dụng bằng Actuator. |

**Không bắt buộc** phải biết trước Eureka, Consul, Kubernetes, Spring Cloud Config Server hoặc API Gateway. Đây là các sản phẩm, triển khai hoặc thành phần chuyên biệt có thể học sau khi đã hiểu abstraction chung. Docker hữu ích cho thực hành nhiều instance nhưng không phải điều kiện để bắt đầu.

### Bài kiểm tra đầu vào trong 15–30 phút

Tạo một ứng dụng Spring Boot có endpoint `GET /greeting`. Cấu hình thông điệp qua `application.yml` với giá trị mặc định, sau đó thay đổi bằng biến môi trường. Chạy ứng dụng trên hai port khác nhau, gọi cả hai bằng `curl` và quan sát kết quả.

Nếu chưa làm được, hãy ôn phần Spring Boot và cấu hình bên ngoài trước. Nếu làm được nhưng chưa giải thích được `ApplicationContext`, hãy ôn lại bean, scope và cách Spring quản lý đối tượng; kiến thức này đặc biệt cần thiết khi gặp `@RefreshScope`.

## 3. Bản đồ khái niệm trước khi học

Các mảnh ghép chính liên hệ với nhau như sau:

~~~mermaid
flowchart LR
    C["Cấu hình bên ngoài"] --> CTX["Spring ApplicationContext"]
    CTX --> A["order-service"]
    REG["Service registry hoặc cấu hình tĩnh"] --> DISC["DiscoveryClient"]
    DISC --> LB["LoadBalancer"]
    A --> LB
    LB --> B1["inventory-service: instance A"]
    LB --> B2["inventory-service: instance B"]
    OBS["Logs, health, metrics"] -.-> A
    OBS -.-> B1
    OBS -.-> B2
~~~

Sơ đồ là **mô hình khái niệm**, không khẳng định Spring Cloud mặc định khởi chạy tất cả các thành phần trên.

- **Spring Cloud Commons** cung cấp abstraction chung như `DiscoveryClient`, `ServiceInstance`, `ServiceRegistry` và cơ chế tích hợp load balancing. Nhà cung cấp thực tế có thể khác nhau.
- **Spring Cloud Context** cung cấp các khả năng liên quan tới ngữ cảnh ứng dụng và cấu hình, trong đó có refresh scope. Cơ chế nạp cấu hình lúc khởi động và cách làm mới cấu hình lúc chạy phải được xem là hai vấn đề khác nhau.
- **Discovery** trả lời câu hỏi “dịch vụ X hiện có những instance nào?”. **Service registry** là cơ chế quản lý thông tin đăng ký của các instance khi dùng một registry tương ứng. Không phải mọi `DiscoveryClient` đều có registry thật phía sau.
- **Load balancing** chọn một instance trong tập instance khả dụng; nó không tự bảo đảm timeout, retry, circuit breaker hay xử lý nghiệp vụ khi dịch vụ đích lỗi.
- **Giao tiếp dịch vụ** là lời gọi thực tế như HTTP qua `RestClient`, `WebClient` hoặc client tương ứng, thường sử dụng tên dịch vụ logic thay vì hard-code địa chỉ của một instance.

Hiểu rõ những ranh giới này sẽ giúp tránh nhầm lẫn giữa abstraction, implementation và hành vi khi chạy.

## 4. Trình tự học đề xuất

Hãy giữ nguyên thứ tự từ trên xuống vì mỗi chặng tạo điều kiện cho chặng kế tiếp.

| Chặng | Chủ đề | Câu hỏi phải trả lời được | Sản phẩm thực hành |
| --- | --- | --- | --- |
| **0** | Nền tảng Spring Boot và công cụ | Cấu hình đi vào ứng dụng như thế nào? Bean được tạo ra ở đâu? | Một REST API chạy được, đổi được port và thông điệp qua môi trường. |
| **1** | Tương thích phiên bản và quản lý dependency | Spring Boot và Spring Cloud release train được ghép cặp ra sao? | Một project build sạch, dependency tree không có phiên bản Cloud tự ghép tùy tiện. |
| **2** | Spring Cloud Commons | `DiscoveryClient`, `ServiceInstance`, `ServiceRegistry` đại diện cho điều gì? | Đọc được danh sách instance của một service ID từ nguồn discovery đơn giản. |
| **3** | Cấu hình bên ngoài và Spring Cloud Context | Giá trị cấu hình lấy từ đâu, lúc nào được đọc và lúc nào được cập nhật? | Đổi cấu hình theo profile/môi trường; giải thích được cách refresh hoạt động và giới hạn của nó. |
| **4** | Discovery và đăng ký dịch vụ | Tìm instance khác gì đăng ký instance? Điều gì xảy ra khi instance mất? | Hai dịch vụ; bên gọi tìm được instance qua tên logic. |
| **5** | Giao tiếp dịch vụ và load balancing | Một request đi từ service ID tới instance cụ thể bằng đường nào? | Gọi HTTP qua tên dịch vụ; quan sát timeout và instance không khả dụng. |
| **6** | Kiểm thử, quan sát, vận hành | Làm sao xác minh cấu hình, discovery và hành vi khi lỗi? | Test tự động, health endpoint, log đủ để truy vết request. |
| **7** | Bài thực hành tổng hợp | Ghép các abstraction mà không phụ thuộc cứng vào một registry cụ thể ra sao? | Một mini-system có hướng dẫn chạy và bảng kết quả thử nghiệm. |

Có thể học song song kiến thức HTTP, Spring Boot và kỹ năng kiểm thử, nhưng **không nên học refresh hoặc load balancing trước khi hiểu bean scope và discovery**.

## 5. Chặng 0–1: Chuẩn bị môi trường và khóa phiên bản

### 5.1. Thiết lập tối thiểu

Cần một JDK được hỗ trợ bởi phiên bản Spring Boot lựa chọn, IDE hoặc editor, Maven/Gradle, terminal và công cụ gọi HTTP. Kiểm tra:

~~~bash
java -version
./mvnw -version
./mvnw dependency:tree
~~~

Các lệnh `./mvnw` áp dụng cho dự án Maven có Maven Wrapper; trên Windows có thể dùng `mvnw.cmd`. Nếu dự án dùng Gradle, dùng `./gradlew dependencies` và các tác vụ tương đương. Kiểm tra build thành công bằng phiên bản JDK thực sự sử dụng trong môi trường CI, không chỉ trên máy cá nhân.

### 5.2. Vì sao phải kiểm tra tương thích?

Spring Cloud được phát hành theo **release train**, mỗi train quản lý một tập phiên bản các module Spring Cloud và chỉ tương thích với các dòng Spring Boot nhất định. Sự hiện diện của dependency trong Maven Central không chứng minh rằng việc ghép ngẫu nhiên một Spring Boot và một Spring Cloud sẽ chạy đúng.

Quy trình chọn phiên bản:

1. Chọn phiên bản Spring Boot được dự án chấp nhận, gồm cả yêu cầu Java và chính sách hỗ trợ.
2. Đối chiếu **bảng tương thích chính thức** của Spring Cloud để chọn release train phù hợp; đọc release notes khi nâng cấp.
3. Dùng cơ chế dependency management của Spring Boot và **Spring Cloud BOM**. Hạn chế đặt phiên bản riêng cho từng module Cloud trừ khi có lý do được kiểm chứng.
4. Kiểm tra dependency tree, chạy test khởi động và thử lại một luồng nghiệp vụ sau khi đổi phiên bản.
5. Khi gặp lỗi tương thích, giải quyết từ bộ phiên bản và dependency conflict trước khi thay đổi logic ứng dụng.

Ví dụ cấu hình **phần quản lý phiên bản Cloud** trong `pom.xml` của một dự án đã quản lý Spring Boot bằng parent/BOM tương ứng:

~~~xml
<properties>
    <!-- Thay bằng release train đúng theo compatibility matrix -->
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
~~~

Chuỗi `REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN` là **giá trị cần thay**, không phải phiên bản có thể build. Mỗi capability, chẳng hạn load balancing hoặc registry client, còn cần dependency thích hợp; BOM chỉ quản lý phiên bản và **không tự thêm thư viện vào ứng dụng**.

**Điểm hoàn thành:** bạn giải thích được cách lựa chọn cặp Boot/Cloud, biết phân biệt BOM với starter, và có một project build/test khởi động được với các phiên bản đã chọn.

## 6. Chặng 2: Nắm Spring Cloud Commons trước khi chọn công nghệ registry

Commons tạo hợp đồng chung để mã ứng dụng ít phụ thuộc hơn vào một nhà cung cấp service discovery cụ thể. Ba abstraction đầu tiên nên học:

| Abstraction | Trách nhiệm | Lưu ý |
| --- | --- | --- |
| `DiscoveryClient` | Truy vấn tên dịch vụ và danh sách `ServiceInstance` hiện biết. | Có thể lấy dữ liệu từ registry thật hoặc cấu hình tĩnh; không mặc định đảm bảo dữ liệu luôn mới. |
| `ServiceInstance` | Mô tả một instance: service ID, host, port, URI, metadata (tùy implementation). | Một service ID có thể tương ứng nhiều instance; metadata không tự bảo đảm instance đang healthy. |
| `ServiceRegistry` | Abstraction cho đăng ký/bỏ đăng ký hoặc quản lý trạng thái đăng ký với registry tương ứng. | Không phải mọi môi trường đều cần hoặc hỗ trợ cùng cách đăng ký. |

Trong thực hành đầu tiên, có thể dùng cấu hình tĩnh của **SimpleDiscoveryClient** để học lookup mà không phải cài đặt registry server:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Đây là cấu hình minh họa đặt trong ứng dụng **bên gọi**. Để chạy được, dự án phải có các dependency cung cấp Spring Cloud Commons/discovery tương thích; hai tiến trình đích cũng phải thực sự đang lắng nghe trên port đã khai báo.

Một đoạn mã dùng abstraction:

~~~java
@RestController
class DiscoveryLabController {
    private final DiscoveryClient discoveryClient;

    DiscoveryLabController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/lab/instances")
    List<String> inventoryInstances() {
        return discoveryClient.getInstances("inventory-service")
                .stream()
                .map(instance -> instance.getUri().toString())
                .toList();
    }
}
~~~

Ví dụ này phục vụ học tập; endpoint kiểm tra nội bộ cần hạn chế truy cập hoặc loại bỏ khi đưa vào production.

Khi đã hiểu, thay nguồn discovery tĩnh bằng một implementation phù hợp, chẳng hạn Eureka, Consul hoặc cơ chế tích hợp với môi trường triển khai. Khi đổi provider, hãy xem lại những khác biệt về đăng ký, cập nhật trạng thái, cache, metadata và thời gian phát hiện instance mất kết nối.

**Điểm hoàn thành:** bạn giải thích được vì sao “không tìm thấy instance” khác với “tìm được instance nhưng gọi HTTP thất bại”, và lấy được danh sách URI từ service ID.

## 7. Chặng 3: Cấu hình bên ngoài, Spring Cloud Context và refresh

### 7.1. Nền tảng cấu hình bên ngoài

Spring Boot có cơ chế externalized configuration: tệp cấu hình, profile, biến môi trường, tham số dòng lệnh và các property source khác có thể cung cấp giá trị cho cùng một khóa. **Thứ tự ưu tiên cụ thể** phụ thuộc loại nguồn cấu hình và cách khởi động; hãy kiểm chứng bằng tài liệu phiên bản đang dùng, tránh học thuộc một thứ tự tổng quát rồi áp dụng cho mọi trường hợp.

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

app:
  greeting: ${APP_GREETING:Chao ban}
~~~

Giá trị `APP_GREETING` được sử dụng khi có biến môi trường phù hợp; nếu không thì dùng `Chao ban`. Với nhiều thuộc tính liên quan, ưu tiên binding có kiểu rõ ràng bằng `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(String greeting) {}
~~~

Cần bật đăng ký lớp properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(AppProperties.class)`, tùy cấu trúc ứng dụng. Tách cấu hình khỏi code giúp cùng một bản build chạy trên nhiều môi trường, nhưng **secret** không nên đặt trực tiếp trong repository.

### 7.2. Điều gì xảy ra khi cấu hình thay đổi lúc chạy?

Hãy phân biệt:

- **Đọc cấu hình khi khởi động:** bean nhận giá trị trong quá trình tạo; sửa tệp trên đĩa không mặc nhiên khiến bean đang chạy đổi theo.
- **Cập nhật property source:** nguồn cấu hình có thể thay đổi, nhưng chưa chắc mọi bean đã đọc lại giá trị.
- **Refresh của Spring Cloud Context:** có cơ chế làm mới trạng thái cấu hình và các bean thuộc refresh scope khi được kích hoạt đúng cách.
- **`@RefreshScope`:** dùng proxy và cache để bean mục tiêu có thể được tạo lại sau khi scope được làm mới. Không có nghĩa mọi bean trong ứng dụng được tạo lại hoặc mọi giá trị đều thay đổi tức thì.

Ví dụ tối giản:

~~~java
@Component
@RefreshScope
class GreetingService {
    private final String greeting;

    GreetingService(@Value("${app.greeting:Chao ban}") String greeting) {
        this.greeting = greeting;
    }

    String greeting() {
        return greeting;
    }
}
~~~

Trình tự kiểm chứng: đọc giá trị ban đầu → cập nhật **nguồn cấu hình thực sự được ứng dụng sử dụng** → kích hoạt quy trình refresh được hỗ trợ và cấu hình trong phiên bản đang dùng → gọi lại bean qua proxy để xác minh giá trị. Nếu không có cơ chế cập nhật property source hoặc refresh, kết quả không đổi là điều có thể dự đoán.

Trong một số tổ hợp dependency có thể có endpoint Actuator dành cho refresh. Endpoint này **không nên coi là luôn tồn tại hoặc được expose mặc định**; nếu dùng, cần kiểm tra dependency, cấu hình expose, xác thực và quyền truy cập. Không công khai endpoint thay đổi cấu hình cho mọi người dùng.

**Điểm hoàn thành:** bạn mô tả được thời điểm giá trị cấu hình được đọc, khi nào cần khởi động lại, khi nào refresh có tác dụng, và nêu một trường hợp refresh không cập nhật bean như mong muốn.

## 8. Chặng 4–5: Discovery, load balancing và giao tiếp dịch vụ

Giả sử `order-service` cần lấy tồn kho từ `inventory-service`. Cách tiếp cận thủ công là gọi cố định `http://localhost:8081`. Cách đó có thể dùng khi học HTTP nhưng trở nên bất tiện khi có nhiều instance, thay port hoặc triển khai trên các host khác nhau.

Quy trình logic trong hệ thống có discovery và load balancing:

1. `order-service` gửi yêu cầu đến **tên dịch vụ logic** `inventory-service`.
2. Discovery client cung cấp tập instance đang biết của service ID đó.
3. Load balancer chọn một instance theo chính sách và trạng thái khả dụng do implementation hỗ trợ.
4. HTTP client gửi request đến URI thực của instance được chọn.
5. Ứng dụng xử lý kết quả, timeout hoặc lỗi; quyết định retry/fallback theo tính chất nghiệp vụ.

Có thể thực hành với `RestClient` của Spring Framework và tích hợp Spring Cloud LoadBalancer, **nếu release train đã chọn hỗ trợ cách tích hợp đó**. Ví dụ về phần cấu hình client:

~~~java
@Configuration
class ClientConfiguration {
    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Sau khi có builder được Spring quản lý và dependency LoadBalancer phù hợp, request có thể dùng service ID trong URI:

~~~java
String body = loadBalancedRestClientBuilder.build()
        .get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(String.class);
~~~

Ở đây `loadBalancedRestClientBuilder` là bean đã được inject vào lớp thực hiện lời gọi; đoạn mã minh họa **phần gọi**, không phải một class đầy đủ có thể biên dịch độc lập. Nếu release train hoặc HTTP client trong dự án khác nhau, dùng cách tích hợp load balancing được tài liệu của đúng phiên bản hỗ trợ.

Những điều cần thử nghiệm có chủ đích:

| Tình huống | Quan sát mong đợi | Cần hiểu |
| --- | --- | --- |
| Cả hai instance chạy | Request thành công; có thể quan sát instance được chọn nếu response/log cho biết nguồn. | Discovery và load balancing là hai bước riêng. |
| Một instance dừng | Một số request có thể lỗi trước khi thông tin discovery/health cập nhật hoặc client loại bỏ instance. | Discovery có độ trễ, cache và giới hạn. |
| Không có instance | Bên gọi không thể chọn đích phù hợp; phải xử lý lỗi rõ ràng. | Lookup thất bại khác lỗi nghiệp vụ 404 từ dịch vụ đích. |
| Instance nhận request nhưng phản hồi chậm | Có thể phát sinh timeout; retry chỉ dùng khi an toàn và có giới hạn. | Chống khuếch đại tải; cân nhắc tính idempotent. |
| Cấu hình service ID sai | Client không tìm được đúng dịch vụ dù registry vẫn hoạt động. | Tên dịch vụ logic là một phần của hợp đồng tích hợp. |

**Không đồng nhất** load balancing với cơ chế bảo đảm tính sẵn sàng. Một hệ thống cần định nghĩa timeout, chiến lược retry có giới hạn, xử lý idempotency, quan sát lỗi và phương án suy giảm chức năng khi dịch vụ phụ thuộc không đáp ứng.

## 9. Chặng 6: Kiểm thử và vận hành các abstraction

Chỉ kiểm tra happy path là chưa đủ. Với Spring Cloud Core, nên xác minh ít nhất bốn nhóm hành vi sau:

| Nhóm kiểm thử | Ví dụ | Bằng chứng đạt |
| --- | --- | --- |
| **Cấu hình** | Thay biến môi trường/profile; bỏ một thuộc tính bắt buộc; thử cấu hình sai kiểu dữ liệu. | Ứng dụng nhận đúng giá trị hoặc fail fast với lỗi có thể chẩn đoán. |
| **Context/refresh** | Đổi nguồn cấu hình, refresh đúng quy trình, so sánh kết quả trước/sau. | Quan sát được bean thuộc refresh scope thay đổi đúng lúc; biết bean nào không đổi. |
| **Discovery/load balancing** | Trả về 0/1/n instance từ nguồn discovery giả lập; thay URI instance. | Client xử lý có instance, không instance và thông tin instance thay đổi. |
| **Giao tiếp và sự cố** | Dịch vụ đích trả 500, timeout, từ chối kết nối, chạy chậm. | Lỗi được ghi log có ngữ cảnh, không chặn vô thời hạn; hành vi retry/fallback phù hợp. |

Gợi ý dùng các mức kiểm thử tăng dần:

- **Unit test** cho xử lý nghiệp vụ và quy tắc chọn hành động khi HTTP call thất bại; mock dependency ở biên phù hợp.
- **Spring test / integration test** cho binding `@ConfigurationProperties`, auto-configuration, discovery client và HTTP client thực tế ở môi trường kiểm soát.
- **Smoke test** cho hai service thật: khởi động, gọi endpoint, dừng một instance rồi kiểm tra biểu hiện của hệ thống.
- **Kiểm tra vận hành** qua log, health/readiness và metrics. Actuator có thể hỗ trợ nhưng endpoint được expose tùy cấu hình; không mở rộng bừa bãi trong production.

Nên ghi các trường quan trọng: service ID, instance đích, thời gian đáp ứng, mã lỗi, correlation/trace ID nếu hệ thống có tracing. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào log. Với request liên dịch vụ, đo p95/p99 latency và tỉ lệ lỗi để tránh chỉ dựa vào cảm giác “chạy được”.

## 10. Chặng 7: Mini-project tổng hợp

Thực hiện một hệ thống nhỏ gồm `order-service` và **hai instance** `inventory-service`. Có thể giữ tất cả chạy trên máy local ở các port khác nhau.

**Yêu cầu chức năng:**

1. `inventory-service` cung cấp `GET /api/stock/{sku}`, trả về mã hàng, số lượng còn và một trường `instanceId` để dễ quan sát instance xử lý.
2. `order-service` cung cấp `GET /api/orders/check/{sku}` và gọi `inventory-service` bằng tên dịch vụ logic.
3. Cấu hình các instance ban đầu bằng SimpleDiscoveryClient, sau đó (nếu có điều kiện) thử thay bằng registry implementation đang học.
4. Cho phép tùy chỉnh một thuộc tính nghiệp vụ đơn giản qua externalized configuration.
5. Thử thao tác refresh đúng với cấu hình đã bật, kiểm tra khác biệt giữa bean thường và bean thuộc refresh scope.
6. Viết test cho trường hợp thành công, không có instance, HTTP error và timeout.
7. Bổ sung health endpoint và log đủ để chỉ ra dịch vụ/instance chịu trách nhiệm khi có lỗi.

**Kịch bản xác nhận:** gọi liên tiếp để kiểm tra service ID được phân giải; dừng một instance; so sánh log và đáp ứng trước/sau; sửa cấu hình; quan sát hành vi sau refresh; chạy lại test. Khi ghi kết quả, nêu rõ library/version, nguồn discovery, điều kiện timeout và những endpoint đã expose, vì các chi tiết này ảnh hưởng trực tiếp tới quan sát.

Một bảng kết quả ngắn có thể gồm:

| Kịch bản | Kỳ vọng | Kết quả thực tế | Giải thích |
| --- | --- | --- | --- |
| Hai instance sẵn sàng | Gọi dịch vụ theo tên logic thành công | Tự điền | Cách client chọn instance |
| Một instance ngừng | Có thể có lỗi/chậm cập nhật trước khi hệ thống ổn định | Tự điền | Cache, health và timeout |
| Không tìm được instance | Lỗi được xử lý rõ ràng | Tự điền | Xử lý khi discovery trả rỗng |
| Thay đổi cấu hình | Kết quả thay đổi theo đúng cơ chế áp dụng | Tự điền | Restart hay refresh; bean liên quan |
| Đích trả 5xx/timeout | Quan sát được lỗi và giới hạn thời gian chờ | Tự điền | Chính sách lỗi của client |

## 11. Sai lầm thường gặp khi bắt đầu

- **Học tên sản phẩm trước abstraction:** biết cách chạy một registry nhưng không giải thích được `DiscoveryClient` và `ServiceRegistry` khác nhau ở đâu. Hãy thực hành SimpleDiscoveryClient trước rồi mới chọn provider.
- **Ghép phiên bản theo bài hướng dẫn cũ:** một ví dụ có thể dùng Spring Boot và Spring Cloud không còn tương thích với môi trường hiện tại. Luôn đối chiếu release train và dependency tree.
- **Nhầm đổi tệp YAML với refresh:** một bean singleton có thể giữ giá trị đã đọc trước đó. Phải xác định nguồn cấu hình, cơ chế refresh và scope.
- **Nghĩ rằng tìm được URI là đủ:** instance có thể chưa sẵn sàng hoặc lỗi sau khi được discover. Phải thử các tình huống lỗi HTTP/network.
- **Retry mọi request:** retry thiếu giới hạn có thể tạo trùng giao dịch hoặc tăng tải khi hệ thống đang sự cố. Cần hiểu timeout và tính idempotent.
- **Mở rộng endpoint quản trị để dễ demo:** endpoint liên quan tới cấu hình và vận hành có thể nhạy cảm; chỉ expose những gì thực sự cần và giới hạn quyền truy cập.

## 12. Checklist hoàn thành module

Bạn có thể chuyển sang chủ đề Spring Cloud chuyên sâu hơn khi tự trả lời và chứng minh được các câu sau:

- [ ] Phân biệt Spring Boot, Spring Cloud Commons và Spring Cloud Context bằng trách nhiệm cụ thể.
- [ ] Chọn được Spring Cloud release train tương thích với Spring Boot và JDK của dự án.
- [ ] Giải thích được dependency management BOM khác dependency thực tế.
- [ ] Dùng được externalized configuration, profile và binding kiểu rõ ràng.
- [ ] Giải thích được khi nào bean nhận cấu hình mới, khi nào cần refresh hoặc restart.
- [ ] Phân biệt discovery, service registration, service instance và load balancing.
- [ ] Gọi được dịch vụ khác qua service ID và xử lý trường hợp không tìm thấy instance.
- [ ] Kiểm thử được lỗi HTTP, timeout và thay đổi trạng thái instance.
- [ ] Có log/health/metrics cơ bản và không expose thông tin quản trị nhạy cảm.
- [ ] Hoàn thành mini-project, lưu các bước chạy, test và nhận xét về giới hạn quan sát.

### Nên học gì tiếp theo?

Sau khi nắm kiến thức cốt lõi, có thể mở rộng theo nhu cầu hệ thống: **Spring Cloud Config** cho quản lý cấu hình tập trung; một **discovery provider** phù hợp môi trường; **Spring Cloud Gateway** cho API entry point; cơ chế chịu lỗi như circuit breaker; tracing phân tán; hoặc tích hợp cloud/Kubernetes. Chúng sử dụng hoặc bổ sung các khái niệm đã học, nhưng mỗi thành phần có cấu hình, giới hạn và yêu cầu phiên bản riêng.

**Tài liệu nên đối chiếu khi thực hành:** tài liệu chính thức của Spring Boot về externalized configuration và Actuator; tài liệu Spring Cloud về release train, compatibility, Commons, Context, LoadBalancer; và tài liệu của discovery provider đang sử dụng. Kiểm tra đúng phiên bản được chọn thay vì lấy cấu hình từ nhiều thế hệ Spring Cloud trộn lẫn.
