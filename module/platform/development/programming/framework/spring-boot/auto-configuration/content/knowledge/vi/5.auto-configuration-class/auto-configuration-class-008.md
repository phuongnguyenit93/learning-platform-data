# Thiết kế phương thức @Bean công khai và khai báo kiểu trả về đủ thông tin trong Spring Boot

> **Chủ đề:** Spring Boot — auto-configuration → lớp tự cấu hình. Trọng tâm là thiết kế các phương thức `@Bean` mà phần khai báo **dễ đọc, có khả năng sử dụng từ thư viện khác và cung cấp kiểu trả về đủ cụ thể** để Spring xác định bean definition, tiêm phụ thuộc và đánh giá `@ConditionalOnBean` / `@ConditionalOnMissingBean` trước khi instance được tạo. Ví dụ sử dụng Java 17, Maven và Spring Boot 3.5.7.

## 1. Vì sao chỉ sửa kiểu trả về của @Bean có thể đổi hành vi ứng dụng?

Hãy so sánh hai cách khai báo một bean có instance thực tế giống hệt nhau:

```java
@Bean
public Store store() {
    return new InMemoryStore();
}
```

```java
@Bean
public InMemoryStore store() {
    return new InMemoryStore();
}
```

Hai đoạn trên chỉ là **fragments**; cần có định nghĩa `Store`, `InMemoryStore` và class cấu hình. Khi bean thực sự được tạo, cả hai đều trả về một đối tượng `InMemoryStore`. Tuy nhiên, **tại thời điểm Spring phân tích bean definition trước khi khởi tạo instance**, metadata kiểu của factory method khác nhau:

- Ở ví dụ thứ nhất, Spring có thông tin đáng tin từ chữ ký rằng bean là `Store`.
- Ở ví dụ thứ hai, Spring biết bean là `InMemoryStore` và do Java type hierarchy, cũng biết nó có thể gán cho `Store`.
- Một điều kiện `@ConditionalOnBean(InMemoryStore.class)` cần nhận diện kiểu triển khai cụ thể. Với chữ ký chỉ khai báo `Store`, thông tin này **có thể chưa sẵn có khi điều kiện được đánh giá**.
- Khi đã tạo instance, việc gọi `bean.getClass()` có thể trả về `InMemoryStore.class` ở cả hai trường hợp. Kết quả lúc runtime **không chứng minh** rằng điều kiện ở giai đoạn bean-definition nhìn thấy cùng thông tin.

Tài liệu Spring Boot khuyến nghị: **khai báo càng nhiều thông tin kiểu có ích càng tốt trong kiểu trả về của phương thức `@Bean`**. Nếu implementation hiện thực một interface, nhiều trường hợp nên trả về kiểu implementation cụ thể thay vì chỉ interface, vì bean conditions dựa vào metadata từ chữ ký method. Điều này đặc biệt quan trọng trong auto-configuration. 

**Lưu ý:** Không phải lúc nào cũng buộc phải lộ kiểu triển khai. Giữ kiểu interface ở API công khai có lợi ích kiến trúc khi có chủ ý che implementation. Khi đó phải thiết kế các bean conditions, điểm extension và dependency injection **phù hợp với abstraction đã công bố**; đừng đồng thời kỳ vọng điều kiện khác phát hiện một kiểu concrete không được khai báo.

## 2. Ba lớp khái niệm cần phân biệt

| Khái niệm | Ví dụ | Điều nó mô tả |
| --- | --- | --- |
| **Kiểu khai báo của method** | `public InMemoryStore inMemoryStore()` | Kiểu mà Spring có thể suy ra từ chữ ký bean factory method. |
| **Kiểu runtime của instance** | `new InMemoryStore()` | Class thực tế của đối tượng sau khi method đã chạy. |
| **Kiểu hợp đồng được điều kiện tìm kiếm** | `@ConditionalOnMissingBean(Store.class)` | Kiểu bean mà auto-configuration dùng để quyết định tạo mặc định hay nhường chỗ. |

Ba kiểu có thể trùng nhau, nhưng không bắt buộc. Thiết kế tốt thường trả lời riêng hai câu hỏi:

1. **Bean này thực chất là gì?** Nếu là `InMemoryStore` và bạn muốn các auto-configuration khác nhận thấy đặc tính đó, trả về `InMemoryStore`.
2. **Bean mặc định phải nhường chỗ cho loại bean nào?** Nếu bất kỳ `Store` nào của người dùng đều là lựa chọn hợp lệ, ghi `@ConditionalOnMissingBean(Store.class)` thay vì dựa vào kiểu trả về concrete.

Kết hợp hai quyết định:

```java
@Bean
@ConditionalOnMissingBean(Store.class)
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

**Giải thích:** Method được khai báo kiểu `InMemoryStore` để giữ metadata cụ thể. Điều kiện chủ động tìm kiểu `Store` (interface), vì nó diễn đạt quy tắc back-off rộng hơn. Đó là thiết kế thường phù hợp cho starter/auto-configuration.

## 3. Vì sao metadata kiểu được cần đến **trước khi** tạo instance?

Trong quá trình khởi tạo ApplicationContext, Spring xây dựng danh sách **bean definitions**. Với method `@Bean`, Spring đọc class cấu hình và chữ ký của method để xác định những bean có thể được tạo. Việc khởi tạo singleton thực tế thường xảy ra sau bước đăng ký và đánh giá nhiều loại điều kiện.

Có thể hình dung:

```text
Đọc @AutoConfiguration / @Configuration
              |
              v
Phát hiện @Bean factory method
              |
              v
Ghi metadata từ chữ ký return type
              |
              +----> @ConditionalOnBean(X) hoặc @ConditionalOnMissingBean(X)
              |      dùng kiểu đã biết tại thời điểm điều kiện chạy
              v
Đăng ký bean definition nếu hợp lệ
              |
              v
Tạo instance khi Spring cần khởi tạo bean
              |
              v
getClass() cho biết class thực tế của instance
```

Spring không nên phải gọi tất cả `@Bean` methods để tìm class implementation, vì điều đó có thể:

- Khởi tạo kết nối mạng, database hoặc thread pool quá sớm.
- Gây tác dụng phụ trước khi property và BeanPostProcessor hoàn tất.
- Làm sai thứ tự phụ thuộc hoặc gây vòng lặp khi điều kiện cần biết loại bean trước khi tạo bean.
- Làm tăng thời gian startup và biến việc chọn cấu hình thành quá trình có side effects.

Thông tin từ **method signature** vì vậy có giá trị riêng. Spring có thể có thêm metadata từ nhiều nguồn tùy kiểu bean, proxy, factory method và giai đoạn, nhưng **không nên dựa vào khả năng suy đoán implementation runtime** để làm cho điều kiện auto-configuration hoạt động.

### Hai tình huống trái ngược

**Trường hợp A:**

```java
@Bean
public Object paymentClient() {
    return new PaymentClient();
}
```

Tại thời điểm phân tích, một method trả `Object` không truyền tải rằng nó thực sự cung cấp `PaymentClient`. Một consumer dùng `@ConditionalOnBean(PaymentClient.class)` có thể không thấy bean này trong quá trình đăng ký.

**Trường hợp B:**

```java
@Bean
public PaymentClient paymentClient() {
    return new PaymentClient();
}
```

Chữ ký cụ thể giúp Spring nhận diện `PaymentClient` mà không phải khởi tạo nó trước. Đây là **hai fragments minh họa**, chưa bao gồm định nghĩa `PaymentClient` hoặc imports.

## 4. “Công khai” ở đây có hai nghĩa khác nhau

### 4.1. `public` trong Java

```java
@Bean
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

Từ khóa `public` làm method có thể được gọi theo quy tắc visibility của Java khi class chứa nó cũng truy cập được. Với cấu hình thư viện, `public` thường tăng tính minh bạch, hỗ trợ tooling hoặc việc mở rộng có chủ đích và nhất quán với ví dụ chính thức của Spring.

**Tuy nhiên, `public` không phải điều kiện bắt buộc cho mọi `@Bean` method.** Spring Framework có thể xử lý method package-private trong nhiều cấu hình thích hợp. Không nên kết luận rằng đổi method từ package-private sang public sẽ tự sửa lỗi `@ConditionalOnBean`: vấn đề metadata ở đây nằm ở **kiểu trả về**, không nằm ở visibility.

Khi thiết kế auto-configuration cung cấp điểm mở rộng công khai, hãy chọn visibility nhất quán với hợp đồng Java/module và quy ước nhóm. Tránh dùng `private` cho method cần Spring xử lý trong full `@Configuration` mode, và tránh làm API vô tình phụ thuộc vào implementation không truy cập được. Với `@AutoConfiguration`, `proxyBeanMethods=false` đã được quy định nên khả năng proxy interception cũng khác full mode.

### 4.2. “Công khai đủ thông tin” trong Java type metadata

Đó là việc type signature truyền tải được những gì downstream dependency thực sự cần:

- Có kiểu cụ thể (`PaymentClient`) thay vì quá rộng (`Object`).
- Có phân cấp rõ ràng (`InMemoryStore implements Store`).
- Với type generic, giữ tham số kiểu hữu ích, ví dụ `MessageHandler<Order>` thay vì raw `MessageHandler` khi framework cần phân biệt.
- Với wrapper/factory/proxy, hiểu Spring lấy type metadata từ đâu; nếu đối tượng thực tế được tạo qua factory phức tạp, kết quả type matching cần được kiểm thử.
- Kiểu cụ thể phải **có thể truy cập** bởi code sử dụng nó nếu bạn muốn thư viện consumer tham chiếu trực tiếp. Có thể giữ implementation đóng kín, nhưng đừng viết điều kiện bên ngoài dựa vào implementation ẩn đó.

Nói ngắn gọn: public visibility và return-type specificity là **hai chiều thiết kế khác nhau**, dù chúng thường xuất hiện cạnh nhau trong ví dụ `@Bean`.

## 5. Quy tắc thiết kế với @ConditionalOnMissingBean

Annotation `@ConditionalOnMissingBean` có hai kiểu dùng thường gặp.

### 5.1. Không ghi kiểu: lấy mặc định từ return type

```java
@Bean
@ConditionalOnMissingBean
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

Khi `@ConditionalOnMissingBean` nằm trên `@Bean` method và bạn không chỉ rõ `value`/`type`/`name`, mục tiêu kiểm tra mặc định gắn với **kiểu trả về đã khai báo** của method.

Ở đây mục tiêu gần như là `InMemoryStore`. Điều này **không diễn đạt** “bất kỳ implementation nào của `Store` do người dùng cung cấp đều khiến tôi back off”. Nếu người dùng tạo `RemoteStore implements Store`, có thể cả `RemoteStore` và `InMemoryStore` đều được đăng ký.

### 5.2. Ghi rõ kiểu abstraction: back-off theo contract

```java
@Bean
@ConditionalOnMissingBean(Store.class)
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

Trong bản này:

- Method vẫn công bố kiểu đủ cụ thể `InMemoryStore` cho Spring và auto-configuration khác.
- Điều kiện xem mọi bean phù hợp với `Store` là ứng viên thay thế.
- User `RemoteStore`, `InMemoryStore` hoặc bất kỳ implementation phù hợp của `Store` đều có thể khiến bean mặc định không đăng ký.

Nếu contract thực sự là bean **theo tên** (ví dụ đặt tên bean chuẩn để extension tìm bằng name), có thể dùng `@ConditionalOnMissingBean(name="storeClient")`. Nếu contract là theo kiểu, ưu tiên khai báo kiểu rõ. Name-conditions và type-conditions không phải lúc nào tương đương, nhất là khi một application có nhiều bean cùng interface.

### 5.3. Cẩn trọng với bean name và @Primary

`@Primary` chỉ giúp chọn ưu tiên khi autowire trong tình huống có nhiều bean phù hợp; nó **không tự khiến** một bean mặc định được bảo vệ bằng `@ConditionalOnMissingBean(InMemoryStore.class)` back off khi user chỉ cung cấp bean `RemoteStore`.

Nếu có hai bean cùng tên, mặc định Spring Boot có thể báo lỗi overriding bị vô hiệu hóa. Nếu có hai bean cùng interface, autowire theo interface không có qualifier/primary có thể lỗi do nhiều ứng viên. Thiết kế điều kiện đúng ngay từ đầu tốt hơn dùng `@Primary` để che vấn đề.

## 6. Ví dụ runnable: public @Bean với return type cụ thể và contract back-off rõ ràng

Chúng ta tạo ứng dụng nhỏ có hai auto-configuration:

- `StoreAutoConfiguration` cung cấp `InMemoryStore` khi chưa có bean `Store` của người dùng.
- `StoreDiagnosticsAutoConfiguration` chỉ tạo `StoreDiagnostics` khi đã biết có bean `InMemoryStore`.

Class `InMemoryStore` thuộc nhánh `dev.example.impl`; application class nằm ở `dev.example.app`. Hai auto-configuration thuộc `dev.example.autoconfigure` **ngoài component scan mặc định**, và được nạp qua file `AutoConfiguration.imports`.

### 6.1. Cấu trúc thư mục

```text
bean-type-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/
    │   │   ├── api/Store.java
    │   │   ├── impl/InMemoryStore.java
    │   │   ├── monitoring/StoreDiagnostics.java
    │   │   ├── autoconfigure/StoreAutoConfiguration.java
    │   │   ├── autoconfigure/StoreDiagnosticsAutoConfiguration.java
    │   │   └── app/
    │   │       ├── DemoApplication.java
    │   │       ├── CustomStore.java
    │   │       └── UserStoreConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/dev/example/testing/
        ├── StoreAutoConfigurationTest.java
        └── ApplicationWiringTest.java
```

**Lưu ý:** Cấu trúc này là một artifact để học. Trong thư viện thực tế, bạn thường đóng gói package `autoconfigure`, `api`, `impl` và tài nguyên imports vào JAR thư viện riêng, rồi để application sử dụng chúng thông qua dependency.

### 6.2. Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>bean-type-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Không cần HTTP server, database hoặc starter ngoài Spring Boot cơ bản.

### 6.3. Interface Store

`src/main/java/dev/example/api/Store.java`:

```java
package dev.example.api;

public interface Store {
    String read(String key);
}
```

### 6.4. Implementation mặc định

`src/main/java/dev/example/impl/InMemoryStore.java`:

```java
package dev.example.impl;

import dev.example.api.Store;

public final class InMemoryStore implements Store {
    @Override
    public String read(String key) {
        return "memory:" + key;
    }
}
```

Implementation này là class `public`, có thể được dùng trong chữ ký của `@Bean` và các condition ở module khác. Nó không có `@Component` vì bean sẽ được tạo **qua `@Bean` method**, không qua scan.

### 6.5. Bean diagnostics phụ thuộc implementation cụ thể

`src/main/java/dev/example/monitoring/StoreDiagnostics.java`:

```java
package dev.example.monitoring;

import dev.example.impl.InMemoryStore;

public final class StoreDiagnostics {
    private final InMemoryStore store;

    public StoreDiagnostics(InMemoryStore store) {
        this.store = store;
    }

    public String kind() {
        return store.getClass().getSimpleName();
    }
}
```

Đây là component tùy chọn: diagnostics chỉ phù hợp với `InMemoryStore`; nếu người dùng thay bằng `CustomStore`, chúng ta cố ý không tạo bean `StoreDiagnostics`.

### 6.6. Auto-configuration tạo bean mặc định

`src/main/java/dev/example/autoconfigure/StoreAutoConfiguration.java`:

```java
package dev.example.autoconfigure;

import dev.example.api.Store;
import dev.example.impl.InMemoryStore;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class StoreAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Store.class)
    public InMemoryStore inMemoryStore() {
        return new InMemoryStore();
    }
}
```

**Hai dòng cốt lõi:**

- `public InMemoryStore inMemoryStore()` cung cấp thông tin **kiểu triển khai** ngay tại chữ ký.
- `@ConditionalOnMissingBean(Store.class)` xác định **chính sách nhường chỗ**: mọi bean kiểu `Store` hợp lệ của người dùng đều làm cấu hình mặc định back off.

Khi Boot nạp auto-configuration thông thường sau user definitions, condition sẽ xét các bean definitions đã đăng ký. Cách bố trí này làm rõ ý định thay vì đánh cược vào thứ tự hoặc việc Spring đã khởi tạo instance hay chưa.

### 6.7. Auto-configuration khác phụ thuộc bean concrete

`src/main/java/dev/example/autoconfigure/StoreDiagnosticsAutoConfiguration.java`:

```java
package dev.example.autoconfigure;

import dev.example.impl.InMemoryStore;
import dev.example.monitoring.StoreDiagnostics;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = StoreAutoConfiguration.class)
@ConditionalOnBean(InMemoryStore.class)
public class StoreDiagnosticsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(StoreDiagnostics.class)
    public StoreDiagnostics storeDiagnostics(InMemoryStore store) {
        return new StoreDiagnostics(store);
    }
}
```

Giải thích:

1. `after = StoreAutoConfiguration.class` yêu cầu Spring Boot xử lý auto-configuration này sau nguồn cung cấp mặc định, khi lựa chọn conditional bean đang cần metadata từ nguồn kia.
2. `@ConditionalOnBean(InMemoryStore.class)` không cần khởi tạo `InMemoryStore` trước; nó dựa trên bean definitions đã có và kiểu metadata có thể phân giải.
3. `@Bean public StoreDiagnostics storeDiagnostics(InMemoryStore store)` vừa công bố kiểu cụ thể vừa dùng method-parameter injection. Tránh gọi trực tiếp method `inMemoryStore()` vì auto-configuration có `proxyBeanMethods=false`.
4. `@ConditionalOnMissingBean(StoreDiagnostics.class)` cho người dùng lựa chọn cung cấp bean diagnostics của riêng họ nếu phù hợp.

**Không dùng việc thay method return type bằng interface rồi kỳ vọng điều kiện thứ hai luôn nhận biết implementation runtime.**

### 6.8. Khai báo file imports

Tạo tài nguyên `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.example.autoconfigure.StoreAutoConfiguration
dev.example.autoconfigure.StoreDiagnosticsAutoConfiguration
```

Spring Boot nhận cả hai class dù chúng nằm ngoài package gốc ứng dụng. Đặt auto-configuration trong package tách biệt, không thêm package đó vào component scan.

### 6.9. Người dùng tự cung cấp Store

`src/main/java/dev/example/app/CustomStore.java`:

```java
package dev.example.app;

import dev.example.api.Store;

public final class CustomStore implements Store {
    @Override
    public String read(String key) {
        return "custom:" + key;
    }
}
```

`src/main/java/dev/example/app/UserStoreConfiguration.java`:

```java
package dev.example.app;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class UserStoreConfiguration {

    @Bean
    public CustomStore customStore() {
        return new CustomStore();
    }
}
```

Class `UserStoreConfiguration` nằm dưới root application `dev.example.app` nên được component scan xét. Chỉ khi bật profile `custom`, bean `CustomStore` mới xuất hiện và khiến `@ConditionalOnMissingBean(Store.class)` của auto-configuration **không khớp**.

Lưu ý: Method người dùng cũng khai báo kiểu concrete `CustomStore`, nên Spring biết bean này là một `Store` từ quan hệ `implements Store`. Mặc dù không dùng `@Primary`, context vẫn chỉ có một bean `Store` trong mỗi tình huống.

### 6.10. Ứng dụng hiển thị kết quả

`src/main/java/dev/example/app/DemoApplication.java`:

```java
package dev.example.app;

import dev.example.api.Store;
import dev.example.monitoring.StoreDiagnostics;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            Store store = context.getBean(Store.class);
            StoreDiagnostics diagnostics =
                context.getBeanProvider(StoreDiagnostics.class).getIfAvailable();

            System.out.println(
                "store.class=" + store.getClass().getSimpleName()
            );
            System.out.println("store.read=" + store.read("sample"));
            System.out.println("diagnostics.present=" + (diagnostics != null));
            System.out.println(
                "diagnostics.kind=" +
                (diagnostics == null ? "none" : diagnostics.kind())
            );
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Bốn dòng do mã ứng dụng in ra (bỏ qua log Spring Boot):

```text
store.class=InMemoryStore
store.read=memory:sample
diagnostics.present=true
diagnostics.kind=InMemoryStore
```

Spring Boot nạp `StoreAutoConfiguration` qua imports, đăng ký `InMemoryStore`. Sau đó, điều kiện của diagnostics thấy bean kiểu `InMemoryStore` và tạo `StoreDiagnostics`.

Bật cấu hình người dùng:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=custom
```

Bốn dòng do mã ứng dụng in ra:

```text
store.class=CustomStore
store.read=custom:sample
diagnostics.present=false
diagnostics.kind=none
```

Ở nhánh custom, bean `CustomStore` là một `Store`, nên `StoreAutoConfiguration` nhường chỗ, đồng thời không có `InMemoryStore` để bật diagnostics. Đây là back-off đúng mục đích, không phải lỗi thiếu component scan.

## 7. Kiểm thử: metadata concrete, back-off theo interface, và return type quá rộng

Các test dưới đây dùng `ApplicationContextRunner` để tạo context nhỏ; không cần khởi động application web. Chúng được đặt trong package `dev.example.testing`, **ngoài phạm vi quét `dev.example.app`**, nên class cấu hình dùng riêng cho test không vô tình bị Spring Boot application scan.

### 7.1. Test các nhánh chính

File `src/test/java/dev/example/testing/StoreAutoConfigurationTest.java`:

```java
package dev.example.testing;

import dev.example.api.Store;
import dev.example.app.CustomStore;
import dev.example.autoconfigure.StoreAutoConfiguration;
import dev.example.autoconfigure.StoreDiagnosticsAutoConfiguration;
import dev.example.impl.InMemoryStore;
import dev.example.monitoring.StoreDiagnostics;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StoreAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(
                StoreAutoConfiguration.class,
                StoreDiagnosticsAutoConfiguration.class
            )
        );

    @Test
    void defaultStoreExposesConcreteMetadata() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Store.class);
            assertThat(context).hasSingleBean(InMemoryStore.class);
            assertThat(context).hasSingleBean(StoreDiagnostics.class);
            assertThat(context.getBean(Store.class).read("sample"))
                .isEqualTo("memory:sample");
            assertThat(context.getBean(StoreDiagnostics.class).kind())
                .isEqualTo("InMemoryStore");
        });
    }

    @Test
    void anyUserStoreCanMakeDefaultBackOff() {
        runner.withUserConfiguration(UserStoreForTest.class)
            .run(context -> {
                assertThat(context).hasSingleBean(Store.class);
                assertThat(context).hasSingleBean(CustomStore.class);
                assertThat(context).doesNotHaveBean(InMemoryStore.class);
                assertThat(context).doesNotHaveBean(StoreDiagnostics.class);
                assertThat(context.getBean(Store.class).read("sample"))
                    .isEqualTo("custom:sample");
            });
    }

    @Test
    void broadDeclaredReturnTypeCanHideConcreteTypeFromCondition() {
        new ApplicationContextRunner()
            .withUserConfiguration(BroadReturnTypeConfiguration.class)
            .withConfiguration(
                AutoConfigurations.of(StoreDiagnosticsAutoConfiguration.class)
            )
            .run(context -> {
                assertThat(context).hasSingleBean(Store.class);
                assertThat(context.getBean(Store.class))
                    .isInstanceOf(InMemoryStore.class);
                assertThat(context).doesNotHaveBean(StoreDiagnostics.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserStoreForTest {
        @Bean
        public CustomStore customStore() {
            return new CustomStore();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BroadReturnTypeConfiguration {
        @Bean
        public Store broadStore() {
            return new InMemoryStore();
        }
    }
}
```

**Tại sao test thứ ba quan trọng?**

- `BroadReturnTypeConfiguration.broadStore()` thật sự tạo instance `InMemoryStore`.
- Nhưng chữ ký khai báo `Store`; khi `@ConditionalOnBean(InMemoryStore.class)` được đánh giá trên `StoreDiagnosticsAutoConfiguration`, bean definition từ method không hứa hẹn kiểu concrete đó.
- Vì vậy diagnostics không được đăng ký trong ngữ cảnh test này; kể cả sau đó Spring tạo bean và ta chứng minh instance là `InMemoryStore`.
- Test này cố ý **không** nạp `StoreAutoConfiguration` để tránh việc một nguồn bean concrete khác làm kết quả nhiễu. Nó cô lập khác biệt giữa kiểu khai báo và kiểu runtime.

### 7.2. Integration test kiểm chứng file imports

File `src/test/java/dev/example/testing/ApplicationWiringTest.java`:

```java
package dev.example.testing;

import dev.example.api.Store;
import dev.example.app.DemoApplication;
import dev.example.impl.InMemoryStore;
import dev.example.monitoring.StoreDiagnostics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DemoApplication.class)
class ApplicationWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversAutoConfigurationOutsideComponentScan() {
        assertThat(context.getBean(Store.class))
            .isInstanceOf(InMemoryStore.class);
        assertThat(context.containsBean("inMemoryStore")).isTrue();
        assertThat(context.getBean(StoreDiagnostics.class).kind())
            .isEqualTo("InMemoryStore");
    }
}
```

Chạy từ thư mục project:

```bash
mvn -q test
```

Kỳ vọng **4 test pass** (3 test ở `StoreAutoConfigurationTest` và 1 test tích hợp). Integration test đang giả định profile `custom` **không được kích hoạt** bởi môi trường CI; nếu CI áp profile đó, cần xác lập lại profile mong muốn cho test trước khi đánh giá kết quả.

Hai cách kiểm thử không thay thế nhau:

- `ApplicationContextRunner` kiểm tra điều kiện và bean definitions của các auto-configuration do ta chọn, **không kiểm tra file imports đã được đóng gói**.
- `@SpringBootTest` kiểm tra toàn bộ luồng bootstrapping ứng dụng, qua đó giúp phát hiện tên class sai hoặc resource imports bị thiếu trên classpath.

## 8. Cách kiểm tra kiểu trả về một cách chủ động

Không nên chỉ gọi `context.getBean(...).getClass()` rồi cho rằng bean condition chắc chắn nhận ra kiểu đó. Thay vào đó, test nên kiểm tra **những điều kiện thật sự dùng metadata**.

### 8.1. Phân biệt runtime với registration-time

Giả sử:

```java
@Bean
public Store store() {
    return new InMemoryStore();
}
```

Sau khi khởi tạo:

```java
Store store = context.getBean(Store.class);
System.out.println(store.getClass().getSimpleName());
```

Có thể in:

```text
InMemoryStore
```

Nhưng đó là **runtime observation**. Một condition trên `InMemoryStore.class` được xét trước khi instance được khởi tạo có thể không khớp. Do vậy test thứ ba ở mục 7 quan sát trực tiếp kết quả conditional registration.

### 8.2. Dùng Condition Evaluation Report

Chạy:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Report điều kiện của Spring Boot có thể cho biết vì sao một auto-configuration hoặc `@Bean` method không khớp điều kiện. Khi bean của bạn xuất hiện ở runtime nhưng điều kiện `@ConditionalOnBean(ConcreteType.class)` không match, hãy kiểm tra **declared return type**, không chỉ class thực.

Với Actuator, endpoint `conditions` cũng có thể cung cấp thông tin, nếu đã thêm dependency, expose endpoint đúng và bảo vệ truy cập phù hợp.

### 8.3. Đối chiếu actual bean definitions

Khi cần debug sâu, có thể kiểm tra `BeanDefinition`, `factoryMethodName`, `resolvableType` hoặc metadata từ cấu hình Spring; nhưng không phải mọi bean definition đều có thông tin giống nhau (chẳng hạn bean do `FactoryBean`, proxy, factory method phức tạp). Nên xác nhận **kiểu mà điều kiện thực sự cần**, không phụ thuộc vào một phương thức inspect đơn lẻ.

## 9. Lưu ý về generic type, proxy và abstraction

### 9.1. Kiểu generic

Ví dụ trong hệ thống xử lý sự kiện:

```java
@Bean
public MessageHandler<OrderEvent> orderHandler() {
    return new OrderHandler();
}
```

Đây là **fragment** cần khai báo `MessageHandler`, `OrderEvent` và `OrderHandler`. Chữ ký giữ được thông tin tham số kiểu `OrderEvent`, khác với raw type:

```java
@Bean
@SuppressWarnings("rawtypes")
public MessageHandler rawHandler() {
    return new OrderHandler();
}
```

Spring Framework có khả năng sử dụng thông tin generic để phân giải dependency trong nhiều ngữ cảnh; việc giữ generic signature rõ ràng giúp framework và tooling tránh suy đoán. Tuy nhiên, cách `@ConditionalOnBean` cụ thể so khớp generic hay proxy phụ thuộc API và metadata thực tế; hãy **kiểm thử trường hợp của mình** thay vì suy diễn rằng mọi `ResolvableType` đều được xử lý giống nhau trong mọi condition.

### 9.2. Proxy/AOP

Khi bean được áp dụng AOP proxy, `bean.getClass()` có thể là proxy class (JDK dynamic proxy hoặc CGLIB). Kiểu runtime quan sát được không nhất thiết là implementation class gốc. Đừng dựa vào `getClass().getSimpleName()` trong business logic để định danh bean; ví dụ mục 6 chỉ dùng nó để diễn giải khi không có AOP.

Nếu một bean buộc phải truy cập qua interface trong runtime (chẳng hạn JDK proxy), public API có thể công bố interface và condition phải được thiết kế phù hợp. Quy tắc “càng cụ thể càng tốt” là **ưu tiên cho metadata**, không phải lệnh buộc lộ mọi implementation nội bộ bất chấp encapsulation và proxy semantics.

### 9.3. Optional dependency

Nếu một `@Bean` method trả về kiểu đến từ SDK **có thể không tồn tại** trên classpath, chỉ đặt `@ConditionalOnClass` trên method có thể không đủ an toàn: JVM có thể cần resolve method signature trước khi điều kiện chạy.

Một cách bền vững là đặt method trong **nested configuration class** được gắn `@ConditionalOnClass` ở cấp class:

```java
@AutoConfiguration
class OptionalSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        OptionalClient optionalClient() {
            return new OptionalClient();
        }
    }
}
```

**Đoạn này chỉ minh họa thiết kế, không phải mã chạy độc lập:** cần imports, class SDK `OptionalClient` và resource imports tương ứng. Trong JAR thư viện thật, class bytecode tham chiếu SDK phải được đóng gói nhưng ứng dụng có thể chạy khi SDK vắng mặt nhờ điều kiện ở class cấu hình con. Phương án nested condition bảo vệ class loading, còn kiểu trả về của `@Bean` vẫn đủ cụ thể ở nhánh có SDK.

## 10. @AutoConfiguration, thứ tự và thiết kế theo metadata

Auto-configuration thường được Spring Boot xử lý **sau các định nghĩa cấu hình người dùng**, tạo điều kiện cho `@ConditionalOnMissingBean(Store.class)` thực hiện back-off. Trong nhóm nhiều auto-configuration, có thể cần chỉ định thứ tự:

```java
@AutoConfiguration(after = StoreAutoConfiguration.class)
class StoreDiagnosticsAutoConfiguration {
    // ...
}
```

Đây là **fragment** về thứ tự, không phải một class độc lập. Nó điều khiển **thứ tự xử lý auto-configuration**, không bảo đảm instance của mọi bean ở cấu hình trước được tạo trước.

Vì sao việc này liên quan return type?

1. `StoreAutoConfiguration` đăng ký định nghĩa bean mặc định từ `public InMemoryStore inMemoryStore()`.
2. `StoreDiagnosticsAutoConfiguration` được xử lý sau và cần `@ConditionalOnBean(InMemoryStore.class)`.
3. Kiểu trả về cụ thể giúp điều kiện thứ hai nhận biết bean qua metadata, **ngay cả khi InMemoryStore chưa được khởi tạo**.
4. Nếu chỉ công bố `Store`, bean về mặt runtime có thể vẫn là `InMemoryStore` nhưng condition không nhất thiết nhận ra.
5. Nếu source bean chưa được xử lý trước, ngay cả chữ ký concrete cũng có thể không giúp condition match: **return type đủ cụ thể và processing order phù hợp là hai yêu cầu độc lập**.

Tránh dùng method call giữa các `@Bean` để “ép Spring tạo trước”:

```java
@Bean
public StoreDiagnostics storeDiagnostics() {
    return new StoreDiagnostics(inMemoryStore());
}
```

Đoạn trên là **mẫu nên tránh** khi `@AutoConfiguration` dùng `proxyBeanMethods=false`; lời gọi `inMemoryStore()` trực tiếp là lời gọi Java và có thể tạo instance ngoài lifecycle quản lý của container. Mẫu đúng là nhận dependency qua tham số:

```java
@Bean
public StoreDiagnostics storeDiagnostics(InMemoryStore store) {
    return new StoreDiagnostics(store);
}
```

## 11. Các lựa chọn thiết kế có chủ đích

### Lựa chọn A: công bố concrete implementation

```java
@Bean
public RedisBackedStore redisBackedStore() {
    return new RedisBackedStore();
}
```

**Phù hợp khi:** downstream auto-configuration/condition thực sự cần biết implementation hoặc các bean phụ trợ chỉ hoạt động với class này. Yêu cầu implementation type được đưa vào public API; refactor implementation có thể ảnh hưởng consumer.

### Lựa chọn B: công bố interface

```java
@Bean
public Store store() {
    return new RedisBackedStore();
}
```

**Phù hợp khi:** chủ động ẩn implementation, hỗ trợ đa dạng các implementation hoặc hạn chế coupling. Khi đó condition ở component khác nên dựa trên `Store.class` hoặc một contract marker công khai, **không dựa vào việc Spring đoán ra `RedisBackedStore.class`**.

### Lựa chọn C: công bố concrete nhưng back-off theo interface

```java
@Bean
@ConditionalOnMissingBean(Store.class)
public RedisBackedStore redisBackedStore() {
    return new RedisBackedStore();
}
```

**Phù hợp khi:** cần một mặc định cụ thể, hỗ trợ downstream features tùy loại implementation và vẫn cho phép người dùng thay bằng bất kỳ `Store` nào. Đây là hình thức của ví dụ runnable ở mục 6.

Cả ba đoạn chỉ là fragments; class `RedisBackedStore` chưa được định nghĩa trong project demo.

### Lựa chọn D: nhiều bean cùng interface được thiết kế có chủ đích

Nếu ứng dụng cần nhiều bean `Store` khác nhau (primary/secondary, đọc/ghi, multi-tenancy), điều kiện `@ConditionalOnMissingBean(Store.class)` có thể quá rộng: bất kỳ bean `Store` nào cũng tắt mặc định. Khi đó thiết kế rõ theo tên bean, qualifier hoặc những annotation marker cụ thể; đừng cố xử lý bằng cách khai báo return type `Object`.

Spring Boot có thêm tham số như `name`, `annotation`, `search` cho condition phù hợp từng ngữ cảnh. Hãy chọn điều kiện phản ánh **hợp đồng chức năng**, còn return type phản ánh **kiểu bean tạo ra**.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Triệu chứng | Hướng xử lý |
| --- | --- | --- |
| Khai báo `@Bean public Object service()` | Điều kiện hoặc injection theo `ServiceImpl` không thấy kiểu mong muốn | Trả về `ServiceImpl` nếu kiểu đó là phần hợp đồng cần công bố. |
| Khai báo `@Bean public Service service()` dù downstream cần `ServiceImpl` | Bean có instance đúng sau startup nhưng `@ConditionalOnBean(ServiceImpl.class)` không match | Công bố kiểu cụ thể hoặc đổi condition theo interface/contract. |
| Dùng `@ConditionalOnMissingBean` trống trên method trả kiểu concrete | User bean implement interface khác kiểu concrete không khiến default back off | Viết `@ConditionalOnMissingBean(Service.class)` nếu mọi implementation nên thay default. |
| Dùng `@ConditionalOnMissingBean(Service.class)` khi muốn nhiều Service đồng tồn tại | Chỉ một bean Service của user cũng làm default biến mất | Cân nhắc condition theo bean name, annotation marker hoặc phân biệt role. |
| Chỉ xem `getBean(...).getClass()` | Runtime class đúng nhưng condition không khớp | Test kết quả condition/bean definition; xem chữ ký `@Bean`. |
| Tạo dependency bằng gọi trực tiếp method trong auto-configuration | Có thể tạo instance thừa vì `proxyBeanMethods=false` | Inject dependency làm tham số `@Bean` method. |
| Method trả kiểu SDK tùy chọn nhưng SDK vắng mặt | Có thể lỗi class loading trước khi condition trên method có cơ hội chạy | Bảo vệ bằng `@ConditionalOnClass` ở nested configuration class. |
| Nhầm `public` với yêu cầu Spring phải thấy kiểu concrete | Đổi visibility nhưng lỗi condition vẫn còn | Kiểm tra declared return type và condition target. |
| Quên order giữa auto-configurations | Condition dùng bean từ cấu hình khác đánh giá quá sớm | Dùng `@AutoConfiguration(after=...)` khi có quan hệ phụ thuộc. |
| Trộn package auto-configuration vào component scan ứng dụng | Cấu hình có thể bị nạp ngoài luồng intended/condition | Đăng ký qua `AutoConfiguration.imports`, giữ package riêng. |
| Để type implementation không truy cập được nhưng muốn consumer public tham chiếu | Module khác không compile được chữ ký/điều kiện | Cân nhắc public contract hoặc public implementation có chủ đích. |

## 13. Checklist khi review một @Bean method của starter

1. **Tên bean:** Bean này được nhận diện chủ yếu qua name hay type? Nếu có nhiều bean cùng kiểu, tên và qualifier có quan trọng không?
2. **Kiểu trả về:** Nó đang trả `Object`, raw type, interface hay class cụ thể? Người đọc metadata cần phân giải kiểu nào?
3. **Visibility:** Method và return type có khả năng truy cập nhất quán với public API dự định không? `public` có thực sự cần theo thiết kế library không?
4. **Back-off:** `@ConditionalOnMissingBean` được ghi rõ contract mà user có thể thay thế chưa?
5. **Điều kiện downstream:** `@ConditionalOnBean(ConcreteType.class)` có thể thấy type từ chữ ký của bean provider mà không cần tạo instance không?
6. **Thứ tự:** Nếu bean provider và consumer là hai auto-configuration khác nhau, có ràng buộc `before/after` thích hợp chưa?
7. **Optional classpath:** Chữ ký có nhắc SDK class tùy chọn không; có cần nested configuration gắn class condition không?
8. **Proxy:** Kiểu khai báo có tương thích với cơ chế proxy thực tế và abstraction mà component khác nên phụ thuộc không?
9. **Generic:** Các tham số generic quan trọng có được giữ lại trong chữ ký không?
10. **Thử nghiệm:** Đã có test chứng minh default, user override, condition theo concrete và tình huống return type quá rộng chưa?
11. **Đóng gói:** Auto-configuration có trong file imports, không phụ thuộc component scan của app không?
12. **Quan sát:** Khi condition thất bại, đã xem Condition Evaluation Report và bean definitions thay vì chỉ xem instance sau startup chưa?

## 14. Câu hỏi tự kiểm tra

1. `@Bean public Object storage() { return new DiskStorage(); }` có đảm bảo `@ConditionalOnBean(DiskStorage.class)` khớp trước khi bean tạo không? **Không**; kiểu khai báo chỉ hứa hẹn `Object`.
2. Tại sao `@Bean public InMemoryStore inMemoryStore()` có ích? **Vì Spring biết kiểu concrete từ chữ ký**, giúp type-based conditions nhận diện nó ở giai đoạn xử lý definitions.
3. Có nên viết `@ConditionalOnMissingBean` không tham số trên method trả `InMemoryStore` nếu user được thay bằng `RemoteStore implements Store`? **Thông thường không**; nên dùng `@ConditionalOnMissingBean(Store.class)`.
4. `public` có bắt buộc với mọi Spring `@Bean` method? **Không**. Visibility và metadata kiểu trả về là hai vấn đề khác.
5. Khi instance runtime là `InMemoryStore`, có chắc condition theo concrete trước đó match? **Không**; xem thời điểm đánh giá và declared type.
6. `@ConditionalOnMissingBean(Store.class)` có làm Spring xóa bean mặc định đã tạo không? **Không**; nếu condition không khớp thì bean mặc định không được đăng ký từ method đó.
7. `@AutoConfiguration(after=X.class)` có bảo đảm method `@Bean` của X đã được gọi tạo instance không? **Không**; điều đó chỉ định thứ tự xử lý cấu hình.
8. Nếu mục tiêu là che implementation và cho consumer dùng contract, dùng return type interface có hợp lý không? **Có**, miễn là downstream không phụ thuộc vào metadata kiểu concrete.
9. Khi method `@Bean` trả kiểu SDK tùy chọn, vì sao nên dùng nested `@Configuration` được bảo vệ bởi `@ConditionalOnClass`? **Để tránh class loading của method signature khi SDK không có mặt**.
10. Kiểm thử nào giúp kiểm tra condition mà không khởi động toàn ứng dụng? **`ApplicationContextRunner`** với cấu hình và user beans được khai báo có chủ đích.

## Tài liệu tham khảo chính thức

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): hướng dẫn rõ về việc khai báo type information càng đầy đủ càng tốt trong return type của `@Bean` và đánh giá bean conditions.
- [Spring Boot 3.5 — ConditionalOnBean API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): matching theo bean definition và thông tin thời điểm điều kiện xét.
- [Spring Boot 3.5 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): quy tắc mặc định với `@Bean` methods và các tiêu chí lựa chọn.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): `@Bean`, kiểu của bean definition, tham số method và scope.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): back-off, exclude và Condition Evaluation Report.
