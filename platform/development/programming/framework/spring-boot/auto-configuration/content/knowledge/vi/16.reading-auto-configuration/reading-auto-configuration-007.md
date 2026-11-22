# Lập bảng classpath, thuộc tính, bean người dùng và kết quả dự kiến

## 1. Vì sao cần lập bảng trước khi đọc sâu auto-configuration?

Spring Boot không bật một auto-configuration chỉ vì thư viện có mặt trong project. Spring quyết định đăng ký từng cấu hình và từng bean dựa trên nhiều điều kiện cùng lúc: class có trên runtime classpath hay không, property hiệu lực có đúng giá trị hay không, bean do ứng dụng khai báo đã tồn tại hay chưa, ứng dụng là servlet/reactive/non-web, resource cần thiết có tồn tại không và cấu hình có bị loại trừ hay không.

Khi một bean không xuất hiện, chỉ nhìn một annotation thường dẫn đến kết luận thiếu. Ví dụ:

- Dependency đã có trong build file, nhưng class không nằm trên runtime classpath.
- Property trong application.yml là true, nhưng profile hoặc biến môi trường ghi đè thành false.
- Auto-configuration có @ConditionalOnMissingBean, nhưng ứng dụng đã cung cấp bean tương thích nên bean mặc định chủ động back off.
- Điều kiện class-level đúng, nhưng điều kiện trên một phương thức @Bean không khớp.
- Cấu hình bị loại trừ qua exclude hoặc spring.autoconfigure.exclude.
- Condition khớp và bean definition được đăng ký, nhưng instance không khởi tạo được vì thiếu dependency hoặc lỗi factory method.

Cách làm hiệu quả là lập **ma trận đầu vào → điều kiện → kết quả dự kiến** trước khi thay đổi dependency hay property. Bảng buộc ta ghi rõ điều kiện nào phải đúng, giá trị thực tế lấy từ đâu và bean nào đáng lẽ xuất hiện.

Bài học dùng baseline **Spring Boot 3.3.x, Java 17+** và tập trung vào các điều kiện thường gặp:

- @ConditionalOnClass / @ConditionalOnMissingClass
- @ConditionalOnProperty
- @ConditionalOnBean / @ConditionalOnMissingBean
- @ConditionalOnSingleCandidate
- @ConditionalOnWebApplication / @ConditionalOnNotWebApplication
- @ConditionalOnResource
- @ConditionalOnExpression và custom Condition

## 2. Mô hình tư duy: từ đầu vào đến bean cuối cùng

Khi đọc một auto-configuration, lần theo chuỗi sau:

1. **Ứng viên cấu hình:** Spring Boot có tìm thấy lớp auto-configuration trong danh sách imports không? Có bị loại trừ không?
2. **Classpath:** các class mà condition yêu cầu có thể được tải từ runtime classpath không?
3. **Property:** property nào được đọc, giá trị hiệu lực là gì, default và matchIfMissing ra sao?
4. **User beans:** bean theo kiểu hoặc tên đã tồn tại trong BeanFactory chưa? Condition đang tìm ở context hiện tại hay cả context cha?
5. **Application type/resource:** ứng dụng có phải servlet/reactive/non-web không, resource bắt buộc có tồn tại không?
6. **Condition kết luận:** tất cả điều kiện trên lớp và phương thức bean có khớp không?
7. **Bean kết quả:** bean definition nào được đăng ký, tên gì, kiểu trả về nào, có bị điều kiện khác loại bỏ không?
8. **Runtime:** instance có khởi tạo thành công không, có dependency nào thiếu hoặc gây lỗi không?

Các điều kiện đặt đồng thời trên một lớp hoặc phương thức thường kết hợp theo logic **AND**: mọi condition liên quan phải khớp. Bên trong từng annotation cũng có quy tắc riêng. Ví dụ nhiều name của @ConditionalOnProperty đều phải đạt; nhiều kiểu trong @ConditionalOnBean đều phải được tìm thấy.

~~~text
AutoConfiguration.imports
          |
          v
Có bị exclude không? ---- Có ----> Không nạp cấu hình
          |
         Không
          v
Điều kiện classpath khớp?
          |
     Không +----> Bỏ qua cấu hình
          |
         Có
          v
Property / application type / resource khớp?
          |
     Không +----> Bỏ qua cấu hình
          |
         Có
          v
Điều kiện bean trên @Bean method khớp?
          |
     Không +----> Không đăng ký bean đó
          |
         Có
          v
Đăng ký bean definition
          |
          v
Khởi tạo instance theo dependency và lifecycle
~~~

Sơ đồ là cách rút gọn để phân tích. Spring xử lý condition trong nhiều giai đoạn của quá trình đăng ký cấu hình; class-level condition và method-level condition không nhất thiết được đánh giá cùng một lúc. Điều cần giữ là **đừng đồng nhất việc cấu hình được nạp, bean definition được đăng ký và instance được khởi tạo**.

## 3. Xác định đúng auto-configuration candidate

Trong Spring Boot 3.x, auto-configuration của thư viện được công bố qua file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng thường là tên đầy đủ của một lớp @AutoConfiguration. Khi đọc mã nguồn starter, tìm file imports trong JAR để xác định class có được Spring Boot khám phá hay không. Chỉ tìm thấy class Java trong dependency chưa đủ chứng minh nó đã được đưa vào danh sách auto-configuration.

Kiểm tra các cơ chế loại trừ:

~~~java
@SpringBootApplication(
    exclude = {MetricsAutoConfiguration.class}
)
public class Application {
}
~~~

Hoặc cấu hình property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.metrics.MetricsAutoConfiguration
~~~

Có thể loại trừ bằng excludeName khi muốn dùng tên class thay vì tham chiếu trực tiếp. Nếu auto-configuration không có trong imports, hoặc đã bị exclude, các condition bên trong nó không thể làm bean xuất hiện.

| Câu hỏi | Nơi kiểm tra | Kết quả cần ghi vào bảng |
|---|---|---|
| Class có trong AutoConfiguration.imports không? | JAR của starter, source dependency | Có/Không |
| Ứng dụng có exclude class không? | @SpringBootApplication, @EnableAutoConfiguration, property | Có/Không |
| Class có được import theo đường khác không? | @Import, component scan, test configuration | Ghi rõ đường nạp |
| Auto-configuration có bị giới hạn thứ tự không? | before, after, @AutoConfigureOrder | Ghi dependency cấu hình |
| Phiên bản dependency nào đang chạy? | Maven/Gradle dependency report | Ghi version thực tế |

Trong Boot 3, auto-configuration candidates được công bố qua file imports chuyên dụng. Không nên tìm spring.factories như nơi đăng ký auto-configuration mới theo cơ chế cũ. File đó vẫn có thể xuất hiện cho các extension point khác.

## 4. Cột classpath: thư viện có mặt hay không?

### 4.1. @ConditionalOnClass

Dùng khi auto-configuration chỉ có ý nghĩa nếu một thư viện hoặc API có trên classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ReportClient")
class ReportClientAutoConfiguration {
    // Các bean tích hợp với ReportClient
}
~~~

Thuộc tính name là tên đầy đủ của class. Cách này hữu ích khi class là dependency tùy chọn, tránh tham chiếu trực tiếp một type có thể không tồn tại. @ConditionalOnClass(ReportClient.class) cũng dùng được khi class luôn có thể được tham chiếu an toàn ở metadata của cấu hình.

**Điểm quan trọng:** condition class-level có thể được đọc từ annotation metadata mà không cần nạp class tùy chọn. Nếu đặt condition trên một method @Bean có return type hoặc chữ ký tham chiếu class tùy chọn, JVM có thể phải nạp class trước khi condition method có cơ hội bảo vệ. Với dependency thực sự optional, nên tách một nested/static configuration được bảo vệ bằng @ConditionalOnClass, để các method dùng type đó nằm trong cấu hình tách biệt.

~~~java
@AutoConfiguration
class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.ReportClient")
    static class VendorClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        ReportGateway reportGateway() {
            return new VendorReportGateway();
        }
    }
}
~~~

Đây là ví dụ cấu trúc; ReportGateway và VendorReportGateway là các type của ứng dụng/starter. Cấu hình con chỉ được xử lý khi class tùy chọn có mặt. Hãy giữ code phụ thuộc vendor trong nhánh cấu hình được bảo vệ.

### 4.2. @ConditionalOnMissingClass

Dùng khi một cấu hình chỉ được kích hoạt nếu một class không có:

~~~java
@AutoConfiguration
@ConditionalOnMissingClass("com.vendor.legacy.LegacyClient")
class FallbackClientAutoConfiguration {
}
~~~

Điều kiện này phù hợp cho fallback khi thư viện cũ không được cài. Cần kiểm tra classpath thực tế, vì dependency bắc cầu (transitive dependency) có thể khiến class vẫn hiện diện dù nhóm ứng dụng không khai báo trực tiếp.

### 4.3. Phân biệt khai báo dependency và runtime classpath

Một dòng dependency trong build file chưa phải bằng chứng cuối cùng. Hãy xem cấu hình runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Hoặc với Maven:

~~~bash
./mvnw dependency:tree
~~~

Kiểm tra version được resolve, dependency bị exclude, scope, conflict version và class có nằm trong JAR runtime hay không. Trong container, kiểm tra artifact được build/deploy có cùng dependency set với môi trường dev.

Trong test, Spring Boot Test cung cấp FilteredClassLoader để mô phỏng một class không nhìn thấy được:

~~~java
runner.withClassLoader(new FilteredClassLoader(OptionalTransport.class));
~~~

Đây là cách kiểm tra classpath condition mà không cần tạo hai project build khác nhau. Tên class dùng trong @ConditionalOnClass(name=...) phải đúng với class được filter.

## 5. Cột property: ghi giá trị hiệu lực, không chỉ giá trị trong YAML

### 5.1. @ConditionalOnProperty

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "reporting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class ReportingAutoConfiguration {
}
~~~

Condition chỉ khớp khi property hiệu lực reporting.enabled có giá trị true theo havingValue. Vì matchIfMissing=false, property thiếu sẽ không khớp.

Nếu không chỉ định havingValue, property tồn tại và giá trị khác chuỗi false sẽ được coi là khớp. Đây là điểm dễ gây nhầm khi property có giá trị như off, no, 0 hoặc một chuỗi tùy ý. Khi ý định là boolean, khai báo havingValue="true" để thể hiện rõ hợp đồng.

matchIfMissing=true có nghĩa property không tồn tại vẫn được coi là khớp. Chỉ dùng khi default enable là quyết định có chủ đích.

### 5.2. Nhiều property trong một annotation

~~~java
@ConditionalOnProperty(
    prefix = "reporting",
    name = {"enabled", "export"},
    havingValue = "true"
)
~~~

Cả reporting.enabled và reporting.export đều phải khớp. Danh sách name không phải phép OR. Nếu cần logic OR, dùng condition lồng hoặc một Condition tùy chỉnh được kiểm thử rõ ràng.

@ConditionalOnProperty không phù hợp để kiểm tra một property dạng collection có ít nhất một phần tử. Với key như reporting.targets[0], hãy dùng @ConfigurationProperties hoặc Condition phù hợp thay vì giả định annotation phát hiện mọi phần tử collection.

### 5.3. Giá trị hiệu lực đến từ đâu?

Property trong application.yml không nhất thiết là giá trị cuối cùng. Các nguồn có thể ghi đè lẫn nhau: command-line arguments, system properties, environment variables, config data, profile-specific files, imported config và các PropertySource khác.

Ví dụ YAML:

~~~yaml
reporting:
  enabled: false
~~~

Nhưng môi trường triển khai đặt:

~~~bash
REPORTING_ENABLED=true
~~~

Spring Boot có relaxed binding nên tên biến môi trường tương ứng property reporting.enabled; giá trị cuối cùng có thể là true tùy property source precedence. Vì vậy trong bảng phải ghi **effective value** lấy từ Environment, cùng nguồn tạo ra nó, thay vì chỉ copy YAML.

Ghi rõ các cột:

- Property key chính xác.
- Giá trị mặc định trong annotation hoặc @ConfigurationProperties.
- Giá trị hiệu lực tại runtime.
- Nguồn cung cấp giá trị (profile file, env var, command-line, config server...).
- Điều kiện so khớp (havingValue, matchIfMissing).
- Kết quả mong đợi.

Không paste secret hoặc password vào bảng chẩn đoán. Chỉ ghi trạng thái có/không, nguồn, profile hoặc giá trị đã mask nếu không cần giá trị gốc.

## 6. Cột user bean: có bean tương thích hay chưa?

### 6.1. @ConditionalOnMissingBean

Đây là mẫu phổ biến để auto-configuration cung cấp bean mặc định nhưng nhường chỗ cho ứng dụng:

~~~java
@Bean
@ConditionalOnMissingBean(ReportGateway.class)
DefaultReportGateway reportGateway() {
    return new DefaultReportGateway();
}
~~~

Nếu BeanFactory đã biết một bean tương thích ReportGateway trước khi condition được đánh giá, bean mặc định sẽ back off. Đây là **kết quả thành công có chủ đích**, không phải lỗi auto-configuration.

Đọc condition theo đúng tiêu chí:

- value/type: tìm theo kiểu bean.
- name: tìm theo bean name.
- annotation: tìm bean có annotation tương ứng.
- ignored/ignoredType: loại một số kiểu khỏi phép kiểm tra missing.
- search: quyết định có xét context cha trong context hierarchy hay không.

Không nhầm @ConditionalOnMissingBean với @Primary: condition missing quyết định có đăng ký bean mặc định hay không; @Primary quyết định ứng viên nào được ưu tiên khi injection theo kiểu có nhiều bean phù hợp.

### 6.2. @ConditionalOnBean

Dùng khi một bean chỉ có ý nghĩa khi dependency đã được đăng ký:

~~~java
@Bean
@ConditionalOnBean(ReportGateway.class)
ReportHealthIndicator reportHealthIndicator(ReportGateway gateway) {
    return new ReportHealthIndicator(gateway);
}
~~~

Condition này kiểm tra bean definitions/metadata mà container đã xử lý, không đòi instance phải được khởi tạo trước. Nếu cần nhiều kiểu trong value, mọi yêu cầu phải được đáp ứng. Không dùng nó để kiểm tra getter hoặc trạng thái mutable bên trong bean.

### 6.3. @ConditionalOnSingleCandidate

Dùng khi cần một ứng viên duy nhất hoặc một ứng viên chính có thể xác định được:

~~~java
@Bean
@ConditionalOnSingleCandidate(ReportGateway.class)
ReportFacade reportFacade(ReportGateway gateway) {
    return new ReportFacade(gateway);
}
~~~

Nếu có một bean phù hợp, hoặc có nhiều bean nhưng Spring xác định được một primary candidate, condition có thể khớp. Nếu nhiều ứng viên ngang nhau và không có ứng viên chính, condition không khớp. Đây là khác biệt so với @ConditionalOnBean, vốn chỉ kiểm tra có bean phù hợp.

### 6.4. Thứ tự bean definition ảnh hưởng condition

Bean conditions chỉ nhìn thấy những bean definitions đã được xử lý tới thời điểm đánh giá. Vì vậy Spring Boot khuyến nghị dùng @ConditionalOnBean và @ConditionalOnMissingBean trên auto-configuration, vốn được xử lý sau user bean definitions. Khi auto-configuration A phụ thuộc bean do auto-configuration B cung cấp, có thể dùng @AutoConfiguration(after = B.class) để sắp thứ tự definition.

after không có nghĩa instance của bean B được khởi tạo trước. Thứ tự tạo instance được quyết định bởi dependency graph và @DependsOn. Hãy ghi riêng hai điều này nếu chẩn đoán liên quan cả condition lẫn lifecycle.

## 7. Các cột điều kiện bổ sung

### 7.1. Loại ứng dụng: servlet, reactive hay non-web

Một cấu hình có thể dùng:

- @ConditionalOnWebApplication(type = SERVLET) cho servlet web application.
- @ConditionalOnWebApplication(type = REACTIVE) cho reactive web application.
- @ConditionalOnNotWebApplication cho ứng dụng không phải web.

Đừng kết luận chỉ dựa trên việc có dependency spring-boot-starter-web trong file build; kiểm tra runtime classpath và WebApplicationType mà Spring Boot thực sự chọn. Nếu cả MVC và WebFlux cùng có mặt, lựa chọn loại ứng dụng còn phụ thuộc cấu hình và cách Boot xác định context.

### 7.2. Resource có mặt hay không

@ConditionalOnResource(resources = "classpath:report-defaults.yml") yêu cầu resource tồn tại theo cơ chế resource loading của Spring. Resource có thể đến từ src/main/resources, dependency JAR hoặc classpath runtime khác. Nếu resource ở filesystem, ghi rõ vị trí và cách đóng gói/deploy.

### 7.3. SpEL và custom Condition

@ConditionalOnExpression cho phép kiểm tra biểu thức SpEL, nhưng không nên tham chiếu bean như @settings.enabled: điều đó có thể khởi tạo bean rất sớm trong context refresh và làm bean bỏ lỡ post-processing như @ConfigurationProperties binding. Với logic phức tạp, dùng Condition đọc Environment/metadata, tránh lấy instance bean trong lúc condition chạy.

Custom Condition cần trả về quyết định nhất quán và có thể giải thích. Nếu cần báo lý do match/no-match rõ ràng, có thể kế thừa SpringBootCondition và tạo ConditionOutcome/ConditionMessage; đừng log ngẫu nhiên hoặc truy cập service trong matches().

## 8. Ma trận chính: classpath × property × user bean

Giả sử starter có auto-configuration:

- Chỉ hoạt động khi class example.matrix.AutoConfigurationMatrixTests$OptionalTransport có trên classpath.
- Chỉ bật khi reporting.enabled=true.
- Tạo DefaultReportGateway nếu ứng dụng chưa cung cấp bean ReportGateway.

Mã minh họa:

~~~java
package example.matrix;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "example.matrix.AutoConfigurationMatrixTests$OptionalTransport")
@ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportGateway.class)
    DefaultReportGateway reportGateway() {
        return new DefaultReportGateway();
    }
}
~~~

Các interface/implementation ReportGateway, DefaultReportGateway và marker OptionalTransport là các type của ví dụ. Trong starter thực tế, OptionalTransport thường thuộc thư viện ngoài và không cần được định nghĩa trong module auto-configuration. Để tránh lỗi nạp class tùy chọn, condition dùng name và cấu hình được cô lập.

### 8.1. Bảng chân trị 3 đầu vào

Ký hiệu:

- C: optional class có trên runtime classpath.
- P: property hiệu lực reporting.enabled bằng true.
- U: user bean kiểu ReportGateway đã được xử lý.
- D: bean mặc định DefaultReportGateway được đăng ký.
- X: bean tùy chỉnh của ứng dụng (nếu U = Có).

| C | P | U | D (default) | X (user) | Giải thích |
|---|---|---|---|---|---|
| Có | Có | Không | Có | Không | Mọi condition khớp; starter tạo default |
| Có | Có | Có | Không | Có | User bean làm @ConditionalOnMissingBean back off |
| Có | Không | Không | Không | Không | Property condition không khớp |
| Có | Thiếu | Không | Không | Không | matchIfMissing=false |
| Không | Có | Không | Không | Không | Class condition không khớp |
| Không | Có | Có | Không | Có | Auto-config bị bỏ qua; user bean vẫn tồn tại |
| Có | Không | Có | Không | Có | Property tắt default; user bean vẫn tồn tại |
| Không | Không | Không | Không | Không | Cả classpath và property đều không đạt |

Bảng chỉ xét các điều kiện đã nêu và giả định user configuration được xử lý bình thường. Nó chưa tính trường hợp auto-configuration bị exclude, bean creation lỗi, dependency khác thiếu hoặc context bị đóng trước khi hoàn tất. Ghi những trường hợp đó thành cột/ghi chú riêng, không gộp chúng vào C, P hoặc U.

### 8.2. Tách kết quả “không đăng ký” khỏi “đăng ký nhưng khởi tạo lỗi”

Khi bảng dự kiến D = Có nhưng context không có bean, cần xác định nó dừng ở đâu:

1. Auto-configuration không được load hoặc bị exclude.
2. Class condition không khớp.
3. Property condition không khớp.
4. Bean condition back off vì user bean.
5. Bean definition được đăng ký nhưng instance không tạo được vì dependency, constructor, factory method, binding hoặc lifecycle.
6. Bean được tạo nhưng không được tìm theo cách truy vấn đang dùng (scope, parent context, bean name/type, alias).

Không ghi chung “auto-config không chạy” nếu chưa xác định đúng giai đoạn. Condition report giải thích việc match/no-match; stack trace và bean creation logs giải thích lỗi ở giai đoạn tạo instance.

## 9. Mẫu bảng chẩn đoán dùng trong dự án

Khi đọc một auto-configuration thực tế, tạo bảng riêng cho từng bean quan trọng. Một dòng có thể mô tả một phương thức @Bean; nếu một lớp có nhiều bean với điều kiện khác nhau, đừng gộp chúng thành một kết quả chung.

| Trường | Nội dung cần ghi | Ví dụ |
|---|---|---|
| Auto-config | Tên đầy đủ của lớp | com.acme.ReportAutoConfiguration |
| Bean method | Phương thức và bean name | reportGateway() / reportGateway |
| Candidate | Có trong imports? Có bị exclude? | Có / Không |
| Classpath condition | Tên class và kết quả | com.vendor.sdk.ReportClient / Có |
| Property condition | Key, havingValue, matchIfMissing | reporting.enabled / true / false |
| Effective property | Giá trị thực tế và source | true / environment variable |
| User bean condition | Kiểu/tên, bean nào đang tồn tại | ReportGateway / customReportGateway |
| Context condition | Servlet/reactive/non-web hoặc context parent | Servlet |
| Resource condition | Resource và kết quả | classpath:report.yml / Có |
| Order | before/after và condition phụ thuộc | after = TransportAutoConfiguration |
| Expected result | Có/không, bean name/type | Không tạo default |
| Actual result | Kết quả thực tế từ report/context | Default back off |
| Evidence | Report, test, stack trace, command | ConditionEvaluationReport + test |
| Diagnosis | Nguyên nhân và hành động tiếp theo | User bean tồn tại; đây là hành vi đúng |

Để bảng hữu ích, tránh ghi “dependency có” mà không nêu class nào; “property đúng” mà không ghi key/value/source; hoặc “bean user có” mà không nêu type/name. Một người khác phải có thể tái tạo kết luận chỉ từ các cột này.

### 9.1. Phân biệt dữ kiện và giả thuyết

Trong quá trình điều tra, dùng trạng thái rõ ràng:

- **Observed:** đã xác minh từ runtime classpath, Environment, BeanFactory hoặc condition report.
- **Expected:** kết quả theo code/annotation.
- **Unknown:** chưa thu thập được bằng chứng.
- **Mismatch:** actual khác expected và cần điều tra.

Ví dụ không ghi reporting.enabled=true nếu mới chỉ nhìn thấy giá trị trong file YAML. Hãy ghi YAML=false, Environment effective=true (source=REPORTING_ENABLED) nếu đã xác minh. Nếu chưa biết giá trị hiệu lực, ghi Unknown, không suy diễn.

## 10. Cách lấy bằng chứng runtime

### 10.1. Condition Evaluation Report

Chạy ứng dụng với --debug:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Hoặc khi đã build executable JAR:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot ghi condition evaluation report, thường có các nhóm:

- **Positive matches:** các condition khớp.
- **Negative matches:** các condition không khớp và lý do.
- **Exclusions:** auto-configuration bị loại trừ.
- **Unconditional classes:** cấu hình không cần condition.

Đọc report theo tên class và bean method. Ví dụ ReportAutoConfiguration#reportGateway không match vì @ConditionalOnMissingBean tìm thấy ReportGateway là bằng chứng user bean đã khiến default back off. Điều này khác với ReportAutoConfiguration bị bỏ qua vì classpath condition.

### 10.2. Actuator conditions

Nếu project có spring-boot-starter-actuator, endpoint conditions có thể cung cấp condition outcomes qua HTTP khi được expose. Với Spring Boot 3.3, endpoint này không mặc nhiên được expose qua HTTP; cấu hình exposure và security phải được rà soát. Không mở endpoint chẩn đoán ra public chỉ để debug.

Ví dụ cấu hình nội bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,conditions"
~~~

Bảo vệ endpoint bằng Spring Security hoặc network policy phù hợp. Report có thể tiết lộ classpath, cấu hình và cấu trúc nội bộ, vì vậy chỉ cấp cho người cần chẩn đoán.

### 10.3. Kiểm tra Environment

Trong test, ApplicationContextRunner.withPropertyValues(...) tạo các biến thể property rõ ràng. Ở runtime, có thể dùng Environment#getProperty("reporting.enabled") trong mã chẩn đoán hoặc debugger. Nếu dùng Actuator env, giữ sanitization và không chia sẻ response có secret.

### 10.4. Kiểm tra bean definitions

Phân biệt definition và instance:

- containsBeanDefinition("reportGateway"): kiểm tra definition theo tên.
- containsBean("reportGateway"): kiểm tra bean có thể được truy cập theo tên, có thể kích hoạt tạo bean tùy loại/scope.
- getBeanNamesForType(ReportGateway.class): tìm tên bean phù hợp kiểu.
- getBean(ReportGateway.class): lấy instance, có thể kích hoạt khởi tạo và có thể lỗi nếu nhiều ứng viên.

Khi chỉ cần chứng minh điều kiện đăng ký, ưu tiên xem definition/condition report trước khi gọi getBean(), vì lấy instance có thể làm thay đổi trạng thái đang quan sát.

## 11. Kiểm thử ma trận bằng ApplicationContextRunner

ApplicationContextRunner là công cụ Spring Boot Test để dựng context nhỏ, độc lập cho từng combination của property, user configuration và classloader. Nó phù hợp để xác nhận bảng dự kiến thay vì khởi động toàn bộ ứng dụng cho từng trường hợp.

### 11.1. Mã test hoàn chỉnh

Tạo file src/test/java/example/matrix/AutoConfigurationMatrixTests.java trong project Spring Boot 3.3.x, Java 17+, có spring-boot-starter-test.

~~~java
package example.matrix;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationMatrixTests {

    interface ReportGateway {
        String source();
    }

    static final class DefaultReportGateway implements ReportGateway {
        @Override
        public String source() {
            return "default";
        }
    }

    static final class CustomReportGateway implements ReportGateway {
        @Override
        public String source() {
            return "user";
        }
    }

    // Marker đại diện cho một dependency tùy chọn.
    static final class OptionalTransport {}

    @AutoConfiguration
    @ConditionalOnClass(
        name = "example.matrix.AutoConfigurationMatrixTests$OptionalTransport"
    )
    @ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportGateway.class)
        DefaultReportGateway reportGateway() {
            return new DefaultReportGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        CustomReportGateway customReportGateway() {
            return new CustomReportGateway();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ReportAutoConfiguration.class));

    @Test
    void allConditionsMatchCreatesDefaultBean() {
        runner.withPropertyValues("reporting.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(DefaultReportGateway.class);
                    assertThat(context).hasSingleBean(ReportGateway.class);
                    assertThat(context.getBean(ReportGateway.class).source())
                            .isEqualTo("default");
                });
    }

    @Test
    void missingPropertyDoesNotCreateDefaultBean() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(ReportGateway.class);
            assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
        });
    }

    @Test
    void falsePropertyDoesNotCreateDefaultBean() {
        runner.withPropertyValues("reporting.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportGateway.class);
                    assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
                });
    }

    @Test
    void missingOptionalClassPreventsAutoConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(OptionalTransport.class))
                .withPropertyValues("reporting.enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportGateway.class);
                    assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
                });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        runner.withUserConfiguration(UserGatewayConfiguration.class)
                .withPropertyValues("reporting.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportGateway.class);
                    assertThat(context).hasSingleBean(CustomReportGateway.class);
                    assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
                    assertThat(context.getBean(ReportGateway.class).source())
                            .isEqualTo("user");
                });
    }
}
~~~

**Lưu ý về tên class trong @ConditionalOnClass:** test dùng nested marker nên tên đầy đủ có dấu $. Trong dự án thực tế, marker thường là class của dependency ngoài, ví dụ com.vendor.sdk.ReportClient; khi dùng FilteredClassLoader, filter đúng class đó. Ví dụ test không dùng OptionalTransport trong chữ ký method của auto-configuration, nên có thể cô lập classpath condition bằng name mà không buộc method return type nạp class tùy chọn.

### 11.2. Lệnh chạy và kết quả mong đợi

Gradle:

~~~bash
./gradlew test --tests example.matrix.AutoConfigurationMatrixTests
~~~

Maven:

~~~bash
./mvnw -Dtest=AutoConfigurationMatrixTests test
~~~

Kết quả mong đợi: **5 test PASS**.

| Test | Classpath | Property | User bean | Kết quả |
|---|---|---|---|---|
| allConditionsMatchCreatesDefaultBean | Có | true | Không | Default xuất hiện |
| missingPropertyDoesNotCreateDefaultBean | Có | Thiếu | Không | Không có gateway |
| falsePropertyDoesNotCreateDefaultBean | Có | false | Không | Không có gateway |
| missingOptionalClassPreventsAutoConfiguration | Thiếu | true | Không | Không có gateway |
| userBeanMakesDefaultBackOff | Có | true | Có | Chỉ custom bean |

Các test xác nhận những trục chính của ma trận. Chúng không kiểm tra mọi combination có thể có, cũng không kiểm tra profile, exclude, context parent, web application type hoặc lỗi khởi tạo gateway. Hãy thêm test riêng khi auto-configuration thực tế có các điều kiện đó.

### 11.3. Mở rộng test theo ma trận thực tế

Khi có nhiều property, đừng viết một test khổng lồ với rất nhiều nhánh if. Tạo các test tên theo scenario hoặc dùng parameterized tests để mỗi hàng của ma trận là một case có đầu vào và kết quả mong đợi. Ví dụ:

- classpathPresent_propertyEnabled_noUserBean_createsDefault
- classpathMissing_propertyEnabled_noUserBean_skipsConfiguration
- classpathPresent_propertyMissing_noUserBean_skipsConfiguration
- classpathPresent_propertyEnabled_userBeanPresent_backsOff
- configurationExcluded_neverCreatesDefault

Tên test nên thể hiện đầu vào hoặc nguyên nhân chính và bean kết quả, giúp CI failure đọc được ngay.

## 12. Quy trình điều tra một bean không xuất hiện

1. **Xác định bean cần điều tra:** tên, kiểu, @Bean method hoặc component class. Đừng chỉ tìm tên interface vì có thể có nhiều implementation.
2. **Tìm auto-configuration candidate:** JAR imports, @Import, component scan và các exclude. Nếu class chưa được nạp, không cần phân tích sâu condition method của nó.
3. **Lập bảng điều kiện:** ghi từng annotation class-level và method-level; tách classpath, property, bean, resource, application type.
4. **Thu thập giá trị runtime:** runtime dependency tree, effective property/source, active profiles, user bean definitions và context type.
5. **Dự đoán kết quả trước khi xem report:** đánh dấu từng condition match/no-match và tính kết quả AND. Việc này giúp phân biệt hiểu sai logic với sự kiện runtime.
6. **Đối chiếu Condition Evaluation Report:** xem positive/negative matches và message. Xác định condition đầu tiên không khớp hoặc bean condition back-off.
7. **Kiểm tra thứ tự:** nếu @ConditionalOnBean/@ConditionalOnMissingBean phụ thuộc bean từ auto-configuration khác, kiểm tra after/before và return type bean method.
8. **Phân biệt definition với instance:** nếu report cho thấy bean definition được đăng ký nhưng lấy bean thất bại, kiểm tra dependency, constructor, factory method, binding và lifecycle.
9. **Viết test nhỏ tái hiện:** dùng ApplicationContextRunner với đúng classpath/property/user bean combination, sau đó sửa đúng một trục để xác nhận giả thuyết.
10. **Ghi actual và evidence:** cập nhật bảng bằng kết quả quan sát, không chỉ ghi dự đoán. Lưu lại lệnh, profile và version dependency để người khác tái hiện.

## 13. Lỗi thường gặp khi lập bảng

- **Chỉ ghi dependency trong build file:** cần kiểm tra runtime classpath và dependency đã resolve.
- **Chỉ đọc application.yml:** giá trị hiệu lực có thể bị environment variable, command line, profile hoặc config import ghi đè.
- **Không tách condition class-level và method-level:** cấu hình có thể được nạp nhưng một bean cụ thể không được đăng ký.
- **Hiểu @ConditionalOnMissingBean là lỗi khi user bean tồn tại:** đó thường là back-off đúng thiết kế.
- **Hiểu @ConditionalOnBean cần instance đã khởi tạo:** condition dựa trên bean metadata/definitions đã được xử lý.
- **Bỏ qua thứ tự auto-configuration:** điều kiện bean nhìn những definitions có trước thời điểm đánh giá.
- **Dùng @ConditionalOnProperty cho collection:** annotation không phù hợp để xác định collection có phần tử.
- **Đặt @ConditionalOnClass trên method có signature phụ thuộc class tùy chọn:** JVM có thể nạp type trước khi method condition được xét; tách cấu hình được bảo vệ.
- **Đọc condition report như kết quả khởi tạo:** report giải thích condition, không chứng minh bean instance đã được tạo và chạy thành công.
- **Gọi getBean() trước khi kiểm tra definition:** có thể kích hoạt khởi tạo và làm thay đổi trạng thái quan sát.
- **Không ghi rõ matchIfMissing:** property thiếu có thể khiến kết quả khác dự đoán.
- **Nhầm @Primary với @ConditionalOnMissingBean:** một cái chọn ứng viên injection, một cái quyết định default bean có được đăng ký.
- **Không phân biệt exclude với condition mismatch:** auto-configuration bị exclude sẽ không đi qua logic bean như dự kiến.
- **Không ghi version:** condition, auto-configuration và dependency graph có thể thay đổi giữa các phiên bản Boot/starter.

## 14. Câu hỏi tự kiểm tra

1. Dependency có trong pom.xml, nhưng @ConditionalOnClass không khớp. Cần kiểm tra gì trước? **Runtime classpath**, scope, dependency exclusion, version được resolve và classloader thực tế.
2. reporting.enabled=true trong YAML nhưng condition không khớp. Vì sao? **Có thể property source ưu tiên cao hơn đã ghi đè**, profile khác đang active, key sai hoặc giá trị hiệu lực không đúng havingValue.
3. User khai báo bean ReportGateway, auto-config có @ConditionalOnMissingBean(ReportGateway.class). Default có xuất hiện không? **Không**, nếu user definition đã được xử lý trước condition.
4. @ConditionalOnBean({A.class, B.class}) cần bao nhiêu kiểu được tìm thấy? **Cả A và B**.
5. Có hai bean ReportGateway và một bean được đánh dấu @Primary. @ConditionalOnSingleCandidate có thể khớp không? **Có**, nếu Spring xác định được một primary candidate.
6. Auto-configuration không xuất hiện trong Condition Evaluation Report. Cần xem gì? **Imports file, exclude và đường nạp configuration** trước khi phân tích property.
7. Condition report cho thấy bean method match, nhưng ứng dụng vẫn không khởi động. Cần kiểm tra gì? **Lỗi khởi tạo bean và dependency graph**; condition match chỉ xác nhận điều kiện đăng ký.
8. Vì sao cần ghi actual property source trong bảng? **Để chứng minh giá trị runtime thực tế và truy ra nguồn ghi đè**, không dựa vào file cấu hình tĩnh.
9. Muốn test classpath condition mà không build hai artifact. Dùng gì? **FilteredClassLoader trong ApplicationContextRunner**.
10. @AutoConfiguration(after = X.class) đảm bảo bean của X đã được khởi tạo chưa? **Không**; nó sắp thứ tự xử lý bean definitions, còn khởi tạo phụ thuộc dependency và @DependsOn.

## 15. Tài liệu tham khảo chính thức (Spring Boot 3.3)

- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): imports, ordering, class/bean/property conditions, back-off và ApplicationContextRunner.
- [Condition Annotations API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/package-summary.html): danh sách annotation điều kiện và các kiểu condition.
- [ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): mô hình báo cáo condition match/no-match.
- [Spring Boot Actuator — Conditions endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): endpoint chẩn đoán condition và yêu cầu exposure/security.
- [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): property sources, profiles và thứ tự ưu tiên cấu hình.
- [ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): dựng context nhỏ để kiểm thử auto-configuration.
- [FilteredClassLoader API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html): mô phỏng class không có trên classpath trong test.
