# Khai báo basePackages và basePackageClasses trong Spring Component Scan

## Mục tiêu

Spring Core Container có thể tìm các class được đánh dấu `@Component`, `@Service`, `@Repository`, `@Controller` hoặc stereotype tương thích, rồi tạo bean definition tương ứng mà không cần viết phương thức `@Bean` cho từng class. Cơ chế này gọi là **component scanning**. Tuy nhiên, Spring cần biết **bắt đầu tìm trong những package nào**.

Annotation `org.springframework.context.annotation.ComponentScan` cung cấp hai thuộc tính thường dùng để xác định phạm vi:

- `basePackages`: chỉ định **tên package dưới dạng chuỗi** (ví dụ `"com.example.orders"`).
- `basePackageClasses`: chỉ định **các class/interface làm mốc**; Spring lấy **package chứa các kiểu đó** làm điểm bắt đầu quét.

Bài này giúp bạn chọn đúng thuộc tính, phối hợp nhiều package, hiểu quét đệ quy qua package con, dùng marker interface an toàn khi refactor, khắc phục trường hợp thiếu bean và kiểm tra kết quả bằng ví dụ Java 17 + Spring Framework chạy được.

**Phạm vi:** Đây là cách cấu hình `@ComponentScan` trong **Spring Core Container**. Các cơ chế quét entity của JPA, Spring Data repository, hoặc đăng ký bean thủ công có quy tắc riêng; chúng chỉ được nhắc ngắn khi dễ gây nhầm.

## 1. Component scanning giải quyết vấn đề gì?

Xem cấu trúc package:

```text
com.example.shop
├── app
│   └── AppConfig.java
├── orders
│   ├── OrderService.java
│   └── internal
│       └── OrderValidator.java
└── shipping
    ├── ShippingService.java
    └── ShippingPackage.java
```

Giả sử `AppConfig` mang annotation `@Configuration` và `@ComponentScan`. Nếu không cấu hình thêm package, Spring sẽ bắt đầu quét tại **package của class khai báo `@ComponentScan`**, tức `com.example.shop.app`, bao gồm các package con của nó. Vì `orders` và `shipping` là package **anh em**, chúng không được tìm thấy bằng quét mặc định từ `app`.

Một nguyên nhân phổ biến của `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` là **component có thật nhưng nằm ngoài vùng quét**.

Bạn có thể giải quyết bằng một trong hai cách:

```java
// Khai báo bằng chuỗi tên package:
@ComponentScan(basePackages = {
    "com.example.shop.orders",
    "com.example.shop.shipping"
})
```

hoặc:

```java
// Dùng hai marker type đặt trong hai package đích:
@ComponentScan(basePackageClasses = {
    OrdersPackage.class,
    ShippingPackage.class
})
```

Đây là **các đoạn minh họa annotation**. Để sử dụng được, cần có `@Configuration` trên class cấu hình, import `org.springframework.context.annotation.ComponentScan` và các marker tương ứng.

Cả hai cách yêu cầu Spring quét **hai vùng package**; chúng không có nghĩa là lập danh sách cố định hai bean phải tạo.

## 2. Ý nghĩa chính xác của `basePackages`

Chữ ký thuộc tính trong `@ComponentScan`:

```java
String[] basePackages() default {};
```

Một số cách viết đúng:

```java
@Configuration
@ComponentScan(basePackages = "com.example.shop")
class ShopConfig {
}
```

```java
@Configuration
@ComponentScan(basePackages = {
    "com.example.shop.orders",
    "com.example.shop.shipping"
})
class ShopConfig {
}
```

Trong cả hai đoạn, import cần có là `org.springframework.context.annotation.Configuration` và `org.springframework.context.annotation.ComponentScan`. Các đoạn chỉ minh họa cấu hình; ví dụ chạy độc lập nằm ở mục 6.

### Package là tên Java, không phải đường dẫn file

Sử dụng `"com.example.shop.orders"`, không viết `"src/main/java/com/example/shop/orders"` hay `"com/example/shop/orders"`. Package trong annotation là tên logic được class khai báo và có mặt trên classpath, không phụ thuộc thư mục gốc của IDE.

Tên package **phân biệt chữ hoa và chữ thường**. Nếu code khai báo `package com.example.shop.orders;` thì chuỗi `"com.example.shop.Orders"` không trỏ vào package đó.

### Quét đệ quy qua package con

Khi chỉ định `"com.example.shop.orders"`, Spring xem cả những candidate dưới:

```text
com.example.shop.orders
com.example.shop.orders.internal
com.example.shop.orders.api
com.example.shop.orders.impl
```

Do đó, một package cha đủ hẹp thường bao phủ các subpackage thuộc cùng feature. **Package cùng cấp** như `com.example.shop.shipping` không được bao phủ nếu chỉ quét `com.example.shop.orders`.

Quét `"com.example.shop"` cũng bao gồm `orders`, `shipping` và `app`. Cách này tiện cho ứng dụng nhỏ, nhưng ở hệ thống lớn có thể đăng ký thêm những component không mong muốn nếu mọi module cùng nằm dưới package đó.

### `value` là alias của `basePackages`

`@ComponentScan` còn có thuộc tính `value()`, là alias của `basePackages()`. Khi chỉ ghi một đối số không tên:

```java
@ComponentScan("com.example.shop.orders")
```

nó có nghĩa tương đương:

```java
@ComponentScan(basePackages = "com.example.shop.orders")
```

Vì `value` và `basePackages` là **hai tên cho cùng một thuộc tính**, không nên đặt chúng thành hai danh sách độc lập hoặc khác nhau trên cùng annotation. Nếu muốn nhiều package, truyền một mảng vào **một** trong hai tên.

### Khi nào dùng `basePackages`?

Phù hợp khi:

- Package cần quét được quy định qua hợp đồng cấu hình hoặc cấu trúc ổn định.
- Muốn mô tả rõ từng tên package trong annotation.
- Cấu hình tích hợp với các vùng package mà project không có marker interface thuận tiện.

Hạn chế chính: tên package là **chuỗi**, nên công cụ refactor/đổi package không phải lúc nào cũng cập nhật chuỗi. Nếu class chuyển từ `com.example.shop.orders` sang `com.example.shop.sales.orders` mà annotation vẫn giữ chuỗi cũ, Spring có thể không tìm được bean mong muốn.

## 3. Ý nghĩa chính xác của `basePackageClasses`

Chữ ký thuộc tính trong `@ComponentScan`:

```java
Class<?>[] basePackageClasses() default {};
```

Với:

```java
@ComponentScan(basePackageClasses = ShippingPackage.class)
```

Spring tìm **package của `ShippingPackage`** và quét package đó cùng các package con. Nếu class marker nằm tại:

```java
package com.example.shop.shipping;

public interface ShippingPackage {
}
```

thì cơ chế có hiệu quả như chỉ định `"com.example.shop.shipping"`, miễn các kiểu đó tồn tại trên classpath. Marker interface **không cần** gắn `@Component`, vì mục đích của nó chỉ là làm mốc package.

Điều quan trọng: `basePackageClasses = ShippingService.class` **không nói rằng Spring chỉ đăng ký riêng `ShippingService`**. Nó yêu cầu quét **toàn bộ package chứa `ShippingService` và các subpackage**, theo điều kiện của scanner.

### Vì sao marker interface hữu ích?

Spring Javadoc gợi ý dùng một class hoặc interface không có hành vi, chuyên làm marker:

```java
package com.example.shop.orders;

/** Điểm neo package cho component scanning. */
public interface OrdersPackage {
}
```

Nếu có hai module feature tách biệt:

```java
@Configuration
@ComponentScan(basePackageClasses = {
    OrdersPackage.class,
    ShippingPackage.class
})
class ApplicationConfig {
}
```

Với import đầy đủ cho `OrdersPackage` và `ShippingPackage`, compiler kiểm tra rằng marker type tồn tại. Khi refactor package và di chuyển marker bằng công cụ IDE, các tham chiếu class có cơ hội được cập nhật/được compiler phát hiện, thay vì để một chuỗi package âm thầm trỏ sai.

Nên đặt marker ở **gốc package muốn quét**, ví dụ `com.example.shop.shipping.ShippingPackage`. Nếu marker vô tình nằm trong `com.example.shop.shipping.internal`, scanner bắt đầu từ `internal` và có thể bỏ sót những component tại `com.example.shop.shipping.api`.

### Có bắt buộc dùng marker riêng không?

Không. Bạn có thể chỉ định bất cứ class hoặc interface nào nằm trong package mục tiêu:

```java
@ComponentScan(basePackageClasses = {
    OrderService.class,
    ShippingService.class
})
```

Điều này hợp lệ nếu hai class đó tồn tại và được import; scanner lấy package của chúng làm mốc. Tuy nhiên, nếu `OrderService` chuyển xuống `orders.impl`, vùng quét có thể vô tình thu hẹp. Một marker đặt cố định ở package gốc thường truyền đạt rõ hơn rằng **đây là ranh giới của một feature**, không phải một class ngẫu nhiên.

### Những điều `basePackageClasses` không làm

- Không tự tạo bean cho marker interface không có stereotype.
- Không tự thêm `@Component` vào mọi class trong package.
- Không "tiêm" các class được liệt kê vào một service; việc tiêm dependency là bước khác.
- Không giới hạn scanner chỉ tới các class xuất hiện trong mảng.
- Không yêu cầu marker là implementation cụ thể; một interface trống cũng hợp lệ.

Nhiều marker ở cùng một package chỉ làm bạn khai báo thừa; thông thường một marker cho mỗi gốc package cần quét là đủ.

## 4. Chọn thuộc tính nào? Có được dùng cùng lúc?

Cả hai thuộc tính **có thể xuất hiện cùng nhau** trên một `@ComponentScan`:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.legacy",
    basePackageClasses = { OrdersPackage.class, ShippingPackage.class }
)
class ApplicationConfig {
}
```

Spring xây danh sách các package nguồn từ **cả hai thuộc tính**, và quét các vùng tương ứng. Hãy hiểu đây là **tập hợp các root package**, không phải điều kiện "package phải vừa trùng chuỗi, vừa chứa marker".

| Tiêu chí | `basePackages` | `basePackageClasses` |
| --- | --- | --- |
| Dạng giá trị | `String[]` | `Class<?>[]` |
| Ví dụ | `"com.example.orders"` | `OrdersPackage.class` |
| Chọn vùng quét | Tên package được chỉ định | Package chứa kiểu mốc |
| Package con | Có | Có |
| Type safety khi đổi cấu trúc source | Phụ thuộc việc cập nhật chuỗi | Compiler/type reference hỗ trợ nhận diện |
| Dễ đọc khi liệt kê package độc lập | Rõ tên trực tiếp | Rõ hơn khi đã có marker |
| Có thể kết hợp với thuộc tính kia | Có | Có |

**Gợi ý lựa chọn:** Với package thuộc codebase bạn kiểm soát, `basePackageClasses` cùng marker interface thường đáng ưu tiên vì ít phụ thuộc vào chuỗi tên package. Với gốc package ổn định, đơn giản và tường minh, `basePackages` cũng hoàn toàn phù hợp. Tránh biến lựa chọn này thành mục tiêu tự thân: điều quan trọng là vùng quét **đủ**, **đúng**, **dễ kiểm thử** và **không quá rộng**.

### Ví dụ nhiều package: ba cách tương đương về vùng quét

Giả sử `OrdersPackage` nằm trong `com.example.orders` và `ShippingPackage` nằm trong `com.example.shipping`:

```java
// Cách 1: toàn chuỗi.
@ComponentScan(basePackages = {
    "com.example.orders", "com.example.shipping"
})

// Cách 2: toàn marker.
@ComponentScan(basePackageClasses = {
    OrdersPackage.class, ShippingPackage.class
})

// Cách 3: phối hợp.
@ComponentScan(
    basePackages = "com.example.orders",
    basePackageClasses = ShippingPackage.class
)
```

Ba đoạn trên là **những phương án annotation riêng biệt**, không phải ba annotation phải đặt nối tiếp vào một class. Khi dùng phương án nào, các gốc package được chọn sẽ quyết định class nào được scanner xem xét, sau đó mới xét stereotype/filter và các điều kiện đăng ký bean khác.

## 5. Mặc định khi không khai báo gốc package

Khi một class cấu hình trong `com.example.shop.app` mang `@ComponentScan` không tham số, Spring quét từ **`com.example.shop.app` và các subpackage**. Nó không tự tìm sibling `com.example.shop.orders`. `@ComponentScan(basePackages={})` cũng dùng package mặc định khi không có root khác. Với dự án chứa nhiều feature, nên đặt configuration tại gốc phù hợp hoặc chọn roots tường minh qua chuỗi/marker. Tránh class cấu hình ở default package Java vì scan có thể quá rộng.

## 6. Ví dụ runnable Java 17: kết hợp hai thuộc tính

Ví dụ này dùng Spring Framework 6.2, không phụ thuộc Spring Boot. Ta cố ý đặt cấu hình trong `demo.app.config`, còn hai `@Service` ở hai package anh em. Cấu hình sử dụng:

- `basePackages = "demo.orders"` để tìm `OrderService`;
- `basePackageClasses = ShippingPackage.class` để tìm `ShippingService` trong `demo.shipping`.

### 6.1. Cấu trúc dự án

```text
component-scan-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        ├── app/
        │   ├── Main.java
        │   └── config/
        │       └── AppConfig.java
        ├── orders/
        │   └── OrderService.java
        └── shipping/
            ├── ShippingPackage.java
            └── ShippingService.java
```

### 6.2. Maven POM

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>component-scan-demo</artifactId>
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

### 6.3. Class cấu hình

Tệp `src/main/java/demo/app/config/AppConfig.java`:

```java
package demo.app.config;

import demo.shipping.ShippingPackage;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackages = "demo.orders",
        basePackageClasses = ShippingPackage.class
)
public class AppConfig {
}
```

Class `AppConfig` không phải là một service trong hai package cần scan. Nó được **đăng ký tường minh** khi tạo context ở `Main`. Annotation `@ComponentScan` mới chỉ định vùng để tìm các component còn lại.

### 6.4. Service thứ nhất được tìm bằng `basePackages`

Tệp `src/main/java/demo/orders/OrderService.java`:

```java
package demo.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String label() {
        return "orders";
    }
}
```

Vì `demo.orders` là gốc package được chỉ định bằng chuỗi, scanner tìm được `OrderService` gắn `@Service`. `@Service` là stereotype của Spring và được component scan nhận diện theo cấu hình mặc định.

### 6.5. Marker và service thứ hai được tìm bằng `basePackageClasses`

Tệp `src/main/java/demo/shipping/ShippingPackage.java`:

```java
package demo.shipping;

/** Marker xác định gốc package shipping cho @ComponentScan. */
public interface ShippingPackage {
}
```

Tệp `src/main/java/demo/shipping/ShippingService.java`:

```java
package demo.shipping;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {
    public String label() {
        return "shipping";
    }
}
```

`ShippingPackage` là interface trống, không mang `@Component` và không trở thành bean service chỉ vì được dùng trong `basePackageClasses`. Điều quan trọng là interface này nằm trong `demo.shipping`; Spring từ đó tìm `ShippingService` đã mang stereotype `@Service`.

### 6.6. Main class và kết quả

Tệp `src/main/java/demo/app/Main.java`:

```java
package demo.app;

import demo.app.config.AppConfig;
import demo.orders.OrderService;
import demo.shipping.ShippingService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orders = context.getBean(OrderService.class);
            ShippingService shipping = context.getBean(ShippingService.class);

            System.out.println("orders=" + orders.label());
            System.out.println("shipping=" + shipping.label());
            System.out.println("markerBean=" +
                    context.containsBean("shippingPackage"));
        }
    }
}
```

Từ thư mục chứa `pom.xml`, chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.app.Main
```

Các dòng do chương trình in ra (không tính logging của môi trường Maven/Spring):

```text
orders=orders
shipping=shipping
markerBean=false
```

**Vì sao output chính xác?**

1. `AppConfig` được truyền vào `AnnotationConfigApplicationContext`, nên không cần scanner tự phát hiện nó.
2. `@ComponentScan(basePackages = "demo.orders")` bao phủ `OrderService`.
3. `@ComponentScan(basePackageClasses = ShippingPackage.class)` lấy package `demo.shipping` làm gốc, nên bao phủ `ShippingService`.
4. `context.getBean(OrderService.class)` và `context.getBean(ShippingService.class)` đều thành công vì có bean đúng kiểu.
5. Marker interface không có stereotype và không có bean definition tường minh nên `containsBean("shippingPackage")` là `false`.

Bạn có thể thay hoàn toàn `AppConfig` bằng phương án marker cho cả hai package nếu tạo thêm `OrdersPackage` trong `demo.orders`:

```java
// Phương án minh họa, cần khai báo interface OrdersPackage
// nằm trong demo.orders, và import cả hai marker.
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = {
        OrdersPackage.class, ShippingPackage.class
})
public class AppConfig {
}
```

Hoặc thay bằng mảng chuỗi:

```java
// Phương án minh họa khác, thay thế AppConfig ở ví dụ:
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = {
        "demo.orders", "demo.shipping"
})
public class AppConfig {
}
```

Các phương án này có cùng ý định chọn **hai gốc package**; không dùng cùng lúc nhiều class `AppConfig` trùng tên trong một project.

## 7. Nếu bỏ một thuộc tính thì chuyện gì xảy ra?

Thử sửa `AppConfig` để chỉ còn:

```java
@ComponentScan(basePackages = "demo.orders")
```

Khi đó scanner không tìm `ShippingService` ở `demo.shipping`, trừ khi bạn đăng ký nó bằng cơ chế khác. Nếu vẫn chạy `Main` như cũ, lời gọi:

```java
context.getBean(ShippingService.class);
```

sẽ không tìm được bean tương ứng và gây `NoSuchBeanDefinitionException`. Đây là hành vi mong đợi: component nằm ngoài vùng quét. Nó không có nghĩa Spring không hiểu `@Service` hoặc Java class không tồn tại.

Ngược lại, nếu chỉ có:

```java
@ComponentScan(basePackageClasses = ShippingPackage.class)
```

`OrderService` nằm ngoài gốc `demo.shipping`; vì vậy `getBean(OrderService.class)` thất bại nếu bean không được đăng ký bằng đường khác.

Thử nghiệm này cho thấy hai thuộc tính **bổ sung vùng quét**. Khi cùng xuất hiện, cả hai tập package được xét; khi bỏ một bên, vùng quét tương ứng biến mất.

### Kiểm tra chỉ bằng BeanFactory

Nếu muốn quan sát bean đã đăng ký nhưng không muốn để `getBean` ném lỗi:

```java
// Đoạn minh họa trong main/context đã tạo:
boolean hasOrders = context.containsBean("orderService");
boolean hasShipping = context.containsBean("shippingService");
```

Với `@Service` không ghi tên cụ thể, Spring thường dùng bean name mặc định theo class đơn giản đã chuyển chữ đầu thành thường: `orderService` và `shippingService`. Nhưng tên có thể khác khi dùng `@Service("customName")` hoặc `BeanNameGenerator` tùy chỉnh. Vì vậy khi kiểm tra ứng viên theo kiểu, `getBeanNamesForType` hoặc `getBeansOfType` thường phản ánh mục tiêu rõ hơn:

```java
// Đoạn minh họa: dùng khi context còn mở.
String[] shippingNames =
        context.getBeanNamesForType(ShippingService.class);
```

Khi không tìm thấy bean, mảng có thể rỗng. **Đừng chỉ dựa vào tên** nếu mục tiêu là xác nhận class đúng kiểu đã được đăng ký.

## 8. Scanner phát hiện class nào?

`basePackages` và `basePackageClasses` chỉ quyết định **nơi tìm**, không buộc mọi class trở thành bean. Với `useDefaultFilters=true`, Spring xét stereotype `@Component`, `@Service`, `@Repository`, `@Controller` và composed stereotypes trên concrete, independent classes. Marker interface không mang stereotype chỉ là mốc package.

Khi thiếu bean, kiểm tra runtime classpath, filters, `@Profile`/`@Conditional`, dependency, lỗi bean name và context đang dùng. Bean ngoài vùng scan vẫn có thể xuất hiện qua `@Bean`/`@Import`. Tắt `useDefaultFilters` yêu cầu bổ sung include filter rõ ràng; chỉ gắn `@Service` không còn đủ để được scanner chọn.

## 9. Quét vừa đủ: tránh quá hẹp hoặc quá rộng

Nếu module checkout có các nhánh `com.company.checkout.api`, `application`, `domain`, `infrastructure`, marker ở `com.company.checkout` sẽ bao phủ toàn bộ feature. Marker đặt sâu dưới `...checkout.application.internal` lại bỏ các package ngang cấp; scan từ `com.company` có thể kéo vào nhiều module không liên quan.

Chọn **root package đủ rộng cho dependency hợp lệ và đủ hẹp cho đúng phạm vi module**. Trong multi-project Gradle/JAR, scanner vẫn đọc Java packages trên runtime classpath, không đọc tên Gradle module để thiết lập ranh giới. Khi library công bố một adapter trong số nhiều component nội bộ, explicit `@Import`/`@Bean` có thể diễn đạt lựa chọn rõ hơn một package scan rộng.

## 10. Những chi tiết quan trọng về refactor và module

### Khi đổi package trong IDE

Với chuỗi:

```java
@ComponentScan(basePackages = "com.company.oldname")
```

nếu package được đổi thành `com.company.newname` mà annotation chưa cập nhật, mã vẫn **biên dịch** vì chuỗi bất kỳ đều hợp lệ về cú pháp Java. Vấn đề chỉ lộ khi context chạy và bean mong muốn thiếu.

Với marker:

```java
@ComponentScan(basePackageClasses = NewModulePackage.class)
```

compiler kiểm tra tham chiếu `NewModulePackage`. Nếu marker di chuyển và import chưa được sửa, mã sẽ lỗi biên dịch. Nếu marker được chuyển cùng package và import được cập nhật, scanner theo package mới. Đây là lợi thế "type-safe" của cách khai báo này — dù nó **không** tự bảo đảm mọi bean cần thiết nằm trong vùng mới.

### Tách package qua nhiều module/JAR

Nếu `OrdersPackage` ở module phụ thuộc, `basePackageClasses = OrdersPackage.class` chỉ làm mốc khi type đó **có mặt trên classpath** của ứng dụng. Việc quét package sẽ tìm các candidate trong classpath theo cơ chế Spring; nó **không tự thêm dependency Maven/Gradle** tới module chứa class hoặc tự tải JAR từ network.

Vì vậy, với dự án đa module, cần cả:

1. Runtime/build dependency đúng để các class có trên classpath.
2. Cấu hình scan đúng package.
3. Điều kiện để các class thực sự là component ứng viên.

Nếu marker đã import được mà một implementation nằm trong module chưa đưa lên runtime classpath, việc quét vẫn không thể phát hiện implementation đó.

### Đặt marker ở đâu?

Một convention đơn giản:

```text
com.company.module.orders
├── OrdersPackage.java       <-- marker, không @Component
├── api/...
├── application/...
└── infrastructure/...
```

Marker ít thay đổi, nằm ở package cha chung và có tên thể hiện ý định. Không đặt marker trong package `impl` chỉ vì ở đó hiện có một service, trừ khi chỉ muốn quét đúng package đó.

## 11. Lưu ý khi sử dụng Spring Boot

Spring Boot đã tích hợp component scan vào `@SpringBootApplication`. Để tùy chỉnh gốc, dùng tên thuộc tính riêng:

| `@ComponentScan` | `@SpringBootApplication` | Mốc lựa chọn |
| --- | --- | --- |
| `basePackages` | `scanBasePackages` | Chuỗi package |
| `basePackageClasses` | `scanBasePackageClasses` | Marker type |

```java
@SpringBootApplication(scanBasePackageClasses = {
    OrdersPackage.class, ShippingPackage.class
})
public class ShopApplication { }
```

Snippet cần imports, marker types và dependency Boot. Khi không tùy chỉnh, Spring Boot thường quét package chứa class ứng dụng và các subpackage. **`scanBasePackages` không đổi phạm vi JPA entity scanning hay Spring Data repository scanning**: cần kiểm tra `@EntityScan`, `@EnableJpaRepositories` hoặc cơ chế tương ứng khi dùng các công nghệ đó. Việc thêm `@ComponentScan` trực tiếp lên class Boot có thể thay đổi composed scan filters mặc định; với nhu cầu đổi root đơn giản, dùng thuộc tính sẵn có của `@SpringBootApplication`.

## 12. Những lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho service có `@Service` | Service nằm ngoài package gốc | Xác minh package và mở rộng `basePackages`/`basePackageClasses` có chủ đích |
| Context khởi tạo thất bại với `UnsatisfiedDependencyException` | Một bean phụ thuộc vào service chưa được đăng ký, hoặc dependency nội bộ của service bị thiếu | Đọc exception chain, xác định **bean nào** thực sự thiếu |
| Chỉ quét được package shipping, thiếu orders | Chỉ khai báo marker trong shipping | Thêm gốc orders bằng chuỗi hoặc marker tương ứng |
| Dùng `basePackageClasses = SomeService.class` nhưng thiếu class cùng feature | `SomeService` nằm trong subpackage hẹp | Đặt marker ở gốc feature |
| Dùng `"src/main/java/..."` | Dùng đường dẫn thay vì tên Java package | Đổi thành `"com.example...."` |
| Refactor package xong mất bean dù vẫn biên dịch | Chuỗi `basePackages` cũ | Cập nhật chuỗi hoặc dùng marker type |
| Marker không được tạo thành bean | Marker interface không có stereotype | Đây là chủ đích; marker chỉ định package quét, không tự là component |
| Có nhiều bean cùng interface hơn dự kiến | Root scan quá rộng, quét cả module ngoài phạm vi | Thu hẹp gốc, điều chỉnh cấu trúc/qualifier thích hợp |
| Bị xung đột bean name | Hai component cùng tên bean sau khi quét rộng | Đặt tên rõ ràng, xử lý cấu hình/module, không chỉ bỏ qua lỗi |
| Không tìm thấy entity/repository JPA trong Boot | Nhầm component scan với entity/repository scan | Cấu hình cơ chế scan riêng phù hợp từng công nghệ |
| Không thấy bean dù package đúng | Thiếu runtime JAR, thiếu stereotype, exclude filter, condition | Kiểm tra classpath và metadata component |
| Scan thay đổi khi di chuyển class cấu hình | Dựa vào gốc scan mặc định | Đặt `@ComponentScan` tại package gốc ổn định hoặc chỉ định root rõ ràng |

### Quy trình debug ngắn

1. Xác định **tên package thật** từ dòng `package ...;` trong file Java.
2. Xác định **class khai báo `@ComponentScan` có được đưa vào ApplicationContext** không.
3. Tính các root scan: từ `basePackages`, package của từng type trong `basePackageClasses`, hoặc mặc định package của config nếu không chỉ định.
4. Kiểm tra service có thuộc đúng root/subpackage nào không.
5. Kiểm tra class có stereotype và được đưa lên runtime classpath không.
6. Nếu vẫn thất bại, đọc exception gốc và kiểm tra filter, condition, dependency của bean và xung đột tên.

Để chẩn đoán sâu, có thể bật log mức DEBUG cho các package của Spring context/scanner trong môi trường phát triển. Tránh đọc một thông điệp "không tìm được bean" như bằng chứng duy nhất rằng package scan sai: dependency bên trong class hoặc điều kiện đăng ký cũng có thể là nguyên nhân.

## 13. Thực hành và tự kiểm tra

### Bài 1 — Mặc định quét ở đâu?

`AppConfig` nằm ở `com.example.shop.app` và có:

```java
@Configuration
@ComponentScan
class AppConfig { }
```

`OrderService` ở `com.example.shop.orders`. Nó có được tìm thấy chỉ nhờ `@ComponentScan` này không?

**Đáp án:** Không, vì `orders` là package anh em với `app`. Gốc mặc định là `com.example.shop.app` và các package con của nó. Muốn quét `orders`, cần chuyển gốc scan thích hợp hoặc khai báo package này.

### Bài 2 — Marker có được đưa thành bean?

`ShippingPackage` là interface trống ở `demo.shipping`, không có stereotype. `@ComponentScan(basePackageClasses = ShippingPackage.class)` có tạo bean tên `shippingPackage` không?

**Đáp án:** Không. Annotation lấy **package của marker** làm mốc quét; marker không trở thành component chỉ vì được tham chiếu ở thuộc tính đó.

### Bài 3 — Kết hợp hai thuộc tính

`@ComponentScan(basePackages = "demo.orders", basePackageClasses = ShippingPackage.class)` quét những vùng nào, nếu `ShippingPackage` nằm trong `demo.shipping`?

**Đáp án:** `demo.orders`, `demo.shipping` và các package con của từng vùng. Không cần service nằm trong **cả hai** package.

### Bài 4 — Thay marker bằng implementation con

Nếu đổi `basePackageClasses = ShippingPackage.class` thành `basePackageClasses = InternalShippingService.class`, nhưng `InternalShippingService` thuộc `demo.shipping.internal`, vùng quét còn tìm `demo.shipping.ShippingService` không?

**Đáp án:** Không chỉ từ cấu hình này, vì gốc mới bị thu hẹp xuống `demo.shipping.internal`. Nếu có một gốc scan khác bao phủ `demo.shipping` thì có thể vẫn thấy bean. Để ổn định, đặt marker tại đúng package gốc.

### Bài 5 — Boot và JPA repository

Có `@SpringBootApplication(scanBasePackages = "com.example.orders")` nhưng entity hoặc repository Spring Data ở một vùng khác vẫn không được phát hiện. Có thể chỉ thêm package vào `scanBasePackages` để bảo đảm entity và repositories được quét không?

**Đáp án:** Không. Thuộc tính đó ánh xạ vào `@ComponentScan`; phạm vi quét entity và Spring Data repository có cơ chế riêng. Cần kiểm tra cấu hình tương ứng như `@EntityScan` và `@Enable...Repositories`.

### Bài 6 — Chọn phương án dễ refactor

Một project có module `com.company.checkout` chứa nhiều subpackage và bạn sở hữu toàn bộ source. Nên dùng `@ComponentScan(basePackages = "com.company.checkout")` hay marker `CheckoutPackage.class`?

**Đáp án:** Cả hai hợp lệ. Marker tại gốc module hữu ích khi refactor vì tham chiếu class được compiler kiểm tra và IDE thường hỗ trợ di chuyển package. Nếu dùng chuỗi, cần bảo đảm test cập nhật phạm vi khi đổi package.

## 14. Checklist cấu hình thực tế

Trước khi hoàn tất thay đổi `@ComponentScan`, hãy kiểm tra:

- Đã xác định đúng **root package** tương ứng với module/feature muốn quét.
- `basePackages` là tên Java package hợp lệ về mặt dự án, không phải path filesystem.
- Marker của `basePackageClasses` nằm trong **package cha đúng mong muốn**.
- Khi cần nhiều package, đã khai báo đủ các root hoặc root cha thích hợp.
- Không vô tình quét cả các module/test component không thuộc ứng dụng.
- Các class cần dùng có stereotype và có trên runtime classpath.
- Class `@Configuration` được đăng ký/import vào container.
- Nếu ứng dụng Boot, sử dụng tên thuộc tính tương ứng và không nhầm component scan với JPA/repository scan.
- Có integration test hoặc một lần tạo `AnnotationConfigApplicationContext` xác minh bean cốt lõi thực sự có mặt.

## Ghi nhớ

**`basePackages` chọn bằng chuỗi; `basePackageClasses` chọn bằng type làm mốc.** Cả hai đều cấu hình vùng package cho `@ComponentScan` và có thể dùng kết hợp. `basePackageClasses` lấy **package chứa class/interface**, không chỉ quét class đó và không tự biến marker thành bean. Nếu không khai báo root, Spring lấy package của class mang `@ComponentScan` làm gốc.

Một cấu hình tốt chọn đúng module, bao phủ đủ package con, tránh root quá rộng và có kiểm chứng bean thực sự được đăng ký. Khi source thường xuyên refactor, marker interface đặt tại gốc feature là lựa chọn đáng cân nhắc.

## Tài liệu chính thức

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): cách bật component scanning và các stereotype được nhận diện.
- [Spring Framework 6.2 — `@ComponentScan` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html): `basePackages`, `basePackageClasses`, alias `value` và mặc định package.
- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): `@Configuration`, `@Bean` và `AnnotationConfigApplicationContext`.
- [Spring Boot — `@SpringBootApplication` Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html): `scanBasePackages`/`scanBasePackageClasses` và phạm vi áp dụng của chúng.
