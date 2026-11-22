# Chính sách ghi đè định nghĩa bean và phụ thuộc vòng trong Spring Boot

## 1. Vì sao hai chính sách này quan trọng khi thiết lập SpringApplication?

`SpringApplication` khởi động `ApplicationContext`, chuẩn bị `Environment`, nạp cấu hình, đăng ký `BeanDefinition` và tạo các bean cần thiết. Hai lỗi thường xuất hiện ở quá trình này là **hai định nghĩa dùng cùng tên** và **hai hay nhiều bean cần nhau theo một vòng phụ thuộc**. Chúng khác nhau về nguyên nhân, thời điểm phát hiện và cách sửa.

Spring Boot cung cấp hai thuộc tính riêng trong nhóm `spring.main`:

| Thuộc tính | Mặc định trong Spring Boot 2.6+, 3.x và 4.x | Kiểm soát điều gì? |
| --- | --- | --- |
| `spring.main.allow-bean-definition-overriding` | `false` | Có cho phép đăng ký một `BeanDefinition` mới với cùng **tên** của định nghĩa đã tồn tại hay không |
| `spring.main.allow-circular-references` | `false` | Container có được **thử** giải quyết tham chiếu vòng trong lúc tạo bean hay không |

Cờ đầu được Boot đặt mặc định là `false` từ Spring Boot 2.1; cờ thứ hai được đổi mặc định thành `false` từ Spring Boot 2.6. Các phiên bản cũ có thể có hành vi khác nên phải đối chiếu version thực tế. Cấu hình đúng thường là **giữ cả hai bằng `false`** và sửa trùng tên hoặc thiết kế phụ thuộc khi khởi động thất bại.

~~~yaml
# src/main/resources/application.yaml
spring:
  main:
    allow-bean-definition-overriding: false
    allow-circular-references: false
~~~

Đây là hai thiết lập của `SpringApplication`/bean factory, được áp dụng khi khởi động; chúng **không** phải cờ đổi quy tắc trực tiếp sau khi các bean đã được tạo. Việc đặt cấu hình vào YAML giúp bộc lộ chính sách, dù không cần ghi tường minh vì đó đã là giá trị mặc định.

## 2. Ghi đè định nghĩa bean: xung đột theo tên, không phải theo kiểu

Spring quản lý các định nghĩa bean trong một registry, thường là `DefaultListableBeanFactory`. Mỗi định nghĩa có một **bean name** dùng để đăng ký. Các nguồn đăng ký phổ biến là `@Component`/`@Service`/`@Repository`, `@Bean` trong lớp `@Configuration`, cấu hình XML hoặc đăng ký bằng API. Với `@Bean` không chỉ định tên, tên mặc định thường là tên method; với component scan, tên mặc định thường suy ra từ tên class.

**Bean definition overriding** xảy ra khi một định nghĩa khác được đăng ký với tên đã sử dụng. Nếu chính sách cấm, quá trình đăng ký sẽ thất bại, thường với `BeanDefinitionOverrideException`. Nếu bật cho phép, một định nghĩa có thể thay thế định nghĩa trước, khiến kết quả phụ thuộc thứ tự đăng ký hoặc cấu trúc cấu hình. Tránh dựa vào thứ tự đó để chọn chiến lược nghiệp vụ.

### Ví dụ xung đột tên bean

Xét một dự án Spring Boot có package gốc `com.example.override`; ba file sau nằm trong package này.

**`src/main/java/com/example/override/OverrideApplication.java`**

~~~java
package com.example.override;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OverrideApplication {
    public static void main(String[] args) {
        SpringApplication.run(OverrideApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/override/LocalConfig.java`**

~~~java
package com.example.override;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LocalConfig {
    @Bean("deliveryMode")
    String localDeliveryMode() {
        return "local";
    }
}
~~~

**`src/main/java/com/example/override/RemoteConfig.java`**

~~~java
package com.example.override;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RemoteConfig {
    @Bean("deliveryMode")
    String remoteDeliveryMode() {
        return "remote";
    }
}
~~~

Hai method khác tên nhưng cùng đăng ký `deliveryMode`. Khi Spring Boot tải cả hai configuration và chính sách mặc định đang tắt overriding, ứng dụng không hoàn thành khởi động; log thường cho biết bean `deliveryMode` đã được định nghĩa và ghi đè bị cấm. Lỗi không đến từ việc cả hai trả về `String`, mà từ việc **trùng bean name**. Nếu đặt `spring.main.allow-bean-definition-overriding=true`, ứng dụng có thể qua được lỗi trùng tên; tuy nhiên không nên kết luận bean cuối cùng chắc chắn là `"local"` hay `"remote"` nếu không kiểm soát đăng ký và kiểm thử.

Có thể phát sinh xung đột tương tự khi hai class `@Service("billingService")` khác nhau, hoặc một class `@Component("gateway")` và một method `@Bean("gateway")` cùng tồn tại. Cũng cần phân biệt tình huống framework xử lý đặc biệt giữa `@Bean` và component scan trong cùng configuration; không lấy một trường hợp đặc biệt để suy ra mọi định nghĩa trùng tên đều được phép.

### Ba khái niệm thường bị nhầm

1. **Trùng bean name:** hai định nghĩa muốn đăng ký cùng identifier. Chính sách overriding chi phối trường hợp này.
2. **Nhiều bean cùng kiểu:** `EmailSender` và `SmsSender` đều triển khai `MessageSender` với **hai tên khác nhau**. Chúng được phép cùng tồn tại; khi inject `MessageSender` đơn lẻ, Spring có thể báo `NoUniqueBeanDefinitionException` nếu không xác định được ứng viên phù hợp.
3. **Override method trong Java:** `@Override` trên method là tính năng ngôn ngữ Java; không liên quan tới bean definition overriding.

`@Qualifier` và `@Primary` giúp giải quyết **chọn bean khi inject theo kiểu**, không làm hai định nghĩa trùng tên trở thành hợp lệ. `@Order` sắp thứ tự các thành phần trong một số ngữ cảnh như danh sách/chain, cũng không phải cách sửa xung đột định nghĩa.

### Sửa xung đột đúng cách

Nếu thực sự cần hai implementation, **đặt hai tên khác nhau**, inject bằng qualifier hoặc chọn ứng viên mặc định bằng `@Primary`. Ví dụ:

~~~java
public interface MessageSender {
    void send(String text);
}
~~~

~~~java
import org.springframework.stereotype.Component;

@Component("emailSender")
public class EmailSender implements MessageSender {
    @Override
    public void send(String text) {
        System.out.println("EMAIL: " + text);
    }
}
~~~

~~~java
import org.springframework.stereotype.Component;

@Component("smsSender")
public class SmsSender implements MessageSender {
    @Override
    public void send(String text) {
        System.out.println("SMS: " + text);
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final MessageSender sender;

    public NotificationService(@Qualifier("emailSender") MessageSender sender) {
        this.sender = sender;
    }

    public void notifyUser(String message) {
        sender.send(message);
    }
}
~~~

Các snippet vừa rồi minh họa thiết kế: đặt mỗi type vào file và package thích hợp rồi khai báo import của `MessageSender` trong dự án thực tế. Trong ví dụ, `@Qualifier("emailSender")` chọn đúng bean cho tham số constructor; nó không được dùng để cho phép hai bean cùng tên.

Nếu chỉ một cấu hình được phép hoạt động theo môi trường, dùng `@Profile` hoặc `@ConditionalOnProperty` để chỉ đăng ký cấu hình thích hợp. Cần kiểm thử trường hợp không có hoặc nhiều profile cùng active: nếu cả hai definition vẫn được đăng ký với cùng tên, xung đột vẫn xảy ra. Với auto-configuration, nhiều bean mặc định được định nghĩa có điều kiện bằng `@ConditionalOnMissingBean`, để tự **back off** khi người dùng cung cấp bean thích hợp. Đây là cơ chế lựa chọn có điều kiện, **khác** với cho phép định nghĩa sau ghi đè định nghĩa trước.

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return text -> System.out.println("DEFAULT: " + text);
}
~~~

Đoạn trên mô tả logic trong một cấu hình có điều kiện kiểu auto-configuration; cần đặt đúng vị trí trong chu trình xử lý cấu hình (thông thường sau bean của ứng dụng). Không đặt `@ConditionalOnMissingBean` tùy tiện trên nhiều cấu hình ngang cấp rồi giả định kết quả không phụ thuộc thứ tự xử lý.

## 3. Phụ thuộc vòng: xung đột trong đồ thị khởi tạo

Một bean có thể cần bean khác qua constructor, setter hoặc field. Khi lần theo các phụ thuộc, nếu quay lại bean đang được tạo, ta có **circular dependency**.

~~~mermaid
flowchart LR
  A["OrderService"] -->|"constructor"| B["PaymentService"]
  B -->|"constructor"| C["RiskService"]
  C -->|"constructor"| A
~~~

Vòng không nhất thiết chỉ gồm hai bean. Chuỗi `A → B → C → A` cũng là vòng. Cấu trúc này thường cho biết hai trách nhiệm đang ràng buộc quá chặt hoặc có logic gọi ngược chưa được tách khỏi khâu khởi tạo.

### Ví dụ constructor injection không thể giải quyết tự động

Hai class sau được Spring tìm thấy thông qua component scan:

**`src/main/java/com/example/cycle/PricingService.java`**

~~~java
package com.example.cycle;

import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final PromotionService promotionService;

    public PricingService(PromotionService promotionService) {
        this.promotionService = promotionService;
    }
}
~~~

**`src/main/java/com/example/cycle/PromotionService.java`**

~~~java
package com.example.cycle;

import org.springframework.stereotype.Service;

@Service
public class PromotionService {
    private final PricingService pricingService;

    public PromotionService(PricingService pricingService) {
        this.pricingService = pricingService;
    }
}
~~~

Để tạo `PricingService` phải có `PromotionService`; muốn tạo `PromotionService` lại phải có `PricingService`. Không bean nào có thể hoàn tất constructor trước. Spring thường báo lỗi chuỗi khởi tạo, với `BeanCurrentlyInCreationException` là nguyên nhân cốt lõi (có thể được bọc bởi `UnsatisfiedDependencyException`). **Ngay cả khi bật `spring.main.allow-circular-references=true`, vòng constructor-to-constructor này vẫn không được tự giải**.

### Vì sao setter injection đôi khi khác constructor injection?

Ở trường hợp singleton có thể gán dependency sau khi tạo đối tượng, Spring Framework từng hỗ trợ **early reference**: container có thể tạo instance A, đưa một tham chiếu sớm để hỗ trợ B, rồi tiếp tục gán thuộc tính và hoàn thiện vòng đời. Cách đó chỉ khả thi trong một số cấu hình và điều kiện cụ thể; việc có proxy/AOP, nhiều scope, factory method hoặc thao tác trong lúc init có thể khiến vòng không thể xử lý. Một object được nhìn thấy trước khi khởi tạo xong cũng là nguồn lỗi khó tái hiện.

Vì vậy, `allow-circular-references=true` nghĩa là **“thử giải quyết những vòng hỗ trợ được”**, không phải “mọi vòng đều hợp lệ”. Spring Boot từ 2.6 mặc định ngăn vòng thay vì phụ thuộc ngầm vào early reference.

Hai cơ chế đăng ký và khởi tạo khác nhau hoàn toàn: bật bean overriding không giải quyết vòng A ↔ B; bật circular references không giải quyết lỗi trùng bean name.

## 4. Cách sửa bền vững: thay đổi chiều phụ thuộc

Giả sử `PricingService` cần tính giảm giá, còn `PromotionService` lại gọi ngược `PricingService` để lấy thông tin đơn. Hãy xác định chức năng chung thực sự là gì: một **chính sách tính giảm giá** không cần biết toàn bộ `PricingService`. Trích xuất interface và làm cho chiều phụ thuộc một hướng.

~~~mermaid
flowchart LR
  A["PricingService"] --> B["DiscountPolicy"]
  C["FixedDiscountPolicy"] -.implements.-> B
  D["Promotion workflow"] --> A
~~~

Một vòng nghiệp vụ có thể được tách thành bước orchestration ở tầng cao, giao tiếp qua sự kiện hoặc callback chỉ khi thực sự cần. Hạn chế tạo hai service vừa phụ thuộc trực tiếp vừa gọi nhau qua constructor.

### Ví dụ Spring Boot Java 17+ hoàn chỉnh, không còn vòng

Tạo project Maven từ Spring Initializr, chọn Java 17 trở lên, dependency **Spring Boot Starter** (không cần Web hay Actuator cho ví dụ bean lifecycle), package `com.example.policy`. Đặt bốn file sau dưới `src/main/java/com/example/policy/`.

**`PolicyApplication.java`**

~~~java
package com.example.policy;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PolicyApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PricingService pricing) {
        return args -> System.out.println(
            "TOTAL=" + pricing.priceAfterDiscount(100)
        );
    }
}
~~~

**`DiscountPolicy.java`**

~~~java
package com.example.policy;

public interface DiscountPolicy {
    int discountFor(int originalPrice);
}
~~~

**`FixedDiscountPolicy.java`**

~~~java
package com.example.policy;

import org.springframework.stereotype.Component;

@Component
public class FixedDiscountPolicy implements DiscountPolicy {
    @Override
    public int discountFor(int originalPrice) {
        return 10;
    }
}
~~~

**`PricingService.java`**

~~~java
package com.example.policy;

import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final DiscountPolicy discountPolicy;

    public PricingService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    public int priceAfterDiscount(int originalPrice) {
        return Math.max(0, originalPrice -
            discountPolicy.discountFor(originalPrice));
    }
}
~~~

Chạy trong thư mục chứa `pom.xml` đã được Spring Initializr tạo:

~~~bash
mvn spring-boot:run
~~~

Bên cạnh thông tin khởi động của Spring Boot, chương trình in một dòng do `CommandLineRunner` tạo:

~~~text
TOTAL=90
~~~

Giải thích: `FixedDiscountPolicy` implement `DiscountPolicy` và không cần `PricingService`; `PricingService` chỉ cần chính sách giảm giá; `CommandLineRunner` nhận service đã được tạo rồi mới chạy. Đồ thị không có đường quay lại. Cả hai cờ trong `spring.main` giữ mặc định `false` nhưng ứng dụng vẫn khởi động thành công. Công thức ở đây minh họa dependency injection; hệ thống thực cần quy tắc tiền tệ và validation phù hợp hơn số nguyên đơn giản.

Một dự án thực nên có test khởi động context để phát hiện vòng và bean collision, cùng test riêng cho logic giảm giá; ví dụ trên tập trung vào vòng đời bean, không yêu cầu HTTP controller.

## 5. Biện pháp trì hoãn và tương thích: dùng có giới hạn

Khi tạm thời chưa thể refactor, có vài cơ chế cho phép trì hoãn thời điểm lấy dependency. Chúng có ý nghĩa khác nhau và không nên bị coi là cách sửa kiến trúc triệt để.

### `@Lazy` tại điểm inject

~~~java
@Service
class ReportService {
    private final ExportService exportService;

    ReportService(@Lazy ExportService exportService) {
        this.exportService = exportService;
    }
}

@Service
class ExportService {
    private final ReportService reportService;

    ExportService(ReportService reportService) {
        this.reportService = reportService;
    }
}
~~~

Trong snippet trên cần import `org.springframework.context.annotation.Lazy` và `org.springframework.stereotype.Service`. `@Lazy` ở tham số constructor yêu cầu Spring đưa **proxy trì hoãn lookup** của `ExportService`; cách này có thể cho phép tạo `ReportService` mà chưa phải dựng bean thật của `ExportService`. Nhưng nếu constructor, `@PostConstruct` hoặc một call quá sớm dereference proxy, lỗi vẫn có thể xảy ra. Ngay cả sau khi start thành công, hai service gọi nhau không có điều kiện dừng vẫn gây đệ quy vô hạn trong nghiệp vụ. Tách vòng phụ thuộc vẫn là cách nên chọn.

### `ObjectProvider<T>`

~~~java
import org.springframework.beans.factory.ObjectProvider;

@Service
class JobCoordinator {
    private final ObjectProvider<JobHandler> handlerProvider;

    JobCoordinator(ObjectProvider<JobHandler> handlerProvider) {
        this.handlerProvider = handlerProvider;
    }

    void execute() {
        handlerProvider.getObject().handle();
    }
}
~~~

Provider hoãn lookup đến khi gọi `getObject()` và hữu ích cho phụ thuộc tùy chọn hoặc cần lazy lookup. Nếu `JobHandler` lại cần `JobCoordinator`, bạn phải đảm bảo chỉ lấy handler sau khi context và các bean liên quan đã sẵn sàng. Provider không loại bỏ mối quan hệ vòng về mặt thiết kế.

### Bật lại hỗ trợ vòng như một bước chuyển tiếp

~~~yaml
spring:
  main:
    allow-circular-references: true
~~~

Hoặc đưa qua CLI khi khởi động:

~~~bash
java -jar target/app.jar --spring.main.allow-circular-references=true
~~~

Tùy loại vòng, cách này có thể giúp hệ thống cũ dùng setter/field injection khởi động trong thời gian refactor. Nó **không** sửa vòng constructor injection, không bảo đảm với AOP/proxy và không thay thế đánh giá startup/test. Tránh để giải pháp chuyển tiếp thành cấu hình production lâu dài.

### Những thay đổi không giải quyết gốc rễ

- `spring.main.lazy-initialization=true` có thể đẩy lỗi sang lúc bean được dùng; nó không xóa một dependency cycle.
- `@DependsOn` điều khiển thứ tự khởi tạo, không thể giải một vòng mà mỗi bean thực sự cần bean kia để tạo xong; cấu hình `depends-on` vòng còn có thể dẫn tới lỗi rõ ràng hơn.
- Chuyển constructor injection thành field injection chỉ để qua startup có thể che sự phụ thuộc hai chiều và làm test khó hơn.
- Dùng `ApplicationContext.getBean(...)` bất cứ đâu để né khai báo dependency có thể biến lỗi rõ ràng thành service locator khó theo dõi.
- `@Configuration(proxyBeanMethods=false)` điều chỉnh cơ chế proxy của các `@Bean` method trong configuration; không tự sửa trùng bean name hay vòng phụ thuộc của service.

## 6. Thiết lập chính sách bằng SpringApplication và bằng cấu hình ngoài

Các cờ này thuộc nhóm cấu hình khởi động. Có thể kiểm soát qua properties:

~~~properties
# src/main/resources/application.properties
spring.main.allow-bean-definition-overriding=false
spring.main.allow-circular-references=false
~~~

Hoặc đặt qua `SpringApplication` trước `run(...)`:

~~~java
package com.example.policy;

import org.springframework.boot.SpringApplication;

public final class ExplicitPolicyLauncher {
    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(PolicyApplication.class);
        app.setAllowBeanDefinitionOverriding(false);
        app.setAllowCircularReferences(false);
        app.run(args);
    }
}
~~~

Đây là **launcher thay thế** cho cùng ứng dụng `PolicyApplication` ở mục 4; không cần chạy đồng thời hai method `main`. Spring Boot cũng hỗ trợ các setter tương ứng trên `SpringApplicationBuilder`. Giá trị được xác định khi tạo context, vì vậy không sửa cờ qua một bean đã khởi tạo rồi mong container thay đổi cách đăng ký/khởi tạo trước đó.

Ví dụ với tham số CLI:

~~~bash
java -jar target/app.jar \
  --spring.main.allow-bean-definition-overriding=false \
  --spring.main.allow-circular-references=false
~~~

Lệnh trên minh họa **cú pháp**; thay `target/app.jar` bằng đường dẫn artifact thực. Trên Windows PowerShell, nên đặt lệnh trên một dòng hoặc dùng ký tự nối dòng PowerShell thích hợp thay cho dấu `\` của bash.

Với cấu hình ngoài, những nguồn như tham số command line có thể ghi đè giá trị trong `application.yaml` theo thứ tự ưu tiên `PropertySource` tiêu chuẩn. Vì vậy, khi có sự khác biệt giữa môi trường, hãy kiểm tra tham số chạy thực tế, biến môi trường và profile config data. Một container của Spring Framework thuần có thể có mặc định khác; không dùng mặc định của `DefaultListableBeanFactory` thuần để suy ra chính sách của `SpringApplication`.

## 7. Quy trình xác định nguyên nhân khi khởi động lỗi

### A. Trùng bean definition

Biểu hiện thường gặp:

~~~text
... BeanDefinitionOverrideException ...
... bean 'deliveryMode' ... already defined ...
... overriding is disabled ...
~~~

Văn bản đầy đủ thay đổi theo phiên bản Spring Boot, tên class và thứ tự cấu hình. Cách điều tra:

1. Đọc **bean name** trong lỗi, ví dụ `deliveryMode`.
2. Xem hai nguồn định nghĩa được log chỉ ra: `@Bean` method, component scan, `@Import`, cấu hình từ thư viện.
3. Xác định liệu có cần hai implementation cùng tồn tại hay chỉ một cấu hình đúng cho profile hiện tại.
4. Ưu tiên đổi tên/đổi qualifier, loại bỏ đăng ký trùng hoặc áp dụng điều kiện đăng ký rõ ràng.
5. Nếu dùng `@ConditionalOnMissingBean`, kiểm tra thứ tự áp dụng auto-configuration và điều kiện hiện có.
6. Chỉ xem bật override như ngoại lệ có lý do cụ thể, kèm test xác nhận bean thực tế.

**Dấu hiệu phân biệt:** hai class khác nhau cùng kiểu nhưng tên khác nhau thường dẫn đến bài toán chọn candidate (`NoUniqueBeanDefinitionException`), không phải `BeanDefinitionOverrideException`.

### B. Vòng phụ thuộc

Biểu hiện thường gặp là chuỗi tên bean trong log với hình mũi tên/vòng, hoặc cause `BeanCurrentlyInCreationException`:

~~~text
pricingService -> promotionService -> pricingService
~~~

Cách điều tra:

1. Xác định các cạnh của vòng từ constructor, setter hoặc injection field.
2. Xem những method nào cần gọi ngược từ tầng dưới lên tầng trên.
3. Phân biệt vòng ở **constructor** với vòng có thể gán thuộc tính sau khi tạo; cả hai đều nên được sửa cấu trúc.
4. Chia trách nhiệm chung ra một interface/service độc lập, hoặc chuyển điều phối lên một tầng orchestration chỉ phụ thuộc một chiều.
5. Thêm test khởi động context và test call path nghiệp vụ; startup thành công không chứng minh không có đệ quy khi chạy.
6. Nếu có biện pháp trì hoãn tạm thời, ghi rõ điểm dereference, độ an toàn của initialization và kế hoạch loại bỏ vòng.

**Dấu hiệu phân biệt:** đổi tên bean hoặc `@Qualifier` có thể chọn đúng dependency nhưng không loại bỏ đồ thị A → B → A nếu các constructor vẫn cần nhau.

### C. App chỉ lỗi khi deploy, chạy local vẫn được

Kiểm tra các khác biệt sau: profile active, các module/dependency được bật, lớp `@Configuration` được scan/import, các properties CLI hoặc biến môi trường, và trạng thái tạo bean lazy/eager. Hai profile cùng active có thể làm bật hai cấu hình tưởng như loại trừ nhau. Một service chỉ được dùng ở runtime có thể khiến vòng ẩn bộc lộ sau startup nếu dùng lazy resolution.

## 8. Bảng quyết định nhanh

| Tình huống | Triệu chứng chính | Giải pháp ưu tiên | Điều không nên nhầm |
| --- | --- | --- | --- |
| Hai `@Bean("cacheClient")` khác nguồn | `BeanDefinitionOverrideException` | Chỉ đăng ký một bean đúng điều kiện hoặc đặt tên rõ ràng | `@Primary` không sửa trùng name |
| Hai implementation cùng interface, tên khác | `NoUniqueBeanDefinitionException` khi inject | `@Qualifier`, `@Primary` hoặc inject collection khi cần | Không cần bật bean overriding |
| A constructor cần B, B constructor cần A | Vòng không thể khởi tạo | Thiết kế lại chiều phụ thuộc | `allow-circular-references=true` không chữa vòng constructor |
| A và B dùng setter/field injection hai chiều | Vòng bị Boot chặn khi tạo bean | Refactor; trường hợp chuyển tiếp có thể thử cờ circular | Cho phép thử giải vòng không bảo đảm mọi tình huống |
| Dùng `@Lazy`/provider rồi startup qua được | Lỗi có thể chuyển tới thời điểm dùng | Kiểm tra lại call graph và tách vòng thực sự | Startup pass không có nghĩa call recursion an toàn |
| Bean mặc định của starter “không xuất hiện” | Điều kiện auto-config không thỏa | Đọc condition evaluation report | Auto-config backoff khác ghi đè definition |
| Hai cấu hình chỉ nên tồn tại ở hai môi trường | Trùng bean khi profile kết hợp | `@Profile`/`@ConditionalOnProperty` với test ma trận profile | Nhiều profile có thể active cùng lúc |

## 9. Nguyên tắc cấu trúc khi thiết kế ứng dụng

- Dùng **constructor injection** cho dependency bắt buộc: lỗi thiếu bean hoặc vòng phụ thuộc lộ ra sớm, đối tượng có dependency cần thiết ngay sau khi tạo.
- Đặt tên bean có chủ đích khi có nhiều implementation cùng loại; chọn candidate một cách rõ ràng tại điểm inject.
- Các tầng có chiều phụ thuộc dễ giải thích: API/controller → application service → domain policy/repository/gateway; không để tầng dưới phải constructor-inject service tầng trên để gọi ngược.
- Tách trách nhiệm giữa **đăng ký bean**, **lựa chọn candidate khi inject** và **khởi tạo đối tượng**. Mỗi nhóm lỗi có cách điều tra riêng.
- Giữ `allow-bean-definition-overriding=false` và `allow-circular-references=false` trong cấu hình vận hành thông thường; nếu có ngoại lệ tương thích, mô tả lý do và kiểm thử cụ thể.
- Khi nâng phiên bản Spring Boot, đọc release notes về chính sách khởi tạo bean, vì một ứng dụng từng khởi động với mặc định cũ có thể bộc lộ trùng tên hoặc vòng phụ thuộc sau upgrade.

## 10. Tự kiểm tra hiểu biết

**Câu 1.** Hai bean `emailSender` và `smsSender` đều implement `MessageSender`. Có cần bật `allow-bean-definition-overriding` không? **Không**, vì tên khác nhau. Khi inject một `MessageSender` cần xử lý lựa chọn candidate.

**Câu 2.** Hai method `@Bean` khác nhau cùng khai báo tên `metricsClient`. Thêm `@Primary` vào một method có hết lỗi không? **Không**, lỗi là đăng ký trùng tên chứ không phải ưu tiên inject.

**Câu 3.** Hai service inject lẫn nhau bằng constructor. Đặt `spring.main.allow-circular-references=true` có chắc chạy được không? **Không**, vòng constructor-to-constructor không thể tự hoàn tất.

**Câu 4.** Dùng `@Lazy` ở một cạnh phụ thuộc làm startup chạy được. Có thể coi đã loại bỏ cycle chưa? **Chưa**, chỉ trì hoãn lookup; gọi proxy quá sớm hoặc logic gọi ngược vẫn có thể lỗi.

**Câu 5.** Một starter không tạo bean mặc định vì người dùng đã khai báo bean cùng kiểu. Đây luôn là bean definition overriding? **Không**, auto-configuration có thể dùng `@ConditionalOnMissingBean` để không đăng ký bean mặc định từ đầu.

### Tài liệu chính thức

- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): hai key `spring.main.allow-bean-definition-overriding` và `spring.main.allow-circular-references` cùng giá trị mặc định.
- [Spring Boot — SpringApplication API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html): `setAllowBeanDefinitionOverriding` và `setAllowCircularReferences`.
- [Spring Framework — Bean Overview / Overriding Beans](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): identifier của bean và ghi đè định nghĩa.
- [Spring Framework — Dependency Injection / Circular Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): phân tích vòng trong constructor injection.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): cơ chế bean mặc định điều kiện.
- [Spring Boot 2.6 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.6-Release-Notes): thay đổi mặc định của circular references.