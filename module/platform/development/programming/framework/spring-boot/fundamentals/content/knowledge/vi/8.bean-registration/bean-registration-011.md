# Kiểm tra bean đã được đăng ký bằng công cụ hoặc truy vấn context

Khi làm việc với Spring Boot, một lớp có thể mang annotation **@Component**, **@Service**, **@Repository** hoặc được khai báo qua **@Bean**, nhưng điều đó chưa đủ để kết luận object tương ứng đã xuất hiện trong Spring container. Component có thể nằm ngoài phạm vi quét, cấu hình có thể chưa được import, profile hoặc condition có thể không thỏa, và một bean factory method có thể thất bại khi khởi tạo.

Vì vậy, sau khi khai báo bean, cần biết cách **kiểm tra bean có được đăng ký hay không**, **tên bean là gì**, **bean có kiểu nào**, và **nó có được khởi tạo thành công hay chưa**.

Spring cung cấp nhiều cách quan sát khác nhau:

- Truy vấn **ApplicationContext** và các API của BeanFactory trong code hoặc debugger.
- Quan sát **BeanDefinition** để hiểu định nghĩa bean đã đăng ký.
- Dùng **Spring Boot Actuator** và endpoint **/actuator/beans** để xem bean trong ứng dụng đang chạy.
- Dùng condition report để tìm lý do auto-configuration được áp dụng hoặc bị bỏ qua.
- Viết test với Spring context để xác nhận bean tồn tại trong cấu hình cụ thể.

Mỗi cách trả lời một câu hỏi hơi khác nhau. Cần phân biệt **bean definition**, **bean instance**, **bean đang được khởi tạo**, và **object Java tự tạo bằng new** để tránh đọc nhầm kết quả.

## 1. Trước hết, cần biết mình muốn kiểm tra điều gì

Giả sử có service:

~~~java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Và controller:

~~~java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "bạn") String name) {
        return greetingService.greet(name);
    }
}
~~~

Nếu hai class nằm trong phạm vi component scan và context khởi động thành công, Spring sẽ đăng ký các bean tương ứng. Nhưng khi nói “GreetingService đã có chưa?”, có nhiều ý nghĩa có thể cần kiểm tra:

| Câu hỏi | Điều cần quan sát |
|---|---|
| Có bean definition được đăng ký không? | Tên bean và metadata trong BeanFactory. |
| Context có tìm thấy bean theo tên không? | **containsBean("greetingService")**. |
| Có bean nào phù hợp với kiểu không? | **getBeanNamesForType(...)** hoặc **getBeansOfType(...)**. |
| Bean đã được khởi tạo thành công chưa? | Truy vấn instance hoặc quan sát startup/runtime. |
| Bean có phải singleton không? | Scope trong BeanDefinition hoặc API scope tương ứng. |
| Bean đến từ cấu hình nào? | Resource/metadata của BeanDefinition, condition report, debug hoặc endpoint Actuator. |
| Vì sao auto-configuration không tạo bean? | Condition evaluation report và điều kiện cấu hình. |

Không nên gộp tất cả các câu hỏi này thành một câu “bean có tồn tại không”, vì câu trả lời của từng API có thể khác nhau.

## 2. ApplicationContext là điểm truy vấn phổ biến nhất

**ApplicationContext** là giao diện trung tâm của Spring IoC container. Nó kế thừa các khả năng tra cứu bean từ BeanFactory và bổ sung các dịch vụ ứng dụng như event, resource và message source.

Trong một component do Spring quản lý, có thể inject ApplicationContext:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInspector {
    private final ApplicationContext context;

    public BeanInspector(ApplicationContext context) {
        this.context = context;
    }
}
~~~

Từ **context**, ta có thể kiểm tra bean theo tên, kiểu, alias hoặc lấy instance. Trong code nghiệp vụ thông thường, không nên lạm dụng truy vấn context để thay thế constructor injection; ví dụ này nhằm giải thích công cụ quan sát và hữu ích cho một số hạ tầng/chẩn đoán.

### 2.1. Kiểm tra bean theo tên bằng containsBean

~~~java
boolean exists = context.containsBean("greetingService");
System.out.println("greetingService exists = " + exists);
~~~

Nếu kết quả là **true**, context có thể tìm thấy bean theo tên đó. Cần nhớ:

- Tên bean mặc định của class **GreetingService** thường là **greetingService** (chữ cái đầu viết thường), theo quy tắc đặt tên component thông dụng.
- Tên bean có thể được chỉ định tường minh bằng **@Component("...")**, **@Service("...")** hoặc tên phương thức **@Bean**.
- **containsBean** có thể xét cả bean từ parent context trong hệ phân cấp context.
- **true** không đồng nghĩa bean đã được khởi tạo thành công và mọi phương thức của nó đều hoạt động.

Ví dụ bean có tên riêng:

~~~java
@Service("primaryGreetingService")
public class GreetingService {
    // ...
}
~~~

Khi đó có thể kiểm tra:

~~~java
context.containsBean("primaryGreetingService");
~~~

Tên **greetingService** không còn là tên phù hợp nếu class được đăng ký với tên **primaryGreetingService** và không có alias tương ứng.

### 2.2. Lấy bean theo tên hoặc kiểu

~~~java
GreetingService service =
        context.getBean("greetingService", GreetingService.class);

GreetingService byType =
        context.getBean(GreetingService.class);
~~~

Hai cách lookup khác nhau ở tiêu chí lựa chọn:

- **getBean(name, type)** yêu cầu một bean theo tên, đồng thời kiểm tra kiểu tương thích.
- **getBean(type)** yêu cầu một bean phù hợp theo kiểu.

Nếu không có bean phù hợp, Spring ném exception như **NoSuchBeanDefinitionException**. Nếu có nhiều bean phù hợp với kiểu mà không thể chọn một candidate duy nhất, có thể gặp **NoUniqueBeanDefinitionException**.

**getBean() có thể khiến bean được khởi tạo.** Vì vậy nếu mục tiêu chỉ là xem bean definition hoặc kiểm tra tên đã đăng ký, đừng vô tình gọi lookup lấy instance rồi kết luận rằng trước đó bean đã được tạo sẵn.

### 2.3. Lấy tất cả bean theo một kiểu

~~~java
import java.util.Map;

Map<String, GreetingService> services =
        context.getBeansOfType(GreetingService.class);

services.forEach((name, service) ->
        System.out.println(name + " -> " + service.getClass().getName())
);
~~~

Kết quả là map từ **bean name** tới instance có kiểu tương thích. Cách này hữu ích khi một interface có nhiều implementation hoặc muốn quan sát toàn bộ bean thuộc một họ.

Ví dụ:

~~~java
public interface NotificationSender {
    void send(String message);
}
~~~

~~~java
@Component("emailSender")
class EmailSender implements NotificationSender {
    public void send(String message) {
        // Gửi email.
    }
}
~~~

~~~java
@Component("smsSender")
class SmsSender implements NotificationSender {
    public void send(String message) {
        // Gửi SMS.
    }
}
~~~

Truy vấn:

~~~java
Map<String, NotificationSender> senders =
        context.getBeansOfType(NotificationSender.class);
~~~

có thể trả về cả **emailSender** và **smsSender** nếu cả hai đã được đăng ký và có thể lấy được.

Lưu ý rằng việc lấy map instance có thể khởi tạo các bean lazy phù hợp. Nếu chỉ cần danh sách tên, hãy dùng API truy vấn tên theo kiểu thay vì yêu cầu toàn bộ object.

### 2.4. Liệt kê tên bean theo kiểu

ApplicationContext cũng cung cấp khả năng truy vấn qua **ListableBeanFactory**:

~~~java
String[] names =
        context.getBeanNamesForType(GreetingService.class);

for (String name : names) {
    System.out.println(name);
}
~~~

Đây là cách gọn để biết những bean name mà context có thể liệt kê theo kiểu. Tùy API và tham số truy vấn, việc xác định kiểu có thể liên quan đến FactoryBean hoặc khởi tạo sớm factory; khi cần tránh eager initialization, hãy dùng overload phù hợp của BeanFactory/ListableBeanFactory và đọc rõ ý nghĩa tham số.

Không phải mọi phương thức liệt kê đều có cùng hành vi về **parent context**, bean lazy và FactoryBean. Khi chẩn đoán chính xác, cần biết đang gọi API nào thay vì giả định tất cả chỉ đọc một danh sách tĩnh.

## 3. Phân biệt BeanDefinition với bean instance

Đây là điểm quan trọng khi kiểm tra bean.

**BeanDefinition** là metadata mô tả cách Spring quản lý một bean: bean class hoặc factory method, scope, lazy flag, dependency và những thuộc tính cấu hình khác. **Bean instance** là object cụ thể được tạo từ định nghĩa đó hoặc được đăng ký theo một cơ chế tương ứng.

Ví dụ:

~~~java
@Configuration
public class AppConfiguration {
    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

Khi cấu hình được xử lý, Spring đăng ký định nghĩa bean. Nếu bean là singleton eager mặc định, instance thường được tạo trong quá trình refresh context. Nếu bean lazy, definition có thể tồn tại trong khi instance chưa được tạo.

### 3.1. Lấy tên các bean definition

Với một context triển khai **ConfigurableApplicationContext**, có thể lấy BeanFactory:

~~~java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public void printDefinitions(ConfigurableApplicationContext context) {
    ConfigurableListableBeanFactory beanFactory =
            context.getBeanFactory();

    for (String name : beanFactory.getBeanDefinitionNames()) {
        System.out.println(name);
    }
}
~~~

**getBeanDefinitionNames()** liệt kê các **bean definition được đăng ký trong BeanFactory hiện tại**. Nó không phải danh sách mọi object Java đang tồn tại trong JVM.

Một object được tạo bằng:

~~~java
GreetingService manual = new GreetingService();
~~~

không tự xuất hiện trong danh sách này, bởi dòng **new** không đăng ký BeanDefinition vào context.

### 3.2. Kiểm tra definition theo tên

~~~java
boolean hasDefinition =
        beanFactory.containsBeanDefinition("greetingService");

if (hasDefinition) {
    var definition =
            beanFactory.getBeanDefinition("greetingService");

    System.out.println("Scope: " + definition.getScope());
    System.out.println("Lazy: " + definition.isLazyInit());
    System.out.println("Bean class: " + definition.getBeanClassName());
    System.out.println("Resource: " + definition.getResourceDescription());
}
~~~

Thông tin có thể giúp hiểu:

- Bean definition có được đăng ký tại factory hiện tại không?
- Scope được khai báo là gì?
- Bean có đánh dấu lazy initialization không?
- Có tên class hoặc mô tả resource nào để truy nguyên nguồn cấu hình không?

**getBeanClassName() có thể trả null**, ví dụ khi bean được định nghĩa bằng factory method hoặc khi class không được ghi trực tiếp trong definition. Đừng coi null là bằng chứng bean không tồn tại.

### 3.3. containsBean và containsBeanDefinition khác nhau

| API | Ý nghĩa |
|---|---|
| **ApplicationContext.containsBean(name)** | Kiểm tra context có bean theo tên hay không; có thể xét parent context. |
| **BeanFactory.containsBean(name)** | Kiểm tra bean theo tên trong factory và có thể bao gồm ancestor theo hợp đồng BeanFactory. |
| **BeanDefinitionRegistry.containsBeanDefinition(name)** | Kiểm tra definition có được đăng ký tại registry/factory đó không. |
| **ConfigurableListableBeanFactory.getBeanDefinitionNames()** | Liệt kê các definition thuộc factory hiện tại. |

Một bean có thể được cung cấp bởi **parent context** nên containsBean trả true trong khi danh sách definition của child factory không có tên đó. Ngược lại, một singleton có thể được đăng ký trực tiếp mà không có BeanDefinition thông thường; khi đó kiểm tra definition và kiểm tra instance có thể cho kết quả khác nhau.

## 4. Kiểm tra singleton instance đã được tạo hay chưa

Với một **DefaultListableBeanFactory** hoặc factory triển khai **ConfigurableListableBeanFactory**, có thể quan sát registry singleton thông qua các API phù hợp. Ví dụ:

~~~java
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public void inspectSingleton(
        ConfigurableListableBeanFactory beanFactory,
        String beanName) {

    System.out.println(
            "Has definition: "
                    + beanFactory.containsBeanDefinition(beanName)
    );
    System.out.println(
            "Has singleton instance: "
                    + beanFactory.containsSingleton(beanName)
    );
}
~~~

Ý nghĩa:

- **containsBeanDefinition** cho biết có bean definition trong factory hiện tại.
- **containsSingleton** cho biết singleton instance có được đăng ký trong singleton registry dưới tên đó hay chưa.

Không thể dùng **containsSingleton=false** để kết luận bean không tồn tại. Bean có thể:

- Đã có definition nhưng chưa được khởi tạo do lazy initialization.
- Thuộc prototype scope, không được lưu trong singleton registry.
- Đến từ parent context.
- Được cung cấp theo cơ chế khác.

Một lần lookup bean có thể khiến singleton lazy được tạo; sau đó containsSingleton đổi từ false sang true. Vì vậy thao tác quan sát cũng có thể ảnh hưởng trạng thái nếu bạn gọi API khởi tạo bean.

### 4.1. Liệt kê singleton names

Một factory cụ thể có thể cung cấp danh sách singleton đã đăng ký:

~~~java
String[] singletonNames = beanFactory.getSingletonNames();

for (String name : singletonNames) {
    System.out.println(name);
}
~~~

Đây là danh sách instance singleton đã được registry ghi nhận, không phải toàn bộ definition, cũng không phải toàn bộ bean theo mọi scope. Với prototype bean, mỗi lần lấy có thể tạo instance mới mà không xuất hiện trong danh sách singleton.

## 5. Kiểm tra alias, scope và kiểu bean

### 5.1. Tên bean và alias

Một bean có thể có nhiều tên truy cập thông qua alias. Ví dụ:

~~~java
@Configuration
public class GreetingConfiguration {
    @Bean({"greetingService", "primaryGreeting"})
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

Tên **greetingService** là tên bean theo phương thức; **primaryGreeting** là alias bổ sung. Khi kiểm tra, cần phân biệt alias với hai bean instance độc lập.

Có thể truy vấn:

~~~java
String[] aliases = context.getAliases("greetingService");
for (String alias : aliases) {
    System.out.println(alias);
}
~~~

Nếu lookup bằng alias, bạn vẫn có thể nhận về cùng bean. Không nên đếm alias như những instance riêng.

### 5.2. Kiểm tra scope

Với BeanFactory:

~~~java
String scope = beanFactory.getMergedBeanDefinition("greetingService")
        .getScope();

System.out.println(scope);
~~~

Nếu scope rỗng trong BeanDefinition thông thường, Spring sử dụng **singleton** làm scope mặc định. Với một số kiểu bean/factory đặc biệt, cần xem metadata và hành vi thực tế thay vì giả định mọi definition có chuỗi scope tường minh.

Scope trả lời câu hỏi **container cung cấp instance theo quy tắc nào**. Nó không khẳng định bean đã được khởi tạo.

### 5.3. Kiểm tra kiểu bean

~~~java
Class<?> type = context.getType("greetingService");
System.out.println(type);
~~~

**getType** có thể trả về kiểu mà container dự đoán cho bean. Với factory method, **FactoryBean**, proxy hoặc cấu hình lazy, kiểu dự đoán có thể không phải lúc nào cũng là class runtime cuối cùng của target object.

Nếu đã lấy instance:

~~~java
Object bean = context.getBean("greetingService");
System.out.println(bean.getClass().getName());
~~~

thì bạn quan sát class runtime của reference được trả về. Nếu bean được bọc bởi AOP proxy, class có thể là class proxy thay vì class implementation.

## 6. Dùng Spring Boot Actuator để xem bean đang chạy

Khi cần quan sát một ứng dụng đã khởi động, **Spring Boot Actuator** cung cấp endpoint **beans** để xem các bean trong ApplicationContext.

Thêm dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Spring Boot 3.x, endpoint web thường cần được expose rõ ràng. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans
~~~

Sau khi ứng dụng chạy, endpoint mặc định thường có đường dẫn:

~~~http
GET /actuator/beans
~~~

Đường dẫn thực tế có thể khác nếu ứng dụng đổi **management.endpoints.web.base-path**, management port hoặc cấu hình context path. Endpoint cũng phải được phép truy cập theo cấu hình bảo mật hiện tại.

### 6.1. Endpoint /actuator/beans cung cấp thông tin gì?

Endpoint này trình bày các context và bean mà actuator có thể quan sát, thường bao gồm thông tin như:

- Bean name.
- Aliases.
- Scope.
- Type/kiểu bean.
- Resource hoặc nguồn định nghĩa nếu có.
- Các bean mà bean phụ thuộc vào hoặc những bean phụ thuộc vào nó, khi thông tin được cung cấp.

Cấu trúc JSON chi tiết phụ thuộc phiên bản và cấu hình; nên xem response thực tế của ứng dụng đang chạy thay vì hardcode một schema từ hướng dẫn khác phiên bản.

Ví dụ một đoạn JSON minh họa:

~~~json
{
  "contexts": {
    "application": {
      "beans": {
        "greetingService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.demo.service.GreetingService",
          "resource": "..."
        }
      }
    }
  }
}
~~~

Đây là dữ liệu minh họa, không phải response nguyên văn được bảo đảm cho mọi phiên bản Spring Boot. Endpoint có thể hiển thị nhiều context nếu ứng dụng có context hierarchy.

### 6.2. Vì sao Actuator hữu ích?

Actuator đặc biệt tiện khi:

- Ứng dụng đang chạy ở một môi trường mà bạn không thể dễ dàng attach debugger.
- Cần xem bean nào thực sự xuất hiện trong context sau startup.
- Cần xác định bean name, type, scope hoặc nguồn định nghĩa.
- Muốn quan sát sự khác nhau giữa local, staging và production.
- Cần điều tra một bean được thêm bởi starter hoặc thư viện tích hợp.

Nó giúp trả lời câu hỏi **context đang công bố những bean nào**, không thay thế việc đọc source hoặc tìm hiểu điều kiện tạo bean.

### 6.3. Endpoint beans không phải endpoint conditions

Hai endpoint này phục vụ hai mục tiêu khác nhau:

| Endpoint | Mục đích |
|---|---|
| **/actuator/beans** | Xem bean và thông tin liên quan trong các context. |
| **/actuator/conditions** | Xem báo cáo điều kiện liên quan đến auto-configuration. |

Nếu GreetingService không xuất hiện:

- **beans** giúp xác nhận bean có mặt trong context hay không.
- **conditions** có thể giải thích auto-configuration liên quan đã match hay bị loại vì điều kiện nào.

Một bean do **@ComponentScan** đăng ký có thể không có entry tương ứng trong condition report như một auto-configuration cụ thể. Ngược lại, condition report có thể cho biết auto-configuration match nhưng bean method bên trong có điều kiện riêng hoặc quá trình khởi tạo thất bại.

### 6.4. Bảo mật endpoint quản trị

Thông tin bean có thể tiết lộ:

- Tên package và class nội bộ.
- Tên tích hợp, client hoặc hệ thống dữ liệu.
- Cấu trúc thành phần và quan hệ phụ thuộc.
- Một phần thông tin về cấu hình ứng dụng.

Vì vậy không nên mở công khai endpoint **/actuator/beans** chỉ để tiện kiểm tra. Trong môi trường thực tế, hãy giới hạn endpoint qua authentication/authorization, mạng quản trị hoặc cấu hình expose phù hợp. Chỉ expose những endpoint cần thiết.

Ví dụ cấu hình expose **health** và **beans** chỉ quyết định endpoint nào có thể được công bố qua web; nó **không tự thiết lập đầy đủ chính sách bảo mật**. Cần cấu hình Spring Security hoặc cơ chế bảo vệ tương ứng của môi trường triển khai.

## 7. Dùng condition evaluation report khi bean đến từ auto-configuration

Nếu bean được kỳ vọng đến từ Spring Boot auto-configuration, nhưng không thấy trong context, hãy xem **điều kiện lựa chọn cấu hình**.

Chạy ứng dụng với tùy chọn:

~~~bash
java -jar app.jar --debug
~~~

Boot có thể in **Condition Evaluation Report** trong log startup. Report thường có nhóm:

- **Positive matches**: các điều kiện được thỏa.
- **Negative matches**: điều kiện không thỏa và lý do.
- **Exclusions**: các auto-configuration bị loại trừ.

Ví dụ minh họa:

~~~text
Negative matches:
-----------------
GreetingAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty did not find property 'demo.greeting.enabled'
~~~

Tên class và câu chữ chỉ là ví dụ. Thông tin thực tế phụ thuộc auto-configuration, phiên bản Boot và các điều kiện đã khai báo.

### 7.1. Đọc kết quả condition đúng cách

Nếu report ghi **did not match**, hãy đọc điều kiện cụ thể:

- **@ConditionalOnClass**: class cần thiết không có trên classpath được kiểm tra.
- **@ConditionalOnProperty**: property không có hoặc giá trị không khớp.
- **@ConditionalOnBean**: bean cần thiết chưa có ở thời điểm đánh giá.
- **@ConditionalOnMissingBean**: đã có bean phù hợp nên bean mặc định nhường chỗ.
- **@ConditionalOnWebApplication**: loại context hiện tại không phù hợp.

Không phải mọi negative match là lỗi. Nếu ứng dụng không sử dụng một tích hợp tùy chọn, việc auto-configuration đó không được áp dụng là bình thường.

### 7.2. Positive match không chứng minh bean đã được tạo thành công

Một class auto-configuration có thể thỏa điều kiện cấp class, nhưng một phương thức **@Bean** bên trong có điều kiện khác. Ngoài ra, bean factory method có thể ném exception khi tạo instance.

Do đó, cần kết hợp:

1. **Condition report** để hiểu điều kiện.
2. **Beans endpoint hoặc ApplicationContext** để xác nhận bean được đăng ký/cung cấp.
3. **Startup log/stack trace** để xác định bean creation có thất bại không.

## 8. Kiểm tra bean bằng test với Spring context

Một cách kiểm tra đáng tin cậy là viết test khởi tạo đúng cấu hình Spring mà ứng dụng sử dụng.

### 8.1. Test toàn bộ Spring Boot application context

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.service.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class GreetingBeanRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void greetingServiceIsRegistered() {
        assertThat(context.containsBean("greetingService")).isTrue();
        assertThat(context.getBeansOfType(GreetingService.class))
                .hasSize(1);
    }
}
~~~

Test này xác nhận trong context được khởi động bởi **@SpringBootTest** có bean theo tên và có đúng một bean phù hợp kiểu GreetingService trong truy vấn đó.

**@SpringBootTest** thường tạo context với cấu hình ứng dụng được phát hiện theo quy ước hoặc được chỉ định. Nó có thể nặng hơn unit test thuần vì khởi tạo nhiều bean và tích hợp. Hãy dùng khi mục tiêu thật sự là kiểm tra wiring hoặc hành vi của context.

### 8.2. Test một cấu hình nhỏ bằng ApplicationContextRunner

Khi muốn kiểm tra auto-configuration mà không khởi động toàn bộ ứng dụng, Spring Boot test hỗ trợ **ApplicationContextRunner**.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(GreetingAutoConfiguration.class);

    @Test
    void registersGreetingServiceWhenEnabled() {
        contextRunner
                .withPropertyValues("demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                });
    }
}
~~~

Đây là ví dụ về cấu hình kiểm thử; cần có **spring-boot-starter-test** hoặc các dependency test thích hợp và class auto-configuration cùng các kiểu liên quan thực sự tồn tại trong dự án.

Có thể thêm một test cho trường hợp tắt:

~~~java
@Test
void doesNotRegisterGreetingServiceWhenDisabled() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(GreetingService.class);
            });
}
~~~

Điểm mạnh của ApplicationContextRunner là test một lát cắt cấu hình nhỏ, truyền property hoặc bean bổ sung và quan sát kết quả mà không cần dựng toàn bộ web server.

### 8.3. Test component scan và bean registration

Nếu muốn kiểm tra một component được tìm thấy từ package, có thể tạo context bằng cấu hình có **@ComponentScan** hoặc dùng test với cấu hình ứng dụng. Test nên phản ánh đúng package scan và profile mà ứng dụng cần.

Một unit test chỉ gọi:

~~~java
GreetingService service = new GreetingService();
~~~

không chứng minh **@Service** đã được quét hoặc bean được đăng ký. Nó chỉ chứng minh Java có thể tạo object.

## 9. Dùng debugger trong IDE

Khi chạy ứng dụng từ IntelliJ IDEA, Eclipse hoặc VS Code với Java extension, có thể đặt breakpoint để quan sát:

- ApplicationContext nào đang được tạo.
- Các bean definition đã đăng ký.
- Constructor hoặc factory method nào được gọi.
- BeanPostProcessor nào đang tác động.
- Bean nào được inject vào constructor của consumer.
- Một reference là target object hay AOP proxy.

### 9.1. Điểm dừng hữu ích

Với một lỗi thiếu bean, hãy đặt breakpoint ở:

1. Constructor của class cần được inject.
2. Configuration class hoặc factory method khai báo bean.
3. Code khởi tạo application context nếu cần.
4. Phần code tạo/đăng ký bean liên quan trong framework khi đã xác định được hướng điều tra.

Không cần bắt đầu bằng việc step-debug toàn bộ Spring Framework. Trước tiên xác nhận bean name, type và package scan; sau đó mới đi sâu vào điểm tạo bean nếu log và context chưa giải thích được.

### 9.2. Quan sát instance được inject

Ở constructor:

~~~java
public GreetingController(GreetingService greetingService) {
    this.greetingService = greetingService;
}
~~~

đặt breakpoint để xem giá trị tham số. Bạn có thể kiểm tra runtime class, instance identity và dependency bên trong. Nếu Spring AOP đang hoạt động, class của reference có thể là proxy; hãy dùng công cụ phù hợp để xem target class khi cần.

## 10. Truy vấn context không giống việc tìm mọi object trong JVM

Spring context chỉ biết những bean được đăng ký hoặc được cung cấp theo cơ chế container. Nó không phải bộ nhớ toàn cục chứa mọi object Java.

Ví dụ:

~~~java
GreetingService managed = context.getBean(GreetingService.class);
GreetingService manual = new GreetingService();
~~~

Object **manual** không tự xuất hiện trong:

~~~java
context.getBeanNamesForType(GreetingService.class);
~~~

trừ khi bạn có thêm một bước đăng ký nó như bean. Context không có nhiệm vụ theo dõi mọi lời gọi **new** của chương trình.

Ngược lại, một bean có thể được tạo bởi factory method mà code consumer không nhìn thấy lời gọi new. Điều quyết định là **đường đăng ký bean**, không phải class có annotation hay object được tạo bằng constructor nào.

## 11. Những tình huống làm kết quả kiểm tra khác nhau

### 11.1. Bean lazy chưa được khởi tạo

Với:

~~~java
@Bean
@org.springframework.context.annotation.Lazy
GreetingService greetingService() {
    return new GreetingService();
}
~~~

Bean definition có thể tồn tại dù instance singleton chưa được tạo. Một truy vấn chỉ kiểm tra definition có thể trả về có, trong khi kiểm tra singleton instance trả về chưa có. Khi gọi **getBean**, Spring có thể khởi tạo instance.

### 11.2. Prototype bean không nằm trong singleton registry

~~~java
@Component
@org.springframework.context.annotation.Scope("prototype")
class ReportDraft {
}
~~~

Prototype definition có thể tồn tại và lookup có thể tạo object mới mỗi lần. Không thấy tên trong singleton registry không có nghĩa prototype bean chưa đăng ký.

### 11.3. Parent và child ApplicationContext

Một ứng dụng có thể có nhiều context theo quan hệ cha/con, ví dụ một số cấu trúc web hoặc ứng dụng được cấu hình nhiều context. Bean ở parent có thể được child nhìn thấy qua quy tắc lookup, nhưng danh sách BeanDefinition của child không nhất thiết chứa definition của parent.

Khi kiểm tra:

- Xác định context đang được truy vấn.
- Kiểm tra quan hệ parent nếu có.
- Phân biệt bean được khai báo ở context hiện tại với bean kế thừa từ ancestor.

Actuator có thể trình bày nhiều context trong response của endpoint beans; đừng giả định toàn bộ ứng dụng chỉ có một map bean duy nhất.

### 11.4. FactoryBean

Spring có interface **FactoryBean<T>** cho phép một bean factory tạo ra object khác. Khi lookup bean theo tên thông thường, context thường cung cấp **object do FactoryBean tạo ra**; prefix **&** dùng để truy cập chính FactoryBean.

Ví dụ về cách lookup:

~~~java
Object product = context.getBean("clientFactory");
Object factory = context.getBean("&clientFactory");
~~~

Trong ví dụ, **clientFactory** là tên giả định của một FactoryBean. Hai lookup có thể trả hai kiểu object khác nhau: sản phẩm và factory. Điều này khiến việc so sánh tên bean, kiểu runtime và definition cần hiểu đúng cơ chế FactoryBean.

### 11.5. Bean proxy

Một bean được bọc proxy có thể có runtime class không trùng class implementation. Ví dụ một service có transaction hoặc aspect có thể được cung cấp qua JDK dynamic proxy hoặc class-based proxy tùy cấu hình.

Do đó:

- **getBeanNamesForType** có thể tìm bean theo kiểu mà Spring dự đoán.
- **getBean(name).getClass()** cho biết class của reference trả về, có thể là proxy.
- **BeanDefinition** giúp truy nguyên cách khai báo.

Không nên kết luận bean bị thiếu chỉ vì getClass() không phải class source mà bạn mong đợi.

## 12. Quy trình chẩn đoán khi không tìm thấy bean

Giả sử startup báo:

~~~text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.demo.GreetingService' available
~~~

Một quy trình điều tra có thể thực hiện:

### Bước 1: Kiểm tra kiểu và tên bean mong đợi

Xác định constructor đang yêu cầu **GreetingService** hay một interface khác. Nếu có nhiều implementation, cần kiểm tra candidate và qualifier.

### Bước 2: Xác định bean được đăng ký bằng cách nào

Bean đến từ:

- **@Component**, **@Service**, **@Repository** và component scanning?
- **@Bean** trong một **@Configuration**?
- **@Import** hoặc registrar?
- Auto-configuration từ một starter?
- Một cấu hình test hoặc profile riêng?

Không nên tìm trong mọi cơ chế cùng lúc; hãy xác định nguồn khai báo mong muốn trước.

### Bước 3: Kiểm tra phạm vi component scan hoặc import

Nếu là component, xem package của lớp main có bao phủ package component không. Nếu là **@Bean**, xác nhận configuration class được import/scan và điều kiện của nó thỏa.

### Bước 4: Kiểm tra profile và condition

Xác nhận profile đang active và các property thực tế. Nếu bean đến từ auto-configuration, đọc condition report để biết cấu hình nào không match hoặc bị exclude.

### Bước 5: Kiểm tra context thực tế

Trong debugger, test hoặc Actuator, xem:

- Bean name có xuất hiện không?
- Có definition không?
- Có bean cùng kiểu khác tên không?
- Bean nằm ở parent context hay child context?
- Bean scope/lazy có làm thay đổi cách quan sát không?

### Bước 6: Đọc lỗi tạo bean nếu definition có nhưng startup thất bại

Một bean definition có thể đã được đăng ký nhưng constructor hoặc factory method ném exception khi khởi tạo. Lúc đó tìm **BeanCreationException** và chuỗi **Caused by**. Đây không phải trường hợp component scan không tìm thấy class.

### Bước 7: Sửa nguồn đăng ký và xác nhận lại

Sửa package scan, import, property, profile, dependency hoặc factory method theo nguyên nhân được chứng minh. Sau đó chạy lại test/context và xác nhận bean xuất hiện theo đúng tên, kiểu và scope mong muốn.

## 13. Một ví dụ hoàn chỉnh: kiểm tra bean ở nhiều mức

Giả sử:

~~~java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Ta muốn kiểm tra service có được đăng ký và lấy ra được hay không.

Một component chẩn đoán:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class StartupBeanReport {
    private final ApplicationContext context;

    public StartupBeanReport(ApplicationContext context) {
        this.context = context;
    }

    public void printGreetingService() {
        String name = "greetingService";

        System.out.println(
                "containsBean = " + context.containsBean(name)
        );

        String[] names =
                context.getBeanNamesForType(GreetingService.class);

        System.out.println(
                "matching type count = " + names.length
        );

        for (String beanName : names) {
            System.out.println("bean name = " + beanName);
        }
    }
}
~~~

Nếu cần xem BeanDefinition:

~~~java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public void printDefinition(ConfigurableApplicationContext context) {
    ConfigurableListableBeanFactory factory = context.getBeanFactory();

    if (factory.containsBeanDefinition("greetingService")) {
        var definition = factory.getBeanDefinition("greetingService");
        System.out.println(definition.getScope());
        System.out.println(definition.isLazyInit());
        System.out.println(definition.getResourceDescription());
    }
}
~~~

Hai đoạn trên minh họa hai góc nhìn:

- ApplicationContext lookup theo tên và kiểu.
- BeanFactory inspection theo bean definition.

Trong ứng dụng thực tế, không nên log toàn bộ bean registry ở mọi lần khởi động nếu danh sách quá lớn hoặc chứa tên thành phần nội bộ không cần thiết. Hãy giới hạn vào nhóm bean đang cần chẩn đoán.

## 14. Công cụ nào phù hợp với từng mục tiêu?

| Mục tiêu | Cách phù hợp | Điểm cần lưu ý |
|---|---|---|
| Kiểm tra một bean theo tên trong code | **ApplicationContext.containsBean(name)** | Có thể xét parent context; không chứng minh instance đã khởi tạo. |
| Lấy bean theo kiểu | **getBean(type)** | Có thể ném lỗi nếu không có hoặc có nhiều candidate. |
| Liệt kê bean name theo kiểu | **getBeanNamesForType(type)** | Chú ý FactoryBean, lazy và phạm vi context. |
| Xem bean definition | **getBeanDefinitionNames()**, **getBeanDefinition(name)** | Chỉ cho factory hiện tại; definition khác instance. |
| Xem singleton đã được tạo | **containsSingleton(name)**, **getSingletonNames()** | Không bao gồm mọi scope và mọi ancestor. |
| Xem bean đang chạy ở môi trường khác | Actuator **/actuator/beans** | Cần expose và bảo vệ endpoint. |
| Tìm vì sao auto-configuration không match | **--debug**, condition report hoặc **/actuator/conditions** | Không thay thế kiểm tra bean instance. |
| Kiểm tra wiring trong test | **@SpringBootTest** | Khởi tạo context tương đối đầy đủ. |
| Test một auto-configuration nhỏ | **ApplicationContextRunner** | Cần test dependency và cấu hình tương ứng. |
| Quan sát constructor/proxy/lifecycle | IDE debugger | Cần chạy đúng môi trường và đặt breakpoint có mục tiêu. |

Không có một công cụ duy nhất giải quyết mọi câu hỏi. **Chọn công cụ theo điều muốn xác minh** sẽ giúp tránh gọi bean ngoài ý muốn hoặc hiểu sai một danh sách.

## 15. Những ngộ nhận thường gặp

**“Có @Service nghĩa là bean chắc chắn đã được đăng ký.”**  
Không. Class phải được quét hoặc đăng ký bằng một cơ chế phù hợp; profile, condition và phạm vi scan có thể khiến nó không xuất hiện.

**“containsBean trả true nghĩa bean đã khởi tạo thành công.”**  
Không. Nó kiểm tra khả năng tìm bean theo tên; lazy bean hoặc bean cần tạo khi lookup có thể chưa được khởi tạo trước đó.

**“getBeanDefinitionNames là danh sách mọi object trong JVM.”**  
Không. Đây là danh sách bean definitions của factory hiện tại; object tạo bằng new ở nơi khác không tự xuất hiện.

**“Không có trong getSingletonNames nghĩa bean không tồn tại.”**  
Không. Bean có thể là lazy, prototype, thuộc parent context hoặc được cung cấp theo cơ chế khác.

**“Một alias là một bean mới.”**  
Không. Alias là tên bổ sung cho cùng bean identity, không nhất thiết tạo instance khác.

**“Bean có runtime class khác source class nghĩa đăng ký sai.”**  
Không. Có thể reference là AOP proxy hoặc sản phẩm do FactoryBean cung cấp.

**“Condition report có bean nghĩa bean đã tạo thành công.”**  
Không. Condition report mô tả kết quả điều kiện; bean vẫn có thể thất bại ở bước khởi tạo hoặc có condition ở cấp method.

**“Actuator beans endpoint mặc định luôn truy cập được.”**  
Không. Cần có Actuator, endpoint phải được expose và quyền truy cập phải cho phép. Đường dẫn cũng có thể được cấu hình khác.

**“Chỉ cần dùng getBean để kiểm tra, không có tác động phụ.”**  
Không. Lookup có thể kích hoạt khởi tạo bean lazy hoặc factory. Nếu chỉ cần metadata, hãy truy vấn definition phù hợp.

**“Một test tự new service chứng minh component scan hoạt động.”**  
Không. Chỉ test tạo Spring context mới kiểm tra được đăng ký và wiring của container.

## Ghi nhớ cốt lõi

Để xác nhận một bean đã được đăng ký, trước tiên hãy xác định **bạn cần biết definition, tên, kiểu hay instance**. **ApplicationContext** hỗ trợ lookup theo tên/kiểu; **BeanFactory/BeanDefinitionRegistry** giúp xem metadata; **Actuator /beans** cho phép quan sát ứng dụng đang chạy; **condition report** giải thích các quyết định auto-configuration; và **Spring context test** xác nhận wiring trong một cấu hình xác định.

Một bean definition có thể tồn tại trước khi instance được tạo; một bean lazy hoặc prototype có thể không xuất hiện trong singleton registry; một bean từ parent context có thể không nằm trong danh sách definition của child; và một reference có thể là proxy. Hiểu những khác biệt này giúp bạn kiểm tra chính xác, chẩn đoán lỗi thiếu bean và tránh nhầm object tạo bằng new với bean do Spring quản lý.
