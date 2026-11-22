# Kiểm tra bean, nguồn cấu hình và điều kiện tự động cấu hình

Khi một ứng dụng Spring Boot hoặc Spring Cloud khởi động, việc tiến trình chạy thành công chưa chứng minh rằng **bean cần dùng đã được tạo**, **giá trị cấu hình đúng đã được nạp** hay **auto-configuration mong muốn đã được áp dụng**. Một ứng dụng có thể mở cổng HTTP nhưng vẫn thiếu `DiscoveryClient`, đọc nhầm profile, dùng giá trị timeout mặc định hoặc không tạo được bean do điều kiện trên classpath không thỏa mãn.

Cách chẩn đoán có hệ thống là đi theo ba câu hỏi:

1. **Bean nào đang tồn tại?** Bean được đăng ký từ component scan, cấu hình thủ công hay auto-configuration nào?
2. **Giá trị cấu hình đến từ đâu?** Property nào thắng khi có nhiều nguồn cùng khai báo, profile nào đang hoạt động và Config Server có tham gia không?
3. **Vì sao auto-configuration được bật hoặc bị bỏ qua?** Điều kiện nào match, điều kiện nào không match và dependency/bean/property nào còn thiếu?

Bài học thuộc chương **Khởi tạo** của module **SPRING_CLOUD_CORE**, tập trung vào các abstraction chung của Spring Cloud trong ứng dụng Spring Boot: `ApplicationContext`, `Environment`, cấu hình bên ngoài, discovery, service registry, refresh scope và cách kiểm thử, vận hành quá trình khởi tạo.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt `BeanDefinition`, bean instance và auto-configuration.
- Kiểm tra bean theo tên, kiểu, nguồn đăng ký và trạng thái trong `ApplicationContext`.
- Đọc các `PropertySource` trong `Environment`, xác định giá trị cuối cùng và nguồn cấu hình ưu tiên.
- Hiểu thời điểm nạp Config Data, profile và cấu hình từ Spring Cloud Config.
- Đọc condition evaluation report để giải thích vì sao một auto-configuration hoặc bean được bật/tắt.
- Viết kiểm thử khởi tạo cô lập bằng `ApplicationContextRunner` và kiểm thử tích hợp phù hợp.
- Chẩn đoán các lỗi thường gặp như thiếu bean, sai profile, property bị ghi đè, thiếu implementation discovery hoặc điều kiện auto-configuration không thỏa mãn.

## 2. Bức tranh khởi tạo: từ cấu hình đến bean

Spring Boot tổ chức quá trình khởi tạo quanh `SpringApplication` và Spring `ApplicationContext`. Ở mức khái quát, luồng thường gồm:

~~~mermaid
flowchart TD
    A[SpringApplication.run] --> B[Chuẩn bị Environment]
    B --> C[Nạp Config Data và profile]
    C --> D[Tạo ApplicationContext]
    D --> E[Đăng ký BeanDefinition]
    E --> F[Refresh ApplicationContext]
    F --> G[Đánh giá điều kiện và tạo singleton]
    G --> H[Chạy ApplicationRunner / CommandLineRunner]
    H --> I[ApplicationReady]
~~~

Sơ đồ mô tả các giai đoạn chính; chi tiết nội bộ có thể thay đổi theo phiên bản Boot và loại ứng dụng.

### 2.1. Environment được chuẩn bị trước khi bean thông thường được tạo

`Environment` là abstraction của Spring để truy cập profile và các nguồn thuộc tính. Trong Spring Boot, các file cấu hình theo quy ước như `application.properties` hoặc `application.yaml` được nạp trong giai đoạn chuẩn bị môi trường thông qua cơ chế Config Data. Những thuộc tính ảnh hưởng đến việc chọn cấu hình, chẳng hạn `spring.config.name`, `spring.config.location`, `spring.config.additional-location` và profile active, phải được cung cấp đủ sớm để quá trình nạp cấu hình sử dụng được chúng.

Điều này giải thích vì sao thêm một `@PropertySource` trong lớp `@Configuration` không phải cách thích hợp để đặt mọi thuộc tính khởi động: annotation đó được xử lý trong quá trình tạo context, có thể quá muộn đối với một số thiết lập cần thiết để quyết định Config Data hoặc bootstrap.

### 2.2. BeanDefinition và bean instance là hai trạng thái khác nhau

Spring container thường đăng ký metadata dưới dạng `BeanDefinition` trước khi tạo đối tượng thực tế.

- **BeanDefinition** mô tả bean: tên, kiểu dự kiến, factory method, scope, dependency và metadata liên quan.
- **Bean instance** là đối tượng đã được container tạo và quản lý.
- **Singleton scope** thường tạo một instance dùng chung trong một `ApplicationContext`; singleton không có nghĩa là duy nhất trên toàn bộ JVM nếu có nhiều context.
- **Lazy initialization** có thể trì hoãn việc tạo bean cho đến lần truy cập đầu tiên.
- **Prototype** tạo instance mới theo yêu cầu; không được quản lý vòng đời đầy đủ như singleton.

Vì vậy, nhìn thấy bean definition không nhất thiết chứng minh đối tượng đã được khởi tạo. Ngược lại, kiểm tra một bean bằng `getBean()` có thể kích hoạt khởi tạo và làm phát sinh lỗi phụ thuộc; khi chỉ chẩn đoán metadata, nên bắt đầu bằng cách liệt kê tên/definition.

### 2.3. Bean đến từ đâu?

Một bean trong ứng dụng có thể được đăng ký bởi:

1. **Component scanning:** các lớp được đánh dấu `@Component`, `@Service`, `@Repository`, `@Controller` hoặc stereotype tương ứng.
2. **Java configuration:** phương thức `@Bean` trong một lớp `@Configuration` hoặc cấu hình tương thích.
3. **Auto-configuration:** cấu hình do thư viện cung cấp, được Spring Boot xét theo điều kiện.
4. **Import trực tiếp:** `@Import`, registrar hoặc cơ chế đăng ký bean chuyên biệt.
5. **Cơ chế tích hợp của framework:** ví dụ Spring Cloud tạo bean liên quan đến discovery, Config Client hoặc refresh khi dependency và điều kiện phù hợp.

Một bean có tên giống nhau có thể đến từ những nguồn khác nhau giữa các môi trường. Do đó, khi điều tra, cần xác định **nguồn đăng ký và điều kiện tạo bean**, không chỉ xác nhận tên bean.

## 3. Kiểm tra bean trong ApplicationContext

`ApplicationContext` vừa là container quản lý bean vừa cung cấp API tra cứu. Khi debug, nên kiểm tra từ phạm vi hẹp đến rộng để tránh vô tình khởi tạo những bean nặng.

### 3.1. Tra cứu theo tên và kiểu

~~~java
import java.util.Arrays;

import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
class BeanInventory {
    private final ApplicationContext context;

    BeanInventory(ApplicationContext context) {
        this.context = context;
    }

    void inspect() {
        System.out.println("inventoryGateway exists: "
                + context.containsBean("inventoryGateway"));

        String[] names = context.getBeanNamesForType(InventoryGateway.class);
        System.out.println("InventoryGateway beans: "
                + Arrays.toString(names));
    }
}
~~~

`containsBean(name)` kiểm tra tên bean trong context và context cha theo quy tắc của container. `getBeanNamesForType(type)` trả về những bean có thể gán cho kiểu được hỏi. Nếu chỉ cần kiểm tra metadata, các API `ListableBeanFactory` và `ConfigurableListableBeanFactory` có các lựa chọn kiểm soát việc khởi tạo eager của `FactoryBean`; hãy chọn overload phù hợp với mục đích và phiên bản Spring.

Lưu ý:

- `getBean(InventoryGateway.class)` yêu cầu lấy đối tượng, nên có thể kích hoạt khởi tạo lazy bean.
- Nếu có nhiều bean cùng kiểu, tra cứu theo kiểu có thể gây `NoUniqueBeanDefinitionException`; kiểm tra tên, `@Primary`, `@Qualifier` và phạm vi context.
- `getBeanNamesForType` không chứng minh dependency của bean đã được inject thành công vào một consumer cụ thể.
- Bean có thể nằm trong context cha; cần xác định đang kiểm tra context nào.

### 3.2. Liệt kê bean definition

Khi cần biết container đã đăng ký những tên nào:

~~~java
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;

void listDefinitions(ConfigurableApplicationContext context) {
    ConfigurableListableBeanFactory factory = context.getBeanFactory();

    for (String name : factory.getBeanDefinitionNames()) {
        var definition = factory.getBeanDefinition(name);
        System.out.printf(
                "%s | class=%s | scope=%s | resource=%s%n",
                name,
                definition.getBeanClassName(),
                definition.getScope(),
                definition.getResourceDescription()
        );
    }
}
~~~

`getBeanClassName()` có thể là `null` nếu bean được tạo qua factory method hoặc class chưa thể suy ra từ definition. Với bean khai báo bằng `@Bean`, hãy xem thêm factory bean name và factory method name. `resourceDescription` giúp định hướng vị trí metadata, nhưng không phải lúc nào cũng chứa đường dẫn nguồn rõ ràng.

Không nên ghi toàn bộ danh sách bean ra log production ở mọi lần khởi động: dữ liệu có thể lớn và làm lộ tên lớp hoặc chi tiết nội bộ. Dùng log tạm trong môi trường kiểm thử hoặc công cụ quản trị có kiểm soát.

### 3.3. Dùng Spring Boot Actuator để quan sát

Nếu ứng dụng đã thêm Actuator, một số endpoint hữu ích là:

| Endpoint ID | Mục đích |
| --- | --- |
| `beans` | Xem bean definitions theo context |
| `conditions` | Xem điều kiện auto-configuration đã match hoặc không match |
| `env` | Quan sát property và các property source trong `Environment` |
| `configprops` | Quan sát bean được bind từ `@ConfigurationProperties` |
| `health` | Kiểm tra tình trạng ứng dụng và health contributor được cấu hình |

Các endpoint chỉ hoạt động khi dependency, điều kiện endpoint, web exposure và quyền truy cập phù hợp. Ví dụ, có thể expose trong môi trường local:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans,conditions,env,configprops
~~~

Đây là ví dụ cho môi trường phát triển. **Không expose hàng loạt endpoint quản trị ra Internet hoặc mạng không tin cậy.** `env` và `configprops` có cơ chế che giá trị nhạy cảm, nhưng việc che không thay thế xác thực, phân quyền và giới hạn mạng. Chỉ mở những endpoint thật sự cần thiết; cân nhắc dùng management port riêng và bảo vệ bằng Spring Security hoặc lớp kiểm soát tương đương.

## 4. Kiểm tra nguồn cấu hình qua Environment

Spring `Environment` cung cấp danh sách `PropertySource`. Khi cùng một key xuất hiện ở nhiều nguồn, thứ tự ưu tiên quyết định giá trị nào được đọc.

### 4.1. PropertySource và giá trị cuối cùng

Ví dụ, `server.port` có thể được đặt trong file YAML, biến môi trường và tham số dòng lệnh. Khi có nhiều giá trị, Spring Boot áp dụng quy tắc ưu tiên của nguồn cấu hình. Thông thường, tham số dòng lệnh có độ ưu tiên cao hơn file cấu hình; file bên ngoài có thể ghi đè file đóng gói trong JAR; file theo profile có thể ghi đè file chung.

Không nên học thuộc một danh sách rút gọn rồi áp dụng cho mọi phiên bản: Spring Boot có nhiều nguồn cấu hình và thứ tự cụ thể được tài liệu hóa theo phiên bản. Khi có nghi vấn, hãy xem `Environment` thực tế và tài liệu Externalized Configuration của đúng phiên bản.

Có thể quan sát các property source bằng code:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

void inspectPropertySources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println("PropertySource: " + source.getName());
    }

    System.out.println("server.port = "
            + environment.getProperty("server.port"));
    System.out.println("spring.application.name = "
            + environment.getProperty("spring.application.name"));
}
~~~

Danh sách thường được duyệt theo thứ tự ưu tiên mà `MutablePropertySources` sử dụng. Đoạn code in tên nguồn và giá trị cuối cùng; nó chưa chỉ ra chính xác nguồn nào đã cung cấp giá trị thắng. Muốn xem nguồn gốc chi tiết, dùng Actuator `env` trong môi trường được bảo vệ hoặc các cơ chế origin tracking mà Spring Boot hỗ trợ.

Không nên dump mọi key/value vào log: có thể làm lộ password, token, connection string hoặc thông tin định danh.

### 4.2. Nguồn cấu hình thường gặp

| Nguồn | Ví dụ | Vai trò |
| --- | --- | --- |
| File cấu hình đóng gói | `classpath:/application.yaml` | Giá trị mặc định đi cùng ứng dụng |
| File bên ngoài | `./application.yaml`, `./config/application.yaml` | Cấu hình theo môi trường triển khai |
| File theo profile | `application-prod.yaml` | Ghi đè hoặc bổ sung cấu hình khi profile `prod` hoạt động |
| Biến môi trường | `SPRING_DATASOURCE_URL` | Đưa cấu hình từ môi trường chạy vào ứng dụng |
| JVM system properties | `-Dserver.port=9090` | Cấu hình khi khởi chạy JVM |
| Tham số dòng lệnh | `--server.port=9091` | Override thuận tiện cho lần chạy |
| Spring Cloud Config | Property từ Config Server | Quản lý cấu hình tập trung theo application/profile/label |
| Test property source | `@TestPropertySource`, `properties` của test | Override cấu hình trong phạm vi kiểm thử |

Thứ tự cụ thể phụ thuộc loại nguồn và cách khai báo. Ví dụ `@TestPropertySource` hoặc `@DynamicPropertySource` trong kiểm thử có quy tắc ưu tiên riêng; không suy luận từ bảng này cho mọi ngữ cảnh.

### 4.3. Kiểm tra profile đang hoạt động

Profile quyết định nhóm bean và file cấu hình nào được kích hoạt. Có thể khai báo profile qua:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Hoặc truyền lúc chạy:

~~~bash
java -jar orders-service.jar --spring.profiles.active=prod
~~~

Kiểm tra profile thực tế:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;

void inspectProfiles(Environment environment) {
    System.out.println("active="
            + Arrays.toString(environment.getActiveProfiles()));
    System.out.println("default="
            + Arrays.toString(environment.getDefaultProfiles()));
}
~~~

Nếu không có active profile, Spring có thể dùng default profile (mặc định thường là `default`). Cần phân biệt **active profiles** với **default profiles**. Ngoài ra, `spring.profiles.include` và profile groups có thể làm phát sinh profile bổ sung; hãy kiểm tra kết quả sau khi Environment được chuẩn bị.

Một lỗi phổ biến là đặt `spring.profiles.active` trong tài liệu cấu hình chỉ được kích hoạt bởi chính profile đó. Cách khai báo profile phải tuân thủ quy tắc Config Data của Spring Boot; không đặt thuộc tính kích hoạt profile ở tài liệu mà nó đang dùng để quyết định kích hoạt chính nó.

### 4.4. File cấu hình ngoài và Config Data

Spring Boot tìm file cấu hình theo các vị trí mặc định và có thể bổ sung hoặc thay thế vị trí bằng các thuộc tính:

- `spring.config.name`: tên cơ sở của file cấu hình.
- `spring.config.location`: xác định vị trí cần tìm và có thể thay thế vị trí mặc định.
- `spring.config.additional-location`: bổ sung vị trí bên cạnh các vị trí mặc định.
- `spring.config.import`: nhập nguồn cấu hình bổ sung, ví dụ Config Server hoặc file khác.

Những thuộc tính điều khiển việc tìm file cần có sẵn đủ sớm, thường qua environment variable, system property hoặc command-line argument. Khi file bên ngoài không được nạp, hãy xác minh working directory, đường dẫn tuyệt đối/tương đối, tên file, profile và cách dùng `location` hay `additional-location`.

## 5. Spring Cloud Config và thời điểm nạp cấu hình

Trong Spring Cloud, cấu hình có thể đến từ Config Server. Ở cách tích hợp Config Data hiện đại, ứng dụng khai báo import:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Cần có **Config Client starter** phù hợp với release train đang dùng. Giá trị `spring.application.name`, profile và label được dùng để yêu cầu bộ cấu hình tương ứng từ server.

### 5.1. `optional:` và bắt buộc kết nối Config Server

- `optional:configserver:...` cho phép ứng dụng tiếp tục trong những trường hợp nguồn import không khả dụng theo chính sách Config Data.
- Bỏ `optional:` thể hiện nguồn cấu hình là bắt buộc; lỗi truy cập có thể khiến ứng dụng khởi động thất bại.
- Cách cấu hình fail-fast/retry có thể khác nhau theo phiên bản và cơ chế bootstrap đang dùng; phải kiểm tra đúng tài liệu release train.

Quyết định optional hay bắt buộc là quyết định vận hành. Nếu ứng dụng cần secret hoặc endpoint bắt buộc từ Config Server, khởi động với giá trị mặc định có thể gây lỗi khó phát hiện hoặc tạo hành vi không an toàn.

### 5.2. Config Data và bootstrap context

Các phiên bản Spring Cloud mới dùng cơ chế Config Data với `spring.config.import` cho Config Client. Những dự án cũ có thể sử dụng **bootstrap context** và dependency/bootstrap configuration tương ứng. Không nên mặc định mọi dự án Spring Cloud đều tạo bootstrap context hoặc mọi thuộc tính `bootstrap.yml` vẫn có cùng hành vi trong cấu hình hiện đại.

Khi nâng cấp, kiểm tra:

1. Release train Spring Cloud tương thích với Spring Boot.
2. Starter Config Client và cơ chế import đang dùng.
3. Profile, application name, label và endpoint Config Server.
4. Có dependency hoặc thiết lập legacy bootstrap nào còn được bật không.
5. Giá trị cấu hình cuối cùng trong `Environment` có đúng như dự kiến không.

### 5.3. Nạp cấu hình ban đầu khác với refresh runtime

Đọc Config Server lúc khởi động không đồng nghĩa ứng dụng sẽ tự nhận mọi thay đổi sau đó. Cần phân biệt:

- **Load:** nạp property source khi chuẩn bị Environment.
- **Refresh:** kích hoạt cập nhật/rebind hoặc tạo lại bean thuộc refresh scope theo cơ chế đã cấu hình.
- **Propagate:** thông báo cho các instance khác, ví dụ qua cơ chế messaging/bus nếu hệ thống triển khai.
- **Observe:** xác minh từng instance đã nhận giá trị mới.

`@RefreshScope` thuộc Spring Cloud Context; nó không tự gọi Config Server định kỳ, không tự broadcast thay đổi tới toàn cụm và không bảo đảm mọi bean đều được refresh.

## 6. Auto-configuration: vì sao bean được tạo hoặc bị bỏ qua?

Spring Boot auto-configuration là tập hợp các cấu hình được đưa vào ứng dụng và chỉ áp dụng khi các điều kiện phù hợp. Đây là cơ chế giúp starter tích hợp thư viện mà người dùng không cần khai báo từng bean.

### 6.1. Các loại điều kiện thường gặp

| Annotation / điều kiện | Ý nghĩa | Ví dụ chẩn đoán |
| --- | --- | --- |
| `@ConditionalOnClass` | Chỉ áp dụng nếu class cần thiết có trên classpath | Thiếu thư viện HTTP client hoặc provider |
| `@ConditionalOnMissingBean` | Chỉ tạo bean mặc định khi chưa có bean phù hợp | Người dùng đã khai báo bean tùy chỉnh |
| `@ConditionalOnBean` | Chỉ áp dụng khi một bean khác tồn tại | Thiếu prerequisite configuration |
| `@ConditionalOnProperty` | Kiểm tra property có giá trị phù hợp | Feature flag chưa bật hoặc sai tên property |
| `@ConditionalOnResource` | Kiểm tra resource có tồn tại | Thiếu file hoặc schema |
| `@ConditionalOnWebApplication` | Kiểm tra loại ứng dụng web | Auto-configuration web không áp dụng cho non-web app |
| `@ConditionalOnNotWebApplication` | Chỉ áp dụng khi không phải web app | Cấu hình dành riêng cho tiến trình batch/CLI |

Một điều kiện có thể phụ thuộc vào nhiều điều kiện khác. Ví dụ một auto-configuration cho discovery có thể yêu cầu implementation class hiện diện, property bật và chưa có bean tùy chỉnh thay thế.

### 6.2. Ví dụ auto-configuration tùy chỉnh

Giả sử một thư viện cung cấp `InventoryClient` khi ứng dụng có một HTTP transport tương thích và property `inventory.client.enabled=true`.

~~~java
@AutoConfiguration
@ConditionalOnClass(InventoryClient.class)
@ConditionalOnProperty(
        prefix = "inventory.client",
        name = "enabled",
        havingValue = "true"
)
public class InventoryClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    InventoryClient inventoryClient(InventoryTransport transport) {
        return new InventoryClient(transport);
    }
}
~~~

Trong ví dụ:

- `@ConditionalOnClass` kiểm tra class có trên classpath.
- `@ConditionalOnProperty` kiểm tra feature flag.
- `@ConditionalOnMissingBean` cho phép ứng dụng tự cung cấp `InventoryClient` riêng.
- `InventoryTransport` vẫn phải có bean phù hợp; nếu thiếu, bean method không thể được tạo thành công.

Với Spring Boot 3, auto-configuration của thư viện thường được đăng ký trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File chứa tên đầy đủ của lớp auto-configuration, mỗi dòng một lớp. Các dự án Boot cũ có thể dùng cơ chế đăng ký khác như `spring.factories`; khi nâng cấp, phải theo đúng hướng dẫn của phiên bản Boot mục tiêu.

### 6.3. Thứ tự auto-configuration

Khi nhiều cấu hình phụ thuộc lẫn nhau, thứ tự có thể ảnh hưởng điều kiện `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`. Các annotation như `@AutoConfigureBefore`, `@AutoConfigureAfter` hoặc thuộc tính `before`/`after` của `@AutoConfiguration` có thể điều khiển thứ tự tương đối.

Tuy nhiên, không nên dựa vào thứ tự để che một dependency thiết kế sai. Nếu một bean tùy chỉnh cần tồn tại trước, hãy khai báo cấu hình và dependency rõ ràng; dùng condition report để xác minh thứ tự và điều kiện thực tế.

## 7. Đọc condition evaluation report

Condition evaluation report là bằng chứng quan trọng khi một tính năng không xuất hiện. Nó cho biết auto-configuration nào match, điều kiện nào không match và lý do được ghi nhận.

### 7.1. Bật debug khi khởi động

Có thể chạy ứng dụng với:

~~~bash
java -jar orders-service.jar --debug
~~~

Hoặc bật logging debug cho nhóm auto-configuration phù hợp theo phiên bản. Spring Boot in **Condition Evaluation Report** với các nhóm điều kiện match và không match. Hãy tìm tên auto-configuration liên quan tới tính năng cần điều tra, ví dụ Config Client, LoadBalancer hoặc một provider discovery.

Một dòng “did not match” thường có mô tả như class không có, property không được đặt hoặc bean prerequisite không tồn tại. Đọc lý do cụ thể trước khi thêm dependency hay thay cấu hình.

### 7.2. Dùng Actuator `conditions`

Nếu có Actuator và endpoint được expose/bảo vệ đúng cách, có thể gọi:

~~~http
GET /actuator/conditions
~~~

Endpoint này trả về thông tin condition evaluation theo context. Nó hữu ích khi so sánh local, staging và production: cùng một auto-configuration có thể match ở local nhưng không match ở production vì classpath hoặc property khác nhau.

Endpoint `conditions` phục vụ chẩn đoán; không nên expose công khai. Có thể thay bằng debug log trong môi trường kiểm thử nếu không muốn mở endpoint quản trị.

### 7.3. Phân loại nguyên nhân theo bằng chứng

| Bằng chứng trong report | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `@ConditionalOnClass` không match | Thiếu JAR hoặc version không có class đó | Kiểm tra runtime dependency tree và BOM |
| `@ConditionalOnProperty` không match | Key sai, value khác, profile chưa active | Kiểm tra `Environment`, property source và profile |
| `@ConditionalOnMissingBean` không match | Đã có bean tùy chỉnh hoặc bean từ cấu hình khác | Tìm bean hiện có, xác định có chủ ý override không |
| `@ConditionalOnBean` không match | Thiếu bean prerequisite | Kiểm tra auto-configuration tạo bean đó và điều kiện của nó |
| Configuration bị exclude | Bị loại trừ qua annotation hoặc property | Kiểm tra `exclude`, `excludeName`, `spring.autoconfigure.exclude` |
| Auto-configuration không xuất hiện trong report | Không được import, không có metadata phù hợp hoặc không thuộc phiên bản đang dùng | Kiểm tra starter, file imports và phiên bản Boot |

Điều kiện không match không luôn là lỗi. Một auto-configuration mặc định có thể chủ động nhường chỗ cho bean do ứng dụng cung cấp. Hãy đánh giá so với mục tiêu ứng dụng thay vì cố làm mọi điều kiện đều match.

## 8. Chẩn đoán theo tình huống thực tế

### 8.1. Thiếu `DiscoveryClient`

Ứng dụng Spring Cloud cần tra cứu `inventory-service`, nhưng inject `DiscoveryClient` thất bại hoặc không có implementation mong muốn.

Kiểm tra theo thứ tự:

1. **Class và bean:** `DiscoveryClient` API có trong runtime classpath không? Có bean nào thuộc kiểu này không?
2. **Provider:** đã thêm starter discovery phù hợp, ví dụ Eureka Client, hay đang chủ ý dùng `SimpleDiscoveryClient`?
3. **Auto-configuration:** condition report cho biết cấu hình provider match hay bị bỏ qua?
4. **Property:** application name, registry URL, profile và thuộc tính discovery có đúng không?
5. **Runtime:** provider có kết nối được registry và trả về instance hay không?

`spring-cloud-commons` cung cấp abstraction chung, nhưng không tự cung cấp mọi registry implementation. Có bean `DiscoveryClient` cũng chưa chứng minh registry bên ngoài đã kết nối thành công; có thể đó là simple/static discovery hoặc một implementation khác.

### 8.2. Giá trị timeout không đúng như cấu hình

Giả sử file `application-prod.yaml` đặt timeout 400 ms nhưng runtime vẫn đọc 1.000 ms. Các bước:

- Xác nhận `prod` có nằm trong active profiles.
- Kiểm tra file có ở đúng location và tên đúng không.
- Kiểm tra biến môi trường, system property, tham số command line hoặc Config Server có ghi đè không.
- Xem property source và giá trị cuối cùng qua `Environment`/Actuator.
- Kiểm tra bean client có được tạo trước khi giá trị mới xuất hiện hoặc có giữ cấu hình cũ trong object đã khởi tạo không.

Nếu bean client lưu timeout trong constructor, thay đổi property trong Environment không nhất thiết thay đổi instance đang chạy. Cần thiết kế lifecycle/refresh rõ ràng.

### 8.3. Bean tồn tại local nhưng không tồn tại production

So sánh các khác biệt có thể kiểm chứng:

- Runtime dependency tree và artifact versions.
- Active profiles, environment variables và Config Data locations.
- Auto-configuration exclusions.
- Conditional properties và classpath.
- Component scan base package, `@Import` và cấu hình được kích hoạt.
- Sự khác biệt giữa web application và non-web application.
- Bean tùy chỉnh, `@Primary`, `@Qualifier` và context hierarchy.

Không nên khắc phục bằng cách thêm `@Component` hoặc khai báo bean trùng lặp trước khi hiểu vì sao cấu hình ban đầu không được áp dụng. Làm vậy có thể che nguyên nhân và tạo xung đột khi môi trường khác khởi động.

### 8.4. Config Server có cấu hình nhưng ứng dụng không nhận

Kiểm tra `spring.config.import`, Config Client starter, Config Server URL, application name, profile và label. Sau đó kiểm tra log Config Data lúc khởi động, property source trong Environment và chính sách optional/fail-fast.

Nếu cấu hình xuất hiện ở một instance nhưng không xuất hiện ở instance khác, so sánh thời điểm khởi động, profile, phiên bản ứng dụng, label và cơ chế refresh/propagation. Không suy luận rằng server có dữ liệu nghĩa là mọi client đã nhận cùng dữ liệu.

## 9. Kiểm thử bean và auto-configuration

Kiểm thử khởi tạo giúp xác nhận một điều kiện cụ thể mà không cần khởi động toàn bộ hệ thống phụ thuộc bên ngoài.

### 9.1. ApplicationContextRunner

Spring Boot cung cấp `ApplicationContextRunner` để chạy một context nhỏ với cấu hình và property được chỉ định. Ví dụ minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryClientAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            InventoryClientAutoConfiguration.class
                    ))
                    .withBean(InventoryTransport.class,
                            () -> request -> "ok");

    @Test
    void createsClientWhenEnabled() {
        runner.withPropertyValues("inventory.client.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(InventoryClient.class);
                });
    }

    @Test
    void backsOffWhenDisabled() {
        runner.withPropertyValues("inventory.client.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(InventoryClient.class);
                });
    }
}
~~~

Đây là ví dụ kiểm thử cho auto-configuration giả định trong bài. `InventoryTransport` và constructor của `InventoryClient` là API ví dụ của ứng dụng, không phải lớp Spring có sẵn.

Ưu điểm của `ApplicationContextRunner`:

- Chạy context nhỏ, không cần web server.
- Thay đổi property dễ dàng giữa các trường hợp.
- Có thể đăng ký bean prerequisite hoặc bean tùy chỉnh.
- Kiểm tra được auto-configuration tạo bean, back-off hoặc thất bại vì thiếu điều kiện.

### 9.2. Kiểm tra nguồn cấu hình

Với cấu hình dùng `@ConfigurationProperties`, nên kiểm tra cả binding lẫn giá trị mong muốn:

~~~java
@ConfigurationProperties(prefix = "inventory.client")
public record InventoryClientProperties(
        boolean enabled,
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

Test có thể tạo context với các property khác nhau và xác nhận giá trị được bind. Khi có nhiều property source, hãy thêm từng nguồn trong test để chứng minh nguồn có ưu tiên cao hơn thực sự ghi đè nguồn thấp hơn.

### 9.3. Khi nào cần integration test?

`ApplicationContextRunner` không thay thế mọi integration test. Cần kiểm thử tích hợp khi hành vi phụ thuộc vào:

- Config Server thật hoặc container mô phỏng.
- Eureka/Consul hoặc discovery provider.
- Network, HTTP client và service registry.
- Spring Security bảo vệ management endpoints.
- Refresh event, messaging/bus hoặc lifecycle bean.
- Cách ứng dụng đóng gói và chạy trong môi trường production-like.

Tách kiểm thử **điều kiện tạo bean** khỏi kiểm thử **khả năng kết nối dependency** để lỗi có nguyên nhân rõ ràng.

## 10. Checklist vận hành và bảo mật

Khi một ứng dụng Spring Cloud khởi động trong production, cần quan sát các tín hiệu có thể giúp xác định trạng thái:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Startup log | Context đã refresh thành công? Có warning về config import hoặc condition nào quan trọng? |
| Condition report | Auto-configuration mong đợi có match không? Vì sao bị bỏ qua? |
| Bean inventory | Bean quan trọng có tồn tại trong context đúng không? |
| Active profiles | Instance đang chạy profile nào? |
| Property source | Giá trị cuối cùng đến từ nguồn nào? Có bị override ngoài dự kiến không? |
| Config Client log | Server, application name, profile và label nào đã được dùng? |
| Discovery/registry health | Client đã đăng ký/tra cứu thành công chưa? |
| Readiness | Ứng dụng có đủ khả năng phục vụ request hay chỉ mới sống? |

Một số nguyên tắc:

- Không bật debug/trace toàn bộ framework lâu dài nếu log quá lớn hoặc có thể chứa thông tin nhạy cảm.
- Không expose `/actuator/env`, `/actuator/configprops`, `/actuator/beans` hay `/actuator/conditions` công khai chỉ để tiện debug.
- Bảo vệ management endpoint bằng xác thực, phân quyền và network policy.
- Không log secret, token, mật khẩu hoặc toàn bộ cấu hình đã resolve.
- Tách health của ứng dụng khỏi trạng thái của dependency tùy chọn; một dịch vụ gợi ý không nhất thiết phải làm readiness của toàn bộ API thất bại.
- Dùng cùng cách quan sát ở local/staging/production nhưng điều chỉnh quyền truy cập và mức chi tiết theo môi trường.

## 11. Tương thích phiên bản và các khác biệt cần lưu ý

Spring Boot và Spring Cloud thay đổi cơ chế khởi tạo, metadata auto-configuration và cách nạp cấu hình qua các release. Khi kiểm tra một ví dụ hoặc log từ dự án khác, phải xác định phiên bản trước khi áp dụng.

Một số điểm cần chú ý:

- Spring Boot 3 sử dụng cơ chế đăng ký auto-configuration qua `AutoConfiguration.imports`; thư viện cũ có thể còn dùng metadata `spring.factories` theo thế hệ Boot trước.
- Spring Cloud Config hiện đại hỗ trợ Config Data qua `spring.config.import`; dự án legacy có thể dựa vào bootstrap context.
- API, tên property, điều kiện và endpoint Actuator có thể khác theo phiên bản.
- Chọn Spring Cloud release train tương thích với Spring Boot theo ma trận chính thức, quản lý version qua `spring-cloud-dependencies` BOM và kiểm tra dependency tree sau nâng cấp.
- Không sao chép một cấu hình `bootstrap.yml`, ví dụ auto-configuration hoặc endpoint từ bài viết cũ mà chưa xác nhận nó còn phù hợp với phiên bản đang chạy.

Khi có `NoSuchMethodError`, `ClassNotFoundException` hoặc bean condition bất thường sau nâng cấp, hãy kiểm tra **phiên bản được resolve thực tế**, không chỉ version khai báo trong `pom.xml` hoặc `build.gradle`.

## 12. Bài tập vận dụng

**Bài tập 1 — Bean bị thiếu.** Một controller inject `DiscoveryClient` nhưng ứng dụng báo `NoSuchBeanDefinitionException`. Hãy lập trình tự kiểm tra classpath, provider starter, auto-configuration condition, profile và bean inventory. Giải thích vì sao thêm Commons có thể chưa đủ.

**Bài tập 2 — Property bị ghi đè.** `application-prod.yaml` đặt `inventory.client.read-timeout=400ms`, nhưng Actuator cho thấy giá trị cuối cùng là `1s`. Hãy xác định những nguồn cấu hình cần kiểm tra và cách chứng minh nguồn nào có độ ưu tiên cao hơn.

**Bài tập 3 — Auto-configuration không match.** Condition report cho biết `@ConditionalOnProperty` không match. Hãy đưa ra các nguyên nhân có thể có: sai key, sai value, profile chưa active, property source chưa được nạp hoặc cấu hình bị ghi đè. Viết một `ApplicationContextRunner` test cho cả trường hợp enabled và disabled.

**Bài tập 4 — Config Client.** Một ứng dụng có `spring-cloud-context` nhưng không đọc được cấu hình từ Config Server. Hãy giải thích sự khác nhau giữa Context và Config Client, liệt kê dependency, `spring.config.import` và bằng chứng runtime cần kiểm tra.

**Bài tập 5 — So sánh môi trường.** Bean tồn tại ở local nhưng vắng mặt ở production. Lập bảng so sánh runtime classpath, active profiles, property sources, exclusions và condition report; chỉ ra bằng chứng nào đủ để kết luận nguyên nhân.

## 13. Ghi nhớ và nguồn tra cứu

Khi một tính năng Spring Cloud không hoạt động, đi theo chuỗi kiểm tra:

**Environment → BeanDefinition/bean → auto-configuration conditions → dependency/provider → hành vi runtime.**

- `ApplicationContext` cho biết container đang quản lý những bean nào.
- `Environment` cho biết profile và các nguồn cấu hình; property source ưu tiên cao hơn có thể ghi đè giá trị trong file.
- Condition evaluation report giải thích vì sao auto-configuration được bật hoặc bỏ qua.
- Starter đưa dependency vào classpath, nhưng không tự chứng minh provider đã kết nối hoặc hành vi đã hoạt động.
- Spring Cloud Context hỗ trợ refresh; Config Client đảm nhiệm tích hợp nạp cấu hình từ Config Server. Hai nhiệm vụ này cần được kiểm tra riêng.

Nguồn chính thức để tra cứu theo phiên bản dự án:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot Reference – Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
3. [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
4. [Spring Boot API – ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
5. [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
6. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
7. [Spring Cloud – release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
