# Nạp cấu hình XML và tài nguyên classpath

Spring Framework có thể tạo và cấu hình ApplicationContext từ nhiều nguồn khác nhau. Bên cạnh Java configuration và annotation, Spring vẫn hỗ trợ XML bean definition để khai báo bean, dependency, component scan, property placeholder và các cấu hình hạ tầng. Những file XML này thường được đặt trên classpath để ứng dụng và test có thể nạp chúng theo cùng một quy tắc, bất kể đang chạy từ IDE, Gradle hay một gói JAR.

Để nạp cấu hình XML đúng cách, cần hiểu ba phần liên quan:

1. **ApplicationContext** quản lý bean và cung cấp cơ chế nạp tài nguyên.
2. **XML bean definition** mô tả bean, dependency và các cấu hình Spring.
3. **Resource abstraction** cho phép tham chiếu tài nguyên qua classpath, filesystem, URL hoặc ServletContext.

Trong kiểm thử Spring, các khái niệm này thường xuất hiện khi test cần khởi tạo context từ một file XML, nạp fixture trong src/test/resources hoặc kiểm tra một cấu hình XML cũ đang được tích hợp với Java configuration.

## 1. ApplicationContext và cơ chế nạp tài nguyên

ApplicationContext là container cấp cao của Spring. Ngoài chức năng tạo và quản lý bean, nó còn cung cấp các dịch vụ như đọc message, phát application event và truy cập tài nguyên. ApplicationContext có khả năng hoạt động như một ResourceLoader, vì vậy code có thể yêu cầu container tìm một Resource bằng location string.

Ví dụ:

~~~java
Resource resource = applicationContext.getResource(
    "classpath:/config/application-context.xml"
);
~~~

Resource là abstraction đại diện cho một nguồn dữ liệu. Nó có thể là file trên classpath, file hệ thống, URL hoặc tài nguyên trong web application. Code có thể mở InputStream để đọc nội dung mà không cần biết nguồn đó được lưu ở đâu.

Các API chính liên quan:

| API | Vai trò |
|---|---|
| ApplicationContext | Quản lý bean và cung cấp dịch vụ container |
| ResourceLoader | Chuyển location string thành Resource |
| Resource | Đại diện cho một tài nguyên có thể đọc |
| ResourcePatternResolver | Tìm một hoặc nhiều tài nguyên theo pattern |
| XmlBeanDefinitionReader | Đọc XML và đăng ký bean definition vào registry |

Spring dùng các abstraction này để tách việc khai báo bean khỏi cách file được lưu trữ. Một file XML có thể được nạp từ classpath trong ứng dụng đóng gói hoặc từ filesystem trong một môi trường triển khai cụ thể.

## 2. Đặt cấu hình XML trên classpath

Trong dự án Java thông thường, tài nguyên của ứng dụng thường nằm trong src/main/resources. Build tool sẽ đưa các file đó vào runtime classpath. Tài nguyên chỉ dùng cho test thường nằm trong src/test/resources và được đưa vào test runtime classpath.

Ví dụ cấu trúc:

~~~text
src/
├── main/
│   └── resources/
│       └── com/example/config/
│           ├── application-context.xml
│           ├── data-access.xml
│           └── application.properties
└── test/
    └── resources/
        └── fixtures/
            ├── expected-product.json
            └── sample-catalog.xml
~~~

Khi file nằm trong src/main/resources/com/example/config/application-context.xml, location trên classpath thường là:

~~~text
com/example/config/application-context.xml
~~~

Có thể dùng prefix classpath: để làm rõ nguồn:

~~~text
classpath:/com/example/config/application-context.xml
~~~

Tên đường dẫn classpath dùng dấu slash làm dấu phân cách. Không ghép đường dẫn bằng dấu phân cách của hệ điều hành như backslash, vì tài nguyên có thể được đọc bên trong JAR và không có đường dẫn filesystem tương ứng.

Không nên dùng đường dẫn tuyệt đối trên máy phát triển như C:/work/project/src/main/resources/... để nạp cấu hình ứng dụng. Đường dẫn đó không tồn tại trong container, CI hoặc máy của thành viên khác. Đặt tài nguyên trên classpath giúp build artifact mang theo file cấu hình và ứng dụng tìm được nó ở runtime.

## 3. Các prefix resource thường gặp

ResourceLoader hiểu một số prefix để xác định loại tài nguyên:

| Prefix | Ý nghĩa | Ví dụ |
|---|---|---|
| classpath: | Tìm một tài nguyên trên classpath | classpath:/config/app.xml |
| classpath*: | Tìm tài nguyên phù hợp trên toàn bộ classpath | classpath*:META-INF/spring/*.xml |
| file: | Tài nguyên trên filesystem | file:/etc/myapp/app.xml |
| https: hoặc URL scheme khác | Tài nguyên từ URL | https://example.test/config.xml |

### 3.1. classpath:

classpath: chỉ một tài nguyên trên classpath. Ví dụ:

~~~java
Resource resource = new ClassPathResource(
    "com/example/config/application-context.xml"
);
~~~

Hoặc:

~~~java
Resource resource = applicationContext.getResource(
    "classpath:/com/example/config/application-context.xml"
);
~~~

ClassPathResource thường được tạo với đường dẫn tương đối từ gốc classpath. Dấu slash đầu đường dẫn có thể được chuẩn hóa, nhưng dùng một quy ước nhất quán giúp tránh nhầm lẫn.

### 3.2. classpath*:

classpath*: được dùng khi cần tìm tất cả tài nguyên phù hợp trên classpath, bao gồm các vị trí khác nhau như thư mục classes và các JAR dependency. Nó thường được phối hợp với ResourcePatternResolver:

~~~java
ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
    "classpath*:META-INF/spring/*.xml"
);
~~~

Pattern có thể chứa ký tự đại diện như * hoặc **. Ví dụ trên tìm các file XML nằm trực tiếp trong thư mục META-INF/spring của những vị trí classpath phù hợp.

classpath*: hữu ích khi nhiều module hoặc thư viện cùng đóng góp một file cấu hình theo quy ước chung. Tuy nhiên, thứ tự tài nguyên được tìm thấy không nên được dùng như một cơ chế ưu tiên cấu hình ngầm. Nếu thứ tự nạp có ý nghĩa, hãy xác định rõ danh sách location hoặc thứ tự import.

### 3.3. file:

file: tham chiếu một đường dẫn filesystem:

~~~java
Resource resource = new FileSystemResource(
    "/etc/myapp/application-context.xml"
);
~~~

Hoặc dùng location string:

~~~java
Resource resource = applicationContext.getResource(
    "file:/etc/myapp/application-context.xml"
);
~~~

File resource phù hợp với cấu hình triển khai được quản lý bên ngoài artifact. Cần bảo đảm file tồn tại, có quyền đọc và đường dẫn được cung cấp qua cấu hình môi trường. Không nên buộc unit test chạy trên một đường dẫn hệ thống cố định.

### 3.4. URL resource

ResourceLoader có thể tạo resource từ URL:

~~~java
Resource remoteConfig = applicationContext.getResource(
    "https://config.example.test/application-context.xml"
);
~~~

Tài nguyên từ xa có thể chịu ảnh hưởng của mạng, xác thực, timeout và khả năng sẵn sàng của server. Không nên để test thông thường tải cấu hình từ một URL công cộng. Nếu cần kiểm tra tích hợp URL, hãy dùng server thử nghiệm có thể điều khiển hoặc fixture cục bộ.

### 3.5. Location không có prefix

Khi location không có prefix, cách diễn giải phụ thuộc ResourceLoader hoặc ApplicationContext implementation. Ví dụ, ClassPathXmlApplicationContext mặc định tìm cấu hình XML trên classpath; FileSystemXmlApplicationContext diễn giải location theo filesystem. Vì vậy, khi code có thể được dùng với nhiều loại context, hãy dùng prefix tường minh như classpath: hoặc file: để tránh phụ thuộc mặc định.

## 4. Nạp XML bằng ClassPathXmlApplicationContext

ClassPathXmlApplicationContext là cách trực tiếp để tạo ApplicationContext từ XML trên classpath. Constructor nhận một hoặc nhiều location. Context sẽ đọc bean definition và hoàn tất quá trình refresh trong constructor thông thường.

Ví dụ:

~~~java
ApplicationContext context =
    new ClassPathXmlApplicationContext(
        "classpath:/com/example/config/application-context.xml"
    );

ProductService productService =
    context.getBean("productService", ProductService.class);
~~~

Có thể truyền nhiều file XML:

~~~java
ApplicationContext context =
    new ClassPathXmlApplicationContext(
        "classpath:/com/example/config/data-access.xml",
        "classpath:/com/example/config/services.xml"
    );
~~~

Các bean được khai báo trong những file này được đăng ký vào cùng context. Nếu nhiều file định nghĩa cùng bean name, kết quả phụ thuộc chính sách override bean definition và cấu hình container. Không nên dựa vào việc một file tình cờ ghi đè file khác; hãy đặt tên bean rõ ràng và quản lý thứ tự nạp có chủ đích.

Với context cần đóng khi kết thúc, giữ reference tới ConfigurableApplicationContext hoặc AbstractApplicationContext để gọi close:

~~~java
try (ClassPathXmlApplicationContext context =
         new ClassPathXmlApplicationContext(
             "classpath:/com/example/config/application-context.xml"
         )) {

    ProductService service =
        context.getBean("productService", ProductService.class);
}
~~~

Đóng context giúp Spring phát callback hủy bean và giải phóng tài nguyên mà bean quản lý. Trong ứng dụng web hoặc ứng dụng Spring Boot, framework thường quản lý vòng đời context; trong ví dụ standalone hoặc test tự tạo context, cần đảm bảo context được đóng.

## 5. Nạp XML bằng FileSystemXmlApplicationContext

FileSystemXmlApplicationContext nạp cấu hình từ filesystem:

~~~java
ApplicationContext context =
    new FileSystemXmlApplicationContext(
        "file:/etc/myapp/application-context.xml"
    );
~~~

Trong môi trường triển khai, cách này hữu ích khi XML được quản lý ngoài ứng dụng và có thể thay đổi mà không đóng gói lại artifact. Đường dẫn tương đối trong FileSystemXmlApplicationContext được diễn giải theo quy tắc filesystem của context và working directory. Để tránh kết quả phụ thuộc working directory, ưu tiên đường dẫn tuyệt đối hoặc truyền location file được cấu hình rõ ràng.

Không dùng FileSystemXmlApplicationContext chỉ vì file XML nằm trong thư mục src/main/resources của project. Khi file được đóng gói vào JAR, nó không còn là file thông thường có thể mở bằng đường dẫn filesystem. Với tài nguyên đóng gói, dùng classpath.

## 6. Đọc XML bằng XmlBeanDefinitionReader

Khi cần kiểm soát quá trình đăng ký bean definition, có thể kết hợp GenericApplicationContext và XmlBeanDefinitionReader. Cách này tách việc đọc XML khỏi việc refresh context:

~~~java
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.beans.factory.xml.XmlBeanDefinitionReader;
import org.springframework.core.io.ClassPathResource;

try (GenericApplicationContext context = new GenericApplicationContext()) {
    XmlBeanDefinitionReader reader =
        new XmlBeanDefinitionReader(context);

    reader.loadBeanDefinitions(
        new ClassPathResource(
            "com/example/config/application-context.xml"
        )
    );

    context.refresh();

    ProductService service =
        context.getBean("productService", ProductService.class);
}
~~~

Quy trình có ba bước:

1. Tạo context và bean definition registry.
2. Dùng XmlBeanDefinitionReader đọc XML, phân tích bean definition và đăng ký vào registry.
3. Gọi refresh để context tạo các bean cần khởi tạo, áp dụng post processor và sẵn sàng phục vụ truy vấn.

Không nên gọi refresh trước khi đăng ký XML, vì những bean definition được nạp sau refresh không tự động tham gia đầy đủ vào quá trình khởi tạo đã hoàn tất. Nếu cần nạp thêm cấu hình, hãy làm theo lifecycle và API của context tương ứng, hoặc tạo context mới với tập cấu hình đầy đủ.

XmlBeanDefinitionReader cũng có thể nạp từ Resource khác:

~~~java
reader.loadBeanDefinitions(
    new FileSystemResource("/etc/myapp/application-context.xml")
);
~~~

Điểm quan trọng là reader nhận Resource; nó không yêu cầu nội dung phải đến từ classpath. Đây là cách phù hợp khi ứng dụng cần chọn nguồn XML dựa trên môi trường.

## 7. Cấu trúc một file Spring XML

Một file bean definition dùng namespace beans của Spring. Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="com.example.service"/>

    <bean id="systemClock" class="java.time.Clock" factory-method="systemUTC"/>

    <bean id="productRepository"
          class="com.example.repository.InMemoryProductRepository"/>

    <bean id="productService"
          class="com.example.service.ProductService">
        <constructor-arg ref="productRepository"/>
        <constructor-arg ref="systemClock"/>
    </bean>
</beans>
~~~

Trong ví dụ:

- component-scan yêu cầu Spring tìm component trong package đã chỉ định.
- systemClock được tạo bằng static factory method systemUTC.
- productRepository được khai báo như một bean.
- productService nhận hai dependency qua constructor injection.

XML bean definition hỗ trợ constructor argument, property injection, factory method, scope, lifecycle method, alias và nhiều cấu hình container khác. Với ứng dụng mới, Java configuration thường dễ refactor và được IDE hỗ trợ tốt hơn; XML vẫn hữu ích khi tích hợp hệ thống cũ, cấu hình được quản lý bên ngoài hoặc cần tách cấu hình khỏi mã Java.

### 7.1. Constructor injection

Có thể khai báo dependency bằng ref:

~~~xml
<bean id="notificationService"
      class="com.example.notification.NotificationService">
    <constructor-arg ref="mailGateway"/>
    <constructor-arg value="support@example.test"/>
</bean>
~~~

ref trỏ tới bean khác trong container; value là giá trị literal hoặc biểu thức placeholder. Constructor injection giúp dependency rõ ràng và thuận tiện cho test vì đối tượng có thể được tạo trực tiếp với dependency giả lập.

### 7.2. Property injection

Nếu bean có setter hoặc property phù hợp, XML có thể dùng property:

~~~xml
<bean id="reportOptions"
      class="com.example.report.ReportOptions">
    <property name="format" value="csv"/>
    <property name="includeHeader" value="true"/>
</bean>
~~~

Không nên dùng property injection chỉ để né một constructor quá dài. Dependency bắt buộc thường nên được biểu đạt bằng constructor; property phù hợp hơn với cấu hình tùy chọn hoặc JavaBean cần được cấu hình sau khi tạo.

### 7.3. Tách XML bằng import

Khi cấu hình lớn, có thể chia thành nhiều file:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <import resource="classpath:/com/example/config/data-access.xml"/>
    <import resource="classpath:/com/example/config/services.xml"/>
</beans>
~~~

Thẻ import cho phép tập hợp các nhóm cấu hình vào một entry point. Có thể dùng đường dẫn tương đối để tham chiếu file cùng vị trí với XML hiện tại; đường dẫn classpath tường minh giúp người đọc nhận ra nguồn tài nguyên và tránh nhầm lẫn khi file được di chuyển.

Nên chia theo trách nhiệm, chẳng hạn data access, integration, services và web. Không nên tạo quá nhiều file nhỏ chỉ chứa một bean nếu việc tách làm khó theo dõi quan hệ cấu hình.

## 8. Nạp property file từ classpath trong XML

XML có thể dùng context namespace để nạp properties và thay thế placeholder trong bean definition:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:property-placeholder
        location="classpath:/com/example/config/application.properties"/>

    <bean id="reportOptions" class="com.example.report.ReportOptions">
        <property name="currency" value="${report.currency:VND}"/>
        <property name="maximumRows" value="${report.maximum-rows:500}"/>
    </bean>
</beans>
~~~

Trong placeholder, phần sau dấu hai chấm là giá trị mặc định nếu property không được tìm thấy. Nếu property là bắt buộc, không cung cấp default để cấu hình thiếu được phát hiện trong lúc khởi tạo context.

File properties có thể nằm trên classpath:

~~~properties
report.currency=VND
report.maximum-rows=1000
~~~

Không nên đặt mật khẩu hoặc secret thật trong file properties được đóng gói vào JAR. Dùng biến môi trường, secret manager hoặc cơ chế cấu hình an toàn phù hợp với môi trường triển khai.

## 9. Kết hợp XML với Java configuration

Spring không yêu cầu ứng dụng phải chọn duy nhất XML hoặc Java configuration. Một cấu hình Java có thể import XML bằng @ImportResource:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;

@Configuration
@ImportResource("classpath:/com/example/config/legacy-services.xml")
class ApplicationConfiguration {
}
~~~

Sau đó, context có thể được tạo từ Java configuration:

~~~java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
             ApplicationConfiguration.class
         )) {

    ProductService service =
        context.getBean(ProductService.class);
}
~~~

Cách này hữu ích khi chuyển dần một ứng dụng từ XML sang Java configuration. Có thể giữ một số bean legacy trong XML và khai báo bean mới bằng @Bean hoặc component scanning.

Spring Boot cũng hỗ trợ import XML bằng @ImportResource trên application configuration:

~~~java
@SpringBootApplication
@ImportResource("classpath:/legacy/application-context.xml")
public class Application {
}
~~~

Khi dùng Spring Boot, không cần tự tạo ClassPathXmlApplicationContext bên cạnh SpringApplication chỉ để nạp XML. Việc tạo hai context độc lập có thể khiến bean bị khởi tạo hai lần và dependency không được chia sẻ như mong đợi. Hãy import XML vào context do Spring Boot quản lý.

## 10. Nạp XML trong Spring Test

Spring TestContext Framework cho phép test khởi tạo ApplicationContext từ XML. Với JUnit Jupiter, có thể dùng @SpringJUnitConfig hoặc kết hợp @ExtendWith(SpringExtension.class) và @ContextConfiguration.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(locations =
    "classpath:/com/example/config/application-context.xml")
class ProductServiceXmlConfigTest {

    @Autowired
    private ProductService productService;

    @Test
    void loadsProductServiceFromXml() {
        assertNotNull(productService);
    }
}
~~~

@SpringJUnitConfig là annotation kết hợp cho JUnit Jupiter và Spring TestContext. Thuộc tính locations chỉ ra file cấu hình XML cần nạp. Spring tạo context, đăng ký bean và inject dependency vào test instance.

Có thể viết tương đương bằng:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    locations = "classpath:/com/example/config/application-context.xml"
)
class ProductServiceXmlConfigTest {
    // ...
}
~~~

Nếu cần nạp nhiều file XML:

~~~java
@SpringJUnitConfig(locations = {
    "classpath:/com/example/config/data-access.xml",
    "classpath:/com/example/config/services.xml"
})
class ServiceIntegrationTest {
    // ...
}
~~~

Đặt XML fixture hoặc test-only configuration trong src/test/resources nếu nó chỉ phục vụ test. Cấu hình dùng chung cho ứng dụng nên nằm trong src/main/resources và được test tham chiếu qua classpath.

### 10.1. XML location và classes

@ContextConfiguration hỗ trợ cả locations và classes. Có thể dùng XML cùng Java configuration trong một test:

~~~java
@SpringJUnitConfig(
    locations = "classpath:/legacy/legacy-services.xml",
    classes = TestOverrides.class
)
class MixedConfigurationTest {
    // ...
}
~~~

TestContext sẽ nạp các nguồn cấu hình được khai báo. Khi nhiều nguồn cùng đăng ký bean name, hãy hiểu rõ chính sách override và thứ tự xử lý của phiên bản Spring đang dùng. Tốt nhất nên tránh hai nguồn cùng định nghĩa một bean name nếu không có chủ đích rõ ràng.

### 10.2. Context cache trong test

Spring TestContext có thể cache ApplicationContext giữa các test có cấu hình tương đương. Nạp XML không có nghĩa mỗi test method luôn tạo một context mới. Cache giúp giảm thời gian chạy, nhưng test cần tránh làm thay đổi trạng thái singleton dùng chung.

Nếu một test thay đổi application-wide state hoặc bean mutable, hãy khôi phục trạng thái sau test hoặc thiết kế fixture riêng. Chỉ dùng @DirtiesContext khi test làm context không còn an toàn để tái sử dụng; annotation này khiến Spring loại context khỏi cache và có thể làm suite chậm hơn.

## 11. Đọc một classpath Resource trực tiếp trong test

Không phải lúc nào cũng cần tạo ApplicationContext để kiểm tra tài nguyên. Nếu mục tiêu chỉ là xác nhận file fixture tồn tại hoặc đọc được, dùng ClassPathResource trực tiếp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.util.StreamUtils;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

class ClasspathResourceTest {

    @Test
    void readsExpectedXmlFixture() throws Exception {
        // Arrange
        Resource resource = new ClassPathResource(
            "fixtures/sample-catalog.xml"
        );

        // Act
        String xml;
        try (InputStream input = resource.getInputStream()) {
            xml = StreamUtils.copyToString(
                input,
                StandardCharsets.UTF_8
            );
        }

        // Assert
        assertTrue(resource.exists());
        assertTrue(xml.contains("<catalog"));
    }
}
~~~

Trong test thực tế, assertion nên kiểm tra nội dung XML bằng parser hoặc XPath nếu cấu trúc là điều quan trọng. contains chỉ minh họa một kiểm tra rất hẹp và không chứng minh toàn bộ XML hợp lệ.

### 11.1. Vì sao nên dùng getInputStream?

Resource có thể nằm trong JAR, URL hoặc một nguồn không có file hệ thống. getFile() chỉ dùng được khi resource có thể được biểu diễn thành File. getInputStream() là cách tổng quát để đọc nội dung.

~~~java
Resource resource = new ClassPathResource("fixtures/sample-catalog.xml");

try (InputStream input = resource.getInputStream()) {
    byte[] bytes = StreamUtils.copyToByteArray(input);
}
~~~

Hãy đóng InputStream sau khi đọc. Không nên giữ stream mở qua nhiều test hoặc dựa vào garbage collection để giải phóng file handle.

### 11.2. Resource existence và readability

Resource có thể cung cấp các thông tin:

- exists(): tài nguyên có tồn tại theo cách implementation nhận biết hay không.
- isReadable(): tài nguyên có thể đọc hay không.
- getFilename(): tên file nếu xác định được.
- contentLength(): kích thước nội dung nếu implementation hỗ trợ xác định.
- getInputStream(): mở stream để đọc nội dung.
- getURL(): lấy URL nếu nguồn tài nguyên có thể biểu diễn bằng URL.

Không phải mọi Resource implementation đều hỗ trợ getFile, getURL hoặc contentLength. Khi viết code tổng quát, hãy dựa trên API được đảm bảo hoặc xử lý IOException phù hợp.

## 12. ResourcePatternResolver và nhiều tài nguyên classpath

ResourceLoader thường trả về một Resource cho một location. Khi cần tìm nhiều file theo pattern, dùng ResourcePatternResolver:

~~~java
ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] xmlFiles = resolver.getResources(
    "classpath*:com/example/plugins/*.xml"
);

for (Resource xmlFile : xmlFiles) {
    try (InputStream input = xmlFile.getInputStream()) {
        // Đọc hoặc xử lý từng resource.
    }
}
~~~

ResourcePatternResolver mở rộng ResourceLoader bằng khả năng tìm resource theo pattern. PathMatchingResourcePatternResolver là implementation thường dùng trong Spring.

Một số lưu ý:

- classpath*: hữu ích khi cần tìm resource ở nhiều entry classpath.
- Wildcard pattern cho phép tìm nhiều file theo quy tắc tên hoặc thư mục.
- Không giả định thứ tự trả về là thứ tự ưu tiên cấu hình.
- Một số pattern có thể hoạt động khác nhau tùy classloader, JAR layout và cách đóng gói.
- Nếu mỗi XML được dùng để đăng ký bean, cân nhắc nạp bằng một reader/context có kiểm soát thay vì tự xử lý nội dung XML như text.

Khi cần tìm các file XML do plugin cung cấp, classpath scanning có thể giúp phát hiện extension. Khi cần nạp cấu hình chính của ứng dụng, danh sách location tường minh thường dễ hiểu và dễ kiểm soát hơn.

## 13. Import resource tương đối và tuyệt đối

Trong XML, thẻ import có thể dùng location tương đối hoặc location có prefix:

~~~xml
<import resource="repositories.xml"/>
<import resource="classpath:/com/example/config/services.xml"/>
~~~

Location tương đối được phân giải liên quan đến resource XML đang chứa thẻ import. Điều này thuận tiện khi các file nằm cạnh nhau:

~~~text
config/
├── application-context.xml
├── repositories.xml
└── services.xml
~~~

Nếu application-context.xml import repositories.xml bằng tên tương đối, việc di chuyển cả nhóm file cùng nhau vẫn giữ được quan hệ. Nếu file được đặt ở một vị trí classpath khác, dùng classpath: để thể hiện nguồn rõ ràng.

Không nên dùng đường dẫn tương đối dựa vào working directory của process trong XML import. Working directory có thể khác giữa IDE, Gradle, container và môi trường production.

## 14. Lỗi thường gặp khi nạp XML và classpath resource

### 14.1. File XML không có trên runtime classpath

Nếu file nằm nhầm trong thư mục source Java hoặc một thư mục không được build tool coi là resource, Spring sẽ không tìm thấy nó. Đặt file ứng dụng trong src/main/resources và fixture test trong src/test/resources, hoặc cấu hình source set/resource directory đúng cách.

### 14.2. Dùng filesystem path cho file đã đóng gói trong JAR

Tài nguyên trong JAR không nhất thiết có đường dẫn file hệ thống. Dùng classpath: và Resource API để đọc. Không chuyển classpath resource thành File nếu không cần thiết.

### 14.3. Nhầm classpath: với classpath*:

classpath: tham chiếu một resource. classpath*: tìm nhiều resource phù hợp trên classpath. Nếu cần quét các file được cung cấp từ nhiều JAR, hãy dùng classpath*: cùng ResourcePatternResolver.

### 14.4. Không có prefix và phụ thuộc implementation

Một location không có prefix có thể được hiểu khác nhau bởi ClassPathXmlApplicationContext và FileSystemXmlApplicationContext. Dùng prefix rõ ràng khi nguồn tài nguyên cần ổn định.

### 14.5. Import XML sai đường dẫn

Thẻ import có thể dùng đường dẫn tương đối theo vị trí XML hiện tại hoặc một location có prefix. Hãy xác định file đang import nằm cạnh file hiện tại hay ở gốc classpath. Không giả định mọi đường dẫn đều tính từ project root.

### 14.6. Gọi refresh sai thời điểm

Với GenericApplicationContext, nạp bean definition trước rồi mới refresh. Refresh hoàn tất quá trình tạo container và khởi tạo bean theo lifecycle; không coi nó là thao tác có thể gọi tùy ý nhiều lần.

### 14.7. Thiếu XML namespace hoặc schema

Khi dùng context:component-scan hoặc context:property-placeholder, cần khai báo namespace và schema tương ứng. Nếu parser báo không nhận diện element, kiểm tra namespace URI, schemaLocation và dependency Spring tương ứng.

### 14.8. Trùng bean name giữa nhiều XML

Khi nạp nhiều file, bean name trùng có thể gây lỗi hoặc ghi đè tùy cấu hình. Dùng tên rõ ràng, tránh định nghĩa trùng ngoài chủ đích và kiểm tra chính sách bean definition overriding của ứng dụng.

### 14.9. File properties không được tìm thấy

Placeholder location cũng là resource location. Dùng classpath: với file nằm trong resources; nếu property nằm bên ngoài artifact, dùng file: và đảm bảo file có mặt trong môi trường chạy.

### 14.10. Tài nguyên chỉ có trong test classpath

Một file trong src/test/resources có thể đọc được khi chạy test nhưng không có trong ứng dụng production. Không đặt cấu hình runtime cần thiết vào test resources.

## 15. Chọn cách nạp phù hợp

| Nhu cầu | Cách tiếp cận |
|---|---|
| Nạp một hoặc nhiều XML từ classpath trong ứng dụng standalone | ClassPathXmlApplicationContext |
| Nạp XML từ file bên ngoài artifact | FileSystemXmlApplicationContext |
| Kiểm soát đăng ký bean definition và thời điểm refresh | GenericApplicationContext + XmlBeanDefinitionReader |
| Giữ XML legacy trong ứng dụng dùng Java configuration | @ImportResource |
| Nạp XML trong Spring TestContext | @SpringJUnitConfig hoặc @ContextConfiguration với locations |
| Chỉ đọc một file fixture trên classpath | ClassPathResource |
| Tìm nhiều resource theo wildcard | ResourcePatternResolver |
| Nạp XML vào Spring Boot ApplicationContext | @ImportResource trên cấu hình Boot |

Không có một cách nạp duy nhất phù hợp cho mọi tình huống. Chọn API theo việc ai sở hữu vòng đời context, nguồn file ở đâu và test cần xác nhận điều gì.

## 16. Mẫu kiểm thử XML context từ classpath

Một test có thể xác nhận bean được khai báo trong XML và dependency đã được kết nối:

~~~java
@SpringJUnitConfig(locations =
    "classpath:/com/example/config/application-context.xml")
class ApplicationXmlContextTest {

    @Autowired
    private ProductService productService;

    @Autowired
    private ProductRepository productRepository;

    @Test
    void loadsServiceAndItsRepositoryDependency() {
        assertNotNull(productService);
        assertNotNull(productRepository);
    }
}
~~~

Nếu muốn xác nhận hành vi thực tế, hãy gọi một method public của service và kiểm tra kết quả nghiệp vụ. Chỉ xác nhận bean tồn tại chứng minh container đã tạo được bean, nhưng chưa chắc mọi dependency hoặc cấu hình đều có hành vi đúng.

Một test có thể đọc trực tiếp Resource nếu muốn xác nhận file có trên test classpath:

~~~java
@Test
void xmlConfigurationIsAvailableOnClasspath() {
    Resource xml = new ClassPathResource(
        "com/example/config/application-context.xml"
    );

    assertTrue(xml.exists());
    assertTrue(xml.isReadable());
}
~~~

Hai test này kiểm tra hai điều khác nhau: test đầu khởi tạo Spring context từ XML; test sau chỉ xác nhận tài nguyên có thể được tìm thấy và đọc. Không thay test context bằng một kiểm tra file tồn tại nếu mục tiêu là xác nhận Spring hiểu được bean definition.

## Kết luận

Spring ApplicationContext có thể nạp XML từ classpath, filesystem hoặc nhiều nguồn Resource khác nhau. Dùng ClassPathXmlApplicationContext cho cấu hình XML đóng gói cùng ứng dụng, FileSystemXmlApplicationContext cho file ngoài artifact, XmlBeanDefinitionReader khi cần kiểm soát quá trình đăng ký bean, và @ImportResource khi kết hợp XML với Java configuration. Trong test, @SpringJUnitConfig hoặc @ContextConfiguration giúp nạp XML vào Spring TestContext; ClassPathResource và ResourcePatternResolver phù hợp khi chỉ cần đọc hoặc tìm fixture. Prefix location tường minh, quản lý đúng vòng đời context và đặt tài nguyên đúng source set giúp cấu hình chạy nhất quán giữa máy phát triển, CI và môi trường triển khai.
