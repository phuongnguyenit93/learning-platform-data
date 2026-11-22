# Giới hạn YAML, tài liệu nhiều phần và thời điểm của @PropertySource

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Mở rộng Environment

## 1. Bài toán: cùng là cấu hình, nhưng không phải cách nạp nào cũng tương đương

Spring Boot cho phép đưa cấu hình vào ứng dụng qua nhiều nguồn: file `application.properties`, `application.yml`, biến môi trường, Java system properties, command-line arguments, `SPRING_APPLICATION_JSON`, các file import và nguồn tự định nghĩa. Khi mới học, có thể thấy annotation `@PropertySource` và nghĩ rằng chỉ cần trỏ nó tới một tệp bất kỳ là Spring Boot sẽ nạp tệp ấy giống `application.yml`.

Đây là một nhầm lẫn dễ dẫn tới lỗi trong môi trường thực tế.

Ví dụ:

~~~java
@Configuration
@PropertySource("classpath:extra.yml")
public class ExtraConfiguration {}
~~~

Người viết có thể mong `extra.yml` được xử lý như file cấu hình YAML của Spring Boot, bao gồm tài liệu nhiều phần, điều kiện profile và thứ tự ưu tiên. Nhưng `@PropertySource` là cơ chế của **Spring Framework** để thêm `PropertySource` vào `Environment`, và nó có những giới hạn khác với **Config Data API** của Spring Boot.

Ba vấn đề cần phân biệt:

1. **Định dạng:** `@PropertySource` mặc định không có cơ chế đọc YAML tương đương `application.yml`.
2. **Tài liệu nhiều phần:** cú pháp phân tách các document và kích hoạt document theo profile không tự được `@PropertySource` xử lý như Config Data.
3. **Thời điểm:** `@PropertySource` được xử lý khi ApplicationContext đang được làm mới; một số thuộc tính Spring Boot cần được đọc **trước** thời điểm đó nên không thể trông chờ nó tác động.

Ba giới hạn trên không có nghĩa `@PropertySource` vô dụng. Nó vẫn phù hợp khi bạn muốn đưa một tệp `.properties` đơn giản vào Spring `Environment` để sử dụng cho các bean được khởi tạo ở giai đoạn thích hợp. Điều quan trọng là chọn đúng công cụ cho đúng yêu cầu.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa `@PropertySource` của Spring Framework và cơ chế Config Data của Spring Boot.
- Nạp một tệp `.properties` đơn giản bằng `@PropertySource`.
- Hiểu vì sao `@PropertySource("classpath:extra.yml")` không tương đương với nạp một YAML file bằng Boot.
- Viết `PropertySourceFactory` cho YAML trong trường hợp có lý do đặc biệt, và hiểu giới hạn của giải pháp đó.
- Đọc cấu hình YAML nhiều document, dấu `---`, `spring.config.activate.on-profile` và thứ tự override.
- Nhận biết cơ chế nhiều document của file `.properties` và lý do `@PropertySource` không phải cách nạp phù hợp.
- Phân biệt những property có thể ảnh hưởng tới bean ở giai đoạn refresh với những property cần được xác định rất sớm, ví dụ `logging.*`, `spring.main.*` hoặc config-data locations.
- Dùng `spring.config.import`, `spring.config.additional-location` và biến môi trường/CLI để thay thế các trường hợp vốn không phù hợp với `@PropertySource`.
- Chẩn đoán cấu hình bị bỏ qua, active profile không như dự kiến và kết quả bind khác giữa local và production.

## 2. Nền tảng: Environment chứa các PropertySource theo thứ tự ưu tiên

Spring Framework cung cấp `Environment`, trong đó `PropertySources` là tập nguồn chứa các cặp key/value. Một property có thể được khai báo ở nhiều nguồn, và **thứ tự ưu tiên** quyết định giá trị có hiệu lực.

Sơ đồ khái quát:

~~~text
command-line arguments
SPRING_APPLICATION_JSON
Java system properties
OS environment variables
Config Data: application.yml, imports, profiles ...
@PropertySource từ @Configuration
default properties
                 |
                 v
          Spring Environment
                 |
                 v
        Binder / @Value / lookup
                 |
                 v
             Spring beans
~~~

Thứ tự trong hình có tính minh họa với những nguồn thường gặp, không liệt kê toàn bộ loại PropertySource của Spring Boot. Trong môi trường Servlet, test hoặc cấu hình tùy chỉnh sẽ có thêm các nguồn khác. Ở thứ tự mặc định của Boot, **config data thường ưu tiên hơn `@PropertySource`**, và command-line properties thường có ưu tiên cao hơn config data.

Ví dụ, nếu `@PropertySource` cung cấp:

~~~properties
catalog.client.timeout=10s
~~~

nhưng `application.yml` có:

~~~yaml
catalog:
  client:
    timeout: 3s
~~~

thì trong thứ tự mặc định, giá trị từ Config Data có thể thắng nguồn `@PropertySource`. Không nên kết luận rằng annotation xuất hiện “sau” trong code sẽ luôn ghi đè file application.

### 2.1. PropertySource khác configuration file

`PropertySource` là một nguồn key/value đã được đưa vào `Environment`.

File cấu hình là **một phương tiện chứa dữ liệu**. Để file trở thành PropertySource, phải có loader hiểu format đó, có chính sách về nhiều document, thứ tự và vòng đời khởi động.

Các file `application.yml` và `application.properties` được Boot xử lý bởi cơ chế Config Data. Annotation `@PropertySource` có đường xử lý khác. Sự khác nhau này giải thích vì sao hai cách dùng cùng `Environment` nhưng không có đầy đủ tính năng như nhau.

### 2.2. Đừng nhầm với @ConfigurationProperties

- `@PropertySource`: thêm nguồn property vào `Environment`.
- `@ConfigurationProperties`: bind những property đã có trong `Environment` vào Java object có kiểu.
- `@Value`: chèn một giá trị/biểu thức trong phạm vi một bean.
- `spring.config.import`: yêu cầu Spring Boot nạp bổ sung Config Data trong giai đoạn phù hợp.

Có thể kết hợp `@PropertySource` với `@ConfigurationProperties` cho một tệp properties đơn giản, nhưng chúng không thay thế vai trò của nhau.

## 3. Trường hợp @PropertySource làm tốt: một tệp .properties thông thường

Tệp `src/main/resources/legacy-feature.properties`:

~~~properties
legacy.feature.enabled=true
legacy.feature.timeout=5s
legacy.feature.banner=Hello from properties
~~~

Class đăng ký:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy-feature.properties")
public class LegacyFeatureConfiguration {}
~~~

Một bean khác có thể đọc:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class LegacyFeatureReader {

    private final boolean enabled;
    private final String banner;

    public LegacyFeatureReader(
            @Value("${legacy.feature.enabled:false}") boolean enabled,
            @Value("${legacy.feature.banner:Welcome}") String banner) {
        this.enabled = enabled;
        this.banner = banner;
    }

    public boolean enabled() {
        return enabled;
    }

    public String banner() {
        return banner;
    }
}
~~~

Khi tệp được tìm thấy, annotation được xử lý và không có nguồn cao hơn ghi đè key, bean có thể nhận các giá trị từ `legacy-feature.properties`.

### 3.1. Có thể gắn @PropertySource lên class @Configuration

Annotation thường đặt trên class `@Configuration`, nơi Spring xử lý metadata cấu hình trong quá trình tạo context.

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(value = "classpath:legacy-feature.properties")
class LegacyConfig {}
~~~

Không nên đặt annotation tùy ý lên một Java class không được đưa vào quá trình xử lý configuration của Spring rồi kỳ vọng nó luôn hoạt động.

### 3.2. Tệp tùy chọn

Khi không bắt buộc có file:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "classpath:optional-feature.properties",
    ignoreResourceNotFound = true
)
class OptionalFeatureConfig {}
~~~

`ignoreResourceNotFound=true` cho phép bỏ qua trường hợp resource không tìm thấy. Tuy nhiên, **file không tồn tại** khác **file tồn tại nhưng nội dung sai định dạng**. Không dùng tùy chọn này như một cách bỏ qua tất cả lỗi cấu hình.

Nếu một file chứa thuộc tính quan trọng, việc cho phép thiếu nó có thể làm lỗi triển khai bị che giấu. Cần cân nhắc mức độ bắt buộc.

### 3.3. Dùng placeholder trong đường dẫn resource

Có thể tham chiếu một property đã tồn tại khi xử lý location:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:/config/${app.config.region}.properties")
class RegionPropertiesConfiguration {}
~~~

Ý tưởng: Spring giải quyết `app.config.region` từ những nguồn đã có để tạo đường dẫn. Điều này **không** có nghĩa `@PropertySource` được phép tự quyết định mọi profile hoặc nguồn config-data từ một property được nạp sau. Nếu placeholder của resource location chưa có ở thời điểm xử lý, cần cấp giá trị sớm qua nguồn phù hợp.

## 4. Giới hạn thứ nhất: @PropertySource không đọc YAML mặc định như Boot

Cấu hình YAML thông thường:

~~~yaml
demo:
  service:
    endpoint: "https://example.test"
    enabled: true
    timeout: 3s
~~~

Nếu viết:

~~~java
@Configuration
@PropertySource("classpath:custom.yml")
class YamlConfig {}
~~~

đây **không phải** con đường mặc định được Spring Boot khuyến nghị để nạp YAML. `@PropertySource` sử dụng factory/loader thông thường của Spring Framework cho dạng properties, không tự kích hoạt tất cả cách diễn giải của `YamlPropertySourceLoader` và Config Data.

Tùy implementation và nội dung, YAML có thể bị đọc không đúng thành các property dòng văn bản, không được flatten thành `demo.service.endpoint` như kỳ vọng, hoặc gây lỗi. Vì vậy, không nên diễn đạt đơn giản rằng “YAML lúc nào cũng làm JVM crash”; vấn đề chính là **không có hợp đồng đọc YAML đúng chuẩn thông qua factory mặc định**.

### 4.1. Vì sao YAML cần một loader riêng?

Properties file:

~~~properties
demo.service.endpoint=https://example.test
demo.service.enabled=true
demo.service.timeout=3s
~~~

YAML:

~~~yaml
demo:
  service:
    endpoint: "https://example.test"
    enabled: true
    timeout: 3s
~~~

YAML có object lồng nhau, list, scalar theo cú pháp YAML và nhiều document trong cùng file. Để đưa vào `Environment`, loader cần hiểu cấu trúc, flatten các đường dẫn property và thực hiện quy tắc riêng với các document.

Một parser dành cho Java `.properties` không thể được coi là YAML parser chỉ vì tên file kết thúc bằng `.yml` hay `.yaml`.

### 4.2. Khác biệt với application.yml

Spring Boot có cơ chế Config Data tự động xem xét các file `application.yml`, `application.yaml`, `application.properties` ở các vị trí được hỗ trợ. Cơ chế này hiểu YAML, profile-specific files, YAML document separators và thông tin activation theo quy tắc Boot.

Do đó, **nếu nội dung cần vận hành như cấu hình Boot tiêu chuẩn**, lựa chọn thường đúng hơn là đưa file vào cơ chế Config Data, không gắn `@PropertySource` lên file YAML.

### 4.3. YAML không chỉ là “properties có xuống dòng đẹp hơn”

Ví dụ YAML list:

~~~yaml
demo:
  regions:
    - ap-southeast-1
    - ap-northeast-1
~~~

Loader cần biết cách ánh xạ các phần tử thành dữ liệu binder có thể hiểu, ví dụ những property indexed. Đối với một map có key đặc biệt, còn có quy tắc giữ nguyên key. Dùng một loader không hỗ trợ đúng YAML có thể làm mất cấu trúc hoặc gây kết quả khác biệt giữa file và Java model.

## 5. Có thể viết PropertySourceFactory cho YAML, nhưng phải hiểu giới hạn

Trong trường hợp thực sự cần tích hợp một file YAML riêng qua annotation, Spring Framework cho phép cung cấp `factory` trong `@PropertySource`.

Ví dụ sau là minh họa một factory dành cho YAML **đơn giản**, không nhằm mô phỏng mọi semantics Config Data của Spring Boot.

~~~java
package com.example.config;

import java.io.IOException;
import java.util.Properties;

import org.springframework.beans.factory.config.YamlPropertiesFactoryBean;
import org.springframework.core.env.PropertiesPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.core.io.support.PropertySourceFactory;

public class SimpleYamlPropertySourceFactory
        implements PropertySourceFactory {

    @Override
    public PropertySource<?> createPropertySource(
            String name, EncodedResource resource) throws IOException {

        YamlPropertiesFactoryBean yaml = new YamlPropertiesFactoryBean();
        yaml.setResources(resource.getResource());
        yaml.afterPropertiesSet();

        Properties properties = yaml.getObject();
        if (properties == null) {
            throw new IllegalStateException("Không thể đọc YAML resource");
        }

        String sourceName = name != null
                ? name : resource.getResource().getDescription();

        return new PropertiesPropertySource(sourceName, properties);
    }
}
~~~

Cấu hình dùng factory:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "classpath:custom-settings.yml",
    factory = SimpleYamlPropertySourceFactory.class
)
public class CustomYamlConfiguration {}
~~~

File `custom-settings.yml`:

~~~yaml
demo:
  service:
    endpoint: "https://api.example.test"
    timeout: 3s
~~~

### 5.1. Factory giải quyết vấn đề nào?

Nó giải quyết yêu cầu **đọc cú pháp YAML và chuyển nó thành một PropertiesPropertySource** trong trường hợp đơn giản, để các key có thể được tra cứu từ `Environment`.

Nó **không** làm annotation trở thành Spring Boot Config Data API:

- Không tự thay đổi thời điểm `@PropertySource` được xử lý.
- Không mặc định áp dụng cùng chính sách profile activation của Boot.
- Không tự áp dụng thứ tự import/document location của Config Data.
- Không có cam kết mô phỏng mọi cú pháp nhiều document.
- Không tự quyết định nguồn precedence tương đương một file `application.yml` ở location ngoài JAR.
- Không biến các thuộc tính được đọc quá muộn thành thuộc tính bootstrap.

### 5.2. YamlPropertiesFactoryBean không phải Spring Boot ConfigDataImporter

`YamlPropertiesFactoryBean` của Spring Framework giúp biến YAML thành properties. Spring Boot còn có các lớp xử lý YAML trong pipeline Config Data, nhưng việc sử dụng một parser YAML **không tự mang theo cơ chế nạp config data, chọn document theo profile và ghi đè theo source**.

Nếu nhóm cần dùng custom factory, nên giới hạn phạm vi ở file YAML đơn giản và test rõ semantics khi có nested properties hoặc một số cấu trúc phức tạp.

### 5.3. Khi nào không nên viết factory?

Không nên tự thêm factory chỉ vì muốn:

- Nạp file YAML ngoài JAR.
- Có cấu hình theo active profile.
- Kết hợp nhiều document YAML.
- Điều chỉnh thứ tự override giữa file đóng gói và file externalized.
- Dùng `spring.config.import` hoặc optional imports.

Những mục tiêu này thường có cơ chế Config Data phù hợp hơn và ít rủi ro hơn custom factory.

## 6. Giới hạn thứ hai: tệp cấu hình nhiều document

Spring Boot hỗ trợ các **multi-document configuration files**. Một file có thể chứa nhiều “tài liệu logic”, mỗi tài liệu thêm một nhóm property source hoặc những giá trị với điều kiện riêng.

### 6.1. YAML dùng dấu ---

Ví dụ `application.yml`:

~~~yaml
app:
  message: "default"
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  message: "production"
  timeout: 2s
~~~

Document đầu có hiệu lực trong ví dụ thông thường. Document thứ hai chỉ tham gia khi profile `prod` đang active theo cơ chế Boot. Khi `prod` active, `app.message` có thể thành `production` và `app.timeout` là `2s` vì document sau đang hoạt động ghi đè các key trùng của document trước.

Khi `prod` không active, giá trị từ document đầu được giữ nếu không có nguồn khác ưu tiên cao hơn.

### 6.2. Document order và property precedence

Trong cùng file nhiều document, những document được chấp nhận theo điều kiện của Boot thường được xử lý theo thứ tự; tài liệu sau có thể ghi đè giá trị trùng của tài liệu trước.

Nhưng **thứ tự giữa các document trong một file** không thay thế precedence giữa các file, import locations, OS environment và CLI. Ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.timeout=1s
~~~

Khi command-line properties có hiệu lực mặc định, `--app.timeout=1s` thường thắng giá trị `2s` từ YAML document theo profile.

### 6.3. Multi-document không chỉ có YAML

Spring Boot cũng hỗ trợ phân tách các tài liệu trong file `application.properties` bằng marker được quy định, thường là một dòng riêng `#---` hoặc `!---`.

Ví dụ:

~~~properties
app.message=default
app.timeout=5s

#---
spring.config.activate.on-profile=prod
app.message=production
app.timeout=2s
~~~

Có quy tắc cú pháp đối với dòng separator và các dòng comment kề bên. Khi dùng thực tế, hãy tuân theo đúng định dạng separator của tài liệu Spring Boot cho phiên bản đang sử dụng; không coi mọi dòng comment có dấu gạch ngang đều là separator hợp lệ.

### 6.4. @PropertySource không phải đường nạp nhiều document phù hợp

Một điểm được Spring Boot cảnh báo trong tài liệu externalized configuration: **multi-document property files không thể được nạp theo cùng semantics qua `@PropertySource` hoặc `@TestPropertySource`**.

Với file `.properties` truyền thống, marker `#---` có thể chỉ bị hiểu là comment thông thường, không được xem là bộ phân tách các Config Data document. Các key trùng có thể bị xử lý theo hành vi của properties parser thay vì profile activation và thứ tự document của Boot.

Với YAML, một factory tự viết có thể parse nhiều document theo một cách riêng nhưng vẫn không tự có semantics `spring.config.activate.on-profile`. Do đó, nếu mục tiêu là multi-document config của Spring Boot, hãy dùng pipeline **Config Data**.

## 7. Điều kiện kích hoạt document và profile

### 7.1. spring.config.activate.on-profile

Một YAML document có thể đặt:

~~~yaml
spring:
  config:
    activate:
      on-profile: dev
~~~

Nghĩa là document đó chỉ tham gia khi expression/profile activation khớp. Đây là một phần của cơ chế Config Data của Spring Boot.

Ví dụ:

~~~yaml
app:
  feature:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

app:
  feature:
    enabled: true
~~~

Khi `dev` active, `app.feature.enabled` có thể thành `true`; khi `dev` không active, giá trị vẫn là `false` nếu không có nguồn cao hơn ghi đè.

### 7.2. spring.config.activate.on-cloud-platform

Một document có thể được kích hoạt dựa trên cloud platform theo các giá trị hỗ trợ bởi Spring Boot. Cơ chế activation này cũng thuộc pipeline Config Data, không phải điều kiện chung mà mọi YAML parser tự hiểu.

Không nên giả định một `YamlPropertiesFactoryBean` được gọi thủ công sẽ áp dụng toàn bộ quy tắc activation cloud platform của Spring Boot.

### 7.3. Không đặt spring.profiles.active tùy ý trong activated document

Các property kích hoạt profile như `spring.profiles.active` có quy tắc nạp rất sớm. Spring Boot giới hạn việc sử dụng chúng trong những tài liệu đã mang điều kiện activation/profile-specific. Không nên đặt `spring.profiles.active` trong một document được kích hoạt bằng `spring.config.activate.on-profile` rồi mong nó kích hoạt thêm các document khác.

Nên chọn active profile thông qua environment, CLI hoặc nguồn cấu hình hợp lệ trong giai đoạn bootstrap. Sau đó Boot quyết định document nào tham gia.

### 7.4. Chọn profile khác với chọn property source

`spring.profiles.active=prod` yêu cầu Spring Boot chọn profile trong cơ chế khởi động thích hợp. Nó không chỉ là một property text tùy ý mà bất cứ nguồn nào thêm muộn cũng có thể dùng để làm Boot quay lại nạp toàn bộ file profile-specific từ đầu.

Đây là sự kết hợp giữa **thứ tự xử lý** và **thời điểm** sẽ được làm rõ ở phần sau.

## 8. Giới hạn thứ ba: @PropertySource được xử lý quá muộn cho một số property

Spring Boot có nhiều giai đoạn khởi động. Một mô hình khái quát:

~~~text
main(String[] args)
          |
          v
Tạo và chuẩn bị Environment
          |
          v
Đọc command line, OS env, system properties
          |
          v
Config Data: locations, profiles, imports, activation
          |
          v
Một số quyết định bootstrap
  - cấu hình logging sớm
  - spring.main.* và thiết lập ứng dụng
          |
          v
Tạo / refresh ApplicationContext
          |
          v
Xử lý các class @Configuration
  - @PropertySource góp thêm PropertySource
          |
          v
Khởi tạo / bind / inject beans
          |
          v
Ứng dụng chạy
~~~

Sơ đồ giúp hình dung, không thay thế mô tả toàn bộ event listener, initializer và hook của Spring Boot. **Cốt lõi:** `@PropertySource` trên `@Configuration` thường được thêm vào `Environment` khi ApplicationContext đang được làm mới, trong khi Boot đã cần quyết định một số giá trị trước lúc đó.

### 8.1. Logging configuration được đọc sớm

Ví dụ:

~~~properties
# late-logging.properties
logging.level.root=DEBUG
logging.file.name=service.log
~~~

Nếu file này chỉ được đưa vào bằng:

~~~java
@Configuration
@PropertySource("classpath:late-logging.properties")
class LoggingPropertiesConfiguration {}
~~~

không nên tin rằng Boot sẽ dùng nó để thiết lập logging bootstrap đầy đủ. Tài liệu Spring Boot nêu rõ những property như `logging.*` được đọc trước khi refresh context, nên `@PropertySource` có thể là **quá muộn** để ảnh hưởng tới các thiết lập đó.

Có thể một vài thành phần hoặc lần truy vấn muộn nhìn thấy giá trị sau khi annotation được xử lý, nhưng việc giá trị xuất hiện trong `Environment` lúc ấy **không chứng minh logging system đã được cấu hình lại**.

Với logging configuration cần áp dụng sớm, dùng `application.yml`/`application.properties`, biến môi trường, Java system property, CLI hoặc cơ chế logging được Boot hỗ trợ.

### 8.2. spring.main.* cũng cần được giải quyết sớm

Ví dụ:

~~~properties
# late-main.properties
spring.main.banner-mode=off
spring.main.lazy-initialization=true
~~~

Không nên chọn `@PropertySource` như nguồn duy nhất để kiểm soát những thuộc tính quyết định quá trình tạo SpringApplication và khởi tạo context. Các giá trị `spring.main.*` được dùng ở giai đoạn sớm hơn quá trình xử lý annotation ở refresh.

Ví dụ cần tắt banner nên dùng:

~~~bash
java -jar app.jar --spring.main.banner-mode=off
~~~

hoặc trong một Config Data file được Boot nạp sớm:

~~~yaml
spring:
  main:
    banner-mode: off
~~~

### 8.3. spring.config.location / additional-location / import

Các khóa điều khiển nơi tìm và nhập Config Data phải được hiểu đúng thời điểm. Điển hình:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`
- `spring.config.import` trong tài liệu config data đang được xử lý

Không nên đặt các khóa dùng để chỉ vị trí tìm config data **chỉ trong một file được @PropertySource đưa vào muộn** rồi kỳ vọng Boot quay ngược thời gian để tìm thêm file khi giai đoạn config data đã qua.

Đặc biệt `spring.config.location` và `spring.config.additional-location` được dùng để quyết định các vị trí ngay khi Boot chuẩn bị môi trường. Chúng thường cần đến từ các nguồn sớm như OS environment, system properties hoặc CLI.

`spring.config.import` được sử dụng **bên trong một tài liệu Config Data được nạp**, để loader có thể theo import đúng giai đoạn. Viết nó trong một file properties thuần chỉ được gắn vào Environment bằng `@PropertySource` không có nghĩa cơ chế import sẽ được kích hoạt lại.

### 8.4. spring.profiles.active và profile-specific files

Profile được Boot dùng để lựa chọn tài liệu Config Data. Nếu một file properties chỉ xuất hiện sau khi `@PropertySource` xử lý mới cung cấp `spring.profiles.active=prod`, không nên trông chờ Boot tải `application-prod.yml` trở về từ giai đoạn trước.

Khi muốn chọn profile cho một lần chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

hoặc môi trường:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar
~~~

Trong triển khai thực tế, đảm bảo tiến trình Java đúng nhận được biến môi trường và không có nguồn ưu tiên cao hơn ghi đè nó.

## 9. Dùng Config Data cho YAML bên ngoài JAR

Giả sử có file:

~~~text
project/
├── app.jar
└── config/
    └── application.yml
~~~

Nếu chạy từ đúng working directory và không đổi các cơ chế tìm file mặc định, Spring Boot thường tìm config data ở các location như:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

`file:./` là đường dẫn tương đối với **working directory**, không tự động là thư mục chứa JAR. Điều này quan trọng khi chạy trong Docker, systemd hoặc IDE.

### 9.1. Ví dụ bên ngoài JAR

File `./config/application.yml`:

~~~yaml
catalog:
  client:
    endpoint: "https://internal.example.test"
    timeout: 2s
~~~

Nếu file này được Boot nạp theo search locations mặc định, các khóa có thể ưu tiên hơn những giá trị tương ứng đóng gói trong JAR, theo cơ chế Config Data.

Không cần thêm:

~~~java
@PropertySource("file:./config/application.yml")
~~~

để làm điều đó. Việc bỏ qua annotation có lợi vì Boot xử lý YAML, profile activation, precedence và location semantics trong pipeline được thiết kế cho file application config.

### 9.2. spring.config.location

Có thể chỉ định rõ vị trí:

~~~bash
java -jar app.jar \
  --spring.config.location=optional:file:./deployment/
~~~

Cần cẩn thận: `spring.config.location` **thay thế** các vị trí tìm kiếm mặc định, nếu không khai báo kèm những vị trí bạn vẫn cần. Dùng nó có thể làm ứng dụng không nạp file mặc định mà bạn tưởng vẫn được nhận.

Prefix `optional:` cho phép bỏ qua trường hợp một location không tồn tại trong những cơ chế hỗ trợ. Nó **không** cho phép bỏ qua nội dung YAML sai hoặc property bắt buộc không hợp lệ.

### 9.3. spring.config.additional-location

Khi muốn giữ search locations mặc định và bổ sung một vị trí khác:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deployment/
~~~

Thông thường cách này phù hợp hơn `spring.config.location` nếu chỉ cần nạp thêm file bên ngoài, vì nó bảo tồn những nơi tìm kiếm gốc và thêm nơi mới có thứ tự ưu tiên theo quy tắc Boot.

### 9.4. Location groups và thứ tự

Khi dùng nhiều location hoặc location groups, thứ tự override có thể phụ thuộc cách nhóm các location. Dấu phân cách và cách Boot xử lý profile-specific files là chi tiết quan trọng của Config Data.

Không nên thay thế nguyên tắc này bằng “file nào ghi sau trong @PropertySource thì luôn thắng”. Với hệ thống có nhiều environment và profile, hãy xác định location group/precedence theo tài liệu Boot và kiểm tra những key thực tế.

## 10. spring.config.import: nhập tệp cấu hình bổ sung đúng giai đoạn

Một ứng dụng có `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment/partner.yml"

partner:
  timeout: 5s
~~~

Và file `./deployment/partner.yml`:

~~~yaml
partner:
  endpoint: "https://partner.example.test"
  timeout: 2s
~~~

Khi Boot nạp document khai báo `spring.config.import`, nó có thể nạp file import cùng trong giai đoạn Config Data. Theo quy tắc import của Boot, file được import có mức ưu tiên phù hợp để các property của import có thể override những property trùng của tài liệu khai báo import. Ví dụ `partner.timeout` có thể nhận `2s`.

### 10.1. Vì sao import khác @PropertySource?

| Tiêu chí | `spring.config.import` | `@PropertySource` |
| --- | --- | --- |
| Giai đoạn xử lý | Config Data processing | Context refresh/configuration class processing |
| YAML mặc định | Có trong định dạng được Boot hỗ trợ | Không mặc định |
| Multi-document activation | Theo quy tắc Config Data | Không tự có |
| Profile-specific variants | Được tích hợp theo quy tắc Boot | Không tương đương |
| Optional location | `optional:` theo quy tắc Boot | `ignoreResourceNotFound` cho resource annotation |
| Dùng cho `logging.*`/`spring.main.*` sớm | Thích hợp hơn | Có thể quá muộn |
| Dùng cho file properties đơn giản thêm muộn | Có thể dùng nhưng không phải lúc nào cần | Có thể thích hợp |

### 10.2. Import không có nghĩa mọi file trên ổ đĩa đều được đọc

Đường dẫn trong import cần đúng với working directory hoặc vị trí resource. Nếu file không tồn tại, tùy khai báo có `optional:` hay không, Boot có thể báo lỗi location hoặc bỏ qua. Nếu file tồn tại nhưng YAML sai, lỗi parser/binding vẫn có thể xuất hiện.

Không nên dùng `optional:` để che giấu một cấu hình **bắt buộc**. Nếu endpoint cần có ở mọi môi trường production, thêm validation trên typed configuration.

### 10.3. Không tự hiểu JSON như Config Data YAML

Một file JSON bất kỳ không nhất thiết được nạp như file application configuration mặc định. `SPRING_APPLICATION_JSON` là một cơ chế riêng để truyền JSON object qua environment/system property/CLI. Không nên đồng nhất “import một file” với “parse mọi định dạng thành config” nếu không có loader phù hợp.

## 11. Phân biệt @PropertySource và PropertySourceFactory với Config Data API

### 11.1. @PropertySource

- Tuyên bố thêm một resource (thường là `.properties`) vào `Environment`.
- Gắn với vòng đời xử lý `@Configuration`.
- Có factory tùy chỉnh để thay đổi cách đọc resource.
- Không phải nơi phù hợp cho bootstrap configuration và multi-document Boot semantics.

### 11.2. PropertySourceFactory

- Quyết định cách biến một resource của annotation thành một `PropertySource`.
- Có thể dùng YAML parser và tạo `PropertiesPropertySource`.
- **Không** di chuyển thời điểm annotation được xử lý từ refresh lên config-data bootstrap.
- Không tự có API chọn document theo profile hoặc location groups nếu bạn không tự triển khai.

### 11.3. Spring Boot Config Data

- Xử lý sớm các file application config và imports.
- Có quy tắc profile activation, search locations, profile-specific variants và document ordering.
- Cung cấp giá trị cho nhiều cấu hình cần được biết trước context refresh.
- Là giải pháp nên ưu tiên cho nhu cầu cấu hình externalized theo convention của Spring Boot.

### 11.4. EnvironmentPostProcessor

Khi thật sự cần **tự bổ sung hoặc biến đổi PropertySource trước khi context refresh**, Spring Boot có cơ chế mở rộng ở giai đoạn chuẩn bị `Environment`, chẳng hạn `EnvironmentPostProcessor`.

Ví dụ ý tưởng:

~~~java
package com.example.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;

public class CustomEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        // Thêm hoặc điều chỉnh PropertySource ở giai đoạn Environment.
        // Chọn tên nguồn và thứ tự precedence một cách rõ ràng.
        // Tránh in secret hoặc ghi đè những key không thuộc phạm vi.
    }
}
~~~

Để Spring Boot phát hiện processor cần đăng ký nó theo cơ chế tương ứng của phiên bản (thường dựa trên `META-INF/spring.factories` đối với EnvironmentPostProcessor). **Viết một class implements interface thôi chưa đủ**.

Nếu cần xử lý phức tạp theo Config Data, có API mở rộng Config Data riêng, không nhất thiết chỉ dùng EnvironmentPostProcessor. Việc custom bootstrap tăng chi phí bảo trì, nên chỉ dùng khi Config Data file/import và các nguồn tiêu chuẩn không đáp ứng.

### 11.5. Thứ tự bootstrap của custom processor cũng có giới hạn

Dù `EnvironmentPostProcessor` chạy trước context refresh, không thể giả định nó chạy trước **mọi** xử lý của Spring Boot. Processor khác, logging initialization và Config Data processing có thứ tự được xác định bằng order/registration cụ thể. Nếu một property cần xuất hiện **trước một processor khác**, phải thiết kế thứ tự và kiểm tra theo phiên bản Boot.

Không dùng cơ chế mở rộng như một phép màu sửa được mọi vấn đề “nạp quá muộn”.

## 12. Khi nào @PropertySource vẫn có ích?

Những trường hợp tương đối phù hợp:

1. Một module kế thừa có file `.properties` riêng chứa key cho bean của module.
2. Một thư viện Spring Framework không phụ thuộc nhiều vào Boot Config Data convention.
3. Cấu hình bean nội bộ không ảnh hưởng tới logging hoặc bootstrap.
4. Một resource properties đã được đóng gói và cần được thêm vào `Environment` khi xử lý configuration class.

Ví dụ `feature-flags.properties`:

~~~properties
feature.preview.enabled=false
feature.preview.title=Preview mode
~~~

Trong module:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:feature-flags.properties")
class PreviewFeatureConfiguration {}
~~~

Code đọc:

~~~java
@Component
class PreviewService {

    private final Environment env;

    PreviewService(Environment env) {
        this.env = env;
    }

    boolean enabled() {
        return env.getProperty(
                "feature.preview.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

Đây là một use case dễ hiểu. Nhưng nếu cần thay đổi theo profile, deployment hoặc inject file YAML bên ngoài, nên xem cách chuyển sang `application.yml` hoặc `spring.config.import`.

## 13. Cấu hình XML, .properties và YAML: phân biệt chính xác

### 13.1. File .properties

Dạng key/value:

~~~properties
acme.client.endpoint=https://api.example.test
acme.client.timeout=3s
~~~

`@PropertySource` mặc định xử lý loại này theo cơ chế resource properties phù hợp.

### 13.2. File XML theo định dạng Java Properties

Spring Framework có khả năng tải một số resource XML theo định dạng properties XML qua loader hỗ trợ. Nhưng **không đồng nghĩa mọi file XML tùy ý** đều trở thành PropertySource. Một XML bean definition file và XML properties file là hai loại tài liệu khác nhau.

Khi định nghĩa annotation dùng một resource XML, hãy xác định loader và định dạng có thực sự được hỗ trợ không.

### 13.3. YAML

YAML cần parser/loader hiểu object, list và documents. Boot có hỗ trợ đầy đủ theo Config Data convention, còn `@PropertySource` mặc định không tương đương.

Không nên cho rằng đổi đuôi file `.properties` thành `.yml` là đủ hoặc một factory YAML tối giản tự áp dụng toàn bộ profile rules.

## 14. Các lỗi thường gặp khi kết hợp YAML và @PropertySource

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@PropertySource("classpath:extra.yml")` không bind đúng nested key | Factory mặc định không xử lý YAML theo cách Boot | Dùng Config Data hoặc custom YAML factory có kiểm soát |
| File YAML nhiều document không đổi theo profile | Parser/annotation không có Boot activation semantics | Đưa file vào Config Data |
| `#---` không tạo document mới khi dùng @PropertySource | Dòng separator bị xử lý như comment properties thường | Dùng application config loader Boot |
| `logging.level.root` trong @PropertySource không tác động lúc bootstrap | Annotation xử lý sau khi logging đã được setup | Đưa property vào nguồn sớm |
| `spring.main.banner-mode` trong @PropertySource không hiệu lực | Thiết lập SpringApplication đã được đọc trước | Dùng config data/CLI/env |
| `spring.config.location` trong @PropertySource không làm Boot tìm file mới | Config Data search đã hoàn tất | Cấp location qua nguồn bootstrap sớm |
| Active profile được đặt muộn nhưng file profile không nạp | Profile activation đã được xử lý | Cấp profile qua CLI/env hợp lệ |
| Property trong @PropertySource khác giá trị quan sát | Config Data/OS/CLI có precedence cao hơn | Xem PropertySources thực tế |
| File ngoài JAR không được tìm thấy | Sai working directory/resource location | Kiểm tra `user.dir`, absolute/relative paths |
| Đọc được một phần YAML nhưng mất list/map | Factory flatten có giới hạn hoặc code bind khác | Test schema, dùng loader phù hợp |
| `@PropertySource` class không được xử lý | Class không được đưa vào configuration processing | Import/scan configuration đúng |
| Một file properties bị lặp key | Duplicate key/đường nạp nhiều nguồn | Xem quy tắc precedence và cấu hình nguồn |
| Secret bị lộ khi in Environment | Log toàn bộ value hoặc mở endpoint Actuator không bảo vệ | Giới hạn quyền, masking, không log secrets |

### 14.1. Đừng gộp lỗi nạp file với lỗi binding

Một file có thể được đọc thành công nhưng field Java vẫn null vì:

- Prefix `@ConfigurationProperties` không khớp.
- Property key bị viết sai.
- Source ưu tiên cao hơn override.
- Class properties chưa được đăng ký.
- Nested object không có dữ liệu hoặc có semantics riêng.
- Conversion không nhận kiểu.

Ngược lại, nếu file không được loader nạp đúng, sẽ không có property tương ứng để Binder dùng. Chẩn đoán cần phân biệt hai giai đoạn này.

## 15. Quan sát PropertySources để hiểu nguồn thắng

Với một key **không nhạy cảm**:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.client.timeout";

        System.out.println("Effective: "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Trong trường hợp cụ thể, tên các `PropertySource` có thể phản ánh file Config Data hoặc annotation. Nhưng không nên viết logic nghiệp vụ dựa vào một tên string `source.getName()` cố định.

**Lưu ý:** Một số nguồn (đặc biệt env vars) có cơ chế relaxed binding khi Binder xử lý. Việc `source.getProperty(key)` trả null cho một tên cụ thể không phải bằng chứng chắc chắn rằng không thể bind property tương ứng qua tên biến môi trường. Khi cần, kiểm tra hiệu quả binding và origin metadata được Boot cung cấp.

### 15.1. Actuator và bảo mật

Spring Boot Actuator có các endpoint như `env` và `configprops` giúp chẩn đoán cấu hình trong những môi trường cho phép. Chỉ bật và truy cập có kiểm soát; phải bảo vệ giá trị nhạy cảm, tránh công khai endpoint chứa cấu hình.

Các giá trị như password, API key, signing secret không nên được in trong log, thông báo lỗi hoặc một endpoint public chỉ để debug nguồn property.

## 16. Phương án lựa chọn theo nhu cầu

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Thêm vài key từ file `.properties` nội bộ khi xử lý `@Configuration` | `@PropertySource` |
| Nạp YAML tiêu chuẩn theo profile | Config Data `application.yml`/`application-{profile}.yml` |
| Nạp file YAML riêng ngoài JAR | `spring.config.import` hoặc additional-location |
| Một file YAML nhiều documents với `---` | Boot Config Data loader |
| File `.properties` nhiều documents với `#---` | Boot Config Data loader |
| Điều chỉnh `logging.*` sớm | Config Data, env, JVM property hoặc CLI |
| Điều chỉnh `spring.main.*` | Nguồn sớm như Config Data/env/CLI |
| Chỉ định nơi tìm config data | `spring.config.location`/`additional-location` ở giai đoạn bootstrap |
| Tạo một nguồn property custom rất sớm | `EnvironmentPostProcessor` với order/registration phù hợp |
| Mở rộng loại Config Data chuyên biệt | Config Data API của Spring Boot |
| Bind nhiều key cấu trúc vào Java type | `@ConfigurationProperties` |
| Thêm validation cho cấu hình | `@Validated` và Bean Validation |

### 16.1. Chọn giải pháp đơn giản nhất có đúng semantics

Nếu yêu cầu là “thêm file YAML chứa timeout, endpoint và tài liệu theo profile”, đừng giải quyết bằng cách tạo một YAML factory rồi tự triển khai logic profile và location. Config Data đã được xây dựng cho nhu cầu đó.

Nếu yêu cầu chỉ là “module legacy có một file properties nhỏ”, `@PropertySource` có thể là giải pháp đủ tốt, không cần mang thêm extension Bootstrap phức tạp.

## 17. Kiểm thử: bảo đảm cơ chế nạp thực sự đáp ứng ý đồ

Khi behavior quan trọng, test phải mô phỏng **cơ chế loader thực tế**, không chỉ đọc một file rồi assert cú pháp.

### 17.1. Test @PropertySource với .properties

Tạo `src/test/resources/extra-test.properties`:

~~~properties
demo.greeting=Hello
demo.timeout=5s
~~~

Test config:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:extra-test.properties")
class ExtraTestConfiguration {}
~~~

Với một Spring context kiểm tra class này được xử lý, bạn có thể assert `Environment.getProperty("demo.greeting")` là `Hello`. Đây là test nạp resource và tạo `PropertySource`, không phải test Config Data profile activation.

### 17.2. Test multi-document bằng đúng Spring Boot Config Data

Nếu cần test:

~~~yaml
demo:
  greeting: "default"

---
spring:
  config:
    activate:
      on-profile: test

demo:
  greeting: "from-test-profile"
~~~

đặt YAML trong một config location được Boot nạp và khởi tạo test context với profile `test` active, ví dụ thông qua `@ActiveProfiles("test")` kết hợp Spring Boot test. Kết quả mong đợi là `from-test-profile` nếu không có nguồn ưu tiên cao hơn ghi đè.

Đừng chỉ dùng một ApplicationContextRunner không cấu hình nạp Config Data rồi ngạc nhiên vì tài liệu YAML chưa được đọc. Công cụ test phải thực sự sử dụng pipeline cần kiểm tra.

### 17.3. Test property cần xác định từ sớm

Muốn kiểm tra logging bootstrap hoặc `spring.main.*`, test trực tiếp hành vi của lần chạy Spring Boot với config data/CLI phù hợp, không chỉ assert rằng cuối cùng `Environment` có một property. Một property có mặt **sau refresh** chưa chứng minh nó đã ảnh hưởng tới bootstrap phase.

### 17.4. Test precedence giữa nguồn

`application.yml`:

~~~yaml
demo:
  color: blue
~~~

Một file được nạp bằng `@PropertySource`:

~~~properties
demo.color=red
~~~

Trong thứ tự ưu tiên mặc định, config data có thể thắng nên `demo.color=blue`. Nếu CLI có `--demo.color=green`, giá trị có thể là `green`.

Test cần xác định chính xác các nguồn có mặt, profile đang active và các custom processors đã được cài đặt, tránh giả định rằng môi trường của máy chạy test không có property trùng.

## 18. Bài tập thực hành

### Bài tập A — Một file properties đơn giản

Tạo `src/main/resources/my-extra.properties`:

~~~properties
lesson.message=Hello Extra
lesson.enabled=true
~~~

Tạo `@Configuration` có `@PropertySource("classpath:my-extra.properties")`. Đọc hai key từ `Environment`. Thử xóa file rồi quan sát lỗi nạp, sau đó cân nhắc `ignoreResourceNotFound=true` khi file thật sự tùy chọn.

### Bài tập B — Chuyển sang YAML

Viết `my-extra.yml`:

~~~yaml
lesson:
  message: "Hello YAML"
  enabled: true
~~~

Thử dùng annotation mặc định, quan sát khác biệt so với `.properties`. Sau đó dùng `spring.config.import` qua một Config Data file để nạp YAML đúng cách. Giải thích tại sao hai đường xử lý khác nhau.

### Bài tập C — Custom YAML factory

Cài đặt `SimpleYamlPropertySourceFactory` theo ví dụ mục 5. Dùng một YAML document duy nhất và kiểm tra `lesson.enabled` được đọc. Sau đó thêm document thứ hai có `spring.config.activate.on-profile` và giải thích vì sao kết quả từ factory không nên được suy ra giống Boot Config Data.

### Bài tập D — YAML nhiều document

Tạo `application.yml`:

~~~yaml
lesson:
  mode: default
---
spring:
  config:
    activate:
      on-profile: prod
lesson:
  mode: prod
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Dự đoán `lesson.mode`. Chạy không có profile prod và đối chiếu. Kiểm tra nếu CLI thêm `--lesson.mode=from-cli` thì nguồn nào thắng.

### Bài tập E — Properties nhiều document

Tạo `application.properties` với separator `#---` và một document `spring.config.activate.on-profile=prod`. Để Boot nạp theo Config Data. Sau đó thử cùng file qua `@PropertySource` và giải thích vì sao không thể trông đợi profile activation tương tự.

### Bài tập F — Thời điểm logging

Thêm `logging.level.root=DEBUG` vào một file chỉ được nạp bằng `@PropertySource`. So sánh với việc đặt property trong `application.yml` hoặc CLI. Quan sát logging bootstrap để hiểu khác biệt giữa **property hiện diện ở Environment cuối cùng** và **property đã có tại lúc logging được cấu hình**.

### Bài tập G — File ngoài JAR

Đặt `./config/application.yml` cạnh một thư mục chạy thử, rồi khởi động từ working directory phù hợp. Thử thay đổi working directory và đối chiếu kết quả. Giải thích vì sao `file:./config/` không tự là thư mục chứa JAR.

### Bài tập H — Import optional

Trong `application.yml` đặt:

~~~yaml
spring:
  config:
    import: "optional:file:./extra.yml"
~~~

Chạy khi file thiếu và khi file tồn tại. Sau đó cố ý viết YAML sai trong file tồn tại. Giải thích khác biệt giữa optional location và cấu hình sai cú pháp.

### Bài tập I — Chọn công cụ

Với từng yêu cầu, chọn `@PropertySource`, Config Data hoặc `EnvironmentPostProcessor`:

1. Thêm một file `.properties` chứa nhãn cho một module legacy.
2. Dùng YAML có ba document active theo profile.
3. Thay giá trị `spring.main.banner-mode`.
4. Bổ sung một vị trí config data ngoài JAR.
5. Cấp property từ một hệ thống tùy chỉnh trước context refresh mà Boot chưa có loader.
6. Bind cấu hình HTTP client thành một record có kiểu và validation.

Giải thích vì sao không phải một annotation đáp ứng tối ưu mọi trường hợp.

## 19. Checklist khi điều tra cấu hình không có tác dụng

- [ ] Xác nhận tên key và prefix chính xác.
- [ ] Xác nhận resource có tồn tại ở classpath/file path thực tế.
- [ ] Kiểm tra file là `.properties` hay YAML và loader có hiểu định dạng không.
- [ ] Kiểm tra nhu cầu nhiều document, separator và profile activation.
- [ ] Xác định ứng dụng đang dùng `@PropertySource` hay Config Data.
- [ ] Xác định active profile đã được cấp từ nguồn sớm chưa.
- [ ] Kiểm tra working directory với đường dẫn `file:./...`.
- [ ] Kiểm tra `spring.config.location` có vô tình thay thế search locations mặc định không.
- [ ] Kiểm tra `spring.config.import` có ở trong tài liệu Config Data được Boot xử lý không.
- [ ] Phân biệt property được thêm muộn với property cần thiết trong bootstrap.
- [ ] Xem precedence của config data, env, system properties, JSON và CLI.
- [ ] Phân biệt nguồn file được nạp và việc bean `@ConfigurationProperties` đã đăng ký/bind chưa.
- [ ] Không in secret khi xem Environment hoặc Actuator.
- [ ] Có test đúng đường nạp và profile mà production thực sự sử dụng.

## 20. Ghi nhớ

1. **`@PropertySource` không tương đương với Spring Boot Config Data.** Nó thêm nguồn property khi xử lý `@Configuration`, không tự thực hiện toàn bộ quy tắc nạp application configuration.
2. **YAML không được `@PropertySource` hỗ trợ mặc định như `application.yml`.** Có thể tạo `PropertySourceFactory` riêng cho YAML đơn giản, nhưng đó không biến nó thành Config Data loader.
3. **Multi-document YAML với `---` và multi-document properties với `#---`/`!---`** có semantics do Spring Boot Config Data xử lý; không nên nạp các tài liệu này qua `@PropertySource` hay `@TestPropertySource` nếu cần activation theo document.
4. **Thời điểm xử lý quyết định kết quả:** `@PropertySource` được thêm trong context refresh; `logging.*` và `spring.main.*` có thể đã được đọc trước đó.
5. **Các khóa chọn config-data locations và profile** cần được cấp ở nguồn thích hợp trong giai đoạn đủ sớm, thay vì trông chờ một resource annotation muộn kích hoạt lại pipeline.
6. Với YAML/profile/import/external file, thường ưu tiên **`application.yml`, `spring.config.import`, `spring.config.location` hoặc `spring.config.additional-location`**.
7. `@ConfigurationProperties` là cơ chế bind dữ liệu đã nạp, không phải loader file; Bean Validation là lớp kiểm tra hợp lệ riêng.
8. **Property cuối cùng nằm trong Environment chưa chắc đã ảnh hưởng tới giai đoạn bootstrap.** Muốn xác nhận một property sớm, test hành vi thực sự khi startup.
9. Chọn cơ chế mở rộng như `EnvironmentPostProcessor` hoặc Config Data API chỉ khi những nguồn cấu hình chuẩn không đáp ứng, và kiểm soát thứ tự xử lý rõ ràng.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn cấu hình, precedence, `@PropertySource` và giới hạn thời điểm.
- [Spring Boot Reference — Multi-Document Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.multi-document): YAML `---`, properties separators và hạn chế của `@PropertySource`/`@TestPropertySource`.
- [Spring Boot Reference — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import` và optional locations.
- [Spring Boot Reference — Config Data Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files): file locations, profile-specific files và thứ tự nạp.
- [Spring Framework Reference — @PropertySource](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): placeholder và `Environment`; xem API `PropertySource` để phân biệt annotation với Config Data.
- [Spring Framework Javadoc — PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/PropertySource.html): thời điểm xử lý và cách dùng `@PropertySource`.
- [Spring Framework Javadoc — PropertySourceFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/support/PropertySourceFactory.html): extension point cho resource loader của annotation.
- [Spring Framework Javadoc — YamlPropertiesFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/YamlPropertiesFactoryBean.html): biến YAML thành Java Properties trong tình huống phù hợp.
- [Spring Boot Reference — EnvironmentPostProcessor](https://docs.spring.io/spring-boot/how-to/application.html): các điểm mở rộng của SpringApplication/Environment theo phiên bản.
