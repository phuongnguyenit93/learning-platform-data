# Điều kiện được đánh giá khi xây context, không phải công tắc tự cập nhật theo từng lời gọi

## 1. Ý chính: Spring chọn bean khi dựng ApplicationContext

Các annotation như **@Conditional**, **@ConditionalOnProperty**, **@ConditionalOnClass**, **@ConditionalOnBean** và **@ConditionalOnMissingBean** được Spring/Spring Boot sử dụng để quyết định **lớp cấu hình hoặc bean definition nào được đưa vào ApplicationContext** trong giai đoạn phân tích và đăng ký cấu hình.

**Chúng không tự biến thành công tắc được kiểm tra lại mỗi lần ứng dụng gọi một phương thức trên bean.**

Nếu **demo.feature.enabled=false** khi Spring xét một phương thức @Bean có **@ConditionalOnProperty(havingValue="true")**, định nghĩa của bean đó bị bỏ qua. Sau khi ứng dụng đã khởi động xong, việc đổi giá trị trong **Environment** thành true **không tự thêm lại** định nghĩa bị bỏ qua. Tương tự, nếu bean đã được đăng ký khi startup với property true, việc đổi property thành false sau đó **không tự gỡ hoặc hủy bean**.

Phải phân biệt:

- **Cấu hình hiện đọc được**: giá trị của Environment hoặc các nguồn property tại một thời điểm.
- **Condition evaluation**: quyết định trong quá trình xây dựng configuration/bean definitions.
- **Bean definition**: mô tả cách container tạo bean, scope, dependency và các đặc điểm khác.
- **Bean instance**: đối tượng thực tế được tạo theo lifecycle của Spring.
- **Runtime method call**: lần code nghiệp vụ gọi method trên một instance hoặc thông qua proxy đang có.

Chỉ tầng cuối cùng xảy ra theo từng lời gọi thông thường. Việc condition được đọc ở các pha build context không khiến nó trở thành một runtime listener.

### Ví dụ tối giản

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
FeatureClient featureClient() {
    return () -> "ready";
}
~~~

Đây là snippet minh họa; để biên dịch cần class FeatureClient và các import Spring trong một lớp cấu hình. Đoạn này nói: **đăng ký bean FeatureClient khi điều kiện đạt lúc xử lý @Bean**. Nó không nói: “mỗi lần FeatureClient.call() được gọi, hãy đọc lại property và tạo/hủy bean”.

## 2. Condition được đánh giá khi nào?

Một chuỗi khởi động Spring Boot thông thường:

~~~text
SpringApplication.run(...)
        |
        v
Chuẩn bị Environment và các PropertySource
        |
        v
Khởi tạo ApplicationContext
        |
        v
Đọc các @Configuration, @Import, auto-configuration candidates
        |
        v
Đánh giá các condition phù hợp trong quá trình
phân tích cấu hình và đăng ký bean definitions
        |
        v
Đăng ký BeanDefinition của các nhánh được chọn
        |
        v
Xử lý BeanFactory, post-processors, inject dependency
và tạo các singleton eager cần thiết
        |
        v
Context refresh hoàn tất
        |
        v
ApplicationRunner và hoạt động nghiệp vụ
        |
        +--> Gọi bean methods
        +--> Có thể đọc Environment
        +--> Không tự xét lại condition sau mỗi method call
~~~

Đây là sơ đồ giải thích các pha, không phải bản sao chính xác mọi phương thức nội bộ của Spring Framework. Một condition có thể được đánh giá trong pha **PARSE_CONFIGURATION** hoặc **REGISTER_BEAN**, và một implementation có thể được framework hỏi nhiều lần trong quá trình xử lý metadata. Vì vậy không nên khẳng định cứng nhắc rằng “mọi condition luôn chạy đúng một lần duy nhất”.

Điều ổn định về mặt thiết kế là **@Conditional quyết định cấu trúc container ở những bước xử lý cấu hình**, không tự theo dõi property như một công tắc runtime.

### 2.1. Vì sao @ConditionalOnBean nhạy với thứ tự?

**@ConditionalOnBean** và **@ConditionalOnMissingBean** dựa trên trạng thái bean đã được Spring xử lý ở thời điểm condition được kiểm tra. Vì thế Spring Boot dùng cơ chế xử lý auto-configuration sau những cấu hình do người dùng khai báo, và cung cấp thứ tự before/after giữa các auto-configuration khi cần.

Khi ứng dụng đã khởi động, Spring **không duy trì một bộ theo dõi liên tục** để mỗi lần có thêm/mất một bean thì tự tái xét tất cả các @ConditionalOnMissingBean trước đó. Mặc định, đó là quyết định **đăng ký definition**.

### 2.2. Condition ở cấp class khác condition ở cấp method

Ví dụ ở cấp class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "demo.mail",
    name = "enabled",
    havingValue = "true"
)
class MailConfiguration {

    @Bean
    MailSender mailSender() {
        return new MailSender();
    }
}
~~~

Ví dụ này dùng kiểu MailSender giả định, không phải source hoàn chỉnh. Condition trên lớp có thể làm bỏ qua cả nhánh cấu hình, trong khi condition trên từng @Bean method có thể loại riêng method tương ứng. Dù đặt ở cấp nào, annotation không mặc nhiên được đánh giá lại cho mỗi lần client gửi email.

## 3. @ConditionalOnProperty đọc gì?

Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Spring Boot kiểm tra key **demo.feature.enabled** từ **Environment** ở giai đoạn đánh giá. Với havingValue true, property phải phù hợp giá trị true; **matchIfMissing=false** nghĩa là thiếu property thì điều kiện không đạt.

| Property khi xây context | Condition trên @Bean có đạt? | Bean definition của method đó |
| --- | --- | --- |
| true | Có | Có thể được đăng ký nếu điều kiện khác cũng đạt |
| false | Không | Bị bỏ qua |
| Vắng mặt | Không | Bị bỏ qua |
| Giá trị khác true | Không | Bị bỏ qua |

Bảng chỉ mô tả một condition trên một @Bean; một bean cùng kiểu vẫn có thể được đăng ký bởi một nguồn khác, và một class auto-configuration vẫn có thể bị exclude.

**Điều quan trọng là thời điểm**: property hiện tại sau startup có thể khác property mà condition đã nhìn thấy lúc đăng ký.

### 3.1. Property source có thể đổi, bean graph không tự đổi

Giả sử Spring xét property false và bỏ qua FeatureClient. Sau refresh, code thêm một **MapPropertySource** có độ ưu tiên cao chứa key **demo.feature.enabled=true**. Khi đó:

- **Environment.getProperty("demo.feature.enabled")** có thể trả true.
- Một service tự gọi **Environment.getProperty(...)** ở mỗi lần xử lý có thể trả kết quả khác.
- **ObjectProvider<FeatureClient>** vẫn có thể không tìm thấy bean, vì **@ConditionalOnProperty** không tự đăng ký lại một BeanDefinition đã bị bỏ qua.

Ngược lại, nếu FeatureClient được đăng ký lúc property true, thay Environment thành false **không tự gỡ** FeatureClient.

### 3.2. Sửa application.properties có khác không?

Thay nội dung một file **application.properties** khi tiến trình đang chạy **không có nghĩa** Spring Boot tự đọc lại file và làm mới context. Dữ liệu file thường được load vào Environment lúc startup. Muốn áp dụng thay đổi, cần một cơ chế reload được hỗ trợ hoặc khởi động context/ứng dụng mới; và cơ chế reload không nhất thiết làm condition của mọi bean được chạy lại.

Bài thực hành bên dưới **chủ động sửa Environment trong bộ nhớ** để quan sát hai tầng. Nó **không** giả định file application.properties tự hot reload.

## 4. Ví dụ chạy được với Java 21 và Spring Boot 3.3.13

Mục tiêu: trên cùng một tiến trình Spring Boot, thay đổi giá trị Environment **sau refresh**, rồi quan sát việc bean có mặt/vắng mặt không tự cập nhật.

Ta viết:

1. **FeatureClient**: interface mà auto-configuration có thể tạo bean.
2. **FeatureAutoConfiguration**: có @Bean FeatureClient gắn **@ConditionalOnProperty**.
3. **RuntimeGate**: luôn tồn tại, method đọc Environment **mỗi lần gọi**.
4. **DemoApplication**: sau khi startup xong, dùng **ApplicationRunner** đổi property trong Environment rồi in kết quả trước/sau.

Cấu trúc:

~~~text
condition-lifecycle-demo/
├── pom.xml
└── src/main/
    ├── java/dev/course/
    │   ├── api/FeatureClient.java
    │   ├── autoconfig/FeatureAutoConfiguration.java
    │   └── app/
    │       ├── RuntimeGate.java
    │       └── DemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Lớp ứng dụng ở package **dev.course.app**. Auto-configuration thuộc package **dev.course.autoconfig** nằm ngoài vùng component scan mặc định của app, nên lớp auto-configuration đi vào ứng dụng qua file imports, không phải vì component scan tình cờ tìm thấy.

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.course</groupId>
    <artifactId>condition-lifecycle-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
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

Starter cơ bản đủ cho ví dụ context không có web server. Không cần kết nối mạng khi chạy JAR sau khi các dependencies đã được tải và build.

### 4.2. FeatureClient.java

**src/main/java/dev/course/api/FeatureClient.java**

~~~java
package dev.course.api;

@FunctionalInterface
public interface FeatureClient {
    String call();
}
~~~

FeatureClient không tự đọc Environment. Nó chỉ là API của bean được đăng ký có điều kiện.

### 4.3. FeatureAutoConfiguration.java

**src/main/java/dev/course/autoconfig/FeatureAutoConfiguration.java**

~~~java
package dev.course.autoconfig;

import dev.course.api.FeatureClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    FeatureClient featureClient() {
        return () -> "ready";
    }
}
~~~

Khi property true lúc xây context, Spring đăng ký BeanDefinition của FeatureClient theo phương thức này. Khi false, definition bị bỏ qua. **Sau khi context đã refresh, không có logic trong code trên để tạo/hủy bean khi property bị thay đổi.**

### 4.4. Đăng ký candidate qua AutoConfiguration.imports

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.course.autoconfig.FeatureAutoConfiguration
~~~

Trong Spring Boot 3.x, file imports là cách thư viện công bố auto-configuration candidates. Annotation @AutoConfiguration trên source mà không có cơ chế phát hiện phù hợp thì không tự bảo đảm Boot import class ngoài package scan.

### 4.5. RuntimeGate.java: đọc Environment ở từng lời gọi

**src/main/java/dev/course/app/RuntimeGate.java**

~~~java
package dev.course.app;

import org.springframework.core.env.Environment;

public final class RuntimeGate {
    private final Environment environment;

    public RuntimeGate(Environment environment) {
        this.environment = environment;
    }

    public String state() {
        boolean enabled = environment.getProperty(
            "demo.feature.enabled", Boolean.class, false);
        return enabled ? "ON" : "OFF";
    }
}
~~~

RuntimeGate khác với FeatureClient: method **state()** luôn gọi lại Environment. Nếu Environment thay đổi thực sự, kết quả một lần gọi method về sau có thể khác. Nhưng class RuntimeGate **không** làm Spring chạy lại @ConditionalOnProperty của FeatureClient.

### 4.6. DemoApplication.java: đổi một PropertySource sau refresh

**src/main/java/dev/course/app/DemoApplication.java**

~~~java
package dev.course.app;

import java.util.HashMap;
import java.util.Map;

import dev.course.api.FeatureClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RuntimeGate runtimeGate(Environment environment) {
        return new RuntimeGate(environment);
    }

    @Bean
    ApplicationRunner compare(
            ObjectProvider<FeatureClient> clients,
            ConfigurableEnvironment environment,
            RuntimeGate gate) {

        return args -> {
            boolean before = environment.getProperty(
                "demo.feature.enabled", Boolean.class, false);

            System.out.println("property.before=" + before);
            System.out.println("bean.before=" +
                (clients.getIfAvailable() != null));
            System.out.println("gate.before=" + gate.state());

            Map<String, Object> overrides = new HashMap<>();
            overrides.put(
                "demo.feature.enabled",
                Boolean.toString(!before));

            environment.getPropertySources().addFirst(
                new MapPropertySource("late-override", overrides));

            System.out.println("property.after=" +
                environment.getProperty(
                    "demo.feature.enabled", Boolean.class, false));
            System.out.println("bean.after=" +
                (clients.getIfAvailable() != null));
            System.out.println("gate.after=" + gate.state());
        };
    }
}
~~~

**Lưu ý về tính runnable:**

- **ApplicationRunner** thực thi sau khi Spring đã refresh context. Vì vậy lúc runner thêm MapPropertySource, Spring đã quyết định những bean definitions nào thuộc ApplicationContext.
- **MapPropertySource** được thêm bằng **addFirst**, có độ ưu tiên cao hơn những property sources cũ. Nhờ vậy đoạn kiểm tra cố ý đổi false thành true hoặc true thành false.
- **ObjectProvider.getIfAvailable()** trả bean nếu có, hoặc null nếu không có. Nó có thể khiến một bean lazy được tạo nếu definition đã tồn tại, nhưng không tự đăng ký definition bị bỏ qua.
- Method **state()** được gọi lại trước và sau thay đổi; nó minh họa runtime lookup thật sự.
- Không có API rebuild context, không remove BeanDefinition và không xóa bean singleton. Mọi thay đổi chỉ nằm ở Environment.

### 4.7. application.properties

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
demo.feature.enabled=false
~~~

Property mặc định false. Có thể ghi đè bằng tham số dòng lệnh khi **khởi động tiến trình mới**. Các dòng logging chỉ nhằm giúp nhìn rõ stdout của chương trình.

### 4.8. Build

Trong thư mục **condition-lifecycle-demo**:

~~~bash
mvn -q -DskipTests package
~~~

Yêu cầu JDK 21 và Maven 3.9+. Sau khi build thành công sẽ có **target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar**.

### 4.9. Chạy A: startup false rồi đổi Environment thành true

~~~bash
java -jar target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

Sáu dòng do ApplicationRunner in:

~~~text
property.before=false
bean.before=false
gate.before=OFF
property.after=true
bean.after=false
gate.after=ON
~~~

Giải thích:

1. Khi xây context, Environment có **demo.feature.enabled=false** nên phương thức @Bean có condition không được đăng ký.
2. Runner đọc property false, không tìm thấy bean FeatureClient và RuntimeGate cho OFF.
3. Runner thêm một property source mới với giá trị true; Environment và RuntimeGate thấy true/ON.
4. **FeatureClient vẫn không có.** Condition bị bỏ qua trong bước build trước đó không tự chạy lại để đăng ký bean.

### 4.10. Chạy B: startup true rồi đổi Environment thành false

Khởi động **tiến trình mới**:

~~~bash
java -jar target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true
~~~

Sáu dòng do ApplicationRunner in:

~~~text
property.before=true
bean.before=true
gate.before=ON
property.after=false
bean.after=true
gate.after=OFF
~~~

Giải thích:

1. Trước khi Spring xét condition, tham số dòng lệnh **--demo.feature.enabled=true** có hiệu lực và cho phép đăng ký FeatureClient.
2. Sau refresh, runner đổi Environment thành false và RuntimeGate cho OFF.
3. **FeatureClient vẫn tồn tại.** Spring không tự gỡ bean vì Environment bị thay đổi sau khi bean definition đã được xử lý.

### 4.11. Kết quả đối chiếu

| Quan sát | Context A: startup false | Context B: startup true |
| --- | --- | --- |
| Property lúc Spring chọn bean | false | true |
| FeatureClient được đăng ký | Không | Có |
| Property sau thay đổi in-memory | true | false |
| FeatureClient sau thay đổi | Vẫn không có | Vẫn có |
| RuntimeGate.state() sau thay đổi | ON | OFF |
| Condition tự chạy lại sau lời gọi state()? | Không | Không |

Các output dự kiến ở trên là các dòng do code ứng dụng in, không tính những dòng có thể được môi trường Java/Maven hoặc agent bên ngoài bổ sung. Hai lần chạy tạo **hai ApplicationContext khác nhau**, không phải một context tự refresh bằng một property toggle.

## 5. Vì sao condition không giống một runtime feature flag?

### 5.1. Condition định hình bean graph

Annotation điều kiện rất phù hợp để quyết định:

- Có tạo mặc định một DataSource, Client, CacheManager hay không.
- Có áp dụng cấu hình servlet/reactive dựa trên classpath và loại ứng dụng không.
- Có nhường bean mặc định cho cấu hình người dùng không.
- Có kích hoạt một tích hợp thư viện khi property startup cho phép không.

Những lựa chọn này thuộc **wiring**, tức cách container được cấu thành.

### 5.2. Runtime flag điều khiển hành vi trên một bean đã tồn tại

Một ứng dụng cần bật/tắt hành vi ngay giữa hai HTTP requests có thể đặt logic trong đường thực thi:

~~~java
public String process() {
    if (!environment.getProperty(
            "demo.feature.enabled", Boolean.class, false)) {
        return "SKIPPED";
    }
    return "PROCESSED";
}
~~~

Đây là snippet minh họa method trong bean có field **environment**, chưa phải một class chạy độc lập. Method chủ động đọc giá trị mới mỗi lần được gọi. Nó **không** thêm/gỡ definition của bean chứa method.

Nếu môi trường dùng feature flag service riêng, có thể đọc snapshot, subscribe update hoặc cache theo contract của dịch vụ đó. Nhưng độ trễ cập nhật, tính nhất quán giữa các instance và concurrency phải được thiết kế chủ động.

### 5.3. Runtime switch nhỏ dùng AtomicBoolean

Một ví dụ Java độc lập về state (chưa có main method):

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeSwitch {
    private final AtomicBoolean enabled = new AtomicBoolean(false);

    public void setEnabled(boolean next) {
        enabled.set(next);
    }

    public String handle() {
        return enabled.get() ? "RUN" : "SKIP";
    }
}
~~~

**AtomicBoolean** cho phép các thread đọc/ghi flag một cách có quy tắc bộ nhớ rõ ràng trong JVM, nhưng thay đổi nó cũng không tự làm Spring đăng ký hay hủy bean. Đây là logic runtime do ứng dụng sở hữu.

**Cảnh báo:** runtime flag OFF không nhất thiết stop connection pool, background thread, scheduled task hay resource mà một bean đã tạo. Nếu cần ngắt subsystem thực sự, phải có lifecycle API riêng, timeout, cleanup và kiểm thử đồng thời.

## 6. Những trường hợp dễ hiểu nhầm

### 6.1. @Lazy không làm condition tự động

~~~java
@Bean
@Lazy
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
FeatureClient lazyFeatureClient() {
    return () -> "lazy";
}
~~~

Đoạn này là snippet, không phải file độc lập. **@Lazy** có thể hoãn việc tạo bean instance cho đến khi cần. Nhưng **BeanDefinition** của lazyFeatureClient đã được quyết định trong quá trình xây context. Nếu property true khi quyết định definition rồi sau đó false trước khi bean được yêu cầu, lazy bean vẫn có thể được tạo theo definition đã đăng ký. Nếu definition bị bỏ qua ngay từ đầu, property true sau startup không tự bổ sung nó.

### 6.2. Prototype không đánh giá lại condition ở mỗi getBean

~~~java
@Bean
@Scope("prototype")
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
FeatureClient newClient() {
    return () -> "prototype";
}
~~~

Đây là snippet minh họa. Scope prototype thay đổi **số lần tạo instance** từ bean definition đã tồn tại. Nó không biến @ConditionalOnProperty thành một condition được xét lại ở từng getBean.

### 6.3. @Profile cũng không tự cập nhật bean graph

**@Profile("dev")** là một điều kiện lựa chọn configuration/bean dựa trên active profiles khi Spring xây context. Đổi danh sách active profiles sau refresh không tự tạo hoặc xóa các bean có @Profile tương ứng. Khi muốn cấu trúc bean khác theo profile, nên khởi tạo context mới với profile đúng ngay từ đầu.

### 6.4. @ConditionalOnMissingBean không phải listener của registry

Nếu lúc xử lý auto-configuration đã có bean của người dùng, default có @ConditionalOnMissingBean sẽ không được đăng ký. Việc sau đó một bean người dùng bị hủy hay bạn thao tác registry động không làm Spring tự tái tạo bean mặc định bị bỏ qua. Các thao tác registry runtime là một cơ chế nâng cao khác, cần quản lý lifecycle/dependencies cẩn thận.

### 6.5. @Value và @ConfigurationProperties không mặc nhiên đọc lại mỗi call

**@Value** thường được resolve/inject lúc Spring tạo bean. Một field được inject không tự lookup Environment ở từng lời gọi getter của bạn.

**@ConfigurationProperties** thường được bind vào object ở giai đoạn khởi tạo. Sau đó việc sửa file hoặc property source không mặc nhiên rebind object theo mỗi lần method được gọi. Nếu muốn runtime rebinding, cần một cơ chế được thiết kế/bổ sung, không thể suy từ annotation binding đơn thuần.

### 6.6. Sửa System properties có thể không ghi đè nguồn đang được ưu tiên

Lệnh Java **System.setProperty** có thể thay đổi một property source, nhưng Environment kết hợp nhiều nguồn theo thứ tự ưu tiên. Nếu một nguồn có độ ưu tiên cao hơn vẫn giữ giá trị cũ, **Environment.getProperty** chưa chắc đã phản ánh system property vừa thay.

Ví dụ runnable chủ động dùng **addFirst(MapPropertySource)** để đảm bảo lần đọc sau thấy giá trị bị đảo. Dù đọc được mới, cấu trúc bean graph vẫn không tự đổi.

## 7. Restart, refresh và hệ thống có nhiều instance

### 7.1. Tạo context mới thì condition được đánh giá cho context mới

Để thay đổi tập bean một cách dễ suy luận, dùng **khởi động lại ứng dụng** hoặc **tạo một ApplicationContext mới** với Environment đã thiết lập đúng. Khi đó Spring phân tích cấu hình và đánh giá condition cho một lượt khởi tạo mới.

Không nên gọi **ConfigurableApplicationContext.refresh()** tùy tiện trên một Boot context đang hoạt động và giả định nó là thao tác “rebuild bean graph” an toàn. Một số loại context không hỗ trợ refresh nhiều lần theo cách đó; các dependency đang chạy còn cần cleanup và rollout.

### 7.2. Spring Cloud @RefreshScope là cơ chế khác

Một ứng dụng có Spring Cloud phù hợp có thể dùng **@RefreshScope** và cơ chế refresh để làm mới một số bean hoặc giá trị được quản lý. Nhưng:

- Chức năng này **không được bật mặc định** chỉ bằng Spring Boot starter cơ bản.
- Refresh một nhóm bean không tương đương với việc **mọi @ConditionalOnProperty và mọi auto-configuration được đăng ký/gỡ lại** như khởi động context mới.
- Phải xem version, contract, endpoint security, lifecycle và kiểm thử cụ thể.

Do đó không suy luận “có @RefreshScope ở đâu đó” thành “mọi condition là live switch cho mỗi request”.

### 7.3. Nhiều pod/process là nhiều context

Nếu một dịch vụ có nhiều instance, mỗi JVM có ApplicationContext riêng. Thay property hoặc runtime flag trong một tiến trình không tự phân phối sang tiến trình khác. Hệ thống feature flag thực tế cần cơ chế phát hành/đồng bộ và xác định mức nhất quán. Nếu thay đổi bean graph cần restart, triển khai rolling restart có kiểm soát thường dễ quản trị hơn một nỗ lực sửa registry động.

## 8. Chẩn đoán: phân biệt property hiện tại với kết quả startup

### 8.1. Condition Evaluation Report

Với project ví dụ, có thể bật log chẩn đoán bằng:

~~~bash
java -jar target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

Tìm **FeatureAutoConfiguration** và **featureClient**. Khi startup với property false, điều kiện @Bean là negative match; khi startup true, điều kiện có thể positive match. Output report thay đổi tùy version và logging.

**Quan trọng:** Condition Evaluation Report mô tả kết quả các lần condition được đánh giá khi xây cấu hình. Nó **không phải** bảng live truth luôn đồng bộ với property hiện tại nếu Environment đã bị đổi sau refresh.

Khi dùng Actuator và cấu hình exposure/security phù hợp, **/actuator/conditions** và **/actuator/beans** giúp quan sát condition và bean hiện được container nhận biết. Những endpoint này không tự kích hoạt re-evaluation của tất cả bean definitions.

### 8.2. Quan sát BeanDefinition và Bean instance

- **BeanFactory.containsBeanDefinition(name)** hỏi về definition cục bộ theo tên.
- **ApplicationContext.containsBean(name)** hỏi container nhận biết bean theo tên hay không, có thể khác câu hỏi definition cục bộ trong một số trường hợp.
- **ObjectProvider.getIfAvailable()** có thể lấy bean nếu định nghĩa tồn tại; đôi khi thao tác lấy bean khởi tạo một instance lazy.
- **Condition report** giúp giải thích vì sao nhánh cấu hình được chọn hoặc bỏ qua.
- **BeanCreationException** và stack trace giúp tìm lỗi tạo instance sau khi definition đã được chấp nhận.

Không đồng nhất những phép kiểm tra này khi debug.

### 8.3. ApplicationContextRunner để kiểm thử điều kiện

Đối với code auto-configuration của thư viện, **ApplicationContextRunner** từ spring-boot-test là công cụ hữu ích để tạo các context riêng biệt với property khác nhau. Bạn có thể kiểm thử hai trường hợp startup true và startup false, kiểm tra bean có/vắng đúng ý định.

Ví dụ ý tưởng, **không phải file test độc lập**:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(FeatureAutoConfiguration.class))
    .withPropertyValues("demo.feature.enabled=false")
    .run(context ->
        assertThat(context).doesNotHaveBean(FeatureClient.class));
~~~

Muốn chạy ví dụ test thật, cần dependency **spring-boot-starter-test** ở test scope, các import và JUnit/test class đầy đủ. Điều đáng học là **mỗi lần runner xây một context mới**, chứ không phải sửa property trên một context cũ rồi tự thêm bean.

## 9. Các hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “@ConditionalOnProperty kiểm tra mỗi lần gọi service.” | Điều kiện quyết định registration trong quá trình xử lý cấu hình. |
| “Đổi Environment thành true làm bean bị bỏ qua xuất hiện.” | Environment có thể đổi; bean graph không tự tái tạo. |
| “Đổi property thành false sẽ tự hủy singleton.” | Singleton đã đăng ký không tự biến mất vì giá trị property đổi. |
| “Spring Boot watch application.properties và rebuild beans mặc định.” | Không có cơ chế mặc định như vậy. |
| “@Lazy sẽ kiểm tra @Conditional khi tạo instance.” | Lazy hoãn instance; definition đã được quyết định. |
| “Prototype là condition chạy theo mỗi getBean.” | Prototype tạo instance mới từ definition có sẵn. |
| “Thêm @Profile sau refresh sẽ kích hoạt bean.” | Profile conditions thuộc quá trình xây context. |
| “@ConfigurationProperties tự rebind mọi lúc.” | Binding không tự lặp lại mỗi business call. |
| “@Value là Environment lookup liên tục.” | Giá trị thường được inject trong quá trình khởi tạo. |
| “@RefreshScope có nghĩa mọi condition của Boot là live.” | Đây là cơ chế mở rộng, không đồng nhất với re-evaluate toàn bộ auto-configuration. |
| “Condition report hiện tại chắc chắn dùng property runtime mới.” | Phải phân biệt thời điểm evaluation với thời điểm quan sát. |
| “Runtime flag OFF tự giải phóng resource.” | Hành vi xử lý và lifecycle resource là hai trách nhiệm riêng. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Startup với **demo.feature.enabled=false**; sau refresh thêm một property source với true. FeatureClient có tự xuất hiện không?

**Đáp án:** Không. BeanDefinition của featureClient đã bị bỏ qua khi condition không đạt. Environment đổi sau đó không kích hoạt đăng ký lại tự động.

**Câu 2.** Startup với property true; sau refresh đổi false. FeatureClient có tự bị gỡ không?

**Đáp án:** Không. Bean đã được đăng ký vẫn tồn tại, trừ khi chương trình dùng một cơ chế lifecycle/registry riêng.

**Câu 3.** Vì sao project in **property.after=true** và **bean.after=false** trong cùng một lần chạy?

**Đáp án:** Property mới được đưa vào Environment sau khi context refresh, nhưng Spring không xét lại condition để tạo bean đã bị bỏ qua.

**Câu 4.** Vì sao **gate.after=ON** nhưng FeatureClient chưa có?

**Đáp án:** RuntimeGate chủ động đọc Environment ở từng lời gọi. Bean FeatureClient được quyết định bằng annotation condition lúc container được xây.

**Câu 5.** Nếu dùng @Lazy trên FeatureClient, sau startup property đổi thành false trước lần lấy bean đầu tiên, @ConditionalOnProperty có chạy lại không?

**Đáp án:** Không. @Lazy chỉ thay thời điểm tạo instance, không làm condition trở thành runtime switch.

**Câu 6.** Prototype được yêu cầu hai lần có tạo hai instance không? Condition có tự chạy lại ở lần thứ hai không?

**Đáp án:** Prototype thường tạo một instance mới cho mỗi lần container được yêu cầu, nhưng điều kiện đăng ký bean definition không tự chạy lại theo từng lần getBean.

**Câu 7.** Muốn thay đổi hành vi cho request kế tiếp, dùng gì?

**Đáp án:** Có thể dùng một runtime gate/feature flag được chủ động đọc trong đường xử lý. Nếu cần tạo/hủy resource thì phải thiết kế thêm lifecycle manager, không chỉ điều kiện đăng ký bean.

**Câu 8.** Muốn thay đổi tập auto-configured beans theo property mà không xây cơ chế refresh riêng thì cách đơn giản nhất là gì?

**Đáp án:** Khởi động lại ứng dụng hoặc tạo context mới với property được thiết lập trước khi context xây dựng.

## 11. Checklist áp dụng vào dự án

Khi dùng một condition hoặc feature toggle, hãy hỏi:

1. **Quyết định ở startup hay runtime?** Startup wiring dùng @Conditional; per-call behavior dùng runtime check.
2. **Có thay đổi bean graph hay chỉ thay đổi đường chạy method?** Hai nhu cầu khác nhau.
3. **Nguồn cấu hình cập nhật bằng cách nào?** Sửa file, remote config, MapPropertySource, flag service có cơ chế riêng.
4. **Có yêu cầu đồng bộ nhiều instance không?** Một JVM không đại diện toàn cluster.
5. **Có cần stop thread/connection/job không?** Runtime flag OFF chưa đủ bảo đảm cleanup.
6. **Đã test cả context startup true và false chưa?** Nên tạo context riêng cho từng trường hợp.
7. **Đang quan sát property, condition report, BeanDefinition hay instance?** Mỗi phép đo nói về một tầng riêng.

### Tổng kết

**@ConditionalOnProperty và các condition tương tự quyết định cấu trúc Spring ApplicationContext khi Spring phân tích/đăng ký cấu hình, không phải công tắc tự cập nhật theo từng lời gọi method.** Một Environment có thể được thay đổi có chủ đích sau startup và code nghiệp vụ chủ động đọc lại nó có thể cho kết quả mới. Nhưng điều đó **không tự thêm hoặc gỡ bean definitions đã được lựa chọn ở giai đoạn xây context**.

Dùng condition để chọn bean/configuration khi khởi động; dùng runtime feature flag hoặc lifecycle/update mechanism chuyên biệt khi mục tiêu là thay đổi hành vi của ứng dụng đang chạy.

### Tài liệu tham khảo

- Spring Framework, *Using the @Conditional Annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/conditional.html
- Spring Framework, API **Condition**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Condition.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, API **@ConditionalOnProperty**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
