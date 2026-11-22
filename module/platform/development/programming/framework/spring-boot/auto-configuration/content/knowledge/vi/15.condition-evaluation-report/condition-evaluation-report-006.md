# Kết hợp báo cáo điều kiện với danh sách bean thực tế trong ApplicationContext

## 1. Vì sao cần xem đồng thời hai nguồn thông tin?

Khi một bean của Spring Boot không xuất hiện như mong đợi, chỉ nhìn **Condition Evaluation Report** thường chưa đủ. Báo cáo điều kiện cho biết vì sao một lớp cấu hình hoặc phương thức `@Bean` được đánh giá là match hay không match. Còn danh sách bean trong **ApplicationContext** cho biết những bean nào đã được đăng ký trong context, tên, kiểu, scope và các dependency liên quan.

Hai nguồn trả lời hai câu hỏi khác nhau:

- **Condition report:** Spring Boot đã đánh giá những điều kiện nào? Điều kiện nào match, điều kiện nào không match, và thông báo cụ thể là gì?
- **Bean inventory:** Trong context đang kiểm tra có bean nào? Bean có tên gì, kiểu gì, được định nghĩa ở đâu và phụ thuộc bean nào?

Kết hợp chúng giúp đi từ nguyên nhân cấu hình đến kết quả đăng ký bean. Ví dụ, báo cáo cho thấy `CacheAutoConfiguration#cacheManager` đã match; danh sách bean xác nhận có `cacheManager` kiểu `CacheManager`. Nếu condition match nhưng bean không có trong inventory, ta cần kiểm tra thêm phạm vi condition, tên bean, thứ tự auto-configuration, lỗi tạo bean và context cha–con.

**Không đồng nhất hai khái niệm:** một condition match không tự chứng minh một object đã được khởi tạo thành công. Bean definition có thể đã được đăng ký nhưng instance còn lazy; việc tạo instance có thể xảy ra muộn và thất bại khi được sử dụng. Ngược lại, một bean có thể đến từ cấu hình người dùng hoặc context cha mà không phải kết quả trực tiếp của auto-configuration đang xem.

Bài viết dùng **Spring Boot 3.5.x, Spring Framework 6.2 và Java 17+** để minh họa. API nội bộ và định dạng Actuator cần được đối chiếu với phiên bản dự án khi nâng cấp.

## 2. Condition Evaluation Report chứa gì?

Spring Boot lưu các kết quả đánh giá condition trong lớp:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
~~~

Báo cáo ghi nhận các điều kiện được áp dụng cho nguồn (source) như:
- Tên lớp auto-configuration, ví dụ `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`;
- Phương thức cấu hình bean, ví dụ `SomeAutoConfiguration#someService`;
- Các condition con, ví dụ `OnClassCondition`, `OnBeanCondition`, `OnPropertyCondition` hoặc condition do ứng dụng tự viết.

Các API quan trọng trong Spring Boot 3.5:

| API | Ý nghĩa |
| --- | --- |
| `ConditionEvaluationReport.find(beanFactory)` | Tìm báo cáo đã được gắn với BeanFactory; có thể trả về `null` nếu không có |
| `ConditionEvaluationReport.get(beanFactory)` | Lấy báo cáo hoặc tạo một báo cáo mới cho BeanFactory |
| `getConditionAndOutcomesBySource()` | Map kết quả condition, nhóm theo source class/method |
| `ConditionAndOutcomes.isFullMatch()` | `true` khi tất cả outcomes trong source đều match |
| `ConditionAndOutcome.getOutcome()` | Lấy `ConditionOutcome` của một condition |
| `ConditionOutcome.isMatch()` | Condition cụ thể có match không |
| `ConditionOutcome.getMessage()` | Lý do do condition cung cấp |
| `getExclusions()` | Danh sách lớp đã bị loại trừ khỏi auto-configuration evaluation |
| `getUnconditionalClasses()` | Danh sách lớp được đánh giá nhưng không có condition |

Một source có thể có nhiều condition. Ví dụ, lớp auto-configuration match `@ConditionalOnClass` nhưng phương thức bean không match `@ConditionalOnProperty`. Vì vậy phải đọc **từng outcome**, không chỉ tìm chữ "positive".

### Phân biệt positiveMatches và negativeMatches

Condition report thường có ba nhóm chính:

- **Positive matches:** các source có điều kiện match.
- **Negative matches:** các source có ít nhất một condition không match. Trong mỗi source, phần `notMatched` mô tả điều kiện thất bại, còn `matched` liệt kê những điều kiện đã đạt.
- **Unconditional classes:** lớp không cần condition để được đưa vào quá trình cấu hình.

Một source xuất hiện trong `negativeMatches` không có nghĩa mọi condition của source đều thất bại. Có thể một số condition đã match và chỉ một condition không đạt.

Ví dụ dạng rút gọn:

~~~json
{
  "positiveMatches": {
    "example.CacheAutoConfiguration#cacheManager": [
      {
        "condition": "OnClassCondition",
        "message": "Cache API found"
      },
      {
        "condition": "OnPropertyCondition",
        "message": "Property demo.cache.enabled matched"
      }
    ]
  },
  "negativeMatches": {
    "example.MetricsAutoConfiguration#metricsPublisher": {
      "notMatched": [
        {
          "condition": "OnBeanCondition",
          "message": "did not find any beans of type MeterRegistry"
        }
      ],
      "matched": [
        {
          "condition": "OnClassCondition",
          "message": "required metrics API found"
        }
      ]
    }
  }
}
~~~

Đây là JSON minh họa để giải thích cấu trúc; message thực tế do condition cụ thể tạo ra và có thể khác theo phiên bản, classpath và cấu hình.

## 3. Bean inventory trong ApplicationContext là gì?

Spring quản lý bean trong **BeanFactory**, thường được truy cập qua `ApplicationContext`. Có thể liệt kê bean theo tên, theo kiểu hoặc đọc metadata của bean definition.

Các API cơ bản:

| API | Thông tin | Lưu ý |
| --- | --- | --- |
| `getBeanDefinitionNames()` | Tên các bean definition trong BeanFactory hiện tại | Không tự bao gồm context cha; không bao gồm mọi singleton đăng ký trực tiếp ngoài bean definition |
| `getBeanDefinition(name)` | Metadata của definition: scope, lazy-init, resource, factory method, role | Chỉ dùng được với bean có definition trong factory hiện tại |
| `getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` | Tên bean phù hợp kiểu, kể cả subclass | Có thể điều khiển việc xét prototype và eager initialization của FactoryBean |
| `getType(name)` | Kiểu dự kiến của bean | Có thể không xác định được kiểu và trả về `null`; introspection FactoryBean có thể cần khởi tạo factory |
| `getBeansOfType(type)` | Map tên và instance theo kiểu | Có thể tạo lazy/prototype bean và gây side effect |
| `containsBean(name)` | Có thể tra cứu bean theo tên trong factory/context | Không chứng minh instance đã được khởi tạo trước đó |

### Bean definition khác bean instance

Đây là phân biệt quan trọng khi chẩn đoán:

- **Bean definition đã đăng ký:** Spring biết cách tạo bean, nhưng instance có thể chưa được tạo.
- **Singleton đã khởi tạo:** instance singleton đã được tạo và lưu trong context.
- **Prototype:** mỗi lần yêu cầu có thể tạo instance mới.
- **Lazy singleton:** chỉ tạo instance khi có lần truy cập phù hợp.
- **FactoryBean:** bản thân factory và object mà factory tạo ra là hai khái niệm khác nhau.

`getBeanDefinitionNames()` trả về tên definition, không phải danh sách chứng minh mọi instance đã tồn tại. Nếu cần xác nhận instance theo một kiểu cụ thể, có thể dùng `getBeanNamesForType(...)` để tìm tên rồi gọi `getBean(name)` có chủ đích. Lời gọi `getBean` có thể kích hoạt khởi tạo bean lazy hoặc tạo prototype, vì vậy không nên dùng để quét toàn bộ production context một cách vô tư.

## 4. Hai nguồn được kết hợp như thế nào?

Trong Spring Boot Actuator, hai endpoint có vai trò riêng:

| Endpoint | Nội dung | Dùng để trả lời |
| --- | --- | --- |
| `GET /actuator/conditions` | Báo cáo điều kiện theo application context | Vì sao auto-configuration hoặc bean method match/không match? |
| `GET /actuator/beans` | Bean inventory theo application context | Bean nào được đăng ký, tên/kiểu/scope/dependency ra sao? |

### 4.1. Bật endpoint

Thêm dependency Actuator nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Trong `application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info,conditions,beans
~~~

Mặc định, Actuator không expose mọi endpoint qua HTTP. Cấu hình trên chủ động expose `conditions` và `beans` cùng một số endpoint thông dụng. Nếu dùng Spring Security, cấu hình authorization thích hợp cho các đường dẫn quản trị.

Gửi request trong môi trường local:

~~~bash
curl http://localhost:8080/actuator/conditions
curl http://localhost:8080/actuator/beans
~~~

Nếu ứng dụng đổi `management.endpoints.web.base-path`, port hoặc management server riêng, URL thực tế cũng thay đổi.

### 4.2. Đọc endpoint conditions

Dữ liệu thường có dạng:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "example.CacheAutoConfiguration#cacheManager": [
          {
            "condition": "OnPropertyCondition",
            "message": "Property demo.cache.enabled matched"
          }
        ]
      },
      "negativeMatches": {},
      "unconditionalClasses": [],
      "parentId": null
    }
  }
}
~~~

Các phần cần quan sát:
- `contexts`: map các ApplicationContext theo ID.
- `positiveMatches`: source có condition match.
- `negativeMatches`: source có condition không match, kèm chi tiết matched/notMatched.
- `unconditionalClasses`: lớp unconditional.
- `parentId`: ID context cha nếu có.

### 4.3. Đọc endpoint beans

Ví dụ dạng rút gọn:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "cacheManager": {
          "aliases": [],
          "scope": "singleton",
          "type": "example.CacheManager",
          "resource": "example.CacheAutoConfiguration",
          "dependencies": []
        }
      },
      "parentId": null
    }
  }
}
~~~

Bean inventory cung cấp:
- `beans`: map theo tên bean;
- `aliases`: bí danh;
- `scope`: phạm vi;
- `type`: tên kiểu đầy đủ;
- `resource`: nguồn định nghĩa nếu có;
- `dependencies`: các bean phụ thuộc;
- `parentId`: context cha.

JSON trên chỉ minh họa hình dạng dữ liệu, không phải response thực của một ứng dụng đang chạy.

### 4.4. Ghép hai báo cáo theo source và bean name

Với phương thức:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo.cache",
        name = "enabled",
        havingValue = "true")
CacheService cacheService() {
    return new CacheService();
}
~~~

Nếu tên bean không được tùy chỉnh, tên mặc định thường là `cacheService`, tương ứng với source `example.CacheAutoConfiguration#cacheService` trong condition report.

Cách đối chiếu:
1. Tìm source `CacheAutoConfiguration#cacheService` trong `positiveMatches`.
2. Đọc message của từng condition để biết vì sao phương thức được phép đăng ký.
3. Tìm `cacheService` trong `beans` của **cùng context ID**.
4. Kiểm tra `type`, `scope`, `resource` và `dependencies`.
5. Nếu tên bean được đặt tường minh, ví dụ `@Bean("primaryCache")`, tìm `primaryCache` trong inventory; tên phương thức không còn là tên bean mặc định.
6. Nếu source là tên lớp cấu hình, không có nghĩa lớp đó cũng chính là bean nghiệp vụ cần tìm. Hãy tìm các phương thức `@Bean` bên trong lớp và bean name/return type tương ứng.

**Không có phép nối tự động một-một cho mọi trường hợp.** Một class condition có thể bật nhiều bean; một bean có thể đến từ cấu hình người dùng; tên `@Bean` có thể tùy chỉnh; factory method có thể trả về interface hoặc proxy. Vì vậy phải đối chiếu source, tên bean, kiểu và context, không chỉ so sánh chuỗi một cách máy móc.

## 5. Ví dụ Java: đọc condition report và bean definitions trong cùng context

Spring Boot 3.5 cung cấp API để truy cập report trực tiếp. Ví dụ sau tạo một `ApplicationRunner` ghi condition outcomes và bean definitions ra console sau khi ApplicationContext đã refresh.

Tạo file **`src/main/java/example/AutoConfigurationDiagnostics.java`**:

~~~java
package example;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class AutoConfigurationDiagnostics implements ApplicationRunner {

    private final ConfigurableApplicationContext context;

    public AutoConfigurationDiagnostics(
            ConfigurableApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        ConfigurableListableBeanFactory beanFactory =
                context.getBeanFactory();

        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(beanFactory);

        System.out.println("=== CONDITION REPORT ===");

        if (report == null) {
            System.out.println("No ConditionEvaluationReport found");
        }
        else {
            report.getConditionAndOutcomesBySource()
                    .forEach((source, outcomes) -> {
                        outcomes.forEach(conditionAndOutcome -> {
                            var outcome = conditionAndOutcome.getOutcome();

                            System.out.printf(
                                    "SOURCE=%s | RESULT=%s | MESSAGE=%s%n",
                                    source,
                                    outcome.isMatch() ? "MATCH" : "NO_MATCH",
                                    outcome.getMessage());
                        });
                    });

            System.out.println(
                    "EXCLUDED_AUTO_CONFIGURATIONS="
                            + report.getExclusions());
        }

        System.out.println("=== BEAN DEFINITIONS ===");

        for (String beanName : context.getBeanDefinitionNames()) {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition(beanName);

            Class<?> type = context.getType(beanName);

            String scope = definition.getScope();
            if (scope == null || scope.isBlank()) {
                scope = "singleton";
            }

            System.out.printf(
                    "BEAN=%s | TYPE=%s | SCOPE=%s | RESOURCE=%s | FACTORY_METHOD=%s%n",
                    beanName,
                    type == null ? "<unknown>" : type.getName(),
                    scope,
                    definition.getResourceDescription(),
                    definition.getFactoryMethodName());
        }
    }
}
~~~

**Cách hoạt động:**

- `ConfigurableApplicationContext.getBeanFactory()` lấy BeanFactory của context hiện tại.
- `ConditionEvaluationReport.find(beanFactory)` tìm report đã được Boot ghi nhận; nếu không tìm thấy thì trả về `null`.
- `getConditionAndOutcomesBySource()` trả về kết quả theo class/method.
- `ConditionAndOutcomes` có thể duyệt bằng vòng lặp; `ConditionOutcome.isMatch()` và `getMessage()` cung cấp trạng thái và lý do.
- `getExclusions()` hiển thị lớp auto-configuration bị loại trừ.
- `context.getBeanDefinitionNames()` liệt kê bean definitions thuộc **context hiện tại**.
- `getBeanDefinition(beanName)` cung cấp scope, resource description và factory method.
- `context.getType(beanName)` cố gắng xác định kiểu bean; nếu không suy ra được, ví dụ hiển thị `<unknown>`.

Ví dụ console sẽ chứa các dòng dạng:

~~~text
=== CONDITION REPORT ===
SOURCE=example.CacheAutoConfiguration#cacheService | RESULT=MATCH | MESSAGE=...
EXCLUDED_AUTO_CONFIGURATIONS=[]
=== BEAN DEFINITIONS ===
BEAN=cacheService | TYPE=example.CacheService | SCOPE=singleton | RESOURCE=... | FACTORY_METHOD=cacheService
~~~

Đây là **dạng minh họa**; message, thứ tự và số lượng bean phụ thuộc classpath, profile, condition, phiên bản và cấu hình ứng dụng. Không kỳ vọng toàn bộ output của một ứng dụng thực sẽ giống hệt đoạn trên.

### Giới hạn của đoạn code

1. `getBeanDefinitionNames()` chỉ liệt kê definition ở factory hiện tại; nó không tự liệt kê context cha.
2. Các singleton được đăng ký trực tiếp qua API ngoài bean definitions có thể không xuất hiện trong danh sách definition.
3. `getType(name)` có thể không xác định được kiểu ở một số FactoryBean hoặc factory method.
4. Đoạn code đọc metadata, không gọi `getBean(name)` để cố ý khởi tạo từng bean. Vì vậy nó không chứng minh tất cả bean lazy đã tạo instance thành công.
5. Nếu thêm `ApplicationRunner` này vào production, nó có thể in ra nhiều tên lớp và cấu trúc nội bộ; chỉ bật khi có mục đích chẩn đoán và kiểm soát log.

## 6. Kiểm tra bean theo kiểu và context hierarchy

### 6.1. Tìm bean theo kiểu mà không chủ động eager-init

Khi đã biết kiểu cần kiểm tra, có thể dùng:

~~~java
String[] names = context.getBeanNamesForType(
        CacheService.class,
        true,
        false);
~~~

Tham số:
- `includeNonSingletons=true`: xét cả prototype và các scope không phải singleton.
- `allowEagerInit=false`: không yêu cầu khởi tạo eager FactoryBean chỉ để xác định kiểu.

Kết quả là tên bean phù hợp kiểu, không phải map instance. Với FactoryBean mà kiểu object do factory tạo ra không thể xác định nếu không khởi tạo factory, kết quả tìm kiếm có thể không đầy đủ. Nếu cần xác nhận instance thật, hãy truy cập bean có chủ đích và xử lý khả năng tạo bean gây side effect/lỗi.

### 6.2. BeanFactoryUtils khi có context cha–con

Một ApplicationContext có thể có parent context. Ví dụ, ứng dụng web có management context riêng hoặc ứng dụng tạo nhiều context con.

Các phương thức `ListableBeanFactory` thông thường chỉ xét bean ở factory hiện tại. Để xét tên bean ở các factory cha, Spring Framework cung cấp:

~~~java
import org.springframework.beans.factory.BeanFactoryUtils;
import org.springframework.context.ConfigurableApplicationContext;

// context là ConfigurableApplicationContext.
String[] allNames =
        BeanFactoryUtils.beanNamesIncludingAncestors(context);
~~~

Nếu muốn lọc theo kiểu:

~~~java
String[] cacheNames =
        BeanFactoryUtils.beanNamesForTypeIncludingAncestors(
                context,
                CacheService.class,
                true,
                false);
~~~

Cách này giúp xét bean trong hierarchy. Tuy nhiên khi chẩn đoán, vẫn cần ghi nhận bean thuộc context nào, vì bean cùng tên ở child context có thể che khuất bean ở parent theo quy tắc phân giải của Spring.

Trong Condition Evaluation Report, `getParent()` cho phép lần theo report ở factory cha. Với Actuator, cả `/conditions` và `/beans` trả về map `contexts` cùng `parentId`. **Hãy ghép báo cáo và bean inventory theo đúng context ID**, không so condition của context con với danh sách bean của context cha rồi kết luận thiếu bean.

## 7. Kiểm thử bằng ApplicationContextRunner

`ApplicationContextRunner` cho phép tạo context nhỏ, kiểm soát property và auto-configuration. Đây là cách tốt để kiểm chứng đồng thời:
- condition outcome có match không;
- bean definition có được đăng ký không;
- bean name và kiểu thực tế có xuất hiện trong context không.

### 7.1. Cấu hình auto-configuration thử nghiệm

Tạo file **`src/test/java/example/ConditionAndBeanInventoryTests.java`**:

~~~java
package example;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionAndBeanInventoryTests {

    static class CacheService {
    }

    @AutoConfiguration
    static class CacheAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.cache",
                name = "enabled",
                havingValue = "true")
        CacheService cacheService() {
            return new CacheService();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CacheAutoConfiguration.class));

    private Map.Entry<String,
            ConditionEvaluationReport.ConditionAndOutcomes> cacheOutcome(
                    ConditionEvaluationReport report) {

        return report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith("#cacheService"))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void matchingConditionHasCorrespondingBeanDefinition() {
        runner.withPropertyValues("demo.cache.enabled=true")
                .run(context -> {
                    ConditionEvaluationReport report =
                            ConditionEvaluationReport.find(
                                    context.getBeanFactory());

                    assertThat(report).isNotNull();

                    var outcomes = cacheOutcome(report).getValue();
                    assertThat(outcomes.isFullMatch()).isTrue();

                    assertThat(context.getBeanDefinitionNames())
                            .contains("cacheService");

                    assertThat(context.getBeanNamesForType(
                            CacheService.class, true, false))
                            .containsExactly("cacheService");
                });
    }

    @Test
    void nonMatchingConditionDoesNotRegisterBeanDefinition() {
        runner.withPropertyValues("demo.cache.enabled=false")
                .run(context -> {
                    ConditionEvaluationReport report =
                            ConditionEvaluationReport.find(
                                    context.getBeanFactory());

                    assertThat(report).isNotNull();

                    var outcomes = cacheOutcome(report).getValue();
                    assertThat(outcomes.isFullMatch()).isFalse();

                    assertThat(context.getBeanDefinitionNames())
                            .doesNotContain("cacheService");

                    assertThat(context.getBeanNamesForType(
                            CacheService.class, true, false))
                            .isEmpty();
                });
    }
}
~~~

Dự án test cần `spring-boot-starter-test`; auto-configuration và `ConditionEvaluationReport` thuộc các dependency Spring Boot mà starter test sử dụng. Ví dụ phù hợp với Spring Boot 3.5.x vì dùng `ConditionAndOutcomes.isFullMatch()`.

Chạy:

~~~bash
./mvnw test -Dtest=ConditionAndBeanInventoryTests
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=ConditionAndBeanInventoryTests'
~~~

Hoặc dùng Maven cài sẵn:

~~~bash
mvn test -Dtest=ConditionAndBeanInventoryTests
~~~

**Kết quả kỳ vọng:** hai test PASS:
- Khi `demo.cache.enabled=true`, report của source `#cacheService` full match và bean name `cacheService` có trong inventory.
- Khi property là `false`, source không full match và bean definition không được đăng ký.

Không đưa ra một chuỗi stdout cố định vì Maven/Surefire thay đổi cách hiển thị theo phiên bản. Test xác nhận trực tiếp điều kiện và bean list bằng assertion.

### 7.2. Vì sao không chỉ assert hasBean?

Một assertion như:

~~~java
assertThat(context).hasBean("cacheService");
~~~

xác nhận tên bean tồn tại, nhưng không giải thích **vì sao** bean được đăng ký. Ngược lại, chỉ assert `outcomes.isFullMatch()` không xác nhận bean inventory thực sự có definition. Kết hợp cả hai assertion mới kiểm tra được quan hệ giữa quyết định điều kiện và kết quả đăng ký.

## 8. Cách đọc tình huống thực tế khi hai nguồn không trùng nhau

| Condition report | Bean inventory | Cách diễn giải và bước tiếp theo |
| --- | --- | --- |
| Method source MATCH | Có bean tương ứng | Điều kiện đạt và bean definition xuất hiện; kiểm tra tiếp scope/instance nếu lỗi xảy ra lúc sử dụng |
| Class source MATCH | Không thấy bean nghiệp vụ | Class config được chấp nhận nhưng method bean có thể có condition riêng, không khai báo bean cần tìm, hoặc tên bean khác |
| Method source MATCH | Không thấy bean cùng tên | Kiểm tra tên `@Bean` tùy chỉnh, context ID, loại FactoryBean, và bean definition bị thay thế |
| Method source NO_MATCH | Không có bean | Thường là kết quả mong đợi; đọc message trong `notMatched` để biết condition thất bại |
| Method source NO_MATCH | Vẫn có bean cùng kiểu | Bean có thể đến từ user configuration, auto-configuration khác, parent context hoặc đăng ký thủ công |
| Method source MATCH | Bean definition có, nhưng gọi bean bị lỗi | Điều kiện đã qua; điều tra constructor, dependency, init method, external service và stack trace |
| Không thấy source trong report | Có bean | Bean có thể được tạo bởi user configuration, component scan, đăng ký thủ công hoặc một source không thuộc phần report đang xét |
| Source không có trong report và bean không có | Chưa đủ dữ liệu | Kiểm tra class có phải auto-configuration candidate không, có bị exclude không, có đúng context và đúng phiên bản không |

### Các nguyên nhân thường gặp

**1. Condition ở cấp class và method khác nhau**

Ví dụ lớp `CacheAutoConfiguration` thỏa `@ConditionalOnClass`, nhưng method `cacheManager()` có thêm `@ConditionalOnProperty` và property không đạt. Nhìn class-level positive match mà kết luận bean chắc chắn tồn tại là sai.

**2. Bean name không giống method name**

Theo mặc định, tên method `@Bean` thường là bean name. Nhưng khai báo:

~~~java
@Bean("primaryCache")
CacheService cacheManager() {
    return new CacheService();
}
~~~

thì inventory có `primaryCache`, không phải `cacheManager`.

**3. Condition đã match nhưng bean khởi tạo thất bại**

Condition được đánh giá trong quá trình cấu hình/đăng ký bean definition. Constructor, dependency, `@PostConstruct`, init method hoặc kết nối bên ngoài có thể lỗi khi instance được tạo. Condition report không phải health check cho object.

**4. Bean lazy chưa được khởi tạo**

Bean definition có thể nằm trong inventory nhưng instance chưa tồn tại. Khi gọi `getBean`, Spring mới tạo instance. Điều này thường đúng với `@Lazy`, lazy-init toàn context hoặc prototype.

**5. Bean nằm ở context khác**

Actuator trả nhiều context theo ID. Một bean có thể nằm ở context cha hoặc management context, trong khi condition report đang xem context con. Luôn đối chiếu `parentId` và context ID.

**6. Auto-configuration bị exclude**

Một lớp được khai báo trong `spring.autoconfigure.exclude`, `exclude` hoặc `excludeName` có thể không đi qua đánh giá condition bình thường. Trong API `ConditionEvaluationReport`, xem `getExclusions()`. Không nên đợi mọi lớp bị exclude xuất hiện trong `positiveMatches` hoặc `negativeMatches`.

**7. Auto-configuration ordering**

Các `@ConditionalOnBean` và `@ConditionalOnMissingBean` có thể phụ thuộc bean definitions được xử lý trước đó. Nếu cấu hình phụ thuộc một bean từ auto-configuration khác, thứ tự cấu hình có thể quyết định kết quả. Xem message `OnBeanCondition`, source method và thứ tự `@AutoConfiguration(before/after)`.

## 9. Quy trình chẩn đoán đề xuất

Khi một bean mong đợi không có trong context, thực hiện theo trình tự:

1. **Xác định context cần kiểm tra.** Ghi lại context ID, display name, parent context và profile đang hoạt động.
2. **Tìm source trong condition report.** Tra lớp auto-configuration và method `@Bean`; xác định source nằm trong positive hay negative matches.
3. **Đọc tất cả outcome của source.** Với negative source, xem chính xác condition nào không match và condition nào đã match.
4. **Kiểm tra exclusions.** Nếu lớp không được đánh giá, xem `getExclusions()` hoặc báo cáo debug.
5. **Tìm bean trong inventory cùng context.** Dùng tên bean, type, resource, factory method và dependencies.
6. **Kiểm tra tên thực tế.** Đọc `@Bean("...")`, alias và factory method.
7. **Kiểm tra instance.** Nếu definition tồn tại nhưng dùng bean lỗi, lấy stack trace khi khởi tạo hoặc truy cập bean có chủ đích.
8. **Kiểm tra context cha–con.** Khi cần, dùng `BeanFactoryUtils` hoặc duyệt từng context.
9. **Kiểm thử lại bằng ApplicationContextRunner.** Cô lập property, classpath và user beans để tái tạo kết quả.

### Bật Condition Evaluation Report qua debug

Có thể khởi động ứng dụng với:

~~~bash
java -jar target/my-app.jar --debug
~~~

Spring Boot ghi **Conditions Evaluation Report** ra log, hữu ích khi endpoint Actuator chưa được cấu hình hoặc ứng dụng không khởi động đủ để gọi endpoint. Khi lỗi startup, đọc phần condition report cùng stack trace; condition report giải thích quyết định cấu hình, còn stack trace giải thích lỗi tạo bean.

Trong test auto-configuration, có thể dùng `ConditionEvaluationReportLoggingListener` để log report:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // Assertion về bean và condition đặt tại đây.
        });
~~~

Import trong Boot 3.5:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Listener này được thiết kế làm `ApplicationContextInitializer`; không dùng chung một instance initializer cho nhiều context instance.

## 10. Các lưu ý khi dùng Actuator trong môi trường thật

Endpoint `/actuator/conditions` và `/actuator/beans` rất hữu ích nhưng chứa thông tin nội bộ:
- tên lớp, tên bean và tên thư viện;
- cấu trúc context;
- dependency giữa các bean;
- resource description có thể gợi ý vị trí cấu hình;
- chi tiết điều kiện và property liên quan.

Không expose rộng các endpoint này ra Internet. Trong production:
1. Chỉ expose endpoint cần thiết.
2. Giới hạn qua management port/network hoặc firewall khi phù hợp.
3. Dùng Spring Security để yêu cầu quyền quản trị.
4. Tránh log condition message chứa thông tin cấu hình nhạy cảm.
5. Dùng log chẩn đoán ở mức phù hợp và tắt sau khi hoàn thành điều tra.
6. Khi chia sẻ report ra ngoài nhóm vận hành, loại bỏ thông tin bí mật hoặc tên nội bộ không cần thiết.

Việc expose endpoint có thể cấu hình qua:

~~~properties
management.endpoints.web.exposure.include=health,conditions,beans
~~~

Nhưng cấu hình expose chỉ quyết định endpoint có thể truy cập qua web hay không; nó **không tự thiết lập authorization**. Chính sách bảo vệ phải được cấu hình riêng.

## 11. Những hiểu nhầm cần tránh

| Hiểu nhầm | Thực tế |
| --- | --- |
| Positive match đồng nghĩa bean đã khởi tạo | Chỉ cho biết condition match; bean creation có thể diễn ra sau |
| Mọi positive class match đều phải có bean nghiệp vụ cùng tên | Class condition và method condition có phạm vi khác nhau |
| Bean inventory chỉ có bean do auto-configuration tạo | Còn có bean từ component scan, user configuration, import và đăng ký thủ công |
| `getBeanDefinitionNames()` bao gồm cả parent context | Chỉ factory hiện tại; dùng `BeanFactoryUtils` hoặc duyệt hierarchy |
| `getBeansOfType()` là phép đọc metadata không side effect | Nó lấy instance, có thể khởi tạo lazy/prototype/FactoryBean |
| `/actuator/conditions` cũng là danh sách bean | Nó là báo cáo điều kiện; danh sách bean nằm ở `/actuator/beans` |
| Bean xuất hiện trong /beans nghĩa là đã khởi tạo thành công | Endpoint mô tả bean metadata; scope/lazy và thời điểm tạo instance vẫn quan trọng |
| Negative match có nghĩa tất cả condition đều thất bại | Có thể chỉ một condition không match, các condition khác đã match |
| Bean cùng kiểu chắc chắn đến từ auto-configuration đang xét | Có thể được cung cấp bởi user config hoặc một auto-configuration khác |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Condition report cho thấy `MyAutoConfiguration#myService` MATCH. Có thể kết luận instance `MyService` đã được tạo thành công không?

**Đáp án:** Không. Match chỉ cho biết các điều kiện cho source đó đạt. Cần kiểm tra bean definition trong inventory và kiểm tra quá trình tạo instance nếu bean bị lỗi.

**Câu 2.** `/actuator/conditions` và `/actuator/beans` khác nhau ở điểm nào?

**Đáp án:** `conditions` giải thích condition outcomes theo class/method; `beans` liệt kê bean metadata như name, type, scope, resource và dependencies.

**Câu 3.** Một source có hai condition match và một condition không match xuất hiện ở đâu?

**Đáp án:** Nó thuộc `negativeMatches`; phần `notMatched` chứa condition thất bại, phần `matched` vẫn liệt kê hai condition đạt.

**Câu 4.** Vì sao `getBeanDefinitionNames()` có thể không tìm thấy bean nằm ở parent context?

**Đáp án:** Vì API này chỉ xét BeanFactory hiện tại. Dùng `BeanFactoryUtils.beanNamesIncludingAncestors(...)` hoặc duyệt từng context trong hierarchy.

**Câu 5.** Nếu `@Bean("primaryCache")` nằm trong method `cacheManager()`, tên nào cần tìm trong Actuator beans?

**Đáp án:** Tìm `primaryCache`, vì tên đã được chỉ định tường minh trong annotation.

**Câu 6.** Vì sao không nên gọi `getBeansOfType(Object.class)` để kiểm kê toàn bộ bean production?

**Đáp án:** Vì nó lấy instance, có thể khởi tạo lazy bean, prototype hoặc FactoryBean, gây side effect và làm thay đổi trạng thái ứng dụng trong lúc chẩn đoán.

## 13. Tài liệu tham khảo chính thức

- Spring Boot 3.5 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.5 API — `ConditionOutcome`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Spring Boot 3.5 Actuator API — Conditions endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/conditions.html
- Spring Boot 3.5 Actuator API — Beans endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/beans.html
- Spring Framework 6.2 API — `ListableBeanFactory`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html
- Spring Framework 6.2 API — `BeanFactoryUtils`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/BeanFactoryUtils.html
- Spring Boot Reference — Creating Your Own Auto-configuration and ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
