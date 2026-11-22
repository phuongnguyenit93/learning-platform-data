# Đặt điều kiện tại lớp hay từng `@Bean` để kiểm soát mức độ “nhường chỗ” trong Spring Boot

## 1. “Nhường chỗ” nghĩa là gì?

Trong Spring Boot, auto-configuration cung cấp bean mặc định để ứng dụng hoạt động nhanh, nhưng thường phải **nhường chỗ (back off)** khi ứng dụng đã khai báo bean phù hợp. Cơ chế phổ biến là `@ConditionalOnMissingBean`: chỉ đăng ký cấu hình hoặc bean được đánh dấu khi **chưa có bean đáp ứng tiêu chí** trong `BeanFactory` tại thời điểm Spring đánh giá điều kiện.

“Nhường chỗ” ở đây là **không đăng ký bean mặc định ngay từ đầu**, khác với việc ghi đè một bean definition đã có. Nó cũng khác `@Primary`: `@Primary` chỉ ưu tiên chọn bean khi tiêm phụ thuộc nếu có nhiều ứng viên, không tự loại bỏ bean mặc định.

Vấn đề đặt ra: nếu một auto-configuration tạo **nhiều bean**, người dùng muốn tùy chỉnh một bean thì các bean mặc định còn lại có nên tồn tại không? **Vị trí đặt annotation quyết định phạm vi ảnh hưởng.**

## 2. Cơ chế theo vị trí đặt điều kiện

### 2.1. Đặt tại lớp cấu hình: cổng chung cho toàn bộ cấu hình

```java
@AutoConfiguration
@ConditionalOnMissingBean(NotificationSender.class)
public class NotificationAutoConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

Ở đây, Spring đánh giá điều kiện đối với **lớp `NotificationAutoConfiguration`**. Nếu đã có `NotificationSender` do ứng dụng định nghĩa, lớp cấu hình không được đăng ký; cả phương thức `notificationSender()` **và** `retryPolicy()` đều không đóng góp bean. Dù `RetryPolicy` không liên quan trực tiếp đến sender, nó vẫn bị loại theo cổng chung.

Điều kiện trên lớp cần **chỉ rõ tiêu chí**, chẳng hạn `@ConditionalOnMissingBean(NotificationSender.class)`, vì không có kiểu trả về của phương thức `@Bean` để suy ra. Một điều kiện ở lớp không tự động kiểm tra riêng rẽ tất cả kiểu bean mà lớp đó có thể tạo.

Kỹ thuật này phù hợp khi **cả nhóm bean là một đơn vị chức năng không thể tách rời**, và một bean do người dùng tự cung cấp được coi là thay thế trọn nhóm. Nếu các bean có thể tùy chỉnh độc lập, cổng chung thường quá rộng.

### 2.2. Đặt tại từng `@Bean`: nhường chỗ độc lập

```java
@AutoConfiguration
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

Lúc này, mỗi phương thức có một điều kiện riêng:

- Nếu ứng dụng có `NotificationSender`, **chỉ** bean sender mặc định nhường chỗ.
- Nếu ứng dụng chưa có `RetryPolicy`, bean retry mặc định **vẫn được đăng ký**.
- Nếu ứng dụng cung cấp `RetryPolicy` nhưng chưa có sender, sender mặc định vẫn hoạt động.

`@Configuration`/`@AutoConfiguration` vẫn có thể được đăng ký dù một số phương thức `@Bean` bị bỏ qua. Đây thường là lựa chọn đúng khi xây dựng starter có **nhiều điểm mở rộng độc lập**.

Với `@ConditionalOnMissingBean` đặt trực tiếp trên `@Bean`, nếu không ghi `value`, `type`, `name` hoặc `annotation`, Spring Boot mặc định dùng **kiểu trả về khai báo** của phương thức để so khớp. Viết tường minh kiểu như ở ví dụ giúp mục đích rõ ràng hơn, nhất là khi API có interface và implementation.

### 2.3. So sánh bằng các tình huống cụ thể

Giả sử auto-configuration cung cấp hai default: `NotificationSender` và `RetryPolicy`; điều kiện cấp lớp chỉ kiểm tra sự thiếu vắng `NotificationSender`.

| Bean do ứng dụng khai báo | Điều kiện tại lớp theo `NotificationSender` | Điều kiện riêng ở hai `@Bean` |
| --- | --- | --- |
| Không khai báo bean nào | Có cả sender và retry mặc định | Có cả sender và retry mặc định |
| Chỉ có sender tùy chỉnh | Cả hai default bị bỏ; **không còn retry mặc định** | Sender mặc định bị bỏ; **retry mặc định vẫn có** |
| Chỉ có retry tùy chỉnh | Cấu hình vẫn chạy và có thể tạo **retry mặc định thứ hai** vì cổng lớp không kiểm tra `RetryPolicy` | Có sender mặc định; retry tùy chỉnh được dùng |
| Có cả sender và retry tùy chỉnh | Toàn bộ cấu hình nhường chỗ | Mỗi default tương ứng nhường chỗ |

Hàng thứ ba là một lỗi thiết kế dễ bỏ sót: `@ConditionalOnMissingBean(NotificationSender.class)` tại lớp **không đảm bảo** một bean `RetryPolicy` mặc định sẽ nhường chỗ. Nếu hai bean cùng kiểu mang tên khác nhau, ứng dụng có thể có hai ứng viên và gặp lỗi mơ hồ khi tiêm theo kiểu.

## 3. Ví dụ Spring Boot 3.3.x / Java 17+ chạy được

Ví dụ dùng một ứng dụng Maven nhỏ. Gói `demo.app` là gói quét component của ứng dụng; gói `demo.autoconfigure` nằm ngoài phạm vi quét và được Spring Boot nạp đúng cách qua file `AutoConfiguration.imports`. Ban đầu, ứng dụng có sender tùy chỉnh nhưng không tự cung cấp retry.

Cấu trúc các tệp chính:

```text
pom.xml
src/main/java/demo/api/NotificationSender.java
src/main/java/demo/api/RetryPolicy.java
src/main/java/demo/autoconfigure/NotificationAutoConfiguration.java
src/main/java/demo/app/DemoApplication.java
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>bean-condition-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**`src/main/java/demo/api/NotificationSender.java`**

```java
package demo.api;

public interface NotificationSender {
    String send(String message);
}
```

**`src/main/java/demo/api/RetryPolicy.java`**

```java
package demo.api;

public record RetryPolicy(int maxAttempts) {
}
```

**`src/main/java/demo/autoconfigure/NotificationAutoConfiguration.java`** — bản nhường chỗ **theo từng bean**:

```java
package demo.autoconfigure;

import demo.api.NotificationSender;
import demo.api.RetryPolicy;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
demo.autoconfigure.NotificationAutoConfiguration
```

Tên này phải khớp với tên lớp auto-configuration đầy đủ. Trong Spring Boot 3.x, đây là cơ chế khai báo các auto-configuration candidate cho thư viện/starter. Không dùng component scanning để tự động phát hiện lớp auto-configuration.

**`src/main/java/demo/app/DemoApplication.java`**

```java
package demo.app;

import demo.api.NotificationSender;
import demo.api.RetryPolicy;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    public NotificationSender userSender() {
        return message -> "user:" + message;
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {
            NotificationSender sender =
                    context.getBean(NotificationSender.class);
            Map<String, RetryPolicy> policies =
                    context.getBeansOfType(RetryPolicy.class);

            String retry = policies.isEmpty()
                    ? "none"
                    : Integer.toString(
                            policies.values().iterator().next().maxAttempts());

            System.out.println("sender=" + sender.send("ping"));
            System.out.println("retry=" + retry);
        }
    }
}
```

Build và chạy từ thư mục chứa `pom.xml` (có JDK 17+ và Maven):

```bash
mvn -q -DskipTests package
java -jar target/bean-condition-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

**Stdout mong đợi của bản điều kiện trên từng `@Bean`:**

```text
sender=user:ping
retry=3
```

Giải thích: `userSender()` của ứng dụng đăng ký một `NotificationSender`, nên điều kiện của `notificationSender()` mặc định không khớp. Tuy nhiên chưa có `RetryPolicy`, vì vậy `retryPolicy()` mặc định vẫn được đăng ký với `maxAttempts = 3`.

### Thử chuyển điều kiện lên lớp

Thay **toàn bộ nội dung** `NotificationAutoConfiguration.java` bằng bản sau; giữ nguyên các tệp khác:

```java
package demo.autoconfigure;

import demo.api.NotificationSender;
import demo.api.RetryPolicy;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnMissingBean(NotificationSender.class)
public class NotificationAutoConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

Chạy lại hai lệnh build/run như trên. **Stdout mong đợi:**

```text
sender=user:ping
retry=none
```

Sender do ứng dụng cung cấp vẫn hoạt động. Nhưng vì điều kiện cấp lớp không khớp, `NotificationAutoConfiguration` không đóng góp **bất kỳ** bean nào, kể cả `RetryPolicy`; ứng dụng không còn retry mặc định.

Thử bỏ phương thức `userSender()` khỏi `DemoApplication` và build lại: không còn sender tự định nghĩa, nên **cả hai cách đặt điều kiện** đều có thể cung cấp sender và retry mặc định. Kết quả khi đó là `sender=default:ping` và `retry=3`. Điều này cho thấy khác biệt chính xuất hiện khi người dùng chỉ tùy chỉnh **một phần** bộ default.

## 4. Chọn vị trí điều kiện đúng theo ranh giới tùy chỉnh

**Chọn điều kiện ở lớp** khi nhiều bean tạo thành **một nhóm không nên tồn tại riêng lẻ**. Ví dụ, một adapter có toàn bộ cấu hình phụ thuộc vào sự hiện diện của một thư viện: `@ConditionalOnClass(VendorClient.class)` có thể đặt trên một lớp cấu hình riêng để chỉ nạp nhóm khi dependency có mặt. Một cờ tính năng cũng có thể là điều kiện chung:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.notification",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class NotificationAutoConfiguration {
    // Các @Bean mặc định, mỗi bean vẫn có thể có điều kiện riêng.
}
```

Đoạn trên chỉ minh họa điều kiện chung; thay vì dùng nguyên lớp này cùng lớp trong ví dụ chạy, hãy **kết hợp annotation cấp lớp** với các phương thức `@Bean` đã trình bày. Cổng cấp lớp trả lời “tính năng có được bật không?”, còn điều kiện cấp phương thức trả lời “đã có bean do người dùng cung cấp chưa?”. Khi cả hai mức cùng có điều kiện, bean chỉ được đăng ký nếu **mọi điều kiện liên quan đều khớp**.

**Chọn điều kiện trên từng `@Bean`** khi người dùng được phép thay thế từng thành phần như sender, cache, policy, serializer hoặc client mà vẫn muốn sử dụng các thành phần mặc định khác. Đây là dạng back-off thường thích hợp nhất cho starter và auto-configuration mở rộng được.

**Kết hợp hai mức** khi cần cổng chung thật sự (classpath, property, môi trường web...) và các fallback độc lập. Không dùng một điều kiện kiểm tra thiếu bean ở cấp lớp chỉ để “tiện tay” áp dụng cho nhiều bean có vai trò khác nhau.

## 5. Những điểm dễ sai và cách kiểm tra

1. **Nhầm back-off với override:** `@ConditionalOnMissingBean` giúp bean mặc định **không được đăng ký** nếu đã có bean phù hợp. `spring.main.allow-bean-definition-overriding` điều khiển việc nhiều bean definition có cùng tên ghi đè nhau; bật nó không thay thế thiết kế điều kiện đúng. `@Primary` chỉ ảnh hưởng lựa chọn khi tiêm bean.

2. **Đặt điều kiện quá rộng:** Nếu chỉ muốn tùy chỉnh sender mà vẫn giữ retry, đừng khóa cả class bằng `@ConditionalOnMissingBean(NotificationSender.class)`. Dùng một điều kiện riêng cho từng default, và kiểm tra cả các trường hợp “chỉ override A”, “chỉ override B”, “override cả hai”.

3. **Đặt tiêu chí sai loại:** `@ConditionalOnMissingBean(NotificationSender.class)` kiểm tra **theo kiểu bean**, không phải theo tên phương thức. `@ConditionalOnMissingBean(name = "notificationSender")` chỉ kiểm tra tên. Một bean do người dùng đặt tên `customSender` nhưng vẫn có kiểu `NotificationSender` sẽ làm điều kiện **theo kiểu** không khớp; điều kiện **theo tên** có thể vẫn khớp. Chọn kiểu hoặc tên theo hợp đồng mở rộng thực sự.

4. **Suy kiểu từ chữ ký `@Bean` quá chung:** Trên phương thức, `@ConditionalOnMissingBean` không khai báo tham số sẽ suy kiểu cần kiểm tra từ **kiểu trả về khai báo**. Một phương thức khai báo trả `Object` che mất thông tin kiểu quan trọng. Hãy khai báo kiểu trả về có ý nghĩa hoặc chỉ rõ điều kiện bằng `value`/`type`. Trên lớp, luôn chỉ rõ tiêu chí thiếu bean.

5. **Quên thứ tự đăng ký bean:** `@ConditionalOnBean` và `@ConditionalOnMissingBean` đánh giá trên **các bean definition đã được xử lý đến thời điểm đó**, không phải mọi bean sẽ xuất hiện về sau. Đặt chúng trong auto-configuration vì Spring Boot xử lý auto-configuration sau cấu hình người dùng. Nếu điều kiện phụ thuộc bean do **một auto-configuration khác** cung cấp, hãy sắp thứ tự phù hợp, ví dụ `@AutoConfiguration(after = OtherAutoConfiguration.class)`; thứ tự này điều khiển đăng ký definition, **không quyết định thứ tự tạo instance**.

6. **Cho rằng bean đã tồn tại chỉ vì có lớp Java:** `@ConditionalOnClass` kiểm tra classpath, còn `@ConditionalOnBean` kiểm tra bean trong context. Có class `NotificationSender` trên classpath không có nghĩa đã có một bean `NotificationSender`. Nếu điều kiện cần class của thư viện có thể vắng mặt, đặt `@ConditionalOnClass` trên lớp `@Configuration` độc lập để tránh rủi ro tải kiểu không có trên classpath từ chữ ký `@Bean`.

7. **Lỗi mơ hồ do nhiều bean cùng kiểu:** `@ConditionalOnMissingBean` theo kiểu chỉ ngăn default được đăng ký khi thấy bean phù hợp. Với điều kiện đặt sai phạm vi, hai bean khác tên nhưng cùng kiểu vẫn có thể đồng tồn tại, dẫn đến `NoUniqueBeanDefinitionException` khi tiêm một bean duy nhất không có qualifier. Cần sửa điều kiện và điểm mở rộng, không dựa vào `@Primary` để che lỗi thiết kế.

Khi kết quả khác dự kiến, chạy ứng dụng với `--debug` để xem **Condition Evaluation Report**, hoặc dùng `ApplicationContextRunner` trong test để kiểm tra từng tổ hợp bean do người dùng cung cấp. Trong test, xác minh cả **bean mặc định bị loại** lẫn **những bean mặc định cần được giữ lại**.

## 6. Quy tắc áp dụng nhanh

- **Một bean tùy chỉnh phải thay thế cả nhóm:** cân nhắc `@ConditionalOnMissingBean(TargetType.class)` ở **lớp**, nhưng chỉ khi việc loại cả nhóm được thiết kế có chủ ý.
- **Mỗi bean được tùy chỉnh riêng:** đặt `@ConditionalOnMissingBean(ThatBeanType.class)` ở **từng `@Bean`**.
- **Cần một điều kiện bật/tắt toàn bộ tính năng:** đặt điều kiện tổng quát ở **lớp** (ví dụ `@ConditionalOnProperty`), rồi đặt điều kiện thiếu bean trên **từng default độc lập**.
- **Có dependency giữa các auto-configuration:** kiểm soát thứ tự đăng ký và viết test với bean của người dùng có mặt/vắng mặt.

Câu hỏi tự kiểm tra quan trọng nhất: **“Nếu người dùng cung cấp một bean A, tôi có thực sự muốn mọi bean B, C, D cùng biến mất không?”** Nếu câu trả lời là **không**, hãy để điều kiện back-off tại từng `@Bean`.

## Tham khảo chính thức

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): cơ chế `@AutoConfiguration`, bean conditions, thứ tự xử lý và khai báo `AutoConfiguration.imports`.
- [Spring Boot API — `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): quy tắc so khớp và suy kiểu từ phương thức `@Bean`.
