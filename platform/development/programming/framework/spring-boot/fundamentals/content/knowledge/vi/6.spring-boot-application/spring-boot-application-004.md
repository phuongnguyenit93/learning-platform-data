# @EnableAutoConfiguration lựa chọn cấu hình theo điều kiện

Một ứng dụng Spring Boot rất nhỏ có thể chạy HTTP server, nhận JSON, chuyển đổi request thành đối tượng Java và sử dụng nhiều thành phần của Spring Framework dù lập trình viên chưa từng viết mã khởi tạo từng thành phần đó. **@EnableAutoConfiguration** là một phần quan trọng tạo nên trải nghiệm này: nó cho phép Spring Boot **tìm các cấu hình tự động có sẵn, đánh giá điều kiện và áp dụng những cấu hình phù hợp với ứng dụng hiện tại**.

Điểm cốt lõi là từ **“theo điều kiện”**. Spring Boot không bật mọi tính năng chỉ vì một thư viện tồn tại. Nó quan sát những gì đã có trong ứng dụng: dependency trên classpath, các bean do bạn định nghĩa, property đang cấu hình, loại ứng dụng web, tài nguyên và một số yếu tố khác. Từ đó Boot quyết định phần cấu hình nào có thể được đưa vào Spring ApplicationContext.

Trong chương **@SpringBootApplication**, bài học này tập trung vào vai trò của **@EnableAutoConfiguration**, cách nó phối hợp với các annotation còn lại và cách lần theo nguyên nhân khi một bean được tự động tạo, bị bỏ qua hoặc không xuất hiện như mong đợi.

## 1. Vị trí của @EnableAutoConfiguration trong @SpringBootApplication

Một ứng dụng Boot thông thường có điểm khởi động:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Về vai trò, **@SpringBootApplication** kết hợp ba nhóm khả năng:

| Thành phần | Trách nhiệm |
|---|---|
| **@SpringBootConfiguration** | Đánh dấu lớp là cấu hình Spring Boot của ứng dụng; xây dựng trên cơ chế **@Configuration** của Spring Framework. |
| **@EnableAutoConfiguration** | Kích hoạt cơ chế xem xét các auto-configuration của Spring Boot và các thư viện tích hợp. |
| **@ComponentScan** | Tìm các component do ứng dụng đăng ký theo cách quét package, như **@Component**, **@Service**, **@Repository** và **@Controller**. |

Ba thành phần phục vụ **ba mục tiêu khác nhau**, dù thường được đặt dưới một annotation duy nhất.

~~~text
DemoApplication
    @SpringBootApplication
            │
            ├── @SpringBootConfiguration
            │       └── Lớp cấu hình ứng dụng
            │
            ├── @ComponentScan
            │       └── Bean/component do ứng dụng định nghĩa
            │
            └── @EnableAutoConfiguration
                    └── Các cấu hình tự động được chọn có điều kiện
                            │
                            ▼
                    Spring ApplicationContext
                        ├── bean ứng dụng
                        ├── bean từ cấu hình Java
                        └── bean do auto-configuration cung cấp
~~~

**@ComponentScan không phải là @EnableAutoConfiguration.** Khi bạn viết một lớp **@Service** ở package con và Spring tạo bean cho nó, nguyên nhân trực tiếp có thể là component scanning. Khi Boot tự chuẩn bị một số bean web hoặc cấu hình nền tảng theo dependency đang có, đó là trách nhiệm của auto-configuration.

Có thể tự sử dụng **@EnableAutoConfiguration** trong một cấu hình Spring nếu thiết kế ứng dụng yêu cầu, nhưng trường hợp phổ biến là dùng **@SpringBootApplication** để có điểm khởi động thống nhất.

## 2. Auto-configuration giải quyết bài toán gì?

Spring Framework đã có cơ chế IoC container, **@Configuration**, **@Bean**, DI, Spring MVC, transaction management và nhiều tiện ích khác. Trước khi ứng dụng có thể sử dụng chúng, một số thành phần hạ tầng phải được khai báo và kết nối đúng với nhau.

Ví dụ, để xử lý HTTP request qua Spring MVC, một ứng dụng cần đủ các phần thích hợp như:

- Web framework trên classpath.
- ApplicationContext phù hợp với loại ứng dụng.
- DispatcherServlet và các thành phần MVC cần thiết.
- HTTP message conversion hoặc những cơ chế xử lý nội dung được chọn.
- Servlet container hoặc môi trường HTTP hỗ trợ Spring MVC.

Các phần này có thể cấu hình thủ công. Nhưng nếu mỗi dự án đều phải lặp lại cùng một bộ cấu hình, việc tạo ứng dụng mới trở nên nặng nề và tăng khả năng cấu hình lệch giữa các service.

Spring Boot cung cấp các **auto-configuration class** để xử lý những trường hợp lặp lại, áp dụng những mặc định hữu ích khi điều kiện tương ứng được đáp ứng.

Ví dụ với một ứng dụng web dùng **spring-boot-starter-web** trong Spring Boot 3.x:

~~~text
Dependency starter-web
          │
          ▼
Classpath có các thành phần web liên quan
          │
          ▼
Spring Boot đọc tập auto-configuration ứng viên
          │
          ▼
Đánh giá điều kiện theo môi trường và bean hiện có
          │
          ▼
Những cấu hình phù hợp được áp dụng
          │
          ▼
ApplicationContext có hạ tầng web cần thiết
          │
          ▼
Controller của bạn có thể xử lý request
~~~

Spring Boot **không tự viết endpoint, nghiệp vụ hoặc chính sách bảo mật thay bạn**. Nó hỗ trợ tạo hạ tầng phù hợp cho những phần bạn thực sự sử dụng.

## 3. Tìm ứng viên auto-configuration khác với quét component

Một câu hỏi quan trọng: **Boot biết những class auto-configuration nào để xem xét?**

Với Spring Boot 3.x, các thư viện có thể công bố danh sách auto-configuration trong resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File này chứa tên đầy đủ của những lớp auto-configuration được xuất bản bởi module, thường một tên lớp trên mỗi dòng. Ví dụ minh họa:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.metrics.autoconfigure.MetricsBridgeAutoConfiguration
~~~

Những tên trên chỉ là ví dụ giả định, không phải các class có sẵn của Spring Boot.

**@EnableAutoConfiguration** sử dụng cơ chế import và selector của Boot để thu thập các ứng viên được đăng ký qua metadata. Thành phần tiêu biểu trong cơ chế này là **AutoConfigurationImportSelector**, được gắn với annotation thông qua **@Import**. Bộ chọn còn xem xét các loại trừ và metadata liên quan trước khi cấu hình được đưa vào quá trình xử lý của Spring.

Mô hình khái niệm:

~~~text
@SpringBootApplication
    └── @EnableAutoConfiguration
          └── @Import(AutoConfigurationImportSelector)
                 │
                 ▼
       Đọc danh sách auto-configuration ứng viên
                 │
                 ├── Lọc các cấu hình bị exclude
                 ├── Xem metadata để loại sớm ứng viên không phù hợp
                 └── Đưa các class được chọn vào xử lý cấu hình
                                  │
                                  ▼
                        Đánh giá @Conditional...
                                  │
                       ┌──────────┴──────────┐
                       │                     │
                    Thỏa mãn            Không thỏa mãn
                       │                     │
                       ▼                     ▼
                Áp dụng cấu hình        Bỏ qua cấu hình/
                và các bean phù hợp    hoặc bean tương ứng
~~~

Không nên hiểu sơ đồ trên là một lần kiểm tra duy nhất áp dụng cho mọi trường hợp. **Condition có thể đặt ở cấp class hoặc cấp phương thức @Bean**, và được đánh giá ở các giai đoạn phù hợp khi Spring xử lý cấu hình và định nghĩa bean. Một auto-configuration class được chấp nhận không có nghĩa **mọi bean** bên trong nó đều được tạo.

### 3.1. Vì sao không quét mọi class trên classpath?

Classpath có thể chứa rất nhiều JAR và class. Tìm mọi class rồi tự đoán class nào cần thiết sẽ vừa tốn chi phí vừa khó kiểm soát. Việc công bố danh sách các auto-configuration giúp Boot biết **những cấu hình nào được thiết kế để tự động tham gia**, độc lập với việc quét component của ứng dụng.

Một lớp **@Configuration** thông thường nằm trong một dependency không mặc nhiên trở thành auto-configuration chỉ vì JAR có trên classpath. Để trở thành ứng viên auto-configuration theo cơ chế thông thường của Boot 3.x, nó cần được đăng ký theo hợp đồng của Boot.

### 3.2. Khác biệt giữa Boot 2.x và Boot 3.x

Ở những phiên bản Spring Boot cũ, auto-configuration thường được khai báo thông qua khóa **org.springframework.boot.autoconfigure.EnableAutoConfiguration** trong **META-INF/spring.factories**. Spring Boot 2.7 đã hỗ trợ định dạng **AutoConfiguration.imports**; trong Spring Boot 3.x, đây là cơ chế đăng ký auto-configuration chuẩn.

Khi đọc một thư viện cũ hoặc nâng cấp thư viện tự viết, hãy kiểm tra **phiên bản Spring Boot mà thư viện hỗ trợ**. Không thể chỉ copy cấu hình đăng ký của một hướng dẫn cũ mà mặc định nó hoạt động ở phiên bản mới.

## 4. Điều kiện (condition) được kiểm tra ở những mức nào?

Một auto-configuration class thường khai báo điều kiện ở **cấp class**; các phương thức **@Bean** có thể khai báo điều kiện riêng.

~~~java
@AutoConfiguration
@ConditionalOnClass(SomeClient.class)
public class SomeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SomeClient.class)
    SomeClient someClient() {
        return new SomeClient();
    }
}
~~~

*SomeClient ở đây là kiểu minh họa giả định.* Ý nghĩa:

- Nếu class **SomeClient** không xuất hiện theo điều kiện classpath tương ứng, auto-configuration có thể được bỏ qua.
- Nếu class có mặt, Boot tiếp tục xét điều kiện trên bean definition.
- Nếu ứng dụng đã có bean phù hợp, cấu hình tạo bean mặc định có thể **back off**.
- Nếu các điều kiện cần thiết đều đáp ứng, bean mặc định được đăng ký.

Cơ chế này giúp Boot cung cấp mặc định mà vẫn cho phép code ứng dụng khai báo một số thành phần thay thế.

### 4.1. Những nhóm điều kiện quan trọng

| Annotation | Câu hỏi được kiểm tra | Tình huống sử dụng |
|---|---|---|
| **@ConditionalOnClass** | Có những class được chỉ định trên classpath không? | Chỉ cấu hình một client khi thư viện client có mặt. |
| **@ConditionalOnMissingClass** | Một class cụ thể có vắng mặt không? | Chọn đường cấu hình tương thích với môi trường thiếu thư viện nào đó. |
| **@ConditionalOnBean** | Đã có bean phù hợp theo điều kiện chưa? | Cấu hình một adapter chỉ khi đã có dependency cần thiết. |
| **@ConditionalOnMissingBean** | Chưa có bean phù hợp hay chưa? | Cung cấp bean mặc định, để ứng dụng tự thay thế. |
| **@ConditionalOnSingleCandidate** | Có thể xác định một ứng viên bean phù hợp hay không? | Chỉ cấu hình một tích hợp khi dependency không mơ hồ. |
| **@ConditionalOnProperty** | Các property có giá trị phù hợp với quy tắc khai báo không? | Cho phép bật/tắt tính năng qua cấu hình ngoài code. |
| **@ConditionalOnWebApplication** | Đây có phải web application thuộc loại yêu cầu không? | Cấu hình Servlet web hoặc reactive web. |
| **@ConditionalOnNotWebApplication** | Đây có phải ứng dụng không phải web không? | Cấu hình thích hợp cho batch/command-line app. |
| **@ConditionalOnResource** | Các resource yêu cầu có trên classpath không? | Chỉ kích hoạt tích hợp khi resource phù hợp tồn tại. |
| **@ConditionalOnJava** | Java runtime có đáp ứng yêu cầu phiên bản không? | Phân nhánh hỗ trợ theo phiên bản Java. |
| **@ConditionalOnExpression** | Biểu thức SpEL có thỏa điều kiện không? | Trường hợp đặc biệt; cần cân nhắc chi phí và tác động khởi tạo sớm. |

Tất cả các điều kiện được xét trong **ngữ cảnh cụ thể**. Ví dụ, **@ConditionalOnBean** không đơn giản hỏi “có một class trên classpath hay không”; nó hỏi về **bean definition/sự hiện diện bean** trong Spring context theo các tiêu chí khai báo.

### 4.2. @ConditionalOnClass: dependency là tín hiệu đầu tiên

Hãy tưởng tượng ứng dụng có hoặc không có thư viện xử lý Redis. Một cấu hình tự động liên quan Redis thường chỉ có ý nghĩa nếu các kiểu thư viện cần thiết có mặt. **@ConditionalOnClass** cho phép Boot bỏ qua cấu hình khi điều kiện classpath không đáp ứng.

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optional.ClientDriver")
public class OptionalClientAutoConfiguration {
    // Cấu hình được xét khi điều kiện classpath thỏa.
}
~~~

Sử dụng **name** là một cách kiểm tra class theo tên chuỗi, hữu ích khi kiểu là dependency tùy chọn. Khi một cấu hình phải tham chiếu trực tiếp các class có thể vắng mặt, nên cô lập chúng trong cấu hình con có điều kiện tương ứng để tránh lỗi liên kết class trước khi điều kiện có thể bảo vệ phần code đó.

Có class trên classpath **không chứng minh cấu hình đã bật**. Auto-configuration còn có thể bị loại trừ, thiếu property, sai loại web application hoặc gặp điều kiện bean không đáp ứng.

### 4.3. @ConditionalOnMissingBean: mặc định có thể nhường chỗ

Giả sử thư viện muốn cung cấp một **GreetingService** mặc định, nhưng ứng dụng có thể tự tạo implementation.

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new GreetingService("Xin chào");
}
~~~

Nếu application context đã có bean **GreetingService** phù hợp khi điều kiện được đánh giá, bean mặc định này sẽ không được đăng ký.

Đây là nguyên tắc **back off**: “Boot cung cấp một giá trị mặc định khi ứng dụng chưa cung cấp lựa chọn của mình”.

Điểm cần nhớ: **@ConditionalOnMissingBean không phải cơ chế ghi đè bean sau khi nó đã được tạo**. Điều kiện làm việc trong quá trình xử lý đăng ký bean definitions, và phụ thuộc những định nghĩa bean đã được biết ở thời điểm kiểm tra. Vì thế tài liệu Boot thường khuyến nghị sử dụng điều kiện kiểu này trong auto-configuration, nơi Boot có thể sắp xếp để các bean do ứng dụng tự khai báo được xem xét trước.

### 4.4. @ConditionalOnProperty: chọn cấu hình bằng property

Một annotation minh họa:

~~~java
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Ý nghĩa mong muốn:

- **demo.greeting.enabled=true**: điều kiện thỏa.
- **demo.greeting.enabled=false**: không thỏa.
- Không khai báo property: không thỏa vì **matchIfMissing=false**.

Nếu đặt **matchIfMissing=true**, điều kiện có thể thỏa ngay cả khi property vắng mặt.

Với **@ConditionalOnProperty** và không ghi **havingValue**, quy tắc chung là property phải hiện diện và giá trị không được bằng chuỗi **false** theo cách kiểm tra của điều kiện. Vì vậy đừng tự hiểu nó là một trình phân tích boolean tổng quát cho mọi giá trị tùy ý; khi cần chính xác, hãy ghi **havingValue** rõ ràng.

Đặc biệt, điều kiện này không phù hợp để suy luận trực tiếp sự có mặt/phần tử của một property dạng **collection** bằng tên prefix đơn giản; cần lựa chọn cơ chế điều kiện khác khi bài toán phức tạp.

### 4.5. @ConditionalOnBean và rủi ro thứ tự xử lý

Khi một auto-configuration chỉ được dùng nếu có một bean từ cấu hình khác:

~~~java
@ConditionalOnBean(SomeClient.class)
~~~

điều kiện kiểm tra những bean definitions đã được xử lý đến thời điểm đó. Nếu một bean được đăng ký trong cấu hình xử lý sau, điều kiện có thể chưa nhìn thấy nó. Do đó, auto-configuration thường khai báo **ordering** khi phụ thuộc vào một auto-configuration khác.

Không nên nghĩ rằng thứ tự class trong file imports là một hợp đồng đáng tin cho mọi quan hệ điều kiện. Có công cụ sắp xếp auto-configuration riêng, được mô tả ở phần sau.

## 5. Một ví dụ đầy đủ về điều kiện phối hợp

Giả sử ứng dụng có một module gửi lời chào và muốn:

1. Cho phép bật/tắt việc tạo service mặc định bằng cấu hình.
2. Có prefix mặc định nhưng cho phép cấu hình lại.
3. Cho phép ứng dụng tự khai báo **GreetingService** để thay thế bean mặc định.

Đây là ví dụ có chủ ý đơn giản để hiểu auto-configuration. Trước tiên, một lớp nghiệp vụ thuần Java:

~~~java
package com.example.greeting;

public class GreetingService {
    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

Một lớp cấu hình properties:

~~~java
package com.example.greeting.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {
    private String prefix = "Xin chào";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Auto-configuration:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new GreetingService(properties.getPrefix());
    }
}
~~~

Ở đây:

- **@AutoConfiguration** đánh dấu lớp cấu hình tự động theo cơ chế Spring Boot.
- **@EnableConfigurationProperties** đăng ký việc bind **demo.greeting.prefix** vào **GreetingProperties**.
- **@ConditionalOnProperty** quyết định có áp dụng auto-configuration theo property **enabled** hay không.
- **@Bean** mô tả cách tạo **GreetingService**.
- **@ConditionalOnMissingBean** chỉ tạo service mặc định nếu chưa có bean cùng loại phù hợp.

Để module thư viện này được xem là auto-configuration ứng viên trong Spring Boot 3.x, file sau cần nằm trong JAR:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Tên class phải tương ứng với class thực tế đã được biên dịch và có trên classpath. **Chỉ gắn @AutoConfiguration mà không đăng ký hoặc import cấu hình theo cơ chế phù hợp chưa đủ để thư viện được Boot tự động phát hiện.**

### 5.1. Trường hợp bật mặc định

Với:

~~~yaml
demo:
  greeting:
    prefix: "Chào bạn"
~~~

Do **matchIfMissing=true**, việc không khai báo **demo.greeting.enabled** vẫn cho phép cấu hình tham gia.

Nếu chưa có bean **GreetingService** khác, Boot đăng ký bean được tạo qua factory method. Khi gọi:

~~~java
greetingService.greet("Lan");
~~~

kết quả là:

~~~text
Chào bạn, Lan!
~~~

### 5.2. Trường hợp tắt bằng property

~~~yaml
demo:
  greeting:
    enabled: false
~~~

Điều kiện ở cấp **GreetingAutoConfiguration** không thỏa, nên cấu hình này không đăng ký bean do nó định nghĩa. Nếu ứng dụng vẫn có một bean GreetingService từ nguồn khác, bean đó **không tự bị xóa** bởi việc tắt auto-configuration.

### 5.3. Trường hợp người dùng định nghĩa bean riêng

Ứng dụng có thể khai báo:

~~~java
package com.example.demo;

import com.example.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MyGreetingConfiguration {
    @Bean
    GreetingService customGreetingService() {
        return new GreetingService("Hello");
    }
}
~~~

Khi bean này được đăng ký trước thời điểm đánh giá **@ConditionalOnMissingBean(GreetingService.class)**, auto-configuration sẽ **nhường chỗ**. Kết quả dự kiến khi inject GreetingService trong ứng dụng là bean do application khai báo.

Đây là hành vi chủ động của auto-configuration được thiết kế với điều kiện back off. Không phải mọi bean có sẵn trong Spring Boot đều mặc nhiên cho phép thay thế bằng cùng một cách; cần xem điều kiện của cấu hình cụ thể.

### 5.4. Bảng kết quả theo các tình huống

| Property enabled | Bean GreetingService do app tự khai báo | Kết quả từ auto-configuration ví dụ |
|---|---|---|
| Vắng mặt | Không | Đăng ký bean mặc định do **matchIfMissing=true**. |
| **true** | Không | Đăng ký bean mặc định. |
| **false** | Không | Không đăng ký bean từ cấu hình này. |
| **true** | Có | **@ConditionalOnMissingBean** khiến bean mặc định nhường chỗ. |
| **false** | Có | Auto-configuration bị bỏ qua; bean do app khai báo vẫn là bean riêng của app. |

Bảng này chỉ áp dụng khi thư viện được đăng ký, classpath đầy đủ và không có cấu hình đặc biệt khác can thiệp.

## 6. Classpath và starter: yếu tố đầu vào, không phải toàn bộ quyết định

Khi thêm starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle resolve các dependency trực tiếp và bắc cầu để tạo classpath. Classpath này là tín hiệu quan trọng cho những điều kiện như **@ConditionalOnClass**. Nhưng các quyết định ở cấp Spring ApplicationContext còn liên quan property, bean đang có và loại ứng dụng.

Ví dụ:

~~~text
Starter/dependency hiện diện
           │
           ▼
Các class cần thiết xuất hiện
           │
           ▼
Điều kiện classpath thỏa?
           │
           ▼
Điều kiện web app phù hợp?
           │
           ▼
Property cho phép cấu hình?
           │
           ▼
Ứng dụng đã có bean thay thế?
           │
           ▼
Quyết định đăng ký bean mặc định
~~~

Đây là một cây quyết định minh họa. Một auto-configuration cụ thể có thể dùng một tập điều kiện khác hoàn toàn; Boot không bắt buộc tất cả cấu hình phải chứa đủ năm bước.

### 6.1. Ví dụ Spring MVC

Với Spring Boot 3.x và starter web theo mô hình Servlet, Boot có thể cung cấp những cấu hình nền tảng như thiết lập Spring MVC và tích hợp máy chủ nhúng phù hợp khi các điều kiện được đáp ứng.

Nếu không có một số thư viện web cần thiết, hoặc ứng dụng được thiết kế như non-web application, những điều kiện tương ứng có thể không được kích hoạt. Nếu ứng dụng tự định nghĩa một bean MVC được hỗ trợ ghi đè qua điều kiện missing-bean, Boot có thể nhường chỗ cho bean đó.

Điều này giải thích vì sao chỉ thêm **@RestController** không đủ để chạy API trong bất kỳ loại chương trình Java nào: controller cần nằm trong context có hạ tầng web thích hợp.

### 6.2. Ví dụ DataSource

Với các thư viện JDBC và điều kiện cấu hình phù hợp, Spring Boot có thể tự chuẩn bị **DataSource**. Nhưng:

- Driver và connection URL thích hợp phải được xác định bằng classpath/cấu hình hoặc các lựa chọn mà Boot hỗ trợ.
- Trường hợp embedded database được hỗ trợ sẽ khác với database ngoài.
- Một bean DataSource do ứng dụng tự cung cấp có thể khiến cấu hình DataSource mặc định back off, tùy điều kiện cụ thể.
- Thiếu URL/driver/credentials cho một database ngoài không phải điều Boot có thể suy ra từ tên starter.

Nếu startup thất bại với lỗi liên quan DataSource, cần đọc **cause** và kiểm tra configuration; không thể kết luận “thêm starter JDBC là Boot phải tự kết nối thành công”.

## 7. Sự khác nhau giữa auto-configuration và configuration thông thường

Một lớp cấu hình thường:

~~~java
@Configuration
public class BusinessConfiguration {
    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }
}
~~~

Nếu được component scan hoặc import, lớp này đóng góp bean cho ứng dụng theo cấu hình bạn đã chọn.

Một lớp auto-configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optional.ExternalClient")
public class ExternalClientAutoConfiguration {
    // Các bean và điều kiện tùy chọn.
}
~~~

được thiết kế để Boot có thể **xem xét như một ứng viên**, và chỉ áp dụng khi điều kiện tương ứng thỏa. Nó thường nằm trong thư viện hoặc module tích hợp, dùng các điều kiện để không làm hỏng ứng dụng không sử dụng tính năng đó.

| Tiêu chí | Cấu hình ứng dụng | Auto-configuration |
|---|---|---|
| Ai chủ động khai báo? | Chủ dự án, qua scan hoặc import. | Thư viện/Boot đăng ký ứng viên theo cơ chế auto-configuration. |
| Mục đích chính | Thể hiện quyết định cụ thể của ứng dụng. | Cung cấp mặc định và tích hợp có điều kiện. |
| Có dùng @Conditional được không? | Có. | Có, và thường sử dụng nhiều điều kiện. |
| Có bắt buộc dùng @ConditionalOnMissingBean? | Không. | Không bắt buộc, nhưng thường có để nhường chỗ cho cấu hình riêng. |
| Có tự động trở thành bean chỉ vì nằm trong JAR? | Không. | Không; phải được đăng ký theo cơ chế phù hợp và thỏa điều kiện. |

Một số cơ chế **@Conditional** thuộc Spring Framework, còn các annotation **@ConditionalOn...** được Spring Boot cung cấp như các điều kiện tiện ích phù hợp bài toán auto-configuration.

## 8. Điều kiện “có bean” khác điều kiện “có class”

Hai điều kiện thường bị nhầm lẫn nhất là **@ConditionalOnClass** và **@ConditionalOnBean**.

Giả sử một thư viện có kiểu **EmailSender**:

~~~text
Dependency có EmailSender.class
                 │
                 ▼
    @ConditionalOnClass(EmailSender.class)
                 │
              Thỏa mãn
~~~

Điều đó chỉ cho biết **class có thể được tìm thấy theo classpath và class loader dùng để kiểm tra**. Không có gì bảo đảm một instance EmailSender đã được đăng ký làm Spring bean.

Ngược lại:

~~~text
ApplicationContext có bean EmailSender
                 │
                 ▼
    @ConditionalOnBean(EmailSender.class)
                 │
              Thỏa mãn
~~~

Ở đây Spring kiểm tra bean phù hợp. Một bean có thể được khai báo bằng **@Bean** hoặc tìm thấy qua component scanning, nhưng việc class tồn tại trên classpath không tự tạo ra bean.

Ví dụ:

~~~java
@ConditionalOnClass(name = "com.example.mail.EmailSender")
class MailIntegrationConfiguration {
    // Có thư viện tương ứng mới xem xét cấu hình.
}
~~~

~~~java
@ConditionalOnBean(name = "primaryEmailSender")
class MailNotificationConfiguration {
    // Chỉ áp dụng khi bean mang tên yêu cầu đã tồn tại.
}
~~~

Hai điều kiện giải quyết hai câu hỏi khác nhau:

| Câu hỏi | Điều kiện |
|---|---|
| Thư viện/tính năng có mặt trên classpath không? | **@ConditionalOnClass** |
| Đã có bean do ứng dụng hoặc cấu hình khác cung cấp chưa? | **@ConditionalOnBean** |
| Ứng dụng chưa cung cấp bean để tôi dùng mặc định? | **@ConditionalOnMissingBean** |

Đó cũng là lý do một dependency đã tải thành công nhưng việc inject bằng **@Autowired** hoặc constructor vẫn có thể báo thiếu bean: classpath và bean registry là hai lớp thông tin khác nhau.

## 9. Thứ tự auto-configuration và điều kiện dựa trên bean

Các điều kiện về bean quan sát những bean definition đã được xử lý trong quá trình xây dựng context. Vì vậy thứ tự giữa những auto-configuration có thể quan trọng.

Giả sử **AuditAutoConfiguration** chỉ hoạt động khi có một **EventPublisher** được tạo từ **EventsAutoConfiguration**:

~~~text
EventsAutoConfiguration
          │ đăng ký EventPublisher
          ▼
AuditAutoConfiguration
          │ kiểm tra @ConditionalOnBean(EventPublisher.class)
          ▼
Đăng ký AuditListener nếu điều kiện phù hợp
~~~

Với Spring Boot 3.x, một auto-configuration có thể khai báo quan hệ thứ tự bằng thuộc tính **after** hoặc **before** của **@AutoConfiguration**:

~~~java
@AutoConfiguration(after = EventsAutoConfiguration.class)
@ConditionalOnBean(EventPublisher.class)
public class AuditAutoConfiguration {
    // Bean và cấu hình audit.
}
~~~

Đây là ví dụ giả định về tên class. Trong code thực tế, cần bảo đảm bean EventPublisher được đăng ký theo cách phù hợp và các điều kiện khác cũng thỏa.

**@AutoConfiguration(after = ...)** ảnh hưởng đến thứ tự xử lý các **auto-configuration class**. Nó không phải chỉ thị “khởi tạo bean này sau bean kia ở runtime”. Thứ tự khởi tạo bean còn chịu ảnh hưởng bởi dependency injection, **@DependsOn** và các cơ chế lifecycle khác.

Các annotation **@AutoConfigureBefore** và **@AutoConfigureAfter** cũng có thể xuất hiện trong code Boot hoặc thư viện tương ứng. Khi viết code mới cho Spring Boot 3.x, thuộc tính của **@AutoConfiguration** là cách diễn đạt dễ thấy.

### 9.1. Không dựa vào thứ tự ngẫu nhiên của file imports

Danh sách auto-configuration ứng viên được đọc rồi xử lý theo cơ chế sắp xếp của Boot. Do đó không nên dùng việc đặt một dòng ở trên dòng khác trong file **AutoConfiguration.imports** như một hợp đồng thứ tự giữa các bean.

Nếu một cấu hình có điều kiện **@ConditionalOnBean** phải phụ thuộc vào bean đến từ cấu hình khác, nên mô tả quan hệ dependency và ordering rõ ràng.

### 9.2. Khi nào nên dùng @ConditionalOnMissingBean?

Cách dùng phổ biến nhất là **cung cấp bean mặc định nếu ứng dụng chưa cung cấp lựa chọn riêng**. Ví dụ một thư viện cung cấp serializer, HTTP client, converter hoặc service adapter mặc định.

Không nên dùng điều kiện này như một phương thức sửa xung đột tên bean một cách tùy tiện. Nếu dự án có hai implementation cùng interface nhưng cần sử dụng cả hai, vấn đề có thể thuộc thiết kế injection với **@Qualifier** hoặc **@Primary**, chứ không phải lúc nào cũng nên loại một bean khỏi context.

## 10. Điều gì xảy ra nếu có nhiều điều kiện?

Một auto-configuration có thể có điều kiện cấp class, điều kiện cấp method và điều kiện được kết hợp:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.storage.StorageClient")
@ConditionalOnProperty(
    prefix = "demo.storage",
    name = "enabled",
    havingValue = "true"
)
public class StorageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(StorageService.class)
    StorageService storageService() {
        return new StorageService();
    }
}
~~~

Giả sử **StorageService** là lớp có sẵn trong module minh họa. Các điều kiện trên tạo ra ba cổng quyết định:

1. **Có StorageClient class** theo điều kiện classpath.
2. **Property demo.storage.enabled có giá trị true**.
3. **Chưa có bean StorageService** phù hợp tại thời điểm xét method.

Nếu điều kiện ở cấp class không thỏa, cấu hình bị bỏ qua trước khi bean method có thể đóng góp bean. Nếu class-level conditions thỏa nhưng điều kiện method không thỏa, class cấu hình vẫn có thể đã được xử lý nhưng bean cụ thể không được tạo.

Khi các điều kiện được khai báo kết hợp, cần hiểu cách **@Conditional** của Spring tổng hợp kết quả. Trong các tình huống điều kiện độc lập thông dụng như ở ví dụ, tất cả điều kiện bắt buộc tại mức tương ứng phải thỏa để phần cấu hình được áp dụng.

### 10.1. Điểm tránh hiểu nhầm: không tự động đánh giá lại khi property thay đổi

Auto-configuration thường được quyết định trong quá trình tạo/refresh application context. Nếu một operator sửa property trong file cấu hình trên đĩa sau khi ứng dụng đã khởi động, Spring Boot **không mặc nhiên cập nhật lại mọi bean và auto-configuration đang chạy**.

Để thay đổi cấu hình động cần một cơ chế được thiết kế riêng, chẳng hạn tạo lại context, khởi động lại ứng dụng hoặc dùng cơ chế refresh có kiểm soát trong hệ sinh thái phù hợp. Không nên coi **@ConditionalOnProperty** là một công tắc được tái đánh giá liên tục mỗi request.

### 10.2. Spring profiles tương tác ra sao?

**@Profile** và các file cấu hình theo profile là cơ chế của Spring/Spring Boot để chọn bean hoặc nguồn cấu hình theo môi trường. Chúng có thể gián tiếp thay đổi:

- Property được nạp vào **Environment**.
- Bean do ứng dụng đăng ký.
- Kết quả của **@ConditionalOnProperty**, **@ConditionalOnBean** và **@ConditionalOnMissingBean**.

Ví dụ:

~~~yaml
# application-dev.yml
demo:
  greeting:
    enabled: true
    prefix: "Chào môi trường dev"
~~~

~~~yaml
# application-prod.yml
demo:
  greeting:
    enabled: false
~~~

Nếu profile **dev** được kích hoạt, cùng một auto-configuration có thể thỏa điều kiện; nếu profile **prod** được kích hoạt và property tương ứng được dùng, điều kiện sẽ không thỏa. Kết quả vẫn phụ thuộc nguồn cấu hình, thứ tự ưu tiên property và các bean khác của ứng dụng.

Không nên đồng nhất **@Profile** với **@ConditionalOnProperty**: profile là một khái niệm môi trường và lựa chọn cấu hình, còn conditional property kiểm tra property theo một biểu thức điều kiện cụ thể.

## 11. Khi nào nên loại trừ một auto-configuration?

Đôi khi một auto-configuration là ứng viên và điều kiện của nó đủ để tham gia, nhưng ứng dụng muốn **không sử dụng** phần tự động thiết lập đó.

Ví dụ, một ứng dụng chủ động không dùng cơ sở dữ liệu có thể cần loại trừ auto-configuration về DataSource trong một trường hợp đặc biệt nếu classpath và cấu hình khiến nó được xem xét.

Với Spring Boot 3.x:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Đây là **lựa chọn loại trừ có chủ đích**. Nếu ứng dụng thực sự cần database, loại trừ DataSource auto-configuration chỉ để startup hết lỗi có thể khiến vấn đề chuyển thành **thiếu bean DataSource** hoặc chức năng truy cập dữ liệu không hoạt động. Khi ấy cần sửa kết nối, driver hoặc cấu hình cho đúng.

### 11.1. Ba cách loại trừ thường gặp

| Cách | Ví dụ | Khi nào hữu ích |
|---|---|---|
| **exclude** | **@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)** | Có thể tham chiếu trực tiếp class auto-configuration. |
| **excludeName** | **@SpringBootApplication(excludeName = "com.example.SomeAutoConfiguration")** | Muốn khai báo theo tên class, không buộc code phụ thuộc trực tiếp vào loại đó. |
| **spring.autoconfigure.exclude** | Property cấu hình chứa tên đầy đủ class auto-configuration cần loại. | Muốn điều khiển exclusion bằng cấu hình môi trường. |

Ví dụ property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Việc loại trừ áp dụng cho **auto-configuration candidates** được Boot quản lý. Nó không phải cơ chế chung để xóa tất cả bean đã được khai báo bằng tay, tất cả class trong một package hoặc mọi dependency khỏi runtime classpath.

### 11.2. Exclude auto-configuration không loại dependency khỏi JAR

Đây là hai thao tác khác nhau:

~~~text
Gradle exclude dependency
    └── Thay đổi dependency graph / classpath

Spring Boot exclude auto-configuration
    └── Thay đổi tập cấu hình tự động được xét
~~~

Bạn có thể giữ dependency để sử dụng API trực tiếp nhưng muốn tự định nghĩa bean, hoặc loại một auto-configuration vì kiến trúc riêng. Tuy nhiên, để giảm kích thước artifact và bề mặt dependency thì cần xem lại **build dependency**, không chỉ exclusion ở Spring.

## 12. Chẩn đoán: vì sao một auto-configuration được áp dụng hoặc bị bỏ qua?

Khi một bean xuất hiện ngoài dự kiến, hoặc bean mong muốn không có, nên hỏi:

- Cấu hình ứng viên nào chịu trách nhiệm?
- Nó có được đăng ký trong danh sách auto-configuration hay không?
- Nó đã bị exclude chưa?
- Điều kiện classpath có thỏa không?
- Có bean nào khác làm điều kiện missing-bean không thỏa?
- Property và profile thực tế là gì?
- Ứng dụng đang chạy dưới loại context nào?

Spring Boot cung cấp thông tin chẩn đoán cho các **condition evaluation** để trả lời những câu hỏi đó.

### 12.1. Condition Evaluation Report

Khi chạy ứng dụng với tùy chọn debug:

~~~bash
java -jar demo.jar --debug
~~~

Spring Boot có thể in **Condition Evaluation Report** trong log startup, mô tả nhiều kết quả kiểm tra điều kiện. Các mục có thể được nhóm thành:

- **Positive matches**: điều kiện được ghi nhận là thỏa.
- **Negative matches**: điều kiện được ghi nhận là không thỏa, kèm lý do.
- **Exclusions**: auto-configuration bị loại trừ.
- **Unconditional classes**: một số auto-configuration không đặt điều kiện kiểu được báo cáo ở cấp tương ứng.

Một đoạn output dạng minh họa:

~~~text
CONDITIONS EVALUATION REPORT

Positive matches:
-----------------
SomeWebAutoConfiguration matched:
   - @ConditionalOnClass found required class '...'

Negative matches:
-----------------
SomeOptionalAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class '...'

Exclusions:
-----------
    org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Tên cấu hình trong ví dụ là giả định; cách format và câu chữ cụ thể phụ thuộc phiên bản Boot và điều kiện thực tế.

**Positive match không khẳng định ứng dụng hoạt động đúng mọi tính năng liên quan.** Nó chỉ ghi nhận việc điều kiện cụ thể đã thỏa. Auto-configuration có thể còn các điều kiện ở cấp bean, và code khi khởi tạo bean vẫn có thể ném exception.

**Negative match cũng không nhất thiết là lỗi.** Ví dụ ứng dụng không sử dụng MongoDB thì Mongo auto-configuration bị bỏ qua là chuyện bình thường.

### 12.2. Endpoint Actuator conditions

Nếu ứng dụng đã thêm **spring-boot-starter-actuator** và cấu hình expose endpoint phù hợp, endpoint **conditions** có thể cung cấp thông tin condition evaluation qua giao diện quản trị.

Ví dụ cấu hình minh họa việc bật expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Sau đó, nếu endpoint được triển khai và truy cập theo security policy thích hợp, có thể xem dữ liệu qua đường dẫn quản trị tương ứng, thường là **/actuator/conditions**.

Các endpoint chẩn đoán có thể tiết lộ cấu trúc nội bộ, cấu hình và thành phần ứng dụng. Khi vận hành thực tế, nên kiểm soát quyền truy cập, mạng và phạm vi expose; không bật công khai chỉ để tiện debug.

### 12.3. Đọc kết quả theo chuỗi lý do

Giả sử bạn kỳ vọng một **GreetingService** mặc định nhưng không tìm thấy:

~~~text
Không có GreetingService
          │
          ├── GreetingAutoConfiguration có được đăng ký?
          │
          ├── Auto-configuration có bị exclude?
          │
          ├── demo.greeting.enabled có phải false?
          │
          ├── Có bean GreetingService khác làm back off?
          │
          └── Bean method có lỗi khởi tạo?
~~~

Điểm cuối rất quan trọng: **điều kiện thỏa nhưng tạo bean thất bại** là trường hợp khác với **điều kiện không thỏa nên bean không được định nghĩa**. Trường hợp đầu thường có stack trace **BeanCreationException** hoặc cause liên quan; trường hợp thứ hai thường được giải thích qua condition report và bean registry.

## 13. Các lỗi thường gặp liên quan đến auto-configuration

### 13.1. “Có dependency nhưng bean vẫn không tồn tại”

Nguyên nhân có thể là:

- Dependency chỉ có trên **test** hoặc **compile classpath**, không nằm trong runtime classpath cần thiết.
- Module có class nhưng không công bố auto-configuration ứng viên.
- Auto-configuration đã bị exclude.
- Điều kiện classpath/property/bean/web application không thỏa.
- Auto-configuration chỉ tạo bean khi có một bean phụ thuộc khác.
- Bạn đang inject nhầm kiểu hoặc nhầm tên bean.

Hãy xem **resolved classpath**, condition report và bean definitions tương ứng. Việc thêm một dependency khác mà chưa hiểu điều kiện có thể làm tình hình rối hơn.

### 13.2. “Ứng dụng tự nhiên tạo bean mình không khai báo”

Đó có thể là bean từ auto-configuration. Tìm class định nghĩa bean, kiểm tra đường imports, điều kiện đã thỏa và xem có property để điều chỉnh hay không.

Nếu cần thay đổi hành vi, ưu tiên cơ chế customization mà cấu hình công bố: property, bean do ứng dụng cung cấp, customizer, hoặc exclusion có chủ đích. Không cần viết lại toàn bộ cơ chế Spring chỉ để thay một giá trị mặc định.

### 13.3. “NoSuchBeanDefinitionException dù đã có @Component”

Không phải mọi lỗi thiếu bean đều bắt nguồn từ auto-configuration. Nếu component nằm ngoài phạm vi quét, bị **@Profile** loại hoặc không được import, nó vẫn không được đăng ký.

Ví dụ **@SpringBootApplication** thường component-scan từ package của lớp main và các package con. Đặt một service ở package không thuộc vùng quét có thể khiến DI thất bại.

Việc thay **scanBasePackages** trên @SpringBootApplication chủ yếu tác động **component scanning**, không phải cách Boot tìm toàn bộ auto-configuration candidates. Hai phạm vi có cơ chế khác nhau; cần xác định bean của bạn là **component do ứng dụng định nghĩa** hay **bean do auto-configuration tạo** trước khi sửa.

### 13.4. “NoUniqueBeanDefinitionException: có nhiều bean cùng kiểu”

Điều này cho biết Spring không xác định được một bean duy nhất cho vị trí injection. Có thể ứng dụng tự khai báo nhiều implementation, hoặc một auto-configuration không có điều kiện back off phù hợp.

Cách giải quyết phụ thuộc thiết kế:

- Kiểm tra các bean thực sự được đăng ký.
- Dùng **@Qualifier** nếu bên gọi yêu cầu implementation cụ thể.
- Dùng **@Primary** nếu có một implementation mặc định có ý nghĩa.
- Kiểm tra điều kiện của auto-configuration liên quan nếu có bean ngoài dự kiến.

Không nên tắt auto-configuration ngẫu nhiên chỉ để làm mất một bean nếu ứng dụng vẫn cần các thành phần khác trong cấu hình đó.

### 13.5. “Thêm starter rồi ứng dụng không khởi động”

Thêm starter có thể thay đổi classpath và khiến những điều kiện trước đây không thỏa trở thành thỏa. Một auto-configuration mới có thể bắt đầu tạo bean hoặc yêu cầu một cấu hình môi trường mà ứng dụng chưa chuẩn bị.

Ví dụ có thêm thư viện liên quan dữ liệu, Boot có thể xem xét các cấu hình DataSource/JPA phù hợp, trong khi URL/driver/credentials chưa hoàn chỉnh.

Quy trình điều tra:

1. Đọc **cause chain** trong lỗi startup.
2. Xác định auto-configuration liên quan.
3. So sánh resolved dependencies trước/sau thay đổi.
4. Xác định điều kiện nào đã đổi kết quả.
5. Hoàn thiện cấu hình, điều chỉnh dependency hoặc exclude đúng phần không cần thiết.

### 13.6. “Đã thay property mà hành vi không đổi”

Có thể property được nạp từ nguồn khác có độ ưu tiên cao hơn, profile đang hoạt động khác dự kiến, tên property viết sai hoặc annotation condition không kiểm tra tên/value đó.

Ngoài ra, nếu bạn sửa file trên đĩa sau startup mà không có cơ chế refresh, auto-configuration thường **không tự đánh giá lại**. Trước tiên hãy xác định giá trị property trong **Environment lúc context khởi động** và cách application đang được chạy.

## 14. Các nguyên tắc khi tự viết auto-configuration cho thư viện

Khi một nhóm muốn tạo thư viện Spring Boot dùng chung, auto-configuration có thể giúp consumer chỉ cần thêm dependency và một vài property. Để thư viện hoạt động dự đoán được:

1. **Đăng ký ứng viên đúng cách** trong AutoConfiguration.imports tương ứng với phiên bản Boot mục tiêu.
2. **Chỉ bật tính năng khi dependency cần thiết có mặt**, dùng điều kiện classpath và chia cấu hình khi các kiểu optional có thể vắng mặt.
3. **Cung cấp property rõ ràng**, đặt mặc định hợp lý và mô tả điều kiện bật/tắt.
4. **Nhường chỗ cho bean do ứng dụng định nghĩa** ở những điểm thư viện cho phép customization.
5. **Mô tả ordering** nếu một cấu hình phụ thuộc kết quả của cấu hình tự động khác.
6. **Giữ cấu hình tự động khỏi vùng component-scan thông thường của consumer** để tránh việc phát hiện ngoài ý muốn.
7. **Không giả định ứng dụng là Servlet web** nếu thư viện có thể được dùng trong reactive hoặc non-web context.
8. **Đặt hành vi có side effect trong lifecycle thích hợp**, không biến việc đọc condition thành thực thi nghiệp vụ.

Auto-configuration là cơ chế của **thư viện tích hợp và mặc định**. Nó không thay thế hoàn toàn thiết kế module hoặc quyết định nghiệp vụ của ứng dụng dùng thư viện.

### 14.1. Phân biệt điều kiện có mặt class và khả năng khởi tạo

Một cấu hình có thể thỏa **@ConditionalOnClass** nhưng vẫn thất bại khi tạo bean vì:

- Constructor ném exception.
- Property có mặt nhưng giá trị sai định dạng hoặc không hợp lệ.
- Dependency thấp hơn bị thiếu ở runtime.
- Dịch vụ ngoài không sẵn sàng khi bean khởi tạo.
- Hai thư viện có phiên bản binary không tương thích.

Vì vậy **auto-configuration được chọn** khác với **bean đã khởi tạo thành công**.

### 14.2. Không dùng auto-configuration để che phụ thuộc bắt buộc

Nếu một thư viện **bắt buộc** cần một service, việc im lặng bỏ qua bean chỉ vì service thiếu có thể khiến consumer khó phát hiện cấu hình chưa hoàn chỉnh. Có trường hợp cần điều kiện để module hoàn toàn không tham gia; cũng có trường hợp nên đưa ra thông báo startup rõ ràng hoặc ràng buộc bắt buộc.

Thiết kế phù hợp phụ thuộc hợp đồng của thư viện: một tích hợp **tùy chọn** nên tránh ảnh hưởng ứng dụng không sử dụng nó; một chức năng **đã được người dùng bật rõ ràng** có thể cần báo lỗi nếu cấu hình không đầy đủ.

## 15. Thử phân tích ba kịch bản

### Kịch bản A: Thêm starter web

Ứng dụng ban đầu là một Java command-line app. Bạn thêm starter web, tạo controller và chạy lại.

**Câu hỏi:** Vì sao Boot bắt đầu khởi động HTTP server?

**Cách giải thích:** Classpath chứa thêm những thành phần web thích hợp; Boot xác định loại ứng dụng và xét các auto-configuration tương ứng. Những cấu hình đủ điều kiện có thể thiết lập embedded server và Spring MVC. Controller của bạn được đăng ký qua component scanning và có môi trường xử lý request.

**Chú ý:** Đây là sự phối hợp của dependency resolution, environment, auto-configuration và component scanning, không phải chỉ một annotation đơn lẻ.

### Kịch bản B: Ứng dụng tự cung cấp bean

Thư viện có:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new GreetingService("Xin chào");
}
~~~

Ứng dụng thêm:

~~~java
@Bean
GreetingService greetingServiceForApp() {
    return new GreetingService("Chào từ ứng dụng");
}
~~~

**Câu hỏi:** Có hai bean GreetingService không?

**Cách giải thích:** Theo ý đồ thông thường của auto-configuration, nếu bean ứng dụng đã được biết khi điều kiện được xét, **@ConditionalOnMissingBean** sẽ không đăng ký bean mặc định. Cần xem condition report và quá trình đăng ký bean để xác định chính xác tình huống thực tế.

### Kịch bản C: Property không bật tính năng

Thư viện dùng:

~~~java
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Ứng dụng không khai báo **demo.greeting.enabled**.

**Câu hỏi:** Tại sao GreetingService không xuất hiện?

**Cách giải thích:** Vì property vắng mặt và **matchIfMissing=false**, điều kiện không thỏa. Muốn bật tính năng, cần khai báo property phù hợp hoặc thay đổi hợp đồng mặc định của thư viện. Không phải lỗi của IoC container.

## 16. Các ngộ nhận cần tránh

**“@EnableAutoConfiguration quét toàn bộ class và tự biến tất cả thành bean.”**  
Không. Nó dùng danh sách ứng viên auto-configuration và hệ thống condition; component scanning là cơ chế riêng.

**“Thêm starter là mọi auto-configuration trong starter đều bật.”**  
Không. Classpath là một tín hiệu, còn property, bean, loại web application và các điều kiện khác vẫn có thể khiến cấu hình bị bỏ qua.

**“@ConditionalOnClass có nghĩa đã có bean.”**  
Không. Class có thể tồn tại mà chưa có bean definition tương ứng.

**“@ConditionalOnMissingBean ghi đè bean cũ sau khi khởi động.”**  
Không. Nó kiểm tra điều kiện trong quá trình xử lý cấu hình và đăng ký bean; không phải cơ chế thay bean runtime.

**“Positive match chứng minh tất cả bean trong auto-configuration đã được tạo.”**  
Không. Có thể vẫn có điều kiện ở cấp method hoặc lỗi lúc khởi tạo bean.

**“Negative match có nghĩa ứng dụng bị cấu hình sai.”**  
Không. Việc bỏ qua cấu hình không cần thiết là mục tiêu bình thường của Spring Boot.

**“Exclude auto-configuration tương đương xóa thư viện khỏi classpath.”**  
Không. Exclusion xử lý cấu hình; dependency graph thuộc công cụ build.

**“Đổi application.yml lúc chạy sẽ lập tức đổi các quyết định điều kiện.”**  
Không mặc nhiên. Conditions thường được đánh giá khi xây dựng context.

**“Mọi bean do Spring quản lý đều đến từ auto-configuration.”**  
Không. Bean có thể được định nghĩa qua **@Bean**, component scan, import, các cơ chế đăng ký khác hoặc auto-configuration.

**“Spring Boot sẽ tự chữa mọi cấu hình thiếu.”**  
Không. Auto-configuration cung cấp mặc định hợp lý khi có đủ tín hiệu; dependency bắt buộc, endpoint, kết nối bên ngoài và nghiệp vụ riêng vẫn phải được ứng dụng xác định.

## 17. Cách vận dụng khi đọc một ứng dụng Spring Boot

Khi muốn hiểu vì sao một bean tồn tại hoặc bị thiếu, hãy lần theo chuỗi:

~~~text
1. Dependency nào cung cấp class / module liên quan?
                     │
                     ▼
2. Auto-configuration ứng viên có được đăng ký không?
                     │
                     ▼
3. Có bị exclude bằng annotation/property không?
                     │
                     ▼
4. Những @Conditional... nào được khai báo?
                     │
                     ▼
5. Classpath, property, web type, bean hiện có ra sao?
                     │
                     ▼
6. Bean definition có được đăng ký?
                     │
                     ▼
7. Bean có được tạo thành công khi cần?
                     │
                     ▼
8. Ứng dụng sử dụng bean đó như thế nào?
~~~

Chuỗi này kết nối ba lớp kiến thức quan trọng: **dependency và classpath**, **Spring IoC container**, và **Spring Boot auto-configuration**. Khi cần chẩn đoán, condition evaluation report sẽ giúp giải thích bước chọn cấu hình, còn stack trace và log startup sẽ giúp hiểu lỗi trong giai đoạn tạo bean hoặc thực thi.

## Ghi nhớ cốt lõi

**@EnableAutoConfiguration** kích hoạt cơ chế để Spring Boot tìm và xem xét các auto-configuration đã được đăng ký. Các điều kiện như **@ConditionalOnClass**, **@ConditionalOnProperty**, **@ConditionalOnBean**, **@ConditionalOnMissingBean** và **@ConditionalOnWebApplication** quyết định cấu hình hoặc bean nào có thể tham gia ứng dụng.

Trong **@SpringBootApplication**, auto-configuration phối hợp với cấu hình Spring và component scanning, nhưng đảm nhiệm vai trò riêng: **cung cấp hạ tầng và các mặc định phù hợp với ngữ cảnh hiện tại**. Nhờ hiểu cách lựa chọn theo điều kiện, bạn có thể giải thích được vì sao một bean xuất hiện, vì sao Spring Boot nhường chỗ cho bean ứng dụng, và vì sao thêm một dependency hoặc thay đổi property có thể làm startup của hệ thống thay đổi.
