# Chia cấu hình theo ranh giới chức năng trong Spring Core Container

## 1. Vì sao cần chia cấu hình?

Một ứng dụng Spring nhỏ có thể khởi đầu bằng một class `@Configuration` chứa tất cả phương thức `@Bean`. Nhưng khi ứng dụng phát triển, một file cấu hình lớn thường trộn lẫn các trách nhiệm:

- Cấu hình lưu trữ: `DataSource`, repository, transaction infrastructure hoặc adapter dữ liệu.
- Cấu hình tính giá: discount policy, tax calculator và quy tắc nghiệp vụ.
- Cấu hình thanh toán: client của cổng thanh toán, retry policy và credential provider.
- Cấu hình checkout: use case kết hợp các phụ thuộc.
- Cấu hình giao tiếp: HTTP client, serialization và event publisher.

Nếu tất cả đặt trong một class `ApplicationConfig` dài hàng trăm hoặc hàng nghìn dòng, người đọc khó biết **bean nào thuộc chức năng nào, module nào phụ thuộc module nào, cấu hình nào cần cho test hoặc một môi trường triển khai cụ thể**.

Giải pháp là **chia cấu hình theo ranh giới chức năng**: mỗi nhóm bean được khai báo gần với trách nhiệm mà nó phục vụ, rồi một **composition root** ghép chúng thành application context. Trong Java configuration, `@Configuration`, `@Bean` và đặc biệt `@Import` cung cấp cơ chế trực tiếp cho cách làm này. Đây là bài về **ghép cấu hình** trong Spring Core Container, không phải quy định rằng mỗi module nhất thiết phải là microservice hoặc mỗi package phải có một container riêng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện ranh giới cấu hình theo **capability/use case**, thay vì gom ngẫu nhiên theo loại annotation hoặc tiện ích.
2. Viết nhiều class `@Configuration` chuyên trách và sử dụng `@Import` để ghép chúng từ một điểm khởi động.
3. Nối dependency **xuyên cấu hình** bằng tham số `@Bean` để Spring resolve bean theo type, qualifier và scope.
4. Phân biệt `@Import`, `@ComponentScan`, `@Bean`, `@Profile` và `@Conditional`: mỗi công cụ đảm nhiệm một phần khác nhau.
5. Chọn điểm sở hữu bean hợp lý, tránh trùng tên, trùng kiểu, vòng phụ thuộc và việc khởi tạo tài nguyên lặp lại.
6. Thiết kế module dễ thay implementation và viết integration test theo phạm vi chức năng.
7. Chạy một ví dụ Java 17+ có các module **Storage**, **Pricing**, **Checkout**, được ghép mà **không cần component scanning**.

## 2. “Ranh giới chức năng” nghĩa là gì?

Ranh giới chức năng là nơi một nhóm cấu hình và bean phục vụ một **trách nhiệm tương đối độc lập**, có hợp đồng rõ với phần còn lại của hệ thống. Ví dụ:

| Ranh giới | Trách nhiệm | Bean tiêu biểu | Phụ thuộc công khai cần thiết |
| --- | --- | --- | --- |
| Storage | Lưu và tìm đơn hàng | `OrderStore`, adapter JDBC/in-memory | DataSource hoặc cấu hình storage |
| Pricing | Tính giá, khuyến mại | `DiscountPolicy` | Các chính sách giá, cấu hình tỷ lệ |
| Checkout | Điều phối việc đặt hàng | `CheckoutService` | `OrderStore` và `DiscountPolicy` |
| Integration | Kết nối dịch vụ bên ngoài | SDK client, timeout/retry | Settings và credentials |
| Delivery/Web | Chuyển HTTP request thành use case | Controller, message mapper | `CheckoutService` |

Một ranh giới hợp lý nên có:

- **Cohesion cao:** bean trong cùng nhóm phục vụ mục tiêu gần nhau.
- **Dependency direction rõ:** checkout có thể cần pricing và storage; pricing thường không cần biết checkout controller.
- **Hợp đồng ổn định:** module khác sử dụng interface hoặc public service thay vì cấu trúc bên trong.
- **Ownership nhất quán:** nhóm nào tạo bean, nhóm đó có trách nhiệm cấu hình scope/lifecycle phù hợp.
- **Khả năng bật/tắt/thay thế có chủ ý:** một adapter có thể đổi trong test mà không phải sửa hàng loạt cấu hình không liên quan.

Không có quy tắc “mỗi class một configuration” hay “mỗi module đúng một configuration”. Tách theo trách nhiệm thực sự, tránh cả **God Configuration** lẫn quá nhiều file không mang thêm ý nghĩa.

### Hai cách tổ chức package thường gặp

**Theo tầng kỹ thuật:**

```text
com.example
├── config
│   ├── DataConfig.java
│   ├── ServiceConfig.java
│   └── WebConfig.java
├── controller
├── service
└── repository
```

Cách này có thể tốt cho dự án nhỏ, nhưng khi nhiều chức năng khác nhau cùng chia sẻ một tầng, thay đổi một feature có thể kéo theo chỉnh sửa nhiều nơi.

**Theo chức năng/capability:**

```text
com.example
├── checkout
│   ├── CheckoutService.java
│   └── CheckoutConfiguration.java
├── pricing
│   ├── DiscountPolicy.java
│   └── PricingConfiguration.java
├── storage
│   ├── OrderStore.java
│   └── StorageConfiguration.java
└── bootstrap
    ├── ApplicationConfiguration.java
    └── Application.java
```

Đây là một phương án rõ ownership hơn khi các chức năng phát triển độc lập. Trong hệ thống lớn, có thể tiếp tục tách **API hợp đồng** khỏi implementation/infrastructure trong từng chức năng. Đừng cứng nhắc: lựa chọn phụ thuộc kích thước đội ngũ, hướng dependency, khả năng test và ranh giới triển khai thực tế.

## 3. Cơ chế Spring giúp ghép nhiều cấu hình

### 3.1. @Configuration mô tả một nhóm bean definitions

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PricingConfiguration {

    @Bean
    DiscountPolicy discountPolicy() {
        return new TenPercentDiscountPolicy();
    }
}
```

Đây là snippet minh họa, cần định nghĩa `DiscountPolicy` và `TenPercentDiscountPolicy` như ví dụ hoàn chỉnh ở phần sau. `@Configuration` cho Spring biết class chứa cấu hình; method `@Bean` đăng ký một bean definition. Khi context được dựng, Spring có thể tạo bean `discountPolicy` để inject vào các chức năng khác.

`proxyBeanMethods=false` phù hợp ở đây vì các factory methods độc lập, không cần gọi trực tiếp một `@Bean` method khác. **Nó không tắt dependency injection**: tham số của factory method vẫn được Spring giải quyết bình thường.

### 3.2. @Import ghép cấu hình theo danh sách tường minh

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import({
    StorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
public class ApplicationConfiguration {
}
```

Các class trong mảng phải có thật và được import đúng package. Đây là sơ đồ cấu hình sẽ xuất hiện trong ví dụ chạy được.

Khi `ApplicationConfiguration` được đăng ký vào `AnnotationConfigApplicationContext`, Spring xử lý `@Import` và các cấu hình được import. Các `@Bean` methods của chúng trở thành bean definitions trong **cùng ApplicationContext**, cho phép dependency injection xuyên ranh giới.

**Điểm quan trọng:** `@Import` không có nghĩa “nhúng source code Java”, không phải `new StorageConfiguration()` và không tự tạo context con. Nó là metadata để Spring nạp thêm các nguồn cấu hình/type vào context.

Tài liệu Spring còn cho phép `@Import` tham chiếu một số class component thông thường, `ImportSelector` hay `ImportBeanDefinitionRegistrar` trong các tình huống nâng cao. Trong bài này, dùng các class `@Configuration` tường minh là cách dễ học và dễ kiểm soát nhất.

### 3.3. Tham số @Bean nối dependency xuyên cấu hình

```java
@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {
    @Bean
    CheckoutService checkoutService(
            OrderStore orderStore,
            DiscountPolicy discountPolicy) {
        return new CheckoutService(orderStore, discountPolicy);
    }
}
```

`CheckoutService`, `OrderStore` và `DiscountPolicy` là các kiểu trong ví dụ hoàn chỉnh. Spring giải quyết hai tham số từ bean definitions đã được đăng ký, dù chúng do **các configuration class khác** khai báo.

Đây là điểm mấu chốt của ghép cấu hình: **module checkout biết hợp đồng mà nó cần, không nhất thiết biết class cấu hình nào đã tạo implementation**.

Đừng thay cách này bằng:

```java
@Bean
CheckoutService checkoutService() {
    return new CheckoutService(
            new StorageConfiguration().orderStore(),
            new PricingConfiguration().discountPolicy()
    );
}
```

Đoạn phản ví dụ giả định truy cập các factory methods được phép ở package tương ứng. Tự `new` các configuration class và gọi trực tiếp factory methods có thể tạo object ngoài container, bỏ qua scope, lifecycle, proxies và sự thay thế bean trong test. Khi dùng `@Configuration(proxyBeanMethods=false)`, lời gọi chéo `@Bean` cũng mang semantics Java trực tiếp, không phải container lookup.

## 4. Vai trò của composition root

**Composition root** là nơi ứng dụng quyết định **những cấu hình/module nào cùng có mặt** trong một deployment. Thông thường là một hoặc một vài class gần entry point:

```text
                 ApplicationConfiguration
                       @Import
                      /   |   \
                     v    v    v
          StorageConfig PricingConfig CheckoutConfig
                |           |           |
                v           v           v
             OrderStore DiscountPolicy CheckoutService
                \           /
                 \         /
                  \       v
                    CheckoutService
```

Sơ đồ mô tả import ở lớp trên và dependency thật ở lớp dưới. `CheckoutService` nhận các hợp đồng do modules khác cung cấp; container không tự tạo dependency chỉ vì hai configuration cùng được import.

### Vì sao composition root hữu ích?

- **Một điểm quyết định thành phần ứng dụng:** startup không phải nhớ đăng ký thủ công hàng chục class cấu hình rời rạc.
- **Có thể cấu hình môi trường khác nhau:** test import storage in-memory; production import JDBC storage.
- **Dependency graph quan sát được:** composition root bộc lộ module nào tạo nên ứng dụng.
- **Ít scan ngoài ý muốn:** explicit import cho phép lựa chọn chính xác nhóm cấu hình được nạp.
- **Ranh giới trách nhiệm rõ:** pricing không cần tự import checkout để hoạt động; bootstrap làm nhiệm vụ ghép.

**Không nhầm:** `ApplicationContext` vẫn là **một** container trong ví dụ. Nhiều `@Configuration` không đồng nghĩa nhiều container hoặc nhiều singleton cache tách biệt. Scope singleton thông thường áp dụng trong context chung mà các definitions được ghép vào.

## 5. Ví dụ Java 17+ hoàn chỉnh: Storage + Pricing + Checkout

Ví dụ sau sử dụng **Spring Framework 6.2.19**, **Java 17+**, **Gradle** và `AnnotationConfigApplicationContext`. Ta cố ý không dùng `@ComponentScan` để nhìn rõ cơ chế **`@Import` + `@Bean` + parameter injection**.

Chương trình lưu dữ liệu giả lập trong bộ nhớ, tính giảm giá 10% bằng số nguyên và in kết quả xác định. Không cần database, web server, Spring Boot hoặc network.

### 5.1. Cấu trúc thư mục

```text
modular-config-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── App.java
    ├── config/
    │   ├── ApplicationConfiguration.java
    │   ├── StorageConfiguration.java
    │   ├── PricingConfiguration.java
    │   └── CheckoutConfiguration.java
    ├── storage/
    │   ├── OrderStore.java
    │   └── InMemoryOrderStore.java
    ├── pricing/
    │   ├── DiscountPolicy.java
    │   └── TenPercentDiscountPolicy.java
    └── checkout/
        └── CheckoutService.java
```

Có **10 file Java**: một entry point, bốn configuration classes và năm class/interface triển khai hợp đồng. Mỗi file public top-level type đặt đúng tên và package tương ứng.

### 5.2. Cấu hình Gradle

**`settings.gradle`**

```groovy
rootProject.name = 'modular-config-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
```

Spring Framework 6.2.x hỗ trợ Java 17+. Dependency `spring-context` đem vào các thư viện Spring Core/Beans cần thiết qua Maven metadata. Không cần thêm `spring-boot-starter` để chạy demo IoC Container thuần.

### 5.3. Module Storage: hợp đồng và implementation

**`src/main/java/demo/storage/OrderStore.java`**

```java
package demo.storage;

public interface OrderStore {
    String save(String orderId, long chargedTotal);
    int count();
}
```

`OrderStore` là hợp đồng được Checkout sử dụng. Ứng dụng thực tế có thể thiết kế API domain phong phú hơn, nhưng demo chỉ cần lưu một record và đếm số lần ghi.

**`src/main/java/demo/storage/InMemoryOrderStore.java`**

```java
package demo.storage;

import java.util.concurrent.atomic.AtomicInteger;

public final class InMemoryOrderStore implements OrderStore {
    private final AtomicInteger writes = new AtomicInteger();

    @Override
    public String save(String orderId, long chargedTotal) {
        writes.incrementAndGet();
        return orderId + ":" + chargedTotal;
    }

    @Override
    public int count() {
        return writes.get();
    }
}
```

Implementation không có `@Component`. Chính `StorageConfiguration` sẽ chủ động đăng ký nó. `AtomicInteger` giúp bộ đếm an toàn trước việc tăng đồng thời, mặc dù demo chỉ chạy một thread. Đây là in-memory fake dùng để học cấu hình, **không phải persistence bền vững**.

### 5.4. Module Pricing: quy tắc tính giá

**`src/main/java/demo/pricing/DiscountPolicy.java`**

```java
package demo.pricing;

public interface DiscountPolicy {
    long discountedTotal(long baseTotal);
}
```

**`src/main/java/demo/pricing/TenPercentDiscountPolicy.java`**

```java
package demo.pricing;

public final class TenPercentDiscountPolicy implements DiscountPolicy {
    @Override
    public long discountedTotal(long baseTotal) {
        if (baseTotal < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return baseTotal - (baseTotal / 10);
    }
}
```

Đây là chính sách demo tính bằng `long`. Với 100, kết quả 90; với 50, kết quả 45. Ứng dụng tiền tệ thật nên định nghĩa đơn vị nhỏ nhất, rounding policy, overflow handling và dùng `BigDecimal` khi bài toán đòi hỏi, thay vì coi phép chia nguyên này là chuẩn nghiệp vụ phổ quát.

### 5.5. Module Checkout: chỉ phụ thuộc interface

**`src/main/java/demo/checkout/CheckoutService.java`**

```java
package demo.checkout;

import demo.pricing.DiscountPolicy;
import demo.storage.OrderStore;

import java.util.Objects;

public final class CheckoutService {
    private final OrderStore store;
    private final DiscountPolicy discounts;

    public CheckoutService(OrderStore store, DiscountPolicy discounts) {
        this.store = Objects.requireNonNull(store);
        this.discounts = Objects.requireNonNull(discounts);
    }

    public String checkout(String orderId, long baseTotal) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("blank order id");
        }
        long charged = discounts.discountedTotal(baseTotal);
        return store.save(orderId, charged);
    }
}
```

Checkout không import `StorageConfiguration`, `PricingConfiguration` hoặc các implementation cụ thể; nó chỉ dùng `OrderStore` và `DiscountPolicy`. Nhờ vậy, test nghiệp vụ có thể truyền fake vào constructor mà **không cần Spring**.

### 5.6. Ba configuration classes chuyên trách

**`src/main/java/demo/config/StorageConfiguration.java`**

```java
package demo.config;

import demo.storage.InMemoryOrderStore;
import demo.storage.OrderStore;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {
    @Bean
    OrderStore orderStore() {
        return new InMemoryOrderStore();
    }
}
```

**`src/main/java/demo/config/PricingConfiguration.java`**

```java
package demo.config;

import demo.pricing.DiscountPolicy;
import demo.pricing.TenPercentDiscountPolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PricingConfiguration {
    @Bean
    DiscountPolicy discountPolicy() {
        return new TenPercentDiscountPolicy();
    }
}
```

**`src/main/java/demo/config/CheckoutConfiguration.java`**

```java
package demo.config;

import demo.checkout.CheckoutService;
import demo.pricing.DiscountPolicy;
import demo.storage.OrderStore;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {
    @Bean
    CheckoutService checkoutService(
            OrderStore orderStore,
            DiscountPolicy discountPolicy) {
        return new CheckoutService(orderStore, discountPolicy);
    }
}
```

Điểm đáng chú ý: ba configuration class có trách nhiệm riêng. `CheckoutConfiguration` **không khởi tạo một repository hay discount policy thứ hai**. Spring sẽ resolve cả hai parameter từ container.

Trong các module có nhiều implementation `OrderStore` hoặc `DiscountPolicy`, cần khai báo qualifier hoặc `@Primary` phù hợp. Bài demo chỉ có một bean cho mỗi interface để luồng khởi đầu dễ kiểm chứng.

### 5.7. Composition root dùng @Import

**`src/main/java/demo/config/ApplicationConfiguration.java`**

```java
package demo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import({
    StorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
public class ApplicationConfiguration {
}
```

Đây là file quyết định ba ranh giới sẽ được ghép trong ứng dụng. Không cần `@ComponentScan`. Không cần ghi `@Import` trong từng module để import qua lại thành vòng.

Đặt entry point chỉ phụ thuộc `ApplicationConfiguration` là cách biểu đạt composition root rõ ràng.

### 5.8. Entry point

**`src/main/java/demo/App.java`**

```java
package demo;

import demo.checkout.CheckoutService;
import demo.config.ApplicationConfiguration;
import demo.storage.OrderStore;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class App {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        ApplicationConfiguration.class)) {

            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            OrderStore store =
                    context.getBean(OrderStore.class);

            System.out.println("store-bean="
                    + context.containsBean("orderStore"));
            System.out.println("discount-bean="
                    + context.containsBean("discountPolicy"));

            System.out.println("checkout1="
                    + checkout.checkout("ORDER-7", 100));
            System.out.println("checkout2="
                    + checkout.checkout("ORDER-8", 50));

            System.out.println("writes=" + store.count());
            System.out.println("store-count="
                    + context.getBeansOfType(OrderStore.class).size());

            System.out.println("service-singleton="
                    + (checkout == context.getBean(CheckoutService.class)));
        }
    }
}
```

### 5.9. Chạy

Trong thư mục `modular-config-demo`, với Gradle và JDK 17+:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Lệnh `javac App.java` đơn lẻ không đủ vì project có nhiều file/package và cần Spring JAR trên classpath; Gradle xử lý compile/runtime dependencies.

**Các dòng do ứng dụng in ra:**

```text
store-bean=true
discount-bean=true
checkout1=ORDER-7:90
checkout2=ORDER-8:45
writes=2
store-count=1
service-singleton=true
```

Output có thể kèm log của Gradle hoặc runtime tùy môi trường, nhưng bảy dòng trên đến từ `System.out.println` của chương trình.

### 5.10. Vì sao output đúng?

1. `ApplicationConfiguration` được đăng ký trực tiếp. Spring phân tích `@Import` và đăng ký definitions từ ba class `@Configuration` được import.
2. `@Bean OrderStore orderStore()` tạo một `InMemoryOrderStore`; `containsBean("orderStore")` trả `true`.
3. `@Bean DiscountPolicy discountPolicy()` tạo `TenPercentDiscountPolicy`; bean tên `discountPolicy` tồn tại.
4. `CheckoutConfiguration` yêu cầu `OrderStore` và `DiscountPolicy` bằng tham số factory method. Hai interface này có mỗi loại đúng một bean hợp lệ, nên Spring inject được.
5. `checkout("ORDER-7", 100)` áp quy tắc giảm 10%, lưu `ORDER-7:90`. Lệnh thứ hai lưu `ORDER-8:45`.
6. `OrderStore` là singleton mặc định. Checkout và entry point đều dùng cùng managed store, nên sau hai lần lưu, `store.count()` bằng 2.
7. `getBeansOfType(OrderStore.class).size()` bằng 1 vì chỉ có một bean loại này trong context.
8. `CheckoutService` cũng mặc định singleton nên hai lần `getBean(CheckoutService.class)` trả cùng instance.

**Điểm cốt lõi được kiểm chứng:** nhiều configuration classes vẫn đóng góp bean vào **một IoC Container chung**, và các dependencies có thể nối xuyên class/package qua type. Không có lệnh `new StorageConfiguration()` trong checkout hoặc lời gọi trực tiếp `orderStore()` từ một configuration khác.

## 6. Vì sao nên tránh các cấu hình import qua lại?

Xem một tình huống tổ chức kém:

```text
PricingConfiguration -> @Import(CheckoutConfiguration)
CheckoutConfiguration -> @Import(StorageConfiguration)
StorageConfiguration -> @Import(PricingConfiguration)
```

Một số tổ hợp import qua lại có thể được Spring xử lý theo metadata trong các giới hạn cụ thể, nhưng **về mặt thiết kế**, chúng làm dependency direction mờ đi: lớp thấp hơn cần “biết” ứng dụng cao hơn và khó xác định composition root.

Đề xuất rõ ràng hơn:

```text
ApplicationConfiguration
    |
    +--> StorageConfiguration
    +--> PricingConfiguration
    +--> CheckoutConfiguration

CheckoutService
    |
    +--> OrderStore interface
    +--> DiscountPolicy interface
```

**Phân biệt hai loại đồ thị:**

- **Import graph** nói cấu hình nào được nạp vào application context.
- **Bean dependency graph** nói bean nào cần bean nào khi được tạo/sử dụng.

Không nên cố mô phỏng bean dependency graph bằng cách để mỗi module tự `@Import` những configuration của module mà nó dùng. Composition root nạp tập modules, còn bean dependency được thể hiện qua constructor/factory method parameters. Đây là cách giảm coupling giữa các configuration classes.

## 7. @Import và @ComponentScan: dùng khi nào?

| Tiêu chí | `@Import` | `@ComponentScan` |
| --- | --- | --- |
| Cách chọn class | Tường minh bằng class/type được tham chiếu | Tự tìm candidate trong base packages theo filters |
| Mục đích chính | Ghép cấu hình hoặc đăng ký type được chỉ định | Phát hiện `@Component` và các stereotype |
| Bị ảnh hưởng bởi package scan? | Không cần package scan của type được import | Có |
| Dễ thấy module nào được bật từ composition root? | Có, đọc mảng `@Import` | Phải xem package/filter và classpath |
| Có thể dùng với class không có `@Component`? | Có, theo các kiểu `@Import` hỗ trợ | Scanner mặc định không tự chọn type thiếu marker |
| Phù hợp | Tập cấu hình/feature module xác định rõ | Nhiều application components theo convention |

Không cần lựa chọn **chỉ một**. Một tổ chức thực tế thường:

1. Composition root dùng `@Import` để ghép các cấu hình chức năng.
2. Mỗi configuration có thể dùng `@ComponentScan(basePackageClasses=FeatureMarker.class)` để tìm service/controller của **chức năng đó**, hoặc dùng `@Bean` explicit.
3. Tránh scan package gốc quá rộng nếu dễ cuốn các test doubles, adapters và configuration không dự kiến vào context.

Ví dụ cấu trúc cho một feature có nhiều component:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = PricingPackageMarker.class)
public class PricingConfiguration {
}
```

`PricingPackageMarker` là marker class/interface nằm trong package muốn scan. `basePackageClasses` dùng **package** của class tham chiếu làm gốc; nó không chỉ quét riêng class marker. Cần import `ComponentScan`, `Configuration` và marker hợp lệ.

**Lưu ý:** nếu marker nằm ở một package quá chung, scanner có thể nhận cả cấu hình/bean của modules khác. Việc gắn package vào module chức năng là ý định tổ chức, không tự tạo “module isolation” ở runtime: tất cả bean được scan/import vẫn nằm trong context hiện tại.

## 8. Ranh giới chức năng không tự biến thành DI isolation

Khi import ba configuration vào một context, các bean definitions đều cùng tham gia dependency resolution trong context ấy. Spring không tự ngăn một bean Storage phụ thuộc ngược vào Checkout chỉ vì chúng ở package khác.

**Ví dụ hướng dependency kém:**

```text
Storage adapter ---> CheckoutService ---> OrderStore
        ^                                 |
        +---------------------------------+
```

Rủi ro là vòng phụ thuộc và kiến trúc khó thay thế. Ngược lại, nếu Checkout chỉ biết `OrderStore` interface, implementation có thể thay bằng JDBC, event store hoặc in-memory fake mà không chỉnh sửa CheckoutService.

Để enforce boundaries, có thể dùng:

- Code review và quy ước package.
- Module Java/Gradle/Maven phù hợp với kích thước dự án.
- Kiểm thử kiến trúc kiểm soát import directions.
- Chỉ export hợp đồng được tiêu thụ; implementation để internal khi Java visibility/package cho phép.
- Dependency graph review trước khi thêm một constructor dependency mới.

**Tách cấu hình là một bước tổ chức; không tự động là bảo đảm cô lập kiến trúc.**

## 9. Nên chia theo chức năng hay theo hạ tầng kỹ thuật?

Cả hai hướng có chỗ dùng.

### 9.1. Feature-first khi use case có ownership rõ

Một checkout feature có thể sở hữu `CheckoutConfiguration`, service và các adapter đặc thù. Mỗi feature module mang một “entry point” cấu hình và public contracts của nó.

Ưu điểm:

- Đội phụ trách feature dễ tìm nơi thay đổi.
- Test chỉ cần import configuration liên quan.
- Ít chỉnh sửa central config khi nội bộ feature phát triển.
- Có thể tắt/thay module bằng composition root.

Nhược điểm: nếu mỗi feature tạo một `ObjectMapper` hoặc một connection pool riêng dù chúng phải chia sẻ, hệ thống có thể trùng tài nguyên và khó quản lý lifecycle.

### 9.2. Infrastructure-first khi tài nguyên có ownership chung

Các tài nguyên như shared `DataSource`, Jackson mapper, HTTP connection pool, metrics hoặc clock có thể được định nghĩa ở một **shared infrastructure configuration**. Những feature khác inject **hợp đồng** của chúng, tránh tạo tài nguyên trùng.

Ví dụ:

```text
ApplicationConfiguration
├── SharedInfrastructureConfiguration
├── CustomerFeatureConfiguration
├── OrderFeatureConfiguration
└── BillingFeatureConfiguration
```

Nhưng một shared config cũng có thể trở thành “God Configuration” nếu mọi feature-specific decision bị nhét vào đó. Tiêu chí nên là **ai sở hữu lifecycle/policy của tài nguyên** và **những ai thật sự cần dùng chung**, không đơn thuần số lượng class.

### 9.3. Hybrid thường thực tế nhất

- Configuration theo feature/use case: service, policies, feature adapters.
- Configuration theo shared infrastructure: tài nguyên chung thực sự.
- Composition root: chọn tập modules cho một application/deployment.
- Profiles/conditions: chọn biến thể implementation theo môi trường khi cần.
- Interface: ngăn feature service lệ thuộc trực tiếp vendor SDK.

## 10. Thay đổi implementation mà không sửa service

Trong ví dụ, Checkout dùng `OrderStore`, không biết `InMemoryOrderStore`. Ta có thể định nghĩa một implementation khác:

```java
public final class JdbcOrderStore implements OrderStore {
    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public String save(String id, long total) {
        jdbc.update(
            "insert into orders(id, total) values (?, ?)",
            id, total
        );
        return id + ":" + total;
    }

    @Override
    public int count() {
        Integer value = jdbc.queryForObject(
            "select count(*) from orders",
            Integer.class
        );
        return java.util.Objects.requireNonNull(value);
    }
}
```

Đây là **mã minh họa không độc lập**, vì cần import `OrderStore`, `JdbcTemplate` (`spring-jdbc`), một database với schema `orders`, cấu hình `DataSource` và các kiểu tương ứng. Không dùng SQL snippet này như một migration/schema production.

Khi production chọn JDBC:

```java
@Configuration(proxyBeanMethods = false)
class JdbcStorageConfiguration {
    @Bean
    OrderStore orderStore(JdbcTemplate jdbc) {
        return new JdbcOrderStore(jdbc);
    }
}
```

Composition root có thể import `JdbcStorageConfiguration` thay cho `StorageConfiguration` in-memory, **không import đồng thời cả hai nếu chúng cùng khai báo bean name `orderStore` mà không có chính sách conflict**.

CheckoutService không phải thay. Đây là lợi ích chính của **configurable composition**.

### 10.1. Tránh import hai implementation cùng lúc

Nếu hai configurations cùng chứa:

```java
@Bean
OrderStore orderStore() { /*...*/ }
```

trong một context, chúng có thể đụng **cùng bean name** `orderStore`. Tùy thiết lập, việc định nghĩa trùng có thể gây lỗi hoặc một definition ghi đè definition khác. Không nên dựa vào thứ tự import để lựa chọn implementation.

Nếu hai methods có **khác tên** nhưng cùng return type `OrderStore`, injection đơn theo type cũng có thể bị mơ hồ: `NoUniqueBeanDefinitionException`.

Cách rõ hơn:

- Composition root chỉ import **một** implementation mặc định trong deployment.
- Nếu cần hai implementation hợp lệ, dùng tên/`@Qualifier`/`@Primary` theo nhu cầu nghiệp vụ.
- Với Spring Boot auto-configuration, các condition như `@ConditionalOnMissingBean` thường giải quyết bean mặc định, nhưng đó là **API của Spring Boot**, không tự có trong project Spring Framework thuần chỉ dùng `spring-context`.

## 11. @Qualifier và @Primary trong module cấu hình

Giả sử hệ thống có hai adapters cùng kiểu:

```java
@Bean("fastStore")
OrderStore fastStore() {
    return new FastOrderStore();
}

@Bean("durableStore")
OrderStore durableStore() {
    return new DurableOrderStore();
}
```

`FastOrderStore` và `DurableOrderStore` là các kiểu giả định, code chỉ minh họa hai bean registrations. Khi Checkout yêu cầu một bean nhất định:

```java
@Bean
CheckoutService checkoutService(
        @Qualifier("durableStore") OrderStore store,
        DiscountPolicy discounts) {
    return new CheckoutService(store, discounts);
}
```

Cần import `Qualifier`. Spring sẽ chọn candidate phù hợp theo qualifier. Nếu có một bean mặc định nên dùng khi injection không gắn qualifier, có thể đánh dấu `@Primary` lên một bean definition phù hợp.

**Quy ước:** qualifier nên diễn đạt vai trò như `durableStore`, `reportingStore`, `paymentClient` hơn là tên implementation chi tiết dễ đổi. Mặc dù tên bean là string, có thể dùng custom qualifier annotation để giảm phụ thuộc literal nếu số điểm injection lớn.

## 12. Profiles và điều kiện chọn biến thể

Trong thực tế, nhiều ứng dụng cần in-memory storage cho local/test và database cho production. Spring cung cấp `@Profile` để giới hạn bean/configuration theo active profiles.

Ví dụ cấu trúc:

```java
@Configuration(proxyBeanMethods = false)
@Profile("local")
class LocalStorageConfiguration {
    @Bean
    OrderStore orderStore() {
        return new InMemoryOrderStore();
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("prod")
class ProductionStorageConfiguration {
    @Bean
    OrderStore orderStore(DataSource dataSource) {
        return new ProductionOrderStore(dataSource);
    }
}
```

`ProductionOrderStore` là kiểu giả định; cần `DataSource` và code persistence thật. Đây không phải phần chạy của demo chính.

Nếu composition root import cả hai nhưng chỉ một profile tương ứng active, Spring có thể chọn bean definitions theo `@Profile`. Tuy nhiên cần xác định rõ behavior khi **không profile nào active**, **cả hai active** hoặc các conditional registrations tương tác. Nếu cả hai profile active và cùng tạo tên `orderStore`, vẫn có nguy cơ conflict.

Đừng xem profile như một cơ chế hoàn chỉnh để quản lý mọi feature toggle. Feature flags runtime có thể thay đổi trong quá trình ứng dụng chạy; `@Profile` chủ yếu ảnh hưởng **đăng ký bean khi context được xây dựng**.

### @Conditional trong Spring Core

Spring hỗ trợ `@Conditional` với implementation `Condition` để điều khiển registration bằng điều kiện cấu hình. Nhưng viết condition phức tạp chỉ để tránh import hai configurations thường làm khó debug. Với composition root tường minh, chọn đúng module từ đầu có thể rõ hơn.

`@ConditionalOnProperty` và `@ConditionalOnMissingBean` là công cụ thường gặp trong **Spring Boot**, không phải những annotation cơ bản của `spring-context` trong demo hiện tại.

## 13. Test từng ranh giới cấu hình

Cấu hình chia module giúp tạo **context nhỏ** cho từng test.

### 13.1. Test riêng PricingConfiguration

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
                 PricingConfiguration.class)) {

    DiscountPolicy policy =
            context.getBean(DiscountPolicy.class);

    if (policy.discountedTotal(100) != 90) {
        throw new AssertionError("unexpected discount");
    }
}
```

Đây là đoạn code dựa vào file `PricingConfiguration` và `DiscountPolicy` của demo; cần import cả hai cùng `AnnotationConfigApplicationContext`. Test chỉ cần module Pricing; không cần storage và checkout.

### 13.2. Test Checkout với fake store và policy

Vì `CheckoutService` chỉ phụ thuộc interfaces, có thể kiểm thử thuần Java:

```java
OrderStore fake = new InMemoryOrderStore();
DiscountPolicy fixed = baseTotal -> baseTotal - 5;

CheckoutService service = new CheckoutService(fake, fixed);

String result = service.checkout("TEST-1", 20);
if (!"TEST-1:15".equals(result)) {
    throw new AssertionError(result);
}
```

Snippet này dùng các kiểu trong demo (cần imports). Không cần ApplicationContext. Đây là **unit test nghiệp vụ**, không kiểm chứng khả năng ghép bean definitions.

### 13.3. Test composition root bằng context thật

Dựng context với `ApplicationConfiguration.class` và kiểm tra:

- `OrderStore` có đúng một candidate.
- `DiscountPolicy` có đúng một candidate.
- `CheckoutService` được tạo và có behavior đúng.
- Không có bean ngoài ý muốn từ module chưa import.
- Tài nguyên chung (nếu có) đúng scope và chỉ tạo một lần.

Demo `App.main()` chính là một integration smoke test đơn giản với bảy dòng stdout xác định. Trong dự án có JUnit 5, có thể dùng assertions thay vì `System.out.println`.

### 13.4. Test cấu hình thay thế

Một **test composition root** khác có thể import:

```java
@Configuration(proxyBeanMethods = false)
@Import({
    FakeStorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
class CheckoutTestConfiguration {}
```

`FakeStorageConfiguration` là một class test giả định trả `OrderStore` fake. Đây là cấu hình riêng cho test, không thêm bean fake vào production root. Cần đảm bảo **chỉ có một candidate hợp lệ** cho injection point, không tạo hai `OrderStore` cùng type rồi dựa vào thứ tự ngẫu nhiên.

### 13.5. Đừng dùng cả application context khi test một utility

Test service logic thuần Java có thể tạo object trực tiếp. Dùng Spring context khi đang kiểm thử **wiring/configuration**, scope, qualifier, bean lifecycle hoặc integration hạ tầng. Cách chia cấu hình hợp lý cho phép chọn test scope nhỏ nhất mà vẫn chứng minh được điều cần kiểm tra.

## 14. Phương pháp giữ module độc lập khi dùng @ComponentScan

Một module có vài chục service có thể muốn quét theo package riêng thay vì khai báo `@Bean` cho từng class. Có thể cho `FeatureConfiguration` thực hiện scan **đúng package feature**:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrdersPackageMarker.class)
class OrdersFeatureConfiguration {}
```

`OrdersPackageMarker` là marker type do ứng dụng đặt trong package orders, và các `@Service`/`@Repository` liên quan nằm trong package đó hoặc package con. Đây là snippet minh họa, cần các imports và marker thực tế.

Hai nguyên tắc quan trọng:

1. **Composition root vẫn có thể dùng `@Import(OrdersFeatureConfiguration.class)`** để chọn feature; scan chỉ hoạt động bên trong feature được nạp.
2. Nếu component scan quá rộng, nó có thể tìm thêm các `@Configuration` của tính năng khác do `@Configuration` là specialization của `@Component`. Khi ấy “chỉ import feature A” vẫn có thể gián tiếp nhận bean feature B nếu package scan không được giới hạn cẩn thận.

Các `includeFilters`/`excludeFilters` và `useDefaultFilters=false` có thể tinh chỉnh scanning, nhưng không phải công cụ chính để sửa một cấu trúc package thiếu rõ ràng.

### Một lưu ý về “internal configuration”

Một configuration class `@Configuration` trong package nội bộ có thể bị Spring tìm thấy nếu một component scan khác bao trùm package ấy. Không nên dựa vào Java package name để khẳng định module không bao giờ được register. Giới hạn scan và dùng import graph tường minh nếu module activation là yêu cầu quan trọng.

## 15. Kết hợp @Import với lớp cấu hình dùng @Bean parameters

Giả sử một feature muốn dùng `Clock`, `OrderStore` và `DiscountPolicy`:

```java
@Configuration(proxyBeanMethods = false)
class CheckoutConfiguration {
    @Bean
    CheckoutService checkoutService(
            OrderStore store,
            DiscountPolicy policy) {
        return new CheckoutService(store, policy);
    }
}
```

Method chỉ khai báo những gì cần; nơi cấp các beans có thể đến từ `StorageConfiguration` và `PricingConfiguration`. Spring cho phép dependency resolution xuyên classes được import **không cần gọi direct `@Bean` methods**.

Không cần viết:

```java
@Configuration
class CheckoutConfiguration {
    @Autowired
    private StorageConfiguration storageConfiguration;

    @Bean
    CheckoutService checkoutService() {
        return new CheckoutService(
                storageConfiguration.orderStore(),
                new TenPercentDiscountPolicy()
        );
    }
}
```

Đây là **anti-pattern minh họa**; nếu `StorageConfiguration` dùng `proxyBeanMethods=false`, direct call có thể tạo store khác ngoài singleton managed. Nếu dùng full interception, code vẫn khiến checkout biết concrete configuration, làm coupling tăng. Injection bằng interface qua method parameter đơn giản hơn.

Tài liệu Spring còn cảnh báo rằng class `@Configuration` được xử lý sớm. Field/constructor injection trên **chính configuration class** có thể dẫn tới khởi tạo sớm không mong muốn, nhất là khi cấu hình chứa `BeanFactoryPostProcessor`/`BeanPostProcessor`. Với processors cần tạo rất sớm, thường dùng `static @Bean` cùng return type thích hợp. Khi khai báo bean nghiệp vụ thông thường, parameter injection là cách dễ kiểm soát dependency nhất.

## 16. Ranh giới module và vòng đời tài nguyên

Một cấu hình chức năng có thể tạo resource đắt tiền:

```java
@Configuration(proxyBeanMethods = false)
class MessagingConfiguration {
    @Bean(destroyMethod = "close")
    VendorMessageClient messageClient(MessagingSettings settings) {
        return VendorMessageClient.create(settings);
    }
}
```

`VendorMessageClient`/`MessagingSettings` là kiểu SDK giả định; code này minh họa ý tưởng ownership/lifecycle. Nếu thư viện có `close()` phù hợp và resource do ứng dụng sở hữu, container sẽ gọi destroy callback theo định nghĩa khi đóng bean/context trong điều kiện phù hợp.

Ranh giới chức năng không chỉ nói bean nằm trong file nào, mà còn **ai sở hữu tài nguyên**:

- Shared HTTP client có thể thuộc `SharedIntegrationConfiguration`.
- Connection pool có thể thuộc `PersistenceConfiguration`.
- Một per-request builder có thể thuộc feature configuration với `prototype` hoặc scope phù hợp.
- Feature service thường chỉ inject hợp đồng tài nguyên; **không tự tạo hoặc tự đóng resource dùng chung**.

Nếu mỗi feature tự `new DataSource()` hoặc tạo pool độc lập, tách cấu hình có thể làm phân tán ownership và tăng rò rỉ tài nguyên. Chia module đúng phải giúp quyền sở hữu rõ hơn, không làm phức tạp hơn.

## 17. Khi nào chia sang Gradle/Maven module riêng?

Tách `@Configuration` theo class/package là ranh giới **logic trong một codebase**. Khi quy mô lớn hơn, bạn có thể tách module vật lý:

```text
checkout-api/
checkout-impl/
pricing-api/
pricing-impl/
storage-api/
storage-jdbc/
application/
```

Nhưng điều này thêm chi phí build, dependency management, public API governance và deploy. Cân nhắc khi:

- Có nhiều nhóm thay đổi độc lập.
- Muốn compiler/build ngăn implementation dependency bị đảo hướng.
- Có test hoặc artifact cần reuse riêng.
- Muốn tách adapter theo environment mà không kéo mọi dependency vào một package lớn.

Ngay cả khi đã có nhiều Gradle/Maven modules, Spring vẫn có thể ghép các configuration classes vào **một ApplicationContext** qua `@Import`, scan phù hợp hoặc auto-configuration. Module build-time và bean container runtime là hai khái niệm khác nhau.

**Tránh phát biểu sai:** mỗi Gradle module không tự động có một Spring context; mỗi `@Configuration` cũng không tự động có singleton cache riêng.

## 18. Các phương án ghép cấu hình khác nhau

### 18.1. @Import trực tiếp

```java
@Configuration(proxyBeanMethods = false)
@Import({
    StorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
class ApplicationConfiguration {}
```

Ưu điểm: explicit, dễ code review. Phù hợp số modules vừa phải.

### 18.2. @Import ở cấu hình cấp feature

Nếu một feature có nhiều phần nội bộ:

```java
@Configuration(proxyBeanMethods = false)
@Import({
    FeatureDomainConfiguration.class,
    FeatureAdaptersConfiguration.class
})
class FeatureConfiguration {}
```

`FeatureDomainConfiguration`/`FeatureAdaptersConfiguration` là các class giả định. Composition root import `FeatureConfiguration`. Mẫu này hữu ích nếu một feature thật sự sở hữu hai cấu hình con, chứ không phải để mỗi feature âm thầm import cả toàn bộ ứng dụng.

### 18.3. Context.register nhiều cấu hình

```java
try (AnnotationConfigApplicationContext ctx =
         new AnnotationConfigApplicationContext()) {
    ctx.register(
        StorageConfiguration.class,
        PricingConfiguration.class,
        CheckoutConfiguration.class
    );
    ctx.refresh();
    CheckoutService service = ctx.getBean(CheckoutService.class);
}
```

Đây là snippet có thể dùng với các class demo và imports phù hợp. Nó ghép trực tiếp nhiều config từ bootstrap, không cần `@Import`. Phù hợp bootstrap cần chọn module bằng code; tuy nhiên một `ApplicationConfiguration` làm composition root thường giúp tập cấu hình hiển thị rõ ràng và dễ reuse hơn.

### 18.4. Spring Boot auto-configuration

Spring Boot có cơ chế tự động cấu hình bean dựa trên classpath/properties và các conditions. Đây là cấp độ tổ hợp mạnh hơn, phù hợp thư viện/starter reusable, nhưng **không phải bắt buộc** để ghép 3–10 chức năng trong ứng dụng Spring đơn giản. Đừng áp dụng `@ConditionalOnMissingBean` của Boot vào demo thuần `spring-context` mà chưa thêm dependencies tương ứng.

### 18.5. @ImportSelector và ImportBeanDefinitionRegistrar

Đây là các extension point cấp cao giúp quyết định import/đăng ký definitions bằng code và metadata. Chúng có ích khi xây framework, starter hoặc module plugin, nhưng tăng độ khó truy vết bean. Với ghép module tường minh, thường chưa cần.

## 19. Các lỗi thường gặp

### Lỗi 1 — Chỉ tạo class @Configuration nhưng không nạp vào context

Bean definitions không tự xuất hiện chỉ vì file có trong source. Kiểm tra `@Import`, `context.register(...)`, component scan và những cơ chế đăng ký khác. Nếu `ApplicationConfiguration` không được nạp, import graph của nó cũng không được xử lý.

### Lỗi 2 — Mỗi module tự tạo implementation của module khác

Ví dụ Checkout tạo `new InMemoryOrderStore()` thay vì nhận `OrderStore` bean. Hậu quả là hai store khác nhau, mất shared state/lifecycle, test khó thay thế. Dùng interface injection qua constructor/`@Bean` parameters.

### Lỗi 3 — Đặt @ComponentScan ở package gốc quá rộng

Scanner có thể phát hiện cả `@Configuration`, test adapters hoặc implementation dự kiến chỉ dùng cho môi trường khác. Giới hạn scan theo feature hoặc dùng `@Import` explicit.

### Lỗi 4 — Một bean được đăng ký hai lần

Nếu cùng implementation vừa có `@Component` trong package đang scan, vừa có `@Bean` tạo object khác, Spring có thể có nhiều bean cùng type hoặc trùng tên. Rà soát tất cả đường đăng ký và chỉ duy trì registration có chủ ý.

### Lỗi 5 — Hai module cùng khai báo bean name giống nhau

Hai phương thức tên `orderStore` ở các configurations khác nhau có thể xung đột definition. Đừng dựa vào việc BeanDefinition overriding luôn được phép. Thiết kế mỗi tên bean có chủ sở hữu rõ.

### Lỗi 6 — Có hai beans cùng interface mà Checkout không biết chọn

`CheckoutConfiguration.checkoutService(OrderStore store, ...)` có thể gây `NoUniqueBeanDefinitionException`. Dùng `@Qualifier`/`@Primary` khi nhiều candidate là chủ ý hoặc chỉ import một implementation.

### Lỗi 7 — Dùng @Profile mà quên profile mặc định

Khi cả hai implementations đều chỉ tồn tại theo `local`/`prod`, không active profile phù hợp sẽ thiếu bean. Nếu cả hai active, có thể trùng tên hoặc mơ hồ. Kiểm thử rõ từng environment.

### Lỗi 8 — Lạm dụng @Import theo dạng vòng

Nếu storage import checkout và checkout lại import storage, kiến trúc trở nên khó đoán và có thể tạo bean circular dependencies. Giữ composition root làm nơi chọn modules; code nghiệp vụ chỉ phụ thuộc hợp đồng.

### Lỗi 9 — Dựa vào thứ tự khai báo trong @Import

Các dependency nên được Spring giải quyết qua parameter injection. Đừng giả định modules được instantiate theo thứ tự trong mảng `@Import` như một quy tắc nghiệp vụ; Spring có dependency graph, scope, lazy beans và infrastructure lifecycle riêng.

### Lỗi 10 — Tạo tài nguyên nặng ở nhiều configuration

Hai modules mỗi nơi `@Bean ObjectMapper`/client/pool khác nhau có thể hợp lý khi policy khác nhau, nhưng nguy hiểm nếu vô tình nhân đôi connection pool. Xác định scope và ownership, reuse bean chung qua injection khi thực sự cần.

### Lỗi 11 — Ghép tất cả configuration vào mọi test

Context quá lớn gây test chậm, yêu cầu database/network không cần thiết và khó tách nguyên nhân lỗi. Tạo fixture nhỏ chỉ import module đang test, cộng các fake dependencies cần thiết.

### Lỗi 12 — Dùng @Configuration(proxyBeanMethods=false) nhưng gọi chéo @Bean

Lời gọi trong thân factory method là Java direct call, có thể tạo object mới ngoài managed bean. Dùng parameter injection thay thế. Dù full mode có thể intercept inter-bean calls, explicit parameters vẫn dễ hiểu và ít coupling hơn.

### Lỗi 13 — Nhầm import graph với runtime visibility constraint

`@Import` chỉ nạp định nghĩa bean; nó không cấm class khác `getBean(...)` hoặc inject một type mà thiết kế kiến trúc muốn giữ private. Cần module boundaries/code review/test kiến trúc để kiểm soát hướng phụ thuộc.

### Lỗi 14 — Nghĩ @Profile thay thế composition root

`@Profile` chọn registrations theo môi trường, nhưng không giúp giải thích **module nào sở hữu bean** hoặc ngăn profile bị bật đồng thời. Dùng profile cho biến thể có chủ đích; composition root vẫn nên thể hiện tập feature.

## 20. Checklist khi thiết kế cấu hình chức năng

Trước khi tạo một configuration class mới, trả lời:

1. **Chức năng nào chịu trách nhiệm?** Storage, pricing, checkout, billing, reporting hay shared infra?
2. **Public contract là gì?** Interface/service nào module khác được phép tiêu thụ?
3. **Ai đăng ký bean implementation?** Nên có một nơi sở hữu bean definition và lifecycle.
4. **Cấu hình được nạp bằng cách nào?** `@Import`, direct register, component scan hay Boot auto-configuration?
5. **Module nào phụ thuộc module nào?** Hướng dependency có nhất quán và không tạo vòng không?
6. **Có nhiều implementation cùng type không?** Nếu có, qualifier/primary/conditional selection được thiết kế rõ chưa?
7. **Có cần scan tự động không?** Nếu không, explicit `@Bean` thường dễ theo dõi hơn.
8. **Có tài nguyên dùng chung không?** Những bean nào nên singleton, prototype, lazy, có destroy callback hay external ownership?
9. **Test tối thiểu cần module nào?** Có thể dựng context cho riêng feature hay unit test bằng object thường không?
10. **Có thể thay adapter mà không sửa service không?** Nếu không, cân nhắc tách interface và composition logic.

## 21. Câu hỏi tự luyện và đáp án

**Câu 1.** Một context nạp `ApplicationConfiguration` với `@Import(StorageConfiguration.class, PricingConfiguration.class)`. Có cần `@ComponentScan` để nhận `@Bean` methods trong hai configuration này không?

**Đáp:** Không. `@Import` nạp các configuration và Spring xử lý các `@Bean` methods của chúng. Component scanning là một đường tìm class khác.

**Câu 2.** CheckoutConfiguration có method `checkoutService(OrderStore store, DiscountPolicy policy)`. Bean `OrderStore` đến từ StorageConfiguration. Spring nối hai class cấu hình bằng cách nào?

**Đáp:** Khi tạo `checkoutService`, container resolve hai tham số dựa trên bean definitions/type/qualifier đang có trong cùng context. CheckoutConfiguration không cần gọi trực tiếp StorageConfiguration.

**Câu 3.** Mỗi `@Configuration` có tạo một context riêng không?

**Đáp:** Không. Trong ví dụ, một `AnnotationConfigApplicationContext` chứa definitions được import từ ba configuration classes.

**Câu 4.** Vì sao không nên để PricingConfiguration import CheckoutConfiguration chỉ vì Checkout dùng DiscountPolicy?

**Đáp:** Đó là đảo hướng composition/dependency. Pricing không cần biết use case dùng nó; composition root chọn cả hai, còn Checkout khai báo tham số `DiscountPolicy`.

**Câu 5.** Có thể tách implementation JDBC khỏi in-memory mà không sửa CheckoutService không?

**Đáp:** Có. CheckoutService dùng interface `OrderStore`. Composition root chọn một configuration cung cấp implementation tương ứng; chú ý không để hai beans không phân định cùng xuất hiện.

**Câu 6.** Vì sao `@Import` phù hợp khi cần nhìn rõ các modules được bật?

**Đáp:** Mảng import là danh sách tường minh các nguồn cấu hình. Component scan có thể chọn thêm classes tùy package/filter/classpath và cần kiểm tra phạm vi để biết tập bean thật.

**Câu 7.** Nếu hai beans cùng implement `OrderStore`, tiêm `OrderStore` vào Checkout có luôn được không?

**Đáp:** Không chắc. Khi nhiều candidate không xác định được ứng viên duy nhất, Spring báo `NoUniqueBeanDefinitionException`. Cần qualifier, primary hoặc chỉ một implementation cho deployment.

**Câu 8.** Trong demo, `writes=2` chứng minh điều gì?

**Đáp:** Hai lần checkout sử dụng cùng managed singleton `OrderStore` mà entry point đọc lại từ context. Module composition giữ dependency identity nhất quán.

**Câu 9.** Nếu dùng `@ComponentScan(basePackageClasses=Marker.class)` thì Spring chỉ quét một class Marker đúng không?

**Đáp:** Không. Nó dùng package chứa Marker làm gốc để scan, kể cả các package con tương ứng.

**Câu 10.** Một bean được loại khỏi một component scan có chắc không xuất hiện trong context không?

**Đáp:** Không. Bean có thể được đăng ký bằng `@Bean`, `@Import` hoặc scan từ nơi khác. Phải kiểm tra tất cả đường đăng ký.

**Câu 11.** Có nên cho shared HTTP pool vào cả PricingConfiguration và CheckoutConfiguration?

**Đáp:** Chỉ nếu thật sự cần hai pools với policy/lifecycle độc lập. Nếu là tài nguyên chia sẻ, nên có một owner configuration, rồi các feature inject cùng bean được quản lý.

**Câu 12.** Khi test DiscountPolicy, có cần dựng luôn Storage và Checkout modules không?

**Đáp:** Không. Với unit test, tạo policy trực tiếp; với wiring test, chỉ import PricingConfiguration. Context tối thiểu giúp test nhanh và rõ nguyên nhân.

## 22. Tài liệu chính thức để đối chiếu

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, ghép cấu hình, injection xuyên configuration classes và lưu ý early initialization.
- [Spring Framework 6.2 — Instantiating the Container with AnnotationConfigApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/instantiating-container.html): `register()`, `refresh()` và `scan()`.
- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): hai annotation cấu hình cốt lõi.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters, return type, scope và lifecycle.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): phương thức cấu hình và inter-bean references.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): quan hệ giữa `@ComponentScan`, stereotype và metadata registration.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): vòng đời và scope khi ghép nhiều bean definitions.

**Ghi nhớ:** Chia cấu hình theo ranh giới chức năng giúp module có trách nhiệm và ownership rõ ràng. `@Import` ghép những nguồn cấu hình cần thiết vào **một Spring IoC Container**, còn **tham số `@Bean`**/constructor injection nối các bean thông qua hợp đồng thay vì thông qua lời gọi trực tiếp giữa configuration classes. Composition root quyết định *cái gì được lắp vào ứng dụng*; mỗi module quyết định *mình cung cấp bean nào*; Spring giải quyết *cách các dependency gặp nhau*.
