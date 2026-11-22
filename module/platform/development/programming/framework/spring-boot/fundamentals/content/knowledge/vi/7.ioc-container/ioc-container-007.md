# Phân biệt đối tượng được tạo bằng new với bean trong context

Trong Java, muốn có một đối tượng, ta thường dùng từ khóa **new**:

~~~java
GreetingService service = new GreetingService();
~~~

Nhưng trong ứng dụng Spring Boot, ta cũng thường thấy một lớp có **@Service**, **@Component** hoặc được trả về từ phương thức **@Bean**, sau đó được truyền vào constructor của lớp khác mà không có lời gọi **new** tại nơi sử dụng:

~~~java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

~~~java
@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }
}
~~~

Câu hỏi cốt lõi không phải “đối tượng có được tạo bằng **new** hay không”. Bản thân Spring vẫn có thể dùng constructor, factory method và cuối cùng là các thao tác tạo đối tượng Java thông thường. **Điểm khác biệt là ai đăng ký, tạo, lắp ráp, quản lý vòng đời và cung cấp đối tượng cho phần còn lại của ứng dụng.**

- **Đối tượng tạo bằng new trong code ứng dụng**: lời gọi tại đó trực tiếp tạo instance; code của bạn chịu trách nhiệm giữ reference, cung cấp dependency và quản lý tài nguyên liên quan.
- **Spring bean**: một đối tượng nằm dưới sự quản lý của **Spring IoC container** (thường được truy cập qua **ApplicationContext**) theo một **bean definition** hoặc một cơ chế đăng ký bean hợp lệ. Spring có thể cung cấp dependency, áp dụng các bước khởi tạo, bean post-processor, scope và những dịch vụ tích hợp thích hợp.

Bean không phải một kiểu dữ liệu Java đặc biệt. Cùng lớp **GreetingService** có thể được khởi tạo thủ công hoặc được container quản lý; sự khác biệt nằm ở **quá trình tạo và cơ chế quản lý instance**, không nằm ở tên lớp.

## 1. Đối tượng Java thông thường và Spring bean

Xét một lớp Java:

~~~java
public class DiscountCalculator {
    public int applyTenPercent(int price) {
        return price - price / 10;
    }
}
~~~

Tạo một object thủ công:

~~~java
DiscountCalculator calculator = new DiscountCalculator();
int discounted = calculator.applyTenPercent(200);
~~~

Lời gọi **new DiscountCalculator()** tạo một instance bằng constructor. Đối tượng đó không tự động được đăng ký vào Spring ApplicationContext chỉ vì chương trình đang chạy dưới Spring Boot.

Nếu ta đăng ký một bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    DiscountCalculator discountCalculator() {
        return new DiscountCalculator();
    }
}
~~~

Đối tượng được trả về từ phương thức **discountCalculator()** lại là một **bean**, miễn là cấu hình này được Spring xử lý và bean definition được đăng ký trong context tương ứng.

Ở đây có một chi tiết quan trọng: **bên trong @Bean vẫn sử dụng new**. Vì vậy:

> Không thể nhận biết một bean chỉ bằng cách hỏi có từ khóa new trong code hay không. Cần hỏi instance có được Spring context đăng ký và quản lý hay không.

### 1.1. Bảng so sánh

| Khía cạnh | Object được new trực tiếp ngoài container | Bean do Spring context quản lý |
|---|---|---|
| Bản chất | Đối tượng Java. | Vẫn là đối tượng Java, đôi khi được cung cấp qua proxy. |
| Nguồn tạo | Lời gọi constructor từ code của bạn. | Bean definition, constructor, factory method, supplier hoặc cơ chế đăng ký phù hợp. |
| Ai quản lý dependency | Code tạo object phải cung cấp hoặc tự lắp ráp. | Container có thể resolve và inject dependency phù hợp. |
| Có tên/định nghĩa trong context | Không tự có. | Có bean definition hoặc đăng ký được context quản lý theo cơ chế tương ứng. |
| Vòng đời | Code của bạn quản lý; sau đó GC thu hồi khi không còn reference, nếu đủ điều kiện. | Spring có các bước khởi tạo/hủy và quản lý vòng đời theo scope. |
| Scope | Phụ thuộc cách bạn giữ và tái sử dụng reference. | Có thể là singleton, prototype, request, session... theo context. |
| AOP/transaction/cache | Không tự nhận cơ chế proxy của Spring. | Có thể được áp dụng khi đủ điều kiện và lời gọi đi qua cơ chế Spring phù hợp. |
| Cấu hình từ Environment | Không tự bind/inject chỉ vì class có annotation. | Có thể nhận @Value, @ConfigurationProperties hoặc dependency cấu hình khi được kích hoạt đúng. |
| Nơi phù hợp | DTO, value object, entity, đối tượng tạm, unit test độc lập, thuật toán nhỏ. | Service, repository, controller, configuration, collaborator cần DI hoặc lifecycle của Spring. |

**Không phải bean nào cũng được áp dụng mọi chức năng trong bảng.** Chẳng hạn transaction chỉ hoạt động nếu hạ tầng transaction phù hợp đã được thiết lập và lời gọi đúng điều kiện; một bean singleton đơn giản không tự có transaction.

## 2. Spring IoC container quản lý bean bằng cách nào?

**Inversion of Control (IoC)** có nghĩa một phần quyền điều khiển việc tạo và kết nối các thành phần được chuyển từ code nghiệp vụ sang container. **Dependency Injection (DI)** là một cơ chế quan trọng để thực hiện điều đó: một object nhận dependency cần thiết thay vì tự tạo nó.

Mô hình:

~~~text
Không dùng container:

OrderService
  └── tự new PaymentGateway
          └── tự new HttpClient

Dùng Spring IoC container:

ApplicationContext
  ├── định nghĩa / tạo PaymentGateway bean
  ├── định nghĩa / tạo OrderService bean
  └── cung cấp PaymentGateway cho OrderService
              │
              ▼
        OrderService sử dụng dependency
        đã được cung cấp qua constructor
~~~

Trong quá trình xử lý cấu hình, Spring biết những **bean definition** nào đã đăng ký. Bean definition có thể mô tả class, scope, cách tạo bean, dependency và một số metadata liên quan. Từ thông tin đó container tạo và lắp ráp các instance theo thời điểm thích hợp.

Một sơ đồ khái niệm:

~~~text
@Component / @Service / @Bean / import cấu hình
                      │
                      ▼
              Bean definitions
                      │
                      ▼
             ApplicationContext
                      │
             ┌────────┴────────┐
             │                 │
       Tạo instance      Resolve dependency
             │                 │
             └────────┬────────┘
                      │
             Khởi tạo và xử lý
             bean post-processor
                      │
                      ▼
              Bean sẵn sàng
                      │
                      ▼
       Injection / lookup / sử dụng
                      │
                      ▼
        Kết thúc vòng đời theo scope
~~~

Đây là sơ đồ đơn giản hóa. Spring còn nhiều giai đoạn và extension point, ví dụ xử lý BeanFactoryPostProcessor, BeanPostProcessor và các bước tạo proxy. Không phải mọi bean đều được tạo ngay khi application context bắt đầu; thời điểm thực tế phụ thuộc scope và các cấu hình như lazy initialization.

### 2.1. ApplicationContext là gì?

**ApplicationContext** là một giao diện Spring đóng vai trò điểm truy cập tới IoC container và các dịch vụ hỗ trợ ứng dụng. Nó mở rộng khả năng của BeanFactory, bổ sung các chức năng như phát sự kiện, hỗ trợ resource, internationalization và các tích hợp context.

Ví dụ có thể truy xuất một bean:

~~~java
import org.springframework.context.ApplicationContext;

public class Example {
    public void run(ApplicationContext context) {
        DiscountCalculator calculator =
                context.getBean(DiscountCalculator.class);
        System.out.println(calculator.applyTenPercent(200));
    }
}
~~~

Phương thức **getBean** yêu cầu container cung cấp bean phù hợp. Nó khác với **new DiscountCalculator()** vì việc tạo và lựa chọn instance được điều phối bởi Spring.

Tuy nhiên, trong phần lớn code nghiệp vụ, **constructor injection** thường được ưu tiên so với việc gọi **getBean** rải rác. Code cần dependency nên khai báo rõ dependency đó ở constructor; container sẽ lắp ráp khi tạo bean.

### 2.2. Bean definition khác bean instance

Phân biệt:

- **Bean definition**: mô tả cách Spring cung cấp bean, trong đó có thông tin cấu hình, scope và factory method.
- **Bean instance**: đối tượng cụ thể đã được tạo hoặc được trả về theo definition.
- **Bean name**: tên định danh bean trong một container.

Với singleton scope mặc định, một bean definition thường tương ứng với một instance được dùng lại trong context sau khi bean khởi tạo. Với prototype scope, cùng một definition có thể tạo ra **nhiều instance** khi có yêu cầu lấy bean.

Do đó, **có bean definition** không đồng nghĩa rằng object đã được tạo tại thời điểm bạn quan sát. Spring có thể trì hoãn việc khởi tạo, hoặc tạo object mới theo scope khi có request.

## 3. Hai cách tạo cùng một lớp: một object thủ công và một Spring bean

Giả sử có service đơn giản:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Giả sử ứng dụng có:

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

Theo quy ước component scanning thông thường, **GreetingService** nằm trong package của lớp ứng dụng và được Spring quét để đăng ký thành bean.

Trong code ứng dụng khác, ta vẫn có thể viết:

~~~java
GreetingService manual = new GreetingService();
~~~

Trong context, Spring có thể có:

~~~java
GreetingService managed = context.getBean(GreetingService.class);
~~~

Hai biến này tham chiếu tới **hai object khác nhau** trong tình huống phổ biến này:

~~~text
manual = new GreetingService()
          │
          ▼
      Instance A
      Không được Spring tự quản lý

context.getBean(GreetingService.class)
          │
          ▼
      Instance B (bean do context quản lý)
~~~

Ví dụ với singleton bean bình thường không dùng proxy:

~~~java
GreetingService fromContext1 = context.getBean(GreetingService.class);
GreetingService fromContext2 = context.getBean(GreetingService.class);

System.out.println(fromContext1 == fromContext2); // thường true
System.out.println(manual == fromContext1);       // false
~~~

Với singleton bean bình thường, hai lần lookup trả về cùng instance do context quản lý. Nhưng nếu bean được Spring AOP bọc proxy, đối tượng được cung cấp ra ngoài có thể là **proxy**. Nếu scope là prototype, hai lần lookup có thể trả về hai instance khác nhau.

Không nên suy luận bằng cách so sánh class tên Java đơn thuần: **cùng class không có nghĩa cùng instance, cùng bean name hoặc cùng lifecycle**.

### 3.1. Annotation @Service không biến mọi instance thành bean

Đây là hiểu nhầm phổ biến:

~~~java
@Service
public class GreetingService {
    // ...
}
~~~

Annotation **@Service** cho Spring biết lớp này là một component chuyên biệt **khi cơ chế tìm/đăng ký component xử lý lớp đó**. Nó không thay đổi ý nghĩa của từ khóa **new** trong Java.

~~~java
GreetingService service = new GreetingService();
~~~

Đối tượng vừa tạo **không được đăng ký làm bean chỉ vì class có @Service**. Nó không tự tham gia lifecycle, autowiring hoặc proxy mechanism của một bean đang nằm trong Spring context.

Ngược lại, một lớp **không có @Service** vẫn có thể trở thành bean nếu được đăng ký bằng **@Bean** hoặc cơ chế khác.

### 3.2. Không phải cứ có @SpringBootApplication là mọi class đều được quét

Theo mặc định, **@SpringBootApplication** kích hoạt component scanning từ package chứa lớp main và các package con. Ví dụ:

~~~text
com.example.demo
├── DemoApplication        @SpringBootApplication
├── web
│   └── GreetingController @RestController
└── service
    └── GreetingService    @Service
~~~

Trong cấu trúc này, **GreetingController** và **GreetingService** được quét theo quy ước phổ biến.

Nếu một component nằm ở package nằm ngoài phạm vi quét, Spring sẽ không tự động biết nó chỉ từ annotation. Khi đó cần bố trí package phù hợp, import cấu hình hoặc điều chỉnh scan có chủ đích.

Điều này khác với việc **new**: constructor Java không cần component scanning. Nhưng việc tạo object bằng new cũng không biến object thành bean.

## 4. Dependency Injection: tác động dễ thấy nhất

Một lớp service thường phụ thuộc repository hoặc client:

~~~java
package com.example.orders;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    public String findDescription(long orderId) {
        return "Đơn hàng #" + orderId;
    }
}
~~~

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public String describe(long orderId) {
        return repository.findDescription(orderId);
    }
}
~~~

Khi **OrderRepository** và **OrderService** đều được đăng ký làm bean, container có thể chọn bean repository phù hợp và truyền vào constructor của service.

Nếu code tự tạo service:

~~~java
OrderService service = new OrderService(new OrderRepository());
~~~

thì đoạn này **vẫn hoạt động** cho logic đơn giản vì bạn đã chủ động tạo và cung cấp mọi dependency. Nhưng cả service và repository ở đây là những instance tự tạo; chúng không mặc nhiên có các dịch vụ lifecycle, proxy và những phần kết nối theo context Spring.

Đây là sự phân biệt quan trọng:

> DI không phải phép màu khiến Java không còn cần constructor. DI là cách chuyển **trách nhiệm lắp ráp object graph** sang một thành phần chuyên trách, trong Spring là IoC container.

### 4.1. Constructor injection dễ quan sát nhất

Với constructor:

~~~java
public OrderService(OrderRepository repository) {
    this.repository = repository;
}
~~~

Dependency là **bắt buộc** ngay khi tạo object. Nếu bạn tự new, Java buộc cung cấp đối số; nếu Spring tạo bean, Spring phải tìm dependency phù hợp. Điều này làm quan hệ phụ thuộc rõ ràng khi đọc code và thuận tiện khi unit test.

### 4.2. Field injection dễ gây hiểu nhầm khi dùng new

Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class LegacyOrderService {

    @Autowired
    private OrderRepository repository;

    public String describe(long orderId) {
        return repository.findDescription(orderId);
    }
}
~~~

Nếu Spring tạo bean và cơ chế autowiring phù hợp hoạt động, field **repository** có thể được inject.

Nhưng:

~~~java
LegacyOrderService manual = new LegacyOrderService();
manual.describe(42L);
~~~

đối tượng thủ công không đi qua Spring autowiring. Field **repository** vẫn có giá trị mặc định **null**, và lời gọi có thể ném **NullPointerException**.

**@Autowired không phải câu lệnh được JVM tự thực thi mỗi khi new một object.** Nó là metadata được Spring xử lý đối với đối tượng đang được container quản lý hoặc đối tượng được yêu cầu autowire qua API chuyên biệt.

Với code mới, constructor injection thường giúp tránh tình trạng object được tạo nhưng dependency quan trọng chưa có.

### 4.3. Có nhiều bean cùng kiểu thì sao?

Giả sử Spring có hai bean implement interface **PaymentGateway**:

~~~java
public interface PaymentGateway {
    void pay(long orderId);
}
~~~

Nếu constructor yêu cầu một **PaymentGateway** nhưng context có nhiều candidate và không có cách lựa chọn phù hợp, quá trình injection có thể thất bại với **NoUniqueBeanDefinitionException** hoặc exception liên quan.

Có thể dùng **@Qualifier**, **@Primary** hoặc thiết kế injection rõ hơn:

~~~java
public CheckoutService(
        @org.springframework.beans.factory.annotation.Qualifier("stripeGateway")
        PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Khi tự new, bạn tự chọn implementation:

~~~java
CheckoutService checkout = new CheckoutService(new LocalPaymentGateway());
~~~

Chọn trực tiếp không phải sai, nhưng bạn đang quyết định dependency ở **nơi tạo object**, thay vì để Spring xác định từ container.

## 5. @Bean có thể trả về một object tạo bằng new

Đây là phản ví dụ quan trọng nhất đối với cách hiểu “new đối lập với bean”.

~~~java
package com.example.demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    PricePolicy pricePolicy() {
        return new PricePolicy(0.10);
    }
}
~~~

~~~java
package com.example.demo.config;

public class PricePolicy {
    private final double discountRate;

    public PricePolicy(double discountRate) {
        this.discountRate = discountRate;
    }

    public double apply(double price) {
        return price * (1 - discountRate);
    }
}
~~~

**PricePolicy** không có **@Component**, **@Service** hay **@Repository**. Tuy vậy object được phương thức **@Bean** trả về vẫn có thể được đăng ký và quản lý như bean.

Sơ đồ:

~~~text
Spring ApplicationContext
      │
      ├── xử lý PricingConfiguration
      │
      ├── thấy @Bean PricePolicy pricePolicy()
      │
      ├── gọi factory method:
      │       return new PricePolicy(0.10)
      │
      └── quản lý đối tượng được trả về
              như một bean PricePolicy
~~~

Thế nên câu hỏi đúng phải là **lời gọi new được thực hiện ở đâu và kết quả có được đưa vào cơ chế quản lý bean của Spring hay không**.

### 5.1. Khi nào dùng @Bean?

**@Bean** thường phù hợp khi:

- Bạn muốn đăng ký một lớp bên thứ ba không thể thêm annotation Spring vào source.
- Cần truyền tham số constructor do cấu hình quyết định.
- Muốn một factory method thể hiện cách tạo instance rõ ràng.
- Muốn lựa chọn implementation hoặc cấu hình các đối tượng tích hợp dựa trên dependency.

Ví dụ:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    ApiClient apiClient(ApiClientProperties properties) {
        return new ApiClient(properties.getBaseUrl());
    }
}
~~~

Giả sử **ApiClient** là lớp thư viện và **ApiClientProperties** đã được Spring đăng ký làm bean cấu hình. Spring có thể inject properties vào factory method, sau đó quản lý ApiClient được trả về theo định nghĩa bean.

### 5.2. Có thể tạo object rồi đăng ký trực tiếp không?

Spring có các API cấp thấp để đăng ký singleton đã tạo hoặc đăng ký bean definition/supplier vào một BeanFactory/registry phù hợp. Đó là những trường hợp nâng cao, ví dụ tích hợp framework hay lập trình cấu hình động.

Nhưng **new** rồi lưu vào một biến cục bộ, một field hoặc một collection **không phải** là hành vi đăng ký bean. Phải có bước đăng ký hoặc tạo qua một bean definition rõ ràng.

Các API đăng ký instance đã tồn tại có thể có khác biệt về việc áp dụng đầy đủ lifecycle và bean post-processing so với đường tạo bean thông thường. Vì vậy đối với ứng dụng phổ biến, **@Component** hoặc **@Bean** là điểm bắt đầu dễ hiểu và dễ kiểm soát hơn.

## 6. Ai quản lý vòng đời của object?

Với object tạo thủ công:

~~~java
ReportClient client = new ReportClient();
client.connect();
client.sendReport();
client.close();
~~~

Code của bạn phải biết khi nào cần khởi tạo, sử dụng và đóng tài nguyên. Nếu quên đóng một client giữ socket hoặc thread pool, có thể xảy ra rò rỉ tài nguyên. **Garbage collector không thay thế nghĩa vụ đóng tài nguyên bên ngoài heap**.

Với Spring bean, container có thể xử lý các callback và extension point lifecycle. Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class CacheWarmup {

    @PostConstruct
    public void initialize() {
        System.out.println("Khởi tạo tài nguyên của bean");
    }

    @PreDestroy
    public void shutdown() {
        System.out.println("Giải phóng tài nguyên của bean");
    }
}
~~~

Đối với singleton bean được Spring tạo và quản lý, các callback tương ứng có thể được xử lý khi bean khởi tạo và khi ApplicationContext đóng bình thường.

Nếu bạn tự tạo:

~~~java
CacheWarmup manual = new CacheWarmup();
~~~

Spring không tự động gọi **initialize()** cho object đó, và không tự động gọi **shutdown()** khi context đóng. Annotation lifecycle chỉ có ý nghĩa khi được cơ chế xử lý phù hợp áp dụng.

### 6.1. Các bước lifecycle phổ biến

Một mô hình khái niệm cho singleton bean:

~~~text
Đọc BeanDefinition / resolve dependency
                     │
                     ▼
               Tạo object
                     │
                     ▼
             Dependency injection
                     │
                     ▼
         BeanPostProcessor trước init
                     │
                     ▼
      @PostConstruct / initializing callbacks
                     │
                     ▼
          BeanPostProcessor sau init
                     │
                     ▼
           Bean sẵn sàng sử dụng
                     │
                     ▼
            Context đóng bình thường
                     │
                     ▼
         @PreDestroy / destroy callbacks
~~~

Trình tự đầy đủ trong Spring có nhiều chi tiết hơn và có thể thay đổi theo phương thức tạo bean, scope, proxy hoặc các extension point. Sơ đồ chỉ cho thấy container làm **nhiều hơn hành động gọi constructor**.

### 6.2. Constructor vẫn chạy khi Spring tạo bean

Một bean bình thường vẫn cần instance Java thực sự. Khi container tạo bằng constructor, constructor đó **vẫn được gọi**, giống như khi bạn gọi new. Spring không bỏ qua quá trình khởi tạo của ngôn ngữ Java.

Điểm khác biệt là Spring có thể:

1. Chọn constructor và resolve dependency.
2. Tạo instance hoặc gọi factory method.
3. Áp dụng các bước injection, callback và post-processing.
4. Quản lý scope và trả đối tượng/proxy phù hợp cho consumer.

Vì vậy câu “bean được Spring tạo nên không dùng new” chỉ là cách nói giản lược, dễ gây hiểu lầm.

### 6.3. Không phải scope nào cũng được container hủy như singleton

Spring quản lý lifecycle khác nhau tùy scope. Với **singleton**, Spring thường quản lý callback hủy khi context đóng. Với **prototype**, container tạo và khởi tạo object khi được yêu cầu, nhưng **không tự theo dõi mọi instance prototype để gọi đầy đủ destruction callback khi context đóng**. Chủ sở hữu sử dụng prototype phải tự giải quyết phần cleanup khi cần.

Với **request** hoặc **session** scope trong môi trường web phù hợp, lifecycle gắn với request hoặc session. Một bean dùng trong môi trường không hỗ trợ scope tương ứng có thể gặp lỗi khi truy cập.

## 7. Singleton bean khác singleton object theo cách tự thiết kế

Một Java class có thể tự cài singleton bằng static field:

~~~java
public final class ManualRegistry {
    private static final ManualRegistry INSTANCE = new ManualRegistry();

    private ManualRegistry() {
    }

    public static ManualRegistry getInstance() {
        return INSTANCE;
    }
}
~~~

Đây là một mẫu thiết kế do Java class kiểm soát, độc lập với Spring.

Ngược lại:

~~~java
@Service
public class OrderService {
    // ...
}
~~~

nếu được Spring đăng ký dưới singleton scope mặc định, container thường tạo và sử dụng **một instance cho mỗi bean definition trong một ApplicationContext**.

Hai khái niệm khác nhau:

| Tiêu chí | Singleton tự thiết kế bằng Java | Spring singleton scope |
|---|---|---|
| Ai quyết định instance? | Class/static field/factory của ứng dụng. | Spring container và bean definition. |
| Phạm vi thông thường | Theo class loader/cơ chế static của JVM. | Trong một Spring container cho bean definition đó. |
| Khởi tạo | Do code static/factory quyết định. | Theo lifecycle và thời điểm khởi tạo bean. |
| Dependency injection | Phải tự thiết kế hoặc tích hợp thủ công. | Có thể được Spring resolve/inject. |
| Callback lifecycle của Spring | Không tự có. | Có thể được xử lý theo cơ chế bean. |

Một ứng dụng có thể có **nhiều ApplicationContext**, hoặc nhiều bean definition cho cùng một class. Khi ấy “Spring singleton” không có nghĩa một object duy nhất trong toàn bộ JVM.

### 7.1. Singleton bean có tự thread-safe không?

**Không.** Scope singleton chỉ quy định cách chia sẻ instance; nó không tự đảm bảo đồng bộ dữ liệu.

Ví dụ không nên đặt trạng thái request vào field dùng chung:

~~~java
@Service
public class UnsafeCounterService {
    private int counter;

    public int next() {
        return ++counter;
    }
}
~~~

Nhiều request có thể gọi **next()** đồng thời. Phép tăng **++counter** không phải thao tác nguyên tử an toàn cho cạnh tranh luồng, nên có nguy cơ trả kết quả sai.

Nếu cần bộ đếm chia sẻ trong một process, có thể dùng cấu trúc phù hợp như **AtomicInteger**:

~~~java
@Service
public class CounterService {
    private final java.util.concurrent.atomic.AtomicInteger counter =
            new java.util.concurrent.atomic.AtomicInteger();

    public int next() {
        return counter.incrementAndGet();
    }
}
~~~

Điều này giải quyết tính nguyên tử của bộ đếm đơn giản trong một JVM; nó không thay thế bộ đếm phân tán nếu ứng dụng có nhiều instance.

## 8. Scope: Spring có thể tạo một hoặc nhiều instance

Bean có thể tồn tại dưới những scope khác nhau:

| Scope | Ý nghĩa thường gặp |
|---|---|
| **singleton** | Một instance cho một bean definition trong một container; mặc định phổ biến. |
| **prototype** | Tạo instance mới khi container nhận yêu cầu lấy bean đó. |
| **request** | Instance gắn với một HTTP request trong web-aware context. |
| **session** | Instance gắn với một HTTP session trong web-aware context. |
| **application** | Scope gắn với ServletContext trong môi trường phù hợp. |
| **websocket** | Scope gắn với WebSocket session khi có môi trường tương ứng. |

Ví dụ prototype:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    private final java.util.UUID id = java.util.UUID.randomUUID();

    public java.util.UUID getId() {
        return id;
    }
}
~~~

Khi gọi:

~~~java
ReportDraft first = context.getBean(ReportDraft.class);
ReportDraft second = context.getBean(ReportDraft.class);

System.out.println(first == second); // false với prototype thông thường
~~~

Như vậy **bean không đồng nghĩa với singleton**. Spring quản lý cách cung cấp bean theo scope, còn object tạo bằng new chỉ theo logic bạn viết.

### 8.1. Prototype được inject vào singleton có tạo object mới mỗi lần gọi không?

Giả sử:

~~~java
@Service
public class ReportService {
    private final ReportDraft draft;

    public ReportService(ReportDraft draft) {
        this.draft = draft;
    }
}
~~~

Nếu **ReportService** là singleton và **ReportDraft** là prototype, Spring thường resolve một instance prototype **tại thời điểm tạo singleton ReportService**. Field draft sẽ tiếp tục tham chiếu tới instance đó trong suốt thời gian service tồn tại. Nó **không tự tạo ReportDraft mới cho mỗi lời gọi phương thức**.

Khi muốn lấy một prototype mới theo nhu cầu, có thể inject **ObjectProvider**:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ObjectProvider<ReportDraft> draftProvider;

    public ReportService(ObjectProvider<ReportDraft> draftProvider) {
        this.draftProvider = draftProvider;
    }

    public ReportDraft createDraft() {
        return draftProvider.getObject();
    }
}
~~~

Mỗi lần **getObject()** được gọi trong trường hợp prototype thông thường, Spring cung cấp một instance mới. Đây là khác biệt rõ ràng giữa **yêu cầu bean qua container** và **giữ một reference đã inject**.

### 8.2. Request-scoped bean và scope proxy

Một bean gắn với HTTP request có thể cần được dùng từ singleton service. Không thể chỉ giữ một object request-scoped cố định cho toàn bộ đời sống singleton. Spring hỗ trợ cơ chế scoped proxy hoặc provider để ánh xạ lời gọi tới instance đang thuộc request hiện tại.

Ví dụ về khai báo:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {
    // Dữ liệu gắn với request hiện tại.
}
~~~

**@RequestScope** theo cấu hình mặc định sử dụng cơ chế proxy thích hợp để việc inject vào bean sống lâu hơn có thể hoạt động. Tuy nhiên, instance thực tế vẫn cần **request context đang hoạt động**. Gọi vào bean request-scoped từ một background thread ngoài request có thể thất bại nếu không có context phù hợp.

Đừng dùng request-scoped bean như một singleton Java tĩnh hoặc tự giữ instance qua nhiều request.

## 9. Proxy: thứ bạn inject có thể khác instance bên trong

Một lợi ích quan trọng của Spring bean là container có thể áp dụng **BeanPostProcessor** và các cơ chế **AOP proxy** khi hạ tầng thích hợp được kích hoạt.

Ví dụ một service được Spring quản lý:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        // Logic nghiệp vụ liên quan tới database.
    }
}
~~~

Nếu Spring transaction management đã được cấu hình phù hợp, một lời gọi vào bean được Spring cung cấp có thể đi qua proxy để mở/điều phối transaction quanh phương thức.

~~~text
Controller
    │ gọi bean do Spring inject
    ▼
OrderService proxy
    │
    ├── Transaction interceptor
    │      ├── bắt đầu / tham gia transaction
    │      ├── gọi logic thật
    │      └── commit / rollback theo quy tắc
    │
    ▼
OrderService target instance
~~~

Nhưng:

~~~java
OrderService manual = new OrderService();
manual.placeOrder();
~~~

Object này không mặc nhiên được bọc trong transaction proxy của Spring. Annotation **@Transactional** không được JVM tự hiểu như một lệnh mở database transaction. Đó là metadata để hạ tầng Spring phù hợp xử lý lời gọi theo các điều kiện được hỗ trợ.

**Cần chú ý:** transaction không thể hoạt động chỉ bằng cách đánh dấu một phương thức. Ứng dụng phải có **PlatformTransactionManager** hoặc transaction infrastructure tương ứng và đường gọi phù hợp. Ví dụ tối giản ở trên chỉ minh họa sự khác biệt về cách quản lý object, không khẳng định tự có transaction khi chưa cấu hình datasource/transaction manager.

### 9.1. Transaction proxy không được kích hoạt với mọi lời gọi

Trong chế độ proxy thông dụng, lời gọi phải đi qua proxy:

~~~text
Bean A → OrderService proxy → @Transactional method
~~~

Nếu target gọi một method khác trên chính nó:

~~~java
@Service
public class OrderService {
    public void placeAndNotify() {
        placeOrder();
    }

    @Transactional
    public void placeOrder() {
        // ...
    }
}
~~~

Lời gọi **placeOrder()** từ **placeAndNotify()** là **self-invocation** trên đối tượng hiện tại; trong cơ chế Spring AOP proxy thông dụng, nó không đi qua proxy để bắt đầu advice transaction riêng cho **placeOrder()**. Nếu **placeAndNotify()** đã chạy trong một transaction được mở từ nơi khác, logic có thể vẫn nằm trong transaction hiện có; điều không xảy ra ở đây là áp dụng advice mới qua lời gọi self-invocation.

Điều này chứng minh rằng **có bean** là điều kiện cần để tận dụng nhiều cơ chế Spring, nhưng chưa đủ để bảo đảm mọi đường gọi đều đi qua AOP.

### 9.2. Một số tính năng khác có thể phụ thuộc proxy

Tùy cách cấu hình và công nghệ:

- **@Transactional** có thể dùng interceptor để quản lý ranh giới transaction.
- **@Cacheable** có thể dùng cache interceptor khi Spring caching được kích hoạt.
- **@Async** có thể dùng proxy để chuyển lời gọi sang executor khi asynchronous method execution được bật.
- Custom aspect có thể chèn logic chung quanh method call.

Tất cả đều có yêu cầu riêng về hạ tầng và kiểu lời gọi. **Object tạo bằng new bên ngoài container không tự nhận các proxy và interceptor đó.**

### 9.3. So sánh reference của bean có proxy

Với Spring AOP, **context.getBean(OrderService.class)** có thể trả proxy, tùy cách Spring chọn kiểu proxy và tính tương thích kiểu. Target thật có thể khác instance proxy.

Không nên lấy việc in **getClass()**, dùng **==** hoặc kiểm tra một annotation trên runtime proxy làm bằng chứng tuyệt đối rằng object không phải bean. Cần hiểu bean definition, scope và cơ chế proxy đang hoạt động.

## 10. Ví dụ end-to-end trong Spring Boot: controller, service và repository

Hãy xây dựng một API đọc thông tin đơn hàng, tập trung vào việc **ai tạo các object và ai cung cấp dependency**.

### 10.1. Repository

~~~java
package com.example.store.repository;

import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    public String findName(long id) {
        if (id == 1L) {
            return "Bút máy";
        }
        return "Sản phẩm #" + id;
    }
}
~~~

Ví dụ này dùng repository thuần Java để minh họa IoC, chưa kết nối cơ sở dữ liệu. Annotation **@Repository** giúp class có thể được phát hiện như một component khi được quét. Nó còn mang ý nghĩa chuyên biệt cho tầng truy cập dữ liệu và có thể tham gia các cơ chế persistence exception translation khi hạ tầng tương ứng được cấu hình.

### 10.2. Service có constructor injection

~~~java
package com.example.store.service;

import com.example.store.repository.ProductRepository;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public String describe(long productId) {
        return "Tên sản phẩm: " + repository.findName(productId);
    }
}
~~~

Service không gọi **new ProductRepository()**. Nó công bố nhu cầu qua constructor và cho phép bên tạo service cung cấp dependency.

### 10.3. Controller sử dụng service

~~~java
package com.example.store.web;

import com.example.store.service.ProductService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/products/{id}/description")
    public String description(@PathVariable long id) {
        return productService.describe(id);
    }
}
~~~

Trong ứng dụng Spring MVC có hạ tầng web đầy đủ, **@RestController** đăng ký một component web, còn **@GetMapping** khai báo mapping của phương thức xử lý request.

### 10.4. Điểm khởi động

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

Nếu dự án có dependency **spring-boot-starter-web** phù hợp và các lớp nằm trong các package con của **com.example.store**, component scanning thông thường sẽ tìm thấy repository, service và controller.

Spring sẽ lắp ráp:

~~~text
                  ApplicationContext
                         │
             ┌───────────┴───────────┐
             │                       │
     ProductRepository          ProductService
          bean                       bean
             │                       │
             └─────inject───────────►│
                                     │
                               ProductController
                                     bean
                                      ▲
                       inject service │
                                      │
                            HTTP GET /products/1/description
~~~

Trong hình, hai mũi tên chỉ sự cung cấp dependency; thứ tự đặt nhãn không phải timeline chính xác của Spring.

Request minh họa:

~~~http
GET /products/1/description HTTP/1.1
Host: localhost:8080
~~~

Body response:

~~~text
Tên sản phẩm: Bút máy
~~~

Đây là kết quả mong đợi nếu ứng dụng khởi động đúng ở cổng 8080, không có cấu hình path/security khác can thiệp và các thành phần Spring MVC hoạt động bình thường.

### 10.5. Điều gì xảy ra nếu controller tự new service?

Thay constructor injection bằng:

~~~java
@RestController
public class ProductController {
    private final ProductService productService =
            new ProductService(new ProductRepository());

    // Các handler sử dụng productService...
}
~~~

Đoạn code vẫn có thể hoạt động cho ví dụ đơn giản vì bạn đã cung cấp đủ constructor arguments. Nhưng:

- **ProductController** là bean nếu được Spring quét; **ProductService** trong field này không nhất thiết là bean của context.
- **ProductRepository** mới tạo cũng không phải bean repository do context đang quản lý.
- Các thay đổi cấu hình, mock, wrapper và proxy trên bean thực sự trong context có thể không tác động tới hai object thủ công đó.
- Controller tự chịu trách nhiệm lựa chọn và lắp ráp dependency, nên liên kết trực tiếp với implementation.

Giả sử sau này service được thiết kế có **@Transactional** và repository là một bean truy cập database thực sự; việc tự new một service/repository không bảo đảm transaction, exception translation, dependency injection hay cấu hình DataSource hoạt động theo Spring.

**Sự khác biệt không nằm ở việc phương thức describe() hiện có trả kết quả giống nhau, mà nằm ở hợp đồng quản lý và mở rộng của những object được sử dụng.**

## 11. Bean nhận cấu hình khác với object new thủ công

Spring Boot thường sử dụng **externalized configuration** để đưa giá trị từ file cấu hình, biến môi trường và các nguồn property phù hợp vào ứng dụng.

Ví dụ một component:

~~~java
package com.example.store;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ReceiptFormatter {
    private final String prefix;

    public ReceiptFormatter(
            @Value("${store.receipt-prefix:Receipt}") String prefix) {
        this.prefix = prefix;
    }

    public String format(long orderId) {
        return prefix + " #" + orderId;
    }
}
~~~

Với cấu hình:

~~~yaml
store:
  receipt-prefix: "Hóa đơn"
~~~

nếu class được Spring quét và Spring xử lý **@Value** thích hợp, container có thể truyền **"Hóa đơn"** vào constructor.

Nhưng gọi trực tiếp:

~~~java
ReceiptFormatter formatter = new ReceiptFormatter("Manual receipt");
~~~

thì bạn tự quyết định chuỗi truyền vào. Java không tự đọc **application.yml** chỉ vì constructor parameter được chú thích **@Value**. Nếu constructor cần đối số String, bạn vẫn phải đưa đối số vào khi dùng new.

Với field injection:

~~~java
@Component
public class LegacyFormatter {
    @Value("${store.receipt-prefix:Receipt}")
    private String prefix;

    public String format(long id) {
        return prefix + " #" + id;
    }
}
~~~

Gọi **new LegacyFormatter()** sẽ không tự kích hoạt Spring property injection. Field **prefix** vẫn có thể là **null**, tạo kết quả sai hoặc exception tùy cách sử dụng.

### 11.1. Configuration properties được bind cho bean

Spring Boot cũng hỗ trợ các object kiểu **@ConfigurationProperties** để bind một nhóm property thành cấu hình có cấu trúc. Việc bind này cần được kích hoạt theo cơ chế phù hợp như **@EnableConfigurationProperties** hoặc **@ConfigurationPropertiesScan**, hoặc qua một bean được đăng ký cho cơ chế binding được hỗ trợ.

Chỉ khai báo:

~~~java
@org.springframework.boot.context.properties.ConfigurationProperties(
        prefix = "store")
public class StoreProperties {
    private String receiptPrefix;

    public String getReceiptPrefix() {
        return receiptPrefix;
    }

    public void setReceiptPrefix(String receiptPrefix) {
        this.receiptPrefix = receiptPrefix;
    }
}
~~~

rồi tự chạy:

~~~java
StoreProperties properties = new StoreProperties();
~~~

sẽ không khiến Spring Boot tự điền giá trị vào instance thủ công đó. Property binding là một quá trình cấu hình, cần một cơ chế thực thi, không phải hành vi của từ khóa new.

## 12. Nên dùng new khi nào? Không phải mọi object đều cần thành bean

Một sai lầm theo chiều ngược lại là cố biến **mọi object** của ứng dụng thành bean. Spring IoC không nhằm quản lý từng chuỗi, từng DTO, từng record, từng entity hoặc từng phần tử trong collection.

### 12.1. Value object và DTO

Ví dụ:

~~~java
public record Money(long amount, String currency) {
}
~~~

~~~java
Money price = new Money(120_000L, "VND");
~~~

**Money** là một giá trị gắn với nghiệp vụ. Thông thường không cần đăng ký mỗi Money instance thành một bean. Mỗi giá trị tiền tệ có thể được tạo theo nhu cầu và truyền qua các phương thức như một object Java bình thường.

Tương tự:

~~~java
public record CreateOrderRequest(long productId, int quantity) {
}
~~~

**CreateOrderRequest** là DTO mô tả dữ liệu của một request. Spring MVC có thể dùng cơ chế chuyển đổi/binding để tạo DTO từ request, nhưng **DTO đó không mặc nhiên là bean singleton được quản lý trong ApplicationContext**.

Không nên đặt trạng thái riêng của mỗi request vào field của singleton bean chỉ vì “muốn dùng Spring cho tất cả”.

### 12.2. JPA entity

Entity như:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Order {
    @Id
    @GeneratedValue
    private Long id;

    private String description;

    protected Order() {
    }

    public Order(String description) {
        this.description = description;
    }
}
~~~

thường là object thuộc mô hình persistence, có lifecycle liên quan **JPA EntityManager/persistence context**. Nó không tự động là Spring bean chỉ vì có **@Entity**.

Trong code nghiệp vụ, bạn có thể tạo:

~~~java
Order order = new Order("Mua bút");
~~~

và yêu cầu repository/entity manager persist theo cơ chế JPA. Quản lý **JPA entity lifecycle** và quản lý **Spring bean lifecycle** là hai khái niệm khác nhau.

### 12.3. Đối tượng tạm hoặc thuật toán nhỏ

Một object chỉ phục vụ phép tính cục bộ, không cần DI/lifecycle, có thể được tạo trực tiếp:

~~~java
StringBuilder builder = new StringBuilder();
builder.append("ORDER-").append(123L);
String code = builder.toString();
~~~

Không có lợi ích trong việc biến từng StringBuilder thành bean. Tương tự với đa số data structures và objects được tạo cho một yêu cầu ngắn hạn.

### 12.4. Service/repository/controller và các collaborator chia sẻ

Các thành phần có dependency, cấu hình, transaction, lifecycle hoặc cần dùng lại qua nhiều consumer thường phù hợp để Spring quản lý:

- Business service như **OrderService**, **PaymentService**.
- Repository hoặc các adapter truy cập dữ liệu.
- HTTP client được cấu hình chung, serializer hay connection-pool wrapper.
- Controller, filter hoặc các thành phần framework tích hợp.
- Các service chứa cấu hình môi trường và dependency được inject.

Tuy nhiên, một object dùng ngắn hạn **có thể cần factory** thay vì singleton bean, nếu mỗi lần sử dụng yêu cầu state riêng. Khi đó Spring có thể quản lý **factory** chứ không nhất thiết quản lý từng kết quả mà factory tạo ra.

### 12.5. Bảng chọn cách tạo

| Trường hợp | Cách thường phù hợp | Lý do |
|---|---|---|
| Tạo DTO từ một request | Constructor, record, mapper hoặc data binding | Dữ liệu riêng của request, không cần singleton bean. |
| Tạo JPA entity mới | Constructor/factory/domain method, sau đó persist | Entity thuộc persistence lifecycle. |
| Service có repository và transaction | Spring bean + constructor injection | Container quản lý dependency, proxy và lifecycle thích hợp. |
| Client của thư viện bên thứ ba dùng chung | **@Bean** trả về instance được cấu hình | Có thể tạo bằng new bên trong factory method nhưng vẫn được quản lý. |
| Giá trị tạm cho phép tính | **new** hoặc factory Java thuần | Nhẹ, không cần container. |
| Object có state riêng cho mỗi lần xử lý | **new**, factory, prototype hoặc scope phù hợp | Tránh state bị chia sẻ ngoài ý muốn. |
| Unit test logic thuần | **new** kết hợp mock/fake dependency | Test nhanh, không cần khởi động Spring. |
| Kiểm thử wiring/auto-configuration | Spring test context | Cần thực sự kiểm tra cấu hình container. |

## 13. Unit test và integration test: vì sao new vẫn rất hữu ích?

Khi dùng constructor injection, logic nghiệp vụ có thể được kiểm thử mà **không khởi động Spring context**.

Ví dụ service:

~~~java
public class TaxService {
    private final TaxRateProvider rateProvider;

    public TaxService(TaxRateProvider rateProvider) {
        this.rateProvider = rateProvider;
    }

    public long calculate(long amount) {
        return Math.round(amount * rateProvider.currentRate());
    }
}
~~~

Interface:

~~~java
public interface TaxRateProvider {
    double currentRate();
}
~~~

Unit test độc lập:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class TaxServiceTest {

    @Test
    void calculatesTaxUsingProvidedRate() {
        TaxRateProvider fakeRateProvider = () -> 0.10;
        TaxService service = new TaxService(fakeRateProvider);

        assertEquals(10L, service.calculate(100L));
    }
}
~~~

Đây là ví dụ **new là lựa chọn tốt**. Service được thiết kế nhận dependency qua constructor, nên test không cần tạo cả ApplicationContext.

Ngược lại, nếu bạn muốn xác minh **@Transactional**, autowiring, component scanning, bean scope hoặc auto-configuration có thực sự hoạt động, một test chỉ new object sẽ không chứng minh những chức năng đó. Cần test có Spring context và hạ tầng tương ứng.

### 13.1. Hai mức kiểm thử có mục đích khác nhau

| Mục tiêu | Unit test với new | Test với Spring context |
|---|---|---|
| Logic tính toán hoặc điều kiện nghiệp vụ | Phù hợp. | Có thể dùng nhưng thường nặng hơn yêu cầu. |
| Constructor nhận dependency đúng hợp đồng | Phù hợp. | Cũng kiểm tra được khi wiring. |
| Component scanning có đăng ký bean không | Không tự chứng minh. | Phù hợp. |
| Property binding hoạt động không | Không tự chứng minh. | Phù hợp. |
| AOP transaction interceptor có được áp dụng không | Không tự chứng minh. | Cần context và transaction infrastructure. |
| HTTP mapping hoạt động trong MVC không | Không tự chứng minh. | Cần các công cụ test web phù hợp. |

Đừng biến mọi unit test thành integration test chỉ vì class production là **@Service**. Nhưng cũng đừng giả định một unit test tạo object bằng new chứng minh toàn bộ hành vi Spring.

## 14. Những lỗi dễ gặp khi trộn new với Spring bean

### 14.1. NullPointerException ở field @Autowired

Code:

~~~java
@Service
public class InvoiceService {
    @Autowired
    private InvoiceRepository repository;

    public void createInvoice() {
        repository.save();
    }
}
~~~

Đường gọi:

~~~java
new InvoiceService().createInvoice();
~~~

Có thể ném **NullPointerException** vì **repository** không được inject. Nguyên nhân không phải annotation mất tác dụng; object này chưa được Spring xử lý.

Hướng sửa thường là **constructor injection** và để consumer nhận InvoiceService bean nếu cần các tính năng container:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu InvoiceService được dùng như một lớp Java thuần trong unit test, bạn có thể tự truyền một fake repository vào constructor.

### 14.2. @PostConstruct không được gọi

Giả sử:

~~~java
@Component
public class TemplateRegistry {
    private java.util.Map<String, String> templates;

    @PostConstruct
    void initialize() {
        templates = java.util.Map.of("default", "Xin chào");
    }
}
~~~

Tạo thủ công bằng **new TemplateRegistry()** không kích hoạt callback **@PostConstruct**. Nếu code dùng field **templates** ngay, nó có thể là null.

Hướng thiết kế tốt thường là đưa các trạng thái bắt buộc vào constructor nếu khả thi; còn nếu thực sự cần lifecycle container, hãy sử dụng instance bean do context quản lý.

### 14.3. @Transactional không có tác dụng như mong đợi

~~~java
@Service
public class TransferService {
    @Transactional
    public void transfer() {
        // Thao tác chuyển tiền.
    }
}
~~~

Nếu service được tự new rồi gọi trực tiếp, không có transaction advice của Spring tự áp vào object đó.

Ngay cả khi dùng bean, lời gọi nội bộ không qua proxy vẫn là một trường hợp khác cần hiểu. Hãy xác định **ai tạo object, lời gọi đi qua proxy không và hạ tầng transaction đã cấu hình đúng chưa** trước khi sửa annotation.

### 14.4. Cấu hình trong application.yml không được áp dụng

Một object tự new không tự được Spring đọc **@Value** hoặc bind **@ConfigurationProperties**. Nếu một bean được Spring tạo thông qua constructor/factory method và cấu hình được đăng ký phù hợp, các giá trị có thể được cung cấp từ Environment.

Hãy truy nguyên rõ: giá trị do ai truyền, bean nào được đăng ký, property nào đang được nạp và profile nào hoạt động.

### 14.5. Có hai instance nhưng tưởng chỉ có một

~~~java
@Service
public class SequenceGenerator {
    private int value;

    public int next() {
        return ++value;
    }
}
~~~

Nếu ở một chỗ sử dụng bean và ở chỗ khác viết **new SequenceGenerator()**, hai nơi có state độc lập. Cách gọi số thứ tự hoặc trạng thái đăng nhập có thể cho kết quả khó hiểu.

Đây còn là ví dụ về nguy cơ race condition khi sử dụng mutable singleton; dù có chỉ một bean, phép **++value** vẫn không tự thread-safe.

### 14.6. Không tìm thấy bean dù đã thêm @Service

**NoSuchBeanDefinitionException** hoặc **UnsatisfiedDependencyException** có thể do:

- Class nằm ngoài component-scan scope.
- Bean chỉ được tạo khi profile/condition thỏa.
- Một constructor dependency khác không được đăng ký.
- Class chưa nằm trong runtime classpath cần thiết.
- Bạn đang inject một kiểu hoặc qualifier không khớp.

Không nên sửa mọi trường hợp thiếu bean bằng cách **new** object ngay trong controller. Làm vậy có thể che nguyên nhân và làm mất DI ở toàn bộ chuỗi dependency.

### 14.7. Có nhiều bean cùng kiểu

Nếu context có hai bean **NotificationSender**, injection theo kiểu không có qualifier có thể mơ hồ. Đây là vấn đề chọn bean, **không phải lỗi do container tạo nhiều object vô ích**.

Cần kiểm tra bean names, qualifiers, primary candidate và ý đồ cấu hình trước khi quyết định. Đôi khi cần cả hai bean để xử lý hai loại kênh gửi thông báo.

## 15. Cách nhận biết một object có thuộc Spring context không

Một biến Java tự nó không cho biết chắc chắn nguồn tạo object. Nhiều component có thể được truyền qua API chung; proxy cũng có thể che class thực.

Hãy xem **đường đi của reference**.

### 15.1. Tìm nơi tạo object

Nếu code:

~~~java
ReportService reportService = new ReportService(new ReportRepository());
~~~

thì đây là các object được lắp ráp thủ công trong đoạn code hiện tại.

Nếu code:

~~~java
public ReportController(ReportService reportService) {
    this.reportService = reportService;
}
~~~

và **ReportController** là bean do Spring tạo, tham số constructor **reportService** thường được Spring resolve từ container. Tuy nhiên cần biết phương thức/bean registration cụ thể và các custom factory nếu ứng dụng có cấu hình đặc biệt.

### 15.2. Kiểm tra đăng ký bean trong ApplicationContext

Ví dụ:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInspector {
    private final ApplicationContext context;

    public BeanInspector(ApplicationContext context) {
        this.context = context;
    }

    public void inspect() {
        System.out.println(
                context.getBeanNamesForType(ReportService.class).length
        );
    }
}
~~~

Đây là cách quan sát **những bean context có thể tìm theo type**. Nó không kiểm tra một object cụ thể bằng reference. Kết quả còn phụ thuộc loại bean, factory bean và trạng thái context. Trong code nghiệp vụ, không nên dùng các lệnh lookup hoặc introspection thay cho constructor injection chỉ để lấy dependency thông thường.

### 15.3. Khi nghi vấn nằm ở auto-configuration

Spring Boot có **condition evaluation report** giúp giải thích một số điều kiện auto-configuration đã hoặc chưa thỏa. Nếu bean được tạo tự động bởi Boot, việc xem điều kiện và classpath có thể hữu ích.

Nếu đã thêm Actuator và expose endpoint thích hợp, endpoint **beans** có thể giúp quan sát bean trong các application context:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans
~~~

Khi được kích hoạt và truy cập theo cấu hình, endpoint thường nằm ở **/actuator/beans**. Cần giới hạn quyền truy cập endpoint quản trị theo yêu cầu bảo mật, bởi dữ liệu có thể tiết lộ cấu trúc nội bộ của ứng dụng.

Một bean không xuất hiện ở báo cáo như mong đợi có thể do scan, profile, condition, scope hoặc cấu hình context. Hãy đối chiếu với source và startup log.

## 16. Một sơ đồ quyết định: nên new hay nhận bean?

~~~text
Bạn cần một object
       │
       ▼
Object chỉ chứa dữ liệu / giá trị riêng của lần xử lý?
       │
       ├── Có
       │     └── new / factory Java / binding thường phù hợp
       │
       └── Không
             │
             ▼
Nó có cần dependency của ứng dụng,
config, lifecycle hoặc AOP của Spring?
             │
             ├── Có
             │    └── Đăng ký Spring bean và inject vào consumer
             │
             └── Không
                   │
                   ▼
Nó có cần được chia sẻ/cấu hình nhất quán
cho nhiều thành phần của ứng dụng?
                   │
                   ├── Có
                   │    └── Cân nhắc bean hoặc factory được quản lý
                   │
                   └── Không
                        └── Tạo trực tiếp theo nhu cầu
~~~

Sơ đồ này không phải quy tắc cứng. Một object có trạng thái riêng có thể được cung cấp qua **prototype bean** hoặc một factory do Spring quản lý; một lớp không cần Spring có thể được dùng trong Spring bean mà bản thân không phải bean.

Nguyên tắc thiết kế sâu hơn là **phân biệt logic nghiệp vụ với việc lắp ráp object graph**. Những object quản lý dependency và hạ tầng ứng dụng có thể được Spring điều phối, còn những object mô tả dữ liệu ngắn hạn có thể được tạo trực tiếp.

## 17. Bài tập tự phân biệt

### Tình huống 1: new bên trong @Bean

~~~java
@Configuration
class MyConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

**Clock được trả về có phải bean không?** Có, nếu cấu hình được Spring xử lý và definition được đăng ký. Việc **Clock.systemUTC()** trả về một object Java không cản trở object đó trở thành bean.

### Tình huống 2: @Service nhưng gọi new

~~~java
@Service
class ReportService {
}

ReportService report = new ReportService();
~~~

**Biến report có tham chiếu bean do Spring quản lý không?** Không tự động. Class mang **@Service** có thể tạo một bean khác khi component scanning hoạt động, nhưng instance được tạo trực tiếp trong dòng **new** không được đăng ký chỉ bởi annotation đó.

### Tình huống 3: Singleton prototype và lookup

~~~java
@Component
@Scope("prototype")
class JobContext {
}
~~~

~~~java
JobContext first = context.getBean(JobContext.class);
JobContext second = context.getBean(JobContext.class);
~~~

**first và second có phải cùng instance không?** Với prototype scope thông thường, không. Cả hai đều là những bean instance được container tạo theo yêu cầu, nhưng chúng khác nhau.

### Tình huống 4: Object tự new với annotation lifecycle

~~~java
@Component
class WorkerClient {
    @PostConstruct
    void start() {
        System.out.println("Started");
    }
}

WorkerClient client = new WorkerClient();
~~~

**Có tự in Started không?** Không vì riêng hành động new không kích hoạt Spring lifecycle processing. Nếu constructor của class có logic in thì đó là trường hợp khác; ở ví dụ này method **start()** chỉ được đánh dấu bằng annotation.

### Tình huống 5: DTO tạo trong controller

~~~java
@GetMapping("/status")
public StatusResponse status() {
    return new StatusResponse("OK");
}
~~~

**StatusResponse có cần là Spring bean không?** Thường không. Đây là DTO của response, được tạo cho dữ liệu trả về. Controller có thể là bean nhưng object DTO do nó tạo ra không vì thế trở thành bean.

### Tình huống 6: Dùng cùng class ở hai nơi

~~~java
PricingService fromContext = context.getBean(PricingService.class);
PricingService manual = new PricingService(...);
~~~

**Hai reference có chắc là một object không?** Không. Đối tượng thủ công và bean context thông thường là hai instance khác nhau, dù cùng kiểu Java. Cần hiểu constructor, scope và proxy của bean khi phân tích identity.

## 18. Những hiểu nhầm thường gặp

**“Bean không phải object Java bình thường.”**  
Bean vẫn là đối tượng Java. Khác biệt là container quản lý quá trình tạo, lắp ráp, scope và lifecycle; reference có thể trỏ tới proxy do Spring tạo.

**“Spring không dùng new khi tạo bean.”**  
Spring có thể dùng constructor hoặc gọi factory method trả về object tạo bằng new. Quan trọng là **quyền quản lý instance**.

**“Thêm @Component lên class là mọi new của class đó đều được inject.”**  
Không. Component scanning đăng ký bean definition phù hợp; nó không thay đổi các lời gọi new tùy ý trong chương trình.

**“Chỉ cần @Autowired thì field sẽ được điền dù ai tạo object.”**  
Không. Autowiring cần cơ chế Spring phù hợp xử lý object. Với object thủ công, field có thể giữ giá trị null.

**“Bean nào cũng là singleton và mọi lookup trả cùng object.”**  
Không. Scope có thể là prototype, request hoặc session; proxy và nhiều ApplicationContext còn khiến identity cần xem theo ngữ cảnh.

**“Singleton bean tự thread-safe.”**  
Không. Nhiều thread có thể dùng cùng instance; mutable state phải được thiết kế an toàn.

**“Có @Transactional trên class là mọi lời gọi sẽ có transaction.”**  
Không. Transaction infrastructure và cách lời gọi đi qua proxy/aspect đều quan trọng.

**“Muốn unit test một @Service phải chạy Spring Boot.”**  
Không. Constructor injection cho phép tạo service với fake dependency và kiểm thử logic bằng Java thuần. Chỉ cần Spring context khi muốn kiểm chứng wiring hoặc behavior do Spring cung cấp.

**“DTO được Spring MVC tạo nên chắc chắn là bean singleton.”**  
Không. Data binding/serialization tạo object phục vụ request hoặc response; nó khác với đăng ký bean trong ApplicationContext.

**“Một object được bean gọi tới thì bản thân nó tự trở thành bean.”**  
Không. Một bean có thể dùng nhiều object Java thường. Chỉ object được container đăng ký/quản lý theo cơ chế bean mới có hợp đồng bean tương ứng.

**“Đã có bean trên context thì không bao giờ cần factory hoặc new nữa.”**  
Không. Application code vẫn tạo value object, entity, DTO hoặc đối tượng tạm. Factory và các scope giúp chọn ranh giới phù hợp giữa quản lý bởi Spring và tạo theo nhu cầu.

## Kết luận: phân biệt bằng quyền sở hữu, không bằng từ khóa

Hãy nhớ ba ý:

1. **new là thao tác tạo instance của Java**; nó không tự động đăng ký instance vào Spring ApplicationContext.
2. **Spring bean là một object được container quản lý**; object này vẫn có thể được tạo bằng constructor hoặc một factory method có new bên trong.
3. **Hành vi DI, lifecycle, scope và nhiều tính năng AOP** phụ thuộc việc object nằm trong cơ chế quản lý phù hợp và cách nó được sử dụng, chứ không chỉ phụ thuộc annotation xuất hiện trên source code.

Trong Spring Boot, nên để container quản lý các thành phần ứng dụng cần dependency và tích hợp framework, đồng thời tiếp tục tạo object Java thông thường cho dữ liệu và công việc ngắn hạn. Khi phân biệt rõ hai loại reference này, bạn sẽ dễ hiểu vì sao một field không được inject, vì sao callback lifecycle không chạy, vì sao transaction không kích hoạt, và vì sao cùng một class lại có nhiều instance với trạng thái khác nhau.
