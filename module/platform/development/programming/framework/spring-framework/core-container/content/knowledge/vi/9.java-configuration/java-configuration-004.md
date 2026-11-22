# Tên, bí danh và kiểu trả về của phương thức @Bean trong Spring Core Container

## Mục tiêu bài học

Trong Spring Core Container, phương thức được đánh dấu `@Bean` khai báo một **bean definition** dựa trên factory method Java. Ba khía cạnh rất dễ nhầm với nhau là:

1. **Tên bean (bean name):** định danh chính để container đăng ký và tra cứu bean.
2. **Bí danh (alias):** một hoặc nhiều tên bổ sung trỏ về **cùng bean definition**, không phải các bean độc lập.
3. **Kiểu trả về của phương thức `@Bean`:** metadata kiểu mà Spring có thể dùng để dự đoán ứng viên, giải quyết dependency và làm việc với generic, AOP/proxy hoặc các thành phần hạ tầng.

Bài này giải thích rõ cách khai báo và sử dụng từng khía cạnh, tập trung vào Java configuration bằng `@Configuration` và `@Bean`. Bạn sẽ biết khi nào để tên theo mặc định, khi nào đặt tên tường minh, phân biệt alias với hai factory methods riêng, chọn return type đúng, chẩn đoán `NoSuchBeanDefinitionException`/`NoUniqueBeanDefinitionException`, và thực hành với dự án Java 17 + Spring Framework thuần.

**Nguyên tắc:** Tên bean xác định **bean được gọi là gì**; alias xác định **các tên khác của cùng bean**; return type thể hiện **loại đối tượng mà factory method hứa cung cấp**. Chúng tương tác với dependency resolution nhưng không thay thế cho nhau.

## 1. Phương thức @Bean đăng ký cái gì?

Ví dụ tối giản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
```

Đây là **đoạn minh họa**, cần các kiểu `PaymentGateway` và `DemoPaymentGateway` do ứng dụng định nghĩa. Khi class `AppConfig` được đăng ký vào `ApplicationContext`:

- Spring đọc metadata `@Bean` trên phương thức `paymentGateway()`.
- Một bean definition được tạo cho factory method đó.
- Theo mặc định, bean có tên `paymentGateway` (giống tên method).
- Kiểu được công bố bởi method là `PaymentGateway`.
- Khi cần tạo bean theo scope/lifecycle, Spring gọi factory method và quản lý đối tượng trả về.

Bean không phải là chính phương thức Java; bean là **đối tượng do Spring quản lý** theo bean definition. Nếu gọi `new AppConfig().paymentGateway()` bên ngoài container, kết quả là đối tượng Java thường, không tự nhận lifecycle, dependency injection hay các post-processors của Spring.

Điều này khác với đăng ký hai bean definitions: một method `@Bean` với hai alias vẫn chỉ định nghĩa **một bean**, trong khi hai method `@Bean` riêng thường định nghĩa **hai bean** dù return type giống nhau.

## 2. Tên bean mặc định là tên của phương thức @Bean

Khi không khai báo `name` hoặc `value`:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
```

Spring đặt **bean name** mặc định là `paymentGateway`, đúng bằng tên Java method. Có thể tra cứu bằng tên:

```java
// Đoạn minh họa bên trong nơi đã có context.
PaymentGateway gateway =
        context.getBean("paymentGateway", PaymentGateway.class);
```

Điều cần ghi nhớ:

- Tên bean `paymentGateway` được dùng làm **định danh trong container**, không phải tên class `DemoPaymentGateway`.
- Đổi tên Java method `paymentGateway()` thành `createGateway()` mà vẫn giữ `@Bean` không tên sẽ **đổi bean name mặc định** thành `createGateway`.
- Nếu code cấu hình khác hoặc thư viện tra cứu bean bằng chuỗi `"paymentGateway"`, việc đổi tên method có thể gây lỗi runtime dù source vẫn biên dịch.
- Tiêm dependency theo kiểu `PaymentGateway` có thể vẫn hoạt động nếu Spring phân giải được một ứng viên duy nhất; tên không phải lúc nào cũng được người tiêu thụ nhắc đến trực tiếp.

**Khác với component scanning:** Một class `@Component` không có tên thường được `AnnotationBeanNameGenerator` đặt tên dựa trên tên class; còn `@Bean` không có tên dùng **tên factory method**. Hai quy tắc này có thể tạo ra cùng chuỗi trong một số trường hợp, nhưng nguồn gốc metadata khác nhau.

### Khi nào để tên mặc định?

Nếu cấu hình nội bộ đơn giản, không có lookup bằng chuỗi hoặc hợp đồng bean name công khai, tên phương thức dễ đọc thường là đủ. Chọn tên như `httpClient`, `orderRepository`, `notificationSender` để phản ánh vai trò bean.

Nếu bean name được tài liệu hóa như một integration contract — ví dụ bean dành cho module khác dùng `@Qualifier("billingGateway")` — nên cân nhắc đặt tên tường minh để refactor method không vô tình phá hợp đồng.

## 3. Đặt tên tường minh bằng @Bean(name) hoặc @Bean(value)

`@Bean` có hai thuộc tính `name` và `value`, là **alias cho nhau trong annotation metadata**. Một số cách viết tương đương về tên:

```java
// Các biến thể minh họa, chỉ chọn một cho một factory method:

@Bean(name = "billingGateway")
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}

@Bean(value = "billingGateway")
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}

@Bean("billingGateway")
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}
```

Các đoạn trên **không** được đặt cả ba method `gateway()` giống hệt nhau vào cùng một class; chúng là những phương án tương đương về cú pháp. Cả ba đều khai báo tên bean là `billingGateway` dù tên phương thức là `gateway`.

Nếu khai báo tên tường minh, đừng mặc định tên phương thức cũ còn dùng để `getBean(...)`. Với:

```java
@Bean("billingGateway")
PaymentGateway createGateway() {
    return new DemoPaymentGateway();
}
```

tên chính là `billingGateway`. Spring **không tự động** bổ sung `createGateway` làm alias. Nếu cần hỗ trợ tên này như một tên thứ hai, hãy khai báo trong mảng tên hoặc đăng ký alias có chủ đích.

**Lưu ý cú pháp:** `@Bean(name = ...)` nhận `String[]`, vì vậy một chuỗi đơn được Java chấp nhận như mảng một phần tử trong ngữ cảnh annotation. Dạng `@Bean("billingGateway")` là cách viết ngắn nhờ thuộc tính `value`.

### @Bean(name) khác @AliasFor

`@Bean.name` và `@Bean.value` được định nghĩa là alias **giữa hai thuộc tính annotation** theo `@AliasFor` của Spring. Còn `@Bean(name = {"main", "legacy"})` tạo ra một **bean name và một bean-name alias trong BeanFactory**.

Hai cách dùng từ "alias" này thuộc **hai cấp độ khác nhau**:

| Loại alias | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Alias thuộc tính annotation | `@Bean.name` và `@Bean.value` | Hai thuộc tính thể hiện cùng metadata cấu hình |
| Alias tên bean | `@Bean(name = {"main", "legacy"})` | Hai chuỗi tra cứu cùng một bean definition/instance theo scope |

Đừng nghĩ rằng khai báo `name` và `value` là cách tạo hai bean độc lập hoặc dùng chúng làm hai danh sách tên khác nhau.

## 4. Bí danh trong mảng @Bean(name = {...})

Khi một phương thức `@Bean` khai báo nhiều chuỗi tên:

```java
@Bean(name = {"paymentGateway", "legacyGateway", "checkoutGateway"})
PaymentGateway paymentGatewayFactory() {
    return new DemoPaymentGateway();
}
```

Spring dùng **phần tử đầu tiên** làm tên chính `paymentGateway`; những chuỗi còn lại là alias `legacyGateway` và `checkoutGateway` của **cùng bean**.

Ví dụ trong một singleton container:

```java
// Minh họa trong code đã có context.
Object a = context.getBean("paymentGateway");
Object b = context.getBean("legacyGateway");
Object c = context.getBean("checkoutGateway");

System.out.println(a == b && b == c);
```

Nếu bean là singleton mặc định và những tên đó được khai báo như trên, output là:

```text
true
```

Điều đó không nghĩa Spring tạo ba instance rồi trộn lại. Tất cả tên được phân giải đến cùng bean definition, và singleton resolution cho ra cùng reference.

### Dùng alias khi nào?

- **Tương thích ngược:** module cũ tra cứu `legacyGateway`, module mới chuyển sang `paymentGateway`.
- **Đa ngữ nghĩa cùng vai trò:** một bean cần được công bố cho hai API naming conventions có chủ đích.
- **Di trú cấu hình:** đổi tên chính nhưng vẫn hỗ trợ tên cũ trong giai đoạn chuyển đổi.

Cần thận trọng: alias càng nhiều càng khó nhận biết đâu là tên chuẩn; không dùng alias để che sự nhập nhằng thực sự giữa hai implementation khác nhau.

### Alias không tạo thêm bean cùng kiểu

Giả sử:

```java
@Bean(name = {"mainGateway", "oldMainGateway"})
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}
```

Lúc tiêm một `PaymentGateway`, chỉ có **một bean definition** được khai báo bởi method này. Số alias không làm container có "hai ứng viên cùng kiểu". Trong khi đó:

```java
@Bean("firstGateway")
PaymentGateway firstGateway() {
    return new DemoPaymentGateway();
}

@Bean("secondGateway")
PaymentGateway secondGateway() {
    return new DemoPaymentGateway();
}
```

là **hai bean definitions** tách biệt, có thể tạo hai singleton riêng; injection `PaymentGateway` không qualifier có thể trở nên nhập nhằng nếu không có quy tắc chọn.

### Bean name là duy nhất trong vùng BeanFactory

Tên chính và alias có thể xung đột với tên/alias khác. Một container không thể dùng cùng một tên hiệu quả cho hai bean definitions khác nhau mà không có chính sách override/đăng ký alias hợp lệ. Tùy loại container, phiên bản và cấu hình, tên trùng có thể bị từ chối hoặc có quy tắc ghi đè; **đừng** dựa vào thứ tự phương thức `@Bean` để mặc định bean cuối được chọn.

Nên dùng tên duy nhất, có ý nghĩa nghiệp vụ và kiểm thử trường hợp có nhiều module đăng ký bean cùng tên.

## 5. Tên bean khác biệt với việc chọn bean theo kiểu

Khi Spring inject dependency:

```java
@Bean
CheckoutService checkoutService(PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
```

Spring phân giải `PaymentGateway` theo **kiểu và các quy tắc chọn ứng viên**. Tên tham số `gateway` không phải một lệnh luôn phải tìm bean tên `gateway`; tên có thể là tín hiệu hỗ trợ trong một số tình huống chọn ứng viên, nhưng không thay thế cho `@Qualifier` khi cần xác định rõ một bean.

### Khi chỉ có một bean đúng kiểu

Nếu chỉ có một `PaymentGateway` có thể autowire, Spring thường tiêm bean đó bất kể tên tham số là `gateway` hay `paymentClient`.

### Khi có nhiều bean cùng kiểu

```java
@Configuration(proxyBeanMethods = false)
class MultiGatewayConfig {

    @Bean("fastGateway")
    PaymentGateway fastGateway() {
        return new FastPaymentGateway();
    }

    @Bean("safeGateway")
    PaymentGateway safeGateway() {
        return new SafePaymentGateway();
    }

    @Bean
    CheckoutService checkoutService(
            @Qualifier("safeGateway") PaymentGateway gateway) {
        return new CheckoutService(gateway);
    }
}
```

Đây là **đoạn minh họa cần các class ứng dụng tương ứng**. `@Qualifier("safeGateway")` làm injection point yêu cầu ứng viên phù hợp với qualifier/tên đó; tên Java method `checkoutService` xác định bean của consumer, không quyết định gateway.

Có thể đánh dấu `@Primary` trên một bean làm ứng viên ưu tiên khi cần chọn một bean theo kiểu. Nhưng `@Primary` không đổi tên bean và không tạo alias.

### Đừng lạm dụng tên tham số

Spring có một số cơ chế chọn ứng viên dựa trên bean name trùng tên dependency, tùy metadata tên tham số/field và những điều kiện khác. Điều này đôi khi giúp autowiring khi nhiều bean tồn tại, nhưng nó dễ thay đổi sau refactor. Khi selection mang ý nghĩa nghiệp vụ, dùng **`@Qualifier` tường minh**, interface hẹp, hoặc registry đúng mục đích.

### Tra cứu theo tên và kiểu cùng lúc

```java
PaymentGateway gateway =
        context.getBean("safeGateway", PaymentGateway.class);
```

Method này yêu cầu bean có **tên** `safeGateway` đồng thời có **kiểu tương thích** `PaymentGateway`. Nếu tên tồn tại nhưng bean không thể được cast sang kiểu yêu cầu, Spring báo lỗi kiểu; việc biết đúng tên không biến một đối tượng thành kiểu bất kỳ.

## 6. Return type của @Bean là metadata quan trọng

Phương thức factory công bố một **kiểu trả về Java**, ví dụ:

```java
@Bean
PaymentGateway paymentGateway() {
    return new DemoPaymentGateway();
}
```

Bean thực tế là instance `DemoPaymentGateway`, nhưng kiểu được khai báo là **`PaymentGateway`**. Spring sử dụng thông tin về phương thức `@Bean` để dự đoán bean type trong nhiều giai đoạn **trước khi instance được khởi tạo**.

Điều này có hệ quả:

- Những injection points nhận `PaymentGateway` có metadata phù hợp với return type.
- Một injection point đòi `DemoPaymentGateway` có thể **không được Spring nhận diện** ở thời điểm dự đoán type nếu factory method chỉ khai báo `PaymentGateway` và instance chưa được tạo.
- Sau khi bean đã được tạo, container có thể biết thêm runtime type, nhưng việc giải quyết dependency sớm không nên phụ thuộc vào việc bean tình cờ đã khởi tạo trước.
- Scope, proxying, factory object và generic metadata còn ảnh hưởng cách Spring thấy type; không đánh đồng Java runtime class với exposed bean type trong mọi giai đoạn.

### Chọn return type interface hay concrete class?

| Cách khai báo | Lợi điểm | Lưu ý |
| --- | --- | --- |
| `PaymentGateway paymentGateway()` | Giao diện rõ, khuyến khích consumer phụ thuộc abstraction | Không công bố concrete type đầy đủ trong method signature cho early type matching |
| `DemoPaymentGateway paymentGateway()` | Spring có nhiều metadata cụ thể hơn trước khi tạo bean | Consumer không nhất thiết phải inject theo concrete class; tránh coupling |
| `Object paymentGateway()` | Rất rộng, ít thông tin | Dễ làm container khó dự đoán đúng ứng viên; hầu như không nên dùng |
| `Collection<Handler> handlers()` | Công bố một bean có type collection | **Một bean collection**, khác với "nhiều Handler bean" được tiêm thành list |
| `FactoryBean<Product> productFactory()` | Công bố một `FactoryBean` cung cấp product | Spring có hợp đồng phân biệt **factory** và **product**; cần hiểu cú pháp `&name` |

**Khuyến nghị:** Khai báo **kiểu trả về đủ cụ thể để các injection point cần thiết được phân giải một cách tin cậy**. Đây không phải yêu cầu mọi factory method phải trả concrete class; nếu cả ứng dụng chỉ phụ thuộc `PaymentGateway`, việc trả interface này hoàn toàn hợp lý. Nếu bạn dự kiến Spring phải nhận bean theo subtype cụ thể **trước khi tạo**, hãy cân nhắc công bố subtype từ method hoặc thay đổi thiết kế injection.

### Không cố cast ở mọi nơi

Nếu một factory method trả `PaymentGateway` nhưng object là `DemoPaymentGateway`, việc cast ở một consumer để gọi method riêng của concrete type làm tăng coupling. Thường nên mở rộng interface đúng hợp đồng hoặc tạo một interface capability hẹp, thay vì buộc nhiều consumer phụ thuộc implementation.

## 7. Ví dụ hoàn chỉnh Java 17 + Spring Framework: tên, alias, kiểu trả về

Ví dụ sau chạy bằng Java 17 và Maven với Spring Framework thuần; không cần Spring Boot.

Mục tiêu kiểm chứng:

1. `@Bean` không chỉ định tên dùng **tên method**.
2. `@Bean(name = {"mailClient", "legacyMailClient"})` đăng ký **một bean và một alias**.
3. Nếu tên bean được đặt tường minh, tên method factory **không tự trở thành alias**.
4. Factory method có thể khai báo concrete return type `SmtpClient` hoặc interface return type `DeliveryClient`.
5. `@Primary` chọn bean ưu tiên cho single-bean injection mà không đổi tên và không loại các bean khác khỏi collection.
6. `@Qualifier("smsClient")` chọn chính xác một bean khi có hai ứng viên theo interface.

### 7.1. Tạo cấu trúc dự án

```text
bean-name-return-type/
├── pom.xml
└── src/main/java/demo/BeanIdentityDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-name-return-type</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. Mã nguồn Java

Tạo `src/main/java/demo/BeanIdentityDemo.java`:

```java
package demo;

import java.util.Arrays;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public class BeanIdentityDemo {

    interface DeliveryClient {
        String channel();
    }

    static final class SmtpClient implements DeliveryClient {
        @Override
        public String channel() {
            return "mail";
        }
    }

    static final class SmsClient implements DeliveryClient {
        @Override
        public String channel() {
            return "sms";
        }
    }

    static final class OrderNotifier {
        private final DeliveryClient client;

        OrderNotifier(DeliveryClient client) {
            this.client = client;
        }

        String notifyOrder(String orderId) {
            return client.channel() + ":" + orderId;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean(name = {"mailClient", "legacyMailClient"})
        @Primary
        SmtpClient createMailClient() {
            return new SmtpClient();
        }

        @Bean("smsClient")
        DeliveryClient createSmsClient() {
            return new SmsClient();
        }

        @Bean
        OrderNotifier orderNotifier(
                @Qualifier("smsClient") DeliveryClient client) {
            return new OrderNotifier(client);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            SmtpClient byMainName =
                    context.getBean("mailClient", SmtpClient.class);
            SmtpClient byAlias =
                    context.getBean("legacyMailClient", SmtpClient.class);
            SmtpClient byConcreteType =
                    context.getBean(SmtpClient.class);
            DeliveryClient byInterfaceType =
                    context.getBean(DeliveryClient.class);

            System.out.println("defaultName=" +
                    context.containsBean("orderNotifier"));
            System.out.println("methodNameIsBean=" +
                    context.containsBean("createMailClient"));
            System.out.println("aliasSame=" +
                    (byMainName == byAlias));
            System.out.println("concreteSame=" +
                    (byMainName == byConcreteType));
            System.out.println("primaryIsMail=" +
                    (byMainName == byInterfaceType));

            OrderNotifier notifier =
                    context.getBean(OrderNotifier.class);
            System.out.println("notifier=" +
                    notifier.notifyOrder("A42"));

            String[] names =
                    context.getBeanNamesForType(DeliveryClient.class);
            Arrays.sort(names);
            System.out.println("deliveryBeans=" +
                    Arrays.toString(names));
        }
    }
}
```

### 7.3. Biên dịch và chạy

Từ thư mục có `pom.xml`, cài JDK 17+ và Maven rồi chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanIdentityDemo
```

Output **do chương trình in**, không tính log của Maven/Spring nếu môi trường cấu hình log khác:

```text
defaultName=true
methodNameIsBean=false
aliasSame=true
concreteSame=true
primaryIsMail=true
notifier=sms:A42
deliveryBeans=[mailClient, smsClient]
```

### 7.4. Giải thích từng kết quả

**`defaultName=true`:** Method `orderNotifier(...)` chỉ có `@Bean` không tên, vì vậy bean mặc định tên `orderNotifier`.

**`methodNameIsBean=false`:** Method `createMailClient()` khai báo tên tường minh `mailClient` và alias `legacyMailClient`. Tên method `createMailClient` **không** tự được đăng ký thêm làm tên bean.

**`aliasSame=true`:** `mailClient` và `legacyMailClient` cùng trỏ tới bean definition singleton của `SmtpClient`, vì vậy chúng cho cùng instance.

**`concreteSame=true`:** Phương thức `createMailClient()` công bố kiểu trả về `SmtpClient`. Spring nhận diện và cung cấp bean này khi lookup theo concrete type `SmtpClient.class`. Bean lấy theo kiểu và tên chính giống nhau trong một context singleton.

**`primaryIsMail=true`:** Có hai bean implement `DeliveryClient`: `mailClient` và `smsClient`. `@Primary` trên factory method mail giúp Spring chọn mail khi lookup một `DeliveryClient` không có qualifier. `@Primary` không đổi tên `mailClient` và không hủy `smsClient`.

**`notifier=sms:A42`:** Factory method `orderNotifier` nhận tham số được đánh dấu `@Qualifier("smsClient")`. Dù mail là primary, qualifier chọn `smsClient` để tạo `OrderNotifier`; kết quả là `sms:A42`.

**`deliveryBeans=[mailClient, smsClient]`:** `getBeanNamesForType(DeliveryClient.class)` trả **bean names chính** của các bean phù hợp kiểu, không liệt kê `legacyMailClient` như bean độc lập. `Arrays.sort` bảo đảm thứ tự output theo tên; không dựa vào thứ tự đăng ký bean.

### 7.5. Tự kiểm chứng alias bằng BeanFactory

Trong `Main` của ví dụ, có thể thêm:

```java
// Đoạn bổ sung bên trong try đã có biến context:
boolean isAlias =
        context.getBeanFactory().isAlias("legacyMailClient");
System.out.println("recognizedAlias=" + isAlias);
```

Output bổ sung:

```text
recognizedAlias=true
```

Method `isAlias` kiểm tra tên đó được đăng ký là alias của một tên bean khác. Cần nhớ `context.getBean("legacyMailClient")` và `context.getBean("mailClient")` bằng reference với bean singleton không có nghĩa chúng là hai bean definitions.

## 8. Return type interface và concrete class khác nhau khi nào?

Xem hai kiểu factory:

```java
@Bean("mailA")
DeliveryClient mailA() {
    return new SmtpClient();
}

@Bean("mailB")
SmtpClient mailB() {
    return new SmtpClient();
}
```

Đây là đoạn minh họa, **không đặt hai bean này cạnh các bean đang có trong ví dụ chính nếu không sửa injection** vì thêm ứng viên có thể ảnh hưởng việc chọn bean.

**Ở runtime Java**, object của cả hai có thể là instance `SmtpClient`. Nhưng metadata lúc container đọc factory method khác nhau:

- `mailA()` công bố `DeliveryClient`.
- `mailB()` công bố `SmtpClient`.

Nếu Spring cần dự đoán bean nào có thể tiêm vào `SmtpClient` **trước khi khởi tạo**, `mailB` là ứng viên rõ ràng hơn vì method signature công bố concrete type. Không nên trông chờ bean `mailA` sẽ được tìm như `SmtpClient` ở mọi thời điểm khởi tạo, dù factory cuối cùng trả đúng subtype ấy.

### Tránh giả định "Spring sẽ tự nhìn vào return statement"

Spring không luôn thực thi factory method trước để biết return type thực tế. Làm vậy có thể phá lazy initialization, tạo resource sớm, hoặc tạo dependency cycle. Trong type prediction, method signature là nguồn metadata quan trọng. Hãy xem khai báo method như **hợp đồng của bean**, không chỉ như cú pháp Java cho compiler.

### Cân bằng abstraction và metadata

Khi các consumer chỉ cần `DeliveryClient`, trả interface là thiết kế tốt. Khi một bean cần cung cấp tính năng cụ thể của `SmtpClient` và Spring phải inject subtype đó, có thể:

1. Công bố concrete return type `SmtpClient` trong factory method.
2. Định nghĩa một interface có ý nghĩa hẹp hơn thay vì phụ thuộc concrete class.
3. Dùng qualifier hoặc bean name rõ ràng nếu mục tiêu là chọn implementation theo vai trò, **không phải** truy cập method đặc thù của concrete class.

Việc công bố concrete return type không buộc tất cả consumer phải inject concrete type: chúng vẫn có thể phụ thuộc `DeliveryClient`.

## 9. Return type và generic type trong dependency matching

Spring có thể dùng **generic type metadata** như một điều kiện lọc ứng viên. Đây là lý do khác để tránh raw types hoặc `Object` trong chữ ký phương thức `@Bean`.

Ví dụ:

```java
// Các đoạn minh họa; cần đặt trong một @Configuration phù hợp.
interface Codec<T> {
    T decode(byte[] input);
}

@Bean
Codec<String> stringCodec() {
    return bytes ->
            new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
}

@Bean
Codec<byte[]> binaryCodec() {
    return byte[]::clone;
}
```

Hai bean trên cùng interface raw `Codec`, nhưng metadata return type phân biệt `Codec<String>` và `Codec<byte[]>`. Một consumer khai báo:

```java
// Đoạn minh họa trong constructor bean khác:
CodecRegistry(Codec<String> stringCodec) {
    this.stringCodec = stringCodec;
}
```

có thể dùng generic như một tiêu chí phân giải `Codec<String>` khi Spring giữ được metadata kiểu tương ứng.

### Vì sao không nên trả raw Codec?

Nếu viết:

```java
// Phản ví dụ về metadata nghèo:
@Bean
@SuppressWarnings("rawtypes")
Codec codec() {
    return bytes -> "decoded";
}
```

method không công bố rõ generic argument. Spring có ít thông tin hơn khi lựa chọn những injection points với `Codec<String>` hoặc `Codec<byte[]>`. Raw type còn làm giảm type safety của Java. Nên khai báo đầy đủ generic khi một BeanFactory phải phân biệt các bean cùng raw type.

### Factory method trả Collection khác collection injection

Hai cấu hình sau phục vụ hai mục đích khác nhau:

```java
@Bean
java.util.List<String> supportedChannels() {
    return java.util.List.of("mail", "sms");
}
```

Đây là **một bean** có kiểu `List<String>`, được tạo từ một factory method.

Ngược lại, constructor nhận:

```java
// Đoạn minh họa trong Spring-managed bean:
Router(java.util.List<DeliveryClient> clients) {
    this.clients = clients;
}
```

thường yêu cầu Spring tổng hợp **nhiều bean `DeliveryClient`** vào một collection khi inject. Đừng nghĩ factory method trả `List<DeliveryClient>` và Spring tổng hợp nhiều `DeliveryClient` sẽ luôn tương đương trong mọi injection context; một cái là bean collection, cái kia là tập các bean ứng viên.

## 10. Kiểu trả về FactoryBean<T> là trường hợp đặc biệt

Spring có abstraction `org.springframework.beans.factory.FactoryBean<T>` để một bean factory object chịu trách nhiệm cung cấp **product bean**. Đây **không phải** cùng khái niệm với một phương thức `@Bean` bình thường, dù tên gọi đều có chữ "factory".

Ví dụ về ý tưởng:

```java
// Minh họa: ProductFactory là một FactoryBean<Product> do ứng dụng viết.
@Bean("product")
FactoryBean<Product> productFactory() {
    return new ProductFactory();
}
```

Cần hiểu khi dùng `FactoryBean<T>`:

- Tra cứu `context.getBean("product")` thông thường lấy **product** do `FactoryBean` tạo/cung cấp.
- Tra cứu `context.getBean("&product")` lấy **chính FactoryBean object** (tiền tố `&` là dereference convention của Spring).
- Generic `FactoryBean<Product>` và thông tin từ `getObjectType()` có ảnh hưởng quan trọng đến **dự đoán product type**; nếu không công bố đúng, autowiring theo product type có thể khó phân giải trước khi tạo factory/product.
- `FactoryBean` có hợp đồng về `getObject()`, `getObjectType()` và `isSingleton()` riêng; không suy ra product được tạo mới từ scope của factory bean mà không xét các method đó.

Đây là ví dụ minh họa API nâng cao, không phải chương trình độc lập. Khi không cần custom FactoryBean, một `@Bean Product product()` đơn giản thường dễ hiểu hơn. Đừng thêm FactoryBean chỉ để đổi tên bean hoặc tạo alias.

## 11. Return type và proxy/AOP/lazy resolution

Một bean có thể được Spring bọc bằng proxy khi bật transaction, AOP hoặc một số scope. Vì vậy, **runtime class nhận từ container có thể khác concrete class được factory method trực tiếp tạo ra**. Ví dụ JDK dynamic proxy thường implement interface mà không extend class thực tế. Đó là lý do constructor injection theo **interface ổn định** thường bền vững hơn kiểu cast concrete class không cần thiết.

Cần phân biệt:

- **Declared return type** trong phương thức `@Bean`.
- **Target class/instance** mà factory method tạo.
- **Exposed type** của bean sau khi Spring post-process/proxy ở thời điểm sử dụng.

Khi một injection point yêu cầu concrete class nhưng bean được proxy theo interface, việc tìm/cast bean có thể không phù hợp. Chọn interface làm hợp đồng chính hoặc điều chỉnh proxy strategy có chủ đích, không dựa vào chi tiết implementation.

### @Lazy không giải quyết metadata kiểu nghèo

`@Lazy` có thể trì hoãn thời điểm khởi tạo singleton nhưng không tự cung cấp generic/concrete type metadata đã bị mất do factory method khai báo `Object` hoặc raw interface. Ngược lại, declared return type rõ ràng càng quan trọng khi Spring phải quyết định ứng viên **trước khi tạo** đối tượng lazy.

### @Primary và @Qualifier cũng không "sửa" return type

Nếu một factory method khai báo `Object`, việc thêm `@Primary` không biến nó thành `PaymentGateway` về mặt Java type signature. `@Qualifier` lọc các ứng viên Spring đã xem là phù hợp; nếu metadata kiểu không thể xác định đúng từ factory method, qualifier không có phép màu để bảo đảm injection subtype sớm sẽ thành công.

## 12. Vai trò của tên bean khi dùng @Qualifier

`@Qualifier` thường được dùng tại constructor parameter, field hoặc tham số của method `@Bean`. Khi một qualifier là chuỗi trùng với bean name, Spring có thể chọn bean theo tên đó.

```java
@Bean
NotificationService notificationService(
        @Qualifier("mailClient") DeliveryClient client) {
    return new NotificationService(client);
}
```

Đoạn trên minh họa một class `NotificationService` phải được định nghĩa. Nó yêu cầu một bean `DeliveryClient` phù hợp với `mailClient`, không yêu cầu tên phương thức factory cũng là `mailClient`.

### Alias có thể dùng để tra cứu như một tên bean hợp lệ

```java
context.getBean("legacyMailClient");
```

lấy được bean đã đăng ký tên chính `mailClient` nếu `legacyMailClient` là alias. Trong autowiring, việc so khớp qualifier và tên/alias còn chịu quy tắc lựa chọn ứng viên của Spring. **Ưu tiên tên chính ổn định trong qualifier mới** và dùng alias cho tương thích khi cần, thay vì phát tán nhiều biệt danh tới mọi consumer.

### @Primary không biến alias thành bean thứ hai

Trong ví dụ `BeanIdentityDemo`, `@Primary` được đặt trên method khai báo `mailClient`. Nó gắn metadata ưu tiên vào **bean definition**, không chọn riêng tên chính mà bỏ alias; tìm theo `legacyMailClient` vẫn trỏ tới bean ấy.

## 13. Tránh nhầm @Bean name với Spring BeanDefinition identity

Một bean definition có các metadata như bean name, aliases, scope, qualifiers và factory method. Khi `@Bean` tạo singleton, BeanFactory còn giữ singleton object tương ứng.

Có thể hình dung:

```text
BeanDefinition "mailClient"
    ├── factoryMethod = AppConfig.createMailClient()
    ├── exposedType = SmtpClient
    ├── primary = true
    └── aliases:
        └── "legacyMailClient"
                 |
                 v
         BeanFactory resolves
                 |
                 v
         cùng managed singleton
```

Đối lập:

```text
BeanDefinition "mailClient" ---> SmtpClient instance A
BeanDefinition "smsClient"  ---> SmsClient instance B
```

Hai bean definitions riêng có thể cùng interface `DeliveryClient`, nhưng chúng có identity, scope, lifecycle và qualifiers độc lập. Để kiểm thử **alias**, hãy so sánh cùng reference và/hoặc gọi `isAlias`; để kiểm thử **hai bean độc lập**, hãy xem danh sách bean names theo type và xác nhận đúng các definitions.

### Singleton identity chỉ trong một container

Hai context khác nhau cùng đăng ký `@Bean("mailClient")` thường có **singleton độc lập**:

```java
// Đoạn minh họa với AppConfig đã định nghĩa:
try (var a = new AnnotationConfigApplicationContext(AppConfig.class);
     var b = new AnnotationConfigApplicationContext(AppConfig.class)) {
    System.out.println(
            a.getBean("mailClient") == b.getBean("mailClient"));
}
```

Output dự kiến:

```text
false
```

Vì mỗi `ApplicationContext` có singleton registry riêng. Bean name chỉ xác định object **trong phạm vi container**, không tự làm instance thành JVM-global singleton.

## 14. Đặt tên khi @Bean có nhiều method cùng tên hoặc inheritance

### Tránh overload factory methods thiếu chủ đích

Java cho phép overload:

```java
// Phản ví dụ minh họa, không đặt vào chương trình chạy chính:
@Bean
Client client() { return new Client(); }

@Bean
Client client(Settings settings) { return new Client(settings); }
```

Đây là nhiều factory methods **cùng tên Java**, dẫn đến khó đoán hoặc sai hợp đồng bean name/factory overload. Spring Framework hiện đại có các quy tắc xử lý/kiểm tra tính duy nhất của `@Bean` methods trong full configuration; khi khai báo overload cần rất thận trọng và có thể không được chấp nhận trong những cấu hình mặc định.

**Khuyến nghị:** Dùng các **tên phương thức khác nhau**, và nếu cần bean name cụ thể, dùng `@Bean("name")`. Đừng phụ thuộc vào overload để chọn factory method theo tập tham số vào lúc runtime nếu muốn Java configuration rõ ràng.

### Inheritance và method override

Nếu các configuration classes kế thừa phương thức `@Bean` hoặc override method, cách Spring xử lý phụ thuộc vào metadata method/class, full/lite mode và những quy tắc override liên quan. Không dựa vào inheritance phức tạp để tạo alias hoặc thay bean một cách ngầm. Với cấu hình nhiều module, `@Import` và các factory methods có tên riêng thường dễ hiểu/test hơn.

### Method rename là thay đổi public bean-name contract

Một dự án có:

```java
@Bean
Client oldClient() { return new Client(); }
```

Nếu đổi thành `createClient()`, tên bean mặc định đổi. Nếu các consumer tiêm bằng `@Qualifier("oldClient")` hoặc gọi `getBean("oldClient")`, cần cập nhật chúng hoặc giữ tên cũ bằng `@Bean("oldClient")` / alias tương thích.

Đừng xem đổi tên factory method luôn là refactor không ảnh hưởng hành vi runtime.

## 15. Tên và kiểu return của @Bean trong cấu hình nhiều module

Một module cấu hình có thể được import vào module khác:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfig {

    @Bean("billingClient")
    PaymentClient paymentClient() {
        return new HttpPaymentClient();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(ClientConfig.class)
class CheckoutConfig {

    @Bean
    CheckoutService checkoutService(
            @Qualifier("billingClient") PaymentClient paymentClient) {
        return new CheckoutService(paymentClient);
    }
}
```

Đây là các class minh họa, cần có `PaymentClient`, `HttpPaymentClient` và `CheckoutService`. `@Import` đưa configuration class vào context, còn tham số `PaymentClient paymentClient` được Spring giải quyết theo kiểu và qualifier. Ta **không cần** tự tạo `new ClientConfig().paymentClient()`.

Trong dự án đa module, đặt tên bean là một phần của thiết kế module nếu bên ngoài module phải tham chiếu nó. Khi đó:

- Ưu tiên tên có ý nghĩa và tránh xung đột với module khác, ví dụ `billingClient` thay vì `client` quá chung.
- Thông báo khi đổi tên chính; cân nhắc alias giữ tương thích trong giai đoạn migration.
- Công bố return type đủ ổn định như `PaymentClient` nếu consumer chỉ cần interface.
- Đừng để framework nội bộ ngầm phụ thuộc vào concrete type của một bean được khai báo trả interface rộng mà chưa có test.

## 16. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| `getBean("oldName")` lỗi sau refactor | Đã đổi tên `@Bean` method nhưng không đặt tên tường minh | Đặt `@Bean("oldName")` hoặc khai báo alias migration |
| `containsBean("factoryMethodName")` trả `false` | `@Bean(name=...)` đã đặt tên khác, tên method không tự là alias | Tra đúng primary bean name/alias đã khai báo |
| Có hai bean cùng interface nhưng tưởng một vì alias | Đã viết **hai** `@Bean` methods riêng | Dùng một method với mảng tên khi chỉ cần một bean |
| Nghĩ có hai bean vì `name={"a","b"}` | `b` chỉ là alias của `a` | Kiểm tra `getBeanNamesForType`/`isAlias` |
| `NoUniqueBeanDefinitionException` | Nhiều bean definitions cùng kiểu không có ứng viên thắng | Dùng `@Qualifier`, `@Primary` hoặc thiết kế collection |
| `NoSuchBeanDefinitionException` theo subtype | Return type factory chỉ là interface rộng, subtype chưa dự đoán được; cũng có thể chưa đăng ký bean | Khai báo return type cụ thể khi cần, kiểm tra đăng ký/scan và bean scope |
| `BeanNotOfRequiredTypeException` | Lookup bằng tên tồn tại nhưng kiểu yêu cầu không phù hợp | Dùng đúng interface/exposed type hoặc điều chỉnh proxy/config |
| Bean name collision | Hai methods/modules cố dùng cùng tên chính hoặc alias | Đặt tên duy nhất, kiểm tra BeanFactory và chính sách override |
| `@Primary` không giúp chọn đúng subtype | Primary chỉ giúp chọn trong tập ứng viên đã tương thích kiểu | Sửa return type/generic metadata hoặc injection type |
| Alias không thể được lấy | Alias chưa được khai báo đúng, xung đột tên hoặc config chưa được nạp | Kiểm tra `@Bean(name={...})`, context và bean definitions |
| Generic injection sai/nhập nhằng | Factory method trả raw type hoặc thiếu metadata generic | Khai báo `Codec<String>` thay vì `Codec` |
| FactoryBean không cho object dự kiến | Nhầm product và FactoryBean object hoặc `getObjectType()` sai | Phân biệt `name` với `&name` và hợp đồng FactoryBean |
| Bean type đổi sau khi bật AOP | Proxy expose type khác concrete class | Dùng interface injection hoặc cấu hình proxy phù hợp |
| Factory method dùng `new` ngoài Spring | Object không do Spring quản lý | Lấy bean từ context hoặc constructor-inject trong managed bean |

### Quy trình debug có hệ thống

1. **Xác định bean name chính**: method có `@Bean(name/value)` không? Nếu không, dùng tên method.
2. **Kiểm tra aliases**: chuỗi thứ hai trở đi trong `name={...}` có được đăng ký không?
3. **Xác định số bean definitions**: một factory method hay nhiều factory methods cùng kiểu?
4. **Xem declared return type**: interface, concrete class, generic hay raw type?
5. **Xem injection point**: cần một bean hay nhiều; có `@Qualifier`/`@Primary` không?
6. **Xem lifecycle**: singleton đã được tạo chưa; `@Lazy`/scope/proxy có ảnh hưởng type prediction không?
7. **Kiểm tra context**: configuration class đã được `register`, `@Import` hoặc component scan tìm thấy chưa?
8. **Đọc nguyên nhân gốc** trong exception chain: thiếu tên, thiếu kiểu, nhiều ứng viên, bean creation hay type mismatch?

### Đừng sửa lỗi bằng cách đổi tên ngẫu nhiên

Khi gặp `NoUniqueBeanDefinitionException`, đổi tên `firstGateway` thành `preferredGateway` không nhất thiết giải quyết việc hai bean cùng kiểu. Phải chỉ rõ **cách chọn ứng viên** bằng qualifier/primary hoặc sửa dependency để nhận collection đúng nhu cầu.

Tương tự, thêm alias cho một bean không làm nó có subtype khác. Bean name resolution và Java type compatibility là hai lớp kiểm tra khác nhau.

## 17. Kiểm thử hành vi cần giữ ổn định

Một cấu hình quan trọng nên được kiểm thử bằng Spring ApplicationContext nhỏ thay vì chỉ test Java factory method bằng `new`.

Trong ví dụ `BeanIdentityDemo`, các phép kiểm tra sau được đặt **bên trong `try` đã có biến `context`**, không phải chương trình độc lập:

```java
if (!context.containsBean("mailClient")) {
    throw new AssertionError("Missing primary bean name");
}
if (!context.containsBean("legacyMailClient")) {
    throw new AssertionError("Missing alias");
}
if (context.containsBean("createMailClient")) {
    throw new AssertionError("Unexpected method-name alias");
}
if (context.getBean("mailClient") !=
        context.getBean("legacyMailClient")) {
    throw new AssertionError("Alias must reference same singleton");
}
if (context.getBean(DeliveryClient.class) !=
        context.getBean(SmtpClient.class)) {
    throw new AssertionError("Primary selection is incorrect");
}
```

Nếu toàn bộ điều kiện đúng, đoạn assert không in thêm dòng stdout. Nếu sai, nó ném `AssertionError` với thông báo cụ thể. Một bộ integration tests có thể thực hiện những assert tương tự qua JUnit/AssertJ và kiểm tra cả tình huống thiếu bean hoặc nhập nhằng.

### Test rename and migration

Nếu thư viện khác cần tên bean `legacyMailClient`, một test tra cứu theo alias giúp bắt regression khi người viết vô tình xóa alias. Nếu bạn muốn bỏ tên cũ, test nên được cập nhật có chủ đích cùng kế hoạch chuyển đổi consumer; đừng để alias kéo dài không cần thiết.

### Test bean type prediction

Nếu một injection point cần `SmtpClient` và bạn đổi factory method từ return type `SmtpClient` sang `DeliveryClient`, hãy tạo context trong integration test với dependency đó để phát hiện việc Spring không còn phân giải subtype trước khi tạo bean. Test này có giá trị hơn giả định từ `getBean("mailClient").getClass()` sau khi context đã khởi tạo.

## 18. Bài tập và đáp án định hướng

### Bài 1 — Tên bean mặc định

```java
@Bean
ReportService reportService() {
    return new ReportService();
}
```

Tên bean mặc định là gì?

**Đáp án:** `reportService`. Đây là tên method, miễn không có metadata tên tường minh/chiến lược đăng ký đặc biệt thay đổi định danh.

### Bài 2 — Explicit name khác tên method

```java
@Bean("mainAudit")
AuditSink createAuditSink() {
    return new StdoutAuditSink();
}
```

Có thể mặc định gọi `getBean("createAuditSink")` không?

**Đáp án:** Không. Tên bean chính là `mainAudit`. `createAuditSink` chỉ là tên Java factory method, không tự trở thành bean name hoặc alias.

### Bài 3 — Một bean hay hai bean?

```java
@Bean(name={"mainAudit","legacyAudit"})
AuditSink auditSink() {
    return new StdoutAuditSink();
}
```

Có bao nhiêu bean definitions được phương thức này đóng góp? `legacyAudit` có tạo thêm singleton không?

**Đáp án:** Một bean definition; `legacyAudit` là alias của `mainAudit`, không phải một bean thứ hai. Với singleton mặc định, tra cứu hai tên cho cùng reference.

### Bài 4 — Hai implementation và qualifier

Một context có `@Bean("smsClient") DeliveryClient sms()` và `@Bean("mailClient") DeliveryClient mail()`. Một service phải luôn chọn SMS. Đổi tên method `sms()` thành `buildSms()` có đủ để chọn SMS không?

**Đáp án:** Không. Bean names tường minh vẫn là `smsClient` và `mailClient`; selection phải được xác định bằng `@Qualifier("smsClient")`, hoặc một quy tắc khác thực sự thể hiện yêu cầu nghiệp vụ.

### Bài 5 — Return type interface/concrete

Hai method `@Bean` đều trả instance `SmtpClient`, nhưng một method khai báo `DeliveryClient`, method kia khai báo `SmtpClient`. Khi Spring cần tìm ứng viên kiểu `SmtpClient` trước khi tạo bean, method nào dễ phân giải hơn?

**Đáp án:** Method khai báo return type `SmtpClient` cung cấp metadata subtype tường minh, nên thích hợp hơn cho early type prediction. Method khai báo interface `DeliveryClient` không công bố subtype bằng chữ ký, dù object tạo ra ở runtime có thể là `SmtpClient`.

### Bài 6 — Return type và generic

Vì sao `Codec<String> stringCodec()` tốt hơn raw `Codec stringCodec()` khi có nhiều codec trong container?

**Đáp án:** Spring có thêm generic metadata để chọn bean cho injection point `Codec<String>`; Java compiler cũng kiểm tra kiểu chặt chẽ hơn.

### Bài 7 — FactoryBean và tiền tố &

Một bean tên `product` được tạo bởi `FactoryBean<Product>`. `getBean("product")` và `getBean("&product")` có cùng mục đích không?

**Đáp án:** Không. Truy vấn thường lấy product do FactoryBean cung cấp; tên có tiền tố `&` dereference tới bản thân factory object. Hành vi này đặc biệt của Spring `FactoryBean`, không phải của mọi phương thức `@Bean`.

### Bài 8 — Đổi tên an toàn

Dự án muốn đổi bean name `oldGateway` thành `billingGateway` nhưng consumer cũ còn dùng tên cũ. Gợi ý cấu hình?

```java
@Bean(name = {"billingGateway", "oldGateway"})
PaymentGateway gateway() {
    return new DemoPaymentGateway();
}
```

**Đáp án:** `billingGateway` là tên chính mới, `oldGateway` là alias hỗ trợ tương thích. Cần lên kế hoạch cập nhật consumer, tránh giữ aliases không còn dùng vô thời hạn.

### Bài 9 — Bẫy collection bean

Một `@Bean List<Handler> handlers()` trả một danh sách handler. Điều đó có tương đương tạo N bean `Handler` bằng N phương thức `@Bean` độc lập không?

**Đáp án:** Không. Factory method trả danh sách đăng ký **một bean collection**; N phương thức đăng ký **N bean `Handler`**. Quy tắc injection collection có thể còn chịu ảnh hưởng các ứng viên có sẵn, vì vậy cần xác định chính xác thứ bạn muốn Spring quản lý.

### Bài 10 — Đọc log lỗi đúng tầng

Một consumer cần `@Qualifier("billingGateway") PaymentGateway`, nhưng Spring báo không có bean phù hợp. Bạn kiểm tra những gì?

**Đáp án:** Đầu tiên kiểm tra configuration đã được nạp, bean name/alias có `billingGateway` không, return type có phù hợp `PaymentGateway` không, và bean có bị loại khỏi autowire candidates không. Nếu bean tồn tại nhưng khởi tạo lỗi, đọc exception gốc thay vì chỉ thêm alias. Nếu có nhiều ứng viên và qualifier không đủ phân biệt, kiểm tra metadata lựa chọn.

## 19. Checklist thiết kế và review

- [ ] Tên bean chính là **tên method mặc định** hoặc tên đã khai báo tường minh.
- [ ] Nếu dùng `@Bean(name={"a","b"})`, hiểu `b` là alias, **không phải bean thứ hai**.
- [ ] Không vô tình dựa vào factory method name khi đã đặt tên tường minh khác.
- [ ] Bean names/aliases không trùng với module khác.
- [ ] Khi nhiều bean cùng kiểu, injection points có qualifier/primary hoặc collection contract rõ ràng.
- [ ] Return type đủ thông tin để Spring phân giải các dependency cần thiết.
- [ ] Generic return type được khai báo đầy đủ thay vì raw type.
- [ ] Không nhầm declared type, runtime object class và exposed proxy type.
- [ ] Nếu dùng `FactoryBean<T>`, phân biệt product và factory qua `name` / `&name`.
- [ ] Có integration test cho tên công khai, alias, bean identity và type matching.
- [ ] Việc đổi tên method `@Bean` được đánh giá như thay đổi hợp đồng runtime khi dựa vào tên mặc định.

## Tổng kết

Trong Java configuration của Spring, **`@Bean` đặt tên mặc định bằng method name**. `@Bean(name = ...)` hoặc `@Bean(value = ...)` cho phép chỉ định tên tường minh; khi cung cấp mảng tên, **phần tử đầu là bean name chính**, các phần tử còn lại là **aliases của cùng bean**. Alias không tăng số lượng bean definitions và không tạo thêm instance theo scope.

**Return type là hợp đồng type metadata của factory method**: nó ảnh hưởng cách Spring dự đoán bean type, chọn ứng viên và xử lý generic trước khi object được tạo. Trả interface là thiết kế tốt khi consumer phụ thuộc abstraction; trả concrete class có ích khi Spring cần dự đoán subtype để inject chính xác. Đừng khai báo return type quá rộng chỉ để code biên dịch.

Hãy đánh giá độc lập ba câu hỏi: **bean tên gì, có bao nhiêu bean độc lập, và bean được công bố dưới kiểu nào?** Trả lời rõ sẽ giúp tránh nhập nhằng autowiring, lỗi tên sau refactor và sự cố type matching khó phát hiện.

## Tài liệu tham khảo chính thức

- [Spring Framework — Using the @Bean Annotation (6.2)](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): naming, aliases, return type, injection và lifecycle.
- [Spring Framework — @Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): `name`, `value`, aliases và các thuộc tính của factory method.
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): `@Qualifier` và chọn ứng viên.
- [Spring Framework — Fine-tuning Annotation-based Autowiring with @Primary](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html): lựa chọn primary khi có nhiều ứng viên.
- [Spring Framework — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/generics-as-qualifiers.html): generic type trong injection.
- [Spring Framework — Customizing Instantiation Logic with FactoryBean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): hợp đồng của `FactoryBean`, product type và lifecycle.
