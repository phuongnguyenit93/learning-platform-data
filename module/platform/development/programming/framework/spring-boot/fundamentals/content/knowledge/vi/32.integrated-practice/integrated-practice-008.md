# Dùng conditions report giải thích vì sao một bean xuất hiện hoặc vắng mặt

Khi một Spring Boot application khởi động, Spring không tạo tất cả bean một cách vô điều kiện. Nhiều bean được đăng ký dựa trên classpath, property, profile, loại ứng dụng, bean khác đã tồn tại hoặc những điều kiện do dự án định nghĩa. Cơ chế này đặc biệt quan trọng với **auto-configuration**: starter có thể mang theo nhiều cấu hình, nhưng chỉ những cấu hình phù hợp với ứng dụng hiện tại mới được áp dụng.

Khi một bean xuất hiện ngoài dự kiến hoặc không được tạo, chỉ nhìn vào class Java thường chưa đủ. Cần biết Spring đã đánh giá điều kiện nào, điều kiện đó match hay không, và thông điệp nào giải thích kết quả. Spring Boot cung cấp **Condition Evaluation Report** (conditions report) để quan sát quá trình này.

Bài học hướng dẫn cách bật report, đọc positive/negative matches, exclusions và unconditional classes, truy vết điều kiện của một bean, phân biệt điều kiện match với bean thực sự được khởi tạo, và dùng báo cáo để xử lý những lỗi cấu hình phổ biến.

## 1. Vì sao một bean có thể xuất hiện hoặc vắng mặt?

Một bean Spring có thể được đăng ký theo nhiều cách:

- Component scanning phát hiện class có `@Component`, `@Service`, `@Repository`, `@Controller` hoặc stereotype tương ứng.
- Một configuration class được import và khai báo bean bằng `@Bean`.
- Auto-configuration của Spring Boot đăng ký bean khi các điều kiện phù hợp.
- Một profile hoặc property bật/tắt configuration.
- Một thư viện/starter đăng ký bean theo classpath hoặc loại application.
- Một cấu hình khác cung cấp bean thay thế khiến auto-configuration mặc định lùi lại.

Ví dụ một auto-configuration tạo client nếu ứng dụng bật tính năng:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.catalog",
        name = "enabled",
        havingValue = "true"
)
public class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

Bean `catalogClient` có thể xuất hiện khi:

1. Auto-configuration được import/discover.
2. Property `app.catalog.enabled` có giá trị `true`.
3. Không có bean `CatalogClient` phù hợp khiến điều kiện `@ConditionalOnMissingBean` không đạt.

Nếu một trong các điều kiện không thỏa, bean có thể không được đăng ký. Conditions report giúp xác định **điều kiện nào đã được đánh giá và kết quả ra sao**.

### 1.1. Hai câu hỏi cần tách biệt

Khi điều tra bean:

- **Bean definition có được đăng ký không?** Đây là câu hỏi về configuration và điều kiện.
- **Bean instance có được tạo thành công không?** Đây là câu hỏi về lifecycle, dependency injection, constructor, proxy và khởi tạo bean.

Một điều kiện match không đảm bảo object cuối cùng được tạo thành công. Ngược lại, một bean không xuất hiện trong report không nhất thiết chứng minh có lỗi: bean đó có thể được đăng ký bằng component scan hoặc configuration không có conditional annotation.

## 2. Conditions report là gì?

Spring Framework có abstraction `Condition` và annotation `@Conditional`. Spring Boot mở rộng cơ chế đó bằng nhiều điều kiện chuyên biệt như:

- `@ConditionalOnClass` / `@ConditionalOnMissingClass`
- `@ConditionalOnBean` / `@ConditionalOnMissingBean`
- `@ConditionalOnProperty`
- `@ConditionalOnResource`
- `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication`
- `@ConditionalOnSingleCandidate`
- `@ConditionalOnExpression`

Khi Spring đánh giá các condition trong quá trình xử lý configuration, Spring Boot có thể ghi lại kết quả trong `ConditionEvaluationReport`.

Report tổng hợp những thông tin như:

- Configuration source nào được đánh giá.
- Những condition nào match.
- Những condition nào không match và lý do.
- Auto-configuration nào bị loại trừ.
- Một số configuration không có condition được ghi nhận như unconditional classes.

Báo cáo thường được dùng để giải thích auto-configuration. Nó đặc biệt hữu ích khi một starter không tạo bean như mong đợi hoặc một cấu hình mặc định xuất hiện ngoài dự kiến.

### 2.1. Report không phải danh sách toàn bộ bean

Đừng hiểu conditions report là bản dump của `ApplicationContext.getBeanDefinitionNames()`.

Report phản ánh **các condition đã được đánh giá và được ghi nhận**. Nó không phải inventory hoàn chỉnh của mọi bean đang tồn tại. Bean được tạo qua component scan thông thường, bean không có conditional annotation hoặc bean được đăng ký theo cơ chế khác có thể không xuất hiện dưới dạng một mục condition riêng.

Muốn biết bean nào thực sự tồn tại, hãy dùng bean inspection phù hợp; muốn biết vì sao auto-configuration được chọn hoặc bị bỏ qua, hãy đọc conditions report. Hai công cụ trả lời hai câu hỏi bổ sung cho nhau.

## 3. Bật conditions report bằng --debug

Cách nhanh nhất khi chạy ứng dụng là truyền cờ `--debug`:

~~~bash
java -jar catalog-service.jar --debug
~~~

Với Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Với Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Cú pháp truyền arguments của build tool có thể khác theo plugin và shell; điểm quan trọng là ứng dụng nhận được Spring Boot command-line argument `--debug`.

Có thể bật bằng property:

~~~properties
debug=true
~~~

Hoặc YAML:

~~~yaml
debug: true
~~~

`--debug` / `debug=true` yêu cầu Spring Boot bật debug logging cho **một nhóm logger lõi được chọn** và in conditions evaluation report. Nó không có nghĩa là bật `DEBUG` cho mọi logger trong ứng dụng.

### 3.1. Debug mode không giống logging.level.root=DEBUG

Hai cấu hình có phạm vi khác nhau:

| Cấu hình | Tác dụng |
|---|---|
| `--debug` hoặc `debug=true` | Bật một số debug log của Spring Boot và conditions report |
| `logging.level.root=DEBUG` | Đặt root logger ở DEBUG, có thể làm lượng log toàn ứng dụng tăng mạnh |
| `logging.level.org.springframework=DEBUG` | Bật DEBUG cho package Spring tương ứng |
| `logging.level.com.example=TRACE` | Bật TRACE cho package ứng dụng được chỉ định |

Khi chỉ cần hiểu auto-configuration, bắt đầu bằng `--debug` thường đủ. Không nên bật DEBUG/TRACE toàn bộ ứng dụng production chỉ để xem condition report.

### 3.2. Report xuất hiện ở đâu?

Report thường được ghi vào console/log output trong quá trình startup. Khi ứng dụng thất bại lúc khởi động, điều kiện đã đánh giá có thể được in kèm phần thông tin lỗi tùy giai đoạn và phiên bản.

Hãy lưu toàn bộ startup log, không chỉ dòng cuối cùng. Phần report thường nằm sau các log khởi tạo và có các tiêu đề như:

~~~text
CONDITIONS EVALUATION REPORT
============================
~~~

Tên logger, mức log và cách trình bày có thể thay đổi theo phiên bản Spring Boot.

## 4. Bật report bằng Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator, có thể sử dụng endpoint `conditions` để xem kết quả condition evaluation qua HTTP.

Thêm dependency nếu chưa có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Mặc định, các Actuator web endpoints được expose rất hạn chế. Để expose endpoint conditions trong môi trường development được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Sau đó gọi:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

Đường dẫn giả định management base path mặc định là `/actuator` và endpoint chạy trên cùng cổng ứng dụng. Nếu ứng dụng đổi base path, management port hoặc security rules, URL và quyền truy cập sẽ khác.

Endpoint có thể trả các nhóm thông tin như:

~~~json
{
  "positiveMatches": {
    "SomeAutoConfiguration": [
      {
        "condition": "OnClassCondition",
        "message": "..."
      }
    ]
  },
  "negativeMatches": {
    "OtherAutoConfiguration": [
      {
        "condition": "OnPropertyCondition",
        "message": "..."
      }
    ]
  },
  "exclusions": [],
  "unconditionalClasses": []
}
~~~

Đây là cấu trúc minh họa rút gọn. Response thực tế có thể dài và chứa nhiều class/condition hơn.

### 4.1. Bảo vệ endpoint conditions

Conditions report có thể tiết lộ:

- Tên class và package trong ứng dụng.
- Những thư viện có mặt trên classpath.
- Tên property và một số thông tin điều kiện cấu hình.
- Những thành phần hạ tầng đã được kích hoạt.

Không expose `/actuator/conditions` công khai chỉ để thuận tiện debug. Chỉ bật trong môi trường phù hợp, giới hạn network access, authentication và authorization; tắt exposure khi không còn cần thiết.

## 5. Đọc cấu trúc report

Một conditions report thường được trình bày theo các nhóm lớn:

~~~text
CONDITIONS EVALUATION REPORT

Positive matches:
-----------------
...

Negative matches:
-----------------
...

Exclusions:
-----------
...

Unconditional classes:
----------------------
...
~~~

### 5.1. Positive matches

Đây là những configuration source mà các điều kiện liên quan đều match.

Ví dụ minh họa:

~~~text
Positive matches:
-----------------

   DataSourceAutoConfiguration matched:
      - @ConditionalOnClass found required classes
        'javax.sql.DataSource', 'org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType'
      - @ConditionalOnMissingBean did not find any beans
        of type 'javax.sql.DataSource'
~~~

Cách đọc:

- `DataSourceAutoConfiguration` được đánh giá.
- Những class cần thiết có mặt.
- Không có bean `DataSource` phù hợp ở thời điểm điều kiện được kiểm tra.
- Auto-configuration có thể cung cấp cấu hình DataSource mặc định.

Thông điệp chính xác phụ thuộc classpath, version, bean definitions và cấu hình đang chạy. Ví dụ trên chỉ minh họa cách diễn giải.

### 5.2. Negative matches

Đây là nơi quan trọng khi bean/configuration **không xuất hiện**.

Ví dụ:

~~~text
Negative matches:
-----------------

   DataSourceAutoConfiguration:
      Did not match:
         - @ConditionalOnClass did not find required class
           'javax.sql.DataSource'
~~~

Điều này gợi ý dependency hoặc class cần thiết không có trên runtime classpath.

Ví dụ khác:

~~~text
   SomeFeatureAutoConfiguration:
      Did not match:
         - @ConditionalOnProperty (app.feature.enabled=true)
           found different value in property 'enabled'
~~~

Điều kiện property không đạt. Hãy kiểm tra giá trị thực tế và nguồn cấu hình được sử dụng.

Một configuration có nhiều condition; chỉ cần một condition bắt buộc không match là configuration có thể bị bỏ qua. Report cho biết condition nào là lý do thất bại.

### 5.3. Exclusions

Nhóm này liệt kê những auto-configuration bị loại trừ một cách tường minh, ví dụ qua:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class CatalogApplication {
}
~~~

Hoặc property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Nếu một auto-configuration không xuất hiện dù classpath/property có vẻ phù hợp, kiểm tra `exclude` và `spring.autoconfigure.exclude`.

### 5.4. Unconditional classes

Nhóm này hiển thị các auto-configuration được import mà không cần điều kiện match thông thường. Tùy phiên bản và cách cấu hình, nhóm có thể chứa các class infrastructure không được biểu diễn như một chuỗi điều kiện thông thường.

Đừng suy luận rằng mọi class trong mục này chắc chắn đã tạo thành công tất cả bean của nó. Đây vẫn là thông tin về quá trình configuration/condition, không phải xác nhận toàn bộ bean lifecycle đã hoàn tất.

## 6. Đọc từng condition message

Report thường ghi cả tên condition và thông điệp giải thích. Hãy đọc message trước khi sửa code.

### 6.1. @ConditionalOnClass

Điều kiện này match khi class được yêu cầu có mặt trên classpath.

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.search.SearchClient")
public class SearchAutoConfiguration {

    @Bean
    SearchService searchService() {
        return new SearchService();
    }
}
~~~

Nếu dependency chứa `com.vendor.search.SearchClient` không nằm trên runtime classpath, auto-configuration có thể không match.

Trong report, tìm `OnClassCondition` và thông báo class nào không tìm thấy.

Cần phân biệt dependency có mặt lúc compile với dependency có mặt khi chạy. Một thư viện khai báo `compileOnly` hoặc Maven scope không phù hợp có thể khiến IDE biên dịch được nhưng executable runtime không có class cần thiết.

### 6.2. @ConditionalOnMissingClass

Điều kiện này match khi một class không tồn tại:

~~~java
@ConditionalOnMissingClass("com.vendor.native.Driver")
class FallbackDriverConfiguration {
}
~~~

Nếu class xuất hiện trên classpath, fallback configuration không được áp dụng. Đây thường là cách chọn implementation thay thế khi một thư viện tùy chọn không có mặt.

### 6.3. @ConditionalOnProperty

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchConfiguration {
}
~~~

Điều kiện match khi `app.search.enabled` có giá trị `true` theo quy tắc property comparison.

Các thuộc tính quan trọng:

- `prefix`: tiền tố nhóm property.
- `name` hoặc `value`: tên property cần kiểm tra.
- `havingValue`: giá trị mong đợi.
- `matchIfMissing`: có match khi property không tồn tại hay không.

Nếu không đặt `havingValue`, hành vi mặc định của `@ConditionalOnProperty` thường match khi property có mặt và không bằng chuỗi `false` (không phân biệt hoa thường theo semantics của annotation). Nếu cần kiểm tra boolean cụ thể, nên khai báo `havingValue` tường minh.

Report có thể giải thích property không tồn tại, có giá trị khác mong đợi hoặc condition không được thỏa.

### 6.4. @ConditionalOnBean

~~~java
@AutoConfiguration
@ConditionalOnBean(SearchClient.class)
public class SearchMetricsAutoConfiguration {
}
~~~

Điều kiện match khi bean type phù hợp đã được đăng ký và có thể được tìm thấy theo search strategy.

Nếu bean chưa được đăng ký ở thời điểm condition được đánh giá, configuration có thể không match dù một configuration khác dự định tạo bean đó sau này.

Đây là lý do ordering giữa các auto-configuration có thể quan trọng.

### 6.5. @ConditionalOnMissingBean

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Điều kiện match khi chưa có bean type `PaymentGateway` phù hợp trong phạm vi tìm kiếm.

Nếu ứng dụng cung cấp implementation riêng, auto-configuration có thể back off và không tạo bean mặc định. Đây thường là hành vi mong muốn để người dùng override default.

Report giúp giải thích hai tình huống:

- Không có bean nào: default bean được đăng ký.
- Đã có bean người dùng: default bean bị bỏ qua vì missing-bean condition không còn đúng.

**Quan trọng:** `@ConditionalOnMissingBean` thường được khuyến nghị cho auto-configuration vì nó được xử lý trong một quy trình đăng ký bean có thứ tự. Không nên dùng tùy tiện trên các component configuration rời rạc nếu thứ tự xử lý bean definitions không rõ.

### 6.6. @ConditionalOnSingleCandidate

Điều kiện này phù hợp khi một configuration cần một bean có thể được chọn duy nhất theo quy tắc resolution, ví dụ có một primary candidate giữa nhiều bean cùng type.

Nếu có hai bean cùng type nhưng không có primary phù hợp, điều kiện có thể không match. Đọc message để biết Spring có tìm được single candidate hay không.

### 6.7. @ConditionalOnWebApplication

Điều kiện này phân biệt loại application context/web application theo môi trường runtime. Một auto-configuration dành cho servlet web application có thể không được bật trong ứng dụng non-web hoặc reactive tùy điều kiện cụ thể.

Nếu chạy test với `WebApplicationType.NONE`, một số web auto-configurations không match là điều bình thường.

### 6.8. @Profile

`@Profile` cũng là một conditional mechanism trong Spring:

~~~java
@Configuration
@Profile("dev")
class DevelopmentConfiguration {
}
~~~

Nếu profile `dev` không active, cấu hình không được đăng ký. Khi điều tra, kiểm tra:

~~~properties
spring.profiles.active=dev
~~~

hoặc biến môi trường/command-line tương ứng.

Report có thể thể hiện condition profile được đánh giá, nhưng cần kiểm tra cả nguồn profile thực tế và cấu hình Config Data.

## 7. Tìm bean theo tên trong report

Khi biết bean mong muốn, hãy tìm **tên configuration class hoặc factory method** liên quan.

Ví dụ:

~~~java
@AutoConfiguration
public class SearchClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.search",
            name = "enabled",
            havingValue = "true"
    )
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
~~~

Bean name mặc định thường là `searchClient`. Trong report, nguồn condition có thể được hiển thị theo dạng:

~~~text
SearchClientAutoConfiguration#searchClient
~~~

Đây là dấu hiệu condition gắn trên bean factory method đang được đánh giá.

Nếu report cho thấy method condition không match, hãy đọc thông điệp tương ứng. Nếu class-level condition không match, toàn bộ bean methods bên trong configuration có thể không được xử lý như mong muốn.

### 7.1. Bean name có thể không giống tên class

Một `@Bean` method có thể đổi tên bean bằng:

~~~java
@Bean("primarySearchClient")
SearchClient searchClient() {
    return new DefaultSearchClient();
}
~~~

Tên nguồn trong report có thể dùng tên class/method, trong khi bean registry sử dụng bean name tùy chỉnh. Khi đối chiếu, cần phân biệt **configuration source** với **bean name cuối cùng**.

## 8. Vì sao condition match nhưng bean vẫn không có?

Đây là một trong những nhầm lẫn phổ biến nhất.

Conditions report có thể cho biết configuration/bean method đã qua điều kiện. Nhưng sau đó bean vẫn có thể không được khởi tạo thành công hoặc không truy cập được theo cách mong muốn.

Các nguyên nhân:

1. Constructor của bean ném exception.
2. Một dependency bắt buộc không tồn tại.
3. Có nhiều candidate gây `NoUniqueBeanDefinitionException`.
4. Bean initialization hoặc `@PostConstruct` thất bại.
5. Bean bị proxy hóa nhưng caller inject sai kiểu.
6. Scope/lazy initialization khiến instance chưa được tạo ở thời điểm kiểm tra.
7. Bean definition có tên khác với tên bạn đang tìm.
8. Một configuration khác thay đổi registration/override theo cách được hỗ trợ.

Ví dụ:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.search",
        name = "enabled",
        havingValue = "true"
)
SearchClient searchClient(RequiredCredential credential) {
    return new DefaultSearchClient(credential);
}
~~~

Condition property có thể match, nhưng nếu `RequiredCredential` không tồn tại, việc tạo bean thất bại. Report không biến lỗi dependency injection thành một condition mismatch.

**Phân biệt:** report giải thích *vì sao một cấu hình được chọn hoặc bỏ qua*. Startup exception giải thích *vì sao quá trình tạo object sau đó thất bại*.

## 9. Vì sao bean tồn tại nhưng không thấy trong conditions report?

Không phải bean nào cũng được tạo bởi auto-configuration có điều kiện.

Ví dụ:

~~~java
@Service
public class OrderService {
}
~~~

Bean này có thể được component scanning đăng ký mà không có một conditional configuration riêng được ghi trong report.

Tương tự:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean
    OrderPolicy orderPolicy() {
        return new DefaultOrderPolicy();
    }
}
~~~

Nếu configuration không dùng condition, không nên mong conditions report có một positive-match entry giải thích bean này.

Nếu muốn biết bean thực sự có mặt:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(OrderPolicy.class);
~~~

Hoặc:

~~~java
Map<String, OrderPolicy> candidates =
        applicationContext.getBeansOfType(OrderPolicy.class);
~~~

Các API này trả lời câu hỏi bean registry có những candidate nào. Dùng kết hợp với conditions report để hiểu vì sao auto-configuration đã back off hoặc bean được đăng ký từ đâu.

## 10. Phân biệt report với bean inventory và dependency graph

Ba công cụ này có vai trò khác nhau:

| Công cụ | Trả lời câu hỏi |
|---|---|
| Conditions report | Condition/configuration nào match hoặc không match, và vì sao? |
| Bean inventory | Bean name/type nào đang được đăng ký trong context? |
| Dependency graph/exception chain | Bean nào cần bean nào, và dependency resolution thất bại ở đâu? |

Ví dụ:

- Report nói `PaymentAutoConfiguration` không match vì đã có `PaymentGateway`.
- Bean inventory cho thấy hai bean `stripeGateway` và `bankGateway`.
- Startup exception cho biết `CheckoutService` cần một `PaymentGateway` nhưng có hai candidate.

Không công cụ nào thay thế hoàn toàn công cụ còn lại.

### 10.1. Actuator beans endpoint

Nếu Actuator được bật và endpoint `beans` được expose có kiểm soát:

~~~text
GET /actuator/beans
~~~

Endpoint này có thể giúp quan sát bean names, types và context. Nó phù hợp để xác nhận bean đã được đăng ký, còn `/actuator/conditions` giải thích điều kiện auto-configuration.

Giữ các endpoint diagnostics trong network được bảo vệ. Chúng có thể tiết lộ nội bộ ứng dụng.

## 11. Đọc exclusions để tìm auto-configuration bị loại bỏ

Một ứng dụng có thể loại trừ auto-configuration qua annotation:

~~~java
@SpringBootApplication(
        exclude = {
                DataSourceAutoConfiguration.class,
                SecurityAutoConfiguration.class
        }
)
public class CatalogApplication {
}
~~~

Hoặc cấu hình property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Khi bean mặc định của một starter không xuất hiện, hãy kiểm tra nhóm `Exclusions`.

Đừng nhầm exclusion với negative match:

- **Exclusion:** auto-configuration được yêu cầu loại bỏ một cách tường minh.
- **Negative match:** configuration được xét nhưng một hoặc nhiều điều kiện không đạt.
- **Positive match:** các điều kiện liên quan đều đạt.

Nếu auto-configuration bị exclude, thay đổi property để thỏa một condition bên trong thường không giúp nó xuất hiện trở lại; cần bỏ exclusion trước.

## 12. Điều tra property sai hoặc không được nạp

Giả sử report nói:

~~~text
@ConditionalOnProperty (app.search.enabled=true) did not find property 'enabled'
~~~

Hãy kiểm tra:

1. Tên property có đúng prefix không?
2. Có typo giữa `app.search.enabled` và `app.search.enable` không?
3. Profile mong muốn có active không?
4. File cấu hình có nằm trong Config Data locations được nạp không?
5. Biến môi trường có mapping đúng tên property không?
6. Command-line argument có truyền đến process Spring Boot không?
7. Có property source khác override giá trị không?
8. Dùng `havingValue` và `matchIfMissing` đúng ý định không?

Ví dụ cấu hình:

~~~yaml
app:
  search:
    enabled: true
~~~

Tên environment variable tương ứng theo relaxed binding:

~~~text
APP_SEARCH_ENABLED=true
~~~

Chạy bằng command line:

~~~bash
java -jar catalog.jar --app.search.enabled=true
~~~

Nếu ứng dụng vẫn báo property không tồn tại, xác nhận process thực sự nhận argument và profile/config location đang dùng. Đừng chỉ nhìn file YAML trong repository rồi kết luận runtime đã nạp nó.

### 12.1. Actuator env endpoint

Endpoint `/actuator/env` có thể hỗ trợ xem property sources và giá trị hiệu lực khi được expose và bảo vệ phù hợp. Nhưng endpoint này có thể tiết lộ thông tin cấu hình nhạy cảm, nên không mở công khai.

Khi chỉ cần điều tra local, có thể in tên property và nguồn liên quan một cách chọn lọc; tránh dump toàn bộ Environment hoặc log credentials.

## 13. Điều tra classpath và dependency scope

Nếu report cho thấy `@ConditionalOnClass` không match, kiểm tra runtime dependency graph.

Ví dụ Gradle:

~~~groovy
dependencies {
    compileOnly 'com.vendor:search-client'
}
~~~

Code có thể compile nếu API được nhìn thấy trong compile classpath, nhưng `compileOnly` không tự đưa thư viện vào runtime classpath. Khi chạy executable JAR, class có thể vắng mặt.

Nếu ứng dụng cần thư viện khi chạy:

~~~groovy
dependencies {
    implementation 'com.vendor:search-client'
}
~~~

Hoặc `runtimeOnly` nếu code không cần dùng API đó lúc compile nhưng thư viện cần có khi runtime.

Kiểm tra Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Và xem dependency cụ thể:

~~~bash
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency search-client
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

Sau đó kiểm tra artifact phát hành, ví dụ các dependency trong `BOOT-INF/lib` của executable JAR. IDE classpath và runtime artifact không phải lúc nào cũng giống nhau.

## 14. Điều tra @ConditionalOnBean và thứ tự auto-configuration

Một cấu hình có thể phụ thuộc bean do cấu hình khác đăng ký:

~~~java
@AutoConfiguration
@ConditionalOnBean(SearchClient.class)
public class SearchIndexAutoConfiguration {

    @Bean
    SearchIndex searchIndex(SearchClient client) {
        return new SearchIndex(client);
    }
}
~~~

Nếu `SearchClient` chưa được đăng ký khi condition này được đánh giá, `SearchIndexAutoConfiguration` có thể không match.

Trong auto-configuration, thứ tự có ý nghĩa vì conditions như `@ConditionalOnBean` và `@ConditionalOnMissingBean` thường nhìn thấy bean definitions đã được xử lý ở thời điểm đánh giá.

Spring Boot cung cấp các cơ chế ordering như:

~~~java
@AutoConfiguration(after = SearchClientAutoConfiguration.class)
public class SearchIndexAutoConfiguration {
}
~~~

Với các style/phiên bản cũ hơn có thể gặp `@AutoConfigureAfter`, `@AutoConfigureBefore` hoặc `@AutoConfigureOrder`.

### 14.1. Vì sao @ConditionalOnMissingBean thường phù hợp với auto-configuration?

Một starter muốn cung cấp default bean nhưng cho phép ứng dụng override:

~~~java
@AutoConfiguration
public class SearchClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
~~~

Nếu user configuration đã đăng ký một `SearchClient` trước thời điểm auto-configuration đánh giá condition, default bean sẽ back off.

Nếu auto-configuration tự phụ thuộc vào một bean được tạo sau đó mà ordering không phù hợp, condition có thể không nhìn thấy bean dự kiến. Hãy thiết kế ordering và điều kiện theo quy tắc auto-configuration, không dùng một thứ tự may rủi của component scan.

### 14.2. Không dùng @ConditionalOnMissingBean như cơ chế chọn giữa hai user beans

Nếu ứng dụng tự đăng ký hai implementation cùng type, `@ConditionalOnMissingBean` trong starter chỉ quyết định có thêm default bean hay không. Nó không tự chọn giữa hai implementation do ứng dụng cung cấp.

Nếu một service cần một bean đơn, vẫn phải dùng `@Primary`, `@Qualifier` hoặc một chiến lược registry.

## 15. Điều tra component scan và import

Nếu bean không xuất hiện nhưng conditions report không có negative match liên quan, có thể configuration chưa từng được đưa vào context.

Kiểm tra:

- Package của class có nằm trong phạm vi `@ComponentScan` không?
- Configuration có được `@Import` không?
- Starter đã đăng ký auto-configuration theo metadata đúng phiên bản chưa?
- Với Spring Boot hiện đại, auto-configuration candidates có được khai báo trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` không?
- Với các starter cũ, metadata có thể dùng `META-INF/spring.factories` theo cơ chế của phiên bản tương ứng.
- Dependency chứa configuration class có nằm trong runtime classpath không?

Ví dụ cấu trúc auto-configuration hiện đại:

~~~text
my-starter.jar
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.example.search.autoconfigure.SearchClientAutoConfiguration
~~~

Nếu file metadata thiếu hoặc sai tên class, auto-configuration có thể không được discover. Khi class chưa được import/đánh giá, conditions report không thể cho một negative condition cụ thể của class đó.

## 16. Conditions report và @ConditionalOnMissingBean: vì sao default bean biến mất?

Một trường hợp phổ biến:

~~~java
@AutoConfiguration
public class CacheClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheClient.class)
    CacheClient cacheClient() {
        return new DefaultCacheClient();
    }
}
~~~

Ứng dụng lại khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
class ApplicationCacheConfiguration {

    @Bean
    CacheClient customCacheClient() {
        return new RedisCacheClient();
    }
}
~~~

Kết quả mong đợi:

- `customCacheClient` tồn tại.
- `cacheClient` mặc định không được tạo.
- Conditions report ghi nhận missing-bean condition không match vì đã tìm thấy bean `CacheClient`.

Đây là **back-off behavior** của auto-configuration, không phải lỗi.

Nếu ứng dụng vẫn mong có cả hai bean, phải xem lại type/qualifier và ý định thiết kế. `@ConditionalOnMissingBean` được tạo ra để tránh tạo default khi người dùng đã cung cấp implementation.

### 16.1. Tại sao report không cho biết custom bean đến từ đâu?

Report cho biết condition của auto-configuration đã tìm thấy một bean phù hợp, nhưng không phải lúc nào cũng cung cấp toàn bộ câu chuyện đăng ký bean đó trong cùng một mục.

Dùng bean inventory hoặc tìm kiếm bean definition để xác định custom bean được khai báo bởi component/configuration nào.

## 17. Tạo custom condition và đọc report

Ứng dụng có thể tạo condition riêng khi điều kiện không thể diễn đạt bằng annotation có sẵn.

Ví dụ condition kiểm tra một system property:

~~~java
public class ExternalModeCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        return "external".equals(
                context.getEnvironment()
                        .getProperty("app.mode")
        );
    }
}
~~~

Dùng:

~~~java
@Configuration
@Conditional(ExternalModeCondition.class)
class ExternalModeConfiguration {
}
~~~

Khi condition không match, configuration bị bỏ qua. Conditions report có thể ghi nhận condition outcome, nhưng message tùy chỉnh sẽ hữu ích hơn nếu condition cung cấp lý do rõ.

### 17.1. Dùng SpringBootCondition để có message rõ hơn

Spring Boot có abstraction `SpringBootCondition` cho các condition tích hợp với condition evaluation reporting.

Ví dụ minh họa:

~~~java
public class ExternalModeCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String mode = context.getEnvironment()
                .getProperty("app.mode");

        if ("external".equals(mode)) {
            return ConditionOutcome.match(
                    "app.mode is external"
            );
        }

        return ConditionOutcome.noMatch(
                "app.mode must be external; current value is " + mode
        );
    }
}
~~~

Để biên dịch, cần các import Boot condition APIs phù hợp:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
~~~

Message nên:

- Nói rõ điều kiện đang kiểm tra.
- Nêu lý do match/no-match.
- Không tiết lộ secret hoặc toàn bộ giá trị cấu hình nhạy cảm.
- Ngắn đủ để người vận hành hiểu.
- Không thực hiện I/O tốn kém trong lúc đánh giá condition.

### 17.2. Condition phải deterministic và nhẹ

Conditions được đánh giá trong quá trình đăng ký configuration. Tránh:

- Gọi HTTP tới dịch vụ ngoài.
- Query database để quyết định có tạo bean không.
- Thay đổi state hệ thống.
- Dựa vào thời điểm ngẫu nhiên hoặc side effect.
- Log token/password trong message.

Condition phù hợp để kiểm tra classpath, environment property, bean definitions và metadata có sẵn. Kiểm tra khả năng kết nối runtime nên được thực hiện bởi health/initialization/service logic phù hợp, không nhồi vào condition.

## 18. Truy cập ConditionEvaluationReport bằng code

Trong một số tình huống chẩn đoán nâng cao, có thể đọc report từ bean factory:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);
~~~

API này thuộc package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
~~~

Report cung cấp thông tin như condition outcomes theo source, exclusions và unconditional classes. Tên method/kiểu dữ liệu chi tiết nên được kiểm tra theo Spring Boot version mà dự án đang compile.

Ví dụ ý tưởng đọc các source:

~~~java
report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            System.out.println(source);
            System.out.println("Matched: " + outcomes.isFullMatch());
        });
~~~

Đây là ví dụ chẩn đoán, không phải code nên đưa vào business service. `ConditionEvaluationReport` là API phục vụ auto-configuration diagnostics; tránh xây logic nghiệp vụ phụ thuộc vào cấu trúc report hoặc implementation details thay đổi theo phiên bản.

### 18.1. Đọc report ở đúng thời điểm

Report chỉ có nội dung condition đã được đánh giá đến thời điểm đọc. Nếu truy cập quá sớm, một số configuration/condition chưa được xử lý.

Với chẩn đoán, ưu tiên đọc sau khi context đã được chuẩn bị hoặc từ Actuator conditions endpoint. Nếu context fail trước khi refresh hoàn tất, dùng startup report và exception log do Boot phát ra.

## 19. Kiểm thử auto-configuration bằng ApplicationContextRunner

Conditions report hữu ích khi debug thủ công, nhưng auto-configuration nên được kiểm thử với các điều kiện quan trọng.

`ApplicationContextRunner` giúp dựng một context nhỏ, áp dụng một tập configuration, property và user beans rồi kiểm tra kết quả.

Ví dụ auto-configuration:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "app.catalog",
        name = "enabled",
        havingValue = "true"
)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class
                            )
                    );

    @Test
    void createsClientWhenFeatureIsEnabled() {
        contextRunner
                .withPropertyValues("app.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context.getBean(CatalogClient.class))
                            .isInstanceOf(DefaultCatalogClient.class);
                });
    }

    @Test
    void doesNotCreateClientWhenFeatureIsDisabled() {
        contextRunner
                .withPropertyValues("app.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                });
    }
}
~~~

Ví dụ giả định project có dependency test phù hợp và `CatalogAutoConfiguration` được biên dịch trong test source/runtime.

### 19.1. Kiểm thử user override

~~~java
@Test
void backsOffWhenUserProvidesClient() {
    contextRunner
            .withPropertyValues("app.catalog.enabled=true")
            .withBean(
                    CatalogClient.class,
                    () -> new CustomCatalogClient()
            )
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context.getBean(CatalogClient.class))
                        .isInstanceOf(CustomCatalogClient.class);
            });
}
~~~

Test này xác nhận `@ConditionalOnMissingBean` back off khi user cung cấp implementation.

### 19.2. Kiểm thử classpath condition

Với condition phụ thuộc classpath, `ApplicationContextRunner` có các phương thức hỗ trợ class loader/filtering theo nhu cầu test. Mục tiêu là kiểm tra cả hai nhánh:

- Dependency có mặt: auto-configuration được áp dụng.
- Dependency không có: auto-configuration lùi lại mà context vẫn có thể khởi động.

Đừng chỉ test trường hợp “mọi dependency đều có” vì starter thường phải hoạt động đúng cả khi thư viện tùy chọn vắng mặt.

### 19.3. Vì sao test runner tốt hơn test toàn bộ ứng dụng?

Auto-configuration test nhỏ giúp kiểm soát chính xác:

- Property values.
- User-provided beans.
- Classpath.
- Web application type.
- Import order.
- Kết quả đăng ký bean.

Nó làm rõ nguyên nhân match/no-match mà không cần khởi động database, web server hoặc toàn bộ hệ thống production.

## 20. Một quy trình thực tế khi bean không xuất hiện

Giả sử ứng dụng cần `SearchClient` nhưng:

~~~java
@Autowired
SearchClient searchClient;
~~~

không được resolve hoặc context báo không có bean.

Thực hiện theo thứ tự:

**Bước 1 — Bật report**

~~~bash
java -jar catalog.jar --debug
~~~

Hoặc bật `debug=true` trong cấu hình local.

**Bước 2 — Tìm auto-configuration liên quan**

Tìm tên class như `SearchAutoConfiguration`, `SearchClientAutoConfiguration` hoặc bean factory method tương ứng.

**Bước 3 — Đọc negative match**

Tìm condition message cụ thể:

- Thiếu class?
- Property chưa tồn tại?
- Property có giá trị sai?
- Bean phụ thuộc chưa được đăng ký?
- Không tìm thấy single candidate?
- Profile không active?

**Bước 4 — Kiểm tra exclusion**

Tìm auto-configuration trong nhóm `Exclusions`, đồng thời kiểm tra `spring.autoconfigure.exclude` và annotation trên application class.

**Bước 5 — Kiểm tra runtime classpath**

Xem dependency tree và artifact thực tế. Đặc biệt chú ý `compileOnly`, `provided`, `optional` và exclusions.

**Bước 6 — Kiểm tra config data**

Xác nhận profile, config location, environment variables, command-line properties và giá trị override.

**Bước 7 — Kiểm tra bean inventory**

Nếu report cho thấy configuration match, kiểm tra bean definition có tồn tại không. Nếu bean có mặt nhưng injection thất bại, xem qualifier, primary và dependency graph.

**Bước 8 — Đọc root cause của bean creation**

Nếu điều kiện match nhưng bean không tạo được, tìm `BeanCreationException`, `UnsatisfiedDependencyException` hoặc lỗi khởi tạo sâu hơn.

**Bước 9 — Tạo test tái hiện**

Dùng `ApplicationContextRunner` với property/bean/classpath giống trường hợp lỗi để khóa hành vi mong đợi.

## 21. Một quy trình khi bean xuất hiện ngoài dự kiến

Giả sử ứng dụng không muốn auto-configuration tạo `DataSource` mặc định nhưng nó vẫn xuất hiện.

Hãy kiểm tra:

1. Positive matches có `DataSourceAutoConfiguration` không?
2. `@ConditionalOnClass` đã match do JDBC classes có mặt?
3. `@ConditionalOnMissingBean` có match vì chưa có bean DataSource nào khác?
4. Property có bật embedded database hoặc cấu hình datasource không?
5. Có starter transitively kéo JDBC/embedded database vào classpath không?
6. Có profile hoặc config import làm bật datasource không?
7. Có thể loại trừ auto-configuration nếu ứng dụng thật sự không dùng nó không?

Nếu một user bean `DataSource` đã được đăng ký, auto-configuration mặc định thường back off theo missing-bean condition. Nếu report nói không tìm thấy bean, kiểm tra vì sao user configuration chưa được xử lý trước condition hoặc bean type không tương ứng.

Đừng loại trừ toàn bộ `DataSourceAutoConfiguration` chỉ để che lỗi một bean duplicate nếu ứng dụng vẫn cần datasource. Hãy xác định default bean nào không mong muốn và chọn giải pháp phù hợp.

## 22. Những trường hợp report không cho câu trả lời trực tiếp

Conditions report rất hữu ích nhưng có giới hạn.

### 22.1. Configuration chưa được discover

Nếu class không được component scan/import/auto-configuration discovery, condition có thể chưa từng chạy. Không có negative match để đọc.

### 22.2. Bean được tạo bằng component scanning

Một `@Service` bình thường có thể không có condition report entry riêng. Dùng bean inventory và kiểm tra scan base package.

### 22.3. Bean creation thất bại sau khi condition match

Report không thay thế stack trace. Xem exception về constructor, dependency, initialization, proxy hoặc resource.

### 22.4. Bean bị thay thế hoặc nhiều candidate

Conditions report có thể nói default auto-configuration đã back off. Nhưng lỗi `NoUniqueBeanDefinitionException` cần kiểm tra candidate list và qualifier/primary.

### 22.5. Property được thay đổi sau startup

Condition evaluation diễn ra trong quá trình cấu hình context. Thay đổi Environment sau đó không tự động chạy lại toàn bộ auto-configuration để thêm/bớt bean. Nhiều bean definitions không phải cơ chế feature toggle runtime.

### 22.6. Condition custom không cung cấp message hữu ích

Nếu custom condition trả outcome chung chung, report cũng chỉ giải thích chung chung. Hãy trả message rõ trong `SpringBootCondition` hoặc sử dụng điều kiện có sẵn nếu phù hợp.

## 23. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không thấy conditions report | Chưa bật debug hoặc log output bị cấu hình khác che | Chạy với `--debug` hoặc `debug=true` |
| Auto-configuration không xuất hiện trong report | Class chưa được discover/import hoặc chưa nằm trên runtime classpath | Kiểm tra starter metadata, component/import và dependency |
| Negative match do thiếu class | Dependency không có trong runtime classpath | Sửa dependency scope/version và kiểm tra executable artifact |
| Negative match do property | Sai tên, giá trị, profile hoặc config location | Kiểm tra property source và `havingValue`/`matchIfMissing` |
| Default bean không được tạo | `@ConditionalOnMissingBean` thấy user bean tương ứng | Đây có thể là back-off đúng; kiểm tra bean inventory |
| Condition match nhưng bean không khởi tạo | Constructor/dependency/initialization thất bại | Đọc root cause của `BeanCreationException` |
| Bean tồn tại nhưng không có trong report | Bean được đăng ký qua component scan hoặc cấu hình không conditional | Kiểm tra bean inventory |
| Auto-configuration bị bỏ dù condition có vẻ đúng | Có exclusion hoặc ordering/bean condition khác | Kiểm tra exclusions và toàn bộ condition outcomes |
| Test có bean nhưng production không có | Profile, classpath, property hoặc runtime config khác | Tái hiện cấu hình production trong context test |
| Bean xuất hiện hai lần | Hai nguồn đăng ký hoặc hai implementation cùng type | Kiểm tra component scan, `@Bean`, import và qualifier |
| Actuator conditions trả 404 | Endpoint chưa expose hoặc management path/port khác | Cấu hình exposure và kiểm tra URL |
| Actuator conditions trả 401/403 | Security rule hạn chế endpoint | Cấp quyền nội bộ tối thiểu, không mở public |
| Report có quá nhiều thông tin | Debug bật rộng hoặc endpoint diagnostics được expose | Tắt debug sau điều tra, giới hạn truy cập |
| Condition custom báo lý do khó hiểu | Message outcome chung chung | Cung cấp message match/no-match cụ thể, không chứa secret |

## 24. Checklist đọc report nhanh

Khi mở conditions report, đi theo thứ tự:

1. **Tìm tên auto-configuration hoặc bean method** liên quan đến dependency đang điều tra.
2. Xác định nó nằm trong **Positive matches**, **Negative matches** hay **Exclusions**.
3. Đọc tất cả condition messages trong mục đó, không chỉ dòng đầu.
4. Nếu có `@ConditionalOnProperty`, xác nhận property name/value/profile.
5. Nếu có `@ConditionalOnClass`, xác nhận runtime dependency.
6. Nếu có `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`, kiểm tra bean definitions và ordering.
7. Nếu configuration match, xác minh bean definition/instance bằng bean inventory.
8. Nếu bean không tạo được, đọc exception chain và root cause.
9. Nếu không tìm thấy configuration trong report, kiểm tra discovery/import/component scan.
10. Sau khi xác định nguyên nhân, tạo test tái hiện nhánh match/no-match.

## 25. Những nguyên tắc quan trọng

- **Conditions report giải thích quyết định conditional configuration**, đặc biệt là auto-configuration.
- Dùng `--debug` hoặc `debug=true` để bật report trong quá trình startup.
- `--debug` không đồng nghĩa bật DEBUG cho toàn bộ logger.
- Actuator `/actuator/conditions` cung cấp report qua HTTP khi endpoint được expose.
- **Positive matches** cho biết điều kiện đã match; **negative matches** nêu lý do không match.
- **Exclusions** cho biết auto-configuration bị loại trừ tường minh.
- **Unconditional classes** là thông tin về configuration không có condition theo cách thông thường, không phải bảo đảm mọi bean đã được tạo.
- Report không phải danh sách tất cả bean; dùng bean inventory để xác nhận bean thực sự tồn tại.
- Condition match không bảo đảm bean instance khởi tạo thành công; đọc exception khi gặp lỗi lifecycle/dependency.
- `@ConditionalOnMissingBean` thường cho phép user bean thay thế default auto-configuration.
- Thứ tự auto-configuration có thể ảnh hưởng `@ConditionalOnBean` và `@ConditionalOnMissingBean`.
- Nếu configuration không được discover/import, report có thể không có entry để giải thích.
- Custom condition nên nhẹ, deterministic và trả message cụ thể.
- Không expose Actuator diagnostics công khai hoặc đưa secret vào condition message.
- Dùng `ApplicationContextRunner` để kiểm thử các nhánh property, classpath và user override.

**Kết luận:** Khi một bean xuất hiện hoặc vắng mặt, conditions report cho biết Spring Boot đã đánh giá những điều kiện nào và lý do mỗi điều kiện match hoặc không match. Bắt đầu bằng `--debug`, tìm đúng configuration source, đọc positive/negative matches và exclusions, rồi đối chiếu với bean inventory và exception chain. Cách điều tra theo từng tầng này giúp phân biệt lỗi property, classpath, auto-configuration ordering, component scanning và bean creation, thay vì thay đổi annotation hoặc dependency một cách mò mẫm.
