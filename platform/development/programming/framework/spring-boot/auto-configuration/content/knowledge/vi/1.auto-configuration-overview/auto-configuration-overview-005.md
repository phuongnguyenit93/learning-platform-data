# Từ danh sách cấu hình ứng viên đến tập bean thực sự có trong ứng dụng

## 1. Bức tranh tổng thể: ba tập hợp khác nhau

Khi Spring Boot khởi động, việc một lớp có tên trong danh sách *auto-configuration* không có nghĩa tất cả bean được khai báo trong lớp đó sẽ xuất hiện. Cần tách ba câu hỏi:

1. **Ứng viên:** những lớp auto-configuration nào được tìm thấy trên classpath và được đưa vào danh sách xem xét?
2. **Cấu hình đủ điều kiện:** sau các bước loại trừ, sắp xếp và đánh giá `@Conditional`, cấu hình hay phương thức `@Bean` nào được phép đóng góp định nghĩa bean?
3. **Bean thực tế:** sau quá trình đăng ký định nghĩa bean, xử lý phụ thuộc và khởi tạo theo vòng đời, `ApplicationContext` đang có những bean nào, thuộc kiểu nào và tên gì?

Luồng khái niệm:

~~~text
@SpringBootApplication (bao gồm @EnableAutoConfiguration)
    |
    v
Tìm các AutoConfiguration.imports trên classpath
    |
    v
Danh sách lớp ứng viên -> exclusions -> bộ lọc/điều kiện sớm -> sắp xếp
    |
    v
Xử lý các lớp cấu hình được chọn và điều kiện của chúng
    |
    v
Đăng ký các BeanDefinition đủ điều kiện
    |                         ^
    |                         |
    +--- quan sát bean người dùng đã tự định nghĩa
    |
    v
Spring tạo các bean cần thiết, tiêm phụ thuộc, áp dụng vòng đời
    |
    v
ApplicationContext: tập bean có thể tra cứu được
~~~

Đây là sơ đồ học tập, không phải khẳng định mỗi mũi tên tương ứng một thao tác đơn lẻ. Một số điều kiện được đánh giá ở các pha khác nhau của quá trình xử lý cấu hình. Các định nghĩa bean có thể tồn tại trước khi đối tượng bean được khởi tạo.

**Điểm cốt lõi:** `candidate != configuration accepted != BeanDefinition registered != bean instance instantiated`. Một class auto-configuration có thể được tìm thấy nhưng không được áp dụng; một cấu hình được áp dụng cũng có thể không đóng góp bean nào; một định nghĩa bean có thể đã đăng ký nhưng chưa tạo instance do `@Lazy` hoặc phạm vi `prototype`.

## 2. Ứng viên được tìm thấy như thế nào?

### Điểm kích hoạt

`@SpringBootApplication` kết hợp `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Phần tự cấu hình được kích hoạt bởi `@EnableAutoConfiguration`; `@ComponentScan` là cơ chế khác, dùng tìm các thành phần do ứng dụng khai báo trong phạm vi quét. Không nên đồng nhất hai cơ chế.

Trong Spring Boot 3.x, ứng viên auto-configuration được liệt kê bằng tài nguyên có đường dẫn chính xác:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng hợp lệ là tên lớp đầy đủ, ví dụ:

~~~text
com.example.feature.autoconfigure.FeatureAutoConfiguration
com.example.feature.autoconfigure.FeatureMetricsAutoConfiguration
~~~

Các thư viện hoặc starter có thể đóng gói tài nguyên này trong JAR. Spring Boot tìm các tài nguyên tương ứng trên classpath và lấy danh sách lớp qua cơ chế nhập ứng viên. Lớp được chú thích `@AutoConfiguration` (bản chất cũng là cấu hình Spring) chỉ trở thành **ứng viên** khi được khai báo đúng trong file imports; thêm một dependency không bảo đảm mọi cấu hình hoặc bean trong đó sẽ được dùng.

Lưu ý với Spring Boot 3.x: `spring.factories` vẫn có một số vai trò SPI khác, nhưng đường khai báo lớp auto-configuration kiểu Boot 3 là `AutoConfiguration.imports`. Không dùng mô hình đăng ký auto-configuration đời cũ làm quy tắc cho ví dụ này.

### Ứng viên không đồng nghĩa với component scan

Lớp auto-configuration của thư viện nên đặt ở gói riêng, nằm ngoài phạm vi `@ComponentScan` của ứng dụng. Nếu lớp ấy vừa bị quét như `@Configuration` thông thường vừa được nhập tự động, người học sẽ khó phân biệt thứ tự và cơ chế áp dụng. Auto-configuration được thiết kế để nhập bằng file imports; khi cần cấu hình bổ trợ, hãy dùng `@Import` có chủ đích.

## 3. Từ ứng viên đến cấu hình đủ điều kiện

Có ba nhóm quyết định quan trọng.

**(a) Loại trừ chủ động.** Ứng dụng có thể loại trừ một auto-configuration cụ thể bằng `@SpringBootApplication(exclude = ...)`, `@EnableAutoConfiguration(exclude = ...)` hoặc thuộc tính `spring.autoconfigure.exclude`. Loại trừ một lớp không gỡ JAR khỏi classpath và không xóa các bean do nguồn cấu hình khác tạo.

**(b) Kiểm tra điều kiện.** Các điều kiện khai báo trên lớp cấu hình có thể khiến toàn bộ lớp không được xử lý như một cấu hình phù hợp. Các điều kiện trên phương thức `@Bean` lại có thể chỉ ngăn định nghĩa bean từ phương thức đó, trong khi các phương thức khác vẫn đủ điều kiện.

**(c) Sắp xếp thứ tự.** `@AutoConfiguration(before = ..., after = ...)`, `@AutoConfigureBefore`, `@AutoConfigureAfter` và `@AutoConfigureOrder` điều khiển thứ tự xử lý auto-configuration nhằm đáp ứng quan hệ phụ thuộc giữa các **định nghĩa**. Chúng không cam kết thứ tự tạo đối tượng bean lúc chạy; việc khởi tạo phụ thuộc vào dependency graph và các quan hệ như `@DependsOn`.

Các điều kiện có thể được xử lý sớm khi lọc ứng viên, hoặc khi Spring phân tích/đăng ký cấu hình và phương thức bean. Vì thế không nên tưởng tượng hệ thống chỉ chạy một vòng kiểm tra duy nhất rồi tạo tất cả bean.

### Bảng điều kiện thường gặp

| Điều kiện | Ý nghĩa thực tế | Tình huống điển hình |
| --- | --- | --- |
| `@ConditionalOnClass` / `@ConditionalOnMissingClass` | Có/không có một kiểu trên classpath | Chỉ cấu hình tích hợp khi thư viện liên quan được đưa vào |
| `@ConditionalOnBean` | Đã có bean phù hợp theo kiểu hoặc tên trong phạm vi tìm kiếm | Tạo adapter chỉ khi hạ tầng cần thiết đã tồn tại |
| `@ConditionalOnMissingBean` | Chưa thấy bean phù hợp tại thời điểm đánh giá | Đưa ra bean mặc định nếu ứng dụng chưa khai báo |
| `@ConditionalOnProperty` | Giá trị thuộc tính trong Spring `Environment` thỏa điều kiện | Bật/tắt một cấu hình bằng cờ |
| `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication` | Kiểu môi trường web phù hợp hoặc không phải web | Chỉ thêm hạ tầng Servlet/WebFlux đúng ngữ cảnh |
| `@ConditionalOnResource` | Có tài nguyên được chỉ định | Chỉ cấu hình khi tồn tại tệp/tài nguyên cần thiết |

Đừng suy từ tên annotation rằng điều kiện luôn trả đúng/sai theo một phép tìm kiếm đơn giản: `@ConditionalOnProperty` có tham số `havingValue`, `matchIfMissing`; `@ConditionalOnBean` có thể tìm theo tên/kiểu và phân cấp context; `@ConditionalOnMissingBean` còn phụ thuộc các định nghĩa đã được xử lý tại thời điểm kiểm tra.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.client.RemoteClient")
@ConditionalOnProperty(
    prefix = "feature.remote",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class RemoteFeatureAutoConfiguration {
    // Các @Bean có thể có thêm điều kiện riêng.
}
~~~

Đây là **đoạn minh họa**, chưa phải một chương trình độc lập. `name` ở `@ConditionalOnClass` cho phép nêu tên class bằng chuỗi. Khi phụ thuộc có thể vắng mặt, tránh đặt kiểu tùy chọn trực tiếp vào chữ ký phương thức `@Bean` được JVM nạp quá sớm; tách cấu hình có `@ConditionalOnClass` sang lớp `@Configuration` riêng là một cách an toàn.

## 4. Vì sao bean do người dùng tự khai báo được ưu tiên?

Spring Boot tạo cấu hình mặc định theo nguyên tắc *back off*: nếu ứng dụng đã khai báo bean phù hợp, một bean mặc định có `@ConditionalOnMissingBean` thường sẽ **không đăng ký**. Điều kiện ấy kiểm tra các định nghĩa bean đã biết, không chờ đến lúc tất cả instance được khởi tạo rồi mới quyết định.

Ví dụ về ý nghĩa, giả sử một auto-configuration có:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultPaymentGateway() {
    return new SandboxPaymentGateway();
}
~~~

Nếu ứng dụng đã có bean loại `PaymentGateway` tại thời điểm điều kiện được đánh giá, định nghĩa `defaultPaymentGateway` không được thêm. Khi dùng `@ConditionalOnMissingBean` trong auto-configuration, Spring Boot tổ chức việc xử lý các cấu hình do người dùng khai báo trước, giúp giá trị mặc định nhường chỗ phù hợp.

**Không phải mọi bean cùng tên hoặc cùng kiểu đều tự động ghi đè nhau.** `@ConditionalOnMissingBean(PaymentGateway.class)` kiểm tra theo **kiểu**, còn `@ConditionalOnMissingBean(name = "paymentGateway")` kiểm tra theo **tên**. Quy tắc ghi đè định nghĩa cùng tên là một vấn đề khác; Spring Boot thường không cho phép vô tình ghi đè bean definition.

Một lỗi tinh vi là khai báo `@Bean` với kiểu trả về quá chung, ví dụ `Object` thay vì kiểu nghiệp vụ thực tế. Các điều kiện tìm bean dựa trên thông tin kiểu có sẵn trong định nghĩa, nên chữ ký rõ ràng giúp Spring nhận biết chính xác. Chỉ dùng điều kiện bean trong auto-configuration hoặc nơi hiểu chắc thứ tự xử lý; dùng tùy tiện trong cấu hình ứng dụng thường dẫn tới kết quả phụ thuộc thứ tự.

## 5. Thí nghiệm hoàn chỉnh với Spring Boot 3.3 và Java 17

Mục tiêu: cùng một lớp `GreetingAutoConfiguration` nằm trong danh sách ứng viên nhưng tập bean `GreetingService` cuối cùng thay đổi theo cấu hình ứng dụng. Ví dụ sử dụng Spring Boot 3.3.13, Java 17+, Maven 3.9+.

Cây tệp:

~~~text
auto-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/GreetingService.java
    │       ├── app/DemoApplication.java
    │       └── autoconfig/GreetingAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>demo</groupId>
    <artifactId>auto-demo</artifactId>
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

`spring-boot-starter` cung cấp cơ chế tạo context và logging cơ bản; ví dụ không phải ứng dụng web nên không cần `spring-boot-starter-web`.

### 5.2. `src/main/java/demo/api/GreetingService.java`

~~~java
package demo.api;

public interface GreetingService {
    String source();
}
~~~

### 5.3. `src/main/java/demo/autoconfig/GreetingAutoConfiguration.java`

~~~java
package demo.autoconfig;

import demo.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "demo.auto",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return () -> "auto";
    }
}
~~~

Đọc các điều kiện từ ngoài vào trong: interface `GreetingService` có trên classpath; `demo.auto.enabled` bằng `true` hoặc không được khai báo; và cuối cùng **chưa có** bean `GreetingService` khác. Chỉ khi tất cả điều kiện liên quan được đáp ứng, phương thức mới đăng ký định nghĩa bean mặc định.

### 5.4. `src/main/java/demo/app/DemoApplication.java`

~~~java
package demo.app;

import demo.api.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "custom",
        havingValue = "true"
    )
    GreetingService customGreetingService() {
        return () -> "custom";
    }

    @Bean
    ApplicationRunner inspect(ObjectProvider<GreetingService> provider) {
        return args -> {
            GreetingService service = provider.getIfAvailable();
            System.out.println("origin=" +
                (service == null ? "none" : service.source()));
        };
    }
}
~~~

Lớp chính nằm trong `demo.app` nên component scan thông thường **không quét** gói ngang cấp `demo.autoconfig`. Auto-configuration chỉ được tham gia nhờ file imports bên dưới. Bean người dùng `customGreetingService` xuất hiện khi `demo.custom=true`.

### 5.5. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
demo.autoconfig.GreetingAutoConfiguration
~~~

Đây là bước biến lớp trên thành **ứng viên auto-configuration**. Chỉ viết `@AutoConfiguration` lên Java class mà quên file này thì thí nghiệm không thể chứng minh cơ chế tìm ứng viên.

### 5.6. Chạy và quan sát

Từ thư mục `auto-demo`, chạy lần lượt các lệnh sau (mỗi lần khởi động một tiến trình riêng):

~~~bash
mvn -q spring-boot:run
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.custom=true
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.auto.enabled=false
mvn -q spring-boot:run -Dspring-boot.run.arguments="--demo.custom=true --demo.auto.enabled=false"
~~~

Các dòng **do `System.out.println` của ví dụ in ra** lần lượt là:

~~~text
origin=auto
origin=custom
origin=none
origin=custom
~~~

Ứng dụng còn có thể in banner và log Spring Boot; đây không phải toàn bộ stdout. Diễn giải:

| Trường hợp | Bean tự khai báo | Điều kiện lớp auto-config | Điều kiện missing-bean | Kết quả |
| --- | --- | --- | --- | --- |
| Mặc định | Không | Đạt | Đạt | `defaultGreetingService` được chọn |
| `demo.custom=true` | Có | Đạt | Không đạt | `customGreetingService` được chọn |
| `demo.auto.enabled=false` | Không | Không đạt do property | Không xét phương thức | Không có `GreetingService` |
| Cả custom=true và auto=false | Có | Không đạt | Không xét phương thức | Bean do người dùng khai báo vẫn tồn tại |

Giá trị `origin=none` được in ra vì chương trình sử dụng `ObjectProvider` để tra cứu tùy chọn. Nếu thay bằng constructor injection bắt buộc cho `GreetingService` trong trường hợp không có bean, ứng dụng có thể không khởi động được do thiếu phụ thuộc. Điều đó **không** có nghĩa Spring Boot tự tạo bean chỉ để thỏa mãn mọi injection.

Có thể kiểm tra thêm cơ chế exclusion:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
~~~

Với `demo.custom` không bật, dòng quan sát là `origin=none`. Lớp ứng viên vẫn nằm trong file imports, nhưng đã bị chủ động loại trừ.

## 6. Quan sát kết quả thật: đừng chỉ nhìn file imports

### Điều kiện nào đạt, điều kiện nào không?

Khởi chạy ứng dụng với `--debug` để Spring Boot in *Condition Evaluation Report* trong log. Ví dụ:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments="--debug --demo.custom=true"
~~~

Trong báo cáo, tìm tên `GreetingAutoConfiguration` và các điều kiện liên quan. Báo cáo có phần điều kiện khớp và không khớp, nhưng **không phải** một danh sách cuối cùng của mọi instance bean đã được tạo.

Nếu ứng dụng có `spring-boot-starter-actuator` và cấu hình cho phép truy cập endpoint tương ứng, `/actuator/conditions` cung cấp thông tin đánh giá điều kiện; `/actuator/beans` cung cấp thông tin bean trong context. Endpoint và mức độ được expose phụ thuộc cấu hình quản trị; không suy rằng tất cả endpoint đều công khai mặc định.

### Bean nào thực sự có trong context?

Có thể dùng đoạn sau bên trong một `ApplicationRunner` hoặc mã kiểm tra đang có `ApplicationContext`:

~~~java
String[] names = context.getBeanNamesForType(GreetingService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

Đây là **đoạn mã minh họa cần biến `context` kiểu `ApplicationContext`**, không phải một file Java chạy độc lập. Trong thí nghiệm, kết quả dự kiến là `[defaultGreetingService]`, `[customGreetingService]` hoặc `[]` theo từng trường hợp. Nếu cần xem định nghĩa đăng ký thay vì chỉ tên theo kiểu, dùng API `getBeanDefinitionNames()` và `getBeanFactory()` phù hợp với loại context.

Phân biệt ba loại bằng chứng:

- **Classpath/imports:** lớp có thể được xét như một ứng viên.
- **Condition Evaluation Report:** vì sao cấu hình hoặc phương thức bean khớp/không khớp tại thời điểm đánh giá.
- **ApplicationContext / bean definitions:** trạng thái bean được đăng ký và có thể tra cứu trong context của tiến trình cụ thể.

Khi muốn xác định nguyên nhân thiếu bean, kết hợp cả ba. Chỉ kiểm tra JAR có class không đủ để kết luận bean xuất hiện.

## 7. Các yếu tố làm thay đổi tập bean cuối cùng

### Dependency và môi trường chạy

Thêm `spring-boot-starter-jdbc` và driver phù hợp có thể khiến các auto-configuration liên quan JDBC trở thành ứng viên có cơ hội khớp điều kiện classpath; đồng thời còn phải xét cấu hình kết nối và các bean sẵn có. Thêm starter, thay classpath, thay runtime Servlet/WebFlux hay thiếu tài nguyên đều có thể thay đổi kết quả mà không cần sửa lớp auto-configuration.

### Cấu hình ngoài mã nguồn

Thuộc tính được tổng hợp vào Spring `Environment` từ nhiều nguồn, ví dụ `application.yml`, biến môi trường hoặc tham số dòng lệnh. Một property như `feature.enabled` có thể khiến điều kiện `@ConditionalOnProperty` đổi kết quả. `@ConfigurationProperties` là cơ chế gắn cấu hình ngoài vào đối tượng; bản thân việc khai báo class `@ConfigurationProperties` không đồng nghĩa auto-configuration nhất định tạo bean đó. Để có bean cấu hình, cần cơ chế đăng ký phù hợp, chẳng hạn `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.

### Các bean người dùng và quan hệ phụ thuộc

Một cấu hình tự động có thể tạo bean hạ tầng A chỉ khi đã tồn tại bean B, hoặc bỏ bean mặc định A nếu ứng dụng cung cấp A. Kết quả phụ thuộc cả **định nghĩa của người dùng** lẫn các auto-configuration được xử lý trước. Thứ tự đăng ký quan trọng với điều kiện về sự tồn tại của bean, vì điều kiện nhìn thấy những định nghĩa đã có tại thời điểm đánh giá.

### Khởi tạo và vòng đời

Từ thời điểm có `BeanDefinition` đến lúc có instance còn có các bước tạo đối tượng, tiêm phụ thuộc, xử lý hậu kỳ và khởi tạo. Singleton mặc định thường được tạo trong quá trình refresh context; lazy singleton có thể trì hoãn đến khi cần; prototype thường được tạo mỗi lần yêu cầu. Nếu lỗi khi tạo bean hoặc thiếu phụ thuộc bắt buộc, ứng dụng có thể khởi động thất bại. Do đó, câu “bean đã được đăng ký” chính xác hơn “bean chắc chắn đã được khởi tạo và dùng được”.

## 8. Tình huống phân tích: vì sao có hoặc không có DataSource?

Một câu trả lời thiếu chính xác là “có starter JDBC thì chắc chắn có `DataSource`”. Cách lần theo cơ chế:

1. Kiểm tra các dependency JDBC và driver trong classpath. Xác định có các điều kiện nền tảng cần thiết không.
2. Xác định các auto-configuration liên quan, ví dụ `DataSourceAutoConfiguration`, có nằm trong danh sách ứng viên, bị exclude hay không.
3. Đọc điều kiện class-level và điều kiện trên các cấu hình lồng/phương thức `@Bean`. Những cấu hình này có thể cần class, property, môi trường và các bean liên quan phù hợp.
4. Kiểm tra ứng dụng đã tự định nghĩa `DataSource` hoặc cấu hình kết nối chưa. Một bean người dùng có thể khiến bean mặc định nhường chỗ.
5. Dùng Condition Evaluation Report để xem lý do khớp/không khớp. Dùng `ApplicationContext` hoặc actuator `beans` để xác nhận định nghĩa/bean cuối cùng.
6. Nếu startup lỗi, xem exception gốc: sai thông tin kết nối và thiếu bean là hai nhóm nguyên nhân khác nhau.

Trong thực tế, mô hình này áp dụng tương tự cho Jackson, transaction manager, security filter chain và nhiều hạ tầng khác; từng auto-configuration vẫn có điều kiện cụ thể riêng, nên không áp một quy tắc chung cho tất cả.

## 9. Những nhầm lẫn phổ biến và cách sửa

| Nhầm lẫn | Sự thật cần kiểm tra |
| --- | --- |
| “Nằm trong `AutoConfiguration.imports` thì chắc chắn có bean.” | Imports chỉ xác định ứng viên; còn exclude, điều kiện ở lớp và phương thức, rồi đăng ký bean. |
| “Chỉ cần thêm starter là mọi thứ hoạt động.” | Starter bổ sung dependency; bean còn phụ thuộc classpath, môi trường, property và bean đã có. |
| “`@ComponentScan` tìm mọi auto-configuration.” | Component scan và cơ chế nhập auto-configuration là hai nguồn khác nhau. |
| “`@ConditionalOnMissingBean` kiểm tra lúc bean chạy.” | Điều kiện đánh giá từ thông tin bean đã được xử lý, trước khi quyết định đăng ký bean mặc định. |
| “Order của auto-config quyết định thứ tự constructor bean.” | Order ảnh hưởng thứ tự đăng ký định nghĩa; phụ thuộc và vòng đời quyết định khởi tạo. |
| “Một bean đã đăng ký luôn có instance ngay.” | `@Lazy`, `prototype` và các tình huống tạo bean làm hai thời điểm khác nhau. |
| “Cấu hình bị loại trừ thì mọi bean cùng loại biến mất.” | Bean do người dùng hoặc cấu hình khác tạo vẫn có thể tồn tại. |
| “Debug report là danh sách bean cuối cùng.” | Báo cáo cho lý do condition; tra cứu context để biết bean hiện có. |
| “Không thấy bean thì phải bật override definition.” | Trước hết kiểm tra điều kiện, package scan, imports, types, properties và startup errors. |

### Cách phân tích có hệ thống khi bean không xuất hiện

Bắt đầu từ **bean muốn tìm**, truy ngược đến **phương thức `@Bean` hoặc component tạo bean**, rồi đến **lớp cấu hình sở hữu**, cuối cùng mới đến **imports và dependency**. Tại từng bước hỏi: bean có được khai báo không, cấu hình có được nạp không, condition nào loại nó, có bean tự khai báo làm mặc định nhường chỗ không, và khởi tạo có lỗi không?

Không kết luận chỉ bằng một thông báo “No qualifying bean” vì thông báo này nói về điểm injection không được thỏa mãn, chưa cho biết nguyên nhân gốc.

## 10. Bài tập tự kiểm chứng

1. Trong ví dụ, xóa dòng tên lớp khỏi `AutoConfiguration.imports` rồi chạy mặc định. Dự đoán và kiểm tra `origin`. Giải thích vì sao việc Java class vẫn nằm trong project không đủ.
2. Thử `--demo.custom=true` và `--demo.auto.enabled=false` đồng thời. Bean nào chịu sự chi phối của từng property?
3. Thay `@ConditionalOnMissingBean(GreetingService.class)` bằng điều kiện kiểm tra tên `defaultGreetingService`. Dự đoán điều gì xảy ra khi ứng dụng có bean tên `customGreetingService` cùng kiểu; giải thích vì sao có thể sinh hai bean `GreetingService` và tác động lên tra cứu theo kiểu đơn.
4. Thử thêm `@Lazy` cho bean mặc định, rồi phân biệt việc bean definition tồn tại với thời điểm tạo instance. Chú ý: đoạn `ApplicationRunner` hiện tại yêu cầu bean, nên có thể kích hoạt lazy bean.
5. Bật `--debug` trong từng tình huống và ghi lại bằng chứng từ Condition Evaluation Report, sau đó đối chiếu với bean names trong context.

**Tiêu chí tự đánh giá:** giải thích được vì sao cùng một file imports cho ra các tập bean khác nhau; chỉ đúng điều kiện khiến bean mặc định nhường chỗ; không nhầm *tìm ứng viên*, *đăng ký định nghĩa* và *khởi tạo bean*.

## 11. Checklist vận dụng

Khi kiểm tra một bean liên quan auto-configuration, đi theo chuỗi: **đúng classpath → imports → exclusions → thứ tự và điều kiện cấu hình → điều kiện của `@Bean` → định nghĩa do người dùng cung cấp → đăng ký BeanDefinition → khởi tạo và tra cứu trong ApplicationContext**. Có thể rút ngắn các bước đã xác nhận, nhưng không nhảy từ “có thư viện” sang “chắc có bean”.

Tài liệu tham khảo chính thức (Spring Boot 3.3):
- [Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Maven plugin và starter parent](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
