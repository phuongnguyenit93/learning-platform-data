# PropertySourceLocator chạy sai thời điểm hoặc bị gọi lặp

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_CORE**. `PropertySourceLocator` là extension point của Spring Cloud bootstrap, cho phép ứng dụng bổ sung `PropertySource` từ Config Server, secret/configuration service hoặc một nguồn dữ liệu bên ngoài. Khi locator được gọi trước khi profile, application name hoặc bootstrap setting sẵn sàng, ứng dụng có thể tải sai cấu hình. Khi locator được gọi nhiều lần, ứng dụng có thể gửi nhiều request tới nguồn cấu hình, tạo log trùng, tăng thời gian startup hoặc lặp side effect nếu implementation không an toàn.

Không phải mọi lần gọi lặp đều là lỗi. Từ các release train hiện đại, Spring Cloud có thể gọi locator theo hai pha: lần đầu lấy property source chưa gắn profile để chúng có cơ hội kích hoạt profile; lần tiếp theo diễn ra sau khi main application context khởi động với các profile đã được xác định. Config Data của Spring Boot cũng có thể tạo nhiều request tới Config Server khi dùng `spring.config.import`. Ngoài ra, context hierarchy và test có thể tạo nhiều bootstrap context độc lập.

Bài học giúp bạn phân biệt các cơ chế đó, xác định locator đang chạy ở bootstrap hay main context, kiểm tra profile và property source order, thiết kế locator an toàn khi được gọi lại, và chọn cách đăng ký phù hợp với Config Data hoặc legacy bootstrap.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của `PropertySourceLocator` trong Spring Cloud bootstrap.
2. Phân biệt bootstrap context, main application context và Config Data loading.
3. Giải thích vì sao locator có thể được gọi hai lần trong các release train hiện đại.
4. Phân biệt lần fetch không profile với lần fetch có active profile.
5. Hiểu mục đích và phạm vi của `spring.cloud.config.initialize-on-context-refresh`.
6. Xác định khi nào ứng dụng đang dùng legacy bootstrap, Config Data hoặc cả hai.
7. Phát hiện nhiều bootstrap context trong context hierarchy.
8. Đăng ký custom bootstrap configuration qua `META-INF/spring.factories`.
9. Tránh để bootstrap configuration bị component scan vào main application context.
10. Thiết kế locator idempotent, không tạo side effect và không phụ thuộc bean chỉ có ở main context.
11. Xử lý `spring.application.name`, active profiles, label và property source precedence.
12. Chẩn đoán lỗi do thứ tự `@Order` hoặc trùng tên property source.
13. Viết unit test cho locator và integration test cho vòng đời bootstrap.
14. Phân biệt locator được gọi lúc startup với locator được gọi lại khi runtime refresh.
15. Dùng log và dependency inspection để phân biệt fetch hợp lệ với fetch bất thường.

## 2. PropertySourceLocator nằm ở đâu trong vòng đời ứng dụng?

### 2.1. Bootstrap context và main application context

Trong legacy bootstrap, Spring Cloud tạo một bootstrap context làm parent của main application context. Bootstrap context chịu trách nhiệm nạp cấu hình ngoài và chuẩn bị các property source trước khi main context được khởi tạo.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["SpringApplication bắt đầu"] --> B["Tạo bootstrap context"]
    B --> C["Đọc BootstrapConfiguration từ spring.factories"]
    C --> D["Tạo các PropertySourceLocator bean"]
    D --> E["Chạy pha bootstrap của locator"]
    E --> F["Thêm bootstrap PropertySource vào Environment"]
    F --> G["Tạo main application context"]
    G --> H["Xác định active profiles"]
    H --> I["Chạy pha locator với Environment của main context"]
    I --> J["Hoàn tất Environment và tạo application beans"]
~~~

Sơ đồ thể hiện ý tưởng hai pha thường gặp trong các phiên bản hỗ trợ profile-aware bootstrap. Thời điểm chính xác phụ thuộc Spring Cloud release train và cấu hình bootstrap. Không dùng sơ đồ này để kết luận mọi ứng dụng luôn có đúng hai lần gọi.

Bootstrap và main context có thể chia sẻ `Environment` theo cơ chế Spring Cloud, nhưng chúng vẫn là hai ApplicationContext khác nhau. Một property source được thêm trong bootstrap có thể được main context kế thừa. Locator nhận `Environment` của context mà nó đang cung cấp property source.

### 2.2. PropertySourceLocator làm nhiệm vụ gì?

Interface `PropertySourceLocator` nằm trong package:

~~~java
org.springframework.cloud.bootstrap.config.PropertySourceLocator
~~~

Contract chính là:

~~~java
public interface PropertySourceLocator {

    PropertySource<?> locate(Environment environment);
}
~~~

Method `locate` nhận Environment hiện tại và trả về một PropertySource; có thể trả `null` nếu không có dữ liệu. Interface còn hỗ trợ `locateCollection` để biểu diễn một hoặc nhiều property source, bao gồm các property source con của CompositePropertySource.

Locator không phải bean nghiệp vụ thông thường. Nó được dùng trong quá trình bootstrap để bổ sung cấu hình trước khi phần lớn bean của main application context được tạo.

### 2.3. Environment được truyền vào có gì?

Environment nhận được đã có các property source Spring Boot cung cấp cho context tương ứng. Locator có thể đọc các thông tin như:

- `spring.application.name`.
- `spring.profiles.active` và `Environment.getActiveProfiles()`.
- Config label hoặc tenant selector đã có từ bootstrap/local setting.
- System property và environment variable cần để định vị nguồn cấu hình.

Tuy nhiên, không nên giả định mọi giá trị remote đã tồn tại trong lần gọi đầu tiên. Một trong những mục đích của hai pha là cho phép lần fetch đầu tiên trả về property có thể kích hoạt profile, rồi lần fetch sau mới lấy cấu hình profile-specific.

## 3. Vì sao locator được gọi hai lần?

### 3.1. Hai pha profile-aware là hành vi dự kiến

Từ các release train hiện đại, tài liệu Spring Cloud mô tả `PropertySourceLocators` được gọi hai lần:

1. **Lần fetch đầu:** lấy property source khi chưa có profile active từ remote config. Property source này có thể chứa `spring.profiles.active` để kích hoạt profile.
2. **Lần fetch sau:** sau khi main application context bắt đầu, locator được gọi lại với active profiles đã xác định để tìm thêm property source phù hợp với profile.

Ví dụ Config Server trả về cấu hình mặc định:

~~~yaml
spring:
  profiles:
    active: production

app:
  feature:
    mode: safe-default
~~~

Sau khi profile `production` được kích hoạt, lần fetch tiếp theo có thể lấy property source tương ứng:

~~~yaml
app:
  feature:
    mode: production
~~~

Vì vậy, hai log của cùng một locator với profile list khác nhau thường là điều bình thường.

### 3.2. Khác biệt theo release train

Tài liệu Spring Cloud Commons hiện hành ghi rõ rằng trước Spring Cloud 2022.0.3, các PropertySourceLocator (bao gồm locator của Config Client) được chạy trong main application context thay vì bootstrap context. Có thể đặt `spring.cloud.config.initialize-on-context-refresh=true` trong `bootstrap.yml` hoặc `bootstrap.properties` để buộc locator chạy trong bootstrap context.

Các dòng Spring Cloud cũ hơn có thể có mốc chuyển đổi và behavior khác trong tài liệu của chính release train đó. Khi chẩn đoán, hãy đối chiếu đúng BOM đang dùng; không suy luận lifecycle chỉ từ tài liệu của phiên bản mới nhất.

### 3.3. Số lần gọi không phải cam kết cố định cho mọi ứng dụng

Số lần quan sát được còn phụ thuộc:
- Spring Cloud release train.
- Legacy bootstrap có được bật hay không.
- Config Data có được sử dụng hay không.
- Số ApplicationContext trong hierarchy.
- Test tạo một hay nhiều context.
- Cơ chế retry của locator hoặc client mà locator sử dụng.
- Ứng dụng có khởi tạo lại context trong cùng process hay không.

Hãy so sánh context ID, active profiles, thread, timestamp và stack/log marker để xác định từng lần gọi thuộc pha nào. Không viết test production phụ thuộc cứng vào giả định rằng toàn bộ ứng dụng chỉ có đúng hai lần gọi.

### 3.4. Phân biệt với nhiều request của Config Data

Spring Boot Config Data sử dụng `spring.config.import` để nạp cấu hình. Config Client có thể gửi request đầu tiên với profile `default` để tìm profile được kích hoạt từ remote config, sau đó gửi request tiếp theo với các active profiles.

Các request này thuộc Config Data loader, không phải custom `PropertySourceLocator` của legacy bootstrap.

| Dấu hiệu | Legacy bootstrap locator | Config Data import |
| --- | --- | --- |
| Cơ chế | `PropertySourceLocator` | `ConfigDataLocationResolver` / ConfigDataLoader của Config Client |
| Kích hoạt | Bootstrap được bật và locator được đăng ký trong bootstrap configuration. | Có `spring.config.import=configserver:`. |
| Nơi cấu hình | `bootstrap.yml` và `spring.factories` theo bootstrap mechanism. | `application.yml` hoặc Config Data import location. |
| Nhiều lần fetch | Có thể có hai pha profile-aware và nhiều context. | Có thể có nhiều request do quá trình resolve default profile và active profiles. |
| Cách xử lý | Kiểm tra bootstrap lifecycle và custom locator. | Kiểm tra Config Data import, resolver/loader và profile resolution. |

Nếu log cho thấy hai request Config Server nhưng không có log từ custom locator, đừng vội sửa `PropertySourceLocator`. Hãy xác định request được tạo bởi Config Data loader.

## 4. initialize-on-context-refresh điều khiển điều gì?

### 4.1. Giá trị mặc định

Property:

~~~yaml
spring:
  cloud:
    config:
      initialize-on-context-refresh: false
~~~

Mặc định của Spring Cloud Commons hiện hành là `false`. Property này điều khiển việc khởi tạo bootstrap configuration theo ContextRefreshedEvent. Nó liên quan đến thời điểm locator chạy trong bootstrap lifecycle.

### 4.2. Khi nào đặt true?

Trong legacy bootstrap, có thể đặt property trong `bootstrap.yml` hoặc `bootstrap.properties`:

~~~yaml
spring:
  cloud:
    config:
      initialize-on-context-refresh: true
~~~

Tùy chọn này buộc PropertySourceLocators được thực thi trong bootstrap context theo cơ chế Spring Cloud mô tả. Nó hữu ích khi một property source phải có mặt sớm hơn trong quá trình tạo main context.

### 4.3. Đây không phải công tắc tắt lần gọi thứ hai

Không dùng `initialize-on-context-refresh=true` với mục tiêu loại bỏ lần fetch profile-specific. Tùy chọn này điều chỉnh thời điểm bootstrap initialization; behavior hai pha profile-aware vẫn cần được hiểu theo release train đang dùng.

Nếu locator gọi dịch vụ từ xa, hãy làm cho mỗi lần gọi có thể lặp an toàn. Nếu mục tiêu là giảm số request, cần tối ưu fetch, cache theo application/profile/label hoặc thay đổi kiến trúc nguồn cấu hình sau khi đã xác định chính xác request nào là dư thừa.

### 4.4. Đặt property ở đúng nơi

Với legacy bootstrap, đặt property trong bootstrap configuration:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: inventory-service
  cloud:
    config:
      initialize-on-context-refresh: true
      uri: http://config-server:8888
~~~

Nếu ứng dụng chỉ dùng Config Data qua `spring.config.import`, property bootstrap này không phải công tắc để điều khiển số lần Config Data request. Hãy kiểm tra cơ chế đang thực sự được sử dụng trước khi thay đổi.

## 5. Đăng ký custom locator đúng cách

### 5.1. Bật legacy bootstrap

Bootstrap có thể được bật bằng starter `spring-cloud-starter-bootstrap` hoặc property `spring.cloud.bootstrap.enabled=true` được truyền qua system property/environment variable theo hướng dẫn của phiên bản tương ứng.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-bootstrap")
}
~~~

Nếu dependency management đã cung cấp `spring-cloud-starter-bootstrap`, không tự khai báo version riêng. Trong ứng dụng thực tế, chỉ thêm bootstrap starter nếu kiến trúc cần legacy bootstrap hoặc custom PropertySourceLocator.

Nếu bật bootstrap bằng property thay vì starter, property phải có sẵn trước khi Spring Boot đọc application configuration. Ví dụ chạy ứng dụng:

~~~bash
java -Dspring.cloud.bootstrap.enabled=true -jar inventory-service.jar
~~~

Hoặc truyền environment variable `SPRING_CLOUD_BOOTSTRAP_ENABLED=true` từ runtime. Không đặt property này chỉ trong `application.yml` rồi kỳ vọng nó tự bật bootstrap, vì file đó được xử lý trong main application config phase.

### 5.2. Đăng ký bằng spring.factories

Tạo file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=com.example.bootstrap.CatalogBootstrapConfiguration
~~~

Key `org.springframework.cloud.bootstrap.BootstrapConfiguration` khai báo các configuration class dùng để tạo bootstrap context. Có thể liệt kê nhiều class, phân tách bằng dấu phẩy.

### 5.3. Không để bootstrap configuration bị component scan

Đặt class bootstrap ở package riêng, không nằm trong package được `@SpringBootApplication` hoặc `@ComponentScan` của main app quét vào.

Ví dụ cấu trúc:

~~~text
com.example.inventory
  InventoryApplication.java
  service/
  controller/
  config/
com.example.inventorybootstrap
  CatalogBootstrapConfiguration.java
  CustomCatalogPropertySourceLocator.java
src/main/resources/META-INF/spring.factories
~~~

Nếu cùng configuration class được nạp vào cả bootstrap context và main context, có thể xuất hiện bean trùng, locator được đăng ký hai nơi hoặc dependency có vòng đời không như dự kiến.

### 5.4. Kiểm tra package và classpath

Khi locator không chạy:
- Kiểm tra resource `META-INF/spring.factories` có nằm trong artifact cuối cùng.
- Kiểm tra class name trong file đúng package và tên class.
- Kiểm tra bootstrap đã được bật.
- Kiểm tra dependency `spring-cloud-context` và release train tương thích.
- Kiểm tra configuration class không bị component scan vào main context.
- Kiểm tra không có nhiều file spring.factories khai báo cùng locator ngoài ý muốn.

## 6. Viết locator an toàn khi được gọi lại

### 6.1. Locator nên là thao tác đọc có thể lặp

Một locator tốt nên:
- Đọc application name và active profiles từ Environment.
- Gọi nguồn cấu hình với timeout hữu hạn.
- Trả về property source bất biến hoặc dữ liệu đã được snapshot.
- Không ghi database, không đăng ký service, không phát message.
- Không sửa trực tiếp Environment trong method `locate`.
- Không tạo bean nghiệp vụ hoặc giữ reference tới main application context.
- Không lưu kết quả dùng chung mà bỏ qua profile, label hoặc tenant.

Vì locator có thể được gọi lại, mọi side effect trong method này đều có nguy cơ bị lặp.

### 6.2. Ví dụ locator đơn giản

Ví dụ dưới đây minh họa locator lấy cấu hình hiệu lực theo application và active profiles. Phần `fetchEffectiveProperties` là logic do ứng dụng triển khai để đọc nguồn cấu hình từ xa; trong ví dụ, nó trả map mẫu để làm rõ việc hợp nhất cấu hình mặc định và profile.

~~~java
package com.example.inventorybootstrap;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

public class CustomCatalogPropertySourceLocator
        implements PropertySourceLocator {

    @Override
    public PropertySource<?> locate(Environment environment) {
        String application =
                environment.getProperty("spring.application.name");

        if (application == null || application.isBlank()) {
            return null;
        }

        List<String> profiles =
                Arrays.asList(environment.getActiveProfiles());

        Map<String, Object> properties =
                fetchEffectiveProperties(application, profiles);

        if (properties.isEmpty()) {
            return null;
        }

        return new MapPropertySource(
                "catalog-" + application,
                properties
        );
    }

    private Map<String, Object> fetchEffectiveProperties(
            String application,
            List<String> profiles) {

        Map<String, Object> result = new LinkedHashMap<>();

        // Giá trị mặc định luôn được lấy trước.
        result.put("catalog.timeout-ms", 2000);
        result.put("catalog.mode", "safe");

        // Profile cụ thể ghi đè giá trị mặc định.
        if (profiles.contains("production")) {
            result.put("catalog.timeout-ms", 5000);
            result.put("catalog.mode", "production");
        }

        return result;
    }
}
~~~

Class locator ở ví dụ trên không tự component-scan. Nó được tạo thành bean bởi bootstrap configuration bên dưới, rồi được nạp qua `spring.factories`.

### 6.3. Ví dụ bootstrap configuration rõ ràng

Có thể khai báo locator như một bean trong configuration class:

~~~java
package com.example.inventorybootstrap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class CatalogBootstrapConfiguration {

    @Bean
    @Order(Ordered.LOWEST_PRECEDENCE)
    CustomCatalogPropertySourceLocator catalogPropertySourceLocator() {
        return new CustomCatalogPropertySourceLocator();
    }
}
~~~

Và đăng ký configuration class trong `META-INF/spring.factories`:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=com.example.inventorybootstrap.CatalogBootstrapConfiguration
~~~

Chọn một cách đăng ký nhất quán. Không vừa component-scan class locator trong main app vừa đăng ký nó trong bootstrap context.

### 6.4. Luôn hợp nhất default và profile-specific properties

Ở lần gọi sau, bootstrap property source được xây dựng lại theo Environment và các locator hiện có. Locator nên trả về tập property hiệu lực đầy đủ cho application/profile hiện tại, gồm default/common values và phần override theo active profiles.

Không chỉ trả phần delta profile-specific nếu nguồn cấu hình không bảo đảm giữ lại base source. Nếu lần gọi thứ hai chỉ trả các key của production, các key mặc định không xuất hiện trong kết quả mới có thể biến mất khỏi composite bootstrap property source.

### 6.5. Cache phải có key đầy đủ

Nếu nguồn cấu hình đắt tiền và cần cache, key cache tối thiểu nên phân biệt:
- Application name.
- Danh sách active profiles đã chuẩn hóa.
- Config label/revision.
- Tenant hoặc namespace nếu có.
- Version của credential/configuration request nếu ảnh hưởng kết quả.

Không cache duy nhất theo application name rồi dùng lại kết quả lần đầu cho lần gọi có profile. Điều đó làm locator chạy đúng hai lần nhưng trả sai property source ở pha thứ hai.

## 7. Chẩn đoán locator chạy sai thời điểm

### 7.1. Property cần dùng đã bị thiếu trong lần gọi đầu

Triệu chứng:
- Locator không tìm thấy `spring.application.name`.
- Config source truy vấn sai application.
- Bootstrap URL hoặc credential chưa có.
- Locator không biết profile cần dùng.

Nguyên nhân thường là property được đặt trong remote source mà locator đang cố truy vấn. Locator không thể dùng một giá trị chỉ có thể lấy được sau chính lần truy vấn đó để định vị request đầu tiên.

Cách xử lý:
1. Đặt tối thiểu bootstrap identity trong environment variable, system property hoặc `bootstrap.yml`.
2. Đặt `spring.application.name` và Config Server URI ở nơi có sẵn trước bootstrap.
3. Để remote config cung cấp phần cấu hình còn lại.
4. Nếu profile được kích hoạt từ remote config, dùng kết quả pha đầu để kích hoạt profile và pha sau để lấy profile-specific properties.

### 7.2. Locator phụ thuộc bean của main context

Bootstrap context được tạo trước main context. Bean chỉ được khai báo trong package main app hoặc được tạo bởi auto-configuration của main context có thể chưa tồn tại khi locator chạy.

Không inject các service nghiệp vụ như repository, business service hoặc client chỉ được khởi tạo trong main context vào bootstrap locator.

Thay vào đó:
- Tạo bootstrap-specific client tối giản.
- Dùng HTTP client với timeout rõ ràng.
- Truyền bootstrap credentials từ environment/system property.
- Đăng ký dependency cần thiết trong bootstrap configuration.
- Tránh phụ thuộc ngược từ bootstrap bean vào main context.

### 7.3. Locator chạy trước khi active profile được thiết lập

Nếu profile được cấu hình trong remote property source, lần fetch đầu có thể chưa có profile đó. Đây là lý do có pha fetch tiếp theo.

Nếu profile phải được biết ngay từ đầu, đặt profile trong local/bootstrap environment:

~~~yaml
spring:
  profiles:
    active: production
~~~

Nếu profile được remote config kích hoạt, không ép locator phải thấy profile đó trong lần đầu. Hãy kiểm tra lần gọi thứ hai và property source được trả về.

### 7.4. Locator chạy sau thời điểm ứng dụng cần property

Nếu main context cần một remote property để quyết định cấu hình bean quá sớm, xác định property đó có thực sự cần trong bootstrap không. Với legacy bootstrap, xem xét `spring.cloud.config.initialize-on-context-refresh=true` trong `bootstrap.yml` để chuyển locator vào bootstrap phase theo cơ chế được hỗ trợ.

Nếu dùng Config Data, khai báo `spring.config.import` đúng cách để remote properties tham gia quá trình Config Data resolution. Không dùng property legacy để sửa một luồng Config Data mà nó không điều khiển.

## 8. Chẩn đoán locator bị gọi nhiều hơn mong đợi

### 8.1. Kiểm tra cơ chế nào thực sự gửi request

Bật log an toàn cho:
- `org.springframework.cloud.bootstrap.config.PropertySourceBootstrapConfiguration`.
- Custom locator của ứng dụng.
- Config Client loader nếu dùng `spring.config.import`.

Trong custom locator, ghi metadata không nhạy cảm:
- Tên locator.
- Application name.
- Active profiles.
- Context ID nếu có thể xác định.
- Timestamp và correlation ID.
- Số lần gọi trong test.

Không ghi token, password, raw property value hoặc toàn bộ Environment.

### 8.2. Kiểm tra đồng thời Config Data và legacy bootstrap

Một nguyên nhân phổ biến là ứng dụng vừa:
- Có `spring.config.import=configserver:`.
- Vừa có `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`.
- Vừa giữ cấu hình `spring.cloud.config.uri` và custom `PropertySourceLocator` cũ.

Khi cả hai đường nạp Config Server được bật, có thể xuất hiện request trùng từ hai cơ chế độc lập. Chọn một mô hình cấu hình chính. Nếu cần custom source trong Config Data, cân nhắc triển khai theo extension point Config Data của Spring Boot thay vì giữ bootstrap locator cũ cho cùng một nguồn.

### 8.3. Kiểm tra context hierarchy

Với `SpringApplicationBuilder`, ứng dụng có thể tạo parent, child hoặc sibling contexts. Mỗi context trong hierarchy có thể có bootstrap property source riêng và, tùy cấu hình, có thể truy vấn nguồn remote riêng.

Kiểm tra:
- Có bao nhiêu ApplicationContext được tạo?
- Context nào là parent, child hoặc sibling?
- Mỗi context dùng application name nào?
- Environment có được chia sẻ hay không?
- Locator có cần chạy riêng cho từng child không?

Không dùng static counter toàn JVM để kết luận locator bị gọi lặp nếu ứng dụng chủ động tạo nhiều context.

### 8.4. Kiểm tra test tạo nhiều context

`@SpringBootTest`, `@ContextConfiguration` hoặc các test khởi chạy nhiều `SpringApplication` có thể tạo nhiều context trong cùng một JVM. Test isolation, context cache và context hierarchy ảnh hưởng số lần locator được khởi tạo.

Trong integration test, log context ID cùng application/profile. Nếu mỗi test class khởi tạo context riêng, nhiều lần gọi có thể hoàn toàn hợp lệ.

### 8.5. Kiểm tra retry ở client bên trong locator

Nếu locator gọi HTTP tới Config Server, Vault hoặc custom service, client đó có thể retry khi timeout hoặc lỗi tạm thời. Một lần gọi `locate` có thể tạo nhiều request mạng.

Phân biệt:
- Số lần method `locate` được gọi.
- Số lần HTTP request được gửi trong một lần `locate`.
- Số lần context/bootstrap được khởi tạo.

Gắn correlation ID cho mỗi lần locate và request ID cho mỗi outbound request để xác định tầng nào tạo lặp.

### 8.6. Kiểm tra runtime refresh gọi lại nguồn cấu hình

Một lần gọi locator sau startup có thể đến từ thao tác refresh chứ không phải một lần khởi động mới. Khi legacy bootstrap được bật, Spring Cloud tạo `LegacyContextRefresher`; khi `POST /actuator/refresh` hoặc refresh event được xử lý, refresher nạp lại bootstrap property sources và có thể gọi lại các PropertySourceLocator.

Khi bootstrap bị tắt, Spring Cloud dùng `ConfigDataContextRefresher` để tải lại cấu hình theo Config Data. Luồng này dùng resolver/loader của Config Data; không nên gán các request đó cho custom PropertySourceLocator.

Phân biệt hai trường hợp:

| Điều kiện | Refresher được chọn | Extension point được chạy lại |
| --- | --- | --- |
| Legacy bootstrap enabled | `LegacyContextRefresher` | `PropertySourceLocator` trong bootstrap context. |
| Bootstrap disabled, dùng Config Data | `ConfigDataContextRefresher` | Config Data import/resolver/loader. |

Property `spring.cloud.config.initialize-on-context-refresh` điều khiển thời điểm locator được khởi tạo trong bootstrap lifecycle. Nó không phải công tắc ngăn `LegacyContextRefresher` gọi locator khi ứng dụng thực hiện runtime refresh.

Khi thấy log locator sau khi ứng dụng đã READY, hãy kiểm tra:
- Có request `POST /actuator/refresh` hay không.
- Có RefreshEvent từ Spring Cloud Bus hoặc custom event listener không.
- Có scheduled job hoặc watcher phát refresh event không.
- Có bao nhiêu lần refresh được phát trong một khoảng thời gian.
- Refresh đang dùng LegacyContextRefresher hay ConfigDataContextRefresher.

Trong integration test, ghi timestamp, request/correlation ID và profile ở mỗi lần locate; sau đó gọi refresh endpoint một lần để xác minh đúng một chu kỳ refresh được quan sát. Không assert tổng số lần gọi của cả process nếu test còn tạo nhiều context hoặc có retry.

## 9. Thứ tự locator và property source precedence

### 9.1. Dùng @Order khi có nhiều locator

Spring Cloud sắp xếp các `PropertySourceLocator` theo order trước khi thực thi. Nếu có nhiều locator, hãy đặt `@Order` hoặc triển khai `Ordered` để thể hiện thứ tự rõ ràng.

Ví dụ:

~~~java
@Bean
@Order(10)
PropertySourceLocator platformDefaultsLocator() {
    return platformDefaultsLocator;
}

@Bean
@Order(20)
PropertySourceLocator serviceOverridesLocator() {
    return serviceOverridesLocator;
}
~~~

Đừng để thứ tự phụ thuộc vào thứ tự classpath hoặc component scanning. Khi hai nguồn có cùng key, hãy viết test xác minh giá trị cuối cùng và nguồn có precedence cao hơn theo cấu hình thực tế.

### 9.2. Tên property source phải ổn định và có ý nghĩa

Dùng tên duy nhất, ổn định, dễ nhận diện:

~~~java
return new MapPropertySource(
        "catalog-config-" + application,
        properties
);
~~~

Tránh dùng tên ngẫu nhiên theo timestamp hoặc UUID cho mỗi lần gọi. Tên thay đổi liên tục làm khó chẩn đoán, tăng nguy cơ property source trùng lặp và khiến việc kiểm tra thứ tự trở nên khó khăn.

### 9.3. Remote property source có thể có precedence cao

Bootstrap property source thường được thêm với precedence cao theo quy tắc bootstrap. Nếu muốn local configuration được override remote properties, phải hiểu các property `spring.cloud.config.allowOverride`, `overrideNone` và `overrideSystemProperties`. Một số quyền override phải được cấp từ remote source; không thể luôn bật chỉ bằng local property.

Không giải quyết lỗi precedence bằng cách đổi tên property source ngẫu nhiên. Hãy xác minh property source list, order và policy override.

## 10. Log và công cụ quan sát

### 10.1. Log nên thể hiện phase và profile

Ví dụ log an toàn:

~~~text
locator=CatalogLocator
application=inventory-service
profiles=[]
context=bootstrap
phase=initial
result=property-source-found
~~~

Lần gọi sau:

~~~text
locator=CatalogLocator
application=inventory-service
profiles=[production]
context=main
phase=profile-specific
result=property-source-found
~~~

Tên phase là metadata do ứng dụng ghi để chẩn đoán; nó không phải field bắt buộc của Spring Cloud. Hãy lấy context ID và profiles từ Environment hoặc context tương ứng nếu có.

### 10.2. Không log property values

Property source có thể chứa password, token, private key, database URL hoặc thông tin nội bộ. Không log `PropertySource.toString()`, map values hoặc toàn bộ Environment ở production.

Nếu cần chẩn đoán:
- Ghi tên property source.
- Ghi số lượng key.
- Ghi application/profile/label.
- Ghi revision hoặc config version không nhạy cảm.
- Ghi request duration và kết quả.
- Chỉ hiển thị key đã được allowlist khi cần.

### 10.3. Kiểm tra Environment và property sources

Trong môi trường development, có thể kiểm tra:
- Active profiles.
- Tên các PropertySource.
- Giá trị một property không nhạy cảm.
- Nguồn property theo cơ chế origin nếu được hỗ trợ.

Actuator `/actuator/env` có thể tiết lộ dữ liệu cấu hình. Chỉ expose có kiểm soát, yêu cầu authorization phù hợp và không mở endpoint này công khai để debug.

### 10.4. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-starter-bootstrap,org.springframework.cloud:spring-cloud-config-client,org.springframework.cloud:spring-cloud-context
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-starter-bootstrap --configuration runtimeClasspath
~~~

Tìm các dependency kéo bootstrap starter vào transitively. Không loại bỏ một dependency chỉ vì nó xuất hiện trong tree; xác minh component nào đang cần legacy bootstrap trước khi thay đổi.

## 11. Kiểm thử PropertySourceLocator

### 11.1. Unit test theo profile

Unit test cần kiểm tra locator với các Environment khác nhau:
- Không có active profile.
- Có một profile.
- Có nhiều profile.
- Thiếu application name.
- Remote source rỗng.
- Nguồn cấu hình trả lỗi.
- Hai lần gọi với cùng Environment trả kết quả nhất quán.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.core.env.PropertySource;

class CustomCatalogPropertySourceLocatorTests {

    private final CustomCatalogPropertySourceLocator locator =
            new CustomCatalogPropertySourceLocator();

    @Test
    void returnsDefaultPropertiesWithoutActiveProfile() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.application.name", "inventory-service");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source).isNotNull();
        assertThat(source.getProperty("catalog.mode")).isEqualTo("safe");
    }

    @Test
    void returnsProfileSpecificProperties() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.application.name", "inventory-service");
        environment.setActiveProfiles("production");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source.getProperty("catalog.mode"))
                .isEqualTo("production");
    }
}
~~~

Đây là unit test cho logic locator, không chứng minh bootstrap lifecycle đã gọi nó đúng hai pha. Cần integration test riêng cho lifecycle.

### 11.2. Integration test xác minh hai pha

Tạo một recording locator trong test, ghi lại:
- Số lần method được gọi.
- Active profiles ở mỗi lần gọi.
- Application name.
- Context ID hoặc marker phase.
- Thời gian gọi.

Khi chạy với release train hỗ trợ hai pha, xác minh lần đầu lấy được base properties và lần sau có profile mà base properties kích hoạt. Không assert một con số cố định trên mọi context hierarchy hoặc mọi retry scenario.

### 11.3. Test tính idempotent

Gọi locator hai lần với cùng Environment và xác minh:
- Kết quả cấu hình tương đương.
- Không tạo record/database row trùng.
- Không phát event hoặc message.
- Không đăng ký service nhiều lần.
- Không thay đổi trạng thái dùng chung ngoài cache được kiểm soát.

Nếu locator bắt buộc phải có side effect, chuyển side effect sang một lifecycle hook có semantics một lần rõ ràng, không đặt trong `locate`.

### 11.4. Test context hierarchy

Tạo parent/child contexts với application name hoặc profile khác nhau nếu ứng dụng thật sử dụng hierarchy. Xác minh:
- Locator nào được gọi trong từng context.
- Child có nhận property source của parent hay không.
- Property source cùng tên có bị thay thế theo quy tắc Spring hay không.
- Application name/profile của child có truy vấn remote source riêng không.

### 11.5. Test Config Data và bootstrap riêng

Nếu ứng dụng đang migration:
1. Test Config Data import trong một profile ứng dụng.
2. Test legacy bootstrap locator trong profile riêng.
3. Test khi cả hai được bật để phát hiện request trùng.
4. Xác minh chỉ cơ chế được chọn được dùng trong deployment cuối cùng.

Không dựa vào unit test của locator để khẳng định Config Data loader đã hoạt động.

## 12. Các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Locator không được gọi. | Bootstrap chưa bật hoặc spring.factories không được đọc. | Kiểm tra starter/property, resource trong jar và key BootstrapConfiguration. |
| Locator được gọi nhưng application name rỗng. | spring.application.name chỉ có trong remote config. | Đặt application name trong local/bootstrap environment. |
| Lần đầu không có profile. | Đây là pha lấy base properties để kích hoạt profile. | Kiểm tra lần gọi tiếp theo; không coi lần đầu là lỗi. |
| Locator gọi hai lần với profile khác nhau. | Hai pha profile-aware của Spring Cloud. | Đảm bảo locator idempotent và trả full effective properties. |
| Có nhiều HTTP request nhưng locator chỉ log một lần. | Client bên trong locator retry hoặc một request bị redirect. | Gắn request ID ở HTTP client và đo retry. |
| Config Server bị gọi hai lần dù không có custom locator log. | Config Data profile resolution. | Kiểm tra spring.config.import và ConfigData loader. |
| Config Server bị gọi từ cả bootstrap và Config Data. | Cả legacy bootstrap và Config Data cùng được cấu hình. | Chọn một cơ chế chính; bỏ đường nạp trùng sau khi xác minh migration. |
| Locator chạy trước khi bean dependency sẵn sàng. | Bean chỉ tồn tại trong main context. | Chuyển dependency cần thiết vào bootstrap config hoặc dùng client tối giản. |
| Profile-specific properties bị mất sau lần gọi thứ hai. | Locator chỉ trả delta thay vì base + profile merged source. | Trả đầy đủ property set hiệu lực cho profile hiện tại. |
| Hai locator ghi đè cùng key không ổn định. | Thiếu @Order hoặc chưa xác định precedence. | Khai báo order và viết test property source precedence. |
| Property source xuất hiện nhiều tên khác nhau. | Tên source được tạo ngẫu nhiên theo mỗi lần locate. | Dùng tên ổn định theo application/source. |
| Locator chạy nhiều lần trong test. | Nhiều ApplicationContext hoặc context hierarchy được tạo. | Ghi context ID và tách số lần theo context. |
| Locator chạy trong main context ngoài dự kiến. | Bootstrap configuration bị component scan hoặc timing khác theo release train. | Đặt package bootstrap riêng và kiểm tra initialize-on-context-refresh. |
| Locator được gọi lại sau khi app đã READY. | POST /actuator/refresh, RefreshEvent hoặc refresh event từ Bus kích hoạt LegacyContextRefresher. | Kiểm tra nguồn phát refresh và xác định đang dùng LegacyContextRefresher hay ConfigDataContextRefresher. |
| Thay property trong bootstrap.yml nhưng không có tác dụng. | File bootstrap không được nạp hoặc bootstrap chưa bật. | Xác minh legacy bootstrap activation và vị trí file. |
| Profile production không được lấy. | Profile không được kích hoạt trong pha đầu hoặc locator không dùng active profiles. | Kiểm tra spring.profiles.active, Environment và pha fetch thứ hai. |
| Startup chậm do locator. | Network call không có timeout hoặc retry quá lớn. | Đặt connect/read timeout, retry budget và metric duration. |
| Locator gây duplicate database rows. | locate() có side effect và được gọi lại. | Chuyển sang read-only/idempotent operation; side effect dùng lifecycle riêng. |
| Custom config không xuất hiện trong Environment. | Locator trả null/rỗng, PropertySource bị thay thế hoặc thứ tự precedence không đúng. | Log source name/key count và inspect property source order trong test. |

## 13. Quy trình chẩn đoán theo thứ tự

1. **Xác định version.** Ghi Spring Boot version và Spring Cloud release train/BOM đang chạy.
2. **Xác định cơ chế.** Kiểm tra `spring.config.import`, bootstrap starter và `spring.cloud.bootstrap.enabled`.
3. **Xác định số context.** Ghi parent/child context ID và số lần SpringApplication được khởi tạo.
4. **Đo từng lần locate.** Ghi application name, active profiles và timestamp.
5. **Phân biệt request và method call.** Thêm request ID trong HTTP client của locator.
6. **Kiểm tra property source.** Ghi tên source và key count, không ghi values.
7. **Kiểm tra registration.** Xác minh spring.factories và package component scan.
8. **Kiểm tra timing.** Nếu cần bootstrap phase sớm, đánh giá initialize-on-context-refresh trong bootstrap config.
9. **Kiểm tra order.** Xác định @Order và property source precedence.
10. **Kiểm thử lại.** Chạy unit test, integration test hai pha và context hierarchy nếu ứng dụng có dùng.

## 14. Nguyên tắc thiết kế và vận hành

1. **Coi locate là thao tác có thể lặp.** Không giả định chỉ được gọi một lần.
2. **Tách fetch theo profile.** Lần đầu có thể không có profile; lần sau có thể có profile đã kích hoạt.
3. **Trả đầy đủ cấu hình hiệu lực.** Pha sau cần giữ base values và bổ sung profile overrides.
4. **Giữ locator read-only.** Không ghi database, phát message hoặc đăng ký service trong locate.
5. **Đặt timeout cho remote source.** Không để bootstrap treo vô hạn vì một config endpoint.
6. **Giới hạn retry.** Phân biệt lỗi tạm thời với credential/profile/label sai.
7. **Dùng cache có key đầy đủ.** Application, profile, label và tenant phải tham gia cache key khi ảnh hưởng kết quả.
8. **Giữ bootstrap configuration tối giản.** Chỉ chứa thông tin cần để tìm nguồn cấu hình.
9. **Không phụ thuộc main context bean.** Bootstrap chạy trước phần lớn bean nghiệp vụ.
10. **Đăng ký đúng một nơi.** Tránh vừa component scan vừa bootstrap registration.
11. **Đặt @Order có chủ đích.** Kiểm thử xung đột key và property source precedence.
12. **Phân biệt Config Data với bootstrap.** Hai cơ chế có lifecycle và cách extension khác nhau.
13. **Ghi log an toàn.** Chỉ log app/profile/context/source metadata.
14. **Đối chiếu release train.** Thời điểm gọi và behavior có thể thay đổi giữa các dòng Spring Cloud.
15. **Test cả startup và context hierarchy.** Unit test locator không đủ để chứng minh lifecycle.
16. **Đo thời gian fetch.** Theo dõi startup duration, số outbound request và retry count.

## 15. Checklist hoàn thành

- [ ] Giải thích được vai trò của PropertySourceLocator.
- [ ] Phân biệt bootstrap context và main application context.
- [ ] Hiểu hai pha fetch profile-aware trong các release train hiện đại.
- [ ] Phân biệt PropertySourceLocator với Config Data loader.
- [ ] Biết ý nghĩa của spring.cloud.config.initialize-on-context-refresh.
- [ ] Đặt bootstrap properties ở đúng file và đúng thời điểm.
- [ ] Kiểm tra spring-cloud-starter-bootstrap hoặc spring.cloud.bootstrap.enabled.
- [ ] Đăng ký BootstrapConfiguration trong META-INF/spring.factories.
- [ ] Không để bootstrap configuration bị component scan.
- [ ] Đọc application name và active profiles từ Environment.
- [ ] Trả base properties và profile-specific properties đầy đủ.
- [ ] Thiết kế locator idempotent và không có side effect.
- [ ] Đặt timeout/retry cho remote fetch.
- [ ] Dùng @Order khi có nhiều locator.
- [ ] Kiểm tra property source names và precedence.
- [ ] Phân biệt nhiều context với nhiều lần locate trong cùng context.
- [ ] Phân biệt method invocation với HTTP retry.
- [ ] Kiểm thử unit test cho profile và application name.
- [ ] Kiểm thử integration test cho bootstrap lifecycle.
- [ ] Kiểm tra không cấu hình đồng thời Config Data và legacy bootstrap ngoài chủ đích.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, context hierarchy, custom PropertySourceLocator và hai pha gọi theo profile.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): default và ý nghĩa của spring.cloud.config.initialize-on-context-refresh.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, Config First Bootstrap và nhiều request khi resolve default/active profiles.
- [ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java): refreshEnvironment, updateEnvironment và việc phát EnvironmentChangeEvent.
- [RefreshAutoConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/autoconfigure/RefreshAutoConfiguration.java): lựa chọn LegacyContextRefresher khi bootstrap bật và ConfigDataContextRefresher khi bootstrap tắt.
- [PropertySourceLocator API](https://www.javadoc.io/doc/org.springframework.cloud/spring-cloud-context/latest/org/springframework/cloud/bootstrap/config/PropertySourceLocator.html): contract locate, locateCollection và khả năng trả null khi không có property source.
- [PropertySourceBootstrapConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/bootstrap/config/PropertySourceBootstrapConfiguration.java): cách sắp xếp locator, gọi locateCollection, thêm property source và xử lý ContextRefreshedEvent.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data loading và cách mở rộng nguồn cấu hình khi không dùng legacy bootstrap.

Khi thấy PropertySourceLocator được gọi lặp, trước tiên hãy xác định profile và context của từng lần gọi. Hai pha fetch có thể là behavior dự kiến; lỗi thực sự thường nằm ở việc locator có side effect, cache thiếu profile key, cấu hình đồng thời hai cơ chế nạp config hoặc bootstrap configuration được đăng ký ở nhiều context ngoài ý muốn.
