# Nạp properties bổ sung bằng @PropertySource và xác định ưu tiên

Trong Spring Boot, cấu hình ứng dụng không chỉ đến từ `application.yml`, `application.properties`, biến môi trường và tham số dòng lệnh. Khi cần bổ sung một tệp `.properties` được quản lý cùng một module hoặc một thư viện, Spring Framework cung cấp annotation **`@PropertySource`** để đăng ký nội dung tệp đó thành một `PropertySource` trong Spring `Environment`.

Tuy nhiên, việc “nạp thêm một tệp” và việc “ghi đè cấu hình hiện có” là hai chuyện khác nhau. `@PropertySource` có **thời điểm xử lý** và **vị trí ưu tiên** riêng. Trong ứng dụng Spring Boot thông thường, nguồn thêm bằng `@PropertySource` có độ ưu tiên **thấp hơn Config Data** như `application.yml` và thấp hơn những nguồn override phổ biến như biến môi trường hay tham số dòng lệnh. Hơn nữa, annotation này được xử lý trong quá trình làm mới ApplicationContext nên **quá muộn** để tác động đáng tin cậy tới một số thiết lập được đọc từ rất sớm, chẳng hạn `logging.*`, `spring.main.*` hoặc cơ chế lựa chọn Config Data/profile.

Bài học giải thích cú pháp `@PropertySource`, vị trí của nó trong hệ thống property sources, cách kiểm tra nguồn thắng, khác biệt với `spring.config.import`, những điều cần lưu ý khi dùng YAML, và cách kiểm thử trong dự án Spring Boot.

## 1. Mô hình: Environment và nhiều PropertySource

Spring `Environment` không chỉ là một map chứa các key/value. Nó có thể chứa **nhiều PropertySource**, mỗi nguồn sở hữu một tập key và được xếp theo thứ tự ưu tiên.

Có thể hình dung:

~~~text
Spring Environment
  |
  +-- PropertySource ưu tiên cao
  |     app.client.timeout = 1s
  |
  +-- PropertySource ưu tiên trung bình
  |     app.client.timeout = 3s
  |
  +-- PropertySource ưu tiên thấp
        app.client.timeout = 5s

getProperty("app.client.timeout")
          |
          v
     chọn 1s, nếu không có nguồn cao hơn can thiệp
~~~

Khi đọc:

~~~java
String timeoutText =
    environment.getProperty("app.client.timeout");
~~~

Spring tìm giá trị có thể dùng được theo thứ tự các nguồn. Với cùng key, giá trị ở nguồn ưu tiên cao thường che giá trị ở nguồn thấp.

Các nguồn có thể bao gồm:

- Properties mặc định do ứng dụng cung cấp.
- Nguồn thêm bằng `@PropertySource`.
- Spring Boot Config Data như `application.properties`, `application.yml` và các bản theo profile.
- Biến môi trường hệ điều hành.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Những nguồn khác do framework hoặc ứng dụng thêm.

Danh sách trên là các loại nguồn, **không phải danh sách đầy đủ mọi mức độ ưu tiên của Spring Boot**. Điều cần giữ trong đầu: thứ tự cuối cùng do Spring Environment và cơ chế bootstrapping thực sự quyết định; không phải đơn giản “file được viết sau luôn thắng”.

## 2. @PropertySource giải quyết nhu cầu nào?

Giả sử module tích hợp tồn kho muốn mang theo một số mặc định của riêng nó:

~~~text
src/main/java/example/inventory/
  InventoryConfiguration.java
  InventoryClient.java

src/main/resources/
  inventory-client-defaults.properties
~~~

Nội dung resource:

~~~properties
inventory.client.enabled=true
inventory.client.timeout=3s
inventory.client.max-retries=2
inventory.client.user-agent=order-service
~~~

Muốn Spring Environment nhìn thấy các property này khi module cấu hình được nạp, viết:

~~~java
package example.inventory;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
public class InventoryConfiguration {
}
~~~

Khi `InventoryConfiguration` là một configuration class thực sự được Spring xử lý, nội dung `inventory-client-defaults.properties` sẽ được đưa vào Environment như một nguồn property.

Từ bean khác:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class InventorySettingsReader {

    private final Environment environment;

    InventorySettingsReader(Environment environment) {
        this.environment = environment;
    }

    String timeout() {
        return environment.getProperty("inventory.client.timeout");
    }
}
~~~

Nếu không có nguồn ưu tiên cao hơn ghi đè, `timeout()` có thể trả chuỗi `"3s"`.

`@PropertySource` phù hợp khi muốn khai báo rõ rằng **module này mang theo một resource properties cụ thể**. Nó không phải cơ chế mặc định tốt nhất cho mọi cấu hình triển khai và không có nghĩa resource được refresh tự động sau khi ứng dụng đã khởi động.

## 3. Annotation nằm ở đâu và khi nào được xử lý?

Một cách viết phổ biến:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:config/inventory.properties")
public class InventoryConfiguration {
}
~~~

Điều kiện cần:

1. Tệp `config/inventory.properties` thực sự có trong classpath của ứng dụng.
2. `InventoryConfiguration` phải được Spring **scan, import hoặc đăng ký** như một configuration class.
3. Spring xử lý annotation trong lúc tạo/làm mới ApplicationContext.
4. Các property được đưa vào Environment sẽ có hiệu lực theo thứ tự PropertySource hiện hành.

Nếu chỉ tạo file `inventory.properties` trong resources nhưng **không khai báo `@PropertySource` hoặc cơ chế import nào khác**, Spring Boot không có nghĩa vụ tự động đọc tệp tùy ý đó.

Nếu class có `@PropertySource` nhưng nằm ngoài component scan và không được import, annotation có thể không bao giờ được xử lý.

Ví dụ import tường minh từ application class:

~~~java
package example;

import example.inventory.InventoryConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(InventoryConfiguration.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Không nên tạo một class `@Configuration` không được context nạp rồi kỳ vọng nguồn properties tự xuất hiện.

## 4. Quan hệ với @ConfigurationProperties

Một trong những mục đích chính của externalized configuration là bind giá trị vào typed object.

Ví dụ:

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory.client")
public record InventoryClientProperties(
        boolean enabled,
        Duration timeout,
        int maxRetries,
        String userAgent
) {}
~~~

Đăng ký kiểu cấu hình:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {
}
~~~

Nội dung properties:

~~~properties
inventory.client.enabled=true
inventory.client.timeout=3s
inventory.client.max-retries=2
inventory.client.user-agent=inventory-module
~~~

Khi context xử lý cấu hình, Spring Boot Binder có thể tìm giá trị từ Environment và bind vào record `InventoryClientProperties` theo các converter thích hợp.

**Phân vai:**

- `@PropertySource`: thêm một nguồn key/value vào Environment.
- `@ConfigurationProperties`: mô tả một nhóm property và kiểu đích Java.
- `@EnableConfigurationProperties`: đăng ký typed configuration bean.
- Binder/ConversionService: chuyển giá trị sang `Duration`, `int`, `boolean`…
- Validation: kiểm tra giá trị có đạt ràng buộc vận hành không, nếu được cấu hình.

Không nhầm annotation nạp file với annotation đăng ký bean. `@PropertySource` không tự biến mọi class `@ConfigurationProperties` thành Spring bean.

## 5. Cú pháp classpath: và file:

`@PropertySource` nhận location của resource. Hai dạng quan trọng:

**Classpath resource:**

~~~java
@PropertySource("classpath:inventory-client-defaults.properties")
~~~

Phù hợp khi file được đóng gói trong `src/main/resources` và đi cùng JAR/module.

**Filesystem resource:**

~~~java
@PropertySource("file:./config/inventory-client.properties")
~~~

Dạng này đọc file ngoài package theo đường dẫn filesystem. Với đường dẫn tương đối, kết quả phụ thuộc **working directory** của tiến trình, không phải nhất thiết thư mục chứa JAR.

Ví dụ:

~~~text
deployment/
  app.jar
  config/
    inventory-client.properties
~~~

Nếu chạy:

~~~bash
cd deployment
java -jar app.jar
~~~

thì `file:./config/inventory-client.properties` có thể trỏ vào file kỳ vọng.

Nhưng nếu một service manager chạy ứng dụng với working directory khác, đường dẫn tương đối có thể không còn đúng.

Quy ước vận hành:

- Classpath resource: dùng cho defaults của module hoặc tài nguyên đi cùng artifact.
- Filesystem resource: dùng khi đường dẫn ngoài artifact được quản lý rõ bởi deployment.
- Những tài liệu Config Data của Spring Boot: thường phù hợp hơn khi muốn đọc file triển khai từ sớm và kiểm soát profile/priority một cách chuẩn.

Đừng đưa secret thật vào resource mặc định được commit hoặc đóng gói chung JAR.

## 6. Khi file thiếu: ignoreResourceNotFound

Mặc định, nếu vị trí được khai báo bằng `@PropertySource` không tồn tại hoặc không thể đọc, quá trình tạo context có thể thất bại.

Ví dụ yêu cầu file phải có:

~~~java
@PropertySource("classpath:required-settings.properties")
~~~

Với resource thật sự tùy chọn:

~~~java
@PropertySource(
    value = "file:./config/local-overrides.properties",
    ignoreResourceNotFound = true
)
~~~

Thuộc tính `ignoreResourceNotFound=true` cho phép bỏ qua một resource **không tìm thấy** trong các trường hợp được Spring hỗ trợ, thay vì bắt buộc mọi máy đều phải có file đó.

Nhưng cần phân biệt:

- **File không tồn tại:** có thể bỏ qua khi được khai báo optional.
- **File có mặt nhưng nội dung sai:** không nên mặc định mọi lỗi parse đều được bỏ qua.
- **File có mặt nhưng permission không hợp lệ:** cần xử lý như sự cố vận hành, không mặc nhiên xem như “cấu hình rỗng”.
- **Property có giá trị sai kiểu:** xảy ra ở giai đoạn binding/conversion, không được `ignoreResourceNotFound` sửa chữa.
- **Bean validation thất bại:** cũng không được annotation này tự tắt.

Nếu ứng dụng cần một key để hoạt động an toàn ở production, không nên tùy tiện dùng `ignoreResourceNotFound=true` rồi để khởi động với mặc định không mong muốn. Cần fail-fast hoặc validation phù hợp.

## 7. Dùng name và encoding

Khi cần một tên nguồn rõ ràng để chẩn đoán hoặc định vị trong `MutablePropertySources`:

~~~java
@PropertySource(
    name = "inventory-client-defaults",
    value = "classpath:inventory-client-defaults.properties"
)
~~~

Tên giúp người đọc hoặc một công cụ chẩn đoán phân biệt nguồn bổ sung với các nguồn khác.

Với nội dung có ký tự Unicode, có thể khai báo encoding:

~~~java
@PropertySource(
    name = "inventory-labels",
    value = "classpath:inventory-labels.properties",
    encoding = "UTF-8"
)
~~~

Resource:

~~~properties
inventory.label.display-name=Kho hàng phía Nam
inventory.label.status-name=Đang hoạt động
~~~

Việc đặt encoding tường minh giúp tránh phụ thuộc vào mặc định đọc file của các nền tảng/phiên bản framework khác nhau.

**Lưu ý:** không nhầm encoding của file cấu hình với charset của request HTTP hay encoding của source code Java. Chúng là những khâu riêng.

## 8. Nạp nhiều tệp với một @PropertySource

Annotation có thể nhận một mảng resource locations:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource({
    "classpath:inventory-common.properties",
    "classpath:inventory-advanced.properties"
})
class InventoryConfiguration {
}
~~~

Giả sử:

~~~properties
# inventory-common.properties
inventory.timeout=3s
inventory.max-retries=2
~~~

~~~properties
# inventory-advanced.properties
inventory.timeout=5s
inventory.enabled=true
~~~

Khi Spring xử lý nhiều resource trong cùng annotation theo thứ tự được khai báo, resource sau có thể ghi đè cùng key của resource trước theo quy tắc xử lý của `@PropertySource`. Trong ví dụ này, giá trị timeout từ `inventory-advanced.properties` có thể thắng giá trị ở common **ở cấp các nguồn @PropertySource được xét với nhau**.

Tuy nhiên, phải tách hai lớp ưu tiên:

1. **Giữa những resource được `@PropertySource` thêm**: thứ tự xử lý có thể ảnh hưởng key trùng.
2. **Giữa @PropertySource và những nguồn khác của Spring Boot**: Config Data, environment, command line vẫn có vị trí ưu tiên riêng; chúng có thể tiếp tục ghi đè giá trị của cả hai resource.

Không nên chỉ vì file thứ hai thắng file thứ nhất mà kết luận nó thắng `application.yml`.

## 9. Nhiều @PropertySource hoặc @PropertySources

Có thể khai báo nhiều annotation:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-defaults.properties")
@PropertySource("classpath:inventory-feature.properties")
class InventoryConfiguration {
}
~~~

Hoặc nhóm bằng `@PropertySources`:

~~~java
import org.springframework.context.annotation.PropertySource;
import org.springframework.context.annotation.PropertySources;

@Configuration(proxyBeanMethods = false)
@PropertySources({
    @PropertySource("classpath:inventory-defaults.properties"),
    @PropertySource("classpath:inventory-feature.properties")
})
class InventoryConfiguration {
}
~~~

Trong một configuration class có thứ tự xử lý rõ, resource được xử lý sau có thể có ưu tiên cao hơn với key trùng nhau theo các quy tắc tương ứng.

Nhưng khi các annotation nằm ở **nhiều configuration classes khác nhau** được Spring nhận diện qua nhiều đường scan/import, thứ tự xử lý có thể không rõ và có thể phụ thuộc registration order. Không nên thiết kế một hợp đồng production dựa vào sự cạnh tranh key của các class mà thứ tự nạp không được xác định chính thức.

Nếu cần override có chủ đích và dễ kiểm chứng, nên tạo một chiến lược rõ:

- Một module sở hữu một prefix cụ thể.
- Mỗi nguồn chứa defaults riêng.
- Deployment sử dụng Config Data, environment hoặc CLI để ghi đè.
- Có test chỉ ra giá trị hiệu lực khi trùng key.

## 10. @PropertySource nằm ở đâu trong thứ tự ưu tiên Spring Boot?

Trong **Spring Boot thông thường**, các nguồn cấu hình được cân nhắc theo một thứ tự ưu tiên có quy định. Trong chuỗi liên quan đến bài này, theo hướng từ **thấp đến cao**:

~~~text
SpringApplication defaultProperties
          |
          v
@PropertySource trên @Configuration
          |
          v
Config Data: application.yml, application.properties,
             profile-specific documents, config imports...
          |
          v
Các nguồn ưu tiên cao hơn theo quy tắc Spring Boot:
random.*, OS environment, Java system properties,
SPRING_APPLICATION_JSON, command-line arguments, v.v.
~~~

Sơ đồ không liệt kê toàn bộ nguồn test, servlet/JNDI hay các nguồn tùy biến. Nó nhấn mạnh: **@PropertySource không phải một “override cuối cùng” của application.yml**.

Một bảng thực hành:

| Nguồn | `inventory.client.timeout` |
| --- | --- |
| `@PropertySource`: `inventory-client-defaults.properties` | `3s` |
| `application.yml` | `5s` |
| Biến môi trường triển khai phù hợp | `2s` |
| Command line `--inventory.client.timeout=1s` | `1s` |

Nếu tất cả nguồn trên đều hợp lệ và xuất hiện trong cách Spring Boot chuẩn xử lý, giá trị hiệu lực sẽ là `1s` từ command line.

Nếu bỏ command line, có thể còn `2s` từ environment. Nếu bỏ cả environment, `5s` từ `application.yml` có thể thắng `3s` từ `@PropertySource`.

Không phải vì `@PropertySource` được viết trong mã Java nên nó tự có ưu tiên hơn file Boot config.

## 11. Một phép thử quan trọng: application.yml thắng @PropertySource

File defaults của module:

~~~properties
# inventory-client-defaults.properties
inventory.client.timeout=3s
inventory.client.max-retries=2
~~~

File chung của ứng dụng:

~~~yaml
# application.yml
inventory:
  client:
    timeout: 7s
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {}
~~~

Khi không có nguồn ưu tiên cao hơn, kết quả kỳ vọng:

~~~text
inventory.client.timeout     = 7s
inventory.client.max-retries = 2
~~~

Giải thích:

- Timeout có ở cả hai nguồn: `application.yml` thắng.
- Max retries chỉ có ở file mặc định của module: `@PropertySource` đóng vai trò fallback.
- Hai key độc lập; việc một key bị override không xóa toàn bộ nội dung của resource properties còn lại.

Đây là pattern tốt cho thư viện muốn cung cấp **mặc định có thể được ứng dụng ghi đè** mà không cần sửa JAR của thư viện.

## 12. @PropertySource và SpringApplication defaultProperties

Spring Boot còn cho phép cung cấp default properties từ code:

~~~java
public static void main(String[] args) {
    SpringApplication application =
        new SpringApplication(Application.class);

    application.setDefaultProperties(
        java.util.Map.of(
            "inventory.client.timeout", "10s"
        )
    );

    application.run(args);
}
~~~

Những default này là một trong các nguồn **ưu tiên thấp** của Spring Boot.

Nếu module bổ sung:

~~~properties
inventory.client.timeout=3s
~~~

qua `@PropertySource`, và không có Config Data/environment/CLI khác ghi đè, `3s` có thể thắng `10s` từ defaultProperties.

Vì vậy không nên gọi tất cả “mặc định” là một mức duy nhất:

- Default properties của SpringApplication.
- Resource module được thêm bằng `@PropertySource`.
- DefaultValue trên constructor của typed configuration.
- Giá trị trong `application.yml`.

Chúng có cơ chế và thời điểm riêng. Việc dự đoán đúng giá trị cuối cùng cần xác định chính xác **nguồn** chứ không chỉ xem giá trị có được gọi là default hay không.

## 13. Thời điểm xử lý: @PropertySource đến khá muộn

Spring Boot không đợi tới khi tất cả `@Configuration` được xử lý mới đưa ra mọi quyết định khởi động. Một số hệ thống cần giá trị **trước khi ApplicationContext refresh**.

Tài liệu Spring Boot lưu ý rõ rằng các `@PropertySource` được thêm vào Environment trong khi context đang làm mới. Vì vậy chúng có thể quá muộn với những thiết lập như:

- `logging.*`: logging system thường được cấu hình rất sớm.
- `spring.main.*`: nhiều thuộc tính điều khiển cấu hình ban đầu của `SpringApplication`.
- Các quyết định sớm về Config Data và profile: không nên dựa vào `@PropertySource` để chọn nguồn `application-prod.yml` hoặc quyết định `spring.config.import` được xử lý ở bước trước.

Ví dụ **không nên làm**:

~~~properties
# early-settings.properties
logging.level.root=DEBUG
spring.main.banner-mode=off
spring.profiles.active=prod
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:early-settings.properties")
class EarlySettingsConfiguration {}
~~~

Người viết có thể mong cả ba thiết lập luôn có hiệu lực từ lúc SpringApplication bắt đầu khởi động. Nhưng việc thêm nguồn ở giai đoạn context refresh **không đảm bảo** các thành phần đã khởi tạo trước đó được cấu hình lại.

Nếu cần các giá trị ảnh hưởng bootstrap, hãy cấp chúng từ nguồn mà Spring Boot đọc từ sớm, như tham số dòng lệnh, environment variables, Java system properties hoặc Config Data theo khả năng hỗ trợ của từng property.

**Không nên sử dụng @PropertySource để giải quyết một bài toán bootstrap mà nó không được thiết kế để giải quyết.**

## 14. Vì sao không nên đặt spring.profiles.active ở @PropertySource?

Giả sử dự án có:

~~~text
application.yml
application-prod.yml
prod-selector.properties
~~~

Tệp:

~~~properties
# prod-selector.properties
spring.profiles.active=prod
~~~

Class:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:prod-selector.properties")
class ProdSelectorConfiguration {}
~~~

Nếu người viết mong Spring Boot đọc `prod-selector.properties` rồi tự nạp `application-prod.yml` trong cùng một vòng bootstrap, thiết kế này không đáng tin cậy. Cơ chế chọn Config Data và kích hoạt tài liệu theo profile đã xảy ra trước giai đoạn xử lý `@PropertySource`.

Chọn profile tại deployment:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Hoặc:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
~~~

Khi đó Spring Boot biết profile cần dùng ngay từ sớm, nạp những tài liệu thích hợp và sau đó mới hoàn thiện context.

Nếu một module thật sự cần một số bean chỉ có ở production, `@Profile("prod")` trên configuration class có thể là cơ chế tạo bean có điều kiện. Nhưng **@Profile không làm @PropertySource trở thành nguồn bootstrap sớm**; điều kiện profile vẫn cần được xác định đúng ở bước trước.

## 15. Không hỗ trợ YAML trực tiếp theo mặc định

Một hiểu nhầm rất thường gặp là:

~~~java
@PropertySource("classpath:integration.yml")
~~~

Spring Framework `@PropertySource` với factory mặc định được thiết kế để nạp các resource theo các định dạng được `ResourcePropertySource`/PropertiesLoader hỗ trợ, chủ yếu là `.properties`; nó **không có hỗ trợ YAML tương đương Config Data của Spring Boot theo mặc định**.

Vì vậy đừng giả định tệp:

~~~yaml
integration:
  timeout: 3s
~~~

sẽ được flatten thành `integration.timeout` khi chỉ gắn `@PropertySource("classpath:integration.yml")`.

Các lựa chọn phù hợp:

1. **Ưu tiên Config Data của Spring Boot** khi cần nạp YAML.
2. Dùng `spring.config.import` hoặc `spring.config.additional-location` theo nhu cầu triển khai.
3. Nếu thực sự phải dùng `@PropertySource`, viết custom `PropertySourceFactory` có khả năng đọc YAML và xử lý tài liệu đa đoạn, rồi chỉ định bằng thuộc tính `factory`. Cách này yêu cầu code và kiểm thử riêng.

Với đa số ứng dụng Spring Boot, **không cần tự viết YAML factory** chỉ để đưa một file YAML phụ vào Environment.

## 16. Dùng spring.config.import cho YAML và Config Data

Một ví dụ trong `application.yml`:

~~~yaml
spring:
  config:
    import: "classpath:integration-defaults.yml"

integration:
  enabled: true
~~~

Tệp bổ sung:

~~~yaml
# integration-defaults.yml
integration:
  timeout: 3s
  max-retries: 2
~~~

Spring Boot Config Data có hỗ trợ YAML, tài liệu đa đoạn và các cơ chế kích hoạt profile tương ứng với quy tắc của nó.

Một khác biệt rất quan trọng là **vị trí ưu tiên**: tài liệu được import qua Config Data là một phần của hệ thống Config Data, không được xếp mặc nhiên vào mức ưu tiên thấp của `@PropertySource`. Trong cơ chế Config Data, tài liệu import có thể được đặt ở vị trí ưu tiên **cao hơn tài liệu khai báo import**, theo quy tắc xử lý import của Spring Boot.

Không được máy móc thay:

~~~java
@PropertySource("classpath:integration-defaults.properties")
~~~

bằng:

~~~yaml
spring:
  config:
    import: "classpath:integration-defaults.properties"
~~~

mà không xét **thay đổi về precedence**. Nếu trước đây file chỉ cung cấp defaults dưới `application.yml`, cách import mới có thể khiến key từ file bổ sung thắng key của tài liệu import nếu chúng trùng nhau.

Khi chuyển cơ chế nạp, cần test với các trường hợp key trùng để đảm bảo giá trị hiệu lực vẫn đúng ý định.

## 17. Khi nào dùng spring.config.additional-location?

Nếu mục tiêu là **bổ sung thư mục hoặc file cấu hình ngoài artifact** cho deployment, Spring Boot còn có property:

~~~text
spring.config.additional-location
~~~

Ví dụ ở command line:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deployment-config/
~~~

Cấu hình này được Boot dùng trong giai đoạn tìm/nạp Config Data. Nó phù hợp khi muốn mở rộng các vị trí đọc `application.properties`/`application.yml` mà không thêm một class `@Configuration` chỉ để nạp file.

Phân biệt:

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Module Java có một file defaults `.properties` riêng | `@PropertySource` |
| Import thêm YAML/properties theo ngữ nghĩa Config Data | `spring.config.import` |
| Bổ sung vị trí tìm Config Data khi deploy | `spring.config.additional-location` |
| Đưa giá trị theo môi trường mà không đổi artifact | OS environment, command line, secret/config service |
| Cần thay đổi nguồn cấu hình trước khi context refresh | Cơ chế bootstrap/EnvironmentPostProcessor phù hợp |
| Chỉ muốn bind các key đã tồn tại sang Java | `@ConfigurationProperties` |

Không phải mọi dự án đều cần đủ những cơ chế này. Chọn một mô hình đơn giản, nhất quán với cách triển khai.

## 18. Placeholder trong @PropertySource location

Resource location có thể dùng placeholder được giải quyết từ những property **đã có trong Environment khi location được xử lý**.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "classpath:defaults/${integration.defaults-file:client.properties}"
)
class IntegrationConfiguration {}
~~~

Nếu `integration.defaults-file` đã có từ một nguồn đủ sớm, location có thể trỏ tới resource được chọn. Phần sau dấu `:` trong placeholder là fallback khi key không được tìm thấy trong ngữ cảnh đó.

Các giới hạn cần hiểu:

- Placeholder ở **đường dẫn resource**, không phải một parser thông minh của mọi nội dung file.
- Độ ưu tiên/khả năng nhìn thấy của placeholder phụ thuộc Environment ở thời điểm annotation được xử lý.
- Không nên tạo vòng phụ thuộc: file chưa được nạp không thể tự quyết định đường dẫn của chính nó bằng một property chỉ có trong file ấy.
- Nếu location sai, resource có thể không tìm thấy; `ignoreResourceNotFound` có thể giúp với resource tùy chọn, nhưng không thay mọi lỗi thành cấu hình hợp lệ.
- Một value được dùng để chọn file external nên được kiểm soát; không tùy tiện cho input người dùng ở runtime quyết định đường dẫn filesystem.

Đây là lựa chọn khi một module cần chọn tệp defaults có tên rõ. Với Config Data/profiles của cả ứng dụng, cơ chế Boot sẵn có thường nhất quán hơn.

## 19. @PropertySource với @Profile

Nếu resource chỉ cần nạp trong một môi trường:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@Profile("local")
@PropertySource("classpath:inventory-local-defaults.properties")
class LocalInventoryDefaultsConfiguration {}
~~~

Khi `local` active và configuration class được đưa vào context, Spring có thể xử lý thêm property resource đó.

Nhưng phải hiểu:

- `@Profile("local")` chọn **configuration class có điều kiện**.
- `@PropertySource` bổ sung resource khi class đó được xử lý.
- Profile `local` phải đã được xác định từ cơ chế phù hợp ở thời điểm context khởi động.
- Resource vẫn có precedence của `@PropertySource`; nó không đột nhiên được ưu tiên hơn `application-local.yml`.
- Nếu nhiều configuration classes có @PropertySource và điều kiện khác nhau, việc xác định thứ tự cần được thiết kế và kiểm thử.

Nếu mục tiêu chỉ là một giá trị khác theo môi trường, thường đơn giản hơn khi đặt trong `application-local.yml` hoặc externalized configuration của deployment.

## 20. Đọc giá trị sau khi thêm PropertySource

Sau khi context đã khởi tạo, bean có thể lấy từ `Environment`:

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
class InventorySyncService {

    private final Duration timeout;
    private final int maxRetries;

    InventorySyncService(Environment environment) {
        this.timeout = environment.getProperty(
            "inventory.client.timeout",
            Duration.class,
            Duration.ofSeconds(3)
        );

        this.maxRetries = environment.getProperty(
            "inventory.client.max-retries",
            Integer.class,
            2
        );
    }
}
~~~

Điểm cần chú ý:

- `Environment#getProperty(key)` có thể trả String hoặc null nếu không có giá trị.
- Overload có `Class<T>` cho phép yêu cầu conversion sang kiểu đích.
- Overload có default giúp xử lý key thiếu.
- Dữ liệu có mặt nhưng sai kiểu có thể gây conversion error; default không mặc định nuốt lỗi.
- Việc biến được gán trong constructor không có nghĩa nó tự đổi khi file nguồn thay đổi về sau.

Nếu nhóm property có nhiều field, dùng `@ConfigurationProperties` để quản lý rõ prefix, kiểu, validation và default thay vì rải key string trong nhiều service.

## 21. Làm sao biết nguồn nào thật sự thắng?

Một ứng dụng có:

~~~properties
# inventory-client-defaults.properties
inventory.client.timeout=3s
~~~

~~~yaml
# application.yml
inventory:
  client:
    timeout: 5s
~~~

Khi truy vấn:

~~~java
environment.getProperty("inventory.client.timeout")
~~~

kết quả có thể là `"5s"`. Nhưng để giải thích nguồn nào thắng, cần nhìn danh sách `PropertySource`.

Một cách chẩn đoán **chỉ với key không nhạy cảm**:

~~~java
package example.debug;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration(proxyBeanMethods = false)
class PropertySourceInspectionConfiguration {

    @Bean
    ApplicationRunner inspectSources(
            ConfigurableEnvironment environment) {
        return args -> {
            String key = "inventory.client.timeout";

            for (PropertySource<?> source :
                    environment.getPropertySources()) {
                Object value = source.getProperty(key);
                if (value != null) {
                    System.out.println(
                        "Source with key: " + source.getName());
                }
            }
        };
    }
}
~~~

Code này liệt kê các nguồn có cung cấp **giá trị khác null** cho key, không in giá trị. Thứ tự duyệt `getPropertySources()` thể hiện thứ tự đang được Environment sử dụng tại thời điểm ấy; nguồn phù hợp đầu tiên có thể là nguồn thắng trong cách phân giải thông thường.

**Cảnh báo:**

- Tên của một PropertySource có thể chứa đường dẫn hoặc chi tiết triển khai; tránh log rộng rãi nếu không cần.
- Không duyệt rồi in tất cả key/value vì dễ lộ credential, token hoặc dữ liệu nhạy cảm.
- Một số nguồn có thể được Spring xử lý đặc biệt, chẳng hạn placeholder, alias tên environment variable hoặc composite sources.
- Code kiểm tra ở giai đoạn `ApplicationRunner` cho biết Environment **sau khi context được tạo**, không thể chứng minh những giá trị có hiệu lực từ đầu quá trình bootstrap.

Với mục tiêu kiểm tra thứ tự, nên sử dụng test hoặc công cụ debug nội bộ, không để nguyên một bộ dump cấu hình trong production.

## 22. ConfigurableEnvironment và MutablePropertySources

Nếu cần truy cập trực tiếp thứ tự nguồn, Spring cung cấp:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;

MutablePropertySources sources =
    environment.getPropertySources();
~~~

`MutablePropertySources` có những thao tác như `addFirst`, `addLast`, `addBefore` và `addAfter` để thêm nguồn ở vị trí xác định. Ví dụ minh họa trên một môi trường tùy biến:

~~~java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

MapPropertySource overrides = new MapPropertySource(
    "integration-overrides",
    Map.of("integration.timeout", "1s")
);

environment.getPropertySources().addFirst(overrides);
~~~

`addFirst` đưa nguồn mới vào đầu danh sách, vì vậy nó có thể có ưu tiên cao khi phân giải key.

**Không nên coi code này là khuyến nghị thêm nguồn tùy ý vào ApplicationRunner**: khi ApplicationRunner chạy, nhiều bean và hệ thống đã được khởi tạo, một số giá trị có thể đã được bind/đọc trước đó. Thay đổi Environment muộn không tự tái tạo những bean ấy hoặc tái cấu hình hệ thống logging.

Nếu yêu cầu thật sự là **định nghĩa một nguồn ưu tiên tùy chỉnh trong bootstrap**, hãy dùng lifecycle extension phù hợp của Spring Boot, thay vì thêm nguồn muộn rồi đoán các bean đã cập nhật.

## 23. Khi nào cần EnvironmentPostProcessor?

`EnvironmentPostProcessor` là cơ chế mở rộng Spring Boot để thay đổi `Environment` trong giai đoạn chuẩn bị trước khi ApplicationContext hoàn thiện. Nó phù hợp khi cần:

- Nạp nguồn cấu hình đặc biệt không thuộc Config Data mặc định.
- Thêm defaults hoặc overrides trước khi nhiều bean được tạo.
- Xác định một vị trí ưu tiên rõ ràng bằng `MutablePropertySources`.
- Tích hợp một config service hoặc một định dạng nguồn đặc thù theo lifecycle được hỗ trợ.

Tuy nhiên, đây là cơ chế **mạnh hơn và phức tạp hơn** `@PropertySource`; cần hiểu đăng ký extension theo phiên bản Spring Boot, các giai đoạn lifecycle, độ ưu tiên giữa processors, khả năng truy cập tài nguyên và test.

Ví dụ ý tưởng bên trong processor:

~~~java
import java.util.Map;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public void addDefaults(ConfigurableEnvironment env) {
    env.getPropertySources().addLast(
        new MapPropertySource(
            "warehouse-module-defaults",
            Map.of("warehouse.timeout", "3s")
        )
    );
}
~~~

Đoạn trên **chỉ minh họa thao tác thêm nguồn**, không phải một `EnvironmentPostProcessor` hoàn chỉnh có registration. Trong production cần thực thi đúng extension point và đặt vị trí có chủ đích.

Nếu chỉ cần một vài property default từ file `.properties`, `@PropertySource` vẫn đơn giản hơn. Nếu yêu cầu là YAML profile-specific hoặc deployment config, ưu tiên cơ chế Config Data sẵn có trước khi tạo processor tùy chỉnh.

## 24. @PropertySource không tự reload file

Nếu khai báo:

~~~java
@PropertySource("file:./config/inventory-client.properties")
~~~

thì file được đọc trong quá trình context xử lý cấu hình. Khi một người sửa file trên đĩa sau startup, Spring Boot không tự cam kết:

- đọc lại file,
- thay PropertySource bằng nội dung mới,
- rebind mọi `@ConfigurationProperties`,
- hoặc tái tạo bean đã nhận giá trị trong constructor.

Muốn **dynamic refresh**, cần một cơ chế quản lý vòng đời và cập nhật cấu hình riêng (có thể liên quan Spring Cloud, event, reload logic hoặc restart có kiểm soát).

Không nên chọn `@PropertySource` chỉ vì nghĩ rằng “resource trên filesystem” đồng nghĩa “thay đổi live”. Đó là hai vấn đề khác nhau.

Với triển khai immutable artifact/containers, phương án đơn giản thường là cập nhật config và **restart/rollout** ứng dụng theo quy trình CI/CD.

## 25. Cấu hình trùng key và một chính sách sở hữu rõ

Giả sử có hai module:

~~~text
payments-defaults.properties:
  http.timeout=2s

inventory-defaults.properties:
  http.timeout=5s
~~~

Nếu hai module cùng đưa một key quá chung như `http.timeout` vào Environment, giá trị hiệu lực có thể phụ thuộc thứ tự nạp configuration classes. Đây là thiết kế dễ gây xung đột.

Thay vì dùng key chung, nên đặt namespace rõ:

~~~properties
payment.client.timeout=2s
inventory.client.timeout=5s
~~~

Các module có thể nạp file defaults độc lập mà không tranh một key.

Nguyên tắc:

1. Mỗi module sở hữu một prefix rõ ràng.
2. File resource nội bộ chủ yếu cung cấp defaults.
3. Ứng dụng/deployment được phép override qua nguồn chuẩn của Spring Boot.
4. Không cho các module tranh một key rồi dựa vào thứ tự scan để quyết định thắng.
5. Nếu thật sự cần shared key, hãy công bố nguồn sở hữu và cơ chế override được hỗ trợ.

Một thiết kế tốt có thể giải thích thứ tự ưu tiên **mà không phải dựa vào tình cờ class nào được scan trước**.

## 26. @PropertySource và biến môi trường

Tệp:

~~~properties
inventory.client.timeout=3s
~~~

Deployment có thể cấp biến môi trường phù hợp quy ước relaxed binding của Spring Boot, ví dụ:

~~~bash
INVENTORY_CLIENT_TIMEOUT=1s java -jar app.jar
~~~

Khi bind `InventoryClientProperties`, nguồn environment variable thường có ưu tiên cao hơn nguồn `@PropertySource`; timeout hiệu lực có thể là 1 giây.

Cần phân biệt hai việc:

- **Ưu tiên nguồn:** OS environment thường thắng nguồn file defaults.
- **Chuẩn hóa tên property:** Spring Boot Binder có các quy tắc relaxed binding để ánh xạ tên biến môi trường sang property key Java, ví dụ dạng uppercase + underscore.

Khi dùng `Environment#getProperty` trực tiếp, khả năng nhận tên tương đương tùy PropertySource và resolver; nên dùng tên canonical khi có thể và kiểm tra trong context thực.

Nếu phải debug một override từ môi trường, xác minh biến đã được truyền tới **đúng tiến trình Java** và không bị một nguồn cao hơn ghi đè.

## 27. @Value đọc được property từ @PropertySource

Ngoài `Environment` và `@ConfigurationProperties`, một bean có thể dùng `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class InventoryBanner {

    private final String userAgent;

    InventoryBanner(
            @Value("${inventory.client.user-agent:inventory}")
            String userAgent) {
        this.userAgent = userAgent;
    }
}
~~~

Nếu file nạp bằng `@PropertySource` có:

~~~properties
inventory.client.user-agent=inventory-module
~~~

và không có nguồn cao hơn ghi đè, giá trị được inject có thể là `"inventory-module"`.

`@Value` không có quyền ưu tiên riêng so với Environment. Nó vẫn dựa vào hệ thống property resolution. Placeholder fallback `:inventory` được sử dụng khi không tìm thấy giá trị thích hợp; nó không phải một PropertySource ở mức cao.

Với nhiều key liên quan, `@ConfigurationProperties` thường dễ bảo trì hơn `@Value` trên nhiều field/constructor parameters.

## 28. Đừng dùng @PropertySource để chứa bí mật

Một file trong resources của JAR:

~~~properties
payment.api-token=real-production-secret
~~~

sẽ rất dễ bị lộ qua repository, artifact, CI logs hoặc công cụ đọc JAR. `@PropertySource` không làm nội dung đó được mã hóa hoặc bảo vệ.

Với secret:

- Sử dụng secret manager, Kubernetes Secret, environment hoặc config service phù hợp với hạ tầng.
- Giới hạn quyền đọc ở cấp deployment.
- Không commit bí mật thực.
- Không in token/password khi kiểm tra PropertySources.
- Có validation để không khởi động với credential vắng mặt hoặc placeholder giả.
- Không đặt một “secret mặc định” có thể vô tình được sử dụng ở production.

Nếu file external chỉ được tạo tại runtime bởi hạ tầng, vẫn phải xem permission và lifecycle rõ ràng. `ignoreResourceNotFound=true` không phải chiến lược quản lý secret.

## 29. Kiểm thử @PropertySource bằng ApplicationContextRunner

Để xác nhận một resource được nạp, có thể tạo test config nhỏ.

File trong test resources:

~~~properties
# src/test/resources/module-defaults.properties
demo.feature.enabled=true
demo.feature.retry-count=2
~~~

Configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:module-defaults.properties")
class ModuleDefaultsConfiguration {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class PropertySourceLoadingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(ModuleDefaultsConfiguration.class);

    @Test
    void loadsModuleDefaults() {
        runner.run(context -> {
            assertThat(
                context.getEnvironment()
                    .getProperty("demo.feature.enabled")
            ).isEqualTo("true");

            assertThat(
                context.getEnvironment()
                    .getProperty("demo.feature.retry-count")
            ).isEqualTo("2");
        });
    }
}
~~~

Test này kiểm tra:

1. Class config được đưa vào context.
2. Resource `module-defaults.properties` được nạp.
3. Environment đọc được key từ nguồn đó.

Nó chưa kiểm tra toàn bộ thứ tự ưu tiên trong một Spring Boot application chạy với Config Data thực tế.

## 30. Kiểm thử override priority

Có thể bổ sung property source trong test context với độ ưu tiên cao hơn:

~~~java
@Test
void explicitTestPropertyOverridesModuleDefaults() {
    runner
        .withPropertyValues(
            "demo.feature.retry-count=7"
        )
        .run(context -> {
            assertThat(
                context.getEnvironment().getProperty(
                    "demo.feature.retry-count"
                )
            ).isEqualTo("7");
        });
}
~~~

Ở đây giá trị test được cấp qua `withPropertyValues` theo cơ chế của `ApplicationContextRunner` và có thể có ưu tiên cao hơn nguồn defaults của `@PropertySource`. Test xác minh một cách cụ thể rằng **thêm properties resource không nhất thiết làm nó thắng mọi nguồn khác**.

Với ứng dụng có profile Config Data, nên bổ sung integration test thực sự nạp `application.yml` và `application-dev.yml` theo cấu hình mong muốn, thay vì mặc định rằng `ApplicationContextRunner` thuần có mọi quy tắc/auto-configuration của quá trình boot.

## 31. Test integration với @SpringBootTest

Giả sử ứng dụng đã nạp `InventoryConfiguration`.

File module defaults:

~~~properties
inventory.client.timeout=3s
inventory.client.max-retries=2
~~~

File `application.yml` của test/application:

~~~yaml
inventory:
  client:
    timeout: 5s
~~~

Test:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class InventoryPriorityIntegrationTest {

    @Autowired
    InventoryClientProperties properties;

    @Test
    void applicationConfigOverridesModuleDefault() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofSeconds(5));

        assertThat(properties.maxRetries())
            .isEqualTo(2);
    }
}
~~~

Test trên cần application context, properties registration và tài nguyên cấu hình đúng như ví dụ. Nếu test khác cấp property cùng key bằng `@SpringBootTest(properties=...)`, giá trị test có thể có ưu tiên cao hơn và kết quả kỳ vọng phải điều chỉnh.

Không cần chạy một lượt test cho toàn bộ Spring Boot framework; tập trung vào các **key quan trọng của module** mà ứng dụng thực sự cần đúng.

## 32. Test tránh phụ thuộc vào logging và bootstrap property

Một cách kiểm tra sai là viết:

~~~properties
# module-defaults.properties
logging.level.root=DEBUG
spring.profiles.active=prod
~~~

rồi test rằng module có được nạp hay không bằng cách quan sát logging/profile lúc khởi động.

Những property này có thể được xử lý từ sớm, trước khi annotation `@PropertySource` được đưa vào Environment. Vì vậy test có thể cho kết quả không như dự đoán, dù resource thật sự đã được nạp ở thời điểm context refresh.

Muốn test tính năng `@PropertySource`, nên dùng một key thông thường của module, ví dụ `demo.feature.retry-count`. Muốn test bootstrap configuration, phải cung cấp key từ nguồn được đọc ở giai đoạn thích hợp như Config Data hoặc môi trường khởi chạy.

Đừng suy luận từ một property được xử lý sớm rằng `@PropertySource` nói chung không hoạt động.

## 33. Test optional resource

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "file:./config/not-present-local.properties",
    ignoreResourceNotFound = true
)
class OptionalLocalConfig {}
~~~

Trong test chạy từ một working directory không chứa file trên, context vẫn có thể khởi tạo nếu chỉ vấn đề là resource tùy chọn bị thiếu và các thành phần khác không đòi những key từ file đó.

Nhưng đây không phải lời khuyên dựa vào working directory ngẫu nhiên trong CI. Muốn test lặp lại ổn định, hãy dùng temporary directory hoặc một đường dẫn được test cố ý kiểm soát, và khẳng định trạng thái file rõ ràng.

Nếu file là bắt buộc trong production, cần test startup bị từ chối khi file vắng, thay vì đặt optional cho mọi môi trường.

## 34. Khi hai @Configuration cùng thêm nguồn có key trùng

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:module-a.properties")
class ModuleAConfiguration {}

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:module-b.properties")
class ModuleBConfiguration {}
~~~

Hai file đều có:

~~~properties
integration.timeout=...
~~~

Dù Spring có thứ tự xử lý nguồn, bạn không nên thiết kế ứng dụng dựa vào thứ tự xử lý các configuration classes được phát hiện tự động nếu chưa có hợp đồng rõ về registration/import order.

Giải pháp tốt hơn:

- Dùng prefix phân biệt: `module-a.timeout` và `module-b.timeout`.
- Hoặc chỉ có một module sở hữu `integration.timeout`.
- Nếu cần override, đưa giá trị vào nguồn application/deployment có thứ tự ưu tiên rõ.
- Thêm integration test với tổ hợp modules thực tế.

Sự mơ hồ về precedence là dấu hiệu ownership của key chưa rõ, không phải lý do để thêm thêm nhiều @PropertySource annotations.

## 35. Nhận diện lỗi nạp resource và lỗi bind

Khi ứng dụng thất bại sau khi thêm annotation, cần xác định lớp lỗi:

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không tìm thấy `classpath:defaults.properties` | Resource chưa được đóng gói, sai path hoặc module |
| Không tìm thấy file external | Working directory, mount, path, quyền đọc |
| Có file nhưng YAML không bind | `@PropertySource` mặc định không đọc YAML như Boot Config Data |
| Key không có giá trị như mong đợi | Tên key sai hoặc nguồn ưu tiên cao hơn ghi đè |
| Giá trị `"many"` không bind sang `int` | Conversion error |
| Bean `@ConfigurationProperties` không tồn tại | Thiếu scanning/registration |
| Bean có giá trị nhưng vi phạm `@Min` | Validation |
| Logging không đổi theo file | Property được đọc sớm trước khi @PropertySource được thêm |
| Sửa file nhưng bean không thay đổi | Không có cơ chế refresh/rebind tự động |
| Chạy IDE được nhưng container lỗi | Classpath/working directory/mount khác nhau |

Lỗi resource, lỗi precedence và lỗi conversion **không nên được xử lý bằng cùng một workaround**. Cần sửa đúng tầng.

## 36. Checklist chọn @PropertySource hay cơ chế khác

Trước khi thêm `@PropertySource`, hỏi:

1. Resource có phải file `.properties` đúng định dạng không?
2. Resource đi cùng module hay được deployment cung cấp bên ngoài?
3. Class `@Configuration` chứa annotation có thực sự được nạp không?
4. Mục tiêu là cung cấp **defaults thấp ưu tiên** hay muốn override `application.yml`?
5. Key nào có thể trùng và nguồn nào phải thắng?
6. Có cần file/profile-specific YAML hoặc multi-document support không?
7. Có key nào phải có hiệu lực trước context refresh như `logging.*` không?
8. Có cần tự động refresh khi file thay đổi không?
9. Có secret nào không được đóng gói vào JAR không?
10. Resource có thể thiếu một cách hợp lệ không? Có nên fail-fast không?
11. Có cần encoding UTF-8 cho nội dung Unicode không?
12. Có test với application config và environment override thật không?
13. Có module khác đang tranh cùng prefix không?
14. Đã ưu tiên Config Data cho bài toán triển khai Spring Boot chưa?

**Quy tắc lựa chọn:** dùng `@PropertySource` cho file properties bổ sung gắn với configuration/module; dùng Config Data để quản lý cấu hình khởi động, profile và deployment; dùng nguồn bootstrap thích hợp nếu cần can thiệp sớm hoặc kiểm soát priority đặc thù.

## 37. Bài tập thực hành: module defaults và app overrides

**Yêu cầu:** module HTTP client có defaults 3s/2 retries, nhưng ứng dụng có quyền thay timeout thành 5s qua `application.yml` và production có quyền thay tiếp thành 1s qua biến môi trường.

### Bước 1 — Resource mặc định

Tạo:

~~~text
src/main/resources/inventory-client-defaults.properties
~~~

Nội dung:

~~~properties
inventory.client.timeout=3s
inventory.client.max-retries=2
inventory.client.enabled=true
~~~

### Bước 2 — Configuration nạp resource và bind record

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory.client")
public record InventoryClientProperties(
        Duration timeout,
        int maxRetries,
        boolean enabled
) {}
~~~

~~~java
package example.inventory;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {}
~~~

### Bước 3 — Ứng dụng ghi đè bằng Config Data

~~~yaml
# application.yml
inventory:
  client:
    timeout: 5s
~~~

Khi không có nguồn cao hơn, kỳ vọng:

~~~text
timeout     = 5s
maxRetries  = 2
enabled     = true
~~~

### Bước 4 — Deployment ghi đè

Ví dụ POSIX shell:

~~~bash
INVENTORY_CLIENT_TIMEOUT=1s java -jar app.jar
~~~

Khi biến được truyền và binder nhận diện theo quy tắc Spring Boot, timeout có thể thành 1s. Hai key không có override vẫn lấy từ defaults/module hoặc từ nguồn phù hợp khác.

### Bước 5 — Kiểm tra

Viết integration test có:

- Một case chỉ với defaults: timeout 3s.
- Một case có application config override: timeout 5s.
- Một case có nguồn override ưu tiên cao hơn: timeout 1s.
- Một case thiếu resource bắt buộc: context thất bại.
- Một case giá trị timeout sai định dạng: binding thất bại hoặc được xử lý theo cấu hình converter/validation rõ ràng.

Không cần in toàn bộ Environment, nhất là khi có token hoặc password. Có thể assert trực tiếp trên `InventoryClientProperties`.

### Bước 6 — Tự trả lời

**Câu 1:** Thêm `@PropertySource` có tự kích hoạt profile prod không?

**Đáp:** Không đáng tin cậy. Profile/Config Data cần được chọn trong giai đoạn bootstrap thích hợp.

**Câu 2:** Vì sao `application.yml` ghi 5s lại thắng resource ghi 3s?

**Đáp:** Theo precedence thông thường của Spring Boot, Config Data có ưu tiên cao hơn nguồn thêm qua `@PropertySource`.

**Câu 3:** Có thể chỉ đổi annotation thành `@PropertySource("classpath:defaults.yml")` để dùng YAML không?

**Đáp:** Không theo factory mặc định. Hãy dùng Config Data hoặc custom PropertySourceFactory có kiểm chứng.

**Câu 4:** `ignoreResourceNotFound=true` có bỏ qua timeout sai định dạng không?

**Đáp:** Không. Nó liên quan resource không tìm thấy, không phải conversion/validation.

**Câu 5:** Nếu cần source ưu tiên cao hơn command line thì có nên thêm nguồn ở ApplicationRunner không?

**Đáp:** Không nên. Đó là thay đổi quá muộn đối với nhiều giá trị đã được bind/đọc. Cần thiết kế extension point sớm và priority rõ ràng, đồng thời cân nhắc tính vận hành và bảo mật.

## 38. Tổng kết

`@PropertySource` là công cụ của Spring Framework để **nạp thêm resource properties vào Spring Environment** khi một configuration class được xử lý. Nó hữu ích cho mặc định của module hoặc một tệp properties bổ sung đã xác định rõ. Annotation hỗ trợ location dạng classpath/file, `name`, `encoding`, `ignoreResourceNotFound` và nhiều resource.

Trong Spring Boot, nguồn này thông thường có ưu tiên **dưới Config Data** và các nguồn override triển khai phổ biến. Vì `@PropertySource` được xử lý trong giai đoạn context refresh, đừng dùng nó để quyết định những property được Boot đọc từ rất sớm như logging, các thiết lập spring.main hoặc việc chọn profile/Config Data.

Nếu cần YAML, profile-specific config, import priority hoặc thêm đường dẫn cấu hình bên ngoài artifact, ưu tiên cơ chế **Spring Boot Config Data** như `spring.config.import` và `spring.config.additional-location`. Khi cần xác định nguồn thắng, hãy đọc Environment/PropertySources trong test hoặc môi trường debug được kiểm soát, không suy luận chỉ từ tên file.

**Ghi nhớ:** `@PropertySource` **thêm một nguồn cấu hình**, không phải một chỉ thị “ghi đè mọi nguồn”; kết quả cuối cùng phụ thuộc **thời điểm nạp**, **thứ tự ưu tiên** và **kiểu binding của property**.
