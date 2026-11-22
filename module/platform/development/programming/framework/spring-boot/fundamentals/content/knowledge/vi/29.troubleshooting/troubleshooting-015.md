# Kết hợp log, conditions report, dependency tree và kiểm thử tái hiện

Khi một ứng dụng Spring Boot khởi động thất bại hoặc hoạt động khác với mong đợi, một thông báo lỗi đơn lẻ thường chưa đủ để xác định nguyên nhân. Có thể bean không được tạo vì điều kiện auto-configuration không khớp; một dependency bị thiếu hoặc xung đột version; cấu hình bị ghi đè bởi profile hay biến môi trường; hoặc logic chỉ lỗi trong một tổ hợp bean và property cụ thể.

Một quy trình chẩn đoán hiệu quả kết hợp bốn nguồn bằng chứng:

1. **Log và stack trace** cho biết điều gì đã xảy ra, tại thời điểm nào và lỗi xuất hiện ở đâu.
2. **Conditions report** giải thích vì sao Spring Boot áp dụng hoặc bỏ qua một auto-configuration.
3. **Dependency tree** cho biết thư viện nào thực sự có mặt, được kéo vào qua đường nào và version nào được chọn.
4. **Kiểm thử tái hiện** biến giả thuyết thành một trường hợp nhỏ, có thể chạy lại và xác nhận cách sửa.

Mỗi nguồn trả lời một câu hỏi khác nhau. Log không tự giải thích đầy đủ dependency graph; dependency tree không chứng minh bean đã được đăng ký; conditions report không xác nhận logic nghiệp vụ; còn test tái hiện giúp kiểm chứng nguyên nhân trong một môi trường có thể kiểm soát.

## 1. Bắt đầu bằng triệu chứng và phạm vi lỗi

Trước khi thay đổi cấu hình hoặc nâng version thư viện, hãy mô tả chính xác điều đang xảy ra.

Ví dụ:

- Ứng dụng dừng khi khởi động với `UnsatisfiedDependencyException`.
- Một endpoint trả `404` trong khi ứng dụng vẫn khởi động.
- Bean của một auto-configuration không xuất hiện.
- Một test chạy riêng thành công nhưng chạy cả suite lại thất bại.
- Ứng dụng chạy trong IDE nhưng executable JAR báo `NoClassDefFoundError`.
- Một thư viện hoạt động trên máy developer nhưng CI gặp `NoSuchMethodError`.

Ghi lại ít nhất:

- Lệnh khởi chạy hoặc lệnh test chính xác.
- Phiên bản Java, Spring Boot và build tool.
- Active profiles và các property override có liên quan.
- Môi trường xảy ra lỗi: IDE, local terminal, CI, container hay production.
- Thời điểm lỗi: compile, test, tạo ApplicationContext, xử lý request hay shutdown.
- Lỗi có lặp lại ổn định không, hay chỉ xuất hiện theo thời điểm/tải.

Một lỗi xảy ra ở bước compile cần được xử lý khác với lỗi xuất hiện khi Spring tạo bean. Nếu ứng dụng chưa thể tạo ApplicationContext, việc kiểm tra controller mapping thường chưa phải điểm bắt đầu phù hợp.

### Phân loại theo giai đoạn

| Giai đoạn | Dấu hiệu | Bằng chứng nên xem đầu tiên |
|---|---|---|
| Resolve dependency / compile | Không tìm thấy class, method hoặc artifact | Dependency tree, compile output, repository và version |
| Test startup | Context load thất bại | Stack trace, conditions report, test properties |
| Application startup | Bean creation hoặc auto-configuration lỗi | Startup logs, failure analysis, conditions report |
| Runtime request | HTTP status, lỗi nghiệp vụ, timeout | Request logs, trace, configuration và dependency ngoài |
| Shutdown | Task không kết thúc, resource không đóng | Lifecycle logs, thread dump, graceful shutdown config |
| Chỉ lỗi trong CI | Khác môi trường hoặc thứ tự chạy | Java/build version, environment, test isolation, dependency resolution |

Mục tiêu là xác định lỗi nằm ở **build**, **Spring bootstrap**, **logic ứng dụng** hay **hệ thống bên ngoài** trước khi đi sâu vào một công cụ cụ thể.

## 2. Đọc log và stack trace theo cấu trúc

Log cho biết ứng dụng đã đi tới đâu và lỗi đầu tiên có ý nghĩa xuất hiện ở vị trí nào. Trong Spring Boot, startup logs thường bao gồm:

- Phiên bản Spring Boot và Java.
- Profile đang hoạt động.
- Các bước khởi tạo ApplicationContext.
- Web server được khởi chạy trên cổng nào.
- Thời điểm context hoàn tất startup.
- Warning hoặc exception trong quá trình tạo bean.

Khi ứng dụng thất bại, hãy tìm **exception đầu tiên có ý nghĩa**, sau đó lần theo chuỗi nguyên nhân lồng nhau đến root cause. Exception ngoài cùng thường mô tả giai đoạn Spring thất bại, còn exception sâu hơn có thể nêu nguyên nhân thực tế.

Ví dụ rút gọn:

~~~text
APPLICATION FAILED TO START

Description:
Parameter 0 of constructor in com.example.OrderService
required a bean of type 'com.example.PaymentGateway'
that could not be found.

Action:
Consider defining a bean of type 'com.example.PaymentGateway'
in your configuration.
~~~

Thông báo này chỉ ra Spring không tìm được bean kiểu `PaymentGateway`. Nhưng nó chưa trả lời tại sao:

- Implementation chưa được tạo?
- Package không nằm trong component scan?
- Một `@Profile` không hoạt động?
- `@ConditionalOnProperty` không khớp?
- Auto-configuration bị exclude?
- Dependency chứa implementation không có trên runtime classpath?

Đây là lúc kết hợp log với conditions report và dependency tree.

### Đọc chuỗi caused by

Một stack trace có thể có nhiều lớp exception:

~~~text
UnsatisfiedDependencyException
  caused by BeanCreationException
    caused by NoSuchBeanDefinitionException
~~~

Cách đọc:

1. `UnsatisfiedDependencyException`: Spring không thể cung cấp dependency cho một bean.
2. `BeanCreationException`: quá trình tạo một bean cụ thể thất bại.
3. `NoSuchBeanDefinitionException`: nguyên nhân sâu hơn là không có bean phù hợp trong context.

Không nên chỉ nhìn dòng exception đầu tiên rồi kết luận phải thêm dependency. Có thể dependency đã có nhưng điều kiện tạo bean không khớp.

Nếu root cause là `NoClassDefFoundError` hoặc `NoSuchMethodError`, hướng điều tra chuyển sang runtime classpath và version compatibility thay vì chỉ xem component scanning.

### Đừng bỏ qua log trước exception

Một số dòng ngay trước lỗi chứa thông tin rất hữu ích:

- Profile đã active.
- Configuration class nào đang được xử lý.
- DataSource hoặc embedded server đã được tạo chưa.
- Bean nào khởi tạo thành công trước đó.
- Một auto-configuration bị exclude hoặc một property bị deprecate.
- Một external connection timeout xảy ra trước khi context thất bại.

Hãy xem đủ phần log trước root cause. Chỉ copy dòng cuối cùng có thể làm mất chuỗi sự kiện dẫn tới lỗi.

## 3. Chọn logging level có mục tiêu

Spring Boot sử dụng logging facade và logging implementation theo dependency của ứng dụng; cấu hình phổ biến có thể dùng Logback. Có thể thay đổi mức log bằng file cấu hình:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.boot.autoconfigure: DEBUG
    org.springframework.context.annotation: DEBUG
    com.example.orders: DEBUG
~~~

Ý nghĩa:

- `root: INFO` giữ log thông thường ở mức vừa phải.
- `org.springframework.boot.autoconfigure: DEBUG` cung cấp thêm thông tin về auto-configuration.
- `org.springframework.context.annotation: DEBUG` giúp quan sát một số bước xử lý cấu hình và bean definition.
- `com.example.orders: DEBUG` tăng chi tiết cho package nghiệp vụ đang điều tra.

Không nên bật `TRACE` cho toàn bộ `root` trong production nếu chưa biết lượng log và dữ liệu nhạy cảm có thể xuất hiện. Hãy bật theo package hoặc class cần thiết, tái hiện lỗi, thu thập bằng chứng rồi trả mức log về phù hợp.

### Thay log level qua command line

Có thể override property khi chạy:

~~~bash
java -jar app.jar --logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Hoặc đặt JVM/system properties phù hợp với cách chạy. Command-line property của Spring Boot là một cách nhanh để điều tra mà không cần sửa file cấu hình đã đóng gói.

Với Gradle:

~~~bash
./gradlew bootRun --args='--logging.level.org.springframework.boot.autoconfigure=DEBUG'
~~~

Với Maven Spring Boot plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Cú pháp truyền argument có thể phụ thuộc version và cấu hình plugin. Khi dùng wrapper hoặc script riêng, hãy xác nhận ứng dụng thực sự nhận property bằng startup log hoặc Environment.

### --debug có tác dụng gì?

Spring Boot hỗ trợ tham số:

~~~bash
java -jar app.jar --debug
~~~

`--debug` bật debug mode của Spring Boot và giúp in **conditions evaluation report** cùng một số log chẩn đoán liên quan. Nó không có nghĩa toàn bộ logger của mọi package trong ứng dụng chuyển sang DEBUG.

Nếu cần xem log của một package cụ thể, hãy cấu hình `logging.level.<logger-name>`. Hai cơ chế bổ trợ nhau:

- `--debug`: tập trung vào báo cáo điều kiện auto-configuration và một số logger cốt lõi.
- `logging.level`: điều khiển mức log cho package/class cụ thể.

Có thể bật qua cấu hình:

~~~yaml
debug: true
~~~

Đối với điều tra ngắn hạn, command line thường thuận tiện vì không phải commit thay đổi debug vào file cấu hình mặc định.

## 4. Conditions report trả lời điều gì?

Spring Boot auto-configuration dựa trên các điều kiện như:

- Class có mặt trên classpath hay không.
- Một bean đã tồn tại hay chưa.
- Property có giá trị phù hợp hay không.
- Web application type là servlet hay reactive.
- Một resource có tồn tại hay không.
- Một cấu hình khác có được import hay không.

Các điều kiện này được thể hiện qua annotation như:

~~~java
@ConditionalOnClass(...)
@ConditionalOnMissingBean(...)
@ConditionalOnBean(...)
@ConditionalOnProperty(...)
@ConditionalOnWebApplication(...)
@ConditionalOnResource(...)
~~~

Ví dụ, một auto-configuration có thể chỉ tạo bean khi thư viện tồn tại và người dùng chưa tự cung cấp implementation:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
@ConditionalOnMissingBean(PaymentGateway.class)
class PaymentAutoConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentClient client) {
        return new DefaultPaymentGateway(client);
    }
}
~~~

Nếu bean `PaymentGateway` không xuất hiện, có ít nhất hai giả thuyết trực tiếp:

1. `PaymentClient` không có trên classpath nên `@ConditionalOnClass` không khớp.
2. Một bean `PaymentGateway` khác đã tồn tại hoặc cấu hình bean bị tác động bởi điều kiện khác nên `@ConditionalOnMissingBean` không khớp.

Conditions report giúp xác định điều kiện nào đã match hoặc không match.

## 5. Bật conditions evaluation report

Cách nhanh nhất khi chạy ứng dụng:

~~~bash
java -jar app.jar --debug
~~~

Trong quá trình startup, Spring Boot có thể in phần `CONDITIONS EVALUATION REPORT`, thường được chia thành:

- **Positive matches:** các auto-configuration hoặc condition đã khớp.
- **Negative matches:** các auto-configuration không được áp dụng vì điều kiện không khớp.
- **Exclusions:** các auto-configuration bị loại trừ.
- **Unconditional classes:** các cấu hình không phụ thuộc điều kiện theo report.

Ví dụ minh họa:

~~~text
CONDITIONS EVALUATION REPORT

Positive matches:

   DataSourceAutoConfiguration matched:
      - @ConditionalOnClass found required classes
      - @ConditionalOnMissingBean did not find a bean of type DataSource

Negative matches:

   MongoAutoConfiguration:
      Did not match:
         - @ConditionalOnClass did not find
           'com.mongodb.client.MongoClient'

   WebMvcAutoConfiguration:
      Did not match:
         - @ConditionalOnWebApplication did not find
           a servlet web application
~~~

Đây là output minh họa để giải thích cách đọc; tên condition, nội dung và format thực tế phụ thuộc version Boot, dependency và ứng dụng.

### Đọc positive match

Positive match cho biết một cấu hình đã vượt qua các điều kiện được report. Nó **không bảo đảm toàn bộ bean bên trong cấu hình khởi tạo thành công**.

Ví dụ, `DataSourceAutoConfiguration` match nhưng tạo DataSource vẫn có thể thất bại vì thiếu URL, driver, credential hoặc database không kết nối được. Khi đó, cần đọc exception và log tạo bean.

### Đọc negative match

Negative match thường là đầu mối khi một bean mặc định không xuất hiện.

Ví dụ:

~~~text
SomeAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty (feature.enabled=true)
        found different value
~~~

Cần kiểm tra:

- Property name có đúng không?
- Giá trị có bị ghi đè bởi environment variable hoặc command-line argument không?
- Profile có làm thay đổi file cấu hình không?
- Property có đang nằm trong YAML document không được kích hoạt không?
- Có khác biệt về prefix hoặc relaxed binding không?

Đừng vội sửa annotation condition nếu property source đang cung cấp giá trị ngoài dự kiến.

### Đọc exclusions

Auto-configuration có thể bị loại trừ qua:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class Application {
}
~~~

Hoặc property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Nếu conditions report cho biết auto-configuration bị exclude, hãy tìm nơi cấu hình loại trừ. Việc thêm dependency database sẽ không khắc phục nếu chính auto-configuration đã bị loại khỏi quá trình áp dụng.

## 6. Conditions report không phải dependency report

Hai báo cáo thường bị nhầm:

| Công cụ | Trả lời câu hỏi |
|---|---|
| Conditions evaluation report | Vì sao Spring Boot chọn hoặc bỏ qua auto-configuration? |
| Dependency tree | Thư viện nào được build tool resolve, từ đâu và version nào? |
| ApplicationContext/beans report | Bean nào thực sự được tạo trong context? |
| Runtime log | Điều gì xảy ra khi bean hoặc ứng dụng khởi tạo? |

Ví dụ, conditions report nói `@ConditionalOnClass` không khớp vì thiếu `com.example.PaymentClient`. Dependency tree có thể xác nhận thư viện chứa class này chưa được đưa vào runtime classpath.

Ngược lại, dependency tree cho thấy JAR đã có mặt không chứng minh Spring đã tạo bean từ JAR đó. Component scan, auto-configuration import, profile và conditions vẫn quyết định bean có được đăng ký hay không.

### Conditions report ở Actuator

Nếu ứng dụng có Actuator và phiên bản hỗ trợ endpoint conditions, có thể quan sát report qua endpoint:

~~~text
GET /actuator/conditions
~~~

Endpoint này cần được tạo, bật/access và expose qua HTTP hoặc transport tương ứng; caller cũng phải có quyền truy cập. Nó không tự xuất hiện chỉ vì Actuator starter được thêm vào.

Ví dụ exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Endpoint conditions có thể tiết lộ thông tin về cấu trúc cấu hình và thư viện của ứng dụng. Chỉ expose trên môi trường và đối tượng vận hành phù hợp, kết hợp authentication/authorization; không mở mọi Actuator endpoint chỉ để điều tra một lỗi.

Trong một số phiên bản hoặc cấu hình, có thể dùng các endpoint quan sát khác như `beans`, `env` hoặc `configprops` để xác định trạng thái thực tế. Các endpoint này cũng cần bảo vệ vì có thể tiết lộ thông tin nhạy cảm.

## 7. Dependency tree: kiểm tra classpath được build tool resolve

Khi lỗi liên quan tới class hoặc method, hãy kiểm tra dependency graph thay vì đoán version từ file build.

Dependency tree cho biết:

- Dependency trực tiếp và dependency bắc cầu (transitive).
- Đường đi nào kéo một thư viện vào.
- Version được chọn sau conflict resolution.
- Scope/configuration mà dependency thuộc về.
- Một thư viện có bị loại trừ (exclude) hay không.

Ví dụ ứng dụng khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.example:payment-adapter:2.0.0'
}
~~~

`payment-adapter` có thể kéo theo một version khác của thư viện client mà ứng dụng cũng sử dụng trực tiếp. Build tool chọn version theo quy tắc resolution; version được ghi trong một dòng khai báo không phải lúc nào cũng là version cuối cùng trong runtime classpath.

Đây là lý do cần xem **resolved graph**.

## 8. Maven dependency:tree

Với Maven, plugin dependency cung cấp goal:

~~~bash
mvn dependency:tree
~~~

Có thể tăng chi tiết:

~~~bash
mvn dependency:tree -Dverbose
~~~

Lọc một dependency:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-core
~~~

Lọc theo group/artifact cụ thể:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Khi cần xem một scope cụ thể, có thể sử dụng các tham số hỗ trợ bởi phiên bản dependency plugin đang dùng, ví dụ:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Ví dụ output rút gọn:

~~~text
com.example:catalog-service:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:...
|  +- org.springframework.boot:spring-boot-starter:jar:...
|  |  +- org.springframework:spring-core:jar:...
|  |  - org.springframework:spring-context:jar:...
|  - org.springframework.boot:spring-boot-starter-json:jar:...
- com.example:payment-adapter:jar:2.0.0
   - com.fasterxml.jackson.core:jackson-databind:jar:...
~~~

Output minh họa cho thấy dependency có thể đến từ nhiều nhánh. Nếu cùng một artifact xuất hiện với version khác nhau, hãy xem phần conflict/omitted để hiểu Maven đã chọn version nào.

### Dùng effective POM khi cần hiểu dependency management

Maven có thể quản lý version qua parent POM hoặc BOM. Khi một dependency không khai báo version trực tiếp, hãy xem effective POM:

~~~bash
mvn help:effective-pom
~~~

Lệnh này giúp thấy cấu hình sau khi kế thừa parent, áp dụng profile và hợp nhất các phần liên quan.

Cần phân biệt:

- `dependencyManagement` quản lý version/scope mặc định khi dependency được khai báo.
- `dependencies` khai báo dependency thực sự của module.
- Maven profile có thể làm thay đổi effective POM và dependency graph.
- Dependency tree phản ánh những dependency đã được resolve cho project hiện tại.

Nếu một dependency không có trong tree, thêm version vào `dependencyManagement` một mình chưa chắc làm nó xuất hiện; module còn phải khai báo dependency hoặc nhận nó từ một cấu hình phù hợp.

## 9. Gradle dependencies và dependencyInsight

Với Gradle, lệnh tổng quát:

~~~bash
./gradlew dependencies
~~~

Đối với ứng dụng Spring Boot, hãy xem configuration phù hợp. Ví dụ:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Ba configuration có thể khác nhau:

- `compileClasspath`: những gì cần để biên dịch source chính.
- `runtimeClasspath`: những gì cần khi chạy ứng dụng.
- `testRuntimeClasspath`: những gì cần khi chạy test.

Nếu lỗi chỉ xuất hiện khi chạy executable JAR, `runtimeClasspath` thường đáng chú ý hơn compile classpath.

Để điều tra một dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Hoặc:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Gradle có thể hiển thị version được chọn, các dependency path dẫn tới nó và lý do resolution như version constraint, conflict resolution hoặc rule do build áp dụng.

### Ví dụ đọc dependencyInsight

Output minh họa:

~~~text
org.springframework:spring-core:6.x.y
   Selection reasons:
      - By constraint
      - By conflict resolution

org.springframework:spring-core:6.x.y
--- org.springframework:spring-context:6.x.y
     --- runtimeClasspath
~~~

Nếu một thư viện kéo version cũ nhưng Gradle chọn version mới hơn, hãy xác định ai đưa ra constraint hoặc rule. Không nên thêm một dependency cùng tên với version mới hơn chỉ để “ép” build xanh mà không hiểu compatibility.

### Kiểm tra cấu hình test

Một thư viện có thể có trên `runtimeClasspath` nhưng không có trong `testRuntimeClasspath` nếu cấu hình dependency hoặc variant khác nhau. Nếu lỗi chỉ xuất hiện trong test, hãy xem đúng configuration test.

Đừng giả định mọi configuration Gradle đều có cùng dependency graph. Một ứng dụng có thể compile thành công nhưng test runtime thiếu provider, hoặc test pass trong khi executable archive thiếu một runtime dependency.

## 10. Hiểu các lỗi dependency phổ biến

Một số exception gợi ý rất rõ loại vấn đề cần tìm.

| Lỗi | Ý nghĩa thường gặp | Nơi điều tra |
|---|---|---|
| `ClassNotFoundException` | Class được yêu cầu nhưng classloader không tìm thấy | Runtime classpath, scope, packaging |
| `NoClassDefFoundError` | JVM không thể sử dụng class cần thiết lúc runtime; có thể thiếu class hoặc class khởi tạo thất bại trước đó | Dependency tree, nguyên nhân đầu tiên, classloader |
| `NoSuchMethodError` | Class có mặt nhưng method không tồn tại trong version đang được load | Version conflict, dependency alignment |
| `NoSuchFieldError` | Field mong đợi không có trong class đang được load | Version mismatch |
| `NoSuchBeanDefinitionException` | Spring không tìm thấy bean phù hợp | Component scan, condition, profile, bean registration |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng phù hợp mà không có lựa chọn duy nhất | `@Primary`, `@Qualifier`, condition |
| `BeanCreationException` | Tạo bean thất bại | Nested cause, constructor, factory method, configuration |
| `UnsatisfiedDependencyException` | Không giải quyết được dependency của bean | Bean graph và root cause |
| `NoSuchBeanDefinitionException` từ auto-config | Điều kiện hoặc bean user-defined chưa phù hợp | Conditions report, classpath, property |

### ClassNotFoundException

Ví dụ:

~~~text
java.lang.ClassNotFoundException: com.example.payment.PaymentClient
~~~

Có thể class chưa nằm trên runtime classpath, dependency bị exclude, dependency chỉ khai báo compile-only hoặc executable archive thiếu JAR tương ứng.

Kiểm tra Gradle:

~~~bash
./gradlew dependencyInsight --dependency payment-client --configuration runtimeClasspath
~~~

Kiểm tra Maven:

~~~bash
mvn dependency:tree -Dincludes=com.example:payment-client
~~~

Nếu dependency có trong tree nhưng class vẫn thiếu, kiểm tra đúng JAR có chứa class hay không, artifact có đúng classifier/variant không và classloader có đang dùng một archive khác không.

### NoSuchMethodError

Ví dụ:

~~~text
java.lang.NoSuchMethodError:
  'void com.example.client.ApiClient.setTimeout(...)'
~~~

Lỗi này thường cho thấy code được compile với một API version nhưng runtime lại load class từ version khác không có method đó.

Điều tra:

1. Xác định class được nạp thuộc artifact nào.
2. Xem version trên compile classpath và runtime classpath.
3. Tìm dependency nào kéo version khác.
4. Kiểm tra BOM hoặc dependency constraints.
5. Đồng bộ version theo compatibility matrix của framework/thư viện.

Chỉ thêm một JAR mới vào build chưa chắc sửa được nếu version cũ vẫn được chọn hoặc có nhiều class trùng nhau.

## 11. Version alignment với Spring Boot BOM

Spring Boot cung cấp dependency management để các thư viện trong hệ sinh thái có version tương thích với nhau. Khi dùng Spring Boot parent hoặc BOM, nên tận dụng version đã được quản lý thay vì tự pin tùy tiện từng module Spring.

Maven với parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version><!-- Spring Boot version --></version>
    <relativePath/>
</parent>
~~~

Hoặc import BOM khi dùng parent khác:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version><!-- Spring Boot version --></version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Gradle native BOM support:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.boot:spring-boot-dependencies:<spring-boot-version>"
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Các placeholder version cần được thay bằng phiên bản Spring Boot mà project chủ động sử dụng.

Không nên tự nâng riêng `spring-core`, `spring-context` hoặc một module Spring Framework khác lệch khỏi version line được Boot quản lý nếu không có lý do tương thích rõ ràng. Một dependency tree có thể giúp phát hiện sự lệch version, nhưng quyết định sửa nên dựa trên version alignment và compatibility của cả hệ sinh thái.

### Dependency convergence và exclusions

Nếu hai dependency kéo hai version khác nhau của cùng artifact, build tool phải chọn một version theo resolution rule. Việc chọn thành công không bảo đảm các thư viện đều tương thích với version được chọn.

Khi cần exclude:

~~~groovy
dependencies {
    implementation('com.example:legacy-adapter:1.4.0') {
        exclude group: 'commons-logging', module: 'commons-logging'
    }
}
~~~

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-adapter</artifactId>
    <version>1.4.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Chỉ exclude khi đã xác nhận dependency đó thực sự không cần thiết hoặc được thay thế bởi một implementation tương thích. Exclude bừa có thể biến conflict dễ nhận biết thành lỗi runtime khó chẩn đoán.

## 12. Kết nối conditions report với dependency tree

Đây là bước quan trọng để hai báo cáo bổ trợ nhau.

Giả sử startup log cho biết bean `PaymentGateway` không tồn tại. Conditions report hiển thị:

~~~text
PaymentAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find
        'com.example.payment.PaymentClient'
~~~

Từ đây, chuyển sang dependency tree:

**Maven**

~~~bash
mvn dependency:tree -Dincludes=com.example:payment-client
~~~

**Gradle**

~~~bash
./gradlew dependencyInsight --dependency payment-client --configuration runtimeClasspath
~~~

Có thể gặp một trong các trường hợp:

- Không có artifact: dependency chưa được khai báo.
- Có artifact trong compile nhưng không có runtime: scope/configuration sai.
- Có artifact nhưng sai version/classifier: class mong đợi không tồn tại.
- Dependency bị exclude hoặc variant không được chọn.
- Dependency đã có nhưng auto-configuration condition khác không khớp.

Nếu dependency tree xác nhận artifact đúng và class có mặt, chuyển sang điều kiện khác như `@ConditionalOnProperty`, `@ConditionalOnBean`, profile hoặc auto-configuration import.

Không nên lặp lại thao tác thêm dependency nhiều lần nếu điều kiện thực sự bị chặn bởi property hoặc bean khác.

## 13. Từ conditions report tới cấu hình thực tế

Giả sử report ghi:

~~~text
FeatureAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty
        (app.feature.enabled=true) found different value
~~~

Kiểm tra nguồn cấu hình hiệu lực:

- `application.yml` trong classpath.
- `application-{profile}.yml`.
- File bên ngoài JAR.
- Biến môi trường.
- Java system properties.
- Command-line arguments.
- Test properties hoặc cấu hình chương trình.

Ví dụ một file mặc định:

~~~yaml
app:
  feature:
    enabled: false
~~~

Nhưng môi trường triển khai có:

~~~bash
APP_FEATURE_ENABLED=true
~~~

hoặc ngược lại. Property source ưu tiên cao hơn có thể ghi đè giá trị trong file.

Có thể tăng log cho package configuration và dùng Actuator `env`/`configprops` nếu ứng dụng đã cấu hình, expose và bảo vệ phù hợp. Không nên công khai các endpoint này chỉ để tiện điều tra, vì chúng có thể tiết lộ thông tin cấu hình và giá trị nhạy cảm.

### Profile cũng là một điều kiện

Một bean có thể được khai báo:

~~~java
@Component
@Profile("production")
public class ProductionPaymentGateway implements PaymentGateway {
}
~~~

Nếu ứng dụng chạy với profile `prod` thay vì `production`, bean này không được đăng ký. Conditions report có thể giúp nhận ra cấu hình liên quan, còn startup log cho biết active profiles thực tế.

Hãy kiểm tra chính xác tên profile và nơi kích hoạt nó. Maven `-Pprod` hoặc Gradle `-PtargetEnv=prod` không tự động kích hoạt Spring profile `prod`.

## 14. Kiểm thử tái hiện: biến giả thuyết thành một test nhỏ

Sau khi log, conditions report và dependency tree tạo ra giả thuyết, hãy viết một test có thể tái hiện lỗi mà không phụ thuộc toàn bộ môi trường nếu không cần.

Ví dụ giả thuyết:

> Auto-configuration chỉ tạo `PaymentGateway` khi `app.payment.enabled=true` và `PaymentClient` có mặt trên classpath.

Có thể dùng `ApplicationContextRunner` để kiểm tra điều kiện auto-configuration trong một context nhỏ.

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            PaymentAutoConfiguration.class
                    ));

    @Test
    void createsGatewayWhenFeatureIsEnabled() {
        contextRunner
                .withPropertyValues("app.payment.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                });
    }

    @Test
    void doesNotCreateGatewayWhenFeatureIsDisabled() {
        contextRunner
                .withPropertyValues("app.payment.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(PaymentGateway.class);
                });
    }
}
~~~

Đây là ví dụ minh họa; auto-configuration thật cần các class và dependency tương ứng. Nếu điều kiện có `@ConditionalOnClass`, test classpath phải được cấu hình đúng để kiểm tra cả trường hợp có và không có class.

### Vì sao ApplicationContextRunner hữu ích?

Nó cho phép:

- Tạo một context nhỏ cho từng test.
- Thêm property bằng `withPropertyValues`.
- Đăng ký cấu hình hoặc auto-configuration có mục tiêu.
- Kiểm tra bean có/không có.
- Quan sát context startup failure.
- Tránh khởi động web server, database và toàn bộ ứng dụng khi không cần.

Mỗi lời gọi `run(...)` tạo một context độc lập cho scenario tương ứng. Test không cần phụ thuộc vào một test trước đó để thay đổi profile hoặc bean state.

### Kiểm tra startup failure

Ví dụ khi cấu hình bắt buộc bị thiếu:

~~~java
@Test
void failsWhenRequiredPropertyIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(PaymentClientConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure()).isNotNull();
            });
}
~~~

Test này xác nhận context thất bại khi cấu hình yêu cầu không có. Nếu cần kiểm tra chính xác loại lỗi hoặc property name, có thể duyệt cause chain và assert thông tin ổn định; tránh khóa test vào toàn bộ stack trace vì format có thể thay đổi giữa phiên bản framework.

## 15. Chọn test phù hợp với phạm vi lỗi

Không phải mọi lỗi Spring Boot đều cần `@SpringBootTest`.

| Vấn đề cần tái hiện | Loại test phù hợp |
|---|---|
| Logic thuần của service | JUnit + Mockito/fake, không cần Spring |
| Điều kiện auto-configuration | `ApplicationContextRunner` |
| Bean wiring trong toàn ứng dụng | `@SpringBootTest` hoặc context test có phạm vi phù hợp |
| MVC mapping và serialization | `@WebMvcTest` |
| JPA repository và mapping | `@DataJpaTest` |
| JSON serialization | `@JsonTest` |
| HTTP client adapter | Mock server hoặc `@RestClientTest` phù hợp |
| Tương tác database thật | Integration test với database test riêng/Testcontainers |
| Nhiều thành phần chạy cùng nhau | Integration hoặc end-to-end test |

Một test nhỏ hơn thường làm nguyên nhân lỗi rõ hơn. Nhưng nếu lỗi phụ thuộc AOP proxy, servlet container, transaction manager hoặc auto-configuration tích hợp, unit test thuần không thể xác nhận đầy đủ hành vi đó. Chọn test scope theo cơ chế đang nghi ngờ.

### @WebMvcTest

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        // Stub service và kiểm tra HTTP response.
    }
}
~~~

`@MockitoBean` có trong các phiên bản Spring Framework mới; các dự án Spring Boot cũ hơn có thể sử dụng `@MockBean`. Chọn annotation theo version đang dùng.

Test slice tập trung vào MVC infrastructure và controller được chỉ định. Nó không nhằm kiểm tra toàn bộ database hoặc mọi service integration của ứng dụng.

### @DataJpaTest

Ví dụ:

~~~java
@DataJpaTest
class OrderRepositoryTests {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrder() {
        // Tạo entity, lưu và đọc lại.
    }
}
~~~

Test slice này tập trung vào JPA components. Tùy dependency và cấu hình, Spring Boot có thể chọn embedded database thay cho database production; nếu cần xác nhận hành vi trên đúng engine, hãy cấu hình database test phù hợp hoặc sử dụng Testcontainers.

## 16. Dùng test để xác nhận dependency problem

Nếu dependency graph gợi ý một version conflict, không nên chỉ viết test mock để chứng minh service vẫn gọi collaborator. Test mock không load class implementation thật, nên có thể bỏ lỡ `NoSuchMethodError` hoặc lỗi linkage.

Cần test ở tầng có sử dụng dependency thật:

- Tạo ApplicationContext có auto-configuration cần thiết.
- Gọi một đường code nhỏ đi qua API của thư viện.
- Chạy test với runtime classpath giống deployment.
- Với lỗi chỉ xảy ra khi đóng gói, chạy executable archive hoặc một smoke test trên artifact được tạo ra.

Ví dụ, nếu lỗi xảy ra khi chạy JAR nhưng test trong IDE pass, có thể do compile/runtime classpath hoặc packaging khác nhau. Một integration test trên classpath Gradle không nhất thiết chứng minh executable JAR chứa đúng mọi dependency.

Đối với lỗi binary compatibility, test nên khởi tạo và gọi đúng method gây lỗi bằng version thực tế đã resolve, thay vì chỉ kiểm tra bean có tồn tại.

## 17. Kiểm thử integration với dependency bên ngoài

Nếu root cause giả thuyết nằm ở adapter gọi HTTP hoặc database, hãy tạo test cho **adapter đó** với hạ tầng kiểm thử có thể kiểm soát.

Ví dụ HTTP:

~~~text
Service unit test
    |
    +--> Mock RoomAvailabilityPort
    |
    v
Kiểm tra logic đặt chỗ

Adapter integration test
    |
    +--> HttpRoomAvailabilityAdapter thật
    |
    +--> Mock HTTP server trên port động
    |
    v
Kiểm tra URL, header, JSON, timeout và lỗi HTTP
~~~

Mock server giúp tái hiện response cụ thể:

- HTTP 200 với JSON hợp lệ.
- HTTP 404 hoặc 409.
- HTTP 500.
- Timeout hoặc connection refused.
- Payload không đúng schema.

Test không cần gọi staging/production API, không phụ thuộc credential cá nhân và không bị rate limit của dịch vụ thật.

Nếu cần kiểm tra contract giữa hai hệ thống, có thể dùng contract test riêng. Unit test của business service không nên bị kéo vào để thực hiện vai trò đó.

## 18. Dùng Testcontainers khi cần database hoặc broker thật

Một số lỗi chỉ xuất hiện với database engine thật: SQL dialect, locking, index, transaction isolation, constraint hoặc migration. Khi đó, mock repository không đủ.

Testcontainers có thể tạo database/container riêng cho integration test:

~~~text
Test setup
    |
    v
Start PostgreSQL test container
    |
    v
Spring context + real repository
    |
    v
Execute query / transaction
    |
    v
Assert result
    |
    v
Stop container and clean test data
~~~

Testcontainers tăng tính thực tế nhưng cũng làm test chậm hơn và cần Docker hoặc runtime container tương thích trong môi trường chạy. Chỉ dùng khi hạ tầng thật là một phần của câu hỏi cần kiểm chứng.

Nếu lỗi xảy ra vì service bên ngoài không liên quan, thêm container cho service đó sẽ mở rộng phạm vi mà không giải quyết nguyên nhân thiết kế. Hãy chỉ khởi tạo những dịch vụ mà test thực sự cần.

## 19. Reproduce profile và property đúng như môi trường lỗi

Một test tái hiện phải sử dụng đúng property/profile liên quan. Nếu production lỗi khi active profile `prod`, test chỉ dùng default profile có thể không tái hiện được.

Với integration test:

~~~java
@SpringBootTest(properties = {
        "app.payment.enabled=true",
        "app.payment.timeout=2s"
})
@ActiveProfiles("test")
class PaymentStartupTests {
}
~~~

Hoặc dùng `@DynamicPropertySource` để cung cấp địa chỉ runtime của container:

~~~java
@DynamicPropertySource
static void paymentProperties(DynamicPropertyRegistry registry) {
    registry.add("app.payment.base-url", mockServer::getUrl);
}
~~~

Ví dụ cần khai báo mock server và lifecycle thực tế tương ứng. `@DynamicPropertySource` hữu ích khi property chỉ có sau khi test infrastructure được khởi động, như port động của Testcontainers hoặc mock server.

Khi tái hiện lỗi từ môi trường thật, đừng copy secret production vào test. Hãy thay bằng giá trị test tương đương về cấu trúc, hoặc dùng credential riêng có quyền hạn giới hạn.

## 20. Xác nhận property nào thực sự có hiệu lực

Một nguyên nhân phổ biến là test và ứng dụng nhận property khác nhau dù cùng file cấu hình.

Spring Boot có nhiều property source, ví dụ:

- Config Data trong classpath.
- Config Data bên ngoài.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Test properties và dynamic properties.

Giá trị ở nguồn ưu tiên cao hơn có thể ghi đè giá trị ở nguồn thấp hơn.

Ví dụ:

~~~yaml
app:
  payment:
    enabled: false
~~~

Nhưng test chạy:

~~~java
@SpringBootTest(properties = "app.payment.enabled=true")
~~~

thì giá trị test override có thể khiến auto-configuration match, khác với môi trường mặc định.

Nếu cần quan sát giá trị hiệu lực, có thể dùng `Environment` trực tiếp trong test:

~~~java
@Autowired
Environment environment;

@Test
void printsEffectiveFlag() {
    assertEquals(
            "true",
            environment.getProperty("app.payment.enabled")
    );
}
~~~

Không nên dùng test chỉ để in giá trị rồi bỏ qua assertion. Hãy biến giá trị mong đợi thành assertion có ý nghĩa và cung cấp test properties rõ ràng.

## 21. Tái hiện lỗi không có nghĩa hard-code workaround vào test

Khi lỗi xảy ra, có thể thử thêm property, exclude auto-configuration hoặc thay dependency để xác định giả thuyết. Nhưng cần phân biệt:

- **Test reproducer:** tối thiểu hóa đầu vào để tái hiện lỗi.
- **Fix:** thay đổi code, dependency hoặc cấu hình để giải quyết root cause.
- **Regression test:** giữ lại điều kiện tái hiện để xác nhận lỗi không quay lại.

Ví dụ, nếu bean không xuất hiện do property sai tên, regression test nên xác nhận tên property và giá trị đúng kích hoạt bean. Không nên thêm một mock bean thay thế để test pass nếu mục tiêu thật là kiểm tra auto-configuration.

Nếu lỗi do version conflict, test cần chạy với dependency graph đã sửa và exercise API gây lỗi. Không nên exclude một thư viện không liên quan chỉ để làm cây dependency ngắn hơn.

## 22. Quy trình chẩn đoán kết hợp bốn nguồn

Một workflow thực dụng có thể tiến hành như sau.

### Bước 1 — Thu thập triệu chứng

Ghi lại command, môi trường, profile, version và thời điểm lỗi. Giữ phần log quanh exception đầu tiên và toàn bộ cause chain cần thiết.

### Bước 2 — Bật chẩn đoán có mục tiêu

Chạy lại với `--debug` để lấy conditions report. Nếu cần, tăng logger cho package liên quan thay vì bật TRACE toàn hệ thống.

### Bước 3 — Tìm điều kiện không khớp

Xác định auto-configuration hoặc bean nào đáng lẽ phải xuất hiện. Xem positive/negative matches, exclusions và property condition.

### Bước 4 — Xác minh classpath

Nếu report nói thiếu class, hoặc log có lỗi linkage, chạy Maven `dependency:tree` hoặc Gradle `dependencyInsight` trên đúng configuration. Kiểm tra cả runtime classpath, không chỉ compile.

### Bước 5 — Đối chiếu cấu hình hiệu lực

Kiểm tra active profiles, property sources, external files và environment variables. Xác nhận điều kiện nhận đúng giá trị mong đợi.

### Bước 6 — Viết reproducer nhỏ

Chọn `ApplicationContextRunner` cho auto-configuration, unit test cho business logic, slice test cho MVC/JPA hoặc integration test cho dependency thật.

### Bước 7 — Xác nhận root cause

Test phải thất bại với điều kiện gây lỗi và thành công khi áp dụng sửa chữa. Nếu test không thể tái hiện, hãy xem lại giả thuyết hoặc sự khác biệt môi trường.

### Bước 8 — Chạy regression test và kiểm tra artifact

Chạy test mục tiêu, sau đó test liên quan. Nếu lỗi runtime/package, xác nhận dependency graph và chạy artifact được đóng gói giống cách triển khai.

### Bước 9 — Ghi lại bằng chứng

Ghi rõ:

- Triệu chứng ban đầu.
- Condition hoặc dependency gây lỗi.
- Root cause đã xác nhận.
- Thay đổi sửa chữa.
- Test tái hiện trước/sau.
- Version và môi trường đã kiểm chứng.

Bằng chứng này giúp người khác hiểu vì sao thay đổi được thực hiện, thay vì chỉ thấy một dependency được thêm vào hoặc một property được đổi.

## 23. Ví dụ điều tra hoàn chỉnh: bean không được auto-configure

Giả sử ứng dụng cần bean `PaymentGateway` nhưng startup báo thiếu bean.

**Log:**

~~~text
Parameter 0 of constructor in CheckoutService
required a bean of type PaymentGateway that could not be found.
~~~

**Conditions report:**

~~~text
PaymentAutoConfiguration did not match:
   @ConditionalOnClass did not find
   'com.example.payment.PaymentClient'
~~~

**Dependency tree Maven:**

~~~bash
mvn dependency:tree -Dincludes=com.example:payment-client
~~~

Không có dependency tương ứng. Trong POM, adapter chỉ được khai báo ở một Maven profile không được kích hoạt ở môi trường này.

**Giả thuyết:** runtime artifact thiếu thư viện payment client do build profile hoặc dependency scope.

**Reproducer:** tạo một context test với auto-configuration và xác nhận bean không xuất hiện khi classpath thiếu dependency; sau đó bổ sung dependency trong test fixture phù hợp và xác nhận điều kiện class khớp. Với một thư viện bên thứ ba thật, test nên sử dụng artifact thực tế thay vì chỉ tạo một class giả có cùng tên.

**Fix:** điều chỉnh dependency để nằm trên runtime classpath của module ứng dụng, dùng version được dependency management kiểm soát.

**Regression test:** khởi tạo context và xác nhận `PaymentGateway` được đăng ký với cấu hình cần thiết; đồng thời kiểm tra runtime dependency graph trong build.

Chuỗi bằng chứng kết hợp log → conditions → dependency tree → reproducer giúp giải thích nguyên nhân cụ thể. Chỉ thêm một bean thủ công có thể làm startup hết lỗi nhưng bỏ qua việc adapter thực tế bị thiếu.

## 24. Ví dụ điều tra version conflict: NoSuchMethodError

Giả sử ứng dụng khởi động nhưng khi xử lý request lại có:

~~~text
java.lang.NoSuchMethodError:
  com.example.json.JsonMapper.configure(...)
~~~

**Log:** cho biết class và method bị thiếu.

**Dependency tree:** phát hiện hai dependency kéo các version khác nhau của `json-core`.

**DependencyInsight:** cho biết Gradle chọn version nào và lý do chọn.

**Giả thuyết:** code được compile với API mới nhưng runtime load API cũ hoặc một variant không tương thích.

**Reproducer:** viết test/integration test gọi đúng API qua dependency thật, chạy trên runtime classpath giống ứng dụng.

**Fix:** align version theo BOM hoặc constraint tương thích, loại bỏ pin version riêng không cần thiết, rồi chạy test và executable artifact.

Không nên chỉ thêm dependency version mới mà không xem conflict resolution. Build có thể vẫn chọn version cũ do constraint hoặc dependency management.

## 25. Ví dụ điều tra test thất bại khi load context

Giả sử `@SpringBootTest` thất bại khi tạo bean `AnalyticsClient` vì không thể kết nối tới một endpoint bên ngoài. Nhưng test đang kiểm tra quy tắc tính tổng đơn hàng.

Các bằng chứng:

- Log cho biết lỗi xảy ra ở `AnalyticsClient` trong startup.
- Conditions report cho biết auto-configuration của analytics được bật bởi property.
- Dependency tree cho biết SDK analytics hiện diện.
- Test source không sử dụng analytics trong nghiệp vụ đang kiểm tra.

Root cause không nhất thiết là service tính tổng sai. **Phạm vi context đang kéo một integration không liên quan vào test.**

Có thể xử lý bằng:

- Unit test trực tiếp service với constructor injection và fake/mock collaborator.
- Test slice hoặc context test nhỏ hơn.
- Cấu hình test tắt analytics nếu ứng dụng hỗ trợ tùy chọn đó.
- Thay adapter analytics bằng bean test có hành vi xác định nếu context vẫn cần collaborator.

Nếu mục tiêu là kiểm tra analytics integration, hãy viết test riêng với mock server hoặc môi trường test của SDK. Không nên bắt test tính tổng phụ thuộc vào uptime của analytics.

## 26. Các công cụ bổ trợ khi cần thêm bằng chứng

Bốn nguồn chính có thể được bổ sung bởi những công cụ phù hợp với câu hỏi.

| Công cụ | Dùng khi cần |
|---|---|
| Actuator `conditions` | Xem điều kiện auto-configuration trong ứng dụng đang chạy, nếu endpoint được bật và expose |
| Actuator `beans` | Xác định bean nào thực sự tồn tại |
| Actuator `env` | Quan sát property sources và giá trị hiệu lực, với bảo vệ phù hợp |
| Actuator `configprops` | Kiểm tra binding của configuration properties |
| Actuator `loggers` | Quan sát hoặc thay đổi log level runtime khi được phép |
| `jdeps` | Phân tích dependency ở mức bytecode/module của Java |
| `jar tf` | Xem nội dung archive đã đóng gói |
| Build scan | Phân tích dependency resolution và hiệu năng build Gradle khi được cấu hình |
| Thread dump | Điều tra deadlock, thread starvation hoặc tác vụ bị treo |
| Testcontainers | Tái hiện integration cần database/broker thật |

Không cần chạy mọi công cụ cho mọi lỗi. Hãy chọn theo giả thuyết: lỗi auto-configuration thì xem conditions; lỗi linkage thì xem dependency graph và archive; lỗi context test thì thu hẹp context và tạo reproducer.

### Xem nội dung executable JAR

Nếu ứng dụng chạy từ JAR, có thể kiểm tra:

~~~bash
jar tf build/libs/app.jar
~~~

Với Spring Boot executable JAR, xem các nhóm như `BOOT-INF/classes/` và `BOOT-INF/lib/`. Một dependency có trong compile classpath chưa chắc đã được đóng gói đúng; kiểm tra archive giúp xác nhận kết quả packaging.

### Kiểm tra Java dependency

`jdeps` thuộc JDK và có thể phân tích dependency class/module ở mức bytecode:

~~~bash
jdeps --summary build/libs/app.jar
~~~

Khả năng phân tích nested dependency trong Spring Boot executable archive có giới hạn tùy layout và phiên bản công cụ. Đừng xem `jdeps` như sự thay thế cho Maven/Gradle dependency tree; hai công cụ quan sát các lớp khác nhau.

## 27. Bảo mật khi thu thập và chia sẻ diagnostics

Log, conditions report và Actuator có thể chứa thông tin về hệ thống:

- Tên class, bean và package nội bộ.
- Đường dẫn file và tên host.
- Property key, URL hoặc metadata kết nối.
- Stack trace có dữ liệu request.
- Dependency và version đang sử dụng.
- Chi tiết về hạ tầng nội bộ.

Trước khi gửi log hoặc report ra ngoài team, hãy loại bỏ password, token, cookie, private key, dữ liệu cá nhân và thông tin nhạy cảm khác. Không công khai endpoint `env`, `configprops`, `beans` hoặc `conditions` chỉ để tiện debug.

Bật DEBUG/TRACE cũng có thể làm tăng lượng dữ liệu log và để lộ giá trị không nên ghi. Chỉ bật trong phạm vi cần thiết, giới hạn thời gian, lưu trữ theo chính sách và tắt sau khi điều tra.

Trong production, ưu tiên truy cập diagnostics qua kênh vận hành có xác thực, phân quyền và network policy rõ ràng.

## 28. Những sai lầm thường gặp

### Chỉ nhìn exception ngoài cùng

Exception ngoài cùng có thể chỉ nói bean nào không tạo được. Root cause có thể là property sai, dependency thiếu, database timeout hoặc một exception trong constructor. Hãy lần theo cause chain và log trước lỗi.

### Bật DEBUG cho toàn bộ ứng dụng

Điều này có thể tạo quá nhiều log và che mất thông tin quan trọng. Bật theo package hoặc logger có liên quan; dùng `--debug` cho conditions report.

### Thấy dependency trong source rồi cho rằng runtime đã có

Khai báo trong build file có thể thuộc compile-only, test-only, optional, profile không active hoặc bị exclude. Kiểm tra đúng runtime configuration và executable archive.

### Thấy class có mặt rồi kết luận auto-configuration phải match

`@ConditionalOnClass` chỉ là một trong nhiều điều kiện. Property, bean, web application type, resource và exclusions vẫn có thể làm cấu hình không được áp dụng.

### Thêm dependency ngẫu nhiên để sửa NoClassDefFoundError

Dependency mới có thể làm version conflict nghiêm trọng hơn. Xác định class thuộc artifact nào và xem đường đi dependency trước khi thay đổi.

### Dùng @SpringBootTest cho mọi reproducer

Một context đầy đủ có thể kéo nhiều integration không liên quan vào test. Chọn unit test, ApplicationContextRunner hoặc test slice khi chúng đủ kiểm tra giả thuyết.

### Chỉ kiểm tra test xanh mà không chạy đúng artifact

Lỗi có thể chỉ xuất hiện trong executable JAR vì runtime classpath/packaging khác. Khi triệu chứng xảy ra sau deploy, cần xác nhận archive và cách khởi chạy tương ứng.

### Sửa lỗi bằng cách loại auto-configuration mà không hiểu hậu quả

Exclude có thể làm ứng dụng khởi động nhưng cũng bỏ luôn DataSource, web infrastructure hoặc một integration cần thiết. Chỉ loại khi kiến trúc thực sự không cần cấu hình đó và có test chứng minh.

### Chạy lại test đến khi pass

Một test flaky có thể pass ngẫu nhiên. Rerun chỉ giúp thu thập thêm bằng chứng; cần tìm shared state, race condition, timing hoặc dependency ngoài gây ra sự không ổn định.

## 29. Mẫu ghi nhận một lần điều tra

Một bản ghi ngắn có thể dùng cấu trúc:

~~~text
Symptom:
  Application startup fails with UnsatisfiedDependencyException.

Environment:
  Java:
  Spring Boot:
  Build tool:
  Active profiles:
  Command:

Log evidence:
  First relevant exception:
  Root cause:
  Related startup messages:

Conditions report:
  Auto-configuration:
  Positive/negative condition:
  Exclusions:

Dependency evidence:
  Artifact:
  Selected version:
  Dependency path:
  Runtime scope/configuration:

Reproducer:
  Test class:
  Minimal properties:
  Expected result:
  Actual result:

Root cause:
  ...

Fix:
  ...

Regression evidence:
  Test command:
  Result:
  Packaged artifact check:
~~~

Mẫu này giúp người đọc kiểm tra lại bằng chứng thay vì phải suy luận từ một dòng “đã sửa dependency”.

## 30. Quy trình tổng hợp

Khi Spring Boot có lỗi khó xác định, hãy đi từ bằng chứng rộng tới reproducer nhỏ:

1. Mô tả triệu chứng và xác định giai đoạn xảy ra lỗi.
2. Đọc startup/runtime logs, stack trace và cause chain.
3. Bật `--debug` để lấy conditions evaluation report; tăng logger có mục tiêu nếu cần.
4. Xác định auto-configuration, bean hoặc property condition không khớp.
5. Kiểm tra Maven dependency tree hoặc Gradle dependencyInsight trên đúng compile/runtime/test configuration.
6. Đối chiếu version, scope, profile và property sources với môi trường lỗi.
7. Viết reproducer nhỏ bằng unit test, ApplicationContextRunner, test slice hoặc integration test tùy cơ chế.
8. Áp dụng sửa chữa dựa trên root cause và giữ regression test.
9. Nếu lỗi chỉ xảy ra khi đóng gói, kiểm tra archive và chạy đúng executable artifact.
10. Lưu bằng chứng, giảm log debug và bảo vệ thông tin nhạy cảm.

**Log cho biết điều gì đã xảy ra; conditions report cho biết vì sao Spring chọn hoặc bỏ qua cấu hình; dependency tree cho biết runtime/build classpath được hình thành thế nào; kiểm thử tái hiện xác nhận giả thuyết và giữ lỗi không quay lại.** Kết hợp bốn nguồn theo đúng câu hỏi giúp chẩn đoán có căn cứ, tránh sửa ngẫu nhiên và tạo ra một bản sửa có thể kiểm chứng.

