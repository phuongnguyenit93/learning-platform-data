# Vì sao điều kiện không nên khởi tạo bean hoặc thực hiện tác vụ có tác dụng phụ?

## 1. Vấn đề: quyết định cấu hình khác với thực thi nghiệp vụ

Trong Spring, một điều kiện gắn qua `@Conditional` giúp framework quyết định **có đăng ký một thành phần/BeanDefinition hay không**. Ở Spring Boot, những cơ chế như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và `@ConditionalOnMissingBean` được xây dựng trên ý tưởng này, để auto-configuration chỉ đóng góp bean khi phù hợp.

Điều kiện không phải nơi để tạo các đối tượng ứng dụng, mở kết nối mạng, gửi thông điệp, cập nhật cơ sở dữ liệu hay chạy tác vụ nền. Lý do không chỉ là “code sạch”; **thời điểm đánh giá điều kiện nằm trong quá trình Spring đang chuẩn bị cấu trúc container, trước khi các bean có vòng đời hoàn chỉnh**.

Giao ước quan trọng được Spring Framework quy định cho interface `Condition`:

> Điều kiện được kiểm tra gần thời điểm bean definition cần đăng ký; một điều kiện có thể phủ quyết việc đăng ký, và phải tuân thủ các hạn chế tương tự `BeanFactoryPostProcessor`, đặc biệt là không tương tác với các bean instance.

Cách phân chia đúng:

~~~text
                 PHASE CẤU HÌNH / ĐĂNG KÝ
  đọc @Configuration, @Bean, @Import, metadata annotation
                            |
                            v
                @Conditional -> matches(...)
                            |
                 +----------+----------+
                 |                     |
               true                  false
                 |                     |
                 v                     v
       Cho phép định nghĩa       Bỏ qua định nghĩa
       bean được đăng ký         bean / cấu hình đó
                 |
                 v
                 PHASE KHỞI TẠO CONTAINER
           dependency injection, BeanPostProcessor,
         @PostConstruct, initMethod, proxy/lifecycle
                 |
                 v
                  BEAN CÓ THỂ HOẠT ĐỘNG
     ApplicationRunner / sự kiện / request / scheduler
~~~

Một condition lý tưởng là **phép kiểm tra dựa trên thông tin đã có**, trả lời câu hỏi “có nên đăng ký?”; công việc thật diễn ra ở nơi quản lý vòng đời, sau khi quyết định đã được đưa ra.

## 2. Giao ước thực tế của `Condition.matches`

Interface trong Spring Framework:

~~~java
package org.springframework.context.annotation;

import org.springframework.core.type.AnnotatedTypeMetadata;

@FunctionalInterface
public interface Condition {
    boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    );
}
~~~

Đây là **chữ ký API rút gọn để học**, không phải file bạn cần tự định nghĩa.

- `context`: cung cấp `Environment`, `BeanDefinitionRegistry`, `BeanFactory` (có thể chưa có trong một số ngữ cảnh), class loader và resource loader.
- `metadata`: thông tin annotation của **class hoặc method đang được đánh giá**; không phải một bean instance.
- `true`: condition này cho phép **tiếp tục** đăng ký, nhưng các condition khác vẫn có quyền phủ quyết; bean instance chưa chắc đã được tạo.
- `false`: thành phần được gắn condition đó không được đăng ký theo lần xử lý cấu hình này.
- Nếu nhiều condition cùng áp dụng, về logic **tất cả phải đạt** (AND). Condition nên độc lập, không dùng thứ tự đánh giá làm kênh truyền dữ liệu.

Ví dụ tốt, chỉ đọc property:

~~~java
package sample.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class EnabledCondition implements Condition {
    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment()
            .getProperty("sample.feature.enabled", Boolean.class, true);
    }
}
~~~

Condition này đọc cấu hình tại thời điểm kiểm tra và trả một `boolean`. Nó không `new` object nghiệp vụ, không yêu cầu bean khác và không tạo tài nguyên ngoài ứng dụng.

**Lưu ý tính đúng của mẫu:** kiểu property `Boolean.class` và default `true` sử dụng cơ chế chuyển đổi của `Environment`. Nếu thuộc tính có giá trị không hợp lệ và không thể chuyển đổi, có thể nhận lỗi cấu hình; không nên giả vờ rằng mọi chuỗi tùy ý đều được diễn giải an toàn thành `false`.

## 3. Nguy cơ thứ nhất: bean chưa sẵn sàng để sử dụng

### Container vẫn đang được xây dựng

Khi Spring xử lý `@Configuration` hoặc đăng ký bean definition, quy trình khởi tạo toàn bộ context chưa nhất thiết hoàn tất. Một số bean vẫn đang ở trạng thái **chưa tạo**, chưa được gắn dependency, chưa qua BeanPostProcessor hoặc chưa chạy callback khởi tạo.

Gọi `getBean(...)` trong `matches(...)` có thể buộc tạo một bean quá sớm:

~~~java
// PHẢN VÍ DỤ — không sử dụng trong condition.
@Override
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    Object remoteClient =
        context.getBeanFactory().getBean("remoteClient");
    return remoteClient != null;
}
~~~

Vấn đề:

1. `getBeanFactory()` không phải lúc nào cũng sẵn có, có thể trả `null`.
2. Bean `remoteClient` có thể chưa có definition; gọi `getBean` ném exception.
3. Nếu đã có definition, `getBean` có thể kích hoạt **khởi tạo instance** trong khi container chưa hoàn tất chuẩn bị.
4. Instance ấy có thể chưa hưởng đầy đủ hậu xử lý, proxy và cấu hình mà ứng dụng mong đợi.
5. Điều kiện có thể tạo vòng phụ thuộc: để quyết định bean A, nó đòi tạo B; trong khi B lại phụ thuộc A hoặc một phần cấu hình đang bị điều kiện chặn.

Ngay cả khi đoạn code thỉnh thoảng chạy “ổn”, nó vẫn vi phạm ý nghĩa của condition và có thể thất bại khi thay thứ tự xử lý, thêm auto-configuration hoặc thay phiên bản Spring.

### Không nhầm `BeanDefinition` với bean instance

| Đối tượng / thao tác | Ý nghĩa | Có phù hợp ở condition? |
| --- | --- | --- |
| `AnnotatedTypeMetadata` | Metadata annotation của class/method | Có |
| `Environment#getProperty(...)` | Giá trị cấu hình hiện có | Thường có |
| `ClassLoader` / `ResourceLoader` | Thông tin classpath/resource | Có, nếu tra cứu nhẹ, không tạo tác dụng phụ |
| `BeanDefinitionRegistry` | Metadata các definitions đã đăng ký đến thời điểm này | Có thể, với hiểu biết giai đoạn/thứ tự |
| `BeanFactory#getBean(...)` | Có thể tạo và trả bean **instance** | **Không** |
| `ApplicationContext#getBean(...)` | Lấy instance; có thể kích hoạt tạo bean | **Không** |
| Tự gọi `new SomeService(...)` | Tạo object ngoài container | **Không**, nếu là object nghiệp vụ/tài nguyên |

**Kết luận:** nếu mục đích là xem bean *đã được đăng ký dưới dạng definition* chưa, hãy dùng điều kiện Spring Boot chuyên biệt như `@ConditionalOnBean`/`@ConditionalOnMissingBean` khi phù hợp. Đừng gọi bean instance để “kiểm tra sự tồn tại”.

## 4. Nguy cơ thứ hai: khởi tạo sớm làm sai vòng đời

Giả sử một bean cần các bước:

~~~text
Khởi tạo object
 -> inject dependencies/configuration properties
 -> BeanPostProcessor trước initialize
 -> @PostConstruct / InitializingBean / initMethod
 -> BeanPostProcessor sau initialize
 -> AOP proxy nếu áp dụng
 -> dùng trong ứng dụng
~~~

Nếu condition buộc tạo bean ngay trong giai đoạn quyết định configuration, một số bước thiết lập quan trọng có thể chưa hoàn tất hoặc bị can thiệp không đúng thời điểm. Hậu quả tùy trường hợp:

- Giá trị từ `@ConfigurationProperties`/binding chưa được áp dụng như dự kiến.
- Proxy `@Transactional`, cache, security hoặc AOP chưa được tạo hoặc chưa gắn đúng cách.
- Bean được dùng khi collaborator chưa sẵn sàng.
- `BeanFactoryPostProcessor`, `BeanPostProcessor` hoặc cấu hình khác chưa hoàn thành công việc liên quan.
- Có thể xuất hiện thông điệp về bean “not eligible for getting processed by all BeanPostProcessors”, hoặc lỗi vòng phụ thuộc khó lần theo.

**Không khẳng định mọi lần gọi `getBean` sớm sẽ luôn thiếu proxy hay binding**; đây là các **rủi ro có thật tùy thời điểm**. Điểm sai căn bản là condition đã chủ động kéo khởi tạo bean ra ngoài tiến trình vòng đời bình thường.

### Cảnh báo liên quan trong Spring Boot: SpEL gọi bean

Một ví dụ dễ bị bỏ sót là điều kiện biểu thức tham chiếu bean:

~~~java
// PHẢN VÍ DỤ về ý định thiết kế.
// @ConditionalOnExpression("@remoteProbe.check()")
~~~

Tài liệu Spring Boot cảnh báo rằng tham chiếu bean trong SpEL của `@ConditionalOnExpression` có thể khiến bean được khởi tạo rất sớm, dẫn đến không đủ điều kiện được hậu xử lý (ví dụ binding configuration properties) và trạng thái chưa hoàn chỉnh. Vì vậy **không dùng việc gọi method bean trong SpEL để thay cho điều kiện metadata**. Nếu chỉ cần property, dùng `@ConditionalOnProperty` thay thế.

## 5. Nguy cơ thứ ba: tác vụ có tác dụng phụ không có giao ước chạy đúng một lần

**Tác dụng phụ (side effect)** là hành vi quan sát được ngoài kết quả `boolean`: ghi file, gửi HTTP request, thay dữ liệu trong database, publish message, thay biến static, đăng ký task, mở socket, tiêu thụ một message khỏi queue, v.v.

Một condition sai về ý tưởng:

~~~java
// PHẢN VÍ DỤ — không dùng trong ứng dụng.
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    chargeCreditCard();
    return true;
}
~~~

*Đây là pseudocode: `chargeCreditCard()` không được khai báo; chỉ nhằm chỉ ra điều cấm làm.*

Vì sao sai?

- Spring gọi `matches` khi xử lý cấu hình, **không cung cấp giao ước rằng method luôn chỉ được gọi đúng một lần**.
- Nhiều cấu hình hoặc lượt xây context khác nhau có thể dẫn đến nhiều lần kiểm tra.
- Dữ liệu có thể đổi giữa những lần gọi; side effect khiến condition không còn là một phép kiểm tra có thể dự đoán.
- Nếu cuối cùng bean bị chặn bởi một condition khác, một side effect của condition trước đó có thể **đã xảy ra**.
- Khởi động thất bại sau khi condition chạy không tự rollback các thay đổi file, request, email hoặc transaction ở hệ thống ngoài.
- Trong test suite, mỗi test context hoặc mỗi lần thử cấu hình có thể gọi lại condition, gây hành động lặp ngoài ý muốn.

Ví dụ đặc biệt nguy hiểm:

~~~java
// PHẢN VÍ DỤ — không dùng trong condition.
static int checks = 0;

public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    checks++;
    return checks == 1;
}
~~~

Lần gọi đầu `true`, lần sau `false`; cùng cấu hình đầu vào nhưng kết quả thay đổi theo số lần framework gọi. Đây là dạng code dựa trên **trạng thái ẩn và thứ tự chạy**, rất dễ tạo lỗi khó tái hiện.

Một lệnh log để hỗ trợ chẩn đoán là side effect nhẹ; có thể cân nhắc nếu thực sự cần, nhưng **logic đúng không được dựa vào số dòng log hoặc thứ tự log**, và tránh ghi log chứa bí mật hoặc gọi I/O nặng trong condition.

## 6. Nguy cơ thứ tư: kết quả điều kiện không ổn định

Condition nên cho kết quả **ổn định theo dữ liệu cấu hình được cung cấp cho lần xử lý đó**. Không nên hỏi trạng thái bên ngoài có thể thay đổi từng mili-giây, nhất là thực hiện kiểm tra mạng:

~~~java
// PHẢN VÍ DỤ — tạo kết quả phụ thuộc mạng.
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    return pingProductionDatabase(); // Không triển khai tại đây.
}
~~~

Lý do nên tránh:

1. **Mạng chưa chắc sẵn sàng lúc startup.** Một lỗi kết nối tạm thời có thể khiến bean bị loại, mặc dù ứng dụng đáng ra cần khởi động rồi đợi dependency phục hồi.
2. **Chậm khởi động** khi request timeout hoặc DNS lỗi.
3. **Không phân biệt lỗi cấu hình với lỗi availability.** Một service không đáp ứng tại giây khởi động không có nghĩa bean definition không nên tồn tại.
4. **Điều kiện có thể được đánh giá ở các giai đoạn/context khác nhau**; kết quả bất nhất khiến hệ thống khó dự đoán.
5. **Không có refresh tự động:** sau khi condition trả false và bean bị bỏ qua, khi dịch vụ bên ngoài trở lại, Spring không tự đăng ký bean trở lại chỉ vì sự cố mạng đã hết.

Nếu thật sự muốn feature chỉ được tạo khi có property, hãy đánh giá **property**. Nếu phải theo dõi kết nối dịch vụ, tạo bean ở cấu hình ổn định rồi dùng health check, retry, circuit breaker hoặc cơ chế lifecycle phù hợp.

### Phân biệt metadata và trạng thái hoạt động

- **Metadata phù hợp condition:** “dependency JAR có class này không?”, “property bật không?”, “profile nào đang active?”, “resource cấu hình có hiện diện không?”.
- **Trạng thái runtime nên nằm nơi khác:** “database đang nhận kết nối không?”, “một job đã gửi email chưa?”, “API có trả 200 tại thời điểm này không?”, “đã tiêu thụ bao nhiêu event?”.

Không phải mọi I/O đọc đều bị cấm tuyệt đối về mặt cú pháp API, nhưng **I/O có độ trễ, lỗi, trạng thái biến thiên hoặc tác dụng phụ** là thiết kế xấu cho quyết định đăng ký definitions.

## 7. Nguy cơ thứ năm: thứ tự đăng ký và phụ thuộc vòng

Bean definitions được xử lý dần khi Spring phân tích cấu hình. Một condition đọc registry chỉ thấy **trạng thái đã được xử lý tại thời điểm kiểm tra**, không nhất thiết toàn bộ tập bean definitions cuối cùng.

Ví dụ một custom condition làm điều sau:

~~~java
// VẪN CẦN RẤT THẬN TRỌNG:
boolean present =
    context.getRegistry().containsBeanDefinition("mailClient");
return present;
~~~

Câu lệnh trên kiểm tra **definition** chứ không khởi tạo instance, nên không vi phạm cùng một lỗi như `getBean`. Nhưng kết quả có thể phụ thuộc thứ tự: bean `mailClient` chưa được đăng ký khi condition chạy, mặc dù có thể sẽ được đăng ký bởi class được xử lý sau đó.

Với Spring Boot, `@ConditionalOnBean` và `@ConditionalOnMissingBean` có semantics đã được framework định nghĩa. Tài liệu Boot khuyến nghị dùng chúng chủ yếu ở auto-configuration, vì các auto-configuration được xử lý sau những bean definitions người dùng. Tuy nhiên, ngay cả các điều kiện này cũng dựa trên những definitions **đã được xử lý đến thời điểm đánh giá**; thứ tự giữa các auto-configuration vẫn quan trọng.

**Không khắc phục vấn đề thiếu definition bằng cách gọi `getBean`**, vì phương thức này đi xa hơn: nó có thể tạo cả object khi container chưa sẵn sàng. Thay vào đó, sửa tầng cấu hình, khai báo quan hệ thứ tự auto-configuration khi thích hợp, hoặc dùng annotation Boot có semantics phù hợp.

## 8. Quy tắc thiết kế: một condition tốt có đặc điểm nào?

Để giữ condition dễ kiểm thử và bảo trì:

1. **Chỉ đọc dữ liệu cần thiết.** Ưu tiên `Environment`, metadata annotation, classpath/resource metadata hoặc các definitions đang có theo API phù hợp.
2. **Không tạo instance nghiệp vụ.** Không gọi `getBean`, `new` service/database client chỉ để quyết định đăng ký.
3. **Không thay đổi trạng thái.** Tránh ghi file, publish event, gọi endpoint thay đổi dữ liệu, tăng counter nghiệp vụ, đặt lịch task.
4. **Không phụ thuộc số lần gọi.** `matches` có thể được Spring kiểm tra trong các hoàn cảnh khác nhau.
5. **Không dựa vào thứ tự mơ hồ.** Condition đọc trạng thái registry cần hiểu giai đoạn và các definitions đã xử lý.
6. **Chạy nhanh và đáng tin cậy.** Tránh mạng, database, I/O chậm và timeout.
7. **Dễ suy luận.** Cùng cấu hình và metadata thích hợp cho cùng kết quả logic.
8. **Dùng điều kiện dựng sẵn khi có.** Trong Boot, `@ConditionalOnProperty`/`@ConditionalOnClass`/`@ConditionalOnMissingBean` thường an toàn, dễ đọc hơn condition tự viết.

Không đồng nhất **pure condition** với “không được sử dụng bất kỳ API nào”. Một phép tra cứu property trong `Environment` hợp lệ; nguy cơ nằm ở **khởi tạo sai vòng đời, tác dụng phụ, trạng thái biến thiên và giả định quá sớm về container**.

## 9. Ví dụ chạy được: condition thuần túy, khởi tạo bean đúng lúc

Phần này là một ứng dụng console Spring Boot **3.3.13 + Java 17 + Maven 3.9+**, không cần HTTP server. Ví dụ cố ý dùng `@Lazy` để tách hai thời điểm:

- **Đăng ký bean definition**: do `@Conditional` quyết định.
- **Tạo bean instance**: chỉ khi chương trình yêu cầu bean bằng `getBeanProvider(...).getIfAvailable()`.

Ta dùng biến đếm trong **constructor của bean** để quan sát thời điểm khởi tạo. Đây là công cụ minh họa trong ứng dụng, **không đặt biến đếm hoặc tăng biến trong `Condition.matches`**.

### 9.1. Cây thư mục

~~~text
safe-condition-demo/
├── pom.xml
└── src/main/java/example/
    ├── app/
    │   └── DemoApplication.java
    ├── config/
    │   └── FeatureConfiguration.java
    ├── condition/
    │   └── FeatureEnabledCondition.java
    └── service/
        └── CountedService.java
~~~

Các package ở `example.config`/`example.condition`/`example.service` nằm **ngoài** component scan mặc định từ `example.app`. Ta dùng `@Import(FeatureConfiguration.class)` để biết chắc class cấu hình được xử lý mà không cần mở rộng scan không liên quan.

### 9.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>safe-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. `src/main/java/example/condition/FeatureEnabledCondition.java`

~~~java
package example.condition;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment().getProperty(
            "demo.feature.enabled", Boolean.class, true
        );
    }
}
~~~

Đây là toàn bộ condition: một phép đọc property rồi trả kết quả. Không có `getBean`, không có JDBC/HTTP và không có biến mutable.

### 9.4. `src/main/java/example/service/CountedService.java`

~~~java
package example.service;

import java.util.concurrent.atomic.AtomicInteger;

public final class CountedService {
    private static final AtomicInteger CREATED =
        new AtomicInteger();

    public CountedService() {
        CREATED.incrementAndGet();
    }

    public static int createdCount() {
        return CREATED.get();
    }

    public String value() {
        return "ready";
    }
}
~~~

Đây là bean Java thông thường. `CREATED` chỉ để minh họa **constructor đã chạy bao nhiêu lần trong cùng một JVM**. Các lệnh `java -jar` dưới đây là tiến trình độc lập, nên mỗi lần chạy bắt đầu với counter bằng 0. Không dùng pattern đếm này để thiết kế condition thật.

### 9.5. `src/main/java/example/config/FeatureConfiguration.java`

~~~java
package example.config;

import example.condition.FeatureEnabledCondition;
import example.service.CountedService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @Lazy
    @Conditional(FeatureEnabledCondition.class)
    public CountedService countedService() {
        return new CountedService();
    }
}
~~~

- `@Conditional` quyết định có đăng ký definition `countedService` hay không.
- `@Lazy` yêu cầu bean singleton này chưa được khởi tạo chỉ vì container startup, miễn không có thành phần khác buộc phải sử dụng nó.
- Factory method mới gọi `new CountedService()` **sau khi bean được yêu cầu**; nó không nằm bên trong condition.
- `proxyBeanMethods=false` phù hợp vì cấu hình không gọi chéo các factory methods.

### 9.6. `src/main/java/example/app/DemoApplication.java`

~~~java
package example.app;

import example.config.FeatureConfiguration;
import example.service.CountedService;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "example.app")
@Import(FeatureConfiguration.class)
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(DemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            boolean definition = context.getBeanFactory()
                .containsBeanDefinition("countedService");

            int beforeLookup = CountedService.createdCount();

            CountedService service =
                context.getBeanProvider(CountedService.class)
                    .getIfAvailable();

            System.out.println("definition=" + definition);
            System.out.println("constructedBeforeLookup=" + beforeLookup);
            System.out.println("service=" +
                (service == null ? "none" : service.value()));
            System.out.println("constructedAfterLookup=" +
                CountedService.createdCount());
        }
    }
}
~~~

`WebApplicationType.NONE` giữ ví dụ ở chế độ console, không khởi động embedded HTTP server. `containsBeanDefinition` kiểm tra **định nghĩa**, không lấy instance. Chỉ `getIfAvailable()` mới có thể yêu cầu container tạo `CountedService`.

### 9.7. Chạy và đối chiếu output

Trong thư mục `safe-condition-demo`:

~~~bash
java -version
mvn -version
mvn -q clean package
java -jar target/safe-condition-demo-1.0.0.jar
~~~

Bốn dòng từ các câu `System.out.println` của chương trình:

~~~text
definition=true
constructedBeforeLookup=0
service=ready
constructedAfterLookup=1
~~~

Giải thích:

1. `matches` được đánh giá dựa trên property mặc định `true`.
2. `BeanDefinition` của `countedService` tồn tại.
3. Do bean là `@Lazy`, constructor chưa chạy tại thời điểm đo `beforeLookup`.
4. `getIfAvailable()` yêu cầu bean, Spring khởi tạo một instance.
5. Counter tăng lên 1; condition **không phải thủ phạm gây tạo instance**.

Tắt bằng property:

~~~bash
java -jar target/safe-condition-demo-1.0.0.jar --demo.feature.enabled=false
~~~

Bốn dòng do chương trình in:

~~~text
definition=false
constructedBeforeLookup=0
service=none
constructedAfterLookup=0
~~~

Bởi điều kiện không đạt, Spring không đăng ký bean definition `countedService`. Provider trả `null` và không có instance được tạo.

Bật tường minh:

~~~bash
java -jar target/safe-condition-demo-1.0.0.jar --demo.feature.enabled=true
~~~

Kết quả trở lại giống lần chạy mặc định.

**Giới hạn của bằng chứng:** counter dùng trong ví dụ này không đo số lần `matches` được gọi. Bài toán yêu cầu condition không có side effect, nên không cài counter vào `matches` chỉ để đếm lượt đánh giá.

### Bảng phân biệt hai thời điểm

| Tình huống | Bean definition sau startup | Instance trước lookup | Instance sau lookup |
| --- | --- | --- | --- |
| Thiếu property (mặc định bật) | Có | 0 | 1 |
| `demo.feature.enabled=true` | Có | 0 | 1 |
| `demo.feature.enabled=false` | Không | 0 | 0 |

Không nên suy từ `definition=true` rằng instance đã tồn tại: `@Lazy` là phản ví dụ trực quan. Và không nên suy rằng mọi điều kiện chỉ chạy một lần vì ví dụ tạo đúng một instance; đó là **hai hợp đồng khác nhau**.

## 10. Các thay đổi nhỏ để thấy rõ hành vi

### Thử A: bỏ `@Lazy`

Trong `FeatureConfiguration`, xóa `@Lazy` và import của annotation đó, build lại:

~~~bash
mvn -q clean package
java -jar target/safe-condition-demo-1.0.0.jar
~~~

Khi các điều kiện đều đạt, bean singleton mặc định thường được khởi tạo trong khi refresh context. Dự kiến:

~~~text
definition=true
constructedBeforeLookup=1
service=ready
constructedAfterLookup=1
~~~

Điểm quan trọng: **constructor chạy sớm hơn do scope/lazy policy**, không phải do `matches` được phép tự tạo bean.

### Thử B: thêm condition ở cấp class

Di chuyển `@Conditional(FeatureEnabledCondition.class)` từ method lên `FeatureConfiguration`. Khi property=false, cả cấu hình bị bỏ qua. Nếu cấu hình còn các `@Bean`/`@Import` khác, chúng cũng chịu ảnh hưởng của condition trên class.

Nếu chỉ muốn tắt đúng `CountedService`, giữ điều kiện trên method. Phạm vi condition và thời điểm bean tạo là hai chiều độc lập.

### Thử C: cố tình inject service vào bean khác

Thêm một singleton eager bean phụ thuộc `CountedService` (chỉ khi điều kiện bật). Khi nó được Spring tạo lúc startup, dependency có thể khiến `CountedService` bị khởi tạo sớm **dù nó có `@Lazy` trên factory method**. Vì vậy `@Lazy` không phải cam kết “không bao giờ khởi tạo trước lookup của main”; một dependency eager có thể yêu cầu bean.

Bài thực hành này giúp phân biệt **hành vi hợp lệ do container giải quyết dependency** với **hành vi sai khi condition tự gọi getBean**.

### Thử D: chuyển condition sang annotation dựng sẵn của Boot

Thay:

~~~java
@Conditional(FeatureEnabledCondition.class)
~~~

bằng:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Nhớ import `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty`. Với ba tình huống true/false/thiếu property, kết quả tương đương ví dụ chính. Tuy nhiên, hãy nhớ điều kiện Boot có quy tắc chuyển đổi giá trị riêng; không đồng nhất implementation với `Environment#getProperty(..., Boolean.class, true)` trong mọi chuỗi đầu vào có thể có.

Ưu điểm là ít code tự viết, semantics được chuẩn hóa và có hỗ trợ báo cáo điều kiện của Boot.

## 11. Side effect nên đặt ở đâu nếu ứng dụng thực sự cần làm việc?

### Khởi tạo tài nguyên: đặt trong bean và vòng đời

Nếu cần tạo một client hay kết nối, bean factory method, constructor hoặc hook khởi tạo phù hợp là nơi thực hiện. Nên cân nhắc thời điểm kết nối, retry và đóng tài nguyên; **không đặt các bước đó vào `matches`**.

Ví dụ cấu hình service có property:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "client",
        name = "enabled",
        havingValue = "true"
    )
    ExternalClient externalClient(ClientProperties properties) {
        return new ExternalClient(properties.url());
    }
}
~~~

*Đây là đoạn minh họa, cần có class `ExternalClient`, `ClientProperties` và import tương ứng; không phải file độc lập.* Condition chỉ quyết định có đăng ký bean; công việc xây client thực hiện trong factory method do Spring quản lý.

### Tác vụ sau khi application đã sẵn sàng: `ApplicationRunner`

Khi ứng dụng cần chạy một tác vụ sau startup, có thể khai báo `ApplicationRunner`:

~~~java
@Bean
ApplicationRunner warmupRunner(CacheWarmer warmer) {
    return args -> warmer.preload();
}
~~~

*Đây là một method minh họa, cần class `CacheWarmer`/import, không phải chương trình đầy đủ.* Spring Boot chạy runner sau khi context đã refresh, vào giai đoạn sẵn sàng thực hiện tác vụ ứng dụng. Thao tác có tác dụng phụ nằm trong body của runner, **không trong condition**.

Với task có yêu cầu thực thi đúng một lần trong hệ thống phân tán, `ApplicationRunner` tự nó **không bảo đảm exactly-once toàn hệ thống**: mỗi instance khi khởi động có thể chạy. Hãy dùng idempotency, transactional outbox, job lock hoặc cơ chế điều phối tương ứng.

### Kiểm tra tình trạng hệ thống: health indicator / readiness / retry

Nếu feature cần một hệ thống ngoài đang hoạt động:

- Dùng feature flag/property ổn định để quyết định bean definition.
- Để bean sở hữu kết nối và chính sách retry/circuit breaker.
- Dùng health/readiness để báo trạng thái có thể phục vụ.
- Nếu chưa sẵn sàng, trả lỗi trạng thái thích hợp hoặc trì hoãn thực thi ở tầng nghiệp vụ.

Đừng biến **“dịch vụ ngoài đang down đúng một lần kiểm tra”** thành quyết định vĩnh viễn không đăng ký bean trong một context đã khởi động.

### Công việc theo lịch: đăng ký bằng lifecycle/scheduler

Nếu cần schedule, hãy để Spring tạo scheduler/task với cấu hình hợp lệ, sau đó quản lý chạy/dừng theo lifecycle. Điều kiện có thể quyết định bean scheduler **có được đăng ký**; nó không nên tự tạo thread hoặc đăng ký cron job mỗi khi `matches` được gọi.

## 12. Vì sao viết condition “đọc bean” dễ gây vòng phụ thuộc?

Xét mô hình:

~~~text
Để đăng ký bean A:
    ConditionForA.matches(...)
         |
         +-- gọi getBean("B")
               |
               +-- tạo B -> cần A
                    |
                    +-- A chưa có BeanDefinition
                         vì ConditionForA chưa trả kết quả
~~~

Đây là vòng phụ thuộc ngay ở **cấp quyết định đăng ký**, không đơn thuần là constructor cycle của hai singleton có sẵn definitions. Có thể nhận `NoSuchBeanDefinitionException`, lỗi phụ thuộc vòng, hoặc khởi tạo sai thứ tự; loại exception thực tế phụ thuộc cách code và cấu hình.

Thiết kế đúng là điều kiện chỉ đọc **metadata** đủ để xác định có nên đăng ký A, còn B được injection sau khi A đã có definition. Nếu điều kiện thực sự cần kiểm tra bean type, hãy dùng `@ConditionalOnBean`/`@ConditionalOnMissingBean` phù hợp trong Boot; các điều kiện ấy được thiết kế để xem metadata definitions theo giai đoạn.

### Không sửa bằng `@DependsOn` một cách tùy tiện

`@DependsOn` điều khiển thứ tự **khởi tạo** của các bean đã được định nghĩa; nó không biến một condition vốn gọi `getBean` thành hợp lệ. Cần sửa logic registration trước, không chỉ cố ép thứ tự bean instance.

## 13. Điều kiện ở class, method và giai đoạn xử lý

Một condition áp dụng ở **lớp `@Configuration`** có thể khiến Spring bỏ cả lớp cấu hình và những method/import/scan liên quan. Điều kiện ở **phương thức `@Bean`** nhắm tới definition của method đó.

Đối với condition cần kiểm soát phase, Spring Framework có interface `ConfigurationCondition` (mở rộng `Condition`) với:

~~~java
ConfigurationPhase getConfigurationPhase();
~~~

Hai phase được phân biệt là `PARSE_CONFIGURATION` và `REGISTER_BEAN`. Đây là lý do một condition cần metadata hoặc bean definitions phải hiểu mình chạy **ở giai đoạn nào**.

Tuy nhiên, `ConfigurationCondition` không hợp thức hóa việc lấy bean instances. Dù chạy ở `REGISTER_BEAN`, hợp đồng không tương tác với bean instances vẫn có hiệu lực. Nó chỉ giúp chỉ định thời điểm đánh giá điều kiện cấu hình, không đảm bảo mọi bean đã được khởi tạo.

## 14. Những sai lầm thường gặp và hệ quả

| Sai lầm | Vì sao nguy hiểm | Giải pháp |
| --- | --- | --- |
| `context.getBeanFactory().getBean(...)` trong `matches` | Có thể khởi tạo instance khi context chưa sẵn sàng | Đọc metadata/registry hoặc dùng condition Boot chuyên biệt |
| `new DatabaseClient()` rồi kết nối ngay trong condition | I/O, timeout, thiếu lifecycle/disposal | Xây client dưới `@Bean` và quản lý khởi tạo/đóng |
| HTTP request đến service ngoài để quyết định condition | Trạng thái tạm thời làm cấu hình sai hoặc startup chậm | Feature flag + health/retry ở runtime |
| Gửi email hoặc publish event trong condition | Có thể xảy ra dù bean bị chặn, không bảo đảm đúng một lần | Runner/event/lifecycle, kèm idempotency |
| Ghi file/cache/DB trong condition | Side effect không được rollback khi startup fail | Dời vào tác vụ có transaction hoặc API ứng dụng |
| Đếm lần gọi để điều khiển `matches` | Không có bảo đảm condition chỉ chạy một lần | Kiểm tra dữ liệu ổn định, không dựa counter |
| Truy vấn bean definitions chưa được xử lý | Kết quả phụ thuộc thứ tự cấu hình | Hiểu phase; dùng `@ConditionalOnBean`/`OnMissingBean` đúng ngữ cảnh |
| Dùng SpEL tham chiếu bean trong `@ConditionalOnExpression` | Có nguy cơ khởi tạo bean sớm | `@ConditionalOnProperty`/`@ConditionalOnClass` khi thích hợp |
| Dùng condition để bật/tắt ngay runtime | Conditions thường không tự đánh giá lại khi property đổi | Config runtime, refresh có kiểm soát hoặc logic nghiệp vụ |
| Throw/nuốt exception bất thường không nhất quán | Startup lỗi khó đọc hoặc lỗi cấu hình bị che giấu | Điều kiện đơn giản, validate configuration rõ ràng |

## 15. Cách kiểm thử condition an toàn

### Kiểm tra kết quả đăng ký, không đo số lượt gọi

Trong một ứng dụng demo, thực hiện các lần chạy độc lập với property khác nhau và kiểm tra:

1. Có hay không có `BeanDefinition` tương ứng.
2. Bean instance có được tạo khi container yêu cầu không.
3. Side effects mong đợi của code nghiệp vụ chỉ xuất hiện trong lifecycle phù hợp.
4. Thời gian khởi động và log không có dấu hiệu timeout hoặc khởi tạo resource sớm.

Không đưa counter vào `matches` rồi cố assert rằng nó đúng một lần. Đây không phải hợp đồng Spring bảo đảm và làm test giòn.

### Với Spring Boot: `ApplicationContextRunner`

Spring Boot test cung cấp `ApplicationContextRunner` để tạo các context riêng với properties và user configurations khác nhau, đặc biệt phù hợp cho auto-configuration. Ví dụ ý tưởng:

~~~java
// ĐOẠN MINH HỌA TEST: cần dependency spring-boot-test
// và assertion library, không phải chương trình độc lập.
new ApplicationContextRunner()
    .withUserConfiguration(FeatureConfiguration.class)
    .withPropertyValues("demo.feature.enabled=false")
    .run(context -> {
        assertThat(context).doesNotHaveBean(CountedService.class);
    });
~~~

*Đoạn này cần imports và AssertJ trong project test; không phải code để dán vào `main`.* Test nên xác nhận **bean có/không**, thay vì giả định condition chạy số lần cụ thể. Một auto-configuration thật còn có thể được kiểm thử theo từng cặp điều kiện classpath/property/bean người dùng để phát hiện lỗi thứ tự.

### Đọc Condition Evaluation Report đúng phạm vi

Spring Boot cung cấp Condition Evaluation Report (có thể xem bằng `--debug`) để giải thích nhiều điều kiện Spring Boot và lý do match/no match. Tuy nhiên, một custom `Condition` thuần chỉ triển khai interface Framework **không nhất thiết được báo cáo theo cách các `SpringBootCondition` xây dựng `ConditionOutcome`**. Khi quan sát, dùng cả context và report; không suy rằng condition không chạy chỉ vì nó không có dòng riêng trong report.

### Lỗi thường xuất hiện trước `main` quan sát

Nếu condition sai gọi `getBean` và ném exception khi refresh context, `SpringApplication.run(...)` có thể thất bại **trước khi mã sau `run` được thực thi**. Khi ấy không có output kiểm tra bean mong đợi. Hãy đọc stack trace gốc, tránh quy lỗi cho `System.out.println` hoặc provider lookup.

## 16. Bài tập tự kiểm tra

1. **Giao ước:** Vì sao `matches=true` không có nghĩa bean singleton instance đã khởi tạo? Dùng khái niệm `BeanDefinition` và `@Lazy` để giải thích.
2. **Phân tích phản ví dụ:** Khi condition gọi `getBean("remoteClient")`, ít nhất bốn rủi ro nào có thể xảy ra? Rủi ro nào thuộc vòng đời, rủi ro nào thuộc thứ tự đăng ký?
3. **Đúng thời điểm:** Nếu cần gửi một thông điệp sau startup, bạn chọn `ApplicationRunner` hay `Condition.matches`? Còn yêu cầu exactly-once trên nhiều instance thì cần thêm điều gì?
4. **Dịch vụ ngoài bị down:** Vì sao việc ping endpoint trong condition có thể biến lỗi mạng tạm thời thành cấu hình thiếu bean? Nên chuyển phép kiểm tra sang tầng nào?
5. **Mã chạy được:** Chạy project mục 9 khi thiếu property, khi true và khi false. Giải thích bốn dòng output, nhất là tại sao `constructedBeforeLookup=0` nhưng `definition=true`.
6. **Thử eager:** Bỏ `@Lazy`, rebuild và dự đoán thay đổi counter. Có phải condition tự tạo instance không?
7. **Thử dependency:** Thêm bean singleton eager phụ thuộc `CountedService`. Tại sao `@Lazy` không còn bảo đảm constructor chưa chạy trước `main`?
8. **Thứ tự:** Phân biệt `context.getRegistry().containsBeanDefinition("x")` với `context.getBeanFactory().getBean("x")`. Phép nào có thể khiến instance bị tạo?
9. **Auto-configuration:** Vì sao `@ConditionalOnMissingBean` vẫn phải xét thứ tự đăng ký definitions? Boot khuyên đặt điều kiện này chủ yếu ở đâu?
10. **SpEL:** Vì sao `@ConditionalOnExpression("@bean.check()")` có thể nguy hiểm hơn `@ConditionalOnProperty` khi khởi động?
11. **Kiểm thử:** Vì sao assert số lần gọi `matches` là một thiết kế test kém bền vững? Nên assert trạng thái nào của context?
12. **Phạm vi:** Tại sao `ConfigurationCondition.REGISTER_BEAN` không đồng nghĩa với “tất cả bean instances đã sẵn sàng”?

**Tiêu chí hoàn thành:** bạn có thể giải thích chính xác thời điểm và vai trò của `Condition.matches`, chỉ ra nguy cơ khởi tạo bean sớm và tác dụng phụ, viết condition chỉ đọc metadata/property, kiểm chứng sự khác nhau giữa đăng ký definition và tạo instance, và đặt tác vụ nghiệp vụ vào lifecycle phù hợp.

## 17. Tài liệu chính thức

- [Spring Framework 6.1 — `Condition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html)
- [Spring Framework 6.1 — `ConditionContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html)
- [Spring Framework 6.1 — `ConfigurationCondition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Application Startup / SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
