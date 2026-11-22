# BeanDefinition, đối tượng bean thực tế và proxy của bean

Trong Spring Boot, một lớp có `@Service` không lập tức trở thành một đối tượng đang hoạt động. Spring trước hết **ghi nhận cách tạo và quản lý đối tượng**, sau đó mới **tạo bean**, và trong một số tình huống còn **đưa một proxy ra cho các bean khác sử dụng**. Ba thứ này liên quan chặt chẽ nhưng không đồng nhất:

- **`BeanDefinition`**: bản mô tả hoặc “công thức” để Spring quản lý một bean.
- **Bean instance (đối tượng bean thực tế)**: đối tượng được tạo hoặc cung cấp theo định nghĩa, thuộc quyền quản lý của IoC container.
- **Bean proxy**: đối tượng trung gian có thể được Spring đưa ra thay cho việc truy cập trực tiếp đối tượng đích, nhằm bổ sung hành vi như transaction, cache, security hoặc xử lý scope.

Hiểu rõ sự khác nhau giúp bạn giải thích vì sao Spring có thể inject một interface mà không cần tự gọi `new`, vì sao `@Transactional` đôi lúc không hoạt động, và vì sao `getBean(...).getClass()` đôi khi trả về một lớp có tên lạ.

## 1. Bức tranh tổng thể trong IoC container

Spring IoC container có nhiệm vụ đăng ký cấu hình bean, giải quyết dependency, tạo đối tượng, quản lý lifecycle và cung cấp bean cho phần còn lại của ứng dụng.

Một luồng đơn giản:

```text
Mã nguồn / cấu hình ứng dụng
  @Component, @Service, @Configuration, @Bean, ...
                    |
                    v
     Đọc metadata và đăng ký BeanDefinition
                    |
                    v
            BeanFactory / registry
                    |
          cần tạo bean theo scope
                    |
                    v
       Khởi tạo đối tượng và inject dependency
                    |
                    v
        Chạy các bước khởi tạo / post-processing
                    |
                    +-----------------------------+
                    |                             |
                    v                             v
            Bean thông thường          Có thể tạo proxy bọc target
                    |                             |
                    +--------------+--------------+
                                   |
                                   v
                    Đối tượng được container cung cấp
                                   |
                                   v
                         Bean khác sử dụng qua DI
```

Sơ đồ mang tính khái niệm. Trên thực tế, việc tạo bean có thể có nhiều bước hơn; Spring còn có nhiều loại bean và cơ chế đăng ký khác nhau. Đặc biệt, **không phải bean nào cũng có proxy**.

### 1.1. Hai vai trò quan trọng: `BeanFactory` và `ApplicationContext`

`BeanFactory` là giao diện cốt lõi cho việc lấy bean và quản lý các khả năng cơ bản của IoC container. `ApplicationContext` mở rộng khả năng đó với cơ chế đọc cấu hình, sự kiện, tài nguyên, tích hợp môi trường và nhiều tiện ích khác.

Ứng dụng Spring Boot thường lấy một `ApplicationContext` khi gọi:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);
```

Bạn có thể lấy bean theo tên hoặc kiểu:

```java
PaymentService service = context.getBean(PaymentService.class);
```

Lời gọi `getBean` lấy **đối tượng mà container công khai để sử dụng**. Nếu có AOP proxy, kết quả có thể là proxy chứ không phải instance của lớp triển khai nguyên bản.

## 2. `BeanDefinition` là gì?

`BeanDefinition` là một đối tượng metadata bên trong Spring, mô tả cách tạo và cấu hình một bean. Nó không phải instance của `PaymentService`, `OrderService` hoặc một lớp nghiệp vụ bất kỳ.

Một bean definition có thể cung cấp thông tin như:

| Thuộc tính/metadata | Ý nghĩa |
| --- | --- |
| Bean name | Tên định danh được đăng ký trong container |
| Bean class hoặc factory method | Loại đối tượng dự kiến hoặc cách gọi factory để tạo đối tượng |
| Scope | Chẳng hạn `singleton`, `prototype`, `request`, `session` |
| Lazy initialization | Có trì hoãn khởi tạo đến lúc cần hay không |
| Constructor arguments / property values | Thông tin cấu hình hoặc dependency cần cấp khi tạo |
| Init / destroy methods | Callback khởi tạo và hủy được cấu hình |
| Primary / qualifiers / autowire candidate | Metadata hỗ trợ chọn bean phù hợp khi inject |
| Role và thông tin nguồn | Phân biệt bean ứng dụng, bean hạ tầng và nguồn định nghĩa |

Không phải mọi `BeanDefinition` đều có đầy đủ tất cả các thuộc tính trên. Ví dụ, một bean được tạo từ phương thức `@Bean` có thể tham chiếu **factory bean và factory method**, thay vì chỉ có một lớp để gọi constructor trực tiếp.

### 2.1. `BeanDefinition` đến từ đâu?

Spring có nhiều cách đăng ký bean definition:

**Qua component scanning:**

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long calculate(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

Khi component scan quét package này, nó có thể đăng ký một bean definition với tên mặc định `priceService`.

**Qua phương thức `@Bean`:**

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    public TaxPolicy taxPolicy() {
        return new TaxPolicy(0.10);
    }
}
```

Ở đây, Spring đăng ký bean definition cho kết quả của `taxPolicy()`. `TaxPolicy` không nhất thiết phải mang `@Component`; Spring biết cách tạo bean từ phương thức `@Bean`.

**Các nguồn khác:** khai báo XML, `@Import`, đăng ký thủ công qua registry, auto-configuration của Spring Boot, và cơ chế tích hợp của những framework khác.

Vì vậy, câu nói “bean chỉ tồn tại nếu lớp có `@Component`” là không chính xác.

### 2.2. Bean name khác Java class name

Với `@Service` không khai báo tên, Spring thường đặt tên từ tên lớp bằng quy ước:

```java
@Service
public class PaymentService {
}
```

Bean name thường là `paymentService`. Bạn có thể khai báo tên cụ thể:

```java
@Service("onlinePaymentService")
public class PaymentService {
}
```

Với `@Bean`, tên mặc định thường là tên phương thức:

```java
@Bean
public Clock appClock() {
    return Clock.systemUTC();
}
```

Bean name mặc định là `appClock`, mặc dù kiểu trả về là `Clock`. Bean name hữu ích để lấy bean theo tên, đặt qualifier hoặc chẩn đoán cấu hình; tên bean không nhất thiết giống tên class hay object mà nó đại diện.

### 2.3. Khi nào có `BeanDefinition` nhưng chưa có instance?

Ví dụ một bean `@Lazy`:

```java
@Service
@Lazy
public class ReportGenerator {

    public ReportGenerator() {
        System.out.println("ReportGenerator được tạo");
    }
}
```

Spring vẫn có thể đăng ký bean definition của `reportGenerator` khi khởi động, nhưng việc tạo instance được trì hoãn đến thời điểm bean thực sự cần được lấy hoặc phụ thuộc vào điều kiện sử dụng. Nếu một bean khác phụ thuộc trực tiếp vào `ReportGenerator` và bean đó được tạo sớm, `ReportGenerator` vẫn có thể được khởi tạo trong quá trình giải quyết dependency.

Điều này cho thấy **đăng ký định nghĩa** và **khởi tạo đối tượng** là hai bước khác nhau.

## 3. Đối tượng bean thực tế được tạo như thế nào?

Với bean thông thường, Spring sử dụng metadata trong bean definition để chọn constructor hoặc factory method, giải quyết dependency và tạo đối tượng.

Ví dụ:

```java
package com.example.shop;

import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
class InventoryClient {
    public boolean available(String sku) {
        return true;
    }
}

@Service
class OrderService {
    private final InventoryClient inventoryClient;

    OrderService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public boolean canOrder(String sku) {
        return inventoryClient.available(sku);
    }
}
```

Khi Spring tạo `orderService`, container resolve tham số constructor có kiểu `InventoryClient`, tìm bean phù hợp và đưa bean đó vào constructor. Bạn không cần tự viết:

```java
new OrderService(new InventoryClient());
```

Đây là **dependency injection**: việc cung cấp dependency được chuyển cho IoC container. Nếu có nhiều bean phù hợp hoặc không có bean nào, Spring cần thêm thông tin như `@Qualifier`, `@Primary` hoặc cấu hình bean thích hợp; nếu không, quá trình tạo bean có thể thất bại.

### 3.1. Một vòng đời bean đơn giản

Đối với một bean singleton thông thường, các giai đoạn chính có thể được hình dung như sau:

```text
1. Đăng ký BeanDefinition
           |
2. Quyết định cần tạo bean
           |
3. Chọn constructor / factory method, tạo target instance
           |
4. Cấp dependency và property
           |
5. Chạy callback và BeanPostProcessor trước khởi tạo
           |
6. Khởi tạo: ví dụ @PostConstruct / InitializingBean
           |
7. Chạy BeanPostProcessor sau khởi tạo
           |              \
           |               \-- có thể trả về proxy
           v
8. Công khai bean để các thành phần khác sử dụng
           |
9. Hủy bean theo lifecycle thích hợp khi context đóng
```

Thứ tự trên được giản lược để dễ học. Các phương thức callback khác nhau có thứ tự chi tiết riêng, một số cơ chế proxy có thể tham gia ở thời điểm khác trong lifecycle, và circular dependency có thể khiến quá trình phức tạp hơn.

### 3.2. Phân biệt object tạo bằng `new` với Spring bean

Giả sử có:

```java
@Service
public class ReceiptService {
    public String createReceipt() {
        return "Receipt created";
    }
}
```

Hai lệnh dưới đây không nhất thiết tạo cùng loại đối tượng về mặt quản lý:

```java
ReceiptService managed = context.getBean(ReceiptService.class);
ReceiptService manual = new ReceiptService();
```

`managed` do container cung cấp, có thể đã được inject dependency, chạy lifecycle callback và được bọc bằng proxy. `manual` là object Java do bạn tạo bằng `new` nên Spring **không mặc nhiên** quản lý nó. Các cơ chế như `@Transactional`, `@Async` hoặc injection do Spring thực hiện không tự áp dụng cho object được tạo thủ công.

Một instance của lớp Java **không tự động là Spring bean chỉ vì lớp được gắn `@Service`**.

## 4. Scope ảnh hưởng số lượng bean instance

Bean definition chứa thông tin scope. Cùng một định nghĩa nhưng số lượng hoặc thời điểm tạo instance có thể khác.

| Scope | Hành vi điển hình |
| --- | --- |
| `singleton` | Một bean instance được container quản lý cho mỗi bean definition trong một IoC container (mặc định) |
| `prototype` | Tạo một instance mới khi yêu cầu bean theo scope này |
| `request` | Một instance ứng với một HTTP request, khi có web context phù hợp |
| `session` | Một instance ứng với một HTTP session, khi có web context phù hợp |
| `application` | Scope gắn với servlet application context |

“Singleton trong Spring” là phạm vi **theo container và bean definition**, không có nghĩa toàn bộ JVM chỉ được phép tồn tại một object của class đó. Bạn có thể có nhiều `ApplicationContext`, hai bean definition cùng kiểu, hoặc object tạo bằng `new`.

### 4.1. Ví dụ singleton

```java
@Component
public class IdGenerator {
}
```

Nếu đang dùng scope mặc định:

```java
IdGenerator a = context.getBean(IdGenerator.class);
IdGenerator b = context.getBean(IdGenerator.class);

System.out.println(a == b); // thường true
```

Cùng một bean singleton thông thường, `getBean` trả về cùng tham chiếu mà container quản lý. Nếu bean đó được bọc bằng singleton proxy thì hai lần lấy bean cũng có thể cùng trả về **proxy**, không phải reference tới target thô.

### 4.2. Ví dụ prototype

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
```

Khi gọi:

```java
JobContext first = context.getBean(JobContext.class);
JobContext second = context.getBean(JobContext.class);

System.out.println(first == second); // false, với định nghĩa prototype này
```

Cần import `org.springframework.context.annotation.Scope` và `org.springframework.beans.factory.config.ConfigurableBeanFactory`. Một lưu ý thực tế: nếu inject trực tiếp prototype vào constructor của singleton, prototype thông thường được resolve **một lần khi singleton được tạo**. Muốn lấy một prototype mới mỗi lần sử dụng có thể dùng `ObjectProvider<T>`, `Provider<T>` hoặc thiết kế cơ chế lookup phù hợp.

### 4.3. Scope và lifecycle hủy

Container quản lý lifecycle đầy đủ cho singleton thông thường. Với prototype, Spring tạo và cung cấp bean nhưng thường **không tự gọi toàn bộ callback hủy** khi context đóng; phía sử dụng cần quản lý tài nguyên của prototype nếu cần. Các scope web có lifecycle theo request/session và yêu cầu ngữ cảnh web thích hợp.

## 5. Proxy của bean là gì?

**Proxy** là một đối tượng đứng giữa phía gọi và đối tượng đích (**target**). Phía gọi tương tác với proxy; proxy có thể thêm logic trước, sau hoặc xung quanh lời gọi rồi chuyển tiếp đến target.

```text
Controller / Service khác
          |
          | gọi placeOrder()
          v
    +---------------+
    |  Bean proxy   |
    |---------------|
    | Kiểm tra      |
    | Mở transaction|
    | Ghi log / ... |
    +---------------+
          |
          | chuyển tiếp lời gọi
          v
    +---------------+
    |  Target bean  |
    |---------------|
    | placeOrder()  |
    | logic nghiệp vụ|
    +---------------+
          |
          v
       Kết quả
```

Với Spring AOP, proxy có thể áp dụng một chuỗi interceptor/advice thay vì chỉ một bước. Ví dụ:

```text
Client
   ↓
Proxy
   ├── Security interceptor
   ├── Transaction interceptor
   ├── Metrics interceptor
   ↓
Target.placeOrder()
   ↓
Trả kết quả / ném exception
   ↓
Các interceptor hoàn tất logic tương ứng
   ↓
Client
```

Thứ tự advice thực tế phụ thuộc cấu hình và thứ tự áp dụng interceptor. Sơ đồ chỉ minh họa khả năng nhiều hành vi cùng tham gia một lời gọi.

### 5.1. Proxy giải quyết vấn đề gì?

Không dùng proxy, nếu muốn mọi phương thức nghiệp vụ đều ghi log hoặc mở transaction, bạn có thể phải lặp code:

```java
public void placeOrder() {
    beginTransaction();
    try {
        // Logic nghiệp vụ
        commitTransaction();
    } catch (RuntimeException ex) {
        rollbackTransaction();
        throw ex;
    }
}
```

Khi sử dụng Spring declarative transaction đúng điều kiện, bạn có thể biểu đạt ý định:

```java
@Transactional
public void placeOrder() {
    // Logic nghiệp vụ
}
```

Logic transaction được triển khai bởi hạ tầng Spring Transaction qua interceptor và transaction manager, thay vì được viết lặp trong từng phương thức. Annotation là **metadata**; proxy và những thành phần hạ tầng mới thực hiện hành vi khi có lời gọi phù hợp.

Những tính năng thường liên quan đến proxy:

- `@Transactional`: can thiệp vào giao dịch khi transaction management được cấu hình phù hợp.
- `@Cacheable`: tra cứu/cập nhật cache khi caching được bật và có `CacheManager`.
- `@Async`: chuyển việc thực thi sang executor khi async support được bật.
- Method-level security: kiểm tra phân quyền khi method security được cấu hình.
- Spring AOP custom aspect: thêm logging, tracing, metrics hoặc logic cắt ngang.
- Scoped proxy: giữ một tham chiếu ổn định nhưng phân giải target theo request/session hoặc scope khác.

**Không phải cứ thấy annotation là sẽ có proxy.** Bạn cần đúng dependency, hạ tầng được bật, điều kiện áp dụng và đường gọi phương thức phù hợp. Cũng có những proxy phục vụ mục đích khác ngoài Spring AOP.

### 5.2. Proxy khác target như thế nào?

| Thành phần | Chức năng | Có thể nhìn thấy khi `getBean`? |
| --- | --- | --- |
| `BeanDefinition` | Mô tả cách đăng ký/tạo bean | Không, `getBean` không trả về bean definition |
| Target object | Chứa state và logic nghiệp vụ được gọi | Có nếu không cần proxy; khi có proxy thường được proxy sử dụng bên trong |
| Proxy object | Trung gian áp dụng advice, scope hoặc hành vi khác | Có, khi Spring công khai proxy như bean |

Trong trường hợp có AOP proxy, đối tượng thường được inject chính là **proxy**. Vì thế, dùng `getBean("orderService")` hoặc injection có thể trả về một kiểu runtime khác kiểu lớp mà bạn viết trong mã nguồn.

## 6. Hai loại Spring AOP proxy thường gặp

Spring AOP thường sử dụng proxy dựa trên **JDK dynamic proxy** hoặc **CGLIB subclass proxy**.

### 6.1. JDK dynamic proxy

JDK dynamic proxy triển khai một hoặc nhiều interface. Ví dụ:

```java
public interface PaymentOperations {
    void pay(long amount);
}

@Service
public class CardPaymentService implements PaymentOperations {
    @Override
    public void pay(long amount) {
        System.out.println("Paid: " + amount);
    }
}
```

Khi Spring cấu hình dùng JDK proxy cho bean này, đối tượng công khai sẽ **implement `PaymentOperations`**, nhưng không nhất thiết là instance của `CardPaymentService`:

```java
PaymentOperations payment = context.getBean(PaymentOperations.class);
```

Inject theo interface thường là lựa chọn ổn định trong tình huống này. Nếu cố inject `CardPaymentService` trong khi bean chỉ được công khai bằng JDK dynamic proxy, bạn có thể gặp vấn đề khớp kiểu.

### 6.2. CGLIB subclass proxy

CGLIB proxy tạo một lớp con của class đích để chặn các lời gọi phương thức có thể override. Runtime class có thể có tên tương tự:

```text
com.example.shop.CardPaymentService$$SpringCGLIB$$...
```

Vì proxy là subclass, một số phép kiểm tra `instanceof CardPaymentService` có thể đúng. Nhưng không phải phương thức nào cũng có thể được override: **private** và **final methods** không được chặn theo cơ chế override, và một **final class** không thể tạo subclass proxy.

### 6.3. So sánh

| Khía cạnh | JDK dynamic proxy | CGLIB subclass proxy |
| --- | --- | --- |
| Cơ sở tạo proxy | Triển khai interface | Kế thừa class đích |
| Yêu cầu interface | Cần interface để công khai tương tác | Không bắt buộc có interface |
| Kiểu công khai điển hình | Interface | Class đích hoặc các kiểu cha phù hợp |
| Giới hạn thường gặp | Chỉ can thiệp lời gọi qua phương thức công khai qua interface proxy | Không thể override final/private method; không subclass final class |
| Tên runtime | Dạng JDK proxy như `jdk.proxy...` | Dạng `...$$SpringCGLIB$$...` |

Trong nhiều ứng dụng Spring Boot dùng AOP, proxy theo class được lựa chọn mặc định khi cấu hình thích hợp; giá trị mặc định và cách tùy chỉnh có thể khác theo phiên bản và tính năng. Khi cần xác định loại proxy của **ứng dụng đang chạy**, nên kiểm tra trực tiếp thay vì đoán từ tên annotation.

Có thể điều chỉnh cách Spring Boot tạo Spring AOP proxy qua property trong những cấu hình tương ứng:

```properties
# Ưu tiên proxy dựa trên interface khi có thể
spring.aop.proxy-target-class=false
```

Hoặc:

```properties
# Sử dụng proxy dựa trên class
spring.aop.proxy-target-class=true
```

Lựa chọn này liên quan đến hệ thống Spring AOP auto-configuration, không có nghĩa mọi loại proxy trong hệ sinh thái Spring đều được điều khiển bởi đúng property đó.

## 7. Ví dụ quan sát `BeanDefinition`, bean và AOP proxy

Ví dụ sau sử dụng ứng dụng Spring Boot với **Spring AOP** để nhìn thấy sự khác biệt. Giả định dự án dùng Java phù hợp và dependency AOP tương ứng phiên bản Spring Boot. Trong dự án Spring Boot 3.x, dependency thường dùng là:

**Gradle (Groovy DSL):**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Nếu dự án thuộc dòng Spring Boot mới có thay đổi cách tổ chức starter, hãy chọn starter AOP được hỗ trợ trong phiên bản đang dùng. Các đoạn trên giả định dự án đã quản lý phiên bản dependency theo cấu hình Spring Boot.

### 7.1. Tạo interface và service

`src/main/java/com/example/demo/service/GreetingService.java`:

```java
package com.example.demo.service;

public interface GreetingService {
    String greet(String name);
}
```

`src/main/java/com/example/demo/service/DefaultGreetingService.java`:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class DefaultGreetingService implements GreetingService {

    public DefaultGreetingService() {
        System.out.println("Constructing DefaultGreetingService");
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Lớp được component scan nhận diện vì có `@Service` và nằm trong package con của package ứng dụng. Tên bean mặc định thường là `defaultGreetingService`.

### 7.2. Tạo aspect để Spring áp dụng advice

`src/main/java/com/example/demo/aop/TraceAspect.java`:

```java
package com.example.demo.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {

    @Around("execution(* com.example.demo.service..*.greet(..))")
    public Object trace(ProceedingJoinPoint point) throws Throwable {
        System.out.println("Before: " + point.getSignature().getName());
        try {
            return point.proceed();
        } finally {
            System.out.println("After: " + point.getSignature().getName());
        }
    }
}
```

Aspect định nghĩa advice bao quanh phương thức `greet` của các class trong package service được chỉ định. Spring AOP có thể tạo proxy tương ứng cho bean có phương thức khớp pointcut. `point.proceed()` cho lời gọi đi tiếp đến target; `finally` bảo đảm đoạn logging phía sau chạy cả khi target ném exception.

### 7.3. Đọc định nghĩa và đối tượng mà container trả về

`src/main/java/com/example/demo/ProxyDemoApplication.java`:

```java
package com.example.demo;

import com.example.demo.service.GreetingService;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ProxyDemoApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ProxyDemoApplication.class, args);

        ConfigurableListableBeanFactory factory =
                context.getBeanFactory();

        BeanDefinition definition =
                factory.getBeanDefinition("defaultGreetingService");

        Object exposedBean = context.getBean("defaultGreetingService");
        GreetingService service = context.getBean(GreetingService.class);

        System.out.println("Bean name: defaultGreetingService");
        System.out.println("Definition class: " +
                definition.getBeanClassName());
        System.out.println("Definition scope: " +
                definition.getScope());
        System.out.println("Exposed class: " +
                exposedBean.getClass().getName());
        System.out.println("AOP proxy: " +
                AopUtils.isAopProxy(exposedBean));
        System.out.println("Same reference: " +
                (exposedBean == service));
        System.out.println(service.greet("Mai"));
    }
}
```

Đây là ví dụ minh họa cho ứng dụng console hoặc web chạy từ lớp main. Nếu chạy dưới chế độ console, tiến trình có thể kết thúc sau khi `main` hoàn tất; nếu có embedded web server, context thường tiếp tục hoạt động đến khi dừng ứng dụng.

Kết quả minh họa:

```text
Constructing DefaultGreetingService
...
Bean name: defaultGreetingService
Definition class: com.example.demo.service.DefaultGreetingService
Definition scope:
Exposed class: com.example.demo.service.DefaultGreetingService$$SpringCGLIB$$...
AOP proxy: true
Same reference: true
Before: greet
After: greet
Hello, Mai
```

Đầu ra thực tế và thứ tự các log khởi động thay đổi theo môi trường. Nếu dùng JDK dynamic proxy, `Exposed class` sẽ có dạng tên JDK proxy. Ở một bean definition có scope mặc định, `definition.getScope()` có thể là chuỗi rỗng (`""`), vì **scope không được ghi tường minh**; nó vẫn được hiểu là singleton theo mặc định.

Chú ý những kết quả quan trọng:

1. `getBeanDefinition(...)` trả về **metadata**, gồm class gốc và các thiết lập cấu hình.
2. `context.getBean(...)` trả về **bean công khai**; trong ví dụ có AOP, nó có thể là proxy.
3. `AopUtils.isAopProxy(...)` kiểm tra đối tượng có phải một Spring AOP proxy hay không.
4. Hai cách lấy cùng bean singleton thường trả về **cùng tham chiếu proxy**.
5. Lời gọi `service.greet(...)` đi qua advice rồi mới thực thi phần nghiệp vụ.

Nếu loại bỏ aspect hoặc dependency/hạ tầng AOP thích hợp, bean có thể được công khai trực tiếp và `AopUtils.isAopProxy(...)` sẽ là `false`.

### 7.4. Kiểm tra loại proxy cụ thể

Bạn có thể mở rộng đoạn kiểm tra:

```java
System.out.println(
    "JDK proxy: " + AopUtils.isJdkDynamicProxy(exposedBean)
);
System.out.println(
    "CGLIB proxy: " + AopUtils.isCglibProxy(exposedBean)
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(exposedBean).getName()
);
```

Trong tình huống JDK proxy:

```java
System.out.println(exposedBean instanceof GreetingService);
// true

System.out.println(exposedBean instanceof DefaultGreetingService);
// có thể false khi proxy chỉ triển khai interface
```

Trong tình huống CGLIB subclass proxy, phép kiểm tra `instanceof DefaultGreetingService` thường đúng vì proxy kế thừa class đích. Không nên dùng `getClass() == DefaultGreetingService.class` để kết luận một bean có đúng chức năng hay không, bởi proxy có thể mang runtime class khác.

## 8. Vì sao proxy làm thay đổi đường đi của lời gọi?

Giả sử có một bean:

```java
@Service
public class CheckoutService {

    @Transactional
    public void checkout() {
        // Ghi nhiều bản ghi trong cùng transaction
    }

    public void placeOrder() {
        checkout();
    }
}
```

Trong mô hình Spring transaction sử dụng **proxy**, có hai đường đi khác nhau:

**Gọi từ một bean khác qua Spring proxy:**

```text
OtherBean -> CheckoutService proxy
          -> TransactionInterceptor
          -> CheckoutService target.checkout()
```

Khi transaction infrastructure và `PlatformTransactionManager` được cấu hình phù hợp, Spring có thể áp dụng transaction cho lời gọi đó.

**Một phương thức trong cùng target gọi phương thức khác qua `this`:**

```text
OtherBean -> CheckoutService proxy
          -> CheckoutService target.placeOrder()
                                  |
                                  v
                             this.checkout()
                                  |
                                  v
                           logic checkout()
```

Lời gọi nội bộ `this.checkout()` **không đi ngược qua proxy**, nên transaction advice gắn riêng cho `checkout()` thường không được kích hoạt bởi lời gọi nội bộ này. Nếu `placeOrder()` đã đi qua một advice transaction thích hợp thì transaction của phương thức ngoài vẫn có thể bao phủ công việc bên trong; không nên suy ra rằng mọi lời gọi nội bộ đều “không có transaction” trong mọi tình huống.

### 8.1. Giải pháp thường dùng cho self-invocation

Tách thao tác yêu cầu advice sang một Spring bean khác rồi inject bean đó:

```java
@Service
public class PaymentWriter {

    @Transactional
    public void savePayment() {
        // Ghi dữ liệu thanh toán
    }
}

@Service
public class CheckoutFacade {
    private final PaymentWriter paymentWriter;

    public CheckoutFacade(PaymentWriter paymentWriter) {
        this.paymentWriter = paymentWriter;
    }

    public void checkout() {
        paymentWriter.savePayment(); // Gọi qua tham chiếu bean được inject
    }
}
```

Khi transaction proxy đã được áp dụng cho `PaymentWriter`, việc gọi từ `CheckoutFacade` đi qua bean được inject và có thể kích hoạt interceptor như dự kiến.

Ngoài việc tách bean, có những cơ chế AOP khác như AspectJ weaving xử lý lời gọi nội bộ theo cách khác; tuy nhiên đây là mô hình ngoài phạm vi proxy-based Spring AOP cơ bản. Tránh biến việc tự gọi `this` thành giải pháp “nhờ Spring tự intercept” vì không đúng cơ chế proxy.

### 8.2. `private`, `final` và constructor

Proxy-based AOP chủ yếu chặn **method invocation đi qua proxy**. Constructor không phải là một lời gọi phương thức nghiệp vụ được AOP proxy intercept theo cách đó. Với class-based proxy, phương thức `private` và `final` không thể được override nên không thể được chặn bằng cơ chế override.

Trong code nghiệp vụ cần advice, lựa chọn dễ hiểu là đặt annotation trên phương thức công khai của một Spring bean và gọi nó từ bean khác qua dependency injection.

## 9. Scoped proxy: một proxy, nhiều target theo request

Proxy không chỉ phục vụ transaction. Nó còn giúp đưa một dependency ngắn hạn vào bean có thời gian sống dài hơn.

Giả sử một ứng dụng web có service singleton cần thông tin của **HTTP request hiện tại**:

```java
package com.example.shop.web;

import java.util.UUID;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestTrace {

    private final String traceId = UUID.randomUUID().toString();

    public String traceId() {
        return traceId;
    }
}
```

Một service singleton sử dụng:

```java
@Service
public class TraceService {
    private final RequestTrace requestTrace;

    public TraceService(RequestTrace requestTrace) {
        this.requestTrace = requestTrace;
    }

    public String currentTraceId() {
        return requestTrace.traceId();
    }
}
```

Nếu inject trực tiếp request-scoped target thực tế vào singleton, thời điểm tạo và scope không tương thích. Với **scoped proxy**, Spring đưa một đối tượng trung gian có thể inject an toàn vào singleton; khi `currentTraceId()` được gọi trong HTTP request, proxy tìm target tương ứng với request đang xử lý.

```text
TraceService (singleton)
          |
          v
RequestTrace scoped proxy (tham chiếu được giữ lại)
          |
          +--- HTTP request A ---> RequestTrace target A
          |
          +--- HTTP request B ---> RequestTrace target B
```

Giữa hai request khác nhau, `traceId` có thể khác nhau vì target khác nhau. Trong cùng request, các lời gọi đến request-scoped bean thường truy cập cùng một target của request đó.

**Lưu ý:** nếu cố gọi method cần target request-scoped bên ngoài một HTTP request có scope đang active, Spring có thể ném exception báo scope không hoạt động. Scoped proxy không tự tạo ra HTTP request.

### 9.1. Một bean name có thể đi kèm nhiều bean definition nội bộ

Khi sử dụng scoped proxy, Spring có thể đăng ký một bean definition cho proxy với tên public và một bean definition khác cho target bên dưới, thường theo quy ước tên nội bộ như `scopedTarget.requestTrace`.

Điều này minh họa lý do không nên áp dụng công thức “mỗi class chỉ có đúng một bean definition hoặc một object”. Bean definition, exposed bean và target object phục vụ những nhiệm vụ riêng; mô hình thực tế tùy loại bean và cấu hình.

## 10. Ai tạo proxy? `BeanPostProcessor` và các thành phần hạ tầng

Một `BeanPostProcessor` có thể được Spring gọi trong quá trình khởi tạo bean, trước và sau callback initialization. Nó có thể giữ nguyên bean hoặc trả về một object khác, ví dụ proxy.

Ở mức khái niệm:

```java
public interface BeanPostProcessor {
    Object postProcessBeforeInitialization(Object bean, String beanName);
    Object postProcessAfterInitialization(Object bean, String beanName);
}
```

Đoạn trên chỉ minh họa chữ ký API cốt lõi; phiên bản Spring hiện đại có các phương thức mặc định và cơ chế hỗ trợ bổ sung. Spring AOP dùng những bộ xử lý hạ tầng như auto-proxy creators để quyết định bean nào cần bọc proxy. Không phải mọi `BeanPostProcessor` đều tạo proxy.

**Phân biệt hai cấp xử lý:**

| Thành phần | Làm việc chủ yếu với | Thời điểm/vai trò |
| --- | --- | --- |
| `BeanFactoryPostProcessor` | Metadata bean definitions | Chỉnh hoặc bổ sung cấu hình của definition trước khi những bean thông thường được tạo |
| `BeanDefinitionRegistryPostProcessor` | Registry của bean definitions | Có thể bổ sung hoặc sửa các định nghĩa ở giai đoạn đăng ký |
| `BeanPostProcessor` | Bean instances | Can thiệp quá trình khởi tạo bean; có thể tạo proxy hoặc xử lý annotation |
| Auto-proxy creator | Những bean cần advice | Phát hiện advisor và có thể tạo AOP proxy |

Đây là sự khác biệt quan trọng: `BeanFactoryPostProcessor` không nên được hiểu là “thay đổi một object đã tạo”, vì nó chủ yếu thao tác trên metadata. `BeanPostProcessor` có thể làm việc với bean instance và là một mắt xích phổ biến trong cơ chế tạo proxy.

### 10.1. Tại sao `@PostConstruct` không chứng minh bean không có proxy?

Một phương thức `@PostConstruct` thường được thực thi trên target trong quá trình khởi tạo trước khi proxy AOP được công khai hoàn chỉnh. Do đó, nếu bạn ghi:

```java
@PostConstruct
public void init() {
    System.out.println("Runtime class: " + getClass().getName());
}
```

bạn có thể thấy tên class gốc, trong khi `context.getBean(...).getClass()` về sau lại là tên proxy. Đây không nhất thiết là mâu thuẫn: hai đoạn code đang quan sát object ở những điểm khác nhau trong lifecycle.

### 10.2. `@Configuration` cũng có thể được tăng cường bằng proxy

Trong một số chế độ, Spring tăng cường lớp `@Configuration` bằng subclass để bảo đảm lời gọi giữa các phương thức `@Bean` được container quản lý nhất quán. Cơ chế này liên quan đến xử lý configuration class và `proxyBeanMethods`, **khác về mục đích** với proxy AOP chạy transaction hoặc cache.

Do đó, nhìn thấy tên class chứa `$$SpringCGLIB$$` chưa đủ để kết luận bean đang có transaction advice. Khi chẩn đoán Spring AOP, nên dùng API như `AopUtils.isAopProxy` và xem cấu hình thực tế.

## 11. Một điểm nâng cao: `FactoryBean` khác `BeanDefinition`

Spring có interface `FactoryBean<T>` cho những bean có nhiệm vụ **tạo một object khác** theo hợp đồng của container. Không nên nhầm:

- `BeanDefinition` là metadata mô tả cách container tạo/quản lý bean.
- `@Bean` là annotation trên factory method.
- `FactoryBean<T>` là interface Spring cho một **factory bean** chuyên biệt.
- `BeanFactory` là hạ tầng lấy và quản lý bean.

Với một `FactoryBean` được đăng ký dưới tên `reportClient`, theo quy ước Spring:

```java
Object product = context.getBean("reportClient");
Object factory = context.getBean("&reportClient");
```

Lời gọi tên thông thường có thể trả về **sản phẩm của `FactoryBean`**, còn tiền tố `&` lấy **factory object**. Đây là ví dụ khác cho thấy `getBean(name)` không phải lúc nào cũng trả về instance của lớp được mô tả trực tiếp trong metadata đăng ký ban đầu.

Cơ chế `FactoryBean` khác với AOP proxy; một object do factory tạo ra vẫn có thể tham gia những cơ chế Spring khác tùy cách cấu hình.

## 12. Những lỗi và câu hỏi thường gặp

### 12.1. “Có `BeanDefinition`, sao `getBean` vẫn lỗi?”

Một bean definition chỉ ghi nhận khả năng tạo bean. Khi tạo instance, Spring còn phải giải quyết constructor, dependency, property, callback và những điều kiện runtime. Nếu thiếu dependency, constructor ném exception hoặc có vòng phụ thuộc không giải quyết được, `getBean` có thể thất bại.

Ví dụ:

```text
BeanCreationException
  caused by UnsatisfiedDependencyException
    caused by NoSuchBeanDefinitionException
```

Hãy đọc phần `Caused by` sâu nhất và xác định dependency nào không được đăng ký hoặc cấu hình.

### 12.2. “Vì sao `@Autowired ConcreteService` lỗi nhưng inject interface lại được?”

Nếu bean đã được thay bằng **JDK dynamic proxy**, đối tượng công khai chỉ đảm bảo implement interface được proxy. Inject lớp triển khai cụ thể có thể thất bại vì proxy không phải instance của class đó.

```java
public interface Sender {
    void send(String message);
}

@Service
class EmailSender implements Sender {
    public void send(String message) {
        System.out.println(message);
    }
}
```

Thiết kế client theo interface thường dễ dùng:

```java
@Service
class NotificationService {
    private final Sender sender;

    NotificationService(Sender sender) {
        this.sender = sender;
    }
}
```

Nếu có nhiều implementation của `Sender`, cần thêm `@Qualifier`, `@Primary` hoặc cách chọn bean tương đương.

### 12.3. “Vì sao `getClass()` khác class trong source?”

Có thể đó là JDK dynamic proxy hoặc CGLIB subclass proxy. Xem `AopUtils.isAopProxy`, `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy` và `AopUtils.getTargetClass`. Tránh ép kiểu về concrete class khi không chắc loại proxy được dùng.

### 12.4. “Tại sao annotation `@Transactional` không hoạt động?”

Kiểm tra lần lượt:

1. Object được gọi có thực sự là Spring bean không, hay được tạo bằng `new`?
2. Transaction management và transaction manager đã được cấu hình cho tài nguyên phù hợp chưa?
3. Phương thức có được gọi **qua proxy** không, hay là self-invocation?
4. Phương thức có đủ điều kiện để proxy intercept không, ví dụ không bị giới hạn bởi `private`/`final` trong trường hợp cần subclass proxy?
5. Transaction attribute, propagation và rollback rule có phù hợp tình huống không?

Lưu ý: mặc định, quy tắc rollback của Spring transaction thường áp dụng cho `RuntimeException` và `Error`; checked exception có thể cần cấu hình `rollbackFor` hoặc quy tắc tương ứng. Đây là một nguyên nhân khác khiến developer tưởng advice không chạy.

### 12.5. “Tại sao dùng `getBeanNamesForType` mà không thấy bean mong đợi?”

Có thể bean chưa được đăng ký do component scan, profile/condition hoặc cấu hình factory. Ngoài ra, với factory bean và proxy, việc dò kiểu có thể cần metadata hoặc quá trình khởi tạo để xác định kiểu sản phẩm. Kết quả tra cứu theo kiểu không nên được diễn giải tách khỏi cách bean được khai báo.

### 12.6. “Có thể lấy target từ proxy để gọi trực tiếp không?”

Một số Spring AOP proxy cho phép tiếp cận thông tin target thông qua những API hạ tầng, nhưng đây không phải cách gọi nghiệp vụ thông thường. Gọi trực tiếp target có thể bỏ qua các advice, và target source có thể có lifecycle hoặc cách cung cấp target riêng. Phần lớn ứng dụng nên tương tác thông qua interface/bean mà container công khai.

## 13. Bảng so sánh ngắn ba khái niệm

| Câu hỏi | `BeanDefinition` | Bean instance / target | Bean proxy |
| --- | --- | --- | --- |
| Là gì? | Metadata cấu hình | Object chứa logic/state | Object trung gian |
| Có thể tồn tại trước khi khởi tạo đối tượng? | Có | Chưa | Thường chưa |
| Tạo ra bởi ai? | Scanner/parser/registrar/configuration processor | Container hoặc factory theo định nghĩa | Cơ chế post-processing/AOP/scope thích hợp |
| Có thể được inject trực tiếp như service? | Không, về mặt khái niệm bean definition không phải service | Có nếu được container công khai trực tiếp | Có nếu container công khai proxy |
| Có chứa logic nghiệp vụ? | Không | Có | Thường chuyển tiếp đến logic của target, đồng thời thêm hành vi |
| Liên quan đến scope? | Lưu metadata scope | Số lượng/thời điểm tạo phụ thuộc scope | Scoped proxy có thể định tuyến đến target theo scope |
| Dễ thấy khi debug? | `getBeanDefinition(...)` | Constructor, lifecycle và nội dung method | `getBean(...).getClass()`, `AopUtils` |

**Một ví dụ tương đương dễ nhớ:** `BeanDefinition` giống công thức chuẩn bị món ăn, target bean là món ăn được làm theo công thức, còn proxy giống người phục vụ tiếp nhận yêu cầu và thực hiện các quy tắc bổ sung trước khi đưa yêu cầu tới đúng món ăn. Đây chỉ là phép so sánh; với scoped proxy, món ăn đích có thể khác nhau theo mỗi yêu cầu.

## 14. Thực hành trên dự án Spring Boot

### Bài 1 — Phân biệt definition và instance

Tạo class `ReportService` gắn `@Service`. Trong `main`, lấy:

```java
BeanDefinition bd =
    context.getBeanFactory().getBeanDefinition("reportService");

Object bean = context.getBean("reportService");
```

`context` ở đây có kiểu `ConfigurableApplicationContext`. Hãy in metadata từ `bd` và runtime class từ `bean`; giải thích tại sao chúng không phải cùng loại object. Thêm `@Lazy` vào `ReportService` và quan sát thời điểm constructor được gọi.

### Bài 2 — Phân biệt scope

Khai báo hai bean, một `singleton` mặc định và một `prototype`. Gọi `getBean` hai lần với mỗi loại và so sánh bằng `==`. Giải thích vì sao singleton của Spring không đồng nghĩa với singleton toàn JVM.

### Bài 3 — Nhận diện proxy

Thực hiện ví dụ Spring AOP ở mục 7. Ghi lại:

```java
AopUtils.isAopProxy(bean)
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
AopUtils.getTargetClass(bean)
```

Thử thay `spring.aop.proxy-target-class` giữa `false` và `true` trong môi trường hỗ trợ, sau đó so sánh kiểu runtime của bean. Giải thích vì sao inject theo interface có lợi khi sử dụng JDK proxy.

### Bài 4 — Dự đoán đường gọi

Cho code:

```java
@Service
public class AuditService {
    @Transactional
    public void record() {
        // Lưu lịch sử
    }

    public void execute() {
        record();
    }
}
```

Giả sử transaction được triển khai bằng proxy và `execute()` không có transaction advice riêng. So sánh:

1. Bean A inject `AuditService` rồi gọi `auditService.record()`.
2. Bean A inject `AuditService` rồi gọi `auditService.execute()`, trong đó `execute()` gọi `record()`.

Đường đi nào qua transaction interceptor của `record()`? Làm sao thiết kế lại để hai tình huống có hành vi nhất quán?

### Bài 5 — Scoped proxy

Tạo request-scoped bean `RequestTrace` và singleton `TraceService` như mục 9. Gửi hai HTTP request khác nhau và quan sát `traceId`. Giải thích vì sao singleton có thể giữ một tham chiếu ổn định mà dữ liệu request vẫn độc lập.

### Bài 6 — Tự giải thích một lỗi thực tế

Một developer viết:

```java
EmailService mail = new EmailService();
mail.sendWelcomeEmail();
```

Trong khi `EmailService` là `@Service` và `sendWelcomeEmail()` có annotation liên quan đến AOP. Hãy giải thích vì sao lời gọi này có thể bỏ qua hành vi do Spring quản lý và đề xuất cách inject `EmailService` từ container.

## 15. Ghi nhớ

Trong Spring Boot, **`BeanDefinition` trả lời “Spring sẽ tạo và quản lý bean này như thế nào?”**; **bean instance/target trả lời “đối tượng thực thi logic là gì?”**; còn **proxy trả lời “đối tượng khác đi qua cơ chế trung gian nào khi sử dụng bean?”**.

Một bean có thể được đăng ký trước khi có instance; một bean có thể được công khai trực tiếp hoặc qua proxy; và một proxy có thể điều hướng lời gọi đến target khác nhau theo scope. Khi quan sát ứng dụng, hãy tách rõ ba câu hỏi: *bean definition đã được đăng ký chưa, đối tượng nào đã được tạo, và tham chiếu được inject thực sự trỏ tới object nào?*

Đây là nền tảng để hiểu dependency injection, bean lifecycle, AOP, transaction, caching và những hành vi có điều kiện của Spring IoC container.
