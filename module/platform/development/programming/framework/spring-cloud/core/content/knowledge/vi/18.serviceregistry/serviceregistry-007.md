# Endpoint serviceregistry và yêu cầu có Registration bean

Bài học thuộc chương **ServiceRegistry** của module **SPRING_CLOUD_CORE**. Spring Cloud Commons cung cấp abstraction `ServiceRegistry` để đăng ký, hủy đăng ký và cập nhật trạng thái của service instance trong registry. Spring Cloud Actuator cũng cung cấp endpoint `/serviceregistry` để đọc hoặc thay đổi trạng thái của registration hiện tại.

Endpoint này có một điều kiện quan trọng: trong Spring `ApplicationContext` phải có bean triển khai `Registration`. `Registration` là marker interface mô tả một lần đăng ký theo contract chung; mỗi discovery provider cung cấp kiểu cụ thể của riêng mình. Vì vậy, endpoint cần registration phù hợp với `ServiceRegistry` của provider đang chạy, chứ chỉ có một bean `ServiceRegistry` hoặc chỉ thêm Actuator dependency chưa đủ.

Bài học tập trung vào endpoint, điều kiện bean, cách bật HTTP exposure, thao tác GET/POST, trạng thái do provider quy định, auto-registration và cách kiểm thử.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của `ServiceRegistry` và `Registration` trong Spring Cloud Commons.
2. Phân biệt registration object với service registry implementation.
3. Nêu được điều kiện để endpoint `/serviceregistry` hoạt động: có bean `Registration` phù hợp trong ApplicationContext.
4. Bật và expose endpoint qua Spring Boot Actuator.
5. Dùng GET để đọc trạng thái registration hiện tại.
6. Dùng POST với JSON field `status` để cập nhật trạng thái.
7. Chọn status hợp lệ theo discovery provider đang dùng.
8. Phân biệt thay đổi status với register, deregister và dừng ứng dụng.
9. Hiểu mối liên hệ giữa Registration bean và auto-registration lúc startup.
10. Kiểm tra endpoint, bean, provider và trạng thái trên registry trong integration test.
11. Bảo vệ thao tác thay đổi trạng thái bằng authentication, authorization và network policy.

## 2. ServiceRegistry và Registration là hai vai trò khác nhau

Spring Cloud Commons định nghĩa abstraction chung để các ứng dụng không phải gọi API riêng của từng registry trong phần lớn logic quản lý service.

### 2.1. ServiceRegistry

`ServiceRegistry` là contract của thành phần giao tiếp với registry. Nó cung cấp các thao tác quản lý registration, tiêu biểu:

- `register(Registration)`: đăng ký một service instance.
- `deregister(Registration)`: hủy đăng ký một service instance.
- `setStatus(Registration, status)`: yêu cầu provider cập nhật trạng thái.
- `getStatus(Registration)`: đọc trạng thái theo cách provider hỗ trợ.
- `close()`: đóng tài nguyên của implementation khi cần.

Các method cụ thể và semantics của status phụ thuộc implementation. Một registry có thể ánh xạ status thành trạng thái riêng, trong khi provider khác có tập giá trị hoặc cách cập nhật khác.

### 2.2. Registration

`Registration` là marker interface đại diện cho dữ liệu đăng ký của một instance. Nó không tự thực hiện giao tiếp mạng và cũng không phải một registry client độc lập.

Một registration thường mô tả những thông tin như:

- Service ID hoặc application name.
- Instance ID.
- Host và port.
- URI hoặc thông tin secure.
- Metadata của instance.
- Các thông tin đặc thù mà provider cần để đăng ký.

Các trường thực tế do implementation định nghĩa. Không giả định mọi Registration đều có cùng getter, cấu trúc hoặc cách khởi tạo.

### 2.3. Quan hệ giữa hai thành phần

~~~mermaid
flowchart LR
    APP["Spring ApplicationContext"] --> REGISTRATION["Registration bean"]
    REGISTRATION --> ENDPOINT["/actuator/serviceregistry"]
    ENDPOINT --> REGISTRY["Provider ServiceRegistry"]
    REGISTRY --> ADAPTER["Eureka / Consul / Zookeeper adapter"]
    ADAPTER --> BACKEND["Remote service registry"]
~~~

Endpoint nhận Registration hiện tại từ ApplicationContext và sử dụng ServiceRegistry implementation để đọc hoặc cập nhật trạng thái. Hai thành phần phải tương thích với cùng provider.

Ví dụ các cặp provider-specific được Spring Cloud Commons nhắc đến:

| Registration implementation | ServiceRegistry implementation |
| --- | --- |
| `EurekaRegistration` | `EurekaServiceRegistry` |
| `ConsulRegistration` | `ConsulServiceRegistry` |
| `ZookeeperRegistration` | `ZookeeperServiceRegistry` |

Không tạo một class chỉ implements `Registration` rồi kỳ vọng mọi provider có thể đăng ký nó. Vì Registration là marker interface, provider cần kiểu cụ thể mà implementation của nó hiểu.

## 3. Endpoint serviceregistry hoạt động thế nào?

Spring Cloud Commons cung cấp Actuator endpoint có ID là `serviceregistry`. Với HTTP management base path mặc định của Spring Boot, URL thường là:

~~~text
/actuator/serviceregistry
~~~

Đường dẫn thực tế có thể thay đổi nếu ứng dụng chỉnh `management.endpoints.web.base-path` hoặc chạy management server trên port riêng.

### 3.1. GET đọc trạng thái

Gửi GET tới endpoint để đọc status của Registration hiện tại:

~~~bash
curl --request GET \
  http://localhost:8080/actuator/serviceregistry
~~~

Endpoint trả về trạng thái hiện tại theo cách provider biểu diễn. Hình thức response chi tiết có thể khác theo phiên bản và implementation, vì vậy không nên hard-code một JSON response chung cho mọi registry.

### 3.2. POST thay đổi trạng thái

Gửi POST cùng endpoint với JSON body có field `status`:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"status":"OUT_OF_SERVICE"}' \
  http://localhost:8080/actuator/serviceregistry
~~~

Endpoint yêu cầu đúng field `status`. Giá trị truyền vào phải nằm trong tập status mà ServiceRegistry provider hỗ trợ. Ví dụ Eureka thường hỗ trợ:

- `UP`
- `DOWN`
- `OUT_OF_SERVICE`
- `UNKNOWN`

Các giá trị trên là ví dụ của Eureka, không phải enum dùng chung cho mọi provider. Hãy xem tài liệu của implementation cụ thể trước khi gửi POST.

### 3.3. Ý nghĩa của thao tác POST

POST yêu cầu ServiceRegistry cập nhật trạng thái của Registration hiện tại. Nó không tương đương với:

- Đăng ký một instance mới.
- Hủy đăng ký instance.
- Dừng JVM hoặc tắt HTTP server.
- Thay đổi trực tiếp trạng thái của tất cả replica.
- Bảo đảm mọi discovery client lập tức loại instance khỏi cache.

Registry và các consumer có thể có cơ chế đồng bộ/cache riêng. Sau khi đổi status, cần xác minh trạng thái ở registry và hành vi của consumer.

## 4. Điều kiện bắt buộc: Registration bean trong ApplicationContext

### 4.1. Vì sao endpoint cần Registration bean?

Endpoint cần biết registration nào đại diện cho instance đang chạy để đọc hoặc cập nhật status. Spring Cloud Commons xác định rõ endpoint dựa vào một bean `Registration` trong Spring ApplicationContext.

Vì vậy, cần phân biệt các trường hợp:

| Bean/Dependency | Có đủ để đáp ứng yêu cầu endpoint? | Lý do |
| --- | --- | --- |
| `spring-boot-starter-actuator` | Không. | Chỉ cung cấp hạ tầng Actuator. |
| `ServiceRegistry` | Chưa đủ. | Registry implementation biết cách gọi provider nhưng endpoint còn cần registration cụ thể. |
| `Registration` phù hợp | Là điều kiện được tài liệu endpoint yêu cầu. | Đại diện cho instance mà endpoint sẽ đọc/cập nhật status. |
| Cả `Registration` và ServiceRegistry provider phù hợp | Cấu hình cần có trong ứng dụng registry-backed thông thường. | Endpoint có registration và implementation để thao tác với registry. |

Một ứng dụng có thể có provider dependency nhưng không có Registration bean do auto-configuration bị loại, provider không được kích hoạt hoặc ứng dụng tự cấu hình theo cách khác. Khi đó endpoint có thể không được tạo hoặc không hoạt động như mong đợi.

### 4.2. Registration thường đến từ đâu?

Trong tích hợp Eureka, Consul hoặc Zookeeper, starter/provider auto-configuration thường tạo registration object cùng các bean quản lý registry. Ứng dụng không cần tự tạo marker bean bằng tay nếu provider đã cung cấp đúng bean.

Ví dụ các kiểu cụ thể:

~~~java
// Các kiểu minh họa theo provider:
EurekaRegistration
ConsulRegistration
ZookeeperRegistration
~~~

Các class này thuộc module/provider tương ứng. Không import một class provider nếu ứng dụng không dùng provider đó.

### 4.3. Kiểm tra bean lúc khởi động

Có thể kiểm tra các bean liên quan trong integration test hoặc lúc debug:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void registrationBeanExists() {
    assertThat(
        applicationContext.getBeansOfType(Registration.class)
    ).isNotEmpty();
}

@Test
void serviceRegistryBeanExists() {
    assertThat(
        applicationContext.getBeansOfType(ServiceRegistry.class)
    ).isNotEmpty();
}
~~~

Hai phép kiểm tra trên xác nhận context có bean theo kiểu chung. Chúng chưa chứng minh provider đã kết nối thành công hoặc instance đã được đăng ký. Cần kiểm tra thêm status ở registry thực tế.

Nếu có nhiều registration bean hoặc nhiều provider trong cùng context, cần xác định rõ bean mà endpoint/provider sử dụng. Không coi việc map có phần tử là bằng chứng endpoint sẽ chọn đúng registration mong muốn.

## 5. Bật Actuator và expose endpoint

### 5.1. Dependency

Ứng dụng cần Actuator và discovery provider có tích hợp ServiceRegistry/Registration tương ứng. Ví dụ dependency Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Thêm starter provider phù hợp với registry mà ứng dụng sử dụng, ví dụ Eureka, Consul hoặc Zookeeper. Dependency provider cần tương thích với Spring Boot và Spring Cloud release train trong dự án.

### 5.2. Expose endpoint qua HTTP

Spring Boot không mặc định expose tất cả Actuator endpoint qua HTTP. Thêm ID `serviceregistry` vào danh sách exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,serviceregistry
~~~

Nếu dự án đã có danh sách include, hãy bổ sung ID này vào danh sách hiện tại để giữ các endpoint cần thiết khác.

Không dùng `include: "*"` chỉ để thử endpoint trong production. Exposure làm endpoint có thể truy cập qua HTTP; quyền truy cập còn phải được kiểm soát bằng Spring Security và network policy.

### 5.3. Management port và base path

Nếu ứng dụng cấu hình management port riêng:

~~~yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,serviceregistry
~~~

URL sẽ dùng management port và base path đã cấu hình, ví dụ:

~~~text
http://localhost:9090/manage/serviceregistry
~~~

Không mặc định endpoint luôn nằm ở port ứng dụng hoặc có prefix `/actuator`. Hãy đọc cấu hình management thực tế.

## 6. Auto-registration và Registration bean

ServiceRegistry provider thường tự đăng ký instance ứng dụng khi khởi động. Spring Cloud Commons cho phép tắt hành vi này bằng cấu hình:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Hoặc dùng annotation trong các cấu hình có sử dụng:

~~~java
@EnableDiscoveryClient(autoRegister = false)
~~~

Trong Spring Cloud hiện đại, `@EnableDiscoveryClient` không còn bắt buộc chỉ để kích hoạt discovery khi provider auto-configuration đã có trên classpath; tuy nhiên thuộc tính auto-register của annotation vẫn có thể xuất hiện trong các cấu hình tương thích cũ. Property thường dễ quản lý theo profile/deployment hơn.

### 6.1. Tắt auto-registration không đồng nghĩa tắt discovery

Ba thao tác này khác nhau:

| Thao tác | Ý nghĩa |
| --- | --- |
| Tắt auto-registration | Ứng dụng không tự đăng ký instance theo lifecycle mặc định. |
| Tắt discovery | Ứng dụng không sử dụng discovery client theo cấu hình tương ứng. |
| Tắt endpoint serviceregistry exposure | HTTP endpoint không được expose; không tự thay đổi registration trong registry. |

Khi `spring.cloud.service-registry.auto-registration.enabled=false`, các event auto-registration `InstancePreRegisteredEvent` và `InstanceRegisteredEvent` sẽ không được phát theo lifecycle tự động. Điều này không tự nói lên bean Registration có còn trong context hay không; phải kiểm tra provider configuration và bean thực tế.

### 6.2. Endpoint cần registration hiện tại, không chỉ ý định auto-register

Nếu auto-registration đã tắt, không giả định endpoint vẫn có một registration hợp lệ chỉ vì ServiceRegistry bean tồn tại. Cần xác minh:

1. Provider có tạo Registration bean hay không.
2. Registration đó mô tả instance nào.
3. Instance đã được register thủ công hoặc bằng một lifecycle khác chưa.
4. Provider chấp nhận thao tác setStatus trên registration hiện tại hay không.

Nếu ứng dụng dùng quy trình đăng ký thủ công, hãy tự quản lý vòng đời registration và bảo đảm endpoint được nối với registration đúng.

## 7. Đăng ký và hủy đăng ký bằng ServiceRegistry

Spring Cloud Commons cho phép ứng dụng quản lý registration qua abstraction ServiceRegistry. Ví dụ tổng quát:

~~~java
public class RegistryCoordinator<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;

    public RegistryCoordinator(ServiceRegistry<R> serviceRegistry) {
        this.serviceRegistry = serviceRegistry;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

Kiểu generic `R` phải là Registration implementation mà ServiceRegistry tương ứng hỗ trợ. Ví dụ, EurekaServiceRegistry cần registration kiểu Eureka mà provider mong đợi.

Một ứng dụng có thể tắt auto-registration rồi gọi register/deregister trong một quy trình riêng, chẳng hạn event, workflow quản trị hoặc custom endpoint. Hãy đảm bảo thao tác có tính lặp an toàn phù hợp và có xử lý lỗi khi registry không sẵn sàng.

### 7.1. Đừng nhầm register với setStatus

| Method | Mục đích |
| --- | --- |
| `register(registration)` | Tạo/cập nhật đăng ký instance theo semantics provider. |
| `deregister(registration)` | Hủy đăng ký instance. |
| `setStatus(registration, status)` | Thay đổi trạng thái của registration đã xác định. |
| `getStatus(registration)` | Đọc trạng thái registration theo provider. |

Endpoint `/serviceregistry` tập trung vào status của Registration hiện tại. Nó không phải API tổng quát để tạo nhiều service registration hoặc hủy đăng ký bất kỳ service nào.

## 8. Các sự kiện auto-registration

Spring Cloud Commons công bố hai event quan trọng:

- `InstancePreRegisteredEvent`: phát trước khi instance được đăng ký.
- `InstanceRegisteredEvent`: phát sau khi instance được đăng ký.

Ứng dụng có thể dùng ApplicationListener để ghi audit, cập nhật metadata phụ trợ hoặc thực hiện logic cần chạy trước/sau đăng ký.

Ví dụ listener:

~~~java
@Component
public class RegistrationEvents
        implements ApplicationListener<InstanceRegisteredEvent<?>> {

    @Override
    public void onApplicationEvent(InstanceRegisteredEvent<?> event) {
        // Ghi nhận việc provider đã hoàn tất bước auto-registration.
        // Không ghi credential hoặc thông tin nhạy cảm của registration.
    }
}
~~~

Chữ ký generic event và import có thể thay đổi theo release train; đối chiếu API đúng phiên bản. Event auto-registration không được phát khi `spring.cloud.service-registry.auto-registration.enabled=false`.

Không dùng event after-registration như bằng chứng tất cả consumer đã nhìn thấy instance. Registry có thể cần thời gian đồng bộ và client có thể cache kết quả.

## 9. Thay đổi status với endpoint

### 9.1. Kiểm tra status hiện tại

~~~bash
curl --request GET \
  http://localhost:8080/actuator/serviceregistry
~~~

Đọc response và ghi lại trạng thái hiện tại trước khi thay đổi. Cách biểu diễn response phụ thuộc provider/phiên bản; chỉ dựa vào field status mà endpoint trả về.

### 9.2. Đưa instance ra khỏi trạng thái phục vụ

Ví dụ với provider hỗ trợ `OUT_OF_SERVICE`:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"status":"OUT_OF_SERVICE"}' \
  http://localhost:8080/actuator/serviceregistry
~~~

Ý định thường gặp là tạm thời đánh dấu instance không nên nhận traffic mới theo semantics của registry. Consumer và load balancer chỉ phản ứng đúng nếu provider chuyển trạng thái này thành thông tin mà client hiểu và cập nhật kịp thời.

### 9.3. Đưa instance trở lại

Ví dụ với provider hỗ trợ `UP`:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"status":"UP"}' \
  http://localhost:8080/actuator/serviceregistry
~~~

Sau đó đọc GET lại và xác minh trạng thái trong registry. Không gửi `UP` chỉ vì process đang chạy; trước hết cần xác nhận ứng dụng đủ điều kiện nhận traffic.

### 9.4. Ví dụ Eureka

Eureka thường hỗ trợ các trạng thái `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`. Một số trạng thái có ý nghĩa vận hành khác nhau:

| Status | Ý nghĩa tổng quát |
| --- | --- |
| `UP` | Instance được đánh dấu sẵn sàng theo trạng thái Eureka. |
| `DOWN` | Instance được đánh dấu không hoạt động. |
| `OUT_OF_SERVICE` | Instance được đưa ra khỏi trạng thái phục vụ thông thường. |
| `UNKNOWN` | Trạng thái không xác định theo Eureka. |

Đây là ví dụ riêng của Eureka. Consul, Zookeeper và provider khác có thể có status string, mapping hoặc hành vi hoàn toàn khác. Không gửi các giá trị này cho provider khác nếu tài liệu provider không hỗ trợ.

## 10. Status không thay thế health check và readiness

Service registry status và application health là hai tín hiệu liên quan nhưng không đồng nhất.

- Health endpoint báo tình trạng của ứng dụng hoặc các thành phần được health contributor kiểm tra.
- Readiness cho biết instance có sẵn sàng nhận traffic theo chính sách nền tảng hay không.
- Registration status là trạng thái được ghi vào registry thông qua ServiceRegistry provider.
- Discovery client và load balancer đọc dữ liệu registry theo cơ chế riêng.

Đổi status không tự dừng HTTP server, không đóng database connection, không tắt scheduler và không ngăn mọi request nội bộ. Nếu cần drain traffic an toàn, phải phối hợp readiness, registry status, load balancer behavior và graceful shutdown.

Một quy trình drain có thể gồm:

1. Đánh dấu instance không nhận traffic mới theo cơ chế readiness/registry.
2. Chờ consumer hoặc load balancer cập nhật.
3. Chờ request và transaction đang chạy hoàn tất.
4. Dừng listener/background worker theo thứ tự.
5. Hủy registration khi quy trình shutdown yêu cầu.
6. Dừng process.

Thứ tự chính xác phụ thuộc orchestrator, provider và chính sách deployment.

## 11. Bảo mật endpoint serviceregistry

POST thay đổi trạng thái một instance trong registry. Nếu người không có quyền có thể gọi endpoint, họ có thể đưa instance ra khỏi trạng thái phục vụ hoặc thay đổi trạng thái theo cách ảnh hưởng định tuyến.

Các biện pháp cần có:

1. Chỉ expose `serviceregistry` khi có nhu cầu vận hành rõ ràng.
2. Bảo vệ endpoint bằng Spring Security authentication và role/authority quản trị.
3. Giới hạn truy cập bằng management network, firewall hoặc network policy.
4. Dùng TLS khi request đi qua mạng.
5. Ghi audit actor, thời điểm, instance và status trước/sau.
6. Không ghi token, credential hoặc thông tin nhạy cảm của Registration vào log.
7. Theo dõi request POST bất thường và các lần status đổi liên tục.
8. Xác minh status hợp lệ theo provider; không cho phép giá trị tùy ý từ UI quản trị.
9. Dùng quy trình phê duyệt/automation phù hợp nếu thay đổi có thể làm giảm capacity của cluster.
10. Không public toàn bộ Actuator endpoints chỉ để mở một endpoint.

Ví dụ exposure tối thiểu:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,serviceregistry
~~~

Exposure chỉ quyết định endpoint có thể được truy cập qua HTTP. Nó không thay thế authorization. Hãy cấu hình security chain để chỉ principal quản trị phù hợp được GET/POST và kiểm tra CSRF policy theo cách ứng dụng bảo vệ các endpoint quản trị.

## 12. Kiểm thử Registration bean và endpoint

### 12.1. Kiểm thử bean prerequisite

Khởi động ApplicationContext với discovery provider test phù hợp rồi xác minh Registration bean:

~~~java
@Test
void applicationContextContainsRegistration() {
    assertThat(applicationContext.getBeansOfType(Registration.class))
        .isNotEmpty();
}
~~~

Nếu test không dùng registry-backed provider, không nên giả định có Registration bean. Dùng test configuration/provider fixture có chủ đích để xác minh endpoint.

### 12.2. Kiểm thử ServiceRegistry implementation

~~~java
@Test
void serviceRegistryImplementationIsAvailable() {
    assertThat(applicationContext.getBeansOfType(ServiceRegistry.class))
        .isNotEmpty();
}
~~~

Bean tồn tại không chứng minh registry server đang reachable. Cần có integration test riêng khi muốn xác minh network/provider interaction.

### 12.3. Kiểm thử HTTP GET

Với Actuator endpoint đã expose trong test context, gọi GET `/actuator/serviceregistry` và xác minh response thành công cùng trạng thái mong đợi theo provider fixture.

Không khẳng định một JSON schema chung nếu implementation trả response khác nhau. Assert các field đã được xác định từ endpoint/version đang test.

### 12.4. Kiểm thử HTTP POST

Gửi body có field status:

~~~json
{
  "status": "OUT_OF_SERVICE"
}
~~~

Sau POST:

1. Xác minh response status code theo endpoint/version.
2. Đọc GET lại endpoint.
3. Xác minh ServiceRegistry nhận lệnh cập nhật.
4. Đọc trạng thái từ provider test double hoặc registry test instance.
5. Xác minh một status không được provider hỗ trợ bị xử lý theo lỗi của implementation.

### 12.5. Kiểm thử trường hợp thiếu Registration

Tạo test context có ServiceRegistry nhưng không có Registration bean phù hợp. Xác minh endpoint không thể hoạt động như trường hợp đầy đủ. Tùy auto-configuration và phiên bản, endpoint có thể không được tạo hoặc không sẵn sàng; kiểm tra điều kiện thực tế thay vì gắn một mã lỗi HTTP cố định.

## 13. Ma trận kiểm thử và chẩn đoán

| ID | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| SR1 | Provider tạo Registration bean và ServiceRegistry bean. | Endpoint được cấu hình với registration hiện tại. |
| SR2 | Có Actuator nhưng không có Registration bean. | Endpoint không đáp ứng prerequisite. |
| SR3 | GET endpoint. | Đọc được status theo provider. |
| SR4 | POST status hợp lệ. | Provider nhận yêu cầu cập nhật status. |
| SR5 | POST status không hợp lệ. | Provider từ chối hoặc báo lỗi theo implementation. |
| SR6 | Auto-registration bật. | Lifecycle đăng ký instance chạy theo provider. |
| SR7 | Auto-registration tắt. | Không có hai event auto-registration; kiểm tra riêng Registration bean và quy trình manual. |
| SR8 | Endpoint chưa expose. | HTTP route không truy cập được dù bean có thể tồn tại. |
| SR9 | Principal không có quyền POST. | Security từ chối thay đổi status. |
| SR10 | Registry không reachable. | Lỗi provider được quan sát và xử lý có kiểm soát. |
| SR11 | POST OUT_OF_SERVICE. | Kiểm tra registry và hành vi consumer/load balancer. |
| SR12 | POST UP. | Instance chỉ nhận traffic lại khi các readiness/registry điều kiện phù hợp. |

### 13.1. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/serviceregistry` trả 404. | Endpoint chưa được expose, Actuator thiếu hoặc endpoint không được tạo. | Kiểm tra dependency, exposure và điều kiện Registration bean. |
| Có ServiceRegistry nhưng endpoint không hoạt động. | Thiếu Registration bean phù hợp. | Kiểm tra bean theo `Registration.class` và provider auto-configuration. |
| Không có Registration bean. | Provider starter thiếu, auto-configuration bị loại hoặc ứng dụng dùng registration thủ công. | Kiểm tra provider configuration và tạo registration theo contract provider nếu cần. |
| POST báo status không hợp lệ. | Status không thuộc tập giá trị provider hỗ trợ. | Đọc tài liệu provider và dùng giá trị hợp lệ. |
| GET trả trạng thái khác mong đợi. | Registry có trạng thái riêng, registration khác hoặc dữ liệu cập nhật chưa đồng bộ. | Kiểm tra registration instance, provider API và registry backend. |
| POST thành công nhưng consumer vẫn gọi instance. | Consumer cache, load balancer hoặc registry propagation chưa cập nhật. | Kiểm tra provider semantics, refresh interval và instance list ở consumer. |
| Tắt auto-registration làm ứng dụng không xuất hiện trong registry. | Không còn lifecycle đăng ký tự động và chưa có manual registration. | Tạo quy trình register/deregister rõ ràng. |
| Endpoint có thể GET nhưng POST bị 403. | Security/CSRF policy không cho phép write operation. | Cấp quyền quản trị phù hợp và giữ policy an toàn. |
| POST đổi status nhưng ứng dụng vẫn nhận request trực tiếp. | Registry status không dừng process hoặc HTTP listener. | Kết hợp readiness, load balancer, traffic draining và graceful shutdown. |
| Nhiều provider cùng tồn tại. | Registration bean không rõ ràng hoặc service registry không tương thích. | Xác định provider/registration cần thao tác và kiểm tra bean wiring. |

## 14. Checklist hoàn thành

- [ ] Giải thích được vai trò của ServiceRegistry.
- [ ] Giải thích được Registration là marker interface.
- [ ] Phân biệt Registration bean với ServiceRegistry implementation.
- [ ] Biết endpoint ID là `serviceregistry` và URL mặc định là `/actuator/serviceregistry`.
- [ ] Hiểu endpoint cần Registration bean trong ApplicationContext.
- [ ] Biết Registration implementation phải tương thích với provider.
- [ ] Expose endpoint qua `management.endpoints.web.exposure.include`.
- [ ] Dùng GET để đọc status.
- [ ] Dùng POST JSON có field `status` để thay đổi status.
- [ ] Kiểm tra status hợp lệ trong tài liệu provider.
- [ ] Phân biệt setStatus với register và deregister.
- [ ] Hiểu auto-registration mặc định và cách tắt bằng property.
- [ ] Biết hai event InstancePreRegisteredEvent và InstanceRegisteredEvent.
- [ ] Không suy luận auto-registration disabled đồng nghĩa Registration bean biến mất.
- [ ] Phân biệt status registry với health, readiness và graceful shutdown.
- [ ] Có test cho Registration bean, ServiceRegistry, GET, POST và trường hợp thiếu bean.
- [ ] Bảo vệ endpoint bằng authentication, authorization, TLS, network policy và audit.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): ServiceRegistry, Registration, auto-registration events và Service Registry Actuator endpoint.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): thuộc tính auto-registration của ServiceRegistry.
- [ServiceRegistryEndpoint Javadoc](https://www.javadoc.io/doc/org.springframework.cloud/spring-cloud-commons/latest/org/springframework/cloud/client/serviceregistry/endpoint/ServiceRegistryEndpoint.html): API endpoint đọc và cập nhật trạng thái.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint availability, HTTP exposure và bảo mật Actuator.

Các status, registration type và cách đồng bộ phụ thuộc discovery provider. Hãy kiểm tra implementation thực tế, xác minh bean Registration trong ApplicationContext và thử GET/POST trên môi trường kiểm thử trước khi mở endpoint trong production.
