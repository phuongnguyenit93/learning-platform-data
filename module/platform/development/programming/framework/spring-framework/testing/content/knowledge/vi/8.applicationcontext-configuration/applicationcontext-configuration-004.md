# Phát hiện cấu hình mặc định khi không chỉ định rõ

Khi viết kiểm thử tích hợp với Spring Test, ta thường cần một `ApplicationContext` chứa các bean phục vụ bài kiểm thử. Có thể khai báo rõ file XML hoặc lớp cấu hình Java trong `@ContextConfiguration`. Tuy nhiên, Spring Test cũng hỗ trợ phát hiện cấu hình theo quy ước khi annotation này không chỉ định `locations` hoặc `classes`.

Cơ chế này giúp giảm cấu hình lặp lại trong các test class đơn giản. Spring có thể tìm lớp cấu hình Java lồng bên trong test class hoặc tìm file XML theo tên test class. Khi không có cấu hình phù hợp, hoặc có nhiều ứng viên không thể chọn một cách rõ ràng, việc khởi tạo context sẽ thất bại. Vì vậy, cần hiểu quy ước đặt tên và giới hạn của cơ chế phát hiện mặc định để biết Spring đang nạp cấu hình nào.

## 1. Cấu hình tường minh và cấu hình theo quy ước

Spring TestContext Framework cần biết cách tạo `ApplicationContext` trước khi chạy các phương thức kiểm thử. Cấu hình có thể được chỉ định tường minh:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
class OrderServiceTests {
    // Test methods
}
```

Trong ví dụ này, `classes` chỉ rõ lớp cấu hình Java cần dùng. Nếu ứng dụng dùng XML, có thể chỉ định `locations`:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "/test-context.xml")
class OrderServiceTests {
    // Test methods
}
```

Khi không truyền `classes` hoặc `locations`, Spring Test có thể áp dụng default configuration detection. Đây là cơ chế dựa trên quy ước, không phải việc Spring tự quét toàn bộ project rồi đoán bean nào cần dùng. Spring tìm các ứng viên theo những quy tắc cụ thể của `ContextLoader`.

Ví dụ, annotation không có thuộc tính cấu hình:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration
class OrderServiceTests {
    // Test methods
}
```

`@ContextConfiguration` vẫn cần xuất hiện để khai báo rằng test sử dụng Spring TestContext Framework và cần nạp context. Chỉ thêm `@ExtendWith(SpringExtension.class)` mà không có `@ContextConfiguration`, `@ContextHierarchy` hoặc annotation cấu hình Spring tương ứng không tự cung cấp nguồn cấu hình cho context.

## 2. Cơ chế phát hiện mặc định của Spring Test

Với cấu hình mặc định của Spring Test, `@ContextConfiguration` có thể được dùng mà không khai báo `classes` hay `locations`. `DelegatingSmartContextLoader` thực hiện default detection theo trình tự: tìm các lớp cấu hình Java lồng `static` được đánh dấu `@Configuration`; nếu không tìm thấy lớp phù hợp, loader chuyển sang quy ước tìm resource XML mặc định. Nếu có nhiều lớp cấu hình Java lồng phù hợp, Spring không tự chọn một lớp tùy ý mà báo lỗi để người viết test chỉ định rõ.

Hai dạng cấu hình thường gặp là:

- **Lớp cấu hình Java lồng bên trong test class:** Spring tìm các lớp lồng `static` được đánh dấu `@Configuration` trước.
- **File XML mặc định:** nếu không phát hiện được lớp cấu hình Java, loader XML tìm resource có tên dựa trên tên đầy đủ của test class và hậu tố `-context.xml`.

Với `DelegatingSmartContextLoader` mặc định, Spring hỗ trợ cả hai kiểu cấu hình theo trình tự trên. Nếu muốn hành vi dễ dự đoán trong một dự án có nhiều loại loader hoặc nhiều nguồn cấu hình, hãy chỉ định `classes` hoặc `locations` rõ ràng.

## 3. Phát hiện lớp cấu hình Java lồng bên trong test class

### 3.1. Quy ước lớp cấu hình mặc định

Nếu test class có một lớp lồng `static` được đánh dấu `@Configuration`, Spring Test có thể phát hiện lớp đó làm cấu hình mặc định khi `@ContextConfiguration` không chỉ định `classes`.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration
class GreetingServiceTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    void createsGreetingServiceFromDetectedConfiguration() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfig {

        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}

class GreetingService {
    String greet(String name) {
        return "Hello, " + name;
    }
}
```

`TestConfig` là lớp lồng `static` và có `@Configuration`, nên có thể được phát hiện làm cấu hình mặc định. Spring tạo context từ cấu hình đó, đăng ký bean `GreetingService`, rồi inject bean vào field `greetingService` của test class.

### 3.2. Vì sao lớp cấu hình phải là static nested class?

Lớp cấu hình mặc định được phát hiện theo quy ước là lớp lồng `static`. Một non-static inner class cần có instance của lớp bên ngoài để được khởi tạo. Spring Test không dùng instance test class như một đối tượng bao ngoài để tự tạo loại cấu hình này.

Do đó, nếu đặt cấu hình trong test class, nên khai báo:

```java
@Configuration
static class TestConfig {
    // @Bean methods
}
```

Không nên dựa vào một lớp lồng không có `static` để làm default configuration. Nếu cấu hình cần nằm ngoài test class, hãy tạo top-level configuration class và khai báo rõ bằng `@ContextConfiguration(classes = ...)`.

### 3.3. Có nhiều lớp cấu hình lồng nhau

Default detection hoạt động tốt khi Spring có thể xác định cấu hình mặc định một cách rõ ràng. Nếu test class chứa nhiều static nested class được đánh dấu `@Configuration`, Spring không thể tự biết lớp nào là cấu hình mong muốn. Khi đó, hãy khai báo rõ lớp cần dùng:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderServiceTests.OrderConfig.class)
class OrderServiceTests {

    @Configuration
    static class OrderConfig {
        // Order test beans
    }

    @Configuration
    static class PaymentConfig {
        // Payment test beans
    }
}
```

Nếu test cần cả hai cấu hình, truyền cả hai lớp theo thứ tự mong muốn:

```java
@ContextConfiguration(classes = {
        OrderServiceTests.OrderConfig.class,
        OrderServiceTests.PaymentConfig.class
})
```

Việc chỉ định tường minh giúp người đọc hiểu context được lắp ghép từ đâu và tránh phụ thuộc vào quy tắc phát hiện tự động.

## 4. Phát hiện file XML mặc định

### 4.1. Quy ước tên resource

Khi sử dụng XML-based context loader và không chỉ định `locations`, Spring có thể tìm file XML theo tên đầy đủ của test class. Với test class:

```java
package com.example.orders;

class OrderRepositoryTests {
}
```

resource mặc định theo quy ước là:

```text
classpath:com/example/orders/OrderRepositoryTests-context.xml
```

Tên package được chuyển thành đường dẫn thư mục, tên test class được giữ nguyên và hậu tố `-context.xml` được thêm vào. File phải nằm trên classpath của test, thường là trong `src/test/resources`.

Ví dụ cấu trúc dự án:

```text
src
├── test
│   ├── java
│   │   └── com/example/orders/OrderRepositoryTests.java
│   └── resources
│       └── com/example/orders/OrderRepositoryTests-context.xml
```

Test class có thể khai báo:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration
class OrderRepositoryTests {
    // Spring Test loads the convention-based XML resource.
}
```

XML context loader sẽ nạp file theo quy ước nếu resource tồn tại và loader đang sử dụng hỗ trợ cách phát hiện đó. Có thể khai báo rõ resource nếu muốn đổi tên file hoặc đặt nó ở vị trí khác:

```java
@ContextConfiguration(locations = "classpath:/spring/order-test-context.xml")
```

### 4.2. Ví dụ file XML

Một file XML tối giản có thể đăng ký bean:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="greetingService" class="com.example.orders.GreetingService"/>
</beans>
```

Nếu resource được đặt đúng đường dẫn mặc định, test có thể dùng `@Autowired` để nhận bean như với cấu hình XML được chỉ định tường minh. Quy ước phát hiện chỉ giúp Spring tìm resource; nội dung XML vẫn phải hợp lệ và có thể khởi tạo các bean cần thiết.

## 5. Chọn cấu hình rõ ràng khi cần

Default detection phù hợp với test class nhỏ và cấu trúc ổn định. Khi có nhiều cấu hình, nhiều profile, nhiều module hoặc yêu cầu kiểm soát chính xác context, nên chỉ định rõ cấu hình.

### 5.1. Chỉ định lớp cấu hình Java

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        OrderTestConfig.class,
        SharedTestConfig.class
})
class OrderServiceTests {
}
```

### 5.2. Chỉ định một hoặc nhiều file XML

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = {
        "classpath:/spring/application-test.xml",
        "classpath:/spring/order-test.xml"
})
class OrderServiceTests {
}
```

### 5.3. Kết hợp XML và Java configuration

Nếu cần kết hợp nguồn XML và Java, có thể dùng `@ImportResource` trong lớp cấu hình Java hoặc khai báo các nguồn phù hợp theo context loader đang sử dụng. Ví dụ:

```java
@Configuration
@ImportResource("classpath:/spring/legacy-order-context.xml")
static class OrderTestConfig {
    // Java @Bean methods can be declared here.
}
```

Sau đó chỉ định `OrderTestConfig.class` trong `@ContextConfiguration`. Cách này làm rõ cấu hình Java là điểm bắt đầu và XML được import như một phần của context.

Không nên khai báo cả `classes` và `locations` một cách tùy tiện mà không xem xét loại `ContextLoader`. Smart loader có thể chọn loader dựa trên loại metadata đã khai báo; nếu cần kết hợp hai định dạng, nên dùng cơ chế import rõ ràng hoặc một loader hỗ trợ trường hợp đó.

## 6. Phân biệt default detection của Spring Test và Spring Boot

Một nhầm lẫn phổ biến là cho rằng `@ContextConfiguration` và `@SpringBootTest` dùng cùng một quy tắc phát hiện cấu hình. Chúng thuộc hai cơ chế bootstrap khác nhau.

### 6.1. Spring Test thuần

Với `@ContextConfiguration` không chỉ định `classes` hoặc `locations`, Spring Test sử dụng quy ước của context loader: lớp nested `static` có `@Configuration` hoặc resource XML mặc định dựa trên tên test class.

### 6.2. Spring Boot Test

Với `@SpringBootTest` không chỉ định `classes`, Spring Boot tìm một lớp cấu hình gốc có `@SpringBootConfiguration` trong package của test hoặc các package cha. Trong ứng dụng thông thường, annotation này được cung cấp gián tiếp bởi `@SpringBootApplication`.

Ví dụ:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Nếu `OrderApplication` có `@SpringBootApplication` và nằm trong `com.example.orders` hoặc package cha phù hợp, Spring Boot có thể phát hiện lớp đó làm cấu hình ứng dụng. Cơ chế này không dựa vào tên file `OrderApplicationTests-context.xml`.

Nếu có nhiều nguồn cấu hình hoặc muốn dùng một application class cụ thể, hãy khai báo:

```java
@SpringBootTest(classes = OrderApplication.class)
class OrderApplicationTests {
}
```

Nếu Spring Boot không tìm được `@SpringBootConfiguration`, test thường thất bại với lỗi cho biết không thể tìm cấu hình Spring Boot. Khi đó, kiểm tra package của test, vị trí lớp ứng dụng và cấu hình `classes`.

### 6.3. Bảng so sánh

| Cơ chế | Cấu hình mặc định được tìm | Cách chỉ định rõ |
|---|---|---|
| `@ContextConfiguration` của Spring Test | Nested `static @Configuration` hoặc resource XML theo quy ước của context loader | `classes` hoặc `locations` |
| `@SpringJUnitConfig` | Kế thừa cơ chế `@ContextConfiguration` và tích hợp JUnit Jupiter | `classes` hoặc `locations` |
| `@SpringBootTest` | Lớp `@SpringBootConfiguration`, thường là lớp có `@SpringBootApplication` | `classes` |

Không nên đổi tên test class để sửa lỗi tìm thấy `@SpringBootConfiguration`, bởi Spring Boot không dùng quy ước XML của Spring Test cho việc đó. Cần xác định đúng annotation đang bootstrap context trước khi sửa cấu hình.

## 7. Dùng @SpringJUnitConfig với cấu hình mặc định

`@SpringJUnitConfig` là annotation kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. Vì vậy, nó cũng có thể dùng cơ chế phát hiện mặc định của `@ContextConfiguration`.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig
class PriceCalculatorTests {

    @Autowired
    private PriceCalculator calculator;

    @Test
    void calculatesTotal() {
        assertEquals(120, calculator.total(100, 20));
    }

    @Configuration
    static class TestConfig {
        @Bean
        PriceCalculator priceCalculator() {
            return new PriceCalculator();
        }
    }
}

class PriceCalculator {
    int total(int amount, int fee) {
        return amount + fee;
    }
}
```

Ở đây `@SpringJUnitConfig` thay cho cặp annotation `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. Nested `TestConfig` vẫn là cấu hình Java mặc định có thể phát hiện.

Nếu muốn viết ngắn gọn hơn, có thể truyền `classes` trực tiếp vào `@SpringJUnitConfig(PriceCalculatorConfig.class)`. Cách tường minh phù hợp khi cấu hình được dùng chung bởi nhiều test class hoặc không nằm trong test class.

## 8. Cấu hình mặc định và kế thừa giữa các test class

Spring Test hỗ trợ kế thừa cấu hình từ test class cha khi các annotation cấu hình cho phép kế thừa. Điều này thường hữu ích khi nhiều test dùng chung một phần cấu hình nền.

Ví dụ:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
abstract class BaseIntegrationTests {
}

class OrderServiceTests extends BaseIntegrationTests {
    // Uses the inherited context configuration.
}
```

`@ContextConfiguration` mặc định cho phép kế thừa cấu hình từ lớp cha thông qua thuộc tính `inheritLocations`. Với cấu hình lớp Java, thuộc tính này cũng điều khiển việc kế thừa các component classes. Nếu lớp con khai báo cấu hình riêng, Spring có thể hợp nhất metadata theo quy tắc kế thừa; nếu muốn thay thế hoàn toàn cấu hình được kế thừa, cần đặt `inheritLocations = false` và khai báo rõ nguồn cấu hình của lớp con.

Ví dụ lớp con dùng cấu hình riêng:

```java
@ContextConfiguration(
        classes = OrderServiceTests.OrderConfig.class,
        inheritLocations = false
)
class OrderServiceTests extends BaseIntegrationTests {

    @Configuration
    static class OrderConfig {
        // Configuration specific to order tests
    }
}
```

Khi dùng kế thừa, cần phân biệt cấu hình từ lớp cha với default detection từ chính lớp test. Một test class có thể nhận cấu hình qua metadata được kế thừa mà không cần tự phát hiện lại. Nếu kết quả context khó hiểu, hãy xem toàn bộ chuỗi lớp cha và các annotation cấu hình, không chỉ lớp con.

## 9. Khi không tìm thấy cấu hình mặc định

Default detection không bảo đảm rằng Spring luôn có thể tạo context. Các tình huống thường gặp gồm:

- Test class không có nested static class nào được đánh dấu `@Configuration` và cũng không có XML resource theo quy ước.
- File XML có tồn tại nhưng nằm sai package hoặc sai tên hậu tố.
- Có nhiều nested configuration class khiến Spring không thể chọn một cấu hình mặc định duy nhất.
- Test đang sử dụng context loader tùy chỉnh hoặc loader chỉ hỗ trợ một kiểu cấu hình.
- Cấu hình được tìm thấy nhưng một bean hoặc resource cần thiết không thể khởi tạo.

Trong các trường hợp không tìm được ứng viên, Spring thường ném exception trong giai đoạn bootstrap context, trước khi phương thức test được thực thi. Thông báo lỗi thường cho biết không thể phát hiện default configuration classes hoặc không tìm thấy resource mặc định. Nếu resource đã tìm thấy nhưng nội dung cấu hình sai, lỗi có thể xuất hiện dưới dạng lỗi parse XML, lỗi tạo bean hoặc `Failed to load ApplicationContext`.

### 9.1. Cách xử lý theo nguyên nhân

| Triệu chứng | Điều cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không phát hiện default configuration class | Có nested class `static` và `@Configuration` hay không | Thêm cấu hình hợp lệ hoặc khai báo `classes` rõ ràng |
| Không tìm thấy XML resource | Package, tên test class, hậu tố `-context.xml`, vị trí trong test classpath | Đặt resource đúng convention hoặc chỉ định `locations` |
| Có nhiều lớp `@Configuration` lồng nhau | Test class có nhiều ứng viên mặc định hay không | Chọn lớp hoặc danh sách lớp bằng `classes` |
| Không tìm thấy `@SpringBootConfiguration` | Package test có nằm dưới package chứa ứng dụng không | Đặt test đúng package hoặc truyền `classes` vào `@SpringBootTest` |
| Context được tìm thấy nhưng khởi tạo thất bại | Bean, profile, property, datasource, resource và lỗi gốc trong stack trace | Sửa cấu hình hoặc dependency gây lỗi; không thay đổi tên test class một cách ngẫu nhiên |

### 9.2. Dùng cấu hình tường minh để giảm mơ hồ

Khi test là một phần của bộ kiểm thử lớn, cấu hình tường minh thường giúp việc bảo trì dễ hơn:

```java
@SpringJUnitConfig(classes = {
        SharedTestConfig.class,
        OrderFeatureTestConfig.class
})
class OrderFeatureTests {
}
```

Đổi lại, test class có thêm metadata cần duy trì. Lựa chọn giữa default detection và cấu hình tường minh nên dựa trên mức độ ổn định, khả năng tái sử dụng và độ rõ ràng của cấu hình.

## 10. Cấu hình được phát hiện ảnh hưởng đến context cache

Spring TestContext Framework có thể cache `ApplicationContext` để các test class dùng cùng cấu hình không phải khởi tạo lại context liên tục. Cấu hình đã được phát hiện trở thành một phần metadata dùng để xác định context cần nạp và cache.

Điều này có một số hệ quả thực tế:

- Nhiều test class dùng chung cùng một lớp cấu hình Java hoặc cùng resource XML có thể tái sử dụng context nếu các metadata liên quan tương thích.
- XML mặc định có tên dựa trên từng test class, vì vậy các test class khác nhau có thể vô tình dùng các context khác nhau dù nội dung XML tương tự.
- Cấu hình tường minh dùng chung một class có thể giúp ý định tái sử dụng context rõ hơn.
- Nếu một test làm bẩn context, `@DirtiesContext` có thể yêu cầu Spring loại context khỏi cache; annotation này nên được dùng khi test thực sự làm thay đổi trạng thái context.

Default detection chỉ quyết định nguồn cấu hình cần dùng; nó không đồng nghĩa mỗi test method sẽ luôn tạo một `ApplicationContext` mới. Việc tái sử dụng context được điều khiển bởi cơ chế cache và metadata cấu hình của Spring Test.

## 11. Quy trình xác định cấu hình Spring đang được sử dụng

Khi một bài kiểm thử khởi tạo context không như mong đợi, có thể lần lượt xác định:

1. **Xác định annotation bootstrap.** Test dùng `@ContextConfiguration`, `@SpringJUnitConfig` hay `@SpringBootTest`?
2. **Kiểm tra thuộc tính cấu hình.** Có truyền `classes`, `locations`, `value` hoặc context loader tùy chỉnh không?
3. **Nếu không khai báo rõ, kiểm tra quy ước mặc định.** Với Spring Test, tìm nested static `@Configuration` và XML resource theo tên test class.
4. **Kiểm tra cấu hình kế thừa.** Xem lớp cha có `@ContextConfiguration` và thuộc tính kế thừa có đang bật không.
5. **Đọc exception gốc.** Phân biệt lỗi không tìm được cấu hình với lỗi đã tìm thấy cấu hình nhưng không khởi tạo được bean.
6. **Chỉ định rõ khi cần.** Dùng `classes` hoặc `locations` để loại bỏ mơ hồ và làm rõ nguồn cấu hình của test.

Ví dụ, nếu `OrderServiceTests` dùng `@ContextConfiguration` nhưng không có nested configuration class, hãy kiểm tra resource `com/example/orders/OrderServiceTests-context.xml` trên test classpath. Nếu test thực ra dùng `@SpringBootTest`, hãy tìm lớp `@SpringBootConfiguration` ở package phù hợp hoặc chỉ định lớp ứng dụng qua `classes`.

## 12. Những lưu ý khi áp dụng trong dự án

- Dùng default detection cho test đơn giản, nơi cấu hình mặc định có một ứng viên duy nhất và tên resource tuân theo quy ước.
- Dùng lớp cấu hình Java `static` lồng trong test khi cấu hình chỉ phục vụ test đó.
- Dùng top-level test configuration và khai báo `classes` khi nhiều test cần tái sử dụng cấu hình.
- Dùng `locations` khi kiểm thử cấu hình XML hoặc khi cần xác định chính xác file resource.
- Phân biệt quy tắc của Spring Test với quy tắc tìm `@SpringBootConfiguration` của Spring Boot.
- Không dựa vào default detection nếu test class có nhiều nguồn cấu hình hoặc cần một context hierarchy phức tạp; hãy khai báo rõ metadata.

Phát hiện cấu hình mặc định giúp Spring Test giảm phần khai báo lặp lại, nhưng cơ chế này chỉ hoạt động theo những quy ước cụ thể. Với `@ContextConfiguration`, Spring có thể phát hiện lớp nested `static @Configuration` hoặc XML resource theo tên test class. Với `@SpringBootTest`, Spring Boot tìm lớp `@SpringBootConfiguration`, thường là lớp có `@SpringBootApplication`. Khi quy ước không thể xác định một cấu hình duy nhất, hãy chỉ định rõ `classes` hoặc `locations` để context được tạo đúng như bài kiểm thử mong đợi.
