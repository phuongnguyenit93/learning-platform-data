# Theo dõi một ví dụ từ dependency đến bean được tạo

Spring Boot auto-configuration giúp ứng dụng có thể sử dụng nhiều thành phần chỉ bằng cách thêm dependency và khai báo cấu hình cần thiết. Khi thêm một starter như web, JDBC hoặc thư viện tích hợp do nhóm phát triển, Spring Boot có thể phát hiện các lớp cấu hình tự động trên classpath, đánh giá điều kiện và đăng ký bean phù hợp vào `ApplicationContext`.

Tuy nhiên, quá trình này gồm nhiều bước riêng biệt. **Thêm dependency không trực tiếp tạo bean**: dependency làm cho class và metadata có mặt trên classpath; auto-configuration được Spring Boot nạp; các điều kiện được kiểm tra; bean definition được đăng ký; sau đó container mới khởi tạo object và inject dependency.

Bài học theo dõi một ví dụ xuyên suốt: ứng dụng thêm `acme-greeting-spring-boot-starter`, Spring Boot phát hiện auto-configuration của thư viện, đăng ký `GreetingClient` nếu điều kiện phù hợp, rồi inject bean đó vào service của ứng dụng. Qua ví dụ này, bạn sẽ thấy mối liên hệ giữa build dependency, metadata, condition evaluation, bean definition và bean lifecycle.

Các ví dụ hướng tới Spring Boot 3.x và Java 17/21. Tên package và một số chi tiết nội bộ có thể thay đổi giữa các phiên bản, nhưng đường đi kiến trúc cơ bản vẫn như nhau.

## 1. Bức tranh tổng thể: từ dependency đến object

Một ứng dụng sử dụng thư viện auto-configuration trải qua chuỗi khái quát:

~~~mermaid
flowchart TD
    A["Thêm starter vào build"] --> B["Starter và các dependency nằm trên runtime classpath"]
    B --> C["SpringApplication khởi động"]
    C --> D["@SpringBootApplication bật auto-configuration"]
    D --> E["Đọc AutoConfiguration.imports từ các JAR"]
    E --> F["Lọc candidate và đánh giá conditions"]
    F --> G["Đăng ký các BeanDefinition phù hợp"]
    G --> H["ApplicationContext refresh"]
    H --> I["Tạo singleton bean và resolve dependency"]
    I --> J["GreetingClient trở thành bean sẵn sàng sử dụng"]
    J --> K["Service / Controller nhận bean qua injection"]
~~~

Có ba lớp cần phân biệt:

1. **Build dependency:** Gradle hoặc Maven đưa artifact và các dependency bắc cầu vào classpath.
2. **Auto-configuration:** Spring Boot tìm lớp cấu hình tự động, kiểm tra điều kiện và đăng ký bean definition.
3. **Bean lifecycle:** Spring container tạo instance, inject dependency, gọi callback khởi tạo và quản lý vòng đời.

Nếu hiểu ba lớp này, bạn sẽ chẩn đoán chính xác hơn các tình huống như “đã thêm starter nhưng không thấy bean”, “bean chỉ xuất hiện ở profile này” hoặc “bean mặc định không được tạo vì ứng dụng đã khai báo implementation riêng”.

## 2. Chuẩn bị ví dụ: một thư viện Greeting

Giả sử nhóm phát triển thư viện dùng chung để tạo lời chào. Thư viện cung cấp một class Java thuần:

~~~java
package com.acme.greeting;

public class GreetingClient {
    private final String prefix;

    public GreetingClient(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return prefix + ", " + name + "!";
    }
}
~~~

Class này không mang `@Component` hay `@Service`. Nó chỉ là một class Java. Khi ứng dụng dùng thư viện, ta muốn Spring Boot tự đăng ký nó thành bean với cấu hình phù hợp.

Cấu trúc artifact có thể chia thành hai module:

~~~text
acme-greeting/
├── acme-greeting-core/
│   └── GreetingClient.java
├── acme-greeting-spring-boot-autoconfigure/
│   ├── GreetingProperties.java
│   ├── GreetingAutoConfiguration.java
│   └── META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-greeting-spring-boot-starter/
    └── build.gradle
~~~

Vai trò:

- `acme-greeting-core` chứa API/logic Java thuần.
- `acme-greeting-spring-boot-autoconfigure` chứa cấu hình Spring Boot và metadata để đăng ký cấu hình đó.
- `acme-greeting-spring-boot-starter` là dependency tiện dụng, kéo auto-configuration module và các thư viện cần thiết vào ứng dụng.

Không bắt buộc mọi thư viện phải có đủ ba module. Với thư viện nhỏ, có thể gộp core và auto-configuration. Tách starter riêng hữu ích khi muốn cung cấp một dependency đơn giản cho người dùng thư viện.

## 3. Bước 1 — Thêm dependency vào ứng dụng

Giả sử ứng dụng dùng Gradle và Spring Boot plugin/dependency management đã được cấu hình ở cấp project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.acme:acme-greeting-spring-boot-starter:1.0.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Hoặc nếu đang phát triển multi-project trong cùng repository:

~~~groovy
dependencies {
    implementation project(':acme-greeting-spring-boot-starter')
}
~~~

Starter có thể khai báo dependency tới module auto-configuration:

~~~groovy
dependencies {
    api project(':acme-greeting-spring-boot-autoconfigure')
}
~~~

Module auto-configuration lại phụ thuộc vào core và Spring Boot auto-configuration API:

~~~groovy
dependencies {
    implementation project(':acme-greeting-core')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Các đoạn build trên chỉ minh họa quan hệ dependency. Trong dự án thật, phiên bản Spring Boot, Java toolchain, plugin và dependency management phải được đồng bộ theo cấu hình repository.

### 3.1. Gradle làm gì khi resolve dependency?

Khi build hoặc chạy ứng dụng, Gradle giải quyết đồ thị dependency:

~~~mermaid
flowchart TD
    APP["Ứng dụng demo"] --> WEB["spring-boot-starter-web"]
    APP --> STARTER["acme-greeting-spring-boot-starter"]
    STARTER --> AUTO["acme-greeting-spring-boot-autoconfigure"]
    AUTO --> CORE["acme-greeting-core"]
    AUTO --> BOOTAUTO["spring-boot-autoconfigure"]
~~~

Gradle sẽ:

- Tìm artifact theo tọa độ dependency.
- Resolve phiên bản trực tiếp và bắc cầu.
- Đưa các class/resource cần thiết vào compile/runtime classpath.
- Đảm bảo các module liên quan được build theo dependency graph.

Sau bước này, class `GreetingAutoConfiguration` và file metadata của nó có thể có mặt trong runtime classpath của ứng dụng.

**Điều chưa xảy ra:** Gradle không khởi tạo `GreetingClient` và không đăng ký bean vào `ApplicationContext`. Build system chỉ chuẩn bị artifact để ứng dụng có thể sử dụng khi chạy.

### 3.2. Starter khác auto-configuration library thế nào?

| Thành phần | Trách nhiệm |
| --- | --- |
| Starter | Dependency entry point thuận tiện, tập hợp các module cần thiết |
| Auto-configuration module | Cung cấp các lớp cấu hình tự động và metadata |
| Core/library module | Cung cấp class và logic mà bean sẽ sử dụng |
| Ứng dụng tiêu thụ | Cung cấp property, custom bean và entry point chạy |

Một starter không nhất thiết chứa code Java. Nhiều starter chỉ là một artifact có các dependency khai báo trong metadata build.

## 4. Bước 2 — Ứng dụng bật cơ chế auto-configuration

Lớp chạy chính:

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

`@SpringBootApplication` là annotation tổng hợp, thường được hiểu qua ba phần chính:

- `@SpringBootConfiguration`: đánh dấu nguồn cấu hình chính của ứng dụng.
- `@EnableAutoConfiguration`: bật cơ chế auto-configuration của Spring Boot.
- `@ComponentScan`: quét component từ package của class ứng dụng và các package con theo cấu hình mặc định.

Trong bài học này, `@EnableAutoConfiguration` là phần mở đầu cho đường đi từ dependency đến bean.

### 4.1. @EnableAutoConfiguration làm gì?

`@EnableAutoConfiguration` sử dụng cơ chế import của Spring để đưa `AutoConfigurationImportSelector` vào quá trình xử lý cấu hình.

Ở mức khái niệm:

~~~java
@SpringBootApplication
public class DemoApplication {
}
~~~

tương đương ứng dụng đã bật một cấu hình chứa ý nghĩa của `@EnableAutoConfiguration`. Bạn không cần tự viết selector hoặc tự đọc file imports trong ứng dụng bình thường.

`AutoConfigurationImportSelector` là một thành phần hạ tầng của Spring Boot. Nó tìm các candidate auto-configuration từ metadata có trên classpath, áp dụng exclusions/filters và trả về các cấu hình được chọn để Spring xử lý.

Không nên nhầm việc này với component scanning:

- Component scan tìm các class component như `@Component`, `@Service`, `@Repository` và `@Controller` trong package được quét.
- Auto-configuration import tìm các lớp cấu hình được khai báo trong metadata của các artifact trên classpath.

Một class auto-configuration có thể nằm trong package ngoài vùng component scan của ứng dụng mà vẫn được import nhờ metadata.

## 5. Bước 3 — Đăng ký auto-configuration trong metadata

Trong Spring Boot 3, thư viện đăng ký lớp auto-configuration bằng file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đặt file trong module auto-configuration tại:

~~~text
acme-greeting-spring-boot-autoconfigure/
└── src/main/resources/
    └── META-INF/
        └── spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Mỗi dòng chứa tên đầy đủ của một lớp auto-configuration. Khi JAR được đưa vào runtime classpath, Spring Boot có thể đọc danh sách này để khám phá candidate.

### 5.1. Vì sao file metadata quan trọng?

Giả sử module có class:

~~~java
package com.acme.greeting.autoconfigure;

@AutoConfiguration
public class GreetingAutoConfiguration {
}
~~~

Chỉ viết `@AutoConfiguration` chưa tự bảo đảm class sẽ được Spring Boot tự khám phá từ một JAR thư viện. Nó còn cần được đăng ký vào cơ chế import candidate, thông thường bằng `AutoConfiguration.imports`.

Đây là điểm phân biệt với component scan: không cần đặt class auto-configuration trong package con của `DemoApplication` nếu metadata đã đăng ký đúng.

### 5.2. Boot 3 và spring.factories

Ở các phiên bản Spring Boot cũ, auto-configuration thường được đăng ký trong `META-INF/spring.factories` dưới key `EnableAutoConfiguration`. Spring Boot 2.7 là giai đoạn chuyển tiếp, còn với auto-configuration viết cho Boot 3, dùng `AutoConfiguration.imports`.

`spring.factories` vẫn được sử dụng cho một số extension point khác. Không nên suy luận rằng mọi chức năng từng đăng ký trong file đó đều đã biến mất; thay đổi ở đây nói riêng về việc liệt kê auto-configuration candidate.

## 6. Bước 4 — Spring Boot đọc candidate và đánh giá điều kiện

Một auto-configuration không có nghĩa mọi bean trong đó luôn được đăng ký. Spring Boot dùng các condition để chỉ bật cấu hình khi môi trường phù hợp.

Ba condition rất phổ biến:

| Annotation | Câu hỏi được kiểm tra |
| --- | --- |
| `@ConditionalOnClass` | Class cần thiết có trên classpath không? |
| `@ConditionalOnProperty` | Property có tồn tại hoặc có giá trị phù hợp không? |
| `@ConditionalOnMissingBean` | Đã có bean do ứng dụng hoặc cấu hình khác cung cấp chưa? |

Các condition khác gồm `@ConditionalOnBean`, `@ConditionalOnResource`, `@ConditionalOnWebApplication` và `@ConditionalOnSingleCandidate`.

### 6.1. ConditionalOnClass

Ví dụ một integration chỉ có ý nghĩa khi SDK tùy chọn có trên classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.GreetingSdk")
public class VendorGreetingAutoConfiguration {
    // Cấu hình chỉ phù hợp khi SDK có mặt.
}
~~~

Dùng thuộc tính `name` cho phép biểu diễn tên class dưới dạng chuỗi, hữu ích khi class tùy chọn không có mặt lúc biên dịch module cấu hình.

Nếu auto-configuration trực tiếp tham chiếu kiểu tùy chọn trong method signature hoặc field, cần đặt cấu hình đó ở vị trí phù hợp để JVM không phải load kiểu thiếu trước khi condition loại nó. Một pattern phổ biến là tách cấu hình tùy chọn vào static nested configuration được đánh dấu condition.

### 6.2. ConditionalOnProperty

Ví dụ chỉ bật một integration khi người dùng cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {
}
~~~

Ý nghĩa:

- Property đầy đủ là `acme.greeting.enabled`.
- Nếu giá trị là `true`, condition khớp.
- Nếu property không được khai báo, `matchIfMissing = true` cho phép bật theo mặc định.
- Nếu property được đặt `false`, condition không khớp.

Nếu muốn integration mặc định tắt, có thể dùng `matchIfMissing = false` hoặc đặt property bắt buộc theo cách phù hợp. Hãy chọn default rõ ràng và ghi trong tài liệu starter.

### 6.3. ConditionalOnMissingBean

Auto-configuration thường cung cấp bean mặc định nhưng cho phép ứng dụng thay thế:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingClient.class)
GreetingClient greetingClient(GreetingProperties properties) {
    return new GreetingClient(properties.getPrefix());
}
~~~

Nếu ứng dụng đã đăng ký bean `GreetingClient` phù hợp, bean mặc định này không được đăng ký. Đây là một điểm mở rộng quan trọng: thư viện đưa ra default behavior, còn ứng dụng giữ quyền tùy biến.

`@ConditionalOnMissingBean` không xóa bean người dùng và cũng không thay thế bean đã đăng ký. Nó chỉ quyết định bean method mặc định có được đóng góp bean definition hay không.

## 7. Bước 5 — Viết cấu hình properties của thư viện

Thư viện muốn người dùng cấu hình prefix. Tạo class:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {
    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Class dùng `@ConfigurationProperties` để bind nhóm property có tiền tố `acme.greeting`.

Cấu hình ứng dụng:

~~~yaml
acme:
  greeting:
    enabled: true
    prefix: Xin chào
~~~

Đăng ký properties trong auto-configuration bằng:

~~~java
@EnableConfigurationProperties(GreetingProperties.class)
~~~

Khi configuration được xử lý, Spring Boot đăng ký bean properties và bind giá trị từ `Environment` vào object đó.

`GreetingProperties` không cần đặt `@Component` nếu đã được đăng ký bằng `@EnableConfigurationProperties` hoặc cơ chế scan configuration properties thích hợp. Tránh đăng ký trùng cùng một kiểu properties qua nhiều cơ chế mà không có chủ đích.

## 8. Bước 6 — Tạo auto-configuration class

Bây giờ viết lớp cấu hình tự động:

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.greeting",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    @ConditionalOnMissingBean(GreetingClient.class)
    public GreetingClient greetingClient(GreetingProperties properties) {
        return new GreetingClient(properties.getPrefix());
    }
}
~~~

Phân tích:

- `@AutoConfiguration` đánh dấu class là Spring Boot auto-configuration.
- `@EnableConfigurationProperties` đăng ký và bind `GreetingProperties`.
- `@Bean` khai báo một factory method tạo `GreetingClient`.
- `@ConditionalOnProperty` quyết định có bật bean theo cấu hình không.
- `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp bean riêng.
- Tham số `GreetingProperties` được Spring resolve từ context khi gọi factory method.

Lưu ý: ví dụ này không cần `@ConditionalOnClass(GreetingClient.class)` vì `GreetingClient` là một phần bắt buộc của cùng thư viện core mà auto-configuration đang phụ thuộc. Trong một integration tùy chọn, condition classpath nên kiểm tra class thực sự đến từ dependency tùy chọn, không thêm condition hình thức mà lúc nào cũng đúng.

### 8.1. Auto-configuration class có tự tạo bean ngay khi được import không?

Không nhất thiết. Auto-configuration class là một cấu hình được đưa vào quá trình xử lý bean definition. Các phương thức `@Bean` đóng góp bean definition nếu điều kiện tương ứng khớp.

Quá trình đăng ký definition khác với việc tạo object. Đến giai đoạn refresh và pre-instantiation, container mới tạo singleton bean eager khi cần, resolve tham số factory method và thực hiện lifecycle.

### 8.2. Điều kiện trên class và điều kiện trên bean method

Condition đặt trên class ảnh hưởng đến việc cấu hình đó có được xử lý hay không. Condition đặt trên bean method quyết định bean definition cụ thể có được đăng ký hay không.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingClient.class)
    GreetingClient greetingClient(GreetingProperties properties) {
        return new GreetingClient(properties.getPrefix());
    }
}
~~~

Nếu property không khớp ở cấp class, cấu hình này không đóng góp bean method nào. Nếu class-level condition khớp nhưng ứng dụng đã có bean `GreetingClient`, method-level condition loại bean mặc định.

## 9. Bước 7 — Spring Boot đăng ký bean definition

Khi auto-configuration candidate được chọn và condition khớp, Spring xử lý class cấu hình như một configuration source.

Tại giai đoạn này, container đăng ký các bean definition, tức metadata mô tả cách tạo bean:

- Bean type hoặc factory method trả về kiểu nào.
- Tên bean là gì.
- Scope nào được sử dụng.
- Dependency của factory method là gì.
- Initialization/destruction method nào được cấu hình.
- Condition nào đã cho phép bean được đăng ký.

Ví dụ method:

~~~java
@Bean
GreetingClient greetingClient(GreetingProperties properties) {
    return new GreetingClient(properties.getPrefix());
}
~~~

đóng góp một bean definition có factory method là `greetingClient`. Tên bean mặc định thường là tên method, trong trường hợp này là `greetingClient`.

Cần phân biệt:

| Thời điểm | Kết quả |
| --- | --- |
| Auto-configuration candidate được import | Spring xử lý cấu hình |
| Condition khớp | Bean method được phép đóng góp definition |
| Bean definition được đăng ký | Container biết cách tạo bean |
| Bean được instantiate | Object Java thực sự được tạo |
| Bean initialization hoàn tất | Object sẵn sàng để sử dụng |

Việc có bean definition không đồng nghĩa object đã được tạo ngay ở đúng thời điểm đó. Với singleton không lazy, Spring thường khởi tạo sớm trong quá trình refresh. Với lazy bean hoặc bean chỉ được yêu cầu khi runtime, instance có thể được tạo muộn hơn.

## 10. Bước 8 — ApplicationContext refresh và tạo bean

Sau khi xử lý cấu hình, Spring refresh context. Trong quá trình này, các singleton non-lazy được pre-instantiate theo dependency graph và các quy tắc lifecycle.

Với `GreetingClient`, factory method cần `GreetingProperties`:

~~~mermaid
flowchart TD
    A["Refresh ApplicationContext"] --> B["Tìm singleton eager cần tạo"]
    B --> C["Yêu cầu GreetingClient"]
    C --> D["Resolve tham số GreetingProperties"]
    D --> E["Lấy bean properties đã bind"]
    E --> F["Gọi @Bean method greetingClient(...)"]
    F --> G["new GreetingClient(prefix)"]
    G --> H["BeanPostProcessor / initialization"]
    H --> I["GreetingClient sẵn sàng"]
~~~

Từng bước:

1. Container cần tạo `GreetingClient`.
2. Spring xem factory method và nhận ra nó cần `GreetingProperties`.
3. `GreetingProperties` đã được đăng ký qua `@EnableConfigurationProperties`.
4. Spring resolve bean properties và bảo đảm giá trị đã được bind theo cấu hình.
5. Spring gọi `greetingClient(properties)`.
6. Method trả về instance `GreetingClient`.
7. Instance đi qua các bước post-processing và lifecycle phù hợp.
8. Bean được lưu trong singleton registry của context để các consumer sử dụng.

### 10.1. Constructor của GreetingClient chạy ở đâu?

Trong ví dụ, dòng:

~~~java
return new GreetingClient(properties.getPrefix());
~~~

là nơi object thực sự được tạo. Nhưng object đó được tạo bên trong factory method do Spring quản lý, nên kết quả trả về được đăng ký thành bean.

Đây là điểm quan trọng: class `GreetingClient` không cần stereotype annotation để trở thành bean. Nó được Spring quản lý vì một phương thức `@Bean` trả về instance của nó.

### 10.2. BeanPostProcessor và initialization

Sau khi instance được tạo và dependencies được cung cấp, Spring áp dụng các bước lifecycle như aware callbacks, BeanPostProcessor và initialization callback theo quy tắc của container.

Nếu `GreetingClient` có `@PostConstruct`, callback sẽ chạy trong giai đoạn initialization thích hợp. Nếu có AOP hoặc post-processor tạo proxy, reference cuối cùng được expose cho consumer có thể là proxy thay vì raw target instance.

Ví dụ này không cần lifecycle callback hay proxy, nhưng cơ chế quản lý bean vẫn áp dụng.

## 11. Bước 9 — Consumer nhận bean qua constructor injection

Trong ứng dụng demo:

~~~java
package com.example.demo;

import com.acme.greeting.GreetingClient;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final GreetingClient greetingClient;

    public WelcomeService(GreetingClient greetingClient) {
        this.greetingClient = greetingClient;
    }

    public String welcome(String name) {
        return greetingClient.greet(name);
    }
}
~~~

`WelcomeService` được component scan phát hiện vì nó nằm trong package con của class ứng dụng. Khi Spring tạo service, nó cần một bean `GreetingClient`.

Bean đó đã được auto-configuration đăng ký, vì vậy constructor injection thành công.

Có thể dùng trong controller:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {
    private final WelcomeService service;

    public WelcomeController(WelcomeService service) {
        this.service = service;
    }

    @GetMapping("/welcome/{name}")
    public String welcome(@PathVariable String name) {
        return service.welcome(name);
    }
}
~~~

Với cấu hình:

~~~yaml
acme:
  greeting:
    enabled: true
    prefix: Xin chào
~~~

request:

~~~http
GET /welcome/Phuong
~~~

có thể trả về:

~~~text
Xin chào, Phuong!
~~~

Toàn bộ luồng:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot app
    participant Import as AutoConfigurationImportSelector
    participant Auto as GreetingAutoConfiguration
    participant Context as ApplicationContext
    participant Service as WelcomeService
    App->>Import: Khởi động và bật auto-configuration
    Import->>Import: Đọc AutoConfiguration.imports
    Import->>Auto: Chọn candidate, kiểm tra condition
    Auto->>Context: Đăng ký bean definitions
    Context->>Context: Bind GreetingProperties
    Context->>Context: Gọi greetingClient(properties)
    Context->>Context: Lưu GreetingClient singleton
    Context->>Service: Inject GreetingClient
    Service-->>App: WelcomeService sẵn sàng
~~~

## 12. Bước 10 — Ứng dụng có thể override bean mặc định

Auto-configuration tốt thường cung cấp default bean nhưng không khóa ứng dụng vào implementation đó.

Giả sử ứng dụng muốn thay `GreetingClient` bằng custom implementation. Tạo bean:

~~~java
package com.example.demo;

import com.acme.greeting.GreetingClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreetingConfiguration {

    @Bean
    GreetingClient greetingClient() {
        return new GreetingClient("Welcome");
    }
}
~~~

Khi Spring đánh giá `@ConditionalOnMissingBean(GreetingClient.class)` trong auto-configuration, bean do ứng dụng cung cấp được ưu tiên theo thứ tự xử lý cấu hình thông thường. Bean mặc định của thư viện không được đăng ký.

Kết quả:

- Ứng dụng có một bean `GreetingClient` tùy biến.
- Auto-configuration vẫn có thể được import.
- Bean method mặc định bị bỏ qua do condition không khớp.
- `WelcomeService` vẫn inject theo kiểu `GreetingClient` mà không cần biết implementation được cung cấp từ đâu.

Đây là một hợp đồng quan trọng của thư viện auto-configuration: **cung cấp mặc định hợp lý, đồng thời tôn trọng cấu hình của ứng dụng tiêu thụ**.

### 12.1. @ConditionalOnMissingBean không phải @Primary

Hai cơ chế khác nhau:

| Cơ chế | Tác dụng |
| --- | --- |
| `@ConditionalOnMissingBean` | Không đăng ký bean mặc định nếu đã có bean phù hợp |
| `@Primary` | Chọn một bean ưu tiên khi nhiều bean cùng kiểu đã tồn tại |
| `@Qualifier` | Lọc bean candidate theo metadata tại injection point |

Nếu ứng dụng muốn thay default, `@ConditionalOnMissingBean` phù hợp. Nếu ứng dụng muốn giữ nhiều implementation và chọn một mặc định, `@Primary` có thể phù hợp. Nếu consumer cần một loại implementation theo vai trò, dùng qualifier.

### 12.2. Vì sao thứ tự cấu hình lại quan trọng?

Auto-configuration được thiết kế để xử lý sau các cấu hình do người dùng khai báo, giúp condition như `@ConditionalOnMissingBean` có thể nhìn thấy bean definitions mà ứng dụng đã đóng góp.

Nếu có auto-configuration phụ thuộc cấu hình khác, có thể dùng `@AutoConfigureAfter`, `@AutoConfigureBefore` hoặc `@AutoConfigureOrder` để điều khiển thứ tự xử lý giữa các auto-configuration.

Những annotation này sắp xếp **cấu hình tự động**, không phải cách điều khiển thứ tự khởi tạo mọi object trong container. Không nên dùng `@DependsOn` hoặc `@Order` thay thế cho auto-configuration ordering khi mục tiêu là thứ tự xử lý các cấu hình.

## 13. Nếu condition không khớp thì điều gì xảy ra?

Thử đặt:

~~~yaml
acme:
  greeting:
    enabled: false
~~~

Với `@ConditionalOnProperty` trong ví dụ, bean mặc định `GreetingClient` không được đăng ký.

Nếu `WelcomeService` vẫn yêu cầu `GreetingClient` qua constructor, ứng dụng có thể thất bại khi khởi tạo context vì thiếu bean.

Điều đó không có nghĩa condition hoạt động sai. Nó có nghĩa cấu hình tắt feature nhưng consumer vẫn khai báo dependency bắt buộc.

Có ba cách thiết kế tùy ý nghĩa feature:

1. **Feature bắt buộc:** không cho phép tắt nếu consumer cần bean; loại property enable hoặc validation cấu hình phù hợp.
2. **Feature tùy chọn:** consumer phải xử lý trường hợp không có bean, ví dụ inject `ObjectProvider<GreetingClient>` hoặc một abstraction optional.
3. **No-op default:** khi feature tắt, auto-configuration vẫn đăng ký một implementation không thực hiện side effect nhưng đáp ứng hợp đồng.

Ví dụ no-op:

~~~java
public class DisabledGreetingClient extends GreetingClient {
    public DisabledGreetingClient() {
        super("");
    }

    @Override
    public String greet(String name) {
        return name;
    }
}
~~~

Đây chỉ là minh họa cho một default behavior; trong ứng dụng thật, nên thiết kế interface/contract phù hợp thay vì kế thừa một class chỉ để lách cấu hình. Mấu chốt là condition và consumer phải có hợp đồng nhất quán.

## 14. Theo dõi một auto-configuration có sẵn của Spring Boot

Ví dụ Greeting ở trên là thư viện tự xây để thấy rõ từng thành phần. Trong ứng dụng thực tế, cùng một cơ chế được dùng cho nhiều bean hạ tầng có sẵn.

Ví dụ với JDBC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

Ứng dụng cấu hình datasource:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/shop
    username: app_user
    password: change-me
~~~

Ở mức khái niệm:

1. Starter JDBC đưa Spring JDBC, connection pool mặc định phù hợp và các dependency liên quan vào classpath.
2. Driver MySQL được thêm vào runtime classpath.
3. `@SpringBootApplication` bật auto-configuration.
4. Spring Boot phát hiện các auto-configuration liên quan JDBC/DataSource từ metadata của Spring Boot.
5. Các condition kiểm tra class JDBC, connection factory, loại datasource, pool có sẵn và bean do ứng dụng cung cấp.
6. Cấu hình datasource phù hợp có thể đăng ký bean `DataSource` và bind các thuộc tính từ `spring.datasource`.
7. Các auto-configuration khác như JDBC template có thể sử dụng bean `DataSource` đã có để cung cấp `JdbcTemplate`.
8. Service có thể inject `JdbcTemplate` hoặc repository phù hợp.

Đây là mô tả đường đi kiến trúc, không phải danh sách đầy đủ từng condition hoặc mọi nhánh implementation của một phiên bản Spring Boot cụ thể. Lựa chọn pool và bean chi tiết phụ thuộc dependency, version, classpath và cấu hình ứng dụng.

Ví dụ service dùng JDBC:

~~~java
@Repository
public class ProductQuery {
    private final JdbcTemplate jdbcTemplate;

    public ProductQuery(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countProducts() {
        return jdbcTemplate.queryForObject(
                "select count(*) from product",
                Integer.class
        );
    }
}
~~~

`JdbcTemplate` không cần được tạo thủ công trong service. Khi auto-configuration điều kiện phù hợp, Spring Boot có thể đăng ký bean để ứng dụng inject.

Để kiểm tra chính xác auto-configuration của phiên bản đang dùng, xem condition report hoặc tài liệu API của chính phiên bản đó; đừng phụ thuộc vào tên class nội bộ của một bản Boot rồi coi nó bất biến qua mọi phiên bản.

## 15. Chẩn đoán: vì sao bean không được tạo?

Khi thêm starter nhưng không inject được bean, hãy kiểm tra theo đường đi từ ngoài vào trong.

| Triệu chứng | Lớp cần kiểm tra | Câu hỏi |
| --- | --- | --- |
| Không compile được class của thư viện | Build dependency | Artifact có trong compile classpath không? |
| Compile được nhưng không thấy auto-configuration | Runtime dependency/metadata | JAR có mặt ở runtime? File imports có được đóng gói? |
| Auto-configuration không xuất hiện trong report | Candidate discovery/filter/exclusion | Tên class có trong imports? Có bị exclude hoặc filter không? |
| Auto-configuration được tìm thấy nhưng không match | Conditions | Classpath, property, bean hoặc web condition nào không khớp? |
| Auto-configuration match nhưng bean không có | Bean method condition | Có condition khác loại bean method không? |
| Bean mặc định không xuất hiện, nhưng ứng dụng chạy | User override | Ứng dụng đã có bean phù hợp nên missing-bean condition bỏ qua? |
| Có nhiều bean cùng kiểu | Dependency resolution | Cần qualifier hay primary không? |
| Bean xuất hiện nhưng dependency vẫn lỗi | Bean graph | Một dependency sâu hơn chưa được đăng ký? |
| Chỉ lỗi ở một profile | Property/profile source | Giá trị cấu hình thực tế và profile active là gì? |

### 15.1. Bật debug condition report

Có thể chạy ứng dụng với:

~~~bash
java -jar app.jar --debug
~~~

Hoặc cấu hình log/debug phù hợp khi phát triển. Spring Boot in báo cáo condition để cho biết auto-configuration nào match và không match.

Trong report, chú ý các nhóm:

- Positive matches: cấu hình/condition đã thỏa mãn.
- Negative matches: cấu hình bị loại và lý do.
- Exclusions: cấu hình bị loại trừ tường minh.
- Unconditional classes: các cấu hình không cần condition thông thường.

Đây là một trong những cách hữu ích nhất để hiểu vì sao starter không tạo bean như mong đợi.

### 15.2. Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator và endpoint phù hợp được bật/expose, endpoint `/actuator/conditions` có thể hiển thị condition evaluation report.

Chỉ expose endpoint chẩn đoán theo chính sách quản trị và bảo mật của môi trường. Không mở rộng endpoint quản trị ra mạng công khai chỉ để debug nhanh.

### 15.3. Kiểm tra artifact và metadata

Nếu auto-configuration không được phát hiện, hãy kiểm tra JAR của module thư viện có chứa resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

và dòng class name có đúng package/case hay không. File phải nằm trong resource source set để được đóng gói vào artifact. Nếu chỉ tồn tại trong thư mục test hoặc bị build exclude, ứng dụng tiêu thụ sẽ không đọc được.

## 16. Kiểm thử auto-configuration với ApplicationContextRunner

Thư viện auto-configuration nên kiểm thử điều kiện bằng context nhỏ, không cần khởi động cả ứng dụng web.

Spring Boot cung cấp `ApplicationContextRunner` trong test support. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.acme.greeting.GreetingClient;
import com.acme.greeting.autoconfigure.GreetingAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class)
                    );

    @Test
    void createsDefaultClientWhenEnabled() {
        contextRunner
                .withPropertyValues(
                        "acme.greeting.enabled=true",
                        "acme.greeting.prefix=Hello"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingClient.class);
                    assertThat(context.getBean(GreetingClient.class).greet("Sam"))
                            .isEqualTo("Hello, Sam!");
                });
    }

    @Test
    void doesNotCreateClientWhenDisabled() {
        contextRunner
                .withPropertyValues("acme.greeting.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(GreetingClient.class)
                );
    }
}
~~~

Test này trực tiếp nạp class auto-configuration bằng `AutoConfigurations.of`. Nó kiểm tra condition và bean factory method, nhưng **không kiểm tra file `AutoConfiguration.imports` có được đóng gói và phát hiện tự động hay không**.

Có thể bổ sung một integration test dùng ứng dụng tiêu thụ starter hoặc một context khởi động với cơ chế auto-configuration discovery thực tế để xác nhận metadata registration.

### 16.1. Kiểm tra ứng dụng có thể override bean

Bổ sung user configuration trong test:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {
    @Bean
    GreetingClient greetingClient() {
        return new GreetingClient("Welcome");
    }
}
~~~

Sau đó nạp cấu hình người dùng cùng auto-configuration và xác nhận context chỉ có bean tùy biến. Điều này kiểm tra hành vi `@ConditionalOnMissingBean`.

### 16.2. Kiểm tra property mặc định

Vì ví dụ đặt `matchIfMissing = true`, nên test cả trường hợp không khai báo `acme.greeting.enabled`. Nếu default behavior thay đổi trong tương lai, test này giúp phát hiện thay đổi hợp đồng.

## 17. Auto-configuration ordering và dependency ordering

Một số auto-configuration phụ thuộc vào bean hoặc cấu hình do auto-configuration khác cung cấp. Spring Boot có các annotation:

- `@AutoConfigureBefore`
- `@AutoConfigureAfter`
- `@AutoConfigureOrder`

Ví dụ:

~~~java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class ReportingAutoConfiguration {
    // Cấu hình được xử lý sau DataSourceAutoConfiguration.
}
~~~

Chúng điều khiển thứ tự xử lý auto-configuration candidate, giúp các condition nhìn thấy bean definition từ cấu hình liên quan theo cách mong muốn.

Không nhầm với:

- `@DependsOn`: quan hệ khởi tạo giữa bean cụ thể.
- `@Order`: thứ tự ưu tiên trong một số collection/extension point.
- `@Primary`: ưu tiên một bean khi resolve dependency đơn.
- Constructor injection: biểu diễn dependency object thực tế.

Hãy dùng đúng cơ chế cho đúng loại quan hệ. Auto-configuration ordering không đảm bảo mọi singleton được instantiate theo một thứ tự tuyến tính toàn cục.

## 18. Component scan và auto-configuration có thể cùng tồn tại

Trong cùng một ứng dụng, Spring có thể tìm bean qua nhiều đường:

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["Component scanning"]
    A --> C["Auto-configuration imports"]
    A --> D["Java configuration / @Import"]
    B --> E["@Component / @Service / @Repository"]
    C --> F["@AutoConfiguration + @Bean"]
    D --> G["@Configuration + @Bean"]
    E --> H["Bean definitions"]
    F --> H
    G --> H
~~~

Ví dụ:

- `WelcomeService` được tìm thấy nhờ component scan.
- `GreetingClient` được đăng ký nhờ auto-configuration.
- Một `Clock` tùy chỉnh có thể được đăng ký từ configuration class của ứng dụng.
- Các dependency sau đó được resolve trong cùng context.

Đây là lý do một class auto-configuration không nhất thiết phải nằm trong package được component scan của ứng dụng. Nó được tìm từ metadata riêng.

## 19. Những sai lầm thường gặp khi viết starter

### 19.1. Nghĩ rằng thêm starter sẽ quét mọi class trong JAR

Starter chỉ thêm artifact vào classpath. Auto-configuration phải được đăng ký qua metadata và condition phải khớp. Một class `@Component` trong JAR nằm ngoài scan package không tự nhiên trở thành bean.

### 19.2. Quên file AutoConfiguration.imports

Có class `@AutoConfiguration` nhưng thiếu metadata thì Boot không tự phát hiện class từ thư viện theo cơ chế imports. Kiểm tra resource trong artifact đã build.

### 19.3. Tạo bean mặc định mà không cho phép override

Nếu starter luôn đăng ký bean không có `@ConditionalOnMissingBean` trong khi ứng dụng cần thay implementation, có thể dẫn đến nhiều bean cùng kiểu và injection ambiguity. Với bean mặc định của thư viện, hãy cân nhắc một điểm mở rộng có chủ đích.

### 19.4. Dùng condition không đúng phạm vi

Đặt condition trên cả auto-configuration class có thể loại toàn bộ bean trong class. Đặt condition trên một bean method chỉ ảnh hưởng bean đó. Hãy chọn phạm vi phù hợp với feature.

### 19.5. Dùng @ConditionalOnMissingBean trong cấu hình thông thường tùy tiện

Condition này hữu ích trong auto-configuration vì cấu hình ứng dụng thường được xử lý trước auto-configuration. Nếu dùng rải rác trong các configuration thông thường, kết quả có thể phụ thuộc thứ tự xử lý khó hiểu.

### 19.6. Dùng component scan rộng để sửa thiếu bean

Quét toàn bộ package của dependency có thể kéo nhiều component ngoài ý muốn vào context. Với thư viện được thiết kế để tích hợp Spring Boot, cung cấp auto-configuration tường minh thường kiểm soát tốt hơn.

### 19.7. Không kiểm tra default property

Các giá trị `matchIfMissing`, giá trị mặc định trong properties class và điều kiện bật/tắt tạo thành hợp đồng với người dùng starter. Viết test cho cả giá trị mặc định và các nhánh property rõ ràng.

### 19.8. Cho rằng auto-configuration luôn chạy

Auto-configuration có thể bị loại trừ bằng `exclude` trên `@EnableAutoConfiguration`/`@SpringBootApplication`, qua thuộc tính cấu hình exclude, hoặc bị condition/filter loại. Nếu bean không xuất hiện, hãy xem condition report trước khi sửa code.

## 20. Quy trình tự lần theo một bean bất kỳ

Khi muốn hiểu một bean đến từ starter nào và được tạo ra thế nào, hãy lần theo thứ tự:

1. Tìm nơi ứng dụng khai báo dependency trực tiếp hoặc bắc cầu.
2. Xác định JAR nào chứa class bean hoặc class auto-configuration.
3. Kiểm tra resource `AutoConfiguration.imports` trong JAR.
4. Tìm class auto-configuration được đăng ký.
5. Đọc các annotation condition trên class và bean method.
6. Kiểm tra property, profile, classpath và bean definitions hiện có.
7. Tìm `@Bean` method tạo object hoặc component được đăng ký.
8. Xác định dependency của factory method/constructor.
9. Kiểm tra bean definition và lifecycle sau khi context refresh.
10. Dùng condition report hoặc context test để xác nhận nhánh thực tế.

Một cách tìm trong codebase là tìm tên kiểu bean, sau đó lần ngược từ method `@Bean` hoặc stereotype tới lớp configuration, metadata và dependency tương ứng. Đừng chỉ tìm annotation trên class rồi kết luận đó là nguồn tạo bean; bean có thể được trả về từ factory method trong module khác.

## 21. Bài tập thực hành

### Bài tập 1 — Theo dấu starter

Tạo ba module `demo-app`, `demo-greeting-autoconfigure` và `demo-greeting-starter`. Khai báo dependency từ app tới starter, từ starter tới auto-configuration. Xác nhận app nhìn thấy class từ module core trên runtime classpath.

### Bài tập 2 — Đăng ký auto-configuration metadata

Tạo `GreetingAutoConfiguration` và file `AutoConfiguration.imports`. Chạy ứng dụng với `@SpringBootApplication` nhưng không thêm `@Import(GreetingAutoConfiguration.class)`. Xác nhận bean vẫn được phát hiện nhờ metadata.

### Bài tập 3 — Quan sát condition

Thêm `@ConditionalOnProperty` cho `demo.greeting.enabled`. Chạy hai lần với true và false, quan sát bean có xuất hiện trong context hay không. Dùng `--debug` để đọc condition report.

### Bài tập 4 — Cho phép ứng dụng override

Thêm `@ConditionalOnMissingBean(GreetingClient.class)`. Tạo một bean `GreetingClient` từ configuration của ứng dụng. Xác nhận auto-configuration không đăng ký default bean.

### Bài tập 5 — Phân biệt definition và instance

Ghi log trong factory method và constructor của `GreetingClient`. Quan sát thời điểm chúng chạy khi context refresh. Thử đánh dấu bean lazy hoặc chỉ yêu cầu bean ở runtime, rồi so sánh với singleton eager.

### Bài tập 6 — Kiểm thử với ApplicationContextRunner

Viết test cho các trường hợp: property mặc định, property tắt, user-defined bean override và dependency classpath không có. Xác nhận mỗi condition tạo hoặc bỏ bean đúng như hợp đồng.

## 22. Ghi nhớ

Đường đi từ dependency đến bean có thể tóm tắt thành các bước có ranh giới rõ ràng: Gradle/Maven đưa starter và các dependency bắc cầu vào classpath; `@SpringBootApplication` bật auto-configuration; `AutoConfigurationImportSelector` đọc candidate từ `AutoConfiguration.imports`; Spring Boot lọc và đánh giá condition; các cấu hình phù hợp đóng góp bean definitions; khi context refresh, Spring khởi tạo object và resolve dependency; consumer nhận bean qua constructor injection.

Starter không tự tạo object và component scan không phải cơ chế duy nhất để có bean. Auto-configuration cung cấp một cách đăng ký bean mặc định dựa trên classpath, property và bean đã có. Với `@ConditionalOnMissingBean`, ứng dụng có thể thay default implementation mà không sửa thư viện. Với `@ConditionalOnProperty`, tính năng có thể được bật/tắt theo cấu hình.

Khi bean không xuất hiện, lần theo build dependency, metadata, condition report, bean definition và lifecycle theo đúng thứ tự. Cách suy luận này giúp bạn hiểu không chỉ bean nào được tạo, mà còn vì sao Spring Boot quyết định tạo nó trong một môi trường cụ thể.
