# Tổ chức cấu hình management trong application.properties hoặc YAML

## 1. Cấu hình management giải quyết vấn đề gì?

Sau khi thêm Actuator, ứng dụng cần xác định những khả năng vận hành sẽ được sử dụng: endpoint nào được đưa ra HTTP, hiển thị bao nhiêu thông tin sức khỏe, dùng đường dẫn hoặc cổng nào và những môi trường nào cần cấu hình khác nhau.

Spring Boot đọc các nguồn cấu hình rồi đưa giá trị vào môi trường cấu hình và các đối tượng cấu hình tương ứng. **Gắn giá trị vào đối tượng cấu hình (binding)** giúp các thành phần sử dụng giá trị với kiểu phù hợp, chẳng hạn danh sách endpoint hoặc số cổng.

Properties và YAML là hai cách biểu diễn cấu hình. Chúng không phải hai cơ chế Actuator khác nhau.

Ví dụ, khóa:

~~~text
management.endpoints.web.exposure.include
~~~

có thể được viết trên một dòng properties hoặc thành một cây YAML. Điều quan trọng là **tên khóa, giá trị và nguồn cấu hình thực sự có hiệu lực**, không phải hình thức nhìn gọn hơn.

## 2. Nhận diện các nhóm khóa trước khi viết

| Nhóm khóa | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `management.endpoint.<id>.*` | Cấu hình riêng một endpoint | `management.endpoint.health.show-details` |
| `management.endpoints.web.*` | Cách đưa tập endpoint ra HTTP | `management.endpoints.web.exposure.include` |
| `management.endpoints.jmx.*` | Cấu hình đưa endpoint ra JMX | `management.endpoints.jmx.exposure.include` |
| `management.server.*` | Các tùy chọn của máy chủ quản trị | `management.server.port` |
| `management.metrics.*` | Những tùy chọn metrics thuộc nhóm đó | `management.metrics.tags.application` |

Chú ý **endpoint** số ít trong cấu hình riêng từng endpoint và **endpoints** số nhiều trong cấu hình tập endpoint. Hai tên không thay thế nhau.

`server.port` là cổng máy chủ ứng dụng chính; `management.server.port` có thể đặt cổng riêng cho quản trị. `logging.level.*` thuộc hệ thống ghi log, không được chuyển xuống dưới `management` chỉ vì log phục vụ vận hành.

Đối chiếu tên khóa với đúng phiên bản Boot đang dùng. Bài này dùng hợp đồng Spring Boot 3.3.x; tra cứu tại [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### Cấu hình web không quản lý mọi loại endpoint

`management.endpoints.web` là một nhóm cấu hình riêng cho web; nó có base path, exposure và path mapping. Cấu hình JMX là nhóm khác. Mở một endpoint trên HTTP không đồng nghĩa đã đưa nó ra JMX. Xem [WebEndpointProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.html).

Cũng cần tách ba quyết định:

1. Endpoint có được bật và đủ điều kiện tạo hay không.
2. Endpoint có được đưa ra giao diện HTTP hay không.
3. Yêu cầu cụ thể có được phép truy cập hay không.

Một dòng include không thay thế hai quyết định còn lại.

## 3. Viết một cấu hình nền bằng hai định dạng tương đương

Với dự án thông thường, tệp được đặt trong `src/main/resources`. Chọn **một** trong hai cách dưới đây cho cùng ví dụ.

### 3.1. application.properties

~~~properties
spring.application.name=management-config-demo

management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info

management.endpoint.health.show-details=never
management.endpoint.shutdown.enabled=false
~~~

Cách tổ chức bằng dòng trống:

- Nhận diện ứng dụng.
- Đường dẫn và phạm vi endpoint web.
- Chính sách hiển thị hoặc bật/tắt từng endpoint.

Dòng trống chỉ giúp con người đọc; nó không tạo một phạm vi cấu hình mới. Mỗi dòng vẫn cần đầy đủ tên khóa.

### 3.2. application.yml

~~~yaml
spring:
  application:
    name: management-config-demo

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
    shutdown:
      enabled: false
~~~

`application.yaml` cũng là tên YAML được Spring Boot hỗ trợ. Trong ví dụ sử dụng `application.yml` để thống nhất cách đặt tên.

Khi đọc cây, nối các cấp bằng dấu chấm:

~~~text
management
  endpoints
    web
      exposure
        include
→ management.endpoints.web.exposure.include
~~~

Danh sách YAML `health`, `info` được gắn thành danh sách tương ứng với giá trị properties `health,info`.

### 3.3. Hiểu đúng ý nghĩa của ví dụ

| Khóa | Ý nghĩa trong ví dụ |
| --- | --- |
| `spring.application.name` | Đặt tên ứng dụng |
| `management.endpoints.web.base-path` | Chọn tiền tố web quản trị là /actuator |
| `management.endpoints.web.exposure.include` | Chọn health và info để đưa ra HTTP khi khả dụng |
| `management.endpoint.health.show-details` | Không hiển thị chi tiết health |
| `management.endpoint.shutdown.enabled` | Giữ endpoint shutdown ở trạng thái tắt |

Cấu hình không tự tạo một HTTP server cho ứng dụng không có web. Nó cũng không bảo đảm info luôn trả thông tin bản dựng: dữ liệu endpoint còn phụ thuộc thành phần đóng góp thực tế.

Trong Spring Boot 3.3, mặc định chỉ health được đưa ra HTTP. Include/exclude chọn phạm vi giao diện; khi cùng liệt kê một endpoint, exclude được ưu tiên. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 3.4. Không giữ hai bản cấu hình nền để “dự phòng”

Nên chọn một định dạng nhất quán. Nếu cùng vị trí có cả properties và YAML, Spring Boot ưu tiên properties khi trùng khóa.

Vì vậy, sửa YAML nhưng giữ một giá trị khác trong properties có thể khiến kết quả không đổi như dự đoán. Đây không phải lỗi thụt lề nhất thiết; có thể đang đọc nhầm nguồn thắng. Xem [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

## 4. Những quy tắc cú pháp dễ gây sai cấu hình

### 4.1. YAML dùng thụt lề để biểu diễn phạm vi

Trong YAML, các mục cùng cấp phải thẳng hàng. Dùng dấu cách cho phần thụt lề, không dùng tab.

Trong ví dụ nền, `endpoint` và `endpoints` là hai mục cùng cấp dưới `management`. Nếu đặt `endpoint` dưới `endpoints.web`, tên khóa sau khi làm phẳng sẽ khác với khóa Actuator cần đọc.

Hãy kiểm tra cây từ trái sang phải khi một thuộc tính không có tác dụng, thay vì chỉ kiểm tra từ cuối cùng như `include` hoặc `show-details`.

### 4.2. Chỉ có một khóa management trong mỗi tài liệu YAML

Đừng ghép các đoạn cấu hình bằng cách lặp hai khối gốc `management:` trong cùng tài liệu. Hãy ghép các nhánh vào một khối chung:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Khóa ánh xạ trùng nhau không phải cách hợp lệ để cộng dồn cấu hình. Cũng không nên dựa vào việc một công cụ tình cờ chọn giá trị cuối. Các quy tắc về ánh xạ và thụt lề được mô tả trong [YAML Specification](https://yaml.org/spec/1.2.2/).

Nếu chủ động dùng nhiều tài liệu YAML, chúng cần được phân cách bằng `---` và có điều kiện kích hoạt rõ ràng khi cần. Đó là cơ chế khác với hai khóa trùng nhau trong một tài liệu.

### 4.3. Dấu sao cần viết khác nhau

Nếu thực sự cần ký tự đại diện cho toàn bộ endpoint, cú pháp là:

~~~properties
management.endpoints.web.exposure.include=*
~~~

hoặc:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Trong YAML, dấu sao không đặt trong chuỗi có ý nghĩa cú pháp liên quan alias, nên cần quote ở trường hợp trên.

Đây chỉ là minh họa cú pháp ký tự đại diện. Cấu hình nền của bài vẫn chọn `health,info`; không cần mở toàn bộ endpoint để kiểm tra việc đọc tệp.

### 4.4. Dấu nháy và chú thích của properties không phải cú pháp shell

Với tệp properties, viết:

~~~properties
management.endpoints.web.base-path=/actuator
# Chọn các endpoint web cần dùng
management.endpoints.web.exposure.include=health,info
~~~

Không tự bao giá trị bằng nháy kép theo thói quen shell hoặc YAML. Trong định dạng properties thông thường, dấu nháy có thể trở thành một phần của giá trị.

Cũng nên đặt chú thích trên dòng riêng. Chẳng hạn, viết thêm `# ghi chú` cuối dòng giá trị properties không có cùng ý nghĩa với comment YAML. Định dạng dòng và comment được mô tả trong [Java Properties API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html).

### 4.5. Danh sách không phải tập khóa được tự cộng dồn

Hai cách biểu diễn danh sách YAML sau đều có thể dùng cho include:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
~~~

Khi ghi đè danh sách ở profile hoặc nguồn ưu tiên cao hơn, hãy khai báo danh sách mong muốn đầy đủ. Không suy đoán việc thêm một mục ở tệp khác sẽ tự hợp nhất với mọi mục của cấu hình nền.

Phần thực nghiệm sẽ đối chiếu cụ thể việc danh sách bị thay thế bằng giá trị dòng lệnh.

## 5. Tách phần chung và phần khác nhau theo profile

Cấu trúc gợi ý nếu chọn properties:

~~~text
src/main/resources/
├── application.properties
└── application-local.properties
~~~

Nếu chọn YAML:

~~~text
src/main/resources/
├── application.yml
└── application-local.yml
~~~

Tệp nền giữ các quyết định chung; tệp local chỉ ghi những gì cần thay đổi khi thử cục bộ. Không cần sao chép toàn bộ khối management sang mọi profile.

### 5.1. Nội dung cho profile local

Trong `application-local.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=always
~~~

Hoặc trong `application-local.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: always
~~~

Khi local hoạt động, ví dụ mong muốn đọc thêm metrics và hiển thị chi tiết health. Đây là lựa chọn phục vụ thử nghiệm; tên profile local không tự bảo đảm ứng dụng chỉ có thể được truy cập cục bộ. Nếu dùng với HTTP, còn phải kiểm soát địa chỉ lắng nghe và quyền truy cập.

Nếu cần cho nhiều môi trường, có thể thêm `application-prod.yml` hoặc properties tương ứng để thể hiện phần khác biệt. Tên profile do dự án quy định, không phải mọi ứng dụng đều phải có đủ dev/test/staging/prod.

### 5.2. Kích hoạt profile từ bên ngoài tệp profile

Với Gradle wrapper trong dự án có tác vụ bootRun:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

Với Maven wrapper và Boot Maven plugin:

~~~powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=local"
~~~

Không đặt `spring.profiles.active=local` vào chính `application-local.properties` rồi kỳ vọng tệp tự kích hoạt nó. Spring Boot chỉ cho cấu hình active/default profile trong tài liệu không dành riêng cho profile; các tài liệu đã được kích hoạt bằng `spring.config.activate.on-profile` cũng có ràng buộc này. Xem [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

Tham số `--args` là cách BootRun nhận đối số ứng dụng; `spring-boot.run.profiles` là thuộc tính tương ứng của Maven plugin. Xem [Running with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html) và [Running with Maven](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html).

### 5.3. Khi dùng nhiều tài liệu YAML trong một tệp

Thay vì tách application-local.yml, dự án có thể chủ động dùng một tài liệu local trong application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
---
spring:
  config:
    activate:
      on-profile: local

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Hai khối management thuộc **hai tài liệu khác nhau**, được ngăn bởi `---`. Tài liệu thứ hai chỉ tham gia khi profile local đang hoạt động.

Đây là phương án thay thế về cách tổ chức. Khi mới học, dùng tệp profile riêng thường dễ đối chiếu hơn; đừng giữ cả hai phương án cùng ghi những giá trị khác nhau nếu không có nhu cầu rõ ràng.

## 6. Tổ chức các tùy chọn liên quan mà không nhầm phạm vi

### 6.1. Cổng quản trị và đường dẫn web

Đoạn cấu hình tùy chọn cho một ứng dụng HTTP thử nghiệm:

~~~properties
server.port=8080
management.server.port=8081
management.server.address=127.0.0.1
management.endpoints.web.base-path=/manage
~~~

YAML tương đương:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /manage
~~~

Khi không có cấu hình đường dẫn nền khác và health khả dụng, URL quản trị tương ứng là `http://127.0.0.1:8081/manage/health`. API nghiệp vụ vẫn thuộc cổng chính.

`management.server.address` riêng được dùng khi cổng quản trị khác cổng chính. Nếu dùng chung cổng, cần xét địa chỉ máy chủ chính. Khi ghép đoạn này vào cấu hình đang có, gộp vào các khối server/management hiện tại. Xem [Spring Boot 3.3 — Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 6.2. Nhãn metrics có thể dùng một giá trị chung

Ví dụ phần bổ sung trong properties:

~~~properties
management.metrics.tags.application=${spring.application.name}
~~~

Hoặc ghép vào nhánh management đang có:

~~~yaml
management:
  metrics:
    tags:
      application: "${spring.application.name}"
~~~

Placeholder lấy tên ứng dụng đã được cấu hình. Nhờ đó, khi đổi tên ứng dụng không phải sửa lại cùng giá trị tại nhiều vị trí.

Đây là nhãn chung cho metrics theo cơ chế hỗ trợ của Boot; không phải lệnh mở endpoint metrics hoặc khởi tạo máy chủ Prometheus. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 6.3. Không dùng khóa tự đặt để thay khóa chuẩn

Một tên như `management.exposure` có thể nhìn hợp lý với người viết nhưng không thay thế `management.endpoints.web.exposure.include`.

Không phải mọi thuộc tính viết sai đều làm ứng dụng dừng ngay. Việc xử lý trường không nhận diện còn phụ thuộc đối tượng binding và cơ chế đọc. Vì vậy, “khởi động được” chưa chứng minh từng khóa management đều đúng. Xem [ConfigurationProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).

Dùng gợi ý IDE và metadata theo đúng dependency để giảm lỗi gõ; sau đó kiểm tra giá trị và hành vi thực tế.

## 7. Kiểm chứng hai định dạng và việc ghi đè

Thực nghiệm sau dùng một dự án Boot **3.3.0**, JDK **21**, có starter Actuator và tác vụ chạy phù hợp. Mã Java dùng cú pháp tương thích Java 17 trở lên. Không cần một web server: mục tiêu là xem cấu hình nào đã được đọc và danh sách nào được bind.

### 7.1. Điều kiện của dự án thử nghiệm

Trong dự án Gradle đã có Boot plugin và quản lý phiên bản dependency 3.3.0, cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đoạn trên là phần dependencies cần ghép, không phải toàn bộ build.gradle.

Chọn bộ tệp properties hoặc YAML ở phần 3 và 5, đặt vào `src/main/resources`. Thực nghiệm giả định không có biến môi trường, tệp bên ngoài hoặc tham số khác đang ghi đè các khóa được in.

### 7.2. Một chương trình chỉ đọc ba giá trị

Tạo `src/main/java/example/managementconfig/ManagementConfigApplication.java`:

~~~java
package example.managementconfig;

import java.util.List;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ManagementConfigApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ManagementConfigApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            Environment environment = context.getEnvironment();
            List<String> included = Binder.get(environment)
                    .bind("management.endpoints.web.exposure.include",
                            Bindable.listOf(String.class))
                    .orElse(List.of());

            System.out.println("basePath=" + environment.getProperty(
                    "management.endpoints.web.base-path"));
            System.out.println("include=" + String.join(",", included));
            System.out.println("showDetails=" + environment.getProperty(
                    "management.endpoint.health.show-details"));
        }
    }
}
~~~

Chương trình thực hiện ba việc:

- Khởi động Spring Boot ở chế độ không có web.
- Dùng Environment để đọc hai giá trị đơn và Binder để đọc danh sách.
- In các giá trị được chọn rồi đóng context.

Binder hỗ trợ gắn cấu hình từ các nguồn thuộc tính vào kiểu dữ liệu mong muốn. Cách đọc danh sách cho phép cùng xử lý biểu diễn chuỗi có dấu phẩy và danh sách YAML. Xem [Binder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html).

Mã này là công cụ kiểm tra nhỏ cho bài học; không cần thêm chức năng in cấu hình vào mọi ứng dụng thực tế.

### 7.3. Không bật profile local

Chạy:

~~~powershell
.\gradlew.bat bootRun
~~~

Với bộ cấu hình nền đã nêu, ba dòng do chương trình in là:

~~~text
basePath=/actuator
include=health,info
showDetails=never
~~~

Kết quả giống nhau cho hai định dạng. Đây là stdout của chương trình kiểm tra; log từ framework nếu có không được coi là đầu ra cố định.

Muốn tự so sánh properties và YAML, dùng hai bản thử riêng hoặc thay định dạng bằng cách giữ lại đúng một bộ tệp. Đừng vô tình kiểm tra cả hai nhưng thực tế properties đang che giá trị YAML.

### 7.4. Bật profile local

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

Kết quả:

~~~text
basePath=/actuator
include=health,info,metrics
showDetails=always
~~~

Base path được kế thừa từ tệp nền vì profile không khai báo lại. Hai thuộc tính có trong profile mang giá trị mới.

### 7.5. Ghi đè include bằng tham số dòng lệnh

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local --management.endpoints.web.exposure.include=health"
~~~

Kết quả:

~~~text
basePath=/actuator
include=health
showDetails=always
~~~

Include chỉ còn health. Nó không được tự cộng thành health,info,metrics vì một giá trị ưu tiên cao hơn đã được cung cấp cho danh sách này.

Show-details vẫn là always từ profile vì tham số không ghi đè khóa đó. Việc ghi đè xảy ra theo thuộc tính, không có nghĩa toàn bộ khối management bị thay cùng lúc.

### 7.6. Điều chương trình xác minh và chưa xác minh

Ba dòng in xác minh việc nạp các tệp, chọn profile, ưu tiên tham số và chuyển đổi danh sách. Chúng **chưa xác minh URL HTTP** hoặc chính sách truy cập, vì chương trình đặt `WebApplicationType.NONE`.

Đối với ứng dụng web thực tế, cần gọi đúng URL và kiểm tra quyền truy cập riêng. Giá trị include chứa tên một endpoint không chứng minh endpoint đó đã đủ điều kiện tồn tại.

## 8. Kiểm tra nguồn cấu hình khi kết quả khác dự kiến

### 8.1. Tìm nơi đang đặt cùng một khóa

Khi đã sửa tệp mà hành vi không đổi, lần lượt xác định:

1. Đang khởi chạy đúng module và artifact đã được dựng lại chưa?
2. Tệp đã nằm trong nguồn tài nguyên được nạp chưa?
3. Profile nào đang hoạt động?
4. Có cùng khóa trong properties/YAML khác, tệp bên ngoài, biến môi trường hoặc tham số chạy không?
5. Thuộc tính có đúng tên và được thành phần tương ứng sử dụng không?

Trong tình huống ứng dụng thông thường, đối số dòng lệnh có thể ghi đè giá trị từ các tệp cấu hình, như thực nghiệm đã thể hiện. Biến môi trường cũng là một nguồn đầu vào cần xem xét.

Ví dụ tên biến môi trường cho khóa include là:

~~~text
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
~~~

Hãy đọc tham số trong cấu hình Run của IDE hoặc môi trường triển khai, không chỉ đọc application.yml trong source.

### 8.2. Dùng công cụ chẩn đoán đúng phạm vi

Trong ứng dụng web đã có chính sách truy cập thích hợp, endpoint `env` hỗ trợ xem các nguồn thuộc tính và nguồn gốc giá trị; dữ liệu có thể bị che theo cấu hình. Xem [Spring Boot 3.3 — Environment REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

Endpoint `configprops` hỗ trợ xem các bean cấu hình đã được bind và đầu vào tương ứng. Nó giúp phân biệt “khóa có trong Environment” với “giá trị đã đi vào đối tượng cấu hình nào”. Xem [Spring Boot 3.3 — Configuration Properties REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

Không cần mở hai endpoint này ra công khai hoặc bật hiển thị toàn bộ giá trị để hoàn thành bài. Ưu tiên kiểm tra cục bộ và chỉ quan sát những khóa không chứa bí mật.

### 8.3. Lưu ý tên tệp và cập nhật khi đang chạy

Một tệp tùy ý tên `management.yml` không tự được nạp chỉ vì chứa khóa management. Nếu tách tệp theo nhu cầu dự án, cần cấu hình nạp/import rõ ràng.

Đổi application.yml trong source cũng không mặc nhiên cập nhật tiến trình đã chạy với artifact cũ. Sau thay đổi, dựng/chạy lại theo cơ chế của dự án và xác minh lại; không giả định mọi khóa management hỗ trợ thay đổi động.

## 9. Lỗi thường gặp

| Biểu hiện | Điều cần kiểm tra |
| --- | --- |
| Sửa YAML nhưng giá trị vẫn như cũ | Có properties cùng vị trí hoặc nguồn ưu tiên cao hơn không? |
| Một khóa không tác động mà ứng dụng vẫn chạy | Đúng tên, đúng cấp YAML và đúng tuyến phiên bản chưa? |
| Profile local không được nạp | Đã kích hoạt profile từ nguồn hợp lệ chưa? |
| Chỉ muốn thêm metrics nhưng làm mất info | Có đang ghi đè cả danh sách bằng giá trị mới thiếu info không? |
| YAML lỗi ngay khi đọc include là dấu sao | Đã viết `"*"` thành một chuỗi chưa? |
| Ghép thêm đoạn management làm lỗi cấu hình | Có lặp khóa gốc trong cùng tài liệu không? |
| Đổi management port nhưng vẫn gọi cổng chính | Đã tính lại URL theo port và base path thực tế chưa? |
| Include đúng nhưng không có URL | Có web server, thành phần endpoint, exposure và quyền truy cập phù hợp chưa? |
| Chỉ đổi tên tệp thành management.yml rồi không thấy giá trị | Tệp có được cấu hình nạp không? |
| Chạy được nên kết luận mọi thuộc tính đều hợp lệ | Đã kiểm tra giá trị được bind và hành vi mong muốn chưa? |

### Tự thực hành

1. Chuyển cấu hình nền từ properties sang YAML mà giữ nguyên các giá trị và danh sách.
2. Bật profile local rồi dự đoán ba dòng đầu ra trước khi chạy chương trình.
3. Ghi đè include bằng health và giải thích vì sao info,metrics không còn trong kết quả.
4. Với một ứng dụng web có cổng quản trị 8081 và base path /manage, chỉ ra URL health trong điều kiện không có đường dẫn nền bổ sung.
5. Tìm một khóa bị khai báo ở nhiều nguồn trong dự án thử nghiệm; xác định giá trị thắng bằng chứng cứ thay vì chỉ theo vị trí tệp đang mở.

**Gợi ý đối chiếu:** tập trung vào tên khóa sau khi làm phẳng, nguồn cấu hình đang thắng, kiểu giá trị được bind và hành vi của thành phần sử dụng. Hai định dạng tương đương khi biểu diễn cùng cấu hình có hiệu lực; thụt lề hoặc ghi đè sai có thể làm chúng không còn tương đương.
