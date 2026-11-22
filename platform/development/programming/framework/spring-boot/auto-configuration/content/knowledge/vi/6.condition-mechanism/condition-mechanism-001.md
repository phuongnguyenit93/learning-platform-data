# @Conditional và giao ước Condition.matches trong Spring

## 1. Tại sao Spring cần đăng ký bean có điều kiện?

Một ứng dụng thường phải thay đổi cấu hình theo môi trường. Ví dụ: chỉ đăng ký bộ gửi thông báo nếu một tính năng được bật, chỉ tạo bean mặc định khi người dùng chưa định nghĩa bean riêng, hoặc chỉ nạp lớp cấu hình khi thư viện tương ứng có mặt. Spring thực hiện những quyết định này thông qua **điều kiện tại thời điểm xử lý cấu hình**.

Hai thành phần cốt lõi của Spring Framework là:

- `@Conditional` (`org.springframework.context.annotation.Conditional`): annotation gắn với lớp cấu hình, lớp component hoặc phương thức `@Bean` để khai báo điều kiện phải thỏa mãn.
- `Condition` (`org.springframework.context.annotation.Condition`): interface có phương thức duy nhất `matches(ConditionContext, AnnotatedTypeMetadata)` trả về `boolean`.

**Giao ước quan trọng nhất:** một thành phần chỉ *đủ điều kiện để được đăng ký* khi mọi `Condition` áp dụng cho nó đều trả về `true`. Một điều kiện trả `false` sẽ phủ quyết việc đăng ký thành phần đó.

~~~text
Spring phân tích metadata cấu hình
            |
            v
Thấy @Conditional(MyCondition.class)
            |
            v
Khởi tạo và gọi MyCondition.matches(context, metadata)
            |
       +----+----+
       |         |
      true      false
       |         |
       v         v
Tiếp tục xem xét  Bỏ qua registration
BeanDefinition    của thành phần
       |
       v
Spring có thể tạo bean theo scope/lifecycle
~~~

Đây là **cổng đăng ký bean definition**, không phải lệnh `if` chạy mỗi khi business method được gọi. `true` cũng không bảo đảm một bean instance đã tồn tại ngay tức thì: sau khi điều kiện đạt, bean còn phụ thuộc định nghĩa hợp lệ, dependency, scope, lazy initialization và tiến trình khởi tạo context.

### Liên hệ với Spring Boot auto-configuration

Spring Boot xây các annotation quen thuộc như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và `@ConditionalOnMissingBean` trên nền tảng điều kiện của Spring. Nhờ đó, một lớp `@AutoConfiguration` có thể là **ứng viên** nhưng chỉ đăng ký một số bean khi điều kiện thực tế khớp.

Không đồng nhất ba bước:

1. **Phát hiện ứng viên:** Boot tìm lớp tự cấu hình từ `AutoConfiguration.imports`.
2. **Đánh giá điều kiện:** `@Conditional` hoặc các điều kiện Boot quyết định lớp/phương thức có được xử lý không.
3. **Tạo và sử dụng bean:** container đăng ký `BeanDefinition`, giải quyết dependency và tạo instance theo scope/lifecycle.

Bài này đi sâu vào **bước 2**, đặc biệt là hợp đồng của `Condition.matches`; ví dụ Spring Boot chỉ là môi trường để quan sát cơ chế Spring Framework.

## 2. Cú pháp `@Conditional` và ý nghĩa AND

Dạng thường gặp:

~~~java
@Conditional(MyCondition.class)
class MyConfiguration {
}
~~~

Bạn cũng có thể khai báo nhiều condition cùng lúc:

~~~java
@Conditional({ConditionA.class, ConditionB.class})
class MyConfiguration {
}
~~~

Khi hai condition cùng áp dụng, cả hai phải khớp: `A && B`. Điều này là **AND logic**, không phải OR.

| `ConditionA.matches` | `ConditionB.matches` | Thành phần được phép đăng ký? |
| --- | --- | --- |
| `true` | `true` | Có, xét tiếp các ràng buộc khác |
| `true` | `false` | Không |
| `false` | `true` | Không |
| `false` | `false` | Không |

Nếu muốn OR, bạn phải thiết kế một condition tổng hợp tự trả `true` khi một trong các tiêu chí phù hợp, hoặc tách các bean/cấu hình phù hợp. Không thể lấy hai lớp condition trong cùng `@Conditional` rồi mặc định chúng nối OR.

Về mặt API, `@Conditional` có giá trị là một mảng `Class<? extends Condition>[]`. Spring có thể sắp xếp việc đánh giá condition bằng `Ordered` hoặc `@Order`; **không viết condition dựa vào giả định rằng chúng sẽ chạy đúng một lần hoặc theo thứ tự source**. Kết quả phải là tính toán từ trạng thái phù hợp, không dựa trên side effect của condition khác.

### Đặt `@Conditional` ở đâu?

Theo giao ước của Spring Framework, annotation được dùng trên:

- **Lớp cấu hình (`@Configuration`)**: điều kiện áp dụng cho cả cấu hình đó. Những khai báo `@Bean`, `@Import` và `@ComponentScan` gắn với lớp cấu hình cũng bị chi phối bởi kết quả này.
- **Lớp component (`@Component`, `@Service`,... hoặc stereotype tương ứng)**: class chỉ đủ điều kiện đăng ký thành component nếu condition đạt.
- **Phương thức `@Bean`**: điều kiện chỉ nhắm vào bean definition của phương thức đó, không tự động loại các phương thức khác trong cùng lớp.
- **Meta-annotation**: định nghĩa annotation tên miền riêng, bên trong có `@Conditional`, để tái sử dụng và truyền tham số khi cần.

Điều kiện trên lớp và trên phương thức có tác động **khác phạm vi**. Đây là nguyên nhân phổ biến của các tình huống “một bean không có mặt nhưng các bean khác vẫn xuất hiện”.

### Không có cơ chế kế thừa `@Conditional`

`@Conditional` **không được đánh dấu `@Inherited`**, và tài liệu Spring Framework nói rõ điều kiện từ superclass hoặc overridden method không tự được xét như điều kiện của thành phần mới. Khi tạo annotation tổng hợp có `@Conditional`, **không đánh dấu annotation tổng hợp đó bằng `@Inherited`**; nếu cần điều kiện, khai báo rõ tại lớp hoặc method đích.

## 3. Interface `Condition` và chữ ký `matches`

Giao ước Java quan trọng:

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

*Đây là phần trích cấu trúc giao ước để học, không phải file Spring Framework cần tự định nghĩa.*

Một custom condition đơn giản:

~~~java
package example.feature;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        String value = context.getEnvironment()
            .getProperty("example.feature.enabled", "true");
        return "true".equalsIgnoreCase(value);
    }
}
~~~

Trong ví dụ này:

- Không khai báo property: sử dụng giá trị mặc định `"true"`, condition trả `true`.
- `example.feature.enabled=true` hoặc `TRUE`: trả `true`.
- `example.feature.enabled=false`: trả `false`.
- Giá trị khác như `yes` hoặc `invalid`: trả `false` vì so sánh chuỗi chính xác sau khi bỏ qua hoa/thường.

Đây là lựa chọn có chủ ý của **custom condition cụ thể**, không phải quy tắc chung của `@Conditional`. Ví dụ không đọc metadata bởi điều kiện này chỉ cần `Environment`; tham số `metadata` vẫn là một phần bắt buộc của giao ước.

### `true` thực sự có nghĩa gì?

Giá trị `true` nghĩa là **condition không phủ quyết** việc đăng ký thành phần. Nếu còn các condition khác, chúng vẫn phải khớp; bean có thể gặp lỗi dependency khi được tạo, hoặc chưa khởi tạo vì `@Lazy`/scope.

### `false` thực sự có nghĩa gì?

Giá trị `false` yêu cầu Spring **bỏ qua đăng ký** thành phần tương ứng. Nó không xóa một bean instance đang chạy khi property đổi và không tự thực hiện logic “tắt tính năng” của object đã được tạo.

Trong ứng dụng khởi động thông thường, condition được đánh giá khi container đang xử lý cấu hình/đăng ký definitions. Việc đổi property sau khi context đã refresh **không tự kích hoạt đánh giá lại** toàn bộ `@Conditional`. Nếu cần cấu hình thay đổi liên tục ở runtime, hãy thiết kế cơ chế khác, thay vì trông chờ `matches` được gọi mỗi lần business method chạy.

## 4. `ConditionContext` cung cấp những gì?

`ConditionContext` là ngữ cảnh Spring cấp cho condition lúc đánh giá. Các phương thức chính:

| Phương thức | Mục đích | Lưu ý |
| --- | --- | --- |
| `getEnvironment()` | Đọc properties và profiles | Hợp với feature flag, cấu hình môi trường |
| `getRegistry()` | Quan sát `BeanDefinitionRegistry` | Có thể xem definitions đã đăng ký ở thời điểm đó |
| `getBeanFactory()` | Truy cập `ConfigurableListableBeanFactory` | Có thể là `null` ở một số tình huống |
| `getClassLoader()` | ClassLoader phục vụ tra cứu class | Cẩn thận side effects/chi phí class loading |
| `getResourceLoader()` | Tra cứu resource trên classpath hoặc nơi hỗ trợ | Phân biệt resource tồn tại với bean được đăng ký |

Ví dụ kiểm tra môi trường:

~~~java
@Override
public boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
) {
    return context.getEnvironment()
        .acceptsProfiles(org.springframework.core.env.Profiles.of("prod"));
}
~~~

*Đây là thân phương thức minh họa cần đặt trong một lớp `implements Condition` có import tương ứng.* Trong trường hợp chỉ kiểm tra active profile, `@Profile("prod")` thường đơn giản hơn là tự viết condition.

### Điều tối kỵ: tạo hoặc lấy bean instance trong condition

Tài liệu `Condition` quy định condition phải tuân theo những hạn chế tương tự `BeanFactoryPostProcessor`: **không tương tác với bean instances**. Không làm như sau:

~~~java
// Sai hướng thiết kế: tạo/lấy bean instance khi đang quyết định registration.
Object service = context.getBeanFactory().getBean("myService");
return service != null;
~~~

Đây là đoạn **phản ví dụ**, không phải mã để sử dụng. Đọc bean instance có thể kích hoạt khởi tạo sớm, đụng vòng phụ thuộc, gây side effect và còn có nguy cơ `getBeanFactory()` không sẵn có.

Nếu thật sự cần điều kiện dựa trên definitions, hãy dùng API kiểm tra **metadata/định nghĩa** thích hợp và hiểu thời điểm đánh giá. Với Spring Boot, `@ConditionalOnBean`/`@ConditionalOnMissingBean` thường thích hợp hơn tự xây condition. Hai annotation Boot này cũng có ràng buộc về **thứ tự xử lý definition**; không nên giả định tất cả bean definitions cuối cùng đã có từ thời điểm condition được kiểm tra.

### Condition cần đơn giản và có thể đánh giá lặp lại

Tốt:

- Đọc property ổn định trong `Environment`.
- Kiểm tra class/resource qua API phù hợp, không khởi tạo thành phần nghiệp vụ.
- Đọc metadata annotation trên element đang được xét.
- Trả kết quả xác định cho cùng một trạng thái đầu vào.

Không nên:

- Gọi HTTP API, cơ sở dữ liệu hoặc hệ thống không ổn định khi khởi động.
- Ghi file, gửi message hoặc thay đổi registry như “hệ quả” của `matches`.
- Dựa vào biến đếm số lần gọi, thời điểm thread hay thứ tự chạy.
- Lấy bean instance từ context để xác định kết quả.
- Nuốt mọi exception và giả vờ coi lỗi cấu hình là `false` nếu điều đó che một vấn đề nghiêm trọng.

Condition là công cụ quyết định **đủ điều kiện đăng ký**, không phải vòng đời tự động của dịch vụ.

## 5. `AnnotatedTypeMetadata` là metadata của cái gì?

Tham số thứ hai của `matches` là `org.springframework.core.type.AnnotatedTypeMetadata`. Nó mô tả các annotation trên **lớp hoặc phương thức đang được Spring xem xét**, cho phép đọc metadata mà không nhất thiết tạo instance của kiểu đó.

- Khi điều kiện gắn lên class: metadata có thể là `AnnotationMetadata`, cung cấp thông tin lớp.
- Khi điều kiện gắn lên method `@Bean`: metadata có thể là `MethodMetadata`, cung cấp thông tin phương thức.
- API chung cho phép tra cứu annotation thông qua `isAnnotated(...)`, `getAnnotationAttributes(...)` và những phương thức liên quan.
- Không nhầm metadata của thành phần đang xét với **danh sách bean instance** có trong container.

Ví dụ đọc tên element (minh họa, không phải chương trình độc lập):

~~~java
import org.springframework.core.type.AnnotationMetadata;
import org.springframework.core.type.MethodMetadata;

// metadata là tham số được Spring truyền vào matches(...)
String target;
if (metadata instanceof MethodMetadata method) {
    target = "method:" + method.getMethodName();
} else if (metadata instanceof AnnotationMetadata type) {
    target = "class:" + type.getClassName();
} else {
    target = "other";
}
~~~

Đây là cách **quan sát loại metadata** khi cần debug hoặc viết condition nhận tham số, không nên dùng nó để in log có side effect trong mỗi lần `matches`.

## 6. Ví dụ hoàn chỉnh: Spring Boot console không có web server

Ví dụ dùng **Java 17+, Maven 3.9+ và Spring Boot 3.3.13**. Chúng ta tạo một custom `Condition` quyết định có đăng ký bean `MessageService` theo property `lab.feature.enabled`.

**Đầu ra mong muốn:**

- Mặc định hoặc `true`: bean `featureService` tồn tại và trả `enabled`.
- `false` hoặc giá trị khác `true`: bean không được đăng ký; lookup tùy chọn trả `null`.
- Bất kể kết quả condition: ứng dụng chạy `WebApplicationType.NONE`, không mở embedded web server.

### 6.1. Cây thư mục

~~~text
conditional-contract-demo/
├── pom.xml
└── src/main/java/lab/
    ├── app/
    │   └── ConditionDemoApplication.java
    ├── api/
    │   └── MessageService.java
    └── feature/
        ├── FeatureEnabledCondition.java
        └── FeatureConfiguration.java
~~~

Đặt class main tại `lab.app`, lớp cấu hình tại `lab.feature` (ngoài vùng scan của app), rồi dùng `@Import` để nạp cấu hình một cách tường minh. Điều này giúp quan sát rõ **tác động của `@Conditional`**, không bị nhầm với tình huống lớp cấu hình chưa hề được Spring nạp.

### 6.2. `pom.xml`

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
    <groupId>lab</groupId>
    <artifactId>conditional-contract-demo</artifactId>
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

`spring-boot-starter` cung cấp Spring Framework context và Boot auto-configuration mà không yêu cầu HTTP server. Không cần thêm dependency web để học condition.

### 6.3. `src/main/java/lab/api/MessageService.java`

~~~java
package lab.api;

public interface MessageService {
    String message();
}
~~~

Interface này không mang `@Component` nên không tự được đăng ký thành bean. Một phương thức `@Bean` trong cấu hình sẽ tạo instance cụ thể.

### 6.4. `src/main/java/lab/feature/FeatureEnabledCondition.java`

~~~java
package lab.feature;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        String configured = context.getEnvironment()
            .getProperty("lab.feature.enabled", "true");
        return "true".equalsIgnoreCase(configured);
    }
}
~~~

Điểm cần nắm vững:

1. `implements Condition` khiến Spring biết đây là một điều kiện có thể dùng bởi `@Conditional`.
2. `@Override matches(...)` dùng đúng hai tham số mà Spring Framework truyền vào.
3. `ConditionContext` cấp môi trường để đọc property.
4. `metadata` không được dùng trong case này vì không có tham số annotation riêng; vẫn phải khai báo trong chữ ký method.
5. Return `boolean` **chỉ quyết định đăng ký bean**, không tự tạo object hoặc gọi nghiệp vụ.

### 6.5. `src/main/java/lab/feature/FeatureConfiguration.java`

~~~java
package lab.feature;

import lab.api.MessageService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @Conditional(FeatureEnabledCondition.class)
    public MessageService featureService() {
        return () -> "enabled";
    }
}
~~~

`@Conditional` ở **phương thức** chỉ điều khiển bean `featureService`. Spring vẫn có thể xử lý lớp `FeatureConfiguration` khi condition của method trả `false`.

`@Configuration(proxyBeanMethods = false)` là lựa chọn hợp lý ở ví dụ vì các factory method không gọi chéo nhau. Thuộc tính này **không thay đổi ý nghĩa của `Condition.matches`**.

### 6.6. `src/main/java/lab/app/ConditionDemoApplication.java`

~~~java
package lab.app;

import lab.api.MessageService;
import lab.feature.FeatureConfiguration;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "lab.app")
@Import(FeatureConfiguration.class)
public class ConditionDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(
                     ConditionDemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            MessageService service =
                context.getBeanProvider(MessageService.class)
                    .getIfAvailable();

            System.out.println("webServer=" +
                (context instanceof WebServerApplicationContext));
            System.out.println("featureBean=" +
                context.containsBean("featureService"));
            System.out.println("message=" +
                (service == null ? "none" : service.message()));
        }
    }
}
~~~

Ứng dụng dùng `@Import(FeatureConfiguration.class)` để đảm bảo lớp cấu hình được xử lý, mặc dù package `lab.feature` ở ngoài `lab.app` và không được component scan mặc định đưa vào. Việc thiếu bean khi property=false vì thế có thể quy cho condition, không phải “cấu hình không được tìm thấy”.

`getBeanProvider(...).getIfAvailable()` không ném exception khi thiếu bean. Trong ví dụ này tại mỗi lần chạy có tối đa một bean `MessageService`, vì chỉ có một factory method cung cấp kiểu đó.

### 6.7. Build và chạy

Đứng tại thư mục chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q clean package
java -jar target/conditional-contract-demo-1.0.0.jar
~~~

Ba dòng **do chính chương trình in** (các log Spring Boot có thể xuất hiện thêm):

~~~text
webServer=false
featureBean=true
message=enabled
~~~

Khi không có property, custom condition dùng mặc định `"true"` và cho phép đăng ký bean.

Chạy với property tắt:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --lab.feature.enabled=false
~~~

Kết quả:

~~~text
webServer=false
featureBean=false
message=none
~~~

Chạy với giá trị true tường minh:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --lab.feature.enabled=true
~~~

Kết quả:

~~~text
webServer=false
featureBean=true
message=enabled
~~~

Chạy với giá trị không phải true:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --lab.feature.enabled=other
~~~

Kết quả giống trường hợp `false`, vì logic của `FeatureEnabledCondition` chỉ chấp nhận chuỗi `true`, không phải vì `@Conditional` tự có quy tắc hiểu property như thế.

### Bảng đối chiếu

| `lab.feature.enabled` | `matches` | Bean `featureService` | `message` |
| --- | --- | --- | --- |
| Thiếu property | `true` | Có | `enabled` |
| `true` | `true` | Có | `enabled` |
| `TRUE` | `true` | Có | `enabled` |
| `false` | `false` | Không | `none` |
| `other` | `false` | Không | `none` |

**Phân biệt dấu hiệu:** `featureBean=false` nghĩa là bean không có trong context sau khi khởi động. Trong cấu hình này, cách giải thích là `@Conditional` ở method phủ quyết `BeanDefinition` đó; không phải bean tồn tại mà chỉ trả kết quả nghiệp vụ rỗng.

## 7. Chuyển condition từ method lên class: chuyện gì thay đổi?

Trong ví dụ chính, điều kiện chỉ đặt trên method `featureService()`. Hãy thử **di chuyển** annotation lên `FeatureConfiguration`:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(FeatureEnabledCondition.class)
public class FeatureConfiguration {

    @Bean
    public MessageService featureService() {
        return () -> "enabled";
    }
}
~~~

*Đây là bản thay thế nội dung class `FeatureConfiguration`, giữ package/import tương ứng; không phải file Java độc lập nếu bạn bỏ những import ở mục 6.5.*

Trong demo hiện tại, ba dòng output vẫn giống nhau theo property vì lớp chỉ có một `@Bean`. Nhưng semantics đã thay đổi:

- `@Conditional` **trên method**: class cấu hình được xử lý, chỉ riêng bean method bị điều kiện ràng buộc.
- `@Conditional` **trên class**: khi condition trả `false`, toàn bộ cấu hình đó bị bỏ qua, bao gồm `@Bean`, `@Import` và `@ComponentScan` gắn với class đó.

Giả sử thêm một method `@Bean` khác cung cấp kiểu `Clock` không liên quan. Ở kiểu condition trên method, `Clock` vẫn được đăng ký khi bean `MessageService` bị bỏ qua. Ở kiểu condition trên class, cả hai bean methods đều bị chặn khi điều kiện lớp không đạt. Vì vậy hãy đặt condition ở phạm vi nhỏ nhất phù hợp với yêu cầu.

### Chú ý sự khác nhau về thời điểm đánh giá

Spring có nhiều giai đoạn khi xử lý class cấu hình, chẳng hạn phân tích cấu hình và đăng ký bean definitions. Kết quả của condition trên class có thể ảnh hưởng việc phân tích `@Import`/`@ComponentScan` bên trong, trong khi condition ở `@Bean` method áp dụng tại bước đăng ký bean method.

Đó là lý do không nên tùy tiện viết một condition dựa trên “bean X đã tồn tại” rồi áp dụng ở mọi nơi. Tại thời điểm sớm, các bean definitions mong đợi có thể chưa được xử lý. Nếu cần điều khiển giai đoạn rõ ràng, hãy tìm hiểu `ConfigurationCondition` ở mục 10.

## 8. Kết hợp nhiều condition một cách đúng đắn

Ví dụ giả định một bean chỉ được đăng ký nếu:

- Feature flag bật.
- Hệ thống chạy một profile phù hợp.

Định nghĩa thêm condition dựa trên profile:

~~~java
package lab.feature;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Profiles;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class ProductionCondition implements Condition {
    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment()
            .acceptsProfiles(Profiles.of("prod"));
    }
}
~~~

Thay annotation trên method trong `FeatureConfiguration`:

~~~java
@Bean
@Conditional({
    FeatureEnabledCondition.class,
    ProductionCondition.class
})
public MessageService featureService() {
    return () -> "enabled";
}
~~~

**Hai đoạn trên là mở rộng cho project mục 6**; đặt class `ProductionCondition` vào file `src/main/java/lab/feature/ProductionCondition.java` và cập nhật method `featureService`, không thêm đồng thời một method cùng tên.

Lúc này phải đồng thời có feature flag phù hợp **và** profile `prod`. Bạn có thể chạy:

~~~bash
java -jar target/conditional-contract-demo-1.0.0.jar --spring.profiles.active=prod
java -jar target/conditional-contract-demo-1.0.0.jar --spring.profiles.active=prod --lab.feature.enabled=false
~~~

Ở lệnh đầu, nếu đã rebuild sau khi thay đổi code, bean được đăng ký. Ở lệnh hai, bean bị chặn vì feature flag=false dù profile phù hợp. Nếu quên rebuild, JAR cũ vẫn có phiên bản một điều kiện.

Tuy nhiên, khi chỉ cần profile, `@Profile("prod")` thường trực tiếp và dễ bảo trì hơn; không cần tự định nghĩa `ProductionCondition`.

### Multiple conditions là AND, nhưng đừng dựa trên thứ tự

Spring có thể sử dụng `Ordered`/`@Order` để sắp xếp việc đánh giá condition. Điều đó **không cấp quyền** để condition A ghi trạng thái mà condition B phải đọc, hoặc để việc chạy một lần duy nhất trở thành giả định nghiệp vụ. Các condition nên là phép kiểm tra độc lập, ổn định, không có side effect.

## 9. Dùng metadata để tạo annotation điều kiện tùy biến

Vì sao `matches` còn nhận `AnnotatedTypeMetadata`, trong khi ví dụ chính chỉ đọc `Environment`? Lý do là condition tổng quát có thể **đọc tham số của annotation** đang gắn trên lớp hoặc method.

Ví dụ, ta muốn cách viết:

~~~java
@EnabledWhenProperty("lab.feature.enabled")
@Bean
MessageService featureService() {
    return () -> "enabled";
}
~~~

Định nghĩa annotation tùy biến:

### `src/main/java/lab/feature/EnabledWhenProperty.java`

~~~java
package lab.feature;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(PropertyEnabledCondition.class)
public @interface EnabledWhenProperty {
    String value();
}
~~~

### `src/main/java/lab/feature/PropertyEnabledCondition.java`

~~~java
package lab.feature;

import java.util.Map;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class PropertyEnabledCondition implements Condition {

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        Map<String, Object> attrs =
            metadata.getAnnotationAttributes(
                EnabledWhenProperty.class.getName()
            );

        if (attrs == null) {
            return false;
        }

        String propertyName = (String) attrs.get("value");
        String actual = context.getEnvironment()
            .getProperty(propertyName, "false");

        return "true".equalsIgnoreCase(actual);
    }
}
~~~

Đây là **phương án thay thế/mở rộng**, không nên đồng thời giữ `@Conditional(FeatureEnabledCondition.class)` và thêm `@EnabledWhenProperty` lên cùng method nếu mục tiêu là so sánh riêng tác dụng từng loại. Nếu cùng áp dụng, chúng kết hợp theo AND, và giá trị mặc định của hai condition trong ví dụ là khác nhau.

### Giải thích chính xác vai trò hai tham số

- `context` cấp dữ liệu runtime environment để đọc **giá trị property**.
- `metadata` cho phép đọc annotation `@EnabledWhenProperty` để xác định **tên property cần kiểm tra**.
- `metadata.getAnnotationAttributes(...)` có thể trả `null` nếu annotation không hiện diện; đoạn code xử lý rõ trường hợp này.
- `getProperty(propertyName, "false")` làm mặc định là không đăng ký khi thiếu property. Điều này khác với `FeatureEnabledCondition` chính ở mục 6 có mặc định `true`.

Bạn không cần dùng reflection để khởi tạo class được kiểm tra hoặc gọi bean method. Spring cung cấp metadata đủ cho ví dụ.

**Không gắn `@Inherited` lên `@EnabledWhenProperty`.** Điều kiện của Spring không hỗ trợ kế thừa annotation như một quy tắc đăng ký chung.

### Khi nào nên dùng meta-annotation?

Khi nhiều module cần diễn đạt cùng một điều kiện nhưng với cách đặt tên dễ hiểu, hoặc cần nhận tham số annotation cụ thể. Tuy nhiên, nếu chỉ muốn điều kiện theo property trong Spring Boot, ưu tiên `@ConditionalOnProperty` để giảm mã tự viết và tận dụng các quy tắc Boot đã có.

## 10. `ConfigurationCondition` và hai giai đoạn xử lý

`Condition` đơn giản đủ cho các kiểm tra môi trường, classpath/resource và metadata. Khi condition phải phụ thuộc vào **giai đoạn** đang xử lý class cấu hình, Spring cung cấp interface mở rộng `ConfigurationCondition`.

Nó thêm một method:

~~~java
ConfigurationPhase getConfigurationPhase();
~~~

Hai giá trị thường cần hiểu:

- `PARSE_CONFIGURATION`: giai đoạn phân tích cấu hình, nơi quyết định có phân tích những `@Import`, `@ComponentScan` và `@Bean` đi kèm class hay không.
- `REGISTER_BEAN`: giai đoạn đăng ký bean definition từ cấu hình đã được phân tích, phù hợp cho những điều kiện cần dựa trên definitions đã đăng ký theo quy tắc tương ứng.

Ví dụ minh họa khung code:

~~~java
import org.springframework.context.annotation.ConfigurationCondition;

public final class RegistrationPhaseCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        org.springframework.core.type.AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment()
            .getProperty("lab.registration.enabled", Boolean.class, false);
    }
}
~~~

*Đoạn trên minh họa method và phase, cần bổ sung khai báo package/file tương ứng khi đưa vào project.* Condition này vẫn chỉ đọc property; việc chỉ định phase chưa làm nó “đợi mọi bean của ứng dụng được khởi tạo”.

Spring Boot dùng những condition chuyên biệt, đôi khi có yêu cầu về giai đoạn và thứ tự auto-configuration. Không dùng `ConfigurationCondition` trừ khi thật sự hiểu sự khác nhau của các giai đoạn.

## 11. `@Conditional` trong auto-configuration Spring Boot

Các class auto-configuration của Spring Boot thường được đưa vào context sau khi Boot phát hiện từ tệp:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ ý tưởng của một thư viện:

~~~java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
public class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
~~~

*Đây là đoạn minh họa, giả định đã có `RemoteClient` và import/đăng ký phù hợp; không phải file Java chạy độc lập.*

Cơ chế áp dụng:

1. Class auto-configuration là **ứng viên** vì được liệt kê trong imports.
2. `@ConditionalOnClass` quyết định việc xem xét class khi dependency có mặt.
3. `@ConditionalOnMissingBean` quyết định có đóng góp bean mặc định khi chưa có bean tương ứng mà điều kiện nhìn thấy hay không.
4. Bean được tạo khi context thực sự xử lý/khởi tạo các definitions, không phải vì file imports vừa được đọc.

### Mối quan hệ giữa annotation Spring và annotation Boot

| Annotation | Thuộc | Mục đích |
| --- | --- | --- |
| `@Conditional` | Spring Framework | Gắn danh sách `Condition` tổng quát |
| `Condition` | Spring Framework | Giao ước quyết định true/false |
| `@Profile` | Spring Framework | Kích hoạt thành phần theo profile; dựa trên cơ chế điều kiện |
| `@ConditionalOnProperty` | Spring Boot | Kiểm tra cấu hình property theo quy tắc Boot |
| `@ConditionalOnClass` | Spring Boot | Kiểm tra điều kiện classpath |
| `@ConditionalOnBean` | Spring Boot | Kiểm tra bean đã có trong ngữ cảnh đánh giá |
| `@ConditionalOnMissingBean` | Spring Boot | Chỉ tạo bean mặc định khi thiếu bean phù hợp |
| `@ConditionalOnWebApplication` | Spring Boot | Điều kiện dựa trên web application |
| `@ConditionalOnNotWebApplication` | Spring Boot | Điều kiện dựa trên ứng dụng không phải web |

Với một điều kiện đơn giản theo property, thường **không cần tự viết `Condition`**. Ví dụ:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "lab.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
MessageService featureService() {
    return () -> "enabled";
}
~~~

Đây là đoạn thay thế cho method trong `FeatureConfiguration`; cần import `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty`.

Tuy giống mục 6 ở các trường hợp `true`/`false`/thiếu property, `@ConditionalOnProperty` là API Boot có semantics riêng, không phải kết quả tự động của phép `String.equalsIgnoreCase` trong custom condition.

### Cẩn thận với điều kiện phụ thuộc bean

Các điều kiện kiểu `@ConditionalOnBean` và `@ConditionalOnMissingBean` chỉ nhìn thấy những definitions đã được xử lý tại thời điểm chúng chạy. Spring Boot khuyến nghị dùng loại điều kiện này trong auto-configuration, vốn thường được xử lý sau bean definitions của người dùng. Đừng viết custom `Condition` dùng tên bean rồi giả định toàn bộ context đã hoàn tất khởi tạo.

## 12. Kiểm thử condition và đọc bằng chứng

### Ba lớp bằng chứng cần phân biệt

- **Giá trị environment:** property có thật sự nhận đúng giá trị hay không?
- **Đánh giá condition:** condition cụ thể trả `true`/`false` tại thời điểm Spring xét thành phần?
- **Trạng thái bean:** sau refresh, bean name/definition/type nào có mặt trong context?

Trong demo, `context.containsBean("featureService")` là bằng chứng trực tiếp về trạng thái bean sau khởi động. Bạn có thể xem tên bean theo kiểu:

~~~java
String[] names =
    context.getBeanNamesForType(MessageService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

*Đoạn trên cần biến `context` và import `MessageService` như chương trình đầy đủ ở mục 6.*

### `--debug` và Condition Evaluation Report có giới hạn

Spring Boot có *Condition Evaluation Report* cho các điều kiện Boot, giúp giải thích những auto-configuration và method đã khớp/không khớp. Tuy nhiên, **không được giả định mọi custom `Condition` của Spring Framework đều tự được báo cáo trong đó với message riêng**. Đặc biệt, custom condition chỉ `implements Condition` như `FeatureEnabledCondition` của ví dụ **không nhất thiết xuất hiện trong report Boot giống như một `SpringBootCondition`**.

Hãy lấy bằng chứng bằng các trạng thái bean của demo và thử property trước. Nếu cần báo cáo phong phú từ condition tự viết trong Boot, hãy tìm hiểu `SpringBootCondition` và `ConditionOutcome` — đó là một mức mở rộng riêng, không phải chữ ký bắt buộc của `Condition.matches`.

### Kiểm thử có lặp lại

Đối với bài tập nhỏ, chạy bốn lần ứng dụng bằng các property khác nhau là đủ để chứng minh contract. Với thư viện lớn, có thể dùng `ApplicationContextRunner` (Spring Boot test) để tạo context bằng các properties đầu vào khác nhau và kiểm tra bean presence/absence. Đây là một kỹ thuật kiểm thử, **không thay đổi contract** của `matches`.

Ví dụ ý tưởng assert:

~~~java
// Đây là fragment test, cần dependency test,
// ApplicationContextRunner và cấu hình test phù hợp.
runner.withPropertyValues("lab.feature.enabled=false")
    .run(context ->
        org.assertj.core.api.Assertions.assertThat(context)
            .doesNotHaveBean(MessageService.class));
~~~

Dòng này chỉ minh họa cách kiểm chứng trạng thái; **không phải unit test tự chạy độc lập**. Nếu muốn dùng `ApplicationContextRunner`, cần tạo runner có `FeatureConfiguration` và khai báo dependency test phù hợp.

## 13. Lỗi thường gặp và cách sửa

| Triệu chứng / suy nghĩ | Giải thích đúng |
| --- | --- |
| “`matches=true` tức bean đã tạo” | Chỉ là không phủ quyết registration; bean còn phụ thuộc scope, dependencies và vòng đời |
| “`matches=false` thì business method được gọi và trả `null`” | Sai: bean definition bị chặn ở bước cấu hình, method nghiệp vụ không được gọi |
| “Đổi property runtime sẽ tự bật bean ngay” | Không; `@Conditional` thường được xét khi cấu hình/đăng ký, không có cơ chế refresh tự động |
| “Hai condition trong `@Conditional` dùng OR” | Sai; tất cả condition phải khớp (AND) |
| “Method-level condition loại cả class cấu hình” | Sai; class còn có thể đăng ký những bean khác |
| “Class-level condition chỉ chặn một method” | Sai; nó chi phối cấu hình và các khai báo liên quan |
| “Trong `matches` có thể gọi `getBean` bình thường” | Không nên tương tác bean instance ở thời điểm trước registration |
| “Chỉ cần bean mang `@Conditional` nhưng class cấu hình không được scan/import” | Condition không giúp Spring tự phát hiện class không được nạp |
| “`@Conditional` được thừa kế tự động” | Tài liệu Spring không hỗ trợ kế thừa condition theo cách đó |
| “Custom condition lúc nào cũng hiện trong Boot report” | Không bảo đảm; report của Boot tập trung vào cơ chế condition/reporting tương ứng |
| “Mọi condition dựa trên bean có thể xem toàn bộ definitions” | Không; phải xét giai đoạn và thứ tự xử lý |
| “Nếu condition có exception, Spring mặc định coi false” | Sai kỳ vọng: exception từ condition thường làm xử lý cấu hình/khởi động thất bại, cần sửa lỗi gốc |

### Cách gỡ lỗi tuần tự

1. Xác nhận lớp mang `@Conditional` hoặc `@Bean` đang được Spring xử lý (component scan, `@Import`, auto-configuration...).
2. Xác nhận đầy đủ properties/profiles/classpath mà condition đọc; kiểm tra chính xác tên và kiểu dữ liệu.
3. Phân biệt condition gắn ở **class** hay **method**.
4. Kiểm tra nhiều condition kết hợp AND có condition nào không khớp.
5. Nếu dùng bean-dependent condition, xem phase và thứ tự đăng ký definitions.
6. Kiểm tra `ApplicationContext` sau khởi động bằng tên/kiểu bean hoặc `BeanDefinitionRegistry` khi phù hợp.
7. Với Boot condition có báo cáo, dùng `--debug`; với plain custom `Condition`, ưu tiên test và đọc kết quả context.
8. Chỉ khi đã xác định đúng tầng lỗi mới chỉnh code, tránh sửa component scan hay thêm bean tùy tiện để “chữa” condition=false.

## 14. Bài tập tự kiểm tra

1. **Khái niệm:** mô tả ý nghĩa của `true` và `false` từ `Condition.matches`. Vì sao true không đồng nghĩa với singleton instance đã khởi tạo?
2. **Phạm vi:** đặt `@Conditional` trên method `@Bean` khác gì đặt trên class `@Configuration`?
3. **Hai tham số:** khi nào dùng `ConditionContext.getEnvironment()`, khi nào dùng `AnnotatedTypeMetadata.getAnnotationAttributes(...)`?
4. **Thực nghiệm:** chạy dự án mục 6 với property không có, true, false và other. Đối chiếu đúng ba dòng output.
5. **AND:** thay `@Conditional(FeatureEnabledCondition.class)` bằng hai condition trong mục 8. Dự đoán kết quả theo profile `prod` và property.
6. **Metadata:** tạo `@EnabledWhenProperty("lab.feature.enabled")` trong mục 9; bỏ annotation direct cũ, rebuild rồi thử không truyền property và true. Giải thích sự khác nhau giữa mặc định false ở annotation tổng hợp với mặc định true của demo gốc.
7. **Lớp vs method:** thêm một `@Bean` độc lập kiểu `Clock` trong `FeatureConfiguration`. Đặt condition lúc trên method, lúc trên class; với property=false, giải thích bean nào bị chặn.
8. **Không được làm:** viết ví dụ phản tác dụng của `matches` lấy bean instance. Vì sao cách này có thể khởi tạo bean sớm hoặc làm context lỗi?
9. **Tự cấu hình:** vì sao một class có trong `AutoConfiguration.imports` nhưng condition của nó trả false thì không đóng góp bean tương ứng?
10. **Đọc report:** khi một custom condition không xuất hiện trong Condition Evaluation Report của Boot, điều gì có thể và không thể kết luận?

**Tiêu chí hoàn thành:** bạn biết viết một `Condition` hợp lệ, giải thích đúng `matches(context, metadata)`, nhận ra phạm vi class/method, hiểu AND của nhiều condition, biết kiểm chứng bằng context và phân biệt thời điểm đánh giá điều kiện với khởi tạo bean.

## 15. Tài liệu chính thức

- [Spring Framework 6.1 — `@Conditional` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html)
- [Spring Framework 6.1 — `Condition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html)
- [Spring Framework 6.1 — `ConditionContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html)
- [Spring Framework 6.1 — `ConfigurationCondition` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html)
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
