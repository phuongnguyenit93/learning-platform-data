# Đọc điều kiện tạo bean trước khi thay thế mặc định

Bài học thuộc chương **Tùy biến tự động cấu hình** của module **SPRING_CLOUD_CORE**. Spring Boot và Spring Cloud dùng auto-configuration để tạo các bean mặc định dựa trên classpath, bean hiện có, property và loại ứng dụng. Khi muốn thay một implementation mặc định, bước đầu tiên là đọc điều kiện đã tạo ra bean đó. Điều kiện thường cho biết bean chỉ xuất hiện khi thư viện có mặt, khi một property được bật, khi dependency khác đã tồn tại hoặc khi ứng dụng chưa cung cấp bean thay thế.

Cơ chế mở rộng phổ biến nhất là `@ConditionalOnMissingBean`. Auto-configuration khai báo bean mặc định với điều kiện “chưa có bean phù hợp”; nếu ứng dụng cung cấp bean theo contract mà điều kiện kiểm tra, auto-configuration sẽ lùi lại. Đây là cách thay thế có chủ đích và dễ kiểm soát. Để áp dụng đúng, cần xem báo cáo điều kiện, đọc method tạo bean và xác định chính xác type/name mà condition đang tìm.

Trong hệ sinh thái Spring Cloud, cách làm này xuất hiện ở các module như LoadBalancer, discovery và service registry. Ví dụ, LoadBalancer có thể tạo `ReactorLoadBalancer` hoặc `ServiceInstanceListSupplier` mặc định nếu context của service chưa có bean tùy chỉnh. Bài học sử dụng những ví dụ đó để xây dựng quy trình đọc điều kiện trước khi thay đổi cấu hình.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của Spring Boot auto-configuration trong Spring Cloud.
2. Phân biệt auto-configuration với component scanning và cấu hình do ứng dụng khai báo.
3. Đọc các điều kiện classpath, bean, property, resource và web application.
4. Sử dụng `--debug` hoặc Actuator `/conditions` để xem ConditionEvaluationReport.
5. Tìm auto-configuration và bean method đã tạo một bean mặc định.
6. Xác định `@ConditionalOnMissingBean` đang kiểm tra theo type hay name.
7. Thay thế default bằng custom bean theo đúng contract để auto-configuration back off.
8. Phân biệt back-off theo điều kiện với bean-definition overriding và `@Primary`.
9. Hiểu ảnh hưởng của thứ tự auto-configuration đến việc đánh giá condition.
10. Dùng `ApplicationContextRunner` để kiểm thử cả trường hợp dùng default và trường hợp custom bean thay thế.
11. Tùy biến Spring Cloud LoadBalancer theo service ID mà không vô tình áp dụng cấu hình cho mọi service.
12. Chẩn đoán vì sao bean mặc định không xuất hiện hoặc custom bean không được dùng.

## 2. Auto-configuration tạo bean mặc định như thế nào?

### 2.1. Auto-configuration là cấu hình có điều kiện

Spring Boot auto-configuration là các lớp cấu hình được phát hiện và áp dụng tự động. Từ Spring Boot 2.7 trở đi, các auto-configuration hiện đại thường được liệt kê trong resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng trong file là tên một auto-configuration class. Các class thường dùng `@AutoConfiguration`, vốn là một dạng cấu hình Spring có `proxyBeanMethods=false`, và dùng các condition để quyết định có tạo bean hay không. Trước Spring Boot 2.7, auto-configuration candidates thường được đăng ký qua key `EnableAutoConfiguration` trong `META-INF/spring.factories`; khi đọc dự án cũ, hãy kiểm tra cơ chế discovery tương ứng với version đó.

Ví dụ khái quát:

~~~java
@AutoConfiguration
@ConditionalOnClass(CatalogSdk.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    DefaultCatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

Auto-configuration trên chỉ được áp dụng khi class `CatalogSdk` có trên classpath. Bean mặc định `CatalogClient` chỉ được tạo khi ApplicationContext chưa có bean phù hợp với contract `CatalogClient`.

### 2.2. Tại sao có default?

Thư viện cần cung cấp một cách dùng hợp lý ngay sau khi người dùng thêm starter. Ví dụ:
- Discovery starter tạo implementation DiscoveryClient.
- Spring Cloud LoadBalancer cung cấp thuật toán chọn instance mặc định.
- Spring Cloud Context cung cấp các bean hỗ trợ refresh.
- Actuator auto-configuration đăng ký endpoint khi dependency và điều kiện phù hợp.

Người dùng có thể sử dụng default trước. Khi yêu cầu thay đổi, họ có thể cung cấp implementation riêng hoặc thay đổi property được thư viện hỗ trợ.

### 2.3. Ba lớp cần phân biệt

| Lớp | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| Dependency/classpath | Cung cấp class và module có thể được kích hoạt. | Starter LoadBalancer, Eureka client. |
| Auto-configuration | Đánh giá condition và khai báo bean mặc định. | LoadBalancerClientConfiguration. |
| Application configuration | Cung cấp bean, property hoặc customization của ứng dụng. | Custom ServiceInstanceListSupplier. |

Thêm dependency chỉ làm class có mặt trên classpath. Nó không đảm bảo mọi bean của module được tạo; các condition vẫn phải khớp.

## 3. Đọc condition theo thứ tự

Khi muốn thay một bean mặc định, hãy lần theo luồng sau:

~~~mermaid
flowchart TD
    A["Bean mặc định không đúng nhu cầu"] --> B["Tìm bean type và nơi khai báo"]
    B --> C["Đọc class-level conditions"]
    C --> D["Đọc bean-method conditions"]
    D --> E["Xem ConditionEvaluationReport"]
    E --> F{"Vì sao bean được tạo?"}
    F -->|"Classpath/property/bean condition"| G["Điều chỉnh đúng dependency hoặc property"]
    F -->|"ConditionalOnMissingBean"| H["Cung cấp custom bean theo type/name được kiểm tra"]
    F -->|"Condition không khớp"| I["Sửa điều kiện còn thiếu hoặc dependency"]
    G --> J["Kiểm tra bean thực tế trong context"]
    H --> J
    I --> J
    J --> K["Viết context test cho default và custom"]
~~~

Một quy trình thực tế:

1. Xác định bean đang được inject và hành vi cần thay đổi.
2. Ghi lại bean type, bean name, qualifier và nơi inject.
3. Tìm class `*AutoConfiguration` hoặc cấu hình provider tạo bean đó.
4. Đọc mọi condition ở cấp class và cấp method.
5. Xem ConditionEvaluationReport để biết condition nào match hoặc không match.
6. Chọn điểm mở rộng phù hợp: property, custom bean, customizer, strategy hoặc exclude.
7. Khởi động context và kiểm tra bean thực tế.
8. Viết test chứng minh cả default lẫn custom behavior.

Đừng bắt đầu bằng việc đổi bean name hoặc bật bean-definition overriding. Trước hết phải hiểu cơ chế tạo bean hiện tại.

## 4. Những loại condition thường gặp

Spring Boot cung cấp các annotation condition để áp dụng cho class cấu hình hoặc từng method `@Bean`.

### 4.1. Điều kiện classpath

| Annotation | Ý nghĩa |
| --- | --- |
| `@ConditionalOnClass` | Chỉ áp dụng khi class yêu cầu có trên classpath. |
| `@ConditionalOnMissingClass` | Chỉ áp dụng khi class yêu cầu không có trên classpath. |

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.vendor.CatalogSdk")
class CatalogSdkConfiguration {
    // Cấu hình cần SDK này.
}
~~~

Dùng `name` hữu ích khi class là optional dependency. Nếu class không có, ứng dụng vẫn có thể khởi động mà không phải load kiểu đó.

### 4.2. Điều kiện bean

| Annotation | Ý nghĩa |
| --- | --- |
| `@ConditionalOnBean` | Áp dụng khi đã có bean phù hợp. |
| `@ConditionalOnMissingBean` | Áp dụng khi chưa có bean phù hợp. |
| `@ConditionalOnSingleCandidate` | Áp dụng khi có một candidate duy nhất hoặc một candidate được xác định là primary. |

Ví dụ:

~~~java
@Bean
@ConditionalOnBean(DiscoveryClient.class)
InventoryLocator inventoryLocator(DiscoveryClient discoveryClient) {
    return new DiscoveryInventoryLocator(discoveryClient);
}
~~~

Bean `InventoryLocator` chỉ được tạo khi có `DiscoveryClient`. Nếu discovery provider chưa tạo bean, locator cũng không được tạo.

### 4.3. Điều kiện property

`@ConditionalOnProperty` kiểm tra giá trị trong Environment:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
CatalogClient catalogClient() {
    return new HttpCatalogClient();
}
~~~

Mặc định, condition khớp khi property tồn tại và giá trị không phải chuỗi `false`. Dùng `havingValue` để yêu cầu một giá trị cụ thể. Dùng `matchIfMissing=true` khi muốn bật capability nếu property chưa được khai báo.

Nếu khai báo nhiều property trong `name`, tất cả property phải thỏa điều kiện. Với property boolean, hãy ghi rõ semantics mong muốn để người đọc không phải suy luận từ giá trị mặc định.

### 4.4. Điều kiện resource

`@ConditionalOnResource` kiểm tra một resource có tồn tại hay không:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:catalog/schema.json")
class CatalogSchemaConfiguration {
}
~~~

Nó phù hợp khi cấu hình chỉ có ý nghĩa nếu file, schema hoặc resource cần thiết có mặt.

### 4.5. Điều kiện loại ứng dụng

`@ConditionalOnWebApplication` và `@ConditionalOnNotWebApplication` cho phép giới hạn cấu hình theo loại ứng dụng:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE
)
class ReactiveCatalogConfiguration {
}
~~~

Các điều kiện này hữu ích khi một starter hỗ trợ cả Servlet MVC và Reactive WebFlux nhưng mỗi stack cần bean khác nhau.

### 4.6. Điều kiện biểu thức

`@ConditionalOnExpression` cho phép dùng SpEL:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.catalog.enabled:false}")
class CatalogExpressionConfiguration {
}
~~~

Chỉ dùng khi các condition tiêu chuẩn không diễn đạt được yêu cầu. Tham chiếu bean trong biểu thức có thể khiến bean khởi tạo rất sớm, trước một số post-processing như configuration properties binding; do đó không nên dùng SpEL để truy vấn trạng thái bean tùy tiện.

### 4.7. Các condition được kết hợp

Khi một class hoặc bean method có nhiều condition, tất cả condition được áp dụng phải khớp để cấu hình/bean được đăng ký. Ví dụ class có `@ConditionalOnClass` và method có `@ConditionalOnMissingBean` thì cả hai lớp điều kiện đều tham gia quyết định.

Đọc cả condition trên class bao quanh lẫn condition trên method. Chỉ xem annotation trên method có thể bỏ sót điều kiện cấp class khiến toàn bộ cấu hình không được nạp.

## 5. ConditionEvaluationReport cho biết điều gì?

### 5.1. Bật debug khi khởi động

Spring Boot có thể in ConditionEvaluationReport ra log khi bật debug:

~~~bash
java -jar app.jar --debug
~~~

Hoặc:

~~~bash
java -Ddebug -jar app.jar
~~~

Báo cáo giúp xác định:
- Auto-configuration nào được áp dụng.
- Condition nào match.
- Condition nào không match.
- Lý do condition không khớp, ví dụ thiếu class, thiếu bean hoặc property không đúng.

Hãy tìm tên auto-configuration hoặc bean method liên quan, rồi đọc message của condition thay vì chỉ nhìn kết luận tổng thể.

### 5.2. Dùng Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator, endpoint `conditions` cung cấp báo cáo JSON:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Truy vấn:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

Endpoint có thể chứa các nhóm:
- `contexts`: các ApplicationContext, thường có context chính và có thể có context con.
- `positiveMatches`: class/method có condition khớp.
- `negativeMatches`: class/method không khớp, kèm danh sách điều kiện và thông báo.
- `unconditionalClasses`: các auto-configuration không cần condition.

Ví dụ rút gọn:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "CatalogAutoConfiguration#catalogClient": [
          {
            "condition": "OnBeanCondition",
            "message": "@ConditionalOnMissingBean found no beans of type CatalogClient"
          }
        ]
      },
      "negativeMatches": {
        "ReactiveCatalogConfiguration": {
          "notMatched": [
            {
              "condition": "OnClassCondition",
              "message": "Required class was not found"
            }
          ]
        }
      }
    }
  }
}
~~~

Response thực tế phụ thuộc Spring Boot version. Ví dụ chỉ minh họa cách đọc các phần chính.

### 5.3. Expose conditions có kiểm soát

Endpoint conditions có thể tiết lộ class nội bộ, dependency và lý do một capability được bật/tắt. Chỉ expose trên management interface phù hợp, bảo vệ bằng authentication/authorization và network policy. Không public toàn bộ Actuator endpoint chỉ để xem điều kiện.

### 5.4. Kết hợp với beans endpoint

`/actuator/conditions` giải thích quyết định condition. `/actuator/beans` liệt kê bean definitions thực tế. Hai endpoint trả lời hai câu hỏi khác nhau:

| Endpoint | Câu hỏi |
| --- | --- |
| `/actuator/conditions` | Vì sao auto-configuration hoặc bean method được/không được áp dụng? |
| `/actuator/beans` | Bean nào thực sự có trong ApplicationContext? |
| `/actuator/configprops` | Các bean configuration properties đang nhận cấu hình nào? |

Nếu condition report nói bean mặc định đã back off, hãy kiểm tra beans endpoint để xác nhận custom bean đang có trong context.

## 6. Đọc @ConditionalOnMissingBean trước khi thay thế

### 6.1. Cơ chế back-off

`@ConditionalOnMissingBean` cho phép auto-configuration tạo default khi chưa có bean thỏa điều kiện.

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    DefaultCatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

Khi ứng dụng có một bean triển khai `CatalogClient`, method mặc định không được áp dụng. Auto-configuration back off để dùng bean do ứng dụng cung cấp.

Đây là cơ chế thay thế default được thiết kế sẵn. Không cần đăng ký bean trùng tên với bean mặc định.

### 6.2. Thay thế default bằng custom bean

Giả sử ứng dụng cần thêm header và timeout riêng cho Catalog client:

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new AuthenticatedCatalogClient(
                URI.create("https://catalog.internal"),
                Duration.ofSeconds(2)
        );
    }
}
~~~

Nếu auto-configuration dùng `@ConditionalOnMissingBean(CatalogClient.class)`, bean custom trên làm condition không khớp và default không được tạo.

Để xác minh:
1. Chạy ứng dụng với custom configuration.
2. Kiểm tra report: method default không còn match do tìm thấy bean.
3. Kiểm tra ApplicationContext có đúng một bean theo contract mong đợi.
4. Gọi service client và xác minh hành vi custom.

### 6.3. Kiểm tra theo type hoặc name

Condition có thể kiểm tra theo type:

~~~java
@ConditionalOnMissingBean(CatalogClient.class)
~~~

Hoặc theo bean name:

~~~java
@ConditionalOnMissingBean(name = "catalogClient")
~~~

Theo type thường bền vững hơn khi mục tiêu là thay implementation theo contract. Theo name chỉ phù hợp khi bean name là một phần chủ đích của extension point.

Nếu condition kiểm tra theo name mà custom bean dùng tên khác, default vẫn có thể được tạo. Ngược lại, nếu condition kiểm tra theo type, custom bean phải thực sự assignable với type được kiểm tra.

### 6.4. Nhiều bean cùng contract

Nếu ứng dụng tạo nhiều bean cùng type:
- `@ConditionalOnMissingBean` có thể xem rằng bean phù hợp đã tồn tại và default sẽ back off.
- Injection theo type có thể trở nên ambiguous.
- `@Primary` hoặc `@Qualifier` có thể cần thiết để chọn candidate.

Đừng mặc định rằng “default back off” đồng nghĩa “mọi injection đã rõ ràng”. Kiểm tra cả số lượng bean và cách các consumer inject.

## 7. Kiểu trả về của @Bean ảnh hưởng condition

Khi đặt `@ConditionalOnMissingBean` trên một method `@Bean` và không khai báo rõ type/name, Spring Boot mặc định dùng kiểu trả về của method làm target type.

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean
DefaultCatalogClient catalogClient() {
    return new DefaultCatalogClient();
}
~~~

Method trả về `DefaultCatalogClient`. Bean condition có thể dựa trên type metadata của method.

Nếu condition muốn kiểm tra contract `CatalogClient`, hãy khai báo rõ:

~~~java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
DefaultCatalogClient catalogClient() {
    return new DefaultCatalogClient();
}
~~~

Cách này vừa kiểm tra đúng contract vừa cung cấp return type cụ thể để Spring biết implementation đầy đủ hơn.

Spring Boot khuyến nghị cung cấp càng nhiều type information càng tốt trong return type của `@Bean` method. Điều đó đặc biệt quan trọng khi condition cần đánh giá type từ bean definition mà chưa khởi tạo bean.

## 8. Thời điểm đánh giá condition và thứ tự cấu hình

### 8.1. Condition chỉ nhìn những bean definitions đã được xử lý

`@ConditionalOnBean` và `@ConditionalOnMissingBean` đánh giá những bean definitions đã được xử lý tại thời điểm condition chạy. Nếu custom bean được đăng ký sau khi condition đã được đánh giá, nó không thể làm condition trước đó đổi kết quả hồi tố.

Đây là lý do Spring Boot khuyến nghị dùng hai condition này chủ yếu trên auto-configuration class. Auto-configuration được nạp sau user-defined bean definitions nên có thể nhận biết bean do ứng dụng khai báo.

Tránh đặt `@ConditionalOnMissingBean` trên một cấu hình thông thường được component scan nếu mục tiêu là chờ auto-configuration hoặc cấu hình khác tạo bean trước đó.

### 8.2. Class-level và method-level condition

| Vị trí | Tác động |
| --- | --- |
| Trên class `@Configuration` / `@AutoConfiguration` | Nếu condition không khớp, cấu hình đó không được đăng ký như một bean configuration. |
| Trên method `@Bean` | Chỉ bean do method đó tạo bị bỏ qua; các bean method khác trong class vẫn có thể được xử lý. |

Chọn vị trí theo phạm vi cần điều khiển. Nếu một cấu hình có nhiều bean độc lập, method-level condition thường cho phép tùy biến từng bean chính xác hơn.

### 8.3. Thứ tự auto-configuration

Spring Boot hỗ trợ:
- `@AutoConfigureBefore`
- `@AutoConfigureAfter`
- `@AutoConfigureOrder`
- Các thuộc tính `before`, `after`, `beforeName`, `afterName` của `@AutoConfiguration`.

Ví dụ:

~~~java
@AutoConfiguration(after = WebClientAutoConfiguration.class)
public class CatalogWebClientAutoConfiguration {
}
~~~

Thứ tự auto-configuration ảnh hưởng thứ tự bean definitions được đăng ký và do đó có thể ảnh hưởng điều kiện dựa trên bean đã xử lý. Nó không quyết định trực tiếp thứ tự khởi tạo instance bean; dependencies và `@DependsOn` mới chi phối vòng đời khởi tạo.

Không dùng ordering để sửa một custom bean không đúng type hoặc một condition sai. Trước hết kiểm tra contract và thời điểm đăng ký; chỉ khai báo thứ tự khi hai auto-configuration thực sự cần phối hợp.

## 9. Class condition và optional dependency

### 9.1. Vì sao cần tách nested configuration?

`@ConditionalOnClass` trên class configuration có thể kiểm tra class metadata mà không cần load mọi class optional. Nhưng trên `@Bean` method, JVM có thể cần load return type hoặc các kiểu được method tham chiếu trước khi method condition được đánh giá.

Với dependency tùy chọn, hãy cô lập code phụ thuộc class đó trong nested configuration:

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(CatalogSdk.class)
    static class SdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient() {
            return new SdkCatalogClient();
        }
    }
}
~~~

Khi SDK không có trên classpath, nested configuration không được áp dụng. Ứng dụng vẫn có thể chạy mà không cần load các class của SDK.

### 9.2. Meta-annotation và thuộc tính name

Nếu tạo composed annotation chứa `@ConditionalOnClass` hoặc `@ConditionalOnMissingClass`, dùng thuộc tính `name` để tham chiếu class bằng tên. Việc dùng thuộc tính `value` kiểu Class không được xử lý theo cùng cách trong meta-annotation.

## 10. Các cách tùy biến trước khi exclude auto-configuration

Khi đã hiểu điều kiện, chọn điểm mở rộng ít tác động nhất phù hợp yêu cầu.

| Cách | Dùng khi | Tác động |
| --- | --- | --- |
| External property | Thư viện đã cung cấp property cho hành vi cần đổi. | Giữ nguyên bean graph, thay giá trị cấu hình. |
| Custom bean | Auto-configuration có `@ConditionalOnMissingBean` cho contract đó. | Custom bean được dùng, default back off. |
| Customizer/strategy | Module có extension point chuyên biệt. | Thay một phần hành vi, giữ phần còn lại của default. |
| `@Primary` / `@Qualifier` | Cần chọn một trong nhiều bean cùng type. | Chọn candidate cho injection; không xóa default. |
| Exclude auto-configuration | Toàn bộ cấu hình tự động của module không phù hợp. | Loại cả nhóm bean do auto-configuration đó cung cấp; cần tự cung cấp các phần cần thiết. |

### 10.1. Ưu tiên property có sẵn

Ví dụ, LoadBalancer có các property để chọn retry, cache, health-check supplier hoặc cấu hình theo service. Nếu property đáp ứng yêu cầu, hãy dùng property thay vì tự tạo lại toàn bộ supplier hoặc load balancer.

Kiểm tra metadata property và tài liệu đúng release train. Một property có thể được đổi tên, đổi default hoặc không có trong version đang dùng.

### 10.2. Dùng custom bean ở extension point

Nếu module có default bean được guard bằng `@ConditionalOnMissingBean`, tạo bean custom theo contract được kiểm tra. Đừng tạo một class không implement đúng interface rồi mong auto-configuration nhận diện.

### 10.3. Dùng customizer hoặc strategy

Nhiều module cung cấp customizer để thay đổi một phần cấu hình:
- WebClientCustomizer.
- RestClientCustomizer.
- LoadBalancer request transformer.
- ServiceInstanceListSupplier.
- ReactorLoadBalancer.
- Các strategy/provider interface của Spring Cloud.

Đây thường là cách thay đổi hẹp, ít ảnh hưởng tới những cấu hình mặc định khác.

### 10.4. @Primary không thay thế bean

`@Primary` chỉ ưu tiên một bean khi có nhiều candidate cho injection theo type. Bean mặc định vẫn tồn tại trong ApplicationContext. Nếu mục tiêu là auto-configuration back off, hãy kiểm tra `@ConditionalOnMissingBean` và cung cấp bean đúng contract.

## 11. Bean overriding không phải cơ chế back-off

Bean overriding xảy ra khi một bean definition mới dùng identifier đã được đăng ký. Nó khác với việc auto-configuration không tạo default do `@ConditionalOnMissingBean`.

Ví dụ, hai cấu hình cùng khai báo bean name `catalogClient` có thể tạo xung đột. Spring Boot thường không bật bean-definition overriding theo mặc định; property `spring.main.allow-bean-definition-overriding` có thể thay đổi hành vi này tùy phiên bản/cấu hình.

Không nên bật overriding chỉ để thay default. Việc override cùng tên làm phụ thuộc vào tên bean và thứ tự đăng ký, khó đọc và khó kiểm thử hơn. Spring Framework cũng cảnh báo bean overriding làm cấu hình khó hiểu và đang định hướng loại bỏ dần trong tương lai.

| Cơ chế | Kết quả |
| --- | --- |
| `@ConditionalOnMissingBean` | Auto-configuration không đăng ký default nếu đã có bean phù hợp. |
| `@Primary` | Chọn một bean ưu tiên khi inject nhiều candidate. |
| `@Qualifier` | Chỉ định rõ bean cần inject. |
| Bean-definition overriding | Definition cùng identifier thay thế definition trước đó nếu container cho phép. |

## 12. Ví dụ thực tế: tùy biến Spring Cloud LoadBalancer

Spring Cloud LoadBalancer là ví dụ rõ ràng về auto-configuration có điều kiện.

### 12.1. Default ReactorLoadBalancer

Trong cấu hình LoadBalancer, Spring Cloud có thể tạo `ReactorLoadBalancer<ServiceInstance>` mặc định khi chưa có bean cùng contract. Implementation mặc định phổ biến là `RoundRobinLoadBalancer`.

Ví dụ cấu trúc trong auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean
public ReactorLoadBalancer<ServiceInstance> reactorServiceInstanceLoadBalancer(
        Environment environment,
        LoadBalancerClientFactory clientFactory) {

    String serviceId = environment.getProperty(
            LoadBalancerClientFactory.PROPERTY_NAME);

    return new RoundRobinLoadBalancer(
            clientFactory.getLazyProvider(
                    serviceId,
                    ServiceInstanceListSupplier.class),
            serviceId);
}
~~~

Cách đọc:
1. Bean có type contract là `ReactorLoadBalancer<ServiceInstance>`.
2. Condition `@ConditionalOnMissingBean` kiểm tra context con của LoadBalancer đã có implementation phù hợp hay chưa.
3. Nếu chưa có, factory tạo Round Robin default.
4. Nếu service-specific configuration cung cấp bean phù hợp trước đó, default có thể back off.

Chi tiết class, method và điều kiện cần được đối chiếu với version Spring Cloud LoadBalancer đang sử dụng.

### 12.2. Default ServiceInstanceListSupplier

LoadBalancer cũng tạo `ServiceInstanceListSupplier` khi có DiscoveryClient phù hợp và chưa có supplier tùy chỉnh. Ví dụ điều kiện có thể bao gồm:

~~~java
@Bean
@ConditionalOnBean(DiscoveryClient.class)
@ConditionalOnMissingBean
ServiceInstanceListSupplier discoveryClientServiceInstanceListSupplier(
        ConfigurableApplicationContext context) {

    return ServiceInstanceListSupplier.builder()
            .withBlockingDiscoveryClient()
            .withCaching()
            .build(context);
}
~~~

Đây là default supplier dùng blocking discovery và cache. Với reactive provider, cấu hình tương ứng có thể dùng ReactiveDiscoveryClient. Điều kiện discovery mode và service-specific configuration cũng ảnh hưởng bean nào được tạo.

### 12.3. Thay supplier cho một service

Nếu chỉ service `inventory-service` cần supplier tùy chỉnh, dùng `@LoadBalancerClient` để khai báo cấu hình theo service ID:

~~~java
@Configuration
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryClientRegistration {
}
~~~

Cấu hình được nạp trong LoadBalancer child context của service tương ứng. Ví dụ cấu hình supplier:

~~~java
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Lưu ý:
- Configuration class dành riêng cho LoadBalancer client không nên bị component scan vào context chính nếu điều đó khiến bean tùy chỉnh áp dụng toàn cục.
- Bean custom cần đúng contract mà default condition đang kiểm tra.
- Cấu hình chỉ tác động service ID đã khai báo.
- Nếu application dùng reactive discovery, chọn supplier reactive phù hợp thay cho blocking supplier.
- Kiểm tra điều kiện thực tế trong source code của release train đang dùng.

### 12.4. Đọc source code trước khi thay

Khi mở source của `LoadBalancerClientConfiguration`, tìm:
- `@ConditionalOnDiscoveryEnabled`.
- `@ConditionalOnBlockingDiscoveryEnabled` hoặc reactive tương ứng.
- `@ConditionalOnBean(DiscoveryClient.class)`.
- `@ConditionalOnMissingBean`.
- Điều kiện property chọn default, zone preference, health check hoặc retry.
- `@AutoConfigureAfter` nếu một cấu hình phụ thuộc bean của cấu hình khác.

Chỉ sau khi hiểu các điều kiện đó mới quyết định thêm supplier, load balancer hoặc property. Nếu custom bean không xuất hiện, condition report và child context sẽ giúp tìm nguyên nhân.

## 13. Exclude auto-configuration khi thật sự cần

Có thể loại một auto-configuration cụ thể bằng annotation:

~~~java
@SpringBootApplication(
        exclude = CatalogAutoConfiguration.class
)
public class OrdersApplication {
}
~~~

Hoặc bằng property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Exclude toàn bộ auto-configuration có thể làm mất nhiều bean liên quan cùng lúc. Trước khi dùng, hãy đọc toàn bộ class và các nested configuration, rồi xác định những bean nào ứng dụng phải tự cung cấp sau khi exclude.

Không exclude chỉ vì một default bean không phù hợp nếu module đã có custom bean hoặc customizer cho đúng phần cần thay.

## 14. Kiểm thử điều kiện bằng ApplicationContextRunner

`ApplicationContextRunner` giúp kiểm tra auto-configuration trong context nhỏ, độc lập với việc khởi chạy toàn bộ ứng dụng.

### 14.1. Cấu hình ví dụ

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    DefaultCatalogClient catalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

### 14.2. Kiểm thử default được tạo

~~~java
class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultWhenNoCustomBeanExists() {
        contextRunner.run(context ->
                assertThat(context)
                        .hasSingleBean(CatalogClient.class)
                        .hasSingleBean(DefaultCatalogClient.class)
        );
    }
}
~~~

Test xác nhận khi không có custom bean, default được tạo.

### 14.3. Kiểm thử custom bean làm default back off

~~~java
@Test
void backsOffWhenCustomBeanExists() {
    contextRunner
            .withBean(
                    CatalogClient.class,
                    CustomCatalogClient::new
            )
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(CatalogClient.class)
                        .hasSingleBean(CustomCatalogClient.class)
                        .doesNotHaveBean(DefaultCatalogClient.class);
            });
}
~~~

Test này xác minh custom bean đúng contract khiến default không được đăng ký.

### 14.4. Kiểm thử property condition

~~~java
@Test
void doesNotCreateCatalogClientWhenDisabled() {
    contextRunner
            .withPropertyValues("app.catalog.enabled=false")
            .run(context ->
                    assertThat(context)
                            .doesNotHaveBean(CatalogClient.class)
            );
}
~~~

Bài test cần cấu hình auto-configuration có `@ConditionalOnProperty` tương ứng. Nó chứng minh property tắt đã ngăn bean được tạo.

### 14.5. Kiểm thử optional class

Có thể dùng `FilteredClassLoader` để mô phỏng optional library không có trên classpath:

~~~java
@Test
void skipsSdkConfigurationWhenSdkIsMissing() {
    contextRunner
            .withClassLoader(
                    new FilteredClassLoader(CatalogSdk.class)
            )
            .run(context ->
                    assertThat(context)
                            .doesNotHaveBean(CatalogClient.class)
            );
}
~~~

Test này hữu ích khi starter hỗ trợ nhiều provider hoặc dependency tùy chọn. Đảm bảo class bị lọc không bị tham chiếu từ một method/class ngoài vùng condition đã cô lập.

### 14.6. Test những gì?

| Test case | Điều cần xác minh |
| --- | --- |
| Không có custom bean | Default được tạo. |
| Có custom bean đúng contract | Default back off. |
| Custom bean sai type | Default vẫn được tạo nếu condition không nhận diện bean đó. |
| Property tắt | Bean method/class bị loại theo condition. |
| Optional class vắng mặt | Cấu hình phụ thuộc class không được load. |
| Có nhiều bean cùng type | Injection rõ ràng bằng qualifier/primary theo thiết kế. |
| Context con của LoadBalancer | Custom bean nằm đúng service-specific context. |

Không chỉ assert rằng context khởi động thành công. Hãy kiểm tra bean type, bean count, qualifier và hành vi thực tế.

## 15. Quy trình điều tra khi custom bean không thay thế được default

| Quan sát | Câu hỏi cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Default vẫn xuất hiện | Condition kiểm tra type hay name? | Cung cấp đúng contract hoặc bean name. |
| Custom bean không được tạo | Condition trên class/method nào không khớp? | Đọc positive/negative match và property. |
| Custom bean tồn tại nhưng inject nhầm | Có nhiều candidate cùng type? | Dùng qualifier hoặc primary đúng chỗ. |
| Optional provider không hoạt động | Class có trên classpath và class condition có khớp? | Kiểm tra dependency tree và nested configuration. |
| Condition không thấy custom bean | Custom bean được đăng ký trước khi auto-config condition chạy chưa? | Đưa điều kiện missing-bean vào auto-configuration đúng thứ tự. |
| Cấu hình custom toàn cục ngoài ý muốn | Child configuration có bị component scan không? | Tách cấu hình per-service khỏi component scan. |
| Exclude làm mất nhiều bean | Auto-configuration class chứa những nested config nào? | Chỉ exclude khi sẵn sàng tự cung cấp các bean liên quan. |
| Bean conflict cùng tên | Có hai definition dùng cùng identifier? | Dùng back-off theo type hoặc đổi bean naming; tránh overriding không cần thiết. |
| Report không thấy auto-configuration | Imports, dependency hoặc exclude có vấn đề? | Kiểm tra AutoConfiguration.imports và condition report. |

## 16. Nguyên tắc triển khai

1. **Đọc source trước khi thay.** Tìm class auto-configuration, bean method và tất cả condition liên quan.
2. **Dùng report để xác minh.** ConditionEvaluationReport cho biết lý do match hoặc không match; đừng suy luận từ dependency list.
3. **Thay theo contract.** Custom bean phải implement đúng type hoặc name mà `@ConditionalOnMissingBean` kiểm tra.
4. **Giữ type metadata rõ ràng.** Khai báo return type cụ thể cho `@Bean` method.
5. **Ưu tiên property/customizer.** Dùng extension point hẹp trước khi thay toàn bộ implementation.
6. **Hiểu thứ tự đăng ký.** Missing-bean conditions chỉ nhìn bean definitions đã được xử lý.
7. **Dùng ordering có mục đích.** Before/after điều khiển thứ tự auto-configuration, không thay thế kiểm tra type và condition.
8. **Phân biệt back-off với overriding.** Tránh dựa vào trùng bean name để thay default.
9. **Kiểm tra context con.** Với LoadBalancer per-service, bean phải được đăng ký trong child context tương ứng.
10. **Test cả hai nhánh.** Có test cho default và custom bean, cùng property/class condition.
11. **Bảo vệ diagnostic endpoint.** Conditions và beans có thể tiết lộ cấu trúc nội bộ của ứng dụng.
12. **Đối chiếu release train.** Condition, class name và property có thể thay đổi theo Spring Boot/Spring Cloud version.

## 17. Checklist hoàn thành

- [ ] Giải thích được auto-configuration tạo bean mặc định theo condition.
- [ ] Biết auto-configuration hiện đại được liệt kê trong AutoConfiguration.imports.
- [ ] Phân biệt classpath, bean, property, resource và web condition.
- [ ] Đọc được condition ở cả class level và bean method level.
- [ ] Bật --debug để xem ConditionEvaluationReport.
- [ ] Truy vấn được /actuator/conditions trong môi trường được bảo vệ.
- [ ] Phân biệt positiveMatches và negativeMatches.
- [ ] Biết @ConditionalOnMissingBean kiểm tra theo type/name.
- [ ] Hiểu default back off khi custom bean phù hợp đã được đăng ký.
- [ ] Biết return type của @Bean method ảnh hưởng type metadata.
- [ ] Hiểu condition chỉ nhìn các bean definitions đã được xử lý.
- [ ] Phân biệt class-level và method-level conditions.
- [ ] Hiểu @AutoConfigureBefore, @AutoConfigureAfter và @AutoConfigureOrder.
- [ ] Phân biệt back-off, @Primary, @Qualifier và bean-definition overriding.
- [ ] Đọc được điều kiện trong Spring Cloud LoadBalancer configuration.
- [ ] Biết cách thay ReactorLoadBalancer hoặc ServiceInstanceListSupplier theo service ID.
- [ ] Có test ApplicationContextRunner cho default, custom bean và property condition.
- [ ] Chỉ exclude auto-configuration khi đã xác định các bean phải tự cung cấp.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): auto-configuration discovery, condition annotations, bean back-off, type metadata và ordering.
- [Spring Boot – Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/4.0/how-to/application.html): ConditionEvaluationReport, --debug và cách đọc source của auto-configuration.
- [Spring Boot Actuator – Conditions Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/conditions.html): response positiveMatches, negativeMatches và thông báo condition.
- [Spring Boot – ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): cách condition xác định bean candidate và giới hạn theo thời điểm xử lý.
- [Spring Framework – Bean Definition and Overriding](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean identity, overriding và các lưu ý khi trùng bean name.
- [Spring Cloud LoadBalancer – LoadBalancerClientConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): ví dụ thực tế về default ReactorLoadBalancer, ServiceInstanceListSupplier và các điều kiện back-off.

API và auto-configuration có thể thay đổi theo release train. Hãy kiểm tra đúng Spring Boot/Spring Cloud BOM, condition report và source code của version đang chạy trước khi thay thế một bean mặc định.
